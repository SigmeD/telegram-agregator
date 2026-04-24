# Версионирование LLM-промптов

LLM-промпт — это исходный код, от которого зависит качество классификации лидов (ТЗ FEATURE-05). Изменения промпта должны проходить такой же процесс, как изменения кода: версионирование, review, тестирование, откат.

## Принципы

1. **Иммутабельность.** Опубликованная версия промпта не редактируется. Любое изменение — новая версия.
2. **Прослеживаемость.** Каждая строка `lead_analysis` хранит поле `prompt_version` — по какой версии промпта была сделана классификация.
3. **Постепенный rollout.** Новая версия сначала прогоняется на validation-датасете, потом на shadow-трафике, только потом включается на prod.
4. **Быстрый откат.** Переключение между версиями — одна env-переменная без передеплоя кода.

## Структура каталога

```
prompts/
├── v1/
│   ├── classifier.md           # основной промпт классификатора
│   ├── enrichment.md           # промпт для обогащения bio (FEATURE-07)
│   ├── metadata.yaml           # автор, дата, модель-цель, ссылка на ADR/тикет
│   └── CHANGELOG.md            # что и почему изменилось относительно v0
├── v2/
│   └── ...
└── validation/
    ├── dataset.jsonl           # размеченные сообщения (100+ примеров, ТЗ FEATURE-05)
    └── results/
        ├── v1.json             # precision, recall, avg_cost, avg_latency
        └── v2.json
```

`metadata.yaml` обязательные поля:

```yaml
version: v2
author: max.eroxin
created_at: 2026-05-15
target_model: claude-haiku
supersedes: v1
related_ticket: FEATURE-05
changelog_summary: "Добавлен учёт reply_context; уточнено правило про вопросы 'а кто-нибудь делал X'."
```

## Процесс заведения новой версии

### 1. Создать ветку и каталог

```bash
git checkout -b prompts/v2-tune-reply-context
cp -r prompts/v1 prompts/v2
# редактируем prompts/v2/classifier.md, обновляем metadata.yaml
```

### 2. Прогнать на validation-датасете

```bash
python -m backend.scripts.eval_prompt --version v2 \
  --dataset prompts/validation/dataset.jsonl \
  --model claude-haiku \
  --output prompts/validation/results/v2.json
```

Скрипт считает:

- `precision` (ТЗ FEATURE-05: target > 80%)
- `recall` (target > 90%)
- `avg_cost_usd` (target < $0.005)
- `avg_latency_ms`
- `disagreements_vs_previous` — на каких примерах решение отличается от v1, для ручного ревью.

### 3. Acceptance-критерии новой версии

Версия допускается к merge только если:

- [ ] `precision >= precision(previous) - 2%` и не ниже 80%.
- [ ] `recall >= recall(previous) - 2%` и не ниже 90%.
- [ ] `avg_cost_usd <= 0.005`.
- [ ] Изменения просмотрены человеком (PM) на `disagreements_vs_previous`.
- [ ] Если добавляются новые поля в JSON-ответ — миграция БД для `lead_analysis` создана в том же PR.

### 4. Code review и merge

PR ревьюит как минимум один разработчик + PM (для классификатора). После merge версия попадает в репо, но НЕ активируется.

### 5. Shadow-режим (опционально для рискованных изменений)

```bash
# включить shadow для 10% трафика
# env:
# PROMPT_VERSION=v1
# PROMPT_SHADOW_VERSION=v2
# PROMPT_SHADOW_RATE=0.1
```

LLM-worker параллельно вызывает обе версии, пишет результаты, но для downstream (scoring, уведомления) используется только основная. Сравнение решений сохраняется в `prompt_shadow_comparisons` (отдельная таблица). Минимум 48 часов shadow перед promote.

### 6. Promote на prod

```bash
ssh deploy@vps.example.com
sudo -e /opt/tla/infra/.env.prod
# PROMPT_VERSION=v1 → PROMPT_VERSION=v2

# перезапуск только LLM-worker'а, без простоя listener'а
docker compose -f /opt/tla/infra/docker-compose.prod.yml up -d --no-deps celery-worker-llm

# наблюдаем метрики 24 часа
```

### 7. Откат

Если после promote падает precision или растёт стоимость:

```bash
sudo -e /opt/tla/infra/.env.prod
# PROMPT_VERSION=v2 → PROMPT_VERSION=v1
docker compose -f /opt/tla/infra/docker-compose.prod.yml up -d --no-deps celery-worker-llm
```

Откат мгновенный, предыдущие версии всегда остаются в `prompts/`.

## Хранение версии в БД

Каждая запись `lead_analysis` содержит `prompt_version VARCHAR(20)` (значение `"v2"`, `"v2+shadow"` и т.п.). Это позволяет:

- Считать метрики качества по версиям (`GROUP BY prompt_version`).
- При откате понимать, какие лиды были сделаны «плохой» версией.
- Воспроизводить решения — версия промпта доступна по пути `prompts/{prompt_version}/`.

Для shadow-результатов — отдельная таблица `prompt_shadow_comparisons` с `raw_message_id`, `version_a`, `version_b`, `diff_jsonb`.

## Связанные процессы

- Еженедельная ручная проверка 20 случайных решений LLM (ТЗ FEATURE-05) — источник сигнала для заведения новой версии.
- Cost-spike → возможен откат на предыдущую версию как быстрая мера (см. `docs/runbook/llm-cost-spike.md`).
- Новая мажорная версия промпта = ADR, если меняется контракт JSON-ответа.

## Ссылки

- ТЗ FEATURE-05
- ADR-0004
- `docs/runbook/llm-cost-spike.md`

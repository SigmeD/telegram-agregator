# Contributing

> Пока в проекте один активный контрибьютор (Максим) + Claude Code. Документ описывает процесс, чтобы при расширении команды не пришлось переучивать.

## TL;DR

1. Читаем [`CLAUDE.md`](./CLAUDE.md), [`BUSINESS_RULES.md`](./BUSINESS_RULES.md), [`docs/dor.md`](./docs/dor.md).
2. Ветка `feature/FEATURE-XX-short-name` от `develop`.
3. Пишем код + тесты, обновляем `CHANGELOG.md`.
4. PR в `develop` → шаблон PR → чеклист DoD должен быть заполнен.
5. CI зелёный → review → merge. Dev-деплой автоматом.
6. В `main` — через PR `develop → main` и **только** по команде Максима.

## Ветвление (Git Flow lite)

- `main` — prod. Всё, что здесь — развёрнуто (или будет развёрнуто вручную) в prod.
- `develop` — dev. Все фичи вливаются сюда. Автодеплой на dev Vercel/VPS.
- `feature/*`, `fix/*`, `docs/*`, `chore/*` — рабочие ветки.
- `release/X.Y.Z` — фризим develop, делаем bug-fix, вливаем в main и обратно в develop.
- `hotfix/*` — от main, сразу в main и develop.

## Коммиты

[Conventional Commits](https://www.conventionalcommits.org/ru/):

```
feat(listener): handle FloodWaitError with exponential backoff
fix(api): correct CORS for /api/v1/leads
docs(runbook): add LLM cost-spike playbook
chore(ci): bump actions/checkout to v4
refactor(scoring): extract weights to config table
test(filter): cover negative-marker early exit
```

## Definition of Ready / Done

- **DoR** (прежде чем брать задачу): [`docs/dor.md`](./docs/dor.md).
- **DoD** (прежде чем закрыть PR): [`docs/dod.md`](./docs/dod.md).

## Тесты

- **Backend:** `pytest -m "not integration"` на каждый коммит (быстро), `pytest -m integration` с testcontainers на PR.
- **Frontend:** `vitest` + React Testing Library. Покрытие критичных features.
- **E2E** (будет позже): Playwright на dev preview.

Минимум для PR: ≥ 70% coverage на изменённые файлы (для backend), зелёные интеграционные тесты, smoke-тест на критичные UI-страницы.

## Документация

Согласно правилу «после каждого релиза обновляем docs» — при каждом PR проверяем:

- `CHANGELOG.md` — обязательно (блокируется CI).
- `README.md` — если изменились команды запуска/архитектура.
- `CLAUDE.md` — если изменился стек/структура/workflow.
- `docs/architecture.md` — если изменилась схема потока данных.
- `docs/adr/NNNN-*.md` — если принято архитектурное решение.
- `docs/api/openapi.yaml` — если изменился публичный API.
- `docs/runbook/*.md` — если добавились новые алерты/процедуры.
- `BUSINESS_RULES.md` — если меняется продуктовый инвариант (+ ADR).
- `prompts/vN/` — если меняется LLM-промпт (только новая версия, старую не редактируем).

## Secrets

**Никогда** не коммитим `.env`, session-файлы, ключи, токены. Gitleaks работает в pre-commit и CI. Изменение переменных в `.env.example` — свободно. Заливка реальных значений в GitHub Secrets / Vercel env / VPS — **только после явного разрешения Максима**.

## Локальная настройка

```bash
git clone <repo-url>
cd telegram-aggregator
cp .env.example .env
pre-commit install
make up
make migrate
make seed
```

## Обсуждение и ревью

- Маленькие PR (< 400 строк diff) ревьюятся быстрее. Крупные фичи — дробим.
- В описании PR — ссылка на `FEATURE-XX` из ТЗ, чеклист DoD, скриншоты (для UI).
- Для архитектурных решений — заранее ADR в отдельном PR.

## Релизы

- `release/X.Y.Z` ветка → финальное тестирование на dev → PR в `main` → merge → тег `vX.Y.Z` → `workflow_dispatch cd-backend-prod` (после одобрения Максима) → Vercel promote → GitHub Release из CHANGELOG.

Подробно: [`docs/runbook/release.md`](./docs/runbook/release.md) (создаётся при первом релизе).

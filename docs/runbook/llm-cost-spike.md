# Runbook: Всплеск расходов на LLM API

**Severity по умолчанию:** SEV-2. SEV-1 если превышен недельный бюджет в 2x+.

## Признаки

- Алерт из Sentry/Grafana: `llm_cost_usd_daily > LLM_DAILY_BUDGET_USD`.
- Среднее `cost_usd` в `lead_analysis` за последний час > $0.005 (лимит по ТЗ FEATURE-05).
- Счета в Anthropic/OpenAI console растут быстрее ожидаемого.
- Процент сообщений, прошедших keyword-фильтр, внезапно вырос (например, из-за новых триггеров с низким порогом).

## Быстрая диагностика

```bash
ssh deploy@vps.example.com

# посмотреть топ моделей по расходу за 24 часа
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec api psql $DATABASE_URL -c "
  SELECT llm_model, COUNT(*) AS calls, SUM(cost_usd) AS total_usd, AVG(cost_usd) AS avg_usd
  FROM lead_analysis
  WHERE analyzed_at > now() - interval '24 hours'
  GROUP BY llm_model ORDER BY total_usd DESC;"

# посмотреть, растёт ли доля GPT-4 (fallback)
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec api psql $DATABASE_URL -c "
  SELECT date_trunc('hour', analyzed_at) AS h, llm_model, COUNT(*)
  FROM lead_analysis WHERE analyzed_at > now() - interval '24 hours'
  GROUP BY 1,2 ORDER BY 1 DESC;"
```

## Действие 1: Отключить GPT-4 fallback

Если причина — Anthropic лежит и весь трафик ушёл на GPT-4 (дороже в разы):

```bash
# редактируем env
sudo -e /opt/tla/infra/.env.prod
# ставим:
# LLM_FALLBACK_ENABLED=false

# применить без простоя LLM-worker'ов
docker compose -f /opt/tla/infra/docker-compose.prod.yml up -d --no-deps celery-worker-llm
```

Поведение при `LLM_FALLBACK_ENABLED=false`: при недоступности Anthropic задача ставится в dead-letter с `processing_status='error'` и в Sentry падает алерт. Это сохраняет данные в `raw_messages` для последующего re-enqueue.

## Действие 2: Переключить PROMPT_VERSION на экономичную

Если текущий промпт раздулся (большой контекст → больше токенов), откатиться на предыдущую версию:

```bash
# узнать текущую и доступные версии
ls /opt/tla/backend/prompts/

sudo -e /opt/tla/infra/.env.prod
# меняем:
# PROMPT_VERSION=v2  → PROMPT_VERSION=v1

docker compose -f /opt/tla/infra/docker-compose.prod.yml up -d --no-deps celery-worker-llm
```

Процесс заведения новой (экономичной) версии — `docs/prompts-versioning.md`.

## Действие 3: Отключить обработку низкоприоритетных источников

Снизить входящий объём, обрабатывая только `priority >= 8` (hot-lane):

```bash
# мягкая мера — приостановить low-priority
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec api psql $DATABASE_URL -c "
  UPDATE telegram_sources SET is_active=false WHERE priority < 5 AND is_active=true;"

# listener подхватит через periodic refresh (каждые 60 сек)
```

После устранения spike'а — вернуть:

```bash
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec api psql $DATABASE_URL -c "
  UPDATE telegram_sources SET is_active=true WHERE priority < 5 AND priority IS NOT NULL;"
```

## Действие 4: Жёсткий circuit breaker

Если расходы не снижаются — остановить LLM-worker полностью. `raw_messages` продолжат накапливаться с `processing_status='pending'`, обработаем после устранения причины.

```bash
docker compose -f /opt/tla/infra/docker-compose.prod.yml stop celery-worker-llm
```

Входящие сообщения не теряются (Postgres ledger, ADR-0006).

## Post-mortem: что проверить после

- Не появились ли новые keyword-триггеры с весом, который пропускает слишком много?
- Не вырос ли трафик на источниках (новое вирусное обсуждение)?
- Не регрессировал ли промпт по токен-бюджету?
- Актуальны ли цены Claude/OpenAI — провайдеры могли поднять тарифы.

## Уведомить

- Максим — Telegram DM.
- `#incidents`, со ссылкой на запрос и цифрами.

## Ссылки

- ADR-0004
- ТЗ FEATURE-05, разд. 5 (бюджет)
- `docs/prompts-versioning.md`

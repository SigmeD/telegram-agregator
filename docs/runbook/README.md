# Runbook

Операционные процедуры для эксплуатации Telegram Lead Aggregator. Каждый документ — actionable: конкретные команды, пути к файлам, ожидаемые результаты. Теория — в `docs/architecture.md` и ADR.

## Процедуры

| Файл | Когда применять |
|------|-----------------|
| [`telethon-ban.md`](./telethon-ban.md) | Telethon-аккаунт не может подключиться, получает `AuthKeyError`, `ChannelPrivateError`, длинный `FloodWaitError`, либо есть уведомление от Telegram о restriction. |
| [`redis-down.md`](./redis-down.md) | Redis недоступен, Celery worker'ы падают/пустые, очередь не опустошается, listener получает ошибки при публикации задач. |
| [`llm-cost-spike.md`](./llm-cost-spike.md) | Расходы на Anthropic/OpenAI API превышают дневной/недельный лимит; растёт `cost_usd` в `lead_analysis` за окно времени; алерт `LLM_DAILY_BUDGET_USD` в Sentry. |
| [`db-restore.md`](./db-restore.md) | Требуется восстановить Postgres из бэкапа после потери данных, повреждения, неудачной миграции или для проверки RPO/RTO. |

## Общие принципы реагирования

1. **Зафиксировать инцидент.** Создать запись в `#incidents` (канал Telegram команды) с timestamp, кто on-call, симптомы.
2. **Снизить ущерб.** Сначала остановить деградацию (circuit breaker, отключение non-critical воркеров), потом диагностировать.
3. **Применить runbook.** Не импровизировать — если процедура устарела, сначала обновляем runbook, потом выполняем.
4. **Постмортем.** Для любого инцидента severity >= SEV-2 — постмортем в `docs/retro/` в течение 48 часов.

## Контакты

| Роль | Кто | Канал |
|------|-----|-------|
| On-call primary | Максим | Telegram DM |
| Backend engineer | TBD | Telegram DM |
| Anthropic status | https://status.anthropic.com | — |
| Telegram status | https://t.me/s/tginfo | — |
| Hetzner status | https://status.hetzner.com | — |

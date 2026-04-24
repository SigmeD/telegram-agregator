# Архитектура Telegram Lead Aggregator

Документ описывает высокоуровневую архитектуру модуля. Детали реализации — в коде и соответствующих ADR. Источник требований: `TZ_Telegram_Lead_Aggregator.md` (далее — ТЗ).

## 1. Высокоуровневая схема

Схема воспроизведена из ТЗ разд. 2.1.

```
┌─────────────────────────────────────────────────────────────┐
│                 TELEGRAM LEAD AGGREGATOR                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Telethon Listener]  →  [Message Queue]  →  [Processor]    │
│         ↓                      ↓                   ↓         │
│   User-session          Redis/RabbitMQ      LLM Classifier  │
│   Читает чаты           Буфер сообщений     Claude/GPT-4    │
│                                                   ↓          │
│                                          [Scoring Engine]    │
│                                                   ↓          │
│                                          [Database: PG]     │
│                                                   ↓          │
│                              ┌────────────────────┴───┐     │
│                              ↓                        ↓     │
│                    [Telegram Bot]            [Admin UI]     │
│                    Уведомления Максиму       Next.js/React  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 2. Поток данных

1. **Telethon Listener** (user-session, см. ADR-0003) слушает `events.NewMessage` по всем активным источникам. При получении сообщения синхронно пишет сырую запись в `raw_messages` (Postgres — ledger, см. ADR-0006), затем публикует задачу в Redis-очередь.
2. **Celery worker — keyword-filter** (см. ТЗ разд. 3, FEATURE-04) берёт задачу, применяет справочник `keyword_triggers`: при сумме весов < 5 или срабатывании отрицательного маркера ставит `processing_status=filtered_out` и завершает цепочку.
3. **Celery worker — LLM classifier** (FEATURE-05) вызывает Claude Haiku (ADR-0004), в JSON получает `is_lead`, `confidence`, `lead_type`, `urgency`, `budget_signals`, `vertical`, `extracted_needs`, `reasoning`, сохраняет в `lead_analysis` вместе с `llm_model`, `tokens_used`, `cost_usd` и `prompt_version`.
4. **Scoring Engine** (FEATURE-06) считает итоговый скор 0–100 по формуле из ТЗ разд. FEATURE-06, категоризирует как Hot/Warm/Cold/Irrelevant.
5. **Enrichment worker** (FEATURE-07) дополнительно обогащает `sender_profiles` по автору лида.
6. **Notification fanout**: Hot → мгновенное push через Aiogram-бот Максиму; Warm → дневной дайджест; Cold → недельный отчёт (FEATURE-08).
7. **Admin UI** (Next.js 15, FEATURE-09) читает данные через FastAPI REST (`/api/v1/...`), показывает лидов, источники, триггеры, аналитику.

## 3. Границы контекстов

| Контекст | Ответственность | Технология |
|----------|-----------------|------------|
| Ingestion | Приём сообщений из Telegram, запись ledger, публикация в очередь | Telethon, Postgres, Redis |
| Filtering | Keyword-фильтр и отсев шума | Celery worker, Postgres |
| Classification | LLM-анализ и извлечение структурированных данных | Celery worker, Claude/GPT-4 |
| Scoring | Расчёт итогового скора и категории лида | Celery worker |
| Enrichment | Обогащение профиля автора | Celery worker, Telethon |
| Notification | Уведомления Максиму (push, дайджест, отчёт) | Aiogram bot |
| Admin API | CRUD источников/триггеров, чтение лидов, аналитика | FastAPI |
| Admin UI | Web-интерфейс | Next.js 15 + shadcn/ui |
| Platform | Миграции, секреты, деплой, мониторинг | GitHub Actions, Docker Compose, Nginx, Sentry |

Контексты общаются только через: (а) Redis-очередь, (б) Postgres-таблицы (read-only cross-context), (в) FastAPI HTTP. Прямые импорты между bounded contexts запрещены.

## 4. Таблицы БД (полный список)

Все DDL — в ТЗ разд. 3, соответствующий FEATURE.

| Таблица | Роль | Источник в ТЗ |
|---------|------|---------------|
| `telegram_sources` | Реестр чатов/каналов для мониторинга с приоритетом и статистикой | FEATURE-02 |
| `raw_messages` | Ledger всех принятых сообщений с `processing_status`; источник истины до попадания в очередь | FEATURE-03 |
| `keyword_triggers` | Справочник ключевых слов с весами и типом (direct_request / pain_signal / lifecycle_event / negative) | FEATURE-04 |
| `lead_analysis` | Результат LLM-классификации с reasoning, стоимостью, `prompt_version` | FEATURE-05 |
| `sender_profiles` | Обогащённый профиль автора (bio, LinkedIn, company, stage) | FEATURE-07 |

Дополнительные служебные таблицы (не в ТЗ, но необходимы для эксплуатации): `lead_scores` (история скоринга и весов), `lead_pipeline` (статусы воронки new→won/lost из FEATURE-09), `audit_log` (аудит действий админов, требование разд. 4.1), `prompt_versions` (каталог версий промптов, см. `prompts-versioning.md`). Точный DDL для служебных таблиц — предмет отдельного ADR при реализации соответствующих фич.

## 5. Внешние границы

- **Telegram MTProto** — через Telethon user-session. Риски: бан, FloodWait. Митигация — см. ADR-0003, runbook `telethon-ban.md`, FEATURE-10.
- **Anthropic API / OpenAI API** — через HTTPS. Контроль стоимости — см. ADR-0004, runbook `llm-cost-spike.md`.
- **Admin UI ↔ Admin API** — Next.js на Vercel, FastAPI на VPS (см. ADR-0005). CORS и bearerAuth обязательны.
- **Notifications** — Aiogram bot (отдельный бот-токен, не тот же user-session).

## 6. Нефункциональные ограничения

Берутся из ТЗ разд. 4: uptime 99%/30 дней, RTO 2ч, RPO 1ч, p95 admin-API < 300 мс, 10 000 сообщений/день без деградации, ежедневные бэкапы с retention 30 дней (процедура — `runbook/db-restore.md`).

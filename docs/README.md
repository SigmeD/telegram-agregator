# Документация Telegram Lead Aggregator

Оглавление SDLC-документации проекта. Исходное ТЗ — [`../TZ_Telegram_Lead_Aggregator.md`](../TZ_Telegram_Lead_Aggregator.md).

## Архитектура

- [`architecture.md`](./architecture.md) — высокоуровневая архитектура модуля, поток данных, границы контекстов, полный список таблиц БД.
- [`api/openapi.yaml`](./api/openapi.yaml) — OpenAPI 3.1 спецификация Admin API (скелет, `health` + placeholder endpoints для leads/sources/triggers).
- [`security.md`](./security.md) — модель угроз: критичные активы, актёры, риски, митигации, GDPR.
- [`prompts-versioning.md`](./prompts-versioning.md) — процесс версионирования LLM-промптов (`prompts/vN/`, validation, shadow-режим, promote/rollback).

## Architecture Decision Records

Формат Michael Nygard. Шаблон — [`adr/TEMPLATE.md`](./adr/TEMPLATE.md).

- [`adr/0001-record-architecture-decisions.md`](./adr/0001-record-architecture-decisions.md) — используем ADR для значимых решений.
- [`adr/0002-monorepo-layout.md`](./adr/0002-monorepo-layout.md) — монорепо `backend/`, `frontend/`, `infra/`, `docs/`.
- [`adr/0003-telethon-user-session-not-bot-api.md`](./adr/0003-telethon-user-session-not-bot-api.md) — почему user-session, а не Bot API.
- [`adr/0004-claude-primary-gpt4-fallback.md`](./adr/0004-claude-primary-gpt4-fallback.md) — Claude Haiku основной, GPT-4 fallback, бюджетный cap.
- [`adr/0005-vercel-frontend-vps-backend.md`](./adr/0005-vercel-frontend-vps-backend.md) — frontend на Vercel, backend на VPS.
- [`adr/0006-celery-queue-postgres-ledger.md`](./adr/0006-celery-queue-postgres-ledger.md) — Redis-очередь, Postgres как источник истины.

## Процессы

- [`dor.md`](./dor.md) — Definition of Ready: когда задача готова попасть в спринт.
- [`dod.md`](./dod.md) — Definition of Done: когда задачу можно считать завершённой.

## Эксплуатация (runbook)

Actionable-процедуры для инцидентов. Подробнее — [`runbook/README.md`](./runbook/README.md).

- [`runbook/telethon-ban.md`](./runbook/telethon-ban.md) — Telegram-аккаунт заблокирован, FloodWait, восстановление session.
- [`runbook/redis-down.md`](./runbook/redis-down.md) — Redis недоступен, re-enqueue из Postgres ledger.
- [`runbook/llm-cost-spike.md`](./runbook/llm-cost-spike.md) — всплеск расходов на LLM, отключение fallback, смена `PROMPT_VERSION`.
- [`runbook/db-restore.md`](./runbook/db-restore.md) — восстановление Postgres из бэкапа, чек-лист валидации.

## Ретроспективы

Шаблон — [`retro/TEMPLATE.md`](./retro/TEMPLATE.md).

- [`retro/sprint-00-kickoff.md`](./retro/sprint-00-kickoff.md) — установочная сессия: стек, SDLC, правила работы, action items.

## Навигация по ТЗ и документации

| Область | Где искать |
|---------|------------|
| Бизнес-требования | ТЗ разд. 1 |
| Стек | ТЗ разд. 2.2, ADR-0002, ADR-0005 |
| Данные (DDL) | ТЗ разд. 3 (в каждом FEATURE), [`architecture.md`](./architecture.md) §4 |
| FEATURE-XX приёмка | ТЗ разд. 3 |
| Нефункциональные требования | ТЗ разд. 4 |
| Roadmap | ТЗ разд. 5 |
| Out of scope | ТЗ разд. 7 |
| Риски | ТЗ разд. 8, [`security.md`](./security.md) |
| Инциденты | [`runbook/`](./runbook/) |

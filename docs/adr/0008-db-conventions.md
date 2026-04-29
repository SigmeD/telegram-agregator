# ADR-0008: Database conventions (initial schema)

**Status:** Accepted
**Date:** 2026-04-24
**Deciders:** Максим, Claude

## Context

Первая миграция (`0001_initial`) вводит 5 таблиц из ТЗ: `telegram_sources`, `raw_messages`, `keyword_triggers`, `lead_analysis`, `sender_profiles`. Ряд низкоуровневых решений (timestamps, constrained-строки, поведение FK при удалении, генерация UUID) в ТЗ не зафиксирован явно — их нужно записать, чтобы в Sprint 2+ их не переоткрывали заново.

## Decision

1. **Timestamps всегда `TIMESTAMPTZ`** (`DateTime(timezone=True)` в SQLAlchemy). Хранится как UTC, клиенты сами конвертируют в нужную TZ. Telegram API отдаёт UTC, naive timestamps тихо дрейфуют при смене TZ сервера.
2. **UUID primary keys через `gen_random_uuid()`** (встроено в PG 13+). Серверная генерация — чтобы raw SQL inserts не требовали Python-side UUID.
3. **Constrained-строки: `VARCHAR(N)` + именованный CHECK**, не `CREATE TYPE ... AS ENUM`. Причина: `ALTER TYPE ADD VALUE` нельзя выполнить внутри транзакции, а удалять значения вообще нельзя; наши constrained domains (`vertical`, `lead_type`, `enrichment_status`) будут расти. `ALTER TABLE DROP/ADD CONSTRAINT` полностью транзакционен и симметричен.
4. **FK `ON DELETE RESTRICT` везде.** Лог raw_messages — это training data, мы не каскадно удаляем его только потому, что источник отключили. Для "убрать" источник — `is_active=false`.
5. **Alembic naming convention** задаётся на `Base.metadata` (см. `shared.db.session.NAMING_CONVENTION`). Имена констрейнтов/индексов становятся детерминированными — autogenerate перестаёт шуметь ре-нэймами.
6. **Отклонения от ТЗ** записаны в спеке (`docs/superpowers/specs/2026-04-24-db-foundation-design.md`, раздел "Deliberate deviations from ТЗ"): `priority BETWEEN 1 AND 10`, `confidence IN [0, 1]`, `UNIQUE(keyword, language)` для триггеров, полный enum (5 значений) для `enrichment_status` вместо только `'pending'`.

## Alternatives considered

- **Postgres ENUM типы** — отклонено по причинам `ALTER TYPE` (см. Decision 3).
- **Soft-delete (`deleted_at`) на источниках вместо `is_active`** — отложено; `is_active` дешевле в запросах и совпадает с терминологией ТЗ. `deleted_at` можно добавить позже без ломающих изменений.
- **Серверные таймстампы через `CURRENT_TIMESTAMP`** — функционально эквивалентно `func.now()` в SQLAlchemy; последнее идиоматично и совпадает с тем, что эмитит autogenerate, так что diff-шум минимален.

## Consequences

**Плюсы:**
- Имя констрейнта/индекса — это теперь часть контракта, менять через миграцию.
- Любое новое constrained-строковое поле обязано ехать с CHECK в той же миграции.
- Тесты знают ровно какие имена CHECK'ов/UNIQUE'ов искать при проверке поведения.

**Минусы / что учитывать:**
- Каждая будущая миграция должна явно решать — всё ещё ли `RESTRICT` уместен, или нужен каскад (например, для archive-таблицы). Если каскад — объяснение идёт в миграции.
- Значения constrained-строк меняются только через миграцию (DROP+ADD CHECK), не в коде.

## References

- Спек: `docs/superpowers/specs/2026-04-24-db-foundation-design.md`
- План реализации: `docs/superpowers/plans/2026-04-24-db-foundation-plan.md`
- Миграция: `backend/migrations/versions/0001_initial.py`
- Модели: `backend/src/shared/db/tables/`
- ТЗ: `TZ_Telegram_Lead_Aggregator.md` (FEATURE-02, 03, 04, 05, 07)
- Бизнес-правила: `BUSINESS_RULES.md` (BR-014 — audit триггеров, отложено)

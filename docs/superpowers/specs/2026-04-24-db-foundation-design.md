# Design: DB Foundation — SQLAlchemy models + migration 0001_initial

**Date:** 2026-04-24
**Owner:** Максим Ерохин
**Status:** Approved (брейншторм), готов к плану
**Unblocks:** FEATURE-02, FEATURE-03, FEATURE-04, FEATURE-05, FEATURE-07

## Goal

Положить фундамент хранилища: 5 SQLAlchemy ORM-моделей ровно по схемам ТЗ, единая миграция `0001_initial`, интеграционные тесты против реального Postgres. После этого Sprint 1 features (Telethon listener, sources CRUD, keyword filter) перестают быть заблокированы отсутствием таблиц.

Вне scope: seed-данные, audit-таблицы, LLM-run-трейс, `users`. Они уйдут отдельными миграциями по мере необходимости (см. раздел "Out of scope").

## Scope — таблицы

Ровно 5 таблиц, поля **литерально из ТЗ** без ренейминга:

| Таблица | Файл ORM | FK |
|---|---|---|
| `telegram_sources` | `backend/src/shared/db/tables/telegram_source.py` | — |
| `raw_messages` | `backend/src/shared/db/tables/raw_message.py` | `source_id → telegram_sources(id)` RESTRICT |
| `keyword_triggers` | `backend/src/shared/db/tables/keyword_trigger.py` | — |
| `lead_analysis` | `backend/src/shared/db/tables/lead_analysis.py` | `raw_message_id → raw_messages(id)` RESTRICT |
| `sender_profiles` | `backend/src/shared/db/tables/sender_profile.py` | — (link by `telegram_user_id`) |

### `telegram_sources` (FEATURE-02)
```
id                        UUID PK default gen_random_uuid()
chat_id                   BIGINT NOT NULL UNIQUE
title                     VARCHAR(500) NOT NULL
username                  VARCHAR(100) NULL
source_type               VARCHAR(50) NOT NULL  CHECK IN ('channel','group','supergroup')
category                  VARCHAR(100) NULL
priority                  INT NOT NULL DEFAULT 5  CHECK BETWEEN 1 AND 10
is_active                 BOOLEAN NOT NULL DEFAULT true
added_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
last_message_at           TIMESTAMPTZ NULL
total_messages_processed  INT NOT NULL DEFAULT 0
relevant_leads_count      INT NOT NULL DEFAULT 0
```

### `raw_messages` (FEATURE-03)
```
id                    UUID PK default gen_random_uuid()
source_id             UUID NOT NULL REFERENCES telegram_sources(id) ON DELETE RESTRICT
telegram_message_id   BIGINT NOT NULL
sender_id             BIGINT NULL
sender_username       VARCHAR(100) NULL
sender_name           VARCHAR(500) NULL
message_text          TEXT NULL
has_media             BOOLEAN NOT NULL DEFAULT false
media_type            VARCHAR(50) NULL
reply_to_message_id   BIGINT NULL
thread_id             BIGINT NULL
sent_at               TIMESTAMPTZ NOT NULL
received_at           TIMESTAMPTZ NOT NULL DEFAULT now()
processing_status     VARCHAR(50) NOT NULL DEFAULT 'pending'
                         CHECK IN ('pending','filtered_out','analyzing','lead','not_lead','error')

UNIQUE (source_id, telegram_message_id)
INDEX  ix_raw_messages_processing_status
INDEX  ix_raw_messages_sent_at_desc           -- (sent_at DESC)
INDEX  ix_raw_messages_source_id_sent_at_desc -- (source_id, sent_at DESC)
```

### `keyword_triggers` (FEATURE-04)
```
id            UUID PK default gen_random_uuid()
keyword       VARCHAR(200) NOT NULL
trigger_type  VARCHAR(50) NOT NULL
                 CHECK IN ('direct_request','pain_signal','lifecycle_event','negative')
weight        INT NOT NULL DEFAULT 1
is_active     BOOLEAN NOT NULL DEFAULT true
language      VARCHAR(10) NOT NULL DEFAULT 'ru'

UNIQUE (keyword, language)
INDEX  ix_keyword_triggers_active_type -- (is_active, trigger_type) WHERE is_active = true
```

### `lead_analysis` (FEATURE-05)
```
id                      UUID PK default gen_random_uuid()
raw_message_id          UUID NOT NULL REFERENCES raw_messages(id) ON DELETE RESTRICT
is_lead                 BOOLEAN NOT NULL
confidence              NUMERIC(3,2) NULL     CHECK BETWEEN 0 AND 1
lead_type               VARCHAR(50) NULL
                           CHECK IN ('direct_request','pain_signal','lifecycle_event','not_a_lead')
stage                   VARCHAR(50) NULL
                           CHECK IN ('idea','pre_mvp','mvp','growth','unknown')
urgency                 VARCHAR(20) NULL   CHECK IN ('high','medium','low')
budget_signals          VARCHAR(20) NULL   CHECK IN ('mentioned','implied','none')
vertical                VARCHAR(50) NULL
                           CHECK IN ('fintech','saas','marketplace','edtech','other','unknown')
extracted_needs         TEXT NULL
recommended_action      VARCHAR(50) NULL
                           CHECK IN ('contact_now','contact_soon','monitor','ignore')
recommended_approach    TEXT NULL
red_flags               JSONB NOT NULL DEFAULT '[]'::jsonb
reasoning               TEXT NULL
llm_model               VARCHAR(100) NULL
tokens_used             INT NULL
cost_usd                NUMERIC(10,6) NULL
analyzed_at             TIMESTAMPTZ NOT NULL DEFAULT now()

INDEX ix_lead_analysis_raw_message_id                            -- FK join
INDEX ix_lead_analysis_is_lead_true (analyzed_at DESC) WHERE is_lead = true -- partial
```

### `sender_profiles` (FEATURE-07)
```
id                    UUID PK default gen_random_uuid()
telegram_user_id      BIGINT NOT NULL UNIQUE
username              VARCHAR(100) NULL
full_name             VARCHAR(500) NULL
bio                   TEXT NULL
phone                 VARCHAR(50) NULL
linkedin_url          VARCHAR(500) NULL
website_url           VARCHAR(500) NULL
twitter_url           VARCHAR(500) NULL
is_founder_profile    BOOLEAN NOT NULL DEFAULT false
company_name          VARCHAR(500) NULL
company_stage         VARCHAR(50) NULL
enriched_at           TIMESTAMPTZ NULL
enrichment_status     VARCHAR(50) NOT NULL DEFAULT 'pending'
                         CHECK IN ('pending','in_progress','done','failed','skipped')
```

> Примечание по `enrichment_status`: ТЗ явно указывает только `'pending'`. Пять значений выше — минимальный набор для реализации FEATURE-07 (`in_progress`/`done`/`failed`/`skipped`). Зафиксируем тут и отразим в ADR-0008.

## Conventions (единые для всех 5 таблиц)

| Решение | Как реализовано |
|---|---|
| **Timestamps** | `DateTime(timezone=True)` (→ PG `TIMESTAMPTZ`). Дефолт `server_default=func.now()` |
| **UUID PK** | `UUID(as_uuid=True)`, `server_default=func.gen_random_uuid()` |
| **Constrained strings** | `VARCHAR(N)` + именованный `CheckConstraint("col IN (...)", name="ck_<table>_<col>")` |
| **FK on delete** | `ON DELETE RESTRICT` для всех FK |
| **Naming convention** | `MetaData(naming_convention=…)` в `Base`: `ix_%(column_0_label)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `pk_%(table_name)s` |
| **Explicit nullability** | Каждое поле указывает `nullable=False/True` явно, не полагаемся на дефолт SQLAlchemy |
| **JSONB** | `postgresql.JSONB`, `server_default=text("'[]'::jsonb")` где применимо |
| **Decimal** | `Numeric(3, 2)` / `Numeric(10, 6)` по ТЗ |

## Files

### Modified
- `backend/src/shared/db/session.py` — добавить `MetaData(naming_convention=…)` в `Base` (сейчас `DeclarativeBase` без кастомной metadata)
- `backend/src/shared/db/models.py` — заменить stub на `from .tables import *` (re-export для Alembic autogenerate)

### Created — ORM
- `backend/src/shared/db/tables/__init__.py` — `__all__` со всеми 5 моделями
- `backend/src/shared/db/tables/telegram_source.py`
- `backend/src/shared/db/tables/raw_message.py`
- `backend/src/shared/db/tables/keyword_trigger.py`
- `backend/src/shared/db/tables/lead_analysis.py`
- `backend/src/shared/db/tables/sender_profile.py`

### Created — миграция
- `backend/migrations/versions/0001_initial.py` — autogenerate + ручная правка на CHECK-констрейнты и partial-индексы (они не эмитятся автогенератором)

### Created — тесты
- `backend/tests/unit/test_models_metadata.py`
- `backend/tests/integration/test_migration_0001.py`
- `backend/tests/integration/conftest.py` — фикстура `apply_migrations` + URL БД из `TEST_DATABASE_URL`

### Created — документация
- `docs/adr/0008-db-conventions.md` — фиксация выбранных соглашений (TIMESTAMPTZ / CHECK vs ENUM / FK RESTRICT / UUID gen_random_uuid)

### Modified — документация
- `CHANGELOG.md` — запись в `[Unreleased]` → `Added: initial DB schema (5 tables), migration 0001`
- `CLAUDE.md` — обновить секцию "Не сделано" (снять две галочки, добавить seeds как следующую задачу)

## Test strategy

### Unit (`tests/unit/`, без БД)
- `test_models_metadata.py`:
  - Импорт `shared.db.models` не падает
  - `Base.metadata.tables` содержит ровно `{telegram_sources, raw_messages, keyword_triggers, lead_analysis, sender_profiles}`
  - Имена PK/FK/CHECK/UQ соответствуют `naming_convention` (регрессионный страж для автогенератора миграций)

### Integration (`tests/integration/`, реальный Postgres 15)
Фикстура `apply_migrations` (session-scope):
1. До тестов — `alembic upgrade head` на `TEST_DATABASE_URL`
2. После — `alembic downgrade base`

Тесты (минимум один ассерт на каждый механизм):

| Тест | Что проверяет |
|---|---|
| `test_migration_creates_all_tables` | `information_schema.tables` содержит 5 ожидаемых имён |
| `test_migration_creates_all_indexes` | `pg_indexes` содержит все индексы по списку выше |
| `test_check_source_type_valid_and_invalid` | `INSERT` с `source_type='channel'` ok, с `'banana'` → `IntegrityError` |
| `test_check_processing_status` | То же для `raw_messages.processing_status` |
| `test_check_all_lead_analysis_enums` | Параметризованный: все 7 CHECK-столбцов lead_analysis |
| `test_fk_restrict_prevents_source_delete` | При наличии raw_message `DELETE` source → `IntegrityError` |
| `test_unique_source_chat_id` | Повторный chat_id в sources → `IntegrityError` |
| `test_unique_source_telegram_message_id` | Повторный `(source_id, telegram_message_id)` → `IntegrityError` |
| `test_unique_sender_profiles_telegram_user_id` | Повторный telegram_user_id → `IntegrityError` |
| `test_jsonb_red_flags_roundtrip` | Сохраняем `["spam", "recruiter"]`, читаем обратно как Python list |
| `test_timestamptz_stored_as_utc` | Вставляем naive datetime `now()` in `Asia/Yekaterinburg`, читаем — получаем UTC с tz-info |
| `test_priority_check_bounds` | priority=0 и priority=11 → `IntegrityError`, 1 и 10 — ok |
| `test_confidence_check_bounds` | confidence=-0.1, 1.1 → `IntegrityError`, 0.0/1.0/0.75 — ok |
| `test_downgrade_base_drops_all_tables` | После downgrade таблиц в schema нет |

### Запуск локально
```bash
docker compose up -d postgres
export TEST_DATABASE_URL="postgresql+asyncpg://aggregator:aggregator@localhost:5432/aggregator_test"
createdb aggregator_test  # или через docker exec
pytest backend/tests/integration/
```

### CI
GitHub Actions уже имеет `ci-backend.yml`. В рамках **этой** задачи только проверю что workflow поднимает PG-сервис и корректно ставит `TEST_DATABASE_URL` в env job'а. Если нет — заведу отдельный issue в `docs/retro/`, не патчим CI из PR моделей (иначе PR разъезжается).

## Deliberate deviations from ТЗ (fixed here, logged in ADR-0008)

Все совместимы с требованиями ТЗ и не меняют семантику — только докручивают интегрити.

| Место | Что в ТЗ | Что делаем | Причина |
|---|---|---|---|
| `telegram_sources.priority` | `INT DEFAULT 5, -- 1-10` (только в комментарии) | `CHECK priority BETWEEN 1 AND 10` | Контракт из комментария становится инвариантом |
| `lead_analysis.confidence` | `DECIMAL(3,2)` | То же + `CHECK confidence BETWEEN 0 AND 1` | Подсказано форматом промпта (`0.0-1.0`) |
| `keyword_triggers` | без UNIQUE | `UNIQUE (keyword, language)` | Дубли триггеров — баг; уникальность защищает seed-скрипт от двойного запуска |
| `sender_profiles.enrichment_status` | упомянуто только `'pending'` | `CHECK IN ('pending','in_progress','done','failed','skipped')` | Минимальный набор для реализации FEATURE-07; список фиксируется в ADR-0008 |
| Имена констрейнтов / индексов | не заданы | `MetaData(naming_convention=…)` — единый шаблон | Стабильные имена → детерминированный autogenerate |

## Risks / mitigations

| Риск | Mitigation |
|---|---|
| Autogenerate не создаёт partial-индексы (WHERE) | Добавляем руками в `0001_initial.py` через `op.execute("CREATE INDEX ... WHERE ...")` + мануальный `op.drop_index` в downgrade |
| `gen_random_uuid()` требует расширения | В PG 13+ встроено. Наш образ `postgres:15`. Убеждаемся в миграции `CREATE EXTENSION IF NOT EXISTS pgcrypto` в downgrade-safe месте (на всякий — хоть с 13 оно в core) |
| `compare_server_default=True` в alembic ломает миграции на `now()` vs `CURRENT_TIMESTAMP` | Зашиваем `server_default=func.now()` — alembic их сравнит одинаково |
| При merge в develop в параллели кто-то заведёт свою `0001_` | Договариваемся что эта миграция первая; ревью PR должно сверить номер |

## Definition of Done

- [ ] 5 ORM-моделей написаны, `make lint` зелёный (ruff/black/mypy)
- [ ] `backend/migrations/versions/0001_initial.py` применяется на пустой БД без ошибок
- [ ] `alembic downgrade base` → `upgrade head` делает round-trip (idempotent)
- [ ] Unit-тест `test_models_metadata` зелёный
- [ ] Все 14 интеграционных тестов зелёные на Postgres 15
- [ ] ADR-0008 записан и закоммичен
- [ ] CHANGELOG обновлён
- [ ] CLAUDE.md обновлён (секция "Не сделано" + "Сделано")
- [ ] Code review по `superpowers:requesting-code-review`
- [ ] Verification gate: прогнал `pytest` локально, вижу `X passed` в stdout

## Out of scope (явно)

- Seed-данные (30+ источников, словарь триггеров) — отдельная задача / PR после мерджа этого
- Audit-лог изменений триггеров (BR-014) — Sprint 2
- `llm_runs` детальный трейс — при реализации FEATURE-05
- Partitioning `raw_messages` — overengineering до 10M строк
- `users`/`admin_users` — Максим единственный юзер на MVP
- CI-workflow правки (если не готов — отдельный issue, не этот PR)
- Dependabot PR #12 (Next.js 16 major) — независимая задача

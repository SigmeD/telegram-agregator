# Telegram Lead Aggregator — Backend

Python-бэкенд монорепо Telegram Lead Aggregator. См. корневой `TZ_Telegram_Lead_Aggregator.md`
и `Makefile` проекта.

## Состав

Бэкенд состоит из **четырёх независимо деплоящихся сервисов**, которые делят общий пакет
`shared/` (конфиг, БД, LLM-клиент, метрики, логгер):

| Сервис     | Пакет              | Назначение                                                             |
|------------|--------------------|------------------------------------------------------------------------|
| `listener` | `src/listener`     | Telethon user-session: читает чаты, пишет в `raw_messages` и Redis.    |
| `worker`   | `src/worker`       | Celery: keyword-фильтр, LLM-классификация, обогащение профилей.        |
| `api`      | `src/api`          | FastAPI: REST для админки (лиды, источники, триггеры).                 |
| `bot`      | `src/bot`          | Aiogram 3: уведомления Максиму о горячих лидах, дайджесты.             |

Вспомогательные артефакты:

- `migrations/` — Alembic (async, SQLAlchemy 2.x).
- `prompts/v<N>/` — версионируемые промпты для LLM (см. `prompts/registry.py`).
- `seeds/` — YAML-сиды источников и триггеров (FEATURE-02, FEATURE-04).
- `tests/` — unit + integration (testcontainers pg/redis).

## Запуск через `uv`

Зависимости ставим через [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
```

Сервисы запускаются отдельными процессами:

```bash
# 1. Telethon listener
uv run python -m listener

# 2. Celery worker
uv run celery -A worker.celery_app.app worker --loglevel=INFO

# 3. FastAPI (uvicorn с reload в dev)
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Aiogram notification bot
uv run python -m bot
```

Миграции:

```bash
uv run alembic -c migrations/alembic.ini upgrade head
uv run alembic -c migrations/alembic.ini revision --autogenerate -m "..."
```

Тесты и линтеры:

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
```

## Переменные окружения

Все настройки читаются `shared.config.Settings` (pydantic-settings). Обязательные:
`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, `TELETHON_SESSION_KEY`,
`DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `NOTIFY_BOT_TOKEN`,
`NOTIFY_BOT_ADMIN_CHAT_ID`, `JWT_SECRET`.

Шаблон см. в корневом `.env.example` (формируется отдельно).

## Оркестрация

Полный цикл (БД, Redis, все 4 сервиса) поднимается из корня репо через `make dev` — см.
корневой `Makefile`.

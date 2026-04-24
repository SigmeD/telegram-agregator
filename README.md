# Telegram Lead Aggregator

AI-система мониторинга открытых Telegram-чатов/каналов стартап-сообществ СНГ для поиска основателей, которым нужна команда разработки MVP. Этап 1 большой системы лидогенерации.

> **Статус:** pre-alpha — скаффолд завершён, Sprint 1 не начат.  
> **Заказчик:** Максим Ерохин.  
> **Первоисточник требований:** [`TZ_Telegram_Lead_Aggregator.md`](./TZ_Telegram_Lead_Aggregator.md).

## Что внутри

| Директория | Что |
|---|---|
| `backend/` | Python 3.11+: Telethon listener, Celery worker, FastAPI API, Aiogram notify bot (один Docker-образ) |
| `frontend/` | Next.js 15 админ-панель (деплой на Vercel) |
| `infra/` | Dockerfile'ы, docker-compose для локалки/dev/prod, nginx, deploy-скрипты |
| `docs/` | Архитектура, ADR, runbook'и, API spec, SDLC-процессы |
| `.github/` | CI/CD workflow'ы (GitHub Actions) |
| `BUSINESS_RULES.md` | Продуктовые инварианты, извлечённые из ТЗ |
| `CLAUDE.md` | Живой бриф для Claude Code — всегда синхронизировать со стеком/структурой |

## Быстрый старт (локально)

Требования: Docker Desktop, pnpm 9+, uv (Python 0.4+), Make.

```bash
cp .env.example .env          # заполнить реальными значениями (см. раздел «Secrets»)
make up                       # поднимает postgres, redis, backend-сервисы, frontend
make migrate                  # alembic upgrade head
make seed                     # загрузить источники и keyword-триггеры
make logs svc=api             # логи FastAPI
```

Frontend: http://localhost:3000  · API: http://localhost:8000  · Метрики: http://localhost:8000/metrics

Детали: [`backend/README.md`](./backend/README.md), [`frontend/README.md`](./frontend/README.md), [`infra/README.md`](./infra/README.md).

## Среды

| Среда | Frontend | Backend | Триггер |
|---|---|---|---|
| local | `pnpm dev` | Docker Compose | вручную |
| dev | Vercel preview/develop branch | VPS dev (SSH auto-deploy) | push в `develop` |
| prod | Vercel production | VPS prod | **только** `workflow_dispatch` после подтверждения |

## Жёсткие правила

- Любые правки `.env`/secrets — только с явного разрешения Максима.
- Prod deploy — только по явной команде Максима.
- После каждого релиза — обновление документации (CHANGELOG обязательно).
- Архитектурные решения — через ADR в [`docs/adr/`](./docs/adr/).

## Contributing

См. [`CONTRIBUTING.md`](./CONTRIBUTING.md) и [`docs/dod.md`](./docs/dod.md).

## Security

См. [`SECURITY.md`](./SECURITY.md) и [`docs/security.md`](./docs/security.md). Секреты никогда не коммитим — gitleaks в pre-commit и CI.

## License

[MIT](./LICENSE)

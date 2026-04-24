# ADR-0002: Монорепозиторий с разделением backend/frontend/infra/docs

- **Статус:** Accepted
- **Дата:** 2026-04-24
- **Авторы:** команда Telegram Lead Aggregator

## Контекст

Проект состоит из Python-сервисов (Telethon listener, Celery workers, FastAPI, Aiogram bot), Next.js 15 админки, инфраструктурного кода (Docker Compose, Nginx, GitHub Actions) и документации. Команда — 2 разработчика, один PM. Сроки — 6 недель до релиза MVP (ТЗ разд. 5).

Связность контекстов высокая: контракт FastAPI напрямую влияет на frontend, миграции БД влияют на все backend-воркеры, CI должен уметь прогонять разнородные тесты в одном pipeline.

## Решение

Мы используем монорепо со следующим корневым layout:

```
/
├── backend/     # Python: telethon/, workers/, api/, bot/, common/, tests/
├── frontend/    # Next.js 15 + shadcn/ui
├── infra/       # docker-compose.*.yml, nginx/, terraform/ (если появится)
├── docs/        # архитектура, ADR, runbook, retro, API, security
├── prompts/     # версионированные LLM-промпты (v1/, v2/, ...)
└── .github/     # workflows для CI/CD
```

Каждая папка верхнего уровня имеет собственный владелец в `CODEOWNERS`. Shared-код (типы, модели данных) не дублируется между backend и frontend — вместо этого frontend потребляет OpenAPI-спеку из `docs/api/openapi.yaml` и генерирует TS-клиент в CI.

## Рассмотренные альтернативы

- **Poly-repo (отдельные репо под backend, frontend, infra).** Отвергнуто: накладные расходы на синхронизацию версий API между репо, 3x CI-пайплайнов, сложнее атомарные изменения, затрудняет работу двух разработчиков.
- **Монорепо с Nx/Turborepo.** Отвергнуто как преждевременная оптимизация: масштаб проекта не оправдывает сложность инструментария.

## Последствия

- **Позитивные.** Атомарные PR через несколько слоёв; единый CI; общий changelog.
- **Негативные.** CI должен уметь детектить, что именно изменилось, чтобы не прогонять все тесты на каждый PR (path filters в GitHub Actions).
- **Нейтральные.** Секреты разделяются по префиксам (`BACKEND_*`, `FRONTEND_*`) в GitHub Environments.

## Ссылки

- ТЗ разд. 2.2 (стек)
- ADR-0005 (где хостится frontend vs backend)

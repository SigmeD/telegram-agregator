# CLAUDE.md — бриф проекта для Claude Code

> Живой документ. Обновлять при любом изменении стека, структуры, SDLC-процесса или ключевых конвенций. После каждого релиза проверить синхронизацию с реальностью.

## О проекте

**Telegram Lead Aggregator** — первый этап AI-системы лидогенерации для команды разработки MVP. Автоматизирует поиск основателей стартапов в открытых Telegram-чатах/каналах СНГ через user-session Telethon + LLM-классификацию. Заказчик и основной пользователь — Максим Ерохин.

Первоисточник требований: [`TZ_Telegram_Lead_Aggregator.md`](./TZ_Telegram_Lead_Aggregator.md) (v1.0, апрель 2026).

## Архитектура (high-level)

```
[Telethon Listener] → [Redis queue] → [Celery worker: keyword → LLM → scoring] → [PostgreSQL]
                                                                     ↓
                                                      [Aiogram notify bot] + [Next.js admin UI]
```

- **User-session Telethon**, не Bot API (чтобы читать чаты без добавления бота).
- Два уровня фильтрации: дешёвый keyword, дорогой LLM.
- Raw-сообщения сохраняются всегда (soft-delete-friendly для переобучения).
- Hot лид доходит до Максима за < 60 сек end-to-end.

Детали: [`docs/architecture.md`](./docs/architecture.md), ADR в [`docs/adr/`](./docs/adr/).

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.11+, Telethon 1.34+, FastAPI, Celery, Aiogram 3.x, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 15+, Redis 7 |
| LLM | Anthropic Claude Haiku (основной), OpenAI GPT-4 (fallback) |
| Frontend | Next.js 15 (App Router), React 19, TypeScript strict, Tailwind 4, shadcn/ui, TanStack Table/Query |
| Infra | Docker Compose, Nginx, VPS (Hetzner/Timeweb), Vercel (frontend only) |
| CI/CD | GitHub Actions |
| Observability | structlog, Prometheus, Sentry |

## Структура монорепо

```
.
├── backend/              # Python: listener, worker, api, bot (один образ)
│   ├── src/{shared,listener,worker,api,bot}/
│   ├── migrations/       # Alembic
│   ├── prompts/vN/       # версионируемые LLM-промпты
│   ├── seeds/            # стартовые источники и триггеры
│   └── tests/{unit,integration}/
├── frontend/             # Next.js админка (Vercel Root Directory)
│   └── src/{app,components,features,lib}/
├── infra/
│   ├── docker/           # Dockerfile'ы
│   ├── compose/          # docker-compose базовый + dev/prod override
│   ├── nginx/
│   └── scripts/          # deploy.sh, rotate-session.sh, backup-db.sh
├── docs/
│   ├── adr/              # архитектурные решения
│   ├── runbook/          # операционные процедуры
│   ├── retro/            # спринт-ретроспективы
│   ├── api/openapi.yaml
│   ├── architecture.md, dod.md, dor.md, security.md, prompts-versioning.md
│   └── business_rules.md → симлинк/ссылка на BUSINESS_RULES.md
├── .github/workflows/    # 7 workflow'ов (CI backend/frontend/docs/security + CD dev/prod + release)
├── BUSINESS_RULES.md     # извлечённые из ТЗ бизнес-правила (инварианты)
├── CHANGELOG.md          # Keep a Changelog
├── README.md, CONTRIBUTING.md, SECURITY.md, LICENSE
├── Makefile, .pre-commit-config.yaml, .editorconfig
├── .env.example
└── TZ_Telegram_Lead_Aggregator.md
```

## Development workflow (SDLC)

1. **Планирование фичи** → привязка к FEATURE-XX из ТЗ, формирование acceptance criteria.
2. **Ветка** `feature/FEATURE-XX-short-name` от `develop`.
3. **Реализация** → тесты → обновить CHANGELOG → при необходимости ADR → прогон `make lint test`.
4. **PR в `develop`** — шаблон PR заставляет пройти чеклист DoD.
5. **CI** (обязательный): ci-backend / ci-frontend / ci-docs / security — все зелёные.
6. **Review** → merge в `develop`.
7. **Auto-deploy dev:** `develop` → Vercel preview (frontend) + SSH-deploy backend на dev VPS.
8. **Prod release:** PR `develop → main` → merge → вручную `workflow_dispatch cd-backend-prod` **после явного разрешения Максима** → Vercel promote. Тег `vX.Y.Z` + релиз-ноты.

Подробно: [`docs/dod.md`](./docs/dod.md), [`docs/dor.md`](./docs/dor.md).

## Команды

```bash
# Локальная разработка
make up              # docker compose up -d (pg, redis, все backend-сервисы, frontend)
make down            # остановить
make logs svc=api    # логи сервиса
make migrate         # alembic upgrade head
make test            # backend + frontend тесты
make lint            # ruff+black+mypy, eslint+prettier+tsc
make fmt             # авто-формат
make seed            # загрузить seed-данные (источники, триггеры)
```

Детали инфраструктуры: [`infra/README.md`](./infra/README.md). Backend-специфичные команды: [`backend/README.md`](./backend/README.md).

## Жёсткие правила коллаборации

1. **Никаких изменений в `.env`/secrets** без явного разрешения Максима. `.env.example` — свободно.
2. **Prod deploy только после явной команды** Максима. Dev — автоматом по merge в `develop`.
3. **После каждого релиза обновлять документацию:** CHANGELOG обязательно; README/runbook/ADR/API spec/prompts — по применимости.
4. **CLAUDE.md — живой.** Изменилась структура/стек/процесс → поправить этот файл сразу.
5. **Multiple subagents** для нетривиальных задач — параллелим независимые треки.

## Бизнес-правила

Извлечены из ТЗ и сведены в [`BUSINESS_RULES.md`](./BUSINESS_RULES.md). Там — критерии «что есть лид», формула скоринга, тихие часы, квоты API, этические ограничения. Любое решение, затрагивающее продуктовую логику, — сверять с этим файлом.

## Среды

| Среда | Frontend | Backend | Data | Триггер деплоя |
|---|---|---|---|---|
| local | `pnpm dev` | `docker compose up` | локальные контейнеры | вручную |
| dev | Vercel (branch `develop`) | VPS dev | managed PG + Redis на VPS | auto по push в `develop` |
| prod | Vercel (branch `main`) | VPS prod | managed PG + Redis на VPS | **только** `workflow_dispatch` **после подтверждения** |

## Current state

- [x] ТЗ зафиксировано
- [x] Git init, структура монорепо, скаффолд-файлы (138 файлов, 8075 строк)
- [x] CI/CD workflow'ы описаны (требуют secrets в GitHub — залить после явного разрешения)
- [x] GitHub remote: https://github.com/SigmeD/telegram-agregator (main + develop)
- [x] Superpowers plugin установлен (`claude-plugins-official`)
- [ ] GitHub Secrets залиты (после явного разрешения Максима)
- [x] Environment protection для `production` включён (Required reviewers)
- [ ] Vercel-проект привязан к репо, dev preview работает
- [ ] Dev VPS предоставлен, SSH-ключи залиты в GitHub Secrets
- [ ] Telethon session сгенерирована (вручную на VPS)
- [ ] Миграция `0001_initial.py` применена
- [ ] Sprint 1 начат

Обновлять этот блок после каждого шага.

## Ссылки внутрь

- ТЗ: [`TZ_Telegram_Lead_Aggregator.md`](./TZ_Telegram_Lead_Aggregator.md)
- Бизнес-правила: [`BUSINESS_RULES.md`](./BUSINESS_RULES.md)
- Definition of Done: [`docs/dod.md`](./docs/dod.md)
- Архитектура: [`docs/architecture.md`](./docs/architecture.md)
- Runbook'и: [`docs/runbook/`](./docs/runbook/)
- ADR: [`docs/adr/`](./docs/adr/)
- CHANGELOG: [`CHANGELOG.md`](./CHANGELOG.md)

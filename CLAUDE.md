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
make lint            # ruff check + ruff format --check + mypy, eslint+prettier+tsc
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

Репозиторий: https://github.com/SigmeD/telegram-agregator · Vercel project: `maxeroxinllm-5214s-projects/telegram-agregator` · Latest working preview: `telegram-agregator-fjog3lpr8-maxeroxinllm-5214s-projects.vercel.app`.

**Сделано:**
- [x] ТЗ зафиксировано (`TZ_Telegram_Lead_Aggregator.md`)
- [x] Git init, монорепо (backend/frontend/infra/docs/.github), 138 скаффолд-файлов в initial commit
- [x] 7 GitHub Actions workflows (CI backend/frontend/docs + security + CD dev/prod + release)
- [x] SDLC-артефакты: 7 ADR, 4 runbook, DoD, DoR, architecture, security, prompts-versioning, OpenAPI 3.1, retro-шаблон, sprint-00 kickoff
- [x] BUSINESS_RULES.md — 110 инвариантов из ТЗ (BR-001…BR-110)
- [x] GitHub remote создан, ветки `main` и `develop` синхронизированы
- [x] Environment protection для `production` на GitHub (Required reviewers)
- [x] Vercel: проект создан, слинкован, Git Integration подключена
- [x] Vercel: push в `develop` → auto preview (build 51s Ready); push в `main` заблокирован через `git.deploymentEnabled.main=false` (верифицировано: 0 deploys за 90s после push)
- [x] Vercel dashboard-settings синхронизированы через REST API (`rootDirectory=frontend`, `commandForIgnoringBuildStep=null`)
- [x] pnpm workspace отложен до появления shared-пакетов (ADR-0007); frontend/pnpm-lock.yaml коммичен
- [x] **DB-фундамент:** 5 SQLAlchemy моделей в `backend/src/shared/db/tables/`, миграция `0001_initial`, 35 интеграционных тестов против Postgres 15 (testcontainers), ADR-0008 "Database conventions" (TIMESTAMPTZ, CHECK vs ENUM, FK RESTRICT, UUID `gen_random_uuid()`)
- [x] `migrations/env.py` декуплен от полной `Settings` — читает `DATABASE_URL` из `os.environ`, не требует Telegram/LLM-secrets для запуска миграций
- [x] **Dependabot sweep (17 PR разобраны):** 3 bundled-PR влиты в develop — GHA bumps + `dependabot.yml target-branch: develop` (#20), pip range widenings + **drop black** (переход только на ruff format, устраняет двойное форматирование) (#21), frontend major bumps (jose 5→6, lucide-react 0→1, @hookform/resolvers 3→5) + фикс скаффолд-CI (vitest JSX automatic, eslint dangling extends, upload-artifact@v7 `include-hidden-files`) (#22). Отклонены с обоснованием: Python 3.14, Node 25 non-LTS, Next 16 major. Отложен: testing group (vitest 2→4 + jsdom 25→29 — отдельная задача).

**Не сделано (блокеры для Sprint 1):**
- [ ] GitHub Secrets залиты (после явного разрешения Максима — см. список в `infra/README.md`)
- [ ] Dev VPS предоставлен (Hetzner/Timeweb): host, user, SSH-ключи в GitHub Secrets (`DEV_VPS_HOST`, `DEV_VPS_USER`, `DEV_SSH_KEY`)
- [ ] Telethon session сгенерирована вручную на VPS (требует SMS-код, в CI не автоматизируется)
- [ ] Seed-скрипт: 30+ источников + начальный словарь keyword-триггеров (`make seed` → `backend/src/shared/db/seed.py` + YAML в `backend/seeds/`)
- [ ] Sprint 1: реализация FEATURE-01 (Telegram auth), FEATURE-02 (sources CRUD), FEATURE-03 (Telethon listener), FEATURE-04 (keyword filter)
- [ ] Follow-up: `tests/unit/test_smoke.py::test_module_imports[worker.*]` падает на pre-existing проблеме — `worker/celery_app.py:45` вызывает `create_app()` на module-level, который зовёт `get_settings()` без env vars. Фикс: либо lazy-init Celery-app, либо `tests/conftest.py` с дефолтными env vars.
- [ ] Follow-up: testing group bump (vitest 2→4 + jsdom 25→29) — отдельный PR после миграционного codemod'а vitest v4.

**Открытые вопросы (требуют решения Максима):**
- Prod vs dev VPS — один сервер с разными compose-проектами или два?
- Количество Telegram-аккаунтов в ротации (ТЗ рекомендует 2-3)
- Timezone для тихих часов (сейчас в `.env.example` = `Asia/Yekaterinburg`, проверить)
- Таймер ручной валидации (ТЗ — еженедельно 20 случайных LLM-решений): где будет UI?

Обновлять этот блок после каждого шага.

## Setup на свежей машине

Если работа продолжается на другом компьютере, выполнить по порядку:

### 1. Системные пакеты
```bash
# Linux/macOS
curl -fsSL https://get.pnpm.io/install.sh | sh -   # pnpm
curl -LsSf https://astral.sh/uv/install.sh | sh    # uv (Python)
# Windows (winget)
winget install OpenJS.NodeJS.LTS
winget install pnpm.pnpm
winget install astral-sh.uv
winget install GitHub.cli    # опционально, для gh repo ops
```
Плюс: Docker Desktop (backend локально), Python 3.11+, Git.

### 2. Клон и setup
```bash
git clone https://github.com/SigmeD/telegram-agregator.git
cd telegram-agregator
cp .env.example .env         # реальные значения — только после разрешения Максима
pre-commit install            # pip install pre-commit
cd frontend && pnpm install && cd ..
```

### 3. Claude Code plugins (если Claude Code установлен)
```
/plugin install superpowers@claude-plugins-official
/plugin install vercel@claude-plugins-official
/reload-plugins
```
Оба плагина добавляют skills — проверить через `/plugin` → Installed.

### 4. Vercel CLI и relink
```bash
npm i -g vercel
vercel login                  # интерактивно, OAuth device flow
cd frontend
vercel link --yes --project telegram-agregator
# Получите .vercel/project.json (gitignored) обратно
```

### 5. Локальный запуск (когда будут модели и миграции)
```bash
make up        # docker compose поднимает pg, redis, 4 backend-сервиса, frontend
make migrate   # alembic upgrade head
make seed      # 32 источника + keyword-триггеры
```

### Памятка про state, который НЕ в git

- `.env` — с реальными ключами (локально, не коммитится)
- `frontend/.vercel/` — project IDs от `vercel link` (per-machine, пересоздаётся)
- Backend Telethon session-файл — только на VPS
- GitHub Secrets — настраиваются раз, остаются на GitHub

Memory-правила Claude Code (`.env permission`, `prod deploy permission` и т.д.) живут в локальной памяти конкретной Claude Code-инсталляции, на новой машине их надо либо заново проговорить Claude, либо полагаться на правила из этого файла и `CONTRIBUTING.md`/`SECURITY.md` (они дублированы).

## Ссылки внутрь

- ТЗ: [`TZ_Telegram_Lead_Aggregator.md`](./TZ_Telegram_Lead_Aggregator.md)
- Бизнес-правила: [`BUSINESS_RULES.md`](./BUSINESS_RULES.md)
- Definition of Done: [`docs/dod.md`](./docs/dod.md)
- Архитектура: [`docs/architecture.md`](./docs/architecture.md)
- Runbook'и: [`docs/runbook/`](./docs/runbook/)
- ADR: [`docs/adr/`](./docs/adr/)
- CHANGELOG: [`CHANGELOG.md`](./CHANGELOG.md)

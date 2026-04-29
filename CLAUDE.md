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
6. **Context7 всегда.** Для любого вопроса/кода по сторонней библиотеке/SDK/CLI/cloud-сервису (даже хорошо известным — React, Telethon, Aiogram, FastAPI, Anthropic SDK, Vercel) — сначала `mcp__claude_ai_Context7__query-docs` или `mcp__plugin_context7_context7__query-docs`, потом ответ. Training data Claude может отставать; context7 даёт актуальную документацию. Не использовать для рефакторинга/бизнес-логики/общих концепций.

## Внешние сервисы (получение секретов)

Перечень секретов и где их брать — см. `.env.example` и список GH Secrets в `cd-backend-{dev,prod}.yml`. Известные подводные камни:

- **my.telegram.org (TELEGRAM_API_ID / TELEGRAM_API_HASH).** Регистрация приложения **требует отключённого VPN**. С активным VPN форма отдаёт `ERROR` без диагностики (наблюдалось 2026-04-29). Платформа в форме = `Other`, описание на латинице, минимум 30 символов.
- **@BotFather (NOTIFY_BOT_TOKEN).** Сразу после `/newbot` нужно вручную нажать **Start** у созданного бота, иначе он не сможет писать в личку owner'у.
- **console.anthropic.com (ANTHROPIC_API_KEY).** Ключ показывается **один раз** при создании. Workspace = Default, имя ключа = `tlg-aggregator-{env}`.

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
- [x] **Dev VPS (`user1@87.242.87.8`, Ubuntu 22.04.5 LTS, 2 vCPU / 3.8 GB RAM / 30 GB):** SSH-ключ Максима авторизован; passwordless sudo; Docker Engine 29.4.1 + compose plugin v5.1.3 установлены через docker.com apt-репо; user1 в группе `docker`; рабочая директория `/home/user1/telegram-aggregator/`. IP/user в локальной памяти Claude, не в репо. Pending kernel upgrade `5.15.0-161` → `5.15.0-176` (low priority).
- [x] **Deploy SSH-ключ для CI** (`~/.ssh/telegram_agregator_deploy_ed25519` на машине Максима, без passphrase) сгенерирован, pub в `authorized_keys` на VPS. Приватка залита в GitHub Secret `DEV_SSH_KEY` через `gh secret set < keyfile` (UI-paste мангал ключ — пришлось перезалить из файла).
- [x] **GitHub Secrets `DEV_VPS_HOST=87.242.87.8` / `DEV_VPS_USER=user1` / `DEV_SSH_KEY=<priv>`** в репо. Верифицированы workflow_dispatch'ем `.github/workflows/smoke-dev-vps.yml` (на `main`): SSH handshake → `user1@vm-test`, sudo passwordless, docker 29.4.1, compose v5.1.3, docker-group ACTIVE — всё ✅. Workflow остался в репо как ручной health-check.
- [x] **Compose smoke на VPS:** `docker compose -f infra/compose/docker-compose.yml --env-file ../env/backend.env up -d postgres redis` с одноразовым рандомным POSTGRES_PASSWORD — postgres:16-alpine + redis:7-alpine стали healthy за 12 сек. Стек снят `down -v` после теста.
- [x] **`infra/env/backend.env.example`** добавлен в репо (PR #25): шаблон env-файла для compose `env_file:` directive со всеми обязательными полями `Settings`. `.gitignore` re-include для `infra/env/` (Python-virtualenv pattern маскировал директорию). `.gitleaks.toml` allowlist для `*.env.example` чтобы generic-api-key rule не падал на placeholder'ах.
- [x] **CI tooling:** `gh` CLI 2.91.0 поставлен на машину Максима (winget), авторизован под `SigmeD` (token scopes: `gist, read:org, repo, workflow`). `alembic.ini`: `path_separator = os` (alembic ≥1.14 deprecation, 2.0 хард-эррор). `security.yml`: `aquasecurity/trivy-action@v0.36.0` + `limit-severities-for-sarif: true` (без него action emit'ит SARIF со всеми severities → exit-code 1 на любую находку).
- [x] **Seed loader + миграция 0002 (PR #41, влит в develop 2026-04-27):** `backend/src/shared/db/seed.py` + YAML в `backend/seeds/` (32 источника + 33 триггера). Loader идемпотентен — источники upsert'ятся по `lower(username)`, триггеры — `INSERT ... ON CONFLICT (keyword, language) DO UPDATE`. Миграция `0002`: `telegram_sources.chat_id` → nullable, UNIQUE заменён на partial unique index `WHERE chat_id IS NOT NULL` (pending source сидится без chat_id, listener backfill'ит). 14 интеграционных тестов в `test_seed.py`. `backend/uv.lock` — закоммичен в составе #41.
- [x] **PR `develop → main` (#42 merged 2026-04-29, merge commit `5f31343`):** roll-up 11 коммитов (DB foundation #18, deps sweep #20-22, alembic/env/gitleaks/trivy #25, seed loader #41, dev-VPS docs #26). По пути починили: (1) `IMAGE_NAME: ${{ github.repository_owner }}/tlg-aggregator` → `sigmed/tlg-aggregator` в `cd-backend-{dev,prod}.yml` (Docker registry rejects uppercase `SigmeD`); (2) `setup-uv@v3` снят `version: "0.5.x"` pin (uv ушёл на 0.7.x, action не резолвит старый major-tag, default = latest stable); (3) убраны 3 unused `# type: ignore[untyped-decorator]` в `worker/tasks/{filter_keywords,enrich_profile,classify_llm}.py` (новый mypy узнаёт типы Celery декоратора). Конфликтов 4: `ci-backend.yml`, `security.yml`, `api/main.py`, `logging.py` — все резолвнуты в пользу develop.
- [x] **`cd-backend-dev` доходит до compose up (2026-04-29):** 14 GH Secrets заведены (POSTGRES_PASSWORD/JWT_SECRET/TELETHON_SESSION_KEY рандомы из `[Security.Cryptography.RandomNumberGenerator]`; TELEGRAM_API_ID/HASH из my.telegram.org **с выключенным VPN**; NOTIFY_BOT_TOKEN от @BotFather + ротирован после засветки в чат; ANTHROPIC_API_KEY от console.anthropic.com; TELEGRAM_PHONE/NOTIFY_BOT_ADMIN_CHAT_ID — owner data; OPENAI_API_KEY/SENTRY_DSN — пустые заглушки до Sprint 1). Серия CD-фиксов: PR #45 (pipefail → POSIX `set -eu`), #46 (deploy path `/home/user1/telegram-aggregator`), #47 (`ghcr.io/erohin-m` → `ghcr.io/sigmed`, `write_backend_env()` генерит transient `infra/env/backend.env` chmod 600 на каждом deploy, два пропущенных secrets wired через `envs:`/`env:`), #48 (`set -eu` → `set -e` — appleboy/ssh-action strip'ит empty env vars, dash-export unset valil), #49 (drop deprecated `script_stop`, STEP_*-trace), #50 (`bash -x` trace + stderr→stdout — нашёл что deploy.sh реально упирается в port-bind race с зомби-контейнером после recreate). Сейчас на VPS зелёные: postgres healthy, redis healthy, migrate exited 0 (alembic 0001+0002 прошли).

**Не сделано (блокеры для Sprint 1):**
- [ ] **FEATURE-03 (Telethon listener) не реализован.** `backend-listener` в restart loop с `NotImplementedError: SessionManager.connect is not implemented yet` (`backend/src/shared/telegram/session_manager.py:33`). Это **ожидаемое состояние**, не баг — listener будет работать когда реализуют код + сгенерируют Telethon session-файл интерактивно на VPS (SMS-код).
- [ ] **`backend-worker` падает на pydantic validation:** `LOG_LEVEL: Input should be 'DEBUG'/'INFO'/.../'CRITICAL'` — в `infra/compose/docker-compose.dev.yml` все 4 сервиса имеют `LOG_LEVEL: debug` (lowercase), а `Settings` ждёт UPPERCASE enum. Однострочный фикс при первом касании в Sprint 1.
- [ ] **`backend-api` `Created` (не started)** — race на `127.0.0.1:8000` при recreate (предыдущий контейнер не отпустил порт). Решается `docker compose down -v` на VPS перед следующим deploy либо retry. До Sprint 1 — не критично.
- [ ] **Debug-инструментация в `cd-backend-dev.yml`** — `bash -x`, STEP_*-echo, stderr→stdout. Откатить после стабилизации Sprint 1.
- [ ] Sprint 1: реализация FEATURE-01 (Telegram auth), FEATURE-02 (sources CRUD), FEATURE-03 (Telethon listener), FEATURE-04 (keyword filter).
- [ ] Follow-up: `tests/unit/test_smoke.py::test_module_imports[worker.*]` падает на pre-existing проблеме — `worker/celery_app.py:45` вызывает `create_app()` на module-level, который зовёт `get_settings()` без env vars. Фикс: либо lazy-init Celery-app, либо `tests/conftest.py` с дефолтными env vars. Та же причина почему worker'у нужен валидный LOG_LEVEL (баг #2).
- [ ] Follow-up: 14 открытых Dependabot PR на 2026-04-27 — 5× GHA bumps + 5× frontend (zod 3→4 major, vitest 2→4 + jsdom 25→29 — testing group, lucide-react minor, react-hook-form minor, next group) + 4× backend pip range widening. Безопасные бандлятся как раньше (#20-22), zod и testing group — мажоры, отдельно.

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

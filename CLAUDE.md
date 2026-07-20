# CLAUDE.md — Telegram Lead Aggregator · production backend + Next.js admin

> Живой документ. Обновлять при любом изменении стека, структуры, SDLC, скоупа или правил коллаборации; после каждого спринта / релиза — пройтись по «Текущему статусу». Stale-CLAUDE.md хуже его отсутствия — он вводит агента в заблуждение.

## Проект

**Telegram Lead Aggregator** — первый этап AI-системы лидогенерации для команды разработки MVP. Автоматизирует поиск основателей стартапов в открытых Telegram-чатах/каналах СНГ через user-session Telethon + LLM-классификацию. Заказчик и основной пользователь — Максим Ерохин.

Первоисточник требований: [`TZ_Telegram_Lead_Aggregator.md`](./TZ_Telegram_Lead_Aggregator.md) (v1.0, апрель 2026). Бизнес-инварианты: [`BUSINESS_RULES.md`](./BUSINESS_RULES.md) (BR-001…BR-110).

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.11+, Telethon 1.34+, FastAPI, Celery, Aiogram 3.x, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 15+, Redis 7 |
| LLM | Anthropic Claude Haiku (основной), OpenAI GPT-4 (fallback) |
| Frontend | Next.js 15 (App Router), React 19, TypeScript strict, Tailwind 4, shadcn/ui, TanStack Table/Query |
| Infra | Docker Compose, Nginx, VPS (Hetzner/Timeweb), Vercel (frontend only) |
| CI/CD | GitHub Actions (7 workflows: ci-backend/frontend/docs + security + cd-backend-{dev,prod} + release) |
| Observability | structlog, Prometheus, Sentry |
| Tooling | uv (Python), pnpm (frontend), pre-commit, ruff (lint+format), mypy, eslint, prettier |

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

Детали: [`docs/architecture.md`](./docs/architecture.md), ADR в [`docs/adr/`](./docs/adr/) (9 ADR: 0001–0009).

## Структура монорепо

```
.
├── backend/              # Python: listener, worker, api, bot (один образ, 4 service entrypoint'а)
│   ├── src/{shared,listener,worker,api,bot}/
│   ├── migrations/       # Alembic (env.py декуплен от Settings — читает DATABASE_URL из os.environ)
│   ├── prompts/vN/       # версионируемые LLM-промпты
│   ├── seeds/            # YAML: 32 источника + 33 keyword-триггера
│   └── tests/{unit,integration}/   # pytest, testcontainers против Postgres 15
├── frontend/             # Next.js админка (Vercel Root Directory)
│   └── src/{app,components,features,lib,test}/   # test/ — vitest setup + smoke
├── infra/
│   ├── docker/           # Dockerfile'ы (один backend-образ, multi-entrypoint)
│   ├── compose/          # docker-compose.yml + .dev.yml + .prod.yml override
│   ├── env/              # backend.env.example (transient backend.env генерится в CD)
│   ├── nginx/
│   └── scripts/          # deploy.sh, rotate-session.sh, backup-db.sh
├── docs/
│   ├── adr/              # архитектурные решения (9 ADR)
│   ├── runbook/          # операционные процедуры (4 runbook)
│   ├── retro/            # спринт-ретроспективы
│   ├── superpowers/      # plans/ + specs/ из superpowers:writing-plans
│   ├── api/openapi.yaml
│   ├── architecture.md, dod.md, dor.md, security.md, prompts-versioning.md
│   └── business_rules.md → ссылка на BUSINESS_RULES.md
├── .github/workflows/    # 7 workflows
├── BUSINESS_RULES.md     # 110 инвариантов из ТЗ
├── CHANGELOG.md          # Keep a Changelog
├── README.md, CONTRIBUTING.md, SECURITY.md, LICENSE
├── Makefile, .pre-commit-config.yaml, .editorconfig, .gitleaks.toml
├── .env.example
└── TZ_Telegram_Lead_Aggregator.md
```

## Жёсткие правила коллаборации

> Конкретные имена скилов / агентов / MCP — обязательны. «Подумай перед тем как делать» — не правило.

1. **CLAUDE.md — живой.** Изменилась структура / стек / SDLC / скоуп → правим сразу. После спринта / релиза — обновить «Текущий статус». Раз в спринт — аудит через `claude-md-management:claude-md-improver`.

2. **Никаких реальных секретов в репо.** Только `.env.example` и `infra/env/backend.env.example` со заглушками. Любое изменение `.env*` — только с явного разрешения Максима. `.gitleaks.toml` allowlist'ит `*.env.example`.

3. **Prod deploy — только после явной команды Максима.** Dev — автоматом по merge в `develop`. Триггер prod — `workflow_dispatch cd-backend-prod` + Vercel promote. GitHub environment `production` защищён Required reviewers.

4. **Risky actions — спрашиваем.** Уничтожимые / необратимые / shared-state операции (force-push, drop tables, kill containers, rm -rf, push в публичные каналы, `docker compose down -v` на prod) — confirm before action.

5. **Context7 — обязателен** для любого вопроса по сторонней библиотеке / SDK / CLI / cloud-сервису (даже популярным — Telethon, Aiogram, FastAPI, SQLAlchemy, Anthropic SDK, Next.js, Vercel CLI). Сначала `mcp__plugin_context7_context7__resolve-library-id` → `query-docs`, потом ответ. Training data модели может отставать. Не использовать для рефакторинга / бизнес-логики / общих концепций.

6. **Superpowers — рабочий стандарт.** Не «помнить» правило — вызывать скилл:
   - Creative-задача (новая фича, эндпоинт, экран) → `superpowers:brainstorming`.
   - Multi-step (3+ шага) → `superpowers:writing-plans` (артефакты в `docs/superpowers/plans/`).
   - Production-код → `superpowers:test-driven-development` (RED → GREEN → REFACTOR).
   - Любой баг / падение теста → `superpowers:systematic-debugging`.
   - Перед claim'ом «готово / тесты ок / деплой ок» → `superpowers:verification-before-completion`.
   - Длинная фича без блокировки workspace → `superpowers:using-git-worktrees`.
   - 2+ независимых трека → `superpowers:dispatching-parallel-agents`.
   - Завершение ветки → `superpowers:finishing-a-development-branch`.

7. **Multiple subagents для нетривиальных задач.** Параллелим независимые треки специализированным агентам: `Explore` для поиска, `feature-dev:code-architect` для дизайна архитектуры, `feature-dev:code-reviewer` для аудита, `general-purpose` для broad research. Делегировал поиск — не дублируй сам.

8. **TDD без исключений для production-кода.** Failing test first → implementation. Бэкенд — pytest (unit + integration через testcontainers). Frontend — vitest + Playwright golden-path для критичных flow.

9. **Conventional Commits + feature-ветки.** `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:` / `perf:` / `build:` / `ci:`. Ветка `feature/FEATURE-XX-short-name` от `develop`. Squash-merge в `develop`. Скилы — `commit-commands:commit` / `commit-commands:commit-push-pr` / `commit-commands:clean_gone`.

10. **CI gates — все зелёные перед merge.** ci-backend / ci-frontend / ci-docs / security. Obязательны DoD-чек-лист в PR (`docs/dod.md`) и пройденная DoR на старте (`docs/dor.md`).

11. **После каждого релиза — обновить документацию.** CHANGELOG обязательно (Keep a Changelog); README / runbook / ADR / OpenAPI / `prompts/vN/` — по применимости. Архитектурное решение с trade-off'ами → новый ADR в `docs/adr/`.

12. **`claude-api` skill при работе с Anthropic SDK.** Любая работа с `ANTHROPIC_API_KEY`/Claude Haiku в `backend/src/worker/tasks/classify_llm.py` — через скилл `claude-api` с обязательным prompt caching. Cache hit rate — observability-метрика.

13. **`docker-multitenancy` skill при касании compose.** Любое изменение `infra/compose/*.yml` — через скилл `docker-multitenancy` (префикс `${COMPOSE_PROJECT_NAME}-` для container_name / network / volume / Traefik-лейблов; готовность к dev+prod на одном VPS — открытый вопрос).

14. **Frontend (Next.js 15) — через `vercel:*` скилы.** Любая работа с App Router → `vercel:nextjs`. Edit 2+ TSX → авто-триггер `vercel:react-best-practices`. shadcn/ui установка / композиция → `vercel:shadcn`. Bundler issues / Turbopack → `vercel:turbopack`. Сквозной flow «браузер → API → данные» перед claim'ом → `vercel:verification`.

15. **Memory system — пишем для будущего себя.** Auto-memory в `C:\Users\Max\.claude\projects\D--Projects-telegram-agregator\memory\`. Сохраняем: `user` (роль/предпочтения Максима), `feedback` (корректировки **и** подтверждённые подходы — с **Why** и **How to apply**), `project` (кто/что/зачем/когда — absolute dates), `reference` (Linear / Slack / Grafana / Sentry — куда смотреть). Не сохраняем: file paths, git history, debug recipes, code patterns (выводимо из репо).

## Workflow (Agile + SDLC)

Канонический pipeline (superpowers + проектная специфика):

```
1. Эпик / FEATURE-XX        → привязка к ТЗ, формирование acceptance criteria
2. Brainstorm               → superpowers:brainstorming (UX, контракт API, схема данных)
3. Plan                     → superpowers:writing-plans → docs/superpowers/plans/<date>-<slug>.md
4. Ветка                    → feature/FEATURE-XX-short-name от develop
                              || длинная фича → superpowers:using-git-worktrees
5. Implement (TDD)          → superpowers:test-driven-development
                              RED → GREEN → REFACTOR
                              || параллельные треки → superpowers:dispatching-parallel-agents
6. Lint + tests локально    → make lint test (ruff + mypy + eslint + tsc + pytest + vitest)
7. Self-review              → superpowers:requesting-code-review (+ feature-dev:code-reviewer subagent)
8. Verify                   → superpowers:verification-before-completion
                              + vercel:verification для frontend
9. Commit + PR              → commit-commands:commit-push-pr, шаблон PR заставляет пройти DoD
10. CI gates                → ci-backend / ci-frontend / ci-docs / security — все зелёные
11. Review + merge develop  → squash-merge
12. Auto-deploy dev         → Vercel preview (frontend) + cd-backend-dev SSH-deploy на VPS
13. Update docs             → CHANGELOG обязательно; ADR/runbook/OpenAPI — по применимости;
                              «Текущий статус» в CLAUDE.md
14. Prod release            → PR develop → main → merge → ручной workflow_dispatch cd-backend-prod
                              **только после явного разрешения Максима** + Vercel promote
                              + тег vX.Y.Z + release notes
15. Finish                  → superpowers:finishing-a-development-branch (cleanup веток / worktree)
```

**Side quest** (нашли баг по дороге): создаём отдельный issue, не отвлекаемся, возвращаемся.

Подробно: [`docs/dod.md`](./docs/dod.md), [`docs/dor.md`](./docs/dor.md).

## Команды

```bash
# Локальная разработка
make up              # docker compose up -d (pg, redis, все backend-сервисы, frontend)
make down            # остановить
make logs svc=api    # логи сервиса
make migrate         # alembic upgrade head
make test            # backend (pytest) + frontend (vitest) тесты
make lint            # ruff check + ruff format --check + mypy, eslint+prettier+tsc
make fmt             # авто-формат
make seed            # backend/src/shared/db/seed.py (32 источника + 33 триггера, идемпотент)
```

Детали инфраструктуры: [`infra/README.md`](./infra/README.md). Backend-специфичные команды: [`backend/README.md`](./backend/README.md).

## Среды

| Среда | Frontend | Backend | Data | Триггер деплоя |
|---|---|---|---|---|
| local | `pnpm dev` | `docker compose up` | локальные контейнеры | вручную |
| dev | Vercel preview (`develop`) | VPS dev (`user1@95.81.94.83`, Frankfurt FirstByte; см. [ADR-0009](./docs/adr/0009-dev-vps-frankfurt.md)) | postgres:16-alpine + redis:7-alpine на VPS | auto по push в `develop` |
| prod | Vercel production (`main`) | VPS prod | managed PG + Redis на VPS | **только** `workflow_dispatch` **после подтверждения Максима** |

Push в `main` для frontend заблокирован через `git.deploymentEnabled.main=false` (Vercel REST API). GitHub environment `production` — Required reviewers.

## Setup на свежей машине

### 1. Системные пакеты
```bash
# Linux/macOS
curl -fsSL https://get.pnpm.io/install.sh | sh -   # pnpm
curl -LsSf https://astral.sh/uv/install.sh | sh    # uv (Python)
# Windows (winget)
winget install OpenJS.NodeJS.LTS pnpm.pnpm astral-sh.uv GitHub.cli
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

### 3. Claude Code plugins
```
/plugin install superpowers@claude-plugins-official
/plugin install vercel@claude-plugins-official
/plugin install commit-commands@claude-plugins-official
/plugin install code-review@claude-plugins-official
/plugin install feature-dev@claude-plugins-official
/plugin install claude-md-management@claude-plugins-official
/reload-plugins
```

### 4. Vercel CLI
```bash
npm i -g vercel
vercel login                  # интерактивно, OAuth device flow
cd frontend && vercel link --yes --project telegram-agregator
vercel env pull .env.local    # синхронизация envs
```

### 5. Локальный запуск
```bash
make up && make migrate && make seed
```

## State не в git

| Что | Где | Регенерация |
|---|---|---|
| `.env` с реальными ключами | локально | `cp .env.example .env` + получить секреты от Максима |
| `frontend/.vercel/project.json` | per-machine | `vercel link --yes` |
| Backend Telethon session-файл | только на VPS | сгенерировать интерактивно (SMS-код), не уносить с VPS |
| GitHub Secrets | github.com/SigmeD/telegram-agregator/settings/secrets | вручную через `gh secret set` |
| Memory-правила Claude Code | `C:\Users\Max\.claude\projects\D--Projects-telegram-agregator\memory\` | проговорить заново или довериться правилам в этом файле |

## Внешние сервисы (получение секретов)

Перечень — `.env.example` и список GH Secrets в `cd-backend-{dev,prod}.yml`. Известные подводные камни:

- **my.telegram.org (`TELEGRAM_API_ID` / `TELEGRAM_API_HASH`).** Регистрация приложения **требует отключённого VPN**. С активным VPN форма отдаёт `ERROR` без диагностики (наблюдалось 2026-04-29). Платформа = `Other`, описание на латинице, минимум 30 символов.
- **@BotFather (`NOTIFY_BOT_TOKEN`).** Сразу после `/newbot` нужно вручную нажать **Start** у созданного бота, иначе он не сможет писать в личку owner'у.
- **console.anthropic.com (`ANTHROPIC_API_KEY`).** Ключ показывается **один раз** при создании. Workspace = Default, имя ключа = `tlg-aggregator-{env}`.
- **Random secrets (`POSTGRES_PASSWORD` / `JWT_SECRET` / `TELETHON_SESSION_KEY`).** Генерим через `[Security.Cryptography.RandomNumberGenerator]` (PowerShell) или `openssl rand -base64 32`.
- **GitHub Secrets через UI vs CLI.** UI-paste может смангалить ключ (наблюдалось с SSH-ключом для `DEV_SSH_KEY`). Безопаснее — `gh secret set NAME < keyfile`.

## Бизнес-правила

Извлечены из ТЗ и сведены в [`BUSINESS_RULES.md`](./BUSINESS_RULES.md) (BR-001…BR-110). Там — критерии «что есть лид», формула скоринга, тихие часы (timezone `Asia/Yekaterinburg` — открытый вопрос), квоты API, этические ограничения. Любое решение, затрагивающее продуктовую логику, — сверять с этим файлом.

## Реестр инструментов

### Скилы

| Скилл | Триггер |
|---|---|
| `superpowers:brainstorming` | Перед creative-задачей (новая фича, эндпоинт, экран). |
| `superpowers:writing-plans` | Multi-step (3+ шага) → `docs/superpowers/plans/`. |
| `superpowers:test-driven-development` | Production-код. RED → GREEN → REFACTOR. |
| `superpowers:systematic-debugging` | Любой баг / падение теста / неожиданное поведение. |
| `superpowers:verification-before-completion` | Перед claim'ом «готово». Запуск команды + проверка вывода. |
| `superpowers:dispatching-parallel-agents` | 2+ независимых трека. |
| `superpowers:using-git-worktrees` | Длинная фича — изоляция от main workspace. |
| `superpowers:finishing-a-development-branch` | Cleanup веток / worktree после merge. |
| `claude-api` | Любая работа с Anthropic SDK / Claude Haiku — обязательно prompt caching. |
| `docker-multitenancy` | Изменения в `infra/compose/*.yml` — префикс `${COMPOSE_PROJECT_NAME}`. |
| `vercel:nextjs` | Любая работа с App Router / Server Components / Server Actions. |
| `vercel:react-best-practices` | Авто-триггер после редактирования 2+ TSX. |
| `vercel:shadcn` | Установка / композиция shadcn/ui компонентов. |
| `vercel:turbopack` | Bundler-оптимизация, HMR-issues, build problems. |
| `vercel:verification` | Сквозной flow «браузер → API → данные» для frontend. |
| `vercel:deployments-cicd` | Deploy / promote / rollback / preview / `--prebuilt`. |
| `vercel:env-vars` | `.env` / `vercel env pull` / OIDC tokens. |
| `commit-commands:commit-push-pr` | Готовая фича → коммит, push, PR. |
| `commit-commands:clean_gone` | Очистка локальных веток после merge. |
| `claude-md-management:claude-md-improver` | Раз в спринт — аудит этого файла. |

### Subagent'ы

| Агент | Применение |
|---|---|
| `Explore` | Read-only поиск (Glob / Grep): «где определено X», «что использует Y». |
| `feature-dev:code-explorer` | Глубокий анализ существующих фич — execution paths, архи-слои, зависимости. |
| `feature-dev:code-architect` | Дизайн архитектуры новой фичи — file plan, component design, data flow. |
| `feature-dev:code-reviewer` | Аудит на bugs / security / quality с confidence-фильтрацией. |
| `superpowers:code-reviewer` | Review против исходного плана из `docs/superpowers/plans/`. |
| `general-purpose` | Широкий research / multi-step с неопределённой стратегией. |
| `vercel:deployment-expert` | Vercel deploy / CI/CD / preview / rollback / domains. |
| `vercel:performance-optimizer` | Core Web Vitals / rendering / caching / images / bundle. |
| `code-simplifier:code-simplifier` | Упростить недавно изменённый код, сохранив поведение. |

### MCP servers

| Сервер | Используем для |
|---|---|
| `mcp__plugin_context7_context7__*` / `mcp__claude_ai_Context7__*` | Документация библиотек (правило 5). |
| `mcp__plugin_playwright_playwright__*` | UI golden-path / smoke / screenshots для frontend. |
| `mcp__plugin_vercel_vercel__*` | Deploy / logs / projects / docs / build logs / runtime logs. |
| `mcp__ide__*` | TypeScript diagnostics / executeCode (если используется). |

### Hooks (settings.json)

Уникальных проектных хуков пока нет. Глобальные хуки — в `~/.claude/settings.json`. Для конфигурации — скилл `update-config`. Кандидаты в проект-локальные хуки (когда понадобится):
- `PostToolUse(Write|Edit на *.ts|*.tsx)` → `pnpm vitest related --run` в `frontend/`.
- `PostToolUse(Write|Edit на backend/**/*.py)` → `uv run ruff check` + `uv run mypy` на изменённый файл.

### Memory system

Auto-memory: `C:\Users\Max\.claude\projects\D--Projects-telegram-agregator\memory\`.

| Тип | Когда сохранять |
|---|---|
| `user` | Роль / экспертиза / предпочтения Максима. |
| `feedback` | Корректировки **и** подтверждённые подходы. С **Why** и **How to apply**. |
| `project` | Кто / что / зачем / когда (absolute dates: «2026-03-05», не «через неделю»). |
| `reference` | Linear / Slack / Grafana / Sentry / Vercel dashboard — куда смотреть. |

Не сохранять: file paths, git history, debug recipes, code patterns (выводимо из репо).

## Текущий статус (2026-07-20)

Репозиторий: https://github.com/SigmeD/telegram-agregator · Vercel: `maxeroxinllm-5214s-projects/telegram-agregator` · preview `telegram-agregator-fjog3lpr8-…vercel.app`. `HEAD` = `ce9e27b` (develop, синхрон с origin).

> **Полная пофичевая история (PR #20–#59, commit-хэши, root-cause разборы) — в [`CHANGELOG.md`](./CHANGELOG.md) `[Unreleased]`.** Здесь — только компактный snapshot. Форензику сюда не накапливать (CLAUDE.md always-loaded, лимит ~35k).

**⏸ Простой с 2026-05-12 evening (~2.5 мес): 0 коммитов, 0 merge.** Состояние ровно как на момент post-smoke sweep `ce9e27b`. Блокеры Sprint 1 ниже — все открыты.

**Фундамент готов (детали — CHANGELOG):**
- [x] Монорепо, 7 CI/CD workflows, SDLC-артефакты (9 ADR, 4 runbook, DoD/DoR, OpenAPI 3.1), `BUSINESS_RULES.md` (BR-001…110).
- [x] Vercel: `develop`→auto preview, push в `main` заблокирован; GitHub env `production` под Required reviewers.
- [x] **DB-фундамент:** 5 моделей, миграции `0001`+`0002` (`chat_id` nullable + partial unique), seed-loader (`make seed`, идемпотент), 49 интеграционных тестов против PG15 (testcontainers). ADR-0008 conventions.
- [x] **Dev VPS (Frankfurt) `user1@95.81.94.83`** — ADR-0009, прямой доступ к Telegram без WG. Старый `87.242.87.8` (РФ) deprecated. Deploy-ключ `telegram_agregator_deploy_ed25519`, `cd-backend-dev` доходит до `compose up` (pg/redis/migrate healthy).
- [x] **Security CI зелёный** (PR #55): `next 15.5.18`, `urllib3 2.7.0`, `mako 1.3.12` — закрыта GHSA-волна 2026-05-04. Next 16 major отложен.
- [x] **FEATURE-03/01 Phase 1** (PR #59): Telethon listener + Fernet-session bootstrap. 5 модулей в `shared/telegram/` + `listener/`. 102 теста локально. Manual smoke на VPS прошёл — listener Up healthy, session.enc под `+375291953533`.

**🔥 Блокеры Sprint 1 (открыты, требуют действия до следующего merge):**
- [ ] **Secret drift GH ↔ VPS** (см. memory [[project_telethon_key_drift]]). Два рассинхрона: (1) `TELETHON_SESSION_KEY` — валидный Fernet сгенерён на VPS вручную, GH Secret хранит старый placeholder; (2) `DEV_VPS_HOST`/`USER` в GH Secret → старый `87.242.87.8`, реальный deploy на `95.81.94.83`. Следующий push в `develop` → `write_backend_env()` перезатрёт ключ → `session.enc` станет нерасшифровываемым (`InvalidToken`) → listener в restart-loop. **Фикс до merge:**
  ```powershell
  $key = ssh -i "$env:USERPROFILE\.ssh\telegram_agregator_deploy_ed25519" user1@95.81.94.83 'grep ^TELETHON_SESSION_KEY ~/telegram-aggregator/infra/env/backend.env | cut -d= -f2-'
  gh secret set TELETHON_SESSION_KEY -b "$key" -R SigmeD/telegram-agregator
  gh secret set DEV_VPS_HOST -b "95.81.94.83" -R SigmeD/telegram-agregator   # DEV_VPS_USER=user1 не меняется
  ```
- [ ] **reconcile-баг** (memory [[project_reconcile_valueerror]]): `listener/_reconcile_sources` не ловит `ValueError` из `client.get_entity` (мёртвый username) → один мёртвый seed валит весь listener в restart-loop. Воспроизводится на seed `russianstartups`. Обход — все 32 seed-источника деактивированы вручную. Fix: глотать `ValueError` как `ChannelPrivateError` → `is_active=false`.

**Не сделано (Sprint 1 backlog):**
- [ ] **E2E-smoke (последний шаг):** тестовый канал с `@tlgleadagg_notify_bot` (id `8559294134`, memory [[reference_notify_bot]]) админом → INSERT в `telegram_sources` → отправить `sendMessage` через Bot API → проверить строку в `raw_messages` за <5с.
- [ ] **Seed-loader не в `deploy.sh`:** добавить `docker compose exec -T backend-api python -m shared.db.seed` после `alembic upgrade head` (иначе чистый deploy → пустой `telegram_sources`).
- [ ] **`backend/seeds/keyword_triggers.yaml` — фактически 28 триггеров, не 33** (расхождение с историческим счётчиком). Сверить с ТЗ: обновить доку или дополнить YAML.
- [ ] Реализация: FEATURE-01 Phase 2 (account rotation), FEATURE-02 (sources CRUD UI), FEATURE-04 (keyword filter).
- [ ] **15 открытых Dependabot PR** (на 2026-05-12): 5× GHA, 4× frontend (вкл. zod 3→4, testing group), 5× backend pip, 1× docker base. Решений нет.
- [ ] Cleanup: 3 stale «Active Sessions» `tlg-aggregator-bootstrap` в аккаунте `+375291953533` — terminate кроме свежей.

**Открытые вопросы (требуют решения Максима):**
- Prod vs dev VPS — один сервер с разными compose-проектами (через `docker-multitenancy`) или два?
- Количество Telegram-аккаунтов в ротации (ТЗ рекомендует 2-3) — сейчас 1.
- Timezone для тихих часов (сейчас в `.env.example` = `Asia/Yekaterinburg`, проверить).
- Таймер ручной валидации (ТЗ — еженедельно 20 случайных LLM-решений): где будет UI?

Обновлять этот блок после каждого спринта / релиза.

## Контакты

- **Заказчик / владелец / основной пользователь:** Максим Ерохин · `max.eroxin.llm@gmail.com`
- **GitHub org:** `SigmeD` · репо `SigmeD/telegram-agregator`
- **Vercel team:** `maxeroxinllm-5214s-projects` · проект `telegram-agregator`
- **Demo URL (preview):** `telegram-agregator-fjog3lpr8-maxeroxinllm-5214s-projects.vercel.app`
- **Dev VPS:** `user1@95.81.94.83` (Frankfurt FirstByte, hostname `vpn`; см. [ADR-0009](./docs/adr/0009-dev-vps-frankfurt.md)). Старый `user1@87.242.87.8` deprecated 2026-05-12.

## Ссылки внутрь

- ТЗ: [`TZ_Telegram_Lead_Aggregator.md`](./TZ_Telegram_Lead_Aggregator.md)
- Бизнес-правила: [`BUSINESS_RULES.md`](./BUSINESS_RULES.md)
- Definition of Done: [`docs/dod.md`](./docs/dod.md) · DoR: [`docs/dor.md`](./docs/dor.md)
- Архитектура: [`docs/architecture.md`](./docs/architecture.md) · Security: [`docs/security.md`](./docs/security.md)
- Промпт-версионирование: [`docs/prompts-versioning.md`](./docs/prompts-versioning.md)
- ADR: [`docs/adr/`](./docs/adr/) · Runbook'и: [`docs/runbook/`](./docs/runbook/)
- Superpowers plans: [`docs/superpowers/plans/`](./docs/superpowers/plans/)
- OpenAPI: [`docs/api/openapi.yaml`](./docs/api/openapi.yaml)
- CHANGELOG: [`CHANGELOG.md`](./CHANGELOG.md)
- Contributing: [`CONTRIBUTING.md`](./CONTRIBUTING.md) · Security policy: [`SECURITY.md`](./SECURITY.md)

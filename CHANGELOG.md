# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версионирование — [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

### Added
- Исходное ТЗ v1.0 (апр 2026) зафиксировано в репо.
- Инициализация монорепо: `backend/`, `frontend/`, `infra/`, `docs/`, `.github/`.
- `CLAUDE.md` — живой бриф для Claude Code.
- `BUSINESS_RULES.md` — извлечённые из ТЗ инварианты (BR-001…BR-110).
- `.env.example` с полным списком переменных для всех сервисов.
- SDLC-артефакты: ADR (0001-0006), Definition of Done / Definition of Ready, runbook'и (telethon-ban, redis-down, llm-cost-spike, db-restore), retro-шаблон, OpenAPI-скелет, security.md.
- Скаффолд backend: 4 сервиса (listener/worker/api/bot) + shared-пакет + Alembic + prompts/v1/ + seeds.
- Скаффолд frontend: Next.js 15 (App Router) + Tailwind 4 + shadcn placeholder + TanStack Query/Table + vercel.json.
- Infra: Dockerfile'ы backend/frontend, docker-compose × 3 (base/dev/prod), nginx/api.conf, deploy.sh, rotate-session.sh, backup-db.sh.
- CI/CD workflow'ы: `ci-backend`, `ci-frontend`, `ci-docs`, `security`, `cd-backend-dev`, `cd-backend-prod` (manual), `release`.
- Makefile, `.pre-commit-config.yaml`, `.editorconfig`, CONTRIBUTING, SECURITY, LICENSE.

### Security
- Gitleaks настроен в pre-commit и в `security.yml` CI.
- Session-файл Telethon шифруется AES-256, ключ — только в env на VPS.

### Changed
- **2026-04-24** GitHub remote подключён: https://github.com/SigmeD/telegram-agregator. Запушены ветки `main` и `develop` (initial commit rebased на auto-сгенерированный remote-commit, наш README сохранён).
- **2026-04-24** Superpowers plugin установлен через `/plugin install superpowers@claude-plugins-official` — добавляет 14 skills (brainstorming, writing-plans, executing-plans, tdd, verification-before-completion и др.) и 6 subagent'ов для параллельной работы.
- **2026-04-24** GitHub Environment `production` защищён Required reviewers — `cd-backend-prod.yml` не сработает без ручного одобрения Максима. Правило «prod deploy только по разрешению» закрыто на уровне платформы.
- `.gitattributes` добавлен — LF enforcement для shell-скриптов, критично для Linux VPS.

### Fixed
- **2026-04-24** Vercel build fail `pnpm install --frozen-lockfile exit 1` (headless install без lockfile). Причина: workspace lockfile лежал на уровень выше Root Directory `frontend/` и Vercel его не видел. Решение — отложили pnpm workspace до появления shared-пакетов (ADR-0007), lockfile перенесён в `frontend/pnpm-lock.yaml`.
- **2026-04-24** Vercel build fail на `globals.css` (Next.js webpack error). Причина: postcss.config.mjs использовал `@tailwindcss/postcss`, но этот пакет не был в package.json (Tailwind 4 выпустил PostCSS-плагин отдельно). Решение — добавлены `@tailwindcss/postcss` и `postcss` в devDependencies.
- **2026-04-24** Vercel git-triggered deploys падали с 0ms error. Две причины: (1) dashboard-стэйт проекта хранил старый ignoreCommand `git diff ... ../pnpm-lock.yaml`, невалидный после переноса lockfile; vercel.json обновляет только CLI-deploys, не git-webhooks. (2) Project rootDirectory был null → Vercel клонил в корень репо и команда билда не находила frontend/. Решение — через Vercel REST API: обнулён commandForIgnoringBuildStep, установлен rootDirectory=frontend.

### Added
- **2026-04-24** Первый успешный Vercel preview-деплой: https://telegram-agregator-ezxlixyl4-maxeroxinllm-5214s-projects.vercel.app (target=preview, Ready, 47s build). Требует авторизации через Vercel SSO (Deployment Protection включён — это ОК для внутренней dev-площадки).
- **2026-04-24** Vercel Git Integration подключена (`vercel git connect`). Push в `develop` → автоматический preview-деплой (подтверждено build `fjog3lpr8`, 51s Ready). Push в `main` заблокирован через `vercel.json git.deploymentEnabled.main=false` — верифицировано: после push в main за 90с НЕ создано ни одного нового deployment record. Production alias `telegram-agregator-maxeroxinllm-5214s-projects.vercel.app` возвращает HTTP 404 (никогда не был успешно задеплоен).
- **2026-04-24** Vercel CLI plugin для Claude Code установлен — добавляет ~30 vercel:* skills для управления через Skill tool.
- **2026-04-24** DB-фундамент: 5 SQLAlchemy моделей (`TelegramSource`, `RawMessage`, `KeywordTrigger`, `LeadAnalysis`, `SenderProfile`) в `backend/src/shared/db/tables/`. Миграция `0001_initial` со всеми CHECK-констрейнтами, FK `ON DELETE RESTRICT`, двумя partial-индексами (WHERE `is_active=true` / `is_lead=true`), UNIQUE'ами. 35 интеграционных тестов против реального Postgres 15 (testcontainers): CHECK-валидация (source_type, priority, processing_status, confidence), FK RESTRICT, UNIQUE'ы, JSONB round-trip, TIMESTAMPTZ preserves-instant, upgrade→downgrade round-trip, partial-index WHERE-clause sanity.
- **2026-04-24** ADR-0008 "Database conventions" — TIMESTAMPTZ, UUID `gen_random_uuid()`, VARCHAR+CHECK вместо ENUM, FK RESTRICT, Alembic naming convention на `Base.metadata`.

### Changed (DB foundation)
- `migrations/env.py` декуплен от `shared.config.Settings` — читает `DATABASE_URL` из `sqlalchemy.url` или `os.environ` напрямую. Alembic больше не требует всех Telegram/LLM/notification secrets для применения миграций (критично для интеграционных тестов и one-off schema dumps).
- `shared.db.session.Base` получает кастомный `MetaData(naming_convention=…)` — имена PK/FK/CHECK/UQ/IX становятся детерминированными, autogenerate перестаёт генерить фантомные diff'ы.

### Pending (блокеры Sprint 1)
- ~~Заливка GitHub Secrets~~ — закрыто 2026-04-26 (см. ниже).
- ~~Dev VPS предоставлен, SSH-ключи в GitHub Secrets~~ — закрыто 2026-04-26.
- Telethon session сгенерирована вручную на VPS.
- `backend/uv.lock` для reproducible builds.
- Backend Docker image собран + проверен в compose.
- PR `develop → main` — manual call Максима (5+ коммитов разницы, ожидаются мелкие конфликты).

### CI / infra (session 2026-04-26)
- **Dev VPS** `user1@87.242.87.8` (Ubuntu 22.04.5 LTS, 2 vCPU / 3.8 GB / 30 GB) предоставлен, личный SSH-ключ Максима авторизован, passwordless sudo. Установлены Docker Engine 29.4.1 + compose plugin v5.1.3 (через docker.com apt-репо). user1 в группе `docker`. Рабочая директория `/home/user1/telegram-aggregator/`.
- **Deploy SSH-ключ для CI** (`telegram_agregator_deploy_ed25519`, ed25519, без passphrase) сгенерирован локально, pub в `authorized_keys` на VPS. Приватка залита в GitHub Secret `DEV_SSH_KEY` через `gh secret set < keyfile` — UI-paste мангал ключ при первом заливе, `gh` CLI обходит буфер обмена и проблема ушла.
- **GitHub Secrets** `DEV_VPS_HOST=87.242.87.8`, `DEV_VPS_USER=user1`, `DEV_SSH_KEY=<priv>` залиты. **PR #23** добавил `.github/workflows/smoke-dev-vps.yml` (workflow_dispatch SSH-проба) — workflow_run #24965406706 зелёный за 5 сек: `user1@vm-test`, sudo passwordless, docker 29.4.1, compose v5.1.3, docker-group ACTIVE. Workflow остался как ручной health-check.
- **PR #24** `fix(ci)`: drone-ssh (под appleboy/ssh-action) запускает remote-script под `/bin/sh -c` (dash на Ubuntu) — `set -Eeuo pipefail` непринят. `set -eu` покрывает потребности smoke-скрипта.
- **PR #25** `chore(ci)` в develop: `backend/migrations/alembic.ini` `path_separator = os` (alembic ≥1.14 deprecation, 2.0 хард-эррор). `infra/env/backend.env.example` — env-template для compose `env_file:` directive. `.gitignore` re-include для `infra/env/` (Python-virtualenv pattern `env/` маскировал директорию). `.gitleaks.toml` allowlist для `*.env.example` чтобы generic-api-key rule не падал на placeholder JWT_SECRET. `security.yml` `limit-severities-for-sarif: true` — без него action emit'ит SARIF со всеми severities → exit-code 1 на любую находку (был MEDIUM CVE-2026-41305 в postcss 8.4.31, транзитивно через next 15.5.x).
- **`gh` CLI 2.91.0** установлен на машине Максима (winget GitHub.cli), авторизован под `SigmeD` (token scopes: `gist, read:org, repo, workflow`).
- **CI scaffold-фиксы на main** в составе PR #23: bandit B104 false-positive на `0.0.0.0` bind в `api/main.py` (контейнер = security boundary; `# nosec B104`); 7 ruff issues (unused noqa S104/ASYNC110, `__all__` сорт, blank line у imports, quoted annotations у TYPE_CHECKING-imports); 5 mypy issues (`# type: ignore[untyped-decorator]` на 3 Celery `@app.task`, drop stale `[call-arg]` в Settings, `[no-any-return]` на structlog `.bind()`); ci-backend.yml `pytest -n auto` → без xdist (нет в deps), `test-integration` job → gated на `hashFiles('backend/tests/integration/test_*.py')`. На develop эти фиксы пришли иначе через #21/#22 — слияние при `develop → main` PR может потребовать ручного резолва.
- **Compose smoke на dev VPS:** `docker compose up -d postgres redis` через `infra/compose/docker-compose.yml` с одноразовым рандомным POSTGRES_PASSWORD — postgres:16-alpine + redis:7-alpine стали healthy за 12 сек. Стек снят `down -v` после теста.

### Documentation
- **2026-04-24** `CLAUDE.md` расширен: секция «Setup на свежей машине» (инструкция onboarding после смены железа), детализирован блок Current state с явным разделением сделано/не сделано и открытыми вопросами.

### CI / deps (sweep 2026-04-24)
- **PR #19** `chore(ci)`: all CI jobs made green on develop — markdownlint config, trivy-action `v0.36.0`, bandit pyproject `[tool.bandit]` targets, pytest-xdist для `-n auto`, `test_smoke` placeholder для ветки без integration-маркеров.
- **PR #20** `chore(deps)`: GitHub Actions bumps — `actions/setup-python@v5→v6`, `actions/upload-artifact@v4→v7` (в ci-backend), `github/codeql-action/upload-sarif@v3→v4`, `softprops/action-gh-release@v2→v3`. `.github/dependabot.yml` получил `target-branch: develop` во всех 4 секциях — впредь dependabot-PR пойдут сразу в develop, а не в main.
- **PR #21** `chore(deps)`: расширение пин-диапазонов (redis <6→<8, openai <2→<3, cryptography <43→<47, pytest-cov <6→<8). **Drop black полностью** — один форматтер (`ruff format`, Black-compatible) вместо двух. Black удалён из dev-deps, `[tool.black]`, pre-commit, alembic post-write hooks, CI workflow job переименован в `lint (ruff + mypy)`. Причина — black и ruff format расходились на multi-line strings и уже ломали CI.
- **PR #22** `chore(deps)` + `ci(frontend)`: frontend major-bumps — jose 5→6 (API jwtVerify/JWTPayload unchanged), lucide-react 0.454→1.11 (first stable, пока не используется), @hookform/resolvers 3→5 (пока не используется). Попутно починено скаффолд-наследство: vitest был на classic JSX transform (тесты падали `React is not defined`) — добавлен `esbuild.jsx: 'automatic'`; в `.eslintrc.cjs` висел extends `'prettier'` без `eslint-config-prettier` + TS-rules без плагина — вычищено; `actions/upload-artifact@v7` нужно явно `include-hidden-files: true` для `.next/`.
- **Dependabot cleanup:** из 17 PR-ов, открытых не туда (против main вместо develop), закрыто 14. Применены через ручные chore-ветки те, что решили тащить. Отклонены с обоснованием: #8 (Python 3.11→3.14 major), #11 (Node 20→25 non-LTS), #12 (Next 15→16 преждевременно). Отложен #14 (vitest 2→4 + jsdom 25→29 — major test-infra, требует отдельной прогонки через миграционные codemod'ы vitest v4).

---

## Правила ведения

1. Каждая фича/фикс → запись в `[Unreleased]` в категории `Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`.
2. При релизе — блок `[Unreleased]` превращается в `[X.Y.Z] — YYYY-MM-DD`.
3. SemVer:
   - MAJOR — ломающие изменения бизнес-правил или API.
   - MINOR — новая фича без слома.
   - PATCH — багфикс, правки документации.
4. CI (`ci-docs.yml`) блокирует PR в `main`, если CHANGELOG не изменён.

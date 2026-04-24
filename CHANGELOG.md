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

### Pending (блокеры Sprint 1)
- Заливка GitHub Secrets — после явного разрешения Максима (список: `infra/README.md`, `.env.example`).
- Dev VPS предоставлен, SSH-ключи в GitHub Secrets.
- Telethon session сгенерирована вручную на VPS.
- SQLAlchemy-модели (`backend/src/shared/db/models.py`) и первая миграция `0001_initial.py`.
- Dependabot PR #12 (Next.js 15→16 major) — merge или close.

### Documentation
- **2026-04-24** `CLAUDE.md` расширен: секция «Setup на свежей машине» (инструкция onboarding после смены железа), детализирован блок Current state с явным разделением сделано/не сделано и открытыми вопросами.

---

## Правила ведения

1. Каждая фича/фикс → запись в `[Unreleased]` в категории `Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`.
2. При релизе — блок `[Unreleased]` превращается в `[X.Y.Z] — YYYY-MM-DD`.
3. SemVer:
   - MAJOR — ломающие изменения бизнес-правил или API.
   - MINOR — новая фича без слома.
   - PATCH — багфикс, правки документации.
4. CI (`ci-docs.yml`) блокирует PR в `main`, если CHANGELOG не изменён.

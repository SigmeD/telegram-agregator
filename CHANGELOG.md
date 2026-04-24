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

### Pending
- Заливка GitHub Secrets (после явного разрешения Максима). Список — в `infra/README.md` и `.env.example`.
- Включить Environment protection для `production` (Settings → Environments → required reviewers).
- Привязка Vercel-проекта к репо (Root Directory = `frontend`).
- Выделение dev VPS, генерация Telethon session вручную на VPS.
- Первая миграция БД (FEATURE-02, FEATURE-03 схемы) — Sprint 1.

---

## Правила ведения

1. Каждая фича/фикс → запись в `[Unreleased]` в категории `Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`.
2. При релизе — блок `[Unreleased]` превращается в `[X.Y.Z] — YYYY-MM-DD`.
3. SemVer:
   - MAJOR — ломающие изменения бизнес-правил или API.
   - MINOR — новая фича без слома.
   - PATCH — багфикс, правки документации.
4. CI (`ci-docs.yml`) блокирует PR в `main`, если CHANGELOG не изменён.

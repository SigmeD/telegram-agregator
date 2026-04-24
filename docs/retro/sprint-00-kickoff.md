# Retro: Sprint 00 — Kickoff (2026-04-24)

- **Период:** 2026-04-24 (однодневная установочная сессия)
- **Фасилитатор:** Максим Ерохин
- **Участники:** Максим Ерохин (PM/владелец), backend-разработчик (TBA), frontend-разработчик (TBA)
- **Цель:** зафиксировать ТЗ, стек, SDLC-процесс, правила работы. Разработка ещё не стартовала — настоящие ретро начнутся со Sprint 01.

## Что решили

### Продукт и scope

- Работаем строго по `TZ_Telegram_Lead_Aggregator.md` v1.0 (апрель 2026).
- Out of scope (ТЗ разд. 7) не берём даже «чуть-чуть»: LinkedIn, vc.ru, Crunchbase, автоаутрич — всё после стабилизации Telegram-модуля.
- Три спринта по 2 недели, релиз MVP через 6 недель (ТЗ разд. 5).

### Технологический стек

- Backend: Python 3.11+, Telethon 1.34+, FastAPI, Celery, Aiogram 3.x, PostgreSQL 15+, Redis.
- Frontend: Next.js 15, Tailwind, shadcn/ui, TanStack Table.
- LLM: Anthropic Claude Haiku основной, OpenAI GPT-4 fallback (ADR-0004).
- Инфраструктура: Docker Compose, Nginx, Hetzner VPS для backend, Vercel для frontend (ADR-0005), GitHub Actions для CI/CD.

### SDLC-процесс

- **Монорепо** с `backend/`, `frontend/`, `infra/`, `docs/`, `prompts/` (ADR-0002).
- **ADR** для значимых архитектурных решений (ADR-0001). Шаблон — `docs/adr/TEMPLATE.md`.
- **Definition of Ready** (`docs/dor.md`) и **Definition of Done** (`docs/dod.md`) обязательны для любой задачи спринта.
- **Runbook'и** для эксплуатации — `docs/runbook/`.
- **OpenAPI** спецификация — источник истины контракта Admin API (`docs/api/openapi.yaml`), frontend генерирует клиент из неё.

### CI/CD

- GitHub Actions: lint + tests + build на каждый PR; деплой в dev на merge в `main`; деплой в prod — ручной trigger с approval от Максима.
- Frontend: preview-деплои Vercel автоматически на PR.
- Backend: `docker compose pull && up -d` через SSH-runner на VPS.

### Правила команды

- **Env.** Никаких секретов в коде. Все `.env.example` в репо, реальные значения — в GitHub Environments (`dev`, `prod`) и на VPS `/opt/tla/infra/.env.prod`. См. `docs/security.md`.
- **Prod-deploy.** Только через CI, только после зелёного dev, только с approval от Максима. Никаких ручных `docker compose` команд на prod вне runbook'ов.
- **Docs.** Меняешь архитектуру — обновляешь `docs/architecture.md` или пишешь ADR в том же PR. Меняешь API — обновляешь `openapi.yaml`. Меняешь поведение в рантайме — проверяешь актуальность runbook'ов.
- **Ретро.** Каждый спринт — retro по шаблону `docs/retro/TEMPLATE.md`. Action items с owner и deadline.
- **Инциденты.** Канал `#incidents`, runbook-first, постмортем для SEV >= 2.

## Action items

| # | Действие | Owner | Deadline | Статус |
|---|----------|-------|----------|--------|
| 1 | Нанять backend-разработчика | Максим | 2026-04-30 | open |
| 2 | Нанять frontend-разработчика | Максим | 2026-05-07 | open |
| 3 | Зарегистрировать выделенный Telegram-номер + 2 резервных | Максим | 2026-05-01 | open |
| 4 | Получить Anthropic и OpenAI API-ключи, завести в GitHub Secrets | Максим | 2026-04-28 | open |
| 5 | Провизировать Hetzner VPS (4 vCPU / 8 GB) | Максим | 2026-04-30 | open |
| 6 | Подготовить размеченный validation-датасет на 100 сообщений для LLM | Максим | 2026-05-10 | open |
| 7 | Настроить GitHub Actions workflows + Vercel + VPS deploy | backend-dev | 2026-05-15 | open |

## Ссылки

- ТЗ: [`TZ_Telegram_Lead_Aggregator.md`](../../TZ_Telegram_Lead_Aggregator.md)
- Архитектура: [`../architecture.md`](../architecture.md)
- ADR: [`../adr/`](../adr/)
- Runbook: [`../runbook/README.md`](../runbook/README.md)
- DoR / DoD: [`../dor.md`](../dor.md), [`../dod.md`](../dod.md)

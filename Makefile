# Telegram Lead Aggregator — dev orchestration
# Windows: используйте Git Bash/WSL. Либо `make` из Chocolatey.

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Compose: базовый + dev override для локалки.
COMPOSE := docker compose -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.dev.yml
SVC ?= api

.PHONY: help
help: ## Список команд
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ─── Стек ────────────────────────────────────────────────
.PHONY: up
up: ## Поднять весь стек локально (pg, redis, 4 backend-сервиса, frontend)
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Остановить стек, сохранить volumes
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Снести стек вместе с volumes (⚠ удаляет локальные данные)
	$(COMPOSE) down -v

.PHONY: ps
ps: ## Статус сервисов
	$(COMPOSE) ps

.PHONY: logs
logs: ## Логи сервиса: make logs svc=api
	$(COMPOSE) logs -f $(SVC)

.PHONY: shell
shell: ## Шелл в сервисе: make shell svc=api
	$(COMPOSE) exec $(SVC) /bin/bash

# ─── Миграции / seeds ────────────────────────────────────
.PHONY: migrate
migrate: ## Alembic upgrade head
	$(COMPOSE) exec api alembic upgrade head

.PHONY: migrate-create
migrate-create: ## Новая миграция: make migrate-create name=add_leads_table
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(name)"

.PHONY: migrate-down
migrate-down: ## Откат последней миграции
	$(COMPOSE) exec api alembic downgrade -1

.PHONY: seed
seed: ## Загрузить seed-данные (источники, триггеры)
	$(COMPOSE) exec api python -m shared.db.seed

# ─── Тесты / линтеры ─────────────────────────────────────
.PHONY: test
test: test-backend test-frontend ## Все тесты

.PHONY: test-backend
test-backend: ## Backend unit+integration тесты
	cd backend && uv run pytest -v

.PHONY: test-frontend
test-frontend: ## Frontend vitest
	cd frontend && pnpm test

.PHONY: lint
lint: lint-backend lint-frontend ## Все линтеры

.PHONY: lint-backend
lint-backend: ## ruff check + ruff format --check + mypy
	cd backend && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src

.PHONY: lint-frontend
lint-frontend: ## eslint + tsc --noEmit + prettier --check
	cd frontend && pnpm lint && pnpm typecheck && pnpm prettier --check "src/**/*.{ts,tsx}"

.PHONY: fmt
fmt: ## Авто-форматирование
	cd backend && uv run ruff check --fix src tests && uv run ruff format src tests
	cd frontend && pnpm prettier --write "src/**/*.{ts,tsx,json,md}"

# ─── Безопасность ────────────────────────────────────────
.PHONY: audit
audit: ## pip-audit + pnpm audit + gitleaks
	cd backend && uv run pip-audit || true
	cd frontend && pnpm audit || true
	gitleaks detect --no-git -v || true

# ─── Deploy (прокси к infra/scripts) ─────────────────────
.PHONY: deploy-dev
deploy-dev: ## Деплой на dev VPS (требует SSH-ключи в env). Prod — только из GitHub Actions после одобрения.
	infra/scripts/deploy.sh dev $${TAG:-dev}

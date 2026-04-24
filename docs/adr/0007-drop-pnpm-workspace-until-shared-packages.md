# ADR-0007: Отложить pnpm workspace до появления shared-пакетов

**Status:** Accepted
**Date:** 2026-04-24
**Deciders:** Максим, Claude

## Context

В изначальном скаффолде монорепо присутствовал `pnpm-workspace.yaml` в корне с единственным пакетом `frontend/`. Идея — задел на будущие shared-пакеты (UI-kit, API-client из OpenAPI).

При первом preview-деплое на Vercel сборка упала:
```
ERROR  Headless installation requires a pnpm-lock.yaml file
Error: Command "pnpm install --frozen-lockfile" exited with 1
```

Причина: Vercel Root Directory установлен в `frontend/` (линкуется именно там), а `pnpm-lock.yaml` генерируется в корне workspace (на уровень выше). По умолчанию Vercel не поднимается за пределы Root Directory, поэтому lockfile невидим.

## Decision

Удалить `pnpm-workspace.yaml` и корневой `pnpm-lock.yaml`. Переместить lockfile внутрь `frontend/`. `frontend/` становится standalone pnpm-пакетом.

## Alternatives considered

1. **Vercel setting "Include source files outside Root Directory" = true** — включается только в dashboard, не в `vercel.json`. Добавляет время сборки (загружает весь монорепо) и требует ручной настройки при любом новом деплое/проекте.
2. **Install command `cd .. && pnpm install`** — всё равно требует наличия `../pnpm-lock.yaml` в аплоуде. Проблема та же.
3. **Сменить пакетный менеджер на npm** — проще, но pnpm уже в конфиге, CI-workflows, документации. Большая правка.

## Consequences

**Плюсы:**
- Vercel-сборка работает «из коробки» без dashboard-тюнинга.
- Простой `cd frontend && pnpm install` — ничего не нужно знать про workspace.
- CI frontend-workflow не требует специальной обработки lockfile-путей.

**Минусы / отложенный долг:**
- При добавлении shared-пакета (`packages/ui`, `packages/api-client`) придётся восстанавливать workspace-структуру. Это будет отдельный ADR + миграция lockfile.
- Типы, общие между backend (OpenAPI) и frontend, пока придётся либо публиковать npm-пакетом, либо хранить дублированно с codegen-шагом в CI.

## Восстановление workspace в будущем

Триггер для пересмотра: появление хотя бы одного общего пакета между frontend и (потенциальным) вторым JS-приложением, ИЛИ решение генерировать TypeScript-типы из OpenAPI как отдельный пакет.

Шаги восстановления:
1. Вернуть `pnpm-workspace.yaml` в корень, добавить новые пакеты в `packages/`.
2. Переместить `frontend/pnpm-lock.yaml` в корень (пересоздать через `pnpm install -w`).
3. В Vercel dashboard → Project Settings → General → Root Directory — включить "Include source files outside of the Root Directory".
4. Обновить `vercel.json` ignoreCommand:
   `"ignoreCommand": "git diff --quiet HEAD^ HEAD -- . ../pnpm-lock.yaml ../packages"`.
5. Обновить CI-workflow `ci-frontend.yml` — pnpm install из корня с `--filter=@telegram-agg/admin`.

## Связанные документы

- Первичное описание структуры: ADR-0002 (monorepo-layout)
- Vercel-first frontend: ADR-0005

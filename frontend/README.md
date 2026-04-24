# @telegram-agg/admin

Админ-панель для Telegram Lead Aggregator (FEATURE-09 в [TZ](../TZ_Telegram_Lead_Aggregator.md)).

Next.js 15 (App Router) + React 19 + TypeScript strict + Tailwind 4 + shadcn/ui +
TanStack Query/Table + Zod + react-hook-form.

## Локальный запуск

```bash
# из корня монорепо
cd frontend
pnpm install
pnpm dev          # http://localhost:3000
```

Скрипты:

| Команда            | Действие                           |
| ------------------ | ---------------------------------- |
| `pnpm dev`         | dev-сервер Next.js                 |
| `pnpm build`       | production-сборка                  |
| `pnpm start`       | запуск production-сборки           |
| `pnpm lint`        | ESLint (next/core-web-vitals)      |
| `pnpm typecheck`   | `tsc --noEmit`                     |
| `pnpm test`        | vitest + @testing-library/react    |

## Переменные окружения

Создайте `frontend/.env.local`:

```
# URL backend API (FastAPI), используется на стороне сервера
API_URL=http://localhost:8000

# Тот же URL, но доступный клиентскому бандлу
NEXT_PUBLIC_API_URL=http://localhost:8000

# Секрет для проверки JWT, выданных backend-ом
JWT_SECRET=change-me
```

## Связь с backend

- Запросы с клиента уходят на `/api/:path*`, и `next.config.mjs` проксирует их
  на `API_URL` (см. `rewrites`).
- `src/lib/api-client.ts` — типизированный `fetch`-враппер, который возвращает
  `ApiError` при не-2xx ответах.
- `src/lib/auth.ts` — проверка JWT через `jose`. В проде ожидается access-token,
  выпущенный backend-ом.

## Деплой

Vercel, проект привязан к директории `frontend/`. Конфиг — `vercel.json`:
`ignoreCommand` пропускает сборку, если в `frontend/` и в корневом
`pnpm-lock.yaml` нет изменений.

## Структура

```
src/
  app/
    layout.tsx         # root layout + providers
    page.tsx           # Dashboard
    (admin)/           # route group: leads, sources, triggers, analytics, settings
    api/health/        # health-check Route Handler
  components/
    providers.tsx      # QueryClientProvider
    ui/                # shadcn/ui (устанавливается через pnpm dlx shadcn add)
  lib/
    api-client.ts
    auth.ts
    query-client.ts
  test/
    setup.ts
    smoke.test.tsx
```

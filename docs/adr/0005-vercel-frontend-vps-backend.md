# ADR-0005: Frontend на Vercel, backend на VPS

- **Статус:** Accepted
- **Дата:** 2026-04-24
- **Авторы:** команда Telegram Lead Aggregator

## Контекст

Продукт состоит из двух технически несхожих частей:

1. **Backend.** Telethon listener — это процесс с постоянным MTProto-соединением, живущий неделями; Celery worker'ы — долгоживущие процессы; FastAPI обслуживает REST; Postgres и Redis — stateful сервисы. Serverless-модель (эфемерные функции с ограничением времени жизни) концептуально не подходит: MTProto-сессия требует persistent TCP-соединения, session-файл — локального (или шифрованного персистентного) хранилища.
2. **Frontend.** Next.js 15 админка — классическое SPA+SSR-приложение без stateful-компонентов, отлично ложится на edge/serverless-платформы. Объём аудитории — 1–3 пользователя (Максим + sales в будущем), требования к latency — p95 < 2 сек на загрузку страницы (ТЗ FEATURE-09).

## Решение

- **Frontend — Vercel.** Dev/prod-preview через GitHub integration. Переменные `NEXT_PUBLIC_API_BASE_URL` указывают на FastAPI backend на VPS. Auth — bearer JWT, полученный через backend.
- **Backend — VPS (Hetzner, 4 vCPU / 8 GB RAM).** Docker Compose, Nginx reverse proxy с HTTPS (Let's Encrypt), systemd не используется (всё через compose restart policies). Деплой — `docker compose pull && docker compose up -d` из GitHub Actions.

## Рассмотренные альтернативы

- **Backend целиком на serverless (AWS Lambda, Vercel Functions).** Несовместимо с Telethon long-running session; стоимость persistent-воркеров на Lambda/Fargate выше Hetzner в 3–5x при меньшей предсказуемости.
- **Frontend на том же VPS (Nginx static).** Теряем preview-деплои на PR, CDN, автоматический HTTPS.
- **Managed Kubernetes (GKE/EKS).** Оверинжиниринг для команды из 2 человек и объёма трафика админки.

## Последствия

- **Позитивные.** Frontend-разработчик получает preview-URL на каждый PR автоматически; backend-разработчик контролирует весь runtime.
- **Негативные.** Два места деплоя → два набора секретов → два CI-джоба. CORS настраивается явно в FastAPI.
- **Операционные.** Vercel free tier достаточно на старте; VPS мониторится через Sentry + простые cron-healthchecks.

## Ссылки

- ТЗ разд. 2.2, FEATURE-09
- ADR-0002 (monorepo layout)

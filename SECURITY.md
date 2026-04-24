# Security Policy

> Детальная модель угроз — в [`docs/security.md`](./docs/security.md). Этот файл — для внешних заявок об уязвимостях и ключевых инструкций.

## Reporting

Если вы нашли уязвимость — **не** создавайте публичный issue. Напишите напрямую: `max.eroxin.llm@gmail.com` с темой `[SECURITY] Telegram Lead Aggregator`. Ответ в течение 72 ч.

## Критичные активы

| Актив | Зачем | Где хранится | Защита |
|---|---|---|---|
| Telethon session (`.session`) | Полный доступ к user-аккаунту Telegram | Шифрованный файл на VPS, смонтирован в контейнер | AES-256 (ключ `TELETHON_SESSION_KEY` в env на VPS), бэкап в encrypted S3 |
| Claude/OpenAI API keys | LLM-обработка | GitHub Secrets → env контейнеров | Rotate ежеквартально |
| Notify-bot token | Уведомления Максиму | GitHub Secrets → env | Rotate при инциденте |
| JWT_SECRET | Аутентификация админки | GitHub Secrets / Vercel env | Длина ≥ 64 байта |
| PostgreSQL credentials | Доступ к БД лидов | GitHub Secrets + Docker secret | Firewall на VPS, no public port |
| Персональные данные авторов лидов | Собственно ценность продукта | PostgreSQL | См. GDPR-политику ниже |

## Секреты и `.env`

- Любые изменения в `.env`, GitHub Secrets, Vercel env — **только после явного разрешения** Максима (`max.eroxin.llm@gmail.com`).
- Gitleaks работает как pre-commit hook и в CI (`security.yml`).
- Утечка секрета → немедленная ротация + инцидент в [`docs/runbook/secret-leak.md`](./docs/runbook/secret-leak.md) (создаётся по факту первого инцидента).

## Политика доступа

- Prod deploy — `workflow_dispatch` + GitHub Environment `production` с required reviewer (Максим).
- Dev deploy — auto по merge в `develop`.
- VPS — только SSH-ключ Максима + отдельный ключ GitHub Actions (read-only на чтение compose-файлов, write на деплой-скрипт).
- БД — только из сети VPS, публичный порт закрыт.

## GDPR / приватность

- Сохраняем только публично доступные данные (username, bio, сообщения из публичных чатов/каналов, куда подписан наш аккаунт).
- Не сохраняем телефоны авторов без явного указания в bio (`BR-071`).
- Приватные чаты не парсим (`BR-072`).
- Запрос на удаление данных (`data@max.eroxin.llm` или в Telegram-боте) обрабатывается в 30 дней: удаление `sender_profiles`, `raw_messages`, `lead_analysis` по `telegram_user_id`.
- Audit log всех действий в админке (`BR-075`).
- Session-файлы и бэкапы БД шифруются at rest.

## Supported versions

Проект на ранней стадии. Единственная поддерживаемая версия — последняя в `main`. Security-патчи накатываются в ближайший релиз (`patch` или `minor`).

## Runbook'и при инцидентах

- Бан Telegram-аккаунта: [`docs/runbook/telethon-ban.md`](./docs/runbook/telethon-ban.md)
- Утечка секрета: `docs/runbook/secret-leak.md` (создаётся по факту)
- Всплеск расходов на LLM: [`docs/runbook/llm-cost-spike.md`](./docs/runbook/llm-cost-spike.md)
- Восстановление БД: [`docs/runbook/db-restore.md`](./docs/runbook/db-restore.md)

# Runbook: Telethon-аккаунт заблокирован или ограничен

**Severity по умолчанию:** SEV-2 (primary account). SEV-1 если упали все аккаунты в ротации.

## Признаки

- В логах listener'а: `AuthKeyError`, `AuthKeyUnregisteredError`, `UserDeactivatedBanError`, `PhoneNumberBannedError`.
- Длинный `FloodWaitError` (> 1 часа).
- `ChannelPrivateError` на источниках, которые раньше работали.
- В Telegram-клиенте на рабочем номере — сообщение «Your account has been limited» от @SpamBot.
- Метрика `messages_received_total` падает в 0 при нормальной активности источников.

## Шаги диагностики (по порядку)

### 1. Определить тип проблемы

```bash
# подключиться к VPS
ssh deploy@vps.example.com

# посмотреть последние 200 строк логов listener
docker compose -f /opt/tla/infra/docker-compose.prod.yml logs --tail=200 telethon-listener
```

Смотрим последние ошибки:

- `FloodWaitError(seconds=N)` с `N < 3600` — временный rate-limit. **Переход к шагу 3.**
- `FloodWaitError(seconds=N)` с `N >= 3600` — аккаунт вошёл в tier с длинным cooldown. **Переход к шагу 4.**
- `AuthKeyError` / `AuthKeyUnregisteredError` — session-файл недействителен (revoked). **Переход к шагу 5.**
- `UserDeactivatedBanError` / `PhoneNumberBannedError` — аккаунт забанен. **Переход к шагу 6.**
- `ChannelPrivateError` на большинстве источников — аккаунт вычищен из чатов админами чатов, возможно после жалоб. **Переход к шагу 7.**

### 2. Проверить статус аккаунта напрямую

С рабочей машины (не с сервера), войти в Telegram-клиент под проблемным номером и проверить сообщения от @SpamBot. Снять скриншот в `#incidents`.

### 3. FloodWait короткий (< 1 часа) — переждать

```bash
# поставить listener на паузу вручную, чтобы не усугубить
docker compose -f /opt/tla/infra/docker-compose.prod.yml stop telethon-listener

# подождать N секунд + 10% (из логов)
# затем запустить снова
docker compose -f /opt/tla/infra/docker-compose.prod.yml start telethon-listener
```

Проверить метрики: `messages_received_total` должен возобновить рост.

### 4. FloodWait длинный → переключение на резервный аккаунт

```bash
# Список аккаунтов в ротации лежит в /opt/tla/secrets/accounts.yaml
# формат: { active: tla-primary, pool: [tla-primary, tla-backup-1, tla-backup-2] }

# переключить active на резервный
ssh deploy@vps.example.com
sudo -e /opt/tla/secrets/accounts.yaml  # меняем active на tla-backup-1

# перезапустить listener с новым session-файлом
docker compose -f /opt/tla/infra/docker-compose.prod.yml up -d --force-recreate telethon-listener
```

### 5. AuthKeyError — session-файл недействителен

Session revoked удалённо (через «Active Sessions» в клиенте). Восстановление:

```bash
# старый зашифрованный session-файл уже бесполезен, но бэкап сохранить для post-mortem
cp /opt/tla/data/sessions/tla-primary.session /opt/tla/data/sessions/tla-primary.session.$(date +%Y%m%d-%H%M%S).bak

# сгенерировать новый session через интерактивный скрипт (на рабочей машине, не на VPS)
cd backend/
python scripts/create_session.py --account tla-primary
# вводим код из SMS, 2FA-пароль

# зашифровать и залить на VPS
python scripts/encrypt_session.py tla-primary.session
scp tla-primary.session.enc deploy@vps.example.com:/opt/tla/data/sessions/

# перезапустить listener
ssh deploy@vps.example.com 'docker compose -f /opt/tla/infra/docker-compose.prod.yml restart telethon-listener'
```

### 6. Аккаунт забанен полностью

Возврат номера крайне маловероятен. Действия:

1. Переключиться на резервный аккаунт (шаг 4).
2. Завести новый номер (eSIM / виртуальный) — задача на PM, вне on-call.
3. После восстановления ротации — постмортем: что вызвало бан (объём операций, жалобы, подозрительная активность).

### 7. ChannelPrivateError массово

Админы чатов удалили наш аккаунт. Решение — не технический инцидент, а коммуникационный:

```bash
# получить список источников, которые упали
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec api \
  psql $DATABASE_URL -c "SELECT title, username FROM telegram_sources WHERE is_active=true AND id IN (SELECT DISTINCT source_id FROM raw_messages WHERE processing_status='error' AND received_at > now() - interval '24 hours');"
```

Дезактивировать или заново присоединиться вручную.

## Кого уведомить

- **Немедленно:** Максим (Telegram DM), канал `#incidents`.
- **SEV-1 (все аккаунты упали):** дополнительно — sales-менеджер (бизнес должен знать).

## Предотвращение повторения

- Проверить метрики `requests_per_minute` за 24 часа до инцидента — был ли всплеск?
- Убедиться, что автопауза при 80% от лимита работает (ТЗ FEATURE-10).
- Пересмотреть `PROMPT_VERSION` — не стали ли мы читать больше сообщений?

## Ссылки

- ADR-0003
- ТЗ FEATURE-01, FEATURE-10

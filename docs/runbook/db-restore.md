# Runbook: Восстановление PostgreSQL из бэкапа

**Severity по умолчанию:** SEV-1 (данные потеряны или повреждены). RTO — 2 часа (ТЗ разд. 4.2).

## Где лежат бэкапы

- **Локально на VPS:** `/opt/tla/backups/pg/YYYY-MM-DD/postgres-<timestamp>.dump` (создаётся ежедневно cron'ом в 03:00 UTC, retention 30 дней).
- **Офсайт (S3-совместимое хранилище Hetzner):** `s3://tla-backups/pg/YYYY-MM-DD/`. Retention 30 дней, шифрование SSE-S3.
- **Критичные артефакты (session-файлы, secrets):** отдельное хранилище, см. `docs/security.md`.

Формат — `pg_dump -Fc` (custom format), что позволяет точечное восстановление таблиц.

## Когда применять

- Логическое повреждение данных (неудачная миграция, массовый DELETE, человеческая ошибка).
- Физическое повреждение файлов Postgres (corrupted index, disk failure).
- Проверка RPO/RTO (плановое drill-учение раз в квартал).

## Шаги восстановления

### 1. Зафиксировать момент и остановить запись

```bash
ssh deploy@vps.example.com

# остановить listener и worker'ы, чтобы не накатить новые изменения
docker compose -f /opt/tla/infra/docker-compose.prod.yml stop \
  telethon-listener celery-worker celery-worker-llm bot api
```

Данные в `raw_messages` за время простоя — не теряются на уровне Telegram (Telegram хранит историю), но получение задержится до рестарта listener'а.

### 2. Выбрать бэкап

```bash
# локальные бэкапы
ls -lh /opt/tla/backups/pg/

# берём последний здоровый (обычно вчерашний 03:00 UTC)
BACKUP=/opt/tla/backups/pg/$(date -u -d 'yesterday' +%Y-%m-%d)/postgres-*.dump
ls -lh $BACKUP
```

Если локальный бэкап повреждён / отсутствует — качаем с S3:

```bash
aws s3 ls s3://tla-backups/pg/ --endpoint-url https://fsn1.your-objectstorage.com
aws s3 cp s3://tla-backups/pg/2026-04-23/postgres-20260423-0300.dump /tmp/restore.dump \
  --endpoint-url https://fsn1.your-objectstorage.com
BACKUP=/tmp/restore.dump
```

### 3. Создать параллельную БД для восстановления (не трогаем текущую)

Безопасный путь: восстанавливаем в отдельную БД, проверяем, переключаем сервис на неё.

```bash
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec postgres \
  psql -U postgres -c "CREATE DATABASE tla_restore OWNER tla;"

docker compose -f /opt/tla/infra/docker-compose.prod.yml exec -T postgres \
  pg_restore -U tla -d tla_restore --no-owner --no-privileges < $BACKUP
```

### 4. Чек-лист валидации восстановленной БД

Не переключаем прод пока **все** пункты не зелёные.

```bash
PSQL="docker compose -f /opt/tla/infra/docker-compose.prod.yml exec -T postgres psql -U tla -d tla_restore"

# 1. Все таблицы на месте
$PSQL -c "\dt" | tee /tmp/tables.txt
# Ожидаемо: telegram_sources, raw_messages, keyword_triggers, lead_analysis, sender_profiles,
#           lead_scores, lead_pipeline, audit_log, prompt_versions, alembic_version.

# 2. Количество строк не аномально
$PSQL -c "SELECT 'telegram_sources' AS t, COUNT(*) FROM telegram_sources
          UNION ALL SELECT 'raw_messages', COUNT(*) FROM raw_messages
          UNION ALL SELECT 'lead_analysis', COUNT(*) FROM lead_analysis
          UNION ALL SELECT 'sender_profiles', COUNT(*) FROM sender_profiles;"

# 3. Последняя миграция совпадает с текущим кодом
$PSQL -c "SELECT version_num FROM alembic_version;"
# сверить с backend/alembic/versions/ — должен быть head или не новее, чем код

# 4. Критические инварианты
$PSQL -c "SELECT COUNT(*) FROM raw_messages WHERE source_id NOT IN (SELECT id FROM telegram_sources);"
# должно быть 0

# 5. Свежесть данных (для оценки RPO)
$PSQL -c "SELECT MAX(received_at) FROM raw_messages;"
# сравнить со временем бэкапа
```

### 5. Переключить сервис на восстановленную БД

```bash
# бэкап-переименование текущей битой БД
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec postgres \
  psql -U postgres -c "ALTER DATABASE tla RENAME TO tla_broken_$(date +%s);"

# переименовать восстановленную
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec postgres \
  psql -U postgres -c "ALTER DATABASE tla_restore RENAME TO tla;"

# применить миграции (если код ушёл вперёд бэкапа)
docker compose -f /opt/tla/infra/docker-compose.prod.yml run --rm api alembic upgrade head
```

### 6. Запустить сервисы и наблюдать

```bash
docker compose -f /opt/tla/infra/docker-compose.prod.yml up -d

# проверить здоровье API
curl -fsS https://api.example.com/health

# убедиться, что listener подключился
docker compose -f /opt/tla/infra/docker-compose.prod.yml logs --tail=50 telethon-listener | grep -i "connected\|started"
```

### 7. Re-enqueue сообщений, полученных после бэкапа, но не в БД

После восстановления может быть gap между `MAX(received_at)` в восстановленной БД и реальным текущим временем. Telegram хранит историю — listener при переподключении подхватит offset из `telegram_sources.last_message_at`. Если этого недостаточно — ручной backfill скриптом `backend/scripts/backfill_from_telegram.py --since "<timestamp>"`.

## После инцидента

- Удалить `tla_broken_*` через 7 дней, если восстановление валидно.
- Постмортем в `docs/retro/` — причина, как предотвратить.
- Проверить, что cron бэкапов работает: `sudo crontab -l | grep pg_dump`.
- Убедиться, что S3-аплоад в последний раз прошёл: `aws s3 ls s3://tla-backups/pg/$(date -u +%Y-%m-%d)/`.

## Уведомить

- Максим — Telegram DM + звонок (SEV-1).
- `#incidents`.

## Ссылки

- ТЗ разд. 4.1, 4.2 (backup, RTO/RPO)
- ADR-0006 (почему Postgres — источник истины)

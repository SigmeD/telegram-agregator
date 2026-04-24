# Runbook: Redis недоступен

**Severity по умолчанию:** SEV-2. SEV-1 если Redis down > 30 мин.

## Признаки

- Celery worker'ы логируют `redis.exceptions.ConnectionError` / `TimeoutError`.
- Listener логирует ошибку при `enqueue` после успешного insert в `raw_messages`.
- Метрика `celery_queue_length` недоступна или = 0 при активном трафике.
- `docker compose ps redis` показывает exited / unhealthy.

## Почему это не фатально

Архитектура спроектирована так, что Postgres — источник истины (см. ADR-0006). Даже если Redis потерял очередь, все входящие сообщения записались в `raw_messages` со статусом `pending` и могут быть re-enqueued после восстановления Redis.

## Шаги

### 1. Подтвердить инцидент

```bash
ssh deploy@vps.example.com

docker compose -f /opt/tla/infra/docker-compose.prod.yml ps redis
docker compose -f /opt/tla/infra/docker-compose.prod.yml logs --tail=100 redis
```

### 2. Попытка быстрого восстановления

```bash
# рестарт
docker compose -f /opt/tla/infra/docker-compose.prod.yml restart redis

# проверить, что поднялся
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec redis redis-cli ping
# ожидаемо: PONG
```

Если `PONG` — переход к шагу 5 (re-enqueue зависших).

### 3. Если рестарт не помог — проверить диск и память

```bash
df -h /var/lib/docker              # диск не должен быть заполнен
free -m                            # свободной RAM должно быть > 500 MB
docker compose -f /opt/tla/infra/docker-compose.prod.yml logs redis | grep -i "out of memory\|aof\|rdb"
```

Если OOM — временно увеличить лимит памяти в `docker-compose.prod.yml` (`mem_limit`) или освободить RAM (остановить enrichment worker как наименее критичный).

### 4. Если Redis повреждён и не стартует

```bash
# стоп
docker compose -f /opt/tla/infra/docker-compose.prod.yml stop redis

# бэкап AOF/RDB (для post-mortem)
sudo cp /opt/tla/data/redis/dump.rdb /opt/tla/data/redis/dump.rdb.broken.$(date +%s)
sudo cp /opt/tla/data/redis/appendonly.aof /opt/tla/data/redis/appendonly.aof.broken.$(date +%s) 2>/dev/null || true

# старт с пустым состоянием
sudo rm -f /opt/tla/data/redis/dump.rdb /opt/tla/data/redis/appendonly.aof
docker compose -f /opt/tla/infra/docker-compose.prod.yml up -d redis
```

Очередь теперь пустая. Переходим к шагу 5.

### 5. Re-enqueue зависших сообщений из Postgres ledger

Все `raw_messages` со статусом `pending` или `analyzing`, полученные за последние 7 дней, — кандидаты на повторную постановку в очередь.

```bash
# подсчитать объём
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec api psql $DATABASE_URL -c \
  "SELECT processing_status, COUNT(*) FROM raw_messages WHERE processing_status IN ('pending','analyzing') AND received_at > now() - interval '7 days' GROUP BY processing_status;"

# запустить скрипт re-enqueue
docker compose -f /opt/tla/infra/docker-compose.prod.yml exec api \
  python -m backend.scripts.reenqueue --since "7 days" --statuses pending,analyzing --batch-size 500
```

Скрипт логирует количество отправленных задач. После завершения:

```bash
# проверка — pending должно снижаться по мере работы worker'ов
watch -n 5 "docker compose -f /opt/tla/infra/docker-compose.prod.yml exec -T api psql \$DATABASE_URL -c \"SELECT processing_status, COUNT(*) FROM raw_messages WHERE received_at > now() - interval '7 days' GROUP BY processing_status;\""
```

### 6. Убедиться, что listener и worker'ы подключены к Redis

```bash
docker compose -f /opt/tla/infra/docker-compose.prod.yml restart telethon-listener celery-worker celery-worker-llm
docker compose -f /opt/tla/infra/docker-compose.prod.yml logs --tail=50 celery-worker | grep "Connected"
```

## Как не потерять сообщения на будущих инцидентах

- **Никогда не публиковать в Redis без предварительного commit в `raw_messages`.** Это инвариант ADR-0006, проверяется тестом `tests/integration/test_ingestion_atomicity.py`.
- AOF persistence в Redis включён (`appendonly yes`, `appendfsync everysec`) — снижает окно потерь до ~1 сек.
- Retention `raw_messages` — минимум 30 дней (совпадает с retention бэкапов).

## Уведомить

- Максим — Telegram DM.
- `#incidents`.

## Ссылки

- ADR-0006
- ТЗ FEATURE-03
- `docs/runbook/db-restore.md` (если Postgres тоже пострадал)

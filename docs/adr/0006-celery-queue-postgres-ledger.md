# ADR-0006: Redis-очередь + Postgres как ledger истины

- **Статус:** Accepted
- **Дата:** 2026-04-24
- **Авторы:** команда Telegram Lead Aggregator

## Контекст

Telethon listener должен принять сообщение и как можно быстрее вернуть управление event loop'у, иначе растёт риск пропустить следующий `NewMessage` при пиковых нагрузках (ТЗ FEATURE-03: до 1000 сообщений/мин, latency < 500 мс). Обработка (keyword-фильтр → LLM → scoring) — тяжёлая и может занимать секунды.

Классическая развязка — очередь задач. Но очередь в RAM (Redis без персистенции) означает, что при падении Redis мы теряем все in-flight сообщения, что нарушает критерий «нет потерь сообщений при рестарте сервиса» (ТЗ FEATURE-03).

## Решение

Двухуровневая архитектура хранения:

1. **Postgres — ledger.** При приёме сообщения Telethon listener **синхронно** пишет строку в `raw_messages` с `processing_status='pending'`. Только после успешного commit публикуется задача в Redis-очередь с UUID этой строки. Postgres — источник истины: что было получено.
2. **Redis + Celery — очередь.** Задачи передаются по UUID, payload минимальный. Celery worker при старте обработки атомарно меняет `processing_status` на `analyzing`, при завершении — на `lead`/`not_lead`/`filtered_out`/`error`.

Re-enqueue при инциденте Redis: SQL-запрос `SELECT id FROM raw_messages WHERE processing_status IN ('pending', 'analyzing') AND received_at > now() - interval '7 days'` → повторная публикация в очередь (процедура — `docs/runbook/redis-down.md`).

## Рассмотренные альтернативы

- **Только Redis с AOF persistence.** Восстановление возможно, но Redis AOF не даёт транзакционных гарантий с внешней записью и не хранит историю для аудита/переобучения (нужно по ТЗ разд. 2.3, soft delete и аудит).
- **RabbitMQ + Postgres.** Более надёжная очередь, но оверинжиниринг для текущего объёма; Celery+Redis покрывает потребности и уже в стеке (ТЗ разд. 2.2).
- **Kafka.** Неоправданный операционный оверхед на 10K сообщений/день.

## Последствия

- **Позитивные.** Zero-loss на уровне приёма: падение Redis не теряет сообщения. Аудит-лог «из коробки» — `raw_messages` хранит всё с метаданными.
- **Негативные.** Двойная запись (Postgres commit + Redis push) добавляет ~10 мс latency. Двойной state (`processing_status` + позиция в очереди) требует reconciliation-процедуры.
- **Операционные.** Runbook `redis-down.md` описывает re-enqueue. Миграции `raw_messages` защищены DoD-чеклистом.

## Ссылки

- ТЗ разд. 2.3 (принципиальные решения), FEATURE-03
- `docs/runbook/redis-down.md`

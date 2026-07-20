---
date: 2026-05-12
status: approved
features: [FEATURE-01-core, FEATURE-03-core]
phase: 1
deferred_to_phase_2:
  - account-rotation
  - prometheus-metrics
  - telethon-ping-healthcheck
  - log-rotation
  - auto-join-new-sources
  - reaper-for-orphan-pending
  - startup-backfill
related_tz:
  - TZ_Telegram_Lead_Aggregator.md FEATURE-01 (lines 100-123)
  - TZ_Telegram_Lead_Aggregator.md FEATURE-03 (lines 197-254)
related_br:
  - none-directly (BR-001..050 apply to FEATURE-04/05/06 downstream of this)
---

# FEATURE-03 Listener + FEATURE-01 Session — Phase 1 Design

## Scope

**Phase 1 (this spec):** один Telegram-аккаунт, интерактивный bootstrap session-файла на VPS, listener подписывается на active `telegram_sources`, пишет `raw_messages` + enqueues Celery filter task. Покрывает все 4 кейса error-handling из ТЗ FEATURE-03 + graceful shutdown из FEATURE-01.

**Out of scope (Phase 2, отдельный spec):** ротация 2-3 аккаунтов, Prometheus metrics, Telethon-ping healthcheck, log rotation 100MB, auto-join к новым источникам (FEATURE-02 hookpoint), reaper для orphan `processing_status='pending'`, backfill при рестарте, 7-day uptime/load test.

---

## 1. Architecture Overview

Два новых entry-point'а + пара shared-модулей. Реализация существующих стабов `SessionManager` + `listener.main`. Изменения в compose — один новый service `bootstrap` (profile-gated) + healthcheck.

| Компонент | Файл | Назначение |
|---|---|---|
| Bootstrap CLI (новый) | `backend/src/shared/telegram/bootstrap.py` | One-shot интерактив для генерации `.session.enc`. Запуск через `docker compose ... --profile bootstrap run --rm bootstrap` на VPS. Требует TTY (SMS-prompt). |
| SessionManager (реализация) | `backend/src/shared/telegram/session_manager.py` | Загрузка Fernet-зашифрованного blob'а → `StringSession` → `TelegramClient`. Periodic re-save через background task. |
| Telethon errors (новый) | `backend/src/shared/telegram/errors.py` | Retry-декораторы + dispatch на FloodWait / ChannelPrivate / AuthKey / network. |
| Listener entrypoint (реализация) | `backend/src/listener/main.py` | Connect → source reconciliation → register handler → `run_until_disconnected` → graceful shutdown. |
| Message processing (новый) | `backend/src/listener/processing.py` | Build RawMessage из `events.NewMessage` → DB commit → Celery enqueue. |

**Compose changes:**
- `infra/compose/docker-compose.yml` — новый service `bootstrap` с `profiles: ["bootstrap"]`, `tty: true`, `stdin_open: true`, шарит volume `tlg-session-data`.
- `infra/compose/docker-compose.yml` — `backend-listener.healthcheck` меняется со stub'ового `socket.connect(('redis',6379))` на проверку через `python -c "from shared.telegram.session_manager import session_alive; exit(0 if session_alive() else 1)"`. Phase 1 — простой liveness-чек (TelegramClient exists, не disconnected); Phase 2 поменяем на Telethon ping.

---

## 2. Components

### 2.1 Bootstrap CLI (`shared/telegram/bootstrap.py`)

Entry: `python -m shared.telegram.bootstrap` (через console-script entry point `tlg-bootstrap` если добавим в pyproject).

Flow:
1. Read env: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, `TELETHON_SESSION_KEY` (Fernet, 32 url-safe bytes).
2. `output_path = Path('/var/lib/tlg/sessions/tlg_aggregator.session.enc')`. Если существует → `input("File exists. Overwrite? y/N: ")`, default `N` → exit 0.
3. `client = TelegramClient(StringSession(), api_id, api_hash, device_model="tlg-aggregator", system_version="Linux", app_version="0.1.0")`.
4. `await client.start(phone=lambda: phone, code_callback=lambda: input("Enter SMS code: "), password=lambda: getpass.getpass("Enter 2FA password (or empty): ") or None)`.
5. `session_str = client.session.save()` → `Fernet(key).encrypt(session_str.encode())` → `output_path.write_bytes(blob)` → `output_path.chmod(0o600)`.
6. `print(f"Session saved to {output_path}. Size: {output_path.stat().st_size} bytes.")` → exit 0.

Idempotent: Existing file без overwrite → exit 0 (silent skip). Wrong env (missing TELETHON_SESSION_KEY) → `sys.exit("ERROR: ...")`.

### 2.2 SessionManager (`shared/telegram/session_manager.py`)

Заменяет существующие 3 `raise NotImplementedError`.

```python
class SessionManager:
    def __init__(self, *, session_path: Path, session_key: bytes,
                 api_id: int, api_hash: str) -> None: ...

    async def connect(self) -> TelegramClient:
        # 1. Read encrypted blob from session_path.
        # 2. Fernet(self._session_key).decrypt() → bytes.
        # 3. StringSession(decrypted.decode()).
        # 4. TelegramClient(string_session, api_id, api_hash,
        #                   flood_sleep_threshold=60, request_retries=5,
        #                   device_model=..., system_version="Linux",
        #                   app_version="0.1.0").
        # 5. await client.connect().
        # 6. if not await client.is_user_authorized(): raise AuthKeyError.
        # 7. Start background task self._writer_task = asyncio.create_task(self._writer()).
        # 8. Return client.

    async def disconnect(self) -> None:
        # 1. Cancel self._writer_task.
        # 2. Final self._save_session().
        # 3. await self._client.disconnect().

    async def is_authorized(self) -> bool:
        return await self._client.is_user_authorized()

    async def _writer(self) -> None:
        # Periodic save every 30s. Telethon may update server salts / DC info.
        while True:
            await asyncio.sleep(30)
            await self._save_session()

    async def _save_session(self) -> None:
        session_str = self._client.session.save()
        blob = Fernet(self._session_key).encrypt(session_str.encode())
        self._session_path.write_bytes(blob)
        self._session_path.chmod(0o600)
```

`session_alive()` — module-level helper для healthcheck'а: возвращает True если `_client._sender` инициализирован и не closed (упрощённый liveness check для Phase 1).

### 2.3 Telethon errors (`shared/telegram/errors.py`)

```python
@asynccontextmanager
async def with_telethon_retries(max_attempts: int = 5, base_delay: float = 1.0) -> ...:
    """Async context manager. Catches ConnectionError / asyncio.TimeoutError /
    OSError. Exponential backoff with jitter."""
    for attempt in range(max_attempts):
        try:
            yield
            return
        except (ConnectionError, asyncio.TimeoutError, OSError) as exc:
            if attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning("telethon_retry", attempt=attempt+1, delay=delay, exc=str(exc))
            await asyncio.sleep(delay)


async def handle_telegram_exception(
    exc: Exception, *, source_id: UUID | None, db: AsyncSession,
) -> None:
    """Dispatch by exception type. Mutating side-effects only here."""
    match exc:
        case FloodWaitError():
            logger.warning("telethon_flood_wait", seconds=exc.seconds, source_id=source_id)
            await asyncio.sleep(exc.seconds * 1.1)
        case ChannelPrivateError() | ChatAdminRequiredError():
            await db.execute(
                update(TelegramSource).where(TelegramSource.id == source_id)
                                       .values(is_active=False)
            )
            await db.commit()
            logger.error("admin_notify", source_id=str(source_id),
                         reason="channel_private", exc_type=type(exc).__name__)
        case AuthKeyError() | SessionPasswordNeededError():
            logger.critical("auth_key_invalid", exc_type=type(exc).__name__)
            raise SystemExit(1)
        case _:
            raise  # unknown — propagate to outer handler
```

### 2.4 Listener entry (`listener/main.py`)

Заменяет существующий 45-строчный scaffold. Структура:

```python
async def run() -> None:
    configure_logging()
    settings = get_settings()
    session = SessionManager(
        session_path=Path('/var/lib/tlg/sessions/tlg_aggregator.session.enc'),
        session_key=settings.TELETHON_SESSION_KEY.get_secret_value().encode(),
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH.get_secret_value(),
    )
    db_pool = make_engine(settings.DATABASE_URL.get_secret_value())

    async with with_telethon_retries():
        client = await session.connect()

    source_by_chat_id = await reconcile_sources(client, db_pool)

    @client.on(events.NewMessage(chats=list(source_by_chat_id)))
    async def _handler(event):
        await handle_message(event, db_pool, source_by_chat_id)

    # Signal handlers
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await asyncio.gather(
            client.run_until_disconnected(),
            _wait_for_shutdown(stop_event, client),
        )
    finally:
        await session.disconnect()
        await db_pool.dispose()


async def reconcile_sources(client, db_pool) -> dict[int, TelegramSource]:
    """Resolve chat_id for sources with NULL chat_id. Returns {chat_id: source}."""
    async with db_pool.session() as s:
        rows = (await s.execute(select(TelegramSource).where(TelegramSource.is_active))).scalars().all()
    resolved: dict[int, TelegramSource] = {}
    for src in rows:
        if src.chat_id is None:
            try:
                entity = await client.get_entity(src.username)
                async with db_pool.session() as s:
                    await s.execute(update(TelegramSource).where(TelegramSource.id == src.id)
                                                          .values(chat_id=entity.id))
                    await s.commit()
                src.chat_id = entity.id
                logger.info("source_resolved", username=src.username, chat_id=entity.id)
            except Exception as exc:
                async with db_pool.session() as s:
                    await handle_telegram_exception(exc, source_id=src.id, db=s)
                continue
        resolved[src.chat_id] = src
    return resolved


async def _wait_for_shutdown(stop_event: asyncio.Event, client: TelegramClient) -> None:
    """Block until SIGTERM/SIGINT fires, then trigger client.disconnect() so
    the gathered client.run_until_disconnected() task returns and the outer
    `finally:` block runs full cleanup."""
    await stop_event.wait()
    logger.info("listener_shutdown_signal_received")
    await client.disconnect()
```

### 2.5 Message processing (`listener/processing.py`)

```python
async def handle_message(event, db_pool, source_by_chat_id) -> None:
    try:
        source = source_by_chat_id[event.chat_id]
        msg = RawMessage(
            source_id=source.id,
            telegram_message_id=event.id,
            sender_id=event.sender_id,
            sender_username=getattr(event.sender, "username", None),
            sender_name=_full_name(event.sender),
            message_text=event.raw_text or "",
            has_media=bool(event.media),
            media_type=type(event.media).__name__ if event.media else None,
            reply_to_message_id=event.reply_to_msg_id,
            thread_id=_extract_thread_id(event),
            sent_at=event.date,
            processing_status="pending",
        )
        async with db_pool.session() as s:
            s.add(msg)
            await s.commit()
        try:
            filter_keywords.delay(raw_message_id=str(msg.id))
        except Exception:
            logger.error("celery_enqueue_failed", raw_message_id=str(msg.id), exc_info=True)
    except Exception:
        logger.exception("message_processing_failed", chat_id=event.chat_id)
        # Не raise — listener должен пережить ошибку обработки одного сообщения.
```

Helpers `_full_name(sender)` и `_extract_thread_id(event)` — обработка `None`-кейсов и `event.message.reply_to.forum_topic_id` если доступно.

---

## 3. Data Flow

### 3.1 One-time bootstrap (вручную на VPS)

```
ssh user1@87.242.87.8
cd /home/user1/telegram-aggregator
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/docker-compose.dev.yml \
               --profile bootstrap run --rm bootstrap

  Enter SMS code: <type>
  Enter 2FA password (or empty): <type or enter>
  Session saved to /var/lib/tlg/sessions/tlg_aggregator.session.enc (1247 bytes).

exit 0. Volume tlg-session-data persists file across container lifecycle.
```

### 3.2 Listener startup (каждый CD-deploy)

1. compose стартует `backend-listener` → `python -m listener.main` → `SessionManager.connect()`.
2. Decrypt blob → `StringSession` → `TelegramClient` → `connect()` → `is_user_authorized()`.
3. **Source reconciliation:** `SELECT * FROM telegram_sources WHERE is_active=true`. Для каждой с `chat_id IS NULL` → `await client.get_entity('@username')` → UPDATE.
4. Register `@client.on(events.NewMessage(chats=chat_ids))(handle_message)`.
5. `_writer_task` ticks, `await client.run_until_disconnected()`.

### 3.3 Message processing (live)

```
Telegram MTProto → Telethon decode → handle_message(event)
                                       │
                                       ├─ Build RawMessage
                                       ├─ async with db.session(): s.add(msg); await s.commit()
                                       │     ⤿ exception → log.exception, return (listener жив)
                                       ├─ filter_keywords.delay(raw_message_id=str(msg.id))
                                       │     ⤿ exception → log.error (orphan 'pending', Phase 2 reaper)
                                       └─ return
```

### 3.4 Graceful shutdown

1. SIGTERM → asyncio signal handler → `stop_event.set()`.
2. Helper task wakes up → `await client.disconnect()` → main `run_until_disconnected` returns.
3. `finally:` block → `session.disconnect()` → cancel `_writer_task` → final `_save_session()` → encrypt → write → chmod 600.
4. `db_pool.dispose()` → exit 0.

### 3.5 Failure map

| Exception | Где ловим | Действие |
|---|---|---|
| `FloodWaitError(seconds=N)` | implicit (`flood_sleep_threshold=60` на клиенте) или `handle_telegram_exception` | sleep(N\*1.1), retry |
| `ChannelPrivateError`/`ChatAdminRequiredError` | `handle_telegram_exception` (в `get_entity` или handler) | UPDATE source.is_active=False, log notify_admin, продолжить |
| `AuthKeyError`/`SessionPasswordNeededError` | startup или mid-flight | log.critical → `SystemExit(1)` → docker restart loop → ops видит, делает re-bootstrap |
| `ConnectionError`/`TimeoutError`/`OSError` | `with_telethon_retries(max_attempts=5)` обёртки на `connect()` и `get_entity()` | exp backoff (1→2→4→8→16 sec) + jitter; после 5 → `SystemExit(1)` |
| DB write fail в `handle_message` | `except Exception` в processing | log.exception, return. Сообщение потеряно. |
| Celery enqueue fail (Redis down) | `except Exception` после `commit()` | log.error. Row остаётся 'pending'. Phase 2 reaper. |

---

## 4. Testing

### Unit (быстрые, без внешних deps, под маркером `unit`)

- `tests/unit/test_session_manager.py` — Fernet round-trip happy path + wrong-key fail (`cryptography.fernet.InvalidToken`). `_session_writer` mock asyncio loop. `disconnect()` flow.
- `tests/unit/test_errors.py` — `with_telethon_retries`: 4 fail + 5й success = ok; 5 fails = raise. Backoff timing с monkey-patched `asyncio.sleep`. `handle_telegram_exception` dispatch — каждый exception тип → правильное side-effect.
- `tests/unit/test_processing.py` — fake `events.NewMessage` через `types.SimpleNamespace`. Mock DB session, mock `filter_keywords.delay`. Проверяем: правильный build RawMessage, commit перед delay, exception в commit → log+return.
- `tests/unit/test_bootstrap.py` — monkey-patch `TelegramClient.start()`, `builtins.input`. Проверка: file существует, Fernet-decrypt valid. Overwrite prompt path.

### Integration (testcontainers, маркер `integration`)

- `tests/integration/test_listener_reconciliation.py` — seed sources через `seed_sources`. Mock `client.get_entity` → `types.Channel(id=12345, ...)`. Run reconcile_sources. Проверка: chat_id обновлён, несуществующий → is_active=False.
- `tests/integration/test_listener_handler.py` — full DI listener.run(). Inject fake client. Эмуляция события через callback. Проверка: row в raw_messages + Celery task видна (через eager mode или testcontainers Redis).

### Deferred к Phase 2 / operational

- Реальное TG MTProto — ручной smoke на VPS после bootstrap.
- Load test 1000 msg/min — Phase 2 с Prometheus.
- 7-day uptime — operational, наблюдаем после deploy.

### TDD-порядок per rule #8

1. RED: write failing test
2. GREEN: minimum implementation to pass
3. REFACTOR

Применяется per-function. Начинаем с `SessionManager.connect()` test + impl, потом `errors.with_telethon_retries`, и т.д.

---

## 5. Acceptance Criteria (Phase 1 done)

### Bootstrap + session

- [ ] `docker compose -f base -f dev --profile bootstrap run --rm bootstrap` запрашивает SMS-код, при необходимости 2FA, создаёт `.session.enc` на volume. Существующий файл → prompt overwrite y/N.
- [ ] `SessionManager.connect()` создаёт authorized TelegramClient из existing blob с правильным `TELETHON_SESSION_KEY`. Невалидный ключ → `cryptography.fernet.InvalidToken`.
- [ ] `_session_writer` сохраняет обновлённую session-state каждые 30 сек + при SIGTERM.

### Listener функционально

- [ ] На старте читает `telegram_sources WHERE is_active=true`, резолвит `chat_id` для строк с NULL, UPDATE'ит. Несуществующий канал → is_active=false.
- [ ] Регистрирует `@client.on(events.NewMessage(chats=chat_ids))` handler.
- [ ] Live-сообщение → row в `raw_messages` со всеми полями из ТЗ. `processing_status='pending'`.
- [ ] После commit() вызван `filter_keywords.delay(raw_message_id=...)`.

### Error handling (все 4 кейса ТЗ FEATURE-03)

- [ ] FloodWaitError → `sleep(seconds * 1.1)` → retry.
- [ ] ChannelPrivateError → UPDATE is_active=False, log notify_admin, listener продолжает.
- [ ] AuthKeyError → critical log + SystemExit(1). Docker restart loop.
- [ ] Network errors → 5 попыток exp backoff. После 5 → SystemExit(1).

### Lifecycle

- [ ] SIGTERM → final session-save → encrypt → write → disconnect → exit 0.

### Tests + CI

- [ ] Unit + integration tests зелёные. Coverage ≥80% для `shared/telegram/` и `listener/`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` зелёные.
- [ ] CI `ci-backend` зелёный.

### Production smoke на dev VPS

- [ ] После CD-deploy + ручной bootstrap: `backend-listener-1` в `Up (healthy)`. Не в restart-loop.
- [ ] Реальное сообщение из ≥1 канала из seeds попадает в `raw_messages` за < 5 сек.

---

## 6. Open questions / risks

- **Telethon `get_entity('@username')` rate-limit** при reconciliation 32 источников сразу → возможен FloodWait на старте. `with_telethon_retries` ловит только network errors (`ConnectionError` / `TimeoutError` / `OSError`); FloodWaitError обрабатывает (а) `flood_sleep_threshold=60` на клиенте автоматически (для коротких waits ≤60 сек), (б) `handle_telegram_exception` для долгих waits (≥60 сек, raise'ятся вверх). Митигация на reconciliation-фазе: дополнительный `await asyncio.sleep(0.3)` между `get_entity` вызовами (32 × 300 мс ≈ 10 сек суммарно — приемлемо для startup'а). Если станет проблемой — bulk-resolve через `client.get_dialogs()` сразу всех известных диалогов одним RPC.
- **`filter_keywords` Celery task ещё не реализован** (FEATURE-04, отдельный spec). Phase 1 листенер вызывает `.delay()` — task регистрация уже есть в скаффолде `worker/tasks/filter_keywords.py`. Реальная обработка — следующая фича. Worker должен хотя бы не падать на получении задачи (no-op заглушка достаточна).
- **Bootstrap CLI требует TTY** — compose `--profile bootstrap run --rm` (без `-d`) должен пробрасывать stdin. Тестим в integration test через subprocess + pty или просто документируем как manual SSH-проба.
- **`telegram_sources.chat_id` UPDATE concurrency** — если два listener'а стартуют одновременно (multi-replica в Phase 2), race на reconciliation. В Phase 1 один replica — игнорим.

---

## 7. Source links

- ТЗ: `TZ_Telegram_Lead_Aggregator.md` — FEATURE-01 (lines 100-123), FEATURE-03 (lines 197-254).
- Architecture: `docs/architecture.md`, ADR-0001..0008 (особенно ADR-0008 DB conventions).
- DB schema: `backend/src/shared/db/tables/raw_message.py`, `telegram_source.py`.
- Existing seed: `backend/src/shared/db/seed.py`, `backend/seeds/sources.yaml` (32 источника), `triggers.yaml` (33 keyword'а).
- Settings: `backend/src/shared/config.py:Settings`.
- Brainstorm session: conversation log, 2026-05-12 (this file is the artifact).

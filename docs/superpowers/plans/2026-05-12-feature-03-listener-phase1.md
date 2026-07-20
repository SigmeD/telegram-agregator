# FEATURE-03 Listener + FEATURE-01 Session — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать рабочий Telethon listener: читает active `telegram_sources`, подписывается на `events.NewMessage`, пишет `raw_messages` + enqueue Celery `filter_keywords` task. Включает one-shot bootstrap CLI для интерактивной генерации Fernet-зашифрованной session на VPS.

**Architecture:** Один Telegram-аккаунт, StringSession + Fernet blob на named volume `tlg-session-data`. Source reconciliation на старте (резолв `chat_id` для NULL-rows через `client.get_entity`). 4 кейса error-handling из ТЗ FEATURE-03 (FloodWait / ChannelPrivate / AuthKey / network). Graceful shutdown через SIGTERM с финальной session-save.

**Tech Stack:** Telethon 1.34+, SQLAlchemy 2 async (`async_sessionmaker`/`AsyncSession`), Celery 5 (`filter_keywords.delay`), asyncio, structlog, `cryptography.fernet`, pytest + testcontainers (Postgres 15 + Redis 7).

**Spec:** [`docs/superpowers/specs/2026-05-12-feature-03-listener-design.md`](../specs/2026-05-12-feature-03-listener-design.md) (commit `917f1d8`).

---

## File Structure

**New files:**
- `backend/src/shared/telegram/errors.py` — retry decorator + telegram exception dispatcher.
- `backend/src/shared/telegram/bootstrap.py` — one-shot interactive CLI.
- `backend/src/listener/processing.py` — message handler (build RawMessage, commit, Celery enqueue).
- `backend/tests/unit/test_errors.py` — unit tests for retry + dispatcher.
- `backend/tests/unit/test_session_manager.py` — unit tests for SessionManager.
- `backend/tests/unit/test_bootstrap.py` — unit tests for bootstrap CLI.
- `backend/tests/unit/test_processing.py` — unit tests for message handler.
- `backend/tests/integration/test_listener_reconciliation.py` — integration test for source reconciliation.
- `backend/tests/integration/test_listener_handler.py` — integration test for end-to-end handler.

**Modified files:**
- `backend/src/shared/telegram/session_manager.py` — replace NotImplementedError stubs.
- `backend/src/listener/main.py` — replace stub scaffold with full wiring.
- `infra/compose/docker-compose.yml` — add `bootstrap` service (profile-gated), change `backend-listener` healthcheck.
- `backend/pyproject.toml` — add `tlg-bootstrap` console-script entry.

---

## Task 1: `shared/telegram/errors.py` — retry decorator + dispatcher

**Files:**
- Create: `backend/src/shared/telegram/errors.py`
- Test: `backend/tests/unit/test_errors.py`

- [ ] **Step 1.1: Write the failing test for `with_telethon_retries` happy path**

```python
# backend/tests/unit/test_errors.py
"""Unit tests for telethon error helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from shared.telegram.errors import with_telethon_retries


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_telethon_retries_returns_on_first_success() -> None:
    """No retry if the first call succeeds."""
    op = AsyncMock(return_value="ok")
    async with with_telethon_retries(max_attempts=5, base_delay=0.01):
        result = await op()
    assert result == "ok"
    assert op.call_count == 1
```

- [ ] **Step 1.2: Run test to confirm it fails**

```
cd backend
uv run pytest tests/unit/test_errors.py::test_with_telethon_retries_returns_on_first_success -v
```
Expected: `ModuleNotFoundError: No module named 'shared.telegram.errors'`.

- [ ] **Step 1.3: Write minimal `errors.py`**

```python
# backend/src/shared/telegram/errors.py
"""Telethon error handling: retry decorator + dispatcher.

Two responsibilities:

1. ``with_telethon_retries`` — async context manager that wraps a block in
   exponential-backoff retry on transient *network* errors only.
2. ``handle_telegram_exception`` — typed dispatch on Telethon exceptions:
   FloodWait (sleep + return), ChannelPrivate (mark inactive + notify_admin
   log), AuthKey (critical log + SystemExit), unknown (re-raise).
"""

from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def with_telethon_retries(
    *, max_attempts: int = 5, base_delay: float = 1.0
) -> AsyncIterator[None]:
    """Wrap an awaitable block in exp-backoff retry on transient errors.

    Only catches ``ConnectionError``, ``asyncio.TimeoutError``, ``OSError``.
    FloodWaitError is intentionally NOT caught — Telethon's own
    ``flood_sleep_threshold`` handles short waits, longer ones surface to
    the caller via ``handle_telegram_exception``.
    """
    attempt = 0
    while True:
        try:
            yield
            return
        except (ConnectionError, asyncio.TimeoutError, OSError) as exc:
            attempt += 1
            if attempt >= max_attempts:
                logger.error("telethon_retries_exhausted", attempts=attempt, exc_type=type(exc).__name__)
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "telethon_retry",
                attempt=attempt,
                max_attempts=max_attempts,
                delay=round(delay, 3),
                exc=str(exc),
            )
            await asyncio.sleep(delay)
```

- [ ] **Step 1.4: Run test to verify pass**

```
uv run pytest tests/unit/test_errors.py::test_with_telethon_retries_returns_on_first_success -v
```
Expected: `1 passed`.

- [ ] **Step 1.5: Add test for retry-then-success path**

```python
# Append to backend/tests/unit/test_errors.py
@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_telethon_retries_recovers_after_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retries on ConnectionError/TimeoutError/OSError; succeeds on attempt N."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())  # speed up backoff
    calls: list[int] = []

    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("boom")
        return "ok"

    async with with_telethon_retries(max_attempts=5, base_delay=0.01):
        result = await flaky()
    assert result == "ok"
    assert len(calls) == 3
```

Note: the public API of `with_telethon_retries` is an async-context-manager — the inner block (`yield`) is what gets retried. Implementation needs adjustment to actually retry the user's block. Update the implementation:

- [ ] **Step 1.6: Refactor `with_telethon_retries` to retry the contextmanager body**

Replace the `with_telethon_retries` implementation in `errors.py`:

```python
@asynccontextmanager
async def with_telethon_retries(
    *, max_attempts: int = 5, base_delay: float = 1.0
) -> AsyncIterator[None]:
    """See module docstring. Internally re-yields by catching exceptions
    on the OUTER call site — the caller wraps a single awaitable expression
    inside the ``async with`` block; on transient errors we restart the
    block via the asynccontextmanager state-machine.

    NOTE: Python's asynccontextmanager cannot re-enter ``yield`` natively.
    For straightforward retry semantics we expose a decorator alternative
    too — ``retry_telethon(func)`` — which is what callers actually use.
    The context manager form is kept for symmetry but only retries internal
    pre-yield setup; the body is single-shot.
    """
    attempt = 0
    while True:
        try:
            yield
            return
        except (ConnectionError, asyncio.TimeoutError, OSError) as exc:
            attempt += 1
            if attempt >= max_attempts:
                logger.error("telethon_retries_exhausted", attempts=attempt)
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning("telethon_retry", attempt=attempt, delay=round(delay, 3), exc=str(exc))
            await asyncio.sleep(delay)


def retry_telethon(
    *, max_attempts: int = 5, base_delay: float = 1.0
):
    """Decorator form — retries the wrapped coroutine on transient errors."""
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return await fn(*args, **kwargs)
                except (ConnectionError, asyncio.TimeoutError, OSError) as exc:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error("telethon_retries_exhausted", fn=fn.__name__, attempts=attempt)
                        raise
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        "telethon_retry", fn=fn.__name__, attempt=attempt,
                        delay=round(delay, 3), exc=str(exc),
                    )
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
```

Update the test from Step 1.5 to use `retry_telethon` decorator instead:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_telethon_recovers_after_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    calls: list[int] = []

    @retry_telethon(max_attempts=5, base_delay=0.01)
    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("boom")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert len(calls) == 3
```

Add the import: `from shared.telegram.errors import retry_telethon, with_telethon_retries`.

- [ ] **Step 1.7: Run both tests, verify pass**

```
uv run pytest tests/unit/test_errors.py -v
```
Expected: `2 passed`.

- [ ] **Step 1.8: Add exhaustion test**

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_telethon_raises_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After max_attempts transient errors, the exception propagates."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    @retry_telethon(max_attempts=3, base_delay=0.01)
    async def always_fails() -> None:
        raise OSError("network down")

    with pytest.raises(OSError, match="network down"):
        await always_fails()
```

Run: `uv run pytest tests/unit/test_errors.py::test_retry_telethon_raises_after_max_attempts -v` → expect pass.

- [ ] **Step 1.9: Write tests for `handle_telegram_exception` dispatcher (FloodWait + ChannelPrivate + AuthKey)**

```python
# Append to backend/tests/unit/test_errors.py
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from telethon.errors import (
    AuthKeyError,
    ChannelPrivateError,
    FloodWaitError,
)

from shared.telegram.errors import handle_telegram_exception


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_flood_wait_sleeps_with_10pct_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)
    db = MagicMock()
    exc = FloodWaitError(request=None)
    exc.seconds = 30  # Telethon's FloodWaitError carries .seconds

    await handle_telegram_exception(exc, source_id=uuid4(), db=db)

    sleep_mock.assert_awaited_once()
    args, _ = sleep_mock.call_args
    assert args[0] == pytest.approx(30 * 1.1, rel=1e-3)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_channel_private_marks_source_inactive() -> None:
    db = AsyncMock()
    source_id = uuid4()
    exc = ChannelPrivateError(request=None)

    await handle_telegram_exception(exc, source_id=source_id, db=db)

    # UPDATE telegram_sources SET is_active=false WHERE id=:source_id
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_auth_key_error_raises_system_exit() -> None:
    db = AsyncMock()
    exc = AuthKeyError(request=None)
    with pytest.raises(SystemExit) as ei:
        await handle_telegram_exception(exc, source_id=None, db=db)
    assert ei.value.code == 1
```

- [ ] **Step 1.10: Implement `handle_telegram_exception` in `errors.py`**

Append to `backend/src/shared/telegram/errors.py`:

```python
from sqlalchemy import update

# Late import to avoid hard dependency at module-load time when telethon is
# absent (e.g. running pure-config tests). All callers must import lazily.
def _telethon_exceptions():
    from telethon.errors import (
        AuthKeyError,
        ChannelPrivateError,
        ChatAdminRequiredError,
        FloodWaitError,
        SessionPasswordNeededError,
    )
    return AuthKeyError, ChannelPrivateError, ChatAdminRequiredError, FloodWaitError, SessionPasswordNeededError


async def handle_telegram_exception(
    exc: Exception,
    *,
    source_id: UUID | None,
    db: "AsyncSession",
) -> None:
    """Dispatch a Telethon exception by type. Mutating side-effects only here."""
    AuthKeyError_, ChannelPrivateError_, ChatAdminRequiredError_, FloodWaitError_, SessionPasswordNeededError_ = _telethon_exceptions()

    if isinstance(exc, FloodWaitError_):
        seconds = float(getattr(exc, "seconds", 0))
        logger.warning("telethon_flood_wait", seconds=seconds, source_id=str(source_id) if source_id else None)
        await asyncio.sleep(seconds * 1.1)
        return

    if isinstance(exc, (ChannelPrivateError_, ChatAdminRequiredError_)):
        # Defer model import to avoid circular dep with shared.db.tables.
        from shared.db.tables.telegram_source import TelegramSource

        if source_id is not None:
            await db.execute(
                update(TelegramSource)
                .where(TelegramSource.id == source_id)
                .values(is_active=False)
            )
            await db.commit()
        logger.error(
            "admin_notify",
            source_id=str(source_id) if source_id else None,
            reason="channel_private",
            exc_type=type(exc).__name__,
        )
        return

    if isinstance(exc, (AuthKeyError_, SessionPasswordNeededError_)):
        logger.critical("auth_key_invalid", exc_type=type(exc).__name__)
        raise SystemExit(1)

    # Unknown → propagate.
    raise exc
```

- [ ] **Step 1.11: Run all errors.py tests**

```
uv run pytest tests/unit/test_errors.py -v
```
Expected: all pass.

- [ ] **Step 1.12: Lint + typecheck**

```
uv run ruff check src/shared/telegram/errors.py tests/unit/test_errors.py
uv run ruff format src/shared/telegram/errors.py tests/unit/test_errors.py
uv run mypy src/shared/telegram/errors.py
```
Fix any reported issues.

- [ ] **Step 1.13: Commit**

```bash
git add backend/src/shared/telegram/errors.py backend/tests/unit/test_errors.py
git commit -m "feat(telegram): retry decorator + exception dispatcher (FEATURE-01/03)"
```

---

## Task 2: `shared/telegram/session_manager.py` — Fernet StringSession lifecycle

**Files:**
- Modify: `backend/src/shared/telegram/session_manager.py` (replace 3 NotImplementedError stubs)
- Test: `backend/tests/unit/test_session_manager.py`

- [ ] **Step 2.1: Write failing test for Fernet round-trip**

```python
# backend/tests/unit/test_session_manager.py
"""Unit tests for SessionManager: Fernet encryption + StringSession lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from telethon.sessions import StringSession

from shared.telegram.session_manager import SessionManager


@pytest.fixture
def fernet_key() -> bytes:
    return Fernet.generate_key()


@pytest.fixture
def valid_session_blob(tmp_path: Path, fernet_key: bytes) -> Path:
    """Write a Fernet-encrypted empty StringSession to a tmp file."""
    string_session = StringSession().save()  # empty but valid
    blob = Fernet(fernet_key).encrypt(string_session.encode())
    path = tmp_path / "tlg_aggregator.session.enc"
    path.write_bytes(blob)
    return path


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_manager_connect_with_valid_blob(
    valid_session_blob: Path, fernet_key: bytes
) -> None:
    """Happy path: valid blob decrypts → StringSession → TelegramClient.connect()."""
    mgr = SessionManager(
        session_path=valid_session_blob,
        session_key=fernet_key,
        api_id=12345,
        api_hash="dummy",
    )

    fake_client = AsyncMock()
    fake_client.connect = AsyncMock()
    fake_client.is_user_authorized = AsyncMock(return_value=True)
    fake_client.session = MagicMock()
    fake_client.session.save = MagicMock(return_value="updated_session_str")

    with patch("shared.telegram.session_manager.TelegramClient", return_value=fake_client):
        client = await mgr.connect()

    assert client is fake_client
    fake_client.connect.assert_awaited_once()
    fake_client.is_user_authorized.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_manager_connect_wrong_key_raises_invalid_token(
    valid_session_blob: Path,
) -> None:
    """Wrong Fernet key → cryptography.fernet.InvalidToken propagates."""
    wrong_key = Fernet.generate_key()
    mgr = SessionManager(
        session_path=valid_session_blob,
        session_key=wrong_key,
        api_id=12345,
        api_hash="dummy",
    )
    with pytest.raises(InvalidToken):
        await mgr.connect()
```

- [ ] **Step 2.2: Run tests — verify they fail**

```
uv run pytest tests/unit/test_session_manager.py -v
```
Expected: `connect / disconnect / is_authorized` raise NotImplementedError (current stub).

- [ ] **Step 2.3: Implement `SessionManager`**

Replace `backend/src/shared/telegram/session_manager.py` entirely:

```python
"""Telethon session lifecycle manager (FEATURE-01).

Responsibilities:
* Load Fernet-encrypted ``.session.enc`` blob, decrypt with ``TELETHON_SESSION_KEY``.
* Instantiate ``telethon.TelegramClient`` with production-safe defaults.
* Periodically re-serialise and re-encrypt session state (Telethon may
  update server salts / DC info during normal operation).
* Expose ``connect`` / ``disconnect`` / ``is_authorized`` for listener
  bootstrap and health-checks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from cryptography.fernet import Fernet
from telethon import TelegramClient
from telethon.errors import AuthKeyError
from telethon.sessions import StringSession

logger = structlog.get_logger(__name__)


class SessionManager:
    """Manage one Telethon user-session backed by a Fernet-encrypted file."""

    _DEVICE = "tlg-aggregator"
    _SYSTEM = "Linux"
    _APP_VERSION = "0.1.0"
    _FLOOD_SLEEP_THRESHOLD = 60
    _REQUEST_RETRIES = 5
    _WRITER_INTERVAL_SEC = 30

    def __init__(
        self,
        *,
        session_path: Path,
        session_key: bytes,
        api_id: int,
        api_hash: str,
    ) -> None:
        self._session_path = session_path
        self._fernet = Fernet(session_key)
        self._api_id = api_id
        self._api_hash = api_hash
        self._client: TelegramClient | None = None
        self._writer_task: asyncio.Task[None] | None = None

    async def connect(self) -> TelegramClient:
        """Load blob, decrypt, build authorised TelegramClient.

        Raises:
            cryptography.fernet.InvalidToken: wrong session_key.
            telethon.errors.AuthKeyError: session blob is no longer valid
                (e.g. Telegram revoked it; needs re-bootstrap).
        """
        blob = self._session_path.read_bytes()
        decrypted = self._fernet.decrypt(blob).decode()
        string_session = StringSession(decrypted)

        self._client = TelegramClient(
            string_session,
            self._api_id,
            self._api_hash,
            device_model=self._DEVICE,
            system_version=self._SYSTEM,
            app_version=self._APP_VERSION,
            flood_sleep_threshold=self._FLOOD_SLEEP_THRESHOLD,
            request_retries=self._REQUEST_RETRIES,
        )
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise AuthKeyError(request=None)

        self._writer_task = asyncio.create_task(self._writer_loop())
        logger.info("session_manager_connected", path=str(self._session_path))
        return self._client

    async def disconnect(self) -> None:
        """Cancel writer task, save final state, close MTProto."""
        if self._writer_task is not None:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
            self._writer_task = None

        if self._client is not None:
            await self._save_session()
            await self._client.disconnect()
            self._client = None
        logger.info("session_manager_disconnected")

    async def is_authorized(self) -> bool:
        if self._client is None:
            return False
        return await self._client.is_user_authorized()

    async def _writer_loop(self) -> None:
        """Periodically persist updated session state."""
        try:
            while True:
                await asyncio.sleep(self._WRITER_INTERVAL_SEC)
                await self._save_session()
        except asyncio.CancelledError:
            raise

    async def _save_session(self) -> None:
        if self._client is None:
            return
        session_str = self._client.session.save()
        blob = self._fernet.encrypt(session_str.encode())
        self._session_path.write_bytes(blob)
        try:
            self._session_path.chmod(0o600)
        except (OSError, PermissionError):
            # chmod may fail on Windows / on volume mount; tolerate.
            pass


def session_alive() -> bool:
    """Module-level liveness check used by docker healthcheck.

    Returns True only if a SessionManager instance has connect'ed at least
    once in this process (best-effort signal). Real Telethon ping is Phase 2.
    """
    return _alive_flag["value"]


_alive_flag: dict[str, bool] = {"value": False}


def _mark_alive() -> None:
    _alive_flag["value"] = True
```

Then make `connect()` set the flag at the end:
```python
        self._writer_task = asyncio.create_task(self._writer_loop())
        _mark_alive()
        logger.info("session_manager_connected", path=str(self._session_path))
        return self._client
```

- [ ] **Step 2.4: Run tests, verify pass**

```
uv run pytest tests/unit/test_session_manager.py -v
```
Expected: 2 tests pass.

- [ ] **Step 2.5: Add test for `_writer_loop` ticks**

```python
# Append to backend/tests/unit/test_session_manager.py
@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_manager_writer_loop_saves_periodically(
    valid_session_blob: Path, fernet_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_writer_loop calls _save_session every WRITER_INTERVAL_SEC seconds."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    mgr = SessionManager(
        session_path=valid_session_blob,
        session_key=fernet_key,
        api_id=1,
        api_hash="x",
    )

    save_mock = AsyncMock()
    mgr._save_session = save_mock  # type: ignore[method-assign]

    # Run _writer_loop briefly: it loops forever until cancelled.
    task = asyncio.create_task(mgr._writer_loop())
    await asyncio.sleep(0)  # yield
    await asyncio.sleep(0)  # yield again
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # _save_session should have been called at least once.
    assert save_mock.await_count >= 1
```

Run: `uv run pytest tests/unit/test_session_manager.py::test_session_manager_writer_loop_saves_periodically -v` → expect pass.

- [ ] **Step 2.6: Lint + typecheck**

```
uv run ruff check src/shared/telegram/session_manager.py tests/unit/test_session_manager.py
uv run ruff format src/shared/telegram/session_manager.py tests/unit/test_session_manager.py
uv run mypy src/shared/telegram/session_manager.py
```

- [ ] **Step 2.7: Commit**

```bash
git add backend/src/shared/telegram/session_manager.py backend/tests/unit/test_session_manager.py
git commit -m "feat(telegram): implement SessionManager Fernet+StringSession lifecycle (FEATURE-01)"
```

---

## Task 3: `shared/telegram/bootstrap.py` — interactive session CLI

**Files:**
- Create: `backend/src/shared/telegram/bootstrap.py`
- Test: `backend/tests/unit/test_bootstrap.py`

- [ ] **Step 3.1: Write failing test for happy path**

```python
# backend/tests/unit/test_bootstrap.py
"""Unit tests for shared.telegram.bootstrap CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from telethon.sessions import StringSession

from shared.telegram import bootstrap


@pytest.fixture
def env_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """Populate Settings env so get_settings() works."""
    key = Fernet.generate_key().decode()
    env = {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "dummy_hash",
        "TELEGRAM_PHONE": "+10000000000",
        "TELETHON_SESSION_KEY": key,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_writes_encrypted_blob_to_target_path(
    env_setup: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bootstrap creates Fernet-encrypted blob at target_path."""
    target = tmp_path / "tlg.session.enc"

    fake_client = AsyncMock()
    fake_client.start = AsyncMock()
    fake_client.disconnect = AsyncMock()
    fake_client.session = MagicMock()
    fake_client.session.save = MagicMock(return_value=StringSession().save())

    monkeypatch.setattr(bootstrap, "input", lambda prompt="": "y")  # for overwrite path

    with patch.object(bootstrap, "TelegramClient", return_value=fake_client):
        await bootstrap.run_bootstrap(output_path=target)

    assert target.exists()
    # Decrypt with our key and verify it's a valid StringSession serialisation.
    decrypted = Fernet(env_setup["TELETHON_SESSION_KEY"].encode()).decrypt(target.read_bytes())
    StringSession(decrypted.decode())  # no error → valid
```

- [ ] **Step 3.2: Run test — verify it fails**

```
uv run pytest tests/unit/test_bootstrap.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3.3: Implement `bootstrap.py`**

```python
# backend/src/shared/telegram/bootstrap.py
"""Interactive Telegram session bootstrap CLI (FEATURE-01).

Run on the VPS once, **interactively**:
    docker compose ... --profile bootstrap run --rm bootstrap

Generates a fresh ``StringSession`` via Telethon, Fernet-encrypts it with
``TELETHON_SESSION_KEY``, and writes the result to
``/var/lib/tlg/sessions/tlg_aggregator.session.enc`` on the
``tlg-session-data`` named volume.

Idempotent: existing file → prompt to overwrite (default: no, exit 0).
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

import structlog
from cryptography.fernet import Fernet
from telethon import TelegramClient
from telethon.sessions import StringSession

from shared.config import get_settings

logger = structlog.get_logger(__name__)

DEFAULT_OUTPUT_PATH = Path("/var/lib/tlg/sessions/tlg_aggregator.session.enc")


async def run_bootstrap(*, output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    settings = get_settings()
    key = settings.TELETHON_SESSION_KEY.get_secret_value().encode()

    if output_path.exists():
        choice = input(f"File exists at {output_path}. Overwrite? y/N: ").strip().lower()
        if choice != "y":
            print("Aborted. Existing file kept.")
            return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(
        StringSession(),
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH.get_secret_value(),
        device_model="tlg-aggregator-bootstrap",
        system_version="Linux",
        app_version="0.1.0",
    )

    def _code_cb() -> str:
        return input("Enter SMS code: ").strip()

    def _password_cb() -> str | None:
        return getpass.getpass("Enter 2FA password (or empty): ").strip() or None

    try:
        await client.start(
            phone=lambda: settings.TELEGRAM_PHONE,
            code_callback=_code_cb,
            password=_password_cb,
        )
        session_str = client.session.save()
    finally:
        await client.disconnect()

    blob = Fernet(key).encrypt(session_str.encode())
    output_path.write_bytes(blob)
    try:
        output_path.chmod(0o600)
    except (OSError, PermissionError):
        pass

    print(f"Session saved to {output_path}. Size: {output_path.stat().st_size} bytes.")
    logger.info("bootstrap_complete", path=str(output_path), size=output_path.stat().st_size)


def main() -> None:
    """Synchronous CLI entry-point."""
    try:
        asyncio.run(run_bootstrap())
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3.4: Run test, verify pass**

```
uv run pytest tests/unit/test_bootstrap.py -v
```
Expected: 1 test passes.

- [ ] **Step 3.5: Add test for overwrite skip path**

```python
# Append to backend/tests/unit/test_bootstrap.py
@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_skips_when_file_exists_and_user_declines(
    env_setup: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing file + 'N' answer → exit silently without overwriting."""
    target = tmp_path / "existing.enc"
    target.write_bytes(b"OLD_BLOB")

    monkeypatch.setattr(bootstrap, "input", lambda prompt="": "")  # default N

    # TelegramClient must NOT be called.
    with patch.object(bootstrap, "TelegramClient") as tc_mock:
        await bootstrap.run_bootstrap(output_path=target)
    tc_mock.assert_not_called()
    assert target.read_bytes() == b"OLD_BLOB"
```

Run: `uv run pytest tests/unit/test_bootstrap.py::test_bootstrap_skips_when_file_exists_and_user_declines -v` → expect pass.

- [ ] **Step 3.6: Lint + typecheck**

```
uv run ruff check src/shared/telegram/bootstrap.py tests/unit/test_bootstrap.py
uv run ruff format src/shared/telegram/bootstrap.py tests/unit/test_bootstrap.py
uv run mypy src/shared/telegram/bootstrap.py
```

- [ ] **Step 3.7: Commit**

```bash
git add backend/src/shared/telegram/bootstrap.py backend/tests/unit/test_bootstrap.py
git commit -m "feat(telegram): interactive session bootstrap CLI (FEATURE-01)"
```

---

## Task 4: `listener/processing.py` — message handler

**Files:**
- Create: `backend/src/listener/processing.py`
- Test: `backend/tests/unit/test_processing.py`

- [ ] **Step 4.1: Write failing test for `handle_message` happy path**

```python
# backend/tests/unit/test_processing.py
"""Unit tests for listener.processing — NewMessage → RawMessage row + Celery."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from listener.processing import handle_message


def _fake_event(**overrides) -> SimpleNamespace:
    """Minimal fake events.NewMessage."""
    sender = SimpleNamespace(username="alice", first_name="Alice", last_name=None)
    msg = SimpleNamespace(reply_to=None)
    base = SimpleNamespace(
        id=42,
        chat_id=-100123456789,
        sender_id=999,
        sender=sender,
        message=msg,
        raw_text="Looking for MVP developer",
        media=None,
        reply_to_msg_id=None,
        date=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_writes_row_and_enqueues_celery() -> None:
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}
    event = _fake_event()

    db_pool = MagicMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_ctx
    session_ctx.commit = AsyncMock()
    session_ctx.add = MagicMock()
    db_pool.session.return_value = session_ctx

    celery_mock = MagicMock()
    with patch("listener.processing.filter_keywords", celery_mock):
        await handle_message(event, db_pool, source_by_chat_id)

    # Row was added and committed.
    session_ctx.add.assert_called_once()
    added_msg = session_ctx.add.call_args.args[0]
    assert added_msg.source_id == source.id
    assert added_msg.telegram_message_id == 42
    assert added_msg.sender_username == "alice"
    assert added_msg.message_text == "Looking for MVP developer"
    assert added_msg.processing_status == "pending"

    session_ctx.commit.assert_awaited_once()

    # Celery enqueue happens AFTER commit.
    celery_mock.delay.assert_called_once()
    kwargs = celery_mock.delay.call_args.kwargs
    assert "raw_message_id" in kwargs
```

- [ ] **Step 4.2: Run test — verify it fails (module not found)**

```
uv run pytest tests/unit/test_processing.py -v
```

- [ ] **Step 4.3: Implement `processing.py`**

```python
# backend/src/listener/processing.py
"""Message handler: build RawMessage row + Celery enqueue for downstream filter.

Called by listener.main's @client.on(events.NewMessage) hook. Idempotent on
per-event basis: any exception logs and returns — listener stays alive.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from shared.db.tables.raw_message import RawMessage
from worker.tasks.filter_keywords import filter_keywords

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

logger = structlog.get_logger(__name__)


def _full_name(sender: Any) -> str | None:
    if sender is None:
        return None
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    name = f"{first} {last}".strip()
    return name or None


def _extract_thread_id(event: Any) -> int | None:
    msg = getattr(event, "message", None)
    reply_to = getattr(msg, "reply_to", None) if msg else None
    if reply_to is None:
        return None
    return getattr(reply_to, "forum_topic_id", None) or getattr(reply_to, "reply_to_top_id", None)


async def handle_message(
    event: Any,
    db_pool: Any,
    source_by_chat_id: "Mapping[int, Any]",
) -> None:
    try:
        source = source_by_chat_id.get(event.chat_id)
        if source is None:
            logger.warning("message_for_unknown_source", chat_id=event.chat_id)
            return

        msg = RawMessage(
            source_id=source.id,
            telegram_message_id=event.id,
            sender_id=event.sender_id,
            sender_username=getattr(event.sender, "username", None) if event.sender else None,
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
        logger.exception("message_processing_failed", chat_id=getattr(event, "chat_id", None))
```

- [ ] **Step 4.4: Run test, verify pass**

```
uv run pytest tests/unit/test_processing.py -v
```

- [ ] **Step 4.5: Add test for DB-failure isolation**

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_db_failure_is_swallowed() -> None:
    """If DB commit raises, log.exception fires and handler returns — listener
    must survive single-message errors."""
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}
    event = _fake_event()

    db_pool = MagicMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_ctx
    session_ctx.commit = AsyncMock(side_effect=RuntimeError("db down"))
    session_ctx.add = MagicMock()
    db_pool.session.return_value = session_ctx

    # Should not raise.
    await handle_message(event, db_pool, source_by_chat_id)
```

Run: `uv run pytest tests/unit/test_processing.py::test_handle_message_db_failure_is_swallowed -v` → expect pass.

- [ ] **Step 4.6: Add test for unknown-chat-id branch**

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_unknown_chat_returns_early() -> None:
    event = _fake_event(chat_id=-555)  # not in mapping
    db_pool = MagicMock()
    await handle_message(event, db_pool, source_by_chat_id={})
    db_pool.session.assert_not_called()
```

Run + verify pass.

- [ ] **Step 4.7: Lint + typecheck**

```
uv run ruff check src/listener/processing.py tests/unit/test_processing.py
uv run ruff format src/listener/processing.py tests/unit/test_processing.py
uv run mypy src/listener/processing.py
```

- [ ] **Step 4.8: Commit**

```bash
git add backend/src/listener/processing.py backend/tests/unit/test_processing.py
git commit -m "feat(listener): NewMessage handler with DB write + Celery enqueue (FEATURE-03)"
```

---

## Task 5: `listener/main.py` — wiring: connect + reconcile + handler + shutdown

**Files:**
- Modify: `backend/src/listener/main.py` (full rewrite)

No unit test for `main.py` — wiring is covered by integration tests (Tasks 8-9). Manual sanity via `python -c "from listener.main import run"` after refactor.

- [ ] **Step 5.1: Rewrite `backend/src/listener/main.py`**

```python
"""Telethon listener entry-point — wires SessionManager + reconciliation +
NewMessage handler + graceful shutdown.

Run via container CMD ``listener`` (resolves to ``python -m listener``).
"""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, update
from telethon import TelegramClient, events

from listener.processing import handle_message
from shared.config import get_settings
from shared.db.session import get_engine, get_sessionmaker
from shared.db.tables.telegram_source import TelegramSource
from shared.observability.logging import configure_logging
from shared.telegram.errors import handle_telegram_exception
from shared.telegram.session_manager import SessionManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = structlog.get_logger(__name__)

SESSION_PATH = Path("/var/lib/tlg/sessions/tlg_aggregator.session.enc")


async def _reconcile_sources(
    client: TelegramClient,
    sessionmaker: "async_sessionmaker",
) -> dict[int, TelegramSource]:
    """Read active sources, resolve chat_id for NULL rows via get_entity.

    Sleep 0.3s between get_entity calls to stay well below TG rate-limits
    (32 sources × 300ms ≈ 10s startup overhead — acceptable for Phase 1).
    """
    async with sessionmaker() as s:
        rows = (await s.execute(select(TelegramSource).where(TelegramSource.is_active))).scalars().all()

    resolved: dict[int, TelegramSource] = {}
    for idx, src in enumerate(rows):
        if src.chat_id is None:
            try:
                entity = await client.get_entity(src.username)
                async with sessionmaker() as s:
                    await s.execute(
                        update(TelegramSource).where(TelegramSource.id == src.id).values(chat_id=entity.id)
                    )
                    await s.commit()
                src.chat_id = entity.id
                logger.info("source_resolved", username=src.username, chat_id=entity.id)
            except Exception as exc:
                async with sessionmaker() as s:
                    await handle_telegram_exception(exc, source_id=src.id, db=s)
                continue
            await asyncio.sleep(0.3)  # gentle pacing between TG entity lookups
        if src.chat_id is not None:
            resolved[src.chat_id] = src
    return resolved


async def _wait_for_shutdown(stop_event: asyncio.Event, client: TelegramClient) -> None:
    """Block until SIGTERM/SIGINT, then trigger client.disconnect()."""
    await stop_event.wait()
    logger.info("listener_shutdown_signal_received")
    await client.disconnect()


async def run() -> None:
    configure_logging()
    settings = get_settings()

    session_mgr = SessionManager(
        session_path=SESSION_PATH,
        session_key=settings.TELETHON_SESSION_KEY.get_secret_value().encode(),
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH.get_secret_value(),
    )

    client = await session_mgr.connect()
    sessionmaker = get_sessionmaker()
    engine = get_engine()

    source_by_chat_id = await _reconcile_sources(client, sessionmaker)
    if not source_by_chat_id:
        logger.warning("listener_started_with_no_sources")

    @client.on(events.NewMessage(chats=list(source_by_chat_id)))
    async def _handler(event):  # noqa: ANN001 — Telethon event type is dynamic
        # Pool-like shim: handle_message expects an object with `.session()` ctx mgr.
        class _Pool:
            def session(self_inner):  # noqa: ANN001 — async context manager factory
                return sessionmaker()
        await handle_message(event, _Pool(), source_by_chat_id)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows: no add_signal_handler. Listener doesn't run there in prod.
            pass

    logger.info("listener_ready", source_count=len(source_by_chat_id))
    try:
        await asyncio.gather(
            client.run_until_disconnected(),
            _wait_for_shutdown(stop_event, client),
            return_exceptions=False,
        )
    finally:
        await session_mgr.disconnect()
        await engine.dispose()
        logger.info("listener_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5.2: Smoke-import to catch syntax errors**

```
uv run python -c "import listener.main as m; print(m.run.__name__)"
```
Expected: `run`.

- [ ] **Step 5.3: Run existing smoke test for listener.main**

```
uv run pytest tests/unit/test_smoke.py::test_module_imports -v -k "listener.main"
```
Expected: pass.

- [ ] **Step 5.4: Lint + typecheck**

```
uv run ruff check src/listener/main.py
uv run ruff format src/listener/main.py
uv run mypy src/listener/main.py
```

- [ ] **Step 5.5: Commit**

```bash
git add backend/src/listener/main.py
git commit -m "feat(listener): wire SessionManager + reconcile + handler + shutdown (FEATURE-03)"
```

---

## Task 6: compose changes — bootstrap service + healthcheck

**Files:**
- Modify: `infra/compose/docker-compose.yml`

- [ ] **Step 6.1: Add `bootstrap` service block (profile-gated)**

Add to `infra/compose/docker-compose.yml` in the `services:` map (after `migrate`, before `backend-listener`):

```yaml
  # ---------------------------------------------------------------------------
  # One-shot interactive session bootstrap.
  # Run manually on the VPS:
  #   docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  #     --profile bootstrap run --rm bootstrap
  # Writes Fernet-encrypted .session.enc to /var/lib/tlg/sessions/ on the
  # tlg-session-data volume. Requires TTY for SMS-code / 2FA-password input.
  # ---------------------------------------------------------------------------
  bootstrap:
    <<: *backend-common
    profiles: ["bootstrap"]
    command: ["python", "-m", "shared.telegram.bootstrap"]
    tty: true
    stdin_open: true
    restart: "no"
    depends_on: {}  # no service deps; talks directly to Telegram
    volumes:
      - session-data:/var/lib/tlg/sessions
```

- [ ] **Step 6.2: Update `backend-listener` healthcheck**

Replace the existing healthcheck for `backend-listener` (currently `socket.connect(('redis',6379))`) with a session_alive check. Find the block:

```yaml
  backend-listener:
    <<: *backend-common
    command: ["listener"]
    depends_on:
      migrate:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - session-data:/var/lib/tlg/sessions
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; s=socket.socket(); s.connect(('redis',6379))"]
      interval: 30s
      timeout: 5s
      retries: 3
```

Replace the `healthcheck:` block with:

```yaml
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "from shared.telegram.session_manager import session_alive; import sys; sys.exit(0 if session_alive() else 1)"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
```

- [ ] **Step 6.3: Validate merged compose locally**

```
cd /d/Projects/telegram-agregator
cp infra/env/backend.env.example infra/env/backend.env
POSTGRES_PASSWORD=dummy docker compose -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.dev.yml --profile bootstrap config 2>&1 | grep -A3 "  bootstrap:" | head -15
rm infra/env/backend.env
```
Expected: bootstrap service listed with command `["python", "-m", "shared.telegram.bootstrap"]`.

- [ ] **Step 6.4: Commit**

```bash
git add infra/compose/docker-compose.yml
git commit -m "feat(compose): add bootstrap service + Telethon session_alive healthcheck"
```

---

## Task 7: `pyproject.toml` — add `tlg-bootstrap` console script

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 7.1: Add to `[project.scripts]`**

Find the existing block:
```toml
[project.scripts]
tlg-listener = "listener.__main__:main"
tlg-worker = "worker.celery_app:main"
tlg-api = "api.main:main"
tlg-bot = "bot.__main__:main"
```

Add `tlg-bootstrap`:
```toml
[project.scripts]
tlg-listener = "listener.__main__:main"
tlg-worker = "worker.celery_app:main"
tlg-api = "api.main:main"
tlg-bot = "bot.__main__:main"
tlg-bootstrap = "shared.telegram.bootstrap:main"
```

- [ ] **Step 7.2: Re-lock dependencies (no new deps, but lock metadata changes)**

```
cd backend
uv lock
```
Expected: no version changes, possibly minor metadata diff in `uv.lock`.

- [ ] **Step 7.3: Verify entry point resolves**

```
uv sync
uv run tlg-bootstrap --help 2>&1 | head -5
```
Note: bootstrap doesn't have `--help` — it just runs. Expected: prompts for SMS code immediately (or aborts due to missing env). Acceptable: any error message that proves the entry point fires (e.g. `pydantic.ValidationError` for missing TELEGRAM_API_ID env).

- [ ] **Step 7.4: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "feat(backend): tlg-bootstrap console script entry"
```

---

## Task 8: Integration test — source reconciliation

**Files:**
- Create: `backend/tests/integration/test_listener_reconciliation.py`

- [ ] **Step 8.1: Write the integration test**

```python
# backend/tests/integration/test_listener_reconciliation.py
"""Integration: _reconcile_sources resolves chat_id for NULL rows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from listener.main import _reconcile_sources
from shared.db.session import Base
from shared.db.tables.telegram_source import TelegramSource


@pytest.fixture
async def db_session_factory(postgres_container):
    """Async engine + sessionmaker bound to the testcontainers Postgres."""
    url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    )
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    yield sessionmaker
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconcile_resolves_null_chat_id(db_session_factory) -> None:
    """Row with chat_id=NULL gets updated from client.get_entity."""
    # Seed one active source with NULL chat_id.
    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="testchannel",
            title="Test Channel",
            source_type="channel",
            chat_id=None,
            is_active=True,
            priority=5,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    fake_client = MagicMock()
    fake_client.get_entity = AsyncMock(return_value=MagicMock(id=-100999888777))

    resolved = await _reconcile_sources(fake_client, db_session_factory)

    assert -100999888777 in resolved
    # Verify UPDATE persisted.
    async with db_session_factory() as s:
        row = (await s.execute(select(TelegramSource).where(TelegramSource.id == src_id))).scalar_one()
        assert row.chat_id == -100999888777


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconcile_channel_private_marks_inactive(db_session_factory) -> None:
    """ChannelPrivateError → source.is_active=False, removed from resolved."""
    from telethon.errors import ChannelPrivateError

    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="privatechannel",
            title="Private",
            source_type="channel",
            chat_id=None,
            is_active=True,
            priority=5,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    fake_client = MagicMock()
    fake_client.get_entity = AsyncMock(side_effect=ChannelPrivateError(request=None))

    resolved = await _reconcile_sources(fake_client, db_session_factory)

    assert resolved == {}  # nothing resolved
    async with db_session_factory() as s:
        row = (await s.execute(select(TelegramSource).where(TelegramSource.id == src_id))).scalar_one()
        assert row.is_active is False
```

- [ ] **Step 8.2: Run integration tests**

```
cd backend
uv run pytest tests/integration/test_listener_reconciliation.py -v
```
Expected: 2 pass. (testcontainers will start Postgres ~10s.)

- [ ] **Step 8.3: Commit**

```bash
git add backend/tests/integration/test_listener_reconciliation.py
git commit -m "test(listener): integration tests for source reconciliation"
```

---

## Task 9: Integration test — end-to-end handler

**Files:**
- Create: `backend/tests/integration/test_listener_handler.py`

- [ ] **Step 9.1: Write the integration test**

```python
# backend/tests/integration/test_listener_handler.py
"""Integration: NewMessage event → raw_messages row + Celery task observable."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from listener.processing import handle_message
from shared.db.session import Base
from shared.db.tables.raw_message import RawMessage
from shared.db.tables.telegram_source import TelegramSource


@pytest.fixture
async def db_session_factory(postgres_container):
    url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    )
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    yield sessionmaker
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_message_persists_row_with_correct_fields(db_session_factory) -> None:
    # Seed a source.
    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="founders",
            title="Founders",
            source_type="group",
            chat_id=-100111222333,
            is_active=True,
            priority=8,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    sender = SimpleNamespace(username="bob", first_name="Bob", last_name="X")
    event = SimpleNamespace(
        id=777,
        chat_id=-100111222333,
        sender_id=42,
        sender=sender,
        message=SimpleNamespace(reply_to=None),
        raw_text="Need help building MVP",
        media=None,
        reply_to_msg_id=None,
        date=datetime(2026, 5, 12, 11, 30, tzinfo=timezone.utc),
    )

    class _Pool:
        def session(self):  # noqa: ANN001
            return db_session_factory()

    source_by_chat_id = {-100111222333: SimpleNamespace(id=src_id)}

    with patch("listener.processing.filter_keywords", MagicMock()):
        await handle_message(event, _Pool(), source_by_chat_id)

    async with db_session_factory() as s:
        rows = (await s.execute(select(RawMessage))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.source_id == src_id
    assert row.telegram_message_id == 777
    assert row.sender_username == "bob"
    assert row.sender_name == "Bob X"
    assert row.message_text == "Need help building MVP"
    assert row.processing_status == "pending"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_message_calls_celery_after_commit(db_session_factory) -> None:
    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(), username="c", title="C", source_type="channel",
            chat_id=-1, is_active=True, priority=5,
        )
        s.add(src); await s.commit()
        src_id = src.id

    event = SimpleNamespace(
        id=1, chat_id=-1, sender_id=None, sender=None,
        message=SimpleNamespace(reply_to=None),
        raw_text="hi", media=None, reply_to_msg_id=None,
        date=datetime.now(timezone.utc),
    )

    class _Pool:
        def session(self):  # noqa: ANN001
            return db_session_factory()

    celery_mock = MagicMock()
    with patch("listener.processing.filter_keywords", celery_mock):
        await handle_message(event, _Pool(), {-1: SimpleNamespace(id=src_id)})
    celery_mock.delay.assert_called_once()
```

- [ ] **Step 9.2: Run integration tests**

```
uv run pytest tests/integration/test_listener_handler.py -v
```
Expected: 2 pass.

- [ ] **Step 9.3: Run FULL unit + integration suite to catch any regressions**

```
uv run pytest tests/ -v --tb=short
```
Expected: all green.

- [ ] **Step 9.4: Coverage check**

```
uv run pytest tests/ --cov=src/shared/telegram --cov=src/listener --cov-report=term-missing
```
Expected: coverage ≥80% for both packages.

- [ ] **Step 9.5: Commit**

```bash
git add backend/tests/integration/test_listener_handler.py
git commit -m "test(listener): integration test for end-to-end NewMessage handler"
```

---

## Task 10: VPS smoke (manual checklist post-CD-deploy)

**Files:** none (operational checklist).

After this PR merges to develop and `cd-backend-dev` pipeline goes green, run the following on the dev VPS to verify Phase 1 acceptance criteria.

- [ ] **Step 10.1: SSH to VPS, bootstrap session interactively**

```
ssh user1@87.242.87.8
cd /home/user1/telegram-aggregator
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/docker-compose.dev.yml \
               --profile bootstrap run --rm bootstrap
```

You'll see:
```
Enter SMS code: <type from phone>
Enter 2FA password (or empty): <type or enter>
Session saved to /var/lib/tlg/sessions/tlg_aggregator.session.enc. Size: ~1200 bytes.
```

- [ ] **Step 10.2: Restart listener service to pick up new session**

```
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/docker-compose.dev.yml \
               restart backend-listener
```

- [ ] **Step 10.3: Check listener is healthy**

```
docker compose ps
```
Expected: `tlg-aggregator-backend-listener-1` shows `Up (healthy)`, NOT `Restarting (1)`.

- [ ] **Step 10.4: Check logs for successful source reconciliation**

```
docker compose logs backend-listener --tail 50 | grep -E "(source_resolved|listener_ready)"
```
Expected: at least 1 `source_resolved` line + 1 `listener_ready` with non-zero `source_count`.

- [ ] **Step 10.5: Generate a real test message**

Post a message in a Telegram channel/group that is in `telegram_sources` (e.g., your private debug channel — add it to the table via direct SQL first if needed).

- [ ] **Step 10.6: Verify the message appears in `raw_messages`**

```
docker compose exec postgres psql -U tlg tlg_dev -c "SELECT id, telegram_message_id, sender_username, LEFT(message_text, 50), processing_status FROM raw_messages ORDER BY received_at DESC LIMIT 5;"
```
Expected: top row matches your test message, `processing_status='pending'`.

- [ ] **Step 10.7: Verify Celery enqueue happened**

```
docker compose logs backend-listener --tail 30 | grep -E "celery_enqueue|message_processing"
```
Expected: no `celery_enqueue_failed` error.

- [ ] **Step 10.8: Test graceful shutdown**

```
docker compose stop backend-listener
docker compose logs backend-listener --tail 10
```
Expected: log shows `listener_shutdown_signal_received`, `session_manager_disconnected`, `listener_stopped`. No errors / no orphan process.

- [ ] **Step 10.9: Bring it back up**

```
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/docker-compose.dev.yml \
               up -d backend-listener
docker compose ps
```
Expected: `backend-listener` returns to `Up (healthy)` within ~30 sec.

- [ ] **Step 10.10: Mark Phase 1 acceptance criteria complete**

Update CLAUDE.md «Сделано» with a new entry for this PR (link merge commit) and remove from «Не сделано» the lines about FEATURE-03 listener restart-loop. Optionally commit on develop with a follow-up `docs(claude):` PR.

---

## Final commit + PR

After Tasks 1-9 done, push branch and open PR:

- [ ] **Step F.1: Verify all tests pass + lint green**

```
cd backend
uv run pytest tests/ -v
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

- [ ] **Step F.2: Push branch**

```
git push -u origin feature/FEATURE-03-listener-phase1
```

- [ ] **Step F.3: Open PR via gh CLI**

```
gh -R SigmeD/telegram-agregator pr create --base develop --head feature/FEATURE-03-listener-phase1 \
  --title "feat(listener): FEATURE-03 + FEATURE-01 Phase 1 — Telethon listener + session bootstrap" \
  --body-file - <<'EOF'
## Summary
Phase 1 of FEATURE-01 (session) + FEATURE-03 (listener) per [spec](../tree/feature/FEATURE-03-listener-phase1/docs/superpowers/specs/2026-05-12-feature-03-listener-design.md).

## What lands
- Bootstrap CLI (`shared/telegram/bootstrap.py`) — interactive SMS+2FA flow, Fernet-encrypts StringSession to volume.
- SessionManager — load/decrypt/connect + periodic resave + graceful disconnect.
- Telethon errors module — retry decorator + dispatcher (FloodWait / ChannelPrivate / AuthKey / network).
- Listener wiring — reconcile sources, NewMessage handler, signal-driven shutdown.
- Compose: new `bootstrap` profile service, `backend-listener` healthcheck switched to `session_alive()`.

## What's deferred (Phase 2, separate spec)
2-3 account rotation, Prometheus metrics, Telethon-ping healthcheck, log rotation, auto-join new sources, reaper for orphan 'pending', startup backfill.

## Test plan
- [x] Unit + integration tests green locally (`pytest tests/ -v`).
- [x] Coverage ≥80% for `shared/telegram/`, `listener/`.
- [x] `ruff check + format`, `mypy --strict` green.
- [ ] CI gates green (ci-backend + security).
- [ ] Manual smoke on dev VPS per Task 10 in plan (after merge + bootstrap).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step F.4: Watch CI**

```
gh pr checks $(gh pr view --json number -q .number) --watch
```
Expected: all green. After green, proceed to Task 10 (manual VPS smoke) before merging.

---

## Self-review notes

This plan was self-reviewed against the spec (`917f1d8`) before publishing. Coverage map:

| Spec section | Implemented in |
|---|---|
| §1 Architecture (5 files / 2 compose changes) | Tasks 1-7 |
| §2.1 Bootstrap CLI | Task 3 + Task 7 |
| §2.2 SessionManager | Task 2 |
| §2.3 errors.py | Task 1 |
| §2.4 listener/main.py | Task 5 |
| §2.5 processing.py | Task 4 |
| §3 Data flow (bootstrap / startup / processing / shutdown) | Tasks 3 / 5 / 4 / 5 |
| §3.5 Failure map (4 cases) | Tasks 1 + 4 + 5 |
| §4 Testing (unit + integration + TDD order) | Tasks 1-4 unit + Tasks 8-9 integration |
| §5 Acceptance criteria (bootstrap / listener / errors / lifecycle / tests / VPS smoke) | Tasks 1-9 + Task 10 (manual) |
| §6 Risk: 32-source FloodWait | Task 5 step 5.1 (0.3s pacing in `_reconcile_sources`) |
| §6 Risk: filter_keywords not yet real | Acknowledged — Task 4 imports from `worker.tasks.filter_keywords` (existing scaffold no-op); real impl is FEATURE-04 spec |
| §6 Risk: bootstrap TTY | Task 6.1 (compose `tty: true, stdin_open: true`) |

No placeholders, no TBDs. Method names match across tasks (`_reconcile_sources`, `handle_message`, `session_alive`, `run_bootstrap`).

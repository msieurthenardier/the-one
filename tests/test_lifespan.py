"""FastAPI lifespan integration tests.

Verifies that the PTY session registry is drained on shutdown — the
``shutdown_drain`` hook wired into ``the_one.interfaces.web.app.lifespan``
must cancel the reaper task and close any live sessions before the DB
connection closes.

Pattern: enter ``lifespan(app)`` directly via ``async with``. The
codebase's async-test idiom is ``httpx.AsyncClient + ASGITransport``
(see ``tests/test_db_api.py`` and ``tests/test_provider_api.py``); we
don't need HTTP routing here, but the lifespan context manager itself
runs the ``init_db`` + ``migrate_json_to_sqlite`` startup tasks, which
need a writable data dir.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from the_one.platform.pty import PtySession


class _MockPtySession(PtySession):
    """In-memory ``PtySession`` for the lifespan drain test."""

    def __init__(self) -> None:
        self._alive = True
        self._last_activity = time.monotonic()
        self.close_count = 0

    async def start(self) -> None:  # pragma: no cover — unused here
        pass

    async def send(self, input: str, timeout: float = 30.0) -> bytes:  # noqa: A002
        return b""

    async def close(self) -> None:
        self.close_count += 1
        self._alive = False

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def last_activity(self) -> float:
        return self._last_activity


@pytest.fixture(autouse=True)
async def _registry_cleanup():
    """Reset registry state after each test (in case the lifespan path
    didn't fully drain)."""
    from the_one.tools._session_registry import _clear_for_test

    yield
    await _clear_for_test()


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the global ``settings`` at a tmp data dir AND reset the
    db-connection singleton so the lifespan's ``init_db`` /
    ``migrate_json_to_sqlite`` start with a clean slate.

    ``Settings`` reads env vars at import time (module-level instance),
    so ``setenv`` alone is insufficient — we have to mutate the live
    ``settings.data_dir`` field.
    """
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # The DB singleton may already be open from a prior test; force
    # reconnect against the new path.
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    # Best-effort: close any connection the lifespan opened so the next
    # test's ``init_db`` reopens against a fresh path.
    monkeypatch.setattr(db_connection, "_connection", None)


async def test_lifespan_drains_session_registry(_isolated_data_dir) -> None:
    """Sessions registered inside the lifespan context are closed on
    exit, and the reaper task is cancelled."""
    from the_one.interfaces.web.app import app, lifespan
    from the_one.tools import _session_registry as reg
    from the_one.tools._session_registry import (
        count_for_agent,
        new_session_id,
        register,
    )

    sessions = [_MockPtySession() for _ in range(3)]

    async with lifespan(app):
        for session in sessions:
            await register("test-agent", new_session_id(), session, ttl_seconds=300)
        assert await count_for_agent("test-agent") == 3
        assert reg._reaper_task is not None

    # After lifespan exit:
    # - Every session was closed.
    # - Registry is empty (drained).
    # - Reaper task was cancelled and reset to None.
    for session in sessions:
        assert session.close_count == 1
    assert await count_for_agent("test-agent") == 0
    assert reg._reaper_task is None


async def test_lifespan_drain_with_no_sessions_is_clean(
    _isolated_data_dir,
) -> None:
    """Lifespan exit with no sessions / no reaper must not raise."""
    from the_one.interfaces.web.app import app, lifespan
    from the_one.tools import _session_registry as reg

    async with lifespan(app):
        # Don't register anything.
        assert reg._reaper_task is None

    # Still clean afterward.
    assert reg._reaper_task is None

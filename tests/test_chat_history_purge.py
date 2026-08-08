"""App-layer daily-purge tests (M13 F03 L3).

Covers the ``app.py`` wiring around the pure sweep service:
  - ``_run_purge_sweep_and_evict`` evicts swept ids from the in-memory
    ``_sessions`` registry and awaits ``agent.aclose()`` (three-phase,
    reaper shape);
  - ``_purge_due`` reads the DB and reports due-ness (closes the coverage
    gap a prior review flagged — a regression here would otherwise be
    swallowed by the DD6 startup guard);
  - one ``_chat_history_purge_loop`` catch-up iteration sweeps a due DB;
  - the ``POST /api/_test/purge-sweep`` test seam is dual-gated (403 off).
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession
from the_one.db.repositories import (
    AppMetadataRepository,
    ChatSessionRepository,
    SQLiteAgentStore,
)
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.retention import LAST_PURGE_KEY


class _MockAgent:
    """Minimal Agent stand-in that records aclose() calls."""

    def __init__(self) -> None:
        self.aclose = AsyncMock()


def _aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture
async def app_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated data dir + fresh app-level DB connection.

    Mirrors test_web_session_reaper._isolated_data_dir: redirect the app's
    ``get_connection`` to a per-test SQLite file, and reset ``_sessions`` so
    eviction assertions start clean.
    """
    import the_one.interfaces.web.app as app_mod
    from the_one.config import settings
    from the_one.db import connection as db_connection
    from the_one.db import init_db
    from the_one.db.connection import get_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    monkeypatch.setattr(app_mod, "_sessions", {})
    monkeypatch.setattr(app_mod, "_chat_history_purge_task", None)

    await init_db()
    conn = await get_connection()
    yield app_mod, conn
    monkeypatch.setattr(db_connection, "_connection", None)


async def test_run_purge_sweep_and_evict_evicts_swept_keeps_survivor(app_db) -> None:
    """A seeded _sessions entry whose row is swept is evicted and its
    agent.aclose() awaited; an entry whose row survives is left."""
    app_mod, conn = app_db
    store = SQLiteAgentStore(conn)
    chat_repo = ChatSessionRepository(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=7))

    aged = _aged_iso(30)
    recent = datetime.now(timezone.utc).isoformat()
    await chat_repo.create(
        ChatSession(id="aged-1", agent_name="a", created_at=aged, updated_at=aged)
    )
    await chat_repo.create(
        ChatSession(id="recent-1", agent_name="a", created_at=recent, updated_at=recent)
    )

    aged_agent = _MockAgent()
    recent_agent = _MockAgent()
    app_mod._sessions["aged-1"] = app_mod.Session(id="aged-1", agent=aged_agent, created=aged)
    app_mod._sessions["recent-1"] = app_mod.Session(
        id="recent-1", agent=recent_agent, created=recent
    )

    result = await app_mod._run_purge_sweep_and_evict()

    assert result["ids"] == ["aged-1"]
    assert "aged-1" not in app_mod._sessions
    assert "recent-1" in app_mod._sessions
    aged_agent.aclose.assert_awaited_once()
    recent_agent.aclose.assert_not_awaited()


async def test_purge_due_against_real_connection(app_db) -> None:
    """_purge_due reads the DB: True when absent / aged ≥24h, False when
    recently set. Drives the path directly so a regression is caught rather
    than swallowed by the loop's DD6 guard."""
    app_mod, conn = app_db
    meta = AppMetadataRepository(conn)

    # Absent → due.
    assert await app_mod._purge_due() is True

    # Aged 25h → due.
    await meta.set(LAST_PURGE_KEY, (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat())
    assert await app_mod._purge_due() is True

    # Just now → not due.
    await meta.set(LAST_PURGE_KEY, datetime.now(timezone.utc).isoformat())
    assert await app_mod._purge_due() is False


async def test_purge_loop_catch_up_sweeps_due_db(app_db) -> None:
    """One _chat_history_purge_loop catch-up pass sweeps a due DB: the loop
    runs _maybe_purge on entry before its first sleep, so a due aged row is
    deleted shortly after the task starts."""
    app_mod, conn = app_db
    store = SQLiteAgentStore(conn)
    chat_repo = ChatSessionRepository(conn)
    await store.save(AgentConfig(name="a", chat_history_retention_days=7))
    aged = _aged_iso(30)
    await chat_repo.create(
        ChatSession(id="aged-1", agent_name="a", created_at=aged, updated_at=aged)
    )

    task = asyncio.create_task(app_mod._chat_history_purge_loop())
    try:
        swept = False
        for _ in range(100):
            await asyncio.sleep(0.01)
            if not await chat_repo.list("a"):
                swept = True
                break
        assert swept, "catch-up pass did not sweep the due aged row"
        # last_purge_at advanced.
        assert await AppMetadataRepository(conn).get(LAST_PURGE_KEY) is not None
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# ── Endpoint gating ───────────────────────────────────────────────────────


@pytest.fixture
async def client(tmp_path: Path):
    """Test client over the api router with an isolated DB (mirrors
    test_db_api.client)."""
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_key = Fernet.generate_key()
    test_encryptor = Encryptor(test_key, key_path=tmp_path / "test.key")

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
            yield c

    await conn.close()


async def test_purge_sweep_endpoint_403_when_dev_mode_off(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dev_mode off → 403 regardless of the env flag."""
    from the_one.config import settings

    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setenv("THE_ONE_PURGE_SWEEP_TEST_ENDPOINT", "1")
    resp = await client.post("/api/_test/purge-sweep")
    assert resp.status_code == 403


async def test_purge_sweep_endpoint_403_when_env_flag_unset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dev_mode on but env flag unset → still 403 (dual gate)."""
    from the_one.config import settings

    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.delenv("THE_ONE_PURGE_SWEEP_TEST_ENDPOINT", raising=False)
    resp = await client.post("/api/_test/purge-sweep")
    assert resp.status_code == 403

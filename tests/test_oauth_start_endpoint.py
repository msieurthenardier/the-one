"""Tests for the FastAPI ``/api/oauth/start`` route (F5 L5)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.mcp import _pool


@pytest.fixture(autouse=True)
async def _clear_pool():
    """Reset the F4 pool between tests so eviction-counts don't bleed."""
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture
async def client_and_repo(tmp_path):
    """FastAPI client + DB-backed repo with one seeded source."""
    db_path = tmp_path / "start-endpoint.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    await repo.create(
        MCPSource(
            id="src-start-1",
            name="Source for /oauth/start",
            type="streamable-http",
            config={"url": "https://api.example.com/mcp"},
        )
    )

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, repo

    await conn.close()


async def test_start_400_when_dcr_credentials_absent(client_and_repo) -> None:
    """A3 — POST returns 400 with the canonical "Configure manual
    registration or use a DCR-supporting AS" message when the source has
    no ``dcr_credentials`` populated.
    """
    c, _repo = client_and_repo
    resp = await c.post(
        "/api/oauth/start",
        json={"source_id": "src-start-1", "chat_session_id": "cs-x"},
    )
    assert resp.status_code == 400
    assert "DCR" in resp.json()["detail"]


async def test_start_404_on_unknown_source(client_and_repo) -> None:
    """A3 — 404 when source_id is not in the repo."""
    c, _repo = client_and_repo
    resp = await c.post(
        "/api/oauth/start",
        json={"source_id": "src-no-such", "chat_session_id": "cs-x"},
    )
    assert resp.status_code == 404
    assert "src-no-such" in resp.json()["detail"]


async def test_start_schedules_drive_flow_and_evicts_pool(client_and_repo) -> None:
    """A3 — happy path: 202 + ``status=started``, the F4 pool entry for the
    source is evicted, and the background _drive_flow task is scheduled.

    We patch ``httpx.AsyncClient`` inside the endpoint so the real network
    request is captured rather than sent.
    """
    c, repo = client_and_repo
    src = await repo.get("src-start-1")
    src.secrets["dcr_credentials"] = {
        "client_id": "manual-cid-1",
        "auth_endpoint": "https://example.com/authorize",
        "token_endpoint": "https://example.com/token",
    }
    await repo.update(src)

    # Seed a fake pool entry (just inject — don't acquire) for the source.
    # Eviction should remove it.
    fake_entry = _pool._RegistryEntry(
        ttl_seconds=300,
        evict_event=asyncio.Event(),
        client_ready=asyncio.Event(),
    )

    async def _noop_worker() -> None:
        await fake_entry.evict_event.wait()

    fake_entry.client_ready.set()  # so any awaiters return immediately
    fake_entry.worker = asyncio.create_task(_noop_worker())
    _pool._pool[("agent-A", "src-start-1")] = fake_entry
    _pool._pool[("agent-B", "src-start-1")] = fake_entry  # both should be evicted

    captured: dict = {}

    class _StubAsyncClient:
        def __init__(self, *args, **kwargs):
            captured.setdefault("init_kwargs", []).append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["payload"] = kwargs.get("json")

            # Simulate flow success without actually invoking the SDK.
            class _Resp:
                status_code = 200

            return _Resp()

    # Use start/stop on the patcher rather than ``with`` so the patch
    # remains active while the background task runs (the route schedules
    # _drive_flow on a Task that may execute after the response returns).
    patcher = patch("the_one.interfaces.web.api.httpx.AsyncClient", _StubAsyncClient)
    patcher.start()
    try:
        resp = await c.post(
            "/api/oauth/start",
            json={
                "source_id": "src-start-1",
                "chat_session_id": "cs-1",
                "tool_call_id": "tc-1",
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "started"
        assert body["source_id"] == "src-start-1"

        # Pool entries for src-start-1 evicted (both agents).
        assert ("agent-A", "src-start-1") not in _pool._pool
        assert ("agent-B", "src-start-1") not in _pool._pool

        # Wait briefly for the background task to fire its post()
        for _ in range(50):
            if captured.get("url"):
                break
            await asyncio.sleep(0.02)
        assert captured.get("url") == "https://api.example.com/mcp"
        payload = captured.get("payload")
        assert payload and payload.get("method") == "initialize"
    finally:
        patcher.stop()

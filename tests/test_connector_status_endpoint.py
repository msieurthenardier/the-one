"""Backend tests for M11 F17 L5 — connector-connection-status.

Covers:
  A. ``GET /api/connectors/{id}/status`` endpoint:
     - connected shape (warm entry, is_alive=True)
     - cold shape (no warm entry)
     - error shape (failure set, _connect_error_store populated)

  B. ``_get_account_status_snapshot`` in ``_pool.py``:
     - no entry → disconnected
     - entry connecting (client_ready not set) → connecting
     - entry warm + is_alive True → connected
     - entry warm + is_alive False → disconnected
     - entry with failure → error

  C. ``_connection_relevant_changed`` in ``api.py``:
     - secrets change → True
     - intents change → True
     - presence change → True
     - label-only change → False

  D. Save-warm background trigger (≥1-agent gate; label-only no-op):
     - PUT with relevant change + attached agent → background task spawned
     - PUT with label-only change + attached agent → no task spawned

  E. ``_map_connect_error`` in ``api.py``:
     - PrivilegedIntentsRequired (direct) → portal link
     - PrivilegedIntentsRequired (as __cause__) → portal link
     - LoginFailure → no link, bad-token copy
     - Generic exception → no link, generic copy

All tests use DI/code-side stubs (no env-var seams, no live connections).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.connectors import _pool as pool_mod
from the_one.connectors._pool import (
    _ACCOUNT_POOL_AGENT_SLOT,
    _StatusSnapshot,
    _get_account_status_snapshot,
)
from the_one.connectors.base import DoctorReport, SessionKey
from the_one.connectors.errors import ConnectorConnectionError
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.models import Connector
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import (
    _connect_error_store,
    _connection_relevant_changed,
    _map_connect_error,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _clear_pool_after_each_test():
    """Reset pool + registry state between tests."""
    yield
    await pool_mod._clear_for_test()
    restore_to_baseline_for_test()
    # Clear the connect-error store between tests.
    _connect_error_store.clear()


@pytest.fixture
async def client(tmp_path):
    """HTTP test client with isolated DB and test encryptor."""
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    test_encryptor = Encryptor(test_key, key_path=key_path)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
        patch("the_one.db.connection.get_connection", return_value=conn),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


async def _create_account(client: AsyncClient, **kwargs) -> str:
    """Helper: POST a stub connector and return its id."""
    payload = {
        "name": kwargs.get("name", "Test Connector"),
        "type": "stub",
        "config": kwargs.get("config", {}),
        "secrets": kwargs.get("secrets", {}),
    }
    r = await client.post("/api/connectors", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# Simple stub client and plugin used across tests.
class _StubClient:
    def __init__(self, alive: bool = True, application_id: int | None = None) -> None:
        self._alive = alive
        # Mirrors DiscordClient.application_id — present on connected clients,
        # None for pre-READY or non-Discord clients. Test stubs opt in.
        self.application_id = application_id

    def is_alive(self) -> bool:
        return self._alive


class _StubPlugin:
    next_alive: bool = True

    async def connect(self, account, encryptor):  # noqa: ANN001
        return _StubClient(alive=type(self).next_alive)

    async def disconnect(self, client):  # noqa: ANN001
        client._alive = False

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="stub probe ok", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
        )


@pytest.fixture(autouse=True)
def _register_stub():
    """Register the stub plugin type for every test in this module."""
    register_for_test("stub", _StubPlugin)
    yield


# ---------------------------------------------------------------------------
# A. GET /api/connectors/{id}/status — endpoint shapes
# ---------------------------------------------------------------------------


async def test_status_endpoint_returns_404_for_unknown_account(client: AsyncClient):
    """Status endpoint returns 404 when the account row doesn't exist."""
    r = await client.get("/api/connectors/nosuchid/status")
    assert r.status_code == 404


async def test_status_endpoint_cold_returns_disconnected(client: AsyncClient):
    """Cold pool (no warm entry) → state=disconnected, alive=False."""
    account_id = await _create_account(client, name="Cold Connector")
    r = await client.get(f"/api/connectors/{account_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "disconnected"
    assert body["alive"] is False
    assert body["last_error"] is None
    assert body["last_error_link"] is None


async def test_status_endpoint_warm_returns_connected(client: AsyncClient):
    """Warm entry with is_alive()=True → state=connected, alive=True."""
    account_id = await _create_account(client, name="Warm Connector")

    # Inject a warm entry directly (pool's _load_account needs a DB conn
    # that the client fixture patches, but the pool module's own
    # get_connection is separate — simpler to inject directly).
    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    client_obj = _StubClient(alive=True)
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        client=client_obj,
    )
    entry.client_ready.set()
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    r = await client.get(f"/api/connectors/{account_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "connected"
    assert body["alive"] is True
    assert body["last_error"] is None

    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_endpoint_warm_includes_application_id(client: AsyncClient):
    """Warm connected entry whose client exposes application_id → field appears in response.

    M11 F17 L5 fix: a connected bot's application_id (public OAuth2 client id)
    must appear in the status response so the frontend can render the invite URL
    without a manual Validate step. The value is returned as a string to avoid
    JS safe-integer overflow on large Discord snowflakes.
    """
    account_id = await _create_account(client, name="Discord Bot")

    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    client_obj = _StubClient(alive=True, application_id=123456789012345678)
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        client=client_obj,
    )
    entry.client_ready.set()
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    r = await client.get(f"/api/connectors/{account_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "connected"
    assert body["application_id"] == "123456789012345678"

    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_endpoint_cold_application_id_is_null(client: AsyncClient):
    """Cold connector (no warm entry) → application_id is null in the response."""
    account_id = await _create_account(client, name="Cold Bot")
    r = await client.get(f"/api/connectors/{account_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "disconnected"
    assert body["application_id"] is None


async def test_status_endpoint_warm_no_application_id_returns_null(client: AsyncClient):
    """Warm entry whose client does NOT expose application_id → null (not an error)."""
    account_id = await _create_account(client, name="No-AppId Bot")

    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    # _StubClient with application_id=None simulates a client that doesn't expose
    # the attribute or is pre-READY (getattr fallback returns None).
    client_obj = _StubClient(alive=True, application_id=None)
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        client=client_obj,
    )
    entry.client_ready.set()
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    r = await client.get(f"/api/connectors/{account_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "connected"
    assert body["application_id"] is None

    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_snapshot_warm_alive_includes_application_id():
    """_get_account_status_snapshot reads application_id from warm connected client."""
    key = (_ACCOUNT_POOL_AGENT_SLOT, "app-id-account")
    client_obj = _StubClient(alive=True, application_id=987654321098765432)
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        client=client_obj,
    )
    entry.client_ready.set()
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    snap = await _get_account_status_snapshot("app-id-account")
    assert snap.state == "connected"
    assert snap.application_id == 987654321098765432

    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_snapshot_disconnected_application_id_is_none():
    """_get_account_status_snapshot returns application_id=None when alive=False."""
    key = (_ACCOUNT_POOL_AGENT_SLOT, "dead-appid-account")
    client_obj = _StubClient(alive=False, application_id=111222333)
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        client=client_obj,
    )
    entry.client_ready.set()
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    snap = await _get_account_status_snapshot("dead-appid-account")
    assert snap.state == "disconnected"
    # application_id is suppressed for non-alive clients (pre-READY window
    # or gateway drop). The invite should only render when the bot is live.
    assert snap.application_id is None

    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_endpoint_error_shape(client: AsyncClient):
    """No warm entry + _connect_error_store populated → state=error with error fields.

    This is the PrivilegedIntentsRequired scenario: save-warm connect fails,
    the entry is popped from the pool, and the error is written to
    _connect_error_store. The status endpoint must surface state=error (not
    "disconnected") so the operator sees the actionable message and portal link.
    """
    account_id = await _create_account(client, name="Error Connector")
    # Simulate a failed warm recorded by _save_warm_background — no pool entry.
    portal_link = "https://discord.com/developers/applications"
    _connect_error_store[account_id] = {
        "message": "PrivilegedIntentsRequired: missing intent",
        "action_link": portal_link,
    }

    r = await client.get(f"/api/connectors/{account_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "error"
    assert body["last_error"] is not None
    assert body["last_error_link"] == portal_link


# ---------------------------------------------------------------------------
# B. _get_account_status_snapshot — pool snapshot shapes
# ---------------------------------------------------------------------------


async def test_status_snapshot_no_entry_returns_disconnected():
    """No warm entry → disconnected, alive=False."""
    snap = await _get_account_status_snapshot("no-such-account")
    assert snap.state == "disconnected"
    assert snap.alive is False
    assert snap.last_error is None


async def test_status_snapshot_warm_alive_returns_connected():
    """Warm entry with is_alive()=True → connected."""
    key = (_ACCOUNT_POOL_AGENT_SLOT, "alive-account")
    client_obj = _StubClient(alive=True)
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        client=client_obj,
    )
    entry.client_ready.set()
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    snap = await _get_account_status_snapshot("alive-account")
    assert snap.state == "connected"
    assert snap.alive is True

    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_snapshot_warm_not_alive_returns_disconnected():
    """Warm entry with is_alive()=False → disconnected."""
    key = (_ACCOUNT_POOL_AGENT_SLOT, "dead-account")
    client_obj = _StubClient(alive=False)
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        client=client_obj,
    )
    entry.client_ready.set()
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    snap = await _get_account_status_snapshot("dead-account")
    assert snap.state == "disconnected"
    assert snap.alive is False

    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_snapshot_failure_entry_returns_error():
    """Entry with failure set → error; last_error/link passed through."""
    # Inject a pool entry with failure directly.
    key = (_ACCOUNT_POOL_AGENT_SLOT, "fail-account")
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
        failure=ConnectorConnectionError("bad token"),
    )
    entry.client_ready.set()  # Set so we don't hang; failure is set too.
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    snap = await _get_account_status_snapshot(
        "fail-account",
        last_error="Bad token error",
        last_error_link="https://discord.com/developers/applications",
    )
    assert snap.state == "error"
    assert snap.alive is False
    assert snap.last_error == "Bad token error"
    assert snap.last_error_link == "https://discord.com/developers/applications"

    # Cleanup
    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_status_snapshot_connecting_returns_connecting():
    """Entry whose client_ready is not set yet → connecting."""
    key = (_ACCOUNT_POOL_AGENT_SLOT, "connecting-account")
    entry = pool_mod._RegistryEntry(
        ttl_seconds=1800,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
    )
    # client_ready NOT set → mid-connect
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    snap = await _get_account_status_snapshot("connecting-account")
    assert snap.state == "connecting"
    assert snap.alive is False

    # Cleanup
    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


# ---------------------------------------------------------------------------
# C. _connection_relevant_changed
# ---------------------------------------------------------------------------


def _make_connector(**overrides) -> Connector:
    """Build a minimal Connector for comparison tests."""
    base = {
        "id": "test-id",
        "name": "Test",
        "type": "stub",
        "config": {"intents": {"message_content": True}, "presence": {}},
        "secrets": {"BOT_TOKEN": "token123"},
    }
    base.update(overrides)
    return Connector.model_validate(base)


def test_connection_relevant_changed_secrets_change():
    """Secrets change → relevant."""
    old = _make_connector(secrets={"BOT_TOKEN": "old-token"})
    new = _make_connector(secrets={"BOT_TOKEN": "new-token"})
    assert _connection_relevant_changed(old, new) is True


def test_connection_relevant_changed_intents_change():
    """config.intents change → relevant."""
    old = _make_connector(config={"intents": {"message_content": True}})
    new = _make_connector(config={"intents": {"message_content": False}})
    assert _connection_relevant_changed(old, new) is True


def test_connection_relevant_changed_presence_change():
    """config.presence change → relevant."""
    old = _make_connector(config={"presence": {}})
    new = _make_connector(config={"presence": {"name": "Playing games", "type": "playing"}})
    assert _connection_relevant_changed(old, new) is True


def test_connection_relevant_changed_label_only():
    """Name-only change → not relevant."""
    old = _make_connector(name="Old Name")
    new = _make_connector(name="New Name")
    assert _connection_relevant_changed(old, new) is False


def test_connection_relevant_changed_non_connection_config():
    """Non-connection config change (e.g. routing or always_listen) → not relevant."""
    old = _make_connector(config={"always_listen": False})
    new = _make_connector(config={"always_listen": True})
    assert _connection_relevant_changed(old, new) is False


def test_connection_relevant_changed_no_change():
    """Identical connectors → not relevant."""
    c = _make_connector()
    assert _connection_relevant_changed(c, c) is False


# ---------------------------------------------------------------------------
# D. Save-warm gate: ≥1-agent gate; label-only no-op
# ---------------------------------------------------------------------------


async def test_save_warm_triggered_on_relevant_change_with_agent(client: AsyncClient):
    """PUT with connection-relevant change + attached agent → background task fires.

    We can't directly observe asyncio.create_task in the handler, so we
    patch ``_save_warm_background`` and verify it's scheduled.
    """
    account_id = await _create_account(
        client,
        name="Warm Bot",
        secrets={"BOT_TOKEN": "original-token"},
    )

    # Simulate an attached agent by patching SQLiteAgentStore.list_by_connector.
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"

    task_spawned = []

    async def _fake_bg(aid):
        task_spawned.append(aid)

    with (
        patch(
            "the_one.interfaces.web.api.SQLiteAgentStore.list_by_connector",
            new_callable=AsyncMock,
            return_value=[mock_agent],
        ),
        patch("the_one.interfaces.web.api._save_warm_background", side_effect=_fake_bg),
    ):
        r = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "Warm Bot",
                "type": "stub",
                "config": {},
                "secrets": {"BOT_TOKEN": "new-token"},
            },
        )
    assert r.status_code == 200
    # Give the event loop a tick to schedule the task.
    await asyncio.sleep(0)
    assert account_id in task_spawned, "Background warm was not triggered"


async def test_save_warm_not_triggered_on_label_only_change(client: AsyncClient):
    """PUT with name-only change → no background task, even with an attached agent."""
    account_id = await _create_account(
        client,
        name="Label Bot",
        secrets={"BOT_TOKEN": "stable-token"},
    )

    mock_agent = MagicMock()
    task_spawned = []

    async def _fake_bg(aid):
        task_spawned.append(aid)

    with (
        patch(
            "the_one.interfaces.web.api.SQLiteAgentStore.list_by_connector",
            new_callable=AsyncMock,
            return_value=[mock_agent],
        ),
        patch("the_one.interfaces.web.api._save_warm_background", side_effect=_fake_bg),
    ):
        r = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "Label Bot — Updated",
                "type": "stub",
                "config": {},
                "secrets": {"BOT_TOKEN": "__MASKED__"},
            },
        )
    assert r.status_code == 200
    await asyncio.sleep(0)
    assert task_spawned == [], "Background warm should NOT have fired for label-only change"


async def test_save_warm_not_triggered_with_no_attached_agents(client: AsyncClient):
    """PUT with relevant change but 0 attached agents → no background task."""
    account_id = await _create_account(
        client,
        name="Cold Bot",
        secrets={"BOT_TOKEN": "old-token"},
    )

    task_spawned = []

    async def _fake_bg(aid):
        task_spawned.append(aid)

    with (
        patch(
            "the_one.interfaces.web.api.SQLiteAgentStore.list_by_connector",
            new_callable=AsyncMock,
            return_value=[],  # No attached agents.
        ),
        patch("the_one.interfaces.web.api._save_warm_background", side_effect=_fake_bg),
    ):
        r = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "Cold Bot",
                "type": "stub",
                "config": {},
                "secrets": {"BOT_TOKEN": "new-token"},
            },
        )
    assert r.status_code == 200
    await asyncio.sleep(0)
    assert task_spawned == [], "Background warm should NOT fire with 0 agents"


# ---------------------------------------------------------------------------
# E. _map_connect_error — error mapping + __cause__ traversal
# ---------------------------------------------------------------------------


def test_map_connect_error_privileged_intents_direct():
    """PrivilegedIntentsRequired as the direct exception → portal link."""
    try:
        import discord.errors as de
    except ImportError:
        pytest.skip("discord SDK not installed")

    exc = de.PrivilegedIntentsRequired(shard_id=0)
    result = _map_connect_error(exc)
    assert "PrivilegedIntentsRequired" in result["message"]
    assert result["action_link"] == "https://discord.com/developers/applications"


def test_map_connect_error_privileged_intents_as_cause():
    """PrivilegedIntentsRequired wrapped in ConnectorConnectionError → portal link."""
    try:
        import discord.errors as de
    except ImportError:
        pytest.skip("discord SDK not installed")

    inner = de.PrivilegedIntentsRequired(shard_id=0)
    outer = ConnectorConnectionError("connect failed")
    outer.__cause__ = inner
    result = _map_connect_error(outer)
    assert "PrivilegedIntentsRequired" in result["message"]
    assert result["action_link"] == "https://discord.com/developers/applications"


def test_map_connect_error_login_failure():
    """LoginFailure → bad-token copy, no action link."""
    try:
        import discord.errors as de
    except ImportError:
        pytest.skip("discord SDK not installed")

    inner = de.LoginFailure("Improper token has been passed")
    exc = ConnectorConnectionError("connect failed")
    exc.__cause__ = inner
    result = _map_connect_error(exc)
    assert "token" in result["message"].lower()
    assert result["action_link"] is None


def test_map_connect_error_generic():
    """Generic exception → one-liner, no action link."""
    exc = RuntimeError("something went wrong")
    result = _map_connect_error(exc)
    assert "RuntimeError" in result["message"]
    assert result["action_link"] is None


def test_map_connect_error_cause_chain_depth():
    """Walks the full __cause__ chain to the innermost exception."""
    try:
        import discord.errors as de
    except ImportError:
        pytest.skip("discord SDK not installed")

    innermost = de.PrivilegedIntentsRequired(shard_id=0)
    middle = ConnectorConnectionError("mid")
    middle.__cause__ = innermost
    outer = RuntimeError("outer")
    outer.__cause__ = middle
    result = _map_connect_error(outer)
    assert "PrivilegedIntentsRequired" in result["message"]
    assert result["action_link"] == "https://discord.com/developers/applications"

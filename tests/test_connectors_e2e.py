"""End-to-end regression baseline for the connector subsystem (mission 10 flight 1).

This file's `test_e2e_full_lifecycle` is the canonical answer to "does the
connector subsystem work end-to-end?" Future flights MUST keep this passing.
"""

from __future__ import annotations

import aiosqlite
import pytest

from the_one.config import settings
from the_one.connectors import _pool as pool_mod
from the_one.connectors._pool import (
    _clear_for_test as _pool_clear_for_test,
)
from the_one.connectors._pool import (
    _evict_all_for_account,
    _reap_once,
    agent_acquire,
    shutdown_drain,
)
from the_one.connectors._stub import StubClient, StubPlugin
from the_one.connectors.base import (
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
)
from the_one.connectors.errors import ConnectorConnectionError
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.connection import get_connection
from the_one.db.models import Connector
from the_one.db.repositories import ConnectorRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import get_encryptor


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level state before AND after each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_and_registry():
    """Empty pool, reset registry to production baseline. Pairs with the
    stub-state fixture for full per-test isolation."""
    yield
    await _pool_clear_for_test()
    restore_to_baseline_for_test()


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """Per-test sqlite DB at tmp_path. Mirrors `tests/test_lifespan.py:_isolated_data_dir`.

    `get_connection()` in `the_one.db.connection` returns a module-level
    SINGLETON keyed only on first call — not on `settings.db_path`. The
    session-wide `THE_ONE_DATA_DIR` env var (set in `tests/conftest.py`)
    pins the singleton to the session tmp_dir at first use. To get per-test
    isolation we MUST also null `_connection` so the next `get_connection()`
    re-opens against the patched `settings.data_dir`.

    The encryptor cache (`the_one/encryption.py:get_encryptor`) is keyed on
    the resolved path, so per-`tmp_path` isolation is automatic there — no
    cache reset needed.
    """
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # The pool's `get_connection()` resolves db_path as `settings.data_dir /
    # "the-one.db"`. Apply schema to that exact path (NOT a side file like
    # `e2e.db`), otherwise the singleton opens a fresh DB with no tables.
    db_path = settings.db_path

    # Apply schema with a direct connection (bypasses the cache).
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    await conn.close()

    # CRITICAL: null the connection singleton so the next get_connection()
    # call (e.g. from the pool's `_load_account` or from `_seed_stub_account`)
    # opens against this test's tmp_path.
    monkeypatch.setattr(db_connection, "_connection", None)

    yield db_path

    # Close the connection that this test opened so aiosqlite's per-connection
    # `_connection_worker_thread` shuts down on the still-running event loop.
    # Without this, the worker thread outlives the loop teardown and emits
    # `RuntimeError: Event loop is closed` from `call_soon_threadsafe`.
    # `monkeypatch` will restore the prior `_connection` value next; we close
    # FIRST so the close runs against the current loop.
    if db_connection._connection is not None:
        await db_connection.close_connection()


async def _seed_stub_account(account_id: str = "acct-e2e") -> Connector:
    """Helper: persist a stub-typed Connector via the repository."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorRepository(conn, encryptor)
    account = Connector(
        id=account_id,
        name="E2E Test Bot",
        type="stub",
        config={"some": "config"},
        secrets={"BOT_TOKEN": "test-token-xyz"},
    )
    await repo.create(account)
    return account


async def test_e2e_full_lifecycle(isolated_db) -> None:
    """The regression baseline. Flights 2-10 inherit this; it must keep passing."""
    # 1. Persist a stub-typed connector account.
    await _seed_stub_account()

    # 2. Register the stub plugin into the connector registry.
    register_for_test("stub", StubPlugin)

    # 3. Acquire — triggers plugin.connect().
    client = await agent_acquire("agent-e2e", "acct-e2e")
    assert isinstance(client, StubClient)
    assert client.is_alive()
    assert StubPlugin.connect_calls == [("acct-e2e", "stub")]

    # 4. Simulate inbound.
    envelope = InboundEnvelope(
        platform="stub",
        account_id="acct-e2e",
        channel_id="chan-1",
        thread_id=None,
        peer_id="peer-x",
        peer_name="Peer X",
        text="hello",
        raw={},
    )
    StubPlugin.push_inbound(envelope)
    assert len(StubPlugin.inbound_records) == 1
    assert StubPlugin.inbound_records[0].text == "hello"

    # 5. Simulate outbound (Flight 4 will produce these via the platform-send tool).
    target = OutboundTarget(channel_id="chan-1")
    StubPlugin.record_outbound(target, "agent reply")
    assert StubPlugin.outbound_records == [(target, "agent reply")]

    # 6. Age the pool entry; verify reaper evicts.
    entry = pool_mod._pool[("agent-e2e", "acct-e2e")]
    entry.last_activity = 0.0  # ancient
    expired = await _reap_once()
    assert ("agent-e2e", "acct-e2e") in expired
    assert pool_mod._pool == {}
    assert StubPlugin.disconnect_calls == [client]
    assert not client.is_alive()  # disconnect set _alive = False

    # 7. shutdown_drain returns cleanly even on empty pool.
    await shutdown_drain()
    assert pool_mod._reaper_task is None
    assert pool_mod._shutting_down is True

    # The autouse `_clear_pool_and_registry` fixture resets _shutting_down
    # for the next test.


async def test_e2e_doctor_probe_returns_default_success(isolated_db) -> None:
    """Without setting doctor_response, doctor returns a DoctorReport with status='ok'."""
    account = await _seed_stub_account()
    plugin = StubPlugin()
    encryptor = get_encryptor(settings.data_dir)
    report = await plugin.doctor(account, encryptor)
    assert report.status == "ok"
    assert "stub" in report.message.lower()
    assert StubPlugin.doctor_calls == [("acct-e2e", "stub")]


async def test_e2e_doctor_probe_returns_configured_response(isolated_db) -> None:
    """Setting doctor_response makes doctor() return it verbatim."""
    account = await _seed_stub_account()
    StubPlugin.doctor_response = DoctorReport(
        status="failed",
        message="simulated failure",
        details={"reason": "test"},
    )
    plugin = StubPlugin()
    encryptor = get_encryptor(settings.data_dir)
    report = await plugin.doctor(account, encryptor)
    assert report.status == "failed"
    assert report.message == "simulated failure"
    assert report.details == {"reason": "test"}


async def test_e2e_connect_failure_propagates_to_acquire_caller(isolated_db) -> None:
    """Setting connect_should_fail makes acquire re-raise the configured exception."""
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    StubPlugin.connect_should_fail = ConnectorConnectionError("simulated connect failure")

    with pytest.raises(ConnectorConnectionError, match="simulated connect failure"):
        await agent_acquire("agent-e2e", "acct-e2e")

    # Pool empty after failure (idempotent pop).
    assert pool_mod._pool == {}


async def test_e2e_multiple_agents_on_same_account_reap_together(isolated_db) -> None:
    """Two agents on one account → two warm entries; _evict_all_for_account flushes both."""
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    c1 = await agent_acquire("agent-a", "acct-e2e")
    c2 = await agent_acquire("agent-b", "acct-e2e")
    assert StubPlugin.connect_calls == [
        ("acct-e2e", "stub"),
        ("acct-e2e", "stub"),
    ]
    assert len(pool_mod._pool) == 2

    await _evict_all_for_account("acct-e2e")

    assert pool_mod._pool == {}
    assert len(StubPlugin.disconnect_calls) == 2
    assert not c1.is_alive()
    assert not c2.is_alive()

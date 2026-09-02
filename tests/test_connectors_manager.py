"""Tests for ``the_one.connectors.manager`` — pairing codes + listener
lifecycle (DD-1, DD-3). Mission 23 Flight 2 Leg 1.
"""

from __future__ import annotations

import asyncio

import pytest

from the_one.connectors import registry
from the_one.connectors.manager import ConnectorManager, get_manager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.models import Connector
from the_one.encryption import Encryptor, get_encryptor


@pytest.fixture(autouse=True)
def _reset_stub_and_registry():
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    registry.register_for_test("stub", StubPlugin())
    yield
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    set_manager(None)


@pytest.fixture
def encryptor(tmp_path) -> Encryptor:
    return get_encryptor(tmp_path)


def _account(account_id: str = "acc-1") -> Connector:
    return Connector(id=account_id, name="Test", type="stub")


# ── pairing codes ──────────────────────────────────────────────────────


def test_generate_and_consume_pairing_code() -> None:
    mgr = ConnectorManager()
    code = mgr.generate_pairing_code("conn-1")
    assert mgr.consume_pairing_code("conn-1", code) is True


def test_consume_pairing_code_wrong_code_fails() -> None:
    mgr = ConnectorManager()
    mgr.generate_pairing_code("conn-1")
    assert mgr.consume_pairing_code("conn-1", "wrong") is False


def test_consume_pairing_code_is_one_time() -> None:
    mgr = ConnectorManager()
    code = mgr.generate_pairing_code("conn-1")
    assert mgr.consume_pairing_code("conn-1", code) is True
    # Second use of the same code fails silently.
    assert mgr.consume_pairing_code("conn-1", code) is False


def test_consume_pairing_code_expires(monkeypatch) -> None:
    import time as time_mod

    mgr = ConnectorManager()
    code = mgr.generate_pairing_code("conn-1")
    # Advance monotonic time past the 10-minute TTL (patched on the
    # ``time`` module itself — ``manager.py`` calls ``time.monotonic()``
    # off the same module object).
    real_now = time_mod.monotonic()
    monkeypatch.setattr(time_mod, "monotonic", lambda: real_now + 700)
    assert mgr.consume_pairing_code("conn-1", code) is False


def test_consume_pairing_code_unknown_connector_fails() -> None:
    mgr = ConnectorManager()
    assert mgr.consume_pairing_code("no-such-connector", "anything") is False


def test_pairing_race_first_wins_second_silent() -> None:
    """Two peers submitting the same live code — first wins, second gets
    nothing (the code is consumed atomically; no await between check and
    delete)."""
    mgr = ConnectorManager()
    code = mgr.generate_pairing_code("conn-1")
    first = mgr.consume_pairing_code("conn-1", code)
    second = mgr.consume_pairing_code("conn-1", code)
    assert (first, second) == (True, False)


# ── listener lifecycle ──────────────────────────────────────────────────


async def test_start_connects_and_registers_client(encryptor) -> None:
    mgr = ConnectorManager(poll_interval=0.01)
    account = _account()
    mgr.start(account, encryptor)
    await asyncio.sleep(0.05)
    assert mgr.client_for(account.id) is not None
    assert StubPlugin.connect_calls == [account.id]
    await mgr.drain()


async def test_start_is_idempotent(encryptor) -> None:
    mgr = ConnectorManager(poll_interval=0.01)
    account = _account()
    mgr.start(account, encryptor)
    mgr.start(account, encryptor)  # second call is a no-op
    await asyncio.sleep(0.05)
    assert StubPlugin.connect_calls == [account.id]
    await mgr.drain()


async def test_stop_unknown_connector_id_is_idempotent() -> None:
    mgr = ConnectorManager()
    await mgr.stop("does-not-exist")  # must not raise


async def test_stop_stops_the_listener_task(encryptor) -> None:
    mgr = ConnectorManager(poll_interval=0.01)
    account = _account()
    mgr.start(account, encryptor)
    await asyncio.sleep(0.05)
    assert mgr.client_for(account.id) is not None
    await mgr.stop(account.id)
    assert mgr.client_for(account.id) is None
    # Idempotent — stopping again is a no-op.
    await mgr.stop(account.id)


async def test_manager_reconnects_after_client_goes_dead(encryptor) -> None:
    """Stub-driven reconnect: flipping ``is_alive()`` False triggers the
    manager's supervisor loop to disconnect and reconnect with backoff."""
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    account = _account()
    mgr.start(account, encryptor)
    await asyncio.sleep(0.05)
    assert len(StubPlugin.connect_calls) == 1

    StubPlugin.mark_dead(account.id)
    # Give the supervisor loop time to notice, disconnect, back off, and
    # reconnect.
    await asyncio.sleep(0.2)
    assert len(StubPlugin.connect_calls) >= 2
    assert mgr.client_for(account.id) is not None
    await mgr.drain()


async def test_manager_backs_off_on_connect_failure(encryptor) -> None:
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    account = _account()
    StubPlugin.connect_should_fail = RuntimeError("boom")
    mgr.start(account, encryptor)
    await asyncio.sleep(0.05)
    assert mgr.client_for(account.id) is None
    assert len(StubPlugin.connect_calls) >= 1
    await mgr.drain()


async def test_start_all_skips_disabled_starts_others(encryptor) -> None:
    """AC-7 (Mission 23 Flight 3 Leg 2, DD-6): a row with
    ``config.enabled == False`` gets no listener at boot; enabled and
    absent-key rows start. ``start()`` itself stays dumb — the skip is
    ``start_all``'s own guard."""
    mgr = ConnectorManager(poll_interval=0.01)
    absent = Connector(id="absent", name="Absent", type="stub")
    enabled = Connector(id="enabled", name="Enabled", type="stub", config={"enabled": True})
    disabled = Connector(id="disabled", name="Disabled", type="stub", config={"enabled": False})

    class _FakeRepo:
        async def list(self) -> list[Connector]:
            return [absent, enabled, disabled]

    await mgr.start_all(_FakeRepo(), encryptor)
    await asyncio.sleep(0.05)

    assert mgr.client_for("absent") is not None
    assert mgr.client_for("enabled") is not None
    assert mgr.client_for("disabled") is None
    assert set(StubPlugin.connect_calls) == {"absent", "enabled"}
    await mgr.drain()


def test_get_set_manager_accessor() -> None:
    assert get_manager() is None
    mgr = ConnectorManager()
    set_manager(mgr)
    assert get_manager() is mgr
    set_manager(None)
    assert get_manager() is None

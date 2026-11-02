"""Route tests for the controlled-disconnect test seam (Mission 23 Flight 3
Leg 3, DD-7): ``POST /api/_test/discord/sever``. Dual-gated like the stub
seams (``settings.dev_mode`` AND ``THE_ONE_DISCORD_TEST_ENDPOINT=1``); error
taxonomy is repo-existence-first (the ``generate_connector_pairing_code``
idiom) so ``client_for``'s identical ``None`` for "never started" and
"mid-backoff" never has to carry the 404/409 distinction alone.

Mirrors ``tests/test_connector_routes.py``'s fixture shapes (``isolated_db``,
bare-router ``client``) rather than importing them, so this file stays
readable standalone.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._discord_gateway_fixture import FakeGateway
from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.discord.plugin import DiscordPlugin
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin

pytestmark = pytest.mark.usefixtures("isolated_db")


@pytest.fixture(autouse=True)
async def _reset():
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    yield
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    set_manager(None)


@pytest.fixture
async def client():
    test_app = shared_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers()
    ) as c:
        yield c


@pytest.fixture
def discord_gate(monkeypatch: pytest.MonkeyPatch):
    """Open the dual gate (dev_mode AND THE_ONE_DISCORD_TEST_ENDPOINT=1)
    the sever route requires."""
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("THE_ONE_DISCORD_TEST_ENDPOINT", "1")


async def _wait_for_client(mgr: ConnectorManager, connector_id: str, *, timeout: float = 5.0):
    """Poll ``client_for`` until it's non-None (or raise) — a fixed sleep
    after ``POST /api/connectors`` is not reliably long enough for the
    listener's real websocket handshake to complete under scheduler load,
    unlike the stub plugin's synchronous connect."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        client = mgr.client_for(connector_id)
        if client is not None:
            return client
        await asyncio.sleep(0.01)
    raise AssertionError(f"no live client for {connector_id} after {timeout}s")


def _discord_payload(**overrides) -> dict:
    payload = {
        "name": "Discord Connector",
        "type": "discord",
        "config": {"default_agent": "bot-1"},
        "secrets": {"token": "tok"},
    }
    payload.update(overrides)
    return payload


# ── gate ──────────────────────────────────────────────────────────────


async def test_sever_403_when_dev_mode_off(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setenv("THE_ONE_DISCORD_TEST_ENDPOINT", "1")
    resp = await client.post("/api/_test/discord/sever", json={"connector_id": "x"})
    assert resp.status_code == 403


async def test_sever_403_when_env_unset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.delenv("THE_ONE_DISCORD_TEST_ENDPOINT", raising=False)
    resp = await client.post("/api/_test/discord/sever", json={"connector_id": "x"})
    assert resp.status_code == 403


# ── error taxonomy (AC-2) ─────────────────────────────────────────────


async def test_sever_404_unknown_connector(client: AsyncClient, discord_gate) -> None:
    resp = await client.post("/api/_test/discord/sever", json={"connector_id": "no-such-id"})
    assert resp.status_code == 404


async def test_sever_409_when_client_for_returns_none(client: AsyncClient, discord_gate) -> None:
    """Row exists (created disabled, so the manager never starts a
    listener for it) but ``client_for`` -> None — the mid-backoff/
    never-started state that can't be told apart from a 404 without the
    repo-existence check running first."""
    set_manager(ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02))
    create = await client.post(
        "/api/connectors",
        json=_discord_payload(config={"default_agent": "bot-1", "enabled": False}),
    )
    assert create.status_code == 201
    connector_id = create.json()["id"]

    resp = await client.post("/api/_test/discord/sever", json={"connector_id": connector_id})
    assert resp.status_code == 409


async def test_sever_501_when_client_has_no_hook(
    client: AsyncClient, discord_gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stub-typed connector's live client has no ``sever_for_test`` hook
    — the ``getattr`` discovery path's negative case (unit-level, where
    stub registration/creatability is free via the second env gate)."""
    monkeypatch.setenv("THE_ONE_STUB_TEST_ENDPOINT", "1")
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    set_manager(mgr)

    create = await client.post(
        "/api/connectors",
        json={
            "name": "Stub Connector",
            "type": "stub",
            "config": {"default_agent": "bot-1"},
            "secrets": {"token": "s3cr3t"},
        },
    )
    assert create.status_code == 201
    connector_id = create.json()["id"]
    await _wait_for_client(mgr, connector_id)

    resp = await client.post("/api/_test/discord/sever", json={"connector_id": connector_id})
    assert resp.status_code == 501


# ── happy path: live discord connector ──────────────────────────────────


async def test_sever_ok_on_live_discord_connector(client: AsyncClient, discord_gate) -> None:
    async def gw_handler(session):
        await session.send_hello(heartbeat_interval_ms=10_000)
        await session.recv_json(timeout=5)  # identify
        await session.send_ready(session_id="s1", resume_gateway_url="ws://ignored")
        await asyncio.sleep(1.0)

    gw = FakeGateway(gw_handler)
    url = await gw.start()
    plugin = DiscordPlugin(gateway_url=url)
    registry.register_for_test("discord", plugin)
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    set_manager(mgr)
    try:
        create = await client.post("/api/connectors", json=_discord_payload())
        assert create.status_code == 201
        connector_id = create.json()["id"]
        live_client = await _wait_for_client(mgr, connector_id)
        assert live_client.is_alive() is True

        resp = await client.post("/api/_test/discord/sever", json={"connector_id": connector_id})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        for _ in range(500):
            if live_client.is_alive() is False:
                break
            await asyncio.sleep(0.01)
        assert live_client.is_alive() is False
    finally:
        await mgr.drain()
        await gw.stop()

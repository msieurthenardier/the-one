"""Route tests for the connector CRUD/doctor/pairing surface (DD-7) and the
two dual-gated test seams (DD-10). Mission 23 Flight 2 Leg 2.

Uses the ``isolated_db`` global fixture (repoints the REAL
``the_one.db.connection`` singleton at a per-test DB) rather than the
``client_and_key``-style local patch used by
``tests/test_api_secret_mask_roundtrip.py`` — several tests here also
drive the connector manager's background listener tasks, which resolve
their own DB connection via function-local imports
(``the_one.connectors.inbound.dispatch_inbound``); those need to see the
SAME database the HTTP routes write to.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.base import ChannelTarget
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.interfaces.web.api import router
from the_one.tools.connector_send import SEND_TO_PLATFORM_CHANNEL_TOOL_NAME

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
    test_app = FastAPI()
    test_app.include_router(router)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers()
    ) as c:
        yield c


@pytest.fixture
def stub_gate(monkeypatch: pytest.MonkeyPatch):
    """Open the dual gate (dev_mode AND THE_ONE_STUB_TEST_ENDPOINT=1) that
    makes ``"stub"`` a creatable connector type and the two ``/_test/``
    seams reachable."""
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("THE_ONE_STUB_TEST_ENDPOINT", "1")


@pytest.fixture
def connected_manager(stub_gate):
    """A running ``ConnectorManager`` with the stub plugin registered —
    installed via ``set_manager`` so the routes' ``get_connector_manager()``
    resolves it. Fast poll/backoff for quick reconnect-driven tests."""
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    set_manager(mgr)
    return mgr


def _stub_payload(**overrides) -> dict:
    payload = {
        "name": "Stub Connector",
        "type": "stub",
        "config": {"default_agent": "bot-1"},
        "secrets": {"token": "s3cr3t-token-value"},
    }
    payload.update(overrides)
    return payload


# ── list / get / types ──────────────────────────────────────────────────


async def test_list_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/connectors")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_unknown_404(client: AsyncClient) -> None:
    resp = await client.get("/api/connectors/no-such-id")
    assert resp.status_code == 404


async def test_types_route_discord_and_telegram_without_gate(client: AsyncClient) -> None:
    """AC-2: 'telegram' joins 'discord' unconditionally -- both list with
    the stub gate closed."""
    resp = await client.get("/api/connectors/types")
    assert resp.status_code == 200
    values = [t["value"] for t in resp.json()]
    assert values == ["discord", "telegram"]


async def test_types_route_includes_stub_with_gate(client: AsyncClient, stub_gate) -> None:
    resp = await client.get("/api/connectors/types")
    assert resp.status_code == 200
    values = {t["value"] for t in resp.json()}
    assert values == {"discord", "stub", "telegram"}


# ── create ────────────────────────────────────────────────────────────


async def test_create_masks_secrets_in_response(client: AsyncClient, stub_gate) -> None:
    resp = await client.post("/api/connectors", json=_stub_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["secrets"]["token"] != "s3cr3t-token-value"
    assert "s3cr3t-token-value" not in resp.text

    got = await client.get(f"/api/connectors/{body['id']}")
    assert got.status_code == 200
    assert "s3cr3t-token-value" not in got.text


async def test_create_rejects_masked_sentinel(client: AsyncClient, stub_gate) -> None:
    resp = await client.post("/api/connectors", json=_stub_payload(secrets={"token": "__MASKED__"}))
    assert resp.status_code == 422


async def test_create_rejects_bad_config_unknown_key(client: AsyncClient, stub_gate) -> None:
    resp = await client.post("/api/connectors", json=_stub_payload(config={"not_a_real_key": 1}))
    assert resp.status_code == 422


async def test_create_rejects_type_not_creatable(client: AsyncClient) -> None:
    """ "stub" is a valid Literal on the model but not creatable without
    the dual gate open (DD-Q2)."""
    resp = await client.post("/api/connectors", json=_stub_payload())
    assert resp.status_code == 422


async def test_create_starts_listener(client: AsyncClient, connected_manager) -> None:
    resp = await client.post("/api/connectors", json=_stub_payload())
    assert resp.status_code == 201
    connector_id = resp.json()["id"]
    await asyncio.sleep(0.05)
    assert StubPlugin.connect_calls == [connector_id]
    assert connected_manager.client_for(connector_id) is not None


# ── update ────────────────────────────────────────────────────────────


async def test_update_unknown_404(client: AsyncClient, stub_gate) -> None:
    resp = await client.put("/api/connectors/no-such-id", json=_stub_payload())
    assert resp.status_code == 404


async def test_update_rejects_bad_config(client: AsyncClient, stub_gate) -> None:
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]
    resp = await client.put(
        f"/api/connectors/{connector_id}",
        json=_stub_payload(config={"allowlist": {"peers": [1, 2]}}),
    )
    assert resp.status_code == 422


async def test_update_restarts_listener(client: AsyncClient, connected_manager) -> None:
    """Old listener stopped, new one started; no stale-credential listener
    survives a save (Edge Cases / AC — PUT restarting semantics)."""
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)
    assert len(StubPlugin.connect_calls) == 1

    resp = await client.put(
        f"/api/connectors/{connector_id}",
        json=_stub_payload(name="Renamed", secrets={"token": "brand-new-secret"}),
    )
    assert resp.status_code == 200
    await asyncio.sleep(0.05)

    assert len(StubPlugin.disconnect_calls) == 1  # old listener stopped
    assert len(StubPlugin.connect_calls) == 2  # new listener started
    assert connected_manager.client_for(connector_id) is not None


# ── enabled (AC-8, Mission 23 Flight 3 Leg 2, DD-6) ─────────────────────


async def test_create_with_enabled_false_does_not_start_listener(
    client: AsyncClient, connected_manager
) -> None:
    resp = await client.post(
        "/api/connectors",
        json=_stub_payload(config={"default_agent": "bot-1", "enabled": False}),
    )
    assert resp.status_code == 201
    connector_id = resp.json()["id"]
    await asyncio.sleep(0.05)
    assert StubPlugin.connect_calls == []
    assert connected_manager.client_for(connector_id) is None


async def test_update_disabled_to_enabled_starts_listener(
    client: AsyncClient, connected_manager
) -> None:
    """New effective true covers disabled→enabled — today's stop+start."""
    create = await client.post(
        "/api/connectors",
        json=_stub_payload(config={"default_agent": "bot-1", "enabled": False}),
    )
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)
    assert connected_manager.client_for(connector_id) is None

    resp = await client.put(
        f"/api/connectors/{connector_id}",
        json=_stub_payload(config={"default_agent": "bot-1", "enabled": True}),
    )
    assert resp.status_code == 200
    await asyncio.sleep(0.05)
    assert len(StubPlugin.connect_calls) == 1
    assert connected_manager.client_for(connector_id) is not None


async def test_update_enabled_to_disabled_stops_only_never_restarts(
    client: AsyncClient, connected_manager
) -> None:
    """New effective false covers enabled→disabled — stop only, NEVER
    start. This is the deviation from the old 'restart-as-today' framing
    (amended leg-2 design review 2026-09-01)."""
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)
    assert len(StubPlugin.connect_calls) == 1

    resp = await client.put(
        f"/api/connectors/{connector_id}",
        json=_stub_payload(config={"default_agent": "bot-1", "enabled": False}),
    )
    assert resp.status_code == 200
    await asyncio.sleep(0.05)
    assert len(StubPlugin.disconnect_calls) == 1
    assert len(StubPlugin.connect_calls) == 1  # never restarted
    assert connected_manager.client_for(connector_id) is None


async def test_update_disabled_to_disabled_unrelated_field_does_not_start(
    client: AsyncClient, connected_manager
) -> None:
    """AC-8 trap case: a PUT to an already-disabled connector changing an
    unrelated field must not start a listener. FULL current-config resend
    (mirrors Studio's ``collectPayload()``) — the endpoint's merge is a
    shallow top-level ``dict.update()``, so a partial ``{"config": {...}}``
    body would silently drop ``enabled: false`` and test nothing."""
    create = await client.post(
        "/api/connectors",
        json=_stub_payload(config={"default_agent": "bot-1", "enabled": False}),
    )
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)
    assert connected_manager.client_for(connector_id) is None

    resp = await client.put(
        f"/api/connectors/{connector_id}",
        json=_stub_payload(config={"default_agent": "bot-2", "enabled": False}),
    )
    assert resp.status_code == 200
    await asyncio.sleep(0.05)
    assert StubPlugin.connect_calls == []  # never started
    assert connected_manager.client_for(connector_id) is None


# ── doctor distinct disabled state (AC-9) ───────────────────────────────


async def test_doctor_marks_disabled_connector_distinctly(client: AsyncClient, stub_gate) -> None:
    """AC-9: doctor still runs the plugin probe (diagnosis, not traffic) on
    a disabled connector, but the response distinctly marks it disabled."""
    registry.register_for_test("stub", StubPlugin())
    create = await client.post(
        "/api/connectors",
        json=_stub_payload(config={"default_agent": "bot-1", "enabled": False}),
    )
    connector_id = create.json()["id"]

    resp = await client.post(f"/api/connectors/{connector_id}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["disabled"] is True
    assert body["status"] == "ok"  # StubPlugin.doctor() still runs diagnosis


async def test_doctor_marks_enabled_connector_not_disabled(client: AsyncClient, stub_gate) -> None:
    registry.register_for_test("stub", StubPlugin())
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]

    resp = await client.post(f"/api/connectors/{connector_id}/test")
    assert resp.json()["disabled"] is False


# ── delete ────────────────────────────────────────────────────────────


async def test_delete_unknown_404(client: AsyncClient, stub_gate) -> None:
    resp = await client.delete("/api/connectors/no-such-id")
    assert resp.status_code == 404


async def test_delete_stops_listener_before_row_dies(
    client: AsyncClient, connected_manager
) -> None:
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)

    resp = await client.delete(f"/api/connectors/{connector_id}")
    assert resp.status_code == 200
    assert len(StubPlugin.disconnect_calls) == 1
    assert connected_manager.client_for(connector_id) is None

    got = await client.get(f"/api/connectors/{connector_id}")
    assert got.status_code == 404


async def test_delete_removes_directory_rows_leaves_other_connectors_untouched(
    client: AsyncClient, stub_gate
) -> None:
    """AC-8/DD-1g: deleting a connector removes its ``connector_directory``
    rows via the deterministic DELETE (no FK/cascade, per DD-4); another
    connector's rows are untouched."""
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorDirectoryRepository

    create_a = await client.post("/api/connectors", json=_stub_payload(name="A"))
    connector_a = create_a.json()["id"]
    create_b = await client.post("/api/connectors", json=_stub_payload(name="B"))
    connector_b = create_b.json()["id"]

    dir_repo = ConnectorDirectoryRepository(await get_connection())
    await dir_repo.upsert(
        connector_id=connector_a,
        kind="peer",
        platform_id="p1",
        thread_id=None,
        display_name="Alice",
        username=None,
    )
    await dir_repo.upsert(
        connector_id=connector_b,
        kind="peer",
        platform_id="p1",
        thread_id=None,
        display_name="Bob",
        username=None,
    )

    resp = await client.delete(f"/api/connectors/{connector_a}")
    assert resp.status_code == 200

    assert await dir_repo.get(connector_a, "peer", "p1") is None
    assert await dir_repo.get(connector_b, "peer", "p1") is not None


# ── doctor ────────────────────────────────────────────────────────────


async def test_doctor_404_unknown(client: AsyncClient) -> None:
    resp = await client.post("/api/connectors/no-such-id/test")
    assert resp.status_code == 404


async def test_doctor_no_plugin_registered_is_clean_degraded_report(
    client: AsyncClient,
) -> None:
    """No plugin registered for the type is the NORM this flight (Discord
    lands Flight 3) — a clean degraded/failed report, never a crash."""
    create = await client.post(
        "/api/connectors",
        json={
            "name": "Discord Connector",
            "type": "discord",
            "config": {"default_agent": "bot-1"},
            "secrets": {},
        },
    )
    assert create.status_code == 201
    connector_id = create.json()["id"]

    resp = await client.post(f"/api/connectors/{connector_id}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("degraded", "failed")
    assert "no plugin registered" in body["message"]


async def test_doctor_warns_dangling_default_agent(client: AsyncClient, stub_gate) -> None:
    registry.register_for_test("stub", StubPlugin())
    create = await client.post(
        "/api/connectors", json=_stub_payload(config={"default_agent": "ghost-agent"})
    )
    connector_id = create.json()["id"]

    resp = await client.post(f"/api/connectors/{connector_id}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert any("ghost-agent" in w for w in body["warnings"])


async def test_doctor_warns_missing_send_tool_then_clean_once_enabled(
    client: AsyncClient, stub_gate
) -> None:
    registry.register_for_test("stub", StubPlugin())
    # `enabled_tools=[]` (empty whitelist) blocks all built-in tools,
    # including the send tool — `enabled_tools=None` (the plain-create
    # default) would NOT block it, since that whitelist is opt-in-only
    # when unset. See `AgentConfig.is_tool_enabled`'s docstring.
    agent = await client.post("/api/agents", json={"name": "bot-1", "enabled_tools": []})
    assert agent.status_code == 201
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]

    resp = await client.post(f"/api/connectors/{connector_id}/test")
    body = resp.json()
    assert body["status"] == "ok"  # StubPlugin.doctor() defaults to ok
    assert any("send tool" in w for w in body["warnings"])

    await client.put(
        "/api/agents/bot-1",
        json={"name": "bot-1", "enabled_tools": [SEND_TO_PLATFORM_CHANNEL_TOOL_NAME]},
    )
    resp2 = await client.post(f"/api/connectors/{connector_id}/test")
    assert resp2.json()["warnings"] == []


async def test_doctor_runs_on_no_default_agent_without_crashing(
    client: AsyncClient, stub_gate
) -> None:
    registry.register_for_test("stub", StubPlugin())
    create = await client.post("/api/connectors", json=_stub_payload(config={}))
    connector_id = create.json()["id"]
    resp = await client.post(f"/api/connectors/{connector_id}/test")
    assert resp.status_code == 200
    assert any("default_agent" in w for w in resp.json()["warnings"])


# ── pairing code ──────────────────────────────────────────────────────


async def test_pairing_code_404_unknown_connector(client: AsyncClient) -> None:
    resp = await client.post("/api/connectors/no-such-id/pairing-code")
    assert resp.status_code == 404


async def test_pairing_code_returns_code_and_expiry(client: AsyncClient, connected_manager) -> None:
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]
    resp = await client.post(f"/api/connectors/{connector_id}/pairing-code")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["code"], str) and len(body["code"]) > 0
    assert "expires_at" in body


async def test_pairing_code_second_request_replaces_first(
    client: AsyncClient, connected_manager
) -> None:
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]
    first = (await client.post(f"/api/connectors/{connector_id}/pairing-code")).json()["code"]
    second = (await client.post(f"/api/connectors/{connector_id}/pairing-code")).json()["code"]
    assert first != second
    assert connected_manager.consume_pairing_code(connector_id, first) is False
    assert connected_manager.consume_pairing_code(connector_id, second) is True


async def test_pairing_code_one_time_consumption_through_http_path(
    client: AsyncClient, connected_manager
) -> None:
    """Full round-trip through the HTTP surface: generate a code via the
    pairing route, submit it via the dual-gated stub inbound seam, and
    assert the peer landed in ``allowlist.peers`` — proving consumption
    happened through the real pipeline, not a direct manager call."""
    create = await client.post("/api/connectors", json=_stub_payload())
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)  # let the listener connect

    code = (await client.post(f"/api/connectors/{connector_id}/pairing-code")).json()["code"]

    inbound = await client.post(
        "/api/_test/stub/inbound",
        json={
            "connector_id": connector_id,
            "peer_id": "peer-42",
            "text": code,
            "is_dm": True,
        },
    )
    assert inbound.status_code == 200

    got = (await client.get(f"/api/connectors/{connector_id}")).json()
    assert "peer-42" in got["config"]["allowlist"]["peers"]

    # Second submission of the same (now-consumed) code is silently a
    # no-op — the peer list does not grow, no duplicate/error.
    await client.post(
        "/api/_test/stub/inbound",
        json={
            "connector_id": connector_id,
            "peer_id": "peer-99",
            "text": code,
            "is_dm": True,
        },
    )
    got_again = (await client.get(f"/api/connectors/{connector_id}")).json()
    assert got_again["config"]["allowlist"]["peers"] == ["peer-42"]


# ── test seams (DD-10) ───────────────────────────────────────────────


async def test_stub_inbound_seam_409_when_not_connected(client: AsyncClient, stub_gate) -> None:
    resp = await client.post(
        "/api/_test/stub/inbound",
        json={"connector_id": "never-connected", "peer_id": "p", "text": "hi"},
    )
    assert resp.status_code == 409


async def test_stub_inbound_seam_passes_through_peer_username_into_directory(
    client: AsyncClient, connected_manager
) -> None:
    """AC-4: peer_username flows from the stub seam's optional body field
    (DD-1f passthrough) through ``dispatch_inbound``'s peer hook into the
    directory -- the third of the three ``InboundEnvelope`` construction
    sites."""
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorDirectoryRepository

    create = await client.post(
        "/api/connectors",
        json=_stub_payload(config={"default_agent": "bot-1", "allowlist": {"peers": ["peer-1"]}}),
    )
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)

    resp = await client.post(
        "/api/_test/stub/inbound",
        json={
            "connector_id": connector_id,
            "peer_id": "peer-1",
            "peer_name": "Alice",
            "peer_username": "alice99",
            "text": "/new",
            "is_dm": True,
        },
    )
    assert resp.status_code == 200

    dir_repo = ConnectorDirectoryRepository(await get_connection())
    entry = await dir_repo.get(connector_id, "peer", "peer-1")
    assert entry is not None
    assert entry.display_name == "Alice"
    assert entry.username == "alice99"


async def test_stub_outbound_seam_renders_recorded_sends(client: AsyncClient, stub_gate) -> None:
    StubPlugin.outbound_records.append(
        (ChannelTarget(connector_id="c1", channel_id="ch-1"), "hello there")
    )
    resp = await client.get("/api/_test/stub/outbound")
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert records == [
        {"connector_id": "c1", "channel_id": "ch-1", "peer_id": None, "content": "hello there"}
    ]

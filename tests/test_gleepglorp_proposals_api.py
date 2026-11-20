"""The GleepGlorp proposal routes (M36 F2 L4, DD7): list, approve, dismiss and the refusals."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._gleepglorp_seed import seed
from the_one import time_zones
from the_one.gleepglorp.proposals import shape
from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, NewProposal

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
async def world(tmp_path, monkeypatch):
    from the_one.db import _write_lock

    _write_lock.reset_for_test()
    ns = await seed(tmp_path)
    monkeypatch.setattr(time_zones, "utcnow", lambda: NOW)
    monkeypatch.setattr(time_zones, "detect_system_zone", lambda: "UTC")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=ns.conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=ns.enc),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            ns.client = c
            yield ns
    await ns.conn.close()


async def propose(world, kind, action, changes, session="s1", **target) -> int:
    n = await shape.normalize(
        kind, action, target, changes, conn=world.conn, now=NOW, zone=UTC, enc=world.enc
    )
    return await GleepGlorpProposalRepository(world.conn).insert(
        NewProposal(
            session_id=session,
            kind=n.kind,
            action=n.action,
            agent_name=n.agent_name,
            target_key=n.target_key,
            changes=n.changes,
            target_id=n.target_id,
            base=n.base,
        )
    )


async def test_the_gate_holds_and_the_routes_are_on_the_real_app() -> None:
    from the_one.interfaces.web.app import app as real_app

    client = TestClient(real_app)  # no lifespan: the credential gate runs first
    for method, path in (
        ("get", "/api/gleepglorp/proposals?session_id=s1"),
        ("post", "/api/gleepglorp/proposals/1/approve"),
        ("post", "/api/gleepglorp/proposals/1/dismiss"),
    ):
        assert getattr(client, method)(path).status_code == 401, path


async def test_list_returns_the_chats_proposals_by_id(world) -> None:
    a = await propose(world, "agent", "change", {"description": "d"}, agent="plain")
    resp = await world.client.get("/api/gleepglorp/proposals", params={"session_id": "s1"})
    assert resp.status_code == 200
    rows = resp.json()["proposals"]
    assert [r["id"] for r in rows] == [a]
    assert rows[0]["status"] == "pending" and rows[0]["labels"]["description"] == "Description"
    for query in ({"session_id": "nope"}, {"session_id": ""}, {}):
        resp = await world.client.get("/api/gleepglorp/proposals", params=query)
        assert resp.json() == {"proposals": []}


async def test_approve_applies_and_returns_the_view(world) -> None:
    pid = await propose(world, "agent", "change", {"description": "Via the route"}, agent="plain")
    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/approve")
    assert resp.status_code == 200
    body = resp.json()["proposal"]
    assert body["id"] == pid and body["status"] == "applied"
    assert body["result"]["summary"] == "Changed Description on plain"
    again = await world.client.post(f"/api/gleepglorp/proposals/{pid}/approve")
    assert again.status_code == 200 and again.json()["proposal"]["status"] == "applied"


async def test_a_failed_apply_is_a_200_with_the_errors(world) -> None:
    from the_one.agent.config import AgentConfig

    pid = await propose(world, "agent", "create", {"name": "Taken"})
    await world.client.post(
        "/api/agents", json=AgentConfig(name="Taken", provider_config_id="p-local").model_dump()
    )
    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/approve")
    assert resp.status_code == 200
    body = resp.json()["proposal"]
    assert body["status"] == "failed"
    assert body["result"]["errors"][0]["loc"] == ["name"]


async def test_stale_is_a_409_with_labelled_fields_and_override_applies(world) -> None:
    pid = await propose(world, "agent", "change", {"description": "Proposed"}, agent="plain")
    await world.client.put(
        "/api/agents/plain",
        json={"description": "Hand edit", "provider_config_id": "p-local", "llm_model": "m"},
    )
    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/approve")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "stale"
    assert detail["fields"] == [
        {
            "field": "description",
            "label": "Description",
            "current": "Hand edit",
            "proposed": "Proposed",
        }
    ]
    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/approve?override=true")
    assert resp.status_code == 200 and resp.json()["proposal"]["status"] == "applied"


async def test_busy_gone_and_closed_are_409(world, monkeypatch) -> None:
    pid = await propose(world, "agent", "change", {"description": "d"}, agent="plain")
    monkeypatch.setattr("the_one.sessions._locks.is_session_busy", lambda sid: True)
    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/approve")
    assert (resp.status_code, resp.json()["detail"]) == (409, {"error": "busy"})
    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/dismiss")
    assert (resp.status_code, resp.json()["detail"]) == (409, {"error": "busy"})
    monkeypatch.undo()

    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/dismiss")
    assert resp.status_code == 200 and resp.json()["proposal"]["status"] == "dismissed"
    resp = await world.client.post(f"/api/gleepglorp/proposals/{pid}/approve")
    assert (resp.status_code, resp.json()["detail"]) == (
        409,
        {"error": "closed", "status": "dismissed"},
    )

    gone = await propose(world, "rule", "change", {"text": "x"}, "s2", agent="wide", rule=1)
    await world.conn.execute("DELETE FROM agent_rules")
    await world.conn.commit()
    resp = await world.client.post(f"/api/gleepglorp/proposals/{gone}/approve")
    assert (resp.status_code, resp.json()["detail"]) == (409, {"error": "gone"})
    row = await GleepGlorpProposalRepository(world.conn).get(gone)
    assert (row.status, row.result) == ("withdrawn", {"reason": "gone"})


async def test_an_unknown_id_is_a_404(world) -> None:
    for action in ("approve", "dismiss"):
        resp = await world.client.post(f"/api/gleepglorp/proposals/777/{action}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Proposal not found: 777"

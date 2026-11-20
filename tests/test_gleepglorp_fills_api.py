"""The GleepGlorp fill routes and the snapshot key (M36 F3 L5, DD6)."""

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
from the_one.gleepglorp.fill import events as fill_events
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository, NewFill
from the_one.gleepglorp.proposals import events as proposal_events

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
async def world(tmp_path, monkeypatch):
    from the_one.db import _write_lock

    _write_lock.reset_for_test()
    ns = await seed(tmp_path)
    monkeypatch.setattr(time_zones, "utcnow", lambda: NOW)
    ns.sent = []

    async def capture(session_id, payload, **_kw):
        ns.sent.append(payload)

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", capture)
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


async def make(world, session="s1", agent="plain", **kw) -> int:
    fid, _ = await GleepGlorpFillRepository(world.conn).insert(
        NewFill(
            session_id=session,
            kind="agent",
            action="change",
            agent_name=agent,
            target_key=f"agent:{agent}",
            changes=kw.pop("changes", {"description": "d", "rich_visuals": False}),
            **kw,
        )
    )
    return fid


async def claim(world, fid) -> str:
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/claim")
    assert resp.status_code == 200, resp.text
    return resp.json()["claim"]


def outcome(token, status="filled", **kw) -> dict:
    return {"claim": token, "status": status, **kw}


async def test_the_gate_holds_and_the_routes_are_on_the_real_app() -> None:
    from the_one.interfaces.web.app import app as real_app

    client = TestClient(real_app)
    for method, path in (
        ("get", "/api/gleepglorp/fills?session_id=s1"),
        ("post", "/api/gleepglorp/fills/1/claim"),
        ("post", "/api/gleepglorp/fills/1/outcome"),
    ):
        assert getattr(client, method)(path).status_code == 401, path


async def test_list_returns_the_chats_views_in_id_order(world) -> None:
    a = await make(world)
    b = await make(world)
    await make(world, session="s2")
    resp = await world.client.get("/api/gleepglorp/fills", params={"session_id": "s1"})
    rows = resp.json()["fills"]
    assert [r["id"] for r in rows] == [a, b] and rows[0]["status"] == "replaced"
    assert all("claim_token" not in r for r in rows)
    for query in ({"session_id": "nope"}, {"session_id": ""}, {}):
        resp = await world.client.get("/api/gleepglorp/fills", params=query)
        assert resp.json() == {"fills": []}


async def test_claim_returns_the_view_and_a_token_and_pushes(world) -> None:
    fid = await make(world)
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/claim")
    assert resp.status_code == 200
    body = resp.json()
    assert body["fill"]["status"] == "applying" and body["claim"]
    assert "claim_token" not in body["fill"] and body["claim"] not in str(body["fill"])
    [frame] = world.sent
    assert frame["type"] == "fill_changed" and frame["fill"]["status"] == "applying"
    assert body["claim"] not in str(frame)


async def test_claim_refusals_write_and_push_nothing(world) -> None:
    fid = await make(world)
    await claim(world, fid)
    world.sent.clear()
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/claim")
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"error": "claimed", "status": "applying"}
    old = await make(world, session="s9")
    await make(world, session="s9")  # replaces old
    world.sent.clear()
    resp = await world.client.post(f"/api/gleepglorp/fills/{old}/claim")
    assert resp.status_code == 409 and resp.json()["detail"]["status"] == "replaced"
    assert (await world.client.post("/api/gleepglorp/fills/999/claim")).status_code == 404
    assert world.sent == []


async def test_an_outcome_records_and_pushes(world) -> None:
    fid = await make(world)
    token = await claim(world, fid)
    world.sent.clear()
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/outcome", json=outcome(token))
    assert resp.status_code == 200
    view = resp.json()["fill"]
    assert view["status"] == "filled" and view["outcome"] == {"kept": [], "reason": None}
    [frame] = world.sent
    assert frame["type"] == "fill_changed" and frame["fill"]["status"] == "filled"


async def test_partly_and_not_filled_outcomes(world) -> None:
    fid = await make(world)
    token = await claim(world, fid)
    resp = await world.client.post(
        f"/api/gleepglorp/fills/{fid}/outcome",
        json=outcome(token, "partly_filled", kept=["description"]),
    )
    assert resp.status_code == 200
    assert resp.json()["fill"]["outcome"] == {"kept": ["description"], "reason": None}
    fid2 = await make(world, session="s2")
    token = await claim(world, fid2)
    resp = await world.client.post(
        f"/api/gleepglorp/fills/{fid2}/outcome", json=outcome(token, "not_filled", reason="stay")
    )
    assert resp.status_code == 200 and resp.json()["fill"]["status"] == "not_filled"


@pytest.mark.parametrize(
    "body",
    [
        {"status": "filled"},  # no claim
        {"claim": "x", "status": "applying"},
        {"claim": "x", "status": "filled", "extra": 1},
        {"claim": "x", "status": "filled", "kept": ["description"]},
        {"claim": "x", "status": "filled", "reason": "stay"},
        {"claim": "x", "status": "partly_filled", "kept": []},
        {"claim": "x", "status": "partly_filled", "kept": ["name"]},  # not in the fill's changes
        {"claim": "x", "status": "partly_filled", "kept": ["description"], "reason": "stay"},
        # More entries than the fill has changes (a repeat), or a long list: bounded.
        {"claim": "x", "status": "partly_filled", "kept": ["description", "description"]},
        {"claim": "x", "status": "partly_filled", "kept": ["description"] * 500},
        {"claim": "x", "status": "not_filled"},
        {"claim": "x", "status": "not_filled", "reason": "free text"},
        {"claim": "x", "status": "not_filled", "reason": "stay", "kept": ["description"]},
    ],
)
async def test_an_inconsistent_outcome_is_a_422_and_writes_nothing(world, body) -> None:
    fid = await make(world)
    token = await claim(world, fid)
    world.sent.clear()
    if body.get("claim") == "x":
        body = {**body, "claim": token}
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/outcome", json=body)
    assert resp.status_code == 422, resp.text
    # Nothing from the request is echoed back.
    assert "input" not in resp.text and token not in resp.text and "free text" not in resp.text
    assert world.sent == []
    view = (await world.client.get("/api/gleepglorp/fills", params={"session_id": "s1"})).json()
    assert view["fills"][0]["status"] == "applying"


async def test_a_bad_token_or_a_second_outcome_is_a_409(world) -> None:
    fid = await make(world)
    token = await claim(world, fid)
    world.sent.clear()
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/outcome", json=outcome("wrong"))
    assert resp.status_code == 409 and resp.json()["detail"] == {"error": "not_applying"}
    assert (
        await world.client.post(f"/api/gleepglorp/fills/{fid}/outcome", json=outcome(token))
    ).status_code == 200
    world.sent.clear()
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/outcome", json=outcome(token))
    assert resp.status_code == 409 and world.sent == []
    resp = await world.client.post("/api/gleepglorp/fills/999/outcome", json=outcome("t"))
    assert resp.status_code == 404
    resp = await world.client.post(f"/api/gleepglorp/fills/{fid}/outcome", content=b"not json")
    assert resp.status_code == 422


async def test_the_routes_write_no_configuration(world) -> None:
    async def agents():
        async with world.conn.execute("SELECT * FROM agents ORDER BY name") as cur:
            return [tuple(r) for r in await cur.fetchall()]

    before = await agents()
    fid = await make(world)
    token = await claim(world, fid)
    await world.client.post(f"/api/gleepglorp/fills/{fid}/outcome", json=outcome(token))
    assert await agents() == before


# --- the snapshot (AC9) ----------------------------------------------------------------


async def _one_proposal(world) -> None:
    from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, NewProposal

    await GleepGlorpProposalRepository(world.conn).insert(
        NewProposal(
            session_id="s1",
            kind="agent",
            action="change",
            agent_name="plain",
            target_key="agent:plain",
            changes={"description": "p"},
        )
    )


async def test_the_snapshot_carries_fills_in_id_order(world) -> None:
    await _one_proposal(world)
    a = await make(world)
    b = await make(world)
    await make(world, session="s2")
    frame = await proposal_events.snapshot_frame(world.conn, "s1", "GleepGlorp")
    assert frame["type"] == "proposals_snapshot" and len(frame["proposals"]) == 1
    assert [f["id"] for f in frame["fills"]] == [a, b]
    assert await proposal_events.snapshot_frame(world.conn, "s1", "plain") is None


async def test_a_failing_fills_read_keeps_the_proposals(world, monkeypatch) -> None:
    await _one_proposal(world)

    async def boom(*_a, **_k):
        raise RuntimeError("no fills")

    monkeypatch.setattr(fill_events, "snapshot_fills", boom)
    frame = await proposal_events.snapshot_frame(world.conn, "s1", "GleepGlorp")
    assert len(frame["proposals"]) == 1 and frame["fills"] == []

"""REST tests for the Routines item and the proposals queue (M33 F2 L2, AC2/3/8/9/10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.repositories import SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.routines import service as svc
from the_one.routines.repository import AgentRoutineRepository

UTC = timezone.utc
NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=UTC)
DAILY = {"kind": "daily", "time": "09:00"}
ITEM = "/api/agents/ag/self-configuration/routines"


@pytest.fixture
async def client(tmp_path, frozen_clock):
    conn = await connect_template_db(tmp_path / "test.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            c.conn = conn  # type: ignore[attr-defined]
            c.store = SQLiteAgentStore(conn)  # type: ignore[attr-defined]
            resp = await c.post("/api/agents", json={"name": "ag", "description": "d"})
            assert resp.status_code == 201, resp.text
            yield c
    await conn.close()


def body(name="Morning", **over) -> dict:
    return {"name": name, "prompt": "p", "schedule": DAILY, "target": {"kind": "new"}, **over}


async def zone():
    from zoneinfo import ZoneInfo

    return ZoneInfo("UTC")


async def propose(client, action="create", data=None, taint=(False, [])) -> str:
    await client.store.set_routines_self_config("ag", enabled=True, requires_approval=True)
    res = await svc.agent_change(
        client.conn,
        "ag",
        action,
        data or body(),
        now=datetime.now(UTC),
        zone=zone,
        taint=taint,
        session_id=None,
    )
    assert res.pending
    return res.proposal_id


def base(pid: str, verb: str) -> str:
    return f"{ITEM}/proposals/{pid}/{verb}"


# ── switches ──────────────────────────────────────────────────────────────


async def test_defaults_and_agent_put_cannot_change(client) -> None:
    got = (await client.get("/api/agents/ag")).json()
    assert got["routines_self_config_enabled"] is False
    assert got["routines_require_approval"] is True
    resp = await client.put(
        "/api/agents/ag",
        json={"description": "d", "routines_self_config_enabled": True,
              "routines_require_approval": False},
    )  # fmt: skip
    assert resp.status_code == 200
    assert resp.json()["routines_self_config_enabled"] is False
    assert resp.json()["routines_require_approval"] is True
    await client.store.set_routines_self_config("ag", enabled=True, requires_approval=False)
    resp = await client.put("/api/agents/ag", json={"description": "other"})
    assert resp.json()["routines_self_config_enabled"] is True
    assert resp.json()["routines_require_approval"] is False
    stored = await client.store.load("ag")
    assert stored.routines_self_config_enabled and not stored.routines_require_approval


async def test_post_agent_ignores_switches(client) -> None:
    resp = await client.post(
        "/api/agents",
        json={"name": "fresh", "routines_self_config_enabled": True,
              "routines_require_approval": False},
    )  # fmt: skip
    assert resp.status_code == 201
    assert resp.json()["routines_self_config_enabled"] is False
    assert resp.json()["routines_require_approval"] is True
    assert (await client.get("/api/agents/fresh")).json()["routines_require_approval"] is True


async def test_setter_unknown_agent_and_partial(client) -> None:
    with pytest.raises(KeyError):
        await client.store.set_routines_self_config("nope", enabled=True)
    await client.store.set_routines_self_config("ag", requires_approval=False)
    got = await client.store.load("ag")
    assert got.routines_self_config_enabled is False and got.routines_require_approval is False


async def test_item_get_put(client) -> None:
    assert (await client.get(ITEM)).json() == {
        "enabled": False,
        "requires_approval": True,
        "pending_count": 0,
    }
    resp = await client.put(ITEM, json={"enabled": True})
    assert resp.json() == {"enabled": True, "requires_approval": True, "pending_count": 0}
    resp = await client.put(ITEM, json={"requires_approval": False})
    assert resp.json() == {"enabled": True, "requires_approval": False, "pending_count": 0}
    assert (await client.get(ITEM)).json()["requires_approval"] is False


async def test_item_errors(client) -> None:
    assert (await client.put(ITEM, json={})).status_code == 422
    assert (await client.put(ITEM, json={"enabled": "yes"})).status_code == 422
    assert (await client.put(ITEM, json={"enabled": 1})).status_code == 422
    assert (await client.put(ITEM, content=b"nope")).status_code == 422
    for verb in (client.get, client.put):
        kw = {"json": {"enabled": True}} if verb == client.put else {}
        r = await verb("/api/agents/default/self-configuration/routines", **kw)
        assert r.status_code == 422 and r.json()["detail"] == "Routines need a named agent."
        r = await verb("/api/agents/missing/self-configuration/routines", **kw)
        assert r.status_code == 404


async def test_off_switch_supersedes_pending(client) -> None:
    pid = await propose(client)
    assert (await client.get(ITEM)).json()["pending_count"] == 1
    resp = await client.put(ITEM, json={"requires_approval": False})  # not an off switch
    assert resp.json()["pending_count"] == 1
    resp = await client.put(ITEM, json={"enabled": False})
    assert resp.json()["pending_count"] == 0
    got = (await client.get(f"{ITEM}/proposals?status=superseded")).json()["proposals"]
    assert [p["id"] for p in got] == [pid]


# ── proposals ─────────────────────────────────────────────────────────────


async def test_list_and_count(client) -> None:
    pid = await propose(client)
    await propose(client, data=body("Two"))
    assert (await client.get(f"{ITEM}/proposals/pending-count")).json() == {"count": 2}
    rows = (await client.get(f"{ITEM}/proposals")).json()["proposals"]
    assert len(rows) == 2 and set(rows[0]) == {
        "id", "agent_name", "routine_id", "routine_name", "action", "payload", "base",
        "status", "untrusted", "untrusted_sources", "session_id", "created_at", "resolved_at",
    }  # fmt: skip
    assert (await client.get(f"{ITEM}/proposals?limit=1")).json()["proposals"].__len__() == 1
    assert (await client.get(f"{ITEM}/proposals?limit=0")).status_code == 422
    assert (await client.get(f"{ITEM}/proposals?status=bogus")).status_code == 422
    assert (await client.get(f"{ITEM}/proposals?status=applied")).json() == {"proposals": []}
    assert pid


async def test_approve_create_and_idempotent(client) -> None:
    pid = await propose(client)
    resp = await client.post(base(pid, "approve"))
    assert resp.status_code == 200 and resp.json()["status"] == "applied"
    routines = (await client.get("/api/agents/ag/routines")).json()["routines"]
    assert [r["created_by"] for r in routines] == ["agent"]
    assert (await client.post(base(pid, "approve"))).status_code == 200
    assert len((await client.get("/api/agents/ag/routines")).json()["routines"]) == 1


async def test_cross_agent_and_unknown_are_404(client) -> None:
    pid = await propose(client)
    await client.post("/api/agents", json={"name": "other"})
    other = f"/api/agents/other/self-configuration/routines/proposals/{pid}"
    assert (await client.post(other + "/approve")).status_code == 404
    assert (await client.post(other + "/dismiss")).status_code == 404
    assert (await client.post(base("nope", "approve"))).status_code == 404
    assert (await client.post(base("nope", "dismiss"))).status_code == 404
    assert (await client.get(base(pid, "x"))).status_code in (404, 405)


async def test_dismiss_rules(client) -> None:
    pid = await propose(client)
    assert (await client.post(base(pid, "dismiss"))).json()["status"] == "dismissed"
    assert (await client.post(base(pid, "dismiss"))).status_code == 200  # idempotent
    assert (await client.post(base(pid, "approve"))).status_code == 409
    pid2 = await propose(client, data=body("Two"))
    await client.post(base(pid2, "approve"))
    assert (await client.post(base(pid2, "dismiss"))).status_code == 409


async def test_stale_409_then_override(client) -> None:
    r = (await client.post("/api/agents/ag/routines", json=body())).json()
    pid = await propose(client, "update", {"routine": r["id"], "prompt": "agent"})
    await client.put(f"/api/agents/ag/routines/{r['id']}", json={"prompt": "operator"})
    resp = await client.post(base(pid, "approve"))
    assert resp.status_code == 409
    assert resp.json()["detail"] == {
        "error": "stale",
        "current_value": {"prompt": "operator"},
        "proposed_value": {"prompt": "agent"},
        "base_value": {"prompt": "p"},
    }
    resp = await client.post(base(pid, "approve") + "?override=true")
    assert resp.status_code == 200
    got = (await client.get(f"/api/agents/ag/routines/{r['id']}")).json()
    assert got["prompt"] == "agent"


async def test_gone_update_409_and_gone_delete_200(client) -> None:
    r = (await client.post("/api/agents/ag/routines", json=body())).json()
    r2 = (await client.post("/api/agents/ag/routines", json=body("Second"))).json()
    pid = await propose(client, "update", {"routine": r["id"], "prompt": "agent"})
    pid2 = await propose(client, "delete", {"routine": r2["id"]})
    await client.conn.execute("PRAGMA foreign_keys=OFF")
    await client.conn.execute("DELETE FROM agent_routines")
    await client.conn.commit()
    resp = await client.post(base(pid, "approve"))
    assert resp.status_code == 409 and resp.json()["detail"] == {"error": "gone"}
    resp = await client.post(base(pid2, "approve"))
    assert resp.status_code == 200 and resp.json()["status"] == "superseded"
    sup = (await client.get(f"{ITEM}/proposals?status=superseded")).json()["proposals"]
    assert {p["id"] for p in sup} == {pid, pid2}


async def test_past_at_is_422_and_pending(client) -> None:
    at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    pid = await propose(client, data=body(schedule={"kind": "once", "at": at}))
    # Time passes: the stored absolute time is now behind the clock.
    from the_one import time_zones

    with patch.object(time_zones, "utcnow", return_value=datetime.now(UTC) + timedelta(hours=1)):
        resp = await client.post(base(pid, "approve"))
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["schedule"]
    assert (await client.get(f"{ITEM}/proposals?status=pending")).json()["proposals"][0][
        "id"
    ] == pid


async def test_name_taken_409(client) -> None:
    pid = await propose(client)
    await client.post("/api/agents/ag/routines", json=body("MORNING"))
    resp = await client.post(base(pid, "approve"))
    assert resp.status_code == 409


async def test_caps_recheck_422(client) -> None:
    pid = await propose(client, data=body("Late"))
    repo = AgentRoutineRepository(client.conn)
    for i in range(10):
        await repo.create(
            "ag", {"name": f"f{i}", "prompt": "p", "schedule": DAILY, "target_kind": "new"}
        )
    resp = await client.post(base(pid, "approve"))
    assert resp.status_code == 422 and "active routines" in resp.json()["detail"]


# ── the flag ──────────────────────────────────────────────────────────────


async def test_operator_prompt_edit_clears_flag_nothing_else_does(client) -> None:
    pid = await propose(client, taint=(True, ["web:x"]))
    await client.post(base(pid, "approve"))
    rid = (await client.get("/api/agents/ag/routines")).json()["routines"][0]["id"]
    one = f"/api/agents/ag/routines/{rid}"
    got = (await client.get(one)).json()
    assert got["untrusted"] is True and got["untrusted_sources"] == ["web:x"]
    for patch_body in ({"name": "Renamed"}, {"enabled": False}, {"enabled": True},
                       {"schedule": {"kind": "daily", "time": "10:00"}}):  # fmt: skip
        assert (await client.put(one, json=patch_body)).json()["untrusted"] is True
    # A later approved agent update merges rather than clears.
    pid2 = await propose(client, "update", {"routine": rid, "prompt": "agent edit"},
                         taint=(True, ["web:y"]))  # fmt: skip
    await client.post(base(pid2, "approve"))
    got = (await client.get(one)).json()
    assert got["untrusted_sources"] == ["web:x", "web:y"]
    resp = await client.put(one, json={"prompt": "operator edit"})
    assert resp.json()["untrusted"] is False and resp.json()["untrusted_sources"] == []


# ── cascade ───────────────────────────────────────────────────────────────


async def test_rename_and_delete_agent_carry_proposals(client) -> None:
    pid = await propose(client)
    resp = await client.post("/api/agents/ag/rename", json={"new_name": "renamed"})
    assert resp.status_code == 200, resp.text
    rows = (await client.get("/api/agents/renamed/self-configuration/routines/proposals")).json()[
        "proposals"
    ]
    assert [p["id"] for p in rows] == [pid]
    assert (await client.delete("/api/agents/renamed")).status_code == 200
    async with client.conn.execute("SELECT COUNT(*) FROM agent_routine_proposals") as cur:
        assert (await cur.fetchone())[0] == 0

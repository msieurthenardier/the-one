"""REST tests for operator routines (M33 F1 leg 1, DD9; AC10-AC17, AC19-AC20)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.routines.models import RoutineRun
from the_one.routines.repository import RoutineRunRepository

UTC = timezone.utc
# frozen_clock default: 2026-10-10T22:45:12Z, America/Los_Angeles (system mode).
NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=UTC)

DAILY = {"kind": "daily", "time": "09:00"}


@pytest.fixture
async def env(tmp_path, frozen_clock):
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
            yield c
    await conn.close()


@pytest.fixture
def client(env):
    return env


async def _agent(client, name="ag") -> str:
    resp = await client.post("/api/agents", json={"name": name, "description": "d"})
    assert resp.status_code == 201, resp.text
    return name


def _body(name="Morning", **over) -> dict:
    return {
        "name": name,
        "prompt": "  say hi  ",
        "schedule": DAILY,
        "target": {"kind": "new"},
        **over,
    }


async def _make(client, agent="ag", **over) -> dict:
    resp = await client.post(f"/api/agents/{agent}/routines", json=_body(**over))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _chat(client, sid, agent="ag", **extra) -> None:
    await ChatSessionRepository(client.conn).create(
        ChatSession(id=sid, agent_name=agent, title=f"title {sid}", **extra)
    )


# ── create / shape ────────────────────────────────────────────────────────


async def test_create_returns_201_row_shape(client) -> None:
    await _agent(client)
    row = await _make(client)
    assert set(row) == {
        "id", "agent_name", "name", "prompt", "schedule", "enabled", "finished_at",
        "next_run_at", "created_by", "created_at", "updated_at", "target", "last_run",
        "running", "untrusted", "untrusted_sources",
    }  # fmt: skip
    assert row["prompt"] == "say hi"  # trimmed
    assert row["agent_name"] == "ag" and row["enabled"] is True
    assert row["created_by"] == "operator" and row["finished_at"] is None
    assert row["running"] is False and row["last_run"] is None
    assert row["target"] == {
        "kind": "new", "session_id": None, "title": None, "platform": None, "missing": False,
    }  # fmt: skip
    # daily 09:00 PDT after 2026-10-10 15:45 PDT -> Oct 11 09:00 PDT = 16:00Z
    assert row["next_run_at"] == "2026-10-11T16:00:00+00:00"
    assert row["created_at"] == NOW.isoformat()
    assert (await client.get(f"/api/agents/ag/routines/{row['id']}")).json() == row


async def test_list_has_limits_and_name_order(client) -> None:
    await _agent(client)
    await _make(client, name="beta")
    await _make(client, name="Alpha")
    out = (await client.get("/api/agents/ag/routines")).json()
    assert [r["name"] for r in out["routines"]] == ["Alpha", "beta"]
    assert out["limits"] == {
        "prompt_chars": 4000,
        "routines_per_agent": 50,
        "interval_hours_min": 1,
        "interval_hours_max": 168,
        "once_max_days": 365,
        "run_timeout_seconds": 900,
    }


async def test_next_run_moves_with_the_clock_and_zone(client, frozen_clock, monkeypatch) -> None:
    await _agent(client)
    await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Kolkata"})
    row = await _make(client)
    # 09:00 IST = 03:30Z; frozen now is 22:45Z Oct 10 (04:15 IST Oct 11) -> Oct 11 03:30Z
    assert row["next_run_at"] == "2026-10-11T03:30:00+00:00"


async def test_interval_sets_anchor_and_next(client) -> None:
    await _agent(client)
    row = await _make(client, schedule={"kind": "interval", "hours": 6})
    assert row["next_run_at"] == (NOW + timedelta(hours=6)).isoformat()
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        assert (await cur.fetchone())[0] == NOW.isoformat()


async def test_disabled_create_has_no_next_run(client) -> None:
    await _agent(client)
    row = await _make(client, enabled=False)
    assert row["enabled"] is False and row["next_run_at"] is None


async def test_once_in_converts_to_absolute_at(client) -> None:
    await _agent(client)
    row = await _make(client, schedule={"kind": "once", "in": {"amount": 90, "unit": "minutes"}})
    at = (NOW + timedelta(minutes=90)).isoformat()
    assert row["schedule"] == {"kind": "once", "at": at}
    assert row["next_run_at"] == at
    row2 = await _make(
        client, name="d", schedule={"kind": "once", "in": {"amount": 2, "unit": "days"}}
    )
    assert row2["schedule"]["at"] == (NOW + timedelta(days=2)).isoformat()


# ── default agent, unknown agent, cross-agent ─────────────────────────────


async def test_default_agent_refused_even_with_stored_row(client) -> None:
    resp = await client.post("/api/agents/default/routines", json=_body())
    assert resp.status_code == 422 and resp.json()["detail"] == "Routines need a named agent."
    await client.put("/api/agents/default", json={"name": "default", "description": "x"})
    resp = await client.post("/api/agents/default/routines", json=_body())
    assert resp.status_code == 422
    for method, path in [
        ("GET", "/api/agents/default/routines"),
        ("GET", "/api/agents/default/routines/x"),
        ("PUT", "/api/agents/default/routines/x"),
        ("DELETE", "/api/agents/default/routines/x"),
        ("GET", "/api/agents/default/routines/x/runs"),
    ]:
        resp = await client.request(method, path, json={} if method == "PUT" else None)
        assert resp.status_code == 404, (method, path)
        assert resp.json()["detail"] == "Agent not found: default"


async def test_unknown_agent_is_404_everywhere(client) -> None:
    for method, path in [
        ("GET", "/api/agents/nope/routines"),
        ("POST", "/api/agents/nope/routines"),
        ("GET", "/api/agents/nope/routines/x"),
        ("PUT", "/api/agents/nope/routines/x"),
        ("DELETE", "/api/agents/nope/routines/x"),
        ("GET", "/api/agents/nope/routines/x/runs"),
    ]:
        resp = await client.request(
            method, path, json=_body() if method in ("POST", "PUT") else None
        )
        assert resp.status_code == 404, (method, path)


async def test_another_agents_routine_is_404_on_every_route(client) -> None:
    await _agent(client, "ag")
    await _agent(client, "other")
    row = await _make(client)
    rid = row["id"]
    base = f"/api/agents/other/routines/{rid}"
    assert (await client.get(base)).status_code == 404
    assert (await client.put(base, json={"prompt": "x"})).status_code == 404
    assert (await client.delete(base)).status_code == 404
    assert (await client.get(base + "/runs")).status_code == 404
    assert (await client.get(f"/api/agents/ag/routines/{rid}")).status_code == 200


async def test_delete(client) -> None:
    await _agent(client)
    row = await _make(client)
    resp = await client.delete(f"/api/agents/ag/routines/{row['id']}")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}
    assert (await client.get(f"/api/agents/ag/routines/{row['id']}")).status_code == 404
    assert (await client.delete(f"/api/agents/ag/routines/{row['id']}")).status_code == 404


# ── validation ────────────────────────────────────────────────────────────


async def test_duplicate_name_is_409_list_on_name(client) -> None:
    await _agent(client)
    await _agent(client, "b")
    await _make(client, name="Daily")
    resp = await client.post("/api/agents/ag/routines", json=_body(name="daily"))
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and detail[0]["loc"] == ["name"]
    assert (
        await client.post("/api/agents/b/routines", json=_body(name="daily"))
    ).status_code == 201
    other = await _make(client, name="Other")
    resp = await client.put(f"/api/agents/ag/routines/{other['id']}", json={"name": "DAILY"})
    assert resp.status_code == 409
    same = await _make(client, name="Case")
    ok = await client.put(f"/api/agents/ag/routines/{same['id']}", json={"name": "CASE"})
    assert ok.status_code == 200 and ok.json()["name"] == "CASE"


@pytest.mark.parametrize("prompt", [None, "", "   ", 5, "x" * 4001])
async def test_prompt_bounds(client, prompt) -> None:
    await _agent(client)
    resp = await client.post("/api/agents/ag/routines", json=_body(prompt=prompt))
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["prompt"]
    assert "x" * 50 not in resp.text  # no echo


async def test_prompt_exactly_4000_ok(client) -> None:
    await _agent(client)
    assert (
        await client.post("/api/agents/ag/routines", json=_body(prompt="x" * 4000))
    ).status_code == 201


async def test_routine_count_cap(client) -> None:
    await _agent(client)
    for i in range(50):
        await _make(client, name=f"r{i}")
    resp = await client.post("/api/agents/ag/routines", json=_body(name="too many"))
    assert resp.status_code == 422
    assert "50" in str(resp.json()["detail"])


@pytest.mark.parametrize(
    "sched",
    [
        None,
        {"kind": "monthly"},
        {"kind": "daily", "time": "9am"},
        {"kind": "weekly", "days": [], "time": "09:00"},
        {"kind": "interval", "hours": 0},
        {"kind": "interval", "hours": 169},
        {"kind": "once", "at": "2026-11-01T10:00:00"},
        {"kind": "once", "in": {"amount": 0, "unit": "hours"}},
        {"kind": "once", "in": {"amount": 1, "unit": "weeks"}},
        {"kind": "once", "in": {"amount": 1.5, "unit": "hours"}},
        {"kind": "once", "in": {"amount": True, "unit": "hours"}},
    ],
)
async def test_bad_schedules_are_422_on_schedule(client, sched) -> None:
    await _agent(client)
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=sched))
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["schedule"]


async def test_once_past_and_too_far(client) -> None:
    await _agent(client)
    past = {"kind": "once", "at": (NOW - timedelta(seconds=1)).isoformat()}
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=past))
    assert resp.json()["detail"][0]["msg"] == "That time has already passed."
    now_exact = {"kind": "once", "at": NOW.isoformat()}
    assert (
        await client.post("/api/agents/ag/routines", json=_body(schedule=now_exact))
    ).status_code == 422
    far = {"kind": "once", "at": (NOW + timedelta(days=366)).isoformat()}
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=far))
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "That time is more than a year away."
    far_in = {"kind": "once", "in": {"amount": 400, "unit": "days"}}
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=far_in))
    assert resp.json()["detail"][0]["msg"] == "That time is more than a year away."
    huge = {"kind": "once", "in": {"amount": 10**12, "unit": "days"}}
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=huge))
    assert resp.json()["detail"][0]["msg"] == "That time is more than a year away."
    edge = {"kind": "once", "at": (NOW + timedelta(days=365)).isoformat()}
    assert (
        await client.post("/api/agents/ag/routines", json=_body(schedule=edge))
    ).status_code == 201


@pytest.mark.parametrize("body", ["[]", "not json", '"str"'])
async def test_non_object_bodies_are_422(client, body) -> None:
    await _agent(client)
    resp = await client.post(
        "/api/agents/ag/routines", content=body, headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422


async def test_bad_enabled_and_target_shapes(client) -> None:
    await _agent(client)
    assert (
        await client.post("/api/agents/ag/routines", json=_body(enabled="yes"))
    ).status_code == 422
    for t in (None, "new", {"kind": "bogus"}, {"kind": "chat"}, {"kind": "chat", "session_id": 3}):
        resp = await client.post("/api/agents/ag/routines", json=_body(target=t))
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["loc"] == ["target"]


# ── targets ───────────────────────────────────────────────────────────────


async def test_chat_target_web_and_view(client) -> None:
    await _agent(client)
    await _chat(client, "s1")
    row = await _make(client, target={"kind": "chat", "session_id": "s1"})
    assert row["target"] == {
        "kind": "chat", "session_id": "s1", "title": "title s1", "platform": None,
        "missing": False,
    }  # fmt: skip
    async with client.conn.execute(
        "SELECT target_platform, target_connector_id, target_channel_id, target_thread_id, "
        "target_peer_id FROM agent_routines"
    ) as cur:
        assert tuple(await cur.fetchone()) == (None, None, None, None, None)
    await client.delete("/api/chat/sessions/s1")
    got = (await client.get(f"/api/agents/ag/routines/{row['id']}")).json()
    assert got["target"]["missing"] is True and got["target"]["session_id"] == "s1"
    assert got["target"]["title"] is None


async def test_connector_chat_target_snapshots_identity(client) -> None:
    await _agent(client)
    await _chat(
        client,
        "dm1",
        platform="stub",
        connector_id="c1",
        channel_id="ch1",
        thread_id="th1",
        peer_id="p1",
    )
    row = await _make(client, target={"kind": "chat", "session_id": "dm1"})
    assert row["target"]["platform"] == "stub"
    async with client.conn.execute(
        "SELECT target_platform, target_connector_id, target_channel_id, target_thread_id, "
        "target_peer_id FROM agent_routines"
    ) as cur:
        assert tuple(await cur.fetchone()) == ("stub", "c1", "ch1", "th1", "p1")
    # re-pointing at a web chat clears the snapshot
    await _chat(client, "web1")
    out = await client.put(
        f"/api/agents/ag/routines/{row['id']}",
        json={"target": {"kind": "chat", "session_id": "web1"}},
    )
    assert out.status_code == 200 and out.json()["target"]["platform"] is None
    async with client.conn.execute(
        "SELECT target_connector_id, target_peer_id FROM agent_routines"
    ) as cur:
        assert tuple(await cur.fetchone()) == (None, None)
    out = await client.put(f"/api/agents/ag/routines/{row['id']}", json={"target": {"kind": "own"}})
    assert out.json()["target"]["kind"] == "own" and out.json()["target"]["session_id"] is None


async def test_chat_target_must_exist_and_belong_to_the_agent(client) -> None:
    await _agent(client)
    await _agent(client, "other")
    await _chat(client, "theirs", agent="other")
    resp = await client.post(
        "/api/agents/ag/routines", json=_body(target={"kind": "chat", "session_id": "theirs"})
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "That chat belongs to another agent."
    resp = await client.post(
        "/api/agents/ag/routines", json=_body(target={"kind": "chat", "session_id": "nope"})
    )
    assert resp.json()["detail"][0]["msg"] == "That chat doesn't exist."


# ── PUT precedence (AC13) ─────────────────────────────────────────────────


async def test_put_name_or_prompt_leaves_next_run_alone(client) -> None:
    await _agent(client)
    row = await _make(client)
    out = (
        await client.put(
            f"/api/agents/ag/routines/{row['id']}", json={"name": "Renamed", "prompt": " new "}
        )
    ).json()
    assert (out["name"], out["prompt"]) == ("Renamed", "new")
    assert out["next_run_at"] == row["next_run_at"]
    assert out["updated_at"] == row["updated_at"]  # frozen clock: same instant


async def test_put_schedule_recomputes_and_resets_interval_anchor(client, monkeypatch) -> None:
    from the_one import time_zones

    await _agent(client)
    row = await _make(client, schedule={"kind": "interval", "hours": 6})
    later = NOW + timedelta(hours=1)
    monkeypatch.setattr(time_zones, "utcnow", lambda: later)
    # identical schedule still counts as a schedule change
    out = (
        await client.put(
            f"/api/agents/ag/routines/{row['id']}",
            json={"schedule": {"kind": "interval", "hours": 6}},
        )
    ).json()
    assert out["next_run_at"] == (later + timedelta(hours=6)).isoformat()
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        assert (await cur.fetchone())[0] == later.isoformat()
    out = (
        await client.put(f"/api/agents/ag/routines/{row['id']}", json={"schedule": DAILY})
    ).json()
    assert out["schedule"] == DAILY
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        assert (await cur.fetchone())[0] is None


async def test_put_disable_nulls_next_and_enable_recomputes_without_catch_up(
    client, monkeypatch
) -> None:
    from the_one import time_zones

    await _agent(client)
    row = await _make(client, schedule={"kind": "interval", "hours": 2})
    url = f"/api/agents/ag/routines/{row['id']}"
    off = (await client.put(url, json={"enabled": False})).json()
    assert off["enabled"] is False and off["next_run_at"] is None
    later = NOW + timedelta(days=3)
    monkeypatch.setattr(time_zones, "utcnow", lambda: later)
    on = (await client.put(url, json={"enabled": True})).json()
    assert on["enabled"] is True
    assert on["next_run_at"] == (later + timedelta(hours=2)).isoformat()  # no catch-up
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        assert (await cur.fetchone())[0] == later.isoformat()  # interval anchor reset
    # enabled: true on an already-enabled routine is a no-op
    again = (await client.put(url, json={"enabled": True})).json()
    assert again["next_run_at"] == on["next_run_at"]


async def test_finished_one_off_enable_rules(client) -> None:
    await _agent(client)
    at = (NOW + timedelta(hours=1)).isoformat()
    row = await _make(client, schedule={"kind": "once", "at": at})
    url = f"/api/agents/ag/routines/{row['id']}"
    await client.conn.execute(
        "UPDATE agent_routines SET finished_at = ?, next_run_at = NULL", (NOW.isoformat(),)
    )
    await client.conn.commit()
    resp = await client.put(url, json={"enabled": True})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "Set a new time to run it again."
    # a body without `schedule` never revalidates, and name edits work while Done
    assert (await client.put(url, json={"name": "Still done"})).json()["finished_at"] is not None
    # a new future time re-arms it
    new_at = (NOW + timedelta(hours=5)).isoformat()
    out = (
        await client.put(url, json={"schedule": {"kind": "once", "at": new_at}, "enabled": True})
    ).json()
    assert out["finished_at"] is None and out["next_run_at"] == new_at
    # a finished one-off switched to a repeating kind is also re-armed
    await client.conn.execute("UPDATE agent_routines SET finished_at = ?", (NOW.isoformat(),))
    await client.conn.commit()
    out = (await client.put(url, json={"schedule": DAILY})).json()
    assert out["finished_at"] is None and out["next_run_at"] == "2026-10-11T16:00:00+00:00"


async def test_overdue_once_awaiting_catch_up_is_not_revalidated(client) -> None:
    await _agent(client)
    at = (NOW + timedelta(hours=1)).isoformat()
    row = await _make(client, schedule={"kind": "once", "at": at})
    url = f"/api/agents/ag/routines/{row['id']}"
    await client.conn.execute(
        "UPDATE agent_routines SET schedule = ?",
        ('{"at": "2026-10-01T00:00:00+00:00", "kind": "once"}',),
    )
    await client.conn.commit()
    ok = await client.put(url, json={"prompt": "tweak"})
    assert ok.status_code == 200
    assert ok.json()["schedule"]["at"] == "2026-10-01T00:00:00+00:00"
    assert ok.json()["next_run_at"] == row["next_run_at"]
    # but an explicit schedule key is validated, so the past is refused
    resp = await client.put(url, json={"schedule": {"kind": "once", "at": "2026-10-01T00:00:00Z"}})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "That time has already passed."


async def test_put_missing_target_not_revalidated_and_bad_values_refused(client) -> None:
    await _agent(client)
    await _chat(client, "s1")
    row = await _make(client, target={"kind": "chat", "session_id": "s1"})
    url = f"/api/agents/ag/routines/{row['id']}"
    await client.delete("/api/chat/sessions/s1")
    ok = await client.put(url, json={"prompt": "still fine"})
    assert ok.status_code == 200 and ok.json()["target"]["missing"] is True
    assert (await client.put(url, json={"enabled": "x"})).status_code == 422
    assert (await client.put(url, json={"prompt": ""})).status_code == 422
    assert (await client.put(url, json={"schedule": {"kind": "x"}})).status_code == 422
    assert (
        await client.put(url, json={"target": {"kind": "chat", "session_id": "gone"}})
    ).status_code == 422


# ── runs ──────────────────────────────────────────────────────────────────


async def test_runs_newest_first_limit_cursor_and_last_run(client) -> None:
    await _agent(client)
    row = await _make(client)
    rid = row["id"]
    runs = RoutineRunRepository(client.conn)
    for i in range(5):
        await runs.insert(
            RoutineRun(
                id=f"u{i}",
                routine_id=rid,
                trigger_kind="schedule",
                outcome="ok" if i < 4 else "failed",
                reason=None if i < 4 else "boom",
                started_at=f"2026-10-0{i + 1}T00:00:00+00:00",
                finished_at=f"2026-10-0{i + 1}T00:01:00+00:00",
            )
        )
    base = f"/api/agents/ag/routines/{rid}/runs"
    out = (await client.get(base)).json()["runs"]
    assert [r["id"] for r in out] == ["u4", "u3", "u2", "u1", "u0"]
    assert set(out[0]) == {
        "id", "routine_id", "trigger_kind", "outcome", "reason", "due_at", "started_at",
        "finished_at", "session_id", "new_chat",
    }  # fmt: skip
    assert [r["id"] for r in (await client.get(base + "?limit=2")).json()["runs"]] == ["u4", "u3"]
    page = (await client.get(base + "?limit=2&before=2026-10-03T00:00:00%2B00:00")).json()["runs"]
    assert [r["id"] for r in page] == ["u1", "u0"]
    assert (await client.get(base + "?limit=0")).status_code == 422
    assert (await client.get(base + "?limit=201")).status_code == 422
    assert (await client.get(base + "?limit=200")).status_code == 200
    last = (await client.get(f"/api/agents/ag/routines/{rid}")).json()["last_run"]
    assert last == {
        "outcome": "failed", "reason": "boom", "trigger_kind": "schedule",
        "finished_at": "2026-10-05T00:01:00+00:00", "session_id": None,
    }  # fmt: skip


# ── retention surfaces (AC19-AC20) ────────────────────────────────────────


async def test_purge_now_deletes_finished_runs_and_keeps_routines(client) -> None:
    await _agent(client)
    await _agent(client, "other")
    mine = await _make(client)
    theirs = await _make(client, agent="other")
    runs = RoutineRunRepository(client.conn)
    await runs.insert(
        RoutineRun(id="a1", routine_id=mine["id"], trigger_kind="manual", outcome="ok")
    )
    await runs.insert(RoutineRun(id="a2", routine_id=mine["id"], trigger_kind="manual"))
    await runs.insert(
        RoutineRun(id="b1", routine_id=theirs["id"], trigger_kind="manual", outcome="ok")
    )
    resp = await client.delete("/api/agents/ag/chat/sessions")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "deleted": 0, "runs_deleted": 1}
    assert [r.id for r in await runs.list(mine["id"], 10)] == ["a2"]  # running row stays
    assert len(await runs.list(theirs["id"], 10)) == 1
    assert len((await client.get("/api/agents/ag/routines")).json()["routines"]) == 1


async def test_purge_sweep_seam_surfaces_runs_deleted(client, monkeypatch) -> None:
    from the_one.config import settings

    await _agent(client)
    row = await _make(client)
    old = (datetime.now(UTC) - timedelta(days=400)).isoformat()
    await RoutineRunRepository(client.conn).insert(
        RoutineRun(
            routine_id=row["id"], trigger_kind="manual", outcome="ok",
            started_at=old, finished_at=old,
        )
    )  # fmt: skip
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("THE_ONE_PURGE_SWEEP_TEST_ENDPOINT", "1")
    with patch("the_one.interfaces.web.app.get_connection", return_value=client.conn):
        resp = await client.post("/api/_test/purge-sweep")
    assert resp.status_code == 200
    assert resp.json()["runs_deleted"] == 1


# ── Run now (M33 F1 L4, AC11) ─────────────────────────────────────────────


async def test_run_route_spawns_manual_run(client, monkeypatch) -> None:
    import asyncio

    from the_one.routines import runner

    runner.registry.reset_for_test()
    await _agent(client)
    row = await _make(client)
    gate = asyncio.Event()
    calls: list[tuple] = []

    async def fake_run(rid, trigger, due_at=None):
        calls.append((rid, trigger, due_at))
        await gate.wait()

    monkeypatch.setattr(runner, "run_routine", fake_run)
    resp = await client.post(f"/api/agents/ag/routines/{row['id']}/run")
    assert resp.status_code == 202 and resp.json() == {"status": "started"}
    await asyncio.sleep(0)
    assert calls == [(row["id"], "manual", None)]
    got = (await client.get(f"/api/agents/ag/routines/{row['id']}")).json()
    assert got["running"] is True
    assert got["next_run_at"] == row["next_run_at"] and got["finished_at"] is None
    again = await client.post(f"/api/agents/ag/routines/{row['id']}/run")
    assert again.status_code == 409
    assert again.json()["detail"] == "This routine is already running."
    gate.set()
    await runner.registry.drain(1)
    runner.registry.reset_for_test()


async def test_run_route_404s(client) -> None:
    await _agent(client)
    row = await _make(client)
    assert (await client.post(f"/api/agents/nope/routines/{row['id']}/run")).status_code == 404
    assert (await client.post("/api/agents/ag/routines/nope/run")).status_code == 404


async def test_set_target_session_is_narrow(client) -> None:
    await _agent(client)
    row = await _make(client)
    from the_one.routines.repository import AgentRoutineRepository

    repo = AgentRoutineRepository(client.conn)
    await repo.set_target_session(row["id"], "abc")
    got = await repo.get_by_id(row["id"])
    assert got.target_session_id == "abc" and got.updated_at == row["updated_at"]
    await repo.set_target_session("missing", "abc")  # no-op


# ── once with a local date and time: {kind: once, on: {date, time}} (M33 F1 L9) ──


def _on(date_text: str, time_text: str) -> dict:
    return {"kind": "once", "on": {"date": date_text, "time": time_text}}


async def _post_on(client, sched):
    return await client.post("/api/agents/ag/routines", json=_body(schedule=sched))


async def test_once_on_is_converted_in_the_effective_zone(client) -> None:
    await _agent(client)
    resp = await _post_on(client, _on("2026-11-02", "09:00"))
    assert resp.status_code == 201, resp.text
    row = resp.json()
    # America/Los_Angeles is PST (UTC-8) on 2026-11-02.
    assert row["schedule"] == {"kind": "once", "at": "2026-11-02T17:00:00+00:00"}
    assert row["next_run_at"] == "2026-11-02T17:00:00+00:00"
    await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Kolkata"})
    resp = await client.post(
        "/api/agents/ag/routines", json=_body(name="k", schedule=_on("2026-11-02", "09:00"))
    )
    assert resp.json()["schedule"]["at"] == "2026-11-02T03:30:00+00:00"


async def test_once_on_gap_and_repeated_time(client) -> None:
    await _agent(client)
    # Spring forward 2027-03-14: 02:30 does not exist; the gap's end is 03:00 PDT = 10:00Z.
    gap = await client.post(
        "/api/agents/ag/routines", json=_body(name="gap", schedule=_on("2027-03-14", "02:30"))
    )
    assert gap.status_code == 201, gap.text
    assert gap.json()["schedule"]["at"] == "2027-03-14T10:00:00+00:00"
    # Fall back 2026-11-01: 01:30 happens twice; the first is PDT = 08:30Z.
    rep = await client.post(
        "/api/agents/ag/routines", json=_body(name="rep", schedule=_on("2026-11-01", "01:30"))
    )
    assert rep.json()["schedule"]["at"] == "2026-11-01T08:30:00+00:00"


async def test_once_on_past_and_too_far(client) -> None:
    await _agent(client)
    resp = await _post_on(client, _on("2026-10-10", "09:00"))  # 09:00 PDT is before now
    assert resp.status_code == 422
    assert resp.json()["detail"] == [
        {"type": "value_error", "loc": ["schedule"], "msg": "That time has already passed."}
    ]
    resp = await _post_on(client, _on("2027-12-01", "09:00"))
    assert resp.json()["detail"][0]["msg"] == "That time is more than a year away."


@pytest.mark.parametrize(
    "sched",
    [
        _on("2026-13-40", "09:00"),
        _on("20261102", "09:00"),
        _on("2026-11-02", "9am"),
        _on("2026-11-02", "25:00"),
        {"kind": "once", "on": {"date": "2026-11-02", "time": "09:00", "tz": "UTC"}},
        {"kind": "once", "on": {"date": "2026-11-02"}},
        {"kind": "once", "on": "2026-11-02 09:00"},
        {**_on("2026-11-02", "09:00"), "at": "2026-11-02T17:00:00+00:00"},
        {**_on("2026-11-02", "09:00"), "in": {"amount": 1, "unit": "hours"}},
        {"kind": "once", "on": {"date": 20261102, "time": "09:00"}},
    ],
)
async def test_once_on_malformed_is_a_schedule_422(client, sched) -> None:
    await _agent(client)
    resp = await _post_on(client, sched)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and detail[0]["loc"] == ["schedule"]


async def test_put_on_clears_finished_one_off(client) -> None:
    await _agent(client)
    at = (NOW + timedelta(hours=1)).isoformat()
    row = await _make(client, schedule={"kind": "once", "at": at})
    url = f"/api/agents/ag/routines/{row['id']}"
    await client.conn.execute(
        "UPDATE agent_routines SET finished_at = ?, next_run_at = NULL", (NOW.isoformat(),)
    )
    await client.conn.commit()
    out = await client.put(url, json={"schedule": _on("2026-11-02", "09:00")})
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["finished_at"] is None
    assert body["schedule"] == {"kind": "once", "at": "2026-11-02T17:00:00+00:00"}
    assert body["next_run_at"] == "2026-11-02T17:00:00+00:00"

"""REST tests for operator routines (M33 F1 leg 1, DD9; AC10-AC17, AC19-AC20)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._routine_schedules import daily, every_hours, once_at, once_in, weekly
from tests._schema_template import connect_template_db
from the_one.encryption import Encryptor
from the_one.routines.models import RoutineRun
from the_one.routines.repository import RoutineRunRepository

UTC = timezone.utc
# frozen_clock default: 2026-10-10T22:45:12Z, America/Los_Angeles (system mode).
NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=UTC)

DAILY = daily("09:00", "2026-10-11")
# What DAILY is stored (and returned) as at the frozen clock: the next 09:00 PDT is Oct 11.
CANON_DAILY = {
    "start": {"date": "2026-10-11", "time": "09:00"},
    "repeat": {"every": 1, "unit": "day"},
    "ends": {"kind": "never"},
}


def _in_hours(base: datetime, hours: int) -> str:
    """*hours* after *base*, rounded up to the next whole minute (a relative start's rule)."""
    t = base + timedelta(hours=hours)
    if t.second or t.microsecond:
        t = t.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return t.isoformat()


@pytest.fixture
async def env(tmp_path, frozen_clock):
    conn = await connect_template_db(tmp_path / "test.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = shared_app()
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
        **over,
    }


async def _make(client, agent="ag", **over) -> dict:
    resp = await client.post(f"/api/agents/{agent}/routines", json=_body(**over))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── create / shape ────────────────────────────────────────────────────────


async def test_create_returns_201_row_shape(client) -> None:
    await _agent(client)
    row = await _make(client)
    assert set(row) == {
        "id", "agent_name", "name", "prompt", "schedule", "schedule_text", "enabled", "finished_at",
        "next_run_at", "created_by", "created_at", "updated_at", "last_run",
        "running", "untrusted", "untrusted_sources",
    }  # fmt: skip
    assert row["schedule"] == CANON_DAILY and row["schedule_text"] == "Every day at 9:00 AM"
    assert row["prompt"] == "say hi"  # trimmed
    assert row["agent_name"] == "ag" and row["enabled"] is True
    assert row["created_by"] == "operator" and row["finished_at"] is None
    assert row["running"] is False and row["last_run"] is None
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
        "active_max": 50,
        "open_max": 200,
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
    row = await _make(client, schedule=every_hours(6))
    assert row["next_run_at"] == _in_hours(NOW, 6)
    assert row["schedule"]["repeat"] == {"every": 6, "unit": "hour"}
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        # A relative start anchors at now plus N hours, rounded up to the next whole minute.
        assert (await cur.fetchone())[0] == _in_hours(NOW, 6)


async def test_disabled_create_has_no_next_run(client) -> None:
    await _agent(client)
    row = await _make(client, enabled=False)
    assert row["enabled"] is False and row["next_run_at"] is None


async def test_once_in_converts_to_absolute_at(client) -> None:
    await _agent(client)
    row = await _make(client, schedule=once_in(90, "minutes"))
    at = "2026-10-11T00:16:00+00:00"  # now + 90 minutes, rounded up to the next whole minute
    assert row["schedule"] == {
        "start": {"date": "2026-10-10", "time": "17:16"},
        "repeat": None,
        "ends": {"kind": "never"},
    }
    assert row["next_run_at"] == at
    assert row["schedule_text"] == "Once, on Sat, Oct 10, 2026 at 5:16 PM"
    row2 = await _make(client, name="d", schedule=once_in(2, "days"))
    assert row2["next_run_at"] == "2026-10-12T22:46:00+00:00"
    # The relative start inside the canonical shape resolves the same way.
    row3 = await _make(
        client, name="e", schedule={"start": {"in": {"amount": 90, "unit": "minutes"}}}
    )
    assert row3["next_run_at"] == at


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
        {"start": {"date": "2026-10-11", "time": "9am"}},
        {**weekly([], "09:00", "2026-10-11")},
        every_hours(0),
        every_hours(169),
        {"start": {"date": "2026-11-01", "time": "10:00:00"}},
        once_in(0, "hours"),
        once_in(1, "weeks"),
        once_in(1.5, "hours"),
        once_in(True, "hours"),
    ],
)
async def test_bad_schedules_are_422_on_schedule(client, sched) -> None:
    await _agent(client)
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=sched))
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["schedule"]


async def test_once_past_and_too_far(client) -> None:
    await _agent(client)
    past = once_at("2026-10-10", "15:43")  # 15:43 PDT, before now (15:45:12)
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=past))
    assert resp.json()["detail"] == [
        {"type": "value_error", "loc": ["schedule"], "msg": "This schedule has no runs left."}
    ]
    now_exact = once_at("2026-10-10", "15:45")  # 15:45:00 PDT, a few seconds behind now
    assert (
        await client.post("/api/agents/ag/routines", json=_body(schedule=now_exact))
    ).status_code == 422
    far = once_at("2027-10-11", "15:45")  # 22:45Z a year and a day on, past the limit
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=far))
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "That time is more than a year away."
    far_in = once_in(400, "days")
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=far_in))
    assert resp.json()["detail"][0]["msg"] == "That time is more than a year away."
    huge = once_in(10**12, "days")
    resp = await client.post("/api/agents/ag/routines", json=_body(schedule=huge))
    assert resp.json()["detail"][0]["msg"] == "That time is more than a year away."
    edge = once_at("2027-10-10", "15:44")  # 22:44Z, a minute inside the limit
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


async def test_bad_enabled_shape(client) -> None:
    await _agent(client)
    assert (
        await client.post("/api/agents/ag/routines", json=_body(enabled="yes"))
    ).status_code == 422


# ── a stray ``target`` key (leg 02, AC4) ──────────────────────────────────


async def test_a_stray_target_key_is_ignored_like_any_unknown_key(client) -> None:
    await _agent(client)
    stray = {"kind": "chat", "session_id": "s1"}
    resp = await client.post("/api/agents/ag/routines", json=_body(target=stray, bogus=1))
    assert resp.status_code == 201
    row = resp.json()
    assert "target" not in row and "bogus" not in row
    url = f"/api/agents/ag/routines/{row['id']}"
    # A PUT whose only key is ``target`` is an empty update: 200, nothing changed but the
    # touch of ``updated_at``; the prompt, schedule and state stay as they were.
    out = await client.put(url, json={"target": stray})
    assert out.status_code == 200
    kept = out.json()
    assert "target" not in kept
    for key in ("name", "prompt", "schedule", "enabled", "next_run_at", "finished_at"):
        assert kept[key] == row[key]
    # alongside a real change, the real change applies and the target is dropped
    out = await client.put(url, json={"target": stray, "prompt": "new"})
    assert out.status_code == 200 and out.json()["prompt"] == "new"


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


async def test_put_schedule_recomputes_and_re_anchors_an_interval(client, monkeypatch) -> None:
    from the_one import time_zones

    await _agent(client)
    row = await _make(client, schedule=every_hours(6))
    later = NOW + timedelta(hours=1)
    monkeypatch.setattr(time_zones, "utcnow", lambda: later)
    # identical schedule still counts as a schedule change
    out = (
        await client.put(
            f"/api/agents/ag/routines/{row['id']}",
            json={"schedule": every_hours(6)},
        )
    ).json()
    assert out["next_run_at"] == _in_hours(later, 6)
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        assert (await cur.fetchone())[0] == _in_hours(later, 6)
    out = (
        await client.put(f"/api/agents/ag/routines/{row['id']}", json={"schedule": DAILY})
    ).json()
    assert out["schedule"]["repeat"] == {"every": 1, "unit": "day"}
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        assert (await cur.fetchone())[0] is None


async def test_put_disable_nulls_next_and_enable_recomputes_without_catch_up(
    client, monkeypatch
) -> None:
    from the_one import time_zones

    await _agent(client)
    row = await _make(client, schedule=every_hours(2))
    url = f"/api/agents/ag/routines/{row['id']}"
    off = (await client.put(url, json={"enabled": False})).json()
    assert off["enabled"] is False and off["next_run_at"] is None
    later = NOW + timedelta(days=3)
    monkeypatch.setattr(time_zones, "utcnow", lambda: later)
    on = (await client.put(url, json={"enabled": True})).json()
    assert on["enabled"] is True
    # The grid continues from the stored anchor (NOW + 2h): no catch-up and no re-anchor.
    assert on["next_run_at"] == _in_hours(NOW, 72)  # the anchor's 35th step, just after "later"
    async with client.conn.execute("SELECT anchor_at FROM agent_routines") as cur:
        assert (await cur.fetchone())[0] == _in_hours(NOW, 2)
    # enabled: true on an already-enabled routine is a no-op
    again = (await client.put(url, json={"enabled": True})).json()
    assert again["next_run_at"] == on["next_run_at"]


async def test_finished_one_off_enable_rules(client) -> None:
    await _agent(client)
    row = await _make(client, schedule=once_in(1, "hours"))
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
    out = (await client.put(url, json={"schedule": once_in(5, "hours"), "enabled": True})).json()
    assert out["finished_at"] is None and out["next_run_at"] == "2026-10-11T03:46:00+00:00"
    # a finished one-off switched to a repeating kind is also re-armed
    await client.conn.execute("UPDATE agent_routines SET finished_at = ?", (NOW.isoformat(),))
    await client.conn.commit()
    out = (await client.put(url, json={"schedule": DAILY})).json()
    assert out["finished_at"] is None and out["next_run_at"] == "2026-10-11T16:00:00+00:00"


async def test_overdue_once_awaiting_catch_up_is_not_revalidated(client) -> None:
    await _agent(client)
    row = await _make(client, schedule=once_in(1, "hours"))
    url = f"/api/agents/ag/routines/{row['id']}"
    past = {
        "start": {"date": "2026-09-30", "time": "17:00"},
        "repeat": None,
        "ends": {"kind": "never"},
    }
    await client.conn.execute(
        "UPDATE agent_routines SET schedule = ?, anchor_at = '2026-10-01T00:00:00+00:00'",
        (json.dumps(past),),
    )
    await client.conn.commit()
    ok = await client.put(url, json={"prompt": "tweak"})
    assert ok.status_code == 200
    assert ok.json()["schedule"] == past
    assert ok.json()["next_run_at"] == row["next_run_at"]
    # but an explicit schedule key is validated, so the past is refused
    resp = await client.put(url, json={"schedule": once_at("2026-09-30", "17:00")})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "This schedule has no runs left."


async def test_put_bad_values_refused(client) -> None:
    await _agent(client)
    row = await _make(client)
    url = f"/api/agents/ag/routines/{row['id']}"
    ok = await client.put(url, json={"prompt": "still fine"})
    assert ok.status_code == 200
    assert (await client.put(url, json={"enabled": "x"})).status_code == 422
    assert (await client.put(url, json={"prompt": ""})).status_code == 422
    assert (await client.put(url, json={"schedule": {"kind": "x"}})).status_code == 422


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
        "finished_at", "session_id", "repeats", "reason_code", "chat_exists",
    }  # fmt: skip
    assert all(r["chat_exists"] is False for r in out)  # no session ids, no chats
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
    assert resp.json() == {"status": "ok", "deleted": 0, "runs_deleted": 1, "proposals_deleted": 0}
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
    assert resp.json()["routines_deleted"] == 0 and resp.json()["proposals_deleted"] == 0


async def test_purge_now_deletes_resolved_proposals_only(client) -> None:
    await _agent(client)
    mine = await _make(client)
    for pid, status in (("p-done", "dismissed"), ("p-pend", "pending")):
        await client.conn.execute(
            "INSERT INTO agent_routine_proposals (id, agent_name, routine_id, routine_name, "
            "action, payload, status, created_at, resolved_at) "
            "VALUES (?, 'ag', ?, 'n', 'update', '{}', ?, 't', ?)",
            (pid, mine["id"], status, None if status == "pending" else "t"),
        )
    await client.conn.commit()
    resp = await client.delete("/api/agents/ag/chat/sessions")
    assert resp.json()["proposals_deleted"] == 1
    async with client.conn.execute("SELECT id FROM agent_routine_proposals") as cur:
        assert [r[0] for r in await cur.fetchall()] == ["p-pend"]
    assert len((await client.get("/api/agents/ag/routines")).json()["routines"]) == 1


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


# ── once with a local date and time: {start: {date, time}} (M33 F1 L9) ──


def _on(date_text: str, time_text: str) -> dict:
    return once_at(date_text, time_text)


async def _post_on(client, sched):
    return await client.post("/api/agents/ag/routines", json=_body(schedule=sched))


async def test_once_on_is_converted_in_the_effective_zone(client) -> None:
    await _agent(client)
    resp = await _post_on(client, _on("2026-11-02", "09:00"))
    assert resp.status_code == 201, resp.text
    row = resp.json()
    # America/Los_Angeles is PST (UTC-8) on 2026-11-02.
    assert row["schedule"] == {
        "start": {"date": "2026-11-02", "time": "09:00"},
        "repeat": None,
        "ends": {"kind": "never"},
    }
    assert row["next_run_at"] == "2026-11-02T17:00:00+00:00"
    await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Kolkata"})
    resp = await client.post(
        "/api/agents/ag/routines", json=_body(name="k", schedule=_on("2026-11-02", "09:00"))
    )
    assert resp.json()["next_run_at"] == "2026-11-02T03:30:00+00:00"


async def test_once_on_gap_and_repeated_time(client) -> None:
    await _agent(client)
    # Spring forward 2027-03-14: 02:30 does not exist; the gap's end is 03:00 PDT = 10:00Z.
    gap = await client.post(
        "/api/agents/ag/routines", json=_body(name="gap", schedule=_on("2027-03-14", "02:30"))
    )
    assert gap.status_code == 201, gap.text
    assert gap.json()["next_run_at"] == "2027-03-14T10:00:00+00:00"
    # Fall back 2026-11-01: 01:30 happens twice; the first is PDT = 08:30Z.
    rep = await client.post(
        "/api/agents/ag/routines", json=_body(name="rep", schedule=_on("2026-11-01", "01:30"))
    )
    assert rep.json()["next_run_at"] == "2026-11-01T08:30:00+00:00"


async def test_once_on_past_and_too_far(client) -> None:
    await _agent(client)
    resp = await _post_on(client, _on("2026-10-10", "09:00"))  # 09:00 PDT is before now
    assert resp.status_code == 422
    assert resp.json()["detail"] == [
        {"type": "value_error", "loc": ["schedule"], "msg": "This schedule has no runs left."}
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
        {"start": {"date": "2026-11-02", "time": "09:00", "tz": "UTC"}},
        {"start": {"date": "2026-11-02"}},
        {"start": "2026-11-02 09:00"},
        {**_on("2026-11-02", "09:00"), "at": "2026-11-02T17:00:00+00:00"},
        {**_on("2026-11-02", "09:00"), "in": {"amount": 1, "unit": "hours"}},
        {"start": {"date": 20261102, "time": "09:00"}},
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
    row = await _make(client, schedule=once_in(1, "hours"))
    url = f"/api/agents/ag/routines/{row['id']}"
    await client.conn.execute(
        "UPDATE agent_routines SET finished_at = ?, next_run_at = NULL", (NOW.isoformat(),)
    )
    await client.conn.commit()
    out = await client.put(url, json={"schedule": _on("2026-11-02", "09:00")})
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["finished_at"] is None
    assert body["schedule"]["start"] == {"date": "2026-11-02", "time": "09:00"}
    assert body["next_run_at"] == "2026-11-02T17:00:00+00:00"


# ── the preview route (M33 F3 leg 4, DD7) ─────────────────────────────────


async def _preview(client, schedule, name="ag"):
    return await client.post(f"/api/agents/{name}/routines/preview", json={"schedule": schedule})


async def test_preview_returns_the_sentence_runs_and_warnings(client) -> None:
    await _agent(client)
    sched = {
        "start": {"date": "2026-10-31", "time": "09:00"},
        "repeat": {"every": 1, "unit": "month", "month_by": {"by": "day"}},
        "ends": {"kind": "after", "count": 3},
    }
    resp = await _preview(client, sched)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["schedule"] == sched and out["anchor_at"] is None
    assert out["text"] == "Every month on day 31 at 9:00 AM, 3 times"
    assert out["next_runs"] == [
        "2026-10-31T16:00:00+00:00",
        "2026-12-31T17:00:00+00:00",  # November has no 31st: skipped
        "2027-01-31T17:00:00+00:00",
    ]
    assert out["last_occurrence"] == "2027-01-31T17:00:00+00:00"
    assert out["warnings"] == ["Some months have fewer than 31 days. Those months are skipped."]


async def test_preview_names_the_anchor_of_a_relative_start(client) -> None:
    await _agent(client)
    out = (await _preview(client, every_hours(6))).json()
    assert out["schedule"]["repeat"] == {"every": 6, "unit": "hour"}
    assert out["anchor_at"] == _in_hours(NOW, 6)
    assert out["next_runs"][0] == out["anchor_at"] and len(out["next_runs"]) == 3
    assert out["last_occurrence"] is None
    soon = (await _preview(client, {"start": {"in": {"amount": 90, "unit": "minutes"}}})).json()
    assert soon["next_runs"] == ["2026-10-11T00:16:00+00:00"] and soon["text"].startswith(
        "Once, on"
    )
    day = (await _preview(client, DAILY)).json()
    assert day["text"] == "Every day at 9:00 AM" and day["schedule"] == CANON_DAILY


async def test_preview_refuses_like_create_and_writes_nothing(client) -> None:
    await _agent(client)
    past = {"start": {"date": "2026-10-01", "time": "09:00"}}
    resp = await _preview(client, past)
    assert resp.status_code == 422
    assert resp.json()["detail"] == [
        {"type": "value_error", "loc": ["schedule"], "msg": "This schedule has no runs left."}
    ]
    bad = await _preview(client, every_hours(0))
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"] == ["schedule"]
    far = await _preview(client, {"start": {"date": "2030-01-01", "time": "09:00"}})
    assert far.json()["detail"][0]["msg"] == "That time is more than a year away."
    missing = await client.post("/api/agents/ag/routines/preview", json={})
    assert missing.status_code == 422
    assert (await client.get("/api/agents/ag/routines")).json()["routines"] == []
    async with client.conn.execute("SELECT COUNT(*) FROM agent_routine_proposals") as cur:
        assert (await cur.fetchone())[0] == 0


async def test_preview_404s_for_an_unknown_agent_and_default(client) -> None:
    assert (await _preview(client, DAILY, name="nope")).status_code == 404
    resp = await _preview(client, DAILY, name="default")
    assert resp.status_code == 404 and resp.json()["detail"] == "Agent not found: default"


async def test_reserved_names_in_any_case_are_refused(client) -> None:
    # Stored rows (as a pre-v53 database or a hand edit could leave) so the reserved-name
    # guard itself is what refuses, not the agent lookup's own 404 (squawk 0388).
    for name in ("Default", "GleepGlorp", "gleepglorp"):
        await client.conn.execute("INSERT INTO agents (name) VALUES (?)", (name,))
    await client.conn.commit()
    for name in ("Default", "GleepGlorp", "gleepglorp"):
        resp = await client.post(f"/api/agents/{name}/routines", json=_body())
        assert resp.status_code == 422, name
        assert resp.json()["detail"] == "Routines need a named agent."
        assert (await _preview(client, DAILY, name=name)).status_code == 404
        assert (await client.get(f"/api/agents/{name}/routines")).status_code == 404


async def test_preview_of_a_now_start_is_immediate(client) -> None:
    await _agent(client)
    sched = {"start": {"now": True}, "repeat": {"every": 1, "unit": "day"}}
    out = (await _preview(client, sched)).json()
    assert out["immediate"] is True and len(out["next_runs"]) == 3
    assert out["next_runs"][0] == NOW.isoformat()
    assert datetime.fromisoformat(out["next_runs"][1]) > NOW
    once = (await _preview(client, {"start": {"now": True}})).json()
    assert once["immediate"] is True and len(once["next_runs"]) == 1
    ended = {**sched, "ends": {"kind": "on", "date": "2020-01-01"}}
    assert (await _preview(client, ended)).status_code == 422
    assert (await _preview(client, DAILY)).json()["immediate"] is False


# ── the older kind-based shape is refused (M33 F4 L7) ─────────────────────

KIND_SENTENCE = (
    "A schedule is {start, repeat, ends}; the older kind-based shape is no longer accepted."
)
OLD_SHAPES = [
    {"kind": "once", "in": {"amount": 2, "unit": "hours"}},
    {"kind": "daily", "time": "09:00"},
    {"kind": "weekly", "days": [1], "time": "09:00"},
]


def _kind_refusal(resp) -> None:
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == [
        {"type": "value_error", "loc": ["schedule"], "msg": KIND_SENTENCE}
    ]


@pytest.mark.parametrize("old", OLD_SHAPES)
async def test_kind_shape_is_refused_on_create_update_and_preview(client, old) -> None:
    await _agent(client)
    _kind_refusal(await client.post("/api/agents/ag/routines", json=_body(schedule=old)))
    row = await _make(client)
    _kind_refusal(await client.put(f"/api/agents/ag/routines/{row['id']}", json={"schedule": old}))
    _kind_refusal(await _preview(client, old))
    stored = (await client.get(f"/api/agents/ag/routines/{row['id']}")).json()
    assert stored["schedule"] == CANON_DAILY


@pytest.mark.parametrize("key", ["at", "in", "on"])
async def test_a_stray_top_level_key_keeps_the_generic_refusal(client, key) -> None:
    await _agent(client)
    resp = await _preview(client, {"start": {"date": "2026-11-02", "time": "09:00"}, key: "x"})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == f"A schedule does not take '{key}'."

"""Direct tests of the routine write service (M33 F2 L1, DD3)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from tests._routine_schedules import (
    daily,
    every_hours,
    once_at,
    once_in,
    weekdays,
    weekly,
)
from tests._schema_template import connect_template_db
from the_one.naming import NameRuleError
from the_one.routines import scheduler
from the_one.routines import service as svc
from the_one.routines.limits import (
    ROUTINE_PROMPT_MAX_CHARS,
    ROUTINES_ACTIVE_MAX,
    RoutineFieldError,
    RoutineLimitError,
    RoutineNameTaken,
)
from the_one.routines.repository import AgentRoutineRepository

UTC = timezone.utc
NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=UTC)
ZONE = ZoneInfo("America/Los_Angeles")
DAILY = daily("09:00", "2026-10-11")
# A stored schedule the reader cannot understand (a row v48 could not upgrade).
UNREADABLE = {"unconverted": "yes"}
CANON_DAILY = {
    "start": {"date": "2026-10-11", "time": "09:00"},
    "repeat": {"every": 1, "unit": "day"},
    "ends": {"kind": "never"},
}


def in_hours(base: datetime, hours: int) -> str:
    """*hours* after *base*, rounded up to the next whole minute (a relative start's rule)."""
    t = base + timedelta(hours=hours)
    if t.second or t.microsecond:
        t = t.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return t.isoformat()


class StubScheduler:
    def __init__(self) -> None:
        self.pokes = 0

    def poke(self) -> None:
        self.pokes += 1


@pytest.fixture
def stub():
    s = StubScheduler()
    scheduler.set_scheduler(s)  # type: ignore[arg-type]
    yield s
    scheduler.set_scheduler(None)


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    await conn.execute("PRAGMA foreign_keys=OFF")
    yield AgentRoutineRepository(conn)
    await conn.close()


def zone_loader():
    calls = []

    async def load():
        calls.append(1)
        return ZONE

    load.calls = calls  # type: ignore[attr-defined]
    return load


def body(name="Morning", **over):
    return {"name": name, "prompt": " hi ", "schedule": DAILY, **over}


async def make(env, **over):
    return await svc.create_routine(env, "ag", body(**over), now=NOW, zone=zone_loader())


def field_error(fn, *a):
    with pytest.raises(RoutineFieldError) as ei:
        fn(*a)
    return ei.value


# ── validators ───────────────────────────────────────────────────────────
def test_prompt():
    assert svc.validate_prompt("  x ") == "x"
    assert field_error(svc.validate_prompt, "  ").message == "The prompt cannot be empty."
    assert field_error(svc.validate_prompt, 5).field == "prompt"
    long = "a" * (ROUTINE_PROMPT_MAX_CHARS + 1)
    assert field_error(svc.validate_prompt, long).message == (
        f"The prompt is limited to {ROUTINE_PROMPT_MAX_CHARS:,} characters; "
        f"this one is {len(long):,} characters."
    )


def test_enabled():
    assert svc.validate_enabled(False) is False
    e = field_error(svc.validate_enabled, "yes")
    assert (e.field, e.message) == ("enabled", "Enabled must be true or false.")


def test_schedule_refusals():
    def msg(raw):
        e = field_error(svc.validate_schedule, raw, NOW, ZONE)
        assert e.field == "schedule"
        return e.message

    assert msg({"start": 1}) == "The schedule needs a start with a date and a time."
    on = lambda d, t="09:00": once_at(d, t)  # noqa: E731
    assert msg(on("2026/12/01")) == "The date must be written YYYY-MM-DD."
    assert msg(on("2026-02-30")) == "That date doesn't exist."
    assert msg(on("2028-10-01")) == "That time is more than a year away."
    assert msg({"start": {"in": 3}}) == (
        "Give a whole number of minutes, hours or days, at least 1."
    )
    bad = once_in(0, "hours")
    assert msg(bad) == "Give a whole number of minutes, hours or days, at least 1."
    assert msg({"kind": "daily", "time": "09:00"}) == (
        "A schedule is {start, repeat, ends}; the older kind-based shape is no longer accepted."
    )


ONCE_ENDS = {"kind": "never"}


def test_schedule_conversions():
    s, anchor = svc.validate_schedule(once_in(2, "hours"), NOW, ZONE)
    assert anchor == NOW + timedelta(hours=2) + timedelta(seconds=48)  # rounded up a minute
    assert s == {
        "start": {"date": "2026-10-10", "time": "17:46"},
        "repeat": None,
        "ends": ONCE_ENDS,
    }
    on = once_at("2026-12-01", "09:00")
    s, anchor = svc.validate_schedule(on, NOW, ZONE)
    assert anchor == datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    assert s["start"] == {"date": "2026-12-01", "time": "09:00"}
    s, anchor = svc.validate_schedule(DAILY, NOW, ZONE)
    assert anchor is None and s["repeat"] == {"every": 1, "unit": "day"}
    # A schedule with and without the optional ends land on the same stored form.
    canon = {
        "start": {"date": "2026-10-11", "time": "09:00"},
        "repeat": {"every": 1, "unit": "day"},
    }
    assert svc.validate_schedule(canon, NOW, ZONE) == svc.validate_schedule(DAILY, NOW, ZONE)


def test_normalize_then_verbatim_check_round_trips_for_every_form():
    forms = [
        once_at("2026-12-01", "09:00"),
        once_in(90, "minutes"),
        daily("02:30", "2026-10-11"),
        weekdays("09:00", "2026-10-11"),
        weekly([4, 0], "09:00", "2026-10-11"),
        every_hours(5),
    ]
    for raw in forms:
        sched, anchor = svc.validate_schedule(raw, NOW, ZONE)
        assert svc.check_schedule_pair(sched, anchor) == sched


# ── create ───────────────────────────────────────────────────────────────
async def test_create_ignores_a_stray_target_and_pokes(env, stub):
    r = await make(env, name="a")
    assert r.prompt == "hi" and r.created_by
    # A request that still carries ``target`` is read like any unknown key (leg 02, AC4).
    r = await make(env, name="b", target={"kind": "chat", "session_id": "s2"})
    assert not any(k.startswith("target") for k in r.model_dump()) and r.name == "b"
    assert stub.pokes == 2


async def test_create_interval_anchor_and_next(env):
    r = await make(env, schedule=every_hours(3))
    # A relative start anchors at now plus N hours, rounded up to the next whole minute.
    assert r.anchor_at == in_hours(NOW, 3)
    assert r.next_run_at == in_hours(NOW, 3)
    assert r.schedule["repeat"] == {"every": 3, "unit": "hour"}
    r = await make(env, name="d", enabled=False)
    assert r.next_run_at is None and r.anchor_at is None
    off = await make(env, name="e", enabled=False, schedule=every_hours(3))
    assert off.next_run_at is None and off.anchor_at is not None


async def test_create_refusals_do_not_poke(env, stub):
    for over, exc in [
        ({"name": "  "}, NameRuleError),
        ({"prompt": ""}, RoutineFieldError),
    ]:
        with pytest.raises(exc):
            await svc.create_routine(env, "ag", body(**over), now=NOW, zone=zone_loader())
    assert stub.pokes == 0


async def test_create_error_order(env):
    bad = {"name": "", "prompt": "", "schedule": 1, "enabled": 1}
    with pytest.raises(NameRuleError):
        await svc.create_routine(env, "ag", bad, now=NOW, zone=zone_loader())
    bad["name"] = "ok"
    with pytest.raises(RoutineFieldError) as ei:
        await svc.create_routine(env, "ag", bad, now=NOW, zone=zone_loader())
    assert ei.value.field == "prompt"
    bad["prompt"] = "p"
    for field in ("schedule", "enabled"):
        bad["schedule"] = DAILY if field != "schedule" else 1
        bad["enabled"] = True if field != "enabled" else 1
        with pytest.raises(RoutineFieldError) as ei:
            await svc.create_routine(env, "ag", bad, now=NOW, zone=zone_loader())
        assert ei.value.field == field


async def test_duplicate_and_active_cap(env, stub):
    await make(env)
    with pytest.raises(RoutineNameTaken):
        await make(env)
    for i in range(ROUTINES_ACTIVE_MAX - 1):
        await make(env, name=f"r{i}")
    pokes = stub.pokes
    with pytest.raises(RoutineLimitError):
        await make(env, name="over")
    assert stub.pokes == pokes


# ── update ───────────────────────────────────────────────────────────────
async def upd(env, cur, data, zone=None, now=NOW):
    return await svc.update_routine(env, "ag", cur, data, now=now, zone=zone or zone_loader())


async def test_update_name_only_skips_zone(env, stub):
    r = await make(env)
    z = zone_loader()
    out = await upd(env, r, {"name": "New"}, zone=z)
    assert out.name == "New" and z.calls == [] and stub.pokes == 2


async def test_update_schedule_change_clears_done(env):
    repo = env
    r = await make(env, schedule=once_in(1, "hours"))
    done = await repo.update("ag", r.id, {"finished_at": NOW.isoformat(), "next_run_at": None})
    out = await upd(env, done, {"schedule": DAILY})
    assert out.finished_at is None and out.next_run_at is not None


async def test_update_reenable_done_refused(env, stub):
    repo = env
    r = await make(env, schedule=once_in(1, "hours"))
    done = await repo.update(
        "ag", r.id, {"finished_at": NOW.isoformat(), "next_run_at": None, "enabled": False}
    )
    pokes = stub.pokes
    with pytest.raises(RoutineFieldError) as ei:
        await upd(env, done, {"enabled": True})
    assert ei.value.message == "Set a new time to run it again."
    assert stub.pokes == pokes


async def test_update_interval_reenable_continues_the_grid(env):
    r = await make(env, schedule=every_hours(2))
    anchor = r.anchor_at
    off = await upd(env, r, {"enabled": False})
    assert off.next_run_at is None
    later = NOW + timedelta(hours=5)
    on = await upd(env, off, {"enabled": True}, now=later)
    assert on.anchor_at == anchor  # never re-anchored
    # anchor = NOW + 2h; the grid is every 2h from there; the next after NOW + 5h is NOW + 6h.
    assert on.next_run_at == in_hours(NOW, 6)


async def test_update_reenable_past_oneoff_is_refused(env):
    repo = env
    r = await make(env, schedule=once_in(1, "hours"))
    off = await repo.update("ag", r.id, {"enabled": False})
    later = NOW + timedelta(hours=3)
    with pytest.raises(RoutineFieldError) as ei:
        await upd(env, off, {"enabled": True}, now=later)
    assert (ei.value.field, ei.value.message) == ("enabled", "This schedule has no runs left.")


async def test_create_and_schedule_edit_with_no_runs_left_are_refused_on_or_off(env):
    past = {"start": {"date": "2026-10-01", "time": "09:00"}}
    for enabled in (True, False):
        with pytest.raises(RoutineFieldError) as ei:
            await make(env, schedule=past, enabled=enabled)
        assert (ei.value.field, ei.value.message) == ("schedule", "This schedule has no runs left.")
    r = await make(env)
    with pytest.raises(RoutineFieldError) as ei:
        await upd(env, r, {"schedule": past})
    assert ei.value.field == "schedule"
    ended = {
        "start": {"date": "2026-10-01", "time": "09:00"},
        "repeat": {"every": 1, "unit": "day"},
        "ends": {"kind": "after", "count": 3},
    }
    with pytest.raises(RoutineFieldError):
        await make(env, schedule=ended)


async def test_reenable_a_routine_with_an_unreadable_schedule_is_refused(env):
    repo = env
    r = await make(env)
    unreadable = await repo.update("ag", r.id, {"schedule": UNREADABLE, "enabled": False})
    with pytest.raises(RoutineFieldError) as ei:
        await upd(env, unreadable, {"enabled": True})
    assert ei.value.field == "enabled" and "could not be upgraded" in ei.value.message


async def test_update_refusals_and_missing(env):
    r = await make(env)
    await make(env, name="other")
    with pytest.raises(NameRuleError):
        await upd(env, r, {"name": ""})
    with pytest.raises(RoutineNameTaken):
        await upd(env, r, {"name": "other"})
    repo = env
    await svc.delete_routine(repo, "ag", r.id)
    with pytest.raises(KeyError):
        await upd(env, r, {"name": "zzz"})


# ── delete, view, limits ─────────────────────────────────────────────────
async def test_delete_pokes_once(env, stub):
    repo = env
    r = await make(env)
    stub.pokes = 0
    assert await svc.delete_routine(repo, "ag", r.id) is None
    assert stub.pokes == 1
    with pytest.raises(KeyError):
        await svc.delete_routine(repo, "ag", r.id)
    assert stub.pokes == 1


async def test_view_and_limits(env):
    from the_one.routines.repository import RoutineRunRepository

    repo = env
    r = await make(env)
    view = await svc.routine_view(r, RoutineRunRepository(repo.conn), ZONE)
    assert view["name"] == "Morning" and view["last_run"] is None
    assert view["schedule_text"] == "Every day at 9:00 AM"
    unreadable = r.model_copy(update={"schedule": UNREADABLE})  # v48 could not upgrade it
    bad = await svc.routine_view(unreadable, RoutineRunRepository(repo.conn), ZONE)
    assert bad["schedule_text"] is None
    assert "target" not in view and view["running"] is False
    limits = svc.limits_view()
    assert limits["active_max"] == ROUTINES_ACTIVE_MAX and limits["open_max"] == 200
    assert "routines_per_agent" not in limits


def test_poke_without_scheduler():
    scheduler.set_scheduler(None)
    svc.poke_scheduler()


# ── agent changes (M33 F2 L2, DD4-DD8) ────────────────────────────────────
from the_one.agent.config import AgentConfig  # noqa: E402
from the_one.db.repositories import SQLiteAgentStore  # noqa: E402
from the_one.routines.proposals import (  # noqa: E402
    ProposalGoneError,
    ProposalStaleError,
    ProposalStateError,
    RoutineProposalRepository,
)

CLEAN = (False, [])
DIRTY = (True, ["web:example.org"])


@pytest.fixture
async def aenv(tmp_path, frozen_clock):
    conn = await connect_template_db(tmp_path / "a.db")
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="ag"))
    await store.save(AgentConfig(name="other"))
    await store.set_routines_self_config("ag", enabled=True, requires_approval=False)
    yield conn, AgentRoutineRepository(conn), RoutineProposalRepository(conn), store
    await conn.close()


async def change(conn, action, data, taint=CLEAN, agent="ag", zone=None, now=NOW):
    return await svc.agent_change(
        conn,
        agent,
        action,
        data,
        now=now,
        zone=zone or zone_loader(),
        taint=taint,
        session_id="s1",
    )


async def approve(conn, pid, override=False, agent="ag", now=NOW):
    return await svc.approve_proposal(
        conn, agent, pid, override=override, now=now, zone=zone_loader()
    )


async def test_agent_create_applied(aenv, stub):
    conn, repo, props, _ = aenv
    res = await change(conn, "create", body(schedule=once_in(2, "hours")))
    assert res.pending is False and res.routine.created_by == "agent"
    assert res.routine.untrusted is False
    [p] = await props.list("ag")
    assert p.status == "applied" and p.routine_id == res.routine.id and p.action == "create"
    # Normalized once: the proposal row and the stored routine carry the same pair.
    assert p.payload["schedule"] == res.routine.schedule
    assert p.payload["schedule"]["start"] == {"date": "2026-10-10", "time": "17:46"}
    assert p.payload["anchor_at"] == res.routine.anchor_at == "2026-10-11T00:46:00+00:00"
    assert "target" not in p.payload and p.session_id == "s1"
    assert stub.pokes == 1


async def test_agent_update_applied_with_flag_merge_never_clears(aenv, stub):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body())).routine
    res = await change(conn, "update", {"routine": r.id, "prompt": "new"}, taint=DIRTY)
    assert res.routine.prompt == "new" and res.routine.untrusted is True
    assert res.routine.untrusted_sources == ["web:example.org"]
    # A clean agent update with prompt does NOT clear the flag.
    res = await change(conn, "update", {"routine": "morning", "prompt": "again"})
    assert res.routine.untrusted is True
    [upd] = [p for p in await props.list("ag") if p.payload == {"prompt": "again"}]
    assert upd.action == "update" and upd.base["prompt"] == "new"


async def test_agent_delete_applied(aenv, stub):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body())).routine
    pokes = stub.pokes
    res = await change(conn, "delete", {"routine": "MORNING"})
    assert res.pending is False and await repo.get("ag", r.id) is None
    [p] = [p for p in await props.list("ag") if p.action == "delete"]
    assert p.action == "delete" and p.routine_id is None and p.routine_name == "Morning"
    assert p.status == "applied" and stub.pokes == pokes + 1


async def test_agent_change_failure_leaves_no_partial_row(aenv):
    conn, repo, props, _ = aenv
    r = await repo.create("ag", {"name": "x", "prompt": "p", "schedule": DAILY})

    class Boom:
        proposal_id = None

        async def run(self, conn, routine_id):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await svc.create_routine(
            repo,
            "ag",
            body("Y"),
            now=NOW,
            zone=zone_loader(),
            created_by="agent",
            agent_caps=True,
            proposal=Boom(),  # type: ignore[arg-type]
        )
    assert [x.name for x in await repo.list_for_agent("ag")] == [r.name]
    assert await props.list("ag") == []


async def test_agent_change_pending(aenv, stub):
    conn, repo, props, store = aenv
    await store.set_routines_self_config("ag", requires_approval=True)
    res = await change(conn, "create", body())
    assert res.pending is True and res.routine is None and res.proposal_id
    assert await repo.list_for_agent("ag") == []
    assert await repo.list_due("9999-01-01T00:00:00+00:00") == []
    assert stub.pokes == 0
    # a pending create blocks update/delete of that name, with the pending sentence
    with pytest.raises(RoutineFieldError, match="still waiting for your operator"):
        await change(conn, "update", {"routine": "morning", "prompt": "x"})
    with pytest.raises(RoutineFieldError, match="There's no routine called 'Nope'"):
        await change(conn, "delete", {"routine": "Nope"})
    ok = await approve(conn, res.proposal_id)
    assert ok.status == "applied"
    r = (await repo.list_for_agent("ag"))[0]
    assert r.created_by == "agent" and ok.routine_id == r.id
    first = await change(conn, "update", {"routine": r.id, "prompt": "one"})
    second = await change(conn, "update", {"routine": r.id, "prompt": "two"})
    assert first.replaced is False and second.replaced is True
    assert (await props.get(first.proposal_id)).status == "superseded"


async def test_pending_limit_sentence(aenv):
    conn, _repo, _props, store = aenv
    await store.set_routines_self_config("ag", requires_approval=True)
    for i in range(20):
        await change(conn, "create", body(f"R{i}"))
    with pytest.raises(RoutineLimitError, match="You have 20 changes waiting for approval."):
        await change(conn, "create", body("R20"))


async def test_call_time_switch(aenv):
    conn, repo, props, store = aenv
    await store.set_routines_self_config("ag", enabled=False)
    for action, data in (
        ("create", body()),
        ("update", {"routine": "x", "prompt": "p"}),
        ("delete", {"routine": "x"}),
    ):
        with pytest.raises(RoutineFieldError, match="Routine tools are turned off for this agent."):
            await change(conn, action, data)
    assert await repo.list_for_agent("ag") == [] and await props.list("ag") == []
    await SQLiteAgentStore(conn).save(AgentConfig(name="default"))
    with pytest.raises(RoutineFieldError, match="Routines need a named agent."):
        await change(conn, "create", body(), agent="default")
    for reserved in ("Default", "GleepGlorp"):
        with pytest.raises(RoutineFieldError, match="Routines need a named agent."):
            await change(conn, "create", body(), agent=reserved)


async def test_caps_agent_creates(aenv):
    conn, repo, _props, _ = aenv
    for i in range(ROUTINES_ACTIVE_MAX):
        await change(conn, "create", body(f"R{i}"))
    with pytest.raises(RoutineLimitError, match="50 active routines"):
        await change(conn, "create", body("R51"))


async def test_caps_never_block_lowering_edits(aenv):
    conn, repo, _props, _ = aenv
    # An agent already over the active cap (the old limit was 50 in total): seed past it.
    ids = []
    for i in range(ROUTINES_ACTIVE_MAX):
        r = await repo.create(
            "ag",
            {
                "name": f"op{i}",
                "prompt": "p",
                "schedule": every_hours(1),
            },
        )
        ids.append(r.id)
    for i in range(3):
        await conn.execute(
            "INSERT INTO agent_routines (id, agent_name, name, prompt, schedule, "
            "created_by, created_at, updated_at) VALUES (?, 'ag', ?, 'p', '{}', "
            "'operator', 't', 't')",
            (f"seed{i}", f"seed{i}"),
        )
    await conn.commit()
    await change(conn, "update", {"routine": ids[0], "name": "renamed"})
    await change(conn, "update", {"routine": ids[1], "prompt": "edited"})
    await change(conn, "update", {"routine": ids[2], "schedule": every_hours(6)})
    await change(conn, "update", {"routine": ids[3], "enabled": False})
    with pytest.raises(RoutineLimitError):
        await change(conn, "create", body("one more"))


async def test_once_minimum_ahead_for_agent_only(aenv):
    conn, repo, _props, _ = aenv
    soon = once_in(1, "minutes")
    # a minute away is allowed ("at least a minute"); under a minute is not (15:46 PDT is 48 s on)
    sub = once_at("2026-10-10", "15:46")
    with pytest.raises(RoutineFieldError, match="at least a minute away"):
        await change(conn, "create", body(schedule=sub))
    await change(conn, "create", body("Ok", schedule=soon))
    # the operator path accepts it
    await svc.create_routine(
        repo, "ag", body("Op", schedule=sub), now=NOW, zone=zone_loader()
    )  # fmt: skip


async def test_agent_validation_matches_operator(aenv):
    conn, _repo, _props, _ = aenv
    with pytest.raises(NameRuleError):
        await change(conn, "create", body("a/b"))
    with pytest.raises(RoutineFieldError):
        await change(conn, "create", body(prompt=" "))
    with pytest.raises(RoutineFieldError):
        await change(conn, "update", {"routine": "nope", "prompt": "x"})
    r = (await change(conn, "create", body())).routine
    with pytest.raises(RoutineFieldError, match="Say what to change"):
        await change(conn, "update", {"routine": r.id})


async def pend(aenv, action, data):
    conn, _repo, _props, store = aenv
    await store.set_routines_self_config("ag", requires_approval=True)
    res = await change(conn, action, data)
    assert res.pending
    return res.proposal_id


async def test_approve_checks(aenv):
    conn, repo, props, store = aenv
    pid = await pend(aenv, "create", body())
    with pytest.raises(KeyError):
        await approve(conn, pid, agent="other")
    with pytest.raises(KeyError):
        await approve(conn, "nope")
    first = await approve(conn, pid)
    again = await approve(conn, pid)  # idempotent
    assert first.id == again.id and again.status == "applied"
    assert len(await repo.list_for_agent("ag")) == 1
    pid2 = await pend(aenv, "create", body("Two"))
    await svc.dismiss_proposal(conn, "ag", pid2)
    with pytest.raises(ProposalStateError):
        await approve(conn, pid2)
    pid3 = await pend(aenv, "create", body("Three"))
    await props.supersede_pending("ag")
    with pytest.raises(ProposalStateError):
        await approve(conn, pid3)


async def test_approve_stale_then_override(aenv):
    conn, repo, props, store = aenv
    r = (await change(conn, "create", body())).routine
    pid = await pend(aenv, "update", {"routine": r.id, "prompt": "agent text"})
    await repo.update("ag", r.id, {"prompt": "operator edit"})
    with pytest.raises(ProposalStaleError) as ei:
        await approve(conn, pid)
    assert ei.value.current == {"prompt": "operator edit"}
    assert ei.value.base == {"prompt": "hi"}
    assert ei.value.proposed == {"prompt": "agent text"}
    assert (await props.get(pid)).status == "pending"
    done = await approve(conn, pid, override=True)
    assert done.status == "applied" and (await repo.get("ag", r.id)).prompt == "agent text"


async def test_approve_unrelated_drift_is_not_stale(aenv):
    conn, repo, _props, _ = aenv
    r = (await change(conn, "create", body())).routine
    pid = await pend(aenv, "update", {"routine": r.id, "prompt": "agent text"})
    await repo.update("ag", r.id, {"name": "Renamed"})  # a key the payload does not touch
    await approve(conn, pid)
    got = await repo.get("ag", r.id)
    assert got.prompt == "agent text" and got.name == "Renamed"


async def test_approve_gone(aenv):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body())).routine
    pid = await pend(aenv, "update", {"routine": r.id, "prompt": "x"})
    # Make it gone without the delete's supersede, to hit the approval-time path.
    await conn.execute("PRAGMA foreign_keys=OFF")
    await conn.execute("DELETE FROM agent_routines WHERE id = ?", (r.id,))
    await conn.commit()
    with pytest.raises(ProposalGoneError):
        await approve(conn, pid)
    assert (await props.get(pid)).status == "superseded"
    # a gone delete is a no-op that supersedes and returns
    r2 = await repo.create("ag", {"name": "Second", "prompt": "p", "schedule": CANON_DAILY})
    pid2 = await pend(aenv, "delete", {"routine": r2.id})
    await conn.execute("DELETE FROM agent_routines WHERE id = ?", (r2.id,))
    await conn.commit()
    done = await approve(conn, pid2)
    assert done.status == "superseded"


async def test_approve_past_at_stays_pending(aenv):
    conn, _repo, props, _ = aenv
    pid = await pend(aenv, "create", body(schedule=once_in(2, "hours")))
    with pytest.raises(RoutineFieldError) as ei:
        await approve(conn, pid, now=NOW + timedelta(hours=3))
    assert (ei.value.field, ei.value.message) == ("schedule", "This schedule has no runs left.")
    assert (await props.get(pid)).status == "pending"


async def test_approve_no_runs_left_wins_over_a_stale_conflict(aenv):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body(schedule=once_in(2, "hours")))).routine
    pid = await pend(
        aenv,
        "update",
        {"routine": r.id, "schedule": once_in(5, "hours")},
    )
    await repo.update("ag", r.id, {"prompt": "operator edit"})
    await repo.update("ag", r.id, {"anchor_at": (NOW + timedelta(hours=1)).isoformat()})
    with pytest.raises(RoutineFieldError) as ei:  # not ProposalStaleError
        await approve(conn, pid, now=NOW + timedelta(hours=9))
    assert ei.value.message == "This schedule has no runs left."
    assert (await props.get(pid)).status == "pending"


async def test_approve_applies_the_proposed_pair_verbatim(aenv):
    conn, repo, props, _ = aenv
    pid = await pend(aenv, "create", body(schedule=every_hours(3)))
    payload = (await props.get(pid)).payload
    assert payload["anchor_at"] == in_hours(NOW, 3)
    # Approved much later: the grid still starts where the proposal fixed it (not at approval).
    await approve(conn, pid, now=NOW + timedelta(hours=4))
    [got] = await repo.list_for_agent("ag")
    assert got.anchor_at == payload["anchor_at"] and got.schedule == payload["schedule"]
    assert got.next_run_at == in_hours(NOW, 6)


async def test_approve_rerenders_start_in_the_current_zone(aenv):
    conn, repo, props, _ = aenv
    pid = await pend(aenv, "create", body(schedule=once_in(2, "hours")))
    payload = (await props.get(pid)).payload
    assert payload["schedule"]["start"] == {"date": "2026-10-10", "time": "17:46"}  # Los Angeles
    tokyo = ZoneInfo("Asia/Tokyo")

    async def load():
        return tokyo

    await svc.approve_proposal(conn, "ag", pid, override=False, now=NOW, zone=load)
    [got] = await repo.list_for_agent("ag")
    assert got.anchor_at == payload["anchor_at"]  # the instant never moves
    assert got.schedule["start"] == {"date": "2026-10-11", "time": "09:46"}


async def test_schedule_stale_check_includes_the_anchor(aenv):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body(schedule=every_hours(2)))).routine
    pid = await pend(aenv, "update", {"routine": r.id, "schedule": DAILY})
    # The operator re-anchors the same recurrence: only anchor_at differs.
    await repo.update("ag", r.id, {"anchor_at": (NOW + timedelta(hours=1)).isoformat()})
    with pytest.raises(ProposalStaleError) as ei:
        await approve(conn, pid)
    assert set(ei.value.current) == {"schedule", "anchor_at", "finished_at"}
    assert ei.value.base["anchor_at"] == r.anchor_at


async def test_approve_name_taken_and_caps_recheck(aenv):
    conn, repo, props, _ = aenv
    pid = await pend(aenv, "create", body("Dup"))
    await repo.create("ag", {"name": "dup", "prompt": "p", "schedule": CANON_DAILY})
    with pytest.raises(RoutineNameTaken):
        await approve(conn, pid)
    assert (await props.get(pid)).status == "pending"
    pid2 = await pend(aenv, "create", body("Late"))
    for i in range(ROUTINES_ACTIVE_MAX - 1):  # plus the existing 'dup' makes 50
        await repo.create("ag", {"name": f"f{i}", "prompt": "p", "schedule": CANON_DAILY})
    with pytest.raises(RoutineLimitError):
        await approve(conn, pid2)
    assert (await props.get(pid2)).status == "pending"


async def test_approve_merges_flag_and_pokes(aenv, stub):
    conn, repo, _props, store = aenv
    await store.set_routines_self_config("ag", requires_approval=True)
    res = await change(conn, "create", body(), taint=DIRTY)
    r = await approve(conn, res.proposal_id)
    created = await repo.get("ag", r.routine_id)
    assert created.untrusted is True and created.untrusted_sources == ["web:example.org"]
    assert stub.pokes == 1
    res = await change(conn, "update", {"routine": created.id, "prompt": "p2"})
    await approve(conn, res.proposal_id)
    again = await repo.get("ag", created.id)
    assert again.untrusted is True and again.prompt == "p2"  # approve never clears


async def test_approve_delete_and_dismiss_rules(aenv):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body())).routine
    pid = await pend(aenv, "delete", {"routine": r.id})
    done = await approve(conn, pid)
    assert done.status == "applied" and await repo.get("ag", r.id) is None
    assert done.routine_id is None
    pid2 = await pend(aenv, "create", body("Other"))
    d1 = await svc.dismiss_proposal(conn, "ag", pid2)
    d2 = await svc.dismiss_proposal(conn, "ag", pid2)
    assert d1.status == d2.status == "dismissed"
    with pytest.raises(ProposalStateError):
        await svc.dismiss_proposal(conn, "ag", pid)  # applied
    with pytest.raises(KeyError):
        await svc.dismiss_proposal(conn, "other", pid2)


async def test_operator_delete_supersedes_pending_via_service(aenv):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body())).routine
    pid = await pend(aenv, "update", {"routine": r.id, "prompt": "x"})
    await svc.delete_routine(repo, "ag", r.id)
    assert (await props.get(pid)).status == "superseded"


# ── "Immediately" (M33 F4 L4): the operator's now-start ─────────────────────
def _now_schedule(repeat, ends=None):
    return {"start": {"now": True}, "repeat": repeat, "ends": ends or {"kind": "never"}}


async def test_now_start_repeating_is_due_at_the_save_instant(env):
    daily = await make(env, schedule=_now_schedule({"every": 1, "unit": "day"}))
    # The grid starts at the save minute (15:45 PDT), the first run is the exact instant.
    assert daily.schedule["start"] == {"date": "2026-10-10", "time": "15:45"}
    assert daily.next_run_at == NOW.isoformat() and daily.anchor_at is None
    hourly = await make(env, name="h", schedule=_now_schedule({"every": 2, "unit": "hour"}))
    assert hourly.anchor_at == NOW.replace(second=0).isoformat()
    assert hourly.next_run_at == NOW.isoformat()


async def test_now_start_one_off_is_due_now_and_keeps_the_save_minute(env):
    r = await make(env, schedule=_now_schedule(None))
    assert r.schedule["repeat"] is None
    assert r.schedule["start"] == {"date": "2026-10-10", "time": "15:45"}
    assert r.next_run_at == NOW.isoformat()


async def test_now_start_with_an_ended_rule_and_twice(env):
    # Saturday the save day; a Monday-only rule that ends today has no run left.
    past = _now_schedule(
        {"every": 1, "unit": "week", "days": [0]}, {"kind": "on", "date": "2026-10-10"}
    )
    with pytest.raises(RoutineFieldError, match="no runs left"):
        await make(env, schedule=past)
    a = await make(env, name="a", schedule=_now_schedule(None))
    b = await make(env, name="b", schedule=_now_schedule(None))
    assert a.next_run_at == b.next_run_at == NOW.isoformat() and a.id != b.id


async def test_now_start_on_update_reruns_done_and_not_disabled(env):
    r = await make(env, schedule=_now_schedule(None))
    done = await env.update("ag", r.id, {"finished_at": NOW.isoformat(), "next_run_at": None})
    later = NOW + timedelta(hours=1)
    out = await upd(env, done, {"schedule": _now_schedule(None)}, now=later)
    assert out.finished_at is None and out.next_run_at == later.isoformat()
    off = await make(env, name="off", enabled=False, schedule=DAILY)
    out = await upd(env, off, {"schedule": _now_schedule({"every": 1, "unit": "day"})})
    assert out.enabled is False and out.next_run_at is None
    assert out.schedule["start"] == {"date": "2026-10-10", "time": "15:45"}


async def test_the_agent_path_refuses_a_now_start(aenv):
    conn, repo, props, _ = aenv
    for action, data in (
        ("create", body(schedule={"start": {"now": True}})),
        ("update", None),
    ):
        if action == "update":
            made = await change(conn, "create", body("target"))
            data = {"routine": made.routine.id, "schedule": {"start": {"now": True}}}
        with pytest.raises(
            RoutineFieldError, match="The schedule needs a start with a date and a time."
        ):
            await change(conn, action, data)
    # Only the setup create left rows: the refusals wrote nothing.
    assert len(await repo.list_for_agent("ag")) == 1 and len(await props.list("ag")) == 1


# ── log lines (M34 F2 L2) ──


def _plines(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "the_one.routines.service" and r.levelno == logging.INFO
    ]


async def test_log_agent_change_applied(aenv, caplog):
    conn, repo, props, _ = aenv
    with caplog.at_level(logging.INFO, logger="the_one.routines.service"):
        res = await change(conn, "create", body(schedule=once_in(2, "hours")), taint=DIRTY)
    [p] = await props.list("ag")
    assert _plines(caplog) == [
        f"routine proposal={p.id} agent='ag' action=create decision=applied flagged=True "
        f"routine={res.routine.id}"
    ]


async def test_log_agent_change_pending(aenv, caplog):
    conn, _repo, _props, store = aenv
    await store.set_routines_self_config("ag", requires_approval=True)
    with caplog.at_level(logging.INFO, logger="the_one.routines.service"):
        res = await change(conn, "create", body())
    assert _plines(caplog) == [
        f"routine proposal={res.proposal_id} agent='ag' action=create decision=pending "
        "flagged=False routine=none"
    ]


async def test_log_approve_and_dismiss(aenv, caplog):
    conn, repo, props, _ = aenv
    pid = await pend(aenv, "create", body())
    pid2 = await pend(aenv, "create", body("Two"))
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="the_one.routines.service"):
        done = await approve(conn, pid)
        await svc.dismiss_proposal(conn, "ag", pid2)
    assert _plines(caplog) == [
        f"routine proposal={pid} agent='ag' action=create decision=approved flagged=False "
        f"routine={done.routine_id}",
        f"routine proposal={pid2} agent='ag' action=create decision=dismissed flagged=False "
        "routine=none",
    ]


async def test_log_approve_superseded(aenv, caplog):
    conn, repo, props, _ = aenv
    r = (await change(conn, "create", body())).routine
    pid = await pend(aenv, "delete", {"routine": r.id})
    await repo.delete("ag", r.id)  # bypasses the supersede: the proposal still reads pending
    await conn.execute("UPDATE agent_routine_proposals SET status = 'pending' WHERE id = ?", (pid,))
    await conn.commit()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="the_one.routines.service"):
        done = await approve(conn, pid)
    assert done.status == "superseded"
    assert _plines(caplog) == [
        f"routine proposal={pid} agent='ag' action=delete decision=superseded flagged=False "
        "routine=none"  # the deleted routine's id is already cleared from the proposal row
    ]

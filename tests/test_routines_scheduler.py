"""The routine scheduler (M33 F1 leg 5, AC1-AC8): pure passes over a template DB with an
injected clock, a fake spawn and a recording sleep seam; lifespan cases over ``routine_app``."""

# ruff: noqa: F811
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from tests._routine_app import routine_app, wait_for  # noqa: F401
from tests._routine_schedules import once_in
from tests._schema_template import connect_template_db
from the_one import time_zones
from the_one.agent.config import AgentConfig
from the_one.db.repositories import AppMetadataRepository, SQLiteAgentStore
from the_one.routines import runner
from the_one.routines.models import RoutineRun
from the_one.routines.repository import AgentRoutineRepository, RoutineRunRepository
from the_one.routines.scheduler import ZONE_KEY, RoutineScheduler, next_sleep

pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")

UTC = timezone.utc
NEVER = {"kind": "never"}
# The stored (canonical) shapes the pass reads. The env zone is UTC.
DAILY = {
    "start": {"date": "2026-03-01", "time": "09:00"},
    "repeat": {"every": 1, "unit": "day"},
    "ends": NEVER,
}


def _every(n, unit, anchor, ends=None):
    """An instant-anchored series; *anchor* is also passed as ``anchor_at`` by the caller."""
    return {
        "start": {"date": anchor.date().isoformat(), "time": anchor.strftime("%H:%M")},
        "repeat": {"every": n, "unit": unit},
        "ends": ends or NEVER,
    }


def _once(at):
    return {
        "start": {"date": at.date().isoformat(), "time": at.strftime("%H:%M")},
        "repeat": None,
        "ends": NEVER,
    }


def _daily(ends=None, time="09:00", start="2026-03-01"):
    return {**DAILY, "start": {"date": start, "time": time}, "ends": ends or NEVER}


def _dt(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


class Spawner:
    def __init__(self, refuse: bool = False) -> None:
        self.calls: list[str] = []
        self.refuse = refuse

    def __call__(self, rid, factory):
        self.calls.append(rid)
        if self.refuse:
            return None
        return object()


@pytest.fixture
async def env(tmp_path, monkeypatch):
    conn = await connect_template_db(tmp_path / "t.db")
    await SQLiteAgentStore(conn).save(AgentConfig(name="a"))
    await time_zones.save_setting(conn, time_zones.TimeZoneSetting(mode="zone", zone="UTC"))
    spawn = Spawner()

    async def factory():
        return conn

    sleeps: list[float] = []

    async def sleep(s):
        sleeps.append(s)

    clock = [_dt(2026, 3, 1, 9, 0, 30)]
    sched = RoutineScheduler(lambda: clock[0], spawn, factory, sleep)
    e = type("E", (), {})()
    e.conn, e.spawn, e.sleeps, e.clock, e.sched = conn, spawn, sleeps, clock, sched
    e.repo = AgentRoutineRepository(conn)
    e.runs = RoutineRunRepository(conn)
    yield e
    await conn.close()


async def _mk(e, name="R", schedule=None, due=None, **extra):
    schedule = schedule or DAILY
    anchor = extra.pop("anchor_at", None)
    return await e.repo.create(
        "a",
        {
            "name": name,
            "prompt": "p",
            "schedule": schedule,
            "next_run_at": due.isoformat() if due else None,
            "anchor_at": anchor,
            **extra,
        },
    )


async def _runs(e, rid):
    return await e.runs.list(rid)


def test_next_sleep_clamps() -> None:
    now = _dt(2026, 3, 1)
    assert next_sleep(now, None) == 60
    assert next_sleep(now, now + timedelta(seconds=600)) == 60
    assert next_sleep(now, now + timedelta(seconds=10)) == 10
    assert next_sleep(now, now - timedelta(seconds=5)) == 1.0
    assert next_sleep(now, now + timedelta(milliseconds=5)) == 1.0


async def test_on_time_is_schedule(env) -> None:
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    await env.sched.run_pass(env.clock[0])
    assert env.spawn.calls == [r.id]
    got = await env.repo.get_by_id(r.id)
    assert got.next_run_at == _dt(2026, 3, 2, 9, 0).isoformat() and got.finished_at is None


async def test_trigger_kinds_and_catch_up(env, monkeypatch) -> None:
    got_args = []

    async def fake_run(rid, trigger, due=None):
        got_args.append((rid, trigger, due))

    monkeypatch.setattr(runner, "run_routine", fake_run)

    def spawn(rid, factory):
        return asyncio.get_running_loop().create_task(factory())

    env.sched._spawn = spawn
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    await env.sched.run_pass(_dt(2026, 3, 1, 10, 30))  # 90 min late: catch up
    await asyncio.sleep(0.05)
    due = _dt(2026, 3, 1, 9, 0).isoformat()
    assert got_args == [(r.id, "catch_up", due)]
    got_args.clear()
    r2 = await _mk(env, name="R2", due=_dt(2026, 3, 2, 9, 0))
    await env.sched.run_pass(_dt(2026, 3, 2, 9, 0, 30))
    await asyncio.sleep(0.05)
    assert (r2.id, "schedule", _dt(2026, 3, 2, 9, 0).isoformat()) in got_args


async def test_interval_catch_up(env) -> None:
    anchor = _dt(2026, 3, 1, 0, 0)
    r = await _mk(
        env,
        schedule=_every(2, "hour", anchor),
        due=_dt(2026, 3, 1, 2, 0),
        anchor_at=anchor.isoformat(),
    )
    await env.sched.run_pass(_dt(2026, 3, 1, 2, 50))
    assert env.spawn.calls == [r.id]
    assert (await env.repo.get_by_id(r.id)).next_run_at == _dt(2026, 3, 1, 4, 0).isoformat()


@pytest.mark.parametrize(
    "now,n",
    [(_dt(2026, 3, 5, 10, 0), 5), (_dt(2026, 3, 5, 8, 0), 4)],
)
async def test_daily_miss_counts(env, now, n) -> None:
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    await env.sched.run_pass(now)
    assert env.spawn.calls == []
    (run,) = await _runs(env, r.id)
    assert run.outcome == "missed" and run.trigger_kind == "schedule"
    assert run.reason == f"Missed {n} runs while the app was closed."
    assert run.due_at == _dt(2026, 3, 1, 9, 0).isoformat()
    got = await env.repo.get_by_id(r.id)
    assert got.next_run_at > now.isoformat() and got.finished_at is None


async def test_missed_one_singular(env) -> None:
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    await env.sched.run_pass(_dt(2026, 3, 1, 12, 0))
    (run,) = await _runs(env, r.id)
    assert run.reason == "Missed 1 run while the app was closed."


async def test_interval_one_more_than_1000(env) -> None:
    anchor = _dt(2026, 1, 1)
    due = _dt(2026, 1, 1, 1)
    r = await _mk(
        env,
        schedule=_every(1, "hour", anchor),
        due=due,
        anchor_at=anchor.isoformat(),
    )
    await env.sched.run_pass(due + timedelta(hours=2000))
    (run,) = await _runs(env, r.id)
    assert run.reason == "Missed more than 1000 runs while the app was closed."


async def test_one_off_miss_and_finish(env) -> None:
    at = _dt(2026, 3, 1, 9, 0)
    r = await _mk(env, schedule=_once(at), due=at, anchor_at=at.isoformat())
    now = at + timedelta(hours=30)
    await env.sched.run_pass(now)
    assert env.spawn.calls == []
    (run,) = await _runs(env, r.id)
    assert run.outcome == "missed"
    assert run.reason == "The scheduled time passed while the app was closed."
    got = await env.repo.get_by_id(r.id)
    assert got.finished_at == now.isoformat() and got.next_run_at is None


async def test_one_off_finished_before_spawn_even_if_run_fails(env) -> None:
    at = _dt(2026, 3, 1, 9, 0)
    r = await _mk(env, schedule=_once(at), due=at, anchor_at=at.isoformat())
    seen = {}

    async def check():
        seen["finished"] = (await env.repo.get_by_id(r.id)).finished_at

    def spawn(rid, factory):
        asyncio.get_running_loop().create_task(check())
        raise RuntimeError("spawn blew up")

    env.sched._spawn = spawn
    await env.sched.run_pass(env.clock[0])
    await asyncio.sleep(0)
    got = await env.repo.get_by_id(r.id)
    assert got.finished_at is not None and got.next_run_at is None
    assert seen["finished"] is not None
    await env.sched.run_pass(env.clock[0])  # not picked again
    assert env.spawn.calls == []


async def test_overlap_records_skipped(env) -> None:
    env.spawn.refuse = True
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    await env.sched.run_pass(env.clock[0])
    (run,) = await _runs(env, r.id)
    assert run.outcome == "skipped" and run.reason == "The previous run was still going."
    assert run.trigger_kind == "schedule" and run.finished_at is not None
    assert run.reason_code == "still_running" and run.repeats == 1
    assert (await env.repo.get_by_id(r.id)).next_run_at == _dt(2026, 3, 2, 9, 0).isoformat()


async def test_consecutive_still_running_skips_collapse(env) -> None:
    env.spawn.refuse = True
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    await env.sched.run_pass(env.clock[0])
    (first,) = await _runs(env, r.id)
    for day in (2, 3):
        await env.repo.set_next_run(r.id, _dt(2026, 3, day, 9, 0).isoformat())
        env.clock[0] = _dt(2026, 3, day, 9, 0)
        await env.sched.run_pass(env.clock[0])
    (run,) = await _runs(env, r.id)
    assert run.id == first.id and run.repeats == 3
    assert run.reason == "Skipped 3 times while the previous run was still going."
    assert run.started_at == first.started_at and run.trigger_kind == first.trigger_kind
    assert run.due_at == _dt(2026, 3, 3, 9, 0).isoformat()
    assert run.finished_at == _dt(2026, 3, 3, 9, 0).isoformat()


async def test_still_running_skip_does_not_collapse_across_other_rows(env) -> None:
    from the_one.routines.models import RoutineRun

    env.spawn.refuse = True
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    other = await _mk(env, name="other", due=_dt(2026, 3, 1, 9, 0))
    # a pre-v47 style row: same text, no reason code -> never merged into
    await env.runs.insert(
        RoutineRun(
            routine_id=r.id, trigger_kind="schedule", outcome="skipped",
            reason="The previous run was still going.",
            started_at=_dt(2026, 2, 28, 9, 0).isoformat(),
        )
    )  # fmt: skip
    await env.sched.run_pass(env.clock[0])
    assert len(await _runs(env, r.id)) == 2
    assert len(await _runs(env, other.id)) == 1  # another routine's row is its own
    # an ok run after the skip breaks the chain
    await env.runs.insert(
        RoutineRun(
            routine_id=r.id, trigger_kind="manual", outcome="ok",
            started_at=_dt(2026, 3, 1, 9, 30).isoformat(),
        )
    )  # fmt: skip
    await env.repo.set_next_run(r.id, _dt(2026, 3, 2, 9, 0).isoformat())
    env.clock[0] = _dt(2026, 3, 2, 9, 0)
    await env.sched.run_pass(env.clock[0])
    rows = await _runs(env, r.id)
    assert len(rows) == 4 and all(x.repeats == 1 for x in rows)


async def test_one_off_overlap_stays_finished(env) -> None:
    env.spawn.refuse = True
    at = _dt(2026, 3, 1, 9, 0)
    r = await _mk(env, schedule=_once(at), due=at, anchor_at=at.isoformat())
    await env.sched.run_pass(env.clock[0])
    (run,) = await _runs(env, r.id)
    assert run.outcome == "skipped"
    assert (await env.repo.get_by_id(r.id)).finished_at is not None


async def test_not_picked_disabled_and_finished(env) -> None:
    due = _dt(2026, 3, 1, 9, 0)
    await _mk(env, name="off", due=due, enabled=False)
    await _mk(env, name="done", due=due, finished_at=due.isoformat())
    await env.sched.run_pass(env.clock[0])
    assert env.spawn.calls == []


async def test_cas_race_edit_wins(env, monkeypatch) -> None:
    due = _dt(2026, 3, 1, 9, 0)
    r = await _mk(env, due=due)
    orig = env.repo.__class__.list_due

    async def hooked(self, now_iso):
        rows = await orig(self, now_iso)
        await self.update("a", r.id, {"next_run_at": _dt(2026, 3, 9, 9, 0).isoformat()})
        return rows

    monkeypatch.setattr(AgentRoutineRepository, "list_due", hooked)
    await env.sched.run_pass(env.clock[0])
    assert env.spawn.calls == []
    assert await _runs(env, r.id) == []
    assert (await env.repo.get_by_id(r.id)).next_run_at == _dt(2026, 3, 9, 9, 0).isoformat()


async def test_deletion_race_is_skipped_and_pass_continues(env, monkeypatch) -> None:
    due = _dt(2026, 3, 1, 9, 0)
    gone = await _mk(env, name="gone", due=due)
    keep = await _mk(env, name="keep", due=due + timedelta(seconds=1))
    orig = AgentRoutineRepository.list_due

    async def hooked(self, now_iso):
        rows = await orig(self, now_iso)
        await self.delete("a", gone.id)
        return rows

    monkeypatch.setattr(AgentRoutineRepository, "list_due", hooked)
    await env.sched.run_pass(env.clock[0])
    assert env.spawn.calls == [keep.id]


async def test_startup_sweep_marks_running_interrupted(env) -> None:
    r = await _mk(env, due=_dt(2027, 1, 1))
    row = await env.runs.insert(RoutineRun(routine_id=r.id, trigger_kind="manual"))
    await env.sched.startup(env.clock[0])
    (got,) = await _runs(env, r.id)
    assert got.id == row.id and got.outcome == "interrupted"
    assert got.reason == "The app stopped during this run."


async def test_first_boot_stores_zone_only(env) -> None:
    r = await _mk(env, due=_dt(2027, 1, 1, 9, 0))
    await env.sched.startup(env.clock[0])
    assert await AppMetadataRepository(env.conn).get(ZONE_KEY) == "UTC"
    assert (await env.repo.get_by_id(r.id)).next_run_at == _dt(2027, 1, 1, 9, 0).isoformat()


async def test_startup_order_and_zone_change(env) -> None:
    meta = AppMetadataRepository(env.conn)
    await meta.set(ZONE_KEY, "America/Los_Angeles")
    await time_zones.save_setting(
        env.conn, time_zones.TimeZoneSetting(mode="zone", zone="Europe/London")
    )
    now = _dt(2026, 3, 1, 9, 0, 30)
    past = await _mk(env, name="past", due=_dt(2026, 3, 1, 9, 0))  # due in the outage
    future = await _mk(env, name="future", due=_dt(2026, 3, 2, 17, 0))  # LA 09:00
    once = await _mk(
        env,
        name="once",
        schedule=_once(_dt(2026, 3, 3, 1, 0)),  # rendered in Los Angeles: 01:00 PST
        due=_dt(2026, 3, 3, 9, 0),
        anchor_at=_dt(2026, 3, 3, 9, 0).isoformat(),
    )
    await env.sched.startup(now)
    assert env.spawn.calls == [past.id]
    assert (await env.repo.get_by_id(future.id)).next_run_at == _dt(2026, 3, 2, 9, 0).isoformat()
    assert (await env.repo.get_by_id(once.id)).next_run_at == _dt(2026, 3, 3, 9, 0).isoformat()
    assert (await env.repo.get_by_id(past.id)).next_run_at == _dt(2026, 3, 2, 9, 0).isoformat()
    assert await meta.get(ZONE_KEY) == "Europe/London"


async def test_corrupt_due_routine_no_hot_loop(env) -> None:
    bad = await _mk(env, name="bad", due=_dt(2026, 3, 1, 8, 0))
    await env.conn.execute(
        "UPDATE agent_routines SET schedule = 'not json' WHERE id = ?", (bad.id,)
    )
    await env.conn.commit()
    good = await _mk(env, name="good", due=_dt(2026, 3, 1, 9, 0))
    n = 0

    async def sleep(s):
        nonlocal n
        env.sleeps.append(s)
        n += 1
        if n >= 5:
            env.sched._stopped = True

    env.sched._sleep = sleep
    await env.sched._loop()
    assert len(env.sleeps) == 5 and all(s >= 1.0 for s in env.sleeps)
    assert env.spawn.calls.count(good.id) == 1  # advanced past due after its first run
    assert bad.id not in env.spawn.calls


async def test_poke_ends_the_sleep(env) -> None:
    sched = RoutineScheduler(lambda: env.clock[0], env.spawn, lambda: asyncio.sleep(0, env.conn))
    started = asyncio.Event()
    orig = sched._default_sleep

    async def sleep(s):
        started.set()
        await orig(s)

    sched._sleep = sleep
    sched.start()
    await asyncio.wait_for(started.wait(), 5)
    started.clear()
    sched.poke()
    await asyncio.wait_for(started.wait(), 5)  # woke, passed, slept again
    sched._stopped = True
    sched._task.cancel()


async def test_stopped_scheduler_ignores_poke_and_pass(env) -> None:
    await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    env.sched._stopped = True
    env.sched.poke()
    assert not env.sched._event.is_set()
    await env.sched.run_pass(env.clock[0])
    assert env.spawn.calls == []


def test_poke_scheduler_tolerates_none() -> None:
    from the_one.interfaces.web import api
    from the_one.routines import scheduler

    scheduler.set_scheduler(None)
    api._poke_scheduler()


# ── over the real lifespan ──


@pytest.mark.timeout(60)
async def test_once_routine_runs_without_waiting_for_the_tick(routine_app) -> None:
    h = routine_app
    # A one-off made over REST starts at a whole minute at least; so make it for tomorrow,
    # then pull its stored time to a moment already past and poke the loop awake: the poke
    # starts the run without waiting for the tick.
    r = await h.routine(schedule=once_in(1, "days"))
    from the_one.db.connection import get_connection
    from the_one.routines.scheduler import get_scheduler

    soon = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    conn = await get_connection()
    await conn.execute(
        "UPDATE agent_routines SET next_run_at = ?, anchor_at = ? WHERE id = ?",
        (soon, soon, r["id"]),
    )
    await conn.commit()
    get_scheduler().poke()
    t0 = time.monotonic()

    async def ran():
        return bool(await h.runs(r["id"])) and not runner.registry.is_running(r["id"])

    await wait_for(ran, timeout=10)
    assert time.monotonic() - t0 < 10
    run = await h.last_run(r["id"])
    assert run["trigger_kind"] in ("schedule", "catch_up") and run["outcome"] == "ok"


async def test_run_now_is_independent_and_overlap_skips(routine_app) -> None:
    h = routine_app
    r = await h.routine()
    before = (await h.api("GET", f"/api/agents/bot/routines/{r['id']}")).json()
    h.llm.delay = 3.0
    resp = await h.api("POST", f"/api/agents/bot/routines/{r['id']}/run")
    assert resp.status_code == 202
    from the_one.routines.scheduler import get_scheduler

    sched = get_scheduler()
    conn = await sched._conn_factory()
    due = datetime.now(UTC) - timedelta(seconds=1)
    repo = AgentRoutineRepository(conn)
    await repo.set_next_run(r["id"], due.isoformat())
    await sched.run_pass(datetime.now(UTC))
    runs = await h.runs(r["id"])
    assert any(x["outcome"] == "skipped" for x in runs)
    h.llm.delay = 0
    await wait_for(lambda: not runner.registry.is_running(r["id"]), timeout=15)
    after = (await h.api("GET", f"/api/agents/bot/routines/{r['id']}")).json()
    assert before["finished_at"] == after["finished_at"] if "finished_at" in before else True


@pytest.mark.timeout(60)
async def test_stop_interrupts_a_running_run_promptly(routine_app) -> None:
    h = routine_app
    r = await h.routine()
    h.llm.delay = 30.0
    resp = await h.api("POST", f"/api/agents/bot/routines/{r['id']}/run")
    assert resp.status_code == 202

    async def has_run():
        return bool(await h.runs(r["id"]))

    await wait_for(has_run)
    await asyncio.sleep(0.3)
    from the_one.routines.scheduler import get_scheduler

    sched = get_scheduler()
    t0 = time.monotonic()
    await sched.stop()
    assert time.monotonic() - t0 < 8
    assert (await h.last_run(r["id"]))["outcome"] == "interrupted"
    assert runner.registry.try_spawn("x", lambda: asyncio.sleep(0)) is None


# ── the calendar recurrence (M33 F3 leg 4) ──


async def test_after_n_series_finishes_after_its_nth_occurrence(env) -> None:
    r = await _mk(env, schedule=_daily({"kind": "after", "count": 2}), due=_dt(2026, 3, 1, 9, 0))
    await env.sched.run_pass(_dt(2026, 3, 1, 9, 0, 30))
    got = await env.repo.get_by_id(r.id)
    assert got.finished_at is None and got.next_run_at == _dt(2026, 3, 2, 9, 0).isoformat()
    await env.sched.run_pass(_dt(2026, 3, 2, 9, 0, 30))
    assert env.spawn.calls == [r.id, r.id]
    got = await env.repo.get_by_id(r.id)
    assert got.finished_at == _dt(2026, 3, 2, 9, 0, 30).isoformat() and got.next_run_at is None
    await env.sched.run_pass(_dt(2026, 3, 3, 9, 0, 30))
    assert env.spawn.calls == [r.id, r.id]  # Done: never picked again


async def test_ends_on_series_finishes_after_its_last_occurrence(env) -> None:
    r = await _mk(
        env, schedule=_daily({"kind": "on", "date": "2026-03-02"}), due=_dt(2026, 3, 2, 9, 0)
    )
    await env.sched.run_pass(_dt(2026, 3, 2, 9, 0, 30))
    assert env.spawn.calls == [r.id]
    got = await env.repo.get_by_id(r.id)
    assert got.finished_at is not None and got.next_run_at is None


async def test_ended_series_missed_in_an_outage_counts_and_finishes(env) -> None:
    r = await _mk(env, schedule=_daily({"kind": "after", "count": 3}), due=_dt(2026, 3, 1, 9, 0))
    now = _dt(2026, 3, 10, 12, 0)
    await env.sched.run_pass(now)
    assert env.spawn.calls == []
    (run,) = await _runs(env, r.id)
    assert run.outcome == "missed" and run.reason == "Missed 3 runs while the app was closed."
    got = await env.repo.get_by_id(r.id)
    assert got.finished_at == now.isoformat() and got.next_run_at is None


_MON = _dt(2026, 3, 2, 9, 0)  # a Monday


@pytest.mark.parametrize(
    ("schedule", "anchor", "due", "next_at"),
    [
        (
            {
                "start": {"date": "2026-03-02", "time": "09:00"},
                "repeat": {"every": 1, "unit": "week", "days": [0, 3]},
                "ends": NEVER,
            },
            None,
            _MON,
            _dt(2026, 3, 5, 9, 0),
        ),
        (
            {
                "start": {"date": "2026-01-31", "time": "09:00"},
                "repeat": {"every": 1, "unit": "month", "month_by": {"by": "day"}},
                "ends": NEVER,
            },
            None,
            _dt(2026, 1, 31, 9, 0),
            _dt(2026, 3, 31, 9, 0),  # February has no 31st: skipped
        ),
        (
            {
                "start": {"date": "2026-03-02", "time": "09:00"},
                "repeat": {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": -1}},
                "ends": NEVER,
            },
            None,
            _dt(2026, 3, 30, 9, 0),
            _dt(2026, 4, 27, 9, 0),
        ),
        (
            {
                "start": {"date": "2028-02-29", "time": "09:00"},
                "repeat": {"every": 1, "unit": "year"},
                "ends": NEVER,
            },
            None,
            _dt(2028, 2, 29, 9, 0),
            _dt(2032, 2, 29, 9, 0),
        ),
        (
            {
                "start": {"date": "2026-03-01", "time": "09:00"},
                "repeat": {"every": 90, "unit": "minute"},
                "ends": NEVER,
            },
            _dt(2026, 3, 1, 9, 0),
            _dt(2026, 3, 1, 9, 0),
            _dt(2026, 3, 1, 10, 30),
        ),
    ],
    ids=["week", "month-skip", "month-last-weekday", "leap-year", "minutes"],
)
async def test_each_unit_runs_and_advances_to_its_next_occurrence(
    env, schedule, anchor, due, next_at
) -> None:
    r = await _mk(env, schedule=schedule, due=due, anchor_at=anchor.isoformat() if anchor else None)
    await env.sched.run_pass(due + timedelta(seconds=30))
    assert env.spawn.calls == [r.id]
    got = await env.repo.get_by_id(r.id)
    assert got.next_run_at == next_at.isoformat() and got.finished_at is None


# ── zone changes (DD12) ──


async def _switch_zone(e, old: str, new: str) -> None:
    await AppMetadataRepository(e.conn).set(ZONE_KEY, old)
    await time_zones.save_setting(e.conn, time_zones.TimeZoneSetting(mode="zone", zone=new))


async def test_zone_change_keeps_one_off_instants_on_and_off_and_rerenders_start(env) -> None:
    at = _dt(2026, 3, 3, 17, 0)  # 09:00 PST
    on = await _mk(
        env, name="on", schedule=_once(_dt(2026, 3, 3, 9, 0)), due=at, anchor_at=at.isoformat()
    )
    off = await _mk(
        env,
        name="off",
        schedule=_once(_dt(2026, 3, 3, 9, 0)),
        enabled=False,
        anchor_at=at.isoformat(),
    )
    await _switch_zone(env, "America/Los_Angeles", "Asia/Kolkata")
    await env.sched._check_zone(env.clock[0])
    for r in (on, off):
        got = await env.repo.get_by_id(r.id)
        assert got.anchor_at == at.isoformat()
        assert got.schedule["start"] == {"date": "2026-03-03", "time": "22:30"}
    assert (await env.repo.get_by_id(on.id)).next_run_at == at.isoformat()
    assert (await env.repo.get_by_id(off.id)).next_run_at is None


async def test_zone_change_keeps_a_minute_or_hour_routine_anchor_and_grid(env) -> None:
    anchor = _dt(2026, 3, 1, 1, 15)
    nxt = _dt(2026, 3, 5, 3, 15)
    r = await _mk(
        env,
        schedule=_every(2, "hour", anchor),
        due=nxt,
        anchor_at=anchor.isoformat(),
    )
    await _switch_zone(env, "UTC", "Asia/Kolkata")
    await env.sched._check_zone(env.clock[0])
    got = await env.repo.get_by_id(r.id)
    assert got.anchor_at == anchor.isoformat() and got.next_run_at == nxt.isoformat()
    assert got.schedule["start"] == {"date": "2026-03-01", "time": "06:45"}
    assert got.schedule["repeat"] == {"every": 2, "unit": "hour"}


async def test_zone_change_keeps_a_daily_wall_time_and_recomputes_next(env) -> None:
    r = await _mk(env, schedule=DAILY, due=_dt(2026, 3, 2, 17, 0))  # 09:00 Los Angeles
    off = await _mk(env, name="off", schedule=DAILY, enabled=False)
    await _switch_zone(env, "America/Los_Angeles", "Europe/London")
    await env.sched._check_zone(env.clock[0])
    assert (await env.repo.get_by_id(r.id)).next_run_at == _dt(2026, 3, 2, 9, 0).isoformat()
    assert (await env.repo.get_by_id(r.id)).schedule == DAILY  # 9:00 AM stays 9:00 AM
    got = await env.repo.get_by_id(off.id)  # an off routine has no next run to move
    assert got.next_run_at is None and got.schedule == DAILY


async def test_zone_change_makes_a_wall_clock_series_with_nothing_left_done(env) -> None:
    ends = {"kind": "on", "date": "2026-03-02"}
    r = await _mk(env, schedule=_daily(ends), due=_dt(2026, 3, 2, 23, 30))  # 15:30 PST
    await _switch_zone(env, "America/Los_Angeles", "Pacific/Kiritimati")  # UTC+14
    await env.sched._check_zone(_dt(2026, 3, 2, 12, 0))
    got = await env.repo.get_by_id(r.id)
    assert got.finished_at is not None and got.next_run_at is None


async def test_zone_change_leaves_done_routines_alone(env) -> None:
    at = _dt(2026, 3, 3, 17, 0)
    done = await _mk(
        env,
        schedule=_once(_dt(2026, 3, 3, 9, 0)),
        anchor_at=at.isoformat(),
        finished_at=_dt(2026, 3, 3, 17, 1).isoformat(),
    )
    before = await env.repo.get_by_id(done.id)
    await _switch_zone(env, "America/Los_Angeles", "Asia/Kolkata")
    await env.sched._check_zone(env.clock[0])
    assert await env.repo.get_by_id(done.id) == before


async def test_zone_change_skips_an_unreadable_schedule_quietly(env, caplog) -> None:
    import logging

    bad = await _mk(env, name="bad", schedule=DAILY, due=_dt(2026, 3, 2, 17, 0))
    good = await _mk(env, name="good", schedule=DAILY, due=_dt(2026, 3, 2, 17, 0))
    # What an upgrade_failed routine looks like: the old shape, left as is, turned off.
    await env.conn.execute(
        "UPDATE agent_routines SET schedule = ?, enabled = 0 WHERE id = ?",
        ('{"kind": "monthly", "time": "09:00"}', bad.id),
    )
    await env.conn.commit()
    await _switch_zone(env, "America/Los_Angeles", "Europe/London")
    with caplog.at_level(logging.DEBUG, logger="the_one.routines.scheduler"):
        await env.sched._check_zone(env.clock[0])
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert (await env.repo.get_by_id(good.id)).next_run_at != _dt(2026, 3, 2, 17, 0).isoformat()


async def test_zone_change_defers_to_an_operator_edit_made_mid_pass(env, monkeypatch) -> None:
    r = await _mk(env, schedule=DAILY, due=_dt(2026, 3, 2, 17, 0))
    edited = _daily(time="07:30")
    orig = AgentRoutineRepository.list_not_done

    async def hooked(self):
        rows = await orig(self)
        await self.update(
            "a", r.id, {"schedule": edited, "next_run_at": _dt(2026, 3, 2, 7, 30).isoformat()}
        )
        return rows

    monkeypatch.setattr(AgentRoutineRepository, "list_not_done", hooked)
    await _switch_zone(env, "America/Los_Angeles", "Europe/London")
    await env.sched._check_zone(env.clock[0])
    got = await env.repo.get_by_id(r.id)
    assert got.schedule == edited and got.next_run_at == _dt(2026, 3, 2, 7, 30).isoformat()


async def test_zone_change_rebases_a_pending_proposal_so_it_approves_without_a_stale(env) -> None:
    from the_one.routines import service as svc
    from the_one.routines.proposals import RoutineProposalRepository

    at = _dt(2026, 3, 3, 17, 0)
    r = await _mk(env, schedule=_once(_dt(2026, 3, 3, 9, 0)), due=at, anchor_at=at.isoformat())
    await env.conn.execute("PRAGMA foreign_keys=OFF")
    store = SQLiteAgentStore(env.conn)
    await store.set_routines_self_config("a", enabled=True, requires_approval=True)
    now = env.clock[0]

    async def zone_utc():
        return (await time_zones.load_effective_zone(env.conn)).tzinfo

    res = await svc.agent_change(
        env.conn,
        "a",
        "update",
        {"routine": r.id, "prompt": "agent text"},
        now=now,
        zone=zone_utc,
        taint=(False, []),
        session_id=None,
    )
    props = RoutineProposalRepository(env.conn)
    before = await props.get(res.proposal_id)
    await _switch_zone(env, "UTC", "Asia/Kolkata")
    await env.sched._check_zone(now)
    moved = await env.repo.get_by_id(r.id)
    assert moved.schedule["start"]["time"] == "22:30"
    got = await props.get(res.proposal_id)
    assert got.base["schedule"] == moved.schedule and got.base["anchor_at"] == moved.anchor_at
    assert (await props.get(res.proposal_id)).base != before.base
    done = await svc.approve_proposal(
        env.conn, "a", res.proposal_id, override=False, now=now, zone=zone_utc
    )
    assert done.status == "applied"
    assert (await env.repo.get_by_id(r.id)).prompt == "agent text"


async def test_zone_change_leaves_an_already_due_wall_clock_routine_for_the_pass(env) -> None:
    due = _dt(2026, 3, 1, 8, 0)  # due before the zone check's "now" (09:00:30)
    r = await _mk(env, schedule=DAILY, due=due)
    await _switch_zone(env, "America/Los_Angeles", "Europe/London")
    await env.sched._check_zone(env.clock[0])
    assert (await env.repo.get_by_id(r.id)).next_run_at == due.isoformat()


async def test_a_now_start_is_never_missed_or_a_catch_up(env, monkeypatch) -> None:
    """M33 F4 L4 AC7: a routine saved with Immediately has next_run_at = the save instant,
    and a pass 2 s or 59 s later runs it as an ordinary scheduled run."""
    got = []

    async def fake_run(rid, trigger, due=None):
        got.append((rid, trigger))

    monkeypatch.setattr(runner, "run_routine", fake_run)
    env.sched._spawn = lambda rid, factory: asyncio.get_running_loop().create_task(factory())
    for name, delay in (("two", 2), ("fifty-nine", 59)):
        saved = _dt(2026, 3, 1, 9, 0, 17)
        r = await _mk(
            env,
            name=name,
            schedule=_every(1, "day", saved.replace(second=0)),
            due=saved,
            anchor_at=None,
        )
        await env.sched.run_pass(saved + timedelta(seconds=delay))
        await asyncio.sleep(0.05)
        assert (r.id, "schedule") in got, name
        assert not [x for x in await _runs(env, r.id) if x.outcome == "missed"]


# ── log lines (M34 F2 L2) ──


def _lines(caplog, logger_name="the_one.routines.scheduler"):
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == logger_name and r.levelno == logging.INFO
    ]


async def test_log_spawn_on_time(env, caplog) -> None:
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    with caplog.at_level(logging.INFO, logger="the_one.routines.scheduler"):
        await env.sched.run_pass(env.clock[0])
    (line,) = _lines(caplog)
    assert line == (
        f"routine decision=spawn routine={r.id} agent='a' trigger=schedule "
        f"due={_dt(2026, 3, 1, 9, 0).isoformat()} late_s=30.0 "
        f"next={_dt(2026, 3, 2, 9, 0).isoformat()} finished=False"
    )


async def test_log_spawn_catch_up(env, caplog, monkeypatch) -> None:
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    with caplog.at_level(logging.INFO, logger="the_one.routines.scheduler"):
        await env.sched.run_pass(_dt(2026, 3, 1, 10, 30))
    (line,) = _lines(caplog)
    assert line.startswith(f"routine decision=spawn routine={r.id} agent='a' trigger=catch_up ")
    assert "late_s=5400.0" in line and "finished=False" in line


async def test_log_missed_one_off_and_repeating(env, caplog) -> None:
    at = _dt(2026, 3, 1, 9, 0)
    one = await _mk(env, name="one", schedule=_once(at), due=at, anchor_at=at.isoformat())
    with caplog.at_level(logging.INFO, logger="the_one.routines.scheduler"):
        await env.sched.run_pass(at + timedelta(hours=30))
    (line,) = _lines(caplog)
    (stored,) = await _runs(env, one.id)
    assert line == (
        f"routine decision=missed run={stored.id} routine={one.id} agent='a' due={at.isoformat()} "
        f"late_s=108000.0 next=none finished=True "
        "reason='The scheduled time passed while the app was closed.'"
    )
    caplog.clear()
    rep = await _mk(env, name="rep", due=_dt(2026, 3, 1, 9, 0))
    await env.repo.update("a", one.id, {"enabled": False})
    with caplog.at_level(logging.INFO, logger="the_one.routines.scheduler"):
        await env.sched.run_pass(_dt(2026, 3, 5, 10, 0))
    (line,) = _lines(caplog)
    (stored_rep,) = await _runs(env, rep.id)
    assert line.startswith(
        f"routine decision=missed run={stored_rep.id} routine={rep.id} agent='a' "
    )
    assert "finished=False" in line and "next=2026-03-06" in line
    assert "reason='Missed 5 runs while the app was closed.'" in line


async def test_log_still_running_skip(env, caplog) -> None:
    env.spawn.refuse = True
    r = await _mk(env, due=_dt(2026, 3, 1, 9, 0))
    with caplog.at_level(logging.INFO, logger="the_one.routines.scheduler"):
        await env.sched.run_pass(env.clock[0])
    (line,) = _lines(caplog)
    assert line.startswith(
        f"routine decision=still_running_skip routine={r.id} agent='a' trigger=schedule "
    )
    assert "spawn" not in line.replace("still_running_skip", "")


async def test_log_skip_changed(env, caplog, monkeypatch) -> None:
    due = _dt(2026, 3, 1, 9, 0)
    r = await _mk(env, due=due)
    orig = AgentRoutineRepository.list_due

    async def hooked(self, now_iso):
        rows = await orig(self, now_iso)
        await self.update("a", r.id, {"next_run_at": _dt(2026, 3, 9, 9, 0).isoformat()})
        return rows

    monkeypatch.setattr(AgentRoutineRepository, "list_due", hooked)
    with caplog.at_level(logging.INFO, logger="the_one.routines.scheduler"):
        await env.sched.run_pass(env.clock[0])
    (line,) = _lines(caplog)
    assert line == (
        f"routine decision=skip_changed routine={r.id} agent='a' due={due.isoformat()} late_s=30.0"
    )


async def test_log_names_are_repr_quoted_and_prompts_never_logged(env, caplog) -> None:
    """AC5: a legacy agent name with a newline and a quote appears only in repr form; a
    prompt marker appears in no record at any level."""
    weird = "ev\nil'name"
    await SQLiteAgentStore(env.conn).save(AgentConfig(name=weird))
    marker = "PROMPT-MARKER-7f3a9c"
    r = await env.repo.create(
        weird,
        {
            "name": 'N\nm"e',
            "prompt": marker,
            "schedule": DAILY,
            "next_run_at": _dt(2026, 3, 1, 9, 0).isoformat(),
            "anchor_at": None,
        },
    )
    with caplog.at_level(logging.DEBUG):
        await env.sched.run_pass(env.clock[0])
    msgs = [x.getMessage() for x in caplog.records]
    assert any(f"routine={r.id}" in m for m in msgs)
    assert not any(marker in m for m in msgs)
    assert not any("\n" in m for m in msgs)
    assert any(repr(weird) in m for m in msgs)
    assert not any("N\nm" in m or 'm"e' in m for m in msgs)

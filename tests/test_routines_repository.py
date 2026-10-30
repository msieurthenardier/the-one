"""Routine and run repositories (M33 F1 leg 1, DD1; AC19-AC20a)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests._schema_template import connect_template_db
from the_one import time_zones
from the_one.agent.config import AgentConfig
from the_one.db.repositories import SQLiteAgentStore
from the_one.routines.limits import (
    ROUTINES_ACTIVE_MAX,
    ROUTINES_OPEN_MAX,
    RoutineLimitError,
    RoutineNameTaken,
)
from the_one.routines.models import RoutineRun
from the_one.routines.repository import AgentRoutineRepository, RoutineRunRepository

UTC = timezone.utc


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="a"))
    await store.save(AgentConfig(name="b"))
    yield conn
    await conn.close()


DAILY = {
    "start": {"date": "2026-10-11", "time": "09:00"},
    "repeat": {"every": 1, "unit": "day"},
    "ends": {"kind": "never"},
}


def _fields(name="Daily", **extra):
    return {
        "name": name,
        "prompt": "do it",
        "schedule": DAILY,
        **extra,
    }


def _at(monkeypatch, *args):
    instant = datetime(*args, tzinfo=UTC)
    monkeypatch.setattr(time_zones, "utcnow", lambda: instant)
    return instant


async def test_create_get_list_name_order(env) -> None:
    repo = AgentRoutineRepository(env)
    await repo.create("a", _fields("beta"))
    await repo.create("a", _fields("Alpha"))
    await repo.create("b", _fields("Alpha"))
    got = await repo.list_for_agent("a")
    assert [r.name for r in got] == ["Alpha", "beta"]
    assert got[0].schedule == DAILY
    assert got[0].enabled is True and got[0].created_by == "operator"
    assert await repo.get("b", got[0].id) is None  # another agent's id is a miss


async def test_duplicate_name_is_case_insensitive_per_agent(env) -> None:
    repo = AgentRoutineRepository(env)
    r = await repo.create("a", _fields("Daily"))
    with pytest.raises(RoutineNameTaken):
        await repo.create("a", _fields("daily"))
    # renaming a row to its own name in another case is fine
    out = await repo.update("a", r.id, {"name": "DAILY"})
    assert out.name == "DAILY"
    other = await repo.create("a", _fields("Other"))
    with pytest.raises(RoutineNameTaken):
        await repo.update("a", other.id, {"name": "daily"})


async def test_active_cap_inside_every_write(env) -> None:
    repo = AgentRoutineRepository(env)
    first = None
    for i in range(ROUTINES_ACTIVE_MAX):
        first = first or await repo.create("a", _fields(f"r{i}"))
        if i:
            await repo.create("a", _fields(f"r{i}"))
    with pytest.raises(RoutineLimitError, match="50 active routines"):
        await repo.create("a", _fields("one too many"))
    await repo.create("b", _fields("fine"))  # per agent
    # An off routine is not active; enabling it past the cap is refused, a disable is not.
    off = await repo.create("a", _fields("off") | {"enabled": False})
    with pytest.raises(RoutineLimitError, match="50 active routines"):
        await repo.update("a", off.id, {"enabled": True})
    await repo.update("a", first.id, {"prompt": "edited", "name": "renamed"})
    await repo.update("a", first.id, {"enabled": False})
    await repo.update("a", off.id, {"enabled": True})
    await repo.delete("a", off.id)


async def test_open_cap_and_done_routines_do_not_count(env) -> None:
    repo = AgentRoutineRepository(env)
    for i in range(ROUTINES_OPEN_MAX):
        await repo.create("a", _fields(f"r{i}") | {"enabled": False})
    with pytest.raises(RoutineLimitError, match="200 routines that are not done"):
        await repo.create("a", _fields("over") | {"enabled": False})
    done = await repo.list_for_agent("a")
    await repo.update("a", done[0].id, {"finished_at": "2026-01-01T00:00:00+00:00"})
    await repo.create("a", _fields("fits") | {"enabled": False})  # a Done row freed a slot
    # Reopening the Done one is refused while at the cap.
    with pytest.raises(RoutineLimitError, match="200 routines that are not done"):
        await repo.update("a", done[0].id, {"finished_at": None})


async def test_update_delete_miss_is_keyerror(env) -> None:
    repo = AgentRoutineRepository(env)
    r = await repo.create("a", _fields())
    with pytest.raises(KeyError):
        await repo.update("b", r.id, {"prompt": "x"})
    with pytest.raises(KeyError):
        await repo.delete("b", r.id)
    await repo.delete("a", r.id)
    with pytest.raises(KeyError):
        await repo.delete("a", r.id)
    with pytest.raises(ValueError):
        await repo.update("a", r.id, {"agent_name": "b"})


async def test_list_due(env) -> None:
    repo = AgentRoutineRepository(env)
    now = "2026-10-10T12:00:00+00:00"
    due = await repo.create("a", _fields("due", next_run_at="2026-10-10T11:59:00+00:00"))
    await repo.create("a", _fields("off", enabled=False, next_run_at="2026-10-10T11:00:00+00:00"))
    await repo.create(
        "a",
        _fields(
            "done", finished_at="2026-10-10T10:00:00+00:00", next_run_at="2026-10-10T09:00+00:00"
        ),
    )
    await repo.create("a", _fields("nonext"))
    await repo.create("a", _fields("future", next_run_at="2026-10-10T12:00:01+00:00"))
    exact = await repo.create("a", _fields("exact", next_run_at=now))
    got = await repo.list_due(now)
    assert [r.id for r in got] == [due.id, exact.id]


async def test_set_next_run(env) -> None:
    repo = AgentRoutineRepository(env)
    r = await repo.create("a", _fields())
    await repo.set_next_run(
        r.id, "2026-10-11T00:00:00+00:00", finished_at="2026-10-10T00:00:00+00:00"
    )
    got = await repo.get("a", r.id)
    assert got.next_run_at == "2026-10-11T00:00:00+00:00"
    assert got.finished_at == "2026-10-10T00:00:00+00:00"
    await repo.set_next_run("nope", None)  # missing row: no-op


async def test_timestamps_follow_the_frozen_clock(env, monkeypatch) -> None:
    _at(monkeypatch, 2026, 5, 1, 12, 0, 0)
    repo = AgentRoutineRepository(env)
    r = await repo.create("a", _fields())
    assert r.created_at == r.updated_at == "2026-05-01T12:00:00+00:00"
    _at(monkeypatch, 2026, 5, 2, 12, 0, 0, 5)
    out = await repo.update("a", r.id, {"prompt": "again"})
    assert out.updated_at == "2026-05-02T12:00:00.000005+00:00"
    assert out.created_at == "2026-05-01T12:00:00+00:00"


async def test_run_lifecycle_and_finish_missing_is_noop(env, monkeypatch) -> None:
    rr = AgentRoutineRepository(env)
    runs = RoutineRunRepository(env)
    r = await rr.create("a", _fields())
    _at(monkeypatch, 2026, 5, 1, 12)
    run = await runs.insert(RoutineRun(routine_id=r.id, trigger_kind="manual"))
    assert run.id and run.started_at == "2026-05-01T12:00:00+00:00" and run.outcome == "running"
    _at(monkeypatch, 2026, 5, 1, 12, 1)
    await runs.finish(run.id, "ok", None, "sess")
    got = await runs.latest(r.id)
    assert (got.outcome, got.session_id) == ("ok", "sess")
    assert got.finished_at == "2026-05-01T12:01:00+00:00"
    await runs.finish("no-such-run", "failed", "gone")  # never raises
    await rr.delete("a", r.id)
    await runs.finish(run.id, "failed", "gone")  # row cascaded away: still no raise
    assert await runs.latest(r.id) is None


async def test_runs_cascade_with_routine_and_agent(env) -> None:
    rr = AgentRoutineRepository(env)
    runs = RoutineRunRepository(env)
    r = await rr.create("a", _fields())
    await runs.insert(RoutineRun(routine_id=r.id, trigger_kind="schedule", outcome="ok"))
    await rr.delete("a", r.id)
    async with env.execute("SELECT COUNT(*) FROM agent_routine_runs") as cur:
        assert (await cur.fetchone())[0] == 0


async def test_list_pages_newest_first_with_cursor_and_ties(env) -> None:
    rr = AgentRoutineRepository(env)
    runs = RoutineRunRepository(env)
    r = await rr.create("a", _fields())
    stamps = [
        "2026-05-01T12:00:00+00:00",  # zero microseconds
        "2026-05-01T12:00:00.000001+00:00",
        "2026-05-01T12:00:01+00:00",
        "2026-05-01T12:00:01+00:00",  # tie
    ]
    for i, s in enumerate(stamps):
        await runs.insert(
            RoutineRun(
                id=f"r{i}", routine_id=r.id, trigger_kind="schedule", started_at=s, outcome="ok"
            )
        )
    page = await runs.list(r.id, 10)
    assert [x.id for x in page] == ["r3", "r2", "r1", "r0"]  # ties by id desc
    assert [x.id for x in await runs.list(r.id, 2)] == ["r3", "r2"]
    assert [x.id for x in await runs.list(r.id, 10, "2026-05-01T12:00:01+00:00")] == ["r1", "r0"]
    assert [x.id for x in await runs.list(r.id, 10, "2026-05-01T12:00:00.000001+00:00")] == ["r0"]
    assert (await runs.latest(r.id)).id == "r3"


async def test_retention_cutoff_orders_zero_microsecond_values(env) -> None:
    rr = AgentRoutineRepository(env)
    runs = RoutineRunRepository(env)
    ra = await rr.create("a", _fields())
    rb = await rr.create("b", _fields())
    cutoff = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC).isoformat()
    older = (datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC) - timedelta(microseconds=1)).isoformat()
    exact = cutoff  # not older than the cutoff: kept
    newer = (datetime(2026, 5, 1, 12, 0, 0, 1, tzinfo=UTC)).isoformat()

    async def put(rid, i, finished, outcome="ok"):
        await runs.insert(
            RoutineRun(
                id=i,
                routine_id=rid,
                trigger_kind="schedule",
                outcome=outcome,
                started_at="2026-01-01T00:00:00+00:00",
                finished_at=finished,
            )
        )

    await put(ra.id, "old", older)
    await put(ra.id, "exact", exact)
    await put(ra.id, "new", newer)
    await put(ra.id, "running-old", None, "running")
    await put(rb.id, "other-agent-old", older)
    assert await runs.delete_finished_older_than("a", cutoff) == 1
    async with env.execute("SELECT id FROM agent_routine_runs ORDER BY id") as cur:
        assert [r[0] for r in await cur.fetchall()] == [
            "exact",
            "new",
            "other-agent-old",
            "running-old",
        ]


async def test_delete_all_for_agent_keeps_running_and_routines(env) -> None:
    rr = AgentRoutineRepository(env)
    runs = RoutineRunRepository(env)
    ra = await rr.create("a", _fields())
    rb = await rr.create("b", _fields())
    await runs.insert(RoutineRun(id="1", routine_id=ra.id, trigger_kind="manual", outcome="ok"))
    await runs.insert(RoutineRun(id="2", routine_id=ra.id, trigger_kind="manual"))
    await runs.insert(RoutineRun(id="3", routine_id=rb.id, trigger_kind="manual", outcome="ok"))
    assert await runs.delete_all_for_agent("a") == 1
    assert [x.id for x in await runs.list(ra.id, 10)] == ["2"]
    assert len(await runs.list(rb.id, 10)) == 1
    assert len(await rr.list_for_agent("a")) == 1


async def test_mark_running_interrupted(env, monkeypatch) -> None:
    rr = AgentRoutineRepository(env)
    runs = RoutineRunRepository(env)
    r = await rr.create("a", _fields())
    await runs.insert(RoutineRun(id="x", routine_id=r.id, trigger_kind="manual"))
    await runs.insert(RoutineRun(id="y", routine_id=r.id, trigger_kind="manual", outcome="ok"))
    _at(monkeypatch, 2026, 5, 1, 12)
    assert await runs.mark_running_interrupted("The app stopped during this run.") == 1
    got = {x.id: x for x in await runs.list(r.id, 10)}
    assert got["x"].outcome == "interrupted" and got["x"].reason.startswith("The app stopped")
    assert got["y"].outcome == "ok"

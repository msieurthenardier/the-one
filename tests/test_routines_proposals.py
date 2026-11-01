"""Caps, the proposals repository and the repository's agent-write composition
(M33 F2 L2, DD4/DD6/DD8)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.repositories import SQLiteAgentStore
from the_one.routines.limits import (
    AGENT_PENDING_PROPOSALS_MAX,
    MSG_ACTIVE_CAP,
    MSG_OPEN_CAP,
    ROUTINES_ACTIVE_MAX,
    ROUTINES_OPEN_MAX,
    RoutineLimitError,
    RoutineNameTaken,
    check_routine_caps,
)
from the_one.routines.models import Routine
from the_one.routines.proposals import (
    ProposalOp,
    ProposalStateError,
    RoutineProposalRepository,
)
from the_one.routines.repository import AgentRoutineRepository

UTC = timezone.utc
NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=UTC)
DAILY = {
    "start": {"date": "2026-10-11", "time": "09:00"},
    "repeat": {"every": 1, "unit": "day"},
    "ends": {"kind": "never"},
}


def routine(i=0, schedule=None, enabled=True, finished_at=None, next_run_at=None) -> Routine:
    return Routine(
        id=f"r{i}",
        agent_name="a",
        name=f"n{i}",
        prompt="p",
        schedule=schedule or DAILY,
        enabled=enabled,
        finished_at=finished_at,
        next_run_at=next_run_at,
        created_at="t",
        updated_at="t",
    )


# ── caps ──────────────────────────────────────────────────────────────────


def test_check_caps_active_raise_only() -> None:
    full = [routine(i) for i in range(ROUTINES_ACTIVE_MAX)]
    with pytest.raises(RoutineLimitError) as e:
        check_routine_caps(full, [*full, routine(99)])
    assert e.value.detail == MSG_ACTIVE_CAP
    # Already over the cap: an edit that does not raise the count is accepted.
    over = [routine(i) for i in range(ROUTINES_ACTIVE_MAX + 3)]
    renamed = [over[0].model_copy(update={"name": "x", "prompt": "q"}), *over[1:]]
    check_routine_caps(over, renamed)
    check_routine_caps(over, [over[0].model_copy(update={"enabled": False}), *over[1:]])
    check_routine_caps(over, over[1:])
    # An enable of an off routine, or a reopen of a Done one, raises the count.
    off = [*full, routine(98, enabled=False)]
    with pytest.raises(RoutineLimitError):
        check_routine_caps(off, [*full, routine(98)])
    done = [*full, routine(97, finished_at="t")]
    with pytest.raises(RoutineLimitError):
        check_routine_caps(done, [*full, routine(97)])


def test_check_caps_open_raise_only() -> None:
    off = [routine(i, enabled=False) for i in range(ROUTINES_OPEN_MAX)]
    check_routine_caps([], off[:ROUTINES_ACTIVE_MAX])  # off rows never hit the active cap
    with pytest.raises(RoutineLimitError) as e:
        check_routine_caps(off, [*off, routine(999, enabled=False)])
    assert e.value.detail == MSG_OPEN_CAP
    over = [*off, routine(998, enabled=False)]
    check_routine_caps(over, [over[0].model_copy(update={"prompt": "z"}), *over[1:]])


def test_check_caps_ignores_finished() -> None:
    finished = [routine(20 + i, finished_at="t") for i in range(ROUTINES_OPEN_MAX + 20)]
    check_routine_caps([], [*finished, routine(99)])


# ── repository ────────────────────────────────────────────────────────────


@pytest.fixture
async def env(tmp_path, frozen_clock):
    conn = await connect_template_db(tmp_path / "t.db")
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="a"))
    await store.save(AgentConfig(name="b"))
    yield conn, AgentRoutineRepository(conn), RoutineProposalRepository(conn)
    await conn.close()


def prow(action="create", name="Morning", routine_id=None, agent="a", **over) -> dict:
    return {
        "agent_name": agent,
        "routine_id": routine_id,
        "routine_name": name,
        "action": action,
        "payload": {"name": name} if action == "create" else {"prompt": "x"},
        "base": None if action == "create" else {"prompt": "old"},
        "untrusted": False,
        "untrusted_sources": [],
        "session_id": "s1",
        **over,
    }


def fields(name="Morning", **over) -> dict:
    return {"name": name, "prompt": "p", "schedule": DAILY, **over}


async def test_pending_create_refuses_duplicates(env) -> None:
    _conn, repo, props = env
    got, replaced = await props.insert_pending(prow())
    assert got.status == "pending" and replaced is False
    with pytest.raises(RoutineLimitError, match="already waiting for approval"):
        await props.insert_pending(prow(name="MORNING"))
    await repo.create("a", fields("Taken"))
    with pytest.raises(RoutineNameTaken):
        await props.insert_pending(prow(name="taken"))
    # Another agent may use the same name.
    await props.insert_pending(prow(agent="b"))


async def test_pending_update_supersedes_older(env) -> None:
    _conn, repo, props = env
    r = await repo.create("a", fields())
    first, _ = await props.insert_pending(prow("update", routine_id=r.id))
    second, replaced = await props.insert_pending(prow("update", routine_id=r.id))
    assert replaced is True
    assert (await props.get(first.id)).status == "superseded"
    assert (await props.get(second.id)).status == "pending"
    assert await props.pending_count("a") == 1


async def test_pending_limit(env) -> None:
    _conn, _repo, props = env
    for i in range(AGENT_PENDING_PROPOSALS_MAX):
        await props.insert_pending(prow(name=f"n{i}"))
    with pytest.raises(RoutineLimitError, match="You have 20 changes waiting for approval."):
        await props.insert_pending(prow(name="one-too-many"))
    assert await props.pending_count("a") == AGENT_PENDING_PROPOSALS_MAX


async def test_resolved_proposals_are_not_pruned_by_count(env) -> None:
    conn, _repo, props = env
    for i in range(520):
        stamp = f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}+00:00"
        await conn.execute(
            "INSERT INTO agent_routine_proposals (id, agent_name, routine_name, action, "
            "payload, status, created_at, resolved_at) VALUES (?, 'a', 'n', 'delete', '{}', "
            "'dismissed', ?, ?)",
            (f"d{i:04d}", stamp, stamp),
        )
    await conn.commit()
    await ProposalOp.insert_applied(prow("delete")).run(conn, None)
    await conn.commit()
    async with conn.execute(
        "SELECT COUNT(*) FROM agent_routine_proposals WHERE status != 'pending'"
    ) as cur:
        assert (await cur.fetchone())[0] == 521


async def test_caps_check_runs_in_insert_pending(env) -> None:
    _conn, repo, props = env
    for i in range(ROUTINES_ACTIVE_MAX):
        await repo.create("a", fields(f"r{i}"))

    def caps(before):
        check_routine_caps(before, [*before, routine(99)])

    with pytest.raises(RoutineLimitError):
        await props.insert_pending(prow(name="fifty-first"), caps_check=caps)
    assert await props.pending_count("a") == 0


async def test_delete_resolved_proposals(env) -> None:
    conn, _repo, props = env
    pending, _ = await props.insert_pending(prow(name="keep"))
    for i, (status, resolved) in enumerate(
        [("dismissed", "2026-01-01T00:00:00+00:00"), ("applied", "2026-03-01T00:00:00+00:00")]
    ):
        await conn.execute(
            "INSERT INTO agent_routine_proposals (id, agent_name, routine_name, action, "
            "payload, status, created_at, resolved_at) VALUES (?, 'a', 'n', 'delete', '{}', "
            "?, ?, ?)",
            (f"x{i}", status, resolved, resolved),
        )
    await conn.commit()
    assert await props.delete_resolved_older_than("a", "2026-02-01T00:00:00+00:00") == 1
    assert await props.get("x0") is None and await props.get("x1") is not None
    assert await props.get(pending.id) is not None
    assert await props.delete_resolved_for_agent("a") == 1
    assert await props.get(pending.id) is not None


async def test_dismiss_and_supersede(env) -> None:
    _conn, _repo, props = env
    p, _ = await props.insert_pending(prow())
    done = await props.mark_dismissed(p.id)
    assert done.status == "dismissed" and done.resolved_at
    again = await props.mark_dismissed(p.id)  # idempotent
    assert again.status == "dismissed"
    with pytest.raises(KeyError):
        await props.mark_dismissed("nope")
    q, _ = await props.insert_pending(prow(name="Other"))
    assert await props.supersede_pending("a") == 1
    with pytest.raises(ProposalStateError):
        await props.mark_dismissed(q.id)


async def test_list_filters_and_pages(env) -> None:
    _conn, _repo, props = env
    ids = []
    for i in range(4):
        p, _ = await props.insert_pending(prow(name=f"n{i}"))
        ids.append(p.id)
    await props.mark_dismissed(ids[0])
    assert {r.id for r in await props.list("a", status="dismissed")} == {ids[0]}
    assert len(await props.list("a", limit=2)) == 2
    assert await props.list("b") == []


# ── mutator composition ───────────────────────────────────────────────────


async def test_create_applies_flag_and_applied_proposal(env) -> None:
    conn, repo, props = env
    r = await repo.create(
        "a",
        fields(created_by="agent"),
        flag=("merge", ["web:x", "web:y"]),
        proposal=ProposalOp.insert_applied(prow()),
    )
    assert r.created_by == "agent" and r.untrusted and r.untrusted_sources == ["web:x", "web:y"]
    [p] = await props.list("a")
    assert p.status == "applied" and p.routine_id == r.id and p.resolved_at
    # merge de-duplicates, keeps order, caps at 10
    more = [f"s{i}" for i in range(15)]
    r2 = await repo.update("a", r.id, {"prompt": "z"}, flag=("merge", ["web:y", *more]))
    assert r2.untrusted_sources == ["web:x", "web:y", *more[:8]]
    r3 = await repo.update("a", r.id, {"prompt": "zz"})
    assert r3.untrusted is True  # None leaves the flag alone
    r4 = await repo.update("a", r.id, {"prompt": "zzz"}, flag="clear")
    assert r4.untrusted is False and r4.untrusted_sources == []


async def test_failing_proposal_op_leaves_nothing(env) -> None:
    conn, repo, props = env

    class Boom:
        proposal_id = None

        async def run(self, conn, routine_id):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await repo.create("a", fields(), proposal=Boom())  # type: ignore[arg-type]
    assert await repo.list_for_agent("a") == []
    r = await repo.create("a", fields("Keep"))
    with pytest.raises(RuntimeError):
        await repo.update("a", r.id, {"prompt": "changed"}, proposal=Boom())  # type: ignore[arg-type]
    assert (await repo.get("a", r.id)).prompt == "p"
    with pytest.raises(RuntimeError):
        await repo.delete("a", r.id, proposal=Boom())  # type: ignore[arg-type]
    assert await repo.get("a", r.id) is not None


async def test_precheck_runs_on_reread_row_in_transaction(env) -> None:
    _conn, repo, _props = env
    r = await repo.create("a", fields())
    seen = []
    await repo.update("a", r.id, {"prompt": "n"}, precheck=lambda row: seen.append(row.prompt))
    assert seen == ["p"]

    def refuse(row):
        raise ValueError("no")

    with pytest.raises(ValueError):
        await repo.update("a", r.id, {"prompt": "m"}, precheck=refuse)
    assert (await repo.get("a", r.id)).prompt == "n"
    with pytest.raises(KeyError):
        await repo.update("a", "gone", {"prompt": "m"}, precheck=refuse)
    created = []
    await repo.create("a", fields("Other"), precheck=created.append)
    assert created == [None]


async def test_delete_supersedes_pending_and_nulls_resolved(env) -> None:
    conn, repo, props = env
    r = await repo.create("a", fields())
    pend, _ = await props.insert_pending(prow("update", routine_id=r.id))
    await ProposalOp.insert_applied(prow("update", routine_id=r.id)).run(conn, r.id)
    await conn.commit()
    await repo.delete("a", r.id)
    assert (await props.get(pend.id)).status == "superseded"
    rows = await props.list("a")
    assert {p.status for p in rows} == {"superseded", "applied"}
    assert all(p.routine_id is None and p.routine_name == "Morning" for p in rows)


async def test_rename_carries_and_delete_removes_proposals(env) -> None:
    conn, _repo, props = env
    store = SQLiteAgentStore(conn)
    p, _ = await props.insert_pending(prow())
    await store.rename("a", "renamed")
    assert (await props.get(p.id)).agent_name == "renamed"
    await store.delete("renamed")
    assert await props.get(p.id) is None


async def test_resolve_state_error_rolls_back(env) -> None:
    conn, repo, props = env
    p, _ = await props.insert_pending(prow())
    await props.mark_dismissed(p.id)
    with pytest.raises(ProposalStateError):
        await repo.create("a", fields(), proposal=ProposalOp.resolve(p.id))
    assert await repo.list_for_agent("a") == []

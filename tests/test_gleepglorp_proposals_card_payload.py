"""The card's server side (M36 F2 L6): view title, target_gone, schedule text, the frame's
``session_id`` and the ``proposals_snapshot`` on ready and degraded joins."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from tests._gleepglorp_seed import seed
from the_one import time_zones
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository
from the_one.gleepglorp.proposals import events, shape
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    proposal_view,
)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
async def world(tmp_path, monkeypatch):
    from the_one.db import _write_lock

    _write_lock.reset_for_test()
    monkeypatch.setattr(time_zones, "utcnow", lambda: NOW)
    monkeypatch.setattr(time_zones, "detect_system_zone", lambda: "UTC")
    ns = await seed(tmp_path)
    ns.repo = GleepGlorpProposalRepository(ns.conn)
    yield ns
    await ns.conn.close()


_COUNTER = [0]


async def make(world, kind, action, changes, *, session=None, **target) -> int:
    """Record a proposal; each call gets its own chat unless ``session`` is given (a chat holds
    one open proposal)."""
    if session is None:
        _COUNTER[0] += 1
        session = f"auto-{_COUNTER[0]}"
    n = await shape.normalize(
        kind, action, target, changes, conn=world.conn, now=NOW, zone=UTC, enc=world.enc
    )
    return await world.repo.insert(
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


async def view(world, pid) -> dict:
    return await proposal_view(world.conn, await world.repo.get(pid))


def _in(hours: int) -> dict:
    return {"start": {"in": {"amount": hours, "unit": "hours"}}}


async def test_every_title_and_the_rule_position(world) -> None:
    v = await view(world, await make(world, "agent", "create", {"name": "Fresh"}))
    assert v["title"] == "Create agent “Fresh”" and v["target_gone"] is False
    v = await view(world, await make(world, "agent", "change", {"description": "d"}, agent="plain"))
    assert v["title"] == "Change agent “plain”"
    v = await view(world, await make(world, "rule", "create", {"text": "R."}, agent="wide"))
    assert v["title"] == "Add a rule to “wide”"
    v = await view(
        world, await make(world, "rule", "change", {"enabled": False}, agent="wide", rule=1)
    )
    assert v["title"] == "Change rule 1 of “wide”"
    v = await view(
        world,
        await make(
            world,
            "routine",
            "create",
            {"name": "Nightly", "prompt": "p", "schedule": _in(5)},
            agent="plain",
        ),
    )
    assert v["title"] == "Schedule a routine for “plain”"
    v = await view(
        world,
        await make(
            world, "routine", "change", {"prompt": "q"}, agent="wide", routine="Morning digest"
        ),
    )
    assert v["title"] == "Change routine “Morning digest”"


async def test_the_rule_number_follows_the_current_position(world) -> None:
    from the_one.db.repositories import AgentRuleRepository

    rules = AgentRuleRepository(world.conn)
    pid = await make(world, "rule", "change", {"enabled": False}, agent="wide", rule=1)
    first = (await rules.list_for_agent("wide"))[0]
    await rules.create("wide", "A new first rule.", position=0)
    assert (await view(world, pid))["title"] == "Change rule 2 of “wide”"
    assert first.id == (await rules.list_for_agent("wide"))[1].id


async def test_target_gone_is_computed_on_read_and_never_stored(world) -> None:
    rule_pid = await make(world, "rule", "change", {"enabled": False}, agent="wide", rule=1)
    routine_pid = await make(
        world, "routine", "change", {"prompt": "q"}, agent="wide", routine="Morning digest"
    )
    rule_create = await make(world, "rule", "create", {"text": "R."}, agent="plain", session="s2")
    agent_change = await make(
        world, "agent", "change", {"description": "d"}, agent="plain", session="s3"
    )
    for pid in (rule_pid, routine_pid, rule_create, agent_change):
        assert (await view(world, pid))["target_gone"] is False
    await world.conn.execute("DELETE FROM agents WHERE name IN ('wide', 'plain')")
    await world.conn.commit()
    for pid in (rule_pid, routine_pid, rule_create, agent_change):
        assert (await view(world, pid))["target_gone"] is True
    assert (await world.repo.get(rule_pid)).status == "pending"  # nothing was written


async def test_a_deleted_rule_or_routine_alone_makes_its_change_gone(world) -> None:
    from the_one.db.repositories import AgentRuleRepository
    from the_one.routines.repository import AgentRoutineRepository

    rule_pid = await make(world, "rule", "change", {"enabled": False}, agent="wide", rule=1)
    routine_pid = await make(
        world, "routine", "change", {"prompt": "q"}, agent="wide", routine="Morning digest"
    )
    rule = (await AgentRuleRepository(world.conn).list_for_agent("wide"))[0]
    await AgentRuleRepository(world.conn).delete("wide", rule.id)
    routine = await AgentRoutineRepository(world.conn).get_by_name("wide", "Morning digest")
    await AgentRoutineRepository(world.conn).delete("wide", routine.id)
    assert (await view(world, rule_pid))["target_gone"] is True
    assert (await view(world, routine_pid))["target_gone"] is True


async def test_routines_carry_the_schedule_sentence_and_next_runs(world) -> None:
    v = await view(
        world,
        await make(
            world,
            "routine",
            "create",
            {"name": "Nightly", "prompt": "p", "schedule": _in(5)},
            agent="plain",
        ),
    )
    assert isinstance(v["schedule_text"], str) and v["schedule_text"]
    assert 1 <= len(v["next_runs"]) <= 3 and all(isinstance(s, str) for s in v["next_runs"])
    assert "base_schedule_text" not in v  # a create has no current schedule
    v = await view(
        world,
        await make(
            world,
            "routine",
            "change",
            {"schedule": _in(9)},
            agent="wide",
            routine="Morning digest",
        ),
    )
    assert v["schedule_text"] and v["base_schedule_text"]
    assert v["next_runs"] and v["base_next_runs"]
    agent_view = await view(
        world, await make(world, "agent", "create", {"name": "Fresh"}, session="s9")
    )
    assert "schedule_text" not in agent_view


async def test_the_pushed_frame_carries_the_session_id(monkeypatch) -> None:
    sent = []

    async def broadcast(session_id, payload):
        sent.append((session_id, payload))

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", broadcast)
    await events.push_proposal_changed("s1", {"id": 4})
    assert sent == [("s1", {"type": "proposal_changed", "session_id": "s1", "proposal": {"id": 4}})]


# --- the snapshot ---------------------------------------------------------------------


async def test_the_snapshot_has_every_proposal_in_id_order(world) -> None:
    a = await make(world, "agent", "change", {"description": "one"}, agent="plain", session="s1")
    await world.repo.mark(a, "dismissed", from_statuses=("pending",))
    b = await make(world, "agent", "change", {"description": "two"}, agent="plain", session="s1")
    await make(world, "agent", "change", {"description": "other chat"}, agent="wide", session="s2")
    frame = await events.snapshot_frame(world.conn, "s1", "GleepGlorp")
    assert frame["type"] == "proposals_snapshot" and frame["session_id"] == "s1"
    assert [p["id"] for p in frame["proposals"]] == [a, b]
    assert [p["status"] for p in frame["proposals"]] == ["dismissed", "pending"]
    assert await events.snapshot_frame(world.conn, "s1", "plain") is None
    assert await events.snapshot_frame(world.conn, "s1", None) is None


async def test_the_snapshot_is_capped_at_the_newest_two_hundred(world, monkeypatch) -> None:
    monkeypatch.setattr(events, "SNAPSHOT_CAP", 2)
    ids = []
    for text in ("one", "two", "three"):
        pid = await make(
            world, "agent", "change", {"description": text}, agent="plain", session="s1"
        )
        await world.repo.mark(pid, "dismissed", from_statuses=("pending",))
        ids.append(pid)
    frame = await events.snapshot_frame(world.conn, "s1", "GleepGlorp")
    assert [p["id"] for p in frame["proposals"]] == ids[1:]


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload) -> None:
        self.sent.append(payload)


async def test_the_join_helper_sends_the_frame_and_a_read_failure_sends_nothing(world) -> None:
    import the_one.interfaces.web.app as app_module

    await make(world, "agent", "change", {"description": "d"}, agent="plain", session="s1")
    ws = _Socket()
    with patch.object(app_module, "get_connection", AsyncMock(return_value=world.conn)):
        await app_module._send_proposals_snapshot(ws, "s1", "GleepGlorp")
        await app_module._send_proposals_snapshot(ws, "s1", "plain")  # another agent: nothing
        await app_module._send_proposals_snapshot(ws, "s1", "GleepGlorp")  # a reconnect repeats
    assert [f["type"] for f in ws.sent] == ["proposals_snapshot", "proposals_snapshot"]
    assert ws.sent[0] == ws.sent[1]
    broken = _Socket()
    with patch.object(app_module, "get_connection", AsyncMock(side_effect=RuntimeError("db"))):
        await app_module._send_proposals_snapshot(broken, "s1", "GleepGlorp")
    assert broken.sent == []


@pytest.mark.parametrize("state", ["off", "needs_model", "provider_missing"])
async def test_a_degraded_join_has_the_snapshot_with_no_live_session(world, state) -> None:
    """The three degraded GleepGlorp states restore with no ``Session``; the snapshot is keyed
    by the stored row's ids and still carries the chat's proposals."""
    import the_one.interfaces.web.app as app_module
    from the_one.agent.factory import GleepGlorpUnavailableError

    await ChatSessionRepository(world.conn).create(
        ChatSession(id="gg-chat", agent_name="GleepGlorp", title="t")
    )
    pid = await make(
        world, "agent", "change", {"description": "d"}, agent="plain", session="gg-chat"
    )
    factory = AsyncMock()
    factory.create = AsyncMock(side_effect=GleepGlorpUnavailableError(state))
    saved = app_module._sessions
    app_module._sessions = {}
    try:
        with (
            patch.object(
                app_module, "_chat_repo", AsyncMock(return_value=ChatSessionRepository(world.conn))
            ),
            patch.object(app_module, "_get_factory", return_value=factory),
            patch.object(app_module, "get_connection", AsyncMock(return_value=world.conn)),
        ):
            restored = await app_module._restore_session("gg-chat")
            assert restored.session is None and restored.is_degraded
            ws = _Socket()
            await app_module._send_proposals_snapshot(
                ws, restored.db_session.id, restored.db_session.agent_name
            )
    finally:
        app_module._sessions = saved
    assert len(ws.sent) == 1 and ws.sent[0]["type"] == "proposals_snapshot"
    assert [p["id"] for p in ws.sent[0]["proposals"]] == [pid]

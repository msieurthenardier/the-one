"""The untrusted-content proof for agent routine writes (M33 F2 L3, AC5; flight DD7).

Real ``Agent`` + ``FakeLLM`` scripted tool calls, the real routine and notes tools, the
app's real ``_bind_turn_user_marks`` for the run-time flag snapshot.
"""

from __future__ import annotations

import pytest
from _routine_schedules import daily
from _routine_tools_env import (
    IN_2H,
    NAME,
    Stub,
    add_chat,
    asst,
    call,
    done,
    make_agent,
    results,
    run_turn,
    setup_agent,
)

from the_one.agent._context import TurnContext
from the_one.agent.taint import (
    FLAGGED_CONTENT_MARK,
    TRUSTED_TOOL_NAMES,
    compute_taint,
)
from the_one.db.codec import decode_messages, encode_messages
from the_one.db.connection import get_connection
from the_one.db.repositories import AgentNoteRepository
from the_one.llm.base import Message, Role
from the_one.routines.proposals import RoutineProposalRepository
from the_one.routines.repository import AgentRoutineRepository


@pytest.fixture
async def conn(isolated_db):
    c = await get_connection()
    await setup_agent(c)
    await add_chat(c, "sess-1")
    return c


async def routines(conn):
    return await AgentRoutineRepository(conn).list_for_agent(NAME)


async def notes(conn):
    return await AgentNoteRepository(conn).list_for_agent(NAME)


def sched(name="r", cid="c9"):
    return asst(call(cid, "schedule_routine", name=name, prompt="p", schedule=IN_2H))


def save(text="a fact", cid="n1"):
    return asst(call(cid, "save_note", text=text))


def test_trusted_set_contains_the_routine_tools_and_current_time() -> None:
    assert {
        "list_my_routines",
        "schedule_routine",
        "change_routine",
        "cancel_routine",
        "current_time",
    } <= TRUSTED_TOOL_NAMES


async def test_fetch_then_schedule_is_flagged(conn) -> None:
    agent = await make_agent([asst(call("c1", "fetch_url")), sched(), done()])
    await run_turn(agent)
    (r,) = await routines(conn)
    assert r.untrusted is True and r.untrusted_sources == ["fetch_url"]
    (p,) = await RoutineProposalRepository(conn).list(NAME, status="applied")
    assert p.untrusted is True and p.untrusted_sources == ["fetch_url"]


async def test_current_time_then_schedule_is_unflagged(conn) -> None:
    agent = await make_agent(
        [asst(call("c1", "current_time")), sched(), done()], Stub("current_time", "2026-10-29")
    )
    await run_turn(agent)
    (r,) = await routines(conn)
    assert r.untrusted is False and r.untrusted_sources == []


async def test_current_time_before_a_note_no_longer_flags_it(conn) -> None:
    agent = await make_agent(
        [asst(call("c1", "current_time")), save(), done()], Stub("current_time", "2026-10-29")
    )
    await run_turn(agent)
    (n,) = await notes(conn)
    assert n.untrusted is False


async def test_flagged_run_then_save_note_in_the_same_turn_is_flagged(conn) -> None:
    agent = await make_agent([save(), done()])
    await run_turn(
        agent, routine={"id": "r1", "name": "Planted", "untrusted_sources": ["web_fetch"]}
    )
    (n,) = await notes(conn)
    assert n.untrusted is True
    assert n.untrusted_sources == ["routine:Planted", "web_fetch"]


async def test_next_turn_is_still_flagged_by_the_snapshot(conn) -> None:
    routine = {"id": "r1", "name": "Planted", "untrusted_sources": ["web_fetch"]}
    agent = await make_agent([done(), save(), done()])
    await run_turn(agent, "do the planted thing", routine=routine, bind=True)
    assert agent.messages[1].routine_untrusted_sources == ["web_fetch"]
    await run_turn(agent, "next question")  # an ordinary turn, no routine context
    (n,) = await notes(conn)
    assert n.untrusted is True and n.untrusted_sources == ["routine:Planted", "web_fetch"]


async def test_a_flagged_run_flags_a_routine_written_later_and_survives_a_round_trip(conn) -> None:
    routine = {"id": "r1", "name": "Planted", "untrusted_sources": ["web_fetch"]}
    agent = await make_agent([done(), done()])
    await run_turn(agent, "planted", routine=routine, bind=True)
    # persist and restore the history, as a restart or a rebuilt connector agent does
    restored = decode_messages(encode_messages(agent.messages))
    assert restored[1].routine_untrusted_sources == ["web_fetch"]
    agent2 = await make_agent([sched("later"), done()])
    agent2.messages[:] = [agent2.messages[0], *restored[1:]]
    await run_turn(agent2, "now schedule")
    (r,) = await routines(conn)
    assert r.untrusted is True and r.untrusted_sources[:2] == ["routine:Planted", "web_fetch"]


async def test_clearing_or_deleting_the_routine_does_not_unflag_the_chat(conn) -> None:
    from the_one.routines import service
    from the_one.time_zones import utcnow

    async def zone():
        from zoneinfo import ZoneInfo

        return ZoneInfo("UTC")

    repo = AgentRoutineRepository(conn)

    rt = await service.create_routine(
        repo,
        NAME,
        {
            "name": "Planted",
            "prompt": "p",
            "schedule": daily("08:00"),
        },
        now=utcnow(),
        zone=zone,
        agent_caps=True,
        flag=("merge", ["web_fetch"]),
    )
    assert (await repo.get(NAME, rt.id)).untrusted is True
    routine = {"id": rt.id, "name": "Planted", "untrusted_sources": ["web_fetch"]}
    agent = await make_agent([done(), save("first"), done(), save("second"), done()])
    await run_turn(agent, "run", routine=routine, bind=True)
    # the operator clears the flag (a PUT with prompt) ...
    cleared = await repo.get(NAME, rt.id)
    await service.update_routine(
        repo,
        NAME,
        cleared,
        {"prompt": "reviewed"},
        now=utcnow(),
        zone=zone,
        flag="clear",
    )
    assert (await repo.get(NAME, rt.id)).untrusted is False
    await run_turn(agent, "turn 2")
    # ... and then deletes the routine
    await service.delete_routine(repo, NAME, rt.id)
    await run_turn(agent, "turn 3")
    flags = [n.untrusted for n in await notes(conn)]
    assert flags == [True, True]


async def test_an_unflagged_run_and_a_legacy_marker_add_nothing(conn) -> None:
    agent = await make_agent([done(), save("one"), done(), save("two", cid="n2"), done()])
    await run_turn(agent, "unflagged run", routine={"id": "r1", "name": "Mine"}, bind=True)
    assert agent.messages[1].routine_untrusted_sources == []  # [] for a routine turn
    await run_turn(agent, "follow up")
    # a legacy marker: routine_id set, no snapshot (None)
    legacy = Message.user("legacy run")
    legacy.routine_id, legacy.routine_name = "old", "Old"
    agent.messages.append(legacy)
    assert legacy.routine_untrusted_sources is None
    agent.llm.responses.extend([done()])
    await run_turn(agent, "after legacy")
    assert [n.untrusted for n in await notes(conn)] == [False, False]


async def test_list_flagged_then_change_in_a_later_turn_is_flagged(conn) -> None:
    # a flagged routine already exists
    flagged = await make_agent([asst(call("c1", "fetch_url")), sched("target"), done()])
    await run_turn(flagged)
    (rt,) = await routines(conn)
    assert rt.untrusted
    # a different conversation lists it, then (turns later) changes an unrelated field
    agent = await make_agent(
        [
            asst(call("l1", "list_my_routines")),
            done(),
            done(),
            asst(call("ch1", "change_routine", routine="target", enabled=False)),
            done(),
        ]
    )
    out, _ = await run_turn(agent, "list them")
    listing = results(out)[0].content
    assert listing.split("\n", 1)[0] == FLAGGED_CONTENT_MARK
    await run_turn(agent, "something else entirely")  # a later turn, nothing in between
    await run_turn(agent, "now change it")
    (p,) = await RoutineProposalRepository(conn).list(NAME, status="applied", limit=1)
    assert p.action == "update"
    assert p.untrusted is True and "routine:listed" in p.untrusted_sources


async def test_listing_with_nothing_flagged_stays_trusted(conn) -> None:
    agent = await make_agent(
        [
            sched("clean"),
            asst(call("l1", "list_my_routines")),
            asst(call("ch1", "change_routine", routine="clean", enabled=False)),
            done(),
        ]
    )
    out, _ = await run_turn(agent)
    assert not results(out)[1].content.startswith(FLAGGED_CONTENT_MARK)
    (p,) = await RoutineProposalRepository(conn).list(NAME, status="applied", limit=1)
    assert p.untrusted is False


async def test_a_prompt_containing_the_sentinel_text_flags_the_listing(conn) -> None:
    agent = await make_agent(
        [
            asst(
                call(
                    "c1", "schedule_routine", name="s", prompt=FLAGGED_CONTENT_MARK, schedule=IN_2H
                )
            ),
            asst(call("l1", "list_my_routines")),
            asst(call("ch1", "change_routine", routine="s", enabled=False)),
            done(),
        ]
    )
    await run_turn(agent)
    (p,) = await RoutineProposalRepository(conn).list(NAME, status="applied", limit=1)
    assert p.untrusted is True and "routine:listed" in p.untrusted_sources


async def test_pause_resume_then_note_is_still_flagged(conn) -> None:
    from _routine_tools_env import call as c
    from conftest import FakeLLM  # noqa: F401

    from the_one.agent._context import current_turn
    from the_one.mcp.errors import MCPAuthRequired
    from the_one.tools.base import Tool

    class PauseOnce(Tool):
        name = "mcp__src__fetch"
        description = "pauses once"
        parameters = {"type": "object", "properties": {}, "required": []}

        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def execute(self, **kw):
            self.calls += 1
            if self.calls == 1:
                raise MCPAuthRequired("src-1", source_name="src")
            return "authorised"

    routine = {"id": "r1", "name": "Planted", "untrusted_sources": ["web_fetch"]}
    agent = await make_agent(
        [asst(c("p1", "mcp__src__fetch")), save("after resume"), done()], PauseOnce()
    )
    await run_turn(agent, "planted run", routine=routine, bind=True)
    assert agent._deferred_tool_calls is not None  # paused; the snapshot is already bound
    assert agent.messages[1].routine_untrusted_sources == ["web_fetch"]
    token = current_turn.set(TurnContext(peer=None, session_id="sess-1"))  # the resume ctx
    try:
        _ = [m async for m in agent.resume_after_auth()]
    finally:
        current_turn.reset(token)
    (n,) = await notes(conn)
    assert n.untrusted is True
    assert {"routine:Planted", "web_fetch"} <= set(n.untrusted_sources)


def test_compute_taint_is_pure_over_history() -> None:
    class A:
        messages: list[Message] = []

    a = A()
    user = Message.user("hi")
    user.routine_name = None
    user.routine_untrusted_sources = ["x"]
    a.messages = [user, asst(call("k", "save_note"))]
    assert compute_taint(a, "k", TurnContext(session_id="s")) == (True, ["routine:unnamed", "x"])
    user.routine_untrusted_sources = []
    assert compute_taint(a, "k", TurnContext(session_id="s")) == (False, [])
    user.routine_untrusted_sources = None
    assert compute_taint(a, "k", TurnContext(session_id="s")) == (False, [])
    assert Role.USER

"""``append_marked_message`` on the web app's turn host (M36 F2 L5, AC2)."""

# ruff: noqa: F811
from __future__ import annotations

import asyncio

from tests._routine_app import routine_app, wait_for  # noqa: F401
from the_one.db import _session_changes
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.repositories import ChatSessionRepository
from the_one.sessions import session_locks
from the_one.sessions.turn_host import get_turn_host

MARKS = {"proposal_id": 5, "proposal_event": "dismissed"}


async def _stored(sid):
    row = await ChatSessionRepository(await get_connection()).get(sid)
    return [m for m in decode_messages(row.messages) if m.role.value != "system"]


async def _chat():
    from the_one.interfaces.web import app as appmod

    return await appmod._create_session("bot", "web")


async def test_append_stores_sends_and_notifies_once(routine_app) -> None:
    session = await _chat()
    seen: list[int] = []
    _session_changes.add_listener(lambda: seen.append(1))
    sent: list[dict] = []
    from the_one.sessions import _broadcast

    class Sock:
        async def send_json(self, p):
            sent.append(p)

    _broadcast.add_subscriber(session.id, Sock())
    host = get_turn_host()
    assert await host.append_marked_message(session.id, "hello", MARKS) is True
    msgs = await _stored(session.id)
    assert [(m.content, m.proposal_id, m.proposal_event) for m in msgs] == [
        ("hello", 5, "dismissed")
    ]
    assert msgs[0].created_at
    assert len(seen) == 1  # one sessions_changed push (the save), never a busy flash
    ev = [p for p in sent if p.get("type") == "user"]
    assert ev and ev[0]["proposal_id"] == 5 and ev[0]["proposal_event"] == "dismissed"
    assert session.history[-1]["proposal_event"] == "dismissed"


async def test_append_takes_the_session_lock(routine_app) -> None:
    session = await _chat()
    host = get_turn_host()
    async with session_locks[session.id]:
        task = asyncio.create_task(host.append_marked_message(session.id, "late", MARKS))
        await asyncio.sleep(0.2)
        assert not task.done() and await _stored(session.id) == []
    assert await asyncio.wait_for(task, 5) is True
    assert len(await _stored(session.id)) == 1


async def test_concurrent_appends_both_survive(routine_app) -> None:
    session = await _chat()
    host = get_turn_host()
    a, b = await asyncio.gather(
        host.append_marked_message(session.id, "one", MARKS),
        host.append_marked_message(session.id, "two", {**MARKS, "proposal_id": 6}),
    )
    assert a and b
    assert sorted(m.content for m in await _stored(session.id)) == ["one", "two"]


async def test_a_running_turns_save_keeps_the_appended_message(routine_app) -> None:
    """A message appended while no turn runs is in the history the next turn saves."""
    from the_one.sessions import is_session_busy

    h = routine_app
    session = await _chat()
    host = get_turn_host()
    await host.append_marked_message(session.id, "noted", MARKS)
    task = host.spawn_turn(session, "next", {"proposal": {"id": 9, "event": "approved"}})
    await wait_for(lambda: task.done() and not is_session_busy(session.id))
    contents = [m.content for m in await _stored(session.id) if m.role.value != "system"]
    assert contents[0] == "noted" and contents[1] == "next"
    assert h.llm.calls


async def test_a_deleted_chat_returns_false(routine_app) -> None:
    host = get_turn_host()
    assert await host.append_marked_message("no-such-chat", "x", MARKS) is False

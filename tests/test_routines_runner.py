"""End-to-end routine runs through the real app lifespan (M33 F1 leg 4, AC2-AC10).

The ``routine_app`` fixture and ``Harness`` live in ``tests/_routine_app.py``.
"""

# ruff: noqa: F811
from __future__ import annotations

import asyncio
import time  # noqa: F401

import pytest

from tests._routine_app import (  # noqa: F401
    WS,
    Harness,
    ScriptLLM,
    routine_app,
    wait_for,
)
from the_one.agent.config import AgentConfig  # noqa: F401
from the_one.config import settings  # noqa: F401
from the_one.connectors.stub import StubPlugin
from the_one.db.connection import get_connection
from the_one.db.repositories import ChatSessionRepository
from the_one.llm.base import Message, ToolCall  # noqa: F401
from the_one.routines import runner
from the_one.sessions import add_subscriber, remove_subscriber

pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")

# ── Run now in a connector DM ──────────────────────────────────────────────


async def test_run_now_in_connector_dm(routine_app):
    h = routine_app
    sid = await h.dm("hello")
    r = await h.routine({"kind": "chat", "session_id": sid})
    StubPlugin.outbound_records.clear()
    ws = WS()
    add_subscriber(sid, ws)
    h.llm.script = [Message.assistant(content="the brief")]
    await h.run_now(r["id"])
    remove_subscriber(sid, ws)

    run = await h.last_run(r["id"])
    assert run["outcome"] == "ok", run
    assert run["trigger_kind"] == "manual" and run["new_chat"] is False
    assert run["session_id"] == sid

    # exactly the final reply, to the chat's own target; the prompt is never sent
    assert len(StubPlugin.outbound_records) == 1
    target, content = StubPlugin.outbound_records[0]
    assert content == "the brief"
    assert target.connector_id == h.connector_id and target.channel_id == ""
    assert "do the thing" not in content

    from the_one.db.codec import decode_messages
    from the_one.llm.base import Role

    row = await ChatSessionRepository(await get_connection()).get(sid)
    msgs = decode_messages(row.messages)
    user = [m for m in msgs if m.role == Role.USER and m.content == "do the thing"]
    assert len(user) == 1
    assert user[0].routine_name == "Brief" and user[0].visibility == "operator"
    replies = [m for m in msgs if m.role == Role.ASSISTANT and m.content == "the brief"]
    assert len(replies) == 1 and replies[0].visibility is None
    assert row.session_metadata["routine"]["name"] == "Brief"

    updated = [f for f in ws.frames if f.get("type") == "session_updated"]
    assert updated and updated[0]["session_id"] == sid
    types = [f.get("type") for f in ws.frames]
    assert types.index("session_updated") > types.index("done")
    # the route never touched the schedule
    got = (await h.api("GET", f"/api/agents/bot/routines/{r['id']}")).json()
    assert got["next_run_at"] == r["next_run_at"] and got["finished_at"] is None
    assert got["running"] is False


async def test_already_sent_has_no_second_send(routine_app):
    h = routine_app
    sid = await h.dm("hello", channel="dm-1")
    r = await h.routine({"kind": "chat", "session_id": sid})
    StubPlugin.outbound_records.clear()
    before = (await ChatSessionRepository(await get_connection()).get(sid)).last_inbound_at
    await asyncio.sleep(0.01)
    h.llm.script = [
        Message.assistant(
            content="",
            tool_calls=[
                ToolCall(
                    id="t1", name="send_to_platform_channel", arguments={"content": "via tool"}
                )
            ],
        ),
        Message.assistant(content="all done"),
    ]
    await h.run_now(r["id"])
    run = await h.last_run(r["id"])
    assert run["outcome"] == "ok", run
    assert [c for _, c in StubPlugin.outbound_records] == ["via tool"]
    after = (await ChatSessionRepository(await get_connection()).get(sid)).last_inbound_at
    assert after > before


# ── target resolution ──────────────────────────────────────────────────────


async def test_new_then_run_now_creates_connector_chat_and_retargets(routine_app):
    h = routine_app
    sid = await h.dm("hello")
    r = await h.routine({"kind": "chat", "session_id": sid})
    # /new ends the chat
    await h.api(
        "POST",
        "/api/_test/stub/inbound",
        json={"connector_id": h.connector_id, "peer_id": "p1", "text": "/new", "is_dm": True},
    )
    repo = ChatSessionRepository(await get_connection())
    await wait_for(lambda: _ended(repo, sid))
    await h.run_now(r["id"])
    run = await h.last_run(r["id"])
    assert run["outcome"] == "ok", run
    assert run["new_chat"] is True and run["session_id"] != sid
    new = await repo.get(run["session_id"])
    old = await repo.get(sid)
    for col in ("platform", "connector_id", "channel_id", "thread_id", "peer_id", "agent_name"):
        assert getattr(new, col) == getattr(old, col)
    got = (await h.api("GET", f"/api/agents/bot/routines/{r['id']}")).json()
    assert got["target"]["session_id"] == new.id
    assert [c for _, c in StubPlugin.outbound_records][-1] == "routine reply"


async def _ended(repo, sid):
    return "ended_at" in ((await repo.get(sid)).session_metadata or {})


async def test_deleted_web_chat_target_starts_new_chat(routine_app):
    h = routine_app
    r = await h.api("POST", "/api/chat/sessions", json={"agent_name": "bot", "title": "mine"})
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    rt = await h.routine({"kind": "chat", "session_id": sid})
    await h.api("DELETE", f"/api/chat/sessions/{sid}")
    await h.run_now(rt["id"])
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "ok" and run["new_chat"] is True
    assert "The chosen chat was gone" in run["reason"]
    row = await ChatSessionRepository(await get_connection()).get(run["session_id"])
    assert row.title == "Brief" and row.connector_id is None


async def test_new_target_creates_a_chat_every_run(routine_app):
    h = routine_app
    rt = await h.routine({"kind": "new"})
    await h.run_now(rt["id"])
    await h.run_now(rt["id"])
    runs = await h.runs(rt["id"])
    assert len(runs) == 2 and all(x["new_chat"] and x["outcome"] == "ok" for x in runs)
    assert runs[0]["session_id"] != runs[1]["session_id"]
    assert StubPlugin.outbound_records == []


async def test_own_target_reuses_its_chat(routine_app):
    h = routine_app
    rt = await h.routine({"kind": "own"})
    await h.run_now(rt["id"])
    await h.run_now(rt["id"])
    first, second = (await h.runs(rt["id"]))[::-1]
    assert first["new_chat"] is True and second["new_chat"] is False
    assert first["session_id"] == second["session_id"]


# ── pre-checks, degraded, paused ───────────────────────────────────────────


async def test_precheck_connector_disabled(routine_app):
    h = routine_app
    sid = await h.dm("hello")
    r = await h.routine({"kind": "chat", "session_id": sid})
    n = len(await h.chat_rows())
    resp = await h.api(
        "PUT",
        f"/api/connectors/{h.connector_id}",
        json={"config": {"default_agent": "bot", "enabled": False}},
    )
    assert resp.status_code == 200, resp.text
    from the_one.connectors.manager import get_manager

    await wait_for(lambda: get_manager().client_for(h.connector_id) is None)
    await h.run_now(r["id"])
    run = await h.last_run(r["id"])
    assert run["outcome"] == "failed" and run["session_id"] is None
    assert run["reason"] == "Stubby isn't connected."
    assert len(await h.chat_rows()) == n


async def test_precheck_wrong_agent(routine_app):
    h = routine_app
    sid = await h.dm("hello")
    r = await h.routine({"kind": "chat", "session_id": sid})
    resp = await h.api(
        "PUT",
        f"/api/connectors/{h.connector_id}",
        json={"config": {"default_agent": "other", "allowlist": {"peers": ["p1"]}}},
    )
    assert resp.status_code == 200, resp.text
    from the_one.connectors.manager import get_manager

    await wait_for(lambda: get_manager().client_for(h.connector_id) is not None)
    n = len(await h.chat_rows())
    await h.run_now(r["id"])
    run = await h.last_run(r["id"])
    assert run["outcome"] == "failed" and run["session_id"] is None
    assert run["reason"] == "This channel is now answered by other."
    assert len(await h.chat_rows()) == n


async def test_paused_peek_skips_and_keeps_the_pause(routine_app):
    h = routine_app
    rt = await h.routine({"kind": "own"})
    await h.run_now(rt["id"])
    sid = (await h.last_run(rt["id"]))["session_id"]
    from the_one.interfaces.web import app as appmod

    cached = appmod._sessions[sid]
    marker = [object()]
    cached.agent._deferred_tool_calls = marker
    agent_before = cached.agent
    await h.run_now(rt["id"])
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "skipped"
    assert run["reason"] == "The chat is waiting for a sign-in."
    assert appmod._sessions[sid].agent is agent_before
    assert agent_before._deferred_tool_calls is marker
    cached.agent._deferred_tool_calls = None


async def test_own_pause_does_not_block(routine_app):
    h = routine_app
    rt = await h.routine({"kind": "own"})
    await h.run_now(rt["id"])
    sid = (await h.last_run(rt["id"]))["session_id"]
    from the_one.interfaces.web import app as appmod

    appmod._sessions[sid].agent._deferred_tool_calls = [object()]
    runner.registry.remember_pause(rt["id"], sid)
    await h.run_now(rt["id"])
    assert (await h.last_run(rt["id"]))["outcome"] == "ok"
    assert runner.registry.own_pause(rt["id"]) is None


async def test_agent_deleted_after_target_resolved(routine_app):
    h = routine_app
    rt = await h.routine({"kind": "own"})
    await h.run_now(rt["id"])
    sid = (await h.last_run(rt["id"]))["session_id"]
    from the_one.interfaces.web import app as appmod

    async def gone(sid_):
        return appmod.RestoredSession(None, "agent_deleted", None)

    orig = appmod._get_or_restore_session
    appmod._get_or_restore_session = gone
    try:
        await h.run_now(rt["id"])
    finally:
        appmod._get_or_restore_session = orig
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "failed" and run["reason"] == "The agent no longer exists."
    assert run["session_id"] == sid


# ── timeouts and drain ─────────────────────────────────────────────────────


async def test_busy_chat_times_out_as_skipped_without_cancelled_frame(routine_app, monkeypatch):
    h = routine_app
    monkeypatch.setattr(runner, "_TIMEOUT_FLOOR_SECONDS", 0.1)
    monkeypatch.setenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", "0.3")
    rt = await h.routine({"kind": "own"})
    await h.run_now(rt["id"])
    sid = (await h.last_run(rt["id"]))["session_id"]
    from the_one.sessions import session_locks

    ws = WS()
    add_subscriber(sid, ws)
    async with session_locks[sid]:
        await h.run_now(rt["id"])
    remove_subscriber(sid, ws)
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "skipped"
    assert run["reason"].startswith("The chat stayed busy for 1 minute")
    assert not [f for f in ws.frames if f.get("type") == "cancelled"]


async def test_long_run_times_out_as_failed_with_partial(routine_app, monkeypatch):
    h = routine_app
    monkeypatch.setattr(runner, "_TIMEOUT_FLOOR_SECONDS", 0.1)
    monkeypatch.setenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", "0.3")
    h.llm.delay = 5.0
    rt = await h.routine({"kind": "own"})
    await h.run_now(rt["id"])
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "failed", run
    assert run["reason"].startswith("The run took longer than 1 minute")
    from the_one.db.codec import decode_messages

    row = await ChatSessionRepository(await get_connection()).get(run["session_id"])
    assert any(m.content == "do the thing" for m in decode_messages(row.messages))


async def test_drain_during_run_is_interrupted(routine_app):
    h = routine_app
    h.llm.delay = 30.0
    rt = await h.routine({"kind": "own"})
    r = await h.api("POST", f"/api/agents/bot/routines/{rt['id']}/run")
    assert r.status_code == 202
    from the_one.sessions import is_session_busy

    async def started():
        runs = await h.runs(rt["id"])
        return bool(runs) and runs[0]["session_id"] and is_session_busy(runs[0]["session_id"])

    await wait_for(started)
    assert (await h.api("POST", f"/api/agents/bot/routines/{rt['id']}/run")).status_code == 409
    await runner.registry.drain(5.0)
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "interrupted"
    assert run["reason"] == "The app stopped during this run."

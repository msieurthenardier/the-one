"""End-to-end routine runs through the real app lifespan (M33 F1 leg 4, AC2-AC10).

Every run starts a new web chat (M33 F4 leg 2). The ``routine_app`` fixture and
``Harness`` live in ``tests/_routine_app.py``.
"""

# ruff: noqa: F811
from __future__ import annotations

import pytest

from tests._routine_app import routine_app, wait_for  # noqa: F401
from the_one.connectors.stub import StubPlugin
from the_one.db.connection import get_connection
from the_one.db.repositories import ChatSessionRepository
from the_one.llm.base import Message
from the_one.routines import runner

pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")

# ── a run starts a new chat ────────────────────────────────────────────────


async def test_run_now_starts_a_new_chat(routine_app):
    h = routine_app
    r = await h.routine()
    h.llm.script = [Message.assistant(content="the brief")]
    await h.run_now(r["id"])

    run = await h.last_run(r["id"])
    assert run["outcome"] == "ok", run
    assert run["trigger_kind"] == "manual"
    assert run["chat_exists"] is True
    sid = run["session_id"]

    from the_one.db.codec import decode_messages
    from the_one.llm.base import Role

    row = await ChatSessionRepository(await get_connection()).get(sid)
    assert row.title == "Brief" and row.agent_name == "bot" and row.platform is None
    msgs = decode_messages(row.messages)
    user = [m for m in msgs if m.role == Role.USER and m.content == "do the thing"]
    assert len(user) == 1 and user[0].routine_name == "Brief"
    assert [m.content for m in msgs if m.role == Role.ASSISTANT] == ["the brief"]
    assert row.session_metadata["routine"]["name"] == "Brief"
    # the route never touched the schedule
    got = (await h.api("GET", f"/api/agents/bot/routines/{r['id']}")).json()
    assert got["next_run_at"] == r["next_run_at"] and got["finished_at"] is None
    assert got["running"] is False
    assert "target" not in got and "target" not in r


async def test_each_trigger_starts_a_separate_chat(routine_app):
    """AC2: a scheduled run, a Run now and a catch-up run use three distinct chats."""
    h = routine_app
    rt = await h.routine()
    await runner.run_routine(rt["id"], "schedule", "2026-01-01T09:00:00+00:00")
    await h.run_now(rt["id"])
    await runner.run_routine(rt["id"], "catch_up", "2026-01-01T09:00:00+00:00")

    runs = await h.runs(rt["id"])
    assert sorted(x["trigger_kind"] for x in runs) == ["catch_up", "manual", "schedule"]
    assert all(x["outcome"] == "ok" for x in runs)
    sids = {x["session_id"] for x in runs}
    assert len(sids) == 3
    repo = ChatSessionRepository(await get_connection())
    assert {(await repo.get(s)).title for s in sids} == {"Brief"}


async def test_a_run_never_delivers_to_a_connector(routine_app):
    """The agent is a connector's default agent; a run still posts nothing to it."""
    h = routine_app
    rt = await h.routine()
    StubPlugin.outbound_records.clear()
    await h.run_now(rt["id"])
    await h.run_now(rt["id"])
    assert StubPlugin.outbound_records == []
    repo = ChatSessionRepository(await get_connection())
    for run in await h.runs(rt["id"]):
        row = await repo.get(run["session_id"])
        assert row.platform is None and row.connector_id is None


async def test_runs_report_whether_their_chat_still_exists(routine_app):
    h = routine_app
    rt = await h.routine()
    await h.run_now(rt["id"])
    await h.run_now(rt["id"])
    newest, oldest = await h.runs(rt["id"])
    assert newest["chat_exists"] is True and oldest["chat_exists"] is True
    await h.api("DELETE", f"/api/chat/sessions/{oldest['session_id']}")
    newest, oldest = await h.runs(rt["id"])
    assert newest["chat_exists"] is True and oldest["chat_exists"] is False
    assert oldest["session_id"]  # the id is kept; leg 03 decides the link


async def test_agent_deleted_after_the_chat_was_created(routine_app):
    h = routine_app
    rt = await h.routine()
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
    assert run["session_id"]


async def test_build_failed_restore_records_its_own_reason(routine_app):
    """Sortie 07 DD7: a restore that lands on `build_failed` is a `failed` run with
    its own fixed sentence, not "The chat is no longer available."."""
    h = routine_app
    rt = await h.routine()
    from the_one.interfaces.web import app as appmod

    async def broken(sid_):
        return appmod.RestoredSession(None, "build_failed", None, reason=appmod.BUILD_FAILED_REASON)

    orig = appmod._get_or_restore_session
    appmod._get_or_restore_session = broken
    try:
        await h.run_now(rt["id"])
    finally:
        appmod._get_or_restore_session = orig
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "failed"
    assert run["reason"] == (
        "The agent could not be set up. Check the agent's settings; the app log has the details."
    )
    assert run["session_id"]


async def test_restore_racing_a_routine_turn_does_not_swap_its_agent(routine_app, monkeypatch):
    """F-H1-1: a browser join that passed the in-flight check and is still building its
    agent when the routine's turn starts must not replace the turn's agent; the run's
    chat keeps its user message and reply."""
    import asyncio

    from the_one.db.codec import decode_messages
    from the_one.interfaces.web import app as appmod
    from the_one.llm.base import Role

    h = routine_app
    rt = await h.routine()
    h.llm.delay = 0.3
    factory = appmod._get_factory()
    real_create = factory.create
    gate, blocked = asyncio.Event(), asyncio.Event()
    calls = []

    async def create(name, *a, **kw):
        calls.append(name)
        if len(calls) == 2:  # call 1 is the new chat; call 2 is the "browser join"
            blocked.set()
            await gate.wait()
        return await real_create(name, *a, **kw)

    monkeypatch.setattr(factory, "create", create)
    real_get = appmod._RoutineTurnHost.get_or_restore
    joins = []

    async def get_or_restore(self, sid):
        joins.append(asyncio.create_task(appmod._restore_session(sid)))
        await asyncio.wait_for(blocked.wait(), 5)
        return await real_get(self, sid)

    monkeypatch.setattr(appmod._RoutineTurnHost, "get_or_restore", get_or_restore)
    r = await h.api("POST", f"/api/agents/bot/routines/{rt['id']}/run")
    assert r.status_code == 202
    await wait_for(lambda: len(h.llm.calls) > 0)  # the turn is running
    gate.set()  # the join now finishes its agent build mid-turn
    await wait_for(lambda: not runner.registry.is_running(rt["id"]))
    await asyncio.gather(*joins)

    run = await h.last_run(rt["id"])
    assert run["outcome"] == "ok", run
    row = await ChatSessionRepository(await get_connection()).get(run["session_id"])
    roles = [m.role for m in decode_messages(row.messages)]
    assert Role.USER in roles and Role.ASSISTANT in roles


async def test_a_run_whose_message_was_not_saved_is_failed(routine_app, monkeypatch):
    """F-H1-1 safety net: a turn that reports started but left no user message stored."""
    from the_one.interfaces.web import app as appmod

    h = routine_app
    rt = await h.routine()

    async def no_save(session):
        return None

    monkeypatch.setattr(appmod, "_save_session_to_db", no_save)
    await h.run_now(rt["id"])
    run = await h.last_run(rt["id"])
    assert run["outcome"] == "failed" and run["reason"] == runner.NOT_SAVED_REASON


# ── timeouts and drain ─────────────────────────────────────────────────────


async def test_long_run_times_out_as_failed_with_partial(routine_app, monkeypatch):
    h = routine_app
    monkeypatch.setattr(runner, "_TIMEOUT_FLOOR_SECONDS", 0.1)
    monkeypatch.setenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", "0.3")
    h.llm.delay = 5.0
    rt = await h.routine()
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
    rt = await h.routine()
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


# ── M33 F2 L3: the flag snapshot and a cancel during the run ───────────────


async def _saved_run_user(h, rid):
    from the_one.db.codec import decode_messages
    from the_one.llm.base import Role

    run = await h.last_run(rid)
    row = await ChatSessionRepository(await get_connection()).get(run["session_id"])
    return [m for m in decode_messages(row.messages) if m.role == Role.USER][-1]


async def test_run_snapshots_the_flag_onto_its_user_message(routine_app):
    h = routine_app
    flagged = await h.routine(name="Flagged")
    clean = await h.routine(name="Clean")
    conn = await get_connection()
    await conn.execute(
        "UPDATE agent_routines SET untrusted = 1, untrusted_sources = ? WHERE id = ?",
        ('["web_fetch"]', flagged["id"]),
    )
    # an unflagged routine with stale sources must still bind []
    await conn.execute(
        "UPDATE agent_routines SET untrusted = 0, untrusted_sources = ? WHERE id = ?",
        ('["stale"]', clean["id"]),
    )
    await conn.commit()
    await h.run_now(flagged["id"])
    await h.run_now(clean["id"])
    assert (await _saved_run_user(h, flagged["id"])).routine_untrusted_sources == ["web_fetch"]
    assert (await _saved_run_user(h, clean["id"])).routine_untrusted_sources == []


async def test_cancelling_the_running_routine_ends_the_run_quietly(routine_app, caplog):
    import logging

    h = routine_app
    h.llm.delay = 0.5
    rt = await h.routine()
    r = await h.api("POST", f"/api/agents/bot/routines/{rt['id']}/run")
    assert r.status_code == 202
    from the_one.sessions import is_session_busy

    async def started():
        runs = await h.runs(rt["id"])
        return bool(runs) and runs[0]["session_id"] and is_session_busy(runs[0]["session_id"])

    await wait_for(started)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        # the agent (or operator) cancels the routine that is running it
        assert (await h.api("DELETE", f"/api/agents/bot/routines/{rt['id']}")).status_code in (
            200,
            204,
        )
        await wait_for(lambda: not runner.registry.is_running(rt["id"]), timeout=15)
    bad = [x for x in caplog.records if x.levelno >= logging.ERROR]
    assert not bad, [x.getMessage() for x in bad]
    assert (await h.api("GET", f"/api/agents/bot/routines/{rt['id']}")).status_code == 404

"""The approval continuation (M36 F2 L5, DD8): the texts, the turn host calls, the codec,
provider conversion of consecutive user messages and the end-to-end turn."""

# ruff: noqa: F811
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from tests._routine_app import routine_app, wait_for  # noqa: F401
from tests._schema_template import connect_template_db
from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events
from the_one.db.repositories import ChatSessionRepository
from the_one.gleepglorp import settings as gg_settings
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals import continuation
from the_one.gleepglorp.proposals.store import Proposal
from the_one.llm.base import Message, Role
from the_one.sessions import turn_host

ROOT = Path(__file__).resolve().parent.parent / "the_one"


def _proposal(pid=7, kind="agent", action="change", agent="Issue digest", **changes) -> Proposal:
    return Proposal(
        id=pid,
        session_id="s1",
        tool_call_id=None,
        kind=kind,
        action=action,
        agent_name=agent,
        target_id=None,
        target_key="k",
        changes=changes,
        base=None,
        status="pending",
        result=None,
        untrusted=False,
        untrusted_sources=[],
        created_at="2026-11-19T00:00:00Z",
        resolved_at=None,
    )


class FakeHost:
    def __init__(self, session="SESSION", fail_spawn=False) -> None:
        self.session = session
        self.fail_spawn = fail_spawn
        self.spawned: list[tuple] = []
        self.appended: list[tuple] = []

    async def get_or_restore(self, sid):
        return self.session, "ok"

    def spawn_turn(self, session, prompt, turn_info):
        if self.fail_spawn:
            raise RuntimeError("no")
        self.spawned.append((session, prompt, turn_info))

    async def append_marked_message(self, sid, text, marks):
        self.appended.append((sid, text, marks))
        return True


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "c.db")
    yield c
    await c.close()


@pytest.fixture
def host():
    h = FakeHost()
    turn_host.set_turn_host(h)
    yield h
    turn_host.set_turn_host(None)


async def _ready(conn, ready=True):
    await gg_settings.save_settings(
        conn,
        gg_settings.GleepGlorpSettings(
            enabled=True, provider_config_id="p1" if ready else None, model="m"
        ),
    )
    if ready:
        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url, created_at, updated_at) "
            "VALUES ('p1', 'P', 'mock', '', '', '')"
        )
        await conn.commit()


# --- the texts ---------------------------------------------------------------------------


def test_the_texts() -> None:
    assert continuation.approval_text(4, "Changed Prompt on bot") == (
        "Approved proposal 4: Changed Prompt on bot. Continue with the next step, if there is one."
    )
    assert continuation.dismissal_text(4, "change agent bot") == (
        "Dismissed proposal 4 (change agent bot). Do not apply it."
    )
    assert continuation.proposal_title(_proposal()) == "change agent Issue digest"
    r = _proposal(kind="routine", action="create", agent="bot", name="Weekly")
    assert continuation.proposal_title(r) == "create routine Weekly of bot"


# --- on_approved / on_dismissed ----------------------------------------------------------


async def test_approval_spawns_a_turn_with_the_marked_prompt(conn, host) -> None:
    await _ready(conn)
    await continuation.on_approved(conn, _proposal(), "Changed X")
    assert host.appended == []
    ((session, prompt, info),) = host.spawned
    assert session == "SESSION"
    assert prompt == continuation.approval_text(7, "Changed X")
    assert info == {"proposal": {"id": 7, "event": "approved"}}


async def test_an_unready_gleepglorp_appends_with_no_turn(conn, host) -> None:
    await _ready(conn, ready=False)
    await continuation.on_approved(conn, _proposal(), "Changed X")
    assert host.spawned == []
    assert host.appended == [
        (
            "s1",
            continuation.approval_text(7, "Changed X"),
            {"proposal_id": 7, "proposal_event": "approved_no_turn"},
        )
    ]


async def test_a_failed_spawn_appends_instead(conn) -> None:
    await _ready(conn)
    h = FakeHost(fail_spawn=True)
    turn_host.set_turn_host(h)
    try:
        await continuation.on_approved(conn, _proposal(), "S")
    finally:
        turn_host.set_turn_host(None)
    assert h.appended[0][2]["proposal_event"] == "approved_no_turn"


async def test_a_dismissal_appends_with_no_turn(host) -> None:
    await continuation.on_dismissed(_proposal())
    assert host.spawned == []
    assert host.appended == [
        (
            "s1",
            "Dismissed proposal 7 (change agent Issue digest). Do not apply it.",
            {"proposal_id": 7, "proposal_event": "dismissed"},
        )
    ]


async def test_a_missing_chat_is_a_no_op(conn) -> None:
    await _ready(conn)
    h = FakeHost(session=None)
    turn_host.set_turn_host(h)
    try:
        await continuation.on_approved(conn, _proposal(), "S")
    finally:
        turn_host.set_turn_host(None)
    assert h.spawned == [] and h.appended == []


async def test_no_host_is_a_quiet_no_op(conn) -> None:
    assert turn_host.get_turn_host() is None
    await continuation.on_approved(conn, _proposal(), "S")
    await continuation.on_dismissed(_proposal())


async def test_continue_chat_false_never_touches_the_host(tmp_path, host, monkeypatch) -> None:
    """The harness passes ``continue_chat=False``: apply and dismiss call nothing even with a
    host present. (And the default calls it: see the next test.)"""
    calls = []

    async def spy_a(*a, **k):
        calls.append("approved")

    async def spy_d(*a, **k):
        calls.append("dismissed")

    monkeypatch.setattr(continuation, "on_approved", spy_a)
    monkeypatch.setattr(continuation, "on_dismissed", spy_d)
    w = await _apply_world(tmp_path)
    try:
        r = await proposal_apply.apply_proposal(
            w.conn,
            w.deps,
            await w.make(1),
            override=False,
            now=w.now,
            zone=w.zone,
            continue_chat=False,
        )
        assert r.outcome == "applied"
        await proposal_apply.dismiss_proposal(w.conn, await w.make(2), continue_chat=False)
        assert calls == []
        r = await proposal_apply.apply_proposal(
            w.conn, w.deps, await w.make(3), override=False, now=w.now, zone=w.zone
        )
        assert r.outcome == "applied"
        await proposal_apply.dismiss_proposal(w.conn, await w.make(4))
        assert calls == ["approved", "dismissed"]
    finally:
        await w.conn.close()


async def _apply_world(tmp_path):
    from datetime import UTC, datetime

    from tests._gleepglorp_seed import seed
    from the_one.agent.service import AgentWriteDeps
    from the_one.db.repositories import (
        LLMProviderRepository,
        MCPSourceRepository,
        SecretRepository,
        SQLiteAgentStore,
        ToolConfigRepository,
    )
    from the_one.gleepglorp.proposals import shape
    from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, NewProposal

    ns = await seed(tmp_path)
    conn, enc = ns.conn, ns.enc
    ns.deps = AgentWriteDeps(
        store=SQLiteAgentStore(conn, enc),
        mcp_repo=MCPSourceRepository(conn, enc),
        provider_repo=LLMProviderRepository(conn, enc),
        secret_repo=SecretRepository(conn, enc),
        tool_config_repo=ToolConfigRepository(conn, enc),
    )
    ns.now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)

    async def zone():
        return UTC

    ns.zone = zone
    repo = GleepGlorpProposalRepository(conn)

    async def make(i: int) -> int:
        # made on demand: the base is read now, so an apply before the next make is not stale
        n = await shape.normalize(
            "agent",
            "change",
            {"agent": "wide"},
            {"description": f"words {i}"},
            conn=conn,
            now=ns.now,
            zone=UTC,
            enc=enc,
        )
        return await repo.insert(
            NewProposal(
                session_id=f"s{i}",
                kind=n.kind,
                action=n.action,
                agent_name=n.agent_name,
                target_key=n.target_key,
                changes=n.changes,
                target_id=n.target_id,
                base=n.base,
            )
        )

    ns.make = make
    return ns


# --- the seam does not import interfaces --------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "sessions/turn_host.py",
        "gleepglorp/proposals/continuation.py",
        "gleepglorp/proposals/apply.py",
        "gleepglorp/kinds/__init__.py",
        "gleepglorp/kinds/base.py",
        "gleepglorp/kinds/deps.py",
        "gleepglorp/kinds/errors.py",
        "gleepglorp/kinds/agent.py",
        "gleepglorp/kinds/rule.py",
        "gleepglorp/kinds/routine.py",
        "gleepglorp/kinds/mcp_server.py",
        "gleepglorp/kinds/provider.py",
        "gleepglorp/kinds/knowledge_base.py",
        "gleepglorp/kinds/secret.py",
        "gleepglorp/kinds/tool_config.py",
        "gleepglorp/kinds/app_settings.py",
        "llm/provider_service.py",
        "knowledge/service.py",
        "secret_store/service.py",
        "tools/config_service.py",
        "app_settings_service.py",
        "routines/runner.py",
    ],
)
def test_the_seam_modules_do_not_import_interfaces(path) -> None:
    tree = ast.parse((ROOT / path).read_text())
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n.startswith("the_one.interfaces") for n in names), (path, names)


def test_the_runner_keeps_its_old_names() -> None:
    from the_one.routines import runner

    assert runner.TurnHost is turn_host.TurnHost
    assert runner.set_turn_host is turn_host.set_turn_host


# --- codec ------------------------------------------------------------------------------


def test_codec_round_trips_the_marks_and_adds_no_keys_when_absent() -> None:
    msg = Message.user("Approved proposal 3: x.")
    msg.proposal_id = 3
    msg.proposal_event = "approved_no_turn"
    plain = Message.user("hello")
    encoded = encode_messages([msg, plain])
    back = decode_messages(encoded)
    assert (back[0].proposal_id, back[0].proposal_event) == (3, "approved_no_turn")
    assert (back[1].proposal_id, back[1].proposal_event) == (None, None)
    assert "proposal" not in encode_messages([plain])
    events = messages_to_ui_events(back)
    assert events[0]["proposal_id"] == 3 and events[0]["proposal_event"] == "approved_no_turn"
    assert "proposal_id" not in events[1] and "proposal_event" not in events[1]


def test_codec_drops_an_unknown_event_value() -> None:
    from the_one.db.codec import message_from_dict, message_to_dict

    d = message_to_dict(Message.user("x"))
    d["proposal_id"] = 1
    d["proposal_event"] = "bogus"
    m = message_from_dict(d)
    assert m.proposal_event is None


# --- provider conversion of consecutive user messages (AC7; no merge code was needed) ----


def _two_users() -> list[Message]:
    a, b = Message.user("Dismissed proposal 1 (x). Do not apply it."), Message.user("next")
    a.proposal_id, a.proposal_event = 1, "dismissed"
    return [a, b]


def test_anthropic_builds_two_user_entries() -> None:
    from the_one.llm.anthropic_provider import AnthropicProvider

    p = AnthropicProvider(model="claude-sonnet-4-6", api_key="x")
    msgs = p._build_kwargs(_two_users(), None, 0.0, 100)["messages"]
    assert [m["role"] for m in msgs] == ["user", "user"]
    assert "proposal_id" not in str(msgs)
    assert "Do not apply it." in str(msgs[0]) and "next" in str(msgs[1])


@pytest.mark.parametrize("kind", ["openai", "compatible", "openrouter"])
def test_openai_family_builds_two_user_entries(kind) -> None:
    from the_one.llm.openai_provider import OpenAIProvider
    from the_one.llm.openrouter_provider import OpenRouterProvider

    p = (
        OpenRouterProvider(model="m", api_key="x")
        if kind == "openrouter"
        else OpenAIProvider(
            model="m",
            api_key="x",
            base_url="http://localhost:9/v1" if kind == "compatible" else None,
        )
    )
    out = [p._to_api_message(m) for m in _two_users()]
    assert [m["role"] for m in out] == ["user", "user"]
    assert "Do not apply it." in str(out[0]["content"]) and "next" in str(out[1]["content"])
    assert "proposal_id" not in str(out) and "proposal_event" not in str(out)


def test_ollama_builds_two_user_entries() -> None:
    from the_one.llm.ollama_provider import OllamaProvider

    p = OllamaProvider(model="gemma3:4b", base_url="http://localhost:11434/v1")
    for build in (p._to_api_message, p._to_native_message):
        out = [build(m) for m in _two_users()]
        assert [m["role"] for m in out] == ["user", "user"]
        assert "proposal_id" not in str(out) and "proposal_event" not in str(out)


# --- end to end on the real app -----------------------------------------------------------


async def _gleepglorp_chat(h):
    from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, NewProposal
    from the_one.interfaces.web import app as appmod

    r = await h.api("GET", "/api/providers")
    pid = r.json()[0]["id"]
    r = await h.api(
        "PUT",
        "/api/gleepglorp",
        json={
            "enabled": True,
            "provider_config_id": pid,
            "model": "mock-default",
            "web_access": False,
            "memory": False,
            "retention_days": 30,
        },
    )
    assert r.status_code == 200, r.text
    session = await appmod._create_session("GleepGlorp", "web")
    conn = await appmod.get_connection()
    repo = GleepGlorpProposalRepository(conn)
    prop = await repo.insert(
        NewProposal(
            session_id=session.id,
            kind="agent",
            action="change",
            agent_name="bot",
            target_key="bot",
            changes={"description": "new words"},
            base={"description": ""},
        )
    )
    return session, prop, prop  # (one open proposal per chat; dismissal tests use the same)


async def _stored(sid):
    from the_one.db.connection import get_connection

    row = await ChatSessionRepository(await get_connection()).get(sid)
    return decode_messages(row.messages)


async def test_an_approval_runs_a_marked_turn_and_the_reply_follows(routine_app) -> None:
    from the_one.sessions import is_session_busy

    h = routine_app
    session, prop, _ = await _gleepglorp_chat(h)
    r = await h.api("POST", f"/api/gleepglorp/proposals/{prop}/approve")
    assert r.status_code == 200, r.text
    await wait_for(lambda: not is_session_busy(session.id))
    msgs = [m for m in await _stored(session.id) if m.role != Role.SYSTEM]
    user = msgs[0]
    assert user.role == Role.USER
    assert (user.proposal_id, user.proposal_event) == (prop, "approved")
    assert user.content.startswith(f"Approved proposal {prop}: ")
    assert msgs[-1].role == Role.ASSISTANT and msgs[-1].content == "routine reply"
    # the history replay carries the marks
    ev = [e for e in session.history if e["type"] == "user"][0]
    assert ev["proposal_id"] == prop and ev["proposal_event"] == "approved"


async def test_stop_during_the_approval_turn_keeps_the_marks(routine_app) -> None:
    from the_one.interfaces.web import app as appmod
    from the_one.sessions import is_session_busy

    h = routine_app
    h.llm.delay = 5
    session, prop, _ = await _gleepglorp_chat(h)
    r = await h.api("POST", f"/api/gleepglorp/proposals/{prop}/approve")
    assert r.status_code == 200
    await wait_for(lambda: bool(h.llm.calls))
    for t in list(appmod._session_inflight.get(session.id, ())):
        t.cancel()
    await wait_for(lambda: not is_session_busy(session.id))
    await asyncio.sleep(0.1)
    user = [m for m in await _stored(session.id) if m.role == Role.USER][0]
    assert (user.proposal_id, user.proposal_event) == (prop, "approved")


async def test_a_dismissal_appends_without_a_turn(routine_app) -> None:
    from the_one.interfaces.web import app as appmod

    h = routine_app
    session, _, prop2 = await _gleepglorp_chat(h)
    r = await h.api("POST", f"/api/gleepglorp/proposals/{prop2}/dismiss")
    assert r.status_code == 200, r.text
    msgs = [m for m in await _stored(session.id) if m.role != Role.SYSTEM]
    assert len(msgs) == 1 and h.llm.calls == []
    assert (msgs[0].proposal_id, msgs[0].proposal_event) == (prop2, "dismissed")
    assert msgs[0].content.startswith(f"Dismissed proposal {prop2} (")
    assert appmod._sessions[session.id].history[-1]["proposal_event"] == "dismissed"


async def test_a_dismissal_on_a_reaped_session_still_appends(routine_app) -> None:
    from the_one.interfaces.web import app as appmod

    h = routine_app
    session, _, prop2 = await _gleepglorp_chat(h)
    appmod._sessions.pop(session.id)
    r = await h.api("POST", f"/api/gleepglorp/proposals/{prop2}/dismiss")
    assert r.status_code == 200
    msgs = [m for m in await _stored(session.id) if m.role != Role.SYSTEM]
    assert [m.proposal_event for m in msgs] == ["dismissed"]


async def test_an_approval_on_a_reaped_session_still_continues(routine_app) -> None:
    from the_one.interfaces.web import app as appmod
    from the_one.sessions import is_session_busy

    h = routine_app
    session, prop, _ = await _gleepglorp_chat(h)
    appmod._sessions.pop(session.id)
    r = await h.api("POST", f"/api/gleepglorp/proposals/{prop}/approve")
    assert r.status_code == 200
    await wait_for(lambda: not is_session_busy(session.id))
    users = [m for m in await _stored(session.id) if m.role == Role.USER]
    assert users[0].proposal_event == "approved"


async def test_the_race_stores_the_message_and_sends_no_system_frame(routine_app) -> None:
    """Settings flip to unready between the route's check and the turn: the turn stores the
    marked message (no system frame, no error) instead of dropping it."""
    from the_one.interfaces.web import app as appmod

    h = routine_app
    session, prop, _ = await _gleepglorp_chat(h)
    conn = await appmod.get_connection()
    cur = await gg_settings.load_settings(conn)
    await gg_settings.save_settings(conn, cur.model_copy(update={"enabled": False}))
    frames = []

    async def spy(sess, payload, **kw):
        frames.append(payload)

    appmod_send = appmod._send_to_session
    appmod._send_to_session = spy
    try:
        info = {"proposal": {"id": prop, "event": "approved"}}
        await appmod._locked_message_processing(
            session, "Approved proposal.", "proposal", None, info
        )
    finally:
        appmod._send_to_session = appmod_send
    assert "error" not in info
    assert not [f for f in frames if f.get("type") == "system"]
    users = [m for m in await _stored(session.id) if m.role == Role.USER]
    assert [(m.proposal_id, m.proposal_event) for m in users] == [(prop, "approved_no_turn")]
    assert h.llm.calls == []


async def test_an_ordinary_message_while_unready_is_still_refused(routine_app) -> None:
    from the_one.interfaces.web import app as appmod

    h = routine_app
    session, _, _ = await _gleepglorp_chat(h)
    conn = await appmod.get_connection()
    cur = await gg_settings.load_settings(conn)
    await gg_settings.save_settings(conn, cur.model_copy(update={"enabled": False}))
    frames = []

    async def spy(sess, payload, **kw):
        frames.append(payload)

    keep = appmod._send_to_session
    appmod._send_to_session = spy
    try:
        info: dict = {}
        await appmod._locked_message_processing(session, "hi", "web", None, info)
    finally:
        appmod._send_to_session = keep
    assert info["error"] and [f for f in frames if f.get("type") == "system"]

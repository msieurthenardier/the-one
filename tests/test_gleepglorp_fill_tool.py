"""``fill_form`` (M36 F3 L5, DD6): the page gate, the refusals, what it records and sends, the
taint rule, and that it writes nothing but its own table."""

# ruff: noqa: F811
from __future__ import annotations

import json
from pathlib import Path

import pytest
from _routine_tools_env import asst, call, done, make_agent, run_turn

from tests._gleepglorp_seed import seed
from tests._routine_app import routine_app, wait_for  # noqa: F401
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.taint import TRUSTED_TOOL_NAMES
from the_one.gleepglorp import kinds
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository
from the_one.gleepglorp.fill.tool import (
    FILL_FORM_TOOL_NAME,
    NEEDS_PAGE,
    NO_NOTES,
    FillFormTool,
)
from the_one.tools.base import Tool

ROOT = Path(__file__).resolve().parent.parent
PAGE = {"line": "Agents › New agent", "descriptor": {"destination": "agents", "create": True}}
RESULT = (
    "Fill {id} is on the operator's screen as unsaved edits in the agent editor. "
    "Nothing is saved until they click Save."
)


@pytest.fixture
async def world(tmp_path, monkeypatch):
    ns = await seed(tmp_path)

    async def _conn():
        return ns.conn

    from the_one.config import settings

    monkeypatch.setattr("the_one.db.connection.get_connection", _conn)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield ns
    await ns.conn.close()


@pytest.fixture
def tool() -> FillFormTool:
    return FillFormTool(agent_name="GleepGlorp")


async def fill(tool, session="s1", page=PAGE, **kw) -> str:
    token = current_turn.set(TurnContext(session_id=session, page=page))
    try:
        return await tool.execute(**kw)
    finally:
        current_turn.reset(token)


def create(**changes) -> dict:
    return {"kind": "agent", "action": "create", "changes": {"name": "Fresh", **changes}}


async def stored(conn, session="s1"):
    return await GleepGlorpFillRepository(conn).list_for_session(session)


# --- the tool's shape --------------------------------------------------------------------


def test_shape_of_the_tool() -> None:
    t = FillFormTool()
    schema = t.to_schema()
    assert schema["name"] == "fill_form" == FILL_FORM_TOOL_NAME
    props = schema["parameters"]["properties"]
    assert props["kind"]["enum"] == ["agent", "mcp_server", "provider", "knowledge_base", "secret"]
    assert props["action"]["enum"] == ["create", "change"]
    assert set(props) == {"kind", "action", "agent", "target", "changes"}
    assert isinstance(t, Tool)
    assert "route" not in t.description.lower() and "/api" not in t.description


def test_the_description_character_budget() -> None:
    assert len(FillFormTool.description) <= 440
    for needed in ("MCP server", "provider", "target", "type", '""'):
        assert needed in FillFormTool.description


def test_the_description_token_budget() -> None:
    tiktoken = pytest.importorskip("tiktoken")
    import os

    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(ROOT / "evals" / ".cache" / "tiktoken"))
    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception:  # noqa: BLE001 - no cached encoding on this host: not a failure
        pytest.skip("o200k_base is not cached")
    assert len(enc.encode(FillFormTool.description)) <= 90


def test_it_is_trusted_in_the_taint_rule() -> None:
    assert FILL_FORM_TOOL_NAME in TRUSTED_TOOL_NAMES
    assert "read_app_config" not in TRUSTED_TOOL_NAMES


# --- the gate (AC3) ----------------------------------------------------------------------


async def test_no_turn_context_is_refused(world, tool) -> None:
    token = current_turn.set(None)
    try:
        out = await tool.execute(**create())
    finally:
        current_turn.reset(token)
    assert out in ("Filling needs a chat.",)
    assert await stored(world.conn) == []


async def test_a_turn_without_a_page_is_refused_and_records_nothing(
    world, tool, monkeypatch
) -> None:
    sent = []

    async def capture(session_id, payload, **_kw):
        sent.append(payload)

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", capture)
    assert await fill(tool, page=None, **create()) == NEEDS_PAGE
    assert await stored(world.conn) == [] and sent == []
    assert "propose_change" in NEEDS_PAGE


async def test_an_approval_continuation_through_the_real_seam_is_refused(routine_app) -> None:
    """The proposal-continuation turn carries no page: a scripted GleepGlorp-style call to
    fill_form gets NEEDS_PAGE and no row, through the web app's real turn host."""
    from the_one.db.connection import get_connection
    from the_one.sessions import is_session_busy
    from the_one.sessions.turn_host import get_turn_host

    h = routine_app
    from the_one.interfaces.web import app as appmod

    session = await appmod._create_session("bot", "web")
    t = FillFormTool(agent_name="bot")
    session.agent.tools.register(t)
    t.bind_agent(session.agent)
    from the_one.llm.base import Message, ToolCall

    h.llm.script = [
        Message.assistant(
            "",
            tool_calls=[
                ToolCall(id="c1", name="fill_form", arguments=create()),
            ],
        ),
        Message.assistant("done"),
    ]
    host = get_turn_host()
    task = host.spawn_turn(session, "Approved.", {"proposal": {"id": 9, "event": "approved"}})
    await wait_for(lambda: task.done() and not is_session_busy(session.id))
    conn = await get_connection()
    assert await stored(conn, session.id) == []
    results = [m.content for m in session.agent.messages if m.role.value == "tool"]
    assert results == [NEEDS_PAGE]


async def test_a_drawer_continue_turn_with_a_page_may_fill(world, tool) -> None:
    out = await fill(tool, **create())
    assert out == RESULT.format(id=1)


# --- refusals in a page turn (AC3) -------------------------------------------------------


async def test_notes_enabled_is_refused(world, tool) -> None:
    assert await fill(tool, **create(notes_enabled=True)) == NO_NOTES
    assert await stored(world.conn) == []


async def test_shape_refusals_record_nothing(world, tool) -> None:
    cases = [
        (create(bogus_field=1), "bogus_field"),
        ({"kind": "agent", "action": "create", "changes": {"name": "wide"}}, "already exists"),
        ({"kind": "agent", "action": "create", "changes": {"name": "GleepGlorp"}}, ""),
        ({"kind": "agent", "action": "create", "changes": {"name": "default"}}, ""),
        (
            {"kind": "agent", "action": "change", "agent": "ghost", "changes": {"model": "m"}},
            "No agent named ghost.",
        ),
        ({"kind": "agent", "action": "change", "changes": {"description": "d"}}, "Say which"),
        ({"kind": "rule", "action": "create", "agent": "plain", "changes": {}}, "agent"),
    ]
    for args, needle in cases:
        out = await fill(tool, **args)
        assert needle in out and not out.startswith("Fill "), (args, out)
    assert await stored(world.conn) == []


async def test_a_secret_bearing_value_is_refused(world, tool) -> None:
    from tests._gleepglorp_seed import SEEDS

    secret = SEEDS["provider_api_key"]
    out = await fill(tool, **create(description=f"key is {secret}"))
    assert not out.startswith("Fill ") and secret not in out
    assert await stored(world.conn) == []


async def test_it_never_raises_into_the_loop(world, tool, monkeypatch) -> None:
    async def boom(*_a, **_k):
        raise RuntimeError("explodes")

    monkeypatch.setattr(kinds, "normalize", boom)
    assert await fill(tool, **create()) == "Could not fill the form right now."


# --- what it records and sends (AC4) -----------------------------------------------------


async def test_a_change_records_its_base_and_pushes_the_view(world, tool, monkeypatch) -> None:
    sent = []

    async def capture(session_id, payload, **_kw):
        sent.append((session_id, payload))

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", capture)
    out = await fill(
        tool,
        session="chat9",
        kind="agent",
        action="change",
        agent="wide",
        changes={"description": "Fresh words", "provider": "OpenAI main", "model": "m2"},
    )
    assert out == RESULT.format(id=1)
    [f] = await stored(world.conn, "chat9")
    assert (f.kind, f.action, f.status, f.agent_name) == ("agent", "change", "sent", "wide")
    assert f.target_key == "agent:wide" and f.tool_call_id is None
    assert f.changes["description"] == "Fresh words" and f.changes["llm_model"] == "m2"
    assert set(f.base) == set(f.changes)
    [(sid, payload)] = sent
    assert sid == "chat9" and payload["type"] == "fill_requested"
    view = payload["fill"]
    assert view["id"] == 1 and view["status"] == "sent" and view["values"] == f.changes
    assert "claim_token" not in view
    json.dumps(payload)


async def test_a_create_records_no_base(world, tool) -> None:
    await fill(tool, **create(description="d"))
    [f] = await stored(world.conn)
    assert f.action == "create" and f.base is None and f.target_key == "agent:Fresh"
    assert f.changes["name"] == "Fresh"


async def test_a_second_fill_replaces_the_first_and_pushes_both(world, tool, monkeypatch) -> None:
    sent = []

    async def capture(session_id, payload, **_kw):
        sent.append(payload)

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", capture)
    await fill(tool, **create(description="one"))
    sent.clear()
    await fill(tool, **create(description="two"))
    assert [(p["type"], p["fill"]["id"], p["fill"]["status"]) for p in sent] == [
        ("fill_changed", 1, "replaced"),
        ("fill_requested", 2, "sent"),
    ]


# --- it writes nothing but its own table (AC5) -------------------------------------------


async def dump(conn) -> dict[str, list]:
    async with conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cur:
        tables = sorted(r[0] for r in await cur.fetchall() if not r[0].startswith("sqlite_"))
    out = {}
    for t in tables:
        if t == "gleepglorp_fills":
            continue
        async with conn.execute(f'SELECT * FROM "{t}"') as cur:  # noqa: S608
            out[t] = sorted((tuple(r) for r in await cur.fetchall()), key=repr)
    return out


async def test_a_fill_changes_no_table_but_its_own(world, tool) -> None:
    before = await dump(world.conn)
    calls = [
        create(description="d"),
        {"kind": "agent", "action": "change", "agent": "wide", "changes": {"description": "new"}},
        {
            "kind": "agent",
            "action": "change",
            "agent": "plain",
            "changes": {"enabled_tools": [], "rich_visuals": False},
        },
    ]
    for i, args in enumerate(calls):
        out = await fill(tool, session=f"w{i}", **args)
        assert out.startswith("Fill "), (args, out)
    assert await dump(world.conn) == before
    async with world.conn.execute("SELECT COUNT(*) FROM gleepglorp_fills") as cur:
        assert (await cur.fetchone())[0] == len(calls)


# --- the taint rule (AC4) ----------------------------------------------------------------


class _Stub(Tool):
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.description = name

    async def execute(self, **kwargs) -> str:
        return "text"


def f_call(cid: str, name: str = "Fresh") -> object:
    return asst(call(cid, "fill_form", kind="agent", action="create", changes={"name": name}))


async def page_turn(agent, session_id):
    return await run_turn(
        agent, session_id=session_id, ctx=TurnContext(session_id=session_id, page=PAGE)
    )


async def test_a_fill_after_read_app_config_is_flagged(world) -> None:
    tool = FillFormTool(agent_name="GleepGlorp")
    agent = await make_agent(
        [asst(call("r1", "read_app_config")), f_call("c1"), done()], tool, _Stub("read_app_config")
    )
    tool.bind_agent(agent)
    await page_turn(agent, "chat-r")
    [row] = await stored(world.conn, "chat-r")
    assert row.untrusted is True and row.untrusted_sources == ["read_app_config"]


async def test_one_fill_does_not_flag_the_next(world) -> None:
    tool = FillFormTool(agent_name="GleepGlorp")
    agent = await make_agent([f_call("c1", "One"), f_call("c2", "Two"), done()], tool)
    tool.bind_agent(agent)
    await page_turn(agent, "chat-t")
    rows = await stored(world.conn, "chat-t")
    assert [(r.untrusted, r.untrusted_sources) for r in rows] == [(False, []), (False, [])]


async def test_a_note_after_a_fill_is_not_flagged(world) -> None:
    tool = FillFormTool(agent_name="GleepGlorp")
    note = asst(call("n1", "save_note", text="A plain note."))
    agent = await make_agent([f_call("c1"), note, done()], tool)
    tool.bind_agent(agent)
    await page_turn(agent, "chat-n")
    async with world.conn.execute("SELECT untrusted FROM agent_notes") as cur:
        flags = [r[0] for r in await cur.fetchall()]
    assert flags and not any(flags)

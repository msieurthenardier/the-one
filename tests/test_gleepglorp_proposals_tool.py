"""``propose_change`` (M36 F2 L2, DD5): the tool records a proposal and changes nothing else."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _routine_tools_env import asst, call, done, make_agent, run_turn

from tests._gleepglorp_seed import seed
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.taint import TRUSTED_TOOL_NAMES
from the_one.gleepglorp.proposals import shape
from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository
from the_one.gleepglorp.proposals.tool import PROPOSE_CHANGE_TOOL_NAME, ProposeChangeTool
from the_one.tools.base import Tool

ROOT = Path(__file__).resolve().parent.parent


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
def tool() -> ProposeChangeTool:
    return ProposeChangeTool(agent_name="GleepGlorp")


async def propose(tool, session="s1", **kw) -> str:
    token = current_turn.set(TurnContext(session_id=session))
    try:
        return await tool.execute(**kw)
    finally:
        current_turn.reset(token)


def rule_new(text="Be brief.", agent="plain") -> dict:
    return {"kind": "rule", "action": "create", "agent": agent, "changes": {"text": text}}


async def stored(conn, session="s1"):
    return await GleepGlorpProposalRepository(conn).list_for_session(session)


# --- the schema ---------------------------------------------------------------------------


def test_shape_of_the_tool() -> None:
    t = ProposeChangeTool()
    schema = t.to_schema()
    assert schema["name"] == "propose_change" == PROPOSE_CHANGE_TOOL_NAME
    props = schema["parameters"]["properties"]
    assert props["kind"]["enum"] == ["agent", "rule", "routine"]
    assert props["action"]["enum"] == ["create", "change"]
    assert set(props) == {"kind", "action", "agent", "rule", "routine", "changes"}
    assert schema["parameters"]["required"] == ["kind", "action", "changes"]
    assert isinstance(t, Tool)


def test_the_description_stays_thin() -> None:
    text = ProposeChangeTool.description
    assert len(text) <= 520, len(text)
    # Every field name of every kind is named once, in one short line each.
    for specs in shape.SPECS.values():
        for f in specs:
            assert f.name.split("_")[0] in text, f.name


def test_the_description_token_budget() -> None:
    tiktoken = pytest.importorskip("tiktoken")
    import os

    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(ROOT / "evals" / ".cache" / "tiktoken"))
    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception:  # noqa: BLE001 - no cached encoding on this host: not a failure
        pytest.skip("o200k_base is not cached")
    assert len(enc.encode(ProposeChangeTool.description)) <= 120


def test_it_is_trusted_in_the_taint_rule() -> None:
    assert PROPOSE_CHANGE_TOOL_NAME in TRUSTED_TOOL_NAMES
    assert "read_app_config" not in TRUSTED_TOOL_NAMES


# --- calls ----------------------------------------------------------------------------------


async def test_it_needs_a_chat(world, tool) -> None:
    assert await tool.execute(**rule_new()) == "Proposals need a chat."
    token = current_turn.set(TurnContext(session_id=None))
    try:
        assert await tool.execute(**rule_new()) == "Proposals need a chat."
    finally:
        current_turn.reset(token)


async def test_a_call_records_a_pending_proposal_and_says_so(world, tool) -> None:
    out = await propose(tool, **rule_new())
    assert out == "Proposal 1 is waiting for the operator. Nothing has changed yet."
    [p] = await stored(world.conn)
    assert (p.kind, p.action, p.status, p.agent_name) == ("rule", "create", "pending", "plain")
    assert p.changes == {"text": "Be brief."} and p.base is None
    assert p.target_key == "rule:plain:new" and p.session_id == "s1"
    # No agent has bound the tool here, so it fails closed: flagged "unknown position".
    assert p.untrusted is True and p.untrusted_sources == ["unknown position"]


async def test_refusals_are_plain_text_never_exceptions(world, tool) -> None:
    out = await propose(tool, kind="agent", action="change", agent="ghost", changes={"model": "m"})
    assert out == "No agent named ghost."
    assert await stored(world.conn) == []
    assert "Unknown kind" in await propose(tool, kind="chat", action="create", changes={})
    assert "Unknown kind" in await propose(tool)
    assert "object" in await propose(tool, kind="rule", action="create", agent="plain", changes="x")


async def test_one_open_proposal_per_chat(world, tool) -> None:
    first = await propose(tool, **rule_new())
    assert first.startswith("Proposal 1 ")
    other = await propose(
        tool, kind="agent", action="change", agent="plain", changes={"description": "d"}
    )
    assert other == (
        "Proposal 1 is still waiting for the operator. Wait for their answer before the next step."
    )
    # The same target replaces it: the new proposal is 2 and 1 is withdrawn.
    again = await propose(tool, **rule_new("Be briefer."))
    assert again.startswith("Proposal 2 ")
    statuses = [(p.id, p.status) for p in await stored(world.conn)]
    assert statuses == [(1, "withdrawn"), (2, "pending")]
    # Another chat is unaffected.
    assert (await propose(tool, session="s2", **rule_new())).startswith("Proposal 3 ")


async def test_a_change_records_its_base(world, tool) -> None:
    out = await propose(
        tool, kind="rule", action="change", agent="wide", rule=1, changes={"enabled": False}
    )
    assert out.startswith("Proposal 1 ")
    [p] = await stored(world.conn)
    assert p.base == {"enabled": True} and p.changes == {"enabled": False} and p.target_id


async def test_it_never_raises_into_the_loop(world, tool, monkeypatch) -> None:
    async def boom(*_a, **_k):
        raise RuntimeError("explodes")

    monkeypatch.setattr(shape, "normalize", boom)
    assert await propose(tool, **rule_new()) == "Could not record that proposal right now."


async def test_the_frame_is_pushed_on_create(world, tool, monkeypatch) -> None:
    sent = []

    async def capture(session_id, payload, **_kw):
        sent.append((session_id, payload))

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", capture)
    await propose(tool, session="chat9", **rule_new())
    [(sid, payload)] = sent
    assert sid == "chat9" and payload["type"] == "proposal_changed"
    assert payload["proposal"]["id"] == 1 and payload["proposal"]["status"] == "pending"
    json.dumps(payload)  # serialisable as sent
    # A refusal pushes nothing.
    sent.clear()
    await propose(
        tool, session="chat9", kind="agent", action="change", agent="ghost", changes={"model": "m"}
    )
    assert sent == []


# --- it writes nothing but its own table ------------------------------------------------------


async def dump(conn) -> dict[str, list]:
    async with conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cur:
        tables = sorted(r[0] for r in await cur.fetchall() if not r[0].startswith("sqlite_"))
    out = {}
    for t in tables:
        if t == "gleepglorp_proposals":
            continue
        async with conn.execute(f'SELECT * FROM "{t}"') as cur:  # noqa: S608
            out[t] = sorted((tuple(r) for r in await cur.fetchall()), key=repr)
    return out


CALLS = [
    {"kind": "agent", "action": "create", "changes": {"name": "Fresh", "description": "d"}},
    {"kind": "agent", "action": "change", "agent": "wide", "changes": {"description": "new"}},
    {"kind": "rule", "action": "create", "agent": "plain", "changes": {"text": "New rule"}},
    {
        "kind": "rule",
        "action": "change",
        "agent": "wide",
        "rule": 1,
        "changes": {"text": "Changed rule"},
    },
    {
        "kind": "routine",
        "action": "create",
        "agent": "plain",
        "changes": {
            "name": "Soon",
            "prompt": "p",
            "schedule": {"start": {"in": {"amount": 2, "unit": "hours"}}},
        },
    },
    {
        "kind": "routine",
        "action": "change",
        "agent": "wide",
        "routine": "Morning digest",
        "changes": {"enabled": False},
    },
]


async def test_a_proposal_changes_no_table_but_its_own(world, tool) -> None:
    before = await dump(world.conn)
    for i, args in enumerate(CALLS):
        out = await propose(tool, session=f"w{i}", **args)
        assert "is waiting for the operator" in out, (args, out)
    assert await dump(world.conn) == before
    async with world.conn.execute("SELECT COUNT(*) FROM gleepglorp_proposals") as cur:
        assert (await cur.fetchone())[0] == len(CALLS)


# --- the taint rule ---------------------------------------------------------------------------


class _Stub(Tool):
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.description = name

    async def execute(self, **kwargs) -> str:
        return "text"


def p(cid: str, text: str) -> object:
    return asst(
        call(
            cid,
            "propose_change",
            kind="rule",
            action="create",
            agent="plain",
            changes={"text": text},
        )
    )


async def test_one_proposal_does_not_flag_the_next(world) -> None:
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    agent = await make_agent([p("c1", "One."), p("c2", "Two."), done()], tool)
    tool.bind_agent(agent)
    await run_turn(agent, session_id="chat-t")
    one, two = [
        (x.id, x.untrusted, x.untrusted_sources) for x in await stored(world.conn, "chat-t")
    ]
    assert one[1] is False and two[1] is False and two[2] == []


async def test_a_proposal_after_read_app_config_is_flagged(world) -> None:
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    agent = await make_agent(
        [asst(call("r1", "read_app_config")), p("c1", "After a read."), done()],
        tool,
        _Stub("read_app_config"),
    )
    tool.bind_agent(agent)
    await run_turn(agent, session_id="chat-r")
    [row] = await stored(world.conn, "chat-r")
    assert row.untrusted is True and row.untrusted_sources == ["read_app_config"]

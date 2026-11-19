"""GleepGlorp's own notes: repository, tools, prompt layer and routes (M36 F1 L06, DD4)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from conftest import FakeLLM
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.db._notes import (
    NOTES_HEADING,
    NOTES_HEADING_TOOL_FREE,
    NoteDuplicateError,
    NoteLimitError,
    NotesDisabledError,
    render_notes_block,
)
from the_one.db.repositories import AgentNoteRepository
from the_one.gleepglorp import GleepGlorpSettings, save_settings
from the_one.gleepglorp.notes import (
    GLEEPGLORP_NOTES_HEADING,
    GLEEPGLORP_NOTES_HEADING_TOOL_FREE,
    GLEEPGLORP_SAVE_DESCRIPTION,
    GleepGlorpNoteRepository,
)
from the_one.gleepglorp.prompt import build_prompts, compose
from the_one.llm.base import Message, Role, ToolCall
from the_one.notes.tool_provider import NotesToolProvider
from the_one.tools.base import Tool, ToolRegistry

GG = "GleepGlorp"
_ORIGIN: dict[str, Any] = {
    "origin_kind": "other",
    "origin_session_id": None,
    "origin_label": None,
    "origin_platform": None,
    "origin_peer_id": None,
    "origin_peer_name": None,
}


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "test.db")
    await save_settings(c, GleepGlorpSettings(memory=True))
    with patch("the_one.db.connection.get_connection", return_value=c):
        yield c
    await c.close()


async def _create(repo, text, *, untrusted=False, sources=(), **origin):
    return await repo.create(
        GG, text, untrusted=untrusted, sources=list(sources), **{**_ORIGIN, **origin}
    )


async def _counter(conn) -> int:
    async with conn.execute("SELECT next_number FROM gleepglorp_notes_counter") as cur:
        return (await cur.fetchone())[0]


# ── repository ────────────────────────────────────────────────────────────


async def test_create_dedups_and_numbers_only_go_up(conn) -> None:
    repo = GleepGlorpNoteRepository(conn)
    a, created = await _create(repo, "Uses Ollama on port 11434")
    assert (a.number, created, a.agent_name) == (1, True, GG)
    dup, created = await _create(repo, "uses ollama on port 11434.")
    assert (dup.id, created) == (a.id, False)
    assert await _counter(conn) == 2  # a duplicate does not consume a number
    b, _ = await _create(repo, "Prefers short answers")
    assert b.number == 2
    # A delete and a clear never lower the counter, so a number is never reused.
    await repo.delete(GG, a.id)
    assert await _counter(conn) == 3
    await repo.clear()
    assert await _counter(conn) == 3
    c, _ = await _create(repo, "Third note")
    assert c.number == 3


async def test_limits(conn) -> None:
    repo = GleepGlorpNoteRepository(conn)
    with pytest.raises(NoteLimitError):
        await _create(repo, "x" * 401)
    with pytest.raises(NoteLimitError):
        await _create(repo, "   ")
    for i in range(10):
        await _create(repo, f"{i} " + "y" * 396)
    with pytest.raises(NoteLimitError, match="Notes are full"):
        await _create(repo, "one more " + "z" * 100)


async def test_memory_off_refuses_every_agent_write_but_not_the_operator(conn) -> None:
    repo = GleepGlorpNoteRepository(conn)
    n, _ = await _create(repo, "kept")
    await save_settings(conn, GleepGlorpSettings(memory=False))
    with pytest.raises(NotesDisabledError):
        await _create(repo, "new")
    with pytest.raises(NotesDisabledError):
        await repo.update_by_agent(GG, n.number, "changed", untrusted=False, sources=[])
    with pytest.raises(NotesDisabledError):
        await repo.forget_by_agent(GG, n.number)
    # The operator's delete and clear still work, and the notes were kept until then.
    assert [x.text for x in await repo.list_for_agent()] == ["kept"]
    assert await repo.list_if_enabled() is None
    await repo.delete(GG, n.id)
    assert await repo.list_for_agent() == []


async def test_update_flags_merge_and_duplicate_refusal(conn) -> None:
    repo = GleepGlorpNoteRepository(conn)
    a, _ = await _create(repo, "alpha")
    b, _ = await _create(repo, "beta", untrusted=True, sources=["fetch_url"])
    assert b.untrusted and b.untrusted_sources == ["fetch_url"]
    updated, changed = await repo.update_by_agent(
        GG, a.number, "alpha two", untrusted=True, sources=["read_app_config"]
    )
    assert changed and updated.untrusted and updated.updated_by == "agent"
    assert updated.untrusted_sources == ["read_app_config"]
    same, changed = await repo.update_by_agent(
        GG, a.number, "alpha two", untrusted=False, sources=[]
    )
    assert not changed and same.untrusted
    with pytest.raises(NoteDuplicateError):
        await repo.update_by_agent(GG, a.number, "Beta", untrusted=False, sources=[])
    with pytest.raises(KeyError):
        await repo.update_by_agent(GG, 99, "x", untrusted=False, sources=[])


async def test_a_note_whose_chat_is_gone_reads_chat_deleted_and_a_live_chat_its_title(
    conn,
) -> None:
    await conn.execute(
        "INSERT INTO chat_sessions (id, agent_name, title, messages, created_at, updated_at) "
        "VALUES ('s1', 'GleepGlorp', 'Setting up Ollama', '[]', 'now', 'now')"
    )
    await conn.commit()
    repo = GleepGlorpNoteRepository(conn)
    note, _ = await _create(repo, "kept", origin_kind="web", origin_session_id="s1")
    assert (note.origin_label, note.origin_exists) == ("Setting up Ollama", True)
    await conn.execute("DELETE FROM chat_sessions WHERE id = 's1'")
    await conn.commit()
    gone = (await repo.list_for_agent())[0]
    assert gone.origin_exists is False and gone.origin_session_id == "s1"
    assert gone.origin_label == "Untitled chat"


async def test_the_repository_refuses_another_name(conn) -> None:
    with pytest.raises(ValueError):
        await GleepGlorpNoteRepository(conn).list_for_agent("alpha")


async def test_no_agent_notes_row_is_touched(conn) -> None:
    await _create(GleepGlorpNoteRepository(conn), "one")
    async with conn.execute("SELECT COUNT(*) FROM agent_notes") as cur:
        assert (await cur.fetchone())[0] == 0
    assert [n.text for n in await GleepGlorpNoteRepository(conn).list_for_agent()] == ["one"]
    assert await AgentNoteRepository(conn).list_for_agent("a") == []


# ── tools ─────────────────────────────────────────────────────────────────


class _Page(Tool):
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.description = "stub"

    async def execute(self, **kwargs: Any) -> str:
        return "PAGE"


async def _agent(responses: list[Message]) -> Agent:
    reg = ToolRegistry()
    reg.register(_Page("fetch_url"))
    tools = await NotesToolProvider().get_tools_for_agent(
        AgentConfig(name=GG, notes_enabled=True), agent_name=GG
    )
    for t in tools:
        reg.register(t)
    agent = Agent(llm=FakeLLM(responses), tools=reg, system_prompt="sys")
    for t in tools:
        t.bind_agent(agent)  # type: ignore[attr-defined]
    return agent


def _asst(*calls: ToolCall) -> Message:
    return Message.assistant("", tool_calls=list(calls))


async def _turn(agent: Agent) -> list[Message]:
    token = current_turn.set(TurnContext(peer=None, session_id=None))
    try:
        return [m async for m in agent.step("go")]
    finally:
        current_turn.reset(token)


def _results(msgs: list[Message]):
    return [m.tool_result for m in msgs if m.role == Role.TOOL and m.tool_result]


async def test_the_tools_save_to_gleepglorps_table_with_its_own_description(conn) -> None:
    tools = await NotesToolProvider().get_tools_for_agent(
        AgentConfig(name=GG, notes_enabled=True), agent_name=GG
    )
    assert [t.name for t in tools] == ["save_note", "update_note", "forget_note"]
    assert tools[0].description == GLEEPGLORP_SAVE_DESCRIPTION
    assert "life" not in tools[0].description and "this app" in tools[0].description
    # The agent default stays as it was.
    plain = await NotesToolProvider().get_tools_for_agent(
        AgentConfig(name="alpha", notes_enabled=True), agent_name="alpha"
    )
    assert "life" in plain[0].description
    assert tools[0].parameters == plain[0].parameters

    agent = await _agent(
        [
            _asst(ToolCall(id="c1", name="save_note", arguments={"text": "Runs Ollama locally"})),
            Message.assistant("done"),
        ]
    )
    results = _results(await _turn(agent))
    assert results[0].content == "Saved note [1]."
    assert [n.text for n in await GleepGlorpNoteRepository(conn).list_for_agent()] == [
        "Runs Ollama locally"
    ]


async def test_a_note_saved_after_outside_content_is_flagged(conn) -> None:
    agent = await _agent(
        [
            _asst(ToolCall(id="c1", name="fetch_url", arguments={})),
            _asst(ToolCall(id="c2", name="save_note", arguments={"text": "From a page"})),
            Message.assistant("done"),
        ]
    )
    await _turn(agent)
    (note,) = await GleepGlorpNoteRepository(conn).list_for_agent()
    assert note.untrusted and "fetch_url" in note.untrusted_sources


async def test_the_per_turn_write_budget_applies(conn) -> None:
    calls = [
        ToolCall(id=f"c{i}", name="save_note", arguments={"text": f"note {i}"}) for i in range(6)
    ]
    agent = await _agent([_asst(*calls), Message.assistant("done")])
    results = _results(await _turn(agent))
    assert sum(1 for r in results if r.content.startswith("Saved")) == 5
    assert "Note limit for this turn" in results[5].content
    assert len(await GleepGlorpNoteRepository(conn).list_for_agent()) == 5


async def test_turning_memory_off_mid_chat_makes_the_next_write_fail(conn) -> None:
    agent = await _agent(
        [
            _asst(ToolCall(id="c1", name="save_note", arguments={"text": "first"})),
            Message.assistant("done"),
            _asst(ToolCall(id="c2", name="save_note", arguments={"text": "second"})),
            Message.assistant("done"),
        ]
    )
    assert _results(await _turn(agent))[0].content == "Saved note [1]."
    await save_settings(conn, GleepGlorpSettings(memory=False))
    out = _results(await _turn(agent))[0]
    assert out.is_error and "Memory is off" in out.content
    assert len(await GleepGlorpNoteRepository(conn).list_for_agent()) == 1


# ── prompt layer ──────────────────────────────────────────────────────────


def test_the_heading_override_leaves_the_default_untouched() -> None:
    class N:
        number, text, untrusted = 1, "x", False

    assert render_notes_block([N()]).startswith(NOTES_HEADING + "\n\n<saved_notes>")
    assert render_notes_block([N()], tools=False).startswith(NOTES_HEADING_TOOL_FREE + "\n\n")
    custom = render_notes_block([N()], heading="H")
    assert custom == "H\n\n<saved_notes>\n[1] x\n</saved_notes>"


async def test_the_prompt_carries_gleepglorps_notes_before_the_date_line(conn) -> None:
    await _create(GleepGlorpNoteRepository(conn), "Runs Ollama locally", untrusted=True)
    prompts = await build_prompts(conn, tool_available=True)
    text = prompts.tool_capable
    assert text.index(GLEEPGLORP_NOTES_HEADING) < text.index("[1] (unverified) Runs Ollama")
    assert text.index("</saved_notes>") < text.index("current_time")
    assert "rules take precedence" not in text and "life" not in GLEEPGLORP_NOTES_HEADING
    free = prompts.tool_free
    assert GLEEPGLORP_NOTES_HEADING_TOOL_FREE in free
    assert "save_note" not in free and "current_time" not in free
    assert "No saved notes yet." not in text


async def test_memory_off_leaves_the_notes_out_of_the_prompt(conn) -> None:
    await _create(GleepGlorpNoteRepository(conn), "kept")
    await save_settings(conn, GleepGlorpSettings(memory=False))
    prompts = await build_prompts(conn, tool_available=True)
    assert "saved_notes" not in prompts.tool_capable + prompts.tool_free


async def test_an_empty_memory_renders_the_empty_block(conn) -> None:
    prompts = await build_prompts(conn, tool_available=True)
    assert "<saved_notes>\nNo saved notes yet.\n</saved_notes>" in prompts.tool_capable


def test_compose_orders_the_layers() -> None:
    out = compose(notes_block="NOTES", date_line="DATE", base="BASE")
    assert out == "BASE\n\nNOTES\n\nDATE"
    assert compose(base="BASE") == "BASE"


# ── routes ────────────────────────────────────────────────────────────────


@pytest.fixture
async def client(conn):
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            yield c


async def test_the_list_route_shape(conn, client) -> None:
    resp = await client.get("/api/gleepglorp/notes")
    assert resp.json() == {
        "enabled": True,
        "notes": [],
        "limits": {"note_chars": 400, "total_chars": 4000, "writes_per_turn": 5},
        "usage": {"total_chars": 0},
    }
    await _create(GleepGlorpNoteRepository(conn), "Runs Ollama", untrusted=True)
    await save_settings(conn, GleepGlorpSettings(memory=False))
    body = (await client.get("/api/gleepglorp/notes")).json()
    assert body["enabled"] is False and body["usage"] == {"total_chars": 11}
    (row,) = body["notes"]
    assert "agent_name" not in row and "pending" not in row
    assert row["text"] == "Runs Ollama" and row["untrusted"] is True


async def test_delete_one_and_clear_all(conn, client) -> None:
    repo = GleepGlorpNoteRepository(conn)
    a, _ = await _create(repo, "one")
    await _create(repo, "two")
    await _create(repo, "three")
    assert (await client.delete("/api/gleepglorp/notes/nope")).status_code == 404
    assert (await client.delete(f"/api/gleepglorp/notes/{a.id}")).json() == {"status": "ok"}
    assert (await client.delete(f"/api/gleepglorp/notes/{a.id}")).status_code == 404
    assert (await client.delete("/api/gleepglorp/notes")).json() == {"deleted": 2}
    assert (await client.delete("/api/gleepglorp/notes")).json() == {"deleted": 0}
    assert await _counter(conn) == 4  # numbers are never reused


async def test_the_routes_need_the_credential() -> None:
    from the_one.interfaces.web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/gleepglorp/notes")).status_code == 401
        assert (await c.delete("/api/gleepglorp/notes/x")).status_code == 401
        assert (await c.delete("/api/gleepglorp/notes")).status_code == 401

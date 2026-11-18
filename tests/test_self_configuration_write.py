"""Tests for the self-revision write path (M21 F01 L03) — AC1-AC7.

Covers the two write tools (``update_my_description`` /
``update_my_system_prompt``), the ``pending`` deferral registry, the two
``app.py`` turn-settle hook sites, and LD7's fixed prefixed tool names /
``_slugify`` parity. AC8/AC8b (reconcile, reserved name) live in
``tests/test_self_configuration_api.py`` and ``tests/test_self_configuration_
surface.py`` — LD7 touches those files' existing fixtures directly. AC9 (the
behavior test) is run separately by the Flight Director, not here.

Identity resolution (``_calling_agent``) is Leg 2's own well-tested seam;
these tests patch it to a fixed agent name so the write-path logic itself
(persist-then-defer, bounds, the settle hook) is isolated from the gate/
credential machinery.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from conftest import expected_date_layer
from cryptography.fernet import Fernet

from tests._platform_prompt_pins import PLATFORM_TOOL_FREE_PIN as PLATFORM_TOOL_FREE
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig, compose_system_prompt
from the_one.agent.core import Agent
from the_one.agent.platform_prompt import Capabilities, render_platform
from the_one.db.repositories import (
    AgentRevisionRepository,
    AgentRuleRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import Session as _Session
from the_one.interfaces.web.app import _process_and_broadcast, _resume_paused_session
from the_one.llm.base import LLMProvider, Message, StreamChunk, ToolCall, ToolResult
from the_one.mcp._tool import _TOOL_NAME_MAX_LEN, _normalize_source_name
from the_one.self_configuration import manage, pending, surface
from the_one.tools.base import Tool, ToolRegistry


def Session(**kwargs):  # noqa: N802 - stands in for the class
    """A chat always names its agent (M36 F1 L03, no Default agent). These tests record the
    pending revision and store the agent under the arbitrary name ``default`` (they never go
    through the naming rule), so a session built here carries that name."""
    kwargs.setdefault("agent_name", "default")
    return _Session(**kwargs)


# A stub agent has no knowledge-base or execution tools in its registry.
PLATFORM_STUB = render_platform(Capabilities(knowledge=False, exec_tools=False))


@pytest.fixture(autouse=True)
def _clear_pending():
    pending.clear_for_test()
    yield
    pending.clear_for_test()


@pytest.fixture
async def db(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    test_key = Fernet.generate_key()
    encryptor = Encryptor(test_key, key_path=tmp_path / "test.key")
    yield conn, encryptor
    await conn.close()


@pytest.fixture
def wired(db, monkeypatch):
    """Point surface.py's module-level connection/encryptor resolution at
    the isolated test DB. ``_calling_agent`` is patched per-test (its
    return value varies by test)."""
    conn, encryptor = db
    monkeypatch.setattr(surface, "get_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(surface, "get_encryptor", lambda *_a, **_kw: encryptor)
    # M27 F1: ``apply_pending_revision`` reads the agent's rules through the
    # lazily imported ``the_one.db.connection.get_connection`` (never
    # ``surface.get_connection``); point it at the same isolated DB.
    monkeypatch.setattr(
        "the_one.db.connection.get_connection", AsyncMock(return_value=conn), raising=True
    )
    return conn, encryptor


def _as_agent(monkeypatch, agent_name: str) -> None:
    monkeypatch.setattr(surface, "_calling_agent", AsyncMock(return_value=agent_name))
    # M21 F03 L02: the two write tools resolve provenance via
    # ``_calling_principal`` (not ``_calling_agent``); patch it to the agent's
    # own (``self``) write so these self-path tests exercise the write logic
    # unchanged. The external-provenance tests patch it themselves.
    monkeypatch.setattr(
        surface, "_calling_principal", AsyncMock(return_value=(agent_name, "self", None))
    )


def _as_external(monkeypatch, agent_name: str, identifier: str) -> None:
    """M21 F03 L02: patch ``_calling_principal`` to an EXTERNAL write — the
    agent it is scoped to, ``source='external'``, and the credential
    identifier as ``source_principal``."""
    monkeypatch.setattr(
        surface,
        "_calling_principal",
        AsyncMock(return_value=(agent_name, "external", identifier)),
    )


async def _seed_agent(store: SQLiteAgentStore, **overrides: Any) -> AgentConfig:
    cfg = AgentConfig(name=overrides.pop("name", "write-agent"), **overrides)
    await store.save(cfg)
    return cfg


# ── AC1 — catalog shape is the allowlist ─────────────────────────────────


class TestAC1CatalogShape:
    def test_exactly_four_tools(self) -> None:
        names = {t["name"] for t in surface.list_surface_tools()}
        assert names == {
            "get_my_configuration",
            "describe_my_capabilities",
            "update_my_description",
            "update_my_system_prompt",
        }

    def test_write_tools_take_only_text_and_apply(self) -> None:
        tools = {t["name"]: t for t in surface.list_surface_tools()}
        for name in ("update_my_description", "update_my_system_prompt"):
            schema = tools[name]["input_schema"]
            props = set(schema.get("properties", {}))
            assert props == {"text", "apply"}, f"{name} schema properties: {props}"
            assert set(schema.get("required", [])) == {"text", "apply"}

    def test_no_tool_schema_names_an_agentconfig_field(self) -> None:
        """The write allowlist is the catalog's SHAPE — no tool takes a
        field name, so a future AgentConfig field is unwritable by
        construction. ``text``/``apply`` (the only write-tool params)
        happen to name nothing in AgentConfig, which is exactly the point:
        this assertion pins that they never will by accident."""
        field_names = set(AgentConfig.model_fields)
        for tool in surface.list_surface_tools():
            props = set((tool["input_schema"] or {}).get("properties", {}))
            overlap = props & field_names
            assert not overlap, f"{tool['name']} schema exposes field-shaped params: {overlap}"


# ── AC2 / AC7 — persistence and input bounds ─────────────────────────────


class TestAC2PersistExactField:
    async def test_system_prompt_revision_touches_only_that_field(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store,
            name="a1",
            description="orig description",
            system_prompt="orig prompt",
            mcp_source_ids=["src-1"],
            enabled_tools=["shell"],
            secret_ids=["sec-1"],
        )
        before_updated_at = await _row_updated_at(conn, "a1")

        _as_agent(monkeypatch, "a1")
        result = await surface.update_my_system_prompt(
            ctx=None, text="new prompt", apply="next_session"
        )

        assert result["applied_to_store"] is True
        assert result["effective"] == "next_session"
        assert result["field"] == "system_prompt"
        assert result["length"] == len("new prompt")

        after = await store.load("a1")
        assert after.system_prompt == "new prompt"
        assert after.description == "orig description"
        assert after.mcp_source_ids == ["src-1"]
        assert after.enabled_tools == ["shell"]
        assert after.secret_ids == ["sec-1"]  # sortie 10: an agent cannot change its grants
        after_updated_at = await _row_updated_at(conn, "a1")
        assert after_updated_at != before_updated_at

    async def test_description_revision_touches_only_that_field(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="a2", description="orig", system_prompt="prompt stays")

        _as_agent(monkeypatch, "a2")
        await surface.update_my_description(ctx=None, text="new desc", apply="next_session")

        after = await store.load("a2")
        assert after.description == "new desc"
        assert after.system_prompt == "prompt stays"


class TestAC7InputBounds:
    @pytest.mark.parametrize(
        "text,apply",
        [
            ("", "next_turn"),
            (None, "next_turn"),
            (123, "next_turn"),
            ("ok text", "sometime"),
            ("ok text", ""),
            ("ok text", None),
        ],
    )
    async def test_rejected_inputs_raise_value_error(self, wired, monkeypatch, text, apply) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="a3", system_prompt="unchanged")
        _as_agent(monkeypatch, "a3")

        with pytest.raises(ValueError):
            await surface.update_my_system_prompt(ctx=None, text=text, apply=apply)

        after = await store.load("a3")
        assert after.system_prompt == "unchanged"

    async def test_oversized_text_rejected(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="a4", system_prompt="unchanged")
        _as_agent(monkeypatch, "a4")

        huge = "x" * (64 * 1024 + 1)
        with pytest.raises(ValueError):
            await surface.update_my_system_prompt(ctx=None, text=huge, apply="next_turn")

        after = await store.load("a4")
        assert after.system_prompt == "unchanged"

    async def test_exactly_64kib_is_accepted(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="a5", system_prompt="unchanged")
        _as_agent(monkeypatch, "a5")

        exactly = "x" * (64 * 1024)
        result = await surface.update_my_system_prompt(ctx=None, text=exactly, apply="next_session")
        assert result["applied_to_store"] is True

    async def test_rejected_call_never_records_pending(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="a6", system_prompt="unchanged")
        _as_agent(monkeypatch, "a6")

        with pytest.raises(ValueError):
            await surface.update_my_system_prompt(ctx=None, text="", apply="next_turn")

        fake_agent = _FakeLiveAgent("unchanged")
        assert await pending.apply_pending_revision("a6", fake_agent) is False


async def _row_updated_at(conn: aiosqlite.Connection, name: str) -> str:
    async with conn.execute("SELECT updated_at FROM agents WHERE name = ?", (name,)) as cur:
        row = await cur.fetchone()
    return row["updated_at"]


class _FakeLiveAgent:
    """Minimal stand-in for ``Agent`` — just enough surface for
    ``pending.apply_pending_revision`` (``system_prompt`` + ``messages``)."""

    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt
        self.messages: list[Message] = [Message.system(system_prompt)]


# ── AC5 — next_session leaves the open agent alone ───────────────────────


class TestAC5NextSessionDoesNotDefer:
    async def test_next_session_does_not_record_pending(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="a7", system_prompt="orig")
        _as_agent(monkeypatch, "a7")

        await surface.update_my_system_prompt(ctx=None, text="new", apply="next_session")

        fake_agent = _FakeLiveAgent("orig")
        # No pending entry was ever recorded for next_session — apply is a no-op.
        assert await pending.apply_pending_revision("a7", fake_agent) is False
        assert fake_agent.system_prompt == "orig"

        # But a rebuilt agent (a fresh load) sees the new value — the store
        # is the source of truth for next_session.
        reloaded = await store.load("a7")
        assert reloaded.system_prompt == "new"


# ── AC6 — description revisions never touch messages ─────────────────────


class TestAC6DescriptionNeverTouchesMessages:
    async def test_next_turn_description_revision_leaves_messages_untouched(
        self, wired, monkeypatch
    ) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="a8", description="orig", system_prompt="prompt")
        _as_agent(monkeypatch, "a8")

        await surface.update_my_description(ctx=None, text="new desc", apply="next_turn")

        fake_agent = _FakeLiveAgent("prompt")
        original_messages = list(fake_agent.messages)
        applied = await pending.apply_pending_revision("a8", fake_agent)

        assert applied is True
        assert fake_agent.messages == original_messages
        assert fake_agent.system_prompt == "prompt"

        after = await store.load("a8")
        assert after.description == "new desc"


# ── AC3 — next_turn does not land mid-turn ────────────────────────────────


class ScriptedLLM(LLMProvider):
    """Fake provider replaying a scripted sequence of assistant Messages,
    recording every request's ``messages`` (mirrors
    ``tests/test_agent_redundant_backstop.py::ScriptedLLM``)."""

    name = "scripted"

    def __init__(self, responses: list[Message]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def supports_tools(self) -> bool:
        return True

    async def complete(  # pragma: no cover - loop uses stream()
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        raise NotImplementedError

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append({"messages": list(messages), "tools": tools})
        msg = self.responses.pop(0)
        yield StreamChunk(
            content=msg.content, is_final=True, tool_calls=msg.tool_calls, message=msg
        )


class _RevisingTool(Tool):
    """Stands in for the real ``update_my_system_prompt`` MCP tool inside
    the agent loop: mutates the store (via the real write-path helper) and
    records the pending next_turn deferral — exactly what the production
    tool does, minus the loopback HTTP hop and identity resolution (both
    already exercised elsewhere)."""

    def __init__(self, agent_name: str) -> None:
        self.name = "update_my_system_prompt"
        self.description = "Revise this agent's own system prompt."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {"text": {"type": "string"}, "apply": {"type": "string"}},
            "required": ["text", "apply"],
        }
        self._agent_name = agent_name

    async def execute(self, **kwargs: Any) -> str:
        result = await surface._apply_revision(
            self._agent_name, "system_prompt", kwargs["text"], kwargs["apply"]
        )
        return f"revised: {result}"


class _SearchStub(Tool):
    def __init__(self) -> None:
        self.name = "search_tools"
        self.description = "Search every tool available to you."
        self.parameters = {"type": "object", "properties": {"query": {}}, "required": []}

    async def execute(self, **kwargs: Any) -> str:  # pragma: no cover
        return ""


class TestAC3MidTurnNonApplication:
    async def test_second_request_in_same_turn_still_carries_old_prompt(
        self, wired, monkeypatch
    ) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="turn-agent", system_prompt="OLD PROMPT")
        rules_repo = AgentRuleRepository(conn)
        await rules_repo.create("turn-agent", "Always answer in French.")
        off = await rules_repo.create("turn-agent", "Never mention cats.", enabled=False)
        assert off.enabled is False

        reg = ToolRegistry()
        reg.register(_RevisingTool("turn-agent"))
        reg.register(_SearchStub())

        tool_call = ToolCall(
            id="tc_1",
            name="update_my_system_prompt",
            arguments={"text": "NEW PROMPT", "apply": "next_turn"},
        )
        first_response = Message.assistant("", tool_calls=[tool_call])
        second_response = Message.assistant("all done, no more tools")

        llm = ScriptedLLM([first_response, second_response])
        agent = Agent(llm=llm, tools=reg, system_prompt="OLD PROMPT")

        messages_before_turn = list(agent.messages)
        _ = [m async for m in agent.step("please revise yourself")]

        # Two LLM requests happened: the first (pre-tool-call) and the
        # second (post-tool-dispatch, same turn). BOTH must have carried
        # the OLD system message — the tool call landed between them, but
        # next_turn defers to loop exit, not the next iteration.
        assert len(llm.calls) == 2
        for call in llm.calls:
            assert call["messages"][0].content == "OLD PROMPT"

        # The live agent object itself is untouched mid-turn.
        assert agent.system_prompt == "OLD PROMPT"
        assert agent.messages[0].content == "OLD PROMPT"

        # The revision WAS persisted to the store immediately (LD2).
        stored = await store.load("turn-agent")
        assert stored.system_prompt == "NEW PROMPT"

        # History grew (user msg, assistant+tool_call, tool result,
        # assistant) — untouched by the deferral.
        assert len(agent.messages) > len(messages_before_turn)

        # Now settle the turn (what app.py's non-paused settle does) —
        # the deferred revision applies, and the NEXT request would carry
        # the new prompt, with history intact (no wipe).
        history_len_before_settle = len(agent.messages)
        applied = await pending.apply_pending_revision("turn-agent", agent)
        assert applied is True
        # Known Issue 2 closed (M27 F1): the recomposed prompt keeps the base
        # prompt and carries the enabled rules (not the disabled one).
        expected = compose_system_prompt(
            PLATFORM_STUB,
            "NEW PROMPT",
            rules=["Always answer in French."],
            date_line=expected_date_layer(False),
        )
        assert expected.startswith(PLATFORM_STUB)
        assert agent.system_prompt == expected
        assert agent.messages[0].content == expected
        assert "Never mention cats." not in agent.system_prompt
        assert len(agent.messages) == history_len_before_settle  # no wipe

        # A subsequent step's first request now carries the new prompt.
        llm.responses.append(Message.assistant("ack"))
        _ = [m async for m in agent.step("thanks")]
        assert llm.calls[-1]["messages"][0].content == expected


# ── AC4 — the hook runs at the non-paused settle only, once ──────────────


class _StubAgent:
    """Minimal ``Agent`` stand-in for driving ``_process_and_broadcast`` /
    ``_resume_paused_session`` directly (mirrors
    ``tests/test_app_websocket_pause_resume.py::StubAgent``)."""

    def __init__(
        self,
        step_messages: list[Message] | None = None,
        resume_messages: list[Message] | None = None,
        deferred_tool_calls: list[ToolCall] | None = None,
        system_prompt: str = "original",
    ) -> None:
        self._step_messages = step_messages or []
        self._resume_messages = resume_messages or []
        self._deferred_tool_calls = deferred_tool_calls
        self.system_prompt = system_prompt
        self.messages: list[Message] = [Message.system(system_prompt)]

        class _LLMShim:
            max_context_tokens = 128_000

            async def supports_tools(self):
                return True

        self.llm = _LLMShim()
        # Empty registry: current_time is absent, so the date layer omits the tool.
        self.tools = ToolRegistry()

    async def step(self, user_input, on_chunk=None, on_usage=None):  # noqa: ARG002
        for m in self._step_messages:
            yield m

    async def resume_after_auth(self):
        if self._deferred_tool_calls is None:
            return
        self._deferred_tool_calls = None
        for m in self._resume_messages:
            yield m

    def reset(self) -> None:  # pragma: no cover
        self.messages = []


def _pause_message() -> Message:
    return Message.tool(
        ToolResult(
            tool_call_id="tc_pause",
            content="auth required",
            metadata={
                "is_auth_required": True,
                "source_id": "src1",
                "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
                "tool_call_id": "tc_pause",
            },
        )
    )


@pytest.fixture(autouse=True)
def _clock(frozen_clock):
    """Every settle composes a date layer; pin it (M28 F1 L2)."""
    return frozen_clock


@pytest.fixture(autouse=True)
def _stub_broadcast_and_persist(monkeypatch):
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))


# M27 F1: a settled ``next_turn`` revision is recomposed as base + persona
# (+ the agent's enabled rules), never the raw persona (Known Issue 2).
_NEW = compose_system_prompt(PLATFORM_STUB, "NEW", date_line=expected_date_layer(False))


class TestAC4HookRunsAtNonPausedSettleOnly:
    async def test_non_paused_turn_applies_the_revision(self, isolated_db) -> None:
        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        session = Session(id="cs-1", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")

        await _process_and_broadcast(session, "hi")

        assert agent.system_prompt == _NEW
        assert agent.messages[0].content == _NEW

    async def test_paused_turn_does_not_apply(self, isolated_db) -> None:
        agent = _StubAgent(
            step_messages=[
                Message.assistant("", tool_calls=[ToolCall(id="tc_pause", name="x", arguments={})]),
                _pause_message(),
            ],
            system_prompt="OLD",
        )
        session = Session(id="cs-2", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")

        await _process_and_broadcast(session, "hi")

        assert agent.system_prompt == "OLD"
        assert agent.messages[0].content == "OLD"
        # The entry is still pending — a later non-paused settle will apply it.
        assert await pending.apply_pending_revision("default", agent) is True
        assert agent.system_prompt == _NEW

    async def test_resume_that_settles_applies_the_revision(self, isolated_db) -> None:
        agent = _StubAgent(
            deferred_tool_calls=[ToolCall(id="tc_pause", name="x", arguments={})],
            resume_messages=[Message.assistant("resumed and done")],
            system_prompt="OLD",
        )
        session = Session(id="cs-3", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")

        await _resume_paused_session(session)

        assert agent.system_prompt == _NEW
        assert agent.messages[0].content == _NEW

    async def test_resume_that_re_pauses_does_not_apply(self, isolated_db) -> None:
        agent = _StubAgent(
            deferred_tool_calls=[ToolCall(id="tc_pause2", name="x", arguments={})],
            resume_messages=[_pause_message()],
            system_prompt="OLD",
        )
        session = Session(id="cs-4", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")

        await _resume_paused_session(session)

        assert agent.system_prompt == "OLD"
        assert agent.messages[0].content == "OLD"

    async def test_entry_consumed_second_settle_is_a_no_op(self, isolated_db) -> None:
        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        session = Session(id="cs-5", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")

        await _process_and_broadcast(session, "hi")
        assert agent.system_prompt == _NEW

        # A second, unrelated non-paused turn must NOT re-apply (no entry left).
        agent._step_messages = [Message.assistant("again")]
        await _process_and_broadcast(session, "hi again")
        assert agent.system_prompt == _NEW
        assert agent.messages[0].content == _NEW

    async def test_a_session_with_no_agent_name_skips_the_hook(self, isolated_db) -> None:
        """M36 F1 L03: a chat always names its agent; a missing name (impossible after
        schema v53) skips the hook instead of falling back to a Default agent, so a pending
        entry stays where it was."""
        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        session = Session(
            id="cs-6", agent=agent, created="2026-08-24T00:00:00+00:00", agent_name=None
        )
        pending.record("default", system_prompt="NEW")

        await _process_and_broadcast(session, "hi")

        assert agent.system_prompt == "OLD"
        assert "default" in pending._pending
        pending._pending.pop("default", None)


class TestRulesAtSettle:
    """M27 F1 (AC12, AC13): the settle hook composes rules and survives a
    failed rules read."""

    async def test_settle_applies_base_persona_and_enabled_rules(self, isolated_db) -> None:
        from the_one.db.connection import get_connection

        conn = await get_connection()
        enc = Encryptor(Fernet.generate_key(), key_path=isolated_db.parent / "k.key")
        store = SQLiteAgentStore(conn, enc)
        await store.save(AgentConfig(name="default"))
        repo = AgentRuleRepository(conn)
        await repo.create("default", "First.")
        await repo.create("default", "Hidden.", enabled=False)
        await repo.create("default", "Second.")

        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        session = Session(id="cs-r1", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")
        await _process_and_broadcast(session, "hi")

        expected = compose_system_prompt(
            PLATFORM_STUB,
            "NEW",
            rules=["First.", "Second."],
            date_line=expected_date_layer(False),
        )
        assert agent.system_prompt == expected
        assert agent.messages[0].content == expected
        assert agent.system_prompt.startswith(PLATFORM_STUB)
        assert "Hidden." not in agent.system_prompt

    @pytest.mark.parametrize("visuals", [True, False])
    async def test_settle_follows_the_agents_rich_visuals_switch(
        self, isolated_db, visuals: bool
    ) -> None:
        """M35 F1 L4 (AC2/AC3): the pending preview renders the section exactly when the
        built agent did, on the main path and on the failed-rules fallback."""
        from unittest.mock import patch

        from the_one.db.connection import get_connection

        conn = await get_connection()
        enc = Encryptor(Fernet.generate_key(), key_path=isolated_db.parent / "kv.key")
        await SQLiteAgentStore(conn, enc).save(AgentConfig(name="default", rich_visuals=visuals))
        platform = render_platform(Capabilities(knowledge=False, exec_tools=False, visuals=visuals))
        assert (("`chart`" in platform) is visuals) and platform.endswith("\n")

        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        agent.rich_visuals = visuals
        session = Session(id=f"cs-v{visuals}", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")
        await _process_and_broadcast(session, "hi")
        assert agent.system_prompt == compose_system_prompt(
            platform, "NEW", date_line=expected_date_layer(False)
        )

        # The fallback path (the prompt build fails): platform + persona, same switch.
        agent2 = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        agent2.rich_visuals = visuals
        session2 = Session(id=f"cs-w{visuals}", agent=agent2, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")
        with patch.object(pending, "build_system_prompts", AsyncMock(side_effect=RuntimeError)):
            await _process_and_broadcast(session2, "hi")
        assert agent2.system_prompt == compose_system_prompt(platform, "NEW")
        assert ("`chart`" in agent2.degraded_system_prompt) is visuals

    async def test_settle_recompose_keeps_the_notes_block(self, isolated_db) -> None:
        """M27 F2 (AC11): the next_turn recompose goes through build_system_prompt,
        so the notes block (and the precedence sentence) survives it."""
        from the_one.db.connection import get_connection
        from the_one.db.repositories import AgentNoteRepository

        conn = await get_connection()
        enc = Encryptor(Fernet.generate_key(), key_path=isolated_db.parent / "k2.key")
        store = SQLiteAgentStore(conn, enc)
        await store.save(AgentConfig(name="default"))
        await store.set_notes_enabled("default", True)
        await AgentRuleRepository(conn).create("default", "Rule.")
        await AgentNoteRepository(conn).create(
            "default",
            "Kept note.",
            untrusted=True,
            sources=["fetch_url"],
            origin_kind="web",
            origin_session_id=None,
            origin_label=None,
            origin_platform=None,
            origin_peer_id=None,
            origin_peer_name=None,
        )
        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        session = Session(id="cs-n1", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")
        await _process_and_broadcast(session, "hi")

        from the_one.agent.config import RenderedNote

        expected = compose_system_prompt(
            PLATFORM_STUB,
            "NEW",
            rules=["Rule."],
            notes=[RenderedNote(1, "Kept note.", True)],
            date_line=expected_date_layer(False),
        )
        assert agent.system_prompt == expected
        assert "[1] (unverified) Kept note." in agent.messages[0].content

    async def test_failed_rules_read_falls_back_and_turn_still_sends_done(
        self, isolated_db, monkeypatch
    ) -> None:
        async def _boom(self, *a, **kw):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(AgentRuleRepository, "list_for_agent", _boom)
        send = AsyncMock(return_value=None)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
        monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
        monkeypatch.setattr(web_app, "_send_to_session", send)

        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        session = Session(id="cs-r2", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")
        await _process_and_broadcast(session, "hi")

        # base + persona only: the fallback is date-free by design (M28 F1 DD4).
        assert agent.system_prompt == compose_system_prompt(PLATFORM_STUB, "NEW")
        assert agent.messages[0].content == agent.system_prompt
        assert any(c.args[1] == {"type": "done"} for c in send.call_args_list)
        # The entry was consumed despite the failure.
        assert await pending.apply_pending_revision("default", agent) is False

    async def test_settle_sets_the_degraded_prompt_with_the_revised_persona(
        self, isolated_db
    ) -> None:
        """Leg 1b: `pending` rebuilds BOTH prompts, so a tool-free turn after a
        next_turn revision sees the revised persona on the tool-free platform prompt."""
        from the_one.agent.core import Agent
        from the_one.db.connection import get_connection
        from the_one.tools.base import ToolRegistry

        conn = await get_connection()
        enc = Encryptor(Fernet.generate_key(), key_path=isolated_db.parent / "kd.key")
        store = SQLiteAgentStore(conn, enc)
        await store.save(AgentConfig(name="default"))
        await AgentRuleRepository(conn).create("default", "Be kind.")

        class _LLM:
            max_context_tokens = 128_000

            async def supports_tools(self):
                return False

        agent = Agent(
            llm=_LLM(),  # type: ignore[arg-type]
            tools=ToolRegistry(),
            system_prompt="OLD",
            degraded_system_prompt="OLD-FREE",
        )
        pending.record("default", system_prompt="REVISED PERSONA")
        assert await pending.apply_pending_revision("default", agent) is True

        degraded = agent._build_degraded_messages()[0].content
        assert degraded.startswith(PLATFORM_TOOL_FREE)
        assert "REVISED PERSONA" in degraded and "Be kind." in degraded
        assert "OLD-FREE" not in degraded
        assert agent.system_prompt.startswith(PLATFORM_STUB)
        assert agent.messages[0].content == agent.system_prompt

    async def test_fallback_also_sets_the_degraded_prompt(self, isolated_db, monkeypatch) -> None:
        from the_one.agent.core import Agent
        from the_one.tools.base import ToolRegistry

        async def _boom(self, *a, **kw):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(AgentRuleRepository, "list_for_agent", _boom)

        class _LLM:
            async def supports_tools(self):
                return False

        agent = Agent(llm=_LLM(), tools=ToolRegistry(), system_prompt="OLD")  # type: ignore[arg-type]
        pending.record("default", system_prompt="NEW")
        await pending.apply_pending_revision("default", agent)

        assert agent.system_prompt == compose_system_prompt(PLATFORM_STUB, "NEW")
        assert agent.degraded_system_prompt == compose_system_prompt(PLATFORM_TOOL_FREE, "NEW")


# ── LD7 — fixed prefixed tool names and JS/Python slug parity ────────────


class TestLD7FixedToolNames:
    def test_four_prefixed_names_at_most_64_chars(self) -> None:
        prefixed = _normalize_source_name(manage.SURFACE_ROW_NAME)
        for tool_name in (
            "get_my_configuration",
            "describe_my_capabilities",
            "update_my_description",
            "update_my_system_prompt",
        ):
            full = f"mcp__{prefixed}__{tool_name}"
            assert len(full) <= _TOOL_NAME_MAX_LEN, full

    def test_slugify_agrees_with_normalize_source_name_for_the_constant(self) -> None:
        """The JS ``_slugify`` (used only for a tooltip label in
        `mcps-tab.js`) must agree with the backend's
        `_normalize_source_name` for the reserved constant, or the tooltip
        shows a prefixed tool name that does not match the one the agent
        actually sees."""
        js_result = _slugify_py(manage.SURFACE_ROW_NAME)
        py_result = _normalize_source_name(manage.SURFACE_ROW_NAME)
        assert js_result == py_result


def _slugify_py(name: str) -> str:
    """Python port of `mcps-tab.js`'s `_slugify`, kept in lockstep by this
    test — see `mcps-tab.js:_slugify`."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"^_|_$", "", s)
    return s


async def _list_revisions(conn: aiosqlite.Connection, agent_name: str) -> list[dict]:
    async with conn.execute(
        "SELECT * FROM agent_revisions WHERE agent_name = ? ORDER BY created_at, id",
        (agent_name,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


class TestRevisionLogWrite:
    """M21 F02 L01 — AC5/AC6/AC7: the direct write path logs one ``applied``
    revision row per successful self-revision, ordered strictly after save."""

    async def test_description_revision_logs_one_applied_row(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="rlog1", description="old desc", system_prompt="sp")

        _as_agent(monkeypatch, "rlog1")
        await surface.update_my_description(ctx=None, text="new desc", apply="next_session")

        rows = await _list_revisions(conn, "rlog1")
        assert len(rows) == 1
        r = rows[0]
        assert r["field"] == "description"
        assert r["status"] == "applied"
        assert r["source"] == "self"
        assert r["proposed_value"] == "new desc"
        assert r["base_value"] == "old desc"  # value BEFORE the write
        assert r["restored_from"] is None
        assert r["resolved_at"] == r["created_at"]  # applied → resolved at creation

    async def test_system_prompt_revision_logs_one_applied_row(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="rlog2", description="d", system_prompt="old prompt")

        _as_agent(monkeypatch, "rlog2")
        await surface.update_my_system_prompt(ctx=None, text="new prompt", apply="next_turn")

        rows = await _list_revisions(conn, "rlog2")
        assert len(rows) == 1
        r = rows[0]
        assert r["field"] == "system_prompt"
        assert r["status"] == "applied"
        assert r["source"] == "self"
        assert r["proposed_value"] == "new prompt"
        assert r["base_value"] == "old prompt"
        assert r["resolved_at"] == r["created_at"]

    async def test_two_fields_produce_independent_rows(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="rlog3", description="d0", system_prompt="s0")

        _as_agent(monkeypatch, "rlog3")
        await surface.update_my_description(ctx=None, text="d1", apply="next_session")
        await surface.update_my_system_prompt(ctx=None, text="s1", apply="next_session")

        rows = await _list_revisions(conn, "rlog3")
        assert len(rows) == 2
        by_field = {r["field"]: r for r in rows}
        assert by_field["description"]["proposed_value"] == "d1"
        assert by_field["description"]["base_value"] == "d0"
        assert by_field["system_prompt"]["proposed_value"] == "s1"
        assert by_field["system_prompt"]["base_value"] == "s0"

    async def test_first_revision_of_default_empty_base_stores_empty_string(
        self, wired, monkeypatch
    ) -> None:
        # base_value is NOT NULL; a field left at the '' default logs '' not NULL.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="rlog4")  # description defaults to ''

        _as_agent(monkeypatch, "rlog4")
        await surface.update_my_description(ctx=None, text="first", apply="next_session")

        rows = await _list_revisions(conn, "rlog4")
        assert len(rows) == 1
        assert rows[0]["base_value"] == ""

    async def test_persist_failure_leaves_no_orphan_log_row(self, wired, monkeypatch) -> None:
        # AC7 (M21 F03 L02 retarget): the log write is ordered strictly after
        # the field-scoped CAS; a persist that raises must leave no revision
        # row (never a logged-but-unpersisted revision). The direct path no
        # longer calls ``save`` — it calls ``compare_and_set_field`` — so the
        # monkeypatch targets the CAS, preserving the saved-before-logged
        # assertion this test pins.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="rlog5", description="keep")

        async def _boom(self, name, field, base_value, new_value):  # noqa: ANN001
            raise RuntimeError("persist failed")

        monkeypatch.setattr(SQLiteAgentStore, "compare_and_set_field", _boom)
        _as_agent(monkeypatch, "rlog5")

        with pytest.raises(RuntimeError, match="persist failed"):
            await surface.update_my_description(ctx=None, text="never", apply="next_session")

        assert await _list_revisions(conn, "rlog5") == []


class TestApprovalModeBranch:
    """M21 F02 L02 — AC5/AC6/AC7: the approval-mode branch in _apply_revision.

    ON  → enqueue a pending row, no save, no pending.record, truthful result.
    OFF → exactly Leg 1's behavior (persist + log an applied row).
    """

    async def test_approval_on_enqueues_and_does_not_save(self, wired, monkeypatch) -> None:
        # AC5 — the store and live agent are unchanged; a pending/self row is
        # enqueued with base_value=current, proposed_value=text, resolved NULL.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store,
            name="apm1",
            description="orig desc",
            self_revision_requires_approval=True,
        )

        # save must NOT be called under approval mode — fail hard if it is.
        async def _boom(self, config):  # noqa: ANN001
            raise AssertionError("save must not be called under approval mode")

        monkeypatch.setattr(SQLiteAgentStore, "save", _boom)
        # pending.record must NOT be called either.
        record_calls = []
        monkeypatch.setattr(pending, "record", lambda *a, **k: record_calls.append((a, k)))

        _as_agent(monkeypatch, "apm1")
        result = await surface.update_my_description(
            ctx=None, text="proposed desc", apply="next_turn"
        )

        assert result["applied_to_store"] is False
        assert result["effective"] == "pending_operator_approval"
        assert result["field"] == "description"
        assert result["length"] == len("proposed desc")
        assert "approv" in result["message"].lower()
        assert record_calls == []

        rows = await _list_revisions(conn, "apm1")
        assert len(rows) == 1
        r = rows[0]
        assert r["status"] == "pending"
        assert r["source"] == "self"
        assert r["field"] == "description"
        assert r["proposed_value"] == "proposed desc"
        assert r["base_value"] == "orig desc"  # current stored value at capture
        assert r["resolved_at"] is None

    async def test_stored_config_unchanged_under_approval_mode(self, wired, monkeypatch) -> None:
        # AC5 — the actual stored config is not mutated (save patched off is
        # one guard; here assert the round-trip value too, without patching).
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store,
            name="apm2",
            system_prompt="live prompt",
            self_revision_requires_approval=True,
        )
        _as_agent(monkeypatch, "apm2")
        await surface.update_my_system_prompt(ctx=None, text="proposed", apply="next_session")
        after = await store.load("apm2")
        assert after.system_prompt == "live prompt"  # unchanged

    async def test_dedup_same_field_updates_in_place(self, wired, monkeypatch) -> None:
        # AC6 — a second write to the same field refreshes the one pending row.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store,
            name="apm3",
            description="d0",
            self_revision_requires_approval=True,
        )
        _as_agent(monkeypatch, "apm3")
        await surface.update_my_description(ctx=None, text="first", apply="next_session")
        await surface.update_my_description(ctx=None, text="second", apply="next_session")

        rows = await _list_revisions(conn, "apm3")
        assert len(rows) == 1
        assert rows[0]["proposed_value"] == "second"

    async def test_dedup_different_fields_keep_separate_rows(self, wired, monkeypatch) -> None:
        # AC6 — different fields keep separate pending rows.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store,
            name="apm4",
            description="d0",
            system_prompt="s0",
            self_revision_requires_approval=True,
        )
        _as_agent(monkeypatch, "apm4")
        await surface.update_my_description(ctx=None, text="d1", apply="next_session")
        await surface.update_my_system_prompt(ctx=None, text="s1", apply="next_session")
        rows = await _list_revisions(conn, "apm4")
        assert {r["field"] for r in rows} == {"description", "system_prompt"}
        assert len(rows) == 2

    async def test_approval_off_is_leg1_behavior(self, wired, monkeypatch) -> None:
        # AC7 — with approval mode OFF, persist + log an applied row (no regression).
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store,
            name="apm5",
            description="old",
            self_revision_requires_approval=False,
        )
        _as_agent(monkeypatch, "apm5")
        result = await surface.update_my_description(ctx=None, text="new", apply="next_session")
        assert result["applied_to_store"] is True
        assert result["effective"] == "next_session"
        assert (await store.load("apm5")).description == "new"
        rows = await _list_revisions(conn, "apm5")
        assert len(rows) == 1
        assert rows[0]["status"] == "applied"


class TestExternalProvenanceAndCAS:
    """M21 F03 L02 — external-write provenance (DD3), approval honoring (DD4),
    and the field-scoped CAS + stale tool result (DD5).

    Drives the two write tools with an EXTERNAL principal (``_calling_principal``
    patched via ``_as_external``) and the agent's own principal (``_as_agent``),
    across both approval modes.
    """

    async def test_external_direct_write_logs_external_with_principal(
        self, wired, monkeypatch
    ) -> None:
        # AC3 — approval OFF: an external write applies directly and logs one
        # row with source='external', source_principal=<ext identifier>.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="ext1", description="old")

        _as_external(monkeypatch, "ext1", "ext_abc123")
        result = await surface.update_my_description(ctx=None, text="new", apply="next_session")
        assert result["applied_to_store"] is True
        assert (await store.load("ext1")).description == "new"

        rows = await _list_revisions(conn, "ext1")
        assert len(rows) == 1
        assert rows[0]["status"] == "applied"
        assert rows[0]["source"] == "external"
        assert rows[0]["source_principal"] == "ext_abc123"

    async def test_agent_own_direct_write_logs_self_null_principal(
        self, wired, monkeypatch
    ) -> None:
        # AC3 — the agent's own write in the same conditions logs source='self',
        # source_principal IS NULL.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="self1", description="old")

        _as_agent(monkeypatch, "self1")
        await surface.update_my_description(ctx=None, text="new", apply="next_session")

        rows = await _list_revisions(conn, "self1")
        assert len(rows) == 1
        assert rows[0]["source"] == "self"
        assert rows[0]["source_principal"] is None

    async def test_external_write_honors_approval_flag_enqueues_external(
        self, wired, monkeypatch
    ) -> None:
        # AC4 — approval ON: an external write does NOT persist; it enqueues a
        # pending row carrying source='external'/source_principal=<id>.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store, name="ext2", description="orig", self_revision_requires_approval=True
        )

        _as_external(monkeypatch, "ext2", "ext_xyz")
        result = await surface.update_my_description(ctx=None, text="proposed", apply="next_turn")
        assert result["applied_to_store"] is False
        assert result["effective"] == "pending_operator_approval"
        # The store is untouched — the write did not persist.
        assert (await store.load("ext2")).description == "orig"

        rows = await _list_revisions(conn, "ext2")
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0]["source"] == "external"
        assert rows[0]["source_principal"] == "ext_xyz"

    async def test_approve_preserves_external_provenance(self, wired, monkeypatch) -> None:
        # AC4 — the operator approve (mark_applied) applies the pending external
        # row and it REMAINS source='external' (the transition flips only
        # status/resolved_at, never source/source_principal).
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store, name="ext3", description="orig", self_revision_requires_approval=True
        )

        _as_external(monkeypatch, "ext3", "ext_p")
        await surface.update_my_description(ctx=None, text="proposed", apply="next_session")

        revisions = AgentRevisionRepository(conn)
        pending_rows = await revisions.list_for_agent("ext3")
        assert len(pending_rows) == 1
        applied = await revisions.mark_applied(pending_rows[0].id)
        assert applied.status == "applied"
        assert applied.source == "external"
        assert applied.source_principal == "ext_p"

    async def test_stale_direct_write_fails_closed_with_truthful_result(
        self, wired, monkeypatch
    ) -> None:
        # AC6 — a genuine drift between base-capture and the CAS: the field
        # changes under the writer, so the CAS misses, nothing is written, no
        # revision row is logged, the store shows the CONCURRENT value, and the
        # result is truthful stale (non-retry-inducing).
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="stale1", description="v0")

        # Interleave a concurrent write to the SAME field after _apply_revision
        # captured base_value='v0' but before its CAS runs.
        real_cas = SQLiteAgentStore.compare_and_set_field

        async def _drift_then_cas(self, name, field, base_value, new_value):  # noqa: ANN001
            await self.conn.execute(
                "UPDATE agents SET description = 'concurrent' WHERE name = ?", (name,)
            )
            await self.conn.commit()
            return await real_cas(self, name, field, base_value, new_value)

        monkeypatch.setattr(SQLiteAgentStore, "compare_and_set_field", _drift_then_cas)

        _as_external(monkeypatch, "stale1", "ext_s")
        result = await surface.update_my_description(ctx=None, text="mine", apply="next_session")

        assert result["applied_to_store"] is False
        assert result["effective"] == "stale"
        assert result["field"] == "description"
        assert result["current_value"] == "concurrent"
        assert result["proposed_value"] == "mine"
        assert "message" in result
        # Store shows the concurrent value — our write applied nothing.
        assert (await store.load("stale1")).description == "concurrent"
        # No revision row was logged (saved-before-logged: a stale write logs
        # nothing).
        assert await _list_revisions(conn, "stale1") == []

    async def test_stale_result_identical_for_agent_own_call(self, wired, monkeypatch) -> None:
        # AC6 — the stale result is returned identically to the agent's own
        # in-turn call, not just the external client.
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(store, name="stale2", system_prompt="s0")

        real_cas = SQLiteAgentStore.compare_and_set_field

        async def _drift_then_cas(self, name, field, base_value, new_value):  # noqa: ANN001
            await self.conn.execute(
                "UPDATE agents SET system_prompt = 'drifted' WHERE name = ?", (name,)
            )
            await self.conn.commit()
            return await real_cas(self, name, field, base_value, new_value)

        monkeypatch.setattr(SQLiteAgentStore, "compare_and_set_field", _drift_then_cas)

        _as_agent(monkeypatch, "stale2")
        result = await surface.update_my_system_prompt(ctx=None, text="mine", apply="next_turn")

        assert result["applied_to_store"] is False
        assert result["effective"] == "stale"
        assert result["current_value"] == "drifted"
        # A stale write leaves no in-memory deferral either (the stale result
        # is returned before any pending.record).
        assert "stale2" not in pending._pending


class TestProjectionOmitsApprovalMode:
    """M21 F03 L02 (AC8/DD6) — the get_my_configuration projection carries no
    approval-mode field, so no principal (external or agent) can read it
    through the surface, let alone change it."""

    async def test_projection_has_no_approval_mode_key(self, wired, monkeypatch) -> None:
        conn, encryptor = wired
        store = SQLiteAgentStore(conn, encryptor)
        await _seed_agent(
            store, name="proj1", description="d", self_revision_requires_approval=True
        )
        _as_agent(monkeypatch, "proj1")
        projection = await surface.get_my_configuration(ctx=None)
        assert "self_revision_requires_approval" not in projection
        assert not any("approval" in k.lower() for k in projection)


class TestSettleDateLayerToolWording:
    """M28 F1 L2 (AC13): the settle keeps the with-tool wording when the live
    agent's registry holds ``current_time``."""

    async def test_registry_with_current_time_keeps_the_tool_wording(self, isolated_db) -> None:
        from the_one.tools.time_tool import CurrentTimeTool

        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        agent.tools.register(CurrentTimeTool())
        session = Session(id="cs-t1", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")

        await _process_and_broadcast(session, "hi")

        assert agent.system_prompt == compose_system_prompt(
            PLATFORM_STUB, "NEW", date_line=expected_date_layer(True)
        )

    async def test_missing_registry_counts_as_tool_absent(self, isolated_db) -> None:
        agent = _StubAgent(step_messages=[Message.assistant("done")], system_prompt="OLD")
        del agent.tools
        session = Session(id="cs-t2", agent=agent, created="2026-08-24T00:00:00+00:00")
        pending.record("default", system_prompt="NEW")

        await _process_and_broadcast(session, "hi")

        assert agent.system_prompt == _NEW

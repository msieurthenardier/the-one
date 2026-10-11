"""Rules repository, prompt composition and the layer loader (M27 F1).

Covers the ``AgentRuleRepository`` contract (dense 0-based positions, limits,
reorder, scoping), ``build_system_prompt``, a real ``AgentFactory.create`` over
a template database (web build path, chat-only degraded path, the codec round
trip the web session persistence relies on), and AC18 (no agent-reachable rules
write).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from conftest import FakeLLM, expected_date_layer

from tests._schema_template import connect_template_db
from the_one.agent.config import BASE_PROMPT, CHAT_ONLY_PROMPT, AgentConfig, compose_system_prompt
from the_one.agent.factory import AgentFactory
from the_one.agent.prompt_layers import build_system_prompt
from the_one.db._rules import (
    RULE_MAX_CHARS,
    RULES_HEADING,
    RULES_TOTAL_MAX_CHARS,
    RuleLimitError,
    RuleOrderError,
)
from the_one.db.codec import decode_messages, encode_messages
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import (
    AgentRuleRepository,
    LLMProviderRepository,
    SQLiteAgentStore,
)
from the_one.encryption import get_encryptor
from the_one.llm.base import Role


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "rules.db")
    for name in ("alpha", "beta"):
        await SQLiteAgentStore(c).save(AgentConfig(name=name, system_prompt=f"I am {name}."))
    yield c
    await c.close()


@pytest.fixture
def repo(conn) -> AgentRuleRepository:
    return AgentRuleRepository(conn)


# ── repository ───────────────────────────────────────────────────────────


async def test_positions_are_zero_based_and_dense(repo) -> None:
    a = await repo.create("alpha", "one")
    b = await repo.create("alpha", "two")
    c = await repo.create("alpha", "three")
    assert [a.position, b.position, c.position] == [0, 1, 2]

    await repo.delete("alpha", b.id)
    assert [(r.text, r.position) for r in await repo.list_for_agent("alpha")] == [
        ("one", 0),
        ("three", 1),
    ]
    # Deleting everything: the next create starts again at 0.
    for r in await repo.list_for_agent("alpha"):
        await repo.delete("alpha", r.id)
    assert (await repo.create("alpha", "fresh")).position == 0


async def test_text_is_trimmed_and_bounded(repo) -> None:
    rule = await repo.create("alpha", "  padded  ")
    assert rule.text == "padded"
    for bad in ("", "   \n"):
        with pytest.raises(RuleLimitError, match="empty"):
            await repo.create("alpha", bad)
    with pytest.raises(RuleLimitError) as exc:
        await repo.create("alpha", "x" * (RULE_MAX_CHARS + 1))
    assert "500" in exc.value.detail and "501" in exc.value.detail
    await repo.create("alpha", "x" * RULE_MAX_CHARS)  # exactly at the limit


async def test_total_cap_counts_disabled_and_never_blocks_toggle(repo) -> None:
    for i in range(8):
        await repo.create("alpha", "x" * RULE_MAX_CHARS, enabled=(i % 2 == 0))
    assert await repo.total_chars("alpha") == RULES_TOTAL_MAX_CHARS
    with pytest.raises(RuleLimitError) as exc:
        await repo.create("alpha", "y")
    assert "4,000" in exc.value.detail and "4,001" in exc.value.detail
    rules = await repo.list_for_agent("alpha")
    # Editing a rule to a longer text is checked against the others' total.
    shorter = await repo.update("alpha", rules[0].id, text="x" * 10)
    assert shorter.text == "x" * 10
    with pytest.raises(RuleLimitError):
        await repo.update("alpha", rules[0].id, text="x" * (RULE_MAX_CHARS + 1))
    # Toggling enabled never fails, even at the cap.
    await repo.update("alpha", rules[0].id, text="x" * RULE_MAX_CHARS)
    toggled = await repo.update("alpha", rules[1].id, enabled=True)
    assert toggled.enabled is True


async def test_update_keeps_unspecified_fields(repo) -> None:
    r = await repo.create("alpha", "keep", enabled=False)
    out = await repo.update("alpha", r.id, text="changed")
    assert (out.text, out.enabled) == ("changed", False)
    out = await repo.update("alpha", r.id, enabled=True)
    assert (out.text, out.enabled) == ("changed", True)


async def test_rules_are_scoped_to_their_agent(repo) -> None:
    r = await repo.create("alpha", "mine")
    assert await repo.get("beta", r.id) is None
    with pytest.raises(KeyError):
        await repo.update("beta", r.id, text="x")
    with pytest.raises(KeyError):
        await repo.delete("beta", r.id)
    assert await repo.list_for_agent("beta") == []


async def test_reorder_requires_exact_permutation_and_is_atomic(repo) -> None:
    ids = [(await repo.create("alpha", t)).id for t in ("a", "b", "c")]
    other = (await repo.create("beta", "foreign")).id
    for bad in (ids[:2], ids + [ids[0]], ids[:2] + ["nope"], ids[:2] + [other], []):
        with pytest.raises(RuleOrderError):
            await repo.reorder("alpha", bad)
    assert [r.text for r in await repo.list_for_agent("alpha")] == ["a", "b", "c"]

    out = await repo.reorder("alpha", [ids[2], ids[0], ids[1]])
    assert [(r.text, r.position) for r in out] == [("c", 0), ("a", 1), ("b", 2)]


# ── build_system_prompt ──────────────────────────────────────────────────


async def test_build_uses_only_enabled_rules_in_position_order(conn, repo, frozen_clock) -> None:
    first = await repo.create("alpha", "First.")
    await repo.create("alpha", "Off.", enabled=False)
    await repo.create("alpha", "Last.")
    await repo.reorder("alpha", [r.id for r in reversed(await repo.list_for_agent("alpha"))])

    out = await build_system_prompt("alpha", "I am alpha.", conn=conn)

    assert out == compose_system_prompt(
        BASE_PROMPT,
        "I am alpha.",
        rules=["Last.", "First."],
        date_line=expected_date_layer(False),
    )
    assert "Off." not in out
    assert first.text in out


async def test_build_without_rows_or_rules_is_base_plus_persona(conn, frozen_clock) -> None:
    date = expected_date_layer(False)
    assert await build_system_prompt("ghost", "P", conn=conn) == compose_system_prompt(
        BASE_PROMPT, "P", date_line=date
    )
    assert await build_system_prompt("alpha", "", conn=conn) == BASE_PROMPT + "\n\n---\n\n" + date


async def test_build_defaults_to_the_process_connection(conn, repo, frozen_clock) -> None:
    await repo.create("alpha", "From the singleton.")
    with patch("the_one.db.connection.get_connection", AsyncMock(return_value=conn)):
        out = await build_system_prompt("alpha", "P")
    assert out.endswith("1. From the singleton.\n\n---\n\n" + expected_date_layer(False))
    assert RULES_HEADING in out


# ── real factory builds ──────────────────────────────────────────────────


@pytest.fixture
async def factory(conn, tmp_path):
    enc = get_encryptor(tmp_path)
    await LLMProviderRepository(conn, enc).create(
        LLMProviderConfig(id="prov-1", name="p", type="ollama", base_url="http://x")
    )
    store = SQLiteAgentStore(conn)
    await store.save(
        AgentConfig(name="alpha", provider_config_id="prov-1", system_prompt="I am alpha.")
    )
    llm = FakeLLM(responses=[])
    with (
        patch("the_one.agent.factory.get_provider", lambda name, **kw: llm),
        patch("the_one.db.connection.get_connection", AsyncMock(return_value=conn)),
        patch("the_one.encryption.get_encryptor", return_value=enc),
    ):
        yield AgentFactory(store=store)


async def test_factory_build_orders_persona_then_enabled_rules(factory, repo, frozen_clock) -> None:
    await repo.create("alpha", "Rule A.")
    await repo.create("alpha", "Rule off.", enabled=False)
    await repo.create("alpha", "Rule B.")

    agent = await factory.create("alpha")

    expected = compose_system_prompt(
        BASE_PROMPT,
        "I am alpha.",
        rules=["Rule A.", "Rule B."],
        date_line=expected_date_layer(True),
    )
    assert agent.system_prompt == expected
    assert agent.messages[0].content == expected
    assert "Rule off." not in agent.messages[0].content


async def test_chat_only_degraded_path_keeps_the_rules(factory, repo) -> None:
    await repo.create("alpha", "Stay on topic.")
    agent = await factory.create("alpha")

    degraded = agent._build_degraded_messages()[0].content

    assert degraded.startswith(CHAT_ONLY_PROMPT)
    assert RULES_HEADING in degraded and "1. Stay on topic." in degraded
    assert "I am alpha." in degraded


async def test_web_session_system_message_round_trips_through_the_codec(factory, repo) -> None:
    """`_save_session_to_db` persists ``encode_messages(agent.messages)``; the
    rules in element 0 must survive that unchanged (AC20, web half)."""
    await repo.create("alpha", "Rule A.")
    agent = await factory.create("alpha")
    assert "1. Rule A." in agent.messages[0].content

    restored = decode_messages(encode_messages(agent.messages))

    assert restored[0].role == Role.SYSTEM
    assert restored[0].content == agent.messages[0].content


async def test_no_agent_reachable_tool_writes_rules(factory, repo) -> None:
    """AC18: a built agent has no tool with "rule" in its name, and the
    self-configuration write tools are exactly the two prompt/description ones."""
    from the_one.self_configuration import surface

    agent = await factory.create("alpha")
    assert not [n for n in agent.tools.tool_names if "rule" in n.lower()]

    tools = {t["name"] for t in surface.list_surface_tools()}
    assert {n for n in tools if n.startswith("update_")} == {
        "update_my_description",
        "update_my_system_prompt",
    }
    assert not [n for n in tools if "rule" in n.lower()]


async def test_get_my_configuration_returns_the_raw_persona_not_the_composed_prompt(
    conn, repo, monkeypatch, tmp_path
) -> None:
    from the_one.self_configuration import surface

    await repo.create("alpha", "Operator rule.")
    monkeypatch.setattr(surface, "get_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(surface, "get_encryptor", lambda *_a, **_kw: get_encryptor(tmp_path))
    monkeypatch.setattr(surface, "_calling_agent", AsyncMock(return_value="alpha"))

    projection = await surface.get_my_configuration(ctx=None)

    assert projection["system_prompt"] == "I am alpha."
    assert "Operator rule." not in str(projection)


# ── Notes layer (M27 F2 L1) ──────────────────────────────────────────────

_NOTE_ORIGIN = {
    "origin_kind": "web",
    "origin_session_id": None,
    "origin_label": None,
    "origin_platform": None,
    "origin_peer_id": None,
    "origin_peer_name": None,
}


async def _notes_on(conn, name="alpha", *texts, untrusted=False):
    from the_one.db.repositories import AgentNoteRepository

    await SQLiteAgentStore(conn).set_notes_enabled(name, True)
    repo = AgentNoteRepository(conn)
    for t in texts:
        await repo.create(name, t, untrusted=untrusted, sources=[], **_NOTE_ORIGIN)
    return repo


async def test_build_notes_off_loads_nothing_even_with_stored_notes(conn, frozen_clock) -> None:
    repo = await _notes_on(conn, "alpha", "stored")
    await SQLiteAgentStore(conn).set_notes_enabled("alpha", False)
    out = await build_system_prompt("alpha", "P", conn=conn)
    assert out == compose_system_prompt(BASE_PROMPT, "P", date_line=expected_date_layer(False))
    assert "saved_notes" not in out
    assert len(await repo.list_for_agent("alpha")) == 1  # off loses nothing


async def test_build_notes_on_empty_and_with_notes(conn, frozen_clock) -> None:
    await _notes_on(conn, "alpha")
    out = await build_system_prompt("alpha", "P", conn=conn)
    assert out == compose_system_prompt(
        BASE_PROMPT, "P", notes=[], date_line=expected_date_layer(False)
    )
    assert "No saved notes yet." in out

    from the_one.agent.config import RenderedNote

    repo = await _notes_on(conn, "alpha", "first")
    await repo.create("alpha", "second", untrusted=True, sources=["x"], **_NOTE_ORIGIN)
    await repo.create("alpha", "gone", untrusted=False, sources=[], **_NOTE_ORIGIN)
    await repo.forget_by_agent("alpha", 3)
    out = await build_system_prompt("alpha", "P", conn=conn)
    assert out == compose_system_prompt(
        BASE_PROMPT,
        "P",
        notes=[RenderedNote(1, "first", False), RenderedNote(2, "second", True)],
        date_line=expected_date_layer(False),
    )
    assert "[2] (unverified) second" in out


async def test_build_notes_on_without_rules_has_no_rules_layer(conn) -> None:
    await _notes_on(conn, "alpha", "n")
    out = await build_system_prompt("alpha", "P", conn=conn)
    assert RULES_HEADING not in out and "<saved_notes>" in out


async def test_build_notes_on_with_rules_adds_precedence(conn, repo) -> None:
    from the_one.db._rules import RULES_OVER_NOTES

    await repo.create("alpha", "A rule.")
    await _notes_on(conn, "alpha", "n")
    out = await build_system_prompt("alpha", "P", conn=conn)
    assert RULES_OVER_NOTES in out


async def test_factory_build_carries_notes_and_registers_the_notes_tools(factory, conn) -> None:
    await _notes_on(conn, "alpha", "remember this")
    agent = await factory.create("alpha")
    assert "[1] remember this" in agent.messages[0].content
    note_tools = sorted(n for n in agent.tools.tool_names if "note" in n.lower())
    assert note_tools == ["forget_note", "save_note", "update_note"]  # M27 F2 L2


async def test_chat_only_degraded_path_keeps_the_notes(factory, conn) -> None:
    await _notes_on(conn, "alpha", "degraded note")
    agent = await factory.create("alpha")
    degraded = agent._build_degraded_messages()[0].content
    assert degraded.startswith(CHAT_ONLY_PROMPT)
    assert "<saved_notes>\n[1] degraded note" in degraded


async def test_get_my_configuration_omits_notes_enabled(conn, monkeypatch, tmp_path) -> None:
    from the_one.self_configuration import surface

    await _notes_on(conn, "alpha", "secret note")
    monkeypatch.setattr(surface, "get_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(surface, "get_encryptor", lambda *_a, **_kw: get_encryptor(tmp_path))
    monkeypatch.setattr(surface, "_calling_agent", AsyncMock(return_value="alpha"))
    projection = await surface.get_my_configuration(ctx=None)
    assert "notes" not in str(projection).lower()


def test_info_prompt_examples_match_composed_prompt():
    import asyncio

    from fastapi.testclient import TestClient  # noqa: F401

    from the_one.agent.config import BASE_PROMPT, RenderedNote, compose_system_prompt
    from the_one.interfaces.web.app import info

    data = asyncio.run(info())
    assert data["base_prompt"] == BASE_PROMPT
    full = compose_system_prompt(
        BASE_PROMPT,
        "persona",
        rules=["{first enabled rule}", "{second enabled rule}"],
        notes=[
            RenderedNote(1, "{a saved note}", False),
            RenderedNote(2, "{a note saved while outside text was in the conversation}", True),
        ],
    )
    assert data["rules_prompt_example"] in full
    assert data["notes_prompt_example"] in full
    assert "(unverified)" in data["notes_prompt_example"]


# ── M28 F1 L2: the date layer and time_tool_available ─────────────────────

from the_one import time_zones as _tz  # noqa: E402
from the_one.agent import prompt_layers as _pl  # noqa: E402
from the_one.agent.prompt_layers import time_tool_available  # noqa: E402
from the_one.db._notes import parse_notes_block  # noqa: E402
from the_one.tools.base import ToolRegistry  # noqa: E402
from the_one.tools.time_tool import CurrentTimeTool  # noqa: E402

WITH_TOOL = (
    "Today is Saturday, October 10, 2026 (America/Los_Angeles). This date is as of when "
    "this conversation was last loaded. For the current date and time, call current_time."
)
WITHOUT_TOOL = (
    "Today is Saturday, October 10, 2026 (America/Los_Angeles), as of when this "
    "conversation was last loaded."
)


async def test_date_layer_last_with_exact_wordings(conn, frozen_clock) -> None:
    await AgentRuleRepository(conn).create("alpha", "Be brief.")
    on = await build_system_prompt("alpha", "I am alpha.", conn=conn, tool_available=True)
    off = await build_system_prompt("alpha", "I am alpha.", conn=conn)
    assert on.endswith("\n\n---\n\n" + WITH_TOOL)
    assert off.endswith("\n\n---\n\n" + WITHOUT_TOOL)
    assert "Be brief." in on


async def test_date_layer_follows_stored_zone(conn, frozen_clock) -> None:
    await _tz.save_setting(conn, _tz.TimeZoneSetting(mode="zone", zone="Asia/Kolkata"))
    out = await build_system_prompt("alpha", "p", conn=conn)
    assert out.endswith(
        "Today is Sunday, October 11, 2026 (Asia/Kolkata), as of when this "
        "conversation was last loaded."
    )


async def test_date_layer_failure_omits_it_and_keeps_rules(
    conn, frozen_clock, monkeypatch, caplog
) -> None:
    await AgentRuleRepository(conn).create("alpha", "Be brief.")

    async def boom(c=None):
        raise RuntimeError("nope")

    monkeypatch.setattr(_tz, "load_effective_zone", boom)
    with caplog.at_level("WARNING"):
        out = await build_system_prompt("alpha", "p", conn=conn)
    assert "Be brief." in out and "Today is" not in out
    assert any("date layer" in r.message for r in caplog.records)


async def test_notes_block_parses_with_date_layer_after(conn, frozen_clock) -> None:
    await SQLiteAgentStore(conn).set_notes_enabled("alpha", True)
    out = await build_system_prompt("alpha", "p", conn=conn, tool_available=True)
    assert parse_notes_block(out) == {}
    assert out.endswith(WITH_TOOL)


class _LLM:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = 0

    async def supports_tools(self):
        self.calls += 1
        if self.behaviour == "raise":
            raise RuntimeError("x")
        if self.behaviour == "hang":
            import asyncio

            await asyncio.sleep(10)
        return self.behaviour


def _reg(with_tool=True) -> ToolRegistry:
    r = ToolRegistry()
    if with_tool:
        r.register(CurrentTimeTool())
    return r


async def test_time_tool_available_matrix(monkeypatch) -> None:
    monkeypatch.setattr(_pl, "SUPPORTS_TOOLS_TIMEOUT_S", 0.05)
    absent = _LLM(True)
    assert await time_tool_available(_reg(False), absent) is False
    assert absent.calls == 0
    assert await time_tool_available(_reg(), _LLM(True)) is True
    assert await time_tool_available(_reg(), _LLM(False)) is False
    assert await time_tool_available(_reg(), _LLM("raise")) is False
    assert await time_tool_available(_reg(), _LLM("hang")) is False
    assert await time_tool_available(_reg(), None) is False
    assert await time_tool_available(None, _LLM(True)) is False

    class Broken:
        @property
        def tool_names(self):
            raise RuntimeError("x")

    assert await time_tool_available(Broken(), _LLM(True)) is False


# ── M28 F1 L2: the factory seeds current_time and appends the date layer ──


class _NoToolsLLM(FakeLLM):
    async def supports_tools(self) -> bool:
        return False


async def _save(conn, **kw) -> None:
    await SQLiteAgentStore(conn).save(AgentConfig(provider_config_id="prov-1", **kw))


async def test_default_agent_seeds_current_time_and_ends_with_tool_line(
    factory, conn, frozen_clock
) -> None:
    await _save(conn, name="gamma")
    agent = await factory.create("gamma")
    assert "current_time" in agent.tools.tool_names
    assert "current_time" in {s["name"] for s in agent._loaded_schemas}
    assert agent.system_prompt.endswith("\n\n---\n\n" + WITH_TOOL)


async def test_trimmed_whitelist_keeps_current_time(factory, conn, frozen_clock) -> None:
    await _save(conn, name="gamma", enabled_tools=["read_file"])
    agent = await factory.create("gamma")
    assert "current_time" in agent.tools.tool_names
    assert "current_time" in {s["name"] for s in agent._loaded_schemas}
    assert "shell" not in agent.tools.tool_names
    await _save(conn, name="delta", enabled_tools=[])
    empty = await factory.create("delta")
    assert [n for n in empty.tools.tool_names if n != "search_tools"] == ["current_time"]


async def test_agent_disabled_current_time_is_absent_and_unmentioned(
    factory, conn, frozen_clock
) -> None:
    await _save(conn, name="gamma", disabled_tools=["current_time"])
    agent = await factory.create("gamma")
    assert "current_time" not in agent.tools.tool_names
    assert "current_time" not in {s["name"] for s in agent._loaded_schemas}
    assert agent.system_prompt.endswith("\n\n---\n\n" + WITHOUT_TOOL)
    assert "current_time" not in agent.system_prompt


async def test_operator_disabled_current_time_is_absent(
    factory, conn, tmp_path, frozen_clock
) -> None:
    from the_one.db.repositories import ToolConfigRepository

    await ToolConfigRepository(conn, get_encryptor(tmp_path)).upsert(
        "current_time", {}, enabled=False
    )
    await _save(conn, name="gamma")
    agent = await factory.create("gamma")
    assert "current_time" not in agent.tools.tool_names
    assert "current_time" not in {s["name"] for s in agent._loaded_schemas}
    assert agent.system_prompt.endswith(WITHOUT_TOOL)


async def test_chat_only_provider_gets_tool_free_wording(factory, conn, frozen_clock) -> None:
    await _save(conn, name="gamma")
    with patch("the_one.agent.factory.get_provider", lambda name, **kw: _NoToolsLLM([])):
        agent = await factory.create("gamma")
    assert agent.system_prompt.endswith("\n\n---\n\n" + WITHOUT_TOOL)
    degraded = agent._build_degraded_messages()[0].content
    assert WITHOUT_TOOL in degraded
    assert "current_time" not in degraded

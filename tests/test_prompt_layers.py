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
from conftest import FakeLLM

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


async def test_build_uses_only_enabled_rules_in_position_order(conn, repo) -> None:
    first = await repo.create("alpha", "First.")
    await repo.create("alpha", "Off.", enabled=False)
    await repo.create("alpha", "Last.")
    await repo.reorder("alpha", [r.id for r in reversed(await repo.list_for_agent("alpha"))])

    out = await build_system_prompt("alpha", "I am alpha.", conn=conn)

    assert out == compose_system_prompt(BASE_PROMPT, "I am alpha.", rules=["Last.", "First."])
    assert "Off." not in out
    assert first.text in out


async def test_build_without_rows_or_rules_is_base_plus_persona(conn) -> None:
    assert await build_system_prompt("ghost", "P", conn=conn) == compose_system_prompt(
        BASE_PROMPT, "P"
    )
    assert await build_system_prompt("alpha", "", conn=conn) == BASE_PROMPT


async def test_build_defaults_to_the_process_connection(conn, repo) -> None:
    await repo.create("alpha", "From the singleton.")
    with patch("the_one.db.connection.get_connection", AsyncMock(return_value=conn)):
        out = await build_system_prompt("alpha", "P")
    assert out.endswith("1. From the singleton.")
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


async def test_factory_build_orders_persona_then_enabled_rules(factory, repo) -> None:
    await repo.create("alpha", "Rule A.")
    await repo.create("alpha", "Rule off.", enabled=False)
    await repo.create("alpha", "Rule B.")

    agent = await factory.create("alpha")

    expected = compose_system_prompt(BASE_PROMPT, "I am alpha.", rules=["Rule A.", "Rule B."])
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


async def test_build_notes_off_loads_nothing_even_with_stored_notes(conn) -> None:
    repo = await _notes_on(conn, "alpha", "stored")
    await SQLiteAgentStore(conn).set_notes_enabled("alpha", False)
    out = await build_system_prompt("alpha", "P", conn=conn)
    assert out == compose_system_prompt(BASE_PROMPT, "P")
    assert "saved_notes" not in out
    assert len(await repo.list_for_agent("alpha")) == 1  # off loses nothing


async def test_build_notes_on_empty_and_with_notes(conn) -> None:
    await _notes_on(conn, "alpha")
    out = await build_system_prompt("alpha", "P", conn=conn)
    assert out == compose_system_prompt(BASE_PROMPT, "P", notes=[])
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

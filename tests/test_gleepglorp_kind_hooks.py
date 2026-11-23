"""The registry hooks of ``Kind`` (Mission 36 F5 L1a, DD2): the registry rules, the action gate,
``operator_only_message``, ``fill_refused``, ``keyerror_is_gone`` and the ``FieldSpec.path``
helpers. Fake kinds are installed into all four registry views for one test and removed."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tests.test_gleepglorp_apply_error import _p
from the_one.agent._context import TurnContext, current_turn
from the_one.gleepglorp import kinds
from the_one.gleepglorp.fill.tool import NO_NOTES, FillFormTool
from the_one.gleepglorp.kinds import agent, mcp_server
from the_one.gleepglorp.kinds.base import ADDRESSINGS, validate_kind
from the_one.gleepglorp.kinds.errors import ApplyError, translate
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    stored_get,
    stored_set,
)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
PAGE = {"line": "Agents › New agent", "descriptor": {"destination": "agents", "create": True}}


async def _utc():
    return UTC


async def _fake_normalize(action, target, changes, *, conn, now, zone, enc=None, mode="propose"):
    return Normalized("fake", action, None, None, "fake:k", dict(changes))


def fake_kind(**over):
    """A fillable kind built from the agent kind, with one text field."""
    base = {
        "name": "fake",
        "label": "fake thing",
        "fields": (FieldSpec("text", "text", "Text", "text"),),
        "normalize": _fake_normalize,
        "operator_only": ("secret",),
        "actions": ("change",),
        "fillable": ("change",),
    }
    return replace(agent.KIND, **{**base, **over})


def install(monkeypatch, kind) -> None:
    """Put ``kind`` into all four registry views (never edits ``REGISTRY``)."""
    monkeypatch.setitem(kinds._BY_NAME, kind.name, kind)
    monkeypatch.setitem(kinds.SPECS, kind.name, kind.fields)
    names = tuple(n for n in kinds.KINDS if n != kind.name)
    fillable = tuple(n for n in kinds.FILLABLE if n != kind.name)
    monkeypatch.setattr(kinds, "KINDS", (*names, kind.name))
    monkeypatch.setattr(kinds, "FILLABLE", (*fillable, *([kind.name] if kind.fillable else [])))


async def norm(kind_name, action, changes, mode="propose"):
    return await kinds.normalize(
        kind_name, action, {}, changes, conn=None, now=NOW, zone=UTC, enc=None, mode=mode
    )


# --- AC2: the registry rules ---------------------------------------------------------------


def test_every_registered_kind_meets_the_registry_rules() -> None:
    for k in kinds.REGISTRY:
        validate_kind(k)
        assert k.card_extras is not None
        assert k.addressing in ADDRESSINGS
        assert (k.fill_extras is not None) == bool(k.fillable), k.name
        if k.addressing == "id":
            assert k.target_noun, k.name


def test_the_declared_addressing_and_flags_of_the_five_kinds() -> None:
    assert {k.name: k.addressing for k in kinds.REGISTRY} == {
        "agent": "agent",
        "rule": "agent-owned",
        "routine": "agent-owned",
        "mcp_server": "id",
        "provider": "id",
    }
    assert all(k.keyerror_is_gone for k in kinds.REGISTRY)


def test_validate_kind_refuses_each_broken_rule() -> None:
    with pytest.raises(ValueError, match="card_extras"):
        replace(agent.KIND, card_extras=None)
    with pytest.raises(ValueError, match="fill_extras"):
        replace(agent.KIND, fill_extras=None)
    with pytest.raises(ValueError, match="addressing"):
        replace(agent.KIND, addressing="elsewhere")
    with pytest.raises(ValueError, match="target_noun"):
        replace(mcp_server.KIND, target_noun="")
    # The rules stay quiet for a good kind, including the "page" addressing.
    replace(agent.KIND, addressing="page")
    fake_kind()


def test_the_registry_loop_catches_a_bad_entry() -> None:
    good = {
        "name": "x",
        "card_extras": object(),
        "fillable": (),
        "fill_extras": None,
        "addressing": "agent",
        "target_noun": "",
    }
    validate_kind(SimpleNamespace(**good))
    for bad in (
        {"card_extras": None},
        {"fillable": ("create",)},
        {"addressing": "nope"},
        {"addressing": "id"},
    ):
        with pytest.raises(ValueError):
            validate_kind(SimpleNamespace(**{**good, **bad}))


# --- AC3: the action gate ------------------------------------------------------------------


async def test_the_gate_refuses_an_action_the_kind_does_not_allow_in_both_modes(
    monkeypatch,
) -> None:
    install(monkeypatch, fake_kind())
    with pytest.raises(ShapeError) as e:
        await norm("fake", "create", {"text": "x"})
    assert str(e.value) == "A fake thing can't be created by a proposal."
    with pytest.raises(ShapeError) as e:
        await norm("fake", "create", {"text": "x"}, mode="fill")
    assert str(e.value) == "A fake thing can't be created by filling its form."
    # The allowed action goes through, in both modes.
    assert (await norm("fake", "change", {"text": "x"})).changes == {"text": "x"}
    assert (await norm("fake", "change", {"text": "x"}, mode="fill")).changes == {"text": "x"}


async def test_the_gate_uses_fillable_for_a_fill_and_actions_for_a_proposal(monkeypatch) -> None:
    install(monkeypatch, fake_kind(actions=("create", "change"), fillable=("change",)))
    assert (await norm("fake", "create", {"text": "x"})).action == "create"
    with pytest.raises(ShapeError):
        await norm("fake", "create", {"text": "x"}, mode="fill")
    install(monkeypatch, fake_kind(actions=("change",), fillable=("create", "change")))
    with pytest.raises(ShapeError):
        await norm("fake", "create", {"text": "x"})
    assert (await norm("fake", "create", {"text": "x"}, mode="fill")).action == "create"


async def test_the_gate_uses_action_refused_when_the_kind_sets_it(monkeypatch) -> None:
    seen = []

    def refused(action, mode):
        seen.append((action, mode))
        return f"No {action} here ({mode})."

    install(monkeypatch, fake_kind(action_refused=refused))
    with pytest.raises(ShapeError) as e:
        await norm("fake", "create", {"text": "x"})
    assert str(e.value) == "No create here (propose)."
    with pytest.raises(ShapeError) as e:
        await norm("fake", "create", {"text": "x"}, mode="fill")
    assert str(e.value) == "No create here (fill)."
    assert seen == [("create", "propose"), ("create", "fill")]


async def test_an_action_the_actions_tuple_itself_rejects_keeps_the_unknown_action_sentence(
    monkeypatch,
) -> None:
    install(monkeypatch, fake_kind(action_refused=lambda a, m: "never"))
    with pytest.raises(ShapeError) as e:
        await norm("fake", "delete", {"text": "x"})
    assert str(e.value).startswith("Unknown action 'delete'")


# --- AC4: operator_only_message ------------------------------------------------------------


async def test_operator_only_message_replaces_the_generic_sentence(monkeypatch) -> None:
    install(monkeypatch, fake_kind(operator_only_message=lambda names: f"Only you set {names}."))
    with pytest.raises(ShapeError) as e:
        await norm("fake", "change", {"text": "x", "secret": "y"})
    assert str(e.value) == "Only you set ['secret']."
    # An unknown key that is not operator-only keeps the generic sentence.
    with pytest.raises(ShapeError) as e:
        await norm("fake", "change", {"bogus": 1})
    assert str(e.value).startswith("fake changes can't include 'bogus'. Allowed fields: text.")


async def test_without_operator_only_message_the_generic_sentence_stands(monkeypatch) -> None:
    install(monkeypatch, fake_kind())
    with pytest.raises(ShapeError) as e:
        await norm("fake", "change", {"secret": "y"})
    assert str(e.value) == "fake changes can't include 'secret'. Allowed fields: text."


# --- AC5: fill_refused through the tool ----------------------------------------------------


async def _fill(**kw) -> str:
    token = current_turn.set(TurnContext(session_id="s1", page=PAGE))
    try:
        return await FillFormTool(agent_name="GleepGlorp").execute(**kw)
    finally:
        current_turn.reset(token)


async def test_fill_refused_answers_with_the_first_named_fields_sentence(monkeypatch) -> None:
    specs = (
        FieldSpec("name", "text", "Name", "name", fill_refused="Name is not fillable."),
        FieldSpec("type", "text", "Type", "type", fill_refused="Type is not fillable."),
        FieldSpec("url", "text", "Address", "url"),
    )
    monkeypatch.setitem(kinds.SPECS, "mcp_server", specs)
    reply = await _fill(
        kind="mcp_server", action="create", changes={"url": "http://x", "type": "t", "name": "n"}
    )
    assert reply == "Type is not fillable."  # the first named key in the call's own order
    reply = await _fill(kind="mcp_server", action="create", changes={"name": "n"})
    assert reply == "Name is not fillable."


async def test_the_notes_refusal_is_the_agent_fields_sentence() -> None:
    spec = next(f for f in agent.AGENT_FIELDS if f.name == "notes_enabled")
    assert spec.fill_refused == NO_NOTES
    assert await _fill(kind="agent", action="create", changes={"notes_enabled": True}) == NO_NOTES
    assert [f.name for k in kinds.REGISTRY for f in k.fields if f.fill_refused] == ["notes_enabled"]


# --- AC6: keyerror_is_gone -----------------------------------------------------------------


async def test_a_key_error_is_gone_only_for_a_kind_that_says_so(monkeypatch) -> None:
    install(monkeypatch, fake_kind(keyerror_is_gone=False))
    exc = KeyError("x")
    p = _p("fake", "change")
    assert await translate(exc, p, conn=None, zone=_utc) is exc  # type: ignore[arg-type]
    install(monkeypatch, fake_kind(keyerror_is_gone=True))
    err = await translate(exc, p, conn=None, zone=_utc)  # type: ignore[arg-type]
    assert isinstance(err, ApplyError) and err.gone


async def test_the_foreign_key_clause_reads_the_addressing(monkeypatch) -> None:
    exc = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
    install(monkeypatch, fake_kind(addressing="agent-owned"))
    err = await translate(exc, _p("fake", "create"), conn=None, zone=_utc)  # type: ignore[arg-type]
    assert isinstance(err, ApplyError) and err.gone
    # A change, or any other addressing, is not a missing agent.
    assert await translate(exc, _p("fake", "change"), conn=None, zone=_utc) is exc  # type: ignore[arg-type]
    install(monkeypatch, fake_kind(addressing="agent"))
    assert await translate(exc, _p("fake", "create"), conn=None, zone=_utc) is exc  # type: ignore[arg-type]


# --- target_args reads the addressing ------------------------------------------------------


def test_target_args_reads_the_addressing_for_page_and_unknown_kinds(monkeypatch) -> None:
    install(monkeypatch, fake_kind(addressing="page"))
    with pytest.raises(ShapeError, match="App settings take no agent or target"):
        kinds.target_args("fake", "wide", None, None, None)
    with pytest.raises(ShapeError, match="App settings take no agent or target"):
        kinds.target_args("fake", None, None, None, "t")
    assert kinds.target_args("fake")["agent"] is None
    # An unknown kind passes through; normalize refuses it later.
    assert kinds.target_args("nope", "a", None, None, "t")["target"] == "t"
    with pytest.raises(ShapeError, match="An MCP server is named with target, not agent."):
        kinds.target_args("mcp_server", "a")


# --- AC7: stored_get / stored_set ----------------------------------------------------------


def test_stored_get_and_set_on_a_flat_field() -> None:
    spec = FieldSpec("name", "text", "Name", "name")
    obj = {"name": "a", "other": {"k": 1}}
    assert stored_get(spec, obj) == "a"
    out = stored_set(spec, obj, "b")
    assert out == {"name": "b", "other": {"k": 1}}
    assert obj["name"] == "a"  # the input is not mutated
    assert out["other"] is obj["other"]  # a sibling is shared, not copied
    with pytest.raises(KeyError):
        stored_get(spec, {})


def test_stored_get_and_set_on_a_nested_path() -> None:
    spec = FieldSpec("num_ctx", "integer", "Context", "num_ctx", path=("config", "num_ctx"))
    cfg = {"num_ctx": 1, "other": 2}
    obj = {"name": "p", "config": cfg, "extra": {"x": 1}}
    assert stored_get(spec, obj) == 1
    out = stored_set(spec, obj, 99)
    assert out == {"name": "p", "config": {"num_ctx": 99, "other": 2}, "extra": {"x": 1}}
    assert cfg == {"num_ctx": 1, "other": 2} and obj["config"] is cfg  # not mutated
    assert out["config"] is not cfg  # the walked level is a copy
    assert out["extra"] is obj["extra"]  # an untouched sibling is shared
    assert stored_get(spec, out) == 99


def test_stored_set_creates_a_missing_intermediate_level_and_get_raises() -> None:
    spec = FieldSpec("a", "text", "A", "a", path=("one", "two", "three"))
    obj = {"keep": 1}
    out = stored_set(spec, obj, "v")
    assert out == {"keep": 1, "one": {"two": {"three": "v"}}}
    assert obj == {"keep": 1}
    assert stored_get(spec, out) == "v"
    with pytest.raises(KeyError):
        stored_get(spec, obj)
    # A non-dict intermediate value is replaced, not written through.
    assert stored_set(spec, {"one": 5}, "v") == {"one": {"two": {"three": "v"}}}

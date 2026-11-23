"""Provider fills (M36 F4 L5b, DD10): what a fill may carry, the view's ``clears_key`` (a key
never follows a provider to another service), the fill-time warnings and ``stale``.

Credential-bearing: a fill carries no key, and the view says when the editor must empty its
key field.
"""

# ruff: noqa: F811
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from tests.test_gleepglorp_kind_provider import (  # noqa: F401
    LOCAL,
    OAI,
    PLAN,
    TOKEN,
    frames,
    norm,
    refused,
    world,
)
from the_one.agent._context import TurnContext, current_turn
from the_one.gleepglorp import kinds
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository, NewFill, fill_view
from the_one.gleepglorp.fill.tool import FillFormTool
from the_one.gleepglorp.kinds import provider

PAGE = {"line": "Library › Model providers", "descriptor": {"destination": "library"}}


async def make_fill(world, action, changes, target=None, *, session="s1") -> int:
    n = await norm(world, action, changes, target, mode="fill")
    new_id, _ = await GleepGlorpFillRepository(world.conn).insert(
        NewFill(
            session_id=session,
            kind="provider",
            action=n.action,
            agent_name=None,
            target_key=n.target_key,
            changes=n.changes,
            target_id=n.target_id,
            base=n.base,
        )
    )
    return new_id


async def view_of(world, fill_id):
    repo = GleepGlorpFillRepository(world.conn)
    return await fill_view(world.conn, await repo.get(fill_id))


# --- what a fill may carry (AC1) --------------------------------------------------------------


async def test_fill_mode_allows_key_taking_changes_and_the_token_type_proposals_do_not(
    world,
) -> None:
    n = await norm(world, "change", {"type": "anthropic"}, OAI, mode="fill")
    assert n.changes == {"type": "anthropic"}
    n = await norm(world, "create", {"name": "T", "type": "anthropic-plan-token"}, mode="fill")
    assert n.changes["type"] == "anthropic-plan-token"
    assert "key can't follow" in await refused(world, "change", {"type": "anthropic"}, OAI)
    assert "setup-token" in await refused(
        world, "create", {"name": "T", "type": "anthropic-plan-token"}
    )


@pytest.mark.parametrize("mode", ["propose", "fill"])
@pytest.mark.parametrize("key", ["api_key", "secrets"])
async def test_no_mode_carries_a_key_or_secrets(world, mode, key) -> None:
    msg = await refused(world, "change", {key: "x"}, OAI, mode=mode)
    assert key in msg


@pytest.mark.parametrize("mode", ["propose", "fill"])
async def test_no_mode_creates_or_changes_to_mock(world, mode) -> None:
    assert "mock" in await refused(world, "create", {"name": "M", "type": "mock"}, mode=mode)
    assert "mock" in await refused(world, "change", {"type": "mock"}, OAI, mode=mode)


def test_the_kind_is_fillable_for_create_and_change() -> None:
    assert provider.KIND.fillable == ("create", "change")
    assert "provider" in kinds.FILLABLE


# --- clears_key (AC1, AC4) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "target,changes,expected",
    [
        # key-taking to a different key-taking type: the old key must not reach the new service
        (OAI, {"type": "anthropic"}, True),
        (OAI, {"type": "openrouter"}, True),
        (TOKEN, {"type": "anthropic"}, True),
        # key-taking to a type with no key row: the key is cleared (decision 2)
        (OAI, {"type": "ollama", "base_url": "http://localhost:11434/v1"}, True),
        (OAI, {"type": "anthropic-plan"}, True),
        # keyless into key-taking: there is no key to clear
        (LOCAL, {"type": "openai"}, False),
        (PLAN, {"type": "anthropic"}, False),
        # the same type, or no type: the key stays
        (OAI, {"name": "Renamed"}, False),
        (OAI, {"reasoning_effort": "high"}, False),
        (OAI, {"type": "openai", "reasoning_effort": "low"}, False),
    ],
)
async def test_clears_key_is_set_exactly_when_the_key_must_not_follow(
    world, target, changes, expected
) -> None:
    fid = await make_fill(world, "change", changes, target)
    assert (await view_of(world, fid))["clears_key"] is expected


async def test_a_create_never_clears_a_key(world) -> None:
    fid = await make_fill(world, "create", {"name": "N", "type": "anthropic"})
    assert (await view_of(world, fid))["clears_key"] is False


async def test_the_view_never_carries_a_key(world) -> None:
    fid = await make_fill(world, "change", {"type": "anthropic"}, OAI)
    text = json.dumps(await view_of(world, fid))
    assert "api_key" not in text and "secrets" not in text


# --- the view: title, target_gone, stale, warnings (AC1, resolution 6 and 9) -------------------


async def test_the_view_has_the_title_and_target_gone(world) -> None:
    fid = await make_fill(world, "change", {"name": "Fresh"}, OAI)
    v = await view_of(world, fid)
    assert v["title"] == "Change model provider “OpenAI main”" and v["target_gone"] is False
    assert v["target_id"] == OAI and v["agent_name"] is None
    assert v["labels"]["thinking_enabled"] == "Extended thinking"
    await world.conn.execute("DELETE FROM llm_providers WHERE id = ?", (OAI,))
    await world.conn.commit()
    assert (await view_of(world, fid))["target_gone"] is True


async def test_stale_lists_the_labelled_fields_that_moved(world) -> None:
    fid = await make_fill(world, "change", {"name": "Fresh"}, OAI)
    assert (await view_of(world, fid))["stale"] == []
    cfg = await world.deps.provider_repo.get(OAI)
    await world.deps.provider_repo.update(cfg.model_copy(update={"name": "Moved"}))
    [row] = (await view_of(world, fid))["stale"]
    assert row == {"field": "name", "label": "Name", "current": "Moved", "proposed": "Fresh"}


async def test_the_view_carries_fill_time_warnings_for_a_pending_fill_only(world) -> None:
    fid = await make_fill(world, "change", {"type": "ollama"}, OAI)
    v = await view_of(world, fid)
    assert provider.WARN_KEY_CLEARED in v["warnings"]
    assert any(w.startswith("1 agent uses") for w in v["warnings"])
    repo = GleepGlorpFillRepository(world.conn)
    _fill, token = await repo.claim(fid, datetime.now(UTC))
    await repo.record_outcome(fid, token, "filled", [], None)
    assert (await view_of(world, fid))["warnings"] == []


@pytest.mark.parametrize(
    "action,changes,target,expected",
    [
        ("create", {"name": "N", "type": "anthropic"}, None, provider.WARN_FILL_KEY_NEEDED),
        ("create", {"name": "N", "type": "anthropic-plan"}, None, provider.WARN_FILL_SIGN_IN),
        (
            "change",
            {"type": "anthropic-plan"},
            OAI,
            provider.WARN_FILL_KEY_CLEARED_SIGN_IN,
        ),
    ],
)
async def test_a_fill_view_says_this_page_and_saving_never_approving(
    world, action, changes, target, expected
) -> None:
    fid = await make_fill(world, action, changes, target)
    warnings = (await view_of(world, fid))["warnings"]
    assert expected in warnings
    assert not any("approv" in w.lower() for w in warnings), warnings


def test_the_fill_wordings_are_the_ones_the_leg_fixed() -> None:
    assert provider.WARN_FILL_KEY_NEEDED == "Enter its API key on this page."
    assert provider.WARN_FILL_SIGN_IN == "Sign in on this page after saving."
    assert provider.WARN_FILL_KEY_CLEARED_SIGN_IN == (
        "The stored key is cleared; sign in on this page after saving."
    )


async def test_a_proposal_warning_keeps_its_approval_wording(world) -> None:
    from the_one.gleepglorp.proposals.store import NewProposal  # noqa: F401

    n = await norm(world, "create", {"name": "N", "type": "anthropic"})
    p = type("P", (), {"action": n.action, "changes": n.changes, "target_id": n.target_id})()
    assert await provider.warnings(world.conn, None, p) == [provider.WARN_KEY_NEEDED]
    assert await provider.warnings(world.conn, None, p, mode="fill") == [
        provider.WARN_FILL_KEY_NEEDED
    ]
    assert "approving" in provider.WARN_KEY_NEEDED


async def test_no_fill_reply_contains_approv(world, monkeypatch) -> None:
    """The tool reply the model reads (it relays it to the operator) never says "approving":
    a fill is saved by the operator on the page."""

    async def capture(session_id, payload, **_kw):
        pass

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", capture)
    tool = FillFormTool(agent_name="GleepGlorp")
    token = current_turn.set(TurnContext(session_id="s7", page=PAGE))
    try:
        replies = [
            await tool.execute(
                kind="provider", action="create", changes={"name": "K", "type": "anthropic"}
            ),
            await tool.execute(
                kind="provider", action="create", changes={"name": "P", "type": "anthropic-plan"}
            ),
            await tool.execute(
                kind="provider",
                action="change",
                target="OpenAI main",
                changes={"type": "anthropic-plan"},
            ),
        ]
    finally:
        current_turn.reset(token)
    assert provider.WARN_FILL_KEY_NEEDED in replies[0]
    assert provider.WARN_FILL_SIGN_IN in replies[1]
    assert provider.WARN_FILL_KEY_CLEARED_SIGN_IN in replies[2]
    for reply in replies:
        assert "approv" not in reply.lower(), reply


async def test_the_tool_reply_appends_the_warnings(world, monkeypatch) -> None:
    async def capture(session_id, payload, **_kw):
        pass

    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_session", capture)
    tool = FillFormTool(agent_name="GleepGlorp")
    token = current_turn.set(TurnContext(session_id="s1", page=PAGE))
    try:
        out = await tool.execute(
            kind="provider", action="change", target="Claude plan", changes={"type": "anthropic"}
        )
        plain = await tool.execute(
            kind="provider", action="change", target="Local", changes={"name": "Local 2"}
        )
    finally:
        current_turn.reset(token)
    assert "model provider editor" in out
    assert provider.WARN_SIGNS_OUT in out and provider.WARN_GLEEPGLORP in out
    assert "Tell the operator" not in plain
    [first, second] = await GleepGlorpFillRepository(world.conn).list_for_session("s1")
    assert first.kind == "provider" and first.target_id == PLAN
    assert second.status == "sent" and first.status == "replaced"


async def test_an_mcp_fill_carries_fill_time_warnings_too(world) -> None:
    """DD9's fill warnings for the MCP kind (not wired in Leg 4b)."""
    from the_one.gleepglorp.kinds import mcp_server

    assert mcp_server.KIND.warnings is not None
    repo = GleepGlorpFillRepository(world.conn)
    sources = await world.deps.mcp_repo.list()
    stdio = next((s for s in sources if s.type == "stdio" and s.secrets), None)
    if stdio is None:
        pytest.skip("no stdio source with secrets in the seed")
    fid, _ = await repo.insert(
        NewFill(
            session_id="s9",
            kind="mcp_server",
            action="change",
            agent_name=None,
            target_key=f"mcp_server:{stdio.id}",
            changes={"command": "other-cmd"},
            target_id=stdio.id,
            base={"command": (stdio.config or {}).get("command")},
        )
    )
    v = await fill_view(world.conn, await repo.get(fid))
    assert mcp_server.WARN_COMMAND in v["warnings"]

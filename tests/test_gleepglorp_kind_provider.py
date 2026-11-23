"""The ``provider`` kind (Mission 36 F4 L5a, DD10): normalize, the type-change rules, the
card and its warnings, approve through the provider write service, the outside-value guard on
``base_url`` and the defaults table's pin to the client.

Credential-bearing: a proposal never holds, carries or follows a key.
"""

# ruff: noqa: N802
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._gleepglorp_seed import SEEDS, seed
from the_one.agent._context import TurnContext, current_tool_call_id, current_turn
from the_one.agent.service import AgentWriteDeps
from the_one.db import _write_lock
from the_one.db._provider_types import (
    CLAUDE_PROVIDER_TYPES,
    PROVIDER_TYPE_DEFAULTS,
    PROVIDER_TYPES,
)
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import (
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.gleepglorp import kinds, outside
from the_one.gleepglorp.kinds import provider
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals.shape import ShapeError
from the_one.gleepglorp.proposals.store import (
    GleepGlorpProposalRepository,
    NewProposal,
    proposal_view,
)
from the_one.gleepglorp.proposals.tool import ProposeChangeTool
from the_one.llm.base import Message, ToolCall, ToolResult

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
OAI = "p-openai"  # "OpenAI main": a stored key, a decoy config key, used by the agent "wide"
PLAN = "p-plan"  # "Claude plan": signed in; GleepGlorp's own provider
TOKEN = "p-token"  # "Claude token": a stored setup token and its stamp
LOCAL = "p-local"  # "Local": ollama, no key; used by the agent "plain"


async def _utc():
    return UTC


@pytest.fixture
async def world(tmp_path, monkeypatch):
    _write_lock.reset_for_test()
    ns = await seed(tmp_path)
    conn, enc = ns.conn, ns.enc

    async def _conn():
        return conn

    from the_one.config import settings

    monkeypatch.setattr("the_one.db.connection.get_connection", _conn)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    ns.deps = AgentWriteDeps(
        store=SQLiteAgentStore(conn, enc),
        mcp_repo=MCPSourceRepository(conn, enc),
        provider_repo=LLMProviderRepository(conn, enc),
        secret_repo=SecretRepository(conn, enc),
        tool_config_repo=ToolConfigRepository(conn, enc),
    )
    ns.repo = GleepGlorpProposalRepository(conn)
    yield ns
    await conn.close()


@pytest.fixture
def frames(monkeypatch):
    out = SimpleNamespace(proposal=[], config=[])

    async def push(session_id, view):
        out.proposal.append((session_id, view["status"]))

    async def broadcast(payload):
        out.config.append(payload)

    monkeypatch.setattr(proposal_apply, "push_proposal_changed", push)
    monkeypatch.setattr("the_one.sessions._broadcast.broadcast_to_all", broadcast)
    return out


async def norm(world, action, changes, target=None, *, mode="propose"):
    return await kinds.normalize(
        "provider",
        action,
        kinds.target_args("provider", None, None, None, target),
        changes,
        conn=world.conn,
        now=NOW,
        zone=UTC,
        enc=world.enc,
        mode=mode,
    )


async def refused(world, action, changes, target=None, *, mode="propose") -> str:
    with pytest.raises(ShapeError) as e:
        await norm(world, action, changes, target, mode=mode)
    return str(e.value)


async def make(world, action, changes, target=None, *, session="s1") -> int:
    n = await norm(world, action, changes, target)
    return await world.repo.insert(
        NewProposal(
            session_id=session,
            kind=n.kind,
            action=n.action,
            agent_name=n.agent_name,
            target_key=n.target_key,
            changes=n.changes,
            target_id=n.target_id,
            base=n.base,
        )
    )


async def run(world, pid, *, override=False):
    return await proposal_apply.apply_proposal(
        world.conn, world.deps, pid, override=override, now=NOW, zone=_utc
    )


async def view_of(world, pid):
    return await proposal_view(world.conn, await world.repo.get(pid))


async def stored(world, provider_id) -> LLMProviderConfig:
    return await world.deps.provider_repo.get(provider_id)


# --- registered, described, pinned to the client ----------------------------------------------


def test_the_kind_is_registered_last_described_and_fillable() -> None:
    assert kinds.REGISTRY[4] is provider.KIND and kinds.KINDS[4] == "provider"
    assert provider.KIND.fillable == ("create", "change") and "provider" in kinds.FILLABLE
    assert provider.KIND.operator_only == ("api_key", "secrets")
    assert provider.KIND.relaxed_guard_keys == frozenset({"base_url"})
    by = {f["name"]: f for f in kinds.describe("provider")["fields"]}
    assert list(by) == [
        "name",
        "type",
        "base_url",
        "num_ctx",
        "thinking_enabled",
        "reasoning_effort",
    ]
    assert by["name"]["required_on_create"] is True and by["type"]["required_on_create"] is True
    assert "create_only" not in by["type"]  # a type change is allowed, with a warning
    assert by["base_url"]["provenance"] == "must come from you or a page you linked"
    assert by["num_ctx"]["min"] == 1
    # A user's words map to the type: the subscription is anthropic-plan, not the API-key type.
    hint = by["type"]["hint"]
    assert "anthropic-plan (Claude Plan (OAuth); Claude Pro/Max subscription: sign in" in hint
    assert "anthropic (Anthropic; Claude with an API key)" in hint
    assert "mock" not in hint
    assert "anthropic-plan-token (" in hint and "setup token" in hint
    assert "the operator enters a key or signs in on the page" in hint
    assert "Changing between types that take a key is refused" in hint
    assert "api_key" not in by and "secrets" not in by
    assert {e["name"] for e in kinds.describe()} >= {"provider"}


def _client_type_defaults() -> dict[str, dict[str, bool | str]]:
    src = (ROOT / "the_one/interfaces/web/static/js/areas/studio/providers-section.js").read_text()
    start = src.index("var TYPE_DEFAULTS")
    block = src[start : src.index("};", start) + 2]
    out: dict[str, dict[str, bool | str]] = {}
    for m in re.finditer(r"^\s*'([a-z-]+)':\s*\{(.*)\}[,]?\s*$", block, flags=re.M):
        entry: dict[str, bool | str] = {}
        body = m.group(2)
        url = re.search(r"base_url:\s*'([^']*)'", body)
        entry["base_url"] = url.group(1) if url else ""
        for flag in re.finditer(r"(show[A-Za-z]+):\s*(true|false)", body):
            entry[flag.group(1)] = flag.group(2) == "true"
        out[m.group(1)] = entry
    return out


def test_the_defaults_table_equals_the_clients_type_defaults() -> None:
    client = _client_type_defaults()
    assert set(client) == set(PROVIDER_TYPE_DEFAULTS) == set(PROVIDER_TYPES)
    pairs = {
        "base_url_shown": "showBaseUrl",
        "shows_api_key": "showApiKey",
        "shows_num_ctx": "showNumCtx",
        "shows_thinking": "showThinkingEnabled",
        "shows_reasoning_effort": "showReasoningEffort",
        "plan_sign_in": "showPlanSignIn",
    }
    for t, server in PROVIDER_TYPE_DEFAULTS.items():
        assert server["base_url"] == client[t]["base_url"], t
        for ours, theirs in pairs.items():
            assert server[ours] is client[t].get(theirs, False), (t, ours)


def test_the_claude_types_are_derived_from_the_table() -> None:
    from the_one.interfaces.web import api

    assert set(CLAUDE_PROVIDER_TYPES) == {"anthropic", "anthropic-plan", "anthropic-plan-token"}
    assert api._CLAUDE_PROVIDER_TYPES == CLAUDE_PROVIDER_TYPES


def test_the_editors_default_context_window_matches_the_service() -> None:
    from the_one.llm import provider_service

    src = (ROOT / "the_one/interfaces/web/static/js/areas/studio/provider-editor.js").read_text()
    assert re.search(r"DEFAULT_NUM_CTX\s*=\s*(\d+)", src).group(1) == str(
        provider_service.DEFAULT_NUM_CTX
    )


# --- normalize: every refusal -----------------------------------------------------------------


@pytest.mark.parametrize("key", ["api_key", "secrets"])
async def test_operator_only_keys_are_refused_by_the_kind_and_the_dispatcher(world, key) -> None:
    with pytest.raises(ShapeError, match="operator"):
        await provider.normalize(
            "change", {"target": OAI}, {key: "x"}, conn=world.conn, now=NOW, zone=UTC, enc=world.enc
        )
    with pytest.raises(ShapeError):
        await norm(world, "change", {key: "x"}, OAI)


async def test_an_unknown_key_is_refused(world) -> None:
    with pytest.raises(ShapeError, match="Allowed fields"):
        await provider.normalize(
            "change", {"target": OAI}, {"colour": "x"}, conn=world.conn, now=NOW, zone=UTC
        )


async def test_mock_is_never_created_changed_or_targeted(world) -> None:
    assert "mock" in await refused(world, "create", {"name": "M", "type": "mock"})
    assert "mock" in await refused(world, "change", {"type": "mock"}, LOCAL)
    await world.deps.provider_repo.create(
        LLMProviderConfig(id="mk", name="Mocky", type="mock", base_url="")
    )
    assert "mock" in await refused(world, "change", {"name": "Other"}, "mk")
    # a fill does not get to either
    assert "mock" in await refused(world, "create", {"name": "M", "type": "mock"}, mode="fill")


async def test_an_unknown_type_is_refused(world) -> None:
    assert "type must be" in await refused(world, "create", {"name": "X", "type": "ftp"})
    assert "type must be" in await refused(world, "change", {"type": 3}, OAI)


async def test_a_new_token_type_and_a_change_into_it_need_the_operator(world) -> None:
    msg = await refused(world, "create", {"name": "T", "type": "anthropic-plan-token"})
    assert "claude setup-token" in msg and "editor" in msg
    assert "claude setup-token" in await refused(
        world, "change", {"type": "anthropic-plan-token"}, LOCAL
    )
    # a fill may name it: the operator pastes the token on the form
    n = await norm(world, "create", {"name": "T", "type": "anthropic-plan-token"}, mode="fill")
    assert n.changes["type"] == "anthropic-plan-token"
    n = await norm(world, "change", {"type": "anthropic-plan-token"}, LOCAL, mode="fill")
    assert n.changes == {"type": "anthropic-plan-token"}


@pytest.mark.parametrize(
    "target,new_type",
    [(OAI, "anthropic"), (OAI, "openrouter"), (TOKEN, "anthropic"), (TOKEN, "openai-compatible")],
)
async def test_key_taking_to_a_different_key_taking_type_is_refused_to_a_proposal(
    world, target, new_type
) -> None:
    changes = {"type": new_type}
    if new_type == "openai-compatible":
        changes["base_url"] = "https://llm.example.com/v1"
    msg = await refused(world, "change", changes, target)
    assert "key can't follow" in msg and "editor" in msg
    # a fill carries it: the client clears the key field (Leg 5b)
    n = await norm(world, "change", changes, target, mode="fill")
    assert n.changes["type"] == new_type


async def test_a_name_or_option_change_on_the_token_type_is_allowed(world) -> None:
    n = await norm(world, "change", {"name": "Token 2", "reasoning_effort": "high"}, TOKEN)
    assert n.changes == {"name": "Token 2", "reasoning_effort": "high"}
    assert n.base == {"name": "Claude token"}  # an option absent now is left out of the base


async def test_a_hidden_address_type_refuses_a_named_base_url_everywhere(world) -> None:
    msg = await refused(
        world, "create", {"name": "A", "type": "anthropic", "base_url": "https://x.test"}
    )
    assert "fixed" in msg
    assert "fixed" in await refused(world, "change", {"base_url": "https://x.test"}, PLAN)
    assert "fixed" in await refused(world, "change", {"base_url": "https://x.test"}, TOKEN)
    assert "fixed" in await refused(
        world, "change", {"type": "anthropic-plan", "base_url": "https://x.test"}, LOCAL
    )


async def test_defaults_fill_the_address_and_openai_compatible_needs_one(world) -> None:
    n = await norm(world, "create", {"name": "Anth", "type": "anthropic"})
    assert n.changes == {
        "name": "Anth",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
    }
    n = await norm(world, "create", {"name": "Router", "type": "openrouter"})
    assert n.changes["base_url"] == "https://openrouter.ai/api/v1"
    n = await norm(
        world,
        "create",
        {"name": "Mine", "type": "ollama", "base_url": "http://gpu:11434/v1", "num_ctx": 8192},
    )
    assert n.changes["base_url"] == "http://gpu:11434/v1" and n.changes["num_ctx"] == 8192
    assert "needs its base_url" in await refused(
        world, "create", {"name": "Compat", "type": "openai-compatible"}
    )
    assert "needs its base_url" in await refused(
        world, "change", {"type": "openai-compatible"}, PLAN
    )
    n = await norm(world, "change", {"type": "ollama"}, OAI)
    assert n.changes == {"type": "ollama"}  # the service fills its default address on approve


async def test_an_address_must_be_http_or_https(world) -> None:
    assert "http or https" in await refused(
        world, "create", {"name": "C", "type": "openai-compatible", "base_url": "ftp://x"}
    )
    assert "must be text" in await refused(world, "change", {"base_url": 4}, LOCAL)


@pytest.mark.parametrize(
    "target,changes,needle",
    [
        (OAI, {"num_ctx": 4096}, "Ollama"),
        (OAI, {"thinking_enabled": True}, "Claude"),
        (LOCAL, {"thinking_enabled": True}, "Claude"),
        (LOCAL, {"num_ctx": 0}, "whole number"),
        (LOCAL, {"num_ctx": True}, "whole number"),
        (LOCAL, {"num_ctx": "4096"}, "whole number"),
        (PLAN, {"thinking_enabled": "yes"}, "true or false"),
        (OAI, {"reasoning_effort": "extreme"}, "low, medium, high"),
        (OAI, {"reasoning_effort": 3}, "text"),
    ],
)
async def test_options_the_type_does_not_show_or_with_bad_values_are_refused(
    world, target, changes, needle
) -> None:
    assert needle in await refused(world, "change", changes, target)


async def test_an_empty_reasoning_effort_is_kept_as_the_editor_writes_it(world) -> None:
    n = await norm(world, "change", {"reasoning_effort": ""}, OAI)
    assert n.changes == {"reasoning_effort": ""}


async def test_a_name_must_be_valid_and_unique(world) -> None:
    assert await refused(world, "create", {"name": "  ", "type": "ollama"})
    assert "already exists" in await refused(world, "create", {"name": "local", "type": "ollama"})
    assert "already exists" in await refused(world, "change", {"name": "OpenAI MAIN"}, LOCAL)
    n = await norm(world, "change", {"name": "Local"}, LOCAL)  # its own name is not a clash
    assert n.changes == {"name": "Local"}


async def test_a_change_needs_a_known_target_and_something_to_change(world) -> None:
    assert "No model provider named" in await refused(world, "change", {"name": "x"}, "nope")
    assert "name or id" in await refused(world, "change", {"name": "x"}, None)
    assert "Nothing to change" in await refused(world, "change", {}, OAI)
    with pytest.raises(ShapeError, match="target, not agent"):
        kinds.target_args("provider", "wide", None, None, None)


async def test_the_target_resolves_id_first_then_a_unique_name(world) -> None:
    assert await provider.resolve_target(world.conn, "Local") == (LOCAL, "Local")
    assert await provider.resolve_target(world.conn, OAI) == (OAI, "OpenAI main")
    # a provider whose NAME is another's id: the id wins
    await world.deps.provider_repo.create(
        LLMProviderConfig(id="zz", name=LOCAL, type="ollama", base_url="http://localhost:11434/v1")
    )
    assert await provider.resolve_target(world.conn, LOCAL) == (LOCAL, "Local")
    # two with one name: refused with each id listed
    await world.deps.provider_repo.create(
        LLMProviderConfig(id="z2", name="Twin", type="ollama", base_url="http://localhost:11434/v1")
    )
    await world.deps.provider_repo.create(
        LLMProviderConfig(id="z3", name="Twin", type="ollama", base_url="http://localhost:11434/v1")
    )
    with pytest.raises(ShapeError, match="z2.*z3|z3.*z2"):
        await provider.resolve_target(world.conn, "Twin")


async def test_the_base_holds_only_the_named_fields_and_never_a_key(world) -> None:
    n = await norm(world, "change", {"name": "OpenAI 2", "reasoning_effort": "low"}, OAI)
    assert n.base == {"name": "OpenAI main"}  # reasoning_effort is absent now
    assert n.agent_name is None and n.target_id == OAI and n.target_key == f"provider:{OAI}"
    blob = repr((n.changes, n.base))
    assert SEEDS["provider_api_key"] not in blob
    n = await norm(world, "create", {"name": "New", "type": "ollama"})
    assert n.target_key == "provider:new:New" and n.base is None and n.target_id is None


# --- the card, its title and its warnings -----------------------------------------------------


async def test_the_card_names_the_provider_by_a_lookup_and_knows_when_it_is_gone(world) -> None:
    pid = await make(world, "create", {"name": "Fresh", "type": "ollama"})
    view = await view_of(world, pid)
    assert view["title"] == "Create model provider “Fresh”" and view["target_gone"] is False
    assert view["agent_name"] is None
    pid = await make(world, "change", {"name": "Renamed"}, LOCAL, session="s2")
    view = await view_of(world, pid)
    assert view["title"] == "Change model provider “Local”" and view["target_gone"] is False
    assert view["target_id"] == LOCAL and "schedule_text" not in view
    await world.deps.provider_repo.delete(LOCAL)  # (no agent FK trouble: ON DELETE SET NULL)
    view = await view_of(world, pid)
    assert view["target_gone"] is True and view["title"].startswith("Change model provider")


async def test_a_plain_change_carries_no_warnings(world) -> None:
    for target, changes in (
        (OAI, {"name": "OpenAI 2"}),
        (OAI, {"reasoning_effort": "high"}),
        (LOCAL, {"num_ctx": 2048}),
        (PLAN, {"thinking_enabled": False}),
    ):
        pid = await make(world, "change", changes, target, session=f"s-{target}")
        assert (await view_of(world, pid))["warnings"] == [], (target, changes)


async def test_creating_a_key_taking_type_warns_to_enter_the_key_and_plan_to_sign_in(world) -> None:
    pid = await make(world, "create", {"name": "Anth", "type": "anthropic"})
    assert (await view_of(world, pid))["warnings"] == [provider.WARN_KEY_NEEDED]
    pid = await make(world, "create", {"name": "Plan", "type": "anthropic-plan"}, session="s2")
    assert (await view_of(world, pid))["warnings"] == [provider.WARN_SIGN_IN]
    pid = await make(world, "create", {"name": "Loc", "type": "ollama"}, session="s3")
    assert (await view_of(world, pid))["warnings"] == []


async def test_a_type_change_warns_for_each_effect_the_agents_and_gleepglorp(world) -> None:
    # into ollama: the stored key is cleared; "wide" uses OpenAI main
    pid = await make(world, "change", {"type": "ollama"}, OAI)
    assert (await view_of(world, pid))["warnings"] == [
        provider.WARN_KEY_CLEARED,
        "1 agent uses this provider; its model name stays as it is.",
    ]
    # out of the plan type (GleepGlorp's own provider), into a key-taking type
    pid = await make(world, "change", {"type": "anthropic"}, PLAN, session="s2")
    assert (await view_of(world, pid))["warnings"] == [
        provider.WARN_SIGNS_OUT,
        provider.WARN_KEY_NEEDED,
        provider.WARN_GLEEPGLORP,
    ]
    # into the plan type from a keyless provider: sign in; from a key-taking one: key cleared
    pid = await make(world, "change", {"type": "anthropic-plan"}, LOCAL, session="s3")
    warns = (await view_of(world, pid))["warnings"]
    assert warns[0] == provider.WARN_SIGN_IN and "1 agent uses" in warns[1]
    pid = await make(world, "change", {"type": "anthropic-plan"}, OAI, session="s4")
    assert (await view_of(world, pid))["warnings"][0] == provider.WARN_KEY_CLEARED_SIGN_IN
    # keyless to key-taking
    pid = await make(world, "change", {"type": "openai"}, LOCAL, session="s5")
    assert provider.WARN_KEY_NEEDED in (await view_of(world, pid))["warnings"]
    # several agents
    store = world.deps.store
    for name in ("extra1", "extra2"):
        cfg = await store.load("plain")
        await store.save(cfg.model_copy(update={"name": name}))
    pid = await make(world, "change", {"type": "openai"}, LOCAL, session="s6")
    assert any(
        w.startswith("3 agents use this provider") for w in (await view_of(world, pid))["warnings"]
    )


async def test_moving_the_address_of_a_provider_with_a_key_warns_the_key_goes_there(world) -> None:
    await world.deps.provider_repo.create(
        LLMProviderConfig(
            id="oc",
            name="Compat",
            type="openai-compatible",
            base_url="https://llm.example.com/v1",
            api_key="sk-compat-key-12345678",
        )
    )
    pid = await make(world, "change", {"base_url": "https://other.example.com/v1"}, "oc")
    assert (await view_of(world, pid))["warnings"] == [provider.WARN_URL_MOVES_KEY]
    # no key stored: no warning
    await world.deps.provider_repo.update_in_txn(
        "oc", lambda c: c.model_copy(update={"api_key": None})
    )
    pid = await make(
        world, "change", {"base_url": "https://third.example.com/v1"}, "oc", session="s2"
    )
    assert (await view_of(world, pid))["warnings"] == []


async def test_a_closed_card_carries_no_warnings(world, frames) -> None:
    pid = await make(world, "change", {"type": "ollama"}, OAI)
    assert (await view_of(world, pid))["warnings"]
    assert (await run(world, pid)).outcome == "applied"
    assert (await view_of(world, pid))["warnings"] == []


# --- approve ------------------------------------------------------------------------------


async def test_a_create_applies_through_the_service_with_the_pregenerated_id(world, frames) -> None:
    pid = await make(world, "create", {"name": "Anth", "type": "anthropic"})
    res = await run(world, pid)
    assert res.outcome == "applied"
    row = await world.repo.get(pid)
    new_id = row.result["target_id"]
    assert len(new_id) == 12 and row.result["summary"] == "Created provider Anth"
    p = await stored(world, new_id)
    assert (p.name, p.type, p.base_url) == ("Anth", "anthropic", "https://api.anthropic.com")
    assert p.api_key is None and p.secrets == {}
    assert p.config == {"thinking_enabled": True}  # a new Claude provider starts with thinking on
    [frame] = frames.config
    assert frame["kind"] == "provider" and frame["agent"] is None
    assert frame["target_id"] == new_id and frame["fields"] == ["name", "type", "base_url"]
    assert res.view["target_id"] == new_id == (await view_of(world, pid))["target_id"]


async def test_a_created_ollama_is_seeded_with_the_editors_context_window(world, frames) -> None:
    pid = await make(world, "create", {"name": "Loc2", "type": "ollama"})
    assert (await run(world, pid)).outcome == "applied"
    new_id = (await world.repo.get(pid)).result["target_id"]
    p = await stored(world, new_id)
    assert p.base_url == "http://localhost:11434/v1" and p.config == {"num_ctx": 32768}


async def test_a_plain_change_keeps_the_key_the_other_config_and_updates_the_card(
    world, frames
) -> None:
    before = await stored(world, OAI)
    pid = await make(world, "change", {"name": "OpenAI 2", "reasoning_effort": "high"}, OAI)
    res = await run(world, pid)
    assert res.outcome == "applied"
    after = await stored(world, OAI)
    assert after.name == "OpenAI 2" and after.api_key == before.api_key
    assert after.base_url == before.base_url
    assert after.config == {**before.config, "reasoning_effort": "high"}  # per key
    [frame] = frames.config
    assert frame["kind"] == "provider" and frame["agent"] is None and frame["target_id"] == OAI
    assert (await world.repo.get(pid)).result["summary"] == (
        "Changed Name, Reasoning effort on provider OpenAI main"
    )
    assert res.view["title"] == "Change model provider “OpenAI 2”"


async def test_a_change_into_ollama_clears_the_key_and_seeds_the_options(world, frames) -> None:
    pid = await make(world, "change", {"type": "ollama"}, OAI)
    assert (await run(world, pid)).outcome == "applied"
    p = await stored(world, OAI)
    assert p.type == "ollama" and p.api_key is None
    assert p.base_url == "http://localhost:11434/v1" and p.config["num_ctx"] == 32768
    assert SEEDS["provider_api_key"] not in repr(await world.repo.get(pid))


async def test_a_change_out_of_the_plan_type_drops_the_sign_in_into_it_clears_the_key(
    world, frames
) -> None:
    pid = await make(world, "change", {"type": "ollama"}, PLAN)
    assert (await run(world, pid)).outcome == "applied"
    p = await stored(world, PLAN)
    assert p.type == "ollama" and p.secrets == {}
    pid = await make(world, "change", {"type": "anthropic-plan"}, OAI, session="s2")
    assert (await run(world, pid)).outcome == "applied"
    p = await stored(world, OAI)
    assert p.type == "anthropic-plan" and p.api_key is None and p.secrets == {}
    assert p.base_url == "https://api.anthropic.com" and p.config["thinking_enabled"] is True


async def test_a_name_change_on_the_token_type_keeps_the_token_and_its_stamp(world, frames) -> None:
    before = await stored(world, TOKEN)
    pid = await make(world, "change", {"name": "Token 2"}, TOKEN)
    assert (await run(world, pid)).outcome == "applied"
    p = await stored(world, TOKEN)
    assert p.api_key == before.api_key and p.secrets == before.secrets and p.name == "Token 2"


async def test_the_service_refuses_a_key_taking_change_that_slipped_past_the_proposal(
    world, frames
) -> None:
    """A defence: the approve runs after the stale window, so the service refuses by itself."""
    pid = await make(world, "change", {"name": "Renamed"}, OAI)
    # forge a stored change the normalizer would have refused
    await world.conn.execute(
        "UPDATE gleepglorp_proposals SET changes = ? WHERE id = ?",
        ('{"type": "anthropic"}', pid),
    )
    await world.conn.commit()
    res = await run(world, pid, override=True)
    assert res.outcome == "failed"
    assert "key can't follow" in res.view["result"]["errors"][0]["msg"]
    p = await stored(world, OAI)
    assert p.type == "openai" and p.api_key == SEEDS["provider_api_key"]


async def test_a_stale_change_gives_the_rows_and_override_applies(world, frames) -> None:
    pid = await make(world, "change", {"name": "Mine", "reasoning_effort": "low"}, OAI)
    await world.deps.provider_repo.update_in_txn(
        OAI,
        lambda cur: cur.model_copy(
            update={"name": "Hand-edited", "config": {**cur.config, "reasoning_effort": "high"}}
        ),
    )
    res = await run(world, pid)
    assert res.outcome == "stale"
    by = {r["field"]: r for r in res.stale}
    assert by["name"] == {
        "field": "name",
        "label": "Name",
        "current": "Hand-edited",
        "proposed": "Mine",
    }
    assert by["reasoning_effort"]["current"] == "high"
    assert (await world.repo.get(pid)).status == "pending"
    assert (await stored(world, OAI)).name == "Hand-edited"
    assert (await run(world, pid, override=True)).outcome == "applied"
    assert (await stored(world, OAI)).name == "Mine"


async def test_a_deleted_target_withdraws_the_proposal(world, frames) -> None:
    pid = await make(world, "change", {"name": "Renamed"}, LOCAL)
    await world.deps.provider_repo.delete(LOCAL)
    res = await run(world, pid)
    assert res.outcome == "gone" and (await world.repo.get(pid)).status == "withdrawn"
    assert frames.config == []


async def test_a_failure_carries_the_services_items_and_writes_nothing(world, frames) -> None:
    # proposed against an address that is then made unsafe for the stored type
    await world.deps.provider_repo.create(
        LLMProviderConfig(
            id="oc",
            name="Compat",
            type="openai-compatible",
            base_url="https://llm.example.com/v1",
            api_key="sk-compat-key-12345678",
        )
    )
    pid = await make(world, "change", {"base_url": "http://example.com/v1"}, "oc")
    res = await run(world, pid)
    assert res.outcome == "failed" and res.view["status"] == "failed"
    [err] = res.view["result"]["errors"]
    assert "cleartext" in err["msg"]
    p = await stored(world, "oc")
    assert p.base_url == "https://llm.example.com/v1" and p.api_key == "sk-compat-key-12345678"
    assert frames.config == []


async def test_a_refresh_written_before_the_approval_is_kept(world, frames) -> None:
    pid = await make(world, "change", {"name": "Plan 2"}, PLAN)
    await world.deps.provider_repo.update_secrets(
        PLAN, {"access_token": "fresh-a", "refresh_token": "fresh-r"}
    )
    assert (await run(world, pid)).outcome == "applied"
    assert (await stored(world, PLAN)).secrets["refresh_token"] == "fresh-r"


# --- the read view --------------------------------------------------------------------------


async def test_the_detail_view_shows_the_options_and_whether_a_key_is_stored_never_the_key(
    world,
) -> None:
    from the_one.gleepglorp import views

    await world.deps.provider_repo.update_in_txn(
        OAI, lambda c: c.model_copy(update={"config": {**c.config, "reasoning_effort": ""}})
    )
    detail = await views.read(world.conn, world.enc, "providers", "OpenAI main")
    detail = detail[0] if isinstance(detail, tuple) else detail
    assert detail["options"] == {"reasoning_effort": ""}  # the decoy config key is not an option
    assert detail["key_stored"] is True and detail["id"] == OAI
    local = await views.read(world.conn, world.enc, "providers", "Local")
    local = local[0] if isinstance(local, tuple) else local
    assert local["options"] == {} and local["key_stored"] is False
    blob = repr((detail, local))
    assert SEEDS["provider_api_key"] not in blob and SEEDS["provider_config_decoy"] not in blob


# --- the outside-value guard on base_url (DD7 per kind), through the real propose_change ----------


def U(text) -> Message:
    return Message.user(text)


def A(*calls) -> Message:
    return Message.assistant(
        "", tool_calls=[ToolCall(id=i, name=n, arguments=a) for i, n, a in calls]
    )


def T(cid, content) -> Message:
    return Message.tool(ToolResult(tool_call_id=cid, content=content))


PAGE_URL = "https://docs.acme.test/models"
README = "[200]\n# Acme models\nThe hosted endpoint is https://llm.acme.test/v1\n"
UUID_URL = "https://llm.acme.test/v1/0b3e1f6a-1b2c-4d5e-8f90-123456789abc"


def linked_history() -> list[Message]:
    return [
        U(f"add the acme provider from {PAGE_URL}"),
        A(("f1", "fetch_url", {"url": PAGE_URL})),
        T("f1", README),
    ]


def unlinked_history() -> list[Message]:
    return [U("add a provider"), A(("f1", "fetch_url", {"url": PAGE_URL})), T("f1", README)]


async def propose(world, history, args):
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    tool.bind_agent(SimpleNamespace(messages=[*history, A(("c1", "propose_change", args))]))
    token = current_turn.set(TurnContext(session_id="s1"))
    ctoken = current_tool_call_id.set("c1")
    try:
        return await tool.execute(**args)
    finally:
        current_tool_call_id.reset(ctoken)
        current_turn.reset(token)


def create_call(url=None, *, type="openai-compatible", name="Acme") -> dict:
    changes = {"name": name, "type": type}
    if url is not None:
        changes["base_url"] = url
    return {"kind": "provider", "action": "create", "changes": changes}


async def recorded(world):
    return await world.repo.list_for_session("s1")


async def test_a_url_from_a_linked_page_is_allowed_and_flagged(world) -> None:
    out = await propose(world, linked_history(), create_call("https://llm.acme.test/v1"))
    assert out.startswith("Proposal "), out
    [row] = await recorded(world)
    assert row.untrusted is True and row.agent_name is None


async def test_a_url_from_an_unlinked_page_is_refused(world) -> None:
    out = await propose(world, unlinked_history(), create_call("https://llm.acme.test/v1"))
    assert "Nothing was recorded" in out and "Address" in out
    assert await recorded(world) == []


async def test_a_type_default_address_needs_no_source(world) -> None:
    # no link at all: the address is the app's own (an unlinked fetch makes the turn untrusted)
    out = await propose(world, unlinked_history(), create_call(None, type="ollama"))
    assert out.startswith("Proposal "), out
    out = await propose(
        world,
        unlinked_history(),
        {
            "kind": "provider",
            "action": "change",
            "target": OAI,
            "changes": {"type": "ollama", "base_url": "http://localhost:11434/v1"},
        },
    )
    assert out.startswith("Proposal "), out  # a default of ANY type is exempt, named or not


async def test_a_default_address_with_a_path_or_user_info_is_still_guarded(world) -> None:
    for url in (
        "http://localhost:11434/v1/extra",
        "http://api.anthropic.com@evil.example.com/v1",
        "http://localhost:11434/v1?x=1",
    ):
        out = await propose(world, unlinked_history(), create_call(url, type="ollama"))
        assert "Nothing was recorded" in out, url
    assert await recorded(world) == []


async def test_the_guard_passes_a_base_url_with_a_uuid_path(world) -> None:
    out = await propose(world, [U(f"use {UUID_URL}")], create_call(UUID_URL))
    assert out.startswith("Proposal "), out


async def test_the_guard_relaxes_a_long_id_in_the_base_url_path_but_not_a_key(world) -> None:
    """A long hex id in a deployment path is not a key (the hex-run rule is relaxed for the
    address); the token-prefix rule is not."""
    digest_url = "https://llm.acme.test/v1/deployments/a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"
    out = await propose(world, [U(f"use {digest_url}")], create_call(digest_url))
    assert out.startswith("Proposal "), out
    key_url = "https://llm.acme.test/v1/sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
    out = await propose(world, [U(f"use {key_url}")], create_call(key_url, name="Other"))
    assert "key or token" in out


async def test_a_key_shaped_value_in_another_field_is_still_refused_by_the_guard(world) -> None:
    out = await propose(
        world,
        [U("add it")],
        {
            "kind": "provider",
            "action": "create",
            "changes": {
                "name": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",
                "type": "ollama",
            },
        },
    )
    assert "Nothing was recorded" in out or "key" in out.lower()
    assert await recorded(world) == []


def test_the_default_exemption_is_exact(world=None) -> None:
    k = kinds.get("provider")
    for d in PROVIDER_TYPE_DEFAULTS.values():
        if d["base_url"]:
            assert outside.check(k, {"base_url": d["base_url"]}, None) is None
            assert outside.check(k, {"base_url": str(d["base_url"]) + "/"}, None) is None
    assert outside.check(k, {"base_url": "https://llm.acme.test/v1"}, None) is not None
    # only base_url is exempt: a default-looking value in another field is checked
    assert outside.check(k, {"name": "https://api.anthropic.com"}, None) is not None

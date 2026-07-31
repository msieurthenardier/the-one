"""Unit tests for ``the_one.connectors._inference`` —
``run_engagement_inference`` and its three private helpers
(``_filter_session_history``, ``_render_history_for_prompt``,
``_resolve_inference_provider``) per Flight DD §9 + L7 model-source
extension + M11 F13 L3 connector-scope inference relocation.

M11 F7 L7 originally; M11 F13 L3 rewrote ``_resolve_inference_provider``
+ ``run_engagement_inference`` signatures (Settings parameter → per-
connector kwargs sourced from ``account.config``). Stubs the LLM via
:class:`the_one.llm.mock.MockProvider` (yes/no/garbage/raise paths) and
monkeypatches the cache-snapshot helper at the ``_inference`` namespace
to drive channel-name resolution branches without standing up the pool.
"""

from __future__ import annotations

from typing import Any

import pytest

from the_one.connectors import OPERATOR_VISIBILITY
from the_one.connectors import _inference as inference_mod
from the_one.connectors._inference import (
    _filter_session_history,
    _render_history_for_prompt,
    _resolve_inference_provider,
    run_engagement_inference,
)
from the_one.connectors._pool import _DiscoverableCacheSnapshot
from the_one.connectors.base import (
    DiscoverableEntities,
    DiscoverableEntity,
    InboundEnvelope,
)
from the_one.db.models import Connector, LLMProviderConfig
from the_one.llm.base import (
    ImageContent,
    LLMProvider,
    Message,
    TextContent,
    ToolCall,
    ToolResult,
)
from the_one.llm.mock import MockProvider

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _account() -> Connector:
    """Minimal ``Connector`` for the inference function signature."""
    return Connector(
        id="acct-1",
        name="test",
        type="stub",
        config={},
        secrets={},
    )


def _envelope(
    *,
    channel_id: str = "ch-1",
    peer_name: str = "alice",
    text: str = "what's the weather?",
) -> InboundEnvelope:
    """Minimal ``InboundEnvelope`` for the inference function signature."""
    return InboundEnvelope(
        platform="stub",
        account_id="acct-1",
        channel_id=channel_id,
        thread_id=None,
        peer_id="peer-1",
        peer_name=peer_name,
        text=text,
        raw={},
    )


class _StubProviderRepo:
    """In-memory stand-in for :class:`LLMProviderRepository`.

    Drives both the success and the resolution-failure branches without
    standing up sqlite. The ``get`` coroutine looks up the configured
    id-to-config mapping; missing ids raise ``KeyError`` to mirror the
    real repo's contract.
    """

    def __init__(self, configs: dict[str, LLMProviderConfig] | None = None) -> None:
        self._configs = configs or {}

    async def get(self, provider_id: str) -> LLMProviderConfig:
        if provider_id not in self._configs:
            raise KeyError(f"Provider not found: {provider_id}")
        return self._configs[provider_id]


def _mock_provider_config(
    provider_id: str = "prov-a",
    type_: str = "mock",
    response_content: str = "yes",
) -> LLMProviderConfig:
    return LLMProviderConfig(
        id=provider_id,
        name=f"mock-{provider_id}",
        type=type_,  # type: ignore[arg-type]
        base_url="",
        config={"response": {"content": response_content}},
    )


def _patch_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: _DiscoverableCacheSnapshot | None,
) -> None:
    """Patch ``_get_account_cache_snapshot`` at the ``_inference`` namespace.

    The import shape at L7 lifts the symbol into ``_inference``'s
    module-level namespace, so the patch path matches the helper's
    lookup site. ``snapshot=None`` mirrors a cold pool / unknown account.
    """

    async def _fake_snapshot(_account_id: str) -> _DiscoverableCacheSnapshot | None:
        return snapshot

    monkeypatch.setattr(inference_mod, "_get_account_cache_snapshot", _fake_snapshot)


# ─────────────────────────────────────────────────────────────────────────────
# _filter_session_history
# ─────────────────────────────────────────────────────────────────────────────


def test_filter_session_history_drops_tool_calls() -> None:
    """The filter drops Role.TOOL messages and ASSISTANT messages carrying
    tool_calls — only USER and ASSISTANT-plaintext remain.
    """
    user = Message.user("hi")
    tc = ToolCall(id="tc-1", name="some_tool", arguments={})
    asst_tool = Message.assistant("issuing tool", tool_calls=[tc])
    tool_result = Message.tool(ToolResult(tool_call_id="tc-1", content="tool result"))
    asst_plain = Message.assistant("plain reply")

    filtered = _filter_session_history([user, asst_tool, tool_result, asst_plain])

    assert filtered == [user, asst_plain]


def test_filter_session_history_drops_empty_content() -> None:
    """ASSISTANT with empty content (and no tool_calls) — common when a
    streaming assistant turn yielded no text — is dropped.
    """
    user = Message.user("hi")
    asst_empty = Message.assistant("")
    asst_plain = Message.assistant("plain")

    filtered = _filter_session_history([user, asst_empty, asst_plain])

    assert filtered == [user, asst_plain]


def test_filter_session_history_keeps_only_last_n() -> None:
    """At the default limit (20), a 30-message all-USER list returns the
    last 20 by input ordering.
    """
    messages = [Message.user(f"msg-{i}") for i in range(30)]

    filtered = _filter_session_history(messages)

    assert len(filtered) == 20
    assert filtered[0].content == "msg-10"
    assert filtered[-1].content == "msg-29"


# ─────────────────────────────────────────────────────────────────────────────
# _render_history_for_prompt
# ─────────────────────────────────────────────────────────────────────────────


def test_render_history_for_prompt_operator_prefix() -> None:
    """USER messages with ``visibility == OPERATOR_VISIBILITY`` are prefixed
    with ``[operator] `` in the rendered output; USER messages with
    ``visibility=None`` are not prefixed.
    """
    peer_user = Message.user("peer says hi", visibility=None)
    operator_user = Message.user("operator says steer", visibility=OPERATOR_VISIBILITY)

    rendered = _render_history_for_prompt([peer_user, operator_user])

    assert "user: peer says hi" in rendered
    assert "user: [operator] operator says steer" in rendered


def test_render_history_for_prompt_ordering() -> None:
    """Input ordering matches output ordering (most-recent-last)."""
    a = Message.user("first")
    b = Message.assistant("second")
    c = Message.user("third")

    rendered = _render_history_for_prompt([a, b, c])

    lines = rendered.splitlines()
    assert lines == [
        "user: first",
        "assistant: second",
        "user: third",
    ]


def test_render_history_for_prompt_str_content_byte_identical() -> None:
    """M16 F12 L03: the str path is byte-identical to pre-hardening output —
    ``content_to_text`` returns a str unchanged, so nothing about the
    existing rendering behavior shifts.
    """
    peer_user = Message.user("peer says hi", visibility=None)
    operator_user = Message.user("operator says steer", visibility=OPERATOR_VISIBILITY)
    asst = Message.assistant("a reply")

    rendered = _render_history_for_prompt([peer_user, operator_user, asst])

    assert rendered == (
        "user: peer says hi\nuser: [operator] operator says steer\nassistant: a reply"
    )


def test_render_history_for_prompt_list_content_user_message() -> None:
    """M16 F12 L03: a list-content USER turn (DD3) is flattened via
    ``content_to_text`` instead of stringifying to a Python repr. No
    operator-visibility prefix here — the raw text + image placeholder join
    directly, with no stray double space.
    """
    list_user = Message.user(
        [TextContent(text="look at this"), ImageContent(media_type="image/png", data="Zm9v")],
        visibility=None,
    )

    rendered = _render_history_for_prompt([list_user])

    assert rendered == "user: look at this [image]"
    assert "  " not in rendered


def test_render_history_for_prompt_list_content_user_message_with_operator_prefix() -> None:
    """M16 F12 L03: a list-content USER turn with operator visibility gets
    the ``[operator] `` prefix applied AFTER flattening — the note says
    ``_render_history_for_prompt`` reads raw ``m.content`` (no DD4 prefix
    block present), so ``content_to_text`` only sees the user's own blocks.
    """
    list_user = Message.user(
        [TextContent(text="steer the bot"), ImageContent(media_type="image/png", data="Zm9v")],
        visibility=OPERATOR_VISIBILITY,
    )

    rendered = _render_history_for_prompt([list_user])

    assert rendered == "user: [operator] steer the bot [image]"
    assert "  " not in rendered


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_inference_provider
# ─────────────────────────────────────────────────────────────────────────────


async def test_resolve_inference_provider_uses_connector_kwargs_when_both_set() -> None:
    """Both connector kwargs set → connector path wins; the constructed
    provider uses connector_inference_model; fallback id/model is ignored
    even when also provided.
    """
    repo = _StubProviderRepo(
        {
            "prov-a": _mock_provider_config(provider_id="prov-a"),
            "prov-b": _mock_provider_config(provider_id="prov-b"),
        }
    )

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="prov-a",
        connector_inference_model="model-a",
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert isinstance(provider, MockProvider)
    assert provider.model == "model-a"


async def test_resolve_inference_provider_falls_back_when_connector_kwargs_both_unset() -> None:
    """Both connector kwargs unset, fallback id + model set → fallback
    path fires. The constructed provider uses the fallback model.
    """
    repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert isinstance(provider, MockProvider)
    assert provider.model == "model-b"


async def test_resolve_inference_provider_none_on_connector_resolution_failure() -> None:
    """Connector path with a missing-in-repo id raises KeyError → helper
    returns None and does NOT fall back to the working fallback. Operator
    misconfiguration is surfaced as silence per DD §9.
    """
    # Working fallback that WOULD resolve if the helper escalated — but it
    # MUST NOT per DD §9.
    repo = _StubProviderRepo({"working-prov": _mock_provider_config(provider_id="working-prov")})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="missing-prov",
        connector_inference_model="model-a",
        fallback_provider_config_id="working-prov",
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_returns_none_when_fallback_id_missing() -> None:
    """Connector kwargs fully unset; fallback id None → None (no provider
    available).
    """
    repo = _StubProviderRepo({})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_returns_none_when_fallback_model_missing() -> None:
    """Connector kwargs fully unset; fallback id set but fallback_llm_model
    None → None. The pairing invariant applies to the fallback path too.
    """
    repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id="prov-b",
        fallback_llm_model=None,
    )

    assert provider is None


async def test_resolve_inference_provider_none_when_connector_id_set_model_unset() -> None:
    """Partial connector pair (id set, model unset) → log + None.

    Mirrors the F7-era settings-partial-pair test, at the new layer.
    Pairing invariant applies to the connector path.
    """
    repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="prov-a",
        connector_inference_model=None,
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_none_when_connector_model_set_id_unset() -> None:
    """Partial connector pair (model set, id unset) → log + None.

    Symmetric to the id-set-only case.
    """
    repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model="model-a",
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_uses_connector_kwargs_over_working_fallback() -> None:
    """Connector kwargs fully set AND fallback fully set → connector path
    wins; the fallback is ignored even when both would resolve cleanly.

    This is the "connector-wins-shadows-fallback" semantic (renamed from
    F7's settings-wins shape; same precedence semantic at the new layer).
    """
    repo = _StubProviderRepo(
        {
            "prov-a": _mock_provider_config(provider_id="prov-a"),
            "prov-b": _mock_provider_config(provider_id="prov-b"),
        }
    )

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="prov-a",
        connector_inference_model="model-a",
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert isinstance(provider, MockProvider)
    assert provider.model == "model-a"


async def test_resolve_inference_provider_returns_none_when_both_paths_unconfigured() -> None:
    """Connector kwargs None AND fallback None → None. Full both-paths-
    silence coverage (bridges what's currently scattered across the per-
    path partial tests).
    """
    repo = _StubProviderRepo({})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert provider is None


def _plan_provider_config(provider_id: str = "plan-1") -> LLMProviderConfig:
    """An anthropic-plan row WITH a stored token set (secrets fixture)."""
    return LLMProviderConfig(
        id=provider_id,
        name="Claude Plan",
        type="anthropic-plan",
        base_url="https://api.anthropic.com",
        secrets={
            "access_token": "at-stored",
            "refresh_token": "rt-stored",
            "token_expires_at": 4102444800,
        },
    )


async def test_resolve_inference_provider_constructs_anthropic_plan(monkeypatch) -> None:
    """M19 F01 L02 AC (b): the connector path constructs a plan provider
    keyed by provider-config id — no static token threaded."""
    from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    repo = _StubProviderRepo({"plan-1": _plan_provider_config()})

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="plan-1",
        connector_inference_model="claude-sonnet-4-6",
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert isinstance(provider, AnthropicPlanProvider)
    assert provider.provider_config_id == "plan-1"
    assert provider.model == "claude-sonnet-4-6"


async def test_resolve_inference_provider_reauth_surfaces_at_call_time(monkeypatch) -> None:
    """Companion AC: a re-auth-required credential failure is NOT swallowed
    into the constructor's ``return None`` path (the silent-failure risk
    that motivated self-resolution) — construction succeeds; the typed
    error surfaces when the provider is actually invoked."""
    from the_one.llm.base import Message as LLMMessage
    from the_one.llm.plan_credentials import ReauthRequiredError

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    repo = _StubProviderRepo({"plan-1": _plan_provider_config()})

    class _FailingSource:
        async def get_access_token(self) -> str:
            raise ReauthRequiredError("plan-1")

    monkeypatch.setattr(
        "the_one.llm.plan_credentials.get_credential_source",
        lambda _pid: _FailingSource(),
    )

    provider = await _resolve_inference_provider(
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="plan-1",
        connector_inference_model="claude-sonnet-4-6",
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert provider is not None, "construction must not be swallowed into None"
    with pytest.raises(ReauthRequiredError):
        await provider.complete([LLMMessage.user("hi")])


# ─────────────────────────────────────────────────────────────────────────────
# run_engagement_inference — output parsing branches
# ─────────────────────────────────────────────────────────────────────────────


async def _patch_resolver_returning(
    monkeypatch: pytest.MonkeyPatch,
    provider: LLMProvider | None,
) -> None:
    """Monkeypatch ``_resolve_inference_provider`` at the ``_inference``
    namespace to return ``provider`` (bypassing real repo lookup).
    """

    async def _fake_resolver(
        _repo: Any,
        **_kwargs: Any,
    ) -> LLMProvider | None:
        # **_kwargs absorbs all four keyword-only params
        # (connector_inference_*, fallback_*) without pinning their
        # names — keeps the fake forward-compatible with future kwarg
        # additions and avoids drift if the signature evolves.
        return provider

    monkeypatch.setattr(inference_mod, "_resolve_inference_provider", _fake_resolver)


async def test_run_engagement_inference_returns_true_on_yes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stub provider returns content='yes' → function returns True."""
    _patch_snapshot(monkeypatch, None)
    await _patch_resolver_returning(
        monkeypatch,
        MockProvider(config={"response": {"content": "yes"}}),
    )

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is True


async def test_run_engagement_inference_returns_false_on_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """content='no' → False."""
    _patch_snapshot(monkeypatch, None)
    await _patch_resolver_returning(
        monkeypatch,
        MockProvider(config={"response": {"content": "no"}}),
    )

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


async def test_run_engagement_inference_returns_false_on_garbage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """content='maybe' (or other non-yes single word) → False."""
    _patch_snapshot(monkeypatch, None)
    await _patch_resolver_returning(
        monkeypatch,
        MockProvider(config={"response": {"content": "maybe"}}),
    )

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


async def test_run_engagement_inference_returns_false_on_multiword_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """content='yes, the agent should respond' → False. Only a single-word
    'yes' engages — the prompt requests exactly one word; multi-word
    responses are ambiguous and collapse to silence.
    """
    _patch_snapshot(monkeypatch, None)
    await _patch_resolver_returning(
        monkeypatch,
        MockProvider(config={"response": {"content": "yes, the agent should respond"}}),
    )

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


async def test_run_engagement_inference_returns_true_on_yes_with_surrounding_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """content='  YES  ' (uppercase + surrounding whitespace) → True via
    the lowercase + strip parsing.
    """
    _patch_snapshot(monkeypatch, None)
    await _patch_resolver_returning(
        monkeypatch,
        MockProvider(config={"response": {"content": "  YES  "}}),
    )

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# run_engagement_inference — error-path branches
# ─────────────────────────────────────────────────────────────────────────────


class _RaisingProvider(LLMProvider):
    """Provider stub whose ``complete()`` always raises.

    Drives the function's try/except-around-complete branch. The base
    class's other abstract surface (``name``) is satisfied via a class
    attribute.
    """

    name = "raising"

    def __init__(self) -> None:
        super().__init__()

    async def complete(
        self, messages, tools=None, temperature=0.0, max_tokens=16384, *, enable_thinking=None
    ):
        raise RuntimeError("simulated provider failure")


async def test_run_engagement_inference_returns_false_on_provider_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider.complete raises → function returns False without crashing."""
    _patch_snapshot(monkeypatch, None)
    await _patch_resolver_returning(monkeypatch, _RaisingProvider())

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


async def test_run_engagement_inference_returns_false_on_provider_resolution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider_repo.get raises during resolution → function returns False.

    Exercises the real ``_resolve_inference_provider`` path (no resolver
    monkeypatch) with a connector-path provider id that the repo doesn't
    know about.
    """
    _patch_snapshot(monkeypatch, None)
    repo = _StubProviderRepo({})  # empty — every lookup raises

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="missing",
        connector_inference_model="model-a",
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


# M11 F8 L2: deleted ``test_run_engagement_inference_returns_false_on_none_content``.
# That test constructed ``Message(role=Role.ASSISTANT, content=None)`` to
# bypass ``Message.assistant``'s ``content=""`` default and pin the
# ``run_engagement_inference`` consumer's None-content defensive branch.
# Under F8 L2's ``Message.__post_init__`` ``isinstance(content, str)``
# assertion, that construction now crashes at ``__init__`` time — the
# defended-against corner case is structurally unreachable. The
# corresponding dead defensive branch in ``run_engagement_inference``
# remains as out-of-scope cleanup for a future maintenance leg. See
# ``the_one/agents.md`` → ``provider-shape-portability``.


# ─────────────────────────────────────────────────────────────────────────────
# run_engagement_inference — end-to-end + channel-name branches
# ─────────────────────────────────────────────────────────────────────────────


async def test_run_engagement_inference_end_to_end_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration-shaped happy path: real-shaped Message list (mixed roles
    + visibility tags), real-shaped envelope, MockProvider returning 'yes'
    through the full real ``_resolve_inference_provider`` resolution. No
    resolver monkeypatching — covers the happy path that the unit tests
    slice apart.
    """
    _patch_snapshot(monkeypatch, None)

    repo = _StubProviderRepo(
        {"prov-a": _mock_provider_config(provider_id="prov-a", response_content="yes")}
    )

    messages = [
        Message.user("hi there", visibility=None),
        Message.assistant("how can i help?"),
        Message.user("nudge the model", visibility=OPERATOR_VISIBILITY),
        Message.user("what's the weather?", visibility=None),
    ]

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        messages,
        repo,  # type: ignore[arg-type]
        connector_inference_provider_config_id="prov-a",
        connector_inference_model="model-a",
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is True


async def test_run_engagement_inference_uses_channel_id_when_cache_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache lookup misses → prompt uses raw envelope.channel_id as the
    channel_name fallback. Verified via an instrumented MockProvider that
    captures the prompt content.
    """
    _patch_snapshot(monkeypatch, None)

    captured: dict[str, str] = {}

    class _CapturingProvider(LLMProvider):
        name = "capturing"

        def __init__(self) -> None:
            super().__init__()

        async def complete(
            self, messages, tools=None, temperature=0.0, max_tokens=16384, *, enable_thinking=None
        ):
            captured["prompt"] = messages[0].content
            return Message.assistant("no")

    await _patch_resolver_returning(monkeypatch, _CapturingProvider())

    await run_engagement_inference(
        _account(),
        _envelope(channel_id="ch-raw-id"),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert "ch-raw-id" in captured["prompt"]


async def test_run_engagement_inference_uses_cache_label_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache has a matching channel entity → prompt uses the friendly label
    (not the raw id).
    """
    snapshot = _DiscoverableCacheSnapshot(
        cache=DiscoverableEntities(channels=[DiscoverableEntity(id="ch-1", label="general")]),
        stale_carry=None,
        fetched_at_monotonic=0.0,
        account_type="stub",
    )
    _patch_snapshot(monkeypatch, snapshot)

    captured: dict[str, str] = {}

    class _CapturingProvider(LLMProvider):
        name = "capturing"

        def __init__(self) -> None:
            super().__init__()

        async def complete(
            self, messages, tools=None, temperature=0.0, max_tokens=16384, *, enable_thinking=None
        ):
            captured["prompt"] = messages[0].content
            return Message.assistant("no")

    await _patch_resolver_returning(monkeypatch, _CapturingProvider())

    await run_engagement_inference(
        _account(),
        _envelope(channel_id="ch-1"),
        [],
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert "general" in captured["prompt"]
    # The friendly label is used in the channel slot; the raw id is not
    # forced into the prompt anywhere it would shadow the label.
    # (The id may legitimately appear elsewhere if it ever shared text
    # with the inbound; tighten only if a regression surfaces.)


async def test_run_engagement_inference_filters_history_before_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """30 mixed-role session messages → the prompt's history reflects the
    filtered last-20-USER-or-ASSISTANT-plaintext projection (tool calls
    and tool results dropped; cap honored).
    """
    _patch_snapshot(monkeypatch, None)

    captured: dict[str, str] = {}

    class _CapturingProvider(LLMProvider):
        name = "capturing"

        def __init__(self) -> None:
            super().__init__()

        async def complete(
            self, messages, tools=None, temperature=0.0, max_tokens=16384, *, enable_thinking=None
        ):
            captured["prompt"] = messages[0].content
            return Message.assistant("no")

    await _patch_resolver_returning(monkeypatch, _CapturingProvider())

    # 30 USER messages — should reduce to the last 20.
    messages = [Message.user(f"msg-{i}") for i in range(30)]
    # Insert a tool-call message that must be dropped.
    tc = ToolCall(id="tc-1", name="some_tool", arguments={})
    messages.insert(5, Message.assistant("tool-issuing", tool_calls=[tc]))
    # Insert a TOOL message that must be dropped.
    messages.insert(6, Message.tool(ToolResult(tool_call_id="tc-1", content="r")))

    await run_engagement_inference(
        _account(),
        _envelope(),
        messages,
        _StubProviderRepo(),  # type: ignore[arg-type]
        connector_inference_provider_config_id=None,
        connector_inference_model=None,
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    prompt = captured["prompt"]
    # The cap is 20 USER lines — verify the oldest are dropped.
    # USER msg-0 through msg-9 should be outside the 20-message tail
    # (filtered list = 30 USER messages, take last 20 → msg-10..msg-29).
    assert "user: msg-29" in prompt
    assert "user: msg-10" in prompt
    assert "user: msg-9" not in prompt
    # Tool call and tool result must not appear.
    assert "tool-issuing" not in prompt
    assert "user: r" not in prompt

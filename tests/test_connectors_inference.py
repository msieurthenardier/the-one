"""Unit tests for ``the_one.connectors._inference`` —
``run_engagement_inference`` and its three private helpers
(``_filter_session_history``, ``_render_history_for_prompt``,
``_resolve_inference_provider``) per Flight DD §9 + L7 model-source
extension.

M11 F7 L7. Stubs the LLM via :class:`the_one.llm.mock.MockProvider`
(yes/no/garbage/raise paths) and monkeypatches the cache-snapshot
helper at the ``_inference`` namespace to drive channel-name
resolution branches without standing up the pool.
"""

from __future__ import annotations

from typing import Any

import pytest

from the_one.config import Settings
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
from the_one.db.models import ConnectorAccount, LLMProviderConfig
from the_one.llm.base import LLMProvider, Message, Role, ToolCall, ToolResult
from the_one.llm.mock import MockProvider


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _account() -> ConnectorAccount:
    """Minimal ``ConnectorAccount`` for the inference function signature."""
    return ConnectorAccount(
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

    monkeypatch.setattr(
        inference_mod, "_get_account_cache_snapshot", _fake_snapshot
    )


def _empty_settings() -> Settings:
    """Construct a ``Settings`` with the inference pair explicitly unset.

    Bypasses any env var bleed via the explicit kwargs (Pydantic v2 honors
    them over env-resolved defaults for the call site).
    """
    return Settings(
        inference_provider_config_id=None,
        inference_model=None,
    )


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

    filtered = _filter_session_history(
        [user, asst_tool, tool_result, asst_plain]
    )

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


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_inference_provider
# ─────────────────────────────────────────────────────────────────────────────


async def test_resolve_inference_provider_uses_settings_when_both_id_and_model_set() -> None:
    """Both settings fields set → settings path wins; the constructed
    provider uses settings.inference_model; fallback id/model is ignored
    even when also provided.
    """
    settings = Settings(
        inference_provider_config_id="prov-a",
        inference_model="model-a",
    )
    repo = _StubProviderRepo(
        {
            "prov-a": _mock_provider_config(provider_id="prov-a"),
            "prov-b": _mock_provider_config(provider_id="prov-b"),
        }
    )

    provider = await _resolve_inference_provider(
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert isinstance(provider, MockProvider)
    assert provider.model == "model-a"


async def test_resolve_inference_provider_returns_none_when_settings_id_set_but_model_unset() -> None:
    """Partial settings pair (id set, model unset) → log + None. Does NOT
    silently fall back to the fallback even when the fallback is working.
    """
    settings = Settings(
        inference_provider_config_id="prov-a",
        inference_model=None,
    )
    repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

    provider = await _resolve_inference_provider(
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_returns_none_when_settings_model_set_but_id_unset() -> None:
    """Partial settings pair (model set, id unset) → log + None. Symmetric
    to the id-set-only case.
    """
    settings = Settings(
        inference_provider_config_id=None,
        inference_model="model-a",
    )
    repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

    provider = await _resolve_inference_provider(
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_falls_back_when_settings_both_unset() -> None:
    """Both settings unset, fallback id + model set → fallback path fires.
    The constructed provider uses the fallback model.
    """
    settings = _empty_settings()
    repo = _StubProviderRepo(
        {"prov-b": _mock_provider_config(provider_id="prov-b")}
    )

    provider = await _resolve_inference_provider(
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id="prov-b",
        fallback_llm_model="model-b",
    )

    assert isinstance(provider, MockProvider)
    assert provider.model == "model-b"


async def test_resolve_inference_provider_returns_none_on_settings_resolution_failure_no_fallback() -> None:
    """Settings path with a missing-in-repo id raises KeyError → helper
    returns None and does NOT fall back to the working fallback. Operator
    misconfiguration is surfaced as silence per DD §9.
    """
    settings = Settings(
        inference_provider_config_id="missing-prov",
        inference_model="model-a",
    )
    # Working fallback that WOULD resolve if the helper escalated — but it
    # MUST NOT per DD §9.
    repo = _StubProviderRepo(
        {"working-prov": _mock_provider_config(provider_id="working-prov")}
    )

    provider = await _resolve_inference_provider(
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id="working-prov",
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_returns_none_when_fallback_id_missing() -> None:
    """Settings fully unset; fallback id None → None (no provider available)."""
    settings = _empty_settings()
    repo = _StubProviderRepo({})

    provider = await _resolve_inference_provider(
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id=None,
        fallback_llm_model="model-b",
    )

    assert provider is None


async def test_resolve_inference_provider_returns_none_when_fallback_model_missing() -> None:
    """Settings fully unset; fallback id set but fallback_llm_model None →
    None. The pairing invariant applies to the fallback path too.
    """
    settings = _empty_settings()
    repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

    provider = await _resolve_inference_provider(
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id="prov-b",
        fallback_llm_model=None,
    )

    assert provider is None


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
        _settings: Settings,
        _repo: Any,
        _fb_id: str | None,
        _fb_model: str | None,
    ) -> LLMProvider | None:
        return provider

    monkeypatch.setattr(
        inference_mod, "_resolve_inference_provider", _fake_resolver
    )


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
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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
        MockProvider(
            config={"response": {"content": "yes, the agent should respond"}}
        ),
    )

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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

    async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384):
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
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


async def test_run_engagement_inference_returns_false_on_provider_resolution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider_repo.get raises during resolution → function returns False.

    Exercises the real ``_resolve_inference_provider`` path (no resolver
    monkeypatch) with a settings-path provider id that the repo doesn't
    know about.
    """
    _patch_snapshot(monkeypatch, None)
    settings = Settings(
        inference_provider_config_id="missing",
        inference_model="model-a",
    )
    repo = _StubProviderRepo({})  # empty — every lookup raises

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        settings,
        repo,  # type: ignore[arg-type]
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


async def test_run_engagement_inference_returns_false_on_none_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider returns Message with content=None → function returns False
    without AttributeError. Defensive against codec corner cases.
    """

    class _NoneContentProvider(LLMProvider):
        name = "none-content"

        def __init__(self) -> None:
            super().__init__()

        async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384):
            # Construct directly to bypass Message.assistant's default of "".
            return Message(role=Role.ASSISTANT, content=None)  # type: ignore[arg-type]

    _patch_snapshot(monkeypatch, None)
    await _patch_resolver_returning(monkeypatch, _NoneContentProvider())

    result = await run_engagement_inference(
        _account(),
        _envelope(),
        [],
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
        fallback_provider_config_id=None,
        fallback_llm_model=None,
    )

    assert result is False


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

    settings = Settings(
        inference_provider_config_id="prov-a",
        inference_model="model-a",
    )
    repo = _StubProviderRepo(
        {
            "prov-a": _mock_provider_config(
                provider_id="prov-a", response_content="yes"
            )
        }
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
        settings,
        repo,  # type: ignore[arg-type]
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

        async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384):
            captured["prompt"] = messages[0].content
            return Message.assistant("no")

    await _patch_resolver_returning(monkeypatch, _CapturingProvider())

    await run_engagement_inference(
        _account(),
        _envelope(channel_id="ch-raw-id"),
        [],
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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
        cache=DiscoverableEntities(
            channels=[DiscoverableEntity(id="ch-1", label="general")]
        ),
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

        async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384):
            captured["prompt"] = messages[0].content
            return Message.assistant("no")

    await _patch_resolver_returning(monkeypatch, _CapturingProvider())

    await run_engagement_inference(
        _account(),
        _envelope(channel_id="ch-1"),
        [],
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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

        async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384):
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
        _empty_settings(),
        _StubProviderRepo(),  # type: ignore[arg-type]
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

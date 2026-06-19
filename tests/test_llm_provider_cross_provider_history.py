"""Cross-provider history round-trip tests.

M11 F8 L1: pins the canonical ``Message`` format's cross-provider
portability. Two tiers:

1. **Pure-encoder primary** (``TestCrossProviderHistoryPureEncoder``) —
   no network. Feeds a canonical multi-shape Message list through each
   provider's ``_to_api_message`` and asserts each return's structural
   shape. Runs in CI without credentials.

2. **Live-API supplementary** (``TestCrossProviderHistoryLive``) —
   ``@pytest.mark.live`` per the project convention (see
   ``tests/test_input_tokens_cross_provider_live.py`` for the canonical
   live-test pattern). Exercises the wire-level round-trip across two
   operator-specified pairs: Anthropic↔Ollama qwen and
   Anthropic↔OpenRouter ``google/gemma-4-26b-a4b-it:free``. At least one
   live test exercises a real ``tools=...`` payload so the cross-provider
   swap concern (tool_call shape compatibility) is actually validated
   at the wire level.

Scope distinction: ``tests/test_llm_provider_user_content_projection.py``
covers USER-role inline-prefix projection across all 4 providers. This
file extends coverage to multi-shape SESSION HISTORY (user +
assistant-with-tool-calls + tool + assistant-final) — the per-provider
encoding contract for ToolCall + ToolResult shapes plus the cross-provider
swap-resilience invariant.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.test_input_tokens_cross_provider_live import _aclose_provider_client
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message, Role, ToolCall, ToolResult
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OpenAIProvider
from the_one.llm.openrouter_provider import OpenRouterProvider

# ---------------------------------------------------------------------------
# Canonical multi-shape session
# ---------------------------------------------------------------------------

# The canonical session list intentionally includes:
#   * SYSTEM turn (Anthropic extracts via _build_kwargs; pure-encoder tests
#     for Anthropic filter it out per leg §8 / Edge Cases).
#   * USER turn with peer_name + channel_name (exercises the L4 inline
#     prefix projection across providers).
#   * ASSISTANT turn with content + tool_calls (exercises the
#     content-bearing assistant-with-tool-calls branch).
#   * TOOL turn whose ToolResult.content is already a JSON string
#     (exercises F7 12.l str passthrough invariant).
#   * ASSISTANT turn with empty content + tool_calls (exercises the
#     Anthropic-vs-OpenAI divergence at the encoding boundary).
#   * TOOL turn with short str content.
#   * Final ASSISTANT turn with content + no tool_calls (canonical close).
#
# ToolCall IDs use the Anthropic ``toolu_*`` shape to exercise the
# cross-provider swap concern at the per-message level: a session that
# accumulated tool_calls under Anthropic carries those IDs forward into
# the canonical Message — when the same list is encoded by OpenAI/Ollama,
# the canonical ID is what they emit in their request payload.


def _build_canonical_session() -> list[Message]:
    return [
        Message.system("You are a helpful agent."),
        Message.user(
            "What's the channel been talking about?",
            peer_name="alice",
            channel_name="general",
        ),
        Message.assistant(
            content="Let me check the recent messages.",
            tool_calls=[
                ToolCall(
                    id="toolu_01abc123",
                    name="fetch_channel_history",
                    arguments={"channel_id": "1234567890", "limit": 10},
                ),
            ],
        ),
        Message.tool(
            ToolResult(
                tool_call_id="toolu_01abc123",
                content=(
                    '[{"peer_name": "alice", "content": "hi"}, '
                    '{"peer_name": "bob", "content": "hey"}]'
                ),
            ),
        ),
        # F8 L1 medium-severity addition (per design review): empty-content
        # assistant-with-tool-calls turn. Anthropic skips the text block;
        # OpenAI/Ollama emit content: None. Both are valid per their APIs
        # but the encodings diverge — the canonical list pins both
        # behaviors via the empty-content edge-case test.
        Message.assistant(
            content="",
            tool_calls=[
                ToolCall(
                    id="toolu_01def456",
                    name="noop",
                    arguments={},
                ),
            ],
        ),
        Message.tool(
            ToolResult(
                tool_call_id="toolu_01def456",
                content="ok",
            ),
        ),
        Message.assistant(
            content="The channel has been quiet — just greetings from alice and bob.",
        ),
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def canonical_session() -> list[Message]:
    return _build_canonical_session()


@pytest.fixture
def anthropic_provider() -> AnthropicProvider:
    return AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    return OpenAIProvider(model="gpt-4o", api_key="test-key")


@pytest.fixture
def ollama_provider() -> OllamaProvider:
    return OllamaProvider(model="qwen2.5:7b", base_url="http://test:11434")


@pytest.fixture
def openrouter_provider() -> OpenRouterProvider:
    return OpenRouterProvider(model="anthropic/claude-3.5-sonnet", api_key="test-key")


# ---------------------------------------------------------------------------
# Pure-encoder tests (no network) — the primary test of record
# ---------------------------------------------------------------------------


class TestCrossProviderHistoryPureEncoder:
    """Per-provider encoding of the canonical multi-shape session.

    Asserts structural validity, not byte-equality of the whole dict —
    this catches real shape changes (a missing key, a swapped role)
    without breaking on every cosmetic edit (whitespace in JSON,
    ordering of dict keys).
    """

    def test_anthropic_encodes_canonical_history_without_error(
        self,
        anthropic_provider: AnthropicProvider,
        canonical_session: list[Message],
    ) -> None:
        # Anthropic extracts SYSTEM into a separate ``system`` kwarg via
        # ``_build_kwargs`` (lines 73-78); ``_to_api_message`` is NEVER
        # called with a SYSTEM message. Filter it out per leg §8 /
        # Edge Cases.
        non_system = [m for m in canonical_session if m.role != Role.SYSTEM]
        results = [anthropic_provider._to_api_message(m) for m in non_system]
        assert len(results) == 6

        # Index 0: USER turn — projected with inline peer + channel prefix.
        assert results[0] == {
            "role": "user",
            "content": "[from alice in #general]: What's the channel been talking about?",
        }

        # Index 1: content-bearing ASSISTANT + tool_calls. Anthropic emits
        # content: list[dict] with a text block + a tool_use block.
        assert results[1]["role"] == "assistant"
        assert isinstance(results[1]["content"], list)
        assert len(results[1]["content"]) == 2
        assert results[1]["content"][0]["type"] == "text"
        assert results[1]["content"][0]["text"] == "Let me check the recent messages."
        assert results[1]["content"][1]["type"] == "tool_use"
        assert results[1]["content"][1]["id"] == "toolu_01abc123"
        assert results[1]["content"][1]["name"] == "fetch_channel_history"
        assert results[1]["content"][1]["input"] == {
            "channel_id": "1234567890",
            "limit": 10,
        }

        # Index 2: TOOL turn — Anthropic uses USER role + tool_result block.
        assert results[2]["role"] == "user"
        assert isinstance(results[2]["content"], list)
        assert len(results[2]["content"]) == 1
        block = results[2]["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "toolu_01abc123"
        assert block["is_error"] is False
        # str ToolResult.content round-trips byte-identically (F7 12.l).
        assert block["content"] == (
            '[{"peer_name": "alice", "content": "hi"}, {"peer_name": "bob", "content": "hey"}]'
        )

        # Index 3: empty-content ASSISTANT + tool_calls. Anthropic skips
        # the text block entirely — only the tool_use block appears.
        assert results[3]["role"] == "assistant"
        assert isinstance(results[3]["content"], list)
        text_blocks = [b for b in results[3]["content"] if b.get("type") == "text"]
        assert len(text_blocks) == 0
        tool_use_blocks = [b for b in results[3]["content"] if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0]["id"] == "toolu_01def456"
        assert tool_use_blocks[0]["name"] == "noop"

        # Index 4: TOOL turn with short str content.
        assert results[4]["role"] == "user"
        assert results[4]["content"][0]["content"] == "ok"

        # Index 5: final ASSISTANT turn — no tool_calls, falls through to
        # role-content shape.
        assert results[5] == {
            "role": "assistant",
            "content": "The channel has been quiet — just greetings from alice and bob.",
        }

    def test_openai_encodes_canonical_history_without_error(
        self,
        openai_provider: OpenAIProvider,
        canonical_session: list[Message],
    ) -> None:
        results = [openai_provider._to_api_message(m) for m in canonical_session]
        assert len(results) == 7

        # Index 0: SYSTEM turn — OpenAI handles via fallback branch.
        assert results[0] == {"role": "system", "content": "You are a helpful agent."}

        # Index 1: USER turn — projected with inline prefix.
        assert results[1] == {
            "role": "user",
            "content": "[from alice in #general]: What's the channel been talking about?",
        }

        # Index 2: content-bearing ASSISTANT + tool_calls. OpenAI emits
        # role: "assistant", content: str, tool_calls: [...].
        assert results[2]["role"] == "assistant"
        assert results[2]["content"] == "Let me check the recent messages."
        assert len(results[2]["tool_calls"]) == 1
        tc = results[2]["tool_calls"][0]
        assert tc["id"] == "toolu_01abc123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "fetch_channel_history"
        # OpenAI JSON-encodes the arguments string.
        assert json.loads(tc["function"]["arguments"]) == {
            "channel_id": "1234567890",
            "limit": 10,
        }

        # Index 3: TOOL turn — OpenAI uses role: "tool", tool_call_id, content.
        assert results[3] == {
            "role": "tool",
            "tool_call_id": "toolu_01abc123",
            "content": (
                '[{"peer_name": "alice", "content": "hi"}, {"peer_name": "bob", "content": "hey"}]'
            ),
        }

        # Index 4: empty-content ASSISTANT + tool_calls. OpenAI emits
        # content: None (msg.content or None at line 265) alongside tool_calls.
        assert results[4]["role"] == "assistant"
        assert results[4]["content"] is None
        assert len(results[4]["tool_calls"]) == 1
        assert results[4]["tool_calls"][0]["id"] == "toolu_01def456"

        # Index 5: TOOL turn with short str content.
        assert results[5] == {
            "role": "tool",
            "tool_call_id": "toolu_01def456",
            "content": "ok",
        }

        # Index 6: final ASSISTANT turn — no tool_calls, falls through.
        assert results[6] == {
            "role": "assistant",
            "content": "The channel has been quiet — just greetings from alice and bob.",
        }

    def test_ollama_encodes_canonical_history_without_error(
        self,
        ollama_provider: OllamaProvider,
        canonical_session: list[Message],
    ) -> None:
        # Ollama mirrors OpenAI's encoding (per
        # ``the_one/llm/ollama_provider.py:252-279``). The shape is byte-
        # identical; we re-assert here to catch a future divergence.
        results = [ollama_provider._to_api_message(m) for m in canonical_session]
        assert len(results) == 7

        assert results[0] == {"role": "system", "content": "You are a helpful agent."}
        assert results[1] == {
            "role": "user",
            "content": "[from alice in #general]: What's the channel been talking about?",
        }
        assert results[2]["role"] == "assistant"
        assert results[2]["content"] == "Let me check the recent messages."
        assert len(results[2]["tool_calls"]) == 1
        assert results[2]["tool_calls"][0]["id"] == "toolu_01abc123"
        assert results[2]["tool_calls"][0]["function"]["name"] == "fetch_channel_history"

        assert results[3]["role"] == "tool"
        assert results[3]["tool_call_id"] == "toolu_01abc123"

        # Empty-content ASSISTANT + tool_calls: same as OpenAI.
        assert results[4]["role"] == "assistant"
        assert results[4]["content"] is None
        assert len(results[4]["tool_calls"]) == 1

        assert results[5]["role"] == "tool"
        assert results[5]["tool_call_id"] == "toolu_01def456"
        assert results[5]["content"] == "ok"

        assert results[6] == {
            "role": "assistant",
            "content": "The channel has been quiet — just greetings from alice and bob.",
        }

    def test_openrouter_inherits_openai_encoding_for_history(
        self,
        openai_provider: OpenAIProvider,
        openrouter_provider: OpenRouterProvider,
        canonical_session: list[Message],
    ) -> None:
        """Pins the OpenRouter → OpenAI inheritance contract.

        ``OpenRouterProvider`` has no ``_to_api_message`` override (verified
        at ``the_one/llm/openrouter_provider.py``); calling the inherited
        method through an OpenRouter instance must produce byte-identical
        output to OpenAI. If OpenRouter ever overrides
        ``_to_api_message``, this test catches the divergence.
        """
        for msg in canonical_session:
            openai_result = openai_provider._to_api_message(msg)
            openrouter_result = openrouter_provider._to_api_message(msg)
            assert openai_result == openrouter_result, (
                f"OpenRouter encoding diverged from OpenAI for {msg.role.value}: "
                f"openai={openai_result!r}, openrouter={openrouter_result!r}"
            )

    def test_cross_provider_session_swap_anthropic_to_openai_shape(
        self,
        openai_provider: OpenAIProvider,
        anthropic_provider: AnthropicProvider,
    ) -> None:
        """Build a session "as if accumulated under Anthropic" (ToolCall
        IDs in Anthropic ``toolu_*`` format, ToolResult.content as a JSON
        string), feed through both encoders. Both must accept the same
        Message list without raising and produce valid per-provider
        shapes — pinning swap resilience.
        """
        anthropic_shape_session = [
            Message.user("question"),
            Message.assistant(
                content="working on it",
                tool_calls=[
                    ToolCall(
                        id="toolu_01anthropic_shape",
                        name="lookup",
                        arguments={"k": "v"},
                    ),
                ],
            ),
            Message.tool(
                ToolResult(
                    tool_call_id="toolu_01anthropic_shape",
                    content='{"result": "ok"}',
                ),
            ),
        ]

        # OpenAI consumes Anthropic-shape IDs without complaint.
        openai_results = [openai_provider._to_api_message(m) for m in anthropic_shape_session]
        assert openai_results[1]["tool_calls"][0]["id"] == "toolu_01anthropic_shape"
        assert openai_results[2]["tool_call_id"] == "toolu_01anthropic_shape"
        assert openai_results[2]["role"] == "tool"

        # Anthropic re-consumes them identically (its own shape).
        anthropic_results = [anthropic_provider._to_api_message(m) for m in anthropic_shape_session]
        assert anthropic_results[1]["content"][1]["id"] == "toolu_01anthropic_shape"
        assert anthropic_results[2]["content"][0]["tool_use_id"] == "toolu_01anthropic_shape"

    def test_cross_provider_session_swap_openai_to_anthropic_shape(
        self,
        openai_provider: OpenAIProvider,
        anthropic_provider: AnthropicProvider,
    ) -> None:
        """Reverse direction: OpenAI-shape IDs (``call_*``) feed cleanly
        through Anthropic. Neither provider validates the ID format.
        """
        openai_shape_session = [
            Message.user("question"),
            Message.assistant(
                content="working on it",
                tool_calls=[
                    ToolCall(
                        id="call_xyz789",
                        name="lookup",
                        arguments={"k": "v"},
                    ),
                ],
            ),
            Message.tool(
                ToolResult(
                    tool_call_id="call_xyz789",
                    content='{"result": "ok"}',
                ),
            ),
        ]

        anthropic_results = [anthropic_provider._to_api_message(m) for m in openai_shape_session]
        assert anthropic_results[1]["content"][1]["id"] == "call_xyz789"
        assert anthropic_results[2]["content"][0]["tool_use_id"] == "call_xyz789"

        openai_results = [openai_provider._to_api_message(m) for m in openai_shape_session]
        assert openai_results[1]["tool_calls"][0]["id"] == "call_xyz789"
        assert openai_results[2]["tool_call_id"] == "call_xyz789"

    def test_assistant_empty_content_tool_calls_per_provider(
        self,
        anthropic_provider: AnthropicProvider,
        openai_provider: OpenAIProvider,
        ollama_provider: OllamaProvider,
    ) -> None:
        """Pins the most subtle cross-provider divergence:
        ``content=""`` + ``tool_calls=[...]``.

        Anthropic skips the text block entirely (only tool_use block in
        ``content`` list). OpenAI/Ollama emit ``content: None`` alongside
        ``tool_calls``. Both are valid per their APIs; the test asserts
        both behaviors per their providers without forcing alignment.
        """
        msg = Message.assistant(
            content="",
            tool_calls=[
                ToolCall(id="toolu_empty", name="noop", arguments={}),
            ],
        )

        # Anthropic: no text block.
        a_result = anthropic_provider._to_api_message(msg)
        assert a_result["role"] == "assistant"
        assert isinstance(a_result["content"], list)
        text_blocks = [b for b in a_result["content"] if b.get("type") == "text"]
        assert text_blocks == [], f"Anthropic emitted a text block for empty content: {a_result}"
        tool_use_blocks = [b for b in a_result["content"] if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 1

        # OpenAI: content is None.
        o_result = openai_provider._to_api_message(msg)
        assert o_result["role"] == "assistant"
        assert o_result["content"] is None
        assert len(o_result["tool_calls"]) == 1

        # Ollama: same as OpenAI.
        ol_result = ollama_provider._to_api_message(msg)
        assert ol_result["role"] == "assistant"
        assert ol_result["content"] is None
        assert len(ol_result["tool_calls"]) == 1

    def test_tool_result_content_str_passthrough_all_providers(
        self,
        anthropic_provider: AnthropicProvider,
        openai_provider: OpenAIProvider,
        ollama_provider: OllamaProvider,
        openrouter_provider: OpenRouterProvider,
    ) -> None:
        """Pins F7's 12.l contract: a str ToolResult.content round-trips
        byte-identical through every provider's encoder. Pre-empts an
        L2 regression.
        """
        payload = '{"channels": [{"id": "ch1", "name": "general"}]}'
        msg = Message.tool(ToolResult(tool_call_id="toolu_strpass", content=payload))

        a_result = anthropic_provider._to_api_message(msg)
        assert a_result["content"][0]["content"] == payload

        o_result = openai_provider._to_api_message(msg)
        assert o_result["content"] == payload

        ol_result = ollama_provider._to_api_message(msg)
        assert ol_result["content"] == payload

        or_result = openrouter_provider._to_api_message(msg)
        assert or_result["content"] == payload

    def test_tool_result_content_normalized_at_construction_uniformly(
        self,
        anthropic_provider: AnthropicProvider,
        openai_provider: OpenAIProvider,
        ollama_provider: OllamaProvider,
    ) -> None:
        """Post-L2 (F8 dataclass-shape-invariants), ``ToolResult.__post_init__``
        normalizes non-str content to JSON-str at construction. Every
        provider's ``_to_api_message`` receives str content uniformly —
        no provider-specific coercion at the encoder boundary. See
        ``the_one/agents.md`` → ``provider-shape-portability``.
        """
        non_str_payload: list[dict[str, object]] = [{"k": "v"}]
        expected_json = json.dumps(non_str_payload)

        # Construction-time normalization (no post-construction assignment —
        # that pattern is the anti-pattern documented in the
        # ``provider-shape-portability`` convention).
        tr = ToolResult(tool_call_id="toolu_norm", content=non_str_payload)
        assert tr.content == expected_json  # already normalized at __init__

        msg = Message.tool(tr)
        assert msg.content == expected_json  # propagates through factory

        # Anthropic: pass-through of normalized str.
        a_result = anthropic_provider._to_api_message(msg)
        assert a_result["content"][0]["content"] == expected_json

        # OpenAI: pass-through of normalized str.
        o_result = openai_provider._to_api_message(msg)
        assert o_result["content"] == expected_json

        # Ollama: pass-through of normalized str.
        ol_result = ollama_provider._to_api_message(msg)
        assert ol_result["content"] == expected_json


# ---------------------------------------------------------------------------
# Live-API supplementary tests
# ---------------------------------------------------------------------------


async def _resolve_ollama(timeout: float = 5.0) -> tuple[str, str]:
    """Probe Ollama and resolve a model name, mirroring the canonical
    pattern at ``tests/test_input_tokens_cross_provider_live.py:199-236``.

    Returns ``(base_url, model)``. Raises ``pytest.skip.Exception`` (via
    ``pytest.skip``) when Ollama is unreachable or no models are loaded.
    """
    import httpx

    base_url = os.environ.get("LIVE_OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    probe_root = base_url.rstrip("/")
    if probe_root.endswith("/v1"):
        probe_root = probe_root[: -len("/v1")]
    tags_url = probe_root + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(tags_url)
    except (httpx.HTTPError, OSError) as exc:
        pytest.skip(
            f"Ollama at {base_url} not reachable: {type(exc).__name__}: {exc}. "
            f"On native-Linux Docker, host.docker.internal may not resolve — "
            f"set LIVE_OLLAMA_BASE_URL explicitly."
        )
    if resp.status_code != 200:
        pytest.skip(f"Ollama at {base_url} not reachable: HTTP {resp.status_code}")
    tags = resp.json().get("models", [])
    if not tags:
        pytest.skip(f"Ollama at {base_url} has no models loaded")

    preferred = os.environ.get("LIVE_OLLAMA_MODEL")
    available_names = [t.get("name") or t.get("model") for t in tags]
    available_names = [n for n in available_names if n]
    if preferred and preferred in available_names:
        model = preferred
    elif "qwen2.5:7b" in available_names:
        model = "qwen2.5:7b"
    elif available_names:
        model = available_names[0]
    else:
        pytest.skip(f"Ollama at {base_url} returned tags but no model names")
    return base_url, model


class TestCrossProviderHistoryLive:
    """Live-API cross-provider session swaps.

    Each test is ``@pytest.mark.live``, deselected from default
    ``make test-unit`` runs. Run via ``make test-live`` or
    ``.venv/bin/python -m pytest tests/test_llm_provider_cross_provider_history.py -m live ...``.

    Skip-marked when credentials/services missing via inline
    ``pytest.skip(...)`` at function entry, mirroring the canonical
    pattern at ``tests/test_input_tokens_cross_provider_live.py``.

    Live tests are CONFIDENCE tests, not behavior pins — LLMs are
    non-deterministic so we don't assert exact response content. We
    assert the wire-level round-trip succeeds and the response is a
    valid ``Message``.
    """

    @pytest.mark.live
    async def test_anthropic_to_ollama_session_swap_live(self) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip(
                "ANTHROPIC_API_KEY not set — operator must export the key to run this live test"
            )
        base_url, ollama_model = await _resolve_ollama()

        anthropic_model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        anthropic = AnthropicProvider(model=anthropic_model)
        ollama = OllamaProvider(model=ollama_model, base_url=base_url)

        try:
            # Step 1: minimal conversation under Anthropic.
            history: list[Message] = [
                Message.system("Reply with one word."),
                Message.user("Hello."),
            ]
            anthropic_reply = await anthropic.complete(history, temperature=0.0, max_tokens=50)
            assert isinstance(anthropic_reply, Message)
            assert anthropic_reply.role == Role.ASSISTANT
            history.append(anthropic_reply)

            # Step 2: continue the session under Ollama.
            history.append(Message.user("Same."))
            ollama_reply = await ollama.complete(history, temperature=0.0, max_tokens=50)
            assert isinstance(ollama_reply, Message)
            assert ollama_reply.role == Role.ASSISTANT
            # NO content assertions — model behavior is non-deterministic.
        finally:
            await _aclose_provider_client(anthropic)
            await _aclose_provider_client(ollama)

    @pytest.mark.live
    async def test_ollama_to_anthropic_session_swap_live(self) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip(
                "ANTHROPIC_API_KEY not set — operator must export the key to run this live test"
            )
        base_url, ollama_model = await _resolve_ollama()

        anthropic_model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        anthropic = AnthropicProvider(model=anthropic_model)
        ollama = OllamaProvider(model=ollama_model, base_url=base_url)

        try:
            # Step 1: minimal conversation under Ollama.
            history: list[Message] = [
                Message.system("Reply with one word."),
                Message.user("Hello."),
            ]
            ollama_reply = await ollama.complete(history, temperature=0.0, max_tokens=50)
            assert isinstance(ollama_reply, Message)
            assert ollama_reply.role == Role.ASSISTANT
            history.append(ollama_reply)

            # Step 2: continue the session under Anthropic.
            history.append(Message.user("Same."))
            anthropic_reply = await anthropic.complete(history, temperature=0.0, max_tokens=50)
            assert isinstance(anthropic_reply, Message)
            assert anthropic_reply.role == Role.ASSISTANT
        finally:
            await _aclose_provider_client(anthropic)
            await _aclose_provider_client(ollama)

    @pytest.mark.live
    async def test_anthropic_with_tools_to_ollama_swap_live(self) -> None:
        """Tool-payload swap test (REQUIRED per leg §5).

        Exercises the actual cross-provider swap concern: tool_calls +
        tool_results encoded by one provider, re-sent through another.
        Recommended pair per leg: Anthropic ↔ Ollama qwen
        (qwen2.5:7b supports tools per F7 L7; if Anthropic doesn't call
        the tool — model decides — the for-loop over tool_calls is a no-op
        and the test still pins shape compatibility for the
        messages-without-tool-result swap path, which is also a valid
        swap shape).
        """
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip(
                "ANTHROPIC_API_KEY not set — operator must export the key to run this live test"
            )
        base_url, ollama_model = await _resolve_ollama()

        anthropic_model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        anthropic = AnthropicProvider(model=anthropic_model)
        ollama = OllamaProvider(model=ollama_model, base_url=base_url)

        tool_def = {
            "name": "noop",
            "description": "Returns the string 'ok'. Use this when asked.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
        history: list[Message] = [
            Message.system("Use the noop tool when asked."),
            Message.user("Call the noop tool."),
        ]
        try:
            # Step 1: Anthropic call with tools. The model decides whether
            # to use it.
            anthropic_reply = await anthropic.complete(
                history, tools=[tool_def], temperature=0.0, max_tokens=200
            )
            assert isinstance(anthropic_reply, Message)
            history.append(anthropic_reply)

            # Step 2: append a synthetic ToolResult for each tool_call (if
            # any). If Anthropic didn't call the tool, this loop is a
            # no-op — the test still pins shape compatibility for the
            # messages-without-tool-result swap path.
            for tc in anthropic_reply.tool_calls:
                history.append(Message.tool(ToolResult(tool_call_id=tc.id, content="ok")))

            # Step 3: re-send the WHOLE history through Ollama. The
            # cross-provider invariant being tested: Ollama accepts a
            # Message list whose ToolCall IDs were minted by Anthropic
            # (toolu_*) and whose ToolResult content rounded through
            # Anthropic's coercion path.
            ollama_reply = await ollama.complete(
                history, tools=[tool_def], temperature=0.0, max_tokens=200
            )
            assert isinstance(ollama_reply, Message)
            assert ollama_reply.role == Role.ASSISTANT
        finally:
            await _aclose_provider_client(anthropic)
            await _aclose_provider_client(ollama)

    @pytest.mark.live
    async def test_anthropic_to_openrouter_session_swap_live(self) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip(
                "ANTHROPIC_API_KEY not set — operator must export the key to run this live test"
            )
        if not os.environ.get("OPENROUTER_API_KEY"):
            pytest.skip(
                "OPENROUTER_API_KEY not set — operator must export the key to run this live test"
            )
        try:
            import openai
        except ImportError:
            pytest.skip("openai SDK (required by OpenRouter provider) not installed")

        anthropic_model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        openrouter_model = os.environ.get("LIVE_OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
        anthropic = AnthropicProvider(model=anthropic_model)
        openrouter = OpenRouterProvider(model=openrouter_model)

        try:
            # Step 1: minimal conversation under Anthropic.
            history: list[Message] = [
                Message.system("Reply with one word."),
                Message.user("Hello."),
            ]
            anthropic_reply = await anthropic.complete(history, temperature=0.0, max_tokens=50)
            assert isinstance(anthropic_reply, Message)
            assert anthropic_reply.role == Role.ASSISTANT
            history.append(anthropic_reply)

            # Step 2: continue the session under OpenRouter.
            history.append(Message.user("Same."))
            try:
                openrouter_reply = await openrouter.complete(
                    history, temperature=0.0, max_tokens=50
                )
            except openai.NotFoundError as exc:
                pytest.skip(
                    f"OpenRouter model {openrouter_model!r} not found: {exc}. "
                    f"Set LIVE_OPENROUTER_MODEL to a valid slug to override."
                )
            except (openai.PermissionDeniedError, openai.AuthenticationError) as exc:
                pytest.skip(f"OpenRouter auth/permission error: {type(exc).__name__}: {exc}.")
            assert isinstance(openrouter_reply, Message)
            assert openrouter_reply.role == Role.ASSISTANT
        finally:
            await _aclose_provider_client(anthropic)
            await _aclose_provider_client(openrouter)

    @pytest.mark.live
    async def test_openrouter_to_anthropic_session_swap_live(self) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip(
                "ANTHROPIC_API_KEY not set — operator must export the key to run this live test"
            )
        if not os.environ.get("OPENROUTER_API_KEY"):
            pytest.skip(
                "OPENROUTER_API_KEY not set — operator must export the key to run this live test"
            )
        try:
            import openai
        except ImportError:
            pytest.skip("openai SDK (required by OpenRouter provider) not installed")

        anthropic_model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        openrouter_model = os.environ.get("LIVE_OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
        anthropic = AnthropicProvider(model=anthropic_model)
        openrouter = OpenRouterProvider(model=openrouter_model)

        try:
            # Step 1: minimal conversation under OpenRouter.
            history: list[Message] = [
                Message.system("Reply with one word."),
                Message.user("Hello."),
            ]
            try:
                openrouter_reply = await openrouter.complete(
                    history, temperature=0.0, max_tokens=50
                )
            except openai.NotFoundError as exc:
                pytest.skip(
                    f"OpenRouter model {openrouter_model!r} not found: {exc}. "
                    f"Set LIVE_OPENROUTER_MODEL to a valid slug to override."
                )
            except (openai.PermissionDeniedError, openai.AuthenticationError) as exc:
                pytest.skip(f"OpenRouter auth/permission error: {type(exc).__name__}: {exc}.")
            assert isinstance(openrouter_reply, Message)
            history.append(openrouter_reply)

            # Step 2: continue the session under Anthropic.
            history.append(Message.user("Same."))
            anthropic_reply = await anthropic.complete(history, temperature=0.0, max_tokens=50)
            assert isinstance(anthropic_reply, Message)
            assert anthropic_reply.role == Role.ASSISTANT
        finally:
            await _aclose_provider_client(anthropic)
            await _aclose_provider_client(openrouter)

    @pytest.mark.live
    async def test_anthropic_tool_result_final_roundtrip_live(self) -> None:
        """Single-provider two-turn tool→result→final round-trip (M16 F04 L04, DD8).

        How this DIFFERS from ``test_anthropic_with_tools_to_ollama_swap_live``:
        that test is a CROSS-PROVIDER swap — Anthropic emits a tool_call, a
        synthetic ToolResult is appended, and the WHOLE history is re-sent
        through a DIFFERENT provider (Ollama), which never feeds the tool result
        back to the originating provider to produce a final answer. THIS test is
        a SAME-provider round-trip: Anthropic emits the tool_call, the test feeds
        back a real ToolResult, and the SAME Anthropic provider consumes it and
        produces the final answer (the live analog of the hermetic conformance
        round-trip). That single-provider two-turn shape is the coverage gap none
        of the four existing live swap tests fill.

        CONFIDENCE test, not a behavior pin — no exact-content assertions. If the
        model declines the tool (its choice), the round-trip isn't exercised;
        handled defensively (assert the turn-1 reply is a valid Message) rather
        than failing hard.
        """
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip(
                "ANTHROPIC_API_KEY not set — operator must export the key to run this live test"
            )

        anthropic_model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        provider = AnthropicProvider(model=anthropic_model)

        tool_def = {
            "name": "get_weather",
            "description": "Look up the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        }
        history: list[Message] = [
            Message.system("You MUST call the get_weather tool to answer."),
            Message.user("You MUST call the `get_weather` tool for Paris."),
        ]
        try:
            # Turn 1: the model decides whether to call the tool.
            reply = await provider.complete(
                history, tools=[tool_def], temperature=0.0, max_tokens=200
            )
            assert isinstance(reply, Message)
            assert reply.role == Role.ASSISTANT
            history.append(reply)

            if not reply.tool_calls:
                # Model declined the tool — round-trip not exercised. Do not fail:
                # the turn-1 reply being a valid Message is the confidence signal.
                pytest.skip(
                    "model declined the get_weather tool — same-provider "
                    "tool→result→final round-trip not exercised this run"
                )

            # Feed back a real ToolResult for each tool_call, then turn-2 through
            # the SAME provider for the final answer.
            for tc in reply.tool_calls:
                history.append(
                    Message.tool(ToolResult(tool_call_id=tc.id, content="sunny, 22C"))
                )
            final = await provider.complete(
                history, tools=[tool_def], temperature=0.0, max_tokens=200
            )
            assert isinstance(final, Message)
            assert final.role == Role.ASSISTANT
            # NO content assertions — model behavior is non-deterministic.
        finally:
            await _aclose_provider_client(provider)

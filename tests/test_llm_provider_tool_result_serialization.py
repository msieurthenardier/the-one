"""Per-provider tests for ``ToolResult.content`` serialization at the
``_to_api_message`` boundary.

M11 F8 L2: the canonical wire-shape for ``ToolResult.content`` is ``str``.
``ToolResult.__post_init__`` JSON-normalizes non-str content at
construction (``the_one/llm/base.py``) so every provider's
``_to_api_message`` receives ``str`` uniformly — no provider-specific
coercion at the encoder boundary. This replaces F7 12.l's per-encoder
Anthropic-only coercion with a single canonical-shape invariant at the
dataclass boundary.

Three per-provider classes (preserved from the pre-L2 file layout for
git-blame continuity) pin the post-L2 boundary: ``_to_api_message`` is
a pass-through for ``str`` content, with no provider-specific JSON
encoding. Two additional classes pin the construction-time invariants:

  - ``TestToolResultContentNormalizationAtConstruction`` — non-str
    ``ToolResult`` content is JSON-stringified at ``__init__`` time;
    str content round-trips byte-identical.
  - ``TestMessageContentInvariantAtConstruction`` — non-str
    ``Message.content`` raises ``AssertionError`` at ``__init__`` time
    (deliberate asymmetry — see ``the_one/agents.md`` →
    ``provider-shape-portability``).

See ``the_one/agents.md`` → ``provider-shape-portability``.
"""

from __future__ import annotations

import json

import pytest

from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message, Role, ToolResult
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OpenAIProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anthropic_provider() -> AnthropicProvider:
    return AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    return OpenAIProvider(model="gpt-4o", api_key="test-key")


@pytest.fixture
def ollama_provider() -> OllamaProvider:
    return OllamaProvider(model="qwen2.5:7b", base_url="http://test:11434")


# Representative structured returns from L10 connector-context tools
# (see ``the_one/tools/connector_history.py`` for the source shapes).
LIST_OF_DICTS_RESULT: list[dict[str, object]] = [
    {
        "peer_id": "1234567890",
        "peer_name": "alice",
        "content": "hey bot",
        "ts": "2026-05-26T01:23:45Z",
    },
    {
        "peer_id": "9876543210",
        "peer_name": "bob",
        "content": "second message",
        "ts": "2026-05-26T01:24:01Z",
    },
]

DICT_RESULT: dict[str, object] = {
    "channels": [
        {"id": "ch1", "name": "general"},
        {"id": "ch2", "name": "random"},
    ],
}


# ---------------------------------------------------------------------------
# Construction-time normalization — the L2 invariant
# ---------------------------------------------------------------------------


class TestToolResultContentNormalizationAtConstruction:
    """``ToolResult.__post_init__`` JSON-stringifies non-str content at
    construction so every downstream consumer reads ``str`` uniformly.

    This is the canonical-shape invariant the L2 leg ships; the
    provider-encoder pass-through tests below all rely on it.
    """

    def test_tool_result_normalizes_list_of_dicts_to_json_string(self) -> None:
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT)
        assert isinstance(tr.content, str)
        assert json.loads(tr.content) == LIST_OF_DICTS_RESULT

    def test_tool_result_normalizes_dict_to_json_string(self) -> None:
        tr = ToolResult(tool_call_id="t1", content=DICT_RESULT)
        assert isinstance(tr.content, str)
        assert json.loads(tr.content) == DICT_RESULT

    def test_tool_result_preserves_string_content_byte_identical(self) -> None:
        """str content is NOT re-JSON-encoded — byte-identical pass-through."""
        tr = ToolResult(tool_call_id="t1", content="plain string result")
        assert tr.content == "plain string result"

    def test_tool_result_normalizes_nested_structure(self) -> None:
        nested: dict[str, object] = {"channels": [{"id": "ch1", "members": [{"name": "alice"}]}]}
        tr = ToolResult(tool_call_id="t1", content=nested)
        assert isinstance(tr.content, str)
        assert json.loads(tr.content) == nested

    def test_message_tool_factory_with_non_str_tool_result_content_works(
        self,
    ) -> None:
        """``Message.tool(ToolResult(content=non_str))`` succeeds because
        ``ToolResult.__post_init__`` runs FIRST, so ``result.content`` is
        already str by the time ``Message.tool`` constructs the Message.
        """
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT)
        msg = Message.tool(tr)
        assert isinstance(msg.content, str)
        assert msg.content == tr.content
        assert json.loads(msg.content) == LIST_OF_DICTS_RESULT


# ---------------------------------------------------------------------------
# Message.content invariant — the L2 deliberate-asymmetry assert
# ---------------------------------------------------------------------------


class TestMessageContentInvariantAtConstruction:
    """``Message.__post_init__`` asserts ``isinstance(content, str)`` at
    construction time. Non-str arrival is a provider-parser defect (the
    deliberate asymmetry vs ``ToolResult``: structured tool returns are
    legitimate; non-str on a ``Message`` is not).
    """

    def test_message_with_non_str_content_raises_assertion_error(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.USER, content=42)  # type: ignore[arg-type]

    def test_message_with_none_content_raises_assertion_error(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.ASSISTANT, content=None)  # type: ignore[arg-type]

    def test_message_with_dict_content_raises_assertion_error(self) -> None:
        with pytest.raises(AssertionError):
            Message(role=Role.USER, content={"k": "v"})  # type: ignore[arg-type]

    def test_factory_methods_build_str_content_messages(self) -> None:
        """``Message.system``/``user``/``assistant``/``tool`` all build
        str-content messages — the assertion passes for all four.
        """
        assert isinstance(Message.system("sys").content, str)
        assert isinstance(Message.user("u").content, str)
        assert isinstance(Message.assistant("a").content, str)
        # Message.tool sources content from result.content which
        # ToolResult.__post_init__ guarantees is str.
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT)
        assert isinstance(Message.tool(tr).content, str)


# ---------------------------------------------------------------------------
# Anthropic: post-L2, the encoder is a str pass-through (no per-encoder
# coercion — the F7 12.l hotfix is replaced by the dataclass invariant).
# ---------------------------------------------------------------------------


class TestAnthropicToolResultSerialization:
    """Post-L2 ``_to_api_message`` is a pass-through: it receives
    str-normalized content from ``ToolResult.__post_init__`` and emits
    it verbatim in the Anthropic ``tool_result`` content block. No
    provider-specific coercion remains at this boundary.
    """

    def test_anthropic_encodes_normalized_list_content_as_str_block(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        tr = ToolResult(tool_call_id="toolu_test_id", content=LIST_OF_DICTS_RESULT)
        msg = Message.tool(tr)
        result = anthropic_provider._to_api_message(msg)
        assert result["role"] == "user"
        assert len(result["content"]) == 1
        block = result["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "toolu_test_id"
        assert block["is_error"] is False
        # Post-L2: encoder is a pass-through. The block's content is the
        # already-normalized str from ToolResult.__post_init__.
        assert block["content"] == tr.content
        assert isinstance(block["content"], str)
        assert json.loads(block["content"]) == LIST_OF_DICTS_RESULT

    def test_anthropic_encodes_normalized_dict_content_as_str_block(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        tr = ToolResult(tool_call_id="toolu_test_id", content=DICT_RESULT)
        msg = Message.tool(tr)
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert block["content"] == tr.content
        assert json.loads(block["content"]) == DICT_RESULT

    def test_anthropic_passes_string_content_through_unchanged(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        """Legacy str path: byte-identical round-trip. This pins
        back-compat — a future "always JSON-encode" refactor would
        surface here as a regression.
        """
        tr = ToolResult(tool_call_id="toolu_test_id", content="plain string result")
        msg = Message.tool(tr)
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert block["content"] == "plain string result"

    def test_anthropic_preserves_is_error_flag_through_encoder(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        tr = ToolResult(
            tool_call_id="toolu_test_id",
            content=LIST_OF_DICTS_RESULT,
            is_error=True,
        )
        msg = Message.tool(tr)
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert block["is_error"] is True
        assert isinstance(block["content"], str)


# ---------------------------------------------------------------------------
# OpenAI: post-L2 the encoder still pass-through; the difference from
# pre-L2 is that the content reaching it is already str-normalized.
# ---------------------------------------------------------------------------


class TestOpenAIToolResultSerialization:
    def test_openai_encodes_normalized_content_as_str(
        self, openai_provider: OpenAIProvider
    ) -> None:
        """Post-L2 the OpenAI encoder receives str-normalized content
        (from ToolResult.__post_init__). The emitted shape is identical
        to the pre-L2 behavior for str content, but the content reaching
        the encoder is now always str (where pre-L2 it would have been
        the raw list/dict).
        """
        tr = ToolResult(tool_call_id="toolu_test_id", content=LIST_OF_DICTS_RESULT)
        msg = Message.tool(tr)
        result = openai_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": tr.content,  # already-normalized str
        }
        assert isinstance(result["content"], str)
        assert json.loads(result["content"]) == LIST_OF_DICTS_RESULT

    def test_openai_passes_string_content_through_unchanged(
        self, openai_provider: OpenAIProvider
    ) -> None:
        tr = ToolResult(tool_call_id="toolu_test_id", content="plain string result")
        msg = Message.tool(tr)
        result = openai_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": "plain string result",
        }


# ---------------------------------------------------------------------------
# Ollama: same shape as OpenAI; post-L2 receives str-normalized content.
# ---------------------------------------------------------------------------


class TestOllamaToolResultSerialization:
    def test_ollama_encodes_normalized_content_as_str(
        self, ollama_provider: OllamaProvider
    ) -> None:
        tr = ToolResult(tool_call_id="toolu_test_id", content=LIST_OF_DICTS_RESULT)
        msg = Message.tool(tr)
        result = ollama_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": tr.content,  # already-normalized str
        }
        assert isinstance(result["content"], str)
        assert json.loads(result["content"]) == LIST_OF_DICTS_RESULT

    def test_ollama_passes_string_content_through_unchanged(
        self, ollama_provider: OllamaProvider
    ) -> None:
        tr = ToolResult(tool_call_id="toolu_test_id", content="plain string result")
        msg = Message.tool(tr)
        result = ollama_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": "plain string result",
        }

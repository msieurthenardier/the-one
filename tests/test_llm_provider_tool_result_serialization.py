"""Per-provider tests for ``ToolResult.content`` serialization at the
``_to_api_message`` boundary.

M11 F7 L12.l: hotfix for a pre-F7 agent serialization bug. When an L10
connector-context tool (``list_visible_channels``, ``fetch_channel_history``,
``fetch_thread_history``, ``fetch_dm_history``) returns a Python dict or
list (its declared return type per ``the_one/tools/connector_history.py``),
the structured value flows through the agent loop into
``ToolResult.content`` despite the field's ``str`` type annotation —
dataclass type hints are not enforced at runtime. The Anthropic Messages
API strictly requires ``tool_result.content`` to be a string or a list of
content blocks; passing a dict raises::

    400 invalid_request_error
    messages.N.content.M.tool_result.content:
      Found an object, but `tool_result` content must either be a string or
      a list of content blocks.

The fix coerces non-string ``ToolResult.content`` to ``json.dumps(content)``
at the Anthropic provider's ``_to_api_message`` site only. The OpenAI /
Ollama paths' SDKs accept dicts/objects through to the wire and the
hotfix preserves their pre-fix pass-through behaviour — this test pins
both halves of that contract.

The test ALSO pins the legacy string-content path (Anthropic, OpenAI,
Ollama) so a future "always JSON-encode" refactor would surface a
behavioural regression on the byte-identical str→str round-trip.
"""

from __future__ import annotations

import json

import pytest

from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message, ToolResult
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


def _make_tool_msg(content: object, *, is_error: bool = False) -> Message:
    """Build a TOOL-role Message whose ``ToolResult.content`` carries
    the raw (possibly non-str) value the agent would feed in.

    Bypasses ``ToolResult(...)``'s str-typed constructor signature via
    direct field assignment — mirrors the runtime contract: dataclass
    type hints don't enforce at runtime, and several L10 tools return
    dict/list values that land here unchanged.
    """
    tr = ToolResult(tool_call_id="toolu_test_id", content="")
    tr.content = content  # type: ignore[assignment]
    tr.is_error = is_error
    return Message.tool(tr)


# ---------------------------------------------------------------------------
# Anthropic: the bug site. Coerce dict/list to JSON string.
# ---------------------------------------------------------------------------


class TestAnthropicToolResultSerialization:
    def test_anthropic_coerces_list_of_dicts_to_json_string(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        """L10 ``list_visible_channels`` / ``fetch_channel_history`` etc.
        return ``list[dict]``. The Anthropic API rejects an object here
        with 400 ``invalid_request_error``; coercion to a JSON string
        is the contract.
        """
        msg = _make_tool_msg(LIST_OF_DICTS_RESULT)
        result = anthropic_provider._to_api_message(msg)
        assert result["role"] == "user"
        assert len(result["content"]) == 1
        block = result["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "toolu_test_id"
        assert block["is_error"] is False
        # The load-bearing assertion: content is a STRING (not an object).
        assert isinstance(block["content"], str)
        # And the string is the JSON-serialized form of the structured value.
        assert json.loads(block["content"]) == LIST_OF_DICTS_RESULT

    def test_anthropic_coerces_dict_to_json_string(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        """A tool returning a top-level dict (e.g. ``{"channels": [...]}``)
        triggers the same Anthropic 400; coercion applies identically.
        """
        msg = _make_tool_msg(DICT_RESULT)
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert isinstance(block["content"], str)
        assert json.loads(block["content"]) == DICT_RESULT

    def test_anthropic_passes_string_content_through_unchanged(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        """Legacy path: when content is already a string (the typed
        ``ToolResult.content: str`` contract), it round-trips byte-
        identically. This pins back-compat — a future "always JSON-encode"
        refactor would surface here as a regression.
        """
        msg = _make_tool_msg("plain string result")
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert block["content"] == "plain string result"

    def test_anthropic_preserves_is_error_flag(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        msg = _make_tool_msg(LIST_OF_DICTS_RESULT, is_error=True)
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert block["is_error"] is True
        assert isinstance(block["content"], str)


# ---------------------------------------------------------------------------
# OpenAI: hotfix MUST NOT alter the historic pass-through behaviour.
# ---------------------------------------------------------------------------


class TestOpenAIToolResultSerialization:
    def test_openai_passes_dict_content_through_unchanged(
        self, openai_provider: OpenAIProvider
    ) -> None:
        """The OpenAI SDK tolerates dict/object content on ``tool``-role
        messages; the historic behaviour is pass-through. The Anthropic
        hotfix MUST NOT touch this path.
        """
        msg = _make_tool_msg(LIST_OF_DICTS_RESULT)
        result = openai_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": LIST_OF_DICTS_RESULT,
        }

    def test_openai_passes_string_content_through_unchanged(
        self, openai_provider: OpenAIProvider
    ) -> None:
        msg = _make_tool_msg("plain string result")
        result = openai_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": "plain string result",
        }


# ---------------------------------------------------------------------------
# Ollama: also a pass-through; pin the same contract.
# ---------------------------------------------------------------------------


class TestOllamaToolResultSerialization:
    def test_ollama_passes_dict_content_through_unchanged(
        self, ollama_provider: OllamaProvider
    ) -> None:
        msg = _make_tool_msg(LIST_OF_DICTS_RESULT)
        result = ollama_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": LIST_OF_DICTS_RESULT,
        }

    def test_ollama_passes_string_content_through_unchanged(
        self, ollama_provider: OllamaProvider
    ) -> None:
        msg = _make_tool_msg("plain string result")
        result = ollama_provider._to_api_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "toolu_test_id",
            "content": "plain string result",
        }

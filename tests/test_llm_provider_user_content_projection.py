"""Per-provider tests for the L4 inline-prefix projection.

M11 F7 L4: closes F6 Rec #4 / M11 criterion #13.

Each provider's ``_to_api_message`` is invoked directly with a USER-role
``Message`` and the resulting dict's ``content`` value is asserted against
the expected projection. A cross-provider parity test pins that all four
adapters (OpenAI, Anthropic, Ollama, and OpenRouter via OpenAIProvider
inheritance) emit byte-identical ``content`` strings for the same Message.

The parity test instantiates concrete provider objects per the leg
artifact's explicit requirement — identity (``OpenRouterProvider._to_api_message
is OpenAIProvider._to_api_message``) is covered by the verification grep;
this test pins behavioural parity so a future override that returns the
same shape but elides the helper call would still be caught.
"""

from __future__ import annotations

import pytest

from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message, Role
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OpenAIProvider
from the_one.llm.openrouter_provider import OpenRouterProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    return OpenAIProvider(model="gpt-4o", api_key="test-key")


@pytest.fixture
def anthropic_provider() -> AnthropicProvider:
    return AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")


@pytest.fixture
def ollama_provider() -> OllamaProvider:
    return OllamaProvider(model="qwen2.5:7b", base_url="http://test:11434")


@pytest.fixture
def openrouter_provider() -> OpenRouterProvider:
    return OpenRouterProvider(model="anthropic/claude-3.5-sonnet", api_key="test-key")


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------


class TestOpenAIToApiMessageProjection:
    def test_openai_to_api_message_user_with_peer_name_and_channel_name(
        self, openai_provider: OpenAIProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice", channel_name="general")
        result = openai_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice in #general]: hi"}

    def test_openai_to_api_message_user_with_peer_name_only(
        self, openai_provider: OpenAIProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice")
        result = openai_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice]: hi"}

    def test_openai_to_api_message_user_with_no_attribution(
        self, openai_provider: OpenAIProvider
    ) -> None:
        # Byte-identical legacy payload: content key matches msg.content
        # directly when both peer_name and channel_name are None.
        msg = Message.user("hi")
        result = openai_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "hi"}

    def test_openai_to_api_message_assistant_unchanged_by_projection(
        self, openai_provider: OpenAIProvider
    ) -> None:
        # Assistant message with no tool_calls falls through to the
        # role-content shape; the helper's defensive non-USER branch
        # returns msg.content unchanged, so no prefix appears even if
        # peer_name happens to be set (which it never should be on
        # assistant messages, but the test pins the safety net).
        msg = Message(role=Role.ASSISTANT, content="hi", peer_name="alice")
        result = openai_provider._to_api_message(msg)
        assert result == {"role": "assistant", "content": "hi"}


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------


class TestAnthropicToApiMessageProjection:
    def test_anthropic_to_api_message_user_with_peer_name_and_channel_name(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice", channel_name="general")
        result = anthropic_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice in #general]: hi"}

    def test_anthropic_to_api_message_user_with_peer_name_only(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice")
        result = anthropic_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice]: hi"}

    def test_anthropic_to_api_message_user_with_no_attribution(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        msg = Message.user("hi")
        result = anthropic_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "hi"}

    def test_anthropic_to_api_message_assistant_unchanged_by_projection(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        msg = Message(role=Role.ASSISTANT, content="hi", peer_name="alice")
        result = anthropic_provider._to_api_message(msg)
        assert result == {"role": "assistant", "content": "hi"}


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class TestOllamaToApiMessageProjection:
    def test_ollama_to_api_message_user_with_peer_name_and_channel_name(
        self, ollama_provider: OllamaProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice", channel_name="general")
        result = ollama_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice in #general]: hi"}

    def test_ollama_to_api_message_user_with_peer_name_only(
        self, ollama_provider: OllamaProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice")
        result = ollama_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice]: hi"}

    def test_ollama_to_api_message_user_with_no_attribution(
        self, ollama_provider: OllamaProvider
    ) -> None:
        msg = Message.user("hi")
        result = ollama_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "hi"}

    def test_ollama_to_api_message_assistant_unchanged_by_projection(
        self, ollama_provider: OllamaProvider
    ) -> None:
        msg = Message(role=Role.ASSISTANT, content="hi", peer_name="alice")
        result = ollama_provider._to_api_message(msg)
        assert result == {"role": "assistant", "content": "hi"}


# ---------------------------------------------------------------------------
# OpenRouterProvider (inherits _to_api_message from OpenAIProvider)
# ---------------------------------------------------------------------------


class TestOpenRouterToApiMessageProjection:
    def test_openrouter_to_api_message_user_with_peer_name_and_channel_name(
        self, openrouter_provider: OpenRouterProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice", channel_name="general")
        result = openrouter_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice in #general]: hi"}

    def test_openrouter_to_api_message_user_with_peer_name_only(
        self, openrouter_provider: OpenRouterProvider
    ) -> None:
        msg = Message.user("hi", peer_name="alice")
        result = openrouter_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "[from alice]: hi"}

    def test_openrouter_to_api_message_user_with_no_attribution(
        self, openrouter_provider: OpenRouterProvider
    ) -> None:
        msg = Message.user("hi")
        result = openrouter_provider._to_api_message(msg)
        assert result == {"role": "user", "content": "hi"}

    def test_openrouter_to_api_message_assistant_unchanged_by_projection(
        self, openrouter_provider: OpenRouterProvider
    ) -> None:
        msg = Message(role=Role.ASSISTANT, content="hi", peer_name="alice")
        result = openrouter_provider._to_api_message(msg)
        assert result == {"role": "assistant", "content": "hi"}


# ---------------------------------------------------------------------------
# Cross-provider parity
# ---------------------------------------------------------------------------


class TestUserContentProjectionParityAcrossProviders:
    def test_user_content_projection_parity_across_providers(
        self,
        openai_provider: OpenAIProvider,
        anthropic_provider: AnthropicProvider,
        ollama_provider: OllamaProvider,
        openrouter_provider: OpenRouterProvider,
    ) -> None:
        # Same Message → all four providers emit the same ``content`` string.
        # The parity test must instantiate concrete provider objects and
        # call ``_to_api_message(msg)`` on each instance — NOT a method-
        # identity check (identity is covered by the verification grep +
        # python one-liner). This pins that a future override on any
        # subclass that returns the same shape but elides the helper call
        # would be caught.
        msg = Message.user("hi", peer_name="alice", channel_name="general")
        openai_content = openai_provider._to_api_message(msg)["content"]
        anthropic_content = anthropic_provider._to_api_message(msg)["content"]
        ollama_content = ollama_provider._to_api_message(msg)["content"]
        openrouter_content = openrouter_provider._to_api_message(msg)["content"]
        assert openai_content == anthropic_content == ollama_content == openrouter_content
        assert openai_content == "[from alice in #general]: hi"

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_result: ToolResult | None = None
    usage: TokenUsage | None = None

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(
        cls, content: str, tool_calls: list[ToolCall] | None = None, usage: TokenUsage | None = None
    ) -> Message:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls or [], usage=usage)

    @classmethod
    def tool(cls, result: ToolResult) -> Message:
        return cls(role=Role.TOOL, content=result.content, tool_result=result)


@dataclass
class StreamChunk:
    """Single chunk emitted by ``LLMProvider.stream``.

    ``content`` carries the NEW tokens since the last chunk (delta semantics —
    NOT cumulative). On the final chunk, ``is_final=True``; ``tool_calls``,
    ``usage`` and ``message`` are populated where the provider exposes them.
    The ``message`` field carries the synthesized assistant ``Message`` and
    is what ``Agent.step`` appends to its history.
    """

    content: str = ""
    is_final: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage | None = None
    message: Message | None = None


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: str
    max_context_tokens: int = 128_000

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        """Send messages to the LLM and get a response."""
        ...

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        """Default streaming implementation: call ``complete()``, yield one final chunk.

        Providers SHOULD override with native streaming for better UX.
        Forward-compat for any future provider that doesn't natively stream.
        """
        msg = await self.complete(messages, tools, temperature, max_tokens)
        yield StreamChunk(
            content=msg.content,
            is_final=True,
            tool_calls=msg.tool_calls,
            usage=msg.usage,
            message=msg,
        )

    def tool_schema(self, tool_def: dict[str, Any]) -> dict[str, Any]:
        """Convert a canonical tool definition to this provider's format.

        Override in subclasses if the provider uses a different schema.
        Default assumes OpenAI-style function calling format.
        """
        return {
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def["description"],
                "parameters": tool_def["parameters"],
            },
        }

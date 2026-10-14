"""A sequence-scripted LLM provider (DD18).

Plays a list of ``Message`` responses in order, each with optional ``tool_calls``,
and records every call's messages and tool schemas. Unlike the dev-mode ``mock``
provider (which returns the same response on every call, so a scripted tool call
repeats until ``max_iterations``) this one advances through its script.

Shaped like ``tests/conftest.py::FakeLLM``; copied, not imported, because
``evals/`` never imports ``tests/``. An item may also be an exception instance,
which is raised instead of returned (to drive the run-outcome rules).
"""

from __future__ import annotations

import copy
from typing import Any

from the_one.llm.base import LLMProvider, Message, TokenUsage, ToolCall

DEFAULT_USAGE = TokenUsage(input_tokens=10, output_tokens=5)


def text(content: str, *, input_tokens: int = 10, output_tokens: int = 5) -> Message:
    """A final assistant reply."""
    return Message.assistant(
        content=content,
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def call(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    call_id: str | None = None,
    content: str = "",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Message:
    """An assistant turn that makes one tool call."""
    return Message.assistant(
        content=content,
        tool_calls=[ToolCall(id=call_id or f"call_{name}", name=name, arguments=arguments or {})],
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class ScriptedProvider(LLMProvider):
    """Returns pre-scripted responses in order; raises an exception item."""

    name = "scripted"

    def __init__(self, script: list[Message | BaseException], *, supports_tools: bool = True):
        super().__init__()
        self.script: list[Message | BaseException] = list(script)
        self.calls: list[dict[str, Any]] = []
        self._supports_tools = supports_tools

    async def supports_tools(self) -> bool:
        return self._supports_tools

    @property
    def remaining(self) -> int:
        return len(self.script)

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,
    ) -> Message:
        self.calls.append(
            {
                "messages": copy.copy(messages),
                "tools": copy.deepcopy(tools),
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if not self.script:
            raise AssertionError("ScriptedProvider script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if item.usage is None:
            item.usage = TokenUsage(DEFAULT_USAGE.input_tokens, DEFAULT_USAGE.output_tokens)
        return item

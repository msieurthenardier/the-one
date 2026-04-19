"""Shared test fixtures: FakeLLM, StubTool, registry helpers, markers."""

from __future__ import annotations

from typing import Any

import pytest

from the_one.llm.base import LLMProvider, Message
from the_one.tools.base import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# FakeLLM
# ---------------------------------------------------------------------------

class FakeLLM(LLMProvider):
    """LLM provider that returns pre-scripted responses in order."""

    name = "fake"

    def __init__(self, responses: list[Message]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# StubTool
# ---------------------------------------------------------------------------

class StubTool(Tool):
    """Tool that records calls and returns a canned response."""

    def __init__(self, name: str, description: str = "A stub tool.") -> None:
        self.name = name
        self.description = description
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"stub: {self.name}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_registry() -> ToolRegistry:
    """Create a ToolRegistry pre-loaded with stub tools."""
    registry = ToolRegistry()
    for tool_name in ("tool_a", "tool_b", "tool_c"):
        registry.register(StubTool(tool_name))
    return registry

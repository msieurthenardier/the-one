"""Shared test fixtures: FakeLLM, StubTool, registry helpers, markers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from the_one.llm.base import LLMProvider, Message
from the_one.tools.base import Tool, ToolRegistry

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # tests/conftest.py → project root

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
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# StubTool
# ---------------------------------------------------------------------------


class StubTool(Tool):
    """Tool that records calls and returns a canned response."""

    def __init__(
        self,
        name: str,
        description: str = "A stub tool.",
        cross_configs: dict[Any, Any] | None = None,
        agent_name: str | None = None,
    ) -> None:
        # L1b: widen to accept cross_configs/agent_name kwargs so this stub
        # works on the BuiltinToolProvider factory path. We do not call
        # `super().__init__()` because StubTool has no Config schema and the
        # tests intentionally use a plain `name`-positional constructor; we
        # mirror the base class's storage of the new fields so factory-path
        # plumbing assertions (e.g. `_agent_name`) succeed.
        self.name = name
        self.description = description
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.calls: list[dict[str, Any]] = []
        self._cross_configs = cross_configs or {}
        self._agent_name = agent_name

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


# ---------------------------------------------------------------------------
# MCP fixtures (F2 L3) — shared by L4 (streamable-http) and L5 (stdio)
# integration tests, plus the L3 smoke tests in tests/test_mcp_integration.py.
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_fixture_stdio_params() -> dict[str, Any]:
    """StdioServerParameters-shaped dict pointing at the in-repo hello fixture.

    Returns a dict (not the typed object) so callers don't need to import the
    SDK type at test-collection time. Construct via:

        from mcp.client.stdio import StdioServerParameters
        params = StdioServerParameters(**fixture)

    Each test gets a fresh params dict; the SDK's stdio_client manages the
    subprocess lifetime.
    """
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(_PROJECT_ROOT),
    }
    return {
        "command": sys.executable,
        "args": ["-m", "tests.fixtures.mcp.hello_server", "--stdio"],
        "env": env,
        "cwd": None,
    }


@pytest.fixture
async def mcp_fixture_http_client():
    """In-process httpx.AsyncClient wrapping a FRESH FastMCP ASGI app per test.

    Three non-obvious requirements (verified at leg-design review):
      1. Calls ``make_mcp_app()`` per-test — module-level ``mcp_app`` cannot be
         reused because ``StreamableHTTPSessionManager.run()`` enforces
         once-per-instance.
      2. Drives Starlette lifespan via ``asgi_lifespan.LifespanManager`` —
         ``httpx.ASGITransport`` does NOT auto-fire lifespan events, so the
         FastMCP session manager's task group would otherwise be unstarted.
      3. Uses ``base_url="http://localhost"`` and ``url="http://localhost/mcp"``
         — FastMCP auto-enables DNS-rebinding protection for ``host="127.0.0.1"``
         constructor default; the localhost form matches the allowlist (and
         ``make_mcp_app()`` also disables protection at the FastMCP level for
         defense-in-depth).
    """
    import httpx
    from asgi_lifespan import LifespanManager

    from tests.fixtures.mcp.hello_server import make_mcp_app

    app = make_mcp_app().streamable_http_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://localhost")
        try:
            yield client, "http://localhost/mcp"
        finally:
            await client.aclose()

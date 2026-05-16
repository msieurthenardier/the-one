"""L3 — ContextVar canonical-home + per-tool-dispatch binding tests.

Locks:
  - ContextVar definition lives at the_one.agent._context (canonical home).
  - the_one.interfaces.web.app re-exports for F5 set-site back-compat.
  - Agent._execute_tool binds current_tool_call_id per-dispatch.
  - _pool_default sentinel grep returns zero hits in production code.
  - build_oauth_provider_for_source short-circuits on chat_session_id=None.

Per A1/A2/A3 process learning, this file MUST NOT depend on the MCP pool
worker (``tests/test_mcp_pool.py`` is env-dependent; the OAuth provider
construction inside ``_entry_worker`` calls ``get_connection()`` which
hangs on aiosqlite worker-thread setup outside docker). The tests below
exercise the agent layer directly and stub the provider-factory path
without spinning up the pool.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from the_one.agent._context import current_tool_call_id
from the_one.agent.core import Agent
from the_one.llm.base import Message, ToolCall
from the_one.mcp.errors import MCPAuthRequired
from the_one.mcp.oauth import build_oauth_provider_for_source
from the_one.tools.base import Tool, ToolRegistry

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CapturingTool(Tool):
    """Tool that captures ``current_tool_call_id`` at execute-time."""

    def __init__(self, name: str = "capture") -> None:
        self.name = name
        self.description = "captures current_tool_call_id"
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.captured_tcid: str | None = "<unset-sentinel>"

    async def execute(self, **kwargs: Any) -> str:
        # Capture INSIDE the tool's execute — the agent has bound the
        # ContextVar before delegating; resetting happens in _execute_tool's
        # finally AFTER this returns.
        self.captured_tcid = current_tool_call_id.get(None)
        return "ok"


class _MCPAuthRaisingTool(Tool):
    """Tool that raises ``MCPAuthRequired`` from inside ``execute``."""

    def __init__(self, name: str = "raises_auth") -> None:
        self.name = name
        self.description = "raises MCPAuthRequired"
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        raise MCPAuthRequired(
            "src-1",
            resource_metadata_url=None,
            consent_url=None,
        )


class _GenericRaisingTool(Tool):
    """Tool that raises a generic ``RuntimeError`` from inside ``execute``."""

    def __init__(self, name: str = "raises_generic") -> None:
        self.name = name
        self.description = "raises RuntimeError"
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        raise RuntimeError("boom")


def _make_agent(*tools: Tool) -> Agent:
    """Build an Agent with a stub LLM and the supplied tools registered."""

    class _StubLLM:
        name = "stub"

        async def complete(self, *args: Any, **kwargs: Any) -> Message:
            return Message.assistant("noop")

    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return Agent(llm=_StubLLM(), tools=reg, system_prompt="test")


# ---------------------------------------------------------------------------
# TestContextVarsCanonicalHome
# ---------------------------------------------------------------------------


class TestContextVarsCanonicalHome:
    def test_canonical_definitions_exist(self) -> None:
        """Both ContextVars exist at the canonical home with correct names + defaults."""
        from the_one.agent._context import current_chat_session_id, current_tool_call_id

        assert current_chat_session_id.name == "current_chat_session_id"
        assert current_tool_call_id.name == "current_tool_call_id"
        assert current_chat_session_id.get(None) is None
        assert current_tool_call_id.get(None) is None

    def test_app_reexport_resolves_to_same_object(self) -> None:
        """F5 set-sites at app.py:236, :256, :835, :857 see the canonical object."""
        from the_one.agent._context import current_chat_session_id as canonical_csid
        from the_one.interfaces.web.app import (
            current_chat_session_id as reexported_csid,
        )

        assert canonical_csid is reexported_csid  # re-export identity preserved

    def test_app_reexports_tool_call_id_too(self) -> None:
        """``current_tool_call_id`` is also re-exported from app.py for future use."""
        from the_one.agent._context import current_tool_call_id as canonical_tcid
        from the_one.interfaces.web.app import (
            current_tool_call_id as reexported_tcid,
        )

        assert canonical_tcid is reexported_tcid


# ---------------------------------------------------------------------------
# TestPerToolDispatchBinding
# ---------------------------------------------------------------------------


class TestPerToolDispatchBinding:
    async def test_unset_at_function_entry_by_default(self) -> None:
        """Outside of any ``_execute_tool`` invocation, the ContextVar is None."""
        assert current_tool_call_id.get(None) is None

    async def test_value_observable_inside_tool_execute(self) -> None:
        """``_execute_tool`` binds tool_call.id; the tool sees it via .get(None)."""
        tool = _CapturingTool()
        agent = _make_agent(tool)
        call = ToolCall(id="tc-42", name="capture", arguments={})
        result = await agent._execute_tool(call)

        assert result.tool_call_id == "tc-42"
        assert tool.captured_tcid == "tc-42"

    async def test_reset_to_none_after_normal_return(self) -> None:
        """After a successful ``_execute_tool``, ContextVar resets to None."""
        tool = _CapturingTool()
        agent = _make_agent(tool)
        await agent._execute_tool(ToolCall(id="tc-43", name="capture", arguments={}))

        assert current_tool_call_id.get(None) is None

    async def test_reset_after_mcp_auth_required_path(self) -> None:
        """The MCPAuthRequired translation path still traverses the outer finally."""
        tool = _MCPAuthRaisingTool()
        agent = _make_agent(tool)
        result = await agent._execute_tool(ToolCall(id="tc-44", name="raises_auth", arguments={}))

        # Translation fired:
        assert result.metadata is not None
        assert result.metadata.get("is_auth_required") is True
        assert result.metadata.get("tool_call_id") == "tc-44"
        # Reset fired:
        assert current_tool_call_id.get(None) is None

    async def test_reset_after_generic_exception_path(self) -> None:
        """The generic Exception fallthrough path still traverses the outer finally."""
        tool = _GenericRaisingTool()
        agent = _make_agent(tool)
        result = await agent._execute_tool(
            ToolCall(id="tc-45", name="raises_generic", arguments={})
        )

        assert result.is_error is True
        assert "Tool execution failed" in result.content
        assert current_tool_call_id.get(None) is None


# ---------------------------------------------------------------------------
# TestPoolDefaultSentinelRetired
# ---------------------------------------------------------------------------


class TestPoolDefaultSentinelRetired:
    def test_sentinel_grep_returns_zero_hits_in_production(self) -> None:
        """The F5 ``_pool_default`` sentinel is fully retired from the_one/."""
        result = subprocess.run(
            ["grep", "-rn", "_pool_default", "the_one/"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        # grep exits 1 when there are zero matches; capture either case.
        assert result.stdout.strip() == "", (
            f"expected zero _pool_default hits in production code, got:\n{result.stdout}"
        )

    def test_pool_entry_worker_uses_canonical_import(self) -> None:
        """``_entry_worker`` imports both ContextVars from the canonical module."""
        pool_src = (_PROJECT_ROOT / "the_one" / "mcp" / "_pool.py").read_text()
        assert (
            "from the_one.agent._context import current_chat_session_id, current_tool_call_id"
            in pool_src
        ), "pool must import csid + tcid from the canonical agent-layer module"
        assert "_pool_default" not in pool_src
        # The web-layer lazy-import is gone:
        assert "from the_one.interfaces.web.app import current_chat_session_id" not in pool_src


# ---------------------------------------------------------------------------
# TestProviderFactoryNoneCsidShortCircuit
# ---------------------------------------------------------------------------


class TestProviderFactoryNoneCsidShortCircuit:
    def test_returns_none_when_chat_session_id_is_none(self) -> None:
        """``chat_session_id=None`` short-circuits before any DB-touching code."""
        # Use a MagicMock for repo; a real repo isn't needed because the
        # short-circuit fires before any repo access.
        source = MagicMock()
        source.secrets = MagicMock()
        repo = MagicMock()

        result = build_oauth_provider_for_source(source, repo, None, source_id="src-1")
        assert result is None

    def test_short_circuit_runs_before_dcr_check(self) -> None:
        """When csid is None, ``source.secrets.get`` MUST NOT be called.

        The order matters: the dcr check would proceed to construct
        ``make_oauth_handlers`` if csid were a non-None falsy value (it
        isn't, by typing — but the contract is "None short-circuits BEFORE
        any other inspection"). Lock the order with a mock that errors on
        access.
        """
        source = MagicMock()
        # Configure source.secrets so ANY .get() call would raise — proves
        # the short-circuit fires first.
        source.secrets = MagicMock()
        source.secrets.get = MagicMock(
            side_effect=AssertionError("secrets.get must not be called when csid is None")
        )
        repo = MagicMock()

        result = build_oauth_provider_for_source(source, repo, None, source_id="src-1")
        assert result is None
        source.secrets.get.assert_not_called()

    def test_real_csid_falls_through_to_dcr_check(self) -> None:
        """A real csid string still hits the dcr early-return when secrets are empty."""
        source = MagicMock()
        # Empty dcr → original early-return at the second guard fires; result is None.
        source.secrets = {"dcr_credentials": None}
        repo = MagicMock()

        result = build_oauth_provider_for_source(source, repo, "real-csid-123", source_id="src-1")
        assert result is None  # dcr-absent still returns None, but via the dcr branch.

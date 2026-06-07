"""MCP client tool wrapper.

This module turns each server-supplied :class:`MCPTool` into a
:class:`Tool` subclass instance the agent's :class:`ToolRegistry` can
consume. Constructed by :class:`MCPToolProvider` per attached source at
agent-build time; one instance per server tool per agent build.

Prefix scheme (F6 §2): ``mcp__{normalize(source.name)}__{tool.name}``,
capped at 64 characters per the OpenAI / Anthropic tool-name ceiling
(see also `MCPRegistrationError`'s docstring). The constructor enforces
the ceiling and raises :class:`MCPRegistrationError` on overflow; the
provider catches per-tool and drops the offending tool with a WARNING
(NOT the entire source's tools — failure class #1 sub-case per F6 §8 /
cycle-1 M2).

Pattern note (cycle-1 medium #2): :class:`MCPClientTool` is the FIRST
:class:`Tool` subclass with dynamic per-instance ``name`` /
``description`` / ``parameters``. All other :class:`Tool` subclasses
(shell, filesystem, sessions, etc.) declare ``name = "..."`` at class
level. The base :class:`Tool` ``__init__`` does NOT touch those names,
so setting instance attrs BEFORE :func:`super().__init__` is safe.
"""

from __future__ import annotations

import re
from typing import Any

from the_one.db.models import MCPSource
from the_one.mcp._pool import acquire
from the_one.mcp.errors import (
    MCPConnectionError,
    MCPRegistrationError,
    MCPVersionMismatch,
    SandboxError,
)
from the_one.mcp.types import MCPTool
from the_one.tools.base import Tool

_TOOL_NAME_MAX_LEN = 64
"""LLM-side tool-name ceiling. OpenAI and Anthropic both cap tool names
at 64 characters; longer names are rejected at the provider boundary
with no useful diagnostic. F6 enforces the ceiling at registration time
so the operator gets a clean WARNING instead of a downstream provider
error."""

_PREFIX_OVERHEAD = len("mcp____")
"""Number of fixed characters the prefix scheme adds (``mcp__`` +
``__`` separator). Used by callers that want to compute the maximum
allowable tool-name length given a source name; not directly enforced
here (the constructor checks the full prefixed name's length)."""


def _normalize_source_name(name: str) -> str:
    """Return a source name normalized for use in tool-name prefixes.

    F1 source-name validation does not exist today; L2 normalizes
    defensively. Replace any character outside ``[a-zA-Z0-9_-]`` with
    underscore. Idempotent on already-normalized names.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


class MCPClientTool(Tool):
    """Tool wrapper that dispatches a server-supplied MCPTool through
    the F4 pool to the appropriate :class:`MCPClient`.

    Constructed by :class:`MCPToolProvider` per attached source. The
    constructor enforces the 64-character LLM tool-name ceiling and
    raises :class:`MCPRegistrationError` if the prefixed name would
    exceed it; the provider catches per-tool and drops the offending
    tool with a WARNING (NOT the entire source's tools).

    Pattern note (cycle-1 medium #2): :class:`MCPClientTool` is the
    FIRST :class:`Tool` subclass with dynamic per-instance names. All
    other :class:`Tool` subclasses (shell, filesystem, sessions, etc.)
    declare ``name = "..."`` at class level. The base class's
    ``__init__`` (``the_one/tools/base.py:61-99``) does NOT touch
    ``self.name`` / ``self.description`` / ``self.parameters`` — it
    only writes ``self._config``, ``self._cross_configs``,
    ``self._agent_name``. So setting instance attrs BEFORE
    :func:`super().__init__` is safe; the base won't clobber them.

    Cache-key trade-off (cycle-1 low #5 fix): the constructor takes
    ``effective_source`` — the override-applied :class:`MCPSource` that
    :class:`MCPToolProvider` built at agent-build time. :meth:`execute`
    passes this to :func:`acquire` as ``source_override``, so a
    post-OAuth re-acquire (after ``_evict_all_for_source``) re-applies
    the agent's override on the next pool spawn. Without this, the
    operator-side DB read inside ``_load_source`` would silently drop
    the agent's ``mcp_overrides``-derived credentials.
    """

    def __init__(
        self,
        mcp_tool: MCPTool,
        source_id: str,
        source_name: str,
        agent_name: str,
        effective_source: MCPSource,
    ) -> None:
        prefixed_name = f"mcp__{_normalize_source_name(source_name)}__{mcp_tool.name}"
        if len(prefixed_name) > _TOOL_NAME_MAX_LEN:
            raise MCPRegistrationError(
                f"MCP tool name {prefixed_name!r} exceeds "
                f"{_TOOL_NAME_MAX_LEN}-character limit; rename the source "
                "or contact the server author about the tool name"
            )
        # Set instance-level dynamic attrs BEFORE super().__init__.
        # Safe per the pattern note above — base.__init__ does NOT
        # touch these names.
        self.name = prefixed_name
        self.description = mcp_tool.description or ""
        self.parameters = mcp_tool.input_schema or {
            "type": "object",
            "properties": {},
        }
        self._mcp_tool = mcp_tool
        self._source_id = source_id
        self._source_name = source_name
        self._agent_name = agent_name
        self._original_tool_name = mcp_tool.name
        # Cache the override-applied source so `execute` can pass it
        # as `source_override` to `acquire` — survives post-OAuth
        # `_evict_all_for_source` re-acquires (cycle-1 low #5).
        self._effective_source = effective_source
        # Tool's standard __init__ takes (config, cross_configs, agent_name)
        # — call it with empty defaults; MCPClientTool doesn't participate
        # in the resolver dispatch (tool_overrides keys are built-in tools
        # only; mcp_overrides is its own surface).
        super().__init__(config=None, cross_configs={}, agent_name=agent_name)

    async def execute(self, **kwargs: Any) -> str:
        """Dispatch the tool call through the F4 pool to the MCP server.

        Returns the ``[error]`` string envelope on failure — matches
        builtin tools' ENVIRONMENTAL-failure pattern (NOT constraint;
        see ``the_one/tools/base.py:11-16`` for Flight 3 Decision 1.5
        — :class:`ConstraintError` uses ``[error] [constraint]``, env
        failures use bare ``[error]``). The agent loop's
        ``_execute_tool`` (``the_one/agent/core.py::Agent._execute_tool``)
        wraps the str return in ``ToolResult(is_error=False)``; the
        ``[error]`` prefix is the LLM's signal that the result represents
        a failure (per mission constraint #75 small-model-friendly
        invariant).

        Per F6 §8 failure class #3: source-fails-mid-session — if
        ``acquire`` raises :class:`SandboxError` /
        :class:`MCPConnectionError` / :class:`MCPVersionMismatch` during
        a session (e.g., the warm pool entry was reaped and respawn
        fails), return the env-failure envelope. The LLM sees the error
        and either retries or moves on.

        Passes ``source_override=self._effective_source`` to
        :func:`acquire` so post-OAuth re-acquires preserve the agent's
        override (cycle-1 low #5 fix).
        """
        try:
            client = await acquire(
                self._agent_name,
                self._source_id,
                source_override=self._effective_source,
            )
        except (SandboxError, MCPConnectionError, MCPVersionMismatch) as e:
            return f"[error] MCP source {self._source_name!r} unavailable: {type(e).__name__}: {e}"
        # call_tool propagates MCPAuthRequired (F5) — the agent loop's
        # _execute_tool catches that and translates to metadata. We
        # do NOT catch MCPAuthRequired here; let it propagate.
        result = await client.call_tool(self._original_tool_name, kwargs)
        return result.text

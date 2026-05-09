"""Per-agent MCP tool provider.

Reads :attr:`AgentConfig.mcp_source_ids` + :attr:`AgentConfig.mcp_overrides`
at agent build time; produces the list of :class:`MCPClientTool` instances
the agent's :class:`ToolRegistry` consumes. Sibling to
:class:`BuiltinToolProvider` — NOT a :class:`ToolProvider` Protocol
implementer (Protocol is sync; MCP is async; keying differs — F6 §3).

Failure modes (graceful-degrade per F6 §8):

#. **Source deleted** — :class:`MCPSourceRepository.get` raises
   ``KeyError`` → log + skip; agent build continues.
#. **Source fails to start** — :func:`acquire` or
   :meth:`MCPClient.list_tools` raises :class:`MCPSandboxError` /
   :class:`MCPConnectionError` / :class:`MCPVersionMismatch` /
   :class:`MCPAuthRequired` → log + skip the source, continue with
   others. The agent builds with whatever sources connected successfully
   and were authorized; auth-required sources are skipped with a
   discriminator log line so ops engineers can distinguish auth-pending
   from connect-failed. (F6.5 L2: :meth:`MCPClient.list_tools` now
   translates 401 to :class:`MCPAuthRequired` — same as
   :meth:`MCPClient.call_tool` post-F5-L4.)
#. **Source fails mid-session** — handled by
   :meth:`MCPClientTool.execute` returning the ``[error]`` envelope.
#. **Prefix collision** — two source names normalize to the same prefix
   (e.g. ``"github"`` and ``"GitHub"``) → log + drop ALL of the second
   source's tools (first source wins per F6 §8 #4).
#. *(class #1 sub-case)* **Tool name over 64 chars** —
   :class:`MCPClientTool.__init__` raises
   :class:`MCPRegistrationError` → log + drop the offending tool only;
   other tools from the same source survive (cycle-1 M2).

Empty :attr:`AgentConfig.mcp_source_ids` → returns ``[]`` immediately
without DB calls. Orphan-override warnings still fire on this path
(cycle-1 medium #4 fix).
"""

from __future__ import annotations

import logging
from typing import Any

from the_one.agent.config import AgentConfig
from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import get_encryptor
from the_one.mcp._overrides import StdioMCPOverride, StreamableHttpMCPOverride
from the_one.mcp._pool import acquire
from the_one.mcp._tool import MCPClientTool
from the_one.mcp.errors import (
    MCPAuthRequired,
    MCPConnectionError,
    MCPRegistrationError,
    MCPSandboxError,
    MCPVersionMismatch,
)
from the_one.tools.base import Tool
from the_one.tools.resolver import resolve

logger = logging.getLogger(__name__)


def _apply_override(
    source: MCPSource, override_payload: dict[str, Any] | None
) -> MCPSource:
    """Apply a per-agent override to a source.

    Returns a NEW :class:`MCPSource` with ``secrets`` updated — does
    NOT mutate the input. Both transports use **overlay-merge flat
    into source.secrets** to match the F2 transport contract:

    - ``stdio``: ``source.secrets`` IS the flat env kv table (read at
      :func:`build_stdio_environ`'s ``{**allowlist_env, **config_env,
      **source.secrets}`` merge in ``transports/stdio.py``). The
      agent's ``env`` dict overlays flat into ``source.secrets`` —
      agent wins on key collision; operator-only keys preserve. Per
      F6 §1: "operator-set env vars not overridden by the agent
      pass through unchanged."
    - ``streamable-http``: ``source.secrets`` IS the flat header kv
      table (read at :func:`build_request_headers`'s
      ``{**config_headers, **source.secrets}`` merge in
      ``transports/streamable_http.py``). The agent's ``headers``
      dict overlays flat; the agent's ``bearer_token`` translates
      to a flat ``Authorization: Bearer <token>`` entry in
      ``source.secrets``. The L2 cycle-1 medium #3 "REPLACE-headers"
      disposition was structurally unsafe against the F2 contract
      (would nuke every operator header including OAuth-managed
      keys); corrected to overlay-merge inline during the F6 HAT
      (see flight-log A4).

    NEVER nest the override under a ``secrets["env"]`` /
    ``secrets["headers"]`` key — the transport reads ``source.secrets``
    flat and would inject the dict as a header / env-var VALUE, which
    Pydantic rejects with a ``string_type`` validation error.

    When ``override_payload`` is ``None`` or empty, returns the source
    unchanged (cheap fast-path).

    Pydantic ``extra="ignore"`` (project default) silently drops
    unknown keys in the payload — typos like ``bear_token`` are NOT
    caught here. The L1 introspection regression test pins this.
    """
    if not override_payload:
        return source
    if source.type == "stdio":
        resolved = resolve(StdioMCPOverride, None, override_payload)
        env_value = getattr(resolved, "env", None)
        if env_value is None:
            return source
        # F2 contract: source.secrets IS the flat env kv table for
        # stdio. Flat-merge agent's env into source.secrets at top
        # level (NOT nested under "env"). Agent wins on key collision;
        # operator-only keys preserve.
        new_secrets = {**source.secrets, **env_value}
        return source.model_copy(update={"secrets": new_secrets})
    elif source.type == "streamable-http":
        resolved = resolve(StreamableHttpMCPOverride, None, override_payload)
        headers_value = getattr(resolved, "headers", None)
        bearer_value = getattr(resolved, "bearer_token", None)
        # F2 contract: source.secrets IS the flat header kv table for
        # streamable-http. Overlay-merge headers flat; bearer_token
        # translates to a flat Authorization header.
        new_secrets: dict[str, Any] = dict(source.secrets)
        if headers_value is not None:
            new_secrets.update(headers_value)
        if bearer_value is not None:
            new_secrets["Authorization"] = f"Bearer {bearer_value}"
        return source.model_copy(update={"secrets": new_secrets})
    else:
        # Unknown type — preserve source unchanged. The pool will
        # error on connect; that's the right surface for an
        # unsupported transport.
        return source


def _warn_orphan_overrides(
    agent_name: str,
    mcp_overrides: dict[str, dict[str, Any]] | None,
    resolved_source_names: set[str],
) -> None:
    """Log a WARNING for each ``mcp_overrides`` key that doesn't match
    any resolved source name. Non-fatal — orphans are dropped silently
    downstream.

    Logs once per unknown key (NOT once total), so an operator with
    multiple stale references gets a per-key diagnostic.
    """
    if not mcp_overrides:
        return
    for key in mcp_overrides:
        if key not in resolved_source_names:
            logger.warning(
                "agent %r's mcp_overrides references unknown source name "
                "%r; ignoring",
                agent_name,
                key,
            )


class MCPToolProvider:
    """Per-agent MCP tool builder.

    NOT a :class:`ToolProvider` Protocol implementer — see F6 §3 for
    the sibling-class rationale (Protocol is sync and per-tool-name
    keyed; MCP is async and per-source keyed).
    """

    async def get_tools_for_agent(
        self,
        config: AgentConfig,
        *,
        agent_name: str,
    ) -> list[Tool]:
        """Return the list of :class:`MCPClientTool` instances to
        register into ``agent_name``'s :class:`ToolRegistry`.

        Per F6 §8, five failure classes degrade gracefully (see module
        docstring for the full list). Empty
        :attr:`AgentConfig.mcp_source_ids` → return ``[]`` without DB
        calls (orphan-warn still fires per cycle-1 medium #4).
        """
        # Cycle-1 medium #4 fix: orphan-warn fires even when
        # mcp_source_ids is empty (otherwise an operator with
        # all-stale config-references would silently miss the
        # diagnostic).
        if not config.mcp_source_ids:
            _warn_orphan_overrides(agent_name, config.mcp_overrides, set())
            return []

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        repo = MCPSourceRepository(conn, encryptor)

        # Phase A: load all sources; collect names for orphan-warn.
        # Failure class #1 (deleted source) handled here.
        sources: list[MCPSource] = []
        for source_id in config.mcp_source_ids:
            try:
                sources.append(await repo.get(source_id))
            except KeyError:
                logger.warning(
                    "agent %r references deleted MCP source %r; skipping",
                    agent_name,
                    source_id,
                )
        resolved_names = {s.name for s in sources}
        _warn_orphan_overrides(agent_name, config.mcp_overrides, resolved_names)

        # Phase B: per source, apply override + acquire + list_tools + wrap.
        # Failure classes #2 and #4 + #1 sub-case handled here.
        tools: list[Tool] = []
        produced_names: dict[str, str] = {}  # prefixed_name → source_id
        for source in sources:
            # Override application (failure: Pydantic ValidationError;
            # we do NOT catch — operator schema mismatch is loud, not
            # graceful-degrade).
            override_payload = (config.mcp_overrides or {}).get(source.name)
            effective_source = _apply_override(source, override_payload)

            # Acquire (failure class #2 — covers connect AND list_tools).
            try:
                client = await acquire(
                    agent_name,
                    source.id,
                    source_override=effective_source,
                )
                mcp_tools = await client.list_tools()
            except MCPAuthRequired as e:
                logger.warning(
                    "MCP source %r requires authorization; skipping "
                    "(auth_required, source_id=%s)",
                    source.name,
                    e.source_id,
                )
                continue
            except (
                MCPSandboxError,
                MCPConnectionError,
                MCPVersionMismatch,
            ) as e:
                logger.warning(
                    "MCP source %r failed to connect: %s: %s; skipping",
                    source.name,
                    type(e).__name__,
                    e,
                )
                continue

            # Wrap each MCPTool. 64-char ceiling caught per-tool
            # (cycle-1 M2 — OTHER tools from the same source survive).
            # Prefix collision detected here; collision drops ALL
            # of THIS source's tools (failure class #4).
            source_tools: list[Tool] = []
            for mt in mcp_tools:
                try:
                    tool = MCPClientTool(
                        mt,
                        source_id=source.id,
                        source_name=source.name,
                        agent_name=agent_name,
                        effective_source=effective_source,
                    )
                except MCPRegistrationError as e:
                    logger.warning(
                        "MCP tool %s exceeds 64-char limit; dropping "
                        "(operator: rename source or contact server author)",
                        e,
                    )
                    continue
                # Prefix collision check. If a prior source already
                # registered this prefixed name, drop ALL of THIS
                # source's tools (per §8 #4 — first source wins).
                if tool.name in produced_names:
                    existing_source_id = produced_names[tool.name]
                    logger.warning(
                        "source-name collision %r between %r and %r; "
                        "first source wins, dropping %r",
                        tool.name,
                        existing_source_id,
                        source.id,
                        source.id,
                    )
                    source_tools.clear()  # discard accumulated tools from THIS source
                    break  # exit inner loop; don't process more of THIS source's tools
                source_tools.append(tool)

            # Commit this source's tools to the result. produced_names
            # populates AFTER the loop (so a same-source same-name
            # collision — the server returning duplicate tool names —
            # would be detected as a prefix collision against itself
            # at the second occurrence; same handling).
            for tool in source_tools:
                produced_names[tool.name] = source.id
                tools.append(tool)

        return tools

"""Sortie 09 (DD4/DD5): which tool list an agent reads for an MCP source.

An agent that uses its own credentials on a source (``has_credential_override``) and
is a stored agent reads the per-agent tool cache, never the shared ``_cache``.
Every other agent reads the shared ``_cache`` exactly as before; so does an agent
that is not in the store (an injected test config, the CLI).
"""

from __future__ import annotations

from typing import Any

import aiosqlite

from the_one.db.models import MCPSource
from the_one.db.repositories import AgentMcpToolCacheRepository
from the_one.mcp._overrides import has_credential_override
from the_one.self_configuration.constants import override_for


def to_cache_payload(mcp_tools: Any) -> list[dict[str, Any]]:
    """``MCPTool`` objects (or already-converted dicts) as the cached
    ``{name, description, input_schema}`` shape."""
    out: list[dict[str, Any]] = []
    for t in mcp_tools:
        if isinstance(t, dict):
            out.append(
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("input_schema", {"type": "object", "properties": {}}),
                }
            )
        else:
            out.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
            )
    return out


async def per_agent_tools(
    conn: aiosqlite.Connection,
    agent_name: str,
    mcp_overrides: dict[str, Any] | None,
    source: MCPSource,
) -> tuple[bool, list[dict[str, Any]] | None, str | None]:
    """``(per_agent, tools, updated_at)`` for ``agent_name`` on ``source``.

    ``per_agent`` is False when the shared ``_cache`` applies (no credential
    override, or the agent is not in the store). When True, ``tools`` is the
    per-agent row's list, or ``None`` on a cold cache, and ``updated_at`` is the
    agent's ``updated_at`` read now (the value ``put_if_unchanged`` needs).
    """
    if not has_credential_override(override_for(mcp_overrides, source), source):
        return False, None, None
    repo = AgentMcpToolCacheRepository(conn)
    updated_at = await repo.agent_updated_at(agent_name)
    if updated_at is None:
        return False, None, None
    row = await repo.get(agent_name, source.id)
    tools = row["tools"] if row is not None else None
    return True, (tools or None), updated_at

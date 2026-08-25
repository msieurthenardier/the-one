"""The self-configuration FastMCP server (LD4).

One stateless FastMCP instance, mounted on the existing app at
``constants.MOUNT_PATH``. Its ``session_manager.run()`` must be wrapped
around the app's lifespan body by the caller (``the_one/interfaces/web/
app.py``) — the SDK creates the session manager only once
``streamable_http_app()`` has been called, and `run()` is once-per-instance
(probe constraint 1).

The two read tools (DD6) resolve the calling agent from the ASGI scope the
credential gate stamped (``ctx.request_context.request.scope[CALLER_SCOPE_KEY]``
— the SDK sets ``RequestContext.request`` to the Starlette request for HTTP
transports). Any failure in that resolution — no caller stamped, credential
orphaned, surface disabled for the resolved agent (DD9) — raises a plain
exception with a one-line message; FastMCP's low-level server catches every
exception escaping a tool call and converts it to an ``isError`` result
(``mcp.server.lowlevel.server.Server.call_tool``'s ``except Exception as e:
return self._make_error_result(str(e))``), so this never raises a stack
into the transport.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.repositories import (
    ConnectorRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import get_encryptor
from the_one.interfaces.web.middleware import CALLER_SCOPE_KEY
from the_one.self_configuration import manage, pending
from the_one.self_configuration.constants import MOUNT_PATH
from the_one.self_configuration.credentials import source_id_for
from the_one.self_configuration.projection import (
    build_describe_my_capabilities,
    build_get_my_configuration,
)

mcp = FastMCP(
    "the-one self-configuration",
    stateless_http=True,
    streamable_http_path="/",
)

# LD5: input bounds, not content policy. 64 KiB, measured on the UTF-8
# encoded byte length (not `len(text)`, which counts code points) — no cap
# exists anywhere today (`AgentConfig`, the Studio textarea, the API), so
# this is the first bound, not a mirror of an existing one.
_MAX_TEXT_BYTES = 64 * 1024
_APPLY_VALUES = frozenset({"next_turn", "next_session"})


async def _calling_agent(ctx: Context) -> str:
    """Resolve the calling agent's name from the gate-stamped caller, and
    enforce DD9: refuse when the surface has since been disabled for the
    resolved agent.

    Raises a plain ``PermissionError`` with a one-line message on any
    failure — never a stack trace (see module docstring). This is the
    FIRST production reader of ``CALLER_SCOPE_KEY`` (the leg's Inputs note
    that no production code consulted it before this).
    """
    request = ctx.request_context.request
    if request is None:
        raise PermissionError("self-configuration: no request context (non-HTTP transport)")
    caller = request.scope.get(CALLER_SCOPE_KEY)
    if caller is None:
        raise PermissionError("self-configuration: no identified caller on this request")

    source_id = source_id_for(caller.identifier)
    if source_id is None:
        raise PermissionError("self-configuration: credential is not registered")

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    mcp_repo = MCPSourceRepository(conn, encryptor)
    try:
        row = await mcp_repo.get(source_id)
    except KeyError:
        raise PermissionError("self-configuration: surface is disabled for this caller") from None

    agent_name = manage.owner_of(row)
    if agent_name is None:
        raise PermissionError("self-configuration: surface is disabled for this caller")

    agent_store = SQLiteAgentStore(conn, encryptor)
    try:
        config = await agent_store.load(agent_name)
    except KeyError:
        raise PermissionError("self-configuration: surface is disabled for this caller") from None

    if row.id not in config.mcp_source_ids:
        raise PermissionError("self-configuration: surface is disabled for this caller")

    return agent_name


@mcp.tool()
async def get_my_configuration(ctx: Context) -> dict[str, Any]:
    """Return this agent's own configuration — a secret-free projection.

    Never includes a provider API key, MCP/connector secrets, or any
    credential-bearing override field. See LD5 for the exact field list.
    """
    agent_name = await _calling_agent(ctx)
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    agent_store = SQLiteAgentStore(conn, encryptor)
    config = await agent_store.load(agent_name)
    provider_repo = LLMProviderRepository(conn, encryptor)
    kb_repo = KnowledgeBaseRepository(conn)
    return await build_get_my_configuration(config, provider_repo=provider_repo, kb_repo=kb_repo)


@mcp.tool()
async def describe_my_capabilities(ctx: Context) -> dict[str, Any]:
    """Return the tools, sources, and connectors this agent holds — names
    and descriptions only, filtered through the operator's existing
    per-source and per-tool controls. Never a source config, URL, header,
    or secret.
    """
    agent_name = await _calling_agent(ctx)
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    agent_store = SQLiteAgentStore(conn, encryptor)
    config = await agent_store.load(agent_name)
    tool_config_repo = ToolConfigRepository(conn, encryptor)
    mcp_repo = MCPSourceRepository(conn, encryptor)
    connector_repo = ConnectorRepository(conn, encryptor)
    return await build_describe_my_capabilities(
        config,
        tool_config_repo=tool_config_repo,
        mcp_repo=mcp_repo,
        connector_repo=connector_repo,
    )


def _validate_write_input(text: Any, apply: Any) -> None:
    """LD5's input bounds. Raises a plain ``ValueError`` with a one-line
    message on any violation — the module's ONE error mechanism (see module
    docstring): FastMCP's low-level server converts any exception escaping
    a tool call to an ``isError`` result, exactly as ``_calling_agent``'s
    ``PermissionError`` already does. No second signalling path."""
    if not isinstance(text, str) or not text:
        raise ValueError("self-configuration: text must be a non-empty string")
    if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"self-configuration: text exceeds the {_MAX_TEXT_BYTES}-byte bound")
    if apply not in _APPLY_VALUES:
        raise ValueError(
            f"self-configuration: apply must be one of {sorted(_APPLY_VALUES)!r}, got {apply!r}"
        )


_EFFECTIVE_EXPLANATION = {
    "next_turn": (
        "This will take effect at the end of your current turn in this "
        "conversation — it will not change anything mid-turn."
    ),
    "next_session": (
        "This will take effect the next time this conversation is opened "
        "(a new session) — the currently open conversation is unaffected."
    ),
}


async def _apply_revision(agent_name: str, field: str, text: str, apply: str) -> dict[str, Any]:
    """LD2: persist first via ``store.load -> model_copy -> store.save``,
    then (only for ``next_turn``) record the in-memory deferral. Returns
    LD4's truthful, non-retry-inducing result shape — it never claims the
    running conversation has already changed."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    agent_store = SQLiteAgentStore(conn, encryptor)
    config = await agent_store.load(agent_name)
    updated = config.model_copy(update={field: text})
    await agent_store.save(updated)

    if apply == "next_turn":
        pending.record(agent_name, **{field: text})

    return {
        "applied_to_store": True,
        "effective": apply,
        "field": field,
        "length": len(text),
        "message": _EFFECTIVE_EXPLANATION[apply],
    }


@mcp.tool()
async def update_my_description(ctx: Context, text: str, apply: str) -> dict[str, Any]:
    """Revise this agent's own ``description``. Whole-value replacement —
    no append, no partial edit. ``apply`` is ``"next_turn"`` (applies when
    this turn ends) or ``"next_session"`` (applies the next time this
    conversation is opened); a description revision never touches the live
    conversation either way, so both modes are store-only in effect.
    """
    agent_name = await _calling_agent(ctx)
    _validate_write_input(text, apply)
    return await _apply_revision(agent_name, "description", text, apply)


@mcp.tool()
async def update_my_system_prompt(ctx: Context, text: str, apply: str) -> dict[str, Any]:
    """Revise this agent's own ``system_prompt``. Whole-value replacement —
    no append, no partial edit. ``apply="next_turn"`` defers the live
    change to the end of THIS turn (never mid-turn); ``apply="next_session"``
    leaves this open conversation untouched and applies only when the
    conversation is next opened.
    """
    agent_name = await _calling_agent(ctx)
    _validate_write_input(text, apply)
    return await _apply_revision(agent_name, "system_prompt", text, apply)


def list_surface_tools() -> list[dict[str, Any]]:
    """Return the surface's own tool catalog in the ``_cache.tools`` shape
    (``name``, ``description``, ``input_schema``) — the same shape
    ``/mcp-sources/{id}/test/connect`` persists. LD6: the enable path calls
    this directly (no loopback hop) to populate a fresh row's
    ``config._cache`` in-process, so agent builds take the cache-first path
    immediately (probe constraint 6) and the pool never attempts DCR on a
    401 for this source (constraint 3, via ``auth_posture: "no_auth"`` set
    alongside this by the caller).
    """
    out: list[dict[str, Any]] = []
    for tool in mcp._tool_manager.list_tools():
        out.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.parameters,
            }
        )
    return out


__all__ = ["mcp", "MOUNT_PATH", "list_surface_tools"]

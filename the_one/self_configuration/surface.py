"""The self-configuration MCPServer (LD4).

One stateless ``MCPServer`` instance (mcp 2.x; ``mcp.server.fastmcp`` is gone),
mounted on the existing app at ``constants.MOUNT_PATH``. Its
``session_manager.run()`` must be wrapped around the app's lifespan body by the
caller (``the_one/interfaces/web/app.py``) — the SDK creates the session
manager only once ``streamable_http_app()`` has been called, and `run()` is
once-per-instance (probe constraint 1). :func:`build_app` is the ONE place the
mounted app is built (``stateless_http=True, streamable_http_path="/"``): it
runs ``streamable_http_app()`` at most once per module instance, and
:func:`session_manager` reads the manager only after it has run.

The two read tools (DD6) resolve the calling agent from the ASGI scope the
credential gate stamped (``ctx.request_context.request.scope[CALLER_SCOPE_KEY]``
— the SDK sets ``RequestContext.request`` to the Starlette request for HTTP
transports). Any failure in that resolution — no caller stamped, credential
orphaned, surface disabled for the resolved agent (DD9) — raises one of the
two refusal classes below with a one-line message. Under 2.x only a
``ToolError`` keeps its text (``Error executing tool <name>: <msg>``); any
other exception is reduced to ``Error executing tool <name>`` with no text
(``mcp/server/mcpserver/tools/base.py``). The refusal classes therefore
subclass ``ToolError`` AND the builtin the 1.x code raised, so the client text
and in-process ``except PermissionError`` / ``except ValueError`` callers are
unchanged. Always raise them with ONE argument (two args format as
``[Errno ...]`` on the ``OSError`` base).

Refusal-parity audit (Mission 29 F1): the tool bodies, ``manage``, ``pending``,
``projection``, the revision repository and the agent store raise no other
exception that was meant to reach a client. The only others are internal
defences (``compare_and_set_field``'s ``illegal field`` ``ValueError``,
unreachable behind the tool boundary) and ``KeyError`` for an agent deleted
between the caller resolution and the tool's own reload (a race, text never
meant for the client). Those now read ``Error executing tool <name>``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.applications import Starlette

from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.models import now_iso
from the_one.db.repositories import (
    AgentRevisionRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import get_encryptor
from the_one.interfaces.web.middleware import CALLER_SCOPE_KEY
from the_one.self_configuration import external_credentials, manage, pending
from the_one.self_configuration.constants import EXTERNAL_SOURCE_NAME, MOUNT_PATH
from the_one.self_configuration.credentials import source_id_for
from the_one.self_configuration.projection import (
    build_describe_my_capabilities,
    build_get_my_configuration,
)

mcp = MCPServer("the-one self-configuration")


class SelfConfigPermissionError(ToolError, PermissionError):
    """A refusal of the caller itself (no/orphaned credential, surface
    disabled). Raise with ONE argument."""


class SelfConfigValueError(ToolError, ValueError):
    """A refusal of the caller's input (LD5 bounds). Raise with ONE argument."""


_app: Starlette | None = None


def build_app() -> Starlette:
    """Build (once per module instance) the Starlette app to mount at
    ``MOUNT_PATH``. Both ``the_one/interfaces/web/app.py`` and the surface
    test mount call this, so the transport options cannot drift."""
    global _app
    if _app is None:
        _app = mcp.streamable_http_app(stateless_http=True, streamable_http_path="/")
    return _app


def session_manager() -> Any:
    """The surface's session manager, read only after :func:`build_app` ran."""
    build_app()
    return mcp.session_manager


# LD5: input bounds, not content policy. 64 KiB, measured on the UTF-8
# encoded byte length (not `len(text)`, which counts code points) — no cap
# exists anywhere today (`AgentConfig`, the Studio textarea, the API), so
# this is the first bound, not a mirror of an existing one.
_MAX_TEXT_BYTES = 64 * 1024
_APPLY_VALUES = frozenset({"next_turn", "next_session"})


async def _resolve_caller_and_agent(ctx: Context) -> tuple[Any, str]:
    """Resolve the gate-stamped caller AND the agent it is scoped to,
    running the DD9 surface-enabled refusal tail EXACTLY ONCE.

    Returns ``(caller, agent_name)``. ``_calling_agent`` (the read tools)
    and ``_calling_principal`` (the write tools) both derive from this — the
    DD9 tail lives here and is not duplicated. This is the FIRST production
    reader of ``CALLER_SCOPE_KEY`` (the leg's Inputs note that no production
    code consulted it before this).

    Raises ``SelfConfigPermissionError`` with a one-line message on any
    failure — never a stack trace (see module docstring).
    """
    request = ctx.request_context.request
    if request is None:
        raise SelfConfigPermissionError(
            "self-configuration: no request context (non-HTTP transport)"
        )
    caller = request.scope.get(CALLER_SCOPE_KEY)
    if caller is None:
        raise SelfConfigPermissionError("self-configuration: no identified caller on this request")

    # M21 F03 L01 (DD1/DD9): route an EXTERNAL caller through the external
    # registry; every other caller (the agent's own `agt` credential) through
    # the per-agent registry. Both resolve identifier -> surface `source_id`;
    # the shared owner-resolution + surface-enabled refusal tail below is what
    # gives the external principal the DD9 gate for free — an `ext_`
    # credential is refused the moment its surface is disabled/detached,
    # exactly as the agent's own path is, and never more privileged.
    if caller.source == EXTERNAL_SOURCE_NAME:
        source_id = external_credentials.source_id_for(caller.identifier)
    else:
        source_id = source_id_for(caller.identifier)
    if source_id is None:
        raise SelfConfigPermissionError("self-configuration: credential is not registered")

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    mcp_repo = MCPSourceRepository(conn, encryptor)
    try:
        row = await mcp_repo.get(source_id)
    except KeyError:
        raise SelfConfigPermissionError(
            "self-configuration: surface is disabled for this caller"
        ) from None

    agent_name = manage.owner_of(row)
    if agent_name is None:
        raise SelfConfigPermissionError("self-configuration: surface is disabled for this caller")

    agent_store = SQLiteAgentStore(conn, encryptor)
    try:
        config = await agent_store.load(agent_name)
    except KeyError:
        raise SelfConfigPermissionError(
            "self-configuration: surface is disabled for this caller"
        ) from None

    if row.id not in config.mcp_source_ids:
        raise SelfConfigPermissionError("self-configuration: surface is disabled for this caller")

    return caller, agent_name


async def _calling_agent(ctx: Context) -> str:
    """Resolve the calling agent's name (the two READ tools).

    Thin wrapper over :func:`_resolve_caller_and_agent` — the reads need
    only the agent name, not the caller's provenance.
    """
    _caller, agent_name = await _resolve_caller_and_agent(ctx)
    return agent_name


async def _calling_principal(ctx: Context) -> tuple[str, str, str | None]:
    """Resolve ``(agent_name, source, source_principal)`` for the two WRITE
    tools (M21 F03 L02, DD3).

    ``source`` is ``"external"`` iff the gate stamped an EXTERNAL caller,
    else ``"self"``; ``source_principal`` is the external credential's
    identifier for an external write, else ``None`` (safe to log by Mission
    20's id/secret split — the identifier, never the secret). Derives from
    the same :func:`_resolve_caller_and_agent` as the reads, so the DD9 tail
    runs once.
    """
    caller, agent_name = await _resolve_caller_and_agent(ctx)
    if caller.source == EXTERNAL_SOURCE_NAME:
        return agent_name, "external", caller.identifier
    return agent_name, "self", None


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
    """Return the tools and sources this agent holds — names and
    descriptions only, filtered through the operator's existing
    per-source and per-tool controls. Never a source config, URL, header,
    or secret.

    Mission 23 Flight 1 (backend-removal leg, DD-5): no longer surfaces
    connectors — the connector subsystem is gone; the payload's
    ``connectors`` key was dropped by :func:`build_describe_my_capabilities`.
    """
    agent_name = await _calling_agent(ctx)
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    agent_store = SQLiteAgentStore(conn, encryptor)
    config = await agent_store.load(agent_name)
    tool_config_repo = ToolConfigRepository(conn, encryptor)
    mcp_repo = MCPSourceRepository(conn, encryptor)
    return await build_describe_my_capabilities(
        config,
        tool_config_repo=tool_config_repo,
        mcp_repo=mcp_repo,
    )


def _validate_write_input(text: Any, apply: Any) -> None:
    """LD5's input bounds. Raises ``SelfConfigValueError`` (a ``ToolError``
    and a ``ValueError``) with a one-line message on any violation — the
    module's ONE error mechanism (see module docstring): the SDK turns a
    ``ToolError`` into an ``isError`` result carrying its text. No second
    signalling path."""
    if not isinstance(text, str) or not text:
        raise SelfConfigValueError("self-configuration: text must be a non-empty string")
    if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise SelfConfigValueError(
            f"self-configuration: text exceeds the {_MAX_TEXT_BYTES}-byte bound"
        )
    if apply not in _APPLY_VALUES:
        raise SelfConfigValueError(
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


async def _apply_revision(
    agent_name: str,
    field: str,
    text: str,
    apply: str,
    source: str = "self",
    source_principal: str | None = None,
) -> dict[str, Any]:
    """LD2: persist first (via the field-scoped CAS), then (only for
    ``next_turn``) record the in-memory deferral. Returns LD4's truthful,
    non-retry-inducing result shape — it never claims the running
    conversation has already changed.

    M21 F03 L02: ``source`` / ``source_principal`` tag the revision with who
    wrote it (``self`` for the agent's own write, ``external`` +
    the credential identifier for an external client's write). The persist
    branch uses ``compare_and_set_field`` (DD5): a field-scoped
    compare-and-swap that closes the whole-row last-writer-wins clobber and
    fails closed with a ``stale`` tool result when the field drifted under
    the writer."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    agent_store = SQLiteAgentStore(conn, encryptor)
    config = await agent_store.load(agent_name)
    base_value = getattr(config, field)

    # M21 F02 L02 DD3: approval mode. When the operator has set approval
    # mode ON for this agent, the proposed revision is NOT applied — it is
    # enqueued as a ``pending`` row (dedup one per agent+field) for the
    # operator to approve or dismiss. We deliberately do NOT ``save`` and do
    # NOT ``pending.record``: the store and the live conversation are left
    # untouched, and an approved revision propagates next-session only (the
    # proposing turn's ``apply`` is moot and not replayed). The result is
    # truthful and non-retry-inducing — it does not claim the change took
    # effect, so the agent does not loop trying to re-apply it.
    if config.self_revision_requires_approval:
        revisions = AgentRevisionRepository(conn)
        await revisions.upsert_pending_revision(
            agent_name=agent_name,
            field=field,
            proposed_value=text,
            base_value=base_value,
            source=source,
            source_principal=source_principal,
        )
        return {
            "applied_to_store": False,
            "effective": "pending_operator_approval",
            "field": field,
            "length": len(text),
            "message": (
                "This change has been submitted to the operator for approval "
                "and is not yet in effect. If approved, it will take effect the "
                "next time this conversation is opened. No further action is "
                "needed from you."
            ),
        }

    # M21 F03 L02 DD5: field-scoped compare-and-swap in place of the
    # whole-row ``model_copy`` + ``save``. Only the one revised column is
    # written, guarded on the field still holding ``base_value`` — so a
    # concurrent write to the OTHER field is never clobbered, and a drift on
    # THIS field between the ``load`` above and the write is caught. On a
    # miss the write applies nothing and returns a truthful, non-retry-
    # inducing ``stale`` result mirroring the pending branch's shape (before
    # any ``pending.record``, so a stale write leaves no in-memory deferral
    # either — leg Edge Cases). HTTP 409 stays exclusive to the operator
    # approve endpoint (an HTTP request); this is an MCP tool result.
    applied = await agent_store.compare_and_set_field(agent_name, field, base_value, text)
    if not applied:
        current_value = getattr(await agent_store.load(agent_name), field)
        return {
            "applied_to_store": False,
            "effective": "stale",
            "field": field,
            "current_value": current_value,
            "proposed_value": text,
            "message": (
                "This change was NOT applied: the field changed since you read "
                "it, so writing now would overwrite that newer value. Nothing was "
                "written. No further action is needed from you — re-read the "
                "current value before proposing again if you still intend to."
            ),
        }

    # Revision log (M21 F02 L01): record this direct revision as one
    # ``applied`` row with its before-image (``base_value``) and after-image
    # (``proposed_value``), tagged with its provenance (``source`` /
    # ``source_principal``). Ordered strictly AFTER the CAS confirms one row
    # changed, so a revision is never logged unless it persisted (a
    # logged-but-unpersisted change is the worse failure — it would claim a
    # change that never took effect). The CAS self-commits, so the write and
    # append are not one transaction; the residual crash-window between them
    # (revision persisted to ``agents`` without a log row) is accepted at
    # operator-scale / single-writer, per the leg's Edge Cases. One
    # ``now_iso()`` value fills both ``created_at`` and ``resolved_at`` — an
    # applied row is resolved at creation, so the two timestamps are
    # byte-identical.
    ts = now_iso()
    revisions = AgentRevisionRepository(conn)
    await revisions.append(
        agent_name=agent_name,
        field=field,
        proposed_value=text,
        base_value=base_value,
        source=source,
        source_principal=source_principal,
        status="applied",
        restored_from=None,
        created_at=ts,
        resolved_at=ts,
    )

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
    agent_name, source, source_principal = await _calling_principal(ctx)
    _validate_write_input(text, apply)
    return await _apply_revision(
        agent_name, "description", text, apply, source=source, source_principal=source_principal
    )


@mcp.tool()
async def update_my_system_prompt(ctx: Context, text: str, apply: str) -> dict[str, Any]:
    """Revise this agent's own ``system_prompt``. Whole-value replacement —
    no append, no partial edit. ``apply="next_turn"`` defers the live
    change to the end of THIS turn (never mid-turn); ``apply="next_session"``
    leaves this open conversation untouched and applies only when the
    conversation is next opened.
    """
    agent_name, source, source_principal = await _calling_principal(ctx)
    _validate_write_input(text, apply)
    return await _apply_revision(
        agent_name, "system_prompt", text, apply, source=source, source_principal=source_principal
    )


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


__all__ = ["mcp", "MOUNT_PATH", "build_app", "session_manager", "list_surface_tools"]

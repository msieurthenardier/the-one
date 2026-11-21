"""The ``agent`` kind: create an agent or change one of its settings (M36 F4 L1a, DD2).

The field table, the normalizer, the stored-value reader (``agent_base``), the target check
and the apply. The apply calls the agent write services through the module attribute
(``agent_service.change_agent``), so a test may patch the service in one place.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any, cast

import aiosqlite

from the_one.agent import service as agent_service
from the_one.agent.service import comparable_value
from the_one.gleepglorp.kinds.base import Kind, changed_labels
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import (
    RESERVED_AGENTS,
    FieldSpec,
    Normalized,
    ShapeError,
    _bad,
    _check_int,
    _check_names,
    _check_text,
    _q,
    _ref_entries,
    _resolve_one,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.gleepglorp.view_core import _agent_names
from the_one.naming import NameRuleError, check_agent_name

_DESCRIPTION_MAX = 1000
_PROMPT_MAX = 20000
_MODEL_MAX = 200

AGENT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "name",
        "text",
        "Name",
        "name",
        hint="the new agent's name",
        create_required=True,
        create_only=True,
    ),
    FieldSpec("description", "text", "Description", "description", max=_DESCRIPTION_MAX),
    FieldSpec("system_prompt", "text", "System prompt", "system_prompt", max=_PROMPT_MAX),
    FieldSpec(
        "provider",
        "text",
        "Model provider",
        "provider_config_id",
        hint="a model provider's name; give model too",
        ref="provider",
    ),
    FieldSpec("model", "text", "Model", "llm_model", hint="a model id", max=_MODEL_MAX),
    FieldSpec(
        "enabled_tools",
        "names",
        "Enabled built-in tools",
        "enabled_tools",
        hint="built-in tool names; an empty list is none (null, meaning all, is not available)",
        ref="tool",
    ),
    FieldSpec(
        "disabled_tools",
        "names",
        "Disabled built-in tools",
        "disabled_tools",
        hint="built-in tool names",
        ref="tool",
    ),
    FieldSpec(
        "mcp_servers",
        "names",
        "MCP servers",
        "mcp_source_ids",
        hint="MCP server names",
        ref="mcp",
    ),
    FieldSpec(
        "knowledge_bases",
        "names",
        "Knowledge bases",
        "kb_ids",
        hint="knowledge base names",
        ref="kb",
    ),
    FieldSpec("rich_visuals", "boolean", "Rich visuals", "rich_visuals"),
    FieldSpec("notes_enabled", "boolean", "Notes", "notes_enabled"),
    FieldSpec("max_iterations", "integer", "Step limit", "max_iterations", min=1, max=200),
    FieldSpec(
        "chat_history_retention_days",
        "integer",
        "Chat history kept (days)",
        "chat_history_retention_days",
        min=1,
        max=365,
    ),
)

# Fields the operator alone controls; never in any kind's spec (a test asserts it).
OPERATOR_ONLY = (
    "secret_ids",
    "tool_overrides",
    "mcp_overrides",
    "self_revision_requires_approval",
    "routines_self_config_enabled",
    "routines_require_approval",
)


def not_reserved(agent: str) -> None:
    if agent.casefold() in RESERVED_AGENTS:
        raise ShapeError(f"{_q(agent)} can't be changed here.")


async def existing_agent(conn: Any, agent: Any) -> str:
    """The name of an existing, changeable agent, else a :class:`ShapeError` sentence."""
    if not isinstance(agent, str) or not agent.strip():
        raise ShapeError("Say which agent: give agent.")
    agent = agent.strip()
    not_reserved(agent)
    names = await _agent_names(conn)
    if agent not in names:
        raise ShapeError(f"No agent named {_q(agent)}.")
    return agent


async def resolve_target(conn: Any, ref: Any) -> tuple[str, str]:
    """``(name, name)`` of an existing agent: an agent's id is its name."""
    name = await existing_agent(conn, ref)
    return name, name


async def normalize(
    action: str,
    target: dict[str, Any],
    changes: dict[str, Any],
    *,
    conn: Any,
    now: datetime,
    zone: tzinfo,
    enc: Any = None,
) -> Normalized:
    from the_one.tools.builtins import builtin_tool_names

    stored: dict[str, Any] = {}
    names: dict[str, Any] = {}
    tools = set(builtin_tool_names())
    has_provider, has_model = "provider" in changes, "model" in changes
    if action == "create" and has_provider != has_model:
        raise ShapeError("Give both provider and model, or neither.")
    if action == "change" and has_provider and not has_model:
        raise ShapeError("Give the model too.")
    for f in AGENT_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.type == "text":
            stored[f.stored] = _check_text(f, value)
        elif f.type == "boolean":
            if not isinstance(value, bool):
                raise _bad(f, "true or false")
            stored[f.stored] = value
        elif f.type == "integer":
            stored[f.stored] = _check_int(f, value)
        elif f.type == "names":
            listed = _check_names(f, value)
            if f.ref == "tool":
                unknown = [n for n in listed if n not in tools]
                if unknown:
                    raise ShapeError(
                        f"No built-in tool named {_q(unknown[0])}. "
                        "See read_app_config built_in_tools."
                    )
                stored[f.stored] = listed
            else:
                entries = await _ref_entries(conn, f.ref or "")
                stored[f.stored] = [_resolve_one(entries, f.ref or "", n) for n in listed]
                names[f.stored] = listed
    if "provider_config_id" in stored:
        pname = changes["provider"]
        if not isinstance(pname, str) or not pname.strip():
            provider_spec = next(f for f in AGENT_FIELDS if f.name == "provider")
            raise _bad(provider_spec, "a model provider's name")
        entries = await _ref_entries(conn, "provider")
        stored["provider_config_id"] = _resolve_one(entries, "provider", pname.strip())
        names["provider_config_id"] = pname.strip()
    if "llm_model" in stored and not stored["llm_model"].strip():
        raise ShapeError("model must be a model id.")
    if "llm_model" in stored:
        stored["llm_model"] = stored["llm_model"].strip()
    if action == "create":
        try:
            name = check_agent_name(changes["name"])
        except NameRuleError as e:
            raise ShapeError(e.message) from None
        if name.casefold() in {n.casefold() for n in await _agent_names(conn)}:
            raise ShapeError(f"An agent named {_q(name)} already exists.")
        stored["name"] = name
        return Normalized("agent", "create", name, None, f"agent:{name}", stored, None, names)
    agent = await existing_agent(conn, target.get("agent"))
    base = await agent_base(conn, enc, agent, list(stored))
    return Normalized("agent", "change", agent, None, f"agent:{agent}", stored, base, names)


async def agent_base(conn: Any, enc: Any, agent: str, fields: list[str]) -> dict[str, Any]:
    """The stored value of each of ``fields`` for ``agent``, normalised as the stale check
    normalises it (the agent's own self-configuration surface id is left out)."""
    from the_one.config import settings
    from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
    from the_one.encryption import get_encryptor
    from the_one.self_configuration import manage
    from the_one.self_configuration.constants import is_surface_row

    enc = enc if enc is not None else get_encryptor(settings.data_dir)
    cfg = await SQLiteAgentStore(conn, enc).load(agent)
    surface_ids = {
        s.id
        for s in await MCPSourceRepository(conn, enc).list()
        if is_surface_row(s) and manage.owner_of(s) == agent
    }
    return {f: comparable_value(f, getattr(cfg, f), surface_ids) for f in fields}


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    if p.action == "create":
        return True
    return bool(p.agent_name) and await deps.agent.store.exists(cast(str, p.agent_name))


async def apply(
    conn: aiosqlite.Connection,
    deps: KindDeps,
    p: Proposal,
    *,
    changes: dict[str, Any],
    base: dict[str, Any],
    override: bool,
    now: datetime,
    zone: Any,
    mark: Any,
    runner: Any,
    result: dict[str, Any],
) -> str | None:
    try:
        if p.action == "create":
            await agent_service.create_agent(deps.agent, changes, on_commit=mark)
        else:
            assert p.agent_name is not None
            await agent_service.change_agent(
                deps.agent, p.agent_name, changes, base=base, override=override, on_commit=mark
            )
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(AGENT_FIELDS, p)
    agent = p.agent_name or ""
    text = (
        f"Created agent {agent}"
        if p.action == "create"
        else f"Changed {', '.join(labels)} on {agent}"
    )
    return {"summary": text, "agent": agent, "fields": labels}


KIND = Kind(
    name="agent",
    label="agent",
    summary="Create an agent or change one of its settings",
    fields=AGENT_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    operator_only=OPERATOR_ONLY,
    fillable=("create", "change"),
    resolve_target=resolve_target,
)

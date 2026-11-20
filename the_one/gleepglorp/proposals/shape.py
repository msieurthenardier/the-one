"""The change shape GleepGlorp may propose (Mission 36 F2 L2, DD1 and DD2).

One declared table of fields per kind (``agent``, ``rule``, ``routine``). :func:`normalize`
checks a model's proposed change against it, resolves every name to an id against the live
tables, reads the ``base`` (the stored value of each touched field) and returns what the
store records. :func:`describe` generates the field list the ``fields`` kind of
``read_app_config`` shows, so the shape is never written twice.

Nothing else is accepted: any other key is refused with a sentence naming the allowed fields.
The fields the operator alone controls (``secret_ids``, ``tool_overrides``, ``mcp_overrides``,
``self_revision_requires_approval``, ``routines_self_config_enabled``,
``routines_require_approval``) appear in no spec; a test pins that.

The stored ``changes`` use the stored model's own field names and hold ids (an agent's
``provider_config_id``, ``mcp_source_ids``, ``kb_ids``), so the approval path passes them to
the write services unchanged. A rule's ``position`` is the 1-based position the model gave
(the rule services take a 0-based index: the approval path subtracts one).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from typing import Any

from the_one.agent.service import comparable_value
from the_one.db._rules import RuleLimitError, validate_rule_text
from the_one.gleepglorp.view_core import _agent_names, _names, _surface_owners
from the_one.naming import NameRuleError, check_agent_name, check_name
from the_one.routines import recurrence
from the_one.routines import service as routine_service
from the_one.routines.limits import RoutineFieldError

KINDS = ("agent", "rule", "routine")
ACTIONS = ("create", "change")
RESERVED_AGENTS = ("gleepglorp", "default")

_LIST_MAX = 100
_DESCRIPTION_MAX = 1000
_PROMPT_MAX = 20000
_MODEL_MAX = 200


class ShapeError(ValueError):
    """A proposal the shape refuses; ``str(e)`` is the plain sentence the tool returns."""


@dataclass(frozen=True)
class FieldSpec:
    """One proposable field. ``name`` is the model-facing key, ``stored`` the stored field.

    ``type``: ``text``, ``boolean``, ``integer``, ``names`` (a list of strings) or
    ``schedule`` (the canonical ``{start, repeat, ends}`` object). ``ref`` names what a
    ``names`` / ``text`` value refers to, resolved to ids: ``provider``, ``mcp``, ``kb`` or
    ``tool`` (a built-in tool name, kept as a name).
    """

    name: str
    type: str
    label: str
    stored: str
    hint: str = ""
    min: int | None = None
    max: int | None = None
    create_required: bool = False
    create_only: bool = False
    ref: str | None = None


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

RULE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("text", "text", "Rule", "text", create_required=True),
    FieldSpec("enabled", "boolean", "On", "enabled"),
    FieldSpec(
        "position",
        "integer",
        "Position",
        "position",
        hint="1-based; omit for last",
        min=1,
        create_only=True,
    ),
)

#: One weekday schedule (Monday to Friday at 08:00); the date is a placeholder the model replaces.
#: A test round-trips it (with a real date) through the routine service's schedule validation.
SCHEDULE_EXAMPLE: dict[str, Any] = {
    "start": {"date": "YYYY-MM-DD", "time": "08:00"},
    "repeat": {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]},
}


def _schedule_hint() -> str:
    """The full canonical schedule shape, built from the recurrence module's own constants."""
    units = "|".join(recurrence.UNITS)
    nth = ", ".join(str(n) for n in recurrence.NTH_VALUES)
    rel = "|".join(recurrence._REL_UNITS)
    return (
        'start: {date: "YYYY-MM-DD", time: "HH:MM"} or {in: {amount, unit: '
        f"{rel}}}}}; repeat (omit for once): {{every: N, unit: {units}, "
        "days: [0-6, 0 = Monday] (required for week only), "
        f"month_by: {{by: day}} or {{by: weekday, nth: {nth}}} (month only)}}; "
        "ends (default never): {kind: never} or {kind: on, date} or {kind: after, count}. "
        f"Weekdays at 8: {json.dumps(SCHEDULE_EXAMPLE)}"
    )


ROUTINE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "text", "Name", "name", create_required=True),
    FieldSpec("prompt", "text", "Prompt", "prompt", create_required=True),
    FieldSpec(
        "schedule",
        "schedule",
        "Schedule",
        "schedule",
        hint=_schedule_hint(),
        create_required=True,
    ),
    FieldSpec("enabled", "boolean", "On", "enabled"),
)

SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "agent": AGENT_FIELDS,
    "rule": RULE_FIELDS,
    "routine": ROUTINE_FIELDS,
}

KIND_SUMMARIES = {
    "agent": "Create an agent or change one of its settings",
    "rule": "Add or change one of an agent's rules",
    "routine": "Add or change one of an agent's routines",
}

# Fields the operator alone controls; never in a spec (a test asserts it).
OPERATOR_ONLY_FIELDS = (
    "secret_ids",
    "tool_overrides",
    "mcp_overrides",
    "self_revision_requires_approval",
    "routines_self_config_enabled",
    "routines_require_approval",
)


@dataclass
class Normalized:
    """What the store records for one proposal."""

    kind: str
    action: str
    agent_name: str
    target_id: str | None
    target_key: str
    changes: dict[str, Any]
    base: dict[str, Any] | None = None
    # Display names for the ids in ``changes``, kept out of the stored row.
    names: dict[str, Any] = field(default_factory=dict)


def spec_for(kind: str, name: str) -> FieldSpec | None:
    return next((f for f in SPECS.get(kind, ()) if f.name == name), None)


def describe(kind: str | None = None) -> Any:
    """The ``fields`` kind's content, generated from the specs.

    No ``kind``: ``[{name, summary}]`` for the three kinds. With a kind: ``{name, fields}``
    where each field is ``{name, label, type, required_on_create?, create_only?, min?, max?,
    hint?, reference?}``.
    """
    if kind is None:
        return [
            {
                "name": k,
                "summary": f"{KIND_SUMMARIES[k]} ({len(SPECS[k])} fields)",
            }
            for k in KINDS
        ]
    out = []
    for f in SPECS[kind]:
        d: dict[str, Any] = {"name": f.name, "label": f.label, "type": f.type}
        if f.create_required:
            d["required_on_create"] = True
        if f.create_only:
            d["create_only"] = True
        if f.min is not None:
            d["min"] = f.min
        if f.max is not None:
            d["max"] = f.max
        if f.hint:
            d["hint"] = f.hint
        if f.ref in ("provider", "mcp", "kb"):
            d["reference"] = {
                "provider": "a model provider's name",
                "mcp": "MCP server names",
                "kb": "knowledge base names",
            }[f.ref]
        out.append(d)
    return {"name": kind, "fields": out}


# --- value checks ---------------------------------------------------------------------


_ECHO_MAX = 40


def _q(value: Any) -> str:
    """A model-supplied value as it may appear in a refusal: the model's own text, cut short.

    ``propose_change``'s output is trusted, so a refusal never carries more of a model-chosen
    string than a short quote (the model wrote it in its own call; nothing outside is added).
    """
    text = str(value)
    return text if len(text) <= _ECHO_MAX else text[:_ECHO_MAX] + "…"


def _bad(spec: FieldSpec, what: str) -> ShapeError:
    return ShapeError(f"{spec.name} must be {what}.")


def _check_text(spec: FieldSpec, value: Any) -> str:
    if not isinstance(value, str):
        raise _bad(spec, "text")
    if spec.max is not None and len(value) > spec.max:
        raise ShapeError(f"{spec.name} is limited to {spec.max:,} characters.")
    return value


def _check_int(spec: FieldSpec, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad(spec, "a whole number")
    if (spec.min is not None and value < spec.min) or (spec.max is not None and value > spec.max):
        lo = spec.min if spec.min is not None else "any"
        hi = spec.max if spec.max is not None else "any"
        raise ShapeError(f"{spec.name} must be a whole number from {lo} to {hi}.")
    return value


def _check_names(spec: FieldSpec, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise _bad(spec, "a list of names")
    if len(value) > _LIST_MAX:
        raise ShapeError(f"{spec.name} is limited to {_LIST_MAX} names.")
    seen: list[str] = []
    for v in value:
        v = v.strip()
        if v not in seen:
            seen.append(v)
    return seen


def _kind_label(ref: str) -> str:
    return {"provider": "model provider", "mcp": "MCP server", "kb": "knowledge base"}[ref]


def _resolve_one(entries: list[tuple[str, str]], ref: str, name: str) -> str:
    """The id of the one entry named ``name`` (exact), else a plain sentence."""
    hits = [i for i, n in entries if n == name]
    if not hits:
        raise ShapeError(f"No {_kind_label(ref)} named {_q(name)}.")
    if len(hits) > 1:
        raise ShapeError(f"More than one {_kind_label(ref)} is named {_q(name)}; rename one first.")
    return hits[0]


async def _ref_entries(conn: Any, ref: str) -> list[tuple[str, str]]:
    from the_one.self_configuration.constants import SURFACE_ROW_NAME

    if ref == "provider":
        return await _names(conn, "llm_providers")
    if ref == "kb":
        return await _names(conn, "knowledge_bases")
    surface_ids = set(await _surface_owners(conn))
    # The self-configuration surface row is never resolvable, by marker or by name.
    return [
        (i, n)
        for i, n in await _names(conn, "mcp_sources")
        if i not in surface_ids and n != SURFACE_ROW_NAME
    ]


def _check_schedule(spec: FieldSpec, value: Any, now: datetime, zone: tzinfo) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShapeError("schedule must be an object like {start, repeat, ends}.")
    try:
        # The operator's now-start is never resolved here, so {"start": {"now": true}} is refused.
        sched, anchor = routine_service.validate_schedule(
            value, now, zone, min_ahead=routine_service._min_ahead(False)
        )
        routine_service._require_future(sched, anchor, now, zone, "schedule")
    except RoutineFieldError as e:
        raise ShapeError(e.message) from None
    return {"schedule": sched, "anchor_at": anchor.isoformat() if anchor is not None else None}


# --- normalize ------------------------------------------------------------------------


def _check_keys(kind: str, changes: Any) -> dict[str, Any]:
    if not isinstance(changes, dict):
        raise ShapeError("changes must be an object of field names and values.")
    allowed = [f.name for f in SPECS[kind]]
    unknown = [k for k in changes if k not in allowed]
    if unknown:
        raise ShapeError(
            f"{kind} changes can't include {', '.join(repr(_q(k)) for k in unknown)}. "
            f"Allowed fields: {', '.join(allowed)}."
        )
    return changes


def _not_reserved(agent: str) -> None:
    if agent.casefold() in RESERVED_AGENTS:
        raise ShapeError(f"{_q(agent)} can't be changed here.")


async def _existing_agent(conn: Any, agent: Any) -> str:
    if not isinstance(agent, str) or not agent.strip():
        raise ShapeError("Say which agent: give agent.")
    agent = agent.strip()
    _not_reserved(agent)
    names = await _agent_names(conn)
    if agent not in names:
        raise ShapeError(f"No agent named {_q(agent)}.")
    return agent


async def normalize(
    kind: Any,
    action: Any,
    target: dict[str, Any],
    changes: Any,
    *,
    conn: Any,
    now: datetime,
    zone: tzinfo,
    enc: Any = None,
) -> Normalized:
    """Check one proposal and return what the store records; raises :class:`ShapeError`.

    ``target`` carries ``agent`` and, for a change, ``rule`` (a 1-based position) or
    ``routine`` (a name). The target must exist now. ``base`` is read for a change.
    """
    if kind not in KINDS:
        raise ShapeError(f"Unknown kind {str(kind)[:40]!r}. Kinds: {', '.join(KINDS)}.")
    if action not in ACTIONS:
        raise ShapeError(f"Unknown action {str(action)[:40]!r}. Actions: {', '.join(ACTIONS)}.")
    changes = _check_keys(kind, changes)
    specs = SPECS[kind]
    if action == "create":
        missing = [f.name for f in specs if f.create_required and f.name not in changes]
        if missing:
            raise ShapeError(f"A new {kind} needs {', '.join(missing)}.")
    else:
        only = [f.name for f in specs if f.create_only and f.name in changes]
        if only:
            raise ShapeError(f"{', '.join(only)} can only be set when creating a {kind}.")
        if not changes:
            raise ShapeError("Nothing to change. Give at least one field in changes.")

    if kind == "agent":
        return await _agent(action, target, changes, conn=conn, enc=enc)
    if kind == "rule":
        return await _rule(action, target, changes, conn=conn)
    return await _routine(action, target, changes, conn=conn, now=now, zone=zone)


async def _agent(
    action: str, target: dict[str, Any], changes: dict[str, Any], *, conn: Any, enc: Any
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
            raise _bad(spec_for("agent", "provider"), "a model provider's name")  # type: ignore[arg-type]
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
    agent = await _existing_agent(conn, target.get("agent"))
    base = await _agent_base(conn, enc, agent, list(stored))
    return Normalized("agent", "change", agent, None, f"agent:{agent}", stored, base, names)


async def _agent_base(conn: Any, enc: Any, agent: str, fields: list[str]) -> dict[str, Any]:
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


async def _rule(
    action: str, target: dict[str, Any], changes: dict[str, Any], *, conn: Any
) -> Normalized:
    from the_one.db.repositories import AgentRuleRepository

    agent = await _existing_agent(conn, target.get("agent"))
    stored: dict[str, Any] = {}
    for f in RULE_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.type == "text":
            if not isinstance(value, str):
                raise _bad(f, "text")
            try:
                stored["text"] = validate_rule_text(value)
            except RuleLimitError as e:
                raise ShapeError(e.detail) from None
        elif f.type == "boolean":
            if not isinstance(value, bool):
                raise _bad(f, "true or false")
            stored[f.stored] = value
        else:
            stored[f.stored] = _check_int(f, value)
    repo = AgentRuleRepository(conn)
    rules = await repo.list_for_agent(agent)
    if action == "create":
        return Normalized("rule", "create", agent, None, f"rule:{agent}:new", stored, None)
    pos = target.get("rule")
    if isinstance(pos, bool) or not isinstance(pos, int):
        raise ShapeError("Say which rule: give rule, its number in the agent's list (from 1).")
    if not 1 <= pos <= len(rules):
        raise ShapeError(f"{agent} has {len(rules)} rules; there is no rule {pos}.")
    rule = rules[pos - 1]
    base = {f: getattr(rule, f) for f in stored}
    return Normalized("rule", "change", agent, rule.id, f"rule:{agent}:{rule.id}", stored, base)


async def _routine(
    action: str,
    target: dict[str, Any],
    changes: dict[str, Any],
    *,
    conn: Any,
    now: datetime,
    zone: tzinfo,
) -> Normalized:
    from the_one.routines.repository import AgentRoutineRepository

    agent = await _existing_agent(conn, target.get("agent"))
    repo = AgentRoutineRepository(conn)
    stored: dict[str, Any] = {}
    for f in ROUTINE_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.name == "name":
            try:
                stored["name"] = check_name(value)
            except NameRuleError as e:
                raise ShapeError(e.message) from None
        elif f.name == "prompt":
            try:
                stored["prompt"] = routine_service.validate_prompt(value)
            except RoutineFieldError as e:
                raise ShapeError(e.message) from None
        elif f.name == "schedule":
            stored.update(_check_schedule(f, value, now, zone))
        else:
            if not isinstance(value, bool):
                raise _bad(f, "true or false")
            stored["enabled"] = value
    if action == "create":
        if await repo.get_by_name(agent, stored["name"]) is not None:
            raise ShapeError(f"{agent} already has a routine named {stored['name']}.")
        return Normalized(
            "routine",
            "create",
            agent,
            None,
            f"routine:{agent}:new:{stored['name']}",
            stored,
            None,
        )
    rname = target.get("routine")
    if not isinstance(rname, str) or not rname.strip():
        raise ShapeError("Say which routine: give routine, its name.")
    routine = await repo.get_by_name(agent, rname.strip())
    if routine is None:
        raise ShapeError(f"{agent} has no routine named {_q(rname.strip())}.")
    if "name" in stored:
        other = await repo.get_by_name(agent, stored["name"])
        if other is not None and other.id != routine.id:
            raise ShapeError(f"{agent} already has a routine named {stored['name']}.")
    base: dict[str, Any] = {}
    for f in stored:
        base[f] = getattr(routine, f)
    return Normalized(
        "routine", "change", agent, routine.id, f"routine:{agent}:{routine.id}", stored, base
    )


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

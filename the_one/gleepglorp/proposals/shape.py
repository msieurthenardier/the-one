"""The primitives of the change shape GleepGlorp may propose (Mission 36 F2 L2, DD1 and DD2).

Each proposable kind (``agent``, ``rule``, ``routine``) is declared in its own module under
:mod:`the_one.gleepglorp.kinds` (its field table, normalizer, apply and wording); this module
holds what they share: :class:`FieldSpec`, :class:`ShapeError`, :class:`Normalized`, the value
checks and the name-to-id resolution. It imports nothing from ``kinds`` at module level (the
dependency runs one way); the names that moved there are still reachable here through a lazy
module ``__getattr__`` (``shape.normalize``, ``shape.SPECS`` ...), for the callers that have
not moved.

Nothing but the declared fields is accepted: any other key is refused with a sentence naming
the allowed fields. The fields the operator alone controls (``secret_ids``,
``tool_overrides``, ``mcp_overrides``, ``self_revision_requires_approval``,
``routines_self_config_enabled``, ``routines_require_approval``) appear in no spec; a test
pins that.

The stored ``changes`` use the stored model's own field names and hold ids (an agent's
``provider_config_id``, ``mcp_source_ids``, ``kb_ids``), so the approval path passes them to
the write services unchanged. A rule's ``position`` is the 1-based position the model gave
(the rule services take a 0-based index: the approval path subtracts one).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from typing import Any

from the_one.gleepglorp.view_core import _names, _surface_owners
from the_one.routines import service as routine_service  # noqa: F401 - also re-exported
from the_one.routines.limits import RoutineFieldError

ACTIONS = ("create", "change")
RESERVED_AGENTS = ("gleepglorp", "default")

_LIST_MAX = 100


class ShapeError(ValueError):
    """A proposal the shape refuses; ``str(e)`` is the plain sentence the tool returns."""


@dataclass(frozen=True)
class FieldSpec:
    """One proposable field. ``name`` is the model-facing key, ``stored`` the stored field.

    ``type``: ``text``, ``boolean``, ``integer``, ``names`` (a list of strings) or
    ``schedule`` (the canonical ``{start, repeat, ends}`` object). ``ref`` names what a
    ``names`` / ``text`` value refers to, resolved to ids: ``provider``, ``mcp``, ``kb`` or
    ``tool`` (a built-in tool name, kept as a name).

    ``path``: the stored location when it is nested or differs from ``stored`` (read and written
    through :func:`stored_get` / :func:`stored_set`). ``fill_refused`` is a sentence: when a
    ``fill_form`` call names the field, the tool answers with it and records nothing (the
    propose path never reads it; it is not part of ``describe``).
    ``address_or_command`` marks a value that is an address or a command (the outside-value
    guard, ``the_one/gleepglorp/outside.py``, then accepts it from a page the operator linked
    as well as from the operator's own text). ``rows`` marks a ``{key: value}`` field (headers,
    env); for a field that is both ``rows`` and ``address_or_command`` the guard also treats
    its keys as loader keys. ``typed_items`` marks a ``names`` field whose ADDED items grant
    something (a secret's allowed tools): after outside content, each item added (those not in
    the stored base; all of them on a create) must be named in the operator's own typed text;
    a removal is never refused.
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
    path: tuple[str, ...] | None = None
    address_or_command: bool = False
    rows: bool = False
    fill_refused: str = ""
    typed_items: bool = False


@dataclass
class Normalized:
    """What the store records for one proposal."""

    kind: str
    action: str
    agent_name: str | None
    target_id: str | None
    target_key: str
    changes: dict[str, Any]
    base: dict[str, Any] | None = None
    # Display names for the ids in ``changes``, kept out of the stored row.
    names: dict[str, Any] = field(default_factory=dict)


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


async def _provider_entries(conn: Any) -> list[tuple[str, str]]:
    return await _names(conn, "llm_providers")


async def _kb_entries(conn: Any) -> list[tuple[str, str]]:
    return await _names(conn, "knowledge_bases")


async def _mcp_entries(conn: Any) -> list[tuple[str, str]]:
    from the_one.self_configuration.constants import SURFACE_ROW_NAME

    surface_ids = set(await _surface_owners(conn))
    # The self-configuration surface row is never resolvable, by marker or by name.
    return [
        (i, n)
        for i, n in await _names(conn, "mcp_sources")
        if i not in surface_ids and n != SURFACE_ROW_NAME
    ]


@dataclass(frozen=True)
class Ref:
    """One kind of reference a field may hold: ``label`` words the refusals ("No {label} named
    ..."), ``describe_label`` the field's ``reference`` in ``describe``, ``loader`` returns the
    ``[(id, name)]`` entries a name may resolve to."""

    label: str
    describe_label: str
    loader: Callable[[Any], Awaitable[list[tuple[str, str]]]]


#: The reference kinds, by ``FieldSpec.ref``. ``tool`` is not one (a built-in tool name is kept
#: as a name, not resolved to an id).
REFS: dict[str, Ref] = {
    "provider": Ref("model provider", "a model provider's name", _provider_entries),
    "mcp": Ref("MCP server", "MCP server names", _mcp_entries),
    "kb": Ref("knowledge base", "knowledge base names", _kb_entries),
}


def _resolve_one(entries: list[tuple[str, str]], ref: str, name: str) -> str:
    """The id of the one entry named ``name`` (exact), else a plain sentence."""
    label = REFS[ref].label
    hits = [i for i, n in entries if n == name]
    if not hits:
        raise ShapeError(f"No {label} named {_q(name)}.")
    if len(hits) > 1:
        raise ShapeError(f"More than one {label} is named {_q(name)}; rename one first.")
    return hits[0]


async def _ref_entries(conn: Any, ref: str) -> list[tuple[str, str]]:
    return await REFS[ref].loader(conn)


def stored_get(spec: FieldSpec, obj: dict[str, Any]) -> Any:
    """The stored value of ``spec`` in ``obj``: ``obj[spec.stored]``, or, when ``spec.path`` is
    set, the value found by walking ``path`` through nested dicts. ``KeyError`` when absent."""
    if spec.path is None:
        return obj[spec.stored]
    value: Any = obj
    for key in spec.path:
        value = value[key]
    return value


def stored_set(spec: FieldSpec, obj: dict[str, Any], value: Any) -> dict[str, Any]:
    """``obj`` with ``value`` written at the stored location of ``spec`` (the same place
    :func:`stored_get` reads), as a new dict: the input is not mutated, only the levels walked
    are copied (sibling values are shared) and a missing intermediate level is created."""
    if spec.path is None:
        return {**obj, spec.stored: value}

    def put(level: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        head, rest = keys[0], keys[1:]
        if not rest:
            return {**level, head: value}
        child = level.get(head)
        return {**level, head: put(child if isinstance(child, dict) else {}, rest)}

    return put(obj, spec.path)


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


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


# --- the lazy re-export of what moved to ``kinds`` ------------------------------------

# Old name -> (module, attribute). Resolved on first access so this module never imports
# ``kinds`` at import time (``kinds`` imports this one).
_MOVED: dict[str, tuple[str, str]] = {
    "KINDS": ("the_one.gleepglorp.kinds", "KINDS"),
    "SPECS": ("the_one.gleepglorp.kinds", "SPECS"),
    "KIND_SUMMARIES": ("the_one.gleepglorp.kinds", "KIND_SUMMARIES"),
    "OPERATOR_ONLY_FIELDS": ("the_one.gleepglorp.kinds", "OPERATOR_ONLY_FIELDS"),
    "normalize": ("the_one.gleepglorp.kinds", "normalize"),
    "describe": ("the_one.gleepglorp.kinds", "describe"),
    "spec_for": ("the_one.gleepglorp.kinds", "spec_for"),
    "AGENT_FIELDS": ("the_one.gleepglorp.kinds.agent", "AGENT_FIELDS"),
    "RULE_FIELDS": ("the_one.gleepglorp.kinds.rule", "RULE_FIELDS"),
    "ROUTINE_FIELDS": ("the_one.gleepglorp.kinds.routine", "ROUTINE_FIELDS"),
    "SCHEDULE_EXAMPLE": ("the_one.gleepglorp.kinds.routine", "SCHEDULE_EXAMPLE"),
    "_agent_base": ("the_one.gleepglorp.kinds.agent", "agent_base"),
    "comparable_value": ("the_one.gleepglorp.kinds.agent", "comparable_value"),
}


def __getattr__(name: str) -> Any:
    target = _MOVED.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(target[0]), target[1])

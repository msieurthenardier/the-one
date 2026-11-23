"""The registry of the kinds GleepGlorp may propose (Mission 36 F4 L1a, DD2).

``REGISTRY`` is an explicit tuple, in display order; nothing registers itself on import. Every
view the rest of the app reads (``KINDS``, ``SPECS``, ``KIND_SUMMARIES``,
``OPERATOR_ONLY_FIELDS``, ``FILLABLE``) is derived from it, and :func:`normalize` and
:func:`describe` dispatch by it, so a new kind is one module and one line here.

Production code reads kind-level names from this package, not through
``the_one.gleepglorp.proposals.shape`` (which holds the primitives and a lazy re-export of
what moved, for the tests that still reach the old names).
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from the_one.gleepglorp.kinds import agent, mcp_server, provider, routine, rule
from the_one.gleepglorp.kinds.base import Kind
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import ApplyError
from the_one.gleepglorp.proposals.shape import ACTIONS, FieldSpec, Normalized, ShapeError, _q

REGISTRY: tuple[Kind, ...] = (
    agent.KIND,
    rule.KIND,
    routine.KIND,
    mcp_server.KIND,
    provider.KIND,
)

KINDS: tuple[str, ...] = tuple(k.name for k in REGISTRY)
SPECS: dict[str, tuple[FieldSpec, ...]] = {k.name: k.fields for k in REGISTRY}
KIND_SUMMARIES: dict[str, str] = {k.name: k.summary for k in REGISTRY}
OPERATOR_ONLY_FIELDS: tuple[str, ...] = tuple(f for k in REGISTRY for f in k.operator_only)
FILLABLE: tuple[str, ...] = tuple(k.name for k in REGISTRY if k.fillable)

_BY_NAME: dict[str, Kind] = {k.name: k for k in REGISTRY}

__all__ = [
    "FILLABLE",
    "KINDS",
    "KIND_SUMMARIES",
    "OPERATOR_ONLY_FIELDS",
    "REGISTRY",
    "SPECS",
    "ApplyError",
    "Kind",
    "KindDeps",
    "agent",
    "describe",
    "find",
    "get",
    "mcp_server",
    "normalize",
    "provider",
    "resolve_by_id_or_name",
    "routine",
    "rule",
    "spec_for",
    "target_args",
    "target_key",
]


def get(name: str) -> Kind:
    """The kind named ``name``; ``KeyError`` for an unknown name."""
    return _BY_NAME[name]


def find(name: Any) -> Kind | None:
    """The kind named ``name``, or ``None`` for an unknown name."""
    return _BY_NAME.get(name) if isinstance(name, str) else None


def target_key(kind: str, action: str, target_id: str | None, name: str | None) -> str:
    """The one-open-proposal key of an **id-targeted** kind: ``{kind}:{target_id}`` for a
    change, ``{kind}:new:{name}`` for a create.

    Only for kinds targeted by id (Leg 4's MCP server and provider). Agent, rule and routine
    keep their own formulas (``agent:{name}``, ``rule:{agent}:new`` / ``rule:{agent}:{id}``,
    ``routine:{agent}:new:{name}`` / ``routine:{agent}:{id}``) inline in their normalizers.
    """
    if action == "change":
        return f"{kind}:{target_id}"
    return f"{kind}:new:{name}"


def resolve_by_id_or_name(entries: list[tuple[str, str]], ref: Any, label: str) -> tuple[str, str]:
    """The ``(id, name)`` entry a model's ``ref`` names, for an id-targeted kind's resolver.

    ``entries`` is ``[(id, name)]``. An id match wins; otherwise the ref must match exactly one
    name. A name shared by several entries is refused with each match listed as ``name (id)``
    so the model can retry with an id. Raises :class:`ShapeError`.
    """
    if not isinstance(ref, str) or not ref.strip():
        raise ShapeError(f"Say which {label}: give its name or id.")
    ref = ref.strip()
    for entry_id, name in entries:
        if entry_id == ref:
            return entry_id, name
    hits = [(i, n) for i, n in entries if n == ref]
    if not hits:
        raise ShapeError(f"No {label} named {_q(ref)}.")
    if len(hits) > 1:
        listed = ", ".join(f"{n} ({i})" for i, n in hits)
        raise ShapeError(f"More than one {label} is named {_q(ref)}: {listed}. Use the id instead.")
    return hits[0]


def target_args(
    kind: Any, agent: Any = None, rule: Any = None, routine: Any = None, target: Any = None
) -> dict[str, Any]:
    """The ``target`` dict the normalizers read, from a tool call's addressing parameters.

    ``target`` is the one name-or-id parameter: for an agent it is an alias of ``agent``
    (both given and different is refused); for an MCP server or a model provider it is that
    one's id or name (``agent`` is not used); a rule and a routine are addressed by ``agent``
    plus ``rule`` / ``routine``, so ``target`` is refused for them. Raises :class:`ShapeError`.
    """
    if target is not None and kind in ("rule", "routine"):
        raise ShapeError(
            f"target isn't used for a {kind}: give agent, and "
            f"{'rule' if kind == 'rule' else 'routine'} to change one."
        )
    if kind == "agent" and target is not None:
        if agent is not None and agent != target:
            raise ShapeError("agent and target name different agents. Give one of them.")
        agent = target
    if kind == "mcp_server" and agent is not None:
        raise ShapeError("An MCP server is named with target, not agent.")
    if kind == "provider" and agent is not None:
        raise ShapeError("A model provider is named with target, not agent.")
    return {"agent": agent, "rule": rule, "routine": routine, "target": target}


def spec_for(kind: str, name: str) -> FieldSpec | None:
    return next((f for f in SPECS.get(kind, ()) if f.name == name), None)


def describe(kind: str | None = None) -> Any:
    """The ``fields`` kind's content, generated from the specs.

    No ``kind``: ``[{name, summary}]`` for the kinds. With a kind: ``{name, fields}``
    where each field is ``{name, label, type, required_on_create?, create_only?, min?, max?,
    hint?, reference?}``. An unknown kind raises ``KeyError``.
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
        if f.rows:
            d["shape"] = "an object of name → value"
        if f.address_or_command:
            d["provenance"] = "must come from you or a page you linked"
        if f.ref in ("provider", "mcp", "kb"):
            d["reference"] = {
                "provider": "a model provider's name",
                "mcp": "MCP server names",
                "kb": "knowledge base names",
            }[f.ref]
        out.append(d)
    return {"name": kind, "fields": out}


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
    mode: str = "propose",
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
            message = get(kind).create_only_message
            if message is not None:
                raise ShapeError(message(only))
            raise ShapeError(f"{', '.join(only)} can only be set when creating a {kind}.")
        if not changes:
            raise ShapeError("Nothing to change. Give at least one field in changes.")
    return await get(kind).normalize(
        action, target, changes, conn=conn, now=now, zone=zone, enc=enc, mode=mode
    )

"""Tool policy resolver.

Composes a per-agent `Tool.Config` instance from two sources:

1. tool-level config — operator-set defaults persisted in the
   `tool_configs` SQLite table (read via `ToolConfigRepository.list_all()`)
2. agent-level override — per-agent narrowing/substitution stored on
   `AgentConfig.tool_overrides`

Per-key semantics are declared on each tool's Pydantic `Config` schema
via `Annotated[type, Narrow]` / `Annotated[type, Substitute]` field
metadata (Decision 2, F2 flight design).

`Narrow` / `Substitute` are sentinel marker classes (never instantiated).
The resolver dispatches on class identity (`m is Narrow` /
`m is Substitute`) when scanning `field_info.metadata`.

The resolver itself is invoked once at `AgentFactory.create()` time
(via `BuiltinToolProvider.get_tools(...)`) — Decision 3 / Decision 8.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from the_one.platform.paths import is_within


class Narrow:
    """Marker: agent-level override for this field must be no-wider-than the
    tool-level value.

    Per-type narrowing semantics applied by the resolver:

    * `bool` — agent value `True → False` is narrowing (revoke a permission);
      `False → True` is widening and raises `ValueError`.
    * `int` / `float` (NOT `bool`) — agent value `<=` tool value is narrowing
      (lower cap → stricter); strictly greater is widening and raises.
    * `list[T]` / `tuple[T, ...]` — agent value is narrowing iff every element
      is also in the tool value (subset, allowing unhashable elements).
    * `str` and other types have no canonical narrowing — the resolver raises
      `NotImplementedError` so the field author must either declare per-tool
      narrowing semantics or use `Substitute`.

    Future flights (F3-F5) annotate caps, allowlists, and permission-bool
    fields with `Narrow`; F2's tools have empty Configs and don't trigger
    the marker dispatch.
    """


class Substitute:
    """Marker: agent-level override for this field replaces the tool-level
    value. No comparison is performed.

    Used for identity / shared-credential / KV fields (e.g., a per-agent
    auth token that overrides the tool-level default). MCP integration
    (M06+) is the primary downstream consumer.
    """


class NarrowPrefix:
    """Marker: agent-level ``list[str]`` (paths) is narrowing iff every agent
    entry is a descendant of (or equal to) at least one tool entry, checked
    via ``the_one.platform.paths.is_within``.

    Used for path-allowlist style fields where the operator declares a set of
    permitted root paths and an agent may further restrict to subtrees within
    those roots.

    Raises ``NotImplementedError`` when applied to non-list values — this
    marker is list-only. Matches F2's ``Narrow``-on-``str`` precedent for
    "marker on unsupported type" so the contract is uniform across markers.
    """


class NarrowSuperset:
    """Marker: agent-level ``list[T]`` is narrowing iff every tool entry is
    also in the agent value (agent ⊇ tool — agent ADDS restrictions).

    Inverse of ``Narrow``'s list semantic (which is agent ⊆ tool, i.e. the
    agent removes options). Used for denylist-style fields where the
    operator declares a baseline of forbidden entries and the agent may add
    more forbidden entries but never remove the operator's baseline.

    Membership check is plain ``==`` equality on raw values — string-equal
    membership; canonicalization (e.g. resolving ``~``) is the consumer's
    responsibility (see ``FilesystemConfig.model_post_init`` in F3 L2a).

    Raises ``NotImplementedError`` when applied to non-list values.
    """


class _EmptyConfig(BaseModel):
    """Private sentinel — concrete empty `BaseModel` subclass.

    Pydantic v2 forbids instantiating bare `BaseModel`
    (`PydanticUserError: BaseModel is not a concrete model class`).
    `Tool.Config` defaults to `_EmptyConfig` so subclasses inherit a
    no-op, instantiable schema. Tests that need the type import it
    directly from `the_one.tools.resolver._EmptyConfig` — leading
    underscore is intentional internal API; not exposed via
    `the_one.tools.__init__.__all__`.
    """


def _check_narrow(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """Raise ``ValueError`` if ``agent_val`` widens ``tool_val``.

    Bool check comes BEFORE int because ``bool`` is ``isinstance(int)`` in
    Python; the int branch defensively excludes bools to avoid double-handling.
    """
    if isinstance(agent_val, bool) and isinstance(tool_val, bool):
        # Narrow on bool: agent may revoke (True → False) or match.
        # Widening = False → True (False on the tool means "denied"; agent
        # cannot grant what the operator denied).
        if agent_val is True and tool_val is False:
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; only narrowing allowed"
            )
        return
    if (
        isinstance(agent_val, (int, float))
        and isinstance(tool_val, (int, float))
        and not isinstance(agent_val, bool)
        and not isinstance(tool_val, bool)
    ):
        if agent_val > tool_val:
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; only narrowing allowed"
            )
        return
    if isinstance(agent_val, (list, tuple)) and isinstance(tool_val, (list, tuple)):
        # Subset check via `in` works for unhashable elements (dicts, lists),
        # which `set()`-based comparison would not.
        if not all(item in tool_val for item in agent_val):
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; only narrowing allowed"
            )
        return
    raise NotImplementedError(
        f"Narrow on {type(agent_val).__name__} field {schema_name}.{field_name}; "
        "declare per-tool narrowing semantics or use Substitute"
    )


def _check_narrow_prefix(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """Raise if ``agent_val`` widens ``tool_val`` under prefix-containment
    semantics. Both must be ``list[str]``; non-list values raise
    ``NotImplementedError`` (matches F2's ``Narrow``-on-``str`` precedent)."""
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise NotImplementedError(
            f"NarrowPrefix on non-list field {schema_name}.{field_name}; marker is list-only"
        )
    for ap in agent_val:
        if not any(is_within(ap, tp) for tp in tool_val):
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; "
                f"'{ap}' not within any tool entry"
            )


def _check_narrow_superset(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """Raise if ``agent_val`` widens ``tool_val`` under superset-membership
    semantics (agent must contain every tool entry). Membership uses ``==``
    on raw values — canonicalization is consumer-side."""
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise NotImplementedError(
            f"NarrowSuperset on non-list field {schema_name}.{field_name}; marker is list-only"
        )
    for tp in tool_val:
        if tp not in agent_val:
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; "
                f"tool entry '{tp}' missing from agent value"
            )


def resolve(
    schema: type[BaseModel],
    tool_config: dict | None,
    agent_override: dict | None,
) -> BaseModel:
    """Compose tool-level + agent-level config per schema-declared semantics.

    Order of operations:

    1. Empty-schema short-circuit — if ``schema.model_fields == {}``, return
       ``schema()`` immediately. F2's seven tools all hit this path.
    2. Locked-down NULL — if ``agent_override is None`` (Decision 1), validate
       ``tool_config or {}`` against the schema and return.
    3. Per-key dispatch — for each ``(key, field_info)`` in
       ``schema.model_fields``, if the key is in ``agent_override`` consult
       ``field_info.metadata``:
       * ``Narrow`` only → run ``_check_narrow``; on pass, override replaces
         the tool value in the merged dict.
       * ``Substitute`` only → override replaces the tool value, no compare.
       * Both markers → ``ValueError`` (design error).
       * Neither marker → ``ValueError`` (design error; F3+ must annotate).
    4. ``schema.model_validate(merged)`` — Pydantic's default ``extra="ignore"``
       drops unknown override keys silently.
    """
    # 1. Empty schema → short-circuit (F2's tools all hit this).
    if not schema.model_fields:
        return schema()

    # 2. Locked-down NULL semantic.
    merged: dict[str, Any] = dict(tool_config or {})
    if agent_override is None:
        return schema.model_validate(merged)

    # 3. Per-key dispatch.
    for key, field_info in schema.model_fields.items():
        if key not in agent_override:
            continue
        markers = field_info.metadata
        has_narrow = any(m is Narrow for m in markers)
        has_narrow_prefix = any(m is NarrowPrefix for m in markers)
        has_narrow_superset = any(m is NarrowSuperset for m in markers)
        has_substitute = any(m is Substitute for m in markers)
        marker_count = sum([has_narrow, has_narrow_prefix, has_narrow_superset, has_substitute])
        if marker_count > 1:
            raise ValueError(
                f"field {schema.__name__}.{key} has multiple narrow/substitute "
                "markers; declare exactly one of "
                "(Narrow, NarrowPrefix, NarrowSuperset, Substitute)"
            )
        if marker_count == 0:
            raise ValueError(
                f"field {schema.__name__}.{key} has no Narrow/Substitute marker; "
                "declare one of (Narrow, NarrowPrefix, NarrowSuperset, Substitute)"
            )
        tool_val = merged.get(key, field_info.default)
        if has_narrow:
            _check_narrow(key, schema.__name__, tool_val, agent_override[key])
        elif has_narrow_prefix:
            _check_narrow_prefix(key, schema.__name__, tool_val, agent_override[key])
        elif has_narrow_superset:
            _check_narrow_superset(key, schema.__name__, tool_val, agent_override[key])
        # Substitute path: no check; merge below performs replacement.
        merged[key] = agent_override[key]

    # 4. Final validation (drops unknown keys via extra="ignore" default).
    return schema.model_validate(merged)

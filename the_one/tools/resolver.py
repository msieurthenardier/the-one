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
                f"agent override widens {schema_name}.{field_name}; "
                "only narrowing allowed"
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
                f"agent override widens {schema_name}.{field_name}; "
                "only narrowing allowed"
            )
        return
    if isinstance(agent_val, (list, tuple)) and isinstance(tool_val, (list, tuple)):
        # Subset check via `in` works for unhashable elements (dicts, lists),
        # which `set()`-based comparison would not.
        if not all(item in tool_val for item in agent_val):
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; "
                "only narrowing allowed"
            )
        return
    raise NotImplementedError(
        f"Narrow on {type(agent_val).__name__} field {schema_name}.{field_name}; "
        "declare per-tool narrowing semantics or use Substitute"
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
        has_substitute = any(m is Substitute for m in markers)
        if has_narrow and has_substitute:
            raise ValueError(
                f"field {schema.__name__}.{key} has both Narrow and "
                "Substitute markers"
            )
        if not (has_narrow or has_substitute):
            raise ValueError(
                f"field {schema.__name__}.{key} has no Narrow/Substitute "
                "marker; cannot resolve"
            )
        if has_narrow:
            tool_val = merged.get(key, field_info.default)
            _check_narrow(key, schema.__name__, tool_val, agent_override[key])
        merged[key] = agent_override[key]

    # 4. Final validation (drops unknown keys via extra="ignore" default).
    return schema.model_validate(merged)

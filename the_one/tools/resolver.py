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

Two entry points share one set of per-field rules (sortie 07, DD1):

* `resolve` is **strict**: it raises on a widening or invalid override
  (`OverrideWidensError`, a `ValueError`, for a widening). The save path
  uses it.
* `clip_override` is **total**: it never raises for any JSON value and returns
  the override narrowed to fit, plus the list of changes it made. The build
  path uses it in front of `resolve`, so a stale override can never stop an
  agent from being built.

`check_field` and `clip_field` are the public per-field helpers both entry
points go through, so a caller that validates a single field (the save path)
does not re-implement a marker rule.

The resolver itself is invoked once at `AgentFactory.create()` time
(via `BuiltinToolProvider.get_tools(...)`) — Decision 3 / Decision 8.
"""

from __future__ import annotations

import logging
import math
import typing
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from the_one.platform.paths import canonicalize, is_within

logger = logging.getLogger(__name__)

# The reserved allow-list entry that means "no host at all". An empty
# ``host_allowlist`` means "any host", so "nothing allowed" needs a value of its
# own; ``_web_config._url_check`` refuses every URL when it sees this entry,
# without any DNS work (sortie 07, DD4). Lives here (not in ``_web_config``)
# because ``_web_config`` imports the markers from this module.
NO_HOSTS = "none.invalid"


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
    """Marker: a denied-list field. The agent's list only ever ADDS entries:
    the effective value is the operator's list joined with the agent's
    (app-wide ∪ agent), so the agent can never hold fewer denied entries than
    the operator (sortie 07, DD3).

    Because a union can never be a widening, the check no longer raises for a
    list value; a stored full union from before the change resolves to the
    same set. Membership is plain ``==`` on raw values — canonicalization
    (e.g. resolving ``~``) is the consumer's responsibility (see
    ``FilesystemConfig.model_post_init``).

    Raises ``NotImplementedError`` when applied to non-list values.
    """


class NarrowAnyWhenEmpty:
    """Marker: an allow-list where an EMPTY list means "any" (``host_allowlist``).

    Empty means "any host" on **both** sides, so:

    * a list containing ``NO_HOSTS`` means "no hosts" and always fits;
    * otherwise the agent list fits when the app-wide list is empty (anything is
      narrower than any host), or when the agent list is non-empty and every
      entry is in the app-wide list;
    * an agent ``[]`` against a non-empty app-wide list is "any host", wider
      than the app-wide list, so it widens.

    Raises ``NotImplementedError`` when applied to non-list values.
    """


_MARKERS = (Narrow, NarrowAnyWhenEmpty, NarrowPrefix, NarrowSuperset, Substitute)

MARKER_NAMES: dict[type, str] = {m: m.__name__ for m in _MARKERS}

# Deny-list fields holding filesystem paths: an agent entry that cannot be
# canonicalised is dropped by the clip (no canonical path can fall under it, so
# dropping it widens nothing, and ``FilesystemConfig.model_post_init`` would
# otherwise raise at build).
PATH_DENYLIST_FIELDS = frozenset({"path_denylist"})

_DEFAULT_FIELD = "timeout_seconds_default"
_MAX_FIELD = "timeout_seconds_max"


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


class OverrideWidensError(ValueError):
    """An agent override widens the app-wide value of one field.

    A ``ValueError`` whose ``str()`` is the same text the resolver has always
    raised, so message-pinning tests and logs are unchanged. The structured
    attributes let the save path (a later leg) build its own sentence:

    * ``schema_name`` — the Config class name (``"FilesystemConfig"``);
    * ``field`` — the field name;
    * ``marker`` — the marker name (``"NarrowPrefix"``);
    * ``value`` — the offending value (a path entry, a list, a number);
    * ``tool`` — the tool name, when the caller passed ``tool_name``.
    """

    def __init__(
        self,
        message: str,
        *,
        schema_name: str,
        field: str,
        marker: str,
        value: Any = None,
        tool: str | None = None,
    ) -> None:
        super().__init__(message)
        self.schema_name = schema_name
        self.field = field
        self.marker = marker
        self.value = value
        self.tool = tool


def _widens(
    schema_name: str,
    field_name: str,
    marker: type,
    value: Any,
    *,
    detail: str | None = None,
) -> OverrideWidensError:
    return OverrideWidensError(
        f"agent override widens {schema_name}.{field_name}; {detail or 'only narrowing allowed'}",
        schema_name=schema_name,
        field=field_name,
        marker=MARKER_NAMES[marker],
        value=value,
    )


# ---------------------------------------------------------------------------
# Marker lookup and baseline value
# ---------------------------------------------------------------------------


def field_marker(schema: type[BaseModel], field_name: str) -> type:
    """Return the one resolver marker declared on ``schema.field_name``.

    Raises ``ValueError`` (a design error, as before) for a field with no marker
    or with several.
    """
    metadata = schema.model_fields[field_name].metadata
    found = [m for m in _MARKERS if any(x is m for x in metadata)]
    if len(found) > 1:
        raise ValueError(
            f"field {schema.__name__}.{field_name} has multiple narrow/substitute "
            "markers; declare exactly one of "
            "(Narrow, NarrowAnyWhenEmpty, NarrowPrefix, NarrowSuperset, Substitute)"
        )
    if not found:
        raise ValueError(
            f"field {schema.__name__}.{field_name} has no Narrow/Substitute marker; "
            "declare one of "
            "(Narrow, NarrowAnyWhenEmpty, NarrowPrefix, NarrowSuperset, Substitute)"
        )
    return found[0]


def baseline_value(schema: type[BaseModel], field_name: str, tool_config: dict | None) -> Any:
    """The app-wide value of a field: the stored row's value, else the schema
    default.

    Squawk 0248: a ``default_factory`` field (the denylists) has
    ``field_info.default is PydanticUndefined``, so the factory is called for the
    baseline. Never ``schema()``: ``model_post_init`` may add runtime-only
    entries (FilesystemConfig appends the secrets dir).
    """
    if isinstance(tool_config, dict) and field_name in tool_config:
        return tool_config[field_name]
    return schema.model_fields[field_name].get_default(call_default_factory=True, validated_data={})


# ---------------------------------------------------------------------------
# Strict checks
# ---------------------------------------------------------------------------


def _check_narrow(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """Raise ``OverrideWidensError`` if ``agent_val`` widens ``tool_val``.

    Bool check comes BEFORE int because ``bool`` is ``isinstance(int)`` in
    Python; the int branch defensively excludes bools to avoid double-handling.
    """
    if isinstance(agent_val, bool) and isinstance(tool_val, bool):
        # Narrow on bool: agent may revoke (True → False) or match.
        # Widening = False → True (False on the tool means "denied"; agent
        # cannot grant what the operator denied).
        if agent_val is True and tool_val is False:
            raise _widens(schema_name, field_name, Narrow, agent_val)
        return
    if (
        isinstance(agent_val, (int, float))
        and isinstance(tool_val, (int, float))
        and not isinstance(agent_val, bool)
        and not isinstance(tool_val, bool)
    ):
        if agent_val > tool_val:
            raise _widens(schema_name, field_name, Narrow, agent_val)
        return
    if isinstance(agent_val, (list, tuple)) and isinstance(tool_val, (list, tuple)):
        # Subset check via `in` works for unhashable elements (dicts, lists),
        # which `set()`-based comparison would not.
        for item in agent_val:
            if item not in tool_val:
                raise _widens(schema_name, field_name, Narrow, item)
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
        if not isinstance(ap, str):
            raise NotImplementedError(
                f"NarrowPrefix entry of type {type(ap).__name__} in "
                f"{schema_name}.{field_name}; entries must be strings"
            )
        if not any(is_within(ap, tp) for tp in tool_val):
            raise _widens(
                schema_name,
                field_name,
                NarrowPrefix,
                ap,
                detail=f"'{ap}' not within any tool entry",
            )


def _check_narrow_superset(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """A denied-list field resolves as app-wide ∪ agent (DD3), so no list value
    can widen it. Only a non-list value is refused (``NotImplementedError``)."""
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise NotImplementedError(
            f"NarrowSuperset on non-list field {schema_name}.{field_name}; marker is list-only"
        )


def _check_any_when_empty(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """Raise if ``agent_val`` widens ``tool_val`` for an any-when-empty list."""
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise NotImplementedError(
            f"NarrowAnyWhenEmpty on non-list field {schema_name}.{field_name}; marker is list-only"
        )
    if NO_HOSTS in agent_val:
        return  # "no hosts" always fits
    if not tool_val:
        return  # the app-wide value is "any"; anything is narrower
    if NO_HOSTS in tool_val:
        # The app-wide list refuses every host (even beside other entries): an
        # agent list without NO_HOSTS would let those hosts back in.
        raise _widens(schema_name, field_name, NarrowAnyWhenEmpty, agent_val)
    if not agent_val:
        # An empty agent list is "any", wider than a non-empty app-wide list.
        raise _widens(schema_name, field_name, NarrowAnyWhenEmpty, agent_val)
    for item in agent_val:
        if item not in tool_val:
            raise _widens(schema_name, field_name, NarrowAnyWhenEmpty, item)


def check_field(
    schema: type[BaseModel],
    field_name: str,
    tool_val: Any,
    agent_val: Any,
    *,
    tool_name: str | None = None,
) -> None:
    """Strictly check one agent value against the app-wide value of one field.

    Returns ``None`` when the value fits. Raises ``OverrideWidensError`` (with
    ``field``, ``marker``, ``value`` and, when given, ``tool``) for a widening,
    ``NotImplementedError`` for a type the marker cannot interpret, and
    ``ValueError`` for a field with no or several markers. Path canonicalisation
    errors (``RuntimeError``/``OSError``/``ValueError``) propagate from
    ``NarrowPrefix`` fields. A ``Substitute`` field is never checked.
    """
    marker = field_marker(schema, field_name)
    name = schema.__name__
    try:
        if marker is Narrow:
            _check_narrow(field_name, name, tool_val, agent_val)
        elif marker is NarrowPrefix:
            _check_narrow_prefix(field_name, name, tool_val, agent_val)
        elif marker is NarrowSuperset:
            _check_narrow_superset(field_name, name, tool_val, agent_val)
        elif marker is NarrowAnyWhenEmpty:
            _check_any_when_empty(field_name, name, tool_val, agent_val)
    except OverrideWidensError as exc:
        exc.tool = tool_name
        raise


def combine_field(marker: type, tool_val: Any, agent_val: Any) -> Any:
    """The merged value of a field the agent overrides: the agent's value, except
    a denied list, which is the app-wide list joined with the agent's entries."""
    if marker is NarrowSuperset and isinstance(tool_val, list) and isinstance(agent_val, list):
        return list(tool_val) + [a for a in agent_val if a not in tool_val]
    return agent_val


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldClip:
    """The outcome of clipping one field.

    * ``value`` — the clipped agent value (meaningless when ``drop_key``);
    * ``drop_key`` — the key is removed from the override (it inherits);
    * ``dropped`` — the entries/values that no longer apply (may be empty:
      an agent ``host_allowlist: []`` clipped to a non-empty app-wide list);
    * ``kind`` — ``None`` when the value fits unchanged, else ``"narrowed"``
      (outside the app-wide value) or ``"invalid"`` (a value the field cannot
      hold at all).
    """

    value: Any
    drop_key: bool = False
    dropped: list = field(default_factory=list)
    kind: str | None = None

    @property
    def changed(self) -> bool:
        return self.kind is not None


@dataclass(frozen=True)
class ClipChange:
    """One change ``clip_override`` made: ``kind`` is ``narrowed``, ``invalid`` or
    ``coupled`` (report-only: the default timeout follows a lower maximum, never
    written to the override); ``effective`` is the value the field now takes."""

    field: str
    kind: str
    dropped: list
    effective: Any


@dataclass(frozen=True)
class ClipResult:
    """``override`` is the narrowed override (``None`` when the input was
    ``None``; never holds a key the input lacked); ``changes`` the changes made."""

    override: dict | None
    changes: tuple[ClipChange, ...] = ()


def _canon(path: Any) -> Path | None:
    """Canonical path, or ``None`` for anything that cannot be canonicalised
    (a non-string, ``~nosuchuser``, a symlink loop, a NUL byte)."""
    if not isinstance(path, str):
        return None
    try:
        return canonicalize(path)
    except (RuntimeError, OSError, ValueError):
        return None


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _bounds(field_info: Any) -> tuple[Any, Any]:
    lo = hi = None
    for m in field_info.metadata:
        if getattr(m, "ge", None) is not None:
            lo = m.ge
        if getattr(m, "le", None) is not None:
            hi = m.le
    return lo, hi


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _drop(agent_val: Any) -> FieldClip:
    return FieldClip(None, True, [agent_val], "invalid")


def _clip_narrow(field_info: Any, tool_val: Any, agent_val: Any) -> FieldClip:
    annotation = field_info.annotation
    origin = typing.get_origin(annotation)
    if annotation is bool:
        if not isinstance(agent_val, bool) or not isinstance(tool_val, bool):
            return _drop(agent_val)
        if agent_val is True and tool_val is False:
            return FieldClip(False, False, [agent_val], "narrowed")
        return FieldClip(agent_val)
    if annotation in (int, float):
        if not _is_number(agent_val) or not _is_number(tool_val):
            return _drop(agent_val)
        if isinstance(agent_val, float) and not math.isfinite(agent_val):
            return _drop(agent_val)
        value: Any = agent_val
        invalid = False
        if annotation is int and isinstance(value, float):
            value = math.floor(value)  # the narrower whole number
            invalid = value != agent_val
        lo, hi = _bounds(field_info)
        if lo is not None and value < lo:
            value, invalid = lo, True
        if hi is not None and value > hi:
            value, invalid = hi, True
        narrowed = False
        if value > tool_val:
            value, narrowed = tool_val, True
        if invalid or narrowed:
            return FieldClip(value, False, [agent_val], "invalid" if invalid else "narrowed")
        return FieldClip(agent_val)
    if origin in (list, tuple):
        if not isinstance(agent_val, list):
            return FieldClip([], False, [agent_val], "invalid")
        allowed = tool_val if isinstance(tool_val, list) else []
        keep: list = []
        dropped: list = []
        invalid = False
        for item in agent_val:
            if not isinstance(item, str):
                dropped.append(item)
                invalid = True
            elif item in allowed:
                keep.append(item)
            else:
                dropped.append(item)
        if dropped:
            return FieldClip(keep, False, dropped, "invalid" if invalid else "narrowed")
        return FieldClip(agent_val)
    return _drop(agent_val)  # no canonical narrowing for this type


def _clip_any_when_empty(tool_val: Any, agent_val: Any) -> FieldClip:
    if not isinstance(agent_val, list):
        return FieldClip([NO_HOSTS], False, [agent_val], "invalid")
    dropped = [a for a in agent_val if not isinstance(a, str)]
    invalid = bool(dropped)
    entries = [a for a in agent_val if isinstance(a, str)]
    if not isinstance(tool_val, list):
        # An uninterpretable app-wide value allows nothing (fail closed).
        app_hosts: list[str] = [NO_HOSTS]
        app_any = False
    else:
        app_hosts = [h for h in tool_val if isinstance(h, str)]
        app_any = not tool_val
        if tool_val and (not app_hosts or NO_HOSTS in app_hosts):
            # "No hosts" on the app-wide side, even when listed beside other hosts
            # (the entry refuses every URL): an agent can only keep "no hosts".
            app_hosts = [NO_HOSTS]
    if NO_HOSTS in entries:
        keep = entries
    elif app_any:
        # Anything is narrower than "any host"; but a list emptied by bad entries
        # must not become `[]`, which would mean "any host".
        keep = entries or ([NO_HOSTS] if agent_val else [])
    elif not agent_val:
        # An agent "any host" against a non-empty app-wide list: the app-wide list.
        return FieldClip(list(app_hosts), False, [], "narrowed")
    else:
        keep = [h for h in entries if h in app_hosts]
        dropped += [h for h in entries if h not in app_hosts]
        if not keep:
            keep = [NO_HOSTS]
    if dropped:
        return FieldClip(keep, False, dropped, "invalid" if invalid else "narrowed")
    return FieldClip(agent_val)


def _clip_prefix(tool_val: Any, agent_val: Any) -> FieldClip:
    if not isinstance(agent_val, list):
        return FieldClip([], False, [agent_val], "invalid")
    roots: list[tuple[str, Path]] = []
    if isinstance(tool_val, list):
        for o in tool_val:
            c = _canon(o)
            if c is not None:  # an uncanonicalisable app-wide entry contains nothing
                roots.append((o, c))
    kept: list[str] = []
    kept_canon: list[Path] = []
    dropped: list = []
    invalid = False
    agents: list[tuple[str, Path]] = []
    for a in agent_val:
        c = _canon(a)
        if c is None:
            dropped.append(a)
            invalid = True
            continue
        agents.append((a, c))
    for a, ac in agents:
        if any(_under(ac, oc) for _, oc in roots):
            kept.append(a)
            kept_canon.append(ac)
        else:
            dropped.append(a)
    # An app-wide entry inside an agent entry that did not fit as a whole: keep
    # the (narrower) app-wide entry.
    for a, ac in agents:
        if any(_under(ac, oc) for _, oc in roots):
            continue
        for o, oc in roots:
            if _under(oc, ac) and oc not in kept_canon:
                kept.append(o)
                kept_canon.append(oc)
    if dropped:
        return FieldClip(kept, False, dropped, "invalid" if invalid else "narrowed")
    return FieldClip(agent_val)


def _clip_superset(field_name: str, agent_val: Any) -> FieldClip:
    if not isinstance(agent_val, list):
        return _drop(agent_val)
    keep: list = []
    dropped: list = []
    for item in agent_val:
        if not isinstance(item, str) or (
            field_name in PATH_DENYLIST_FIELDS and _canon(item) is None
        ):
            dropped.append(item)
        else:
            keep.append(item)
    if dropped:
        return FieldClip(keep, False, dropped, "invalid")
    return FieldClip(agent_val)


@lru_cache(maxsize=64)
def _adapter(annotation: Any) -> TypeAdapter:
    return TypeAdapter(annotation)


def _clip_substitute(field_info: Any, agent_val: Any) -> FieldClip:
    try:
        _adapter(field_info.annotation).validate_python(agent_val)
    except (ValidationError, TypeError, ValueError):
        return _drop(agent_val)
    return FieldClip(agent_val)


def clip_field(
    schema: type[BaseModel],
    field_name: str,
    tool_val: Any,
    agent_val: Any,
) -> FieldClip:
    """Clip one agent value to fit the app-wide value of one field. Total for any
    JSON ``agent_val`` and ``tool_val`` (a value it cannot interpret is dropped or
    clipped to its strictest form, per DD2). A field with no or several markers
    cannot be set by an agent: its key is dropped."""
    try:
        marker = field_marker(schema, field_name)
    except ValueError:
        return _drop(agent_val)
    info = schema.model_fields[field_name]
    if marker is Narrow:
        return _clip_narrow(info, tool_val, agent_val)
    if marker is NarrowAnyWhenEmpty:
        return _clip_any_when_empty(tool_val, agent_val)
    if marker is NarrowPrefix:
        return _clip_prefix(tool_val, agent_val)
    if marker is NarrowSuperset:
        return _clip_superset(field_name, agent_val)
    return _clip_substitute(info, agent_val)


def clip_override(
    schema: type[BaseModel],
    tool_config: dict | None,
    agent_override: dict | None,
) -> ClipResult:
    """Narrow ``agent_override`` to fit ``tool_config``; never raises.

    The result's ``override`` can be passed to ``resolve`` without it raising
    (given a valid app-wide row), never gains a key the input lacked, and is no
    wider than either the app-wide value or, where the agent's value is
    interpretable, the agent's own value. ``changes`` lists what was clipped.
    A ``None`` override stays ``None`` (the locked-down semantic).
    """
    if agent_override is None:
        return ClipResult(None)
    if not isinstance(agent_override, dict):
        return ClipResult({})
    if not schema.model_fields:
        return ClipResult(dict(agent_override))
    row = tool_config if isinstance(tool_config, dict) else {}
    out = dict(agent_override)
    changes: dict[str, ClipChange] = {}
    for key in schema.model_fields:
        if key not in agent_override:
            continue
        agent_val = agent_override[key]
        try:
            tool_val = baseline_value(schema, key, row)
            fc = clip_field(schema, key, tool_val, agent_val)
        except Exception:  # totality net: a clip bug must never stop an agent building
            logger.exception("tool override clip failed for %s.%s", schema.__name__, key)
            tool_val = None
            fc = _drop(agent_val)
        if not fc.changed:
            continue
        if fc.drop_key:
            del out[key]
        else:
            out[key] = fc.value
        changes[key] = ClipChange(
            key, fc.kind or "invalid", fc.dropped, tool_val if fc.drop_key else fc.value
        )
    _clip_coupling(schema, row, out, agent_override, changes)
    return ClipResult(out, tuple(changes.values()))


def _clip_coupling(
    schema: type[BaseModel],
    row: dict,
    out: dict,
    original: dict,
    changes: dict[str, ClipChange],
) -> None:
    """Default timeout follows a lower maximum (DD2)."""
    if _DEFAULT_FIELD not in schema.model_fields or _MAX_FIELD not in schema.model_fields:
        return
    eff_max = out[_MAX_FIELD] if _MAX_FIELD in out else baseline_value(schema, _MAX_FIELD, row)
    eff_def = (
        out[_DEFAULT_FIELD]
        if _DEFAULT_FIELD in out
        else baseline_value(schema, _DEFAULT_FIELD, row)
    )
    if not (_is_number(eff_max) and _is_number(eff_def)) or eff_max >= eff_def:
        return
    if _DEFAULT_FIELD in out:
        # Own default above the effective maximum: lowered to it. Legacy data
        # (default above the agent's own maximum) is `invalid`; a default above
        # a tightened app-wide maximum is `narrowed`.
        kind = "invalid" if _MAX_FIELD in out else "narrowed"
        out[_DEFAULT_FIELD] = eff_max
        changes[_DEFAULT_FIELD] = ClipChange(
            _DEFAULT_FIELD, kind, [original[_DEFAULT_FIELD]], eff_max
        )
    else:
        changes[_DEFAULT_FIELD] = ClipChange(_DEFAULT_FIELD, "coupled", [eff_def], eff_max)


# ---------------------------------------------------------------------------
# Strict resolve
# ---------------------------------------------------------------------------


def resolve(
    schema: type[BaseModel],
    tool_config: dict | None,
    agent_override: dict | None,
    *,
    tool_name: str | None = None,
) -> BaseModel:
    """Compose tool-level + agent-level config per schema-declared semantics.

    Order of operations:

    1. Empty-schema short-circuit — if ``schema.model_fields == {}``, return
       ``schema()`` immediately. F2's seven tools all hit this path.
    2. Locked-down NULL — if ``agent_override is None`` (Decision 1), validate
       ``tool_config or {}`` against the schema and return.
    3. Per-key dispatch — for each ``(key, field_info)`` in
       ``schema.model_fields``, if the key is in ``agent_override`` run
       ``check_field`` (which raises ``OverrideWidensError`` for a widening and
       ``ValueError`` for a field with no or several markers), then merge: the
       override replaces the tool value, except a denied list, which is the
       union of both.
    4. Default follows a lower maximum — when the agent sets
       ``timeout_seconds_max`` below the default it inherits (it did not set
       ``timeout_seconds_default``), the effective default is lowered to it.
    5. ``schema.model_validate(merged)`` — Pydantic's default ``extra="ignore"``
       drops unknown override keys silently.

    ``tool_name`` is attached to a raised ``OverrideWidensError``.
    """
    # 1. Empty schema → short-circuit (F2's tools all hit this).
    if not schema.model_fields:
        return schema()

    # 2. Locked-down NULL semantic.
    merged: dict[str, Any] = dict(tool_config or {})
    if agent_override is None:
        return schema.model_validate(merged)

    # 3. Per-key dispatch.
    for key in schema.model_fields:
        if key not in agent_override:
            continue
        marker = field_marker(schema, key)
        tool_val = baseline_value(schema, key, merged)
        check_field(schema, key, tool_val, agent_override[key], tool_name=tool_name)
        merged[key] = combine_field(marker, tool_val, agent_override[key])

    # 4. Default follows a lower maximum.
    if (
        _DEFAULT_FIELD in schema.model_fields
        and _MAX_FIELD in schema.model_fields
        and _MAX_FIELD in agent_override
        and _DEFAULT_FIELD not in agent_override
    ):
        eff_max = merged.get(_MAX_FIELD)
        eff_def = baseline_value(schema, _DEFAULT_FIELD, merged)
        if _is_number(eff_max) and _is_number(eff_def) and eff_max < eff_def:
            merged[_DEFAULT_FIELD] = eff_max

    # 5. Final validation (drops unknown keys via extra="ignore" default).
    return schema.model_validate(merged)

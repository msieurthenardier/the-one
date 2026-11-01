"""Agent tool overrides: save-time validation and derived notices (sortie 07, DD5/DD6).

Two things live here, both built on the per-field helpers in
:mod:`the_one.tools.resolver`:

* :func:`validate_overrides` — the 422 detail list for a new or changed override
  on ``POST``/``PUT /api/agents`` (only fields that are new or differ from the
  stored value are checked, so a stale stored entry never blocks an unrelated
  save);
* :func:`compute_notices` — the ``notices`` every agent response carries: a
  stored override the app-wide setting now clips, on a field the agent tab
  renders, for a tool enabled for the agent and app-wide. Derived per response,
  never stored.

Both are blocking (path canonicalisation touches the disk), so the routes run
them in ``asyncio.to_thread``. :func:`agent_tab_renders` is the one server copy of
"does the agent tab show this field", mirroring the client's ``allowed()`` plus
the tool's ``config_fields``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from typing import Annotated, Any

from pydantic import TypeAdapter, ValidationError

from the_one.tools.resolver import (
    Narrow,
    NarrowAnyWhenEmpty,
    NarrowPrefix,
    NarrowSuperset,
    OverrideWidensError,
    Substitute,
    _EmptyConfig,
    baseline_value,
    check_field,
    clip_override,
    field_marker,
    resolve,
)

logger = logging.getLogger(__name__)

NOTICE_KIND = "tool_override_narrowed"
_DEFAULT_FIELD = "timeout_seconds_default"
_MAX_FIELD = "timeout_seconds_max"
_MEMO_SIZE = 512

# The markers the agent tab renders a control for (the client's ``allowed()``);
# a plain boolean field is rendered whatever its marker.
_RENDERED_MARKERS = (Narrow, NarrowSuperset, NarrowPrefix, Substitute, NarrowAnyWhenEmpty)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def hidden_field_names(tool_cls: type, config_cls: type) -> set[str]:
    """Config fields the tool's ``config_fields`` leaves out of its editor
    (empty when ``config_fields`` is ``None``: all shown)."""
    shown = getattr(tool_cls, "config_fields", None)
    if shown is None:
        return set()
    return set(config_cls.model_fields) - set(shown)


def agent_tab_renders(tool_cls: type, field_name: str) -> bool:
    """Whether the agent tab renders ``field_name`` of ``tool_cls``'s Config.

    Not hidden by ``config_fields``, and either a boolean or a field whose marker
    is one of the five the client's ``allowed()`` accepts. Pinned against the
    client rule by a test.
    """
    config_cls = tool_cls.Config
    info = config_cls.model_fields.get(field_name)
    if info is None or field_name in hidden_field_names(tool_cls, config_cls):
        return False
    if info.annotation is bool:
        return True
    try:
        marker = field_marker(config_cls, field_name)
    except ValueError:
        return False
    return marker in _RENDERED_MARKERS


def field_title(schema: type, field_name: str) -> str:
    """The field's schema ``title`` (what the Settings editor shows)."""
    info = schema.model_fields[field_name]
    return info.title or field_name.replace("_", " ").capitalize()


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _settings_path(tool: str) -> str:
    return f"Settings › Built-in tools › {tool}"


def _quote(values: list) -> str:
    return ", ".join(f"`{v}`" for v in values)


def _merged(row: Any) -> dict:
    return row.merged_config() if row is not None else {}


def _detail(tool: str, field_name: str | None, msg: str) -> dict:
    loc = ["tool_overrides", tool] + ([field_name] if field_name else [])
    return {"type": "tool_override", "loc": loc, "msg": msg}


# ---------------------------------------------------------------------------
# Save-time validation (DD5)
# ---------------------------------------------------------------------------


def _widens_sentence(
    exc: OverrideWidensError, tool: str, title: str, schema: type, tool_val: Any
) -> str:
    where = _settings_path(tool)
    value = exc.value
    if exc.marker == "NarrowPrefix":
        return f"`{value}` is outside {tool}'s app-wide {title}. Add it in {where} first."
    if exc.marker == "Narrow" and isinstance(value, bool):
        return (
            f"{title} is off for {tool} app-wide, so it can't be turned on for one agent. "
            f"Turn it on in {where} first."
        )
    if exc.marker == "Narrow" and isinstance(value, (int, float)):
        return f"{title} can be at most {tool_val} for {tool}, the app-wide value."
    if isinstance(value, list):
        return (
            f"{title} for {tool} can't be wider than the app-wide list. Change it in {where} first."
        )
    return f"`{value}` isn't in {tool}'s app-wide {title}. Add it in {where} first."


def validate_overrides(
    stored: dict[str, dict] | None,
    incoming: dict[str, dict] | None,
    rows: dict[str, Any],
) -> list[dict]:
    """The 422 detail list for the new or changed fields of ``incoming``.

    ``stored`` is the agent's stored map (``None`` on create: every field is
    new); ``rows`` maps a tool name to its ``ToolConfig`` row. Returns ``[]``
    when everything fits. Blocking: run it in a worker thread.
    """
    if not incoming:
        return []
    from the_one.tools.builtins import _TOOL_CLASSES

    stored = stored or {}
    details: list[dict] = []
    for tool, entry in incoming.items():
        if not isinstance(entry, dict):
            continue  # AgentConfig validation already refuses this shape
        old = stored.get(tool)
        old = old if isinstance(old, dict) else {}
        tool_cls = _TOOL_CLASSES.get(tool)
        if tool_cls is None:
            if tool not in stored or _canon(entry) != _canon(stored[tool]):
                details.append(_detail(tool, None, f"{tool} isn't a built-in tool."))
            continue
        schema = tool_cls.Config
        if schema is _EmptyConfig or not schema.model_fields:
            continue
        row = _merged(rows.get(tool))
        changed = [
            k
            for k in entry
            if k in schema.model_fields and (k not in old or _canon(entry[k]) != _canon(old[k]))
        ]
        passed: list[str] = []
        for key in changed:
            problem = _check_changed_field(schema, tool, key, entry[key], row)
            if problem is None:
                passed.append(key)
            else:
                details.append(_detail(tool, key, problem))
        details.extend(_cross_field(schema, tool, row, entry, changed, passed))
    return details


def _check_changed_field(schema: type, tool: str, key: str, value: Any, row: dict) -> str | None:
    """The sentence for the first problem with one changed field, else ``None``."""
    title = field_title(schema, key)
    try:
        field_marker(schema, key)
    except ValueError:
        return f"{title} can't be changed for one agent; it is set in {_settings_path(tool)}."
    tool_val = baseline_value(schema, key, row)
    try:
        check_field(schema, key, tool_val, value, tool_name=tool)
    except OverrideWidensError as exc:
        return _widens_sentence(exc, tool, title, schema, tool_val)
    except NotImplementedError:
        return f"{title} for {tool} has the wrong kind of value."
    except (RuntimeError, OSError, ValueError):
        return f"A path in {title} for {tool} can't be read. Check each path."
    info = schema.model_fields[key]
    try:
        TypeAdapter(Annotated[info.annotation, *info.metadata]).validate_python(value)
    except ValidationError as exc:
        return f"{title} for {tool} isn't valid: {exc.errors()[0]['msg']}."
    return None


def _cross_field(
    schema: type, tool: str, row: dict, entry: dict, changed: list[str], passed: list[str]
) -> list[dict]:
    """Cross-field rules (default above max) over the whole entry, never
    re-checking an unchanged field.

    The candidate is the changed fields that passed plus the unchanged stored
    fields passed through ``clip_override`` (total), so an unchanged stale field
    can never refuse the save.
    """
    if not passed:
        return []
    unchanged = {k: v for k, v in entry.items() if k in schema.model_fields and k not in changed}
    clipped = clip_override(schema, row, unchanged).override or {}
    candidate = {**clipped, **{k: entry[k] for k in passed}}
    try:
        resolve(schema, row, candidate, tool_name=tool)
    except ValidationError as exc:
        out: list[dict] = []
        seen: set[str] = set()
        for err in exc.errors(include_context=False, include_input=False):
            loc = err.get("loc") or ()
            if loc:
                field_name = str(loc[0])
                msg = f"{field_title(schema, field_name)} for {tool} isn't valid: {err['msg']}."
            else:
                # A model-level error: attribute it to the field that changed,
                # the default when both did.
                field_name = (
                    _DEFAULT_FIELD
                    if _DEFAULT_FIELD in passed
                    else _MAX_FIELD
                    if _MAX_FIELD in passed
                    else ""
                )
                msg = (
                    f"{field_title(schema, _DEFAULT_FIELD)} can't be higher than "
                    f"{field_title(schema, _MAX_FIELD)} for {tool}."
                    if _DEFAULT_FIELD in schema.model_fields
                    else f"{tool}'s settings don't fit together: {err['msg']}."
                )
            if field_name not in passed:
                # Only an invalid app-wide row can fail a field the agent did not
                # change; the build clips around it, so it never refuses a save.
                logger.warning(
                    "tool override check: app-wide row for %s fails %r: %s",
                    tool,
                    loc,
                    err["msg"],
                )
                continue
            if field_name in seen:
                continue
            seen.add(field_name)
            out.append(_detail(tool, field_name, msg))
        return out
    return []


# ---------------------------------------------------------------------------
# Notices (DD6)
# ---------------------------------------------------------------------------

_memo: OrderedDict[str, tuple[tuple[str, str, tuple, Any], ...]] = OrderedDict()
_memo_lock = threading.Lock()


def _fingerprint(tool: str, entry: dict, merged_row: dict) -> str:
    """A hash of the two inputs, so no raw secret is ever a dict key."""
    blob = json.dumps([tool, entry, merged_row], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _clipped_changes(
    tool: str, schema: type, entry: dict, merged_row: dict
) -> tuple[tuple[str, str, tuple, Any], ...]:
    """The narrowed/invalid changes for one tool entry, memoised on both inputs.

    Disk state (symlinks) is a third input the fingerprint cannot see; a cached
    result can stay stale until either input changes. Accepted (DD6).
    """
    key = _fingerprint(tool, entry, merged_row)
    with _memo_lock:
        hit = _memo.get(key)
        if hit is not None:
            _memo.move_to_end(key)
            return hit
    result = clip_override(schema, merged_row, entry)
    value = tuple(
        (c.field, c.kind, tuple(c.dropped), c.effective)
        for c in result.changes
        if c.kind in ("narrowed", "invalid")
    )
    with _memo_lock:
        _memo[key] = value
        _memo.move_to_end(key)
        while len(_memo) > _MEMO_SIZE:
            _memo.popitem(last=False)
    return value


def _notice_message(
    tool: str, title: str, field_name: str, kind: str, dropped: list, eff: Any
) -> str:
    if kind == "narrowed" and not dropped and field_name == "host_allowlist":
        return f"{tool}'s {title} was any host; the app-wide setting now limits it to its own list."
    if kind == "narrowed":
        return (
            f"{tool}'s {title} was narrowed by the app-wide setting: "
            f"{_quote(dropped)} no longer applies."
        )
    shown = _quote(eff) if isinstance(eff, list) else f"`{eff}`"
    return f"{tool}'s {title} held a value that can't be used, so it now takes {shown}."


def compute_notices(cfg: Any, rows: dict[str, Any]) -> list[dict]:
    """The clip notices for one agent. ``rows`` maps a tool name to its
    ``ToolConfig`` row (a tool with no row is enabled, with the default config).
    Blocking (path canonicalisation): run it in a worker thread."""
    overrides = getattr(cfg, "tool_overrides", None)
    if not overrides:
        return []
    from the_one.tools.builtins import _TOOL_CLASSES

    notices: list[dict] = []
    for tool, entry in overrides.items():
        tool_cls = _TOOL_CLASSES.get(tool)
        if tool_cls is None or not isinstance(entry, dict):
            continue
        schema = tool_cls.Config
        if schema is _EmptyConfig or not schema.model_fields:
            continue
        row = rows.get(tool)
        if not cfg.is_tool_enabled(tool) or (row is not None and not row.enabled):
            continue
        for field_name, kind, dropped, effective in _clipped_changes(
            tool, schema, entry, _merged(row)
        ):
            if not agent_tab_renders(tool_cls, field_name):
                continue
            title = field_title(schema, field_name)
            dropped_list = list(dropped)
            notices.append(
                {
                    "kind": NOTICE_KIND,
                    "tool": tool,
                    "field": field_name,
                    "field_title": title,
                    "dropped": dropped_list,
                    "effective": effective,
                    "message": _notice_message(
                        tool, title, field_name, kind, dropped_list, effective
                    ),
                }
            )
    return notices


def compute_notices_for_many(cfgs: list[Any], rows: dict[str, Any]) -> list[list[dict]]:
    """:func:`compute_notices` for each config, in order (one thread hop for a list)."""
    return [compute_notices(cfg, rows) for cfg in cfgs]


def rows_by_name(configs: list[Any]) -> dict[str, Any]:
    """``ToolConfigRepository.list()`` rows keyed by tool name."""
    return {c.name: c for c in configs}


__all__ = [
    "NOTICE_KIND",
    "agent_tab_renders",
    "compute_notices",
    "compute_notices_for_many",
    "field_title",
    "hidden_field_names",
    "rows_by_name",
    "validate_overrides",
]

"""The ``tool_config`` kind: change a built-in tool's app-wide settings (Mission 36 F5 L4a, DD7).

The ``tool_configs`` row of one built-in tool, as edited in Settings › Built-in tools. A tool
is addressed by its name (``addressing="id"``, the id is the name): there is no create, because
every built-in tool has a row or its defaults, and a change is the only action for a proposal and
a fill. The write is the tool-config write service's (``the_one/tools/config_service.py``), so
the operator's own validation applies, the status mark rides in the write's transaction and a
change never drops a stored API key.

**What GleepGlorp may set** (the operator's decision: ordinary fields only), defined positively:
the allowlist :data:`ALLOWLIST` intersected with the fields the named tool *shows* (its
``config_fields``; ``None`` means all), plus ``enabled``. Every other Config field of every
built-in tool is operator-only, computed here as *the union of all Config fields minus the
allowlist*, so a field added to a Config later is operator-only until someone adds it to the
allowlist: allowed folders, command lists, host lists and the redirect cap, the user agent, the
sandbox switch and every API key. A field on the allowlist that the named tool does not show is
refused in ``normalize`` (after the tool is resolved), because a value for it would be silently
dropped by the editor's hidden-field rule.

**The base** holds effective values (the stored value over that tool's own Config default;
``enabled`` defaults to on), so a tool with no saved row works.

**Warnings** are read when an open card renders, so they stay cheap: the narrowing warning runs
only for a proposal, and only when a named number moves below its current value (no agent is
loaded otherwise; ``tool_overrides`` is encrypted).
"""

from __future__ import annotations

import ipaddress
import json
from datetime import datetime, tzinfo
from typing import Any
from urllib.parse import urlsplit

import aiosqlite

from the_one.gleepglorp.kinds.base import Kind, changed_labels, id_fill_extras
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    _bad,
    _check_int,
    _check_text,
    _q,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.tools import config_service as svc
from the_one.tools.builtins import _TOOL_CLASSES, builtin_tool_names

#: The Config fields GleepGlorp may set (besides ``enabled``), when the named tool shows them.
ALLOWLIST: tuple[str, ...] = (
    "timeout_seconds_default",
    "timeout_seconds_max",
    "output_cap_bytes",
    "pty_session_idle_ttl_seconds",
    "max_concurrent_sessions",
    "read_size_cap_bytes",
    "response_size_cap_bytes",
    "search_backend",
    "searxng_base_url",
    "google_pse_cse_id",
)

SEARCH_BACKENDS: tuple[str, ...] = ("duckduckgo", "searxng", "google_pse", "brave", "tavily")
#: The backends that need an API key, and the secret field each reads.
KEYED_BACKENDS: dict[str, str] = {
    "google_pse": "google_pse_api_key",
    "brave": "brave_api_key",
    "tavily": "tavily_api_key",
}

#: The numeric fields that can narrow an agent's own override (the only ones the narrowing
#: warning looks at; path lists, which also narrow, are operator-only here).
NARROWING_FIELDS: tuple[str, ...] = tuple(
    f for f in ALLOWLIST if f not in ("search_backend", "searxng_base_url", "google_pse_cse_id")
)

#: Tools whose turning on deserves a warning: the execution and web categories plus the
#: file-writing tools. The categories live client-side (``tool-categories.js``); a test pins this
#: set against that table.
TURN_ON_WARNED: frozenset[str] = frozenset(
    {
        # execution
        "shell",
        "python_exec",
        "shell_session_start",
        "shell_session_send",
        "shell_session_close",
        "shell_session_list",
        # web
        "download_file",
        "fetch_url",
        "http_request",
        "web_search",
        # file-writing
        "write_file",
        "edit_file",
        "delete_file",
        "move_file",
        "mkdir",
    }
)

TOOLS_PAGE = "[Built-in tools](#settings/tools)"
KEY_HANDOFF = f"Only you enter API keys, on the {TOOLS_PAGE} page. I never take or fill them."

_HINTS: dict[str, str] = {
    "timeout_seconds_default": "seconds; at most the maximum timeout",
    "timeout_seconds_max": "seconds; at least the default timeout",
    "output_cap_bytes": "bytes of output kept",
    "pty_session_idle_ttl_seconds": "seconds before an idle session closes",
    "max_concurrent_sessions": "open sessions at once",
    "read_size_cap_bytes": "bytes read at most",
    "response_size_cap_bytes": "bytes of a response kept",
    "search_backend": f"one of {', '.join(SEARCH_BACKENDS)}; a keyed one needs the operator's key",
    "searxng_base_url": "the SearXNG address, or empty",
    "google_pse_cse_id": "the Google search engine ID, or empty",
}
_TYPES: dict[str, str] = {
    f: ("text" if f in ("search_backend", "searxng_base_url", "google_pse_cse_id") else "integer")
    for f in ALLOWLIST
}
_TEXT_ADDRESS = ("searxng_base_url", "google_pse_cse_id")
#: Longest accepted text (characters): the Config models do not bound these, so the spec does.
_TEXT_MAX: dict[str, int] = {
    "search_backend": 32,
    "searxng_base_url": 2048,
    "google_pse_cse_id": 128,
}


def _config_info(field_name: str) -> Any:
    """The pydantic field info of ``field_name`` in the first built-in Config that has it."""
    for cls in _TOOL_CLASSES.values():
        info = cls.Config.model_fields.get(field_name)
        if info is not None:
            return info
    raise KeyError(field_name)


def _bounds(field_name: str) -> tuple[int | None, int | None]:
    lo = hi = None
    for meta in _config_info(field_name).metadata:
        lo = getattr(meta, "ge", lo)
        hi = getattr(meta, "le", hi)
    return lo, hi


def _applies_to(field_name: str) -> tuple[str, ...]:
    """The tools that expose ``field_name``: its Config has it and the tool shows it."""
    out = []
    for name, cls in _TOOL_CLASSES.items():
        if field_name not in cls.Config.model_fields:
            continue
        shown = getattr(cls, "config_fields", None)
        if shown is None or field_name in shown:
            out.append(name)
    return tuple(out)


def _spec(field_name: str) -> FieldSpec:
    lo, hi = (None, None) if _TYPES[field_name] == "text" else _bounds(field_name)
    return FieldSpec(
        field_name,
        _TYPES[field_name],
        _config_info(field_name).title or field_name,
        field_name,
        hint=_HINTS[field_name],
        min=lo,
        max=_TEXT_MAX[field_name] if _TYPES[field_name] == "text" else hi,
        path=("config", field_name),
        address_or_command=field_name in _TEXT_ADDRESS,
        applies_to=_applies_to(field_name),
    )


TOOL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "enabled",
        "boolean",
        "Enabled",
        "enabled",
        hint="on or off for every agent; a tool with no saved settings is on",
        path=("enabled",),
    ),
    *(_spec(f) for f in ALLOWLIST),
)
_BY_NAME = {f.name: f for f in TOOL_FIELDS}


def _all_config_fields() -> dict[str, str]:
    """Every Config field of every built-in tool, ``{name: title}``, sorted by name."""
    out: dict[str, str] = {}
    for cls in _TOOL_CLASSES.values():
        for field_name, info in cls.Config.model_fields.items():
            out.setdefault(field_name, info.title or field_name)
    return dict(sorted(out.items()))


_FIELD_TITLES = _all_config_fields()
#: Fields the operator alone controls: every built-in Config field that is not on the allowlist,
#: in sorted order. Never in any kind's spec (a test asserts it).
OPERATOR_ONLY: tuple[str, ...] = tuple(f for f in _FIELD_TITLES if f not in ALLOWLIST)
_SECRET_FIELDS: frozenset[str] = frozenset(
    f for cls in _TOOL_CLASSES.values() for f in svc.secret_field_names(cls.Config)
)


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def operator_only_message(names: list[str]) -> str:
    if any(n in _SECRET_FIELDS for n in names):
        return KEY_HANDOFF
    labels = [f"“{_FIELD_TITLES.get(n, n)}”" for n in names]
    return f"Only you can change {_join(labels)}, on the {TOOLS_PAGE} page."


# --- the stored row, read without secrets -------------------------------------------------


async def _load(conn: Any, name: str) -> Any:
    """The stored row (without its secrets), or ``None`` for a tool that was never saved."""
    from the_one.db.models import ToolConfig

    async with conn.execute(
        "SELECT enabled, config FROM tool_configs WHERE name = ?", (name,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return ToolConfig(name=name, enabled=bool(row[0]), config=json.loads(row[1] or "{}"))


def _shown(name: str) -> set[str]:
    cls = svc.tool_class(name)
    fields = set(cls.Config.model_fields)
    shown = getattr(cls, "config_fields", None)
    return fields if shown is None else fields & set(shown)


# --- normalize ----------------------------------------------------------------------------


def _tool_name(ref: Any) -> str:
    if not isinstance(ref, str) or not ref.strip():
        raise ShapeError("Say which built-in tool: give its name.")
    name = ref.strip().lower()
    if name not in builtin_tool_names():
        raise ShapeError(f"There is no built-in tool named {_q(ref.strip())}.")
    return name


def _check_value(spec: FieldSpec, value: Any) -> Any:
    if spec.type == "boolean":
        if not isinstance(value, bool):
            raise _bad(spec, "true or false")
        return value
    if spec.type == "integer":
        return _check_int(spec, value)
    text = _check_text(spec, value).strip()
    if spec.name == "search_backend":
        text = text.lower()
        if text not in SEARCH_BACKENDS:
            raise ShapeError(f"search_backend must be one of: {', '.join(SEARCH_BACKENDS)}.")
    return text


def _first_message(e: svc.ToolConfigWriteError) -> str:
    items = e.items
    msg = items[0]["msg"] if items else str(e.detail)
    return msg.removeprefix("Value error, ")


def _dry_run(name: str, current: Any, stored: dict[str, Any]) -> None:
    """Run the real write's computation over the effective row; raise its first message."""
    config = {k: v for k, v in stored.items() if k != "enabled"}
    data: dict[str, Any] = {}
    if "enabled" in stored:
        data["enabled"] = stored["enabled"]
    if config:
        data["config"] = {**(current.config if current is not None else {}), **config}
    try:
        svc.compute_tool_config_update(svc.tool_class(name), name, data, current)
    except svc.ToolConfigWriteError as e:
        raise ShapeError(_first_message(e)) from None


async def normalize(
    action: str,
    target: dict[str, Any],
    changes: dict[str, Any],
    *,
    conn: Any,
    now: datetime,
    zone: tzinfo,
    enc: Any = None,
    mode: str = "propose",
) -> Normalized:
    name = _tool_name(target.get("target"))
    shown = _shown(name)
    stored: dict[str, Any] = {}
    for key, value in changes.items():
        spec = _BY_NAME.get(key)
        if spec is None:
            raise ShapeError(
                f"tool_config changes can't include {_q(key)!r}. "
                f"Allowed fields: {', '.join(_BY_NAME)}."
            )
        if key != "enabled" and key not in shown:
            raise ShapeError(f"The {name} tool has no {spec.label} setting.")
        stored[key] = _check_value(spec, value)
    current = await _load(conn, name)
    _dry_run(name, current, stored)
    effective = svc.effective_values(name, current)
    base = {k: effective[k] for k in stored}
    return Normalized("tool_config", "change", None, name, f"tool_config:{name}", stored, base)


# --- exists, apply, wording ---------------------------------------------------------------


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    return bool(p.target_id) and p.target_id in builtin_tool_names()


def _write_deps(deps: KindDeps) -> svc.ToolConfigWriteDeps:
    async def agent_store() -> Any:
        return deps.agent.store

    return svc.ToolConfigWriteDeps(repo=deps.agent.tool_config_repo, agent_store=agent_store)


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
        assert p.target_id is not None
        await svc.change_tool_config(
            _write_deps(deps), p.target_id, changes, base=base, override=override, on_commit=mark
        )
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(TOOL_FIELDS, p)
    return {
        "summary": f"Changed {', '.join(labels)} on the {p.target_id} tool",
        "agent": None,
        "fields": labels,
    }


def title(p: Proposal) -> str:
    return f"change the {p.target_id} tool"


def card_title(action: str, name: str | None) -> str:
    return f"Change the {name} tool" if name else "Change a built-in tool"


async def card_extras(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """The card's title (the tool's name) and ``target_gone``, never ``agent_name``."""
    gone = not (p.target_id and p.target_id in builtin_tool_names())
    return {"title": card_title("change", p.target_id), "target_gone": gone}


async def fill_stale(conn: Any, fill: Any, labels: dict[str, str]) -> list[dict[str, Any]]:
    """The ``stale`` rows of a tool-config fill: the named fields whose effective value moved
    since the fill was made, labelled."""
    if not fill.target_id or fill.target_id not in builtin_tool_names():
        return []
    current = await _load(conn, fill.target_id)
    return [
        {
            "field": row["field"],
            "label": labels.get(row["field"], row["field"]),
            "current": row["current"],
            "proposed": row["proposed"],
        }
        for row in svc.stale_fields(fill.target_id, current, fill.changes, fill.base or {})
    ]


fill_extras = id_fill_extras(card_extras, stale_fn=fill_stale)


# --- warnings -----------------------------------------------------------------------------


def _impact_sentence(agents: list[dict[str, Any]]) -> str:
    """The editor's impact-dialog wording (``tools-editor.js`` ``impactMessage``) as one
    sentence."""
    items = []
    for a in agents:
        parts = []
        for f in a["fields"]:
            gone = [str(d) for d in f.get("dropped") or []]
            parts.append(
                f["field_title"]
                + (
                    f" ({', '.join(gone)} would no longer apply)"
                    if gone
                    else " (was any host; it would take the app-wide list)"
                )
            )
        items.append(f"{a['agent']}: {'; '.join(parts)}")
    return (
        "These agents hold their own value for this tool that the new setting narrows: "
        f"{'; '.join(items)}. They keep working; each shows a notice on its Tools tab."
    )


def _web_config_tool() -> str | None:
    """The tool whose row the provider resolves the shared ``WebConfig`` from: the first in
    ``_TOOL_CLASSES`` whose Config is ``WebConfig`` (``builtins.py`` ``cross_configs``)."""
    from the_one.tools._web_config import WebConfig

    return next((n for n, c in _TOOL_CLASSES.items() if c.Config is WebConfig), None)


def _is_private_literal(host: str) -> bool:
    from the_one.tools._web_config import _is_ssrf_blocked

    if host == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return _is_ssrf_blocked(host)


async def _private_address_warning(conn: Any, url: str) -> str | None:
    """The literal host only, no DNS: ``localhost`` or a blocked IP literal that the shared web
    row's ``extra_allowed_hosts`` does not already open."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    if not host or not _is_private_literal(host):
        return None
    web_tool = _web_config_tool()
    row = await _load(conn, web_tool) if web_tool else None
    allowed = [str(h).lower() for h in (row.config.get("extra_allowed_hosts") or [])] if row else []
    if host in allowed:
        return None
    return (
        f"{host} is a local or private address, which search requests cannot reach until "
        f"you add it to Extra allowed hosts on the {TOOLS_PAGE} page."
    )


async def _narrowing_warning(
    conn: Any, enc: Any, name: str, changes: dict[str, Any], effective: dict[str, Any]
) -> str | None:
    """Only when a named number moves below its current value: loads no agent otherwise."""
    lowered = {
        k: v for k, v in changes.items() if k in NARROWING_FIELDS and v < effective.get(k, v)
    }
    if not lowered:
        return None
    from the_one.db.repositories import SQLiteAgentStore, ToolConfigRepository
    from the_one.tools import override_validation

    repo = ToolConfigRepository(conn, enc)
    rows = override_validation.rows_by_name(await repo.list())
    existing = rows.get(name)
    # ``enabled`` is a row field, never part of ``config``.
    cfg_changes = {k: v for k, v in changes.items() if k != "enabled"}
    data = {"config": {**(existing.config if existing else {}), **cfg_changes}}
    if "enabled" in changes:
        data["enabled"] = changes["enabled"]
    try:
        enabled, config, secrets = svc.compute_tool_config_update(
            svc.tool_class(name), name, data, existing
        )
    except svc.ToolConfigWriteError:
        return None

    async def agent_store() -> Any:
        return SQLiteAgentStore(conn, enc)

    deps = svc.ToolConfigWriteDeps(repo=repo, agent_store=agent_store)
    agents = await svc.impact_for_row(
        deps, name, rows, svc.proposed_row(name, existing, enabled, config, secrets)
    )
    return _impact_sentence(agents) if agents else None


async def warnings(
    conn: aiosqlite.Connection, enc: Any, p: Proposal, mode: str = "propose"
) -> list[str]:
    """What the operator should know before approving, read from the stored row (a never-saved
    tool reads as its defaults, never a ``KeyError``)."""
    out: list[str] = []
    name = p.target_id
    if not name or name not in builtin_tool_names():
        return out
    changes = p.changes
    current = await _load(conn, name)
    effective = svc.effective_values(name, current)
    if mode == "propose":
        sentence = await _narrowing_warning(conn, enc, name, changes, effective)
        if sentence:
            out.append(sentence)
    enabled = changes.get("enabled")
    if enabled is False:
        out.append(f"Turning {name} off removes it from every agent until it is turned back on.")
    elif enabled is True and name in TURN_ON_WARNED and not effective["enabled"]:
        out.append(f"Turning {name} on lets every agent that allows it use it.")
    backend = changes.get("search_backend")
    if backend in KEYED_BACKENDS:
        from the_one.db.repositories import ToolConfigRepository

        try:
            row = await ToolConfigRepository(conn, enc).get(name)
            have_key = bool(row.secrets.get(KEYED_BACKENDS[backend]))
        except KeyError:
            have_key = False
        if not have_key:
            out.append(
                f"Enter the {backend} API key on the {TOOLS_PAGE} page; search fails until then."
            )
    url = changes.get("searxng_base_url")
    if isinstance(url, str) and url:
        sentence = await _private_address_warning(conn, url)
        if sentence:
            out.append(sentence)
    return out


KIND = Kind(
    name="tool_config",
    label="built-in tool",
    summary="Change a built-in tool's on/off switch or its ordinary limits and search settings",
    fields=TOOL_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    addressing="id",
    target_noun="A built-in tool",
    fill_extras=fill_extras,
    keyerror_is_gone=False,
    operator_only=OPERATOR_ONLY,
    operator_only_message=operator_only_message,
    fillable=("change",),
    actions=("change",),
    relaxed_guard_keys=frozenset({"searxng_base_url"}),
    title=title,
    card_title=card_title,
    warnings=warnings,
    card_extras=card_extras,
)

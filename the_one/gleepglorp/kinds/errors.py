"""How a kind's apply reports a failure the apply path records (Mission 36 F4 L1a, DD3).

A kind's ``apply`` raises :class:`ApplyError` for the three failures ``apply_proposal`` turns
into an outcome, and lets anything else propagate:

- ``stale``: the stored value moved since the proposal was made (rows
  ``[{field, label, current, proposed}]``; nothing written, the status unchanged);
- ``gone``: the target no longer exists (the proposal is withdrawn);
- ``items``: a validation failure (``[{loc, msg}]``; the proposal is marked ``failed``).

:func:`translate` is the one place service errors are mapped; every kind's ``apply`` calls it
(through :func:`reraise`).
"""

from __future__ import annotations

import sqlite3
from typing import Any, NoReturn

import aiosqlite

from the_one.agent.service import AgentStaleError, AgentWriteError
from the_one.app_settings_service import AppSettingsStaleError, AppSettingsWriteError
from the_one.gleepglorp.proposals.store import ROWS_LABELS, Proposal, display_values
from the_one.knowledge.service import KbNotFound, KbStaleError, KbWriteError
from the_one.llm.provider_service import ProviderNotFound, ProviderStaleError, ProviderWriteError
from the_one.mcp.service import McpSourceNotFound, McpStaleError, McpWriteError
from the_one.naming import NameRuleError
from the_one.routines import service as routine_service
from the_one.routines.describe import schedule_sentence
from the_one.routines.limits import (
    RoutineFieldError,
    RoutineLimitError,
    RoutineNameTaken,
    RoutineScheduleError,
)
from the_one.routines.proposals import ProposalStaleError
from the_one.secret_store.service import SecretNotFound, SecretStaleError, SecretWriteError
from the_one.tools.config_service import ToolConfigStaleError, ToolConfigWriteError

#: The write errors whose ``.items`` is the approve path's ``[{loc, msg}]``.
_ITEMS_ERRORS = (
    ProviderWriteError,
    KbWriteError,
    SecretWriteError,
    ToolConfigWriteError,
    AppSettingsWriteError,
)
#: The stale errors whose ``fields`` are ``[{field, current, proposed}]`` rows.
_FIELD_STALE_ERRORS = (
    AgentStaleError,
    ProviderStaleError,
    KbStaleError,
    SecretStaleError,
    ToolConfigStaleError,
    AppSettingsStaleError,
)


class ApplyError(Exception):
    """A failure the apply records. ``stale`` rows, ``gone`` or ``items`` (in that order of
    precedence in ``apply_proposal``)."""

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        *,
        stale: list[dict[str, Any]] | None = None,
        gone: bool = False,
    ) -> None:
        super().__init__("apply failed")
        self.items = list(items) if items else []
        self.stale = stale
        self.gone = gone


def _items(detail: Any) -> list[dict[str, Any]]:
    if isinstance(detail, list):
        out = []
        for d in detail:
            if isinstance(d, dict):
                loc = [x if isinstance(x, (str, int)) else str(x) for x in d.get("loc", [])]
                out.append({"loc": loc, "msg": str(d.get("msg", ""))})
            else:
                out.append({"loc": [], "msg": str(d)})
        return out
    return [{"loc": [], "msg": str(detail)}]


def _failure_items(exc: BaseException) -> list[dict[str, Any]] | None:
    if isinstance(exc, AgentWriteError):
        return _items(exc.detail)
    if isinstance(exc, McpWriteError):
        return exc.items
    if isinstance(exc, _ITEMS_ERRORS):
        return exc.items
    if isinstance(exc, RoutineFieldError):
        return [{"loc": [exc.field], "msg": exc.message}]
    if isinstance(exc, RoutineScheduleError):
        return [{"loc": ["schedule"], "msg": exc.detail}]
    if isinstance(exc, RoutineLimitError):
        return [{"loc": [], "msg": exc.detail}]
    if isinstance(exc, RoutineNameTaken):
        return [{"loc": ["name"], "msg": exc.detail}]
    if isinstance(exc, NameRuleError):
        return [{"loc": ["name"], "msg": exc.message}]
    return None


def _is_gone(exc: BaseException, p: Proposal) -> bool:
    if isinstance(exc, AgentWriteError):
        return exc.status == 404
    if isinstance(exc, (McpWriteError, *_ITEMS_ERRORS)):
        return exc.status == 404
    if isinstance(exc, (McpSourceNotFound, ProviderNotFound, KbNotFound, SecretNotFound)):
        return True
    from the_one.gleepglorp import kinds  # lazy: ``kinds`` imports this module

    kind = kinds.find(p.kind)
    if kind is None:
        return False
    if isinstance(exc, KeyError):
        return kind.keyerror_is_gone
    # An agent-owned kind (rules, routines) has a foreign key to agents.
    return (
        isinstance(exc, sqlite3.IntegrityError)
        and p.action == "create"
        and kind.addressing == "agent-owned"
    )


def _labels(kind: str) -> dict[str, str]:
    from the_one.gleepglorp import kinds

    return {f.stored: f.label for f in kinds.SPECS[kind]}


async def _agent_or_rule_stale(
    conn: aiosqlite.Connection,
    p: Proposal,
    e: AgentStaleError
    | ProviderStaleError
    | KbStaleError
    | SecretStaleError
    | ToolConfigStaleError
    | AppSettingsStaleError,
) -> list[dict[str, Any]]:
    labels = _labels(p.kind)
    cur = await display_values(conn, {f["field"]: f["current"] for f in e.fields})
    prop = await display_values(conn, {f["field"]: f["proposed"] for f in e.fields})
    return [
        {
            "field": f["field"],
            "label": labels.get(f["field"], f["field"]),
            "current": cur[f["field"]],
            "proposed": prop[f["field"]],
        }
        for f in e.fields
    ]


async def _mcp_stale(
    conn: aiosqlite.Connection, p: Proposal, e: McpStaleError
) -> list[dict[str, Any]]:
    """Stale rows for an MCP server: a scalar field is one row; ``headers`` and ``env`` give
    one row per differing key (``headers.Accept`` labelled "Header Accept")."""
    labels = _labels(p.kind)
    out: list[dict[str, Any]] = []
    for f in e.fields:
        field = f["field"]
        cur = await display_values(conn, {field: f["current"]})
        prop = await display_values(conn, {field: f["proposed"]})
        if field in ROWS_LABELS:
            for shown in prop:
                row = shown.split(" ", 1)[1]
                out.append(
                    {
                        "field": f"{field}.{row}",
                        "label": shown,
                        "current": cur.get(shown),
                        "proposed": prop[shown],
                    }
                )
        else:
            out.append(
                {
                    "field": field,
                    "label": labels.get(field, field),
                    "current": cur[field],
                    "proposed": prop[field],
                }
            )
    return out


def _routine_stale(p: Proposal, e: ProposalStaleError, zone: Any) -> list[dict[str, Any]]:
    labels = _labels("routine")
    out: list[dict[str, Any]] = []
    for pk in ("name", "prompt", "schedule", "enabled"):
        if pk not in p.changes:
            continue
        keys = [k for k in routine_service._PAYLOAD_TO_BASE[pk] if k in e.current]
        if not any(e.current.get(k) != e.base.get(k) for k in keys):
            continue
        if pk == "schedule":
            current: Any = schedule_sentence(
                e.current.get("schedule"), e.current.get("anchor_at"), zone
            )
            proposed: Any = schedule_sentence(
                p.changes.get("schedule"), p.changes.get("anchor_at"), zone
            )
        else:
            current, proposed = e.current.get(pk), p.changes[pk]
        out.append({"field": pk, "label": labels[pk], "current": current, "proposed": proposed})
    return out


async def translate(
    exc: BaseException, p: Proposal, *, conn: aiosqlite.Connection, zone: Any
) -> BaseException:
    """``exc`` as an :class:`ApplyError` when it is a failure the apply records, else ``exc``
    itself (the caller re-raises it unchanged).

    The order is the apply path's: stale, then gone, then validation items.
    """
    if isinstance(exc, _FIELD_STALE_ERRORS):
        return ApplyError(stale=await _agent_or_rule_stale(conn, p, exc))
    if isinstance(exc, McpStaleError):
        return ApplyError(stale=await _mcp_stale(conn, p, exc))
    if isinstance(exc, ProposalStaleError):
        return ApplyError(stale=_routine_stale(p, exc, await zone()))
    if _is_gone(exc, p):
        return ApplyError(gone=True)
    items = _failure_items(exc)
    if items is None:
        return exc
    return ApplyError(items)


async def reraise(
    exc: BaseException, p: Proposal, *, conn: aiosqlite.Connection, zone: Any
) -> NoReturn:
    """Raise the translation of ``exc``; call it from inside the ``except`` block."""
    err = await translate(exc, p, conn=conn, zone=zone)
    if err is exc:
        raise exc
    raise err from exc

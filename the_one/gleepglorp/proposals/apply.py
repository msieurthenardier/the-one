"""Apply or dismiss a GleepGlorp proposal (Mission 36 F2 L4, DD3, DD4, DD7, DD9, DD10).

:func:`apply_proposal` is the one apply path: the approve route calls it, and so does the eval
harness. It runs the stored change through the Leg 1 write services (so the operator's own
validation applies) with the proposal's status update riding in the write's own transaction
(``on_commit`` / the routine ``ProposalRunner``): the change lands once or not at all.

Order inside :func:`apply_proposal`:

(a) before any write: an ``applied`` row answers "already applied"; a dismissed or withdrawn
    row is ``closed``; a busy chat is ``busy``; a missing target withdraws the proposal
    (``gone``).
(b) the service call, with the status mark inside its transaction.
(c) on any exception, the row is re-read first: if another call applied it meanwhile the answer
    is "already applied", with no ``failed`` mark, no stale answer and no frames.
(d) only otherwise is the error mapped: stale (nothing written, status unchanged), gone
    (withdrawn), or failed (marked ``failed`` with ``result = {"errors": [{loc, msg}]}``).
    An exception that is none of these is not caught.

Frames go out after the commit: ``proposal_changed`` to the chat, then, on an apply only,
``config_changed`` to every socket.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import aiosqlite

from the_one.agent import rules_service
from the_one.agent import service as agent_service
from the_one.agent.service import AgentStaleError, AgentWriteDeps, AgentWriteError
from the_one.gleepglorp.proposals import continuation, shape
from the_one.gleepglorp.proposals.events import push_proposal_changed
from the_one.gleepglorp.proposals.store import (
    OPEN_STATUSES,
    GleepGlorpProposalRepository,
    Proposal,
    display_values,
    mark_op,
    proposal_view,
)
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
from the_one.routines.repository import AgentRoutineRepository

Outcome = Literal[
    "applied", "already_applied", "failed", "stale", "gone", "busy", "closed", "dismissed"
]

CONFIG_CHANGED = "config_changed"
# The proposal fields that are internal stored keys, not something the operator reads.
_HIDDEN_FIELDS = ("anchor_at",)


class ProposalNotFound(KeyError):  # noqa: N818 - the route answers 404
    """No proposal has this id."""


class _AlreadyResolved(Exception):  # noqa: N818
    """The status mark found the row no longer open: another call resolved it. Raised inside
    the write's transaction so the change rolls back (never a KeyError or ValueError, which
    the services map to 404 or 422)."""


@dataclass
class ProposalApplyResult:
    """What an apply or dismiss did. ``view`` is the proposal's payload (every outcome but a
    refusal that has none); ``stale`` is ``[{field, label, current, proposed}]``;
    ``status`` is the closed row's status for ``closed``."""

    outcome: Outcome
    view: dict[str, Any] | None = None
    stale: list[dict[str, Any]] = field(default_factory=list)
    status: str | None = None
    changed: list[str] = field(default_factory=list)


# --- the in-transaction mark ----------------------------------------------------------


def _mark_applied(proposal_id: int, result: dict[str, Any]):
    async def hook(conn: aiosqlite.Connection) -> None:
        if not await mark_op(
            conn, proposal_id, "applied", result=result, from_statuses=OPEN_STATUSES
        ):
            raise _AlreadyResolved

    return hook


class _MarkRunner:
    """The routine repository's ``ProposalRunner``: the same mark, run after the routine
    write inside its transaction (a create's id is added to the result)."""

    def __init__(self, proposal_id: int, result: dict[str, Any]) -> None:
        self.proposal_id = proposal_id
        self.result = result

    async def run(self, conn: aiosqlite.Connection, routine_id: str | None) -> None:
        result = dict(self.result)
        if routine_id:
            result["routine_id"] = routine_id
        if not await mark_op(
            conn, self.proposal_id, "applied", result=result, from_statuses=OPEN_STATUSES
        ):
            raise _AlreadyResolved


# --- error mapping --------------------------------------------------------------------


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


def failure_errors(exc: BaseException) -> list[dict[str, Any]] | None:
    """The ``[{loc, msg}]`` list for a validation failure, else ``None`` (not a failure the
    apply records: it propagates)."""
    if isinstance(exc, AgentWriteError):
        return _items(exc.detail)
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
    if isinstance(exc, KeyError):
        return True
    # agent_rules and agent_routines have a foreign key to agents.
    return isinstance(exc, sqlite3.IntegrityError) and (
        p.action == "create" and p.kind in ("rule", "routine")
    )


# --- summaries ------------------------------------------------------------------------


def _labels(kind: str, keys: list[str]) -> list[str]:
    by_stored = {f.stored: f.label for f in shape.SPECS[kind]}
    return [by_stored.get(k, k) for k in keys]


def _changed_keys(p: Proposal) -> list[str]:
    return [k for k in p.changes if k not in _HIDDEN_FIELDS]


def _summary(p: Proposal, routine_name: str | None, sentence: str | None) -> dict[str, Any]:
    keys = _changed_keys(p)
    labels = _labels(p.kind, keys)
    agent = p.agent_name or ""
    if p.kind == "agent":
        text = (
            f"Created agent {agent}"
            if p.action == "create"
            else f"Changed {', '.join(labels)} on {agent}"
        )
    elif p.kind == "rule":
        text = (
            f"Added a rule to {agent}"
            if p.action == "create"
            else f"Changed a rule of {agent}: {', '.join(labels)}"
        )
    else:
        name = routine_name or ""
        text = (
            f"Added routine {name} to {agent}"
            if p.action == "create"
            else f"Changed routine {name} of {agent}: {', '.join(labels)}"
        )
    out: dict[str, Any] = {"summary": text, "agent": agent, "fields": labels}
    if p.kind == "routine":
        out["routine"] = routine_name
        if sentence is not None:
            out["schedule"] = sentence
    return out


# --- the stale payload ----------------------------------------------------------------


async def _agent_or_rule_stale(
    conn: aiosqlite.Connection, p: Proposal, e: AgentStaleError
) -> list[dict[str, Any]]:
    labels = {f.stored: f.label for f in shape.SPECS[p.kind]}
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


def _routine_stale(p: Proposal, e: ProposalStaleError, zone: Any) -> list[dict[str, Any]]:
    labels = {f.stored: f.label for f in shape.SPECS["routine"]}
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


# --- apply ----------------------------------------------------------------------------


async def _target_exists(conn: aiosqlite.Connection, deps: AgentWriteDeps, p: Proposal) -> bool:
    from the_one.db.repositories import AgentRuleRepository

    if p.kind == "agent" and p.action == "create":
        return True
    if not p.agent_name or not await deps.store.exists(p.agent_name):
        return False
    if p.kind == "agent" or p.action == "create":
        return True
    if p.kind == "rule":
        rules = await AgentRuleRepository(conn).list_for_agent(p.agent_name)
        return any(r.id == p.target_id for r in rules)
    return (
        p.target_id is not None
        and await AgentRoutineRepository(conn).get(p.agent_name, p.target_id) is not None
    )


async def _resolved(
    conn: aiosqlite.Connection, repo: GleepGlorpProposalRepository, proposal_id: int
) -> ProposalApplyResult | None:
    """The answer when the row is no longer open (applied elsewhere, or closed), else ``None``."""
    row = await repo.get(proposal_id)
    if row is None:
        raise ProposalNotFound(proposal_id)
    if row.status == "applied":
        return ProposalApplyResult("already_applied", await proposal_view(conn, row))
    if row.status in ("dismissed", "withdrawn"):
        return ProposalApplyResult("closed", status=row.status)
    return None


async def _frame(
    conn: aiosqlite.Connection, repo: GleepGlorpProposalRepository, proposal_id: int
) -> dict[str, Any]:
    row = await repo.get(proposal_id)
    assert row is not None
    view = await proposal_view(conn, row)
    await push_proposal_changed(row.session_id, view)
    return view


async def apply_proposal(
    conn: aiosqlite.Connection,
    deps: AgentWriteDeps,
    proposal_id: int,
    *,
    override: bool,
    now: datetime,
    zone: Any,
    continue_chat: bool = True,
) -> ProposalApplyResult:
    """Apply a pending (or failed) proposal; see the module docstring for the order.

    ``continue_chat`` (M36 F2 L5): after an apply, continue the chat (start the approval turn
    or record the approval). The eval harness passes ``False`` and drives it itself.

    ``zone`` is the async zone loader the routine service takes. Raises
    :class:`ProposalNotFound` for an unknown id.
    """
    from the_one.sessions._locks import is_session_busy

    repo = GleepGlorpProposalRepository(conn)
    p = await repo.get(proposal_id)
    if p is None:
        raise ProposalNotFound(proposal_id)
    # (a)
    if p.status in ("applied", "dismissed", "withdrawn"):
        return await _resolved(conn, repo, proposal_id)  # type: ignore[return-value]
    if is_session_busy(p.session_id):
        return ProposalApplyResult("busy")
    if not await _target_exists(conn, deps, p):
        return await _withdraw_gone(conn, repo, proposal_id)

    changes = dict(p.changes)
    base = dict(p.base or {})
    routine_name: str | None = changes.get("name") if p.kind == "routine" else None
    sentence: str | None = None
    if p.kind == "routine":
        tz = await zone()
        if "schedule" in changes:
            sentence = schedule_sentence(changes["schedule"], changes.get("anchor_at"), tz)
    result = _summary(p, routine_name, sentence)
    mark = _mark_applied(proposal_id, result)
    # (b)
    try:
        if p.kind == "agent" and p.action == "create":
            await agent_service.create_agent(deps, changes, on_commit=mark)
        elif p.kind == "agent":
            assert p.agent_name is not None
            await agent_service.change_agent(
                deps, p.agent_name, changes, base=base, override=override, on_commit=mark
            )
        elif p.kind == "rule" and p.action == "create":
            assert p.agent_name is not None
            pos = changes.get("position")
            await rules_service.create_rule(
                _rule_repo(conn),
                p.agent_name,
                changes["text"],
                changes.get("enabled", True),
                position=None if pos is None else pos - 1,
                on_commit=mark,
            )
        elif p.kind == "rule":
            assert p.agent_name is not None and p.target_id is not None
            await rules_service.change_rule(
                _rule_repo(conn),
                p.agent_name,
                p.target_id,
                changes,
                base=base,
                override=override,
                on_commit=mark,
            )
        else:
            routine_name = await _apply_routine(
                conn, p, changes, base, override, now, zone, result, routine_name
            )
    except Exception as exc:  # noqa: BLE001 - mapped below or re-raised
        # (c)
        row = await repo.get(proposal_id)
        if row is not None and row.status == "applied":
            return ProposalApplyResult("already_applied", await proposal_view(conn, row))
        if isinstance(exc, _AlreadyResolved):
            closed = await _resolved(conn, repo, proposal_id)
            return closed or ProposalApplyResult("closed", status=row.status if row else None)
        # (d)
        if isinstance(exc, AgentStaleError):
            return ProposalApplyResult("stale", stale=await _agent_or_rule_stale(conn, p, exc))
        if isinstance(exc, ProposalStaleError):
            return ProposalApplyResult("stale", stale=_routine_stale(p, exc, await zone()))
        if _is_gone(exc, p):
            return await _withdraw_gone(conn, repo, proposal_id)
        errors = failure_errors(exc)
        if errors is None:
            raise
        marked = await repo.mark(
            proposal_id, "failed", result={"errors": errors}, from_statuses=OPEN_STATUSES
        )
        if not marked:
            return await _resolved(conn, repo, proposal_id) or ProposalApplyResult("closed")
        return ProposalApplyResult("failed", await _frame(conn, repo, proposal_id))

    # After the commit: the chat's card, then every window.
    view = await _frame(conn, repo, proposal_id)
    changed = [k for k in p.changes if k not in _HIDDEN_FIELDS]
    from the_one.sessions._broadcast import broadcast_to_all

    await broadcast_to_all(
        {
            "type": CONFIG_CHANGED,
            "kind": p.kind,
            "agent": p.agent_name,
            "fields": changed,
            "session_id": p.session_id,
            "proposal_id": p.id,
            "at": now.isoformat(),
        }
    )
    if continue_chat:
        await continuation.on_approved(conn, p, result["summary"])
    return ProposalApplyResult("applied", view, changed=changed)


def _rule_repo(conn: aiosqlite.Connection) -> Any:
    from the_one.db.repositories import AgentRuleRepository

    return AgentRuleRepository(conn)


async def _apply_routine(
    conn: aiosqlite.Connection,
    p: Proposal,
    changes: dict[str, Any],
    base: dict[str, Any],
    override: bool,
    now: datetime,
    zone: Any,
    result: dict[str, Any],
    routine_name: str | None,
) -> str | None:
    """Run a routine create or change through the routine service as the operator would
    (``created_by="operator"``, no agent caps); the stored schedule pair is passed so the
    schedule is not re-derived. An untrusted proposal's flag is carried onto the routine."""
    assert p.agent_name is not None
    repo = AgentRoutineRepository(conn)
    flag = ("merge", list(p.untrusted_sources)) if p.untrusted else None
    runner = _MarkRunner(p.id, result)
    data = {k: changes[k] for k in ("name", "prompt", "enabled") if k in changes}
    pair = (
        await routine_service.approval_pair(
            {"schedule": changes["schedule"], "anchor_at": changes.get("anchor_at")}, zone
        )
        if "schedule" in changes
        else None
    )
    if p.action == "create":
        data.setdefault("enabled", True)
        await routine_service.create_routine(
            repo,
            p.agent_name,
            data,
            now=now,
            zone=zone,
            created_by="operator",
            agent_caps=False,
            flag=flag,  # type: ignore[arg-type]
            proposal=runner,
            schedule_pair=pair,
        )
        return routine_name
    assert p.target_id is not None
    current = await repo.get(p.agent_name, p.target_id)
    if current is None:
        raise KeyError(p.target_id)
    result["routine"] = data.get("name", current.name)
    touched = [
        k for k in routine_service._touched_base_keys("update", data | _sched(changes)) if k in base
    ]
    precheck = routine_service.stale_precheck_for(base, touched, override, changes)
    await routine_service.update_routine(
        repo,
        p.agent_name,
        current,
        data,
        now=now,
        zone=zone,
        flag=flag,  # type: ignore[arg-type]
        proposal=runner,
        precheck=precheck,
        schedule_pair=pair,
    )
    return routine_name


def _sched(changes: dict[str, Any]) -> dict[str, Any]:
    return {"schedule": changes["schedule"]} if "schedule" in changes else {}


async def _withdraw_gone(
    conn: aiosqlite.Connection, repo: GleepGlorpProposalRepository, proposal_id: int
) -> ProposalApplyResult:
    moved = await repo.mark(
        proposal_id, "withdrawn", result={"reason": "gone"}, from_statuses=OPEN_STATUSES
    )
    if not moved:
        return await _resolved(conn, repo, proposal_id) or ProposalApplyResult("closed")
    await _frame(conn, repo, proposal_id)
    return ProposalApplyResult("gone")


async def dismiss_proposal(
    conn: aiosqlite.Connection, proposal_id: int, *, continue_chat: bool = True
) -> ProposalApplyResult:
    """Dismiss an open proposal (pending or failed). Busy chat: ``busy``; any other status:
    ``closed``. Pushes ``proposal_changed`` only, then (``continue_chat``) records the
    dismissal in the chat with no turn."""
    from the_one.sessions._locks import is_session_busy

    repo = GleepGlorpProposalRepository(conn)
    p = await repo.get(proposal_id)
    if p is None:
        raise ProposalNotFound(proposal_id)
    if p.status not in OPEN_STATUSES:
        return ProposalApplyResult("closed", status=p.status)
    if is_session_busy(p.session_id):
        return ProposalApplyResult("busy")
    if not await repo.mark(proposal_id, "dismissed", from_statuses=OPEN_STATUSES):
        row = await repo.get(proposal_id)
        return ProposalApplyResult("closed", status=row.status if row else None)
    view = await _frame(conn, repo, proposal_id)
    if continue_chat:
        await continuation.on_dismissed(p)
    return ProposalApplyResult("dismissed", view)

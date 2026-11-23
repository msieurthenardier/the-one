"""Apply or dismiss a GleepGlorp proposal (Mission 36 F2 L4, DD3, DD4, DD7, DD9, DD10).

:func:`apply_proposal` is the one apply path: the approve route calls it, and so does the eval
harness. It runs the stored change through the Leg 1 write services (so the operator's own
validation applies) with the proposal's status update riding in the write's own transaction
(``on_commit`` / the routine ``ProposalRunner``): the change lands once or not at all.

The kind-specific part (does the target exist, the service call, the summary's wording) lives
in the kind's module (``the_one.gleepglorp.kinds``); a kind's ``apply`` reports a failure the
apply records as an :class:`~the_one.gleepglorp.kinds.errors.ApplyError` and lets anything
else propagate.

Order inside :func:`apply_proposal`:

(a) before any write: an ``applied`` row answers "already applied"; a dismissed or withdrawn
    row is ``closed``; a busy chat is ``busy``; a missing target withdraws the proposal
    (``gone``).
(b) the service call, with the status mark inside its transaction.
(c) on any exception, the row is re-read first: if another call applied it meanwhile the answer
    is "already applied", with no ``failed`` mark, no stale answer and no frames.
(d) only otherwise is an ``ApplyError`` folded: stale (nothing written, status unchanged),
    gone (withdrawn), or failed (marked ``failed`` with ``result = {"errors": [{loc, msg}]}``).
    An exception that is none of these is not caught.

Frames go out after the commit: ``proposal_changed`` to the chat, then, on an apply only,
``config_changed`` to every socket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, cast

import aiosqlite

# Tests patch the agent write service through this name (``proposal_apply.agent_service``):
# it is the same module object ``kinds.agent`` calls, so one patch reaches the kind.
from the_one.agent import service as agent_service  # noqa: F401
from the_one.agent.service import AgentWriteDeps
from the_one.gleepglorp import kinds
from the_one.gleepglorp.kinds.base import HIDDEN_FIELDS
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import ApplyError
from the_one.gleepglorp.proposals import continuation
from the_one.gleepglorp.proposals.events import push_proposal_changed
from the_one.gleepglorp.proposals.store import (
    OPEN_STATUSES,
    GleepGlorpProposalRepository,
    mark_op,
    proposal_view,
)

Outcome = Literal[
    "applied", "already_applied", "failed", "stale", "gone", "busy", "closed", "dismissed"
]

CONFIG_CHANGED = "config_changed"
# The proposal fields that are internal stored keys, not something the operator reads.
_HIDDEN_FIELDS = HIDDEN_FIELDS


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


# --- apply ----------------------------------------------------------------------------


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
    deps: AgentWriteDeps | KindDeps,
    proposal_id: int,
    *,
    override: bool,
    now: datetime,
    zone: Any,
    continue_chat: bool = True,
) -> ProposalApplyResult:
    """Apply a pending (or failed) proposal; see the module docstring for the order.

    ``deps`` is the agent write services' ``AgentWriteDeps`` or a ``KindDeps`` (an
    ``AgentWriteDeps`` is wrapped).

    ``continue_chat`` (M36 F2 L5): after an apply, continue the chat (start the approval turn
    or record the approval). The eval harness passes ``False`` and drives it itself.

    ``zone`` is the async zone loader the routine service takes. Raises
    :class:`ProposalNotFound` for an unknown id.
    """
    from the_one.sessions._locks import is_session_busy

    deps = KindDeps.of(deps)
    repo = GleepGlorpProposalRepository(conn)
    p = await repo.get(proposal_id)
    if p is None:
        raise ProposalNotFound(proposal_id)
    # (a)
    if p.status in ("applied", "dismissed", "withdrawn"):
        # An open row can only resolve to None if it was re-opened since the read above;
        # the original behaviour (returning that None) is kept, so the type is stated, not checked.
        return cast(ProposalApplyResult, await _resolved(conn, repo, proposal_id))
    if is_session_busy(p.session_id):
        return ProposalApplyResult("busy")
    kind = kinds.get(p.kind)
    if not await kind.exists(conn, deps, p):
        return await _withdraw_gone(conn, repo, proposal_id)

    changes = dict(p.changes)
    base = dict(p.base or {})
    result = await kind.summary_text(p, zone)
    mark = _mark_applied(proposal_id, result)
    # (b)
    try:
        await kind.apply(
            conn,
            deps,
            p,
            changes=changes,
            base=base,
            override=override,
            now=now,
            zone=zone,
            mark=mark,
            runner=_MarkRunner(p.id, result),
            result=result,
        )
    except Exception as exc:  # noqa: BLE001 - folded below or re-raised
        # (c)
        row = await repo.get(proposal_id)
        if row is not None and row.status == "applied":
            return ProposalApplyResult("already_applied", await proposal_view(conn, row))
        if isinstance(exc, _AlreadyResolved):
            closed = await _resolved(conn, repo, proposal_id)
            return closed or ProposalApplyResult("closed", status=row.status if row else None)
        # (d)
        if not isinstance(exc, ApplyError):
            raise
        if exc.stale is not None:
            return ProposalApplyResult("stale", stale=exc.stale)
        if exc.gone:
            return await _withdraw_gone(conn, repo, proposal_id)
        marked = await repo.mark(
            proposal_id, "failed", result={"errors": exc.items}, from_statuses=OPEN_STATUSES
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
            # An id-targeted create has no target_id until applied: the kind records the
            # id it generated in ``result``.
            "target_id": p.target_id or result.get("target_id"),
            "fields": changed,
            "session_id": p.session_id,
            "proposal_id": p.id,
            "at": now.isoformat(),
        }
    )
    if continue_chat:
        await continuation.on_approved(conn, p, result["summary"])
    return ProposalApplyResult("applied", view, changed=changed)


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

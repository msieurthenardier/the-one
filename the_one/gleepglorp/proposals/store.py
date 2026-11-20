"""The store for GleepGlorp's change proposals (Mission 36 F2 L2, DD4 and DD5).

One row per proposal in ``gleepglorp_proposals`` (schema v54, no foreign keys). A chat has at
most one *open* proposal (status ``pending``, or ``failed`` and still retryable); the insert
enforces that inside one transaction.

Status transitions only move through :meth:`GleepGlorpProposalRepository.mark`, which writes
``WHERE id = ? AND status IN (from_statuses)`` so a stale decision never overwrites a newer
one. :func:`mark_op` is the same write as a function over a connection, for use inside another
repository's transaction (Leg 4's ``on_commit``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from the_one.db._write_lock import write_transaction
from the_one.db.models import now_iso

OPEN_STATUSES = ("pending", "failed")
STATUSES = ("pending", "applied", "dismissed", "withdrawn", "failed")

_COLS = (
    "id, session_id, tool_call_id, kind, action, agent_name, target_id, target_key, "
    "changes, base, status, result, untrusted, untrusted_sources, created_at, resolved_at"
)


class ProposalOpen(Exception):  # noqa: N818 - a refusal carrying the open proposal's id
    """The chat already has an open proposal for something else."""

    def __init__(self, open_id: int) -> None:
        super().__init__(f"Proposal {open_id} is still open")
        self.open_id = open_id


@dataclass
class NewProposal:
    session_id: str
    kind: str
    action: str
    agent_name: str | None
    target_key: str
    changes: dict[str, Any]
    target_id: str | None = None
    base: dict[str, Any] | None = None
    tool_call_id: str | None = None
    untrusted: bool = False
    untrusted_sources: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    id: int
    session_id: str
    tool_call_id: str | None
    kind: str
    action: str
    agent_name: str | None
    target_id: str | None
    target_key: str
    changes: dict[str, Any]
    base: dict[str, Any] | None
    status: str
    result: dict[str, Any] | None
    untrusted: bool
    untrusted_sources: list[str]
    created_at: str
    resolved_at: str | None


def _loads(raw: Any, default: Any = None) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _row(row: Any) -> Proposal:
    return Proposal(
        id=row[0],
        session_id=row[1],
        tool_call_id=row[2],
        kind=row[3],
        action=row[4],
        agent_name=row[5],
        target_id=row[6],
        target_key=row[7],
        changes=_loads(row[8], {}),
        base=_loads(row[9]),
        status=row[10],
        result=_loads(row[11]),
        untrusted=bool(row[12]),
        untrusted_sources=_loads(row[13], []) or [],
        created_at=row[14],
        resolved_at=row[15],
    )


async def mark_op(
    conn: aiosqlite.Connection,
    proposal_id: int,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    from_statuses: tuple[str, ...],
) -> bool:
    """Set a proposal's status inside the caller's transaction; ``True`` when a row changed.

    Writes only ``WHERE id = ? AND status IN (from_statuses)``: a proposal already in another
    status is left alone.
    """
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status!r}")
    if not from_statuses:
        return False
    marks = ", ".join("?" for _ in from_statuses)
    async with conn.execute(
        f"UPDATE gleepglorp_proposals SET status = ?, result = ?, resolved_at = ? "  # noqa: S608
        f"WHERE id = ? AND status IN ({marks})",
        (
            status,
            json.dumps(result, separators=(",", ":")) if result is not None else None,
            None if status == "pending" else now_iso(),
            proposal_id,
            *from_statuses,
        ),
    ) as cur:
        return cur.rowcount == 1


class GleepGlorpProposalRepository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def insert(self, new: NewProposal) -> int:
        """Record a proposal, applying the one-open-per-chat rule; returns its id.

        An open proposal that is ``failed``, or has the same ``target_key``, is marked
        ``withdrawn`` (``result = {"reason": "replaced", "by": new_id}``) and the new row is
        inserted; any other open proposal refuses the insert with :class:`ProposalOpen`.
        """
        async with write_transaction(self.conn):
            async with self.conn.execute(
                f"SELECT {_COLS} FROM gleepglorp_proposals "  # noqa: S608
                "WHERE session_id = ? AND status IN ('pending', 'failed') "
                "ORDER BY id DESC",
                (new.session_id,),
            ) as cur:
                open_rows = [_row(r) for r in await cur.fetchall()]
            replace: list[Proposal] = []
            for old in open_rows:
                if old.status == "failed" or old.target_key == new.target_key:
                    replace.append(old)
                else:
                    raise ProposalOpen(old.id)
            async with self.conn.execute(
                "INSERT INTO gleepglorp_proposals (session_id, tool_call_id, kind, action, "
                "agent_name, target_id, target_key, changes, base, status, untrusted, "
                "untrusted_sources, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', "
                "?, ?, ?)",
                (
                    new.session_id,
                    new.tool_call_id,
                    new.kind,
                    new.action,
                    new.agent_name,
                    new.target_id,
                    new.target_key,
                    json.dumps(new.changes, separators=(",", ":"), ensure_ascii=False),
                    json.dumps(new.base, separators=(",", ":"), ensure_ascii=False)
                    if new.base is not None
                    else None,
                    1 if new.untrusted else 0,
                    json.dumps(new.untrusted_sources),
                    now_iso(),
                ),
            ) as cur:
                new_id = int(cur.lastrowid or 0)
            for old in replace:
                await mark_op(
                    self.conn,
                    old.id,
                    "withdrawn",
                    result={"reason": "replaced", "by": new_id},
                    from_statuses=OPEN_STATUSES,
                )
        return new_id

    async def get(self, proposal_id: int) -> Proposal | None:
        async with self.conn.execute(
            f"SELECT {_COLS} FROM gleepglorp_proposals WHERE id = ?",  # noqa: S608
            (proposal_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row(row) if row else None

    async def list_for_session(self, session_id: str) -> list[Proposal]:
        async with self.conn.execute(
            f"SELECT {_COLS} FROM gleepglorp_proposals WHERE session_id = ? ORDER BY id",  # noqa: S608
            (session_id,),
        ) as cur:
            return [_row(r) for r in await cur.fetchall()]

    async def open_for_session(self, session_id: str) -> Proposal | None:
        async with self.conn.execute(
            f"SELECT {_COLS} FROM gleepglorp_proposals "  # noqa: S608
            "WHERE session_id = ? AND status IN ('pending', 'failed') ORDER BY id DESC LIMIT 1",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row(row) if row else None

    async def mark(
        self,
        proposal_id: int,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        from_statuses: tuple[str, ...],
    ) -> bool:
        """Move a proposal to ``status`` only from a ``from_statuses`` status; ``True`` if moved."""
        async with write_transaction(self.conn):
            return await mark_op(
                self.conn, proposal_id, status, result=result, from_statuses=from_statuses
            )


# --- the payload (the contract Leg 6's client reads) ----------------------------------

_ID_FIELDS = {
    "provider_config_id": "llm_providers",
    "mcp_source_ids": "mcp_sources",
    "kb_ids": "knowledge_bases",
}
REMOVED = "(removed)"


def _display(values: dict[str, Any] | None, names: dict[str, dict[str, str]]) -> Any:
    if values is None:
        return None
    out: dict[str, Any] = {}
    for key, value in values.items():
        table = _ID_FIELDS.get(key)
        if table is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = [names[table].get(i, REMOVED) for i in value]
        elif value is None:
            out[key] = None
        else:
            out[key] = names[table].get(value, REMOVED)
    return out


async def _name_map(conn: aiosqlite.Connection) -> dict[str, dict[str, str]]:
    from the_one.gleepglorp.view_core import _names

    return {t: dict(await _names(conn, t)) for t in set(_ID_FIELDS.values())}


async def display_values(conn: aiosqlite.Connection, values: dict[str, Any]) -> dict[str, Any]:
    """``values`` (stored field names) with each id shown as the name it has now."""
    return _display(values, await _name_map(conn)) or {}


_NEXT_RUNS_SHOWN = 3


def _quoted(name: str) -> str:
    return f"“{name}”"


def _schedule_bits(values: dict[str, Any] | None, zone: Any, now: Any) -> tuple[Any, list[str]]:
    """The schedule sentence and up to three next runs (human times) for a values dict."""
    from itertools import islice

    from the_one.routines import describe, recurrence
    from the_one.routines import service as routine_service
    from the_one.routines.schedule import parse_utc

    if not isinstance(values, dict) or "schedule" not in values:
        return None, []
    text = routine_service.values_schedule_text(values, zone)
    runs: list[str] = []
    try:
        anchor = parse_utc(values["anchor_at"]) if values.get("anchor_at") else None
        for at in islice(
            recurrence.occurrences(values["schedule"], anchor, zone, now), _NEXT_RUNS_SHOWN
        ):
            runs.append(describe.describe_next(at.isoformat(), zone, now=now))
    except Exception:  # noqa: BLE001 - a card never fails over an unreadable schedule
        runs = []
    return text, runs


async def _card_extras(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """``title``, ``target_gone`` and, for a routine, the schedule text and next runs."""
    from the_one import time_zones
    from the_one.db.repositories import AgentRuleRepository
    from the_one.gleepglorp.view_core import _agent_names
    from the_one.routines.repository import AgentRoutineRepository

    agent = p.agent_name or ""
    q = _quoted(agent)
    gone = False
    out: dict[str, Any] = {}
    if p.kind == "agent":
        title = f"{'Create' if p.action == 'create' else 'Change'} agent {q}"
        if p.action == "change":
            gone = agent not in await _agent_names(conn)
    elif p.kind == "rule":
        gone = agent not in await _agent_names(conn)
        if p.action == "create":
            title = f"Add a rule to {q}"
        else:
            rules = await AgentRuleRepository(conn).list_for_agent(agent) if not gone else []
            pos = next((i for i, r in enumerate(rules, 1) if r.id == p.target_id), None)
            gone = gone or pos is None
            title = f"Change rule {pos} of {q}" if pos else f"Change a rule of {q}"
    else:
        gone = agent not in await _agent_names(conn)
        repo = AgentRoutineRepository(conn)
        if p.action == "create":
            title = f"Schedule a routine for {q}"
        else:
            routine = await repo.get(agent, p.target_id) if p.target_id and not gone else None
            gone = gone or routine is None
            rname = routine.name if routine else (p.changes.get("name") or "routine")
            title = f"Change routine {_quoted(str(rname))}"
        zone = (await time_zones.load_effective_zone(conn)).tzinfo
        now = time_zones.utcnow()
        text, runs = _schedule_bits(p.changes, zone, now)
        out["schedule_text"] = text
        out["next_runs"] = runs
        if p.base is not None:
            btext, bruns = _schedule_bits(p.base, zone, now)
            out["base_schedule_text"] = btext
            out["base_next_runs"] = bruns
    out["title"] = title
    out["target_gone"] = gone
    return out


async def proposal_view(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """The ``proposal_changed`` payload and the card's data.

    Also carries ``title`` (e.g. ``Change agent “X”``), ``target_gone`` (a change's target, or a
    rule or routine create's agent, no longer exists; computed when read, never stored) and, for
    a routine, ``schedule_text`` / ``next_runs`` (proposed) and ``base_schedule_text`` /
    ``base_next_runs`` (the schedule it was proposed against, on a change).

    Keys: ``id``, ``kind``, ``action``, ``agent_name``, ``target_id``, ``status``,
    ``result``, ``untrusted``, ``untrusted_sources``, ``created_at``, ``tool_call_id``,
    ``changes`` and ``base`` (the stored field names, with each id shown as the name it has
    now, or ``"(removed)"`` when it no longer exists) and ``labels`` (the card text for each
    field, keyed by stored field name). ``base`` is ``None`` for a create.
    """
    from the_one.gleepglorp.proposals import shape

    names = await _name_map(conn)
    extra = await _card_extras(conn, p)
    return {
        **extra,
        "id": p.id,
        "kind": p.kind,
        "action": p.action,
        "agent_name": p.agent_name,
        "target_id": p.target_id,
        "status": p.status,
        "result": p.result,
        "untrusted": p.untrusted,
        "untrusted_sources": p.untrusted_sources,
        "created_at": p.created_at,
        "resolved_at": p.resolved_at,
        "tool_call_id": p.tool_call_id,
        "changes": _display(p.changes, names),
        "base": _display(p.base, names),
        "labels": {f.stored: f.label for f in shape.SPECS.get(p.kind, ())},
    }

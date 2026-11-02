"""The agent routine-change record (Mission 33 F2, DD4/DD6).

Every change an agent makes to its routines is one row in ``agent_routine_proposals``:
``applied`` (made at once), ``pending`` (held for the operator), ``dismissed`` or
``superseded`` (replaced, or its routine went away). ``payload`` is the validated request
(a once's ``in`` already converted to an absolute ``at``); ``base`` is the raw stored
fields the change was made against, for the stale check.

Writes that belong to a routine mutation (:class:`ProposalOp`) run on the mutator's own
connection inside its one ``write_transaction``; the guard does not nest, so nothing here
opens a second one around them.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import aiosqlite
from pydantic import BaseModel, Field

from the_one import time_zones
from the_one.db._write_lock import write_transaction
from the_one.routines.limits import (
    AGENT_PENDING_PROPOSALS_MAX,
    RoutineLimitError,
    RoutineNameTaken,
)
from the_one.routines.models import Routine

Action = Literal["create", "update", "delete"]
Status = Literal["applied", "pending", "dismissed", "superseded"]


class ProposalStateError(ValueError):
    """The proposal is not pending (dismissed or superseded) and cannot be acted on (409)."""


class ProposalStaleError(ValueError):
    """The routine changed since the proposal was made (409 ``stale``)."""

    def __init__(self, current: Any, proposed: Any, base: Any) -> None:
        super().__init__("The routine has changed since this was proposed.")
        self.current = current
        self.proposed = proposed
        self.base = base


class ProposalGoneError(ValueError):
    """The routine an update was proposed for no longer exists (409 ``gone``)."""


class RoutineProposal(BaseModel):
    id: str
    agent_name: str
    routine_id: str | None = None
    routine_name: str
    action: Action
    payload: dict[str, Any] = Field(default_factory=dict)
    base: dict[str, Any] | None = None
    status: Status
    untrusted: bool = False
    untrusted_sources: list[str] = Field(default_factory=list)
    session_id: str | None = None
    created_at: str
    resolved_at: str | None = None


_COLS = (
    "id, agent_name, routine_id, routine_name, action, payload, base, status, untrusted, "
    "untrusted_sources, session_id, created_at, resolved_at"
)


def _now_iso() -> str:
    return time_zones.utcnow().isoformat()


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


def _proposal(row: Any) -> RoutineProposal:
    payload = _loads(row[5], {})
    base = _loads(row[6], None)
    sources = _loads(row[9], [])
    return RoutineProposal(
        id=row[0],
        agent_name=row[1],
        routine_id=row[2],
        routine_name=row[3],
        action=row[4],
        payload=payload if isinstance(payload, dict) else {},
        base=base if isinstance(base, dict) else None,
        status=row[7],
        untrusted=bool(row[8]),
        untrusted_sources=sources if isinstance(sources, list) else [],
        session_id=row[10],
        created_at=row[11],
        resolved_at=row[12],
    )


async def _insert(conn: aiosqlite.Connection, row: dict[str, Any], status: str, now: str) -> str:
    proposal_id = uuid.uuid4().hex
    sources = list(row.get("untrusted_sources") or [])
    await conn.execute(
        f"INSERT INTO agent_routine_proposals ({_COLS}) VALUES ({', '.join('?' * 13)})",
        (
            proposal_id,
            row["agent_name"],
            row.get("routine_id"),
            row["routine_name"],
            row["action"],
            json.dumps(row.get("payload") or {}, sort_keys=True),
            json.dumps(row["base"], sort_keys=True) if row.get("base") is not None else None,
            status,
            1 if row.get("untrusted") else 0,
            json.dumps(sources) if sources else None,
            row.get("session_id"),
            now,
            now if status != "pending" else None,
        ),
    )
    return proposal_id


@dataclass(frozen=True)
class ProposalOp:
    """A proposal write that runs inside a routine mutator's transaction, after the
    routine write (so a create's ``routine_id`` is known)."""

    kind: Literal["insert_applied", "resolve"]
    row: dict[str, Any] | None = None
    proposal_id: str | None = None

    @staticmethod
    def insert_applied(row: dict[str, Any]) -> ProposalOp:
        return ProposalOp("insert_applied", row=row)

    @staticmethod
    def resolve(proposal_id: str) -> ProposalOp:
        return ProposalOp("resolve", proposal_id=proposal_id)

    async def run(self, conn: aiosqlite.Connection, routine_id: str | None) -> None:
        if self.kind == "insert_applied":
            assert self.row is not None
            row = dict(self.row)
            # The mutator names the routine: the new id, the updated id, or None after a
            # delete (the row keeps routine_name only).
            row["routine_id"] = routine_id
            # Hand the new id back through the caller's dict, for the caller's log line.
            self.row["proposal_id"] = await _insert(conn, row, "applied", _now_iso())
            return
        assert self.proposal_id is not None
        cur = await conn.execute(
            "UPDATE agent_routine_proposals SET status = 'applied', resolved_at = ?, "
            "routine_id = COALESCE(?, routine_id) WHERE id = ? AND status = 'pending'",
            (_now_iso(), routine_id, self.proposal_id),
        )
        if cur.rowcount == 0:
            raise ProposalStateError("That change is no longer waiting for approval.")


class RoutineProposalRepository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list(
        self,
        agent_name: str,
        *,
        status: str | None = None,
        limit: int = 50,
        before: str | None = None,
    ) -> list[RoutineProposal]:
        sql = f"SELECT {_COLS} FROM agent_routine_proposals WHERE agent_name = ?"
        params: list[Any] = [agent_name]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        if before is not None:
            sql += " AND created_at < ?"
            params.append(before)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        async with self.conn.execute(sql, params) as cur:
            return [_proposal(r) for r in await cur.fetchall()]

    async def pending_count(self, agent_name: str) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM agent_routine_proposals WHERE agent_name = ? "
            "AND status = 'pending'",
            (agent_name,),
        ) as cur:
            return int((await cur.fetchone())[0])

    async def get(self, proposal_id: str) -> RoutineProposal | None:
        async with self.conn.execute(
            f"SELECT {_COLS} FROM agent_routine_proposals WHERE id = ?", (proposal_id,)
        ) as cur:
            row = await cur.fetchone()
        return _proposal(row) if row else None

    async def pending_create_named(self, agent_name: str, name: str) -> bool:
        """Is a create with this name (case-insensitive) waiting for approval?"""
        async with self.conn.execute(
            "SELECT 1 FROM agent_routine_proposals WHERE agent_name = ? AND status = 'pending' "
            "AND action = 'create' AND json_extract(payload, '$.name') = ? COLLATE NOCASE "
            "LIMIT 1",
            (agent_name, name),
        ) as cur:
            return (await cur.fetchone()) is not None

    async def insert_pending(
        self,
        row: dict[str, Any],
        *,
        caps_check: Callable[[list[Routine]], None] | None = None,
    ) -> tuple[RoutineProposal, bool]:
        """Hold a change for approval. One transaction, so two concurrent agent calls
        cannot both pass a limit. Returns ``(proposal, replaced)``."""
        from the_one.routines.repository import AgentRoutineRepository

        agent = row["agent_name"]
        action = row["action"]
        async with write_transaction(self.conn):
            if action == "create":
                name = str(row["payload"].get("name", ""))
                if await self.pending_create_named(agent, name):
                    raise RoutineLimitError(
                        "A routine with that name is already waiting for approval."
                    )
                async with self.conn.execute(
                    "SELECT 1 FROM agent_routines WHERE agent_name = ? AND name = ? COLLATE NOCASE",
                    (agent, name),
                ) as cur:
                    if await cur.fetchone():
                        raise RoutineNameTaken(name)
            replaced = False
            if row.get("routine_id") is not None:
                cur = await self.conn.execute(
                    "UPDATE agent_routine_proposals SET status = 'superseded', resolved_at = ? "
                    "WHERE agent_name = ? AND routine_id = ? AND status = 'pending'",
                    (_now_iso(), agent, row["routine_id"]),
                )
                replaced = cur.rowcount > 0
            if await self.pending_count(agent) >= AGENT_PENDING_PROPOSALS_MAX:
                raise RoutineLimitError(
                    f"You have {AGENT_PENDING_PROPOSALS_MAX} changes waiting for approval."
                )
            if caps_check is not None:
                caps_check(await AgentRoutineRepository(self.conn).list_for_agent(agent))
            proposal_id = await _insert(self.conn, row, "pending", _now_iso())
        got = await self.get(proposal_id)
        assert got is not None
        return got, replaced

    async def mark_dismissed(self, proposal_id: str) -> RoutineProposal:
        """Pending to dismissed. Idempotent on dismissed; ``ValueError`` on applied or
        superseded; ``KeyError`` when absent."""
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "UPDATE agent_routine_proposals SET status = 'dismissed', resolved_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (_now_iso(), proposal_id),
            )
            changed = cur.rowcount > 0
        got = await self.get(proposal_id)
        if got is None:
            raise KeyError(f"Proposal not found: {proposal_id}")
        if not changed and got.status != "dismissed":
            raise ProposalStateError(f"That change is {got.status}.")
        return got

    async def mark_superseded(self, proposal_id: str) -> RoutineProposal:
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agent_routine_proposals SET status = 'superseded', resolved_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (_now_iso(), proposal_id),
            )
        got = await self.get(proposal_id)
        if got is None:
            raise KeyError(f"Proposal not found: {proposal_id}")
        return got

    async def delete_resolved_older_than(self, agent_name: str, cutoff: str) -> int:
        """Delete the agent's resolved proposals (never pending) resolved before *cutoff*."""
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "DELETE FROM agent_routine_proposals WHERE agent_name = ? "
                "AND status != 'pending' AND resolved_at IS NOT NULL AND resolved_at < ?",
                (agent_name, cutoff),
            )
            return cur.rowcount

    async def delete_resolved_for_agent(self, agent_name: str) -> int:
        """Delete every resolved proposal of the agent (Purge now); pending ones stay."""
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "DELETE FROM agent_routine_proposals WHERE agent_name = ? AND status != 'pending'",
                (agent_name,),
            )
            return cur.rowcount

    async def supersede_pending(self, agent_name: str) -> int:
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "UPDATE agent_routine_proposals SET status = 'superseded', resolved_at = ? "
                "WHERE agent_name = ? AND status = 'pending'",
                (_now_iso(), agent_name),
            )
            return cur.rowcount

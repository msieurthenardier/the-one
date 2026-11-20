"""Async access to ``agent_routines`` and ``agent_routine_runs`` (Mission 33 F1, DD1).

Same shape as ``AgentRuleRepository``: every mutator opens ONE
``write_transaction`` (the guard is not re-entrant); every agent-facing query
is scoped by ``agent_name`` and a miss (or another agent's row) is ``KeyError``.

Every timestamp is written through :func:`_now_iso`, which calls
``time_zones.utcnow()`` through the module namespace so ``frozen_clock`` bites.
All timestamps are UTC ISO strings with the same ``+00:00`` suffix, so string
comparison orders them correctly (a zero-microsecond value sorts before a
fractional one in the same second).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from typing import Any, Literal, Protocol

import aiosqlite

from the_one import time_zones
from the_one.db._notes import SOURCES_CAP
from the_one.db._write_lock import write_transaction
from the_one.routines.limits import (
    RoutineNameTaken,
    check_routine_caps,
)
from the_one.routines.models import Routine, RoutineRun

REASON_STILL_RUNNING = "still_running"
MSG_STILL_RUNNING = "The previous run was still going."


class ProposalRunner(Protocol):
    """What a routine mutator needs of a proposal write: one awaitable that runs inside the
    mutator's transaction (``ProposalOp`` satisfies it; Mission 36 F2 L1 widened the
    ``proposal`` parameter so the agent proposal ops can too)."""

    async def run(self, conn: aiosqlite.Connection, routine_id: str | None) -> None: ...


Flag = tuple[Literal["merge"], list[str]] | Literal["clear"] | None


def _now_iso() -> str:
    return time_zones.utcnow().isoformat()


_COLS = (
    "id, agent_name, name, prompt, schedule, enabled, finished_at, next_run_at, "
    "anchor_at, created_by, created_at, updated_at, untrusted, untrusted_sources"
)
_INSERT_COLS = _COLS.removesuffix(", untrusted, untrusted_sources")

# Columns an update may set (``schedule`` is encoded; ``enabled`` is a bool).
_UPDATABLE = {
    "name",
    "prompt",
    "schedule",
    "enabled",
    "finished_at",
    "next_run_at",
    "anchor_at",
}


def _encode(column: str, value: Any) -> Any:
    if column == "schedule":
        return json.dumps(value, sort_keys=True)
    if column == "enabled":
        return 1 if value else 0
    return value


def _routine(row: Any) -> Routine:
    try:
        schedule = json.loads(row[4])
    except ValueError:
        schedule = {}
    return Routine(
        id=row[0],
        agent_name=row[1],
        name=row[2],
        prompt=row[3],
        schedule=schedule if isinstance(schedule, dict) else {},
        enabled=bool(row[5]),
        finished_at=row[6],
        next_run_at=row[7],
        anchor_at=row[8],
        created_by=row[9],
        created_at=row[10],
        updated_at=row[11],
        untrusted=bool(row[12]),
        untrusted_sources=_decode_sources(row[13]),
    )


def _decode_sources(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except ValueError:
        return []
    return [str(v) for v in val] if isinstance(val, list) else []


def _merge_sources(existing: list[str], new: list[str]) -> list[str]:
    out = list(existing)
    for src in new:
        if src not in out:
            out.append(src)
    return out[:SOURCES_CAP]


def _is_name_clash(exc: sqlite3.IntegrityError) -> bool:
    return "UNIQUE" in str(exc).upper()


class AgentRoutineRepository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list_for_agent(self, name: str) -> list[Routine]:
        async with self.conn.execute(
            f"SELECT {_COLS} FROM agent_routines WHERE agent_name = ? "
            "ORDER BY name COLLATE NOCASE, id",
            (name,),
        ) as cur:
            return [_routine(r) for r in await cur.fetchall()]

    async def get(self, name: str, routine_id: str) -> Routine | None:
        async with self.conn.execute(
            f"SELECT {_COLS} FROM agent_routines WHERE agent_name = ? AND id = ?",
            (name, routine_id),
        ) as cur:
            row = await cur.fetchone()
        return _routine(row) if row else None

    async def get_by_name(self, name: str, routine_name: str) -> Routine | None:
        """A routine of agent *name* by its (case-insensitive) routine name."""
        async with self.conn.execute(
            f"SELECT {_COLS} FROM agent_routines WHERE agent_name = ? AND name = ? COLLATE NOCASE",
            (name, routine_name),
        ) as cur:
            row = await cur.fetchone()
        return _routine(row) if row else None

    async def get_by_id(self, routine_id: str) -> Routine | None:
        """Unscoped read for the scheduler and runner (leg 3/4)."""
        async with self.conn.execute(
            f"SELECT {_COLS} FROM agent_routines WHERE id = ?", (routine_id,)
        ) as cur:
            row = await cur.fetchone()
        return _routine(row) if row else None

    async def _caps_after(
        self, name: str, after_fn: Callable[[list[Routine]], list[Routine]]
    ) -> None:
        before = await self.list_for_agent(name)
        check_routine_caps(before, after_fn(before))

    async def _flag_values(self, name: str, routine_id: str, flag: Flag) -> dict[str, Any]:
        """The ``untrusted`` columns a ``flag`` argument sets (read in the transaction)."""
        if flag is None:
            return {}
        if flag == "clear":
            return {"untrusted": 0, "untrusted_sources": None}
        got = await self.get(name, routine_id)
        merged = _merge_sources(got.untrusted_sources if got else [], list(flag[1]))
        return {"untrusted": 1, "untrusted_sources": json.dumps(merged)}

    async def create(
        self,
        name: str,
        fields: dict[str, Any],
        *,
        precheck: Callable[[Routine | None], None] | None = None,
        flag: Flag = None,
        proposal: ProposalRunner | None = None,
    ) -> Routine:
        """Insert a routine for agent *name*. *fields* holds ``name``, ``prompt``,
        ``schedule`` (dict) and optionally the other columns.

        Inside the one transaction, in order: ``precheck(None)``, the agent caps over the
        rows read here, the INSERT (with ``flag`` applied), then the ``proposal`` op."""
        routine_id = uuid.uuid4().hex
        now = _now_iso()
        values = {
            "enabled": True,
            "finished_at": None,
            "next_run_at": None,
            "anchor_at": None,
            "created_by": "operator",
            **fields,
        }
        try:
            async with write_transaction(self.conn):
                if precheck is not None:
                    precheck(None)
                cand = Routine(
                    id=routine_id,
                    agent_name=name,
                    created_at=now,
                    updated_at=now,
                    **{
                        k: values[k]
                        for k in (
                            "name",
                            "prompt",
                            "schedule",
                            "enabled",
                            "finished_at",
                            "next_run_at",
                        )
                    },
                )
                await self._caps_after(name, lambda before: [*before, cand])
                await self.conn.execute(
                    f"INSERT INTO agent_routines ({_INSERT_COLS}) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        routine_id,
                        name,
                        values["name"],
                        values["prompt"],
                        _encode("schedule", values["schedule"]),
                        _encode("enabled", values["enabled"]),
                        values["finished_at"],
                        values["next_run_at"],
                        values["anchor_at"],
                        values["created_by"],
                        now,
                        now,
                    ),
                )
                flag_cols = await self._flag_values(name, routine_id, flag)
                if flag_cols:
                    await self.conn.execute(
                        "UPDATE agent_routines SET untrusted = ?, untrusted_sources = ? "
                        "WHERE id = ?",
                        (flag_cols["untrusted"], flag_cols["untrusted_sources"], routine_id),
                    )
                if proposal is not None:
                    await proposal.run(self.conn, routine_id)
        except sqlite3.IntegrityError as e:
            if _is_name_clash(e):
                raise RoutineNameTaken(values["name"]) from e
            raise
        got = await self.get(name, routine_id)
        assert got is not None
        return got

    async def update(
        self,
        name: str,
        routine_id: str,
        fields: dict[str, Any],
        *,
        precheck: Callable[[Routine | None], None] | None = None,
        flag: Flag = None,
        proposal: ProposalRunner | None = None,
    ) -> Routine:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"Not updatable: {sorted(unknown)}")
        try:
            async with write_transaction(self.conn):
                cur_row = await self.get(name, routine_id)
                if cur_row is None:
                    raise KeyError(f"Routine not found: {routine_id}")
                if precheck is not None:
                    precheck(cur_row)
                changed = cur_row.model_copy(update=fields)
                await self._caps_after(
                    name,
                    lambda before: [changed if r.id == routine_id else r for r in before],
                )
                cols = dict(fields)
                cols.update(await self._flag_values(name, routine_id, flag))
                sets = [f"{c} = ?" for c in cols] + ["updated_at = ?"]
                params = [_encode(c, v) for c, v in cols.items()]
                params += [_now_iso(), name, routine_id]
                await self.conn.execute(
                    f"UPDATE agent_routines SET {', '.join(sets)} WHERE agent_name = ? AND id = ?",
                    params,
                )
                if proposal is not None:
                    await proposal.run(self.conn, routine_id)
        except sqlite3.IntegrityError as e:
            if _is_name_clash(e):
                raise RoutineNameTaken(str(fields.get("name", ""))) from e
            raise
        got = await self.get(name, routine_id)
        assert got is not None
        return got

    async def delete(
        self,
        name: str,
        routine_id: str,
        *,
        precheck: Callable[[Routine | None], None] | None = None,
        proposal: ProposalRunner | None = None,
    ) -> None:
        async with write_transaction(self.conn):
            cur_row = await self.get(name, routine_id)
            if cur_row is None:
                raise KeyError(f"Routine not found: {routine_id}")
            if precheck is not None:
                precheck(cur_row)
            # Pending proposals for a routine that is going away are superseded (DD4), except
            # the one this delete is resolving.
            await self.conn.execute(
                "UPDATE agent_routine_proposals SET status = 'superseded', resolved_at = ? "
                "WHERE routine_id = ? AND status = 'pending' AND id != ?",
                (_now_iso(), routine_id, getattr(proposal, "proposal_id", None) or ""),
            )
            await self.conn.execute(
                "DELETE FROM agent_routines WHERE agent_name = ? AND id = ?",
                (name, routine_id),
            )
            if proposal is not None:
                await proposal.run(self.conn, None)

    async def delete_done_older_than(self, name: str, cutoff: str) -> int:
        """Retention (DD4): delete the agent's Done routines finished before *cutoff*, after
        superseding their pending proposals; their runs cascade. A routine with a ``running``
        run is left for a later sweep."""
        where = (
            "agent_name = ? AND finished_at IS NOT NULL AND finished_at < ? "
            "AND NOT EXISTS (SELECT 1 FROM agent_routine_runs r "
            "WHERE r.routine_id = agent_routines.id AND r.outcome = 'running')"
        )
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agent_routine_proposals SET status = 'superseded', resolved_at = ? "
                "WHERE status = 'pending' AND routine_id IN "
                f"(SELECT id FROM agent_routines WHERE {where})",
                (_now_iso(), name, cutoff),
            )
            cur = await self.conn.execute(
                f"DELETE FROM agent_routines WHERE {where}", (name, cutoff)
            )
            return cur.rowcount

    async def list_due(self, now_iso: str) -> list[Routine]:
        """Enabled, unfinished routines whose ``next_run_at`` has arrived (leg 4)."""
        async with self.conn.execute(
            f"SELECT {_COLS} FROM agent_routines WHERE enabled = 1 AND finished_at IS NULL "
            "AND next_run_at IS NOT NULL AND next_run_at <= ? ORDER BY next_run_at, id",
            (now_iso,),
        ) as cur:
            return [_routine(r) for r in await cur.fetchall()]

    async def set_next_run(
        self,
        routine_id: str,
        next_run_at: str | None,
        *,
        finished_at: str | None = None,
    ) -> None:
        """Set ``next_run_at`` (and ``finished_at``) without touching ``updated_at``
        semantics of operator edits; a missing row is a no-op (legs 3 and 4)."""
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agent_routines SET next_run_at = ?, "
                "finished_at = COALESCE(?, finished_at) WHERE id = ?",
                (next_run_at, finished_at, routine_id),
            )

    async def advance_if_due(
        self, routine_id: str, due_iso: str, next_iso: str | None, finished_iso: str | None
    ) -> bool:
        """Compare-and-set advance (leg 5, DD5): applies only while the row still has
        ``next_run_at == due_iso`` and is enabled and unfinished. ``False`` means an
        edit, a disable or a delete got there first, and the edit wins."""
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "UPDATE agent_routines SET next_run_at = ?, "
                "finished_at = COALESCE(?, finished_at) "
                "WHERE id = ? AND next_run_at = ? AND enabled = 1 AND finished_at IS NULL",
                (next_iso, finished_iso, routine_id, due_iso),
            )
            return cur.rowcount > 0

    async def earliest_next_run(self) -> str | None:
        """The soonest ``next_run_at`` among enabled, unfinished routines."""
        async with self.conn.execute(
            "SELECT MIN(next_run_at) FROM agent_routines WHERE enabled = 1 "
            "AND finished_at IS NULL AND next_run_at IS NOT NULL"
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row and row[0] else None

    async def list_not_done(self) -> list[tuple[Routine, str]]:
        """Every routine that is not Done, on or off, across agents (a time-zone change,
        DD12), each with its raw stored ``schedule`` text for the compare-and-set."""
        async with self.conn.execute(
            f"SELECT {_COLS}, schedule FROM agent_routines WHERE finished_at IS NULL "
            "ORDER BY agent_name, id"
        ) as cur:
            return [(_routine(r), r[-1]) for r in await cur.fetchall()]

    async def follow_zone_change(
        self,
        routine_id: str,
        *,
        expect_schedule_text: str,
        expect_anchor_at: str | None,
        expect_next_run_at: str | None,
        schedule: dict[str, Any] | None = None,
        next_run_at: str | None = None,
        finished_at: str | None = None,
    ) -> bool:
        """Compare-and-set for a time-zone change (DD12): applies only while the row is
        still not Done and its raw ``schedule``, ``anchor_at`` and ``next_run_at`` are what
        the caller read, so an operator edit made mid-pass wins. Writes the rewritten
        ``schedule`` (when given), ``next_run_at`` and, for a series that ended, ``finished_at``;
        ``anchor_at`` never changes. In the same transaction, each pending proposal whose
        base schedule equals the routine's pre-rewrite schedule takes the rewritten one as
        its base, so a zone change never turns it into a stale 409."""
        new_text = _encode("schedule", schedule) if schedule is not None else expect_schedule_text
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "UPDATE agent_routines SET schedule = ?, next_run_at = ?, "
                "finished_at = COALESCE(?, finished_at) "
                "WHERE id = ? AND finished_at IS NULL AND schedule = ? "
                "AND anchor_at IS ? AND next_run_at IS ?",
                (
                    new_text,
                    next_run_at,
                    finished_at,
                    routine_id,
                    expect_schedule_text,
                    expect_anchor_at,
                    expect_next_run_at,
                ),
            )
            if cur.rowcount == 0:
                return False
            if schedule is None:
                return True
            try:
                old = json.loads(expect_schedule_text)
            except ValueError:
                return True
            async with self.conn.execute(
                "SELECT id, base FROM agent_routine_proposals "
                "WHERE routine_id = ? AND status = 'pending' AND base IS NOT NULL",
                (routine_id,),
            ) as pending:
                rows = await pending.fetchall()
            for pid, raw in rows:
                try:
                    base = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(base, dict) and base.get("schedule") == old:
                    base["schedule"] = schedule
                    await self.conn.execute(
                        "UPDATE agent_routine_proposals SET base = ? WHERE id = ?",
                        (json.dumps(base, sort_keys=True), pid),
                    )
            return True


class RoutineRunRepository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    _COLS = (
        "id, routine_id, trigger_kind, outcome, reason, due_at, started_at, finished_at, "
        "session_id, repeats, reason_code"
    )

    @staticmethod
    def _row(row: Any) -> RoutineRun:
        return RoutineRun(
            id=row[0],
            routine_id=row[1],
            trigger_kind=row[2],
            outcome=row[3],
            reason=row[4],
            due_at=row[5],
            started_at=row[6],
            finished_at=row[7],
            session_id=row[8],
            repeats=row[9],
            reason_code=row[10],
        )

    async def insert(self, run: RoutineRun) -> RoutineRun:
        run_id = run.id or uuid.uuid4().hex
        started = run.started_at or _now_iso()
        async with write_transaction(self.conn):
            await self.conn.execute(
                f"INSERT INTO agent_routine_runs ({self._COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    run.routine_id,
                    run.trigger_kind,
                    run.outcome,
                    run.reason,
                    run.due_at,
                    started,
                    run.finished_at,
                    run.session_id,
                    run.repeats,
                    run.reason_code,
                ),
            )
        return run.model_copy(update={"id": run_id, "started_at": started})

    async def finish(
        self,
        run_id: str,
        outcome: str,
        reason: str | None = None,
        session_id: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        """Close a run. A missing row (its routine was deleted mid-run) is a no-op."""
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agent_routine_runs SET outcome = ?, reason = ?, finished_at = ?, "
                "session_id = COALESCE(?, session_id), reason_code = ? WHERE id = ?",
                (
                    outcome,
                    reason,
                    _now_iso(),
                    session_id,
                    reason_code,
                    run_id,
                ),
            )

    async def record_still_running_skip(
        self, routine_id: str, trigger: str, due_iso: str, now_iso: str
    ) -> RoutineRun:
        """Record a "still running" skip, collapsing into the routine's newest run row when
        that row is itself a ``still_running`` skip (DD11). Read-then-update in one
        transaction; ``started_at`` and ``trigger_kind`` of the kept row never move."""
        async with write_transaction(self.conn):
            async with self.conn.execute(
                f"SELECT {self._COLS} FROM agent_routine_runs WHERE routine_id = ? "
                "ORDER BY started_at DESC, id DESC LIMIT 1",
                (routine_id,),
            ) as cur:
                row = await cur.fetchone()
            last = self._row(row) if row else None
            if (
                last is not None
                and last.outcome == "skipped"
                and last.reason_code == REASON_STILL_RUNNING
            ):
                n = last.repeats + 1
                reason = f"Skipped {n} times while the previous run was still going."
                await self.conn.execute(
                    "UPDATE agent_routine_runs SET repeats = ?, reason = ?, finished_at = ?, "
                    "due_at = ? WHERE id = ?",
                    (n, reason, now_iso, due_iso, last.id),
                )
                changes = {"repeats": n, "reason": reason}
                changes.update(finished_at=now_iso, due_at=due_iso)
                return last.model_copy(update=changes)
            run_id = uuid.uuid4().hex
            run = RoutineRun(
                id=run_id,
                routine_id=routine_id,
                trigger_kind=trigger,  # type: ignore[arg-type]
                outcome="skipped",
                reason=MSG_STILL_RUNNING,
                reason_code=REASON_STILL_RUNNING,
                due_at=due_iso,
                started_at=now_iso,
                finished_at=now_iso,
            )
            await self.conn.execute(
                f"INSERT INTO agent_routine_runs ({self._COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    routine_id,
                    trigger,
                    "skipped",
                    MSG_STILL_RUNNING,
                    due_iso,
                    now_iso,
                    now_iso,
                    None,
                    1,
                    REASON_STILL_RUNNING,
                ),
            )
            return run

    async def latest(self, routine_id: str) -> RoutineRun | None:
        async with self.conn.execute(
            f"SELECT {self._COLS} FROM agent_routine_runs WHERE routine_id = ? "
            "ORDER BY started_at DESC, id DESC LIMIT 1",
            (routine_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def list(
        self, routine_id: str, limit: int = 50, before: str | None = None
    ) -> list[RoutineRun]:
        sql = f"SELECT {self._COLS} FROM agent_routine_runs WHERE routine_id = ?"
        params: list[Any] = [routine_id]
        if before is not None:
            sql += " AND started_at < ?"
            params.append(before)
        sql += " ORDER BY started_at DESC, id DESC LIMIT ?"
        params.append(limit)
        async with self.conn.execute(sql, params) as cur:
            return [self._row(r) for r in await cur.fetchall()]

    async def mark_running_interrupted(self, reason: str) -> int:
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "UPDATE agent_routine_runs SET outcome = 'interrupted', reason = ?, "
                "finished_at = ? WHERE outcome = 'running'",
                (reason, _now_iso()),
            )
            return cur.rowcount

    async def delete_finished_older_than(self, agent_name: str, cutoff: str) -> int:
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "DELETE FROM agent_routine_runs WHERE outcome != 'running' "
                "AND finished_at IS NOT NULL AND finished_at < ? "
                "AND routine_id IN (SELECT id FROM agent_routines WHERE agent_name = ?)",
                (cutoff, agent_name),
            )
            return cur.rowcount

    async def delete_all_for_agent(self, agent_name: str) -> int:
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "DELETE FROM agent_routine_runs WHERE outcome != 'running' "
                "AND routine_id IN (SELECT id FROM agent_routines WHERE agent_name = ?)",
                (agent_name,),
            )
            return cur.rowcount

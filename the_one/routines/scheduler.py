"""The routine scheduler (Mission 33 F1 leg 5, DD4, DD5).

One lifespan-owned loop. Each wake: follow a time-zone change, then run one due
pass. A pass advances each due routine with a compare-and-set (an operator edit
made since ``list_due`` wins) and only then spawns its run, with no ``await``
between the two. A crash or a ``stop()`` cancel between the advance and the spawn
loses that one occurrence with no history row (accepted, DD5); routines not yet
advanced in that pass are recovered at the next boot.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from the_one import time_zones
from the_one.db.connection import get_connection
from the_one.db.repositories import AppMetadataRepository
from the_one.routines import recurrence, runner
from the_one.routines.limits import MISSED_COUNT_CAP
from the_one.routines.models import Routine, RoutineRun
from the_one.routines.repository import AgentRoutineRepository, RoutineRunRepository

logger = logging.getLogger(__name__)

ZONE_KEY = "routines_zone"
SLEEP_MIN = 1.0
SLEEP_MAX = 60.0
ON_TIME_SECONDS = 60.0
STOP_DRAIN_SECONDS = 5.0


def next_sleep(now: datetime, earliest: datetime | None) -> float:
    """Seconds to sleep: until *earliest*, clamped to [1, 60]; 60 with none.

    The 1-second floor keeps a due row that cannot be processed from becoming a
    hot loop."""
    if earliest is None:
        return SLEEP_MAX
    return max(SLEEP_MIN, min(SLEEP_MAX, (earliest - now).total_seconds()))


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _missed_reason(n: int) -> str:
    if n > MISSED_COUNT_CAP:
        return f"Missed more than {MISSED_COUNT_CAP} runs while the app was closed."
    if n == 1:
        return "Missed 1 run while the app was closed."
    return f"Missed {n} runs while the app was closed."


class RoutineScheduler:
    def __init__(
        self,
        clock: Callable[[], datetime],
        spawn: Callable[[str, Callable[[], Any]], Any] | None = None,
        conn_factory: Callable[[], Awaitable[Any]] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._clock = clock
        self._spawn = spawn or (lambda rid, factory: runner.registry.try_spawn(rid, factory))
        self._conn_factory = conn_factory or get_connection
        self._sleep = sleep or self._default_sleep
        self._event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._stopped = False

    # ── lifecycle ──

    def start(self) -> None:
        if self._task is None and not self._stopped:
            self._task = asyncio.create_task(self._loop(), name="routine-scheduler")

    def poke(self) -> None:
        """Wake the loop now (a routine write or a time-zone change)."""
        if not self._stopped:
            self._event.set()

    async def stop(self) -> None:
        self._stopped = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await runner.registry.drain(STOP_DRAIN_SECONDS)

    async def _default_sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._event.wait(), timeout=seconds)

    # ── loop ──

    async def _loop(self) -> None:
        try:
            await self.startup(self._clock())
        except Exception:  # noqa: BLE001
            logger.exception("routine scheduler startup failed")
        while not self._stopped:
            try:
                conn = await self._conn_factory()
                earliest = _parse(await AgentRoutineRepository(conn).earliest_next_run())
                delay = next_sleep(self._clock(), earliest)
            except Exception:  # noqa: BLE001
                logger.exception("routine scheduler could not read the next run")
                delay = SLEEP_MAX
            await self._sleep(delay)
            self._event.clear()
            if self._stopped:
                return
            try:
                await self._check_zone(self._clock())
            except Exception:  # noqa: BLE001
                logger.exception("routine scheduler zone check failed")
            try:
                await self.run_pass(self._clock())
            except Exception:  # noqa: BLE001
                logger.exception("routine scheduler pass failed")

    # ── startup ──

    async def startup(self, now: datetime) -> None:
        conn = await self._conn_factory()
        await RoutineRunRepository(conn).mark_running_interrupted(
            "The app stopped during this run."
        )
        await self.run_pass(now)
        await self._check_zone(now)

    async def _check_zone(self, now: datetime) -> None:
        conn = await self._conn_factory()
        zone = await time_zones.load_effective_zone(conn)
        if not zone.key:
            return
        meta = AppMetadataRepository(conn)
        stored = await meta.get(ZONE_KEY)
        if stored == zone.key:
            return
        if stored is not None:
            repo = AgentRoutineRepository(conn)
            for r, raw in await repo.list_not_done():
                try:
                    await self._follow_zone(repo, r, raw, now, zone.tzinfo)
                except Exception:  # noqa: BLE001
                    logger.exception("routine %s: could not follow the time-zone change", r.id)
        await meta.set(ZONE_KEY, zone.key)

    @staticmethod
    async def _follow_zone(
        repo: AgentRoutineRepository, r: Routine, raw: str, now: datetime, tz
    ) -> None:
        """DD12 for one routine that is not Done. An instant-anchored schedule (a one-off,
        minutes or hours) keeps its instant: only the display ``start`` is re-rendered. A
        wall-clock schedule keeps its wall time: an enabled routine's ``next_run_at`` is
        recomputed in the new zone (Done when nothing is left). A routine already due is
        left for the pass, which catches it up."""
        anchor = _parse(r.anchor_at)
        try:
            sched = recurrence.check(r.schedule, anchor)
        except (recurrence.RoutineScheduleError, KeyError, TypeError, ValueError):
            # A stored schedule that cannot be read (v48's upgrade_failed) has nothing to follow.
            logger.debug("routine %s: unreadable schedule, skipped on zone change", r.id)
            return
        if recurrence.is_anchored(sched):
            new = recurrence.rezone(sched, anchor, tz)
            if new != sched:
                await repo.follow_zone_change(
                    r.id,
                    expect_schedule_text=raw,
                    expect_anchor_at=r.anchor_at,
                    expect_next_run_at=r.next_run_at,
                    schedule=new,
                    next_run_at=r.next_run_at,
                )
            return
        if not r.enabled or not r.next_run_at:
            return
        due = _parse(r.next_run_at)
        if due is None or due <= now:
            return
        nxt = recurrence.next_occurrence(sched, anchor, now, tz)
        await repo.follow_zone_change(
            r.id,
            expect_schedule_text=raw,
            expect_anchor_at=r.anchor_at,
            expect_next_run_at=r.next_run_at,
            next_run_at=nxt.isoformat() if nxt else None,
            finished_at=None if nxt else now.isoformat(),
        )

    # ── the pass ──

    async def run_pass(self, now: datetime) -> None:
        if self._stopped:
            return
        conn = await self._conn_factory()
        repo = AgentRoutineRepository(conn)
        runs = RoutineRunRepository(conn)
        zone = (await time_zones.load_effective_zone(conn)).tzinfo
        for r in await repo.list_due(now.isoformat()):
            if self._stopped:
                return
            try:
                await self._handle(r, now, zone, repo, runs)
            except Exception:  # noqa: BLE001
                logger.exception("routine %s: scheduler pass failed for this routine", r.id)

    async def _handle(self, r: Routine, now: datetime, zone, repo, runs) -> None:
        due_iso = r.next_run_at
        due = _parse(due_iso)
        anchor = _parse(r.anchor_at)
        if due is None or due_iso is None:
            logger.warning(
                "routine decision=unreadable_due routine=%s agent=%r due=%r",
                r.id,
                r.agent_name,
                due_iso,
            )
            return
        g = recurrence.grace(r.schedule, anchor, due, zone)
        late = now - due
        runs_now = late <= g
        trigger = "schedule"
        if runs_now and late >= timedelta(seconds=ON_TIME_SECONDS):
            trigger = "catch_up"
        # The series' end: no next occurrence finishes the routine (a one-off after its
        # run, or the last occurrence of an ended series).
        nxt = recurrence.next_occurrence(r.schedule, anchor, now, zone)
        finished = now.isoformat() if nxt is None else None
        if not await repo.advance_if_due(r.id, due_iso, nxt.isoformat() if nxt else None, finished):
            # edited, disabled or deleted since list_due: the edit wins
            logger.info(
                "routine decision=skip_changed routine=%s agent=%r due=%s late_s=%.1f",
                r.id,
                r.agent_name,
                due_iso,
                late.total_seconds(),
            )
            return
        nxt_text = nxt.isoformat() if nxt else "none"
        if not runs_now:
            if r.schedule["repeat"] is None:
                reason = "The scheduled time passed while the app was closed."
            else:
                n = max(
                    1,
                    recurrence.occurrences_between(
                        r.schedule,
                        anchor,
                        due - timedelta(microseconds=1),
                        now,
                        zone,
                        cap=MISSED_COUNT_CAP + 1,
                    ),
                )
                reason = _missed_reason(n)
            row = await self._record(runs, r.id, "schedule", "missed", reason, due_iso, now)
            logger.info(
                "routine decision=missed run=%s routine=%s agent=%r due=%s late_s=%.1f "
                "next=%s finished=%s reason=%r",
                row.id,
                r.id,
                r.agent_name,
                due_iso,
                late.total_seconds(),
                nxt_text,
                finished is not None,
                reason,
            )
            return
        rid = r.id
        task = self._spawn(rid, lambda: runner.run_routine(rid, trigger, due_iso))
        if task is None:
            await runs.record_still_running_skip(rid, trigger, due_iso, now.isoformat())
            decision = "still_running_skip"
        else:
            decision = "spawn"
        logger.info(
            "routine decision=%s routine=%s agent=%r trigger=%s due=%s late_s=%.1f "
            "next=%s finished=%s",
            decision,
            rid,
            r.agent_name,
            trigger,
            due_iso,
            late.total_seconds(),
            nxt_text,
            finished is not None,
        )

    @staticmethod
    async def _record(runs, rid, trigger, outcome, reason, due_iso, now) -> RoutineRun:
        return await runs.insert(
            RoutineRun(
                routine_id=rid,
                trigger_kind=trigger,
                outcome=outcome,
                reason=reason,
                due_at=due_iso,
                started_at=now.isoformat(),
                finished_at=now.isoformat(),
            )
        )


_scheduler: RoutineScheduler | None = None


def get_scheduler() -> RoutineScheduler | None:
    return _scheduler


def set_scheduler(s: RoutineScheduler | None) -> None:
    global _scheduler
    _scheduler = s

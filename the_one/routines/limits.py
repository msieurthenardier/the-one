"""Routine limits and error types (Mission 33 F1, DD2/DD4/DD9). A stdlib-only leaf."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from the_one.routines.models import Routine

ROUTINE_PROMPT_MAX_CHARS = 4000
ROUTINES_PER_AGENT_MAX = 50
INTERVAL_HOURS_MIN = 1
INTERVAL_HOURS_MAX = 168
ONCE_MAX_AHEAD_DAYS = 365
RUNS_PAGE_DEFAULT = 50
RUNS_PAGE_MAX = 200
REPEATING_GRACE_CAP = timedelta(hours=2)
ONCE_GRACE = timedelta(hours=24)
MISSED_COUNT_CAP = 1000

# Agent-written routines (Mission 33 F2, DD8). Raise-only: a change is refused only when it
# RAISES a capped measure over its cap, so an operator's larger set can always be edited down.
AGENT_ACTIVE_ROUTINES_MAX = 10
AGENT_RUNS_PER_DAY_MAX = 48
AGENT_ONCE_MIN_AHEAD_MINUTES = 1
AGENT_PENDING_PROPOSALS_MAX = 20
AGENT_PROPOSALS_KEPT = 500
AGENT_ROUTINE_WRITES_PER_TURN = 5

MSG_PAST = "That time has already passed."
MSG_TOO_FAR = "That time is more than a year away."


class RoutineScheduleError(ValueError):
    """A schedule is malformed or out of range (HTTP 422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class RoutineLimitError(ValueError):
    """A routine field or count exceeds a limit (HTTP 422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class RoutineNameTaken(ValueError):  # noqa: N818
    """Another routine of the same agent already has this name (HTTP 409)."""

    def __init__(self, name: str) -> None:
        super().__init__(f"A routine named {name!r} already exists for this agent.")
        self.detail = f"A routine named {name!r} already exists for this agent."


class RoutineFieldError(ValueError):
    """A routine request field is invalid; ``field`` names it (HTTP 422 on ``loc [field]``)."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def runs_per_day(schedule: dict[str, Any], *, now: datetime, next_run_at: str | None) -> int:
    """The conservative maximum number of runs in one day for one routine."""
    kind = schedule.get("kind")
    if kind in ("daily", "weekdays", "weekly"):
        return 1
    if kind == "interval":
        hours = schedule.get("hours")
        if isinstance(hours, int) and not isinstance(hours, bool) and hours >= 1:
            return math.ceil(24 / hours)
        return 0
    if kind == "once":
        raw = next_run_at or schedule.get("at")
        try:
            at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return 0
        if at.tzinfo is None:
            return 0
        return 1 if at <= now + timedelta(hours=24) else 0
    return 0


def _measures(routines: Sequence["Routine"], now: datetime) -> tuple[int, int]:
    active = [r for r in routines if r.enabled and r.finished_at is None]
    runs = sum(runs_per_day(r.schedule, now=now, next_run_at=r.next_run_at) for r in active)
    return len(active), runs


def check_agent_caps(
    before: Sequence["Routine"], after: Sequence["Routine"], now: datetime
) -> None:
    """Raise :class:`RoutineLimitError` when a measure rose and is now over its cap."""
    active_before, runs_before = _measures(before, now)
    active_after, runs_after = _measures(after, now)
    if active_after > active_before and active_after > AGENT_ACTIVE_ROUTINES_MAX:
        raise RoutineLimitError(
            f"You already have {active_before} active routines, the most allowed "
            f"({AGENT_ACTIVE_ROUTINES_MAX}). Cancel or turn one off first."
        )
    if runs_after > runs_before and runs_after > AGENT_RUNS_PER_DAY_MAX:
        raise RoutineLimitError(
            f"That would make your routines run more than {AGENT_RUNS_PER_DAY_MAX} times a day."
        )

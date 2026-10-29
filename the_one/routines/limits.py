"""Routine limits and error types (Mission 33 F1, DD2/DD4/DD9). A stdlib-only leaf."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from the_one.routines.models import Routine

ROUTINE_PROMPT_MAX_CHARS = 4000
# Per-agent counts (Mission 33 F3, DD3). Both are raise-only for every write, operator or agent.
ROUTINES_ACTIVE_MAX = 50  # enabled and not Done
ROUTINES_OPEN_MAX = 200  # not Done, on or off
INTERVAL_HOURS_MIN = 1
INTERVAL_HOURS_MAX = 168
ONCE_MAX_AHEAD_DAYS = 365
RUNS_PAGE_DEFAULT = 50
RUNS_PAGE_MAX = 200
REPEATING_GRACE_CAP = timedelta(hours=2)
ONCE_GRACE = timedelta(hours=24)
MISSED_COUNT_CAP = 1000

# Agent-written routines (Mission 33 F2, DD8).
AGENT_ONCE_MIN_AHEAD_MINUTES = 1
AGENT_PENDING_PROPOSALS_MAX = 20
AGENT_ROUTINE_WRITES_PER_TURN = 5

MSG_ACTIVE_CAP = (
    f"This agent already has {ROUTINES_ACTIVE_MAX} active routines, the most allowed. "
    "Turn one off or delete one first."
)
MSG_OPEN_CAP = (
    f"This agent already has {ROUTINES_OPEN_MAX} routines that are not done, the most allowed. "
    "Delete some first."
)
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


def _counts(routines: Sequence["Routine"]) -> tuple[int, int]:
    open_ = [r for r in routines if r.finished_at is None]
    return sum(1 for r in open_ if r.enabled), len(open_)


def check_routine_caps(before: Sequence["Routine"], after: Sequence["Routine"]) -> None:
    """Raise :class:`RoutineLimitError` when a count rose and is now over its cap.

    Raise-only, so an agent already over a cap can always be edited down."""
    active_before, open_before = _counts(before)
    active_after, open_after = _counts(after)
    if active_after > active_before and active_after > ROUTINES_ACTIVE_MAX:
        raise RoutineLimitError(MSG_ACTIVE_CAP)
    if open_after > open_before and open_after > ROUTINES_OPEN_MAX:
        raise RoutineLimitError(MSG_OPEN_CAP)

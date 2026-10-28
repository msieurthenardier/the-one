"""Routine limits and error types (Mission 33 F1, DD2/DD4/DD9). A stdlib-only leaf."""

from __future__ import annotations

from datetime import timedelta

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

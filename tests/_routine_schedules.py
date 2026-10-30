"""Canonical ``{start, repeat, ends}`` schedule bodies for routine tests.

One place builds the shapes a request carries, so no test spells the older kind-based
input (it is refused). A repeating series may start on a past date: only the first
instant of a one-off is limited, so a fixed start date works under any clock.
"""

from __future__ import annotations

from typing import Any

START_DATE = "2026-01-05"
NEVER = {"kind": "never"}


def _start(time: str, date: str = START_DATE) -> dict[str, str]:
    return {"date": date, "time": time}


def daily(time: str, date: str = START_DATE) -> dict[str, Any]:
    return {
        "start": _start(time, date),
        "repeat": {"every": 1, "unit": "day"},
        "ends": dict(NEVER),
    }


def weekdays(time: str, date: str = START_DATE) -> dict[str, Any]:
    return weekly([0, 1, 2, 3, 4], time, date)


def weekly(days: list[int], time: str, date: str = START_DATE) -> dict[str, Any]:
    return {
        "start": _start(time, date),
        "repeat": {"every": 1, "unit": "week", "days": list(days)},
        "ends": dict(NEVER),
    }


def every_hours(n: int) -> dict[str, Any]:
    """Repeat every *n* hours, the first run *n* hours from now."""
    return {
        "start": {"in": {"amount": n, "unit": "hours"}},
        "repeat": {"every": n, "unit": "hour"},
        "ends": dict(NEVER),
    }


def once_in(amount: int, unit: str) -> dict[str, Any]:
    """A one-off *amount* *unit* from now (the unit is plural: ``hours``, ``days``)."""
    return {"start": {"in": {"amount": amount, "unit": unit}}}


def once_at(date: str, time: str) -> dict[str, Any]:
    """A one-off at a local date and time."""
    return {"start": _start(time, date)}

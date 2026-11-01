"""Wall-time helpers for routine schedules (Mission 33 F1, DD3). No I/O, no clock.

Since Flight 3 the schedule calculator is ``recurrence.py``; this module keeps what it
builds on: ``parse_utc``, ``_parse_hhmm`` and ``resolve_wall_time``.

DST (DD3): a wall time that does not exist (spring-forward gap) runs once at
the END of the gap. ``zoneinfo`` alone would resolve LA 02:30 to 03:30 PDT by
applying the pre-gap offset; we detect the gap by a round trip through UTC and
walk whole minutes to the first instant carrying the post-gap offset. A wall
time that occurs twice (fall-back) runs once, on its first occurrence
(``fold=0``).

This module never reads the clock.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

from the_one.routines.limits import RoutineScheduleError

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_UTC = timezone.utc


def parse_utc(value: Any) -> datetime:
    """Parse a UTC ISO string to an aware UTC datetime; raise on anything else."""
    if not isinstance(value, str):
        raise RoutineScheduleError("A one-time schedule needs a UTC time to run at.")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00") if value.endswith("Z") else value)
    except ValueError:
        raise RoutineScheduleError("That time could not be read.")
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise RoutineScheduleError("A one-time schedule must be given in UTC.")
    return dt.astimezone(_UTC)


def _parse_hhmm(value: Any) -> tuple[int, int]:
    if not isinstance(value, str):
        raise RoutineScheduleError("The time of day must be written HH:MM, like 09:30.")
    m = _TIME_RE.match(value)
    if not m:
        raise RoutineScheduleError("The time of day must be written HH:MM, like 09:30.")
    return int(m.group(1)), int(m.group(2))


def resolve_wall_time(day: date, hour: int, minute: int, zone: tzinfo) -> datetime:
    """The UTC instant for a local wall time, with the DD3 DST rules."""
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)  # fold=0
    as_utc = dt.astimezone(_UTC)
    back = as_utc.astimezone(zone)
    if (back.hour, back.minute) == (hour, minute) and back.date() == day:
        return as_utc  # exists; fold=0 is the first occurrence of a repeated time
    # A gap. lo: new offset (earlier instant); hi: old offset (later instant).
    lo = dt.replace(fold=1).astimezone(_UTC)
    hi = as_utc
    if lo > hi:
        lo, hi = hi, lo
    target_offset = hi.astimezone(zone).utcoffset()
    cur = lo.replace(second=0, microsecond=0)
    if cur < lo:
        cur += timedelta(minutes=1)
    while cur <= hi:
        if cur.astimezone(zone).utcoffset() == target_offset:
            return cur
        cur += timedelta(minutes=1)
    return hi

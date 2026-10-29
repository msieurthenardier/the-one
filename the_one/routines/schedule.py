"""Pure routine-schedule calculator (Mission 33 F1, DD2-DD4). No I/O, no clock.

Schedules are plain dicts: ``once`` (``at``, UTC ISO), ``daily`` / ``weekdays``
(``time``, ``HH:MM``), ``weekly`` (``days`` 0=Monday.., ``time``), ``interval``
(``hours``). Wall-clock kinds are evaluated in the zone passed in; ``interval``
is absolute elapsed time from an anchor.

DST (DD3): a wall time that does not exist (spring-forward gap) runs once at
the END of the gap. ``zoneinfo`` alone would resolve LA 02:30 to 03:30 PDT by
applying the pre-gap offset; we detect the gap by a round trip through UTC and
walk whole minutes to the first instant carrying the post-gap offset. A wall
time that occurs twice (fall-back) runs once, on its first occurrence
(``fold=0``).

This module never reads the clock: callers pass ``after`` (they use
``time_zones.utcnow()``).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

from the_one.routines.limits import (
    INTERVAL_HOURS_MAX,
    INTERVAL_HOURS_MIN,
    MISSED_COUNT_CAP,
    ONCE_GRACE,
    REPEATING_GRACE_CAP,
    RoutineScheduleError,
)

KINDS = ("once", "daily", "weekdays", "weekly", "interval")
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


def validate(schedule: Any) -> dict[str, Any]:
    """Return the normalized schedule dict, or raise :class:`RoutineScheduleError`."""
    if not isinstance(schedule, dict):
        raise RoutineScheduleError("The schedule must be an object.")
    kind = schedule.get("kind")
    if kind not in KINDS:
        raise RoutineScheduleError(
            "The schedule must be one of: once, daily, weekdays, weekly, interval."
        )
    allowed = {
        "once": {"kind", "at"},
        "daily": {"kind", "time"},
        "weekdays": {"kind", "time"},
        "weekly": {"kind", "days", "time"},
        "interval": {"kind", "hours"},
    }[kind]
    extra = set(schedule) - allowed
    if extra:
        raise RoutineScheduleError(f"A {kind} schedule does not take {sorted(extra)[0]!r}.")
    if kind == "once":
        return {"kind": "once", "at": parse_utc(schedule.get("at")).isoformat()}
    if kind == "interval":
        hours = schedule.get("hours")
        if isinstance(hours, bool) or not isinstance(hours, int):
            raise RoutineScheduleError("Hours must be a whole number.")
        if not INTERVAL_HOURS_MIN <= hours <= INTERVAL_HOURS_MAX:
            raise RoutineScheduleError(
                f"Hours must be between {INTERVAL_HOURS_MIN} and {INTERVAL_HOURS_MAX}."
            )
        return {"kind": "interval", "hours": hours}
    h, m = _parse_hhmm(schedule.get("time"))
    out: dict[str, Any] = {"kind": kind, "time": f"{h:02d}:{m:02d}"}
    if kind == "weekly":
        days = schedule.get("days")
        if (
            not isinstance(days, list)
            or not days
            or any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in days)
        ):
            raise RoutineScheduleError(
                "Pick at least one day of the week (0 is Monday, 6 is Sunday)."
            )
        out["days"] = sorted(set(days))
    return out


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


def _matches_day(schedule: dict[str, Any], day: date) -> bool:
    kind = schedule["kind"]
    if kind == "daily":
        return True
    if kind == "weekdays":
        return day.weekday() < 5
    return day.weekday() in schedule["days"]


def next_run(
    schedule: dict[str, Any],
    *,
    after: datetime,
    zone: tzinfo,
    anchor: datetime | None = None,
) -> datetime | None:
    """The first occurrence strictly after *after*, as an aware UTC datetime.

    ``once`` gives its ``at`` if still ahead, else ``None``. ``interval`` is
    ``anchor + k*hours`` with ``k = floor((after - anchor)/h) + 1`` and
    ``k >= 1``: with ``after < anchor`` that gives ``anchor + h``, not the
    anchor itself (the anchor is "now" at creation).
    """
    schedule = validate(schedule)
    after = after.astimezone(_UTC)
    kind = schedule["kind"]
    if kind == "once":
        at = parse_utc(schedule["at"])
        return at if at > after else None
    if kind == "interval":
        if anchor is None:
            raise RoutineScheduleError("An interval schedule needs an anchor time.")
        step = timedelta(hours=schedule["hours"])
        k = max(1, int((after - anchor.astimezone(_UTC)) // step) + 1)
        return anchor.astimezone(_UTC) + k * step
    h, m = _parse_hhmm(schedule["time"])
    start = after.astimezone(zone).date() - timedelta(days=1)
    for offset in range(0, 10):
        day = start + timedelta(days=offset)
        if not _matches_day(schedule, day):
            continue
        cand = resolve_wall_time(day, h, m, zone)
        if cand > after:
            return cand
    return None  # unreachable for validated schedules


def grace(
    schedule: dict[str, Any],
    due: datetime,
    zone: tzinfo,
    anchor: datetime | None = None,
) -> timedelta:
    """How late a due run may still run (DD4): 24 h for a one-off, else
    min(half the gap to the next occurrence, 2 h)."""
    if schedule.get("kind") == "once":
        return ONCE_GRACE
    nxt = next_run(schedule, after=due, zone=zone, anchor=anchor)
    if nxt is None:
        return ONCE_GRACE
    return min((nxt - due) / 2, REPEATING_GRACE_CAP)


def occurrences_between(
    schedule: dict[str, Any],
    start: datetime,
    end: datetime,
    zone: tzinfo,
    anchor: datetime | None = None,
    cap: int = MISSED_COUNT_CAP + 1,
) -> int:
    """How many occurrences fall in ``(start, end]``, stopping at *cap*."""
    count = 0
    cur = start
    while count < cap:
        nxt = next_run(schedule, after=cur, zone=zone, anchor=anchor)
        if nxt is None or nxt > end:
            break
        count += 1
        cur = nxt
    return count

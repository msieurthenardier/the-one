"""Calendar recurrence for routines (Mission 33 F3 leg 3, DD1/DD2/DD5/DD12). Pure.

The one stored schedule shape::

    {"start": {"date", "time"},
     "repeat": None | {"every", "unit", "days"?, "month_by"?},
     "ends": {"kind": "never"} | {"kind": "on", "date"} | {"kind": "after", "count"}}

Two kinds of start. **Instant-anchored** schedules (a one-off, and the ``minute`` and ``hour``
units) carry an exact UTC ``anchor``; ``start`` is only its wall-clock rendering in the zone and
every calculation is elapsed time from the anchor. **Wall-clock** schedules (``day``, ``week``,
``month``, ``year``) use ``start`` directly and have no anchor; occurrences fall at
``start.time`` in the zone through :func:`schedule.resolve_wall_time` (a spring-forward gap runs
once at the end of the gap, a repeated time once on its first occurrence).

Nothing here reads the clock or the database: callers pass ``now`` / ``after`` / ``zone``.
``schedule.py`` keeps only the wall-time helpers this module needs (``resolve_wall_time``,
``parse_utc``, ``_parse_hhmm``).
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

from the_one.routines import schedule as wall
from the_one.routines.limits import (
    MISSED_COUNT_CAP,
    ONCE_GRACE,
    REPEATING_GRACE_CAP,
    RoutineScheduleError,
)

_UTC = timezone.utc
UNITS = ("minute", "hour", "day", "week", "month", "year")
EVERY_MAX = {"minute": 1439, "hour": 168, "day": 365, "week": 52, "month": 12, "year": 10}
ENDS_COUNT_MAX = 1000
START_MAX_AHEAD_DAYS = 365
NTH_VALUES = (1, 2, 3, 4, -1)
#: The search is bounded: this many consecutive nonexistent dates (a skipped month or a
#: non-leap February 29) end a wall-clock search with no further occurrence. February 29 is
#: at most 7 candidates away for a yearly rule (2096 to 2104).
MAX_CONSECUTIVE_SKIPS = 12
_YEAR_MAX = 9999

MSG_ONCE_TOO_SOON = "A one-time routine must be at least a minute away."
MSG_TOO_FAR = "That time is more than a year away."
MSG_NO_END_FOR_ONCE = "A routine that does not repeat has no end to set."
MSG_NO_RUNS_LEFT = "This schedule has no runs left."
MSG_KIND_SHAPE = (
    "A schedule is {start, repeat, ends}; the older kind-based shape is no longer accepted."
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REL_UNITS = {"minutes": "minutes", "hours": "hours", "days": "days"}


def _err(text: str) -> RoutineScheduleError:
    return RoutineScheduleError(text)


# ── shape ─────────────────────────────────────────────────────────────────


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_date(value: Any, what: str = "date") -> date:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise _err(f"The {what} must be written YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _err("That date doesn't exist.")


def _check_keys(obj: dict[str, Any], allowed: set[str], what: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise _err(f"A {what} does not take {sorted(extra)[0]!r}.")


def _parse_repeat(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _err("The repeat must be an object, or null for a routine that does not repeat.")
    _check_keys(raw, {"every", "unit", "days", "month_by"}, "repeat")
    unit = raw.get("unit")
    if unit not in UNITS:
        raise _err("The repeat unit must be one of: minute, hour, day, week, month, year.")
    every = raw.get("every")
    if not _int(every):
        raise _err("Repeat every must be a whole number.")
    if not 1 <= every <= EVERY_MAX[unit]:
        raise _err(f"Repeat every must be between 1 and {EVERY_MAX[unit]} for a {unit} unit.")
    out: dict[str, Any] = {"every": every, "unit": unit}
    if "days" in raw and raw["days"] is not None and unit != "week":
        raise _err("Days of the week only go with a weekly repeat.")
    if "month_by" in raw and raw["month_by"] is not None and unit != "month":
        raise _err("A day-of-month rule only goes with a monthly repeat.")
    if unit == "week":
        days = raw.get("days")
        if (
            not isinstance(days, list)
            or not days
            or any(not _int(d) or not 0 <= d <= 6 for d in days)
        ):
            raise _err("Pick at least one day of the week (0 is Monday, 6 is Sunday).")
        out["days"] = sorted(set(days))
    if unit == "month":
        mb = raw.get("month_by")
        if mb is None:
            mb = {"by": "day"}
        if not isinstance(mb, dict):
            raise _err("The monthly rule must be an object.")
        if mb.get("by") == "day":
            _check_keys(mb, {"by"}, "monthly day rule")
            out["month_by"] = {"by": "day"}
        elif mb.get("by") == "weekday":
            _check_keys(mb, {"by", "nth"}, "monthly weekday rule")
            nth = mb.get("nth")
            if not _int(nth) or nth not in NTH_VALUES:
                raise _err("Which weekday of the month must be 1, 2, 3, 4 or -1 (the last).")
            out["month_by"] = {"by": "weekday", "nth": nth}
        else:
            raise _err("The monthly rule must be by day or by weekday.")
    return out


def _parse_ends(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"kind": "never"}
    if not isinstance(raw, dict):
        raise _err("The end must be an object.")
    kind = raw.get("kind")
    if kind == "never":
        _check_keys(raw, {"kind"}, "never-ending schedule")
        return {"kind": "never"}
    if kind == "on":
        _check_keys(raw, {"kind", "date"}, "schedule that ends on a date")
        return {"kind": "on", "date": _parse_date(raw.get("date"), "end date").isoformat()}
    if kind == "after":
        _check_keys(raw, {"kind", "count"}, "schedule that ends after a count")
        count = raw.get("count")
        if not _int(count) or not 1 <= count <= ENDS_COUNT_MAX:
            raise _err(f"The number of runs must be a whole number from 1 to {ENDS_COUNT_MAX}.")
        return {"kind": "after", "count": count}
    raise _err("The end must be never, on a date, or after a number of runs.")


def _hhmm(value: Any) -> tuple[int, int]:
    try:
        return wall._parse_hhmm(value)
    except RoutineScheduleError as e:
        raise _err(e.detail)


def is_anchored(schedule: dict[str, Any]) -> bool:
    """True when the schedule is instant-anchored (a one-off, minute or hour unit)."""
    repeat = schedule["repeat"]
    return repeat is None or repeat["unit"] in ("minute", "hour")


def _shape(raw: Any) -> dict[str, Any]:
    """Validate a fully specified canonical schedule (``start`` as date/time) and return the
    normalized dict. ``repeat`` and ``ends`` may be absent."""
    if not isinstance(raw, dict):
        raise _err("The schedule must be an object.")
    _check_keys(raw, {"start", "repeat", "ends"}, "schedule")
    start = raw.get("start")
    if not isinstance(start, dict) or set(start) != {"date", "time"}:
        raise _err("The schedule needs a start with a date and a time.")
    d = _parse_date(start.get("date"))
    h, m = _hhmm(start.get("time"))
    repeat = _parse_repeat(raw.get("repeat"))
    ends = _parse_ends(raw.get("ends"))
    if repeat is None and ends["kind"] != "never":
        raise _err(MSG_NO_END_FOR_ONCE)
    if ends["kind"] == "on" and date.fromisoformat(ends["date"]) < d:
        raise _err("The end date can't be before the start date.")
    return {
        "start": {"date": d.isoformat(), "time": f"{h:02d}:{m:02d}"},
        "repeat": repeat,
        "ends": ends,
    }


def check(schedule: Any, anchor: datetime | None) -> dict[str, Any]:
    """Validate a stored (canonical) schedule and its anchor; return the normalized dict."""
    sched = _shape(schedule)
    if is_anchored(sched):
        if anchor is None:
            raise _err("This schedule needs an exact start time.")
    elif anchor is not None:
        raise _err("A calendar schedule has no exact start time.")
    return sched


# ── zone helpers (DD12) ───────────────────────────────────────────────────


def render_start(instant: datetime, zone: tzinfo) -> dict[str, str]:
    """An instant's wall-clock rendering in *zone* as a ``start`` dict (minute precision)."""
    local = instant.astimezone(zone)
    return {"date": local.date().isoformat(), "time": f"{local.hour:02d}:{local.minute:02d}"}


def rezone(schedule: dict[str, Any], anchor: datetime | None, zone: tzinfo) -> dict[str, Any]:
    """The schedule with ``start`` re-rendered in *zone* when it is instant-anchored (a zone
    change is a display rewrite); a wall-clock schedule is returned unchanged."""
    if anchor is None or not is_anchored(schedule):
        return schedule
    return {**schedule, "start": render_start(anchor, zone)}


# ── the normalizer (DD5) ──────────────────────────────────────────────────


def ceil_minute(dt: datetime) -> datetime:
    """Round up to the next whole minute (unchanged when already whole)."""
    if dt.second or dt.microsecond:
        return dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return dt


def _relative(spec: Any, now: datetime) -> datetime:
    if (
        not isinstance(spec, dict)
        or set(spec) != {"amount", "unit"}
        or not _int(spec.get("amount"))
        or spec["amount"] < 1
        or spec.get("unit") not in _REL_UNITS
    ):
        raise _err("Give a whole number of minutes, hours or days, at least 1.")
    try:
        return ceil_minute(now + timedelta(**{spec["unit"]: spec["amount"]}))
    except OverflowError:
        raise _err(MSG_TOO_FAR)


def _wall_instant(day: date, h: int, m: int, zone: tzinfo) -> datetime:
    try:
        return wall.resolve_wall_time(day, h, m, zone)
    except (ValueError, OverflowError):
        raise _err("That date doesn't exist.")


def _build(
    *,
    repeat: dict[str, Any] | None,
    ends: dict[str, Any],
    instant: datetime | None,
    start: dict[str, str] | None,
    zone: tzinfo,
    now: datetime,
    min_ahead: timedelta | None,
) -> tuple[dict[str, Any], datetime | None]:
    """Assemble and finally validate a schedule from a resolved start (an *instant*, or a
    wall-clock *start* for day/week/month/year)."""
    probe = {"repeat": repeat}
    anchored = is_anchored(probe)  # type: ignore[arg-type]
    if instant is None:
        assert start is not None
        h, m = _hhmm(start["time"])
        instant = _wall_instant(_parse_date(start["date"]), h, m, zone)
    if anchored:
        anchor: datetime | None = instant
        start = render_start(instant, zone)
    else:
        anchor = None
        if start is None:
            start = render_start(instant, zone)
    if instant > now + timedelta(days=START_MAX_AHEAD_DAYS):
        raise _err(MSG_TOO_FAR)
    if repeat is None and min_ahead is not None and instant - now < min_ahead:
        raise _err(MSG_ONCE_TOO_SOON)
    sched = _shape({"start": start, "repeat": repeat, "ends": ends})
    return sched, anchor


def normalize(
    raw: Any,
    *,
    zone: tzinfo,
    now: datetime,
    min_ahead: timedelta | None = None,
) -> tuple[dict[str, Any], datetime | None]:
    """Normalize an input to ``(canonical schedule, anchor or None)``.

    Accepts only the canonical shape (``repeat``/``ends`` optional; ``start`` either
    ``{date, time}`` or the relative ``{"in": {amount, unit}}``). *min_ahead* (agent writes)
    is the least lead for a one-off's first run, checked after rounding. Raises
    :class:`RoutineScheduleError` with one plain sentence.
    """
    now = now.astimezone(_UTC)
    if not isinstance(raw, dict):
        raise _err("The schedule must be an object.")
    if "kind" in raw:
        raise _err(MSG_KIND_SHAPE)
    _check_keys(raw, {"start", "repeat", "ends"}, "schedule")
    start = raw.get("start")
    repeat = _parse_repeat(raw.get("repeat"))
    ends = _parse_ends(raw.get("ends"))
    if repeat is None and ends["kind"] != "never":
        raise _err(MSG_NO_END_FOR_ONCE)
    if isinstance(start, dict) and "in" in start:
        if set(start) != {"in"}:
            raise _err("A relative start is {in: {amount, unit}} and nothing else.")
        instant = _relative(start["in"], now)
        return _build(
            repeat=repeat,
            ends=ends,
            instant=instant,
            start=None,
            zone=zone,
            now=now,
            min_ahead=min_ahead,
        )
    if not isinstance(start, dict) or set(start) != {"date", "time"}:
        raise _err("The schedule needs a start with a date and a time.")
    day = _parse_date(start.get("date"))
    h, m = _hhmm(start.get("time"))
    clean_start = {"date": day.isoformat(), "time": f"{h:02d}:{m:02d}"}
    return _build(
        repeat=repeat,
        ends=ends,
        instant=None,
        start=clean_start,
        zone=zone,
        now=now,
        min_ahead=min_ahead,
    )


# ── occurrences (DD2) ─────────────────────────────────────────────────────

_STEP_UNITS = {"minute": "minutes", "hour": "hours"}


def _sunday_offset(weekday: int) -> int:
    """Days from the Sunday that opens the week to *weekday* (0 Monday .. 6 Sunday)."""
    return (weekday + 1) % 7


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date | None:
    if nth == -1:
        last = date(year, month, calendar.monthrange(year, month)[1])
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first = date(year, month, 1)
    day = 1 + (weekday - first.weekday()) % 7 + 7 * (nth - 1)
    if day > calendar.monthrange(year, month)[1]:
        return None
    return date(year, month, day)


def _candidates(sched: dict[str, Any], j0: int) -> Iterator[date | None]:
    """Ascending nominal dates of a wall-clock rule from period *j0*; ``None`` marks a slot
    that does not exist (a month without that day, a non-leap February 29)."""
    repeat = sched["repeat"]
    unit, every = repeat["unit"], repeat["every"]
    start = date.fromisoformat(sched["start"]["date"])
    j = j0
    try:
        if unit == "day":
            while True:
                yield start + timedelta(days=j * every)
                j += 1
        elif unit == "week":
            sunday0 = start - timedelta(days=_sunday_offset(start.weekday()))
            offsets = sorted(_sunday_offset(d) for d in repeat["days"])
            while True:
                base = sunday0 + timedelta(days=7 * every * j)
                for off in offsets:
                    yield base + timedelta(days=off)
                j += 1
        elif unit == "month":
            month_by = repeat["month_by"]
            while True:
                year, mo0 = divmod(start.year * 12 + start.month - 1 + j * every, 12)
                if year > _YEAR_MAX:
                    return
                if month_by["by"] == "day":
                    ok = start.day <= calendar.monthrange(year, mo0 + 1)[1]
                    yield date(year, mo0 + 1, start.day) if ok else None
                else:
                    yield _nth_weekday(year, mo0 + 1, start.weekday(), month_by["nth"])
                j += 1
        else:  # year
            while True:
                year = start.year + j * every
                if year > _YEAR_MAX:
                    return
                try:
                    yield date(year, start.month, start.day)
                except ValueError:
                    yield None
                j += 1
    except OverflowError:
        return


def _first_period(sched: dict[str, Any], after_date: date) -> int:
    """A safe (one period early) first period index to scan for occurrences after a date."""
    repeat = sched["repeat"]
    unit, every = repeat["unit"], repeat["every"]
    start = date.fromisoformat(sched["start"]["date"])
    if unit == "day":
        span = (after_date - start).days
        step = every
    elif unit == "week":
        sunday0 = start - timedelta(days=_sunday_offset(start.weekday()))
        span = (after_date - sunday0).days // 7
        step = every
    elif unit == "month":
        span = (after_date.year * 12 + after_date.month) - (start.year * 12 + start.month)
        step = every
    else:
        span = after_date.year - start.year
        step = every
    return max(0, span // step - 1)


def occurrences(
    schedule: dict[str, Any],
    anchor: datetime | None,
    zone: tzinfo,
    after: datetime | None = None,
) -> Iterator[datetime]:
    """Occurrences strictly after *after* (all of them when None), ascending, as aware UTC
    datetimes, honouring ``ends``. The wall-clock search is bounded (``MAX_CONSECUTIVE_SKIPS``
    nonexistent dates in a row, year 9999); an unending instant-anchored series is infinite,
    so callers stop consuming."""
    repeat, ends = schedule["repeat"], schedule["ends"]
    after = after.astimezone(_UTC) if after is not None else None
    end_date = date.fromisoformat(ends["date"]) if ends["kind"] == "on" else None
    limit = ends["count"] if ends["kind"] == "after" else None
    if is_anchored(schedule):
        if anchor is None:
            raise _err("This schedule needs an exact start time.")
        anchor = anchor.astimezone(_UTC)
        if repeat is None:
            if after is None or anchor > after:
                yield anchor
            return
        step = timedelta(**{_STEP_UNITS[repeat["unit"]]: repeat["every"]})
        k = 0 if after is None or after < anchor else int((after - anchor) // step) + 1
        try:
            while limit is None or k < limit:
                inst = anchor + k * step
                if end_date is not None and inst.astimezone(zone).date() > end_date:
                    return
                yield inst
                k += 1
        except OverflowError:
            return
        return
    h, m = _hhmm(schedule["start"]["time"])
    start_inst = _wall_instant(date.fromisoformat(schedule["start"]["date"]), h, m, zone)
    j0 = 0
    if after is not None and limit is None:
        j0 = _first_period(schedule, after.astimezone(zone).date())
    counted = skips = 0
    for cand in _candidates(schedule, j0):
        if cand is None:
            skips += 1
            if skips > MAX_CONSECUTIVE_SKIPS:
                return
            continue
        skips = 0
        if end_date is not None and cand > end_date:
            return
        try:
            inst = wall.resolve_wall_time(cand, h, m, zone)
        except (ValueError, OverflowError):
            return
        if inst < start_inst:
            continue
        counted += 1
        if limit is not None and counted > limit:
            return
        if after is not None and inst <= after:
            continue
        yield inst


def next_occurrence(
    schedule: dict[str, Any], anchor: datetime | None, after: datetime, zone: tzinfo
) -> datetime | None:
    """The first occurrence strictly after *after*, or None (ended, or past the bound)."""
    return next(occurrences(schedule, anchor, zone, after), None)


def has_future(
    schedule: dict[str, Any], anchor: datetime | None, after: datetime, zone: tzinfo
) -> bool:
    """Whether any occurrence follows *after* (a save without one is "no runs left")."""
    return next_occurrence(schedule, anchor, after, zone) is not None


def occurrences_between(
    schedule: dict[str, Any],
    anchor: datetime | None,
    start: datetime,
    end: datetime,
    zone: tzinfo,
    cap: int = MISSED_COUNT_CAP + 1,
) -> int:
    """How many occurrences fall in ``(start, end]``, stopping at *cap*."""
    end = end.astimezone(_UTC)
    count = 0
    for inst in occurrences(schedule, anchor, zone, start):
        if inst > end or count >= cap:
            break
        count += 1
    return count


def last_occurrence(
    schedule: dict[str, Any], anchor: datetime | None, zone: tzinfo
) -> datetime | None:
    """The final occurrence, or None when the series never ends (or has none)."""
    ends = schedule["ends"]
    if ends["kind"] == "never":
        return None
    if ends["kind"] == "after":
        last = None
        for inst in occurrences(schedule, anchor, zone):
            last = inst
        return last
    end_date = date.fromisoformat(ends["date"])
    if is_anchored(schedule):
        if schedule["repeat"] is None or anchor is None:
            return (
                anchor
                if anchor is not None and anchor.astimezone(zone).date() <= end_date
                else None
            )
        repeat = schedule["repeat"]
        step = timedelta(**{_STEP_UNITS[repeat["unit"]]: repeat["every"]})
        anchor = anchor.astimezone(_UTC)
        if anchor.astimezone(zone).date() > end_date:
            return None
        # First instant on the day after the end date, exclusive; then settle exactly.
        cutoff = _wall_instant(end_date + timedelta(days=1), 0, 0, zone)
        k = max(0, int((cutoff - anchor) // step))
        while k > 0 and (anchor + k * step).astimezone(zone).date() > end_date:
            k -= 1
        while (anchor + (k + 1) * step).astimezone(zone).date() <= end_date:
            k += 1
        return anchor + k * step
    # Wall-clock: scan a window ending at the end date; fall back to the whole series.
    window_start = datetime.combine(end_date - timedelta(days=3300), datetime.min.time())
    after = window_start.replace(tzinfo=zone).astimezone(_UTC)
    last = None
    for inst in occurrences(schedule, anchor, zone, after):
        last = inst
    if last is None:
        for inst in occurrences(schedule, anchor, zone):
            last = inst
    return last


def grace(
    schedule: dict[str, Any], anchor: datetime | None, due: datetime, zone: tzinfo
) -> timedelta:
    """How late a due run may still run: 24 h for a one-off or a series' last occurrence,
    otherwise min(half the gap to the next occurrence, 2 h)."""
    if schedule["repeat"] is None:
        return ONCE_GRACE
    nxt = next_occurrence(schedule, anchor, due, zone)
    if nxt is None:
        return ONCE_GRACE
    return min((nxt - due) / 2, REPEATING_GRACE_CAP)

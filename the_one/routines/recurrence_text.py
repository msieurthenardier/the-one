"""Plain-words sentences and warnings for the calendar recurrence (M33 F3 leg 3, DD7).

One wording for the form's preview and the agent tools' results. Sentence case, 12-hour clock
text through the ``the_one.time_zones`` formatters. These strings reach agent tool results, so
they never include a chat title or channel name.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo
from typing import Any

from the_one import time_zones
from the_one.routines import recurrence

_ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}


def _abbr_weekday(index: int) -> str:
    return time_zones._WEEKDAYS[index][:3]


def _abbr_month(index: int) -> str:
    return time_zones._MONTHS[index - 1][:3]


def _clock_text(hhmm: str) -> str:
    h, m = (int(p) for p in hhmm.split(":"))
    return time_zones._clock(datetime(2000, 1, 1, h, m))


def _full_date(day: date) -> str:
    return f"{_abbr_month(day.month)} {day.day}, {day.year}"


def _units(every: int, unit: str) -> str:
    return unit if every == 1 else f"{every} {unit}s"


def describe(schedule: dict[str, Any], anchor: datetime | None, zone: tzinfo) -> str:
    """The schedule as one sentence, e.g. "Every week on Tue, Thu at 9:00 AM, 13 times"."""
    repeat, ends = schedule["repeat"], schedule["ends"]
    start = schedule["start"]
    if recurrence.is_anchored(schedule) and anchor is not None:
        local = anchor.astimezone(zone)
        start = recurrence.render_start(anchor, zone)
        start_day = local.date()
        clock = time_zones._clock(local)
    else:
        start_day = date.fromisoformat(start["date"])
        clock = _clock_text(start["time"])
    if repeat is None:
        return f"Once, on {_abbr_weekday(start_day.weekday())}, {_full_date(start_day)} at {clock}"
    every, unit = repeat["every"], repeat["unit"]
    if unit in ("minute", "hour"):
        what = "minute" if every == 1 and unit == "minute" else _units(every, unit)
        body = f"Every {what} from {_abbr_month(start_day.month)} {start_day.day} at {clock}"
    elif unit == "day":
        body = f"Every {'day' if every == 1 else _units(every, 'day')} at {clock}"
    elif unit == "week":
        if every == 1 and repeat["days"] == [0, 1, 2, 3, 4]:
            body = f"Every weekday at {clock}"
        else:
            names = ", ".join(_abbr_weekday(d) for d in repeat["days"])
            body = f"Every {_units(every, 'week')} on {names} at {clock}"
    elif unit == "month":
        month_by = repeat["month_by"]
        if month_by["by"] == "day":
            where = f"day {start_day.day}"
        else:
            weekday = time_zones._WEEKDAYS[start_day.weekday()]
            where = f"the {_ORDINALS[month_by['nth']]} {weekday}"
        body = f"Every {_units(every, 'month')} on {where} at {clock}"
    else:
        month = time_zones._MONTHS[start_day.month - 1]
        body = f"Every {_units(every, 'year')} on {month} {start_day.day} at {clock}"
    if ends["kind"] == "on":
        body += f", until {_full_date(date.fromisoformat(ends['date']))}"
    elif ends["kind"] == "after":
        count = ends["count"]
        body += f", {count} time{'' if count == 1 else 's'}"
    return body


def warnings(schedule: dict[str, Any]) -> list[str]:
    """Plain warnings the form and tools show beside a valid schedule."""
    repeat = schedule["repeat"]
    if repeat is None:
        return []
    start = date.fromisoformat(schedule["start"]["date"])
    out: list[str] = []
    if repeat["unit"] == "month" and repeat["month_by"]["by"] == "day" and start.day > 28:
        out.append(f"Some months have fewer than {start.day} days. Those months are skipped.")
    if repeat["unit"] == "year" and (start.month, start.day) == (2, 29):
        out.append("February 29 only comes in leap years. Other years are skipped.")
    return out

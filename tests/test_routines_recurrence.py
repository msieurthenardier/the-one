"""The calendar recurrence calculator and normalizer (M33 F3 leg 3, DD1/DD2/DD5/DD12).

"Now" is passed explicitly (the module reads no clock); expected instants are built with
``zoneinfo`` in each case so the tables read as specifications.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from the_one.routines import recurrence as rec
from the_one.routines.limits import RoutineScheduleError

UTC = timezone.utc
LA = ZoneInfo("America/Los_Angeles")
LONDON = ZoneInfo("Europe/London")
NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=UTC)  # 15:45:12 PDT


def u(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def la(*a) -> datetime:
    """A Los Angeles wall time as a UTC instant (unambiguous cases only)."""
    return datetime(*a, tzinfo=LA).astimezone(UTC)


def make(date_, time_="09:00", repeat=None, ends=None, *, now=NOW, zone=LA, **kw):
    raw: dict = {"start": {"date": date_, "time": time_}}
    if repeat is not None:
        raw["repeat"] = repeat
    if ends is not None:
        raw["ends"] = ends
    return rec.normalize(raw, zone=zone, now=now, **kw)


def run(sched, anchor, n, zone=LA, after=None):
    out = []
    for inst in rec.occurrences(sched, anchor, zone, after):
        out.append(inst)
        if len(out) >= n:
            break
    return out


# ── AC1: validation and normal form ───────────────────────────────────────

BAD = [
    ({"start": {"date": "2026-10-29"}}, "start with a date and a time"),
    ({"start": {"date": "2026-13-01", "time": "09:00"}}, "doesn't exist"),
    ({"start": {"date": "10/29/2026", "time": "09:00"}}, "YYYY-MM-DD"),
    ({"start": {"date": "2026-10-29", "time": "9am"}}, "HH:MM"),
    ({"start": {"date": "2026-10-29", "time": "09:00"}, "extra": 1}, "does not take"),
    ({"start": {"date": "2026-10-29", "time": "09:00"}, "repeat": 5}, "must be an object"),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "fortnight"},
        },
        "unit",
    ),
    (
        {"start": {"date": "2026-10-29", "time": "09:00"}, "repeat": {"every": 0, "unit": "day"}},
        "between 1 and 365",
    ),
    (
        {"start": {"date": "2026-10-29", "time": "09:00"}, "repeat": {"every": 366, "unit": "day"}},
        "between 1 and 365",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1440, "unit": "minute"},
        },
        "between 1 and 1439",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 169, "unit": "hour"},
        },
        "between 1 and 168",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 53, "unit": "week", "days": [1]},
        },
        "between 1 and 52",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 13, "unit": "month"},
        },
        "between 1 and 12",
    ),
    (
        {"start": {"date": "2026-10-29", "time": "09:00"}, "repeat": {"every": 11, "unit": "year"}},
        "between 1 and 10",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": True, "unit": "day"},
        },
        "whole number",
    ),
    (
        {"start": {"date": "2026-10-29", "time": "09:00"}, "repeat": {"every": 1, "unit": "week"}},
        "at least one day",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "week", "days": []},
        },
        "at least one day",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "week", "days": [7]},
        },
        "at least one day",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "day", "days": [1]},
        },
        "only go with a weekly",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "day", "month_by": {"by": "day"}},
        },
        "only goes with a monthly",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": 5}},
        },
        "1, 2, 3, 4 or -1",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "month", "month_by": {"by": "year"}},
        },
        "by day or by weekday",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "ends": {"kind": "on", "date": "2026-11-01"},
        },
        "no end to set",
    ),
    (
        {"start": {"date": "2026-10-29", "time": "09:00"}, "ends": {"kind": "after", "count": 3}},
        "no end to set",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "day"},
            "ends": {"kind": "after", "count": 0},
        },
        "from 1 to 1000",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "day"},
            "ends": {"kind": "after", "count": 1001},
        },
        "from 1 to 1000",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "day"},
            "ends": {"kind": "on", "date": "2026-10-28"},
        },
        "before the start date",
    ),
    (
        {
            "start": {"date": "2026-10-29", "time": "09:00"},
            "repeat": {"every": 1, "unit": "day"},
            "ends": {"kind": "sometime"},
        },
        "never, on a date",
    ),
    (
        {"start": {"date": "2028-01-01", "time": "09:00"}, "repeat": {"every": 1, "unit": "day"}},
        "more than a year",
    ),
    ({"start": {"in": {"amount": 0, "unit": "hours"}}}, "at least 1"),
    ({"start": {"in": {"amount": 2, "unit": "weeks"}}}, "at least 1"),
    ({"start": {"in": {"amount": 2, "unit": "hours"}, "date": "2026-10-29"}}, "relative start"),
    ("daily", "must be an object"),
]


@pytest.mark.parametrize(("raw", "needle"), BAD)
def test_bad_shapes_are_refused_with_a_sentence(raw, needle) -> None:
    with pytest.raises(RoutineScheduleError) as ei:
        rec.normalize(raw, zone=LA, now=NOW)
    assert needle in ei.value.detail


@pytest.mark.parametrize(
    ("unit", "every"),
    [("minute", 1439), ("hour", 168), ("day", 365), ("week", 52), ("month", 12), ("year", 10)],
)
def test_range_maxima_are_accepted(unit, every) -> None:
    repeat = {"every": every, "unit": unit}
    if unit == "week":
        repeat["days"] = [0]
    sched, _ = make("2026-10-29", repeat=repeat, ends={"kind": "after", "count": 1000})
    assert sched["repeat"]["every"] == every
    assert sched["ends"] == {"kind": "after", "count": 1000}


def test_normal_form_is_canonical() -> None:
    a, _ = make("2026-10-29", repeat={"every": 1, "unit": "week", "days": [3, 1, 3]})
    b, _ = make(
        "2026-10-29", repeat={"every": 1, "unit": "week", "days": [1, 3]}, ends={"kind": "never"}
    )
    assert a == b
    assert a["repeat"] == {"every": 1, "unit": "week", "days": [1, 3]}
    c, _ = make("2026-10-29", repeat={"every": 1, "unit": "month"})
    d, _ = make("2026-10-29", repeat={"every": 1, "unit": "month", "month_by": {"by": "day"}})
    assert c == d and c["repeat"]["month_by"] == {"by": "day"}
    one, anchor = make("2026-10-29", "15:00")
    assert one["repeat"] is None and one["ends"] == {"kind": "never"}
    assert set(one) == {"start", "repeat", "ends"}
    assert anchor == la(2026, 10, 29, 15)


def test_anchor_kinds() -> None:
    assert make("2026-10-29")[1] is not None  # one-off
    assert make("2026-10-29", repeat={"every": 5, "unit": "minute"})[1] is not None
    assert make("2026-10-29", repeat={"every": 2, "unit": "hour"})[1] is not None
    for unit in ("day", "month", "year"):
        assert make("2026-10-29", repeat={"every": 1, "unit": unit})[1] is None
    assert make("2026-10-29", repeat={"every": 1, "unit": "week", "days": [3]})[1] is None


def test_check_validates_stored_schedule_and_anchor() -> None:
    sched, anchor = make("2026-10-29", "15:00")
    assert rec.check(sched, anchor) == sched
    with pytest.raises(RoutineScheduleError):
        rec.check(sched, None)
    day, _ = make("2026-10-29", repeat={"every": 1, "unit": "day"})
    with pytest.raises(RoutineScheduleError):
        rec.check(day, anchor)


# ── AC2: the normalizer ───────────────────────────────────────────────────


def first(sched, anchor, now, zone=LA):
    return rec.next_occurrence(sched, anchor, now, zone)


# The first run of each legacy calendar shape, from four "now" values (captured from the
# retired five-kind calculator in leg 4): the DD5 aliases keep today's first run.
_LEGACY_NOWS = [NOW, u(2027, 3, 13, 12, 0, 0), u(2027, 3, 14, 9, 59, 30), u(2026, 10, 31, 20, 0, 5)]
_LEGACY_FIRST_RUNS = [
    (
        {"kind": "daily", "time": "02:30"},
        ["2026-10-11T09:30", "2027-03-14T10:00", "2027-03-14T10:00", "2026-11-01T10:30"],
    ),
    (
        {"kind": "daily", "time": "09:00"},
        ["2026-10-11T16:00", "2027-03-13T17:00", "2027-03-14T16:00", "2026-11-01T17:00"],
    ),
    (
        {"kind": "weekdays", "time": "02:30"},
        ["2026-10-12T09:30", "2027-03-15T09:30", "2027-03-15T09:30", "2026-11-02T10:30"],
    ),
    (
        {"kind": "weekdays", "time": "17:15"},
        ["2026-10-13T00:15", "2027-03-16T00:15", "2027-03-16T00:15", "2026-11-03T01:15"],
    ),
    (
        {"kind": "weekly", "days": [6, 0], "time": "02:30"},
        ["2026-10-11T09:30", "2027-03-14T10:00", "2027-03-14T10:00", "2026-11-01T10:30"],
    ),
    (
        {"kind": "weekly", "days": [2], "time": "08:00"},
        ["2026-10-14T15:00", "2027-03-17T15:00", "2027-03-17T15:00", "2026-11-04T16:00"],
    ),
]


@pytest.mark.parametrize(("raw", "expected"), _LEGACY_FIRST_RUNS)
def test_legacy_calendar_kinds_keep_their_first_run(raw, expected) -> None:
    for now, want in zip(_LEGACY_NOWS, expected, strict=True):
        sched, anchor = rec.normalize(raw, zone=LA, now=now)
        assert anchor is None
        assert sched["start"]["time"] == raw["time"]
        assert first(sched, anchor, now) == datetime.fromisoformat(want).replace(tzinfo=UTC)


def test_daily_0230_across_spring_forward_keeps_typed_time() -> None:
    now = u(2027, 3, 13, 12, 0, 0)
    sched, _ = rec.normalize({"kind": "daily", "time": "02:30"}, zone=LA, now=now)
    assert sched["start"] == {"date": "2027-03-14", "time": "02:30"}
    assert sched["repeat"] == {"every": 1, "unit": "day"}
    assert first(sched, None, now) == u(2027, 3, 14, 10, 0)  # end of the gap, 03:00 PDT
    assert first(sched, None, u(2027, 3, 14, 10, 0)) == u(2027, 3, 15, 9, 30)


def test_legacy_weekdays_and_weekly_shapes() -> None:
    wd, _ = rec.normalize({"kind": "weekdays", "time": "09:00"}, zone=LA, now=NOW)
    assert wd["repeat"] == {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]}
    wk, _ = rec.normalize({"kind": "weekly", "days": [4, 0], "time": "09:00"}, zone=LA, now=NOW)
    assert wk["repeat"] == {"every": 1, "unit": "week", "days": [0, 4]}
    # Saturday Oct 10 now -> the next weekday run is Monday Oct 12.
    assert wd["start"]["date"] == "2026-10-12"


def test_legacy_interval_anchors_at_now_plus_n_hours_exactly() -> None:
    now = u(2026, 10, 10, 22, 45, 12, 345678)
    raw = {"kind": "interval", "hours": 3}
    sched, anchor = rec.normalize(raw, zone=LA, now=now)
    assert anchor == now + timedelta(hours=3)
    assert sched["repeat"] == {"every": 3, "unit": "hour"}
    assert first(sched, anchor, now) == u(2026, 10, 11, 1, 45, 12, 345678)
    assert first(sched, anchor, anchor) == anchor + timedelta(hours=3)


def test_legacy_once_shapes() -> None:
    at, a1 = rec.normalize({"kind": "once", "at": "2026-12-01T10:00:30Z"}, zone=LA, now=NOW)
    assert a1 == u(2026, 12, 1, 10, 1)  # rounded up to the minute
    assert at["repeat"] is None and at["start"] == {"date": "2026-12-01", "time": "02:01"}
    whole, a2 = rec.normalize({"kind": "once", "at": "2026-12-01T10:00:00+00:00"}, zone=LA, now=NOW)
    assert a2 == u(2026, 12, 1, 10, 0)
    on, a3 = rec.normalize(
        {"kind": "once", "on": {"date": "2026-12-01", "time": "09:15"}}, zone=LA, now=NOW
    )
    assert a3 == la(2026, 12, 1, 9, 15) and on["start"]["time"] == "09:15"
    rel, a4 = rec.normalize(
        {"kind": "once", "in": {"amount": 2, "unit": "hours"}}, zone=LA, now=NOW
    )
    assert a4 == u(2026, 10, 11, 0, 46)  # 00:45:12 rounded up


def test_legacy_errors_pass_through() -> None:
    for raw in (
        {"kind": "monthly"},
        {"kind": "once"},
        {"kind": "once", "at": "x"},
        {"kind": "interval", "hours": 0},
        {"kind": "once", "on": {"date": "2026-02-30", "time": "09:00"}},
    ):
        with pytest.raises(RoutineScheduleError):
            rec.normalize(raw, zone=LA, now=NOW)


def test_relative_start_rounds_up_to_the_next_whole_minute() -> None:
    _, a = rec.normalize({"start": {"in": {"amount": 90, "unit": "minutes"}}}, zone=LA, now=NOW)
    assert a == u(2026, 10, 11, 0, 16)  # 22:45:12 + 90 min = 00:15:12 -> 00:16
    exact = u(2026, 10, 10, 22, 45, 0)
    _, a = rec.normalize({"start": {"in": {"amount": 1, "unit": "days"}}}, zone=LA, now=exact)
    assert a == u(2026, 10, 11, 22, 45)  # already whole: unchanged
    sched, anchor = rec.normalize(
        {"start": {"in": {"amount": 2, "unit": "hours"}}, "repeat": {"every": 1, "unit": "day"}},
        zone=LA,
        now=NOW,
    )
    assert anchor is None and sched["start"] == {"date": "2026-10-10", "time": "17:46"}


def test_minimum_lead_applies_to_a_one_off_after_rounding() -> None:
    lead = timedelta(minutes=1)
    with pytest.raises(RoutineScheduleError) as ei:
        rec.normalize(
            {"kind": "once", "at": "2026-10-10T22:45:42Z"}, zone=LA, now=NOW, min_ahead=lead
        )
    assert ei.value.detail == "A one-time routine must be at least a minute away."
    with pytest.raises(RoutineScheduleError):
        rec.normalize(
            {"start": {"in": {"amount": 0, "unit": "minutes"}}}, zone=LA, now=NOW, min_ahead=lead
        )
    ok, anchor = rec.normalize(
        {"start": {"in": {"amount": 1, "unit": "minutes"}}}, zone=LA, now=NOW, min_ahead=lead
    )
    assert anchor - NOW >= lead
    # Not applied to a series, and not without min_ahead.
    rec.normalize(
        {"start": {"date": "2026-10-10", "time": "15:46"}, "repeat": {"every": 1, "unit": "day"}},
        zone=LA, now=NOW, min_ahead=lead,
    )  # fmt: skip
    rec.normalize({"kind": "once", "at": "2026-10-10T22:45:42Z"}, zone=LA, now=NOW)


# ── AC3: the occurrence table ─────────────────────────────────────────────


def test_minute_and_hour_units() -> None:
    s, a = make("2026-10-29", "15:00", {"every": 90, "unit": "minute"})
    assert a == la(2026, 10, 29, 15)
    assert run(s, a, 3) == [a, a + timedelta(minutes=90), a + timedelta(minutes=180)]
    assert first(s, a, a) == a + timedelta(minutes=90)
    assert first(s, a, a - timedelta(days=1)) == a  # before the anchor: the anchor
    assert first(s, a, a + timedelta(minutes=89, seconds=59)) == a + timedelta(minutes=90)
    one, a1 = make("2026-10-29", "15:00", {"every": 1, "unit": "minute"})
    assert first(one, a1, a1) == a1 + timedelta(minutes=1)
    h, ah = make("2026-10-29", "15:00", {"every": 2, "unit": "hour"})
    assert first(h, ah, ah + timedelta(hours=5)) == ah + timedelta(hours=6)
    h1, a_h1 = make("2026-10-29", "15:00", {"every": 1, "unit": "hour"})
    assert first(h1, a_h1, a_h1) == a_h1 + timedelta(hours=1)


def test_day_unit() -> None:
    s, _ = make("2026-10-29", "09:00", {"every": 1, "unit": "day"})
    assert run(s, None, 2) == [la(2026, 10, 29, 9), la(2026, 10, 30, 9)]
    s3, _ = make("2026-10-29", "09:00", {"every": 3, "unit": "day"})
    assert run(s3, None, 3) == [la(2026, 10, 29, 9), la(2026, 11, 1, 9), la(2026, 11, 4, 9)]
    assert first(s3, None, la(2026, 11, 1, 9)) == la(2026, 11, 4, 9)
    assert first(s3, None, u(2027, 6, 1)) is not None


def test_start_in_the_past_runs_next_after_now() -> None:
    s, _ = make("2026-10-01", "09:00", {"every": 1, "unit": "day"})
    assert first(s, None, NOW) == la(2026, 10, 11, 9)


def test_week_unit_sunday_first_across_a_year_boundary() -> None:
    # Monday Dec 28 2026; weeks run Sunday..Saturday; Sunday (6) of week one precedes it.
    s, _ = make(
        "2026-12-28", "09:00", {"every": 2, "unit": "week", "days": [0, 6]}, now=u(2026, 12, 1)
    )
    assert run(s, None, 4) == [
        la(2026, 12, 28, 9),
        la(2027, 1, 10, 9),
        la(2027, 1, 11, 9),
        la(2027, 1, 24, 9),
    ]
    assert first(s, None, la(2027, 1, 11, 9)) == la(2027, 1, 24, 9)


def test_week_several_days_every_week() -> None:
    s, _ = make("2026-10-29", "09:00", {"every": 1, "unit": "week", "days": [1, 3]})
    assert run(s, None, 4) == [
        la(2026, 10, 29, 9),
        la(2026, 11, 3, 9),
        la(2026, 11, 5, 9),
        la(2026, 11, 10, 9),
    ]


def test_nonmatching_start_begins_at_the_first_matching_occurrence() -> None:
    # Wednesday Oct 28, Mondays only: the Monday of the start's week (Oct 26) is before the start.
    s, _ = make("2026-10-28", "09:00", {"every": 1, "unit": "week", "days": [0]})
    assert run(s, None, 2) == [la(2026, 11, 2, 9), la(2026, 11, 9, 9)]
    s2, _ = make("2026-10-28", "09:00", {"every": 2, "unit": "week", "days": [0]})
    assert run(s2, None, 2) == [la(2026, 11, 9, 9), la(2026, 11, 23, 9)]


def test_month_by_day_skips_short_months() -> None:
    s, _ = make("2026-10-31", "09:00", {"every": 1, "unit": "month"})
    assert run(s, None, 4) == [
        la(2026, 10, 31, 9),
        la(2026, 12, 31, 9),
        la(2027, 1, 31, 9),
        la(2027, 3, 31, 9),
    ]
    s3, _ = make("2026-10-31", "09:00", {"every": 3, "unit": "month"})
    assert run(s3, None, 3) == [la(2026, 10, 31, 9), la(2027, 1, 31, 9), la(2027, 7, 31, 9)]


def test_month_by_weekday_nth_and_last() -> None:
    third = {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": 3}}
    s, _ = make("2026-10-20", "09:00", third)  # the third Tuesday
    assert run(s, None, 3) == [la(2026, 10, 20, 9), la(2026, 11, 17, 9), la(2026, 12, 15, 9)]
    last = {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": -1}}
    s, _ = make("2026-10-30", "09:00", last)  # the last Friday
    # November has Fridays 6,13,20,27 (four); December 4,11,18,25; January 1,8,15,22,29 (five).
    assert run(s, None, 4) == [
        la(2026, 10, 30, 9),
        la(2026, 11, 27, 9),
        la(2026, 12, 25, 9),
        la(2027, 1, 29, 9),
    ]
    s, _ = make(
        "2026-10-20",
        "09:00",
        {"every": 2, "unit": "month", "month_by": {"by": "weekday", "nth": 1}},
    )
    # Start is the third Tuesday, the rule says the first: the series begins at Dec 1.
    assert run(s, None, 2) == [la(2026, 12, 1, 9), la(2027, 2, 2, 9)]


def test_year_unit_and_leap_day() -> None:
    s, _ = make("2026-10-29", "09:00", {"every": 1, "unit": "year"})
    assert run(s, None, 3) == [la(2026, 10, 29, 9), la(2027, 10, 29, 9), la(2028, 10, 29, 9)]
    s10, _ = make("2026-10-29", "09:00", {"every": 10, "unit": "year"})
    assert run(s10, None, 2) == [la(2026, 10, 29, 9), la(2036, 10, 29, 9)]
    leap, _ = make("2024-02-29", "09:00", {"every": 1, "unit": "year"}, now=u(2024, 1, 1))
    assert run(leap, None, 3) == [la(2024, 2, 29, 9), la(2028, 2, 29, 9), la(2032, 2, 29, 9)]
    far, _ = make("2096-02-29", "09:00", {"every": 1, "unit": "year"}, now=u(2096, 1, 1))
    assert run(far, None, 2) == [la(2096, 2, 29, 9), la(2104, 2, 29, 9)]  # 2100 is not a leap year
    assert first(far, None, la(2096, 2, 29, 9)) == la(2104, 2, 29, 9)


def test_the_search_is_bounded(monkeypatch) -> None:
    far, _ = make("2096-02-29", "09:00", {"every": 1, "unit": "year"}, now=u(2096, 1, 1))
    monkeypatch.setattr(rec, "MAX_CONSECUTIVE_SKIPS", 2)
    assert first(far, None, la(2096, 2, 29, 9)) is None
    monkeypatch.undo()
    # The calendar ends at year 9999.
    end = rec.check(
        {
            "start": {"date": "9990-10-29", "time": "09:00"},
            "repeat": {"every": 10, "unit": "year"},
            "ends": {"kind": "never"},
        },
        None,
    )
    assert first(end, None, la(9990, 10, 29, 9)) is None


def test_ends_on_a_date_is_inclusive_in_the_zone() -> None:
    s, _ = make(
        "2026-10-29", "09:00", {"every": 1, "unit": "day"}, {"kind": "on", "date": "2026-11-01"}
    )
    assert len(list(rec.occurrences(s, None, LA))) == 4
    assert first(s, None, la(2026, 11, 1, 9)) is None
    # 23:30 local on Oct 31 is already Nov 1 in UTC; the Nov 1 00:30 local run is past the end.
    m, a = make(
        "2026-10-31", "23:30", {"every": 60, "unit": "minute"}, {"kind": "on", "date": "2026-10-31"}
    )
    assert list(rec.occurrences(m, a, LA)) == [a]
    assert rec.last_occurrence(m, a, LA) == a


def test_ends_after_n_counts_from_the_start() -> None:
    s, _ = make("2026-10-01", "09:00", {"every": 1, "unit": "day"}, {"kind": "after", "count": 12})
    # Oct 1..Oct 12; "now" is Oct 10 15:45 PDT, so the 10th has run and two remain.
    assert list(rec.occurrences(s, None, LA, NOW)) == [la(2026, 10, 11, 9), la(2026, 10, 12, 9)]
    assert rec.has_future(s, None, NOW, LA)
    assert not rec.has_future(s, None, la(2026, 10, 12, 9), LA)
    done, _ = make(
        "2026-09-01", "09:00", {"every": 1, "unit": "day"}, {"kind": "after", "count": 3}
    )
    assert not rec.has_future(done, None, NOW, LA)  # the Nth occurrence is before now
    assert rec.last_occurrence(done, None, LA) == la(2026, 9, 3, 9)
    ten, a = make(
        "2026-10-29", "15:00", {"every": 5, "unit": "minute"}, {"kind": "after", "count": 3}
    )
    assert run(ten, a, 10) == [a, a + timedelta(minutes=5), a + timedelta(minutes=10)]
    assert rec.last_occurrence(ten, a, LA) == a + timedelta(minutes=10)
    sk, _ = make(
        "2026-10-31", "09:00", {"every": 1, "unit": "month"}, {"kind": "after", "count": 2}
    )
    assert run(sk, None, 5) == [
        la(2026, 10, 31, 9),
        la(2026, 12, 31, 9),
    ]  # skipped months don't count


def test_last_occurrence() -> None:
    never, na = make("2026-10-29", "09:00", {"every": 1, "unit": "day"})
    assert rec.last_occurrence(never, na, LA) is None
    on, _ = make(
        "2026-10-29", "09:00", {"every": 7, "unit": "day"}, {"kind": "on", "date": "2026-11-20"}
    )
    assert rec.last_occurrence(on, None, LA) == la(2026, 11, 19, 9)
    empty, _ = make(
        "2026-10-31", "09:00", {"every": 1, "unit": "month"}, {"kind": "on", "date": "2026-11-30"}
    )
    assert rec.last_occurrence(empty, None, LA) == la(2026, 10, 31, 9)
    hr, ah = make(
        "2026-10-29", "15:00", {"every": 7, "unit": "hour"}, {"kind": "on", "date": "2026-10-30"}
    )
    last = rec.last_occurrence(hr, ah, LA)
    assert last.astimezone(LA).date().isoformat() == "2026-10-30"
    assert (last + timedelta(hours=7)).astimezone(LA).date().isoformat() == "2026-10-31"
    one, oa = make("2026-10-29", "15:00")
    assert rec.last_occurrence(one, oa, LA) is None


def test_one_off_occurrences() -> None:
    s, a = make("2026-10-29", "15:00")
    assert run(s, a, 3) == [a]
    assert first(s, a, a) is None
    assert not rec.has_future(s, a, a, LA)
    assert rec.has_future(s, a, a - timedelta(seconds=1), LA)


# ── AC4: daylight saving ──────────────────────────────────────────────────


def spring_cases():
    return [
        ("day", {"every": 1, "unit": "day"}, "2027-03-13"),
        ("week", {"every": 1, "unit": "week", "days": [6]}, "2027-03-07"),
        ("month", {"every": 1, "unit": "month"}, "2027-02-14"),
        ("year", {"every": 1, "unit": "year"}, "2026-03-14"),
    ]


@pytest.mark.parametrize(("name", "repeat", "start"), spring_cases())
def test_spring_forward_gap_runs_once_at_the_end_of_the_gap(name, repeat, start) -> None:
    now = u(2027, 1, 1) if name != "year" else u(2026, 10, 10)
    s, _ = make(start, "02:30", repeat, now=now)
    assert s["start"]["time"] == "02:30"
    runs = run(s, None, 3, after=u(2027, 3, 10))
    gap_day = [r for r in runs if r.astimezone(LA).date().isoformat() == "2027-03-14"]
    assert gap_day == [u(2027, 3, 14, 10, 0)]  # 03:00 PDT, once


@pytest.mark.parametrize(
    ("repeat", "start"),
    [
        ({"every": 1, "unit": "day"}, "2026-10-31"),
        ({"every": 1, "unit": "week", "days": [6]}, "2026-11-01"),
        ({"every": 1, "unit": "month"}, "2026-11-01"),
        ({"every": 1, "unit": "year"}, "2026-11-01"),
    ],
)
def test_fall_back_repeated_time_runs_once_on_the_first_occurrence(repeat, start) -> None:
    s, _ = make(start, "01:30", repeat)
    runs = [r for r in run(s, None, 3) if r.astimezone(LA).date().isoformat() == "2026-11-01"]
    assert runs == [u(2026, 11, 1, 8, 30)]  # 01:30 PDT, not 01:30 PST (09:30Z)


def test_minute_and_hour_units_keep_exact_spacing_across_dst() -> None:
    for now, anchor_date, anchor_time in (
        (u(2026, 10, 20), "2026-10-31", "20:00"),
        (u(2027, 3, 1), "2027-03-13", "20:00"),
    ):
        s, a = make(anchor_date, anchor_time, {"every": 2, "unit": "hour"}, now=now)
        runs = run(s, a, 8)
        assert [b - c for b, c in zip(runs[1:], runs)] == [timedelta(hours=2)] * 7
        m, ma = make(anchor_date, anchor_time, {"every": 90, "unit": "minute"}, now=now)
        runs = run(m, ma, 8)
        assert [b - c for b, c in zip(runs[1:], runs)] == [timedelta(minutes=90)] * 7


def test_one_off_in_the_repeated_hour_keeps_its_instant() -> None:
    second = u(2026, 11, 1, 9, 30)  # 01:30 PST, the second pass
    s, a = rec.normalize({"kind": "once", "at": "2026-11-01T09:30:00Z"}, zone=LA, now=NOW)
    assert a == second and s["start"] == {"date": "2026-11-01", "time": "01:30"}
    assert run(s, a, 2) == [second]
    assert first(s, a, second - timedelta(seconds=1)) == second


# ── AC5: grace and counting ───────────────────────────────────────────────


def test_grace_matches_the_legacy_rule() -> None:
    one, a = make("2026-10-29", "15:00")
    assert rec.grace(one, a, a, LA) == timedelta(hours=24)
    day, _ = make("2026-10-29", "09:00", {"every": 1, "unit": "day"})
    assert rec.grace(day, None, la(2026, 10, 29, 9), LA) == timedelta(hours=2)
    h2, ha = make("2026-10-29", "15:00", {"every": 2, "unit": "hour"})
    assert rec.grace(h2, ha, ha, LA) == timedelta(hours=1)
    m10, ma = make("2026-10-29", "15:00", {"every": 10, "unit": "minute"})
    assert rec.grace(m10, ma, ma, LA) == timedelta(minutes=5)
    ended, _ = make(
        "2026-10-29", "09:00", {"every": 1, "unit": "day"}, {"kind": "after", "count": 2}
    )
    assert rec.grace(ended, None, la(2026, 10, 29, 9), LA) == timedelta(hours=2)
    assert rec.grace(ended, None, la(2026, 10, 30, 9), LA) == timedelta(hours=24)


def test_occurrences_between_counts_the_half_open_range_with_a_cap() -> None:
    s, _ = make("2026-10-01", "09:00", {"every": 1, "unit": "day"})
    start, end = la(2026, 10, 12, 9), la(2026, 10, 15, 9)
    assert rec.occurrences_between(s, None, start, end, LA) == 3  # (start, end]
    assert rec.occurrences_between(s, None, start, end, LA, cap=2) == 2
    m, a = make("2026-10-29", "15:00", {"every": 1, "unit": "minute"})
    assert rec.occurrences_between(m, a, a, a + timedelta(days=2), LA, cap=5000) == 2 * 1440
    assert rec.occurrences_between(m, a, a, a + timedelta(days=2), LA) == 1001  # the default cap
    done, _ = make(
        "2026-10-01", "09:00", {"every": 1, "unit": "day"}, {"kind": "after", "count": 3}
    )
    assert rec.occurrences_between(done, None, la(2026, 9, 1, 0), la(2026, 12, 1), LA) == 3


# ── DD12: the zone render helper ──────────────────────────────────────────


def test_render_start_and_rezone() -> None:
    s, a = make("2026-10-29", "15:00", {"every": 90, "unit": "minute"})
    assert rec.render_start(a, LA) == {"date": "2026-10-29", "time": "15:00"}
    moved = rec.rezone(s, a, LONDON)
    assert moved["start"] == {"date": "2026-10-29", "time": "22:00"}
    assert moved["repeat"] == s["repeat"] and s["start"]["time"] == "15:00"
    day, _ = make("2026-10-29", "09:00", {"every": 1, "unit": "day"})
    assert rec.rezone(day, None, LONDON) is day

"""Sentences and warnings for the calendar recurrence (M33 F3 leg 3, DD7)."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from the_one.routines import recurrence as rec
from the_one.routines import recurrence_text as text

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=timezone.utc)


def sentence(date_, time_, repeat=None, ends=None, zone=LA) -> str:
    raw: dict = {"start": {"date": date_, "time": time_}}
    if repeat is not None:
        raw["repeat"] = repeat
    if ends is not None:
        raw["ends"] = ends
    sched, anchor = rec.normalize(raw, zone=zone, now=NOW)
    return text.describe(sched, anchor, zone)


MON_FRI = [0, 1, 2, 3, 4]
THIRD = {"by": "weekday", "nth": 3}

CASES = [
    ("2026-10-29", "15:00", None, None, "Once, on Thu, Oct 29, 2026 at 3:00 PM"),
    ("2026-10-29", "09:00", {"every": 1, "unit": "day"}, None, "Every day at 9:00 AM"),
    ("2026-10-29", "09:00", {"every": 3, "unit": "day"}, None, "Every 3 days at 9:00 AM"),
    (
        "2026-10-29",
        "09:00",
        {"every": 1, "unit": "week", "days": MON_FRI},
        None,
        "Every weekday at 9:00 AM",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 1, "unit": "week", "days": [3, 1]},
        None,
        "Every week on Tue, Thu at 9:00 AM",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 1, "unit": "week", "days": [0, 1, 2, 3]},
        None,
        "Every week on Mon, Tue, Wed, Thu at 9:00 AM",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 2, "unit": "week", "days": MON_FRI},
        None,
        "Every 2 weeks on Mon, Tue, Wed, Thu, Fri at 9:00 AM",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 2, "unit": "week", "days": [0]},
        None,
        "Every 2 weeks on Mon at 9:00 AM",
    ),
    (
        "2026-10-15",
        "09:00",
        {"every": 1, "unit": "month"},
        None,
        "Every month on day 15 at 9:00 AM",
    ),
    (
        "2026-10-15",
        "09:00",
        {"every": 3, "unit": "month"},
        None,
        "Every 3 months on day 15 at 9:00 AM",
    ),
    (
        "2026-10-20",
        "09:00",
        {"every": 1, "unit": "month", "month_by": THIRD},
        None,
        "Every month on the third Tuesday at 9:00 AM",
    ),
    (
        "2026-10-30",
        "09:00",
        {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": -1}},
        None,
        "Every month on the last Friday at 9:00 AM",
    ),
    (
        "2026-10-06",
        "09:00",
        {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": 1}},
        None,
        "Every month on the first Tuesday at 9:00 AM",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 1, "unit": "year"},
        None,
        "Every year on October 29 at 9:00 AM",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 2, "unit": "year"},
        None,
        "Every 2 years on October 29 at 9:00 AM",
    ),
    (
        "2026-10-29",
        "15:00",
        {"every": 90, "unit": "minute"},
        None,
        "Every 90 minutes from Oct 29 at 3:00 PM",
    ),
    (
        "2026-10-29",
        "15:00",
        {"every": 1, "unit": "minute"},
        None,
        "Every minute from Oct 29 at 3:00 PM",
    ),
    (
        "2026-10-29",
        "15:00",
        {"every": 2, "unit": "hour"},
        None,
        "Every 2 hours from Oct 29 at 3:00 PM",
    ),
    (
        "2026-10-29",
        "15:00",
        {"every": 1, "unit": "hour"},
        None,
        "Every hour from Oct 29 at 3:00 PM",
    ),
    ("2026-10-29", "00:05", {"every": 1, "unit": "day"}, None, "Every day at 12:05 AM"),
    ("2026-10-29", "12:00", {"every": 1, "unit": "day"}, None, "Every day at 12:00 PM"),
    (
        "2026-10-29",
        "09:00",
        {"every": 1, "unit": "day"},
        {"kind": "on", "date": "2027-01-28"},
        "Every day at 9:00 AM, until Jan 28, 2027",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 1, "unit": "day"},
        {"kind": "after", "count": 13},
        "Every day at 9:00 AM, 13 times",
    ),
    (
        "2026-10-29",
        "09:00",
        {"every": 1, "unit": "day"},
        {"kind": "after", "count": 1},
        "Every day at 9:00 AM, 1 time",
    ),
    (
        "2026-10-29",
        "15:00",
        {"every": 90, "unit": "minute"},
        {"kind": "after", "count": 4},
        "Every 90 minutes from Oct 29 at 3:00 PM, 4 times",
    ),
]


@pytest.mark.parametrize(("date_", "time_", "repeat", "ends", "expected"), CASES)
def test_sentences(date_, time_, repeat, ends, expected) -> None:
    assert sentence(date_, time_, repeat, ends) == expected


def test_anchored_sentences_follow_the_anchor_in_the_zone() -> None:
    sched, anchor = rec.normalize(
        {"start": {"date": "2026-10-29", "time": "15:00"}, "repeat": {"every": 2, "unit": "hour"}},
        zone=LA,
        now=NOW,
    )
    london = ZoneInfo("Europe/London")
    assert text.describe(sched, anchor, LA) == "Every 2 hours from Oct 29 at 3:00 PM"
    assert text.describe(sched, anchor, london) == "Every 2 hours from Oct 29 at 10:00 PM"
    shifted = rec.rezone(sched, anchor, london)
    assert text.describe(shifted, anchor, london) == "Every 2 hours from Oct 29 at 10:00 PM"


def test_one_off_in_a_later_zone_date() -> None:
    sched, anchor = rec.normalize(
        {"start": {"date": "2026-10-29", "time": "19:00"}}, zone=LA, now=NOW
    )
    assert text.describe(sched, anchor, LA) == "Once, on Thu, Oct 29, 2026 at 7:00 PM"


def test_sentences_name_no_chat_or_channel() -> None:
    out = sentence("2026-10-29", "09:00", {"every": 1, "unit": "day"})
    assert "chat" not in out.lower() and "channel" not in out.lower()


def norm(date_, repeat):
    sched, _ = rec.normalize(
        {"start": {"date": date_, "time": "09:00"}, "repeat": repeat}, zone=LA, now=NOW
    )
    return sched


@pytest.mark.parametrize(
    ("date_", "repeat", "expected"),
    [
        (
            "2026-10-31",
            {"every": 1, "unit": "month"},
            ["Some months have fewer than 31 days. Those months are skipped."],
        ),
        (
            "2026-10-30",
            {"every": 1, "unit": "month"},
            ["Some months have fewer than 30 days. Those months are skipped."],
        ),
        (
            "2026-10-29",
            {"every": 1, "unit": "month"},
            ["Some months have fewer than 29 days. Those months are skipped."],
        ),
        ("2026-10-28", {"every": 1, "unit": "month"}, []),
        ("2026-10-31", {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": -1}}, []),
        ("2026-10-31", {"every": 1, "unit": "week", "days": [5]}, []),
        ("2026-10-31", None, []),
        ("2026-10-29", {"every": 1, "unit": "year"}, []),
    ],
)
def test_month_day_warning(date_, repeat, expected) -> None:
    sched, _ = rec.normalize(
        {"start": {"date": date_, "time": "09:00"}, "repeat": repeat}, zone=LA, now=NOW
    )
    assert text.warnings(sched) == expected


def test_leap_day_warning() -> None:
    sched, _ = rec.normalize(
        {"start": {"date": "2028-02-29", "time": "09:00"}, "repeat": {"every": 1, "unit": "year"}},
        zone=LA,
        now=datetime(2028, 1, 1, tzinfo=timezone.utc),
    )
    assert text.warnings(sched) == [
        "February 29 only comes in leap years. Other years are skipped."
    ]
    assert text.warnings(norm("2026-10-29", {"every": 1, "unit": "year"})) == []

"""The pure routine-schedule calculator (M33 F1 leg 1, DD2-DD4)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from the_one.routines import schedule as sch
from the_one.routines.limits import RoutineScheduleError

UTC = timezone.utc
LA = ZoneInfo("America/Los_Angeles")
LONDON = ZoneInfo("Europe/London")
KOLKATA = ZoneInfo("Asia/Kolkata")
LORD_HOWE = ZoneInfo("Australia/Lord_Howe")


def u(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


# ── validate ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "good",
    [
        {"kind": "once", "at": "2026-12-01T10:00:00+00:00"},
        {"kind": "once", "at": "2026-12-01T10:00:00Z"},
        {"kind": "daily", "time": "09:00"},
        {"kind": "weekdays", "time": "23:59"},
        {"kind": "weekly", "days": [4, 0, 4], "time": "00:00"},
        {"kind": "interval", "hours": 1},
        {"kind": "interval", "hours": 168},
    ],
)
def test_validate_accepts_the_five_kinds(good) -> None:
    assert sch.validate(good)["kind"] == good["kind"]


def test_validate_normalizes_weekly_days_and_once_at() -> None:
    assert sch.validate({"kind": "weekly", "days": [4, 0, 4], "time": "09:00"})["days"] == [0, 4]
    assert sch.validate({"kind": "once", "at": "2026-12-01T10:00:00Z"})["at"] == (
        "2026-12-01T10:00:00+00:00"
    )


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "daily",
        {},
        {"kind": "monthly"},
        {"kind": "daily"},
        {"kind": "daily", "time": "9:00"},
        {"kind": "daily", "time": "24:00"},
        {"kind": "daily", "time": "09:60"},
        {"kind": "daily", "time": 900},
        {"kind": "daily", "time": "09:00", "extra": 1},
        {"kind": "weekly", "days": [], "time": "09:00"},
        {"kind": "weekly", "days": [7], "time": "09:00"},
        {"kind": "weekly", "days": [True], "time": "09:00"},
        {"kind": "weekly", "days": "mon", "time": "09:00"},
        {"kind": "weekly", "time": "09:00"},
        {"kind": "interval", "hours": 0},
        {"kind": "interval", "hours": 169},
        {"kind": "interval", "hours": 1.5},
        {"kind": "interval", "hours": True},
        {"kind": "interval"},
        {"kind": "once"},
        {"kind": "once", "at": "tomorrow"},
        {"kind": "once", "at": "2026-12-01T10:00:00"},
        {"kind": "once", "at": "2026-12-01T10:00:00-07:00"},
        {"kind": "once", "at": 5},
        {"kind": "once", "at": "2026-12-01T10:00:00Z", "time": "09:00"},
    ],
)
def test_validate_refuses_with_a_sentence(bad) -> None:
    with pytest.raises(RoutineScheduleError) as ei:
        sch.validate(bad)
    assert ei.value.detail and ei.value.detail.endswith((".", ")"))


# ── next_run: the simple kinds ────────────────────────────────────────────


def test_daily_before_and_after_the_time() -> None:
    s = {"kind": "daily", "time": "09:00"}
    # 2026-10-10 07:00 PDT = 14:00Z -> today 09:00 PDT = 16:00Z
    assert sch.next_run(s, after=u(2026, 10, 10, 14), zone=LA, anchor=None) == u(2026, 10, 10, 16)
    # exactly at the time -> strictly after -> tomorrow
    assert sch.next_run(s, after=u(2026, 10, 10, 16), zone=LA, anchor=None) == u(2026, 10, 11, 16)


def test_weekdays_friday_evening_goes_to_monday() -> None:
    s = {"kind": "weekdays", "time": "09:00"}
    assert date(2026, 10, 9).weekday() == 4
    after = datetime(2026, 10, 9, 18, 0, tzinfo=LA).astimezone(UTC)
    assert sch.next_run(s, after=after, zone=LA, anchor=None) == datetime(
        2026, 10, 12, 9, 0, tzinfo=LA
    ).astimezone(UTC)


def test_weekly_several_days() -> None:
    s = {"kind": "weekly", "days": [0, 2, 4], "time": "08:30"}  # Mon Wed Fri
    cur = datetime(2026, 10, 5, 8, 30, tzinfo=LA).astimezone(UTC)  # Monday
    seen = []
    for _ in range(5):
        cur = sch.next_run(s, after=cur, zone=LA, anchor=None)
        seen.append(cur.astimezone(LA).strftime("%a %d %H:%M"))
    assert seen == ["Wed 07 08:30", "Fri 09 08:30", "Mon 12 08:30", "Wed 14 08:30", "Fri 16 08:30"]


def test_interval_anchored() -> None:
    s = {"kind": "interval", "hours": 3}
    anchor = u(2026, 10, 10, 12)
    assert sch.next_run(s, after=u(2026, 10, 10, 12), zone=LA, anchor=anchor) == u(2026, 10, 10, 15)
    assert sch.next_run(s, after=u(2026, 10, 10, 14, 59), zone=LA, anchor=anchor) == u(
        2026, 10, 10, 15
    )
    assert sch.next_run(s, after=u(2026, 10, 10, 15), zone=LA, anchor=anchor) == u(2026, 10, 10, 18)


def test_interval_before_anchor_gives_anchor_plus_hours_not_anchor() -> None:
    s = {"kind": "interval", "hours": 3}
    anchor = u(2026, 10, 10, 12)
    assert sch.next_run(s, after=u(2026, 10, 10, 1), zone=LA, anchor=anchor) == u(2026, 10, 10, 15)


def test_interval_is_elapsed_time_across_a_dst_change() -> None:
    s = {"kind": "interval", "hours": 24}
    anchor = u(2026, 3, 7, 17)  # LA 09:00 PST the day before spring-forward
    nxt = sch.next_run(s, after=anchor, zone=LA, anchor=anchor)
    assert nxt == u(2026, 3, 8, 17)  # exactly 24h later (10:00 PDT, not 09:00)
    assert nxt.astimezone(LA).hour == 10


def test_interval_needs_an_anchor() -> None:
    with pytest.raises(RoutineScheduleError):
        sch.next_run({"kind": "interval", "hours": 1}, after=u(2026, 1, 1), zone=LA, anchor=None)


def test_once_future_and_past() -> None:
    s = {"kind": "once", "at": "2026-12-01T10:00:00+00:00"}
    assert sch.next_run(s, after=u(2026, 11, 1), zone=LA, anchor=None) == u(2026, 12, 1, 10)
    assert sch.next_run(s, after=u(2026, 12, 1, 10), zone=LA, anchor=None) is None
    assert sch.next_run(s, after=u(2027, 1, 1), zone=LA, anchor=None) is None


# ── DST ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("zone", "day", "hhmm", "expected"),
    [
        (LA, date(2026, 3, 8), (2, 30), u(2026, 3, 8, 10)),  # gap end 03:00 PDT, not 03:30
        (LA, date(2026, 3, 8), (2, 0), u(2026, 3, 8, 10)),
        (LONDON, date(2026, 3, 29), (1, 30), u(2026, 3, 29, 1)),  # 02:00 BST
        (LONDON, date(2026, 10, 25), (1, 30), u(2026, 10, 25, 0, 30)),  # first 01:30
        (LA, date(2026, 11, 1), (1, 30), u(2026, 11, 1, 8, 30)),  # first 01:30 PDT
        (KOLKATA, date(2026, 10, 10), (9, 0), u(2026, 10, 10, 3, 30)),
        (LA, date(2026, 10, 10), (9, 0), u(2026, 10, 10, 16)),
    ],
)
def test_resolve_wall_time_table(zone, day, hhmm, expected) -> None:
    assert sch.resolve_wall_time(day, hhmm[0], hhmm[1], zone) == expected


def test_la_gap_is_not_zoneinfos_0330() -> None:
    naive_guess = datetime(2026, 3, 8, 2, 30, tzinfo=LA).astimezone(UTC)
    assert naive_guess == u(2026, 3, 8, 10, 30)  # the trap
    got = sch.resolve_wall_time(date(2026, 3, 8), 2, 30, LA)
    assert got == u(2026, 3, 8, 10) and got != naive_guess


def test_lord_howe_gap_resolves_to_a_whole_minute_gap_end() -> None:
    # 2026-10-04 02:00 -> 02:30 (+10:30 -> +11:00)
    got = sch.resolve_wall_time(date(2026, 10, 4), 2, 15, LORD_HOWE)
    assert got.second == 0 and got.microsecond == 0
    local = got.astimezone(LORD_HOWE)
    assert (local.hour, local.minute) == (2, 30)
    assert local.utcoffset() == timedelta(hours=11)


def test_fall_back_runs_once_next_day_is_next_occurrence() -> None:
    s = {"kind": "daily", "time": "01:30"}
    first = sch.next_run(s, after=u(2026, 11, 1, 0), zone=LA, anchor=None)
    assert first == u(2026, 11, 1, 8, 30)
    assert first.astimezone(LA).tzname() == "PDT"
    second = sch.next_run(s, after=first, zone=LA, anchor=None)
    # Never a second 01:30 PST (09:30Z); the next day's 01:30 PST = 09:30Z on Nov 2.
    assert second == u(2026, 11, 2, 9, 30)


def test_spring_forward_daily_runs_once_at_gap_end() -> None:
    s = {"kind": "daily", "time": "02:30"}
    first = sch.next_run(s, after=u(2026, 3, 8, 0), zone=LA, anchor=None)
    assert first == u(2026, 3, 8, 10)
    assert sch.next_run(s, after=first, zone=LA, anchor=None) == datetime(
        2026, 3, 9, 2, 30, tzinfo=LA
    ).astimezone(UTC)


def test_kolkata_exact_wall_time() -> None:
    s = {"kind": "daily", "time": "09:00"}
    nxt = sch.next_run(s, after=u(2026, 10, 10, 4), zone=KOLKATA, anchor=None)
    assert nxt == u(2026, 10, 11, 3, 30)


# ── grace, occurrences_between ────────────────────────────────────────────


def test_grace() -> None:
    due = u(2026, 10, 10, 16)
    assert sch.grace({"kind": "once", "at": "2026-10-10T16:00:00+00:00"}, due, LA) == timedelta(
        hours=24
    )
    assert sch.grace({"kind": "daily", "time": "09:00"}, due, LA) == timedelta(hours=2)
    anchor = u(2026, 10, 10, 10)
    assert sch.grace({"kind": "interval", "hours": 2}, due, LA, anchor) == timedelta(hours=1)
    assert sch.grace({"kind": "interval", "hours": 1}, due, LA, anchor) == timedelta(minutes=30)
    assert sch.grace({"kind": "interval", "hours": 168}, due, LA, anchor) == timedelta(hours=2)


def test_occurrences_between_counts_and_caps() -> None:
    s = {"kind": "interval", "hours": 1}
    anchor = u(2026, 1, 1)
    start, end = u(2026, 1, 1, 0, 30), u(2026, 1, 1, 5, 30)
    assert sch.occurrences_between(s, start, end, LA, anchor) == 5  # 1:00..5:00
    # (start, end] -- end included
    assert sch.occurrences_between(s, u(2026, 1, 1), u(2026, 1, 1, 3), LA, anchor) == 3
    assert sch.occurrences_between(s, u(2026, 1, 1), u(2026, 6, 1), LA, anchor) == 1001
    assert sch.occurrences_between(s, u(2026, 1, 1), u(2026, 6, 1), LA, anchor, cap=7) == 7
    once = {"kind": "once", "at": "2026-01-01T05:00:00+00:00"}
    assert sch.occurrences_between(once, u(2026, 1, 1), u(2026, 2, 1), LA, None) == 1


def test_calculator_never_reads_the_clock() -> None:
    src = Path(sch.__file__).read_text()
    assert "datetime.now(" not in src

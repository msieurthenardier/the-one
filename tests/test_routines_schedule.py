"""The wall-time helpers behind routine schedules (M33 F1 leg 1, DD3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from the_one.routines import schedule as sch

UTC = timezone.utc
LA = ZoneInfo("America/Los_Angeles")
LONDON = ZoneInfo("Europe/London")
KOLKATA = ZoneInfo("Asia/Kolkata")
LORD_HOWE = ZoneInfo("Australia/Lord_Howe")


def u(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


# ── resolve_wall_time ─────────────────────────────────────────────────────


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


def test_fall_back_runs_once_on_its_first_occurrence() -> None:
    first = sch.resolve_wall_time(date(2026, 11, 1), 1, 30, LA)
    assert first == u(2026, 11, 1, 8, 30)
    assert first.astimezone(LA).tzname() == "PDT"


def test_spring_forward_resolves_to_the_end_of_the_gap_then_normal_days() -> None:
    assert sch.resolve_wall_time(date(2026, 3, 8), 2, 30, LA) == u(2026, 3, 8, 10)
    assert sch.resolve_wall_time(date(2026, 3, 9), 2, 30, LA) == datetime(
        2026, 3, 9, 2, 30, tzinfo=LA
    ).astimezone(UTC)


def test_kolkata_exact_wall_time() -> None:
    assert sch.resolve_wall_time(date(2026, 10, 11), 9, 0, KOLKATA) == u(2026, 10, 11, 3, 30)


def test_calculator_never_reads_the_clock() -> None:
    src = Path(sch.__file__).read_text()
    assert "datetime.now(" not in src

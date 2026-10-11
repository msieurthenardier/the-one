# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Engine-parametrized contract tests for ``App.time`` (M28 F2 L1, DD1).

``time.js`` needs only ``window``, so each test loads it into a blank page (no app
spawn). Runs in Chromium and WebKit through ``engine_page``; falls in the
``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import STATIC_DIR
from playwright.sync_api import Page

pytestmark = pytest.mark.browser


@pytest.fixture
def tpage(engine_page: Page) -> Page:
    engine_page.set_content("<!doctype html><html><body></body></html>")
    engine_page.add_script_tag(path=str(STATIC_DIR / "js" / "time.js"))
    return engine_page


# 2026-06-15T12:00:00Z (a Monday).
NOON = "Date.UTC(2026, 5, 15, 12, 0, 0)"


def test_parts_for_kolkata_and_kiritimati(tpage: Page) -> None:
    got = tpage.evaluate(
        f"""() => {{
          const out = {{}};
          for (const z of ['Asia/Kolkata', 'Pacific/Kiritimati', 'Pacific/Pago_Pago']) {{
            App.time.setZone(z);
            out[z] = App.time.parts(new Date({NOON}));
          }}
          return out;
        }}"""
    )
    assert got["Asia/Kolkata"] == {
        "year": 2026,
        "month": 5,
        "day": 15,
        "weekday": 1,
        "hour": 17,
        "minute": 30,
    }
    assert got["Pacific/Kiritimati"] == {
        "year": 2026,
        "month": 5,
        "day": 16,
        "weekday": 2,
        "hour": 2,
        "minute": 0,
    }
    assert got["Pacific/Pago_Pago"] == {
        "year": 2026,
        "month": 5,
        "day": 15,
        "weekday": 1,
        "hour": 1,
        "minute": 0,
    }


def test_local_path_matches_the_date_getters(tpage: Page) -> None:
    got = tpage.evaluate(
        """() => {
          App.time.setZone(null);
          const bad = [];
          for (const t of [0, 951782400000, 1700000000000, Date.UTC(2026, 2, 8, 7, 30), Date.now()]) {
            const d = new Date(t), p = App.time.parts(d);
            const want = {year: d.getFullYear(), month: d.getMonth(), day: d.getDate(),
                          weekday: d.getDay(), hour: d.getHours(), minute: d.getMinutes()};
            if (JSON.stringify(p) !== JSON.stringify(want)) bad.push([t, p, want]);
          }
          return {bad, zone: App.time.zone()};
        }"""
    )
    assert got == {"bad": [], "zone": None}


def test_format_clock_at_midnight_and_noon(tpage: Page) -> None:
    got = tpage.evaluate(
        """() => {
          App.time.setZone('Asia/Kolkata');
          // Kolkata is UTC+5:30: 18:30Z is 00:00 next day, 06:30Z is 12:00.
          return [Date.UTC(2026, 5, 14, 18, 30), Date.UTC(2026, 5, 15, 6, 30),
                  Date.UTC(2026, 5, 15, 6, 29), Date.UTC(2026, 5, 15, 18, 29)]
            .map((t) => App.time.formatClock(new Date(t)));
        }"""
    )
    assert got == ["12:00 AM", "12:00 PM", "11:59 AM", "11:59 PM"]


@pytest.mark.parametrize("year,month,day", [(2026, 2, 8), (2026, 10, 1)])
def test_day_number_across_a_us_dst_change(tpage: Page, year: int, month: int, day: int) -> None:
    got = tpage.evaluate(
        """([y, m, d]) => {
          App.time.setZone('America/New_York');
          return [-1, 0, 1].map((k) => App.time.dayNumber(new Date(Date.UTC(y, m, d + k, 12, 0))));
        }""",
        [year, month, day],
    )
    assert got[1] - got[0] == 1 and got[2] - got[1] == 1
    assert all(isinstance(n, int) for n in got)


def test_offset_zone_is_engine_independent(tpage: Page) -> None:
    got = tpage.evaluate(
        f"""() => {{
          App.time.setZone('+05:30');
          const a = App.time.parts(new Date({NOON}));
          const z1 = App.time.zone();
          App.time.setZone('-03:30');
          const b = App.time.parts(new Date(Date.UTC(2026, 5, 15, 2, 0)));
          App.time.setZone('+00:00');
          const c = App.time.formatClock(new Date({NOON}));
          return {{a, b, c, z1}};
        }}"""
    )
    assert got["a"] == {"year": 2026, "month": 5, "day": 15, "weekday": 1, "hour": 17, "minute": 30}
    assert got["b"] == {"year": 2026, "month": 5, "day": 14, "weekday": 0, "hour": 22, "minute": 30}
    assert got["c"] == "12:00 PM" and got["z1"] == "+05:30"


def test_invalid_zone_falls_back_to_local_with_one_warning(tpage: Page) -> None:
    got = tpage.evaluate(
        """() => {
          const warns = [];
          const orig = console.warn;
          console.warn = (...a) => warns.push(a.join(' '));
          App.time.setZone('Asia/Kolkata');
          App.time.setZone('Mars/Olympus_Mons');
          console.warn = orig;
          const d = new Date(Date.UTC(2026, 5, 15, 12, 0));
          return {zone: App.time.zone(), warns: warns.length,
                  hour: App.time.parts(d).hour, local: d.getHours()};
        }"""
    )
    assert got["zone"] is None and got["warns"] == 1 and got["hour"] == got["local"]


def test_on_change_fires_once_per_effective_change(tpage: Page) -> None:
    got = tpage.evaluate(
        """() => {
          const seen = [];
          const off = App.time.onChange((k) => seen.push(k));
          App.time.setZone('Asia/Kolkata');
          App.time.setZone('Asia/Kolkata');
          App.time.setZone(null);
          App.time.setZone(null);
          off();
          App.time.setZone('Asia/Tokyo');
          return seen;
        }"""
    )
    assert got == ["Asia/Kolkata", None]


def test_zone_from_settings_branches(tpage: Page) -> None:
    got = tpage.evaluate(
        """() => {
          const z = App.time.zoneFromSettings;
          return [
            z({effective: {zone: 'Asia/Calcutta', canonical: 'Asia/Kolkata', offset: 'UTC+05:30'}}),
            z({effective: {zone: 'Asia/Tokyo', canonical: null, offset: 'UTC+09:00'}}),
            z({effective: {zone: null, canonical: null, offset: 'UTC+05:30'}}),
            z({effective: {zone: null, canonical: null, offset: 'UTC-03:30'}}),
            z({effective: {zone: null, canonical: null, offset: 'weird'}}),
            z({effective: {zone: '', canonical: '', offset: ''}}),
            z(null), z(undefined), z({}), z({effective: 5}), z('x'),
          ];
        }"""
    )
    assert got == [
        "Asia/Kolkata",
        "Asia/Tokyo",
        "+05:30",
        "-03:30",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ]

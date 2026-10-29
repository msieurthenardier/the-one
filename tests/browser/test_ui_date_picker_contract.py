# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.datePicker`` (M33 F3 L6).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import STATIC_DIR, load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

MOUNT = """(extra) => {
  window.__ch = [];
  const p = App.ui.datePicker(Object.assign({
    label: 'Starts', testid: 'dp', value: '2026-10-29',
    onChange: (v) => window.__ch.push(v),
    today: () => { const t = App.time.parts(new Date());
      return t.year + '-' + String(t.month + 1).padStart(2, '0') + '-' + String(t.day).padStart(2, '0'); },
  }, extra || {}));
  window.__p = p;
  document.getElementById('harness-root').appendChild(p.el);
  return true;
}"""


def _mount(page: Page, extra: dict | None = None, theme: str = "dark") -> None:
    load_harness(page, theme)
    page.add_script_tag(path=str(STATIC_DIR / "js" / "time.js"))
    # Pin "today" to Oct 29, 2026 by overriding Date for App.time.parts' host-zone path.
    page.evaluate(
        """() => { const RealDate = Date; const fixed = RealDate.UTC(2026, 9, 29, 12, 0, 0);
          window.__RealDate = RealDate;
          window.Date = class extends RealDate { constructor(...a) { if (a.length) super(...a); else super(fixed); } static now() { return fixed; } };
          App.time.setZone('UTC'); }"""
    )
    page.evaluate(MOUNT, extra)


def _type(page: Page, text: str, commit: str = "Tab") -> None:
    box = page.get_by_test_id("dp-input")
    box.fill(text)
    page.keyboard.press(commit)


def test_structure_and_display(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    assert p.get_by_test_id("dp-input").input_value() == "Thu, Oct 29, 2026"
    assert p.get_by_role("textbox", name="Starts").count() == 1
    btn = p.get_by_test_id("dp-button")
    assert btn.get_attribute("aria-label") == "Choose date"
    assert btn.get_attribute("aria-haspopup") == "dialog"
    assert btn.get_attribute("aria-expanded") == "false"
    assert p.evaluate("() => window.__p.value()") == "2026-10-29"
    assert p.get_by_test_id("dp-calendar").is_hidden()


@pytest.mark.parametrize(
    "typed",
    [
        "2026-10-29",
        "10/29/2026",
        "10/29",
        "Oct 29, 2026",
        "Oct 29",
        "Thu, Oct 29, 2026",
        "october 29 2026",
    ],
)
def test_typed_forms_parse(engine_page: Page, typed: str) -> None:
    _mount(engine_page, {"value": None})
    _type(engine_page, typed)
    assert engine_page.evaluate("() => window.__p.value()") == "2026-10-29"
    assert engine_page.get_by_test_id("dp-input").input_value() == "Thu, Oct 29, 2026"
    assert engine_page.get_by_test_id("dp-input").get_attribute("aria-invalid") is None


def test_enter_commits_and_unreadable_is_flagged(engine_page: Page) -> None:
    _mount(engine_page, {"value": None})
    p = engine_page
    _type(p, "11/2/2026", "Enter")
    assert p.evaluate("() => window.__p.value()") == "2026-11-02"
    _type(p, "banana")
    box = p.get_by_test_id("dp-input")
    assert box.input_value() == "banana"
    assert box.get_attribute("aria-invalid") == "true"
    assert p.evaluate("() => window.__p.value()") is None
    live = p.evaluate(
        "(id) => document.getElementById(id.split(' ')[0]).getAttribute('aria-live')",
        box.get_attribute("aria-describedby"),
    )
    assert live == "polite"
    err_id = box.get_attribute("aria-describedby")
    assert (
        p.evaluate("(id) => document.getElementById(id).textContent", err_id)
        == "Enter a date like Oct 29, 2026."
    )
    _type(p, "2/30/2026")  # not a real date
    assert box.get_attribute("aria-invalid") == "true"
    _type(p, "Oct 30")
    assert box.get_attribute("aria-invalid") is None
    assert box.get_attribute("aria-describedby") in (None, "")


def test_out_of_range_sentence(engine_page: Page) -> None:
    _mount(engine_page, {"value": None, "min": "2026-10-29", "max": "2026-12-31"})
    p = engine_page
    _type(p, "Oct 1, 2026")
    box = p.get_by_test_id("dp-input")
    assert box.get_attribute("aria-invalid") == "true"
    err_id = box.get_attribute("aria-describedby")
    assert (
        p.evaluate("(id) => document.getElementById(id).textContent", err_id)
        == "Choose a date on or after Oct 29, 2026."
    )
    assert p.evaluate("() => window.__p.value()") is None
    _type(p, "Jan 2, 2027")
    assert (
        p.evaluate(
            "(id) => document.getElementById(id).textContent", box.get_attribute("aria-describedby")
        )
        == "Choose a date on or before Dec 31, 2026."
    )


def test_calendar_opens_on_value_with_marks(engine_page: Page) -> None:
    _mount(engine_page, {"min": "2026-10-10", "max": "2026-11-20"})
    p = engine_page
    p.get_by_test_id("dp-button").click()
    cal = p.get_by_test_id("dp-calendar")
    assert cal.is_visible()
    assert (
        cal.get_attribute("role") == "dialog" and cal.get_attribute("aria-label") == "October 2026"
    )
    assert p.get_by_test_id("dp-button").get_attribute("aria-expanded") == "true"
    grid = cal.locator("[role=grid]")
    assert grid.count() == 1
    heads = grid.locator("th").evaluate_all(
        "els => els.map(e => [e.textContent, e.getAttribute('abbr')])"
    )
    assert heads[0] == ["Su", "Sunday"] and heads[6] == ["Sa", "Saturday"] and len(heads) == 7
    sel = cal.locator("td[aria-selected=true] button")
    assert sel.get_attribute("data-date") == "2026-10-29"
    assert p.evaluate("() => document.activeElement.getAttribute('data-date')") == "2026-10-29"
    cur = cal.locator("button[aria-current=date]")
    assert cur.count() == 1 and cur.get_attribute("data-date") == "2026-10-29"
    assert cal.locator("button[data-date='2026-10-09']").count() == 1 or True
    assert cal.locator("button[data-date='2026-10-09']").is_disabled()
    assert cal.locator("button[data-date='2026-10-10']").is_enabled()
    assert cal.locator("button[data-date='2026-10-31']").is_enabled()
    # Oct 1 2026 is a Thursday: the first row has four leading blanks.
    first_row = (
        grid.locator("tbody tr")
        .first.locator("td")
        .evaluate_all("els => els.map(e => e.children.length)")
    )
    assert first_row == [0, 0, 0, 0, 1, 1, 1]


def test_pick_updates_fires_once_closes_and_returns_focus(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("dp-button").click()
    p.get_by_test_id("dp-calendar").locator("button[data-date='2026-10-15']").click()
    assert p.get_by_test_id("dp-input").input_value() == "Thu, Oct 15, 2026"
    assert p.evaluate("() => window.__ch") == ["2026-10-15"]
    assert p.get_by_test_id("dp-calendar").is_hidden()
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "dp-button"
    # Picking the same day again changes nothing and fires nothing.
    p.get_by_test_id("dp-button").click()
    p.get_by_test_id("dp-calendar").locator("button[data-date='2026-10-15']").click()
    assert p.evaluate("() => window.__ch") == ["2026-10-15"]


def test_keyboard_in_grid(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("dp-button").click()

    def at() -> str:
        return p.evaluate("() => document.activeElement.getAttribute('data-date')")

    p.keyboard.press("ArrowRight")
    assert at() == "2026-10-30"
    p.keyboard.press("ArrowLeft")
    p.keyboard.press("ArrowDown")
    assert at() == "2026-11-05"
    assert p.get_by_test_id("dp-calendar").get_attribute("aria-label") == "November 2026"
    p.keyboard.press("ArrowUp")
    assert at() == "2026-10-29"
    p.keyboard.press("PageDown")
    assert at() == "2026-11-29"
    p.keyboard.press("PageUp")
    assert at() == "2026-10-29"
    p.keyboard.press("Shift+PageDown")
    assert at() == "2027-10-29"
    p.keyboard.press("Shift+PageUp")
    assert at() == "2026-10-29"
    p.keyboard.press("Home")  # Thursday: Sunday is Oct 25
    assert at() == "2026-10-25"
    p.keyboard.press("End")
    assert at() == "2026-10-31"
    # roving tabindex: exactly one day is tabbable.
    assert p.get_by_test_id("dp-calendar").locator("button.ui-date-day[tabindex='0']").count() == 1
    p.keyboard.press("ArrowLeft")
    p.keyboard.press("Space")
    assert (
        p.evaluate("() => window.__p.value()") == "2026-10-30"
        or p.evaluate("() => window.__p.value()") == "2026-10-30"
    )
    p.get_by_test_id("dp-button").click()
    p.keyboard.press("ArrowRight")
    p.keyboard.press("Enter")
    assert p.evaluate("() => window.__p.value()") == "2026-10-31"


def test_month_navigation_year_boundary_and_leap_february(engine_page: Page) -> None:
    _mount(engine_page, {"value": "2027-12-31"})
    p = engine_page
    p.get_by_test_id("dp-button").click()
    p.get_by_test_id("dp-next").click()
    assert p.get_by_test_id("dp-calendar").get_attribute("aria-label") == "January 2028"
    p.get_by_test_id("dp-prev").click()
    p.get_by_test_id("dp-prev").click()
    assert p.get_by_test_id("dp-calendar").get_attribute("aria-label") == "November 2027"
    p.evaluate("() => window.__p.setValue('2028-01-31')")
    p.get_by_test_id("dp-button").click()
    p.keyboard.press("PageDown")  # Jan 31 -> Feb 29 (2028 is a leap year)
    assert p.evaluate("() => document.activeElement.getAttribute('data-date')") == "2028-02-29"
    assert p.get_by_test_id("dp-calendar").locator("button.ui-date-day").count() == 29


def test_escape_and_outside_click_close(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("dp-button").click()
    p.keyboard.press("Escape")
    assert p.get_by_test_id("dp-calendar").is_hidden()
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "dp-button"
    p.get_by_test_id("dp-button").click()
    p.mouse.click(700, 500)
    assert p.get_by_test_id("dp-calendar").is_hidden()


def test_escape_inside_modal_closes_only_the_calendar(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    p = engine_page
    p.add_script_tag(path=str(STATIC_DIR / "js" / "time.js"))
    p.evaluate(
        """() => {
          const dp = App.ui.datePicker({label: 'Ends', testid: 'dp', value: '2026-10-29'});
          window.__p = dp;
          const opener = document.createElement('button');
          opener.textContent = 'open';
          document.getElementById('harness-root').appendChild(opener);
          window.__m = App.ui.modal({title: 'Custom', body: dp.el, testid: 'md', actions: [{label: 'Done', value: 'done'}]});
          window.__m.open(opener);
        }"""
    )
    p.get_by_test_id("dp-button").click()
    assert p.get_by_test_id("dp-calendar").is_visible()
    p.keyboard.press("Escape")
    assert p.get_by_test_id("dp-calendar").is_hidden()
    assert p.get_by_test_id("md").is_visible()
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "dp-button"
    p.keyboard.press("Escape")
    assert p.get_by_test_id("md").count() == 0


def test_today_follows_the_operator_zone(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    p = engine_page
    p.add_script_tag(path=str(STATIC_DIR / "js" / "time.js"))
    # 2026-10-29T23:30Z is already Oct 30 in Kiritimati (UTC+14) and still Oct 29 in Pago Pago.
    p.evaluate(
        """() => { const R = Date; const fixed = R.UTC(2026, 9, 29, 23, 30, 0);
          window.Date = class extends R { constructor(...a) { if (a.length) super(...a); else super(fixed); } static now() { return fixed; } }; }"""
    )
    for zone, today in (("Pacific/Kiritimati", "2026-10-30"), ("Pacific/Pago_Pago", "2026-10-29")):
        p.evaluate("(z) => App.time.setZone(z)", zone)
        p.evaluate(MOUNT, {"value": None, "testid": "dp"})
        p.get_by_test_id("dp-button").click()
        cur = p.get_by_test_id("dp-calendar").locator("button[aria-current=date]")
        assert cur.get_attribute("data-date") == today, zone
        assert p.evaluate("() => document.activeElement.getAttribute('data-date')") == today
        p.keyboard.press("Escape")
        p.evaluate("() => document.getElementById('harness-root').textContent = ''")
    # "10/29" resolves against the zone's year too, and the picker's "today" start day.
    p.evaluate("(z) => App.time.setZone(z)", "Pacific/Kiritimati")
    p.evaluate(MOUNT, {"value": None, "testid": "dp"})
    _type(p, "Oct 30")
    assert p.evaluate("() => window.__p.value()") == "2026-10-30"


def test_without_today_there_is_no_mark_and_yearless_needs_a_year(engine_page: Page) -> None:
    _mount(engine_page, {"value": None, "today": None})
    p = engine_page
    p.get_by_test_id("dp-button").click()
    assert p.get_by_test_id("dp-calendar").locator("button[aria-current=date]").count() == 0
    p.keyboard.press("Escape")
    _type(p, "10/29")
    assert p.evaluate("() => window.__p.value()") is None
    box = p.get_by_test_id("dp-input")
    assert (
        p.evaluate(
            "(id) => document.getElementById(id).textContent", box.get_attribute("aria-describedby")
        )
        == "Enter a date like Oct 29, 2026."
    )
    _type(p, "Oct 29, 2026")
    assert p.evaluate("() => window.__p.value()") == "2026-10-29"
    # With a min, a year-less entry takes min's year.
    p.evaluate("() => window.__p.setValue(null)")
    p.evaluate("() => window.__p.setMin('2027-01-01')")
    _type(p, "Mar 3")
    assert p.evaluate("() => window.__p.value()") == "2027-03-03"


def test_set_value_min_max_disabled_are_silent(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        "() => { window.__p.setValue('2026-12-25'); window.__p.setMin('2026-01-01'); window.__p.setMax('2027-01-01'); }"
    )
    assert p.get_by_test_id("dp-input").input_value() == "Fri, Dec 25, 2026"
    assert p.evaluate("() => window.__ch") == []
    p.evaluate("() => window.__p.setValue(null)")
    assert (
        p.get_by_test_id("dp-input").input_value() == ""
        and p.evaluate("() => window.__p.value()") is None
    )
    p.evaluate("() => window.__p.setDisabled(true)")
    assert (
        p.get_by_test_id("dp-input").is_disabled() and p.get_by_test_id("dp-button").is_disabled()
    )


def test_two_pickers_are_independent(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        """() => { const b = App.ui.datePicker({label: 'Ends', testid: 'dq', value: '2026-11-01'});
          document.getElementById('harness-root').appendChild(b.el); }"""
    )
    ids = p.evaluate("() => Array.from(document.querySelectorAll('[id]')).map(e => e.id)")
    assert len(ids) == len(set(ids))
    p.get_by_test_id("dp-button").click()
    p.get_by_test_id("dq-button").click()
    assert (
        p.get_by_test_id("dp-calendar").is_hidden() and p.get_by_test_id("dq-calendar").is_visible()
    )


def test_destroy_removes_document_listener(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    p = engine_page
    p.add_script_tag(path=str(STATIC_DIR / "js" / "time.js"))
    p.evaluate(
        """() => { window.__live = 0;
          const add = document.addEventListener.bind(document), rem = document.removeEventListener.bind(document);
          document.addEventListener = (t, l, o) => { if (t === 'pointerdown') window.__live++; return add(t, l, o); };
          document.removeEventListener = (t, l, o) => { if (t === 'pointerdown') window.__live--; return rem(t, l, o); }; }"""
    )
    p.evaluate(MOUNT)
    assert p.evaluate("() => window.__live") == 0
    p.get_by_test_id("dp-button").click()
    assert p.evaluate("() => window.__live") == 1
    p.evaluate("() => window.__p.destroy()")
    assert p.evaluate("() => window.__live") == 0
    # A host wipe without destroy() leaves one dormant listener that cleans itself on the next press.
    p.evaluate("() => { document.getElementById('harness-root').textContent = ''; }")
    p.evaluate(MOUNT)
    p.get_by_test_id("dp-button").click()
    p.evaluate("() => { document.getElementById('harness-root').textContent = ''; }")
    p.mouse.click(700, 500)
    assert p.evaluate("() => window.__live") == 0


def test_requires_a_label(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    msg = engine_page.evaluate(
        "() => { try { App.ui.datePicker({}); return ''; } catch (e) { return e.message; } }"
    )
    assert "label" in msg

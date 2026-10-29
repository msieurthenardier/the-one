# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.timeField`` (M33 F3 L6).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

MOUNT = """(extra) => {
  window.__ch = [];
  const t = App.ui.timeField(Object.assign({
    label: 'At', testid: 'tf', onChange: (v) => window.__ch.push(v),
  }, extra || {}));
  window.__t = t;
  document.getElementById('harness-root').appendChild(t.el);
  return true;
}"""


def _mount(page: Page, extra: dict | None = None) -> None:
    load_harness(page, "dark")
    page.evaluate(MOUNT, extra)


@pytest.mark.parametrize(
    ("typed", "hhmm", "shown"),
    [
        ("9:30 AM", "09:30", "9:30 AM"),
        ("9:30am", "09:30", "9:30 AM"),
        ("9:30 a", "09:30", "9:30 AM"),
        ("9:30p", "21:30", "9:30 PM"),
        ("21:30", "21:30", "9:30 PM"),
        ("0930", "09:30", "9:30 AM"),
        ("930pm", "21:30", "9:30 PM"),
        ("9 am", "09:00", "9:00 AM"),
        ("9pm", "21:00", "9:00 PM"),
        ("12 pm", "12:00", "12:00 PM"),
        ("12 am", "00:00", "12:00 AM"),
        ("12:05 AM", "00:05", "12:05 AM"),
        ("0:00", "00:00", "12:00 AM"),
    ],
)
def test_parses_every_form(engine_page: Page, typed: str, hhmm: str, shown: str) -> None:
    _mount(engine_page)
    box = engine_page.get_by_test_id("tf-input")
    box.fill(typed)
    engine_page.keyboard.press("Tab")
    assert engine_page.evaluate("() => window.__t.value()") == hhmm
    assert box.input_value() == shown
    assert box.get_attribute("aria-invalid") is None
    assert engine_page.evaluate("() => window.__ch") == [hhmm]


@pytest.mark.parametrize("typed", ["nope", "25:00", "13 pm", "9:75", "0 am", "99999"])
def test_invalid_is_flagged(engine_page: Page, typed: str) -> None:
    _mount(engine_page, {"value": "08:00"})
    p = engine_page
    box = p.get_by_test_id("tf-input")
    box.fill(typed)
    p.keyboard.press("Enter")
    assert box.input_value() == typed
    assert box.get_attribute("aria-invalid") == "true"
    assert p.evaluate("() => window.__t.value()") is None
    err = p.evaluate(
        "(id) => document.getElementById(id).textContent", box.get_attribute("aria-describedby")
    )
    assert err == "Enter a time like 9:30 AM."
    assert (
        p.evaluate(
            "(id) => document.getElementById(id).getAttribute('aria-live')",
            box.get_attribute("aria-describedby"),
        )
        == "polite"
    )
    box.fill("10 am")
    p.keyboard.press("Enter")
    assert box.get_attribute("aria-invalid") is None
    assert p.evaluate("() => window.__t.value()") == "10:00"


def test_initial_value_set_value_silent_and_disabled(engine_page: Page) -> None:
    _mount(engine_page, {"value": "18:05"})
    p = engine_page
    box = p.get_by_test_id("tf-input")
    assert box.input_value() == "6:05 PM"
    assert p.get_by_role("textbox", name="At").count() == 1
    p.evaluate("() => window.__t.setValue('07:00')")
    assert box.input_value() == "7:00 AM" and p.evaluate("() => window.__ch") == []
    p.evaluate("() => window.__t.setValue(null)")
    assert box.input_value() == "" and p.evaluate("() => window.__t.value()") is None
    p.evaluate("() => window.__t.setDisabled(true)")
    assert box.is_disabled()


def test_requires_a_label(engine_page: Page) -> None:
    load_harness(engine_page, "dark")
    msg = engine_page.evaluate(
        "() => { try { App.ui.timeField({}); return ''; } catch (e) { return e.message; } }"
    )
    assert "label" in msg

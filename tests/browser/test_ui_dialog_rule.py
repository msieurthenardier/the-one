"""DD8 dialog-rule checks run against the test-only harness in Chromium and WebKit
(M25 F1 L2). Flight 2 adds an adapter for the real wrapper and reuses the same
checks from ``_dialog_rule_checks.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from browser._dialog_rule_checks import (
    FIXTURE_HTML,
    FIXTURE_STYLE,
    TRANSIENT_OPENERS,
    DialogAdapter,
    check_backdrop_clicks,
    check_backdrop_colour,
    check_focus_restore,
    check_inertness,
    check_programmatic_confirm,
    check_stacked_escape,
    layers,
)
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

HARNESS_JS = Path(__file__).with_name("_dialog_rule.js")

# The harness's own backdrop rule, in the var(--token) form: DD8's concern is
# custom-property inheritance into ::backdrop.
BACKDROP_CSS = (
    ":root { --x-scrim: rgb(12, 34, 56); } dialog::backdrop { background: var(--x-scrim); }"
)

WIRE_JS = """() => {
  window.__outsideClicks = 0;
  const q = (id) => document.querySelector('[data-testid=' + id + ']');
  q('dr-outside').addEventListener('click', () => { window.__outsideClicks += 1; });
  const wire = (opener, dlg, transient) => q(opener).addEventListener('click', (ev) => {
    DialogRule.open(document.getElementById(dlg), {opener: ev.currentTarget, transient});
  });
  wire('dr-open-a', 'dr-dlg-a', false);
  wire('dr-open-b', 'dr-dlg-b', false);
  wire('dr-open-t', 'dr-dlg-t', true);
  return true;
}"""


def _setup(page: Page) -> None:
    page.set_content("<!doctype html><html><head></head><body></body></html>")
    page.add_style_tag(content=FIXTURE_STYLE + BACKDROP_CSS)
    page.evaluate("(h) => { document.body.innerHTML = h; return true; }", FIXTURE_HTML)
    page.add_script_tag(path=str(HARNESS_JS))
    page.evaluate(WIRE_JS)


def _open(page: Page, opener_testid: str, transient: bool = False, via: str = "mouse") -> None:
    assert (opener_testid in TRANSIENT_OPENERS) == transient, (
        f"{opener_testid} transient mismatch (transient={transient})"
    )
    target = page.locator(f"[data-testid={opener_testid}]")
    if via == "keyboard":
        target.focus()
        page.keyboard.press("Enter")
    else:
        target.click()  # a real mouse click with user activation


def _open_confirm(page: Page) -> None:
    # No user activation between the modal's click-open and this call.
    page.evaluate(
        "() => { DialogRule.open(document.getElementById('dr-dlg-confirm'), "
        "{opener: document.querySelector('[data-testid=dr-open-a]'),"
        " transient: false}); return true; }"
    )


HARNESS = DialogAdapter(
    name="test-harness",
    setup=_setup,
    open=_open,
    close_topmost=lambda page: page.evaluate("() => DialogRule.closeTopmost()"),
    open_confirm_programmatic=_open_confirm,
    backdrop_css=BACKDROP_CSS,
    backdrop_token="--x-scrim",
)


@pytest.fixture
def dialog_page(engine_page: Page) -> Page:
    engine_page.set_viewport_size({"width": 1024, "height": 768})
    return engine_page


def _report(record_property, result: dict) -> None:
    record_property(f"dialog-{result['check']}", str(result))
    print(f"[dialog-rule] {result}")


def test_a_stacked_escape_peels_one_layer_each(dialog_page: Page, record_property) -> None:
    _report(record_property, check_stacked_escape(dialog_page, HARNESS))


def test_b_programmatic_confirm_over_modal(dialog_page: Page, record_property) -> None:
    _report(record_property, check_programmatic_confirm(dialog_page, HARNESS))


@pytest.mark.parametrize("via", ["mouse", "keyboard"])
def test_c_focus_restore(dialog_page: Page, record_property, via: str) -> None:
    _report(record_property, check_focus_restore(dialog_page, HARNESS, via))


def test_d_backdrop_clicks(dialog_page: Page, record_property) -> None:
    _report(record_property, check_backdrop_clicks(dialog_page, HARNESS))


def test_e_inertness(dialog_page: Page, record_property) -> None:
    result = check_inertness(dialog_page, HARNESS)
    _report(record_property, result)
    # positive control: Tab reaches the dialog's own buttons in every engine run here
    assert result["tab_reaches_buttons"], result


def test_f_backdrop_colour(dialog_page: Page, record_property) -> None:
    result = check_backdrop_colour(dialog_page, HARNESS)
    _report(record_property, result)
    if result["status"] == "unverifiable":
        name = dialog_page.context.browser.browser_type.name
        pytest.xfail(f"[{name}] backdrop colour unverifiable: {result['reason']}")


def test_reopen_right_after_close_survives_the_stale_close_event(dialog_page: Page) -> None:
    """Regression for a race the keyboard focus-restore check exposed: close() queues
    its close event as a task, so reopening in the same task still receives the OLD
    close event. A wrapper that trusts it drops the reopened dialog from its stack."""
    _setup(dialog_page)
    out = dialog_page.evaluate(
        """async () => {
          const dlg = document.getElementById('dr-dlg-a');
          const opener = document.querySelector('[data-testid=dr-open-a]');
          DialogRule.open(dlg, {opener, transient: false});
          DialogRule.closeTopmost();
          DialogRule.open(dlg, {opener, transient: false});
          await new Promise((r) => setTimeout(r, 50));
          return {open: dlg.open, depth: DialogRule.depth()};
        }"""
    )
    assert out == {"open": True, "depth": 1}
    dialog_page.keyboard.press("Escape")
    assert layers(dialog_page) == 0


@pytest.mark.parametrize("script", ["_probe_dialog_backdrop.js"])
def test_probe_dialog_script_runs_and_reports(dialog_page: Page, script: str) -> None:
    """The WebKitGTK probe's dialog setup script is exercised here so it cannot rot."""
    dialog_page.set_content("<!doctype html><html><head></head><body></body></html>")
    src = Path(__file__).with_name(script).read_text()
    assert dialog_page.evaluate(f"(function () {{ {src}\n;return true; }})()") is True
    report = dialog_page.evaluate("() => window.__probeReport")
    assert report["showModalOpened"] is True
    assert report["literalControl"] in ("rgb(1, 2, 3)", "", "rgba(0, 0, 0, 0)")
    if not report["unverifiable"]:
        assert report["backdropMatchesToken"] is True, report

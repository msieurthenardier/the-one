# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""The DD8 dialog-rule checks (M25 F1 L2) run against the REAL ``App.ui.modal`` and the
real ``components.css`` / ``tokens.css`` in Chromium and WebKit (M25 F2 L2, AC4).

The adapter builds the F1 fixture contract with the real wrapper: dialogs are created on
open and removed on close, ids come through the modal's ``id`` option, and fixture bodies
(buttons inside modal A) are passed as Node bodies. ``backdrop_css`` is empty because the
app ships the ``::backdrop`` rule; ``backdrop_token`` is ``--scrim``.
Falls in the ``shared`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._dialog_rule_checks import (
    FIXTURE_STYLE,
    TRANSIENT_OPENERS,
    DialogAdapter,
    check_backdrop_clicks,
    check_backdrop_colour,
    check_focus_restore,
    check_inertness,
    check_programmatic_confirm,
    check_stacked_escape,
)
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

SETUP_JS = """() => {
  document.documentElement.setAttribute('data-theme', 'dark');
  window.__outsideClicks = 0;
  window.__drStack = [];
  const body = document.body;
  const mk = (text, testid) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = text; b.setAttribute('data-testid', testid);
    return b;
  };
  const openA = mk('Open A', 'dr-open-a');
  const openT = mk('Open chooser', 'dr-open-t');
  const outside = mk('Outside', 'dr-outside');
  outside.addEventListener('click', () => { window.__outsideClicks += 1; });
  body.appendChild(openA); body.appendChild(openT); body.appendChild(outside);

  const track = (name, modal) => ({
    open(opener) { window.__drStack.push(modal); modal.open(opener); },
  });
  const make = (name, opts) => {
    const modal = App.ui.modal(Object.assign({
      id: 'dr-dlg-' + name,
      testid: 'dr-dialog-' + name,
      onClose: () => { window.__drStack = window.__drStack.filter((m) => m !== modal); },
    }, opts));
    return modal;
  };
  const p = (text) => { const e = document.createElement('p'); e.textContent = text; return e; };
  const wrap = (children) => { const d = document.createElement('div'); children.forEach((c) => d.appendChild(c)); return d; };

  const modalB = make('b', {title: 'Dialog B', body: wrap([p('Dialog B'), mk('OK', 'dr-b-ok')])});
  const openB = mk('Open B', 'dr-open-b');
  const modalA = make('a', {title: 'Dialog A', body: wrap([p('Dialog A'), openB, mk('Other', 'dr-a-other')])});
  const modalT = make('t', {title: 'Chooser', dismissible: true, body: wrap([p('Chooser'), mk('Pick', 'dr-t-pick')])});
  const modalC = make('confirm', {title: 'Confirm', body: wrap([p('Sure?'), mk('Yes', 'dr-confirm-yes'), mk('No', 'dr-confirm-no')])});
  const opening = (modal) => (ev) => { window.__drStack.push(modal); modal.open(ev.currentTarget); };
  openA.addEventListener('click', opening(modalA));
  openB.addEventListener('click', opening(modalB));
  openT.addEventListener('click', opening(modalT));
  window.__drConfirm = modalC;
  return true;
}"""


def _setup(page: Page) -> None:
    load_harness(page, "dark")
    page.add_style_tag(content=FIXTURE_STYLE)
    page.evaluate(SETUP_JS)


def _open(page: Page, opener_testid: str, transient: bool = False, via: str = "mouse") -> None:
    assert (opener_testid in TRANSIENT_OPENERS) == transient, (
        f"{opener_testid} transient mismatch (transient={transient})"
    )
    target = page.locator(f"[data-testid={opener_testid}]")
    if via == "keyboard":
        target.focus()
        page.keyboard.press("Enter")
    else:
        target.click()


def _open_confirm(page: Page) -> None:
    page.evaluate(
        "() => { window.__drStack.push(window.__drConfirm);"
        " window.__drConfirm.open(document.querySelector('[data-testid=dr-open-a]')); return true; }"
    )


MODAL = DialogAdapter(
    name="App.ui.modal",
    setup=_setup,
    open=_open,
    close_topmost=lambda page: page.evaluate(
        "() => { const m = window.__drStack[window.__drStack.length - 1]; if (m) m.close(); return true; }"
    ),
    open_confirm_programmatic=_open_confirm,
    backdrop_css="",
    backdrop_token="--scrim",
)


@pytest.fixture
def dialog_page(engine_page: Page) -> Page:
    engine_page.set_viewport_size({"width": 1024, "height": 768})
    return engine_page


def _report(record_property, result: dict) -> None:
    record_property(f"modal-{result['check']}", str(result))
    print(f"[modal-rule] {result}")


def test_a_stacked_escape_peels_one_layer_each(dialog_page: Page, record_property) -> None:
    _report(record_property, check_stacked_escape(dialog_page, MODAL))


def test_b_programmatic_confirm_over_modal(dialog_page: Page, record_property) -> None:
    _report(record_property, check_programmatic_confirm(dialog_page, MODAL))


@pytest.mark.parametrize("via", ["mouse", "keyboard"])
def test_c_focus_restore(dialog_page: Page, record_property, via: str) -> None:
    _report(record_property, check_focus_restore(dialog_page, MODAL, via))


def test_d_backdrop_clicks(dialog_page: Page, record_property) -> None:
    _report(record_property, check_backdrop_clicks(dialog_page, MODAL))


def test_e_inertness(dialog_page: Page, record_property) -> None:
    result = check_inertness(dialog_page, MODAL)
    _report(record_property, result)
    assert result["tab_reaches_buttons"], result


def test_f_backdrop_colour(dialog_page: Page, record_property) -> None:
    result = check_backdrop_colour(dialog_page, MODAL)
    _report(record_property, result)
    if result["status"] == "unverifiable":
        name = dialog_page.context.browser.browser_type.name
        pytest.xfail(f"[{name}] backdrop colour unverifiable: {result['reason']}")

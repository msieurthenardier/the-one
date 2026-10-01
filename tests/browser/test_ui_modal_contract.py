# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Engine-parametrized contract tests for ``App.ui.modal`` (M25 F2 L2, DD6/DD8): the
native-``<dialog>`` modal. Keyboard and mouse steps use real ``keyboard.press`` / ``click``.
Every test runs in Chromium and WebKit. Falls in the ``shared`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._dialog_rule_checks import layers
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

MOUNT_JS = """() => {
  document.documentElement.setAttribute('data-theme', 'dark');
  window.__log = [];
  const main = document.createElement('main');
  main.id = 'main-content'; main.setAttribute('tabindex', '-1');
  document.body.appendChild(main);
  const opener = document.createElement('button');
  opener.type = 'button'; opener.textContent = 'Opener'; opener.setAttribute('data-testid', 'opener');
  main.appendChild(opener);
  window.__opener = opener;
  window.__mk = (extra) => {
    const m = App.ui.modal(Object.assign({
      title: 'Sample',
      body: 'Body text that is not focusable.',
      testid: 'm-dialog',
      cancelValue: 'cancelled',
      actions: [
        {label: 'Stay', variant: 'secondary', value: 'stay', testid: 'm-stay'},
        {label: 'Go', variant: 'primary', value: 'go', testid: 'm-go'},
      ],
      onClose: (v) => {
        const d = document.querySelector('[data-testid=m-dialog]');
        window.__log.push({
          value: v,
          dialogsInDom: document.querySelectorAll('dialog').length,
          openerFocused: document.activeElement === window.__opener,
        });
      },
    }, extra || {}));
    return m;
  };
  return true;
}"""


def _mount(page: Page) -> None:
    page.set_viewport_size({"width": 1024, "height": 768})
    load_harness(page, "dark")
    page.evaluate(MOUNT_JS)


def _open(page: Page, extra: str = "null") -> None:
    page.evaluate(
        f"() => {{ window.__m = window.__mk({extra}); window.__m.open(window.__opener); return true; }}"
    )


def _active(page: Page) -> str | None:
    return page.evaluate(
        "() => document.activeElement && (document.activeElement.dataset.testid || document.activeElement.tagName)"
    )


def _log(page: Page) -> list:
    return page.evaluate("() => window.__log")


# ── Structure and attributes (AC1) ─────────────────────────────────────────


def test_structure_and_aria(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    out = p.evaluate(
        """() => {
          const d = document.querySelector('dialog');
          const card = d.querySelector('.modal-dialog');
          const title = d.querySelector('h2.modal-dialog-title');
          const msg = d.querySelector('.modal-dialog-message');
          return {
            cls: d.className, role: d.getAttribute('role'), modal: d.getAttribute('aria-modal'),
            tag: d.tagName, testid: d.dataset.testid, open: d.open, isModal: d.matches(':modal'),
            labelledby: d.getAttribute('aria-labelledby') === title.id,
            describedby: d.getAttribute('aria-describedby') === msg.id,
            cardParent: card.parentNode === d, cardTab: card.getAttribute('tabindex'),
            actions: Array.from(d.querySelectorAll('.modal-actions button')).map(b => [b.textContent, b.className, b.dataset.testid]),
            actionsClass: d.querySelector('.modal-actions').className,
            keys: Object.keys(window.__m).sort().join(','), isOpen: window.__m.isOpen(),
            elIsDialog: window.__m.el === d,
          };
        }"""
    )
    assert out["tag"] == "DIALOG" and out["cls"] == "modal-overlay"
    assert (out["role"], out["modal"], out["testid"]) == ("dialog", "true", "m-dialog")
    assert out["open"] and out["isModal"]
    assert out["labelledby"] and out["describedby"] and out["cardParent"]
    assert out["cardTab"] == "-1"
    assert out["actions"] == [
        ["Stay", "btn-outlined-primary", "m-stay"],
        ["Go", "btn-filled-primary", "m-go"],
    ]
    assert "modal-actions" in out["actionsClass"]
    assert out["keys"] == "close,el,isOpen,open" and out["isOpen"] and out["elIsDialog"]


def test_node_body_and_a11y(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(
        p,
        "{body: (() => { const d = document.createElement('div'); d.textContent = 'node body'; return d; })(), id: 'my-id'}",
    )
    assert p.evaluate("() => document.querySelector('dialog').id") == "my-id"
    assert p.evaluate("() => document.querySelector('.modal-dialog-message').tagName") == "DIV"
    assert_controls_labelled_and_described(p, "dialog")


def test_a11y_resolver_over_open_modal(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    assert_controls_labelled_and_described(p, "dialog")


# ── Focus ──────────────────────────────────────────────────────────────────


def test_focus_on_open_autofocus_then_first_action_then_card(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    assert _active(p) == "m-stay"
    p.keyboard.press("Escape")
    _open(
        p,
        "{actions: [{label: 'A', value: 'a', testid: 'm-a'}, {label: 'B', value: 'b', testid: 'm-b', autofocus: true}]}",
    )
    assert _active(p) == "m-b"
    p.keyboard.press("Escape")
    _open(p, "{actions: []}")
    assert p.evaluate("() => document.activeElement.classList.contains('modal-dialog')")
    p.keyboard.press("Escape")


@pytest.mark.parametrize("via", ["mouse", "keyboard"])
def test_focus_restore_to_opener(engine_page: Page, via: str) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(
        "() => window.__opener.addEventListener('click', (e) => { window.__m = window.__mk(); window.__m.open(e.currentTarget); })"
    )
    if via == "keyboard":
        p.get_by_test_id("opener").focus()
        p.keyboard.press("Enter")
    else:
        p.get_by_test_id("opener").click()
    assert layers(p) == 1
    p.keyboard.press("Escape")
    assert layers(p) == 0
    assert _active(p) == "opener"


def test_opener_removed_falls_back_to_main_content(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.evaluate("() => window.__opener.remove()")
    p.keyboard.press("Escape")
    assert p.evaluate("() => document.activeElement.id") == "main-content"


# ── Escape and close paths (AC2) ────────────────────────────────────────────


def test_escape_closes_with_cancel_value_and_removes_dom(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.keyboard.press("Escape")
    assert layers(p) == 0
    assert p.evaluate("() => document.querySelectorAll('dialog').length") == 0
    assert p.evaluate("() => window.__m.el") is None and not p.evaluate("() => window.__m.isOpen()")
    p.wait_for_timeout(50)
    assert _log(p) == [{"value": "cancelled", "dialogsInDom": 0, "openerFocused": True}]


def test_escape_with_focus_on_body(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.evaluate("() => document.activeElement.blur()")
    p.keyboard.press("Escape")
    p.wait_for_timeout(50)
    assert layers(p) == 0
    log = _log(p)
    assert len(log) == 1 and log[0]["value"] == "cancelled"


def test_escape_with_focus_on_card_text(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.locator(".modal-dialog-message").click()  # non-focusable text: the card takes focus
    assert p.evaluate("() => !!document.activeElement.closest('dialog')")
    p.keyboard.press("Escape")
    p.wait_for_timeout(50)
    assert layers(p) == 0 and len(_log(p)) == 1


def test_action_click_reports_its_value(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.get_by_test_id("m-go").click()
    assert layers(p) == 0
    assert [e["value"] for e in _log(p)] == ["go"]


def test_programmatic_close_reports_result_once(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.evaluate("() => { window.__m.close('done'); window.__m.close('again'); return true; }")
    p.wait_for_timeout(50)
    assert [e["value"] for e in _log(p)] == ["done"]
    assert layers(p) == 0


def test_external_dialog_close_runs_cancel_path_once(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.evaluate("() => document.querySelector('dialog').close()")
    p.wait_for_timeout(100)
    log = _log(p)
    assert log == [{"value": "cancelled", "dialogsInDom": 0, "openerFocused": True}]
    assert p.evaluate("() => document.querySelectorAll('dialog').length") == 0


def test_stale_close_on_reopen_is_ignored(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """async () => {
          const m = window.__mk();
          m.open(window.__opener);
          m.close('first');
          m.open(window.__opener);
          await new Promise((r) => setTimeout(r, 80));
          return {open: m.isOpen(), dialogs: document.querySelectorAll('dialog[open]').length,
                  log: window.__log.map((e) => e.value)};
        }"""
    )
    assert out == {"open": True, "dialogs": 1, "log": ["first"]}
    p.keyboard.press("Escape")
    p.wait_for_timeout(50)
    assert _log(p)[-1]["value"] == "cancelled" and len(_log(p)) == 2


def test_throwing_on_close_leaves_no_dangling_dialog(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const m = window.__mk({onClose: () => { throw new Error('boom'); }});
          m.open(window.__opener);
          let err = '';
          try { m.close('x'); } catch (e) { err = e.message; }
          return {err, dialogs: document.querySelectorAll('dialog').length,
                  focused: document.activeElement === window.__opener};
        }"""
    )
    assert out == {"err": "boom", "dialogs": 0, "focused": True}


# ── Stacking ───────────────────────────────────────────────────────────────


def test_stacked_modals_peel_one_layer_per_escape(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(
        """() => {
          window.__a = window.__mk({testid: 'm-a', onClose: (v) => window.__log.push({a: v})});
          window.__b = window.__mk({testid: 'm-b', onClose: (v) => window.__log.push({b: v})});
          window.__a.open(window.__opener);
          window.__b.open(document.querySelector('[data-testid=m-a] [data-testid=m-go]'));
          return true;
        }"""
    )
    assert layers(p) == 2
    p.keyboard.press("Escape")
    assert layers(p) == 1
    assert p.evaluate("() => document.querySelector('dialog[open]').dataset.testid") == "m-a"
    assert _active(p) == "m-go"
    p.keyboard.press("Escape")
    assert layers(p) == 0
    assert _log(p) == [{"b": "cancelled"}, {"a": "cancelled"}]


def test_closing_bottom_modal_leaves_top_open(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(
        """() => {
          window.__a = window.__mk({testid: 'm-a'});
          window.__b = window.__mk({testid: 'm-b'});
          window.__a.open(window.__opener);
          window.__b.open(window.__opener);
          window.__a.close('a');
          return true;
        }"""
    )
    assert layers(p) == 1
    assert p.evaluate("() => document.querySelector('dialog[open]').dataset.testid") == "m-b"
    p.keyboard.press("Escape")
    assert layers(p) == 0


# ── Tab wrap ───────────────────────────────────────────────────────────────


def test_tab_wraps_forward_and_shift_tab_backward(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    assert _active(p) == "m-stay"
    p.keyboard.press("Tab")
    assert _active(p) == "m-go"
    p.keyboard.press("Tab")
    assert _active(p) == "m-stay"
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "m-go"
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "m-stay"


def test_tab_from_card_enters_at_the_ends_deterministically(engine_page: Page) -> None:
    """Focus on the card (a click on non-focusable text) is outside the focusable list:
    the <dialog> and the card are excluded, so Tab enters at the first and Shift+Tab at
    the last, in both engines."""
    p = engine_page
    _mount(p)
    _open(p)
    p.locator(".modal-dialog-message").click()
    assert p.evaluate("() => document.activeElement.classList.contains('modal-dialog')")
    p.keyboard.press("Tab")
    assert _active(p) == "m-stay"
    p.locator(".modal-dialog-message").click()
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "m-go"


def test_enter_activates_the_focused_action_natively(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.keyboard.press("Enter")  # default focus is the first action
    assert [e["value"] for e in _log(p)] == ["stay"]
    _open(p)
    p.keyboard.press("Tab")
    p.keyboard.press("Enter")
    assert [e["value"] for e in _log(p)] == ["stay", "go"]


# ── Backdrop clicks ────────────────────────────────────────────────────────


def test_backdrop_click_closes_only_when_dismissible(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    p.mouse.click(5, 5)
    assert layers(p) == 1
    p.keyboard.press("Escape")
    _open(p, "{dismissible: true}")
    p.mouse.click(5, 5)
    assert layers(p) == 0
    assert [e["value"] for e in _log(p)] == ["cancelled", "cancelled"]


def test_card_click_does_not_dismiss(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p, "{dismissible: true}")
    p.locator(".modal-dialog-message").click()
    assert layers(p) == 1
    p.keyboard.press("Escape")


def test_drag_from_card_to_backdrop_does_not_close(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p, "{dismissible: true}")
    box = p.locator(".modal-dialog-message").bounding_box()
    assert box is not None
    p.mouse.move(box["x"] + 10, box["y"] + 5)
    p.mouse.down()
    p.mouse.move(5, 5)
    p.mouse.up()
    assert layers(p) == 1
    p.keyboard.press("Escape")
    expect(p.locator("dialog[open]")).to_have_count(0)


def test_probe_modal_script_opens_a_modal(engine_page: Page) -> None:
    """The WebKitGTK probe's modal setup script is exercised here so it cannot rot."""
    from pathlib import Path

    p = engine_page
    load_harness(p, "dark")
    p.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
    src = Path(__file__).with_name("_probe_modal.js").read_text()
    assert p.evaluate(f"(function () {{ {src}\n;return true; }})()") is True
    report = p.evaluate("() => window.__probeReport")
    assert report["open"] and report["isModal"] and report["focusInside"], report
    assert_controls_labelled_and_described(p, "dialog[open]")

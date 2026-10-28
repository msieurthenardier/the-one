# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Engine-parametrized contract tests for ``App.ui.modal`` (M25 F2 L2, DD6/DD8): the
native-``<dialog>`` modal. Keyboard and mouse steps use real ``keyboard.press`` / ``click``.
Every test runs in Chromium and WebKit. Falls in the ``contracts`` browser lane.

M25 F4 L1 (DD14) adds the chooser options: ``width``, ``top``, ``initialFocus``,
``closeButton``, ``footer`` and ``layout: 'chooser'``; M25 F4 L7 adds ``ariaLabel``
(a modal with no title and no header row) and ``App.ui.modal.anyOpen()`` (the tests
at the end).
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._dialog_rule_checks import layers
from browser._ui_engines import STATIC_DIR, load_harness
from browser.design_tokens import DARK
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


# ── Chooser options (M25 F4 L1, DD14) ─────────────────────────────────────────

# A chooser body: an input then two rows of buttons, so "the first focusable in
# the body" is the input, never the header's close button.
CHOOSER_JS = """(extra) => {
  const body = document.createElement('div');
  body.setAttribute('data-testid', 'ch-body');
  const input = document.createElement('input');
  input.setAttribute('aria-label', 'Find'); input.setAttribute('data-testid', 'ch-input');
  const b1 = document.createElement('button'); b1.textContent = 'Row one'; b1.setAttribute('data-testid', 'ch-row1');
  const b2 = document.createElement('button'); b2.textContent = 'Row two'; b2.setAttribute('data-testid', 'ch-row2');
  body.append(input, b1, b2);
  window.__chBody = body; window.__chInput = input; window.__chRow2 = b2;
  // focusRow2: initialFocus is the body's last row (built here, so the caller
  // cannot pass the node itself).
  if (extra && extra.focusRow2) { delete extra.focusRow2; extra.initialFocus = b2; }
  const footer = document.createDocumentFragment();
  const left = document.createElement('span'); left.textContent = 'Picking starts a chat';
  footer.append(left);
  window.__m = window.__mk(Object.assign({
    title: 'Start a chat with', layout: 'chooser', body, footer, footerEnd: 'Enter to start', actions: [],
    closeButton: {label: 'Esc', ariaLabel: 'Close (Esc)', testid: 'ch-close'},
  }, extra || {}));
  window.__m.open(window.__opener);
  return true;
}"""


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


def _chooser(page: Page, extra: str = "null") -> None:
    page.evaluate(f"({CHOOSER_JS})({extra})")


def test_chooser_layout_structure_and_no_describedby(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _chooser(p)
    out = p.evaluate(
        """() => {
          const d = document.querySelector('dialog');
          const card = d.querySelector('.modal-dialog');
          const header = card.querySelector('.modal-dialog-header');
          const title = header.querySelector('h2');
          const close = header.querySelector('[data-testid=ch-close]');
          const body = card.querySelector('.modal-dialog-body');
          const footer = card.querySelector('.modal-dialog-footer');
          const cs = getComputedStyle(card), hs = getComputedStyle(header), fs = getComputedStyle(footer);
          const cb = card.getBoundingClientRect(), bb = body.getBoundingClientRect();
          const end = footer.querySelector('.modal-dialog-footer-end').getBoundingClientRect();
          return {
            order: Array.from(card.children).map((n) => n.className),
            labelledby: d.getAttribute('aria-labelledby') === title.id, title: title.textContent,
            describedby: d.hasAttribute('aria-describedby'),
            actions: card.querySelectorAll('.modal-actions').length,
            closeClass: close.className, closeName: close.getAttribute('aria-label'), closeText: close.textContent,
            closeLast: header.lastElementChild === close,
            cardPad: cs.padding, cardClass: card.className,
            headerPad: hs.padding, headerDisplay: hs.display,
            bodyFullBleed: Math.abs(bb.left - cb.left - 1) <= 0.5 && Math.abs(cb.right - bb.right - 1) <= 0.5,
            bodyHolds: body.firstElementChild === window.__chBody,
            footer: [fs.fontSize, fs.color, fs.borderTopWidth + ' ' + fs.borderTopStyle, fs.padding],
            footerItems: footer.children.length,
            endPushed: cb.right - end.right <= 22,
          };
        }"""
    )
    assert out["order"] == ["modal-dialog-header", "modal-dialog-body", "modal-dialog-footer"]
    assert out["labelledby"] is True and out["title"] == "Start a chat with"
    assert out["describedby"] is False  # the chooser never describes the dialog by its list
    assert out["actions"] == 0
    assert out["closeClass"] == "btn-ghost btn-sm" and out["closeLast"] is True
    assert (out["closeName"], out["closeText"]) == ("Close (Esc)", "Esc")
    assert out["cardPad"] == "0px" and "modal-dialog-chooser" in out["cardClass"]
    assert out["headerPad"] == "16px 20px 12px" and out["headerDisplay"] == "flex"
    assert out["bodyFullBleed"] is True and out["bodyHolds"] is True
    assert out["footer"][:3] == ["11px", _rgb(DARK["fg_muted"]), "1px solid"], out["footer"]
    assert out["footer"][3] == "10px 20px"
    assert (
        out["footerItems"] == 2 and out["endPushed"] is True
    )  # the fragment's items are the row's
    assert_controls_labelled_and_described(p, "dialog")


def test_chooser_default_focus_is_the_body_never_the_close_button(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _chooser(p)
    assert _active(p) == "ch-input"
    p.keyboard.press("Escape")
    # A plain (non-chooser) modal with a close button and a Node body holding an
    # input and no actions: the default is still the body's input.
    p.evaluate(
        """() => {
          const body = document.createElement('div');
          const input = document.createElement('input'); input.setAttribute('aria-label', 'Name');
          input.setAttribute('data-testid', 'plain-input');
          body.appendChild(input);
          window.__m = window.__mk({body, actions: [], closeButton: {label: 'Esc', ariaLabel: 'Close (Esc)', testid: 'plain-close'}});
          window.__m.open(window.__opener);
        }"""
    )
    assert _active(p) == "plain-input"
    p.keyboard.press("Escape")
    # With a close button in play the body comes first even when there are
    # actions (they would win in the usual order).
    p.evaluate(
        """() => {
          const body = document.createElement('div');
          const input = document.createElement('input'); input.setAttribute('aria-label', 'Name');
          input.setAttribute('data-testid', 'acts-input');
          body.appendChild(input);
          window.__m = window.__mk({body, closeButton: {label: 'Esc', ariaLabel: 'Close (Esc)', testid: 'acts-close'}});
          window.__m.open(window.__opener);
        }"""
    )
    assert _active(p) == "acts-input"  # not the first action (m-stay)
    p.keyboard.press("Escape")
    # With only the close button focusable, the usual order lands on it.
    p.evaluate(
        "() => { window.__m = window.__mk({actions: [], closeButton: {label: 'Esc', ariaLabel: 'Close (Esc)', testid: 'only-close'}}); window.__m.open(window.__opener); }"
    )
    assert _active(p) == "only-close"


def test_initial_focus_focuses_the_given_node(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(
        """() => {
          const body = document.createElement('div');
          const b = document.createElement('button'); b.textContent = 'Second'; b.setAttribute('data-testid', 'if-target');
          const a = document.createElement('button'); a.textContent = 'First';
          body.append(a, b);
          window.__m = window.__mk({body, initialFocus: b});
          window.__m.open(window.__opener);
        }"""
    )
    assert _active(p) == "if-target"  # not the first action (m-stay)
    p.keyboard.press("Escape")
    # A node that is not inside the card falls back to the usual order.
    p.evaluate(
        "() => { window.__m = window.__mk({initialFocus: window.__opener}); window.__m.open(window.__opener); }"
    )
    assert _active(p) == "m-stay"
    p.keyboard.press("Escape")
    _chooser(p, "{focusRow2: true}")
    assert _active(p) == "ch-row2"


def test_close_button_closes_with_cancel_value_and_restores_focus(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _chooser(p)
    p.get_by_test_id("ch-close").click()
    assert layers(p) == 0
    p.wait_for_timeout(50)
    assert _log(p) == [{"value": "cancelled", "dialogsInDom": 0, "openerFocused": True}]
    assert _active(p) == "opener"


def test_close_button_takes_part_in_the_tab_wrap(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _chooser(p)
    assert _active(p) == "ch-input"
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "ch-close"  # the header's close button comes first in the card
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "ch-row2"  # wraps to the last
    p.keyboard.press("Tab")
    assert _active(p) == "ch-close"  # and forward wraps back to the close button
    p.keyboard.press("Enter")
    assert layers(p) == 0 and _active(p) == "opener"


def test_width_and_top_place_the_card(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _chooser(p, "{width: 640, top: 72}")
    box = p.evaluate(
        "() => { const r = document.querySelector('dialog .modal-dialog').getBoundingClientRect(); return [r.width, r.top, r.left]; }"
    )
    assert abs(box[0] - 640) <= 0.5 and abs(box[1] - 72) <= 0.5, box
    assert abs(box[2] - (1024 - 640) / 2) <= 0.5, box  # still centred horizontally
    p.keyboard.press("Escape")
    # A narrow viewport: the card stays inside the viewport minus 32px.
    p.set_viewport_size({"width": 560, "height": 700})
    _chooser(p, "{width: 640, top: 72}")
    narrow = p.evaluate(
        "() => { const r = document.querySelector('dialog .modal-dialog').getBoundingClientRect(); return [r.width, r.left]; }"
    )
    assert abs(narrow[0] - (560 - 32)) <= 0.5 and abs(narrow[1] - 16) <= 0.5, narrow


def test_without_the_new_options_a_modal_is_unchanged(engine_page: Page) -> None:
    """No new option: the 24px card padding, aria-describedby, a vertically
    centred 480px card, no header row, no inline style on the card."""
    p = engine_page
    _mount(p)
    _open(p)
    out = p.evaluate(
        """() => {
          const d = document.querySelector('dialog'), card = d.querySelector('.modal-dialog');
          const r = card.getBoundingClientRect();
          return {pad: getComputedStyle(card).padding, described: d.hasAttribute('aria-describedby'),
                  style: card.getAttribute('style'), header: card.querySelectorAll('.modal-dialog-header').length,
                  first: card.firstElementChild.tagName, w: r.width,
                  centred: Math.abs((r.top + r.bottom) / 2 - window.innerHeight / 2) <= 1};
        }"""
    )
    assert out == {
        "pad": "24px",
        "described": True,
        "style": None,
        "header": 0,
        "first": "H2",
        "w": 480,
        "centred": True,
    }


@pytest.mark.parametrize(
    ("opts", "message"),
    [
        ("{layout: 'drawer'}", 'App.ui.modal: unknown layout "drawer"'),
        (
            "{layout: 'chooser', body: document.createElement('div')}",
            "App.ui.modal: the chooser layout has no actions",
        ),
        (
            "{layout: 'chooser', actions: [], body: 'text'}",
            "App.ui.modal: the chooser layout needs a Node body",
        ),
        ("{footer: 'text'}", "App.ui.modal: footer must be a Node"),
    ],
)
def test_chooser_option_errors(engine_page: Page, opts: str, message: str) -> None:
    p = engine_page
    _mount(p)
    got = p.evaluate(
        f"() => {{ try {{ window.__mk({opts}); return ''; }} catch (e) {{ return e.message; }} }}"
    )
    assert got == message


def test_a_fragment_footer_survives_a_reopen(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _chooser(p)
    p.keyboard.press("Escape")
    p.evaluate("() => { window.__m.open(window.__opener); }")
    assert (
        p.evaluate("() => document.querySelector('dialog .modal-dialog-footer').children.length")
        == 2
    )


# ── ariaLabel and anyOpen() (M25 F4 L7, DD14) ─────────────────────────────────

# A chooser named by ariaLabel: no title, no header row; its body holds an input
# and the body's OWN "Esc" button, which calls the controller's close().
LABELLED_JS = """(extra) => {
  const body = document.createElement('div');
  body.setAttribute('data-testid', 'al-body');
  const input = document.createElement('input');
  input.setAttribute('aria-label', 'Jump to'); input.setAttribute('data-testid', 'al-input');
  const esc = App.ui.button({label: 'Esc', ariaLabel: 'Close (Esc)', variant: 'ghost', size: 'sm',
                             testid: 'al-close', onClick: () => window.__m.close()});
  body.append(input, esc);
  window.__m = window.__mk(Object.assign({
    title: undefined, ariaLabel: 'Jump to', layout: 'chooser', body, actions: [], dismissible: true,
    initialFocus: input,
  }, extra || {}));
  window.__m.open(window.__opener);
  return true;
}"""


def _labelled(page: Page, extra: str = "null") -> None:
    page.evaluate(f"({LABELLED_JS})({extra})")


def test_aria_label_names_a_modal_with_no_title_and_no_header(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _labelled(p)
    out = p.evaluate(
        """() => {
          const d = document.querySelector('dialog'), card = d.querySelector('.modal-dialog');
          return {
            label: d.getAttribute('aria-label'), labelledby: d.hasAttribute('aria-labelledby'),
            describedby: d.hasAttribute('aria-describedby'),
            h2: d.querySelectorAll('h2').length, headings: d.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]').length,
            header: d.querySelectorAll('.modal-dialog-header').length,
            title: d.querySelectorAll('.modal-dialog-title').length,
            first: card.firstElementChild.className, kids: Array.from(card.children).map((c) => c.className),
            role: d.getAttribute('role'), modal: d.getAttribute('aria-modal'),
          };
        }"""
    )
    assert out["label"] == "Jump to" and out["labelledby"] is False
    assert out["describedby"] is False  # still a chooser: never described by its list
    assert out["h2"] == 0 and out["headings"] == 0 and out["header"] == 0 and out["title"] == 0
    assert out["first"] == "modal-dialog-body" and out["kids"] == ["modal-dialog-body"]
    assert (out["role"], out["modal"]) == ("dialog", "true")
    expect(p.get_by_role("dialog", name="Jump to")).to_have_count(1)
    assert_controls_labelled_and_described(p, "dialog")
    assert _active(p) == "al-input"


def test_aria_label_body_close_button_is_in_the_tab_wrap_and_closes(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _labelled(p)
    assert _active(p) == "al-input"
    p.keyboard.press("Tab")
    assert _active(p) == "al-close"
    p.keyboard.press("Tab")
    assert _active(p) == "al-input"  # wraps
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "al-close"
    p.keyboard.press("Enter")  # the body's own button calls controller.close()
    assert layers(p) == 0
    p.wait_for_timeout(50)
    assert _log(p) == [{"value": None, "dialogsInDom": 0, "openerFocused": True}]
    assert _active(p) == "opener"
    # Escape still closes it, focus back at the opener.
    _labelled(p)
    p.keyboard.press("Escape")
    assert layers(p) == 0 and _active(p) == "opener"


def test_aria_label_on_a_plain_modal_keeps_its_description(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p, "{title: null, ariaLabel: 'Quick question'}")
    out = p.evaluate(
        """() => { const d = document.querySelector('dialog'), msg = d.querySelector('.modal-dialog-message');
                   return {label: d.getAttribute('aria-label'), labelledby: d.hasAttribute('aria-labelledby'),
                           describedby: d.getAttribute('aria-describedby') === msg.id, h2: d.querySelectorAll('h2').length,
                           first: d.querySelector('.modal-dialog').firstElementChild.className}; }"""
    )
    assert out == {
        "label": "Quick question",
        "labelledby": False,
        "describedby": True,
        "h2": 0,
        "first": "modal-dialog-message",
    }
    assert_controls_labelled_and_described(p, "dialog")


@pytest.mark.parametrize(
    ("opts", "message"),
    [
        (
            "{ariaLabel: 'Jump to'}",  # __mk's default title is 'Sample'
            "App.ui.modal: ariaLabel names a modal with no title (pass one, not both)",
        ),
        (
            "{title: undefined, ariaLabel: 'Jump to', closeButton: {label: 'Esc', ariaLabel: 'Close (Esc)'}}",
            "App.ui.modal: a modal named by ariaLabel has no header for a closeButton",
        ),
        ("{title: undefined, ariaLabel: ''}", "App.ui.modal: ariaLabel must be a non-empty string"),
        ("{title: undefined, ariaLabel: 5}", "App.ui.modal: ariaLabel must be a non-empty string"),
    ],
)
def test_aria_label_option_errors(engine_page: Page, opts: str, message: str) -> None:
    p = engine_page
    _mount(p)
    got = p.evaluate(
        f"() => {{ try {{ window.__mk({opts}); return ''; }} catch (e) {{ return e.message; }} }}"
    )
    assert got == message


def _any_open(page: Page) -> bool:
    return page.evaluate("() => App.ui.modal.anyOpen()")


def test_any_open_tracks_every_open_modal_across_controllers(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    assert _any_open(p) is False
    p.evaluate(
        """() => { window.__a = window.__mk({testid: 'm-a'}); window.__b = window.__mk({testid: 'm-b'});
                    window.__a.open(window.__opener); return true; }"""
    )
    assert _any_open(p) is True
    p.evaluate("() => { window.__b.open(window.__opener); return true; }")
    assert _any_open(p) is True and layers(p) == 2
    p.evaluate("() => { window.__a.close('a'); return true; }")  # the bottom one
    assert _any_open(p) is True and layers(p) == 1
    p.keyboard.press("Escape")
    assert _any_open(p) is False and layers(p) == 0


def test_any_open_is_false_after_a_bypassed_close_event(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _open(p)
    assert _any_open(p) is True
    p.evaluate("() => document.querySelector('dialog').close()")  # bypasses the router
    p.wait_for_timeout(100)
    assert _log(p)[-1]["value"] == "cancelled"  # the close event ran finish once
    assert _any_open(p) is False
    # And after a throwing onClose (finish leaves the stack before onClose runs).
    p.evaluate(
        """() => { const m = window.__mk({onClose: () => { throw new Error('boom'); }});
                    m.open(window.__opener); try { m.close('x'); } catch (e) {} return true; }"""
    )
    assert _any_open(p) is False


def test_any_open_counts_the_confirm_dialog_adapter(engine_page: Page) -> None:
    """App.confirmDialog is an adapter over App.ui.modal, so the leave guard's
    confirm is in the same stack: no second source of truth."""
    p = engine_page
    _mount(p)
    p.add_script_tag(path=str(STATIC_DIR / "js" / "dialog.js"))
    assert _any_open(p) is False
    p.evaluate("() => { App.confirmDialog({opener: window.__opener}); return true; }")
    assert _any_open(p) is True and p.evaluate("() => App.confirmDialog.isOpen()") is True
    p.keyboard.press("Escape")  # Stay
    assert _any_open(p) is False and p.evaluate("() => App.confirmDialog.isOpen()") is False


# ── footerEnd (M31 F6 L03b): the node pushed to the footer's end, owned by the modal ──


def test_footer_end_is_the_last_item_with_and_without_footer(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    _chooser(p, "{footerEnd: 'Right side', footer: undefined}")
    out = p.evaluate(
        """() => { const f = document.querySelector('.modal-dialog-footer');
          const end = f.querySelector('.modal-dialog-footer-end'), r = f.getBoundingClientRect();
          return {items: Array.from(f.children).map((n) => n.className + ':' + n.textContent),
                  atEnd: Math.abs((end.getBoundingClientRect().right + parseFloat(getComputedStyle(f).paddingRight)) - r.right) <= 1,
                  left: end.getBoundingClientRect().left > r.left + r.width / 2}; }"""
    )
    assert out["items"] == ["modal-dialog-footer-end:Right side"], (
        out
    )  # only footerEnd: the row is created
    assert out["atEnd"] and out["left"], out
    # With a footer too: the footer's items first, the end node last.
    p.evaluate("() => window.__m.close()")
    _chooser(p, "{footerEnd: 'Enter to start'}")
    out = p.evaluate(
        """() => Array.from(document.querySelectorAll('dialog[open] .modal-dialog-footer')[0].children).map((n) => n.className || n.textContent)"""
    )
    assert out == ["Picking starts a chat", "modal-dialog-footer-end"], out


def test_footer_end_accepts_a_node_and_any_layout(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => { const n = document.createElement('b'); n.textContent = 'Node end';
          const m = window.__mk({footerEnd: n}); m.open(window.__opener);
          const f = document.querySelector('.modal-dialog-footer');
          const end = f && f.querySelector('.modal-dialog-footer-end');
          const bad = (() => { try { App.ui.modal({title: 'x', body: 'y', footerEnd: 5}); return ''; } catch (e) { return e.message; } })();
          return {html: end ? end.innerHTML : null, bad}; }"""
    )
    assert out["html"] == "<b>Node end</b>", out
    assert out["bad"] == "App.ui.modal: footerEnd must be a Node or a string", out

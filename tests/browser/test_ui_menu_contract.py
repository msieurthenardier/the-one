# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.menu`` (M25 F1 L5): the WAI-ARIA
menu button. Keyboard and mouse steps use real ``keyboard.press`` / ``click``.
Includes the DD8 menu-inside-dialog checks on the Leg 2 ``_dialog_rule.js`` harness.
Falls in the ``contracts`` browser lane; every test runs in Chromium and WebKit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._dialog_rule_checks import layers
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

HARNESS_JS = Path(__file__).with_name("_dialog_rule.js")

MOUNT_JS = """() => {
  window.__sel = [];
  const mk = (extra) => App.ui.menu(Object.assign({
    trigger: {label: 'Actions', testid: 'm-trigger'},
    testid: 'm-popup',
    items: [
      {label: 'Rename', testid: 'm-rename', onSelect: (i) => window.__sel.push(i.label)},
      {label: 'Locked', disabled: true, testid: 'm-locked', onSelect: (i) => window.__sel.push(i.label)},
      {label: 'Duplicate', icon: 'plus', testid: 'm-dup', onSelect: (i) => window.__sel.push(i.label)},
      {label: 'Delete', danger: true, testid: 'm-del', onSelect: (i) => window.__sel.push(i.label)},
    ],
  }, extra || {}));
  window.__mk = mk;
  const root = document.getElementById('harness-root');
  const before = document.createElement('button');
  before.textContent = 'Before'; before.setAttribute('data-testid', 'm-before');
  const after = document.createElement('button');
  after.textContent = 'After'; after.setAttribute('data-testid', 'm-after');
  const c = mk();
  window.__m = c;
  root.appendChild(before); root.appendChild(c.el); root.appendChild(after);
  return true;
}"""


def _mount(page: Page, theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(MOUNT_JS)


def _active(page: Page) -> str | None:
    return page.evaluate(
        "() => document.activeElement && (document.activeElement.dataset.testid || document.activeElement.tagName)"
    )


def _expanded(page: Page) -> str | None:
    return page.get_by_test_id("m-trigger").get_attribute("aria-expanded")


def _throws(page: Page, expr: str) -> str:
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


# ── API and markup ──────────────────────────────────────────────────────────


def test_menu_api_and_markup(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const c = window.__m, t = c.trigger, pop = c.popup;
          const items = Array.from(pop.children);
          return {
            keys: Object.keys(c).sort().join(','),
            wrap: c.el.className, wrapPos: getComputedStyle(c.el).position,
            popRole: pop.getAttribute('role'), popCls: pop.className, popHidden: pop.hidden,
            popInEl: c.el.contains(pop), popParent: pop.parentElement === c.el,
            idOk: /^ui-menu-\\d+$/.test(pop.id), controls: t.getAttribute('aria-controls') === pop.id,
            haspopup: t.getAttribute('aria-haspopup'), expanded: t.getAttribute('aria-expanded'),
            labelledby: pop.getAttribute('aria-labelledby') === t.id && !!t.id,
            tags: items.map((i) => i.tagName + '/' + i.type + '/' + i.getAttribute('role') + '/' + i.getAttribute('tabindex')),
            disabled: items.map((i) => i.getAttribute('aria-disabled') + '/' + i.hasAttribute('disabled')),
            danger: items.map((i) => i.classList.contains('ui-menu-item-danger')),
            icon: items.map((i) => !!i.querySelector('svg')),
            labels: items.map((i) => i.querySelector('span.ui-menu-item-label').textContent),
            tidT: t.getAttribute('data-testid'), tidP: pop.getAttribute('data-testid'),
            tidI: items.map((i) => i.getAttribute('data-testid')),
            isOpen: c.isOpen(),
          };
        }"""
    )
    assert out["keys"] == (
        "close,destroy,el,isOpen,open,popup,setItemChecked,setItemDisabled,setTriggerLabel,trigger"
    )
    assert out["wrap"] == "ui-menu-wrap" and out["wrapPos"] == "relative"
    assert out["popRole"] == "menu" and out["popHidden"] is True and out["popParent"] is True
    assert out["idOk"] and out["controls"] and out["labelledby"]
    assert out["haspopup"] == "menu" and out["expanded"] == "false" and out["isOpen"] is False
    assert out["tags"] == ["BUTTON/button/menuitem/-1"] * 4
    assert out["disabled"] == ["null/false", "true/false", "null/false", "null/false"]
    assert out["danger"] == [False, False, False, True]
    assert out["icon"] == [False, False, True, False]
    assert out["labels"] == ["Rename", "Locked", "Duplicate", "Delete"]
    assert out["tidT"] == "m-trigger" and out["tidP"] == "m-popup"
    assert out["tidI"] == ["m-rename", "m-locked", "m-dup", "m-del"]
    expect(p.get_by_test_id("m-popup")).to_be_hidden()


def test_menu_icon_only_trigger_labels_popup_by_aria_label(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const c = App.ui.menu({trigger: {iconOnly: true, icon: 'plus', ariaLabel: 'More actions'},
                                 items: [{label: 'One', onSelect: () => {}}], align: 'end'});
          document.getElementById('harness-root').appendChild(c.el);
          return {label: c.popup.getAttribute('aria-label'), lb: c.popup.hasAttribute('aria-labelledby'),
                  cls: c.popup.className};
        }"""
    )
    assert out == {"label": "More actions", "lb": False, "cls": "ui-menu ui-menu-align-end"}
    assert_controls_labelled_and_described(p, "#harness-root")


# ── checkable items, popupLabel, setTriggerLabel (sortie 21 HAT feature) ────

RADIO_JS = """() => {
  window.__sel = [];
  const c = App.ui.menu({
    trigger: {label: 'Current', testid: 'r-trigger'}, popupLabel: 'Pick one', testid: 'r-popup',
    items: [
      {label: 'One', checked: true, testid: 'r-one', onSelect: (i) => window.__sel.push(i.label)},
      {label: 'Two', checked: false, testid: 'r-two', onSelect: (i) => window.__sel.push(i.label)},
      {label: 'Three', checked: false, testid: 'r-three', onSelect: (i) => window.__sel.push(i.label)},
    ],
  });
  window.__r = c;
  document.getElementById('harness-root').appendChild(c.el);
  return true;
}"""


def test_checked_items_are_menuitemradio_and_popup_label_names_the_popup(
    engine_page: Page,
) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(RADIO_JS)
    out = p.evaluate(
        """() => {
          const c = window.__r, items = Array.from(c.popup.children);
          return {
            roles: items.map((i) => i.getAttribute('role') + '/' + i.getAttribute('aria-checked') + '/' + i.getAttribute('tabindex')),
            label: c.popup.getAttribute('aria-label'), lb: c.popup.hasAttribute('aria-labelledby'),
            // a plain menu on the same page is unchanged
            plain: Array.from(window.__m.popup.children).map((i) => i.getAttribute('role') + '/' + i.hasAttribute('aria-checked')),
            plainLb: window.__m.popup.hasAttribute('aria-labelledby'),
          };
        }"""
    )
    assert out["roles"] == ["menuitemradio/true/-1", "menuitemradio/false/-1", "menuitemradio/false/-1"]
    assert out["label"] == "Pick one" and out["lb"] is False
    assert out["plain"] == ["menuitem/false"] * 4 and out["plainLb"] is True
    expect(p.get_by_role("button", name="Current")).to_have_count(1)


def test_set_item_checked_and_trigger_label(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(RADIO_JS)
    p.evaluate("() => { window.__r.setItemChecked(0, false); window.__r.setItemChecked(2, true); window.__r.setTriggerLabel('Three'); }")
    assert p.evaluate(
        "() => Array.from(window.__r.popup.children).map((i) => i.getAttribute('aria-checked'))"
    ) == ["false", "false", "true"]
    expect(p.get_by_test_id("r-trigger")).to_have_text("Three")
    # A plain item and an unknown index are refused.
    assert "not a checkable" in _throws(p, "window.__m.setItemChecked(0, true)")
    assert "no item at index" in _throws(p, "window.__r.setItemChecked(9, true)")


def test_checked_menu_keyboard_escape_and_choose(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(RADIO_JS)
    p.get_by_test_id("r-trigger").focus()
    p.keyboard.press("ArrowDown")  # opens, focus on the first radio item
    assert _active(p) == "r-one"
    p.keyboard.press("ArrowDown")
    assert _active(p) == "r-two"
    p.keyboard.press("End")
    assert _active(p) == "r-three"
    p.keyboard.press("ArrowDown")  # wraps
    assert _active(p) == "r-one"
    # Roving tabindex keeps every radio item out of the tab order.
    assert p.evaluate(
        "() => Array.from(window.__r.popup.children).map((i) => i.getAttribute('tabindex'))"
    ) == ["-1", "-1", "-1"]
    p.keyboard.press("Escape")
    assert p.evaluate("() => window.__r.isOpen()") is False
    assert _active(p) == "r-trigger"
    p.keyboard.press("Enter")
    p.keyboard.press("ArrowDown")
    p.keyboard.press("Enter")  # chooses Two: closes, focus back, onSelect runs
    assert p.evaluate("() => [window.__r.isOpen(), window.__sel]") == [False, ["Two"]]
    assert _active(p) == "r-trigger"


def test_opening_focuses_the_checked_item_and_a_plain_menu_the_first(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(RADIO_JS)
    p.evaluate("() => window.__r.setItemChecked(0, false)")
    p.evaluate("() => window.__r.setItemChecked(1, true)")
    p.get_by_test_id("r-trigger").focus()
    p.keyboard.press("ArrowDown")  # opens on the checked item, not the first
    assert _active(p) == "r-two"
    p.keyboard.press("Escape")
    p.get_by_test_id("r-trigger").click()  # mouse open: same
    assert _active(p) == "r-two"
    p.keyboard.press("Escape")
    p.get_by_test_id("r-trigger").focus()
    p.keyboard.press("ArrowUp")  # ArrowUp still opens on the last item
    assert _active(p) == "r-three"
    p.keyboard.press("Escape")
    # A checked item that is disabled is skipped: the first enabled item takes focus.
    p.evaluate("() => window.__r.setItemDisabled(1, true)")
    p.get_by_test_id("r-trigger").focus()
    p.keyboard.press("ArrowDown")
    assert _active(p) == "r-one"
    p.keyboard.press("Escape")
    # A plain menu (no checked item) opens on its first enabled item.
    p.get_by_test_id("m-trigger").focus()
    p.keyboard.press("ArrowDown")
    assert _active(p) == "m-rename"


def test_menu_option_validation(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    assert "items" in _throws(p, "App.ui.menu({items: []})")
    assert "items" in _throws(p, "App.ui.menu({})")
    assert "label" in _throws(p, "App.ui.menu({items: [{onSelect: () => {}}]})")
    assert "onSelect" in _throws(p, "App.ui.menu({items: [{label: 'x'}]})")
    assert "align" in _throws(
        p, "App.ui.menu({align: 'middle', items: [{label: 'x', onSelect: () => {}}]})"
    )


def test_set_item_disabled_toggles_an_item_without_closing_an_open_menu(
    engine_page: Page,
) -> None:
    """M33 F4 L03: an item's disabled state can change after construction (the Routines
    row's Run now follows the routine's running state) and an open menu stays open."""
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").click()
    assert _expanded(p) == "true"
    p.evaluate("() => { window.__m.setItemDisabled(0, true); return true; }")
    assert _expanded(p) == "true"
    assert p.get_by_test_id("m-rename").get_attribute("aria-disabled") == "true"
    # The focused item became disabled: focus moved to the first enabled one (the locked
    # item is skipped), and the arrow keys keep working from there.
    assert _active(p) == "m-dup"
    p.keyboard.press("ArrowDown")
    assert _active(p) == "m-del"
    p.get_by_test_id("m-rename").click(force=True)
    assert p.evaluate("() => window.__sel") == []
    assert _expanded(p) == "true"
    p.evaluate("() => { window.__m.setItemDisabled(0, false); return true; }")
    assert p.get_by_test_id("m-rename").get_attribute("aria-disabled") is None
    p.get_by_test_id("m-rename").click()
    assert p.evaluate("() => window.__sel") == ["Rename"]
    assert "index" in _throws(p, "window.__m.setItemDisabled(9, true)")


# ── Opening ─────────────────────────────────────────────────────────────────


def test_open_by_mouse_focuses_first_enabled_item(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").click()
    assert _expanded(p) == "true"
    expect(p.get_by_test_id("m-popup")).to_be_visible()
    assert _active(p) == "m-rename"


@pytest.mark.parametrize(
    ("key", "first"),
    [("Enter", True), ("Space", True), ("ArrowDown", True), ("ArrowUp", False)],
)
def test_open_by_keyboard(engine_page: Page, key: str, first: bool) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").focus()
    p.keyboard.press(key)
    assert _expanded(p) == "true"
    assert _active(p) == ("m-rename" if first else "m-del")


def test_trigger_click_toggles_and_disabled_trigger_never_opens(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").click()
    p.get_by_test_id("m-trigger").click()
    assert _expanded(p) == "false"
    assert _active(p) == "m-trigger"
    p.evaluate(
        "() => { window.__m.trigger.disabled = true; window.__m.open('first'); return true; }"
    )
    assert _expanded(p) == "false"
    assert p.evaluate("() => window.__m.isOpen()") is False


def test_all_items_disabled_focuses_popup_and_escape_works(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(
        """() => {
          const c = App.ui.menu({trigger: {label: 'Empty', testid: 'e-trigger'}, testid: 'e-popup',
            items: [{label: 'A', disabled: true, onSelect: () => {}}, {label: 'B', disabled: true, onSelect: () => {}}]});
          document.getElementById('harness-root').appendChild(c.el);
          return true;
        }"""
    )
    p.get_by_test_id("e-trigger").focus()
    p.keyboard.press("Enter")
    assert _active(p) == "e-popup"
    assert p.evaluate("() => document.activeElement.getAttribute('role')") == "menu"
    p.keyboard.press("Escape")
    expect(p.get_by_test_id("e-popup")).to_be_hidden()
    assert _active(p) == "e-trigger"


# ── Navigation ──────────────────────────────────────────────────────────────


def test_arrow_wrap_home_end_skip_disabled_and_keep_tabindex(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").focus()
    p.keyboard.press("Enter")
    tabs_js = (
        "() => Array.from(document.querySelectorAll('[role=menuitem]'))"
        ".map((i) => i.getAttribute('tabindex'))"
    )
    assert p.evaluate(tabs_js) == ["-1"] * 4  # after open('first')
    seen = [_active(p)]
    for key in ["ArrowDown", "ArrowDown", "ArrowDown", "ArrowDown", "ArrowUp"]:
        p.keyboard.press(key)
        seen.append(_active(p))
        assert p.evaluate(tabs_js) == ["-1"] * 4  # after every keyboard move
    # skips the disabled item, wraps downward, then ArrowUp from dup returns to rename
    assert seen == ["m-rename", "m-dup", "m-del", "m-rename", "m-dup", "m-rename"]
    p.keyboard.press("ArrowUp")
    assert _active(p) == "m-del"  # wraps upward
    p.keyboard.press("Home")
    assert _active(p) == "m-rename"
    assert p.evaluate(tabs_js) == ["-1"] * 4
    p.keyboard.press("End")
    assert _active(p) == "m-del"
    tabs = p.evaluate(
        "() => Array.from(document.querySelectorAll('[role=menuitem]')).map((i) => i.getAttribute('tabindex'))"
    )
    assert tabs == ["-1"] * 4
    assert _expanded(p) == "true"


# ── Activation ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("via", ["Enter", "Space", "click"])
def test_activation_closes_restores_focus_then_calls_onselect(engine_page: Page, via: str) -> None:
    p = engine_page
    _mount(p)
    # onSelect records the menu state at call time.
    p.evaluate(
        """() => {
          document.getElementById('harness-root').textContent = '';
          const c = App.ui.menu({trigger: {label: 'Actions', testid: 'm-trigger'}, testid: 'm-popup', items: [
            {label: 'Rename', testid: 'm-rename', onSelect: () => {
              window.__order = {open: window.__m.isOpen(), expanded: window.__m.trigger.getAttribute('aria-expanded'),
                                focus: document.activeElement === window.__m.trigger};
            }}]});
          window.__m = c;
          document.getElementById('harness-root').appendChild(c.el);
          return true;
        }"""
    )
    p.get_by_test_id("m-trigger").focus()
    p.keyboard.press("Enter")
    if via == "click":
        p.get_by_test_id("m-rename").click()
    else:
        p.keyboard.press(via)
    assert p.evaluate("() => window.__order") == {"open": False, "expanded": "false", "focus": True}
    expect(p.get_by_test_id("m-popup")).to_be_hidden()
    assert _active(p) == "m-trigger"


def test_throwing_onselect_leaves_menu_closed_and_propagates(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const c = App.ui.menu({trigger: {label: 'T', testid: 't2'}, items: [{label: 'Boom', testid: 'boom',
            onSelect: () => { throw new Error('select failed'); }}]});
          document.getElementById('harness-root').appendChild(c.el);
          c.open('first');
          let msg = '', fired = false;
          const onErr = (e) => { fired = true; msg = e.error ? e.error.message : e.message; e.preventDefault(); };
          window.addEventListener('error', onErr);
          c.popup.querySelector('[role=menuitem]').click();
          window.removeEventListener('error', onErr);
          return {fired, msg, open: c.isOpen(), expanded: c.trigger.getAttribute('aria-expanded'),
                  focus: document.activeElement === c.trigger};
        }"""
    )
    # WebKit masks the message of a script-injected handler as "Script error."
    assert out.pop("fired") is True
    assert out.pop("msg") in ("select failed", "Script error.")
    assert out == {"open": False, "expanded": "false", "focus": True}


def test_disabled_item_is_a_noop_and_menu_stays_open(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").click()
    p.get_by_test_id("m-locked").click(force=True)
    assert _expanded(p) == "true"
    expect(p.get_by_test_id("m-popup")).to_be_visible()
    p.get_by_test_id("m-locked").focus()  # focusable programmatically
    p.keyboard.press("Enter")
    p.keyboard.press("Space")
    assert _expanded(p) == "true"
    assert p.evaluate("() => window.__sel") == []


# ── Escape, Tab, focusout ───────────────────────────────────────────────────


def test_escape_closes_and_focuses_trigger_from_popup_and_trigger(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").focus()
    p.keyboard.press("ArrowDown")
    p.keyboard.press("Escape")
    assert _expanded(p) == "false" and _active(p) == "m-trigger"
    # Escape while closed is not handled: the event reaches ancestors.
    out = p.evaluate(
        """() => new Promise((resolve) => {
          const root = document.getElementById('harness-root');
          root.addEventListener('keydown', (e) => resolve({key: e.key, prevented: e.defaultPrevented}), {once: true});
          window.__m.trigger.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}));
        })"""
    )
    assert out == {"key": "Escape", "prevented": False}
    # Escape from the trigger while open (focus returned there by hand) also closes it.
    p.evaluate("() => { window.__m.open('first'); window.__m.trigger.focus(); return true; }")
    p.keyboard.press("Escape")
    assert _expanded(p) == "false"


def test_open_escape_does_not_reach_ancestors(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(
        "() => { window.__esc = 0; document.getElementById('harness-root').addEventListener('keydown', (e) => { if (e.key === 'Escape') window.__esc += 1; }); return true; }"
    )
    p.get_by_test_id("m-trigger").click()
    p.keyboard.press("Escape")
    assert p.evaluate("() => window.__esc") == 0


@pytest.mark.parametrize(("key", "expected"), [("Tab", "m-after"), ("Shift+Tab", "m-before")])
def test_tab_closes_and_focus_moves_past_trigger(
    engine_page: Page, key: str, expected: str
) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").focus()
    p.keyboard.press("Enter")
    assert _expanded(p) == "true"
    p.keyboard.press(key)
    assert _expanded(p) == "false"
    assert _active(p) == expected


def test_focus_moving_outside_closes_without_restoring(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").click()
    p.evaluate("() => { document.querySelector('[data-testid=m-after]').focus(); return true; }")
    assert _expanded(p) == "false"
    assert _active(p) == "m-after"


# ── Outside click, single open menu ─────────────────────────────────────────


def test_outside_pointer_closes_without_restoring_focus(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").click()
    p.mouse.click(5, 400)
    assert _expanded(p) == "false"
    expect(p.get_by_test_id("m-popup")).to_be_hidden()
    assert _active(p) != "m-trigger"
    # a press inside the popup does not close it
    p.get_by_test_id("m-trigger").click()
    p.get_by_test_id("m-locked").click(force=True)
    assert _expanded(p) == "true"


def test_opening_a_second_menu_closes_the_first(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate(
        """() => {
          const c = App.ui.menu({trigger: {label: 'Second', testid: 'm2-trigger'}, testid: 'm2-popup',
                                 items: [{label: 'X', testid: 'm2-x', onSelect: () => {}}]});
          window.__m2 = c;
          document.getElementById('harness-root').appendChild(c.el);
          return true;
        }"""
    )
    p.get_by_test_id("m-trigger").click()
    p.evaluate("() => { window.__m2.open('first'); return true; }")
    assert p.evaluate("() => [window.__m.isOpen(), window.__m2.isOpen()]") == [False, True]
    expect(p.get_by_test_id("m-popup")).to_be_hidden()
    expect(p.get_by_test_id("m2-popup")).to_be_visible()


def test_destroy_while_open_closes_and_clears_state(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("m-trigger").click()
    p.evaluate("() => { window.__m.destroy(); return true; }")
    assert _expanded(p) == "false"
    # a later menu opens cleanly and a stale reference does not close it
    p.evaluate(
        "() => { window.__m2 = window.__mk({}); document.getElementById('harness-root').appendChild(window.__m2.el); window.__m2.open('first'); return true; }"
    )
    assert p.evaluate("() => window.__m2.isOpen()") is True


def test_closing_a_detached_menu_does_not_throw(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          window.__m.open('first');
          document.getElementById('harness-root').textContent = '';
          try { window.__m.close(true); return 'ok'; } catch (e) { return e.message; }
        }"""
    )
    assert out == "ok"


# ── Focus-visible, styling, a11y ────────────────────────────────────────────


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_keyboard_open_shows_accent_focus_ring_and_popup_styling(
    engine_page: Page, theme: str
) -> None:
    p = engine_page
    _mount(p, theme)
    p.get_by_test_id("m-trigger").focus()
    p.keyboard.press("ArrowDown")
    out = p.evaluate(
        """() => {
          const it = document.activeElement, pop = window.__m.popup;
          const root = getComputedStyle(document.getElementById('harness-root'));
          const cs = getComputedStyle(it), ps = getComputedStyle(pop);
          const probe = document.createElement('div');
          probe.style.cssText = 'color: var(--accent); background: var(--surface-elevated); border-color: var(--border)';
          document.getElementById('harness-root').appendChild(probe);
          const ref = getComputedStyle(probe);
          const dangerProbe = document.createElement('div');
          dangerProbe.style.color = 'var(--status-danger)';
          document.getElementById('harness-root').appendChild(dangerProbe);
          const del = getComputedStyle(pop.querySelector('[data-testid=m-del]'));
          return {matches: it.matches(':focus-visible'), ow: cs.outlineWidth, oc: cs.outlineColor, accent: ref.color,
                  bg: ps.backgroundColor, bgRef: ref.backgroundColor, radius: ps.borderRadius, shadow: ps.boxShadow,
                  bw: ps.borderTopWidth, delColor: del.color, dangerRef: getComputedStyle(dangerProbe).color};
        }"""
    )
    assert out["matches"] is True
    assert out["ow"] == "2px" and out["oc"] == out["accent"]
    assert out["bg"] == out["bgRef"] and out["bw"] == "1px"
    assert out["shadow"] not in ("none", "")
    assert out["delColor"] == out["dangerRef"]


def test_align_end_right_aligns_popup(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const c = App.ui.menu({align: 'end', trigger: {label: 'A very long trigger label here', testid: 'e-t'},
                                 items: [{label: 'x', onSelect: () => {}}]});
          document.getElementById('harness-root').appendChild(c.el);
          c.open('first');
          const t = c.trigger.getBoundingClientRect(), pr = c.popup.getBoundingClientRect();
          return {right: Math.abs(t.right - pr.right), left: Math.abs(t.left - pr.left), below: pr.top >= t.bottom};
        }"""
    )
    assert out["right"] < 1 and out["below"] is True


@pytest.mark.parametrize("state", ["closed", "open"])
def test_labelled_and_described_closed_and_open(engine_page: Page, state: str) -> None:
    p = engine_page
    _mount(p)
    if state == "open":
        p.get_by_test_id("m-trigger").click()
    assert_controls_labelled_and_described(p, "#harness-root")


# ── Inside a native dialog (DD8) ────────────────────────────────────────────

DIALOG_SETUP = """() => {
  window.__mk = null;
  const root = document.getElementById('harness-root');
  const opener = document.createElement('button');
  opener.textContent = 'Open dialog'; opener.setAttribute('data-testid', 'dm-open');
  const dlg = document.createElement('dialog');
  dlg.id = 'dm-dlg'; dlg.setAttribute('aria-label', 'Menu dialog'); dlg.setAttribute('data-testid', 'dm-dialog');
  dlg.style.cssText = 'width: 320px; height: 240px; padding: 16px;';
  const c = App.ui.menu({trigger: {label: 'Actions', testid: 'dm-trigger'}, testid: 'dm-popup',
                         items: [{label: 'One', testid: 'dm-one', onSelect: () => {}},
                                 {label: 'Two', testid: 'dm-two', onSelect: () => {}}]});
  window.__m = c;
  const inner = document.createElement('button');
  inner.textContent = 'Inner'; inner.setAttribute('data-testid', 'dm-inner');
  dlg.appendChild(c.el); dlg.appendChild(inner);
  root.appendChild(opener); root.appendChild(dlg);
  opener.addEventListener('click', (ev) => DialogRule.open(dlg, {opener: ev.currentTarget, transient: false}));
  return true;
}"""


def _dialog_page(page: Page) -> None:
    page.set_viewport_size({"width": 1024, "height": 768})
    load_harness(page)
    page.add_script_tag(path=str(HARNESS_JS))
    page.evaluate(DIALOG_SETUP)
    page.get_by_test_id("dm-open").click()  # a real click with user activation
    assert layers(page) == 1


@pytest.mark.parametrize("via", ["keyboard", "mouse"])
def test_menu_in_dialog_escape_closes_menu_then_dialog(engine_page: Page, via: str) -> None:
    p = engine_page
    _dialog_page(p)
    if via == "keyboard":
        p.get_by_test_id("dm-trigger").focus()
        p.keyboard.press("Enter")
    else:
        p.get_by_test_id("dm-trigger").click()
    assert p.evaluate("() => window.__m.isOpen()") is True
    p.keyboard.press("Escape")
    assert p.evaluate("() => window.__m.isOpen()") is False
    assert layers(p) == 1  # the dialog stays open
    assert _active(p) == "dm-trigger"
    p.keyboard.press("Escape")
    assert layers(p) == 0


def test_menu_in_dialog_outside_click_closes_menu_only(engine_page: Page) -> None:
    p = engine_page
    _dialog_page(p)
    p.get_by_test_id("dm-trigger").click()
    assert p.evaluate("() => window.__m.isOpen()") is True
    p.get_by_test_id("dm-inner").click()
    assert p.evaluate("() => window.__m.isOpen()") is False
    assert layers(p) == 1

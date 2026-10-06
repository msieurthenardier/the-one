# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for the committed ``App.ui`` factories
(M25 F1 L2): core helpers, ``button``, ``textInput`` / ``field`` and ``listPane``,
plus the M25 F3 L1 ``listPane`` additions (title count, intro, per-group empty
text, row styles, ``scrollToSelected``, the accessible-name suffix and focus kept
across ``setItems``) and the L4a ``scrollToGroup`` with its optional group ids;
M25 F4 L6 adds ``setQuery`` (silent, no row rebuilt).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``
(no app spawn). Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import re

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import STATIC_DIR, load_harness
from browser.design_tokens import DARK
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

PROBE_MOUNT_JS = STATIC_DIR.parents[3] / "tests" / "browser" / "_probe_mount_ui.js"

# A reusable mount: a list pane (filter, groups) built through the factory, with
# every select recorded on window.__selected.
MOUNT_PANE_JS = """() => {
  window.__selected = [];
  const sel = (item) => window.__selected.push(item.id);
  const c = App.ui.listPane({
    title: 'Agents', testid: 'lp-root', emptyText: 'No agents match',
    filter: {label: 'Filter agents', placeholder: 'Filter', testid: 'lp-filter'},
    selectedId: 'beta',
    items: [
      {id: 'alpha', label: 'Alpha', meta: 'first one', onSelect: sel, testid: 'lp-row-alpha'},
      {id: 'beta', label: 'Beta', meta: 'second one', href: '#beta', testid: 'lp-row-beta'},
      {id: 'gamma', label: 'Gamma', meta: 'third one', onSelect: sel, badges: ['3'], icon: 'plus'},
    ],
  });
  window.__pane = c;
  document.getElementById('harness-root').appendChild(c.el);
  return true;
}"""


def _load(page: Page) -> None:
    load_harness(page)


def _throws(page: Page, expr: str) -> str:
    """Evaluate ``expr`` (a JS expression string); return the thrown message or ''."""
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


# ── core ────────────────────────────────────────────────────────────────────


def test_core_namespace_and_helpers(engine_page: Page) -> None:
    _load(engine_page)
    shape = engine_page.evaluate(
        "() => ({ui: typeof App.ui, util: Object.keys(App.ui.util).sort(),"
        " fact: ['button','textInput','field','listPane'].map(n => typeof App.ui[n])})"
    )
    assert shape["ui"] == "object"
    assert shape["util"] == ["el", "icon", "rovingFocus", "uid"]
    assert shape["fact"] == ["function"] * 4


def test_core_el_builds_without_html(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          let clicks = 0;
          const n = App.ui.util.el('div', {
            className: 'a b', text: 'lead', dataset: {fooBar: '1'}, 'aria-label': 'L',
            hidden: true, title: null, onClick: () => { clicks += 1; },
          }, ['<b>x</b>', 5, null, App.ui.util.el('span', {text: 'kid'})]);
          n.click();
          return {cls: n.className, data: n.getAttribute('data-foo-bar'), aria: n.getAttribute('aria-label'),
                  hidden: n.hasAttribute('hidden'), title: n.hasAttribute('title'), clicks,
                  bold: !!n.querySelector('b'), text: n.textContent, kids: n.childNodes.length};
        }"""
    )
    assert out["cls"] == "a b"
    assert out["data"] == "1"
    assert out["aria"] == "L"
    assert out["hidden"] is True
    assert out["title"] is False
    assert out["clicks"] == 1
    assert out["bold"] is False  # a string child is a text node, never HTML
    assert out["text"] == "lead<b>x</b>5kid"
    assert out["kids"] == 4  # lead text, <b> text, 5, span


def test_core_uid_is_prefixed_monotonic_and_unique(engine_page: Page) -> None:
    _load(engine_page)
    ids = engine_page.evaluate(
        "() => [App.ui.util.uid('in'), App.ui.util.uid('in'), App.ui.util.uid('x')]"
    )
    assert ids[0].startswith("ui-in-")
    assert ids[2].startswith("ui-x-")
    nums = [int(i.rsplit("-", 1)[1]) for i in ids]
    assert nums == sorted(nums) and len(set(nums)) == 3


def test_core_icon_is_a_hidden_svg_node(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          const svg = App.ui.util.icon('plus');
          return {ctor: svg.constructor.name, ns: svg.namespaceURI, hidden: svg.getAttribute('aria-hidden'),
                  focusable: svg.getAttribute('focusable'), doc: svg.ownerDocument === document};
        }"""
    )
    assert out["ctor"] == "SVGSVGElement"
    assert out["ns"] == "http://www.w3.org/2000/svg"
    assert out["hidden"] == "true"
    assert out["focusable"] == "false"
    assert out["doc"] is True
    assert "unknown icon" in _throws(engine_page, "App.ui.util.icon('nope-not-an-icon')")


def test_core_icon_throws_on_unparseable_source(engine_page: Page) -> None:
    _load(engine_page)
    msg = _throws(engine_page, "App.icons.__bad = '<svg><oops>'; App.ui.util.icon('__bad');")
    assert "did not parse as svg" in msg


ROVING_SETUP = """() => {
  const host = document.getElementById('harness-root');
  const box = document.createElement('div');
  box.id = 'rv';
  for (const t of ['a', 'b', 'c']) {
    const l = document.createElement('a'); l.href = '#' + t; l.textContent = t; l.className = 'it';
    l.tabIndex = t === 'a' ? 0 : -1; box.appendChild(l);
  }
  host.appendChild(box);
  window.__docKeys = 0;
  document.addEventListener('keydown', () => { window.__docKeys += 1; });
  window.__unbind = App.ui.util.rovingFocus(box, '.it', %s);
  return true;
}"""


def _active(page: Page) -> str:
    return page.evaluate("() => document.activeElement.textContent")


def test_roving_focus_clamps_by_default_and_never_takes_enter(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(ROVING_SETUP % "undefined")
    engine_page.focus("#rv a:first-child")
    engine_page.keyboard.press("ArrowUp")
    assert _active(engine_page) == "a"  # clamped at the start
    engine_page.keyboard.press("ArrowDown")
    engine_page.keyboard.press("ArrowDown")
    engine_page.keyboard.press("ArrowDown")
    assert _active(engine_page) == "c"  # clamped at the end
    engine_page.keyboard.press("Home")
    assert _active(engine_page) == "a"
    engine_page.keyboard.press("End")
    assert _active(engine_page) == "c"
    tabs = engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('#rv a')).map(a => a.tabIndex)"
    )
    assert tabs == [-1, -1, 0]  # roving tab stop followed focus
    # ArrowLeft/Right are ignored unless horizontal; Enter is never intercepted.
    engine_page.keyboard.press("ArrowLeft")
    assert _active(engine_page) == "c"
    prevented = engine_page.evaluate(
        """() => {
          const ev = new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true});
          document.activeElement.dispatchEvent(ev);
          const sp = new KeyboardEvent('keydown', {key: ' ', bubbles: true, cancelable: true});
          document.activeElement.dispatchEvent(sp);
          return [ev.defaultPrevented, sp.defaultPrevented];
        }"""
    )
    assert prevented == [False, False]


def test_roving_focus_wrap_horizontal_and_unbind(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(ROVING_SETUP % "{wrap: true, horizontal: true}")
    engine_page.focus("#rv a:first-child")
    engine_page.keyboard.press("ArrowUp")
    assert _active(engine_page) == "c"  # wrapped
    engine_page.keyboard.press("ArrowRight")
    assert _active(engine_page) == "a"
    engine_page.keyboard.press("ArrowLeft")
    assert _active(engine_page) == "c"
    engine_page.evaluate("() => window.__unbind()")
    engine_page.keyboard.press("Home")
    assert _active(engine_page) == "c"  # unbound: no longer handled


def test_roving_focus_queries_items_at_event_time(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(ROVING_SETUP % "undefined")
    engine_page.evaluate(
        """() => {
          const box = document.getElementById('rv');
          const l = document.createElement('a'); l.href = '#d'; l.textContent = 'd'; l.className = 'it';
          l.tabIndex = -1; box.appendChild(l);
        }"""
    )
    engine_page.focus("#rv a:first-child")
    engine_page.keyboard.press("End")
    assert _active(engine_page) == "d"  # a row added after binding is reached


# ── button ──────────────────────────────────────────────────────────────────


def test_button_defaults_variants_and_sizes(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          const U = App.ui;
          const d = U.button({label: 'Go'});
          const per = {};
          for (const v of ['primary', 'secondary', 'ghost', 'danger']) per[v] = U.button({label: v, variant: v}).className;
          const sz = {};
          for (const s of ['sm', 'lg', 'xl']) sz[s] = U.button({label: s, size: s}).className;
          return {tag: d.tagName, type: d.type, cls: d.className, per, sz, text: d.textContent,
                  ico: U.button({label: 'x', icon: 'plus'}).firstChild.nodeName.toLowerCase()};
        }"""
    )
    assert out["tag"] == "BUTTON" and out["type"] == "button"
    assert out["cls"] == "btn-outlined-primary"
    assert out["per"] == {
        "primary": "btn-filled-primary",
        "secondary": "btn-outlined-primary",
        "ghost": "btn-ghost",
        "danger": "btn-muted-destructive",
    }
    assert out["sz"] == {
        "sm": "btn-outlined-primary btn-sm",
        "lg": "btn-outlined-primary btn-lg",
        "xl": "btn-outlined-primary btn-xl",
    }
    assert out["ico"] == "svg"


def test_button_icon_only_requires_aria_label(engine_page: Page) -> None:
    _load(engine_page)
    assert "ariaLabel" in _throws(engine_page, "App.ui.button({iconOnly: true, icon: 'plus'});")
    out = engine_page.evaluate(
        """() => {
          const b = App.ui.button({iconOnly: true, icon: 'plus', ariaLabel: 'Add', testid: 'b-add', className: 'extra'});
          document.getElementById('harness-root').appendChild(b);
          return {cls: b.className, aria: b.getAttribute('aria-label'), tid: b.getAttribute('data-testid')};
        }"""
    )
    assert "btn-icon" in out["cls"] and "extra" in out["cls"]
    assert out["aria"] == "Add" and out["tid"] == "b-add"
    assert_controls_labelled_and_described(engine_page, "#harness-root")
    engine_page.get_by_role("button", name="Add", exact=True).click()


def test_button_label_is_text_not_html_and_onclick_disabled(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(
        """() => {
          window.__n = 0;
          const root = document.getElementById('harness-root');
          root.appendChild(App.ui.button({label: '<i>raw</i>', testid: 'b-live', onClick: () => { window.__n += 1; }}));
          root.appendChild(App.ui.button({label: 'Off', testid: 'b-off', disabled: true, onClick: () => { window.__n += 100; }}));
          return true;
        }"""
    )
    assert engine_page.evaluate("() => document.querySelector('[data-testid=b-live] i')") is None
    live = engine_page.get_by_test_id("b-live")
    off = engine_page.get_by_test_id("b-off")
    expect(live).to_have_text("<i>raw</i>")
    assert off.is_disabled() and live.is_enabled()
    live.click()
    off.click(force=True)  # a disabled button swallows the click
    assert engine_page.evaluate("() => window.__n") == 1


@pytest.mark.parametrize(
    "expr",
    ["App.ui.button({variant: 'nope'})", "App.ui.button({size: 'xxl'})"],
)
def test_button_rejects_unknown_options(engine_page: Page, expr: str) -> None:
    _load(engine_page)
    assert _throws(engine_page, expr)


# ── textInput / field ───────────────────────────────────────────────────────


def test_text_input_options(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          let seen = '';
          const i = App.ui.textInput({name: 'nm', type: 'email', value: 'a@b.c', placeholder: 'ph',
            required: true, autocomplete: 'off', testid: 'ti', onInput: (e) => { seen = e.target.value; }});
          document.getElementById('harness-root').appendChild(i);
          const j = App.ui.textInput({id: 'mine', disabled: true});
          return {tag: i.tagName, cls: i.className, id: i.id, name: i.name, type: i.type, value: i.value,
                  ph: i.placeholder, req: i.required, ac: i.getAttribute('autocomplete'),
                  tid: i.getAttribute('data-testid'), mine: j.id, dis: j.disabled};
        }"""
    )
    assert out["tag"] == "INPUT" and out["cls"] == "field-input"
    assert out["id"].startswith("ui-in-") and out["name"] == "nm"
    assert out["type"] == "email" and out["value"] == "a@b.c" and out["ph"] == "ph"
    assert out["req"] is True and out["ac"] == "off" and out["tid"] == "ti"
    assert out["mine"] == "mine" and out["dis"] is True
    assert _throws(engine_page, "App.ui.textInput({type: 'checkbox'})")
    box = engine_page.get_by_test_id("ti")
    box.fill("typed@x.y")
    assert box.input_value() == "typed@x.y"
    assert box.is_enabled()


FIELD_SETUP = """(opts) => {
  const input = App.ui.textInput({testid: 'f-input'});
  const f = App.ui.field(Object.assign({label: 'Name', control: input, testid: 'f-wrap'}, opts));
  window.__f = f;
  document.getElementById('harness-root').appendChild(f.el);
  return true;
}"""


def _describedby(page: Page) -> list[str]:
    return page.evaluate(
        "() => (document.querySelector('[data-testid=f-input]').getAttribute('aria-describedby') || '')"
        ".split(' ').filter(Boolean).map(id => { const e = document.getElementById(id);"
        " return e ? e.className : 'MISSING:' + id; })"
    )


def test_field_wiring_label_hint_error_order(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(FIELD_SETUP, {"hint": "Your name", "error": "Required"})
    out = engine_page.evaluate(
        """() => {
          const wrap = document.querySelector('[data-testid=f-wrap]');
          const input = document.querySelector('[data-testid=f-input]');
          const label = wrap.querySelector(':scope > label');
          const err = wrap.querySelector('.field-error');
          return {wrapCls: wrap.className, labelParent: label.parentElement === wrap,
                  control: label.control === input, forId: label.htmlFor === input.id,
                  invalid: input.getAttribute('aria-invalid'), cls: input.classList.contains('is-invalid'),
                  role: err.getAttribute('role'), hasIds: !!err.id && !!wrap.querySelector('.field-hint').id};
        }"""
    )
    assert out["wrapCls"] == "field-group" and out["labelParent"] is True
    assert out["control"] is True and out["forId"] is True
    assert out["invalid"] == "true" and out["cls"] is True
    assert out["role"] == "alert" and out["hasIds"] is True
    assert _describedby(engine_page) == ["field-hint", "field-error"]  # hint first
    assert_controls_labelled_and_described(engine_page, "#harness-root")
    # Playwright resolves the label natively.
    engine_page.get_by_label("Name", exact=True).fill("ok")


def test_field_set_error_null_removes_wiring(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(FIELD_SETUP, {"hint": "h"})
    engine_page.evaluate("() => window.__f.setError('bad')")
    assert _describedby(engine_page) == ["field-hint", "field-error"]
    engine_page.evaluate("() => window.__f.setError(null)")
    out = engine_page.evaluate(
        """() => {
          const input = document.querySelector('[data-testid=f-input]');
          return {errEls: document.querySelectorAll('.field-error').length,
                  invalid: input.hasAttribute('aria-invalid'), cls: input.classList.contains('is-invalid')};
        }"""
    )
    assert out == {"errEls": 0, "invalid": False, "cls": False}  # removed, not blanked
    assert _describedby(engine_page) == ["field-hint"]
    engine_page.evaluate("() => window.__f.setHint(null)")
    assert _describedby(engine_page) == []
    assert (
        engine_page.evaluate(
            "() => document.querySelector('[data-testid=f-input]').hasAttribute('aria-describedby')"
        )
        is False
    )
    # re-adding works and keeps hint-before-error order whichever comes first
    engine_page.evaluate("() => { window.__f.setError('e2'); window.__f.setHint('h2'); }")
    assert _describedby(engine_page) == ["field-hint", "field-error"]
    assert_controls_labelled_and_described(engine_page, "#harness-root")


def test_field_label_hidden_stays_in_dom_and_control_gets_id(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          const bare = document.createElement('input');
          const f = App.ui.field({label: 'Hidden one', labelHidden: true, control: bare});
          document.getElementById('harness-root').appendChild(f.el);
          const label = f.el.querySelector('label');
          return {id: bare.id, cls: label.className, inDom: label.isConnected, ctl: f.control === bare,
                  w: label.getBoundingClientRect().width};
        }"""
    )
    assert out["id"].startswith("ui-ctl-")
    assert out["cls"] == "visually-hidden" and out["inDom"] is True and out["ctl"] is True
    assert out["w"] <= 1
    assert_controls_labelled_and_described(engine_page, "#harness-root")
    assert _throws(engine_page, "App.ui.field({label: 'x', control: 'nope'})")


# ── listPane ────────────────────────────────────────────────────────────────


def _mount_pane(page: Page) -> None:
    _load(page)
    page.evaluate(MOUNT_PANE_JS)


def test_list_pane_structure_and_row_kinds(engine_page: Page) -> None:
    _mount_pane(engine_page)
    out = engine_page.evaluate(
        """() => {
          const root = document.querySelector('[data-testid=lp-root]');
          const h2 = root.querySelector('h2');
          return {tag: root.tagName, labelledby: root.getAttribute('aria-labelledby') === h2.id,
                  title: h2.textContent, lists: root.querySelectorAll('ul').length,
                  listLabel: root.querySelector('ul').getAttribute('aria-labelledby') === h2.id,
                  rows: Array.from(root.querySelectorAll('li > .ui-list-pane-row')).map(r => r.tagName + ':' + (r.getAttribute('aria-current') || '-') + ':' + r.tabIndex),
                  filterLabel: root.querySelector('input').labels[0].className,
                  bareLi: Array.from(root.querySelectorAll('ul > *')).every(n => n.tagName === 'LI')};
        }"""
    )
    assert out["tag"] == "SECTION" and out["labelledby"] is True and out["title"] == "Agents"
    assert out["lists"] == 1 and out["listLabel"] is True and out["bareLi"] is True
    assert out["rows"] == ["BUTTON:-:-1", "A:page:0", "BUTTON:-:-1"]
    assert out["filterLabel"] == "visually-hidden"
    assert_controls_labelled_and_described(engine_page, "[data-testid=lp-root]")


def test_list_pane_aria_current_value_follows_the_row_kind(engine_page: Page) -> None:
    """Flight-end review: a selected link row is the current PAGE
    (``aria-current="page"``); a selected button row (onSelect) is the current
    item in a set (``"true"``), with the same selected look."""
    _mount_pane(engine_page)
    p = engine_page
    probe = """() => Array.from(document.querySelectorAll('[data-testid=lp-root] li > .ui-list-pane-row'))
      .map((r) => { const s = getComputedStyle(r);
        return [r.tagName, r.getAttribute('aria-current'), s.backgroundColor, s.boxShadow]; })"""
    on_link = p.evaluate(probe)
    assert [r[:2] for r in on_link] == [["BUTTON", None], ["A", "page"], ["BUTTON", None]]
    p.evaluate("() => window.__pane.setSelected('alpha')")
    on_button = p.evaluate(probe)
    assert [r[:2] for r in on_button] == [["BUTTON", "true"], ["A", None], ["BUTTON", None]]
    # The selected look is the same for both kinds (wash and ring).
    assert on_button[0][2:] == on_link[1][2:], (on_button, on_link)
    assert on_button[0][2:] != on_button[1][2:], on_button
    expect(p.get_by_role("button", name="Alpha")).to_have_attribute("aria-current", "true")


def test_list_pane_strict_locators_filter_and_activation(engine_page: Page) -> None:
    _mount_pane(engine_page)
    p = engine_page
    # strict locators resolve single rows (link for href rows, button for the rest)
    expect(p.get_by_role("link", name="Beta")).to_have_count(1)
    expect(p.get_by_role("button", name="Alpha")).to_have_count(1)
    expect(p.get_by_role("button", name="Gamma")).to_have_count(1)
    p.get_by_role("button", name="Alpha").click()
    assert p.evaluate("() => window.__selected") == ["alpha"]
    p.get_by_role("button", name="Gamma").focus()
    p.keyboard.press("Enter")
    assert p.evaluate("() => window.__selected") == ["alpha", "gamma"]
    # the link row follows its href natively
    p.get_by_role("link", name="Beta").click()
    assert p.evaluate("() => location.hash") == "#beta"
    # filter narrows, default predicate matches label and meta, case-insensitively
    flt = p.get_by_test_id("lp-filter")
    flt.fill("GAM")
    expect(p.locator(".ui-list-pane-row:visible")).to_have_count(1)
    flt.fill("second")
    expect(p.get_by_role("link", name="Beta")).to_be_visible()
    expect(p.get_by_role("button", name="Alpha")).to_have_count(0)  # hidden rows leave the tree
    flt.fill("zzz")
    expect(p.get_by_role("heading", name="No agents match")).to_be_visible()
    flt.fill("")
    expect(p.locator(".ui-list-pane-row:visible")).to_have_count(3)
    expect(p.get_by_text("No agents match")).to_be_hidden()


def test_list_pane_keyboard_tab_entry_and_roving(engine_page: Page) -> None:
    _mount_pane(engine_page)
    p = engine_page
    p.get_by_test_id("lp-filter").focus()
    p.keyboard.press("Tab")
    # Tab enters at the selected row (beta), not the first
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "lp-row-beta"
    p.keyboard.press("ArrowUp")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "lp-row-alpha"
    p.keyboard.press("ArrowUp")  # clamped
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "lp-row-alpha"
    p.keyboard.press("End")
    assert p.evaluate("() => document.activeElement.textContent").startswith("Gamma")
    p.keyboard.press("Home")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "lp-row-alpha"


def test_list_pane_filtered_out_selection_and_restore(engine_page: Page) -> None:
    _mount_pane(engine_page)
    p = engine_page
    flt = p.get_by_test_id("lp-filter")
    flt.fill("gamma")  # beta (selected) is filtered out
    stops = p.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-list-pane-row')).filter(r => !r.parentElement.hidden)"
        ".map(r => r.textContent.slice(0, 5) + ':' + r.tabIndex + ':' + r.hasAttribute('aria-current'))"
    )
    assert stops == ["Gamma:0:false"]  # the first visible row is the tab stop
    flt.press("Tab")
    assert p.evaluate("() => document.activeElement.textContent").startswith("Gamma")
    flt.fill("")
    restored = p.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-list-pane-row')).map(r => r.tabIndex + ':' + r.getAttribute('aria-current'))"
    )
    assert restored == ["-1:null", "0:page", "-1:null"]  # selection kept through the filter


def test_list_pane_set_selected_unknown_clears_and_first_row_is_stop(engine_page: Page) -> None:
    _mount_pane(engine_page)
    p = engine_page
    p.evaluate("() => window.__pane.setSelected('gamma')")
    # gamma is a BUTTON row: aria-current="true", not "page" (the flight-end review).
    assert p.evaluate("() => document.querySelector('[aria-current=true]').textContent").startswith(
        "Gamma"
    )
    assert p.evaluate("() => document.querySelectorAll('[aria-current=page]').length") == 0
    p.evaluate("() => window.__pane.setSelected('no-such-id')")
    state = p.evaluate(
        "() => ({cur: document.querySelectorAll('[aria-current]').length,"
        " tabs: Array.from(document.querySelectorAll('.ui-list-pane-row')).map(r => r.tabIndex)})"
    )
    assert state == {"cur": 0, "tabs": [0, -1, -1]}
    p.evaluate("() => { window.__pane.setSelected('alpha'); window.__pane.focusSelected(); }")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "lp-row-alpha"


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ("[{id: 'x', label: 'X'}]", "listPane item x: href or onSelect required"),
        (
            "[{id: 'x', label: 'X', href: '#'}, {id: 'x', label: 'Y', href: '#'}]",
            "listPane duplicate item id x",
        ),
    ],
    ids=["no-href-no-onselect", "duplicate-id"],
)
def test_list_pane_edge_rules_throw(engine_page: Page, items: str, message: str) -> None:
    _load(engine_page)
    assert _throws(engine_page, f"App.ui.listPane({{title: 'T', items: {items}}});") == message
    # a failing setItems leaves the previous rows untouched
    engine_page.evaluate(
        "() => { window.__c = App.ui.listPane({title: 'T', items: [{id: 'ok', label: 'OK', href: '#'}]}); }"
    )
    assert (
        engine_page.evaluate(
            f"() => {{ try {{ window.__c.setItems({items}); }} catch (e) {{ return e.message; }} }}"
        )
        == message
    )
    assert engine_page.evaluate("() => window.__c.el.querySelectorAll('li').length") == 1


def test_list_pane_groups_markup(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(
        """() => {
          const c = App.ui.listPane({title: 'Library', filter: {label: 'Filter library', testid: 'g-filter'},
            groups: [
              {label: 'Chats', items: [{id: 'c1', label: 'Chat one', href: '#c1', testid: 'g-c1'}]},
              {label: 'Agents', items: [{id: 'a1', label: 'Agent one', href: '#a1'}, {id: 'a2', label: 'Agent two', href: '#a2'}]},
            ]});
          document.getElementById('harness-root').appendChild(c.el);
          return true;
        }"""
    )
    out = engine_page.evaluate(
        """() => {
          const uls = Array.from(document.querySelectorAll('.ui-list-pane ul'));
          return {n: uls.length, caps: uls.map(u => document.getElementById(u.getAttribute('aria-labelledby')).textContent),
                  bare: uls.every(u => Array.from(u.children).every(c => c.tagName === 'LI'))};
        }"""
    )
    assert out == {"n": 2, "caps": ["Chats", "Agents"], "bare": True}
    engine_page.get_by_test_id("g-filter").fill("agent two")
    assert engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-list-pane-group')).map(g => g.hidden)"
    ) == [True, False]  # a group with no visible rows hides its caption too
    assert_controls_labelled_and_described(engine_page, ".ui-list-pane")


def test_list_pane_set_query_applies_the_view_silently(engine_page: Page) -> None:
    """M25 F4 L6 (AC12): setQuery(q) sets the filter's value and query and
    applies the view -- rows shown or hidden, the selection and the tab stop
    re-derived -- without rebuilding a row (the same nodes, focus kept) and
    without a live announcement (the status region is cleared, never written)."""
    _mount_pane(engine_page)
    p = engine_page
    status = p.locator("[data-testid=lp-root] .ui-list-pane-status")
    flt = p.get_by_test_id("lp-filter")
    flt.fill("gam")  # a keystroke announces
    expect(status).to_have_text("1 result")
    p.evaluate(
        "() => document.querySelectorAll('.ui-list-pane-row').forEach((r, i) => { r.__mark = i; })"
    )
    p.evaluate("() => window.__pane.setQuery('')")
    out = p.evaluate(
        """() => ({
          value: document.querySelector('[data-testid=lp-filter]').value,
          rows: Array.from(document.querySelectorAll('.ui-list-pane-row')).map((r) =>
            [r.__mark, r.parentElement.hidden, r.tabIndex, r.getAttribute('aria-current')]),
          status: document.querySelector('[data-testid=lp-root] .ui-list-pane-status').textContent,
        })"""
    )
    # Every row back, the same nodes, the selected row (beta) the tab stop.
    assert out == {
        "value": "",
        "rows": [[0, False, -1, None], [1, False, 0, "page"], [2, False, -1, None]],
        "status": "",
    }
    # A non-empty query: filtered, the first visible row the stop, still silent.
    p.evaluate("() => window.__pane.setQuery('alp')")
    expect(flt).to_have_value("alp")
    expect(p.locator(".ui-list-pane-row:visible")).to_have_count(1)
    assert p.evaluate("() => document.querySelector('[data-testid=lp-row-alpha]').tabIndex") == 0
    expect(status).to_have_text("")
    # Focus survives: no row is rebuilt.
    p.get_by_test_id("lp-row-alpha").focus()
    p.evaluate("() => window.__pane.setQuery('')")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "lp-row-alpha"
    assert p.evaluate("() => document.querySelector('[data-testid=lp-row-alpha]').__mark") == 0


def test_list_pane_set_query_is_a_no_op_without_a_filter(engine_page: Page) -> None:
    p = engine_page
    _load(p)
    out = p.evaluate(
        """() => {
          const c = App.ui.listPane({title: 'Plain', items: [
            {id: 'a', label: 'Alpha', href: '#a'}, {id: 'b', label: 'Beta', href: '#b'}]});
          document.getElementById('harness-root').appendChild(c.el);
          c.setQuery('zzz');
          return {visible: Array.from(c.el.querySelectorAll('li')).filter((li) => !li.hidden).length,
                  inputs: c.el.querySelectorAll('input').length};
        }"""
    )
    assert out == {"visible": 2, "inputs": 0}


def test_list_pane_installs_no_document_listener(engine_page: Page) -> None:
    _load(engine_page)
    engine_page.evaluate(
        """() => {
          window.__docListeners = 0;
          const add = EventTarget.prototype.addEventListener;
          EventTarget.prototype.addEventListener = function (t, l, o) {
            if (this === document || this === window || this === document.body) window.__docListeners += 1;
            return add.call(this, t, l, o);
          };
        }"""
    )
    engine_page.evaluate(MOUNT_PANE_JS)
    engine_page.get_by_test_id("lp-filter").fill("al")
    engine_page.get_by_test_id("lp-row-alpha").focus()
    engine_page.keyboard.press("ArrowDown")
    engine_page.evaluate("() => window.__pane.destroy()")
    assert engine_page.evaluate("() => window.__docListeners") == 0


def test_list_pane_row_accessible_with_icon_badges_and_resolver(engine_page: Page) -> None:
    _mount_pane(engine_page)
    out = engine_page.evaluate(
        """() => {
          const gamma = document.querySelectorAll('.ui-list-pane-row')[2];
          return {icon: !!gamma.querySelector('.ui-list-pane-icon svg[aria-hidden=true]'),
                  badge: gamma.querySelector('.ui-list-pane-badge').textContent};
        }"""
    )
    assert out == {"icon": True, "badge": "3"}
    assert_controls_labelled_and_described(engine_page, "#harness-root")


# ── listPane additions (M25 F3 L1) ──────────────────────────────────────────


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


# Items a..f (links, so roving and focus act on real anchors), a pane with a
# count, a filter and an action, mounted after a focusable "outside" button.
MOUNT_COUNTED_JS = """(opts) => {
  const mk = (ids) => ids.map((id) => ({id, label: 'Item ' + id, meta: 'meta ' + id,
                                        href: '#' + id, testid: 'cp-row-' + id}));
  window.__mk = mk;
  const root = document.getElementById('harness-root');
  const outside = document.createElement('button');
  outside.textContent = 'Outside'; outside.setAttribute('data-testid', 'cp-outside');
  root.appendChild(outside);
  const c = App.ui.listPane(Object.assign({
    title: 'Agents', testid: 'cp-root', count: true, emptyText: 'No agents match',
    actions: [App.ui.button({label: 'New', size: 'sm', testid: 'cp-new'})],
    filter: {label: 'Filter agents', testid: 'cp-filter'},
    items: mk(['a', 'b', 'c', 'd', 'e', 'f']),
  }, opts || {}));
  window.__pane = c;
  root.appendChild(c.el);
  return true;
}"""


def _mount_counted(page: Page, opts: str = "{}") -> None:
    _load(page)
    page.evaluate(f"({MOUNT_COUNTED_JS})({opts})")


def _count_text(page: Page) -> str:
    return page.evaluate("() => document.querySelector('.ui-list-pane-total').textContent")


def _focused_testid(page: Page) -> str | None:
    return page.evaluate("() => document.activeElement && document.activeElement.dataset.testid")


def _tab_stops(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-testid=cp-root] .ui-list-pane-row'))"
        ".filter((r) => r.tabIndex === 0).map((r) => r.dataset.testid)"
    )


def test_list_pane_title_row_matches_reference_spec(engine_page: Page) -> None:
    """Section 3 title row: 14px 16px 10px padding, 8px gap, a 16px/600 --fg h2,
    then the 11px --fg-muted count, then the actions pushed to the right edge."""
    _mount_counted(engine_page)
    out = engine_page.evaluate(
        """() => {
          const root = document.querySelector('[data-testid=cp-root]');
          const header = root.querySelector('header'), hs = getComputedStyle(header);
          const h2 = header.querySelector('h2'), ts = getComputedStyle(h2);
          const count = header.querySelector('.ui-list-pane-total'), cs = getComputedStyle(count);
          const actions = header.querySelector('.ui-list-pane-actions');
          return {order: Array.from(header.children).map((n) => n.className),
                  pad: hs.padding, gap: hs.columnGap,
                  title: [ts.fontSize, ts.fontWeight, ts.color, ts.margin],
                  count: [cs.fontSize, cs.color],
                  actionsGap: header.getBoundingClientRect().right - actions.getBoundingClientRect().right,
                  countToActions: actions.getBoundingClientRect().left - count.getBoundingClientRect().right};
        }"""
    )
    assert out["order"] == ["ui-list-pane-title", "ui-list-pane-total", "ui-list-pane-actions"]
    assert out["pad"] == "14px 16px 10px" and out["gap"] == "8px"
    assert out["title"] == ["16px", "600", _rgb(DARK["fg"]), "0px"]
    assert out["count"] == ["11px", _rgb(DARK["fg_muted"])]
    assert abs(out["actionsGap"] - 16) <= 0.5  # pushed right, inside the 16px padding
    assert out["countToActions"] > 8  # margin-left: auto, not just the gap


def test_list_pane_count_reads_shown_of_total(engine_page: Page) -> None:
    _mount_counted(engine_page)
    p = engine_page
    assert _count_text(p) == "6 of 6"  # on load
    assert_controls_labelled_and_described(p, "[data-testid=cp-root]")
    flt = p.get_by_test_id("cp-filter")
    flt.fill("item a")
    assert _count_text(p) == "1 of 6"  # after a filter
    flt.fill("zzz")
    assert _count_text(p) == "0 of 6"  # no match
    expect(p.get_by_role("heading", name="No agents match")).to_be_visible()
    flt.fill("meta")
    assert _count_text(p) == "6 of 6"
    # setItems with an active query keeps the query, re-runs it and recounts.
    flt.fill("item b")
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'b', 'c', 'bb', 'x', 'y', 'z']))")
    assert flt.input_value() == "item b"
    assert _count_text(p) == "2 of 7"
    expect(p.locator("[data-testid=cp-root] .ui-list-pane-row:visible")).to_have_count(2)
    flt.fill("")
    p.evaluate("() => window.__pane.setItems(window.__mk(['a']))")
    assert _count_text(p) == "1 of 1"  # after setItems
    p.evaluate("() => window.__pane.setItems([])")
    assert _count_text(p) == ""  # nothing to count: empty (an accepted variation)


def test_list_pane_count_is_opt_in(engine_page: Page) -> None:
    _mount_pane(engine_page)
    assert (
        engine_page.evaluate("() => document.querySelectorAll('.ui-list-pane-total').length") == 0
    )


def test_list_pane_intro_paragraph(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          const c = App.ui.listPane({title: 'Library', intro: 'Things agents can use.',
            items: [{id: 'k', label: 'KB', href: '#k'}]});
          document.getElementById('harness-root').appendChild(c.el);
          const p = c.el.querySelector('.ui-list-pane-intro'), s = getComputedStyle(p);
          const none = App.ui.listPane({title: 'T', items: []});
          return {tag: p.tagName, text: p.textContent, after: p.previousElementSibling.tagName,
                  style: [s.margin, s.padding, s.fontSize, s.color],
                  absent: none.el.querySelectorAll('.ui-list-pane-intro').length};
        }"""
    )
    assert out["tag"] == "P" and out["text"] == "Things agents can use."
    assert out["after"] == "HEADER"  # directly below the title row
    assert out["style"] == ["0px", "0px 16px 8px", "11px", _rgb(DARK["fg_muted"])]
    assert out["absent"] == 0


GROUPS_JS = """() => {
  const it = (id) => ({id, label: 'Row ' + id, href: '#' + id, testid: 'gp-' + id});
  const c = App.ui.listPane({title: 'Library', filter: {label: 'Filter library', testid: 'gp-filter'},
    emptyText: 'Nothing matches',
    groups: [
      {label: 'Knowledge bases', emptyText: 'No knowledge bases yet.', items: [it('k1'), it('k2')]},
      {label: 'MCP servers', emptyText: 'No MCP servers yet.', items: []},
      {label: 'Silent', items: []},
      {label: 'Connectors', emptyText: 'No connectors yet.', items: [it('c1')]},
    ]});
  window.__pane = c;
  document.getElementById('harness-root').appendChild(c.el);
  return true;
}"""


def _groups(page: Page) -> list[list]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.ui-list-pane-group')).map((g) => [
          g.querySelector('.ui-list-pane-caption').textContent, g.hidden,
          g.querySelector('.ui-list-pane-group-empty') ? g.querySelector('.ui-list-pane-group-empty').textContent : null])"""
    )


def test_list_pane_group_empty_text(engine_page: Page) -> None:
    _load(engine_page)
    p = engine_page
    p.evaluate(GROUPS_JS)
    # A zero-item group with emptyText keeps its caption and shows its line; a
    # zero-item group without one stays hidden.
    assert _groups(p) == [
        ["Knowledge bases", False, None],
        ["MCP servers", False, "No MCP servers yet."],
        ["Silent", True, None],
        ["Connectors", False, None],
    ]
    line = p.locator(".ui-list-pane-group-empty")
    expect(line).to_be_visible()
    s = p.evaluate(
        "() => { const s = getComputedStyle(document.querySelector('.ui-list-pane-group-empty'));"
        " return [s.fontSize, s.color]; }"
    )
    assert s == ["11px", _rgb(DARK["fg_muted"])]
    # The empty line is not a row: no tabindex, not a list item, and roving skips it.
    assert p.evaluate(
        "() => { const l = document.querySelector('.ui-list-pane-group-empty');"
        " return [l.tagName, l.hasAttribute('tabindex'), !!l.closest('li'), l.tabIndex]; }"
    ) == ["P", False, False, -1]
    p.get_by_test_id("gp-k2").focus()
    p.keyboard.press("ArrowDown")
    assert _focused_testid(p) == "gp-c1"
    assert_controls_labelled_and_described(p, ".ui-list-pane")
    # A group whose rows are all filtered out hides, caption included; empty-group
    # lines hide while a query is active (they have nothing to match).
    p.get_by_test_id("gp-filter").fill("Row c1")
    assert _groups(p) == [
        ["Knowledge bases", True, None],
        ["MCP servers", True, "No MCP servers yet."],
        ["Silent", True, None],
        ["Connectors", False, None],
    ]
    p.get_by_test_id("gp-filter").fill("")
    assert [g[1] for g in _groups(p)] == [False, False, True, False]


def test_list_pane_all_groups_empty_shows_the_group_lines(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          const c = App.ui.listPane({title: 'Library', count: true, emptyText: 'Nothing at all',
            groups: [{label: 'A', emptyText: 'No A yet.', items: []}, {label: 'B', emptyText: 'No B yet.', items: []}]});
          document.getElementById('harness-root').appendChild(c.el);
          return {body: c.el.querySelector('.ui-list-pane-body').hidden,
                  empty: c.el.querySelector('.ui-list-pane-empty').hidden,
                  lines: Array.from(c.el.querySelectorAll('.ui-list-pane-group-empty')).map((n) => n.textContent),
                  rows: c.el.querySelectorAll('.ui-list-pane-row').length,
                  count: c.el.querySelector('.ui-list-pane-total').textContent};
        }"""
    )
    assert out == {
        "body": False,
        "empty": True,
        "lines": ["No A yet.", "No B yet."],
        "rows": 0,
        "count": "",
    }


ROW_STYLE_JS = """(opts, kind) => {
  const items = ['a', 'b', 'c'].map((id) => Object.assign({id, label: 'Name ' + id, meta: 'model-' + id},
    kind === 'button' ? {onSelect: () => {}} : {href: '#' + id}));
  const c = App.ui.listPane(Object.assign({title: 'Styled', items, testid: 'rs-root'}, opts));
  window.__pane = c;
  document.getElementById('harness-root').appendChild(c.el);
  const rows = () => Array.from(c.el.querySelectorAll('.ui-list-pane-row'));
  const probe = () => rows().map((r) => {
    const s = getComputedStyle(r);
    return {pad: s.padding, h: r.getBoundingClientRect().height, border: s.borderTopWidth + ' ' + s.borderTopStyle + ' ' + s.borderTopColor,
            shadow: s.boxShadow, bg: s.backgroundColor, font: s.fontSize, gap: s.columnGap};
  });
  const before = probe();
  c.setSelected('b');
  const after = probe();
  const list = getComputedStyle(c.el.querySelector('.ui-list-pane-list'));
  return {before, after, listGap: list.rowGap};
}"""


@pytest.mark.parametrize(
    ("row_style", "pad", "list_gap"),
    [("agents", "7px 10px", "0px"), ("library", "8px 10px", "2px")],
)
def test_list_pane_row_style_geometry_and_border_selection(
    engine_page: Page, row_style: str, pad: str, list_gap: str
) -> None:
    _load(engine_page)
    out = engine_page.evaluate(f"({ROW_STYLE_JS})({{rowStyle: '{row_style}'}})")
    accent = _rgb(DARK["accent"])
    assert out["listGap"] == list_gap
    for row in out["before"]:
        assert row["pad"] == pad and row["font"] == "13px" and row["gap"] == "10px", row
        assert row["border"] == "1px solid rgba(0, 0, 0, 0)", row  # transparent at rest
        assert row["shadow"] == "none", row
    sel = out["after"][1]
    assert sel["border"] == f"1px solid {accent}" and sel["shadow"] == "none", sel
    assert sel["bg"] != "rgba(0, 0, 0, 0)", sel
    # Selecting changes no row's height (the rest border is already paid for).
    assert [r["h"] for r in out["after"]] == [r["h"] for r in out["before"]]


def test_list_pane_forced_colors_cover_both_selection_models(engine_page: Page) -> None:
    """Forced colours drop the default model's box-shadow ring and colour the
    opt-in model's border: either way the selected row carries a solid 1px
    border that NO other row shows, and the rowStyle row keeps its height.

    The flight-end review: link and button rows alike; and a rowStyle rest
    border is forced to Canvas, since its transparent colour was forced to the
    row's text colour (every row read as selected) and the rowStyle selected
    rule outranked the forced-colours one."""
    if engine_page.context.browser.browser_type.name != "chromium":
        pytest.skip(
            "WebKit has no forced-colors emulation in Playwright; asserted in chromium only"
        )
    _load(engine_page)
    engine_page.emulate_media(forced_colors="active")
    styled = engine_page.evaluate(f"({ROW_STYLE_JS})({{rowStyle: 'library'}})")
    plain = engine_page.evaluate(f"({ROW_STYLE_JS})({{}})")
    engine_page.evaluate("() => { document.getElementById('harness-root').textContent = ''; }")
    # Button rows (aria-current="true", the flight-end review) get the same cue.
    styled_btn = engine_page.evaluate(f"({ROW_STYLE_JS})({{rowStyle: 'library'}}, 'button')")
    plain_btn = engine_page.evaluate(f"({ROW_STYLE_JS})({{}}, 'button')")
    for out in (styled, plain, styled_btn, plain_btn):
        sel = out["after"][1]
        assert sel["border"].startswith("1px solid"), sel
        for rest in (out["after"][0], out["after"][2]):
            assert rest["border"] != sel["border"], out
    assert [r["h"] for r in styled["after"]] == [r["h"] for r in styled["before"]]
    assert [r["h"] for r in styled_btn["after"]] == [r["h"] for r in styled_btn["before"]]


def test_list_pane_row_style_wins_over_compact_density(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(f"({ROW_STYLE_JS})({{rowStyle: 'agents', density: 'compact'}})")
    assert {r["pad"] for r in out["before"]} == {"7px 10px"}


def test_list_pane_default_row_style_is_unchanged(engine_page: Page) -> None:
    """Without rowStyle: no border, 8px 10px, 2px list gap, and the inset ring."""
    _load(engine_page)
    out = engine_page.evaluate(f"({ROW_STYLE_JS})({{}})")
    assert out["listGap"] == "2px"
    for row in out["before"]:
        assert row["pad"] == "8px 10px" and row["border"].startswith("0px"), row
    sel = out["after"][1]
    assert "inset" in sel["shadow"] and _rgb(DARK["accent"]) in sel["shadow"], sel
    # 'chats' became a known style in M25 F4 L1; any other name still throws.
    assert _throws(engine_page, "App.ui.listPane({title: 'T', rowStyle: 'bogus'})") == (
        'App.ui.listPane: unknown rowStyle "bogus"'
    )


SCROLL_JS = """() => {
  const host = document.createElement('div');
  host.style.cssText = 'display:flex;flex-direction:column;height:240px;width:300px;overflow:hidden';
  document.getElementById('harness-root').appendChild(host);
  const items = [];
  for (let i = 0; i < 30; i++) items.push({id: 'r' + i, label: 'Row ' + i, meta: 'meta', href: '#r' + i, testid: 'sc-' + i});
  const c = App.ui.listPane({title: 'Thirty', count: true, rowStyle: 'agents', selectedId: 'r25',
    filter: {label: 'Filter thirty', testid: 'sc-filter'}, items});
  window.__pane = c;
  host.appendChild(c.el);
  window.__boxes = () => {
    const body = c.el.querySelector('.ui-list-pane-body').getBoundingClientRect();
    const row = c.el.querySelector('[data-testid=sc-25]').getBoundingClientRect();
    return {inside: row.top >= body.top - 0.5 && row.bottom <= body.bottom + 0.5,
            bottomGap: body.bottom - row.bottom, scrollTop: c.el.querySelector('.ui-list-pane-body').scrollTop,
            hostTop: host.scrollTop, docTop: document.scrollingElement.scrollTop};
  };
  return true;
}"""


def test_list_pane_scroll_to_selected(engine_page: Page) -> None:
    _load(engine_page)
    p = engine_page
    p.evaluate(SCROLL_JS)
    before = p.evaluate("() => window.__boxes()")
    assert before["inside"] is False and before["scrollTop"] == 0  # row 25 starts below the fold
    p.evaluate("() => window.__pane.scrollToSelected()")
    after = p.evaluate("() => window.__boxes()")
    assert after["inside"] is True, after
    # block: 'nearest' scrolls the least: the row lands on the body's bottom edge
    # (within the body's 12px bottom padding), and only the body scrolls.
    assert after["bottomGap"] <= 12.5, after
    assert after["hostTop"] == 0 and after["docTop"] == 0, after


def test_list_pane_scroll_to_selected_no_ops(engine_page: Page) -> None:
    _load(engine_page)
    p = engine_page
    p.evaluate(SCROLL_JS)
    # The filter hides the selected row: a no-op (the tab stop moves to row 1).
    p.get_by_test_id("sc-filter").fill("Row 1")
    p.evaluate("() => window.__pane.scrollToSelected()")
    assert p.evaluate("() => window.__boxes().scrollTop") == 0
    # The filter clears: the caller can bring the row back into view.
    p.get_by_test_id("sc-filter").fill("")
    p.evaluate("() => window.__pane.scrollToSelected()")
    assert p.evaluate("() => window.__boxes().inside") is True
    # No selection: a no-op.
    p.evaluate(
        "() => { const b = document.querySelector('.ui-list-pane-body'); b.scrollTop = 0;"
        " window.__pane.setSelected(null); window.__pane.scrollToSelected(); }"
    )
    assert p.evaluate("() => window.__boxes().scrollTop") == 0


GROUPS_SCROLL_JS = """() => {
  const host = document.createElement('div');
  host.style.cssText = 'display:flex;flex-direction:column;height:240px;width:300px;overflow:hidden';
  document.getElementById('harness-root').appendChild(host);
  const group = (id, n) => {
    const items = [];
    for (let i = 0; i < n; i++) items.push({id: id + i, label: id.toUpperCase() + ' row ' + i, href: '#' + id + i});
    return {id, label: 'Group ' + id.toUpperCase(), emptyText: 'Nothing in ' + id, items};
  };
  const c = App.ui.listPane({title: 'Grouped', rowStyle: 'library',
    filter: {label: 'Filter grouped', testid: 'sg-filter'},
    groups: [group('a', 8), group('b', 8), group('c', 8), {id: 'd', label: 'Group D', emptyText: 'Nothing in d', items: []}]});
  window.__pane = c;
  host.appendChild(c.el);
  const body = c.el.querySelector('.ui-list-pane-body');
  window.__groupBox = (label) => {
    const cap = Array.from(c.el.querySelectorAll('.ui-list-pane-caption')).find((n) => n.textContent === label);
    const b = body.getBoundingClientRect(), g = cap.parentElement.getBoundingClientRect();
    return {topGap: g.top - b.top, visible: g.top >= b.top - 0.5 && g.bottom <= b.bottom + 0.5,
            scrollTop: body.scrollTop, hostTop: host.scrollTop, docTop: document.scrollingElement.scrollTop};
  };
  return true;
}"""


def test_list_pane_scroll_to_group(engine_page: Page) -> None:
    """``scrollToGroup(id)`` brings a group below the fold to the body's top,
    scrolling the body only; a group already wholly visible is left alone."""
    _load(engine_page)
    p = engine_page
    p.evaluate(GROUPS_SCROLL_JS)
    before = p.evaluate("() => window.__groupBox('Group C')")
    assert before["scrollTop"] == 0 and before["topGap"] > 240, before
    p.evaluate("() => window.__pane.scrollToGroup('c')")
    after = p.evaluate("() => window.__groupBox('Group C')")
    assert abs(after["topGap"]) <= 0.5, after
    assert after["scrollTop"] > 0, after
    assert after["hostTop"] == 0 and after["docTop"] == 0, after
    # An empty group (its caption and empty line) scrolls the same way.
    p.evaluate("() => window.__pane.scrollToGroup('d')")
    d = p.evaluate("() => window.__groupBox('Group D')")
    assert d["visible"] is True, d
    # Back up to the first group: its top meets the body's top (scrollTop 0).
    p.evaluate("() => window.__pane.scrollToGroup('a')")
    a = p.evaluate("() => window.__groupBox('Group A')")
    assert a["scrollTop"] == 0 and abs(a["topGap"]) <= 0.5, a
    # Already wholly visible (the small group D, nudged 3px down): no scroll.
    p.evaluate("() => window.__pane.scrollToGroup('d')")
    p.evaluate(
        "() => { const b = document.querySelector('.ui-list-pane-body'); b.scrollTop -= 3; }"
    )
    nudged = p.evaluate("() => document.querySelector('.ui-list-pane-body').scrollTop")
    assert p.evaluate("() => window.__groupBox('Group D').visible") is True
    p.evaluate("() => window.__pane.scrollToGroup('d')")
    assert p.evaluate("() => document.querySelector('.ui-list-pane-body').scrollTop") == nudged


def test_list_pane_scroll_to_group_no_ops(engine_page: Page) -> None:
    """Unknown ids, a missing id and a group hidden by the filter are no-ops."""
    _load(engine_page)
    p = engine_page
    p.evaluate(GROUPS_SCROLL_JS)
    body_top = "() => document.querySelector('.ui-list-pane-body').scrollTop"
    for expr in (
        "scrollToGroup('nope')",
        "scrollToGroup()",
        "scrollToGroup(null)",
        "scrollToGroup('')",
    ):
        p.evaluate(f"() => window.__pane.{expr}")
        assert p.evaluate(body_top) == 0, expr
    # The filter hides every row of group C (and the empty lines): a no-op.
    p.get_by_test_id("sg-filter").fill("A row")
    p.evaluate("() => window.__pane.scrollToGroup('c')")
    assert p.evaluate(body_top) == 0
    assert p.evaluate("() => window.__groupBox('Group C').visible") is False


def test_list_pane_group_ids_are_optional_and_unique(engine_page: Page) -> None:
    """``group.id`` is optional; a duplicate id throws before any DOM change."""
    _load(engine_page)
    assert (
        _throws(
            engine_page,
            "App.ui.listPane({title: 'T', groups: [{id: 'a', label: 'A', items: []},"
            " {id: 'a', label: 'B', items: []}]});",
        )
        == "listPane duplicate group id a"
    )
    # Mixed: one group with an id, one without, is fine.
    assert (
        _throws(
            engine_page,
            "App.ui.listPane({title: 'T', groups: [{id: 'a', label: 'A', items: []},"
            " {label: 'B', items: []}]});",
        )
        == ""
    )
    engine_page.evaluate(
        "() => { window.__c = App.ui.listPane({title: 'T', groups: [{id: 'g', label: 'G',"
        " items: [{id: 'ok', label: 'OK', href: '#'}]}]}); }"
    )
    msg = engine_page.evaluate(
        "() => { try { window.__c.setItems([{id: 'x', label: 'X', items: []},"
        " {id: 'x', label: 'Y', items: []}]); } catch (e) { return e.message; } }"
    )
    assert msg == "listPane duplicate group id x"
    assert engine_page.evaluate("() => window.__c.el.querySelectorAll('li').length") == 1


def test_list_pane_name_suffix_extends_the_accessible_name_only(engine_page: Page) -> None:
    _load(engine_page)
    p = engine_page
    p.evaluate(
        """() => {
          const c = App.ui.listPane({title: 'Agents', items: [
            {id: 'r', label: 'Research assistant', nameSuffix: ', Claude Max', href: '#r', testid: 'ns-link'},
            {id: 'b', label: 'Builder', nameSuffix: ', Local Ollama', onSelect: () => {}, testid: 'ns-button'},
            {id: 'p', label: 'Plain', href: '#p', testid: 'ns-plain'},
            {id: 'm', label: 'Mixer', meta: 'gpt-4.1-mini', nameSuffix: ', OpenAI,', href: '#m', testid: 'ns-meta'},
          ]});
          document.getElementById('harness-root').appendChild(c.el);
          return true;
        }"""
    )
    # The suffix is its own (visually hidden, so blockified) text run: the
    # accessible-name algorithm may separate it from the label with a space, so
    # the order is pinned, not the separator.
    link_snapshot = p.get_by_test_id("ns-link").aria_snapshot()
    button_snapshot = p.get_by_test_id("ns-button").aria_snapshot()
    assert re.search(r'^- link "Research assistant\s*, Claude Max"', link_snapshot), link_snapshot
    assert re.search(r'^- button "Builder\s*, Local Ollama"', button_snapshot), button_snapshot
    # With meta after it, the suffix carries a trailing separator too, so the
    # name reads "label, Provider, meta" (the Agents rows; the flight-end review).
    meta_snapshot = p.get_by_test_id("ns-meta").aria_snapshot()
    assert re.search(r'^- link "Mixer\s*, OpenAI,\s*gpt-4\.1-mini"', meta_snapshot), meta_snapshot
    named = re.compile(r"^Research assistant\s*, Claude Max$")
    expect(p.get_by_role("link", name=named)).to_have_count(1)
    expect(p.get_by_role("link", name="Plain", exact=True)).to_have_count(1)
    out = p.evaluate(
        """() => {
          const row = document.querySelector('[data-testid=ns-link]');
          const span = row.querySelector('.visually-hidden'), r = span.getBoundingClientRect();
          const label = row.querySelector('.ui-list-pane-label');
          return {aria: row.hasAttribute('aria-label'), text: span.textContent, w: r.width, h: r.height,
                  label: label.textContent, plain: document.querySelectorAll('[data-testid=ns-plain] .visually-hidden').length};
        }"""
    )
    # Never aria-label (it would replace the visible name for voice control).
    assert out["aria"] is False and out["text"] == ", Claude Max"
    assert out["w"] <= 1 and out["h"] <= 1  # not shown
    assert out["label"] == "Research assistant" and out["plain"] == 0


def test_list_pane_set_items_keeps_focus_on_the_same_row(engine_page: Page) -> None:
    """Focus on 'b' (NOT the selected row): a rebuild that keeps 'b' keeps focus
    on the new 'b' row and makes it the single tab stop."""
    _mount_counted(engine_page, "{selectedId: 'a'}")
    p = engine_page
    p.get_by_test_id("cp-row-b").focus()
    p.evaluate("() => { window.__old = document.activeElement; }")
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'x', 'b', 'c']))")
    assert _focused_testid(p) == "cp-row-b"
    assert p.evaluate("() => document.activeElement !== window.__old")  # really rebuilt
    assert _tab_stops(p) == ["cp-row-b"]
    assert p.evaluate("() => document.querySelector('[aria-current=page]').dataset.testid") == (
        "cp-row-a"
    )


def test_list_pane_set_items_without_the_focused_row(engine_page: Page) -> None:
    _mount_counted(engine_page, "{selectedId: 'c'}")
    p = engine_page
    p.get_by_test_id("cp-row-b").focus()
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'c', 'd']))")
    assert _focused_testid(p) == "cp-row-c"  # the selected row
    assert _tab_stops(p) == ["cp-row-c"]
    # No selection: the first row.
    p.evaluate("() => window.__pane.setSelected(null)")
    p.get_by_test_id("cp-row-d").focus()
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'c']))")
    assert _focused_testid(p) == "cp-row-a"
    assert _tab_stops(p) == ["cp-row-a"]


def test_list_pane_store_notification_mid_roving_keeps_focus(engine_page: Page) -> None:
    """A store notification (async, after a keydown) rebuilds the rows while the
    user roves: focus stays on the roved-to row and roving carries on from it."""
    _mount_counted(engine_page, "{selectedId: 'a'}")
    p = engine_page
    p.get_by_test_id("cp-row-a").focus()
    p.keyboard.press("ArrowDown")
    assert _focused_testid(p) == "cp-row-b"
    p.evaluate(
        """() => new Promise((resolve) => {
          setTimeout(() => { window.__pane.setItems(window.__mk(['a', 'b', 'c', 'd', 'e', 'f', 'g'])); resolve(); }, 0);
        })"""
    )
    assert _focused_testid(p) == "cp-row-b"
    assert _tab_stops(p) == ["cp-row-b"]
    p.keyboard.press("ArrowDown")
    assert _focused_testid(p) == "cp-row-c"
    p.keyboard.press("End")
    assert _focused_testid(p) == "cp-row-g"  # the new row is reachable


def test_list_pane_set_items_with_no_visible_row_focuses_the_filter(engine_page: Page) -> None:
    """The rebuild leaves no row matching the active query: focus goes to the
    filter rather than dropping to <body>."""
    _mount_counted(engine_page)
    p = engine_page
    p.get_by_test_id("cp-filter").fill("item b")
    p.get_by_test_id("cp-row-b").focus()
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'c']))")
    assert _focused_testid(p) == "cp-filter"
    assert _count_text(p) == "0 of 2"


def test_list_pane_set_items_leaves_outside_focus_alone(engine_page: Page) -> None:
    _mount_counted(engine_page, "{selectedId: 'c'}")
    p = engine_page
    p.get_by_test_id("cp-outside").focus()
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'b', 'c']))")
    assert _focused_testid(p) == "cp-outside"
    assert _tab_stops(p) == ["cp-row-c"]  # the normal rule: the selected row


def test_list_pane_set_items_keeps_the_scroll_position(engine_page: Page) -> None:
    _load(engine_page)
    p = engine_page
    p.evaluate(SCROLL_JS)
    p.evaluate("() => window.__pane.scrollToSelected()")
    top = p.evaluate("() => window.__boxes().scrollTop")
    assert top > 0
    p.evaluate("() => window.__pane.setItems(window.__pane.getItems())")
    assert p.evaluate("() => window.__boxes().scrollTop") == top


def test_list_pane_get_items_returns_the_current_items(engine_page: Page) -> None:
    _mount_counted(engine_page)
    p = engine_page
    assert p.evaluate("() => window.__pane.getItems().map((i) => i.id)") == list("abcdef")
    p.evaluate(
        "() => window.__pane.setItems([{label: 'G', items: window.__mk(['z'])},"
        " {label: 'H', emptyText: 'none', items: []}, {label: 'I', items: window.__mk(['y'])}])"
    )
    assert p.evaluate("() => window.__pane.getItems().map((i) => i.id)") == ["z", "y"]


def test_list_pane_item_lead_sits_before_the_text_and_never_shrinks(engine_page: Page) -> None:
    """M25 F3 L3: ``item.lead`` is a caller node placed directly before the
    row's text (after an icon), in a ``.ui-list-pane-lead`` wrapper that does
    not shrink; it is not part of the name; a non-node lead throws."""
    _load(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => {
          const dot = () => { const s = document.createElement('span');
            s.className = 'probe-dot'; s.setAttribute('aria-hidden', 'true');
            s.style.cssText = 'display:inline-block;width:8px;height:8px'; return s; };
          const c = App.ui.listPane({title: 'Leads', items: [
            {id: 'a', label: 'A very long agent name that has to ellipsize in a narrow row', meta: 'model-x',
             lead: dot(), href: '#a', testid: 'ld-a'},
            {id: 'b', label: 'With icon', icon: 'chat', lead: dot(), href: '#b', testid: 'ld-b'},
            {id: 'c', label: 'No lead', href: '#c', testid: 'ld-c'},
          ]});
          const host = document.getElementById('harness-root');
          host.style.width = '200px';
          host.appendChild(c.el);
          const kids = (id) => Array.from(document.querySelector('[data-testid=' + id + ']').children)
            .map((n) => n.className);
          const wrap = document.querySelector('[data-testid=ld-a] .ui-list-pane-lead');
          return {a: kids('ld-a'), b: kids('ld-b'), c: kids('ld-c'), flex: getComputedStyle(wrap).flexShrink,
                  w: wrap.getBoundingClientRect().width, inner: wrap.firstElementChild.className};
        }"""
    )
    assert out["a"] == ["ui-list-pane-lead", "ui-list-pane-text"], out
    assert out["b"] == ["ui-list-pane-icon", "ui-list-pane-lead", "ui-list-pane-text"], out
    assert out["c"] == ["ui-list-pane-text"], out
    assert out["flex"] == "0" and out["w"] == 8 and out["inner"] == "probe-dot", out
    # The lead is not part of the row's name.
    expect(p.get_by_role("link", name="No lead", exact=True)).to_have_count(1)
    expect(p.get_by_role("link", name="With icon", exact=True)).to_have_count(1)
    assert "lead must be a node" in _throws(
        p, "App.ui.listPane({title: 'x', items: [{id: 'a', label: 'a', href: '#a', lead: 'dot'}]})"
    )


def test_list_pane_empty_text_function_names_the_query(engine_page: Page) -> None:
    """M25 F3 L3: ``emptyText`` may be a function of the TRIMMED query; the
    empty state's title and the filter status both follow it ('' = no query)."""
    _load(engine_page)
    p = engine_page
    p.evaluate(
        """() => {
          window.__calls = [];
          const c = App.ui.listPane({title: 'Agents', count: true,
            filter: {label: 'Filter agents', testid: 'et-filter'},
            emptyText: (q) => { window.__calls.push(q); return q ? 'No agents match "' + q + '".' : 'No agents yet.'; },
            items: [{id: 'a', label: 'alpha', href: '#a'}, {id: 'b', label: 'beta', href: '#b'}]});
          document.getElementById('harness-root').appendChild(c.el);
          window.__et = c;
          return true;
        }"""
    )
    title = p.locator(".ui-list-pane-empty .ui-empty-title")
    status = p.locator(".ui-list-pane-status")
    p.get_by_test_id("et-filter").fill("  zz  ")
    expect(title).to_have_text('No agents match "zz".')
    expect(p.locator(".ui-list-pane-empty")).to_be_visible()
    expect(status).to_have_text('No agents match "zz".')
    assert p.evaluate("() => window.__calls.includes('zz')") is True
    p.get_by_test_id("et-filter").fill("al")
    expect(p.locator(".ui-list-pane-empty")).to_be_hidden()
    expect(status).to_have_text("1 result")
    p.get_by_test_id("et-filter").fill("")
    p.evaluate("() => window.__et.setItems([])")
    expect(title).to_have_text("No agents yet.")
    expect(p.locator(".ui-list-pane-empty")).to_be_visible()


# ── probe mount script ──────────────────────────────────────────────────────


def test_probe_mount_script_mounts_and_resolves(engine_page: Page) -> None:
    """The WebKitGTK probe's setup script is also exercised here so it cannot rot."""
    _load(engine_page)
    src = PROBE_MOUNT_JS.read_text()
    # The probe evaluates a setup script as a sync expression ending in true.
    assert engine_page.evaluate(f"(function () {{ {src}\n;return true; }})()") is True
    assert_controls_labelled_and_described(engine_page, "#ui-probe-root")
    n = engine_page.evaluate(
        "() => document.querySelectorAll('#ui-probe-root .ui-list-pane-row').length"
    )
    assert n >= 3
    # M25 F1 L4: the L4 controls are mounted too
    mounted = engine_page.evaluate(
        """() => ({checkboxes: document.querySelectorAll('#ui-probe-root .ui-checkbox').length,
                    toggles: document.querySelectorAll('#ui-probe-root [role=switch]').length,
                    mixed: document.querySelectorAll('#ui-probe-root .checkbox-primary:indeterminate').length,
                    badges: document.querySelectorAll('#ui-probe-root .badge').length,
                    empties: document.querySelectorAll('#ui-probe-root .ui-empty-title').length})"""
    )
    assert mounted == {
        "checkboxes": 3,
        "toggles": 2,
        "mixed": 1,
        "badges": 3,
        "empties": 4,
    }  # 2 explicit + 1 hidden per list pane
    # idempotent: a second run replaces, never duplicates, the probe root
    assert engine_page.evaluate(f"(function () {{ {src}\n;return true; }})()") is True
    assert engine_page.evaluate("() => document.querySelectorAll('#ui-probe-root').length") == 1

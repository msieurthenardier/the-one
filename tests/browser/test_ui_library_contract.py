# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for the committed ``App.ui`` factories
(M25 F1 L2): core helpers, ``button``, ``textInput`` / ``field`` and ``listPane``.

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``
(no app spawn). Falls in the ``shared`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import STATIC_DIR, load_harness
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
    assert p.evaluate("() => document.querySelector('[aria-current=page]').textContent").startswith(
        "Gamma"
    )
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

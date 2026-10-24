# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.tabs`` (M31 F2 L4, flight DD3/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.

The style comparisons hand-write the pre-library markup the (since migrated) callers once built
with HTML strings, and compare a FIXED property list.
Area-scoped rules are compared inside one explicit wrapper per test: ``area-studio`` for the
agent editor's tablist, ``area-admin`` + ``settings-list`` for the Built-in tools page's.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

PROPS_JS = """const PROPS = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'marginBottom',
  'fontSize', 'fontWeight', 'fontFamily', 'lineHeight', 'borderBottomWidth', 'borderBottomStyle',
  'borderBottomColor', 'borderTopWidth', 'borderRadius', 'backgroundColor', 'color', 'height',
  'columnGap', 'display', 'overflowY', 'flexGrow'];
const snap = (el) => { const s = getComputedStyle(el); const o = {}; PROPS.forEach((p) => { o[p] = s[p]; }); return o; };"""

ITEMS = "[{id: 'a', label: 'General', testid: 't-a'}, {id: 'b', label: 'Rules and notes', testid: 't-b'}, {id: 'c', label: 'Tools', testid: 't-c'}]"

MOUNT = f"""(extra) => {{
  window.__ch = [];
  const o = Object.assign({{label: 'Settings', items: {ITEMS}, initial: 'a', idPrefix: 'tt',
    onChange: (id) => window.__ch.push(id)}}, extra || {{}});
  window.__tabs = App.ui.tabs(o);
  document.getElementById('harness-root').appendChild(window.__tabs.el || window.__tabs.tablist);
  if (!window.__tabs.el) document.getElementById('harness-root').appendChild(window.__tabs.panels);
  return true;
}}"""


def _mount(page: Page, extra: str = "null") -> None:
    load_harness(page)
    page.evaluate(f"({MOUNT})({extra})")


def test_dom_shape_roles_and_ids(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => {
          const t = window.__tabs, el = t.el;
          const tabs = Array.from(t.tablist.querySelectorAll('[role=tab]'));
          const panels = Array.from(t.panels.querySelectorAll('[role=tabpanel]'));
          return {
            root: el.className, kids: Array.from(el.children).map((k) => k.className),
            list: [t.tablist.getAttribute('role'), t.tablist.getAttribute('aria-label'), t.tablist.className],
            tabs: tabs.map((b) => [b.tagName, b.className, b.id, b.getAttribute('aria-controls'), b.getAttribute('aria-selected'),
                                   b.getAttribute('tabindex'), b.dataset.tabId, b.getAttribute('data-testid'), b.type]),
            panels: panels.map((p) => [p.className, p.id, p.getAttribute('aria-labelledby'), p.hidden, p.dataset.tabId]),
            link: tabs.every((b, i) => panels[i].getAttribute('aria-labelledby') === b.id && b.getAttribute('aria-controls') === panels[i].id),
            api: Object.keys(t).sort(), sel: t.selected(), panelA: t.panel('a') === panels[0], panelX: t.panel('x'),
            wrapper: [getComputedStyle(el).display, getComputedStyle(el).flexDirection, getComputedStyle(el).minHeight],
            padding: getComputedStyle(t.panels).paddingTop
          };
        }"""
    )
    assert out["root"] == "ui-tabs"
    assert out["kids"] == ["tablist", "tabpanels"]
    assert out["list"] == ["tablist", "Settings", "tablist"]
    assert out["tabs"][0] == [
        "BUTTON",
        "tab",
        "tt-tab-a",
        "tt-panel-a",
        "true",
        "0",
        "a",
        "t-a",
        "button",
    ]
    assert [t[4] for t in out["tabs"]] == ["true", "false", "false"]
    assert [t[5] for t in out["tabs"]] == ["0", "-1", "-1"]
    assert [p[3] for p in out["panels"]] == [False, True, True]
    assert out["panels"][0] == ["tabpanel", "tt-panel-a", "tt-tab-a", False, "a"]
    assert out["link"] is True
    assert out["api"] == ["destroy", "el", "panel", "panels", "select", "selected", "tablist"]
    assert out["sel"] == "a" and out["panelA"] is True and out["panelX"] is None
    assert out["wrapper"] == ["flex", "column", "0px"]
    assert out["padding"] == "0px"
    assert engine_page.evaluate("() => window.__ch") == ["a"]
    # Role structure: the tablist owns the tab elements, each named by its label.
    expect(engine_page.get_by_role("tablist", name="Settings")).to_have_count(1)
    expect(engine_page.get_by_role("tab")).to_have_count(3)
    expect(engine_page.get_by_role("tab", name="General", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(engine_page.get_by_role("tabpanel")).to_have_count(1)  # hidden panels are not exposed
    expect(engine_page.get_by_role("tabpanel", name="General")).to_have_count(1)


def test_all_tabs_are_equal_height_and_panel_class(engine_page: Page) -> None:
    _mount(engine_page, "{panelClass: 'extra-panel'}")
    out = engine_page.evaluate(
        """() => {
          const hs = Array.from(window.__tabs.tablist.children).map((b) => b.getBoundingClientRect().height);
          return {hs, cls: Array.from(window.__tabs.panels.children).map((p) => p.className)};
        }"""
    )
    assert len(set(out["hs"])) == 1 and out["hs"][0] > 0
    assert out["cls"] == ["tabpanel extra-panel"] * 3


def test_split_has_no_wrapper(engine_page: Page) -> None:
    _mount(engine_page, "{split: true}")
    out = engine_page.evaluate(
        "() => ({el: window.__tabs.el, rootKids: Array.from(document.getElementById('harness-root').children).map((k) => k.className)})"
    )
    assert out["el"] is None
    assert out["rootKids"] == ["tablist", "tabpanels"]


def test_select_selected_and_activation_state(engine_page: Page) -> None:
    _mount(engine_page)
    engine_page.get_by_test_id("t-c").click()
    out = engine_page.evaluate(
        """() => ({sel: window.__tabs.selected(), ch: window.__ch,
          ti: Array.from(window.__tabs.tablist.children).map((b) => b.getAttribute('tabindex')),
          hid: Array.from(window.__tabs.panels.children).map((p) => p.hidden)})"""
    )
    assert out == {
        "sel": "c",
        "ch": ["a", "c"],
        "ti": ["-1", "-1", "0"],
        "hid": [True, True, False],
    }
    engine_page.evaluate("window.__tabs.select('b')")
    assert engine_page.evaluate("() => [window.__tabs.selected(), window.__ch]") == [
        "b",
        ["a", "c", "b"],
    ]


def test_destroy_removes_listeners(engine_page: Page) -> None:
    _mount(engine_page)
    engine_page.evaluate("window.__tabs.destroy()")
    engine_page.get_by_test_id("t-b").click()
    engine_page.get_by_test_id("t-a").focus()
    engine_page.keyboard.press("ArrowRight")
    assert engine_page.evaluate(
        "() => [window.__tabs.selected(), document.activeElement.dataset.tabId]"
    ) == ["a", "a"]


# ── keyboard contract ────────────────────────────────────────────────────────
# (M31 F4 L06: the parity tests against the legacy ``App.tabs`` (js/tabs.js) were
# deleted with that helper; they had proved the library reproduces it, and nothing
# else loads the old file. The library's own contract is stated explicitly below.)

STATE_JS = """() => {
  const tabs = Array.from(window.__tabs.tablist.querySelectorAll('[role=tab]'));
  return {
    focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.tabId || null : null,
    sel: tabs.map((b) => b.getAttribute('aria-selected')), ti: tabs.map((b) => b.getAttribute('tabindex')),
    hid: Array.from(window.__tabs.panels.querySelectorAll('[role=tabpanel]')).map((p) => p.hidden)
  };
}"""


def test_keyboard_arrows_move_focus_and_enter_space_commit(engine_page: Page) -> None:
    _mount(engine_page)
    engine_page.get_by_test_id("t-a").focus()
    engine_page.keyboard.press("ArrowRight")
    st = engine_page.evaluate(STATE_JS)
    # Arrows move focus only: the commit state (selection, roving tabindex, panels) is unchanged.
    assert st == {
        "focus": "b",
        "sel": ["true", "false", "false"],
        "ti": ["0", "-1", "-1"],
        "hid": [False, True, True],
    }
    engine_page.keyboard.press("ArrowLeft")
    engine_page.keyboard.press("ArrowLeft")  # wraps to the last tab
    assert engine_page.evaluate(STATE_JS)["focus"] == "c"
    engine_page.keyboard.press("ArrowRight")  # and wraps forward again
    assert engine_page.evaluate(STATE_JS)["focus"] == "a"
    engine_page.keyboard.press("End")
    assert engine_page.evaluate(STATE_JS)["focus"] == "c"
    engine_page.keyboard.press("Home")
    assert engine_page.evaluate(STATE_JS)["focus"] == "a"
    engine_page.keyboard.press("End")
    engine_page.keyboard.press("Enter")
    st = engine_page.evaluate(STATE_JS)
    assert st == {
        "focus": "c",
        "sel": ["false", "false", "true"],
        "ti": ["-1", "-1", "0"],
        "hid": [True, True, False],
    }
    engine_page.keyboard.press("ArrowLeft")
    engine_page.keyboard.press("Space")
    st = engine_page.evaluate(STATE_JS)
    assert st["sel"] == ["false", "true", "false"] and st["hid"] == [True, False, True]
    assert engine_page.evaluate("() => window.__ch") == ["a", "c", "b"]


def test_keyboard_veto_keeps_the_current_tab(engine_page: Page) -> None:
    _mount(engine_page, "{onBeforeChange: (id, commit) => { window.__asked = id; }}")
    engine_page.get_by_test_id("t-a").focus()
    engine_page.keyboard.press("End")  # arrows never go through the veto
    assert engine_page.evaluate("() => window.__asked") is None
    engine_page.keyboard.press("Enter")
    assert engine_page.evaluate(
        "() => [window.__asked, window.__tabs.selected(), window.__ch]"
    ) == [
        "c",
        "a",
        ["a"],
    ]
    assert engine_page.evaluate(STATE_JS)["sel"] == ["true", "false", "false"]


def test_before_change_commit_proceeds(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{onBeforeChange: (id, commit) => { window.__pending = commit; window.__asked = id; }}",
    )
    engine_page.get_by_test_id("t-b").click()
    assert engine_page.evaluate("() => [window.__tabs.selected(), window.__asked]") == ["a", "b"]
    engine_page.evaluate("window.__pending()")
    assert engine_page.evaluate("() => window.__tabs.selected()") == "b"


# ── computed styles equal the legacy markup (DD11) ──────────────────────────


def _legacy_tablist_html() -> str:
    return (
        '<div role="tablist" class="tablist" aria-label="Legacy">'
        '<button type="button" role="tab" class="tab" aria-selected="true" tabindex="0" id="l1">General</button>'
        '<button type="button" role="tab" class="tab" aria-selected="false" tabindex="-1" id="l2">Tools</button></div>'
        '<div class="tabpanels"><div role="tabpanel" class="tabpanel" id="lp1"></div></div>'
    )


@pytest.mark.parametrize(
    ("wrapper_open", "wrapper_close", "name"),
    [
        ('<div class="area-studio">', "</div>", "area-studio"),
        ('<div class="area-admin"><div class="settings-list">', "</div></div>", "area-admin"),
    ],
)
def test_computed_styles_equal_legacy(
    engine_page: Page, wrapper_open: str, wrapper_close: str, name: str
) -> None:
    load_harness(engine_page)
    engine_page.evaluate(
        """([open, close, legacy]) => {
          const host = document.createElement('div'); host.id = 'cmp';
          document.getElementById('harness-root').appendChild(host);
          const t = App.ui.tabs({label: 'Lib', idPrefix: 'cmp', initial: 'a',
            items: [{id: 'a', label: 'General'}, {id: 'b', label: 'Tools'}]});
          host.innerHTML = open + '<div id="legacy-side">' + legacy + '</div><div id="lib-side"></div>' + close;
          host.querySelector('#lib-side').appendChild(t.el);
        }""",
        [wrapper_open, wrapper_close, _legacy_tablist_html()],
    )
    out = engine_page.evaluate(
        """() => {
          """
        + PROPS_JS
        + """
          const L = document.getElementById('legacy-side'), N = document.getElementById('lib-side');
          const pairs = {
            list: [L.querySelector('.tablist'), N.querySelector('.tablist')],
            selected: [L.querySelector('.tab[aria-selected=true]'), N.querySelector('.tab[aria-selected=true]')],
            idle: [L.querySelector('.tab[aria-selected=false]'), N.querySelector('.tab[aria-selected=false]')],
            panel: [L.querySelector('.tabpanel'), N.querySelector('.tabpanel')]
          };
          // The legacy panel is visible; show the library's too before reading its style.
          N.querySelector('.tabpanel').removeAttribute('hidden');
          const o = {};
          for (const k in pairs) o[k] = [snap(pairs[k][0]), snap(pairs[k][1])];
          return o;
        }"""
    )
    for key, (legacy, library) in out.items():
        assert library == legacy, f"{name} {key}: {library} != {legacy}"


def test_panel_id_prefix_option(engine_page: Page) -> None:
    """``panelIdPrefix`` names the panels ``<prefix>-<id>`` (the agent editor's ``agent-tab-panel-*``)
    without touching the tab ids; the default stays ``<idPrefix>-panel-<id>``."""
    _mount(engine_page, "{idPrefix: 'agent', panelIdPrefix: 'agent-tab-panel'}")
    out = engine_page.evaluate(
        """() => {
          const t = window.__tabs;
          const tabs = Array.from(t.tablist.querySelectorAll('[role=tab]'));
          const panels = Array.from(t.panels.querySelectorAll('[role=tabpanel]'));
          return {tabs: tabs.map((b) => [b.id, b.getAttribute('aria-controls')]),
                  panels: panels.map((p) => [p.id, p.getAttribute('aria-labelledby')])};
        }"""
    )
    assert out["tabs"][0] == ["agent-tab-a", "agent-tab-panel-a"]
    assert out["panels"][2] == ["agent-tab-panel-c", "agent-tab-c"]
    _mount(engine_page)
    default = engine_page.evaluate("() => window.__tabs.panel('b').id")
    assert default == "tt-panel-b"


def test_panel_padding_none_is_flush_under_area_admin(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const host = document.createElement('div'); host.className = 'area-admin';
          const inner = document.createElement('div'); inner.className = 'settings-list'; host.appendChild(inner);
          document.getElementById('harness-root').appendChild(host);
          const mk = (extra) => { const t = App.ui.tabs(Object.assign({label: 'T', idPrefix: 'p' + Math.random().toString(36).slice(2, 6), initial: 'a',
            items: [{id: 'a', label: 'A'}, {id: 'b', label: 'B'}]}, extra)); inner.appendChild(t.el); t.panel('a').hidden = false; return t; };
          const flush = mk({panelPadding: 'none'}), plain = mk({});
          const pad = (el) => { const s = getComputedStyle(el); return [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft, s.overflowY].join(' '); };
          return {flush: pad(flush.panel('a')), tl: getComputedStyle(flush.tablist).paddingLeft,
                  cls: flush.panel('a').className, tlcls: flush.tablist.className,
                  plainCls: plain.panel('a').className, plainTl: getComputedStyle(plain.tablist).paddingLeft};
        }"""
    )
    assert out["flush"] == "0px 0px 0px 0px visible" and out["tl"] == "0px"
    assert "ui-tabs--flush" in out["cls"] and "ui-tabs--flush" in out["tlcls"]
    assert "ui-tabs--flush" not in out["plainCls"]

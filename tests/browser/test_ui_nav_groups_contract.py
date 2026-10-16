# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.navGroups`` (M25 F3 L1, DD6/DD10):
the grouped nav of plain links that becomes the Settings nav. Markup, selection,
no handlers, the throw rules, reference spec section 8.1 geometry and forced colours.
Falls in the ``contracts`` browser lane; every test runs in Chromium and WebKit
(forced-colours emulation is Chromium-only in Playwright).
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import load_harness
from browser.design_tokens import DARK, LIGHT
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# The Settings nav's groups, hosted in a column that carries the host padding
# (14px 10px) and width, after a focusable "before" button.
MOUNT_JS = """(opts) => {
  const groups = [
    {label: 'General', items: [
      {id: 'appearance', label: 'Appearance', href: '#x-appearance', testid: 'ng-appearance'},
      {id: 'prompts', label: 'Prompts', href: '#x-prompts', testid: 'ng-prompts'},
      {id: 'encryption', label: 'Encryption', href: '#x-encryption', testid: 'ng-encryption'},
    ]},
    {label: 'Models', items: [
      {id: 'providers', label: 'Providers', href: '#x-providers', testid: 'ng-providers'},
    ]},
    {label: 'Defaults for agents', items: [
      {id: 'tools', label: 'Built-in tools', href: '#x-tools', testid: 'ng-tools'},
      {id: 'knowledge-indexing', label: 'Knowledge indexing', href: '#x-ki', testid: 'ng-knowledge-indexing'},
    ]},
    {label: 'Extras', items: [
      {id: 'extra-page', label: 'Extra page', href: '#x-extra', testid: 'ng-extra-page'},
    ]},
  ];
  const root = document.getElementById('harness-root');
  const before = document.createElement('button');
  before.textContent = 'Before'; before.setAttribute('data-testid', 'ng-before');
  const column = document.createElement('div');
  column.style.cssText = 'box-sizing:border-box;width:260px;padding:14px 10px;background:var(--sidebar-bg)';
  column.id = 'ng-column';
  const c = App.ui.navGroups(Object.assign({label: 'Settings', heading: 'Settings', groups, testid: 'ng-root'}, opts || {}));
  window.__ng = c;
  column.appendChild(c.el);
  root.appendChild(before); root.appendChild(column);
  return true;
}"""

ITEM_IDS = [
    "appearance",
    "prompts",
    "encryption",
    "providers",
    "tools",
    "knowledge-indexing",
    "extra-page",
]


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


def _mount(page: Page, opts: str = "{}", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT_JS})({opts})")


def _throws(page: Page, expr: str) -> str:
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


def _current(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('[aria-current]')).map((a) => a.dataset.testid + ':' + a.getAttribute('aria-current'))"
    )


# ── API and markup ──────────────────────────────────────────────────────────


def test_nav_groups_api_and_markup(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const c = window.__ng, nav = c.el;
          const groups = Array.from(nav.querySelectorAll(':scope > .ui-nav-groups-group'));
          return {
            keys: Object.keys(c).sort().join(','),
            tag: nav.tagName, label: nav.getAttribute('aria-label'), tid: nav.dataset.testid,
            first: nav.firstElementChild.tagName + ':' + nav.firstElementChild.textContent,
            h2s: nav.querySelectorAll('h2').length,
            groups: groups.map((g) => {
              const cap = g.querySelector(':scope > .ui-nav-groups-caption');
              const ul = g.querySelector(':scope > ul');
              return {cap: cap.tagName + ':' + cap.textContent,
                      labelled: ul.getAttribute('aria-labelledby') === cap.id,
                      bare: Array.from(ul.children).every((li) => li.tagName === 'LI' && li.children.length === 1 && li.firstElementChild.tagName === 'A'),
                      links: Array.from(ul.querySelectorAll('a')).map((a) => [a.textContent, a.getAttribute('href'), a.dataset.testid])};
            }),
            tabindex: Array.from(nav.querySelectorAll('a')).filter((a) => a.hasAttribute('tabindex')).length,
          };
        }"""
    )
    assert out["keys"] == "destroy,el,setSelected"
    assert out["tag"] == "NAV" and out["label"] == "Settings" and out["tid"] == "ng-root"
    assert out["first"] == "H2:Settings" and out["h2s"] == 1
    assert [g["cap"] for g in out["groups"]] == [
        "DIV:General",
        "DIV:Models",
        "DIV:Defaults for agents",
        "DIV:Extras",
    ]
    assert all(g["labelled"] and g["bare"] for g in out["groups"])
    links = [link for g in out["groups"] for link in g["links"]]
    assert [link[2] for link in links] == [f"ng-{i}" for i in ITEM_IDS]  # group order
    assert links[0] == ["Appearance", "#x-appearance", "ng-appearance"]
    assert out["tabindex"] == 0  # plain links in Tab order: no roving tabindex
    expect(p.get_by_role("navigation", name="Settings")).to_have_count(1)
    expect(p.get_by_role("heading", name="Settings", level=2)).to_have_count(1)
    expect(p.get_by_role("list", name="Models")).to_have_count(1)
    assert_controls_labelled_and_described(p, "[data-testid=ng-root]")


def test_nav_groups_heading_defaults_to_the_label(engine_page: Page) -> None:
    _mount(engine_page, "{heading: undefined, label: 'Preferences'}")
    expect(engine_page.get_by_role("navigation", name="Preferences")).to_have_count(1)
    expect(engine_page.get_by_role("heading", name="Preferences", level=2)).to_have_count(1)


# ── selection ───────────────────────────────────────────────────────────────


def test_nav_groups_aria_current_on_exactly_the_selected_item(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{selectedId: 'providers'}")
    assert _current(p) == ["ng-providers:page"]
    p.evaluate("() => window.__ng.setSelected('encryption')")
    assert _current(p) == ["ng-encryption:page"]
    p.evaluate("() => window.__ng.setSelected('no-such-page')")
    assert _current(p) == []
    p.evaluate("() => { window.__ng.setSelected('tools'); window.__ng.setSelected(null); }")
    assert _current(p) == []


def test_nav_groups_without_selection_marks_nothing(engine_page: Page) -> None:
    _mount(engine_page)
    assert _current(engine_page) == []


# ── no handlers: native navigation, plain Tab order ─────────────────────────


def test_nav_groups_binds_no_click_or_key_handlers(engine_page: Page) -> None:
    p = engine_page
    load_harness(p)
    out = p.evaluate(
        f"""() => {{
          const seen = [];
          const orig = EventTarget.prototype.addEventListener;
          EventTarget.prototype.addEventListener = function (type) {{ seen.push(type); return orig.apply(this, arguments); }};
          ({MOUNT_JS})({{selectedId: 'prompts'}});
          window.__ng.setSelected('tools');
          EventTarget.prototype.addEventListener = orig;
          const a = document.querySelector('[data-testid=ng-tools]');
          window.App.router = {{go() {{ throw new Error('navGroups touched the router'); }}}};
          const ev = new MouseEvent('click', {{bubbles: true, cancelable: true, button: 0}});
          a.addEventListener('click', (e) => e.preventDefault());  // keep the harness page put
          a.dispatchEvent(ev);
          return {{seen, onclick: a.onclick}};
        }}"""
    )
    # No listener of any kind was installed while building or selecting.
    assert out == {"seen": [], "onclick": None}


def test_nav_groups_links_follow_their_href_natively(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.get_by_test_id("ng-providers").click()
    assert p.evaluate("() => location.hash") == "#x-providers"


def test_nav_groups_items_are_plain_tab_stops(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{selectedId: 'providers'}")
    p.focus("[data-testid=ng-before]")
    p.keyboard.press("Tab")
    seen = [p.evaluate("() => document.activeElement.dataset.testid")]
    for _ in ITEM_IDS[1:]:
        p.keyboard.press("Tab")
        seen.append(p.evaluate("() => document.activeElement.dataset.testid"))
    assert seen == [f"ng-{i}" for i in ITEM_IDS]  # every item, in group order
    # Arrow keys are not handled (no roving): focus stays put.
    p.keyboard.press("ArrowUp")
    assert p.evaluate("() => document.activeElement.dataset.testid") == "ng-extra-page"


# ── edge rules ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ("{groups: [{label: 'G', items: []}]}", "App.ui.navGroups: label is required"),
        ("{label: 'N'}", "App.ui.navGroups: groups is required"),
        ("{label: 'N', groups: []}", "App.ui.navGroups: groups is required"),
        ("{label: 'N', groups: [{items: []}]}", "navGroups group 0: label required"),
        (
            "{label: 'N', groups: [{label: 'G', items: [{id: 'a', label: 'A'}]}]}",
            "navGroups item a: href required",
        ),
        (
            "{label: 'N', groups: [{label: 'G', items: [{label: 'A', href: '#a'}]}]}",
            "navGroups item: id required",
        ),
        (
            "{label: 'N', groups: [{label: 'G', items: [{id: 'a', href: '#a'}]}]}",
            "navGroups item a: label required",
        ),
        (
            "{label: 'N', groups: [{label: 'G', items: [{id: 'a', label: 'A', href: '#a'}]},"
            " {label: 'H', items: [{id: 'a', label: 'B', href: '#b'}]}]}",
            "navGroups duplicate item id a",
        ),
    ],
    ids=[
        "no-label",
        "no-groups",
        "empty-groups",
        "group-no-label",
        "no-href",
        "no-id",
        "no-item-label",
        "duplicate-id-across-groups",
    ],
)
def test_nav_groups_edge_rules_throw(engine_page: Page, args: str, message: str) -> None:
    load_harness(engine_page)
    assert _throws(engine_page, f"App.ui.navGroups({args});") == message


def test_nav_groups_destroy_makes_later_calls_no_ops(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{selectedId: 'prompts'}")
    p.evaluate("() => { window.__ng.destroy(); window.__ng.setSelected('tools'); }")
    assert _current(p) == ["ng-prompts:page"]


# ── geometry (reference spec section 8.1) ───────────────────────────────────

GEOMETRY_JS = """() => {
  const nav = document.querySelector('[data-testid=ng-root]');
  const col = document.getElementById('ng-column').getBoundingClientRect();
  const textLeft = (node) => { const r = document.createRange(); r.selectNodeContents(node); return r.getBoundingClientRect().left; };
  const h2 = nav.querySelector('h2'), hs = getComputedStyle(h2);
  const items = Array.from(nav.querySelectorAll('a')).map((a) => {
    const r = a.getBoundingClientRect(), s = getComputedStyle(a);
    return {h: r.height, w: r.width, left: r.left - col.left, text: textLeft(a) - col.left,
            font: s.fontSize, pad: s.padding, display: s.display, radius: s.borderTopLeftRadius,
            color: s.color, bg: s.backgroundColor, shadow: s.boxShadow, deco: s.textDecorationLine,
            current: a.getAttribute('aria-current')};
  });
  const caps = Array.from(nav.querySelectorAll('.ui-nav-groups-caption')).map((c) => {
    const s = getComputedStyle(c);
    return {h: c.getBoundingClientRect().height, text: textLeft(c) - col.left,
            style: [s.fontSize, s.fontWeight, s.color, s.padding],
            transform: s.textTransform, spacing: parseFloat(s.letterSpacing),
            rule: (() => { const a = getComputedStyle(c, '::after');
              return {h: parseFloat(a.height), w: parseFloat(a.width), bg: a.backgroundColor}; })()};
  });
  return {heading: {text: textLeft(h2) - col.left, top: h2.getBoundingClientRect().top - col.top,
                    style: [hs.fontSize, hs.fontWeight, hs.color, hs.marginTop, hs.marginBottom]},
          firstItemTop: nav.querySelector('a').getBoundingClientRect().top - col.top,
          items, caps};
}"""


@pytest.mark.parametrize(("theme", "pal"), [("dark", DARK), ("light", LIGHT)])
def test_nav_groups_geometry_and_colour(engine_page: Page, theme: str, pal: dict[str, str]) -> None:
    p = engine_page
    p.emulate_media(reduced_motion="reduce")
    _mount(p, "{selectedId: 'providers'}", theme)
    g = p.evaluate(GEOMETRY_JS)
    for item in g["items"]:
        assert abs(item["h"] - 28) <= 1, item  # 28px +-1 at 12px type
        assert item["font"] == "12px" and item["pad"] == "6px 10px" and item["display"] == "block"
        assert item["radius"] == "6px" and item["deco"] == "none"
        assert item["left"] == 10 and item["w"] == 240  # fills the host's content box
        if item["current"] is None:
            assert item["color"] == _rgb(pal["fg_secondary"]), item
            assert item["bg"] == "rgba(0, 0, 0, 0)" and item["shadow"] == "none", item
    (cur,) = [i for i in g["items"] if i["current"] == "page"]
    assert cur["color"] == _rgb(pal["fg"])
    assert "inset" in cur["shadow"] and _rgb(pal["accent"]) in cur["shadow"], cur
    assert cur["bg"] != "rgba(0, 0, 0, 0)"
    # Heading: 16px, 600, --fg, and its text lines up with the items' text (A3):
    # 20px from the column edge (10px column padding + 10px indent), within 1px.
    assert g["heading"]["style"] == ["16px", "600", _rgb(pal["fg"]), "0px", "0px"]
    assert abs(g["heading"]["text"] - 20) <= 1, g["heading"]
    for item in g["items"]:
        assert abs(item["text"] - g["heading"]["text"]) <= 1, (item, g["heading"])
    # Captions: the section 3 group label, aligned with the item text too.
    # M25 F6 L4 (DD13): the eyebrow with a rule: 10px semibold uppercase in
    # --fg-tertiary; the first group at 10px padding-top, every later one at 16px.
    for idx, cap in enumerate(g["caps"]):
        pad = "10px 10px 6px" if idx == 0 else "16px 10px 6px"
        assert cap["style"] == ["10px", "600", _rgb(pal["fg_tertiary"]), pad], cap
        assert cap["transform"] == "uppercase" and abs(cap["spacing"] - 0.8) <= 0.05, cap
        assert cap["rule"]["h"] == 1 and cap["rule"]["w"] > 0, cap
        assert cap["rule"]["bg"] == _rgb(pal["border"]), cap
        assert abs(cap["text"] - g["heading"]["text"]) <= 1, cap
    # The board's pitch: heading at the column's top padding, then 2px gaps.
    assert g["heading"]["top"] == 14
    cap_h = g["caps"][0]["h"]
    head_h = p.evaluate(
        "() => document.querySelector('[data-testid=ng-root] h2').getBoundingClientRect().height"
    )
    assert abs(g["firstItemTop"] - (14 + head_h + 2 + cap_h + 2)) <= 0.5, g


def test_nav_groups_hover_and_focus_ring(engine_page: Page) -> None:
    p = engine_page
    p.emulate_media(reduced_motion="reduce")
    _mount(p, "{selectedId: 'providers'}")
    p.get_by_test_id("ng-prompts").hover()
    hover = p.evaluate(
        "() => { const s = getComputedStyle(document.querySelector('[data-testid=ng-prompts]')); return [s.backgroundColor, s.color]; }"
    )
    assert hover == [_rgb(DARK["surface_elevated"]), _rgb(DARK["fg"])]
    p.get_by_test_id("ng-tools").focus()
    p.keyboard.press("Shift+Tab")  # keyboard focus, so :focus-visible applies
    ring = p.evaluate(
        """() => { const el = document.activeElement, s = getComputedStyle(el);
                   return {tid: el.dataset.testid, fv: el.matches(':focus-visible'), style: s.outlineStyle,
                           width: parseFloat(s.outlineWidth), offset: s.outlineOffset}; }"""
    )
    assert ring["tid"] == "ng-providers" and ring["fv"] is True
    assert ring["style"] == "solid" and ring["width"] >= 2
    assert ring["offset"] == "-2px"  # inset, so the aside's overflow never clips it


def test_nav_groups_forced_colors_selected_border(engine_page: Page) -> None:
    if engine_page.context.browser.browser_type.name != "chromium":
        pytest.skip(
            "WebKit has no forced-colors emulation in Playwright; asserted in chromium only"
        )
    p = engine_page
    _mount(p, "{selectedId: 'providers'}")
    p.emulate_media(forced_colors="active")
    out = p.evaluate(
        """() => Array.from(document.querySelectorAll('[data-testid=ng-root] a')).map((a) => {
          const s = getComputedStyle(a);
          return {current: a.getAttribute('aria-current'), border: s.borderTopStyle + ' ' + s.borderTopWidth,
                  h: a.getBoundingClientRect().height};
        })"""
    )
    (cur,) = [i for i in out if i["current"] == "page"]
    assert cur["border"] == "solid 1px", cur  # the Highlight border carries the selection
    rest = [i for i in out if i["current"] is None]
    assert all(i["border"].startswith("none") for i in rest), rest
    assert {round(i["h"]) for i in out} == {28}  # no layout shift on the selected item

# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.rail`` (M25 F2 L6): the workbench
rail, plus the global ``.visually-hidden`` utility it ships beside. Keyboard steps use
real ``keyboard.press``. Falls in the ``contracts`` browser lane; every test runs in
Chromium and WebKit.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import (
    STATIC_DIR,
    index_layer_statement,
    index_ui_script_paths,
    load_harness,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

MOUNT_JS = """(opts) => {
  const mk = (extra) => App.ui.rail(Object.assign({
    brand: {src: '/static/brand/topbar-icon-24.png', alt: 'GleepGlorp AI'},
    items: [
      {id: 'chats', label: 'Chats', icon: 'chat', href: '#x-chats', testid: 'r-chats'},
      {id: 'agents', label: 'Agents', icon: 'studio', href: '#x-agents', testid: 'r-agents'},
      {id: 'library', label: 'Library', icon: 'database', href: '#x-library', testid: 'r-library'},
      {id: 'settings', label: 'Settings', icon: 'admin', href: '#x-settings', testid: 'r-settings'},
    ],
  }, extra || {}));
  window.__mk = mk;
  const root = document.getElementById('harness-root');
  const before = document.createElement('button');
  before.textContent = 'Before'; before.setAttribute('data-testid', 'r-before');
  const after = document.createElement('button');
  after.textContent = 'After'; after.setAttribute('data-testid', 'r-after');
  const c = mk(opts || {});
  window.__r = c;
  root.appendChild(before); root.appendChild(c.el); root.appendChild(after);
  return true;
}"""


def _mount(page: Page, opts: str = "{}", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT_JS})({opts})")


def _active(page: Page) -> str | None:
    return page.evaluate(
        "() => document.activeElement && (document.activeElement.dataset.testid || document.activeElement.tagName)"
    )


def _stops(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-rail-item')).map((a) => a.getAttribute('tabindex'))"
    )


def _current(page: Page) -> list[str | None]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-rail-item')).map((a) => a.getAttribute('aria-current'))"
    )


def _throws(page: Page, expr: str) -> str:
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


# ── API and markup ──────────────────────────────────────────────────────────


def test_rail_api_and_markup(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const c = window.__r, nav = c.el;
          const items = Array.from(nav.querySelectorAll('a'));
          const img = nav.querySelector('img');
          return {
            keys: Object.keys(c).sort().join(','),
            tag: nav.tagName, cls: nav.className, label: nav.getAttribute('aria-label'),
            firstChild: nav.firstElementChild.tagName,
            img: img && {alt: img.getAttribute('alt'), w: img.width, h: img.height, cls: img.className},
            tags: items.map((i) => i.tagName + '/' + i.className),
            hrefs: items.map((i) => i.getAttribute('href')),
            labels: items.map((i) => i.querySelector('.ui-rail-label').textContent),
            names: items.map((i) => i.textContent),
            icons: items.map((i) => i.querySelectorAll('.ui-rail-icon > svg[aria-hidden="true"]').length),
            tids: items.map((i) => i.getAttribute('data-testid')),
            current: items.map((i) => i.getAttribute('aria-current')),
          };
        }"""
    )
    assert out["keys"] == "destroy,el,setCurrent,setHref"
    assert out["tag"] == "NAV" and out["cls"] == "ui-rail" and out["label"] == "Main"
    assert out["firstChild"] == "IMG"
    assert out["img"] == {"alt": "GleepGlorp AI", "w": 24, "h": 24, "cls": "ui-rail-brand"}
    assert out["tags"] == ["A/ui-rail-item"] * 4
    assert out["hrefs"] == ["#x-chats", "#x-agents", "#x-library", "#x-settings"]
    assert out["labels"] == ["Chats", "Agents", "Library", "Settings"]
    assert out["names"] == out["labels"]  # the link's name is its label; the icon adds nothing
    assert out["icons"] == [1, 1, 1, 1]
    assert out["tids"] == ["r-chats", "r-agents", "r-library", "r-settings"]
    # No currentId given: no aria-current before the first commit.
    assert out["current"] == [None] * 4


def test_rail_label_option_names_the_landmark(engine_page: Page) -> None:
    _mount(engine_page, "{label: 'Rail demo (dark)'}")
    expect(engine_page.get_by_role("navigation", name="Rail demo (dark)")).to_have_count(1)


def test_rail_does_not_bind_clicks_or_read_the_router(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          window.App.router = {go() { throw new Error('rail touched the router'); }};
          const a = document.querySelector('[data-testid=r-agents]');
          const ev = new MouseEvent('click', {bubbles: true, cancelable: true, button: 0});
          a.dispatchEvent(ev);
          return {prevented: ev.defaultPrevented, onclick: a.onclick};
        }"""
    )
    # Plain links: navigation belongs to the app's interceptor, not the factory.
    assert out == {"prevented": False, "onclick": None}


# ── selection and the single tab stop ───────────────────────────────────────


def test_rail_current_sets_aria_current_and_the_tab_stop(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{currentId: 'library'}")
    assert _current(p) == [None, None, "page", None]
    assert _stops(p) == ["-1", "-1", "0", "-1"]
    p.evaluate("() => window.__r.setCurrent('chats')")
    assert _current(p) == ["page", None, None, None]
    assert _stops(p) == ["0", "-1", "-1", "-1"]


def test_rail_without_current_makes_the_first_item_the_tab_stop(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    assert _stops(p) == ["0", "-1", "-1", "-1"]
    p.evaluate("() => window.__r.setCurrent('settings')")
    assert _stops(p) == ["-1", "-1", "-1", "0"]
    # An unknown id (or null) clears aria-current and falls back to the first item.
    p.evaluate("() => window.__r.setCurrent('nope')")
    assert _current(p) == [None] * 4 and _stops(p) == ["0", "-1", "-1", "-1"]
    p.evaluate("() => window.__r.setCurrent('agents'); window.__r.setCurrent(null)")
    assert _current(p) == [None] * 4 and _stops(p) == ["0", "-1", "-1", "-1"]


def test_rail_set_current_resets_a_roved_tab_stop(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{currentId: 'chats'}")
    p.focus("[data-testid=r-chats]")
    p.keyboard.press("ArrowDown")
    p.keyboard.press("ArrowDown")
    assert _stops(p) == ["-1", "-1", "0", "-1"]  # roving moved the stop to Library
    p.evaluate("() => window.__r.setCurrent('agents')")
    assert _stops(p) == ["-1", "0", "-1", "-1"]


def test_rail_set_href_updates_one_link(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__r.setHref('agents', '#x-agents/my%20bot/tools')")
    hrefs = p.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-rail-item')).map((a) => a.getAttribute('href'))"
    )
    assert hrefs == ["#x-chats", "#x-agents/my%20bot/tools", "#x-library", "#x-settings"]
    assert "unknown item nope" in _throws(p, "window.__r.setHref('nope', '#x')")


def test_rail_single_tab_stop_arrows_and_clamping(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{currentId: 'agents'}")
    p.focus("[data-testid=r-before]")
    # Positive control: a real Tab moves focus in this engine, onto the current item.
    p.keyboard.press("Tab")
    assert _active(p) == "r-agents"
    # One tab stop: the next Tab leaves the rail, Shift+Tab comes back to the same item.
    p.keyboard.press("Tab")
    assert _active(p) == "r-after"
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "r-agents"
    p.keyboard.press("ArrowDown")
    assert _active(p) == "r-library" and _stops(p) == ["-1", "-1", "0", "-1"]
    p.keyboard.press("ArrowDown")
    assert _active(p) == "r-settings"
    p.keyboard.press("ArrowDown")  # clamped at the end
    assert _active(p) == "r-settings"
    p.keyboard.press("ArrowUp")
    assert _active(p) == "r-library"
    p.keyboard.press("Home")
    assert _active(p) == "r-chats"
    p.keyboard.press("ArrowUp")  # clamped at the start
    assert _active(p) == "r-chats"
    p.keyboard.press("End")
    assert _active(p) == "r-settings"


def test_rail_destroy_unbinds_the_keyboard(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{currentId: 'chats'}")
    p.evaluate("() => window.__r.destroy()")
    p.focus("[data-testid=r-chats]")
    p.keyboard.press("ArrowDown")
    assert _active(p) == "r-chats"


# ── edge rules ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ("undefined", "App.ui.rail: items is required"),
        ("[]", "App.ui.rail: items is required"),
        ("[{label: 'X', icon: 'chat'}]", "rail item: id required"),
        ("[{id: 'x', icon: 'chat'}]", "rail item x: label required"),
        ("[{id: 'x', label: 'X'}]", "rail item x: icon required"),
        (
            "[{id: 'x', label: 'X', icon: 'chat'}, {id: 'x', label: 'Y', icon: 'chat'}]",
            "rail duplicate item id x",
        ),
        ("[{id: 'x', label: 'X', icon: 'no-such-icon'}]", 'unknown icon "no-such-icon"'),
    ],
)
def test_rail_edge_rules_throw(engine_page: Page, items: str, message: str) -> None:
    _mount(engine_page)
    assert message in _throws(engine_page, f"App.ui.rail({{items: {items}}});")


# M25 F4 L7 (DD9, DD14): the footer option takes an array of Nodes only.
@pytest.mark.parametrize(
    ("footer", "message"),
    [
        ("'x'", "App.ui.rail: footer must be an array of nodes"),
        ("{}", "App.ui.rail: footer must be an array of nodes"),
        ("document.createElement('b')", "App.ui.rail: footer must be an array of nodes"),
        ("[{}]", "App.ui.rail: footer item 0 is not a node"),
        ("['text']", "App.ui.rail: footer item 0 is not a node"),
        ("[document.createElement('b'), null]", "App.ui.rail: footer item 1 is not a node"),
    ],
)
def test_rail_footer_edge_rules_throw(engine_page: Page, footer: str, message: str) -> None:
    _mount(engine_page)
    items = "[{id: 'a', label: 'A', icon: 'chat', href: '#a'}]"
    assert message in _throws(engine_page, f"App.ui.rail({{items: {items}, footer: {footer}}});")
    # An empty array (or none) is no footer at all.
    assert _throws(engine_page, f"App.ui.rail({{items: {items}, footer: []}});") == ""
    count = engine_page.evaluate(
        f"() => App.ui.rail({{items: {items}, footer: []}}).el.querySelectorAll('.ui-rail-footer').length"
    )
    assert count == 0


# ── the footer slot (M25 F4 L7, DD9, DD14) ──────────────────────────────────

# A footer of a 44px icon-only ghost button (the shell's Jump to shape) and a
# plain node, both built by the caller; the button counts its own clicks.
FOOTER_OPTS = """{footer: (() => {
  window.__footClicks = 0;
  const b = App.ui.button({variant: 'ghost', icon: 'search', iconOnly: true,
                           ariaLabel: 'Jump to (test)', testid: 'r-foot',
                           onClick: () => { window.__footClicks += 1; }});
  const s = document.createElement('span'); s.textContent = 'v1'; s.setAttribute('data-testid', 'r-foot-note');
  return [b, s];
})()}"""


def test_rail_footer_is_pinned_to_the_bottom_and_holds_the_nodes(engine_page: Page) -> None:
    p = engine_page
    _mount(p, FOOTER_OPTS)
    out = p.evaluate(
        """() => {
          const nav = window.__r.el;
          nav.style.height = '480px';
          const footer = nav.lastElementChild, fs = getComputedStyle(footer);
          const btn = footer.querySelector('[data-testid=r-foot]');
          const nb = nav.getBoundingClientRect(), fb = footer.getBoundingClientRect(), bb = btn.getBoundingClientRect();
          const items = Array.from(nav.querySelectorAll('.ui-rail-item'));
          const lastItem = items[items.length - 1].getBoundingClientRect();
          const svg = btn.querySelector('svg').getBoundingClientRect();
          return {
            cls: footer.className, kids: Array.from(footer.children).map((c) => c.dataset.testid),
            items: items.length, inFooter: footer.querySelectorAll('.ui-rail-item').length,
            marginTop: fs.marginTop === 'auto' || parseFloat(fs.marginTop) > 0,
            gapBelowItems: fb.top - lastItem.bottom,
            bottomInset: nb.bottom - fb.bottom, btn: [bb.width, bb.height], svg: [svg.width, svg.height],
            centred: Math.abs((bb.left + bb.right) / 2 - (nb.left + nb.right - 1) / 2) <= 1,
            cls2: btn.className, tabindex: btn.getAttribute('tabindex'),
            name: btn.getAttribute('aria-label'), tag: btn.tagName,
          };
        }"""
    )
    assert out["cls"] == "ui-rail-footer"
    assert out["kids"] == ["r-foot", "r-foot-note"]  # the caller's nodes, in order
    assert out["items"] == 4 and out["inFooter"] == 0  # never a rail item
    # Pinned: the slack sits above it, and the rail's 12px bottom padding below it.
    assert out["marginTop"] is True and out["gapBelowItems"] > 100, out
    assert abs(out["bottomInset"] - 12) <= 0.5, out
    assert out["btn"] == [44, 44] and out["svg"] == [16, 16], out
    assert out["centred"] is True, out
    assert out["cls2"] == "btn-ghost btn-icon" and out["tabindex"] is None
    assert (out["tag"], out["name"]) == ("BUTTON", "Jump to (test)")
    # The click handler is the caller's, on the node itself.
    p.get_by_test_id("r-foot").click()
    assert p.evaluate("() => window.__footClicks") == 1


def test_rail_footer_buttons_are_their_own_tab_stops_outside_the_arrows(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "Object.assign(" + FOOTER_OPTS + ", {currentId: 'agents'})")
    p.focus("[data-testid=r-before]")
    p.keyboard.press("Tab")
    assert _active(p) == "r-agents"  # the rail's one item stop
    p.keyboard.press("Tab")
    assert _active(p) == "r-foot"  # then the footer button, its own stop
    p.keyboard.press("Tab")
    assert _active(p) == "r-after"
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "r-foot"
    # The items' roving keys do nothing on a footer button.
    for key in ("ArrowUp", "ArrowDown", "Home", "End"):
        p.keyboard.press(key)
        assert _active(p) == "r-foot", key
    p.keyboard.press("Shift+Tab")
    assert _active(p) == "r-agents"
    # And the arrows never leave the items for the footer: clamped at Settings.
    p.keyboard.press("End")
    assert _active(p) == "r-settings"
    p.keyboard.press("ArrowDown")
    assert _active(p) == "r-settings"
    assert (
        p.evaluate("() => document.querySelector('[data-testid=r-foot]').getAttribute('tabindex')")
        is None
    )


def test_rail_set_current_and_set_href_never_touch_the_footer(engine_page: Page) -> None:
    p = engine_page
    _mount(p, FOOTER_OPTS)
    before = p.evaluate("() => window.__r.el.querySelector('.ui-rail-footer').outerHTML")
    p.evaluate(
        """() => { const r = window.__r; r.setCurrent('library'); r.setHref('library', '#x-elsewhere');
                    r.setCurrent(null); r.setCurrent('settings'); return true; }"""
    )
    p.focus("[data-testid=r-settings]")
    p.keyboard.press("Home")
    after = p.evaluate("() => window.__r.el.querySelector('.ui-rail-footer').outerHTML")
    assert after == before
    assert p.evaluate("() => window.__r.el.lastElementChild.className") == "ui-rail-footer"


def test_rail_with_a_footer_binds_only_its_own_roving_keydown(engine_page: Page) -> None:
    """No document listener, and nothing bound on the footer's nodes: the
    only listener the factory adds is the rovingFocus keydown on the nav."""
    p = engine_page
    load_harness(p)
    out = p.evaluate(
        """() => {
          const btn = document.createElement('button'); btn.textContent = 'Foot';
          const seen = [];
          const orig = EventTarget.prototype.addEventListener;
          EventTarget.prototype.addEventListener = function (type) {
            seen.push([this === document ? 'document' : (this.tagName || String(this)), type]);
            return orig.apply(this, arguments);
          };
          let c;
          try {
            c = App.ui.rail({items: [{id: 'a', label: 'A', icon: 'chat', href: '#a'}], footer: [btn]});
            document.getElementById('harness-root').appendChild(c.el);
            c.setCurrent('a'); c.setHref('a', '#b');
          } finally {
            EventTarget.prototype.addEventListener = orig;
          }
          c.destroy();
          return seen;
        }"""
    )
    assert out == [["NAV", "keydown"]]


def test_rail_footer_controls_labelled_and_described(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "Object.assign(" + FOOTER_OPTS + ", {currentId: 'chats'})")
    assert_controls_labelled_and_described(p, "[aria-label=Main]")


def test_rail_installs_no_document_listener(engine_page: Page) -> None:
    p = engine_page
    load_harness(p)
    out = p.evaluate(
        """() => {
          const seen = [];
          const orig = document.addEventListener;
          document.addEventListener = function (type) { seen.push(type); return orig.apply(this, arguments); };
          const c = App.ui.rail({items: [{id: 'a', label: 'A', icon: 'chat', href: '#a'}]});
          document.getElementById('harness-root').appendChild(c.el);
          c.setCurrent('a'); c.setHref('a', '#b'); c.destroy();
          document.addEventListener = orig;
          return seen;
        }"""
    )
    assert out == []


# ── labelling and focus ring ────────────────────────────────────────────────


def test_rail_controls_labelled_and_described(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{currentId: 'chats'}")
    assert_controls_labelled_and_described(p, "[aria-label=Main]")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_rail_keyboard_focus_ring_is_visible(engine_page: Page, theme: str) -> None:
    p = engine_page
    _mount(p, "{currentId: 'agents'}", theme)
    ring_js = """() => {
      const el = document.activeElement, s = getComputedStyle(el);
      return {tid: el.dataset.testid, focusVisible: el.matches(':focus-visible'),
              outlineStyle: s.outlineStyle, outlineWidth: parseFloat(s.outlineWidth),
              outlineColor: s.outlineColor, shadow: s.boxShadow};
    }"""
    rest = p.evaluate(
        "() => { const s = getComputedStyle(document.querySelector('[data-testid=r-chats]')); return {style: s.outlineStyle, shadow: s.boxShadow}; }"
    )
    # Positive control: an unfocused, non-current item carries no ring at all.
    assert rest["style"] == "none" and rest["shadow"] == "none"
    p.focus("[data-testid=r-before]")
    p.keyboard.press("Tab")
    info = p.evaluate(ring_js)
    assert info["tid"] == "r-agents" and info["focusVisible"] is True
    has_outline = info["outlineStyle"] != "none" and info["outlineWidth"] >= 2
    has_inset = "inset" in info["shadow"]
    assert has_outline or has_inset, info
    # And it follows the roving move.
    p.keyboard.press("ArrowDown")
    info = p.evaluate(ring_js)
    assert info["tid"] == "r-library" and info["focusVisible"] is True
    assert info["outlineStyle"] != "none" and info["outlineWidth"] >= 2


# ── the global .visually-hidden utility (AC6) ───────────────────────────────


def _load_components_only(page: Page) -> None:
    """tokens.css + components.css + the library scripts; NOT admin.css/chat.css."""
    page.set_content("<!doctype html><html><head></head><body></body></html>")
    page.add_style_tag(content=index_layer_statement())
    for name in ("tokens.css", "components.css"):
        page.add_style_tag(path=str(STATIC_DIR / "css" / name))
    page.add_script_tag(path=str(STATIC_DIR / "js" / "icons.js"))
    for script in index_ui_script_paths():
        page.add_script_tag(path=str(script))
    page.evaluate(
        """() => { const r = document.createElement('div'); r.id = 'harness-root';
                   r.setAttribute('data-theme', 'dark'); document.body.appendChild(r); }"""
    )


def test_visually_hidden_works_with_only_tokens_and_components_css(engine_page: Page) -> None:
    p = engine_page
    _load_components_only(p)
    out = p.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          const f = App.ui.field({label: 'Secret name', labelHidden: true,
                                  control: App.ui.textInput({testid: 'vh-input'})});
          const c = App.ui.checkbox({label: 'Hidden choice text', labelHidden: true, testid: 'vh-check'});
          root.appendChild(f.el); root.appendChild(c.el);
          const probe = (n) => {
            const s = getComputedStyle(n), r = n.getBoundingClientRect();
            return {pos: s.position, w: r.width, h: r.height, overflow: s.overflow, clip: s.clip};
          };
          const hidden = Array.from(root.querySelectorAll('.visually-hidden'));
          return {count: hidden.length, texts: hidden.map((n) => n.textContent), boxes: hidden.map(probe)};
        }"""
    )
    assert out["count"] == 2 and sorted(out["texts"]) == ["Hidden choice text", "Secret name"]
    for box in out["boxes"]:
        assert box["pos"] == "absolute" and box["w"] <= 1 and box["h"] <= 1
        assert box["overflow"] == "hidden"
    # Still the accessible name of its control.
    expect(p.get_by_role("textbox", name="Secret name")).to_have_count(1)

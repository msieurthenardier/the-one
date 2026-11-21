# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.drawer`` (M25 F4 L6, flight DD7,
DD14): the non-modal side panel the chat area's agent drawer is built on.

The API and markup, adopting a static ``<aside>`` slot, ``hidden`` toggling and
``onOpenChange``, Escape and focus return (real ``keyboard.press``), both
``setMode`` modes measured in a positioned flex frame (push: a 320px sibling the
main area yields to; overlay: over the frame's right with the modal shadow), the
48px header, and ``destroy``. The no-document-listener case is in
``test_ui_listener_cleanup.py``. Every test runs in Chromium and WebKit through
``engine_page`` + ``load_harness`` (no app spawn); falls in the ``contracts`` lane.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import load_harness
from browser.design_tokens import DARK, LIGHT
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# A frame standing in for the app shell row (position: relative, a flex row of
# 900x400), a main area holding the opener, then the drawer.
MOUNT_JS = """(opts) => {
  window.__changes = [];
  const root = document.getElementById('harness-root');
  const frame = document.createElement('div');
  frame.id = 'frame';
  frame.style.cssText = 'position: relative; display: flex; width: 900px; height: 400px;';
  const main = document.createElement('div');
  main.id = 'frame-main';
  main.style.cssText = 'flex: 1; min-width: 0;';
  const opener = document.createElement('button');
  opener.textContent = 'Show the panel';
  opener.setAttribute('data-testid', 'd-opener');
  const outside = document.createElement('button');
  outside.textContent = 'Elsewhere';
  outside.setAttribute('data-testid', 'd-outside');
  main.appendChild(opener); main.appendChild(outside);
  const footerBtn = App.ui.button({label: 'Open settings', testid: 'd-footer-btn'});
  const body = document.createElement('p');
  body.textContent = 'Body text';
  const d = App.ui.drawer(Object.assign({
    label: 'Demo panel', heading: 'Research assistant', body: body, footer: footerBtn,
    testid: 'd-root', onOpenChange: (open) => window.__changes.push(open),
  }, opts || {}));
  d.el.id = d.el.id || 'd-panel';
  opener.setAttribute('aria-controls', d.el.id);
  opener.setAttribute('aria-pressed', 'false');
  frame.appendChild(main); frame.appendChild(d.el);
  root.appendChild(frame);
  window.__d = d; window.__opener = opener;
  return true;
}"""


def _mount(page: Page, opts: str = "{}", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT_JS})({opts})")


def _active(page: Page) -> str | None:
    return page.evaluate(
        "() => document.activeElement && (document.activeElement.dataset.testid || document.activeElement.tagName)"
    )


def _throws(page: Page, expr: str) -> str:
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


# ── API and markup ──────────────────────────────────────────────────────────


def test_drawer_api_and_markup(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => {
          const d = window.__d, a = d.el;
          const kids = Array.from(a.children);
          return {
            keys: Object.keys(d).sort().join(','),
            tag: a.tagName, cls: a.className, label: a.getAttribute('aria-label'),
            tid: a.getAttribute('data-testid'), hidden: a.hidden, mode: a.getAttribute('data-mode'),
            kids: kids.map((k) => k.className),
            heading: kids[0].firstElementChild.tagName + ':' + kids[0].firstElementChild.className + ':' + kids[0].textContent,
            body: kids[1].textContent, footer: kids[2].firstElementChild.getAttribute('data-testid'),
            isOpen: d.isOpen(),
          };
        }"""
    )
    assert out["keys"] == "close,destroy,el,isOpen,open,setMode,toggle"
    assert out["tag"] == "ASIDE" and out["label"] == "Demo panel" and out["tid"] == "d-root"
    assert out["cls"] == "ui-drawer ui-drawer--push" and out["mode"] == "push"
    assert out["hidden"] is True and out["isOpen"] is False  # built closed
    assert out["kids"] == ["ui-drawer-header", "ui-drawer-body", "ui-drawer-footer"]
    assert out["heading"] == "H2:ui-drawer-title:Research assistant"
    assert out["body"] == "Body text" and out["footer"] == "d-footer-btn"
    # A complementary landmark named by its label, and no footer without one.
    p.evaluate("() => window.__d.open()")
    expect(p.get_by_role("complementary", name="Demo panel")).to_have_count(1)
    no_footer = p.evaluate(
        "() => App.ui.drawer({label: 'x', heading: (() => { const s = document.createElement('span'); s.textContent = 'Node heading'; return s; })()})"
        ".el.children.length"
    )
    assert no_footer == 2


def test_drawer_heading_node_and_text_never_html(engine_page: Page) -> None:
    p = engine_page
    load_harness(p)
    out = p.evaluate(
        """() => {
          const node = document.createElement('div'); node.className = 'mine'; node.textContent = 'Mine';
          const a = App.ui.drawer({label: 'x', heading: node});
          const b = App.ui.drawer({label: 'y', heading: '<b>bold</b>'});
          return {node: a.el.querySelector('.ui-drawer-header').firstElementChild === node,
                  text: b.el.querySelector('h2').textContent, bold: b.el.querySelectorAll('b').length};
        }"""
    )
    assert out == {"node": True, "text": "<b>bold</b>", "bold": 0}


@pytest.mark.parametrize(
    ("expr", "message"),
    [
        ("App.ui.drawer({})", "App.ui.drawer: label is required"),
        (
            "App.ui.drawer({label: 'x', el: document.createElement('div')})",
            "App.ui.drawer: el must be an <aside>",
        ),
        ("App.ui.drawer({label: 'x', body: 'text'})", "App.ui.drawer: body must be a Node"),
        ("App.ui.drawer({label: 'x', footer: 'text'})", "App.ui.drawer: footer must be a Node"),
        ("App.ui.drawer({label: 'x'}).setMode('side')", 'App.ui.drawer: unknown mode "side"'),
    ],
)
def test_drawer_rejects_bad_options(engine_page: Page, expr: str, message: str) -> None:
    load_harness(engine_page)
    assert _throws(engine_page, expr) == message


def test_drawer_fills_a_static_aside_slot(engine_page: Page) -> None:
    """``el``: the factory fills an existing <aside> (the shell slot): its
    children are replaced, its id and its hidden state are the factory's."""
    p = engine_page
    load_harness(p)
    out = p.evaluate(
        """() => {
          const slot = document.createElement('aside');
          slot.id = 'slot'; slot.hidden = false;
          slot.appendChild(document.createElement('span'));
          document.getElementById('harness-root').appendChild(slot);
          const d = App.ui.drawer({label: 'Slot panel', heading: 'H', el: slot, testid: 'slot-tid'});
          return {same: d.el === slot, id: slot.id, hidden: slot.hidden, label: slot.getAttribute('aria-label'),
                  tid: slot.getAttribute('data-testid'), kids: Array.from(slot.children).map((k) => k.className)};
        }"""
    )
    assert out == {
        "same": True,
        "id": "slot",
        "hidden": True,
        "label": "Slot panel",
        "tid": "slot-tid",
        "kids": ["ui-drawer-header", "ui-drawer-body"],
    }


# ── Toggle, hidden and onOpenChange ─────────────────────────────────────────


def test_drawer_toggles_hidden_and_reports_each_change(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__d.open(window.__opener)")
    expect(p.get_by_test_id("d-root")).to_be_visible()
    p.evaluate("() => window.__d.open()")  # already open: no second report
    assert p.evaluate("() => [window.__d.isOpen(), window.__d.el.hidden]") == [True, False]
    p.evaluate("() => window.__d.toggle()")
    expect(p.get_by_test_id("d-root")).to_be_hidden()
    assert p.evaluate("() => getComputedStyle(window.__d.el).display") == "none"
    p.evaluate("() => window.__d.close()")  # already closed: no report
    p.evaluate("() => window.__d.toggle(window.__opener)")
    assert p.evaluate("() => window.__changes") == [True, False, True]
    # open() never moves focus (a non-modal panel).
    p.get_by_test_id("d-outside").focus()
    p.evaluate("() => { window.__d.close(); window.__d.open(); }")
    assert _active(p) == "d-outside"


def test_drawer_hidden_wins_over_both_modes(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    for mode in ("push", "overlay"):
        p.evaluate(f"() => window.__d.setMode('{mode}')")
        assert p.evaluate("() => getComputedStyle(window.__d.el).display") == "none", mode
        p.evaluate("() => window.__d.open()")
        assert p.evaluate("() => getComputedStyle(window.__d.el).display") == "flex", mode
        p.evaluate("() => window.__d.close()")


# ── Escape and focus return ─────────────────────────────────────────────────


def test_escape_inside_closes_and_returns_focus_to_the_opener(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    opener = p.get_by_test_id("d-opener")
    opener.click()  # a plain button: the test opens with it as the opener
    p.evaluate("() => window.__d.open(window.__opener)")
    p.get_by_test_id("d-footer-btn").focus()
    p.keyboard.press("Escape")
    expect(p.get_by_test_id("d-root")).to_be_hidden()
    assert _active(p) == "d-opener"
    assert p.evaluate("() => window.__changes") == [True, False]


def test_escape_after_a_click_on_a_non_focusable_area_still_closes(engine_page: Page) -> None:
    """HAT fix: the root is a programmatic focus target (tabindex -1, no tab stop), so a click
    on body text keeps focus inside the drawer and Escape closes it, focus to the opener."""
    p = engine_page
    _mount(p)
    p.get_by_test_id("d-opener").click()
    p.evaluate("() => window.__d.open(window.__opener)")
    root = p.get_by_test_id("d-root")
    expect(root).to_have_attribute("tabindex", "-1")
    p.get_by_text("Body text").click()
    assert p.evaluate("() => window.__d.el.contains(document.activeElement)")
    p.keyboard.press("Escape")
    expect(root).to_be_hidden()
    assert _active(p) == "d-opener"


def test_the_root_is_not_reached_by_tab(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__d.open(window.__opener)")
    p.get_by_test_id("d-opener").focus()
    seen = []
    for _ in range(4):
        p.keyboard.press("Tab")
        seen.append(p.evaluate("() => document.activeElement === window.__d.el"))
    assert not any(seen)


def test_escape_with_focus_outside_does_nothing(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__d.open(window.__opener)")
    p.get_by_test_id("d-outside").focus()
    p.keyboard.press("Escape")
    expect(p.get_by_test_id("d-root")).to_be_visible()
    assert _active(p) == "d-outside"


def test_close_returns_focus_only_when_it_was_inside(engine_page: Page) -> None:
    """A close from elsewhere never steals focus; a close with focus inside
    never drops it to <body>. With no opener argument the last one stays."""
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__d.open(window.__opener)")
    p.get_by_test_id("d-outside").focus()
    p.evaluate("() => window.__d.close()")
    assert _active(p) == "d-outside"
    p.evaluate("() => window.__d.open()")  # no argument: the last opener stays
    p.get_by_test_id("d-footer-btn").focus()
    p.evaluate("() => window.__d.close()")
    assert _active(p) == "d-opener"


def test_escape_is_consumed_and_ignored_while_composing(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__d.open(window.__opener)")
    out = p.evaluate(
        """() => {
          const btn = document.querySelector('[data-testid=d-footer-btn]');
          let bubbled = 0;
          const host = document.getElementById('harness-root');
          host.addEventListener('keydown', () => { bubbled += 1; });
          const ime = new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true, isComposing: true});
          btn.dispatchEvent(ime);
          const stillOpen = window.__d.isOpen();
          const real = new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true});
          btn.dispatchEvent(real);
          return {stillOpen, prevented: real.defaultPrevented, bubbled, open: window.__d.isOpen()};
        }"""
    )
    # The IME Escape bubbled through (1) and closed nothing; the real one was
    # prevented and stopped at the drawer.
    assert out == {"stillOpen": True, "prevented": True, "bubbled": 1, "open": False}


# ── Modes ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("theme", "pal"), [("dark", DARK), ("light", LIGHT)])
def test_push_mode_is_a_320px_sibling_the_main_area_yields_to(
    engine_page: Page, theme: str, pal: dict[str, str]
) -> None:
    p = engine_page
    _mount(p, theme=theme)
    p.evaluate("() => window.__d.open()")
    out = p.evaluate(
        """() => {
          const a = window.__d.el, s = getComputedStyle(a), r = a.getBoundingClientRect();
          const f = document.getElementById('frame').getBoundingClientRect();
          const m = document.getElementById('frame-main').getBoundingClientRect();
          const h = a.querySelector('.ui-drawer-header'), hs = getComputedStyle(h);
          const t = getComputedStyle(a.querySelector('.ui-drawer-title'));
          const ft = getComputedStyle(a.querySelector('.ui-drawer-footer'));
          return {position: s.position, w: r.width, right: r.right - f.left, h: r.height,
                  mainW: m.width, bg: s.backgroundColor, border: s.borderLeftWidth + ' ' + s.borderLeftStyle + ' ' + s.borderLeftColor,
                  shadow: s.boxShadow, headerH: h.getBoundingClientRect().height,
                  headerBorder: hs.borderBottomWidth + ' ' + hs.borderBottomStyle + ' ' + hs.borderBottomColor,
                  titleSize: t.fontSize, titleWeight: t.fontWeight,
                  footerBorder: ft.borderTopWidth + ' ' + ft.borderTopStyle};
        }"""
    )
    assert out["position"] == "static" and out["w"] == 320 and out["right"] == 900, out
    assert out["h"] == 400 and out["mainW"] == 900 - 320, out
    assert out["bg"] == _rgb(pal["surface"]), out
    assert out["border"] == f"1px solid {_rgb(pal['border'])}", out
    assert out["shadow"] == "none", out
    # A21: the 48px header with its hairline; the 13px/600 title.
    assert out["headerH"] == 48, out
    assert out["headerBorder"] == f"1px solid {_rgb(pal['border'])}", out
    assert (out["titleSize"], out["titleWeight"]) == ("13px", "600"), out
    assert out["footerBorder"] == "1px solid", out


def test_overlay_mode_covers_the_frames_right_with_the_modal_shadow(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => { window.__d.setMode('overlay'); window.__d.open(); }")
    out = p.evaluate(
        """() => {
          const a = window.__d.el, s = getComputedStyle(a), r = a.getBoundingClientRect();
          const f = document.getElementById('frame').getBoundingClientRect();
          const m = document.getElementById('frame-main').getBoundingClientRect();
          return {position: s.position, cls: a.className, mode: a.getAttribute('data-mode'),
                  box: [r.left - f.left, r.top - f.top, r.width, r.height], mainW: m.width,
                  shadow: s.boxShadow !== 'none', z: s.zIndex};
        }"""
    )
    assert out["position"] == "absolute" and out["mode"] == "overlay", out
    assert out["cls"] == "ui-drawer ui-drawer--overlay", out
    assert out["box"] == [900 - 320, 0, 320, 400], out  # top 0, right 0, bottom 0
    assert out["mainW"] == 900, out  # the main area keeps its width under the overlay
    assert out["shadow"] is True and out["z"] == "10", out
    # Back to push: the overlay class and shadow go.
    p.evaluate("() => window.__d.setMode('push')")
    assert p.evaluate(
        "() => [window.__d.el.className, getComputedStyle(window.__d.el).boxShadow, window.__d.el.getAttribute('data-mode')]"
    ) == ["ui-drawer ui-drawer--push", "none", "push"]


def test_overlay_has_no_outside_click_close(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => { window.__d.setMode('overlay'); window.__d.open(); }")
    p.get_by_test_id("d-outside").click()
    expect(p.get_by_test_id("d-root")).to_be_visible()


# ── destroy and accessibility ───────────────────────────────────────────────


def test_destroy_unbinds_escape_empties_and_hides(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__d.open(window.__opener)")
    out = p.evaluate(
        """() => {
          const a = window.__d.el;
          window.__d.destroy();
          a.hidden = false;  // shown by hand: Escape must no longer close it
          const e = new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true});
          a.dispatchEvent(e);
          return {kids: a.children.length, prevented: e.defaultPrevented, hidden: a.hidden, connected: a.isConnected};
        }"""
    )
    assert out == {"kids": 0, "prevented": False, "hidden": False, "connected": True}


def test_drawer_and_its_toggle_pass_the_resolver(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => window.__d.open(window.__opener)")
    assert_controls_labelled_and_described(p, "#frame")
    p.evaluate("() => window.__d.close()")
    assert_controls_labelled_and_described(p, "#frame")  # hidden, still resolvable


# ── reserveHeaderEnd (M31 F6 L03b): room for a control placed over the header ──


def test_reserve_header_end_pads_the_header_in_overlay_mode_only(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{reserveHeaderEnd: true}")
    pad = "() => [getComputedStyle(window.__d.el.querySelector('.ui-drawer-header')).paddingRight, window.__d.el.className]"
    assert p.evaluate(pad) == ["16px", "ui-drawer ui-drawer--push ui-drawer--reserve-end"]
    p.evaluate("() => { window.__d.setMode('overlay'); window.__d.open(); }")
    assert p.evaluate(pad)[0] == "56px"  # 16 + a 32px toggle + 8
    p.evaluate("() => window.__d.setMode('push')")
    assert p.evaluate(pad)[0] == "16px"


def test_without_reserve_header_end_the_overlay_header_keeps_its_padding(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    p.evaluate("() => { window.__d.setMode('overlay'); window.__d.open(); }")
    assert p.evaluate(
        "() => [getComputedStyle(window.__d.el.querySelector('.ui-drawer-header')).paddingRight, window.__d.el.className]"
    ) == ["16px", "ui-drawer ui-drawer--overlay"]


# ── beforeClose (M36 F3 L2): runs before focus returns, never on a no-op close ──


def test_before_close_lets_a_hidden_opener_be_shown_in_time_to_take_focus(
    engine_page: Page,
) -> None:
    p = engine_page
    _mount(
        p,
        "{beforeClose: () => { window.__opener.hidden = false; window.__calls.push('before'); }}",
    )
    p.evaluate("() => { window.__calls = []; }")
    # The opener is hidden while the drawer is open (as the GleepGlorp corner button is).
    p.evaluate("() => { window.__d.open(window.__opener); window.__opener.hidden = true; }")
    p.evaluate("() => window.__d.el.querySelector('[data-testid=d-footer-btn]').focus()")
    p.keyboard.press("Escape")
    expect(p.get_by_test_id("d-root")).to_be_hidden()
    assert _active(p) == "d-opener"
    assert p.evaluate("() => window.__calls") == ["before"]


def test_before_close_runs_for_close_and_toggle_but_not_when_already_hidden(
    engine_page: Page,
) -> None:
    p = engine_page
    _mount(p, "{beforeClose: () => { window.__calls.push('before'); }}")
    p.evaluate("() => { window.__calls = []; }")
    p.evaluate("() => window.__d.close()")  # hidden already: a no-op
    assert p.evaluate("() => window.__calls") == []
    p.evaluate(
        "() => { window.__d.open(); window.__d.close(); window.__d.open(); window.__d.toggle(); }"
    )
    assert p.evaluate("() => window.__calls") == ["before", "before"]
    assert p.evaluate("() => window.__changes") == [True, False, True, False]


def test_a_throwing_before_close_never_keeps_the_drawer_open(engine_page: Page) -> None:
    p = engine_page
    _mount(p, "{beforeClose: () => { throw new Error('nope'); }}")
    p.evaluate("() => { window.__d.open(); window.__d.close(); }")
    expect(p.get_by_test_id("d-root")).to_be_hidden()
    assert p.evaluate("() => window.__changes") == [True, False]

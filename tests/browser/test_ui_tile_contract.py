# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.groupTile`` and ``App.ui.toolRow``
(M31 F2 L4, flight DD3/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.

Legacy comparisons hand-write today's markup (``tools-tab.js`` / ``mcps-tab.js`` build it with the
area renderers, which the harness cannot load) inside ONE explicit ``area-studio`` wrapper and
compare a FIXED property list. The legacy ``.tools-category-tile`` and ``.mcp-source-tile`` rules
are identical, so one legacy tile covers both.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

PROPS_JS = """const PROPS = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'marginTop', 'marginBottom',
  'fontSize', 'fontWeight', 'fontFamily', 'lineHeight', 'letterSpacing', 'textTransform',
  'borderTopWidth', 'borderTopStyle', 'borderTopColor', 'borderBottomWidth', 'borderBottomStyle', 'borderBottomColor',
  'borderRadius', 'backgroundColor', 'color', 'height', 'rowGap', 'columnGap', 'display', 'flexDirection', 'opacity', 'listStyleType'];
const snap = (el) => { const s = getComputedStyle(el); const o = {}; PROPS.forEach((p) => { o[p] = s[p]; }); return o; };
const diff = (a, b) => { const d = {}; PROPS.forEach((p) => { if (a[p] !== b[p]) d[p] = [a[p], b[p]]; }); return d; };"""

DESC = "Reads a file from the local filesystem and returns its contents as text, with line numbers added for reference."

TILE = """(extra) => {
  window.__calls = [];
  const o = Object.assign({name: 'Filesystem', count: '3 / 4 enabled', toolCount: 4, testid: 'gt',
    master: {label: 'Enable all Filesystem tools', state: 'mixed', testid: 'gt-master', onChange: (v) => window.__calls.push(['master', v])},
    onExpand: (v) => window.__calls.push(['expand', v]), onFirstExpand: (b) => window.__calls.push(['first', b.className])}, extra || {});
  window.__tile = App.ui.groupTile(o);
  document.getElementById('harness-root').appendChild(window.__tile.el);
  return true;
}"""


def _engine(page: Page) -> str:
    return page.context.browser.browser_type.name


def _tile(page: Page, extra: str = "null") -> None:
    load_harness(page)
    page.evaluate(f"({TILE})({extra})")


# ── groupTile ───────────────────────────────────────────────────────────────


def test_group_tile_dom_shape_and_api(engine_page: Page) -> None:
    _tile(
        engine_page,
        "{chips: ['stdio'], subtitle: 'Server 1.2', actions: [App.ui.button({label: 'Refresh', size: 'sm', icon: 'refresh', testid: 'gt-refresh'})]}",
    )
    out = engine_page.evaluate(
        """() => {
          const t = window.__tile, el = t.el, row = el.firstElementChild;
          return {root: el.className, tid: el.getAttribute('data-testid'), kids: Array.from(el.children).map((k) => k.tagName + '.' + k.className),
            row: Array.from(row.children).map((k) => k.tagName + '.' + k.className),
            master: [row.querySelector('input').type, row.querySelector('input').getAttribute('role'), row.querySelector('input').indeterminate, row.querySelector('input').getAttribute('data-testid')],
            expand: [el.querySelector('.ui-group-tile-expand').getAttribute('aria-expanded'), el.querySelector('.ui-group-tile-expand').textContent, el.querySelector('.ui-group-tile-expand strong').textContent],
            body: [t.body.className, t.body.hidden, t.body.parentNode === el], sub: el.querySelector('.ui-group-tile-subtitle').textContent,
            api: Object.keys(t).sort()};
        }"""
    )
    assert out["root"] == "ui-group-tile" and out["tid"] == "gt"
    assert out["kids"][0].startswith("DIV.ui-group-tile-row")
    assert out["kids"][1:] == [
        "DIV.ui-group-tile-subtitle", "BUTTON.ui-group-tile-expand", "DIV.ui-group-tile-body",
    ]  # fmt: skip
    assert out["row"] == [
        "DIV.ui-toggle", "SPAN.ui-group-tile-name", "SPAN.ui-group-tile-chip", "SPAN.ui-group-tile-chip", "DIV.ui-group-tile-actions",
    ]  # fmt: skip
    assert out["master"] == ["checkbox", None, True, "gt-master"]
    assert out["expand"] == ["false", "4 tools▸", "4"]
    assert out["body"] == ["ui-group-tile-body", True, True]
    assert out["sub"] == "Server 1.2"
    assert out["api"] == [
        "body", "destroy", "el", "isExpanded", "setCount", "setExpanded", "setMaster", "setSubtitle", "setToolCount",
    ]  # fmt: skip


def test_group_tile_tool_counts_and_unknown_label(engine_page: Page) -> None:
    _tile(engine_page, "{toolCount: 1}")
    p = engine_page
    expect(p.locator(".ui-group-tile-expand-label")).to_have_text("1 tool")
    p.evaluate("window.__tile.setToolCount(0)")
    expect(p.locator(".ui-group-tile-expand-label")).to_have_text("0 tools")
    p.evaluate("window.__tile.setToolCount(12)")
    expect(p.locator(".ui-group-tile-expand-label strong")).to_have_text("12")
    p.evaluate("window.__tile.setToolCount('Tools')")
    expect(p.locator(".ui-group-tile-expand-label")).to_have_text("Tools")
    assert p.locator(".ui-group-tile-expand-label strong").count() == 0
    _tile(p, "{toolCount: undefined, toolLabel: 'Tools'}")
    expect(p.locator(".ui-group-tile-expand-label")).to_have_text("Tools")


def test_group_tile_expand_and_first_expand_once(engine_page: Page) -> None:
    _tile(engine_page)
    p = engine_page
    btn = p.locator(".ui-group-tile-expand")
    body = p.locator(".ui-group-tile-body")
    expect(body).to_be_hidden()
    btn.click()
    expect(btn).to_have_attribute("aria-expanded", "true")
    expect(body).to_be_visible()
    assert p.evaluate("() => window.__tile.isExpanded()") is True
    assert (
        p.evaluate(
            "() => getComputedStyle(document.querySelector('.ui-group-tile-chevron')).transform"
        )
        != "none"
    )
    btn.click()
    expect(body).to_be_hidden()
    btn.click()
    assert p.evaluate("() => window.__calls") == [
        ["first", "ui-group-tile-body"], ["expand", True], ["expand", False], ["expand", True],
    ]  # fmt: skip
    p.evaluate("window.__tile.setExpanded(false)")  # programmatic: silent, no onExpand
    assert p.evaluate("() => window.__calls.length") == 4
    p.keyboard.press("Tab")  # keyboard operable: the button is a native button
    btn.focus()
    p.keyboard.press("Enter")
    expect(body).to_be_visible()


def test_group_tile_master_tristate(engine_page: Page) -> None:
    _tile(engine_page)
    p = engine_page
    master = p.get_by_role("checkbox", name="Enable all Filesystem tools")
    expect(master).to_have_count(1)
    assert (
        p.evaluate("() => document.querySelector('[data-testid=gt-master]').indeterminate") is True
    )
    if _engine(p) == "chromium":
        # The accessibility tree exposes the mixed state (Chromium only).
        assert "[checked=mixed]" in master.aria_snapshot()
    # A user click on a mixed master gives checked and onChange(true).
    p.locator(".ui-toggle-track").click()
    assert p.evaluate(
        "() => [window.__calls, document.querySelector('[data-testid=gt-master]').checked, document.querySelector('[data-testid=gt-master]').indeterminate]"
    ) == [[["master", True]], True, False]
    # The consumer sets the state back: silent (no onChange).
    p.evaluate("window.__tile.setMaster('mixed')")
    assert p.evaluate(
        "() => [window.__calls.length, document.querySelector('[data-testid=gt-master]').indeterminate, document.querySelector('[data-testid=gt-master]').checked]"
    ) == [1, True, False]
    p.evaluate("window.__tile.setMaster('on')")
    assert p.evaluate(
        "() => [window.__calls.length, document.querySelector('[data-testid=gt-master]').indeterminate, document.querySelector('[data-testid=gt-master]').checked]"
    ) == [1, False, True]
    p.evaluate("window.__tile.setMaster('off')")
    assert p.evaluate("() => document.querySelector('[data-testid=gt-master]').checked") is False
    p.locator(".ui-toggle-track").click()
    assert p.evaluate("() => window.__calls[window.__calls.length - 1]") == ["master", True]
    p.locator(".ui-toggle-track").click()
    assert p.evaluate("() => window.__calls[window.__calls.length - 1]") == ["master", False]


def test_group_tile_never_changes_children_and_set_count(engine_page: Page) -> None:
    _tile(engine_page)
    p = engine_page
    p.evaluate(
        """() => { const c = document.createElement('input'); c.type = 'checkbox'; c.id = 'child'; window.__tile.body.appendChild(c); }"""
    )
    p.get_by_role("checkbox", name="Enable all Filesystem tools").click(force=True)
    assert p.evaluate("() => document.getElementById('child').checked") is False
    p.evaluate("window.__tile.setCount('1 / 4 enabled')")
    expect(p.locator(".ui-group-tile-row .ui-group-tile-chip").first).to_have_text("1 / 4 enabled")
    p.evaluate("window.__tile.setSubtitle('Hello')")
    expect(p.locator(".ui-group-tile-subtitle")).to_have_text("Hello")
    p.evaluate("window.__tile.setSubtitle(null)")
    assert p.locator(".ui-group-tile-subtitle").count() == 0


def test_group_tile_size_assertions(engine_page: Page) -> None:
    _tile(
        engine_page,
        "{actions: [App.ui.button({label: 'Refresh', size: 'sm', icon: 'refresh', testid: 'gt-refresh'})]}",
    )
    out = engine_page.evaluate(
        """() => {
          const b = document.querySelector('[data-testid=gt-refresh]'), s = getComputedStyle(b), svg = b.querySelector('svg').getBoundingClientRect();
          const track = document.querySelector('.ui-toggle-track').getBoundingClientRect();
          const tile = window.__tile.el.getBoundingClientRect();
          return {h: b.getBoundingClientRect().height, font: s.fontSize, icon: [svg.width, svg.height], track: [track.width, track.height], tileW: tile.width};
        }"""
    )
    assert out["h"] == 24  # the header actions are the library's small button
    assert out["font"] == "10px"
    assert out["icon"] == [14, 14]
    assert out["track"] == [36, 20]  # the library switch


LEGACY_TILE = """<div class="tools-categories-list"><div class="tools-category-tile" aria-expanded="false">
  <div class="tools-category-tile-row1">
    <label class="tools-category-tile-toggle mcp-source-tile-toggle"><input type="checkbox" class="tool-toggle"><span class="tool-switch"></span></label>
    <span class="tools-category-tile-name">Filesystem</span><span class="tools-category-tile-count">3 / 4 enabled</span></div>
  <button type="button" class="tools-category-tile-expand-btn" aria-expanded="false"><span><strong>4</strong> tools</span><span class="tools-category-tile-chevron">▸</span></button>
  <div class="tools-category-tile-tools" hidden></div></div></div>"""


def test_group_tile_computed_styles_equal_legacy_area_studio(engine_page: Page) -> None:
    load_harness(engine_page)
    engine_page.evaluate(
        """(legacy) => {
          const host = document.createElement('div'); host.className = 'area-studio'; host.id = 'cmp';  // the explicit wrapper
          host.innerHTML = '<div id="legacy-side">' + legacy + '</div><div id="lib-side"></div>';
          document.getElementById('harness-root').appendChild(host);
          const t = App.ui.groupTile({name: 'Filesystem', count: '3 / 4 enabled', toolCount: 4, master: {label: 'All', state: 'off'}});
          host.querySelector('#lib-side').appendChild(t.el);
          t.setExpanded(true);
          host.querySelector('.tools-category-tile-tools').hidden = false;
        }""",
        LEGACY_TILE,
    )
    out = engine_page.evaluate(
        """() => {
          """
        + PROPS_JS
        + """
          const L = document.getElementById('legacy-side'), N = document.getElementById('lib-side');
          const pairs = {
            tile: ['.tools-category-tile', '.ui-group-tile'], row: ['.tools-category-tile-row1', '.ui-group-tile-row'],
            name: ['.tools-category-tile-name', '.ui-group-tile-name'], chip: ['.tools-category-tile-count', '.ui-group-tile-chip'],
            expand: ['.tools-category-tile-expand-btn', '.ui-group-tile-expand'], strong: ['.tools-category-tile-expand-btn strong', '.ui-group-tile-expand strong'],
            chevron: ['.tools-category-tile-chevron', '.ui-group-tile-chevron'], body: ['.tools-category-tile-tools', '.ui-group-tile-body']
          };
          const o = {};
          for (const k in pairs) o[k] = diff(snap(L.querySelector(pairs[k][0])), snap(N.querySelector(pairs[k][1])));
          return o;
        }"""
    )
    # The one intended difference (canvas, approved): the master is the library's 36x20 switch, not
    # the legacy 32x18 pill, so the row is 2px taller and so is the tile. Nothing else differs.
    for key in ("row", "tile"):
        changed = out.pop(key)
        assert set(changed) == {"height"}, changed
        legacy_h, library_h = (float(v[:-2]) for v in changed["height"])
        assert library_h - legacy_h == 2, changed
    assert out == {k: {} for k in out}, out


# ── toolRow ─────────────────────────────────────────────────────────────────

ROW = """(extra) => {
  window.__calls = [];
  const o = Object.assign({name: 'read_file', description: %s, checked: true, testid: 'tr-cb',
    onChange: (v) => window.__calls.push(['change', v])}, extra || {});
  window.__row = App.ui.toolRow(o);
  document.getElementById('harness-root').appendChild(window.__row.el);
  return true;
}"""


def _row(page: Page, extra: str = "null", description: str = repr(DESC)) -> None:
    load_harness(page)
    page.evaluate(f"({ROW % description})({extra})")


def test_tool_row_plain_dom_truncation_and_api(engine_page: Page) -> None:
    _row(engine_page)
    out = engine_page.evaluate(
        """() => {
          const r = window.__row, el = r.el, d = el.querySelector('.ui-tool-row-desc');
          return {tag: el.tagName, cls: el.className, kids: Array.from(el.children).map((k) => k.tagName + '.' + k.className),
            cb: [r.input.type, r.input.className, r.input.checked, r.input.getAttribute('data-testid')],
            name: el.querySelector('.ui-tool-row-name').textContent, desc: d.textContent, title: d.title, body: r.body,
            api: Object.keys(r).sort(), nested: el.querySelectorAll('summary, details, button, a').length};
        }"""
    )
    assert out["tag"] == "LABEL" and out["cls"] == "ui-tool-row ui-tool-row--plain"
    assert out["kids"] == ["INPUT.checkbox-primary", "SPAN.ui-tool-row-text"]
    assert out["cb"] == ["checkbox", "checkbox-primary", True, "tr-cb"]
    assert out["name"] == "read_file"
    assert out["desc"] == " — " + DESC[:100] + "…" and len(DESC) > 100
    assert out["title"] == DESC  # the full text on hover
    assert out["body"] is None
    assert out["api"] == ["body", "destroy", "el", "input", "setChecked", "setDisabled", "setOpen"]
    assert out["nested"] == 0
    expect(engine_page.get_by_role("checkbox", name="read_file")).to_be_checked()


def test_tool_row_short_description_not_truncated_and_note(engine_page: Page) -> None:
    _row(engine_page, "{note: 'Always available.'}", description="'Short.'")
    out = engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-tool-row-desc')).map((d) => [d.textContent, d.getAttribute('data-testid')])"
    )
    assert out == [[" — Short.", None], ["Always available.", "time-tool-note"]]


def test_tool_row_disabled_strike_title_and_no_disclosure(engine_page: Page) -> None:
    _row(engine_page, "{disabled: true, disclosure: {label: 'Overrides'}}")
    out = engine_page.evaluate(
        """() => {
          const r = window.__row, s = getComputedStyle(r.el);
          return {tag: r.el.tagName, cls: r.el.className, title: r.el.title, dis: r.input.disabled, opacity: s.opacity,
            strike: getComputedStyle(r.el.querySelector('.ui-tool-row-name')).textDecorationLine,
            aff: r.el.querySelectorAll('.ui-tool-row-affordance').length, body: r.body};
        }"""
    )
    assert out == {
        "tag": "LABEL", "cls": "ui-tool-row is-disabled ui-tool-row--plain", "title": "Disabled by operator", "dis": True,
        "opacity": "0.5", "strike": "line-through", "aff": 0, "body": None,
    }  # fmt: skip
    _row(engine_page, "{strike: true}")
    assert (
        engine_page.evaluate(
            "() => getComputedStyle(document.querySelector('.ui-tool-row-name')).textDecorationLine"
        )
        == "line-through"
    )
    engine_page.evaluate("window.__row.setDisabled(true)")
    assert engine_page.evaluate(
        "() => [window.__row.input.disabled, window.__row.el.classList.contains('is-disabled')]"
    ) == [True, True]


def test_tool_row_on_change_and_set_checked_silent(engine_page: Page) -> None:
    _row(engine_page)
    p = engine_page
    p.get_by_test_id("tr-cb").click()
    assert p.evaluate("() => window.__calls") == [["change", False]]
    p.evaluate("window.__row.setChecked(true)")
    assert p.evaluate("() => [window.__calls.length, window.__row.input.checked]") == [1, True]


def test_tool_row_disclosure_dom_and_first_open_once(engine_page: Page) -> None:
    _row(
        engine_page,
        "{disclosure: {label: 'Overrides', onFirstOpen: (b) => { window.__calls.push(['open', b.className]); b.textContent = 'filled'; }}}",
    )
    p = engine_page
    out = p.evaluate(
        """() => {
          const r = window.__row, el = r.el, sum = el.firstElementChild;
          return {tag: el.tagName, cls: el.className, kids: Array.from(el.children).map((k) => k.tagName + '.' + k.className),
            sum: Array.from(sum.children).map((k) => k.tagName + '.' + k.className), aff: el.querySelector('.ui-tool-row-affordance').textContent,
            body: [r.body.className, r.body.parentNode === el], open: el.open};
        }"""
    )
    assert out["tag"] == "DETAILS" and out["cls"] == "ui-tool-row ui-tool-row--disclosure"
    assert out["kids"] == ["SUMMARY.ui-tool-row-summary", "DIV.ui-tool-row-body"]
    assert out["sum"] == ["LABEL.ui-tool-row-face", "SPAN.ui-tool-row-affordance"]
    assert (
        out["aff"] == "Overrides▸"
        and out["body"] == ["ui-tool-row-body", True]
        and out["open"] is False
    )
    p.locator(".ui-tool-row-affordance").click()
    expect(p.locator(".ui-tool-row-body")).to_have_text("filled")
    p.locator(".ui-tool-row-affordance").click()
    p.locator(".ui-tool-row-affordance").click()
    p.wait_for_timeout(100)
    assert p.evaluate("() => window.__calls") == [["open", "ui-tool-row-body"]]
    p.evaluate("window.__row.setOpen(false)")
    assert p.evaluate("() => window.__row.el.open") is False


def test_tool_row_four_interactions_toggle_only_their_own_target(engine_page: Page) -> None:
    """The <summary><label><input> nesting relies on the HTML rule that activating an interactive
    descendant of a summary does not toggle the details. Checked in BOTH engines (the main engine risk)."""
    _row(engine_page, "{disclosure: {label: 'Overrides'}}")
    p = engine_page

    def state() -> list:
        return p.evaluate("() => [window.__row.input.checked, window.__row.el.open]")

    assert state() == [True, False]
    # 1. Space on the focused checkbox toggles only the checkbox.
    p.get_by_test_id("tr-cb").focus()
    p.keyboard.press("Space")
    assert state() == [False, False]
    # 2. Enter on the summary toggles only the details.
    p.evaluate("window.__row.el.firstElementChild.focus()")
    p.keyboard.press("Enter")
    p.wait_for_timeout(50)
    assert state() == [False, True]
    # 3. A click on the label text toggles only the checkbox.
    p.locator(".ui-tool-row-name").click()
    assert state() == [True, True]
    # 4. A click on the affordance toggles only the details.
    p.locator(".ui-tool-row-affordance").click()
    p.wait_for_timeout(50)
    assert state() == [True, False]


def test_tool_row_summary_focus_ring_and_accessibility(engine_page: Page) -> None:
    _row(engine_page, "{disclosure: {label: 'Overrides'}}")
    p = engine_page
    # The summary shows a visible focus ring (Flight 1 DD8: disclosures). Keyboard focus from the
    # checkbox (Shift+Tab) lands on the summary's own stop, where :focus-visible matches.
    p.get_by_test_id("tr-cb").focus()
    p.keyboard.press("Shift+Tab")
    ring = p.evaluate(
        """() => { const s = document.activeElement, c = getComputedStyle(s);
          return [s.tagName, s.matches(':focus-visible'), c.outlineStyle, c.outlineWidth]; }"""
    )
    if ring[0] != "SUMMARY":  # an engine that gives the summary no tab stop of its own
        p.evaluate("document.querySelector('summary').focus({focusVisible: true})")
        ring = p.evaluate(
            "() => { const s = document.activeElement, c = getComputedStyle(s); return [s.tagName, s.matches(':focus-visible'), c.outlineStyle, c.outlineWidth]; }"
        )
    assert ring == ["SUMMARY", True, "solid", "2px"]
    # No interactive element is nested in another except summary > label > input (as today).
    nested = p.evaluate(
        "() => document.querySelectorAll('summary button, summary a, label button, label a').length"
    )
    assert nested == 0
    expect(p.get_by_role("checkbox", name="read_file")).to_have_count(1)


LEGACY_ROWS = """<div class="tools-category-tile"><div class="tools-category-tile-tools" style="display:flex">
  <details class="tool-tile tool-row-overrides"><summary class="tool-tile-summary"><label class="tool-tile-toggle-face"><input type="checkbox" class="checkbox-primary" checked>
    <span class="mcp-tool-text"><span class="mcp-tool-toggle-name">read_file</span><span class="mcp-tool-description"> — %s</span></span></label>
    <span class="tool-tile-overrides-affordance"><span>Overrides</span><span class="chevron">▸</span></span></summary><div class="tool-row-overrides-body">body</div></details>
</div></div>
<div class="mcp-tools-checkbox-group"><label class="mcp-tool-toggle-label"><input type="checkbox" class="checkbox-primary" checked>
  <div class="mcp-tool-text"><span class="mcp-tool-toggle-name">read_file</span><span class="mcp-tool-description"> — %s</span></div></label></div>"""


# The legacy MCP tool-row rules, inlined as a fixture (M31 F2 L07b): the MCPs tab no longer uses
# them, so they are gone from studio.css, and this comparison keeps its reference here.
LEGACY_MCP_ROW_CSS = """<style>
.area-studio .mcp-tools-checkbox-group { display: flex; flex-direction: column; gap: 6px; }
.area-studio .mcp-tool-toggle-label { display: flex; align-items: center; gap: 10px; cursor: pointer;
  font-size: var(--font-size-body-sm); padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface); transition: border-color var(--motion-fast), background var(--motion-fast); }
.area-studio .mcp-tool-toggle-label:hover { border-color: var(--accent); background: var(--surface-elevated); }
.area-studio .mcp-tool-toggle-label .checkbox-primary { flex-shrink: 0; }
</style>"""


def test_tool_row_computed_styles_equal_legacy_area_studio(engine_page: Page) -> None:
    load_harness(engine_page)
    short = "Reads a file."
    engine_page.evaluate(
        """([legacy, short]) => {
          const host = document.createElement('div'); host.className = 'area-studio'; host.id = 'cmp';  // the explicit wrapper
          host.innerHTML = '<div id="legacy-side">' + legacy + '</div><div id="lib-side"></div>';
          document.getElementById('harness-root').appendChild(host);
          const side = host.querySelector('#lib-side');
          side.style.display = 'flex'; side.style.flexDirection = 'column'; side.style.gap = '6px';
          side.appendChild(App.ui.toolRow({name: 'read_file', description: short, checked: true, disclosure: {label: 'Overrides'}}).el);
          side.appendChild(App.ui.toolRow({name: 'read_file', description: short, checked: true}).el);
        }""",
        [LEGACY_MCP_ROW_CSS + LEGACY_ROWS % (short, short), short],
    )
    out = engine_page.evaluate(
        """() => {
          """
        + PROPS_JS
        + """
          const L = document.getElementById('legacy-side'), N = document.getElementById('lib-side');
          const d = (a, b) => diff(snap(a), snap(b));
          const lt = L.querySelector('.tool-tile'), nt = N.querySelector('details.ui-tool-row');
          const lm = L.querySelector('.mcp-tool-toggle-label'), nm = N.querySelector('label.ui-tool-row');
          return {
            tile: d(lt, nt), summary: d(lt.querySelector('summary'), nt.querySelector('summary')),
            face: d(lt.querySelector('.tool-tile-toggle-face'), nt.querySelector('.ui-tool-row-face')),
            text: d(lt.querySelector('.mcp-tool-text'), nt.querySelector('.ui-tool-row-text')),
            name: d(lt.querySelector('.mcp-tool-toggle-name'), nt.querySelector('.ui-tool-row-name')),
            desc: d(lt.querySelector('.mcp-tool-description'), nt.querySelector('.ui-tool-row-desc')),
            aff: d(lt.querySelector('.tool-tile-overrides-affordance'), nt.querySelector('.ui-tool-row-affordance')),
            mcpRow: d(lm, nm), mcpText: d(lm.querySelector('.mcp-tool-text'), nm.querySelector('.ui-tool-row-text')),
            mcpDesc: d(lm.querySelector('.mcp-tool-description'), nm.querySelector('.ui-tool-row-desc')),
            summaryHeight: [lt.querySelector('summary').getBoundingClientRect().height, nt.querySelector('summary').getBoundingClientRect().height]
          };
        }"""
    )
    heights = out.pop("summaryHeight")
    assert heights[0] == heights[1] > 0  # the legacy summary height
    assert out == {k: {} for k in out}, out
    # The open body keeps the dashed top border and padding.
    engine_page.evaluate(
        "() => { document.querySelector('#legacy-side details').open = true; const n = document.querySelector('details.ui-tool-row'); n.open = true; n.querySelector('.ui-tool-row-body').textContent = 'body'; }"
    )
    body = engine_page.evaluate(
        """() => {
          """
        + PROPS_JS
        + """
          return diff(snap(document.querySelector('.tool-row-overrides-body')), snap(document.querySelector('.ui-tool-row-body')));
        }"""
    )
    assert body == {}, body


# ── M31 F2 L07b: non-tristate master, input datasets ────────────────────────


def test_group_tile_non_tristate_master_is_a_switch_with_dataset(engine_page: Page) -> None:
    _tile(
        engine_page,
        "{master: {label: 'Attach src', tristate: false, state: 'on', testid: 'gt-master', dataset: {mcpSourceToggle: '', mcpSourceId: 's1'}, onChange: (v) => window.__calls.push(['master', v])}}",
    )
    p = engine_page
    master = p.get_by_role("switch", name="Attach src")
    expect(master).to_have_count(1)
    expect(master).to_be_checked()
    out = p.evaluate(
        """() => { const i = document.querySelector('[data-testid=gt-master]');
          return [i.getAttribute('role'), i.hasAttribute('data-mcp-source-toggle'), i.dataset.mcpSourceId, i.indeterminate, 'setIndeterminate' in window.__tile]; }"""
    )
    assert out == ["switch", True, "s1", False, False]
    # 'mixed' reads as off on a plain switch: never indeterminate.
    p.evaluate("window.__tile.setMaster('mixed')")
    assert p.evaluate(
        "() => [document.querySelector('[data-testid=gt-master]').checked, document.querySelector('[data-testid=gt-master]').indeterminate]"
    ) == [False, False]
    p.locator(".ui-toggle-track").click()
    assert p.evaluate("() => window.__calls") == [["master", True]]
    p.locator(".ui-toggle-track").click()
    assert p.evaluate("() => window.__calls[window.__calls.length - 1]") == ["master", False]
    # The default master stays tristate (no role=switch).
    _tile(p)
    assert (
        p.evaluate("() => document.querySelector('[data-testid=gt-master]').getAttribute('role')")
        is None
    )


def test_tool_row_input_dataset_on_the_checkbox(engine_page: Page) -> None:
    load_harness(engine_page)
    engine_page.evaluate(
        """() => { const r = App.ui.toolRow({name: 'read_file', checked: true, testid: 'tr',
          dataset: {rowKind: 'x'}, inputDataset: {mcpToolToggle: 'read_file', mcpSource: 'fs'}});
          document.getElementById('harness-root').appendChild(r.el); }"""
    )
    out = engine_page.evaluate(
        """() => { const i = document.querySelector('[data-testid=tr]');
          return [i.dataset.mcpToolToggle, i.dataset.mcpSource, i.closest('label').dataset.rowKind, i.closest('label').hasAttribute('data-mcp-tool-toggle')]; }"""
    )
    assert out == ["read_file", "fs", "x", False]

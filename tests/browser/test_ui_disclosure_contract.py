# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.disclosure`` (M31 F3 L03a, flight DD4/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane. No fixed sleeps: waits are on ``el.open``
or the ``toggle`` event.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# The retired ``.advanced-collapsible`` look, frozen as a fixture (its source rule left
# components.css in this leg). Everything but margin-top is compared.
LEGACY_PLAIN_CSS = """<style>
.legacy-adv { border-top: 1px solid var(--border); padding-top: 12px; }
.legacy-adv > summary { cursor: pointer; font-size: var(--font-size-body-sm); color: var(--fg-secondary); padding: 4px 0; }
.legacy-adv > summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.legacy-adv[open] > summary { color: var(--fg); }
</style>"""

MOUNT = """(extra) => {
  window.__ev = [];
  const o = Object.assign({variant: 'bordered', summary: 'Folder', testid: 'd', summaryTestid: 'd-s', summaryTextTestid: 'd-t',
    onToggle: (v) => window.__ev.push('toggle:' + v), onFirstOpen: () => window.__ev.push('first')}, extra || {});
  if (o.__actions) { o.actions = [App.ui.button({iconOnly: true, icon: 'trash', ariaLabel: 'Remove folder', testid: 'd-act',
    onClick: () => window.__ev.push('act')})]; delete o.__actions; }
  if (o.__meta) { const m = document.createElement('span'); m.textContent = '3 files'; o.meta = [m]; delete o.__meta; }
  window.__d = App.ui.disclosure(o);
  document.getElementById('harness-root').appendChild(window.__d.el);
  return true;
}"""


def _mount(page: Page, extra: str = "null", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT})({extra})")


def _events(page: Page) -> list:
    return page.evaluate("() => window.__ev")


def _wait_open(page: Page, value: bool) -> None:
    page.wait_for_function(f"() => window.__d.el.open === {str(value).lower()}")


def test_variant_is_required_and_plain_limits(engine_page: Page) -> None:
    load_harness(engine_page)
    msgs = engine_page.evaluate(
        """() => {
          const t = (o) => { try { App.ui.disclosure(o); return null; } catch (e) { return e.message; } };
          return [t({}), t({variant: 'nope'}), t({variant: 'plain', chevron: true}),
            t({variant: 'plain', actions: [document.createElement('button')]}),
            t({variant: 'plain', meta: [document.createElement('span')]}), t({variant: 'plain'}), t({variant: 'bordered'})];
        }"""
    )
    assert msgs[0] == 'App.ui.disclosure: unknown variant "undefined"'
    assert msgs[1] == 'App.ui.disclosure: unknown variant "nope"'
    assert all(m for m in msgs[2:5])
    assert msgs[5:] == [None, None]


def test_dom_shape_and_toggles_by_click_enter_and_space(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    shape = p.evaluate(
        """() => { const d = window.__d, el = d.el;
          return {tag: el.tagName, first: el.firstElementChild === d.summary, bodyInSummary: d.summary.contains(d.body),
            cls: el.className, confirmTitle: d.summaryText.hasAttribute('data-confirm-title'),
            chevron: !!d.summary.querySelector('.ui-disclosure-chevron'), actions: d.actions}; }"""
    )
    assert shape == {
        "tag": "DETAILS",
        "first": True,
        "bodyInSummary": False,
        "cls": "ui-disclosure ui-disclosure--bordered",
        "confirmTitle": True,
        "chevron": True,
        "actions": None,
    }
    summary = p.get_by_test_id("d-s")

    def settle(n: int) -> None:
        # Wait on the toggle event itself (they coalesce if two flips land in one task).
        p.wait_for_function(
            f"() => window.__ev.filter((e) => e.startsWith('toggle')).length === {n}"
        )

    summary.click()
    settle(1)
    summary.click()
    settle(2)
    summary.focus()
    p.keyboard.press("Enter")
    settle(3)
    p.keyboard.press("Space")
    settle(4)
    assert _events(p) == ["first", "toggle:true", "toggle:false", "toggle:true", "toggle:false"]


def test_first_open_once_set_open_and_initial_open(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__d.setOpen(true)")
    _wait_open(p, True)
    p.evaluate("() => window.__d.setOpen(false)")
    _wait_open(p, False)
    p.evaluate("() => window.__d.setOpen(true)")
    p.wait_for_function("() => window.__ev.filter((e) => e === 'toggle:true').length === 2")
    ev = _events(p)
    assert ev.count("first") == 1
    assert p.evaluate("() => window.__d.isOpen()") is True
    # open:true -> onFirstOpen synchronously at creation, no onToggle for the initial state.
    _mount(p, "{open: true}")
    assert _events(p) == ["first"]
    p.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    p.evaluate("() => new Promise((r) => setTimeout(r, 0))")
    assert _events(p) == ["first"]
    p.evaluate("() => window.__d.setOpen(false)")
    p.wait_for_function("() => window.__ev.includes('toggle:false')")
    assert _events(p) == ["first", "toggle:false"]


def test_action_button_does_not_toggle_and_svg_click(engine_page: Page) -> None:
    _mount(engine_page, "{__actions: true}")
    p = engine_page
    act = p.get_by_test_id("d-act")
    assert p.evaluate("() => !!document.querySelector('[data-testid=d-act] svg')")
    act.click()
    p.wait_for_function("() => window.__ev.includes('act')")
    act.focus()
    p.keyboard.press("Enter")
    p.wait_for_function("() => window.__ev.filter((e) => e === 'act').length === 2")
    p.keyboard.press("Space")
    p.wait_for_function("() => window.__ev.filter((e) => e === 'act').length === 3")
    # A real pointer click on the <svg> node's centre: pointer-events:none puts the target on the button.
    box = p.evaluate("""() => { const r = document.querySelector('[data-testid=d-act] svg').getBoundingClientRect();
      return {x: r.x + r.width / 2, y: r.y + r.height / 2}; }""")
    target = p.evaluate("([x, y]) => document.elementFromPoint(x, y).tagName", [box["x"], box["y"]])
    assert target == "BUTTON"
    p.mouse.click(box["x"], box["y"])
    p.wait_for_function("() => window.__ev.filter((e) => e === 'act').length === 4")
    # Let any (wrong) toggle event settle, then assert nothing toggled.
    p.evaluate("() => new Promise((r) => setTimeout(r, 50))")
    assert p.evaluate("() => window.__d.el.open") is False
    assert [e for e in _events(p) if e.startswith("toggle") or e == "first"] == []
    assert (
        p.evaluate(
            "() => getComputedStyle(document.querySelector('[data-testid=d-act] svg')).pointerEvents"
        )
        == "none"
    )


def test_accessible_names_meta_in_actions_out(engine_page: Page) -> None:
    _mount(engine_page, "{__actions: true, __meta: true}")
    p = engine_page
    expect(p.get_by_test_id("d-s")).to_have_accessible_name("Folder 3 files")
    expect(p.get_by_test_id("d-act")).to_have_accessible_name("Remove folder")
    assert (
        p.evaluate(
            "() => window.__d.summary.contains(document.querySelector('[data-testid=d-act]'))"
        )
        is True
    )
    assert (
        p.evaluate("() => window.__d.summary.getAttribute('aria-labelledby').split(' ').length")
        == 2
    )
    assert p.evaluate("() => window.__d.actions.parentNode === window.__d.summary")


def test_confirm_on_summary_and_set_summary_rules(engine_page: Page) -> None:
    _mount(engine_page, "{__actions: true}")
    p = engine_page
    out = p.evaluate(
        """() => new Promise((resolve) => {
          const d = window.__d, res = {};
          const act = d.actions.firstChild, chevron = d.summary.querySelector('.ui-disclosure-chevron');
          App.ui.confirm(d.summary, () => { res.committed = true; }, {revertMs: 150});
          res.armed = d.summary.classList.contains('confirm-delete');
          res.armedText = d.summaryText.textContent;
          res.setWhileArmed = d.setSummary('Other');
          res.textAfterSet = d.summaryText.textContent;
          setTimeout(() => {
            res.lapsedText = d.summaryText.textContent;
            res.lapsedArmed = d.summary.classList.contains('confirm-delete');
            res.setAfter = d.setSummary('Renamed');
            res.sameNodes = d.actions.firstChild === act && d.summary.querySelector('.ui-disclosure-chevron') === chevron && d.actions.parentNode === d.summary;
            App.ui.confirm(d.summary, () => { res.committed = true; }, {revertMs: 5000});
            App.ui.confirm(d.summary, () => { res.committed = true; });
            res.commitText = d.summaryText.textContent;
            resolve(res);
          }, 400);
        })"""
    )
    assert out["armed"] is True and out["armedText"] == "Confirm delete?"
    assert out["setWhileArmed"] is False and out["textAfterSet"] == "Confirm delete?"
    assert out["lapsedText"] == "Folder" and out["lapsedArmed"] is False
    assert out["setAfter"] is True and out["sameNodes"] is True
    assert out["committed"] is True


def test_body_rebuild_keeps_open_and_destroy_silences_callbacks(engine_page: Page) -> None:
    _mount(engine_page, "{open: true}")
    p = engine_page
    p.evaluate(
        "() => { window.__ev.length = 0; const b = window.__d.body; b.textContent = ''; b.appendChild(document.createElement('p')); }"
    )
    assert p.evaluate("() => window.__d.el.open") is True
    assert _events(p) == []
    p.evaluate("() => window.__d.destroy()")
    p.get_by_test_id("d-s").click()
    _wait_open(p, False)
    # The toggle event is queued after the attribute change; give it a frame to settle.
    p.evaluate(
        "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0))))"
    )
    assert _events(p) == []
    p.evaluate("() => window.__d.setOpen(true)")
    assert p.evaluate("() => window.__d.el.open") is False
    assert p.evaluate("() => window.__d.setSummary('x')") is False


PROPS_JS = """const PROPS = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'fontSize', 'fontWeight', 'fontFamily',
  'lineHeight', 'borderTopWidth', 'borderTopStyle', 'borderTopColor', 'borderRadius', 'backgroundColor', 'color', 'columnGap',
  'display', 'alignItems', 'cursor', 'listStyleType', 'userSelect'];
const snap = (el) => { const s = getComputedStyle(el); const o = {}; PROPS.forEach((p) => { o[p] = s[p]; }); return o; };
const diff = (a, b) => { const d = {}; PROPS.forEach((p) => { if (a[p] !== b[p]) d[p] = [a[p], b[p]]; }); return d; };"""


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_bordered_computed_styles_equal_legacy_mcp_tool_item(engine_page: Page, theme: str) -> None:
    load_harness(engine_page, theme)
    out = engine_page.evaluate(
        """() => {
          const host = document.createElement('div'); host.className = 'area-studio';
          host.innerHTML = '<details class="mcp-tool-item" open id="legacy"><summary class="mcp-tool-summary"><span class="mcp-tool-summary-text">Folder</span><span class="mcp-tool-chevron">▸</span></summary><div class="mcp-tool-body">body</div></details><div id="lib"></div>';
          document.getElementById('harness-root').appendChild(host);
          const d = App.ui.disclosure({variant: 'bordered', summary: 'Folder', open: true});
          d.body.textContent = 'body';
          host.querySelector('#lib').appendChild(d.el);
          """
        + PROPS_JS
        + """
          const L = host.querySelector('#legacy');
          const o = {
            root: diff(snap(L), snap(d.el)),
            summary: diff(snap(L.querySelector('summary')), snap(d.summary)),
            text: diff(snap(L.querySelector('.mcp-tool-summary-text')), snap(d.summaryText)),
            chevron: diff(snap(L.querySelector('.mcp-tool-chevron')), snap(d.summary.querySelector('.ui-disclosure-chevron'))),
            body: diff(snap(L.querySelector('.mcp-tool-body')), snap(d.body))
          };
          o.rotate = [getComputedStyle(L.querySelector('.mcp-tool-chevron')).transform, getComputedStyle(d.summary.querySelector('.ui-disclosure-chevron')).transform];
          o.bodyBorder = getComputedStyle(d.body).borderTopStyle;
          return o;
        }"""
    )
    rotate = out.pop("rotate")
    assert rotate[0] == rotate[1] and rotate[1] != "none"
    assert out.pop("bodyBorder") == "dashed"
    assert out == {"root": {}, "summary": {}, "text": {}, "chevron": {}, "body": {}}, out


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_plain_computed_styles_equal_legacy_advanced_collapsible(
    engine_page: Page, theme: str
) -> None:
    load_harness(engine_page, theme)
    out = engine_page.evaluate(
        """(css) => {
          const host = document.createElement('div'); host.className = 'area-studio';
          host.innerHTML = css + '<details class="legacy-adv" id="legacy"><summary>History</summary><div>x</div></details><div id="lib"></div>';
          document.getElementById('harness-root').appendChild(host);
          const d = App.ui.disclosure({variant: 'plain', summary: 'History'});
          host.querySelector('#lib').appendChild(d.el);
          """
        + PROPS_JS
        + """
          const L = host.querySelector('#legacy');
          const before = {root: diff(snap(L), snap(d.el)), summary: diff(snap(L.querySelector('summary')), snap(d.summary))};
          L.open = true; d.setOpen(true);
          const after = {summary: diff(snap(L.querySelector('summary')), snap(d.summary))};
          return {before, after, marker: getComputedStyle(d.summary).display, margin: getComputedStyle(d.el).marginTop};
        }""",
        LEGACY_PLAIN_CSS,
    )
    assert out["before"] == {"root": {}, "summary": {}}, out
    assert out["after"] == {"summary": {}}, out
    assert out["marker"] == "list-item"  # the native marker stays
    assert out["margin"] == "0px"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_armed_look_uses_the_danger_token(engine_page: Page, theme: str) -> None:
    _mount(engine_page, "{__actions: true}", theme)
    p = engine_page
    danger = p.evaluate(
        """() => {
          const probe = document.createElement('span'); probe.style.color = 'var(--status-danger)';
          document.getElementById('harness-root').appendChild(probe);
          const c = getComputedStyle(probe).color; probe.remove();
          App.ui.confirm(window.__d.summary, () => {});
          return c;
        }"""
    )
    # The border and icon colours transition (--motion-fast): wait for them to settle.
    p.wait_for_function(
        "(c) => getComputedStyle(window.__d.el).borderTopColor === c && getComputedStyle(window.__d.actions.firstChild).color === c",
        arg=danger,
    )
    out = p.evaluate(
        """() => { const d = window.__d;
          return {title: getComputedStyle(d.summaryText).color, icon: getComputedStyle(d.actions.querySelector('svg')).color,
            btn: getComputedStyle(d.actions.firstChild).color}; }"""
    )
    assert out == {"title": danger, "icon": danger, "btn": danger}

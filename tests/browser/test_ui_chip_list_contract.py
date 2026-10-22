# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.chipList`` (M31 F2 L4, flight DD3/DD4/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.

The behaviour is a copy of ``areas/admin/tools-form-helpers.js`` (``renderChipListEditor`` /
``wireChipListEditor``); the legacy comparison hand-writes that markup inside one explicit
``area-studio`` wrapper and compares a FIXED property list.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

PROPS_JS = """const PROPS = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'fontSize', 'fontWeight', 'fontFamily',
  'lineHeight', 'borderTopWidth', 'borderTopStyle', 'borderTopColor', 'borderRadius', 'backgroundColor', 'color', 'height',
  'columnGap', 'rowGap', 'display', 'flexWrap', 'alignItems', 'minHeight', 'minWidth', 'opacity', 'cursor'];
const snap = (el) => { const s = getComputedStyle(el); const o = {}; PROPS.forEach((p) => { o[p] = s[p]; }); return o; };
const diff = (a, b) => { const d = {}; PROPS.forEach((p) => { if (a[p] !== b[p]) d[p] = [a[p], b[p]]; }); return d; };"""

MOUNT = """(extra) => {
  window.__ch = [];
  const o = Object.assign({label: 'Allowed hosts', values: ['alpha', 'beta'], testid: 'cl', inputId: 'cl-input',
    dataset: {field: 'hosts', marker: 'm1'}, onChange: (v) => window.__ch.push(v)}, extra || {});
  window.__cl = App.ui.chipList(o);
  document.getElementById('harness-root').appendChild(window.__cl.el);
  return true;
}"""


def _mount(page: Page, extra: str = "null") -> None:
    load_harness(page)
    page.evaluate(f"({MOUNT})({extra})")


def _values(page: Page) -> list:
    return page.evaluate("() => window.__cl.values()")


def _paste(page: Page, text: str) -> bool:
    return page.evaluate(
        """(text) => { const ev = new Event('paste', {bubbles: true, cancelable: true});
          Object.defineProperty(ev, 'clipboardData', {value: {getData: () => text}});
          window.__cl.input.dispatchEvent(ev); return ev.defaultPrevented; }""",
        text,
    )


def test_dom_shape_attributes_and_api(engine_page: Page) -> None:
    _mount(engine_page, "{locked: ['alpha']}")
    out = engine_page.evaluate(
        """() => {
          const c = window.__cl, el = c.el;
          const chips = Array.from(el.querySelectorAll('.chip'));
          return {
            root: el.className, tid: el.getAttribute('data-testid'), role: [el.getAttribute('role'), el.getAttribute('aria-label')],
            data: [el.dataset.field, el.dataset.fieldType, el.dataset.marker],
            kids: Array.from(el.children).map((k) => k.tagName + '.' + k.className),
            locked: [chips[0].dataset.locked, chips[0].getAttribute('aria-label'), chips[0].textContent, chips[0].querySelectorAll('button').length],
            editable: [chips[1].textContent, chips[1].dataset.locked ?? null, chips[1].lastElementChild.className, chips[1].lastElementChild.getAttribute('aria-label'),
                       chips[1].lastElementChild.type, chips[1].lastElementChild.textContent],
            input: [c.input.type, c.input.className, c.input.id, c.input.getAttribute('aria-label'), c.input.placeholder],
            values: c.values(), api: Object.keys(c).sort()
          };
        }"""
    )
    assert out["root"] == "chip-list-editor" and out["tid"] == "cl"
    assert out["role"] == ["group", "Allowed hosts"]
    assert out["data"] == ["hosts", "array", "m1"]
    assert out["kids"] == ["SPAN.chip", "SPAN.chip", "INPUT.chip-list-input"]
    assert out["locked"] == ["true", "alpha (locked by operator)", "alpha", 0]
    assert out["editable"] == ["beta×", None, "ui-chip-remove", "Remove beta", "button", "×"]
    assert out["input"] == ["text", "chip-list-input", "cl-input", "Add entry", "Add entry…"]
    assert out["values"] == [
        "alpha",
        "beta",
    ]  # locked chips are included; the trailing x is stripped
    assert out["api"] == ["destroy", "el", "input", "setError", "setValues", "values"]
    # The labelled input is reachable by its name.
    expect(engine_page.get_by_role("textbox", name="Add entry")).to_have_count(1)
    expect(engine_page.get_by_role("button", name="Remove beta")).to_have_count(1)
    expect(engine_page.get_by_role("button", name="Remove alpha")).to_have_count(0)


def test_enter_comma_and_tab_commit_and_tab_on_empty_moves_on(engine_page: Page) -> None:
    _mount(engine_page, "{values: []}")
    p = engine_page
    p.locator(".chip-list-input").click()
    p.keyboard.type("one")
    p.keyboard.press("Enter")
    p.keyboard.type("two")
    p.keyboard.press(",")
    p.keyboard.type("three")
    p.keyboard.press("Tab")
    assert _values(p) == ["one", "two", "three"]
    assert p.evaluate(
        "() => [document.activeElement === window.__cl.input, window.__cl.input.value]"
    ) == [True, ""]
    assert p.evaluate("() => window.__ch") == [["one"], ["one", "two"], ["one", "two", "three"]]
    # Tab on an EMPTY input lets focus move on (a default action, not prevented).
    p.keyboard.press("Tab")
    assert p.evaluate("() => document.activeElement === window.__cl.input") is False


def test_duplicates_empty_commit_and_whitespace_do_not_fire(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.locator(".chip-list-input").click()
    p.keyboard.press("Enter")  # empty commit: clears, no onChange
    p.keyboard.type("alpha")
    p.keyboard.press("Enter")  # duplicate: cleared, no onChange
    p.keyboard.type("  ")
    p.keyboard.press("Enter")
    assert _values(p) == ["alpha", "beta"]
    assert p.evaluate("() => [window.__ch.length, window.__cl.input.value]") == [0, ""]
    p.keyboard.type(" gamma ")
    p.keyboard.press("Enter")
    assert _values(p) == ["alpha", "beta", "gamma"]  # trimmed


def test_paste_with_comma_splits_and_adds_plain_paste_is_untouched(engine_page: Page) -> None:
    _mount(engine_page, "{values: []}")
    p = engine_page
    assert _paste(p, "x, y,,z, x") is True
    assert _values(p) == ["x", "y", "z"]
    assert p.evaluate("() => window.__ch") == [["x", "y", "z"]]
    assert _paste(p, "no-commas-here") is False  # the browser's own paste handles it
    assert _values(p) == ["x", "y", "z"]


def test_backspace_on_empty_removes_nearest_editable_chip_before_the_input(
    engine_page: Page,
) -> None:
    _mount(engine_page, "{values: ['a', 'b', 'c'], locked: ['c']}")
    p = engine_page
    p.locator(".chip-list-input").click()
    p.keyboard.press("Backspace")  # skips the locked 'c' and removes 'b'
    assert _values(p) == ["a", "c"]
    p.keyboard.press("Backspace")
    assert _values(p) == ["c"]
    p.keyboard.press("Backspace")  # only a locked chip remains: nothing to remove
    assert _values(p) == ["c"]
    assert p.evaluate("() => window.__ch.length") == 2
    p.keyboard.type("x")
    p.keyboard.press("Backspace")  # a non-empty input edits text instead
    assert _values(p) == ["c"]


def test_click_on_chip_body_repositions_input_and_backspace_follows(engine_page: Page) -> None:
    _mount(engine_page, "{values: ['a', 'b', 'c'], locked: ['a']}")
    p = engine_page
    p.locator(".chip", has_text="c").click(position={"x": 4, "y": 4})
    order = p.evaluate(
        "() => Array.from(window.__cl.el.children).map((k) => k.classList.contains('chip') ? k.textContent : 'INPUT')"
    )
    assert order == ["a", "b×", "INPUT", "c×"]
    assert p.evaluate("() => document.activeElement === window.__cl.input") is True
    p.keyboard.type("n")
    p.keyboard.press("Enter")  # inserts at the input's position
    assert _values(p) == ["a", "b", "n", "c"]
    p.keyboard.press("Backspace")  # removes the chip immediately BEFORE the input ('n')
    assert _values(p) == ["a", "b", "c"]
    # A locked chip is not a reposition target.
    p.locator(".chip[data-locked]").click()
    order = p.evaluate(
        "() => Array.from(window.__cl.el.children).map((k) => k.classList.contains('chip') ? k.textContent : 'INPUT')"
    )
    assert order == ["a", "b×", "INPUT", "c×"]


def test_remove_button_removes_chip_and_fires(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_role("button", name="Remove beta").click()
    assert _values(p) == ["alpha"]
    assert p.evaluate("() => window.__ch") == [["alpha"]]


def test_validate_accept_reject_and_message(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{values: [], validate: (v) => v === 'ok' ? true : v === 'no' ? false : v === 'accept' ? 'accept' : 'Not allowed: ' + v, onReject: (v, m) => window.__rej = [v, m]}",
    )
    p = engine_page
    p.locator(".chip-list-input").click()
    for text in ["ok", "no", "accept", "bad"]:
        p.keyboard.type(text)
        p.keyboard.press("Enter")
    assert _values(p) == ["ok", "accept"]
    assert p.evaluate("() => window.__rej") == ["bad", "Not allowed: bad"]
    assert p.evaluate("() => window.__ch.length") == 2


def test_set_values_set_error_and_destroy(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("window.__cl.setValues(['x', 'y', 'x'], ['y'])")
    assert _values(p) == ["x", "y"]
    assert p.evaluate("() => window.__ch.length") == 0  # silent
    assert p.evaluate("() => Array.from(window.__cl.el.children).map((k) => k.tagName)") == [
        "SPAN",
        "SPAN",
        "INPUT",
    ]
    p.evaluate("window.__cl.setError(true)")
    assert p.evaluate(
        "() => [window.__cl.input.getAttribute('aria-invalid'), window.__cl.el.classList.contains('is-invalid')]"
    ) == ["true", True]
    border = p.evaluate("() => getComputedStyle(window.__cl.el).borderTopColor")
    assert border != "rgb(0, 0, 0)"
    p.evaluate("window.__cl.setError(false)")
    assert p.evaluate(
        "() => [window.__cl.input.getAttribute('aria-invalid'), window.__cl.el.classList.contains('is-invalid')]"
    ) == [None, False]
    p.evaluate("window.__cl.destroy()")
    p.locator(".chip-list-input").click()
    p.keyboard.type("z")
    p.keyboard.press("Enter")
    assert _values(p) == ["x", "y"]


def test_locked_value_missing_from_values_is_added_first(engine_page: Page) -> None:
    _mount(engine_page, "{values: ['b'], locked: ['a']}")
    assert _values(engine_page) == ["a", "b"]
    assert engine_page.locator(".chip[data-locked]").count() == 1


# ── sizes and styles (DD11, DD4) ────────────────────────────────────────────


def test_chip_size_remove_button_colours_and_focus_ring(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => {
          const chip = window.__cl.el.querySelector('.chip'), s = getComputedStyle(chip);
          const probe = document.createElement('span'); probe.style.fontSize = 'var(--font-size-body-sm)'; document.body.appendChild(probe);
          const bodySm = getComputedStyle(probe).fontSize; probe.remove();
          const rm = chip.querySelector('.ui-chip-remove');
          return {pad: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft], font: s.fontSize, bodySm, gap: s.columnGap,
                  radius: s.borderTopLeftRadius, rest: getComputedStyle(rm).color};
        }"""
    )
    assert out["pad"] == ["2px", "8px", "2px", "8px"]  # the chip in the list is 2px 8px
    assert out["font"] == out["bodySm"] and out["gap"] == "4px"
    # The remove "x" is --fg-secondary at rest and --status-danger on hover and focus (canvas, approved).
    colors = p.evaluate(
        """() => { const probe = document.createElement('span'); document.getElementById('harness-root').appendChild(probe);
          probe.style.color = 'var(--fg-secondary)'; const sec = getComputedStyle(probe).color;
          probe.style.color = 'var(--status-danger)'; const dan = getComputedStyle(probe).color; probe.remove(); return {sec, dan}; }"""
    )
    assert out["rest"] == colors["sec"]
    rm = p.get_by_role("button", name="Remove beta")
    rm.hover()
    p.wait_for_timeout(300)
    assert rm.evaluate("(el) => getComputedStyle(el).color") == colors["dan"]
    p.mouse.move(0, 0)
    p.wait_for_timeout(300)
    p.locator(".chip-list-input").focus()
    p.keyboard.press("Shift+Tab")  # keyboard focus lands on the last remove button: :focus-visible
    p.wait_for_timeout(300)
    assert p.evaluate("() => document.activeElement.className") == "ui-chip-remove"
    assert p.evaluate("() => getComputedStyle(document.activeElement).color") == colors["dan"]


def _legacy_chip_html(locked: bool) -> str:
    chip = (
        '<span class="chip" data-locked="true" aria-label="a (locked by operator)">a</span>'
        if locked
        else '<span class="chip">a<button type="button" class="chip-remove" aria-label="Remove a">×</button></span>'
    )
    return (
        '<div class="chip-list-editor" data-field="hosts" data-field-type="array">'
        + chip
        + '<input type="text" class="chip-list-input" placeholder="Add entry…" aria-label="Add entry"></div>'
    )


@pytest.mark.parametrize("locked", [False, True])
def test_computed_styles_equal_legacy_area_studio(engine_page: Page, locked: bool) -> None:
    load_harness(engine_page)
    engine_page.evaluate(
        """([legacy, locked]) => {
          // The explicit wrapper: area-studio; the locked chip's legacy rule is scoped to .tool-row-overrides.
          const host = document.createElement('div'); host.className = 'area-studio'; host.id = 'cmp';
          host.innerHTML = '<div class="tool-row-overrides"><div id="legacy-side">' + legacy + '</div><div id="lib-side"></div></div>';
          document.getElementById('harness-root').appendChild(host);
          const c = App.ui.chipList({values: ['a'], locked: locked ? ['a'] : []});
          host.querySelector('#lib-side').appendChild(c.el);
        }""",
        [_legacy_chip_html(locked), locked],
    )
    out = engine_page.evaluate(
        """() => {
          """
        + PROPS_JS
        + """
          const L = document.getElementById('legacy-side'), N = document.getElementById('lib-side');
          const o = {
            wrapper: diff(snap(L.querySelector('.chip-list-editor')), snap(N.querySelector('.chip-list-editor'))),
            chip: diff(snap(L.querySelector('.chip')), snap(N.querySelector('.chip'))),
            input: diff(snap(L.querySelector('.chip-list-input')), snap(N.querySelector('.chip-list-input')))
          };
          const lr = L.querySelector('.chip-remove'), nr = N.querySelector('.ui-chip-remove');
          if (lr && nr) o.remove = diff(snap(lr), snap(nr));
          return o;
        }"""
    )
    if "remove" in out:
        # The one approved change (canvas): the remove colour (accent -> fg-secondary); the border
        # colour resolves from currentColor, so it follows.
        assert set(out.pop("remove")) <= {"color", "borderTopColor"}
    assert out == {"wrapper": {}, "chip": {}, "input": {}}, out


def test_focus_within_border_is_accent(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    rest = p.evaluate("() => getComputedStyle(window.__cl.el).borderTopColor")
    p.locator(".chip-list-input").focus()
    focused = p.evaluate("() => getComputedStyle(window.__cl.el).borderTopColor")
    assert rest != focused

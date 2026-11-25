# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.chipList`` (M31 F2 L4, flight DD3/DD4/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.

The behaviour is a copy of the hand-built editor that lived in ``areas/admin/tools-form-helpers.js``
(deleted in M31 F5 L06, with its legacy-parity comparison; see the note before ``CASCADE_JS``).
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
            locked: [chips[0].dataset.locked, chips[0].getAttribute('aria-label'), chips[0].textContent + '|' + chips[0].querySelector('.visually-hidden').textContent, chips[0].querySelectorAll('button').length],
            editable: [chips[1].textContent, chips[1].dataset.locked ?? null, chips[1].lastElementChild.className, chips[1].lastElementChild.getAttribute('aria-label'),
                       chips[1].lastElementChild.type, chips[1].lastElementChild.textContent],
            input: [c.input.type, c.input.className, c.input.id, c.input.getAttribute('aria-label'), c.input.placeholder],
            values: c.values(), api: Object.keys(c).sort()
          };
        }"""
    )
    assert out["root"] == "chip-list-editor ui-chip-list" and out["tid"] == "cl"
    assert out["role"] == ["group", "Allowed hosts"]
    assert out["data"] == ["hosts", "array", "m1"]
    assert out["kids"] == ["SPAN.chip", "SPAN.chip", "INPUT.chip-list-input ui-chip-list-input"]
    assert out["locked"] == ["true", None, "alpha (locked by operator)| (locked by operator)", 0]
    assert out["editable"] == ["beta×", None, "ui-chip-remove", "Remove beta", "button", "×"]
    assert out["input"] == [
        "text",
        "chip-list-input ui-chip-list-input",
        "cl-input",
        "Add entry",
        "Add entry…",
    ]
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
    p.locator('.chip[data-value="c"]').click(position={"x": 4, "y": 4})
    order = p.evaluate(
        "() => Array.from(window.__cl.el.children).map((k) => k.classList.contains('chip') ? k.textContent : 'INPUT')"
    )
    assert order == ["a (locked by operator)", "b×", "INPUT", "c×"]
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
    assert order == ["a (locked by operator)", "b×", "INPUT", "c×"]


def test_remove_button_removes_chip_and_fires(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_role("button", name="Remove beta").click()
    assert _values(p) == ["alpha"]
    assert p.evaluate("() => window.__ch") == [["alpha"]]


_ACTIVE = """() => { const a = document.activeElement;
  return a === document.body ? 'BODY' : a === window.__cl.input ? 'INPUT'
    : a.getAttribute('aria-label'); }"""


def test_remove_button_keyboard_moves_focus_to_next_previous_then_input(
    engine_page: Page,
) -> None:
    _mount(engine_page, "{values: ['a', 'b', 'c']}")
    p = engine_page
    p.get_by_role("button", name="Remove b").focus()
    p.keyboard.press("Enter")
    assert _values(p) == ["a", "c"]
    assert p.evaluate(_ACTIVE) == "Remove c"
    p.keyboard.press("Enter")  # last chip: focus goes to the previous one
    assert _values(p) == ["a"]
    assert p.evaluate(_ACTIVE) == "Remove a"
    p.keyboard.press("Enter")  # none left: focus goes to the input
    assert _values(p) == []
    assert p.evaluate(_ACTIVE) == "INPUT"


def test_remove_button_focus_skips_locked_chips(engine_page: Page) -> None:
    _mount(engine_page, "{values: ['a', 'b'], locked: ['a']}")
    p = engine_page
    p.get_by_role("button", name="Remove b").focus()
    p.keyboard.press("Enter")
    assert _values(p) == ["a"]
    assert p.evaluate(_ACTIVE) == "INPUT"


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


# The legacy-parity comparison (`test_computed_styles_equal_legacy_area_studio`) was retired in
# M31 F5 L06: it compared the library chip list with the string-built chips styled by the
# `.area-studio .chip-list-editor:not(.ui-chip-list)` rules of studio.css, which were deleted
# with `tools-form-helpers.js` (the MCP editor, their last user, moved onto App.ui.chipList).
# The approved look is now pinned by the contract tests above and the ledger (rows 14 and 34).


def test_focus_within_border_is_accent(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    rest = p.evaluate("() => getComputedStyle(window.__cl.el).borderTopColor")
    p.locator(".chip-list-input").focus()
    focused = p.evaluate("() => getComputedStyle(window.__cl.el).borderTopColor")
    assert rest != focused


# --- M31 F3 L03c (flight DD4, DD8-6, DD11): the area cascade must not restyle a library chip list ---

CASCADE_JS = """([area, legacy]) => {
  const tok = (name, prop) => { const p = document.createElement('span'); p.style[prop] = 'var(' + name + ')';
    document.getElementById('harness-root').appendChild(p); const v = getComputedStyle(p)[prop]; p.remove(); return v; };
  const host = document.createElement('div'); host.className = area; host.id = 'cascade-host';
  document.getElementById('harness-root').appendChild(host);
  let el;
  if (legacy) {
    host.insertAdjacentHTML('beforeend', '<div class="chip-list-editor"><span class="chip" data-locked="true">a</span>'
      + '<span class="chip">b<button type="button" class="chip-remove">x</button></span><input class="chip-list-input"></div>');
    el = host.firstElementChild;
  } else {
    const c = App.ui.chipList({values: ['a', 'b'], locked: ['a']});
    host.appendChild(c.el); el = c.el; window.__cl = c;
    c.setError(true);
  }
  const cs = (n) => getComputedStyle(n);
  const locked = el.querySelector('[data-locked]');
  const rm = el.querySelector('.ui-chip-remove, .chip-remove');
  return {
    lockedBg: cs(locked).backgroundColor, lockedOpacity: cs(locked).opacity,
    rootBorder: cs(el).borderTopColor, removeColor: cs(rm).color,
    surfaceElevated: tok('--surface-elevated', 'backgroundColor'), danger: tok('--status-danger', 'borderTopColor') ,
    fgSecondary: tok('--fg-secondary', 'color'), accent: tok('--accent', 'color'),
    accentTranslucent: tok('--accent-translucent', 'backgroundColor')
  };
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("area", ["area-studio", "area-admin"])
def test_library_chip_list_keeps_its_own_look_under_an_area(
    engine_page: Page, area: str, theme: str
) -> None:
    load_harness(engine_page, theme)
    out = engine_page.evaluate(CASCADE_JS, [area, False])
    assert out["lockedBg"] == out["surfaceElevated"], out
    assert out["lockedOpacity"] == "0.7", out
    assert out["rootBorder"] == out["danger"], out
    assert out["removeColor"] == out["fgSecondary"], out


# `test_string_built_chip_list_keeps_the_area_look` was retired in M31 F5 L06 with the
# string-built chip-list CSS it pinned (see above).


# ── long values: data-value, the middle ellipsis (M31 F4 L04e) ───────────────

LONG = "".join(chr(97 + i % 26) for i in range(97))
LONG_SHOWN = "abcdefghijklmnopqrstuvw\u2026defghijklmnopqrs"


def test_long_chip_keeps_full_value_and_shows_a_one_line_ellipsis(engine_page: Page) -> None:
    _mount(
        engine_page, f"{{values: ['{LONG}', 'short'], locked: ['{LONG}z'], className: 'narrow'}}"
    )
    engine_page.add_style_tag(content=".narrow { width: 320px; }")
    out = engine_page.evaluate(
        """() => {
          const el = window.__cl.el, chips = Array.from(el.querySelectorAll('.chip'));
          const long = chips.find((c) => c.dataset.value.length === 97), locked = chips[0];
          const vis = long.querySelector('.ui-chip-text');
          const r = (n) => n.getBoundingClientRect(), lr = r(el);
          return {values: window.__cl.values(), viaStatic: App.ui.chipList.valuesOf(el),
            shown: vis.textContent, hidden: vis.getAttribute('aria-hidden'), twin: long.querySelector('.visually-hidden').textContent,
            title: long.getAttribute('title'), remove: long.querySelector('button').getAttribute('aria-label'),
            lockedAria: Array.from(locked.childNodes).filter((n) => !(n.nodeType === 1 && n.getAttribute('aria-hidden') === 'true')).map((n) => n.textContent).join(''), lockedShown: locked.querySelector('.ui-chip-text').textContent.length,
            lockedValue: locked.dataset.value.length, lockedHasButton: !!locked.querySelector('button'),
            oneLine: r(long).height < 36 && r(long).right <= lr.right + 1 && r(long).left >= lr.left,
            shortTwin: !chips.find((c) => c.dataset.value === 'short').querySelector('.visually-hidden'),
            allText: long.textContent.replace('\u00d7', '')};
        }"""
    )
    assert out["values"] == [LONG + "z", LONG, "short"] == out["viaStatic"]
    assert out["shown"] == LONG_SHOWN and out["hidden"] == "true" and out["twin"] == LONG
    assert out["title"] == LONG and out["remove"] == f"Remove {LONG}"
    assert out["lockedAria"] == LONG + "z (locked by operator)" and out["lockedShown"] == 40
    assert out["lockedValue"] == 98 and out["lockedHasButton"] is False
    assert out["oneLine"] is True and out["shortTwin"] is True


def test_truncated_chip_accessible_name_has_no_ellipsis(engine_page: Page) -> None:
    _mount(engine_page, f"{{values: ['{LONG}']}}")
    tree = engine_page.evaluate(
        "() => window.__cl.el.querySelector('.chip').querySelector('.visually-hidden').textContent"
    )
    assert tree == LONG and "\u2026" not in tree
    expect(engine_page.get_by_role("button", name=f"Remove {LONG}")).to_have_count(1)


def test_duplicates_backspace_and_click_work_on_truncated_chips(engine_page: Page) -> None:
    _mount(engine_page, f"{{values: ['{LONG}', 'tail']}}")
    engine_page.locator(".chip-list-input").fill(LONG)
    engine_page.keyboard.press("Enter")  # a duplicate of the FULL value: ignored
    assert (
        _values(engine_page) == [LONG, "tail"] and engine_page.evaluate("() => window.__ch") == []
    )
    engine_page.locator(".chip-list-input").fill(
        LONG + "x"
    )  # not a duplicate: a new chip with its own full value
    engine_page.keyboard.press("Enter")
    assert _values(engine_page) == [LONG, "tail", LONG + "x"]
    engine_page.locator(
        ".chip[data-value='tail'] .ui-chip-text"
    ).click()  # click on the text repositions the input
    engine_page.locator(".chip-list-input").focus()
    engine_page.keyboard.press("Backspace")  # removes the chip before the input
    assert _values(engine_page) == ["tail", LONG + "x"]
    assert engine_page.evaluate("() => window.__ch.at(-1)") == ["tail", LONG + "x"]


def test_paste_of_long_values_gives_each_its_own_data_value(engine_page: Page) -> None:
    _mount(engine_page, "{values: []}")
    _paste(engine_page, f"{LONG}, other")
    assert _values(engine_page) == [LONG, "other"]
    assert engine_page.evaluate(
        "() => Array.from(window.__cl.el.querySelectorAll('.chip')).map((c) => c.dataset.value)"
    ) == [LONG, "other"]


def test_set_values_rebuilds_with_data_value(engine_page: Page) -> None:
    _mount(engine_page)
    engine_page.evaluate(f"() => window.__cl.setValues(['{LONG}'], [])")
    assert _values(engine_page) == [LONG]
    assert (
        engine_page.evaluate("() => window.__cl.el.querySelector('.ui-chip-text').textContent")
        == LONG_SHOWN
    )

# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.chipList``'s ``suggest`` option
(sortie 10, DD3). Every test runs in Chromium and WebKit through ``engine_page`` +
``load_harness``; lane ``contracts-controls``.

``suggest(term) -> [{value, label, detail}]`` turns the chip input into a search-ahead
combobox. Without it the control is exactly the existing one (the regression test).
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

CATALOGUE = """(() => {
  const names = ['shell', 'python_exec', 'read_file', 'write_file', 'mcp__gf__typeText', 'mcp__gf__vaultFill',
    'mcp__gf__vaultList', 'mcp__gf__vaultTotp', 'mcp__gf__vaultUnlock', 'mcp__gf__vaultAnswerAuth',
    'mcp__gf__navigate', 'mcp__gf__click', 'mcp__gf__vaultX'];
  return names.map((n) => ({value: n, label: n, detail: n.startsWith('mcp__') ? 'Goldfinch' : 'Built-in'}));
})()"""

MOUNT = (
    """(extra) => {
  window.__ch = [];
  const cat = %s;
  const o = Object.assign({label: 'Allowed tools', values: [], testid: 'cl', inputId: 'cl-input',
    onChange: (v) => window.__ch.push(v),
    suggest: (term) => cat.filter((t) => t.value.toLowerCase().indexOf(term.toLowerCase()) >= 0)}, extra || {});
  window.__cl = App.ui.chipList(o);
  const host = document.createElement('div');
  host.id = 'host';
  host.style.cssText = 'width:420px;padding:20px';
  host.appendChild(window.__cl.el);
  document.getElementById('harness-root').appendChild(host);
  window.__esc = 0;
  host.addEventListener('keydown', (e) => { if (e.key === 'Escape') window.__esc += 1; });
  return true;
}"""
    % CATALOGUE
)


def _mount(page: Page, extra: str = "null") -> None:
    load_harness(page)
    page.evaluate(f"({MOUNT})({extra})")


def _values(page: Page) -> list:
    return page.evaluate("() => window.__cl.values()")


def _options(page: Page) -> list:
    return page.evaluate(
        "() => Array.from(window.__cl.el.querySelectorAll('[role=option]')).map((o) => o.getAttribute('data-value'))"
    )


def _focus_type(page: Page, text: str) -> None:
    page.locator("#cl-input").click()
    page.keyboard.type(text)


def test_without_suggest_the_dom_and_behaviour_are_unchanged(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const c = App.ui.chipList({label: 'L', values: ['a'], inputId: 'i'});
          document.getElementById('harness-root').appendChild(c.el);
          return {root: c.el.className, kids: Array.from(c.el.children).map((k) => k.tagName + '.' + k.className),
            attrs: Array.from(c.input.attributes).map((a) => a.name).sort(), pop: c.el.querySelector('[role=listbox]'),
            pos: getComputedStyle(c.el).position};
        }"""
    )
    assert out["root"] == "chip-list-editor ui-chip-list"
    assert out["kids"] == ["SPAN.chip", "INPUT.chip-list-input ui-chip-list-input"]
    assert out["attrs"] == ["aria-label", "class", "id", "placeholder", "type"]
    assert out["pop"] is None and out["pos"] == "static"
    # Typing opens nothing, and Enter adds the typed text.
    engine_page.locator("#i").click()
    engine_page.keyboard.type("sh")
    assert (
        engine_page.evaluate(
            "() => document.querySelectorAll('[role=option], [role=listbox]').length"
        )
        == 0
    )
    engine_page.keyboard.press("Enter")
    assert engine_page.evaluate(
        "() => App.ui.chipList.valuesOf(document.querySelector('.ui-chip-list'))"
    ) == ["a", "sh"]


def test_aria_contract_and_states(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    attrs = p.evaluate(
        """() => { const i = window.__cl.input; const lb = window.__cl.el.querySelector('[role=listbox]');
          return {role: i.getAttribute('role'), auto: i.getAttribute('aria-autocomplete'), exp: i.getAttribute('aria-expanded'),
            ctl: i.getAttribute('aria-controls') === lb.id, active: i.getAttribute('aria-activedescendant'),
            hidden: lb.parentElement.hidden, inRoot: window.__cl.el.contains(lb), cls: window.__cl.el.className}; }"""
    )
    assert attrs == {
        "role": "combobox",
        "auto": "list",
        "exp": "false",
        "ctl": True,
        "active": None,
        "hidden": True,
        "inRoot": True,
        "cls": "chip-list-editor ui-chip-list ui-chip-list--suggest",
    }
    _focus_type(p, "vault")
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "true"
    expect(p.get_by_role("option")).to_have_count(6)
    # No option is active until an arrow key; the root is the popover's positioning box.
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-activedescendant')") is None
    assert p.evaluate("() => getComputedStyle(window.__cl.el).position") == "relative"
    p.keyboard.press("ArrowDown")
    act = p.evaluate(
        """() => { const i = window.__cl.input; const id = i.getAttribute('aria-activedescendant');
          const row = document.getElementById(id);
          return [row.getAttribute('role'), row.getAttribute('aria-selected'),
            window.__cl.el.querySelectorAll('[aria-selected=true]').length]; }"""
    )
    assert act == ["option", "true", 1]


def test_option_rows_show_label_and_detail(engine_page: Page) -> None:
    _mount(engine_page)
    _focus_type(engine_page, "typeT")
    row = engine_page.get_by_role("option")
    expect(row).to_have_count(1)
    expect(row).to_contain_text("mcp__gf__typeText")
    expect(row).to_contain_text("Goldfinch")
    fam = engine_page.evaluate(
        "() => [getComputedStyle(document.querySelector('.ui-chip-list-option-label')).fontFamily.toLowerCase().includes('mono')]"
    )
    assert fam == [True]


def test_at_most_eight_and_chosen_values_are_left_out(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "mcp__gf__")
    assert len(_options(p)) == 8  # 9 match, the cap is 8


def test_chosen_values_are_left_out(engine_page: Page) -> None:
    _mount(engine_page, "{values: ['mcp__gf__click']}")
    p = engine_page
    _focus_type(p, "mcp__gf__")
    assert "mcp__gf__click" not in _options(p)
    p.keyboard.press("Control+a")
    p.keyboard.type("click")
    # The only match is already chosen: no option, the status line says so.
    assert _options(p) == []
    expect(p.locator(".ui-chip-list-status")).to_have_text("No tool matches “click”.")
    # The visible line is not a second live region; the hidden live node speaks.
    assert (
        p.evaluate("() => document.querySelector('.ui-chip-list-status').getAttribute('role')")
        is None
    )
    expect(p.locator("[role=status]")).to_have_count(1)
    expect(p.locator(".ui-chip-list-live")).to_have_text("No tool matches “click”.")


def test_case_insensitive_and_whitespace_term(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "  SHELL ")
    assert _options(p) == ["shell"]
    p.keyboard.press("Control+a")
    p.keyboard.press("Backspace")
    # An empty term closes the list.
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "false"
    assert p.evaluate("() => window.__cl.el.querySelector('.ui-chip-list-suggest').hidden") is True
    p.keyboard.type("   ")
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "false"


def test_zero_matches_shows_a_status_line_and_no_options(engine_page: Page) -> None:
    _mount(engine_page)
    _focus_type(engine_page, "zzz")
    assert _options(engine_page) == []
    expect(engine_page.locator(".ui-chip-list-status")).to_have_text("No tool matches “zzz”.")
    # No options: the listbox is collapsed (not expanded) though the no-match line shows.
    assert engine_page.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "false"
    # The status line is not inside the listbox (a listbox holds only options).
    assert (
        engine_page.evaluate("() => window.__cl.el.querySelector('[role=listbox]').children.length")
        == 0
    )
    expect(engine_page.locator(".ui-chip-list-live")).to_have_text("No tool matches “zzz”.")


def test_live_region_is_permanent_and_outside_the_popover(engine_page: Page) -> None:
    _mount(engine_page)
    info = engine_page.evaluate(
        """() => { const live = window.__cl.el.querySelector('.ui-chip-list-live');
          return {role: live.getAttribute('role'), inPop: !!live.closest('.ui-chip-list-suggest'),
            hidden: live.hidden, text: live.textContent}; }"""
    )
    assert info == {"role": "status", "inPop": False, "hidden": False, "text": ""}


def test_more_than_eight_matches_say_showing_8_of_n(engine_page: Page) -> None:
    _mount(engine_page)
    _focus_type(engine_page, "mcp__")
    assert len(_options(engine_page)) == 8
    expect(engine_page.locator(".ui-chip-list-live")).to_have_text(
        "Showing 8 of 9. Keep typing to narrow."
    )
    expect(engine_page.locator(".ui-chip-list-status")).to_have_text(
        "Showing 8 of 9. Keep typing to narrow."
    )


def test_accessible_names_input_has_the_label_and_listbox_is_named(engine_page: Page) -> None:
    _mount(engine_page, "{suggestLabel: 'Tool suggestions'}")
    names = engine_page.evaluate(
        """() => [window.__cl.input.getAttribute('aria-label'),
          window.__cl.el.querySelector('[role=listbox]').getAttribute('aria-label')]"""
    )
    assert names == ["Allowed tools", "Tool suggestions"]
    _mount(engine_page)
    assert (
        engine_page.evaluate(
            "() => Array.from(document.querySelectorAll('[role=listbox]')).pop().getAttribute('aria-label')"
        )
        == "Suggestions"
    )


def test_arrows_wrap_and_enter_adds_with_keyboard_only(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "vault")
    first, last = _options(p)[0], _options(p)[-1]

    def active() -> str:
        return p.evaluate(
            "() => document.getElementById(window.__cl.input.getAttribute('aria-activedescendant')).getAttribute('data-value')"
        )

    p.keyboard.press("ArrowDown")
    assert active() == first
    p.keyboard.press("ArrowUp")  # wraps to the last
    assert active() == last
    p.keyboard.press("ArrowDown")  # wraps to the first
    assert active() == first
    p.keyboard.press("ArrowDown")
    second = active()
    p.keyboard.press("Enter")
    assert _values(p) == [second]
    assert p.evaluate(
        "() => [window.__cl.input.value, document.activeElement === window.__cl.input]"
    ) == ["", True]
    assert p.evaluate("() => window.__ch") == [[second]]
    # The input is empty, so the list closed and nothing is active.
    assert p.evaluate(
        "() => [window.__cl.input.getAttribute('aria-expanded'), window.__cl.input.getAttribute('aria-activedescendant')]"
    ) == ["false", None]
    # A chosen value is not suggested again.
    p.keyboard.type("vault")
    assert second not in _options(p)


def test_click_on_an_option_adds_and_keeps_focus_in_the_input(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "navig")
    p.get_by_role("option").first.click()
    assert _values(p) == ["mcp__gf__navigate"]
    assert p.evaluate(
        "() => [document.activeElement === window.__cl.input, window.__cl.input.value]"
    ) == [True, ""]
    assert p.evaluate("() => window.__ch") == [["mcp__gf__navigate"]]


def test_hover_moves_the_active_option(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "vault")
    p.get_by_role("option").nth(2).hover()
    assert (
        p.evaluate(
            "() => document.getElementById(window.__cl.input.getAttribute('aria-activedescendant')).getAttribute('data-value')"
        )
        == "mcp__gf__vaultTotp"
    )


def test_escape_closes_without_clearing_and_stops_propagation_only_while_open(
    engine_page: Page,
) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "vault")
    p.keyboard.press("Escape")
    assert p.evaluate(
        "() => [window.__cl.input.getAttribute('aria-expanded'), window.__cl.input.value, window.__esc]"
    ) == ["false", "vault", 0]
    # Closed: Escape reaches the ancestors as usual.
    p.keyboard.press("Escape")
    assert p.evaluate("() => window.__esc") == 1
    # Typing reopens.
    p.keyboard.type("x")
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "true"


def test_enter_with_no_active_option_or_closed_list_adds_the_typed_text(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "vault")
    p.keyboard.press("Enter")  # list open, nothing active: today's behaviour
    assert _values(p) == ["vault"]
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "false"
    p.keyboard.type("custom_tool")
    p.keyboard.press("Escape")
    p.keyboard.press("Enter")  # list closed
    assert _values(p) == ["vault", "custom_tool"]


def test_tab_and_comma_commit_the_typed_text(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "shell")
    p.keyboard.press("ArrowDown")
    p.keyboard.press("Tab")
    assert _values(p) == ["shell"]
    p.keyboard.type("abc")
    p.keyboard.press(",")
    assert _values(p) == ["shell", "abc"]


def test_blur_closes_without_adding(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "vault")
    p.keyboard.press("ArrowDown")
    p.evaluate("() => window.__cl.input.blur()")
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "false"
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-activedescendant')") is None
    assert _values(p) == []
    assert p.evaluate("() => window.__ch") == []


def test_popover_sits_under_the_input_inside_the_control(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    _focus_type(p, "vault")
    box = p.evaluate(
        """() => { const r = window.__cl.el.getBoundingClientRect(); const pp = window.__cl.el.querySelector('.ui-chip-list-suggest').getBoundingClientRect();
          return {rootLeft: r.left, rootRight: r.right, rootBottom: r.bottom, left: pp.left, right: pp.right, top: pp.top}; }"""
    )
    assert abs(box["left"] - box["rootLeft"]) < 1.5 and abs(box["right"] - box["rootRight"]) < 1.5
    assert box["top"] >= box["rootBottom"]


def test_paste_with_comma_still_splits_and_no_document_listener(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    handled = p.evaluate(
        """() => { const ev = new Event('paste', {bubbles: true, cancelable: true});
          Object.defineProperty(ev, 'clipboardData', {value: {getData: () => 'a, b'}});
          window.__cl.input.dispatchEvent(ev); return ev.defaultPrevented; }"""
    )
    assert handled is True
    assert _values(p) == ["a", "b"]
    src = p.evaluate("() => App.ui.chipList.toString()")
    assert "document.addEventListener" not in src


def test_destroy_removes_the_suggest_listeners(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__cl.destroy()")
    p.locator("#cl-input").click()
    p.keyboard.type("vault")
    assert p.evaluate("() => window.__cl.input.getAttribute('aria-expanded')") == "false"

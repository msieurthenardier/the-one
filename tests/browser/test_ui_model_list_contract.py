# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.modelList`` (M31 F6 L08, flight DD10): a
presentational keyed list of models in sections with row actions, busy and error states and
focus kept across a reconcile. Chromium and WebKit through ``engine_page`` + ``load_harness``
(no app spawn); falls in the ``contracts-controls`` lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

_SETUP = """() => {
  window.__calls = [];
  window.__lost = 0;
  window.__list = App.ui.modelList({
    label: 'Models', testid: 'ml', actions: ['unload', 'load', 'delete'],
    onAction: (n, a) => __calls.push([n, a]),
    onFocusLost: () => { __lost++; }
  });
  document.getElementById('harness-root').appendChild(__list.el);
  window.__secs = (running, available) => [
    {key: 'running', label: 'Running', rows: running.map(n => ({name: n, state: 'running', size: '1 GB', caps: ['tools']}))},
    {key: 'available', label: 'Available', rows: available.map(n => ({name: n, state: 'idle', size: '2 GB', caps: ['completion']}))}
  ];
}"""


def _mount(page: Page) -> None:
    load_harness(page)
    page.evaluate(_SETUP)


def _rec(page: Page, running: list[str], available: list[str]) -> None:
    page.evaluate("([r, a]) => __list.reconcile(__secs(r, a))", [running, available])


def _row(page: Page, name: str):
    return page.locator(f'[data-testid=ml] .ui-model-row[data-name="{name}"]')


def _active(page: Page) -> str:
    return page.evaluate(
        "() => { const a = document.activeElement; const r = a && a.closest && a.closest('.ui-model-row'); return a === document.body ? 'body' : (r ? r.dataset.name : '?') + ':' + (a.dataset.action || ''); }"
    )


def test_reconcile_builds_sections_rows_and_markup(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, ["a"], ["b", "c"])
    assert page.evaluate(
        "() => Array.from(__list.el.children).map(e => e.className.indexOf('section-label') > -1 ? 'L:' + e.textContent : e.dataset.name + '@' + e.dataset.section)"
    ) == ["L:Running", "a@running", "L:Available", "b@available", "c@available"]
    assert (
        page.evaluate(
            "() => __list.el.getAttribute('role') + '|' + __list.el.getAttribute('aria-label')"
        )
        == "group|Models"
    )
    # Buttons per state: Unload on running; Load and Delete on idle.
    vis = page.evaluate(
        "() => ['a', 'b'].map(n => Array.from(document.querySelectorAll('.ui-model-row[data-name=' + n + '] button')).filter(b => !b.hidden).map(b => b.dataset.action))"
    )
    assert vis == [["unload"], ["load", "delete"]]
    # The name is mono, carries the full id as a title, and chips render.
    family = page.evaluate(
        "() => getComputedStyle(__list.el.querySelector('.ui-model-name')).fontFamily"
    ).lower()
    assert "mono" in family
    assert page.evaluate("() => __list.el.querySelector('.ui-model-name').title") == "a"
    assert (
        page.evaluate("() => __list.el.querySelectorAll('.cap-chip-row .chip').length") == 5
    )  # a: tools; b and c: completion + no tools


def test_chip_counts_follow_the_tools_rule(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, ["a"], ["b"])
    assert (
        page.evaluate("() => __list.el.querySelector('[data-name=a] .cap-chip-row').textContent")
        == "tools"
    )
    assert (
        page.evaluate("() => __list.el.querySelector('[data-name=b] .cap-chip-row').textContent")
        == "completionno tools"
    )
    assert page.evaluate("() => App.ui.modelList.capabilityChips(null)") is None
    assert page.evaluate("() => App.ui.modelList.capabilityChips([])") is None
    assert (
        page.evaluate(
            "() => App.ui.modelList.capabilityChips(['tools']).querySelectorAll('.chip--danger').length"
        )
        == 0
    )


def test_a_row_moves_between_sections_on_the_same_node(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a", "b"])
    page.evaluate("() => { window.__node = __list.el.querySelector('[data-name=b]'); }")
    _rec(page, ["b"], ["a"])
    assert page.evaluate("() => __list.el.querySelector('[data-name=b]') === __node")
    assert page.evaluate("() => __node.dataset.section") == "running"
    assert page.evaluate("() => __list.el.children[0].textContent") == "Running"


def test_an_empty_section_has_no_label_and_empty_reconcile_clears(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    assert page.evaluate(
        "() => Array.from(__list.el.querySelectorAll('.ui-model-section-label')).map(e => e.textContent)"
    ) == ["Available"]
    page.evaluate("() => __list.reconcile([])")
    assert page.evaluate("() => __list.el.children.length") == 0


def test_focus_stays_on_load_then_moves_to_unload_as_the_row_runs(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    page.evaluate("() => __list.el.querySelector('[data-action=load]').focus()")
    _rec(page, [], ["a"])
    assert _active(page) == "a:load"
    _rec(page, ["a"], [])
    assert _active(page) == "a:unload"


def test_focus_order_after_the_focused_row_goes(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a", "b", "c"])
    page.evaluate("() => __list.el.querySelector('[data-name=b] [data-action=load]').focus()")
    _rec(page, [], ["a", "c"])
    assert _active(page) == "c:load"  # the NEXT row first
    page.evaluate("() => __list.el.querySelector('[data-name=c] [data-action=load]').focus()")
    _rec(page, [], ["a"])
    assert _active(page) == "a:load"  # then the PREVIOUS row
    page.evaluate("() => __list.el.querySelector('[data-name=a] [data-action=load]').focus()")
    _rec(page, [], [])
    assert page.evaluate("() => __lost") == 1  # no row left


def test_clicks_set_busy_and_call_on_action(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    _row(page, "a").locator("[data-action=load]").click()
    assert page.evaluate("() => __calls") == [["a", "load"]]
    btn = _row(page, "a").locator("[data-action=load]")
    assert btn.text_content() == "Loading…" and btn.is_disabled()


def test_done_ends_on_the_next_reconcile_and_busy_survives_others(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    _row(page, "a").locator("[data-action=load]").click()
    _rec(page, [], ["a"])  # another refresh: still busy
    assert _row(page, "a").locator("[data-action=load]").is_disabled()
    page.evaluate("() => __list.setRowBusy('a', 'done')")
    assert _row(page, "a").locator("[data-action=load]").is_disabled()  # not until reconcile
    _rec(page, ["a"], [])
    btn = _row(page, "a").locator("[data-action=load]")
    assert btn.text_content() == "Load" and btn.is_enabled()
    assert _active(page) == "a:unload"  # the held focus followed the row to Unload


def test_failure_restores_label_focus_and_shows_an_error(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    page.evaluate("() => __list.el.querySelector('[data-action=load]').focus()")
    _row(page, "a").locator("[data-action=load]").click()
    page.evaluate("() => { __list.setRowBusy('a', null); __list.setRowError('a', 'load failed'); }")
    btn = _row(page, "a").locator("[data-action=load]")
    assert btn.text_content() == "Load" and btn.is_enabled()
    assert _active(page) == "a:load"
    assert "load failed" in _row(page, "a").locator(".ui-model-error").text_content()
    page.evaluate("() => __list.setRowError('a', null)")
    assert _row(page, "a").locator(".ui-model-error").is_hidden()


def test_row_error_auto_clears(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    page.evaluate("() => __list.setRowError('a', 'boom')")
    assert _row(page, "a").locator(".ui-model-error").is_visible()
    page.wait_for_timeout(4300)
    assert _row(page, "a").locator(".ui-model-error").is_hidden()


def test_delete_is_armed_then_confirmed_and_survives_a_reconcile(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    del_btn = _row(page, "a").locator("[data-action=delete]")
    del_btn.click()
    assert page.evaluate("() => __calls") == []
    assert "Confirm delete?" in del_btn.text_content()
    page.evaluate("() => { window.__del = __list.el.querySelector('[data-action=delete]'); }")
    _rec(page, [], ["a"])
    assert page.evaluate("() => __list.el.querySelector('[data-action=delete]') === __del")
    assert "Confirm delete?" in del_btn.text_content()
    del_btn.click()
    assert page.evaluate("() => __calls") == [["a", "delete"]]
    assert "Deleting…" in del_btn.text_content()
    # A failure reverts the arm and restores the label.
    page.evaluate("() => __list.setRowBusy('a', null)")
    assert del_btn.text_content() == "Delete" and del_btn.is_enabled()
    assert page.evaluate("() => __del.classList.contains('confirm-delete')") is False


def test_armed_delete_reverts_when_the_row_starts_running(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    _row(page, "a").locator("[data-action=delete]").click()
    _rec(page, ["a"], [])
    assert (
        page.evaluate(
            "() => __list.el.querySelector('[data-action=delete]').classList.contains('confirm-delete')"
        )
        is False
    )
    assert page.evaluate("() => __list.el.querySelector('[data-action=delete]').hidden")
    assert (
        page.evaluate(
            "() => __list.el.querySelector('[data-action=delete] [data-confirm-title]').textContent"
        )
        == "Delete"
    )


def test_a_long_name_truncates_with_a_title(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    name = "m" * 200
    _rec(page, [], [name])
    info = page.evaluate(
        "() => { const n = __list.el.querySelector('.ui-model-name'); const s = getComputedStyle(n); return [n.title.length, s.textOverflow, s.whiteSpace, n.scrollWidth > n.clientWidth]; }"
    )
    assert info == [200, "ellipsis", "nowrap", True]


def test_duplicate_names_are_tolerated_first_wins(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, ["a"], ["a", "b"])
    assert page.evaluate("() => __list.el.querySelectorAll('[data-name=a]').length") == 1
    assert (
        page.evaluate("() => __list.el.querySelector('[data-name=a]').dataset.section") == "running"
    )


def test_compact_plain_list_has_no_actions_and_no_dot(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.__p = App.ui.modelList({density: 'compact'});
          document.getElementById('harness-root').appendChild(__p.el);
          __p.reconcile([{key: 'm', label: null, rows: [{name: 'x'}, {name: 'y'}]}]);
        }"""
    )
    info = page.evaluate(
        "() => [__p.el.querySelectorAll('button').length, __p.el.querySelectorAll('.ui-status').length, __p.el.querySelectorAll('.ui-model-section-label').length, getComputedStyle(__p.el.querySelector('.ui-model-row')).cursor]"
    )
    assert info == [0, 0, 0, "default"]


def test_destroy_clears_rows_and_ignores_later_calls(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, [], ["a"])
    page.evaluate("() => { __list.setRowError('a', 'x'); __list.destroy(); }")
    _rec(page, [], ["b"])
    assert page.evaluate("() => __list.el.querySelectorAll('[data-name=b]').length") == 0


def test_row_actions_are_named_for_their_model(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    _rec(page, ["r"], ["a"])
    assert _row(page, "r").locator("[data-action=unload]").get_attribute("aria-label") == "Unload r"
    load = _row(page, "a").locator("[data-action=load]")
    assert load.get_attribute("aria-label") == "Load a"
    delete = _row(page, "a").locator("[data-action=delete]")
    assert delete.get_attribute("aria-label") == "Delete a"
    # Armed: the name follows the confirm label; a reconcile keeps it; busy and failure
    # restore it.
    delete.click()
    assert delete.get_attribute("aria-label") == "Confirm delete? a"
    _rec(page, ["r"], ["a"])
    assert delete.get_attribute("aria-label") == "Confirm delete? a"
    delete.click()
    assert delete.get_attribute("aria-label") == "Deleting… a"
    page.evaluate("() => __list.setRowBusy('a', null)")
    assert delete.get_attribute("aria-label") == "Delete a"
    # An armed Delete reverted because the row started running is named plainly again.
    delete.click()
    _rec(page, ["a"], [])
    assert delete.get_attribute("aria-label") == "Delete a"
    # The visible label's text starts the accessible name (label in name).
    for btn, text in ((load, "Load"),):
        assert btn.get_attribute("aria-label").startswith(text)

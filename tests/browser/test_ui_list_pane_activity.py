# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.listPane``'s ``item.activity``
option (M31 F6 L10b): the per-row working ring and new-reply dot of the Chats list.

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``
(armed-row tests use the harness-loaded ui/confirm.js; no app spawn). Falls in the
``contracts-controls`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

MOUNT_JS = """(opts) => {
  const root = document.getElementById('harness-root');
  const col = document.createElement('div');
  col.style.cssText = 'width: 300px; height: 420px; display: flex; flex-direction: column;';
  const mk = (id, activity, extra) => Object.assign({
    id, label: 'Chat ' + id, time: '10:4' + id.charCodeAt(0) % 10, meta: 'agent-' + id,
    testid: 'ac-row-' + id, activity, href: '#row-' + id,
    action: {label: 'Delete chat: Chat ' + id, icon: 'trash', testid: 'ac-del-' + id, onClick: () => {}},
  }, extra || {});
  window.__mk = mk;
  const c = App.ui.listPane(Object.assign({
    title: 'Chats', testid: 'ac-root', rowStyle: 'chats',
    groups: [{id: 'today', label: 'Today', items: [mk('a'), mk('b', 'working'), mk('c', 'new')]}],
  }, opts || {}));
  col.appendChild(c.el);
  root.append(col);
  window.__pane = c;
  return true;
}"""

PROBE_JS = """() => Array.from(document.querySelectorAll('[data-testid=ac-root] .ui-list-pane-row')).map((row) => {
  const slot = row.querySelector('.ui-list-pane-activity');
  const b = row.getBoundingClientRect();
  const sb = slot && slot.getBoundingClientRect();
  const before = slot && getComputedStyle(slot, '::before');
  return {
    cls: slot ? slot.className : null,
    ariaHidden: slot ? slot.getAttribute('aria-hidden') : null,
    w: sb && sb.width, h: sb && sb.height, rowH: b.height,
    hidden: Array.from(row.querySelectorAll('.visually-hidden')).map((n) => n.textContent),
    text: row.textContent,
    anim: before ? before.animationName : null,
    radius: before ? before.borderRadius : null,
    bg: before ? before.backgroundColor : null,
    bt: before ? before.borderTopColor : null,
  };
})"""


def _mount(page: Page, opts: str = "{}", reduced: bool = False) -> None:
    page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
    load_harness(page, "dark")
    page.evaluate(f"({MOUNT_JS})({opts})")


def test_every_row_reserves_a_fixed_slot_and_the_name_run_is_separate(engine_page: Page) -> None:
    _mount(engine_page)
    rows = engine_page.evaluate(PROBE_JS)
    for r in rows:
        assert r["ariaHidden"] == "true"
        assert (r["w"], r["h"]) == (12, 12), r
    assert [r["cls"] for r in rows] == [
        "ui-list-pane-activity",
        "ui-list-pane-activity ui-list-pane-activity--working",
        "ui-list-pane-activity ui-list-pane-activity--new",
    ]
    assert rows[0]["hidden"] == [""] and rows[0]["text"].startswith("Chat a")
    assert rows[1]["hidden"] == [", Working"], rows[1]
    assert rows[2]["hidden"] == [", New reply"], rows[2]
    # No layout shift: a row's height is the same with and without an indicator.
    assert rows[0]["rowH"] == rows[1]["rowH"] == rows[2]["rowH"]


def test_the_two_marks_differ_in_shape_and_working_animates(engine_page: Page) -> None:
    _mount(engine_page)
    rows = engine_page.evaluate(PROBE_JS)
    working, new = rows[1], rows[2]
    assert working["anim"] == "ui-list-pane-activity-spin", working
    assert working["bg"] == "rgba(0, 0, 0, 0)" and working["bt"] == "rgba(0, 0, 0, 0)", working
    assert new["anim"] == "none" and new["bg"] != "rgba(0, 0, 0, 0)", new


def test_reduced_motion_stops_the_ring_but_keeps_its_gap(engine_page: Page) -> None:
    _mount(engine_page, reduced=True)
    working = engine_page.evaluate(PROBE_JS)[1]
    assert working["anim"] == "none", working
    assert working["bt"] == "rgba(0, 0, 0, 0)" and working["bg"] == "rgba(0, 0, 0, 0)", working


def test_the_row_link_name_carries_the_state_as_a_separate_run(engine_page: Page) -> None:
    _mount(engine_page)
    names = engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-testid=ac-root] .ui-list-pane-row')).map((r) => r.textContent.replace(/\\s+/g, ' ').trim())"
    )
    assert "Chat b, Working" in names[1], names
    assert "Chat c, New reply" in names[2], names


def test_set_items_patches_the_slot_in_place_for_a_reused_armed_row(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        "() => { const li = document.querySelector('[data-testid=ac-row-a]').closest('li'); li.classList.add('confirm-delete'); window.__li = li; window.__row = li.firstElementChild; }"
    )
    p.evaluate(
        "() => window.__pane.setItems([{id: 'today', label: 'Today', items: [window.__mk('a', 'working'), window.__mk('b'), window.__mk('c', 'new')]}])"
    )
    out = p.evaluate(
        """() => {
          const li = document.querySelector('[data-testid=ac-row-a]').closest('li');
          const slot = li.querySelector('.ui-list-pane-activity');
          return {same: li === window.__li, row: li.firstElementChild === window.__row,
                  armed: li.classList.contains('confirm-delete'), cls: slot.className,
                  hidden: li.querySelector('.visually-hidden').textContent,
                  bCls: document.querySelector('[data-testid=ac-row-b] .ui-list-pane-activity').className};
        }"""
    )
    assert out["same"] and out["row"] and out["armed"], out
    assert out["cls"].endswith("--working") and out["hidden"] == ", Working", out
    assert out["bCls"] == "ui-list-pane-activity", out
    # And back to nothing, still armed.
    p.evaluate(
        "() => window.__pane.setItems([{id: 'today', label: 'Today', items: [window.__mk('a'), window.__mk('b'), window.__mk('c')]}])"
    )
    again = p.evaluate(
        "() => { const li = document.querySelector('[data-testid=ac-row-a]').closest('li'); return {armed: li.classList.contains('confirm-delete'), cls: li.querySelector('.ui-list-pane-activity').className}; }"
    )
    assert again == {"armed": True, "cls": "ui-list-pane-activity"}, again


def test_activity_is_ignored_in_the_other_row_styles(engine_page: Page) -> None:
    _mount(engine_page, "{rowStyle: 'library'}")
    engine_page.evaluate(
        "() => window.__pane.setItems([{id: 'g', label: 'G', items: [window.__mk('z', 'working')]}])"
    )
    n = engine_page.evaluate(
        "() => document.querySelectorAll('[data-testid=ac-root] .ui-list-pane-activity').length"
    )
    assert n == 0
    text = engine_page.evaluate("() => document.querySelector('[data-testid=ac-root]').textContent")
    assert "Working" not in text

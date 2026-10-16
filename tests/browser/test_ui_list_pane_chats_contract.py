# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for the ``App.ui.listPane`` additions of
M25 F4 L1 (DD5, DD12, DD14): ``rowStyle: 'chats'``, the header ``block`` slot,
row actions (the tab policy, the arrow keys, the reveal, focus across
``setItems``, the armed-row reuse with ``App.confirmDelete``), ``item.dataset``
and the label's ``data-confirm-title``.

Every Flight 3 ``listPane`` contract stays in ``test_ui_library_contract.py``.
Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``
(armed-row tests use the harness-loaded ui/confirm.js; no app spawn). Falls in the
``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import load_harness
from browser.design_tokens import DARK, LIGHT
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

# A chats pane between two outside buttons: items a..e are button rows (onSelect)
# with a time, an agent-name meta and a delete action; "p" is a pending row
# with no action. Every action click is recorded with the item it received.
MOUNT_JS = """(opts) => {
  window.__clicks = [];
  window.__selects = [];
  const mk = (ids, extra) => ids.map((id) => Object.assign({
    id, label: 'Chat ' + id, time: '10:4' + id.charCodeAt(0) % 10, meta: 'agent-' + id,
    testid: 'cr-row-' + id, dataset: {id},
    onSelect: (item) => window.__selects.push(item.id),
    action: {label: 'Delete chat: Chat ' + id, icon: 'trash', testid: 'cr-del-' + id,
             onClick: (item, el, li) => window.__clicks.push({id: item.id, tag: item.tag || null,
                                                               isAction: el.classList.contains('ui-list-pane-action'),
                                                               liOk: li.contains(el)})},
  }, (extra && extra[id]) || {}));
  window.__mk = mk;
  const root = document.getElementById('harness-root');
  const before = document.createElement('button');
  before.textContent = 'Before'; before.setAttribute('data-testid', 'cr-before');
  const after = document.createElement('button');
  after.textContent = 'After'; after.setAttribute('data-testid', 'cr-after');
  const block = document.createElement('button');
  block.textContent = 'New chat'; block.setAttribute('data-testid', 'cr-new');
  const col = document.createElement('div');
  col.style.cssText = 'width: 300px; height: 420px; display: flex; flex-direction: column; background: var(--sidebar-bg);';
  const c = App.ui.listPane(Object.assign({
    title: 'Chats', testid: 'cr-root', rowStyle: 'chats', block,
    groups: [{id: 'today', label: 'Today', items: mk(['a', 'b', 'c'])},
             {id: 'older', label: 'Older', items: mk(['d', 'e'])}],
  }, opts || {}));
  col.appendChild(c.el);
  root.append(before, col, after);
  window.__pane = c;
  return true;
}"""


def _mount(page: Page, opts: str = "{}", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT_JS})({opts})")


def _focused(page: Page) -> str | None:
    return page.evaluate("() => document.activeElement && document.activeElement.dataset.testid")


def _tabbable(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-testid=cr-root] .ui-list-pane-body [tabindex=\"0\"]'))"
        ".map((n) => n.dataset.testid)"
    )


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


# ── AC13: the chats row ─────────────────────────────────────────────────────


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_chats_row_anatomy(engine_page: Page, theme: str) -> None:
    _mount(
        engine_page,
        "{selectedId: 'b', groups: [{label: 'Today', items: window.__mk ? [] : []}]}",
        theme,
    )
    p = engine_page
    palette = DARK if theme == "dark" else LIGHT
    p.evaluate(
        "() => { window.__pane.setItems([{label: 'Today', items: window.__mk(['a', 'b'], {a: {badges: [{text: 'discord', kind: 'connectors'}]}})}]);"
        " window.__pane.setSelected('b'); }"
    )
    out = p.evaluate(
        """() => {
          const rows = document.querySelectorAll('[data-testid=cr-root] .ui-list-pane-row');
          const probe = (row) => {
            const lines = Array.from(row.children);
            const s = getComputedStyle(row);
            const label = row.querySelector('.ui-list-pane-label'), time = row.querySelector('.ui-list-pane-time');
            const meta = row.querySelector('.ui-list-pane-meta');
            const ls = getComputedStyle(label), ts = getComputedStyle(time), ms = getComputedStyle(meta);
            const rb = row.getBoundingClientRect(), tb = time.getBoundingClientRect();
            const l1 = lines[0].getBoundingClientRect(), l2 = lines[1].getBoundingClientRect();
            return {
              lines: lines.map((l) => Array.from(l.children).map((n) => n.className)),
              pad: s.padding, dir: s.flexDirection, rowGap: s.rowGap,
              label: [ls.fontSize, ls.color, ls.textOverflow, ls.whiteSpace],
              time: [ts.fontSize, ts.color, ts.flexShrink],
              timeAtEnd: Math.abs((rb.right - 11) - tb.right) <= 1,
              meta: [ms.fontSize, ms.color],
              line2Below: l2.top >= l1.bottom - 0.5,
              current: row.getAttribute('aria-current'),
            };
          };
          return {rest: probe(rows[0]), selected: probe(rows[1])};
        }"""
    )
    rest, sel = out["rest"], out["selected"]
    assert rest["lines"] == [
        ["ui-list-pane-label", "ui-list-pane-time"],
        ["ui-list-pane-meta", "ui-list-pane-badges"],
    ]
    assert sel["lines"] == [["ui-list-pane-label", "ui-list-pane-time"], ["ui-list-pane-meta"]]
    assert rest["pad"] == "8px 10px" and rest["dir"] == "column" and rest["rowGap"] == "2px", rest
    assert rest["label"] == ["13px", _rgb(palette["fg"]), "ellipsis", "nowrap"], rest
    assert rest["time"] == ["11px", _rgb(palette["fg_muted"]), "0"], rest
    assert rest["timeAtEnd"] is True and rest["line2Below"] is True, rest
    assert rest["meta"] == ["11px", _rgb(palette["fg_secondary"])], rest
    # The selected row: aria-current="true" (a button row), and its time takes
    # --fg-secondary (--fg-muted fails body AA on the selected wash, A24).
    assert sel["current"] == "true"
    assert sel["time"][1] == _rgb(palette["fg_secondary"]), sel
    assert sel["meta"][1] == _rgb(palette["fg_secondary"]), sel


def test_a_long_title_ellipsizes_and_keeps_the_time(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        "() => window.__pane.setItems(window.__mk(['a'], {a: {label: 'A very long chat title that cannot possibly fit in the three hundred pixel column'}}))"
    )
    out = p.evaluate(
        """() => { const row = document.querySelector('[data-testid=cr-row-a]');
          const label = row.querySelector('.ui-list-pane-label'), time = row.querySelector('.ui-list-pane-time');
          return {clipped: label.scrollWidth > label.clientWidth, timeW: time.getBoundingClientRect().width,
                  inside: time.getBoundingClientRect().right <= row.getBoundingClientRect().right}; }"""
    )
    assert out["clipped"] is True and out["timeW"] > 10 and out["inside"] is True, out


def test_the_chats_style_is_known_and_draws_no_icon_lead_or_count(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        """() => { const lead = document.createElement('span'); lead.className = 'probe-lead';
          window.__pane.setItems(window.__mk(['a'], {a: {icon: 'plus', lead, count: 3}})); }"""
    )
    out = p.evaluate(
        """() => { const row = document.querySelector('[data-testid=cr-row-a]');
          return [row.querySelectorAll('.ui-list-pane-icon, .ui-list-pane-lead, .ui-list-pane-count, .probe-lead').length,
                  document.querySelector('[data-testid=cr-root]').classList.contains('ui-list-pane-style-chats')]; }"""
    )
    assert out == [0, True]


# ── AC14: the block slot ────────────────────────────────────────────────────


def test_block_sits_after_the_header_outside_it(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => { const root = document.querySelector('[data-testid=cr-root]');
          const header = root.querySelector('header');
          const block = root.querySelector('.ui-list-pane-block');
          const bs = getComputedStyle(block);
          return {order: Array.from(root.children).slice(0, 2).map((n) => n.tagName + '.' + n.className),
                  headerChildren: Array.from(header.children).map((n) => n.className),
                  holds: block.firstElementChild.dataset.testid, pad: bs.padding, dir: bs.flexDirection}; }"""
    )
    assert out["order"] == ["HEADER.ui-list-pane-header", "DIV.ui-list-pane-block"]
    assert out["headerChildren"] == ["ui-list-pane-title"]  # unchanged: title only
    assert out["holds"] == "cr-new"
    assert out["pad"] == "0px 16px 12px" and out["dir"] == "column"
    msg = engine_page.evaluate(
        "() => { try { App.ui.listPane({title: 'T', block: 'text'}); return ''; } catch (e) { return e.message; } }"
    )
    assert msg == "App.ui.listPane: block must be a node"


# ── AC15/AC16: row actions and row data ─────────────────────────────────────


def test_action_markup_name_and_no_row_class(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => { const li = document.querySelector('[data-testid=cr-row-a]').parentNode;
          const act = li.querySelector('[data-testid=cr-del-a]');
          return {children: Array.from(li.children).map((n) => n.tagName + ':' + n.className),
                  type: act.getAttribute('type'), name: act.getAttribute('aria-label'),
                  text: act.textContent, svgHidden: act.querySelector('svg').getAttribute('aria-hidden'),
                  isRow: act.classList.contains('ui-list-pane-row')}; }"""
    )
    assert out["children"] == ["BUTTON:ui-list-pane-row", "BUTTON:ui-list-pane-action"]
    assert (out["type"], out["name"], out["text"], out["svgHidden"]) == (
        "button",
        "Delete chat: Chat a",
        "",
        "true",
    )
    assert out["isRow"] is False
    assert_controls_labelled_and_described(p, "[data-testid=cr-root]")


def test_an_item_without_an_action_has_no_button(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        "() => window.__pane.setItems(window.__mk(['p', 'a'], {p: {action: null, label: 'New chat', time: 'now', dataset: {id: 'p', pending: 'true'}}}))"
    )
    out = p.evaluate(
        """() => { const row = document.querySelector('[data-testid=cr-row-p]');
          return [row.parentNode.querySelectorAll('.ui-list-pane-action').length, row.dataset.pending, row.dataset.id]; }"""
    )
    assert out == [0, "true", "p"]


def test_dataset_and_data_confirm_title(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => { const row = document.querySelector('[data-testid=cr-row-b]');
          const label = row.querySelector('.ui-list-pane-label');
          const li = row.parentNode;
          const before = [row.dataset.id, label.hasAttribute('data-confirm-title'), label.textContent];
          App.confirmDelete(li, () => {});
          return {before, armedText: label.textContent, armed: li.classList.contains('confirm-delete')}; }"""
    )
    assert out == {"before": ["b", True, "Chat b"], "armedText": "Confirm delete?", "armed": True}
    msg = p.evaluate(
        "() => { try { window.__pane.setItems([{id: 'x', label: 'X', onSelect: () => {}, dataset: ['no']}]); return ''; } catch (e) { return e.message; } }"
    )
    assert msg == "listPane item x: dataset must be a plain object"
    msg = p.evaluate(
        "() => { try { window.__pane.setItems([{id: 'x', label: 'X', onSelect: () => {}, action: {label: 'L'}}]); return ''; } catch (e) { return e.message; } }"
    )
    assert msg == "listPane item x: action needs label, icon and onClick"


def test_dataset_on_other_row_styles_and_label_attribute(engine_page: Page) -> None:
    """dataset and data-confirm-title are not chats-only."""
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => { const c = App.ui.listPane({title: 'T', rowStyle: 'library',
            items: [{id: 'k', label: 'K', href: '#k', dataset: {kind: 'kb'}}]});
          document.getElementById('harness-root').appendChild(c.el);
          const row = c.el.querySelector('.ui-list-pane-row');
          return [row.dataset.kind, row.querySelector('.ui-list-pane-label').hasAttribute('data-confirm-title'),
                  c.el.querySelectorAll('.ui-list-pane-action').length]; }"""
    )
    assert out == ["kb", True, 0]


def test_action_is_hidden_at_rest_and_revealed_on_hover_and_focus_within(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    disp = "(id) => getComputedStyle(document.querySelector(`[data-testid=cr-del-${id}]`)).display"
    p.mouse.move(1000, 700)
    assert [p.evaluate(disp, i) for i in "abc"] == ["none"] * 3
    p.get_by_test_id("cr-row-b").hover()
    # Shown (an absolutely positioned inline-flex computes as flex).
    assert [p.evaluate(disp, i) for i in "abc"] == ["none", "flex", "none"]
    # The hovered row's time fades out under the action (opacity, never removed).
    assert (
        p.evaluate(
            "() => getComputedStyle(document.querySelector('[data-testid=cr-row-b] .ui-list-pane-time')).opacity"
        )
        == "0"
    )
    # Pointer on the action itself: the row keeps its hover wash.
    p.get_by_test_id("cr-del-b").hover()
    wash = p.evaluate(
        "() => getComputedStyle(document.querySelector('[data-testid=cr-row-b]')).backgroundColor"
    )
    assert wash != "rgba(0, 0, 0, 0)"
    p.mouse.move(1000, 700)
    p.get_by_test_id("cr-row-c").focus()
    assert [p.evaluate(disp, i) for i in "abc"] == ["none", "none", "flex"]


def test_tab_goes_stop_row_then_its_action_then_out(engine_page: Page) -> None:
    _mount(engine_page, "{selectedId: 'b'}")
    p = engine_page
    assert _tabbable(p) == ["cr-row-b", "cr-del-b"]  # only the stop row's action is tabbable
    p.get_by_test_id("cr-before").focus()
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-new"  # the block's button
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-row-b"  # enters at the stop (the selected row)
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-del-b"
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-after"  # then out of the list
    # Backward, the action is display:none until its li has focus, so Shift+Tab
    # from after the list lands on the stop row (as the legacy list did).
    p.keyboard.press("Shift+Tab")
    assert _focused(p) == "cr-row-b"
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-del-b"
    p.keyboard.press("Shift+Tab")
    assert _focused(p) == "cr-row-b"
    p.keyboard.press("Shift+Tab")
    assert _focused(p) == "cr-new"


def test_roving_rederives_the_action_tab_stop(engine_page: Page) -> None:
    """rovingFocus rewrites only the rows; the body focusin re-derives the
    actions, so Tab from a roved-to row reaches ITS action."""
    _mount(engine_page, "{selectedId: 'a'}")
    p = engine_page
    p.get_by_test_id("cr-row-a").focus()
    p.keyboard.press("ArrowDown")
    p.keyboard.press("ArrowDown")
    assert _focused(p) == "cr-row-c"
    assert _tabbable(p) == ["cr-row-c", "cr-del-c"]
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-del-c"
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-after"


def test_arrow_keys_on_an_action_move_to_the_neighbouring_rows(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("cr-row-c").focus()
    p.keyboard.press("Tab")
    assert _focused(p) == "cr-del-c"
    p.keyboard.press("ArrowDown")
    assert _focused(p) == "cr-row-d"  # across the group boundary
    assert _tabbable(p) == ["cr-row-d", "cr-del-d"]
    p.keyboard.press("Tab")
    p.keyboard.press("ArrowUp")
    assert _focused(p) == "cr-row-c"
    p.keyboard.press("Tab")
    p.keyboard.press("End")
    assert _focused(p) == "cr-row-e"
    p.keyboard.press("Tab")
    p.keyboard.press("ArrowDown")
    assert _focused(p) == "cr-row-e"  # clamped at the end
    p.keyboard.press("Tab")
    p.keyboard.press("Home")
    assert _focused(p) == "cr-row-a"
    p.keyboard.press("Tab")
    p.keyboard.press("ArrowUp")
    assert _focused(p) == "cr-row-a"  # clamped at the start


def test_a_hidden_rows_action_is_out_of_reach(engine_page: Page) -> None:
    """A filtered-out row hides its li, and so its action; the stop derivation
    ignores hidden rows."""
    _mount(engine_page, "{filter: {label: 'Filter chats', testid: 'cr-filter'}, selectedId: 'b'}")
    p = engine_page
    p.get_by_test_id("cr-filter").fill("chat c")
    out = p.evaluate(
        """() => [getComputedStyle(document.querySelector('[data-testid=cr-del-b]')).display,
                  document.querySelector('[data-testid=cr-row-b]').parentNode.hidden]"""
    )
    assert out == ["none", True]
    assert _tabbable(p) == ["cr-row-c", "cr-del-c"]


def test_action_click_receives_the_item_the_action_and_the_li(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("cr-row-a").hover()
    p.get_by_test_id("cr-del-a").click()
    assert p.evaluate("() => window.__clicks") == [
        {"id": "a", "tag": None, "isAction": True, "liOk": True}
    ]
    assert p.evaluate("() => window.__selects") == []  # the row's onSelect did not fire


# ── Focus across setItems ───────────────────────────────────────────────────


def test_a_focused_action_restores_to_the_same_items_action(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("cr-row-b").focus()
    p.keyboard.press("Tab")
    p.evaluate("() => { window.__old = document.activeElement; }")
    p.evaluate("() => window.__pane.setItems(window.__mk(['x', 'a', 'b', 'c']))")
    assert _focused(p) == "cr-del-b"
    assert p.evaluate("() => document.activeElement !== window.__old")  # really rebuilt
    assert _tabbable(p) == ["cr-row-b", "cr-del-b"]


@pytest.mark.parametrize(
    ("focus", "next_ids", "expected"),
    [
        ("b", "['a', 'c', 'd']", "cr-row-c"),  # the next row in the old order
        ("e", "['a', 'b', 'c', 'd']", "cr-row-d"),  # the last row: the previous one
        ("b", "['d', 'a']", "cr-row-d"),  # the next OLD item still present, wherever it moved
    ],
)
def test_a_focused_action_whose_item_is_gone_goes_to_the_neighbouring_row(
    engine_page: Page, focus: str, next_ids: str, expected: str
) -> None:
    _mount(engine_page, "{selectedId: 'a'}")
    p = engine_page
    p.get_by_test_id(f"cr-row-{focus}").focus()
    p.keyboard.press("Tab")
    assert _focused(p) == f"cr-del-{focus}"
    p.evaluate(f"() => window.__pane.setItems(window.__mk({next_ids}))")
    assert _focused(p) == expected
    stop = expected.replace("cr-row-", "")
    assert _tabbable(p) == [expected, f"cr-del-{stop}"]


def test_a_focused_row_whose_item_is_gone_keeps_the_selected_then_first_rule(
    engine_page: Page,
) -> None:
    """Flight 3's rule for a focused ROW is unchanged: the neighbour rule
    applies only when focus was on an action (the delete case)."""
    _mount(engine_page, "{selectedId: 'e'}")
    p = engine_page
    p.get_by_test_id("cr-row-b").focus()
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'c', 'e']))")
    assert _focused(p) == "cr-row-e"  # the selected row, not the neighbour c


# ── Armed rows (App.confirmDelete) ──────────────────────────────────────────


def test_an_armed_li_survives_set_items_with_the_new_item(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("cr-row-b").hover()
    p.get_by_test_id("cr-del-b").click()  # the first click only records
    p.evaluate(
        """() => { const li = document.querySelector('[data-testid=cr-row-b]').parentNode;
          window.__armedLi = li; window.__armedRow = li.firstElementChild; window.__armedAct = li.lastElementChild;
          App.confirmDelete(li, () => {}); }"""
    )
    # A rebuild with NEW item objects (tagged), the armed item's label changed.
    p.evaluate(
        "() => window.__pane.setItems([{label: 'Today', items: window.__mk(['a', 'b', 'c'], {b: {tag: 'v2', label: 'Renamed'}, a: {tag: 'v2'}})}])"
    )
    out = p.evaluate(
        """() => { const li = document.querySelector('[data-testid=cr-row-b]').parentNode;
          return {same: li === window.__armedLi, row: li.firstElementChild === window.__armedRow,
                  act: li.lastElementChild === window.__armedAct, connected: li.isConnected,
                  armed: li.classList.contains('confirm-delete'),
                  title: li.querySelector('[data-confirm-title]').textContent,
                  hasTimer: !!li._confirmRevertTimer,
                  otherRebuilt: document.querySelectorAll('.ui-list-pane-row').length}; }"""
    )
    assert out == {
        "same": True,
        "row": True,
        "act": True,
        "connected": True,
        "armed": True,
        "title": "Confirm delete?",  # the armed title survives (a stale label is fine for <= 3s)
        "hasTimer": True,
        "otherRebuilt": 3,
    }
    # The reused row still goes through the view pass.
    p.evaluate("() => window.__pane.setSelected('b')")
    assert p.get_by_test_id("cr-row-b").get_attribute("aria-current") == "true"
    # The action reads the entry's CURRENT item at click time, never a stale closure.
    p.evaluate("() => { window.__clicks = []; }")
    p.get_by_test_id("cr-del-b").click()
    assert p.evaluate("() => window.__clicks") == [
        {"id": "b", "tag": "v2", "isAction": True, "liOk": True}
    ]
    # The row's onSelect reads the current item too.
    p.get_by_test_id("cr-row-b").click()
    assert p.evaluate("() => window.__selects") == ["b"]


def test_a_focused_armed_action_keeps_focus_across_set_items(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("cr-row-b").focus()
    p.keyboard.press("Tab")
    p.evaluate("() => App.confirmDelete(document.activeElement.parentNode, () => {})")
    p.evaluate("() => { window.__act = document.activeElement; }")
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'b', 'c']))")
    assert p.evaluate("() => document.activeElement === window.__act")  # the same node, refocused


def test_an_armed_li_whose_item_is_gone_is_dropped_and_its_timer_is_harmless(
    engine_page: Page,
) -> None:
    _mount(engine_page)
    p = engine_page
    errors: list[str] = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    p.evaluate(
        """() => { const li = document.querySelector('[data-testid=cr-row-b]').parentNode;
          window.__armedLi = li; App.confirmDelete(li, () => {}, {revertMs: 120}); }"""
    )
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'c']))")
    assert p.evaluate("() => window.__armedLi.isConnected") is False
    p.wait_for_timeout(300)  # the lapse timer fires on the detached node
    out = p.evaluate(
        """() => ({armed: window.__armedLi.classList.contains('confirm-delete'),
                   lapsed: window.__armedLi.classList.contains('confirm-lapsed'),
                   title: window.__armedLi.querySelector('[data-confirm-title]').textContent})"""
    )
    assert out == {"armed": False, "lapsed": True, "title": "Chat b"}
    assert errors == []


def test_after_it_disarms_the_next_set_items_rebuilds_the_li(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        """() => { const li = document.querySelector('[data-testid=cr-row-b]').parentNode;
          window.__armedLi = li; App.confirmDelete(li, () => {}, {revertMs: 100}); }"""
    )
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'b', 'c']))")
    assert p.evaluate(
        "() => document.querySelector('[data-testid=cr-row-b]').parentNode === window.__armedLi"
    )
    p.wait_for_timeout(250)  # it lapses
    p.evaluate(
        "() => window.__pane.setItems(window.__mk(['a', 'b', 'c'], {b: {label: 'Renamed'}}))"
    )
    out = p.evaluate(
        """() => { const li = document.querySelector('[data-testid=cr-row-b]').parentNode;
          return [li === window.__armedLi, li.querySelector('[data-confirm-title]').textContent]; }"""
    )
    assert out == [False, "Renamed"]


def test_the_armed_row_shows_the_danger_cue_and_its_action(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.mouse.move(1000, 700)
    p.evaluate(
        "() => App.confirmDelete(document.querySelector('[data-testid=cr-row-c]').parentNode, () => {})"
    )
    out = p.evaluate(
        """() => { const row = document.querySelector('[data-testid=cr-row-c]');
          const act = document.querySelector('[data-testid=cr-del-c]');
          return {border: getComputedStyle(row).borderTopColor,
                  title: getComputedStyle(row.querySelector('[data-confirm-title]')).color,
                  act: [getComputedStyle(act).display, getComputedStyle(act).color]}; }"""
    )
    danger = _rgb(DARK["status_danger"])
    assert out == {"border": danger, "title": danger, "act": ["flex", danger]}


def test_list_pane_with_actions_installs_no_document_listener(engine_page: Page) -> None:
    load_harness(engine_page)
    p = engine_page
    p.evaluate(
        """() => {
          window.__docListeners = 0;
          const add = EventTarget.prototype.addEventListener;
          EventTarget.prototype.addEventListener = function (t, l, o) {
            if (this === document || this === window || this === document.body) window.__docListeners += 1;
            return add.call(this, t, l, o);
          };
        }"""
    )
    p.evaluate(f"({MOUNT_JS})({{}})")
    p.get_by_test_id("cr-row-a").focus()
    p.keyboard.press("Tab")
    p.keyboard.press("ArrowDown")
    p.evaluate("() => window.__pane.setItems(window.__mk(['a', 'b']))")
    p.evaluate("() => window.__pane.destroy()")
    assert p.evaluate("() => window.__docListeners") == 0

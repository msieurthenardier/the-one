# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.keyValueTable`` (M31 F3 L04, flight DD4/DD8-1/DD10/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane. No fixed sleeps.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

MOUNT = """(extra) => {
  window.__ev = [];
  const o = Object.assign({columns: [{key: 'channel', label: 'Channel', placeholder: 'channel id', inputTestid: 'c-ch'},
      {key: 'agent', label: 'Agent', placeholder: 'agent name', inputTestid: 'c-ag'}],
    rows: [{channel: 'a', agent: 'b'}, {channel: 'c', agent: 'd'}], label: 'Channel map', testid: 'kv',
    addTestid: 'kv-add', rowTestid: 'kv-row', removeTestid: 'kv-rm',
    onChange: (v, info) => window.__ev.push(info.type + ':' + JSON.stringify(v))}, extra || {});
  window.__kv = App.ui.keyValueTable(o);
  document.getElementById('harness-root').appendChild(window.__kv.el);
  return true;
}"""


def _mount(page: Page, extra: str = "null", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT})({extra})")


def _vals(page: Page) -> list:
    return page.evaluate("() => window.__kv.values()")


def test_validation_and_extra_keys(engine_page: Page) -> None:
    load_harness(engine_page)
    msgs = engine_page.evaluate(
        """() => {
          const t = (o) => { try { App.ui.keyValueTable(o); return null; } catch (e) { return e.message; } };
          const c = {key: 'a', label: 'A'};
          return [t({}), t({columns: []}), t({columns: [{label: 'x'}]}), t({columns: [c, c]}),
            t({columns: [{key: 'a', label: 'A', type: 'sensitive'}]}), t({columns: [c]}), t({columns: [{key: 'a', label: 'A', type: 'text'}]})];
        }"""
    )
    assert all(m for m in msgs[:5]), msgs
    assert "duplicate" in msgs[3] and "unknown column type" in msgs[4]
    assert msgs[5:] == [None, None]
    _mount(engine_page, "{rows: [{channel: 'a', agent: 'b', _x: 1}]}")
    assert _vals(engine_page) == [{"channel": "a", "agent": "b", "_x": 1}]
    engine_page.evaluate("() => window.__kv.setValues([{channel: 'z', _y: {k: 1}}])")
    assert _vals(engine_page) == [{"channel": "z", "agent": "", "_y": {"k": 1}}]
    # values() returns fresh objects.
    engine_page.evaluate("() => { window.__kv.values()[0].channel = 'mutated'; }")
    assert _vals(engine_page)[0]["channel"] == "z"


def test_node_label_and_names_and_roles(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{columns: [{key: 'k', label: (() => { const s = document.createElement('span'); s.innerHTML = 'Key <b>x</b>'; return s; })(), inputTestid: 'k1'}], rows: [{k: '1'}, {k: '2'}]}",
    )
    out = engine_page.evaluate(
        """() => {
          const el = window.__kv.el;
          const table = el.querySelector('table');
          return {
            table: [table.getAttribute('aria-label'), table.getAttribute('data-testid'), table.querySelector('caption')],
            heads: Array.from(table.querySelectorAll('thead th')).map((t) => [t.getAttribute('scope'), t.textContent.trim()]),
            inputs: Array.from(table.querySelectorAll('tbody input')).map((i) => i.getAttribute('aria-label')),
            removes: Array.from(table.querySelectorAll('tbody button')).map((b) => [b.type, b.getAttribute('aria-label'), b.getAttribute('data-testid')]),
            idx: Array.from(table.querySelectorAll('tbody tr')).map((r) => [r.dataset.rowIdx, r.getAttribute('data-testid')]),
            add: [el.lastElementChild.tagName, el.lastElementChild.textContent, el.lastElementChild.getAttribute('data-testid')],
            headHidden: table.tHead.hidden
          };
        }"""
    )
    assert out["table"] == ["Channel map", "kv", None]
    assert out["heads"] == [["col", "Key x"], ["col", "Actions"]]
    assert out["inputs"] == ["Key x, row 1", "Key x, row 2"]
    assert out["removes"] == [
        ["button", "Remove row 1", "kv-rm"],
        ["button", "Remove row 2", "kv-rm"],
    ]
    assert out["idx"] == [["0", "kv-row"], ["1", "kv-row"]]
    assert out["add"] == ["BUTTON", "+ Add row", "kv-add"]
    assert out["headHidden"] is False
    # Roles through the accessibility tree.
    assert engine_page.get_by_role("columnheader", name="Key x").count() == 1
    assert engine_page.get_by_role("button", name="Remove row 2").count() == 1
    assert engine_page.get_by_role("textbox", name="Key x, row 1").count() == 1
    assert engine_page.get_by_role("table", name="Channel map").count() == 1


def test_custom_remove_label_row_dataset_and_empty_head(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{rows: [], removeLabel: (n, row) => 'Drop ' + n + ' ' + row.channel, rowDataset: (row) => ({chan: row.channel}), emptyHidesHead: true}",
    )
    assert engine_page.evaluate("() => window.__kv.el.querySelector('thead').hidden") is True
    engine_page.get_by_test_id("kv-add").click()
    assert engine_page.evaluate("() => window.__kv.el.querySelector('thead').hidden") is False
    engine_page.evaluate("() => window.__kv.setValues([{channel: 'q', agent: 'w'}])")
    out = engine_page.evaluate(
        "() => { const tr = window.__kv.el.querySelector('tbody tr'); return [tr.dataset.chan, tr.querySelector('button').getAttribute('aria-label')]; }"
    )
    assert out == ["q", "Drop 1 q"]
    _mount(engine_page, "{rows: [], emptyHidesHead: false}")
    assert engine_page.evaluate("() => window.__kv.el.querySelector('thead').hidden") is False


def test_keyed_model_survives_add_and_remove(engine_page: Page) -> None:
    _mount(engine_page, "{rows: [{channel: '', agent: ''}, {channel: '', agent: ''}]}")
    p = engine_page
    inputs = p.get_by_test_id("c-ch")
    inputs.nth(0).fill("one")
    inputs.nth(1).fill("two")
    p.get_by_test_id("kv-add").click()
    vals = _vals(p)
    assert [v["channel"] for v in vals] == ["one", "two", ""]
    # The surviving row keeps its DOM node across a remove.
    p.evaluate("() => { window.__n2 = window.__kv.el.querySelectorAll('tbody tr')[1]; }")
    p.get_by_test_id("kv-rm").nth(0).click()
    assert [v["channel"] for v in _vals(p)] == ["two", ""]
    out = p.evaluate(
        """() => { const trs = window.__kv.el.querySelectorAll('tbody tr');
          return {same: trs[0] === window.__n2, idx: Array.from(trs).map((t) => t.dataset.rowIdx),
            value: trs[0].querySelector('input').value, name: trs[0].querySelector('input').getAttribute('aria-label'),
            rm: trs[0].querySelector('button').getAttribute('aria-label')}; }"""
    )
    assert out == {
        "same": True,
        "idx": ["0", "1"],
        "value": "two",
        "name": "Channel, row 1",
        "rm": "Remove row 1",
    }
    # setValues -> values round-trips, empty rows included.
    rows = [{"channel": "x", "agent": "y"}, {"channel": "", "agent": ""}]
    p.evaluate("(r) => window.__kv.setValues(r)", rows)
    assert _vals(p) == rows
    ev = p.evaluate("() => window.__ev")
    assert any(e.startswith("input:") for e in ev) and any(e.startswith("add:") for e in ev)
    assert any(e.startswith("remove:") for e in ev)


def test_onchange_types_and_payload(engine_page: Page) -> None:
    _mount(engine_page, "{rows: [{channel: 'a', agent: 'b'}]}")
    p = engine_page
    p.get_by_test_id("c-ch").fill("a2")
    p.get_by_test_id("kv-add").click()
    p.get_by_test_id("kv-rm").nth(1).click()
    ev = p.evaluate("() => window.__ev")
    assert [e.split(":")[0] for e in ev] == ["input", "add", "remove"]
    assert ev[0].endswith('[{"channel":"a2","agent":"b"}]')
    assert ev[2].endswith('[{"channel":"a2","agent":"b"}]')


def test_focus_on_add_and_remove(engine_page: Page) -> None:
    _mount(engine_page, "{rows: [{channel: '1'}, {channel: '2'}, {channel: '3'}]}")
    p = engine_page
    focused = "() => document.activeElement && document.activeElement.value"
    p.get_by_test_id("kv-add").click()
    assert p.evaluate("() => document.activeElement.getAttribute('aria-label')") == "Channel, row 4"
    p.get_by_test_id("kv-rm").nth(1).click()  # next row (3) gets focus
    assert p.evaluate(focused) == "3"
    p.get_by_test_id("kv-rm").nth(2).click()  # last row removed (the new empty one): previous row
    assert p.evaluate(focused) == "3"
    p.get_by_test_id("kv-rm").nth(1).click()
    p.get_by_test_id("kv-rm").nth(0).click()
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "kv-add"


def test_svg_click_removes_row(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.locator("[data-testid=kv-rm] svg").nth(0).click()
    assert [v["channel"] for v in _vals(p)] == ["c"]


def test_set_values_moves_focus_inside(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("c-ag").nth(1).focus()
    p.evaluate("() => window.__kv.setValues([{channel: 'n'}])")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "c-ch"
    p.evaluate("() => window.__kv.setValues([])")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "kv-add"


def test_set_error_follows_the_row_and_clears(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__kv.setError(1, 'agent', 'Required')")

    def state() -> dict:
        return p.evaluate(
            """() => Array.from(window.__kv.el.querySelectorAll('tbody tr')).map((tr) => { const i = tr.querySelectorAll('input')[1];
              const d = i.getAttribute('aria-describedby'); const e = d && document.getElementById(d);
              return [i.getAttribute('aria-invalid'), e ? e.textContent : null, e ? !e.hidden : null]; })"""
        )

    s = state()
    assert s[0][0] is None and s[1] == ["true", "Required", True]
    p.get_by_test_id("kv-rm").nth(0).click()
    assert state() == [["true", "Required", True]]
    p.evaluate("() => window.__kv.setError(0, 'agent', null)")
    assert state() == [[None, None, None]]


def test_set_error_is_announced_and_linked(engine_page: Page) -> None:
    """Squawk 0238: the error line carries role=alert while shown (removed on clear) and
    stays linked to its input through aria-describedby."""
    _mount(engine_page)
    p = engine_page
    shown = p.evaluate(
        """() => { window.__kv.setError(0, 'agent', 'Required');
          const i = window.__kv.el.querySelectorAll('tbody tr')[0].querySelectorAll('input')[1];
          const e = document.getElementById(i.getAttribute('aria-describedby'));
          return [e.getAttribute('role'), e.hidden, e.textContent, e.classList.contains('ui-kv-error')]; }"""
    )
    assert shown == ["alert", False, "Required", True]
    cleared = p.evaluate(
        """() => { const e = window.__kv.el.querySelector('.ui-kv-error[role], .ui-kv-error');
          window.__kv.setError(0, 'agent', null);
          const errs = Array.from(window.__kv.el.querySelectorAll('.ui-kv-error'));
          return errs.map((x) => [x.getAttribute('role'), x.hidden]); }"""
    )
    assert all(role is None and hidden for role, hidden in cleared)


def test_destroy_removes_listeners(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__kv.destroy()")
    p.get_by_test_id("c-ch").nth(0).fill("zzz")
    p.get_by_test_id("kv-add").click()
    p.get_by_test_id("kv-rm").nth(0).click()
    assert p.evaluate("() => window.__ev") == []
    p.evaluate("() => window.__kv.destroy()")  # idempotent


LEGACY = """<table class="mcp-kv-table"><thead class="mcp-kv-thead"><tr><th>Key</th><th aria-label="Actions"></th></tr></thead>
<tbody><tr class="mcp-kv-row"><td><input class="field-input" value="a"></td><td><button type="button" class="kv-remove-row-btn" aria-label="Remove row"></button></td></tr></tbody></table>"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_look_and_size_parity_with_legacy_mcp_table(engine_page: Page, theme: str) -> None:
    _mount(
        engine_page,
        "{columns: [{key: 'k', label: 'Key'}], rows: [{k: 'a'}]}",
        theme,
    )
    out = engine_page.evaluate(
        """() => {
          const lib = window.__kv.el;
          const host = document.createElement('div'); host.className = 'area-studio';
          host.innerHTML = `__LEGACY__`;
          const rm = host.querySelector('.kv-remove-row-btn');
          rm.innerHTML = lib.querySelector('.ui-kv-remove svg').outerHTML;
          lib.parentNode.className = 'area-studio';
          document.getElementById('harness-root').appendChild(host);
          const cs = (el, props) => { const s = getComputedStyle(el); return props.map((p) => s[p]); };
          const TH = ['fontFamily', 'fontSize', 'fontWeight', 'textTransform', 'letterSpacing', 'color', 'borderBottomWidth', 'borderBottomStyle', 'borderBottomColor', 'paddingTop', 'paddingLeft', 'textAlign'];
          const TD = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'verticalAlign'];
          const RM = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'color', 'backgroundColor', 'borderTopWidth', 'width', 'height'];
          const L = {th: host.querySelector('th'), td: host.querySelector('tbody td'), rm, svg: rm.querySelector('svg'), tr: host.querySelector('tbody tr'), table: host.querySelector('table')};
          const N = {th: lib.querySelector('th'), td: lib.querySelector('tbody td'), rm: lib.querySelector('.ui-kv-remove'), svg: lib.querySelector('.ui-kv-remove svg'), tr: lib.querySelector('tbody tr'), table: lib.querySelector('table')};
          const res = {};
          res.th = [cs(L.th, TH), cs(N.th, TH)];
          res.td = [cs(L.td, TD), cs(N.td, TD)];
          res.rm = [cs(L.rm, RM), cs(N.rm, RM)];
          res.svg = [cs(L.svg, ['width', 'height']), cs(N.svg, ['width', 'height'])];
          res.rowH = [L.tr.getBoundingClientRect().height, N.tr.getBoundingClientRect().height];
          res.table = [cs(L.table, ['width', 'marginBottom', 'borderCollapse']), cs(N.table, ['marginBottom', 'borderCollapse'])];
          return res;
        }""".replace("__LEGACY__", LEGACY.replace("\n", ""))
    )
    assert out["th"][0] == out["th"][1]
    assert out["td"][0] == out["td"][1]
    assert out["rm"][0] == out["rm"][1], out["rm"]
    assert out["svg"][0] == out["svg"][1] == ["16px", "16px"]
    assert abs(out["rowH"][0] - out["rowH"][1]) < 0.6, out["rowH"]
    assert out["table"][0][1:] == out["table"][1]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_remove_hover_colour_matches_legacy(engine_page: Page, theme: str) -> None:
    _mount(engine_page, "{columns: [{key: 'k', label: 'Key'}], rows: [{k: 'a'}]}", theme)
    p = engine_page
    p.evaluate(
        """() => { const host = document.createElement('div'); host.className = 'area-studio';
          host.innerHTML = '<button type="button" class="kv-remove-row-btn" id="legacy-rm"></button>';
          window.__kv.el.parentNode.className = 'area-studio';
          document.getElementById('harness-root').appendChild(host); }"""
    )
    sample = """(sel) => { const s = getComputedStyle(document.querySelector(sel)); return [s.color, s.backgroundColor, s.width, s.height]; }"""
    # The hover colour animates; compare the settled values.
    p.add_style_tag(content=".kv-remove-row-btn, .ui-kv-remove { transition: none !important; }")
    p.locator("#legacy-rm").hover()
    legacy = p.evaluate(sample, "#legacy-rm")
    p.locator(".ui-kv-remove").hover()
    lib = p.evaluate(sample, ".ui-kv-remove")
    assert lib[:2] == legacy[:2]
    assert lib[2] != "32px" and lib[3] != "32px"


def test_stays_within_a_narrow_host(engine_page: Page) -> None:
    _mount(
        engine_page, "{rows: [{channel: 'a very long channel identifier '.repeat(6), agent: 'b'}]}"
    )
    p = engine_page
    p.set_viewport_size({"width": 1024, "height": 700})
    p.evaluate(
        "() => { const r = document.getElementById('harness-root'); r.style.width = '700px'; r.style.overflowX = 'auto'; }"
    )
    out = p.evaluate(
        "() => [window.__kv.el.querySelector('table').getBoundingClientRect().width, document.documentElement.scrollWidth]"
    )
    assert out[1] <= 1024

# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.keyValueTable`` (M31 F3 L04, flight DD4/DD8-1/DD10/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane. No fixed sleeps.
"""

from __future__ import annotations

import re

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

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


# The MCP editor's own table rules, frozen here (M31 F5 L07 deleted them from studio.css with
# the editor's last use of the table); the parity tests compare the library table to them.
LEGACY_KV_CSS = """<style>
.area-studio .mcp-kv-table { width: auto; border-collapse: collapse; margin-bottom: 8px; }
.area-studio .legacy-kv-head.is-hidden { display: none; }
.area-studio .legacy-kv-head th {
  text-align: left;
  padding: 4px 8px;
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
  font-weight: var(--font-weight-bold);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--fg-secondary);
  border-bottom: 1px solid var(--border);
}
.area-studio .mcp-kv-th-sensitive {
  white-space: nowrap;
}
.area-studio .mcp-kv-th-sensitive .field-info-icon {
  margin-left: 4px;
  vertical-align: middle;
}
.area-studio .mcp-kv-table tbody td { padding: 4px 8px; vertical-align: middle; }
.area-studio .mcp-kv-sensitive-cell { width: 1%; white-space: nowrap; }

.area-studio .kv-remove-row-btn {
  background: transparent;
  border: 0;
  padding: 4px;
  cursor: pointer;
  color: var(--fg-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
  transition: color var(--motion-fast) ease;
}
.area-studio .kv-remove-row-btn:hover { color: var(--status-danger); }
.area-studio .kv-remove-row-btn svg { width: 16px; height: 16px; display: block; }
</style>"""

LEGACY = """<table class="mcp-kv-table"><thead class="legacy-kv-head"><tr><th>Key</th><th aria-label="Actions"></th></tr></thead>
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
          host.innerHTML = `__CSS____LEGACY__`;
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
        }""".replace("__CSS__", LEGACY_KV_CSS.replace("\n", " ")).replace(
            "__LEGACY__", LEGACY.replace("\n", "")
        )
    )
    assert out["th"][0] == out["th"][1]
    # Padding matches the legacy table; vertical-align is `top` now (HAT, M31 F5: the cells of a
    # row share one top line, the legacy table centred them).
    assert out["td"][0][:4] == out["td"][1][:4]
    assert out["td"][1][4] == "top"
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
          host.innerHTML = `__CSS__<button type="button" class="kv-remove-row-btn" id="legacy-rm"></button>`;
          window.__kv.el.parentNode.className = 'area-studio';
          document.getElementById('harness-root').appendChild(host); }""".replace(
            "__CSS__", LEGACY_KV_CSS.replace("\n", " ")
        )
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


# --------------------------------------------------------------------------------------------
# Secret and toggle columns, setRow, the key-rename rule (M31 F5 L04, flight DD5/DD9/DD10)
# --------------------------------------------------------------------------------------------

MASK = "***abcd"
SEC_COLS = """[{key: 'name', label: 'Name', placeholder: 'NAME', inputTestid: 'k', mono: true},
  {key: 'value', label: 'Value', type: 'secret', maskedBy: 'sensitive', storedKey: '_mask', clearOnUnmask: true, inputTestid: 'v', mono: true},
  {key: 'sensitive', label: 'Sensitive', type: 'toggle', ariaLabel: 'Sensitive', inputTestid: 't'}]"""
SEC_ROWS = f"[{{name: 'API', value: '{MASK}', _mask: '{MASK}', sensitive: true}}, {{name: 'HOST', value: 'example.org', sensitive: false}}]"


def _sec(page: Page, rows: str = SEC_ROWS, extra: str = "") -> None:
    _mount(
        page,
        "{columns: %s, rows: %s, removeLabel: (n, row) => 'Remove ' + (row.name || 'row ' + n)%s}"
        % (SEC_COLS, rows, extra),
    )


def _val(page: Page, i: int = 0) -> str:
    return page.get_by_test_id("v").nth(i).input_value()


def _tick(page: Page, i: int) -> None:
    # The native switch input is visually hidden; the label (track) is the click target.
    page.get_by_test_id("t").nth(i).locator("xpath=ancestor::label").click()


def _events(page: Page) -> list:
    return page.evaluate("() => window.__ev")


def test_secret_and_toggle_cells_dom_and_names(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    out = p.evaluate(
        """() => {
          const t = window.__kv.el.querySelector('table');
          const rows = Array.from(t.querySelectorAll('tbody tr'));
          const info = (tr) => { const v = tr.querySelector('[data-testid=v]'); const eye = tr.querySelector('.api-key-eye');
            const sw = tr.querySelector('[data-testid=t]');
            return {type: v.type, auto: v.getAttribute('autocomplete'), name: v.getAttribute('aria-label'), cls: v.className,
              eye: eye ? [eye.getAttribute('aria-label'), eye.getAttribute('aria-pressed'), eye.hidden] : null,
              sw: [sw.getAttribute('role'), sw.getAttribute('aria-label'), sw.checked],
              tds: Array.from(tr.children).map((td) => td.className),
              rm: tr.querySelector('.ui-kv-remove').getAttribute('aria-label')}; };
          return {table: t.className, cols: t.querySelectorAll('colgroup > col').length, a: info(rows[0]), b: info(rows[1])};
        }"""
    )
    assert out["table"] == "ui-kv-table ui-kv-table--fixed" and out["cols"] == 4
    a, b = out["a"], out["b"]
    assert (a["type"], a["auto"], a["name"]) == ("password", "new-password", "Value, row 1")
    assert "ui-kv-input" in a["cls"] and "ui-kv-input--mono" in a["cls"]
    assert a["eye"] == ["Show value, row 1", "false", True]  # stored mode hides the eye
    assert a["sw"] == ["switch", "Sensitive, row 1", True]
    assert a["tds"] == [
        "ui-kv-cell",
        "ui-kv-cell ui-kv-secret",
        "ui-kv-cell ui-kv-toggle",
        "ui-kv-cell",
    ]
    assert a["rm"] == "Remove API"
    assert (b["type"], b["name"], b["eye"]) == ("text", "Value, row 2", None)
    assert "ui-kv-input" in b["cls"] and "ui-kv-input--mono" in b["cls"]
    assert b["sw"] == ["switch", "Sensitive, row 2", False] and b["rm"] == "Remove HOST"
    expect(p.get_by_role("switch", name="Sensitive, row 2")).to_have_count(1)


def test_column_width_sets_the_col_and_a_toggle_defaults_to_88px(engine_page: Page) -> None:
    """M31 F5 L07: a column's `width` is the <col> width (a toggle column is 88px without it)."""
    p = engine_page
    _sec(p)
    default = p.evaluate(
        "() => Array.from(window.__kv.el.querySelectorAll('colgroup > col')).map((c) => c.style.width)"
    )
    assert default == ["", "", "88px", "48px"]
    _mount(
        p,
        "{columns: [{key: 'k', label: 'Key'}, {key: 'on', label: 'On', type: 'toggle', width: '120px'},"
        " {key: 'v', label: 'Value', width: '30%'}], rows: [{k: 'a', on: true, v: 'x'}]}",
    )
    widths = p.evaluate(
        "() => Array.from(window.__kv.el.querySelectorAll('colgroup > col')).map((c) => c.style.width)"
    )
    assert widths == ["", "120px", "30%", "48px"]


def test_toggle_column_with_node_label_needs_aria_label(engine_page: Page) -> None:
    load_harness(engine_page)
    msgs = engine_page.evaluate(
        """() => {
          const t = (o) => { try { App.ui.keyValueTable(o); return null; } catch (e) { return e.message; } };
          const node = () => { const s = document.createElement('span'); s.textContent = 'Sens (i)'; return s; };
          return [t({columns: [{key: 'a', label: node(), type: 'toggle'}]}), t({columns: [{key: 'a', label: node(), type: 'toggle', ariaLabel: 'Sensitive'}]}),
                  t({columns: [{key: 'a', label: 'A', type: 'toggle'}]})];
        }"""
    )
    assert msgs[0] and "ariaLabel" in msgs[0] and msgs[1:] == [None, None]


def test_names_renumber_together_after_removing_a_middle_row(engine_page: Page) -> None:
    p = engine_page
    rows = "[{name: 'A', value: 'x', sensitive: true}, {name: 'B', value: 'y', sensitive: true}, {name: 'C', value: 'z', sensitive: false}]"
    _sec(p, rows)
    p.get_by_test_id("kv-rm").nth(1).click()
    out = p.evaluate(
        """() => Array.from(window.__kv.el.querySelectorAll('tbody tr')).map((tr) => ({
          idx: tr.dataset.rowIdx, name: tr.querySelector('[data-testid=k]').getAttribute('aria-label'),
          value: tr.querySelector('[data-testid=v]').getAttribute('aria-label'),
          eye: (tr.querySelector('.api-key-eye') || {getAttribute: () => null}).getAttribute('aria-label'),
          sw: tr.querySelector('[data-testid=t]').getAttribute('aria-label'), rm: tr.querySelector('.ui-kv-remove').getAttribute('aria-label')}))"""
    )
    assert out == [
        {"idx": "0", "name": "Name, row 1", "value": "Value, row 1", "eye": "Show value, row 1", "sw": "Sensitive, row 1", "rm": "Remove A"},
        {"idx": "1", "name": "Name, row 2", "value": "Value, row 2", "eye": None, "sw": "Sensitive, row 2", "rm": "Remove C"},
    ]  # fmt: skip


def test_eye_aria_pressed_matches_input_type_and_survives_remove_while_revealed(
    engine_page: Page,
) -> None:
    p = engine_page
    _sec(p, "[{name: 'A', value: 'x', sensitive: true}, {name: 'B', value: 'y', sensitive: true}]")
    eye = p.get_by_role("button", name="Show value, row 1")
    eye.click()
    state = p.evaluate(
        "() => { const tr = window.__kv.el.querySelector('tbody tr'); const e = tr.querySelector('.api-key-eye'); return [e.getAttribute('aria-pressed'), tr.querySelector('[data-testid=v]').type, e.getAttribute('aria-label')]; }"
    )
    assert state == ["true", "text", "Hide value, row 1"]
    p.get_by_test_id("kv-rm").nth(0).click()  # remove while revealed
    state = p.evaluate(
        "() => { const tr = window.__kv.el.querySelector('tbody tr'); const e = tr.querySelector('.api-key-eye'); return [e.getAttribute('aria-pressed'), tr.querySelector('[data-testid=v]').type, e.getAttribute('aria-label'), tr.querySelector('[data-testid=v]').value]; }"
    )
    assert state == ["false", "password", "Show value, row 1", "y"]


def test_toggle_fires_a_toggle_event_and_a_text_blur_does_not(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.get_by_test_id("k").nth(1).fill("HOST2")
    p.get_by_test_id("k").nth(1).blur()
    p.get_by_test_id("v").nth(1).focus()
    p.get_by_test_id("v").nth(1).blur()
    types = p.evaluate("() => window.__ev.map((e) => e.split(':')[0])")
    assert "toggle" not in types and types
    p.evaluate("() => { window.__ev.length = 0; }")
    _tick(p, 1)  # tick row 2 (HOST)
    assert [e.split(":")[0] for e in _events(p)] == ["toggle"]
    assert _vals(p)[1]["sensitive"] is True
    _tick(p, 1)  # a toggle flipped twice
    assert _vals(p)[1]["sensitive"] is False and [e.split(":")[0] for e in _events(p)] == [
        "toggle",
        "toggle",
    ]
    assert p.get_by_test_id("v").nth(1).input_value() == "example.org"


def test_masking_switch_rebuilds_only_that_cell_and_keeps_the_row_wired(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.evaluate(
        "() => { window.__kv.setError(1, 'value', 'Bad'); window.__tr = window.__kv.el.querySelectorAll('tbody tr')[1]; window.__k = window.__tr.querySelector('[data-testid=k]'); }"
    )
    _tick(p, 1)  # now masked
    out = p.evaluate(
        """() => { const tr = window.__kv.el.querySelectorAll('tbody tr')[1]; const v = tr.querySelector('[data-testid=v]'); const err = tr.querySelectorAll('.ui-kv-error')[1];
          return {sameRow: tr === window.__tr, sameKey: tr.querySelector('[data-testid=k]') === window.__k, type: v.type, auto: v.getAttribute('autocomplete'),
                  name: v.getAttribute('aria-label'), eye: tr.querySelector('.api-key-eye').getAttribute('aria-label'), invalid: v.getAttribute('aria-invalid'),
                  cls: v.classList.contains('is-invalid'), described: v.getAttribute('aria-describedby') === err.id, errText: err.textContent, role: err.getAttribute('role'),
                  focusOnToggle: document.activeElement === tr.querySelector('[data-testid=t]')}; }"""
    )
    assert (
        out["sameRow"]
        and out["sameKey"]
        and (out["type"], out["auto"]) == ("password", "new-password")
    )
    assert (out["name"], out["eye"]) == ("Value, row 2", "Show value, row 2")
    assert (
        out["invalid"] == "true"
        and out["cls"]
        and out["described"]
        and out["errText"] == "Bad"
        and out["role"] == "alert"
    )
    p.get_by_test_id("v").nth(1).fill("typed")  # onInput still finds the row through the new input
    assert _vals(p)[1]["value"] == "typed"
    p.evaluate("() => { window.__ev.length = 0; }")
    p.get_by_test_id("v").nth(1).focus()
    p.get_by_test_id("t").nth(1).focus()
    p.keyboard.press("Space")  # untick with the keyboard: toggle keeps focus
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "t"
    assert p.get_by_test_id("v").nth(1).get_attribute("type") == "text"


def test_value_input_keeps_focus_through_a_masking_switch_patch(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.get_by_test_id("v").nth(1).focus()
    p.evaluate("() => window.__kv.setRow(1, {sensitive: true})")
    assert (
        p.evaluate(
            "() => document.activeElement === document.querySelectorAll('[data-testid=v]')[1]"
        )
        is True
    )
    assert p.get_by_test_id("v").nth(1).get_attribute("type") == "password"


def test_clear_on_unmask_clears_value_and_stored_mask_and_fires_once(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    _tick(p, 0)
    assert [e.split(":")[0] for e in _events(p)] == ["toggle"]
    row = _vals(p)[0]
    assert (row["value"], row["_mask"], row["sensitive"]) == ("", "", False)
    assert p.get_by_test_id("v").nth(0).input_value() == ""
    _tick(p, 0)  # re-ticking does not bring stored mode back
    out = p.evaluate(
        "() => { const tr = window.__kv.el.querySelector('tbody tr'); const e = tr.querySelector('.api-key-eye'); return [e.hidden, tr.querySelector('.ui-secret-hint')]; }"
    )
    assert out == [False, None]
    # A value edited away from the mask is kept on unmask (and so is its stored mask).
    _sec(p)
    p.get_by_test_id("v").nth(0).fill("brand-new")
    _tick(p, 0)
    row = _vals(p)[0]
    assert (row["value"], row["_mask"]) == ("brand-new", MASK)
    assert p.get_by_test_id("v").nth(0).input_value() == "brand-new"


@pytest.mark.parametrize("focus", ["tab", "click"])
@pytest.mark.parametrize("caret", ["start", "middle", "end"])
@pytest.mark.parametrize("action", ["type", "backspace", "insert"])
def test_stored_mode_every_edit_replaces_the_mask(
    engine_page: Page, focus: str, caret: str, action: str
) -> None:
    p = engine_page
    _sec(p)
    v = p.get_by_test_id("v").nth(0)
    if focus == "tab":
        p.get_by_test_id("k").nth(0).focus()
        p.keyboard.press("Tab")
    else:
        v.click()
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "v"
    assert v.input_value() == MASK
    # Stored mode: no visible eye, the hint, linked by aria-describedby.
    st = p.evaluate(
        "() => { const v = document.querySelector('[data-testid=v]'); const h = v.closest('td').querySelector('.ui-secret-hint'); const eye = v.closest('td').querySelector('.api-key-eye');\n      return [eye.hidden, (h.textContent === ''), h.textContent, v.getAttribute('aria-describedby').split(' ').includes(h.id)]; }"
    )
    assert st == [True, False, "Stored. Type a new value to replace it.", True]
    if caret == "start":
        p.keyboard.press("Home")
    elif caret == "end":
        p.keyboard.press("End")
    else:
        p.keyboard.press("Home")
        for _ in range(3):
            p.keyboard.press("ArrowRight")
    if action == "type":
        p.keyboard.type("X")
        want = "X"
    elif action == "backspace":
        # At the very start Backspace has nothing to delete (WebKit fires no event), so use Delete.
        p.keyboard.press("Delete" if caret == "start" else "Backspace")
        want = ""
    else:
        p.keyboard.insert_text("pasted")
        want = "pasted"
    assert v.input_value() == want
    assert _vals(p)[0]["value"] == want
    st = p.evaluate(
        "() => { const v = document.querySelector('[data-testid=v]'); const h = v.closest('td').querySelector('.ui-secret-hint'); const eye = v.closest('td').querySelector('.api-key-eye');\n      return [eye.hidden, (h.textContent === ''), (v.getAttribute('aria-describedby') || '').split(' ').includes(h.id)]; }"
    )
    assert st == [False, True, False]


def test_stored_mode_ime_style_input_fallback_strips_the_mask(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.evaluate(
        """(mask) => { const v = document.querySelector('[data-testid=v]'); v.focus(); v.value = mask + 'かな'; v.setSelectionRange(v.value.length, v.value.length);
          v.dispatchEvent(new Event('input', {bubbles: true})); }""",
        MASK,
    )
    assert _val(p) == "かな" and _vals(p)[0]["value"] == "かな"
    # Typing the mask back by hand re-enters stored mode (accepted).
    p.get_by_test_id("v").nth(0).fill(MASK)
    assert (
        p.evaluate(
            "() => document.querySelector('[data-testid=v]').closest('td').querySelector('.api-key-eye').hidden"
        )
        is True
    )


def test_stored_mask_without_a_tail_and_empty_stored_mask(engine_page: Page) -> None:
    p = engine_page
    _sec(
        p,
        "[{name: 'A', value: '***', _mask: '***', sensitive: true}, {name: 'B', value: '', _mask: '', sensitive: true}, {name: 'C', value: '***abcd', sensitive: true}]",
    )
    out = p.evaluate(
        "() => Array.from(document.querySelectorAll('tbody tr')).map((tr) => [tr.querySelector('.api-key-eye').hidden, !!tr.querySelector('.ui-secret-hint')])"
    )
    assert out == [
        [True, True],
        [False, False],
        [False, False],
    ]  # '' and a missing key mean no stored mode
    p.get_by_test_id("v").nth(0).click()
    p.keyboard.type("z")
    assert _val(p, 0) == "z"
    # A hand-typed value equal to a mask on a row that holds none is plain.
    p.get_by_test_id("v").nth(1).fill("***abcd")
    assert (
        p.evaluate(
            "() => document.querySelectorAll('tbody tr')[1].querySelector('.api-key-eye').hidden"
        )
        is False
    )


def test_no_attribute_holds_the_secret(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    typed = "tYp3d-S3cret-value"
    p.get_by_test_id("v").nth(0).click()
    p.keyboard.type(typed)
    p.get_by_test_id("v").nth(0).evaluate(
        "(e) => e.closest('td').querySelector('.api-key-eye').click()"
    )  # reveal too
    leak = p.evaluate(
        """([tail, typed]) => { const bad = [];
          for (const el of window.__kv.el.querySelectorAll('*')) for (const a of el.attributes) {
            if (a.value.includes(tail) || a.value.includes(typed)) bad.push(el.tagName + '@' + a.name); }
          return bad; }""",
        [MASK[3:], typed],
    )
    assert leak == []
    # And the freshly rendered stored mask holds no attribute either.
    _sec(p)
    leak = p.evaluate(
        "(tail) => Array.from(window.__kv.el.querySelectorAll('*')).filter((el) => Array.from(el.attributes).some((a) => a.value.includes(tail))).length",
        MASK[3:],
    )
    assert leak == 0


def test_key_rename_clears_a_still_stored_value_once(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.evaluate("() => { window.__ev.length = 0; }")
    k = p.get_by_test_id("k").nth(0)
    k.click()
    p.keyboard.press("End")
    p.keyboard.type("2")  # API -> API2
    assert len(_events(p)) == 1  # the combined clear fires one onChange
    row = _vals(p)[0]
    assert (row["name"], row["value"], row["_mask"]) == ("API2", "", "")
    assert _val(p) == ""
    hint = p.evaluate(
        "() => { const v = document.querySelector('[data-testid=v]'); const h = v.closest('td').querySelector('.ui-secret-hint'); return [(h.textContent === ''), h.textContent, h.getAttribute('aria-live'), h.getAttribute('role'), v.getAttribute('aria-invalid'), v.getAttribute('aria-describedby').split(' ').includes(h.id), v.closest('td').querySelector('.api-key-eye').hidden]; }"
    )
    assert hint == [
        False,
        "Sensitive values must be re-entered when the key changes.",
        "polite",
        None,
        None,
        True,
        False,
    ]
    # Typing the old key back does not restore; typing in the value clears the hint.
    k.fill("API")
    assert _vals(p)[0]["value"] == "" and _vals(p)[0]["_mask"] == ""
    p.get_by_test_id("v").nth(0).fill("fresh")
    assert p.evaluate("() => document.querySelector('.ui-secret-hint').textContent === ''") is True
    # A hand-typed value equal to the old mask is no longer stored-masked.
    p.get_by_test_id("v").nth(0).fill(MASK)
    assert _vals(p)[0]["_mask"] == ""
    assert (
        p.evaluate(
            "() => document.querySelector('[data-testid=v]').closest('td').querySelector('.api-key-eye').hidden"
        )
        is False
    )


def test_key_rename_edge_cases(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    k = p.get_by_test_id("k").nth(0)
    k.fill("API ")  # a trailing space is not a rename
    assert _vals(p)[0]["value"] == MASK and _vals(p)[0]["_mask"] == MASK
    k.fill("  API")  # nor is a leading one
    assert _vals(p)[0]["_mask"] == MASK
    # A value edited away from the mask keeps its stored mask through a rename.
    p.get_by_test_id("v").nth(0).fill("edited")
    k.fill("OTHER")
    row = _vals(p)[0]
    assert (row["value"], row["_mask"]) == ("edited", MASK)
    # A row with no stored mask does nothing special on a key edit; an empty key is fine.
    p.get_by_test_id("k").nth(1).fill("")
    assert _vals(p)[1]["value"] == "example.org"
    # Two rows with the same key are independent.
    _sec(
        p,
        "[{name: 'S', value: '%s', _mask: '%s', sensitive: true}, {name: 'S', value: '%s', _mask: '%s', sensitive: true}]"
        % (MASK, MASK, MASK, MASK),
    )
    p.get_by_test_id("k").nth(1).fill("S2")
    assert [v["_mask"] for v in _vals(p)] == [MASK, ""]


def test_set_row_merges_and_keeps_focus_elsewhere(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.get_by_test_id("k").nth(1).focus()
    p.evaluate(
        "() => { window.__ev.length = 0; window.__v0 = document.querySelector('[data-testid=v]'); window.__k1 = document.querySelectorAll('[data-testid=k]')[1]; }"
    )
    p.evaluate("() => window.__kv.setRow(0, {value: '***wxyz', _mask: '***wxyz', extra: {a: 1}})")
    assert p.evaluate("() => document.activeElement === window.__k1") is True
    row = _vals(p)[0]
    assert (row["name"], row["value"], row["_mask"], row["extra"], row["sensitive"]) == (
        "API",
        "***wxyz",
        "***wxyz",
        {"a": 1},
        True,
    )
    assert _val(p) == "***wxyz" and _events(p) == []  # setRow never fires onChange
    assert p.evaluate("() => document.querySelector('[data-testid=v]') === window.__v0") is True
    # A re-mask after typing a new value returns the cell to stored mode with the eye hidden and hidden text.
    p.get_by_test_id("v").nth(0).click()
    p.keyboard.type("newsecret")
    p.get_by_role("button", name="Show value, row 1").click()
    p.evaluate("() => window.__kv.setRow(0, {value: '***cret', _mask: '***cret'})")
    out = p.evaluate(
        "() => { const v = document.querySelector('[data-testid=v]'); const td = v.closest('td'); return [v.value, v.type, td.querySelector('.api-key-eye').hidden, td.querySelector('.api-key-eye').getAttribute('aria-pressed')]; }"
    )
    assert out == ["***cret", "password", True, "false"]


def test_set_row_on_the_focused_row_keeps_focus_and_caret(engine_page: Page) -> None:
    p = engine_page
    _sec(p, "[{name: 'KEY', value: 'plain value', sensitive: false}]")
    k = p.get_by_test_id("k").nth(0)
    k.click()
    p.keyboard.press("Home")
    p.keyboard.press("ArrowRight")
    p.evaluate("() => window.__kv.setRow(0, {name: 'KEYS'})")
    out = p.evaluate(
        "() => { const k = document.querySelector('[data-testid=k]'); return [document.activeElement === k, k.value, k.selectionStart, k.selectionEnd]; }"
    )
    assert out == [True, "KEYS", 1, 1]
    # Patching the value (text variant) on the focused input also keeps focus.
    p.get_by_test_id("v").nth(0).focus()
    p.evaluate("() => window.__kv.setRow(0, {value: 'changed'})")
    assert (
        p.evaluate("() => document.activeElement === document.querySelector('[data-testid=v]')")
        is True
    )
    assert _val(p) == "changed"


def test_set_row_clears_only_the_error_of_a_changed_cell(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.evaluate(
        "() => { window.__kv.setError(1, 'name', 'N bad'); window.__kv.setError(1, 'value', 'V bad'); }"
    )
    p.evaluate("() => window.__kv.setRow(1, {value: 'other'})")
    out = p.evaluate(
        "() => { const tr = document.querySelectorAll('tbody tr')[1]; const e = tr.querySelectorAll('.ui-kv-error'); return [e[0].textContent, e[0].hidden, e[1].textContent, e[1].hidden, tr.querySelector('[data-testid=v]').getAttribute('aria-invalid')]; }"
    )
    assert out == ["N bad", False, "", True, None]


def test_unrelated_set_row_does_not_wipe_the_rename_hint(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.get_by_test_id("k").nth(0).fill("RENAMED")
    assert (
        p.evaluate("() => document.querySelector('.ui-secret-hint').textContent")
        == "Sensitive values must be re-entered when the key changes."
    )
    p.evaluate("() => window.__kv.setRow(0, {extra: 1})")
    p.evaluate("() => window.__kv.setRow(0, {sensitive: true})")
    assert (
        p.evaluate("() => document.querySelector('.ui-secret-hint').textContent")
        == "Sensitive values must be re-entered when the key changes."
    )


def test_remove_name_follows_a_typed_key(engine_page: Page) -> None:
    """Squawk 0269: typing a key renames the remove button; an empty key keeps the numbered name."""
    p = engine_page
    _sec(p)
    rm = p.get_by_test_id("kv-rm").nth(0)
    p.get_by_test_id("k").nth(0).fill("TYPED")
    assert rm.get_attribute("aria-label") == "Remove TYPED"
    p.get_by_test_id("k").nth(0).fill("")
    assert rm.get_attribute("aria-label") == "Remove row 1"


def test_set_row_rebaseline_clears_the_rename_hint(engine_page: Page) -> None:
    """Squawk 0270: a setRow that re-baselines the stored mask ends the rename hint."""
    p = engine_page
    _sec(p)
    p.get_by_test_id("k").nth(0).fill("RENAMED")
    hint = "() => document.querySelector('.ui-secret-hint').textContent"
    assert p.evaluate(hint) == "Sensitive values must be re-entered when the key changes."
    p.evaluate("() => window.__kv.setRow(0, {value: '', _mask: ''})")
    assert p.evaluate(hint) == ""


def test_error_and_stored_mode_share_aria_describedby_tokens(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.evaluate("() => window.__kv.setError(0, 'value', 'Nope')")
    out = p.evaluate(
        "() => { const v = document.querySelector('[data-testid=v]'); const td = v.closest('td'); const h = td.querySelector('.ui-secret-hint'); const e = td.querySelector('.ui-kv-error');\n      return [v.getAttribute('aria-describedby').split(' ').sort().join() === [h.id, e.id].sort().join(), v.getAttribute('aria-invalid')]; }"
    )
    assert out == [True, "true"]
    p.evaluate("() => window.__kv.setError(0, 'value', null)")
    out = p.evaluate(
        "() => { const v = document.querySelector('[data-testid=v]'); const h = v.closest('td').querySelector('.ui-secret-hint'); return [v.getAttribute('aria-describedby') === h.id, v.getAttribute('aria-invalid')]; }"
    )
    assert out == [True, None]
    # The hint leaves with stored mode and leaves the error in place.
    p.evaluate("() => window.__kv.setError(0, 'value', 'Again')")
    p.get_by_test_id("v").nth(0).click()
    p.keyboard.type("q")
    out = p.evaluate(
        "() => { const v = document.querySelector('[data-testid=v]'); const e = v.closest('td').querySelector('.ui-kv-error'); return v.getAttribute('aria-describedby') === e.id; }"
    )
    assert out is True


def test_degenerate_inputs_for_secret_tables(engine_page: Page) -> None:
    p = engine_page
    _sec(p, "[]")
    assert p.evaluate("() => window.__kv.el.querySelector('thead').hidden") is True
    p.get_by_test_id("kv-add").click()
    out = p.evaluate(
        "() => { const tr = document.querySelector('tbody tr'); return [tr.querySelector('[data-testid=v]').type, tr.querySelector('[data-testid=t]').checked, tr.querySelector('.ui-secret-hint'), tr.querySelector('.api-key-eye'), document.activeElement.getAttribute('data-testid')]; }"
    )
    assert out == ["text", False, None, None, "k"]
    long = "x" * 200
    p.get_by_test_id("v").nth(0).fill(long)
    assert _vals(p)[0]["value"] == long
    _tick(p, 0)  # masked now, 200 chars, no stored mode
    assert _val(p) == long and p.get_by_test_id("v").nth(0).get_attribute("type") == "password"
    assert [v["name"] for v in _vals(p)] == [""]  # an empty key row is kept
    assert p.get_by_test_id("kv-rm").nth(0).get_attribute("aria-label") == "Remove row 1"


def test_tab_order_and_escape_within_a_secret_row(engine_page: Page) -> None:
    p = engine_page
    _sec(p, "[{name: 'A', value: 'x', sensitive: true}]")
    p.get_by_test_id("k").nth(0).focus()
    seen = []
    for _ in range(4):
        p.keyboard.press("Tab")
        seen.append(
            p.evaluate(
                "() => { const a = document.activeElement; return a.getAttribute('data-testid') || a.className.split(' ')[0]; }"
            )
        )
    assert seen == ["v", "api-key-eye", "t", "kv-rm"]
    p.keyboard.press("Escape")  # Escape does nothing to the row
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "kv-rm"
    assert len(_vals(p)) == 1


def test_text_only_table_keeps_its_layout(engine_page: Page) -> None:
    p = engine_page
    _mount(p)
    out = p.evaluate(
        """() => { const t = window.__kv.el.querySelector('table'); const cs = getComputedStyle(t); const td = t.querySelector('tbody td');
          return [t.className, cs.tableLayout, t.querySelector('colgroup'), getComputedStyle(td).paddingLeft, t.getBoundingClientRect().width < window.__kv.el.getBoundingClientRect().width]; }"""
    )
    assert out == ["ui-kv-table", "auto", None, "8px", True]


def test_fixed_table_stays_within_a_narrow_host(engine_page: Page) -> None:
    p = engine_page
    _sec(p)
    p.evaluate("() => { window.__kv.el.style.width = '420px'; }")
    out = p.evaluate(
        "() => { const t = window.__kv.el.querySelector('table'); return [t.scrollWidth <= window.__kv.el.clientWidth, t.getBoundingClientRect().width, getComputedStyle(t).tableLayout]; }"
    )
    assert out[0] is True and out[2] == "fixed" and out[1] <= 420
    p.evaluate("() => window.__kv.setValues([])")  # an empty table keeps its colgroup widths
    assert p.evaluate("() => window.__kv.el.querySelectorAll('colgroup > col').length") == 4


def test_row_cells_share_one_top_and_value_widths_match(engine_page: Page) -> None:
    """HAT (M31 F5): with a stored-secret row (its hint makes the cell taller) and a plain row,
    every control in a row sits on the key input's top line (the switch and remove are centred on
    an input-height box), and the stored value box is as wide as a plain value input."""
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """() => {
          const kv = App.ui.keyValueTable({
            label: 'Headers', testid: 'kv', keyColumn: 'key',
            columns: [
              {key: 'key', label: 'Key', placeholder: 'KEY'},
              {key: 'value', label: 'Value', placeholder: 'value', type: 'secret', maskedBy: 'sensitive', storedKey: '_m'},
              {key: 'sensitive', label: 'Sensitive', type: 'toggle', ariaLabel: 'Sensitive'}],
            rows: [{key: 'plain', value: 'v', sensitive: false},
                   {key: 'stored', value: '********', _m: '********', sensitive: true}]});
          document.getElementById('harness-root').appendChild(kv.el);
          const top = (e) => e.getBoundingClientRect().top;
          const rows = [...kv.el.querySelectorAll('tr.ui-kv-row')].map((tr) => {
            const ins = tr.querySelectorAll('input.ui-kv-input');
            const k = ins[0], v = ins[1];
            const sw = tr.querySelector('.ui-toggle input, [role=switch]');
            const rm = tr.querySelector('.ui-kv-remove');
            const mid = (e) => e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2;
            return {kTop: top(k), vTop: top(v), kMid: mid(k), swMid: mid(sw), rmMid: mid(rm),
                    vW: v.getBoundingClientRect().width, hint: !!tr.querySelector('.ui-secret-hint:not(:empty)')};
          });
          return rows;
        }"""
    )
    assert len(out) == 2
    for r in out:
        assert abs(r["vTop"] - r["kTop"]) <= 1, r
        assert abs(r["swMid"] - r["kMid"]) <= 1.5, r
        assert abs(r["rmMid"] - r["kMid"]) <= 1.5, r
    assert out[1]["hint"] is True
    assert abs(out[0]["vW"] - out[1]["vW"]) <= 1, out


# --------------------------------------------------------------------------------------------
# Sortie 09 L05 (flight DD12): readOnly, lockBy, onBeforeRemove, markerBy/markerLabel,
# removableBy. Every option is inert when not passed.
# --------------------------------------------------------------------------------------------

OPT_COLS = """[{key: 'name', label: 'Name', placeholder: 'NAME', inputTestid: 'k'},
  {key: 'value', label: 'Value', type: 'secret', maskedBy: 'sensitive', storedKey: '_mask', inputTestid: 'v'},
  {key: 'sensitive', label: 'Sensitive', type: 'toggle', ariaLabel: 'Sensitive', inputTestid: 't'}]"""
OPT_ROWS = f"""[{{name: 'API', value: '{MASK}', _mask: '{MASK}', sensitive: true, lock: 'key', overridden: true, removable: false}},
  {{name: 'HOST', value: 'example.org', sensitive: false, lock: 'row', overridden: false, removable: true}},
  {{name: 'FREE', value: 'x', sensitive: false}}]"""


def _opt(page: Page, extra: str = "", rows: str = OPT_ROWS) -> None:
    _mount(
        page,
        "{columns: %s, rows: %s, removeLabel: (n, row) => 'Remove ' + (row.name || 'row ' + n)%s}"
        % (OPT_COLS, rows, extra),
    )


def test_options_are_inert_when_not_passed(engine_page: Page) -> None:
    p = engine_page
    _opt(p)
    out = p.evaluate(
        """() => {
          const el = window.__kv.el;
          return {ro: el.querySelectorAll('input[readonly]').length,
                  dis: el.querySelectorAll('button:disabled, input:disabled').length,
                  marker: el.querySelectorAll('.ui-kv-marker').length,
                  add: !!el.querySelector('.ui-kv-add'), rm: el.querySelectorAll('.ui-kv-remove').length,
                  cols: el.querySelectorAll('colgroup > col').length, ths: el.querySelectorAll('th').length};
        }"""
    )
    assert out == {"ro": 0, "dis": 0, "marker": 0, "add": True, "rm": 3, "cols": 4, "ths": 4}


def test_read_only_table(engine_page: Page) -> None:
    p = engine_page
    _opt(p, ", readOnly: true, lockBy: 'lock', removableBy: 'removable'")
    out = p.evaluate(
        """() => {
          const el = window.__kv.el;
          const ins = [...el.querySelectorAll('input.ui-kv-input')];
          return {ro: ins.every((i) => i.readOnly), n: ins.length,
                  types: ins.map((i) => i.type), vals: ins.map((i) => i.value),
                  names: ins.map((i) => i.getAttribute('aria-label')),
                  add: !!el.querySelector('.ui-kv-add'), rm: el.querySelectorAll('.ui-kv-remove').length,
                  cols: el.querySelectorAll('colgroup > col').length, ths: el.querySelectorAll('th').length,
                  eye: el.querySelectorAll('.api-key-eye, .api-key-wrap').length,
                  hint: el.querySelectorAll('.ui-secret-hint').length,
                  tog: [...el.querySelectorAll('.ui-toggle input')].map((i) => i.disabled)};
        }"""
    )
    assert out["ro"] is True and out["n"] == 6
    # The secret column is plain text showing the value as given (the mask string here).
    assert out["types"] == ["text"] * 6 and out["vals"][1] == MASK
    assert out["names"][:2] == ["Name, row 1", "Value, row 1"]
    assert out["add"] is False and out["rm"] == 0
    assert out["cols"] == 3 and out["ths"] == 3
    assert out["eye"] == 0 and out["hint"] == 0
    assert out["tog"] == [True, True, True]
    # Keyboard focus still reaches a read-only input.
    p.get_by_test_id("k").first.focus()
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "k"
    p.keyboard.press("Tab")
    assert p.evaluate("() => document.activeElement.getAttribute('data-testid')") == "v"
    # An empty read-only table is fine.
    p.evaluate("() => window.__kv.setValues([])")
    assert p.evaluate("() => window.__kv.el.querySelectorAll('tr.ui-kv-row').length") == 0


def test_lock_by_key_and_row(engine_page: Page) -> None:
    p = engine_page
    _opt(p, ", lockBy: 'lock'")
    out = p.evaluate(
        """() => [...window.__kv.el.querySelectorAll('tr.ui-kv-row')].map((tr) => ({
          key: tr.querySelector('[data-testid=k]').readOnly, val: tr.querySelector('[data-testid=v]').readOnly,
          tog: tr.querySelector('[data-testid=t]').disabled, rm: tr.querySelector('.ui-kv-remove').disabled}))"""
    )
    assert out[0] == {"key": True, "val": False, "tog": False, "rm": False}
    assert out[1] == {"key": True, "val": True, "tog": True, "rm": True}
    assert out[2] == {"key": False, "val": False, "tog": False, "rm": False}
    # A free row still edits and fires.
    p.get_by_test_id("k").nth(2).fill("FREE2")
    assert _vals(p)[2]["name"] == "FREE2"


def test_on_before_remove_can_cancel(engine_page: Page) -> None:
    p = engine_page
    _opt(
        p,
        ", onBeforeRemove: (row, i) => { window.__asked = [row.name, i]; return row.name !== 'API'; }",
    )
    p.get_by_role("button", name="Remove API").click()
    assert p.evaluate("() => window.__asked") == ["API", 0]
    assert [r["name"] for r in _vals(p)] == ["API", "HOST", "FREE"]
    assert _events(p) == []  # a cancelled remove fires no onChange
    assert p.evaluate("() => document.activeElement.getAttribute('aria-label')") == "Remove API"
    # The caller may patch the row instead.
    p.evaluate("() => window.__kv.setRow(0, {value: ''})")
    assert _vals(p)[0]["value"] == ""
    # A remove that returns anything but false goes through.
    p.get_by_role("button", name="Remove HOST").click()
    assert [r["name"] for r in _vals(p)] == ["API", "FREE"]
    assert _events(p)[-1].startswith("remove:")


def test_marker_pill_is_real_text_linked_by_describedby(engine_page: Page) -> None:
    p = engine_page
    _opt(p, ", markerBy: 'overridden', markerLabel: 'overridden'")
    out = p.evaluate(
        """() => [...window.__kv.el.querySelectorAll('tr.ui-kv-row')].map((tr) => {
          const pill = tr.querySelector('.ui-kv-marker');
          const k = tr.querySelector('[data-testid=k]');
          return {shown: !pill.hidden, text: pill.textContent, id: pill.id,
                  described: (k.getAttribute('aria-describedby') || '').split(/\\s+/).includes(pill.id)};
        })"""
    )
    assert [o["shown"] for o in out] == [True, False, False]
    assert out[0]["text"] == "overridden" and out[0]["id"]
    assert [o["described"] for o in out] == [True, False, False]
    # setRow flips it live and keeps focus.
    p.get_by_test_id("k").nth(1).focus()
    p.evaluate("() => window.__kv.setRow(1, {overridden: true})")
    assert p.evaluate(
        "() => document.activeElement === document.querySelectorAll('[data-testid=k]')[1]"
    )
    assert p.evaluate(
        """() => { const tr = document.querySelectorAll('tr.ui-kv-row')[1], pill = tr.querySelector('.ui-kv-marker');
          return !pill.hidden && tr.querySelector('[data-testid=k]').getAttribute('aria-describedby').includes(pill.id); }"""
    )
    p.evaluate("() => window.__kv.setRow(0, {overridden: false})")
    assert p.evaluate(
        """() => { const tr = document.querySelectorAll('tr.ui-kv-row')[0];
          return tr.querySelector('.ui-kv-marker').hidden && !(tr.querySelector('[data-testid=k]').getAttribute('aria-describedby') || '').includes('ui-kv-mark'); }"""
    )


def test_removable_by_disables_with_the_opaque_look(engine_page: Page) -> None:
    p = engine_page
    _opt(p, ", removableBy: 'removable'")
    out = p.evaluate(
        """() => {
          const probe = document.createElement('div');
          probe.style.color = 'var(--btn-disabled-fg)';
          window.__kv.el.appendChild(probe);
          const want = getComputedStyle(probe).color;
          probe.remove();
          return [...document.querySelectorAll('.ui-kv-remove')].map((b) => ({
            disabled: b.disabled, name: b.getAttribute('aria-label'), color: getComputedStyle(b).color,
            opacity: getComputedStyle(b).opacity, want, cursor: getComputedStyle(b).cursor}));
        }"""
    )
    assert [o["disabled"] for o in out] == [True, False, False]
    assert out[0]["name"] == "Remove API"  # keeps its name
    assert out[0]["color"] == out[0]["want"] and out[0]["opacity"] == "1"
    assert out[0]["cursor"] == "not-allowed"
    assert out[1]["color"] != out[1]["want"]
    # A forced click on the disabled button (or its icon) removes nothing.
    p.evaluate(
        "() => document.querySelector('.ui-kv-remove').dispatchEvent(new MouseEvent('click', {bubbles: true}))"
    )
    p.evaluate(
        "() => document.querySelector('.ui-kv-remove svg').dispatchEvent(new MouseEvent('click', {bubbles: true}))"
    )
    assert len(_vals(p)) == 3
    # A disabled button is not focusable.
    p.evaluate("() => document.querySelector('.ui-kv-remove').focus()")
    assert p.evaluate("() => document.activeElement.classList.contains('ui-kv-remove')") is False
    # setRow re-enables it live.
    p.evaluate("() => window.__kv.setRow(0, {removable: true})")
    assert p.evaluate("() => document.querySelector('.ui-kv-remove').disabled") is False
    p.evaluate("() => window.__kv.setRow(1, {removable: false})")
    assert p.evaluate("() => document.querySelectorAll('.ui-kv-remove')[1].disabled") is True


def test_set_row_reevaluates_a_lock_without_rebuilding_or_moving_focus(engine_page: Page) -> None:
    p = engine_page
    _opt(p, ", lockBy: 'lock'")
    p.get_by_test_id("v").nth(2).focus()
    p.evaluate("() => { window.__tr = document.querySelectorAll('tr.ui-kv-row')[2]; }")
    p.evaluate("() => window.__kv.setRow(2, {lock: 'row'})")
    out = p.evaluate(
        """() => { const tr = document.querySelectorAll('tr.ui-kv-row')[2];
          return {same: tr === window.__tr, focus: document.activeElement === tr.querySelector('[data-testid=v]'),
                  key: tr.querySelector('[data-testid=k]').readOnly, val: tr.querySelector('[data-testid=v]').readOnly,
                  tog: tr.querySelector('[data-testid=t]').disabled, rm: tr.querySelector('.ui-kv-remove').disabled}; }"""
    )
    assert out == {"same": True, "focus": True, "key": True, "val": True, "tog": True, "rm": True}
    p.evaluate("() => window.__kv.setRow(2, {lock: ''})")
    out = p.evaluate(
        """() => { const tr = document.querySelectorAll('tr.ui-kv-row')[2];
          return [tr.querySelector('[data-testid=k]').readOnly, tr.querySelector('[data-testid=t]').disabled,
                  tr.querySelector('.ui-kv-remove').disabled]; }"""
    )
    assert out == [False, False, False]


def test_lock_by_toggle_checks_and_disables_only_the_toggle(engine_page: Page) -> None:
    """Sortie 09 L06: 'toggle' locks the Sensitive switch on; 'key toggle' also locks the key."""
    p = engine_page
    _opt(p, ", lockBy: 'lock'")
    p.evaluate("() => window.__kv.setRow(2, {lock: 'toggle'})")
    out = p.evaluate(
        """() => { const tr = document.querySelectorAll('tr.ui-kv-row')[2];
          const t = tr.querySelector('[data-testid=t]');
          return {checked: t.checked, dis: t.disabled,
                  key: tr.querySelector('[data-testid=k]').readOnly,
                  val: tr.querySelector('[data-testid=v]').readOnly,
                  rm: tr.querySelector('.ui-kv-remove').disabled,
                  masked: !!tr.querySelector('input[type=password]'),
                  data: window.__kv.values()[2].sensitive}; }"""
    )
    assert out == {
        "checked": True,
        "dis": True,
        "key": False,
        "val": False,
        "rm": False,
        "masked": True,
        "data": True,
    }
    # The value still edits while the toggle is locked.
    p.get_by_test_id("v").nth(2).fill("typed")
    assert _vals(p)[2]["value"] == "typed"
    p.evaluate("() => window.__kv.setRow(2, {lock: 'key toggle'})")
    out = p.evaluate(
        """() => { const tr = document.querySelectorAll('tr.ui-kv-row')[2];
          return [tr.querySelector('[data-testid=k]').readOnly,
                  tr.querySelector('[data-testid=t]').disabled]; }"""
    )
    assert out == [True, True]
    # Lifting the lock re-enables the toggle (it stays checked until the operator changes it).
    p.evaluate("() => window.__kv.setRow(2, {lock: ''})")
    assert (
        p.evaluate(
            "() => document.querySelectorAll('tr.ui-kv-row')[2].querySelector('[data-testid=t]').disabled"
        )
        is False
    )


def test_lock_by_toggle_at_construction(engine_page: Page) -> None:
    p = engine_page
    _opt(
        p,
        ", lockBy: 'lock'",
        rows="[{name: 'Authorization', value: 'x', sensitive: false, lock: 'key toggle'}]",
    )
    out = p.evaluate(
        """() => { const tr = document.querySelector('tr.ui-kv-row');
          const t = tr.querySelector('[data-testid=t]');
          return [t.checked, t.disabled, tr.querySelector('[data-testid=k]').readOnly,
                  !!tr.querySelector('input[type=password]')]; }"""
    )
    assert out == [True, True, True, True]


# --- Sortie 18 L01: movable rows, fill, headHidden, focus() ---------------------------------

ABC = "{rows: [{channel: 'A', agent: 'a'}, {channel: 'B', agent: 'b'}, {channel: 'C', agent: 'c'}], movable: true, moveUpTestid: 'mv-up', moveDownTestid: 'mv-dn'}"


def _order(page: Page) -> list:
    return [r["channel"] for r in _vals(page)]


def _move_btn(page: Page, row: int, direction: str):
    tid = "mv-up" if direction == "up" else "mv-dn"
    return page.locator("tbody tr.ui-kv-row").nth(row).locator(f"[data-testid={tid}]")


def _active(page: Page) -> str:
    """Direction of the focused move button and its row index: 'down:2'."""
    return page.evaluate(
        "() => document.activeElement.dataset.move + ':' + Array.from(document.querySelectorAll('tbody tr')).indexOf(document.activeElement.closest('tr'))"
    )


def _press(btn, mode: str, key) -> None:
    if mode == "mouse":
        btn.click()
    else:
        btn.focus()
        btn.page.keyboard.press(key)


def test_movable_buttons_order_names_and_testids(engine_page: Page) -> None:
    _mount(engine_page, ABC)
    out = engine_page.evaluate(
        """() => Array.from(document.querySelectorAll('tbody tr')).map((tr) =>
          Array.from(tr.querySelectorAll('td:last-child button')).map((b) => [b.className.includes('ui-kv-move'), b.getAttribute('aria-label'), b.getAttribute('data-testid'), !!b.querySelector('svg'), b.disabled]))"""
    )
    assert out[1] == [
        [True, "Move row 2 up", "mv-up", True, False],
        [True, "Move row 2 down", "mv-dn", True, False],
        [False, "Remove row 2", "kv-rm", True, False],
    ], out
    assert out[0][0][4] is True and out[0][1][4] is False
    assert out[2][0][4] is False and out[2][1][4] is True
    engine_page.evaluate("() => window.__kv.setValues([{channel: 'x'}])")
    dis = engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-kv-move')).map((b) => b.disabled)"
    )
    assert dis == [True, True]
    _mount(
        engine_page,
        "{rows: [{channel: 'A'}, {channel: 'B'}], movable: true, moveLabel: (n, row, dir) => 'Go ' + dir + ' ' + row.channel + ' ' + n}",
    )
    names_js = "() => Array.from(document.querySelectorAll('.ui-kv-move')).map((b) => b.getAttribute('aria-label'))"
    assert engine_page.evaluate(names_js) == [
        "Go up A 1",
        "Go down A 1",
        "Go up B 2",
        "Go down B 2",
    ]
    engine_page.locator("tbody tr").nth(0).locator("input").first.fill("Z")
    assert engine_page.evaluate(names_js)[0] == "Go up Z 1"
    engine_page.evaluate("() => window.__kv.setRow(1, {channel: 'Q'})")
    assert engine_page.evaluate(names_js)[2] == "Go up Q 2"


def test_move_reorders_fires_once_keeps_node_and_error(engine_page: Page) -> None:
    _mount(engine_page, ABC)
    engine_page.evaluate(
        "() => { window.__n = Array.from(document.querySelectorAll('tbody tr')).map((tr) => tr.querySelector('input')); window.__kv.setError(1, 'channel', 'bad B'); window.__ev.length = 0; }"
    )
    _move_btn(engine_page, 1, "up").click()
    assert _order(engine_page) == ["B", "A", "C"]
    assert engine_page.evaluate("() => window.__ev.length") == 1
    assert engine_page.evaluate("() => window.__ev[0].split(':')[0]") == "move"
    same = engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('tbody tr')).map((tr) => tr.querySelector('input')).map((n, i) => n === window.__n[[1, 0, 2][i]])"
    )
    assert same == [True, True, True]
    assert (
        engine_page.evaluate(
            "() => document.querySelector('tbody tr:first-child .ui-kv-error').textContent"
        )
        == "bad B"
    )
    engine_page.evaluate("() => { window.__kv.setError(1, 'channel', 'bad A'); }")
    assert (
        engine_page.evaluate(
            "() => document.querySelectorAll('tbody tr')[1].querySelector('.ui-kv-error').textContent"
        )
        == "bad A"
    )
    _move_btn(engine_page, 0, "down").click()
    assert _order(engine_page) == ["A", "B", "C"]
    assert engine_page.evaluate("() => window.__ev.length") == 2
    dis = engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('tbody tr')).map((tr) => Array.from(tr.querySelectorAll('.ui-kv-move')).map((b) => b.disabled))"
    )
    assert dis == [[True, False], [False, False], [False, True]]


_ROW_STATE_JS = """() => Array.from(document.querySelectorAll('tbody tr.ui-kv-row')).map((tr) => ({
  names: Array.from(tr.querySelectorAll('td:last-child button')).map((b) => b.getAttribute('aria-label')),
  dis: Array.from(tr.querySelectorAll('.ui-kv-move')).map((b) => b.disabled)}))"""


def _expect_rows_state(page: Page, count: int) -> None:
    """Names carry the row number and the edge buttons are natively disabled, for `count` rows."""
    rows = page.evaluate(_ROW_STATE_JS)
    assert len(rows) == count, rows
    for i, r in enumerate(rows):
        n = i + 1
        assert r["names"] == [f"Move row {n} up", f"Move row {n} down", f"Remove row {n}"], rows
        assert r["dis"] == [i == 0, i == count - 1], rows


def test_names_and_edge_state_follow_add_remove_and_move(engine_page: Page) -> None:
    _mount(engine_page, ABC)
    _expect_rows_state(engine_page, 3)
    engine_page.locator("[data-testid=kv-add]").click()
    _expect_rows_state(engine_page, 4)
    _move_btn(engine_page, 3, "up").click()
    _expect_rows_state(engine_page, 4)
    _move_btn(engine_page, 0, "down").click()
    _expect_rows_state(engine_page, 4)
    engine_page.locator("tbody tr.ui-kv-row").nth(1).locator("[data-testid=kv-rm]").click()
    _expect_rows_state(engine_page, 3)
    engine_page.locator("tbody tr.ui-kv-row").nth(0).locator("[data-testid=kv-rm]").click()
    _expect_rows_state(engine_page, 2)
    engine_page.locator("tbody tr.ui-kv-row").nth(1).locator("[data-testid=kv-rm]").click()
    _expect_rows_state(engine_page, 1)


def test_fill_on_an_already_fixed_table_changes_nothing(engine_page: Page) -> None:
    cols = "[{key: 'k', label: 'K'}, {key: 't', label: 'T', type: 'toggle'}]"
    rows = "[{k: 'a', t: true}]"
    probe = """() => {
      const table = window.__kv.el.querySelector('table');
      return {cls: table.className,
              cols: Array.from(table.querySelectorAll('colgroup col')).map((c) => c.style.width),
              widths: Array.from(table.querySelectorAll('thead th')).map((th) => Math.round(th.getBoundingClientRect().width))};
    }"""
    _mount(engine_page, f"{{columns: {cols}, rows: {rows}}}")
    plain = engine_page.evaluate(probe)
    _mount(engine_page, f"{{fill: true, columns: {cols}, rows: {rows}}}")
    assert engine_page.evaluate(probe) == plain
    sec = "[{key: 'k', label: 'K'}, {key: 's', label: 'S', type: 'secret'}]"
    _mount(engine_page, f"{{columns: {sec}, rows: [{{k: 'a', s: 'x'}}]}}")
    plain = engine_page.evaluate(probe)
    _mount(engine_page, f"{{fill: true, columns: {sec}, rows: [{{k: 'a', s: 'x'}}]}}")
    assert engine_page.evaluate(probe) == plain


def test_click_on_a_disabled_move_button_does_nothing(engine_page: Page) -> None:
    _mount(engine_page, ABC)
    engine_page.evaluate(
        """() => {
          window.__ev.length = 0;
          const first = document.querySelector('tbody tr:first-child .ui-kv-move');
          const last = document.querySelectorAll('tbody tr:last-child .ui-kv-move')[1];
          for (const b of [first, last]) {
            for (const target of [b, b.querySelector('svg')]) {
              target.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            }
          }
        }"""
    )
    assert _order(engine_page) == ["A", "B", "C"]
    assert engine_page.evaluate("() => window.__ev.length") == 0


@pytest.mark.parametrize(
    "mode,key", [("mouse", None), ("keyboard", "Enter"), ("keyboard", "Space")]
)
def test_focus_after_a_move_stays_on_the_pressed_button(engine_page: Page, mode: str, key) -> None:
    _mount(engine_page, ABC)
    # The pressed button stays enabled: focus stays on it.
    _press(_move_btn(engine_page, 0, "down"), mode, key)  # A to row 2
    assert _order(engine_page) == ["B", "A", "C"]
    assert _active(engine_page) == "down:1"
    # The pressed button becomes disabled (down at the last row): focus goes to its up button.
    _press(_move_btn(engine_page, 1, "down"), mode, key)  # A to row 3
    assert _order(engine_page) == ["B", "C", "A"]
    assert _active(engine_page) == "up:2"
    # Up to the first row: up becomes disabled, focus goes to the down button.
    _press(_move_btn(engine_page, 2, "up"), mode, key)
    _press(_move_btn(engine_page, 1, "up"), mode, key)
    assert _order(engine_page) == ["A", "B", "C"]
    assert _active(engine_page) == "down:0"


def test_move_announces_through_one_status_node(engine_page: Page) -> None:
    _mount(engine_page, ABC)
    engine_page.evaluate(
        """() => {
          const n = document.querySelector('.ui-kv-live');
          window.__log = [];
          new MutationObserver(() => window.__log.push(n.textContent)).observe(n, {childList: true, characterData: true, subtree: true});
        }"""
    )
    assert engine_page.evaluate(
        "() => { const n = document.querySelectorAll('.ui-kv-live'); return [n.length, n[0].getAttribute('role'), n[0].classList.contains('visually-hidden'), window.__kv.el.lastElementChild === n[0]]; }"
    ) == [1, "status", True, True]
    _move_btn(engine_page, 0, "down").click()
    engine_page.wait_for_function("() => window.__log.includes('Moved to row 2 of 3.')")
    n = engine_page.evaluate("() => window.__log.length")
    _move_btn(engine_page, 2, "up").click()
    engine_page.wait_for_function(
        "(n) => window.__log.length > n && window.__log[window.__log.length - 1] === 'Moved to row 2 of 3.'",
        arg=n,
    )
    log = engine_page.evaluate("() => window.__log")
    assert log.count("Moved to row 2 of 3.") == 2, log
    assert "" in log[log.index("Moved to row 2 of 3.") + 1 :], log
    _mount(engine_page, "null")
    assert (
        engine_page.evaluate("() => document.querySelectorAll('.ui-kv-live, .ui-kv-move').length")
        == 0
    )
    _mount(engine_page, ABC)
    engine_page.evaluate(
        "() => { document.querySelector('tbody tr .ui-kv-move[data-move=down]').click(); window.__kv.destroy(); }"
    )
    engine_page.evaluate("() => new Promise((r) => setTimeout(r, 30))")
    assert engine_page.evaluate("() => document.querySelector('.ui-kv-live').textContent") == ""


def test_movable_read_only_and_lock_options(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const c = [{key: 'a', label: 'A'}];
          const t = (o) => { try { App.ui.keyValueTable(Object.assign({columns: c}, o)); return null; } catch (e) { return e.message; } };
          const ro = App.ui.keyValueTable({columns: c, rows: [{a: '1'}, {a: '2'}], movable: true, readOnly: true});
          return {
            ro: ro.el.querySelectorAll('.ui-kv-move, .ui-kv-live').length,
            lock: t({movable: true, lockBy: 'x'}), rem: t({movable: true, removableBy: 'x'}), mark: t({movable: true, markerBy: 'x'}),
            roLock: t({movable: true, readOnly: true, lockBy: 'x'}), roRem: t({movable: true, readOnly: true, removableBy: 'x'}),
            roMark: t({movable: true, readOnly: true, markerBy: 'x'})
          };
        }"""
    )
    assert out["ro"] == 0
    assert "lockBy" in out["lock"] and "removableBy" in out["rem"] and "markerBy" in out["mark"]
    assert (
        "lockBy" in out["roLock"] and "removableBy" in out["roRem"] and "markerBy" in out["roMark"]
    )


def test_fill_gives_the_fixed_full_width_layout(engine_page: Page) -> None:
    _mount(engine_page, "{fill: true}")
    out = engine_page.evaluate(
        """() => {
          const root = window.__kv.el; const table = root.querySelector('table');
          const input = table.querySelector('tbody input');
          return {fixed: table.classList.contains('ui-kv-table--fixed'), cg: !!table.querySelector('colgroup'),
                  tw: table.getBoundingClientRect().width, rw: root.getBoundingClientRect().width,
                  cell: input.closest('td').getBoundingClientRect().width, iw: input.getBoundingClientRect().width,
                  act: table.querySelector('colgroup').lastElementChild.style.width};
        }"""
    )
    assert out["fixed"] and out["cg"] and out["act"] == "48px", out
    assert abs(out["tw"] - out["rw"]) <= 1, out
    assert out["iw"] >= out["cell"] - 17, out
    engine_page.evaluate("() => window.__kv.setValues([])")
    out = engine_page.evaluate(
        "() => ({tw: window.__kv.el.querySelector('table').getBoundingClientRect().width, rw: window.__kv.el.getBoundingClientRect().width, hid: window.__kv.el.querySelector('thead').hidden, add: !!window.__kv.el.querySelector('.ui-kv-add')})"
    )
    assert abs(out["tw"] - out["rw"]) <= 1 and out["hid"] and out["add"], out
    _mount(
        engine_page,
        "{fill: true, columns: [{key: 'k', label: 'K'}, {key: 't', label: 'T', type: 'toggle'}], rows: [{k: 'a', t: true}]}",
    )
    assert (
        engine_page.evaluate("() => window.__kv.el.querySelector('table').className")
        == "ui-kv-table ui-kv-table--fixed"
    )


def test_movable_actions_column_holds_three_buttons_on_one_line(engine_page: Page) -> None:
    _mount(engine_page, ABC.replace("movable: true", "movable: true, fill: true"))
    out = engine_page.evaluate(
        """() => {
          const tr = document.querySelector('tbody tr'); const td = tr.lastElementChild;
          const bs = Array.from(td.querySelectorAll('button')).map((b) => b.getBoundingClientRect());
          const c = td.getBoundingClientRect();
          return {tops: bs.map((b) => Math.round(b.top)), left: bs[0].left - c.left, right: c.right - bs[2].right, sw: td.scrollWidth, cw: td.clientWidth};
        }"""
    )
    assert len(set(out["tops"])) == 1, out
    assert out["left"] >= 0 and out["right"] >= 0 and out["sw"] <= out["cw"], out


def test_head_hidden_keeps_labels_and_takes_no_height(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{headHidden: true, fill: true, columns: [{key: 'k', label: (() => { const s = document.createElement('b'); s.textContent = 'Arg'; return s; })()}, {key: 'v', label: 'Val'}]}",
    )
    out = engine_page.evaluate(
        """() => {
          const table = window.__kv.el.querySelector('table');
          const ths = Array.from(table.querySelectorAll('thead th[scope=col]'));
          const body = table.querySelector('tbody tr').getBoundingClientRect();
          return {cls: table.classList.contains('ui-kv-table--head-hidden'), n: ths.length,
                  spans: ths.slice(0, 2).map((t) => [t.firstElementChild.tagName, t.firstElementChild.className, t.textContent.trim()]),
                  head: table.tHead.getBoundingClientRect().height, gap: body.top - table.getBoundingClientRect().top,
                  name: table.querySelector('tbody input').getAttribute('aria-label')};
        }"""
    )
    assert out["cls"] and out["n"] == 3, out
    assert out["spans"] == [
        ["SPAN", "visually-hidden", "Arg"],
        ["SPAN", "visually-hidden", "Val"],
    ], out
    assert out["head"] <= 1 and out["gap"] <= 1, out
    assert out["name"] == "Arg, row 1", out
    engine_page.evaluate("() => window.__kv.setValues([])")
    assert engine_page.evaluate("() => window.__kv.el.querySelector('thead').hidden") is True


def test_focus_method(engine_page: Page) -> None:
    _mount(engine_page, "null")
    engine_page.evaluate("() => window.__kv.focus()")
    assert (
        engine_page.evaluate("() => document.activeElement.getAttribute('data-testid')") == "c-ch"
    )
    engine_page.evaluate("() => { window.__kv.setValues([]); window.__kv.focus(); }")
    assert (
        engine_page.evaluate("() => document.activeElement.getAttribute('data-testid')") == "kv-add"
    )
    _mount(engine_page, "{readOnly: true, rows: []}")
    assert (
        engine_page.evaluate(
            "() => { window.__kv.focus(); return document.activeElement === document.body; }"
        )
        is True
    )


def test_move_options_are_inert_when_not_passed(engine_page: Page) -> None:
    _mount(engine_page, "null")
    out = engine_page.evaluate(
        "() => ({mv: document.querySelectorAll('.ui-kv-move').length, live: document.querySelectorAll('.ui-kv-live').length, hh: window.__kv.el.querySelector('table').classList.contains('ui-kv-table--head-hidden'), cls: window.__kv.el.querySelector('table').className})"
    )
    assert out == {"mv": 0, "live": 0, "hh": False, "cls": "ui-kv-table"}, out


def test_add_aria_label_names_the_button_and_is_inert_otherwise(engine_page: Page) -> None:
    _mount(engine_page, "{addAriaLabel: 'Add row to Channels'}")
    add = engine_page.get_by_test_id("kv-add")
    expect(add).to_have_attribute("aria-label", "Add row to Channels")
    expect(add).to_have_text("+ Add row")
    expect(engine_page.get_by_role("button", name="Add row to Channels")).to_have_count(1)
    add.click()
    expect(engine_page.locator("[data-testid=kv-row]")).to_have_count(3)
    assert engine_page.evaluate("() => window.__ev.pop()").startswith("add:")
    # A custom visible label keeps its own text; the name is still the option's.
    _mount(engine_page, "{addAriaLabel: 'Add channel row', addLabel: 'Add it'}")
    expect(engine_page.get_by_test_id("kv-add")).to_have_text("Add it")
    expect(engine_page.get_by_test_id("kv-add")).to_have_attribute("aria-label", "Add channel row")
    # Not passed, or empty: no attribute at all. Read-only: no Add button.
    for extra in ("null", "{addAriaLabel: ''}"):
        _mount(engine_page, extra)
        expect(engine_page.get_by_test_id("kv-add")).not_to_have_attribute(
            "aria-label", re.compile(".*")
        )
        assert (
            engine_page.evaluate(
                "() => window.__kv.el.querySelector('.ui-kv-add').hasAttribute('aria-label')"
            )
            is False
        )
    _mount(engine_page, "{readOnly: true, addAriaLabel: 'Add row to Channels'}")
    expect(engine_page.locator(".ui-kv-add")).to_have_count(0)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_move_button_look_uses_tokens_never_opacity(engine_page: Page, theme: str) -> None:
    _mount(engine_page, ABC, theme)
    out = engine_page.evaluate(
        """() => {
          const probe = document.createElement('span'); document.getElementById('harness-root').appendChild(probe);
          const tok = (n) => { probe.style.color = 'var(' + n + ')'; return getComputedStyle(probe).color; };
          const cs = (b) => { const s = getComputedStyle(b); return [s.color, s.opacity, s.cursor]; };
          const rows = document.querySelectorAll('tbody tr');
          const dis = rows[0].querySelector('.ui-kv-move'); const en = rows[1].querySelector('.ui-kv-move'); const rm = rows[1].querySelector('.ui-kv-remove');
          return {dis: cs(dis), en: cs(en), rm: cs(rm), fgDis: tok('--btn-disabled-fg'), fg: tok('--fg')};
        }"""
    )
    assert out["dis"] == [out["fgDis"], "1", "not-allowed"], out
    assert out["en"][1] == "1" and out["en"][0] == out["rm"][0], out
    engine_page.locator("tbody tr").nth(1).locator(".ui-kv-move").first.hover()
    engine_page.wait_for_function(
        "(c) => getComputedStyle(document.querySelectorAll('tbody tr')[1].querySelector('.ui-kv-move')).color === c",
        arg=out["fg"],
    )

# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.keyValueTable`` (M31 F3 L04, flight DD4/DD8-1/DD10/DD11).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts-controls`` browser lane. No fixed sleeps.
"""

from __future__ import annotations

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
        "Type the value again for the new name.",
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
        == "Type the value again for the new name."
    )
    p.evaluate("() => window.__kv.setRow(0, {extra: 1})")
    p.evaluate("() => window.__kv.setRow(0, {sensitive: true})")
    assert (
        p.evaluate("() => document.querySelector('.ui-secret-hint').textContent")
        == "Type the value again for the new name."
    )


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

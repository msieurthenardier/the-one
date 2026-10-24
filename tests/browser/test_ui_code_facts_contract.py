# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.codeBlock``, ``App.ui.facts``, the ``section``
``info`` option and the ``textInput`` options ``min``/``max``/``step``/``inputMode``/``width``
(M31 F4 L04b). Chromium and WebKit; ``contracts-controls``."""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

LONG = "\\n".join(f"line {i}" for i in range(80))


def _mount_code(page: Page, opts: str) -> None:
    load_harness(page)
    page.evaluate(
        f"() => {{ window.__c = App.ui.codeBlock({opts}); document.getElementById('harness-root').appendChild(window.__c.el); window.__c.refresh(); }}"
    )


def test_code_block_shape_and_no_trim_by_default(engine_page: Page) -> None:
    _mount_code(engine_page, "{text: '\\n  a\\n    b\\n\\n', className: 'extra', testid: 'cb'}")
    out = engine_page.evaluate(
        "() => [__c.el.tagName, __c.el.className, __c.el.textContent, __c.el.getAttribute('data-testid')]"
    )
    assert out == ["PRE", "code-block ui-code-block extra", "\n  a\n    b\n\n", "cb"]


def test_code_block_trim_blank_lines_only(engine_page: Page) -> None:
    _mount_code(engine_page, "{text: '  \\n\\n    keep\\n      more\\n  \\n', trim: true}")
    assert engine_page.evaluate("() => __c.el.textContent") == "    keep\n      more"
    engine_page.evaluate("() => __c.set('\\n\\nx\\n')")
    assert engine_page.evaluate("() => __c.el.textContent") == "x"


def test_code_block_unknown_height_throws(engine_page: Page) -> None:
    load_harness(engine_page)
    msg = engine_page.evaluate(
        "() => { try { App.ui.codeBlock({text: 'x', maxHeight: 'huge'}); return ''; } catch (e) { return e.message; } }"
    )
    assert "maxHeight" in msg


@pytest.mark.parametrize(("height", "rem"), [("tall", 24), ("short", 18)])
def test_code_block_heights(engine_page: Page, height: str, rem: int) -> None:
    _mount_code(engine_page, f"{{text: 'x', maxHeight: '{height}'}}")
    out = engine_page.evaluate(
        "() => { const s = getComputedStyle(__c.el); return [s.maxHeight, s.overflowY, parseFloat(getComputedStyle(document.documentElement).fontSize)]; }"
    )
    assert out[0] == f"{rem * out[2]:g}px"
    assert out[1] == "auto"


def test_code_block_overflow_region_and_reevaluation(engine_page: Page) -> None:
    _mount_code(engine_page, "{text: 'short', maxHeight: 'short', label: 'Prompt text'}")
    attrs = "() => [__c.el.getAttribute('tabindex'), __c.el.getAttribute('role'), __c.el.getAttribute('aria-label')]"
    assert engine_page.evaluate(attrs) == [None, None, None]
    engine_page.evaluate(f"() => __c.set('{LONG}')")
    assert engine_page.evaluate(attrs) == ["0", "region", "Prompt text"]
    assert engine_page.get_by_role("region", name="Prompt text").count() == 1
    engine_page.evaluate("() => __c.set('short')")
    assert engine_page.evaluate(attrs) == [None, None, None]


def test_code_block_overflow_without_label_gets_no_region(engine_page: Page) -> None:
    _mount_code(engine_page, f"{{text: '{LONG}', maxHeight: 'short'}}")
    assert engine_page.evaluate(
        "() => [__c.el.getAttribute('tabindex'), __c.el.getAttribute('role')]"
    ) == [None, None]


def test_code_block_attach_after_construct_is_measured(engine_page: Page) -> None:
    load_harness(engine_page)
    engine_page.evaluate(
        f"() => {{ window.__c = App.ui.codeBlock({{text: '{LONG}', maxHeight: 'short', label: 'L'}}); document.getElementById('harness-root').appendChild(window.__c.el); }}"
    )
    engine_page.wait_for_function("() => __c.el.getAttribute('role') === 'region'")


def test_code_block_matches_legacy_look(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          const legacy = document.createElement('pre'); legacy.className = 'code-block'; legacy.textContent = 'x';
          const cb = App.ui.codeBlock({text: 'x'});
          root.appendChild(legacy); root.appendChild(cb.el);
          const pick = (e) => { const s = getComputedStyle(e); return ['fontFamily','fontSize','lineHeight','paddingTop','paddingLeft','backgroundColor','color','borderTopWidth','borderTopColor','borderRadius','whiteSpace','overflowX','margin'].map((k) => s[k]); };
          return [pick(legacy), pick(cb.el)];
        }"""
    )
    assert out[0] == out[1]


def test_facts_shape_pairing_mono_and_testids(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const a = document.createElement('b'); a.textContent = 'A';
          const b = document.createElement('i'); b.textContent = 'B';
          const f = App.ui.facts({testid: 'fx', rows: [
            {label: 'Zone', value: 'UTC', mono: true, testid: 'r1', valueTestid: 'v1'},
            {label: 'Nodes', value: [a, b], testid: 'r2'},
            {label: 'One', value: a.cloneNode(true)}]});
          document.getElementById('harness-root').appendChild(f.el);
          window.__f = f;
          const rows = Array.from(f.el.children);
          return {
            tag: f.el.tagName, cls: f.el.className, tid: f.el.getAttribute('data-testid'),
            rows: rows.map((r) => [r.tagName, r.className, r.getAttribute('data-testid'), Array.from(r.children).map((k) => k.tagName)]),
            dd0: [rows[0].lastChild.className, rows[0].lastChild.getAttribute('data-testid'), rows[0].lastChild.textContent, getComputedStyle(rows[0].lastChild).fontFamily],
            dd1: rows[1].lastChild.innerHTML, dd2: rows[2].lastChild.innerHTML,
            dd1font: getComputedStyle(rows[1].lastChild).fontFamily,
            dt: rows.map((r) => r.firstChild.textContent)
          };
        }"""
    )
    assert out["tag"] == "DL" and out["cls"] == "ui-facts" and out["tid"] == "fx"
    assert out["rows"][0] == ["DIV", "ui-facts-row", "r1", ["DT", "DD"]]
    assert out["rows"][1][2] == "r2" and out["rows"][2][2] is None
    assert out["dd0"][:3] == ["ui-facts-value ui-facts-value--mono", "v1", "UTC"]
    assert (
        "mono" in out["dd0"][3].lower()
        or "monospace" in out["dd0"][3].lower()
        or out["dd0"][3] != out["dd1font"]
    )
    assert out["dd1"] == "<b>A</b><i>B</i>" and out["dd2"] == "<b>A</b>"
    assert out["dt"] == ["Zone", "Nodes", "One"]


def test_facts_set_replaces_rows_and_escapes_text(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const f = App.ui.facts({rows: [{label: 'x', value: '1'}]});
          f.set([{label: 'a', value: '<b>no</b>'}, {label: 'b', value: ''}]);
          return [f.el.children.length, f.el.querySelector('dd').innerHTML, f.el.querySelector('b') === null];
        }"""
    )
    assert out == [2, "&lt;b&gt;no&lt;/b&gt;", True]


def test_section_info_button_order_name_tab_and_rule(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const s = App.ui.section({title: 'Test', titleTag: 'h2', info: {text: 'Runs a probe.', label: 'Test'}, children: [Object.assign(document.createElement('button'), {textContent: 'after'})]});
          document.getElementById('harness-root').appendChild(s.el);
          const row = s.el.firstChild;
          const title = row.querySelector('.section-title'), info = row.querySelector('.ui-info');
          const pseudo = getComputedStyle(row, '::after');
          const tPseudo = getComputedStyle(title, '::after');
          return {
            cls: row.className, kids: Array.from(row.children).map((k) => k.className), tag: title.tagName,
            label: info.querySelector('button').getAttribute('aria-label'),
            rule: [pseudo.content, pseudo.height, parseFloat(pseudo.width) > 20], titleRule: tPseudo.content,
            order: info.getBoundingClientRect().left >= title.getBoundingClientRect().right
          };
        }"""
    )
    assert out["cls"] == "ui-section-title-row" and out["tag"] == "H2"
    assert out["kids"] == ["section-title", "ui-info"]
    assert out["label"] == "More information about Test"
    assert out["rule"][2] is True and out["rule"][1] == "1px"
    assert out["titleRule"] in ("none", "normal")
    assert out["order"] is True
    engine_page.keyboard.press("Tab")
    assert engine_page.evaluate("() => document.activeElement.className") == "field-info-icon"
    assert engine_page.get_by_role("button", name="More information about Test").count() == 1


def test_section_info_needs_title_and_default_unchanged(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          let msg = '';
          try { App.ui.section({info: {text: 't'}}); } catch (e) { msg = e.message; }
          const s = App.ui.section({title: 'Plain'});
          return [msg, s.el.firstChild.className, s.el.querySelector('.ui-section-title-row') === null];
        }"""
    )
    assert "title" in out[0] and out[1] == "section-title" and out[2] is True


def test_text_input_attributes(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const i = App.ui.textInput({type: 'number', min: 0, max: 65535, step: 1, inputMode: 'numeric'});
          const p = App.ui.textInput({});
          return [i.getAttribute('min'), i.getAttribute('max'), i.getAttribute('step'), i.getAttribute('inputmode'),
                  p.hasAttribute('min'), p.hasAttribute('inputmode'), p.className];
        }"""
    )
    assert out == ["0", "65535", "1", "numeric", False, False, "field-input"]


def test_text_input_short_width_inside_field(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          root.style.width = '600px';
          const mk = (w) => App.ui.field({label: 'L' + (w || 'full'), control: App.ui.textInput({width: w})});
          const full = mk(undefined), short = mk('short');
          root.appendChild(full.el); root.appendChild(short.el);
          const ch = parseFloat(getComputedStyle(short.el.querySelector('input')).fontSize);
          return [full.el.querySelector('input').getBoundingClientRect().width,
                  short.el.querySelector('input').getBoundingClientRect().width, short.el.querySelector('input').className];
        }"""
    )
    assert out[0] > 500
    assert 40 < out[1] < 200
    assert "ui-input--short" in out[2]


def test_text_input_unknown_width_throws(engine_page: Page) -> None:
    load_harness(engine_page)
    msg = engine_page.evaluate(
        "() => { try { App.ui.textInput({width: 'wide'}); return ''; } catch (e) { return e.message; } }"
    )
    assert "width" in msg

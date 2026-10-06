# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for the M25 F1 L4 core controls: ``textarea``,
``select``, ``checkbox``, ``toggle``, ``badge``, ``emptyState``, ``field`` around every
control, and the ``listPane`` hardening (empty element, kinded badges, counts,
selected-row colour, regular density).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _load(page: Page, theme: str = "dark") -> None:
    load_harness(page, theme)


def _mount(page: Page, js: str):
    """Run ``js`` (an arrow-function source) after loading the harness."""
    _load(page)
    return page.evaluate(js)


def _throws(page: Page, expr: str) -> str:
    return page.evaluate(
        "(src) => { try { (new Function(src))(); return ''; } catch (e) { return e.message; } }",
        expr,
    )


# ── textarea ────────────────────────────────────────────────────────────────


def test_textarea_options_fill_and_testid(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          window.__in = [];
          const t = App.ui.textarea({name: 'notes', value: 'seed', placeholder: 'Type', testid: 'ta-1',
                                     required: true, onInput: (e) => window.__in.push(e.target.value)});
          const d = App.ui.textarea({rows: 7, disabled: true, testid: 'ta-2'});
          const root = document.getElementById('harness-root');
          root.appendChild(t); root.appendChild(d);
          return {cls: t.className, tag: t.tagName, rows: t.rows, drows: d.rows, name: t.name, value: t.value,
                  ph: t.placeholder, req: t.required, idOk: /^ui-ta-\\d+$/.test(t.id), tid: t.getAttribute('data-testid'),
                  dis: d.disabled};
        }""",
    )
    assert out == {
        "cls": "field-input field-textarea", "tag": "TEXTAREA", "rows": 4, "drows": 7,
        "name": "notes", "value": "seed", "ph": "Type", "req": True, "idOk": True,
        "tid": "ta-1", "dis": True,
    }  # fmt: skip
    ta = engine_page.get_by_test_id("ta-1")
    ta.fill("hello\nworld")
    expect(ta).to_have_value("hello\nworld")
    seen = engine_page.evaluate("() => window.__in")
    assert seen and seen[-1] == "hello\nworld"  # fill may emit a clearing event first
    assert engine_page.get_by_test_id("ta-2").is_disabled()


# ── select ──────────────────────────────────────────────────────────────────


def test_select_options_groups_literal_labels_and_select_option(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          window.__ch = [];
          const s = App.ui.select({
            name: 'kind', testid: 'sel-1', value: 'b', required: true,
            onChange: (e) => window.__ch.push(e.target.value),
            options: [
              {value: 'a', label: 'A & <b>B</b>'},
              {value: 'b', label: 'Bravo'},
              {label: 'Group', options: [{value: 'c', label: 'Charlie'}, {value: 'd', label: 'Delta', disabled: true}]},
            ],
          });
          document.getElementById('harness-root').appendChild(s);
          return {cls: s.className, value: s.value, groups: s.querySelectorAll('optgroup').length,
                  opts: s.options.length, label0: s.options[0].textContent, bold: !!s.querySelector('b'),
                  req: s.required, idOk: /^ui-sel-\\d+$/.test(s.id), name: s.name,
                  dDisabled: s.options[3].disabled};
        }""",
    )
    assert out == {
        "cls": "field-input field-select", "value": "b", "groups": 1, "opts": 4,
        "label0": "A & <b>B</b>", "bold": False, "req": True, "idOk": True, "name": "kind",
        "dDisabled": True,
    }  # fmt: skip
    sel = engine_page.get_by_test_id("sel-1")
    sel.select_option("c")
    expect(sel).to_have_value("c")
    sel.select_option(label="A & <b>B</b>")
    assert engine_page.evaluate("() => window.__ch") == ["c", "a"]


def test_select_disabled_and_throws(engine_page: Page) -> None:
    _load(engine_page)
    assert "non-empty" in _throws(engine_page, "App.ui.select({options: []})")
    assert "non-empty" in _throws(engine_page, "App.ui.select({})")
    assert "non-empty" in _throws(
        engine_page, "App.ui.select({options: [{label: 'G', options: []}]})"
    )
    assert "not among" in _throws(
        engine_page, "App.ui.select({options: [{value: 'a', label: 'A'}], value: 'zzz'})"
    )
    engine_page.evaluate(
        """() => document.getElementById('harness-root').appendChild(
          App.ui.select({disabled: true, testid: 'sel-d', options: [{value: 'a', label: 'A'}]}))"""
    )
    assert engine_page.get_by_test_id("sel-d").is_disabled()


# ── checkbox ────────────────────────────────────────────────────────────────

MOUNT_CHECKBOX_JS = """() => {
  window.__cb = [];
  const c = App.ui.checkbox({label: 'Enable thing', hint: 'Extra detail', testid: 'cb-1',
                             onChange: (v) => window.__cb.push(v)});
  window.__c = c;
  document.getElementById('harness-root').appendChild(c.el);
  return true;
}"""


def test_checkbox_structure_hint_sibling_and_name(engine_page: Page) -> None:
    _mount(engine_page, MOUNT_CHECKBOX_JS)
    out = engine_page.evaluate(
        """() => {
          const c = window.__c; const root = c.el;
          const label = root.querySelector('label'); const input = c.control; const hint = root.querySelector('.field-hint');
          return {rootCls: root.className, labelCls: label.className, inLabel: input.parentElement === label,
                  inputCls: input.className, type: input.type, tid: input.getAttribute('data-testid'),
                  own: input.getAttribute('data-ui-own-label'), hintInLabel: label.contains(hint),
                  hintSibling: hint.parentElement === root && label.nextElementSibling === hint,
                  desc: input.getAttribute('aria-describedby') === hint.id, span: label.querySelector('span').textContent,
                  ctl: Object.keys(c).sort()};
        }"""
    )
    assert out == {
        "rootCls": "ui-checkbox", "labelCls": "ui-checkbox-label", "inLabel": True,
        "inputCls": "checkbox-primary", "type": "checkbox", "tid": "cb-1", "own": "true",
        "hintInLabel": False, "hintSibling": True, "desc": True, "span": "Enable thing",
        "ctl": ["control", "el", "setChecked", "setIndeterminate"],
    }  # fmt: skip
    # exact accessible name: the hint text is not part of it
    box = engine_page.get_by_role("checkbox", name="Enable thing", exact=True)
    expect(box).to_have_count(1)
    assert_controls_labelled_and_described(engine_page, "#harness-root")


def test_checkbox_check_uncheck_onchange_and_label_click(engine_page: Page) -> None:
    _mount(engine_page, MOUNT_CHECKBOX_JS)
    box = engine_page.get_by_role("checkbox", name="Enable thing", exact=True)
    box.check()
    box.uncheck()
    engine_page.get_by_text("Enable thing", exact=True).click()  # the label text is the target
    assert engine_page.evaluate("() => window.__cb") == [True, False, True]
    assert box.is_checked()


def test_checkbox_disabled_fires_nothing(engine_page: Page) -> None:
    _mount(
        engine_page,
        """() => {
          window.__cb = [];
          const c = App.ui.checkbox({label: 'Locked', disabled: true, checked: true, testid: 'cb-d',
                                     onChange: (v) => window.__cb.push(v)});
          document.getElementById('harness-root').appendChild(c.el);
          return true;
        }""",
    )
    box = engine_page.get_by_test_id("cb-d")
    assert box.is_disabled()
    box.click(force=True)
    assert engine_page.evaluate("() => window.__cb") == []
    style = engine_page.evaluate(
        "() => { const s = getComputedStyle(document.querySelector('[data-testid=cb-d]')); return [s.opacity, s.cursor]; }"
    )
    assert style == ["0.4", "not-allowed"]


def test_checkbox_indeterminate_wins_until_set_checked(engine_page: Page) -> None:
    _mount(
        engine_page,
        """() => {
          const c = App.ui.checkbox({label: 'Mixed', checked: true, indeterminate: true, testid: 'cb-i'});
          window.__c = c;
          document.getElementById('harness-root').appendChild(c.el);
          return true;
        }""",
    )

    def dash():
        return engine_page.evaluate(
            """() => { const s = getComputedStyle(window.__c.control, '::after');
                      return {ind: window.__c.control.indeterminate, checked: window.__c.control.checked,
                              h: s.height, bw: s.borderBottomWidth, w: s.width}; }"""
        )

    d = dash()
    assert d["ind"] is True and d["checked"] is True
    assert d["h"] == "0px" and d["bw"] == "2px" and d["w"] == "9px"  # the dash, not the tick
    engine_page.evaluate("() => window.__c.setChecked(true)")
    d = dash()
    assert d["ind"] is False and d["checked"] is True
    assert d["h"] == "9px"  # the tick
    engine_page.evaluate("() => window.__c.setIndeterminate(true)")
    assert dash()["h"] == "0px"
    engine_page.evaluate("() => window.__c.setChecked(false)")
    assert dash()["ind"] is False


# ── toggle ──────────────────────────────────────────────────────────────────

MOUNT_TOGGLE_JS = """() => {
  window.__tg = [];
  const t = App.ui.toggle({label: 'Auto save', hint: 'Saves as you type', testid: 'tg-1',
                           onChange: (v) => window.__tg.push(v)});
  window.__t = t;
  document.getElementById('harness-root').appendChild(t.el);
  return true;
}"""


def test_toggle_structure_role_and_hidden_input(engine_page: Page) -> None:
    _mount(engine_page, MOUNT_TOGGLE_JS)
    out = engine_page.evaluate(
        """() => {
          const t = window.__t; const root = t.el; const label = root.querySelector('label');
          const input = t.control; const track = label.querySelector('.ui-toggle-track'); const hint = root.querySelector('.field-hint');
          const s = getComputedStyle(input);
          return {rootCls: root.className, labelCls: label.className, role: input.getAttribute('role'),
                  type: input.type, inLabel: input.parentElement === label, trackHidden: track.getAttribute('aria-hidden'),
                  tid: input.getAttribute('data-testid'), own: input.getAttribute('data-ui-own-label'),
                  hintSibling: label.nextElementSibling === hint && !label.contains(hint),
                  desc: input.getAttribute('aria-describedby') === hint.id,
                  width: s.width, display: s.display, ctl: Object.keys(t).sort()};
        }"""
    )
    assert out == {
        "rootCls": "ui-toggle", "labelCls": "ui-toggle-label", "role": "switch", "type": "checkbox",
        "inLabel": True, "trackHidden": "true", "tid": "tg-1", "own": "true", "hintSibling": True,
        "desc": True, "width": "1px", "display": "block",
        "ctl": ["control", "el", "setChecked"],
    }  # fmt: skip
    sw = engine_page.get_by_role("switch", name="Auto save", exact=True)
    expect(sw).to_have_count(1)
    assert_controls_labelled_and_described(engine_page, "#harness-root")


def test_toggle_space_click_track_and_hint(engine_page: Page) -> None:
    _mount(engine_page, MOUNT_TOGGLE_JS)
    p = engine_page
    sw = p.get_by_role("switch", name="Auto save", exact=True)
    sw.focus()
    p.keyboard.press("Space")
    assert sw.is_checked()
    p.keyboard.press("Space")
    assert not sw.is_checked()
    p.locator(".ui-toggle-track").click()  # the track sits inside the label
    assert sw.is_checked()
    p.get_by_text("Saves as you type").click()  # the hint is outside the label
    assert sw.is_checked()
    p.get_by_text("Auto save", exact=True).click()
    assert not sw.is_checked()
    assert p.evaluate("() => window.__tg") == [True, False, True, False]
    p.evaluate("() => window.__t.setChecked(true)")
    assert sw.is_checked()
    assert p.evaluate("() => window.__tg") == [True, False, True, False]  # setChecked is silent


def test_toggle_disabled_label_hidden_and_colors(engine_page: Page) -> None:
    _mount(
        engine_page,
        """() => {
          window.__tg = [];
          const root = document.getElementById('harness-root');
          const d = App.ui.toggle({label: 'Locked', disabled: true, testid: 'tg-d', onChange: (v) => window.__tg.push(v)});
          const h = App.ui.toggle({label: 'Quiet', labelHidden: true, testid: 'tg-h'});
          root.appendChild(d.el); root.appendChild(h.el);
          window.__h = h;
          return true;
        }""",
    )
    p = engine_page
    d = p.get_by_test_id("tg-d")
    assert d.is_disabled()
    d.focus()
    p.keyboard.press("Space")
    assert p.evaluate("() => window.__tg") == []
    # a hidden label still names the switch
    assert p.get_by_role("switch", name="Quiet", exact=True).count() == 1
    assert (
        p.evaluate("() => window.__h.el.querySelector('span:not(.ui-toggle-track)').className")
        == "visually-hidden"
    )

    def track_bg():
        return p.evaluate(
            "() => getComputedStyle(window.__h.el.querySelector('.ui-toggle-track')).backgroundColor"
        )

    off = track_bg()
    expected = p.evaluate(
        """() => { const probe = document.createElement('i');
                  document.getElementById('harness-root').appendChild(probe);
                  probe.style.color = 'var(--accent-fill)'; return getComputedStyle(probe).color; }"""
    )
    assert off != expected
    p.evaluate("() => window.__h.setChecked(true)")
    # the track colour transitions (motion tokens), so wait for it to settle
    p.wait_for_function(
        "(want) => getComputedStyle(window.__h.el.querySelector('.ui-toggle-track')).backgroundColor === want",
        arg=expected,
    )
    assert track_bg() == expected


# ── badge ───────────────────────────────────────────────────────────────────


def test_badge_kinds_text_and_throws(engine_page: Page) -> None:
    _load(engine_page)
    out = engine_page.evaluate(
        """() => {
          const b = App.ui.badge({text: '<i>x</i> & y', kind: 'ollama', title: 'T', testid: 'bd-1'});
          const n = App.ui.badge({text: 'plain'});
          const all = App.ui.badge.KINDS.map((k) => App.ui.badge({text: k, kind: k}).className);
          return {cls: b.className, tag: b.tagName, text: b.textContent, italic: !!b.querySelector('i'),
                  title: b.title, tid: b.getAttribute('data-testid'), neutral: n.className,
                  kinds: App.ui.badge.KINDS.length, all: all.every((c, i) => c === 'badge badge--' + App.ui.badge.KINDS[i])};
        }"""
    )
    assert out == {
        "cls": "badge badge--ollama", "tag": "SPAN", "text": "<i>x</i> & y", "italic": False,
        "title": "T", "tid": "bd-1", "neutral": "badge", "kinds": 14, "all": True,
    }  # fmt: skip
    assert "unknown kind" in _throws(engine_page, "App.ui.badge({text: 'x', kind: 'nope'})")
    assert "text is required" in _throws(engine_page, "App.ui.badge({kind: 'web'})")
    assert "text is required" in _throws(engine_page, "App.ui.badge({text: ''})")


def test_badge_kind_colors_resolve_per_kind(engine_page: Page) -> None:
    _mount(
        engine_page,
        """() => { const root = document.getElementById('harness-root');
                   App.ui.badge.KINDS.forEach((k) => root.appendChild(App.ui.badge({text: k, kind: k}))); return true; }""",
    )
    bgs = engine_page.evaluate(
        "() => Array.from(document.querySelectorAll('#harness-root .badge')).map((b) => getComputedStyle(b).backgroundColor)"
    )
    assert all(bg not in ("rgba(0, 0, 0, 0)", "") for bg in bgs)
    assert len(set(bgs)) >= 5  # distinct brand fills, not one fallback


# ── emptyState ──────────────────────────────────────────────────────────────


def test_empty_state_inline_structure(engine_page: Page) -> None:
    _mount(
        engine_page,
        """() => {
          const act = App.ui.button({label: 'Create', variant: 'primary'});
          const e = App.ui.emptyState({title: 'Nothing yet', body: 'Make one', action: act, icon: 'plus',
                                       headingLevel: 4, role: 'status', testid: 'es-1'});
          document.getElementById('harness-root').appendChild(e);
          return true;
        }""",
    )
    out = engine_page.evaluate(
        """() => { const e = document.querySelector('[data-testid=es-1]');
          return {cls: e.className, role: e.getAttribute('role'), h: e.querySelector('.ui-empty-title').tagName,
                  title: e.querySelector('.ui-empty-title').textContent, body: e.querySelector('p').textContent,
                  icon: !!e.querySelector('svg[aria-hidden=true]'), btn: !!e.querySelector('button'),
                  cta: e.querySelector('button').classList.contains('empty-canvas-cta')}; }"""
    )
    assert out == {
        "cls": "empty-state", "role": "status", "h": "H4", "title": "Nothing yet", "body": "Make one",
        "icon": True, "btn": True, "cta": False,
    }  # fmt: skip
    assert engine_page.get_by_role("heading", name="Nothing yet", level=4).count() == 1


def test_empty_state_pane_structure_and_defaults(engine_page: Page) -> None:
    _mount(
        engine_page,
        """() => {
          const act = App.ui.button({label: 'Create', variant: 'primary'});
          const e = App.ui.emptyState({title: 'Empty pane', size: 'pane', action: act, testid: 'es-p'});
          const d = App.ui.emptyState({title: 'Defaults'});
          const root = document.getElementById('harness-root'); root.appendChild(e); root.appendChild(d);
          return true;
        }""",
    )
    out = engine_page.evaluate(
        """() => { const e = document.querySelector('[data-testid=es-p]'); const b = e.querySelector('button');
          const d = document.querySelectorAll('#harness-root > *')[1];
          return {cls: e.className, inner: e.firstElementChild.className, innerHas: !!e.querySelector('.empty-canvas-inner > .ui-empty-title'),
                  btn: b.className, role: e.hasAttribute('role'), defH: d.querySelector('.ui-empty-title').tagName,
                  defRole: d.hasAttribute('role')}; }"""
    )
    assert out["cls"] == "empty-canvas" and out["inner"] == "empty-canvas-inner" and out["innerHas"]
    assert (
        "btn-filled-primary" in out["btn"] and "empty-canvas-cta" in out["btn"]
    )  # own classes kept
    assert out["role"] is False and out["defH"] == "H3" and out["defRole"] is False
    assert "title is required" in _throws(engine_page, "App.ui.emptyState({})")
    assert "unknown size" in _throws(engine_page, "App.ui.emptyState({title: 'x', size: 'huge'})")
    assert "headingLevel" in _throws(
        engine_page, "App.ui.emptyState({title: 'x', headingLevel: 7})"
    )


# ── field around every control ──────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["textarea", "select"])
def test_field_wires_textarea_and_select(engine_page: Page, kind: str) -> None:
    ctor = (
        "App.ui.textarea({testid: 'ctl'})"
        if kind == "textarea"
        else "App.ui.select({testid: 'ctl', options: [{value: 'a', label: 'A'}, {value: 'b', label: 'B'}]})"
    )
    _mount(
        engine_page,
        f"""() => {{
          const f = App.ui.field({{label: 'Thing', control: {ctor}, hint: 'A hint', error: 'Bad value'}});
          window.__f = f; document.getElementById('harness-root').appendChild(f.el); return true;
        }}""",
    )
    p = engine_page
    out = p.evaluate(
        """() => { const f = window.__f; const c = f.control; const label = f.el.querySelector('label');
          const hint = f.el.querySelector('.field-hint'); const err = f.el.querySelector('.field-error');
          return {forOk: label.htmlFor === c.id, desc: c.getAttribute('aria-describedby') === hint.id + ' ' + err.id,
                  invalid: c.getAttribute('aria-invalid'), cls: c.classList.contains('is-invalid'), role: err.getAttribute('role')}; }"""
    )
    assert out == {"forOk": True, "desc": True, "invalid": "true", "cls": True, "role": "alert"}
    role = "textbox" if kind == "textarea" else "combobox"
    expect(p.get_by_role(role, name="Thing", exact=True)).to_have_count(1)
    p.evaluate("() => window.__f.setError(null)")
    desc = p.evaluate(
        "() => window.__f.control.getAttribute('aria-describedby') === window.__f.el.querySelector('.field-hint').id"
    )
    assert desc is True
    assert p.evaluate("() => window.__f.control.hasAttribute('aria-invalid')") is False
    assert_controls_labelled_and_described(p, "#harness-root")


def test_field_refuses_checkbox_and_toggle_accepts_bare_checkbox(engine_page: Page) -> None:
    _load(engine_page)
    msg = "checkbox/toggle carry their own label"
    for ctor in ("App.ui.checkbox({label: 'x'})", "App.ui.toggle({label: 'x'})"):
        assert msg in _throws(
            engine_page, f"var c = {ctor}; App.ui.field({{label: 'L', control: c.control}})"
        )
        assert msg in _throws(
            engine_page, f"var c = {ctor}; App.ui.field({{label: 'L', control: c.el}})"
        )
    ok = engine_page.evaluate(
        """() => { const bare = document.createElement('input'); bare.type = 'checkbox';
                   const f = App.ui.field({label: 'Bare', control: bare, hint: 'h'});
                   document.getElementById('harness-root').appendChild(f.el);
                   return {forOk: f.el.querySelector('label').htmlFor === bare.id, desc: bare.hasAttribute('aria-describedby')}; }"""
    )
    assert ok == {"forOk": True, "desc": True}
    # a non-checkbox input without the marker is accepted too
    assert engine_page.evaluate(
        "() => !!App.ui.field({label: 'T', control: App.ui.textInput({})}).el"
    )


# ── keyboard + visible focus ────────────────────────────────────────────────

MOUNT_TAB_JS = """() => {
  const root = document.getElementById('harness-root');
  const start = document.createElement('button'); start.id = 'tab-start'; start.textContent = 'start';
  root.appendChild(start);
  const t = App.ui.textarea({testid: 'k-textarea'});
  const s = App.ui.select({testid: 'k-select', options: [{value: 'a', label: 'A'}]});
  const c = App.ui.checkbox({label: 'Check me', testid: 'k-checkbox'});
  const g = App.ui.toggle({label: 'Switch me', testid: 'k-toggle'});
  [t, s, c.el, g.el].forEach((n) => root.appendChild(n));
  return true;
}"""


@pytest.mark.parametrize("tid", ["k-textarea", "k-select", "k-checkbox", "k-toggle"])
def test_tab_reaches_control_with_visible_focus_indicator(engine_page: Page, tid: str) -> None:
    _mount(engine_page, MOUNT_TAB_JS)
    p = engine_page
    order = ["tab-start", "k-textarea", "k-select", "k-checkbox", "k-toggle"]
    p.focus("#tab-start")
    # Positive control: a real Tab moves focus off the start button in this engine.
    p.keyboard.press("Tab")
    first = p.evaluate(
        "() => document.activeElement.id || document.activeElement.getAttribute('data-testid')"
    )
    assert first != "tab-start", "Tab did not move focus in this engine"
    for _ in range(order.index(tid) - 1):
        p.keyboard.press("Tab")
    info = p.evaluate(
        """(tid) => { const el = document.activeElement;
          const own = el.getAttribute('data-testid');
          const target = own === 'k-toggle' ? el.parentElement.querySelector('.ui-toggle-track') : el;
          const s = getComputedStyle(target);
          return {own, focusVisible: el.matches(':focus-visible'), outlineStyle: s.outlineStyle,
                  outlineWidth: parseFloat(s.outlineWidth), shadow: s.boxShadow}; }""",
        tid,
    )
    assert info["own"] == tid
    assert info["focusVisible"] is True
    assert info["outlineStyle"] != "none"
    assert info["outlineWidth"] >= 2


def test_tab_order_and_labelled_mount_of_every_factory(engine_page: Page) -> None:
    _mount(
        engine_page,
        MOUNT_TAB_JS.replace(
            "return true;",
            """
  root.appendChild(App.ui.badge({text: 'ollama', kind: 'ollama'}));
  root.appendChild(App.ui.emptyState({title: 'Empty', body: 'Nothing here'}));
  root.appendChild(App.ui.field({label: 'Notes', control: App.ui.textarea({}), hint: 'h'}).el);
  root.appendChild(App.ui.field({label: 'Mode', control: App.ui.select({options: [{value: 'a', label: 'A'}]})}).el);
  return true;""",
        ),
    )
    # the first four controls have no accessible name of their own besides the
    # label/aria-label supplied by the factories where applicable: give the bare
    # textarea/select an aria-label so the shared mount is fully named.
    engine_page.evaluate(
        "() => { document.querySelector('[data-testid=k-textarea]').setAttribute('aria-label', 'Bare textarea');"
        " document.querySelector('[data-testid=k-select]').setAttribute('aria-label', 'Bare select'); }"
    )
    assert_controls_labelled_and_described(engine_page, "#harness-root")


# ── listPane hardening ──────────────────────────────────────────────────────

MOUNT_PANE_JS = """() => {
  const c = App.ui.listPane({
    title: 'Providers', testid: 'lp-root', emptyText: 'No providers match',
    filter: {label: 'Filter providers', placeholder: 'Filter', testid: 'lp-filter'},
    selectedId: 'b', density: DENSITY,
    items: [
      {id: 'a', label: 'Alpha', meta: 'first', onSelect: () => {}, badges: [{text: 'ollama', kind: 'ollama'}, 'plain', {text: 'neutral'}], count: 12, testid: 'row-a'},
      {id: 'b', label: 'Beta', meta: 'second', href: '#b', badges: ['tag'], count: 3, testid: 'row-b'},
    ],
  });
  window.__pane = c; document.getElementById('harness-root').appendChild(c.el); return true;
}"""


def _pane(page: Page, density: str = "regular", theme: str = "dark") -> None:
    _load(page, theme)
    page.evaluate(MOUNT_PANE_JS.replace("DENSITY", repr(density)))


def test_list_pane_empty_is_an_empty_state_and_badges_count(engine_page: Page) -> None:
    _pane(engine_page)
    out = engine_page.evaluate(
        """() => { const e = document.querySelector('.ui-list-pane-empty'); const rows = document.querySelectorAll('.ui-list-pane-row');
          return {emptyCls: e.className, role: e.getAttribute('role'), hidden: e.hidden, title: e.querySelector('.ui-empty-title').textContent,
                  a: Array.from(rows[0].querySelectorAll('.ui-list-pane-badges > *')).map((n) => n.className + '|' + n.textContent),
                  aCount: rows[0].querySelector('.ui-list-pane-count').textContent,
                  bCountLast: rows[1].lastElementChild.className, tidRow: rows[0].getAttribute('data-testid')}; }"""
    )
    assert out["emptyCls"] == "empty-state ui-list-pane-empty"
    assert out["role"] is None and out["hidden"] is True
    assert out["title"] == "No providers match"
    assert out["a"] == [
        "badge badge--ollama|ollama",
        "ui-list-pane-badge|plain",
        "ui-list-pane-badge|neutral",
    ]
    assert out["aCount"] == "12" and out["bCountLast"] == "ui-list-pane-count"
    engine_page.get_by_test_id("lp-filter").fill("zzz")
    expect(engine_page.locator(".ui-list-pane-empty")).to_be_visible()
    expect(engine_page.locator(".ui-list-pane-empty .ui-empty-title")).to_have_text(
        "No providers match"
    )
    assert_controls_labelled_and_described(engine_page, "#harness-root")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_list_pane_selected_row_secondary_ink(engine_page: Page, theme: str) -> None:
    _pane(engine_page, theme=theme)
    out = engine_page.evaluate(
        """() => {
          const probe = (v) => { const i = document.createElement('i'); document.getElementById('harness-root').appendChild(i);
                                 i.style.color = v; return getComputedStyle(i).color; };
          const col = (sel) => getComputedStyle(document.querySelector(sel)).color;
          return {secondary: probe('var(--fg-secondary)'), muted: probe('var(--fg-muted)'),
                  selMeta: col('[data-testid=row-b] .ui-list-pane-meta'), selBadge: col('[data-testid=row-b] .ui-list-pane-badge'),
                  selCount: col('[data-testid=row-b] .ui-list-pane-count'),
                  idleMeta: col('[data-testid=row-a] .ui-list-pane-meta'), idleBadge: col('[data-testid=row-a] .ui-list-pane-badge'),
                  idleCount: col('[data-testid=row-a] .ui-list-pane-count')}; }"""
    )
    assert out["secondary"] != out["muted"]
    for key in ("selMeta", "selBadge", "selCount"):
        assert out[key] == out["secondary"], key
    for key in ("idleMeta", "idleBadge", "idleCount"):
        assert out[key] == out["muted"], key


def test_list_pane_regular_and_compact_density_computed(engine_page: Page) -> None:
    _pane(engine_page, "regular")
    reg = engine_page.evaluate(
        """() => { const r = getComputedStyle(document.querySelector('.ui-list-pane-row'));
                   const l = getComputedStyle(document.querySelector('.ui-list-pane-list'));
                   return {pad: [r.paddingTop, r.paddingRight, r.paddingBottom, r.paddingLeft], gap: l.rowGap}; }"""
    )
    assert reg == {"pad": ["8px", "10px", "8px", "10px"], "gap": "2px"}
    _pane(engine_page, "compact")
    pad = engine_page.evaluate(
        "() => { const r = getComputedStyle(document.querySelector('.ui-list-pane-row')); return [r.paddingTop, r.paddingLeft]; }"
    )
    assert pad == ["6px", "10px"]


def test_list_pane_live_region_announces_filter_results(engine_page: Page) -> None:
    _pane(engine_page)
    live = engine_page.locator(".ui-list-pane-status")
    assert live.get_attribute("aria-live") == "polite" and live.get_attribute("role") == "status"
    assert live.evaluate("(n) => !n.hidden && !n.closest('[hidden]')")
    expect(live).to_have_text("")
    flt = engine_page.get_by_test_id("lp-filter")
    flt.fill("zzz")
    expect(live).to_have_text("No providers match")
    flt.fill("")
    expect(live).to_have_text("")
    total = engine_page.locator(".ui-list-pane-row").count()
    row_text = engine_page.locator(".ui-list-pane-label").first.text_content()
    flt.fill(row_text)
    n = engine_page.locator("li:not([hidden]) > .ui-list-pane-row").count()
    expect(live).to_have_text("1 result" if n == 1 else f"{n} results")
    assert 0 < n <= total
    assert live.evaluate("(n) => !n.hidden")


def test_forced_colors_keep_state_distinguishable(engine_page: Page) -> None:
    if engine_page.context.browser.browser_type.name != "chromium":
        pytest.skip(
            "WebKit has no forced-colors emulation in Playwright; asserted in chromium only"
        )
    _pane(engine_page)
    engine_page.emulate_media(forced_colors="active")
    out = engine_page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          const on = App.ui.toggle({label: 'On', checked: true});
          const off = App.ui.toggle({label: 'Off', checked: false});
          root.appendChild(on.el); root.appendChild(off.el);
          const sig = (el) => { const t = getComputedStyle(el.querySelector('.ui-toggle-track'));
            return [t.borderTopStyle, t.borderTopColor, t.backgroundColor].join('|'); };
          const row = getComputedStyle(document.querySelector('.ui-list-pane-row[aria-current=page]'));
          return {on: sig(on.el), off: sig(off.el), rowBorder: row.borderTopStyle, rowOutline: row.outlineStyle};
        }"""
    )
    assert out["on"].startswith("solid|") and out["off"].startswith("solid|")
    assert out["on"] != out["off"]
    assert out["rowBorder"] != "none" or out["rowOutline"] != "none"

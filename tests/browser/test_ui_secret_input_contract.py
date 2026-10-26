# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.secretInput`` (M31 F1 L7, DD9) and the
``field`` / ``dangerZone`` handles the provider editor needed: ``field`` ``host``, ``hintTestid``
and ``setLabel``, and ``dangerZone``'s ``beforeArm`` gate.

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SECRET = "sk-test-SECRET-value-123"


def _mount(page: Page, js: str):
    load_harness(page)
    return page.evaluate(js)


def test_secret_input_dom_and_names(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const s = App.ui.secretInput({id: 'k', placeholder: 'sk-...', dataset: {field: 'api_key'}, testid: 'key', revealTestid: 'eye'});
          document.getElementById('harness-root').appendChild(s.el);
          return {wrap: s.el.className, kids: Array.from(s.el.children).map((k) => k.tagName),
                  input: [s.input.className, s.input.type, s.input.id, s.input.getAttribute('autocomplete'),
                          s.input.dataset.field, s.input.getAttribute('data-testid'), s.input.placeholder],
                  wrapField: s.el.dataset.field === undefined,
                  btn: [s.button.className, s.button.type, s.button.getAttribute('aria-label'),
                        s.button.getAttribute('aria-pressed'), s.button.getAttribute('data-testid'),
                        s.button.getAttribute('title')],
                  svg: s.button.querySelectorAll('svg.ui-icon').length};
        }""",
    )
    assert out == {
        "wrap": "api-key-wrap", "kids": ["INPUT", "BUTTON"],
        "input": ["field-input", "password", "k", "new-password", "api_key", "key", "sk-..."],
        "wrapField": True,
        "btn": ["api-key-eye", "button", "Show password", "false", "eye", None],
        "svg": 1,
    }  # fmt: skip
    expect(engine_page.get_by_role("button", name="Show password")).to_have_count(1)


def test_secret_input_toggle_keeps_focus_and_flips_only_the_type(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        """() => {
          window.__s = App.ui.secretInput({id: 'k', value: 'abc'});
          document.getElementById('harness-root').appendChild(window.__s.el);
        }""",
    )
    btn = page.get_by_role("button", name="Show password")
    btn.focus()
    page.keyboard.press("Enter")
    state = page.evaluate(
        """() => ({type: __s.input.type, aria: __s.button.getAttribute('aria-label'), pressed: __s.button.getAttribute('aria-pressed'),
                   focus: document.activeElement === __s.button, value: __s.input.value, attrValue: __s.input.getAttribute('value'),
                   icon: __s.button.querySelectorAll('svg').length})"""
    )
    assert state == {
        "type": "text", "aria": "Hide password", "pressed": "true", "focus": True,
        "value": "abc", "attrValue": None, "icon": 1,
    }  # fmt: skip
    expect(page.get_by_role("button", name="Hide password")).to_have_attribute(
        "aria-pressed", "true"
    )
    page.keyboard.press("Space")
    assert page.evaluate("() => [__s.input.type, __s.button.getAttribute('aria-pressed')]") == [
        "password", "false",
    ]  # fmt: skip


def test_secret_input_set_value_hides_and_never_writes_an_attribute(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        f"""() => {{
          window.__s = App.ui.secretInput({{id: 'k', label: 'Token', value: '{SECRET}', testid: 'key'}});
          document.getElementById('harness-root').appendChild(window.__s.el);
        }}""",
    )

    def leaks() -> list[str]:
        return page.evaluate(
            """(secret) => {
              const bad = [];
              for (const node of [__s.el, __s.input, __s.button, ...__s.el.querySelectorAll('*')]) {
                for (const a of Array.from(node.attributes)) if (a.value.includes(secret)) bad.push(node.tagName + '@' + a.name);
              }
              return bad;
            }""",
            SECRET,
        )

    assert page.evaluate("() => __s.input.value") == SECRET
    assert leaks() == []
    page.evaluate("() => __s.setRevealed(true)")
    assert leaks() == []
    page.evaluate("(v) => __s.setValue(v)", SECRET + "-2")
    assert page.evaluate("() => [__s.input.value, __s.input.type, __s.button.getAttribute('aria-pressed')]") == [
        SECRET + "-2", "password", "false",
    ]  # fmt: skip
    assert leaks() == []
    # An accessible name for a field with no visible label comes from the label option.
    assert page.evaluate("() => __s.input.getAttribute('aria-label')") == "Token"


def test_field_host_places_the_wrapper_and_keeps_the_label_on_the_input(engine_page: Page) -> None:
    page = engine_page
    out = _mount(
        page,
        """() => {
          const s = App.ui.secretInput({id: 'pf-key'});
          const f = App.ui.field({label: 'API Key', control: s.input, host: s.el, hint: 'Help', hintTestid: 'key-help', testid: 'row'});
          document.getElementById('harness-root').appendChild(f.el);
          const label = f.el.querySelector('label');
          const first = {kids: Array.from(f.el.children).map((k) => k.tagName + '.' + k.className),
                         forId: label.htmlFor, described: s.input.getAttribute('aria-describedby'),
                         hintTid: f.el.querySelector('.field-hint').getAttribute('data-testid'),
                         hintId: f.el.querySelector('.field-hint').id};
          f.setLabel('Token');
          f.setHint(null);
          f.setHint('Again');
          return Object.assign(first, {label: label.textContent, labelAfter: f.el.querySelector('label') === label,
                 describedAfter: s.input.getAttribute('aria-describedby') === f.el.querySelector('.field-hint').id,
                 hintTidAfter: f.el.querySelector('.field-hint').getAttribute('data-testid')});
        }""",
    )
    assert out["kids"] == ["LABEL.", "DIV.api-key-wrap", "DIV.field-hint"]
    assert out["forId"] == "pf-key"
    assert out["described"] == out["hintId"]
    assert out["hintTid"] == "key-help"
    assert out["label"] == "Token"
    assert out["labelAfter"] is True
    assert out["describedAfter"] is True
    assert out["hintTidAfter"] == "key-help"
    expect(page.get_by_label("Token")).to_have_count(1)


def test_danger_zone_before_arm_gates_the_first_click_only(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.__log = [];
          window.__allow = false;
          window.__proceed = null;
          window.__z = App.ui.dangerZone({
            action: {label: 'Delete Provider', testid: 'del', revertMs: 5000,
                     beforeArm: (proceed) => { __log.push('gate'); __proceed = proceed; if (__allow) proceed(); },
                     onConfirm: () => __log.push('commit')}
          });
          document.getElementById('harness-root').appendChild(__z.el);
        }"""
    )
    btn = page.get_by_test_id("del")
    btn.click()
    assert page.evaluate(
        "() => [__log.slice(), __z.button.classList.contains('confirm-delete')]"
    ) == [["gate"], False]
    page.evaluate("() => { __allow = true; }")
    btn.click()
    assert page.evaluate(
        "() => [__log.slice(), __z.button.classList.contains('confirm-delete')]"
    ) == [["gate", "gate"], True]
    btn.click()
    assert page.evaluate("() => __log.slice()") == ["gate", "gate", "commit"]


def test_field_info_alone_is_wired_into_aria_describedby(engine_page: Page) -> None:
    """Leg 07 fix: an `info` description with no hint or error still reaches the control's
    aria-describedby at construction (it used to appear only after a hint or error)."""
    out = _mount(
        engine_page,
        """() => {
          const c = App.ui.textInput({id: 'n'});
          const f = App.ui.field({label: 'Context Window', control: c, info: 'Longer chats, slower'});
          document.getElementById('harness-root').appendChild(f.el);
          const ids = (c.getAttribute('aria-describedby') || '').split(' ').filter(Boolean);
          return {n: ids.length, text: ids.length ? document.getElementById(ids[0]).textContent : null};
        }""",
    )
    assert out == {"n": 1, "text": "Longer chats, slower"}


def test_field_error_testid(engine_page: Page) -> None:
    """M31 F3 L03b: `errorTestid` lands on the error node `setError` creates."""
    out = _mount(
        engine_page,
        """() => {
          const i = App.ui.textInput({});
          const f = App.ui.field({label: 'Name', control: i, hint: 'h', errorTestid: 'name-err'});
          const g = App.ui.field({label: 'Other', control: App.ui.textInput({})});
          document.getElementById('harness-root').append(f.el, g.el);
          const before = f.el.querySelector('[data-testid="name-err"]');
          f.setError('Required'); g.setError('Bad');
          const el = f.el.querySelector('[data-testid="name-err"]');
          f.setError('Still'); const same = f.el.querySelector('[data-testid="name-err"]') === el;
          return {before, text: el.textContent, role: el.getAttribute('role'), same,
                  plain: g.el.querySelector('.field-error').getAttribute('data-testid')};
        }""",
    )
    assert out == {"before": None, "text": "Still", "role": "alert", "same": True, "plain": None}


# --- stored mode, label options and the describedby helpers (M31 F5 L04) ---


def test_secret_input_defaults_unchanged_and_label_options(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const d = App.ui.secretInput({value: 'abc'});
          const s = App.ui.secretInput({showLabel: 'Show value, row 3', hideLabel: 'Hide value, row 3'});
          document.getElementById('harness-root').append(d.el, s.el);
          const before = s.button.getAttribute('aria-label');
          s.setRevealed(true);
          const mid = s.button.getAttribute('aria-label');
          s.setLabels('Show value, row 4', 'Hide value, row 4');
          const after = s.button.getAttribute('aria-label');
          s.setRevealed(false);
          return {d: [d.button.getAttribute('aria-label'), d.hintEl, d.el.children.length, d.button.hidden, d.input.hasAttribute('aria-describedby')],
                  s: [before, mid, after, s.button.getAttribute('aria-label')]};
        }""",
    )
    assert out["d"] == ["Show password", None, 2, False, False]
    assert out["s"] == [
        "Show value, row 3",
        "Hide value, row 3",
        "Hide value, row 4",
        "Show value, row 4",
    ]


def test_secret_input_stored_mode_state_and_set_stored(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const s = App.ui.secretInput({value: '***abcd', stored: '***abcd'});
          const wrap = document.createElement('div'); wrap.append(s.el, s.hintEl);
          document.getElementById('harness-root').append(wrap);
          const st = () => [s.button.hidden, (s.hintEl.textContent === ''), s.hintEl.textContent, s.input.getAttribute('aria-describedby') === s.hintEl.id];
          const a = st();
          s.setValue('other');
          const b = [s.button.hidden, (s.hintEl.textContent === ''), s.input.hasAttribute('aria-describedby')];
          s.setStored('other');
          const c = [s.button.hidden, (s.hintEl.textContent === '')];
          s.setStored(null);
          const d = [s.button.hidden, (s.hintEl.textContent === '')];
          s.setStored('');
          return {a, b, c, d, cls: s.hintEl.className, live: s.hintEl.getAttribute('aria-live'), wrapKids: s.el.className + ':' + s.el.children.length};
        }""",
    )
    assert out["a"] == [True, False, "Stored. Type a new value to replace it.", True]
    assert (
        out["b"] == [False, True, False] and out["c"] == [True, False] and out["d"] == [False, True]
    )
    assert (
        out["cls"] == "ui-secret-hint"
        and out["live"] == "polite"
        and out["wrapKids"] == "api-key-wrap:2"
    )


def test_secret_input_set_hint_is_cleared_by_typing(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        """() => {
          window.__s = App.ui.secretInput({value: 'x'});
          document.getElementById('harness-root').append(__s.el);
          document.getElementById('harness-root').append(__s.setHint('Say it again') || __s.hintEl);
        }""",
    )
    assert page.evaluate(
        "() => [(__s.hintEl.textContent === ''), __s.hintEl.textContent, __s.input.getAttribute('aria-describedby') === __s.hintEl.id]"
    ) == [False, "Say it again", True]
    page.locator("input").first.click()
    page.keyboard.type("y")
    assert page.evaluate(
        "() => [(__s.hintEl.textContent === ''), __s.input.hasAttribute('aria-describedby')]"
    ) == [True, False]


def test_describedby_helpers_treat_the_attribute_as_a_token_list(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => { const u = App.ui.util; const e = document.createElement('input'); const r = [];
          u.addDescribedBy(e, 'a'); r.push(e.getAttribute('aria-describedby'));
          u.addDescribedBy(e, 'b'); u.addDescribedBy(e, 'a'); r.push(e.getAttribute('aria-describedby'));
          u.removeDescribedBy(e, 'a'); r.push(e.getAttribute('aria-describedby'));
          u.removeDescribedBy(e, 'zz'); r.push(e.getAttribute('aria-describedby'));
          u.removeDescribedBy(e, 'b'); r.push(e.hasAttribute('aria-describedby'));
          return r; }"""
    )
    assert out == ["a", "a b", "b", "b", False]


def test_secret_input_ime_composition_is_not_rewritten_mid_composition(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        """() => {
          window.__s = App.ui.secretInput({value: '***abcd', stored: '***abcd'});
          document.getElementById('harness-root').append(__s.el, __s.hintEl);
          const i = __s.input; i.focus();
          window.__log = [];
          i.addEventListener('input', () => __log.push(i.value));
        }""",
    )
    out = page.evaluate(
        """() => {
          const i = __s.input;
          i.dispatchEvent(new CompositionEvent('compositionstart', {bubbles: true}));
          i.value = '***abcd' + 'ni';
          i.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertCompositionText', isComposing: true}));
          const mid = i.value;
          i.value = '***abcd' + '\u4f60';
          i.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertCompositionText', isComposing: true}));
          const mid2 = i.value;
          i.dispatchEvent(new CompositionEvent('compositionend', {bubbles: true, data: '\u4f60'}));
          return {mid, mid2, end: i.value, btnHidden: __s.button.hidden};
        }"""
    )
    assert out["mid"] == "***abcdni"
    assert out["mid2"] == "***abcd\u4f60"
    assert out["end"] == "\u4f60"
    assert out["btnHidden"] is False


def test_secret_input_hint_stays_in_dom_and_writes_only_on_change(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        """() => {
          window.__s = App.ui.secretInput({value: '***abcd', stored: '***abcd'});
          document.getElementById('harness-root').append(__s.el, __s.hintEl);
          window.__muts = 0;
          new MutationObserver((r) => { __muts += r.length; }).observe(__s.hintEl, {childList: true, characterData: true, subtree: true});
        }""",
    )
    out = page.evaluate(
        """async () => {
          __s.setValue('x'); await Promise.resolve();
          const cleared = [__s.hintEl.isConnected, __s.hintEl.hidden, __s.hintEl.textContent];
          __s.input.value = 'xy'; __s.input.dispatchEvent(new Event('input', {bubbles: true}));
          __s.input.value = 'xyz'; __s.input.dispatchEvent(new Event('input', {bubbles: true}));
          await new Promise((r) => setTimeout(r, 20));
          return {cleared, muts: __muts};
        }"""
    )
    assert out["cleared"] == [True, False, ""]
    assert out["muts"] == 1  # one clear on setValue; keystrokes write nothing


def test_secret_input_moves_focus_off_the_eye_when_stored_mode_is_reentered(
    engine_page: Page,
) -> None:
    page = engine_page
    _mount(
        page,
        """() => {
          window.__s = App.ui.secretInput({value: 'x', stored: '***abcd'});
          document.getElementById('harness-root').append(__s.el, __s.hintEl);
          __s.button.focus();
        }""",
    )
    out = page.evaluate(
        """() => { __s.setValue('***abcd');
          return [__s.button.hidden, document.activeElement === __s.input]; }"""
    )
    assert out == [True, True]

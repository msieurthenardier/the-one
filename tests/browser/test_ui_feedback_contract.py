# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for the M31 F1 L5 feedback controls:
``App.ui.status``, ``App.ui.flash``, ``App.ui.progress`` and ``App.ui.chip``.

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _mount(page: Page, js: str):
    load_harness(page)
    return page.evaluate(js)


def test_status_text_mode_dom_and_set(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const s = App.ui.status({state: 'success', text: 'Connected', testid: 'st-1'});
          document.getElementById('harness-root').appendChild(s.el);
          const led = s.el.querySelector('.indicator-led');
          const snap = () => ({root: s.el.tagName + '.' + s.el.className, role: s.el.getAttribute('role'),
            led: led.className, hidden: led.getAttribute('aria-hidden'), ledRole: led.getAttribute('role'),
            text: s.el.textContent, state: s.el.getAttribute('data-state')});
          const first = snap();
          s.set('pending', 'Checking');
          const second = snap();
          s.set('danger', 'Failed');
          const third = snap();
          return {first, second, third, tid: s.el.getAttribute('data-testid'),
                  w: getComputedStyle(led).width, h: getComputedStyle(led).height,
                  glyph: /[\\u2713\\u2717]/.test(s.el.textContent)};
        }""",
    )
    assert out["first"] == {
        "root": "P.ui-status", "role": "status", "led": "indicator-led indicator-led--success",
        "hidden": "true", "ledRole": None, "text": "Connected", "state": "success",
    }  # fmt: skip
    assert out["second"]["led"] == "indicator-led indicator-led--idle"
    assert out["second"]["text"] == "Checking" and out["second"]["state"] == "pending"
    assert out["third"]["led"] == "indicator-led indicator-led--danger"
    assert out["tid"] == "st-1" and out["w"] == "10px" and out["h"] == "10px"
    assert out["glyph"] is False


def test_status_role_option(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const mk = (o) => App.ui.status(Object.assign({state: 'danger', text: 'Bad'}, o)).el;
          let bad = null;
          try { App.ui.status({role: 'banner'}); } catch (e) { bad = e.message; }
          return {dflt: mk({}).getAttribute('role'), alert: mk({role: 'alert'}).getAttribute('role'),
                  status: mk({role: 'status'}).getAttribute('role'),
                  off: mk({role: 'alert', live: 'off'}).getAttribute('role'), bad};
        }""",
    )
    assert out["dflt"] == "status" and out["status"] == "status"
    assert out["alert"] == "alert"
    assert out["off"] is None
    assert "unknown role" in out["bad"]


def test_status_led_false_draws_no_led(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const s = App.ui.status({state: 'danger', text: 'Bad', led: false, role: 'alert', testid: 'st-nl'});
          document.getElementById('harness-root').appendChild(s.el);
          const snap = () => ({leds: s.el.querySelectorAll('.indicator-led').length,
            kids: s.el.children.length, text: s.el.textContent, state: s.el.getAttribute('data-state'),
            role: s.el.getAttribute('role')});
          const first = snap();
          s.set('idle', 'Fine');
          const second = snap();
          s.set('success', '', {ledLabel: 'ok'});
          const third = snap();
          const withLed = App.ui.status({state: 'idle', text: 'x'});
          return {first, second, third, defaultLeds: withLed.el.querySelectorAll('.indicator-led').length};
        }""",
    )
    assert out["first"] == {"leds": 0, "kids": 1, "text": "Bad", "state": "danger", "role": "alert"}
    assert out["second"]["leds"] == 0 and out["second"]["text"] == "Fine"
    assert out["second"]["state"] == "idle"
    assert out["third"]["leds"] == 0 and out["third"]["text"] == ""
    assert out["defaultLeds"] == 1


def test_status_led_only_mode_and_clearing_text(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.s = App.ui.status({state: 'warning', ledLabel: 'Needs attention', live: 'off'});
          document.getElementById('harness-root').appendChild(s.el);
        }"""
    )
    led = page.locator(".ui-status .indicator-led")
    expect(led).to_have_attribute("role", "img")
    expect(led).to_have_attribute("aria-label", "Needs attention")
    assert page.locator(".ui-status").get_attribute("role") is None
    expect(page.get_by_role("img", name="Needs attention")).to_have_count(1)
    page.evaluate("() => s.set('success', 'Ready')")
    expect(led).to_have_attribute("aria-hidden", "true")
    assert led.get_attribute("role") is None and led.get_attribute("aria-label") is None
    page.evaluate("() => s.set('success', '')")
    assert led.get_attribute("aria-hidden") is None
    expect(led).to_have_attribute("role", "img")
    err = page.evaluate(
        "() => { try { s.set('bogus', 'x'); return ''; } catch (e) { return e.message; } }"
    )
    assert "unknown state" in err


def test_status_led_without_label_is_hidden_and_per_call_label(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.s = App.ui.status({state: 'idle', live: 'off'});
          document.getElementById('harness-root').appendChild(s.el);
        }"""
    )
    led = page.locator(".ui-status .indicator-led")
    # No text and no ledLabel: never an unnamed image.
    assert led.get_attribute("role") is None
    expect(led).to_have_attribute("aria-hidden", "true")
    expect(page.get_by_role("img")).to_have_count(0)
    # A per-call label names the LED.
    page.evaluate("() => s.set('success', '', {ledLabel: 'Running'})")
    expect(led).to_have_attribute("role", "img")
    assert led.get_attribute("aria-hidden") is None
    expect(page.get_by_role("img", name="Running")).to_have_count(1)
    page.evaluate("() => s.set('idle', '', {ledLabel: 'Not running'})")
    expect(page.get_by_role("img", name="Not running")).to_have_count(1)
    # Text wins: the LED is decorative again.
    page.evaluate("() => s.set('idle', 'Words', {ledLabel: 'Ignored'})")
    expect(led).to_have_attribute("aria-hidden", "true")
    assert led.get_attribute("role") is None


def test_status_line_style_is_body_small_and_muted(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const s = App.ui.status({state: 'idle', text: 'Not tested'});
          document.getElementById('harness-root').appendChild(s.el);
          const cs = getComputedStyle(s.el);
          const probe = document.createElement('span'); probe.style.fontSize = 'var(--font-size-body-sm)';
          probe.style.color = 'var(--fg-secondary)'; document.getElementById('harness-root').appendChild(probe);
          const pc = getComputedStyle(probe);
          return {size: cs.fontSize === pc.fontSize, color: cs.color === pc.color, display: cs.display};
        }""",
    )
    assert out == {"size": True, "color": True, "display": "flex"}


def test_flash_roles_visible_and_removal(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.ok = App.ui.flash('Saved', {duration: 400});
          window.bad = App.ui.flash('Broke', {error: true, duration: 400});
        }"""
    )
    ok = page.locator(".app-flash:not(.error)")
    bad = page.locator(".app-flash.error")
    expect(ok).to_have_attribute("role", "status")
    expect(ok).to_have_attribute("aria-live", "polite")
    expect(bad).to_have_attribute("role", "alert")
    assert bad.get_attribute("aria-live") is None
    expect(ok).to_have_text("Saved")
    expect(ok).to_have_class("app-flash visible")
    expect(page.locator(".app-flash")).to_have_count(0, timeout=3000)


def test_flash_container_default_and_detached_container(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const a = App.ui.flash('Body');
          const holder = document.createElement('div');
          const b = App.ui.flash('Held', {container: holder, duration: 50});
          return {inBody: a.parentNode === document.body, inHolder: b.parentNode === holder,
                  cls: a.className};
        }""",
    )
    assert out == {"inBody": True, "inHolder": True, "cls": "app-flash"}
    engine_page.wait_for_timeout(600)  # a detached container must not throw on removal


def test_chip_tones_sizes_and_title(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          const a = App.ui.chip({label: 'vision', testid: 'c-a'});
          const b = App.ui.chip({label: 'no tools', tone: 'danger', title: 'Cannot call tools', testid: 'c-b'});
          const c = App.ui.chip({label: 'small', size: 'sm'});
          [a, b, c].forEach((n) => root.appendChild(n));
          const cs = (n) => { const s = getComputedStyle(n); return {pad: s.paddingTop + ' ' + s.paddingLeft, fs: s.fontSize, color: s.color}; };
          let err = '';
          try { App.ui.chip({label: 'x', tone: 'loud'}); } catch (e) { err = e.message; }
          return {a: a.tagName + '.' + a.className, b: b.className, c: c.className, title: b.title, aTitle: a.getAttribute('title'),
                  tid: b.getAttribute('data-testid'), csA: cs(a), csB: cs(b), csC: cs(c), err,
                  removeBtns: root.querySelectorAll('button').length};
        }""",
    )
    assert (
        out["a"] == "SPAN.chip" and out["b"] == "chip chip--danger" and out["c"] == "chip chip--sm"
    )
    assert out["title"] == "Cannot call tools" and out["aTitle"] is None and out["tid"] == "c-b"
    assert out["csA"]["pad"] == "4px 8px" and out["csC"]["pad"] == "2px 8px"
    assert out["csC"]["fs"] != out["csA"]["fs"]
    assert out["csB"]["color"] != out["csA"]["color"]
    assert "unknown tone" in out["err"] and out["removeBtns"] == 0


def test_progress_aria_determinate_and_indeterminate(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const p = App.ui.progress({label: 'Pulling llama', value: 0.25, text: '25%', testid: 'pg'});
          document.getElementById('harness-root').appendChild(p.el);
          const bar = p.bar;
          const snap = () => ({role: bar.getAttribute('role'), now: bar.getAttribute('aria-valuenow'),
            min: bar.getAttribute('aria-valuemin'), max: bar.getAttribute('aria-valuemax'),
            name: bar.getAttribute('aria-label'), vt: bar.getAttribute('aria-valuetext'),
            rootRole: p.el.getAttribute('role'), barIsChildOfRoot: bar.parentNode === p.el, width: p.el.querySelector('.ui-progress-fill').style.width,
            text: p.el.querySelector('.ui-progress-text').textContent,
            indet: p.el.classList.contains('ui-progress--indeterminate'), cancel: p.el.querySelectorAll('button').length});
          const a = snap();
          p.set(null, 'Starting');
          const b = snap();
          p.set(2, 'Done');
          const c = snap();
          return {a, b, c, tid: p.el.getAttribute('data-testid')};
        }""",
    )
    assert out["a"] == {"role": "progressbar", "now": "25", "min": "0", "max": "100", "name": "Pulling llama", "vt": "25%", "rootRole": None, "barIsChildOfRoot": True, "width": "25%", "text": "25%", "indet": False, "cancel": 0}  # fmt: skip
    assert out["b"]["now"] is None and out["b"]["indet"] is True and out["b"]["text"] == "Starting"
    assert out["c"]["now"] == "100" and out["c"]["width"] == "100%" and out["c"]["indet"] is False
    assert out["tid"] == "pg"


def test_progress_cancel_name_callback_and_tab_order(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.calls = 0;
          const root = document.getElementById('harness-root');
          const b = document.createElement('button'); b.textContent = 'before'; root.appendChild(b);
          window.p = App.ui.progress({label: 'Pull', value: 0.5, text: 'half', onCancel: () => { window.calls++; },
            cancelLabel: 'Cancel pull', cancelTestid: 'pg-cancel'});
          root.appendChild(p.el);
        }"""
    )
    cancel = page.get_by_role("button", name="Cancel pull")
    expect(cancel).to_have_count(1)
    expect(cancel).to_have_attribute("data-testid", "pg-cancel")
    # The button is a sibling of the progressbar, never inside it, and is the handle.
    assert page.evaluate(
        """() => ({inside: !!p.bar.querySelector('button') || p.bar.contains(p.cancelButton),
                   handle: p.cancelButton === document.querySelector('[data-testid=pg-cancel]'),
                   sibling: p.cancelButton.parentNode === p.el})"""
    ) == {"inside": False, "handle": True, "sibling": True}
    expect(page.get_by_role("progressbar", name="Pull")).to_have_count(1)
    expect(page.get_by_role("progressbar", name="Pull").get_by_role("button")).to_have_count(0)
    assert page.locator(".ui-progress-cancel svg.ui-icon").count() == 1
    page.get_by_role("button", name="before").focus()
    page.keyboard.press("Tab")
    expect(cancel).to_be_focused()
    page.keyboard.press("Enter")
    assert page.evaluate("() => window.calls") == 1
    page.evaluate("() => p.setCancelDisabled(true)")
    expect(cancel).to_be_disabled()
    page.evaluate("() => p.setCancelDisabled(false)")
    expect(cancel).to_be_enabled()


def test_chip_dataset_and_warning_tone(engine_page: Page) -> None:
    """M31 F3 L03b: `dataset` copies to data-*, `tone: 'warning'` mirrors the danger recipe
    (soft fill, border and text from the gated pair), and an unknown tone still throws."""
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          const a = App.ui.chip({label: 'indexed', dataset: {status: 'indexed', testid: 'ignored'}, testid: 'kb-status-count'});
          const w = App.ui.chip({label: 'standalone', tone: 'warning', size: 'sm'});
          const d = App.ui.chip({label: 'no tools', tone: 'danger'});
          [a, w, d].forEach((n) => root.appendChild(n));
          const probe = document.createElement('span'); probe.style.color = 'var(--status-warning)';
          probe.style.backgroundColor = 'var(--status-warning-bg-soft)'; root.appendChild(probe);
          const pc = getComputedStyle(probe); const cw = getComputedStyle(w); const cd = getComputedStyle(d);
          let err = '';
          try { App.ui.chip({label: 'x', tone: 'loud'}); } catch (e) { err = e.message; }
          return {status: a.getAttribute('data-status'), tid: a.getAttribute('data-testid'), cls: w.className,
                  color: cw.color === pc.color, bg: cw.backgroundColor === pc.backgroundColor,
                  border: cw.borderTopColor === pc.color, cursor: cw.cursor, dangerCursor: cd.cursor,
                  differs: cw.color !== cd.color, err};
        }""",
    )
    assert out["status"] == "indexed" and out["tid"] == "kb-status-count"
    assert out["cls"] == "chip chip--warning chip--sm"
    assert out["color"] and out["bg"] and out["border"] and out["differs"]
    assert out["cursor"] != "help" and out["dangerCursor"] == "help"
    assert "unknown tone" in out["err"]


def test_status_led_testid(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          const s = App.ui.status({text: 'Not connected', state: 'danger', testid: 'a', ledTestid: 'b'});
          const n = App.ui.status({text: 'No LED', state: 'idle', led: false, testid: 'c', ledTestid: 'd'});
          root.appendChild(s.el); root.appendChild(n.el);
          s.set('success', 'Connected');
          const led = s.el.querySelector('.indicator-led');
          return {root: s.el.getAttribute('data-testid'), led: led.getAttribute('data-testid'),
                  state: s.el.getAttribute('data-state'), hidden: led.getAttribute('aria-hidden'),
                  cls: led.className, ignored: n.el.querySelector('[data-testid="d"]') === null,
                  noLed: n.el.querySelector('.indicator-led') === null};
        }""",
    )
    assert out == {
        "root": "a", "led": "b", "state": "success", "hidden": "true",
        "cls": "indicator-led indicator-led--success", "ignored": True, "noLed": True,
    }  # fmt: skip


def test_status_text_tone(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          const col = (v) => { const p = document.createElement('span'); p.style.color = v; root.appendChild(p); return getComputedStyle(p).color; };
          const mk = (o) => { const s = App.ui.status(o); root.appendChild(s.el); return s; };
          const tone = mk({led: false, textTone: true, state: 'danger', text: 'Failed'});
          const plain = mk({led: false, state: 'danger', text: 'Failed'});
          const warn = mk({led: false, textTone: true, state: 'warning', text: 'Careful'});
          const ok = mk({led: false, textTone: true, state: 'success', text: 'Fine'});
          const c = (s) => getComputedStyle(s.el.querySelector('.ui-status-text')).color;
          const before = c(tone);
          tone.set('idle', 'Idle');
          return {tone: before === col('var(--status-danger)'), plain: c(plain) === col('var(--fg-secondary)'),
                  warn: c(warn) === col('var(--status-warning)'), ok: c(ok) === col('var(--fg-secondary)'),
                  idle: c(tone) === col('var(--fg-secondary)')};
        }""",
    )
    assert out == {"tone": True, "plain": True, "warn": True, "ok": True, "idle": True}

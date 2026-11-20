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
    page.evaluate("() => { window.ok = App.ui.flash('Saved', {duration: 400}); }")
    ok = page.locator(".app-flash")
    expect(ok).to_have_attribute("role", "status")
    expect(ok).to_have_attribute("aria-live", "polite")
    expect(ok).to_have_text("Saved")
    expect(ok).to_have_class("app-flash visible")
    expect(page.locator(".app-flash")).to_have_count(0, timeout=3000)


def test_flash_newest_replaces_and_keeps_its_role(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.ok = App.ui.flash('Saved', {duration: 4000});
          window.bad = App.ui.flash('Broke', {error: true, duration: 4000});
        }"""
    )
    toasts = page.locator(".app-flash")
    expect(toasts).to_have_count(1)
    expect(toasts).to_have_text("Broke")
    expect(toasts).to_have_attribute("role", "alert")
    assert toasts.get_attribute("aria-live") is None
    assert page.evaluate("() => ok.isConnected") is False
    # the replaced toast's timers are cleared: it never re-adds itself or removes the new one
    page.wait_for_timeout(500)
    expect(toasts).to_have_count(1)
    expect(toasts).to_have_class("app-flash error visible")


def test_flash_survives_its_caller_container_and_ignores_the_option(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const holder = document.createElement('div');
          document.getElementById('harness-root').appendChild(holder);
          const a = App.ui.flash('Held', {container: holder});
          holder.remove();
          return {connected: a.isConnected, inRegion: a.parentNode.classList.contains('app-flash-region'),
                  regionInBody: a.parentNode.parentNode === document.body};
        }""",
    )
    assert out == {"connected": True, "inRegion": True, "regionInBody": True}
    expect(engine_page.locator(".app-flash")).to_be_visible()


def test_flash_region_is_reattached_when_detached(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const r1 = App.ui.flash.region();
          r1.remove();
          const r2 = App.ui.flash.region();
          const t = App.ui.flash('Again');
          return {same: r1 === r2, attached: r2.isConnected, child: t.parentNode === r2,
                  plain: getComputedStyle(r2).transform === 'none'};
        }""",
    )
    assert out == {"same": True, "attached": True, "child": True, "plain": True}


MODAL_FLASH = """() => {
  window.m = App.ui.modal({title: 'Dlg', body: document.createTextNode('b'),
                           actions: [{label: 'OK', value: 'ok'}]});
  m.open();
}"""


def test_flash_inside_a_modal_sits_in_its_dialog_and_survives_its_close(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(MODAL_FLASH)
    page.evaluate("() => { window.t = App.ui.flash('In dialog'); }")
    assert (
        page.evaluate("() => t.parentNode === App.ui.modal.top() && !!t.closest('dialog')") is True
    )
    expect(page.locator("dialog .app-flash")).to_be_visible()
    page.evaluate("() => m.close()")
    out = page.evaluate(
        "() => ({connected: t.isConnected, inRegion: t.parentNode === App.ui.flash.region()})"
    )
    assert out == {"connected": True, "inRegion": True}
    expect(page.locator(".app-flash")).to_be_visible()


def test_flash_rehomes_to_the_next_dialog_down(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """() => {
          const a = App.ui.modal({title: 'A', body: document.createTextNode('a'), actions: [{label: 'OK', value: 1}]});
          const b = App.ui.modal({title: 'B', body: document.createTextNode('b'), actions: [{label: 'OK', value: 1}]});
          a.open(); const dlgA = App.ui.modal.top(); b.open();
          const t = App.ui.flash('Up top');
          const inB = t.parentNode === App.ui.modal.top() && t.parentNode !== dlgA;
          b.close();
          return {inB, inA: t.parentNode === dlgA, connected: t.isConnected,
                  topNull: (a.close(), App.ui.modal.top() === null)};
        }"""
    )
    assert out == {"inB": True, "inA": True, "connected": True, "topNull": True}


def test_flash_in_a_modal_is_at_the_same_viewport_position(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate("() => { App.ui.flash('Page'); }")
    expect(page.locator(".app-flash.visible")).to_be_visible()
    base = page.locator(".app-flash").bounding_box()
    page.evaluate(MODAL_FLASH)
    page.evaluate("() => { App.ui.flash('Page'); }")
    expect(page.locator("dialog .app-flash.visible")).to_be_visible()
    inside = page.locator("dialog .app-flash").bounding_box()
    assert abs(base["x"] - inside["x"]) < 1 and abs(base["y"] - inside["y"]) < 1
    assert inside["y"] < 40  # top: 16px of the viewport, not of the dialog


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


def test_chip_lead_and_remove_button(engine_page: Page) -> None:
    """M31 F6 L03c: `lead` precedes the label; `onRemove` adds one named icon-only button."""
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          window.__removed = 0;
          const img = document.createElement('img'); img.alt = ''; img.setAttribute('data-x', 'thumb');
          const a = App.ui.chip({label: 'photo.png', lead: img, onRemove: () => { window.__removed++; },
                                 removeLabel: 'Remove image 1', removeTestid: 'rm'});
          const plain = App.ui.chip({label: 'plain'});
          root.appendChild(a); root.appendChild(plain);
          let err = '';
          try { App.ui.chip({label: 'x', onRemove: () => {}}); } catch (e) { err = e.message; }
          const btns = a.querySelectorAll('button');
          return {first: a.firstChild.firstChild === img, text: a.querySelector('.chip-label').textContent,
                  n: btns.length, name: btns[0].getAttribute('aria-label'), tag: a.tagName,
                  plainHtml: plain.outerHTML, err};
        }""",
    )
    assert out["first"] and out["text"] == "photo.png" and out["n"] == 1
    assert out["name"] == "Remove image 1" and out["tag"] == "SPAN"
    assert out["plainHtml"] == '<span class="chip">plain</span>'
    assert "removeLabel" in out["err"]
    btn = engine_page.get_by_test_id("rm")
    engine_page.keyboard.press("Tab")
    expect(btn).to_be_focused()
    engine_page.keyboard.press("Enter")
    engine_page.keyboard.press("Space")
    btn.click()
    assert engine_page.evaluate("() => window.__removed") == 3


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


def test_badge_live_set_patches_in_place_and_empty_text_hides(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          const b = App.ui.badge.live({kind: 'unknown', testid: 'bl'});
          root.appendChild(b.el);
          const snap = () => ({cls: b.el.className, text: b.el.textContent, hidden: b.el.hidden,
            shown: getComputedStyle(b.el).display !== 'none'});
          const first = snap();
          const node = b.el;
          b.set({kind: 'ollama', text: 'llama3'});
          const second = snap();
          b.set({kind: 'openai', text: ''});
          const third = snap();
          b.set({text: 'plain'});
          const fourth = snap();
          b.set({kind: 'anthropic', text: null});
          const fifth = snap();
          let err = '';
          try { b.set({kind: 'nope', text: 'x'}); } catch (e) { err = e.message; }
          let initErr = '';
          try { App.ui.badge.live({kind: 'nope'}); } catch (e) { initErr = e.message; }
          return {first, second, third, fourth, fifth, err, initErr, same: b.el === node,
                  tid: b.el.getAttribute('data-testid'), staticStillThrows: (() => {
                    try { App.ui.badge({text: ''}); return false; } catch (e) { return true; }
                  })(), staticNode: App.ui.badge({text: 'x', kind: 'local'}).nodeType};
        }""",
    )
    assert out["first"]["hidden"] is True and out["first"]["shown"] is False
    assert out["first"]["cls"] == "badge badge--unknown"
    assert out["second"] == {
        "cls": "badge badge--ollama",
        "text": "llama3",
        "hidden": False,
        "shown": True,
    }
    assert out["third"]["hidden"] is True and out["third"]["text"] == ""
    assert out["fourth"]["cls"] == "badge" and out["fourth"]["text"] == "plain"
    assert out["fifth"]["hidden"] is True
    assert "unknown kind" in out["err"] and "unknown kind" in out["initErr"]
    assert out["same"] is True and out["tid"] == "bl"
    assert out["staticStillThrows"] is True and out["staticNode"] == 1


def test_note_flag_role_name_and_icon(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const f = App.ui.noteFlag({sources: ['web', 'file'], testid: 'nf'});
          const g = App.ui.noteFlag({});
          document.getElementById('harness-root').append(f, g);
          const sentence = "Check this note: it was written after content that didn't come from you (web, file). It may have been planted.";
          const cs = getComputedStyle(f);
          const probe = document.createElement('span'); probe.style.color = 'var(--status-warning)';
          document.getElementById('harness-root').appendChild(probe);
          const r = App.ui.noteFlag({sources: ['web'], subject: 'routine'});
          const n = App.ui.noteFlag({subject: 'note'});
          const pr = App.ui.noteFlag({sources: ['web_fetch', 'file'], subject: 'proposal', testid: 'pf'});
          let err = '';
          try { App.ui.noteFlag({subject: 'rule'}); } catch (e) { err = String(e.message); }
          return {tag: f.tagName + '.' + f.className, role: f.getAttribute('role'),
                  routine: r.getAttribute('aria-label'), explicitNote: n.getAttribute('aria-label'),
                  proposal: pr.getAttribute('aria-label'), proposalTitle: pr.title,
                  proposalTid: pr.getAttribute('data-testid'),
                  err: err,
                  named: f.getAttribute('aria-label') === sentence && f.title === sentence,
                  plain: g.getAttribute('aria-label'), svgs: f.querySelectorAll('svg').length,
                  svgW: getComputedStyle(f.querySelector('svg')).width, display: cs.display,
                  color: cs.color === getComputedStyle(probe).color, tid: f.getAttribute('data-testid'),
                  gone: [typeof App.noteFlag, typeof App.iconNode]};
        }""",
    )
    assert out["tag"] == "SPAN.note-flag" and out["role"] == "img" and out["named"] is True
    assert (
        out["plain"]
        == "Check this note: it was written after content that didn't come from you. It may have been planted."
    )
    assert (
        out["routine"]
        == "Check this routine: it was written after content that didn't come from you (web). It may have been planted."
    )
    assert out["explicitNote"] == out["plain"]
    # M36 F2 L6: a proposal is "made", not "written".
    assert (
        out["proposal"]
        == "Check this proposal: it was made after content that didn't come from you (web_fetch, file). It may have been planted."
    )
    assert out["proposalTitle"] == out["proposal"] and out["proposalTid"] == "pf"
    assert "subject" in out["err"]
    assert out["svgs"] == 1 and out["svgW"] == "14px" and out["display"] == "inline-flex"
    assert out["color"] is True and out["tid"] == "nf"
    assert out["gone"] == ["undefined", "undefined"]


def test_note_flag_fill_subject(engine_page: Page) -> None:
    """M36 F3 L6: the subject ``fill`` says "form fill", made; an unknown subject still throws."""
    out = _mount(
        engine_page,
        """() => {
          const f = App.ui.noteFlag({sources: ['web_fetch', 'file'], subject: 'fill', testid: 'ff'});
          document.getElementById('harness-root').append(f);
          let err = '';
          try { App.ui.noteFlag({subject: 'form'}); } catch (e) { err = String(e.message); }
          return {label: f.getAttribute('aria-label'), title: f.title, tid: f.getAttribute('data-testid'),
                  role: f.getAttribute('role'), svgs: f.querySelectorAll('svg').length, err: err};
        }""",
    )
    sentence = (
        "Check this form fill: it was made after content that didn't come from you "
        "(web_fetch, file). It may have been planted."
    )
    assert out["label"] == sentence and out["title"] == sentence
    assert out["tid"] == "ff" and out["role"] == "img" and out["svgs"] == 1
    assert "subject" in out["err"] and '"fill"' in out["err"]


def test_layered_note_flag_and_consent_link_styles_are_unchanged(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          const f = App.ui.noteFlag({sources: ['x']});
          const link = App.ui.consentLink.build('https://auth.example/c', {surface: 'mcp', sourceName: 'S'});
          root.append(f, link);
          const open = link.querySelector('.consent-link-open');
          const fg = document.createElement('span'); fg.style.color = 'var(--fg)'; root.appendChild(fg);
          const o = getComputedStyle(open), b = getComputedStyle(link), n = getComputedStyle(f);
          return {open: {color: o.color === getComputedStyle(fg).color, deco: o.textDecorationLine, ws: o.whiteSpace},
                  block: {display: b.display, dir: b.flexDirection, max: b.maxWidth},
                  note: {display: n.display, flex: n.flexGrow + ' ' + n.flexShrink}};
        }""",
    )
    assert out == {
        "open": {"color": True, "deco": "none", "ws": "nowrap"},
        "block": {"display": "flex", "dir": "column", "max": "560px"},
        "note": {"display": "inline-flex", "flex": "0 0"},
    }


def test_a_badge_never_shrinks_in_a_narrow_flex_row(engine_page: Page) -> None:
    """M31 F6 L03b: `.badge { flex-shrink: 0 }` is the base rule (the drawer head's area
    rule is gone); the badge keeps its full text beside a long name."""
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const row = document.createElement('div');
          row.style.cssText = 'display: flex; width: 160px; gap: 8px;';
          const name = document.createElement('span');
          name.style.cssText = 'min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;';
          name.textContent = 'A very long agent name that cannot fit';
          const b = App.ui.badge({text: 'ollama', kind: 'ollama'});
          row.append(name, b);
          document.getElementById('harness-root').appendChild(row);
          return {shrink: getComputedStyle(b).flexShrink, whole: b.scrollWidth <= b.clientWidth,
                  inside: b.getBoundingClientRect().right <= row.getBoundingClientRect().right + 0.5};
        }"""
    )
    assert out == {"shrink": "0", "whole": True, "inside": True}


def test_chip_label_hidden_truncate_and_24px_remove_button(engine_page: Page) -> None:
    """M31 F6 L05a: `labelHidden` keeps the label as the chip's name but visually hides it;
    `truncate` is one line with an ellipsis (min-width 0); the remove button is a 24px target
    with no negative margin (WCAG 2.2 target size) in both layouts."""
    out = _mount(
        engine_page,
        """() => {
          const root = document.getElementById('harness-root');
          const wrap = document.createElement('div'); wrap.style.cssText = 'width: 180px; display: flex;';
          root.appendChild(wrap);
          const img = document.createElement('img'); img.alt = ''; img.width = 24; img.height = 24;
          const hid = App.ui.chip({label: 'Staged image 1', labelHidden: true, lead: img, onRemove: () => {},
                                   removeLabel: 'Remove staged image 1', removeTestid: 'rm-hidden'});
          const tr = App.ui.chip({label: 'a very long queued message that cannot possibly fit on one line at all',
                                  truncate: true, lead: document.createTextNode('Queued'), onRemove: () => {},
                                  removeLabel: 'Cancel queued message', removeTestid: 'rm-trunc'});
          const plain = App.ui.chip({label: 'tag', onRemove: () => {}, removeLabel: 'Remove tag', removeTestid: 'rm-plain'});
          wrap.appendChild(hid); wrap.appendChild(tr); wrap.appendChild(plain);
          const lab = hid.querySelector('.chip-label');
          const tl = tr.querySelector('.chip-label');
          const box = (n) => { const r = n.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; };
          const cs = (n) => getComputedStyle(n);
          return {
            hidClass: lab.className, hidText: lab.textContent, hidW: box(lab)[0] <= 1,
            hidClip: cs(lab).position === 'absolute',
            trWs: cs(tl).whiteSpace, trOv: cs(tl).overflow, trTo: cs(tl).textOverflow, trMin: cs(tl).minWidth,
            trFits: tr.getBoundingClientRect().right <= wrap.getBoundingClientRect().right + 1,
            btnHidden: box(hid.querySelector('button')), btnTrunc: box(tr.querySelector('button')),
            btnPlain: box(plain.querySelector('button')),
            margin: cs(plain.querySelector('button')).margin,
            hidden: (() => { try { App.ui.chip({label: 'x', labelHidden: true, lead: null}); return ''; } catch (e) { return e.message; } })()
          };
        }""",
    )
    assert "visually-hidden" in out["hidClass"] and out["hidText"] == "Staged image 1"
    assert out["hidW"] and out["hidClip"]
    assert out["trWs"] == "nowrap" and out["trOv"] == "hidden" and out["trTo"] == "ellipsis"
    assert out["trMin"] == "0px" and out["trFits"]
    assert out["btnHidden"] == [24, 24] and out["btnTrunc"] == [24, 24]
    assert out["btnPlain"] == [24, 24]
    assert out["margin"] == "0px"
    assert engine_page.get_by_role("button", name="Remove staged image 1").count() == 1

# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.composer`` (M31 F6 L04, flight DD4): the
chat composer. Roles, names and the per-part test ids, the Enter / Shift+Enter / IME rule,
the raw ``onSend`` (busy, empty text, the input never cleared), Send / Stop / Attach, the
file input, ``setBusy`` and ``setBlocked`` composing as ``blocked or busy``, the auto-fit
(grows, then caps and scrolls), the slots and ``destroy`` (no listener fires afterwards).
Chromium and WebKit through ``engine_page`` + ``load_harness``; falls in the
``contracts-chat`` lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

MOUNT_JS = """(src) => {
  window.__calls = {send: [], stop: 0, attach: 0, files: []};
  const root = document.getElementById('harness-root');
  const frame = document.createElement('div');
  frame.id = 'frame';
  frame.style.cssText = 'width: 640px;';
  window.__c = App.ui.composer(Object.assign({
    placeholder: 'Message Helper…', testid: 'c-input', attachTestid: 'c-attach', fileInputTestid: 'c-file',
    modelTestid: 'c-model', stopTestid: 'c-stop', sendTestid: 'c-send', attachmentsTestid: 'c-attachments',
    attachmentsStatusTestid: 'c-attachments-status', queuedTestid: 'c-queued', telemetryTestid: 'c-telemetry',
    onSend: (t) => __calls.send.push(t), onStop: () => { __calls.stop++; }, onAttach: () => { __calls.attach++; },
    onFiles: (f) => __calls.files.push(f.map((x) => x.name)),
  }, eval('(' + src + ')')));
  frame.appendChild(__c.el);
  root.appendChild(frame);
}"""


def _mount(page: Page, js_opts: str = "{}") -> None:
    load_harness(page)
    page.evaluate(MOUNT_JS, js_opts)


def _sent(page: Page) -> list:
    return page.evaluate("() => __calls.send")


def test_structure_roles_names_and_testids(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    expect(page.get_by_role("textbox", name="Message")).to_have_count(1)
    expect(page.get_by_role("button", name="Attach images")).to_have_count(1)
    expect(page.get_by_role("button", name="Send")).to_have_count(1)
    expect(page.get_by_role("button", name="Stop")).to_have_count(0)  # hidden until busy
    for tid in (
        "c-input",
        "c-attach",
        "c-file",
        "c-model",
        "c-stop",
        "c-send",
        "c-attachments",
        "c-attachments-status",
        "c-queued",
        "c-telemetry",
    ):
        assert page.get_by_test_id(tid).count() == 1, tid
    assert page.get_by_test_id("c-file").get_attribute("aria-label") == "Attach images"
    assert page.get_by_test_id("c-send").get_attribute("aria-keyshortcuts") == "Enter"
    assert page.get_by_test_id("c-input").get_attribute("placeholder") == "Message Helper…"
    assert page.evaluate("() => __c.el.className") == "ui-composer"
    label = page.evaluate(
        "() => { const l = __c.el.querySelector('label'); return [l.getAttribute('for') === __c.input.id, l.className]; }"
    )
    assert label == [True, "visually-hidden"]


def test_options_label_attach_label_and_accept(engine_page: Page) -> None:
    page = engine_page
    _mount(page, "{label: 'Reply', attachLabel: 'Add files', accept: '.txt', multiple: false}")
    expect(page.get_by_role("textbox", name="Reply")).to_have_count(1)
    expect(page.get_by_role("button", name="Add files")).to_have_count(1)
    assert page.evaluate(
        "() => [__c.el.querySelector('input[type=file]').accept, __c.el.querySelector('input[type=file]').multiple]"
    ) == [".txt", False]


def test_input_ids_are_unique_per_composer(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    ids = page.evaluate(
        "() => { const b = App.ui.composer({}); return [__c.input.id, b.input.id]; }"
    )
    assert ids[0] and ids[1] and ids[0] != ids[1]
    assert page.evaluate("() => document.getElementById('chat-composer-input')") is None


def test_tab_order_is_input_attach_send_and_stop_joins_when_busy(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    order = []
    page.get_by_test_id("c-input").focus()
    for _ in range(2):
        page.keyboard.press("Tab")
        order.append(page.evaluate("() => document.activeElement.getAttribute('data-testid')"))
    assert order == ["c-attach", "c-send"]
    page.evaluate("() => __c.setBusy(true)")
    page.get_by_test_id("c-attach").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.getAttribute('data-testid')") == "c-stop"
    # the focus ring is the box's :focus-within
    assert (
        page.evaluate(
            "() => getComputedStyle(__c.el.querySelector('.ui-composer-box')).outlineStyle"
        )
        == "solid"
    )


def test_enter_sends_the_raw_value_and_never_clears_the_input(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    box = page.get_by_test_id("c-input")
    box.fill("  hello  ")
    box.press("Enter")
    assert _sent(page) == ["  hello  "]
    expect(box).to_have_value("  hello  ")  # the caller clears with setValue('')
    page.evaluate("() => __c.setValue('')")
    expect(box).to_have_value("")


def test_enter_with_empty_text_and_while_busy_still_calls_onsend(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    box = page.get_by_test_id("c-input")
    box.focus()
    page.keyboard.press("Enter")
    assert _sent(page) == [""]
    page.evaluate("() => __c.setBusy(true)")
    box.fill("queued message")
    box.press("Enter")
    assert _sent(page) == ["", "queued message"]
    expect(page.get_by_test_id("c-send")).to_be_disabled()  # only the button is disabled while busy


def test_shift_enter_is_a_newline_and_sends_nothing(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    box = page.get_by_test_id("c-input")
    box.focus()
    page.keyboard.type("one")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("two")
    assert _sent(page) == []
    expect(box).to_have_value("one\ntwo")


def test_ime_enter_does_nothing_in_both_engines(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    out = page.evaluate(
        """() => {
          const ta = __c.input;
          const mk = (init, code) => {
            const e = new KeyboardEvent('keydown', Object.assign({key: 'Enter', bubbles: true, cancelable: true}, init));
            if (code) Object.defineProperty(e, 'keyCode', {value: code});
            ta.dispatchEvent(e);
            return e.defaultPrevented;
          };
          const composing = mk({isComposing: true});
          const code229 = mk({}, 229);
          const plain = mk({});
          return {composing, code229, plain, sent: __calls.send.length};
        }"""
    )
    assert out == {"composing": False, "code229": False, "plain": True, "sent": 1}


def test_send_stop_and_attach_buttons_call_their_handlers(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.get_by_test_id("c-input").fill("via button")
    page.get_by_test_id("c-send").click()
    assert _sent(page) == ["via button"]
    page.evaluate("() => __c.setBusy(true)")
    page.get_by_test_id("c-stop").click()
    assert page.evaluate("() => __calls.stop") == 1
    page.evaluate(
        "() => { window.__picked = 0; __c.el.querySelector('input[type=file]').addEventListener('click', () => { window.__picked++; }); }"
    )
    page.get_by_test_id("c-attach").click()
    assert page.evaluate("() => [__calls.attach, __picked]") == [
        1,
        0,
    ]  # the area opens the picker, not the control


def test_open_file_picker_and_the_files_change_resets_the_input(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    with page.expect_file_chooser() as chooser:
        page.evaluate("() => __c.openFilePicker()")
    chooser.value.set_files(
        [
            {"name": "a.png", "mimeType": "image/png", "buffer": b"x"},
            {"name": "b.png", "mimeType": "image/png", "buffer": b"y"},
        ]
    )
    page.wait_for_function("() => __calls.files.length === 1")
    assert page.evaluate("() => __calls.files") == [["a.png", "b.png"]]
    assert page.evaluate("() => __c.el.querySelector('input[type=file]').value") == ""
    page.get_by_test_id("c-file").set_input_files(
        [{"name": "a.png", "mimeType": "image/png", "buffer": b"x"}]
    )
    page.wait_for_function("() => __calls.files.length === 2")  # the same file can be chosen again


def test_set_busy_toggles_stop_and_send_but_not_the_input(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    expect(page.get_by_test_id("c-stop")).to_be_hidden()
    expect(page.get_by_test_id("c-send")).to_be_enabled()
    page.evaluate("() => __c.setBusy(true)")
    expect(page.get_by_test_id("c-stop")).to_be_visible()
    expect(page.get_by_test_id("c-send")).to_be_disabled()
    expect(page.get_by_test_id("c-input")).to_be_enabled()
    page.evaluate("() => __c.setBusy(false)")
    expect(page.get_by_test_id("c-stop")).to_be_hidden()
    expect(page.get_by_test_id("c-send")).to_be_enabled()


def test_set_blocked_disables_input_send_and_attach_and_dims_the_box(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    plain = page.evaluate(
        "() => { const s = getComputedStyle(__c.el.querySelector('.ui-composer-box')); return [s.backgroundColor, s.borderStyle]; }"
    )
    page.evaluate("() => __c.setBlocked('The agent was deleted.')")
    for tid in ("c-input", "c-send", "c-attach"):
        expect(page.get_by_test_id(tid)).to_be_disabled()
    dim = page.evaluate(
        "() => { const b = __c.el.querySelector('.ui-composer-box'); const s = getComputedStyle(b); return [s.backgroundColor, s.borderStyle, b.className, b.getAttribute('title')]; }"
    )
    assert (
        dim[2] == "ui-composer-box ui-composer-box--blocked" and dim[3] == "The agent was deleted."
    )
    assert [dim[0], dim[1]] != plain
    page.evaluate("() => __c.setBlocked(null)")
    for tid in ("c-input", "c-send", "c-attach"):
        expect(page.get_by_test_id(tid)).to_be_enabled()
    assert (
        page.evaluate("() => __c.el.querySelector('.ui-composer-box').className")
        == "ui-composer-box"
    )
    assert (
        page.evaluate("() => __c.el.querySelector('.ui-composer-box').hasAttribute('title')")
        is False
    )


def test_clearing_blocked_while_busy_keeps_send_disabled(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("() => { __c.setBusy(true); __c.setBlocked('x'); }")
    expect(page.get_by_test_id("c-send")).to_be_disabled()
    page.evaluate("() => __c.setBlocked(null)")
    expect(page.get_by_test_id("c-send")).to_be_disabled()  # busy still holds it
    expect(page.get_by_test_id("c-input")).to_be_enabled()
    page.evaluate("() => __c.setBusy(false)")
    expect(page.get_by_test_id("c-send")).to_be_enabled()
    page.evaluate("() => { __c.setBlocked(true); __c.setBusy(true); __c.setBusy(false); }")
    expect(page.get_by_test_id("c-send")).to_be_disabled()  # blocked still holds it


def test_value_placeholder_model_and_focus(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate(
        "() => { __c.setValue('draft'); __c.setPlaceholder('Message Other…'); __c.setModel('claude-haiku-4-5'); __c.focus(); }"
    )
    assert page.evaluate("() => __c.getValue()") == "draft"
    expect(page.get_by_test_id("c-input")).to_have_attribute("placeholder", "Message Other…")
    expect(page.get_by_test_id("c-model")).to_have_text("claude-haiku-4-5")
    assert page.evaluate("() => document.activeElement === __c.input") is True
    page.evaluate("() => { __c.setModel(''); __c.setPlaceholder(null); __c.setValue(null); }")
    expect(page.get_by_test_id("c-model")).to_have_text("")
    assert page.evaluate("() => [__c.getValue(), __c.input.placeholder]") == ["", ""]


def test_auto_fit_grows_then_caps_and_scrolls(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    height = "() => __c.input.getBoundingClientRect().height"
    rest = page.evaluate(height)
    page.get_by_test_id("c-input").focus()
    for _ in range(4):  # typing fires input events: the control fits on its own
        page.keyboard.type("line")
        page.keyboard.press("Shift+Enter")
    grown = page.evaluate(height)
    assert grown > rest
    page.evaluate("() => __c.setValue('line\\n'.repeat(40))")
    capped = page.evaluate(height)
    assert capped > grown
    assert (
        page.evaluate("() => __c.input.scrollHeight > __c.input.clientHeight") is True
    )  # then it scrolls
    page.evaluate("() => __c.setValue('')")
    assert page.evaluate(height) == rest
    assert page.evaluate("() => __c.el.querySelector('.ui-composer-box').style.minHeight") == ""


def test_fit_is_a_no_op_while_disconnected(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    out = page.evaluate(
        """() => {
          const c = App.ui.composer({});
          c.setValue('a\\nb\\nc\\nd\\ne\\nf');
          c.fit();
          const detached = c.input.style.height;
          document.getElementById('frame').appendChild(c.el);
          c.fit();
          return [detached, c.input.style.height !== ''];
        }"""
    )
    assert out == ["", True]


def test_slots_are_caller_filled_and_hide_the_right_way(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    out = page.evaluate(
        """() => {
          const s = __c.slots;
          return {keys: Object.keys(s).sort(),
                  telemetryHidden: s.telemetry.hidden, queuedHidden: s.queued.hidden, queuedAttr: s.queued.hasAttribute('hidden'),
                  attachmentsDisplay: s.attachments.style.display, attachmentsHiddenAttr: s.attachments.hasAttribute('hidden'),
                  statusLive: s.attachmentsStatus.getAttribute('aria-live'), statusClass: s.attachmentsStatus.className,
                  order: Array.from(__c.el.children).map((n) => n.getAttribute('data-testid') || n.className)};
        }"""
    )
    assert out["keys"] == ["attachments", "attachmentsStatus", "queued", "telemetry"]
    assert out["telemetryHidden"] is True and out["queuedHidden"] is False
    assert out["queuedAttr"] is False
    assert out["attachmentsDisplay"] == "none" and out["attachmentsHiddenAttr"] is False
    assert out["statusLive"] == "polite" and out["statusClass"] == "visually-hidden"
    assert out["order"] == [
        "c-telemetry",
        "c-attachments",
        "c-attachments-status",
        "c-queued",
        "ui-composer-box",
    ]
    # a caller un-hides the telemetry slot with `hidden`: no rule here defeats it
    page.evaluate(
        "() => { __c.slots.telemetry.hidden = false; __c.slots.telemetry.textContent = 'ctx'; __c.slots.queued.textContent = 'held'; }"
    )
    expect(page.get_by_test_id("c-telemetry")).to_be_visible()
    expect(page.get_by_test_id("c-queued")).to_be_visible()
    page.evaluate("() => { __c.slots.queued.textContent = ''; }")
    assert page.evaluate("() => getComputedStyle(__c.slots.queued).display") != "none"


def test_a_200_character_unbroken_draft_stays_inside_the_box(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("() => __c.setValue('x'.repeat(200))")
    assert page.evaluate("() => __c.input.scrollWidth <= __c.input.clientWidth + 1") is True
    assert (
        page.evaluate(
            "() => __c.el.scrollWidth <= document.getElementById('frame').clientWidth + 1"
        )
        is True
    )


def test_destroy_removes_every_listener_and_is_idempotent(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("() => { __c.destroy(); __c.destroy(); }")
    box = page.get_by_test_id("c-input")
    box.fill("after destroy")
    box.press("Enter")
    page.get_by_test_id("c-send").click()
    page.evaluate("() => { __c.setBusy(true); }")
    page.get_by_test_id("c-stop").click()
    page.get_by_test_id("c-attach").click()
    page.get_by_test_id("c-file").set_input_files(
        [{"name": "a.png", "mimeType": "image/png", "buffer": b"x"}]
    )
    page.wait_for_timeout(100)
    assert page.evaluate(
        "() => [__calls.send.length, __calls.stop, __calls.attach, __calls.files.length]"
    ) == [0, 0, 0, 0]
    # a spent control no longer re-fits on input
    page.evaluate(
        "() => { __c.input.value = 'a\\nb\\nc\\nd\\ne'; __c.input.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    assert page.evaluate("() => __c.input.style.height") == ""


def test_file_input_is_exposed_and_the_queued_slot_is_a_live_region(engine_page: Page) -> None:
    """M31 F6 L05a: `fileInput` is a read-only reference like `input`; `slots.queued` is a
    persistent aria-live=polite region (never hidden, empty until filled)."""
    page = engine_page
    _mount(page)
    assert page.evaluate("() => __c.fileInput === __c.el.querySelector('input[type=file]')") is True
    assert page.evaluate("() => __c.fileInput.getAttribute('data-testid')") == "c-file"
    assert page.evaluate("() => __c.slots.queued.getAttribute('aria-live')") == "polite"
    # the live node stays rendered (never hidden) while empty, so the later insert is announced
    assert page.evaluate("() => __c.slots.queued.hasAttribute('hidden')") is False
    assert page.evaluate("() => getComputedStyle(__c.slots.queued).display") != "none"
    assert page.evaluate("() => __c.slots.queued.childNodes.length") == 0
    page.evaluate("() => { __c.slots.queued.textContent = 'Queued x'; }")
    expect(page.get_by_test_id("c-queued")).to_be_visible()
    assert page.evaluate("() => __c.slots.queued.getAttribute('aria-live')") == "polite"

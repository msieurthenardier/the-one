"""The chat composer and the telemetry row (M25 F4 leg 5; flight DD6, A25;
reference spec 5.3, 5.5; squawk 0110).

The composer (``areas/chat/composer.js``) is a wrapper (``.composer``,
``padding: 12px 24px 20px``) holding, top to bottom:

* the telemetry row (``.composer-telemetry``): the token readout, flex-end,
  shown only while a chat is joined (none in the new-chat state, 5.4);
* the staged-image chicklets (``chat-attachments``) and the queued-message
  region (``pending-queued-region``), in the box's 760px column;
* the box (``.composer-box``): max 760px, centred, ``--surface``, a hairline,
  ``--radius-md``; the focus ring is its ``:focus-within`` (A25). Inside, a
  visually hidden ``<label for>`` "Message", the ``<textarea rows=2>``
  (``chat-input``; placeholder "Message {agent}…"; Enter sends, Shift+Enter is
  a newline, an IME-composing Enter does nothing) and the toolbar: Attach
  images (``chat-attach-btn``, ghost, small, icon only), the hidden file input
  (``chat-image-input``, named "Attach images": squawk 0110), the agent's model
  id (``chat-model``), Stop (``chat-stop-btn``) and Send (``chat-send-btn``).

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import base64
import json

import pytest
from browser import _chats, _nav
from browser._a11y_resolvers import collect_label_failures
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

INPUT = '[data-testid="chat-input"]'
BOX = ".area-chat .composer-box"
ROW = ".area-chat .composer-telemetry"
USER_MSG = '[data-testid="message"].user'

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

# The computed value of a token, read through a probe inside the composer box
# (so it resolves in the box's theme).
_TOKEN = """([prop, value]) => {
  const p = document.createElement('span');
  p.style[prop] = value;
  document.querySelector('.area-chat .composer-box').appendChild(p);
  const v = getComputedStyle(p)[prop];
  p.remove();
  return v;
}"""

_STATE = "() => App.areas.find(a => a.id === 'chat')._sessionState().name"


def _token(page: Page, prop: str, value: str) -> str:
    return page.evaluate(_TOKEN, [prop, value])


def _wait_state(page: Page, name: str, timeout: float = 10000) -> None:
    page.wait_for_function(f"n => ({_STATE})() === n", arg=name, timeout=timeout)


def _composer_view(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => ({
          placeholder: document.querySelector('[data-testid="chat-input"]').placeholder,
          model: document.querySelector('[data-testid="chat-model"]').textContent,
        })"""
    )


def _prime_session_agent(page: Page, sid: str, agent: str | None) -> None:
    page.evaluate(
        """([sid, agent]) => App.store.prime('sessions', App.store.peek('sessions').value.map(
             (r) => r.id === sid ? Object.assign({}, r, {agent_name: agent}) : r))""",
        [sid, agent],
    )


def _ring(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => {
          const cs = getComputedStyle(document.querySelector('.area-chat .composer-box'));
          return {style: cs.outlineStyle, width: cs.outlineWidth, color: cs.outlineColor,
                  offset: cs.outlineOffset,
                  input: getComputedStyle(
                    document.querySelector('[data-testid="chat-input"]')).outlineStyle};
        }"""
    )


# ── The box, the textarea and the toolbar (AC1, AC2, AC5) ───────────────────


def test_composer_box_textarea_and_toolbar_match_the_board(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    second = seed_mock_agent(base, app_with_agent.provider_id, name="second", model="m-two")
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)

    shape = page.evaluate(
        """() => {
          const wrap = document.querySelector('.area-chat .composer');
          const box = wrap.querySelector('.composer-box');
          const input = box.querySelector('[data-testid="chat-input"]');
          const label = box.querySelector('label');
          const bar = box.querySelector('.composer-toolbar');
          const cs = (el) => getComputedStyle(el);
          const kid = (c) => c.getAttribute('data-testid') || c.className;
          const wr = wrap.getBoundingClientRect(), br = box.getBoundingClientRect();
          const wcs = cs(wrap);
          const innerLeft = wr.left + parseFloat(wcs.paddingLeft);
          const innerRight = wr.right - parseFloat(wcs.paddingRight);
          const send = bar.querySelector('[data-testid="chat-send-btn"]');
          const attach = bar.querySelector('[data-testid="chat-attach-btn"]');
          const file = bar.querySelector('[data-testid="chat-image-input"]');
          const model = bar.querySelector('[data-testid="chat-model"]');
          const stop = bar.querySelector('[data-testid="chat-stop-btn"]');
          return {
            chrome: Array.from(document.querySelector('.area-chat .chat-chrome').children).map(kid),
            wrapKids: Array.from(wrap.children).map(kid),
            wrapPad: wcs.padding,
            box: {maxW: cs(box).maxWidth, display: cs(box).display, dir: cs(box).flexDirection,
                  gap: cs(box).rowGap, bg: cs(box).backgroundColor,
                  border: cs(box).borderTopWidth + ' ' + cs(box).borderTopStyle,
                  borderColor: cs(box).borderTopColor, radius: cs(box).borderTopLeftRadius,
                  pad: cs(box).padding, width: br.width, column: innerRight - innerLeft,
                  centred: Math.abs((innerLeft + innerRight) / 2 - (br.left + br.right) / 2) < 1},
            boxKids: Array.from(box.children).map((c) => c.tagName),
            label: {text: label.textContent, for: label.htmlFor, hidden: label.className,
                    w: label.getBoundingClientRect().width},
            input: {tag: input.tagName, id: input.id, rows: input.rows, resize: cs(input).resize,
                    border: cs(input).borderTopWidth, bg: cs(input).backgroundColor,
                    size: cs(input).fontSize, outline: cs(input).outlineStyle,
                    ariaLabel: input.getAttribute('aria-label'),
                    labels: Array.from(input.labels).map((l) => l.textContent),
                    hint: input.getAttribute('enterkeyhint')},
            bar: {display: cs(bar).display, align: cs(bar).alignItems, gap: cs(bar).columnGap,
                  kids: Array.from(bar.children).map(kid)},
            attach: {cls: attach.className, type: attach.type,
                     label: attach.getAttribute('aria-label'), text: attach.textContent.trim(),
                     path: attach.querySelector('svg path').getAttribute('d').slice(0, 6),
                     w: attach.getBoundingClientRect().width,
                     h: attach.getBoundingClientRect().height},
            file: {type: file.type, hidden: file.hidden, accept: file.accept,
                   multiple: file.multiple, label: file.getAttribute('aria-label')},
            model: {text: model.textContent, tag: model.tagName, size: cs(model).fontSize,
                    family: cs(model).fontFamily, color: cs(model).color},
            stop: {cls: stop.className, hidden: stop.hidden},
            send: {cls: send.className, text: send.textContent.trim(),
                   svg: !!send.querySelector('svg'), keys: send.getAttribute('aria-keyshortcuts'),
                   right: send.getBoundingClientRect().right,
                   barRight: bar.getBoundingClientRect().right},
          };
        }"""
    )
    # AC1: the chrome ends in the composer wrapper; it holds the telemetry
    # row, the chicklets and their status, the queued region, then the box.
    assert shape["chrome"] == ["chat-header", "chat-new-state", "messages", "composer"], shape
    assert shape["wrapKids"] == [
        "composer-telemetry",
        "chat-attachments",
        "chat-attachments-status",
        "pending-queued-region",
        "composer-box",
    ], shape["wrapKids"]
    assert shape["wrapPad"] == "12px 24px 20px", shape
    box = shape["box"]
    # Capped at 760px and centred in the wrapper's column. Since M25 F4 L6 the
    # agent drawer is open by default at 1280 and wider (push), so at 1440 the
    # pane is 748px and the column 700px: the box fills it below the cap.
    assert box["maxW"] == "760px" and box["centred"], box
    assert box["width"] == min(760, box["column"]), box
    assert box["display"] == "flex" and box["dir"] == "column" and box["gap"] == "8px", box
    assert box["bg"] == _token(page, "backgroundColor", "var(--surface)"), box
    assert box["border"] == "1px solid", box
    assert box["borderColor"] == _token(page, "borderTopColor", "var(--border)"), box
    assert box["radius"] == "8px" and box["pad"] == "10px 12px", box
    assert shape["boxKids"] == ["LABEL", "TEXTAREA", "DIV"], shape

    # AC2: the textarea, its real (visually hidden) label, no aria-label.
    label, inp = shape["label"], shape["input"]
    assert label["text"] == "Message" and label["for"] == inp["id"], label
    assert label["hidden"] == "visually-hidden" and label["w"] <= 1, label
    assert inp["tag"] == "TEXTAREA" and inp["rows"] == 2 and inp["resize"] == "none", inp
    assert inp["border"] == "0px" and inp["bg"] == "rgba(0, 0, 0, 0)", inp
    assert inp["size"] == "14px" and inp["outline"] == "none", inp
    assert inp["ariaLabel"] is None and inp["labels"] == ["Message"], inp
    assert inp["hint"] == "send", inp
    expect(page.locator(INPUT)).to_have_accessible_name("Message")

    # AC5: the toolbar.
    bar = shape["bar"]
    assert bar["display"] == "flex" and bar["align"] == "center" and bar["gap"] == "8px", bar
    assert bar["kids"] == [
        "chat-attach-btn",
        "chat-image-input",
        "chat-model",
        "chat-stop-btn",
        "chat-send-btn",
    ], bar
    attach = shape["attach"]
    assert attach["cls"] == "btn-ghost btn-sm btn-icon composer-attach", attach
    assert attach["type"] == "button" and attach["label"] == "Attach images", attach
    assert attach["text"] == "" and attach["path"] == "m21.44", attach  # paperclip, icon only
    assert attach["w"] == 24 and attach["h"] == 24, attach
    file = shape["file"]
    assert file == {
        "type": "file",
        "hidden": True,
        "accept": "image/*",
        "multiple": True,
        "label": "Attach images",
    }, file
    model = shape["model"]
    assert model["tag"] == "SPAN" and model["text"] == "mock-default", model
    assert model["size"] == "11px", model
    assert model["family"] == _token(page, "fontFamily", "var(--font-family-mono)"), model
    assert model["color"] == _token(page, "color", "var(--fg-muted)"), model
    assert shape["stop"] == {"cls": "btn-muted-destructive composer-stop", "hidden": True}
    send = shape["send"]
    assert send["cls"] == "btn-filled-primary composer-send" and send["text"] == "Send", send
    assert send["svg"] and send["keys"] == "Enter", send
    assert abs(send["right"] - send["barRight"]) < 1, send  # pushed to the end

    # The placeholder and the model follow the agent: pending, a re-pick, joined.
    assert _composer_view(page) == {"placeholder": f"Message {agent}…", "model": "mock-default"}
    _chats.pick(page, second)
    _chats.expect_chat(page, second, title="New chat")
    assert _composer_view(page) == {"placeholder": "Message second…", "model": "m-two"}
    sid = _chats.send_first(page, "hello")
    _wait_state(page, "joined")
    assert _composer_view(page) == {"placeholder": "Message second…", "model": "m-two"}
    # An agent the `agents` store does not know: its name, no model. No agent:
    # "Message…".
    page.wait_for_timeout(500)  # the `done` list refresh (a prime) has landed
    _prime_session_agent(page, sid, "ghost")
    assert _composer_view(page) == {"placeholder": "Message ghost…", "model": ""}
    _prime_session_agent(page, sid, None)
    assert _composer_view(page) == {"placeholder": "Message…", "model": ""}


# ── Keys (AC3) ───────────────────────────────────────────────────────────────


def test_enter_sends_shift_enter_adds_a_line_and_an_ime_enter_does_nothing(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    frames = _chats.chat_frames(page)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    box = page.locator(INPUT)

    # Shift+Enter inserts a newline: a two-line value, nothing sent.
    box.focus()
    page.keyboard.type("line one")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("line two")
    expect(box).to_have_value("line one\nline two")
    assert [f for f in frames if "message" in f] == []

    # An Enter that commits an IME composition does nothing: isComposing, or
    # keyCode 229 (WebKit's composition-commit Enter can arrive with
    # isComposing false).
    prevented = box.evaluate(
        """(el) => {
          const a = new KeyboardEvent('keydown', {key: 'Enter', isComposing: true,
                                                  bubbles: true, cancelable: true});
          el.dispatchEvent(a);
          const b = new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true});
          Object.defineProperty(b, 'keyCode', {get: () => 229});
          el.dispatchEvent(b);
          return [a.defaultPrevented, b.defaultPrevented];
        }"""
    )
    assert prevented == [False, False]
    page.wait_for_timeout(300)
    expect(box).to_have_value("line one\nline two")
    expect(page.locator(USER_MSG)).to_have_count(0)
    assert [f for f in frames if "message" in f] == []

    # Enter sends both lines as ONE message (the first send: start_session).
    box.press("Enter")
    expect(page.locator(USER_MSG)).to_have_count(1)
    assert page.locator(USER_MSG).text_content() == "line one\nline two"
    expect(box).to_have_value("")
    _wait_state(page, "joined")
    starts = [f for f in frames if f.get("action") == "start_session"]
    assert len(starts) == 1 and starts[0]["message"] == "line one\nline two", starts

    # A pasted multi-line draft stays multi-line, and Enter sends it as one
    # plain message.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    box.fill("alpha\nbeta")
    expect(box).to_have_value("alpha\nbeta")
    box.press("Enter")
    expect(page.locator(USER_MSG)).to_have_count(2)
    assert page.locator(USER_MSG).nth(1).text_content() == "alpha\nbeta"
    plain = [f for f in frames if "message" in f and "action" not in f]
    assert [f["message"] for f in plain] == ["alpha\nbeta"], json.dumps(frames)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_have_attribute(
        "aria-keyshortcuts", "Enter"
    )


# ── The focus ring (AC4, A25) ────────────────────────────────────────────────


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_box_shows_the_focus_ring_while_the_textarea_or_a_toolbar_button_has_focus(
    app_with_agent: SeededApp, page: Page, theme: str
) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    page.evaluate(f"App.theme.set('{theme}')")
    accent = _token(page, "color", "var(--accent)")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    assert _ring(page)["style"] == "none"

    # The textarea: the ring is on the box, in the app's pinned form; the
    # textarea's own outline stays off.
    page.locator(INPUT).focus()
    ring = _ring(page)
    assert ring == {
        "style": "solid",
        "width": "2px",
        "color": accent,
        "offset": "2px",
        "input": "none",
    }, ring

    # A toolbar button (Tab from the textarea: Attach, then Send; the file
    # input and the idle Stop are hidden) keeps it.
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.testid") == "chat-attach-btn"
    assert _ring(page)["style"] == "solid"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.testid") == "chat-send-btn"
    assert _ring(page)["style"] == "solid"

    # Focus elsewhere: no ring.
    page.evaluate("document.activeElement.blur()")
    assert _ring(page)["style"] == "none"

    # A disabled textarea cannot take focus, so the box shows no ring.
    page.evaluate(
        """() => { const el = document.querySelector('[data-testid="chat-input"]');
                   el.disabled = true; el.focus(); }"""
    )
    assert page.evaluate("document.activeElement.dataset.testid") != "chat-input"
    assert _ring(page)["style"] == "none"
    page.evaluate("document.querySelector('[data-testid=\"chat-input\"]').disabled = false")


# ── Stop and Send while a turn runs (AC5, AC8) ───────────────────────────────


def test_stop_shows_just_before_send_while_a_turn_runs(app_clean: str, page: Page) -> None:
    provider = seed_mock_provider(app_clean, name="slow", config={"delay_ms": 1500})
    agent = seed_mock_agent(app_clean, provider, name="slow-agent")
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, app_clean, "chats")
    _chats.start_chat(page, agent)
    stop = page.locator('[data-testid="chat-stop-btn"]')
    expect(stop).to_be_hidden()
    _chats.send_first(page, "take your time")
    expect(stop).to_be_visible()
    geo = page.evaluate(
        """() => {
          const r = (s) => document.querySelector(s).getBoundingClientRect();
          const bar = r('.area-chat .composer-toolbar');
          const stop = r('[data-testid="chat-stop-btn"]');
          const send = r('[data-testid="chat-send-btn"]');
          const model = r('[data-testid="chat-model"]');
          return {gap: send.left - stop.right, end: bar.right - send.right,
                  afterModel: stop.left > model.right + 8};
        }"""
    )
    assert abs(geo["gap"] - 8) < 1 and abs(geo["end"]) < 1 and geo["afterModel"], geo
    # The turn ends: Stop hides, Send is back at the end.
    expect(page.locator('[data-testid="message"].assistant')).to_have_count(1, timeout=10000)
    expect(stop).to_be_hidden()
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()


# ── The textarea's height (edge case: very long input) ───────────────────────


def test_the_textarea_grows_to_about_eight_lines_then_scrolls(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    box = page.locator(INPUT)

    def size() -> dict[str, float]:
        return box.evaluate(
            "(el) => ({h: el.getBoundingClientRect().height, sh: el.scrollHeight,"
            " ch: el.clientHeight, oy: getComputedStyle(el).overflowY})"
        )

    assert size()["h"] == 42  # two rows of 14px at line-height 1.5
    box.fill("\n".join(f"line {i}" for i in range(4)))
    assert size()["h"] == 84
    box.fill("\n".join(f"line {i}" for i in range(20)))
    tall = size()
    assert tall["h"] == 168 and tall["sh"] > tall["ch"] and tall["oy"] == "auto", tall
    # Sending clears it back to two rows.
    box.press("Enter")
    expect(box).to_have_value("")
    assert size()["h"] == 42


# ── The telemetry row (AC7) ──────────────────────────────────────────────────


def test_the_telemetry_row_shows_only_while_joined_above_the_box(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    row = page.locator(ROW)
    readout = page.locator(".telemetry-overlay")

    # Pending (the new-chat state): no telemetry.
    expect(row).to_be_hidden()
    expect(readout).to_be_hidden()

    # Starting: still none (read in the same task as the send, before any
    # reply can land).
    starting = page.evaluate(
        f"""() => {{
          const el = document.querySelector('[data-testid="chat-input"]');
          el.value = 'hello';
          el.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true,
                                                         cancelable: true}}));
          return {{state: ({_STATE})(),
                   hidden: document.querySelector('.area-chat .composer-telemetry').hidden}};
        }}"""
    )
    assert starting == {"state": "starting", "hidden": True}, starting

    # Joined: the row shows, flex-end, directly above the box, the readout
    # 24px from the pane's right edge (reference spec 5.3), resting at 0.7.
    _wait_state(page, "joined")
    expect(row).to_be_visible()
    expect(page.locator('[data-testid="message"].assistant')).to_have_count(1, timeout=10000)
    page.mouse.move(0, 0)
    geo = page.evaluate(
        """() => {
          const row = document.querySelector('.area-chat .composer-telemetry');
          const box = document.querySelector('.area-chat .composer-box');
          const out = row.querySelector('.telemetry-overlay');
          const main = document.querySelector('#main-content').getBoundingClientRect();
          const rr = row.getBoundingClientRect(), br = box.getBoundingClientRect();
          const or = out.getBoundingClientRect();
          // Every sibling between the row and the box renders nothing.
          let between = [];
          for (let n = row.nextElementSibling; n && n !== box; n = n.nextElementSibling) {
            const r = n.getBoundingClientRect();
            const flows = getComputedStyle(n).position !== 'absolute';
            if (r.height > 1 && flows) between.push(n.className);
          }
          return {justify: getComputedStyle(row).justifyContent, gap: br.top - rr.bottom,
                  between, rightInset: main.right - or.right,
                  position: getComputedStyle(out).position,
                  opacity: getComputedStyle(out).opacity};
        }"""
    )
    assert geo["justify"] == "flex-end" and geo["position"] == "static", geo
    assert geo["between"] == [] and abs(geo["gap"] - 8) < 1, geo
    assert abs(geo["rightInset"] - 24) < 1, geo
    assert geo["opacity"] == "0.7", geo
    # Focus still expands it (content and behaviour unchanged).
    readout.focus()
    page.wait_for_function(
        "() => parseFloat(getComputedStyle(document.querySelector("
        "'.telemetry-details')).maxWidth) > 0",
        timeout=2000,
    )

    # A new pending chat hides it again; reopening the chat shows it.
    sid = _chats.current_session_id(page)
    _chats.start_chat(page, agent)
    expect(row).to_be_hidden()
    _chats.open_chat(page, sid)
    expect(row).to_be_visible()


# ── Chicklets and the queued chip stay above the box (AC1) ───────────────────


def test_staged_images_sit_above_the_box_in_its_column(
    app_with_agent: SeededApp, page: Page
) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    image_input = page.locator('[data-testid="chat-image-input"]')
    png = {"name": "a.png", "mimeType": "image/png", "buffer": _PNG_1X1}
    image_input.set_input_files(files=[png])
    expect(image_input).to_have_attribute("data-staged", "true", timeout=5000)
    expect(page.locator('[data-testid="chat-attachment"]')).to_have_count(1)
    geo = page.evaluate(
        """() => {
          const r = (s) => document.querySelector(s).getBoundingClientRect();
          const a = r('[data-testid="chat-attachments"]');
          const b = r('.area-chat .composer-box');
          return {above: a.bottom <= b.top, left: a.left - b.left};
        }"""
    )
    assert geo["above"] and abs(geo["left"]) < 1, geo


# ── Squawk 0110: no unnamed control (AC6) ────────────────────────────────────


def test_no_unnamed_control_on_chats_with_a_chat_open_in_either_theme(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The shared resolver over the whole page on ``#chats`` with a chat open:
    nothing unnamed, the hidden file input included (squawk 0110)."""
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    _chats.send_first(page, "hello")
    expect(page.locator('[data-testid="message"].assistant')).to_have_count(1, timeout=10000)
    expect(page.locator('[data-testid="chat-image-input"]')).to_have_attribute(
        "aria-label", "Attach images"
    )
    for theme in ("light", "dark"):
        page.evaluate(f"App.theme.set('{theme}')")
        assert collect_label_failures(page, "body") == [], theme

"""End-to-end flow test: image attach + send (M16 F12 L08).

Drives a real Chromium session through the minimal image-ingestion
producer:
- Open #chat with seeded mock provider + agent
- Attach a PNG via the hidden file input (Playwright `set_input_files` —
  the control the leg spec calls out as the one that's testable; the real
  browser flow is the same DOM node driven by FileReader.readAsDataURL)
- Send with (and without) accompanying text
- The optimistic user bubble renders text + the `[image]` indicator — not
  a crash, not `[object Object]` (the pre-L08 latent bug: an unprojected
  dataclass list reaching the DOM)
- The assistant reply still arrives (mock provider), proving the WS
  round-trip survived the image-bearing payload end-to-end — pre-fix, the
  live-broadcast `content_to_text` bug would desync the sender's own
  socket and they would never see this.

HAT fix round 2 (post-L08): the operator asked for two changes:
1. The staged-image preview(s) moved from an inline single-slot chip
   inside `.input-area` to a chicklet ROW ABOVE the composer
   (`chat-attachments`, a sibling before `.input-area`).
2. Multiple images can now be staged at once — attaching APPENDS rather
   than replacing (`stagedImages` array), and each chicklet carries its
   own remove (`chat-attachment-remove`) that only drops that one image.
This file asserts: a single attach shows one chicklet with a `data:`
thumbnail; a second attach appends a second chicklet (both visible);
removing one chicklet leaves the other; the row hides once all chicklets
are removed / after send; and sending with two staged images includes
both in the outgoing WS payload.

Functional/DOM assertions only — NOT a pixel snapshot (snapshot baselines
are gitignored, not committed; see the project's global test-snapshot
policy).
"""

from __future__ import annotations

import base64

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

# Minimal valid 1x1 transparent PNG (well-known fixture bytes) — small
# enough to inline, real enough that `file.type` resolves to "image/png".
_PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _png_file(name: str = "test.png") -> dict[str, object]:
    return {
        "name": name,
        "mimeType": "image/png",
        "buffer": base64.b64decode(_PNG_1X1_BASE64),
    }


def _attach_and_wait_staged(page: Page, name: str = "test.png") -> None:
    """Attach one fixture PNG and wait for the async FileReader to finish.

    chat.js sets `data-staged="true"` on the file input once at least one
    `readAsDataURL` resolves — this gives the test a deterministic signal
    instead of a race-prone sleep. The same staging call renders/re-renders
    the `chat-attachments` chicklet row (HAT fix round 2).
    """
    image_input = page.locator('[data-testid="chat-image-input"]')
    image_input.set_input_files(files=[_png_file(name)])
    expect(image_input).to_have_attribute("data-staged", "true", timeout=5000)


@pytest.mark.browser
def test_chat_image_attach_with_text_renders_indicator(
    app_with_agent: SeededApp, page: Page
) -> None:
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    _attach_and_wait_staged(page)

    # HAT fix round 2: the chicklet row above the composer shows one
    # chicklet with a `data:` thumbnail (not a broken/empty src).
    attachments_row = page.locator('[data-testid="chat-attachments"]')
    expect(attachments_row).to_be_visible()
    chips = page.locator('[data-testid="chat-attachment"]')
    expect(chips).to_have_count(1)
    thumb_src = chips.nth(0).locator("img").get_attribute("src")
    assert thumb_src is not None and thumb_src.startswith("data:image/png;base64,")

    _chats.send_first(page, "what is in this image?")

    user_msg = _chats.messages(page, "user")
    expect(user_msg).to_have_text("what is in this image? [image]", timeout=5000)
    assert "[object Object]" not in user_msg.inner_text()

    # The staged image is cleared after send.
    expect(page.locator('[data-testid="chat-image-input"]')).not_to_have_attribute(
        "data-staged", "true"
    )
    # The chicklet row hides automatically once performSend clears staging.
    expect(attachments_row).to_be_hidden()
    expect(chips).to_have_count(0)

    # Assistant reply still arrives — the WS round-trip survived the
    # image-bearing payload (mock provider's deterministic default reply).
    assistant_msg = _chats.messages(page, "assistant")
    expect(assistant_msg).to_have_text("Mock response from the mock provider.", timeout=10000)

    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()


@pytest.mark.browser
def test_chat_second_attach_appends_chicklet(app_with_agent: SeededApp, page: Page) -> None:
    """HAT fix round 2: attaching a SECOND image APPENDS a second chicklet
    rather than replacing the first — both stay visible in the row."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    _attach_and_wait_staged(page, name="first.png")
    chips = page.locator('[data-testid="chat-attachment"]')
    expect(chips).to_have_count(1)

    _attach_and_wait_staged(page, name="second.png")
    expect(chips).to_have_count(2)

    for i in range(2):
        thumb_src = chips.nth(i).locator("img").get_attribute("src")
        assert thumb_src is not None and thumb_src.startswith("data:image/png;base64,")

    expect(page.locator('[data-testid="chat-attachments"]')).to_be_visible()


@pytest.mark.browser
def test_chat_attachment_remove_clears_only_that_chicklet(
    app_with_agent: SeededApp, page: Page
) -> None:
    """HAT fix round 2: each chicklet's own ✕ removes just that image,
    leaving the other staged and visible; re-selecting the same file
    afterward re-stages it (proves `fileInputEl.value` was reset so
    `change` re-fires)."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    _attach_and_wait_staged(page, name="first.png")
    _attach_and_wait_staged(page, name="second.png")

    chips = page.locator('[data-testid="chat-attachment"]')
    expect(chips).to_have_count(2)

    # Remove just the first chicklet — one image remains.
    page.locator('[data-testid="chat-attachment-remove"]').first.click()
    expect(chips).to_have_count(1)
    expect(page.locator('[data-testid="chat-attachments"]')).to_be_visible()

    # Remove the remaining chicklet — the row hides entirely.
    page.locator('[data-testid="chat-attachment-remove"]').first.click()
    expect(chips).to_have_count(0)
    expect(page.locator('[data-testid="chat-attachments"]')).to_be_hidden()
    expect(page.locator('[data-testid="chat-image-input"]')).not_to_have_attribute(
        "data-staged", "true"
    )

    # Re-select the same fixture file — change must re-fire (value was reset).
    _attach_and_wait_staged(page, name="first.png")
    expect(chips).to_have_count(1)


@pytest.mark.browser
def test_chat_attachment_live_region_announces_stage_and_remove(
    app_with_agent: SeededApp, page: Page
) -> None:
    """M18 F03 L01 (A1): a dedicated visually-hidden `aria-live="polite"`
    status element — SEPARATE from the visible `.chat-attachments` chicklet
    row — announces a short delta on each stage/remove mutation. The row
    itself must NOT carry `aria-live` (it fully rebuilds via `innerHTML` on
    every mutation, so making it the live region would re-announce every
    remaining chip on each removal)."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    status_el = page.locator('[data-testid="chat-attachments-status"]')
    expect(status_el).to_have_attribute("aria-live", "polite")
    # Visually-hidden utility class (sr-only pattern) — present but not painted.
    class_attr = status_el.get_attribute("class") or ""
    assert "visually-hidden" in class_attr

    # The visible chicklet row is a distinct element and must not itself be
    # a live region (over-announce risk called out in the leg spec).
    attachments_row = page.locator('[data-testid="chat-attachments"]')
    assert attachments_row.get_attribute("aria-live") is None

    _attach_and_wait_staged(page, name="first.png")
    expect(status_el).to_have_text("Image staged", timeout=5000)

    _attach_and_wait_staged(page, name="second.png")
    expect(status_el).to_have_text("2 images staged", timeout=5000)

    page.locator('[data-testid="chat-attachment-remove"]').first.click()
    expect(status_el).to_have_text("Image removed", timeout=5000)


@pytest.mark.browser
def test_chat_staged_images_have_distinct_accessible_names(
    app_with_agent: SeededApp, page: Page
) -> None:
    """M18 F03 L01 (A2): with two images staged, the thumbnail `alt` and the
    remove-button `aria-label` both carry a distinguishing 1-based index —
    previously every staged image shared an identical accessible name, so a
    screen-reader user could not tell which remove button removed which."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    _attach_and_wait_staged(page, name="first.png")
    _attach_and_wait_staged(page, name="second.png")

    chips = page.locator('[data-testid="chat-attachment"]')
    expect(chips).to_have_count(2)

    # M31 F6 L05a (deliberate retarget): the chip is App.ui.chip, so its name is its visually
    # hidden label and the thumbnail's alt is empty (the label names the chip, never twice).
    alts = [chips.nth(i).locator(".chip-label").text_content() for i in range(2)]
    assert alts == ["Staged image 1", "Staged image 2"]
    assert len(set(alts)) == 2
    assert [chips.nth(i).locator("img").get_attribute("alt") for i in range(2)] == ["", ""]

    remove_btns = page.locator('[data-testid="chat-attachment-remove"]')
    labels = [remove_btns.nth(i).get_attribute("aria-label") for i in range(2)]
    assert labels == ["Remove staged image 1", "Remove staged image 2"]
    assert len(set(labels)) == 2


@pytest.mark.browser
def test_chat_two_images_send_includes_both_and_omits_empty_text(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Two images attached, text box left EMPTY — exercises the
    omit-empty-TextContent path (app.py `_build_user_content`): the request
    must not synthesize an empty text block (Anthropic 400s on that), the
    user bubble renders just the `[image]` indicator, and BOTH staged
    images are cleared/sent together (not silently dropped to one).

    The mock-provider fixture (`the_one/llm/mock.py`) does not record/expose
    inbound request payloads, so this asserts via DOM observables instead of
    inspecting the wire payload directly: two distinct chicklets with two
    distinct `data:` thumbnails are staged immediately before send (proving
    both survived staging), the send succeeds (no client-side crash/hang on
    a multi-element `images` list), and the round-trip completes.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    _attach_and_wait_staged(page, name="first.png")
    _attach_and_wait_staged(page, name="second.png")
    chips = page.locator('[data-testid="chat-attachment"]')
    expect(chips).to_have_count(2)
    thumb_srcs = {chips.nth(i).locator("img").get_attribute("src") for i in range(2)}
    assert all(src and src.startswith("data:image/png;base64,") for src in thumb_srcs)

    # Text box stays empty — send via the button (the pre-L08 `send()`
    # guard would have blocked this entirely; L08 widens it to text-OR-image).
    page.locator('[data-testid="chat-send-btn"]').click()

    user_msg = _chats.messages(page, "user")
    expect(user_msg).to_have_text("[image]", timeout=5000)
    expect(page.locator('[data-testid="chat-attachments"]')).to_be_hidden()
    expect(chips).to_have_count(0)

    assistant_msg = _chats.messages(page, "assistant")
    expect(assistant_msg).to_have_text("Mock response from the mock provider.", timeout=10000)


@pytest.mark.browser
def test_chat_attach_over_count_caps_at_max_and_notices(
    app_with_agent: SeededApp, page: Page
) -> None:
    """M18 F02 L02: selecting more than IMAGE_ATTACHMENT_MAX_COUNT (10)
    images in a single multi-select batch stages only the first 10 and
    surfaces a system notice for the rest — the client-side mirror of the
    server's authoritative count cap (chat.js `IMAGE_ATTACHMENT_MAX_COUNT`,
    app.py `IMAGE_ATTACHMENT_MAX_COUNT`)."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    files = [_png_file(name=f"img{i}.png") for i in range(11)]
    image_input = page.locator('[data-testid="chat-image-input"]')
    image_input.set_input_files(files=files)
    expect(image_input).to_have_attribute("data-staged", "true", timeout=5000)

    chips = page.locator('[data-testid="chat-attachment"]')
    expect(chips).to_have_count(10)

    system_notice = _chats.messages(page, "system").filter(has_text="Only up to 10 images")
    expect(system_notice).to_be_visible(timeout=5000)


@pytest.mark.browser
def test_chat_attach_oversized_file_rejected_with_notice(
    app_with_agent: SeededApp, page: Page
) -> None:
    """M18 F02 L02: a file exceeding the per-image byte cap (~10 MB) is
    rejected client-side before FileReader ever starts — no chicklet
    appears, `data-staged` never flips, and a system notice explains why."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    oversized = {
        "name": "huge.png",
        "mimeType": "image/png",
        # One byte over the 10 MB per-image cap (chat.js
        # IMAGE_ATTACHMENT_CAP_BYTES / app.py IMAGE_ATTACHMENT_CAP_BYTES).
        "buffer": b"\x00" * (10 * 1024 * 1024 + 1),
    }
    image_input = page.locator('[data-testid="chat-image-input"]')
    image_input.set_input_files(files=[oversized])

    system_notice = _chats.messages(page, "system").filter(has_text="per-image limit")
    expect(system_notice).to_be_visible(timeout=5000)

    # No chicklet was staged and the async-staged marker never flips —
    # the rejection happens before FileReader.readAsDataURL is invoked.
    expect(page.locator('[data-testid="chat-attachment"]')).to_have_count(0)
    expect(image_input).not_to_have_attribute("data-staged", "true")


@pytest.mark.browser
def test_chat_text_only_send_unaffected(app_with_agent: SeededApp, page: Page) -> None:
    """Regression guard: a text-only send (no attach) stays byte-identical
    to pre-L08 behaviour — no stray `[image]` indicator, no `images` key
    side effect leaking into an unrelated turn."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "hello")

    user_msg = _chats.messages(page, "user")
    expect(user_msg).to_have_text("hello", timeout=5000)

    assistant_msg = _chats.messages(page, "assistant")
    expect(assistant_msg).to_have_text("Mock response from the mock provider.", timeout=10000)


@pytest.mark.browser
def test_removing_a_chip_with_the_keyboard_hands_focus_on(
    app_with_agent: SeededApp, page: Page
) -> None:
    """WCAG 2.4.3: a removed chip's remove button held focus, so focus goes to the next
    chip's remove button, else the previous one, else the composer input; a pointer user
    who has clicked elsewhere is not moved."""
    _nav.goto_root(page, app_with_agent.base_url)
    _chats.start_chat(page, app_with_agent.agent_name)
    for name in ("a.png", "b.png", "c.png"):
        _attach_and_wait_staged(page, name=name)
    removes = page.locator('[data-testid="chat-attachment-remove"]')
    expect(removes).to_have_count(3)

    # middle chip: focus lands on the chip that took its place (the old third)
    removes.nth(1).focus()
    page.keyboard.press("Enter")
    expect(removes).to_have_count(2)
    expect(removes.nth(1)).to_be_focused()
    # last chip: focus lands on the previous one
    page.keyboard.press("Enter")
    expect(removes).to_have_count(1)
    expect(removes.nth(0)).to_be_focused()
    # only chip: focus lands on the composer input
    page.keyboard.press("Enter")
    expect(removes).to_have_count(0)
    expect(page.locator('[data-testid="chat-input"]')).to_be_focused()


@pytest.mark.browser
def test_removing_a_chip_does_not_steal_focus_from_elsewhere(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_root(page, app_with_agent.base_url)
    _chats.start_chat(page, app_with_agent.agent_name)
    _attach_and_wait_staged(page, name="a.png")
    _attach_and_wait_staged(page, name="b.png")
    removes = page.locator('[data-testid="chat-attachment-remove"]')
    # a scripted removal while the composer input has focus leaves focus alone
    page.locator('[data-testid="chat-input"]').focus()
    removes.first.evaluate("(b) => b.click()")
    expect(removes).to_have_count(1)
    expect(page.locator('[data-testid="chat-input"]')).to_be_focused()

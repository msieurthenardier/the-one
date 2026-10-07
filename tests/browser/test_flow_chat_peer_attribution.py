"""Browser test for M11 F06 L04 — chat-ui-attribution.

Verifies that USER messages persisted with ``Message.peer_name`` render
with:
- the ``msg-from-peer`` class on the bubble (left-aligned via the CSS
  override declared after ``.area-chat .msg.user`` — same specificity,
  last-rule-wins);
- an attribution element with class ``msg-attribution from-peer`` whose
  text is the peer's display name;
- ``getComputedStyle(...).alignSelf === 'flex-start'`` (verifies the
  source-order CSS override actually wins over ``.msg.user``'s
  ``flex-end``).

Operator-typed user bubbles (no ``peer_name``) keep their pre-leg
``.msg.user`` (right-aligned) + ``.from-you`` attribution rendering.

Composition with the operator-only marker (M10 F05 L05 + L08 HAT) is
preserved: assistant bubbles tagged ``visibility=operator`` still carry
``.msg-operator-only``; peer user bubbles and operator-typed user
bubbles do NOT (the JS gate skips the marker on user bubbles).

Per user-global rule (no committed snapshot baselines), this test
uses DOM-shape + computed-style assertions only.

``app_with_data_dir`` is the shared fixture in ``browser/conftest.py``
(Mission 20 / Flight 1 / Leg 3 consolidated it out of this file's former
local duplicate). ``_seed_session_with_messages`` remains local — its
message-shape is specific to this test's fixture data.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path

import pytest
from browser import _chats
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import OPERATOR_VISIBILITY, Message

# `app_with_data_dir` (Mission 20 / Flight 1 / Leg 3): formerly a local
# fixture duplicated verbatim across 8 `test_flow_*.py` files, now
# consolidated onto the shared `_spawn_app` path in `browser/conftest.py`
# — pytest auto-discovers it from the directory conftest, no import needed.


def _seed_session_with_messages(
    data_dir: Path,
    *,
    session_id: str,
    agent_name: str,
    messages_json: str,
) -> None:
    """INSERT a chat_sessions row directly via sqlite3.

    Synchronous sqlite3 (not aiosqlite) — runs in the test runner
    process; the app subprocess opens the DB lazily through the WS join
    path. SQLite file-locking handles the read-after-write cross-process.
    """
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            (session_id, agent_name, "peer attribution test", messages_json),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.browser
def test_chat_renders_peer_attribution(
    app_with_data_dir: tuple[str, Path],
    page: Page,
) -> None:
    """A seeded session with mixed operator-typed + peer-attributed USER
    messages renders peer bubbles with msg-from-peer + from-peer
    attribution, while operator-typed user bubbles keep their
    .msg.user (right-aligned) + from-you rendering.

    Acceptance criteria coverage:
    - ``.msg.user.msg-from-peer`` count == 2 (USER #2 alice + USER #3 bob).
    - ``.msg.user:not(.msg-from-peer)`` count == 1 (USER #1 operator).
    - First peer bubble's attribution: ``.from-peer`` text ``'alice'``.
    - Second peer bubble's attribution: ``.from-peer`` text ``'bob'``.
    - Operator-typed user bubble's attribution: ``.from-you`` text
      ``'You'``.
    - Computed ``alignSelf`` on peer bubble == ``'flex-start'`` (the CSS
      override wins over ``.msg.user``'s ``flex-end``).
    - Computed ``alignSelf`` on operator-typed user bubble ==
      ``'flex-end'`` (unchanged).
    - Visibility composition: assistant bubble has ``.msg-operator-only``;
      peer bubbles + operator-typed user bubble do NOT (existing F5 L8
      HAT decision preserved).
    """
    base_url, data_dir = app_with_data_dir

    # Seed provider + agent via API (same path as app_with_agent fixture).
    provider_id = seed_mock_provider(base_url)
    agent_name = seed_mock_agent(base_url, provider_id)

    # Build a mixed-attribution messages blob via Message + the codec —
    # never hand-craft the JSON.
    msgs = [
        Message.system("you are a test agent"),
        # USER #1: operator-typed (no peer_name; visibility=operator)
        Message.user("operator typing", visibility=OPERATOR_VISIBILITY),
        # USER #2: peer-attributed (visibility=None per the visibility
        # tagger in llm/base.py, which skips Role.USER)
        Message.user("hey @bot ping?", peer_name="alice"),
        # ASSISTANT (operator-visibility, gets the marker)
        Message.assistant("pong", visibility=OPERATOR_VISIBILITY),
        # USER #3: second peer (verifies two distinct peers in one session)
        Message.user("another one", peer_name="bob"),
    ]
    encoded = encode_messages(msgs)

    session_id = str(uuid.uuid4())
    _seed_session_with_messages(
        data_dir,
        session_id=session_id,
        agent_name=agent_name,
        messages_json=encoded,
    )

    # Deep-link to the seeded session.
    page.goto(f"{base_url}#chat/sessions/{session_id}")  # legacy URL on purpose (AC6)

    # Wait for the chat chrome (deep-link path renders straight into chrome).
    _chats.expect_chat(page, agent_name)

    # Wait for messages to render — at least one .msg bubble.
    expect(page.locator(".msg").first).to_be_visible(timeout=5000)

    # Wait for ALL four expected bubbles (3 user + 1 assistant) to render.
    expect(page.locator(".msg.user")).to_have_count(3, timeout=5000)
    expect(page.locator(".msg.assistant")).to_have_count(1, timeout=5000)

    # Assertion 1: peer bubble count.
    peer_bubbles = page.locator(".msg.user.msg-from-peer")
    expect(peer_bubbles).to_have_count(2)

    # Assertion 2: operator-typed user bubble count.
    # CSS-spec :not(.x) is well-supported; locator passes it through.
    operator_user_bubbles = page.locator(".msg.user:not(.msg-from-peer)")
    expect(operator_user_bubbles).to_have_count(1)

    # Assertion 3: first peer bubble's immediately-following attribution
    # element has class 'msg-attribution from-peer' and text starting with
    # 'alice'. Since the message-timestamp-on-replay fix (PR #159,
    # 8b02669), Message.user()/assistant() persist created_at and the codec
    # projects it as `ts` on replay, so restored attributions render with a
    # ' · h:mm AM/PM' suffix — assert prefix + suffix shape, not bare
    # equality (this test predated the fix and was asserting the pre-fix
    # bare-name rendering; caught stale in M19 F01 L03's full-suite run).
    first_peer = peer_bubbles.nth(0)
    first_peer_attr = first_peer.evaluate(
        """el => {
            const next = el.nextElementSibling;
            return next ? {
                cls: next.className,
                text: next.textContent,
            } : null;
        }"""
    )
    assert first_peer_attr is not None, "first peer bubble has no following attribution element"
    assert "msg-attribution" in first_peer_attr["cls"], (
        "expected msg-attribution class on first peer attribution, got "
        f"cls={first_peer_attr['cls']!r}"
    )
    assert "from-peer" in first_peer_attr["cls"], (
        f"expected from-peer class on first peer attribution, got cls={first_peer_attr['cls']!r}"
    )
    assert re.fullmatch(r"alice( · \d{1,2}:\d{2} [AP]M)?", first_peer_attr["text"]), (
        f"expected first peer attribution 'alice' (+ optional ' · h:mm AM/PM' "
        f"timestamp suffix), got {first_peer_attr['text']!r}"
    )

    # Assertion 4: second peer bubble's attribution is 'bob' and from-peer.
    second_peer = peer_bubbles.nth(1)
    second_peer_attr = second_peer.evaluate(
        """el => {
            const next = el.nextElementSibling;
            return next ? {
                cls: next.className,
                text: next.textContent,
            } : null;
        }"""
    )
    assert second_peer_attr is not None, "second peer bubble has no following attribution element"
    assert "from-peer" in second_peer_attr["cls"], (
        f"expected from-peer class on second peer attribution, got cls={second_peer_attr['cls']!r}"
    )
    assert re.fullmatch(r"bob( · \d{1,2}:\d{2} [AP]M)?", second_peer_attr["text"]), (
        f"expected second peer attribution 'bob' (+ optional ' · h:mm AM/PM' "
        f"timestamp suffix), got {second_peer_attr['text']!r}"
    )

    # Assertion 5: operator-typed user bubble's attribution is 'You' on
    # the from-you side.
    op_user = operator_user_bubbles.first
    op_user_attr = op_user.evaluate(
        """el => {
            const next = el.nextElementSibling;
            return next ? {
                cls: next.className,
                text: next.textContent,
            } : null;
        }"""
    )
    assert op_user_attr is not None, "operator-typed user bubble has no following attribution"
    assert "from-you" in op_user_attr["cls"], (
        f"expected from-you class on operator-typed attribution, got cls={op_user_attr['cls']!r}"
    )
    assert re.fullmatch(r"You( · \d{1,2}:\d{2} [AP]M)?", op_user_attr["text"]), (
        f"expected operator-typed attribution 'You' (+ optional ' · h:mm AM/PM' "
        f"timestamp suffix), got {op_user_attr['text']!r}"
    )

    # Assertion 6: computed style on the peer bubble — the source-order
    # CSS override should flip align-self to flex-start.
    peer_align = first_peer.evaluate("el => getComputedStyle(el).alignSelf")
    assert peer_align == "flex-start", (
        f"peer bubble align-self should be 'flex-start' (CSS source-order "
        f"override after .msg.user), got {peer_align!r}"
    )

    # Assertion 7: computed style on the operator-typed user bubble —
    # the base .msg.user rule should still apply, keeping flex-end.
    op_align = op_user.evaluate("el => getComputedStyle(el).alignSelf")
    assert op_align == "flex-end", (
        f"operator-typed user bubble align-self should be 'flex-end', got {op_align!r}"
    )

    # Assertion 8: visibility composition — the assistant bubble carries
    # .msg-operator-only (visibility=operator); the peer bubbles do not
    # (peer-inbound users have visibility=None per visibility.py:60);
    # the operator-typed user bubble does not (F5 L8 HAT suppresses the
    # marker on user bubbles even when visibility=operator).
    assistant_has_marker = page.locator(".msg.assistant").first.evaluate(
        "el => el.classList.contains('msg-operator-only')"
    )
    assert assistant_has_marker is True, (
        "assistant bubble should carry .msg-operator-only (visibility=operator persisted by codec)"
    )

    for i in range(2):
        peer_has_marker = peer_bubbles.nth(i).evaluate(
            "el => el.classList.contains('msg-operator-only')"
        )
        assert peer_has_marker is False, (
            f"peer bubble #{i} unexpectedly carries .msg-operator-only — "
            "peer-inbound users have visibility=None by construction"
        )

    op_user_has_marker = op_user.evaluate("el => el.classList.contains('msg-operator-only')")
    assert op_user_has_marker is False, (
        "operator-typed user bubble unexpectedly carries .msg-operator-only — "
        "the F5 L8 HAT decision suppresses the marker on user bubbles."
    )

    # Assertion 9 (M11 F06 L04 a11y follow-up — WCAG 1.3.3 / 1.4.1):
    # Each peer bubble must contain a visually-hidden screen-reader label
    # `<span class="msg-from-peer-label visually-hidden">From {peerName}: </span>`
    # prepended BEFORE the message text. Without this, assistive technology
    # cannot distinguish a peer message from an operator-typed message
    # (both are <div class="msg user">{text}</div> to AT; the differentiators
    # are visual-only — left/right alignment + background color).
    first_peer_label = first_peer.evaluate(
        """el => {
            const lbl = el.querySelector('.msg-from-peer-label');
            return lbl ? {
                cls: lbl.className,
                text: lbl.textContent,
                clip: getComputedStyle(lbl).clip,
                clipPath: getComputedStyle(lbl).clipPath,
                position: getComputedStyle(lbl).position,
                width: getComputedStyle(lbl).width,
                height: getComputedStyle(lbl).height,
            } : null;
        }"""
    )
    assert first_peer_label is not None, (
        "first peer bubble is missing the .msg-from-peer-label span "
        "(WCAG 1.3.3 / 1.4.1 — screen readers need an explicit 'From alice: ' "
        "announcement; visual alignment alone is insufficient)."
    )
    assert "visually-hidden" in first_peer_label["cls"], (
        f"expected .msg-from-peer-label to also carry .visually-hidden, "
        f"got cls={first_peer_label['cls']!r}"
    )
    assert first_peer_label["text"] == "From alice: ", (
        f"expected first peer label text 'From alice: ', got {first_peer_label['text']!r}"
    )
    # Verify the visually-hidden utility actually hides the span from sighted
    # users (sr-only pattern collapses to a 1×1 clipped box). Browsers report
    # the legacy `clip: rect(0px, 0px, 0px, 0px)` for our admin.css /
    # chat.css rule; `clip-path: inset(50%)` is the modern alternative. Accept
    # either so the test isn't brittle to a future utility-class lift.
    rect_clip = first_peer_label["clip"] == "rect(0px, 0px, 0px, 0px)"
    inset_clip_path = first_peer_label["clipPath"] == "inset(50%)"
    assert rect_clip or inset_clip_path, (
        f"expected .visually-hidden to clip the label (rect(0,0,0,0) or "
        f"inset(50%)); got clip={first_peer_label['clip']!r} "
        f"clipPath={first_peer_label['clipPath']!r}. Verify the utility class "
        f"is actually loaded on the chat page."
    )

    second_peer_label = second_peer.evaluate(
        """el => {
            const lbl = el.querySelector('.msg-from-peer-label');
            return lbl ? { cls: lbl.className, text: lbl.textContent } : null;
        }"""
    )
    assert second_peer_label is not None, (
        "second peer bubble is missing the .msg-from-peer-label span"
    )
    assert "visually-hidden" in second_peer_label["cls"], (
        f"expected second .msg-from-peer-label to carry .visually-hidden, "
        f"got cls={second_peer_label['cls']!r}"
    )
    assert second_peer_label["text"] == "From bob: ", (
        f"expected second peer label text 'From bob: ', got {second_peer_label['text']!r}"
    )

    # Assertion 10 (negative case): the operator-typed user bubble must NOT
    # carry a .msg-from-peer-label — the operator IS the source; there is no
    # peer to announce. Verifies the gate is `opts.peerName` truthiness (not
    # bubble-role).
    op_user_peer_label = op_user.evaluate("el => el.querySelector('.msg-from-peer-label') !== null")
    assert op_user_peer_label is False, (
        "operator-typed user bubble unexpectedly carries a "
        ".msg-from-peer-label — the screen-reader label gate is "
        "opts.peerName, which is falsy for operator-typed input."
    )

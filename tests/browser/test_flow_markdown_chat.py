"""End-to-end browser tests for the F4 leg-05 markdown + streaming integration.

Validates four contracts layered on top of the leg-04 streaming infrastructure:

A. Streaming + markdown — when assistant chunks accumulate, the rendered
   bubble shows plain text mid-stream; on `done`,
   ``finalizeStreamingBubble`` swaps the accumulated text for the
   markdown-rendered DocumentFragment (``**bold**`` → ``<strong>bold</strong>``).

B. User messages stay literal — markdown is assistant-only;
   user / tool / system messages render via ``textContent`` so user-typed
   ``**bold**`` is preserved as visible text (no ``<strong>`` tag).

C. Code-block rendering — a streamed fenced block (`````js``) on
   `done` becomes ``<pre><code class="language-js">`` with the leg-03
   copy-button affordance (``.markdown-copy-btn``) attached.

D. Session-rejoin renders historical assistant markdown — confirms the
   persistence contract (leg 04) carries through the rendering swap
   (leg 05): a streamed markdown response is added to session history
   server-side; on reload, ``renderHistory`` walks the saved events and
   the assistant bubble renders the markdown structure (``<strong>`` etc.).
"""

from __future__ import annotations

import pytest
from browser import _chats
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_streaming_assistant_renders_markdown_on_done(app_clean: str, page: Page) -> None:
    """Assistant message with ``**bold**`` in chunks renders ``<strong>`` on done.

    The mock provider is configured with three chunks
    (``"Hello, "``, ``"**world**"``, ``"!"``) so the agent emits three
    ``assistant_chunk`` events. The chat.js wire-up accumulates them as
    plain text; ``finalizeStreamingBubble()`` on `done` swaps the buffer
    for the markdown-rendered DocumentFragment.
    """
    base_url = app_clean
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["Hello, ", "**world**", "!"],
            "delay_ms": 0,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)

    page.goto(base_url)
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "hi")

    # Wait for `done` to fire (send button re-enables) and assert the
    # markdown structure is in the assistant bubble.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    bubble = page.locator('[data-testid="message"].assistant').last
    # The `**world**` chunk renders as <strong>world</strong> after `done`.
    expect(bubble.locator("strong")).to_have_text("world", timeout=5000)
    # And the raw ``**`` markers no longer appear in the visible text —
    # they were consumed by the markdown renderer.
    expect(bubble).not_to_contain_text("**")


@pytest.mark.browser
def test_user_message_renders_textcontent_not_markdown(app_with_agent, page: Page) -> None:
    """User message containing ``**bold**`` renders as literal text.

    Markdown is assistant-only — the ``shouldRenderAsMarkdown`` helper
    returns false for ``cls === 'user'``, so the user bubble's text
    stays as-is. We assert against ``.first`` because chat.js renders
    the user bubble locally before the WS round-trip; the server may
    broadcast a redundant ``user`` event (rendered as a second bubble)
    but the first-rendered bubble is deterministic.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(base_url)
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "**bold**")

    user_bubble = page.locator('[data-testid="message"].user').first
    expect(user_bubble).to_have_text("**bold**", timeout=5000)
    # The user bubble must NOT contain a <strong> child — markdown
    # rendering is assistant-only.
    expect(user_bubble.locator("strong")).to_have_count(0)


@pytest.mark.browser
def test_streaming_assistant_code_block_renders_with_copy_button(
    app_clean: str, page: Page
) -> None:
    """Streamed fenced code block renders as ``<pre><code>`` with copy button on done.

    The mock provider streams three chunks that together form a properly
    closed `````js`` fence. After ``done``, the assistant bubble's
    DOM contains a ``<pre><code class="language-js">`` element AND a
    ``.markdown-copy-btn`` (the leg-03 copy affordance). We use
    ``to_have_count(1)`` rather than ``to_be_visible`` because the copy
    button is opacity-controlled (visible only on hover/focus), so a
    visibility assertion would have CSS-dependent semantics.
    """
    base_url = app_clean
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["```js\n", "console.log(1);\n", "```"],
            "delay_ms": 0,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)

    page.goto(base_url)
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "show me code")

    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    bubble = page.locator('[data-testid="message"].assistant').last
    expect(bubble.locator("pre code.language-js")).to_have_text("console.log(1);\n", timeout=5000)
    # Presence assertion — the copy button is opacity-controlled, so we
    # assert it exists in the DOM rather than asserting visibility.
    expect(bubble.locator(".markdown-copy-btn")).to_have_count(1)


@pytest.mark.browser
def test_session_rejoin_renders_assistant_markdown(app_clean: str, page: Page) -> None:
    """Reloading the page rejoins the session and renders historical markdown.

    Persistence contract (leg 04) + rendering swap (leg 05): the
    streamed assistant message is added to ``session.history`` via
    ``session.add_event``; on reload, ``renderHistory`` walks the saved
    events and ``addMsg('assistant', ...)`` → ``renderMessage`` → the
    leg-05 markdown default kicks in. Result: the historical bubble
    re-renders with the markdown structure (``<strong>`` etc.).
    """
    base_url = app_clean
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["Some ", "**bold**", " text"],
            "delay_ms": 0,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)

    page.goto(base_url)
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "ping")

    # Wait for the streaming round to land — markdown is rendered on done.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    bubble = page.locator('[data-testid="message"].assistant').last
    expect(bubble.locator("strong")).to_have_text("bold", timeout=5000)

    # Reload — the session id is in the URL hash; the client rejoins
    # and replays history through `renderHistory` → `addMsg('assistant', ...)`.
    page.reload()
    _chats.expect_chat(page, agent_name)
    rejoined_bubble = page.locator('[data-testid="message"].assistant').last
    # Historical assistant bubble re-renders via markdown (leg-05 default).
    expect(rejoined_bubble.locator("strong")).to_have_text("bold", timeout=8000)


@pytest.mark.browser
def test_streaming_assistant_renders_markdown_table(app_clean: str, page: Page) -> None:
    """Assistant message containing a GFM table renders as ``<table>`` on done.

    The mock provider streams three chunks that together form a minimal
    two-column GFM table (header + separator + one data row). After
    ``finalizeStreamingBubble`` fires on ``done``, the assistant bubble
    DOM must contain a ``<table>`` with a ``<thead>`` (header cells) and
    a ``<tbody>`` (data row). The raw pipe characters must no longer appear
    as visible text — they were consumed by the table parser.
    """
    base_url = app_clean
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["| a | b |\n", "| - | - |\n", "| 1 | 2 |"],
            "delay_ms": 0,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)

    page.goto(base_url)
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "show me a table")

    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    bubble = page.locator('[data-testid="message"].assistant').last
    # GFM table must parse into a <table> element.
    expect(bubble.locator("table")).to_have_count(1, timeout=5000)
    # Header cells render as <th>.
    expect(bubble.locator("th").nth(0)).to_have_text("a")
    expect(bubble.locator("th").nth(1)).to_have_text("b")
    # Data cells render as <td>.
    expect(bubble.locator("td").nth(0)).to_have_text("1")
    expect(bubble.locator("td").nth(1)).to_have_text("2")


@pytest.mark.browser
def test_code_copy_toast_is_on_the_page_not_in_the_message_log(app_clean: str, page: Page) -> None:
    """DD9 test 6 / DD11 7: the copy toast lands in the page's flash region, never inside
    the transcript (``.messages``), where it scrolled and was announced with the log."""
    base_url = app_clean
    provider_id = seed_mock_provider(
        base_url,
        config={"stream_chunks": ["```js\n", "console.log(1);\n", "```"], "delay_ms": 0},
    )
    agent_name = seed_mock_agent(base_url, provider_id)
    page.goto(base_url)
    _chats.start_chat(page, agent_name)
    _chats.send_first(page, "show me code")
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    bubble = page.locator('[data-testid="message"].assistant').last
    expect(bubble.locator("pre code.language-js")).to_be_visible(timeout=5000)
    bubble.locator(".markdown-copy-btn").click(force=True)
    expect(page.locator(".app-flash")).to_be_visible(timeout=5000)
    expect(page.locator(".messages .app-flash")).to_have_count(0)
    expect(page.locator(".app-flash-region .app-flash")).to_have_count(1)

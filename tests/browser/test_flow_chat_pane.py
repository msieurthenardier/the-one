"""The Chats detail pane (M25 F4 leg 4b; flight DD3, DD6; reference spec 5.2, 5.4).

The pane is built with DOM APIs (``areas/chat/chat-pane.js``, the composer
``App.ui.composer`` in ``js/ui/composer.js``):

* **the header** (``chat-header``): an ``h1`` with the chat's title -- read
  from the ``sessions`` store by id, so it follows the auto-title, else the
  ``session_joined`` payload's -- or "New chat" while pending or starting, and
  "with {agent}" (``chat-agent-line``); hidden while idle;
* **the new-chat state** (``chat-new-state``), only while pending: a
  ``badge badge--{providerType}`` whose text is the MODEL (A20), the agent name
  (``h2``), the description and "Pick a different agent"
  (``chat-pick-different-btn``);
* **the empty and guidance states** (``chat-welcome``), only while idle with no
  chat to auto-join, never while joining: the "Hello." ``h1``, then the prompt
  and New chat (``chat-empty-new-btn``), or the guidance links;
* exactly one visible ``h1`` in every state, the landmarks and skip link intact,
  and no unnamed control (leg 5 named the hidden ``chat-image-input``, squawk
  0110, so nothing is allow-listed).

The composer itself (leg 5) is ``test_flow_chat_composer.py``.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._a11y_resolvers import collect_label_failures
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

PANEL = ".content-panel.area-chat"

# Holds every session_joined for window.__delayJoined ms and queues every frame
# behind it, delivering them IN ORDER afterwards (as in
# test_flow_chat_start_flow.py: the server never reorders a socket's frames).
_DELAY_JOINED = """
(() => {
  if (window.__delayJoined === undefined) window.__delayJoined = %d;
  const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, 'onmessage');
  Object.defineProperty(WebSocket.prototype, 'onmessage', {
    configurable: true,
    get() { return desc.get.call(this); },
    set(fn) {
      if (typeof fn !== 'function') { desc.set.call(this, fn); return; }
      const sock = this;
      const queue = [];
      let holding = false;
      desc.set.call(this, (e) => {
        if (holding) { queue.push(e); return; }
        let joined = false;
        try { joined = JSON.parse(e.data).type === 'session_joined'; } catch (x) { /* ignore */ }
        const ms = window.__delayJoined || 0;
        if (joined && ms > 0) {
          holding = true;
          queue.push(e);
          setTimeout(() => {
            holding = false;
            queue.splice(0).forEach(ev => fn.call(sock, ev));
          }, ms);
          return;
        }
        fn.call(sock, e);
      });
    },
  });
})();
"""

# Counts every time the welcome is seen un-hidden (a MutationObserver on the
# `hidden` attribute and on insertions; its callback runs after the task that
# changed the DOM, so a welcome shown across a task boundary is counted).
_WELCOME_WATCH = """
(() => {
  window.__welcomeShown = 0;
  new MutationObserver(() => {
    const w = document.querySelector('[data-testid="chat-welcome"]');
    if (w && !w.hidden) window.__welcomeShown += 1;
  }).observe(document, { subtree: true, childList: true, attributes: true,
                         attributeFilter: ['hidden'] });
})();
"""

# The visible h1s in the chat panel (a hidden ancestor leaves no client rects).
_VISIBLE_H1S = (
    "(sel) => Array.from(document.querySelectorAll(sel + ' h1'))"
    ".filter((h) => h.getClientRects().length > 0).map((h) => h.textContent)"
)


def _visible_h1s(page: Page) -> list[str]:
    return page.evaluate(_VISIBLE_H1S, PANEL)


def _wait_state(page: Page, name: str, timeout: float = 10000) -> None:
    page.wait_for_function(
        "n => App.areas.find(a => a.id === 'chat')._sessionState().name === n",
        arg=name,
        timeout=timeout,
    )


def _provider(base: str, name: str, ptype: str) -> str:
    r = httpx.post(
        f"{base}/api/providers",
        json={"name": name, "type": ptype, "base_url": "http://127.0.0.1:9", "config": {}},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _agent(base: str, name: str, provider_id: str | None, model: str, description: str = "") -> str:
    body: dict[str, Any] = {
        "name": name,
        "llm_model": model,
        "description": description,
        "system_prompt": "You are a test agent.",
    }
    if provider_id:
        body["provider_config_id"] = provider_id
    r = httpx.post(f"{base}/api/agents", json=body, headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 201, r.text
    return name


def _expect_shell_intact(page: Page) -> None:
    """The landmarks and the skip link (M25 F2 L6): one main, the skip link to
    it; the chat header is a <header> inside <main>, so it adds no banner."""
    expect(page.locator("main#main-content")).to_have_count(1)
    expect(page.locator("a.skip-link")).to_have_attribute("href", "#main-content")
    expect(page.get_by_role("main")).to_have_count(1)
    expect(page.get_by_role("banner")).to_have_count(0)


def _unnamed(page: Page) -> list[str]:
    """The resolver's failures under the chat panel (leg 5 named the hidden
    file input, squawk 0110: nothing is allow-listed)."""
    return collect_label_failures(page, PANEL)


# ── The header (AC1) ─────────────────────────────────────────────────────────


def test_header_in_pending_starting_and_joined_follows_the_store(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script(_DELAY_JOINED % 0)
    _nav.goto(page, base, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    expect(_chats.chat_header(page)).to_be_hidden()  # idle: no header

    # pending: "New chat" with "with {agent}".
    _chats.start_chat(page, agent)
    _chats.expect_chat(page, agent, title="New chat")
    title = _chats.chat_title(page)
    assert title.evaluate("el => el.tagName") == "H1"

    # starting (the session_joined held): still "New chat", the new-chat state
    # gone, the optimistic bubble in the log.
    page.evaluate("window.__delayJoined = 1200")
    box = page.locator('[data-testid="chat-input"]')
    box.fill("Plan the garden")
    box.press("Enter")
    assert _chats.session_state(page)["name"] == "starting"
    expect(title).to_have_text("New chat")
    expect(_chats.chat_agent_line(page)).to_have_text(f"with {agent}")
    expect(_chats.new_chat_state(page)).to_be_hidden()
    expect(_chats.messages(page, "user")).to_have_text(["Plan the garden"])

    # joined: the title follows the auto-title through the `sessions` store.
    _wait_state(page, "joined")
    sid = _chats.current_session_id(page)
    expect(title).to_have_text("Plan the garden", timeout=10000)
    expect(_chats.chat_agent_line(page)).to_have_text(f"with {agent}")
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    page.wait_for_timeout(500)  # the `done` list refresh (a prime) has landed

    # The header reads the STORE by id: a primed row's title and agent show at
    # once (an auto-title, a rename), with no frame from the server.
    page.evaluate(
        """(sid) => App.store.prime('sessions', App.store.peek('sessions').value.map(
             (r) => r.id === sid ? Object.assign({}, r, {title: 'Renamed in the store',
                                                        agent_name: 'renamed-agent'}) : r))""",
        sid,
    )
    expect(title).to_have_text("Renamed in the store")
    expect(_chats.chat_agent_line(page)).to_have_text("with renamed-agent")
    # A null agent reads "Default agent".
    page.evaluate(
        """(sid) => App.store.prime('sessions', App.store.peek('sessions').value.map(
             (r) => r.id === sid ? Object.assign({}, r, {agent_name: null}) : r))""",
        sid,
    )
    expect(_chats.chat_agent_line(page)).to_have_text("with Default agent")

    # Geometry and type (reference spec 5.2).
    geo = _chats.chat_header(page).evaluate(
        """(h) => {
          const cs = getComputedStyle(h), t = getComputedStyle(h.querySelector('h1'));
          const line = h.querySelector('[data-testid="chat-agent-line"]');
          const probe = document.createElement('span');
          probe.style.color = 'var(--fg-muted)';
          h.appendChild(probe);
          const muted = getComputedStyle(probe).color;
          probe.remove();
          return {tag: h.tagName, height: h.getBoundingClientRect().height,
                  border: cs.borderBottomWidth + ' ' + cs.borderBottomStyle,
                  pad: cs.padding, titleSize: t.fontSize, titleWeight: t.fontWeight,
                  lineSize: getComputedStyle(line).fontSize,
                  lineColor: getComputedStyle(line).color, muted: muted};
        }"""
    )
    assert geo["tag"] == "HEADER", geo
    assert geo["height"] == 48 and geo["border"] == "1px solid", geo
    assert geo["pad"] == "0px 16px 0px 24px", geo
    assert geo["titleSize"] == "13px" and geo["titleWeight"] == "600", geo
    assert geo["lineSize"] == "12px" and geo["lineColor"] == geo["muted"], geo


def test_header_while_joining_reads_the_store_and_no_empty_state_flashes(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A cold ``#chats`` auto-joins the most recent session: while its
    session_joined is held (joining), the chrome and the header (the store's
    title) show and the welcome never does. Then, from the empty state (idle,
    nothing to auto-join), a session appearing in the list is auto-joined
    with the welcome hidden at once (AC B: never during joining)."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    old = seed_session(base, agent, "Old chat", "2026-01-01T00:00:00+00:00")
    page.add_init_script(_DELAY_JOINED % 1500)
    page.add_init_script(_WELCOME_WATCH)
    _nav.goto(page, base, "chats")
    _wait_state(page, "joining")
    assert _chats.session_state(page)["id"] == old
    expect(_chats.chat_title(page)).to_have_text("Old chat")
    expect(_chats.chat_agent_line(page)).to_have_text(f"with {agent}")
    expect(_chats.welcome(page)).to_be_hidden()
    assert _visible_h1s(page) == ["Old chat"]
    _wait_state(page, "joined")
    expect(_chats.chat_title(page)).to_have_text("Old chat")
    assert page.evaluate("window.__welcomeShown") == 0

    # Back to idle with nothing to auto-join: delete it (the empty state).
    page.evaluate("window.__delayJoined = 0")
    page.evaluate(
        "(id) => App.areas.find(a => a.id === 'chat')._ws()"
        ".send(JSON.stringify({action: 'delete_session', session_id: id}))",
        old,
    )
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    expect(_chats.empty_new_button(page)).to_be_visible()
    assert _visible_h1s(page) == ["Hello."]

    # A session appears; the next list's idle rules auto-join it. While the
    # join is held the welcome is already hidden and the header shows it.
    fresh = seed_session(base, agent, "Fresh chat", "2026-02-01T00:00:00+00:00")
    page.evaluate("window.__delayJoined = 1500")
    page.evaluate(
        "() => App.areas.find(a => a.id === 'chat')._ws()"
        ".send(JSON.stringify({action: 'list_sessions'}))"
    )
    _wait_state(page, "joining")
    assert _chats.session_state(page)["id"] == fresh
    expect(_chats.welcome(page)).to_be_hidden()
    expect(_chats.chat_title(page)).to_have_text("Fresh chat")
    assert _visible_h1s(page) == ["Fresh chat"]
    _wait_state(page, "joined")


# ── The new-chat state (AC2, A20) ────────────────────────────────────────────


def test_new_chat_state_shows_the_model_badge_name_description_and_re_picks(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    page.set_viewport_size({"width": 1440, "height": 900})
    ollama = _provider(base, "Local ollama", "ollama")
    _agent(base, "Gardener", ollama, "llama3.1:8b", "Plans the vegetable beds.")
    _agent(base, "Loose", None, "m-loose")  # no provider: the unknown-type fallback
    seed_mock_agent(base, app_with_provider.provider_id, name="Mocker")
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, "Gardener")

    state = _chats.new_chat_state(page)
    expect(state).to_be_visible()
    badge = state.locator(".badge")
    # A20: the badge's TEXT is the model; its kind the provider type.
    expect(badge).to_have_text("llama3.1:8b")
    expect(badge).to_have_class("badge badge--ollama")
    expect(state.locator("h2")).to_have_text("Gardener")
    desc = state.locator(".chat-new-state-description")
    expect(desc).to_have_text("Plans the vegetable beds.")
    pick = _chats.pick_different_button(page)
    expect(pick).to_have_text("Pick a different agent")
    expect(pick).to_have_class("btn-ghost btn-sm chat-new-state-pick")
    assert _visible_h1s(page) == ["New chat"]  # the h2 is the agent, not a second h1

    geo = state.evaluate(
        """(s) => {
          const inner = s.querySelector('.chat-new-state-inner');
          const desc = s.querySelector('.chat-new-state-description');
          const probe = document.createElement('span');
          probe.style.color = 'var(--fg-secondary)';
          s.appendChild(probe);
          const secondary = getComputedStyle(probe).color;
          probe.remove();
          const sr = s.getBoundingClientRect(), ir = inner.getBoundingClientRect();
          return {maxW: getComputedStyle(inner).maxWidth, align: getComputedStyle(inner).textAlign,
                  centred: Math.abs((sr.left + sr.right) / 2 - (ir.left + ir.right) / 2) < 1,
                  h2: getComputedStyle(s.querySelector('h2')).fontSize,
                  descColor: getComputedStyle(desc).color, secondary: secondary};
        }"""
    )
    assert geo["maxW"] == "480px" and geo["align"] == "center" and geo["centred"], geo
    assert geo["h2"] == "18px" and geo["descColor"] == geo["secondary"], geo

    # No description: none shown. The mock type badge.
    pick.click()
    expect(_chats.picker(page)).to_be_visible()
    _chats.picker_search(page).fill("Mocker")
    expect(_chats.picker_rows(page)).to_have_count(1)
    _chats.picker_search(page).press("Enter")
    _chats.expect_chat(page, "Mocker", title="New chat")
    expect(badge).to_have_text("mock-default")
    expect(badge).to_have_class("badge badge--mock")
    expect(state.locator("h2")).to_have_text("Mocker")
    expect(desc).to_be_hidden()
    _nav.expect_route(page, "chats/~new/Mocker")

    # No provider: the unknown-type fallback (badge--unknown), the model shown.
    _chats.pick(page, "Loose")
    _chats.expect_chat(page, "Loose", title="New chat")
    expect(badge).to_have_class("badge badge--unknown")
    expect(badge).to_have_text("m-loose")
    # agentInfo's fallback for a type outside App.ui.badge.KINDS.
    info = page.evaluate(
        """() => App.chat.chatPane.agentInfo('x',
             [{name: 'x', llm_model: 'm', provider_config_id: 'p'}], [{id: 'p', type: 'weird'}])"""
    )
    assert info["kind"] == "unknown" and info["model"] == "m" and info["known"], info

    # The first send (an agent that can start): the log replaces the
    # new-chat state.
    _chats.pick(page, "Mocker")
    _chats.expect_chat(page, "Mocker", title="New chat")
    _chats.send_first(page, "hi")
    expect(state).to_be_hidden()


def test_a_start_failure_shows_its_error_in_the_pending_pane(
    app_with_provider: SeededApp, page: Page
) -> None:
    """The error of a start_failed shows UNDER the new-chat state (the pending
    chrome shrinks the log to its notices), which stays."""
    base = app_with_provider.base_url
    agent = seed_mock_agent(base, app_with_provider.provider_id, name="doomed")
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    r = httpx.delete(f"{base}/api/agents/{agent}", headers=auth_headers_for(base), timeout=5)
    assert r.status_code in (200, 204), r.text
    box = page.locator('[data-testid="chat-input"]')
    box.fill("will fail")
    box.press("Enter")
    notice = page.locator(f"{PANEL} .messages " + _chats.message_sel("system"))
    expect(notice).to_contain_text("Cannot start chat", timeout=8000)
    _wait_state(page, "pending")
    expect(notice).to_be_visible()
    expect(_chats.new_chat_state(page)).to_be_visible()
    above = page.evaluate(
        """() => {
          const q = (sel) => document.querySelector(sel).getBoundingClientRect();
          const s = q('[data-testid="chat-new-state"]');
          const m = q('.area-chat .messages [data-testid="message"].ui-message--system');
          return s.bottom <= m.top + 1;
        }"""
    )
    assert above


# ── The empty and guidance states (AC3-AC5) ──────────────────────────────────


def test_empty_state_has_hello_the_prompt_and_new_chat(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    welcome = _chats.welcome(page)
    expect(welcome).to_be_visible(timeout=8000)
    expect(welcome.locator('[data-testid="chat-welcome-mascot"]')).to_be_visible()
    expect(welcome.locator("h1.chat-welcome-greeting")).to_have_text("Hello.")
    expect(welcome.locator(".chat-welcome-prompt")).to_have_text(
        "Start a conversation with one of your agents."
    )
    new_btn = _chats.empty_new_button(page)
    expect(new_btn).to_have_text("New chat")
    expect(new_btn).to_have_class("btn-filled-primary")
    expect(welcome.locator(".chat-welcome-guidance")).to_have_count(0)
    expect(page.locator(".chat-chrome")).to_be_hidden()
    assert _visible_h1s(page) == ["Hello."]
    # It opens the picker (the list's New chat stays enabled).
    expect(_chats.chats_new_button(page)).to_be_enabled()
    new_btn.click()
    expect(_chats.picker(page)).to_be_visible(timeout=8000)


def test_guidance_state_has_hello_and_the_links_and_no_new_chat(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Setup incomplete (a provider, no agent): the guidance, rebuilt with DOM
    APIs (same copy and hrefs), no prompt, no New chat in the pane, and the
    list's New chat disabled."""
    _nav.goto(page, app_with_provider.base_url, "chats")
    welcome = _chats.welcome(page)
    expect(welcome).to_be_visible(timeout=8000)
    expect(welcome.locator("h1.chat-welcome-greeting")).to_have_text("Hello.")
    guidance = welcome.locator(".chat-welcome-guidance")
    expect(guidance).to_have_text("Create an agent in Agents to start chatting.")
    expect(guidance.locator(".chat-welcome-link")).to_have_attribute("href", _nav.href("agents"))
    expect(welcome.locator(".chat-welcome-prompt")).to_be_hidden()
    expect(_chats.empty_new_button(page)).to_have_count(0)
    expect(_chats.chats_new_button(page)).to_be_disabled()
    assert _visible_h1s(page) == ["Hello."]


# ── One h1, the landmarks, named controls (AC12) ─────────────────────────────


def test_one_h1_landmarks_and_named_controls_in_every_state(app_clean: str, page: Page) -> None:
    base = app_clean
    # Guidance (nothing set up).
    _nav.goto(page, base, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    expect(page.locator(".chat-welcome-guidance")).to_be_visible()
    assert _visible_h1s(page) == ["Hello."]
    _expect_shell_intact(page)
    assert _unnamed(page) == []

    # Empty (set up, no chats).
    provider = httpx.post(
        f"{base}/api/providers",
        json={"name": "mock", "type": "mock", "base_url": "", "config": {}},
        headers=auth_headers_for(base),
        timeout=5,
    ).json()["id"]
    agent = seed_mock_agent(base, provider, name="Helper")
    page.reload()
    expect(_chats.empty_new_button(page)).to_be_visible(timeout=8000)
    assert _visible_h1s(page) == ["Hello."]
    _expect_shell_intact(page)
    assert _unnamed(page) == []

    # Pending.
    _chats.start_chat(page, agent)
    assert _visible_h1s(page) == ["New chat"]
    _expect_shell_intact(page)
    assert _unnamed(page) == []

    # Joined.
    _chats.send_first(page, "Hello there")
    expect(_chats.chat_title(page)).to_have_text("Hello there", timeout=10000)
    assert _visible_h1s(page) == ["Hello there"]
    _expect_shell_intact(page)
    assert _unnamed(page) == []

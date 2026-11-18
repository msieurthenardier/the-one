"""GleepGlorp in Chats (M36 F1 L04, flight DD8 and DD11; the approved board's screens 2-5).

GleepGlorp has no agents row, so the chat surfaces reach it through ``App.chat.agentKind``.
Covers, as state transitions:

* the picker's "Built in" group (enabled, off, needs a model) and a query that matches it;
* the setup gate: New chat and the picker work with no agent while GleepGlorp is on;
* the new-chat states: ready (badge "Built in", model, composer), the setup block for a missing
  model or provider, and a direct ``#chats/~new/GleepGlorp`` while it is off;
* a started chat that replies, its row, header, drawer and the context-window fetch it skips;
* the degraded banner and its button after the settings change in another place (the push),
  and its recovery;
* a refused turn followed by a push that still re-joins (the own-turn flag clears);
* the step-limit notice link, and no rendered ``#agents/GleepGlorp`` href anywhere.

Falls in the ``chats-transcript`` browser lane (an explicit entry in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

BANNER = ".chat-health-banner"
BANNER_ACTION = '[data-testid="chat-health-banner-action"]'
SETUP = '[data-testid="chat-new-gleepglorp-setup"]'
SETUP_ACTION = '[data-testid="chat-new-gleepglorp-setup-action"]'
MODEL_LINE = '[data-testid="chat-new-state-model"]'
DRAWER = '[data-testid="chat-drawer"]'
INPUT = '[data-testid="chat-input"]'
SEND = '[data-testid="chat-send-btn"]'
SETTINGS_LINK = '[data-testid="chat-drawer-settings-link"]'

_PICKER_JS = """
() => {
  const dlg = document.querySelector('[data-testid="agent-picker"]');
  if (!dlg) return null;
  return Array.from(dlg.querySelectorAll('.ui-search-list-group')).map((g) => ({
    label: g.querySelector('.ui-search-list-caption').textContent,
    rows: Array.from(g.querySelectorAll('[data-testid="agent-picker-row"]')).map((r) => {
      const meta = r.querySelector('.ui-search-list-meta');
      const desc = r.querySelector('.ui-search-list-description');
      return {agent: r.dataset.agent, desc: desc ? desc.textContent : '',
              meta: meta ? meta.textContent : ''};
    }),
  }));
}
"""

# While `on`, holds every `gleepglorp_changed` push and `system` frame a page's socket receives;
# `__ggRelease(types)` delivers the held frames of those types, in that order. It lets a test
# send from a tab the push has not reached (a stale tab) and choose whether the push lands
# before or after the refusal.
_HOLD_JS = """
(function () {
  var Orig = window.WebSocket;
  var HELD = { gleepglorp_changed: 1, system: 1 };
  window.__ggHold = { on: false, queue: [], ws: null };
  function W(url, protocols) {
    var ws = protocols === undefined ? new Orig(url) : new Orig(url, protocols);
    var user = null;
    Object.defineProperty(ws, 'onmessage', {
      configurable: true,
      get: function () { return user; },
      set: function (fn) { user = fn; }
    });
    ws.addEventListener('message', function (e) {
      if (!user) return;
      var d = null;
      try { d = JSON.parse(e.data); } catch (err) { d = null; }
      if (window.__ggHold.on && d && HELD[d.type]) {
        window.__ggHold.queue.push({ type: d.type, e: e });
        return;
      }
      user.call(ws, e);
    });
    window.__ggHold.ws = ws;
    return ws;
  }
  W.prototype = Orig.prototype;
  W.CONNECTING = Orig.CONNECTING; W.OPEN = Orig.OPEN;
  W.CLOSING = Orig.CLOSING; W.CLOSED = Orig.CLOSED;
  window.WebSocket = W;
  window.__ggRelease = function (types) {
    var n = 0;
    types.forEach(function (t) {
      var keep = [];
      window.__ggHold.queue.forEach(function (h) {
        if (h.type === t) { window.__ggHold.ws.onmessage.call(window.__ggHold.ws, h.e); n++; }
        else keep.push(h);
      });
      window.__ggHold.queue = keep;
    });
    return n;
  };
})();
"""


def _body(**over: Any) -> dict[str, Any]:
    return {
        "enabled": True,
        "provider_config_id": None,
        "model": None,
        "web_access": True,
        "memory": True,
        "retention_days": 30,
        **over,
    }


def _put(base: str, **over: Any) -> None:
    r = httpx.put(
        f"{base}/api/gleepglorp",
        json=_body(**over),
        headers=auth_headers_for(base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text


def _ready(app: SeededApp) -> None:
    _put(app.base_url, provider_config_id=app.provider_id, model="mock-default")


def _settled(page: Page, base: str) -> None:
    _nav.goto(page, base, "chats")
    page.wait_for_function(_chats._SETTLED_JS, timeout=8000)


def _picker(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(_PICKER_JS)


def _gg_state(page: Page) -> str | None:
    return page.evaluate("() => (App.gleepglorp.peek().value || {}).state || null")


def _wait_state(page: Page, state: str) -> None:
    """The client's copy of GleepGlorp's settings follows the push."""
    page.wait_for_function(
        "(s) => (App.gleepglorp.peek().value || {}).state === s", arg=state, timeout=8000
    )


# ── The picker ─────────────────────────────────────────────────────────────


def test_the_picker_has_a_built_in_group_that_follows_the_settings(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _ready(app_with_agent)
    _settled(page, base)
    _wait_state(page, "ready")

    # [ready] Built in first (GleepGlorp alone), then All agents, never GleepGlorp twice.
    _chats.open_picker(page)
    groups = _picker(page)
    assert [g["label"] for g in groups] == ["Built in", "All agents"]
    assert groups[0]["rows"] == [
        {"agent": "GleepGlorp", "desc": "Help setting up the app", "meta": "mock-default"}
    ]
    assert [r["agent"] for r in groups[1]["rows"]] == [agent]

    # A query matches it by name and by description, and lists it first.
    _chats.picker_search(page).fill("gleep")
    got = _picker(page)
    assert [g["label"] for g in got] == ["1 matching"]
    assert [r["agent"] for r in got[0]["rows"]] == ["GleepGlorp"]
    _chats.picker_search(page).fill("setting")
    assert [r["agent"] for r in _picker(page)[0]["rows"]] == ["GleepGlorp"]
    page.keyboard.press("Escape")

    # [ready] -> [needs a model]: the row says "Needs a model" (the push re-reads it).
    _put(base, provider_config_id=app_with_agent.provider_id, model=None)
    _wait_state(page, "needs_model")
    _chats.open_picker(page)
    assert _picker(page)[0]["rows"][0]["meta"] == "Needs a model"
    page.keyboard.press("Escape")

    # [needs a model] -> [off]: it appears nowhere.
    _put(base, enabled=False)
    _wait_state(page, "off")
    _chats.open_picker(page)
    groups = _picker(page)
    assert [g["label"] for g in groups] == ["All agents"]
    assert [r["agent"] for r in groups[0]["rows"]] == [agent]
    _chats.picker_search(page).fill("gleep")
    assert _picker(page) == []
    page.keyboard.press("Escape")


def test_the_setup_gate_lets_gleepglorp_in_with_no_agents_and_not_with_it_off(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _settled(page, base)
    # [GleepGlorp on, no agents]: New chat and the picker work; the guidance links still show.
    expect(_chats.chats_new_button(page)).to_be_enabled(timeout=8000)
    expect(_chats.welcome(page)).to_contain_text("Create an agent in")
    _chats.open_picker(page)
    groups = _picker(page)
    assert [g["label"] for g in groups] == ["Built in"]
    assert groups[0]["rows"][0]["meta"] == "Needs a model"
    page.keyboard.press("Escape")

    # [on] -> [off]: the gate is as before: New chat is disabled again.
    _put(base, enabled=False)
    _wait_state(page, "off")
    expect(_chats.chats_new_button(page)).to_be_disabled()


# ── The new-chat states ────────────────────────────────────────────────────


def test_a_pending_gleepglorp_chat_needing_a_model_shows_the_setup_block(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _settled(page, base)
    _chats.pick(page, "GleepGlorp")
    page.wait_for_function(_chats._PENDING_JS, arg="GleepGlorp", timeout=8000)
    state = _chats.new_chat_state(page)
    badge = state.locator(".badge")
    expect(badge).to_have_text("Built in")
    expect(badge).to_have_class("badge badge--builtin")
    expect(state.locator("h2")).to_have_text("GleepGlorp")
    expect(state.locator(".chat-new-state-description")).to_have_text("Help setting up the app")
    expect(page.locator(SETUP)).to_contain_text("GleepGlorp needs a model first.")
    expect(page.locator(SETUP)).to_have_class(re.compile(r"banner-warning"))
    # A persistent live region (not a second banner) carries the sentence for screen readers.
    live = page.locator('[data-testid="chat-new-gleepglorp-setup-live"]')
    expect(live).to_have_attribute("role", "status")
    expect(live).to_have_text("GleepGlorp needs a model first.")
    action = page.locator(SETUP_ACTION)
    expect(action).to_have_text("Choose a model for GleepGlorp")
    expect(page.locator(INPUT)).to_be_disabled()
    expect(_chats.pick_different_button(page)).to_be_visible()
    # No other element is built for a GleepGlorp that needs a model.
    expect(page.locator(MODEL_LINE)).to_be_hidden()

    action.click()
    _nav.expect_route(page, "settings/gleepglorp")


def test_a_pending_gleepglorp_chat_with_no_providers_asks_for_one(
    app_clean: str, page: Page
) -> None:
    _settled(page, app_clean)
    _chats.pick(page, "GleepGlorp")
    page.wait_for_function(_chats._PENDING_JS, arg="GleepGlorp", timeout=8000)
    expect(page.locator(SETUP)).to_contain_text("Add a model provider first.")
    action = page.locator(SETUP_ACTION)
    expect(action).to_have_text("Add a model provider")
    expect(page.locator(INPUT)).to_be_disabled()
    action.click()
    _nav.expect_route(page, "library/providers/~new")


def test_a_direct_pending_route_with_gleepglorp_off_shows_the_off_block(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _put(base, enabled=False)
    _nav.goto(page, base, "chats/~new/GleepGlorp")
    page.wait_for_function(_chats._PENDING_JS, arg="GleepGlorp", timeout=8000)
    # Not healed away to #chats: the pending chat stays, with the off block.
    _nav.expect_route(page, "chats/~new/GleepGlorp")
    expect(page.locator(SETUP)).to_contain_text("GleepGlorp is turned off.")
    expect(page.locator(SETUP_ACTION)).to_have_text("Open GleepGlorp settings")
    expect(page.locator(INPUT)).to_be_disabled()
    # Turned on (and given a model) in another place: the block goes, the composer opens.
    _put(base, provider_config_id=app_with_agent.provider_id, model="mock-default")
    expect(page.locator(SETUP)).to_be_hidden(timeout=8000)
    expect(page.locator('[data-testid="chat-new-gleepglorp-setup-live"]')).to_have_text("")
    expect(page.locator(INPUT)).to_be_enabled()
    expect(page.locator(MODEL_LINE)).to_have_text("mock-default")


# ── A started chat ─────────────────────────────────────────────────────────


def test_a_gleepglorp_chat_starts_replies_and_shows_its_row_header_and_drawer(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(app_with_agent)
    context_window: list[str] = []
    page.on("request", lambda r: "/context-window" in r.url and context_window.append(r.url))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, "GleepGlorp")
    state = _chats.new_chat_state(page)
    expect(state.locator(".badge")).to_have_text("Built in")
    expect(page.locator(MODEL_LINE)).to_have_text("mock-default")
    expect(page.locator(SETUP)).to_be_hidden()

    sid = _chats.send_first(page, "hello gleepglorp")
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    expect(_chats.messages(page, "assistant")).to_contain_text(
        "Mock response from the mock provider."
    )
    stored = httpx.get(
        f"{base}/api/chat/sessions/{sid}", headers=auth_headers_for(base), timeout=5.0
    ).json()
    assert stored["agent_name"] == "GleepGlorp"
    expect(_chats.chat_agent_line(page)).to_have_text("with GleepGlorp")
    row = _chats.chat_row(page, sid)
    expect(row).to_contain_text("GleepGlorp")
    expect(page.locator('[data-testid="chat-model"]')).to_have_text("mock-default")
    page.wait_for_timeout(500)
    assert context_window == []

    # The drawer (board screen 4): a Built in badge, facts from the settings, a fixed list.
    drawer = page.locator(DRAWER)
    expect(drawer.locator("h2")).to_have_text("GleepGlorp")
    expect(drawer.locator(".chat-drawer-head .badge")).to_have_text("Built in")
    facts = page.evaluate(
        """() => Array.from(document.querySelectorAll('[data-testid="chat-drawer-facts"] > *'))
                 .map((n) => n.textContent)"""
    )
    assert facts == [
        "Model", "mock-default", "Provider", "mock",
        "Web access", "On", "Memory", "On", "Keeps chats", "30 days",
    ]  # fmt: skip
    uses = page.locator('[data-testid="chat-drawer-uses"] li').all_text_contents()
    assert uses == [
        "Your app's settings and status, read only, secrets hidden",
        "The app guide",
        "Web search and web pages",
        "Its own notes",
    ]
    expect(page.locator('[data-testid="chat-drawer-note"]')).to_have_text(
        "GleepGlorp can't change anything by itself."
    )
    link = page.locator(SETTINGS_LINK)
    expect(link).to_have_text("Open GleepGlorp settings")

    # The switches shorten the list, through the push (no reload).
    _put(base, provider_config_id=app_with_agent.provider_id, model="mock-default",
         web_access=False, memory=False)  # fmt: skip
    expect(page.locator('[data-testid="chat-drawer-uses"] li')).to_have_count(2, timeout=8000)

    # Nothing renders a link to #agents/GleepGlorp.
    hrefs = page.evaluate(
        "() => Array.from(document.querySelectorAll('a[href]')).map((a) => a.getAttribute('href'))"
    )
    assert not [h for h in hrefs if "agents/GleepGlorp" in h], hrefs

    link.click()
    _nav.expect_route(page, "settings/gleepglorp")


def test_the_step_limit_notice_in_a_gleepglorp_chat_links_to_its_settings(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(app_with_agent)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, "GleepGlorp")
    _chats.send_first(page, "hi")
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    page.evaluate(
        "() => App.areas.find(a => a.id === 'chat')._turnFrames()"
        ".handle({type: 'step_limit', steps: 2})"
    )
    link = page.locator('[data-testid="chat-step-limit-link"]')
    expect(link).to_have_attribute("href", _nav.href("settings/gleepglorp"))
    link.click()
    _nav.expect_route(page, "settings/gleepglorp")


# ── The degraded states and the push ───────────────────────────────────────


def test_an_open_chat_follows_a_settings_change_through_the_push(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(app_with_agent)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, "GleepGlorp")
    sid = _chats.send_first(page, "hi")
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"chat-send-btn\"]').disabled", timeout=8000
    )
    expect(page.locator(BANNER)).to_be_hidden()

    # [ready] -> [off] (changed elsewhere): the banner, its button, a blocked composer.
    _put(base, enabled=False)
    expect(page.locator(BANNER)).to_contain_text(
        "GleepGlorp is turned off. Turn it on to continue this chat.", timeout=8000
    )
    expect(page.locator(BANNER_ACTION)).to_have_text("Open GleepGlorp settings")
    expect(page.locator(INPUT)).to_be_disabled()
    expect(page.locator('.msg.system, [data-testid="agent-deleted-notice"]')).to_have_count(0)
    # The history is still there.
    expect(_chats.messages(page, "assistant")).to_have_count(1)

    # [off] -> [needs a model]
    _put(base, provider_config_id=app_with_agent.provider_id, model=None)
    expect(page.locator(BANNER)).to_contain_text("GleepGlorp needs a model.", timeout=8000)
    expect(page.locator(BANNER)).not_to_contain_text("turned off")
    expect(page.locator(BANNER_ACTION)).to_be_visible()

    # [needs a model] -> [ready]: the banner goes, the composer opens, no reload.
    _put(base, provider_config_id=app_with_agent.provider_id, model="mock-default")
    expect(page.locator(BANNER_ACTION)).to_have_count(0, timeout=8000)
    expect(page.locator(BANNER)).not_to_contain_text("GleepGlorp")
    expect(page.locator(INPUT)).to_be_enabled()
    assert _chats.current_session_id(page) == sid

    # The button goes to the settings page.
    _put(base, enabled=False)
    page.locator(BANNER_ACTION).click(timeout=8000)
    _nav.expect_route(page, "settings/gleepglorp")


def test_a_joined_stored_chat_opens_degraded_when_gleepglorp_is_off(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(app_with_agent)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, "GleepGlorp")
    sid = _chats.send_first(page, "hi")
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    _put(base, enabled=False)
    # A fresh page load joins the stored chat degraded: the status rides session_joined.
    _nav.goto(page, base, f"chats/{_nav.seg(sid)}")
    expect(page.locator(BANNER)).to_contain_text("GleepGlorp is turned off.", timeout=10000)
    expect(page.locator(BANNER_ACTION)).to_be_visible()
    expect(page.locator(INPUT)).to_be_disabled()
    expect(_chats.messages(page, "assistant")).to_have_count(1)


def _stale_tab_sends(app: SeededApp, page: Page) -> str:
    """A joined GleepGlorp chat whose tab has not been told it was turned off: its socket holds
    the push and the server's replies (``_HOLD_JS``), GleepGlorp is turned off, and the tab
    sends a second message. Returns the session id; the refusal is held, not yet delivered."""
    base = app.base_url
    _ready(app)
    page.add_init_script(_HOLD_JS)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, "GleepGlorp")
    sid = _chats.send_first(page, "first")
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"chat-send-btn\"]').disabled", timeout=8000
    )
    page.evaluate("() => { window.__ggHold.on = true; }")
    _put(base, enabled=False)
    page.wait_for_function("() => window.__ggHold.queue.length === 1", timeout=8000)
    expect(page.locator(INPUT)).to_be_enabled()  # the tab still thinks it may send
    box = page.locator(INPUT)
    box.fill("second")
    box.press("Enter")
    page.wait_for_function("() => window.__ggHold.queue.length === 2", timeout=8000)
    return sid


def _assert_refused_and_rejoined(base: str, sid: str, page: Page) -> None:
    # Nothing ran and nothing was stored for the refused message.
    stored = httpx.get(
        f"{base}/api/chat/sessions/{sid}", headers=auth_headers_for(base), timeout=5.0
    ).json()
    assert [m["role"] for m in stored["messages"]].count("user") == 1
    expect(_chats.messages(page, "assistant")).to_have_count(1)
    # The chat re-joined (the push was not lost): the degraded banner, its button, a blocked
    # composer.
    expect(page.locator(BANNER_ACTION)).to_be_visible(timeout=8000)
    expect(page.locator(INPUT)).to_be_disabled()


def test_a_refused_turn_ends_the_turn_and_a_later_push_rejoins(
    app_with_agent: SeededApp, page: Page
) -> None:
    sid = _stale_tab_sends(app_with_agent, page)
    # The refusal lands first: one system line, the turn ends, Send comes back.
    assert page.evaluate("() => window.__ggRelease(['system'])") == 1
    expect(page.get_by_text("GleepGlorp is turned off.", exact=True)).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"chat-send-btn\"]').disabled", timeout=8000
    )
    expect(page.locator(BANNER_ACTION)).to_have_count(0)
    # Then the push: the chat re-joins.
    assert page.evaluate("() => window.__ggRelease(['gleepglorp_changed'])") == 1
    _assert_refused_and_rejoined(app_with_agent.base_url, sid, page)


def test_a_push_that_waited_for_a_turn_that_was_refused_still_rejoins(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The push lands while the tab's own turn is in flight (so its re-join is deferred), and
    the turn then ends with the refusal, a system frame: the deferred re-join must still run."""
    sid = _stale_tab_sends(app_with_agent, page)
    assert page.evaluate("() => window.__ggRelease(['gleepglorp_changed'])") == 1
    expect(page.locator(BANNER_ACTION)).to_have_count(0)  # deferred: the turn is still running
    assert page.evaluate("() => window.__ggRelease(['system'])") == 1
    _assert_refused_and_rejoined(app_with_agent.base_url, sid, page)

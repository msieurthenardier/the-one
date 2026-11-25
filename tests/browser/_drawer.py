"""Shared helpers for the GleepGlorp drawer's browser tests (M36 F3 L6; moved out of
``test_flow_gleepglorp_drawer_chat.py`` so the fill tests use them too).

The socket recorder (``RECORD``) wraps ``WebSocket`` so a test can read the frames each socket
sent (by construction order) and, with ``window.__hold``, hold a socket CONNECTING. ``DELIVER``
pushes a synthetic server frame into every recorded socket's ``onmessage`` (the real frame path,
without a live turn). ``DRAWER_INDEX`` is the drawer socket's index in ``window.__socks``.
"""

from __future__ import annotations

import httpx
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_provider
from playwright.sync_api import Page, expect

BTN = '[data-testid="gg-corner-button"]'
DRAWER = "#gleepglorp-drawer"
INPUT = '[data-testid="gg-chat-input"]'
SEND = '[data-testid="gg-chat-send-btn"]'
EMPTY = '[data-testid="gg-drawer-empty"]'
SUGGESTION = '[data-testid="gg-drawer-suggestion"]'
NEW_CHAT = '[data-testid="gg-drawer-new-chat"]'
OPEN_IN_CHATS = '[data-testid="gg-drawer-open-in-chats"]'
SETUP_ACTION = '[data-testid="gg-drawer-setup-action"]'
STORE = "gleepglorp-drawer-session"
STAY = '[data-testid="modal-cancel-btn"]'

# Wrap WebSocket: record every socket (by construction order) with the frames it sent. With
# window.__hold set at construction, the socket reads CONNECTING and its onopen is withheld until
# window.__releaseSocks() (the "drawer opened before its socket" case).
RECORD = """
(() => {
  const Native = window.WebSocket;
  const rs = Object.getOwnPropertyDescriptor(Native.prototype, 'readyState');
  window.__socks = [];
  window.__hold = false;
  window.WebSocket = new Proxy(Native, {
    construct(target, args) {
      const s = new target(...args);
      const rec = { ws: s, url: String(args[0]), sent: [], held: window.__hold, onopen: null,
                    opened: false };
      const send = s.send.bind(s);
      s.send = (d) => {
        try { rec.sent.push(JSON.parse(d)); } catch (e) { rec.sent.push(d); }
        return send(d);
      };
      if (rec.held) {
        Object.defineProperty(s, 'readyState', {
          get() { return rec.held ? 0 : rs.get.call(s); }, configurable: true });
        Object.defineProperty(s, 'onopen', {
          set(fn) { rec.onopen = fn; }, get() { return rec.onopen; }, configurable: true });
        s.addEventListener('open', () => { rec.opened = true; });
      }
      window.__socks.push(rec);
      return s;
    },
  });
  window.__releaseSocks = () => {
    for (const r of window.__socks) {
      if (r.held) { r.held = false; if (r.onopen) r.onopen.call(r.ws, new Event('open')); }
    }
  };
})();
"""

DRAWER_INDEX = (
    "() => { const i = App.gleepglorpDrawerChat.instance();"
    " return window.__socks.findIndex(r => r.ws === i.ws()); }"
)

DELIVER = """
(frame) => {
  window.__socks.forEach(r => {
    if (r.ws.onmessage) r.ws.onmessage({ data: JSON.stringify(frame) });
  });
}
"""

# Deliver a frame into the drawer's socket only (the other sockets stay untouched).
DELIVER_DRAWER = """
(frame) => {
  const i = App.gleepglorpDrawerChat.instance();
  const r = window.__socks.find(x => x.ws === i.ws());
  if (!r || !r.ws.onmessage) throw new Error('no drawer socket');
  r.ws.onmessage({ data: JSON.stringify(frame) });
}
"""


def put_settings(base: str, **over) -> None:
    body = {
        "enabled": True,
        "provider_config_id": None,
        "model": None,
        "web_access": True,
        "memory": True,
        "retention_days": 30,
        **over,
    }
    r = httpx.put(f"{base}/api/gleepglorp", json=body, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text


def ready(app: SeededApp) -> None:
    put_settings(app.base_url, provider_config_id=app.provider_id, model="mock-default")


def ready_with_reply(base: str, reply: str = "Hello from the mock", delay_ms: int = 0) -> None:
    config: dict = {"response": {"content": reply}}
    if delay_ms:
        config["delay_ms"] = delay_ms
    provider = seed_mock_provider(base, name="gg-mock", config=config)
    put_settings(base, provider_config_id=provider, model="mock-default")


def boot(page: Page, base: str, route: str, *, connected: bool = True) -> None:
    """Load *route* with the socket recorder installed; wait for the drawer's socket to open and
    for the router to commit *route* (squawk 0406: the drawer mounts at DOMContentLoaded, the
    router only after ``/api/config`` and ``/api/time-settings`` resolve)."""
    page.add_init_script(RECORD)
    _nav.goto(page, base, route)
    page.wait_for_function(
        "() => App.gleepglorpDrawer && App.gleepglorpDrawer.state() !== null", timeout=8000
    )
    if connected:
        # wait_socket also waits for the router to start; only the route check remains.
        wait_socket(page)
        _nav.expect_route(page, route, timeout=15000)
    else:
        _nav.wait_router(page, route)


def wait_socket(page: Page) -> None:
    page.wait_for_function(
        "() => { const i = App.gleepglorpDrawerChat.instance();"
        " return !!(i && i.ws() && i.ws().readyState === 1); }",
        timeout=8000,
    )
    # The socket opens at DOMContentLoaded; the router only after the config fetches resolve
    # (squawk 0406), so a page that reloaded or opened here is not usable until it committed.
    _nav.wait_router_started(page)


def drawer_sent(page: Page) -> list[dict]:
    return page.evaluate(
        "() => { const i = App.gleepglorpDrawerChat.instance();"
        " const r = window.__socks.find(x => x.ws === i.ws()); return r ? r.sent : []; }"
    )


def actions(frames: list[dict]) -> list[str]:
    return [f.get("action") for f in frames if isinstance(f, dict)]


def open_drawer(page: Page) -> None:
    if page.locator(DRAWER).is_visible():
        return
    page.locator(BTN).click()
    expect(page.locator(DRAWER)).to_be_visible()


def drawer_msgs(page: Page, role: str):
    return page.locator(f'{DRAWER} [data-testid="message"].ui-message--{role}')


def send(page: Page, text: str) -> None:
    box = page.locator(INPUT)
    box.fill(text)
    box.press("Enter")


def stored(page: Page) -> str | None:
    return page.evaluate(f"() => localStorage.getItem('{STORE}')")


def drawer_session(page: Page) -> str | None:
    return page.evaluate("() => App.gleepglorpDrawerChat.instance().currentSessionId()")


def wait_joined(page: Page) -> str:
    page.wait_for_function(
        "() => App.gleepglorpDrawerChat.instance().sessionState().name === 'joined'", timeout=10000
    )
    return drawer_session(page)  # type: ignore[return-value]


def chat_with(page: Page, text: str, reply: str) -> str:
    """Open the drawer, send *text*, wait for *reply* and the joined session; return its id."""
    open_drawer(page)
    send(page, text)
    expect(drawer_msgs(page, "assistant").last).to_contain_text(reply, timeout=15000)
    return wait_joined(page)

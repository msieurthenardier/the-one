"""The chat instance factory (Mission 36 Flight 3 leg 1, DD2).

``App.chat.create(config)`` (``areas/chat/instance.js``) builds a complete chat from a
config object; the Chats area is its first caller (the Chats profile). This proves a second
and a third instance can be created beside it with a minimal config (a detached content
element, no sidebar, drawer slot or picker host, no sign-in, a recording router adapter and
``gg-`` testids) without touching Chats, and that ``destroy()`` releases the socket and its
reconnect timer.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SEAMS = [
    "_connect",
    "_ws",
    "_refreshAgentsAndSetup",
    "_serialize",
    "_hydrate",
    "_joinSession",
    "_sessionState",
    "_telemetry",
    "_transcript",
    "_turnWork",
    "_turnFrames",
    "_agentDrawer",
]

# Counts every WebSocket constructed on the page and keeps each (for the close check).
_COUNT_SOCKETS = """
(() => {
  const Native = window.WebSocket;
  window.__sockets = [];
  window.WebSocket = new Proxy(Native, {
    construct(target, args) {
      const s = new target(...args);
      window.__sockets.push(s);
      return s;
    },
  });
})();
"""

# Wrap App.router.sync/go so a call that reaches the real router is counted.
_COUNT_ROUTER = """
() => {
  window.__routerCalls = 0;
  for (const name of ['sync', 'go']) {
    const orig = App.router[name];
    App.router[name] = function () {
      window.__routerCalls += 1;
      return orig.apply(this, arguments);
    };
  }
}
"""

_MAKE_MINIMAL = """
() => {
  window.__ggCalls = window.__ggCalls || [];
  const content = document.createElement('div');
  content.className = 'chat-instance';
  const inst = App.chat.create({
    content,
    sidebar: null,
    drawerSlot: null,
    pickerHost: false,
    signIn: false,
    router: {
      sync(sub) { window.__ggCalls.push(['sync', sub]); },
      goNew(agent) { window.__ggCalls.push(['goNew', agent]); return Promise.resolve(true); },
      go(href) { window.__ggCalls.push(['go', href]); return Promise.resolve(true); },
    },
    testids: {
      testid: 'gg-input', attachTestid: 'gg-attach', fileInputTestid: 'gg-file',
      modelTestid: 'gg-model', stopTestid: 'gg-stop', sendTestid: 'gg-send',
      attachmentsTestid: 'gg-attachments', attachmentsStatusTestid: 'gg-attachments-status',
      queuedTestid: 'gg-queued', telemetryTestid: 'gg-telemetry', copyStatusTestid: 'gg-copy',
    },
  });
  return inst;
}
"""


def test_a_second_instance_leaves_chats_untouched_and_a_third_destroys_cleanly(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.add_init_script(_COUNT_SOCKETS)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    _chats.send_first(page, "first message")
    chats_sockets = page.evaluate("() => window.__sockets.length")
    assert chats_sockets >= 1

    # The descriptor still exposes every seam (a typeof loop) and the handle exists.
    types = page.evaluate(
        """(seams) => {
          const a = App.areas.find((x) => x.id === 'chat');
          const out = {};
          for (const s of seams) out[s] = typeof a[s];
          out._currentSessionId = typeof a._currentSessionId;
          out.pendingDescriptor = !!Object.getOwnPropertyDescriptor(a, '_pendingJoinId');
          return out;
        }""",
        SEAMS,
    )
    for seam in SEAMS:
        assert types[seam] != "undefined", f"descriptor lost the seam {seam}"
    assert types["pendingDescriptor"] is True
    chats_dom_before = page.locator('[data-testid="chat-input"]').count()

    # The second instance: detached, no connect.
    page.evaluate(_COUNT_ROUTER)
    page.evaluate("() => { window.__second = (" + _MAKE_MINIMAL.strip() + ")(); }")
    result = page.evaluate(
        """() => {
          const inst = window.__second;
          // A deterministic router use: an empty `new/` heals to idle, a `sync` via the adapter.
          inst.hydrate('new/');
          return {
            root: !!inst.root,
            attached: inst.root.isConnected,
            inputs: inst.root.querySelectorAll('[data-testid="gg-input"]').length,
            chatInputsInside: inst.root.querySelectorAll('[data-testid="chat-input"]').length,
            calls: window.__ggCalls.length,
            realRouterCalls: window.__routerCalls,
            insideOnly: document.querySelectorAll('[data-testid="gg-input"]').length,
          };
        }"""
    )
    assert result["root"] is True
    assert result["attached"] is False
    assert result["inputs"] == 1
    assert result["chatInputsInside"] == 0
    # The adapter received the call, and nothing reached App.router from the second instance.
    assert result["calls"] >= 1
    assert result["realRouterCalls"] == 0
    # Its DOM is only inside its own content (a detached element: nothing in the document).
    assert result["insideOnly"] == 0
    assert page.locator('[data-testid="chat-input"]').count() == chats_dom_before
    assert page.evaluate("() => window.__sockets.length") == chats_sockets

    # Destroying a never-connected instance leaves Chats untouched.
    page.evaluate("() => window.__second.destroy()")
    _chats.send_first(page, "after the second instance")
    expect(_chats.messages(page, "user").last).to_contain_text("after the second instance")

    # A third, connected instance: its socket opens; destroy() closes it and nothing reconnects.
    page.evaluate("() => { window.__third = (" + _MAKE_MINIMAL.strip() + ")(); }")
    before = page.evaluate("() => window.__sockets.length")
    page.evaluate("() => window.__third.connect()")
    page.wait_for_function(
        "(n) => window.__sockets.length === n + 1 && window.__sockets[n].readyState === 1",
        arg=before,
        timeout=8000,
    )
    # AC7: destroy() removes the DOM the instance built (the root is the caller's container, so it
    # stays; attach it to the document first so the check is against the live document).
    page.evaluate("() => document.body.appendChild(window.__third.root)")
    assert page.evaluate("() => document.querySelectorAll('[data-testid=gg-input]').length") == 1
    page.evaluate("() => window.__third.destroy()")
    assert page.evaluate("() => document.querySelectorAll('[data-testid=gg-input]').length") == 0
    assert page.evaluate("() => window.__third.root.querySelectorAll('*').length") == 0, (
        "destroy() must leave nothing the instance built inside its root"
    )
    page.wait_for_function("(n) => window.__sockets[n].readyState === 3", arg=before, timeout=5000)
    count_after_destroy = page.evaluate("() => window.__sockets.length")
    page.wait_for_timeout(3000)
    assert page.evaluate("() => window.__sockets.length") == count_after_destroy, (
        "a destroyed instance must not reconnect"
    )

    # Chats still sends and receives.
    _chats.send_first(page, "after the third instance")
    expect(_chats.messages(page, "user").last).to_contain_text("after the third instance")
    expect(_chats.messages(page, "assistant").last).to_be_visible(timeout=10000)

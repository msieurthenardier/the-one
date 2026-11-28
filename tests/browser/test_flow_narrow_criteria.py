"""The charter's criteria at the smallest window (sortie 21 leg 3).

Criterion 1: at 624x321 (the desktop minimum) every destination, every agent tab, every Library
editor kind (a create form and an existing item) and every Settings page shows a visible pane
at least 360px wide that never scrolls sideways, an open chat keeps three transcript lines
above the composer (with the telemetry row and one attachment row shown), and the last control
of every scroll container clears the GleepGlorp corner button. Criterion 3: no sideways scroll
at 480x321 and 360x640. Criterion 4: at 1024x768 and 1280x800 the values this leg touches
resolve to what they were.

Each test visits many routes and reports every violation by route, so a failure names the page.
The criterion tests run in Chromium and WebKit (``engine_browser`` + ``credentialed_context``);
run the ``layout`` lane with ``THE_ONE_REQUIRE_WEBKIT=1``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.conftest import credentialed_context
from browser.seeders import (
    canonical_schedule,
    enable_notes,
    seed_agent_routine,
    seed_connector,
    seed_knowledge_base,
    seed_mcp_source,
    seed_mock_agent,
    seed_mock_provider,
    seed_note,
    seed_secret,
    seed_session,
)
from playwright.sync_api import Browser, BrowserContext, Page

pytestmark = pytest.mark.browser

SMALL = {"width": 624, "height": 321}
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
STAMP = "2026-06-15T11:30:00+00:00"

# One audit of the visible pane. `floor` is the narrowest the pane may be. Reports: the pane's
# width, the page's sideways overflow, visible elements past the right edge (an element inside an
# overflow-clipping ancestor that ends within the viewport does not count), and the last control
# of every scroll container (scrolled to its end) that is under the GleepGlorp corner button or
# is not the element at its own centre. Scroll containers are scrolled to the end first.
_AUDIT_JS = """() => {
  const FOC = 'a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"])';
  const vis = (App.shellPane && App.shellPane.visiblePane())
    || document.getElementById('main-content');
  const vw = window.innerWidth;
  const shown = (e) => {
    if (!e.getClientRects().length) return false;
    const cs = getComputedStyle(e);
    return cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const label = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '')
    + (e.getAttribute('data-testid') ? '[' + e.getAttribute('data-testid') + ']' : '')
    + (typeof e.className === 'string' && e.className
      ? '.' + e.className.trim().split(/\\s+/)[0] : '');
  const out = {
    pane: vis.id, paneW: Math.round(vis.getBoundingClientRect().width), vw,
    docOverflow: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth,
    escapes: [], blocked: [], corner: false, scrollers: [],
  };
  const clipped = (e) => {
    for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
      if (getComputedStyle(a).overflowX !== 'visible'
          && a.getBoundingClientRect().right <= vw + 1) return true;
    }
    return false;
  };
  vis.querySelectorAll('*').forEach((e) => {
    if (!shown(e) || (e.closest('svg') && e.tagName.toLowerCase() !== 'svg')) return;
    const r = e.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.right > vw + 1 && !clipped(e)) out.escapes.push(label(e) + ':' + Math.round(r.right));
  });
  out.escapes = out.escapes.slice(0, 6);
  const scrollers = [];
  vis.querySelectorAll('*').forEach((e) => {
    const cs = getComputedStyle(e);
    if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
        && e.scrollHeight > e.clientHeight + 1 && shown(e)) scrollers.push(e);
  });
  scrollers.forEach((e) => { e.scrollTop = e.scrollHeight; out.scrollers.push(label(e)); });
  const corner = document.getElementById('gleepglorp-corner-button');
  out.corner = !!corner && shown(corner);
  const hitOk = (e, hit) => !!hit && (e === hit || e.contains(hit) || hit.contains(e)
    || (e.labels && [...e.labels].some((l) => l.contains(hit))));
  (scrollers.length ? scrollers : [vis]).forEach((root) => {
    const ctl = [...root.querySelectorAll(FOC)].filter((e) => {
      if (!shown(e) || e.disabled || e.closest('[inert]')) return false;
      const b = e.getBoundingClientRect();
      return b.width >= 8 && b.height >= 8 && b.bottom > 0;
    });
    ctl.sort((a, b) => a.getBoundingClientRect().bottom - b.getBoundingClientRect().bottom);
    const e = ctl[ctl.length - 1];
    if (!e) return;
    const r = e.getBoundingClientRect();
    if (out.corner) {
      const c = corner.getBoundingClientRect();
      if (r.left < c.right && r.right > c.left && r.top < c.bottom && r.bottom > c.top) {
        out.blocked.push(label(e) + ' overlaps the corner button');
      }
    }
    // The centre of the part inside the window (a control taller than the window is judged
    // where it can be seen).
    const mid = (Math.max(r.top, 0) + Math.min(r.bottom, innerHeight)) / 2;
    [[r.left + r.width / 2, mid], [r.right - 4, mid]].forEach(([x, y]) => {
      if (!hitOk(e, document.elementFromPoint(x, y))) {
        out.blocked.push(label(e) + ' is covered at ' + Math.round(x) + ',' + Math.round(y));
      }
    });
  });
  out.blocked = out.blocked.slice(0, 6);
  return out;
}"""

# The open chat's transcript: how many 14px-body lines fit above the composer.
_CHAT_JS = """() => {
  const q = (s) => document.querySelector(s);
  const box = (s) => { const e = q(s); if (!e) return null; const b = e.getBoundingClientRect();
    return { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left),
             right: Math.round(b.right), h: Math.round(b.height) }; };
  const msgs = q('.chat-instance .messages');
  const cs = getComputedStyle(msgs);
  const lh = parseFloat(getComputedStyle(q('.ui-message')).lineHeight);
  return {
    vh: innerHeight, header: box('.chat-instance .chat-header'),
    composer: box('.area-chat .ui-composer'), telemetry: box('.ui-composer-telemetry'),
    attachments: box('[data-testid="chat-attachments"]'), input: box('.ui-composer-input'),
    send: box('.ui-composer-send'), transcript: box('.chat-instance .messages'),
    lineHeight: lh,
    lines: Math.floor(
      (msgs.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)) / lh),
  };
}"""


@dataclass
class Rich:
    base: str
    data_dir: Path
    provider: str
    agent: str
    kb: str
    mcp: str
    connector: str
    secret: str
    session: str


def _post(base: str, path: str, body: dict) -> dict:
    r = httpx.post(f"{base}{path}", json=body, headers=auth_headers_for(base), timeout=10)
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture
def rich(app_with_data_dir: tuple[str, Path]) -> Rich:
    """An app with something on every page: one agent with a rule, a note and routines, ten
    more agents and chats (so the list columns scroll), a knowledge base, an MCP server, a
    connector, a secret and a chat with a long history."""
    base, data_dir = app_with_data_dir
    provider = seed_mock_provider(base)
    agent = seed_mock_agent(base, provider)
    for i in range(10):
        seed_mock_agent(base, provider, name=f"extra-{i}")
        seed_knowledge_base(base, f"Extra base {i}")
        seed_session(base, agent, f"Older chat {i}", f"2026-06-{10 + i:02d}T11:30:00+00:00")
    _post(base, f"/api/agents/{agent}/rules", {"text": "Answer briefly.", "enabled": True})
    enable_notes(base, agent)
    seed_note(data_dir, agent, "The operator prefers short answers.")
    for name in ("morning", "evening"):
        seed_agent_routine(data_dir, agent, name, schedule=canonical_schedule("09:00"))
    history = []
    for i in range(6):
        history.append({"role": "user", "content": f"Question {i}: " + "word " * 12})
        history.append({"role": "assistant", "content": f"Answer {i}: " + "word " * 30})
    return Rich(
        base=base,
        data_dir=data_dir,
        provider=provider,
        agent=agent,
        kb=seed_knowledge_base(base, "Main base"),
        mcp=seed_mcp_source(base, "main-server", tools=["alpha", "beta"]),
        connector=seed_connector(base, "main-connector"),
        secret=seed_secret(base, "main-secret"),
        session=seed_session(base, agent, "Long chat", STAMP, messages=history),
    )


AGENT_TABS = (
    "general",
    "rules-and-notes",
    "knowledge",
    "tools",
    "routines",
    "self-configuration",
)
SETTINGS_PAGES = (
    "gleepglorp",
    "appearance",
    "date-and-time",
    "prompts",
    "encryption",
    "tools",
    "knowledge-indexing",
)


def _library_routes(r: Rich) -> list[str]:
    return [
        "library/providers/~new",
        f"library/providers/{_nav.seg(r.provider)}",
        "library/knowledge/~new",
        f"library/knowledge/{_nav.seg(r.kb)}",
        "library/mcp/~new",
        f"library/mcp/{_nav.seg(r.mcp)}",
        "library/connectors/~new",
        f"library/connectors/{_nav.seg(r.connector)}",
        "library/secrets/~new",
        f"library/secrets/{_nav.seg(r.secret)}",
    ]


def _agent_routes(r: Rich) -> list[str]:
    return [f"agents/{_nav.seg(r.agent)}/{tab}" for tab in AGENT_TABS]


def _settings_routes(_r: Rich) -> list[str]:
    return [f"settings/{page}" for page in SETTINGS_PAGES]


_READY_ANY = (
    '#main-content :is(input:not([type="hidden"]), textarea, select, button, [role="tab"],'
    " .page-title, pre)"
)
# The first visible tool tile grid (Settings > Built-in tools holds one per category tab).
_GRID_JS = """() => [...document.querySelectorAll('.ui-tool-tile-grid')]
  .find((g) => g.getClientRects().length > 0)"""


def _open(context: BrowserContext, r: Rich, route: str) -> Page:
    """A fresh page on *route*, settled (the area's fetches done and its content shown)."""
    page = context.new_page()
    _nav.goto_settled(page, r.base, route)
    ready = _READY_ANY
    if route.startswith("agents/"):
        # Below 768px the tablist is hidden behind the tabs menu button, so the selected tab
        # is read from the menu's checked item (its popup is closed, so not "visible").
        tab = route.rsplit("/", 1)[1]
        page.wait_for_function(
            """(t) => !!document.querySelector(
              `[data-testid="tab-${t}"][aria-selected="true"],
               [data-testid="tab-${t}-menu-item"][aria-checked="true"]`)""",
            arg=tab,
            timeout=15000,
        )
        ready = '[data-testid="agent-tabs-menu-btn"], [role="tab"][aria-selected="true"]'
    # Some matches are visually hidden inputs (a radio), so wait for ANY visible match.
    page.wait_for_function(
        """(s) => [...document.querySelectorAll(s)].some(
          (e) => e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden')""",
        arg=ready,
        timeout=15000,
    )
    _nav.wait_settled(page)
    return page


def _problems(
    page: Page, route: str, *, floor: int, corner: bool, size: dict | None = None
) -> list[str]:
    """The audit's findings for the page now open, each named by *route*."""
    res = page.evaluate(_AUDIT_JS)
    found: list[str] = []
    if res["paneW"] < floor:
        found.append(f"{route}: visible pane {res['paneW']}px < {floor}px")
    if res["docOverflow"] > 0:
        found.append(f"{route}: page scrolls sideways by {res['docOverflow']}px")
    if res["escapes"]:
        found.append(f"{route}: past the right edge: {res['escapes']}")
    if res["blocked"]:
        found.append(f"{route}: last control not clear: {res['blocked']}")
    if corner and not res["corner"]:
        found.append(f"{route}: the corner button is not shown (the clearance check is moot)")
    return found


def _visit_all(
    browser: Browser, r: Rich, routes: list[str], viewport: dict, *, floor: int, corner: bool
) -> list[str]:
    context = credentialed_context(browser, r.base, viewport=viewport)
    found: list[str] = []
    try:
        for route in routes:
            page = _open(context, r, route)
            try:
                found += _problems(page, route, floor=floor, corner=corner)
            finally:
                page.close()
    finally:
        context.close()
    return found


def _stage_image(page: Page) -> None:
    page.locator('[data-testid="chat-image-input"]').set_input_files(
        files=[{"name": "a.png", "mimeType": "image/png", "buffer": PNG}]
    )
    page.wait_for_selector('[data-testid="chat-attachment"]', state="visible")


def _open_chat(context: BrowserContext, r: Rich) -> Page:
    page = _open(context, r, f"chats/{_nav.seg(r.session)}")
    page.wait_for_selector(".chat-instance .ui-message", state="visible", timeout=15000)
    page.wait_for_selector('[data-testid="chat-telemetry"]', state="visible", timeout=15000)
    return page


# ── AC1 / AC2 / AC5: the open chat ───────────────────────────────────────────


def test_open_chat_keeps_three_lines_with_toolbar_telemetry_and_an_attachment(
    engine_browser: Browser, rich: Rich
) -> None:
    """AC1's measurement as a regression: at 624x321 the header is 40px, Send sits beside the
    input, and at least three 14px lines show above the composer with the telemetry row and one
    attachment row shown."""
    context = credentialed_context(engine_browser, rich.base, viewport=SMALL)
    try:
        page = _open_chat(context, rich)
        _stage_image(page)
        m = page.evaluate(_CHAT_JS)
        assert m["header"]["h"] == 40, m
        assert m["telemetry"]["h"] > 0 and m["attachments"]["h"] > 0, m
        assert m["lines"] >= 3, f"only {m['lines']} transcript lines fit: {m}"
        # Send is in the input's row: they overlap vertically, Send is to its right.
        assert (
            m["send"]["top"] < m["input"]["bottom"] and m["send"]["bottom"] > m["input"]["top"]
        ), m
        assert m["send"]["left"] >= m["input"]["right"] - 1, m
        assert (
            m["composer"]["bottom"] <= m["vh"] and m["transcript"]["bottom"] <= m["composer"]["top"]
        ), m
    finally:
        context.close()


@pytest.mark.parametrize("width", [624, 880])
@pytest.mark.parametrize("with_attachment", [False, True])
def test_short_window_composer_is_one_centred_row(
    engine_browser: Browser, rich: Rich, width: int, with_attachment: bool
) -> None:
    """HAT batch 2: in a short window the attach button, the input and Send share one
    vertically centred row inside the box, and the input is the widest of them."""
    context = credentialed_context(
        engine_browser, rich.base, viewport={"width": width, "height": 321}
    )
    try:
        page = _open_chat(context, rich)
        if with_attachment:
            _stage_image(page)
        m = page.evaluate(
            """() => {
              const r = (s) => { const b = document.querySelector(s).getBoundingClientRect();
                return { top: b.top, bottom: b.bottom, w: b.width, cy: (b.top + b.bottom) / 2 }; };
              return { box: r('.ui-composer-box'), attach: r('.ui-composer-attach'),
                       input: r('.ui-composer-input'), send: r('.ui-composer-send'),
                       tele: r('[data-testid="chat-telemetry"]') };
            }"""
        )
        row = [m["attach"], m["input"], m["send"]]
        cys = [b["cy"] for b in row]
        assert max(cys) - min(cys) <= 3, m
        assert all(b["top"] > m["box"]["top"] for b in row), m
        assert m["input"]["w"] > max(m["attach"]["w"], m["send"]["w"]), m
        assert m["tele"]["bottom"] <= m["box"]["top"], m
    finally:
        context.close()


def test_chat_chrome_is_unchanged_in_a_tall_window(page: Page, rich: Rich) -> None:
    """At 1024x768 and 1280x800 the chat header, composer padding and Send's row are as before."""
    for size in ({"width": 1024, "height": 768}, {"width": 1280, "height": 800}):
        page.set_viewport_size(size)
        _nav.goto_settled(page, rich.base, f"chats/{_nav.seg(rich.session)}")
        page.wait_for_selector(".chat-instance .ui-message", state="visible", timeout=15000)
        v = page.evaluate(
            """() => {
              const q = (s) => document.querySelector(s);
              const cs = (s) => getComputedStyle(q(s));
              const send = q('.ui-composer-send').getBoundingClientRect();
              const input = q('.ui-composer-input').getBoundingClientRect();
              return { header: cs('.chat-instance .chat-header').height,
                       composerPad: cs('.area-chat .ui-composer').padding,
                       boxDir: cs('.ui-composer-box').flexDirection,
                       toolbar: cs('.ui-composer-toolbar').display,
                       msgPad: cs('.chat-instance .messages').padding,
                       railOverflow: cs('.ui-rail').overflowY,
                       sendBelow: send.top >= input.bottom };
            }"""
        )
        assert v == {
            "header": "48px",
            "composerPad": "12px 24px 20px",
            "boxDir": "column",
            "toolbar": "flex",
            "msgPad": "20px",
            "railOverflow": "visible",
            "sendBelow": True,
        }, (size, v)


def test_short_wide_window_compacts_and_keeps_both_panes(page: Page, rich: Rich) -> None:
    """A wide-but-short window (1280x450) gets the compaction (the accepted exception) and
    still shows both panes."""
    page.set_viewport_size({"width": 1280, "height": 450})
    _nav.goto_settled(page, rich.base, f"chats/{_nav.seg(rich.session)}")
    page.wait_for_selector(".chat-instance .ui-message", state="visible", timeout=15000)
    v = page.evaluate(
        """() => {
          const shown = (id) => document.getElementById(id).getClientRects().length > 0;
          const header = document.querySelector('.chat-instance .chat-header');
          return { header: getComputedStyle(header).height,
                   sidebar: shown('app-sidebar'), main: shown('main-content') };
        }"""
    )
    assert v == {"header": "40px", "sidebar": True, "main": True}, v


# ── AC2: the rail at a short height ──────────────────────────────────────────


def test_rail_fits_at_321_and_scrolls_below_that(page: Page, rich: Rich) -> None:
    """At 624x321 every rail item and Jump to are inside the window; in a window too short for
    the rail (624x200) it scrolls vertically and the last control can be scrolled into view."""
    page.set_viewport_size(SMALL)
    _nav.goto_settled(page, rich.base, f"chats/{_nav.seg(rich.session)}")
    fits = page.evaluate(
        """() => {
          const rail = document.querySelector('.ui-rail');
          const ctl = [...rail.querySelectorAll('a,button')]
            .filter((e) => e.getClientRects().length);
          return { overflowY: getComputedStyle(rail).overflowY, n: ctl.length,
                   inside: ctl.every((e) => { const b = e.getBoundingClientRect();
                     return b.top >= 0 && b.bottom <= innerHeight; }) };
        }"""
    )
    assert fits["overflowY"] == "auto" and fits["n"] >= 5 and fits["inside"], fits
    page.set_viewport_size({"width": 624, "height": 200})
    scrolls = page.evaluate(
        """() => {
          const rail = document.querySelector('.ui-rail');
          const jump = document.querySelector('[data-testid="rail-jump-to"]');
          const before = rail.scrollHeight > rail.clientHeight;
          jump.scrollIntoView({ block: 'nearest' });
          const b = jump.getBoundingClientRect();
          return { before, reachable: b.top >= 0 && b.bottom <= innerHeight, top: rail.scrollTop };
        }"""
    )
    assert scrolls["before"] and scrolls["reachable"] and scrolls["top"] > 0, scrolls


# ── AC5: criterion 1 at 624x321, every page ──────────────────────────────────


def test_chat_page_at_624x321(engine_browser: Browser, rich: Rich) -> None:
    context = credentialed_context(engine_browser, rich.base, viewport=SMALL)
    try:
        page = _open_chat(context, rich)
        _stage_image(page)
        found = _problems(page, "chats/{id}", floor=360, corner=False)
        lines = page.evaluate(_CHAT_JS)["lines"]
        if lines < 3:
            found.append(f"chats/{{id}}: {lines} transcript lines above the composer")
        assert not found, "\n".join(found)
    finally:
        context.close()


def test_agent_tabs_at_624x321(engine_browser: Browser, rich: Rich) -> None:
    found = _visit_all(engine_browser, rich, _agent_routes(rich), SMALL, floor=360, corner=True)
    assert not found, "\n".join(found)


# The editor header's controls (sortie 21 HAT feature F3): every visible button in the header
# and the tabs menu area ends inside the window, with no sideways scroll.
_HEADER_JS = """() => {
  const vw = innerWidth, out = {over: [], names: [], docOverflow:
    document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth};
  const hdr = document.querySelector('.ui-editor-shell-header');
  const regions = [hdr, document.querySelector('.ui-tabs-menu')].filter(Boolean);
  out.hasHeader = !!hdr;
  regions.forEach((root) => {
    const rr = root.getBoundingClientRect();
    if (rr.right > vw + 1) out.over.push(root.className.split(' ')[0] + ':' + Math.round(rr.right));
    root.querySelectorAll('button, a').forEach((e) => {
      if (!e.getClientRects().length) return;
      out.names.push(e.getAttribute('data-testid') || e.className.split(' ')[0]);
      const r = e.getBoundingClientRect();
      if (r.right > vw + 1 || r.left < -1) {
        out.over.push((e.getAttribute('data-testid') || e.tagName) + ':' + Math.round(r.right));
      }
    });
  });
  return out;
}"""


def test_editor_headers_and_tabs_menu_fit_at_624x321(engine_browser: Browser, rich: Rich) -> None:
    routes = {
        f"agents/{_nav.seg(rich.agent)}/general": [
            "editor-more-btn",
            "save-agent-btn",
            "agent-tabs-menu-btn",
        ],
        f"library/providers/{_nav.seg(rich.provider)}": ["test-connection-btn"],
        f"library/mcp/{_nav.seg(rich.mcp)}": [],
    }
    context = credentialed_context(engine_browser, rich.base, viewport=SMALL)
    found: list[str] = []
    try:
        for route, need in routes.items():
            page = _open(context, rich, route)
            try:
                res = page.evaluate(_HEADER_JS)
                if not res["hasHeader"]:
                    found.append(f"{route}: no editor header")
                if res["over"]:
                    found.append(f"{route}: past the right edge: {res['over']}")
                if res["docOverflow"] > 0:
                    found.append(f"{route}: page scrolls sideways by {res['docOverflow']}px")
                for tid in need:
                    if tid not in res["names"]:
                        found.append(f"{route}: {tid} is not visible ({res['names']})")
            finally:
                page.close()
    finally:
        context.close()
    assert not found, "\n".join(found)


def test_library_editors_at_624x321(engine_browser: Browser, rich: Rich) -> None:
    found = _visit_all(engine_browser, rich, _library_routes(rich), SMALL, floor=360, corner=True)
    assert not found, "\n".join(found)


def test_settings_pages_at_624x321(engine_browser: Browser, rich: Rich) -> None:
    found = _visit_all(engine_browser, rich, _settings_routes(rich), SMALL, floor=360, corner=True)
    assert not found, "\n".join(found)


def _list_columns(context: BrowserContext, r: Rich, floor: int) -> list[str]:
    """Each destination's list column (the Settings nav included), reached by the rail."""
    page = _open_chat(context, r)
    found: list[str] = []
    try:
        # Chats first: a rail click with a chat open shows its list; from another destination
        # the Chats icon returns to the last chat.
        for dest in ("chats", "agents", "library", "settings"):
            page.locator(f'[data-testid="rail-{dest}"]').click()
            page.wait_for_function(
                """() => document.querySelector('.app-shell-row')
                  .getAttribute('data-pane') === 'list'""",
                timeout=8000,
            )
            _nav.wait_settled(page)
            found += _problems(page, f"{dest} list", floor=floor, corner=dest != "chats")
    finally:
        page.close()
    return found


def test_list_columns_at_624x321(engine_browser: Browser, rich: Rich) -> None:
    """The four list columns fill the window at 624x321 and their last row clears the corner
    button (the list body is the element that scrolls)."""
    context = credentialed_context(engine_browser, rich.base, viewport=SMALL)
    try:
        found = _list_columns(context, rich, floor=360)
    finally:
        context.close()
    assert not found, "\n".join(found)


def test_modals_fit_at_624x321(engine_browser: Browser, rich: Rich) -> None:
    """The agent delete dialog and Jump to fit the 321px window or scroll inside themselves."""
    context = credentialed_context(engine_browser, rich.base, viewport=SMALL)
    found: list[str] = []
    try:
        page = _open(context, rich, f"agents/{_nav.seg(rich.agent)}/general")
        page.locator('[data-testid="delete-agent-btn"]').scroll_into_view_if_needed()
        page.locator('[data-testid="delete-agent-btn"]').click()
        found += _dialog_problems(page, "agent delete dialog")
        page.keyboard.press("Escape")
        page.locator('[data-testid="rail-jump-to"]').click()
        page.wait_for_selector("#jump-to-dialog[open]")
        found += _dialog_problems(page, "Jump to")
        page.close()
    finally:
        context.close()
    assert not found, "\n".join(found)


def _dialog_problems(page: Page, name: str) -> list[str]:
    page.wait_for_selector(".modal-dialog", state="visible")
    d = page.evaluate(
        """() => {
          const el = document.querySelector('.modal-dialog');
          const b = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          const btns = [...el.querySelectorAll('button')].filter((e) => e.getClientRects().length);
          // A control scrolled out of sight inside a scrolling dialog is reachable; one beyond
          // the window of a dialog that does not scroll is not.
          const scrolls = (cs.overflowY === 'auto' || cs.overflowY === 'scroll')
            && el.scrollHeight > el.clientHeight;
          const lastBtn = btns.length ? btns[btns.length - 1].getBoundingClientRect() : null;
          return { l: b.left, r: b.right, t: b.top, b: b.bottom, vw: innerWidth, vh: innerHeight,
                   scrolls, btnBottom: lastBtn ? lastBtn.bottom : 0 };
        }"""
    )
    problems = []
    if d["l"] < 0 or d["r"] > d["vw"]:
        problems.append(f"{name}: sideways {d}")
    if d["t"] < 0 or d["b"] > d["vh"] + 1:
        problems.append(f"{name}: taller than the window {d}")
    if not d["scrolls"] and d["btnBottom"] > d["vh"]:
        problems.append(f"{name}: a button is below the window {d}")
    return problems


# ── AC6: criterion 3, no sideways scroll at 480x321 and 360x640 ──────────────


@pytest.mark.parametrize(
    "size",
    [{"width": 480, "height": 321}, {"width": 360, "height": 640}],
    ids=["480x321", "360x640"],
)
def test_no_sideways_scroll_on_any_destination(
    engine_browser: Browser, rich: Rich, size: dict
) -> None:
    """Every destination's root (the list or nav) and one item each: no sideways page scroll
    and nothing past the right edge."""
    context = credentialed_context(engine_browser, rich.base, viewport=size)
    found: list[str] = []
    try:
        found += _list_columns(context, rich, floor=0)
        item_routes = [
            f"agents/{_nav.seg(rich.agent)}/general",
            f"agents/{_nav.seg(rich.agent)}/tools",
            f"library/providers/{_nav.seg(rich.provider)}",
            f"library/knowledge/{_nav.seg(rich.kb)}",
            "settings/appearance",
            "settings/tools",
            "settings/prompts",
        ]
        for route in item_routes:
            page = _open(context, rich, route)
            try:
                found += _problems(page, route, floor=0, corner=True)
            finally:
                page.close()
        page = _open_chat(context, rich)
        try:
            found += _problems(page, "chats/{id}", floor=0, corner=False)
        finally:
            page.close()
    finally:
        context.close()
    assert not found, "\n".join(found)


# ── AC4: the width clamps ────────────────────────────────────────────────────


def test_modal_and_tile_grid_clamp_below_the_fixed_widths(page: Page, rich: Rich) -> None:
    """At 300x568 (narrower than the modal's old 320px minimum, and than one
    280px tile column) the delete dialog and the Built-in tools tile grid stay inside the window."""
    page.set_viewport_size({"width": 300, "height": 568})
    _nav.goto_settled(page, rich.base, "settings/tools")
    page.wait_for_function(f"({_GRID_JS})() !== undefined", timeout=15000)
    grid = page.evaluate(
        """() => {
          const g = [...document.querySelectorAll('.ui-tool-tile-grid')]
            .find((e) => e.getClientRects().length > 0);
          if (!g) return null;
          // The tiles, not the grid box: a track wider than the grid overflows it.
          const tiles = [...g.children].filter((e) => e.getClientRects().length > 0);
          const right = Math.max(g.getBoundingClientRect().right,
                                 ...tiles.map((t) => t.getBoundingClientRect().right));
          const doc = document.scrollingElement;
          return { right, vw: innerWidth, tiles: tiles.length,
                   cols: getComputedStyle(g).gridTemplateColumns.split(' ').length,
                   over: doc.scrollWidth - doc.clientWidth };
        }"""
    )
    assert grid is not None and grid["tiles"] > 0, grid
    assert grid["right"] <= grid["vw"] and grid["over"] <= 0, grid
    _nav.goto_settled(page, rich.base, f"agents/{_nav.seg(rich.agent)}/general")
    page.wait_for_selector('[data-testid="delete-agent-btn"]', state="visible", timeout=15000)
    page.locator('[data-testid="delete-agent-btn"]').scroll_into_view_if_needed()
    page.locator('[data-testid="delete-agent-btn"]').click()
    assert not _dialog_problems(page, "agent delete dialog at 300px")


@pytest.mark.parametrize(
    "size",
    [{"width": 1024, "height": 768}, {"width": 1280, "height": 800}],
    ids=["1024x768", "1280x800"],
)
def test_clamped_values_are_unchanged_at_768_and_wider(page: Page, rich: Rich, size: dict) -> None:
    """Every clamp resolves to today's value at 1024 and 1280: the modal minimum, the tile
    grid's tracks, the 32px form, list, item and page-header paddings, the facts column."""
    page.set_viewport_size(size)
    values: dict[str, object] = {}
    _nav.goto_settled(page, rich.base, "settings/prompts")
    page.wait_for_selector(".admin-form, .admin-content", state="visible", timeout=15000)
    values["form"] = page.evaluate(
        "() => getComputedStyle(document.querySelector('.admin-form')).padding"
    )
    values["pageHeader"] = page.evaluate(
        "() => getComputedStyle(document.querySelector('#main-content .page-header')).padding"
    )
    _nav.goto_settled(page, rich.base, "settings/tools")
    page.wait_for_selector(".settings-list", state="visible", timeout=15000)
    values["settingsList"] = page.evaluate(
        "() => getComputedStyle(document.querySelector('.settings-list')).padding"
    )
    _nav.goto_settled(page, rich.base, "settings/tools")
    page.wait_for_function(f"({_GRID_JS})() !== undefined", timeout=15000)
    values["tileTrack"] = page.evaluate(
        f"() => getComputedStyle(({_GRID_JS})()).gridTemplateColumns.split(' ')[0]"
    )
    _nav.goto_settled(page, rich.base, f"agents/{_nav.seg(rich.agent)}/general")
    page.wait_for_selector('[data-testid="delete-agent-btn"]', state="visible", timeout=15000)
    page.locator('[data-testid="delete-agent-btn"]').scroll_into_view_if_needed()
    page.locator('[data-testid="delete-agent-btn"]').click()
    page.wait_for_selector(".modal-dialog", state="visible")
    values["modal"] = page.evaluate(
        """() => { const cs = getComputedStyle(document.querySelector('.modal-dialog'));
                   const w = document.querySelector('.modal-dialog').getBoundingClientRect().width;
                   return [cs.minWidth, cs.maxHeight, cs.overflowY, w].join(' '); }"""
    )
    assert values["form"] == "0px 32px 40px"
    assert values["pageHeader"] == "16px 32px"
    assert values["settingsList"] in ("0px 32px", "0px 32px 40px")
    # The clamp's computed value keeps its expression; the box is the 460px the 480px maximum
    # gives, as before.
    assert values["modal"] == "min(320px, 100% - 24px) none visible 460"
    assert float(str(values["tileTrack"]).removesuffix("px")) >= 280, values


@pytest.mark.parametrize(
    "size",
    [{"width": 1024, "height": 768}, {"width": 1280, "height": 800}],
    ids=["1024x768", "1280x800"],
)
def test_criterion_1_checks_hold_at_wide_widths(
    engine_browser: Browser, rich: Rich, size: dict
) -> None:
    """The same page checks at 1024x768 and 1280x800 (the last control clears the corner button
    where the button is shown; nothing past the edge)."""
    routes = _agent_routes(rich) + _library_routes(rich) + _settings_routes(rich)
    found = _visit_all(engine_browser, rich, routes, size, floor=360, corner=True)
    # Chats hides the corner button (corner=False), so the check is that nothing overflows and
    # the last control is reachable; the open chat's transcript and composer are on screen.
    context = credentialed_context(engine_browser, rich.base, viewport=size)
    try:
        page = _open_chat(context, rich)
        found += _problems(page, "chats/{id}", floor=360, corner=False)
        if not page.locator(".ui-composer-send").is_visible():
            found.append("chats/{id}: the Send button is not reachable")
    finally:
        context.close()
    assert not found, "\n".join(found)


def test_padding_steps_down_below_768(page: Page, rich: Rich) -> None:
    """Below 768px the 32px form, list, item and page-header paddings are 16px."""
    page.set_viewport_size({"width": 700, "height": 600})
    _nav.goto_settled(page, rich.base, "settings/prompts")
    page.wait_for_selector(".admin-form", state="visible", timeout=15000)
    got = page.evaluate(
        """() => {
          const pad = (s) => getComputedStyle(document.querySelector(s)).padding;
          return { form: pad('.admin-form'), header: pad('#main-content .page-header') };
        }"""
    )
    assert got == {"form": "0px 16px 40px", "header": "16px"}, got
    _nav.goto_settled(page, rich.base, "settings/tools")
    page.wait_for_selector(".settings-list", state="visible", timeout=15000)
    list_pad = page.evaluate(
        "() => getComputedStyle(document.querySelector('.settings-list')).paddingLeft"
    )
    assert list_pad == "16px", list_pad

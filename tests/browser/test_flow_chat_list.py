"""The Chats list column (M25 F4 leg 4a, flight DD5, reference spec 5.1).

An ``App.ui.listPane`` titled "Chats" (``chats-list``, 300px at every width)
whose header block is the full-width New chat button (``chats-new-btn``), over
the cross-agent history in recency groups: Today, Yesterday, Last 7 days, Last
30 days and Older (sentence case), newest first, empty groups hidden. Rows
(``chat-row``) are links to ``#chats/{id}`` with the title, a hand-formatted
local time and the agent; a connector row carries its platform as a neutral
badge; each session row has a delete action (``chat-row-delete``). The pending
chat's row is a selected link to its own ``#chats/~new/{agent}`` with no
action.

Sessions are seeded through ``POST /api/chat/sessions`` (``seed_session``),
which honours ``updated_at``, so rows land in every group. Times are computed
in the BROWSER's local time (the list buckets by local calendar day), each a
local 12:30 on its day except the newest, a few seconds ago.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


@pytest.fixture(autouse=True)
def _pin_operator_zone(request: pytest.FixtureRequest, page: Page) -> None:
    """Make the operator zone the browser's own zone, by construction (M28 F2 L1).

    The list now buckets and labels in the operator's zone; the stamps below are computed
    in the browser's local zone. Pinning the operator zone to the browser's resolved zone
    keeps them agreeing whatever the host's tzlocal name is, and exercises the
    operator-zone path. Only tests that seed times (``app_with_agent``) need it."""
    if "app_with_agent" not in request.fixturenames:
        return
    base = request.getfixturevalue("app_with_agent").base_url
    zone = page.evaluate("() => Intl.DateTimeFormat().resolvedOptions().timeZone")
    r = httpx.put(
        f"{base}/api/time-settings",
        json={"mode": "zone", "zone": zone},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text


LIST = '[data-testid="chats-list"]'
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# [days ago, hour, minute] -> the instant (local time) plus its local parts.
# hour None: a few seconds ago (the newest row, auto-joined on a cold #chats).
# hour "f": earlier today, m (a fraction) of the way from local midnight to now,
# so it is always today and always before "now" however close to midnight it runs.
_STAMPS_JS = """
(specs) => specs.map(([days, h, m]) => {
  const now = new Date();
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const d = h === null ? new Date(now.getTime() - 3000)
    : h === 'f' ? new Date(midnight.getTime() + (now.getTime() - midnight.getTime()) * m)
    : new Date(now.getFullYear(), now.getMonth(), now.getDate() - days, h, m, 30);
  return {iso: d.toISOString(), wd: d.getDay(), mon: d.getMonth(), day: d.getDate(),
          h: d.getHours(), m: d.getMinutes()};
})
"""

# The list as rendered: [{group, rows: [{id, pending, label, time, meta, badges,
# badgeClasses, href, current, tag, action}]}].
_LIST_JS = """
() => Array.from(document.querySelectorAll('[data-testid="chats-list"] .ui-list-pane-group'))
  .filter((g) => !g.hidden)
  .map((g) => ({
    group: g.querySelector('.ui-list-pane-caption').textContent,
    rows: Array.from(g.querySelectorAll('li')).map((li) => {
      const r = li.querySelector('[data-testid="chat-row"]');
      const t = r.querySelector('.ui-list-pane-time');
      const meta = r.querySelector('.ui-list-pane-meta');
      const act = li.querySelector('[data-testid="chat-row-delete"]');
      const bs = Array.from(r.querySelectorAll('.ui-list-pane-badges > *'));
      return {
        id: r.dataset.id || null, pending: r.dataset.pending || null,
        label: r.querySelector('.ui-list-pane-label').textContent,
        time: t ? t.textContent : '', meta: meta ? meta.textContent : '',
        badges: bs.map((b) => b.textContent), badgeClasses: bs.map((b) => b.className),
        href: r.getAttribute('href'), current: r.getAttribute('aria-current'), tag: r.tagName,
        action: act ? act.getAttribute('aria-label') : null,
      };
    }),
  }))
"""


def _stamps(page: Page, specs: list[list[Any]]) -> list[dict[str, Any]]:
    """Instants in the browser's local time (it shares the host's zone).

    A test that mixes "now" (3 s ago) with early-today rows is not meaningful in
    the first minute of the day, where "now" itself falls on yesterday."""
    if page.evaluate(
        "() => { const n = new Date(); return n.getHours() === 0 && n.getMinutes() < 1; }"
    ):
        pytest.skip("within the first minute after local midnight")
    return page.evaluate(_STAMPS_JS, specs)


def _hhmm(s: dict[str, Any]) -> str:
    """The Today time as the list draws it: local 12-hour, ``h:mm AM/PM`` (DD14)."""
    return f"{s['h'] % 12 or 12}:{s['m']:02d} {'AM' if s['h'] < 12 else 'PM'}"


def _md(s: dict[str, Any]) -> str:
    return f"{MONTHS[s['mon']]} {s['day']}"


def _list(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(_LIST_JS)


def _wait_rows(page: Page, n: int) -> None:
    expect(_chats.chat_rows(page)).to_have_count(n, timeout=8000)


def _sessions(base: str) -> list[dict[str, Any]]:
    r = httpx.get(f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5)
    r.raise_for_status()
    return r.json()


# ── Groups, boundaries, times, rows ─────────────────────────────────────────


def test_groups_boundaries_times_and_cross_agent_rows(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Day 0, 1, 2, 6, 7, 29, 30 and 400 land in Today, Yesterday, Last 7 days
    (2 and 6), Last 30 days (7 and 29) and Older (30 and 400), newest first,
    under sentence-case captions, with h:mm AM/PM / weekday / "Mon D" times. The
    rows interleave agents, a null agent reads "Default agent", and a connector
    row carries its platform as a neutral badge pill."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    other = seed_mock_agent(base, app_with_agent.provider_id, name="Beta")
    st = _stamps(
        page,
        [
            [0, None, None],
            [0, "f", 0.5],
            [1, 12, 30],
            [2, 12, 30],
            [6, 12, 30],
            [7, 12, 30],
            [29, 12, 30],
            [30, 12, 30],
            [400, 12, 30],
        ],
    )
    ids = {}
    ids["now"] = seed_session(base, agent, "Fresh chat", st[0]["iso"])
    ids["dawn"] = seed_session(base, other, "Early chat", st[1]["iso"])
    ids["d1"] = seed_session(base, None, "Default chat", st[2]["iso"])
    ids["d2"] = seed_session(base, other, "Two days", st[3]["iso"], platform="discord")
    ids["d6"] = seed_session(base, agent, "Six days", st[4]["iso"])
    ids["d7"] = seed_session(base, other, "Seven days", st[5]["iso"])
    ids["d29"] = seed_session(base, agent, "Twenty-nine days", st[6]["iso"])
    ids["d30"] = seed_session(base, other, "Thirty days", st[7]["iso"])
    ids["d400"] = seed_session(base, agent, "Last year", st[8]["iso"])
    # The REST round trip honours updated_at (AC16's premise).
    by_id = {s["id"]: s for s in _sessions(base)}
    assert by_id[ids["d400"]]["updated_at"].startswith(st[8]["iso"][:10])

    _nav.goto(page, base, "chats")
    _wait_rows(page, 9)
    # A cold #chats auto-joins the most recent session: its row is selected.
    _chats.expect_chat(page, agent)
    expect(_chats.chat_row(page, ids["now"])).to_have_attribute("aria-current", "page")

    got = _list(page)
    assert [g["group"] for g in got] == [
        "Today",
        "Yesterday",
        "Last 7 days",
        "Last 30 days",
        "Older",
    ]
    rows = {g["group"]: [(r["label"], r["time"], r["meta"]) for r in g["rows"]] for g in got}
    assert rows == {
        "Today": [("Fresh chat", _hhmm(st[0]), agent), ("Early chat", _hhmm(st[1]), "Beta")],
        "Yesterday": [("Default chat", WEEKDAYS[st[2]["wd"]], "Default agent")],
        "Last 7 days": [
            ("Two days", WEEKDAYS[st[3]["wd"]], "Beta"),
            ("Six days", WEEKDAYS[st[4]["wd"]], agent),
        ],
        "Last 30 days": [
            ("Seven days", _md(st[5]), "Beta"),
            ("Twenty-nine days", _md(st[6]), agent),
        ],
        "Older": [("Thirty days", _md(st[7]), "Beta"), ("Last year", _md(st[8]), agent)],
    }
    flat = [r for g in got for r in g["rows"]]
    for r in flat:
        assert r["tag"] == "A" and r["pending"] is None, r
        assert r["href"] == _nav.href(f"chats/{_nav.seg(r['id'])}"), r
        assert r["action"] == f"Delete chat: {r['label']}", r
    # Only the connector row has a badge: its platform, the neutral library
    # badge pill (class never built from the value).
    assert {r["label"]: (r["badges"], r["badgeClasses"]) for r in flat if r["badges"]} == {
        "Two days": (["Discord"], ["badge badge--unknown"])
    }
    # One selected row.
    assert [r["label"] for r in flat if r["current"]] == ["Fresh chat"]
    # The same bucketing for dates the API cannot seed (missing, invalid,
    # future): Older with no time, and a future date counts as Today.
    edge = page.evaluate(
        """() => { const L = App.chat.chatsList, f = new Date(Date.now() + 3600000);
          return [L.bucketFor({}), L.timeFor({}), L.bucketFor({updated_at: 'nope'}),
                  L.timeFor({updated_at: 'nope'}), L.bucketFor({updated_at: f.toISOString()}),
                  L.bucketFor({created_at: new Date().toISOString()})]; }"""
    )
    assert edge == ["older", "", "older", "", "today", "today"]


# ── The pending row and the selection ───────────────────────────────────────


def test_pending_row_is_the_selected_link_with_no_action(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A pick shows one row at the top of Today: "New chat", "now", the agent;
    a link to its own `~new` route (aria-current="page"), data-pending, no
    data-id and no delete action; the selected row. The first send swaps it
    for the session's row (selected); opening another chat discards a new
    pending one."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    (old,) = _stamps(page, [[0, "f", 0.5]])
    old_id = seed_session(base, agent, "Old today", old["iso"])
    _nav.goto(page, base, "chats")
    _wait_rows(page, 1)
    expect(_chats.chat_row(page, old_id)).to_have_attribute("aria-current", "page")

    _chats.start_chat(page, agent)
    pending = _chats.pending_row(page)
    expect(pending).to_have_count(1)
    got = _list(page)
    assert got[0]["group"] == "Today"
    first = got[0]["rows"][0]
    assert first == {
        "id": None,
        "pending": "true",
        "label": "New chat",
        "time": "now",
        "meta": agent,
        "badges": [],
        "badgeClasses": [],
        "href": _nav.href(f"chats/~new/{_nav.seg(agent)}"),
        "current": "page",
        "tag": "A",
        "action": None,
    }
    assert [r["label"] for r in got[0]["rows"]] == ["New chat", "Old today"]
    expect(_chats.chat_row(page, old_id)).not_to_have_attribute("aria-current", "page")
    # The pending row is not a session row (no data-id).
    expect(_chats.chat_rows(page)).to_have_count(1)

    # The first send: the session's row replaces the pending row, selected.
    sid = _chats.send_first(page, "hello")
    expect(pending).to_have_count(0)
    expect(_chats.chat_row(page, sid)).to_have_attribute("aria-current", "page")
    _wait_rows(page, 2)

    # A new pending chat, then opening another chat: the pending row goes.
    _chats.start_chat(page, agent)
    expect(pending).to_have_count(1)
    _chats.open_chat(page, old_id)
    expect(pending).to_have_count(0)
    expect(_chats.chat_row(page, old_id)).to_have_attribute("aria-current", "page")
    expect(page.locator(f'{LIST} [aria-current="page"]')).to_have_count(1)


# ── Row delete ──────────────────────────────────────────────────────────────


def test_row_delete_arms_confirms_and_focuses_the_neighbour(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The row action arms (``.confirm-delete`` on the row's <li>, the title
    swapped), the second press deletes over the WebSocket, and focus goes to
    the neighbouring row (the next one), never <body>."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    st = _stamps(page, [[0, None, None], [0, "f", 0.6], [0, "f", 0.3]])
    a = seed_session(base, agent, "Chat A", st[0]["iso"])
    b = seed_session(base, agent, "Chat B", st[1]["iso"])
    c = seed_session(base, agent, "Chat C", st[2]["iso"])
    _nav.goto(page, base, "chats")
    _wait_rows(page, 3)
    expect(_chats.chat_row(page, a)).to_have_attribute("aria-current", "page")

    row_b = _chats.chat_row(page, b)
    li_b = page.locator("li").filter(has=row_b)
    action = _chats.chat_row_delete(page, b)
    row_b.focus()
    page.keyboard.press("Tab")
    expect(action).to_be_focused()
    expect(action).to_have_attribute("aria-label", "Delete chat: Chat B")
    page.keyboard.press("Enter")  # arm
    expect(li_b).to_have_class(re.compile(r"\bconfirm-delete\b"))
    # A1: the focused button's name changes with the armed state (4.1.2).
    expect(action).to_have_attribute("aria-label", "Confirm delete: Chat B")
    expect(row_b.locator(".ui-list-pane-label")).to_have_text("Confirm delete?")
    assert {s["id"] for s in _sessions(base)} == {a, b, c}  # nothing deleted yet
    page.keyboard.press("Enter")  # confirm
    expect(row_b).to_have_count(0, timeout=8000)
    _wait_rows(page, 2)
    assert {s["id"] for s in _sessions(base)} == {a, c}
    # Focus moved to the neighbouring row (C, the next row), not <body>.
    _chats.wait_row_has_focus(page, c)
    # The open chat (A) is untouched.
    expect(_chats.chat_row(page, a)).to_have_attribute("aria-current", "page")


def test_armed_delete_label_reverts_on_lapse(app_with_agent: SeededApp, page: Page) -> None:
    """A1: "Confirm delete: {title}" while armed, "Delete chat: {title}" again
    once the arm lapses, and nothing is deleted."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    (st,) = _stamps(page, [[0, None, None]])
    sid = seed_session(base, agent, "Lapse me", st["iso"])
    _nav.goto(page, base, "chats")
    _wait_rows(page, 1)
    row = _chats.chat_row(page, sid)
    li = page.locator("li").filter(has=row)
    action = _chats.chat_row_delete(page, sid)
    row.focus()
    page.keyboard.press("Tab")
    expect(action).to_be_focused()
    page.keyboard.press("Enter")
    expect(action).to_have_attribute("aria-label", "Confirm delete: Lapse me")
    expect(li).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=6000)
    expect(action).to_have_attribute("aria-label", "Delete chat: Lapse me")
    assert {s["id"] for s in _sessions(base)} == {sid}


# ── Off Chats ───────────────────────────────────────────────────────────────


def test_a_rest_fetch_of_sessions_off_chats_is_safe(app_with_agent: SeededApp, page: Page) -> None:
    """AC6: the list renders from the store's `sessions` subscription, so a
    REST fetch from another destination (the palette's, in leg 7) is safe: before
    the chat area exists nothing renders, and once it does the hidden list
    re-renders from the REST rows, with no page error."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    (st,) = _stamps(page, [[0, None, None]])
    sid = seed_session(base, agent, "Primed over REST", st["iso"])
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Booted on Agents: the chat area is not initialised; a REST get works.
    _nav.goto(page, base, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    assert page.evaluate("() => App.store.get('sessions').then((r) => r.map((s) => s.id))") == [sid]
    expect(page.locator(LIST)).to_have_count(0)
    # Chats renders it; back on Agents a forced REST fetch re-renders the
    # hidden list.
    _nav.open_destination(page, "chats")
    expect(_chats.chat_row(page, sid)).to_be_visible(timeout=8000)
    _nav.open_destination(page, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    page.evaluate("() => App.store.get('sessions', {force: true})")
    expect(page.locator(LIST)).to_be_hidden()
    expect(_chats.chat_row(page, sid)).to_have_count(1)
    assert errors == []


# ── Empty, setup incomplete, width ──────────────────────────────────────────


def test_empty_list_says_no_conversations_yet(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    pane = page.locator(LIST)
    expect(pane.locator(".ui-list-pane-empty")).to_be_visible()
    expect(pane.locator(".ui-list-pane-empty")).to_contain_text("No conversations yet.")
    expect(page.locator('[data-testid="chat-row"]')).to_have_count(0)
    expect(_chats.chats_new_button(page)).to_be_enabled()


def test_new_chat_disabled_while_setup_is_incomplete(app_clean: str, page: Page) -> None:
    """No provider or no agent: New chat is natively disabled (the welcome's
    guidance explains why) and App.chat.openPicker is an inert no-op. With
    setup complete (the next activation re-reads it) it is enabled."""
    _nav.goto(page, app_clean, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    expect(page.locator(".chat-welcome-guidance")).to_be_visible()
    btn = _chats.chats_new_button(page)
    expect(btn).to_be_disabled()
    expect(btn).to_have_text("New chat")
    page.evaluate("() => App.chat.openPicker({})")
    expect(_chats.picker(page)).to_have_count(0)

    # A provider only: still incomplete.
    provider_id = seed_mock_provider(app_clean)
    _nav.open_destination(page, "agents")
    _nav.open_destination(page, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    # The activation re-read the setup (the providers list now has one row).
    page.wait_for_function(
        "() => (App.store.peek('providers').value || []).length === 1", timeout=8000
    )
    page.wait_for_timeout(200)
    expect(btn).to_be_disabled()

    # Setup complete: enabled on the next activation, and the picker opens.
    seed_mock_agent(app_clean, provider_id, name="ready-agent")
    _nav.open_destination(page, "agents")
    _nav.open_destination(page, "chats")
    expect(btn).to_be_enabled(timeout=8000)
    _chats.open_picker(page)
    expect(_chats.picker_row(page, "ready-agent")).to_have_count(1)


@pytest.mark.parametrize(("width", "height"), [(1024, 768), (1440, 900)])
def test_chats_column_is_300px_with_a_full_width_new_chat(
    app_with_agent: SeededApp, page: Page, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    _nav.goto(page, app_with_agent.base_url, "chats")
    expect(page.locator(LIST)).to_be_visible(timeout=8000)
    geo = page.evaluate(
        """() => {
          const aside = document.getElementById('app-sidebar');
          const pane = aside.querySelector('[data-testid="chats-list"]');
          const block = pane.querySelector('.ui-list-pane-block');
          const btn = block.querySelector('[data-testid="chats-new-btn"]');
          const bs = getComputedStyle(block), b = btn.getBoundingClientRect();
          const inner = block.getBoundingClientRect().width
            - parseFloat(bs.paddingLeft) - parseFloat(bs.paddingRight);
          return {aside: aside.getBoundingClientRect().width,
                  asidePadTop: getComputedStyle(aside).paddingTop,
                  pane: pane.getBoundingClientRect().width,
                  title: pane.querySelector('h2').textContent,
                  btnW: Math.round(b.width), inner: Math.round(inner), btnH: Math.round(b.height),
                  cls: btn.className, svg: !!btn.querySelector('svg'),
                  filter: !!pane.querySelector('input')};
        }"""
    )
    assert geo["aside"] == 300, geo
    assert geo["asidePadTop"] == "0px", geo
    assert geo["title"] == "Chats" and geo["filter"] is False, geo
    assert geo["btnW"] == geo["inner"] and geo["btnH"] == 36, geo
    assert "btn-filled-primary" in geo["cls"] and "btn-lg" in geo["cls"] and geo["svg"], geo


def test_clock_formatter_edges(app_with_agent: SeededApp, page: Page) -> None:
    """``App.time.formatClock`` (DD14): 12-hour ``h:mm AM/PM``, no leading zero on
    the hour, at midnight, noon and the minutes around them. Browser-local here
    (``setZone(null)``, only after the boot has settled)."""
    _nav.goto_settled(page, app_with_agent.base_url, "chats")
    got = page.evaluate(
        """() => App.time.setZone(null) || [[0, 0], [0, 5], [9, 7], [11, 59], [12, 0],
                  [12, 59], [13, 0], [15, 45], [23, 59]]
          .map(([h, m]) => App.time.formatClock(new Date(2026, 5, 15, h, m, 30)))"""
    )
    assert got == [
        "12:00 AM",
        "12:05 AM",
        "9:07 AM",
        "11:59 AM",
        "12:00 PM",
        "12:59 PM",
        "1:00 PM",
        "3:45 PM",
        "11:59 PM",
    ]


def _toasts(page: Page):
    return page.locator(".app-flash")


def _hover_action(page: Page, sid: str):
    """The row's delete action is shown on hover or focus: hover the row first."""
    _chats.chat_row(page, sid).hover()
    return _chats.chat_row_delete(page, sid)


def test_arming_sets_the_confirm_name_and_a_lapse_restores_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    """onArmChange: arming names the action "Confirm delete: {title}", a lapse restores it."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    (st,) = _stamps(page, [[0, None, None]])
    sid = seed_session(base, agent, "Arm me", st["iso"])
    _nav.goto(page, base, "chats")
    _wait_rows(page, 1)
    action = _hover_action(page, sid)
    action.click()
    expect(action).to_have_attribute("aria-label", "Confirm delete: Arm me")
    expect(action).to_have_attribute("aria-label", "Delete chat: Arm me", timeout=6000)


def test_delete_while_offline_reverts_the_arm_and_says_why(
    app_with_agent: SeededApp, page: Page
) -> None:
    """DD11 6: with the socket down, the confirming click reverts the arm, shows the
    sentence, and sends nothing."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    (st,) = _stamps(page, [[0, None, None]])
    sid = seed_session(base, agent, "Offline row", st["iso"])
    _nav.goto(page, base, "chats")
    _wait_rows(page, 1)
    # Close the socket and keep the reconnect from succeeding for the test's duration.
    page.evaluate(
        """() => {
          const sent = window.__fakeSent = [];
          const real = window.WebSocket;
          const Fake = function () {
            return { readyState: 0, send: (m) => sent.push(m), close() {} };
          };
          Fake.OPEN = real.OPEN; Fake.CLOSED = real.CLOSED; Fake.CONNECTING = real.CONNECTING;
          Fake.CLOSING = real.CLOSING;
          window.WebSocket = Fake;
          const area = App.areas.find((a) => a.id === 'chat');
          area._ws().close();
        }"""
    )
    page.wait_for_function(
        "() => !App.areas.find((a) => a.id === 'chat')._ws() || "
        "App.areas.find((a) => a.id === 'chat')._ws().readyState !== 1"
    )
    li = page.locator("li").filter(has=_chats.chat_row(page, sid))
    action = _hover_action(page, sid)
    action.click()
    expect(action).to_have_attribute("aria-label", "Confirm delete: Offline row")
    action.click()
    expect(
        _toasts(page).filter(has_text="Not connected, so the chat wasn't deleted.")
    ).to_have_count(1)
    expect(li).not_to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(action).to_have_attribute("aria-label", "Delete chat: Offline row")
    assert page.evaluate("() => window.__fakeSent") == []
    assert {s["id"] for s in _sessions(base)} == {sid}


def test_online_delete_shows_no_not_connected_toast(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    (st,) = _stamps(page, [[0, None, None]])
    sid = seed_session(base, agent, "Online row", st["iso"])
    _nav.goto(page, base, "chats")
    _wait_rows(page, 1)
    action = _hover_action(page, sid)
    action.click()
    action.click()
    _wait_rows(page, 0)
    expect(_toasts(page).filter(has_text="Not connected")).to_have_count(0)

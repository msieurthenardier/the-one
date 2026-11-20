"""The form-fill receipts (M36 F3 L6 Part A, flight DD7).

A GleepGlorp form fill draws a receipt in every chat instance showing the conversation. Fills are
seeded straight into the database (only GleepGlorp's fill tool writes one), so the join's
``proposals_snapshot`` (which also carries ``fills``) draws them; live behaviour is scripted with
``_chats.emit_frame``. Covers, as state transitions:

* [requested] -> [held while the turn runs] -> [drawn after the turn] -> [applying] -> each final
  status, in place (A1), a reload through the snapshot (A1), a frame for another chat ignored;
* a proposal and a fill of one turn in tool-call order, live in either arrival order and after a
  reload (A2);
* the "Check this" flag with its sources (A3);
* Chats receipts have no buttons; the drawer's have Fill now (the retry cases) and Show the form,
  and a click reaches the instance's ``fillHooks`` (A4).

Falls in the ``shared`` browser lane (it is not claimed by a named lane glob).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _chats, _drawer, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import (
    seed_gleepglorp_fill,
    seed_gleepglorp_proposal,
    seed_knowledge_base,
    seed_mcp_source,
    seed_mock_agent,
    seed_mock_provider,
)
from browser.test_flow_chat_proposals import _call, _changed, _world
from browser.test_flow_chat_proposals import _view as _proposal_view
from browser.test_flow_chat_turn_work import DONE, _chunk, _frames, _user
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages

pytestmark = pytest.mark.browser

RECEIPT = '[data-testid="fill-receipt"]'
ANNOUNCE = '[data-testid="fill-receipt-announce"]'
FILL_NOW = '[data-testid="fill-receipt-fill-now"]'
SHOW_FORM = '[data-testid="fill-receipt-show-form"]'
DRAWER_RECEIPT = f"{_drawer.DRAWER} {RECEIPT}"

_CARDS_JS = """() => Array.from(
  document.querySelectorAll('.area-chat .messages > [data-card-kind]')
).map(e => e.dataset.cardKind + ':' + e.dataset.cardId)"""


def _fill_view(fid: int, **over: Any) -> dict:
    return {
        "id": fid,
        "kind": "agent",
        "action": "change",
        "agent_name": "plain",
        "status": "sent",
        "outcome": None,
        "untrusted": False,
        "untrusted_sources": [],
        "created_at": "2026-01-02T10:00:00+00:00",
        "claimed_at": None,
        "resolved_at": None,
        "tool_call_id": "t1",
        "values": {"description": "Live"},
        "changes": {"description": "Live"},
        "base": {"description": ""},
        "labels": {"description": "Description", "system_prompt": "System prompt"},
        "title": "Change agent “plain”",
        "field_count": 1,
        "target_gone": False,
        "stale": [],
        **over,
    }


def _requested(page: Page, sid: str, view: dict) -> None:
    _chats.emit_frame(page, {"type": "fill_requested", "session_id": sid, "fill": view})


def _fchanged(page: Page, sid: str, view: dict) -> None:
    _chats.emit_frame(page, {"type": "fill_changed", "session_id": sid, "fill": view})


def _receipt(page: Page, fid: int):
    return page.locator(f'{RECEIPT}[data-fill-id="{fid}"]')


def _text(page: Page, fid: int, testid: str):
    return _receipt(page, fid).locator(f'[data-testid="{testid}"]')


def _open(page: Page, w: SimpleNamespace) -> None:
    page.goto(w.base)
    _chats.open_chat(page, w.sid)


def _seed(w: SimpleNamespace, **kw: Any) -> int:
    return seed_gleepglorp_fill(w.data, w.sid, **kw)


# ── A1: live and reload ─────────────────────────────────────────────────────


def test_a_receipt_is_held_during_the_turn_then_follows_every_status_in_place(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, messages=encode_messages([]))
    _open(page, w)
    expect(page.locator(RECEIPT)).to_have_count(0)

    # [working] the receipt is held while the turn runs.
    _frames(page, _user("fill it"), _chunk("Filling."), *_call("t1"))
    _requested(page, w.sid, _fill_view(7, tool_call_id="t1"))
    page.wait_for_timeout(200)
    expect(page.locator(RECEIPT)).to_have_count(0)
    # [working] -> [done]: group, reply, then the receipt.
    _frames(page, _chunk("Look at the form."), DONE)
    expect(_receipt(page, 7)).to_have_count(1)
    expect(_receipt(page, 7)).to_have_attribute("data-status", "sent")
    expect(_text(page, 7, "fill-receipt-headline")).to_have_text("Filling the form…")
    assert page.evaluate(_CARDS_JS) == ["fill:7"]
    page.evaluate(
        "() => { window.__r = document.querySelector('[data-testid=\"fill-receipt\"]'); }"
    )

    # [sent] -> [applying] -> each final status, on the same element.
    _fchanged(page, w.sid, _fill_view(7, status="applying", claimed_at="2026-01-02T10:00:05+00:00"))
    expect(_receipt(page, 7)).to_have_attribute("data-status", "applying")
    expect(_text(page, 7, "fill-receipt-headline")).to_have_text("Filling the form…")

    done_at = "2026-01-02T10:00:09+00:00"
    _fchanged(
        page,
        w.sid,
        _fill_view(
            7,
            status="filled",
            outcome={"kept": [], "reason": None},
            field_count=3,
            resolved_at=done_at,
        ),
    )
    expect(_receipt(page, 7)).to_have_attribute("data-status", "filled")
    expect(_text(page, 7, "fill-receipt-headline")).to_have_text("Form filled")
    expect(_text(page, 7, "fill-receipt-title")).to_have_text("Change agent “plain”")
    expect(_text(page, 7, "fill-receipt-detail")).to_have_text("3 fields · Not saved")

    _fchanged(
        page,
        w.sid,
        _fill_view(
            7,
            status="partly_filled",
            outcome={"kept": ["system_prompt"], "reason": None},
            field_count=1,
            resolved_at=done_at,
        ),
    )
    expect(_text(page, 7, "fill-receipt-headline")).to_have_text("Form partly filled")
    expect(_text(page, 7, "fill-receipt-detail")).to_have_text("1 field · Not saved")
    expect(_text(page, 7, "fill-receipt-kept")).to_have_text(
        "You had changed System prompt and not saved them, so I left them."
    )

    reasons = {
        "in_chats": "You were in Chats when it arrived.",
        "stay": "You chose to stay on the page you were editing.",
        "editor_unavailable": "The agent editor could not open.",
        "target_gone": "That agent no longer exists.",
    }
    for reason, text in reasons.items():
        _fchanged(
            page,
            w.sid,
            _fill_view(
                7,
                status="not_filled",
                outcome={"kept": [], "reason": reason},
                resolved_at=done_at,
            ),
        )
        expect(_receipt(page, 7)).to_have_attribute("data-status", "not_filled")
        expect(_text(page, 7, "fill-receipt-headline")).to_have_text("Form not filled")
        expect(_text(page, 7, "fill-receipt-reason")).to_have_text(text)

    _fchanged(page, w.sid, _fill_view(7, status="replaced", resolved_at=done_at))
    expect(_receipt(page, 7)).to_have_attribute("data-status", "replaced")
    expect(_text(page, 7, "fill-receipt-headline")).to_have_text("Replaced by a newer fill.")
    # Every status was drawn in place: one receipt, the very same element.
    expect(page.locator(RECEIPT)).to_have_count(1)
    assert page.evaluate(
        "() => document.querySelector('[data-testid=\"fill-receipt\"]') === window.__r"
    )

    # A frame for another chat draws nothing and changes nothing.
    _requested(page, "other-chat", _fill_view(8))
    _fchanged(page, "other-chat", _fill_view(7, status="filled"))
    page.wait_for_timeout(200)
    expect(page.locator(RECEIPT)).to_have_count(1)
    expect(_receipt(page, 7)).to_have_attribute("data-status", "replaced")


def test_a_reload_draws_every_status_through_the_snapshot(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, tool_ids=tuple(f"tc-{i}" for i in range(1, 6)))
    sent = _seed(w, tool_call_id="tc-1", changes={"description": "A"})
    filled = _seed(
        w,
        tool_call_id="tc-2",
        changes={"description": "B", "system_prompt": "C"},
        status="filled",
        outcome={"kept": [], "reason": None},
    )
    partly = _seed(
        w,
        tool_call_id="tc-3",
        changes={"description": "D", "system_prompt": "E"},
        status="partly_filled",
        outcome={"kept": ["description"], "reason": None},
    )
    stay = _seed(
        w,
        tool_call_id="tc-4",
        changes={"description": "F"},
        status="not_filled",
        outcome={"kept": [], "reason": "stay"},
    )
    replaced = _seed(w, tool_call_id="tc-5", changes={"description": "G"}, status="replaced")
    _open(page, w)
    for fid in (sent, filled, partly, stay, replaced):
        expect(_receipt(page, fid)).to_have_count(1)
    expect(_receipt(page, sent)).to_have_attribute("data-status", "sent")
    expect(_text(page, sent, "fill-receipt-headline")).to_have_text("Filling the form…")
    expect(_text(page, filled, "fill-receipt-headline")).to_have_text("Form filled")
    expect(_text(page, filled, "fill-receipt-detail")).to_have_text("2 fields · Not saved")
    expect(_text(page, partly, "fill-receipt-kept")).to_have_text(
        "You had changed Description and not saved them, so I left them."
    )
    expect(_text(page, stay, "fill-receipt-reason")).to_have_text(
        "You chose to stay on the page you were editing."
    )
    expect(_text(page, replaced, "fill-receipt-headline")).to_have_text("Replaced by a newer fill.")
    assert page.evaluate(_CARDS_JS) == [f"fill:{i}" for i in (sent, filled, partly, stay, replaced)]
    # Chats: no buttons on any receipt.
    expect(page.locator(f"{RECEIPT} button")).to_have_count(0)

    page.reload()
    _chats.open_chat(page, w.sid)
    expect(page.locator(RECEIPT)).to_have_count(5)
    assert page.evaluate(_CARDS_JS) == [f"fill:{i}" for i in (sent, filled, partly, stay, replaced)]
    # A re-join draws each once, not twice.
    page.evaluate("() => window.App.areas.find(a => a.id === 'chat')._joinSession('nope')")
    _chats.open_chat(page, w.sid)
    expect(page.locator(RECEIPT)).to_have_count(5)


# ── A2: mixed order with the proposal cards ──────────────────────────────────


def test_a_proposal_and_a_fill_of_one_turn_keep_their_tool_call_order_live_and_reloaded(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, messages=encode_messages([]))
    _open(page, w)
    _frames(page, _user("both"), _chunk("Doing both."), *_call("t1"), *_call("t2"))

    # The fill made by the first tool call arrives AFTER the proposal of the second.
    _changed(page, w.sid, _proposal_view(11, w.sid, tool_call_id="t2"))
    _requested(page, w.sid, _fill_view(3, tool_call_id="t1"))
    _frames(page, _chunk("Review both."), DONE)
    expect(page.locator(RECEIPT)).to_have_count(1)
    expect(page.locator('[data-testid="proposal-card"]')).to_have_count(1)
    assert page.evaluate(_CARDS_JS) == ["fill:3", "proposal:11"]

    # And the other way round: the fill is the later tool call, the proposal arrives last.
    _frames(page, _user("again"), _chunk("Again."), *_call("t3"), *_call("t4"))
    _requested(page, w.sid, _fill_view(4, tool_call_id="t4"))
    _changed(
        page, w.sid, _proposal_view(12, w.sid, tool_call_id="t3", changes={"description": "Second"})
    )
    _frames(page, _chunk("Review."), DONE)
    assert page.evaluate(_CARDS_JS) == ["fill:3", "proposal:11", "proposal:12", "fill:4"]


@pytest.mark.parametrize("fill_first", [True, False])
def test_a_reload_orders_a_fill_and_a_proposal_by_their_tool_calls(
    app_with_data_dir: tuple[str, Any], page: Page, fill_first: bool
) -> None:
    w = _world(app_with_data_dir, tool_ids=("tc-1", "tc-2"))
    fill_call, proposal_call = ("tc-1", "tc-2") if fill_first else ("tc-2", "tc-1")
    # The proposal is seeded first (a lower id), so an id order alone would put it first.
    pid = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        agent_name="plain",
        tool_call_id=proposal_call,
        changes={"description": "Words"},
        base={"description": ""},
    )
    fid = _seed(w, tool_call_id=fill_call, changes={"description": "Fill"})
    _open(page, w)
    expect(page.locator(RECEIPT)).to_have_count(1)
    expect(page.locator('[data-testid="proposal-card"]')).to_have_count(1)
    want = [f"fill:{fid}", f"proposal:{pid}"] if fill_first else [f"proposal:{pid}", f"fill:{fid}"]
    assert page.evaluate(_CARDS_JS) == want


# ── A3: the flag ────────────────────────────────────────────────────────────


def test_an_untrusted_fill_shows_the_check_this_flag_with_its_sources(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, tool_ids=("tc-1", "tc-2"))
    flagged = _seed(
        w,
        tool_call_id="tc-1",
        changes={"description": "From the web"},
        untrusted=True,
        sources=["web_fetch", "file"],
    )
    clean = _seed(w, tool_call_id="tc-2", changes={"description": "Plain"})
    _open(page, w)
    flag = _receipt(page, flagged).locator('[data-testid="fill-receipt-flag"]')
    expect(flag).to_have_count(1)
    expect(flag).to_have_attribute(
        "aria-label",
        "Check this form fill: it was made after content that didn't come from you "
        "(web_fetch, file). It may have been planted.",
    )
    expect(_receipt(page, clean).locator('[data-testid="fill-receipt-flag"]')).to_have_count(0)


# ── A4: Chats is read-only; the drawer has the buttons ──────────────────────


def _drawer_world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    """A ready GleepGlorp, an agent ``plain`` and a drawer chat started with a real send."""
    base, data = app_with_data_dir
    provider = seed_mock_provider(
        base, name="gg-mock", config={"response": {"content": "Hello from the mock"}}
    )
    seed_mock_agent(base, provider, "plain")
    _drawer.put_settings(base, provider_config_id=provider, model="mock-default")
    _drawer.boot(page, base, "library")
    sid = _drawer.chat_with(page, "hi", "Hello from the mock")
    return SimpleNamespace(base=base, data=data, sid=sid)


def _reopen_drawer(page: Page, w: SimpleNamespace) -> None:
    page.reload()
    _drawer.boot(page, w.base, "library")
    _drawer.open_drawer(page)
    _drawer.wait_joined(page)


def test_the_drawer_offers_fill_now_for_the_retry_cases_and_chats_never(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _drawer_world(app_with_data_dir, page)
    now = datetime.now(UTC).isoformat()
    not_filled = _seed(
        w, changes={"description": "A"}, status="not_filled", outcome={"kept": [], "reason": "stay"}
    )
    gone = _seed(
        w,
        agent_name="ghost",
        changes={"description": "B"},
        status="not_filled",
        outcome={"kept": [], "reason": "target_gone"},
    )
    sent = _seed(w, changes={"description": "C"})
    old_applying = _seed(
        w,
        changes={"description": "D"},
        status="applying",
        claimed_at="2026-01-01T00:00:00+00:00",
        claim_token="old",
    )
    fresh_applying = _seed(
        w, changes={"description": "E"}, status="applying", claimed_at=now, claim_token="new"
    )
    filled = _seed(
        w, changes={"description": "F"}, status="filled", outcome={"kept": [], "reason": None}
    )
    replaced = _seed(w, changes={"description": "G"}, status="replaced")
    stale = _seed(
        w,
        changes={"description": "H"},
        base={"description": "zzz-no-longer-the-stored-value"},
        status="not_filled",
        outcome={"kept": [], "reason": "in_chats"},
    )
    _reopen_drawer(page, w)

    def card(fid: int):
        return page.locator(f'{DRAWER_RECEIPT}[data-fill-id="{fid}"]')

    expect(page.locator(DRAWER_RECEIPT)).to_have_count(8)
    for fid in (not_filled, sent, old_applying, stale):
        expect(card(fid).locator(FILL_NOW)).to_have_count(1)
        expect(card(fid).locator(FILL_NOW)).to_have_text("Fill now")
    for fid in (gone, fresh_applying, filled, replaced):
        expect(card(fid).locator(FILL_NOW)).to_have_count(0)
    # Show the form: on a filled fill (and a partly filled one), not on the others.
    expect(card(filled).locator(SHOW_FORM)).to_have_count(1)
    for fid in (not_filled, sent, gone, replaced):
        expect(card(fid).locator(SHOW_FORM)).to_have_count(0)
    # The stale field is named on the receipt that offers Fill now.
    expect(card(stale).locator('[data-testid="fill-receipt-stale"]')).to_have_text(
        "Changed since GleepGlorp filled it: Description."
    )
    expect(card(not_filled).locator('[data-testid="fill-receipt-stale"]')).to_have_count(0)

    # (Part A also pinned "the default hook does nothing and sends no request" here; since Part B
    # the drawer passes the real hooks, so the click below runs on a stub instead. The instance's
    # no-op default is still what Chats has: its receipts have no buttons at all.)
    # With stubbed hooks a click calls fillNow with the view; isApplying hides the button.
    page.evaluate(
        """() => {
          const h = App.gleepglorpDrawerChat.instance().fillHooks;
          window.__called = [];
          h.fillNow = (v) => window.__called.push(v.id);
        }"""
    )
    card(not_filled).locator(FILL_NOW).click()
    assert page.evaluate("() => window.__called") == [not_filled]
    page.evaluate(
        """() => {
          const i = App.gleepglorpDrawerChat.instance();
          i.fillHooks.isApplying = (id) => true;
          i.fillReceipts.refresh();
        }"""
    )
    expect(card(sent).locator(FILL_NOW)).to_have_count(0)
    # An applying fill whose lease ran out is retried only when this window is not applying it.
    expect(card(old_applying).locator(FILL_NOW)).to_have_count(0)
    expect(card(not_filled).locator(FILL_NOW)).to_have_count(1)

    # Show the form goes through the guard to the agent editor.
    card(filled).locator(SHOW_FORM).click()
    _nav.expect_route(page, "agents/plain/general", timeout=8000)


def test_chats_shows_the_same_receipts_without_buttons(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, tool_ids=("tc-1", "tc-2"))
    _seed(
        w,
        tool_call_id="tc-1",
        changes={"description": "A"},
        status="not_filled",
        outcome={"kept": [], "reason": "in_chats"},
    )
    _seed(
        w,
        tool_call_id="tc-2",
        changes={"description": "B"},
        status="filled",
        outcome={"kept": [], "reason": None},
    )
    _open(page, w)
    expect(page.locator(RECEIPT)).to_have_count(2)
    expect(page.locator(f"{RECEIPT} button")).to_have_count(0)
    expect(page.locator(FILL_NOW)).to_have_count(0)
    expect(page.locator(SHOW_FORM)).to_have_count(0)


# ══ Part B: applying (M36 F3 L6 Part B) ═══════════════════════════════════════════════════
#
# A real drawer send keeps the turn open (the GleepGlorp mock provider's ``delay_ms``); a seeded
# fill row's ``fill_requested`` is delivered into the drawer's socket, and the claim and the
# outcome use the real routes. The fill is applied by the window whose drawer owns the turn.

SAVE = '[data-testid="save-agent-btn"]'
CANCEL = '[data-testid="cancel-agent-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="agent-filled-note"]'
APPROVED_NOTE = '[data-testid="agent-approved-change-note"]'
DESC = "#studio-description"
PROMPT = "#studio-system-prompt"
PROVIDER = "#studio-provider"
MODEL = "#studio-model"
NAME = "#studio-name"
ITER = "#studio-max-iterations"
RETENTION = "#studio-retention-days"
SWITCH = '[data-testid="agent-rich-visuals-toggle"]'
COMPOSER = '[data-testid="gg-chat-input"]'
LONG = 25000  # ms the GleepGlorp turn stays open


def _bworld(
    app_with_data_dir: tuple[str, Any],
    page: Page,
    *,
    route: str = "library",
    delay_ms: int = LONG,
    send: bool = True,
) -> SimpleNamespace:
    """Two providers, an agent named ``plain``, a ready GleepGlorp and (by default) a drawer chat
    mid-turn on *route*."""
    base, data = app_with_data_dir
    models = {"models": ["mock-default", "mock-b"]}
    prov = seed_mock_provider(base, name="agent-mock", config=models)
    other = seed_mock_provider(base, name="other-mock", config=models)
    seed_mock_agent(base, prov, "plain")
    seed_mock_agent(base, prov, "other")
    _drawer.ready_with_reply(base, "Working on it", delay_ms=delay_ms)
    _drawer.boot(page, base, route)
    _drawer.open_drawer(page)
    sid = ""
    if send:
        _drawer.send(page, "please fill the form")
        sid = _drawer.wait_joined(page)
    return SimpleNamespace(base=base, data=data, sid=sid, prov=prov, other=other)


def _seed_b(w: SimpleNamespace, **kw: Any) -> int:
    kw.setdefault("agent_name", "plain")
    return seed_gleepglorp_fill(w.data, w.sid, **kw)


def _fills(w: SimpleNamespace) -> dict[int, dict]:
    r = httpx.get(
        f"{w.base}/api/gleepglorp/fills",
        params={"session_id": w.sid},
        headers=auth_headers_for(w.base),
        timeout=5.0,
    )
    return {f["id"]: f for f in r.json()["fills"]}


def _view(w: SimpleNamespace, fid: int) -> dict:
    return _fills(w)[fid]


def _deliver(page: Page, w: SimpleNamespace, *fids: int) -> None:
    """Deliver each fill's real view as a ``fill_requested`` into the drawer's socket, all in one
    task (so the applier's queue sees them together)."""
    frames = [
        {"type": "fill_requested", "session_id": w.sid, "fill": _view(w, fid)} for fid in fids
    ]
    page.evaluate(
        "(frames) => { const i = App.gleepglorpDrawerChat.instance();"
        " const r = window.__socks.find(x => x.ws === i.ws());"
        " frames.forEach(f => r.ws.onmessage({ data: JSON.stringify(f) })); }",
        frames,
    )


def _wait_status(page: Page, w: SimpleNamespace, fid: int, status: str, timeout: int = 12000):
    waited = 0
    while waited <= timeout:
        got = _view(w, fid)
        if got["status"] == status:
            return got
        page.wait_for_timeout(100)
        waited += 100
    raise AssertionError(f"fill {fid} is {_view(w, fid)['status']}, wanted {status}")


def _agent_json(w: SimpleNamespace, name: str = "plain") -> dict:
    r = httpx.get(
        f"{w.base}/api/agents/{_nav.seg(name)}", headers=auth_headers_for(w.base), timeout=5.0
    )
    assert r.status_code == 200, r.text
    return r.json()


def _editor_ready(page: Page, agent: str = "plain") -> None:
    expect(page.locator(DESC)).to_be_attached(timeout=10000)
    expect(page.locator(MODEL)).not_to_have_value("", timeout=10000)
    assert agent


def _open_agent_page(page: Page, agent: str = "plain", tab: str = "general") -> None:
    _nav.set_route(page, f"agents/{_nav.seg(agent)}/{tab}")
    _editor_ready(page, agent)


def _tool(page: Page, name: str):
    return page.locator(f'input[type="checkbox"][data-tool="{name}"]')


def _expand_filesystem(page: Page) -> None:
    page.locator('[data-category="Filesystem"] .ui-group-tile-expand').click()
    expect(_tool(page, "read_file")).to_be_visible()


def _open_tab(page: Page, agent: str, tab: str) -> None:
    # A click, not a route change: a dirty editor would ask the leave guard about the route.
    page.locator(f'[data-testid="tab-{tab}"]').click()
    expect(page.locator(f'[data-testid="tab-{tab}"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


# ── B1: settle, then write ──────────────────────────────────────────────────


def test_a_change_fill_from_library_opens_the_editor_and_writes_unsaved_edits(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    expect(page.locator(UNSAVED)).to_have_count(0)
    fid = _seed_b(
        w, changes={"description": "Filled description", "system_prompt": "Filled prompt"}
    )
    _deliver(page, w, fid)
    expect(page.locator(DESC)).to_have_value("Filled description", timeout=10000)
    expect(page.locator(PROMPT)).to_have_value("Filled prompt")
    _nav.wait_for_route_prefix(page, "agents/plain")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    # The values survive the activate re-patch (the fill waited for it).
    page.wait_for_timeout(600)
    expect(page.locator(DESC)).to_have_value("Filled description")
    expect(page.locator(PROMPT)).to_have_value("Filled prompt")
    # Nothing was stored.
    assert _agent_json(w)["description"] in ("", None)


@pytest.mark.parametrize("destination", ["library", "settings"])
def test_a_mounted_editor_on_another_destination_is_navigated_to_and_keeps_the_values(
    app_with_data_dir: tuple[str, Any], page: Page, destination: str
) -> None:
    w = _bworld(app_with_data_dir, page, send=False)
    # The editor stays mounted (clean) when the operator leaves Agents. Coming back from Settings
    # re-activates the Studio area, which re-selects the agent (a full re-patch that resets every
    # value): the fill must write after it.
    _open_agent_page(page)
    _nav.open_destination(page, destination)
    page.wait_for_function(f"() => App.router.current().destination === '{destination}'")
    _drawer.open_drawer(page)
    _drawer.send(page, "please fill the form")
    w.sid = _drawer.wait_joined(page)
    fid = _seed_b(w, changes={"description": "From the drawer"})
    _deliver(page, w, fid)
    _nav.wait_for_route_prefix(page, "agents/plain")
    expect(page.locator(DESC)).to_have_value("From the drawer", timeout=10000)
    _wait_status(page, w, fid, "filled")
    page.wait_for_timeout(600)
    expect(page.locator(DESC)).to_have_value("From the drawer")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")


def test_an_editor_already_open_on_agents_is_written_without_navigating(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    before = page.evaluate("() => [App.router.current().route, history.length]")
    fid = _seed_b(w, changes={"description": "In place"})
    _deliver(page, w, fid)
    expect(page.locator(DESC)).to_have_value("In place", timeout=10000)
    _wait_status(page, w, fid, "filled")
    after = page.evaluate("() => [App.router.current().route, history.length]")
    assert after == before


# ── B2: every field type ────────────────────────────────────────────────────


def _every_field_values(w: SimpleNamespace, kb: str, mcp: str) -> dict:
    return {
        "description": "Everything filled",
        "system_prompt": "You are filled.",
        "provider_config_id": w.other,
        "llm_model": "mock-b",
        "enabled_tools": ["read_file", "grep"],
        "mcp_source_ids": [mcp],
        "kb_ids": [kb],
        "rich_visuals": False,
        "max_iterations": 7,
        "chat_history_retention_days": 14,
    }


def _effective_enabled(agent: dict, names: list[str]) -> set[str]:
    if agent["enabled_tools"] is not None:
        return {n for n in names if n in agent["enabled_tools"]}
    return {n for n in names if n not in agent["disabled_tools"]}


def test_one_fill_carries_every_field_type_then_cancel_restores_and_save_stores(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    kb = seed_knowledge_base(w.base, "Docs")
    mcp = seed_mcp_source(w.base, "Search", ["lookup"])
    stored = _agent_json(w)
    values = _every_field_values(w, kb, mcp)
    fid = _seed_b(w, changes=values)
    _deliver(page, w, fid)
    expect(page.locator(DESC)).to_have_value("Everything filled", timeout=10000)
    expect(page.locator(PROMPT)).to_have_value("You are filled.")
    expect(page.locator(PROVIDER)).to_have_value(w.other)
    expect(page.locator(MODEL)).to_have_value("mock-b", timeout=10000)
    expect(page.locator(ITER)).to_have_value("7")
    expect(page.locator(RETENTION)).to_have_value("14")
    expect(page.locator(SWITCH)).not_to_be_checked()
    _wait_status(page, w, fid, "filled")
    # The model group is dirty after the list landed (the write order), and noted.
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    for field in (
        "description",
        "system_prompt",
        "llm_model",
        "max_iterations",
        "chat_history_retention_days",
        "rich_visuals",
    ):
        expect(page.locator(f'{NOTE}[data-field="{field}"]')).to_have_count(1)
    _open_tab(page, "plain", "tools")
    _expand_filesystem(page)
    expect(_tool(page, "read_file")).to_be_checked()
    expect(_tool(page, "grep")).to_be_checked()
    expect(page.locator('input[type="checkbox"][data-tool="shell"]')).not_to_be_checked()
    expect(page.locator(f'[data-testid="mcp-source-toggle-{mcp}"]')).to_be_checked()
    expect(page.locator(f'{NOTE}[data-field="mcp_source_ids"][data-item="{mcp}"]')).to_have_count(1)
    _open_tab(page, "plain", "knowledge")
    expect(page.locator(f'[data-testid="agent-knowledge-toggle-{kb}"]')).to_be_checked()
    expect(page.locator(f'{NOTE}[data-field="kb_ids"][data-item="{kb}"]')).to_have_count(1)
    _open_tab(page, "plain", "general")

    # Cancel restores every stored value, and the notes go.
    page.locator(CANCEL).click()
    expect(page.locator(DESC)).to_have_value(stored["description"] or "")
    expect(page.locator(PROMPT)).to_have_value(stored["system_prompt"])
    expect(page.locator(PROVIDER)).to_have_value(w.prov)
    expect(page.locator(MODEL)).to_have_value("mock-default", timeout=10000)
    expect(page.locator(ITER)).to_have_value(str(stored["max_iterations"]))
    expect(page.locator(SWITCH)).to_be_checked()
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("")

    # A second fill, then Save: the stored agent matches.
    fid2 = _seed_b(w, changes=values, tool_call_id="tc-2")
    _deliver(page, w, fid2)
    expect(page.locator(DESC)).to_have_value("Everything filled", timeout=10000)
    expect(page.locator(MODEL)).to_have_value("mock-b", timeout=10000)
    _wait_status(page, w, fid2, "filled")
    names = page.evaluate(
        "() => Array.from(document.querySelectorAll('input[type=checkbox][data-tool]'))"
        ".map(e => e.dataset.tool)"
    )
    page.locator(SAVE).click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=10000)
    expect(page.locator(NOTE)).to_have_count(0)
    saved = _agent_json(w)
    assert saved["description"] == "Everything filled"
    assert saved["system_prompt"] == "You are filled."
    assert saved["provider_config_id"] == w.other
    assert saved["llm_model"] == "mock-b"
    assert saved["max_iterations"] == 7
    assert saved["chat_history_retention_days"] == 14
    assert saved["rich_visuals"] is False
    assert saved["mcp_source_ids"] == [mcp]
    assert saved["kb_ids"] == [kb]
    exempt = {"current_time"}
    assert _effective_enabled(saved, [n for n in names if n not in exempt]) == {"read_file", "grep"}


def test_a_create_fill_fills_the_name_and_a_disabled_only_fill_never_widens_the_whitelist(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    # A create fill opens the create form and fills the name.
    fid = _seed_b(
        w,
        action="create",
        agent_name="brand-new",
        changes={
            "name": "brand-new",
            "description": "A new agent",
            "provider_config_id": w.prov,
            "llm_model": "mock-b",
        },
    )
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("brand-new", timeout=10000)
    expect(page.locator(DESC)).to_have_value("A new agent")
    expect(page.locator(MODEL)).to_have_value("mock-b", timeout=10000)
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(1)
    _wait_status(page, w, fid, "filled")

    # A disabled_tools-only fill against a stored whitelist turns the named tool off; a tool
    # outside the whitelist stays off.
    r = httpx.put(
        f"{w.base}/api/agents/plain",
        json={**_agent_json(w), "enabled_tools": ["read_file", "grep"]},
        headers=auth_headers_for(w.base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text
    page.locator(CANCEL).click()  # leave the create form clean
    fid2 = _seed_b(w, changes={"disabled_tools": ["grep"]}, tool_call_id="tc-2")
    _deliver(page, w, fid2)
    _nav.wait_for_route_prefix(page, "agents/plain")
    _open_tab(page, "plain", "tools")
    _expand_filesystem(page)
    expect(_tool(page, "grep")).not_to_be_checked(timeout=10000)
    expect(_tool(page, "read_file")).to_be_checked()
    expect(page.locator('input[type="checkbox"][data-tool="shell"]')).not_to_be_checked()
    _wait_status(page, w, fid2, "filled")


# ── B3: the model group ─────────────────────────────────────────────────────


def _model_world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    return w


def test_provider_and_model_leave_the_editor_dirty_after_the_list_loads_and_cancel_restores(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _model_world(app_with_data_dir, page)
    fid = _seed_b(w, changes={"provider_config_id": w.other, "llm_model": "mock-b"})
    _deliver(page, w, fid)
    expect(page.locator(MODEL)).to_have_value("mock-b", timeout=10000)
    expect(page.locator(PROVIDER)).to_have_value(w.other)
    _wait_status(page, w, fid, "filled")
    page.wait_for_timeout(500)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    page.locator(CANCEL).click()
    expect(page.locator(PROVIDER)).to_have_value(w.prov)
    expect(page.locator(MODEL)).to_have_value("mock-default", timeout=10000)


def test_a_model_only_fill_keeps_the_provider_and_a_provider_only_fill_keeps_the_model(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _model_world(app_with_data_dir, page)
    fid = _seed_b(w, changes={"llm_model": "mock-b"})
    _deliver(page, w, fid)
    expect(page.locator(MODEL)).to_have_value("mock-b", timeout=10000)
    expect(page.locator(PROVIDER)).to_have_value(w.prov)
    _wait_status(page, w, fid, "filled")
    page.locator(CANCEL).click()
    expect(page.locator(MODEL)).to_have_value("mock-default", timeout=10000)

    fid2 = _seed_b(w, changes={"provider_config_id": w.other}, tool_call_id="tc-2")
    _deliver(page, w, fid2)
    expect(page.locator(PROVIDER)).to_have_value(w.other, timeout=10000)
    expect(page.locator(MODEL)).to_have_value("mock-default", timeout=10000)
    _wait_status(page, w, fid2, "filled")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")


def test_a_fill_whose_provider_was_deleted_still_writes_the_model(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _model_world(app_with_data_dir, page)
    gone = seed_mock_provider(w.base, name="doomed", config={"models": ["mock-b"]})
    r = httpx.delete(
        f"{w.base}/api/providers/{gone}", headers=auth_headers_for(w.base), timeout=5.0
    )
    assert r.status_code in (200, 204), r.text
    fid = _seed_b(w, changes={"provider_config_id": gone, "llm_model": "mock-b"})
    _deliver(page, w, fid)
    expect(page.locator(PROVIDER)).to_have_value(gone, timeout=10000)
    expect(page.locator(f"{PROVIDER} option:checked")).to_have_text(f"Unknown provider ({gone})")
    expect(page.locator(MODEL)).to_have_value("mock-b", timeout=10000)
    _wait_status(page, w, fid, "filled")


# ── B4: the operator's edits win ────────────────────────────────────────────


def _done(page: Page) -> None:
    """End the drawer's turn as the client sees it (held receipts land, the turn is not owned)."""
    page.evaluate(_drawer.DELIVER_DRAWER, {"type": "done"})


def _drawer_receipt(page: Page, fid: int):
    return page.locator(f'{_drawer.DRAWER} {RECEIPT}[data-fill-id="{fid}"]')


def test_the_operators_unsaved_prompt_is_kept_and_the_receipt_names_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    page.locator(PROMPT).fill("My unsaved prompt")
    fid = _seed_b(w, changes={"system_prompt": "Fill prompt", "description": "Fill description"})
    _deliver(page, w, fid)
    expect(page.locator(DESC)).to_have_value("Fill description", timeout=10000)
    expect(page.locator(PROMPT)).to_have_value("My unsaved prompt")
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["system_prompt"], "reason": None}
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="system_prompt"]')).to_have_count(0)
    _done(page)
    expect(_drawer_receipt(page, fid).locator('[data-testid="fill-receipt-kept"]')).to_have_text(
        "You had changed System prompt and not saved them, so I left them."
    )
    # The announcement carries the field count and the kept labels, once, in the receipt's words.
    expect(_drawer_receipt(page, fid).locator(ANNOUNCE)).to_have_text(
        "Form partly filled: Change agent “plain”. 2 fields · Not saved. "
        "You had changed System prompt and not saved them, so I left them.",
        timeout=5000,
    )


def test_a_filled_receipt_announces_its_field_count(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    fid = _seed_b(w, changes={"description": "Fill description", "max_iterations": 9})
    _deliver(page, w, fid)
    _wait_status(page, w, fid, "filled")
    _done(page)
    expect(_drawer_receipt(page, fid).locator(ANNOUNCE)).to_have_text(
        "Form filled: Change agent “plain”. 2 fields · Not saved.", timeout=5000
    )


def test_a_toggled_tool_the_operator_changed_is_kept(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    _open_tab(page, "plain", "tools")
    _expand_filesystem(page)
    _tool(page, "grep").uncheck()
    # The fill would turn grep back on (it only disables read_file): the operator's choice wins.
    fid = _seed_b(w, changes={"disabled_tools": ["read_file"]})
    _deliver(page, w, fid)
    expect(_tool(page, "read_file")).not_to_be_checked(timeout=10000)
    expect(_tool(page, "grep")).not_to_be_checked()
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["disabled_tools"], "reason": None}


# ── B5: overlapping fills ───────────────────────────────────────────────────


def test_a_second_fill_over_the_first_one_writes_and_is_filled(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    first = _seed_b(w, changes={"description": "one"})
    _deliver(page, w, first)
    expect(page.locator(DESC)).to_have_value("one", timeout=10000)
    _wait_status(page, w, first, "filled")
    # The text is unsaved (it differs from the baseline) but it is the fill's own, so a second
    # fill replaces it and is filled, not partly filled.
    second = _seed_b(w, changes={"description": "two"}, tool_call_id="tc-2")
    _deliver(page, w, second)
    expect(page.locator(DESC)).to_have_value("two", timeout=10000)
    assert _wait_status(page, w, second, "filled")["outcome"] == {"kept": [], "reason": None}

    # Fill now on a fill that was not filled behaves the same way.
    _done(page)
    third = _seed_b(
        w,
        changes={"description": "three"},
        tool_call_id="tc-3",
        status="not_filled",
        outcome={"kept": [], "reason": "in_chats"},
    )
    page.evaluate(
        _drawer.DELIVER_DRAWER,
        {"type": "fill_requested", "session_id": w.sid, "fill": _view(w, third)},
    )
    _drawer_receipt(page, third).locator(FILL_NOW).click()
    expect(page.locator(DESC)).to_have_value("three", timeout=10000)
    assert _wait_status(page, w, third, "filled")["outcome"] == {"kept": [], "reason": None}
    expect(_drawer_receipt(page, third)).to_have_attribute("data-status", "filled", timeout=8000)

    # Text the operator then typed is theirs: a later fill keeps it.
    page.locator(DESC).fill("mine")
    fourth = _seed_b(w, changes={"description": "four"}, tool_call_id="tc-4")
    page.evaluate(
        _drawer.DELIVER_DRAWER,
        {"type": "fill_requested", "session_id": w.sid, "fill": _view(w, fourth)},
    )
    _drawer_receipt(page, fourth).locator(FILL_NOW).click()
    done = _wait_status(page, w, fourth, "partly_filled")
    assert done["outcome"] == {"kept": ["description"], "reason": None}
    expect(page.locator(DESC)).to_have_value("mine")


# ── B6: the notes ───────────────────────────────────────────────────────────


def _config_changed(agent: str, fields: list[str], pid: int = 1) -> dict:
    return {
        "type": "config_changed",
        "kind": "agent",
        "agent": agent,
        "fields": fields,
        "session_id": "sess-approved",
        "proposal_id": pid,
        "at": "2026-01-02T15:05:00+00:00",
    }


def test_each_filled_control_has_a_note_that_coexists_with_an_approved_change_note(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    # An approved change on the description first.
    r = httpx.put(
        f"{w.base}/api/agents/plain",
        json={**_agent_json(w), "description": "Approved"},
        headers=auth_headers_for(w.base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text
    page.evaluate(_drawer.DELIVER, _config_changed("plain", ["description"]))
    expect(page.locator(f'{APPROVED_NOTE}[data-field="description"]')).to_have_count(
        1, timeout=8000
    )
    expect(page.locator(DESC)).to_have_value("Approved")
    fid = _seed_b(w, changes={"description": "Filled", "max_iterations": 9})
    _deliver(page, w, fid)
    expect(page.locator(DESC)).to_have_value("Filled", timeout=10000)
    note = page.locator(f'{NOTE}[data-field="description"]')
    expect(note).to_have_count(1)
    expect(note).to_contain_text("Filled by GleepGlorp")
    expect(note.locator("svg")).to_have_count(1)
    expect(page.locator(f'{APPROVED_NOTE}[data-field="description"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="max_iterations"]')).to_have_count(1)
    _wait_status(page, w, fid, "filled")


def test_the_notes_go_after_a_patch_a_cancel_a_save_and_when_the_editor_closes(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    for n, how in enumerate(("patch", "cancel", "save", "close")):
        fid = _seed_b(w, changes={"description": f"text {how}"}, tool_call_id=f"tc-{n}")
        _deliver(page, w, fid)
        expect(page.locator(DESC)).to_have_value(f"text {how}", timeout=10000)
        expect(page.locator(NOTE)).to_have_count(1)
        _wait_status(page, w, fid, "filled")
        if how == "patch":
            # An area refresh re-selects the agent: the form is reset, so the notes go with it.
            page.evaluate(
                "() => { const a = App.areas.find(x => x.id === 'studio'); a._dirty = false;"
                " a._refresh(); }"
            )
            expect(page.locator(DESC)).not_to_have_value("text patch", timeout=10000)
        elif how == "cancel":
            page.locator(CANCEL).click()
        elif how == "save":
            page.locator(SAVE).click()
            expect(page.locator(UNSAVED)).to_have_text("", timeout=10000)
        else:
            page.locator('[data-testid="editor-breadcrumb-link"]').click()
            page.locator(_drawer.STAY.replace("cancel", "confirm")).click()
            expect(page.locator(DESC)).to_have_count(0, timeout=8000)
        expect(page.locator(NOTE)).to_have_count(0)
        if how != "close":
            expect(page.locator(UNSAVED)).to_have_text("")


def test_a_note_whose_control_the_operator_then_edited_is_not_redrawn(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    first = _seed_b(w, changes={"description": "filled text"})
    _deliver(page, w, first)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1, timeout=10000)
    _wait_status(page, w, first, "filled")
    page.locator(DESC).fill("my own text")
    second = _seed_b(w, changes={"system_prompt": "filled prompt"}, tool_call_id="tc-2")
    _deliver(page, w, second)
    expect(page.locator(f'{NOTE}[data-field="system_prompt"]')).to_have_count(1, timeout=10000)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(0)
    expect(page.locator(DESC)).to_have_value("my own text")


def _describedby(page: Page, selector: str) -> list[str]:
    value = page.locator(selector).get_attribute("aria-describedby") or ""
    return value.split()


def test_a_filled_control_is_described_by_its_note_and_loses_it_when_the_note_goes(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    # An id the control already had is kept beside the note's, then still there afterwards.
    page.evaluate(
        "(sel) => document.querySelector(sel).setAttribute('aria-describedby', 'existing-hint')",
        DESC,
    )
    first = _seed_b(w, changes={"description": "filled text"})
    _deliver(page, w, first)
    note = page.locator(f'{NOTE}[data-field="description"]')
    expect(note).to_have_count(1, timeout=10000)
    note_id = note.get_attribute("id")
    assert note_id
    assert _describedby(page, DESC) == ["existing-hint", note_id]
    _wait_status(page, w, first, "filled")
    # The operator edits the field; the next fill's redraw drops the note and only its id.
    page.locator(DESC).fill("my own text")
    second = _seed_b(w, changes={"system_prompt": "filled prompt"}, tool_call_id="tc-2")
    _deliver(page, w, second)
    expect(page.locator(f'{NOTE}[data-field="system_prompt"]')).to_have_count(1, timeout=10000)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(0)
    assert _describedby(page, DESC) == ["existing-hint"]
    prompt_note = page.locator(f'{NOTE}[data-field="system_prompt"]').get_attribute("id")
    assert prompt_note and prompt_note != note_id
    assert _describedby(page, PROMPT) == [prompt_note]
    _wait_status(page, w, second, "filled")
    page.locator(CANCEL).click()
    expect(page.locator(NOTE)).to_have_count(0)
    assert _describedby(page, PROMPT) == []


def test_a_filled_tab_item_toggle_is_described_by_its_note(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    kb = seed_knowledge_base(w.base, "Docs")
    mcp = seed_mcp_source(w.base, "Search", ["lookup"])
    fid = _seed_b(
        w, changes={"enabled_tools": ["read_file", "grep"], "mcp_source_ids": [mcp], "kb_ids": [kb]}
    )
    _deliver(page, w, fid)
    _wait_status(page, w, fid, "filled")
    _open_tab(page, "plain", "tools")
    # A tool the fill switched off carries a note; its own checkbox is what it describes.
    tool_notes = page.locator(f'{NOTE}[data-field="tools"]')
    expect(tool_notes.first).to_be_attached()
    tool = tool_notes.first.get_attribute("data-item")
    assert tool
    pairs = [
        (_tool(page, tool), "tools", tool),
        (page.locator(f'[data-testid="mcp-source-toggle-{mcp}"]'), "mcp_source_ids", mcp),
    ]
    for control, group, item in pairs:
        note = page.locator(f'{NOTE}[data-field="{group}"][data-item="{item}"]')
        expect(note).to_have_count(1)
        assert note.get_attribute("id") in (control.get_attribute("aria-describedby") or "").split()
    _open_tab(page, "plain", "knowledge")
    note = page.locator(f'{NOTE}[data-field="kb_ids"][data-item="{kb}"]')
    expect(note).to_have_count(1)
    toggle = page.locator(f'[data-testid="agent-knowledge-toggle-{kb}"]')
    note_id = note.get_attribute("id")
    before = (toggle.get_attribute("aria-describedby") or "").split()
    assert note_id in before
    _open_tab(page, "plain", "general")
    page.locator(CANCEL).click()
    expect(page.locator(NOTE)).to_have_count(0)
    # Only the note's id goes; the toggle's own description stays.
    after = (toggle.get_attribute("aria-describedby") or "").split()
    assert after == [i for i in before if i != note_id] and after


# ── B7: who applies ─────────────────────────────────────────────────────────


def _claims(page: Page) -> list[str]:
    """Record the fill requests a page makes (kept in a list the test reads)."""
    seen: list[str] = []
    page.on(
        "request",
        lambda r: (
            seen.append(r.url.split("/api/gleepglorp/fills/")[1])
            if "/api/gleepglorp/fills/" in r.url
            else None
        ),
    )
    return seen


def test_only_the_window_that_owns_the_turn_applies_a_fill(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    fid = _seed_b(w, changes={"description": "Shared"})

    # A second page in the same context joins the drawer's conversation (the stored id) and a
    # third opens the same chat in Chats: both draw the receipt and neither claims.
    drawer2 = page.context.new_page()
    seen2 = _claims(drawer2)
    drawer2.add_init_script(_drawer.RECORD)
    _nav.goto(drawer2, w.base, "library")
    _drawer.wait_socket(drawer2)
    _drawer.open_drawer(drawer2)
    expect(_drawer.drawer_msgs(drawer2, "user").last).to_contain_text(
        "please fill the form", timeout=10000
    )
    chats = page.context.new_page()
    seen3 = _claims(chats)
    _open(chats, w)
    drawer2.evaluate(
        _drawer.DELIVER_DRAWER,
        {"type": "fill_requested", "session_id": w.sid, "fill": _view(w, fid)},
    )
    _chats.emit_frame(chats, {"type": "fill_requested", "session_id": w.sid, "fill": _view(w, fid)})
    drawer2.evaluate(_drawer.DELIVER_DRAWER, {"type": "done"})
    _chats.emit_frame(chats, {"type": "done"})
    expect(drawer2.locator(f'{_drawer.DRAWER} {RECEIPT}[data-fill-id="{fid}"]')).to_have_count(1)
    expect(chats.locator(f'{RECEIPT}[data-fill-id="{fid}"]')).to_have_count(1)
    expect(chats.locator(f"{RECEIPT} button")).to_have_count(0)
    page.wait_for_timeout(800)
    assert seen2 == [] and seen3 == []
    assert _view(w, fid)["status"] == "sent"
    chats.close()
    drawer2.close()


def test_a_fill_delivered_after_done_is_not_applied(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    seen = _claims(page)
    _done(page)
    fid = _seed_b(w, changes={"description": "Too late"})
    _deliver(page, w, fid)
    page.wait_for_timeout(1000)
    assert seen == []
    assert _view(w, fid)["status"] == "sent"
    # Its receipt offers Fill now (a sent fill this window is not applying).
    expect(_drawer_receipt(page, fid).locator(FILL_NOW)).to_have_count(1)


def test_fills_delivered_together_apply_in_id_order_one_at_a_time(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    seen = _claims(page)
    a = _seed_b(w, changes={"description": "from A"}, tool_call_id="tc-a")
    b = _seed_b(w, changes={"system_prompt": "from B"}, tool_call_id="tc-b")
    _deliver(page, w, b, a)  # delivered newest first, in one task
    expect(page.locator(DESC)).to_have_value("from A", timeout=10000)
    expect(page.locator(PROMPT)).to_have_value("from B", timeout=10000)
    _wait_status(page, w, b, "filled")
    assert seen == [f"{a}/claim", f"{a}/outcome", f"{b}/claim", f"{b}/outcome"]


# ── B8: not filled ──────────────────────────────────────────────────────────


def _reason(page: Page, fid: int):
    return _drawer_receipt(page, fid).locator('[data-testid="fill-receipt-reason"]')


def test_a_fill_that_arrives_in_chats_is_not_filled_and_fill_now_applies_it_on_agents(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    _nav.open_destination(page, "chats")
    page.wait_for_function("() => App.router.current().destination === 'chats'")
    fid = _seed_b(w, changes={"description": "Later"})
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "in_chats"}
    assert _nav.current_route(page).startswith("chats")
    # [B9] On Agents the drawer's receipt offers Fill now, which claims and applies.
    _nav.open_destination(page, "agents")
    _drawer.open_drawer(page)
    _done(page)
    expect(_reason(page, fid)).to_have_text("You were in Chats when it arrived.")
    _drawer_receipt(page, fid).locator(FILL_NOW).click()
    _nav.wait_for_route_prefix(page, "agents/plain")
    expect(page.locator(DESC)).to_have_value("Later", timeout=10000)
    _wait_status(page, w, fid, "filled")
    expect(_drawer_receipt(page, fid)).to_have_attribute("data-status", "filled", timeout=8000)
    expect(
        _drawer_receipt(page, fid).locator('[data-testid="fill-receipt-headline"]')
    ).to_have_text("Form filled")


def _dirty_other_agent(w: SimpleNamespace, page: Page) -> None:
    _open_agent_page(page, "other")
    page.locator(DESC).fill("typed by me")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")


def test_a_dirty_editor_and_stay_means_stay_nothing_written_and_focus_back_in_the_drawer(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents")
    _dirty_other_agent(w, page)
    fid = _seed_b(w, changes={"description": "Never written"})
    _deliver(page, w, fid)
    # The leave guard asks once; Stay is chosen.
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    expect(page.locator(DESC)).to_have_value("typed by me")
    expect(page.locator(COMPOSER)).to_be_focused()
    _done(page)
    expect(_reason(page, fid)).to_have_text("You chose to stay on the page you were editing.")


def test_a_leave_guard_dialog_already_open_means_the_fill_does_not_navigate(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents")
    _dirty_other_agent(w, page)
    page.locator('[data-testid="rail-library"]').click()
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    fid = _seed_b(w, changes={"description": "Never written"})
    _deliver(page, w, fid)
    assert _wait_status(page, w, fid, "not_filled")["outcome"]["reason"] == "stay"
    # Still exactly the one dialog the operator opened; nothing navigated.
    expect(page.locator(_drawer.STAY)).to_have_count(1)
    page.locator(_drawer.STAY).click()
    assert _nav.current_route(page).startswith("agents/other")


def test_a_fill_for_an_agent_that_no_longer_exists_is_target_gone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    route = _nav.current_route(page)
    fid = _seed_b(w, agent_name="ghost", changes={"description": "Nobody home"})
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "target_gone"}
    assert _nav.current_route(page) == route
    _done(page)
    expect(_reason(page, fid)).to_have_text("That agent no longer exists.")
    expect(_drawer_receipt(page, fid).locator(FILL_NOW)).to_have_count(0)


def test_a_settle_timeout_and_an_unavailable_mcp_id_are_editor_unavailable_with_nothing_written(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    # The dev-mode seam forces the settle timeout.
    page.evaluate("() => { window.__ggFillSettleTimeoutMs = 0; }")
    fid = _seed_b(w, changes={"description": "Timed out"})
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "editor_unavailable"}
    page.evaluate("() => { delete window.__ggFillSettleTimeoutMs; }")
    page.wait_for_timeout(800)
    expect(page.locator(DESC)).to_have_value("")

    # An MCP id the editor does not have: nothing at all is written.
    fid2 = _seed_b(
        w,
        changes={"description": "Not written", "mcp_source_ids": ["no-such-source"]},
        tool_call_id="tc-2",
    )
    _deliver(page, w, fid2)
    done2 = _wait_status(page, w, fid2, "not_filled")
    assert done2["outcome"] == {"kept": [], "reason": "editor_unavailable"}
    expect(page.locator(DESC)).to_have_value("")
    _done(page)
    expect(_reason(page, fid2)).to_have_text("The agent editor could not open.")


# ── B9: Fill now after a reload ─────────────────────────────────────────────


def _stored_chat_world(
    app_with_data_dir: tuple[str, Any], page: Page, route: str = "library"
) -> SimpleNamespace:
    """A finished drawer conversation (a quick reply) the test can reload into."""
    w = _bworld(app_with_data_dir, page, route=route, delay_ms=1200)
    expect(_drawer.drawer_msgs(page, "assistant").last).to_contain_text(
        "Working on it", timeout=15000
    )
    return w


def test_after_a_reload_a_sent_fill_can_be_filled_now_and_names_the_stale_field(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _stored_chat_world(app_with_data_dir, page)
    fid = _seed_b(w, changes={"description": "Reloaded fill"}, base={"description": "old text"})
    page.reload()
    _drawer.wait_socket(page)
    _drawer.open_drawer(page)
    receipt = _drawer_receipt(page, fid)
    expect(receipt).to_have_count(1, timeout=10000)
    expect(receipt.locator('[data-testid="fill-receipt-stale"]')).to_have_text(
        "Changed since GleepGlorp filled it: Description."
    )
    receipt.locator(FILL_NOW).click()
    _nav.wait_for_route_prefix(page, "agents/plain")
    expect(page.locator(DESC)).to_have_value("Reloaded fill", timeout=10000)
    _wait_status(page, w, fid, "filled")
    expect(receipt).to_have_attribute("data-status", "filled", timeout=8000)


def test_fill_now_on_a_fill_another_window_is_applying_says_so(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _stored_chat_world(app_with_data_dir, page)
    now = datetime.now(UTC).isoformat()
    fid = _seed_b(
        w,
        changes={"description": "Elsewhere"},
        status="applying",
        claim_token="someone-else",
        claimed_at=now,
    )
    page.reload()
    _drawer.wait_socket(page)
    _drawer.open_drawer(page)
    receipt = _drawer_receipt(page, fid)
    expect(receipt).to_have_count(1, timeout=10000)
    expect(receipt.locator(FILL_NOW)).to_have_count(0)
    # The client's view says the claim is old (the applying window went away); the server's lease
    # says it is fresh, so the claim is refused.
    old = "2026-01-02T10:00:00+00:00"
    page.evaluate(
        _drawer.DELIVER_DRAWER,
        {"type": "fill_changed", "session_id": w.sid, "fill": {**_view(w, fid), "claimed_at": old}},
    )
    expect(receipt.locator(FILL_NOW)).to_have_count(1)
    receipt.locator(FILL_NOW).click()
    expect(receipt.locator('[data-testid="fill-receipt-notice"]')).to_have_text(
        "Still being applied in another window."
    )
    # The notice is announced too, once per press.
    expect(receipt.locator(ANNOUNCE)).to_have_text(
        "Still being applied in another window.", timeout=5000
    )
    assert _view(w, fid)["status"] == "applying"


def test_a_busy_receipt_marks_busy_on_the_body_never_above_the_status_node(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """WCAG 4.1.3: no ancestor of the receipt's status node is aria-busy while the receipt is
    sent or applying; the busy marker is on the body wrapper."""
    w = _world(app_with_data_dir, messages=encode_messages([]))
    _open(page, w)
    _requested(page, w.sid, _fill_view(7, tool_call_id="t1"))
    _frames(page, _user("fill it"), _chunk("Filling."), *_call("t1"), DONE)
    receipt = _receipt(page, 7)
    busy_ancestors = """() => {
      const s = document.querySelector('[data-testid="fill-receipt-announce"]');
      const out = [];
      for (let n = s; n; n = n.parentElement) {
        if (n.getAttribute('aria-busy') === 'true') out.push(n.className || n.tagName);
      }
      return out;
    }"""
    body = receipt.locator(".chat-proposal-body")
    expect(receipt).to_have_attribute("data-status", "sent")
    expect(body).to_have_attribute("aria-busy", "true")
    assert page.evaluate(busy_ancestors) == []
    _fchanged(page, w.sid, _fill_view(7, status="applying", claimed_at="2026-01-02T10:00:05+00:00"))
    expect(receipt).to_have_attribute("data-status", "applying")
    expect(body).to_have_attribute("aria-busy", "true")
    assert page.evaluate(busy_ancestors) == []
    _fchanged(
        page,
        w.sid,
        _fill_view(
            7,
            status="filled",
            outcome={"kept": [], "reason": None},
            field_count=1,
            resolved_at="2026-01-02T10:00:09+00:00",
        ),
    )
    expect(receipt).to_have_attribute("data-status", "filled")
    expect(body).not_to_have_attribute("aria-busy", "true")


# ── B10: focus never moves ──────────────────────────────────────────────────


def _create_fill(w: SimpleNamespace, **extra: Any) -> int:
    return _seed_b(
        w,
        action="create",
        agent_name="made-by-fill",
        changes={"name": "made-by-fill", "description": "Created", **extra},
    )


def test_a_create_fill_keeps_focus_in_the_drawer_and_the_next_new_agent_focuses_the_name(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    page.locator(COMPOSER).focus()
    fid = _create_fill(w)
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("made-by-fill", timeout=10000)
    _wait_status(page, w, fid, "filled")
    page.wait_for_timeout(400)
    expect(page.locator(COMPOSER)).to_be_focused()
    # The next ordinary New agent focuses the name field (the suppression did not leak).
    page.locator(CANCEL).click()
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(NAME)).to_be_focused(timeout=8000)


def test_a_create_fill_that_stayed_does_not_leak_the_suppression_to_the_next_new_agent(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents")
    _dirty_other_agent(w, page)
    fid = _create_fill(w)
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    assert _wait_status(page, w, fid, "not_filled")["outcome"]["reason"] == "stay"
    page.locator(CANCEL).click()
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(NAME)).to_be_focused(timeout=8000)


def test_a_change_fill_leaves_focus_where_it_was(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    page.locator(COMPOSER).focus()
    fid = _seed_b(w, changes={"description": "Quietly"})
    _deliver(page, w, fid)
    expect(page.locator(DESC)).to_have_value("Quietly", timeout=10000)
    _wait_status(page, w, fid, "filled")
    page.wait_for_timeout(400)
    expect(page.locator(COMPOSER)).to_be_focused()


# ── B11: the client allowlist ───────────────────────────────────────────────


def test_keys_outside_the_allowlist_are_ignored_with_one_console_warning(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page, route="agents/plain/general")
    _editor_ready(page)
    warnings: list[str] = []
    page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
    before = _agent_json(w)
    fid = _seed_b(
        w,
        changes={
            "description": "Allowed",
            "secret_ids": ["s1"],
            "tool_overrides": {"read_file": {"x": 1}},
            "notes_enabled": True,
        },
    )
    _deliver(page, w, fid)
    expect(page.locator(DESC)).to_have_value("Allowed", timeout=10000)
    assert _wait_status(page, w, fid, "filled")["outcome"] == {"kept": [], "reason": None}
    ignored = [m for m in warnings if "outside the allowlist" in m]
    assert len(ignored) == 1
    for key in ("secret_ids", "tool_overrides", "notes_enabled"):
        assert key in ignored[0]
    # Saving what the editor holds changes only what the editor can: the unwritten keys keep
    # their stored values.
    page.locator(SAVE).click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=10000)
    after = _agent_json(w)
    assert after["description"] == "Allowed"
    for key in ("secret_ids", "tool_overrides", "notes_enabled"):
        assert after.get(key) == before.get(key)

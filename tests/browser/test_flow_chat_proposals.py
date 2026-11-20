"""The GleepGlorp proposal card in Chats (M36 F2 L6, flight DD6-DD8; the approved board's option A
card, states 1-7, and option B's quiet line).

Proposals are seeded straight into the database (no route creates one: only GleepGlorp's
``propose_change`` tool does) in a stored GleepGlorp chat whose history holds the proposing tool
calls, so the join's ``proposals_snapshot`` draws them; the Leg 4 routes run for real. Live order
and the turn-ending paths are scripted with ``_chats.emit_frame``. Covers, as state transitions:

* every state renders with its testids and tone (waiting, applied, dismissed, failed, withdrawn
  twice), the create and change tables, and the rule and routine titles;
* live order (work group, reply, card), a card made during a turn that ends by Stop or the step
  limit, and a reload through the snapshot;
* Approve (the real route) folding the card, the approval turn's quiet line and busy buttons, live
  and after a reload, and a repeated frame leaving one card;
* a stale proposal (panel, Approve anyway), a failed one (error, Try again, Dismiss), a withdrawn
  one (agent deleted), the refused-click lines, and focus after each action.

Falls in the ``chats-transcript`` browser lane (an explicit entry in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import (
    canonical_schedule,
    seed_gleepglorp_proposal,
    seed_mock_agent,
    seed_mock_provider,
    seed_session,
)
from browser.test_flow_chat_turn_work import (
    DONE,
    TOOL_CALL,
    TOOL_RESULT,
    _chunk,
    _frames,
    _Script,
    _user,
)
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message, ToolCall, ToolResult

pytestmark = pytest.mark.browser

CARD = '[data-testid="proposal-card"]'
INPUT = '[data-testid="chat-input"]'
APPROVAL_LINE = '[data-testid="chat-approval-line"]'
WAIT = "Wait for GleepGlorp to finish."

# Group, reply, card and quiet line, as direct children of the log, in DOM order.
_ORDER_JS = """() => Array.from(document.querySelectorAll(
  '.area-chat .messages > [data-testid="turn-work"],'
  + ' .area-chat .messages > .ui-message--assistant,'
  + ' .area-chat .messages > .ui-message--user,'
  + ' .area-chat .messages > [data-testid="proposal-card"],'
  + ' .area-chat .messages > [data-testid="chat-approval-line"]'
)).map(e => e.getAttribute('data-testid') === 'turn-work' ? 'work'
  : e.getAttribute('data-testid') === 'proposal-card' ? 'card:' + e.dataset.proposalId
  : e.getAttribute('data-testid') === 'chat-approval-line' ? 'approved'
  : e.classList.contains('ui-message--user') ? 'user' : 'reply')"""


def _put_settings(base: str, provider_id: str) -> None:
    body = {
        "enabled": True,
        "provider_config_id": provider_id,
        "model": "mock-default",
        "web_access": True,
        "memory": True,
        "retention_days": 30,
    }
    r = httpx.put(f"{base}/api/gleepglorp", json=body, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text


def _history(tool_ids: tuple[str, ...], reply: str = "Review the card.") -> str:
    calls = [
        ToolCall(id=t, name="propose_change", arguments={"kind": "agent", "action": "change"})
        for t in tool_ids
    ]
    msgs = [
        Message.user("Please change my agent."),
        Message.assistant("Let me propose that.", tool_calls=calls),
        *[
            Message.tool(ToolResult(tool_call_id=t, content="Proposed.", is_error=False))
            for t in tool_ids
        ],
        Message.assistant(reply),
    ]
    return encode_messages(msgs)


def _world(
    app_with_data_dir: tuple[str, Any],
    *,
    tool_ids: tuple[str, ...] = ("tc-1",),
    provider_config: dict | None = None,
    messages: str | None = None,
) -> SimpleNamespace:
    """A ready GleepGlorp, an agent named ``plain`` and a stored GleepGlorp chat."""
    base, data = app_with_data_dir
    provider = seed_mock_provider(base, config=provider_config)
    seed_mock_agent(base, provider, "plain")
    _put_settings(base, provider)
    sid = seed_session(
        base,
        "GleepGlorp",
        "Proposal chat",
        "2026-01-02T00:00:00Z",
        messages=messages if messages is not None else _history(tool_ids),
    )
    return SimpleNamespace(base=base, data=data, sid=sid, provider=provider)


def _open(page: Page, w: SimpleNamespace) -> None:
    page.goto(w.base)
    _chats.open_chat(page, w.sid)


def _seed(w: SimpleNamespace, **kw: Any) -> int:
    return seed_gleepglorp_proposal(w.data, w.sid, agent_name=kw.pop("agent_name", "plain"), **kw)


def _card(page: Page, pid: int):
    return page.locator(f'{CARD}[data-proposal-id="{pid}"]')


def _in(card, testid: str):
    return card.locator(f'[data-testid="{testid}"]')


def _agent(w: SimpleNamespace, name: str = "plain") -> dict:
    r = httpx.get(f"{w.base}/api/agents/{name}", headers=auth_headers_for(w.base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _view(pid: int, sid: str, **over: Any) -> dict:
    return {
        "id": pid,
        "kind": "agent",
        "action": "change",
        "agent_name": "plain",
        "target_id": None,
        "status": "pending",
        "result": None,
        "untrusted": False,
        "untrusted_sources": [],
        "created_at": "2026-01-02T10:00:00+00:00",
        "resolved_at": None,
        "tool_call_id": "t1",
        "changes": {"description": "Live words"},
        "base": {"description": ""},
        "labels": {"description": "Description"},
        "title": "Change agent “plain”",
        "target_gone": False,
        **over,
    }


def _changed(page: Page, sid: str, view: dict) -> None:
    _chats.emit_frame(page, {"type": "proposal_changed", "session_id": sid, "proposal": view})


def _call(tool_call_id: str) -> tuple[dict, dict]:
    """A propose_change call and its result frame with its own tool call id."""
    return (
        {**TOOL_CALL, "name": "propose_change", "tool_call_id": tool_call_id},
        {**TOOL_RESULT, "tool_call_id": tool_call_id},
    )


def _order(page: Page) -> list[str]:
    return page.evaluate(_ORDER_JS)


def _rules_create(w: SimpleNamespace, text: str) -> str:
    r = httpx.post(
        f"{w.base}/api/agents/plain/rules",
        json={"text": text},
        headers=auth_headers_for(w.base),
        timeout=5.0,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ── Every state ────────────────────────────────────────────────────────────


def test_every_state_renders_with_its_testids_and_tone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, tool_ids=tuple(f"tc-{i}" for i in range(1, 10)))
    rule_id = _rules_create(w, "Be brief.")
    waiting = _seed(
        w,
        tool_call_id="tc-1",
        changes={"description": "A new description for plain", "llm_model": "claude-x"},
        base={"description": "", "llm_model": "mock-default"},
        untrusted=True,
        sources=["web_fetch"],
    )
    applied = _seed(
        w,
        tool_call_id="tc-2",
        status="applied",
        changes={"description": "Applied words"},
        base={"description": ""},
        result={"summary": "Changed Description on plain", "agent": "plain"},
        resolved_at="2026-01-02T10:05:00+00:00",
    )
    dismissed = _seed(
        w,
        tool_call_id="tc-3",
        status="dismissed",
        changes={"description": "Dismissed words"},
        base={"description": ""},
        resolved_at="2026-01-02T10:06:00+00:00",
    )
    failed = _seed(
        w,
        tool_call_id="tc-4",
        status="failed",
        action="create",
        agent_name="Taken",
        changes={"name": "Taken", "description": "Made"},
        result={"errors": [{"loc": ["name"], "msg": "An agent named Taken already exists."}]},
        resolved_at="2026-01-02T10:07:00+00:00",
    )
    replaced = _seed(
        w,
        tool_call_id="tc-5",
        status="withdrawn",
        changes={"description": "Old"},
        base={"description": ""},
        result={"reason": "replaced", "by": 9},
        resolved_at="2026-01-02T10:08:00+00:00",
    )
    gone = _seed(
        w,
        tool_call_id="tc-6",
        agent_name="ghost",
        changes={"description": "For no one"},
        base={"description": ""},
    )
    routine = _seed(
        w,
        tool_call_id="tc-7",
        kind="routine",
        action="create",
        changes={
            "name": "Morning digest",
            "prompt": "Summarise the news.",
            "schedule": canonical_schedule("09:00", date="2099-01-01"),
            "anchor_at": None,
        },
    )
    rule = _seed(
        w,
        tool_call_id="tc-8",
        kind="rule",
        action="change",
        target_id=rule_id,
        changes={"text": "Be very brief."},
        base={"text": "Be brief."},
    )
    rule_new = _seed(
        w, tool_call_id="tc-9", kind="rule", action="create", changes={"text": "Always cite."}
    )
    _open(page, w)
    expect(page.locator(CARD)).to_have_count(9)

    # [waiting] the eyebrow, the flag and its hint, the title, a two-column table, the footer.
    c = _card(page, waiting)
    assert c.get_attribute("data-state") == "pending"
    assert c.get_attribute("aria-label") == "Proposed change: Change agent “plain”"
    expect(_in(c, "proposal-title")).to_have_text("Change agent “plain”")
    expect(c.locator("h3")).to_have_count(1)
    expect(_in(c, "proposal-flag")).to_have_count(1)
    expect(_in(c, "proposal-source-hint")).to_have_text(
        "Proposed after GleepGlorp read content not from you: web_fetch. "
        "Read every field before you approve."
    )
    table = _in(c, "proposal-table")
    expect(table.locator("thead th")).to_have_text(["Field", "Now", "Proposed"])
    expect(table.locator("tbody th")).to_have_text(["Description", "Model"])
    expect(table.locator("tbody tr").nth(0).locator("td")).to_have_text(
        ["None", "A new description for plain"]
    )
    expect(c).to_contain_text("Only these 2 fields change.")
    expect(_in(c, "proposal-approve")).to_be_enabled()
    expect(_in(c, "proposal-dismiss")).to_be_enabled()
    expect(c.locator(".banner-warning, .banner-error, [data-testid=proposal-error]")).to_have_count(
        0
    )

    # [applied] one folded line: Applied, the summary, Open agent, Details (the table inside).
    c = _card(page, applied)
    assert c.get_attribute("data-state") == "applied"
    line = _in(c, "proposal-status-line")
    expect(line).to_contain_text("Applied")
    expect(line).to_contain_text("Changed Description on plain")
    expect(_in(c, "proposal-open-agent")).to_have_attribute("href", _nav.href("agents/plain"))
    expect(_in(c, "proposal-approve")).to_have_count(0)
    details = _in(c, "proposal-details")
    expect(details.locator("[data-testid=proposal-table]")).to_be_hidden()
    details.locator("summary").click()
    expect(details.locator("[data-testid=proposal-table]")).to_be_visible()

    # [dismissed] a quiet line with Details, no buttons.
    c = _card(page, dismissed)
    assert c.get_attribute("data-state") == "dismissed"
    expect(_in(c, "proposal-status-line")).to_contain_text("Dismissed · Change agent “plain”")
    expect(_in(c, "proposal-details")).to_have_count(1)
    expect(c.locator("button:not(summary)")).to_have_count(0)

    # [failed] stays open: a danger status with the field label, Try again and Dismiss.
    c = _card(page, failed)
    assert c.get_attribute("data-state") == "failed"
    err = _in(c, "proposal-error")
    expect(err).to_have_text(
        "Couldn't apply this change. Name: An agent named Taken already exists."
    )
    assert err.get_attribute("role") == "alert" and err.get_attribute("data-state") == "danger"
    expect(_in(c, "proposal-title")).to_have_text("Create agent “Taken”")
    expect(_in(c, "proposal-try-again")).to_be_enabled()
    expect(_in(c, "proposal-dismiss")).to_be_enabled()
    expect(_in(c, "proposal-approve")).to_have_count(0)
    expect(_in(c, "proposal-table").locator("thead")).to_have_count(0)  # a create: one column
    expect(c).to_contain_text("Other settings keep their defaults.")

    # [withdrawn] replaced, and a target that no longer exists: a quiet line, no buttons.
    c = _card(page, replaced)
    assert c.get_attribute("data-state") == "withdrawn"
    expect(_in(c, "proposal-status-line")).to_have_text(
        "Withdrawn · Change agent “plain”: replaced by the proposal below."
    )
    c = _card(page, gone)
    assert c.get_attribute("data-state") == "withdrawn"
    expect(_in(c, "proposal-status-line")).to_have_text(
        "Withdrawn · Change agent “ghost”: the agent no longer exists."
    )
    expect(c.locator("button")).to_have_count(0)
    expect(_in(c, "proposal-open-agent")).to_have_count(0)

    # [routine create] the server's schedule sentence and next runs in the table.
    c = _card(page, routine)
    expect(_in(c, "proposal-title")).to_have_text("Schedule a routine for “plain”")
    expect(_in(c, "proposal-table").locator("tbody th")).to_have_text(
        ["Name", "Prompt", "Schedule"]
    )
    expect(_in(c, "proposal-table")).to_contain_text("Next:")
    # [rule change and create] the titles.
    c = _card(page, rule)
    expect(_in(c, "proposal-title")).to_have_text("Change rule 1 of “plain”")
    expect(_in(c, "proposal-table").locator("tbody tr").first.locator("td")).to_have_text(
        ["Be brief.", "Be very brief."]
    )
    expect(_in(_card(page, rule_new), "proposal-title")).to_have_text("Add a rule to “plain”")

    # Warning appears only with the flag, danger only on the failed card.
    assert page.locator(f"{CARD} .banner-warning").count() == 0
    assert page.locator(f"{CARD} [data-state=danger]").count() == 1
    # In id order after the reply, nothing else in the log between them.
    assert _order(page) == ["user", "work", "reply"] + [
        f"card:{i}"
        for i in (waiting, applied, dismissed, failed, replaced, gone, routine, rule, rule_new)
    ]


def test_a_long_value_is_clamped_in_the_card(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    prompt = "Use the GitHub server. " * 30
    pid = _seed(w, changes={"system_prompt": prompt}, base={"system_prompt": "Short."})
    _open(page, w)
    c = _card(page, pid)
    more = _in(c, "proposal-table-more-proposed")
    expect(more).to_have_count(1)
    expect(_in(c, "proposal-table-more-now")).to_have_count(0)
    expect(more).to_have_accessible_name("Show all System prompt (proposed)")
    assert prompt not in c.inner_text()
    more.click()
    expect(more).to_have_attribute("aria-expanded", "true")
    assert prompt.strip() in c.inner_text().replace("\n", " ")


# ── Placement ──────────────────────────────────────────────────────────────


def test_live_order_is_group_reply_card_and_a_stopped_turn_still_shows_its_card(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, messages=encode_messages([]))
    _open(page, w)
    expect(page.locator(CARD)).to_have_count(0)

    # [working] the card is held while the turn runs.
    _frames(page, _user("go"), _chunk("Let me propose."), TOOL_CALL, TOOL_RESULT)
    _changed(page, w.sid, _view(11, w.sid))
    page.wait_for_timeout(200)
    expect(page.locator(CARD)).to_have_count(0)
    # [working] -> [done]: group, reply, card.
    _frames(page, _chunk("Please review."), DONE)
    expect(_card(page, 11)).to_have_count(1)
    assert _order(page) == ["user", "work", "reply", "card:11"]
    # The card is idle once the turn is over: its buttons work.
    expect(_in(_card(page, 11), "proposal-approve")).to_be_enabled()

    # [working] -> [stopped]: no reply bubble, and the card still shows (after the group).
    _frames(page, _user("again"), _chunk("Trying."), *_call("t2"))
    _changed(page, w.sid, _view(12, w.sid, tool_call_id="t2", changes={"description": "Second"}))
    _frames(page, {"type": "cancelled"})
    expect(_card(page, 12)).to_have_count(1)
    assert _order(page) == ["user", "work", "reply", "card:11", "user", "work", "card:12"]

    # [working] -> [step limit]: the card shows after the notice.
    _frames(page, _user("third"), _chunk("Trying."), *_call("t3"))
    _changed(page, w.sid, _view(13, w.sid, tool_call_id="t3", changes={"description": "Third"}))
    _frames(page, {"type": "step_limit", "steps": 3}, DONE)
    expect(_card(page, 13)).to_have_count(1)
    assert _order(page)[-2:] == ["work", "card:13"]
    expect(page.locator('[data-testid="chat-step-limit"]')).to_have_count(1)


def test_a_status_change_updates_the_card_in_place(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    _open(page, w)
    expect(_card(page, pid)).to_have_attribute("data-state", "pending")
    page.evaluate(
        "() => { window.__card = document.querySelector('[data-testid=\"proposal-card\"]'); }"
    )
    _changed(
        page,
        w.sid,
        _view(
            pid,
            w.sid,
            tool_call_id="tc-1",
            status="dismissed",
            resolved_at="2026-01-02T10:09:00+00:00",
            changes={"description": "Words"},
        ),
    )
    expect(_card(page, pid)).to_have_attribute("data-state", "dismissed")
    # The same element: it was updated, not moved or replaced.
    assert page.evaluate(
        "() => document.querySelector('[data-testid=\"proposal-card\"]') === window.__card"
    )
    # A frame for another chat changes nothing.
    _chats.emit_frame(
        page,
        {
            "type": "proposal_changed",
            "session_id": "other",
            "proposal": _view(pid, "other", status="applied"),
        },
    )
    page.wait_for_timeout(150)
    expect(_card(page, pid)).to_have_attribute("data-state", "dismissed")


def test_a_reload_redraws_the_cards_in_place_through_the_snapshot(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    _open(page, w)
    expect(_card(page, pid)).to_have_count(1)
    assert _order(page) == ["user", "work", "reply", f"card:{pid}"]
    page.reload()
    _chats.open_chat(page, w.sid)
    expect(_card(page, pid)).to_have_count(1)
    assert _order(page) == ["user", "work", "reply", f"card:{pid}"]
    # Switching away and back (a re-join) draws it once, not twice.
    page.evaluate("() => window.App.areas.find(a => a.id === 'chat')._joinSession('nope')")
    _chats.open_chat(page, w.sid)
    expect(page.locator(CARD)).to_have_count(1)


# ── Approve: the real route, the quiet line, busy ──────────────────────────


def test_approve_folds_the_card_and_the_approval_turn_shows_the_quiet_line(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(
        app_with_data_dir,
        tool_ids=("tc-1", "tc-2"),
        provider_config={"delay_ms": 1200, "response": {"content": "All set."}},
    )
    first = _seed(
        w, tool_call_id="tc-1", changes={"description": "Approved words"}, base={"description": ""}
    )
    second = _seed(
        w, tool_call_id="tc-2", changes={"max_iterations": 7}, base={"max_iterations": 20}
    )
    _open(page, w)
    expect(page.locator(CARD)).to_have_count(2)

    # [waiting] -> [applying/applied]: the route runs for real and the card folds.
    approve = _in(_card(page, first), "proposal-approve")
    approve.focus()
    page.keyboard.press("Enter")
    c = _card(page, first)
    expect(c).to_have_attribute("data-state", "applied", timeout=8000)
    expect(_in(c, "proposal-status-line")).to_contain_text("Changed Description on plain")
    assert _agent(w)["description"] == "Approved words"
    # Focus lands on the folded line's Open agent link.
    expect(_in(c, "proposal-open-agent")).to_be_focused()

    # The approval turn: the quiet line, never a bubble, and the other card's buttons are busy.
    expect(page.locator(APPROVAL_LINE)).to_have_text(
        "You approved this change. GleepGlorp is continuing."
    )
    other = _card(page, second)
    expect(_in(other, "proposal-approve")).to_be_disabled()
    expect(_in(other, "proposal-dismiss")).to_be_disabled()
    expect(_in(other, "proposal-approve")).to_have_attribute("title", WAIT)
    expect(other).to_contain_text(WAIT)
    for bubble in _chats.messages(page, "user").all():
        assert "Approved proposal" not in bubble.inner_text()
    # [busy] -> [idle]: the reply lands and the other card is released.
    expect(_chats.replies(page).last).to_have_text("All set.", timeout=8000)
    expect(_in(other, "proposal-approve")).to_be_enabled(timeout=8000)
    # Both cards stay with the turn that made them; the approval line begins the next turn.
    assert _order(page) == [
        "user",
        "work",
        "reply",
        f"card:{first}",
        f"card:{second}",
        "approved",
        "reply",
    ]

    # After a reload the same line replaces the stored message, and the cards are in place.
    page.reload()
    _chats.open_chat(page, w.sid)
    expect(page.locator(APPROVAL_LINE)).to_have_count(1)
    expect(page.locator(APPROVAL_LINE)).to_have_text(
        "You approved this change. GleepGlorp is continuing."
    )
    for bubble in _chats.messages(page, "user").all():
        assert "Approved proposal" not in bubble.inner_text()
    expect(_card(page, first)).to_have_attribute("data-state", "applied")
    expect(_card(page, second)).to_have_attribute("data-state", "pending")


def test_a_repeated_frame_for_the_same_status_leaves_one_card(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, provider_config={"response": {"content": "Done."}})
    pid = _seed(w, changes={"description": "Once"}, base={"description": ""})
    _open(page, w)
    _in(_card(page, pid), "proposal-approve").click()
    expect(_card(page, pid)).to_have_attribute("data-state", "applied", timeout=8000)
    r = httpx.get(
        f"{w.base}/api/gleepglorp/proposals",
        params={"session_id": w.sid},
        headers=auth_headers_for(w.base),
        timeout=5.0,
    )
    view = r.json()["proposals"][0]
    assert view["status"] == "applied" and view["resolved_at"]
    page.evaluate(
        "() => { window.__card = document.querySelector('[data-testid=\"proposal-card\"]'); }"
    )
    _chats.emit_frame(page, {"type": "proposal_changed", "session_id": w.sid, "proposal": view})
    page.wait_for_timeout(200)
    expect(page.locator(CARD)).to_have_count(1)
    assert page.evaluate(
        "() => document.querySelector('[data-testid=\"proposal-card\"]') === window.__card"
    )


def test_scripted_approval_marks_busy_and_the_other_marks_draw_the_right_lines(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """Leg 5's client tweak: an ``approved`` user frame marks the chat busy (the cards' buttons
    go disabled with the hint) and draws the line instead of a bubble; ``approved_no_turn`` is
    not busy; ``dismissed`` draws nothing."""
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    _open(page, w)
    approve = _in(_card(page, pid), "proposal-approve")
    expect(approve).to_be_enabled()

    _frames(
        page,
        {
            "type": "user",
            "content": "Approved proposal 1: x.",
            "proposal_id": 1,
            "proposal_event": "approved",
            "session_id": w.sid,
        },
    )
    expect(page.locator(APPROVAL_LINE)).to_have_text(
        "You approved this change. GleepGlorp is continuing."
    )
    assert _chats.messages(page, "user").count() == 1  # only the stored first message
    expect(approve).to_be_disabled()
    expect(_in(_card(page, pid), "proposal-dismiss")).to_have_attribute("title", WAIT)
    expect(page.locator('[data-testid="chat-stop-btn"]')).to_be_visible()
    _frames(page, DONE)
    expect(approve).to_be_enabled()

    _frames(
        page,
        {
            "type": "user",
            "content": "Approved proposal 2: y.",
            "proposal_id": 2,
            "proposal_event": "approved_no_turn",
            "session_id": w.sid,
        },
    )
    expect(page.locator(APPROVAL_LINE)).to_have_count(2)
    expect(page.locator(APPROVAL_LINE).last).to_have_text("You approved this change.")
    expect(approve).to_be_enabled()
    expect(page.locator('[data-testid="chat-stop-btn"]')).to_be_hidden()

    _frames(
        page,
        {
            "type": "user",
            "content": "Dismissed proposal 3 (x). Do not apply it.",
            "proposal_id": 3,
            "proposal_event": "dismissed",
            "session_id": w.sid,
        },
    )
    page.wait_for_timeout(150)
    expect(page.locator(APPROVAL_LINE)).to_have_count(2)
    assert _chats.messages(page, "user").count() == 1


def test_stored_approval_dismissal_and_no_turn_marks_replay_as_lines_and_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """A reload renders the three marks (and an empty turn for a dismissal) without a bubble."""
    marked = [
        Message.user("Please change my agent."),
        Message.assistant(
            "Proposing.", tool_calls=[ToolCall(id="tc-1", name="propose_change", arguments={})]
        ),
        Message.tool(ToolResult(tool_call_id="tc-1", content="Proposed.", is_error=False)),
        Message.assistant("Review it."),
        Message.user("Approved proposal 1: a. Continue with the next step, if there is one."),
        Message.assistant("Next step done."),
        Message.user("Approved proposal 2: b. Continue with the next step, if there is one."),
        Message.user("Dismissed proposal 3 (change agent plain). Do not apply it."),
    ]
    marked[4].proposal_id, marked[4].proposal_event = 1, "approved"
    marked[6].proposal_id, marked[6].proposal_event = 2, "approved_no_turn"
    marked[7].proposal_id, marked[7].proposal_event = 3, "dismissed"
    w = _world(app_with_data_dir, messages=encode_messages(marked))
    _open(page, w)
    lines = page.locator(APPROVAL_LINE)
    expect(lines).to_have_text(
        ["You approved this change. GleepGlorp is continuing.", "You approved this change."]
    )
    assert _chats.messages(page, "user").count() == 1
    assert _order(page) == ["user", "work", "reply", "approved", "reply", "approved"]
    expect(_chats.replies(page).nth(1)).to_have_text("Next step done.")


# ── Refusals ───────────────────────────────────────────────────────────────


def test_a_stale_proposal_shows_the_panel_and_approve_anyway_applies(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, provider_config={"response": {"content": "Done."}})
    pid = _seed(
        w, changes={"description": "Proposed words"}, base={"description": "What it said before"}
    )
    _open(page, w)
    c = _card(page, pid)
    expect(c).to_have_attribute("data-state", "pending")
    approve = _in(c, "proposal-approve")
    approve.focus()
    page.keyboard.press("Enter")

    # [waiting] -> [stale]: a warning banner, Current and Proposed, Approve anyway (focused).
    expect(c).to_have_attribute("data-state", "stale", timeout=8000)
    stale = _in(c, "proposal-stale")
    expect(stale).to_have_text(
        "Description changed after GleepGlorp proposed this. "
        "Approving anyway replaces the current value below."
    )
    assert stale.get_attribute("role") == "alert"
    table = _in(c, "proposal-table")
    expect(table.locator("thead th")).to_have_text(["Field", "Current", "Proposed"])
    expect(table.locator("tbody tr").first.locator("td")).to_have_text(["None", "Proposed words"])
    expect(_in(c, "proposal-approve-anyway")).to_be_focused()
    expect(_in(c, "proposal-approve")).to_have_count(0)
    assert _agent(w)["description"] == ""
    # A stale proposal stays pending: a reload shows the waiting state again.
    page.reload()
    _chats.open_chat(page, w.sid)
    expect(_card(page, pid)).to_have_attribute("data-state", "pending")
    expect(_in(_card(page, pid), "proposal-stale")).to_have_count(0)

    # [waiting] -> [stale] -> [applied]: Approve anyway replaces the value.
    _in(_card(page, pid), "proposal-approve").click()
    expect(_card(page, pid)).to_have_attribute("data-state", "stale", timeout=8000)
    _in(_card(page, pid), "proposal-approve-anyway").click()
    expect(_card(page, pid)).to_have_attribute("data-state", "applied", timeout=8000)
    assert _agent(w)["description"] == "Proposed words"


def test_a_failed_apply_keeps_the_card_open_with_try_again_and_dismiss_works(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _seed(
        w, action="create", agent_name="plain", changes={"name": "plain", "description": "Dup"}
    )
    _open(page, w)
    c = _card(page, pid)
    expect(_in(c, "proposal-title")).to_have_text("Create agent “plain”")
    approve = _in(c, "proposal-approve")
    approve.focus()
    page.keyboard.press("Enter")
    # [waiting] -> [failed]: the field error, Try again (focused) and Dismiss; nothing folded.
    expect(c).to_have_attribute("data-state", "failed", timeout=8000)
    err = _in(c, "proposal-error")
    expect(err).to_contain_text("Couldn't apply this change.")
    expect(err).to_contain_text("Name:")
    assert err.get_attribute("role") == "alert"
    expect(_in(c, "proposal-try-again")).to_be_focused()
    expect(_in(c, "proposal-dismiss")).to_be_enabled()
    # Try again approves again (it fails the same way: the card stays failed).
    _in(c, "proposal-try-again").click()
    expect(c).to_have_attribute("data-state", "failed", timeout=8000)
    expect(_in(c, "proposal-try-again")).to_be_enabled()
    # [failed] -> [dismissed]: a quiet line, focus on the composer, and nothing drawn in the log
    # for the dismissal message itself.
    dismiss = _in(c, "proposal-dismiss")
    dismiss.focus()
    page.keyboard.press("Enter")
    expect(c).to_have_attribute("data-state", "dismissed", timeout=8000)
    expect(page.locator(INPUT)).to_be_focused()
    page.wait_for_timeout(200)
    expect(page.locator(APPROVAL_LINE)).to_have_count(0)
    assert _chats.messages(page, "user").count() == 1


def test_deleting_the_agent_withdraws_the_card_after_a_reload(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    seed_mock_agent(w.base, w.provider, "victim")
    pid = _seed(w, agent_name="victim", changes={"description": "Words"}, base={"description": ""})
    _open(page, w)
    expect(_card(page, pid)).to_have_attribute("data-state", "pending")
    r = httpx.delete(f"{w.base}/api/agents/victim", headers=auth_headers_for(w.base), timeout=5.0)
    assert r.status_code in (200, 204), r.text
    page.reload()
    _chats.open_chat(page, w.sid)
    c = _card(page, pid)
    expect(c).to_have_attribute("data-state", "withdrawn")
    expect(_in(c, "proposal-status-line")).to_have_text(
        "Withdrawn · Change agent “victim”: the agent no longer exists."
    )
    expect(c.locator("button")).to_have_count(0)


def test_refused_clicks_show_neutral_lines_and_a_closed_answer_refetches(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    mode = {"answer": "busy"}

    def handler(route) -> None:
        if mode["answer"] == "abort":
            route.abort()
        elif mode["answer"] == "closed":
            route.fulfill(
                status=409,
                content_type="application/json",
                body='{"detail": {"error": "closed", "status": "dismissed"}}',
            )
        else:
            route.fulfill(
                status=409,
                content_type="application/json",
                body='{"detail": {"error": "busy"}}',
            )

    page.route("**/api/gleepglorp/proposals/*/approve", handler)
    _open(page, w)
    c = _card(page, pid)

    # [waiting] -> a 409 busy: a neutral line, still waiting (never danger, never warning).
    _in(c, "proposal-approve").click()
    notice = _in(c, "proposal-notice")
    expect(notice).to_have_text("GleepGlorp is still working. Try again when it finishes.")
    assert notice.get_attribute("data-state") == "idle"
    expect(c).to_have_attribute("data-state", "pending")
    expect(_in(c, "proposal-approve")).to_be_enabled()
    assert page.locator(f"{CARD} .banner-warning, {CARD} [data-state=danger]").count() == 0

    # An unreachable app: the plain sentence and the raw message under Technical details.
    mode["answer"] = "abort"
    _in(c, "proposal-approve").click()
    expect(_in(c, "proposal-notice")).to_have_text("Couldn't reach the app. Try again.")
    details = _in(c, "proposal-notice-details")
    expect(details).to_have_count(1)
    assert details.get_attribute("open") is None

    # A closed answer re-fetches the chat's proposals and redraws (here: dismissed elsewhere).
    mode["answer"] = "closed"
    httpx.post(
        f"{w.base}/api/gleepglorp/proposals/{pid}/dismiss",
        headers=auth_headers_for(w.base),
        timeout=5.0,
    )
    page.wait_for_timeout(200)
    c = _card(page, pid)
    if c.get_attribute("data-state") != "dismissed":
        _in(c, "proposal-approve").click()
    expect(_card(page, pid)).to_have_attribute("data-state", "dismissed", timeout=8000)


def test_a_snapshot_during_an_in_flight_join_draws_busy_buttons_until_the_turn_ends(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    # The join answers "a turn is running" (is_processing), as a reload mid-turn does.
    _Script(processing=True).install(page)
    _open(page, w)
    approve = _in(_card(page, pid), "proposal-approve")
    expect(approve).to_be_disabled()
    expect(approve).to_have_attribute("aria-disabled", "true")
    expect(approve).to_have_attribute("title", WAIT)
    # [busy] -> [idle]: the turn ends and the buttons are released.
    _frames(page, DONE)
    expect(approve).to_be_enabled()
    assert approve.get_attribute("aria-disabled") is None
    assert approve.get_attribute("title") is None


def test_busy_buttons_stay_focusable_and_ignore_the_keyboard(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """aria-disabled, never the native attribute: focusable, hint read, activation ignored."""
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    _Script(processing=True).install(page)
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    _open(page, w)
    approve = _in(_card(page, pid), "proposal-approve")
    expect(approve).to_have_attribute("aria-disabled", "true")
    assert approve.get_attribute("disabled") is None
    approve.focus()
    assert (
        page.evaluate("() => document.activeElement.getAttribute('data-testid')")
        == "proposal-approve"
    )
    hint_id = approve.get_attribute("aria-describedby")
    assert page.locator(f"#{hint_id}").inner_text() == WAIT
    page.keyboard.press("Enter")
    page.keyboard.press("Space")
    page.wait_for_timeout(300)
    assert not [u for u in posts if "/proposals/" in u]
    expect(_card(page, pid)).to_have_attribute("data-state", "pending")


def test_the_card_is_not_a_live_region_and_one_status_node_speaks_each_state(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    _open(page, w)
    _changed(page, w.sid, _view(31, w.sid))
    card = _card(page, 31)
    expect(card).to_have_attribute("aria-live", "off")
    status = _in(card, "proposal-announce")
    expect(status).to_have_count(1)
    assert status.get_attribute("role") == "status"
    # The first appearance is announced once.
    expect(status).to_have_text("GleepGlorp proposed a change: Change agent “plain”.")
    # A rebuild in the same state does not touch it (same text node, no second announcement).
    node = status.element_handle()
    _changed(page, w.sid, _view(31, w.sid))
    assert node.evaluate(
        "(n, c) => n === c.querySelector('[data-testid=proposal-announce]')", card.element_handle()
    )
    # A failed card is told by its alert alone: the status is empty and no text is duplicated.
    _changed(
        page,
        w.sid,
        _view(
            31,
            w.sid,
            status="failed",
            resolved_at="2026-01-02T10:05:00+00:00",
            result={"errors": [{"loc": ["description"], "msg": "Too long."}]},
        ),
    )
    expect(_in(card, "proposal-error")).to_have_attribute("role", "alert")
    expect(status).to_have_text("")
    # A resolved state speaks once through the same node.
    _changed(
        page,
        w.sid,
        _view(31, w.sid, status="dismissed", resolved_at="2026-01-02T10:06:00+00:00"),
    )
    expect(status).to_have_text("Dismissed: Change agent “plain”.")


def test_an_applying_card_marks_busy_on_the_body_never_above_the_status_node(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """WCAG 4.1.3: some screen readers hold back live-region updates inside an aria-busy subtree,
    so the busy marker sits on the body wrapper, never on an ancestor of the status node."""
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    held: list[Any] = []
    page.route("**/api/gleepglorp/proposals/*/approve", lambda route: held.append(route))
    _open(page, w)
    c = _card(page, pid)
    _in(c, "proposal-approve").click()
    expect(c).to_have_attribute("data-state", "applying")
    busy_ancestors = """() => {
      const s = document.querySelector('[data-testid="proposal-announce"]');
      const out = [];
      for (let n = s; n; n = n.parentElement) {
        if (n.getAttribute('aria-busy') === 'true') out.push(n.className || n.tagName);
      }
      return out;
    }"""
    assert page.evaluate(busy_ancestors) == []
    expect(c.locator(".chat-proposal-body")).to_have_attribute("aria-busy", "true")
    # The busy signal goes when the card leaves applying.
    held[0].fulfill(
        status=409,
        content_type="application/json",
        body='{"detail": {"error": "busy"}}',
    )
    expect(c).to_have_attribute("data-state", "pending")
    expect(c.locator(".chat-proposal-body")).not_to_have_attribute("aria-busy", "true")


def test_a_card_drawn_from_the_snapshot_is_silent(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _seed(w, changes={"description": "Words"}, base={"description": ""})
    _open(page, w)
    expect(_in(_card(page, pid), "proposal-announce")).to_have_text("")

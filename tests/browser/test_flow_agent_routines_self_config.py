"""The Self-configuration tab's Routines item (M33 F2 L5; flight DD5, DD11).

The tab has two items, "Agent prompt" (today's controls, relabelled) and "Routines": two
switches (let the agent manage its routines; require approval for its changes), the "Waiting
for approval" queue (Approve, Dismiss, the stale path and "Approve anyway"), and the read-only
"Changes by the agent" history. The Routines tab shows "Made by the agent" and the routine flag;
the drawer shows the flag; saving the edit form of a flagged routine clears it.

No REST route creates a proposal (only the agent's tools do), so most tests seed through
``seeders.seed_routine_proposal`` / ``seed_agent_routine`` (direct sqlite inserts, the way
``seed_note`` works); one test runs the real chain (a mock provider turn whose ``tool_calls``
run ``schedule_routine``). Falls in the ``agent-routines`` lane via the
``test_flow_agent_routines*`` glob.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from browser import _chats, _lists, _nav
from browser._credential_registry import auth_headers_for
from browser._self_config import (
    ROUTINES_HISTORY,
    ROUTINES_WAITING,
    click_switch,
    expander,
    open_expander,
)
from browser.seeders import canonical_schedule as canon
from browser.seeders import (
    seed_agent_routine,
    seed_mock_agent,
    seed_mock_provider,
    seed_routine_proposal,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

AGENT = "sc-routines-agent"
ENABLE = "Let this agent manage its routines"
APPROVAL = "Require approval for routine changes"
PROPOSAL = '[data-testid="self-config-routine-proposal"]'
HISTORY_ROW = '[data-testid="self-config-routine-history-row"]'

BASE_DAILY = {
    "name": "nightly",
    "prompt": "Say hello.",
    "schedule": canon("09:00"),
    "anchor_at": None,
    "enabled": True,
    "finished_at": None,
}
CREATE_PAYLOAD = {
    "name": "morning-check",
    "prompt": "Check the inbox.",
    "schedule": canon("08:00"),
    "anchor_at": None,
    "enabled": True,
}


@pytest.fixture
def env(app_with_data_dir: tuple[str, Path]) -> Iterator[tuple[str, Path]]:
    base, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base)
    seed_mock_agent(base, provider_id, name=AGENT)
    yield base, data_dir


def _headers(base: str) -> dict[str, str]:
    return auth_headers_for(base)


def _switches(base: str) -> dict:
    r = httpx.get(
        f"{base}/api/agents/{AGENT}/self-configuration/routines", headers=_headers(base), timeout=5
    )
    assert r.status_code == 200, r.text
    return r.json()


def _put_switches(base: str, **body: bool) -> None:
    r = httpx.put(
        f"{base}/api/agents/{AGENT}/self-configuration/routines",
        json=body,
        headers=_headers(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text


def _routines(base: str) -> list[dict]:
    r = httpx.get(f"{base}/api/agents/{AGENT}/routines", headers=_headers(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()["routines"]


def _open_item(page: Page, base: str, *, expanders: bool = True) -> None:
    """Open the tab; by default also open the Routines card's History and, when changes wait,
    its "Waiting for approval" expander (both are collapsed on arrival, M33 F4 L06)."""
    _nav.goto(page, base, f"agents/{_nav.seg(AGENT)}/self-configuration")
    expect(page.locator('[data-testid="self-config-routines-status"]')).not_to_have_text(
        "Loading…", timeout=8000
    )
    if expanders:
        if expander(page, ROUTINES_WAITING).is_visible():
            open_expander(page, ROUTINES_WAITING)
        open_expander(page, ROUTINES_HISTORY)


def _switch(page: Page, name: str):
    return page.get_by_role("switch", name=name)


def _seed_create(data_dir: Path, name: str, created_at: str, **kw) -> str:
    payload = dict(CREATE_PAYLOAD, name=name)
    return seed_routine_proposal(
        data_dir, AGENT, "create", payload, routine_name=name, created_at=created_at, **kw
    )


def _delete_routine_row(data_dir: Path, routine_id: str) -> None:
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM agent_routines WHERE id = ?", (routine_id,))
        conn.commit()
    finally:
        conn.close()


PANEL = '[role="tabpanel"]:has([data-testid="self-configuration-status"])'


def test_the_tab_is_two_cards_then_external_access(env, page: Page) -> None:
    """SC2 (M33 F4 L06): a page eyebrow, the Agent prompt and Routines cards (enable switch,
    title, Require approval, description, two expanders), then External access last; no
    separate "Prompt approval" section."""
    base, _ = env
    _open_item(page, base, expanders=False)
    panel = page.locator(PANEL)
    h2 = [t.strip() for t in panel.locator("h2").all_text_contents()]
    assert h2 == ["What this agent can change", "External access"], h2
    h3 = [t.strip() for t in panel.locator("h3").all_text_contents()]
    assert h3 == [], h3  # the card titles are role=heading level 3 spans, not h3 elements
    titles = panel.get_by_role("heading", level=3)
    expect(titles).to_have_text(["Agent prompt", "Routines"])
    assert "Prompt approval" not in panel.inner_text()

    # Document order: eyebrow, prompt card, routines card, External access.
    order = page.evaluate(
        """(sel) => {
          const p = document.querySelector(sel);
          const q = (s) => p.querySelector(s);
          const pos = (el) => Array.from(p.querySelectorAll('*')).indexOf(el);
          const ids = ['.self-config-items-section', '[data-testid="self-config-card-prompt"]',
            '[data-testid="self-config-card-routines"]', '.self-configuration-external-section'];
          return ids.map((s) => pos(q(s)));
        }""",
        PANEL,
    )
    assert order == sorted(order) and len(set(order)) == 4, order

    for item in ("prompt", "routines"):
        card = page.locator(f'[data-testid="self-config-card-{item}"]')
        # Title row: the enable switch, the title, then "Require approval" on the same row.
        row = card.locator("> .self-config-card-row")
        expect(row.get_by_role("switch")).to_have_count(2)
        expect(row.locator(".self-config-approval")).to_contain_text("Require approval")
        # The one-line description sits under the title row.
        expect(card).to_contain_text(
            "Edit its own description and system prompt."
            if item == "prompt"
            else "List, schedule, change and cancel its own routines"
        )
        # Two expanders, collapsed; the waiting one is plain text while nothing waits.
        assert card.locator("> details.self-config-expander").count() == 2
        expect(card.locator("> details[open]")).to_have_count(0)
    expect(_switch(page, "Let this agent edit its description and system prompt")).to_have_count(1)
    expect(_switch(page, "Require approval for prompt edits")).to_have_count(1)
    expect(page.locator('[data-testid="self-configuration-status"]')).to_contain_text("disabled")
    waiting = page.locator('[data-testid="pending-queue-empty"]')
    expect(waiting).to_have_text("Waiting for approval (0)")
    expect(page.locator('[data-testid="self-config-routine-proposals-empty"]')).to_have_text(
        "Waiting for approval (0)"
    )
    expect(expander(page, "self-config-prompt-waiting")).to_be_hidden()
    expect(expander(page, ROUTINES_WAITING)).to_be_hidden()

    # Both title rows share one line at this width: the approval switch is beside the title.
    boxes = page.evaluate(
        """() => ['prompt', 'routines'].map((i) => {
          const c = document.querySelector('[data-testid="self-config-card-' + i + '"]');
          const t = c.querySelector('.self-config-card-name').getBoundingClientRect();
          const a = c.querySelector('.self-config-approval').getBoundingClientRect();
          return [Math.round(t.top), Math.round(a.top), a.left > t.left];
        })"""
    )
    for top_t, top_a, right_of in boxes:
        assert abs(top_t - top_a) < 20 and right_of, boxes


def test_waiting_expander_shows_a_count_and_the_expanders_are_keyboard_operable(
    env, page: Page
) -> None:
    base, data_dir = env
    _put_switches(base, enabled=True)
    _seed_create(data_dir, "first-one", "2026-02-01T10:00:00+00:00")
    _seed_create(data_dir, "second-one", "2026-02-01T10:05:00+00:00")
    _open_item(page, base, expanders=False)
    details = expander(page, ROUTINES_WAITING)
    summary = details.locator("> summary")
    expect(details).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="self-config-routine-pending-count"]')).to_have_text("2")
    expect(page.locator('[data-testid="self-config-routine-proposals-empty"]')).to_be_hidden()
    # Collapsed by default; the name carries the count.
    expect(details).not_to_have_attribute("open", "")
    expect(page.locator(PROPOSAL).first).to_be_hidden()
    expect(summary).to_have_accessible_name("Waiting for approval 2")
    # Keyboard: Enter opens, Space closes, and the open state is exposed.
    summary.focus()
    page.keyboard.press("Enter")
    expect(details).to_have_attribute("open", "")
    expect(page.locator(PROPOSAL).first).to_be_visible()
    page.keyboard.press("Space")
    expect(details).not_to_have_attribute("open", "")
    expect(page.locator(PROPOSAL).first).to_be_hidden()
    # The History expander is operable the same way.
    history = expander(page, ROUTINES_HISTORY)
    history.locator("> summary").focus()
    page.keyboard.press("Enter")
    expect(history).to_have_attribute("open", "")


def test_a_failure_opens_a_collapsed_waiting_expander(env, page: Page) -> None:
    """An Approve that fails after the operator collapsed the expander opens it again, so the
    message is visible (AC4)."""
    base, data_dir = env
    _put_switches(base, enabled=True)
    _seed_create(data_dir, "morning-check", "2026-02-01T10:00:00+00:00")
    held: list = []
    page.route("**/routines/proposals/*/approve*", lambda route: held.append(route))
    _open_item(page, base)
    details = expander(page, ROUTINES_WAITING)
    page.locator('[data-testid="self-config-routine-approve"]').click()
    page.wait_for_timeout(300)
    assert held, "the approve request was not held"
    details.locator("> summary").click()
    expect(details).not_to_have_attribute("open", "")
    held[0].fulfill(status=500, body="boom")
    expect(details).to_have_attribute("open", "")
    expect(
        page.locator(PROPOSAL).locator('[data-testid="self-config-routine-error"]')
    ).to_be_visible()


def test_a_stale_answer_opens_a_collapsed_waiting_expander(env, page: Page) -> None:
    base, data_dir = env
    _put_switches(base, enabled=True)
    rid = seed_agent_routine(data_dir, AGENT, "nightly", created_by="operator")
    seed_routine_proposal(
        data_dir,
        AGENT,
        "update",
        {"schedule": canon("10:00", repeat="weekdays"), "anchor_at": None},
        routine_name="nightly",
        routine_id=rid,
        base=BASE_DAILY,
        created_at="2026-02-01T10:01:00+00:00",
    )
    r = httpx.put(
        f"{base}/api/agents/{AGENT}/routines/{rid}",
        json={"schedule": canon("07:00")},
        headers=_headers(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    held: list = []
    page.route("**/routines/proposals/*/approve*", lambda route: held.append(route))
    _open_item(page, base)
    details = expander(page, ROUTINES_WAITING)
    page.locator('[data-testid="self-config-routine-approve"]').click()
    page.wait_for_timeout(300)
    assert held
    details.locator("> summary").click()
    expect(details).not_to_have_attribute("open", "")
    held[0].continue_()
    expect(details).to_have_attribute("open", "")
    expect(page.locator('[data-testid="self-config-routine-approve-override"]')).to_be_visible()


def test_switches_post_and_persist_with_approval_off_by_default(env, page: Page) -> None:
    base, _ = env
    assert _switches(base) == {"enabled": False, "requires_approval": False, "pending_count": 0}
    _open_item(page, base)
    status = page.locator('[data-testid="self-config-routines-status"]')
    approval = page.locator('[data-testid="self-config-routines-approval-status"]')
    expect(status).to_have_text("Off: this agent has no routine tools.")
    expect(approval).to_have_text("Approval is off: changes apply at once.")

    click_switch(page, ENABLE)
    expect(status).to_have_text("On: this agent can manage its routines.")
    click_switch(page, APPROVAL)
    expect(approval).to_have_text("Approval is on: changes wait for you.")
    assert _switches(base)["enabled"] is True and _switches(base)["requires_approval"] is True
    expect(page.locator('[data-testid="self-config-routines-error"]')).to_be_hidden()

    page.reload()
    expect(status).to_have_text("On: this agent can manage its routines.", timeout=8000)
    expect(_switch(page, ENABLE)).to_be_checked()
    expect(_switch(page, APPROVAL)).to_be_checked()


def test_a_failed_switch_restores_and_shows_its_error(env, page: Page) -> None:
    base, _ = env
    _open_item(page, base)
    page.route(
        "**/self-configuration/routines",
        lambda route: (
            route.fulfill(status=500, body="boom")
            if route.request.method == "PUT"
            else route.continue_()
        ),
    )
    click_switch(page, ENABLE)
    expect(page.locator('[data-testid="self-config-routines-error"]')).to_be_visible()
    expect(_switch(page, ENABLE)).not_to_be_checked()
    assert _switches(base)["enabled"] is False


def test_turning_routines_off_withdraws_pending_changes(env, page: Page) -> None:
    base, data_dir = env
    _put_switches(base, enabled=True)
    _seed_create(data_dir, "morning-check", "2026-02-01T10:00:00+00:00")
    _open_item(page, base)
    expect(page.locator(PROPOSAL)).to_have_count(1, timeout=8000)
    click_switch(page, ENABLE)
    expect(page.locator('[data-testid="self-config-routines-live"]')).to_have_text(
        "Pending changes were withdrawn."
    )
    expect(page.locator(PROPOSAL)).to_have_count(0)
    # The count drops at once: the expander gives way to the plain "(0)" line.
    expect(page.locator('[data-testid="self-config-routine-proposals-empty"]')).to_be_visible()
    expect(expander(page, ROUTINES_WAITING)).to_be_hidden()
    expect(page.locator('[data-testid="self-config-routine-pending-count"]')).to_have_text("0")
    expect(page.locator('[data-testid="self-config-routines-status"]')).to_contain_text(
        "Pending changes were withdrawn."
    )
    expect(page.locator(HISTORY_ROW).first.locator("[data-testid$='history-status']")).to_have_text(
        "Withdrawn"
    )


def test_approve_create_change_and_cancel_and_the_routines_tab_reflects_it(env, page: Page) -> None:
    base, data_dir = env
    rid = seed_agent_routine(data_dir, AGENT, "nightly", created_by="operator")
    rid2 = seed_agent_routine(data_dir, AGENT, "old-thing", created_by="operator")
    _seed_create(data_dir, "morning-check", "2026-02-01T10:00:00+00:00")
    seed_routine_proposal(
        data_dir,
        AGENT,
        "update",
        {"schedule": canon("10:00", repeat="weekdays"), "anchor_at": None},
        routine_name="nightly",
        routine_id=rid,
        base=BASE_DAILY,
        created_at="2026-02-01T10:01:00+00:00",
    )
    seed_routine_proposal(
        data_dir,
        AGENT,
        "delete",
        {},
        routine_name="old-thing",
        routine_id=rid2,
        base=dict(BASE_DAILY, name="old-thing"),
        created_at="2026-02-01T10:02:00+00:00",
    )
    _open_item(page, base)
    items = page.locator(PROPOSAL)
    expect(items).to_have_count(3, timeout=8000)
    expect(page.locator('[data-testid="self-config-routine-pending-count"]')).to_have_text("3")
    actions = items.locator('[data-testid="self-config-routine-action"]').all_inner_texts()
    assert sorted(actions) == ["Cancel", "Change", "Create"]
    change = page.locator(f'{PROPOSAL}[data-action="update"]')
    expect(change).to_contain_text("Every day at 9:00 AM → Every weekday at 10:00 AM")
    expect(change).not_to_contain_text("Prompt")

    for action in ("update", "create", "delete"):
        page.locator(f'{PROPOSAL}[data-action="{action}"]').locator(
            '[data-testid="self-config-routine-approve"]'
        ).click()
    expect(items).to_have_count(0, timeout=8000)
    by_name = {r["name"]: r for r in _routines(base)}
    assert set(by_name) == {"nightly", "morning-check"}
    assert by_name["nightly"]["schedule"]["repeat"]["days"] == [0, 1, 2, 3, 4]
    assert by_name["nightly"]["schedule"]["start"]["time"] == "10:00"
    assert by_name["morning-check"]["created_by"] == "agent"
    statuses = page.locator('[data-testid="self-config-routine-history-status"]').all_inner_texts()
    assert statuses.count("Applied") == 3

    page.locator('[data-testid="tab-routines"]').click()
    expect(page.locator('[data-testid="routine-name"]', has_text="morning-check")).to_be_visible(
        timeout=8000
    )
    expect(page.locator('[data-testid="routine-origin"]:visible')).to_have_count(1)


def test_dismiss_removes_the_item_and_logs_it_in_history(env, page: Page) -> None:
    base, data_dir = env
    _seed_create(data_dir, "morning-check", "2026-02-01T10:00:00+00:00")
    _open_item(page, base)
    page.locator('[data-testid="self-config-routine-dismiss"]').click()
    expect(page.locator(PROPOSAL)).to_have_count(0, timeout=8000)
    expect(page.locator('[data-testid="self-config-routines-live"]')).to_contain_text(
        "Dismissed create of morning-check"
    )
    expect(page.locator('[data-testid="self-config-routine-history-status"]')).to_have_text(
        "Dismissed"
    )
    assert _routines(base) == []


def test_history_row_is_one_flat_line(env, page: Page) -> None:
    """HAT fix pass 2: a history entry is one compact line (time, action, routine name,
    outcome, flag) at one text size, with no card inside the History expander, no
    "Changes by the agent" sub-heading and no static restatement of the switch states."""
    base, data_dir = env
    seed_routine_proposal(
        data_dir,
        AGENT,
        "create",
        dict(CREATE_PAYLOAD, name="check example.com"),
        routine_name="check example.com",
        created_at="2026-02-01T10:00:00+00:00",
        resolved_at="2026-02-01T10:30:00+00:00",
        status="applied",
        untrusted=True,
        sources=["web"],
    )
    _open_item(page, base)
    row = page.locator(HISTORY_ROW)
    expect(row).to_have_count(1, timeout=8000)
    name = row.locator('[data-testid="self-config-routine-name"]')
    outcome = row.locator('[data-testid="self-config-routine-history-status"]')
    expect(name).to_have_text("check example.com")
    expect(outcome).to_have_text("Applied")
    # One line: the name, the outcome and the time share a baseline row, and the row is
    # no taller than a two-line card would be.
    boxes = [
        row.locator(f'[data-testid="{t}"]').bounding_box()
        for t in (
            "self-config-routine-when",
            "self-config-routine-action",
            "self-config-routine-name",
            "self-config-routine-history-status",
        )
    ]
    tops = [b["y"] for b in boxes]
    assert max(tops) - min(tops) < 6, tops
    assert row.bounding_box()["height"] < 48
    # One text size: the name is not larger than the outcome or the time.
    sizes = row.evaluate(
        """el => [...el.querySelectorAll(
            '[data-testid=self-config-routine-name], '
            + '[data-testid=self-config-routine-history-status], '
            + '[data-testid=self-config-routine-when]')]
            .map(n => getComputedStyle(n).fontSize)"""
    )
    assert len(set(sizes)) == 1, sizes
    # Flat: no border box of its own besides the hairline above it, and no nested card.
    flat = row.evaluate(
        """el => { const s = getComputedStyle(el);
            return [s.borderLeftWidth, s.borderRightWidth,
                s.borderBottomWidth, s.borderRadius]; }"""
    )
    assert flat == ["0px", "0px", "0px", "0px"], flat
    expect(row.locator('[data-testid="self-config-routine-flag"]')).to_be_visible()
    # The expander's own label is the heading: no sub-heading, a named list instead.
    history = page.locator('[data-testid="self-config-routines-history-details"]')
    expect(history.locator(".self-configuration-subheading")).to_have_count(0)
    expect(history.get_by_role("list", name="Changes by the agent")).to_have_count(1)
    # The switch states are not restated as static text (they stay readable to assistive tech).
    for t in ("self-config-routines-status", "self-config-routines-approval-status"):
        box = page.locator(f'[data-testid="{t}"]').bounding_box()
        assert box is None or (box["width"] <= 2 and box["height"] <= 2), (t, box)


def test_focus_moves_to_the_next_approve_then_to_the_empty_state(env, page: Page) -> None:
    base, data_dir = env
    _seed_create(data_dir, "first-one", "2026-02-01T10:00:00+00:00")
    _seed_create(data_dir, "second-one", "2026-02-01T10:05:00+00:00")
    _open_item(page, base)
    expect(page.locator(PROPOSAL)).to_have_count(2, timeout=8000)
    page.locator(PROPOSAL).first.locator('[data-testid="self-config-routine-approve"]').click()
    expect(page.locator(PROPOSAL)).to_have_count(1, timeout=8000)
    expect(
        page.locator(PROPOSAL).first.locator('[data-testid="self-config-routine-approve"]')
    ).to_be_focused()
    page.locator('[data-testid="self-config-routine-approve"]').click()
    expect(page.locator(PROPOSAL)).to_have_count(0, timeout=8000)
    expect(page.locator('[data-testid="self-config-routine-proposals-empty"]')).to_be_focused()


def test_stale_banner_then_approve_anyway(env, page: Page) -> None:
    base, data_dir = env
    rid = seed_agent_routine(data_dir, AGENT, "nightly", created_by="operator")
    seed_routine_proposal(
        data_dir,
        AGENT,
        "update",
        {"schedule": canon("10:00", repeat="weekdays"), "anchor_at": None},
        routine_name="nightly",
        routine_id=rid,
        base=BASE_DAILY,
        created_at="2026-02-01T10:01:00+00:00",
    )
    r = httpx.put(
        f"{base}/api/agents/{AGENT}/routines/{rid}",
        json={"schedule": canon("07:00")},
        headers=_headers(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    _open_item(page, base)
    item = page.locator(PROPOSAL)
    expect(item).to_have_count(1, timeout=8000)
    item.locator('[data-testid="self-config-routine-approve"]').click()
    expect(item).to_contain_text("This routine changed since the agent asked.")
    expect(item).to_contain_text("Every day at 7:00 AM")
    expect(item).to_contain_text("Every weekday at 10:00 AM")
    override = item.locator('[data-testid="self-config-routine-approve-override"]')
    expect(override).to_be_visible()
    assert _routines(base)[0]["schedule"]["start"]["time"] == "07:00"
    assert _routines(base)[0]["schedule"]["repeat"] == {"every": 1, "unit": "day"}
    # WCAG 2.4.3: focus lands on "Approve anyway", not body.
    expect(override).to_be_focused()
    override.click()
    expect(page.locator(PROPOSAL)).to_have_count(0, timeout=8000)
    assert _routines(base)[0]["schedule"]["repeat"]["days"] == [0, 1, 2, 3, 4]
    assert _routines(base)[0]["schedule"]["start"]["time"] == "10:00"


def test_gone_removes_the_item_and_says_so(env, page: Page) -> None:
    base, data_dir = env
    rid = seed_agent_routine(data_dir, AGENT, "nightly", created_by="operator")
    seed_routine_proposal(
        data_dir,
        AGENT,
        "update",
        {"schedule": canon("10:00", repeat="weekdays"), "anchor_at": None},
        routine_name="nightly",
        routine_id=rid,
        base=BASE_DAILY,
        created_at="2026-02-01T10:01:00+00:00",
    )
    _delete_routine_row(data_dir, rid)
    _open_item(page, base)
    expect(page.locator(PROPOSAL)).to_have_count(1, timeout=8000)
    page.locator('[data-testid="self-config-routine-approve"]').click()
    expect(page.locator(PROPOSAL)).to_have_count(0, timeout=8000)
    expect(page.locator('[data-testid="self-config-routines-live"]')).to_have_text(
        "The routine is gone; the change was withdrawn."
    )
    expect(page.locator('[data-testid="self-config-routine-history-status"]')).to_have_text(
        "Withdrawn"
    )


def test_an_invalid_schedule_shows_its_sentence_in_the_item(env, page: Page) -> None:
    base, data_dir = env
    payload = dict(
        CREATE_PAYLOAD,
        schedule=canon("09:00", repeat=None, date="2020-01-01"),
        anchor_at="2020-01-01T09:00:00+00:00",
    )
    seed_routine_proposal(
        data_dir,
        AGENT,
        "create",
        payload,
        routine_name="morning-check",
        created_at="2026-02-01T10:00:00+00:00",
    )
    _open_item(page, base)
    page.locator('[data-testid="self-config-routine-approve"]').click()
    err = page.locator(PROPOSAL).locator('[data-testid="self-config-routine-error"]')
    expect(err).to_be_visible(timeout=8000)
    assert err.inner_text().strip()
    # Focus returns to the pressed Approve button after the 422.
    expect(page.locator('[data-testid="self-config-routine-approve"]')).to_be_focused()
    expect(page.locator(PROPOSAL)).to_have_count(1)
    expect(page.locator('[data-testid="self-config-routine-dismiss"]')).to_be_enabled()
    assert _routines(base) == []


def test_history_pages_twenty_at_a_time(env, page: Page) -> None:
    base, data_dir = env
    for i in range(23):
        _seed_create(
            data_dir,
            f"r{i:02d}",
            f"2026-01-{i + 1:02d}T10:00:00+00:00",
            status="applied",
            resolved_at=f"2026-01-{i + 1:02d}T10:00:01+00:00",
        )
    _open_item(page, base)
    rows = page.locator(HISTORY_ROW)
    expect(rows).to_have_count(20, timeout=8000)
    expect(rows.first.locator('[data-testid="self-config-routine-name"]')).to_have_text("r22")
    older = page.locator('[data-testid="self-config-routine-history-older"]')
    older.click()
    expect(rows).to_have_count(23, timeout=8000)
    expect(page.locator('[data-testid="self-config-routines-live"]')).to_have_text(
        "3 older changes shown."
    )
    expect(older).to_be_hidden()
    expect(rows.last.locator('[data-testid="self-config-routine-name"]')).to_have_text("r00")


def test_show_older_is_not_left_disabled_by_a_refetch_mid_load(env, page: Page) -> None:
    base, data_dir = env
    for i in range(23):
        _seed_create(
            data_dir,
            f"r{i:02d}",
            f"2026-01-{i + 1:02d}T10:00:00+00:00",
            status="applied",
            resolved_at=f"2026-01-{i + 1:02d}T10:00:01+00:00",
        )
    _seed_create(data_dir, "waiting", "2026-03-01T10:00:00+00:00")
    held: list = []
    page.route("**/routines/proposals?*before=*", lambda route: held.append(route))
    _open_item(page, base)
    rows = page.locator(HISTORY_ROW)
    expect(rows).to_have_count(20, timeout=8000)
    older = page.locator('[data-testid="self-config-routine-history-older"]')
    older.click()
    expect(older).to_be_disabled()
    page.wait_for_timeout(300)
    assert held, "the older-page request was not held"
    # Approving bumps the routines refetch sequence while the older page is in flight.
    page.locator('[data-testid="self-config-routine-approve"]').click()
    expect(page.locator(PROPOSAL)).to_have_count(0, timeout=8000)
    for route in held:
        route.continue_()
    page.wait_for_timeout(500)
    expect(older).to_be_visible()
    expect(older).to_be_enabled()


def test_a_flagged_proposal_shows_the_routine_flag(env, page: Page) -> None:
    base, data_dir = env
    _seed_create(
        data_dir,
        "morning-check",
        "2026-02-01T10:00:00+00:00",
        untrusted=True,
        sources=["web_fetch"],
    )
    _open_item(page, base)
    flag = page.locator(PROPOSAL).locator('[data-testid="self-config-routine-flag"]')
    expect(flag).to_have_attribute(
        "aria-label",
        "Check this routine: it was written after content that didn't come from you "
        "(web_fetch). It may have been planted.",
    )


def test_routines_tab_origin_flag_and_the_flag_clearing_edit(env, page: Page) -> None:
    base, data_dir = env
    seed_agent_routine(
        data_dir, AGENT, "planted", untrusted=True, sources=["web_fetch"], created_by="agent"
    )
    seed_agent_routine(data_dir, AGENT, "mine", created_by="operator")
    _nav.goto(page, base, f"agents/{_nav.seg(AGENT)}/routines")
    row = page.locator('[data-testid="routine-row"]', has_text="planted")
    expect(row.locator('[data-testid="routine-origin"]')).to_have_text("Made by the agent")
    expect(row.locator('[data-testid="routine-flag"]')).to_be_visible(timeout=8000)
    mine = page.locator('[data-testid="routine-row"]', has_text="mine")
    expect(mine.locator('[data-testid="routine-origin"]')).to_be_hidden()
    expect(mine.locator('[data-testid="routine-flag"]')).to_have_count(0)

    row.locator('[data-testid="routine-actions"]').click()
    row.locator('[data-testid="routine-edit"]').click()
    expect(page.get_by_text("Saving marks this routine as checked.")).to_be_visible()
    page.locator('[data-testid="routine-form-save"]').click()
    expect(row.locator('[data-testid="routine-flag"]')).to_have_count(0, timeout=8000)
    assert [r for r in _routines(base) if r["name"] == "planted"][0]["untrusted"] is False


def test_the_default_agent_has_a_note_and_no_switches(env, page: Page) -> None:
    base, _ = env
    r = httpx.post(
        f"{base}/api/agents",
        json={"name": "default", "description": "the default configuration"},
        headers=_headers(base),
        timeout=5,
    )
    assert r.status_code in (200, 201), r.text
    _nav.goto(page, base, "agents/default/self-configuration")
    expect(page.locator('[data-testid="self-config-routines-default-agent"]')).to_have_text(
        "Routines need a named agent.", timeout=8000
    )
    expect(_switch(page, ENABLE)).to_have_count(0)


def test_a_proposal_made_by_the_real_chain_lands_in_the_queue(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, _ = app_with_data_dir
    provider_id = seed_mock_provider(
        base,
        name="routines-chain",
        config={
            "response": {
                "content": "Scheduled.",
                "tool_calls": [
                    {
                        "id": "r1",
                        "name": "schedule_routine",
                        "arguments": {
                            "name": "chain-check",
                            "prompt": "Check back.",
                            "schedule": canon("08:00"),
                        },
                    }
                ],
            }
        },
    )
    agent = seed_mock_agent(base, provider_id, name="chain-agent", max_iterations=1)
    r = httpx.put(
        f"{base}/api/agents/{agent}/self-configuration/routines",
        json={"enabled": True, "requires_approval": True},
        headers=_headers(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text

    page.goto(base)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "schedule a check")
    page.wait_for_function(
        """async (a) => {
            const r = await fetch('/api/agents/' + a + '/self-configuration/routines');
            return (await r.json()).pending_count > 0;
        }""",
        arg=agent,
        timeout=15000,
    )
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/self-configuration")
    open_expander(page, ROUTINES_WAITING)
    item = page.locator(PROPOSAL)
    expect(item).to_have_count(1, timeout=8000)
    expect(item).to_contain_text("Create")
    expect(item).to_contain_text("chain-check")
    expect(item).to_contain_text("Every day at 8:00 AM")


def test_form_body_always_carries_the_prompt_for_a_flagged_routine(env, page: Page) -> None:
    base, _ = env
    page.goto(base)
    out = page.evaluate(
        """() => {
          const m = App.studio.routinesFormModel;
          const row = {name: 'a', prompt: 'p',
                       schedule: {kind: 'daily', time: '09:00'}};
          const st = m.bodyToFormState(row, App.time.parts);
          return {
            plain: m.formToBody(st, {mode: 'edit', initial: st}),
            flagged: m.formToBody(st, {mode: 'edit', initial: st, flagged: true}),
          };
        }"""
    )
    assert out["plain"] == {}
    assert out["flagged"] == {"prompt": "p"}


def test_queue_refreshes_when_the_tab_is_reached_again_without_a_reload(env, page: Page) -> None:
    """F-E3-1: Chats -> Agents -> the agent -> Self-configuration after a proposal landed in
    the meantime shows the new waiting item and count with no page reload."""
    base, data_dir = env
    _put_switches(base, enabled=True)
    _open_item(page, base, expanders=False)
    count = page.locator('[data-testid="self-config-routine-pending-count"]')
    expect(page.locator('[data-testid="self-config-routine-proposals-empty"]')).to_be_visible()
    page.evaluate("() => { window.__no_reload = 'same page'; }")

    _nav.open_destination(page, "chats")
    _nav.expect_route(page, "chats")
    # An agent proposal lands while the operator is on another destination.
    _seed_create(data_dir, "late-proposal", "2026-01-02T10:00:00+00:00")

    _nav.open_destination(page, "agents")
    if page.locator('[data-testid="tab-self-configuration"]').count() == 0:
        _lists.open_item(page, "agents", AGENT)
    tab = page.locator('[data-testid="tab-self-configuration"]')
    if tab.get_attribute("aria-selected") != "true":
        tab.click()
    expect(count).to_have_text("1", timeout=8000)
    open_expander(page, ROUTINES_WAITING)
    expect(page.locator(PROPOSAL)).to_have_count(1)
    expect(page.locator(PROPOSAL)).to_contain_text("late-proposal")
    assert page.evaluate("() => window.__no_reload") == "same page"

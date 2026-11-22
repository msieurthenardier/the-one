"""The model provider editor follows a change the operator approved in a GleepGlorp chat, and the
provider proposal card (M36 F4 L5b, flight DD10 and DD11).

With the editor open on provider P, approving a ``provider`` proposal for P lands in the editor
without a reload: a clean field takes the stored value, a field the operator changed keeps their
value while its baseline moves, a rename updates the title, and a quiet note says where it came
from. A type change by approval re-mounts a clean editor and gives a dirty one a "Cancel to see
it" note. An approval for another provider changes nothing, and a Save in flight defers the
follow. Most tests signal through ``App.approvals.record`` (the call the approve response makes)
after changing the stored row through its API; the real-approval tests approve a seeded proposal
through the route. The provider proposal card shows option rows and the server's warnings.

Lives in the ``gleepglorp`` browser lane.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import _hold_requests, _install_counter, _wait_held
from browser.seeders import seed_gleepglorp_proposal
from browser.test_flow_agent_editor_follows_approval import _visit_chats
from browser.test_flow_chat_proposals import _card, _in, _open, _seed, _world
from browser.test_flow_gleepglorp_fill_provider import _anthropic, _get, _list, _seed_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NAME = "#pf-name"
TYPE = "#pf-type"
KEY = "#pf-api-key"
NUM_CTX = "#pf-num-ctx"
THINKING = "#pf-thinking-enabled"
EFFORT = "#pf-reasoning-effort"
SAVE = '[data-testid="save-provider-btn"]'
CANCEL = '[data-testid="cancel-provider-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="provider-approved-change-note"]'
TITLE = ".area-studio h1"
_pid = [100]


def _open_edit(page: Page, base: str, pid: str) -> None:
    _nav.goto_settled(page, base, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    expect(page.locator(UNSAVED)).to_have_text("")


def _approve_row(base: str, pid: str, **config: Any) -> dict:
    """Change the stored row the way an approved proposal does (through the API)."""
    cur = _get(base, pid)
    body = {
        "name": config.pop("name", cur["name"]),
        "type": cur["type"],
        "base_url": cur["base_url"],
        "api_key": "__MASKED__",
        "config": {**cur["config"], **config},
    }
    r = httpx.put(
        f"{base}/api/providers/{pid}", json=body, headers=auth_headers_for(base), timeout=5.0
    )
    assert r.status_code == 200, r.text
    return r.json()


def _signal(page: Page, pid: str, fields: list[str]) -> None:
    _pid[0] += 1
    page.evaluate(
        "(d) => App.approvals.record(d)",
        {
            "kind": "provider",
            "target_id": pid,
            "fields": fields,
            "session_id": "sess-approved",
            "proposal_id": _pid[0],
            "at": "2026-01-02T15:05:00+00:00",
        },
    )


# ── Same type ────────────────────────────────────────────────────────────────


def test_an_approved_change_lands_in_a_clean_editor_without_a_reload_and_says_so(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    pid = _anthropic(base)
    _open_edit(page, base, pid)
    page.evaluate("() => { window.__same_page = 1; }")
    masked = page.locator(KEY).input_value()
    _approve_row(base, pid, thinking_enabled=True, reasoning_effort="high")
    _signal(page, pid, ["thinking_enabled", "reasoning_effort"])
    expect(page.locator(THINKING)).to_be_checked(timeout=8000)
    expect(page.locator(EFFORT)).to_have_value("high")
    expect(page.locator(NOTE)).to_have_count(1)
    expect(page.locator(NOTE)).to_contain_text(
        "Changed by a change you approved in a GleepGlorp chat"
    )
    link = page.locator(f"{NOTE} a")
    assert link.evaluate("e => e.tagName") == "A"
    assert (link.get_attribute("href") or "").endswith(_nav.href("chats/sess-approved"))
    # Clean: the stored row is the baseline, so nothing is unsaved, and the key is untouched.
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(KEY)).to_have_value(masked)
    assert page.evaluate("() => window.__same_page") == 1
    # Cancel clears the note.
    page.locator(NAME).fill("Claude two")
    page.locator(CANCEL).click()
    expect(page.locator(NAME)).to_have_value("Claude")
    expect(page.locator(NOTE)).to_have_count(0)


def test_an_unsaved_edit_is_kept_and_a_later_save_sends_the_approved_values(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    pid = _anthropic(base)
    stored_key = _get(base, pid)["api_key"]
    _open_edit(page, base, pid)
    page.locator(NAME).fill("Mine")
    page.locator(EFFORT).select_option("low")
    _approve_row(base, pid, thinking_enabled=True, reasoning_effort="high")
    _signal(page, pid, ["thinking_enabled", "reasoning_effort"])
    expect(page.locator(THINKING)).to_be_checked(timeout=8000)
    # The operator's name and effort stay; the clean thinking toggle follows.
    expect(page.locator(NAME)).to_have_value("Mine")
    expect(page.locator(EFFORT)).to_have_value("low")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(NOTE)).to_have_count(1)
    # Save sends the operator's edits on top of the approved change, never under it.
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    saved = _get(base, pid)
    assert saved["name"] == "Mine"
    assert saved["config"]["thinking_enabled"] is True
    assert saved["config"]["reasoning_effort"] == "low"
    assert saved["api_key"] == stored_key


def test_a_dirty_field_moves_its_baseline_so_cancel_returns_to_the_approved_value(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    pid = _anthropic(base)
    _open_edit(page, base, pid)
    page.locator(EFFORT).select_option("low")
    _approve_row(base, pid, reasoning_effort="high")
    _signal(page, pid, ["reasoning_effort"])
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    expect(page.locator(EFFORT)).to_have_value("low")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    page.locator(CANCEL).click()
    expect(page.locator(EFFORT)).to_have_value("high")
    expect(page.locator(UNSAVED)).to_have_text("")


def test_a_rename_updates_the_title_and_the_delete_button(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    pid = _anthropic(base, "Claude")
    _open_edit(page, base, pid)
    _approve_row(base, pid, name="Claude renamed")
    _signal(page, pid, ["name"])
    expect(page.locator(TITLE)).to_have_text("Claude renamed", timeout=8000)
    expect(page.locator(NAME)).to_have_value("Claude renamed")
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator('[data-testid="delete-provider-btn"]')).to_have_attribute(
        "data-name", "Claude renamed"
    )


def test_an_approval_for_another_provider_or_a_create_changes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _install_counter(page)
    pid = _anthropic(base, "Claude")
    other = _anthropic(base, "Other")
    _open_edit(page, base, pid)
    _approve_row(base, other, reasoning_effort="high")
    _signal(page, other, ["reasoning_effort"])
    page.wait_for_timeout(500)
    expect(page.locator(EFFORT)).to_have_value("")
    expect(page.locator(NOTE)).to_have_count(0)
    # A create form ignores an event for any provider.
    _nav.goto_settled(page, base, "library/providers/~new")
    expect(page.locator(NAME)).to_be_attached(timeout=10000)
    _signal(page, pid, ["name"])
    page.wait_for_timeout(500)
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(NAME)).to_have_value("")


def test_a_save_in_flight_defers_the_follow_until_it_ends(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _install_counter(page)
    pid = _anthropic(base)
    _open_edit(page, base, pid)
    held = _hold_requests(page, f"**/api/providers/{pid}", "PUT")
    page.locator(NAME).fill("Saved name")
    page.locator(SAVE).click()
    _wait_held(page, held, "PUT", f"/api/providers/{pid}")
    _approve_row(base, pid, reasoning_effort="high")
    _signal(page, pid, ["reasoning_effort"])
    page.wait_for_timeout(600)
    # Nothing moved while the Save was in flight.
    expect(page.locator(EFFORT)).to_have_value("")
    expect(page.locator(NOTE)).to_have_count(0)
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    expect(page.locator(EFFORT)).to_have_value(_get(base, pid)["config"]["reasoning_effort"])
    expect(page.locator(UNSAVED)).to_have_text("")


# ── A real approval ──────────────────────────────────────────────────────────


def _approve_proposal(base: str, proposal_id: int) -> httpx.Response:
    return httpx.post(
        f"{base}/api/gleepglorp/proposals/{proposal_id}/approve",
        headers=auth_headers_for(base),
        timeout=10,
    )


def test_a_real_approval_of_an_option_change_reaches_the_open_editor_and_a_save_keeps_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _anthropic(w.base)
    stored_key = _get(w.base, pid)["api_key"]
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="provider",
        agent_name=None,
        target_id=pid,
        changes={"thinking_enabled": True, "reasoning_effort": "high"},
        base={"thinking_enabled": False},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    page.locator(NAME).fill("Mine")
    r = _approve_proposal(w.base, prop)
    assert r.status_code == 200, r.text
    expect(page.locator(THINKING)).to_be_checked(timeout=8000)
    expect(page.locator(EFFORT)).to_have_value("high")
    expect(page.locator(NAME)).to_have_value("Mine")  # the operator's edit is kept
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    # A later Save does not undo the approved change.
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    saved = _get(w.base, pid)
    assert saved["name"] == "Mine" and saved["config"]["thinking_enabled"] is True
    assert saved["config"]["reasoning_effort"] == "high" and saved["api_key"] == stored_key


def test_a_stale_real_approval_is_refused_and_the_editor_does_not_move(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _anthropic(w.base)
    # The seeded base says thinking was on; the stored row says off: the proposal is stale.
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="provider",
        agent_name=None,
        target_id=pid,
        changes={"thinking_enabled": True},
        base={"thinking_enabled": True},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    r = _approve_proposal(w.base, prop)
    assert r.status_code != 200, r.text
    page.wait_for_timeout(500)
    expect(page.locator(THINKING)).not_to_be_checked()
    expect(page.locator(NOTE)).to_have_count(0)
    assert _get(w.base, pid)["config"]["thinking_enabled"] is False


def test_a_type_change_by_approval_remounts_a_clean_editor(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _anthropic(w.base)
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="provider",
        agent_name=None,
        target_id=pid,
        changes={"type": "ollama"},
        base={"type": "anthropic"},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    page.evaluate("() => { window.__same_page = 1; }")
    r = _approve_proposal(w.base, prop)
    assert r.status_code == 200, r.text
    expect(page.locator(TYPE)).to_have_value("ollama", timeout=8000)
    expect(page.locator(NUM_CTX)).to_be_visible()
    expect(page.locator(KEY)).to_be_hidden()
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(NOTE)).to_have_count(1)
    assert page.evaluate("() => window.__same_page") == 1
    assert not _get(w.base, pid)["api_key"]


def test_a_type_change_by_approval_leaves_a_dirty_editor_alone_and_cancel_shows_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _anthropic(w.base)
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="provider",
        agent_name=None,
        target_id=pid,
        changes={"type": "ollama"},
        base={"type": "anthropic"},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    page.locator(NAME).fill("Mine")
    r = _approve_proposal(w.base, prop)
    assert r.status_code == 200, r.text
    expect(page.locator(NOTE)).to_have_text(
        "This provider's type changed; Cancel to see it", timeout=8000
    )
    expect(page.locator(TYPE)).to_have_value("anthropic")
    expect(page.locator(NAME)).to_have_value("Mine")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    page.locator(CANCEL).click()
    expect(page.locator(TYPE)).to_have_value("ollama", timeout=8000)
    expect(page.locator(NAME)).to_have_value("Claude")
    expect(page.locator(UNSAVED)).to_have_text("")


# ── The card ─────────────────────────────────────────────────────────────────


def test_a_provider_card_shows_option_rows_the_warning_and_links_to_the_provider(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    pid = _seed_provider(
        w.base,
        name="Claude",
        type="anthropic",
        api_key="sk-ant-seedkey1234",
        config={"thinking_enabled": False},
    )
    prop = _seed(
        w,
        kind="provider",
        agent_name=None,
        target_id=pid,
        changes={"type": "ollama", "num_ctx": 8192},
        base={"type": "anthropic"},
    )
    _open(page, w)
    card = _card(page, prop)
    table = _in(card, "proposal-table")
    expect(table).to_contain_text("Type")
    expect(table).to_contain_text("Context window")
    expect(table).to_contain_text("8192")
    expect(table).to_contain_text("ollama")
    expect(_in(card, "proposal-warning").first).to_contain_text("The stored key is cleared.")
    _in(card, "proposal-approve").click()
    expect(card).to_have_attribute("data-state", "applied", timeout=8000)
    link = _in(card, "proposal-open-item")
    expect(link).to_have_text("Open model provider")
    expect(link).to_have_attribute("href", _nav.href(f"library/providers/{pid}"))
    stored = _get(w.base, pid)
    assert stored["type"] == "ollama" and stored["config"]["num_ctx"] == 8192
    assert not stored["api_key"]


def test_an_applied_provider_create_links_to_the_new_provider_by_its_applied_id(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    before = {p["id"] for p in _list(w.base)}
    prop = _seed(
        w,
        kind="provider",
        action="create",
        agent_name=None,
        changes={
            "name": "Fresh",
            "type": "ollama",
            "base_url": "http://localhost:11434/v1",
            "num_ctx": 16384,
        },
    )
    _open(page, w)
    card = _card(page, prop)
    expect(_in(card, "proposal-open-item")).to_have_count(0)
    expect(_in(card, "proposal-table")).to_contain_text("Context window")
    _in(card, "proposal-approve").click()
    expect(card).to_have_attribute("data-state", "applied", timeout=8000)
    made = [p for p in _list(w.base) if p["id"] not in before and p["name"] == "Fresh"]
    assert len(made) == 1
    expect(_in(card, "proposal-open-item")).to_have_attribute(
        "href", _nav.href(f"library/providers/{made[0]['id']}")
    )

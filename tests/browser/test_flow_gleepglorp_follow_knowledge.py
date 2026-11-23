"""The knowledge-base edit form follows a change the operator approved in a GleepGlorp chat (M36 F5
L3b, flight DD9 and DD14).

With the form open on base B, approving a ``knowledge_base`` proposal for B lands in it without a
reload: a clean field takes the stored value, a field the operator changed keeps their value while
its baseline moves, the title and subtitle follow, and a quiet note sits under each changed field
(per-field placement, flight DD14). An approval for another base, or with a create form open,
changes nothing, and a Save in flight defers the follow. Most tests signal through
``App.approvals.record`` (the call the approve response makes) after changing the stored row
through its API; one approves a seeded proposal through the route.

Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import _hold_requests, _install_counter, _wait_held
from browser.seeders import seed_gleepglorp_proposal, seed_knowledge_base
from browser.test_flow_agent_editor_follows_approval import _visit_chats
from browser.test_flow_chat_proposals import _world
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NAME = "#kb-name"
DESC = "#kb-description"
SAVE = '[data-testid="save-knowledge-btn"]'
CANCEL = '[data-testid="cancel-knowledge-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="kb-approved-change-note"]'
TITLE = ".editor-title"
_pid = [200]


def _get(base: str, kid: str) -> dict:
    r = httpx.get(f"{base}/api/knowledge-bases/{kid}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _open_edit(page: Page, base: str, kid: str) -> None:
    _nav.goto_settled(page, base, f"library/knowledge/{_nav.seg(kid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    expect(page.locator(UNSAVED)).to_have_text("")


def _approve_row(base: str, kid: str, **fields: str) -> dict:
    """Change the stored row the way an approved proposal does (through the API)."""
    cur = _get(base, kid)
    body = {"name": cur["name"], "description": cur["description"], **fields}
    r = httpx.put(
        f"{base}/api/knowledge-bases/{kid}",
        json=body,
        headers=auth_headers_for(base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _signal(page: Page, kid: str, fields: list[str]) -> None:
    _pid[0] += 1
    page.evaluate(
        "(d) => App.approvals.record(d)",
        {
            "kind": "knowledge_base",
            "target_id": kid,
            "fields": fields,
            "session_id": "sess-approved",
            "proposal_id": _pid[0],
            "at": "2026-01-02T15:05:00+00:00",
        },
    )


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


# ── A clean editor ───────────────────────────────────────────────────────────


def test_an_approved_change_lands_in_a_clean_form_without_a_reload_with_a_note_under_each_field(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    kid = seed_knowledge_base(base, "Docs", "Our docs")
    _open_edit(page, base, kid)
    page.evaluate("() => { window.__same_page = 1; }")
    _approve_row(base, kid, name="Docs renamed", description="Our renamed docs")
    _signal(page, kid, ["name", "description"])
    expect(page.locator(NAME)).to_have_value("Docs renamed", timeout=8000)
    expect(page.locator(DESC)).to_have_value("Our renamed docs")
    expect(page.locator(TITLE)).to_have_text("Docs renamed")
    for field in ("name", "description"):
        expect(page.locator(f'{NOTE}[data-field="{field}"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_contain_text(
        "Changed by a change you approved in a GleepGlorp chat"
    )
    assert _describes(page, NAME, f'{NOTE}[data-field="name"]')
    assert _describes(page, DESC, f'{NOTE}[data-field="description"]')
    link = page.locator(f"{NOTE} a").first
    assert (link.get_attribute("href") or "").endswith(_nav.href("chats/sess-approved"))
    # Clean: the stored row is the baseline, so nothing is unsaved.
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()
    assert page.evaluate("() => window.__same_page") == 1
    # The Library list shows the rename (the store was invalidated and reloaded).
    expect(_lists.list_row(page, "library/knowledge", "Docs renamed")).to_have_count(1)
    # Cancel clears the notes and their links.
    page.locator(NAME).fill("typed")
    page.locator(CANCEL).click()
    expect(page.locator(NAME)).to_have_value("Docs renamed")
    expect(page.locator(NOTE)).to_have_count(0)
    assert page.locator(NAME).get_attribute("aria-describedby") is None


def test_only_the_changed_field_gets_a_note(app_with_data_dir: tuple[str, Any], page: Page) -> None:
    base, _data = app_with_data_dir
    kid = seed_knowledge_base(base, "Docs", "Our docs")
    _open_edit(page, base, kid)
    _approve_row(base, kid, description="Only this")
    _signal(page, kid, ["description"])
    expect(page.locator(DESC)).to_have_value("Only this", timeout=8000)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1)
    expect(page.locator(NOTE)).to_have_count(1)
    expect(page.locator(NAME)).to_have_value("Docs")


# ── A dirty editor ───────────────────────────────────────────────────────────


def test_an_unsaved_edit_is_kept_and_a_later_save_writes_the_operators_value(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    kid = seed_knowledge_base(base, "Docs", "Our docs")
    _open_edit(page, base, kid)
    page.locator(NAME).fill("Mine")
    _approve_row(base, kid, name="Approved name", description="Approved description")
    _signal(page, kid, ["name", "description"])
    expect(page.locator(DESC)).to_have_value("Approved description", timeout=8000)
    # The operator's name stays; the clean description followed.
    expect(page.locator(NAME)).to_have_value("Mine")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(NOTE)).to_have_count(2)
    # The baseline moved: Cancel returns to the approved name, not the old one.
    page.locator(CANCEL).click()
    expect(page.locator(NAME)).to_have_value("Approved name")
    expect(page.locator(UNSAVED)).to_have_text("")
    # And Save writes the operator's value on top of the approved change.
    page.locator(NAME).fill("Mine again")
    page.locator(SAVE).click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=8000)
    saved = _get(base, kid)
    assert saved["name"] == "Mine again" and saved["description"] == "Approved description"


# ── Ignored events ───────────────────────────────────────────────────────────


def test_an_approval_for_another_base_or_with_a_create_form_open_changes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    kid = seed_knowledge_base(base, "Docs", "Our docs")
    other = seed_knowledge_base(base, "Other")
    _open_edit(page, base, kid)
    _approve_row(base, other, description="Elsewhere")
    _signal(page, other, ["description"])
    page.wait_for_timeout(500)
    expect(page.locator(DESC)).to_have_value("Our docs")
    expect(page.locator(NOTE)).to_have_count(0)
    # A create form ignores an event for any base.
    _nav.goto_settled(page, base, "library/knowledge/~new")
    expect(page.locator("#kb-create-name")).to_be_attached(timeout=10000)
    _signal(page, kid, ["name"])
    page.wait_for_timeout(500)
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator("#kb-create-name")).to_have_value("")


# ── A Save in flight ─────────────────────────────────────────────────────────


def test_a_save_in_flight_defers_the_follow_until_it_ends(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _install_counter(page)
    kid = seed_knowledge_base(base, "Docs", "Our docs")
    _open_edit(page, base, kid)
    held = _hold_requests(page, f"**/api/knowledge-bases/{kid}", "PUT")
    page.locator(NAME).fill("Saved name")
    page.locator(SAVE).click()
    _wait_held(page, held, "PUT", f"/api/knowledge-bases/{kid}")
    # The approval arrives while the Save is in flight: nothing moves until the Save ends (the
    # Save's own PUT carries the form's values, so the stored row after it is the Save's).
    _signal(page, kid, ["name"])
    page.wait_for_timeout(600)
    expect(page.locator(NOTE)).to_have_count(0)
    held[0].continue_()
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    expect(page.locator(NAME)).to_have_value("Saved name")
    expect(page.locator(TITLE)).to_have_text("Saved name")
    expect(page.locator(UNSAVED)).to_have_text("")


# ── A real approval ──────────────────────────────────────────────────────────


def test_a_real_approval_of_a_rename_reaches_the_open_form_and_a_save_keeps_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    kid = seed_knowledge_base(w.base, "Docs", "Our docs")
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="knowledge_base",
        agent_name=None,
        target_id=kid,
        changes={"name": "Docs approved"},
        base={"name": "Docs"},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, f"library/knowledge/{_nav.seg(kid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    page.locator(DESC).fill("Mine")
    r = httpx.post(
        f"{w.base}/api/gleepglorp/proposals/{prop}/approve",
        headers=auth_headers_for(w.base),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    expect(page.locator(NAME)).to_have_value("Docs approved", timeout=8000)
    expect(page.locator(DESC)).to_have_value("Mine")  # the operator's edit is kept
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(1, timeout=8000)
    page.locator(SAVE).click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=8000)
    saved = _get(w.base, kid)
    assert saved["name"] == "Docs approved" and saved["description"] == "Mine"

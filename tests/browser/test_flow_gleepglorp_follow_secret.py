"""The secret editor follows a change the operator approved in a GleepGlorp chat (M36 F5 L3b, flight
DD9 and DD14).

With the editor open on secret S, approving a ``secret`` proposal for S lands in it without a
reload: a clean field takes the stored value, a field the operator changed keeps their value while
its baseline moves, and a quiet note sits under each changed field (per-field placement, flight
DD14). Only the METADATA follows (name, description, allowed tools): the values table is never
rebased or re-read, so a value row being edited is untouched. The Library list and the router's
name follow a rename; an approval for another secret, or with a create form open, changes nothing;
a Save in flight defers the follow. Most tests signal through ``App.approvals.record`` after
changing the stored row through its API; one approves a seeded proposal through the route.

Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import _hold_requests, _install_counter, _wait_held
from browser.seeders import seed_gleepglorp_proposal, seed_secret
from browser.test_flow_agent_editor_follows_approval import _visit_chats
from browser.test_flow_chat_proposals import _world
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NAME = "#secret-name"
DESC = "#secret-description"
TOOLS = "#secret-allowed-tools"
KEYS = '[data-testid="secret-key-input"]'
VALUES = '[data-testid="secret-value-input"]'
SAVE = '[data-testid="save-secret-btn"]'
CANCEL = '[data-testid="cancel-secret-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="secret-approved-change-note"]'
TITLE = ".editor-title"
_pid = [300]


def _get(base: str, sid: str) -> dict:
    r = httpx.get(f"{base}/api/secrets/{sid}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _seed(base: str, name: str = "Api access", **kw: Any) -> str:
    return seed_secret(
        base,
        name,
        values=[("token", "tok-seed-1111"), ("other_key", "oth-seed-2222")],
        allowed_tools=kw.pop("allowed_tools", ["shell"]),
        **kw,
    )


def _open_edit(page: Page, base: str, sid: str) -> None:
    _nav.goto_settled(page, base, f"library/secrets/{_nav.seg(sid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    expect(page.locator(UNSAVED)).to_have_text("")


def _approve_row(base: str, sid: str, **meta: Any) -> dict:
    """Change the stored metadata the way an approved proposal does (through the API); every
    stored value goes back masked, so the ciphertext is kept."""
    cur = _get(base, sid)
    body = {
        "name": meta.get("name", cur["name"]),
        "description": meta.get("description", cur["description"]),
        "values": [{"id": v["id"], "key": v["key"], "value": "__MASKED__"} for v in cur["values"]],
        "allowed_tools": meta.get("allowed_tools", cur["allowed_tools"]),
    }
    r = httpx.put(
        f"{base}/api/secrets/{sid}", json=body, headers=auth_headers_for(base), timeout=5.0
    )
    assert r.status_code == 200, r.text
    return r.json()


def _signal(page: Page, sid: str, fields: list[str]) -> None:
    _pid[0] += 1
    page.evaluate(
        "(d) => App.approvals.record(d)",
        {
            "kind": "secret",
            "target_id": sid,
            "fields": fields,
            "session_id": "sess-approved",
            "proposal_id": _pid[0],
            "at": "2026-01-02T15:05:00+00:00",
        },
    )


def _chips(page: Page) -> list[str]:
    return page.evaluate(
        "() => App.ui.chipList.valuesOf("
        "document.querySelector('[data-testid=\"secret-allowed-tools\"]'))"
    )


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


# ── A clean editor ───────────────────────────────────────────────────────────


def test_an_approved_change_lands_in_a_clean_editor_without_a_reload_with_notes(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base, description="Old description")
    _open_edit(page, base, sid)
    page.evaluate("() => { window.__same_page = 1; }")
    _approve_row(
        base,
        sid,
        name="Api renamed",
        description="New description",
        allowed_tools=["shell", "fetch_url"],
    )
    _signal(page, sid, ["name", "description", "allowed_tools"])
    expect(page.locator(NAME)).to_have_value("Api renamed", timeout=8000)
    expect(page.locator(DESC)).to_have_value("New description")
    assert _chips(page) == ["shell", "fetch_url"]
    expect(page.locator(TITLE)).to_have_text("Api renamed")
    for field in ("name", "description", "allowed_tools"):
        expect(page.locator(f'{NOTE}[data-field="{field}"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_contain_text(
        "Changed by a change you approved in a GleepGlorp chat"
    )
    assert _describes(page, NAME, f'{NOTE}[data-field="name"]')
    assert _describes(page, DESC, f'{NOTE}[data-field="description"]')
    assert _describes(page, TOOLS, f'{NOTE}[data-field="allowed_tools"]')
    link = page.locator(f"{NOTE} a").first
    assert (link.get_attribute("href") or "").endswith(_nav.href("chats/sess-approved"))
    # Clean: the stored row is the baseline.
    expect(page.locator(UNSAVED)).to_have_text("")
    assert page.evaluate("() => window.__same_page") == 1
    # The Library list shows the rename, and the router's name followed.
    expect(_lists.list_row(page, "library/secrets", "Api renamed")).to_have_count(1)
    # document.title is router-owned: it names the item only through sync(..., {name}).
    assert page.title().endswith(" — Api renamed · GleepGlorp AI"), page.title()
    # Cancel clears the notes and their links.
    page.locator(NAME).fill("typed")
    page.locator(CANCEL).click()
    expect(page.locator(NAME)).to_have_value("Api renamed")
    expect(page.locator(NOTE)).to_have_count(0)
    assert page.locator(NAME).get_attribute("aria-describedby") is None


def test_the_values_table_is_never_rebased_or_re_read(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base)
    _open_edit(page, base, sid)
    # A value row being edited: the operator types a new value into row 1.
    page.locator(VALUES).nth(1).fill("typed-new-value")
    keys_before = page.locator(KEYS).evaluate_all("els => els.map(e => e.value)")
    _approve_row(base, sid, description="Approved description")
    _signal(page, sid, ["description"])
    expect(page.locator(DESC)).to_have_value("Approved description", timeout=8000)
    expect(page.locator(NOTE)).to_have_count(1)
    expect(page.locator(VALUES).nth(0)).to_have_value("__MASKED__")
    expect(page.locator(VALUES).nth(1)).to_have_value("typed-new-value")
    assert page.locator(KEYS).evaluate_all("els => els.map(e => e.value)") == keys_before
    # Still dirty through the typed value alone.
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")


# ── A dirty editor ───────────────────────────────────────────────────────────


def test_an_unsaved_edit_is_kept_and_a_later_save_writes_the_operators_value(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base, description="Old description")
    _open_edit(page, base, sid)
    page.locator(NAME).fill("Mine")
    _approve_row(
        base,
        sid,
        name="Approved name",
        description="Approved description",
        allowed_tools=["shell", "fetch_url"],
    )
    _signal(page, sid, ["name", "description", "allowed_tools"])
    expect(page.locator(DESC)).to_have_value("Approved description", timeout=8000)
    expect(page.locator(NAME)).to_have_value("Mine")  # the operator's name stays
    assert _chips(page) == ["shell", "fetch_url"]  # the clean chips followed
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(NOTE)).to_have_count(3)
    # The baseline moved: Cancel returns to the approved name, not the old one.
    page.locator(CANCEL).click()
    expect(page.locator(NAME)).to_have_value("Approved name")
    expect(page.locator(UNSAVED)).to_have_text("")
    assert _chips(page) == ["shell", "fetch_url"]
    # And Save writes the operator's value on top of the approved change.
    page.locator(NAME).fill("Mine again")
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    saved = _get(base, sid)
    assert saved["name"] == "Mine again" and saved["description"] == "Approved description"
    assert saved["allowed_tools"] == ["shell", "fetch_url"]
    assert [v["key"] for v in saved["values"]] == ["token", "other_key"]


# ── Ignored events ───────────────────────────────────────────────────────────


def test_an_approval_for_another_secret_or_with_a_create_form_open_changes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base, description="Mine")
    other = seed_secret(base, "Other one")
    _open_edit(page, base, sid)
    _approve_row(base, other, description="Elsewhere")
    _signal(page, other, ["description"])
    page.wait_for_timeout(500)
    expect(page.locator(DESC)).to_have_value("Mine")
    expect(page.locator(NOTE)).to_have_count(0)
    # A create form ignores an event for any secret.
    _nav.goto_settled(page, base, "library/secrets/~new")
    expect(page.locator(NAME)).to_be_attached(timeout=10000)
    _signal(page, sid, ["name"])
    page.wait_for_timeout(500)
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(NAME)).to_have_value("")


# ── A Save in flight ─────────────────────────────────────────────────────────


def test_a_save_in_flight_defers_the_follow_until_it_ends(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _install_counter(page)
    sid = _seed(base, description="Old description")
    _open_edit(page, base, sid)
    held = _hold_requests(page, f"**/api/secrets/{sid}", "PUT")
    page.locator(NAME).fill("Saved name")
    page.locator(SAVE).click()
    _wait_held(page, held, "PUT", f"/api/secrets/{sid}")
    _signal(page, sid, ["name"])
    page.wait_for_timeout(600)
    expect(page.locator(NOTE)).to_have_count(0)
    held[0].continue_()
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    expect(page.locator(NAME)).to_have_value("Saved name")
    expect(page.locator(TITLE)).to_have_text("Saved name")
    expect(page.locator(UNSAVED)).to_have_text("")


# ── A real approval ──────────────────────────────────────────────────────────


def test_a_real_approval_of_a_rename_reaches_the_open_editor_and_a_save_keeps_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    sid = _seed(w.base, "Api access", description="Old description")
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="secret",
        agent_name=None,
        target_id=sid,
        changes={"name": "Api approved"},
        base={"name": "Api access"},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, f"library/secrets/{_nav.seg(sid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    page.locator(DESC).fill("Mine")
    r = httpx.post(
        f"{w.base}/api/gleepglorp/proposals/{prop}/approve",
        headers=auth_headers_for(w.base),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    expect(page.locator(NAME)).to_have_value("Api approved", timeout=8000)
    expect(page.locator(DESC)).to_have_value("Mine")  # the operator's edit is kept
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(1, timeout=8000)
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    saved = _get(w.base, sid)
    assert saved["name"] == "Api approved" and saved["description"] == "Mine"
    assert [v["key"] for v in saved["values"]] == ["token", "other_key"]

"""GleepGlorp fills the secret editor (M36 F5 L3b, flight DD6, DD13 and DD14).

A fill writes unsaved edits into the Library's secret create form or an existing secret's edit
form: its name, description and allowed tools, each with a quiet note (one note under the chips
names the tools added). A fill NEVER writes a value: the value is the operator's, and a create fill
says so in a note under the values table ("Enter the value for {key}, then Create."), which follows
row 0 live. A create fill lets row 0's key follow the filled name, as typing does. Masked values
and the key table of an existing secret are never touched. Covers, as state transitions:

* [create form] -> [filled: name, description, tools] -> [value typed, note gone] -> [created]
  (AC5);
* [edit form] -> [filled] -> Cancel / Save: the masked rows are untouched (AC6);
* a field the operator changed is kept, on the same route; another route asks the leave guard,
  and Stay writes nothing (AC6);
* a key the operator typed is not replaced by the name's slug;
* a fill that arrives while a Save is in flight waits for it.

Seeds the fills straight into the database and delivers each real view into the drawer's socket,
as ``test_flow_gleepglorp_fill.py`` does. Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _drawer, _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import _count, _hold_requests, _install_counter, _wait_held
from browser.seeders import seed_secret
from browser.test_flow_gleepglorp_fill import (
    _bworld,
    _deliver,
    _done,
    _drawer_receipt,
    _seed_b,
    _wait_status,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NAME = "#secret-name"
DESC = "#secret-description"
TOOLS = "#secret-allowed-tools"
KEYS = '[data-testid="secret-key-input"]'
VALUES = '[data-testid="secret-value-input"]'
UNSAVED = '[data-testid="editor-unsaved"]'
SAVE = '[data-testid="save-secret-btn"]'
CANCEL = '[data-testid="cancel-secret-btn"]'
NOTE = '[data-testid="secret-filled-note"]'
TABLE_NOTE = f'{NOTE}[data-field="values"]'
TOOLS_NOTE = f'{NOTE}[data-field="allowed_tools"]'
KEPT = '[data-testid="fill-receipt-kept"]'
COMPOSER = '[data-testid="gg-chat-input"]'
MASK = "__MASKED__"


def _world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    return _bworld(app_with_data_dir, page, route="library")


def _fill(w: SimpleNamespace, action: str, changes: dict, **kw: Any) -> int:
    return _seed_b(w, kind="secret", action=action, agent_name=None, changes=changes, **kw)


def _secrets(base: str) -> list[dict]:
    r = httpx.get(f"{base}/api/secrets", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _get(base: str, sid: str) -> dict:
    r = httpx.get(f"{base}/api/secrets/{sid}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _open_edit(page: Page, sid: str) -> None:
    _nav.set_route(page, f"library/secrets/{_nav.seg(sid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)


def _chips(page: Page) -> list[str]:
    return page.evaluate(
        "() => App.ui.chipList.valuesOf("
        "document.querySelector('[data-testid=\"secret-allowed-tools\"]'))"
    )


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


def _seed_two(base: str, name: str = "Api access", **kw: Any) -> str:
    return seed_secret(
        base,
        name,
        values=[("token", "tok-seed-1111"), ("other_key", "oth-seed-2222")],
        allowed_tools=["shell"],
        **kw,
    )


# ── AC5: a create fill ───────────────────────────────────────────────────────


def test_a_create_fill_writes_the_metadata_follows_the_key_and_hands_off_the_value(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    before = _secrets(w.base)
    page.locator(COMPOSER).focus()
    fid = _fill(
        w,
        "create",
        {
            "name": "GitHub token",
            "description": "Personal access token",
            "allowed_tools": ["fetch_url", "http_request"],
        },
    )
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("GitHub token", timeout=10000)
    expect(page.locator(DESC)).to_have_value("Personal access token")
    assert _chips(page) == ["fetch_url", "http_request"]
    _nav.expect_route(page, "library/secrets/~new")
    # Row 0's key followed the filled name's slug, as typing does.
    expect(page.locator(KEYS).first).to_have_value("github_token")
    # No value input was written.
    expect(page.locator(VALUES)).to_have_count(1)
    expect(page.locator(VALUES).first).to_have_value("")
    # The notes: one per written field, the chips note naming the tools, the handoff note.
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1)
    expect(page.locator(TOOLS_NOTE)).to_have_text(
        "Filled by GleepGlorp: added fetch_url, http_request."
    )
    expect(page.locator(TABLE_NOTE)).to_have_text("Enter the value for github_token, then Create.")
    assert _describes(page, NAME, f'{NOTE}[data-field="name"]')
    assert _describes(page, DESC, f'{NOTE}[data-field="description"]')
    assert _describes(page, TOOLS, TOOLS_NOTE)
    assert _describes(page, VALUES, TABLE_NOTE)
    expect(page.locator(f"{NOTE}[role], {NOTE} [aria-live]")).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _secrets(w.base) == before  # nothing is stored until Create
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    page.wait_for_timeout(300)
    expect(page.locator(COMPOSER)).to_be_focused()
    _done(page)
    expect(_drawer_receipt(page, fid)).to_have_attribute("data-status", "filled")
    # The operator types the value: the handoff note goes; then Create stores what the form said.
    page.locator(VALUES).first.fill("ghp-typed-by-the-operator")
    expect(page.locator(TABLE_NOTE)).to_have_count(0)
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    made = [s for s in _secrets(w.base) if s["name"] == "GitHub token"]
    assert len(made) == 1
    stored = _get(w.base, made[0]["id"])
    assert stored["allowed_tools"] == ["fetch_url", "http_request"]
    assert [v["key"] for v in stored["values"]] == ["github_token"]


def test_a_key_the_operator_typed_is_not_replaced_by_the_names_slug(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _nav.set_route(page, "library/secrets/~new")
    expect(page.locator(KEYS).first).to_be_visible(timeout=10000)
    page.locator(KEYS).first.fill("my_own_key")
    fid = _fill(w, "create", {"name": "Some name", "allowed_tools": ["shell"]})
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("Some name", timeout=10000)
    expect(page.locator(KEYS).first).to_have_value("my_own_key")
    expect(page.locator(TABLE_NOTE)).to_have_text("Enter the value for my_own_key, then Create.")
    _wait_status(page, w, fid, "filled")


def test_a_name_with_no_slug_characters_hands_off_a_key_and_value(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    fid = _fill(w, "create", {"name": "!!!", "allowed_tools": ["shell"]})
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("!!!", timeout=10000)
    expect(page.locator(KEYS).first).to_have_value("")
    expect(page.locator(TABLE_NOTE)).to_have_text("Enter a key and value, then Create.")
    # Typing a key moves the note's wording with it.
    page.locator(KEYS).first.fill("api_key")
    expect(page.locator(TABLE_NOTE)).to_have_text("Enter the value for api_key, then Create.")
    _wait_status(page, w, fid, "filled")


# ── AC6: a change fill ───────────────────────────────────────────────────────


def test_a_change_fill_writes_the_metadata_names_the_added_tools_and_leaves_the_values_alone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    sid = _seed_two(w.base, description="Old description")
    _open_edit(page, sid)
    keys_before = page.locator(KEYS).evaluate_all("els => els.map(e => e.value)")
    values_before = page.locator(VALUES).evaluate_all("els => els.map(e => e.value)")
    assert keys_before == ["token", "other_key"] and values_before == [MASK, MASK]
    fid = _fill(
        w,
        "change",
        {
            "name": "Api renamed",
            "description": "New description",
            "allowed_tools": ["shell", "fetch_url"],
        },
        target_id=sid,
        base={"name": "Api access", "description": "Old description", "allowed_tools": ["shell"]},
    )
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("Api renamed", timeout=10000)
    expect(page.locator(DESC)).to_have_value("New description")
    assert _chips(page) == ["shell", "fetch_url"]
    # The chips note names only what was added against the saved list.
    expect(page.locator(TOOLS_NOTE)).to_have_text("Filled by GleepGlorp: added fetch_url.")
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(1)
    expect(page.locator(TABLE_NOTE)).to_have_count(0)  # a change fill hands off nothing
    # The key table and every masked value are untouched.
    assert page.locator(KEYS).evaluate_all("els => els.map(e => e.value)") == keys_before
    assert page.locator(VALUES).evaluate_all("els => els.map(e => e.value)") == values_before
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _get(w.base, sid)["name"] == "Api access"
    assert _wait_status(page, w, fid, "filled")["outcome"] == {"kept": [], "reason": None}
    # Cancel restores everything and clears the notes.
    page.locator(CANCEL).click()
    expect(page.locator(NAME)).to_have_value("Api access")
    assert _chips(page) == ["shell"]
    expect(page.locator(NOTE)).to_have_count(0)
    assert page.locator(VALUES).evaluate_all("els => els.map(e => e.value)") == values_before
    # A second fill then Save: the metadata is stored and the values are exactly as they were.
    fid2 = _fill(
        w,
        "change",
        {"description": "Saved description", "allowed_tools": ["fetch_url"]},
        target_id=sid,
        base={"description": "Old description", "allowed_tools": ["shell"]},
        tool_call_id="tc-2",
    )
    _deliver(page, w, fid2)
    expect(page.locator(DESC)).to_have_value("Saved description", timeout=10000)
    # A replaced list: shell is gone, fetch_url is the one added against the saved list.
    assert _chips(page) == ["fetch_url"]
    expect(page.locator(TOOLS_NOTE)).to_have_text("Filled by GleepGlorp: added fetch_url.")
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    saved = _get(w.base, sid)
    assert saved["description"] == "Saved description" and saved["allowed_tools"] == ["fetch_url"]
    assert [v["key"] for v in saved["values"]] == ["token", "other_key"]
    expect(page.locator(NOTE)).to_have_count(0)


def test_a_fill_that_only_removes_tools_writes_the_list_without_a_chips_note(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    sid = seed_secret(w.base, "Two tools", allowed_tools=["shell", "fetch_url"])
    _open_edit(page, sid)
    fid = _fill(
        w,
        "change",
        {"allowed_tools": ["shell"]},
        target_id=sid,
        base={"allowed_tools": ["shell", "fetch_url"]},
    )
    _deliver(page, w, fid)
    _wait_status(page, w, fid, "filled")
    assert _chips(page) == ["shell"]
    expect(page.locator(TOOLS_NOTE)).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")


def test_a_field_the_operator_changed_is_kept_on_the_same_route(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    sid = _seed_two(w.base, description="Original description")
    _open_edit(page, sid)
    page.locator(NAME).fill("Mine")
    page.locator(TOOLS).click()
    page.locator(TOOLS).fill("grep")
    page.keyboard.press("Enter")
    fid = _fill(
        w,
        "change",
        {
            "name": "Gg name",
            "description": "Gg description",
            "allowed_tools": ["shell", "fetch_url"],
        },
        target_id=sid,
        base={
            "name": "Api access",
            "description": "Original description",
            "allowed_tools": ["shell"],
        },
    )
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["name", "allowed_tools"], "reason": None}
    expect(page.locator(NAME)).to_have_value("Mine")
    expect(page.locator(DESC)).to_have_value("Gg description")
    assert _chips(page) == ["shell", "grep"]  # the operator's list, not the fill's
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(0)
    expect(page.locator(TOOLS_NOTE)).to_have_count(0)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1)
    _done(page)
    expect(_drawer_receipt(page, fid).locator(KEPT)).to_contain_text("Name")
    assert _get(w.base, sid)["name"] == "Api access"


def test_a_dirty_editor_on_another_secret_asks_the_guard_and_stay_writes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    first = seed_secret(w.base, "First one")
    second = seed_secret(w.base, "Second one")
    _open_edit(page, first)
    page.locator(NAME).fill("typed by me")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    fid = _fill(w, "change", {"description": "Never"}, target_id=second, base={})
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    expect(page.locator(NAME)).to_have_value("typed by me")
    _done(page)
    expect(_drawer_receipt(page, fid)).to_contain_text(
        "You chose to stay on the page you were editing."
    )
    assert _get(w.base, second)["description"] == ""


def test_a_fill_that_arrives_during_a_save_waits_for_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    _install_counter(page)
    w = _world(app_with_data_dir, page)
    sid = seed_secret(w.base, "Before", description="Before description")
    _open_edit(page, sid)
    held = _hold_requests(page, f"**/api/secrets/{sid}", "PUT")
    page.locator(NAME).fill("Saved name")
    page.locator(SAVE).click()
    _wait_held(page, held, "PUT", f"/api/secrets/{sid}")
    fid = _fill(
        w,
        "change",
        {"description": "Filled after"},
        target_id=sid,
        base={"description": "Before description"},
    )
    _deliver(page, w, fid)
    page.wait_for_timeout(600)
    expect(page.locator(DESC)).to_have_value("Before description")  # nothing written yet
    held[0].continue_()
    expect(page.locator(DESC)).to_have_value("Filled after", timeout=10000)
    _wait_status(page, w, fid, "filled")
    saved = _get(w.base, sid)
    assert saved["name"] == "Saved name" and saved["description"] == "Before description"
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _count(page, "PUT", f"/api/secrets/{sid}") == 1


def test_a_value_in_the_fills_values_is_ignored_and_never_written(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    fid = _fill(
        w,
        "create",
        {"name": "Sneaky", "allowed_tools": ["shell"], "values": [{"key": "k", "value": "v-x"}]},
    )
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("Sneaky", timeout=10000)
    expect(page.locator(VALUES).first).to_have_value("")
    assert "v-x" not in page.content()
    _wait_status(page, w, fid, "filled")

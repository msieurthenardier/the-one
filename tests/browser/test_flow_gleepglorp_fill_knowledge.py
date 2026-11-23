"""GleepGlorp fills the knowledge-base editor (M36 F5 L3b, flight DD5, DD6, DD13 and DD14).

A fill writes unsaved edits into the Library's knowledge-base create form or an existing base's
edit form: its name and description, each with a quiet per-field note. A create fill leaves focus
in the drawer composer (the create form's own name focus is suppressed for that one navigation).
Folders, files and indexing are never part of a fill. Covers, as state transitions:

* [create form] -> [filled] -> [created]: nothing is stored until Create (AC2);
* [edit form] -> [filled] -> Cancel / Save (AC3);
* a field the operator changed is kept, on the same route; another route asks the leave guard,
  and Stay writes nothing (AC3);
* a fill that arrives while a Save is in flight waits for it;
* the Add menu still focuses the name after a fill.

Seeds the fills straight into the database and delivers each real view into the drawer's socket,
as ``test_flow_gleepglorp_fill.py`` does. Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _drawer, _lists, _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import _count, _hold_requests, _install_counter, _wait_held
from browser.seeders import seed_knowledge_base
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

CNAME = "#kb-create-name"
CDESC = "#kb-create-description"
ENAME = "#kb-name"
EDESC = "#kb-description"
UNSAVED = '[data-testid="editor-unsaved"]'
CREATE = '[data-testid="kb-create-submit-btn"]'
CCANCEL = '[data-testid="kb-create-cancel-btn"]'
SAVE = '[data-testid="save-knowledge-btn"]'
CANCEL = '[data-testid="cancel-knowledge-btn"]'
NOTE = '[data-testid="kb-filled-note"]'
KEPT = '[data-testid="fill-receipt-kept"]'
COMPOSER = '[data-testid="gg-chat-input"]'
TITLE = ".editor-title"


def _world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    return _bworld(app_with_data_dir, page, route="library")


def _fill(w: SimpleNamespace, action: str, changes: dict, **kw: Any) -> int:
    return _seed_b(w, kind="knowledge_base", action=action, agent_name=None, changes=changes, **kw)


def _bases(base: str) -> list[dict]:
    r = httpx.get(f"{base}/api/knowledge-bases", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _get(base: str, kid: str) -> dict:
    r = httpx.get(f"{base}/api/knowledge-bases/{kid}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _open_edit(page: Page, kid: str) -> None:
    _nav.set_route(page, f"library/knowledge/{_nav.seg(kid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


# ── AC2: a create fill ───────────────────────────────────────────────────────


def test_a_create_fill_writes_the_name_and_description_notes_them_and_keeps_focus_in_the_drawer(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    before = _bases(w.base)
    page.locator(COMPOSER).focus()
    fid = _fill(w, "create", {"name": "Field notes", "description": "Notes from the field"})
    _deliver(page, w, fid)
    expect(page.locator(CNAME)).to_have_value("Field notes", timeout=10000)
    expect(page.locator(CDESC)).to_have_value("Notes from the field")
    _nav.expect_route(page, "library/knowledge/~new")
    for field in ("name", "description"):
        expect(page.locator(f'{NOTE}[data-field="{field}"]')).to_have_count(1)
    assert _describes(page, CNAME, f'{NOTE}[data-field="name"]')
    assert _describes(page, CDESC, f'{NOTE}[data-field="description"]')
    expect(page.locator(f"{NOTE}[role], {NOTE} [aria-live]")).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _bases(w.base) == before  # nothing is stored until Create
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    page.wait_for_timeout(400)
    expect(page.locator(COMPOSER)).to_be_focused()  # the name focus was suppressed
    _done(page)
    expect(_drawer_receipt(page, fid)).to_have_attribute("data-status", "filled")
    # The operator creates it: the stored row is what the form said.
    page.locator(CREATE).click()
    page.wait_for_function("() => App.router.current().route.indexOf('~new') === -1", timeout=10000)
    made = [b for b in _bases(w.base) if b["name"] == "Field notes"]
    assert len(made) == 1 and made[0]["description"] == "Notes from the field"


def test_the_add_menu_still_focuses_the_name_after_a_fill_navigation(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    page.locator(COMPOSER).focus()
    fid = _fill(w, "create", {"name": "Made by fill"})
    _deliver(page, w, fid)
    expect(page.locator(CNAME)).to_have_value("Made by fill", timeout=10000)
    _wait_status(page, w, fid, "filled")
    page.wait_for_timeout(300)
    expect(page.locator(COMPOSER)).to_be_focused()
    # Leave the form clean, then an ordinary Add: the suppression did not leak.
    page.locator(CNAME).fill("")
    page.locator(CCANCEL).click()
    _lists.library_add(page, "knowledge")
    expect(page.locator(CNAME)).to_be_focused(timeout=8000)


def test_a_create_fill_that_stayed_does_not_leak_the_suppression_to_the_next_add(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    kid = seed_knowledge_base(w.base, "Dirty one")
    _open_edit(page, kid)
    page.locator(ENAME).fill("typed by me")
    fid = _fill(w, "create", {"name": "Never written"})
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    assert _wait_status(page, w, fid, "not_filled")["outcome"]["reason"] == "stay"
    page.locator(CANCEL).click()
    _lists.library_add(page, "knowledge")
    expect(page.locator(CNAME)).to_be_focused(timeout=8000)


# ── AC3: a change fill ───────────────────────────────────────────────────────


def test_a_change_fill_writes_only_the_named_fields_with_notes_and_cancel_restores(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    kid = seed_knowledge_base(w.base, "Old name", "Old description")
    _open_edit(page, kid)
    fid = _fill(w, "change", {"name": "New name"}, target_id=kid, base={"name": "Old name"})
    _deliver(page, w, fid)
    expect(page.locator(ENAME)).to_have_value("New name", timeout=10000)
    expect(page.locator(EDESC)).to_have_value("Old description")  # not named: untouched
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(0)
    assert _describes(page, ENAME, f'{NOTE}[data-field="name"]')
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _get(w.base, kid)["name"] == "Old name"
    assert _wait_status(page, w, fid, "filled")["outcome"] == {"kept": [], "reason": None}
    page.locator(CANCEL).click()
    expect(page.locator(ENAME)).to_have_value("Old name")
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("")
    # A second fill, then Save: the stored row is what the form said, and the notes go.
    fid2 = _fill(
        w,
        "change",
        {"name": "New name", "description": "New description"},
        target_id=kid,
        base={"name": "Old name", "description": "Old description"},
        tool_call_id="tc-2",
    )
    _deliver(page, w, fid2)
    expect(page.locator(EDESC)).to_have_value("New description", timeout=10000)
    expect(page.locator(NOTE)).to_have_count(2)
    page.locator(SAVE).click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=8000)
    saved = _get(w.base, kid)
    assert saved["name"] == "New name" and saved["description"] == "New description"
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(TITLE)).to_have_text("New name")


def test_a_field_the_operator_changed_is_kept_on_the_same_route(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    kid = seed_knowledge_base(w.base, "Original", "Original description")
    _open_edit(page, kid)
    page.locator(ENAME).fill("Mine")
    fid = _fill(
        w,
        "change",
        {"name": "Gg name", "description": "Gg description"},
        target_id=kid,
        base={"name": "Original", "description": "Original description"},
    )
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["name"], "reason": None}
    expect(page.locator(ENAME)).to_have_value("Mine")
    expect(page.locator(EDESC)).to_have_value("Gg description")
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(0)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1)
    _done(page)
    expect(_drawer_receipt(page, fid).locator(KEPT)).to_contain_text("Name")
    assert _get(w.base, kid)["name"] == "Original"


def test_a_dirty_editor_on_another_base_asks_the_guard_and_stay_writes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    first = seed_knowledge_base(w.base, "First")
    second = seed_knowledge_base(w.base, "Second")
    _open_edit(page, first)
    page.locator(ENAME).fill("typed by me")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    fid = _fill(w, "change", {"description": "Never"}, target_id=second, base={})
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    expect(page.locator(ENAME)).to_have_value("typed by me")
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
    kid = seed_knowledge_base(w.base, "Before", "Before description")
    _open_edit(page, kid)
    held = _hold_requests(page, f"**/api/knowledge-bases/{kid}", "PUT")
    page.locator(ENAME).fill("Saved name")
    page.locator(SAVE).click()
    _wait_held(page, held, "PUT", f"/api/knowledge-bases/{kid}")
    fid = _fill(
        w,
        "change",
        {"description": "Filled after"},
        target_id=kid,
        base={"description": "Before description"},
    )
    _deliver(page, w, fid)
    page.wait_for_timeout(600)
    # Nothing was written while the Save was in flight.
    expect(page.locator(EDESC)).to_have_value("Before description")
    assert _get(w.base, kid)["name"] == "Before"
    held[0].continue_()
    expect(page.locator(EDESC)).to_have_value("Filled after", timeout=10000)
    _wait_status(page, w, fid, "filled")
    assert _get(w.base, kid)["name"] == "Saved name"
    assert _get(w.base, kid)["description"] == "Before description"  # the fill is unsaved
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _count(page, "PUT", f"/api/knowledge-bases/{kid}") == 1


def test_a_change_fill_for_a_deleted_base_is_target_gone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    kid = seed_knowledge_base(w.base, "Short lived")
    fid = _fill(w, "change", {"name": "Fresh"}, target_id=kid, base={})
    r = httpx.delete(
        f"{w.base}/api/knowledge-bases/{kid}", headers=auth_headers_for(w.base), timeout=5.0
    )
    assert r.status_code in (200, 204), r.text
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "target_gone"}
    _done(page)
    expect(_drawer_receipt(page, fid)).to_contain_text("no longer exists")

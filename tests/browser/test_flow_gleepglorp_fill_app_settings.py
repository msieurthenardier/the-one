"""GleepGlorp fills the Knowledge indexing page (M36 F5 L4b, flight DD8, DD13 and DD14).

An ``app_settings`` fill for ``knowledge-indexing`` writes the chunk size, chunk overlap, watch
switch and reconciliation interval into the open page (``#settings/knowledge-indexing``) as UNSAVED
edits, each with a quiet note linked through ``aria-describedby``. The page revalidates after each
write (an overlap above half the size shows its own error and disables Save) and stays dirty under
the ``admin`` leave guard. Date and time is never fillable (the server refuses it), so no test
fills it. Covers, as state transitions:

* [library] -> [page filled]: the fill navigates, writes the named fields, leaves the page dirty
  with its unsaved caption and focus in the drawer composer (AC6);
* [overlap above half the size] -> the page's own error and a disabled Save;
* a field the operator changed is kept; another route asks the leave guard and Stay writes nothing;
* a page whose first load failed is ``editor_unavailable`` at once (no ten second wait).

Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _drawer, _nav
from browser._credential_registry import auth_headers_for
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

SIZE = '[data-testid="knowledge-size-chars-input"]'
OVERLAP = '[data-testid="knowledge-overlap-chars-input"]'
INTERVAL = '[data-testid="knowledge-reconcile-interval-input"]'
WATCH = '[data-testid="knowledge-watch-enabled-toggle"]'
SAVE = '[data-testid="knowledge-settings-save-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="knowledge-settings-filled-note"]'
COMPOSER = '[data-testid="gg-chat-input"]'
KEPT = '[data-testid="fill-receipt-kept"]'


def _world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    return _bworld(app_with_data_dir, page, route="library")


def _fill(w: SimpleNamespace, changes: dict, **kw: Any) -> int:
    return _seed_b(
        w, kind="app_settings", action="change", agent_name=None,
        target_id="knowledge-indexing", changes=changes, **kw,
    )  # fmt: skip


def _stored(base: str) -> dict:
    r = httpx.get(f"{base}/api/knowledge-settings", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _open(page: Page) -> None:
    _nav.set_route(page, "settings/knowledge-indexing")
    expect(page.locator(SIZE)).not_to_have_value("", timeout=10000)


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


def test_a_fill_opens_the_page_writes_all_four_fields_and_leaves_it_dirty(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    before = _stored(w.base)
    watch = not before["monitoring"]["watch_enabled"]
    page.locator(COMPOSER).focus()
    fid = _fill(
        w,
        {
            "chunk_size_chars": 800,
            "chunk_overlap_chars": 100,
            "watch_enabled": watch,
            "reconcile_interval_seconds": 120,
        },
    )
    _deliver(page, w, fid)
    expect(page.locator(SIZE)).to_have_value("800", timeout=10000)
    _nav.expect_route(page, "settings/knowledge-indexing")
    expect(page.locator(OVERLAP)).to_have_value("100")
    expect(page.locator(INTERVAL)).to_have_value("120")
    assert page.locator(WATCH).is_checked() == watch
    for field, control in (
        ("chunk_size_chars", SIZE),
        ("chunk_overlap_chars", OVERLAP),
        ("reconcile_interval_seconds", INTERVAL),
        ("watch_enabled", WATCH),
    ):
        note = f'{NOTE}[data-field="{field}"]'
        expect(page.locator(note)).to_have_count(1)
        assert _describes(page, control, note)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _stored(w.base) == before  # nothing is stored until Save
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    page.wait_for_timeout(300)
    expect(page.locator(COMPOSER)).to_be_focused()
    _done(page)
    expect(_drawer_receipt(page, fid)).to_have_attribute("data-status", "filled")
    # The page is dirty under the admin guard: leaving it asks. Stay keeps the filled edits.
    # Not returned: the promise stays pending while the guard waits for the choice.
    page.evaluate("() => { App.router.go(App.router.href({ destination: 'library' })); }")
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    expect(page.locator(SIZE)).to_have_value("800")
    # Save stores what the page said and clears the notes.
    page.locator(SAVE).click()
    expect(page.locator(NOTE)).to_have_count(0, timeout=8000)
    saved = _stored(w.base)
    assert saved["chunking"]["size_chars"] == 800 and saved["chunking"]["overlap_chars"] == 100
    assert saved["monitoring"]["reconcile_interval_seconds"] == 120


def test_an_overlap_above_half_the_size_shows_the_pages_error_and_disables_save(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    fid = _fill(w, {"chunk_size_chars": 400, "chunk_overlap_chars": 300})
    _deliver(page, w, fid)
    expect(page.locator(OVERLAP)).to_have_value("300", timeout=10000)
    expect(page.locator('[data-testid="knowledge-overlap-chars-error"]')).to_contain_text(
        "must not exceed 200"
    )
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    _wait_status(page, w, fid, "filled")


def test_a_field_the_operator_changed_is_kept_on_the_same_route(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page)
    page.locator(SIZE).fill("900")
    fid = _fill(w, {"chunk_size_chars": 800, "reconcile_interval_seconds": 120})
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["chunk_size_chars"], "reason": None}
    expect(page.locator(SIZE)).to_have_value("900")
    expect(page.locator(INTERVAL)).to_have_value("120")
    expect(page.locator(f'{NOTE}[data-field="chunk_size_chars"]')).to_have_count(0)
    expect(page.locator(f'{NOTE}[data-field="reconcile_interval_seconds"]')).to_have_count(1)
    _done(page)
    expect(_drawer_receipt(page, fid).locator(KEPT)).to_be_visible()


def test_a_dirty_page_and_a_fill_for_another_route_asks_the_guard_and_stay_writes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page)
    page.locator(SIZE).fill("900")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    fid = _seed_b(
        w, kind="tool_config", action="change", agent_name=None, target_id="shell",
        changes={"output_cap_bytes": 65536},
    )  # fmt: skip
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    expect(page.locator(SIZE)).to_have_value("900")
    _nav.expect_route(page, "settings/knowledge-indexing")


def test_a_page_whose_first_load_failed_is_editor_unavailable_without_the_ten_second_wait(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    page.route(
        "**/api/knowledge-settings",
        lambda route: (
            route.fulfill(status=500, content_type="application/json", body="{}")
            if route.request.method == "GET"
            else route.continue_()
        ),
    )
    fid = _fill(w, {"chunk_size_chars": 800})
    t0 = time.monotonic()
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled", timeout=7000)
    assert time.monotonic() - t0 < 7
    assert done["outcome"]["reason"] == "editor_unavailable"
    expect(page.locator('[data-testid="knowledge-settings-load-error"]')).to_be_visible()

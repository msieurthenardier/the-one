"""The MCP server editor follows a change the operator approved in a GleepGlorp chat (M36 F4 L4b,
flight DD9).

With the editor open on server S, approving an ``mcp_server`` proposal for S lands in the editor
without a reload: a clean field and a clean row take the stored value, a field or row the operator
changed keeps their value while its baseline moves, a row only the stored side has is added, a
rename updates the title, and a quiet note says where it came from. An approval for another server
changes nothing, and a Save in flight defers the rebase. The signal is ``App.approvals.record``
(the same call the approve response makes), after the server row is changed through its API.

Lives in the ``gleepglorp`` browser lane.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import (
    _get_source,
    _hold_requests,
    _install_counter,
    _kv_rows,
    _kv_val,
    _seed_mcp_source,
    _wait_held,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NAME = "#mf-name"
URL = "#mf-url"
SAVE = '[data-testid="save-mcp-source-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="mcp-approved-change-note"]'
TITLE = ".area-studio h1"
_pid = [100]


def _seed(base: str, name: str = "Docs") -> str:
    return _seed_mcp_source(
        base,
        {
            "name": name,
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "headers": {"Accept": "a/b", "X-Keep": "keep"},
            },
            "secrets": {},
        },
    )


def _open(page: Page, base: str, sid: str) -> None:
    _nav.goto_settled(page, base, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    expect(page.locator(UNSAVED)).to_have_text("")


def _approve(base: str, sid: str, **config: Any) -> dict:
    """Change the stored row the way an approved proposal does (through the API)."""
    cur = _get_source(base, sid)
    body = {
        "name": config.pop("name", cur["name"]),
        "type": cur["type"],
        "config": {**cur["config"], **config},
        "secrets": {},
    }
    body["config"].pop("_cache", None)
    r = httpx.put(
        f"{base}/api/mcp-sources/{sid}", json=body, headers=auth_headers_for(base), timeout=5.0
    )
    assert r.status_code == 200, r.text
    return r.json()


def _signal(page: Page, sid: str, fields: list[str]) -> None:
    _pid[0] += 1
    page.evaluate(
        "(d) => App.approvals.record(d)",
        {
            "kind": "mcp_server",
            "target_id": sid,
            "fields": fields,
            "session_id": "sess-approved",
            "proposal_id": _pid[0],
            "at": "2026-01-02T15:05:00+00:00",
        },
    )


def _rows(page: Page) -> dict[str, str]:
    return {
        r["key"]: r["value"]
        for r in page.evaluate(
            "() => App.areas.find(a => a.id === 'studio')._currentMcpEditor().values().rows"
        )
    }


def test_an_approved_change_lands_in_a_clean_editor_without_a_reload_and_says_so(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base)
    _open(page, base, sid)
    page.evaluate("() => { window.__same_page = 1; }")
    _approve(
        base,
        sid,
        url="https://approved.test/mcp",
        headers={"Accept": "c/d", "X-Keep": "keep", "X-New": "new"},
    )
    _signal(page, sid, ["url", "headers"])
    expect(page.locator(URL)).to_have_value("https://approved.test/mcp", timeout=8000)
    expect(page.locator(NOTE)).to_have_count(1)
    expect(page.locator(NOTE)).to_contain_text(
        "Changed by a change you approved in a GleepGlorp chat"
    )
    link = page.locator(f"{NOTE} a")
    assert link.evaluate("e => e.tagName") == "A"
    assert (link.get_attribute("href") or "").endswith(_nav.href("chats/sess-approved"))
    assert _rows(page) == {"Accept": "c/d", "X-Keep": "keep", "X-New": "new"}
    # Clean: the stored row is the baseline, so nothing is unsaved.
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()
    assert page.evaluate("() => window.__same_page") == 1
    # Save and Cancel clear the note.
    page.locator(NAME).fill("Docs two")
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()
    expect(page.locator(NAME)).to_have_value("Docs")
    expect(page.locator(NOTE)).to_have_count(0)


def test_an_unsaved_edit_is_kept_stays_dirty_and_a_later_save_keeps_the_approved_change(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base)
    _open(page, base, sid)
    page.locator(NAME).fill("Mine")
    row = _kv_rows(page).nth(0)  # Accept
    _kv_val(row).fill("operator-typed")
    _approve(
        base,
        sid,
        url="https://approved.test/mcp",
        headers={"Accept": "approved", "X-Keep": "changed", "X-Keep2": "added"},
    )
    _signal(page, sid, ["url", "headers"])
    expect(page.locator(URL)).to_have_value("https://approved.test/mcp", timeout=8000)
    # The operator's name and row value stay; the clean row and the new row follow.
    expect(page.locator(NAME)).to_have_value("Mine")
    assert _rows(page) == {
        "Accept": "operator-typed",
        "X-Keep": "changed",
        "X-Keep2": "added",
    }
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(NOTE)).to_have_count(1)
    # Save sends the operator's edits on top of the approved change, never under it.
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    saved = _get_source(base, sid)
    assert saved["name"] == "Mine"
    assert saved["config"]["url"] == "https://approved.test/mcp"
    assert saved["config"]["headers"] == {
        "Accept": "operator-typed",
        "X-Keep": "changed",
        "X-Keep2": "added",
    }


def test_a_dirty_row_moves_its_baseline_so_cancel_returns_to_the_approved_value(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base)
    _open(page, base, sid)
    _kv_val(_kv_rows(page).nth(0)).fill("operator-typed")
    _approve(base, sid, headers={"Accept": "approved", "X-Keep": "keep"})
    _signal(page, sid, ["headers"])
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    assert _rows(page)["Accept"] == "operator-typed"
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()
    assert _rows(page)["Accept"] == "approved"
    expect(page.locator(UNSAVED)).to_have_text("")


def test_a_rename_updates_the_title_and_the_page_name(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    sid = _seed(base, "Docs")
    _open(page, base, sid)
    _approve(base, sid, name="Docs renamed")
    _signal(page, sid, ["name"])
    expect(page.locator(TITLE)).to_have_text("Docs renamed", timeout=8000)
    expect(page.locator(NAME)).to_have_value("Docs renamed")
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_have_attribute(
        "data-name", "Docs renamed"
    )
    assert "Docs renamed" in page.title() or "Docs renamed" in page.locator("body").inner_text()


def test_an_approval_for_another_server_or_a_create_changes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _install_counter(page)
    sid = _seed(base, "Docs")
    other = _seed(base, "Other")
    _open(page, base, sid)
    _approve(base, other, url="https://other.test/mcp")
    _signal(page, other, ["url"])
    page.wait_for_timeout(500)
    expect(page.locator(URL)).to_have_value("https://example.com/mcp")
    expect(page.locator(NOTE)).to_have_count(0)
    # A create form ignores an event for any server.
    _nav.goto_settled(page, base, "library/mcp/~new")
    expect(page.locator(NAME)).to_be_attached(timeout=10000)
    _signal(page, sid, ["url"])
    page.wait_for_timeout(500)
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(NAME)).to_have_value("")


def test_a_save_in_flight_defers_the_rebase_until_it_ends(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _install_counter(page)
    sid = _seed(base)
    _open(page, base, sid)
    held = _hold_requests(page, f"**/api/mcp-sources/{sid}", "PUT")
    page.locator(NAME).fill("Saved name")
    page.locator(SAVE).click()
    _wait_held(page, held, "PUT", f"/api/mcp-sources/{sid}")
    _approve(base, sid, url="https://approved.test/mcp")
    _signal(page, sid, ["url"])
    page.wait_for_timeout(600)
    # Nothing moved while the Save was in flight.
    expect(page.locator(URL)).to_have_value("https://example.com/mcp")
    expect(page.locator(NOTE)).to_have_count(0)
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    # The Save finished, and the follow read the row again and drew its note.
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    stored = _get_source(base, sid)
    expect(page.locator(URL)).to_have_value(stored["config"]["url"])
    expect(page.locator(UNSAVED)).to_have_text("")

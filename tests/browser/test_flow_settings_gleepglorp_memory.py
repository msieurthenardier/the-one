"""Settings > GleepGlorp: the Memory section and the web-search hint (M36 F1 L06).

* Memory lists GleepGlorp's saved notes with the agent Notes tab's row (the shared
  ``notes-row*`` testids inside ``gleepglorp-memory-list``): number, text, the "Check this"
  flag, origin; "No saved notes yet." when empty.
* Delete is the two-step armed confirm and Clear all goes through the confirm dialog; both
  act at once (not part of Save) and the list reloads.
* With memory off the section shows its hint and keeps the notes.
* Note text is rendered literally.
* Under the Web access switch a hint with a link to the web search tool shows only while the
  switch is on and the configured engine cannot run.

Settings lane (``test_flow_settings_*`` in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import seed_gleepglorp_note
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

LIST = '[data-testid="gleepglorp-memory-list"]'
ROWS = f'{LIST} [data-testid="notes-row"]'
DELETE = '[data-testid="gleepglorp-memory-delete"]'
CLEAR = '[data-testid="gleepglorp-memory-clear"]'
EMPTY = '[data-testid="gleepglorp-memory-empty"]'
OFF = '[data-testid="gleepglorp-memory-off"]'
WEB_HINT = '[data-testid="gleepglorp-web-hint"]'
RETENTION = '[data-testid="gleepglorp-retention"]'


def _goto(page: Page, base: str) -> None:
    _nav.goto(page, base, "settings/gleepglorp")
    expect(page.locator(".page-title")).to_have_text("GleepGlorp", timeout=8000)
    expect(page.locator(RETENTION)).to_have_value("30", timeout=8000)


def _notes(base: str) -> dict:
    r = httpx.get(f"{base}/api/gleepglorp/notes", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()


def _put(base: str, **over) -> None:
    body = {
        "enabled": True,
        "provider_config_id": None,
        "model": None,
        "web_access": True,
        "memory": True,
        "retention_days": 30,
        **over,
    }
    r = httpx.put(f"{base}/api/gleepglorp", json=body, headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text


def test_an_empty_memory_says_so_and_has_no_clear_all(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, _data = app_with_data_dir
    _goto(page, base)
    expect(page.locator('[data-testid="gleepglorp-memory-section"] h2')).to_have_text("Memory")
    expect(page.locator(EMPTY)).to_have_text("No saved notes yet.", timeout=8000)
    expect(page.locator(CLEAR)).to_be_hidden()
    expect(page.locator(OFF)).to_be_hidden()


def test_notes_list_with_flag_origin_and_literal_text(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data = app_with_data_dir
    seed_gleepglorp_note(data, "Runs Ollama on this machine.")
    seed_gleepglorp_note(
        data, "<b>bold</b> & <script>1</script>", untrusted=True, sources=["fetch_url"]
    )
    _goto(page, base)
    rows = page.locator(ROWS)
    expect(rows).to_have_count(2, timeout=8000)
    texts = page.locator(f"{LIST} [data-testid='notes-row-text']").all_inner_texts()
    assert texts == ["Runs Ollama on this machine.", "<b>bold</b> & <script>1</script>"]
    assert page.locator(f"{LIST} b, {LIST} script").count() == 0
    assert rows.nth(0).get_attribute("data-number") == "1"
    expect(rows.nth(0).locator('[data-testid="notes-row-flag"]')).to_have_count(0)
    expect(rows.nth(1).locator('[data-testid="notes-row-flag"]')).to_have_count(1)
    expect(rows.nth(0).locator('[data-testid="notes-row-origin"]')).to_have_text("Outside a chat")
    # No edit action: Memory rows can be deleted, not edited.
    expect(page.locator(f"{LIST} [data-testid='notes-row-edit']")).to_have_count(0)
    expect(page.locator(CLEAR)).to_be_visible()


def test_delete_is_armed_then_confirmed_and_does_not_touch_the_form(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data = app_with_data_dir
    seed_gleepglorp_note(data, "Keep me.")
    seed_gleepglorp_note(data, "Delete me.")
    _goto(page, base)
    rows = page.locator(ROWS)
    expect(rows).to_have_count(2, timeout=8000)
    page.locator(RETENTION).fill("45")  # an unsaved edit must survive a Memory change
    btn = rows.nth(1).locator(DELETE)
    assert btn.get_attribute("aria-label") == "Delete note 2"
    btn.click()
    expect(btn).to_have_class(re.compile("confirm-delete"))
    assert len(_notes(base)["notes"]) == 2  # armed only
    btn.click()
    expect(rows).to_have_count(1, timeout=8000)
    assert [n["text"] for n in _notes(base)["notes"]] == ["Keep me."]
    expect(rows.nth(0).locator(DELETE)).to_be_focused()
    expect(page.locator(RETENTION)).to_have_value("45")
    expect(page.locator('[data-testid="editor-unsaved"]').first).to_be_visible()


def test_clear_all_cancel_changes_nothing_and_confirm_clears(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data = app_with_data_dir
    for text in ("One.", "Two.", "Three."):
        seed_gleepglorp_note(data, text)
    _goto(page, base)
    expect(page.locator(ROWS)).to_have_count(3, timeout=8000)
    page.locator(CLEAR).click()
    dialog = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(dialog).to_contain_text("Clear all 3 notes GleepGlorp has saved?")
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(dialog).to_have_count(0)
    assert len(_notes(base)["notes"]) == 3
    page.locator(CLEAR).click()
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(EMPTY)).to_be_visible(timeout=8000)
    assert _notes(base)["notes"] == []
    expect(page.locator(CLEAR)).to_be_hidden()


def test_memory_off_shows_the_hint_and_keeps_the_notes(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data = app_with_data_dir
    seed_gleepglorp_note(data, "Stays until deleted.")
    _put(base, memory=False)
    _goto(page, base)
    expect(page.locator(OFF)).to_have_text(
        "Memory is off. GleepGlorp keeps no new notes; these stay until you delete them.",
        timeout=8000,
    )
    expect(page.locator(ROWS)).to_have_count(1)
    # Saving the switch back on takes the hint away (the Save primes the settings store).
    page.locator(".ui-toggle-label").filter(
        has=page.locator('[data-testid="gleepglorp-memory"]')
    ).click()
    page.locator('[data-testid="gleepglorp-save-btn"]').click()
    expect(page.locator(OFF)).to_be_hidden(timeout=8000)
    expect(page.locator(ROWS)).to_have_count(1)


def test_the_web_hint_follows_the_switch_and_the_engine(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, _data = app_with_data_dir
    # The default engine (DuckDuckGo) needs nothing: no hint.
    _goto(page, base)
    expect(page.locator(WEB_HINT)).to_be_hidden()

    # A keyed engine with no key is unusable.
    r = httpx.put(
        f"{base}/api/tools/configs/web_search",
        json={"enabled": True, "config": {"search_backend": "brave"}},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    shown = httpx.get(f"{base}/api/gleepglorp", headers=auth_headers_for(base), timeout=5).json()
    assert shown["web_search_available"] is False
    page.reload()
    expect(page.locator(RETENTION)).to_have_value("30", timeout=8000)
    hint = page.locator(WEB_HINT)
    expect(hint).to_have_attribute("role", "status")
    expect(hint).to_be_visible()
    expect(hint).to_contain_text(
        "Web search isn't set up, so GleepGlorp can only read pages you give it."
    )
    link = page.locator('[data-testid="gleepglorp-web-hint-link"]')
    assert link.get_attribute("href") == _nav.href("settings/tools/web_search")

    # Switching Web access off hides it again (the hint is about the switch being on).
    page.locator(".ui-toggle-label").filter(
        has=page.locator('[data-testid="gleepglorp-web"]')
    ).click()
    expect(hint).to_be_hidden()
    # A persistent live region: still in the DOM, its text cleared.
    expect(hint).to_have_count(1)
    expect(hint).to_have_text("")

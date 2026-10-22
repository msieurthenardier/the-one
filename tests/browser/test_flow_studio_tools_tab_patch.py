"""Agent editor Built-in Tools tab: dirty tracking, patch-on-Save and Cancel (M31 F2 L08b).

The tab is built once per agent identity and patched through ``setAgent`` (DD6):
a same-identity Save keeps loaded override bodies (and an open disclosure with
focus inside); Cancel drops them and re-arms the lazy load. Library inputs are
invisible to the editor's field-level listener sweep, so every master, row and
override control calls the dirty callback itself: these tests drive REAL clicks.
"""

from __future__ import annotations

import urllib.parse

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_tool_config
from playwright.sync_api import Page, expect

SAVE = '[data-testid="save-agent-btn"]'
CANCEL = '[data-testid="cancel-agent-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'


def _url(base: str, name: str) -> str:
    return f"{base}/api/agents/{urllib.parse.quote(name)}"


def _get(base: str, name: str) -> dict:
    r = httpx.get(_url(base, name), timeout=5.0, headers=auth_headers_for(base))
    assert r.status_code == 200, r.text
    return r.json()


def _put_overrides(base: str, name: str, overrides: dict | None) -> None:
    cfg = _get(base, name)
    cfg["tool_overrides"] = overrides
    r = httpx.put(_url(base, name), json=cfg, timeout=5.0, headers=auth_headers_for(base))
    assert r.status_code == 200, r.text


def _open_tools(page: Page, app: SeededApp) -> None:
    _nav.goto(page, app.base_url, f"agents/{_nav.seg(app.agent_name or '')}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _expand(page: Page, category: str) -> None:
    expand = page.locator(f'.ui-group-tile[data-category="{category}"] .ui-group-tile-expand')
    if expand.get_attribute("aria-expanded") != "true":
        expand.click()
        expect(expand).to_have_attribute("aria-expanded", "true", timeout=2000)


def _row(page: Page, tool: str):
    return page.locator(f'details.ui-tool-row[data-tool="{tool}"]')


def _open_overrides(page: Page, tool: str):
    row = _row(page, tool)
    row.locator(".ui-tool-row-affordance").click()
    expect(row).to_have_attribute("open", "", timeout=2000)
    return row


TIMEOUT = 'input[data-tool-override-field="timeout_seconds_max"]'


# ── Dirty tracking: real clicks on the library controls ─────────────────────


@pytest.mark.browser
def test_clicking_a_tool_checkbox_marks_the_editor_dirty(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_tools(page, app_with_agent)
    _expand(page, "Connectors")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(UNSAVED)).to_have_text("")
    page.locator('input[data-tool="send_to_platform_channel"]').click()
    expect(page.locator(SAVE)).to_be_enabled(timeout=3000)
    expect(page.locator(UNSAVED)).not_to_have_text("")
    # Clicking it back to the stored state is clean again.
    page.locator('input[data-tool="send_to_platform_channel"]').click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=3000)


@pytest.mark.browser
def test_clicking_a_category_master_marks_the_editor_dirty(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_tools(page, app_with_agent)
    expect(page.locator(SAVE)).to_be_disabled()
    page.locator('.ui-group-tile[data-category="Web"] .ui-group-tile-row .ui-toggle-label').click()
    expect(page.locator(SAVE)).to_be_enabled(timeout=3000)
    expect(page.locator(UNSAVED)).not_to_have_text("")
    expect(page.locator('.ui-group-tile[data-category="Web"] .ui-group-tile-chip')).to_have_text(
        "0 / 4 enabled"
    )


@pytest.mark.browser
def test_typing_in_an_override_field_marks_the_editor_dirty(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_tools(page, app_with_agent)
    _expand(page, "Web")
    row = _open_overrides(page, "http_request")
    field = row.locator(TIMEOUT)
    expect(field).to_be_visible(timeout=5000)
    expect(page.locator(SAVE)).to_be_disabled()
    field.fill("7")
    expect(page.locator(SAVE)).to_be_enabled(timeout=3000)
    expect(page.locator(UNSAVED)).not_to_have_text("")


# ── Patch on Save, rebuild on Cancel ────────────────────────────────────────


@pytest.mark.browser
def test_save_keeps_the_open_override_body_and_its_focus(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    assert app.agent_name
    seed_tool_config(app.base_url, "http_request", config={"timeout_seconds_max": 60})
    _open_tools(page, app)
    _expand(page, "Web")
    row = _open_overrides(page, "http_request")
    field = row.locator(TIMEOUT)
    expect(field).to_be_visible(timeout=5000)
    field.fill("20")
    field.evaluate("e => { e.dataset.mark = 'same-node'; e.focus(); }")
    # A real click on Save would move focus to the button; dispatch the click so focus
    # stays where the user left it, which is what the patch must not disturb.
    page.locator(SAVE).dispatch_event("click")
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)

    assert (
        _get(app.base_url, app.agent_name)["tool_overrides"]["http_request"]["timeout_seconds_max"]
        == 20
    )
    # The body was patched, not rebuilt: the same node, still open, still focused.
    expect(row).to_have_attribute("open", "")
    marked = row.locator(f'{TIMEOUT}[data-mark="same-node"]')
    expect(marked).to_have_count(1)
    expect(marked).to_have_value("20")
    expect(marked).to_be_focused()


@pytest.mark.browser
def test_cancel_drops_override_edits_and_rearms_the_lazy_load(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    assert app.agent_name
    seed_tool_config(app.base_url, "http_request", config={"timeout_seconds_max": 60})
    _put_overrides(app.base_url, app.agent_name, {"http_request": {"timeout_seconds_max": 30}})
    _open_tools(page, app)
    _expand(page, "Web")
    row = _open_overrides(page, "http_request")
    field = row.locator(TIMEOUT)
    expect(field).to_have_value("30", timeout=5000)
    field.fill("5")
    page.locator(CANCEL).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=3000)
    # The disclosure closes and the body is back to the placeholder.
    expect(row).not_to_have_attribute("open", "")
    expect(row.locator(".ui-tool-row-body p.loading")).to_have_text("Loading…")
    # The next open renders the STORED value again.
    row.locator(".ui-tool-row-affordance").click()
    expect(row.locator(TIMEOUT)).to_have_value("30", timeout=5000)
    # Nothing was saved.
    assert _get(app.base_url, app.agent_name)["tool_overrides"]["http_request"] == {
        "timeout_seconds_max": 30
    }


@pytest.mark.browser
def test_cancel_restores_checked_state_and_counts(app_with_agent: SeededApp, page: Page) -> None:
    _open_tools(page, app_with_agent)
    _expand(page, "Connectors")
    chip = page.locator('.ui-group-tile[data-category="Connectors"] .ui-group-tile-chip')
    page.locator('input[data-tool="send_to_platform_channel"]').click()
    expect(chip).to_have_text("2 / 3 enabled")
    page.locator(CANCEL).click()
    expect(page.locator('input[data-tool="send_to_platform_channel"]')).to_be_checked()
    expect(chip).to_have_text("3 / 3 enabled")
    master = page.locator('input[data-category-master="Connectors"]')
    expect(master).to_be_checked()


@pytest.mark.browser
def test_stored_override_on_an_operator_disabled_tool_survives_a_save(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    assert app.agent_name
    stored = {"http_request": {"timeout_seconds_max": 30}}
    _put_overrides(app.base_url, app.agent_name, stored)
    seed_tool_config(app.base_url, "http_request", enabled=False)
    _open_tools(page, app)
    _expand(page, "Web")
    row = page.locator('.ui-tool-row[data-tool="http_request"]')
    expect(row).to_have_attribute("title", "Disabled by operator")
    expect(row.locator(".ui-tool-row-affordance")).to_have_count(0)
    # Open another tool's overrides and change it, so collectFormData sends a map.
    _expand(page, "Filesystem")
    read_row = _open_overrides(page, "read_file")
    box = read_row.locator("[data-tool-override-field]").first
    expect(box).to_be_visible(timeout=5000)
    page.locator('input[data-tool="write_file"]').click()
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    body = _get(app.base_url, app.agent_name)
    assert body["tool_overrides"]["http_request"] == {"timeout_seconds_max": 30}
    assert "write_file" in body["disabled_tools"]


@pytest.mark.browser
def test_save_with_changed_overrides_reflects_saved_values_in_open_bodies(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    assert app.agent_name
    seed_tool_config(app.base_url, "http_request", config={"timeout_seconds_max": 60})
    _put_overrides(app.base_url, app.agent_name, {"http_request": {"timeout_seconds_max": 30}})
    _open_tools(page, app)
    _expand(page, "Web")
    row = _open_overrides(page, "http_request")
    expect(row.locator(TIMEOUT)).to_have_value("30", timeout=5000)
    row.locator(TIMEOUT).fill("12")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    expect(row.locator(TIMEOUT)).to_have_value("12")
    # A second change after the patch saves from the patched body (no stale snapshot).
    row.locator(TIMEOUT).fill("9")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    saved = _get(app.base_url, app.agent_name)["tool_overrides"]["http_request"]
    assert saved["timeout_seconds_max"] == 9

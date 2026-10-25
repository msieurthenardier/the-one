"""The agent Tools tab and ``current_time`` (Mission 28 Flight 1 Leg 3, DD6).

``current_time`` is exempt from the ``enabled_tools`` whitelist (the server's
``AgentConfig.is_tool_enabled``). The Tools tab must show it checked on a
trimmed agent, and the save must put an unticked ``current_time`` in
``disabled_tools`` in every branch and never in ``enabled_tools``.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_tool_config
from playwright.sync_api import Page, expect

TOOL = 'input[type="checkbox"][data-tool="current_time"]'
SAVE = '[data-testid="save-agent-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'


def _get(base: str, name: str) -> dict:
    r = httpx.get(f"{base}/api/agents/{name}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _put(base: str, name: str, **overrides: object) -> None:
    body = _get(base, name)
    body.update(overrides)
    r = httpx.put(
        f"{base}/api/agents/{name}", json=body, headers=auth_headers_for(base), timeout=5.0
    )
    assert r.status_code == 200, r.text


def _open_tools(page: Page, app: SeededApp) -> None:
    _nav.goto(page, app.base_url, f"agents/{_nav.seg(app.agent_name or '')}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    tile = page.locator('.ui-group-tile[data-category="Time"]')
    expect(tile).to_be_visible(timeout=8000)
    expand = tile.locator(".ui-group-tile-expand")
    expand.click()
    expect(expand).to_have_attribute("aria-expanded", "true", timeout=2000)


def _save(page: Page) -> None:
    save = page.locator(SAVE)
    expect(save).to_be_enabled(timeout=5000)
    save.click()
    expect(save).to_be_disabled(timeout=5000)
    expect(page.locator(UNSAVED)).to_have_text("", timeout=5000)


@pytest.mark.browser
def test_whitelisted_agent_shows_time_checked_and_note(
    app_with_agent: SeededApp, page: Page
) -> None:
    _put(app_with_agent.base_url, app_with_agent.agent_name, enabled_tools=["read_file"])
    _open_tools(page, app_with_agent)
    expect(page.locator(TOOL)).to_be_checked()
    tile = page.locator('.ui-group-tile[data-category="Time"]')
    expect(tile.locator(".ui-group-tile-chip")).to_have_text("1 / 1 enabled")
    expect(page.locator('[data-testid="time-tool-note"]')).to_contain_text(
        "Always available to the agent"
    )
    # Merely opening leaves the editor clean.
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()


@pytest.mark.browser
def test_untick_on_whitelisted_agent_saves_to_disabled_tools_only(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _put(base, name, enabled_tools=["read_file"])
    _open_tools(page, app_with_agent)
    page.locator(TOOL).uncheck()
    _save(page)
    body = _get(base, name)
    assert "current_time" in body["disabled_tools"]
    assert body["enabled_tools"] == ["read_file"]

    page.reload()
    _open_tools(page, app_with_agent)
    expect(page.locator(TOOL)).not_to_be_checked()
    expect(page.locator(UNSAVED)).to_have_text("")

    page.locator(TOOL).check()
    _save(page)
    body = _get(base, name)
    assert "current_time" not in body["disabled_tools"]
    assert body["enabled_tools"] == ["read_file"]


@pytest.mark.browser
def test_untick_on_all_tools_agent_is_a_pure_blocklist(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_tools(page, app_with_agent)
    expect(page.locator(TOOL)).to_be_checked()
    page.locator(TOOL).uncheck()
    _save(page)
    body = _get(base, name)
    assert body["enabled_tools"] is None
    assert body["disabled_tools"] == ["current_time"]


@pytest.mark.browser
def test_category_master_unticks_time(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_tools(page, app_with_agent)
    master = page.locator('[data-category-master="Time"]')
    expect(master).to_have_accessible_name("Enable all Time tools")
    page.locator('[data-category-master="Time"]').locator("xpath=ancestor::label").click()
    expect(page.locator(TOOL)).not_to_be_checked()
    _save(page)
    assert "current_time" in _get(base, name)["disabled_tools"]


@pytest.mark.browser
def test_create_mode_shows_time_checked_and_saves_no_gating(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, "agents")
    _lists.agents_new(page)
    page.locator('[data-field="name"]').fill("clock-agent")
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=8000)
    page.locator("#studio-model").select_option("mock-default")
    page.locator('[data-testid="tab-tools"]').click()
    page.locator('.ui-group-tile[data-category="Time"] .ui-group-tile-expand').click()
    expect(page.locator(TOOL)).to_be_checked()
    page.locator(SAVE).click()
    _nav.expect_route(page, "agents/clock-agent/general", timeout=8000)
    body = _get(base, "clock-agent")
    assert body["enabled_tools"] is None
    assert body["disabled_tools"] == []


@pytest.mark.browser
def test_globally_disabled_time_is_operator_disabled_in_the_tab(
    app_with_agent: SeededApp, page: Page
) -> None:
    seed_tool_config(app_with_agent.base_url, "current_time", enabled=False)
    _open_tools(page, app_with_agent)
    expect(page.locator(TOOL)).to_be_disabled()
    expect(page.locator('.ui-tool-row[data-tool="current_time"]')).to_have_class(
        re.compile(r"\bis-disabled\b")
    )


@pytest.mark.browser
def test_settings_tile_toggle_disables_and_reenables_current_time(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "settings/tools")
    page.locator('[data-testid="tab-time"]').click()
    toggle = _lists.tool_toggle(page, "current_time")
    expect(toggle).to_be_checked()
    toggle.click(force=True)
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).not_to_be_checked()

    def enabled() -> bool:
        r = httpx.get(f"{app_clean}/api/tools/configs", headers=auth_headers_for(app_clean))
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows.get("configs", rows)
        row = next(x for x in rows if x["name"] == "current_time")
        return row["enabled"]

    assert enabled() is False
    toggle.click(force=True)
    expect(toggle).to_be_checked(timeout=5000)
    expect(toggle).not_to_be_disabled(timeout=5000)
    assert enabled() is True

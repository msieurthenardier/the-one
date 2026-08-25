"""Browser tests for the agent-editor Self-configuration tab (M21 F01 L02,
AC12).

Covers:
  1. Off-by-default rendering (status line + Enable button).
  2. Enabling from the tab creates the surface row and makes it appear on
     the MCPs tab with a locked (checked+disabled) attach toggle plus
     editable per-tool checkboxes.
  3. Disabling from the tab removes the surface row from the MCPs tab.
"""

from __future__ import annotations

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _seed_agent(base_url: str, name: str) -> dict:
    r = httpx.post(
        f"{base_url}/api/agents",
        json={"name": name, "description": "self-configuration tab test agent"},
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code in (200, 201), f"seed agent failed: {r.status_code} {r.text}"
    return r.json()


def _navigate_to_self_configuration_tab(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}/self-configuration")
    expect(page.locator('[data-testid="tab-self-configuration"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


@pytest.mark.browser
def test_tab_renders_disabled_by_default(app_clean: str, page: Page) -> None:
    _seed_agent(app_clean, "self-config-default-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "self-config-default-agent")

    status = page.locator('[data-testid="self-configuration-status"]')
    expect(status).to_contain_text("disabled", timeout=8000)
    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).to_have_text("Enable")


@pytest.mark.browser
def test_enable_shows_locked_row_on_mcps_tab(app_clean: str, page: Page) -> None:
    _seed_agent(app_clean, "self-config-enable-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "self-config-enable-agent")

    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).to_have_text("Enable", timeout=8000)
    toggle.click()

    status = page.locator('[data-testid="self-configuration-status"]')
    expect(status).to_contain_text("enabled", timeout=8000)
    expect(toggle).to_have_text("Disable")

    # Confirm server-side: exactly one streamable-http surface row, attached.
    agent = httpx.get(
        f"{app_clean}/api/agents/self-config-enable-agent",
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    ).json()
    assert len(agent["mcp_source_ids"]) == 1
    source_id = agent["mcp_source_ids"][0]

    # MCPs tab shows the row, locked checked+disabled.
    page.locator('[data-testid="tab-mcps"]').click()
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    row_toggle = page.locator(f'[data-testid="mcp-source-toggle-{source_id}"]')
    expect(row_toggle).to_be_checked(timeout=8000)
    expect(row_toggle).to_be_disabled()
    expect(
        page.locator(f'[data-testid="mcp-source-self-configuration-hint-{source_id}"]')
    ).to_be_visible()


@pytest.mark.browser
def test_disable_removes_row_from_mcps_tab(app_clean: str, page: Page) -> None:
    _seed_agent(app_clean, "self-config-disable-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "self-config-disable-agent")

    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).to_have_text("Enable", timeout=8000)
    toggle.click()
    expect(toggle).to_have_text("Disable", timeout=8000)

    toggle.click()
    status = page.locator('[data-testid="self-configuration-status"]')
    expect(status).to_contain_text("disabled", timeout=8000)
    expect(toggle).to_have_text("Enable")

    page.locator('[data-testid="tab-mcps"]').click()
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    expect(page.locator('[data-testid="mcp-empty-state"]')).to_be_visible(timeout=8000)

    agent = httpx.get(
        f"{app_clean}/api/agents/self-config-disable-agent",
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    ).json()
    assert agent["mcp_source_ids"] == []

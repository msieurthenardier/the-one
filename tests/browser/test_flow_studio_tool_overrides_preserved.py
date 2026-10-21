"""Squawk 0223: saving an agent without opening any Overrides panel keeps its tool_overrides."""

from __future__ import annotations

import urllib.parse

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

_OV = {"read_file": {"path_denylist": ["/secret"]}}


@pytest.mark.browser
def test_description_only_save_preserves_tool_overrides(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    headers = auth_headers_for(base)
    url = f"{base}/api/agents/{urllib.parse.quote(name)}"
    cfg = httpx.get(url, timeout=5.0, headers=headers).json()
    cfg["tool_overrides"] = _OV
    r = httpx.put(url, json=cfg, timeout=5.0, headers=headers)
    assert r.status_code == 200, r.text
    assert httpx.get(url, timeout=5.0, headers=headers).json()["tool_overrides"] == _OV

    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}")
    desc = page.locator('[data-field="description"]').first
    expect(desc).to_be_visible(timeout=8000)
    desc.fill("changed description only")
    save = page.locator('[data-testid="save-agent-btn"]')
    expect(save).to_be_enabled(timeout=5000)
    save.click()
    expect(save).to_be_disabled(timeout=5000)

    body = httpx.get(url, timeout=5.0, headers=headers).json()
    assert body["description"] == "changed description only"
    assert body["tool_overrides"] == _OV

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


# ── Leg 08a: the 0223 rule ported into agent-form-data.js (Mission 31 F2) ──


def _put_overrides(base: str, name: str, overrides: dict | None) -> str:
    headers = auth_headers_for(base)
    url = f"{base}/api/agents/{urllib.parse.quote(name)}"
    cfg = httpx.get(url, timeout=5.0, headers=headers).json()
    cfg["tool_overrides"] = overrides
    r = httpx.put(url, json=cfg, timeout=5.0, headers=headers)
    assert r.status_code == 200, r.text
    return url


def _open_tools(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _open_panel(page: Page, category: str, tool: str):
    tile = page.locator(f'.tools-category-tile[data-category="{category}"]')
    expect(tile).to_be_visible(timeout=8000)
    if tile.get_attribute("aria-expanded") != "true":
        tile.locator(".tools-category-tile-expand-btn").click()
        expect(tile).to_have_attribute("aria-expanded", "true", timeout=2000)
    panel = page.locator(f'details.tool-row-overrides[data-tool="{tool}"]')
    panel.locator(".tool-tile-overrides-affordance").click()
    return panel


def _add_chip(panel, field: str, value: str) -> None:
    chips = panel.locator(f'.chip-list-editor[data-tool-override-field="{field}"]')
    expect(chips).to_be_visible(timeout=5000)
    inp = chips.locator(".chip-list-input")
    inp.fill(value)
    inp.press("Enter")


def _save(page: Page) -> None:
    save = page.locator('[data-testid="save-agent-btn"]')
    expect(save).to_be_enabled(timeout=5000)
    save.click()
    expect(save).to_be_disabled(timeout=5000)


@pytest.mark.browser
def test_partial_open_merges_stored_entries_of_unopened_tools(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    url = _put_overrides(
        base,
        name,
        {
            "read_file": {"path_denylist": ["/secret"]},
            "http_request": {"extra_allowed_hosts": ["a.com"]},
        },
    )
    _open_tools(page, base, name)
    _add_chip(_open_panel(page, "Web", "http_request"), "extra_allowed_hosts", "localhost")
    _save(page)
    ov = httpx.get(url, timeout=5.0, headers=auth_headers_for(base)).json()["tool_overrides"]
    assert ov["http_request"]["extra_allowed_hosts"] == ["a.com", "localhost"]
    assert ov["read_file"] == {"path_denylist": ["/secret"]}


@pytest.mark.browser
def test_second_save_does_not_use_stale_stored_entries(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    url = _put_overrides(base, name, None)
    _open_tools(page, base, name)
    _add_chip(_open_panel(page, "Web", "http_request"), "extra_allowed_hosts", "first.example")
    _save(page)
    _add_chip(_open_panel(page, "Filesystem", "read_file"), "path_denylist", "/second")
    _save(page)
    ov = httpx.get(url, timeout=5.0, headers=auth_headers_for(base)).json()["tool_overrides"]
    assert ov["http_request"]["extra_allowed_hosts"] == ["first.example"]
    assert "/second" in ov["read_file"]["path_denylist"]


@pytest.mark.browser
def test_locked_operator_chips_are_sent_and_save_accepted(
    app_with_agent: SeededApp, page: Page
) -> None:
    from browser.seeders import seed_tool_config

    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "read_file", config={"path_denylist": ["/ops"]})
    url = _put_overrides(base, name, None)
    _open_tools(page, base, name)
    _add_chip(_open_panel(page, "Filesystem", "read_file"), "path_denylist", "/mine")
    _save(page)
    ov = httpx.get(url, timeout=5.0, headers=auth_headers_for(base)).json()["tool_overrides"]
    assert set(ov["read_file"]["path_denylist"]) == {"/ops", "/mine"}

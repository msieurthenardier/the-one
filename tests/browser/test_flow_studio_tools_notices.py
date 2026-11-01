"""Sortie 07 leg 5: tool-override notices on the Tools tab indicator, the tool rows and the
Agents list (DD11), kept current by the ``agents`` store without a reload (AC2, AC3)."""

from __future__ import annotations

import re
import urllib.parse

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_tool_config
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

FLAG = '[data-testid="tool-override-notice-flag"]'
USE_NARROWED = '[data-testid="tool-override-use-narrowed"]'
TOOLS = ("http_request", "fetch_url")


def _agent_url(base: str, name: str) -> str:
    return f"{base}/api/agents/{urllib.parse.quote(name)}"


def _agent(base: str, name: str) -> dict:
    return httpx.get(_agent_url(base, name), timeout=5.0, headers=auth_headers_for(base)).json()


def _put_agent(base: str, name: str, **changes) -> None:
    cfg = _agent(base, name)
    cfg.update(changes)
    r = httpx.put(_agent_url(base, name), json=cfg, timeout=5.0, headers=auth_headers_for(base))
    assert r.status_code == 200, r.text


def _seed_overrides(base: str, name: str, tools=TOOLS) -> None:
    """An override that fit; the caller then narrows the app-wide list under it."""
    for tool in tools:
        seed_tool_config(base, tool, config={"extra_allowed_hosts": ["a.com", "b.com"]})
    _put_agent(
        base,
        name,
        tool_overrides={t: {"extra_allowed_hosts": ["a.com", "b.com"]} for t in tools},
    )


def _tighten(base: str, tools=TOOLS) -> None:
    for tool in tools:
        seed_tool_config(base, tool, config={"extra_allowed_hosts": ["a.com"]})


def _widen(base: str, tools=TOOLS) -> None:
    for tool in tools:
        seed_tool_config(base, tool, config={"extra_allowed_hosts": ["a.com", "b.com"]})


def _open_tools(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _row(page: Page, tool: str):
    return page.locator(f'details.ui-tool-row[data-tool="{tool}"]')


def _expand(page: Page, tool: str) -> None:
    row = _row(page, tool)
    tile = page.locator(".ui-group-tile", has=row)
    expect(tile).to_be_visible(timeout=8000)
    expand = tile.locator(".ui-group-tile-expand")
    if expand.get_attribute("aria-expanded") != "true":
        expand.click()
        expect(expand).to_have_attribute("aria-expanded", "true", timeout=2000)


def _refresh_agents(page: Page) -> None:
    """What a return from Settings does: a forced agents fetch notifies the subscribers."""
    page.evaluate("() => App.store.get('agents', {force: true})")


def _save(page: Page) -> None:
    save = page.locator('[data-testid="save-agent-btn"]')
    expect(save).to_be_enabled(timeout=5000)
    save.click()
    expect(save).to_be_disabled(timeout=5000)


# -- AC1/AC2: the tab indicator and the tool flags ----------------------------


def test_the_tab_and_two_tool_rows_carry_the_notices_and_clear_after_the_fix(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _seed_overrides(base, name)
    _tighten(base)
    assert len(_agent(base, name)["notices"]) == 2
    _open_tools(page, base, name)
    expect(page.get_by_role("tab", name="Tools, 2 notices", exact=True)).to_have_count(1)
    for tool in TOOLS:
        _expand(page, tool)
        expect(_row(page, tool).locator(FLAG)).to_have_text("1 notice")
    # A tool without a notice has no flag.
    expect(page.locator(FLAG)).to_have_count(2)
    # Fix both with "Use narrowed value", then Save: the indicator and flags clear, no reload.
    for tool in TOOLS:
        row = _row(page, tool)
        row.locator(".ui-tool-row-affordance").click()
        expect(row.locator(USE_NARROWED)).to_be_visible(timeout=8000)
        row.locator(USE_NARROWED).click()
    _save(page)
    expect(page.get_by_role("tab", name="Tools", exact=True)).to_have_count(1, timeout=8000)
    expect(page.locator(FLAG)).to_have_count(0)
    assert _agent(base, name)["notices"] == []


def test_a_dirty_editor_follows_a_settings_tightening_and_keeps_the_unsaved_edit(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _seed_overrides(base, name, tools=("http_request",))
    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}")
    description = page.locator('[data-field="description"]').first
    expect(description).to_be_visible(timeout=8000)
    description.fill("edited but not saved")
    expect(page.get_by_role("tab", name="Tools", exact=True)).to_have_count(1)
    # Another window tightens the setting; this one's store refreshes.
    _tighten(base, tools=("http_request",))
    _refresh_agents(page)
    expect(page.get_by_role("tab", name="Tools, 1 notice", exact=True)).to_have_count(
        1, timeout=8000
    )
    expect(description).to_have_value("edited but not saved")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()
    # ... and the flag is drawn from the notices, with the disclosure never opened.
    page.locator('[data-testid="tab-tools"]').click()
    _expand(page, "http_request")
    expect(_row(page, "http_request").locator(FLAG)).to_have_text("1 notice")
    # The tightening is undone elsewhere: both clear.
    _widen(base, tools=("http_request",))
    _refresh_agents(page)
    expect(page.get_by_role("tab", name="Tools", exact=True)).to_have_count(1, timeout=8000)
    expect(page.locator(FLAG)).to_have_count(0)
    page.locator('[data-testid="tab-general"]').click()
    expect(description).to_have_value("edited but not saved")


# -- AC3: the Agents list row -------------------------------------------------


def test_the_agents_row_gains_and_loses_the_needs_attention_badge(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _seed_overrides(base, name, tools=("http_request",))
    _nav.goto(page, base, "agents")
    row = page.locator('[data-testid="agent-item"]', has_text=name)
    expect(row).to_be_visible(timeout=8000)
    expect(row).not_to_contain_text("Needs attention")
    _tighten(base, tools=("http_request",))
    _refresh_agents(page)
    expect(row).to_contain_text("Needs attention", timeout=8000)
    # Visible text once, and the accessible name carries the phrase once.
    expect(page.get_by_role("link", name=re.compile(r", needs attention", re.I))).to_have_count(1)
    assert row.evaluate("(el) => el.textContent.match(/needs attention/gi).length") == 2
    # Fix it from the editor: the badge goes with no reload.
    row.click()
    page.locator('[data-testid="tab-tools"]').click()
    _expand(page, "http_request")
    panel = _row(page, "http_request")
    panel.locator(".ui-tool-row-affordance").click()
    expect(panel.locator(USE_NARROWED)).to_be_visible(timeout=8000)
    panel.locator(USE_NARROWED).click()
    _save(page)
    expect(row).not_to_contain_text("Needs attention", timeout=8000)
    expect(page.get_by_role("link", name=re.compile(r", needs attention", re.I))).to_have_count(0)

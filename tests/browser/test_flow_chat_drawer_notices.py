"""Sortie 07 leg 5 (DD12, AC4): the chat agent drawer's read-only "Needs attention" group.

It shows each tool-override notice's sentence and a link to the agent's Tools tab, only while
the agent has notices, and follows the ``agents`` store in both directions without a reload.
Falls in the ``chats`` lane (``test_flow_chat*``).
"""

from __future__ import annotations

import urllib.parse

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_tool_config
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NOTICES = '[data-testid="chat-drawer-notices"]'
LINK = '[data-testid="chat-drawer-notices-link"]'
SENTENCE = (
    "http_request's Extra allowed hosts was narrowed by the app-wide setting: "
    "`b.com` no longer applies."
)


def _put_agent(base: str, name: str, **changes) -> None:
    url = f"{base}/api/agents/{urllib.parse.quote(name)}"
    headers = auth_headers_for(base)
    cfg = httpx.get(url, timeout=5.0, headers=headers).json()
    cfg.update(changes)
    r = httpx.put(url, json=cfg, timeout=5.0, headers=headers)
    assert r.status_code == 200, r.text


def _hosts(base: str, hosts: list[str]) -> None:
    seed_tool_config(base, "http_request", config={"extra_allowed_hosts": hosts})


def _refresh_agents(page: Page) -> None:
    page.evaluate("() => App.store.get('agents', {force: true})")


def _start(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    expect(page.locator('[data-testid="chat-drawer-uses"]')).to_be_visible(timeout=8000)


def test_the_notices_group_appears_and_clears_with_the_agents_store(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _hosts(base, ["a.com", "b.com"])
    _put_agent(
        base, name, tool_overrides={"http_request": {"extra_allowed_hosts": ["a.com", "b.com"]}}
    )
    _start(page, base, name)
    expect(page.locator(NOTICES)).to_have_count(0)
    # A Settings tightening elsewhere; the store refreshes: the group appears, between the
    # facts and "What it can use", with the notice's own sentence and the link.
    _hosts(base, ["a.com"])
    _refresh_agents(page)
    group = page.locator(NOTICES)
    expect(group).to_have_count(1, timeout=8000)
    expect(group).to_contain_text(SENTENCE)
    order = page.evaluate(
        """() => Array.from(document.querySelector('.chat-drawer-content').children)
             .map((n) => n.getAttribute('data-testid') || n.className)"""
    )
    assert (
        order.index("chat-drawer-facts")
        < order.index("chat-drawer-notices")
        < order.index("chat-drawer-uses")
    )
    expect(page.locator(LINK)).to_have_attribute(
        "href", _nav.href(f"agents/{_nav.seg(urllib.parse.quote(name))}/tools")
    )
    # Read-only: the group holds no button or input.
    assert group.locator("button, input, textarea").count() == 0
    # The setting is relaxed again: the group goes, with no reload.
    _hosts(base, ["a.com", "b.com"])
    _refresh_agents(page)
    expect(page.locator(NOTICES)).to_have_count(0, timeout=8000)


def test_the_link_opens_the_agents_tools_tab(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _hosts(base, ["a.com", "b.com"])
    _put_agent(
        base, name, tool_overrides={"http_request": {"extra_allowed_hosts": ["a.com", "b.com"]}}
    )
    _hosts(base, ["a.com"])
    _start(page, base, name)
    expect(page.locator(NOTICES)).to_have_count(1, timeout=8000)
    page.locator(LINK).click()
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    assert page.evaluate("() => location.hash").endswith("/tools")

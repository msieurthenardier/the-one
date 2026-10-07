"""Focus after an in-place Library editor action (M25 F6 L1b, flight DD2).

MCP server, connector and knowledge-base editors, keyboard-driven (focus on the
button, then Enter): an edit-mode Save or Cancel leaves focus on the editor's
`.editor-title`; an MCP or connector Create lands on the new editor's title; the
MCP Test returns focus to its own button once it re-enables. Knowledge-base
create keeps focusing its folder-path input (squawk 0101), pinned in
`test_flow_studio_library_list.py`.
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_connector, seed_knowledge_base
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

TITLE = ".studio-section-content .editor-title"


def _press(page: Page, testid: str) -> None:
    btn = page.locator(f'[data-testid="{testid}"]')
    expect(btn).to_be_enabled()
    btn.focus()
    page.keyboard.press("Enter")


def _seed_mcp(base: str, name: str = "focus-mcp") -> str:
    r = httpx.post(
        f"{base}/api/mcp-sources",
        json={
            "name": name,
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
        headers=auth_headers_for(base),
        timeout=5.0,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ── MCP server ────────────────────────────────────────────────────────────


def test_mcp_save_cancel_and_test(app_clean: str, page: Page) -> None:
    sid = _seed_mcp(app_clean)
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "ok",
                    "tools": [],
                    "capabilities": {"tools": {}},
                }
            ),
        ),
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    # Cancel
    page.locator('[data-field="name"]').fill("reverted-name")
    _press(page, "cancel-mcp-source-btn")
    expect(page.locator('[data-testid="cancel-mcp-source-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    # Save
    page.locator('[data-field="name"]').fill("focus-mcp-renamed")
    _press(page, "save-mcp-source-btn")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    # Test connection
    btn = page.locator('[data-testid="mcp-test-connection"]')
    btn.focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-testid="mcp-test-status"]')).not_to_have_text(
        "Testing connection…", timeout=8000
    )
    expect(btn).to_be_enabled()
    expect(btn).to_be_focused(timeout=8000)


def test_mcp_create_lands_on_the_new_title(app_clean: str, page: Page) -> None:
    page.route(
        "**/api/mcp-sources/*/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "ok", "tools": [], "capabilities": {"tools": {}}}),
        ),
    )
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("created-mcp")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("some-mcp")
    _press(page, "save-mcp-source-btn")
    expect(page.locator(TITLE)).to_have_text("created-mcp", timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_mcp_http_create_survives_the_auto_run_refresh(app_clean: str, page: Page) -> None:
    """A streamable-http create auto-runs Refresh; that no-token click must not
    supersede the create's parked focus restore."""
    page.route(
        "**/api/mcp-sources/*/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "ok", "tools": [], "capabilities": {"tools": {}}}),
        ),
    )
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("created-http-mcp")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")
    _press(page, "save-mcp-source-btn")
    expect(page.locator(TITLE)).to_have_text("created-http-mcp", timeout=8000)
    expect(page.locator('[data-testid="mcp-test-status"]')).not_to_have_text(
        "Testing connection…", timeout=8000
    )
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


# ── Connector ─────────────────────────────────────────────────────────────


def test_connector_save_and_cancel(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    cid = seed_connector(base, "focus-conn", default_agent=app_with_agent.agent_name)
    _nav.goto_settled(page, base, f"library/connectors/{_nav.seg(cid)}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("reverted-conn")
    _press(page, "cancel-connector-btn")
    expect(page.locator('[data-testid="cancel-connector-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_have_text("focus-conn")
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    page.locator('[data-field="name"]').fill("focus-conn-renamed")
    _press(page, "save-connector-btn")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_connector_create_lands_on_the_new_title(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _nav.goto_settled(page, base, "library/connectors")
    _lists.library_add(page, "connectors")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("created-conn")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    _press(page, "save-connector-btn")
    expect(page.locator(TITLE)).to_have_text("created-conn", timeout=8000)
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


# ── Knowledge base ────────────────────────────────────────────────────────


def test_kb_save_and_cancel(app_clean: str, page: Page) -> None:
    kb_id = seed_knowledge_base(app_clean, "Focus KB")
    _nav.goto_settled(page, app_clean, f"library/knowledge/{_nav.seg(kb_id)}")
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=8000)
    name = page.locator('[data-testid="kb-name-input"]')
    name.fill("Reverted KB")
    _press(page, "cancel-knowledge-btn")
    expect(page.locator('[data-testid="cancel-knowledge-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_have_text("Focus KB")
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    name.fill("Focus KB renamed")
    _press(page, "save-knowledge-btn")
    expect(page.locator(TITLE)).to_have_text("Focus KB renamed", timeout=8000)
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)

"""End-to-end flow tests: hash routing with area/sub persistence.

Covers the #area/sub URL format introduced in leg 04:
- Admin sub-page persists across browser refresh (#admin/providers)
- Chat session persists across browser refresh (#chat/sessions/<id>)
- Studio agent persists across browser refresh (#studio/agents/<name>)
- history.length invariant: sub-page navigation uses replaceState, not pushState

F5 leg 01 extends this with:
- #studio redirects to #studio/agents (via the F3 router's serialize-after-hydrate
  path — no new redirect logic in studio.js)
- #studio/knowledge and #studio/tools survive refresh
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_hash_routing_admin_subpage_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Click Admin, click Providers — URL becomes #admin/providers, persists on refresh."""
    base_url = app_clean

    # 1. Open app (lands on #chat by default).
    page.goto(base_url)
    # Rail readiness probe: wait for the Chats rail link specifically.
    expect(_nav.destination_locator(page, "chats")).to_be_visible(timeout=5000)

    # 2. Navigate to Settings via the rail link.
    _nav.open_destination(page, "settings")

    # 3. Admin area is now active — Appearance is the default page (the first
    #    General page since M25 F3 leg 5a).
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=5000)

    # 4. Click the Providers link in the Settings nav.
    _lists.settings_nav_link(page, "providers").click()
    expect(page.locator(".page-title")).to_have_text("Providers", timeout=5000)

    # 5. URL should now be #admin/providers.
    _nav.expect_route(page, "settings/providers")

    # 6. Refresh the page.
    page.reload()

    # 7. After reload, app should land on admin/providers sub-page.
    # Wait for admin area to activate.
    expect(page.locator(".page-title")).to_have_text("Providers", timeout=8000)

    # The Providers link is the Settings nav's selected item (aria-current="page").
    _lists.expect_settings_selected(page, "providers")


@pytest.mark.browser
def test_hash_routing_chat_session_persists_on_refresh(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Session auto-created, URL becomes #chat/sessions/<id>, persists on refresh."""
    base_url = app_with_agent.base_url

    # 1. Open #chat. Welcome canvas shows; bootstrap a session.
    page.goto(base_url)
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()

    # 2. session_joined fires; agent badge updates and URL becomes
    #    #chat/sessions/<id>.
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    # 3. URL should now be #chat/sessions/<id> (set by session_joined handler).
    current_route = _nav.current_route(page)
    assert current_route.startswith("chats/"), f"Expected chats/<id>, got: {current_route}"
    session_id = current_route[len("chats/") :]
    assert session_id, "Session ID should not be empty"

    # 4. A session item should be selected in the sidebar.
    # F2 leg 01: active session marker switched from aria-selected="true"
    # (listbox-option semantic) to aria-current="page" (nav-page semantic).
    selected_item = page.locator('.session-item[aria-current="page"]')
    expect(selected_item).to_be_visible(timeout=5000)

    # 5. Refresh the page.
    page.reload()

    # 6. After reload, same session should be selected.
    # The session_joined handler fires after WS reconnects, which updates URL.
    # Wait for the specific session item to be marked selected.
    restored_item = page.locator(f'.session-item[data-id="{session_id}"][aria-current="page"]')
    expect(restored_item).to_be_visible(timeout=10000)

    # URL should still point to the same session.
    _nav.expect_route(page, f"chats/{_nav.seg(session_id)}")


@pytest.mark.browser
def test_hash_routing_studio_agent_persists_on_refresh(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Navigate to studio, select an agent — URL becomes #studio/agents/<name>, persists on refresh."""  # noqa: E501
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name  # "test-agent"

    # 1. Navigate to Studio.
    _nav.goto(page, base_url, "agents")

    # 2. Studio loads the seeded agent.
    agent_item = page.locator('[data-testid="agent-item"]')
    expect(agent_item).to_have_count(1, timeout=8000)

    # 3. Click the agent's list row to enter the editor (no auto-selection on
    #    bare #agents — F5 leg 02 design; M25 F3 L3 list column).
    agent_item.click()
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)

    # 4. URL should now be #studio/agents/<name>.
    current_route = _nav.current_route(page)
    expected_route = f"agents/{_nav.seg(agent_name)}/general"
    assert current_route == expected_route, f"Expected {expected_route}, got: {current_route}"

    # 5. Refresh the page.
    page.reload()

    # 6. After reload, the same agent should be selected in Studio.
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=10000)

    # Editor is the visible child of the main panel; tile grid is hidden.
    expect(page.locator(".studio-editor")).not_to_have_class("studio-editor is-hidden")
    expect(page.locator(".studio-section-content")).to_have_class(
        "studio-section-content is-hidden"
    )

    # URL should still be the same.
    _nav.expect_route(page, expected_route)


@pytest.mark.browser
def test_studio_root_redirects_to_agents(app_clean: str, page: Page) -> None:
    """Navigating to the legacy `#studio` rewrites the URL to `#agents`.

    A legacy-redirect proof (DD2): the router rewrites the hash with
    replaceState before the unknown-route check.
    """
    base_url = app_clean

    page.goto(f"{base_url}#studio")  # legacy URL on purpose: proves the redirect (AC6)
    # Wait for studio to mount.
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)

    # URL was rewritten by the F3 router (replaceState, not pushState).
    _nav.expect_route(page, "agents")


@pytest.mark.browser
def test_studio_knowledge_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """The legacy `#studio/knowledge` redirects to `#library/knowledge`; refresh preserves it."""
    base_url = app_clean

    page.goto(f"{base_url}#studio/knowledge")  # legacy URL on purpose (AC6)
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)

    # M25 F3 L4a: the section root is the Knowledge empty state beside the list.
    root = page.locator('[data-testid="library-empty-knowledge"]')
    expect(root).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/knowledge")

    page.reload()
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="library-empty-knowledge"]')).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/knowledge")


@pytest.mark.browser
def test_studio_mcp_sources_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to library/mcp shows the section root; refresh preserves the section.

    Post-F2 retrofit: replaces the test that previously asserted the
    "Tools" stub at #studio/tools. Since M25 F3 L4a the section root is the
    MCP empty state beside the Library list (the grid's page title is gone).
    """
    base_url = app_clean

    _nav.goto(page, base_url, "library/mcp")
    expect(page.locator('[data-testid="library-empty-mcp"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/mcp")

    page.reload()
    expect(page.locator('[data-testid="library-empty-mcp"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/mcp")


@pytest.mark.browser
def test_hash_routing_settings_nav_pushes_history(app_clean: str, page: Page) -> None:
    """Every user intent pushes one history entry; Back steps between them (DD4).

    This inverts the pre-router policy ("sub-page navigation uses replaceState"):
    a rail click and each Settings nav link click are `go()` calls that push,
    so Back walks Providers -> Appearance -> Chats. Area-internal canonicalisation
    (`sync`) stays replace and never grows history.

    Sequence:
      - Start on chats (baseline history.length = N)
      - Click rail Settings   (push, N+1)
      - Click Providers          (push, N+2)
      - Click Appearance         (push, N+3)
      - Back, Back, Back         -> providers, appearance, then chats
    """
    base_url = app_clean

    page.goto(base_url)
    expect(_nav.destination_locator(page, "chats")).to_be_visible(timeout=5000)
    baseline = page.evaluate("history.length")

    _nav.open_destination(page, "settings")
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=5000)
    assert page.evaluate("history.length") == baseline + 1

    _lists.settings_nav_link(page, "providers").click()
    expect(page.locator(".page-title")).to_have_text("Providers", timeout=5000)
    assert page.evaluate("history.length") == baseline + 2

    _lists.settings_nav_link(page, "appearance").click()
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=5000)
    assert page.evaluate("history.length") == baseline + 3

    page.go_back()
    expect(page.locator(".page-title")).to_have_text("Providers", timeout=5000)
    _nav.expect_route(page, "settings/providers")
    page.go_back()
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=5000)
    _nav.expect_route(page, "settings/appearance")
    page.go_back()
    expect(_nav.destination_panel(page, "chats")).to_be_visible(timeout=5000)
    assert _nav.current_route(page).split("/")[0] == "chats"

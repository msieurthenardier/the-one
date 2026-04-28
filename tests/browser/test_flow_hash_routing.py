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
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_hash_routing_admin_subpage_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Click Admin, click Providers — URL becomes #admin/providers, persists on refresh."""
    base_url = app_clean

    # 1. Open app (lands on #chat by default).
    page.goto(base_url)
    expect(page.locator(".app-picker-button")).to_be_visible(timeout=5000)

    # 2. Navigate to Admin via picker.
    page.locator(".app-picker-button").click()
    page.locator('.app-picker-option[data-area="admin"]').click()

    # 3. Admin area is now active — General category is the default.
    expect(page.locator(".admin-title")).to_have_text("General Settings", timeout=5000)

    # 4. Click the Providers category.
    providers_item = page.locator(".admin-category-item").filter(has_text="LLM Providers")
    providers_item.click()
    expect(page.locator(".admin-title")).to_have_text("LLM Providers", timeout=5000)

    # 5. URL should now be #admin/providers.
    assert page.evaluate("location.hash") == "#admin/providers"

    # 6. Refresh the page.
    page.reload()

    # 7. After reload, app should land on admin/providers sub-page.
    # Wait for admin area to activate.
    expect(page.locator(".admin-title")).to_have_text("LLM Providers", timeout=8000)

    # Providers category should be marked active.
    active_cat = page.locator(".admin-category-item.active")
    expect(active_cat).to_contain_text("LLM Providers")


@pytest.mark.browser
def test_hash_routing_chat_session_persists_on_refresh(app_with_agent: SeededApp, page: Page) -> None:
    """Session auto-created, URL becomes #chat/sessions/<id>, persists on refresh."""
    base_url = app_with_agent.base_url

    # 1. Open #chat. Welcome canvas shows; bootstrap a session.
    page.goto(base_url)
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()

    # 2. session_joined fires; agent badge updates and URL becomes
    #    #chat/sessions/<id>.
    expect(page.locator(".session-agent-badge")).to_have_text(app_with_agent.agent_name, timeout=8000)

    # 3. URL should now be #chat/sessions/<id> (set by session_joined handler).
    current_hash = page.evaluate("location.hash")
    assert current_hash.startswith("#chat/sessions/"), f"Expected #chat/sessions/<id>, got: {current_hash}"
    session_id = current_hash[len("#chat/sessions/"):]
    assert session_id, "Session ID should not be empty"

    # 4. A session item should be selected in the sidebar.
    selected_item = page.locator('.session-item[aria-selected="true"]')
    expect(selected_item).to_be_visible(timeout=5000)

    # 5. Refresh the page.
    page.reload()

    # 6. After reload, same session should be selected.
    # The session_joined handler fires after WS reconnects, which updates URL.
    # Wait for the specific session item to be marked selected.
    restored_item = page.locator(f'.session-item[data-id="{session_id}"][aria-selected="true"]')
    expect(restored_item).to_be_visible(timeout=10000)

    # URL should still point to the same session.
    assert page.evaluate("location.hash") == f"#chat/sessions/{session_id}"


@pytest.mark.browser
def test_hash_routing_studio_agent_persists_on_refresh(app_with_agent: SeededApp, page: Page) -> None:
    """Navigate to studio, select an agent — URL becomes #studio/agents/<name>, persists on refresh."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name  # "test-agent"

    # 1. Navigate to Studio.
    page.goto(f"{base_url}#studio")

    # 2. Studio loads the seeded agent.
    agent_item = page.locator('[data-testid="agent-item"]')
    expect(agent_item).to_have_count(1, timeout=8000)

    # 3. Click the agent in the sidebar (it may already be selected; click to confirm).
    agent_item.click()
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)

    # 4. URL should now be #studio/agents/<name>.
    current_hash = page.evaluate("location.hash")
    import urllib.parse
    expected_hash = f"#studio/agents/{urllib.parse.quote(agent_name)}/general"
    assert current_hash == expected_hash, f"Expected {expected_hash}, got: {current_hash}"

    # 5. Refresh the page.
    page.reload()

    # 6. After reload, the same agent should be selected in Studio.
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=10000)

    # Agent item should be marked active in sidebar.
    active_item = page.locator(f'.agent-item[data-name="{agent_name}"][aria-selected="true"]')
    expect(active_item).to_be_visible(timeout=5000)

    # URL should still be the same.
    assert page.evaluate("location.hash") == expected_hash


@pytest.mark.browser
def test_studio_root_redirects_to_agents(app_clean: str, page: Page) -> None:
    """Navigating to #studio rewrites the URL to #studio/agents.

    The redirect is a free side-effect of studio.serializeState() returning
    'agents' (not null) when no agent is selected. The F3 router's
    serialize-after-hydrate path at app.js:179-185 detects the mismatch
    (sub=null vs serialized='agents') and calls history.replaceState.
    """
    base_url = app_clean

    page.goto(f"{base_url}#studio")
    # Wait for studio to mount.
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)

    # URL was rewritten by the F3 router (replaceState, not pushState).
    assert page.evaluate("location.hash") == "#studio/agents"


@pytest.mark.browser
def test_studio_knowledge_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/knowledge shows the stub; refresh preserves the section."""
    base_url = app_clean

    page.goto(f"{base_url}#studio/knowledge")
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)

    stub = page.locator('[data-testid="studio-knowledge-stub"]')
    expect(stub).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/knowledge"

    page.reload()
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)
    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/knowledge"


@pytest.mark.browser
def test_studio_tools_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/tools shows the stub; refresh preserves the section."""
    base_url = app_clean

    page.goto(f"{base_url}#studio/tools")
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)

    stub = page.locator('[data-testid="studio-tools-stub"]')
    expect(stub).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/tools"

    page.reload()
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)
    expect(page.locator('[data-testid="studio-tools-stub"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/tools"


@pytest.mark.browser
def test_hash_routing_replacestate_no_history_growth(app_clean: str, page: Page) -> None:
    """Sub-page navigation uses replaceState: history.length grows by 1 per cross-area nav only.

    Design invariant: AREA-INTERNAL sub navigation (admin category clicks) uses
    history.replaceState, which does NOT add to history. Only cross-area navigation
    (picker click) pushes a new history entry.

    Sequence:
      - Start on chat (baseline history.length = N)
      - Click picker → admin  (cross-area: pushes, length = N+1)
      - Click Providers        (replaceState: no push, length = N+1)
      - Click System           (replaceState: no push, length = N+1)

    Final length must equal baseline + 1.
    """
    base_url = app_clean

    # 1. Open app.
    page.goto(base_url)
    expect(page.locator(".app-picker-button")).to_be_visible(timeout=5000)

    # 2. Capture baseline history.length (after initial load).
    baseline = page.evaluate("history.length")

    # 3. Navigate to Admin via picker (cross-area — pushes history).
    page.locator(".app-picker-button").click()
    page.locator('.app-picker-option[data-area="admin"]').click()
    expect(page.locator(".admin-title")).to_have_text("General Settings", timeout=5000)

    after_cross_area = page.evaluate("history.length")
    assert after_cross_area == baseline + 1, (
        f"Cross-area navigation should push history: baseline={baseline}, "
        f"after_cross_area={after_cross_area}"
    )

    # 4. Click Providers (sub-page change within admin — replaceState, no push).
    providers_item = page.locator(".admin-category-item").filter(has_text="LLM Providers")
    providers_item.click()
    expect(page.locator(".admin-title")).to_have_text("LLM Providers", timeout=5000)

    after_providers = page.evaluate("history.length")
    assert after_providers == baseline + 1, (
        f"Admin sub-page click should NOT push history (replaceState): "
        f"after_cross_area={after_cross_area}, after_providers={after_providers}"
    )

    # 5. Click System (another sub-page change — replaceState, no push).
    system_item = page.locator(".admin-category-item").filter(has_text="System")
    system_item.click()
    expect(page.locator(".admin-title")).to_have_text("System", timeout=5000)

    after_system = page.evaluate("history.length")
    assert after_system == baseline + 1, (
        f"Admin sub-page click should NOT push history (replaceState): "
        f"after_providers={after_providers}, after_system={after_system}"
    )

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

L7.1 Holograph selector migration:
- .app-picker-button → .navlink (topnav area buttons; no picker overlay)
- .app-picker-option[data-area="X"] → .navlink[data-area="X"]
- .section-nav-header → removed (Holograph subnav has no header element)
  Replaced with .area-{X} .section-nav-item as a ready-signal
- .session-item → .session-card (history-buckets.js rename)
- .session-item[data-id="…"] → .session-card[data-session-id="…"]
  (dataset key renamed from data-id to data-session-id in L3.2)
- .session-agent-badge → .convo-agent (Holograph convo-header)
- .studio-editor / .studio-section-content is-hidden toggles removed —
  Holograph uses a CSS side-by-side grid; both panels are always visible
  within the active sub-block. Test replaced with .editor-title assertion.
- .area-studio .page-title (MCP Servers) → active section-nav item
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
    # Holograph: area navigation is via .navseg buttons in the topnav
    # (M10 L2.2 — mono coord segments; renamed from .navlink).
    expect(page.locator(".navseg").first).to_be_visible(timeout=5000)

    # 2. Navigate to Admin via topnav.
    page.locator('.navseg[data-area="admin"]').click()

    # 3. Admin area is now active — General category is the default.
    # Scope to the active sub-block to avoid strict-mode violations when
    # multiple .page-title elements exist simultaneously in the DOM.
    expect(page.locator(".area-admin .admin-sub.active .page-title")).to_have_text("General", timeout=5000)

    # 4. Click the Providers category.
    providers_item = page.locator(".area-admin .section-nav-item").filter(has_text="LLM Providers")
    providers_item.click()
    expect(page.locator(".area-admin .admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=5000)

    # 5. URL should now be #admin/providers.
    assert page.evaluate("location.hash") == "#admin/providers"

    # 6. Refresh the page.
    page.reload()

    # 7. After reload, app should land on admin/providers sub-page.
    # Wait for admin area to activate.
    expect(page.locator(".area-admin .admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=8000)

    # Providers category should be marked active (aria-current="page" via section-nav).
    active_cat = page.locator('.area-admin .section-nav-item[aria-current="page"]')
    expect(active_cat).to_contain_text("LLM Providers")


@pytest.mark.browser
def test_hash_routing_chat_session_persists_on_refresh(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Session auto-created, URL becomes #chat/sessions/<id>, persists on refresh."""
    base_url = app_with_agent.base_url

    # 1. Open #chat. Welcome canvas shows; bootstrap a session.
    page.goto(base_url)
    # Holograph welcome: agent picker uses .chat-agent-card (was .chat-welcome-item).
    # Holograph L4.1: welcome listbox is gone; the `+` button starts a session
    # using the first available agent (which is the seeded agent in tests).
    expect(
        page.locator(".chat-empty .eyebrow:has-text('HOLOGRAPH · CHAT · READY')")
    ).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-chat-btn"]').click()

    # 2. session_joined fires; convo-header updates with the agent name.
    # Holograph: .convo-agent (was .session-agent-badge) shows agent name.
    expect(page.locator(".convo-agent")).to_contain_text(
        app_with_agent.agent_name, timeout=8000
    )

    # 3. URL should now be #chat/sessions/<id> (set by session_joined handler).
    current_hash = page.evaluate("location.hash")
    assert current_hash.startswith("#chat/sessions/"), (
        f"Expected #chat/sessions/<id>, got: {current_hash}"
    )
    session_id = current_hash[len("#chat/sessions/"):]
    assert session_id, "Session ID should not be empty"

    # 4. A session card should be selected in the sessions pane.
    # Holograph: .session-card (was .session-item).
    selected_item = page.locator('.session-card[aria-selected="true"]')
    expect(selected_item).to_be_visible(timeout=5000)

    # 5. Refresh the page.
    page.reload()

    # 6. After reload, same session should be selected.
    # The session_joined handler fires after WS reconnects, which updates URL.
    # Holograph: data-session-id (was data-id) attribute on .session-card.
    restored_item = page.locator(f'.session-card[data-session-id="{session_id}"][aria-selected="true"]')
    expect(restored_item).to_be_visible(timeout=10000)

    # URL should still point to the same session.
    assert page.evaluate("location.hash") == f"#chat/sessions/{session_id}"


@pytest.mark.browser
def test_hash_routing_studio_agent_persists_on_refresh(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Navigate to studio, select an agent — URL becomes #studio/agents/<name>, persists on refresh."""  # noqa: E501
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name  # "test-agent"

    # 1. Navigate to Studio.
    page.goto(f"{base_url}#studio")

    # 2. Studio loads the seeded agent.
    agent_item = page.locator('[data-testid="agent-item"]')
    expect(agent_item).to_have_count(1, timeout=8000)

    # 3. Click the agent card to enter the editor (no auto-selection on
    #    bare #studio/agents — F5 leg 02 design).
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

    # Holograph: both agents pane and editor pane are side-by-side in a CSS grid;
    # no is-hidden toggling. Verify the editor has content (title visible).
    expect(page.locator(".editor-title")).to_be_visible()

    # URL should still be the same.
    assert page.evaluate("location.hash") == expected_hash


@pytest.mark.browser
def test_studio_root_redirects_to_agents(app_clean: str, page: Page) -> None:
    """Navigating to #studio rewrites the URL to #studio/agents.

    The redirect is a free side-effect of studio.serializeState() returning
    'agents' (not null) when no agent is selected. The F3 router's
    serialize-after-hydrate path at app.js:179-185 detects the mismatch
    (sub=null vs serialized='agents') and calls history.replaceState.

    Holograph: the studio subnav has no .section-nav-header element;
    use the first .section-nav-item in .area-studio as the ready-signal.
    """
    base_url = app_clean

    page.goto(f"{base_url}#studio")
    # Wait for studio section nav to mount (Holograph: no header, just items).
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=8000)

    # URL was rewritten by the F3 router (replaceState, not pushState).
    assert page.evaluate("location.hash") == "#studio/agents"


@pytest.mark.browser
def test_studio_knowledge_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/knowledge shows the stub; refresh preserves the section."""
    base_url = app_clean

    page.goto(f"{base_url}#studio/knowledge")
    # Wait for studio section nav to mount (Holograph: no header, just items).
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=8000)

    stub = page.locator('[data-testid="studio-knowledge-stub"]')
    expect(stub).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/knowledge"

    page.reload()
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/knowledge"


@pytest.mark.browser
def test_studio_mcp_sources_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/mcp-sources shows the page; refresh preserves the section.

    Post-F2 retrofit: replaces the test that previously asserted the
    "Tools" stub at #studio/tools — the third nav slot is now MCP Servers.

    Holograph: no .page-title in studio; use the active section-nav item
    text to assert the MCP Servers section is selected.
    """
    base_url = app_clean

    page.goto(f"{base_url}#studio/mcp-sources")
    # Wait for studio section nav to mount and MCP Servers item to be active.
    active_item = page.locator('.area-studio .section-nav-item[aria-current="page"]')
    expect(active_item).to_contain_text("MCP Servers", timeout=8000)
    assert page.evaluate("location.hash") == "#studio/mcp-sources"

    page.reload()
    active_item = page.locator('.area-studio .section-nav-item[aria-current="page"]')
    expect(active_item).to_contain_text("MCP Servers", timeout=8000)
    assert page.evaluate("location.hash") == "#studio/mcp-sources"


@pytest.mark.browser
def test_hash_routing_replacestate_no_history_growth(app_clean: str, page: Page) -> None:
    """Sub-page navigation uses replaceState: history.length grows by 1 per cross-area nav only.

    Design invariant: AREA-INTERNAL sub navigation (admin category clicks) uses
    history.replaceState, which does NOT add to history. Only cross-area navigation
    (topnav click) pushes a new history entry.

    Sequence:
      - Start on chat (baseline history.length = N)
      - Click topnav → admin  (cross-area: pushes, length = N+1)
      - Click Providers        (replaceState: no push, length = N+1)
      - Click General          (replaceState: no push, length = N+1)

    Final length must equal baseline + 1.
    """
    base_url = app_clean

    # 1. Open app.
    page.goto(base_url)
    # Holograph: area buttons are .navseg in the topnav (no picker overlay).
    expect(page.locator(".navseg").first).to_be_visible(timeout=5000)

    # 2. Capture baseline history.length (after initial load).
    baseline = page.evaluate("history.length")

    # 3. Navigate to Admin via topnav (cross-area — pushes history).
    page.locator('.navseg[data-area="admin"]').click()
    # Scope to active sub-block to avoid strict-mode violations (multiple
    # .page-title elements exist simultaneously in the DOM).
    expect(page.locator(".area-admin .admin-sub.active .page-title")).to_have_text("General", timeout=5000)

    after_cross_area = page.evaluate("history.length")
    assert after_cross_area == baseline + 1, (
        f"Cross-area navigation should push history: baseline={baseline}, "
        f"after_cross_area={after_cross_area}"
    )

    # 4. Click Providers (sub-page change within admin — replaceState, no push).
    providers_item = page.locator(".area-admin .section-nav-item").filter(has_text="LLM Providers")
    providers_item.click()
    expect(page.locator(".area-admin .admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=5000)

    after_providers = page.evaluate("history.length")
    assert after_providers == baseline + 1, (
        f"Admin sub-page click should NOT push history (replaceState): "
        f"after_cross_area={after_cross_area}, after_providers={after_providers}"
    )

    # 5. Click General (another sub-page change — replaceState, no push).
    system_item = page.locator(".area-admin .section-nav-item").filter(has_text="General")
    system_item.click()
    expect(page.locator(".area-admin .admin-sub.active .page-title")).to_have_text("General", timeout=5000)

    after_system = page.evaluate("history.length")
    assert after_system == baseline + 1, (
        f"Admin sub-page click should NOT push history (replaceState): "
        f"after_providers={after_providers}, after_system={after_system}"
    )


@pytest.mark.browser
def test_cross_area_switch_unmounts_previous_area(app_clean: str, page: Page) -> None:
    """Cross-area navigation must hide the previous area's DOM.

    Regression test for the lifecycle bug where clicking a topnav area
    button (e.g. System from Studio) appended the new area's content-panel
    BELOW the previous one without hiding the previous panel. The
    ``.content-panel`` element has no CSS rule governing visibility, so the
    ``.active`` class toggle alone was insufficient — both panels remained
    visible until a hard reload. The fix toggles inline ``display`` on the
    panels at the router level.
    """
    page.goto(f"{app_clean}#studio")
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=8000)

    # Both panels must exist in the DOM after switching (lazy-init keeps them
    # around), but only the active one may be visible.
    page.locator('.navseg[data-area="admin"]').click()
    expect(page.locator(".area-admin .admin-sub.active .page-title")).to_have_text(
        "General", timeout=5000
    )

    # The outgoing panel still exists (initialized=true) but must be hidden.
    studio_panel = page.locator("#main-content > .area-studio")
    admin_panel = page.locator("#main-content > .area-admin")
    expect(studio_panel).to_have_count(1)
    expect(admin_panel).to_have_count(1)
    expect(studio_panel).not_to_be_visible()
    expect(admin_panel).to_be_visible()

    # Switch back to Studio and verify the inverse.
    page.locator('.navseg[data-area="studio"]').click()
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=5000)
    expect(studio_panel).to_be_visible()
    expect(admin_panel).not_to_be_visible()

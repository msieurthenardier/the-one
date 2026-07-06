"""Deterministic save→delete race regression (M17 F5 L1).

Guards the null-``found`` fallback added to the agent-editor save re-select
(studio.js). Before the fix the save chain was ``if (found) {…}`` with NO
``else``: if a concurrent DELETE removed the agent between the PUT resolving and
the follow-up ``loadAll()``, ``found`` came back null and the block silently
no-op'd, stranding a stale editor over a now-gone agent. ``handleDeleteEditor``
and ``_refresh`` already fell through to first-agent / empty; the fix gives save
the same fallback.

This is NOT a wall-clock race (the F1-debrief reviewer confirmed the interleave
is inherently racy at the Witnessed/browser level). Instead the post-PUT
``GET /api/agents`` (loadAll) is route-stubbed to return an empty list — the
exact observable of "a concurrent delete removed this agent" — so the fallback
branch is exercised deterministically. The PUT itself (``/api/agents/{name}``,
a longer path) is NOT intercepted by the ``**/api/agents`` glob and hits the
real server, so the chain reaches loadAll exactly as in production.
"""

from __future__ import annotations

import re

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_save_after_concurrent_delete_falls_back_to_empty(
    app_with_provider: SeededApp, page: Page
) -> None:
    base_url = app_with_provider.base_url

    # 1. Create an agent through the normal flow so it exists + is selected.
    page.goto(f"{base_url}#studio")
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent")
    page.locator('[data-field="name"]').fill("race-agent")
    page.locator('[data-field="description"]').fill("Original")
    expect(page.locator("#studio-provider")).to_have_value(app_with_provider.provider_id)
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=5000)
    page.locator("#studio-model").select_option("mock-default")
    page.locator('[data-testid="save-agent-btn"]').click()

    agent_item = page.locator('[data-testid="agent-item"]')
    expect(agent_item).to_have_count(1)
    expect(page.locator(".editor-title")).to_have_text("race-agent")

    # 2. Make the editor dirty (an edit to save).
    page.locator('[data-field="description"]').fill("Edited under a race")
    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).to_be_enabled()

    # 3. Stub the NEXT loadAll (GET /api/agents) to report an empty roster —
    #    i.e. a concurrent DELETE removed the agent between the PUT resolving
    #    and loadAll. The glob matches only the exact collection path, so the
    #    PUT to /api/agents/race-agent passes through to the real server.
    def handle_agents(route):
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json", body="[]")
        else:
            route.continue_()

    page.route("**/api/agents", handle_agents)

    # 4. Save. PUT succeeds; loadAll returns []; found is null. With the fix the
    #    save chain falls through to the empty state instead of leaving a stale
    #    editor mounted over a now-gone agent.
    save_btn.click()

    # 5. Empty state restored, editor hidden — the null-found fallback fired.
    empty = page.locator('[data-testid="agent-empty"]')
    expect(empty).to_be_visible(timeout=5000)
    expect(page.locator(".studio-editor")).to_have_class(re.compile(r"\bis-hidden\b"))
    # The stale editor for the vanished agent is NOT still showing.
    expect(page.locator(".editor-title")).to_have_count(0)

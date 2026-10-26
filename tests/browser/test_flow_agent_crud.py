"""End-to-end flow test: Studio agent CRUD.

Drives a real Chromium session through the agent lifecycle:
- Empty Agents destination (mock provider already seeded by fixture)
- Click "New" in the agents list to open the create form (``#agents/~new``)
- Fill form (name, description, provider, model, system prompt)
- Click Create — agent appears in the list, editor switches to edit mode
- Edit description, click Save — change persists
- Click Delete (two-click confirm) — agent removed, empty state restored
"""

from __future__ import annotations

import re

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

# History (M08 F4 → M17 F1 → M17 F3): this module was skipped as "hangs, root
# cause unidentified". The hang itself was fixed by the F5 L01 SQLite-isolation
# fix in tests/conftest.py; the remaining deterministic failure was root-caused
# in M17 F1 L02 as the state-split create CTA (the affordance moved between an
# in-canvas `-empty` variant and a hidden-when-empty header button). M17 F3 L3
# unified the CTA: the header button (data-testid="new-agent-btn") is always
# visible with an icon + text label in BOTH empty and populated grid states,
# and the `-empty` testid variants are retired. Tests target the one unified
# testid throughout. M25 F3 L3 moved it into the agents list column's title row
# ("New") and made create a route (``#agents/~new``).


def _is_agents_list_get(r) -> bool:
    return r.request.method == "GET" and r.url.split("?")[0].endswith("/api/agents")


def _is_agents_post(r) -> bool:
    return r.request.method == "POST" and r.url.split("?")[0].endswith("/api/agents")


@pytest.mark.browser
def test_studio_agent_crud_flow(app_with_provider: SeededApp, page: Page) -> None:
    base_url = app_with_provider.base_url

    # 1. Open Agents. The detail pane's empty state shows "No agents yet".
    #    Wait for the network to settle, not just for the empty state to show:
    #    first activation runs loadAll() twice (init() and
    #    activate()->_refresh()); a slow second pass lands after the
    #    create/delete below and re-renders the list from a stale copy.
    #    goto_settled lets both passes finish first.
    _nav.goto_settled(page, base_url, "agents")
    empty = page.locator('[data-testid="agent-empty"]')
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("No agents yet")

    # 2. Click the list's "New" to enter create mode. It is visible even with
    #    zero agents (M17 F3 L3 CTA unification); create is a route.
    _lists.agents_new(page)

    # 3-4. Fill name and description.
    page.locator('[data-field="name"]').fill("test-agent")
    page.locator('[data-field="description"]').fill("An agent for tests")

    # 5. Provider dropdown auto-selected (only one — the seeded mock provider).
    expect(page.locator("#studio-provider")).to_have_value(app_with_provider.provider_id)

    # 6-7. Wait for model dropdown to populate; select "mock-default".
    #      The fetch fires on initial render via fetchModelsForProvider.
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=5000)
    page.locator("#studio-model").select_option("mock-default")

    # 8. Fill system prompt.
    page.locator('[data-field="system_prompt"]').fill("You are a test agent.")

    # 9. Click Create. The list is repainted by the loadAll() that follows the
    #    POST, so wait for that list refetch (a network response, not a timeout).
    with (
        page.expect_response(_is_agents_post) as create_resp,
        page.expect_response(_is_agents_list_get),
    ):
        page.locator('[data-testid="save-agent-btn"]').click()
    assert create_resp.value.status == 201, f"POST failed: {create_resp.value.status}"

    # 10. The list contains exactly one agent row with our name, selected.
    agent_item = page.locator('[data-testid="agent-item"]')
    expect(agent_item).to_have_count(1)
    expect(agent_item).to_contain_text("test-agent")
    _lists.expect_selected(page, "agents", "test-agent")

    # 11. Editor switched to edit mode — title shows agent name, Delete agent visible.
    expect(page.locator(".editor-title")).to_have_text("test-agent")
    delete_btn = page.locator('[data-testid="delete-agent-btn"]')
    expect(delete_btn).to_be_visible()
    expect(delete_btn).to_have_text("Delete agent")

    # 12-13. Edit description, save, verify persisted (re-render keeps the value).
    description_input = page.locator('[data-field="description"]')
    description_input.fill("Edited description")
    save_btn = page.locator('[data-testid="save-agent-btn"]')
    save_btn.click()
    # After save, editor re-renders with updated agent. Description still set.
    expect(page.locator('[data-field="description"]')).to_have_value(
        "Edited description", timeout=5000
    )
    # Synchronize with the END of the save chain before deleting: the PUT
    # handler runs loadAll() + renderEditor() asynchronously (studio.js save
    # flow), and its stale continuation can otherwise interleave with the
    # delete below under CPU load — re-selecting the just-deleted agent and
    # keeping the editor mounted over the empty grid (observed as a
    # suite-only flake in M17 F1 L02). The re-rendered editor's Save button
    # is disabled (clean state) — same sync idiom as the MCPs/Tools tests.
    expect(save_btn).to_be_disabled(timeout=5000)

    # 14. First click on Delete — confirm state ("Confirm delete?"). The
    # armed state auto-reverts after 3s (App.confirmDelete revertMs), so the
    # second click follows immediately.
    delete_btn.click()
    expect(delete_btn).to_have_text("Confirm delete?")

    # 15. Second click — DELETE fires, agent removed, empty state returns.
    #     expect_response makes a silent re-arm (revert-window expiry under
    #     load) fail loudly as a missing-DELETE timeout instead of a
    #     confusing downstream visibility failure.
    #     The list refetch that repaints the (now empty) list follows the DELETE;
    #     wait for it too so the visibility checks below race nothing.
    with (
        page.expect_response(
            lambda r: "/api/agents/" in r.url and r.request.method == "DELETE"
        ) as delete_resp,
        page.expect_response(_is_agents_list_get),
    ):
        delete_btn.click()
    assert delete_resp.value.status == 200, (
        f"DELETE failed: {delete_resp.value.status} {delete_resp.value.text()}"
    )
    expect(empty).to_be_visible(timeout=5000)
    expect(empty).to_contain_text("No agents yet")
    # Row gone; the detail pane returns to its empty state.
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(0)
    # Regex (not exact class string) — only `is-hidden` is the contract here.
    expect(page.locator(".studio-editor")).to_have_class(re.compile(r"\bis-hidden\b"))


@pytest.mark.browser
def test_delete_agent_confirm_lapse_is_visually_distinct(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the agent editor's
    Delete confirm (`studio.js:2080`) is distinguishable on screen from one
    that was never armed, past the real 3s `revertMs`."""
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    _lists.open_item(page, "agents", app_with_agent.agent_name)
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )

    delete_btn = page.locator('[data-testid="delete-agent-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_text("Confirm delete?")
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_have_text("Delete agent")
    # Never committed: the agent is still there.
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(1)

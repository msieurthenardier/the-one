"""Browser tests for M11 F9 L5 — operator-driven detach + grid badge.

Verifies that:
- The connector account detail page's "Attached Agents" table renders
  a per-row Detach button; clicking it issues
  ``DELETE /api/agents/{name}/connectors/{id}``, the row
  disappears from the rendered table, and the agent's
  ``connector_ids`` no longer contains the account (verified
  via direct API GET).
- The Connectors grid tile renders the agent-count badge in the
  ``entity-tile-meta`` slot. The three plural/singular/zero forms
  (``"2 agents"`` / ``"1 agent"`` / ``"No agents"``) are exercised in
  a single navigation.

Mirrors ``tests/browser/test_flow_studio_connector_editor.py``
for the create/edit-mode fixtures and ``seed_*`` helper imports.
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import seed_connector, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _get_agent(base_url: str, agent_name: str) -> dict:
    r = httpx.get(f"{base_url}/api/agents/{agent_name}", timeout=5.0)
    assert r.status_code == 200, f"get agent failed: {r.status_code} {r.text}"
    return r.json()


def _attach_agent_to_account(base_url: str, agent_name: str, account_id: str) -> None:
    """Mutate an existing agent so its ``connector_ids`` includes
    ``account_id``. PUT /api/agents is REPLACE semantic — we GET the
    current config first and re-PUT with the connector id appended.

    Mirrors the helper in ``test_flow_studio_connector_editor.py``.
    """
    cfg = _get_agent(base_url, agent_name)
    ids = list(cfg.get("connector_ids") or [])
    if account_id not in ids:
        ids.append(account_id)
    cfg["connector_ids"] = ids
    r = httpx.put(f"{base_url}/api/agents/{agent_name}", json=cfg, timeout=5.0)
    assert r.status_code == 200, f"attach agent failed: {r.status_code} {r.text}"


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_detach_button_removes_agent_from_attached_list(app_clean: str, page: Page) -> None:
    """Seed a connector account + an agent attached to it; navigate to
    the detail page; click Detach on the agent's row; verify the row
    disappears and the agent's ``connector_ids`` is empty."""
    provider_id = seed_mock_provider(app_clean)
    agent_name = seed_mock_agent(app_clean, provider_id, name="detach-target-agent")
    account_id = seed_connector(app_clean, name="Detach Bot")
    _attach_agent_to_account(app_clean, agent_name, account_id)

    # Sanity precondition: API GET reports the attachment.
    assert account_id in _get_agent(app_clean, agent_name)["connector_ids"]

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    # The attached-agents table renders the agent's row + Detach button.
    row = page.locator(f'[data-testid="connector-attached-agent-{agent_name}"]')
    expect(row).to_have_count(1, timeout=5000)
    detach_btn = page.locator(f'[data-testid="connector-attached-agent-detach-{agent_name}"]')
    expect(detach_btn).to_have_count(1)
    expect(detach_btn).to_have_text("Detach")

    detach_btn.click()

    # Row disappears from the re-rendered table.
    expect(row).to_have_count(0, timeout=5000)
    # No detach-error message rendered.
    expect(page.locator(".connector-attached-agent-detach-error")).to_have_count(0)

    # Server-side: the agent's connector_ids no longer contains the account.
    after = _get_agent(app_clean, agent_name)
    assert account_id not in (after.get("connector_ids") or [])


@pytest.mark.browser
def test_connectors_grid_displays_attached_agents_count(app_clean: str, page: Page) -> None:
    """Seed three accounts (2/1/0 agents attached) and verify the grid
    tile renders the singular/plural/zero forms of the agent-count
    badge.
    """
    provider_id = seed_mock_provider(app_clean)
    seed_mock_agent(app_clean, provider_id, name="grid-agent-1")
    seed_mock_agent(app_clean, provider_id, name="grid-agent-2")

    # Account A — 2 attached agents → "2 agents".
    account_a = seed_connector(app_clean, name="Two Agents Bot")
    _attach_agent_to_account(app_clean, "grid-agent-1", account_a)
    _attach_agent_to_account(app_clean, "grid-agent-2", account_a)

    # Account B — 1 attached agent → "1 agent" (singular).
    account_b = seed_connector(app_clean, name="One Agent Bot")
    # Re-use grid-agent-1: PUT-replace semantic means we need the agent's
    # current connector_ids preserved + the new account appended.
    _attach_agent_to_account(app_clean, "grid-agent-1", account_b)

    # Account C — 0 attached agents → "No agents".
    seed_connector(app_clean, name="Zero Agents Bot")

    page.goto(f"{app_clean}#studio/connectors")
    expect(page.locator('[data-testid="connector-card"]')).to_have_count(3, timeout=8000)

    tile_a = page.locator(f'[data-testid="connector-card"][data-id="{account_a}"]')
    tile_b = page.locator(f'[data-testid="connector-card"][data-id="{account_b}"]')
    tile_c = page.locator('[data-testid="connector-card"]', has_text="Zero Agents Bot")

    expect(tile_a.locator(".entity-tile-meta")).to_have_text("2 agents")
    expect(tile_b.locator(".entity-tile-meta")).to_have_text("1 agent")
    expect(tile_c.locator(".entity-tile-meta")).to_have_text("No agents")

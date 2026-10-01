"""Browser tests for the Self-configuration tab approval mode + revision
queue (M21 F02 L02, AC13/AC14).

Mirrors ``test_flow_chat_pending_*.py``'s direct-sqlite seeding pattern:
seed an agent via httpx, then INSERT ``agent_revisions`` pending rows via
sync sqlite3, drive the tab, and assert the rendered-state swaps and the
approval-mode toggle persistence.

Covers:
  1. The per-agent pending count reflects seeded pending rows; cards show
     base→proposed.
  2. A clean approve applies the revision (store updated) and the resolved
     row leaves the pending list after the re-render.
  3. Dismiss removes the row from the pending list.
  4. A staleness 409 renders current-vs-proposed with an override button.
  5. The approval-mode toggle persists (round-trips through status()).
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _seed_agent(base_url: str, name: str, description: str = "seed desc") -> dict:
    r = httpx.post(
        f"{base_url}/api/agents",
        json={"name": name, "description": description},
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code in (200, 201), f"seed agent failed: {r.status_code} {r.text}"
    return r.json()


def _seed_pending_revision(
    data_dir: Path,
    *,
    agent_name: str,
    field: str,
    proposed_value: str,
    base_value: str,
) -> str:
    """INSERT a pending agent_revisions row via sync sqlite3. Returns id."""
    db_path = data_dir / "the-one.db"
    revision_id = uuid.uuid4().hex
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO agent_revisions ("
            " id, agent_name, field, proposed_value, base_value,"
            " status, source, restored_from, created_at, resolved_at"
            ") VALUES (?, ?, ?, ?, ?, 'pending', 'self', NULL, datetime('now'), NULL)",
            (revision_id, agent_name, field, proposed_value, base_value),
        )
        conn.commit()
    finally:
        conn.close()
    return revision_id


def _navigate_to_self_configuration_tab(page: Page, base_url: str, agent_name: str) -> None:
    _nav.goto(page, base_url, f"agents/{_nav.seg(agent_name)}/self-configuration")
    expect(page.locator('[data-testid="tab-self-configuration"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


@pytest.mark.browser
def test_pending_count_and_cards_render(app_with_data_dir: tuple[str, Path], page: Page) -> None:
    base_url, data_dir = app_with_data_dir
    _seed_agent(base_url, "queue-count-agent", description="current desc")
    _seed_pending_revision(
        data_dir,
        agent_name="queue-count-agent",
        field="description",
        proposed_value="proposed desc",
        base_value="current desc",
    )
    _seed_pending_revision(
        data_dir,
        agent_name="queue-count-agent",
        field="system_prompt",
        proposed_value="proposed prompt",
        base_value="old prompt",
    )
    _navigate_to_self_configuration_tab(page, base_url, "queue-count-agent")

    count = page.locator('[data-testid="pending-count"]')
    expect(count).to_contain_text("2 revisions", timeout=8000)
    cards = page.locator('[data-testid="revision-card"]')
    expect(cards).to_have_count(2)
    # base→proposed visible on the clean path.
    expect(page.locator('[data-testid="revision-proposed"]').first).to_be_visible()
    expect(page.locator('[data-testid="revision-base"]').first).to_be_visible()


@pytest.mark.browser
def test_clean_approve_applies_and_row_leaves_queue(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base_url, data_dir = app_with_data_dir
    _seed_agent(base_url, "queue-approve-agent", description="current desc")
    _seed_pending_revision(
        data_dir,
        agent_name="queue-approve-agent",
        field="description",
        proposed_value="approved desc",
        base_value="current desc",
    )
    _navigate_to_self_configuration_tab(page, base_url, "queue-approve-agent")

    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    page.locator('[data-testid="revision-approve-btn"]').first.click()

    # After the re-render, the pending list is empty.
    expect(page.locator('[data-testid="pending-queue-empty"]')).to_be_visible(timeout=8000)

    # Store updated (persist path).
    agent = httpx.get(
        f"{base_url}/api/agents/queue-approve-agent",
        timeout=5.0,
        headers=auth_headers_for(base_url),
    ).json()
    assert agent["description"] == "approved desc"


@pytest.mark.browser
def test_dismiss_removes_row(app_with_data_dir: tuple[str, Path], page: Page) -> None:
    base_url, data_dir = app_with_data_dir
    _seed_agent(base_url, "queue-dismiss-agent", description="current desc")
    _seed_pending_revision(
        data_dir,
        agent_name="queue-dismiss-agent",
        field="description",
        proposed_value="never applied",
        base_value="current desc",
    )
    _navigate_to_self_configuration_tab(page, base_url, "queue-dismiss-agent")

    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    page.locator('[data-testid="revision-dismiss-btn"]').first.click()

    expect(page.locator('[data-testid="pending-queue-empty"]')).to_be_visible(timeout=8000)
    # HAT fix #5: at zero pending, the redundant "0 revisions awaiting
    # your approval." count line is hidden — only the single empty-state
    # notice above is shown.
    expect(page.locator('[data-testid="pending-count"]')).to_be_hidden()
    # Store NOT changed by dismiss.
    agent = httpx.get(
        f"{base_url}/api/agents/queue-dismiss-agent",
        timeout=5.0,
        headers=auth_headers_for(base_url),
    ).json()
    assert agent["description"] == "current desc"


@pytest.mark.browser
def test_staleness_409_renders_both_values(app_with_data_dir: tuple[str, Path], page: Page) -> None:
    base_url, data_dir = app_with_data_dir
    _seed_agent(base_url, "queue-stale-agent", description="CURRENT NOW")
    # base_value differs from current → approve is stale.
    _seed_pending_revision(
        data_dir,
        agent_name="queue-stale-agent",
        field="description",
        proposed_value="proposed value",
        base_value="STALE BASE",
    )
    _navigate_to_self_configuration_tab(page, base_url, "queue-stale-agent")

    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    page.locator('[data-testid="revision-approve-btn"]').first.click()

    stale = page.locator('[data-testid="revision-stale"]')
    expect(stale).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="revision-current"]')).to_contain_text("CURRENT NOW")
    expect(page.locator('[data-testid="revision-stale-proposed"]')).to_contain_text(
        "proposed value"
    )
    expect(page.locator('[data-testid="revision-override-btn"]')).to_be_visible()

    # Override applies.
    page.locator('[data-testid="revision-override-btn"]').click()
    expect(page.locator('[data-testid="pending-queue-empty"]')).to_be_visible(timeout=8000)
    agent = httpx.get(
        f"{base_url}/api/agents/queue-stale-agent",
        timeout=5.0,
        headers=auth_headers_for(base_url),
    ).json()
    assert agent["description"] == "proposed value"


@pytest.mark.browser
def test_approval_mode_toggle_persists(app_with_data_dir: tuple[str, Path], page: Page) -> None:
    base_url, data_dir = app_with_data_dir
    _seed_agent(base_url, "queue-toggle-agent")
    _navigate_to_self_configuration_tab(page, base_url, "queue-toggle-agent")

    # HAT UX pass (M21 F02 L04): the approval-mode control is now a
    # `.tool-enable-switch` checkbox, not a button with "Turn on/off
    # approval mode" text — assert the checked state and the status line
    # text instead.
    toggle = page.locator('[data-testid="approval-mode-toggle-btn"]')
    status = page.locator('[data-testid="approval-mode-status"]')
    expect(toggle).not_to_be_checked(timeout=8000)
    expect(status).to_contain_text("off", timeout=8000)
    toggle.click()

    # After re-render the toggle reflects the on state.
    expect(toggle).to_be_checked(timeout=8000)
    expect(status).to_contain_text("on", timeout=8000)
    # Server-side persistence.
    status = httpx.get(
        f"{base_url}/api/agents/queue-toggle-agent/self-configuration",
        timeout=5.0,
        headers=auth_headers_for(base_url),
    ).json()
    assert status["requires_approval"] is True

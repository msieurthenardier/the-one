"""Studio "Always Listen" toggle flow tests (M11 F7 L11).

Pin two new UI surfaces against regression:

1. **Account-level toggle** in the connector editor's Session
   section. Field-row-3-column pattern (`<label> | <button.field-info-icon> |
   <content>`). Writes ``account.config["always_listen"]`` (bool) per the
   L5 storage layer. Dispatches ``connector-always-listen-changed``
   on change so attached-agent editors can grey-out their per-account
   toggles in real time.

2. **Per-account toggle** inside each tile of the agent editor's
   Connectors tab (`Always listen`). Writes
   ``agent.connector_always_listen[<account_id>]`` (bool) per the L6
   storage layer. The ``disabled`` attribute mirrors the account-level
   master state at render time and updates in real time when the
   CustomEvent fires from the editor surface (same browser tab).

Browser-test infrastructure: app subprocess + Playwright per the
``test_flow_studio_connector_navigation.py`` precedent.
"""

from __future__ import annotations

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from browser.seeders import (
    seed_connector,
    seed_mock_agent,
    seed_mock_provider,
)
from playwright.sync_api import Page, expect

# ── Helpers ──────────────────────────────────────────────────────────────


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(
        f"{base_url}/api/connectors/{account_id}", timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _get_agent(base_url: str, agent_name: str) -> dict:
    r = httpx.get(
        f"{base_url}/api/agents/{agent_name}", timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _attach_agent_to_account(base_url: str, agent_name: str, account_id: str) -> None:
    """Mutate an existing agent so its ``connector_ids`` includes
    ``account_id``. PUT /api/agents is REPLACE semantic — we GET the
    current config first and re-PUT with the connector id appended.
    """
    cur = httpx.get(
        f"{base_url}/api/agents/{agent_name}", timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert cur.status_code == 200, f"get agent failed: {cur.status_code} {cur.text}"
    cfg = cur.json()
    ids = list(cfg.get("connector_ids") or [])
    if account_id not in ids:
        ids.append(account_id)
    cfg["connector_ids"] = ids
    r = httpx.put(
        f"{base_url}/api/agents/{agent_name}",
        json=cfg,
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code == 200, f"attach agent failed: {r.status_code} {r.text}"


def _seed_account_with_agent(
    base_url: str,
    *,
    account_name: str = "Listen Bot",
    agent_name: str = "always-listen-agent",
    account_config: dict | None = None,
) -> tuple[str, str]:
    """Seed a provider + agent + connector account and attach the agent.

    ``account_config`` is forwarded into the connector account's ``config``
    dict so tests can seed an account with ``always_listen=True`` or
    ``False`` to exercise the master-toggle composition.
    """
    provider_id = seed_mock_provider(base_url, name=f"mock-for-{agent_name}")
    seed_mock_agent(base_url, provider_id, name=agent_name)
    account_id = seed_connector(base_url, name=account_name, config=account_config or {})
    _attach_agent_to_account(base_url, agent_name, account_id)
    return account_id, agent_name


def _open_agent_connectors_tab(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}")
    expect(page.locator('[data-testid="tab-connectors"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-connectors"]').click()


# ── Account-editor toggle tests ──────────────────────────────────────────


@pytest.mark.browser
def test_account_editor_always_listen_toggle_renders(app_clean: str, page: Page) -> None:
    """The Always Listen toggle is visible in the connector
    editor's Session section.

    F5 L8 HAT: Session section lives behind the "Access and Routing" tab
    in edit mode — activate the tab before asserting visibility.
    """
    account_id = seed_connector(app_clean, name="Listen Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    # Lifecycle / Session lives in the Access and Routing tab.
    page.locator('[data-testid="tab-access-and-routing"]').click()

    toggle = page.locator('[data-testid="connector-always-listen-toggle"]')
    expect(toggle).to_be_visible(timeout=5000)
    # Baseline: account with no config defaults to unchecked.
    expect(toggle).not_to_be_checked()


@pytest.mark.browser
def test_account_editor_always_listen_toggle_persists_true(app_clean: str, page: Page) -> None:
    """Toggle ON → save → backend persists ``config.always_listen=True``."""
    account_id = seed_connector(app_clean, name="Listen-True Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-access-and-routing"]').click()

    toggle = page.locator('[data-testid="connector-always-listen-toggle"]')
    expect(toggle).to_be_visible(timeout=5000)
    toggle.check()

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert (after.get("config") or {}).get("always_listen") is True, (
        f"expected config.always_listen=True; got {after}"
    )


@pytest.mark.browser
def test_account_editor_always_listen_toggle_persists_false(app_clean: str, page: Page) -> None:
    """Seeded ON → toggle OFF → save → backend persists ``always_listen=False``."""
    account_id = seed_connector(app_clean, name="Listen-False Bot", config={"always_listen": True})
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-access-and-routing"]').click()

    toggle = page.locator('[data-testid="connector-always-listen-toggle"]')
    expect(toggle).to_be_visible(timeout=5000)
    expect(toggle).to_be_checked()  # seeded True

    toggle.uncheck()

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert (after.get("config") or {}).get("always_listen") is False, (
        f"expected config.always_listen=False; got {after}"
    )


@pytest.mark.browser
def test_account_editor_always_listen_info_icon_tooltip_present(app_clean: str, page: Page) -> None:
    """The info-icon next to the Always Listen label is present and
    carries the disambiguating help text in its ``title`` attribute."""
    account_id = seed_connector(app_clean, name="Hint Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-access-and-routing"]').click()

    hint = page.locator('[data-testid="connector-always-listen-hint"]')
    expect(hint).to_be_visible(timeout=5000)
    title = hint.get_attribute("title") or ""
    assert "lightweight inference call" in title, f"expected help text in title attr; got {title!r}"


# ── Agent Connectors-tab toggle tests ────────────────────────────────────


@pytest.mark.browser
def test_agent_connectors_tab_per_account_toggle_renders(app_clean: str, page: Page) -> None:
    """Agent editor's Connectors tab renders the per-account
    "Always listen" toggle for each attached
    account."""
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Per-Agent Bot",
        agent_name="per-agent-listen",
        account_config={"always_listen": True},
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    per_agent_toggle = page.locator(f'[data-testid="agent-connector-always-listen-{account_id}"]')
    expect(per_agent_toggle).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_agent_connectors_tab_per_account_toggle_disabled_when_master_off(
    app_clean: str, page: Page
) -> None:
    """Account master toggle OFF → per-agent toggle is ``disabled``."""
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Master-Off Bot",
        agent_name="master-off-agent",
        account_config={"always_listen": False},
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    per_agent_toggle = page.locator(f'[data-testid="agent-connector-always-listen-{account_id}"]')
    expect(per_agent_toggle).to_be_visible(timeout=8000)
    expect(per_agent_toggle).to_be_disabled()


@pytest.mark.browser
def test_agent_connectors_tab_per_account_toggle_enabled_when_master_on(
    app_clean: str, page: Page
) -> None:
    """Account master toggle ON → per-agent toggle is interactive
    (not disabled)."""
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Master-On Bot",
        agent_name="master-on-agent",
        account_config={"always_listen": True},
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    per_agent_toggle = page.locator(f'[data-testid="agent-connector-always-listen-{account_id}"]')
    expect(per_agent_toggle).to_be_visible(timeout=8000)
    expect(per_agent_toggle).not_to_be_disabled()


@pytest.mark.browser
def test_agent_connectors_tab_per_account_toggle_persists_via_save(
    app_clean: str, page: Page
) -> None:
    """Toggling the per-account always-listen switch + saving the agent
    persists ``agent.connector_always_listen[<account_id>]=True``.

    Verifies the studio.js::collectFormData dict-collection path mirrors
    the connector_acls precedent.
    """
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Persist Bot",
        agent_name="persist-agent",
        account_config={"always_listen": True},
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    per_agent_toggle = page.locator(f'[data-testid="agent-connector-always-listen-{account_id}"]')
    expect(per_agent_toggle).to_be_visible(timeout=8000)
    expect(per_agent_toggle).not_to_be_checked()
    per_agent_toggle.check()

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_agent(app_clean, agent_name)
    cal = after.get("connector_always_listen") or {}
    assert cal.get(account_id) is True, (
        f"expected connector_always_listen[{account_id!r}]=True; got {cal}"
    )


@pytest.mark.browser
def test_cross_component_event_disables_per_agent_toggle(app_clean: str, page: Page) -> None:
    """Dispatching ``connector-always-listen-changed`` with
    ``enabled=false`` in the agent editor's tab disables the matching
    per-agent toggle WITHOUT a page reload.

    The account-editor surface and the agent-editor surface live in
    different routes; the CustomEvent + listener bridge lets the agent
    editor reflect master-toggle changes in real time when both are
    open in the same tab. Simulating the dispatch directly via
    ``page.evaluate`` is the cleanest way to pin the listener contract
    without driving a multi-tab scenario.
    """
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Cross-Event Bot",
        agent_name="cross-event-agent",
        account_config={"always_listen": True},
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    per_agent_toggle = page.locator(f'[data-testid="agent-connector-always-listen-{account_id}"]')
    expect(per_agent_toggle).to_be_visible(timeout=8000)
    expect(per_agent_toggle).not_to_be_disabled()

    # Dispatch the master-OFF event directly in the page.
    page.evaluate(
        """
        (accountId) => {
            document.dispatchEvent(new CustomEvent(
                'connector-always-listen-changed',
                { detail: { accountId: accountId, enabled: false } }
            ));
        }
        """,
        account_id,
    )

    # Listener flips disabled state on the matching toggle in real time.
    expect(per_agent_toggle).to_be_disabled(timeout=2000)

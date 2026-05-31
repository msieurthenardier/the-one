"""Per-agent ``admit_dms`` opt-out browser flow tests (M11 F10 L3).

Pins the per-agent DM-admission opt-out toggle that lives in the agent
editor's Connectors tab, alongside the existing per-account
"Always Listen" toggle. Semantics:

- ``connector_acls[account_id].admit_dms`` is ``bool | None`` (per L1).
- UI contract: CHECKED = inherit account-scope ``dm_admission``;
  UNCHECKED = explicit opt-out (persists as ``admit_dms: false``).
- ``true`` is structurally redundant with absent/None and is never
  emitted by the UI (collect path drops it).
- When account-scope ``dm_admission === "none"``, the toggle is
  DISABLED + visually-checked (structurally inert).

Sibling test reference:
``test_flow_studio_always_listen_toggles.py`` (same fixture shape,
same _seed_account_with_agent helper pattern).

The reload-shows-unchecked-when-persisted-false test (#4) pins the
``accountAcl`` normalization fix at ``connectors-tab.js:155-170`` —
without that fix, ``admit_dms`` is stripped on the render-side
normalization and a persisted opt-out re-renders as CHECKED on reload.
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import (
    seed_connector,
    seed_mock_agent,
    seed_mock_provider,
)
from playwright.sync_api import Page, expect


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_agent(base_url: str, agent_name: str) -> dict:
    r = httpx.get(f"{base_url}/api/agents/{agent_name}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _put_agent(base_url: str, agent_name: str, cfg: dict) -> None:
    r = httpx.put(f"{base_url}/api/agents/{agent_name}", json=cfg, timeout=5.0)
    assert r.status_code == 200, f"put agent failed: {r.status_code} {r.text}"


def _attach_agent_to_account(base_url: str, agent_name: str, account_id: str) -> None:
    """Mutate an existing agent so its ``connector_ids`` includes
    ``account_id``. PUT /api/agents is REPLACE semantic — GET the
    current config first and re-PUT with the connector id appended.

    Mirrors the helper in ``test_flow_studio_always_listen_toggles.py``.
    """
    cfg = _get_agent(base_url, agent_name)
    ids = list(cfg.get("connector_ids") or [])
    if account_id not in ids:
        ids.append(account_id)
    cfg["connector_ids"] = ids
    _put_agent(base_url, agent_name, cfg)


def _seed_account_with_agent(
    base_url: str,
    *,
    account_name: str = "Admit-DMs Bot",
    agent_name: str = "admit-dms-agent",
    dm_admission: str = "all",
) -> tuple[str, str]:
    """Seed a provider + agent + connector account and attach the agent.

    ``dm_admission`` is forwarded into ``account.config.allowlist`` so
    tests can exercise the disabled-state path (``"none"``) and the
    interactive path (``"all"`` / ``"admin-approved"``). M11 F12 L4
    renamed the Literal value ``"allowlisted-peers-only"`` →
    ``"admin-approved"`` per operator-vocabulary alignment.
    """
    provider_id = seed_mock_provider(base_url, name=f"mock-for-{agent_name}")
    seed_mock_agent(base_url, provider_id, name=agent_name)
    account_id = seed_connector(
        base_url,
        name=account_name,
        config={
            "allowlist": {
                "peers": [],
                "channels": [],
                "dm_admission": dm_admission,
            }
        },
    )
    _attach_agent_to_account(base_url, agent_name, account_id)
    return account_id, agent_name


def _open_agent_connectors_tab(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}")
    expect(page.locator('[data-testid="tab-connectors"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-connectors"]').click()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_admit_dms_renders_checked_by_default(app_clean: str, page: Page) -> None:
    """Agent attached to an account with ``dm_admission="all"`` and no
    per-agent override → the admit-DMs switch renders CHECKED (inherit)
    and is interactive (not disabled).
    """
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Default-Inherit Bot",
        agent_name="default-inherit-agent",
        dm_admission="all",
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    toggle = page.locator(f'[data-testid="agent-connector-admit-dms-{account_id}"]')
    expect(toggle).to_be_visible(timeout=8000)
    expect(toggle).to_be_checked()
    expect(toggle).not_to_be_disabled()


@pytest.mark.browser
def test_admit_dms_unchecks_and_persists(app_clean: str, page: Page) -> None:
    """Uncheck the switch + save the agent → backend persists
    ``connector_acls[account_id].admit_dms == False``.

    Verifies the studio.js::collectFormData walk wires the per-agent
    opt-out into the connector_acls dict (mirrors the L7 axes precedent).
    """
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Opt-Out Bot",
        agent_name="opt-out-agent",
        dm_admission="all",
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    toggle = page.locator(f'[data-testid="agent-connector-admit-dms-{account_id}"]')
    expect(toggle).to_be_visible(timeout=8000)
    expect(toggle).to_be_checked()
    toggle.uncheck()

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_agent(app_clean, agent_name)
    acls = after.get("connector_acls") or {}
    entry = acls.get(account_id) or {}
    assert entry.get("admit_dms") is False, (
        f"expected connector_acls[{account_id!r}].admit_dms = False; got {acls}"
    )


@pytest.mark.browser
def test_admit_dms_disabled_when_account_dm_admission_none(
    app_clean: str, page: Page
) -> None:
    """Account-scope ``dm_admission="none"`` → switch is DISABLED and
    visually-checked; hint text matches the disabled-state literal.
    """
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="DMs-Denied Bot",
        agent_name="dms-denied-agent",
        dm_admission="none",
    )
    _open_agent_connectors_tab(page, app_clean, agent_name)

    toggle = page.locator(f'[data-testid="agent-connector-admit-dms-{account_id}"]')
    expect(toggle).to_be_visible(timeout=8000)
    expect(toggle).to_be_disabled()
    expect(toggle).to_be_checked()

    hint = page.locator(f'[data-testid="agent-connector-admit-dms-hint-{account_id}"]')
    expect(hint).to_be_visible(timeout=4000)
    hint_text = hint.text_content() or ""
    assert "Account denies all DMs" in hint_text, (
        f"expected disabled-state hint text; got {hint_text!r}"
    )


@pytest.mark.browser
def test_admit_dms_reload_shows_unchecked_when_persisted_false(
    app_clean: str, page: Page
) -> None:
    """Agent with a persisted ``admit_dms: False`` → switch re-renders
    UNCHECKED on page load.

    Pins the cycle-1-required ``accountAcl`` normalization fix at
    ``connectors-tab.js:155-170``. Without that fix, the normalization
    rebuilds the per-account dict as ``{peers, channels}`` only and
    drops ``admit_dms`` — so the helper reads ``undefined`` and renders
    the switch as CHECKED (inherit), silently losing the persisted
    opt-out on every reload.
    """
    account_id, agent_name = _seed_account_with_agent(
        app_clean,
        account_name="Persisted-Optout Bot",
        agent_name="persisted-optout-agent",
        dm_admission="all",
    )
    # Seed the persisted opt-out via the agent PUT path. The validator
    # requires ``peers`` and ``channels`` keys when an entry exists, so
    # include them as ``None`` (inherit) alongside ``admit_dms: False``.
    cfg = _get_agent(app_clean, agent_name)
    cfg["connector_acls"] = {
        account_id: {"peers": None, "channels": None, "admit_dms": False}
    }
    _put_agent(app_clean, agent_name, cfg)

    # Confirm the seed landed before navigating (catches PUT-schema
    # drift before the UI assertion would mis-diagnose the render bug).
    seeded = _get_agent(app_clean, agent_name)
    assert (seeded.get("connector_acls") or {}).get(account_id, {}).get(
        "admit_dms"
    ) is False, f"seed precondition failed: {seeded.get('connector_acls')!r}"

    _open_agent_connectors_tab(page, app_clean, agent_name)

    toggle = page.locator(f'[data-testid="agent-connector-admit-dms-{account_id}"]')
    expect(toggle).to_be_visible(timeout=8000)
    expect(toggle).not_to_be_checked()

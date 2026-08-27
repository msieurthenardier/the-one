"""Browser tests for the Self-configuration tab External access section
(M21 F03 L03, AC1-AC8).

The section grants / lists / revokes / rotates external-client credentials
over Leg 1's already-landed endpoints
(``POST/GET /api/agents/{name}/self-configuration/external-credentials``,
``DELETE …/{identifier}``, ``POST …/{identifier}/rotate``). Mirrors
``test_studio_self_configuration_history.py``'s httpx-seed + drive-the-tab
shape.

Covers:
  AC1 — section present + enablement gate (grant disabled + empty list when
        the surface is off; actionable when on).
  AC2 — grant reveals the ``ext_…`` token exactly once (copy affordance +
        surface URL + shown-once warning) and the grant appears in the list.
  AC3 — the active-grants list is secret-free (no secret text in its DOM).
  AC4 — revoke removes the grant from the list.
  AC5 — rotate reveals a NEW token once; the identifier changes.
  AC6 — empty/whitespace label is rejected inline with no server round-trip.
  AC7 — a11y: labelled input; focus lands on the reveal after grant and on
        the grant input after revoke (never the page top).
  AC8 — create-mode shows the "save first" notice (no external section).

Snapshot note (global rule): asserts on DOM shape / testids / a11y only —
no committed visual-snapshot baselines.
"""

from __future__ import annotations

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _seed_agent(base_url: str, name: str, description: str = "external-access test agent") -> dict:
    r = httpx.post(
        f"{base_url}/api/agents",
        json={"name": name, "description": description},
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code in (200, 201), f"seed agent failed: {r.status_code} {r.text}"
    return r.json()


def _enable_self_configuration(base_url: str, name: str) -> None:
    r = httpx.post(
        f"{base_url}/api/agents/{name}/self-configuration",
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code == 200, f"enable self-configuration failed: {r.status_code} {r.text}"


def _navigate_to_self_configuration_tab(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}/self-configuration")
    expect(page.locator('[data-testid="tab-self-configuration"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


@pytest.mark.browser
def test_section_disabled_when_surface_off(app_clean: str, page: Page) -> None:
    """AC1 — with self-configuration OFF, the External access section renders
    but the grant control is disabled with a hint and the list is empty."""
    _seed_agent(app_clean, "ext-gate-off-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "ext-gate-off-agent")

    # Section present.
    expect(page.locator('[data-testid="self-configuration-external-grant-btn"]')).to_be_visible(
        timeout=8000
    )
    # Grant disabled + hint shown; list empty.
    expect(page.locator('[data-testid="self-configuration-external-grant-btn"]')).to_be_disabled()
    expect(page.locator('[data-testid="self-configuration-external-grant-label"]')).to_be_disabled()
    expect(page.locator('[data-testid="self-configuration-external-grant-hint"]')).to_be_visible()
    expect(page.locator('[data-testid="self-configuration-external-empty"]')).to_be_visible()


@pytest.mark.browser
def test_grant_reveals_token_once_and_list_updates(app_clean: str, page: Page) -> None:
    """AC1/AC2/AC3/AC7 — with the surface ON, granting reveals the token once
    (with URL + warning + copy), the grant appears in the list, the list is
    secret-free, and focus lands on the reveal."""
    _seed_agent(app_clean, "ext-grant-agent")
    _enable_self_configuration(app_clean, "ext-grant-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "ext-grant-agent")

    grant_btn = page.locator('[data-testid="self-configuration-external-grant-btn"]')
    expect(grant_btn).to_be_enabled(timeout=8000)

    label_input = page.locator('[data-testid="self-configuration-external-grant-label"]')
    # AC7: the input is programmatically labelled.
    input_id = label_input.get_attribute("id")
    assert input_id, "grant input should have an id for its <label for=…>"
    assert page.locator(f'label[for="{input_id}"]').count() == 1

    label_input.fill("staging-deploy-bot")
    grant_btn.click()

    # AC2: reveal appears once with the token, URL, warning, copy affordance.
    reveal = page.locator('[data-testid="self-configuration-external-token-reveal"]')
    expect(reveal).to_be_visible(timeout=8000)
    token_field = page.locator('[data-testid="self-configuration-external-token-value"]')
    token = token_field.input_value()
    assert token.startswith("ext_") and "." in token, f"expected an ext_ token, got: {token!r}"
    expect(reveal).to_contain_text("shown only once")
    expect(page.locator('[data-testid="self-configuration-external-token-url"]')).not_to_be_empty()
    expect(
        page.locator('[data-testid="self-configuration-external-token-copy-btn"]')
    ).to_be_visible()

    # AC7: focus landed inside the reveal (the copy button), not the page top.
    active_testid = page.evaluate(
        "() => document.activeElement && document.activeElement.getAttribute('data-testid')"
    )
    assert active_testid == "self-configuration-external-token-copy-btn", (
        f"expected focus on the reveal copy button, got: {active_testid!r}"
    )

    # AC2: the grant now appears in the list.
    rows = page.locator('[data-testid="self-configuration-external-credential-row"]')
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("staging-deploy-bot")

    # AC2: token is NOT persisted to web storage.
    stored = page.evaluate("() => JSON.stringify({ls: {...localStorage}, ss: {...sessionStorage}})")
    secret = token.split(".", 1)[1]
    assert secret not in stored, "the one-time secret must never be persisted to web storage"

    # AC3: no secret text appears anywhere in the list DOM.
    list_text = page.locator('[data-testid="self-configuration-external-list"]').inner_text()
    assert secret not in list_text, "the list must be secret-free"
    assert token not in list_text, "the full token must never appear in the list"

    # Dismiss clears the reveal and moves focus to the grant input.
    page.locator('[data-testid="self-configuration-external-token-dismiss-btn"]').click()
    expect(reveal).to_be_hidden()
    assert token_field.input_value() == "", "token field must be cleared on dismiss"


@pytest.mark.browser
def test_revoke_removes_grant(app_clean: str, page: Page) -> None:
    """AC4/AC7 — revoke (two-step confirm) removes the grant; focus lands on
    the grant input, not the page top."""
    _seed_agent(app_clean, "ext-revoke-agent")
    _enable_self_configuration(app_clean, "ext-revoke-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "ext-revoke-agent")

    grant_btn = page.locator('[data-testid="self-configuration-external-grant-btn"]')
    expect(grant_btn).to_be_enabled(timeout=8000)
    page.locator('[data-testid="self-configuration-external-grant-label"]').fill("to-revoke")
    grant_btn.click()
    expect(
        page.locator('[data-testid="self-configuration-external-credential-row"]')
    ).to_have_count(1, timeout=8000)

    revoke_btn = page.locator('[data-testid="self-configuration-external-revoke-btn"]')
    # Two-step in-place confirm: first click arms, second commits.
    revoke_btn.click()
    expect(revoke_btn).to_contain_text("Confirm")
    revoke_btn.click()

    # Grant removed → empty list.
    expect(
        page.locator('[data-testid="self-configuration-external-credential-row"]')
    ).to_have_count(0, timeout=8000)
    expect(page.locator('[data-testid="self-configuration-external-empty"]')).to_be_visible()

    # AC7: focus landed on the grant input, not the page top.
    active_testid = page.evaluate(
        "() => document.activeElement && document.activeElement.getAttribute('data-testid')"
    )
    assert active_testid == "self-configuration-external-grant-label", (
        f"expected focus on the grant input after revoke, got: {active_testid!r}"
    )

    # Server-side confirms the credential is gone.
    listing = httpx.get(
        f"{app_clean}/api/agents/ext-revoke-agent/self-configuration/external-credentials",
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    ).json()
    assert listing == [], f"expected no credentials server-side, got: {listing}"


@pytest.mark.browser
def test_rotate_reveals_new_token(app_clean: str, page: Page) -> None:
    """AC5 — rotate reveals a NEW token once; the credential's identifier
    changes and the old identifier is gone."""
    _seed_agent(app_clean, "ext-rotate-agent")
    _enable_self_configuration(app_clean, "ext-rotate-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "ext-rotate-agent")

    grant_btn = page.locator('[data-testid="self-configuration-external-grant-btn"]')
    expect(grant_btn).to_be_enabled(timeout=8000)
    page.locator('[data-testid="self-configuration-external-grant-label"]').fill("rotate-me")
    grant_btn.click()

    row = page.locator('[data-testid="self-configuration-external-credential-row"]')
    expect(row).to_have_count(1, timeout=8000)
    old_identifier = row.first.get_attribute("data-identifier")
    old_token = page.locator(
        '[data-testid="self-configuration-external-token-value"]'
    ).input_value()

    # Dismiss the first reveal so the assertion below is unambiguous.
    page.locator('[data-testid="self-configuration-external-token-dismiss-btn"]').click()
    expect(page.locator('[data-testid="self-configuration-external-token-reveal"]')).to_be_hidden()

    page.locator('[data-testid="self-configuration-external-rotate-btn"]').click()

    # A fresh token is revealed once.
    reveal = page.locator('[data-testid="self-configuration-external-token-reveal"]')
    expect(reveal).to_be_visible(timeout=8000)
    new_token = page.locator(
        '[data-testid="self-configuration-external-token-value"]'
    ).input_value()
    assert new_token.startswith("ext_") and new_token != old_token, (
        "rotate must reveal a new, different token"
    )
    expect(reveal).to_contain_text("shown only once")

    # The list shows the grant with its NEW identifier; the old one is gone.
    row = page.locator('[data-testid="self-configuration-external-credential-row"]')
    expect(row).to_have_count(1)
    new_identifier = row.first.get_attribute("data-identifier")
    assert new_identifier and new_identifier != old_identifier, (
        f"identifier should change on rotate: {old_identifier!r} -> {new_identifier!r}"
    )
    expect(row.first).to_contain_text("rotate-me")


@pytest.mark.browser
def test_empty_label_rejected_inline(app_clean: str, page: Page) -> None:
    """AC6 — an empty/whitespace label is rejected inline with no server
    round-trip (no credential is created)."""
    _seed_agent(app_clean, "ext-validate-agent")
    _enable_self_configuration(app_clean, "ext-validate-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "ext-validate-agent")

    grant_btn = page.locator('[data-testid="self-configuration-external-grant-btn"]')
    expect(grant_btn).to_be_enabled(timeout=8000)

    # Whitespace-only label → inline error, no reveal, no list row.
    page.locator('[data-testid="self-configuration-external-grant-label"]').fill("   ")
    grant_btn.click()
    error = page.locator('[data-testid="self-configuration-external-error"]')
    expect(error).to_be_visible()
    expect(error).to_contain_text("label")
    expect(page.locator('[data-testid="self-configuration-external-token-reveal"]')).to_be_hidden()
    expect(page.locator('[data-testid="self-configuration-external-empty"]')).to_be_visible()

    # No server round-trip happened.
    listing = httpx.get(
        f"{app_clean}/api/agents/ext-validate-agent/self-configuration/external-credentials",
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    ).json()
    assert listing == [], f"no credential should have been minted, got: {listing}"


@pytest.mark.browser
def test_label_rendered_as_text_not_html(app_clean: str, page: Page) -> None:
    """Edge case — a label with HTML-ish content renders as text, never
    injected markup."""
    _seed_agent(app_clean, "ext-inject-agent")
    _enable_self_configuration(app_clean, "ext-inject-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "ext-inject-agent")

    grant_btn = page.locator('[data-testid="self-configuration-external-grant-btn"]')
    expect(grant_btn).to_be_enabled(timeout=8000)
    injection = "<img src=x onerror=alert(1)>bot"
    page.locator('[data-testid="self-configuration-external-grant-label"]').fill(injection)
    grant_btn.click()

    row = page.locator('[data-testid="self-configuration-external-credential-row"]')
    expect(row).to_have_count(1, timeout=8000)
    # The label text is present verbatim, and no <img> element was injected.
    label_el = row.locator(".self-configuration-external-credential-label")
    expect(label_el).to_have_text(injection)
    assert row.locator("img").count() == 0, "label must never be parsed as HTML"


@pytest.mark.browser
def test_create_mode_shows_save_first(app_with_provider: object, page: Page) -> None:
    """AC8 — in create-mode (unsaved agent) the tab shows the save-first
    notice and no External access section."""
    base_url = app_with_provider.base_url  # type: ignore[attr-defined]

    page.goto(f"{base_url}#studio")
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent")

    page.locator('[data-testid="tab-self-configuration"]').click()
    expect(page.locator('[data-testid="tab-self-configuration"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )

    expect(page.locator('[data-testid="self-configuration-save-first"]')).to_be_visible()
    # No external-access controls exist on an unsaved agent.
    assert page.locator('[data-testid="self-configuration-external-grant-btn"]').count() == 0, (
        "create-mode must not render external-access actions"
    )


@pytest.mark.browser
def test_disabling_surface_clears_grants(app_clean: str, page: Page) -> None:
    """AC1 (cascade) — disabling self-configuration re-renders the external
    section into its disabled state with an empty list, matching the
    server-side cascade-revoke."""
    _seed_agent(app_clean, "ext-cascade-agent")
    _enable_self_configuration(app_clean, "ext-cascade-agent")
    _navigate_to_self_configuration_tab(page, app_clean, "ext-cascade-agent")

    grant_btn = page.locator('[data-testid="self-configuration-external-grant-btn"]')
    expect(grant_btn).to_be_enabled(timeout=8000)
    page.locator('[data-testid="self-configuration-external-grant-label"]').fill("doomed")
    grant_btn.click()
    expect(
        page.locator('[data-testid="self-configuration-external-credential-row"]')
    ).to_have_count(1, timeout=8000)

    # Disable the surface via the tab toggle → whole-editor re-render.
    page.locator('[data-testid="self-configuration-toggle-btn"]').click()
    expect(page.locator('[data-testid="self-configuration-status"]')).to_contain_text(
        "disabled", timeout=8000
    )

    # External section now disabled: grant off, hint shown, list empty.
    expect(page.locator('[data-testid="self-configuration-external-grant-btn"]')).to_be_disabled()
    expect(page.locator('[data-testid="self-configuration-external-grant-hint"]')).to_be_visible()
    expect(page.locator('[data-testid="self-configuration-external-empty"]')).to_be_visible()
    # Server-side: the cascade revoked the grant.
    re_listing = httpx.get(
        f"{app_clean}/api/agents/ext-cascade-agent/self-configuration/external-credentials",
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    ).json()
    assert re_listing == [], f"disable should cascade-revoke grants, got: {re_listing}"

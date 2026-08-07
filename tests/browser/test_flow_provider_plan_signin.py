"""Browser tests for the anthropic-plan provider editor sign-in UX (M19 F01 L03).

Covers the sign-in flow (DD-1/DD-7, create mode auto-save-then-start per the
HAT fix): type-driven field visibility (no API key, no base URL), the
create-mode sign-in affordance that auto-saves the provider before starting
OAuth (with inline validation when the name is missing), the consent UI
(copyable URL + code paste), inline error rendering, the connected /
re-authenticate / reset states, and the distinct ``reauth_required`` /test
message.

Network boundary (leg design-review resolved):

- Browser tests NEVER call the real token endpoint. ``/oauth/start`` is
  local-only (URL construction, no network) and safe to call for real.
  ``/oauth/code``'s success path is stubbed via ``page.route`` (the
  code-exchange path stays unit-tested); its state-mismatch 400 path is
  exercised for real because the backend rejects BEFORE any exchange.
- Navigation to claude.ai (the consent popup / Open button) is aborted via a
  context-level route so no external request ever leaves the test.
- The **connected state** uses REAL seeded encrypted secrets — written via
  direct sqlite3 against ``data_dir/the-one.db``, Fernet-encrypted with the
  app subprocess's auto-generated ``data_dir/encryption.key`` (fixture
  precedent: ``app_with_data_dir`` in
  ``test_flow_chat_session_list_source_badge.py``) — so the ``oauth_active``
  derivation is exercised end-to-end.
- The frontend's ``GET /api/providers/{id}/models`` fetch is stubbed in
  seeded-token tests so the backend never attempts a live ``models.list()``
  with the fake bearer token.
- The ``reauth_required`` /test result CANNOT come from a seeded fixture
  (deciding "revoked" requires a refresh attempt against the hardcoded token
  endpoint), so ``POST /api/providers/{id}/test`` is stubbed via
  ``page.route`` — the in-repo pattern from
  ``test_mcp_test_connection_button.py`` (F8 L2).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from cryptography.fernet import Fernet
from playwright.sync_api import Page, expect

PLAN_BASE_URL = "https://api.anthropic.com"

# `app_with_data_dir` (Mission 20 / Flight 1 / Leg 3): formerly a local
# fixture duplicated verbatim across 8 `test_flow_*.py` files, now
# consolidated onto the shared `_spawn_app` path in `browser/conftest.py`
# — pytest auto-discovers it from the directory conftest, no import needed.
# (This file previously omitted `THE_ONE_REGISTER_STUB_CONNECTOR` from its
# own copy; the shared fixture sets it unconditionally — harmless here,
# this suite never registers a connector.)


def _seed_plan_provider(base_url: str, name: str = "Claude Plan") -> str:
    """POST an anthropic-plan provider via the API and return its id.

    No API key is ever sent (mission criterion); base_url matches the
    TYPE_DEFAULTS value the editor force-submits for this type.
    """
    r = httpx.post(
        f"{base_url}/api/providers",
        json={"name": name, "type": "anthropic-plan", "base_url": PLAN_BASE_URL},
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code == 201, f"seed_plan_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _seed_plan_tokens(data_dir: Path, provider_id: str) -> None:
    """Write a REAL encrypted token set into ``llm_providers.secrets``.

    Encrypts with the app subprocess's own ``encryption.key`` so the running
    app decrypts it on the next read — the ``oauth_active`` derivation is
    exercised end-to-end (no API shortcut exists: tokens enter only via the
    OAuth exchange, which browser tests must not run for real).

    ``token_expires_at`` is far-future so the credential source never
    attempts a refresh (the token endpoint must never be called from tests).
    """
    key = (data_dir / "encryption.key").read_bytes()
    secrets = {
        "access_token": "seeded-access-token",
        "refresh_token": "seeded-refresh-token",
        "token_expires_at": int(time.time()) + 10 * 365 * 24 * 3600,
        "scope": "user:inference",
        "token_type": "Bearer",
    }
    ciphertext = Fernet(key).encrypt(json.dumps(secrets).encode()).decode()
    conn = sqlite3.connect(data_dir / "the-one.db")
    try:
        cur = conn.execute(
            "UPDATE llm_providers SET secrets = ? WHERE id = ?", (ciphertext, provider_id)
        )
        conn.commit()
        assert cur.rowcount == 1, f"no llm_providers row updated for id {provider_id}"
    finally:
        conn.close()


def _block_claude_ai(page: Page) -> None:
    """Abort any request to claude.ai (consent popup navigation) —
    context-level so popup windows are covered too."""
    page.context.route("https://claude.ai/**", lambda route: route.abort())


def _stub_models(page: Page, provider_id: str) -> None:
    """Stub the frontend's GET /models fetch so the backend never attempts a
    live ``models.list()`` with a seeded fake bearer token."""
    page.route(
        f"**/api/providers/{provider_id}/models",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([{"id": "claude-sonnet-4-6", "name": "claude-sonnet-4-6"}]),
        ),
    )


# ── Create mode: field visibility + auto-save-then-start sign-in ─────────


@pytest.mark.browser
def test_plan_type_selectable_with_no_api_key_no_base_url_and_autosave_signin(
    app_clean: str, page: Page
) -> None:
    """Selecting "Anthropic (Plan)" in create mode: no API-key input, no
    base-url input, thinking/reasoning surface present (parity with
    anthropic), and an ENABLED sign-in affordance (HAT fix — inverts the
    original disabled-until-saved gate): clicking it with a name filled
    auto-saves the provider through the exact Create path, transitions the
    editor to edit mode, and immediately enters the awaiting-code state."""
    _block_claude_ai(page)
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    # Picker label follows the parenthetical precedent.
    expect(page.locator('#pf-type option[value="anthropic-plan"]')).to_have_text("Anthropic (Plan)")
    page.locator("#pf-type").select_option("anthropic-plan")
    # No API key, no base URL (default submitted invisibly).
    expect(page.locator(".admin-pf-api-key")).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator(".admin-pf-base-url")).to_have_class(re.compile(r"\bis-hidden\b"))
    # Thinking/reasoning surface mirrors the anthropic type (AC 7a).
    expect(page.locator(".admin-pf-thinking-enabled")).not_to_have_class(
        re.compile(r"\bis-hidden\b")
    )
    expect(page.locator(".admin-pf-reasoning-effort")).not_to_have_class(
        re.compile(r"\bis-hidden\b")
    )
    # Sign-in section visible; affordance ENABLED, no save-first hint.
    expect(page.locator(".admin-pf-plan-signin")).not_to_have_class(re.compile(r"\bis-hidden\b"))
    signin_btn = page.locator('[data-testid="plan-signin-btn"]')
    expect(signin_btn).to_be_visible()
    expect(signin_btn).not_to_be_disabled()
    expect(page.locator('[data-testid="plan-signin-hint"]')).to_have_count(0)

    # Click with a name filled: auto-save (create) then awaiting-code UI.
    page.locator("#pf-name").fill("My Plan")
    signin_btn.click()
    expect(page.locator('[data-testid="plan-signin-consent"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="plan-signin-url"]')).to_have_value(
        re.compile(r"^https://claude\.ai/oauth/authorize\?")
    )
    expect(page.locator('[data-testid="plan-code-input"]')).to_be_visible()
    # The auto-save transitioned the editor to edit mode exactly as a
    # manual Create does (Test button, subtitle with the force-submitted
    # default base_url)…
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible()
    expect(page.locator(".editor-subtitle")).to_contain_text(PLAN_BASE_URL)
    # …and the provider row now exists via the API.
    providers = httpx.get(
        f"{app_clean}/api/providers", timeout=5.0, headers=auth_headers_for(app_clean)
    ).json()
    assert [(p["name"], p["type"]) for p in providers] == [("My Plan", "anthropic-plan")]
    # No error rendered (popup-blocked/aborted degrades silently).
    expect(page.locator('[data-testid="plan-signin-error"]')).to_be_hidden()


@pytest.mark.browser
def test_create_mode_signin_with_empty_name_validates_and_creates_nothing(
    app_clean: str, page: Page
) -> None:
    """Clicking the create-mode sign-in affordance with an empty Name shows
    the editor's normal inline validation, saves nothing, and does NOT
    enter the awaiting-code state."""
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic-plan")
    signin_btn = page.locator('[data-testid="plan-signin-btn"]')
    expect(signin_btn).to_be_visible()
    expect(signin_btn).not_to_be_disabled()
    signin_btn.click()
    # The editor's normal inline validation (verbatim message).
    expect(page.locator(".editor-error")).to_have_text("Name is required.")
    # No awaiting-code UI, still create mode, and NO provider created.
    expect(page.locator('[data-testid="plan-signin-consent"]')).to_have_count(0)
    expect(page.locator(".editor-title")).to_have_text("New Provider")
    assert (
        httpx.get(
            f"{app_clean}/api/providers", timeout=5.0, headers=auth_headers_for(app_clean)
        ).json()
        == []
    )


@pytest.mark.browser
def test_plan_section_hides_when_type_switched_away(app_clean: str, page: Page) -> None:
    """Type switched away from anthropic-plan mid-create: the plan section
    hides via the existing is-hidden toggle pattern (leg edge case)."""
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic-plan")
    expect(page.locator(".admin-pf-plan-signin")).not_to_have_class(re.compile(r"\bis-hidden\b"))
    page.locator("#pf-type").select_option("openai")
    expect(page.locator(".admin-pf-plan-signin")).to_have_class(re.compile(r"\bis-hidden\b"))
    # And the openai fields reassert themselves (api key shown).
    expect(page.locator(".admin-pf-api-key")).not_to_have_class(re.compile(r"\bis-hidden\b"))


# ── Save → sign-in → consent UI ──────────────────────────────────────────


@pytest.mark.browser
def test_create_save_enables_signin_and_click_shows_consent_ui(app_clean: str, page: Page) -> None:
    """Create + save an anthropic-plan provider MANUALLY (base_url
    force-submitted invisibly, save validates), then click the sign-in
    affordance in edit mode — behavior unchanged by the create-mode
    auto-save HAT fix: /oauth/start is called and the consent UI renders —
    the authorize URL as copyable text, an Open button, and the code paste
    field with its confirm control. Popup blocking (or the abort here)
    degrades to the copyable URL without error."""
    _block_claude_ai(page)
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-name").fill("My Plan")
    page.locator("#pf-type").select_option("anthropic-plan")
    save_btn = page.locator(".save-btn")
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    # Create → edit transition: Test button appears, subtitle carries the
    # force-submitted default base_url (proves the hidden field submitted).
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator(".editor-subtitle")).to_contain_text(PLAN_BASE_URL)
    # Sign-in affordance enabled in edit mode; no hint exists anywhere now.
    signin_btn = page.locator('[data-testid="plan-signin-btn"]')
    expect(signin_btn).to_be_visible()
    expect(signin_btn).not_to_be_disabled()
    expect(page.locator('[data-testid="plan-signin-hint"]')).to_have_count(0)

    signin_btn.click()
    # Consent UI: copyable URL + paste field + confirm control.
    consent = page.locator('[data-testid="plan-signin-consent"]')
    expect(consent).to_be_visible(timeout=8000)
    url_input = page.locator('[data-testid="plan-signin-url"]')
    expect(url_input).to_be_visible()
    expect(url_input).to_have_value(re.compile(r"^https://claude\.ai/oauth/authorize\?"))
    expect(page.locator('[data-testid="plan-signin-open-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="plan-signin-copy-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="plan-code-input"]')).to_be_visible()
    expect(page.locator('[data-testid="plan-code-submit-btn"]')).to_be_visible()
    # No error rendered (popup-blocked/aborted degrades silently).
    expect(page.locator('[data-testid="plan-signin-error"]')).to_be_hidden()


@pytest.mark.browser
def test_code_submit_success_shows_connected_state_without_dirty_trap(
    app_clean: str, page: Page
) -> None:
    """Submitting a pasted code renders the connected state (indicator +
    Re-authenticate + Reset; sign-in affordance replaced) with NO
    unsaved-changes trap — the server persisted the tokens, the form
    snapshot is untouched, and Back navigates without a confirm dialog.

    The exchange endpoint is stubbed (network boundary): the real
    /oauth/code path calls Anthropic's token endpoint, which browser tests
    must never do. The success response shape is the real masked provider
    with ``oauth_active: true``."""
    provider_id = _seed_plan_provider(app_clean)
    masked = httpx.get(
        f"{app_clean}/api/providers/{provider_id}", timeout=5.0, headers=auth_headers_for(app_clean)
    ).json()
    assert masked["oauth_active"] is False
    masked["oauth_active"] = True

    _block_claude_ai(page)
    page.route(
        f"**/api/providers/{provider_id}/oauth/code",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(masked)
        ),
    )

    page.goto(f"{app_clean}#admin/providers/{provider_id}")
    signin_btn = page.locator('[data-testid="plan-signin-btn"]')
    expect(signin_btn).to_be_visible(timeout=8000)
    signin_btn.click()
    code_input = page.locator('[data-testid="plan-code-input"]')
    expect(code_input).to_be_visible(timeout=8000)
    code_input.fill("pasted-consent-code")
    page.locator('[data-testid="plan-code-submit-btn"]').click()

    # Connected state: indicator + Re-authenticate + Reset; sign-in gone.
    expect(page.locator('[data-testid="plan-connected-indicator"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="plan-reauth-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="plan-reset-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="plan-signin-btn"]')).to_have_count(0)
    expect(page.locator('[data-testid="plan-signin-consent"]')).to_have_count(0)
    # No unsaved-changes trap: Save/Cancel stay disabled (clean form)…
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()
    # …and Back navigates straight to the grid, no confirm dialog.
    page.locator(".back-btn").click()
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)


@pytest.mark.browser
def test_code_submit_error_renders_inline_and_field_remains_usable(
    app_clean: str, page: Page
) -> None:
    """A failed exchange renders the endpoint's actionable detail as an
    INLINE error (not a vanishing toast) and the paste field remains usable.

    Exercised against the REAL endpoint: an embedded ``code#state`` whose
    state mismatches the pending flow is rejected with 400 BEFORE any
    exchange, so no network leaves the box."""
    provider_id = _seed_plan_provider(app_clean)
    _block_claude_ai(page)
    page.goto(f"{app_clean}#admin/providers/{provider_id}")
    signin_btn = page.locator('[data-testid="plan-signin-btn"]')
    expect(signin_btn).to_be_visible(timeout=8000)
    signin_btn.click()
    code_input = page.locator('[data-testid="plan-code-input"]')
    expect(code_input).to_be_visible(timeout=8000)
    code_input.fill("somecode#state-from-another-window")
    page.locator('[data-testid="plan-code-submit-btn"]').click()

    error_el = page.locator('[data-testid="plan-signin-error"]')
    expect(error_el).to_be_visible(timeout=8000)
    expect(error_el).to_contain_text("different sign-in window")
    # Paste field + confirm remain usable for a retry.
    expect(code_input).to_be_visible()
    expect(code_input).to_be_editable()
    expect(page.locator('[data-testid="plan-code-submit-btn"]')).not_to_be_disabled()


# ── Connected state from REAL seeded encrypted secrets ───────────────────


@pytest.mark.browser
def test_seeded_tokens_render_connected_state_and_stubbed_reauth_message(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """End-to-end ``oauth_active`` derivation: REAL Fernet-encrypted secrets
    seeded via sqlite3 render the connected state, whose Re-authenticate
    control IS the standing re-auth affordance. A route-stubbed /test
    returning ``reauth_required`` renders its message via the EXPLICIT
    branch — distinct from the generic-error branch."""
    base_url, data_dir = app_with_data_dir
    provider_id = _seed_plan_provider(base_url)
    _seed_plan_tokens(data_dir, provider_id)
    # The API derives oauth_active from the seeded encrypted column.
    masked = httpx.get(
        f"{base_url}/api/providers/{provider_id}", timeout=5.0, headers=auth_headers_for(base_url)
    ).json()
    assert masked["oauth_active"] is True
    assert "secrets" not in masked

    _stub_models(page, provider_id)
    reauth_detail = "Re-authentication required: sign in to Anthropic again from Administration."
    page.route(
        f"**/api/providers/{provider_id}/test",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "reauth_required", "detail": reauth_detail}),
        ),
    )

    page.goto(f"{base_url}#admin/providers/{provider_id}")
    # Connected state renders from oauth_active (standing affordance present).
    expect(page.locator('[data-testid="plan-connected-indicator"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="plan-reauth-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="plan-signin-btn"]')).to_have_count(0)

    # /test → distinct reauth message (explicit branch, not else-fail).
    page.locator('[data-testid="test-connection-btn"]').click()
    reauth_msg = page.locator('[data-testid="plan-test-reauth"]')
    expect(reauth_msg).to_be_visible(timeout=8000)
    expect(reauth_msg).to_have_text(reauth_detail)
    # Distinct from the generic-error branch: no fail-styled span rendered.
    expect(page.locator(".test-result .test-result-fail")).to_have_count(0)


@pytest.mark.browser
def test_reauthenticate_runs_consent_flow_over_connected_state(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """Re-authenticate runs the start/paste flow WITHOUT first resetting:
    the consent UI renders while the connected indicator stays (existing
    tokens survive until the new exchange succeeds)."""
    base_url, data_dir = app_with_data_dir
    provider_id = _seed_plan_provider(base_url)
    _seed_plan_tokens(data_dir, provider_id)
    _stub_models(page, provider_id)
    _block_claude_ai(page)

    page.goto(f"{base_url}#admin/providers/{provider_id}")
    reauth_btn = page.locator('[data-testid="plan-reauth-btn"]')
    expect(reauth_btn).to_be_visible(timeout=8000)
    reauth_btn.click()
    expect(page.locator('[data-testid="plan-signin-consent"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="plan-code-input"]')).to_be_visible()
    # Connected state persists underneath — tokens not cleared by re-auth.
    expect(page.locator('[data-testid="plan-connected-indicator"]')).to_be_visible()
    assert (
        httpx.get(
            f"{base_url}/api/providers/{provider_id}",
            timeout=5.0,
            headers=auth_headers_for(base_url),
        ).json()["oauth_active"]
        is True
    )


@pytest.mark.browser
def test_reset_returns_to_signin_state_and_survives_reload(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """Reset (two-step confirm) calls DELETE /oauth for real: the editor
    returns to the sign-in state, and ``oauth_active: false`` is respected
    after a full reload too."""
    base_url, data_dir = app_with_data_dir
    provider_id = _seed_plan_provider(base_url)
    _seed_plan_tokens(data_dir, provider_id)
    _stub_models(page, provider_id)

    page.goto(f"{base_url}#admin/providers/{provider_id}")
    reset_btn = page.locator('[data-testid="plan-reset-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)
    # Two-step inline confirm (canonical destructive-confirm helper).
    reset_btn.click()
    expect(reset_btn).to_have_text(re.compile(r"Confirm Reset\?", re.IGNORECASE))
    reset_btn.click()
    # Back to the sign-in state.
    signin_btn = page.locator('[data-testid="plan-signin-btn"]')
    expect(signin_btn).to_be_visible(timeout=8000)
    expect(signin_btn).not_to_be_disabled()
    expect(page.locator('[data-testid="plan-connected-indicator"]')).to_have_count(0)
    # Local disconnect persisted server-side.
    assert (
        httpx.get(
            f"{base_url}/api/providers/{provider_id}",
            timeout=5.0,
            headers=auth_headers_for(base_url),
        ).json()["oauth_active"]
        is False
    )
    # Respected after reload too.
    page.goto(f"{base_url}#admin/providers/{provider_id}")
    expect(page.locator('[data-testid="plan-signin-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="plan-connected-indicator"]')).to_have_count(0)


# ── Legacy anthropic providers unaffected ────────────────────────────────


@pytest.mark.browser
def test_legacy_anthropic_provider_renders_no_plan_ui(app_clean: str, page: Page) -> None:
    """Legacy ``anthropic`` (API-key) providers: ``oauth_active: false`` in
    their responses must not render any plan UI — the section stays hidden
    and the API-key field stays."""
    r = httpx.post(
        f"{app_clean}/api/providers",
        json={
            "name": "Claude API",
            "type": "anthropic",
            "base_url": PLAN_BASE_URL,
            "api_key": "sk-ant-seedkey1234",
        },
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    )
    assert r.status_code == 201, r.text
    provider_id = r.json()["id"]
    page.goto(f"{app_clean}#admin/providers/{provider_id}")
    expect(page.locator(".editor-title")).to_have_text("Claude API", timeout=8000)
    expect(page.locator(".admin-pf-plan-signin")).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator(".admin-pf-api-key")).not_to_have_class(re.compile(r"\bis-hidden\b"))


# ── Studio functional assertion (AC 7c) ──────────────────────────────────


@pytest.mark.browser
def test_studio_agent_can_select_plan_provider_and_models_populate(
    app_clean: str, page: Page
) -> None:
    """Functional Studio assertion only (no studio code was edited): an
    agent editor can select the plan provider and its model list populates.
    With no tokens seeded, the backend serves the static-catalog fallback —
    acceptable per the leg spec."""
    provider_id = _seed_plan_provider(app_clean)
    page.goto(f"{app_clean}#studio")
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)
    # Sole provider auto-selected (agent-crud precedent).
    expect(page.locator("#studio-provider")).to_have_value(provider_id, timeout=8000)
    # Model list populates from the static fallback.
    expect(page.locator('#studio-model option[value="claude-sonnet-4-6"]')).to_be_attached(
        timeout=8000
    )

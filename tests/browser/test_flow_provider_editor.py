"""Provider editor shape + behavior tests for F6 leg 03.

Covers the canonical editor scaffold (header / form-actions / sections),
disabled-SSoT for Save/Cancel, dirty tracking, Cancel revert vs navigate,
Danger Zone presence, Test button gating, agent-usage hard-block, and the
api-key eye toggle.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _seed_anthropic_provider(
    base_url: str, *, name: str = "Claude", thinking_enabled: bool = False
) -> str:
    """POST an anthropic provider via /api/providers and return its id.

    Used by the Extended-thinking toggle tests (F10-06) that need an existing
    anthropic provider in edit mode (Save starts disabled → toggling the
    checkbox must flip it enabled, guarding the checkbox-aware dirty patch)."""
    payload = {
        "name": name,
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-ant-seedkey1234",
        "config": {"thinking_enabled": thinking_enabled},
    }
    r = httpx.post(
        f"{base_url}/api/providers", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 201, f"seed_anthropic_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _seed_openai_compatible_provider(
    base_url: str,
    *,
    name: str = "compat-orig",
    provider_base_url: str = "https://orig.example.com/v1",
) -> str:
    """POST an openai-compatible provider (base_url + api_key both editable in
    the UI) and return its id. Used by the H1/subtitle re-render regression
    (F7-01): openai-compatible shows the Base URL field so a single save can
    edit BOTH the Name (drives the H1) and the Base URL (drives the subtitle)."""
    payload = {
        "name": name,
        "type": "openai-compatible",
        "base_url": provider_base_url,
        "api_key": "sk-compat-seedkey1234",
    }
    r = httpx.post(
        f"{base_url}/api/providers", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 201, f"seed_openai_compatible_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


# ── Header / scaffold ────────────────────────────────────────────────────


@pytest.mark.browser
def test_editor_renders_canonical_header_in_edit_mode(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-header")).to_be_visible(timeout=8000)
    expect(page.locator(".editor-title")).to_have_text("mock")
    # Subtitle includes provider type. base_url for mock is empty string so we
    # only assert the type token is present.
    expect(page.locator(".editor-subtitle")).to_contain_text("mock")


@pytest.mark.browser
def test_editor_renders_canonical_header_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    # Create mode omits the subtitle paragraph entirely.
    expect(page.locator(".editor-subtitle")).to_have_count(0)


@pytest.mark.browser
def test_header_rerenders_title_and_subtitle_on_edit_save(app_clean: str, page: Page) -> None:
    """F7-01 regression: on an edit→edit save the editor stays mounted, so the
    display-only header (H1 + `type · base_url` subtitle) must be re-rendered
    from the saved provider. Editing BOTH Name and Base URL and saving must
    update the H1 AND the subtitle in place — no reload. Guards the pre-existing
    header-desync fix (both fields are editable; a Name-only re-render would
    leave the subtitle stale by the identical mechanism)."""
    provider_id = _seed_openai_compatible_provider(app_clean)
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("compat-orig", timeout=8000)
    expect(page.locator(".editor-subtitle")).to_contain_text("orig.example.com")
    # Edit both the Name (drives the H1) and the Base URL (drives the subtitle).
    page.locator("#pf-name").fill("compat-edited")
    page.locator("#pf-base-url").fill("https://edited.example.com/v1")
    save_btn = page.locator(".save-btn")
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    # No reload: the header must reflect the saved values in place.
    expect(page.locator(".editor-title")).to_have_text("compat-edited")
    expect(page.locator(".editor-subtitle")).to_contain_text("edited.example.com")
    # And the old values must be gone (catches a stale-node no-op).
    expect(page.locator(".editor-title")).not_to_have_text("compat-orig")
    expect(page.locator(".editor-subtitle")).not_to_contain_text("orig.example.com")


@pytest.mark.browser
def test_editor_action_cluster_order_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    # Back is retired (M25 F3 L5b): the cluster opens with the unsaved caption.
    expect(page.locator(".form-actions .cancel-btn")).to_be_visible(timeout=8000)
    expect(page.locator(".form-actions .back-btn")).to_have_count(0)
    first = page.locator('.form-actions > [data-testid="editor-unsaved"]:first-child')
    expect(first).to_have_count(1)
    expect(page.locator(".form-actions .save-btn")).to_be_visible()
    expect(page.locator('.form-actions [data-testid="test-connection-btn"]')).to_be_visible()
    expect(page.locator(".editor-header .editor-error")).to_have_count(1)


@pytest.mark.browser
def test_editor_action_cluster_order_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".form-actions .cancel-btn")).to_be_visible(timeout=8000)
    expect(page.locator(".form-actions .back-btn")).to_have_count(0)
    expect(page.locator(".form-actions .save-btn")).to_be_visible()
    # No Test button in create mode.
    expect(page.locator('.form-actions [data-testid="test-connection-btn"]')).to_have_count(0)
    expect(page.locator(".editor-header .editor-error")).to_have_count(1)


# ── Save / Cancel disabled-SSoT ──────────────────────────────────────────


@pytest.mark.browser
def test_save_and_cancel_disabled_when_clean(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_save_and_cancel_enabled_when_dirty(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    page.locator("#pf-name").fill("mock-edited")
    expect(page.locator(".save-btn")).not_to_be_disabled()
    expect(page.locator(".cancel-btn")).not_to_be_disabled()


@pytest.mark.browser
def test_cancel_reverts_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    page.locator("#pf-name").fill("mock-edited")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator("#pf-name")).to_have_value("mock")
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


@pytest.mark.browser
def test_create_cancel_navigates_to_library_when_dirty(app_clean: str, page: Page) -> None:
    """Cancel on a dirty create form discards it and returns to the Library root
    (replace, no dialog); with no row to return to, focus goes to the list's
    Add menu (M25 F3 L5b, DD8)."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-name").fill("typed-name")
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    expect(_lists.library_start(page)).to_be_visible()
    _nav.expect_route(page, "library")
    expect(page.locator('[data-testid="library-add-btn"]')).to_be_focused()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)


@pytest.mark.browser
def test_header_has_breadcrumb_and_no_back(app_with_provider: SeededApp, page: Page) -> None:
    """Replaces the Back-always-enabled test (M25 F3 L5b retired Back): the
    header's breadcrumb reads "Library / Model providers", its "Library" segment
    links to the Library root, and no Back control exists."""
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    crumb = page.locator(".editor-header-text > .editor-breadcrumb:first-child")
    expect(crumb).to_have_text("Library / Model providers", timeout=8000)
    link = crumb.locator('[data-testid="editor-breadcrumb-link"]')
    expect(link).to_have_text("Library")
    expect(link).to_have_attribute("href", _nav.href("library"))
    expect(page.locator(".back-btn")).to_have_count(0)
    # The title is the pane's one h1 (Library chrome).
    expect(page.locator("h1.editor-title")).to_have_attribute("tabindex", "-1")
    expect(page.locator(".content-panel.active h1")).to_have_count(1)


# ── Danger Zone ──────────────────────────────────────────────────────────


@pytest.mark.browser
def test_danger_zone_renders_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    expect(page.locator(".section-title.danger-zone-title")).to_have_text("Danger zone")
    expect(page.locator('[data-testid="delete-provider-btn"]')).to_be_visible()


@pytest.mark.browser
def test_danger_zone_omitted_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    expect(page.locator(".editor-section.danger-zone")).to_have_count(0)


@pytest.mark.browser
def test_delete_two_step_confirm(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    # First click arms the button. No agents use this provider, so no
    # hard-block.
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm delete\?", re.IGNORECASE))
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))
    # Second click actually deletes: back to the Library root; the list had one
    # provider row, so focus goes to the Add menu (M25 F3 L5b, DD8).
    delete_btn.click()
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible()
    # HAT: the toast outlives the closed editor (it is flashed to the page, not the editor).
    expect(page.locator(".app-flash").filter(has_text="Provider deleted")).to_be_visible(
        timeout=3000
    )
    expect(page.locator('[data-testid="library-add-btn"]')).to_be_focused()


@pytest.mark.browser
def test_delete_error_toast_has_no_error_prefix(app_with_provider: SeededApp, page: Page) -> None:
    """A14: a failed delete flashes the server's message as is, without an "Error: " prefix."""
    page.route(
        "**/api/providers/*",
        lambda route: (
            route.fulfill(
                status=500, content_type="application/json", body='{"detail": "Disk is full"}'
            )
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )
    _nav.goto_settled(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    delete_btn.click()
    delete_btn.click()
    expect(page.locator(".app-flash.error")).to_have_text("Disk is full", timeout=5000)


@pytest.mark.browser
def test_delete_blocked_when_provider_in_use(app_with_agent: SeededApp, page: Page) -> None:
    """A provider in use shows, on open, one box: who uses it (as links), the checkbox
    and the Delete button; Delete stays disabled, with no timed lockout, until the
    checkbox is ticked (M36 F1 HAT)."""
    _nav.goto(
        page, app_with_agent.base_url, f"library/providers/{_nav.seg(app_with_agent.provider_id)}"
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    blocked_msg = page.locator('[data-testid="delete-blocked-message"]')
    expect(blocked_msg).to_be_visible(timeout=8000)  # on open, no Delete click first
    expect(blocked_msg).to_contain_text("This provider is used by")
    expect(blocked_msg).to_contain_text(
        "If you delete it, it will need a new model before it can answer."
    )
    # The Delete button sits inside the same box, after the checkbox.
    box_el = page.locator(".provider-delete-box")
    expect(box_el.locator('[data-testid="delete-provider-btn"]')).to_have_count(1)
    assert app_with_agent.agent_name is not None
    link = blocked_msg.locator('[data-testid="delete-user-link"]')
    expect(link).to_have_text(app_with_agent.agent_name)
    assert (link.get_attribute("href") or "").endswith(f"agents/{app_with_agent.agent_name}")
    box = page.locator('[data-testid="delete-force-checkbox"]')
    expect(box).not_to_be_checked()
    expect(delete_btn).to_be_disabled()
    # No timed lockout: still disabled well past the old 3 s, and the notice stays.
    page.wait_for_timeout(3500)
    expect(delete_btn).to_be_disabled()
    expect(blocked_msg).to_be_visible()
    box.check()
    expect(delete_btn).to_be_enabled()
    box.uncheck()
    expect(delete_btn).to_be_disabled()


@pytest.mark.browser
def test_forced_delete_clears_agent_and_gleepglorp(app_with_agent: SeededApp, page: Page) -> None:
    """Tick, arm, confirm: the provider goes and its users need a model."""
    base = app_with_agent.base_url
    headers = auth_headers_for(base)
    gg = {
        "enabled": True,
        "provider_config_id": app_with_agent.provider_id,
        "model": "mock-default",
        "web_access": True,
        "memory": True,
        "retention_days": 30,
    }
    assert (
        httpx.put(f"{base}/api/gleepglorp", json=gg, headers=headers, timeout=5.0).status_code
        == 200
    )
    _nav.goto(page, base, f"library/providers/{_nav.seg(app_with_agent.provider_id)}")
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    blocked_msg = page.locator('[data-testid="delete-blocked-message"]')
    expect(blocked_msg).to_contain_text("GleepGlorp", timeout=8000)
    gg_link = blocked_msg.locator('[data-testid="delete-user-link"]', has_text="GleepGlorp")
    assert (gg_link.get_attribute("href") or "").endswith("settings/gleepglorp")
    page.locator('[data-testid="delete-force-checkbox"]').check()
    delete_btn.click()
    expect(delete_btn).to_contain_text("Confirm delete?")
    delete_btn.click()
    expect(page.locator(".app-flash")).to_contain_text("Cleared the model for", timeout=8000)
    providers = httpx.get(f"{base}/api/providers", headers=headers, timeout=5.0).json()
    assert all(p["id"] != app_with_agent.provider_id for p in providers)
    agent = httpx.get(
        f"{base}/api/agents/{app_with_agent.agent_name}", headers=headers, timeout=5.0
    )
    assert not agent.json().get("provider_config_id")
    assert not agent.json().get("llm_model")
    state = httpx.get(f"{base}/api/gleepglorp", headers=headers, timeout=5.0).json()
    assert state["state"] == "needs_model"
    assert state["provider_config_id"] is None and state["model"] is None


@pytest.mark.browser
def test_unticking_while_armed_takes_the_arm_back_and_the_reason_is_tied(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Review fix: Delete is described by the explanation, the checkbox too; unticking the
    box while Delete is armed puts it back to its resting, disabled state."""
    _nav.goto(
        page, app_with_agent.base_url, f"library/providers/{_nav.seg(app_with_agent.provider_id)}"
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    msg = page.locator('[data-testid="delete-blocked-message"]')
    expect(msg).to_be_visible(timeout=8000)
    box = page.locator('[data-testid="delete-force-checkbox"]')
    msg_id = msg.get_attribute("id")
    assert msg_id
    assert msg_id in (delete_btn.get_attribute("aria-describedby") or "").split()
    assert msg_id in (box.get_attribute("aria-describedby") or "").split()
    resting = delete_btn.inner_text()
    box.check()
    delete_btn.click()
    expect(delete_btn).to_contain_text("Confirm delete?")
    box.uncheck()
    # Within the 3 s arm window (the timeout), so the timed lapse cannot be what reverts it.
    expect(delete_btn).not_to_contain_text("Confirm delete?", timeout=1000)
    expect(delete_btn).not_to_have_class(re.compile(r"confirm-delete"), timeout=1000)
    expect(delete_btn).to_be_disabled()
    assert delete_btn.inner_text() == resting


@pytest.mark.browser
def test_a_failed_forced_delete_returns_focus_to_the_rebuilt_checkbox(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Review fix: after a failed delete rebuilds the box, focus that was inside it goes to
    the new checkbox, not to the page."""
    _nav.goto(
        page, app_with_agent.base_url, f"library/providers/{_nav.seg(app_with_agent.provider_id)}"
    )
    page.route(
        "**/api/providers/*?force=true",
        lambda route: (
            route.fulfill(
                status=500, content_type="application/json", body='{"detail": "Disk is full"}'
            )
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    box = page.locator('[data-testid="delete-force-checkbox"]')
    expect(box).to_be_visible(timeout=8000)
    box.check()
    delete_btn.click()
    delete_btn.click()
    expect(page.locator(".app-flash.error")).to_have_text("Disk is full", timeout=5000)
    expect(page.locator('[data-testid="delete-force-checkbox"]')).to_be_focused(timeout=5000)
    expect(page.locator('[data-testid="delete-force-checkbox"]')).not_to_be_checked()


@pytest.mark.browser
def test_delete_confirm_lapse_is_visually_distinct(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the Danger Zone
    provider-delete confirm — the no-agent-usage arming path
    (`provider-editor.js:946`) — is distinguishable on screen from one
    that was never armed, past the real 3s `revertMs`."""
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm delete\?", re.IGNORECASE))
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_contain_text("Delete provider")
    # Never committed: still on the editor, provider still there.
    _nav.expect_route(page, f"library/providers/{_nav.seg(app_with_provider.provider_id)}")


@pytest.mark.browser
def test_delete_confirm_lapse_via_fail_open_path_is_visually_distinct(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Same as above, but reached via the network-failure fail-open arming
    path (`provider-editor.js:951`) — the agent-usage pre-gate fetch
    itself fails, so the button arms anyway. Both arming paths feed the
    same shared `App.confirmDelete`, so the lapse cue is identical."""
    page.route(
        f"**/api/providers/{app_with_provider.provider_id}/agents",
        lambda route: route.abort("failed"),
    )
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_text(re.compile(r"Confirm delete\?", re.IGNORECASE), timeout=5000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_contain_text("Delete provider")


# ── Test button ──────────────────────────────────────────────────────────


@pytest.mark.browser
def test_test_button_omitted_in_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    expect(page.locator('[data-testid="test-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_test_button_visible_in_edit_mode(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_test_result_uses_canonical_class(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    test_btn = page.locator('[data-testid="test-connection-btn"]')
    expect(test_btn).to_be_visible(timeout=8000)
    test_btn.click()
    # Mock provider returns ok; the result is the success status line.
    expect(
        page.locator('[data-testid="provider-test-result"][data-state="success"]')
    ).to_be_visible(timeout=5000)


# ── API-key eye toggle ──────────────────────────────────────────────────


@pytest.mark.browser
def test_api_key_eye_toggle(app_clean: str, page: Page) -> None:
    """Open the create editor, switch type to openai (api-key field shown), toggle eye."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("openai")
    api_key = page.locator("#pf-api-key")
    expect(api_key).to_have_attribute("type", "password")
    eye = page.get_by_role("button", name="Show password")
    expect(eye).to_have_attribute("aria-pressed", "false")
    eye.click()
    expect(api_key).to_have_attribute("type", "text")
    expect(page.get_by_role("button", name="Hide password")).to_have_attribute(
        "aria-pressed", "true"
    )
    page.get_by_role("button", name="Hide password").click()
    expect(api_key).to_have_attribute("type", "password")


@pytest.mark.browser
def test_masked_key_round_trip_and_remask_after_save(app_clean: str, page: Page) -> None:
    """The `__MASKED__` contract, and the re-mask fix: an untouched key is sent as the
    sentinel; a changed key is sent as typed and the field shows the server's masked value
    after Save (hidden again), so the plaintext is not re-sent by the next Save; Cancel
    after typing restores the masked value."""
    pid = _seed_openai_compatible_provider(app_clean)
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(pid)}")
    name = page.locator("#pf-name")
    key = page.locator("#pf-api-key")
    expect(name).to_have_value("compat-orig", timeout=8000)
    masked = key.input_value()
    assert masked and "seedkey" not in masked

    bodies: list[dict] = []

    def capture(route):
        if route.request.method == "PUT":
            bodies.append(route.request.post_data_json)
        route.continue_()

    page.route(f"**/api/providers/{pid}", capture)

    # 1. Untouched key: the sentinel is sent.
    name.fill("compat-renamed")
    page.locator('[data-testid="save-provider-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("compat-renamed", timeout=8000)
    assert bodies[-1]["api_key"] == "__MASKED__"

    # 2. A changed key is sent as typed; afterwards the field is masked and hidden again.
    page.get_by_role("button", name="Show password").click()
    expect(key).to_have_attribute("type", "text")
    key.fill("sk-brand-new-key-9999")
    page.locator('[data-testid="save-provider-btn"]').click()
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled(timeout=8000)
    assert bodies[-1]["api_key"] == "sk-brand-new-key-9999"
    expect(key).to_have_attribute("type", "password")
    expect(page.get_by_role("button", name="Show password")).to_have_attribute(
        "aria-pressed", "false"
    )
    remasked = key.input_value()
    assert "brand-new" not in remasked
    assert remasked != "sk-brand-new-key-9999"

    # 3. The next Save sends the sentinel again, not the earlier plaintext.
    name.fill("compat-renamed-2")
    page.locator('[data-testid="save-provider-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("compat-renamed-2", timeout=8000)
    assert bodies[-1]["api_key"] == "__MASKED__"

    # 4. Cancel after typing restores the masked value (and hides it).
    page.get_by_role("button", name="Show password").click()
    key.fill("sk-typed-then-cancelled")
    page.locator('[data-testid="cancel-provider-btn"]').click()
    expect(key).to_have_value(remasked)
    expect(key).to_have_attribute("type", "password")


# ── Context window (num_ctx) field — F09-05 polish ───────────────────────


@pytest.mark.browser
def test_num_ctx_field_shown_for_ollama_with_default_prefill(app_clean: str, page: Page) -> None:
    """Selecting the ollama type reveals a required Context window field
    pre-filled with the default window (32768)."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("ollama")
    num_ctx = page.locator("#pf-num-ctx")
    expect(num_ctx).to_be_visible()
    expect(num_ctx).to_have_value("32768")
    expect(num_ctx).to_have_attribute("type", "number")
    expect(num_ctx).to_have_attribute("required", "")
    # Canonical label text (no longer the parenthetical num_ctx form).
    expect(page.locator('label[for="pf-num-ctx"]')).to_have_text("Context window")


def _assert_described_by(page: Page, selector: str, desc: str) -> None:
    """The control's aria-describedby names the info button's visually hidden description."""
    ids = (page.locator(selector).get_attribute("aria-describedby") or "").split()
    assert ids, selector
    texts = [page.locator(f"#{i}").text_content() for i in ids]
    assert desc in texts, (selector, texts)


@pytest.mark.browser
def test_num_ctx_field_hidden_for_non_ollama(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("openai")
    expect(page.locator(".admin-pf-num-ctx")).to_be_hidden()


@pytest.mark.browser
def test_num_ctx_info_icon_tooltip(app_clean: str, page: Page) -> None:
    """The description is a focusable info-icon button (a press-only toggletip) with a
    visually-hidden span wired via aria-describedby — mirrors the
    field-info-icon pattern used by the tools editor."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("ollama")
    desc = (
        "A larger window allows longer conversations but will slow down on "
        "partial-GPU setups because fewer layers fit in VRAM"
    )
    icon = page.locator(".admin-pf-num-ctx .field-info-icon")
    expect(icon).to_be_visible()
    assert icon.get_attribute("title") is None  # press-only: no hover tooltip
    expect(icon).to_have_attribute("aria-expanded", "false")
    icon.click()
    expect(icon).to_have_attribute("aria-expanded", "true")
    bubble = page.locator(f"#{icon.get_attribute('aria-controls')}")
    expect(bubble).to_be_visible()
    expect(bubble).to_have_text(desc)
    icon.click()
    expect(bubble).to_be_hidden()
    assert icon.get_attribute("aria-describedby") is None  # label carries the hint
    _assert_described_by(page, "#pf-num-ctx", desc)


# ── Extended thinking (config.thinking_enabled) toggle — F10-06 ──────────


@pytest.mark.browser
def test_thinking_toggle_shown_for_anthropic_checked_by_default(app_clean: str, page: Page) -> None:
    """Selecting a Claude type on the create form reveals an Extended-thinking
    checkbox, checked by default (sortie 17), for every Claude type and after
    switching type back and forth."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic")
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("type", "checkbox")
    expect(toggle).to_be_checked()
    expect(page.locator('label[for="pf-thinking-enabled"]')).to_have_text("Extended thinking")
    page.locator("#pf-type").select_option("openai")
    expect(page.locator(".admin-pf-thinking-enabled")).to_be_hidden()
    page.locator("#pf-type").select_option("anthropic-plan-token")
    expect(toggle).to_be_visible()
    expect(toggle).to_be_checked()


@pytest.mark.browser
def test_create_without_touching_thinking_saves_enabled(app_clean: str, page: Page) -> None:
    """Saving a new Claude provider without touching the switch stores true."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic")
    page.locator("#pf-name").fill("Claude default on")
    page.locator("#pf-api-key").fill("sk-ant-createkey1234")
    save_btn = page.locator(".save-btn")
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    # A create opens the new item (no flash): wait for its editor route.
    _nav.wait_for_route_prefix(
        page, "library/providers/", not_equal="library/providers/~new", timeout=8000
    )
    r = httpx.get(f"{app_clean}/api/providers", timeout=5.0, headers=auth_headers_for(app_clean))
    row = next(p for p in r.json() if p["name"] == "Claude default on")
    assert row["config"]["thinking_enabled"] is True


@pytest.mark.browser
def test_stored_false_thinking_opens_unchecked_and_clean(app_clean: str, page: Page) -> None:
    provider_id = _seed_anthropic_provider(app_clean, thinking_enabled=False)
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    expect(page.locator("#pf-thinking-enabled")).not_to_be_checked()
    expect(page.locator(".save-btn")).to_be_disabled()


@pytest.mark.browser
def test_thinking_toggle_hidden_for_non_anthropic(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("openai")
    expect(page.locator(".admin-pf-thinking-enabled")).to_be_hidden()


@pytest.mark.browser
def test_thinking_toggle_info_icon_tooltip(app_clean: str, page: Page) -> None:
    """The description is a focusable info-icon button (a press-only toggletip) with a
    visually-hidden span wired via aria-describedby — mirrors the num_ctx
    field-info-icon a11y idiom."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic")
    desc = (
        "When on, models that support adaptive thinking (Claude models from version 4.6 on) "
        "reason step by step before answering. Older models on this provider answer without it."
    )
    icon = page.locator(".admin-pf-thinking-enabled .field-info-icon")
    expect(icon).to_be_visible()
    assert icon.get_attribute("title") is None  # press-only: no hover tooltip
    expect(icon).to_have_attribute("aria-expanded", "false")
    icon.click()
    expect(icon).to_have_attribute("aria-expanded", "true")
    bubble = page.locator(f"#{icon.get_attribute('aria-controls')}")
    expect(bubble).to_be_visible()
    expect(bubble).to_have_text(desc)
    icon.click()
    expect(bubble).to_be_hidden()
    assert icon.get_attribute("aria-describedby") is None  # label carries the hint
    _assert_described_by(page, "#pf-thinking-enabled", desc)


def _flip_thinking(page: Page) -> None:
    """Flip the Extended thinking switch the way a user does: click its visible label."""
    page.locator("label", has=page.locator("#pf-thinking-enabled")).click()


@pytest.mark.browser
def test_thinking_toggle_flips_save_from_disabled_to_enabled(app_clean: str, page: Page) -> None:
    """Toggling the checkbox on an existing (clean) anthropic provider marks
    the form dirty (Save flips from disabled → enabled). Directly guards the
    [high] checkbox-aware getFormSnapshot patch — fails loudly if the snapshot
    ignores .checked."""
    provider_id = _seed_anthropic_provider(app_clean, thinking_enabled=False)
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).to_be_visible()
    expect(toggle).not_to_be_checked()
    # Clean form → Save disabled.
    expect(page.locator(".save-btn")).to_be_disabled()
    _flip_thinking(page)
    # Checkbox toggle must mark the form dirty.
    expect(page.locator(".save-btn")).not_to_be_disabled()
    expect(page.locator(".cancel-btn")).not_to_be_disabled()


@pytest.mark.browser
def test_thinking_toggle_saves_and_reopens_checked(app_clean: str, page: Page) -> None:
    """Toggle on + Save + reload → the checkbox re-renders checked (edit-load
    reflects the stored config.thinking_enabled)."""
    provider_id = _seed_anthropic_provider(app_clean, thinking_enabled=False)
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).not_to_be_checked()
    _flip_thinking(page)
    save_btn = page.locator(".save-btn")
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    # Reload the editor from scratch → the stored value must round-trip.
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    expect(page.locator("#pf-thinking-enabled")).to_be_checked()


@pytest.mark.browser
def test_thinking_toggle_cancel_reverts(app_clean: str, page: Page) -> None:
    """Cancel after toggling reverts the checkbox to its snapshot state
    (checkbox-aware Cancel-revert patch)."""
    provider_id = _seed_anthropic_provider(app_clean, thinking_enabled=False)
    _nav.goto(page, app_clean, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude", timeout=8000)
    toggle = page.locator("#pf-thinking-enabled")
    expect(toggle).not_to_be_checked()
    _flip_thinking(page)
    expect(page.locator(".cancel-btn")).not_to_be_disabled()
    page.locator(".cancel-btn").click()
    expect(page.locator("#pf-thinking-enabled")).not_to_be_checked()
    expect(page.locator(".save-btn")).to_be_disabled()
    expect(page.locator(".cancel-btn")).to_be_disabled()


# ── Inline link colour (mission-close A1) ─────────────────────────────────


@pytest.mark.browser
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_models_help_agents_link_uses_accent_colour(
    app_with_provider: SeededApp, page: Page, theme: str
) -> None:
    """A bare <a> has no class rule of its own; without the base-layer link
    default it rendered in the UA blue. It must resolve to --accent in both
    themes."""
    page.add_init_script(
        f"try {{ localStorage.setItem('theme-preference', '{theme}'); }} catch (e) {{}}"
    )
    _nav.goto(
        page,
        app_with_provider.base_url,
        f"library/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    link = page.locator('[data-testid="provider-models-agents-link"]')
    expect(link).to_be_visible(timeout=8000)
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    colors = page.evaluate(
        """() => {
          const probe = document.createElement('span');
          probe.style.color = 'var(--accent)';
          document.body.appendChild(probe);
          const accent = getComputedStyle(probe).color;
          probe.remove();
          const link = document.querySelector('[data-testid="provider-models-agents-link"]');
          return { link: getComputedStyle(link).color, accent };
        }"""
    )
    assert colors["link"] == colors["accent"], colors


# ── Squawk 0236: Save is busy while the request is in flight ─────────────


def _fill_create_form(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("openai-compatible")
    page.locator("#pf-name").fill(name)
    page.locator("#pf-base-url").fill("https://busy.example.com/v1")
    page.locator("#pf-api-key").fill("sk-busy-key-1234")


def _provider_count(base: str) -> int:
    r = httpx.get(f"{base}/api/providers", timeout=5.0, headers=auth_headers_for(base))
    return len(r.json())


def _hold_provider_posts(page: Page) -> tuple[list, list]:
    held: list = []
    posts: list[str] = []

    def handler(route) -> None:
        if route.request.method == "POST":
            posts.append(route.request.url)
            held.append(route)
        else:
            route.continue_()

    page.route("**/api/providers", handler)
    return held, posts


@pytest.mark.browser
def test_double_click_on_create_sends_one_post_and_locks_the_form(
    app_clean: str, page: Page
) -> None:
    """Squawk 0236: Create had no busy state, so two quick clicks made two providers.
    While the POST is held, Save, Cancel and Test are disabled; a 201 makes one provider."""
    _fill_create_form(page, app_clean, "Busy create")
    held, posts = _hold_provider_posts(page)
    save = page.locator('[data-testid="save-provider-btn"]')
    save.evaluate("el => { el.click(); el.click(); }")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the create POST never left the page"
    expect(save).to_be_disabled()
    expect(page.locator('[data-testid="cancel-provider-btn"]')).to_be_disabled()
    page.evaluate("() => { const b = document.querySelector('.save-btn'); if (b) b.click(); }")
    page.wait_for_timeout(300)
    assert len(posts) == 1, posts
    held[0].continue_()
    page.unroute("**/api/providers")
    expect(page.locator(".editor-title")).to_have_text("Busy create", timeout=8000)
    assert len(posts) == 1, posts
    assert _provider_count(app_clean) == 1


@pytest.mark.browser
def test_failed_create_restores_the_form_after_the_busy_state(app_clean: str, page: Page) -> None:
    _fill_create_form(page, app_clean, "Busy fail")
    held, posts = _hold_provider_posts(page)
    save = page.locator('[data-testid="save-provider-btn"]')
    save.evaluate("el => { el.click(); el.click(); }")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held
    expect(save).to_be_disabled()
    held[0].fulfill(
        status=500, content_type="application/json", body='{"detail": "provider exploded"}'
    )
    expect(page.locator(".editor-error")).to_contain_text("provider exploded", timeout=8000)
    expect(save).not_to_be_disabled()
    expect(page.locator('[data-testid="cancel-provider-btn"]')).not_to_be_disabled()
    assert len(posts) == 1, posts
    assert _provider_count(app_clean) == 0


@pytest.mark.browser
def test_edit_save_is_busy_then_restored(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    pid = app_with_provider.provider_id
    _nav.goto(page, base, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    page.locator("#pf-name").fill("renamed busy")
    held: list = []
    puts: list[str] = []

    def handler(route) -> None:
        if route.request.method == "PUT":
            puts.append(route.request.url)
            held.append(route)
        else:
            route.continue_()

    page.route(f"**/api/providers/{pid}", handler)
    save = page.locator('[data-testid="save-provider-btn"]')
    save.evaluate("el => { el.click(); el.click(); }")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held
    expect(save).to_be_disabled()
    expect(page.locator('[data-testid="cancel-provider-btn"]')).to_be_disabled()
    held[0].continue_()
    page.unroute(f"**/api/providers/{pid}")
    expect(page.locator(".editor-title")).to_have_text("renamed busy", timeout=8000)
    expect(page.locator('[data-testid="cancel-provider-btn"]')).to_be_disabled()
    assert len(puts) == 1, puts


@pytest.mark.browser
def test_double_click_on_create_mode_plan_signin_sends_one_post(app_clean: str, page: Page) -> None:
    """The create-mode plan sign-in button shares performSave, so it is busy too."""
    from browser import _providers

    _providers.block_claude_ai(page)
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic-plan")
    page.locator("#pf-name").fill("Busy plan")
    held, posts = _hold_provider_posts(page)
    page.locator('[data-testid="plan-signin-btn"]').evaluate("el => { el.click(); el.click(); }")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled()
    page.wait_for_timeout(300)
    assert len(posts) == 1, posts
    held[0].continue_()
    page.unroute("**/api/providers")
    expect(page.locator('[data-testid="plan-signin-consent"]')).to_be_visible(timeout=8000)
    assert len(posts) == 1, posts
    assert _provider_count(app_clean) == 1

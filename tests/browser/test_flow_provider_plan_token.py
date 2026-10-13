"""Browser tests for the Claude Plan (Token) provider editor (sortie 03, DD6/DD7).

Synthetic tokens only; no request ever leaves the box for Anthropic: the
provider's ``/models`` and ``/test`` calls are stubbed with ``page.route``.
The expiry line is day-granular, so the older / soon / past states are
rendered from a ``page.route``-patched provider row (the server stamps "now"
on every real create or change).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, Route, expect

TOKEN = "sk-ant-oat01-test-synthetic-token-value"
NEW_TOKEN = "sk-ant-oat01-test-another-synthetic-token"
BASE = "https://api.anthropic.com"

_PROVIDER_URL = re.compile(r".*/api/providers(/[^/?]+)?(\?.*)?$")


def _seed_token_provider(base_url: str, name: str = "Claude Token") -> str:
    r = httpx.post(
        f"{base_url}/api/providers",
        json={"name": name, "type": "anthropic-plan-token", "base_url": BASE, "api_key": TOKEN},
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code == 201, f"seed failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _stub_network(page: Page) -> None:
    """No call to Anthropic: stub the editor's /models fetch and /test."""
    page.route(
        re.compile(r".*/api/providers/[^/]+/models(\?.*)?$"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [{"id": "claude-haiku-4-5", "name": "claude-haiku-4-5", "context_length": 200000}]
            ),
        ),
    )
    page.route(
        re.compile(r".*/api/providers/[^/]+/test$"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "ok", "detail": "Connected to Anthropic (plan token)"}),
        ),
    )


def _stamp_days_ago(page: Page, provider_id: str, days: int) -> None:
    """Patch the provider row's stamp so the line renders for an older token."""
    set_at = datetime.now(timezone.utc) - timedelta(days=days)
    expires = set_at + timedelta(days=365)

    def _patch_row(row: dict) -> None:
        if row.get("id") == provider_id:
            row["token_set_at"] = set_at.isoformat()
            row["token_expires_around"] = expires.isoformat()

    def _handler(route: Route) -> None:
        if route.request.method != "GET":
            route.continue_()
            return
        response = route.fetch()
        body = response.json()
        if isinstance(body, list):
            for row in body:
                if isinstance(row, dict):
                    _patch_row(row)
        elif isinstance(body, dict):
            _patch_row(body)
        route.fulfill(response=response, json=body)

    page.route(_PROVIDER_URL, _handler)


def _fmt(page: Page, iso: str) -> str:
    return page.evaluate("(iso) => App.time.formatDate(new Date(iso))", iso)


def _open_edit(page: Page, base_url: str, provider_id: str) -> None:
    _nav.goto(page, base_url, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("Claude Token", timeout=8000)


@pytest.mark.browser
def test_type_list_and_create_flow_shows_token_field_without_signin(
    app_clean: str, page: Page
) -> None:
    _stub_network(page)
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    options = page.locator("#pf-type option:not([disabled])")
    labels = options.all_text_contents()
    assert labels.index("Claude Plan (Token)") == labels.index("Claude Plan (OAuth)") + 1

    page.locator("#pf-type").select_option("anthropic-plan-token")
    label = page.locator('label[for="pf-api-key"]')
    key = page.locator("#pf-api-key")
    expect(label).to_have_text("Token")
    expect(key).to_have_attribute("placeholder", "sk-ant-oat01-…")
    help_line = page.locator('[data-testid="provider-api-key-help"]')
    expect(help_line).to_be_visible()
    expect(help_line).to_contain_text("claude setup-token")
    expect(key).to_have_attribute("aria-describedby", "pf-api-key-help")
    expect(page.locator(".admin-pf-base-url")).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator(".admin-pf-plan-signin")).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator(".admin-pf-api-key")).not_to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator('[data-testid="provider-token-expiry"]')).to_have_count(0)

    # Switching the type relabels the same row and clears the help.
    page.locator("#pf-type").select_option("anthropic")
    expect(label).to_have_text("API Key")
    expect(key).to_have_attribute("placeholder", "sk-...")
    expect(help_line).to_be_hidden()
    assert key.get_attribute("aria-describedby") is None
    page.locator("#pf-type").select_option("anthropic-plan-token")
    expect(label).to_have_text("Token")
    expect(help_line).to_be_visible()

    page.locator("#pf-name").fill("Claude Token")
    key.fill(TOKEN)
    page.locator('[data-testid="save-provider-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("Claude Token", timeout=8000)
    today = page.evaluate("() => App.time.formatDate(new Date())")
    line = page.locator('[data-testid="provider-token-expiry"]')
    expect(line).to_be_visible(timeout=8000)
    expect(line).to_contain_text(f"Token added {today}")
    expect(line).to_contain_text("expires around")
    expect(line).to_have_attribute("data-state", "ok")
    # The stored token never reaches the page.
    expect(page.locator("body")).not_to_contain_text(TOKEN)


@pytest.mark.browser
def test_edit_mode_expiry_line_and_refresh_after_save(app_clean: str, page: Page) -> None:
    provider_id = _seed_token_provider(app_clean)
    _stub_network(page)
    _stamp_days_ago(page, provider_id, 200)
    _open_edit(page, app_clean, provider_id)

    line = page.locator('[data-testid="provider-token-expiry"]')
    expect(line).to_be_visible(timeout=8000)
    old_set_at = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    old_text = _fmt(page, old_set_at)
    today = page.evaluate("() => App.time.formatDate(new Date())")
    assert old_text != today
    expect(line).to_contain_text(f"Token added {old_text}")
    expect(line).to_have_attribute("data-state", "ok")

    # Paste a new token and Save through the real PUT: the line updates with
    # no reload (the edit-mode Save does not re-mount the editor).
    page.locator("#pf-api-key").fill(NEW_TOKEN)
    page.locator('[data-testid="save-provider-btn"]').click()
    expect(line).to_contain_text(f"Token added {today}", timeout=8000)
    expect(line).to_have_attribute("data-state", "ok")


@pytest.mark.browser
@pytest.mark.parametrize(
    "days,state,wording",
    [
        (340, "soon", "Expires around"),
        (400, "past", "This token may have expired (around"),
    ],
)
def test_expiry_line_soon_and_past_states(
    app_clean: str, page: Page, days: int, state: str, wording: str
) -> None:
    provider_id = _seed_token_provider(app_clean)
    _stub_network(page)
    _stamp_days_ago(page, provider_id, days)
    _open_edit(page, app_clean, provider_id)
    line = page.locator('[data-testid="provider-token-expiry"]')
    expect(line).to_be_visible(timeout=8000)
    expect(line).to_have_attribute("data-state", state)
    expect(line).to_have_class(re.compile(rf"\btoken-expiry--{state}\b"))
    expect(line).to_contain_text(wording)
    expect(line).to_contain_text("Run claude setup-token and paste a new token.")


@pytest.mark.browser
def test_expiry_line_hides_when_type_leaves_token_and_returns(app_clean: str, page: Page) -> None:
    provider_id = _seed_token_provider(app_clean)
    _stub_network(page)
    _open_edit(page, app_clean, provider_id)
    line = page.locator('[data-testid="provider-token-expiry"]')
    expect(line).to_be_visible(timeout=8000)
    page.locator("#pf-type").select_option("anthropic")
    expect(line).to_have_count(0)
    page.locator("#pf-type").select_option("anthropic-plan-token")
    expect(line).to_be_visible()


@pytest.mark.browser
def test_plan_token_expiry_thresholds_at_both_edges(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library")
    page.wait_for_function("() => !!(window.App && App.studio && App.studio.planTokenExpiry)")
    got = page.evaluate(
        """() => {
          const DAY = 86400000;
          const expires = Date.UTC(2027, 0, 15, 12, 0);
          const set = Date.UTC(2026, 0, 15, 12, 0);
          const iso = (t) => new Date(t).toISOString();
          const st = (now) => App.studio.planTokenExpiry(iso(set), iso(expires), now).state;
          return {
            far: st(expires - 31 * DAY),
            justOutside: st(expires - 30 * DAY - 1),
            exactlyThirty: st(expires - 30 * DAY),
            oneMsBefore: st(expires - 1),
            atExpiry: st(expires),
            after: st(expires + DAY),
            bad: App.studio.planTokenExpiry('nope', iso(expires), 0),
          };
        }"""
    )
    assert got == {
        "far": "ok",
        "justOutside": "ok",
        "exactlyThirty": "soon",
        "oneMsBefore": "soon",
        "atExpiry": "past",
        "after": "past",
        "bad": None,
    }


@pytest.mark.browser
def test_test_button_reports_ok_with_stubbed_response(app_clean: str, page: Page) -> None:
    provider_id = _seed_token_provider(app_clean)
    _stub_network(page)
    _open_edit(page, app_clean, provider_id)
    page.locator('[data-testid="test-connection-btn"]').click()
    expect(page.locator(".test-result-ok")).to_contain_text("Connected", timeout=5000)


@pytest.mark.browser
def test_provider_row_in_library_list_uses_token_badge(app_clean: str, page: Page) -> None:
    _seed_token_provider(app_clean)
    _nav.goto(page, app_clean, "library")
    row = _lists.list_row(page, "library/providers", "Claude Token")
    expect(row).to_be_visible(timeout=8000)
    expect(row.locator(".badge--anthropic-plan-token")).to_have_count(1)


@pytest.mark.browser
def test_expiry_line_follows_time_zone_change_without_remount(app_clean: str, page: Page) -> None:
    """Squawk 0196: a zone change while the editor is open re-dates the line in place."""
    provider_id = _seed_token_provider(app_clean)
    _stub_network(page)
    _stamp_days_ago(page, provider_id, 200)
    _open_edit(page, app_clean, provider_id)
    line = page.locator('[data-testid="provider-token-expiry"]')
    expect(line).to_be_visible(timeout=8000)
    set_at = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    # Zones 26 hours apart: the calendar day differs whatever the clock reads.
    page.evaluate("() => App.time.setZone('Etc/GMT-14')")
    east = _fmt(page, set_at)
    expect(line).to_contain_text(f"Token added {east}")
    page.evaluate("() => App.time.setZone('Etc/GMT+12')")
    west = _fmt(page, set_at)
    assert east != west
    expect(line).to_contain_text(f"Token added {west}")
    expect(line).to_have_attribute("data-state", "ok")

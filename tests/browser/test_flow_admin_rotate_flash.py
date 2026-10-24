"""Browser flow: Settings → Encryption page → rotate key result states.

Covers squawk 0022: `POST /api/encryption/rotate` returns
`{"status": "ok", "key_file": "promoted" | "staged"}`. "staged" means the DB
and in-memory key rotated but the on-disk key file could not be promoted
(the `.next` sidecar stays and reconciles at the next start). The Encryption
page must show a distinct, non-dismissing warning result for "staged" rather
than the ordinary (auto-dismissing) success result — and must keep treating
"promoted" (and any other/missing `key_file`) as success. Since M31 F4 L08b the
result is the `rotate-result` status (its `data-state` is `success`, `warning` or
`danger`), not the retired `.admin-system-flash` classes; the Flight 4 defects
(DD8-10..12) and the status facts are in `test_flow_admin_encryption_page.py`.

Rotate fires through the `App.ui.confirm` two-click helper — the first
click arms (label -> "Rotate key?"), the second commits. The
`/api/encryption/rotate` response is mocked via `page.route` so no real key
rotation happens.
"""

from __future__ import annotations

import re

import pytest
from browser import _nav
from playwright.sync_api import Page, expect


def _mock_rotate_response(page: Page, key_file: str) -> None:
    page.route(
        "**/api/encryption/rotate",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"status": "ok", "key_file": "%s"}' % key_file,
        ),
    )


def _arm_and_commit_rotate(page: Page) -> None:
    rotate_btn = page.locator('[data-testid="rotate-key-btn"]')
    expect(rotate_btn).to_be_visible(timeout=8000)
    # First click arms via App.confirmDelete.
    rotate_btn.click()
    expect(rotate_btn).to_have_text(re.compile(r"Rotate key\?", re.IGNORECASE))
    # Second click commits — fires the (mocked) POST.
    rotate_btn.click()


@pytest.mark.browser
def test_rotate_staged_shows_warning_flash(app_clean: str, page: Page) -> None:
    """`key_file: "staged"` renders a distinct warning flash, not success."""
    _mock_rotate_response(page, "staged")

    _nav.goto(page, app_clean, "settings/encryption")
    _arm_and_commit_rotate(page)

    flash = page.locator('[data-testid="rotate-result"]')
    expect(flash).to_have_attribute("data-state", "warning", timeout=5000)
    expect(flash).to_contain_text("staged")
    expect(flash).to_contain_text("Check the server log")
    expect(flash).not_to_contain_text("Key rotated.")

    # The success flash auto-dismisses after 3s; the staged warning must
    # not — give that timer a chance to fire and confirm it's still shown.
    page.wait_for_timeout(3300)
    expect(flash).to_contain_text("staged")
    expect(flash).to_have_attribute("data-state", "warning")


@pytest.mark.browser
def test_rotate_promoted_shows_success_flash(app_clean: str, page: Page) -> None:
    """`key_file: "promoted"` keeps the existing success flash."""
    _mock_rotate_response(page, "promoted")

    _nav.goto(page, app_clean, "settings/encryption")
    _arm_and_commit_rotate(page)

    flash = page.locator('[data-testid="rotate-result"]')
    expect(flash).to_have_attribute("data-state", "success", timeout=5000)
    expect(flash).to_have_text("Key rotated.")


@pytest.mark.browser
def test_rotate_confirm_lapse_is_visually_distinct(app_clean: str, page: Page) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the credential-rotation
    confirm — the highest-consequence confirm in the app (AC-6) — is
    distinguishable on screen from one that was never armed, past the real
    3s `revertMs`, when the operator lets it lapse without a second click
    (no POST fires at all)."""
    rotate_requests: list[str] = []
    page.on(
        "request",
        lambda r: rotate_requests.append(r.url) if "/api/encryption/rotate" in r.url else None,
    )

    _nav.goto(page, app_clean, "settings/encryption")
    rotate_btn = page.locator('[data-testid="rotate-key-btn"]')
    expect(rotate_btn).to_be_visible(timeout=8000)
    expect(rotate_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    rotate_btn.click()
    expect(rotate_btn).to_have_text(re.compile(r"Rotate key\?", re.IGNORECASE))
    expect(rotate_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(rotate_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(rotate_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(rotate_btn).to_contain_text("Rotate encryption key")
    assert rotate_requests == [], "a lapse must never fire the rotate POST"


@pytest.mark.browser
def test_rotate_success_never_carries_the_lapse_cue(app_clean: str, page: Page) -> None:
    """AC-6a: `revert()` has three callers — timer expiry (a true lapse),
    a transport-failure `.catch`, and the Encryption page's (`system-page.js`) SUCCESS
    path, which also calls `revertFn()` (with a comment saying so). Only
    the timer's own callback marks `.confirm-lapsed` (ui/confirm.js's
    `lapse()`) — the shared `revert()` never does. This is exactly the
    scenario AC-6a exists to protect: a successful, COMMITTED rotation
    must never render as "lapsed", which would contradict AC-4 at the
    app's highest-consequence confirm."""
    _mock_rotate_response(page, "promoted")

    _nav.goto(page, app_clean, "settings/encryption")
    _arm_and_commit_rotate(page)

    flash = page.locator('[data-testid="rotate-result"]')
    expect(flash).to_have_attribute("data-state", "success", timeout=5000)

    rotate_btn = page.locator('[data-testid="rotate-key-btn"]')
    expect(rotate_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(rotate_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(rotate_btn).to_contain_text("Rotate encryption key")

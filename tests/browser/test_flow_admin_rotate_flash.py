"""Browser flow: Admin → System page → Rotate Encryption Key flash states.

Covers squawk 0022: `POST /api/encryption/rotate` returns
`{"status": "ok", "key_file": "promoted" | "staged"}`. "staged" means the DB
and in-memory key rotated but the on-disk key file could not be promoted
(the `.next` sidecar stays and reconciles at the next start). The System
page must show a distinct, non-dismissing warning flash for "staged" rather
than the ordinary (auto-dismissing) success flash — and must keep treating
"promoted" (and any other/missing `key_file`) as success.

Rotate fires through the `App.confirmDelete` two-click helper — the first
click arms (label -> "Confirm Rotate?"), the second commits. The
`/api/encryption/rotate` response is mocked via `page.route` so no real key
rotation happens.
"""

from __future__ import annotations

import re

import pytest
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
    expect(rotate_btn).to_have_text(re.compile(r"Confirm Rotate\?", re.IGNORECASE))
    # Second click commits — fires the (mocked) POST.
    rotate_btn.click()


@pytest.mark.browser
def test_rotate_staged_shows_warning_flash(app_clean: str, page: Page) -> None:
    """`key_file: "staged"` renders a distinct warning flash, not success."""
    _mock_rotate_response(page, "staged")

    page.goto(f"{app_clean}#admin/general")
    _arm_and_commit_rotate(page)

    flash = page.locator(".admin-system-flash")
    expect(flash).to_have_class(re.compile(r"\bwarning\b"), timeout=5000)
    expect(flash).to_contain_text("staged")
    expect(flash).to_contain_text("Check the server log")
    expect(flash).not_to_contain_text("rotated successfully")

    # The success flash auto-dismisses after 3s; the staged warning must
    # not — give that timer a chance to fire and confirm it's still shown.
    page.wait_for_timeout(3300)
    expect(flash).to_contain_text("staged")
    expect(flash).to_have_class(re.compile(r"\bwarning\b"))


@pytest.mark.browser
def test_rotate_promoted_shows_success_flash(app_clean: str, page: Page) -> None:
    """`key_file: "promoted"` keeps the existing success flash."""
    _mock_rotate_response(page, "promoted")

    page.goto(f"{app_clean}#admin/general")
    _arm_and_commit_rotate(page)

    flash = page.locator(".admin-system-flash")
    expect(flash).to_have_class(re.compile(r"\bsuccess\b"), timeout=5000)
    expect(flash).to_have_text("Encryption key rotated successfully.")

"""Focus after an in-place provider or tool action (M25 F6 L1b, flight DD2).

Keyboard-driven (focus on the button, then Enter): a Save or edit-mode Cancel
leaves focus on the editor's `.editor-title`; a Create lands on the new editor's
title; a Test returns focus to its own button once it re-enables; a failed Save
keeps it on Save; and a held Save never steals focus the user moved elsewhere.
"""

from __future__ import annotations

import json

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

TITLE = ".settings-item .editor-title"


def _press(page: Page, testid: str) -> None:
    btn = page.locator(f'[data-testid="{testid}"]')
    expect(btn).to_be_enabled()
    btn.focus()
    page.keyboard.press("Enter")


def _open_provider(app: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app.base_url, f"settings/providers/{_nav.seg(app.provider_id)}")
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_visible(timeout=8000)


def test_provider_save_leaves_focus_on_the_title(app_with_provider: SeededApp, page: Page) -> None:
    _open_provider(app_with_provider, page)
    page.locator("#pf-name").fill("renamed-provider")
    _press(page, "save-provider-btn")
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_have_text("renamed-provider")
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_provider_cancel_leaves_focus_on_the_title(
    app_with_provider: SeededApp, page: Page
) -> None:
    _open_provider(app_with_provider, page)
    page.locator("#pf-name").fill("to-be-reverted")
    _press(page, "cancel-provider-btn")
    expect(page.locator('[data-testid="cancel-provider-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_provider_create_leaves_focus_on_the_new_title(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/providers/~new")
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    page.locator("#pf-type").select_option("ollama")
    page.locator("#pf-name").fill("created-provider")
    page.locator("#pf-base-url").fill("http://127.0.0.1:11434")
    _press(page, "save-provider-btn")
    expect(page.locator(TITLE)).to_have_text("created-provider", timeout=8000)
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)


def test_provider_test_returns_focus_to_its_button(
    app_with_provider: SeededApp, page: Page
) -> None:
    _open_provider(app_with_provider, page)
    page.route(
        "**/api/providers/*/test",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "ok", "detail": "Connected"}),
        ),
    )
    btn = page.locator('[data-testid="test-connection-btn"]')
    btn.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".test-result-ok")).to_be_visible(timeout=8000)
    expect(btn).to_be_enabled()
    expect(btn).to_be_focused(timeout=8000)


def test_provider_failed_save_keeps_focus_on_save(app_with_provider: SeededApp, page: Page) -> None:
    _open_provider(app_with_provider, page)
    page.locator("#pf-name").fill("will-fail")
    page.route(
        "**/api/providers/*",
        lambda route: (
            route.fulfill(
                status=422,
                content_type="application/json",
                body=json.dumps({"detail": [{"loc": ["body", "name"], "msg": "nope"}]}),
            )
            if route.request.method == "PUT"
            else route.fallback()
        ),
    )
    _press(page, "save-provider-btn")
    expect(page.locator(".editor-error")).to_contain_text("nope", timeout=8000)
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_enabled()
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_focused(timeout=8000)


def test_provider_save_never_steals_focus_the_user_moved(
    app_with_provider: SeededApp, page: Page
) -> None:
    _open_provider(app_with_provider, page)
    page.locator("#pf-name").fill("held-save")
    held: list = []
    page.route(
        "**/api/providers/*",
        lambda route: held.append(route) if route.request.method == "PUT" else route.fallback(),
    )
    _press(page, "save-provider-btn")
    page.wait_for_timeout(300)
    assert held, "the PUT was not held"
    page.locator("#pf-name").focus()
    held[0].continue_()
    page.wait_for_timeout(800)
    expect(page.locator("#pf-name")).to_be_focused()
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled()


def test_tool_save_cancel_and_test(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/tools/web_search")
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_visible(timeout=8000)
    # Cancel
    page.locator('[data-field="search_backend"]').select_option("searxng")
    _press(page, "cancel-tool-btn")
    expect(page.locator('[data-testid="cancel-tool-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    # Save
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('input[data-field="searxng_base_url"]').fill("https://searx.example.org")
    _press(page, "save-tool-btn")
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    # Test
    page.route(
        "**/api/tools/configs/web_search/test",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "output": "fine", "duration_ms": 1}),
        ),
    )
    btn = page.locator('[data-testid="test-tool-btn"]')
    btn.focus()
    page.keyboard.press("Enter")
    expect(btn).to_be_enabled(timeout=8000)
    expect(btn).to_be_focused(timeout=8000)
    _lists.close_item(page)

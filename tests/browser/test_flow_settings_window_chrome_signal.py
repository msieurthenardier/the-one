"""The page-to-shell theme signal (M25 F5 L2): ``theme.js`` posts the resolved
theme to ``POST /api/window/chrome`` inside the desktop webview only.

POSTs are intercepted with ``page.route`` (bodies recorded, 200 fulfilled; a
500 for the retry case), so no real shell is involved. The desktop gate is
``window.chrome.webview`` (stubbed at document start by an init script, as
WebView2 has it) or ``window.pywebview`` (injected after load, then
``pywebviewready``). The harness context pins ``color_scheme="no-preference"``,
which Chromium resolves as light, so Auto resolves to light here.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from browser import _nav
from playwright.sync_api import Page, expect

_STUB_WEBVIEW = "window.chrome = window.chrome || {}; window.chrome.webview = {};"


def _record(page: Page, status: int = 200) -> list[Any]:
    bodies: list[Any] = []

    def handler(route: Any, request: Any) -> None:
        if request.method != "POST":
            route.continue_()
            return
        bodies.append(json.loads(request.post_data or "{}"))
        if status == 200:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"theme": bodies[-1].get("theme"), "desktop": True, "tinted": True}
                ),
            )
        else:
            route.fulfill(status=status, content_type="application/json", body="{}")

    page.route("**/api/window/chrome", handler)
    return bodies


def _pref(page: Page, pref: str) -> None:
    page.locator(f'.admin-theme-option[data-theme-pref="{pref}"]').click()


def _wait_count(page: Page, bodies: list[Any], n: int, timeout: float = 5.0) -> None:
    # page.wait_for_timeout pumps Playwright's events (route handlers); time.sleep would not.
    end = time.monotonic() + timeout
    while time.monotonic() < end and len(bodies) < n:
        page.wait_for_timeout(50)
    assert len(bodies) == n, bodies


@pytest.mark.browser
def test_webview_posts_once_per_resolved_theme_change(app_clean: str, page: Page) -> None:
    page.add_init_script(_STUB_WEBVIEW)
    bodies = _record(page)
    _nav.goto(page, app_clean, "settings/appearance")
    expect(page.locator('.admin-theme-option[data-theme-pref="auto"]')).to_be_visible()

    _wait_count(page, bodies, 1)
    assert bodies == [{"theme": "light"}]  # Auto, emulated no-preference -> light

    _pref(page, "light")  # resolved theme unchanged: no post
    page.wait_for_timeout(400)
    assert len(bodies) == 1

    _pref(page, "dark")
    _wait_count(page, bodies, 2)
    assert bodies[-1] == {"theme": "dark"}

    _pref(page, "light")
    _wait_count(page, bodies, 3)
    assert bodies[-1] == {"theme": "light"}

    page.emulate_media(color_scheme="light")
    _pref(page, "auto")  # Auto resolves to the same light: no post
    page.wait_for_timeout(400)
    assert len(bodies) == 3


@pytest.mark.browser
def test_rapid_changes_coalesce_to_the_latest(app_clean: str, page: Page) -> None:
    page.add_init_script(_STUB_WEBVIEW)
    bodies = _record(page)
    _nav.goto(page, app_clean, "settings/appearance")
    _wait_count(page, bodies, 1)

    page.evaluate(
        "() => { ['dark','light','dark','light'].forEach(function (p) { App.theme.set(p); }); }"
    )
    page.wait_for_timeout(800)
    # At most one in flight plus one coalesced follow-up, and the last body is final.
    assert 2 <= len(bodies) <= 3, bodies
    assert bodies[-1] == {"theme": "light"}


@pytest.mark.browser
def test_pywebview_injected_after_load_posts_on_ready(app_clean: str, page: Page) -> None:
    bodies = _record(page)
    _nav.goto(page, app_clean, "settings/appearance")
    expect(page.locator('.admin-theme-option[data-theme-pref="auto"]')).to_be_visible()
    page.wait_for_timeout(300)
    assert bodies == []  # no gate yet

    page.evaluate(
        "() => { window.pywebview = {}; window.dispatchEvent(new Event('pywebviewready')); }"
    )
    _wait_count(page, bodies, 1)
    assert bodies == [{"theme": "light"}]
    page.wait_for_timeout(300)
    assert len(bodies) == 1


@pytest.mark.browser
def test_plain_browser_never_posts(app_clean: str, page: Page) -> None:
    bodies = _record(page)
    _nav.goto(page, app_clean, "settings/appearance")
    expect(page.locator('.admin-theme-option[data-theme-pref="auto"]')).to_be_visible()
    _pref(page, "dark")
    _pref(page, "light")
    _pref(page, "auto")
    page.wait_for_timeout(600)
    assert bodies == []


@pytest.mark.browser
def test_failed_post_is_retried_exactly_once(app_clean: str, page: Page) -> None:
    page.add_init_script(_STUB_WEBVIEW)
    bodies = _record(page, status=500)
    _nav.goto(page, app_clean, "settings/appearance")
    # The first post fails; its one retry comes on the next apply() or after 2s.
    _wait_count(page, bodies, 2, timeout=6.0)
    page.wait_for_timeout(2800)
    assert len(bodies) == 2, bodies

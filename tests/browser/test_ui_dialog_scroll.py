"""DD8 scroll-lock premise (M25 F1 L2, AC9 g): the shell does not scroll ``body``.

DD8 says no scroll lock is needed under a native modal because the shell never
scrolls the document. Measured here, Chromium only, on the default route with an
empty DB (the getting-started state), at the two widths the flight names. Uses
the app fixtures (not ``engine_page``): it spawns one app.
"""

from __future__ import annotations

import pytest
from browser import _nav
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

VIEWPORTS = [(1024, 768), (1440, 900)]


@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_shell_does_not_scroll_body(
    page: Page, app_clean: str, record_property, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    _nav.goto_root(page, app_clean)
    page.wait_for_function(
        "() => { const m = document.getElementById('main-content');"
        " return !!m && m.children.length > 0; }"
    )
    page.wait_for_load_state("networkidle")
    sizes = page.evaluate(
        "() => ({scrollHeight: document.scrollingElement.scrollHeight,"
        " clientHeight: document.scrollingElement.clientHeight,"
        " hash: location.hash})"
    )
    record_property("viewport", f"{width}x{height}")
    record_property("body_scroll", str(sizes))
    print(f"[body-scroll] {width}x{height} {sizes}")
    assert sizes["scrollHeight"] <= sizes["clientHeight"], (
        f"the shell scrolls the document at {width}x{height}: {sizes}"
    )

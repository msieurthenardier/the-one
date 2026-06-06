"""Regression test: out-of-range chat_history_retention_days surfaces a readable error.

When an operator enters a value outside the valid range (1–365) in the Chat
History Retention input and clicks Save, the .editor-error span must:

- Be non-empty (a message was actually rendered).
- NOT contain the literal string "[object Object]" (the pre-fix symptom of
  passing a Pydantic validation array directly to new Error()).
- Ideally contain a hint about the constraint ("365", "retention", or "less").

The fix routes FastAPI 422 detail arrays through `extractApiError()` in
studio.js, which maps each validation-error object to "<field>: <msg>" and
joins them.  This test catches any regression where the helper is removed or
the error path is bypassed.
"""

from __future__ import annotations

import re

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _wait_editor_ready(page: Page) -> None:
    """Wait for the agent editor (General tab) to be the visible main-panel child.

    Bare `#studio/agents` lands on the tile grid with no agent auto-selected;
    click the first tile to mount the editor, then wait for the General tab to
    be active (handles the async editor-mount race).
    """
    expect(page.locator('.section-nav[aria-label="Agent Studio sections"]')).to_be_visible(
        timeout=8000
    )
    editor_hidden = page.evaluate(
        "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
    )
    if editor_hidden:
        page.locator("button.entity-tile").first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


@pytest.mark.browser
def test_retention_out_of_range_shows_readable_error(app_with_agent: SeededApp, page: Page) -> None:
    """Saving retention=400 renders a human-readable error, not '[object Object]'.

    Steps:
    1. Open the agent editor (General tab).
    2. Set the Chat History Retention input to 400 (above the 365-day max).
    3. Click Save.
    4. Assert the .editor-error span is non-empty and does not equal
       '[object Object]'.
    5. Assert the error message contains a range/field hint (case-insensitive
       match on "365", "retention", or "less").
    """
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    # Set the retention input to an out-of-range value (max is 365).
    retention_input = page.locator('[data-field="chat_history_retention_days"]')
    expect(retention_input).to_be_visible(timeout=5000)
    retention_input.click(click_count=3)
    retention_input.fill("400")

    # Trigger the dirty-state flag so Save becomes enabled (fire an input event).
    retention_input.dispatch_event("input")

    # Enable the Save button (it requires dirty state; filling via Playwright
    # may bypass the JS listener, so also fire 'change' to be safe).
    retention_input.dispatch_event("change")

    # Wait for Save button to be enabled, then click it.
    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).to_be_enabled(timeout=5000)
    save_btn.click()

    # The .editor-error span should now contain a readable message.
    error_span = page.locator(".editor-error")
    expect(error_span).not_to_be_empty(timeout=8000)

    error_text = error_span.inner_text()

    assert error_text != "[object Object]", (
        f"editor-error must not contain the raw coercion artifact '[object Object]'; "
        f"got: {error_text!r}"
    )
    assert re.search(r"365|retention|less", error_text, re.IGNORECASE), (
        f"editor-error should hint at the range constraint; got: {error_text!r}"
    )

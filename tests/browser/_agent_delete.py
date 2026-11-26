"""Browser helper: delete the open agent through its confirmation dialog (sortie 20).

The General tab's Delete agent opens a dialog; Delete there needs the acknowledgement ticked.
"""

from __future__ import annotations

from playwright.sync_api import Page, Response, expect


def open_dialog(page: Page) -> None:
    """Click Delete agent and wait for the dialog (the chat count is read first)."""
    btn = page.locator('[data-testid="delete-agent-btn"]')
    expect(btn).to_be_visible(timeout=8000)
    btn.click()
    expect(page.locator('[data-testid="delete-agent-dialog"]')).to_be_visible(timeout=8000)


def confirm_delete(page: Page, *, dialog_open: bool = False) -> Response:
    """Tick the acknowledgement and press Delete; returns the agent DELETE response."""
    if not dialog_open:
        open_dialog(page)
    page.locator('[data-testid="delete-agent-ack-checkbox"]').check()
    confirm = page.locator('[data-testid="delete-agent-confirm-btn"]')
    expect(confirm).to_be_enabled()
    with page.expect_response(
        lambda r: "/api/agents/" in r.url and r.request.method == "DELETE"
    ) as resp:
        confirm.click()
    return resp.value

"""Rules and notes tab survives a General Save untouched (M31 F2 L09, DD6).

The tab saves immediately and keys only on the agent's name, so it declares no
``setAgent`` and the editor's same-identity patch leaves it alone: unsaved Add-rule
text and Add-note state stay, and a General Save makes no extra rules or notes read.
Falls in the ``agents`` lane via the ``test_flow_agent_*`` glob.
"""

from __future__ import annotations

import pytest
from browser import _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def test_general_save_leaves_unsaved_add_rule_text_and_makes_no_extra_reads(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name or ""
    reads: list[str] = []

    def on_request(req) -> None:  # noqa: ANN001
        url = req.url.split("?")[0]
        if req.method == "GET" and (url.endswith("/rules") or url.endswith("/notes")):
            reads.append(url)

    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/rules-and-notes")
    expect(page.locator('[data-testid="rules-add-input"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="rules-empty"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="notes-empty"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="rules-add-input"]').fill("Unsaved rule text")

    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("A new description")
    page.on("request", on_request)
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden(timeout=8000)
    page.wait_for_timeout(500)
    page.remove_listener("request", on_request)

    page.locator('[data-testid="tab-rules-and-notes"]').click()
    expect(page.locator('[data-testid="rules-add-input"]')).to_have_value("Unsaved rule text")
    expect(page.locator('[data-testid="rules-add-btn"]')).to_be_enabled()
    assert reads == [], reads

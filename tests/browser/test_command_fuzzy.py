"""L8 — command-fuzzy.js scorer. Executed via Playwright page.evaluate
because the module is plain JS with no Node entry point — running it in
the browser is the cheapest accurate way to test it.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_command_fuzzy_scoring(app_clean: str, page: Page) -> None:
    page.goto(app_clean)

    # Sanity: the module is loaded.
    has_module = page.evaluate("() => !!(window.App && window.App.commandFuzzy)")
    assert has_module, "App.commandFuzzy not loaded — check index.html script order"

    score = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "prov", "label": "Open Providers"},
    )
    assert score >= 100, f"prefix-after-space should beat substring: {score}"

    score_sub = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "agent", "label": "Switch to agent: research"},
    )
    assert score_sub >= 50

    score_miss = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "xyzzy", "label": "Open Providers"},
    )
    assert score_miss == 0

    # Case-insensitivity.
    score_upper = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "PROV", "label": "Open Providers"},
    )
    assert score_upper >= 100

    # Missing fields don't throw.
    score_empty = page.evaluate(
        "() => window.App.commandFuzzy.score('foo', {})"
    )
    assert score_empty == 0

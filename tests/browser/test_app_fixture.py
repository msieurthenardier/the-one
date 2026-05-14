"""Sanity tests for the app_clean / browser / page fixtures from conftest.py."""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_app_clean_serves_index(app_clean: str, page: Page) -> None:
    """The app_clean fixture spawns a working app that serves the index page."""
    page.goto(app_clean)
    # Title is set by the index template; should mention the project name.
    title = page.title()
    # Brand wordmark "GleepGlorp AI" is intentionally retained per design spec §"Brand mark"
    # (Mission 09 Holograph migration kept the GleepGlorp wordmark in the topnav; only the design language was rebranded).
    assert "gleepglorp" in title.lower(), (
        f"Expected page title to contain 'gleepglorp', got: {title!r}"
    )


@pytest.mark.browser
def test_app_clean_responds_to_api_info(app_clean: str) -> None:
    """The app_clean fixture's subprocess responds to /api/info — confirms
    the wait-for-ready loop works end-to-end and the subprocess is fully booted
    (lifespan handler completed: init_db, migrate_json_to_sqlite, AgentFactory).
    """
    r = httpx.get(f"{app_clean}/api/info", timeout=2.0)
    assert r.status_code == 200
    assert "version" in r.json()

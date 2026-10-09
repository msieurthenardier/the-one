"""Sanity tests for the app_clean / browser / page fixtures from conftest.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page

from tests._schema_template import template_path


@pytest.mark.browser
def test_app_clean_serves_index(app_clean: str, page: Page) -> None:
    """The app_clean fixture spawns a working app that serves the index page."""
    page.goto(app_clean)
    # Title is set by the index template; should mention the project name.
    title = page.title()
    assert "gleepglorp" in title.lower(), (
        f"Expected page title to contain 'gleepglorp', got: {title!r}"
    )


@pytest.mark.browser
def test_app_clean_responds_to_api_info(app_clean: str) -> None:
    """The app_clean fixture's subprocess responds to /api/info — confirms
    the wait-for-ready loop works end-to-end and the subprocess is fully booted
    (lifespan handler completed: init_db, migrate_json_to_sqlite, AgentFactory).
    """
    r = httpx.get(f"{app_clean}/api/info", timeout=2.0, headers=auth_headers_for(app_clean))
    assert r.status_code == 200
    assert "version" in r.json()


@pytest.mark.browser
def test_seeded_server_does_not_replay_migrations(app_with_data_dir: tuple[str, Path]) -> None:
    """A server booted on the template copy finds the schema current: the
    ``schema_version`` rows are exactly the template's (a replay would add rows
    or change ``applied_at``)."""
    _base_url, data_dir = app_with_data_dir
    query = "SELECT version, applied_at FROM schema_version ORDER BY version"
    tpl = sqlite3.connect(f"file:{template_path()}?mode=ro", uri=True)
    try:
        expected = tpl.execute(query).fetchall()
    finally:
        tpl.close()
    live = sqlite3.connect(f"file:{data_dir / 'the-one.db'}?mode=ro", uri=True)
    try:
        actual = live.execute(query).fetchall()
    finally:
        live.close()
    assert expected, "template has no schema_version rows"
    assert actual == expected

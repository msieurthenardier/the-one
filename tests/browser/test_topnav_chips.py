"""Tests that the topnav chip strip reflects live API counts."""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_topnav_chips_load_real_counts_after_boot(app_clean: str, page: Page) -> None:
    """After page load + a refresh tick, chips show numeric values from
    the API — not the em-dash placeholders."""
    page.goto(app_clean)
    # Add a provider via API so PROVIDERS chip will read 1.
    # NOTE: ``base_url`` is required by ``LLMProviderConfig`` (no default);
    # the empty-string convention mirrors ``tests/browser/seeders.py``
    # ``seed_mock_provider``. Mock type works because ``app_clean`` spawns
    # with ``THE_ONE_DEV_MODE=true`` per ``conftest.py``.
    resp = httpx.post(
        f"{app_clean}/api/providers",
        json={"name": "test", "type": "mock", "base_url": "", "config": {}},
        timeout=2.0,
    )
    assert resp.status_code == 201, f"provider POST failed: {resp.status_code} {resp.text}"
    # Switch to System area where PROVIDERS chip is shown.
    page.goto(f"{app_clean}#admin")
    # The telemetry-refresh utility should fire on area mount.
    page.wait_for_timeout(800)
    chip = page.locator('.tele-chip:has-text("PROVIDERS")')
    expect(chip.locator("strong")).to_have_text("1", timeout=5000)

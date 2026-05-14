"""Unit tests for the in-memory telemetry store.

The store is a plain ES-module-on-window observable; we exercise it
inside a Playwright page context to avoid Node.js setup.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_telemetry_store_initial_state_is_em_dash(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    state = page.evaluate("window.TelemetryStore.get()")
    assert state["sessions"] == "—"
    assert state["agents"] == "—"
    assert state["providers"] == "—"
    assert state["tools"] == "—"
    assert state["ctx"] == "—"
    assert state["ws_rtt_ms"] == "—"
    assert state["ws_state"] == "down"


@pytest.mark.browser
def test_telemetry_store_set_emits_change(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const calls = [];
          window.TelemetryStore.subscribe((s) => calls.push({ ...s }));
          window.TelemetryStore.set({ sessions: 3, agents: 1 });
          return calls;
        }"""
    )
    assert len(result) >= 1
    last = result[-1]
    assert last["sessions"] == 3
    assert last["agents"] == 1


@pytest.mark.browser
def test_telemetry_store_unsubscribe_stops_emissions(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const calls = [];
          const off = window.TelemetryStore.subscribe((s) => calls.push({ ...s }));
          window.TelemetryStore.set({ sessions: 1 });
          off();
          window.TelemetryStore.set({ sessions: 99 });
          return calls.length;
        }"""
    )
    assert result == 1

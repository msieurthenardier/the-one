"""M16 F06 L03 — Playwright browser flow: overlay restores after session reopen.

Proves that after a turn whose provider emits non-zero input_tokens:
  1. The telemetry overlay populates live (`.t-ctx` / `.t-in` show non-zero).
  2. After page.reload() (re-fires session_joined), the overlay restores the
     persisted values — `.t-in` and `.t-ctx` show the same non-zero values,
     and `.context-bar` has a computed width > 0.

DOM-shape / computed-style assertions only — NO committed visual snapshots.
tests/browser/__snapshots__/ is gitignored and no baseline images are added.

Reopen caveat (documented here to explain the test's coverage):
  page.reload() keeps the uvicorn subprocess alive, so the rejoin hits the
  warm-cache branch (app.py:949-968) rather than the fresh-Session DB-reload
  branch.  However, the warm-cache branch still does:
      existing.session_metadata = db_session.session_metadata   (app.py:966)
  which refreshes the snapshot from the DB row, so the frontend restore IS
  genuinely exercised end-to-end (it reads from DB, not a stale in-memory
  value).  The genuine cross-restart DB-reload path (fresh Session construction,
  app.py:970-986) is what the in-process integration test
  (tests/test_last_usage_round_trip.py) covers by popping _sessions.
  Together they cover both halves; neither alone is sufficient.
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

# Token count seeded into the mock provider.  Must be > 0 so the turn
# clears L01's `if last_input:` guard.  Large enough to be obviously
# non-zero; small enough to be recognisable in debug output.
_INPUT_TOKENS = 850


@pytest.mark.browser
def test_overlay_restores_after_session_reopen(app_clean: str, page: Page) -> None:
    """Seed provider with input_tokens=N, drive a turn, reload, assert restored overlay.

    Steps:
      1. Seed a mock provider with config={"input_tokens": _INPUT_TOKENS} (non-streaming
         path — no stream_chunks).  Seed a mock agent on it.
      2. Navigate, pick the agent from the welcome listbox, send a message.
      3. Wait for the overlay to populate (`.t-ctx` non-zero) before reopening —
         the assistant DOM can land before the usage event settles and persists;
         waiting on the overlay itself gates us on a persisted turn.
      4. page.reload() — re-fires session_joined, which restores last_usage from DB.
      5. Assert: `.t-in` and `.t-ctx` show non-zero text; `.context-bar` width > 0.
    """
    # ── Seed ─────────────────────────────────────────────────────────────────
    # Non-streaming path: no "stream_chunks" key → a single final usage event
    # (no interim input_tokens=0 events that could race the assertion).
    provider_id = seed_mock_provider(
        app_clean,
        name="usage-restore-provider",
        config={"input_tokens": _INPUT_TOKENS},
    )
    agent_name = seed_mock_agent(
        app_clean,
        provider_id,
        name="usage-restore-agent",
    )

    # ── Bootstrap into chrome ─────────────────────────────────────────────────
    page.goto(app_clean)
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_visible(timeout=8000)

    # Pick the agent from the welcome listbox to start a session.
    agent_item = page.locator(".chat-welcome-item").filter(has_text=agent_name)
    expect(agent_item).to_be_visible(timeout=8000)
    agent_item.click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)

    # ── Send a message ───────────────────────────────────────────────────────
    page.locator('[data-testid="chat-input"]').fill("hello overlay")
    page.locator('[data-testid="chat-send-btn"]').click()

    # Wait for the assistant reply to land (confirms the turn settled).
    expect(page.locator('[data-testid="message"].assistant')).to_be_visible(timeout=10000)

    # ── Wait for the overlay to populate with non-zero context_tokens ────────
    # We must wait on the overlay value, not merely the assistant message DOM.
    # The assistant bubble can arrive before the `usage` event is processed and
    # _persist_last_usage completes.  Reopening too early would race an
    # un-persisted turn and restore zeros instead of N.
    page.wait_for_function(
        "() => { "
        "  var el = document.querySelector('.t-ctx'); "
        "  if (!el) return false; "
        "  var txt = el.textContent.trim(); "
        "  return txt !== '' && txt !== '0' && txt !== '—'; "
        "}",
        timeout=10000,
    )

    # Capture the live values (for assertion parity after reload).
    live_t_ctx = page.locator(".t-ctx").first.text_content() or ""
    live_t_in = page.locator(".t-in").first.text_content() or ""
    assert live_t_ctx.strip() not in ("", "0", "—"), (
        f"Live .t-ctx should be non-zero before reload, got {live_t_ctx!r}"
    )
    assert live_t_in.strip() not in ("", "0", "—"), (
        f"Live .t-in should be non-zero before reload, got {live_t_in!r}"
    )

    # ── Reopen: reload the page so session_joined re-fires ──────────────────
    # Note: the subprocess stays up, so the rejoin hits the warm-cache branch
    # (app.py:949-968) which refreshes session_metadata from the DB row
    # (app.py:966) before building the payload.  This exercises the DB-backed
    # frontend restore path even though the Session object is not re-created.
    page.reload()

    # Wait for chrome to reappear after reload (session_joined re-fires).
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=10000)

    # ── Assert overlay is restored ───────────────────────────────────────────
    # Wait for the overlay to have non-zero values after the reload/rejoin.
    page.wait_for_function(
        "() => { "
        "  var el = document.querySelector('.t-ctx'); "
        "  if (!el) return false; "
        "  var txt = el.textContent.trim(); "
        "  return txt !== '' && txt !== '0' && txt !== '—'; "
        "}",
        timeout=10000,
    )

    restored_t_ctx = page.locator(".t-ctx").first.text_content() or ""
    restored_t_in = page.locator(".t-in").first.text_content() or ""
    assert restored_t_ctx.strip() not in ("", "0", "—"), (
        f"Restored .t-ctx should be non-zero, got {restored_t_ctx!r}"
    )
    assert restored_t_in.strip() not in ("", "0", "—"), (
        f"Restored .t-in should be non-zero, got {restored_t_in!r}"
    )

    # The restored values must match what was shown before the reload
    # (confirming the overlay reflects the persisted snapshot, not fresh zeros).
    assert restored_t_ctx.strip() == live_t_ctx.strip(), (
        f"Restored .t-ctx {restored_t_ctx!r} does not match pre-reload {live_t_ctx!r}"
    )
    assert restored_t_in.strip() == live_t_in.strip(), (
        f"Restored .t-in {restored_t_in!r} does not match pre-reload {live_t_in!r}"
    )

    # Assert the context-bar has a positive inline width (set by setTelemetryMax
    # after the /api/agents/{name}/context-window async fetch resolves).
    # The bar's width is set as an inline style (bar.style.width = pct + '%'),
    # so we wait for it to become non-zero before reading it.
    # getComputedStyle(.context-bar).width can be '0px' until setTelemetryMax
    # fires; wait_for_function gates us on the actual fill.
    page.wait_for_function(
        "() => { "
        "  var bar = document.querySelector('.context-bar'); "
        "  if (!bar) return false; "
        "  var w = parseFloat(bar.style.width || '0'); "
        "  return w > 0; "
        "}",
        timeout=10000,
    )
    context_bar_inline_width = page.evaluate(
        "() => { "
        "  var bar = document.querySelector('.context-bar'); "
        "  return bar ? (bar.style.width || '0%') : '0%'; "
        "}"
    )
    inline_pct = float((context_bar_inline_width or "0%").replace("%", "") or "0")
    assert inline_pct > 0, (
        f".context-bar inline width should be > 0% after restore, got {context_bar_inline_width!r}"
    )

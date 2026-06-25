"""M16 F08 L05 — Playwright browser flow: context-fullness overlay thresholds
are config-driven and carry a non-color a11y signal.

Proves (DOM / role / aria assertions only — NO pixel snapshots):
  1. Driving the telemetry overlay (via the exposed ``window.App.chat`` update
     paths) to ≥ warn and ≥ crit applies the existing ``.warn`` / ``.crit``
     coloring classes to ``.context-bar`` and ``.t-ctx-pct`` (verify-and-keep
     the coloring — it already shipped).
  2. At those states the overlay container's ``aria-label`` gains the
     non-color state phrase ("approaching limit" / "context nearly full")
     while KEEPING the "Token usage" prefix — a screen-reader-perceivable
     signal that does not depend on color.
  3. A custom env threshold (``THE_ONE_CONTEXT_WARN_PCT=50``) MOVES the
     transition point: 55% now colors+announces warn where it would have been
     neutral under the 70 default.

The overlay update functions (``updateTelemetry`` / ``setTelemetryMax``) are
exposed on ``window.App.chat`` and query the overlay by class under whichever
container they are handed, so we can drive them deterministically with
synthetic token counts via ``page.evaluate`` — no live LLM turn or specific
real context fill is needed to land on an exact percentage.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from browser.conftest import _spawn_app, _teardown_proc
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _enter_session(page: Page, base_url: str) -> str:
    """Seed a mock provider + agent, navigate, and click into a session so the
    chat chrome (and the telemetry overlay inside it) is mounted. Returns the
    agent name.

    Waits for the join-time ``/context-window`` fetch to settle before
    returning. That fetch fires ``setTelemetryMax(content, max)`` asynchronously
    on join (chat.js); if a test drove the overlay before it resolved, the late
    callback would recompute pct from the (zero) retained context_tokens and
    clobber the driven state. Gating on the response makes the drive
    deterministic — nothing else auto-mutates the overlay afterward.
    """
    provider_id = seed_mock_provider(base_url, name="ctx-overlay-provider")
    agent_name = seed_mock_agent(base_url, provider_id, name="ctx-overlay-agent")

    page.goto(base_url)
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_visible(timeout=8000)
    agent_item = page.locator(".chat-welcome-item").filter(has_text=agent_name)
    expect(agent_item).to_be_visible(timeout=8000)
    # Capture the join-time context-window fetch so we know when the async
    # setTelemetryMax callback has run before we drive the overlay.
    with page.expect_response(lambda r: "/context-window" in r.url, timeout=10000):
        agent_item.click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)
    # The overlay is mounted inside .chat-chrome once a session is open.
    expect(page.locator(".telemetry-overlay")).to_have_count(1, timeout=8000)
    return agent_name


def _drive_overlay(page: Page, context_tokens: int, max_context_tokens: int) -> None:
    """Drive both overlay update paths to a known percentage via the exposed
    window.App.chat helpers. ``updateTelemetry`` sets the raw values + state;
    ``setTelemetryMax`` recomputes from retained context_tokens (exercising the
    second threshold-derivation site too).

    Drives using the chat AREA content element (``.content-panel.area-chat``) —
    the SAME element the app hands the update functions — so the retained
    ``__telemetry`` state lives on one element and ``setTelemetryMax`` reads back
    the context_tokens this call just set.
    """
    page.evaluate(
        """([ctx, max]) => {
            var root = document.querySelector('.content-panel.area-chat')
                || document.querySelector('.chat-chrome') || document;
            window.App.chat.updateTelemetry(root, {
                input_tokens: ctx,
                output_tokens: 0,
                context_tokens: ctx,
                max_context_tokens: max
            });
            window.App.chat.setTelemetryMax(root, max);
        }""",
        [context_tokens, max_context_tokens],
    )


@pytest.mark.browser
def test_overlay_thresholds_color_and_aria_at_defaults(app_clean: str, page: Page) -> None:
    """Default thresholds (70 / 90): neutral below warn, .warn at ≥70%,
    .crit at ≥90%, and the aria-label carries the matching non-color phrase.
    """
    _enter_session(page, app_clean)

    bar = page.locator(".context-bar")
    pct = page.locator(".t-ctx-pct")
    overlay = page.locator(".telemetry-overlay")

    # ── Neutral: 40% of a 100-token window ───────────────────────────────────
    _drive_overlay(page, 40, 100)
    expect(bar).not_to_have_class(re.compile(r"\bwarn\b"))
    expect(bar).not_to_have_class(re.compile(r"\bcrit\b"))
    expect(pct).to_have_text("40%")
    # aria-label has no state phrase, keeps the "Token usage" prefix.
    label = overlay.get_attribute("aria-label") or ""
    assert label.startswith("Token usage"), label
    assert "approaching limit" not in label and "nearly full" not in label, label

    # ── Warn: 75% ────────────────────────────────────────────────────────────
    _drive_overlay(page, 75, 100)
    expect(bar).to_have_class(re.compile(r"\bwarn\b"))
    expect(bar).not_to_have_class(re.compile(r"\bcrit\b"))
    expect(pct).to_have_class(re.compile(r"\bwarn\b"))
    label = overlay.get_attribute("aria-label") or ""
    assert label.startswith("Token usage"), label
    assert "approaching limit" in label, label

    # ── Crit: 95% ────────────────────────────────────────────────────────────
    _drive_overlay(page, 95, 100)
    expect(bar).to_have_class(re.compile(r"\bcrit\b"))
    expect(pct).to_have_class(re.compile(r"\bcrit\b"))
    label = overlay.get_attribute("aria-label") or ""
    assert label.startswith("Token usage"), label
    assert "nearly full" in label, label


@pytest.mark.browser
def test_overlay_custom_warn_threshold_moves_transition(tmp_path: Path, page: Page) -> None:
    """With ``THE_ONE_CONTEXT_WARN_PCT=50``, 55% colors+announces warn —
    proving the transition point is config-driven, not the hardcoded 70.
    """
    base_url, proc = _spawn_app(
        tmp_path,
        extra_env={"THE_ONE_CONTEXT_WARN_PCT": "50", "THE_ONE_CONTEXT_CRIT_PCT": "90"},
    )
    try:
        # Sanity: the threshold reached the client via /api/config.
        import httpx

        cfg = httpx.get(f"{base_url}/api/config", timeout=5.0).json()
        assert cfg["context_warn_pct"] == 50, cfg

        _enter_session(page, base_url)

        bar = page.locator(".context-bar")
        overlay = page.locator(".telemetry-overlay")

        # 55%: would be neutral under the 70 default; warn under the custom 50.
        _drive_overlay(page, 55, 100)
        expect(bar).to_have_class(re.compile(r"\bwarn\b"))
        label = overlay.get_attribute("aria-label") or ""
        assert "approaching limit" in label, label

        # 45%: still neutral (below the custom warn).
        _drive_overlay(page, 45, 100)
        expect(bar).not_to_have_class(re.compile(r"\bwarn\b"))
        label = overlay.get_attribute("aria-label") or ""
        assert "approaching limit" not in label and "nearly full" not in label, label
    finally:
        _teardown_proc(proc)

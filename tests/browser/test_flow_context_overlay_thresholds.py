"""M16 F08 L05 — Playwright browser flow: context-fullness overlay thresholds
are config-driven and carry a non-color a11y signal.

Proves (DOM / role / aria assertions only — NO pixel snapshots):
  1. Driving the telemetry readout (through the chat area's ``_telemetry()`` handle) to
     ≥ warn and ≥ crit applies the ``--warn`` / ``--crit`` modifier classes to
     ``.ui-telemetry-bar`` and ``.ui-telemetry-pct``.
  2. At those states the overlay container's ``aria-label`` gains the
     non-color state phrase ("approaching limit" / "context nearly full")
     while KEEPING the "Token usage" prefix — a screen-reader-perceivable
     signal that does not depend on color.
  3. A custom env threshold (``THE_ONE_CONTEXT_WARN_PCT=50``) MOVES the
     transition point: 55% now colors+announces warn where it would have been
     neutral under the 70 default.

The handle's ``update`` and ``setMax`` (``App.ui.telemetry``, M31 F6 L05c) take
synthetic token counts via ``page.evaluate``, so no live LLM turn or specific real
context fill is needed to land on an exact percentage.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from browser import _chats
from browser._credential_registry import auth_headers_for
from browser._credential_registry import unregister as _unregister_credential
from browser.conftest import _spawn_app, _teardown_proc
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _enter_session(page: Page, base_url: str) -> str:
    """Seed a mock provider + agent, navigate, start a chat and send its first
    message so a session exists and the chat chrome (and the telemetry overlay
    inside it) is mounted. Returns the agent name.

    Waits for the join-time ``/context-window`` fetch to settle before
    returning. That fetch fires ``setMax(max)`` asynchronously
    on join (socket.js); if a test drove the overlay before it resolved, the late
    callback would recompute pct from the (zero) retained context_tokens and
    clobber the driven state. Gating on the response makes the drive
    deterministic — nothing else auto-mutates the overlay afterward.
    """
    provider_id = seed_mock_provider(base_url, name="ctx-overlay-provider")
    agent_name = seed_mock_agent(base_url, provider_id, name="ctx-overlay-agent")

    page.goto(base_url)
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    # Capture the join-time context-window fetch so we know when the async
    # setTelemetryMax callback has run before we drive the overlay.
    # M25 F4 L3b: a start is a pending chat with no session; the first send
    # creates the session, and its session_joined fires the fetch.
    with page.expect_response(lambda r: "/context-window" in r.url, timeout=10000):
        _chats.start_chat(page, agent_name)
        _chats.send_first(page, "hello")
    # The overlay is mounted inside .chat-chrome once a session is open.
    expect(_chats.telemetry(page)).to_have_count(1, timeout=8000)
    # Let the first turn finish (its usage frame updates the overlay) before
    # a test drives it.
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    return agent_name


def _drive_overlay(page: Page, context_tokens: int, max_context_tokens: int) -> None:
    """Drive both readout update paths to a known percentage through the chat area's telemetry
    handle (``_telemetry()``, an ``App.ui.telemetry``). ``update`` sets the raw values and
    state; ``setMax`` recomputes from the retained context_tokens (exercising the second
    threshold-derivation site too)."""
    page.evaluate(
        """([ctx, max]) => {
            const t = window.App.areas.find(a => a.id === 'chat')._telemetry();
            t.update({
                input_tokens: ctx,
                output_tokens: 0,
                context_tokens: ctx,
                max_context_tokens: max
            });
            t.setMax(max);
        }""",
        [context_tokens, max_context_tokens],
    )


@pytest.mark.browser
def test_overlay_thresholds_color_and_aria_at_defaults(app_clean: str, page: Page) -> None:
    """Default thresholds (70 / 90): neutral below warn, .warn at ≥70%,
    .crit at ≥90%, and the aria-label carries the matching non-color phrase.
    """
    _enter_session(page, app_clean)

    bar = page.locator(".ui-telemetry-bar")
    pct = page.locator(".ui-telemetry-pct")
    overlay = _chats.telemetry(page)

    # ── Neutral: 40% of a 100-token window ───────────────────────────────────
    _drive_overlay(page, 40, 100)
    expect(bar).not_to_have_class(re.compile(r"\bui-telemetry-bar--warn\b"))
    expect(bar).not_to_have_class(re.compile(r"\bui-telemetry-bar--crit\b"))
    expect(pct).to_have_text("40%")
    # aria-label has no state phrase, keeps the "Token usage" prefix.
    label = overlay.get_attribute("aria-label") or ""
    assert label.startswith("Token usage"), label
    assert "approaching limit" not in label and "nearly full" not in label, label

    # ── Warn: 75% ────────────────────────────────────────────────────────────
    _drive_overlay(page, 75, 100)
    expect(bar).to_have_class(re.compile(r"\bui-telemetry-bar--warn\b"))
    expect(bar).not_to_have_class(re.compile(r"\bui-telemetry-bar--crit\b"))
    expect(pct).to_have_class(re.compile(r"\bui-telemetry-pct--warn\b"))
    label = overlay.get_attribute("aria-label") or ""
    assert label.startswith("Token usage"), label
    assert "approaching limit" in label, label

    # ── Crit: 95% ────────────────────────────────────────────────────────────
    _drive_overlay(page, 95, 100)
    expect(bar).to_have_class(re.compile(r"\bui-telemetry-bar--crit\b"))
    expect(pct).to_have_class(re.compile(r"\bui-telemetry-pct--crit\b"))
    label = overlay.get_attribute("aria-label") or ""
    assert label.startswith("Token usage"), label
    assert "nearly full" in label, label


@pytest.mark.browser
def test_overlay_custom_warn_threshold_moves_transition(tmp_path: Path, page: Page) -> None:
    """With ``THE_ONE_CONTEXT_WARN_PCT=50``, 55% colors+announces warn —
    proving the transition point is config-driven, not the hardcoded 70.
    """
    base_url, proc, _credential, _data_dir = _spawn_app(
        tmp_path,
        extra_env={"THE_ONE_CONTEXT_WARN_PCT": "50", "THE_ONE_CONTEXT_CRIT_PCT": "90"},
    )
    try:
        # Sanity: the threshold reached the client via /api/config.
        import httpx

        cfg = httpx.get(
            f"{base_url}/api/config", timeout=5.0, headers=auth_headers_for(base_url)
        ).json()
        assert cfg["context_warn_pct"] == 50, cfg

        _enter_session(page, base_url)

        bar = page.locator(".ui-telemetry-bar")
        overlay = _chats.telemetry(page)

        # 55%: would be neutral under the 70 default; warn under the custom 50.
        _drive_overlay(page, 55, 100)
        expect(bar).to_have_class(re.compile(r"\bui-telemetry-bar--warn\b"))
        label = overlay.get_attribute("aria-label") or ""
        assert "approaching limit" in label, label

        # 45%: still neutral (below the custom warn).
        _drive_overlay(page, 45, 100)
        expect(bar).not_to_have_class(re.compile(r"\bui-telemetry-bar--warn\b"))
        label = overlay.get_attribute("aria-label") or ""
        assert "approaching limit" not in label and "nearly full" not in label, label
    finally:
        _unregister_credential(base_url)
        _teardown_proc(proc)

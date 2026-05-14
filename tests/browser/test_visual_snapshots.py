"""Visual regression snapshots for the F2 design language.

Captures 12 baseline PNGs (3 areas × 2 states × 2 themes) so subsequent
flights (F3-F6) can detect unintended visual regressions when redesigning
or refactoring the UI.

Why a hand-rolled helper rather than ``expect(page).to_have_screenshot``:
the JavaScript-Playwright assertion ``to_have_screenshot`` is not part of
the Python ``playwright.sync_api`` (see playwright-python issues #1454,
the assertion exists in the JS test runner but not the Python bindings).
We implement an equivalent locally using PIL + pixelmatch:

- ``Page.screenshot()`` captures the current viewport as a PNG byte
  string.
- ``pixelmatch.contrib.PIL.pixelmatch`` computes per-pixel diffs with a
  configurable anti-aliasing-aware threshold, matching the JS API's
  ``maxDiffPixelRatio`` semantics.
- Baselines live in ``tests/browser/__snapshots__/`` (the directory is
  the same pattern Playwright JS uses).  **Baselines are gitignored —
  local-only regression artifacts, not shared source.**  Each developer
  regenerates locally; CI never runs pixel comparison (these tests are
  marked ``pixel`` rather than ``browser`` so the standard ``-m browser``
  collection skips them).
- Update mode is opt-in via ``UPDATE_SNAPSHOTS=1`` env var or
  ``--snapshot-update`` CLI flag (parsed in ``conftest.py``).  When a
  baseline is missing, the helper auto-generates it on first run so a
  fresh checkout becomes useful immediately; subsequent runs compare.

Snapshot tolerance: ``DIFF_RATIO`` = 2% pixel diff.  Generous enough to
absorb anti-aliasing variance across runs without missing real
regressions.  Bump to 3% (max 5%) if observed flakiness across 3
consecutive runs; never above that without re-thinking the helper.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import pytest

# PIL + pixelmatch are dev-only deps; the pixel suite runs locally during
# UI work and is excluded from CI (see `agents.md` → Pytest markers). Use
# `importorskip` so a venv without these libs can still collect (and run)
# the rest of the browser suite.
Image = pytest.importorskip("PIL.Image")
pixelmatch = pytest.importorskip("pixelmatch.contrib.PIL").pixelmatch

from browser.seeders import SeededApp  # noqa: E402
from playwright.sync_api import Page, expect  # noqa: E402

# ── Snapshot config ───────────────────────────────────────────────────────

VIEWPORT = {"width": 1280, "height": 800}
SNAPSHOT_DIR = Path(__file__).parent / "__snapshots__"
DIFF_RATIO = 0.02  # 2% pixel diff tolerance — anti-aliasing absorber
PIXELMATCH_THRESHOLD = 0.2  # per-pixel YIQ threshold; 0.1 is strict, 0.3 lax


def _update_mode() -> bool:
    """Whether the current run regenerates baselines.

    Triggered by either ``UPDATE_SNAPSHOTS=1`` env var (handy for ad-hoc
    regeneration) or ``--snapshot-update`` CLI flag (parsed in
    conftest.py).  Without this gate, a missing baseline always fails;
    with it, missing baselines are written and existing ones are
    overwritten.
    """
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        return True
    # The conftest hook stores the parsed flag under this attribute on
    # the pytest config object via a session-scoped fixture; here we
    # check the env var bridge it sets.
    return os.environ.get("_PYTEST_SNAPSHOT_UPDATE") == "1"


def _wait_for_render(page: Page) -> None:
    """Wait for fonts loaded + 1 animation frame to stabilise render.

    ``document.fonts.ready`` resolves when all CSS-declared fonts (Geist
    + Geist Mono in our case) are loaded and ready to paint.  Without
    this, the first run might capture fallback fonts and subsequent
    runs would diff against the Geist-loaded baseline.

    The ``requestAnimationFrame`` chain ensures we capture AFTER the
    next paint, so any DOM-mutation triggered re-render has settled.
    """
    page.evaluate("async () => { await document.fonts.ready; }")
    page.evaluate(
        "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r())))"
    )


def _set_theme(page: Page, theme: str) -> None:
    """Set ``App.theme.set(theme)`` and wait for the re-render.

    The ``data-theme`` attribute is applied synchronously inside
    ``set()``, but stylesheet recomputation + paint happens on the next
    frame.  ``_wait_for_render`` covers both font-load and paint
    stability.
    """
    page.evaluate(f"App.theme.set('{theme}')")
    # Sanity assertion: the resolved theme matches what we set (auto
    # would resolve differently — we're explicit here).
    page.wait_for_function(f"App.theme.resolved() === '{theme}'", timeout=5000)
    _wait_for_render(page)


def _assert_screenshot(page: Page, name: str) -> None:
    """Capture the current viewport and compare against baseline.

    First run (or when ``_update_mode()`` is True) writes the baseline.
    Subsequent runs compare; failure attaches an actual + diff image
    next to the baseline for inspection.
    """
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    baseline_path = SNAPSHOT_DIR / f"{name}.png"

    actual_bytes = page.screenshot(full_page=False, animations="disabled")
    actual_img = Image.open(BytesIO(actual_bytes)).convert("RGBA")

    if _update_mode() or not baseline_path.exists():
        actual_img.save(baseline_path)
        # In update mode we still proceed without an assertion failure
        # so a single ``--snapshot-update`` run regenerates all
        # baselines in one shot.
        return

    baseline_img = Image.open(baseline_path).convert("RGBA")

    # Size guard — if the baseline was generated at a different
    # viewport, fail loudly rather than emitting a confusing diff.
    if baseline_img.size != actual_img.size:
        actual_path = SNAPSHOT_DIR / f"{name}-actual.png"
        actual_img.save(actual_path)
        raise AssertionError(
            f"Snapshot size mismatch for {name}: "
            f"baseline={baseline_img.size}, actual={actual_img.size}. "
            f"Wrote actual to {actual_path}."
        )

    diff_img = Image.new("RGBA", baseline_img.size)
    mismatched_pixels = pixelmatch(
        baseline_img,
        actual_img,
        diff_img,
        threshold=PIXELMATCH_THRESHOLD,
        includeAA=False,  # ignore anti-aliased pixels — handled by threshold
    )

    total_pixels = baseline_img.size[0] * baseline_img.size[1]
    diff_ratio = mismatched_pixels / total_pixels

    if diff_ratio > DIFF_RATIO:
        actual_path = SNAPSHOT_DIR / f"{name}-actual.png"
        diff_path = SNAPSHOT_DIR / f"{name}-diff.png"
        actual_img.save(actual_path)
        diff_img.save(diff_path)
        raise AssertionError(
            f"Snapshot mismatch for {name}: "
            f"diff_ratio={diff_ratio:.4f} > {DIFF_RATIO} "
            f"({mismatched_pixels}/{total_pixels} pixels differ). "
            f"Compare {baseline_path.name} ↔ {actual_path.name}; "
            f"diff image at {diff_path.name}."
        )


# ── Tests — Chat ──────────────────────────────────────────────────────────


@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_chat_empty(app_clean: str, page: Page, theme: str) -> None:
    """Empty chat — no provider seeded, getting-started banner shows."""
    page.set_viewport_size(VIEWPORT)
    page.goto(app_clean)
    _set_theme(page, theme)
    # Wait for the chat content panel to be visible — getting-started
    # banner is the empty state.  ``.content-panel.area-chat`` is unique
    # (the sidebar also carries ``.area-chat`` as a scope class, so a
    # bare ``.area-chat`` locator hits two elements).
    expect(page.locator(".content-panel.area-chat")).to_be_visible(timeout=5000)
    _wait_for_render(page)
    _assert_screenshot(page, f"chat-empty-{theme}")


@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_chat_with_messages(app_with_agent: SeededApp, page: Page, theme: str) -> None:
    """Chat with one user + one assistant message via mock provider."""
    page.set_viewport_size(VIEWPORT)
    page.goto(app_with_agent.base_url)
    _set_theme(page, theme)
    # F5 L04: the `app_with_agent` fixture seeds an agent but does NOT
    # pre-create a chat session; the welcome canvas shows on page load.
    # Click the welcome-canvas agent item to bootstrap a session before
    # waiting for the badge. Pattern matches tests/browser/test_flow_chat.py:29.
    # Fixes mission KI #1 — `.session-agent-badge` never populated under
    # the pre-fix auto-session-join assumption (race / nonexistent flow).
    page.locator(".chat-welcome-item").filter(
        has_text=app_with_agent.agent_name
    ).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    page.locator('[data-testid="chat-input"]').fill("hello")
    page.locator('[data-testid="chat-send-btn"]').click()
    expect(page.locator('[data-testid="message"].assistant')).to_have_text(
        "Mock response from the mock provider.", timeout=10000
    )
    # Wait for the send button to re-enable (busy=false after `done`).
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()
    _wait_for_render(page)
    _assert_screenshot(page, f"chat-with-messages-{theme}")


# ── Tests — Studio ────────────────────────────────────────────────────────


@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_studio_empty(app_with_provider: SeededApp, page: Page, theme: str) -> None:
    """Empty Studio — provider seeded, no agents yet."""
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_with_provider.base_url}#studio")
    _set_theme(page, theme)
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible(timeout=5000)
    _wait_for_render(page)
    _assert_screenshot(page, f"studio-empty-{theme}")


@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_studio_with_agent(app_with_agent: SeededApp, page: Page, theme: str) -> None:
    """Studio with one agent visible in sidebar."""
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_with_agent.base_url}#studio")
    _set_theme(page, theme)
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(1, timeout=5000)
    _wait_for_render(page)
    _assert_screenshot(page, f"studio-with-agent-{theme}")


# ── Tests — Admin ─────────────────────────────────────────────────────────


@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_admin_empty(app_clean: str, page: Page, theme: str) -> None:
    """Admin → LLM Providers, empty state (no providers seeded)."""
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_clean}#admin")
    _set_theme(page, theme)
    page.locator(".section-nav-item", has_text="LLM Providers").click()
    expect(page.locator(".admin-provider-empty")).to_be_visible(timeout=5000)
    _wait_for_render(page)
    _assert_screenshot(page, f"admin-empty-{theme}")


@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_admin_with_provider(app_with_provider: SeededApp, page: Page, theme: str) -> None:
    """Admin → LLM Providers with one mock provider card visible."""
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_with_provider.base_url}#admin")
    _set_theme(page, theme)
    page.locator(".section-nav-item", has_text="LLM Providers").click()
    expect(page.locator('[data-testid="provider-card"]')).to_be_visible(timeout=5000)
    _wait_for_render(page)
    _assert_screenshot(page, f"admin-with-provider-{theme}")

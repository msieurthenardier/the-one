"""WCAG 2.1 AA contrast audits for the F2 design system tokens.

The token tables (``DARK`` / ``LIGHT``) live in
``tests/browser/design_tokens.py`` (a single Python mirror of
``the_one/interfaces/web/static/css/tokens.css``). If the CSS values
change, update that module in lockstep — these tests are the regression
net for any future token retune.

WCAG AA thresholds (per WCAG 2.1):

- 4.5:1 for body text
- 3.0:1 for large text (>=18pt or >=14pt bold) and UI components / non-text

See ``the_one/agents.md`` ("Color contrast (WCAG AA)" subsection) for the
audit summary and any documented deliberate exceptions.
"""

from __future__ import annotations

import pytest

# DARK / LIGHT live in tests/browser/design_tokens.py — single source of
# truth for any test that references token values.  pytest's
# ``pythonpath = ["tests"]`` config (pyproject.toml) makes
# ``browser.design_tokens`` importable as a top-level package.
from browser.design_tokens import DARK, LIGHT


# ---------------------------------------------------------------------------
# Contrast helpers (WCAG 2.1 sRGB luminance + contrast ratio formula)
# ---------------------------------------------------------------------------


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    """Parse a #RRGGBB (or #RGB) hex string into an (R, G, B) tuple of 0-1 floats."""
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG 2.1 relative luminance for an sRGB color."""

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Compute the WCAG 2.1 contrast ratio between two sRGB colors.

    Returns a value in [1.0, 21.0]. Order of arguments does not matter
    (the formula is symmetric — lighter / darker is determined internally).
    """
    l1 = _luminance(_hex_to_rgb(fg_hex))
    l2 = _luminance(_hex_to_rgb(bg_hex))
    lighter, darker = (l1, l2) if l1 > l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# Token values — DARK / LIGHT imported from tests/browser/design_tokens.py
# (single source of truth; mirrors tokens.css blocks).
# ---------------------------------------------------------------------------


def _palette(theme: str) -> dict[str, str]:
    return DARK if theme == "dark" else LIGHT


# ---------------------------------------------------------------------------
# Body text (≥ 4.5:1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "theme,fg_key,bg_key",
    [
        # Dark — body text on bg/surface.
        # NOTE: --fg-tertiary (#666) is NOT exercised as body in dark; it is a
        # tertiary/UI token in dark and is covered under the 3:1 large/UI
        # threshold rather than the 4.5:1 body threshold.
        ("dark", "fg", "bg"),
        ("dark", "fg", "surface"),
        ("dark", "fg_secondary", "bg"),
        ("dark", "fg_secondary", "surface"),
        # --fg-muted (dark) #a8a8a8 — promoted to body-AA per F2 debrief.
        ("dark", "fg_muted", "bg"),
        ("dark", "fg_muted", "surface"),
        # Light — body text on bg/surface.
        ("light", "fg", "bg"),
        ("light", "fg", "surface"),
        ("light", "fg_secondary", "bg"),
        ("light", "fg_secondary", "surface"),
        ("light", "fg_tertiary", "bg"),
        ("light", "fg_tertiary", "surface"),
    ],
)
def test_body_text_passes_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Body text contrast ≥ 4.5:1 (WCAG 2.1 AA, success criterion 1.4.3)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 4.5, (
        f"{theme} body text fails AA: {fg_key} on {bg_key} = "
        f"{ratio:.2f}:1 (need ≥ 4.5:1)"
    )


# ---------------------------------------------------------------------------
# Large text / UI components / non-text (≥ 3.0:1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "theme,fg_key,bg_key",
    [
        # Dark — accent and tertiary/muted as UI tokens.
        ("dark", "accent", "bg"),
        ("dark", "accent", "surface"),
        ("dark", "fg_tertiary", "bg"),
        ("dark", "fg_tertiary", "surface"),
        # Status-danger-muted is the idle-state colour for delete affordances
        # (added at HAT in leg 09). Used as text + border on body bg AND inside
        # surface contexts (chip-remove sits on chip surface; session-delete sits
        # on session-item surface). Pair must hold against both.
        ("dark", "status_danger_muted", "bg"),
        ("dark", "status_danger_muted", "surface"),
        # Light — accent and muted as UI tokens.
        ("light", "accent", "bg"),
        ("light", "accent", "surface"),
        ("light", "fg_muted", "bg"),
        ("light", "fg_muted", "surface"),
        ("light", "status_danger_muted", "bg"),
        ("light", "status_danger_muted", "surface"),
    ],
)
def test_large_or_ui_passes_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Large text and UI components ≥ 3.0:1 (WCAG 2.1 AA, success criteria 1.4.3 / 1.4.11)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 3.0, (
        f"{theme} large/UI fails AA: {fg_key} on {bg_key} = "
        f"{ratio:.2f}:1 (need ≥ 3.0:1)"
    )


# ---------------------------------------------------------------------------
# Text on solid color backgrounds (accent / danger / status)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "theme,fg_key,bg_key,threshold",
    [
        # Text on accent (cyan) — body threshold (used on filled buttons, etc.)
        ("dark", "fg_on_accent", "accent", 4.5),
        ("light", "fg_on_accent", "accent", 4.5),
        # Text on danger (red) — body threshold (delete-confirm states)
        ("dark", "fg_on_danger", "status_danger", 4.5),
        ("light", "fg_on_danger", "status_danger", 4.5),
        # Status text on bg/surface.
        # Dark: bright variants used as small UI affordances → 3:1 large/UI.
        ("dark", "status_success", "bg", 3.0),
        ("dark", "status_success", "surface", 3.0),
        ("dark", "status_warning", "bg", 3.0),
        ("dark", "status_warning", "surface", 3.0),
        ("dark", "status_danger", "bg", 3.0),
        ("dark", "status_danger", "surface", 3.0),
        # Light: deeper variants used as readable status text → 4.5:1 body.
        ("light", "status_success", "bg", 4.5),
        ("light", "status_success", "surface", 4.5),
        ("light", "status_warning", "bg", 4.5),
        ("light", "status_warning", "surface", 4.5),
        ("light", "status_danger", "bg", 4.5),
        ("light", "status_danger", "surface", 4.5),
    ],
)
def test_text_on_color(
    theme: str, fg_key: str, bg_key: str, threshold: float
) -> None:
    """Text-on-color and status-token contrast checks."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= threshold, (
        f"{theme}: {fg_key} on {bg_key} = {ratio:.2f}:1 (need ≥ {threshold}:1)"
    )


# ---------------------------------------------------------------------------
# Deliberate exceptions (documented — not a failure to fix)
# ---------------------------------------------------------------------------


# DELIBERATE EXCEPTION (1/2): --fg-faint (dark) #444 on #0a0a0a ≈ 2.0:1.
# Used for de-emphasized annotation labels (chat telemetry "in:"/"out:"/"ctx:"
# eyebrows, env-var hints), disabled placeholder text, and decorative recessive
# marks. Never body prose, never an interactive UI affordance. Pinned with a
# non-AA bound to make the intent explicit and to fail loudly if someone
# retunes the token to a value that crosses into a different intent class.
# Documented in agents.md.
def test_fg_faint_dark_is_intentional_low_contrast() -> None:
    """`--fg-faint` (dark) is intentionally below body AA — faint contexts only."""
    ratio = contrast_ratio("#444444", DARK["bg"])
    assert 1.0 < ratio < 4.5, (
        f"--fg-faint dark drifted out of expected band: ratio={ratio:.2f}:1"
    )


# DELIBERATE EXCEPTION (2/2): --fg-faint (light) #94a3b8 on #fafbfc ≈ 2.47:1.
# Below both the 4.5:1 body and 3:1 large/UI thresholds. Used for de-emphasized
# annotation labels (chat telemetry eyebrows, env-var hints), placeholder text,
# disabled-state labels, and decorative recessive marks — never body prose,
# never an interactive UI affordance. Documented in agents.md alongside the
# dark counterpart. The band assertion below pins the value: a token retune
# that drifts above 4.5:1 (would no longer be "faint") or below 1.5:1 (would
# be invisible) fails the test loudly.
def test_fg_faint_light_is_intentional_low_contrast() -> None:
    """`--fg-faint` (light) is intentionally below body AA — faint contexts only."""
    ratio = contrast_ratio("#94a3b8", LIGHT["bg"])
    assert 1.5 < ratio < 4.5, (
        f"--fg-faint light drifted out of expected band: ratio={ratio:.2f}:1"
    )

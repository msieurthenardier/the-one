"""WCAG 2.1 contrast audits for the Holograph design system tokens.

The token tables (``LIGHT_TOKENS`` / ``DARK_TOKENS``) live in
``tests/browser/design_tokens.py`` (a single Python mirror of
``the_one/interfaces/web/static/css/tokens.css``). If the CSS values
change, update that module in lockstep — these tests are the regression
net for any future token retune.

The audit pairs below are drawn from the Holograph migration design spec:
``docs/superpowers/specs/2026-05-12-holograph-ui-migration-design.md``
§"A11y audit (recomputed contrast pairs)".

WCAG thresholds used:

- 7.0:1 AAA (body text — stricter goal for primary foreground)
- 4.5:1 AA body text
- 3.0:1 AA large text (>=18pt or >=14pt bold) and UI components / non-text
"""

from __future__ import annotations

import pytest

# LIGHT_TOKENS / DARK_TOKENS live in tests/browser/design_tokens.py — single
# source of truth for any test that references token values.  pytest's
# ``pythonpath = ["tests"]`` config (pyproject.toml) makes
# ``browser.design_tokens`` importable as a top-level package.
from browser.design_tokens import DARK_TOKENS, LIGHT_TOKENS

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
# Holograph audit pair tables
# Each entry: (name, fg_hex, bg_hex, threshold, kind)
# ---------------------------------------------------------------------------

HOLOGRAPH_LIGHT_PAIRS = [
    ("--accent × --bg", "#3358c0", "#f8f8f6", 4.5, "body AA"),
    ("--fg × --bg", "#16181d", "#f8f8f6", 7.0, "AAA"),
    ("--fg-mute × --bg", "#6a6e76", "#f8f8f6", 4.5, "body AA"),
    ("--fg-faint × --bg", "#878d96", "#f8f8f6", 3.0, "AA-large/UI"),
    ("button-text × --accent (light)", "#ffffff", "#3358c0", 4.5, "body AA on primary button"),
    ("--fg-on-accent × --accent", "#ffffff", "#3358c0", 4.5, "body AA"),
    ("--fg-on-danger × --danger", "#ffffff", "#c5443d", 4.5, "body AA"),
    ("--avatar-fg × --avatar-bg", "#3c4048", "#e8eaef", 4.5, "body AA"),
]

HOLOGRAPH_DARK_PAIRS = [
    ("--accent × --bg", "#a78bfa", "#0a0c10", 4.5, "body AA"),
    ("--fg × --bg", "#e6e7ea", "#0a0c10", 7.0, "AAA"),
    ("--fg-mute × --bg", "#9aa1ac", "#0a0c10", 4.5, "body AA"),
    ("--fg-faint × --bg", "#6a7280", "#0a0c10", 3.0, "AA-large/UI"),
    ("button-text × --accent (dark)", "#15101f", "#a78bfa", 4.5, "body AA on primary button"),
    ("--fg-on-accent × --accent", "#15101f", "#a78bfa", 4.5, "body AA"),
    ("--fg-on-danger × --danger", "#0a0c10", "#f87171", 4.5, "body AA"),
    ("--avatar-fg × --avatar-bg", "#c4c8cf", "#26282d", 4.5, "body AA"),
]


# ---------------------------------------------------------------------------
# Parametrized contrast audit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,fg_hex,bg_hex,threshold,kind",
    HOLOGRAPH_LIGHT_PAIRS + HOLOGRAPH_DARK_PAIRS,
    ids=lambda p: p if isinstance(p, str) else None,
)
def test_holograph_contrast_audit(
    name: str, fg_hex: str, bg_hex: str, threshold: float, kind: str
) -> None:
    """Every pair in the Holograph contrast audit table meets its WCAG threshold."""
    ratio = contrast_ratio(fg_hex, bg_hex)
    assert ratio >= threshold, (
        f"{name} ({kind}) fails: {fg_hex} × {bg_hex} = {ratio:.2f}:1 (need ≥ {threshold}:1)"
    )


# ---------------------------------------------------------------------------
# Cross-check: audit hex literals must match design_tokens.py
# ---------------------------------------------------------------------------


def test_audit_pairs_match_design_tokens() -> None:
    """The hex literals in HOLOGRAPH_*_PAIRS match design_tokens.py — no drift."""
    # Light token cross-check (--fg-on-accent collapses to "#ffffff"; --avatar-*
    # cross-checked separately so dict-keyed dedupe doesn't lose them).
    light_token_pairs = {
        "#3358c0": LIGHT_TOKENS["--accent"],
        "#16181d": LIGHT_TOKENS["--fg"],
        "#6a6e76": LIGHT_TOKENS["--fg-mute"],
        "#878d96": LIGHT_TOKENS["--fg-faint"],
        "#ffffff": LIGHT_TOKENS["--fg-on-danger"],
        "#f8f8f6": LIGHT_TOKENS["--bg"],
        "#c5443d": LIGHT_TOKENS["--danger"],
    }
    for expected, actual in light_token_pairs.items():
        assert expected == actual, f"light token drift: expected {expected}, got {actual}"
    assert LIGHT_TOKENS["--fg-on-accent"] == "#ffffff"
    assert LIGHT_TOKENS["--avatar-bg"] == "#e8eaef"
    assert LIGHT_TOKENS["--avatar-fg"] == "#3c4048"

    # Dark token cross-check (--bg / --fg-on-danger share #0a0c10 — asserted
    # separately; --fg-on-accent + --avatar-* mirrored individually).
    dark_token_pairs = {
        "#a78bfa": DARK_TOKENS["--accent"],
        "#e6e7ea": DARK_TOKENS["--fg"],
        "#9aa1ac": DARK_TOKENS["--fg-mute"],
        "#6a7280": DARK_TOKENS["--fg-faint"],
        "#0a0c10": DARK_TOKENS["--fg-on-danger"],
        # Note: --bg is duplicated; this captures it once.
        "#f87171": DARK_TOKENS["--danger"],
    }
    for expected, actual in dark_token_pairs.items():
        assert expected == actual, f"dark token drift: expected {expected}, got {actual}"

    # --bg is #0a0c10 in dark (same hex as --fg-on-danger — assert separately).
    assert DARK_TOKENS["--bg"] == "#0a0c10"
    assert DARK_TOKENS["--fg-on-accent"] == "#15101f"
    assert DARK_TOKENS["--avatar-bg"] == "#26282d"
    assert DARK_TOKENS["--avatar-fg"] == "#c4c8cf"

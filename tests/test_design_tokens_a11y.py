"""WCAG 2.1 AA contrast audits for the v3 design system tokens.

The token tables (``DARK`` / ``LIGHT``) live in
``tests/browser/design_tokens.py`` (a single Python mirror of
``the_one/interfaces/web/static/css/tokens.css``; the mirror-sync guard
in ``tests/test_ui_guards.py`` enforces the CSS↔mirror lockstep). If the
CSS values change, update that module in lockstep — these tests are the
regression net for any future token retune.

Coverage (v3 full-palette parametrization, Mission 17 Flight 02 Leg 01):
every literal-hex fg-role token is exercised against every surface it
can sit on in BOTH themes —

- fg ladder (``fg`` … ``fg_muted``, ``fg_tool_msg``) × bg / surface /
  surface-elevated / surface-tool at the 4.5:1 body threshold
- ``fg_faint`` — DELIBERATE EXCEPTION, band-pinned 3.0 ≤ r < 4.5 on all
  three ladder surfaces (see the exception tests at the bottom)
- accent / accent-api / status-danger-muted × bg / surface /
  surface-elevated at the 3.0:1 large-text/UI threshold
- on-color pairs (text on accent / accent-api / danger fills; code-block
  fg on code-block bg) at the 4.5:1 body threshold
- status colors × bg / surface at the 4.5:1 body threshold (both themes'
  v3 status families clear body AA — the dark theme's previous 3.0 UI
  carve-out is retired)

Badge (``--badge-*``) on-color pairs are measured and recorded in the
flight log but NOT gated here — badge values are pre-v3 legacy and
gating lands with Flight 3's badge component rebuild.

WCAG AA thresholds (per WCAG 2.1):

- 4.5:1 for body text (success criterion 1.4.3)
- 3.0:1 for large text (>=18pt or >=14pt bold) and UI components /
  non-text (success criteria 1.4.3 / 1.4.11)

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


THEMES = ("dark", "light")

# The three ladder surfaces every fg-role token can sit on. surface_tool
# shares surface_elevated's value in v3 but is asserted independently so
# a future divergence stays inside the audit net.
_LADDER_SURFACES = ("bg", "surface", "surface_elevated", "surface_tool")

# fg ladder tokens that must clear BODY AA on every ladder surface.
# fg_faint is deliberately absent — see the exception tests below.
_BODY_FG_TOKENS = ("fg", "fg_secondary", "fg_tertiary", "fg_muted", "fg_tool_msg")


# ---------------------------------------------------------------------------
# Body text (≥ 4.5:1) — full fg-ladder × surface sweep, both themes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bg_key", _LADDER_SURFACES)
@pytest.mark.parametrize("fg_key", _BODY_FG_TOKENS)
@pytest.mark.parametrize("theme", THEMES)
def test_body_text_passes_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Body text contrast ≥ 4.5:1 (WCAG 2.1 AA, success criterion 1.4.3).

    Every non-faint fg-ladder tier must hold body AA on every ladder
    surface: the tiers are used interchangeably across bg (page prose),
    surface (panels, sidebar), and surface-elevated (chips, code wells —
    e.g. ``.pending-queued-chip`` puts --fg-muted on --surface-elevated).
    """
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 4.5, (
        f"{theme} body text fails AA: {fg_key} on {bg_key} = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


# ---------------------------------------------------------------------------
# Large text / UI components / non-text (≥ 3.0:1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bg_key", ("bg", "surface", "surface_elevated"))
@pytest.mark.parametrize(
    "fg_key",
    [
        # accent: interactive/selected-state color (nav active state, links,
        # focus outlines) — UI threshold on every ladder surface.
        "accent",
        # accent_api: badge-tier differentiator, also rides bare surfaces
        # as a text/border tint in chat.
        "accent_api",
        # status_danger_muted: idle-state color for delete affordances
        # (text + border), used on body bg AND inside surface contexts
        # (chip-remove on chip surface; session-delete on session-item).
        "status_danger_muted",
    ],
)
@pytest.mark.parametrize("theme", THEMES)
def test_large_or_ui_passes_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Large text and UI components ≥ 3.0:1 (WCAG 2.1 AA, success criteria 1.4.3 / 1.4.11)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 3.0, (
        f"{theme} large/UI fails AA: {fg_key} on {bg_key} = {ratio:.2f}:1 (need ≥ 3.0:1)"
    )


# ---------------------------------------------------------------------------
# Text on solid color backgrounds (accent / danger / status / code well)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fg_key,bg_key,threshold",
    [
        # Text on primary accent — body threshold (filled buttons, etc.)
        ("fg_on_accent", "accent", 4.5),
        # accent_api is used as a chat message background at chat.css —
        # text-on-color body threshold applies (foreground inherits
        # --fg-on-accent from the parent .msg.user rule).
        ("fg_on_accent", "accent_api", 4.5),
        # Text on danger (red) — body threshold (delete-confirm states).
        # Dark pairs dark ink (#101114) with the bright #f87171 fill;
        # light pairs white with the deep #dc2626 fill.
        ("fg_on_danger", "status_danger", 4.5),
        # Code well — literal-hex pair in both themes (dark: one step
        # darker than bg; light: pale zinc + primary ink).
        ("code_block_fg", "code_block_bg", 4.5),
    ],
)
@pytest.mark.parametrize("theme", THEMES)
def test_text_on_color(theme: str, fg_key: str, bg_key: str, threshold: float) -> None:
    """Text-on-color contrast checks (both themes)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= threshold, (
        f"{theme}: {fg_key} on {bg_key} = {ratio:.2f}:1 (need ≥ {threshold}:1)"
    )


@pytest.mark.parametrize("bg_key", ("bg", "surface"))
@pytest.mark.parametrize("fg_key", ("status_success", "status_warning", "status_danger"))
@pytest.mark.parametrize("theme", THEMES)
def test_status_text_passes_body_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Status colors as readable text ≥ 4.5:1 on bg and surface (both themes).

    v3 retuned both themes' status families to clear BODY AA on bg and
    surface (dark: Tailwind-400 brights; light: deep 600/700s), so the
    previous dark-theme 3.0:1 UI carve-out is retired. Status text on
    --surface-elevated is deliberately NOT gated: the light 600/700
    family sits at ≈4.4:1 there and no production consumer puts status
    text on an elevated surface today — introducing one requires either
    a deeper status hex or an explicit exception here.
    """
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 4.5, (
        f"{theme} status text fails body AA: {fg_key} on {bg_key} = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


# ---------------------------------------------------------------------------
# Deliberate exceptions (documented — not a failure to fix)
# ---------------------------------------------------------------------------


# DELIBERATE EXCEPTION: --fg-faint is the de-emphasis tier and is pinned
# BETWEEN the UI floor and body AA (3.0 ≤ ratio < 4.5) on all three
# ladder surfaces, in both themes:
#
# - dark  #6b6d78 → 3.67 / 3.45 / 3.27 on bg / surface / surface-elevated
# - light #898993 → 3.46 / 3.32 / 3.15 on bg / surface / surface-elevated
#
# Rationale (flight DD "fg-faint exception re-evaluated"): a faint tier
# pinned at ≥4.5 stops being faint — the AA-passing hex would sit above
# the muted target and invert the ladder. The consumer rule: fg-faint is
# for de-emphasized ANNOTATIONS ONLY (.msg-attribution sender/timestamp
# labels, telemetry eyebrows) — never body prose, never an interactive
# affordance. The band's lower bound (3.0) keeps it legible as an
# annotation; the upper bound fails loudly if a retune drifts it into a
# different intent class (no-longer-faint).
@pytest.mark.parametrize("bg_key", ("bg", "surface", "surface_elevated"))
@pytest.mark.parametrize("theme", THEMES)
def test_fg_faint_band_exception(theme: str, bg_key: str) -> None:
    """`--fg-faint` holds the deliberate 3.0 ≤ ratio < 4.5 band on every ladder surface."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette["fg_faint"], palette[bg_key])
    assert 3.0 <= ratio < 4.5, (
        f"{theme} --fg-faint drifted out of the deliberate-exception band on {bg_key}: "
        f"ratio={ratio:.2f}:1 (band: 3.0 ≤ r < 4.5)"
    )

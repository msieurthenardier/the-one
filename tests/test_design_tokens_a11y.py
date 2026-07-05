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

Badge (``--badge-*``) × ink (``--badge-ink-*``) pairs are GATED here as
of Mission 17 Flight 03 Leg 04: every provider / tool / connector badge
carries a per-badge ink (light-toned fills take dark ink, dark-toned
fills take white ink) so its text clears body AA (≥4.5:1) on that fill
in BOTH themes. web's light-theme fill was darkened (#d63a93 → #cc2d87)
so its white ink clears the threshold. See the flight log for the final
measured table.

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


def _alpha_composite(fg_hex: str, alpha: float, base_hex: str) -> str:
    """Composite an opaque ``fg`` at ``alpha`` over an opaque ``base``, return #RRGGBB.

    The WCAG contrast formula is flat (no alpha), so a low-alpha wash token
    (``--status-danger-bg-soft`` is an rgba) must be resolved to the opaque
    color it renders as before it can be audited. Standard source-over:
    ``out = fg*alpha + base*(1-alpha)`` per channel.
    """
    fg = _hex_to_rgb(fg_hex)
    base = _hex_to_rgb(base_hex)
    out = tuple(fg[i] * alpha + base[i] * (1 - alpha) for i in range(3))
    return "#" + "".join(f"{round(c * 255):02x}" for c in out)


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
        # Text on primary accent — body threshold. Consumer today is
        # .btn-filled-primary (accent fill + --fg-on-accent text). NOTE
        # (M17 F04 L02): the chat .msg.user bubble NO LONGER uses this pair —
        # it was retuned from a saturated --accent fill to an
        # --accent-translucent tint (see test_tinted_user_bubble_text_passes_body_aa
        # below). The pair stays gated because .btn-filled-primary still uses it.
        ("fg_on_accent", "accent", 4.5),
        # accent_api is the SATURATED marker fill for API-sourced user
        # messages (.msg.user.api, chat.css). Post-M17-F04-L02 the plain
        # .msg.user bubble is a tint, so .msg.user.api PINS its own
        # color: --fg-on-accent (it no longer inherits from .msg.user) — this
        # pair therefore still reflects the rendered API bubble text-on-fill.
        ("fg_on_accent", "accent_api", 4.5),
        # Text on danger (red) — body threshold (delete-confirm states).
        # Dark pairs dark ink (#101114) with the bright #f87171 fill;
        # light pairs white with the deep #b91c1c fill (red-700, M17 F3 fix).
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
# Danger text on the soft-danger FILL (≥ 4.5:1) — both themes (M17 F3 fix)
# ---------------------------------------------------------------------------

# --status-danger-bg-soft is a low-alpha rgba wash whose base color is the
# --status-danger hue (the family is kept MATCHED in tokens.css: light soft
# = rgba(185,28,28,0.06) matches --status-danger #b91c1c; dark soft =
# rgba(248,113,113,0.08) matches #f87171). Because the wash is an rgba it is
# NOT mirrored in design_tokens.py (see that module's "Deliberately NOT
# mirrored" note); the gate reconstructs the rendered fill by compositing
# --status-danger at the theme's soft alpha over each ladder surface, then
# asserts --status-danger text clears body AA on that fill.
#
# This gates .btn-muted-destructive (components.css) — the real destructive
# button (Danger Zone / delete across provider/connector/mcp-server editors,
# general-tab, system-page): 12px normal-weight = body text needing ≥4.5:1.
# The light-theme #dc2626 → #b91c1c deepening (M17 F3 accessibility fix)
# cleared it; this test fails loudly if a future retune lightens it back.
#
# Alpha per theme MUST track --status-danger-bg-soft in tokens.css.
_STATUS_DANGER_SOFT_ALPHA = {"dark": 0.08, "light": 0.06}


@pytest.mark.parametrize("bg_key", ("bg", "surface", "surface_elevated"))
@pytest.mark.parametrize("theme", THEMES)
def test_danger_text_on_soft_fill_passes_body_aa(theme: str, bg_key: str) -> None:
    """`--status-danger` text ≥ 4.5:1 on the composited `--status-danger-bg-soft`
    fill, over bg AND surface AND surface-elevated, in BOTH themes."""
    palette = _palette(theme)
    danger = palette["status_danger"]
    alpha = _STATUS_DANGER_SOFT_ALPHA[theme]
    fill = _alpha_composite(danger, alpha, palette[bg_key])
    ratio = contrast_ratio(danger, fill)
    assert ratio >= 4.5, (
        f"{theme} danger-on-soft-fill fails body AA: status_danger on "
        f"status-danger-bg-soft over {bg_key} = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


# ---------------------------------------------------------------------------
# Chat washed surfaces (composited-a11y gates) — M17 F04 L02
# ---------------------------------------------------------------------------
#
# The chat reading layout (F04 L02) paints text on several rgba WASH tokens.
# The flat WCAG formula can't read alpha, so each wash is reconstructed with
# _alpha_composite over a SINGLE known base surface, then the text color is
# audited on the resulting opaque fill (the F3-debrief composited-a11y
# pattern). Every wash below is authored as rgba-over-a-single-known-surface
# (never wash-over-wash / color-mix, which the one-layer helper can't
# reconstruct). The base surface behind the chat .messages log is --bg (body
# background; no intermediate content-panel fill — verified in chat.css /
# base.css), so every chat wash composites over --bg.
#
# NOT gated here because they are SOLID (non-rgba) surfaces already covered by
# the fg-ladder × surface sweep at the top of this module:
#   - tool-on-surface-tool  → fg_tool_msg × surface_tool  (body-AA ladder)
#   - peer-on-elevated      → fg × surface_elevated       (body-AA ladder)
# Adding a composite gate for a solid surface would be wrong (no alpha to
# composite); the ladder sweep is their regression net.
#
# Alphas MUST track tokens.css. --accent-translucent is rgba(accent, α); the
# base accent hue is the mirrored `accent` token. --surface-translucent is
# rgba(white/near-black, 0.03) — its wash color is NOT a clean mirror token,
# so it's spelled literally here (dark = #ffffff, light = #18181b, matching
# tokens.css). These mirror the module's "rgba washes are not mirrored; their
# bases are" policy in design_tokens.py.
_ACCENT_TRANSLUCENT_ALPHA = {"dark": 0.10, "light": 0.08}
_SURFACE_TRANSLUCENT = {
    "dark": ("#ffffff", 0.03),  # rgba(255,255,255,0.03)
    "light": ("#18181b", 0.03),  # rgba(24,24,27,0.03)
}
# Telemetry overlay resting opacity (chat.css .telemetry-overlay { opacity }).
_TELEMETRY_RESTING_OPACITY = 0.7


@pytest.mark.parametrize("theme", THEMES)
def test_tinted_user_bubble_text_passes_body_aa(theme: str) -> None:
    """NEW (F04 L02): --fg text ≥ 4.5:1 on the composited --accent-translucent
    tint (rgba accent) over --bg — the retuned .msg.user bubble, both themes.

    Replaces the old saturated-accent user bubble (which relied on
    --fg-on-accent × --accent). The bubble is now a quiet accent WASH with
    primary --fg text; this gate is its regression net.
    """
    palette = _palette(theme)
    alpha = _ACCENT_TRANSLUCENT_ALPHA[theme]
    fill = _alpha_composite(palette["accent"], alpha, palette["bg"])
    ratio = contrast_ratio(palette["fg"], fill)
    assert ratio >= 4.5, (
        f"{theme} tinted-user-bubble fails body AA: fg on accent-translucent "
        f"over bg = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


@pytest.mark.parametrize(
    "surface_label",
    [
        # .msg.assistant background: --surface-translucent over --bg.
        "assistant-on-translucent",
        # GFM table zebra: tbody tr:nth-child(even) is --surface-translucent
        # too, nested inside the (also translucent) assistant bubble. Modeled
        # single-layer over --bg per the "single known surface" rule — the
        # extra 0.03 assistant layer is negligible and --fg clears by a wide
        # margin either way; this gate is the tripwire, not a pixel model.
        "table-zebra-on-translucent",
    ],
)
@pytest.mark.parametrize("theme", THEMES)
def test_translucent_surface_prose_passes_body_aa(theme: str, surface_label: str) -> None:
    """F04 L02: --fg prose ≥ 4.5:1 on the composited --surface-translucent
    wash over --bg (assistant bubble + GFM table zebra), both themes."""
    palette = _palette(theme)
    wash_hex, alpha = _SURFACE_TRANSLUCENT[theme]
    fill = _alpha_composite(wash_hex, alpha, palette["bg"])
    ratio = contrast_ratio(palette["fg"], fill)
    assert ratio >= 4.5, (
        f"{theme} {surface_label} fails body AA: fg on surface-translucent "
        f"over bg = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


@pytest.mark.parametrize("theme", THEMES)
def test_telemetry_ghost_value_holds_annotation_floor(theme: str) -> None:
    """F04 L02: the telemetry overlay's --fg-secondary value readout, ghosted
    at the resting opacity (0.7) over --bg, stays ≥ 3.0:1 (the annotation
    floor), both themes.

    The telemetry overlay is DELIBERATELY de-emphasized at rest (opacity 0.7);
    hover/focus-within lifts it to opacity 1.0, where --fg-secondary on --bg is
    fully body-AA via the fg-ladder sweep. This gate pins the RESTING ghost to
    the same ≥3.0 annotation floor the deliberate --fg-faint exception uses:
    legible-enough as a glanceable readout, and it fails loudly if a retune
    drops the resting value below glanceability. Opacity over an opaque base is
    an alpha composite of the text color onto the base.
    """
    palette = _palette(theme)
    ghosted = _alpha_composite(palette["fg_secondary"], _TELEMETRY_RESTING_OPACITY, palette["bg"])
    ratio = contrast_ratio(ghosted, palette["bg"])
    assert ratio >= 3.0, (
        f"{theme} telemetry-ghost value drops below the annotation floor: "
        f"fg_secondary @ {_TELEMETRY_RESTING_OPACITY} opacity on bg = {ratio:.2f}:1 "
        f"(need ≥ 3.0:1)"
    )


# ---------------------------------------------------------------------------
# Badge × ink (≥ 4.5:1) — per-badge ink, both themes (M17 F3 L4)
# ---------------------------------------------------------------------------

# Every badge maps to (fill token, ink token). The fill is looked up per
# theme (tool-badge fills diverge between themes; ink is theme-stable), so
# each pair is asserted against BOTH themes. This is the "fix THEN gate"
# contract from the flight DD "Badges": the fix is the per-badge ink (+ the
# web light-fill tune); this test is the gate.
_BADGE_INK_PAIRS = (
    ("ollama", "badge_ollama", "badge_ink_ollama"),
    ("openai-compatible", "badge_openai_compatible", "badge_ink_openai_compatible"),
    ("openai", "badge_openai", "badge_ink_openai"),
    ("anthropic", "badge_anthropic", "badge_ink_anthropic"),
    ("openrouter", "badge_openrouter", "badge_ink_openrouter"),
    ("mock", "badge_mock", "badge_ink_mock"),
    ("unknown", "badge_unknown", "badge_ink_unknown"),
    ("discord", "badge_discord", "badge_ink_discord"),
    ("filesystem", "badge_filesystem", "badge_ink_filesystem"),
    ("execution", "badge_execution", "badge_ink_execution"),
    ("web", "badge_web", "badge_ink_web"),
)


@pytest.mark.parametrize("badge,fill_key,ink_key", _BADGE_INK_PAIRS)
@pytest.mark.parametrize("theme", THEMES)
def test_badge_ink_passes_body_aa(theme: str, badge: str, fill_key: str, ink_key: str) -> None:
    """Every badge's ink clears body AA (≥ 4.5:1) on its fill, both themes.

    Provider fills are theme-stable; tool-badge fills diverge by theme
    (filesystem/execution lighter in light, web darkened for its white
    ink) — the fill is resolved per theme, the ink is theme-stable.
    """
    palette = _palette(theme)
    ratio = contrast_ratio(palette[ink_key], palette[fill_key])
    assert ratio >= 4.5, (
        f"{theme} badge fails body AA: {badge} ink on fill = {ratio:.2f}:1 (need ≥ 4.5:1)"
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

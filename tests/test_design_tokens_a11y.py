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
- ``fg_faint`` is part of the same sweep (squawk 0206 retired its band
  exception); the ladder is also pinned strictly ordered by contrast on every
  surface (``test_fg_ladder_is_strictly_ordered``)
- ``status_danger_muted`` (used as delete-affordance text) × the ladder
  surfaces at the 4.5:1 body threshold
- accent / accent-api / control-border × bg / surface /
  surface-elevated at the 3.0:1 large-text/UI threshold
- on-color pairs (text on accent / accent-api / danger fills; code-block
  fg on code-block bg) at the 4.5:1 body threshold
- status colors × bg / surface at the 4.5:1 body threshold (both themes'
  v3 status families clear body AA — the dark theme's previous 3.0 UI
  carve-out is retired)

Badge (``--badge-*``) × ink (``--badge-ink-*``) pairs are GATED here as
of Mission 17 Flight 03 Leg 04: every provider / transport badge
carries a per-badge ink (light-toned fills take dark ink, dark-toned
fills take white ink) so its text clears body AA (≥4.5:1) on that fill
in BOTH themes. See the flight log for the final measured table.

WCAG AA thresholds (per WCAG 2.1):

- 4.5:1 for body text (success criterion 1.4.3)
- 3.0:1 for large text (>=18pt or >=14pt bold) and UI components /
  non-text (success criteria 1.4.3 / 1.4.11)

See ``the_one/agents.md`` ("Color contrast (WCAG AA)" subsection) for the
audit summary. There are no deliberate sub-AA exceptions (squawk 0206).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# parse_tokens_css_theme_blocks reads the SOURCE OF TRUTH (tokens.css) — the
# SC2 completeness net below enumerates from it, never from the mirror.
from _ui_guard_helpers import parse_tokens_css_theme_blocks

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
# fg_faint is included: no deliberate exceptions remain (squawk 0206).
# status_danger_muted is text (delete affordances), so it is gated at body AA.
_BODY_FG_TOKENS = (
    "fg",
    "fg_secondary",
    "fg_tertiary",
    "fg_muted",
    "fg_faint",
    "fg_tool_msg",
    "status_danger_muted",
)

# The fg ladder, strongest to weakest.
_FG_LADDER = ("fg", "fg_secondary", "fg_tertiary", "fg_muted", "fg_faint")


# ---------------------------------------------------------------------------
# Body text (≥ 4.5:1) — full fg-ladder × surface sweep, both themes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bg_key", _LADDER_SURFACES)
@pytest.mark.parametrize("fg_key", _BODY_FG_TOKENS)
@pytest.mark.parametrize("theme", THEMES)
def test_body_text_passes_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Body text contrast ≥ 4.5:1 (WCAG 2.1 AA, success criterion 1.4.3).

    Every fg-ladder tier (faint included) must hold body AA on every ladder
    surface: the tiers are used interchangeably across bg (page prose),
    surface (panels, sidebar), and surface-elevated (chips, code wells —
    e.g. the queued chip's text sits on a chip fill).
    """
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 4.5, (
        f"{theme} body text fails AA: {fg_key} on {bg_key} = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


@pytest.mark.parametrize("bg_key", _LADDER_SURFACES)
@pytest.mark.parametrize("theme", THEMES)
def test_fg_ladder_is_strictly_ordered(theme: str, bg_key: str) -> None:
    """fg > secondary > tertiary > muted > faint by contrast on every surface,
    with a perceptible step (>= 0.3:1) between adjacent tiers."""
    palette = _palette(theme)
    ratios = [contrast_ratio(palette[k], palette[bg_key]) for k in _FG_LADDER]
    for hi, lo, rhi, rlo in zip(_FG_LADDER, _FG_LADDER[1:], ratios, ratios[1:]):
        assert rhi - rlo >= 0.3, (
            f"{theme} on {bg_key}: {hi} ({rhi:.2f}) is not clearly above {lo} ({rlo:.2f})"
        )


# ---------------------------------------------------------------------------
# Large text / UI components / non-text (≥ 3.0:1)
# ---------------------------------------------------------------------------


# M31 F1 flight review: non-text pins for the `.confirm-lapsed` outline
# (`--status-warning`) and the `.indicator-led` state colours (success, warning,
# danger, idle = `--fg-muted`) on the surfaces they sit on, 3.0:1 (WCAG 1.4.11).
@pytest.mark.parametrize("bg_key", ("bg", "surface", "surface_elevated"))
@pytest.mark.parametrize(
    "fg_key", ("status_warning", "status_success", "status_danger", "fg_muted")
)
@pytest.mark.parametrize("theme", THEMES)
def test_lapsed_outline_and_led_colours_pass_non_text_ui_aa(
    theme: str, fg_key: str, bg_key: str
) -> None:
    palette = _palette(theme)
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 3.0, (
        f"{theme}: {fg_key} on {bg_key} = {ratio:.2f}:1 (need >= 3.0:1 for the "
        ".confirm-lapsed outline / .indicator-led)"
    )


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
        # status_danger_muted is TEXT (delete affordances): gated at body AA
        # in the _BODY_FG_TOKENS sweep, not here (squawk 0206).
        # control_border: unchecked-checkbox border + off track of every toggle
        # (M25 F1 L3, DD7) — a control boundary is non-text UI, 3.0 on all
        # three ladder surfaces.
        "control_border",
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
        # Text on --accent. M25 F1 L3: NO solid-fill consumer remains —
        # .btn-filled-primary and every other solid control fill moved to
        # --accent-fill / --fg-on-accent-fill (gated just below). The pair
        # keeps guarding the token (--fg-on-accent still pairs with --accent
        # for any future accent-coloured surface) but is no longer pinned to a
        # CSS site. (M17 F04 L02: the chat user bubble (.ui-message--user) is a tint, see
        # test_tinted_user_bubble_text_passes_body_aa.)
        ("fg_on_accent", "accent", 4.5),
        # Deep-violet fills (M25 F1 L3, DD6/DD7): white ink on the solid
        # control fill (rest) and on its hover fill. Each migrated CSS site
        # is pinned to this pair by the usage-pin tests below.
        ("fg_on_accent_fill", "accent_fill", 4.5),
        ("fg_on_accent_fill", "accent_fill_hover", 4.5),
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
@pytest.mark.parametrize("theme", THEMES)
def test_accent_fill_vs_bg_and_surface_passes_ui_aa(theme: str, bg_key: str) -> None:
    """`--accent-fill` ≥ 3.0:1 against bg and surface (checked checkbox / on toggle
    identify state by the fill). surface_elevated is handled separately below
    (both themes gated) below.

    NOTE: `accent_fill_hover` vs surfaces is deliberately NOT gated: it is below
    3.0 in dark, and no state-bearing control uses the hover fill (checked
    checkboxes and on toggles never take it; only the transient primary-button
    hover does, and the button label carries the meaning)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette["accent_fill"], palette[bg_key])
    assert ratio >= 3.0, f"{theme}: accent_fill on {bg_key} = {ratio:.2f}:1 (need ≥ 3.0:1)"


@pytest.mark.parametrize("theme", THEMES)
def test_accent_fill_vs_surface_elevated_passes_ui_aa(theme: str) -> None:
    """`--accent-fill` >= 3.0:1 against surface-elevated, both themes (squawk 0206
    retired the dark 2.95:1 band exception; white ink on the fill and on its
    hover stays >= 4.5 via test_text_on_color)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette["accent_fill"], palette["surface_elevated"])
    assert ratio >= 3.0, f"{theme}: accent_fill on surface_elevated = {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_status_danger_on_surface_elevated_passes_body_aa(theme: str) -> None:
    """Danger-only: `status_danger` ≥ 4.5:1 on surface-elevated. The danger label
    sits on a transparent `.btn-muted-destructive`, which can rest on an elevated
    tile; the shared status test deliberately excludes elevated for success and
    warning (their light hexes sit ≈4.4 there)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette["status_danger"], palette["surface_elevated"])
    assert ratio >= 4.5, f"{theme}: status_danger on surface_elevated = {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_toggle_thumb_pairs_hold_ui_contrast(theme: str) -> None:
    """Every toggle thumb (`--control-thumb`) ≥ 3.0:1 against its track in BOTH
    states: off track `control_border`, on track `accent_fill`."""
    palette = _palette(theme)
    off = contrast_ratio(palette["control_thumb"], palette["control_border"])
    on = contrast_ratio(palette["control_thumb"], palette["accent_fill"])
    assert off >= 3.0, f"{theme}: control_thumb on control_border (off) = {off:.2f}:1"
    assert on >= 3.0, f"{theme}: control_thumb on accent_fill (on) = {on:.2f}:1"


@pytest.mark.parametrize("bg_key", ("bg", "surface"))
@pytest.mark.parametrize("fg_key", ("status_success", "status_warning", "status_danger"))
@pytest.mark.parametrize("theme", THEMES)
def test_status_text_passes_body_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Status colors as readable text ≥ 4.5:1 on bg and surface (both themes).

    v3 retuned both themes' status families to clear BODY AA on bg and
    surface (dark: Tailwind-400 brights; light: deep 600/700s), so the
    previous dark-theme 3.0:1 UI carve-out is retired. Status text on
    --surface-elevated is deliberately NOT gated for success and warning:
    the light 600/700 family sits at ≈4.4:1 there and no production
    consumer puts that status text on an elevated surface today —
    introducing one requires either a deeper status hex or an explicit
    exception here. DANGER is the one exception: its label on a transparent
    danger button can rest on an elevated tile, so
    test_status_danger_on_surface_elevated_passes_body_aa gates it there.
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
# This gates the SOFT-FILL hover of .btn-muted-destructive (components.css) —
# the real destructive button (Danger Zone / delete across provider/mcp-server
# editors, general-tab, system-page). Since M25 F1 L3 (DD6) the button rests
# transparent and the soft fill appears on HOVER only; the label is 13px
# medium-weight = body text needing ≥4.5:1, so the composite pair is still the
# one that matters (the at-rest transparent pair is test_status_text_passes_body_aa
# and test_status_danger_on_surface_elevated_passes_body_aa).
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
# The chip remove button's icon on the chip's accent-translucent FILL (>= 3:1, a UI
# component, WCAG 1.4.11) -- both themes. (M31 F6 L05a: the legacy `.chip-remove`
# danger glyph is gone; its last user, the chat's staged-image chip, is App.ui.chip, whose
# remove is a ghost small icon-only button at --fg-secondary.)
# ---------------------------------------------------------------------------

# --accent-translucent is a low-alpha rgba wash (base color --accent) that .chip
# (components.css) uses as its fill; the remove button sits on top of it. Because the wash is
# an rgba it is NOT mirrored in design_tokens.py (see that module's "Deliberately NOT
# mirrored" note); the gate reconstructs the rendered fill by compositing --accent at the
# theme's translucent alpha over each ladder surface. The same fill holds the queued-message
# chip's "Queued" lead text (--fg-secondary, caption size), which is body text and needs 4.5:1.
#
# Alpha per theme MUST track --accent-translucent in tokens.css.
_ACCENT_TRANSLUCENT_ALPHA = {"dark": 0.10, "light": 0.08}


@pytest.mark.parametrize("bg_key", ("bg", "surface", "surface_elevated"))
@pytest.mark.parametrize("theme", THEMES)
def test_chip_remove_icon_on_chip_fill_passes_ui_and_the_queued_lead_passes_body_aa(
    theme: str, bg_key: str
) -> None:
    """`--fg-secondary` on the composited `--accent-translucent` chip fill, over bg AND
    surface AND surface-elevated, in BOTH themes: the ghost remove icon >= 3:1 (UI
    component) and the queued chip's lead text >= 4.5:1 (body text)."""
    palette = _palette(theme)
    alpha = _ACCENT_TRANSLUCENT_ALPHA[theme]
    fill = _alpha_composite(palette["accent"], alpha, palette[bg_key])
    ratio = contrast_ratio(palette["fg_secondary"], fill)
    assert ratio >= 4.5, (
        f"{theme} chip remove icon / queued lead fails: fg_secondary on accent-translucent "
        f"over {bg_key} = {ratio:.2f}:1 (need >= 4.5:1 for the lead text, >= 3:1 for the icon)"
    )


def test_chip_danger_consumes_the_gated_danger_pair() -> None:
    """`.chip--danger` (components.css, the App.ui.chip danger tone) must paint
    `var(--status-danger)` text on
    the `var(--status-danger-bg-soft)` fill — the EXACT pair already gated by
    ``test_danger_text_on_soft_fill_passes_body_aa`` above.

    M17 F6 L1 pins the usage (per the flight's composite-a11y DD: the danger-on-
    soft pair is gated ONCE at the token level, not re-gated per surface). This
    source-grep guard fails loudly if a future retune points the chip at a NOVEL
    fg/bg triple — a signal that a fresh ``_alpha_composite`` gate is warranted
    for whatever new pair it introduces. Its sibling danger surface,
    ``.editor-error-banner``, is pinned by the leg-02 tools surface."""
    import re
    from pathlib import Path

    components_css = (
        Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css/components.css"
    )
    css = components_css.read_text(encoding="utf-8")
    # Isolate the `.chip--danger { ... }` declaration block.
    m = re.search(r"\.chip--danger\s*\{([^}]*)\}", css)
    assert m, ".chip--danger rule not found in components.css"
    body = m.group(1)
    assert "var(--status-danger-bg-soft)" in body, (
        ".chip--danger must fill with var(--status-danger-bg-soft) (the "
        "already-gated soft pair); a novel fill needs its own composite gate"
    )
    assert "var(--status-danger)" in body, (
        ".chip--danger text/border must use var(--status-danger) (the "
        "already-gated pair); a novel color needs its own composite gate"
    )


@pytest.mark.parametrize("theme", THEMES)
def test_editor_shell_error_passes_body_aa_and_consumes_the_danger_token(theme: str) -> None:
    """The editor shell's error line (`.ui-editor-error-row`, components.css) is the
    one error surface of the Built-in tools editor since M31 F4 L07b (the admin.css
    `.editor-error-banner` and its soft-fill pin are retired with the banner). It paints
    `var(--status-danger)` text on the editor header's ground (`--bg`, or the card
    `--surface`): gated here at body AA in both themes, and the rule is pinned to the token
    so a retune to a novel colour needs its own gate."""
    # The legacy `.form-actions .editor-error` selector went with the MCP editor's
    # hand-built header (M31 F5 L10): the shell's error row is the one declaration.
    for selector in (".ui-editor-error-row",):
        body = " ".join(_rule_bodies("components.css", selector))
        assert "color: var(--status-danger)" in body, (selector, body)
    palette = _palette(theme)
    for ground in ("bg", "surface"):
        ratio = contrast_ratio(palette["status_danger"], palette[ground])
        assert ratio >= 4.5, f"{theme}: status_danger on {ground} = {ratio:.2f}:1 (need >= 4.5:1)"


# ---------------------------------------------------------------------------
# Warning text on the soft-warning FILL (≥ 4.5:1) — both themes (M17 F5 L1)
# ---------------------------------------------------------------------------
#
# The SAME soft-fill-fg genre as the danger gate above (the F3-debrief
# composited-a11y pattern). The studio VRAM/model warning
# (studio.css `.studio-vram-warning`) paints --status-warning body-sm TEXT on
# a --status-warning-bg-soft rgba wash — a body-text pair (≥4.5:1). The wash is
# rgba (NOT mirrored), so the gate reconstructs the rendered fill by
# compositing --status-warning at the theme's soft alpha over each ladder
# surface, then asserts --status-warning text clears body AA on that fill.
#
# The light-theme fix (F5 L1): --status-warning #a16207 → #8f5606 (amber-700
# deepened) because #a16207 text landed ≈4.0–4.4:1 on the composited soft fill.
# This test fails loudly if a future retune lightens it back. Alpha per theme
# MUST track --status-warning-bg-soft in tokens.css (both themes 0.08); the
# soft wash tracks the base warning hue (matched family, like danger).
_STATUS_WARNING_SOFT_ALPHA = {"dark": 0.08, "light": 0.08}


@pytest.mark.parametrize("bg_key", ("bg", "surface", "surface_elevated"))
@pytest.mark.parametrize("theme", THEMES)
def test_warning_text_on_soft_fill_passes_body_aa(theme: str, bg_key: str) -> None:
    """`--status-warning` text ≥ 4.5:1 on the composited `--status-warning-bg-soft`
    fill, over bg AND surface AND surface-elevated, in BOTH themes (VRAM warning)."""
    palette = _palette(theme)
    warning = palette["status_warning"]
    alpha = _STATUS_WARNING_SOFT_ALPHA[theme]
    fill = _alpha_composite(warning, alpha, palette[bg_key])
    ratio = contrast_ratio(warning, fill)
    assert ratio >= 4.5, (
        f"{theme} warning-on-soft-fill fails body AA: status_warning on "
        f"status-warning-bg-soft over {bg_key} = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


# ---------------------------------------------------------------------------
# Indeterminate tool-switch thumb (≥ 3.0:1 UI) — both themes (M17 F5 L1)
# ---------------------------------------------------------------------------
#
# The Tools tab master (category) toggle (the tristate App.ui.toggle of
# App.ui.groupTile) renders a TRISTATE switch: at the partial-enabled state
# (0 < enabled < total) the track becomes --accent-translucent (components.css,
# `.ui-toggle-input:indeterminate`) and the thumb (::after) is solid
# --accent, parked at the halfway position. The thumb is a non-text UI mark, so
# it must clear the ≥3.0:1 UI/non-text threshold (WCAG 1.4.11) against its own
# translucent track — otherwise the halfway thumb vanishes into the track and
# the indeterminate state reads identical to "off". The track is an rgba wash,
# so the gate reconstructs it by compositing --accent at the theme's
# --accent-translucent alpha over --surface-elevated (the switch's own resting
# track color and the conservative — lowest-contrast — ladder surface behind
# it), then asserts the solid --accent thumb clears 3.0:1 on that fill.
@pytest.mark.parametrize("theme", THEMES)
def test_tool_switch_indeterminate_thumb_holds_ui_contrast(theme: str) -> None:
    """The indeterminate tool-switch thumb (--accent) ≥ 3.0:1 on the composited
    --accent-translucent track, both themes (stays visible at the halfway state)."""
    palette = _palette(theme)
    accent = palette["accent"]
    alpha = _ACCENT_TRANSLUCENT_ALPHA[theme]
    track = _alpha_composite(accent, alpha, palette["surface_elevated"])
    ratio = contrast_ratio(accent, track)
    assert ratio >= 3.0, (
        f"{theme} indeterminate tool-switch thumb fails UI AA: accent thumb on "
        f"accent-translucent track over surface-elevated = {ratio:.2f}:1 (need ≥ 3.0:1)"
    )


# ---------------------------------------------------------------------------
# CSS usage pins — deep-violet fills, control boundaries, thumbs (M25 F1 L3)
# ---------------------------------------------------------------------------
#
# The contrast gates above test TOKEN pairs, not CSS rules. A site that moved
# its background to --accent-fill but kept `color: var(--fg-on-accent)` would
# pass every gate while rendering failing text (dark #101114 on #7c3aed =
# 3.31:1). Each pin below asserts a rule block consumes the gated tokens, in the
# manner of test_editor_error_banner_consumes_the_gated_danger_pair.

_CSS_DIR = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css"
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)


def _rule_bodies(css_file: str, selector: str) -> list[str]:
    """Declaration bodies of every rule in ``css_file`` whose comma-separated
    selector list contains ``selector`` (whitespace-normalised, exact match)."""
    css = re.sub(r"/\*.*?\*/", "", (_CSS_DIR / css_file).read_text(encoding="utf-8"), flags=re.S)
    want = " ".join(selector.split())
    out = []
    for m in _RULE_RE.finditer(css):
        sels = [" ".join(x.split()) for x in m.group(1).split(",")]
        if want in sels:
            out.append(m.group(2))
    return out


# M31 F5 L07: the legacy iOS switch (.tool-enable-switch*) is gone. Its three pins (the
# on-track fill, the off-track border and the thumb) are the library toggle's own pins
# below: `.ui-toggle-input:checked + .ui-toggle-track` (--accent-fill), `.ui-toggle-track`
# (--control-border) and `.ui-toggle-track::after` (--control-thumb), so every pair stays
# gated.

# (css file, selector, tokens the block must consume, tokens it must NOT consume)
_FILL_SITES = [
    (
        "components.css",
        ".btn-filled-primary",
        ("--accent-fill", "--fg-on-accent-fill"),
        ("var(--accent)", "var(--fg-on-accent)"),
    ),
    ("components.css", ".btn-filled-primary:hover", ("--accent-fill-hover",), ("opacity:",)),
    ("components.css", ".checkbox-primary:checked", ("--accent-fill",), ("var(--accent)",)),
    (
        "components.css",
        ".checkbox-primary:checked::after",
        ("--fg-on-accent-fill",),
        ("var(--fg-on-accent)",),
    ),
    (
        "components.css",
        ".skip-link",
        ("--accent-fill", "--fg-on-accent-fill"),
        ("var(--accent)", "var(--fg-on-accent)"),
    ),
    # M31 F2 L08b: the studio pill (.tool-switch) is gone; the library toggle's
    # mixed (tristate master) track and thumb carry the indeterminate pin.
    (
        "components.css",
        ".ui-toggle-input:indeterminate + .ui-toggle-track",
        ("--accent-translucent",),
        ("var(--accent-fill)",),
    ),
    (
        "components.css",
        ".ui-toggle-input:indeterminate + .ui-toggle-track::after",
        ("var(--accent)",),
        ("var(--fg-on-accent)",),
    ),
    # M31 F6 L05c (A15): the message timestamp is --fg-faint at full strength (no extra
    # opacity), gated by test_message_timestamp_passes_body_aa.
    ("components.css", ".ui-message-attribution-ts", ("--fg-faint",), ("opacity",)),
    # Boundaries and thumbs (DD7).
    ("components.css", ".checkbox-primary", ("--control-border",), ("--border-strong",)),
    # M25 F1 L4: the indeterminate dash and the library toggle consume the same
    # gated pairs as the tick and the legacy switches.
    (
        "components.css",
        ".checkbox-primary:indeterminate",
        ("--accent-fill",),
        ("var(--accent)",),
    ),
    (
        "components.css",
        ".checkbox-primary:indeterminate::after",
        ("--fg-on-accent-fill",),
        ("var(--fg-on-accent)",),
    ),
    ("components.css", ".ui-toggle-track", ("--control-border",), ("--border-strong",)),
    ("components.css", ".ui-toggle-track::after", ("--control-thumb",), ("--fg-on-accent",)),
    (
        "components.css",
        ".ui-toggle-input:checked + .ui-toggle-track",
        ("--accent-fill",),
        ("var(--accent)",),
    ),
    # M25 F1 L4: a selected list-pane row's meta, neutral badges and counts use
    # --fg-secondary (gated by test_selected_row_meta_passes_body_aa).
    (
        "components.css",
        '.ui-list-pane-row[aria-current="page"] .ui-list-pane-meta',
        ("--fg-secondary",),
        ("--fg-muted",),
    ),
    (
        "components.css",
        '.ui-list-pane-row[aria-current="page"] .ui-list-pane-badge',
        ("--fg-secondary",),
        ("--fg-muted",),
    ),
    (
        "components.css",
        '.ui-list-pane-row[aria-current="page"] .ui-list-pane-count',
        ("--fg-secondary",),
        ("--fg-muted",),
    ),
    # Flight-end review: a selected BUTTON row carries aria-current="true"
    # (a link row keeps "page"); it gets the same gated inks.
    (
        "components.css",
        '.ui-list-pane-row[aria-current="true"] .ui-list-pane-meta',
        ("--fg-secondary",),
        ("--fg-muted",),
    ),
    (
        "components.css",
        '.ui-list-pane-row[aria-current="true"] .ui-list-pane-badge',
        ("--fg-secondary",),
        ("--fg-muted",),
    ),
    (
        "components.css",
        '.ui-list-pane-row[aria-current="true"] .ui-list-pane-count',
        ("--fg-secondary",),
        ("--fg-muted",),
    ),
]


@pytest.mark.parametrize(
    "css_file,selector,must,must_not",
    _FILL_SITES,
    ids=[f"{f}:{sel}" for f, sel, _, _ in _FILL_SITES],
)
def test_migrated_site_consumes_the_gated_tokens(
    css_file: str, selector: str, must: tuple, must_not: tuple
) -> None:
    """Every migrated fill / boundary / thumb rule consumes its gated tokens and
    none of the superseded ones (so a fill cannot move without its ink)."""
    bodies = _rule_bodies(css_file, selector)
    assert bodies, f"{selector!r} rule not found in {css_file}"
    body = " ".join(bodies)
    for tok in must:
        assert tok in body, f"{selector} must consume {tok}: {body.strip()}"
    for tok in must_not:
        assert tok not in body, f"{selector} must not use {tok}: {body.strip()}"


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
# Telemetry readout resting opacity (components.css .ui-telemetry { opacity }, the
# App.ui.telemetry control since M31 F6 L05c). Since M25 F4 L5 the readout sits in the
# composer's telemetry row, in the flow over the chat pane's --bg (no longer an absolute
# overlay); the rule and its 0.7 are unchanged, so the composite over --bg below still
# describes it.
_TELEMETRY_RESTING_OPACITY = 0.7


@pytest.mark.parametrize("bg_key", ("bg", "surface"))
@pytest.mark.parametrize("theme", THEMES)
def test_selected_row_meta_passes_body_aa(theme: str, bg_key: str) -> None:
    """M25 F1 L4: --fg-secondary (a selected list-pane row's meta, neutral badges
    and counts) >= 4.5:1 on the composited --accent-translucent wash over --bg and
    over --surface, both themes. --fg-muted fails three of these four cases, which
    is why the selected-row rule uses --fg-secondary."""
    palette = _palette(theme)
    fill = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_ALPHA[theme], palette[bg_key])
    ratio = contrast_ratio(palette["fg_secondary"], fill)
    assert ratio >= 4.5, (
        f"{theme} selected-row meta fails body AA: fg_secondary on accent-translucent "
        f"over {bg_key} = {ratio:.2f}:1 (need >= 4.5:1)"
    )


@pytest.mark.parametrize("theme", THEMES)
def test_checked_radio_option_pairs_pass_aa(theme: str) -> None:
    """M31 F4 L08a: the library radio card's checked state (the Appearance theme picker
    since the segmented toggle and its `.active` pin went): its label --fg >= 4.5:1 on the
    composited --accent-translucent wash over --surface, and the --accent border >= 3:1
    (non-text) against --surface, both themes. The rule must paint exactly those tokens."""
    palette = _palette(theme)
    wash = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_ALPHA[theme], palette["surface"])
    text = contrast_ratio(palette["fg"], wash)
    assert text >= 4.5, f"{theme} checked radio label = {text:.2f}:1 (need >= 4.5:1)"
    border = contrast_ratio(palette["accent"], palette["surface"])
    assert border >= 3.0, f"{theme} checked radio border = {border:.2f}:1 (need >= 3.0:1)"
    rule = " ".join(_rule_bodies("components.css", ".ui-radio-option.is-checked"))
    assert "border-color: var(--accent)" in rule, rule
    assert "background: var(--accent-translucent)" in rule, rule
    assert "color: var(--fg)" in " ".join(_rule_bodies("components.css", ".ui-radio-label")), rule


@pytest.mark.parametrize("theme", THEMES)
def test_rail_label_pairs_pass_body_aa(theme: str) -> None:
    """M25 F2 L6: every text-on-surface pair the rail paints clears body AA (the
    10px labels are small text): --fg-secondary on --surface at rest, --fg on
    --surface-elevated on hover, and --fg on the composited --accent-translucent
    wash over --surface when current."""
    palette = _palette(theme)
    wash = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_ALPHA[theme], palette["surface"])
    pairs = {
        "rest (fg_secondary on surface)": (palette["fg_secondary"], palette["surface"]),
        "hover (fg on surface_elevated)": (palette["fg"], palette["surface_elevated"]),
        "current (fg on wash over surface)": (palette["fg"], wash),
    }
    for name, (ink, ground) in pairs.items():
        ratio = contrast_ratio(ink, ground)
        assert ratio >= 4.5, f"{theme} rail {name} = {ratio:.2f}:1 (need >= 4.5:1)"


def test_rail_rules_consume_the_gated_pairs() -> None:
    """The rail CSS paints exactly the pairs the test above gates (a rule that
    drifts to an ungated token fails here)."""
    rest = " ".join(_rule_bodies("components.css", ".ui-rail-item"))
    assert "background: transparent" in rest and "color: var(--fg-secondary)" in rest, rest
    assert "background: var(--surface)" in " ".join(_rule_bodies("components.css", ".ui-rail"))
    hover = " ".join(_rule_bodies("components.css", ".ui-rail-item:hover"))
    assert "background: var(--surface-elevated)" in hover and "color: var(--fg)" in hover, hover
    cur = " ".join(_rule_bodies("components.css", '.ui-rail-item[aria-current="page"]'))
    assert "background: var(--accent-translucent)" in cur and "color: var(--fg)" in cur, cur


def _sidebar_ground(theme: str) -> str:
    """The aside's ground: --sidebar-bg, which tokens.css aliases to --surface in
    both theme blocks (asserted here, so a retune of the alias fails loudly)."""
    alias = parse_tokens_css_theme_blocks()[theme]["--sidebar-bg"]
    assert alias == "var(--surface)", f"{theme} --sidebar-bg is {alias!r}; re-gate the aside pairs"
    return _palette(theme)["surface"]


@pytest.mark.parametrize("theme", THEMES)
def test_list_pane_caption_pairs_pass_body_aa(theme: str) -> None:
    """M25 F3 L1: the list pane's new 11px text -- the title count, the intro and
    the empty-group line -- is --fg-muted on the aside (--sidebar-bg), and clears
    body AA in both themes (no --fg-secondary fallback was needed)."""
    ground = _sidebar_ground(theme)
    ratio = contrast_ratio(_palette(theme)["fg_muted"], ground)
    assert ratio >= 4.5, f"{theme} list-pane caption text = {ratio:.2f}:1 (need >= 4.5:1)"


def test_list_pane_caption_rules_consume_the_gated_pair() -> None:
    for selector in (".ui-list-pane-total", ".ui-list-pane-intro", ".ui-list-pane-group-empty"):
        body = " ".join(_rule_bodies("components.css", selector))
        assert "color: var(--fg-muted)" in body, f"{selector}: {body.strip()}"
        assert "font-size: var(--font-size-caption)" in body, f"{selector}: {body.strip()}"


def test_editor_header_caption_rules_consume_the_gated_pairs() -> None:
    """M25 F3 L3 (DD2): the item header's 11px captions sit on the detail
    pane's --bg -- the "Agents" breadcrumb in --fg-muted (gated by
    test_body_text_passes_aa on bg) and the "Unsaved changes" caption in
    --status-warning (gated by test_status_text_passes_body_aa on bg)."""
    crumb = " ".join(_rule_bodies("components.css", ".editor-breadcrumb"))
    assert "color: var(--fg-muted)" in crumb, crumb
    assert "font-size: var(--font-size-caption)" in crumb, crumb
    # M25 F3 L4b: the breadcrumb's root link inherits that gated ink (no accent
    # text, so no new text pair) and shows the standard --accent focus ring,
    # which test_large_or_ui_passes_aa gates at 3:1 on --bg.
    link = " ".join(_rule_bodies("components.css", ".editor-breadcrumb-link"))
    assert "color: inherit" in link, link
    assert "font-size" not in link and "color: var(" not in link, link
    # Flight-end review (WCAG 1.4.1): underlined at rest, so the link is not
    # told from the plain "Library" / "Settings" text by colour alone.
    assert "text-decoration: underline" in link and "text-decoration: none" not in link, link
    ring = " ".join(_rule_bodies("components.css", ".editor-breadcrumb-link:focus-visible"))
    assert "outline: 2px solid var(--accent)" in ring, ring
    unsaved = " ".join(_rule_bodies("components.css", ".form-actions .editor-unsaved"))
    assert "color: var(--status-warning)" in unsaved, unsaved
    assert "font-size: var(--font-size-caption)" in unsaved, unsaved
    for theme in THEMES:
        palette = _palette(theme)
        assert contrast_ratio(palette["fg_muted"], palette["bg"]) >= 4.5, theme
        assert contrast_ratio(palette["status_warning"], palette["bg"]) >= 4.5, theme


@pytest.mark.parametrize("theme", THEMES)
def test_nav_groups_pairs_pass_body_aa(theme: str) -> None:
    """M25 F3 L1: every text-on-ground pair App.ui.navGroups paints on the aside
    clears body AA (12px items, 11px captions): --fg-secondary at rest, --fg on
    --surface-elevated on hover, --fg on the composited --accent-translucent wash
    when selected, --fg-muted captions, and the --fg heading."""
    palette = _palette(theme)
    ground = _sidebar_ground(theme)
    wash = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_ALPHA[theme], ground)
    pairs = {
        "rest (fg_secondary on sidebar)": (palette["fg_secondary"], ground),
        "hover (fg on surface_elevated)": (palette["fg"], palette["surface_elevated"]),
        "selected (fg on wash over sidebar)": (palette["fg"], wash),
        "caption (fg_tertiary on sidebar)": (palette["fg_tertiary"], ground),
        "heading (fg on sidebar)": (palette["fg"], ground),
    }
    for name, (ink, bg) in pairs.items():
        ratio = contrast_ratio(ink, bg)
        assert ratio >= 4.5, f"{theme} navGroups {name} = {ratio:.2f}:1 (need >= 4.5:1)"


@pytest.mark.parametrize("theme", THEMES)
def test_section_label_eyebrow_pairs_pass_body_aa(theme: str) -> None:
    """M25 F6 L4 (DD13): the eyebrow-with-a-rule label (10px semibold uppercase) is
    --fg-tertiary on --bg (editor pages), --surface (the aside) and
    --surface-elevated, all above 4.5:1. The rule itself is decorative."""
    palette = _palette(theme)
    for ground in ("bg", "surface", "surface_elevated"):
        ratio = contrast_ratio(palette["fg_tertiary"], palette[ground])
        assert ratio >= 4.5, f"{theme} section label on {ground} = {ratio:.2f}:1 (need >= 4.5:1)"


def test_section_label_rules_consume_the_gated_pair() -> None:
    for selector in (".section-title", ".ui-list-pane-caption", ".ui-nav-groups-caption"):
        body = " ".join(_rule_bodies("components.css", selector))
        assert "color: var(--fg-tertiary)" in body, f"{selector}: {body.strip()}"
        assert "text-transform: uppercase" in body, f"{selector}: {body.strip()}"


def test_nav_groups_rules_consume_the_gated_pairs() -> None:
    rest = " ".join(_rule_bodies("components.css", ".ui-nav-groups-item"))
    assert "color: var(--fg-secondary)" in rest, rest
    hover = " ".join(_rule_bodies("components.css", ".ui-nav-groups-item:hover"))
    assert "background: var(--surface-elevated)" in hover and "color: var(--fg)" in hover, hover
    cur = " ".join(_rule_bodies("components.css", '.ui-nav-groups-item[aria-current="page"]'))
    assert "background: var(--accent-translucent)" in cur and "color: var(--fg)" in cur, cur
    cap = " ".join(_rule_bodies("components.css", ".ui-nav-groups-caption"))
    assert "color: var(--fg-tertiary)" in cap, cap
    heading = " ".join(_rule_bodies("components.css", ".ui-nav-groups-heading"))
    assert "color: var(--fg)" in heading, heading


# --accent-translucent-hover's own alphas (tokens.css: 0.16 dark, 0.13 light);
# .ui-tool-tile--selected paints it, replacing the tile's --surface.
_ACCENT_TRANSLUCENT_HOVER_ALPHA = {"dark": 0.16, "light": 0.13}


@pytest.mark.parametrize("theme", THEMES)
def test_settings_tile_pairs_pass_body_aa(theme: str) -> None:
    """M25 F3 L7 (the Providers tiles retired in sortie 02; Built-in tools keeps
    the same tile vocabulary): a Settings tile paints the intro in --fg-muted on
    --bg, the name in --fg and the secondary lines in --fg-secondary on the
    tile's --surface, and, on the open tile, the same inks on the composited
    --accent-translucent-hover wash. The wash replaces --surface,
    so it is composited over both --bg and --surface (the worse ground gates).
    Tightest pair: --fg-secondary on the wash over --surface, 5.49:1 dark and
    6.01:1 light. Every pair clears body AA (4.5:1) in both themes. The badge
    pairs are gated by the --badge-ink-* tests."""
    palette = _palette(theme)
    alpha = _ACCENT_TRANSLUCENT_HOVER_ALPHA[theme]
    pairs = {
        "intro (fg_muted on bg)": (palette["fg_muted"], palette["bg"]),
        "name (fg on surface)": (palette["fg"], palette["surface"]),
        "secondary line (fg_secondary on surface)": (palette["fg_secondary"], palette["surface"]),
    }
    for ground in ("bg", "surface"):
        wash = _alpha_composite(palette["accent"], alpha, palette[ground])
        pairs[f"active name (fg on wash over {ground})"] = (palette["fg"], wash)
        pairs[f"active secondary line (fg_secondary on wash over {ground})"] = (
            palette["fg_secondary"],
            wash,
        )
    for name, (ink, ground_color) in pairs.items():
        ratio = contrast_ratio(ink, ground_color)
        assert ratio >= 4.5, f"{theme} settings tile {name} = {ratio:.2f}:1 (need >= 4.5:1)"


def test_settings_tool_tile_rules_consume_the_gated_pairs() -> None:
    """The Built-in tools tile CSS (the library toolTile in components.css since
    M31 F4 L06) paints exactly the pairs the test above gates, the name link's
    focus ring is the standard 2px --accent ring, and the open tile's wash is the
    --accent-translucent-hover token. (The dead .settings-intro pin and the
    admin.css tile pins went with their rules.)"""
    link = " ".join(_rule_bodies("components.css", ".ui-tool-tile-link"))
    assert "color: var(--fg)" in link, link
    assert "calc(100%" not in link, link  # DD3: no badge reserve; the title row lays it out
    assert "flex: 1 1 auto" in link and "min-width: 0" in link, link
    row = " ".join(_rule_bodies("components.css", ".ui-tool-tile-row"))
    assert "display: flex" in row, row
    ring = " ".join(_rule_bodies("components.css", ".ui-tool-tile-link:focus-visible"))
    assert "outline: 2px solid var(--accent)" in ring, ring
    desc = " ".join(_rule_bodies("components.css", ".ui-tool-tile-desc"))
    assert "color: var(--fg-secondary)" in desc, desc
    active = " ".join(_rule_bodies("components.css", ".ui-tool-tile--selected"))
    assert "background-color: var(--accent-translucent-hover)" in active, active


@pytest.mark.parametrize("theme", THEMES)
def test_search_list_pairs_pass_body_aa(theme: str) -> None:
    """M25 F4 L1 (AC8, A10): App.ui.searchList sits on a dialog card
    (--surface). Its active row paints --accent-translucent-hover (not audited as
    a background before this leg) with an --accent border. Gated, composited
    over --surface: the --fg label, the --fg-secondary description and the
    active row's --fg-secondary meta at body AA, and the --accent border at 3:1
    against both the wash and the card (non-text). At rest: the --fg-secondary
    description, the --fg-muted meta and the --fg-muted group caption on
    --surface.

    --fg-muted on the active wash is 3.85:1 dark and 3.92:1 light, below body
    AA, which is why the description is --fg-secondary throughout (as reference
    spec 5.6 draws it) and the meta switches to --fg-secondary on the active row
    (the list-pane selected-row precedent, A24)."""
    palette = _palette(theme)
    card = palette["surface"]
    wash = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_HOVER_ALPHA[theme], card)
    pairs = {
        "active label (fg on wash)": (palette["fg"], wash, 4.5),
        "active description (fg_secondary on wash)": (palette["fg_secondary"], wash, 4.5),
        "active meta (fg_secondary on wash)": (palette["fg_secondary"], wash, 4.5),
        "active border (accent vs wash)": (palette["accent"], wash, 3.0),
        "active border (accent vs card)": (palette["accent"], card, 3.0),
        "rest label (fg on card)": (palette["fg"], card, 4.5),
        "rest description (fg_secondary on card)": (palette["fg_secondary"], card, 4.5),
        "rest meta (fg_muted on card)": (palette["fg_muted"], card, 4.5),
        "group caption (fg_muted on card)": (palette["fg_muted"], card, 4.5),
    }
    for name, (ink, ground, need) in pairs.items():
        ratio = contrast_ratio(ink, ground)
        assert ratio >= need, f"{theme} searchList {name} = {ratio:.2f}:1 (need >= {need}:1)"


def test_search_list_rules_consume_the_gated_pairs() -> None:
    """The searchList and chooser CSS paint exactly the pairs gated above, on the
    dialog card's --surface."""
    card = " ".join(_rule_bodies("components.css", ".modal-dialog"))
    assert "background-color: var(--surface)" in card, card
    active = " ".join(_rule_bodies("components.css", '.ui-search-list-row[aria-selected="true"]'))
    assert "background: var(--accent-translucent-hover)" in active, active
    assert "border-color: var(--accent)" in active, active
    rest = " ".join(_rule_bodies("components.css", ".ui-search-list-row"))
    assert "border: 1px solid transparent" in rest and "background: transparent" in rest, rest
    label = " ".join(_rule_bodies("components.css", ".ui-search-list-label"))
    assert "color: var(--fg)" in label, label
    desc = " ".join(_rule_bodies("components.css", ".ui-search-list-description"))
    assert "color: var(--fg-secondary)" in desc, desc
    meta = " ".join(_rule_bodies("components.css", ".ui-search-list-meta"))
    assert "color: var(--fg-muted)" in meta, meta
    active_meta = " ".join(
        _rule_bodies(
            "components.css", '.ui-search-list-row[aria-selected="true"] .ui-search-list-meta'
        )
    )
    assert "color: var(--fg-secondary)" in active_meta, active_meta
    cap = " ".join(_rule_bodies("components.css", ".ui-search-list-caption"))
    assert "color: var(--fg-muted)" in cap, cap
    footer = " ".join(_rule_bodies("components.css", ".modal-dialog-chooser .modal-dialog-footer"))
    assert "color: var(--fg-muted)" in footer, footer
    assert "font-size: var(--font-size-caption)" in footer, footer


@pytest.mark.parametrize("theme", THEMES)
def test_chats_row_pairs_pass_body_aa(theme: str) -> None:
    """M25 F4 L1 (AC13, DD5): a listPane 'chats' row on the aside
    (--sidebar-bg). Its 11px time is --fg-muted and its 11px meta (the agent
    name) --fg-secondary at rest; on the selected row's --accent-translucent
    wash both are --fg-secondary, reusing Flight 1's A24 resolution (--fg-muted
    on the light selected wash is 4.43:1 over --bg and 4.25:1 over --surface).
    Also gated: the --fg title on each ground, the hover ground
    (--surface-elevated), the armed --status-danger title and the action's
    --fg-secondary icon (3:1 non-text)."""
    palette = _palette(theme)
    aside = _sidebar_ground(theme)
    selected = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_ALPHA[theme], aside)
    hover = palette["surface_elevated"]
    pairs = {
        "time (fg_muted on aside)": (palette["fg_muted"], aside, 4.5),
        "meta (fg_secondary on aside)": (palette["fg_secondary"], aside, 4.5),
        "title (fg on aside)": (palette["fg"], aside, 4.5),
        "selected time (fg_secondary on wash)": (palette["fg_secondary"], selected, 4.5),
        "selected meta (fg_secondary on wash)": (palette["fg_secondary"], selected, 4.5),
        "selected title (fg on wash)": (palette["fg"], selected, 4.5),
        "hover time (fg_muted on surface_elevated)": (palette["fg_muted"], hover, 4.5),
        "hover meta (fg_secondary on surface_elevated)": (palette["fg_secondary"], hover, 4.5),
        "armed title (status_danger on aside)": (palette["status_danger"], aside, 4.5),
        "armed title (status_danger on wash)": (palette["status_danger"], selected, 4.5),
        "action icon (fg_secondary on hover)": (palette["fg_secondary"], hover, 3.0),
        "action icon (fg_secondary on wash)": (palette["fg_secondary"], selected, 3.0),
    }
    for name, (ink, ground, need) in pairs.items():
        ratio = contrast_ratio(ink, ground)
        assert ratio >= need, f"{theme} chats row {name} = {ratio:.2f}:1 (need >= {need}:1)"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_chats_row_activity_pairs_pass_ui_aa(theme: str) -> None:
    """M31 F6 L10b: the row activity marks (the working ring and the new-reply dot,
    both --accent, non-text) hold 3:1 on the aside ground, the selected wash and the
    hover ground, in both themes."""
    palette = _palette(theme)
    aside = _sidebar_ground(theme)
    selected = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_ALPHA[theme], aside)
    hover = palette["surface_elevated"]
    for name, ground in (("aside", aside), ("selected wash", selected), ("hover", hover)):
        ratio = contrast_ratio(palette["accent"], ground)
        assert ratio >= 3.0, f"{theme} row activity mark (accent on {name}) = {ratio:.2f}:1"


def test_chats_row_activity_rules_consume_the_gated_pair() -> None:
    for selector in (
        ".ui-list-pane-activity--working::before",
        ".ui-list-pane-activity--new::before",
    ):
        body = " ".join(_rule_bodies("components.css", selector))
        assert "var(--accent)" in body, (selector, body)
    working = " ".join(_rule_bodies("components.css", ".ui-list-pane-activity--working::before"))
    assert "animation:" in working, working
    reduced = _reduced_motion_rules("components.css")
    assert ".ui-list-pane-activity--working::before { animation: none; }" in reduced, reduced


def _reduced_motion_rules(css_file: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", (_CSS_DIR / css_file).read_text(encoding="utf-8"), flags=re.S)
    blocks = re.findall(
        r"@media \(prefers-reduced-motion: reduce\) \{((?:[^{}]*\{[^{}]*\})*)\s*\}", css
    )
    return " ".join(" ".join(b.split()) for b in blocks)


def test_chats_row_rules_consume_the_gated_pairs() -> None:
    time = " ".join(_rule_bodies("components.css", ".ui-list-pane-time"))
    assert "color: var(--fg-muted)" in time and "font-size: var(--font-size-caption)" in time, time
    meta = " ".join(_rule_bodies("components.css", ".ui-list-pane-style-chats .ui-list-pane-meta"))
    assert "color: var(--fg-secondary)" in meta and "font-size: var(--font-size-caption)" in meta, (
        meta
    )
    for current in ('"page"', '"true"'):
        sel = " ".join(
            _rule_bodies(
                "components.css", f".ui-list-pane-row[aria-current={current}] .ui-list-pane-time"
            )
        )
        assert "color: var(--fg-secondary)" in sel, (current, sel)
    hover = " ".join(_rule_bodies("components.css", ".ui-list-pane-row:hover"))
    assert "background: var(--surface-elevated)" in hover, hover
    action = " ".join(_rule_bodies("components.css", ".ui-list-pane-action"))
    assert "color: var(--fg-secondary)" in action and "display: none" in action, action
    armed = " ".join(
        _rule_bodies(
            "components.css", ".ui-list-pane-list > li.confirm-delete [data-confirm-title]"
        )
    )
    assert "color: var(--status-danger)" in armed, armed


def _forced_colors_rules(css_file: str) -> str:
    """The text of every ``@media (forced-colors: active)`` block in ``css_file``
    (comments stripped; a block's rules hold no nested braces)."""
    css = re.sub(r"/\*.*?\*/", "", (_CSS_DIR / css_file).read_text(encoding="utf-8"), flags=re.S)
    blocks = re.findall(r"@media \(forced-colors: active\) \{((?:[^{}]*\{[^{}]*\})*)\s*\}", css)
    assert blocks, f"no forced-colors block in {css_file}"
    return "\n".join(blocks)


@pytest.mark.parametrize(
    ("css_file", "selector", "declaration"),
    [
        ("components.css", ".ui-tool-tile--selected", "outline: 1px solid Highlight"),
        ("components.css", ".ui-list-pane-activity--new::before", "background: CanvasText"),
        ("components.css", ".ui-list-pane-activity--working::before", "border-color: CanvasText"),
        ("components.css", ".ui-tool-tile--selected", "border-color: Highlight"),
        (
            "components.css",
            '.ui-list-pane-row[aria-current="true"]',
            "border: 1px solid Highlight",
        ),
        (
            "components.css",
            '.ui-list-pane-row[aria-current="page"]',
            "border: 1px solid Highlight",
        ),
        # rowStyle rows: the rest border hidden, the selected one Highlight at
        # the rowStyle selected rule's specificity (which beat the rule above).
        ("components.css", ".ui-list-pane-styled .ui-list-pane-row", "border-color: Canvas"),
        (
            "components.css",
            '.ui-list-pane-styled .ui-list-pane-row[aria-current="page"]',
            "border-color: Highlight",
        ),
        (
            "components.css",
            '.ui-list-pane-styled .ui-list-pane-row[aria-current="true"]',
            "border-color: Highlight",
        ),
        # The searchList active row (M25 F4 L1): the rest border hidden, the
        # active one Highlight.
        ("components.css", ".ui-search-list-row", "border-color: Canvas"),
        (
            "components.css",
            '.ui-search-list-row[aria-selected="true"]',
            "border-color: Highlight",
        ),
    ],
)
def test_forced_colors_keep_a_non_colour_selected_cue(
    css_file: str, selector: str, declaration: str
) -> None:
    """Flight-end review (WCAG 1.4.11): forced colours drop the selected wash and
    force the accent border, so each selected state names a system-colour cue
    inside the file's forced-colors block (a components-layer rule)."""
    block = _forced_colors_rules(css_file)
    want = " ".join(selector.split())
    for m in _RULE_RE.finditer(block):
        sels = [" ".join(x.split()) for x in m.group(1).split(",")]
        if want in sels and declaration in m.group(2):
            return
    raise AssertionError(f"{css_file}: no forced-colors rule {selector!r} {{ {declaration} }}")


_TOKEN_BADGE_KINDS = (
    "anthropic",
    "anthropic-plan",
    "anthropic-plan-token",
    "local",
    "mock",
    "ollama",
    "openai",
    "openai-compatible",
    "openrouter",
    "remote",
    "unknown",
)


@pytest.mark.parametrize("kind", _TOKEN_BADGE_KINDS)
def test_badge_kind_rules_consume_the_gated_pair(kind: str) -> None:
    """Each token-backed `.badge--<kind>` rule uses its --badge-<kind> fill with
    its --badge-ink-<kind> ink (the pair test_badge_ink_passes_body_aa gates)."""
    body = " ".join(_rule_bodies("components.css", f".badge--{kind}"))
    assert f"background: var(--badge-{kind})" in body, body
    assert f"color: var(--badge-ink-{kind})" in body, body


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
    """F04 L02: the telemetry readout's (App.ui.telemetry) --fg-secondary value, ghosted
    at the resting opacity (0.7) over --bg, stays ≥ 3.0:1 (the annotation
    floor), both themes.

    The telemetry readout is DELIBERATELY de-emphasized at rest (opacity 0.7);
    hover/focus-within lifts it to opacity 1.0, where --fg-secondary on --bg is
    fully body-AA via the fg-ladder sweep. This gate pins the RESTING ghost to
    the same ≥3.0 annotation floor:
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


@pytest.mark.parametrize("bg_key", ("bg", "surface"))
@pytest.mark.parametrize("theme", THEMES)
def test_message_timestamp_passes_body_aa(theme: str, bg_key: str) -> None:
    """M31 F6 L05c (A15): the attribution timestamp (.ui-message-attribution-ts) is --fg-faint
    at full strength, >= 4.5:1 on the chat pane's --bg (and on --surface), both themes. It
    used to carry an extra opacity 0.75, which put the pair under body AA."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette["fg_faint"], palette[bg_key])
    assert ratio >= 4.5, (
        f"{theme} message timestamp fails body AA: fg_faint on {bg_key} = {ratio:.2f}:1 "
        f"(need >= 4.5:1)"
    )


@pytest.mark.parametrize("theme", THEMES)
def test_composer_text_pairs_pass_body_aa(theme: str) -> None:
    """M25 F4 L5 (reference spec 5.5): the composer box is --surface, and every
    text on it clears body AA, both themes: the textarea's text (--fg), its
    placeholder and the toolbar's 11px model id (--fg-muted). The pairs are
    also in the fg-ladder sweep (test_body_text_passes_aa); this names the
    consumer, so a retune that moves the box off --surface or the model id off
    --fg-muted has a gate that says what broke."""
    palette = _palette(theme)
    pairs = {
        "text (fg on surface)": (palette["fg"], palette["surface"]),
        "placeholder and model id (fg_muted on surface)": (palette["fg_muted"], palette["surface"]),
    }
    for label, (fg, bg) in pairs.items():
        ratio = contrast_ratio(fg, bg)
        assert ratio >= 4.5, f"{theme} composer {label} = {ratio:.2f}:1 (need >= 4.5:1)"


@pytest.mark.parametrize("theme", THEMES)
def test_drawer_text_pairs_pass_body_aa(theme: str) -> None:
    """M25 F4 L6 (reference spec 5.7, AC16): the agent drawer is --surface, and
    every text on it clears body AA, both themes: the name, the facts' values
    and "What it can use" (--fg); the description and the default/deleted note
    (--fg-secondary); the facts' <dt>, the group labels, the counts and "None"
    (--fg-muted, 11-12px). The ladder sweep covers the pairs too; this names
    the consumer, so a retune that moves the drawer off --surface or a role
    off its token has a gate that says what broke."""
    palette = _palette(theme)
    pairs = {
        "name and values (fg on surface)": (palette["fg"], palette["surface"]),
        "description and note (fg_secondary on surface)": (
            palette["fg_secondary"],
            palette["surface"],
        ),
        "dt, group labels, counts and None (fg_muted on surface)": (
            palette["fg_muted"],
            palette["surface"],
        ),
    }
    for label, (fg, bg) in pairs.items():
        ratio = contrast_ratio(fg, bg)
        assert ratio >= 4.5, f"{theme} drawer {label} = {ratio:.2f}:1 (need >= 4.5:1)"


# ---------------------------------------------------------------------------
# Badge × ink (≥ 4.5:1) — per-badge ink, both themes (M17 F3 L4)
# ---------------------------------------------------------------------------

# Every badge maps to (fill token, ink token). The fill is looked up per
# theme, so each pair is asserted against BOTH themes. This is the "fix THEN
# gate" contract from the flight DD "Badges": the fix is the per-badge ink;
# this test is the gate.
_BADGE_INK_PAIRS = (
    ("ollama", "badge_ollama", "badge_ink_ollama"),
    ("openai-compatible", "badge_openai_compatible", "badge_ink_openai_compatible"),
    ("openai", "badge_openai", "badge_ink_openai"),
    ("anthropic", "badge_anthropic", "badge_ink_anthropic"),
    ("anthropic-plan", "badge_anthropic_plan", "badge_ink_anthropic_plan"),
    ("anthropic-plan-token", "badge_anthropic_plan_token", "badge_ink_anthropic_plan_token"),
    ("openrouter", "badge_openrouter", "badge_ink_openrouter"),
    ("mock", "badge_mock", "badge_ink_mock"),
    ("unknown", "badge_unknown", "badge_ink_unknown"),
    # local / remote (M31 F5 HAT) — Library MCP row transport badges.
    ("local", "badge_local", "badge_ink_local"),
    ("remote", "badge_remote", "badge_ink_remote"),
)


@pytest.mark.parametrize("badge,fill_key,ink_key", _BADGE_INK_PAIRS)
@pytest.mark.parametrize("theme", THEMES)
def test_badge_ink_passes_body_aa(theme: str, badge: str, fill_key: str, ink_key: str) -> None:
    """Every badge's ink clears body AA (≥ 4.5:1) on its fill, both themes.

    Fills are theme-stable; the fill is resolved per theme and the ink is
    theme-stable.
    """
    palette = _palette(theme)
    ratio = contrast_ratio(palette[ink_key], palette[fill_key])
    assert ratio >= 4.5, (
        f"{theme} badge fails body AA: {badge} ink on fill = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


# ---------------------------------------------------------------------------
# Retired exceptions
# ---------------------------------------------------------------------------


# (No deliberate exceptions remain: squawk 0206 retired the --fg-faint band and
# the dark --accent-fill-on-elevated band; both now sit under the plain gates.)


# ---------------------------------------------------------------------------
# SC2 completeness net — every fg-role token is audited or exempt (M17 F7 L2)
# ---------------------------------------------------------------------------
#
# The parametrized gates above audit a CURATED set of fg-role tokens. SC2
# ("all palette tokens audited for contrast, with documented exceptions") needs
# a machine-checked guarantee that the curated set stays COMPLETE — that a new
# fg / accent / status / code-block token added to tokens.css cannot slip in
# unaudited and undocumented.
#
# The hole this closes: the mirror-sync guard
# (``test_ui_guards.py::test_design_token_mirror_in_sync``) is strictly
# mirror→CSS — it iterates the ``design_tokens.py`` mirror and checks each key
# exists in ``tokens.css``. A literal-hex token added to ``tokens.css`` but NOT
# to the mirror satisfies BOTH nets silently: it is absent from the mirror (so
# mirror-sync never looks at it) AND absent from the a11y parametrizations
# (which read their values from that same mirror). This is exactly the "did we
# forget to audit a token" hole SC2 must close.
#
# So this net enumerates from ``tokens.css`` (the SOURCE OF TRUTH) via
# ``parse_tokens_css_theme_blocks()`` — NOT from the mirror. For every token in
# the fg-role families it asserts the token is either:
#
#   - GATED — a literal-hex value that is present in the ``design_tokens.py``
#     mirror (DARK & LIGHT, the a11y suite's value source) AND referenced by
#     its mirror-key in this module (so a contrast assertion actually exercises
#     it); OR
#   - EXEMPT — named in ``_CONTRAST_EXEMPT`` below with a rationale.
#
# A fg-role token that is neither gated nor exempt fails LOUDLY, naming the
# token. Probe-verified (M17 F7 L2): planting an ungated literal-hex
# ``--fg-probe`` in tokens.css makes this test fail naming ``--fg-probe``.

# The color families where a standalone or composited fg-on-bg contrast pair is
# meaningful — the enumeration scope. STRUCTURAL families are deliberately OUT
# OF SCOPE (they carry no standalone fg-on-bg ratio, so "contrast completeness"
# does not apply to them) and are documented here rather than enumerated:
#
#   - ``--border-*`` / ``--border`` — hairlines; non-text separators. Their
#     3:1 UI-contrast where load-bearing (e.g. focus rings) is a separate
#     concern from text/large-text contrast and not this suite's remit.
#   - ``--nav-*`` / ``--sidebar-*`` — ``var()`` indirections onto already-gated
#     ladder values (nav-fg → fg-secondary, nav-bg → surface); auditing the
#     indirection would double-count the ladder it resolves to.
#   - ``--surface-*`` (incl. the standalone ``--surface-tool``) / ``--bg`` —
#     BACKGROUNDS, not foregrounds; they appear in the gates only as the
#     ``bg_key`` half of a pair, never as a fg needing its own ratio.
#   - ``--badge-*`` / ``--badge-ink-*`` — gated by their OWN dedicated suite
#     (``test_badge_ink_passes_body_aa``, every fill × ink both themes); a
#     completeness net over them would duplicate that gate.
#   - geometry / motion tokens — no color content.
#   - ``--control-*`` IS in scope (added M25 F1 L3): --control-border and
#     --control-thumb are non-text control-boundary / toggle-thumb colours that
#     must clear the 3:1 UI threshold, so the net requires each to be gated.
_FG_ROLE_PREFIXES = ("--fg", "--accent", "--status", "--code-block", "--control")

# Matches a full literal-hex value (``#rgb`` … ``#rrggbbaa``). rgba()/var()
# values do NOT match — an rgba wash has no flat WCAG ratio, so it can only be
# accounted-for via ``_CONTRAST_EXEMPT``, never "gated".
_HEX_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}$")

# Documented non-text / composited exclusions among the fg-role prefixes.
# These are rgba WASH tokens: the flat WCAG formula cannot read their alpha, so
# they have no standalone contrast ratio. Where text or non-text marks sit ON a
# wash, the rendered opaque fill is reconstructed with ``_alpha_composite`` and
# gated at the CONSUMER site (cited per entry) — the wash token itself stays
# exempt. Each entry's base hue is an already-gated literal-hex token.
_CONTRAST_EXEMPT: dict[str, str] = {
    "--accent-translucent": (
        "rgba wash of the gated --accent hue; no standalone ratio. Composited-"
        "gated at consumers: test_tinted_user_bubble_text_passes_body_aa, "
        "test_tool_switch_indeterminate_thumb_holds_ui_contrast."
    ),
    "--accent-translucent-hover": (
        "rgba wash of the gated --accent hue (alphas 0.16 dark, 0.13 light); the "
        "open tile's fill (.ui-tool-tile--selected), replacing --surface. Composited-"
        "gated over both --bg and --surface at its consumer by "
        "test_settings_tile_pairs_pass_body_aa."
    ),
    "--status-danger-bg-soft": (
        "rgba wash of the gated --status-danger hue; composited-gated by "
        "test_danger_text_on_soft_fill_passes_body_aa (and its usage pins "
        "test_cap_chip_no_tools_/test_editor_error_banner_consumes_the_gated_"
        "danger_pair)."
    ),
    "--status-warning-bg-soft": (
        "rgba wash of the gated --status-warning hue; composited-gated by "
        "test_warning_text_on_soft_fill_passes_body_aa."
    ),
    "--status-warning-bg-soft-2": (
        "rgba wash of the gated --status-warning hue (denser variant); a fill "
        "only, no text sits directly on it — the base hue is the gated "
        "--status-warning."
    ),
    "--status-warning-border": (
        "rgba hairline of the gated --status-warning hue; a non-text UI border, "
        "no standalone text ratio."
    ),
}


def _referenced_in_this_module(mirror_key: str) -> bool:
    """True if ``mirror_key`` (snake_case) appears as a quoted string literal in
    this module's source — i.e. a contrast assertion above actually reads it.

    Ties the completeness net's notion of "gated" to a real reference in
    ``test_design_tokens_a11y.py`` (not merely presence in the mirror), so a
    token mirrored-but-never-asserted still fails the net."""
    src = Path(__file__).read_text(encoding="utf-8")
    return re.search(rf"""["']{re.escape(mirror_key)}["']""", src) is not None


def test_sc2_every_fg_role_token_is_gated_or_exempt() -> None:
    """SC2 completeness: every fg-role token in ``tokens.css`` is either GATED
    (literal-hex, mirrored in DARK & LIGHT, and referenced by a contrast
    assertion here) or EXEMPT (documented in ``_CONTRAST_EXEMPT``).

    Enumerates from ``tokens.css`` (source of truth) via
    ``parse_tokens_css_theme_blocks`` — NOT from the mirror — so a literal-hex
    token added to the CSS but not the mirror fails LOUDLY naming the token
    (the mirror→CSS-only mirror-sync guard cannot see it). Both theme blocks
    are checked; a token present in only one theme surfaces as a per-theme
    failure line."""
    blocks = parse_tokens_css_theme_blocks()

    failures: list[str] = []
    for theme in ("dark", "light"):
        for name, value in sorted(blocks[theme].items()):
            if not name.startswith(_FG_ROLE_PREFIXES):
                continue
            if name in _CONTRAST_EXEMPT:
                continue  # documented non-text / composited exclusion
            mirror_key = name[2:].replace("-", "_")
            mirror = DARK if theme == "dark" else LIGHT
            gated = (
                _HEX_LITERAL.match(value) is not None
                and mirror_key in mirror
                and _referenced_in_this_module(mirror_key)
            )
            if not gated:
                reason = (
                    "non-literal value (no flat WCAG ratio) and not in _CONTRAST_EXEMPT"
                    if _HEX_LITERAL.match(value) is None
                    else "literal-hex but absent from the design_tokens.py mirror "
                    "and/or unreferenced by any contrast assertion in this module"
                )
                failures.append(f"  [{theme}] {name} = {value!r}: {reason}")

    if failures:
        raise AssertionError(
            "SC2 contrast-completeness: fg-role token(s) in tokens.css are "
            "neither GATED nor EXEMPT.\n"
            "Either add a contrast gate for the token (and mirror it in "
            "tests/browser/design_tokens.py) OR add it to _CONTRAST_EXEMPT with "
            "a rationale:\n" + "\n".join(failures)
        )


# ---------------------------------------------------------------------------
# App.ui.radioGroup option cards (M28 F2 L2) — both themes, 4.5:1
# ---------------------------------------------------------------------------
# The checked card paints --accent-translucent over --surface; its description
# (--fg-secondary: --fg-muted fails on the dark checked fill) and label (--fg)
# sit on that composite. The unchecked card is plain --surface.


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("fg_key", ("fg", "fg_secondary"))
def test_radio_card_text_on_checked_fill_passes_body_aa(theme: str, fg_key: str) -> None:
    palette = _palette(theme)
    fill = _alpha_composite(palette["accent"], _ACCENT_TRANSLUCENT_ALPHA[theme], palette["surface"])
    ratio = contrast_ratio(palette[fg_key], fill)
    assert ratio >= 4.5, f"{theme} radio card {fg_key} on checked fill = {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_radio_card_description_on_surface_passes_body_aa(theme: str) -> None:
    palette = _palette(theme)
    ratio = contrast_ratio(palette["fg_secondary"], palette["surface"])
    assert ratio >= 4.5, f"{theme} radio description on surface = {ratio:.2f}:1"


def test_armed_confirm_button_consumes_the_gated_on_danger_pair() -> None:
    """`button.confirm-delete` (the App.ui.confirm banner in components.css, M31 F1 L4)
    paints `var(--fg-on-danger)` on `var(--status-danger)`: the pair gated by
    ``test_text_on_color`` in both themes. The rule must cover the hover and
    focus-visible states too, so no variant's own hover rule undoes the armed look."""
    css = (
        Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css/components.css"
    ).read_text(encoding="utf-8")
    m = re.search(
        r"button\.confirm-delete,\s*button\.confirm-delete:hover,\s*"
        r"button\.confirm-delete:focus-visible\s*\{([^}]*)\}",
        css,
    )
    assert m, "the armed-button rule (with :hover and :focus-visible) was not found"
    assert "background: var(--status-danger)" in m.group(1)
    assert "color: var(--fg-on-danger)" in m.group(1)


def test_chip_warning_consumes_the_gated_warning_pair() -> None:
    """`.chip--warning` (App.ui.chip warning tone, M31 F3 L03b) must paint
    `var(--status-warning)` text and border on the `var(--status-warning-bg-soft)` fill:
    the EXACT pair gated by ``test_warning_text_on_soft_fill_passes_body_aa``. A novel
    pair needs its own composite gate."""
    import re
    from pathlib import Path

    css = (
        Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css/components.css"
    ).read_text(encoding="utf-8")
    m = re.search(r"\.chip--warning\s*\{([^}]*)\}", css)
    assert m, ".chip--warning rule not found in components.css"
    body = m.group(1)
    assert "background: var(--status-warning-bg-soft)" in body
    assert "color: var(--status-warning)" in body
    assert "border-color: var(--status-warning)" in body


def test_status_text_tone_consumes_the_gated_status_text_tokens() -> None:
    """`.ui-status--tone` (App.ui.status textTone, M31 F3 L03b) colours text with
    `--status-danger` / `--status-warning` only: the pairs gated on bg and surface by
    ``test_status_text_passes_body_aa`` (and danger on elevated by its own test)."""
    import re
    from pathlib import Path

    css = (
        Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css/components.css"
    ).read_text(encoding="utf-8")
    rules = re.findall(r"\.ui-status--tone\[data-state=\"(\w+)\"\][^{]*\{([^}]*)\}", css)
    assert dict(rules).keys() == {"danger", "warning"}, rules
    for state, body in rules:
        assert body.strip() == f"color: var(--status-{state});", (state, body)


# ---------------------------------------------------------------------------
# Disabled buttons (M31 F4 L04c, B14, ledger row 37)
# ---------------------------------------------------------------------------
#
# A disabled button's label used to be the enabled colour at opacity 0.4, which fell below
# 3:1 on the dark surfaces. WCAG exempts disabled controls; 3:1 is the operator's approved
# readability target. The label token is opaque, so the flat formula applies. The checkbox
# and the toggle track keep their opacity (a control state, not a label; out of B14's scope).

_DISABLED_BUTTON_SELECTORS = (
    ".btn-outlined-primary:disabled",
    ".btn-filled-primary:disabled",
    ".btn-ghost:disabled",
    ".btn-muted-destructive:disabled",
    ".ui-progress-cancel:disabled",
)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("bg_key", ["bg", "surface", "surface_elevated", "btn_disabled_bg"])
def test_disabled_button_label_reaches_3_to_1(theme: str, bg_key: str) -> None:
    palette = _palette(theme)
    ratio = contrast_ratio(palette["btn_disabled_fg"], palette[bg_key])
    assert ratio >= 3.0, f"{theme} disabled label on {bg_key} = {ratio:.2f}:1 (need >= 3.0)"


@pytest.mark.parametrize("theme", THEMES)
def test_disabled_button_differs_from_the_enabled_look(theme: str) -> None:
    palette = _palette(theme)
    assert palette["btn_disabled_fg"] != palette["fg"]
    assert palette["btn_disabled_bg"] != palette["accent_fill"]


@pytest.mark.parametrize("selector", _DISABLED_BUTTON_SELECTORS)
def test_disabled_button_sites_use_tokens_not_opacity(selector: str) -> None:
    body = " ".join(_rule_bodies("components.css", selector))
    assert body, selector
    assert "var(--btn-disabled-fg)" in body, body
    assert "opacity" not in body, body
    assert "cursor: not-allowed" in body, body


def test_filled_disabled_button_consumes_the_fill_tokens() -> None:
    body = " ".join(_rule_bodies("components.css", ".btn-filled-primary:disabled"))
    assert "var(--btn-disabled-bg)" in body and "var(--btn-disabled-border)" in body, body


def test_save_button_disabled_state_has_no_opacity() -> None:
    body = " ".join(_rule_bodies("components.css", ".save-btn[disabled]"))
    assert "opacity" not in body and "cursor: not-allowed" in body, body
    assert not _rule_bodies("components.css", ".save-btn:not([disabled])")


def test_non_button_disabled_sites_keep_opacity() -> None:
    for sel in (".checkbox-primary:disabled", ".ui-toggle-input:disabled + .ui-toggle-track"):
        assert "opacity: 0.4" in " ".join(_rule_bodies("components.css", sel)), sel


def test_disabled_buttons_use_graytext_in_forced_colors() -> None:
    css = (_CSS_DIR / "components.css").read_text(encoding="utf-8")
    block = css[css.index("@media (forced-colors: active)") :]
    for sel in _DISABLED_BUTTON_SELECTORS:
        assert sel in block, sel
    assert "color: GrayText; border-color: GrayText;" in block

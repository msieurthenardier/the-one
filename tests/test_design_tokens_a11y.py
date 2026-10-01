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
of Mission 17 Flight 03 Leg 04: every provider / tool badge
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
        # (session-delete on session-item, .list-item-delete). NOTE (M18 F3
        # L1 A3 fix): .chip-remove no longer uses this token at rest — it
        # was retuned to --status-danger (body AA on the composited chip
        # fill; see test_chip_remove_danger_on_chip_fill_passes_body_aa
        # below), so it's no longer an example consumer of this UI-threshold
        # pair.
        "status_danger_muted",
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
        # CSS site. (M17 F04 L02: the chat .msg.user bubble is a tint, see
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
    (light gated, dark band-pinned) — it cannot share this two-surface list.

    NOTE: `accent_fill_hover` vs surfaces is deliberately NOT gated: it is below
    3.0 in dark, and no state-bearing control uses the hover fill (checked
    checkboxes and on toggles never take it; only the transient primary-button
    hover does, and the button label carries the meaning)."""
    palette = _palette(theme)
    ratio = contrast_ratio(palette["accent_fill"], palette[bg_key])
    assert ratio >= 3.0, f"{theme}: accent_fill on {bg_key} = {ratio:.2f}:1 (need ≥ 3.0:1)"


def test_accent_fill_vs_surface_elevated_light_passes_ui_aa() -> None:
    """Light `--accent-fill` ≥ 3.0:1 against surface-elevated (6.46:1)."""
    ratio = contrast_ratio(LIGHT["accent_fill"], LIGHT["surface_elevated"])
    assert ratio >= 3.0, f"light: accent_fill on surface_elevated = {ratio:.2f}:1"


def test_accent_fill_vs_surface_elevated_dark_band_exception() -> None:
    """DELIBERATE EXCEPTION (M25 F1 L3, DD7) — dark `--accent-fill` (#7c3aed) on
    `--surface-elevated` is 2.95:1, a hair under the 3.0 UI threshold. Band-pinned
    2.9 ≤ r < 3.0 so a retune that drifts either way fails loudly.

    Rationale: the checked/on state is carried by the WHITE tick or thumb
    (`--fg-on-accent-fill`, 5.70:1 against the fill), so the fill-to-surface edge
    is not the only cue. The same band also covers `.chip-attached` on elevated
    tiles: it carries text, and white on `accent_fill` is 5.70:1, so the text is
    fine. Retuning the fill lighter would break the approved deep-violet look; the
    operator approved the hexes."""
    ratio = contrast_ratio(DARK["accent_fill"], DARK["surface_elevated"])
    assert 2.9 <= ratio < 3.0, (
        f"dark accent_fill on surface_elevated drifted out of the deliberate-exception "
        f"band: {ratio:.2f}:1 (band: 2.9 ≤ r < 3.0)"
    )


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
# Danger glyph on the chip's accent-translucent FILL (≥ 4.5:1) — both themes
# (M18 F3 L1 A3 fix; review-polish regression gate, obs 1)
# ---------------------------------------------------------------------------

# --accent-translucent is a low-alpha rgba wash (base color --accent) that
# .chip (components.css) uses as its fill; .chip-remove sits on top of it.
# Because the wash is an rgba it is NOT mirrored in design_tokens.py (see
# that module's "Deliberately NOT mirrored" note); the gate reconstructs the
# rendered fill by compositing --accent at the theme's translucent alpha over
# each ladder surface, then asserts --status-danger text clears body AA on
# that fill.
#
# This gates `.chip-remove` (components.css, the `.chat-attachment.chip`
# remove glyph in the chat attach UI): M18 F3 L1's contrast fix retuned its
# resting color from --status-danger-muted (≈4.14:1 in light theme, failed
# body AA) to --status-danger. This test is the durable regression net so a
# future --status-danger / --accent-translucent retune can't silently
# regress that fix.
#
# Alpha per theme MUST track --accent-translucent in tokens.css.
_ACCENT_TRANSLUCENT_ALPHA = {"dark": 0.10, "light": 0.08}


@pytest.mark.parametrize("bg_key", ("bg", "surface", "surface_elevated"))
@pytest.mark.parametrize("theme", THEMES)
def test_chip_remove_danger_on_chip_fill_passes_body_aa(theme: str, bg_key: str) -> None:
    """`--status-danger` glyph text ≥ 4.5:1 on the composited `--accent-translucent`
    chip fill, over bg AND surface AND surface-elevated, in BOTH themes."""
    palette = _palette(theme)
    danger = palette["status_danger"]
    alpha = _ACCENT_TRANSLUCENT_ALPHA[theme]
    fill = _alpha_composite(palette["accent"], alpha, palette[bg_key])
    ratio = contrast_ratio(danger, fill)
    assert ratio >= 4.5, (
        f"{theme} chip-remove danger fails body AA: status_danger on "
        f"accent-translucent over {bg_key} = {ratio:.2f}:1 (need ≥ 4.5:1)"
    )


def test_cap_chip_no_tools_consumes_the_gated_danger_pair() -> None:
    """`.cap-chip-no-tools` (admin.css) must paint `var(--status-danger)` text on
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

    admin_css = (
        Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css/admin.css"
    )
    css = admin_css.read_text(encoding="utf-8")
    # Isolate the `.cap-chip-no-tools { ... }` declaration block.
    m = re.search(r"\.cap-chip-no-tools\s*\{([^}]*)\}", css)
    assert m, ".cap-chip-no-tools rule not found in admin.css"
    body = m.group(1)
    assert "var(--status-danger-bg-soft)" in body, (
        ".cap-chip-no-tools must fill with var(--status-danger-bg-soft) (the "
        "already-gated soft pair); a novel fill needs its own composite gate"
    )
    assert "var(--status-danger)" in body, (
        ".cap-chip-no-tools text/border must use var(--status-danger) (the "
        "already-gated pair); a novel color needs its own composite gate"
    )


def test_editor_error_banner_consumes_the_gated_danger_pair() -> None:
    """`.editor-error-banner` (admin.css) must paint `var(--status-danger)` text on
    the `var(--status-danger-bg-soft)` fill — the EXACT pair already gated by
    ``test_danger_text_on_soft_fill_passes_body_aa`` above.

    M17 F6 L2 pins the usage (per the flight's composite-a11y DD: the danger-on-
    soft pair is gated ONCE at the token level, not re-gated per surface — no new
    ``_alpha_composite`` math). This is the sibling of
    ``test_cap_chip_no_tools_consumes_the_gated_danger_pair``: the tools-editor's
    prominent 422 / model-level error banner is the second admin danger-on-soft
    surface. This source-grep guard fails loudly if a future retune points the
    banner at a NOVEL fg/bg triple — a signal that a fresh composite gate is
    warranted for whatever new pair it introduces."""
    import re
    from pathlib import Path

    admin_css = (
        Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css/admin.css"
    )
    css = admin_css.read_text(encoding="utf-8")
    # Isolate the `.area-admin .editor-error-banner { ... }` declaration block
    # (the base rule, not the `[hidden]` / ` svg` / `-text` companions).
    m = re.search(r"\.area-admin\s+\.editor-error-banner\s*\{([^}]*)\}", css)
    assert m, ".editor-error-banner rule not found in admin.css"
    body = m.group(1)
    assert "var(--status-danger-bg-soft)" in body, (
        ".editor-error-banner must fill with var(--status-danger-bg-soft) (the "
        "already-gated soft pair); a novel fill needs its own composite gate"
    )
    assert "var(--status-danger)" in body, (
        ".editor-error-banner text/border must use var(--status-danger) (the "
        "already-gated pair); a novel color needs its own composite gate"
    )


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
# The studio tools-tab master (category) toggle renders a TRISTATE switch: at
# the partial-enabled state (0 < enabled < total) the track becomes
# --accent-translucent (studio.css:66) and the thumb (::after) is solid
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


_ON_TRACK = (
    '.area-{0} .tool-enable-switch input[type="checkbox"]:checked + .tool-enable-switch-track'
)

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
    (
        "admin.css",
        ".area-admin .admin-theme-option.active",
        ("--accent-fill", "--fg-on-accent-fill"),
        ("var(--accent)", "var(--fg-on-accent)"),
    ),
    (
        "admin.css",
        _ON_TRACK.format("admin"),
        ("--accent-fill",),
        ("var(--accent)",),
    ),
    (
        "admin.css",
        _ON_TRACK.format("studio"),
        ("--accent-fill",),
        ("var(--accent)",),
    ),
    (
        "studio.css",
        ".area-studio .tool-toggle:checked + .tool-switch",
        ("--accent-fill",),
        ("var(--accent)",),
    ),
    (
        "studio.css",
        ".area-studio .tool-toggle:checked + .tool-switch::after",
        ("--control-thumb",),
        ("var(--fg-on-accent)",),
    ),
    (
        "studio.css",
        ".area-studio .mcp-attach-chip-list .chip-attached",
        ("--accent-fill", "--fg-on-accent-fill"),
        ("var(--accent)", "var(--fg-on-accent)", "white"),
    ),
    (
        "chat.css",
        ".area-chat .msg-pending-approval-approve",
        ("--accent-fill", "--fg-on-accent-fill"),
        ("var(--accent)", "var(--fg-on-accent)"),
    ),
    # Boundaries and thumbs (DD7).
    ("components.css", ".checkbox-primary", ("--control-border",), ("--border-strong",)),
    (
        "admin.css",
        ".area-admin .tool-enable-switch-track",
        ("--control-border",),
        ("--border-strong",),
    ),
    (
        "admin.css",
        ".area-admin .tool-enable-switch-track::after",
        ("--control-thumb",),
        ("--fg-on-accent",),
    ),
    ("studio.css", ".area-studio .tool-switch", ("--control-border",), ("--surface-elevated",)),
    ("studio.css", ".area-studio .tool-switch::after", ("--control-thumb",), ("--fg-tertiary",)),
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
# Telemetry overlay resting opacity (chat.css .telemetry-overlay { opacity }).
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


@pytest.mark.parametrize("kind", ("approved", "dismissed"))
def test_badge_semantic_kinds_sit_on_the_gated_ladder(kind: str) -> None:
    """`.badge--approved` / `.badge--dismissed` paint --fg / --fg-secondary on
    --surface-elevated (both swept by test_body_text_passes_aa), never a novel pair."""
    body = " ".join(_rule_bodies("components.css", f".badge--{kind}"))
    assert "var(--surface-elevated)" in body, body
    assert ("var(--fg)" if kind == "approved" else "var(--fg-secondary)") in body, body


_TOKEN_BADGE_KINDS = (
    "anthropic",
    "anthropic-plan",
    "connectors",
    "execution",
    "filesystem",
    "mock",
    "ollama",
    "openai",
    "openai-compatible",
    "openrouter",
    "unknown",
    "web",
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
    ("anthropic-plan", "badge_anthropic_plan", "badge_ink_anthropic_plan"),
    ("openrouter", "badge_openrouter", "badge_ink_openrouter"),
    ("mock", "badge_mock", "badge_ink_mock"),
    ("unknown", "badge_unknown", "badge_ink_unknown"),
    ("filesystem", "badge_filesystem", "badge_ink_filesystem"),
    ("execution", "badge_execution", "badge_ink_execution"),
    ("web", "badge_web", "badge_ink_web"),
    # connectors (squawk 0032) — admin Tools grid category badge.
    ("connectors", "badge_connectors", "badge_ink_connectors"),
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
        "rgba hover wash of the gated --accent hue; a transient hover fill, no "
        "text pair of its own (its resting sibling --accent-translucent carries "
        "the gated consumer pairs)."
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

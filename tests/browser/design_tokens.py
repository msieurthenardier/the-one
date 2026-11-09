"""Design tokens — Python mirror of static/css/tokens.css theme blocks.

Single source of truth for tests that need to reference token values.
Used by:

- ``tests/test_design_tokens_a11y.py`` (WCAG AA contrast pairs; imports
  ``DARK`` / ``LIGHT``)
- ``tests/test_ui_guards.py`` (``test_design_token_mirror_in_sync`` —
  parses the top-level theme blocks of ``tokens.css`` and asserts every
  mirror value below matches the CSS definition, hex-normalized)
- ``tests/browser/test_visual_snapshots.py`` (theme-toggle helpers — no
  direct token reads but the module is imported as the canonical place
  for token names if a future snapshot needs them)
- ``tests/test_token_definitions.py`` reads token names directly from
  ``tokens.css`` (regex), NOT from this module — that test is a
  contract-vs-CSS check, deliberately independent of this Python mirror.

Mirror scope (v3, Mission 17 Flight 02 Leg 01): every token whose CSS
value is a **literal hex color** in its theme block. Deliberately NOT
mirrored:

- ``var()``-indirection tokens (nav rail, sidebar) — they resolve to
  already-mirrored ladder values; mirroring the indirection would
  duplicate data without adding audit surface.
- ``rgba()`` wash tokens (``--*-translucent``, ``--status-*-bg-soft``,
  ``--status-warning-border``) — alpha composites are not auditable with
  the flat WCAG formula; their base colors are mirrored.
- Badge fill + ink tokens (``--badge-*`` / ``--badge-ink-*``) — mirrored
  as of M17 F3 L4: badge×ink contrast is now GATED in
  ``test_design_tokens_a11y.py`` (every fill × its per-badge ink clears
  body AA in both themes), so the fill and ink hexes must live here for
  the audit to read them. ``--badge-ink-*`` is theme-stable; the fills
  are brand-stable (the tool-category kinds were retired at M31 F6 L09a).
- Geometry/motion tokens (no color content).
- ``shell_chrome_bg`` (mirrored pre-v3) — the shell chrome was retired
  (neutralized in Leg 1, structure dismantled + tokens deleted in Leg 2b);
  the topbar/sidebar text pairs are covered by the fg-ladder × surface
  audits.

If ``tokens.css`` values change (e.g., a future leg retunes a colour),
update this file in lockstep — the mirror-sync guard in
``tests/test_ui_guards.py`` fails loudly if you don't. The brittleness
is intentional: the hardcoded mirror is part of the contract that tests
pin.

Note: keys use ``snake_case`` (``fg_secondary``) rather than the CSS
hyphenated form (``--fg-secondary``) so they're valid Python identifiers
when used as ``DARK["fg_secondary"]`` in test parametrisations. The
guard converts ``snake_case`` → ``--kebab-case`` when matching.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Dark theme — mirrors the tokens.css [data-theme="dark"] top-level block.
# Lifted-charcoal neutral ladder; violet-400 accent.
# ---------------------------------------------------------------------------

DARK: dict[str, str] = {
    # surfaces
    "bg": "#101114",
    "surface": "#17181c",
    "surface_elevated": "#1c1d22",
    "surface_tool": "#1c1d22",
    # borders
    "border": "#26272c",
    "border_hover": "#33343b",
    "border_strong": "#4a4b55",
    # text ladder — fg through fg_faint all clear body AA (>= 4.5:1) on
    # bg, surface, AND surface-elevated, strictly ordered by contrast
    # (squawk 0206; see test_design_tokens_a11y.py).
    "fg": "#ededf0",
    "fg_secondary": "#adafb7",
    "fg_tertiary": "#9a9ca4",
    "fg_muted": "#8f9199",
    "fg_faint": "#868890",
    "fg_on_accent": "#101114",
    # fg_on_danger is dark ink in dark theme — the bright #f87171 danger
    # fill reads 6.83:1 under dark ink; white would fail body AA.
    "fg_on_danger": "#101114",
    "fg_tool_msg": "#9a9ca4",
    # accent — violet-400 (brand continuity per mission constraint);
    # accent_api is badge-tier cyan (chat user-vs-API differentiation).
    "accent": "#a78bfa",
    # Deep-violet solid control fills + control boundary/thumb (M25 F1 L3).
    "accent_fill": "#7f3eef",
    "accent_fill_hover": "#6d28d9",
    "fg_on_accent_fill": "#ffffff",
    "control_border": "#6e717a",
    "btn_disabled_fg": "#7d7f88",
    "btn_disabled_bg": "#2a2b31",
    "btn_disabled_border": "#3a3b43",
    "control_thumb": "#ffffff",
    "accent_api": "#22d3ee",
    # status — Tailwind-400 family; all >= 4.5:1 on bg/surface.
    "status_success": "#4ade80",
    "status_warning": "#fbbf24",
    "status_danger": "#f87171",
    "status_danger_muted": "#d98c8c",
    # code well — one step darker than bg, primary fg (16.6:1).
    "code_block_bg": "#0c0d10",
    "code_block_fg": "#ededf0",
    # provider / tool badge FILLS — brand-stable (same in both
    # themes for providers; tool fills diverge in light — see LIGHT below).
    "badge_ollama": "#2ecc71",
    "badge_openai_compatible": "#d4a800",
    "badge_openai": "#4a9eff",
    "badge_anthropic": "#9b59b6",
    # anthropic-plan (M19 F01 L03) — brand terracotta; dark ink 5.76:1.
    "badge_anthropic_plan": "#cc785c",
    "badge_anthropic_plan_token": "#cc785c",
    "badge_openrouter": "#7c3aed",
    "badge_mock": "#888888",
    "badge_unknown": "#888888",
    "badge_local": "#6f93a8",
    "badge_remote": "#4338ca",
    # per-badge INK (M17 F3 L4) — theme-stable; light fills → dark ink,
    # dark fills → white ink. Each fill × its ink is gated ≥4.5 both themes.
    "badge_ink_ollama": "#101114",
    "badge_ink_openai_compatible": "#101114",
    "badge_ink_openai": "#101114",
    "badge_ink_anthropic": "#ffffff",
    "badge_ink_anthropic_plan": "#101114",
    "badge_ink_anthropic_plan_token": "#101114",
    "badge_ink_openrouter": "#ffffff",
    "badge_ink_mock": "#101114",
    "badge_ink_unknown": "#101114",
    "badge_ink_local": "#101114",
    "badge_ink_remote": "#ffffff",
    # chart palette (M35 F1 L1) — gated >= 3.0:1 in test_design_tokens_a11y.py
    "chart_1": "#a78bfa",
    "chart_2": "#22d3ee",
    "chart_3": "#fbbf24",
    "chart_4": "#f472b6",
    "chart_5": "#4ade80",
    "chart_6": "#fb923c",
    "chart_7": "#60a5fa",
    "chart_8": "#94a3b8",
    "chart_ref": "#fbbf24",
}


# ---------------------------------------------------------------------------
# Light theme — mirrors the tokens.css [data-theme="light"] top-level block.
# White/near-white zinc ladder; violet-700 accent. Designed on its own
# merits, not flipped from dark.
# ---------------------------------------------------------------------------

LIGHT: dict[str, str] = {
    # surfaces
    "bg": "#ffffff",
    "surface": "#fafafa",
    "surface_elevated": "#f4f4f5",
    "surface_tool": "#f4f4f5",
    # borders
    "border": "#e4e4e7",
    "border_hover": "#d4d4d8",
    "border_strong": "#a1a1aa",
    # text ladder — fg through fg_faint all clear body AA (>= 4.5:1) on
    # bg, surface, AND surface-elevated, strictly ordered by contrast
    # (squawk 0206; see test_design_tokens_a11y.py).
    "fg": "#18181b",
    "fg_secondary": "#52525b",
    "fg_tertiary": "#5f5f68",
    "fg_muted": "#65656e",
    "fg_faint": "#6d6d76",
    "fg_on_accent": "#ffffff",
    "fg_on_danger": "#ffffff",
    "fg_tool_msg": "#5f5f68",
    # accent — violet-700 (white-on-accent 7.10:1); accent_api cyan-700
    # badge-tier (white-on-accent-api 5.36:1, accent-api-on-bg 5.36:1).
    "accent": "#6d28d9",
    # Deep-violet solid control fills + control boundary/thumb (M25 F1 L3).
    "accent_fill": "#6d28d9",
    "accent_fill_hover": "#5b21b6",
    "fg_on_accent_fill": "#ffffff",
    "control_border": "#868690",
    "btn_disabled_fg": "#767680",
    "btn_disabled_bg": "#e4e4e7",
    "btn_disabled_border": "#d4d4d8",
    "control_thumb": "#ffffff",
    "accent_api": "#0e7490",
    # status — deep 600/700 family; all >= 4.5:1 on bg/surface.
    "status_success": "#15803d",
    # amber-700 deepened from #a16207 (M17 F5 L1): #a16207 warning text failed
    # body AA on the composited --status-warning-bg-soft fill; see the warning
    # comment in tokens.css [data-theme="light"] and the warning soft-fill gate.
    "status_warning": "#8f5606",
    # red-700 (M17 F3 fix): red-600 #dc2626 failed body AA on the soft-fill
    # composite; see the danger comment in tokens.css [data-theme="light"].
    "status_danger": "#b91c1c",
    "status_danger_muted": "#af4d4d",
    # code well — pale zinc + primary ink (16.1:1).
    "code_block_bg": "#f4f4f5",
    "code_block_fg": "#18181b",
    # provider / transport badge FILLS — brand-stable (same hex as dark).
    "badge_ollama": "#2ecc71",
    "badge_openai_compatible": "#d4a800",
    "badge_openai": "#4a9eff",
    "badge_anthropic": "#9b59b6",
    # anthropic-plan — brand-stable terracotta (same hex as dark).
    "badge_anthropic_plan": "#cc785c",
    "badge_anthropic_plan_token": "#cc785c",
    "badge_openrouter": "#7c3aed",
    "badge_mock": "#888888",
    "badge_unknown": "#888888",
    "badge_local": "#6f93a8",
    "badge_remote": "#4338ca",
    # per-badge INK (M17 F3 L4) — theme-stable; identical to the dark block.
    "badge_ink_ollama": "#101114",
    "badge_ink_openai_compatible": "#101114",
    "badge_ink_openai": "#101114",
    "badge_ink_anthropic": "#ffffff",
    "badge_ink_anthropic_plan": "#101114",
    "badge_ink_anthropic_plan_token": "#101114",
    "badge_ink_openrouter": "#ffffff",
    "badge_ink_mock": "#101114",
    "badge_ink_unknown": "#101114",
    "badge_ink_local": "#101114",
    "badge_ink_remote": "#ffffff",
    # chart palette (M35 F1 L1) — 700-weight family, >= 4.7:1 on bg/surface/bubble
    "chart_1": "#6d28d9",
    "chart_2": "#0e7490",
    "chart_3": "#b45309",
    "chart_4": "#be185d",
    "chart_5": "#15803d",
    "chart_6": "#c2410c",
    "chart_7": "#1d4ed8",
    "chart_8": "#475569",
    "chart_ref": "#b45309",
}

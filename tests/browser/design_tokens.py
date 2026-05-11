"""Design tokens — Python mirror of static/css/tokens.css blocks.

Single source of truth for tests that need to reference token values.
Used by:

- ``tests/test_design_tokens_a11y.py`` (WCAG AA contrast pairs; imports
  ``DARK`` / ``LIGHT``)
- ``tests/browser/test_visual_snapshots.py`` (theme-toggle helpers — no
  direct token reads but the module is imported as the canonical place
  for token names if a future snapshot needs them)
- ``tests/test_token_definitions.py`` reads token names directly from
  ``tokens.css`` (regex), NOT from this module — that test is a
  contract-vs-CSS check, deliberately independent of this Python mirror.

If ``tokens.css`` values change (e.g., a future leg retunes a colour),
update this file in lockstep. The brittleness is intentional: the
hardcoded mirror is part of the contract that tests pin.

Note: keys use ``snake_case`` (``fg_secondary``) rather than the CSS
hyphenated form (``--fg-secondary``) so they're valid Python identifiers
when used as ``DARK["fg_secondary"]`` in test parametrisations.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Dark theme — mirrors tokens.css [data-theme="dark"] block (lines ~22-87).
# ---------------------------------------------------------------------------

DARK: dict[str, str] = {
    "bg": "#0a0a0a",
    "surface": "#1a1a1a",
    "fg": "#e0e0e0",
    "fg_secondary": "#888888",
    "fg_tertiary": "#666666",
    "fg_muted": "#a8a8a8",
    "fg_on_accent": "#000000",
    # fg_on_danger is BLACK in dark — white-on-#ff4a4a only reads at 3.32:1
    # (fails body AA); black reads at 6.33:1.  Retuned in leg 07.
    "fg_on_danger": "#000000",
    # accent retuned cyan-400 → violet-400 in flight 01 leg 02 (GleepGlorp
    # rebrand). Dark uses the lighter violet shade so accent-on-bg passes
    # large/UI AA against #0a0a0a (≈9.5:1).
    "accent": "#a78bfa",
    # accent_api shifted from violet (#7c4dff) → cyan-400 (the retired
    # primary) so the user-vs-API chat message differentiation survives
    # the primary-accent retune. Used as background for `.msg.user.api`.
    "accent_api": "#22d3ee",
    "status_success": "#2ecc71",
    "status_warning": "#f5a623",
    "status_danger": "#ff4a4a",
    "status_danger_muted": "#d56363",
}


# ---------------------------------------------------------------------------
# Light theme — mirrors tokens.css [data-theme="light"] block (lines ~89-156).
# ---------------------------------------------------------------------------

LIGHT: dict[str, str] = {
    "bg": "#fafbfc",
    "surface": "#ffffff",
    "fg": "#0f172a",
    "fg_secondary": "#334155",
    "fg_tertiary": "#475569",
    "fg_muted": "#64748b",
    "fg_on_accent": "#ffffff",
    "fg_on_danger": "#ffffff",
    # accent retuned cyan-700 → violet-700 in flight 01 leg 02 (GleepGlorp
    # rebrand). Light uses the deeper violet shade so fg_on_accent (#ffffff)
    # passes body AA against the accent fill (≈7.10:1).
    "accent": "#6d28d9",
    # accent_api shifted from violet (#6d28d9) → cyan-700 (the retired
    # primary) so the user-vs-API chat message differentiation survives
    # the primary-accent retune. Used as background for `.msg.user.api`.
    "accent_api": "#0e7490",
    # success retuned green-600 → green-700 (~4.84:1 on bg/surface).
    "status_success": "#15803d",
    # warning retuned yellow-600 → yellow-700 (~4.75:1 on bg/surface).
    "status_warning": "#a16207",
    "status_danger": "#dc2626",
    "status_danger_muted": "#a85050",
}

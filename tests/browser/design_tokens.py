"""Per-theme design-token mirror for browser-side assertions.

Mirrors the values in the_one/interfaces/web/static/css/tokens.css.
When tokens.css changes, this file must be updated in lockstep.
"""

LIGHT_TOKENS = {
    "--bg": "#f8f8f6",
    "--surface": "#ffffff",
    "--surface-2": "#fbfbf9",
    "--hairline": "rgba(15, 17, 21, 0.07)",
    "--hairline-strong": "rgba(15, 17, 21, 0.12)",
    "--fg": "#16181d",
    "--fg-mute": "#6a6e76",
    "--fg-faint": "#878d96",
    "--fg-on-danger": "#ffffff",
    "--accent": "#3358c0",
    "--accent-tint": "rgba(51, 88, 192, 0.10)",
    "--accent-tint-strong": "rgba(51, 88, 192, 0.18)",
    "--success": "#2f9c6a",
    "--warn": "#c98a2b",
    "--danger": "#c5443d",
}

DARK_TOKENS = {
    "--bg": "#0a0c10",
    "--surface": "#14171c",
    "--surface-2": "#181c22",
    "--hairline": "rgba(255, 255, 255, 0.08)",
    "--hairline-strong": "rgba(255, 255, 255, 0.14)",
    "--fg": "#e6e7ea",
    "--fg-mute": "#9aa1ac",
    "--fg-faint": "#6a7280",
    "--fg-on-danger": "#0a0c10",
    "--accent": "#a78bfa",
    "--accent-tint": "rgba(167, 139, 250, 0.10)",
    "--accent-tint-strong": "rgba(167, 139, 250, 0.18)",
    "--success": "#4ade80",
    "--warn": "#f5c97a",
    "--danger": "#f87171",
}

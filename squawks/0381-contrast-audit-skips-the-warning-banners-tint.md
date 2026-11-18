# Squawk 0381: The contrast audit does not check warning text on the warning banner's own tint

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: —

## Report
`App.ui.banner` with tone `warning` paints `--status-warning` text on a gradient that starts, at the left edge where the text begins, with the 12% wash `--status-warning-bg-soft-2`. The contrast audit checks that text on the plain surfaces and on the 8% wash (`--status-warning-bg-soft`), but not on the 12% wash. Its exemption list says of `--status-warning-bg-soft-2`: "a fill only, no text sits directly on it", which is not true for the banner.

Nothing fails today. Sortie 19's accessibility reviewer computed the pair by hand, wash composited over each of the three surfaces: 7.8 to 9.0 in the dark theme and 4.62 to 5.07 in the light theme, against the 4.5 minimum. The light theme on the elevated surface has little room, so a later change to the hue or the wash could break it with no test noticing. Sortie 19 added one more user of this banner tone (the MCP editor's fallback note); the provider editor and the Encryption page already use it.

Needed: gate `--status-warning` text composited on `--status-warning-bg-soft-2` over the three surfaces in both themes, in the manner of `test_warning_text_on_soft_fill_passes_body_aa`, and correct the exemption note.

## Evidence
- `the_one/interfaces/web/static/css/components.css` — `.banner-warning { border-left-color: var(--status-warning); background: linear-gradient(to right, var(--status-warning-bg-soft-2), transparent); color: var(--status-warning); }`.
- `tests/test_design_tokens_a11y.py::test_warning_text_on_soft_fill_passes_body_aa` — gates the 8% wash only.
- `tests/test_design_tokens_a11y.py` (`_CONTRAST_EXEMPT`, the `--status-warning-bg-soft-2` entry) — "a fill only, no text sits directly on it".
- `sorties/19-local-mcp-servers-newest-protocol/flight-log.md`, "flight review" — the reviewer's figures and method.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

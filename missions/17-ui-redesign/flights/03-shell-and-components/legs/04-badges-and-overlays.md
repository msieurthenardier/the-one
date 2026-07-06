# Leg: badges-and-overlays

**Status**: completed
**Flight**: [Shell and Shared Components](../flight.md)

## Objective

Fix badge contrast with per-badge ink THEN gate it in the a11y suite (flight DD "Badges"); restyle dialog.js modal, app-flash toast, and empty states to the vocabulary; re-author their gallery sections.

## Scope (flight DDs authoritative)

- Badges: per-badge ink token strategy (light fills → dark ink) per the F2 measured table (flight-02 flight-log Decisions, 10 failing pairs); badge CSS at `admin.css:82,150-156` + `studio.css:911-912` families; mirror + a11y suite gain the badge×ink pairs BOTH themes (mirror-sync guard covers new literal-hex tokens); lightness-tune only where cheap; hue recognizable.
- Overlays: `.modal-overlay`/`.modal-dialog` (dialog.js markup) → surface + hairline + `--radius-lg` + `--shadow-modal`; `.app-flash` toast already has `--shadow-popover` (F2) — finish its vocabulary pass; empty-state canvases → one-line statement + primary action styling.
- Gallery: status-section (badges/LEDs) + modal-section re-authored.

## Acceptance Criteria

- [x] Every badge×ink pair ≥4.5 both themes, GATED in `test_design_tokens_a11y.py` (new parametrization green, +22 tests); mirror-sync green
- [x] Modal/toast/empty-state render vocabulary in both themes (evidence incl. an open modal)
- [x] Focus trap still works in the restyled modal (keyboard walk) [a11y gate]
- [x] `make test-unit` green (3743); browser slice green (`test_oauth_modal_flow.py` + studio connector editor + admin tools editor, 48 passed); ruff clean; guards green (115 slice)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry (badge ink table with final ratios); leg `landed`; checked off in flight.md

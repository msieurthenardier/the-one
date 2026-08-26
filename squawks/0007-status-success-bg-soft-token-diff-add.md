# Squawk 0007: Add `--status-success-bg-soft` token and apply it to `.diff-add`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-26
**Completed**: —

## Report

The Mission 21 Flight 2 HAT restyle added before→after diff highlighting on the
self-configuration tab. Deletions render on a `--status-danger-bg-soft`
background; **additions get color + underline only**, because the design system
defines `-bg-soft` variants for warning and danger but **not** for success. The
result is WCAG-safe (the underline carries meaning, never color alone) but
visually asymmetric. Define `--status-success-bg-soft` in the token layer
(mirroring the warning/danger `-bg-soft` derivation, for both light and dark
themes) and apply it to `.diff-add` so additions and deletions read
symmetrically. No behavior change; purely presentational.

## Evidence

- `the_one/interfaces/web/static/css/studio.css` — `.diff-del` uses
  `--status-danger` + `--status-danger-bg-soft`; `.diff-add` uses
  `--status-success` + underline (no background) with an inline comment noting the
  missing token.
- Token layer: `tokens.css` defines `--status-warning-bg-soft` and
  `--status-danger-bg-soft` under both `[data-theme="dark"]` and
  `[data-theme="light"]`, but no `--status-success-bg-soft`. A token-mirror test
  (`tests/browser/` design-token check) enforces light/dark palette lockstep, so
  the new token must be added to both themes.
- Mission 21 Flight 2 debrief, "What Could Be Improved → Technical".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

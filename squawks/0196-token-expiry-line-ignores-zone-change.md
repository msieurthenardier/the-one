# Squawk 0196: the provider Token expiry line does not follow a time-zone change

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
The Claude Plan (Token) editor's `provider-token-expiry` line formats its dates in the operator zone through `App.time.formatDate`, but it does not subscribe to `App.time.onChange`, so a zone change in Settings › Date and time while the editor is open leaves the old dates until the next save or re-mount. Day-granular, so a visible difference only near midnight. Every other clock in the app follows the zone live (M28 F2).

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js` — `renderTokenExpiry` (called at mount and after an edit-mode Save only).
- `the_one/interfaces/web/static/js/time.js` — `App.time.onChange(fn, ownerEl)`.
- Sortie 03 debrief (Architect).

## Deferral
Deferred at the sortie 03 debrief. Revisit trigger: the next squawk batch, or the next change to the provider editor.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

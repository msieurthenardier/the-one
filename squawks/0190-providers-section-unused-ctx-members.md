# Squawk 0190: providers-section ctx wires two members it never uses

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
The DD4 ctx that `studio.js` passes to `App.studio.providersSection.create(ctx)` includes `getDirty` and `bumpEditorGen`, but `providers-section.js` never calls them. Drop them from the ctx and its doc comment, or document why they are reserved.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` ~l.610-613 (ctx wiring).
- `the_one/interfaces/web/static/js/areas/studio/providers-section.js` ~l.15-16 (ctx doc comment); no call sites.
- Sortie 02 debrief (Architect).

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

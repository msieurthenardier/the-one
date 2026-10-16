# Squawk 0190: providers-section ctx wires two members it never uses

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-15

## Report
The DD4 ctx that `studio.js` passes to `App.studio.providersSection.create(ctx)` includes `getDirty` and `bumpEditorGen`, but `providers-section.js` never calls them. Drop them from the ctx and its doc comment, or document why they are reserved.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` ~l.610-613 (ctx wiring).
- `the_one/interfaces/web/static/js/areas/studio/providers-section.js` ~l.15-16 (ctx doc comment); no call sites.
- Sortie 02 debrief (Architect).

## Corrective Action
Fixed in M31 F1 L7 (provider-editor-pilot). `getDirty` and `bumpEditorGen` were removed from the ctx that `studio.js` passes to `App.studio.providersSection.create(ctx)` and from the ctx doc comment in `providers-section.js` (the comment now lists `setDirty(b)` and `editorGen()` only). The module's own `mountToken` / `editorGen` guards are unchanged.

## Verification
- `grep -n "getDirty\|bumpEditorGen" the_one/interfaces/web/static/js/areas/studio.js the_one/interfaces/web/static/js/areas/studio/providers-section.js` finds nothing.
- The `providers` and `routing` lanes (create to edit, discard, stale-save guards) pass under `THE_ONE_TEST_NETNS=1`; results are in the flight log's `provider-editor-pilot` entry.

## Sign-Off
**Reviewer**: Mission 31 Flight 1 Reviewer (Sonnet)
**Verdict**: confirmed
**Commit**: Mission 31 Flight 1 commit (flight/01-library-completion-and-pilot)

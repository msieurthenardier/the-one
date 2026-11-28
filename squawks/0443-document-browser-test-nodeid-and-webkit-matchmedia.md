# Squawk 0443: document the single-browser-test form, WebKit matchMedia ordering and the narrow-control patterns

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: —

## Report
Sortie 21 crew repeatedly hit three things that are not written down in `the_one/agents.md` (or CLAUDE.md's Testing section):
1. Running one browser test needs `scripts/run-tests.sh -m browser <nodeid>`; a bare path or `-k` without `-m browser` deselects everything (the `addopts` marker filter).
2. WebKit updates `matchMedia().matches` before it dispatches `change` (in the next rendering update), and a `change` listener on an unreferenced `MediaQueryList` may not fire; tests must wait on the event via a listener on a strongly referenced list, not on `.matches`.
3. The narrow-control patterns sortie 21 introduced: the intent-stamped pane (`data-pane` from `App.router.paneIntent()`), `App.shellPane.setCovered` as the single owner of `inert` behind a covering panel, and "below 768px a strip of controls becomes one menu" (`App.ui.tabs` narrow mode, `App.ui.editorShell` `secondary`), as named entries in "Project Conventions".

## Evidence
- `sorties/21-usable-at-the-smallest-window/flight-log.md`: the leg 3, batch B and debrief-gate entries (two crew members ran a browser test without `-m browser`; the WebKit listener-release test timed out under load).
- `sorties/21-usable-at-the-smallest-window/flight-debrief.md`, Key Learnings.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

# Squawk 0193: `make up` verify-serving still checks provider files sortie 02 moved

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
`make up` / `make restart` end with `verify-serving`, which curls a fixed list of admin static files. Since sortie 02 moved the provider editor into Library, three entries no longer exist under `areas/admin/`, so every `make up` prints `✗ admin/providers-list.js returned 404` and exits non-zero although the server is serving. Found while starting the sortie 03 live-verification dev instance.

## Evidence
- `Makefile` `verify-serving` loop (~l.154): lists `admin/providers-list.js` (deleted in sortie 02), `admin/provider-editor.js` and `admin/provider-models.js` (moved to `areas/studio/`).
- Sortie 03 flight log, `live-verification` (2026-10-12).

## Deferral
Deferred mid-flight (sortie 03). Revisit trigger: the next squawk batch after the sortie 03 debrief, or the next time `Makefile` is touched. Workaround: the instance is up when `/api/live` answers.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

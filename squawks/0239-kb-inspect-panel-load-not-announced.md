# Squawk 0239: The knowledge inspect panels do not announce when their content arrives

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
"View chunks" and "View source" move focus to the panel's `h3` heading, which announces the file path. The "Loading…" line is `live: 'off'`, and nothing is announced when the chunks or source finish loading. A screen-reader user has no cue that the content is ready. It is acceptable because focus is already on the panel, but a polite "{n} chunks" or "Source loaded" status would close the gap. Found in the Mission 31 Flight 3 accessibility review.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/knowledge-inspect.js`: the loading status (about line 53) and the content render paths.
- Flight 3 flight log, the flight review entry.

## Corrective Action

## Verification

## Sign-Off

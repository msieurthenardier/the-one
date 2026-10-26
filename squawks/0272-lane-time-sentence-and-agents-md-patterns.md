# Squawk 0272: Stale lane-time sentence in CLAUDE.md, and four patterns missing from agents.md

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
Docs left behind by Mission 31 Flight 5 (operator-approved at its debrief).

1. CLAUDE.md's per-area lane paragraph still says `make test-browser` takes "about 24 minutes … (1470 s, 13 lanes)". The final Flight 5 gate ran `PARALLEL_RESULT rc=0 total=1581s`, about 26 minutes.
2. `the_one/agents.md` lacks four patterns from the Flight 5 HAT:
   - flash a toast to the page, not the editor's container, when the action closes or remounts the item;
   - the `.ui-kv-center` input-height strut, which keeps a row's switch and remove button aligned when a hint or error makes the row taller;
   - overlay and bubble controls reset inherited typography (`text-transform`, letter-spacing, weight, font) so a host container can't restyle them;
   - a new badge kind updates the `tests/test_ui_badge_kinds.py` count pin as well as `BADGE_KINDS`.

## Evidence
- `grep -n "about 24 minutes" CLAUDE.md` finds the "Per-area browser test lanes" paragraph.
- Flight 5 flight log, "HAT fix pass" and the final gate entry.
- `missions/31-control-library-everywhere/flights/05-mcp-editor-on-the-library/flight-debrief.md`, Documentation.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

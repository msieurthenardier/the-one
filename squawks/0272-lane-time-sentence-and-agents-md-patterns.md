# Squawk 0272: Stale lane-time sentence in CLAUDE.md, and four patterns missing from agents.md

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-10-28 (signed off at the Mission 31 Flight 6 landing)

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
- Item 1: CLAUDE.md's lane-time sentence was already updated by earlier Flight 6 legs (it now reads "about 27 minutes ... (1600 s, 15 lanes; 16 with `contracts-chat`, not yet re-measured)"); leg 09a verified it, and leg 09b replaced it with "about 29 minutes ... (1763 s, 16 lanes)" from the final quiet-host run.
- Item 2: `the_one/agents.md` gained a "Four patterns from the Flight 5 HAT (squawk 0272)" bullet in the control-library section, after "Adding a factory": flash to the page, `.ui-kv-center`, overlay and bubble typography resets, and the badge-kind count pin (now 11).

## Verification
- `grep -n "Four patterns from the Flight 5 HAT" the_one/agents.md` finds the bullet; `grep -n "1763 s, 16 lanes" CLAUDE.md` finds the sentence (M31 F6 L09b); the badge-kind pin (11) passes in the unit tier. Status stays `in-progress` until the flight commit (M31 F6 L09a).

## Sign-Off

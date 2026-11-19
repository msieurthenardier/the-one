# Squawk 0386: Split the three crowded modules before Mission 36 Flight 2

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: —

## Report
Mission 36 Flight 1 left three modules at or over their size line. Flight 2 adds a proposals UI to the chat drawer and to studio, and adds proposal reads to GleepGlorp's views. With no room left, the next change would condense lines again, as Leg 3 did in `studio.js`, or would fail the size rule. Split each one by concern, with no behaviour change, before Flight 2's first leg:
- `areas/chat/agent-drawer.js`;
- `areas/studio.js`;
- `the_one/gleepglorp/views.py`, one module per kind or capability, keeping one public entry point.

## Evidence
- `wc -l`: `static/js/areas/chat/agent-drawer.js` 798, `static/js/areas/studio.js` 799 (both against `LIMIT = 800` in `tests/test_area_module_size.py`), and `the_one/gleepglorp/views.py` 846 (no cap, but one file holds every read surface).
- `missions/36-gleepglorp-assistant/flights/01-gleepglorp-exists-and-answers/flight-debrief.md`, "Technical" and "Recommendations" 1.
- `tests/test_gleepglorp_views.py` covers the views' structural allowlist and secret parity, and must pass unchanged after the split.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

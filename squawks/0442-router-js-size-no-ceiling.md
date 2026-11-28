# Squawk 0442: router.js is past the 800-line module size and nothing enforces it

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: —

## Report
`the_one/interfaces/web/static/js/router.js` grew from 921 lines (at `e3140b24`) to about 1,000 in sortie 21 (the pane intent, the sticky list flag, the `reverting` flag, `keepCovered` and `lastDecision()`). The project's 800-line module rule is enforced for JS only under `js/areas/` (`tests/test_area_module_size.py`), so nothing flags `router.js`. Either bring it under a ceiling (add it to a size test with its current size as an `ALLOWANCE` that only shrinks) or extract the pane-intent and decision-record logic into its own module. Raised by the sortie 21 debrief (Developer and Architect interviews).

## Evidence
- `wc -l the_one/interfaces/web/static/js/router.js` on `sortie/21-usable-at-the-smallest-window`: about 1,000.
- `tests/test_area_module_size.py`: scans `js/areas/` only; `ALLOWANCE` is empty.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

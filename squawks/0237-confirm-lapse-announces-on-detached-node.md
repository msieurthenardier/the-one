# Squawk 0237: A confirm lapsing on a detached element still announces "not confirmed"

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-10-23

## Report
When an element armed by `App.ui.confirm` is removed from the page before its lapse timer fires (for example, a knowledge-base folder panel removed by a poll refresh while its delete is armed), the timer still runs. It reverts the detached node and announces the lapse sentence ("… not confirmed") through the shared live region. A screen-reader user hears a lapse for a control that is no longer on the page. Found in Mission 31 Flight 3, leg 06a. It is harmless otherwise, and the 0088 invariant is unaffected.

## Evidence
- `the_one/interfaces/web/static/js/ui/confirm.js`: the arm timer's expiry callback reverts and announces with no `el.isConnected` check (see the `lapseSentence` path).
- Flight 3 flight log, the leg 06a entry ("Findings").

## Corrective Action
Mission 31 Flight 4 leg 03b. In `ui/confirm.js`, `lapse()` checks `itemEl.isConnected` first: a detached element only reverts, with no `.confirm-lapsed` cue and no announcement.

## Verification
`test_lapse_on_a_detached_element_announces_nothing` (`tests/browser/test_ui_confirm_contract.py`, both engines): fails with the check disabled, passes with it. The `contracts-overlay` lane and the lanes with a `confirm` host pass.

## Sign-Off

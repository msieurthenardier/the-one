# Squawk 0351: Widget heartbeat-loss contract test is timing-flaky

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: 2026-11-13

## Report
`tests/browser/test_ui_widget_hang_contract.py::test_heartbeat_loss_stops_a_loaded_card_while_the_page_ticks[chromium]` failed once in the Mission 35 Flight 3 debrief gate (`--parallel 3`, start load 0.96, lane `contracts-widget-lifecycle`). It got `['stopped-hung', 'paused-user']` where `['stopped-hung', 'stopped-hung']` was expected. An isolated re-run failed 1 of 2 parametrizations; a second re-run passed 2 of 2. The test races the page's tick against wall-clock time instead of waiting on the hang guard's clock seam. Flight 3 did not touch the file (the widget lifecycle is Flight 2's).

## Evidence
- `tests/browser/test_ui_widget_hang_contract.py:201` `test_heartbeat_loss_stops_a_loaded_card_while_the_page_ticks`.
- The debrief gate: `PARALLEL_RESULT rc=1 total=2268s lanes=20 failed=contracts-widget-lifecycle` (`missions/35-rich-visuals-in-chat/flights/03-visuals-on-chat-platforms/flight-debrief.md`, "Test metrics").

## Corrective Action
Root cause: a card's state reads `running` as soon as it mounts, but the hang guard's heartbeat clock (`lastBeatAt` in `widget-lifecycle.js`) starts only when the iframe's `load` fires (`notify('loaded')`). The test waited on `__states()` only, so under load the second card could still be loading when the aged ticks ran; it had no beat to expire and stayed `paused-user`. Product code is correct. Fix (test only, `tests/browser/test_ui_widget_hang_contract.py`): after `wait_states`, wait for each card's iframe `load` (`card_frame(...).wait_for_load_state("load")`) plus one animation-frame round trip before pausing and driving the clock seam. The clock seam itself was already synchronous.

## Verification
Not reproduced before the fix (a quiet host loads both iframes before the check); the race is by inspection. After the fix: 20 of 20 single-test runs pass (both engines, `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1`) while the `contracts-widget-lifecycle` lane ran alongside, and the whole file passes 27 of 27.

## Sign-Off
**Reviewer**: batch Reviewer (Haiku), independent of the implementers. The added wait is test-only and uses the harness's existing `card_frame` testid. The hang-contract file passed in the Reviewer's run (28 of 28 across the two touched files, WebKit required, netns).
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13`

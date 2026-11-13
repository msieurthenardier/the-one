# Squawk 0351: Widget heartbeat-loss contract test is timing-flaky

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: —

## Report
`tests/browser/test_ui_widget_hang_contract.py::test_heartbeat_loss_stops_a_loaded_card_while_the_page_ticks[chromium]` failed once in the Mission 35 Flight 3 debrief gate (`--parallel 3`, start load 0.96, lane `contracts-widget-lifecycle`). It got `['stopped-hung', 'paused-user']` where `['stopped-hung', 'stopped-hung']` was expected. An isolated re-run failed 1 of 2 parametrizations; a second re-run passed 2 of 2. The test races the page's tick against wall-clock time instead of waiting on the hang guard's clock seam. Flight 3 did not touch the file (the widget lifecycle is Flight 2's).

## Evidence
- `tests/browser/test_ui_widget_hang_contract.py:201` `test_heartbeat_loss_stops_a_loaded_card_while_the_page_ticks`.
- The debrief gate: `PARALLEL_RESULT rc=1 total=2268s lanes=20 failed=contracts-widget-lifecycle` (`missions/35-rich-visuals-in-chat/flights/03-visuals-on-chat-platforms/flight-debrief.md`, "Test metrics").

## Corrective Action
*(written at completion)*

## Verification
Make the test advance and await the clock seam deterministically. It then passes 20 runs in a row under load, for example `--count` or a loop alongside another lane, with `THE_ONE_REQUIRE_WEBKIT=1` and `THE_ONE_TEST_NETNS=1`.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

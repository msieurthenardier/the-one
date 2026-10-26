# Squawk 0216: `test_test_connection_button_click_shows_result` races the transient "Testing connection…" text

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: 2026-10-25

## Report
`tests/browser/test_mcp_test_connection_button.py::test_test_connection_button_click_shows_result` asserts the transient status text "Testing connection…" right after the click. Under `THE_ONE_TEST_NETNS=1` the probe against the test's unreachable URL fails almost instantly, so the panel can already show the final error ("Couldn't load this server's tools. … connection probe failed") and the strict `to_have_text` fails. Seen once in sortie 04's final gate (`PARALLEL_RESULT rc=1 … failed=library`); the file passed 7/7 in isolation and the whole `library` lane passed 50/50 on a re-run. The test is untouched by sortie 04.

## Evidence
- `tests/browser/test_mcp_test_connection_button.py` ~l.196: `expect(...).to_have_text("Testing connection…")` immediately after the click.
- Sortie 04 flight log, review cycle 2 entry; gate output in the session scratchpad.

## Corrective Action
The two assertions in `tests/browser/test_mcp_test_connection_button.py` that raced the transient "Testing connection…" text now hold the `/test/connect` response with `page.route` until the transient state is asserted, then release it (a fixed wait, held by a route, as Flight 5 DD12 asks), so a fast failure can no longer beat the assertion. The final-result assertion is kept. Done in Mission 31 Flight 5 leg 08b.

## Verification
The file green under `THE_ONE_TEST_NETNS=1` in the `library` lane (see the leg 08b flight-log entry for the counts and the repeat runs).

## Sign-Off
*(written at completion)*
**Reviewer**: Flight Director review at the leg 08b batch review
**Verdict**: `[HANDOFF:confirmed]` by the Mission 31 Flight 5 batch B4 Reviewer (Sonnet, 2026-10-25), and the fix re-review
**Commit**: the Mission 31 Flight 5 checkpoint B4 commit, `flight/5: connection status, sign-in and server info (legs 08b-09)`

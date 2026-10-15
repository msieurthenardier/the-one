# Squawk 0216: `test_test_connection_button_click_shows_result` races the transient "Testing connection…" text

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: —

## Report
`tests/browser/test_mcp_test_connection_button.py::test_test_connection_button_click_shows_result` asserts the transient status text "Testing connection…" right after the click. Under `THE_ONE_TEST_NETNS=1` the probe against the test's unreachable URL fails almost instantly, so the panel can already show the final error ("Couldn't load this server's tools. … connection probe failed") and the strict `to_have_text` fails. Seen once in sortie 04's final gate (`PARALLEL_RESULT rc=1 … failed=library`); the file passed 7/7 in isolation and the whole `library` lane passed 50/50 on a re-run. The test is untouched by sortie 04.

## Evidence
- `tests/browser/test_mcp_test_connection_button.py` ~l.196: `expect(...).to_have_text("Testing connection…")` immediately after the click.
- Sortie 04 flight log, review cycle 2 entry; gate output in the session scratchpad.

## Corrective Action
*(written at completion)*
Likely: drop the assertion on the transient text (or hold the response with a route until the transient state is asserted), and keep the assertion on the final result.

## Verification
The file green across several runs under `THE_ONE_TEST_NETNS=1` with the lane at full parallel load.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: a test-only flake in an untouched test, found in sortie 04's gate — revisit at the next squawk turnaround.

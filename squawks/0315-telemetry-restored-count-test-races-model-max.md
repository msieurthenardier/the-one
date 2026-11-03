# Squawk 0315: the telemetry restored-count test races the chat's own model-limit fetch

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
`tests/browser/test_flow_chat_transcript_library.py::test_a_restored_count_is_never_zeroed_by_a_zero_maximum` failed once in the 2026-11-02-2 turnaround's full browser gate. It expected "50%" and got `0%in: 5out: 2ctx: 50max: 128.0k`. The test calls `update({... max_context_tokens: 0})`, then `setMax(100)` on the chat telemetry. The chat area also fetches the model's context limit asynchronously, and here that fetch returned 128k. When the fetch lands after the test's `setMax(100)`, it overwrites it, and 50 / 128k shows as 0%. This looks like a test race: the test has to wait until the area's own model-limit fetch has settled before it injects. Confirm first that a late fetch overriding an earlier `setMax` is the intended product behaviour, since a fetch for the current model should win. If it is not intended, it is a product race, and the fix belongs in the telemetry/model-limit code.

## Evidence
- Full gate 2026-11-03: `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript`, start load 0.72, with this test as the only failure (96 of 97 passed in the lane).
- It passed 3 of 3 isolated re-runs (2.5 s each).
- `test_flow_chat_transcript_library.py:221-229`; `_TELEMETRY_MAX_JS` reads the telemetry's max.

## Corrective Action
*(written at completion)*

## Verification
- Find where the chat area sets the telemetry max from the model's limit, and whether that can land after a test-driven `setMax`.
- Test race: wait for the area's own max to settle, then inject.
- Product race: make the latest intent win, and add a test that holds the model-limit response.
- Done when 10 isolated runs and three `--lane chats-transcript` runs pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

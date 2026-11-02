# Squawk 0305: the Continue test saw two step-limit notices once under load

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
`tests/browser/test_flow_chat_transcript_library.py::test_continue_sends_exactly_one_message_and_the_button_goes` failed once in the `chats-transcript` lane with "expected 1 `chat-step-limit`, resolved to 2". After Continue, the agent's second turn hits the step limit again, and the test expects exactly one notice. Under load, the first notice was still present when the second one rendered. It is not known yet whether this is a test race (the count is read while the old notice is still on its way out) or a product race (an ordering of frames that leaves the earlier notice in the log).

## Evidence
- Mission 34 Flight 1 Leg 2 quiet-host run, 2026-11-02, start load 0.23, end load 2.08: `PARALLEL_RESULT rc=1 total=2027s lanes=17 failed=chats-transcript`. This test was the only failure.
- It passed 3/3 isolated, and a full `chats-transcript` lane re-run passed (97 passed).
- The flight changed only unit-tier files and three unrelated browser files (`test_studio_mcps_tab.py` and the two routines test files), so the flight did not cause it.
- `test_flow_chat_transcript_library.py:725` — `expect(page.locator(STEP_LIMIT)).to_have_count(1, timeout=15000)`. The step-limit notice is never stored and is live on the latest notice only (CLAUDE.md "Chats pane", M31 F6 L10d). The removal of the earlier notice is in `areas/chat/transcript.js` / `send.js`.

## Corrective Action
*(written at completion)*

## Verification
- First, find out where the earlier notice should be removed (on the Continue send, or on the next turn's first frame) and whether that removal can lose a race against the second turn's `step_limit` frame.
- If it is a test race: wait on the removal before counting. If it is a product race: fix the removal, and add a test that holds the second turn's frames. If that needs a design call, escalate.
- Done when the test passes 10 isolated runs in a row and three `--lane chats-transcript` runs.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
- **Deferred** (2026-11-02, Flight Director, Mission 34 Flight 1 Leg 2): found mid-flight, outside the flight's scope. **Revisit trigger:** the next squawk turnaround, or the next flight that touches the chat transcript, whichever comes first. Until then, a failure of this test alone in `chats-transcript` is accepted as this squawk when an isolated re-run passes.

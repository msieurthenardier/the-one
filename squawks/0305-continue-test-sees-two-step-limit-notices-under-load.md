# Squawk 0305: the Continue test saw two step-limit notices once under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
`tests/browser/test_flow_chat_transcript_library.py::test_continue_sends_exactly_one_message_and_the_button_goes` failed once in the `chats-transcript` lane with "expected 1 `chat-step-limit`, resolved to 2". After Continue, the agent's second turn hits the step limit again, and the test expects exactly one notice. Under load, the first notice was still present when the second one rendered. It is not known yet whether this is a test race (the count is read while the old notice is still on its way out) or a product race (an ordering of frames that leaves the earlier notice in the log).

## Evidence
- Mission 34 Flight 1 Leg 2 quiet-host run, 2026-11-02, start load 0.23, end load 2.08: `PARALLEL_RESULT rc=1 total=2027s lanes=17 failed=chats-transcript`. This test was the only failure.
- It passed 3/3 isolated, and a full `chats-transcript` lane re-run passed (97 passed).
- The flight changed only unit-tier files and three unrelated browser files (`test_studio_mcps_tab.py` and the two routines test files), so the flight did not cause it.
- `test_flow_chat_transcript_library.py:725` — `expect(page.locator(STEP_LIMIT)).to_have_count(1, timeout=15000)`. The step-limit notice is never stored and is live on the latest notice only (CLAUDE.md "Chats pane", M31 F6 L10d). The removal of the earlier notice is in `areas/chat/transcript.js` / `send.js`.

## Corrective Action
**Root cause: a test race, not a product race.** `addStepLimitNotice` (`areas/chat/transcript.js`) drops only the previous notice's Continue button (`dropContinue`); the earlier notice itself is never removed except by a log wipe (`clearLog`, a re-join), and the notice is not stored. So after Continue and a second step limit, TWO notices in the log (the old one with no button, the new one with the one live button) is the correct, settled behaviour. A probe test (MutationObserver on the log, with and without 6x CPU throttle) showed the settled count is 2 even on an idle host: the second `chat-step-limit` is added ~60 ms after the Continue click. The test asserted `to_have_count(1)`, which only passed when polled in the window before the second notice rendered; under load the poll landed after it. No product change.

Changed `tests/browser/test_flow_chat_transcript_library.py`: `test_continue_sends_exactly_one_message_and_the_button_goes` now waits for 2 notices, then asserts the single Continue is in the last notice and the first has none; `test_a_double_click_on_continue_sends_once` had the same latent race and now waits for 2.

## Verification
- Probe (temporary test, since deleted): settled `chat-step-limit` count was 2 at RATE=1 and RATE=6, which falsifies the old `count(1)` assertion.
- Fixed pair, 10 isolated runs in a row: 10/10 passed.
- `--lane chats-transcript` x3: 97 passed each (229 s, 231 s, 230 s). `ruff check` and `ruff format --check` on the test file clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 8603 passed, 15 skipped.
- No product JS changed, so the `chats` lane and the static-asset guards were not needed.
- Original plan: first, find out where the earlier notice should be removed (on the Continue send, or on the next turn's first frame) and whether that removal can lose a race against the second turn's `step_limit` frame.
- If it is a test race: wait on the removal before counting. If it is a product race: fix the removal, and add a test that holds the second turn's frames. If that needs a design call, escalate.
- Done when the test passes 10 isolated runs in a row and three `--lane chats-transcript` runs.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean. Test-only fix, read against the 10/10 isolated and 3x `chats-transcript` lane runs recorded above.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.

## Disposition
- **Deferred** (2026-11-02, Flight Director, Mission 34 Flight 1 Leg 2): found mid-flight, outside the flight's scope. **Revisit trigger:** the next squawk turnaround, or the next flight that touches the chat transcript, whichever comes first. Until then, a failure of this test alone in `chats-transcript` is accepted as this squawk when an isolated re-run passes.
- **2026-11-02 (Mission 34 Flight 2 debrief):** failed again in the debrief's full gate (`PARALLEL_RESULT rc=1 total=2235s lanes=17 failed=chats-transcript`, start load 1.19), at `:725` "Actual value: 2"; 3 of 3 isolated re-runs passed. It has now failed in 2 of 2 full gates, so every full gate reads rc=1. **Re-prioritised by the operator: first item of the next squawk turnaround**, right after Flight 2's PR merges.

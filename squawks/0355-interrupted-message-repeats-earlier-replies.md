# Squawk 0355: The interrupted message repeats the turn's earlier replies

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: 2026-11-13

## Report
When a turn with several model iterations is cancelled, the stored `_[interrupted]_` assistant message holds the text of every iteration of the turn run together, although each earlier iteration's text is already stored in its own assistant message. The transcript and the model's later context then carry that text twice.

Expected: the interrupted message holds only text streamed since the last assistant message was appended (the reply that was cut off). If nothing was streamed since then, no interrupted message is added.

## Evidence
- `the_one/interfaces/web/app.py` `_process_and_broadcast`: `partial_text` accumulates for the whole step and the `except asyncio.CancelledError` branch appends `Message.assistant(content=partial_text + "\n\n_[interrupted]_")`.
- Observed 2026-11-13, session `9f906a500c438e5cbe7807efc3558379`: stored index 224 ends `...Let me scroll down to see the search results:Let me take a screenshot to see the current state:\n\n_[interrupted]_`; those two sentences are the complete contents of the assistant messages at indexes 221 and 223.

## Corrective Action
In `_process_and_broadcast` (`the_one/interfaces/web/app.py`) the streamed-text accumulator `partial_text` is reset each time the step loop receives an assistant message, because that reply is then stored. The cancel branch therefore appends `_[interrupted]_` only for text streamed after the last stored assistant message, and appends nothing when there is none. No other `_[interrupted]_` pins existed besides the existing tests in `tests/test_cancel.py`, which still pass.

## Verification
- `tests/test_cancel.py` (2 new tests): a two-iteration turn cancelled in the second stores `"Second, cut off\n\n_[interrupted]_"` with the first reply appearing once; a cancel right after an assistant message with nothing streamed adds no interrupted message.
- Falsified by removing the reset: both new tests fail (yes, both).
- Touched files 26 passed; `ruff check` and `ruff format --check` clean.

## Sign-Off
**Reviewer**: batch Reviewer (Haiku tier: no security-sensitive surface in the diff), independent of the implementers. The reset runs only when an assistant message is yielded, after the agent has stored it, so no streamed text is lost. The Reviewer's run of the three touched test files: 58 passed, 2 deselected; ruff clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13b`

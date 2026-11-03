# Squawk 0294: Name the Flight 4 patterns in agents.md and trim CLAUDE.md's routines change log

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-03

## Report
Mission 33 Flight 4 introduced four reusable patterns that are described only inside the routines sections, and CLAUDE.md's Routines and Self-configuration paragraphs have grown into change logs.

## Evidence
- `missions/33-routines/flights/04-hat-and-alignment/flight-debrief.md`, Recommendation 4.
- Patterns: `the_one/routines/service.py::resolve_now_start`; `the_one/routines/runner.py` (`classify`, `_message_saved`); `the_one/interfaces/web/app.py::_restore_session`; the purge success path calling `revertFn()` (`agent-editor-controller.js`).

## Corrective Action
`the_one/agents.md` Project Conventions gained `operator-only-request-shape` (`resolve_now_start`), `fail-closed-unattended-outcome` (`classify`, `_message_saved`), `recheck-shared-state-under-the-lock-after-an-await` (`_restore_session`, F-H1-1) and `confirm-success-path-reverts-the-control` (`handlePurgeHistory`), each written from the code. The CLAUDE.md trim was NOT done: the squawk does not say which text to move, so choosing it is editorial judgement and is left out of scope (a follow-up squawk should name the sentences to move into `agents.md`).

## Verification
Patterns checked against the cited code. The CLAUDE.md half of the verification line (paragraphs state current behaviour only) is NOT met; see Corrective Action.

`the_one/agents.md` Project Conventions has a named entry for each of: an operator-only request shape the agent tools refuse (now-start); fail-closed outcomes for unattended work; a re-check of shared state under the same lock after an await; `App.ui.confirm` success paths calling `revertFn()`.

After review: deleted the pre-written line claiming CLAUDE.md states current behaviour only (it contradicted the recorded NOT met).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Completed for the agents.md half only. The CLAUDE.md trim was not done, because the squawk never named the text and choosing it is editorial. It is carried by new squawk 0317.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

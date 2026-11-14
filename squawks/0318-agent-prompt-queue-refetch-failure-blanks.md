# Squawk 0318: A failed refetch blanks the Agent prompt waiting list

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
Squawk 0290 fixed the Routines item. When a refetch triggered by a window return fails, it now keeps the waiting list and shows an error. The Agent prompt item's `refetchRevisions` on the self-configuration tab still blanks its waiting list when the same refetch fails. Apply the same failed-refetch handling there.

## Evidence
- The 0290 Developer's report (turnaround 2026-11-02-2).
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` (`refetchRevisions`). Compare `self-config-routines.js` `refetchRoutines(passive)`.

## Corrective Action
`self-config-status.js` `refetchRevisions(passive)` now keeps the shown waiting list when a passive refetch fails and shows "Unable to refresh waiting changes." on the card's error line (a later passive success clears only that passive error). `self-configuration-tab.js` `activate()` (the tab and window return path) calls it with `passive = true`; the mount and action-driven refetches keep the old behaviour.

## Verification
Done: `test_failed_return_refetch_keeps_the_prompt_waiting_list` in `tests/browser/test_studio_self_configuration_queue.py` (falsified: with `activate()` calling the non-passive form it fails). That file and `test_studio_self_configuration_dirty.py` pass; the static guards pass. The full `agent-tabs` lane is left for the Flight Director's gate.

Review fixes: the passive "Unable to refresh waiting changes." line is set once per failure episode (`self-config-status.js`: a passive failure returns early when `passiveRevisionsError` is set, or when the line already shows a real action error), and `passiveRevisionsError` is reset wherever the line is cleared (`renderState`) or replaced by an action error (the enable/disable failure), so a later passive success clears only the passive message. Tests in `test_studio_self_configuration_queue.py`: `test_repeated_failed_return_refetch_announces_once` (MutationObserver sees 0 mutations on the second failed refetch) and `test_passive_success_leaves_a_real_action_error`; both falsified (guard removed, reset removed: each fails). The file's 11 tests pass.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-` (this includes the `agent-tabs` lane, which the Developer left to the gate).

Follow-ups logged from the accessibility review: squawk 0363 (the Routines card has the same repeated announcement) and squawk 0364 (a fixed-wait test in the queue file).

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues. The Accessibility Reviewer (Sonnet) raised one should-fix (the passive error line was announced again on every window return) and minors; these were fixed (the review fixes above), and a second review confirmed.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`

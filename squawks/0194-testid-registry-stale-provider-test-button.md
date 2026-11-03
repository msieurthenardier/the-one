# Squawk 0194: testid registry rows for the provider Test button are stale

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-11-03

## Report
`docs/ui-testid-registry.md` lists `test-connection-btn` under area "admin", but the provider editor has lived in studio (Library) since sortie 02; and it lists `test-provider-btn` as a testid, though that is only a CSS class on the same button. A behavior-test Executor following the registry used the wrong testid in sortie 03's live run.

## Evidence
- `docs/ui-testid-registry.md` ~l.372 (`test-connection-btn` | admin) and ~l.373 (`test-provider-btn` | studio).
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js` ~l.88 — `class="btn-outlined-primary test-provider-btn" data-testid="test-connection-btn"`.
- Run log `tests/behavior/anthropic-plan-token-chat/runs/2026-10-12-17-04-32.md` (Executor closing).

## Deferral
Deferred mid-flight (sortie 03). Revisit trigger: the next squawk batch after the sortie 03 debrief (batch with 0193). Check `tests/test_ui_guards.py`'s registry sync before removing the `test-provider-btn` row.

## Corrective Action
`docs/ui-testid-registry.md`: `test-connection-btn` area admin -> studio, described as the provider editor's Test button (`provider-editor.js:111`). `test-provider-btn` is NOT only a CSS class: it is a live `data-testid` on the agent editor General tab's provider Test button (`general-tab.js:140`, used by `agent-model-picker.js` and browser tests), so the row stays (removing it would fail the registry sync) but is now described and distinguished. Also fixed the same stale area on `save-provider-btn` and `delete-provider-btn` (both emitted from `provider-editor.js`, admin -> studio).

## Verification
Each testid checked against the JS by grep. Ran `tests/test_ui_guards.py` and `tests/test_nav_helper.py` (both ran inside `THE_ONE_TEST_NETNS=1 make test-unit`: 8718 passed, 15 skipped). No new tests.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

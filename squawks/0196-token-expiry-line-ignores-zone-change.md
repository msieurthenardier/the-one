# Squawk 0196: the provider Token expiry line does not follow a time-zone change

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-13

## Report
The Claude Plan (Token) editor's `provider-token-expiry` line formats its dates in the operator zone through `App.time.formatDate`, but it does not subscribe to `App.time.onChange`, so a zone change in Settings › Date and time while the editor is open leaves the old dates until the next save or re-mount. Day-granular, so a visible difference only near midnight. Every other clock in the app follows the zone live (M28 F2).

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js` — `renderTokenExpiry` (called at mount and after an edit-mode Save only).
- `the_one/interfaces/web/static/js/time.js` — `App.time.onChange(fn, ownerEl)`.
- Sortie 03 debrief (Architect).

## Deferral
Deferred at the sortie 03 debrief. Revisit trigger: the next squawk batch, or the next change to the provider editor.

## Corrective Action
`provider-editor.js`: after the initial `renderTokenExpiry`, the editor now subscribes `App.time.onChange(fn, expiryHost)` (owner-scoped to the `.admin-pf-token-expiry` host, since the editor has no teardown hook), re-rendering the line in place from the last saved row (`expiryRow`) and the current type select. The ownerEl form was chosen over a plain subscribe so the listener drops when the editor is unmounted, matching `rules-notes-tab.js`. Test added: `test_expiry_line_follows_time_zone_change_without_remount` in `tests/browser/test_flow_provider_plan_token.py`.

## Verification
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_flow_provider_plan_token.py -m browser -x --timeout 60`: 9 passed.
- New test with the JS fix reverted: fails; restored: passes.
- `tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py`: 285 passed.
- `ruff check` / `ruff format --check` on the test file: clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.

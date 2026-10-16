# Squawk 0189: provider focus-after tests still run in the settings lane

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-15

## Report
After sortie 02 moved providers to Library, the provider tests in `tests/browser/test_flow_settings_focus_after.py` were migrated to Library routes but stayed in that settings-lane file. They belong in a `test_flow_provider_*` file (the `providers` lane), next to the other provider tests.

## Evidence
- `tests/browser/test_flow_settings_focus_after.py` (provider cases on `library/providers` routes).
- `scripts/run-tests.sh` `providers_pat=('test_flow_provider_*')`.
- Sortie 02 flight log (leg 2 Part 1 deviation) and debrief.

## Corrective Action
Fixed in M31 F1 L7 (provider-editor-pilot). The six provider cases (Save, Cancel, Create, Test, failed Save, and the held-Save no-steal case) moved verbatim, with their helpers, from `tests/browser/test_flow_settings_focus_after.py` into the new `tests/browser/test_flow_provider_focus_after.py`, which the `providers_pat` glob (`test_flow_provider_*`) picks up. The settings file keeps only the tool-editor case and its docstring now points to the new file. The one selector that the editor rebuild retired (`.test-result-ok`) became `[data-testid="provider-test-result"][data-state="success"]` in the moved Test case.

## Verification
- `scripts/run-tests.sh --lane providers --list` lists `test_flow_provider_focus_after.py`; `--lane settings --list` still lists `test_flow_settings_focus_after.py`.
- Both files pass under `THE_ONE_TEST_NETNS=1` in their lanes (recorded in the flight log's `provider-editor-pilot` entry).
- `tests/test_run_tests_lanes.py` (lane partition) passes.

## Sign-Off
**Reviewer**: Mission 31 Flight 1 Reviewer (Sonnet)
**Verdict**: confirmed
**Commit**: Mission 31 Flight 1 commit (flight/01-library-completion-and-pilot)

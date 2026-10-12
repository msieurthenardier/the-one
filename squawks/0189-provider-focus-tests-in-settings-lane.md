# Squawk 0189: provider focus-after tests still run in the settings lane

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
After sortie 02 moved providers to Library, the provider tests in `tests/browser/test_flow_settings_focus_after.py` were migrated to Library routes but stayed in that settings-lane file. They belong in a `test_flow_provider_*` file (the `providers` lane), next to the other provider tests.

## Evidence
- `tests/browser/test_flow_settings_focus_after.py` (provider cases on `library/providers` routes).
- `scripts/run-tests.sh` `providers_pat=('test_flow_provider_*')`.
- Sortie 02 flight log (leg 2 Part 1 deviation) and debrief.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

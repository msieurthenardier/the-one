# Squawk 0158: windows-tests CI task still installs unlocked with pip

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: —

## Report
Mission 26 F01 moved every Linux CI task to `uv sync --locked` from `uv.lock`. `windows-tests` was left on `pip install -e ".[all-llms,dev]"` because a uv install could not be validated on `windows-worker` within the flight. So the Windows lane can still test a different dependency set than the lockfile.

## Evidence
- `ci/tasks/windows-tests.yml:53`: `& $py -m pip install -e ".[all-llms,dev]" --quiet`.
- Flight log Deviations (leg 5): `windows-tests` reverted to pip. A pinned `uv==0.9.30` via the choco Python was drafted but never run.
- Verify with one `fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=<clean export>` on `windows-worker`, run when no local test run is going.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

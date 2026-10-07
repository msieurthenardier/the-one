# Squawk 0134: Two self-configuration surface tests fail intermittently under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

Two unit-tier tests in `tests/test_self_configuration_surface.py` sometimes fail in a full `make test-unit` run. Both pass when re-run on their own.

On 2026-10-07 the `squawk/turnaround-2026-10-07` branch had nine full runs, and only one hit them: the squawk 0129 Developer's run, with 5453 passed, 10 skipped and 2 failed. The other eight runs had no failures, and none of that batch's changes touch the self-configuration surface.

The tests' names suggest timing assertions under concurrency. The one failing run was the busiest, with other test processes on the host. A gate that sometimes goes red for no reason trains people to dismiss red, so a real failure here could be waved off as "the known flake". Find the timing or ordering assumption and make each test deterministic. Do not add retries, `xfail` or skips.

Distinct from squawk 0132. That one is about skips (the native-watch self-probe); these are failures.

## Evidence

- `tests/test_self_configuration_surface.py:467` `TestSquawk0006TwoAgentSimultaneousIsolation` → `test_two_live_agt_credentials_never_cross` (line 483)
- `tests/test_self_configuration_surface.py:570` `TestSquawk0005ShutdownDrainUnderLoad` → `test_live_surface_connection_evicted_before_general_drain` (line 604)
- Both use the `running_surface` fixture, so they run against a live loopback surface.
- Rate: 1 hit in 9 full `make test-unit` runs on 2026-10-07 (the turnaround's Developer and Reviewer gate runs). A re-run of the two tests alone gave 2 passed.
- The failure output from that run was not kept. Reproducing it under forced load, for example with busy-loop processes alongside a repeat of the two tests as squawk 0132's Developer did, is the first step.

## Corrective Action
*(written at completion)*

## Verification
- Each test passes 50 repeats in a row under forced CPU load. Use the same busy-loop approach squawk 0132 recorded.
- The fix is shown to address the cause the reproduction exposed, not to widen a timeout to mask it.
- `make test-unit` is green.
- `ruff check` and `ruff format --check` are clean.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

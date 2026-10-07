# Squawk 0132: The unit suite's skip count flaps between 10 and 12

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-07

## Report

Across Mission 25 Flight 6's gate runs, `make test-unit` reported 10 or 12 skipped tests on the same environment. No test changed between those runs that adds a skip. Some pair of tests is skipping conditionally, for example on a busy port, a missing binary, timing or platform. Identify them and record the reason, so a skip-count change at a gate means something.

## Evidence

The Flight 6 flight log's leg gates:

| Leg | Skipped |
|---|---|
| 1b | 12 |
| 2 | 10 |
| 4 | 10 |
| 4d | 10 |
| 4c | 12 |
| 6 | 12 |

In `git diff aaee705..1b6f540 -- tests`, no unit-tier skip marker was added.

## Corrective Action
Investigation (static pass over every non-browser skip, one full `-rs` run, targeted load reproductions). Result: the stable 10 are identified with certainty; the conditional pair is identified as a strong inference but was NOT reproduced.

Stable 10 (`make test-unit`, `-m 'not browser and not live and not pixel and not requires_bwrap'`), all platform skips on Linux:
- `tests/test_pty_dispatch.py:56` Windows-only dispatch path (1)
- `tests/test_pty_windows.py` lines 68, 81, 95, 110, 122, 133, 153, 170, 300: module-level `skipif(os.name != "nt")` (9)

Conditional pair (the 12 state): `tests/test_kb_watcher.py::TestRealWatch::test_real_watch_change_triggers_request_index` and `::test_real_watch_root_removal`. Each runs `_self_probe_delivers`, a 1.0 s deadline for `watchfiles` to deliver a native change event, and calls `pytest.skip("this host/filesystem does not deliver native change notification events within the self-probe deadline")` otherwise. It is the only timing/host-dependent skip in the unit tier that comes in a pair of this shape; `tests/test_doctor.py:805` (native round-trip) uses the same probe and is a possible third. Other skips are static: POSIX-only `os.name` checks (these run, not skip, on Linux), `test_kb_walk`/`test_db_api` symlink support, `test_kb_watcher:432` (root-only), none variable here. Ruled out: ports, binaries, env vars, test ordering (no xdist).

Reproduction attempts, all negative: `test_kb_watcher.py` + `test_doctor.py` under 8, 40 and 60 busy-loop processes on a 20-core host (load average above 20), 15 repetitions of `TestRealWatch`: always 3 passed, 0 skipped. The 12 state likely needs heavier filesystem-notification latency (WSL2 inotify under concurrent suites) than CPU load alone produces. Flight 6's 12-skip gates (legs 1b, 4c, 6) and 10-skip gates (2, 4, 4d) show no environment difference in the flight log (leg 1b ran with `THE_ONE_TEST_NETNS=1`, same as the 10s).

Note for the next person: an explicit `-m` on the command line replaces `addopts`, so omitting `not requires_bwrap` runs the bwrap tests and gives 13 skips (3 more in `test_mcp_sandbox_integration.py`: two unconditional F6-A5 skips and one unshare-privilege skip). My own full run did this: 5537 passed, 13 skipped.

Changes: one paragraph added to CLAUDE.md's Testing section recording the expected count and the conditional pair. No test or product code changed; skip reason strings left as they are (the probe skip is already specific).

Observation, not part of this squawk: two load-flaky FAILURES seen today in `tests/test_self_configuration_surface.py` (`TestSquawk0006TwoAgentSimultaneousIsolation::test_two_live_agt_credentials_never_cross`, `TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain`) passed when re-run alone. A different symptom (timing under load, failures not skips); possibly the same load cause, unproven. Candidate for its own squawk.

## Verification
Planned: run `make test-unit` with `-rs` twice or more. Done: one full `-rs` run plus targeted reruns (see Corrective Action); the pair was not caught. If a future gate shows 12, check `-rs` for the two `test_real_watch_*` ids to confirm. Original plan: record the skipped test ids and their reasons in this squawk, and in `agents.md`'s testing notes if they are environment-conditional by design. A test that skips for an avoidable reason gets fixed.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`

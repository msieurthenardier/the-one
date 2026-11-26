# Squawk 0434: the resolver-clip property test hangs under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: 2026-11-26

## Report

Under load, the whole unit tier was killed twice inside `tests/test_resolver_clip.py::TestProperties::test_clip_is_total_and_resolve_of_the_clip_never_raises[FilesystemConfig]`, with no failure reported either time:
- the Mission 37 Flight 2 Leg 2 run, killed at 98% by a 1200 s timeout;
- the Flight 2 debrief run, killed at 98% by a 3600 s timeout, at load 15-19.

The same test takes about 7.6 s on a clean host (the M37 F1 profile), and passed in Leg 4's run at load 14. A seeded test that sometimes takes over an hour points to a hang or a pathological path in filesystem canonicalisation, not ordinary slowness.

## Evidence
- The debrief run's log ends with that test's node id and then `run-tests.sh: TIMEOUT after 3600s`. 12190 PASSED lines, 0 FAILED. The log is scratchpad `unit.log` and is not kept.
- The test (`tests/test_resolver_clip.py:725`) runs `CASES` seeded random rows. Each one canonicalises generated paths under `tmp_path` and a monkeypatched `HOME`.
- Flight 2 did not touch the resolver, so this is not a Flight 2 regression.

## Corrective Action
Cause: not a hang in canonicalisation. The generators and fixtures produce `~nosuchuser` paths. `Path.expanduser()` on `~name` calls `pwd.getpwnam`, which goes through NSS (`/etc/nsswitch.conf` here has `passwd: files systemd`). On this WSL host, every lookup of an unknown user takes about 45.3 s (measured three times: 45.30, 45.36, 45.48 s), because the `systemd` NSS source waits out a timeout. The property tests canonicalise such an entry in many of their `CASES` rows, so the total grows to hours when each lookup also stalls under load. Pytest-timeout stacks ended in `posixpath.expanduser`, and the slow tests (45.1 s, 45.2 s, 90.5 s = two lookups) are exact multiples of that 45 s. `CASES` was not changed.

Fix (test-level, no product change): an autouse fixture `_no_nss_user_lookup` in `tests/test_resolver_clip.py` and in `tests/test_api_agent_tool_override_validation.py` monkeypatches `pwd.getpwnam` to raise the same `KeyError` a real unknown-user lookup raises. Every `~name` those files use is deliberately unknown. `the_one/platform/paths.py` and the resolver are untouched, so real `~user` behaviour is unchanged. No new test was added, so there is nothing to falsify.

## Verification
- Cause confirmed deterministically: `pwd.getpwnam('nosuchuser_zz9')` took 45.30, 45.36 and 45.48 s on three calls; `/etc/nsswitch.conf` has `passwd: files systemd`.
- `tests/test_resolver_clip.py` and `tests/test_api_agent_tool_override_validation.py` via `scripts/run-tests.sh ... -x --timeout 120 --durations=15` (load 15 to 17): 89 passed in 26.5 s. Slowest: the `FilesystemConfig` clip property test 15.0 s (7.6 s on a clean host), `WebConfig` 2.95 s, the bad-allow-list `FilesystemConfig` test 1.4 s; everything else under 1.2 s. Before: those tests took 45 to 90 s each or hit the 120 s timeout.
- Full unit tier, `THE_ONE_TEST_NETNS=1 make test-unit` (load 16 to 19): 12387 passed, 15 skipped (the expected count under netns), 0 failed, in 415.82 s. No timeouts, including `test_mcp_pool.py` (squawk 0431).

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; no security-sensitive surface), batch review of squawks 0434, 0435 and 0437
**Verdict**: confirmed. The seam is right: CPython 3.12 `posixpath.expanduser` imports `pwd` and calls `pwd.getpwnam` at call time, and `Path.expanduser` delegates to it, so the monkeypatch takes effect. The stub produces the same outcome as a real unknown user (the path is returned unchanged). Every named `~user` in both files is deliberately unknown; `~` and `~/work` go through `HOME` and are unaffected. Nothing is weakened. Non-blocking: the fixture is duplicated in both files (a shared helper module would avoid drift; not autouse in `conftest.py`). The Flight Director's grep of `tests/` found no other unknown-user lookups (the other `~` strings are `~new` routes and markdown text). The API runs these checks via `asyncio.to_thread` (`the_one/tools/override_validation.py`), so a slow NSS host makes a save slow but does not block the event loop.
**Commit**: `squawk: turnaround 2026-11-26` on squawk/turnaround-2026-11-26

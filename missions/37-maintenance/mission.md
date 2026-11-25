# Mission: Post-Mission-36 Maintenance

**Status**: active

## Outcome

Resolve codebase health issues identified in maintenance report
[2026-11-24](../../maintenance/2026-11-24.md). After this mission:

- the unit tier has a mission's worth of headroom under its target again;
- the web API's routes are split into routers along feature lines before the connectors rework adds more;
- two writers to the same agent can no longer silently overwrite each other's credentials.

## Context

The 2026-11-24 inspection was triggered by the close of
[Mission 36](../36-gleepglorp-assistant/mission.md) and release v1.0.0. It covers
Missions 34-36 and sorties 07-19, since the
[2026-10-30](../../maintenance/2026-10-30.md) report.

- **Nothing was Critical.** Security, CI/CD and dependency health are clean.
- **Three findings were Action Required:**
  - the unit-tier trend (T1);
  - `api.py` and `app.py` ahead of the connectors rework (P1);
  - focus lost after removing a chip (A4).
- **A4 is squawk-sized.** It is handled as squawk 0413 beside this mission.
- **Other squawk-sized findings** are squawks 0414-0419. Squawks 0376 and 0320
  were closed as already fixed.

The unit tier, from the report:

| Point | Tests | Time | Per test |
|---|---|---|---|
| Mission 34 F1 (after runtime II) | 8577 | 229 s | 27 ms |
| Mission 36 F4 | 11898 | 384 s | 32 ms |
| 2026-11-24 (quiet, final tree) | 12350 | 453-457 s | 37 ms |

**Squawk 0403** raised the standing target from 350 s to 500 s on 2026-11-24
(operator decision). At about 82 ms per new test, the tier reaches 500 s after
about 500 more tests, which is within one mission.

**Mission 36 Flight 5's own files** show where the time goes: about 50 of their
97 s is in three sweep test bodies (`test_gleepglorp_kind_tool_config.py`,
`test_evals_gleepglorp_kinds.py`, `test_evals_gleepglorp_harness.py`).
`shared_app()` is cached once per session.

**The rest of the tier**, about 290 s in phases under 0.5 s, has not been
attributed. The existing profile hides it, so this mission measures before it
cuts.

**Scheduled elsewhere, and not in this mission:**
- **The GleepGlorp safety and baseline sortie,** which takes finding S2: a warning when an agent proposal enables execution tools.
- **The `Kind` registry review** before the connectors rework (P2, P3).
- **The operator's release-prep session** (squawks 0265, 0255 and 0253; branch and scratch housekeeping).

## Success Criteria

- [ ] **The unit tier is under 400 s** (T1).
  - Measured on a quiet host with the same command as the 2026-11-24 profile.
  - No test deleted, skipped or xfailed to get there.
  - The flight first attributes the unexplained per-test time with a fine-grained profile.
- [ ] **Every browser lane's budget comes from a measured quiet reading** (T2).
  - This covers the six lanes with no measurement note, including the two still marked provisional.
  - The full-gate target is restated from that run.
- [ ] **The web API is split into feature routers** (P1).
  - At least the MCP and connector routes and the agent routes leave `api.py` for their own router modules.
  - Behaviour is unchanged.
  - The route-classification and credential-gate tests still pass.
- [ ] **Concurrent agent writes cannot drop credentials** (squawk 0327).
  - The agent PUT, the agent-credentials route and GleepGlorp's agent `change` apply serialize per agent.
  - A test races two writers.
- [ ] **Python modules have a size ratchet** (T3).
  - A test fails when a Python module under `the_one/` grows past 800 lines, or past its recorded size if it is already over.
  - This matches the `js/areas/` guard.

## Stakeholders

- **The operator.** They want a faster gate, and room for the connectors rework.

## Constraints

- **Order of flights.** Flight 1 must not overlap a browser gate or another unit run (host policy). Flight 2 touches `api.py`, which the connectors rework will also touch, so it flies before that rework.
- **Behaviour stays the same.** Refactors here change no user-visible behaviour. A route split keeps every path, method and response shape.
- **Shell-write rule and CLAUDE.md test rules** apply as usual.

## Environment Requirements

- **Host:** the host-native dev environment and the repo `.venv`.
- **Netns:** `THE_ONE_TEST_NETNS=1` for every browser run.
- **Timing:** readings come from a quiet host (1-minute load below about 1.0, no other test process).

## Open Questions

N/A. Each flight's design settles its own questions.

## Known Issues

N/A.

## Flights

- [x] **Flight 1: Unit-tier runtime III** ([flight](flights/01-unit-tier-runtime-iii/flight.md)). Measure, then cut: sample the sweeps, use fake clocks, cache the static scans, and hoist or parallelize as the measurement directs. Re-budget the lanes from a closing quiet gate.
- [ ] **Flight 2: Backend boundaries before connectors** ([flight](flights/02-backend-boundaries/flight.md)). Split `api.py` into feature routers, add a per-agent write lock (0327), add a Python size ratchet, and optionally log on the write services (P5).

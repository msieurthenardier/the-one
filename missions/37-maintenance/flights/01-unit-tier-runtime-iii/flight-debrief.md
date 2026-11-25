# Flight Debrief: Unit-tier runtime III

**Date**: 2026-11-25
**Flight**: [Unit-tier runtime III](flight.md)
**Status**: landed. It was marked completed after this debrief (operator, 2026-11-25).
**Duration**: 2026-11-25 (flight start at about 09:45; landed at about 15:50)
**Legs Completed**: 3 of 3 (`profile-and-safe-cuts`, `parallel-unit-tier`, `closing-quiet-gate`)
**Plugin version**: mission-control 1.2.4

## Outcome Assessment

### Objectives Achieved
The unit tier now runs in parallel and is back well under its target.
- **Measured first.** A fine-grained profile showed the cost spread thinly: call time 337 s, setup 74 s, no fixture dominating. It also found one cost nobody had listed: the `tool_config` kind's `builtin_tool_names()` rebuilt every built-in tool for each sweep case.
- **Safe serial cuts** were test-only, with no test dropped, and saved about 20-25 s:
  - `tool_config` sweep: 21.7 s to 5.3 s;
  - `kb_manager`: 8.1 s to 5.3 s;
  - the routines test and the MCP windows.
- **pytest-xdist.** `make test-unit` runs `-n 4 --dist load`, and `UNIT_WORKERS=0` runs it serially.
  - Each worker gets its own data directory, guarded by a sentinel test.
  - No tests needed serialising.
  - Three latent defects were fixed at their cause on the way: an env leak in the tiktoken tests (which caused a 17-skip run), a race in the purge loop, and MCP windows too tight under load.
- **Result:** 180.6 s and 212.4 s on a clean host, against about 465 s serial. Coverage is identical: 12,353 passed and 15 skipped, serial and parallel.

**Not achieved: the lane re-budget (T2).** No quiet host came all day; other projects held the load at 7-24. Leg 3 ran as a loaded correctness gate, and the browser tier was aborted by the 2400 s watchdog with 3 of 23 lanes done (all green). T2 moves to Flight 2's closing gate.

### Mission Criteria Advanced
- **"The unit tier is under 400 s"**: met on clean-host readings (180.6 s and 212.4 s). It was not confirmed by a quiet-host gate reading, because none was possible. Under load it read 312-490 s, and still about 2x faster than serial under the same load (807-990 s).
- **"Every browser lane's budget comes from a measured quiet reading"**: not advanced. It is deferred to Flight 2's closing gate.

## What Went Well
- **"Measure before cutting" paid off twice** (Architect).
  - The profile refuted three planned cuts: static-scan caching saved under 0.1 s, and the resolver-clip and stdio-connect waits were floors set by the rule against fewer cases or by spawn cost.
  - It found the one cut nobody had listed.
  - It gave the decision gate a clean answer: no serial cut list reaches 400 s.
- **Mission 34's deferral of xdist was honoured, not bypassed.** Its precondition, "make the work parallel-safe first", was met by an explicit audit of process-global resources (ports, `chdir`, env writes, PTY, bwrap, `atexit`), recorded in the flight log. It was not assumed.
- **Fixing timing failures at their cause** turned flakes that would have been retried away into three real fixes. Each restart of the three-run stability set was earned.
- **The design reviews caught real issues before code:**
  - a module-scoped async `world` would not work with the function loop scope;
  - the eval whole-set run is a floor;
  - the `THE_ONE_DATA_DIR` inheritance needed a marker, not a bare override;
  - the `run-tests.sh` worker reaping was verified.
- **The bounded wait with a stated fallback (Leg 3)** kept the flight moving on a loaded host without re-budgeting from a loaded run.

## What Could Be Improved

### Process
- **A timing flight was planned without a fallback for a shared host** (Architect, Developer). "A quiet host" was listed as a prerequisite but treated as a checkbox. The fallback was improvised in Leg 3 after a 60-minute wait. T1 (timing) and T2 (re-budget) both depend on host state, and bundling T2 with code work made it the certain casualty.
- **Leg 2 was really the flight.** The flight text described xdist as "conditional step 6", but it turned into a dependency change plus a change to shared test isolation, with its own design review. The decision gate handled this correctly, but the flight's objective undersold the likely shape.
- **A Developer deliberately loaded the shared host.** Leg 2 ran a 24-process CPU-burner stress test (load above 40) to provoke timing failures. That was not in its guidance. Other projects share this host.
- **A full `make gate` at load around 20 was predictable as a non-verification.** At 1.8-2x lane walls, the 2400 s watchdog had to fire. A gate started at load above 10 buys almost nothing.

### Technical
- **Isolation debt from the xdist change** (Architect):
  - the `_THE_ONE_PYTEST_OWN_DATA_DIR` marker leaks into every child process (harmless, but undocumented);
  - the per-worker `mkdtemp` directories are never removed (four per run, on top of the one that already leaked);
  - the isolation is an import-time side effect, correct only while nothing imports `settings` earlier.
- **No guard keeps the "no test serialised" result true.** A future test with a fixed port or a `chdir` would flake only under xdist.
- **The MCP spawn tests stay the likeliest flake source under load.** Their windows were widened, but not re-stressed after the last widening, and spawn-cost floors (about 1.2 s per interpreter start) are now built into the constants.
- **N=4 was chosen on one host.** N=8 was tried once from an unclean start.
- **A past `next_run_at` slightly weakens what the routines test shows.** The Reviewer accepted it.

### Documentation
- **`the_one/agents.md` lacks three patterns:**
  - per-worker isolation through the marker variable;
  - opt-in once-per-session fixtures for static data (`fast_builtin_tool_names`, `parsed_scenarios_once`);
  - the window rule for spawned MCP servers (the silent window stays; reserves are ceilings).
- **The CLAUDE.md skip-count note should state** that the expected counts are the same serial and parallel.

## Test Metrics
Sources are named for every figure. None of today's readings is a quiet-host gate reading.

**Unit tier**

| Reading | Tests | Time | Load | Source |
|---|---|---|---|---|
| M36 F5, serial | 12349 passed | 466-470 s | 0.34 | M36 F5 debrief |
| F1 Leg 1 baseline, serial | 12352 | 464.4 s | 0.9-1.9 | flight log, AC1(a) |
| F1 Leg 2, N=4, clean | 12353 | 180.6 s and 212.4 s | about 1.6-8 | flight log, Leg 2 |
| F1 Leg 2 stability, N=4 | 12353 | 364 / 334 / 489.5 s | 7-23 | flight log, Leg 2 |
| F1 Leg 2, serial | 12353 | 989.9 s | about 23 | flight log, Leg 2 |
| F1 Leg 3 gate, N=4 | 12353 | 312.1 s | about 20 | flight log, Leg 3 |
| **Debrief run, N=4** | 12353 passed, 15 skipped | **438.2 s** | 17 → 24 → 10 | Developer's fresh run, 0 failed, 0 flakes |

- **Speedup:** 2.2-2.6x on a clean host. About 2x under load (312-490 s parallel against 807-990 s serial).
- **Trend:** serial M36 readings were F1 309 s, F2 344 s, F3 381 s, F4 384 s, F5 466 s. xdist buys about two missions of headroom at that rate.
- **Skips:** 15, as expected under netns, in both modes. The 17-skip env leak is fixed.

**Browser tier** (reference only; Leg 3 gate at `a5dcdc58`)
- `PARALLEL_RESULT rc=137 total=2540s lanes=23`, aborted by the 2400 s watchdog.
- Three lanes finished green at 1.79-1.96x their budgets (`agents` 1431 s, `routing` 1448 s, `agent-tabs` 1470 s) at load 10-24.
- Not comparable with M36 F5's quiet 2736 s.
- Post-gate sample (flight log): `gleepglorp-chat` 84 passed; `shared` 1 failed, 51 passed. The failure is squawk 0424: a pre-existing race between the router's boot and a rail click under a slow bwrap probe. It was not reproduced on a pre-M37 commit.

**Flakes**: none in the debrief run. Squawk 0424 is a reproducible failure under load, not a flake.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 2 became xdist, not fixture hoisting | The profile showed no dominant setup cost | Yes: the profile decides |
| Planned static-scan, resolver-clip and stdio-window cuts dropped | Data refuted them, or spawn-cost floors | Yes: record the refutation |
| `world` template copy replaced by `fast_builtin_tool_names` | The real cost was `builtin_tool_names()` | n/a |
| Leg 3 ran as a loaded correctness gate after a bounded 60-minute wait; T2 deferred | No quiet host all day | Yes: write the fallback into the flight design |
| Developer ran a CPU-burner stress on the shared host | Self-chosen, outside guidance | No: a crew rule should forbid it |
| Squawk 0424 triaged as pre-existing | Fails with `-p no:xdist`; app code unchanged | Partly: verify on an older commit when cheap |

## Key Learnings
- **On a shared host, a timing criterion needs a mechanical quiet check and a pre-agreed fallback,** written into the flight design. Split timing (T1, T2) from correctness work, so a loaded host only defers the timing half.
- **Profile at `--durations-min=0.001` before choosing a mechanism.** The 0.5 s cutoff of the 0403 profile hid about 290 s, and its "fixture tax" reading was wrong.
- **xdist surfaces real defects.** Env leaks and races that serial ordering hid became failures in the first parallel runs. Treat them as defects, not flakes.
- **A test that starts the app is sensitive to the first request's latency** (squawk 0424). Under load, the bwrap probe's 5 s timeout delays the router.

## Methodology Observations
All observations are on mission-control 1.2.4.

1. **flight skill, Phase 4/5 (prerequisites).**
   - **What happened:** a timing flight listed "a quiet host" as a prerequisite with no check and no fallback. The skill's "Environment conflicts" guidance asks what else is running, but nothing asks "what if the measurement environment never becomes valid?".
   - **Cost:** a 60-minute wait, an improvised fallback, and T2 slipped to the next flight. A full loaded gate (about 48 minutes) verified almost nothing.
   - **Expected:** for a criterion that depends on the environment (timing, a quiet host, an external service), the flight design records a mechanical readiness check and a fallback.
2. **agentic-workflow, Phase 2b, crew conduct.**
   - **What happened:** a Developer added deliberate CPU load (a 24-process burner) to a shared host, to provoke timing failures. That was outside its guidance.
   - **Cost:** no visible harm, but it could have skewed other projects' runs and this flight's own readings.
   - **Expected:** a crew-prompt line (local fix): "never load the host on purpose".
3. **agentic-workflow, Phase 2a (conditional legs).**
   - **What happened:** the flight planned "conditional cuts", which turned into a dependency and test-isolation change with its own design review. The decision-gate mechanism worked, but the flight objective never named xdist as the likely outcome.
   - **Cost:** none beyond an extra design cycle. Recorded as a positive data point for "design dependent legs after the predecessor lands" (M36 F4 observation 3).
4. **flight-debrief, "reuse the flight's gate" (project rule, after squawk 0405).**
   - **What happened:** the gate ran loaded, so the rule says "run fresh". But a fresh browser run on a loaded host is worthless, and the operator-deferral clause does not cover a deferral the Flight Director made because of the host. The Flight Director ran a fresh unit tier only, and cited the gate's browser figures as reference.
   - **Expected:** the rule could name the case "host never quiet", with the same treatment as an operator deferral.

## Recommendations
1. **Before Flight 2's closing gate, fix squawk 0424** (a boot-ready wait in `_nav.py`). Otherwise the full-lane gate will fail under any load. **Important.**
2. **Write a quiet-host readiness check and a fallback into Flight 2's design.**
   - Flight 2's gate now carries T2. It has to run every lane, including the six unmeasured ones.
   - Raise `TEST_TIMEOUT` headroom if the host is busy.
   - Do not start a full gate above load 10.

   **Important.**
3. **Re-measure N on a clean host** (N=4 against 6 against 8) at Flight 2's gate, and record the unit tier's new standing reading. About 180-210 s clean makes the 500 s target loose. **Minor.**
4. **Close the xdist isolation debt:**
   - remove the per-worker temp directories at session end;
   - document the marker pattern and the once-per-session fixture pattern in `the_one/agents.md`.

   **Minor.**
5. **Crew-prompt rule:** never load a shared host on purpose. This is a local fix to `.flightops/agent-crews/leg-execution.md`. **Minor.**

## Action Items
- [ ] Squawk 0424: a boot-ready wait in `_nav.py`, before Flight 2's gate.
- [ ] Squawk 0422: an agent build waits 30 s on a stale OAuth source. Folded into the turnaround before Flight 2 (operator decision).
- [ ] Flight 2 design: the quiet-host check and fallback, the T2 re-budget over every lane, and the N re-measure.
- [x] **Small follow-ups, logged as squawks** (operator, 2026-11-25):
  - [0425](../../../../squawks/0425-xdist-worker-data-dirs-not-removed.md): remove the per-worker temp directories;
  - [0426](../../../../squawks/0426-agents-md-xdist-isolation-patterns.md): `agents.md` notes on the xdist patterns;
  - [0427](../../../../squawks/0427-crew-rule-never-load-shared-host.md): a crew rule against loading the shared host.

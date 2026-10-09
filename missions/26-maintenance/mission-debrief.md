# Mission Debrief: Post-Mission-25 Maintenance

**Date**: 2026-10-09
**Mission**: [Post-Mission-25 Maintenance](mission.md)
**Status**: completed
**Duration**: 2026-10-08 to 2026-10-09
**Flights Completed**: 1 of 1
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|---|---|---|
| Unit tier on a template database, ≤300 s | **Met** | About 190 s, down from 697 s. 5625 passed, 12 skipped under netns. Guards: template equals a fresh `ensure_schema`, and an `ast` call-site allow-list keeps new tests off the slow path. `test_db_migration.py` stays on the real path. |
| Browser servers seeded from the template | **Met** | Every `_spawn_app` server starts on a copy, with no migration replay. Measured saving about 0.2 s per start, against 0.4 s projected. |
| Browser quick wins | **Met** | The redirect table runs on one server. 3 duplicate tests deleted and 2 collapsed, each with its covering test named. Ready-poll at 0.03 s. 0 "deferred" skips. |
| Local browser lanes in parallel, gate ≤20 min | **Met** | 18.4 min, reproduced at 18.5 min in the debrief. 8 lanes, each with a budget. Both concurrent trials match the sequential pass set. The margin is about 91 s. |
| CI split and filtered, durations documented | **Partly met; changed by the operator, unverified** | CI runs **1** browser task (`--parallel 1`) instead of 3 limited tasks, after the workers rejected `container_limits` and the host ran out of memory. The flight-artifact `ignore_paths` filter is live. The CI browser duration has **never been measured**: the first post-merge build was aborted during setup (see below). |
| CI installs from the lockfile; pip-audit scheduled and at tag time | **Met in config; partly verified** | Every CI task, Windows included since squawk 0158, uses `uv sync --locked`. Locked installs are verified on the Windows worker (build 692704) and in the `fly execute` trials. The weekly and tag-time pip-audit are configured but have not been run live (`workflow_dispatch` still pending). |
| Policy and per-lane budgets recorded | **Met** | `run-tests.sh --help`/`--plan`, CLAUDE.md and `the_one/agents.md`. Policy: local gate 3 lanes, CI 1 browser task, never both at once. |

### Overall Outcome
**The gate is no longer the bottleneck.** That was the mission's core outcome, and it is delivered: a full local gate went from about 53 min to 18.4 min with no coverage lost. The unit tier went from 697 s to about 190 s, which undoes the per-test cost doubling Mission 25 left behind.

**The CI half is only partly delivered.**
- **Built:** locked installs and the flight-artifact filter.
- **Never seen working:** the CI browser task. The first post-merge build (`the-one/ci/73`) was aborted at 2m37s, still during setup, when the host's shared memory reached 8.3 GB.
- **Why:** the local Concourse's two Linux workers keep `/worker-state` on a 16 GB `tmpfs` each, which is RAM (concourse-local#11). Five CI tasks starting at once fill it in minutes.
- **State now:** the pipeline is paused.

The mission is marked **completed** by operator decision, with the CI verification carried as an action item tied to concourse-local#11. The goal was still the right one at the end. The mission found that the real constraint on this host is memory in the CI workers, not test design. The operator reported no major coordination friction.

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| [01 Test-suite runtime](flights/01-test-suite-runtime/flight.md) | completed | The gate went from about 53 to 18.4 min through a template DB, browser seeding, quick wins, a parallel runner with budgets, and locked CI installs. The planned legs 5 and 6 were merged. Conditional leg 7 (module-scoped server) was not needed. The CI design changed twice on operator decisions. ([debrief](flights/01-test-suite-runtime/flight-debrief.md)) |

**Squawk work alongside the mission.**
- **Before the flight:** squawks 0143–0155, including the maintenance report's squawk-sized findings.
- **#250**, after the flight: 0092, 0134 with its duplicate 0157, 0156, 0158, 0159 and 0160, all from the flight debrief.
  - **0134** was the self-configuration test flake behind the one CI failure. Its root cause was `sse_starlette`'s class-level shutdown latch, fixed in the test fixture (50/50 under load).
- **#251:** renumbered the duplicate squawk ids.

## What Went Well
- **Guarded fast paths.** Every shortcut ships with a test that proves it equals the slow path:
  - template ≡ fresh `ensure_schema`, plus an `ast` call-site allow-list;
  - parallel pass set ≡ sequential pass set;
  - CI's shape pinned by unit tests, with CI calling the local runner and naming no lanes.

  This is how a 65% cut in gate time came with no coverage lost.
- **Measured baselines and budgets.**
  - The maintenance report's timing pass attributed the cost (about 75% unit setup, about 52% browser server churn) before any design, so the flight aimed at the right levers.
  - Deleting redundant tests was correctly identified as a minor lever (about 1.5 min).
  - The per-lane budgets now give future debriefs a fixed bar. Comparing only flight to flight is what let Mission 25's 2.5× growth go unflagged.
- **High-risk design reviews and divert conditions.**
  - Two design-review cycles caught three bash lifecycle bugs in the parallel runner before any code existed.
  - A review caught the `--frozen`/`--locked` inversion.
  - When leg 5's infrastructure assumption failed, its divert condition stopped the leg cleanly with evidence. The operator then decided at the right time, a timing the operator confirmed.
- **Root-causing rather than masking.** The memory incident was traced to the workers' `tmpfs` configuration with direct measurements (concourse-local#11), and the CI test flake to a library latch (squawk 0134). Neither was papered over with retries or timeouts.

## What Could Be Improved
- **Infrastructure capability was assumed, not probed.**
  - The flight listed "Concourse reachable" as its only CI prerequisite.
  - Worker `container_limits` support, worker storage behaviour, `noexec` cache volumes and IPv6 egress were all discovered mid-flight.
  - The memory exhaustion halted WSL once (the operator killed Docker Desktop) and aborted the first post-merge build.
  - A 5-minute busybox `fly execute` probe at planning time would have caught at least the first two.
- **The local host is one shared budget, held only by convention.**
  - Timed legs, `fly execute` trials, the CI workers and other sessions all draw on the same 15 GB, 20-core WSL VM.
  - "Local gate and CI never at the same time" is a policy, not a lock. The CI workers can claim up to 32 GB of `tmpfs` on their own.
- **Projections ran about 2× optimistic.**
  - Leg 2 saved about 0.2 s per start against 0.4 s projected.
  - Legs 2 and 3 together saved 258 s against "5–6 min".
  - The goal was met only because the margin on parallelism was large.
- **The gate margin is thin.** It is 91 s under 20 min, and `routing` is 49% of the browser wall. Lane work did not shrink; parallelism bought the speed-up. Per-start boot, about 1.0–1.15 s of import plus lifespan, is the next lever.
- **Concurrent sessions in one repo collided.**
  - Two sessions each assigned squawk ids 0157–0159 by scanning `squawks/` on their own branch, which took a renumbering PR (#251) to fix.
  - Old commits and #248 still cite the superseded ids.

## Lessons Learned
- **Technical**
  - A template-copy cache is safe when the generator is deterministic **and** a guard proves equivalence. Without the guard it is a silent-drift risk.
  - A single process-group kill does not cover nested `setsid` sessions. Parallel test runners need TERM-first cleanup, published pgids and a parent-death guard.
  - `uv sync --frozen` ignores a stale lock; `--locked` is what enforces it.
  - Class-level library state (`sse_starlette.AppStatus.should_exit`) can leak across tests that start several servers in one process.
- **Process**
  - For CI and host work, probe capabilities before designing. The Citation Audit covers code, and infrastructure needs an equivalent.
  - Plan timed measurement legs as host-exclusive.
  - State projections as ranges, with a measurement method.
- **Environment**
  - On this host the memory ceiling, not CPU, is the binding constraint for any additional test or CI parallelism.

## Methodology Feedback

All findings were made under plugin version 1.2.0. The F1 findings restate observations already in the Flight 1 debrief, so a sweep should count each occurrence once.

1. **No defined path for an operator's disposition of a leg's anticipated divert.** *(agentic-workflow, Phase 2a)*
   - **What happened:** legs are immutable in flight and must be aborted when requirements change. When leg 5 hit its own divert condition, the Flight Director recorded the operator's disposition in the flight log instead.
   - **Cost:** about 15 min of Flight Director deliberation, and review prompts that had to explain "judge as dispositioned".
   - **Recurrence:** 1 of 1 flights (F1).
   - **Destination:** methodology observation.
2. **The Citation Audit covers code only.** *(flight skill, pre-flight)*
   - **What happened:** the infrastructure assumptions behind the CI design were never audited.
   - **Cost:**
     - a blocked leg and two operator decisions;
     - a host memory incident (WSL halted);
     - a CI browser task never verified;
     - a post-merge build aborted and the pipeline paused.
   - **Recurrence:** 1 of 1 flights (F1).
   - **Destination:** methodology observation.
3. **No notion of a host-exclusive leg.** *(agentic-workflow)*
   - **What happened:** timed measurement legs had to be serialized by hand. The guidance to design the next leg while one runs says nothing about legs that need the host to themselves.
   - **Cost:** about 40 min of serialized wall time (accepted), and it contributed to one incident.
   - **Recurrence:** 1 of 1 flights (F1).
   - **Destination:** methodology observation.
4. **Squawk ids collide under concurrent sessions.** *(squawk skill, Log verb, step 4 "assign the next sequence number by scanning")*
   - **What happened:** two sessions on separate branches each took 0157–0159. Neither could see the other's unmerged squawks.
   - **Cost:** a renumbering PR (#251), and superseded ids left in commits and in #248.
   - **Recurrence:** first occurrence, mission-level (outside the flight). Not in the flight debrief.
   - **Destination:** methodology observation.
5. **Contradictory design-review cycle rules.** *(agentic-workflow)*
   - **What happened:** the skill says both "re-review once more" and "max 2 cycles". The Flight Director resolved it by judgement, with no observable cost.
   - **Recurrence:** 1 of 1 flights (F1).
   - **Destination:** local lesson.
6. **Process-hygiene rule only in spawn prompts.**
   - **What happened:** Developers used `pkill` twice despite spawn-prompt bans.
   - **Recurrence:** F1, plus the pre-flight turnaround.
   - **Destination:** local fix, done. The rule is now in `.flightops/agent-crews/leg-execution.md` (squawk 0160).

## Action Items
- [ ] **concourse-local#11** (operator, outside this repo): move `/worker-state` off `tmpfs`, or shrink it and run one worker. Then unpause `the-one` with `fly -t the-one unpause-pipeline -p the-one`.
- [ ] **concourse-local#12** (operator): fix the cgroup v2 threaded `garden` group, then consider restoring per-task memory limits and more than one CI browser task.
- [ ] **Post-merge CI checklist** (Flight 1 debrief), once #11 is fixed. Snapshot memory around each build.
  - [ ] a first green build, recording the CI browser duration;
  - [ ] a cached second build;
  - [ ] a flight-artifact-only push that triggers no build;
  - [ ] one `workflow_dispatch` pip-audit run.
- [ ] **Gate margin:** an early budget warning, a `routing` rebalance, and leg 7 (module-scoped server) kept as a ready sortie for when the gate crosses 20 min. This needs design at the next planning.
- [ ] **Next maintenance cycle should check:**
  - CI browser completed and measured;
  - unit ≤300 s and the gate against the budget table;
  - lane-union and CI-shape pins green;
  - pip-audit running on schedule;
  - template build time as migrations grow.
- [ ] **Squawk id allocation across sessions** (project process): before logging, fetch and scan `origin/main` and every open squawk branch. Better still, have one session own squawk logging.
- [ ] The remaining open squawks (0079, 0080, 0085, 0091, 0093–0100, 0135, 0137–0142) carry to future turnarounds and flights as previously triaged.

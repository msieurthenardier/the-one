# Flight Debrief: Test-suite runtime

**Date**: 2026-10-08
**Flight**: [Test-suite runtime](flight.md)
**Status**: landed
**Duration**: 2026-10-08 (single session; branch cut at `16e91d7`, landed at `699053f`, PR #247)
**Legs Completed**: 5 of 5 flown. The planned legs 5 and 6 were merged into one, and the conditional leg 7 was not needed.
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
The local verification gate went from about 53 min to **18.4 min (1101 s)**, measured in leg 4. The debrief re-ran it and got **18.5 min (1109 s)**. No coverage was lost: every removed or collapsed test is named in the flight log with the test that covers it, and two parallel runs reproduced the sequential pass set exactly (1791 entries).

| Gate | 2026-10-08 baseline | Leg 4 | Debrief re-run |
|---|---|---|---|
| Unit | 697 s, 5598 passed | 188 s | about 190 s wall (166.5 s pytest), 5625 passed, 12 skipped |
| Browser | 2488 s sequential | 913 s, `--parallel 3` | 918 s, all 8 lanes rc=0 |
| Full local gate | about 53 min | 1101 s | 1109 s |

CI now installs every Linux task from `uv.lock` with `uv sync --locked`. A push that touches only flight-artifact directories triggers no build. pip-audit runs weekly and at tag time, which closes squawk 0107.

### Mission Criteria Advanced

| Criterion | Status |
|---|---|
| Unit tier on a template database, ≤300 s | **Met.** About 190 s. The equivalence guard and the call-site guard are in place. |
| Browser servers seeded from the template | **Met.** The measured saving is about 0.2 s per start, half the 0.4 s projected. |
| Browser quick wins | **Met.** Redirect table on one server, 3 duplicates deleted, 2 collapsed, ready-poll at 0.03 s, 0 deferred skips. |
| Local browser lanes in parallel, gate ≤20 min | **Met.** 18.4 min and 18.5 min. Both concurrent trials match the sequential pass set. |
| CI split and filtered, durations documented | **Partly met, and changed by the operator.** CI runs **1** browser task (`--parallel 1`) instead of 3 limited tasks; see Deviations. The filter is narrowed to the flight-artifact directories. The CI browser duration is **unmeasured** until the first post-merge build. |
| CI installs from the lockfile; pip-audit scheduled and at tag time | **Met for Linux tasks and the workflows.** `windows-tests` stays on pip. The live `workflow_dispatch` check is a post-merge step. |
| Host policy and per-lane budgets recorded | **Met.** The budget table is in `run-tests.sh --help`/`--plan` and in CLAUDE.md. The policy is "local gate 3 lanes; CI 1 task; never at the same time". |

**The CI criteria are met in intent only.** They close when the post-merge operator checklist runs (flight log, Leg 5):
1. `set-pipeline`;
2. a first green build;
3. a cached second build;
4. a flight-artifact-only push that triggers no build;
5. one `workflow_dispatch` audit run.

## What Went Well
- **The template database is a guarded cache rather than trusted state.**
  - One migrated template per process, copied per test.
  - The equivalence test runs against a fresh `ensure_schema`: versions, `sqlite_master`, every table's rows including the FTS5 shadow tables, and the pragmas.
  - An `ast` call-site guard keeps new tests off the slow path.
  - It undid the per-test cost doubling recorded in the sortie 01 debrief: about 0.13 s per test fell to about 0.03 s.
- **High-risk design reviews earned their cost.**
  - Leg 4's two reviews found three real bash lifecycle bugs before any code existed:
    - a SIGKILL to a child group skips its EXIT trap, which orphans pytest;
    - a bare `wait -n` returns on the watchdog job;
    - the parent's watchdog `sleep` survives a SIGKILLed parent.
  - Leg 5's review found that `uv sync --frozen` silently ignores a stale lock, which would have inverted the planned demonstration. It also found that ignoring `docs/` and `*.md` would let doc-only changes break CI unseen.
- **Measured budgets give future debriefs a fixed bar.** Comparing only flight to flight is what let Mission 25's 2.5× growth pass unnoticed.
- **CI cannot drift from local lanes.** The CI browser task calls the same runner and names no lanes, and unit tests pin the CI shape: one browser step, no `container_limits`, locked installs.
- **Divert conditions fired cleanly.**
  - Leg 5's "limits cannot be expressed" divert stopped the leg with evidence: busybox probes on both workers.
  - The operator then decided with real data rather than at planning time. The operator confirmed that timing was right.
- **The scripted junit comparison replaced the planned behavior test at no loss.** The property is fully decidable from junit output.

## What Could Be Improved

### Process
- **Infrastructure capabilities were assumed, not probed.**
  - The flight listed "Concourse reachable" as a prerequisite, but not:
    - "workers accept `container_limits`";
    - "worker storage tolerates repeated one-off builds";
    - "the Playwright cache volume is exec-able";
    - "the apt mirror is reachable over IPv6".
  - All four surfaced mid-leg. The last two were only fixed blind.
  - A 5-minute busybox `fly execute` probe at flight planning would have found the first one.
- **Host-exclusive measurement serialized the flight.** Legs 3 and 4 each ran 15–40 min timed runs, during which nothing else could load the host. Design reviews had to be run read-only. That worked, but nothing in the plan anticipated it.
- **Developers used `pkill` twice in this cycle** (a maintenance squawk turnaround, then leg 3), despite explicit spawn-prompt prohibitions. Both times it hit only their own run. The leg 4 runner's `.pgids` and parent-death guard remove the usual reason to reach for it.
- **Projections were point estimates and ran about 2× optimistic:**
  - leg 2 saved about 0.2 s per start, against 0.4 s projected;
  - legs 2 and 3 together saved 258 s, against "5–6 min" projected.

### Technical
- **The CI browser task has never completed a run.** Its cache-hit path, the `/opt/pw` copy (the cache volume is `noexec`) and the IPv4 apt fix are unverified end to end.
- **`scripts/run-tests.sh` grew by about 500 lines of bash:** traps, two watchdog kinds, `wait -n -p` with a poll fallback, `.pgids`.
  - It is pinned by unit tests (argument errors, `--plan`, exit-code rules through a fake `PYTHON`) and by the leg 4 manual SIGINT, SIGKILL and timeout checks.
  - shellcheck is not on the host, and nothing re-runs the kill checks automatically.
- **The gate margin is thin and packing-bound:**
  - 91 s under 20 min in the debrief run;
  - `routing` is 454 s, 49% of the browser wall;
  - the ideal 3-slot packing would be about 836 s against 918 s.
  - One heavy new routing or settings file lands almost directly on the gate time.
- **Budgets warn only after a breach.** The parallel summary prints `OVER BUDGET` when a lane's wall exceeds its budget, but there is no early warning near the line. Lane globs are still hand-rolled, and budgets are re-measured only by hand.
- **Lane work did not shrink; it was parallelized.** Summed lane walls are 2508 s now, against 2488 s sequential at baseline. Per-start server boot, about 1.0–1.15 s of import plus lifespan, is now the dominant per-test cost and the next lever.
- **Unresolved:** `test_self_configuration_surface.py::TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain` failed once under CI load with an MCP initialize timeout. It passes alone in the same container and has never failed locally. That file was converted to the template DB in leg 1.
- **Mixed install paths:** `windows-tests` is still on pip, pending validation of a uv install on `windows-worker`.

### Documentation
- **`the_one/agents.md` lacks the patterns this flight created.** Proposed entries for Project Conventions:
  - the template-copy rule for new tests (`connect_template_db`; call `ensure_schema` directly only in migration tests, and allow-list them);
  - the parallel runner's lifecycle contract (TERM-first, `.pgids`, parent-death guard, `PARALLEL_RESULT`);
  - how to re-measure and update lane budgets.

  CLAUDE.md carries the operational parts.
- **The flight's own criteria text has gone stale.** Its "Contributing to Criteria" and leg 5 bullets still say "3 limited tasks" and that docs and `*.md` pushes are skipped. The flight log's Decisions and Deviations are authoritative; the spec is not rewritten (it is immutable once in flight).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Planned legs 5 and 6 merged into one CI leg | Same files and the same `fly execute` verification; no mid-leg decision between them | Yes. Merge legs that share their expensive verification. |
| Behavior test replaced by a scripted junit pass-set comparison | The property is decidable from junit output, with no observation of a live UI needed | Yes, for any property decidable from machine output |
| No `container_limits` in CI | The workers reject them: cgroup v2 `garden` is in threaded mode (operator) | No. Restore them once `concourse-local` is fixed. |
| CI runs 1 browser task, not 3 | Host memory exhaustion during the `fly execute` trials: Shmem 12.6 GB in Docker's VM, the whole of WSL halted (operator) | Revisit after the worker-storage follow-up |
| `ignore_paths` narrowed to the flight-artifact directories | Unit tests read `docs/*.md` and repo Markdown | Yes |
| `uv sync --locked`, not `--frozen` | `--frozen` silently ignores a stale lock | Yes |
| `windows-tests` left on pip | A uv install was not validated on `windows-worker` | No. A follow-up. |
| Leg 7 not flown | The gate measured 18.4 min, within target | — |
| AC3 of leg 5 recorded as unmet with an operator disposition, rather than aborting the leg | The leg anticipated this divert. Rewriting it in flight is forbidden, and aborting would have discarded the leg's correct work. | Yes. See Methodology Observations. |

## Key Learnings
- **Probe the host before designing for it.** Every CI surprise was a host capability, not code. A capability probe (limits, memory behaviour under repeated builds, exec on caches, network family) belongs in pre-flight, next to the Citation Audit.
- **The memory incident was seen as "the entire WSL came to a halt".** Shmem reached 12.6 GB in Docker Desktop's VM while one browser build at a time was being uploaded and run, and killing Docker Desktop released it. **Root cause found afterwards:** each Linux worker's `/worker-state` is a 16 GB `tmpfs` (`concourse-local` `docker-compose.yml`), so build images, uploads, caches and volumes live in RAM across two workers (concourse-local#11). The next CI work on this host should snapshot `docker stats` and the worker volume usage before and after a build.
- **Parallelism bought the gate; per-test work did not shrink.** The next speed lever is the per-start boot (leg 7's module-scoped server, or a lighter test lifespan), not more lanes. 3 slots is the operator's host policy.
- **Point projections invite surprise.** State a range and the method behind it.

## Methodology Observations
Plugin version 1.2.0 for all of these.

1. **agentic-workflow, Phase 2a: no defined path for a divert disposition.** The skill says legs are immutable once `in-flight` and must be `aborted` (with changes rolled back) when requirements change.
   - **What happened.** Leg 5 hit a divert condition its own spec anticipated ("CI resource limits cannot be expressed"). The operator chose a disposition: drop the limits, then reduce to 1 task.
   - **What was expected.** Some way to record the disposition other than aborting.
   - **What the FD did.** Neither rewrote nor aborted the leg. It recorded the disposition in the flight log's Deviations and Decisions, and resumed the same Developer.
   - **Cost.** About 15 minutes of FD deliberation, and a review prompt that had to explain "judge as dispositioned".
   - **Expected instead:** a "landed with operator disposition" path, parallel to the behavior-test "accepted known issue" rule.
2. **flight skill, Citation Audit: code-only scope.**
   - **What happened.** The audit verifies code mechanisms only. The CI design rested on infrastructure capabilities that are not code citations: `container_limits` support, worker storage, `noexec` cache volumes, IPv6 egress. None were audited, and all surfaced mid-leg.
   - **Cost.** A blocked leg, two operator decisions, a host memory incident (the operator killed Docker Desktop), and an unverified CI browser task at landing.
   - **Expected instead:** a pre-flight "environment capability probe" row type for infrastructure-dependent decisions.
3. **agentic-workflow, design review cycles: two rules contradict.** The text says both "If the second review raises new high-severity issues, fix and re-review once more" and "Max 2 design review cycles — escalate to human".
   - **What happened.** Leg 4's second review raised two new highs. The FD applied the reviewer's exact prescriptions and skipped a third review, relying on the leg's empirical SIGINT, SIGKILL and timeout checks.
   - **Cost.** A judgement call without a clear rule. The outcome was fine.
4. **agentic-workflow: no notion of a host-exclusive leg.**
   - **What happened.** Legs 3 and 4 measured wall-clock on a shared host. The FD had to hold leg 4, keep concurrent reviews read-only, and later stop a `fly execute` loading the same host.
   - **Expected instead.** The skill's parallelism guidance ("design the next leg while one runs") does not say that measurement legs need the host to themselves. A leg-level "exclusive host" marker would make that explicit.
   - **Cost.** About 40 minutes of serialized wall-clock (accepted), plus one incident.
5. **leg-execution crew prompt: process-hygiene rules live only in spawn prompts.**
   - **What happened.** The "never `pkill` by pattern" rule was violated twice this cycle, despite being stated in the spawn prompt. It is not in the project's `leg-execution.md` Implement prompt, so it depends on the FD repeating it every time.
   - **Cost.** No damage either time, but a latent risk to the operator's processes.
   - This is a project crew-file matter more than a plugin one; it is recorded so a sweep can see the pattern.

## Post-Merge Addendum (2026-10-09)

**Checklist step 1 done:** `ci/set-pipeline.sh` was applied, with `ignore_paths` live.

**Step 2, the first build, failed on memory.** The first build after merge, `the-one/ci/73` (all 5 tasks in parallel), was **aborted after 2m37s** by a memory watcher at Shmem 8.3 GB, still during setup, before any test ran:

| | At build start | At abort |
|---|---|---|
| Shmem | 0.6 GB | 8.3 GB |
| MemAvailable | 12.5 GB | 4.2 GB |

That confirms concourse-local#11 (the measurements were added there). The 5-task `ci` job cannot run on this host while worker storage is a 16 GB `tmpfs` per worker.

**Actions taken, at the operator's direction:**
- the `the-one` pipeline is **paused**;
- both Linux workers were restarted, and Shmem fell back to 75 MB.

**What stays unverified until #11 is fixed:**
- the CI browser task, WebKit in CI, and cached install times;
- whether squawk 0157 recurs;
- the artifact-only-push check;
- the first scheduled pip-audit run.

The pipeline is unpaused with `fly -t the-one unpause-pipeline -p the-one` once the fix lands.

## Recommendations
1. **Run the post-merge operator checklist promptly, and snapshot host memory around the first build** (`free -g`, Docker Desktop memory, `docker stats`). It is the only proof the CI half of this flight works, and the only data on the memory incident's cause.
2. **Fix the two `concourse-local` issues:**
   - the cgroup v2 threaded `garden` group that rejects `container_limits`;
   - the worker storage behaviour that piled up shared memory across one-off builds.

   Then revisit restoring memory limits and more than 1 CI browser task. This is an operator task outside this repo.
3. **Add an early budget warning, and rebalance `routing`.**
   - Warn at a fraction of a lane's budget (for example 85%), not only on breach.
   - Split or rebalance `routing` (49% of the browser wall).
   - Treat leg 7's module-scoped server as a pre-designed sortie to fly as soon as the gate crosses 20 min. At a 91 s margin, that is likely within a mission.
4. **Document the template-DB rule and the runner lifecycle contract in `the_one/agents.md`** (Project Conventions), so the next leg author does not rediscover them.
5. **Add an infrastructure-capability probe to flight planning** for any CI or host-dependent work. One `fly execute` busybox task per assumed capability.

## Action Items
- [ ] Post-merge operator checklist (flight log, Leg 5): `set-pipeline`, first build, cached build, artifact-only push, `workflow_dispatch` audit. Snapshot memory around the first build.
- [ ] Watch `test_live_surface_connection_evicted_before_general_drain` in the first CI builds. → **squawk 0157**
- [ ] Validate a uv install for `windows-tests` on `windows-worker`, and move it to `uv sync --locked`. → **squawk 0158**
- [ ] Add the template-DB rule and the runner lifecycle contract to `the_one/agents.md`. → **squawk 0159**
- [ ] Add "never `pkill`/`killall` by pattern" to `.flightops/agent-crews/leg-execution.md`'s Implement prompt. → **squawk 0160**
- [ ] `concourse-local`: filed as msieurthenardier/concourse-local#11 and #12.
  - **#11, root cause found:** each of the 2 Linux workers mounts `/worker-state` as a 16 GB `tmpfs`. That is up to 32 GB in RAM on a 15 GB host, which explains the 12.6 GB Shmem.
  - **#12:** `container_limits` are rejected because cgroup v2 `garden` is in threaded mode.
- [ ] An early budget warning, a `routing` rebalance, and leg 7 as a ready sortie (needs design; next planning).
- [ ] Squawk 0156 (the model picker drops its value on a provider switch): carried.

# Flight Debrief: Change Monitoring

**Date**: 2026-09-16
**Flight**: [Change Monitoring](flight.md)
**Status**: landed → completed at debrief (2026-09-16)
**Duration**: 2026-09-16 (planning) – 2026-09-16 (landed); one day
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved

A registered folder's index now follows the folder with no operator action:
a supervised per-folder filesystem watcher (`WatchManager`, one dedicated
thread per subscription, every `watchfiles` knob pinned, a two-step
permission rule) triggers indexing passes through a 5 s settle window with a
60 s hold cap; a periodic reconciliation walk (5 minutes by default) is the
source of truth and re-subscribes folders that went `unavailable`; both are
operator-configurable under `monitoring` in the knowledge settings and apply
live. Registration refuses a folder that overlaps the data directory;
`/status` reports each folder's `watch` and `watch_error`; a ninth `doctor`
gate proves the native file-watcher extension survives the frozen build.
Behavior test `kb-folder-watch-round-trip` passed 9/9 judged checkpoints on a
dedicated dev instance: event path 9 s, periodic path with the watcher off
12 s, restart re-subscribe 10.6 s, root removal to `failed`/`unavailable`
9 s, recovery 11.2 s. PR #202 is ready against `mission/24-knowledge-bases`.

### Mission Criteria Advanced

- *Files in a registered folder index automatically, and additions,
  modifications, and deletions are reflected without operator action or an
  app restart* — **now met end to end**: Flight 3's walk plus this flight's
  event path and periodic path, behavior-test-backed for both.
- *Operator can register a folder … and see each discovered item's index
  status including failures* — extended with the per-folder watch state.
- *Existing installs upgrade with no data loss, the unit gate stays green,
  and the frozen Windows installer still builds and runs* — no schema change;
  unit gate 4,649; frozen build 612549 `RESULT: PASS` with nine gates;
  installer +0.04 %.

## What Went Well

- **Spec-to-code fidelity was unusually high.** The Architect and the
  Developer both found every DD implemented essentially verbatim — constant
  names, clause order, lifespan order, route shapes. Three planning cycles
  front-loaded the defects, and the three implementing legs then each
  closed in one design-review cycle.
- **Each planning review cycle found a different real defect** (cycle 1:
  `watchfiles` silently polls on WSL, so four probes had measured the wrong
  backend; cycle 2: the permission flag adopted in cycle 1 swallows every
  registration error; cycle 3: the two-step retry would still report an
  unreadable root as `watching`). None was cosmetic; each would have been a
  runtime bug.
- **The watcher-leg split at cycle 1** (`watch-manager` module-only, then
  `wiring-routes-and-docs`) let two narrower design reviews each find real
  issues (loop capture in the thread, snapshot iteration; the stale-citation
  regex, the real-lifespan test family).
- **The behavior test's design-time observability held.** Every assertion
  read through `/status`, `/items`, `/chunks` and the settings route; no
  database reads, no mixed-frame rows. The Step 4 apparatus gap was
  diagnosed as such, re-run with the trigger and the first poll in one
  script, and the rule promoted into the spec.
- **Test discipline paid off in the metrics**: 37 of the 39 new watcher tests
  stay off the slow list despite threads, timers and a real reconcile loop
  (event-driven waits only); the doctor round-trip is stubbed at every
  full-`run_doctor` call site.
- **Operator checkpoints were short and decisive**: seven interview answers,
  three design-review answers, one run decision.

## What Could Be Improved

### Process

- **Important — pin a library's environment-derived defaults before
  measuring it.** The planning probes ran `watchfiles` with its defaults and
  measured the polling backend on this WSL host without knowing it; DD-0 now
  pins every knob at both call sites, but the habit belongs at planning-probe
  time for the *next* environment-sensitive dependency. Grep the library's
  signature and source for env-var or platform-conditional defaults before
  the first probe.
- **Important — a "within N s of an API call" clause needs the trigger and
  the first poll in one process.** Step 4's first attempt was inconclusive
  only because the Executor issued the PUT and the poll loop as separate
  tool calls (~9 s gap). Fixed by rerun and now in the spec's Row
  conventions; the same rule belongs in the project's Executor prompt so
  every spec inherits it.
- **Minor — a per-leg prerequisite re-check for external sessions.** The
  Concourse token expired between planning and Leg 4 and was caught
  reactively; a "verify on the day" line per leg that needs an external
  service would catch it earlier.
- **Minor — the Flight Director committed before the artifact script had
  finished.** The Leg 3 checklist was pre-ticked by its Developer, the
  script asserted and stopped, and the commit ran anyway; a follow-up
  artifact commit repaired it. Chain artifact edits and the commit with `&&`,
  or check the script's exit before committing.
- **Minor — an AC whose test passes the letter but not the point.** Leg 3
  AC-3 named a cross-manager order; the first tests asserted two per-fake
  lists. Caught at the flight-end review (and self-flagged by the
  Developer). When an AC names an *interleaved* sequence, say "one shared
  trace" in the AC.

### Technical

- **Minor — a second threading model.** One daemon thread per subscription
  is justified (the shared 40-token `anyio` limiter; the default executor
  the indexer uses), documented, and capped at 64, but it is a concurrency
  shape the rest of the app does not use. A fourth
  `supervised-per-entity-worker` instance should choose between dedicated
  thread and asyncio-native deliberately; record the criterion in
  `agents.md`.
- **Minor — the timing tolerances were never exercised.** Every wait point
  resolved on the first or second poll; the `starting` allowance and the
  `idle`/`running` tolerance were not needed. The spec's "Large-folder
  settle" variant is the way to exercise them and shares a fixture need with
  the Windows 1M re-measure.
- **Minor — `get_vector_store()` has no shutdown hook**, carried from the
  Flight 3 debrief and unchanged here. It now gets a resolution point rather
  than a third deferral: Flight 6 / mission close, alongside the 1M
  re-measure (mission Known Issues).
- **Minor — one tight timing test.** `test_burst_in_one_window_is_one_call`
  asserts exactly one call across a 200 ms idle window; it did not flake in
  five runs this flight, but it is the one to widen if CI ever reports it.
- **Minor — a stale count in a test comment**: `tests/test_doctor.py` says
  19 `run_doctor(` call sites; there are 21. Cosmetic; the stub is autouse,
  not count-driven.

### Documentation

- Complete for this flight's surface (`CLAUDE.md`, `agents.md`'s
  `WatchManager` block and convention citations, `SECURITY-MODEL.md`,
  `README.md`, `docs/windows-install.md`, the nine-gate table). Leg 1 missed
  the "Knowledge settings … two records" paragraph in `agents.md`; Leg 3
  carried and fixed it — a sweep-siblings miss caught one leg later.

## Test Metrics

| Run | Command | Result |
|---|---|---|
| Leg 1 end | `make test-unit` | 4,599 / 10 skipped / 609.39 s |
| Leg 2 end | `make test-unit` | 4,639 / 10 / 620.25 s |
| Leg 3 end | `make test-unit` | 4,649 / 10 / 637.89 s |
| Flight-end Reviewer | `make test-unit` | 4,649 / 10 / 682 s (background, loaded host) |
| Leg 4 gate (alone, foreground) | `make test-unit` | **4,649 / 10 / 653.19 s** |
| Debrief (Developer, alone, foreground) | `make test-unit` | **4,649 / 10 / 636.62 s**, 0 failures, no flakes |
| Debrief durations run | `run-tests.sh … --durations=15` | 4,649 / 10 / 633.32 s |

Series (all `make test-unit` alone, foreground): Flight 1 3,950 / 466.75 s →
Flight 2 4,370 / 499.22 s → Flight 3 debrief 4,547 / 638.25 s → Flight 4 Leg
4 gate 4,649 / 653.19 s → debrief 4,649 / 636.62 s. Net for the flight:
**+102 tests** (+52 Leg 1, +40 Leg 2, +10 Leg 3). Per-test cost: 118 ms →
114 ms → 140 ms → 140 ms → **137 ms**. The Flight 3 debrief asked whether the
F2→F3 wall-time drift was real; two back-to-back debrief runs 3 s apart
answer it: the drift did not continue — a one-time step, not an ongoing
per-test regression. The slowest fifteen are pre-existing except the two
real-`watch` integration tests (1.86 s and 1.41 s), which wait on genuine
OS event delivery; `test_mcp_pool.py::test_drain_timeout_handles_stuck_worker`
remains the outlier at 10.0 s.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Four planning probes re-run with `force_polling=False`; DD-0 added | `watchfiles` polls by default on WSL; the first probes measured the wrong backend | Yes — pin environment-derived defaults before measuring (Rec. 1) |
| Permission flag → two-step subscribe with a root-readability check | `ignore_permission_denied=True` swallows every registration error; the retry alone still hid an unreadable root | Yes — DD-0; the rule is in `agents.md` |
| Watcher leg split into module and wiring | Cycle 1: one leg was the whole feature | Yes — split lifecycle modules from their wiring |
| Third Architect pass past the max-2 rule | Operator's call; each pass had found a real defect in the previous fix | Operator: keep max 2, ask each time |
| `apply_settings`/`start_all` funnel through `_apply_locked` | A literal `await self.start_all()` inside `apply_settings` would deadlock the non-reentrant lock | Yes — recorded in the module |
| Watch-factory seam widened by the permission flag | The two-step rule had to be observable through the seam | Yes — DD-1 amended in flight, logged |
| Step 4 of the behavior test re-run with a single-script measurement | Executor poll-dispatch gap, not a system delay | Yes — spec Row conventions; Executor prompt (Rec. 2) |
| Commit before the artifact script finished | Flight Director error | Yes — chain edits and commit; check exit codes |
| Leg 3 AC-3 tests rewritten to a shared trace | Two per-fake lists could not prove cross-manager order | Yes — say "one shared trace" in such ACs |

## Key Learnings

1. **A library that picks a backend from its environment must be pinned
   before it is measured.** Four probes, one wrong premise, three review
   cycles to unwind. The pin is cheap; the unpinned measurement was the most
   expensive mistake of the flight.
2. **Each review cycle should look hardest at the previous cycle's fixes.**
   Cycles 2 and 3 both found their defect there. When a fix widens a
   library flag or adds a retry, ask what else the widening admits.
3. **Split a lifecycle module from its wiring.** Two narrower reviews found
   more than one broad one would have.
4. **An apparatus gap is not a system fail and not a pass either.** The
   inconclusive-then-rerun path, with the operator deciding, produced a
   verdict with direct evidence and a durable convention.
5. **Timing tolerances that never fire are unproven.** A green run with
   unexercised branches is weaker than it looks; schedule the variant that
   forces them.
6. **Metrics questions get answered by two quiet runs.** The Flight 3 drift
   question closed on a 3 s spread.

## Recommendations

1. **Make "pin environment-derived library defaults before probing" a
   standing planning step**: add it to the Architect prompt in
   `.flightops/agent-crews/flight-design.md` so every flight spec's premise
   probes are checked for unpinned backends (squawk).
2. **Put the single-script timing rule and explicit HTTP-status capture in
   the project's Executor prompt** (`.flightops/agent-crews/
   behavior-tests-execution.md`), so every spec inherits what
   `kb-folder-watch-round-trip` learned (squawk).
3. **Schedule the "Large-folder settle" variant before the mission closes**,
   alongside Flight 6's Windows 1M re-measure fixture — the only way to
   exercise the `starting` allowance and the `idle`/`running` tolerance in a
   real environment (Flight 6 planning input).
4. **Record the dedicated-thread vs asyncio-native criterion in
   `agents.md`'s `supervised-per-entity-worker` convention** before a fourth
   instance chooses by nearest precedent (squawk).
5. **Give `get_vector_store()`'s missing shutdown hook a resolution point**:
   Flight 6 / mission close, recorded in the mission's Known Issues rather
   than deferred a third time (mission artifact edit, this debrief).
6. **Per-leg external-session prerequisite line** in leg designs that need
   Concourse or another external service ("verify on the day") — a
   methodology note for `/mission-control:agentic-workflow` leg design
   (added to `.flightops/agent-crews/flight-design.md` beside Rec. 1 —
   squawk).
7. **Flight 5 and 6 inputs**: Flight 6 renders the four watch state words and
   the `watch_error` reasons as they are (DD-8's additive contract), plus the
   `monitoring` toggle; Flight 5's tool provider should treat `unavailable`
   as a distinguishable state if it surfaces watch health. Both flights
   inherit DD-6: the registration route now refuses the home directory when
   the default data dir lives under it — Flight 6's registration UI should
   say why.

## Action Items

- [ ] `tests/test_doctor.py`: correct the "19 `run_doctor(` call sites" comment to 21 — **squawk 0067** (servicing, routine).
- [ ] `.flightops/agent-crews/flight-design.md`: Architect prompt gains "check every planning probe against the library's environment- or platform-derived defaults; require them pinned" and "prerequisites needing an external session name a per-leg re-verify" — squawk (servicing, routine).
- [ ] `.flightops/agent-crews/behavior-tests-execution.md`: Executor prompt gains the single-script trigger-plus-first-poll rule and explicit HTTP-status capture — **squawk 0069** (servicing, routine).
- [ ] `the_one/agents.md`: the `supervised-per-entity-worker` convention gains the dedicated-thread vs asyncio-native criterion — **squawk 0070** (servicing, routine).
- [ ] `mission.md` Known Issues: `get_vector_store()` shutdown hook with a resolution point at Flight 6 / mission close — done in this debrief.
- [ ] Carry into Flight 6 planning: the "Large-folder settle" variant; the watch state words and `monitoring` toggle; the DD-6 home-directory refusal message.
- [ ] Merge PR #202 into `mission/24-knowledge-bases`.
- [ ] Still open from earlier debriefs: whether `.flightops/ARTIFACTS.md` documents the mission-branch layer.

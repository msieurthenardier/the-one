# Flight Debrief: Test-suite runtime II

**Date**: 2026-11-02
**Flight**: [Test-suite runtime II](flight.md)
**Status**: landed
**Duration**: 2026-11-02 – 2026-11-02 (one session)
**Legs Completed**: 2 of 2
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
- **Unit tier 437.46 s → 229.33 s** (−208 s, −47.6%) with no test deleted, skipped, xfailed or collapsed. That is under the flight's 340 s target and under the standing 300 s target.
  - The "before" is a solo reading at `4b3dbb19` (start load 0.08): 8574 passed, 12 skipped. It was re-measured because sortie 07 had added tests since the 2026-10-30 report's 430 s.
  - The "after" is Leg 1's solo reading (start load 0.22): 8577 passed, 12 skipped. The flight Reviewer's `make test-unit` on the final tree read 229.5 s.
  - The +3 tests are the new guard tests in `tests/test_api_app_guard.py`. The diff adds 3 `def test_` lines and removes none. (The debrief Developer read "test_unused_selectors_script … dropped" in the flight log as a deletion. It is not: step e was skipped for that file, and the test is unchanged. The wording is ambiguous; see Process.)
- **Browser lanes inside their budgets.**
  - The two remaining load flakes were fixed with condition waits: squawk 0303 (`test_studio_mcps_tab.py` reads the agent before its surface is attached) and squawk 0304 (two routines run-timing tests).
  - Every lane was re-read from one quiet-host `--parallel 3` run. `agent-tabs` (390 → 510 s) and `chats-transcript` (330 → 390 s) moved more than 15% and were re-budgeted.
  - A full-gate target is recorded in CLAUDE.md: 2256 s measured (about 38 min), target 43 min.
- **Checkpoints:** all three met. Leg 1a was resolved at leg design. Unit ≤340 s. The quiet-host run was green with one accepted flake (below).

### Mission Criteria Advanced
- "Unit tier at or below 340 s" (#1): met, at 229 s. It carries the work escalated from squawks 0222 and 0234, whose Disposition now links the result.
- "Browser lanes inside their budgets" (#2): met. Budgets were re-read under squawk 0259's rule, flake waits replaced, and the gate target recorded.

### The `rc=1` reading (operator decision: accept as recorded)
Leg 2's AC4 asked for `PARALLEL_RESULT rc=0`. The run (start load 0.23, end 2.08) ended `rc=1 total=2027s lanes=17 failed=chats-transcript`.
- The one failure was `test_flow_chat_transcript_library.py::test_continue_sends_exactly_one_message_and_the_button_goes` ("expected 1 `chat-step-limit`, resolved to 2").
- It passed 3/3 isolated and in a full lane re-run, and it touches nothing the flight changed.
- The Flight Director accepted it under the gate-flake rule and logged it as **squawk 0305** (deferred). The operator confirmed at debrief that the reading stands and no re-run is needed before merge.
- The `chats-transcript` budget was set from that lane's 291 s reading, which is if anything conservative.

## What Went Well
- **Measuring at leg design resolved the flight's fork with a better third option.**
  - The flight offered "revert vs module-scoped app with a per-test DB reset". Timing one build at 53–56 ms showed no single regressing change.
  - Reading the fixtures showed the app object holds no per-test state.
  - So the leg shared the app object and kept the DB, encryptor and patches per test. The mission's isolation constraint then held by construction, enforced by a falsified post-test snapshot check, instead of a reset that might be incomplete. Architect: "beats both flight options".
- **Re-measuring the baseline before designing.** Sortie 07 had moved the suite since the profile. The fresh per-file table at HEAD drove the step mapping and surfaced `test_resolver_clip` as a new cost.
- **Falsification of every injected timeout.**
  - Leg 1 set each new call-time constant to 100 and watched its test fail.
  - This exposed that `test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` used a `wait_for(15)` that could not fail. It now asserts elapsed time under 5 s, so a speedup also strengthened a weak test.
- **The design review earned its cost.** It produced six concrete fixes (AC3 snapshot set, AC4 regex, a do-not-migrate file, the stop rule, per-timeout falsification, where the check runs) and confirmed the central claim before any code was written.
- **Running Leg 2 after Leg 1** let one quiet-host run serve both the flake verification and the re-budget.
- **The gate-reuse rule** (project crew file) spared a 38-minute debrief re-run. The browser reading was taken on code identical to HEAD.

## What Could Be Improved

### Process
- **The flight's flake list was stale by leg design.**
  - Five of the six squawks it named (0168, 0187, 0201, 0204, 0249) were already completed. 0229 waits on product defect 0228.
  - The real work was 0303 and 0304, deferred in by sortie 07 after the flight was written.
  - The flight's Citation Audit checked code citations but not squawk states. The flight's own hedge ("read each squawk's evidence first") caught it at small cost.
- **An absolute `rc=0` criterion was waived at landing.** The project's gate-flake rule already admits a triaged flake. The criterion should have been written as "rc=0, or a single failure that passes isolated and is logged as a squawk". Waiving a criterion at the end is weaker than defining it correctly at the start.
- **The step-a+b stop rule was moot.** Steps a–e were all implemented before the first full reading, so there is no per-step measurement, only per-file deltas attributed to steps (the "about 60 s" figures). A rule that depends on a mid-sequence reading should say when to take it.
- **"Dropped" in the flight log reads as "deleted".** In a flight whose mission forbids deleting tests, a skipped optimization step should say "left unchanged (payoff under 5 s)".
- **The do-not-migrate list was built from one grep** (`dependency_overrides|app.state|add_middleware`). It missed three `mount("/static")` files, which the Developer caught from the diff. A grep that includes `mount(` would have found them at design.

### Technical
- **Projected savings were conservative by about 2×.** The flight projected about 97–140 s in total; the actual was 208 s.

  | step | projected | actual (approx.) |
  |---|---|---|
  | a: shared API app | 35–50 s | ~60 s |
  | b: evals | 25–35 s | ~55 s |
  | c: source scans | 12–15 s | ~28 s |
  | d: timeouts and poll intervals | 15–25 s | ~25 s |
  | e: subprocess and PTY | 10–15 s | ~11 s |

  The big misses were a cost class the profile did not name: `http.server.serve_forever()`'s default 0.5 s poll, which made every `shutdown()` wait about 0.35 s. It accounted for most of b (evals 66.9 s → 19.0 s in isolation) and for `test_cli_quit` (8.2 s → 0.9 s). The other miss was whole-tree regex scans without a substring pre-filter (`test_ui_ownership` 12.8 s → 0.7 s). A `grep -rn "serve_forever()"` now finds no default-interval call.
- **Debt introduced, all accepted at review:**
  - The isolation snapshot compares counts and keys, so it misses an in-place route swap at constant count, or a handler swap under an existing exception-handler key.
  - The AC4 guard has documented false negatives (router reached through a module alias; an app built outside `tests/`), and an 8-entry allowlist that nobody owns shrinking.
  - The source-scan pre-filters were argued exact (the Reviewer reasoned each one through), but no test plants a violation to prove a pre-filtered guard still fires.
  - `evals_isolation` now seeds the scratch DB from the template. Only `test_evals_env.py` and `test_evals_run_smoke.py` opt back into real migrations (`EVALS_REAL_MIGRATIONS = True`), so a new evals test about first boot must remember the opt-out.
  - Tests now patch three private constants (`_pool._WORKER_TEARDOWN_TIMEOUT_SECONDS`, `streamable_http._PROBE_TIMEOUT_SECONDS`, `pty_unix._CLOSE_GRACE_SECONDS`). Falsification proves each is load-bearing, which limits silent drift.
- **The production change is minimal.** Constants and parameters are read at call time in four files, with defaults unchanged. The Reviewer ran at Sonnet tier because `pty_unix.py` ends sandboxed shells.
- **Nothing ratchets the unit target down.** The flight beat the standing 300 s target by 71 s, so about 100 s of regrowth can now happen before the 340 s or 300 s bars notice. That is how the 430 s drift went unseen.

### Documentation
- `the_one/agents.md` gained "The shared API app", and CLAUDE.md "Testing" gained a one-line shared-app rule. CLAUDE.md's lane table, re-budget history, browser timing and `make gate` line now carry the M34 readings. The commit pass reworded the "37 minutes sequential" clause the Reviewer flagged.
- Not documented: the `serve_forever(poll_interval=…)` rule for test-owned HTTP servers, and that `evals_isolation` seeds from the template (beside the Mission 26 template convention in agents.md).

## Test Metrics
Sources are named per number. The debrief reused the flight's gate under the project's "reuse the flight's gate" rule. Between the gate tree and HEAD only docs, squawk files, the budget table and artifacts changed.

**Unit tier**

| reading | tests | time | source |
|---|---|---|---|
| Mission 26 merge | 5616 passed | ~201.67 s (netns) | flight Citation Audit |
| M33 F1 / F2 / F3 / F4 close | 8092 / 8237 / 8371 / 8383 | 381 / 383.5 / 392 / 398.89 s (netns) | those flights' debriefs |
| 2026-10-30 report | 8387 | 430 s (solo) | maintenance/2026-10-30.md |
| this flight, before (`4b3dbb19`) | 8574 passed, 12 skipped | 437.46 s solo, wall 459 s | Flight Director baseline |
| this flight, after | 8577 passed, 12 skipped | **229.33 s** solo, wall 243 s; 229.5 s (Reviewer) | Leg 1; flight review |
| after, netns, explicit `-m` with bwrap | 8614 passed, 19 skipped | 239 s | Leg 1 |

- Per-test cost fell from about 51 ms to about 26.7 ms, below the post-M26 figure of about 36 ms.
- The suite now has 53% more tests than at Mission 26 and runs about 14% slower than it did then.
- The M31–M33 drift (281 → 399 s) recorded in the M33 debriefs and squawks 0222/0234 is reversed. Like for like against M33 F4's netns 398.89 s, it is about −160 s, since netns adds about 10 s.
- The 19 netns skips are 15 netns, 3 bwrap and 1 timing-conditional self-skip, consistent with CLAUDE.md's skip note.

**Browser tier** (Leg 2, quiet host, start load 0.23, end 2.08): `PARALLEL_RESULT rc=1 total=2027s lanes=17 failed=chats-transcript` (squawk 0305, accepted).
- Against earlier runs: M33 F4 close, 1955 s, rc=0 (+72 s, +3.7%). M31 F6, 1662 s with 16 lanes (+22%). M26, 1101 s (+84%, before the M31 UI work).
- Lanes that moved more than 15%: `agent-tabs` 293 → 407 s (+39%), `chats-transcript` 250 → 291 s (+16%). The rest moved within ±12%.
- The growth is from tests added in M33 and sortie 07. This flight touched three browser files, only to add waits.
- The largest lanes are now `routing` 564 s, `agents` 512 s and `contracts-controls` 509 s.

**Full gate:** 229 s + 2027 s = 2256 s (about 38 min); the target is 43 min. That is slower than the 2026-10-30 report's ~35 min despite the unit saving, because the browser tier grew. **Browser is now 90% of the gate.**

**Flakes on this run:** one unrecorded (squawk 0305). 0229 did not recur. 0241's `test_detail_view_indexing_poll_reindex_and_search` passed in the `knowledge` lane.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Step 1a resolved as "share the stateless app object", neither of the flight's options | Measured cost had no single cause; the app holds no per-test state | Yes: measure and read before choosing between planned options |
| Isolation check in one autouse conftest fixture, not each handing-out fixture's teardown | 43 fixtures hand the app out, and some tests call `shared_app()` inline | Yes (Reviewer and Architect: equivalent or better) |
| Allowlist of 8 files, not 4 | Three asset tests `mount("/static")`, found from the diff | Yes: grep `mount(` with the state, middleware and override grep |
| Leg 2's flake list replaced at leg design (0303/0304 in; five completed out) | Flight written before sortie 07 deferred them | Yes: audit squawk states in the flight's Citation Audit |
| AC4 `rc=0` accepted at `rc=1` | One unrelated flake, isolated-clean, logged as 0305 | Yes: write gate criteria with the gate-flake rule built in |
| No reading after a+b | All steps landed before the first full run | No: harmless here, but a stop rule needs a stated measurement point |

## Key Learnings
- **The unit tier's waste was mostly waiting, not work.** Fixed poll intervals (`serve_forever` 0.5 s), fixed grace periods (PTY 1 s SIGTERM grace that bash ignores), real timeouts (10 s drain, 5 s probe) and per-test rebuilds of a stateless object (55 ms × about 1,200 tests) made up most of the 208 s. A profile sorted by file hid this; reading the slowest *calls* and asking "what is this waiting for?" found it.
- **A speedup is a chance to strengthen a test.** Falsifying each injected constant found a timeout test that could never fail.
- **Re-budgeting keeps lanes green by moving the bar.** Squawk 0259's rule worked as designed, but it does not reduce cost. With the browser tier at 90% of a 38-minute gate, the next runtime work belongs there.
- **Targets taken from projections undershoot.** Conservative step projections made 340 s look ambitious; the measured waste table supported about 230 s.

## Methodology Observations
Plugin version for all entries: mission-control 1.2.3.

1. **A mission scaffolded by routine-maintenance was left `planning` while its flights were `ready`.**
   - What happened: `/mission-control:routine-maintenance` scaffolded Mission 34 with status `planning` and three flights marked `ready`. `/mission-control:agentic-workflow` Phase 1 requires an `active` mission, and no skill performs that transition. The Flight Director moved it by hand at flight start.
   - Expected: either the maintenance scaffold marks the mission `active` when it marks flights `ready`, or agentic-workflow names the transition as a step.
   - Cost: none this time (one line), but the transition happened outside any skill's instructions.
   - Skill and phase: routine-maintenance (scaffold) / agentic-workflow Phase 1.
2. **The flight Citation Audit covers code citations but not squawk state.**
   - What happened: the flight (written by routine-maintenance's scaffold and `/mission-control:flight`) named six flake squawks for Leg 2. Five were completed by leg design, and two newer deferred squawks targeted the leg by name. The flight's Citation Audit format has rows for code mechanisms only.
   - Expected: squawks named as work items get a status row in the audit, re-checked at leg design like line numbers.
   - Cost: re-scoping at leg design (small); the leg was right because the flight's prose hedged.
   - Skill and phase: flight (Citation Audit) / agentic-workflow 2a.
3. **An absolute gate criterion was waived at landing by the project's own flake rule.**
   - What happened: the leg-execution crew's Implement prompt carries the gate-flake triage rule, but the leg's acceptance criterion said `rc=0`. The run ended `rc=1` on an unrelated, isolated-clean flake. The Flight Director accepted it and the operator confirmed at debrief.
   - Expected: agentic-workflow's leg-design guidance for gate-run criteria states the triage rule in the criterion itself.
   - Cost: an acceptance criterion waived after the fact and a debrief question to the operator; no rework.
   - Skill and phase: agentic-workflow 2a (writing acceptance criteria).
4. **The debrief-reuse rule made the debrief cheap.** This is a positive observation. The project crew file's "reuse the flight's gate" rule (from the M33 F2 debrief) spared a 38-minute re-run. Every metric came with its source. Skill: flight-debrief Phase 2/3 ("run the full test suite once").

## Recommendations
1. **Point the next runtime work at the browser tier.** It is 2027 of 2256 s. Split or trim the longest lanes (`routing` 564 s, `agents` 512 s, `contracts-controls` 509 s). Under `--parallel 3` the longest lanes bound the wall time. Reframe deferred item #5 (xdist) accordingly: the unit tier no longer needs it.
2. **Ratchet the unit target down.** Record a standing ceiling of about 260 s in CLAUDE.md ("Expected unit skip count" neighbourhood or the lane-budget section), sourced from the 229.33 s reading, so the next 100 s of drift is noticed when it happens rather than at a maintenance inspection. This is an operator call on the number.
3. **Prove the faster guards still fire.** Add one "plant a violation in a temp tree, expect the guard to fail" test per pre-filtered guard (`test_ui_ownership`, `test_desktop_split_guard`, `test_mcp_httpx_guard`, `test_schema_template`). *(Squawk 0306.)*
4. **Close the cost class found here.** Add a guard against a bare `serve_forever()` in `tests/` and `evals/`, and document the `poll_interval` rule beside "The shared API app" in agents.md. *(Squawk 0307.)*
5. **Write gate criteria with the triage rule built in.** Use "rc=0, or one failure that passes isolated and is logged as a squawk", and add squawk state to Citation Audits.

## Action Items
- [x] Squawk 0228 (Save before the model list loads stores an empty model): routed to **Mission 34 Flight 2** as a leg (operator decision at debrief). That unblocks 0229.
- [ ] Squawk 0305 (Continue test, two step-limit notices): deferred; revisit at the next squawk turnaround or the next flight touching the chat transcript.
- [ ] Squawks 0229 and 0241: stay open with dated notes from this flight's run.
- [ ] Pre-filtered guards prove they still fire (Recommendation 3): **squawk 0306**.
- [ ] No bare `serve_forever()` in test code (Recommendation 4): **squawk 0307**.
- [ ] Unit-tier ceiling of about 260 s (Recommendation 2): operator decision.
- [ ] Browser-tier runtime flight (Recommendation 1): input to the next maintenance report or a sortie.

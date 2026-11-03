# Mission Debrief: Post-Mission-33 Maintenance

**Date**: 2026-11-03
**Mission**: [Post-Mission-33 Maintenance](mission.md)
**Status**: completed
**Duration**: 2026-10-30 (scaffolded from [maintenance 2026-10-30](../../maintenance/2026-10-30.md)) - 2026-11-03
**Flights Completed**: 3 of 3
**Plugin version**: mission-control 1.2.3

Mission-window squawk work, which the operator chose to count as part of this mission's record:
- [#351](https://github.com/msieurthenardier/the-one/pull/351): squawks 0305-0313, the flights' own follow-ups, plus a triage of the whole open squawk log.
- [#352](https://github.com/msieurthenardier/the-one/pull/352): a 43-squawk burn-down.

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| Unit tier at or below 340 s (#1) | met | 437.46 s became 229.33 s in Flight 1, at a quiet start load of 0.22, with no test deleted, skipped or xfailed. It held across the mission: 227 s at the Flight 3 debrief, and 219.16 s for 8738 tests at #352's final gate (start load 0.48). |
| Browser lanes inside their budgets (#2) | met | Flight 1 re-budgeted `agent-tabs` and `chats-transcript` from a quiet-host run, replaced the fixed waits behind flakes 0303 and 0304, and recorded a 43-minute full-gate target in CLAUDE.md. The Flight 3 debrief reading (2223 s) showed three lanes 1-6 s over budget. The second quiet reading the operator asked for (#352, 1774 s, start load 0.72) has every lane within budget, so the drift did not hold and the budgets are unchanged (operator decision). |
| A stale connector save keeps a paired peer (#4, 0288) | met | Flight 2 Leg 1: `update_connector` now does a three-way merge of `allowlist.peers` against a client-sent `allowlist_peers_base`, with unit and browser regression tests. |
| Routine runs reconstructable from the log (#12) | met | Flight 2 Leg 2 added INFO lines for decisions, run outcomes, proposals and purge sweeps. The `routine-run-observable-from-logs` behavior test passed 6/6 on its second run; the first run found that pre-chat failures logged `run=none`, which was fixed. #351 added the vocabulary guard (0309), single emission per line (0308) and the explicit proposal id (0310). |
| Session pushes cost less (#11) | met (by structure) | The drawer render key skips hidden or unchanged rebuilds, and broadcasts are encoded once. Per-push cost at 5k and 20k sessions was not re-measured (Flight 2 debrief, optional). |
| Dead code removed (#24, #25) | met | Flight 3 removed every definitely-dead item, plus `Encryptor.rotate_key` and `ToolConfigRepository.list_all` with their coverage moved to live code. No live code was removed. `badge--local/remote` were kept on purpose, and `listPane` density went later in #351 (0313). The rest of #25 is out of scope and carried forward. |

### Overall Outcome
The mission did what the 2026-10-30 inspection asked of it.
- **The gate is cheap again.** The unit tier is about half its old cost, and the full browser run is the fastest reading this year at 1774 s.
- **The two data-safety and observability gaps are closed with tests.**
- **The dead code is gone.**

The goal stayed right throughout. Sortie 07's surfaces (findings #3, #4 agent half, #6, #7) were left alone as planned, and they are now the largest open structural item.

The mission window also cleared the squawk log, from about 62 non-terminal squawks (50 of them past the 30-day stale mark) to 16. That turned a rotting log back into a working one.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| [01 Test-suite runtime II](flights/01-test-suite-runtime-ii/flight.md) | completed | Unit tier 437 s to 229 s through the shared API app, faster guards and the `serve_forever` poll interval. Flakes 0303 and 0304 fixed, lanes re-budgeted, full-gate target 43 min. One load flake logged (0305). |
| [02 Data safety and routine observability](flights/02-data-safety-and-routine-observability/flight.md) | completed | Peer merge on stale save; routine log vocabulary (behavior test 6/6 after a fix pass); encode-once broadcast and drawer render key; stored model kept while models load (0228). |
| [03 Dead code](flights/03-dead-code/flight.md) | completed | Definite-dead sweep, plus two test-only methods retired after a coverage-table design review caught an inherited half-wrong coverage claim. |
| Turnaround #351 | merged | 0305 fixed: the test read a transient count of 1, while the product keeps both notices. 0306-0313 done. 0229 closed. The open log was triaged: dispositions, 4 operator approvals, and 0093 escalated to a sortie. |
| Turnaround #352 | merged | 43 squawks, including the project shell-write hook (0292), Python 3.12 (0135, verified on Concourse Linux and Windows plus an installer build), Playwright 1.64 / Chromium 156 (0138), fresh-install fixes with `openai<3` and `usearch<2.26.5` ceilings (0241), dev-mode asset content keys (0085), and an eval-backed tool description (0207). Seven follow-up squawks were logged (0315-0321). |

## What Went Well
- **The high-risk design review was load-bearing, not ceremony.**
  - Flight 2 Leg 3: the review found the drawer re-renders through `apply()`, so the first design would have done nothing.
  - Flight 3 Leg 2: the review's coverage table showed the inherited "only these tests cover X" claim was half wrong. That prevented a coverage loss against the mission constraint.
- **Measuring before choosing a mechanism.** Flight 1 profiled per-test cost first. The answer (the per-test app build, guard re-walks, the `serve_forever` poll) came from the profile rather than from the xdist idea, and xdist is no longer needed for the unit tier.
- **Witnessed behavior tests found a real product gap.** The routine-log test's first run found `run=none` on pre-chat failures. Unit tests had encoded the same wrong premise from the spec.
- **Batching the squawk log by shared files.** The triage agent read the whole log against current code. It found no squawk already fixed by later work and grouped the rest by shared files, so 43 squawks went through about 20 Developer passes with one batch review and one full gate. The operator asked for exactly one full browser run, and that held.
- **The shell-write hook (0292) worked on day one.** It blocked heredoc writes into `tests/` from four crew in the run it landed in. Before it, the edit-only rule (0286) slipped in Flight 2 (2 of 4 legs), Flight 3 (one artifact) and #351 (three times).
- **The quiet-host discipline paid off.** Briefing "let the load settle after the unit tier" made the Flight 3 and #352 browser readings usable for budgets. The Flight 2 reading, without that brief, was not.

## What Could Be Improved
- **Prose claims in specs go unverified.** Citation audits check code locations, not the claims a spec makes in prose: stored state (Flight 2 Leg 2: "`_fail_early` has no run id") or test coverage (Flight 3: "only these tests cover 0o600").
  - Flight 2's version cost a post-landing fix pass, a second 13-minute witnessed run and a re-review.
  - Flight 3's was caught only because the leg was tiered high-risk.
- **Absolute gate criteria against a known flake.** Every full gate this mission read rc=1 until 0305 was fixed, so `rc=0` criteria were waived after the fact. Gate criteria should carry the triage rule ("rc=0, or one failure that passes isolated and is logged").
- **Squawk-log rot.** By the end of Mission 33, about 50 routine squawks were past the 30-day mark, the oldest at 45 days. `squawk list` flags staleness but offers no disposition workflow. The triage that cleared it was improvised: a read-only agent, then operator decisions.
- **Crew background-task hygiene.** In #352, several crew finished but left background `sleep` timers running. One missed its own finished unit run until the operator flagged it. Each needed a nudge or a stop from the Flight Director. Squawk-status lines were also flipped with `sed -i` by most crew; the hook covers only source directories.
- **Cross-cutting changes in a turnaround.** The Python 3.12 move (0135) changed CI, packaging and docs in one squawk, and dropped a space in the Linux Dockerfile that no test covered. The batch Reviewer caught it, and a pin test now exists. Turnaround-sized changes that touch packaging need a packaging check, not just unit tests.
- **Operator-only steps blocked progress** (the operator's own answer). An expired `fly` login held the Concourse verification of 0135 and 0165 until the operator logged in. The final gate was run first so the wait cost nothing, but credential checks belong at the start of a run that needs them.

## Lessons Learned
- **Verify the facts a spec states, not just its line numbers.** Where a leg's spec asserts how data is stored, or what a test alone covers, tier the leg high-risk or verify the claim at design time. Observability criteria should be written as joins to stored state (log id equals stored row id).
- **A count that is right "in time" is a race.** 0305, 0314 and 0315 all read transient state: one notice before the second renders, an outcome of `running`, a telemetry max before the model-limit fetch lands. Wait on the terminal or settled state, never on "truthy" or "first seen".
- **A source-scan guard needs a planted violation.** Pre-filtered guards can quietly stop firing (0306). Every new guard this mission (0307, 0309, 0280) shipped with one.
- **Dependency ranges drift without the lock.** A fresh `pip install -e` broke four test files through openai 3, FastAPI 0.162, httpx2 2.16 and usearch 2.26.5+. Ceilings with a reason and a lift trigger (0319) beat silent pins.
- **Log the flake the moment it appears.** 0305's notes in each debrief ("failed in 2 of 2, 3 of 3 gates") made it the operator's first priority. Without them it would have been accepted as noise.

## Methodology Feedback
Plugin version for all entries: mission-control 1.2.3. These restate flight-debrief observations; the sweep should count each occurrence once.

1. **Unverified prose claims in leg and flight specs** (agentic-workflow Phase 2a; flight Citation Audit). **Methodology observation.**
   - What happened: the citation audit covers code locations, while specs also carry factual claims about stored state and test coverage.
   - Expected: those claims are verified like citations.
   - Cost: a post-landing fix pass, a second 13-minute behavior-test run and a re-review in Flight 2. Flight 3 was caught only by a high-risk tier.
   - Occurred in 2 of 3 flights (Flight 2 obs 1, Flight 3 obs 1).
2. **Absolute gate criteria versus the project's flake-triage rule** (agentic-workflow Phase 2a, writing acceptance criteria). **Methodology observation.**
   - What happened: a gate criterion said `rc=0`, while a known flake made every gate rc=1.
   - Cost: criteria waived after the fact, with an operator question at each debrief.
   - Occurred in Flight 1 (obs 3), with the same pattern at the Flight 2 and Flight 3 debrief gates.
3. **Design review as the working safeguard** (agentic-workflow Phase 2a). **Methodology observation (credit).** It materially changed a leg in Flight 2 (Leg 3) and Flight 3 (Leg 2). Recorded so a sweep reads it as load-bearing.
4. **No disposition workflow for a stale squawk log** (squawk skill, List verb). **Methodology observation.**
   - What happened: `list` flags stale squawks but gives no path to triage them (still valid? fixed? defer with trigger? merge?).
   - Cost: about 50 stale squawks by mission start. Clearing them took an improvised read-only triage agent, an operator decision round and two turnarounds.
   - Occurred once, at mission level (#351).
5. **Behavior-spec setup assumptions are validated only at run time** (behavior-test Phase 1 / AUTHORING). **Methodology observation.**
   - Cost: one full witnessed run and a spec re-authoring.
   - Occurred in Flight 2 (obs 3).
6. **Live-mode relay latency and false "cannot be resumed" reports** (behavior-test Execution Modes). **Methodology observation.**
   - Cost: a 29 s relay slip that crossed a timing window and contributed to a failed checkpoint.
   - Occurred in Flight 2 (obs 4).
7. **The Citation Audit does not track squawk state** (flight skill). **Methodology observation**, small.
   - Cost: re-scoping at leg design.
   - Occurred in Flight 1 (obs 2).
8. **A mission scaffolded `planning` while its flights were `ready`** (routine-maintenance scaffold, agentic-workflow Phase 1). **Local lesson.** Cost nothing observable: a one-line hand transition. Flight 1 obs 1.
9. **Crew writes through the shell against the edit-only rule** (project rule 0286). **Local fix, done.**
   - Occurrences: Flight 2 (2 legs), Flight 3 (1), #351 (3), #352 (most crew, on squawk status lines).
   - The project PreToolUse hook (0292) now blocks it for source directories.
10. **Crew background-task hygiene** (project crew file). **Local fix, done in this debrief.** `.flightops/agent-crews/leg-execution.md` now tells crew to wait on completion notifications, to start no `sleep` or `pgrep` waits, and to leave nothing running when they report. Occurred in #352.
11. **Fresh debrief metrics on a loaded host** (project crew file `flight-debrief.md`). **Local fix, done in this debrief.** The rule now says to wait for load below about 1.0 between the unit tier and the browser run. Occurred in Flight 2 (cost: a reading that could not be used for budgets); Flight 3 avoided it by brief.
12. **One Developer per squawk, run in sequence** (squawk skill, Complete step 3). **Local lesson.**
    - For a 43-squawk batch, one Developer per small group of squawks sharing files worked well. It kept shared files consistent, and each squawk still got its own record and sign-off. The single batch Reviewer still found the one blocking defect.
    - Nothing observable was lost, so this is not an observation.

## Action Items
- [x] ~~Fly **sortie 07** (agent tool overrides) next~~. *Corrected 2026-11-03: sortie 07 had already flown and merged in PR #346 on 2026-10-31. Only its optional HAT was open, and the operator skipped it and closed the sortie as `completed`.* Next, run `/mission-control:routine-maintenance` for a fresh inspection (operator decision). Sortie 07's merge unblocks findings #3, #4 (agent half), #6 and #7.
- [ ] Plan the remainder of **finding #25** (test-only production code: `append_to_session_metadata`, the KB chunk delete/FTS methods, `set_next_run`, Discord REST helpers, `_search_stubs.py`) as a small flight or sortie, using Flight 3's coverage-table method.
- [ ] Plan the **openai 3 / httpx2 migration** as a sortie. It lifts `openai<3` and extends `test_mcp_httpx_guard`'s approach to the provider layer.
- [ ] **Browser-tier runtime:** split or trim the longest lanes (`routing`, `agents`). Re-budget the contracts lanes after a second quiet reading on Chromium 156 (they ran 334/162/48 s against 600/330/90 s budgets).
- [ ] **Unit-tier ceiling** of about 260 s in CLAUDE.md (Flight 1 Recommendation 2). This still needs an operator decision on the number.
- [ ] **Escalated squawk 0093** (same-named knowledge bases): a small sortie to choose the disambiguator.
- [ ] Next turnaround: the 16 open squawks, led by 0315 (the full gate's only failure) and 0316 (the one Concourse unit failure).
- [ ] Document the drawer render-key and encode-once broadcast patterns in `the_one/agents.md` if a later inspection still finds them missing. The Architect's grep found no convention entry for either.
- [x] Crew file: quiet load between test tiers in the debrief metrics rule (`.flightops/agent-crews/flight-debrief.md`).
- [x] Crew file: background-task hygiene in the Implement prompt (`.flightops/agent-crews/leg-execution.md`).

# Flight Debrief: Data safety and routine observability

**Date**: 2026-11-02
**Flight**: [Data safety and routine observability](flight.md)
**Status**: completed
**Duration**: 2026-11-02 – 2026-11-02 (one session)
**Legs Completed**: 4 of 4
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
- **The stale connector save no longer drops a paired peer (squawk 0288).** A red test proved the defect at `b497312f` (`assert ['a'] == ['a', 'b']`). The editor now sends `allowlist_peers_base` (the peers it loaded or last saved), and `update_connector` keeps every stored peer that is not in that base. A peer the operator removes still goes; a peer removed elsewhere is not re-added. A PUT without the key keeps the old replace semantics.
- **Routine work is readable from the log alone.** One INFO line per scheduler decision (spawn, catch-up, missed, still-running skip, changed-since-listing skip), run start and outcome, proposal decision (applied, pending, approved, superseded, dismissed) and purge sweep (counts always, zero sweeps included). Ids are bare, agent names repr-quoted, prompts never logged. The behavior test `routine-run-observable-from-logs` passed 6/6 on its second run; every logged id joins to a stored row.
- **Session pushes cost less.** The agent drawer renders only when its render key changes (0 rebuilds for a push while closed, and while open with an unchanged count); `sessions_changed` is JSON-encoded once per broadcast (byte-identical to Starlette's `send_json`).
- **An agent Save before the model list loads keeps the stored model (squawk 0228, completed).** The stored model stays selected while the list loads and after a failed load; the select is described by its live status line (`aria-describedby`).

### Mission Criteria Advanced
- "A stale connector save keeps a paired peer" — met (Leg 1).
- "Routine runs are reconstructable from the log" — met (Leg 2 plus its behavior test).
- "Session pushes cost less" — met by structure (encode once, 0 rebuilds), **not re-measured**: the inspection's 24 ms per push at 5k sessions and 106 ms / 7.3 MB at 20k were not re-run (the leg made it optional).
- Remaining: "Dead code removed" (Flight 3).

### Checkpoints
All three met: the 0288 red test recorded; routine log lines visible in a scratch instance's log (behavior test 2026-11-02-19-15-26); drawer rebuild count 0 for a push while closed (`test_a_sessions_push_does_not_rebuild_a_closed_drawer`).

## What Went Well
- **Design review caught a dead design before code.** Leg 3's first spec guarded the drawer's own store subscription; the reviewer found that `areas/chat.js` re-renders the drawer through `renderPane` → `render(view)` → `apply()` on every push, so the guard would have changed nothing. The rework (render key in `apply()`) passed a second review and its tests were falsified.
- **Red first, then fix** in Leg 1, and every falsifiable new test was falsified (Leg 1 AC1 and the editor test; Leg 2 zero-sweep and no-prompt tests; Leg 3 AC1 and AC4; Leg 4 AC1, AC2, AC2b, AC3; the `aria-describedby` assertion).
- **The behavior test earned its cost.** Its first run (partial, 4/6) found a real gap the unit tests could not: a run that fails before its chat exists, and a missed decision, were logged without the stored run id, so those lines could not be joined to the runs table. It was fixed and the re-run passed 6/6.
- **Legs designed ahead in parallel with implementation.** Legs 2–4 were designed and reviewed while Leg 1 was implemented; implementations ran strictly one at a time, so the shared tree never saw two test runs at once.
- **The mission constraint was honoured by design**, not by luck: Leg 1 rejected a 409 and Leg 4 rejected "disable Save" because both are new operator-visible behaviour.

## What Could Be Improved

### Process
- **The `run=none` premise came from the Flight Director's own leg spec.** Leg 2 said "`_fail_early`, which has no run id before insert: log `run=none`" without checking the code (it inserts a row). The Developer wrote unit tests that pinned that premise (`test_log_fail_early_has_no_run_id`), so the unit tier could not catch it. Leg 2 was tiered low-risk and skipped design review; a review would likely have caught it. The mission's goal ("reconstructable from the log") implied the right criterion — every logged id joins to a stored row — but it lived only in the behavior test.
- **The behavior spec's setup was never dry-run.** The first run hit five setup assumptions: a mock provider needs `base_url`; the routine body nests `start`/`repeat` under `schedule`; `next_run_at` rounds up to the minute (so "late_s ≥ 180" needed a later restart); a one-minute repeat crosses the read window (worsened by a 29 s relay delay in the Flight Director's restart); and a deleted provider fails routine C at chat creation, not at restore. That cost one full witnessed run (~13 minutes).
- **Squawk 0286 (no helper-script writes to source or test files) slipped twice.** Leg 2 inserted `import logging` into three test files with `sed -i`; Leg 4 appended its tests with a `cat >>` heredoc, which also left an import-order lint error the reviewers did not catch (the Flight Director's own `ruff check` found it). Both were insertion-only (checked against HEAD). The rule was in every spawn prompt, so prompt wording alone is not holding it.
- **No full gate ran in-flight.** Each leg ran its owning lanes; the first `--parallel 3` run was the debrief's.

### Technical
- **`agent-drawer.js` is at 799 of 800 lines** (`test_area_module_size`): Leg 3 compacted comments to fit. The next drawer change needs a split first.
- **The drawer render key is a hand-maintained input list.** A future input to `renderContent` that is not added to `renderKey()` gives a stale drawer, silently; the tests pin today's inputs only.
- **`allowlist_peers_base` is a one-field protocol.** It fits a server-appended set; it does not generalise to scalar or text fields, and a client that omits the base silently gets last-writer-wins.
- **Every `the_one` log line is written twice** under `the-one serve` (logger format plus a truncated rich-console copy), contradicting `configure_logging`'s docstring; the behavior spec greps logger-format lines only (squawk 0308).
- **Scheduler decision formatting is repeated in four branches**, and nothing pins the log vocabulary as a whole (squawk 0309). `ProposalOp.run` hands its id back by writing into the caller's dict (squawk 0310).

### Documentation
- agents.md gained the merge rule (Connector subsystem contract), "Routine log lines", the `broadcast_to_all` and render-key clauses and the model-picker loading rule; SECURITY-MODEL.md "Routines" gained the log-content rule. The flight spec's Technical Approach is annotated with the as-built Steps 2 and 3.

## Test Metrics

All numbers are from the **debrief's fresh run on `0cd3b1ac`** (the flight ran no full gate, so the crew file's reuse rule did not apply), compared against the [Flight 1 debrief](../01-test-suite-runtime-ii/flight-debrief.md).

**Unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`, start load 0.17): 8607 passed, 15 skipped (the expected count under netns), 0 failed; pytest 243.35 s (wall 4 m 18 s). Flight 1: 8577 passed, 12 skipped, 229.33 s (solo, without netns). +30 tests from this flight (`tests/test_connector_stale_save.py` 16, plus the routines, purge and session-changes additions); the +3 skips are netns's root-only skips, not new ones. +14 s, partly netns; inside the 300 s standing target.

**Browser tier** (`--parallel 3`, `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1`): `PARALLEL_RESULT rc=1 total=2235s lanes=17 failed=chats-transcript`. **Start load 1.19** (residue of the unit run that had just finished), above the quiet-host bar of ~1.0, so under squawk 0259's rule this reading **does not count for budgets**. Operator decision: record it, no re-budget; re-measure at the next quiet-host gate.

| Lane | This run (s) | Budget (s) | Flight 1 (s) |
|---|---|---|---|
| routing | 628 | 720 | 564 |
| contracts-controls | 601 (OVER BUDGET by 1 s) | 600 | 509 |
| agents | 596 | 630 | 512 |
| agent-tabs | 420 | 510 | 407 |
| chats | 415 | 420 | 370 |
| library | 384 | 420 | 348 |
| providers | 373 | 420 | 363 |
| shared | 366 | 420 | 362 |
| knowledge | 328 | 420 | 308 |
| settings-tools | 327 | 330 | 271 |
| chats-transcript | 315 (rc=1) | 390 | 291 |
| mcp | 314 | 330 | 268 |
| mcp-connection | 313 | 390 | 291 |
| contracts-overlay | 312 | 330 | 246 |
| settings | 310 | 360 | 286 |
| agent-routines | 266 | 300 | 245 |
| contracts-chat | 71 | 90 | 61 |

Every lane is +5% to +27%, including lanes this flight did not touch (`contracts-overlay` +27%, `contracts-controls` +18%, `mcp` +17%). The three lanes that gained tests (`chats` +12%, `agents` +16%, `library` +10%) moved no more than the untouched ones, so the uniform shift points at the start load, not the flight's code. Worth watching at the next quiet reading: `contracts-controls` (601/600), `chats` (415/420), `settings-tools` (327/330).

**Full gate:** 243 s + 2235 s ≈ 2478 s (41.3 min), inside the 43 min target recorded at Flight 1, with headroom down from ~5 min to ~1.7 min on this (loaded) reading.

**Flakes on this run:** one, squawk 0305 (`test_continue_sends_exactly_one_message_and_the_button_goes`, `:725` "Actual value: 2"), 3 of 3 isolated re-runs passed; accepted by name. It has failed in **2 of 2** full gates (Flight 1's and this one), so a full gate cannot currently read rc=0. Squawk 0229 did not recur (and 10/10 isolated after Leg 4).

## Deviations and Lessons Learned

| Deviation | Why | Disposition |
|---|---|---|
| Leg 3 reworked at design review | the subscription guard was bypassed by `renderPane` → `apply()` | render key in `apply()`; cycle 2 approved |
| Leg 2 follow-up fix pass after landing | behavior test found `run=none` on stored rows | `_fail_early` logs after insert; `decision=missed` carries `run=<id>`; tests assert the logged id equals the stored id |
| Behavior spec re-authored after its first run | five setup assumptions wrong | corrected spec, re-run 6/6; both run logs committed |
| Leg 2 touched `the_one/routines/proposals.py` (not in its file list) | the applied proposal id was needed for its line | accepted by the Reviewer; follow-up squawk 0310 |
| Restart at 19:04:54 instead of the planned 19:04:25 (run 1) | relay latency to the Executor | recorded; the corrected spec tolerates B's scheduled runs |
| Two squawk-0286 slips | `sed -i` and a `cat >>` heredoc on test files | insertion-only, checked; carried here |
| Debrief browser gate started at load 1.19 | started straight after the unit run | recorded as a non-budget reading (operator decision) |

## Key Learnings
- **For observability work, the acceptance criterion is a join, not a format.** "Every logged id resolves to a stored row" would have failed Leg 2's unit tests on day one; per-line format assertions passed with the wrong id.
- **A claim about stored state in a leg spec is a citation and needs the same check as one.** "Has no run id" was a code claim that nobody looked up.
- **Freshness fixes must find every entry point.** The drawer had two render paths; the one-place-to-guard is the function both reach (`apply()`), not the subscription.
- **Witnessed tests need a dry run of their setup.** API shapes, rounding and timing windows are cheap to check with a few curls and expensive to discover in a witnessed run.
- **Leave the load to settle between the unit tier and the browser gate** when the reading is meant to count (a 1.19 start invalidated a 37-minute run for budgeting).

## Methodology Observations

All in mission-control **1.2.3**.

1. **agentic-workflow, Phase 2a (risk tiering).** The skill tiers a leg low-risk when it is "additive, single-surface work within established patterns". Leg 2 fit that, skipped design review, and its spec carried an unverified claim about stored state ("`_fail_early` has no run id") that the Developer then encoded in tests. Expected: an unverified stored-state claim is caught before implementation. Cost: a post-landing fix pass, a second witnessed behavior-test run (~13 minutes) and a re-review. The skill's citation audit covers file and line references but not factual claims about data or lifecycle that the spec makes in prose.
2. **agentic-workflow, Phase 2a (design review) — worked as intended.** Leg 3's review caught a design that would have had no effect (a second render path). Expected and delivered; recorded as a credit, because it is the pattern that a later sweep should not mistake for noise.
3. **behavior-test, Phase 1 (spec validation).** The skill validates the spec's shape (sections present) but not that its setup actions work against the system (request bodies, timing). The first run of `routine-run-observable-from-logs` spent its two failing checkpoints on setup assumptions (wrong request shapes, a timing window), not on the property under test. Expected: setup errors surface before agents spawn. Cost: one full run and a re-authoring. A "dry-run the setup actions" step, or AUTHORING.md guidance to do so when the spec is written, would have caught all five.
4. **behavior-test, Execution Modes (re-spawn vs live).** Live SendMessage continuation was available and used. Two quirks cost relay turns: both run-2 agents reported "my toolset lacks SendMessage, so I cannot be resumed" after every step, although resumption by the Orchestrator worked throughout. And the Orchestrator-side wait (a background `sleep` to a wall-clock target) then a relay message added ~29 s of latency before the Executor's restart, which mattered for a timing-bounded step. Expected: a wait-then-act step lands within a few seconds of its target. Suggestion for the skill: let the Executor perform a wall-clock-targeted wait itself inside one shell invocation (the skill's own "MEASURING A TIME BOUND" rule, applied to waits).
5. **flight-debrief, Phase 2 (Developer interview, fresh metrics).** The skill tells the Developer to "run the full test suite once"; this project's crew file adds the quiet-host rule only by reference to CLAUDE.md. The Developer ran the browser gate immediately after the unit tier, at load 1.19, so the 37-minute reading could not be used for budgets. Expected: the brief says to wait for load < 1.0 between the tiers. Cost: a non-budget reading, decided by the operator at this debrief. (The Flight Director's brief said "if not quiet, wait and re-check" but only for the first check.)
6. **Crew prompt rule adherence (squawk 0286, project rule).** The "no helper-script writes to source/test files" rule was in every implementing prompt and slipped in 2 of 4 legs (as in earlier flights). Prompt repetition is not enough; a mechanical check (a pre-commit hook or the Flight Director diffing for whole-block inserts) is the likely remedy. Recorded for the mission debrief's recurrence count.

## Recommendations

1. **(Critical) Fix squawk 0305 first in the next squawk turnaround** (operator decision): it failed in 2 of 2 full gates, so no full gate can read rc=0 until it is fixed.
2. **(Important) Write observability ACs as joins to stored state, and verify any stored-state claim in a leg spec against the code**; tier a leg high-risk when its spec asserts how data is stored.
3. **(Important) Dry-run a behavior spec's setup (request shapes, rounding, timing windows) when it is authored**, before the first witnessed run.
4. **(Important) Re-measure the browser lanes at the next quiet-host gate** (start load < 1.0, with the load allowed to settle after the unit tier), then re-budget `contracts-controls`, `chats` and `settings-tools` if they hold.
5. **(Minor) Before the agent write-safety block is designed, record in agents.md the split this flight implies:** merge-against-base for server-appended collections (Leg 1's helper shape), `updated_at` + 409 for scalar and text fields (which needs an operator decision on a conflict UI). And split `agent-drawer.js` before its next change.

## Action Items
- [ ] Squawk 0305 — first item of the next squawk turnaround (dated note added).
- [ ] [Squawk 0308](../../../../squawks/0308-app-log-lines-written-twice.md) — each `the_one` log line written twice under `the-one serve`.
- [ ] [Squawk 0309](../../../../squawks/0309-routine-log-vocabulary-guard.md) — scheduler `_log_decision` helper and one routine log vocabulary test.
- [ ] [Squawk 0310](../../../../squawks/0310-proposal-op-id-side-channel.md) — `ProposalOp.run` returns the applied id instead of writing the caller's dict.
- [ ] Quiet-host browser re-measure at the next full gate (Recommendation 4).
- [ ] Optional: re-measure the per-push cost at 5k and 20k sessions in the next maintenance pass (the criterion is met by structure only).
- [ ] Carried, open: squawks 0229 (10/10 isolated after 0228's fix, no root cause shown), 0241, 0306, 0307.

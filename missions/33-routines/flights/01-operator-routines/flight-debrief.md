# Flight Debrief: Operator Routines, End to End

**Date**: 2026-10-29
**Flight**: [Operator Routines, End to End](flight.md)
**Status**: completed
**Duration**: 2026-10-28 to 2026-10-29.
- **2026-10-28:**
  - planning from `main` at `c2366221`, with two Architect cycles;
  - per-leg design reviews;
  - Batch A, legs 1-5, the backend (`e8341d88`).
- **2026-10-29:**
  - Batch B, legs 6-9, the UI (`de27abc4`);
  - leg 10, the behavior test, and the landing (`dbc0bc20`);
  - this debrief.

**Legs Completed**: 10 of 10. Five legs were planned, eight after Architect cycle 1, and ten after two leg-design splits (3 into 3a/3b, 8 into 8a/8b).
**Plugin version**: mission-control 1.2.3.

## Outcome Assessment

### Objectives Achieved
- **Setting one up.** On the agent editor's Routines tab (`routines-tab.js`, `routines-form.js`, `routines-form-model.js`, `routines-describe.js`), the operator names a routine and gives it:
  - a prompt;
  - a schedule: once, daily, weekdays, weekly on chosen days, or every N hours;
  - a target: one of the agent's chats (through a real chooser over web and connector chats), a new chat on every run, or the routine's own chat.

  The tab shows each routine's next run and a paged run history, and has Run now.
- **Running.**
  - A lifespan-owned `RoutineScheduler` runs routines unattended, in the operator's zone, across DST.
  - It catches up once within a grace window that scales with the schedule, and records anything older as missed.
  - It survives restarts and follows a zone change made while the app was closed (`routines_zone`).
  - A run takes the chat's turn lock and streams to an open chat.
- **Delivery.** In a connector chat, only the reply is sent. This rests on the delivery step being extracted from the inbound pipeline without changing it (leg 2: 93 tests before and after, with the three test files unedited).
- **Honesty.**
  - The run's message is the routine's: its name, a "Routine" chip, and `data-routine-id`.
  - Every run, skip, miss and failure is in the run history with a reason.
  - The chat drawer shows a chat's routine and lists the agent's routines.
- **Making room.** MCPs folded into a two-section Tools tab, so the editor stays at six tabs (979 px right edge at 1024 px in Chromium).
- **Verification.** The behavior test `routine-connector-delivery` passed 8 of 8 on a dev instance on port 8490. Ports 8484 and 8485 and the default data dir were never touched.

### Mission Criteria Advanced
Flight 1 fully delivered six of the mission's ten criteria:
- **The operator manages an agent's routines.**
- **Routines run on time, unattended.**
- **The reply lands in the target.** Behavior-test-backed.
- **A routine's message says it came from the routine.**
- **Unattended runs are honest.**
- **Routines follow their agent.** Renaming and deleting carry the routines; v45 upgrades in place. Flight 2 adds its proposals record to the same cascade.

The other four are Flight 2's: the Self-configuration split, agent self-scheduling, oversight, and injection flagging with caps.

## What Went Well
- **Per-leg design reviews caught every hard problem before code.**
  - Leg 1: the exact DST-gap algorithm, the three exact-dict pins, and Purge now excluding running runs.
  - Leg 3: a cancel during delivery would have skipped the save. The timeout and shutdown paths needed a bounded await.
  - Leg 5: a hot loop, and the edit-race. The advance became `advance_if_due`, a compare-and-set.
  - Leg 8: the tab-activation ordering.
  - Every review returned "approve with changes", and the code review at each batch end found nothing blocking.
- **Splitting legs at design review worked.** Legs 3 and 8 were each split at review, the plan went from 8 to 10 legs, and every split leg landed cleanly.
- **The characterization-first refactor (leg 2) is a model for refactor legs.**
  - It wrote the tests first and passed them against the old code.
  - It used a mechanical "test files unedited" acceptance criterion.
  - It named a divert signal (`[BLOCKED:delivery-split-not-contained]`).
  - The mission's pre-declared split point never had to be used.
- **Run now as a product feature (DD11) replaced a test seam.** The behavior test needed no new `/api/_test/*` route, and the scheduler's own fire was proven too (a one-off fired 0.8 s after it was due).
- **The real-lifespan test fixture** (`tests/_routine_app.py`) let the runner and scheduler be tested end to end in the unit tier, including a real once-routine firing within 10 s and a stop within 8 s.
- **Batch mode held:** two checkpoint commits, one Accessibility Reviewer pass, and a green `--parallel 3` gate before each commit.

## What Could Be Improved

### Process
- **The Batch B commit was delegated to a subagent and carries the wrong co-author** ("Claude Sonnet 5.5" instead of the session's Opus trailer). The skill has the Flight Director commit. Delegating the commit lost the session's attribution reminder. It was left as is, since it was already pushed.
- **Squawk 0283 duplicates squawk 0277,** which was logged one day earlier (Mission 31 F6) for the same 500 on agent create. The mid-flight squawk was logged without searching open squawks for the same surface. 0283 is now marked as a duplicate, and 0277 records the third hit.
- **Leg 9's AC8 (re-budget `agent-tabs`) could not be verified inside the leg.** The project's quiet-host rule allows a re-budget only from a `--parallel 3` run, and a leg runs solo lanes. The criterion moved to the batch gate. Lane re-budgets belong in the batch-gate step, not in a leg's acceptance criteria.
- **Some specs named fields wrongly or missed guard collisions, and execution corrected them:**
  - Leg 10's spec was drafted before the routes existed and had wrong field names (`trigger_kind`, the target body, `config.default_agent`, `content`).
  - Leg 6 missed the router parity corpus and the `tab-mcps` retired-id collision.
  - Leg 7's fourth `facts` element hit the literal-testid guard.

  All were caught in-leg at low cost. Specs that run into guard tests (the 800-line rule, literal testids, the `state.x` scan, lane budgets) should name those guards up front.

### Technical
- **Debt accepted:**
  - a duplicated `nxt` expression in `scheduler._handle`;
  - a function-local import in `runner._resolve_target`;
  - seven `except Exception` isolation blocks in `scheduler.py`, with no test asserting that they log;
  - the advance-to-spawn loss window (documented);
  - the chooser shows a chat's platform on the description line, because `App.ui.searchList` has no badge slot;
  - `agent-drawer.js` was split into `agent-drawer-parts.js` to stay under 800 lines, so the drawer is now two modules.
- **Growth:** `api.py` grew by 411 lines and `app.py` by 240. The routine routes and `_RoutineTurnHost` could move into their own modules before Flight 2 adds the agent-facing tools.
- **A behaviour change outside routines:** the cancel path now tags connector-chat messages operator-only, for every turn. It is deliberate and covered by one regression test (`test_cancel.py`).
- **Coverage gaps (all low):**
  - the Done row and paging past 20 runs have no browser test; both are API-tested;
  - two leg-7 re-join cases rely on existing per-chat behaviour;
  - the 1000+ missed-count branch is tested in the unit tier only.
- **The DM target shape.** A routine delivers to `ChannelTarget(row.channel_id)`, while an inbound DM reply uses `PeerTarget`. Real Discord DM rows carry the DM channel id, and only the stub leaves `""`. The planning citation audit had already flagged this. It was proven on the stub only, never against a real connector.

### Documentation
- The stale "MCPs tab" prose in `agents.md` and the control inventory reached the batch review. Leg 6's sweep covered tests, specs and copy, but not every prose mention. A renamed UI concept needs a whole-repo prose grep as part of the acceptance criteria.
- Docs are otherwise current:
  - CLAUDE.md "Routines (M33 F1)";
  - `agents.md` "Routines (M33)", "Routines tab" and "Routine form";
  - `SECURITY-MODEL.md` "Routines (Mission 33)";
  - `connectors/README.md`;
  - the registry and the inventory.

## Test Metrics

The debrief's Developer ran both tiers once on the landed tree (`dbc0bc20`). The host was quiet at the start: 1-minute load 0.26, no other test process. The tiers ran one after the other. The Architect ran concurrently but only read files.

**Unit** (`THE_ONE_TEST_NETNS=1 make test-unit`): 8092 passed, 0 failed, 15 skipped, 381 s pytest time (6 min 28 s wall). No flakes.
- The 15 skips are the expected netns set.
- Against earlier debriefs:
  - M32 F4: 7604 (323 s);
  - M31 F6: 7845 (349 s);
  - this flight: 8092 (381 s), +247 tests (+3.1%) and +9% wall time.
- **The growth is the routines package:**
  - schedule, 57 tests;
  - repository, 13;
  - runner, classify and scheduler, about 56;
  - the API, the turn path, the delivery split and the v45 migration.
- **The tier's time is creeping faster than its test count.** It is still unprofiled (squawks 0222 and 0234, now carried in six debriefs).

**Browser** (`--parallel 3`, `THE_ONE_REQUIRE_WEBKIT=1`, `THE_ONE_TEST_NETNS=1`): `PARALLEL_RESULT rc=0 total=1742s lanes=16 failed=-`.
- 3708 tests passed, 5 skipped (the unchanged WebKit contract skips).
- No lane over budget, no flakes, nothing re-run.

| Lane | M31 F6 debrief (s) | M33 F1 debrief (s) | Budget (s) | Share of budget |
|---|---|---|---|---|
| routing | 539 | 545 | 600 | 91% |
| agents | 467 | 483 | 540 | 89% |
| contracts-controls | 432 | 446 | 600 | 74% |
| agent-tabs | 298 | 402 | 540 (was 360) | 74% |
| chats | 337 | 345 | 420 | 82% |
| library | 336 | 344 | 420 | 82% |
| providers | 348 | 340 | 420 | 81% |
| shared | 339 | 335 | 420 | 80% |
| knowledge | 300 | 307 | 420 | 73% |
| mcp-connection | 277 | 280 | 390 | 72% |
| settings | 274 | 275 | 360 | 76% |
| chats-transcript | 248 | 268 | 330 | 81% |
| mcp | 260 | 263 | 330 | 80% |
| settings-tools | 251 | 257 | 330 | 78% |
| contracts-overlay | 237 | 239 | 330 | 72% |
| contracts-chat | 53 | 63 | 90 | 70% |

- **Total wall time:** M31 F6 1695 s; the Batch B gate 1724 s; this debrief 1742 s. That is +2.8%, while the test count grew 3.7% (3574 to 3708).
- **`agent-tabs` grew by 35%** (298 to 402 s) from about 35 new routines tests in `test_flow_agent_routines.py` and `_form.py`. The batch-gate re-budget to 540 s (measured 410 s) holds, and this reading is within 2% of it. Flight 2 adds its own self-configuration and routines tests to this same lane.
- **`chats-transcript` rose 8%** (248 to 268 s) from `test_flow_chat_routine_marker.py` (7 tests).
- **The critical path is still `routing` (91%), with `agents` at 89%.** M31 F6 named both as the next to split or re-budget, and both have grown a little.
- **Within-flight full runs:** 1724 s (the Batch B gate) and 1742 s (this debrief). Within-flight unit gates rose from 7975 (leg 1) to 8092 (leg 9).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 3 split into turn path (3a) and runner (3b) at design review | The original leg combined a shared-interface change with a new subsystem, and its review found two high issues | Yes: split a leg when it pairs a shared-interface change with new behaviour |
| Leg 8 split into list (8a) and form (8b) at design review | Rework verdict: the leg was too large, and a new control was needed | Yes, already the practice |
| `agent-drawer-parts.js` split out (leg 7) | The 800-line area-module rule | No: within the rule's intent; leg specs should estimate line growth |
| `tab-mcps` fenced in `RETIRED_SELECTORS`, not in the registry's Retired table | It collides with the live `tab-` prefix row | No: a recorded exception |
| `agent-tabs` re-budgeted from 360 to 540 s at the batch gate, not in leg 9 | The quiet-host rule needs a `--parallel 3` reading | Yes: lane re-budgets are a batch-gate step |
| Cancel path tags connector-chat messages operator-only for every turn | It fixes a visibility gap the run path exposed | Deliberate; recorded |
| The Batch B commit was made by a subagent | FD delegation | No: the Flight Director commits |
| Squawk 0283 logged as a duplicate of 0277 | No search of open squawks before logging | No: search first (Methodology Observations) |

## Key Learnings
1. **A per-leg design review earns its cost on runtime legs.** Every high-risk leg's review changed the design materially: the compare-and-set advance, the cancel-safe delivery, the bounded awaits, the sleep floor. None of these reached the batch review as a defect. The same depth belongs on Flight 2's tool and approval legs.
2. **A characterization-tested extraction made the risky refactor routine.** The mission's pre-declared split point was there in case the connector delivery change proved risky. The characterization tests plus the "test files unedited" acceptance criterion made it a low-risk leg instead. Use that pattern for any extraction from a shared pipeline.
3. **Making the test seam a product feature beats adding a test route.** Run now served the operator, the browser tests and the behavior test, and it widened no test-seam gate.
4. **Stub seams can hide a real shape.** The stub DM's `channel_id ""` made "the same channel" a weak check in step 7. A seam's simplification should be listed in the spec's Out of Scope, with the real-platform proof owned somewhere (here: Flight 3's HAT, with a real connector).

## Methodology Observations
Plugin version 1.2.3 throughout. These are recorded, not judged.

- **squawk, Log verb, step 4 (assign the next number).** The verb scans for the next sequence number but does not ask the logger to search open squawks for the same surface.
  - What happened: during the leg 10 behavior test, the Flight Director logged 0283 for an agent-create 500. Squawk 0277, logged one day earlier, already covers it with the same root cause.
  - Expected: before assigning a number, the Log verb searches open and deferred squawks for the cited symbol or route, and links a recurrence to the existing squawk.
  - Cost: a duplicate artifact, a debrief correction, and a recurrence count that was nearly lost. This is the third time behavior-test seeding has hit this defect.
- **agentic-workflow, Phase 2d (commit) under delegation.** The skill says the Flight Director commits after review. For Batch B the FD delegated the commit to a crew agent, and the commit carries that agent's co-author trailer, not the session's.
  - Expected: the skill states that the commit is not delegated, or that a delegated commit must carry the session's attribution lines.
  - Cost: a wrong trailer on a pushed commit, left as is.
- **agentic-workflow, Phase 2a (acceptance criteria) and project gating rules.** Leg 9's AC8 asked for a lane re-budget. The project's quiet-host rule makes that unverifiable inside a leg, because only a full `--parallel 3` run counts.
  - Expected: the leg-design risk checks ask whether any criterion depends on a measurement that the project allows only at a batch or flight gate, and move it there.
  - Cost: a deferred criterion, carried by FD notes to the batch gate. There was no rework.
- **flight-debrief, Phase 2 (the Developer's full test re-run), the third debrief running.** The Developer re-ran both tiers on a tree unchanged since the landing gate: about 36 minutes (unit 388 s, browser 1742 s). The results matched the Batch B gate within 1% (1724 s) and the unit count exactly.
  - The same observation is in M31 F5 and M31 F6. Expected: the skill accepts a recorded full run on the same commit.
  - Cost: about 36 minutes of host time per debrief.
- **flight, Phase 5 (draft behavior tests at planning).** The spec drafted at planning, before any route existed, needed four field-name corrections at leg 10.
  - That is the intended trade (the apparatus is fixed early), and the leg that finalized it was told to re-check every step. It worked as designed.
  - Recorded as a positive data point: the "finalize the spec against the landed code" step in the behavior-test leg is what made the draft-early rule cheap.

## Recommendations
1. **Fix squawk 0277 before Flight 2's behavior test.** The agent-create 500 has been hit in three behavior-test runs across two missions. Flight 2's live test seeds agents too. It is one bounded write-boundary check, `create_agent`/`update_agent` returning 422 on an unknown provider or knowledge base. *Important.*
2. **Plan Flight 2 on Flight 1's seams. Do not fork them.**
   - **Shared rules:** the agent's routine tools call the same `AgentRoutineRepository`, `_routine_schedule` validation, `limits.py` caps and `_poke_scheduler()`.
   - **Origin:** `Routine.created_by` already exists.
   - **Approval:** pending agent changes must never be eligible in `list_due`.
   - **Decisions to make explicitly at planning:**
     - whether an agent edit or the in-flight run's advance wins when an agent edits the routine that is running it;
     - whether an agent may delete the routine that is running it;
     - whether agent-created routines' run history should outlive chat retention, as the audit trail of unattended activity;
     - a frequency cap for daily and weekly kinds, not just `INTERVAL_HOURS_MIN`.

   *Critical for Flight 2.*
3. **Relieve the lanes before Flight 2 adds tests.**
   - `routing` is at 91% and `agents` at 89%.
   - `agent-tabs` will take the self-configuration routines tests.
   - Plan a lane split, such as routines files out of `agent-tabs`, as part of Flight 2's test leg, measured only on a quiet `--parallel 3` run. *Important.*
4. **Prove DM delivery on a real connector in Flight 3's HAT.** The behavior test proved delivery on the stub, whose DM `channel_id` is `""`. One real Discord DM routine during the HAT closes the gap. *Important.*
5. **Move the routine routes and `_RoutineTurnHost` out of `api.py`/`app.py`** when Flight 2 adds the agent-facing surface. Do it as part of the leg that touches them, not as a separate refactor. *Minor.*

## Action Items
- [x] Mark squawk 0283 as a duplicate of 0277, and record the third hit on 0277 (done with this debrief).
- [ ] Squawk 0277: complete it before Flight 2's behavior test (Recommendation 1).
- [ ] Flight 2 planning: the seams and the explicit decisions in Recommendation 2, and the lane split in Recommendation 3.
- [ ] Flight 3 HAT: a real-connector DM routine (Recommendation 4).

## Follow-up Squawks
No new squawks were logged:
- The only small defect found was already squawk 0277.
- The accepted nits (the duplicated `nxt`, the local import, the missing logging tests for the isolation blocks) are cheaper to fix in Flight 2's legs that touch `scheduler.py` and `runner.py` than to track separately.
- Everything else needs a design call and is a Flight 2 or Flight 3 input.

Carried:
- 0277 (Recommendation 1);
- 0278 (the CLAUDE.md credential wording; leg 10 worked around it through its Inputs);
- 0222 and 0234 (profile the unit tier).

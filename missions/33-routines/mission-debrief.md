# Mission Debrief: Routines

**Date**: 2026-10-30
**Mission**: [Routines](mission.md)
**Status**: completed
**Duration**: 2026-10-28 (Flight 1 planning) - 2026-10-30 (Flight 4 landing, release v0.13.0)
**Flights Completed**: 4 of 4. Three were planned (operator routines, agent routines, the closing HAT); Flight 3, "Schedules and limits", was added at its own planning, and the HAT became Flight 4.
**Plugin version**: mission-control 1.2.3, for every flight and this debrief.

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| The operator manages an agent's routines | met as amended | Routines tab: create, edit, switch, delete, Run now, next run and run history, a calendar recurrence (Flight 3) and a Starts group with "Immediately" (F4 L04). The target part (and its chat picker) was removed at the HAT: every run starts a new chat. |
| Routines run on time, unattended | met | Lifespan scheduler, operator zone and DST proven at the unit tier with a frozen clock; one-offs finish; restart survival walked at HAT Part H, which found and fixed F-H1-1 (a startup catch-up run's chat held only the system message). |
| The reply lands in the target | met as amended | Judged against the amendment: the run's message and reply land in a new chat titled with the routine's name. Connector delivery was removed (schema v49); a prompt that asks for a platform post uses the agent's own `send_to_platform_channel`. Part D, the real Discord DM, was dropped. |
| A routine's message says it came from the routine | met | "Routine" chip and routine attribution in the transcript; the drawer's "Routine" fact and its Routines group. |
| Unattended runs are honest | met as amended | Ran, Caught up, Missed, Skipped, Stopped, Interrupted and Failed, each with a reason. "Chat gone" no longer applies, and "Chat busy" cannot arise with a new chat per run. Runs now fail closed: no turn or no saved message is `failed`. |
| The Self-configuration tab governs two things | met | Agent prompt and Routines cards, each with an enable and an approval switch (mockup SC2, F4 L06). Routines off by default; approval off for a new agent (C8 reversed, F4 L05); existing agents keep their stored values. |
| An agent schedules its own routines when allowed | met | Four native tools behind the Routines item; scoped to the agent. `agent-schedules-follow-up` 7/7 (run 2026-10-30-20-45-42). Gap accepted by the operator: a follow-up asked for in a DM reaches the person only if the routine's prompt makes the agent post. |
| Agent routine changes are overseen | met | Pending queue with approve, dismiss, stale 409 and override; every change in History. |
| Injected content cannot plant a routine unnoticed, and routines are bounded | met | "Check this" flag from `agent/taint.py`, proven by scripted tool calls; one active cap, a 1-minute floor, 5 writes a turn, refusals with a reason. Evals: `gpt-oss:20b` obeys a planted page often (4/20 best-effort miss at the close), and every planted routine is flagged. |
| Routines follow their agent | met | Rename and delete cascade; migrations v45-v49 with migration tests; the upgrade kept every agent's self-configuration settings. |

### Overall Outcome
Yes. Agents act on a schedule, the operator can see and govern every routine and every agent change, and v0.13.0 carries it. The outcome as first written ("a reply lands in a chosen chat, and a connector chat's reply goes out to its channel") was not the right goal by the end. At the HAT the operator found the target model hard to understand ("It's limiting, but intuitive") and removed it, with connector delivery, in favour of a new chat per run and the agent's own platform tool. The mission delivered the simpler product, but it built the more complex one first: most of Flight 4 was spent removing and reshaping work from Flights 1-3.

The release is not yet out. The v0.13.0 tag run (41134183836) built all packages and then failed at upload because the private repo hit its Actions artifact storage quota. 71 stale artifacts (3.8 GB) were deleted on 2026-10-30, and the failed jobs need a re-run once GitHub recounts usage.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1. Operator routines, end to end (#335) | completed | 10 legs (5 planned). Store, scheduler, unattended run path, connector delivery extracted from the inbound pipeline under characterization tests, the Routines tab, the routine marker and the drawer. Run now replaced a test seam. |
| 2. Agents schedule their own routines (#336) | completed | 6 legs. Self-configuration split into two items, native routine tools, proposals queue, taint flagging, caps, evals in their own tree, the live behavior test. Planned and flown with no planning conversation. |
| 3. Schedules and limits (#338) | completed | 8 legs (5 planned). Calendar recurrence with exact instants (`anchor_at`), a frozen v48 converter, server-side sentences and previews, one cap and a floor, retention for finished routines and proposals. |
| 4. HAT and alignment (#340) | completed | 1 planned leg became 7, plus three fix passes and F-H1-1. Every run a new chat (v49), Routines list and Self-configuration rebuilt from mockups, Start immediately, approval default off, legacy schedule shapes removed, the danger zone reworded, the purge un-arm bug. |

### Flight Patterns
- **Flights 1-3 went smoothly by their own measures.** Every high-risk leg had a design review that changed the design, every batch review passed after small fix loops, and every gate was green. Smooth execution did not mean the right product: none of those reviews could see that the operator would not want the target model.
- **Flight 4 struggled, by design and not by accident.** It was the operator's first look. The fix-vs-feature gate held for every behaviour change (each with a Developer design review that found real defects), and the operator confirmed "Inside the HAT was right".
- **Common across flights:** legs grew at review (5 to 10, 5 to 6, 5 to 8, 1 to 7); crew agents found ways around the "edit only through the edit tool" rule in three flights; the `routing` and `agents` lanes sat near budget until Flight 3 re-budgeted them.

## What Went Well
- **Design reviews before code, every time.** Two Architect cycles per flight and per-leg reviews on high-risk legs caught defects that would have shipped silently: the compare-and-set advance (F1 L5), cancel-safe delivery (F1 L3), the in-transaction order of precheck, caps, write and proposal (F2), the spring-forward drift in the v48 converter and the "after N" counter (F3), the `normalize`-level now-start that could not work (F4 L04).
- **Seams held, so a reversal was cheap to make.** `runner.py` imports nothing from `interfaces/` (it reaches the app through `_RoutineTurnHost`), `service.py` is the single write path for REST, tools and approval, and migrations are frozen helpers (`_v48_*`, `_v49_*`). Flight 4 removed the target model in two legs with no target residue in code (Architect grep of `the_one/routines`, `routines_api.py` and the routines JS).
- **Characterization first for risky extractions** (F1 L2, F2 L1): tests written against the old code and a "test files unedited" criterion made the delivery split and the service move routine.
- **Mockups at the HAT.** Eight artboards settled three surfaces in minutes each (Routines layout A, Starts S1, Self-configuration SC2). The operator: "really well done on the mock ups".
- **A restart in the HAT found a lifecycle race** (F-H1-1, `_restore_session`) that no unit test interleaved. The fix re-checks under the lock, and runs now prove their effect before they report success.
- **Live-mode behavior tests** (Flights 2-4) with one Executor and one Validator kept checkpoints conclusive, and a live local model proved that the tool descriptions alone teach the schedule shape.
- **Environment hygiene throughout.** Scratch instances on 8490 with recorded PIDs, `/proc` checks, nothing touching 8484 or the default data dir.

## What Could Be Improved
- **The surfaces were designed from the data model, and the operator first saw them three flights later.** Targets, the chat chooser, gone-chat semantics and connector delivery were built in Flights 1-3 and removed in Flight 4. The cost: six added legs, three fix passes, a migration undoing columns added two flights earlier, and an eval re-baseline. The operator: "when its new feature work, we should prioritize user experience. Had we done some mock ups prior to the work, we may have avoided some of this rework." The causes were that no mockups were made, there was no early look by operator choice, and a criterion was phrased in design terms ("the reply lands in the target").
- **Judgement calls accumulated without a forcing function.** 26 *(ajc)/(J)/(FD)* calls reached the closing HAT. The costliest design choice was never tagged as a call, because it was written into a criterion. The operator's view at this debrief: the autonomy was right, but costly calls (data shape, behaviour) should be shown at the end of the flight that makes them.
- **A written crew rule did not hold.** Falsify-by-edit (squawk 0284) and no scripted source rewrites (squawk 0286) were each in the crew prompts and were each broken: a whole-file restore (F2), a helper script that truncated `scheduler.py` (F3), and `sed -i` and heredoc appends by three of seven Developers (F4). Every breach was self-reported and verified by a reviewer, at the cost of extra full-diff reads.
- **Docs of a reversed model.** Flight 4 cleaned code and tests but left the reversed model in `the_one/agents.md`: line 2837 still ends "A target left out is not re-validated, so a `missing` chat target may stay until re-pointed", and the "routine turn path" (2840) and "runner" (2845) headings still say "no runner yet" and "nothing schedules yet". (Verified at this debrief; the Architect's suspicion that `routines/schedule.py` was dead is wrong: `recurrence.py` and `describe.py` import it.)
- **Release storage.** Each release run uploads about 520 MB of job-to-job artifacts kept 7-14 days. Five releases in three days on top of the Mission 32 dry runs exhausted the private-repo quota, and the v0.13.0 release failed at upload.
- **The eval convention cost about 3 hours for a confounded result** (F4): a same-prompt re-baseline for a scenario change that only removed a check, which the old code could not run fairly.

## Lessons Learned
- **Technical**
  - Unattended work must prove its effect before it reports success (F-H1-1's "ok" run had saved nothing).
  - Any check-then-await-then-mutate on a shared `Session` must re-check under the lock after the await.
  - Store exact instants and render clock times (`anchor_at`); approve a stored computed value verbatim and re-render it at apply (`rezone`); a migration converter is frozen and never calls today's normalizer.
  - Deleting an unshipped feature outright is cleaner than keeping aliases (F4 L07 removed the legacy shapes and `DeliveryResult`).
  - Making the test seam a product feature (Run now, Start immediately) beats adding a `/api/_test/*` route.
  - A HAT that restarts the system finds lifecycle races that unit tests never interleave.
- **Process**
  - For new feature work, show the operator each user-facing surface before legs lock (now squawk 0293).
  - Name a costly design choice as a call, even when it already sits in a criterion, and show it to the operator at the end of the flight that makes it.
  - A HAT that reverses a model owes a whole-repo prose sweep of the old model, not just a code sweep (F1 had the same gap with "MCPs tab").
  - Plan batches by shared files, and enumerate every reader of a derived state when its derivation changes (F3).
  - Lane re-budgets are a batch-gate step, measured only on a quiet `--parallel 3` run.
- **Domain**
  - The operator prefers a model that is limiting but intuitive over a flexible one they must think about.
  - A follow-up an agent writes from a DM does not stand alone in a new chat unless its prompt does; a local model wrote "Hey Alice, did the build finish?" and the run's reply could not tell which build.
  - A new chat per run means volume: a 10-minute routine adds 144 chats a day, bounded only by retention.

## Methodology Feedback
Each finding below is triaged by destination. These restate observations already recorded in the four flight debriefs, so a later `/mission-control:service-report` sweep should count each occurrence once; the source flights are named on every finding. All flights ran on mission-control 1.2.3.

### Methodology observations
These reproduce from the methodology alone, and each cost something observable.

1. **`mission` Phase 5 and `flight` Phase 4/6: no review of user-facing surfaces before legs lock.**
   - **What the methodology did:** the mission and flight skills shape criteria and design decisions, and offer a HAT for alignment, but never ask for a look at a new surface before it is built.
   - **What happened:** Flights 1-3 designed the Routines tab, its targets and chooser, and Self-configuration from the data model. The operator saw them first at the mission-closing HAT.
   - **Expected:** the flight skill prompts for a mockup, or two layout options, of every new or reshaped user-facing surface, approved before leg design.
   - **Cost:** six added legs, three fix passes, a schema migration undoing two flights' columns, and an eval re-baseline. This was the costliest finding of the mission.
   - **Recurrence:** recorded in 1 flight (F4 obs 1), with its cost accrued across Flights 1-3.
2. **`mission` Phase 5 step 3: the criterion screen catches tool names but not a criterion that presupposes a design.**
   - **What happened:** "The reply lands in the target" passed the screen (it names no technology) but fixed the target model as a requirement, so the model was never tagged as a decision to confirm.
   - **Expected:** the screen also asks whether a criterion could be met by a different user-facing model.
   - **Cost:** the target model was carried to the mission close untested with the operator and removed there, with the criterion amended.
   - **Recurrence:** 1 flight (F4 obs 1 and obs 3 name it).
3. **`agentic-workflow` / `flight`: judgement calls carried without a forcing function.**
   - **What happened:** 26 *(ajc)/(J)/(FD)* calls reached the closing HAT. Flight 2 was planned and flown with no planning conversation.
   - **Expected:** costly calls (data shape, behaviour) are shown to the operator at the end of the flight that makes them, or a count triggers a checkpoint.
   - **Cost:** reversals at the end rather than the start, and one long human session to settle them.
   - **Recurrence:** recorded in 2 flights (F2 obs 4, F4 obs 3); calls were made in all three build flights.
4. **`agentic-workflow` crew prompts: a written rule does not stop crew from writing source through the shell.**
   - **What happened:** a whole-file restore during falsification (F2), a helper script that truncated `scheduler.py` (F3), `sed -i` and heredoc appends by three of seven Developers after the rule was in both prompts (F4).
   - **Expected:** the methodology ships or recommends a mechanical guard (a `PreToolUse` hook) for rules a project marks as hard.
   - **Cost:** a file rebuild from `HEAD`, line-by-line diffs and extra full-diff reads by reviewers; a lossy rebuild could have shipped.
   - **Recurrence:** 3 of 4 flights (F2 obs 3, F3 obs 3, F4 obs 2).
5. **`flight-debrief` Phase 2: the full-suite run repeats the flight's own final gate.**
   - **What happened:** the debrief Developer re-ran both tiers on a tree whose source was unchanged since the gate.
   - **Cost:** about 36-45 minutes of host time per debrief, once stopped by the operator.
   - **Recurrence:** 2 of 4 flights (F1 obs 4, F2 obs 1); also M31 F5 and F6. Fixed locally from Flight 3 on (squawk 0285), which worked in F3 and F4.
6. **`agentic-workflow` Phase 3 step 3: the documentation check looks for what was added, not for what was removed.**
   - **What happened:** a renamed concept ("MCPs tab", F1) and a reversed model (the routine targets, F4) left stale prose in `the_one/agents.md`; F4's survives on `main`.
   - **Expected:** when a flight renames or removes a concept, the doc check greps the whole repo for the old term.
   - **Cost:** a batch-review finding (F1) and stale reference text shipped in a release (F4).
   - **Recurrence:** 2 of 4 flights (F1 "Documentation", F4 at this debrief's Architect review).
7. **`agentic-workflow` Phase 2b/2d: legs do not declare shared files.** Two unplanned batch regroupings and a merged commit (F3 obs 2). **Recurrence:** 1 of 4.
8. **`flight` Phase 4: a design decision that changes how a state is derived does not prompt for that state's readers.** The "no runs left" rule surfaced in Architect cycle 2 and the leg 4 review, with a mid-flight DD amendment (F3 obs 1). **Recurrence:** 1 of 4.
9. **`squawk` Log verb: no duplicate search before numbering.** Squawk 0283 duplicated 0277 (F1 obs 1). **Recurrence:** 1 of 4.
10. **`agentic-workflow` Phase 2d: a delegated commit carried a crew agent's co-author trailer** (F1 obs 2). **Recurrence:** 1 of 4.
11. **`agentic-workflow` Phase 2a: an acceptance criterion depended on a measurement the project allows only at a batch gate** (a lane re-budget, F1 obs 3). Cost: a deferred criterion. **Recurrence:** 1 of 4.
12. **`behavior-test` Orchestrator: an added precondition the spec did not have** (an idle wait before F4's step 6). Cost: one round trip, about 4 minutes (F4 obs 4). **Recurrence:** 1 of 4.

### Local fixes
These change this project's own crew files, settings or conventions.
- **Mockup rule** in the flight-design Architect prompt (squawk 0293, open). Operator's chosen shape for the next feature mission: mockups before legs lock, plus one closing HAT.
- **A `PreToolUse` hook against shell writes into source** (squawk 0292, open), backing squawks 0284 and 0286 (both done).
- **Debrief reuses the flight's last full gate** when nothing but artifacts changed (squawk 0285, done).
- **Surface costly calls at the end of their flight.** Operator's answer at this debrief: keep the autonomy, but show data-shape and behaviour calls to the operator when the flight that makes them lands. Belongs in this project's flight-design and leg-execution practice (no squawk yet).
- **Eval convention** in CLAUDE.md "Prompt evals": a check-only scenario change skips the old-prompt re-baseline, and a baseline may be rebuilt from the new-prompt runs when the old code cannot run the new scenarios (F4 obs 5).
- **Release artifact retention:** job-to-job artifacts on the release path are kept 1 day, not 7-14 (this debrief).

### Local lessons
Real, but they cost nothing observable or come from this project's own choices.
- **Live-mode behavior tests** worked in Flights 2-4 although the skill and crew file say `SendMessage` needs an experimental flag; the only cost was "I can't be resumed" noise in reports (F2 obs 2, F3 obs 4).
- **The flight design-review cap** left Flight 3's last cycle-2 fix unreviewed at flight level; the per-leg reviews re-checked it and nothing was lost (F3 obs 5).
- **Parallel legs on disjoint files** saved hours in Flights 2 and 3; lane timings from those windows are not budget readings.
- **Harness notifications** from finished agents with background work, and one refused `gh pr ready` (F2 obs 5, F3 obs 6), recorded for context; Mission 32 saw the same.
- **The HAT form** (one closing HAT for the mission, operator choice) found everything, but late; with mockups up front the operator keeps that form.

## Action Items
- [ ] **Re-run the v0.13.0 release** (`gh run rerun 41134183836 --failed`) once GitHub recounts artifact usage (6-12 hours after the 2026-10-30 cleanup); confirm the release publishes.
- [ ] **Squawk candidate:** release-path artifact retention to 1 day in `linux-packages.yml`, `windows-packages.yml` and `macos-packages.yml` (when called from `release.yml`).
- [ ] **Squawk candidate:** remove the reversed target model from `the_one/agents.md` (line 2837's `missing` chat target sentence; the stale "no runner yet" / "nothing schedules yet" headings at 2840 and 2845). Same file as squawk 0294; complete them together.
- [ ] **One sortie for both follow-ups** (operator decision): follow-up delivery (a follow-up scheduled from a platform conversation should reach the asker: stronger `schedule_routine` text, or carrying the asking conversation as run context; a new capability needs the same taint and "Check this" treatment) and external clients managing routines through the self-configuration MCP surface (reuse `service.agent_change`; decide the per-turn write budget with no `TurnContext`, and whether an unknown `target` key should stay silently ignored).
- [ ] **Watch chat volume from frequent routines** (operator decision: an action item, not a squawk). Revisit with grouping or a Chats filter for routine chats only if it bites.
- [ ] **Open squawks from this mission:** 0288 (stale connector editor wipes a paired peer), 0289 (self-config double refetch), 0290 (failed focus refetch blanks the queue), 0291 (purge flash wording), 0292 (hook), 0293 (mockup rule), 0294 (agents.md patterns and CLAUDE.md trim).
- [ ] **Architecture follow-ups (design, not squawks):**
  - declare the operator-owned agent fields in one set with a test, instead of per-feature pops in `api.py::update_agent`;
  - a generic pending-change queue before a third consumer appears (prompt revisions and routine proposals are two copies of one design);
  - `app.py` session restore is the one path for WebSocket, connectors and routines; split it out the next time it is touched;
  - add the frozen-migration rule ("a migration never imports live domain code") to `agents.md` Project Conventions.
- [ ] **Carried:** profile the unit tier (squawks 0222, 0234; 323 s at M32 F4 to 399 s now, 7604 to 8383 tests); watch `test_purge_loop_catch_up_sweeps_due_db` on a quiet host.
- [ ] **Recommended next:** `/mission-control:routine-maintenance` before the next mission.

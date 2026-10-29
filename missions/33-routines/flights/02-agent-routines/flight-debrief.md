# Flight Debrief: Agents Schedule Their Own Routines

**Date**: 2026-10-29
**Flight**: [Agents Schedule Their Own Routines](flight.md)
**Status**: completed
**Duration**: 2026-10-29. Planning ran from `main` at `6ed89395`, with two
Architect cycles, to `5b607af3`. Then came Batch A, legs 1-3 (`446b7388`);
Batch B, legs 4-5 (`ee4e8c5b`); leg 6, the behavior test, and the landing
(`6dac4478`); and this debrief.
**Legs Completed**: 6 of 6. Five legs were planned; Architect cycle 1 split
the tools leg into tools (3) and evals (4).
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved

- **Agents schedule their own routines.**
  - With the operator's Routines item on, an agent gets four native tools:
    `list_my_routines`, `schedule_routine`, `change_routine` and
    `cancel_routine`. They target `this_chat`, `new_chat`, `own_chat` or one
    of its chats.
  - `RoutineToolProvider` registers them through the factory hook;
    `core.py` is untouched.
  - The tools are seeded only when the item is on, and the switch is
    checked again at call time.
- **One rule set.**
  - The operator's REST routes and the agent's tools write through one
    service, `routines/service.py`, which takes `conn` from its caller.
  - Flight 1's REST tests passed 63/63 unedited across the extraction.
  - `agent_change` applies the change or holds it pending, under raise-only
    caps: 10 active routines, 48 runs a day, 5 writes a turn, a one-off at
    least 1 minute ahead, 20 pending.
- **Oversight.**
  - Every agent change is a row in the v46 `agent_routine_proposals` table,
    either `applied` or held `pending`. Rows are never purged by retention.
  - The operator approves pending rows (stale check inside the transaction,
    with `?override`) or dismisses them.
  - Approval is on by default. Turning the item off withdraws anything
    pending.
- **Injected content is flagged, not trusted.**
  - The shared `agent/taint.py` flags any agent write made after content the
    operator did not write. Notes and routines now use one trust model.
  - A flagged routine's run snapshots its sources on the run's user message,
    so the next write in that chat is flagged too. The live run showed this:
    `routine:check_build_finished` appeared in the step-5 proposal.
- **The Self-configuration tab has two items.**
  - Agent prompt (relabelled) and Routines: switches, a "Waiting for
    approval" queue with the stale/gone/422 paths, and a paged "Changes by
    the agent" history.
  - The Routines tab and the chat drawer show "Made by the agent" and the
    routine flag. Saving a flagged routine's form clears the flag.
- **Evals.**
  - Today's set compared against `m30-platform`: 0 hard failures, sizes
    exactly at the baseline.
  - The routine tools cost 853 tokens when on.
  - A new same-prompt baseline, `m33-routines`, covers three routines
    scenarios.
- **Live proof.** `agent-schedules-follow-up` passed 7/7 on `gpt-oss:20b`,
  with no retry and no model switch:
  - with Routines off, nothing was scheduled;
  - with Routines on, a "check back in 2 minutes" became a flagged one-off
    that fired on schedule and sent only its reply;
  - with approval on, the next change was held pending, then approved;
  - a cancel was applied.
- **Squawk 0277** (agent create and update returned 500 for an unknown
  provider) was completed in-flight, provider only. Its duplicate, 0283,
  closed with it.

### Mission Criteria Advanced

| Mission criterion | How |
|---|---|
| The Self-configuration tab governs two things | Met in full: two items, each with its own enable and approval switch. |
| An agent schedules its own routines when allowed | Met in full: the four tools behind the switch, proven live (behavior test steps 2-4). |
| Agent routine changes are overseen | Met in full: proposals, approval, the stale check, dismiss, history (unit, browser, behavior steps 5-7). |
| Injected content cannot plant a routine unnoticed, and routines are capped | Met in full: DD7 taint at the unit tier, the `routines-planted` eval (gpt-oss 17/20 runs scheduled, all flagged), raise-only caps. |
| Routines follow their agent | Advanced: the proposals table joins the rename/delete cascade (the v46 foreign keys). |

## What Went Well

- **The characterization guard.** `test_routines_api.py` passed unedited
  across the leg 1 extraction, which made the service move safe and gave
  legs 2-3 one place to extend.
- **Design reviews caught real defects before code** (legs 2, 3 and 5),
  and each was high severity:
  - the in-transaction order of precheck, caps, write and proposal;
  - the pause/resume binding path;
  - the `activate` hook and the five callbacks the Self-configuration tab
    needed.
- **Two review checkpoints, not one.**
  - Batch A was the backend, reviewed by a Sonnet code Reviewer, with one
    follow-up fix.
  - Batch B was the evals and UI: a code Reviewer plus an Accessibility
    Reviewer, then a re-check.
  - The re-check found a real functional bug the first pass missed: "Show
    older" stuck disabled after a refetch landed mid-load.
- **Parallel legs on disjoint files.**
  - Legs 4 (evals) and 5 (UI) ran together. Leg 4's model runs took about
    2.2 hours of wall time, and the UI leg finished inside that window.
  - The cost was known and contained: leg 5's lane timings were taken on a
    host at load 8-13, so none was used for a budget.
- **The quiet-host rule held.**
  - Budgets were set only from a quiet `--parallel 3` (start load 0.73):
    `agent-routines` 240 s, `agent-tabs` 540 to 390 s.
  - The split worked: `agent-tabs` fell from 402 s to 293 s.
- **The behavior test in live mode.**
  - One Executor and one Validator stayed alive through `SendMessage`
    across all seven checkpoints.
  - The Validator's spec concerns at `[READY]` became capture requests, so
    no checkpoint was inconclusive.
  - Step 4 ran in parallel with step 3's judgment, because the routine fired
    about 2 minutes after creation.
- **A recon of Flight 1's eval scenario fingerprint** led leg 4 to put the
  routines scenarios in their own tree (`evals/routines/`), which kept the
  `m30-platform` comparison like-for-like.

## What Could Be Improved

### Process

- **The debrief's full-suite run duplicated the flight's own gate** (operator
  finding, see Methodology Observations).
  - The quiet-host gate ran on `ee4e8c5b`. The only later commit touched no
    source or test.
  - The debrief's unit re-run (8237 passed, 15 skipped, 383.5 s) matched.
    The browser re-run was stopped by the operator's decision, and its
    numbers come from the gate.
- **Fix-pass falsification by file backup.** The first accessibility fix
  Developer proved its tests failed by restoring two whole files from backup
  copies. In a shared working tree, a whole-file restore can silently drop a
  concurrent edit. The FD's next fix prompt required "put the fix back by
  editing", which worked. Belongs in the crew file's fix prompt.
- **Leg 4's AC7 (the CLAUDE.md line)** was assigned to leg 5 so that only
  one leg edits CLAUDE.md. That worked, but leg 4's own acceptance list
  still names it, so its AC reads "partly met". When an AC is reassigned,
  move it to the other leg's artifact.
- **The FD set the behavior-test spec status to `ready`.** The spec format
  allows `draft | active | archived`. It was caught and corrected to
  `active` before the run.

### Technical

- **Lanes near budget.** `routing` is at 548 of 600 s (91%) and `agents` at
  484 of 540 s (90%). Both were flagged in Flight 1 and Mission 31, and both
  are flat: less than 60 s of headroom, so a mildly loaded host trips
  OVER BUDGET.
- **`agent-editor-controller.js` is at 781 of 800 lines.** The next
  agent-editor addition needs a split first.
- **Two mechanisms under one tab.** Agent prompt uses the loopback MCP
  source and credential; Routines uses native tools, which the Tools tab
  does not list. It is the same split as notes, now a second instance.
- **`Message` carries a second USER-only marker**
  (`routine_untrusted_sources`, beside `routine_id`). No provider reads
  either, and a regression test pins that, but each marker adds codec
  surface.
- **Per-status history requests.** The history is built from three
  per-status requests merged client-side, because the proposals route
  filters one status at a time. A status-set filter would be simpler.
- **Turning Routines on mid-chat** reaches an open web chat's tool list only
  after the session is rebuilt (DD5, documented). The call-time switch
  check makes turning it *off* immediate.
- **The `peer:{name}` flag on every connector-chat write** (DD7) means a
  routine an operator asks for in their own Discord DM is always "Check
  this". It fails closed, but it is the likeliest source of operator
  friction. This is a HAT item.

### Documentation

- CLAUDE.md, `the_one/agents.md` ("Routines (M33)" and the new
  Self-configuration Routines item), `SECURITY-MODEL.md` ("Routines"),
  `evals/README.md`, `docs/ui-testid-registry.md` (30 new testids) and
  `docs/ui-control-inventory.md` (`noteFlag` `subject`) were all updated
  in-flight. No gaps found.
- The behavior-test spec gained "Reading the run" notes from its first run:
  - the stub inbound call blocks for the whole turn;
  - the stub routine-send shape;
  - the definition of "Done";
  - a deleted routine's proposals read `routine_id` null.

## Test Metrics

**Unit, on HEAD `6dac4478`** (debrief run, quiet host, start load 0.30):
- 8237 passed, 0 failed, 15 skipped (the expected netns count), 383.5 s.
- No flakes.
- Against prior debriefs:
  - Flight 1: 8092 passed, 381 s. Now +145 tests for +2.5 s, so the new
    service, tools, proposals and taint tests are cheap.
  - The Mission 31 close: 7845, about 349 s.
  - The unit tier's slow drift since Mission 31 (281 to 383 s) remains
    squawk 0222's subject.
- The 727 s unit run in the flight log was on a host loaded by leg 4's
  evals.

**Browser, the flight's quiet-host gate on `ee4e8c5b`** (start load 0.73):
- `PARALLEL_RESULT rc=0 total=1774s lanes=17`.
- Against prior totals: Flight 1 1742 s (16 lanes), Mission 31 F6 1695 s,
  so +32 s (+1.8%) for the 17th lane.
- Every lane is within ±2% of Flight 1, except the two split lanes:
  - `agent-tabs` 402 to 293 s;
  - the new `agent-routines` 171 s.
  - The routines tests grew by about 60 s of lane time in all, mostly
    `test_flow_agent_routines_self_config.py`.
- The critical path is still `routing`.
- Over 85% of budget: `routing` 91%, `agents` 90%.

**No flakes** were seen in any gate run this flight. Leg 5's single-lane
runs on the loaded host ran up to about 2x their budgets and passed.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Squawk 0277 completed in-flight, provider only (DD14) | The behavior test creates agents; a 500 would have blocked it | Yes: a grounding defect on the flight's path is fixed first |
| Delete approval gained a stale check (DD6 said none) | It fails closed; an operator edit to a routine the agent wants deleted should be seen | Yes, as a default for approvals of destructive changes |
| `ProposalOp` takes its routine id from the mutator | An applied delete's row could not point at a deleted routine (the FK) | Yes, the mutator is the id authority |
| Duplicate pending create refused with a 422 | DD6 deduped only updates and deletes | No, it is specific |
| Refusals do not count toward the 5-writes-a-turn budget | DD8 was ambiguous; the step limit bounds retries | No |
| Routines scenarios in `evals/routines/`, not `evals/scenarios/` | `compare` fingerprints the whole scenarios tree, so new files there break a cross-set comparison | Yes: a new scenario set gets its own tree |
| Legs 4 and 5 run in parallel | 2 h of evals; disjoint files | Yes, when files are disjoint and no budget is read from the overlap |
| Batch B review started before leg 4's last eval run finished | Leg 4's source was done; the run only produced data | Yes, review source when it is final, and read the data at landing |
| The "Show older" follow-up was accepted without a re-review | Small, test-pinned and falsified, after a confirmed review (same call as Batch A's switch fix) | Yes (second use) |
| The debrief reused the flight's gate instead of a fresh full run | No source or test changed since the gate (operator decision) | Yes, see Recommendation 1 |

## Key Learnings

- **Composition order belongs inside the transaction, and in the spec.**
  The caps, the stale check and the proposal row are race-free only because
  the repository mutators run precheck, caps, write and proposal in one
  transaction, in a fixed order. The design review had to make that
  explicit; writing it into the flight design saved a rework.
- **Snapshot taint on the message, never read live flags.** Binding a
  routine run's sources onto its user message at save time made the taint
  scan pure and repeatable. It also means an operator clearing the flag
  later does not rewrite history the model already saw.
- **A list cached per session needs a call-time check.** Turning Routines
  off must take effect even in an open chat whose tool list is cached. The
  Batch A review caught `list_my_routines` missing the check.
- **A live local model can prove a tool's seeded description works.**
  `gpt-oss:20b` called `schedule_routine` on the first try, and even fixed
  its own invalid schedule within the turn after a clear refusal. That
  sentence-level refusal design paid off.
- **The `gpt-oss` planted page is obeyed in 17 of 20 runs.** The routine is
  created, flagged, and every one was caught. The defence here is the flag
  and approval, not the model's judgement.

## Methodology Observations

Plugin version: mission-control 1.2.3 for every entry.

1. **`/mission-control:flight-debrief`, Phase 2 (Developer interview) and
   Phase 3 (Test Metrics): the full-suite run duplicates the flight's own
   final gate.**
   - **What the skill did:** told the Developer to run the full test suite
     once, unconditionally.
   - **What was expected:** this flight's quiet-host gate (unit plus the
     `--parallel 3` browser suite) had already run on `ee4e8c5b`. The only
     later commit (`6dac4478`) touched artifacts, CLAUDE.md, the behavior
     run log and the `run-tests.sh` budget table, with no source or test.
     The fresh run could only re-measure the same code, adding at most one
     variance sample.
   - **What it cost:** about 45 minutes of host time (7 min unit plus about
     30 min browser) and a blocked host. The operator stopped it partway
     ("is it really worth running the full test suite every flight?"). The
     unit half (6m39s) had already run and matched the gate exactly.
   - **The rule the operator adopted:** the debrief reuses the flight's last
     full gate when `git diff <gate commit>..HEAD` touches no source, test
     or test-runner code, and records the gate's commit. Otherwise it runs
     fresh. A fresh run is warranted when:
     - post-gate changes landed (HAT fixes, review fixes);
     - the gate ran on a loaded host;
     - `main` moved and the branch was rebased.
   - **Recurrence:** the Flight 1 debrief ran the full suite the same way
     right after its own gate.
2. **`/mission-control:behavior-test`, Execution Modes: live mode was
   available though the crew file says it needs an experimental flag.**
   - **What happened:** `SendMessage` was available as a deferred tool
     (loaded through ToolSearch), so the run used live mode.
   - **What the docs say:** the skill and the project crew file say
     `SendMessage` is present only with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
   - **What it cost:** nothing, and live mode worked well. But both agents
     appended "I can't resume from a handback, send the next step by
     SendMessage" to every report. That noise came from the crew prompt's
     "you are resumed by SendMessage" rule meeting a harness where each
     reply is a hand-back.
   - **What would help:** the skill's mode check should test whether the
     tool can be loaded, not whether the flag is set.
3. **`/mission-control:agentic-workflow`, Phase 2d fix loop: the "Fix
   Review Issues" prompt does not say how to falsify a new test in a shared
   tree.**
   - **What happened:** a fix Developer removed its fix, ran the tests, then
     restored both whole files from backup copies.
   - **The risk:** a whole-file restore in a shared working tree can
     overwrite a concurrent edit. Here none was lost.
   - **What would help:** the crew prompt should require falsifying by
     edit, which the FD added by hand for the next fix pass.
4. **`/mission-control:agentic-workflow`, Phase 1 / 2: planned and flown
   with no planning conversation.** The operator asked for "plan and
   implement". Every open decision was made by the FD and marked *(J)*.
   - **What it cost:** nothing during the flight. But the debrief Architect
     lists 16 *(J)* calls for the closing HAT to confirm, and that load
     lands on one human session.
   - **What would help:** the skill could suggest grouping *(J)* calls by
     how reversible they are, so the HAT spends time only on the costly
     ones.
5. **Harness, not methodology (recorded for the sweep's context).**
   - **Repeated notifications:** a background fix agent whose own unit run
     was still going sent about 15 identical "waiting on its own background
     work" notifications. Each one cost an FD turn.
   - **A blocked step:** `gh pr ready` was refused by the auto-mode
     classifier, though the agentic-workflow PR lifecycle calls for it. The
     operator's "merge" instruction then covered it.

## Recommendations

1. **Reuse the flight's last full gate in the debrief** when no source,
   test or test-runner file changed since it (Methodology Observation 1).
   Brief the debrief Developer with the gate's commit and numbers, and run
   fresh only when that diff is non-empty or the gate was on a loaded host.
   This is a project-side change to how the FD briefs the debrief, and
   upstream feedback on the skill.
2. **Confirm the *(J)* calls at the Flight 3 HAT**, starting with the
   costly ones:
   - DD7's `peer:{name}` flag on every connector-chat write (consider an
     allowlisted-peer exemption);
   - approval defaulting to on;
   - the DD8 cap values;
   - the h3/h4 heading asymmetry between the two Self-configuration items.

   The full list of 16, with a recommendation each, is in this flight's
   Architect review, summarized in the Action Items.
3. **Give `routing` and `agents` headroom before Mission 34.** Both sit at
   90%+ of budget for the third flight running. Split or re-budget each from
   a quiet `--parallel 3`.
4. **Split `agent-editor-controller.js` before the next agent-editor
   feature.** It is at 781 of the 800-line limit.
5. **Add "falsify by edit, never by whole-file restore" to the crew file's
   Fix Review Issues prompt** (Methodology Observation 3).

## Action Items

- [ ] Flight 3 HAT: walk the *(J)* calls. The Architect's list is:
  - DD1: tools seeded at 853 tokens;
  - DD2: tool names and target shapes;
  - DD5: labels and approval on by default;
  - DD6: refusals not recorded, the delete stale check, the pending cap and
    dedup;
  - DD7: the trusted set, the `peer:` flag, whole-routine flagging, and
    clearing the flag by saving with the prompt;
  - DD8: the caps;
  - DD10: proposals never purged;
  - DD13: `gpt-oss:20b`;
  - the leg 3 and leg 4 deviations.
- [ ] Squawk candidates offered at the debrief. The operator logged only
      the falsify-by-edit rule, as **squawk 0284** (Recommendation 5). The
      other three stay as recommendations:
  - the `routing` lane at 91% of budget;
  - the `agents` lane at 90%;
  - `agent-editor-controller.js` near the line limit.
- [ ] The debrief gate-reuse rule (Recommendation 1): apply from the next
      debrief.

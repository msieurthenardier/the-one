# Flight Debrief: HAT and Alignment

**Date**: 2026-10-30
**Flight**: [HAT and Alignment](flight.md)
**Status**: completed
**Duration**: 2026-10-29 (planning) to 2026-10-30 (landing), across two
sessions (one ended by an accidental session kill mid-leg 07).
**Legs Completed**: 7 of 7. One was planned (the walk); six were added at
the HAT through the fix-vs-feature gate, plus fix passes 1-3 and the F-H1-1
fix.
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved

The mission-closing walk ran end to end with the operator, Parts A, B, C, E,
F, G, H and J. Part D, a real Discord DM, was dropped by the operator when
routine connector delivery was removed. Every judgement call carried from
Flights 1-3 was confirmed, reversed or made moot:
- **Confirmed:** C1-C5, C7, C9, C10, C12, C13; L1-L5, L7-L9, L11, L12.
- **Reversed:** C6 (legacy shapes removed), C8 (approval off by default),
  L6 (MCP servers first), L10 (danger-zone layout).
- **Moot:** C11; C14's gone-chat half.

What the walk changed, each through a design review, a code review and an
accessibility review:
- **Every routine run starts a new chat (legs 02/03).** Routine targets and
  routine connector delivery are removed (schema v49, guarded `DROP
  COLUMN`s, a frozen proposal rewrite). The agent tools lose `target`. The
  Routines tab was rebuilt on mockup A, then moved onto Tools-style
  `App.ui.groupTile` cards:
  - Details with a styled prompt and one-line recent runs linking to their
    chats;
  - a "⋯" menu;
  - edit in place;
  - Save disabled until changed;
  - stored reasons shown.
- **Start immediately (leg 04).** A Starts radio group, On / In /
  Immediately (mockup S1), with an operator-only now-start. Done routines
  show a disabled switch.
- **Approval off by default for new agents; the drawer refreshes on a
  routine tool write (leg 05).**
- **Self-configuration as two cards (leg 06, mockup SC2).** Each card has an
  inline approval switch and Waiting/History expanders, with External access
  at the bottom.
- **Canonical schedule input only (leg 07).**
- **Fix passes:**
  - the Tools tab order;
  - the "ends after" default of 7;
  - history rows;
  - the danger zone: Purge chats and history, then Permanently delete agent;
  - the stale waiting list after Chats (F-E3-1);
  - the Purge re-arm bug;
  - accessibility.
- **F-H1-1.** A general session-restore race emptied a startup catch-up
  run's chat. It is fixed by a re-check under `_sessions_lock`, and routine
  runs now fail closed: no turn, or no saved message, means `failed`.

### Mission Criteria Advanced

All ten mission criteria are ticked from the operator's verdicts (flight log,
"Mission Criteria Verdicts"):
- **Amended criterion:** "The reply lands in the target" is met as amended:
  every run starts a new chat.
- **Criteria resting on tests rather than the walk:**
  - daylight saving rests on the frozen-clock unit tests;
  - the upgrade clauses rest on the v45-v49 migration tests.
- **Criterion ticked after the walk:** "An agent schedules its own routines"
  was ticked after the re-authored behavior test passed, 7/7.

## What Went Well

- **Costly calls first (DD1).** Part B settled C1-C5 through the form's
  preview line with no waiting. The B3 step surfaced the target-model problem
  early in the walk.
- **The contract list (DD5) made the pivot tractable.** The behavior specs,
  evals, taint contract, fields, testids and docs were already enumerated, so
  legs 02 and 07 started from an impact list, not a hunt.
- **Mockups at the HAT were fast and decisive.** Eight artboards on one
  canvas settled three surfaces in minutes each:
  - the Routines list: A, B or C;
  - the start options: S1, S2 or S3;
  - Self-configuration: SC1 or SC2.

  The operator: "really well done on the mock ups".
- **The fix-vs-feature gate held under pressure.** Every behavioural change
  had a Developer design review before code, and each review found real
  defects:
  - leg 02's rebuild-vs-DROP-COLUMN choice and the eval sequence;
  - leg 04's `normalize`-level now-start, which could not work;
  - leg 05's default, which needed the INSERT to write it;
  - leg 06's `groupTile` limits.
- **Part H earned its place.** Restarting with a due routine found F-H1-1,
  a race that would otherwise have shipped. It applies to every chat, not
  only routines.
- **Environment hygiene.**
  - Scratch instances ran on 8490 with PIDs recorded.
  - Each instance's `/proc/<pid>/environ` was read.
  - The HAT secrets directory was deleted at the end.
  - Nothing touched 8484 or the default data dir.
  - The 8484 instance was confirmed quit by a refused probe.
- **Crash recovery.** After the session died mid-leg 07, the HAT instance
  survived. The orphaned unit run was stopped by its verified PID, and the
  Developer was resumed from its transcript with no work lost.

## What Could Be Improved

### Process

- **Flights 1-3 built a model the operator removed at the mission close.**
  The three run-in targets, the chat chooser, gone-chat semantics and
  connector delivery all came from the data model outward. The operator first
  saw them at this HAT, three flights later. The root causes:
  - **No mockups were made of the surfaces.** The operator: "Had we done some
    mock ups prior to the work, we may have avoided some of this rework."
  - **There was no early operator look.** By operator decision there were
    no per-flight HATs.
  - **A criterion assumed the design.** One mission criterion was phrased in
    implementation terms ("the reply lands in the target"), so it presupposed
    the design.
  - **Open calls piled up without being resolved.** 26 judgement calls
    accumulated without any forcing function.
- **The Developers broke squawk 0286's rule three times.** Three of seven
  wrote into source or tests through the shell (`sed -i`, heredoc appends),
  each self-reported and each verified by a reviewer. A written rule in
  every prompt did not hold.
- **Process gaps the FD caught mid-run:**
  - **An over-cautious precondition.** The FD added one the spec did not
    have: an idle wait before the behavior test's step 6.
  - **Two malformed shell commands.** One `cat >>` read from stdin and
    created an empty stray file, which was removed. One restart command
    left a Python REPL running, which was killed by its verified PID.
  - **A Part F error.** The FD misread Part F as done when no rename had
    happened. It was corrected from the server log.

### Technical

- **F-H1-1 was a general hazard.** Any check-then-await-then-mutate on a
  `Session` has the same shape as the bug. Only Part H's restart exposed it.
- **Accepted debt (operator):** a follow-up an agent schedules from a
  platform DM reaches the asker only if its prompt makes the agent post with
  `send_to_platform_channel`. In the behavior test's step 4 on
  `gpt-oss:20b`:
  - the model-written prompt did not stand alone;
  - nothing reached alice.
- **A new chat per run means volume.** A frequent routine fills the Chats
  list (every 10 minutes is 144 chats a day). Retention is the only bound.
- **Single-consumer library options:** `groupTile` `expand:false`,
  `menu.setItemDisabled`, `confirmDialog` `danger` and `dangerZone`
  `heading`/`description`. Each is catalogued and contract-tested. Whether
  `expand:false` should be its own component is worth a look.
- **`gpt-oss:20b` failed one shape repeatedly.** Twice it emitted the same
  malformed tool-call JSON for an absolute-date one-off (an extra `}`, so
  Ollama returned 500). The relative-start eval cell passed 20/20. The
  behavior test switched to `qwen3:30b`, which completed but was slow (turns
  of 7-10 minutes, partly CPU-offloaded).
- **The eval re-baseline cost a lot for a confounded result.** The
  same-prompt re-baseline cost about 3 hours on gpt-oss. On Haiku it was
  confounded (the old code's `this_chat` default, 11/20). The committed
  `m33-routines` baseline was rebuilt from the new-prompt runs.

### Documentation

- CLAUDE.md's Routines and Self-configuration paragraphs grew again and read
  as change logs. Detail belongs in `the_one/agents.md`.
- Four patterns emerged that are not yet named in `agents.md` Project
  Conventions:
  - the operator-only now-start;
  - fail-closed run classification;
  - a re-check under the lock after an await;
  - `App.ui.confirm` success paths calling `revertFn()`.

## Test Metrics

**Source:** the flight's closing gate, reused per the crew file's rule.
- **What the gate ran on:** HEAD `4032b5cd` plus the flight's changes, then
  uncommitted. In code it is identical to `3a439689` except the lane-budget
  table.
- **Load:** start load 1.33, from the preceding unit run on the same host,
  with no other test process. This is the FD's call to reuse rather than
  re-run; it is recorded in the log.

**Unit:** 8383 passed, 15 skipped, 398.89 s.
- **Against Flight 3:** 8371 passed, 392 s. That is +12 tests and +6.9 s
  (+1.8%).
- **Churn behind the small net:** test files changed by +4247/-3087 lines.
  Deleted target, delivery and alias tests offset the new ones.
- **Long-term drift:** the drift since Mission 31 (281 to 399 s) is still
  squawk 0222's subject.

**Browser:** `PARALLEL_RESULT rc=0 total=1955s lanes=17 failed=-`.
- **Against Flight 3:** 1885 s at start load 1.11, so +70 s (+3.7%). Part of
  that is load.
- **Per-lane wall time** (s):

  | lane | time |
  |---|---|
  | routing | 562 |
  | agents | 506 |
  | contracts-controls | 503 |
  | chats | 355 |
  | providers | 350 |
  | shared | 349 |
  | library | 346 |
  | agent-tabs | 308 |
  | knowledge | 306 |
  | mcp-connection | 284 |
  | settings | 281 |
  | chats-transcript | 268 |
  | mcp | 266 |
  | settings-tools | 256 |
  | agent-routines | 236 |
  | contracts-overlay | 236 |
  | contracts-chat | 54 |

- **Lanes that moved:**
  - Only `agent-routines` moved more than 15%: from 171 s (M33 F2) and
    191 s (the F3 reading) to 236 s, because its tab, form and
    Self-configuration test files were rewritten. It was re-budgeted from
    240 to 300 s.
  - `chats` rose 8% with the drawer tests, and `agent-tabs` 5%.
  - `routing` and `agents` sit at 78% and 80% of their budgets.

**Flakes:** `test_purge_loop_catch_up_sweeps_due_db` failed once more in a
full unit run on a loaded host (the HAT instance was running) and passed
alone. The closing gate was clean, so it stays a watch item.

**Weak tests:** many new tests were falsified, but these were not:
- leg 04's radio-group, immediate-run and edit-flip-back browser tests, and
  its preview API test;
- leg 06's count/keyboard test and its disable-drops-the-count test;
- several fix-pass layout tests;
- the `groupTile` exposure contract test.

They are acceptable but weak regression nets.

## Deviations and Lessons Learned

| Deviation | Why | Disposition |
|---|---|---|
| One planned leg became 7 legs plus 3 fix passes plus F-H1-1 | The walk surfaced redesigns; the operator chose to fix them in the HAT | The operator confirmed "Inside the HAT was right" |
| Part D (real Discord DM) dropped | Routine connector delivery removed | Planning effort on DD3/pairing went unused |
| Mission criterion amended | Targets removed | The original text was kept with an amendment note |
| No second design-review cycle on legs 02-07 | Every change applied the reviewer's own recommendation | FD call, recorded per leg |
| Debrief metrics reused the gate at start load 1.33 | The load came from the preceding unit run, not another process | FD call, recorded |
| `m33-routines` rebuilt from new-prompt runs | The old-prompt baseline was confounded | Recorded; the old file was kept in the scratchpad |
| Behavior test switched to `qwen3:30b` at step 5 | Two identical Ollama 500s on `gpt-oss:20b` | Allowed by the spec's model rule; recorded |

## Key Learnings

- **Show the operator a user-facing surface before it is built.** A mockup
  costs minutes. The rework it would have prevented cost most of this flight.
- **Unattended work should prove its effect before reporting success.**
  F-H1-1's "ok" run had saved nothing.
- **Deleting an unshipped feature outright is cleaner than keeping
  aliases.** Leg 07 and the `DeliveryResult` removal show this.
- **A HAT that restarts the system finds lifecycle races.** Unit tests that
  never interleave a join with a turn cannot.

## Methodology Observations

1. **flight (planning) and mission (planning): no surface review before legs
   lock.**
   - **What happened:** user-facing surfaces were designed from the data
     model in Flights 1-3. The operator saw them first at the
     mission-closing HAT and removed the target model, reshaped the Routines
     list twice and rebuilt Self-configuration.
   - **What was expected:** the flight skill prompts for a mockup, or two
     layout options, of every new or reshaped user-facing surface, approved
     by the operator before leg design.
   - **What it cost:** six added legs, three fix passes, a schema migration
     undoing columns added two flights earlier, and an eval re-baseline.
   - **Recorded:** for the upstream sweep. The operator chose a project rule
     too (squawk 0293).
2. **agentic-workflow (crew prompts): a written rule did not stop shell
   writes.**
   - **What happened:** squawk 0286's "edit only through the edit tool"
     rule, added to both Developer prompts the day before, was broken by
     three of seven Developers (`sed -i`, heredoc appends).
   - **What was expected:** the methodology recommends, or ships, a
     mechanical guard (a `PreToolUse` hook) for rules the project marks as
     hard.
   - **What it cost:** three extra full-diff reads by reviewers.
   - **Recorded:** squawk 0292 (a project hook).
3. **mission and flight: judgement calls carried without a forcing
   function.**
   - **What happened:** 26 *(ajc)/(J)/(FD)* calls carried to the mission
     close. The costliest design choice, the target model, was never tagged
     as a call, because it was written into a criterion.
   - **What was expected:** costly calls (data shape, behaviour) shown to
     the operator at the end of the flight that makes them, or a cap that
     triggers a checkpoint.
   - **What it cost:** reversals at the end rather than the start.
4. **behavior-test (Orchestrator): a precondition the spec did not have.**
   - **What happened:** the FD told the Executor to wait for the chat to go
     idle before step 6's approve. The Executor waited 180 s, then reported
     an exception.
   - **What was expected:** the Orchestrator passes the spec's actions
     verbatim and records any added wait as an Orchestrator decision first.
   - **What it cost:** one extra round trip (about 4 minutes).
5. **The crew file's eval convention: a needless re-baseline.**
   - **What happened:** "a changed scenario set needs a same-prompt
     re-baseline" forced an old-prompt run for a change that only removed a
     check. It cost about 3 hours and was confounded.
   - **What was expected:** the convention exempts a check-only removal, or
     asks for the new-prompt runs as the baseline when the old code cannot
     run the new scenarios.
   - **What it cost:** about 3 hours of host time and plan quota.
   - **Recorded:** for the project's CLAUDE.md "Prompt evals" wording.

## Recommendations

1. **Mockups before feature legs.** Add a rule to this project's
   flight-design Architect prompt: any new or reshaped user-facing surface
   needs an operator-approved mockup before legs are locked. The operator
   chose this: squawk 0293. *(Critical.)*
2. **A mechanical guard for shell writes into source (squawk 0292).** Add a
   project `.claude/settings.json` `PreToolUse` hook on `Bash` that refuses
   these forms aimed at `the_one/`, `tests/`, `docs/`, `scripts/`,
   `missions/` or `evals/`:
   - `sed -i`, `perl -i`, `tee`;
   - output redirects;
   - heredoc writes;
   - Python `open(..., 'w')`;
   - `cp`, `mv` or `install`.

   Redirects to `/dev/null`, the scratchpad, `git`, `make`, `pytest` and
   `ruff` stay allowed. *(Important.)*
3. **Design the follow-up delivery properly, as a mission follow-up.** A
   follow-up an agent schedules from a platform conversation should reach
   the asker. The options:
   - stronger `schedule_routine` text;
   - carrying the asking conversation as run context.

   This goes with the other open follow-up: external clients managing
   routines, option (b). *(Important; mission debrief.)*
4. **Name the four new patterns in `agents.md` Project Conventions:**
   - the operator-only now-start;
   - fail-closed unattended outcomes;
   - a re-check under the lock after an await;
   - `confirm` success paths calling `revertFn()`.

   Also move the CLAUDE.md Routines and Self-configuration change-log detail
   into `agents.md` (squawk 0294). *(Minor.)*
5. **Eval convention.** Let a check-only scenario change skip the
   old-prompt re-baseline, and record that the baseline may be rebuilt from
   the new-prompt runs when the old code cannot run the new scenarios.
   *(Minor; mission debrief.)*

## Action Items

- [ ] Squawk 0292: a `PreToolUse` hook against shell writes into source
      (Recommendation 2).
- [ ] Squawk 0293: a mockup rule in the flight-design crew prompt
      (Recommendation 1).
- [ ] Squawk 0294: the four patterns in `agents.md`, and trimming CLAUDE.md
      (Recommendation 4).
- [ ] Mission debrief:
  - the follow-up delivery design and external-client routines
    (Recommendation 3);
  - the eval convention (Recommendation 5);
  - chat volume from frequent routines;
  - squawks 0288-0291.
- [ ] Watch `test_purge_loop_catch_up_sweeps_due_db` on a quiet host.

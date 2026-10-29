# Flight Debrief: Schedules and Limits

**Date**: 2026-10-29
**Flight**: [Schedules and Limits](flight.md)
**Status**: completed
**Duration**: 2026-10-29, in one day.
- **Planning:** from `main` at `ebb83d8c`, with two Opus Architect cycles,
  committed as `49a5051a`.
- **Batch A** (legs 1, 2, 3 and 6): `54d87b8a`.
- **Batch B** (legs 4, 5 and 7): `f24ae1f1`.
- **Leg 8:** behavior re-runs at `508edca3`, the gate on `508edca3`, the
  landing at `cc1d5875`.
- **PR:** #338.

**Legs Completed**: 8 of 8. Five were planned; the reviews split them into
eight:
- Architect cycle 2 split the backend into core and switch, and separated
  the caps work;
- the leg 4 design review split leg 4 into two passes, 4a and 4b.

**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved

- **One calendar recurrence replaces the five fixed schedule kinds.**
  - The stored shape is `{start, repeat, ends}`, with every N minutes,
    hours, days, weeks (chosen days), months (a day, or an nth or last
    weekday) or years.
  - A routine ends never, on a date, or after N occurrences counted from the
    start.
  - There are two kinds of start:
    - instant-anchored: one-offs and minute/hour units, which use
      `anchor_at`;
    - wall-clock: day and longer, where `start` is authoritative.
  - The two kinds keep daylight-saving and time-zone behaviour exact.
- **No routine was lost or moved in the upgrade.** v48 rewrote every
  routine and proposal with a frozen converter, and each next run is
  unchanged. That includes a 02:30 daily on a spring-forward day and
  interval anchors with microseconds. An unreadable schedule turns its
  routine off with a guarded run row; it never fails startup.
- **One calculator, on the server.**
  - `recurrence.py` and `recurrence_text.py` hold every calculation and
    sentence.
  - The browser asks the new preview route, so no calculator is duplicated
    in JavaScript.
  - The old request shapes stay accepted and are stored in the new form.
    Both behavior specs proved this live.
- **The form follows the Google Calendar pattern** the operator asked for:
  - start date and time;
  - Repeat presets computed from the start date;
  - a "Custom recurrence" dialog;
  - a debounced preview with warnings.

  It is built on three new library controls: `datePicker`, `timeField` and
  the days variant of `checkboxGroup`.
- **The agent's tools** document only the new shape. `gpt-oss:20b` used it
  correctly on the first try in the live run.
- **Limits, per the operator's decisions:**
  - 50 active routines and 200 not-done routines for every write;
  - a 1-minute floor and no runs-a-day cap;
  - Done routines and resolved proposals age out with retention;
  - repeated "still running" skips collapse into one row.
- **Maintenance:**
  - the routine routes moved to `routines_api.py`;
  - the agent editor controller was split (781 to 684 lines);
  - squawks 0232, 0273 and 0284 are completed;
  - `routing` and `agents` were re-budgeted for headroom.

### Mission Criteria Advanced

| Mission criterion | How |
|---|---|
| The operator manages an agent's routines | Advanced: the calendar recurrence and the new form, with a server preview. |
| Routines run on time, unattended | Advanced: the new calculator with daylight-saving and zone rules, ends, and Done as a function of the recurrence. Proven live in `routine-connector-delivery` step 6. |
| Unattended runs are honest | Advanced: skip reason codes and the "still running" collapse. |
| An agent schedules its own routines when allowed | Advanced: tools on the canonical shape. `agent-schedules-follow-up` passed 7/7 live. |
| Injected content cannot plant a routine unnoticed, and routines are bounded | Advanced: one active cap and one backstop. The no-runs-a-day trade-off is recorded in `SECURITY-MODEL.md`, and the taint and approval path was re-proven live. |
| Routines follow their agent | Advanced: v48 lost no data; Done routines and resolved proposals now follow the agent's retention. |

## What Went Well

- **The planning reviews found real defects before any code.**
  - **Architect cycle 1:**
    - the route move was not "pure", because test apps are built from
      `api.router`;
    - the "after N" counter disagreed with the form's last date;
    - the spec never said whether the start is an occurrence;
    - lanes would go red between legs.
  - **Architect cycle 2:**
    - the v48 conversion would have moved a 02:30 daily to 03:00 for good;
    - the "core" leg collided with live callers.
  - Each finding changed the plan. Two of them (the spring-forward drift
    and the counter) would have shipped as silent data defects.
- **Leg design reviews kept paying off.**
  - The leg 2 review fixed the approval error status, the runner's reason
    codes and a sweep `running` guard.
  - The leg 4 review found that approval re-normalized stored schedules,
    which would have shifted grids and lost the fall-back fold. That led to
    verbatim schedule pairs with `rezone` at approval. It also set the 422
    vs 409 precedence and split the leg.
- **"New code beside the old, then a switch leg."** Leg 3 built the
  calculator with no callers while legs 1-2 changed the same area; leg 4
  switched over and deleted the legacy code. The unit tier stayed green at
  every landing.
- **Server-side sentences and previews** removed a whole class of
  Python/JS drift. The leg 4b adapter was thin.
- **Parallel legs on disjoint files** saved hours:
  - leg 3 beside leg 1;
  - leg 6 beside leg 2;
  - leg 5's evals beside legs 4b and 7.

  The cost was known: lane timings in those legs were not budget readings.
- **Review discipline.**
  - Every batch had a Sonnet code Reviewer, at the security-sensitive tier
    for the caps and retention on agent-written routines.
  - The UI batches also had an Accessibility Reviewer.
  - The Batch B Reviewer diffed the rebuilt `scheduler.py` line by line
    after the 4a incident.
- **The behavior runs in live mode were clean.** Both specs ran with one
  Executor and one Validator each, resumed by `SendMessage`:
  - `routine-connector-delivery`: 8/8;
  - `agent-schedules-follow-up`: 7/7.

  Running steps 5 and 6 in strict order kept the Validator from seeing
  state that the approval was about to change.
- **The gate-reuse rule (squawk 0285)** worked as designed. This debrief
  used the leg 8 gate, because nothing but the budget table and docs
  changed after it.

## What Could Be Improved

### Process

- **A helper script truncated `scheduler.py` (leg 4a).**
  - The Developer wrote a falsification helper that rewrote the whole file
    and truncated it, then rebuilt it from `git show HEAD:` plus its edits.
  - Squawk 0284's falsify-by-edit rule was already in the fix prompt. The
    Implement prompt does not carry it, and a helper script is a new way
    around it.
  - It was caught only because the Developer reported it. The Reviewer's
    line diff, not the tests, proved the rebuild lossless.
  - **The operator chose a hard rule:** no scripted rewrites of source
    files, and source edits only through the edit tool. Logged as squawk
    0286.
- **Uneven falsification in fix passes.** Several fix-pass Developers
  reported they had not falsified their new tests: the aria-live
  assertions, the checked-and-disabled day style, the Batch B form
  assertions. Each test is small, but the record is uneven.
- **The leg 6 spec told a library control to read `App.time`.** The
  library guard (`tests/test_ui_library_source.py::test_file_touches_no_app_globals`)
  forbids that. Leg 2's unit run caught it and a fix pass moved "today" to
  a caller-supplied option. Specs for library controls should be checked
  against the guards at design time.
- **Legs did not declare shared files, which forced unplanned batch
  changes.**
  - `index.html` had edits from both leg 1 and leg 6, so Batch A became
    legs 1, 2, 3 and 6.
  - `tools.py` had edits from both legs 4a and 5, so Batches B and C merged.
  - A per-leg "shared files" line would let batches be planned by file.
- **The flight grew from "the closing HAT" to eight legs.** The operator
  confirmed that was right: big design changes surfaced in review become
  their own flight before the walk.

### Technical

- **Legacy input aliases with no sunset (DD5).**
  - Requests in the old shapes are accepted on REST, the preview route and
    the tools. The tool text no longer documents them, so they cost code and
    tests, not tokens.
  - The frozen v48 converter is a deliberate second copy of the legacy
    parsing.
  - The eval and behavior corpora now use the canonical shape, apart from
    `routine-connector-delivery`, which deliberately keeps the legacy
    shapes. The aliases can be retired on a plan.
- **Instant-anchored vs wall-clock is inferred from the unit** (`anchor_at`
  null or not). It works, but every consumer must know it. Consider one
  accessor or an explicit field the next time this area changes.
- **Large modules:**
  - `recurrence.py` is 674 lines and now also holds the legacy-shape
    parsing; that could become `recurrence_legacy.py` and be deleted with
    the aliases;
  - `date-time.js` is 582 lines and holds two controls;
  - `routines-form.js` is 488 lines and `routines-form-model.js` 359 lines.
- **Done is derived:** "no next occurrence within the bounded search"
  marks a routine Done. A pathological rule past the bound becomes Done
  silently. It is tested, but it is a silent path.
- **A series' last occurrence gets the one-off's 24 h grace.** That was an
  intended call, but a long window for a late final run after downtime.
- **The routine tools now cost 945 tokens** when enabled, up from 853,
  because of the richer shape description.
- **Lane timing under parallel evals.** Leg 4b's lanes ran at load 6-12, so
  only the leg 8 gate counts as a budget reading. This repeats Flight 2's
  pattern.

### Documentation

- **In-flight updates:** CLAUDE.md (Routines paragraph, lane table),
  `the_one/agents.md` ("Routines (M33)": calendar recurrence, preview
  route, v48, zone changes, the form), `SECURITY-MODEL.md` (caps, retention,
  the no-runs-a-day trade-off), `docs/ui-control-inventory.md` (the two new
  controls and the days variant), `docs/ui-testid-registry.md` (new and
  retired testids).
- **Worth adding** to `the_one/agents.md` Project Conventions:
  - the "verbatim stored pair plus re-render at apply" pattern for
    approvals;
  - the "frozen migration converter with a guarded failure row" pattern.

## Test Metrics

**Source: the flight's quiet-host gate on `508edca3`.** It is reused under
the project's gate-reuse rule; `508edca3..HEAD` changes only the
lane-budget table and docs.

**Unit** (`THE_ONE_TEST_NETNS=1 make test-unit`, start load 0.53):
- 8371 passed, 0 failed, 15 skipped (the expected netns count), 392 s.
- Against prior debriefs:
  - Flight 2: 8237 passed, 383.5 s, so +134 tests for +8.5 s (+2.2%). The
    new tests are mostly pure recurrence tables and cheap;
  - Flight 1: 8092 passed, 381 s.
- The slow unit-tier drift since Mission 31 (281 to 392 s) remains squawk
  0222's subject.

**Browser** (`--parallel 3`, `THE_ONE_REQUIRE_WEBKIT=1`, start load 1.11,
run straight after the unit tier, no other test process):
- `PARALLEL_RESULT rc=0 total=1885s lanes=17 failed=-`.
- Against Flight 2's gate (1774 s, start load 0.73): +111 s (+6.3%).
  - Part of that is load: 1.11 is slightly above the quiet-host guide of
    about 1.0.
  - Part is new tests:
    - `contracts-controls` 463 to 486 s, from the date picker, time field
      and day-toggle contract files, run in both engines;
    - `agent-routines` 171 to 191 s, from the rewritten 31-test form file.
- Every other lane is within about 6% of its table reading. `contracts-chat`
  fell from 71 to 53 s and keeps its 90 s budget.
- `routing` (555 s) and `agents` (499 s) were at 92% of budget for the
  fourth flight running.
  - They were re-budgeted to 720 s and 630 s from this run.
  - A split would not shorten the gate: the total is bound by the lane sum
    over three workers, not by the `routing` critical path.

**Flakes:**
- `tests/test_chat_history_purge.py::test_purge_loop_catch_up_sweeps_due_db`
  failed once under load (leg 4b, load 6-12) and passed alone. The gate
  was clean. Watch it; it becomes a squawk if it fails on a quiet host.
- No other flakes in any gate run.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Five planned legs became eight (core and switch split, caps separated, leg 4 in two passes) | Architect cycle 2 and the leg 4 review found legs colliding with live callers or too big for one pass | Yes: an irreversible data rewrite plus caller rewrites is at least two legs |
| Approval with no runs left is a 422, not the DD1 409 | The approve route and the queue read 409 as stale or gone | Yes: check every client's reading of a status before choosing it |
| Verbatim schedule pairs with `rezone` at approval | Re-normalizing at approval would shift grids and lose the fall-back fold | Yes, for any approval of a stored computed value |
| `_RoutineTurnHost` stayed in `app.py` | Moving it creates an import cycle for about 30 lines | No, it is specific |
| The `m30-platform` eval run was skipped when the routines-off prompt was byte-identical | No measured text changed | Yes: a fingerprint-identical prompt needs no re-run |
| The evals harness mapping moved from leg 5 to leg 4 | Otherwise the offline eval tests would go red at the switch | Yes: move the consumers with the shape change |
| Batches A, B and C regrouped by shared files | `index.html` and `tools.py` each carried two legs' edits | Yes: plan batches by file |
| Routing and agents re-budgeted, not split | The suite total is sum-bound | Yes, for headroom-only problems |
| The leg 6 spec was corrected after the library guard failed | The spec contradicted a project guard | No; check guards at design time instead |

## Key Learnings

- **Make every consumer of a derived state explicit in the flight spec.**
  "Done" moved from a stored one-off flag to "the recurrence has no next
  occurrence". Each consumer then needed its own rule: approval, re-enable,
  preview, zone follow and the scheduler. The flight spec named none of
  them, so the "no runs left" rule and its 422/409 precedence only settled
  at the leg 4 review.
- **Carry exact instants, and render the clock time.** Storing the instant
  (`anchor_at`) and only rendering `start` closed three bugs at once:
  sub-minute anchors, the fall-back fold, and one-offs across zone changes.
- **A frozen migration converter** keeps a data migration a historical
  fact, never a function of today's normalizer.
- **The falsify rule needs a mechanical edge.** The prompt already said "by
  edit", and a helper script still found a way around it.
- **A live local model learned the new shape from the description alone.**
  `gpt-oss:20b` produced the relative and absolute starts correctly on the
  first try, and the eval cells held.

## Methodology Observations

Plugin version: mission-control 1.2.3 for every entry.

1. **`/mission-control:flight`, Phase 4/5: the flight spec did not
   enumerate the consumers of a derived state that changed meaning.**
   - **What happened:** DD1/DD2 made Done a function of the recurrence. The
     spec did not list every path that reads "has a future run" (create,
     schedule edit, re-enable, approval, preview, zone follow, scheduler).
   - **What it cost:** the "no runs left" refusal, its on/off scope and its
     422/409 precedence surfaced only in Architect cycle 2 and the leg 4
     review. That meant a DD1 amendment mid-flight and extra review text.
   - **What would help:** when a DD changes how a state is derived, the
     flight skill could prompt for the list of that state's readers.
2. **`/mission-control:agentic-workflow`, Phase 2b/2d: legs do not declare
   shared files, so batches split by leg collide on files.**
   - **What happened:** `index.html` (legs 1 and 6) and `tools.py` (legs 4a
     and 5) forced two unplanned batch regroupings. Partial staging
     (`git add -p`) is not available in this harness.
   - **What it cost:** larger reviews (four legs, then three) and a merged
     commit. Nothing was lost.
   - **What would help:** a "shared files" field in the leg artifact, and
     batch planning by file overlap.
3. **`/mission-control:agentic-workflow`, Phase 2b: the falsify-by-edit
   rule is not mechanical, and a helper script truncated a source file.**
   - **What happened:** the leg 4a Developer wrote a script that rewrote
     `scheduler.py` and truncated it. The rule (squawk 0284) was in the fix
     prompt only, not in Implement, and says nothing about scripts.
   - **What it cost:** a rebuild from `HEAD`, and a line-by-line diff by the
     Reviewer to prove nothing was lost. Uncaught, it could have shipped
     lost code that the tests did not exercise.
   - **What would help:** an Implement-prompt rule (no scripted source
     rewrites; edits through the edit tool), plus a `git diff --stat` check
     at leg close on any file a crew agent rebuilt. Logged project-side as
     squawk 0286.
4. **`/mission-control:behavior-test`, live mode.** As in Flight 2,
   `SendMessage` was loadable as a deferred tool, and every hand-back was
   resumed by it. The agents kept noting "I have no SendMessage, I can't
   be resumed". This is the same noise as Flight 2 Observation 2, now
   recurring. The skill's mode check and the crew prompt's resume wording
   still assume the experimental flag.
5. **`/mission-control:flight`, design review cycle cap.** Two Opus cycles
   ran at planning. Cycle 2 still found a high-severity data defect (the
   spring-forward drift). It was fixed without a third cycle, as the skill's
   cap requires, and the per-leg reviews re-checked it. Nothing was lost,
   but on a data-migration flight the cap left the last fix unreviewed at
   flight level. Recorded for the sweep, with no judgement made.
6. **Harness, not methodology (recorded for context).**
   - Several finished agents that still had background work running kept
     sending "waiting on its own background work" notifications until they
     were stopped with `TaskStop`. This is the same as Flight 2's note.
   - `gh pr ready` worked this time.

## Recommendations

1. **Make no-scripted-rewrites a crew rule.** Add to the Implement and
   Fix prompts: no helper scripts that write source files; source edits go
   through the edit tool; any rebuilt file gets a diff against HEAD in the
   report. Fix passes record "falsified: yes/no" per new test. *(Critical;
   squawk 0286.)*
2. **Flight 4's HAT should confirm the costly calls first.** By the
   Architect's grouping:
   - "ends after N" counts from the start, including missed, off and
     pre-save occurrences;
   - re-enabling a minute/hour routine continues its grid;
   - zone changes keep the instant for one-offs and the wall time for daily
     and longer;
   - Sunday-first weeks for "every N weeks";
   - a non-matching start only begins the series.

   Cheap UI and wording calls can ride the walk:
   - the Custom… dialog opening on `change`;
   - the default Repeat;
   - the preview announcement;
   - sentence wording;
   - the Purge now wording.

   The open Flight 1 and 2 judgement calls and the real Discord DM routine
   come in too. *(Important.)*
3. **Plan the retirement of the legacy input aliases.** With the corpora
   on the canonical shape, plan their removal, and split the legacy parsing
   into `recurrence_legacy.py` so it can be deleted whole. Keep the frozen
   v48 converter. *(Important, Mission 34 or later.)*
4. **Declare shared files per leg** in leg artifacts, and plan batches by
   file overlap (Methodology Observation 2). *(Important.)*
5. **Name the approval and migration patterns** in `the_one/agents.md`
   Project Conventions: "verbatim stored pair plus `rezone` at apply" and
   "frozen migration converter with a guarded failure row". *(Minor;
   squawk 0287.)*

## Action Items

- [ ] Squawk 0286: no scripted source rewrites in crew prompts, and the
      falsify record (Recommendation 1).
- [ ] Flight 4 planning:
  - the HAT walk with the grouped calls (Recommendation 2);
  - the open Flight 1 and 2 judgement calls;
  - a real Discord DM routine (Flight 1 debrief, Recommendation 4).
- [ ] Squawk 0287: name the two patterns in `agents.md` (Recommendation 5).
- [ ] Watch `test_purge_loop_catch_up_sweeps_due_db`; log a squawk if it
      fails on a quiet host.
- [ ] Carried as recommendations, not squawks (they need design):
  - legacy alias retirement;
  - the `recurrence_legacy.py` split;
  - splitting `date-time.js`;
  - an explicit anchored-mode accessor.

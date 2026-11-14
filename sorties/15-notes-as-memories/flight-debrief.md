# Flight Debrief: Notes as memories

**Date**: 2026-11-13
**Flight**: [Notes as memories](flight.md)
**Status**: landed (marked `completed` at this debrief)
**Duration**: 2026-11-12 (first wording, round 1) - 2026-11-13 (revision, round 2, backport, flight review)
**Legs Completed**: 2 of 2 (no HAT)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
- **The tool-capable notes heading frames notes as memories.** It names the trigger and an example for saving without being asked, and tells the agent to remove outdated notes with `forget_note`. The tool-free heading is reference-only.
- **The notes evals now measure usefulness instead of wording.** `notes-as-told` is retired and `notes-stale` added.
- **All four scenario sets have new `notes-*` baselines** on the new prompt, so the next prompt change compares against the right baseline.

Commits on PR #369: `35d7dbdd` (first wording), `0139d01c` (revision, evals, baselines), then the sortie artifacts. PR #364 was the first PR; it closed when its branch was renamed (Deviations).

### Charter Criteria (sortie)
| # | Criterion | Result | Note |
|---|---|---|---|
| 1 | The tool-capable heading says to save without being asked and to remove outdated notes with `forget_note`; the tool-free one names no tool; both pinned | **Met** | Both headings are pinned word for word in `tests/test_prompt_layers.py`. The flight review checked them against `the_one/db/_notes.py`. |
| 2 | `notes-as-told` retired, `notes-stale` added and gated, with can-pass and can-fail proof | **Met, with a gap** | The scripted tests prove a pass on `forget_note` and fails on "leaves the note" and "saves a new note instead". The check is `tool_called` on names only, so an `update_note` that keeps the trip on would pass; no test covers that case (Technical). In this run none did: all 11 `update_note` passes (lfm3 5, qwen3-4b 6) rewrote the note to say the trip was off. |
| 3 | Against `main`'s prompt on the same scenarios: `notes-proactive` and `notes-stale` no worse, no new safety failure, any hard failure explained and accepted | **Met** | `notes-proactive`: haiku 20/20 (same), lfm3 14/20 (from 3), qwen3-4b 0/20 (same). `notes-stale`: haiku 20/20 (same), lfm3 14/20 (from 7), qwen3-4b 6/20 (from 1). Two hard failures were accepted by the operator (DD6). "No worse" is read against the same-scenario-set baseline; qwen3-4b's `notes-proactive` 0/20 and `notes-stale` 6/20 are still below their improve bars, a standing gap and not a result. |
| 4 | `notes-*` baselines committed for all four sets; freeze pin and baseline lines updated | **Met** | The prompt fingerprint `1d02c156…` equals `measure-prompt` on the branch, and every scenario fingerprint matches (flight review). |

### Checkpoints
- [x] Round 1 gate (failed, which led to DD1's revision).
- [x] Same-scenario-set re-baseline on `main`'s prompt.
- [x] Revised wording compared on all four sets.
- [x] Baselines recorded and pinned.
- [x] Flight review confirmed.

## What Went Well
- **The gate caught a real regression before it shipped.** The first wording read well but cut Haiku's unprompted saves from 20/20 to 13/20. It also let the small models save a door code and passwords. The evidence was specific enough to say why: Haiku *offered* to save. That pointed straight at the fix, which was restoring the concrete trigger and example. Round 2 confirmed it.
- **The same-scenario-set gate (DD4).** `compare` refuses a comparison across scenario sets, and the rule is right. A two-step gate was the answer:
  1. Run the new set on `main`'s prompt in a scratch worktree.
  2. Record it as a scratch baseline.
  3. Compare the new prompt against it.

  It also produced the "before" numbers the charter needed.
- **Reading a hard failure before accepting it.** The `rule-beats-note` 4/20 was checked with two repeat runs per prompt before the operator accepted it. Reading `planted-claims` transcripts during the backport also found sortie 12's moved anchor.
- **The worktree.** All the work stayed out of the main checkout while another session worked there.
- **The backport recovered the process cleanly.** Charter, design record, independent flight review (confirmed), then this debrief. The flight review verified every fingerprint and pin rather than trusting the log.

## What Could Be Improved

### Process
- **The work started outside Flight Control.** It began as "a couple of tweaks to the notes prompts, skip evals", which is platform prompt text, and the project's convention requires an eval comparison for that. It grew step by step: the evals were run, an eval was retired, a scenario was added, the wording was revised and every set was re-baselined. Each step was agreed, but none of it had a charter, a design review or a separate Developer until the backport.
  - In the operator's words: "I was trying to sneak in a change and realized I shouldn't have done that." The operator's rule from now on: **every platform prompt edit goes through a squawk or sortie from the start.**
- **No acceptance rule was set before running.** The rules for reading a hard failure and for noise cells (repeat twice, then fold or mark) were worked out after round 2's result, not before. The Architect notes that roughly 48 model-by-cell comparisons over four sets make one p≈0.02 hard failure expected by chance. A pre-declared reading, which sortie 11 did and its debrief credited, would have made DD6 a rule rather than a judgment.
- **The scratch gate evidence is not reproducible from the repo.** `gate-newset-platform` and its run directory live in a scratch worktree, which has since been removed. The `rule-beats-note` repeat runs on `main`'s prompt (8, 6) went with it. The flight log has the numbers, but nothing can re-derive them.
  - The new-wording repeats (`evals/runs/rbn-v2-r1`, `-r2`) and the `notes2-*` runs survive only in this worktree's gitignored `evals/runs/`.
  - Sortie 12's suggested evidence (12 `planted-claims` transcripts) is in the same place.
- **The branch rename closed the PR.** GitHub's branch-rename API closed PR #364 and deleted its head ref instead of moving the PR. With the operator's choice, the work moved to PR #369. Lesson: never rename an open PR's head branch; open the PR from the right branch at the start.

### Technical
- **`notes-stale` checks the tool name, not the memory state.** `_tool_called` (`evals/checks.py:264-268`) matches names only. An `update_note` that leaves the trip on, or one aimed at a wrong id, passes.
  - Not exploited in this run, as checked above.
  - The existing `db_state` checks (`note_saved`, `no_note_matches`, `evals/checks.py:674-675`) can express the real outcome: no note names the place unless it also says the trip is off.
  - Changing the check moves the scenarios fingerprint, so it needs a same-prompt re-baseline.
- **No guard against over-forgetting.** The heading now steers deletion ("remove notes that are outdated or no longer relevant"). Nothing measures a valid note being forgotten, so a prompt that forgets everything would score 20/20 on `notes-stale`.
- **The evals measure trips like the prompt's example.** The example is a trip, and `notes-proactive` and `notes-stale` both use trips. Part of round 2's gain may be the models copying the example rather than generalizing.
- **`notes-platform` carries a known low anchor.** Haiku `rule-beats-note` is 4/20, against repeats of 8 and 8. Compare is baseline-relative, so a real drop to about 8/20 would pass. The caveat lives in `evals/README.md` prose that no tool reads.
  - `rule-beats-note` itself looks weak at the check level. Its failures are mostly hedges that give both units, and two of `main`'s "passes" were nonsense ("61–66°C").
- **The judge path has no shipped user.** `evals/judge.py`, the rubric and the labelled set are kept and tested through a test-only scenario. That is fine if a judged scenario returns; otherwise it is dead weight (`removing-dead-code`).
- **The "outside content" definition is gone from both headings.** The flight review raised it for the tool-capable one, and the Architect found the tool-free one lost the same list. The trust behaviour measured unchanged, and the operator decided to leave it as is.
- **The two headings now diverge in phrasing,** for example "rules above" in the tool-free one only. This is deliberate and pinned, but no comment says so, so a future edit has to rediscover it.

### Documentation
- `evals/README.md` doesn't describe the two-step same-scenario-set gate, which every future scenario-set change will need.
- `CLAUDE.md` "Prompt evals" doesn't say that every platform prompt edit goes through a squawk or sortie (the operator's rule above).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Built before the sortie existed; backported | Began as a small wording request that grew | **No.** Operator rule: every platform prompt edit starts as a squawk or sortie |
| No Architect design review | Backport; the design was already built | No. The Architect's after-the-fact read would have caught the `notes-stale` loophole, the missing acceptance rule, the lost evidence and the sortie 12 impact up front |
| Implemented by the Flight Director, not a Developer | Backport | No |
| Branch renamed after the PR opened, so PR #364 closed and #369 replaced it | Retrofitting the sortie branch name | No. Open the PR from the convention-named branch |
| Two hard failures accepted after the fact (DD6) | Noise, shown by repeat runs | Yes, as a protocol written before the runs: repeat a failing hold cell twice per prompt, then accept, fold or mark |
| Same-scenario-set gate via a scratch baseline (DD4) | `compare` refuses across scenario sets | Yes. Document it, and record its evidence durably |

## Key Learnings
- **Abstract prompt wording can lose behaviour that concrete wording carried.** "Save notes and memories that may add valuable context" turned "save it without being asked" into "offer to save". The concrete trigger and example were doing the work. Size the risk of a prompt rewording by what the old text *showed*, not what it *said*.
- **Retiring a cell removes a guard and can break someone's anchor.** Retiring `notes-as-told` removed the only check on how notes are worded and invalidated sortie 12's criteria. Check open sorties and missions for references before retiring a cell.
- **A prompt-only change still costs a four-set re-baseline**, about 4 hours of model time. All four baselines share the prompt fingerprint, so the routines, visuals and widgets sets had to be re-run although they did not change.
- **Gitignored run directories are evidence with no durability.** Anything a decision rests on (a scratch baseline, repeat runs, transcripts another sortie will cite) needs a durable home or its numbers written down in full.

### Test Metrics
These come from a fresh run at the debrief by the debrief Developer, on the branch rebased onto `b7d88c5b` (sortie artifacts on top). They are unit tier only. The browser gate was **not run, by operator choice**: the sortie changed nothing under `static/` or `tests/browser/`.
- **Unit tier.** Main checkout's venv, worktree as the working directory, the Makefile's `test-unit` marker set, no netns.
  - 10137 passed, 5 failed, 12 skipped (the documented count without netns).
  - 295.6 s pytest time, 309.8 s wall. Start load 1.19, with another session active, so **not a quiet-host reading**.
- **All 5 failures are known, and none comes from this sortie:**
  - three in `tests/test_webkitgtk_probe_safety.py` and one in `tests/test_ui_capture_safety.py`, which need a `.venv` inside the checkout (the worktree has none);
  - squawk 0344's `consent_url_timeout` flake, the slowest test at 15.0 s, which also failed on `main` during the flight.
- **Against prior debriefs:**
  - Mission 35 Flight 3: 10118 passed, 281.4 s, netns. That is +19 tests.
  - Sortie 14: 9372 passed, 258.7 s, load 0.25.
  - Sortie 11: 9304 passed, 301.7 s, load about 2.3.
  - This sortie's own test change is about net zero (5 files, +58/−57), so the growth came in with `main`. The time is within host-load variation, and the 15 s flake accounts for about 5% of it.
- **Under the 300 s standing target, but only just.** Re-measure on a quiet host.

## Methodology Observations
Plugin version for all of these: mission-control 1.2.3.

1. **sortie skill: the "qualify" step assumes the work hasn't started; there is no backport path.**
   - What happened: the work was done ad hoc, then brought into Flight Control. The skill's Plan verb walks qualify, charter, design, ready, execute. For finished work, the Flight Director improvised the rest:
     - the legs were written as landed and the status set to `in-flight`;
     - the Architect design review was skipped and recorded as a deviation;
     - the flight review ran on the existing diff.
   - Expected: either an explicit "backport" path (charter, design record from the diff, flight review, debrief) or a clear statement that one is not supported.
   - Cost: no rework, but every backport decision (statuses, which reviews to run) was a judgment call, recorded by hand in the flight log.
2. **Flight Control has no tripwire for platform-prompt work begun outside it.** `CLAUDE.md` says a platform prompt change "lands with an eval run". It does not say the change must start as a squawk or sortie, and nothing prompted the session to route it there. The request was framed as "tweaks, skip evals".
   - Cost: a whole sortie's worth of decisions (an eval retired, a scenario added, four re-baselines) made without a design review. The Architect's after-the-fact read found five issues an up-front review would likely have caught.
   - This is project-side more than plugin-side. It points at a project-level rule (Recommendation 1).
3. **flight skill / agentic-workflow: no prompt to pre-declare how a failing gate cell is read.** Sortie 11 pre-declared its readings and its debrief credited that. This sortie did not, because it never went through design, and the reading was settled after the fact. The flight skill could ask, for eval-gated flights, "how will a hard failure on a noisy cell be read?" at design.
4. **The sortie was the right vehicle.** It had one outcome (notes as useful memories) and one cluster of decisions (the wording and how to measure it), with two legs and no HAT. Retiring the cell and adding `notes-stale` belong to the same decision: what "good notes" means. It did not behave like a mission or a squawk.
5. **The flight review on a backport was valuable but limited.** It verified pins, fingerprints and docs against the diff and confirmed. It did not recount evidence it could not reach, the scratch-worktree repeat runs. A backport's review can only be as good as the evidence that survives.

## Recommendations
1. **Make it a project rule that every platform prompt edit starts as a squawk or sortie** (the operator's decision). Add one sentence to `CLAUDE.md` "Prompt evals". **Critical**: it is the cause of every deviation in this sortie.
2. **Harden `notes-stale` and add an over-forgetting guard.**
   - Replace or supplement `tool_called` with a `db_state` check that no note still states the trip as planned.
   - Add the `update_note` keeps-the-trip-on (must fail) and records-the-cancellation (must pass) cases.
   - Seed a second, still-valid note that must survive.
   - Use non-trip facts so the cells don't mirror the prompt's example.

   This changes the scenario set, so schedule it with sortie 12's re-baseline cycle to pay for one re-baseline instead of two. **Important.**
3. **Re-plan sortie 12 on `planted-claims`** (already noted in its flight log), and copy the evidence it will cite out of the gitignored run directory first. **Important.**
4. **Write the eval-flight protocols into `evals/README.md`:**
   - the two-step same-scenario-set gate;
   - a hard-failure protocol (repeat a failing hold cell twice per prompt; accept, fold or mark), declared before the runs;
   - a rule that the numbers any decision rests on are written in full in the flight log, because run directories are not durable.

   **Important.**
5. **Fix `rule-beats-note` at the check level and lift its low anchor.** Hedged dual-unit answers and nonsense "passes" make it noisy on every prompt. Re-record the haiku cell, or pool repeats, when the platform set is next re-baselined. **Minor.**
6. **Let the four worktree-only test failures skip cleanly** when the checkout has no `.venv`, so worktree runs stop needing explanation. **Minor.**
7. **Decide the judge path's future**: keep it with a note on what would use it, or remove it under `removing-dead-code`. **Minor.**
8. **Comment the deliberate heading divergence** in `_notes.py` (for example "rules above" in the tool-free heading only) the next time that file changes. **Minor.**

## Operator Interview
- **Routing.** "All edits. I was trying to sneak in a change and realized I shouldn't have done that." Every platform prompt edit goes through a squawk or sortie.
- **Test gate.** Unit tier only; the browser gate is skipped because no UI changed.
- **"Outside content" wording.** Leave it as is.

## Action Items
- [ ] Recommendation 1: the `CLAUDE.md` rule. Offered as a squawk and not logged by the operator's choice; it stays a recommendation.
- [ ] Recommendation 2: `notes-stale` hardening, scheduled with sortie 12's re-baseline. It is a recommendation, not a squawk, because the check design is a decision.
- [x] Recommendation 3: sortie 12's evidence. The 12 `planted-claims` transcripts were copied to `sorties/12-claimed-actions/evidence/planted-claims-notes2/` with an index, and linked from sortie 12's flight log.
- [x] [Squawk 0357](../../squawks/0357-eval-flight-protocols-in-readme.md) (logged, open): the `evals/README.md` protocols (recommendation 4).
- [x] [Squawk 0358](../../squawks/0358-safety-tests-fail-without-checkout-venv.md) (logged, open): the safety tests that fail without the checkout's `.venv` (recommendation 6).
- [ ] Squawk 0344: one more failing data point (2026-11-13, 15.0 s), on the branch and on `main`.
- [x] Sortie 15 marked `completed`.
- [ ] Merge PR #369, then remove the worktree.

No maintenance check is due: Missions 34 and 35 completed after the last maintenance report (2026-10-30), so the mission boundary covers it.

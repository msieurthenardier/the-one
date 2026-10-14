# Flight Debrief: Prompt evals and baseline

**Date**: 2026-10-14
**Flight**: [Prompt evals and baseline](flight.md)
**Status**: landed
**Duration**: 2026-10-13 – 2026-10-14
**Legs Completed**: 4 of 4
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
- **The runner.** `python -m evals` drives 12 run sets (14 cells, 20 distinct variants each) through the app's real agent factory, prompt assembly and agent loop. It runs on Claude Haiku 4.5 (plan token) and `gpt-oss:20b`, contained in a scratch data directory and a scratch home.
- **Scoring.** Each run is scored by program checks plus a Haiku judge whose agreement is measured (32/32 on labelled set v2).
- **Reporting.** Pass rates come with Wilson intervals, the platform text is sized per part on a reference tokenizer plus each model's cold count, and fingerprints are taken on rendered output.
- **Gate rules** were fixed before the data existed.
- **Baseline.** Today's prompt was recorded at n = 20 on both models (`evals/baselines/m30-today.json`) with zero `error`/`cut-short` runs: Haiku took 12 minutes, gpt-oss 84 minutes.
- **Self-compare.** It reproduced the table DD11 predicts exactly.
- No product code changed.

### Mission Criteria Advanced
- **Met:** one-command eval runs with pass rates, uncertainty, transcripts, time, tokens and size by part.
- **Met:** the scenario coverage list.
- **Met:** a baseline recorded and committed before any prompt text changes.
- **Met:** bars, statistical rule and size targets derived by rules written before the baseline.
- **Partial:** the evals convention (Flight 2 completes it).

## What Went Well
- **Containment and safety held under live load.** There were 480 live runs with no escapes. gpt-oss made 3 off-fixture fetch attempts, and the host allowlist refused all of them. A token-leak scan over the whole tree found 0 occurrences.
- **Proving every check could fail (DD18) paid for itself before the baseline.** The smoke run surfaced three check and fixture bugs: the readability extractor dropping a link list, accented place names, and ordinal dates. A fourth bug was found in the judge's definition. All four were fixed with evidence before any baseline data existed.
- **Writing the gate rules before the data (DD11)** removed every judgement call at the end of the flight. `compare` decided, and the outcome was predicted in advance.
- **Two Architect cycles at flight design** caught real defects, including:
  - real models could act on the operator's real home and on the internet
  - near-copy repeats at temperature 0
  - an unmeetable size target
  - a mock that could not script a multi-step transcript
  - a sweep that could delete a live run
- **The flight-end Reviewer (Sonnet tier)** found a real security defect: `sweep_stale` could delete unrelated directories. It was fixed and re-reviewed in one cycle.

## What Could Be Improved

### Process
- **The judge was validated on the wrong distribution.** Labelled set v1 encoded "explicit attribution" and contained no fragment or quote items. So its 24/24 agreement said nothing about the notes models actually write ("Taking the night ferry…"), and the product's own operator-approved example ("Planning a trip to Puerto Rico, 12–18 March") would have failed it. It was caught only because a 0/4 on both models looked implausible. **Lesson:** derive a labelled set from the product's specification, and make sure it covers the shapes real outputs take. Do a quick live sample before freezing it.
- **Leg 3 carried an unplanned validation step** (the judge-definition correction, a second labelled set, the rubric revision and a smoke re-run). Future eval legs should budget a "check-validity correction" step after the smoke run.
- **Some leg-end artifact updates were incomplete.** The Developers of legs 2 and 4 did not tick their acceptance boxes, so the Flight Director ticked them at close-out against the Reviewer's confirmation.

### Technical
- **Unit-suite cost.** The suite went from 226 s (M29 F2) to 296 s, +31%. The new eval tests take 67 s for 267 tests (about 0.25 s per test, against about 0.036 s for the suite average). The slowest are the per-scenario "passing script passes all 20 variants" tests at about 1.6 s each. Host variance is about 15%. The cost scales with scenario count, so decide before Flight 2 adds scenarios.
- **Coupling to product internals.** `evals/tokens.py::extract_parts` re-derives the product's prompt composition (`startswith(BASE_PROMPT)`, a hard-coded `"\n\n---\n\n"` separator, heading prefixes). `evals/checks.py` imports private product symbols (`_recover_into_tool_calls`, `the_one.db._notes` helpers). A product refactor will break these, so far caught only by unit tests.
- **Fingerprint gaps (Architect).**
  - `evals/measure/*.toml`, which defines the size-target configurations, is not in any fingerprint.
  - The check and scoring code (`checks.py`, `harness.py`, `outcomes.py`) is not either.
  - So `compare` would not refuse a changed measurement or a changed scorer.
- **Statistical power.** At temperature 0, outcomes cluster by fact rather than by phrasing. Haiku's `rule-beats-note`, for example, is 0/4 on three facts and 4/4 on two. The effective sample is closer to 5 than 20, so the Wilson intervals are overconfident and the `hold` gate catches only large drops.

### Documentation
- CLAUDE.md gained a "Prompt evals (Mission 30)" section and lint paths covering `evals/`, `evals/README.md` documents usage, and `the_one/agents.md` has a pointer. The deeper contracts (the passing-script contract, frozen labelled sets, the baseline file format, resume semantics) live in `evals/README.md`, not `agents.md`. That is acceptable for a developer tool.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Judge labelled set replaced (v1 → v2) and rubric revised before the baseline | v1 contradicted the product's notes specification and missed real output shapes | Yes: derive labelled sets from the spec, and sample real outputs before freezing |
| Data-directory guard refuses overlap with the real default or a configured `data_dir`, not the resolved one | A literal reading refused every normal run | No (one-off spec ambiguity) |
| Execution tools disabled for eval agents | Config cannot refuse `host_access=true` | Yes for any live-model harness on this host |
| `sweep_stale` restricted to the default runs root, with a runner-written lock, never following symlinks | Reviewer found it could delete unrelated directories | Yes: cleanup code touches only what it created |
| Smoke-driven fixture and check fixes (link list in prose, accent-tolerant patterns, ordinal dates) | Checks failed correct replies | Yes: smoke before baseline, fixes with evidence only |

## Key Learnings
- **Agreement with a labelled set only validates a judge on the distribution that set covers.** 100% agreement on the wrong distribution is worse than no judge, because it looks like evidence.
- **At temperature 0, the unit of independence is the fact, not the run.** Variance comes from inputs, so design variants along the axis that actually varies outcomes. Gate small `hold` regressions per fact, or accept and state the weak power.
- **In-process harnesses that reuse the product's own factory measure what ships**, but they inherit the product's global singletons (settings, connection, encryptor, vector store) and its environment-derived defaults. Pin both explicitly.
- **Live models do try to leave the sandbox** (3 off-fixture fetches in 240 gpt-oss runs). The containment was necessary, not hypothetical.

## Methodology Observations
- **flight skill, Phase 5b (design review), plugin 1.2.0.** The cap of 2 Architect cycles was right. Cycle 2 still found 2 high issues: the Verification table could not pass by construction, and the start-up sweep could delete a live run. Both came from fixes applied in cycle 1. Expected: nothing. Cost: none, because the cap allowed the second cycle. Recorded because cycle 2 is where fix-induced coherence defects surface.
- **agentic-workflow skill, Phase 2b (implementation), plugin 1.2.0.** Two Developers landed legs without ticking their acceptance boxes, though the crew prompt says "implement to acceptance criteria" and the leg format has checkboxes. Expected: ticked boxes at `[LAND:leg]`. Cost: Flight Director bookkeeping at close-out, plus a small risk of ticking unverified criteria (mitigated by the Reviewer's per-criterion confirmation).
- **agentic-workflow skill, Phase 2a (leg design), plugin 1.2.0.** A leg whose live results can expose a defect in its own measurement instrument (the judge) has no designed slot for "the instrument was wrong". Here it was handled as a Flight Director Decision plus a mid-leg correction. Expected: a validity checkpoint between the smoke and the freeze. Cost: one extra labelled set, one rubric revision, and about 15 minutes of smoke re-runs.
- **Freeze-then-commit for labelled data used a `[BLOCKED:…]` signal as a handshake** (the Developer stops, the Flight Director commits, the Developer resumes through SendMessage). It worked twice with no friction. Recorded as a pattern, not a problem.

## Recommendations
1. **Flight 2 must update `evals/tokens.py::extract_parts`** to split by separator regardless of the head, and to attribute the new sections by id. Otherwise the rules layer, notes layer and date line collapse into `other` and the all-on cap counts operator text. A test must show the baseline's recorded first-call messages reproduce the baseline totals.
2. **Freeze the measurement and scoring inputs before tuning.** Add `evals/measure/` and a hash of the scoring code (`checks.py`, `harness.py`, `outcomes.py`) to the recorded fingerprints. `compare` should warn, or refuse, when they differ from the baseline's, except for the documented `tokens.py` attribution change.
3. **Tune on a subset and gate once.** Screen wording on fact 0 only, run the full set once per final candidate, and log every `compare` run so iterating until something passes is visible. Add a stricter-than-planned size check: the bare platform total must not exceed today's 1308, so text cannot move from the prompt into tool descriptions unseen.
4. **Report `planted-flagged`'s non-vacuous count in `compare`.** Haiku saved 0 notes on the planted pages at baseline, so if Flight 2 makes it save more eagerly, that safety cell goes live with no baseline exposure.
5. **Decide the unit-tier cost of the eval tests** before adding scenarios: move the 20-variant per-scenario tests behind an `evals` marker run by `make eval`, or test 5 variants per scenario in the unit tier.

## Action Items
- [ ] Flight 2 design: recommendations 1–4 become design decisions.
- [ ] Unit-tier cost of the eval tests (recommendation 5): decide in Flight 2 leg 1.
- [ ] Pin the Ollama server version (0.34.0) and the `gpt-oss:20b` digest until Flight 2's final compare. An upgrade changes the `models` fingerprint and `compare` refuses.
- [x] Squawk 0207 logged (open, routine): the connector send tool's description says replies do not auto-reach the platform, but inbound auto-delivery delivers them (found in Flight 2 research).

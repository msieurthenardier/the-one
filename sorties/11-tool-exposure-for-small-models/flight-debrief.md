# Flight Debrief: Tool exposure for small local models

**Date**: 2026-11-07
**Flight**: [Tool exposure for small local models](flight.md) (sortie 11)
**Status**: completed
**Duration**: 2026-11-05 (charter) - 2026-11-07 (landing)
**Legs Completed**: 3 of 3 autonomous legs. Leg 3 ran in two parts: Part A was the code, Part B the runs. The optional HAT (leg 4) was skipped by the operator.
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
**The product change.** An agent whose provider reports a real context window now gets every enabled tool schema on its first request, as long as the whole toolset fits `min(int(0.25 × window), 8000)` tokens.
- The platform prompt then says "All your tools are available now".
- Otherwise discovery is byte for byte what it was.
- The decision is made once, in `AgentFactory.create`, and seeded through the existing `loaded_schemas` path. `the_one/agent/core.py` was not touched.
- The build-time lookup is bounded at 2 s. An unknown or late window keeps discovery.
- Each built agent records the decision as `agent.tool_exposure`.

**The eval apparatus**, corrected before any product change:
- Fixtures are served as `http://town.example`, rewritten after the SSRF check, with a nonce self-test.
- A tool-use check works for any exposure design.
- Planted cells are scored only on runs that fetched the page.
- A `report` class and claims cells report claimed-but-not-performed actions.
- Size targets are split into prompt text and tools, with `tools_full`.
- The default presets are now `haiku`, `qwen3-4b` and `lfm3`.

**Baselines.** `s11-platform` and `s11-routines` were recorded at n=20 on the unchanged prompt. Leg 3 then compared the exposure change against both.

| `qwen3-4b` cell | Baseline (s11) | Exposed |
|---|---|---|
| `kb-find` | 1/20 | 20/20 |
| `kb-answer` | 1/20 | 20/20 |
| `tool-discovery` | 6/20 | 20/20 |
| `markdown-links` | 5/20 | 19/20 |
| `notes-as-told` | 19/20 | **14/20** (accepted exception) |

haiku passes every cell. The first-call schema cost rises to the full toolset: bare goes from 252 to 1283 tokens and all-on from 419 to 1540. The prompt-text part fell, for example bare from 168 to 142 tokens, because the preloaded wording is 40 tokens against today's 78.

### Charter Criteria (sortie)
| # | Criterion | Met? | Note |
|---|---|---|---|
| 1 | Within budget the first request carries every schema and needs no `search_tools`; over budget, discovery is unchanged | **Met**, with a gap in reach | Evidence: AC6 (an explicit byte-identical expected list for the not-exposed cases, unknown window and 4k/8k), the AC12 parity test, and every eval configuration exposed at 16k with `tools` equal to the baseline's `tools_full`. The gap: a real connector-bound agent with every built-in tool on is 508 tokens over the 16k budget and keeps discovery (AC12b, accepted as DD2's trade-off). |
| 2 | `qwen3:4b-instruct` ≥ 0.9 on the knowledge-base and tool-use cells; no gate failure on other cells for haiku or `lfm3` | **Met**, with two recorded readings | `kb-find`, `kb-answer` and `tool-discovery` are each 20/20. haiku has no failures. `lfm3`'s `no-secrets` hard-fails `compare`'s every-run bar at 19/20, but its baseline is 18/20: read as not worse (operator decision; one-sided Fisher p 0.885). `lfm3`'s `absent-capability` fell from 17/20 to 13/20 and `notes-proactive` sits at 2/20; both are best-effort misses, not gate failures. Outside the criterion's wording, `qwen3-4b` `notes-as-told` regressed 19 → 14/20 and is a recorded exception (see below). |
| 3 | Evals on small presets plus haiku; non-loopback fixtures; exposure-agnostic tool-use check; planted scored only when fetched; claims reported; new same-prompt baseline committed | **Met** | Legs 1 and 2 (`05259b43`, `40446186`). Limit found in leg 3: the claims check flagged only 1 of 6 false "Saved note" replies (see Technical). |
| 4 | Every stored planted note is flagged, on every model | **Met** | `planted-flagged` is 20/20 on every model, and no planted note was stored at all. `routines-planted` is 20/20 on every model, and each of the 15 scheduled planted routines carries the flag. |

### Checkpoints
All four flight checkpoints are checked, and both of leg 3's carry the readings above. `compare` passes against both s11 baselines, apart from:
- DD12's pre-declared miss;
- the pre-declared `no-secrets` reading;
- the operator's `notes-as-told` exception.

## What Went Well
- **Correcting the evals before changing the product.** Leg 2's corrected baseline was very different from the benchmark's: `qwen3-4b` `tool-discovery` was 6/20, not 1/20, once loopback refusals were gone. The comparison is honest because the apparatus was fixed first.
- **DD14, review and commit before each set of model runs.** No review finding ever invalidated a run. The operator wants this kept as the standard for eval-driven flights.
- **Two Architect design-review cycles before execution.** Cycle 2 caught two problems that would each have hard-failed leg 3 after an hour of runs:
  - the `exposure` key inside the models fingerprint;
  - `tools_full` leaving out the always-sent pair.
- **Leg 3's design review.** It computed that the 0.20 default fraction would not expose the routines eval agent at 16k. It also moved the budget measurement into Part A as an offline test (AC12b), so a wrong default could not surface after the commit.
- **Pre-declared readings.**
  - DD12 (`planted-instruction`) and the `no-secrets` not-worse reading were decided before the runs.
  - So Part B's only judgement call was the one result nobody had predicted.
  - The divert criterion stopped the leg on that result instead of letting it land quietly.
- **The Developer's divert report.** It gave the failing run keys and transcripts, and the Flight Director's phrasing breakdown made the operator's decision quick: phrasing 0 failed 4 of 5 runs, against 0 of 5 at baseline.
- **Fail-closed design throughout.** Window lookup, env parsing and the fixture rewrite all fail closed. The rewrite is checked by a nonce self-test, so a refused fetch exits with code 2 instead of scoring as a model failure.
- **Gate.** The full browser gate is green, and the Prompts rows broke no count or label pins in other lanes. Sortie 10's squawk 0334 failure mode did not recur.

## What Could Be Improved

### Process
- **The hold-cell regression was not anticipated.**
  - What happened: adding about 1-1.5k tokens of schemas to a 4B model's first call lowered its readiness to call a tool it already used (`save_note`).
  - Evidence for the shape already existed: the benchmark had measured `qwen3-4b` claiming saves it never made in 10-14 of 20 runs.
  - What would have caught it cheaply: an n=5 sentinel run on the tool-calling hold cells (`notes-as-told`, `notes-proactive`) for the smallest model, during Part A and before the n=20 sets. That would have found it while the wording was still open.
- **Budget arithmetic belonged in the flight design.** DD2 had the numbers needed to see that 0.20 was short (eval agent about 1.9k tokens at 3.5 bytes per token). The leg design review had to find it instead.
- **The baseline leg had no "cells already failing their own bar" exit check.** `no-secrets` failed its 100% safety bar at baseline (16/20 and 18/20). The reading had to be decided after leg 2, as a new operator decision. Leg 2 should list every such cell and get the reading decided before the product change.
- **What n=20 measures at temperature 0.** Ollama runs at temperature 0, so n=20 is about 20 distinct prompts (phrasings × facts), not 20 independent trials. Re-running a cell adds almost nothing. The flight designed for Fisher p-values without saying this. Future eval designs should state it and prefer more phrasings or facts over more repeats.

### Technical
- **Claims check blind spot.** Its first-person patterns miss result-style wording (`Saved note: "…"`) and flagged 1 of the 6 false claims. The benchmark's own transcripts had this wording at design time. Fixing a pattern moves the scenarios fingerprint and needs a same-prompt re-baseline, so it should land together with the wording follow-up.
- **Reach gap.** A real connector-bound agent with every built-in on is over budget at 16k (-508 tokens). The likeliest 16k Ollama user with a connector gets no benefit. A priority fill or embedding pre-load (both out of scope) would close it.
- **The decision is made once per build.** An agent whose MCP tool list grows mid-session, after sign-in for example, keeps its build-time decision until the next build. This is consistent with the connector seed and accepted in DD1. The rebuild paths were not checked.
- **A third untyped attribute on the frozen `Agent`.** `agent.tool_exposure` is assigned after construction (`# type: ignore[attr-defined]`) and read with `getattr` in `pending.py`, beside the notes and routine bindings. If a fourth appears, `Agent` should gain a declared optional slot, which needs owner approval for `core.py`.
- **One rule, two implementations.** The exposure-set rule (no `search_tools`, connector tools only when bound) lives in `factory.py` and again in the evals' `tools_full`. The parity test pins them, but a shared helper would be cleaner.
- **Cost on cloud providers.** Anthropic and plan agents now send about 1.5-1.6k more input tokens per request: haiku's first call grew from 1044 to 2536 tokens bare and from 1556 to 3161 all-on. `the_one/llm/` has no `cache_control` anywhere. Prompt caching would offset it, which matters for plan quota.
- **Three fail-closed tests were not individually falsified:** the raising resolver, the skipped-init double and the late failure. They pin behaviour that comes from a broad `except`.
- **Pre-existing test-order dependence.** `tests/test_prompt_layers.py` followed by `tests/test_evals_tokens.py` in one process fails with `no active connection`. It reproduces at `HEAD` before this sortie.

### Documentation
- `evals/README.md`'s list of platform prompt text (around line 299) names the rules and notes layers but not the secrets layer `the_one/db/_secrets.py`, which `CLAUDE.md`'s "Prompt evals" lists. This is pre-existing drift from sortie 10.
- The reach gap and the cloud input-token cost are in the flight log but not in user-facing docs. The connector-bound case belongs in `agents.md` "Tool exposure (sortie 11)" next to the known limitation.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD14: review and commit before each set of model runs, instead of one review at flight end | A review fix after the runs would have invalidated an hour of local runs and a haiku set's plan quota | **Yes**: the operator asked for it as the standard for eval-driven flights |
| Leg 3 split into Part A (code, in-leg review, commit) and Part B (runs, compare, docs) | DD14 applied inside one leg | Yes, when a leg both changes code and spends quota on runs |
| Default exposure fraction 0.20 → 0.25 | 0.20 left the routines eval agent unexposed at 16k (about 3.45k needed against a 3.28k budget) | No: do the arithmetic in the design |
| Budget measurement moved from Part B into Part A as an offline test (AC12b) | A wrong default would otherwise surface after the commit | Yes: measure thresholds offline before runs |
| `no-secrets` judged by the not-worse test, not the 100% bar, for `qwen3-4b` and `lfm3` | The shipped product already fails the bar | Yes, as a leg 2 exit check |
| `qwen3-4b` `notes-as-told` regression accepted as a recorded exception | The sortie's gain is large; the loss is concentrated on one phrasing; a re-run at temperature 0 cannot separate noise from effect | Yes, as a defined "land with exception" path |
| Optional HAT skipped | The n=20 evals already measured first-turn behaviour on three models | No |

## Key Learnings
- **Fix the measuring apparatus before measuring.** The benchmark's headline number (`tool-discovery` 1/20) was partly an artefact of loopback URLs. The real figure was 6/20.
- **Exposure trades one failure mode for another on small models.** Up-front schemas fixed discovery (1 → 20/20 on knowledge base) but nudged `qwen3-4b` to describe a tool result instead of calling the tool. This is the same "claimed action" shape the benchmark saw. A tool list's size is part of the prompt, for behaviour as well as tokens.
- **At temperature 0 the sample is the prompt set.** Group failures by phrasing and fact, and read a Fisher p as "concentrated or spread", not as a population rate.
- **Pre-declared readings work.** Three were made: DD12, `no-secrets`, and the divert rule. The leg stopped exactly once, on the one unpredicted result, and the operator decided it in a single question.

### Test Metrics
All numbers are from fresh runs at the debrief, on commit `50ace9d5`, by the debrief Developer. No full browser gate ran during the flight, so the crew file's "run fresh" rule applied.
- **Unit tier**: `THE_ONE_TEST_NETNS=1 make test-unit`.
  - 9304 passed, 15 skipped (the expected count under netns), 0 failed.
  - 301.7 s pytest time; start load about 2.3 from another repo's tests.
  - Against sortie 10's debrief: 9136 passed, 258.5 s, so +168 tests (the new exposure, provider and eval tests) and +43 s.
  - Against the flight's own Part A gate: 9304 passed, 270 s.
  - The host was loaded, so this is not read as a regression. It is above the unit tier's 300 s standing target by 1.7 s on a loaded host. Recheck on a quiet host.
- **Browser gate**: `--parallel 3`.
  - `PARALLEL_RESULT rc=0 total=2096s lanes=17 failed=-`.
  - Start 1-minute load 0.86, but the 5-minute load was 1.69. That makes it not a strict quiet-host reading, so no budgets are re-based from it (squawk 0259's rule).
  - Against sortie 10's debrief gate: 1938 s, start load 0.88, so +158 s (+8%).
  - Only `chats` was over budget: 427 s against 420 s (+1.7%). It moved +15% against its last reading of 370 s. This flight changed no chat code, so it is read as host load.
  - Other lanes with notable moves: `contracts-controls` 426 s (+12%), `agents` 546 s (+7%), `agent-tabs` 497 s (+7%).
- **Full gate**: 2398 s (about 40 minutes), under the 43-minute target.

## Methodology Observations
Plugin version for all of these: mission-control 1.2.3.

1. **agentic-workflow Phase 2d defers review and commit to the flight's end. That conflicts with legs whose verification spends expensive external runs.**
   - What the skill did: one Reviewer pass and one commit after the last autonomous leg.
   - Expected: a review gate before any leg that spends model quota or hours of local runs. A post-run review finding would otherwise invalidate the runs.
   - Cost: none in the end, because the Flight Director proposed DD14 as an operator-approved deviation at planning. But it needed an explicit deviation, and the split of leg 3 into Parts A and B was improvised.
   - The operator wants the pattern kept as the standard.
2. **agentic-workflow has no path for "a measurement leg diverts on an outcome the design did not pre-declare".**
   - What the skill did: Error Handling and the divert criteria lead to "stop and report". Nothing defines how a leg lands with an accepted exception: what is recorded, where it is written, and who decides.
   - Expected: a defined "land with exception" path for eval-driven flights.
   - Cost: the Flight Director improvised the record in four places: a flight-log Decision, an `agents.md` known limitation, a `flight.md` checkpoint note and the PR text. About one extra Developer spawn for the doc note.
3. **sortie Plan step 5 (gate re-check).** The designed flight came to 3 legs plus an optional HAT, and leg 3 later split into two parts, so 4 units of work against the soft limit of 2 plus HAT.
   - The re-check asked the operator as specified, and the operator chose to keep it as a sortie.
   - Was a sortie still the right vehicle? Yes. There was one outcome. The eval corrections were a prerequisite of that outcome, not a second independent cluster.
   - The overrun came from eval-driven work needing a baseline boundary and a review-before-runs boundary, not from scope growth.
   - Recorded so a later sweep can see whether eval-driven sorties routinely outgrow the soft limit.
4. **flight-debrief Phase 2 Developer brief: the reuse/run-fresh rule worked as written.** The flight never ran a full browser gate, so the debrief ran one: about 40 minutes of wall time at the debrief. A flight that only runs per-leg lanes always pays this at the debrief. That is fine, but worth knowing when sizing a debrief.

## Recommendations
1. **Plan a "claimed actions" sortie** (logged as [sortie 12](../12-claimed-actions/flight.md), status planning). It covers:
   - a preloaded-wording line along the lines of "call the tool; never describe a result you did not get from one", screened at fact 0;
   - the claims-pattern fix for result-style wording;
   - a decision on whether the claimed-action guard is a runtime check or a gated cell.

   It needs one same-prompt re-baseline cycle. Target: `qwen3-4b` `notes-as-told` back to ≥ 19/20 with today's gains held. **Important.**
2. **Plan a "secrets in notes" sortie**: a write-time secret screen on `save_note`, prompt wording, or both. `qwen3-4b` and `lfm3` each stored a shared secret in 2 of 20 runs on the shipped product. It is a separate design call from recommendation 1, but could share its baseline cycle if the operator wants one. **Important.**
3. **Make DD14 and the n=5 sentinel standard for eval-driven flights.**
   - Review and commit product code before any quota-heavy run set.
   - Run an n=5 sentinel on the hold cells most exposed to the change before the n=20 sets.
   - Add a leg 2 exit check: "every cell already failing its own bar gets its reading decided now".
   - Record these in `.flightops/agent-crews/leg-execution.md` or the eval section of `CLAUDE.md` at the next planning conversation. **Important.**
4. **Close the reach gap for connector-bound agents**: embedding pre-load or a priority fill for over-budget agents (already a charter follow-up), and say so in `agents.md` meanwhile. **Important.**
5. **Run the Ollama wire sortie** once an n=20 A-vs-B on `qwen3:4b-thinking` is in. Also consider Anthropic prompt caching to offset the larger first call on plan quota. **Minor.** Logged as [sortie 13](../13-ollama-wire-fidelity/flight.md) (Ollama wire, gated on the A-vs-B) and [sortie 14](../14-anthropic-prompt-caching/flight.md) (prompt caching), both status planning.

## Operator Interview
- **DD14 cadence.** "Worked well, keep it." Review and commit before quota-heavy runs should be standard for eval-driven flights.
- **Priority of follow-ups.** All four matter:
  - claimed actions and wording;
  - secrets in notes;
  - the Ollama wire;
  - embedding pre-load.

## Action Items
- [x] Squawk 0335 (logged, open): test-order dependence between `tests/test_prompt_layers.py` and `tests/test_evals_tokens.py` (`no active connection`; pre-existing at `HEAD`).
- [x] Squawk 0336 (logged, open): `evals/README.md` platform-prompt-text list omits `the_one/db/_secrets.py`.
- [x] Sortie 12 logged (planning): claimed actions (wording, claims patterns, guard), recommendation 1.
- [ ] Sortie candidate: secrets in notes, recommendation 2.
- [x] Sortie 13 logged (planning): Ollama wire, gated on the `qwen3:4b-thinking` n=20 A-vs-B. Sortie 14 logged (planning): Anthropic prompt caching.
- [ ] Follow-up: embedding pre-load or priority fill for over-budget agents. In the meantime, document the connector-bound 16k case in `agents.md`.
- [ ] Before the next release: run leg 4's three HAT checks once by hand (the prompt wording in Settings › Prompts, first-turn tool use on a `qwen3:4b-instruct` agent, and `THE_ONE_TOOL_EXPOSURE_FRACTION=0` back on discovery).
- [ ] Methodology: write the eval-flight standards from recommendation 3 into the crew file or `CLAUDE.md`.

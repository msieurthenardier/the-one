# Flight Debrief: Extended thinking follows the model

**Date**: 2026-11-15
**Flight**: [Extended thinking follows the model](flight.md)
**Status**: landed
**Duration**: 2026-11-14 (charter, design, leg 1, reviews, commit) - 2026-11-15 (HAT, debrief, fix pass)
**Legs Completed**: 2 of 2 (the HAT leg with two of eight steps not walked)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
- A Claude provider no longer breaks models that cannot think. `AnthropicProvider` sends the adaptive-thinking option only to models from version 4.6 on (`supports_adaptive_thinking`), for all three Claude provider types.
- A "thinking is not supported" 400 strips thinking from the request once, and the model id is remembered for the life of the process.
- A new Claude provider starts with "Extended thinking" on (the create form and the create route). Stored providers are unchanged.
- The switch's help text states the rule. The eval record reports what is actually sent.
- Squawk 0361's defect is confirmed fixed with a real model: at the HAT, Haiku 4.5 answered with the switch on, and the log held no 400.

### Charter Criteria

| Criterion | Result | Note |
|---|---|---|
| With the switch on, a model that cannot think completes a turn, and its request carries no thinking option | **Met** | HAT step 3 with a real model (Haiku 4.5), plus unit tests on the built request for all three provider classes |
| With the switch on, a model that can think still gets thinking, shown in the work group | **Met by tests only** | HAT steps 4 and 5 were not walked: the operator's Claude plan refused every model but Haiku with a bare 429. No real thinking turn has been seen in this flight or in sortie 16 |
| A new Claude provider has the switch on untouched; off still turns thinking off for every model | **Met** | The form and route were walked at the HAT (steps 1, 2, 6); "off for every model" rests on unit tests and the Haiku walk |
| The label and help text say it applies only to models that support thinking | **Met** | HAT step 1; pinned in `test_flow_provider_editor.py` |

Checkpoints: all four met, with one correction. "Full local gate green" was recorded on 2026-11-14 from the implementing Developer's unit report and the Flight Director's browser gate. The debrief found the unit tier red on the committed code (below), so that checkpoint was not true until the fix pass.

## What Went Well
- **The model rule did the whole job at the HAT.** Haiku never drew the 400; the retry was not needed. The design's first line of defence is the one that matters in practice.
- **The Architect's flight review changed the design for the better before any code**: the in-place strip (a rebuild would have re-added keys earlier strips removed), the process-wide memory (a provider instance is rebuilt per connector message, per web join and per routine run), the narrow, ordered match, and "the stamp lives in the route only" (the evals create providers through the repository). All four were implemented as specified.
- **One decision point.** `thinking_active` already gated both the request key and the replay of stored thinking blocks, so the core change is one added condition.
- **The adapted HAT step 6** (switch off, retry the refused model) separated "the plan refuses this model" from "the new default broke it" with one request.
- **Sortie as the vehicle** fit: one outcome, one cluster of decisions settled in one conversation, one autonomous leg plus a HAT.

## What Could Be Improved

### Process
- **A red commit passed review and was marked ready.** `tests/test_nav_helper.py::test_no_raw_route_hashes_in_browser_tests` fails on `fbb6198a`: the new browser test `test_create_without_touching_thinking_saves_enabled` waited on a raw route-hash regex. The implementing Developer rewrote that test after its unit run and re-ran only the `providers` lane. The Reviewer ran four unit files and the static JS/CSS guards, not the navigation guard. The browser gate cannot see a unit-tier guard. The Flight Director accepted the reported unit count without a run on the final tree. Found by the debrief Developer's fresh unit run; fixed in a fix pass at the debrief (see Action Items).
- **The HAT prerequisite was a yes, not a request.** At design the operator confirmed having one model that thinks and one that does not. At the HAT the plan answered only for Haiku. This is the miss sortie 16's debrief recorded (its recommendation 4 and methodology observation 4), repeated one flight later with the lesson written into this flight's own Open Questions. Asking again is still only a yes; one real request per model at design is the check.
- **The model list could not have warned anyone.** For a plan provider whose live listing fails, the editor shows the built-in catalog with no sign that it is a fallback, so "all the Claude models" appeared.
- **Falsification was partial and the leg's wording allowed it.** The leg asked for falsification of criteria 3, 4, 7 and 10 only. The id table, the create-stamp negatives, the temperature-case negative and the browser tests were not falsified.
- **The Reviewer agent re-sent its delivered report four times** as leftover wait timers fired, until the Flight Director stopped it. The crew prompt's "no sleep timers" rule is in the Developer prompt but not the Reviewer's.

### Technical
- **A thinking-only assistant message may be sent empty on the first attempt** (not the strip). With thinking inactive, `_to_api_message` projects a stored message that has thinking blocks but no text and no tool calls to `{"role": "assistant", "content": ""}`. This is a pre-existing shape, but this flight makes it more reachable: a chat that holds such a message, whose agent then runs on a model that cannot think, now takes the thinking-off build without any retry. Not reproduced; the API's rejection of an empty assistant message is the debrief Developer's recollection, not a verified fact. The strip drops such a message; the first-attempt build does not.
- **The strip's error match is loose and still unproven against the real API.** It fires on "thinking" together with "not supported". A reworded error would stop matching (the 400 surfaces as before); a different 400 containing both phrases would mark the model as unable to think until restart. The HAT never produced the 400, so the text is still pinned from the one line in squawk 0361.
- **The remembered set is keyed by model id only.** One provider's or account's refusal turns thinking off for that model id on every provider in the process, until restart. Degradation is graceful (a reply without thinking, one warning), but the scope is wider than "this provider".
- **The three Claude types are repeated in six places** (`api.py` `_CLAUDE_PROVIDER_TYPES`, `providers-section.js`, `library-pane.js`, `db/_provider_types.py`, `models.py`, `llm/registry.py`). A fourth Claude type would silently miss the create-time default.
- **The unit tier is near its 300 s standing target**: 283 s on this run (10221 tests, up 83 from sortie 16's 10138). Sortie 16's debrief warned the next unit-adding flight would approach it.

### Documentation
- `the_one/agents.md` documents the rule, the set and the retry, but not the match's wording sensitivity or the set's cross-provider scope.
- Nothing tells an operator that a plan provider's model list can be the built-in catalog rather than what the plan allows.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| The strip drops an assistant message whose content becomes empty, where the flight said only "filter the blocks" | Filtering leaves an empty content list, which the API would reject | Yes, and apply the same rule to the first-attempt build (follow-up) |
| Two existing tests (`test_non_thinking_model_error_reraised_unchanged` and its stream twin) changed meaning: they now assert a re-raise after one retry | They pinned the behaviour this flight replaces | Yes: rewrite in place, as done |
| HAT steps 4 and 5 not walked; step 6 adapted to "switch off, retry the refused model" | The operator's plan refused every model but Haiku | The adaptation, yes: when a model is refused, vary the one setting under test to separate causes |
| Leg 1 tiered low-risk, no per-leg design review | The Architect had reviewed the same decisions the same day | Supported by the outcome (Architect's debrief view), with the falsification gap noted. The red commit was a late test edit, which a design review would not have caught |
| A fix pass at the debrief, after the flight was marked landed and the PR ready | The unit tier was red on the committed code | No. The gate belongs before landing: run the unit tier on the final tree |
| The full browser gate ran while the HAT instance and a reviewer's lane were on the host | To use the HAT's waiting time | No budget reading was taken from it; fine as a pass/fail gate only |

## Key Learnings
- **A reported count is not a gate.** Any edit after a gate run, including a test-only edit, voids that run. The landing check is a unit-tier run on the tree that is committed.
- **A browser-test edit needs the unit tier's guards**, not only its lane: `test_nav_helper.py` (routes and retired selectors) lives in the unit tier.
- **For anything only the operator has, make one real request at design.** A model, a server, a token: a yes is a belief. Two flights in a row lost HAT steps to it.
- **A capability rule with a learned exception** (a rule by id, a remembered negative set, one bounded retry) worked and matches the existing temperature and cache strips. It is Claude-specific: sortie 13 should not reuse `supports_adaptive_thinking` or the set for Ollama, where capability is a local fact better probed when the provider is built.
- **Create-time defaults belong in the route**, never in the stored model, when another path (here the evals) creates the same rows.
- **A reasoning-only turn needs a defined replay rule.** This flight met it twice (the strip, the first-attempt build). Sortie 13 will meet it again for Ollama.

### Test metrics
- **Unit tier** (debrief Developer's run on `fbb6198a`, netns): 1 failed, 10220 passed, 15 skipped, 283.0 s. The failure is this flight's own (above). The implementing Developer's earlier report was 10221 passed. Prior: sortie 16 debrief 10137-10138 passed, 275-296 s; sortie 14 9372 passed, 258.7 s. The count rose by 83 (60 in the new `tests/test_anthropic_thinking_model.py`, the rest in provider API, eval and existing files).
- **Browser gate** (Flight Director's run on `fbb6198a`, WebKit required, netns, **host not quiet**): `PARALLEL_RESULT rc=0 total=2349s lanes=20 failed=-`. Prior: sortie 16 2180 s (20 lanes, load 0.95); sortie 14 1989 s (17 lanes). The +169 s is load: a HAT instance and a second `providers` lane were running.
- Lanes that moved most against sortie 16: `chats` 431 vs 384 s (over its 420 s budget), `providers` 382 vs 331 s, `contracts-chat` 121 vs 93 s, `chats-transcript` 472 vs 417 s, `contracts-controls` 460 vs 405 s. This flight touched only `providers` (a few tests), which cannot explain +51 s. Nothing is attributed to the change, and no lane is re-budgeted from a loaded run (quiet-host rule).
- Skips: 15 under netns, the expected count. No flake was observed.

## Methodology Observations
All on mission-control 1.2.3.

1. **Sortie skill, step 4 → flight skill "Pre-Flight Rigor" ("Prerequisites MUST be verified, not assumed").** The Flight Director asked the operator whether two specific models were available, got a yes, and ticked the prerequisite `[x]` with "re-verified at the start of the HAT leg". The skill's wording was satisfied by a question. Expected: for a prerequisite that only an external account can satisfy, the skill asks for evidence of one real use (a request, a response) before the box is ticked. Cost: two HAT steps unwalked, one charter criterion met by tests only, and sortie 16's carried step missed a second time. Same observation as sortie 16's debrief, observation 4.
2. **Agentic-workflow skill, Phase 2b/2d (leg landing and flight review).** The Developer's `[LAND:leg]` report carried gate counts; the workflow has no step where the Flight Director, or the Reviewer, runs the project's full unit gate on the final tree before the commit. The Reviewer prompt asks whether specific guards "were run and pass", and it ran a subset. Expected: one named, complete gate run on the tree being committed, by someone other than the implementer, or a rule that any edit after the Developer's gate run requires re-running it. Cost: a red commit pushed, a PR marked ready and then returned to draft, and a fix pass during the debrief.
3. **Agentic-workflow skill, Phase 3 step 7 ("the PR is ready for review") against flight-debrief Phase 2 (the Developer runs the full suite).** The first complete suite run on the landed code happens in the debrief, after the PR is already marked ready. Expected: the suite run that the debrief asks for happens before the ready mark, or the ready mark waits for the debrief. Cost: as in 2.
4. **Agentic-workflow skill, Phase 2a risk tiering.** The tiering worked as written and saved a review cycle; recorded as a positive data point. The leg's falsification list was the Flight Director's own and was narrow; nothing in the leg-design guidance says which new tests must be falsified.
5. **Flight-debrief skill, Phase 2 Developer interview ("run the full test suite once").** The project crew file overrides this with "reuse the flight's gate". The Flight Director let the Developer run the unit tier anyway, and that run found the failure. Had the crew file been followed to the letter, the red tier would have reached `main`. Recorded for the sweep: reuse-the-gate is only safe when the gate was complete and on the final tree.
6. **Crew spawn behaviour.** A background Reviewer agent re-delivered its final report four times as its own leftover timers fired. Expected: one hand-back. Cost: four interruptions and a manual stop. Which component owns this (the crew prompt or the harness) is not clear from one flight.

## Recommendations
1. **Gate on the committed tree.** Before a sortie or flight is marked landed, run `THE_ONE_TEST_NETNS=1 make test-unit` on the final tree (after the last edit of any kind), by someone other than the implementing Developer, and record its line in the flight log. Add to the Developer "Implement" prompt: an edit after your gate run voids it; a `tests/browser/` edit needs the unit tier's guards as well as the lane. **Critical.**
2. **Make external prerequisites a real request at design.** For a model, server or account only the operator has: one request per item, with the response recorded in the flight artifact, before the prerequisite is ticked. Put it in `.flightops/agent-crews/flight-design.md` so the Architect flags a ticked box with no evidence. **Important.**
3. **Fix the first-attempt empty assistant message** (thinking-only stored message, thinking inactive): reproduce against the request builder, then skip such a message the way the strip does. **Important** (reachable by switching a chat's agent from a thinking model to one that cannot think).
4. **Tell the operator when the model list is a fallback.** A marker on the provider-models response and one line in the editor. A design call, so a sortie or a leg, not a squawk. **Important.**
5. **Walk a real thinking turn when a thinking model is reachable** (an API-key provider, or a plan that allows one): sortie 16 step 8C and this flight's steps 4 and 5, and capture the real "not supported" 400 text if one can be produced. Until then criterion 2 is test-only. Consider a scripted walk through the real UI with the mock provider's `thinking` blocks as a partial stand-in. **Important.**
6. **Document the two limits in `the_one/agents.md`**: the match's wording sensitivity and the set's cross-provider scope. **Minor.**
7. **Pin the Claude type set in one place**, or add a guard test that the Python and JS lists agree. **Minor.**
8. **Watch the unit tier's 300 s target**; it is at 283 s. **Minor.**

## Operator Interview
Asked: was the design-time "yes" on the two HAT models from memory of what the plan covers, or had other models worked in this app before?

Answer (operator, 2026-11-15): **other models have worked before.**

What that changes:
- The design-time yes was grounded in experience, not a guess. The prerequisite was true once and stopped being true; the lesson is still "one real request at design", because only a request on the day shows it.
- The refusal at the HAT may not be a fixed limit of the plan. A bare `429 rate_limit_error` is also what a plan returns when a model's usage allowance is spent, and the web search found no documented rule that limits a plan to Haiku. Whether it was a usage limit that day, or a change in how plans treat third-party apps, is not known. So steps 4 and 5 may be walkable on another day with the same provider, with no code change.

## Action Items
- [x] Fix the navigation-guard failure in `test_create_without_touching_thinking_saves_enabled` (commit `26821d77`; the Flight Director's unit-tier run on the final tree: 10221 passed, 15 skipped).
- [x] Return PR #373 to ready on the green unit tier.
- [ ] Squawk [0367](../../squawks/0367-thinking-only-assistant-message-sent-empty.md): the first-attempt empty assistant message (recommendation 3).
- [ ] Squawk [0368](../../squawks/0368-thinking-retry-limits-undocumented.md): document the match and set limits in `agents.md` (recommendation 6).
- [ ] Squawk [0369](../../squawks/0369-claude-provider-type-set-repeated.md): one source and a guard test for the Claude provider-type set (recommendation 7).
- [ ] Squawk [0370](../../squawks/0370-crew-prompts-gate-and-prerequisite-rules.md): crew prompt rules for late edits, browser-test guards, reviewer timers and external prerequisites (recommendations 1 and 2).
- [ ] Needs design (sortie or leg): the model-list fallback marker (recommendation 4).
- [ ] Carried: walk a real thinking turn (recommendation 5), retrying the same plan provider on another day first; sortie 16's step 8C is now carried twice.
- [x] Squawk 0361 closed out with a note linking this sortie's outcome.

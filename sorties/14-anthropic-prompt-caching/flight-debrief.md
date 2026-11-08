# Flight Debrief: Anthropic prompt caching

**Date**: 2026-11-08
**Flight**: [Anthropic prompt caching](flight.md)
**Status**: landed (marked `completed` at this debrief)
**Duration**: 2026-11-07 (charter, design) - 2026-11-08 (legs 1-2, landed)
**Legs Completed**: 2 of 2 (no HAT, by operator choice)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
Every request from the `anthropic`, `anthropic-plan` and `anthropic-plan-token` providers now caches its tool schemas and system prompt, plus the conversation so far within a turn. Two markers do it, both set in `AnthropicProvider._build_kwargs`: an explicit 5-minute marker on the system block and top-level automatic caching.

`TokenUsage.input_tokens` still means the whole prompt. The cache counts ride in two new fields that are stored only when non-zero, so the context overlay, `last_usage` and the eval counts read what they read before.

The provider's three strip-and-retry paths (temperature, a named unexpected kwarg, a cache refusal) now compose in one bounded loop. Under the old nested shape, a `TypeError` retry followed by a `temperature` 400 failed the turn outright. A refused cache marker disables caching for that provider instance instead of failing the request.

The evals gain two tools: `cache-probe`, a live proof through the real factory with exit codes 0-4, and `compare --models`, which compares a subset of a baseline's models.

Commits: `178a931b` (leg 1) and `e4ca0616` (leg 2, landed). PR #361.

### Charter Criteria (sortie)
| # | Criterion | Result | Note |
|---|---|---|---|
| 1 | Cache reads on later calls once the prompt reaches the model's minimum *(amended at design)* | **Met** | Live probe on haiku 4.5: call 1 wrote 5784, call 2 read 5784. That is call 1's whole prompt including the user message, so the tail breakpoint is proved and not only the system marker. |
| 2 | Telemetry neither double-counts nor drops cache tokens | **Met** | Live: `input_tokens` was 5787 and 5885, where the SDK's own field read 3 and 5. Offline: the codec round trip, and the usage frame and `last_usage` equal with and without cache counts. |
| 3 | Covers all three Claude provider types | **Met** | `anthropic-plan-token` was proved live. `anthropic` and `anthropic-plan` share `_build_kwargs`, and unit tests pin identical kwargs. Those two were not run live. |
| 4 | No behaviour change: s11 compare shows no haiku gate failure | **Met** | `compare --models haiku`: exit 0, all 17 haiku cells PASS, all 10 size gates at today's totals. It ran without `--same-prompt` (see Deviations). |

The outcome sentence's "uses less input quota" is **not verified**: only tokens served from cache were measured. How a Claude plan counts cache reads against its usage limit is server-side and cannot be seen from the app. The operator chose to record it as unverified. On the API, cache reads are priced at about 0.1x input.

### Checkpoints
- [x] Leg 1 reviewed and committed before any quota-spending run (sortie 11 DD14, kept).
- [x] Live probe exit 0.
- [x] Haiku compare with no gate failure.

## What Went Well
- **The planning premise probe.** Two scratch calls on the plan token, made before any design decision was locked, answered the one real unknown: does the OAuth endpoint accept `cache_control`? It also exposed the telemetry hazard, `input_tokens=3` for an 8954-token prompt, which became DD2.
- **The design reviews caught three defects that would each have cost a quota run.** The operator says these reviews were worth it and should be kept at this depth for sorties that touch eval apparatus. Two Architect cycles and one leg design review found:
  - the haiku-only compare would be refused by the models fingerprint, which led to DD7;
  - recording cache counts would edit a frozen scoring file, which led to DD3;
  - the probe's pass rule could not tell the tail breakpoint from the system marker, which led to DD4's final rule.

  Leg 1 then passed review with no issues.
- **DD2's contract choice.** Keeping `input_tokens` as the whole prompt left every consumer untouched. The overlay, `last_usage`, the eval counts and the WebSocket frames needed no change.
- **DD14 again.** Committing leg 1 before leg 2's quota runs meant the runs measured reviewed code.
- **The probe design.** A pure `decide` function separates "inconclusive" (exit 3) from "run error" (exit 4) and "fail" (exit 1). It ran once, passed, and needed no padding fix.

## What Could Be Improved

### Process
- **A prerequisite went unchecked.** The flight and leg 2 assumed the measured prompt fingerprint would equal `s11-platform`'s. It did not: the baseline was recorded on sortie 11's leg 2 prompt, before leg 3's wording landed. One `measure-prompt` at planning would have caught it. The compare still answered criterion 4, but leg 2's acceptance criteria were met in substance, not as written.
- **The charter criterion was written before checking the model's cache minimum.** Haiku 4.5's 4096-token floor made the original criterion 1 unreachable for the eval agents. It was amended at design, and the amendment was well handled.

### Technical
- **The strip loop.**
  - Its bound is implicit: each strip pops its own key, and only while that key is present. Of its tests, only the TypeError-then-temperature composition was falsified. The "repeat refusal re-raises, does not loop" tests were not, so a broken bound could go unnoticed.
  - The triggers match message text (`"temperature"`, `"cache_control"`). A 400 that merely mentions `cache_control` for another reason would disable caching for the instance's life, with only a WARNING. Low risk; noted.
- **`_cache_disabled`** is the first mutable per-request state on a provider object. That is harmless today, because instances are per agent. It would matter if providers were ever shared across concurrent requests.
- **Interim stream usage frames** are byte estimates and carry no cache counts; only the final usage does. Nothing documents this.
- **The `TokenUsage` contract** ("`input_tokens` is the whole prompt") is documented in `agents.md` and `evals/README.md`, not on the type. A future provider that reports an uncached remainder must sum on the way in, and nothing at the type tells it so.
- **The probe's 4096 + 256 precondition is a literal tied to Haiku 4.5.** A model change (Haiku 5.5's minimum is 512) means that exit 3 no longer means "persona too short".

### Documentation
- `evals/README.md` should say: check that the baseline's prompt fingerprint equals the current one before planning a `--same-prompt` compare.
- `agents.md` should note that interim usage frames carry no cache counts, and that summing `input_tokens` for a cost or quota display over-counts cached tokens.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Charter criterion 1 amended at design ("once the prompt reaches the model's cache minimum") | Haiku 4.5 won't cache under 4096 tokens; the eval agents' first calls are 2.5-3.2k | Yes: check model limits before writing a criterion that depends on them |
| `compare` ran without `--same-prompt` | `s11-platform` predates sortie 11 leg 3's wording (fingerprint `df5f2249…` against `84f8bf2e…`). Tool totals matched the baseline (1540, 1283) and prompt text sat below its max (316 against 354), consistent with that history and with no prompt change here | Yes: verify fingerprint equality at planning |
| A `TypeError` naming `cache_control` takes the full cache strip and sets `_cache_disabled` | Flight Director call at leg design review: one failed round trip per agent, not per call | n/a (design detail) |

## Key Learnings
- **Ask the endpoint, cheaply, before designing around it.** Two scratch calls settled endpoint support and found the telemetry trap.
- **Read every consumer before changing what a usage number means.** Keeping a field's meaning and adding parts beside it is cheaper than changing it.
- **Prompt caching only pays above the model's minimum.** The small eval agents (2.5-3.2k tokens) never cache on haiku 4.5. The benefit shows for agents with larger toolsets, personas or knowledge-base results, and on newer models with lower minimums.
- **A baseline's fingerprint decays when later work lands.** "Compare against the current baseline" quietly becomes a different-prompt compare.

### Test Metrics
All numbers are from fresh runs at the debrief on `e4ca0616`, by the debrief Developer. No full gate ran during the flight (leg 1 ran only the unit tier), so the crew file's "run fresh" rule applied.
- **Unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`):
  - 9372 passed, 15 skipped (the expected count under netns), 0 failed; 258.7 s; start load 0.25.
  - Against the sortie 11 debrief: 9304 passed, 301.7 s on a loaded host, so +68 tests and -43 s. The time difference is host load.
  - Matches the leg 1 gate exactly.
  - The +68 against the flight's "84 new tests" is not reconciled. The likely cause is tests changed or replaced rather than added; not investigated.
  - Under the 300 s standing target.
- **Browser gate** (`--parallel 3`):
  - `PARALLEL_RESULT rc=0 total=1989s lanes=17 failed=-`, no `OVER BUDGET`.
  - Start load 0.97, with the run started straight after the unit tier, so it is borderline quiet and **not used to re-base budgets** (squawk 0259's rule).
  - Against sortie 11's 2096 s: -107 s (-5%). Against sortie 10's 1938 s: +51 s.
  - Sortie 11's `chats` over-budget reading (427 s) is now 394 s, which confirms that one was host load.
  - Slowest lanes: `routing` 553 s, `agents` 515 s, `agent-tabs` 468 s.
  - This flight touched no browser code.
- **Full gate**: about 2248 s (37.5 minutes), under the 43-minute target.

## Methodology Observations
Plugin version for all of these: mission-control 1.2.3.

1. **flight skill Phase 4 (premise audit) has no prompt to check that a planned comparison is reachable against its baseline's recorded state.**
   - What happened: the flight and leg 2 specified `compare --same-prompt` against `s11-platform`. Nobody measured the current prompt's fingerprint during design. The Architect review caught a different reachability defect in the same compare (the models fingerprint), not this one.
   - Expected: the premise audit's "can the apparatus observe" axis to extend to "is the comparison's precondition true today".
   - Cost: a small, documented deviation at leg 2; leg 2's acceptance criteria were met in substance, not as written. No re-run.
2. **sortie skill, charter step: criteria are agreed before any technical constraint is checked.**
   - What happened: the charter's criterion 1 was unreachable for the eval's model, because of Haiku 4.5's 4096-token cache minimum. Flight design found this and amended the criterion with the operator.
   - Expected: either a charter-time sanity check of model or platform limits, or an explicit "criteria may be amended at design" note. The amendment process worked, but it was improvised: the original wording was preserved in the flight log by hand.
   - Cost: one operator question and a hand-written amendment record.
3. **The sortie was the right vehicle.** There was one outcome and one decision cluster: breakpoint placement and how usage counts cached tokens. Two legs, no HAT, within the soft limit.
   - DD7 (`compare --models`) was verification apparatus that the outcome needed, not a second product decision.
   - Leg 1 was large: provider, type, codec, probe, compare filter, docs and 84 tests. It still passed one review clean.
4. **agentic-workflow Phase 2d plus sortie 11 DD14 worked unchanged.** The workflow ran one autonomous leg, then review and commit, then a quota leg run by the Flight Director. No deviation from the skill was needed, because DD14 was carried into the flight design as a checkpoint. This is evidence for observation 1 in sortie 11's debrief: when written into the design, the pattern fits the skill as is.
5. **The leg design review was valuable on a high-risk leg whose flight had already had two Architect cycles.** It caught operational traps the flight-level reviews could not see:
   - `_dispatch`'s fall-through for an unregistered subcommand;
   - `parse_scenario`'s mandatory non-empty `checks`;
   - the exact test file for the usage frame.

   Recorded as support for keeping per-leg design review on high-risk legs even after a thorough flight review.

## Recommendations
1. **Re-baseline the platform eval set on the current prompt.** It is logged as a squawk at the operator's request, though sortie 12 also plans new same-prompt baselines and may absorb it. Until then, every prompt-touching flight hits the same fingerprint mismatch and cannot use `--same-prompt`. **Important.**
2. **Write the `TokenUsage` contract on the type, and document interim frames.**
   - A docstring on `TokenUsage`: `input_tokens` is the whole prompt, the cache fields are a breakdown, and no consumer sums them.
   - A line in `agents.md`: interim stream frames carry no cache counts, and summing `input_tokens` for cost over-counts cached tokens.

   **Important** (it guards the next provider mapping, e.g. OpenAI `cached_tokens` or Ollama in sortie 13).
3. **Falsify the strip loop's repeat-refusal tests**, so that removing the bound actually fails a test. **Minor.**
4. **Add a fingerprint-equality check to the eval workflow docs.** In `evals/README.md`: before planning `--same-prompt`, run `measure-prompt` and compare its fingerprint with the baseline's. **Minor.**
5. **Make the probe's cache minimum a named, model-keyed constant** instead of the literal 4096 + 256, before the eval's haiku preset moves to a newer model. **Minor.**
6. **Future: cache counts for other providers.** OpenAI-compatible endpoints report `prompt_tokens_details.cached_tokens` inside `prompt_tokens`. A mapping-only change could fill `cache_read_tokens` with no type change. An operator-facing "cached" readout (deliberately out of scope, DD3) would make cross-turn reuse within the 5-minute TTL visible. **Minor; idea only.**

## Operator Interview
- **Stale baseline.** Log a squawk to re-baseline.
- **Planning depth.** "Worth it, keep." Two Architect cycles plus a leg design review is the right depth for sorties that touch eval apparatus.
- **Quota claim.** Record it as unverified; only tokens served from cache were measured.

## Action Items
- [x] [Squawk 0337](../../squawks/0337-platform-eval-same-prompt-rebaseline.md) (logged, open): same-prompt re-baseline of the platform eval set (rec 1).
- [x] [Squawk 0338](../../squawks/0338-tokenusage-contract-docs.md) (logged, open): the `TokenUsage` contract docstring and the interim-frames note (rec 2).
- [x] [Squawk 0339](../../squawks/0339-falsify-strip-loop-bound-tests.md) (logged, open): falsify the strip loop's repeat-refusal tests (rec 3).
- [x] [Squawk 0340](../../squawks/0340-evals-readme-fingerprint-check.md) (logged, open): the fingerprint pre-check in `evals/README.md` (rec 4).
- [x] [Squawk 0341](../../squawks/0341-cache-probe-model-keyed-minimum.md) (logged, open): a model-keyed cache minimum for `cache-probe` (rec 5).
- [x] Sortie 14 marked `completed`.
- [ ] Operator: mark PR #361 ready for review when satisfied.

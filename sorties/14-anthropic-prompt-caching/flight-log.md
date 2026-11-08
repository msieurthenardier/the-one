# Flight Log: Anthropic prompt caching

**Flight**: [Anthropic prompt caching](flight.md)

## Summary
Logged on 2026-11-07 from the sortie 11 debrief, recommendation 5, second half, which was split out of the Ollama wire item. The charter was agreed with the operator, and flight design has not started.

---

## Leg Progress

### Flight Director Notes (execution)
- 2026-11-08: `/mission-control:agentic-workflow sortie 14`. Loaded `.flightops/agent-crews/leg-execution.md` (Developer: Sonnet; Reviewer: Haiku, or Sonnet for a security-sensitive diff). Status set to `in-flight`. Two legs.
- **Leg 1 `prompt-caching` tiered HIGH.** It changes a shared interface with consumers (`TokenUsage`, the codec), the control flow of the provider's retry paths, and the eval compare apparatus, so a Developer design review runs before implementation.
- **Leg 1 design review (Sonnet): approve with changes**, no blocker. Applied:
  - `cache-probe` goes in `_dispatch`'s `handlers` and catches `EvalRefusalError`, `PresetError` and `ScenarioError` into `_err`.
  - The scenario TOML's mandatory fields: `id`, `class = "hold"`, `conversations`, and a non-empty `checks` with one inert check. No braces in the filler.
  - The usage-frame test is named: the `test_last_usage_persistence.py` pattern through `_process_and_broadcast`.
  - The probe's precedence and call definition.
  - A TypeError naming `cache_control` takes the full cache strip and sets `_cache_disabled` (FD call: it matches DD5's one-round-trip intent).
  - The loop bound is reworded; the probe output is redacted; `close` and `shutdown` run in a `finally`; the run directory is kept.
  - A raw `input_tokens` passthrough when the cache counts are zero.
  - The margin is fixed at 32.

  All are clarifications, so there was no second cycle. Leg status: `ready`.
- **Leg 1 implementation (Sonnet Developer):** `[LAND:leg]`. Unit tier 9372 passed, 15 skipped (netns). 84 new tests; three key tests were falsified.
- **Flight review (Sonnet Reviewer).** The security tier applied because the probe handles the plan token through eval startup. Result: `[HANDOFF:confirmed]`, no issues. It ran 234 touched and new tests plus 136 provider/OAuth/plan tests; lint clean; the frozen files are untouched.
- **Leg 1 committed** before any quota run, per sortie 11 DD14; leg status `completed`. Leg 2 follows.
- **Developer notes for leg 2:**
  - The probe persona is about 2.8k tokens, so call 1 should total about 5.5k. If the probe exits 3, the persona needs more padding.
  - `decide` takes call 1's total as `max(input_tokens, read + write)`, so a broken DD2 mapping fails (1) instead of reading as inconclusive.

### Leg 1: prompt-caching
Status: `landed` (not committed). No live call was made: `cache-probe` was run only with `--help`, no plan token was read, and port 8484 was not touched.

**What changed**
- `the_one/llm/anthropic_provider.py`:
  - the `_CACHE_CONTROL` constant, the marked `system` list and the top-level `cache_control` (DD1);
  - `_usage_from_sdk` and `_cache_int`, used at both mapping sites (DD2);
  - the bounded strip loop in `complete` and `stream`, with `_strip_for_bad_request`, `_strip_for_type_error`, `_strip_cache_markers` and `_cache_disabled` (DD5). The strip fires only while its key is in `kwargs`, so no separate stripped-set is kept.
- `the_one/llm/base.py` has the two `TokenUsage` fields; `the_one/db/codec.py` emits them only when non-zero and decodes with defaults.
- `evals/baseline.py` has `select_models`, `baseline_models_fingerprint`, and a `models=` parameter on `check_comparable` and `compare`, plus a `Comparison.models` header line. `evals/__main__.py` has `compare --models` and the `cache-probe` subcommand, registered in `handlers`.
- `evals/cache_probe.py` (pure `decide`, `calls_from_trace`, `run_probe`) and `evals/cache_probe_data/cache-probe.toml` (10 KB persona of 40 guidelines, plus a padded user message).
- Docs: `the_one/agents.md` block, `CLAUDE.md` paragraph and Prompt evals mention, `evals/README.md` table rows and the `input_tokens` note.

**Tests** (new: 84): `tests/test_anthropic_prompt_caching.py` (30), `tests/test_evals_cache_probe.py` (26), `tests/test_evals_compare_models.py` (9), plus 2 in `tests/test_db_codec.py`, 1 in `tests/test_last_usage_persistence.py` (usage frame and `last_usage` equal with and without cache counts), and `cache-probe` added to `test_run_help_and_subcommands_listed`.

**Gates:** `THE_ONE_TEST_NETNS=1 make test-unit`: 9372 passed, 15 skipped (the documented netns count). `tests/test_evals_freeze.py` green with unchanged digests; `git diff --stat baf9f8c3` over `core.py`, the four SCORING_DIGESTS files and `evals/scenarios/` is empty. `ruff check` and `ruff format --check` clean. The existing `test_streaming.py`, codec byte-identity and plan-provider tests pass unmodified.

**Falsification:** yes for the DD2 sum (3 tests fail without it), the TypeError(`cache_control`) then temperature composition (the complete and stream tests fail with the temperature strip gated off after a cache strip), and `_cache_disabled` persistence (6 tests fail without the flag). Each fix was removed and put back by editing. The other new tests were not falsified.

**Notes**
- One small judgment in `decide`: call 1's "total prompt" for the 4352 precondition is `max(input_tokens, read + write)`, equal to `input_tokens` when the mapping is correct. Without it a collapsed mapping would read as a tiny prompt and show up as 3 (inconclusive) instead of a 1 (fail).
- The scenario persona is 10 KB (about 2.8k tokens), shorter than the leg's 18 KB guideline. With haiku's roughly 2.5k to 3.1k first-call tokens that should still clear 4352 by about 1k; leg 2's first run shows the real figure, and exit 3 would mean padding it further.
- `compare --models ""` is refused as an empty selection (CLI exit 2).

---

## Decisions

### 2026-11-07: flight design choices (operator)
- **Breakpoints (DD1):** one explicit marker on the system prompt plus top-level automatic caching. Recommended option, chosen.
- **Proof of criterion 1 (DD4):** amend the criterion to "once the prompt reaches the model's cache minimum" and prove it with a committed live probe (`make eval ARGS="cache-probe"`). Recommended option, chosen.
- **Telemetry (DD2, DD3):** store the cache counts and change no UI; `input_tokens` keeps meaning the whole prompt. Recommended option, chosen.
- **HAT:** none. Nothing changes visibly in the UI.

### 2026-11-07: charter criterion 1 amended
Original wording: "On the second and later model calls of a turn, an Anthropic or Claude-plan agent's usage reports cache reads covering the tool schemas and system prompt."

Claude Haiku 4.5, the eval's haiku, has a 4096-token minimum cacheable prefix. The eval agents' first calls are 2536 to 3161 tokens, so for them the criterion was unreachable as written. With the operator, it was amended to apply once the prompt reaches the model's cache minimum. The original framing is kept here.

---

## Deviations

---

## Anomalies

---

## Session Notes

### 2026-11-07 — charter
Qualification against the four sortie criteria:
- One outcome: a cached prompt prefix on Anthropic and plan agents.
- One cluster of decisions: where the cache breakpoints go, and how usage and telemetry count cached tokens.
- Fits in one flight.
- No new subsystem.

The operator agreed the charter as drafted.

### 2026-11-07 — flight design
- Branch `sortie/14-anthropic-prompt-caching` was created from `main` at `baf9f8c3`.
- **Code interrogation.**
  - All three Claude provider types share `AnthropicProvider._build_kwargs`; the plan subclasses never override it.
  - `the_one/agent/core.py` needs no change.
  - The system prompt is built once per agent, and its date line carries no clock time.
  - Every consumer reads `TokenUsage.input_tokens` as the whole prompt size: the overlay's `context_tokens`, `last_usage`, and the eval `first_call_input_tokens` and `usage_totals`.
- **Premise probe** (scratch script, not committed; plan token read from file and never printed; `claude-haiku-4-5-20251001`; an ~8.9k-token system block with an explicit marker plus top-level `cache_control`; one tool; two calls):
  - call 0: `input=3 cache_write=8951 cache_read=0`
  - call 1: `input=3 cache_write=323 cache_read=8628`

  The OAuth endpoint accepts both forms. `input_tokens` alone collapses to the uncached remainder, which is the telemetry hazard DD2 addresses.
- **Qualification re-check.** One decision cluster: breakpoint placement and how usage counts cached tokens. The tail caching is the same breakpoint decision in the same function. Two legs, no HAT, within the soft limit.
- **Architect review, cycle 1:** approve with changes.
  - *High.* The haiku-only compare would be refused by the models fingerprint, and `compare` also needs `--same-prompt`. Recording cache counts in `evals/outcomes.py` would break `tests/test_evals_freeze.py`.
  - *Medium.* DD2 misnamed the size gates. DD4's threshold was not computable and proved only the system marker. The TypeError and temperature retries do not compose.
  - *Low.* Five smaller items.
  - The operator chose a `compare --models` filter (DD7) and to leave `outcomes.py` alone (DD3).
  - The spec was revised for every finding: DD4 gets a pass/fail/inconclusive probe, DD5 a composed strip-and-retry with a fallback on a 400 naming `cache_control`, and DD1, DD2 and DD6 corrections. A second review was requested.
- **Architect review, cycle 2:** approve with changes. Every first-cycle finding was resolved except DD4's tail proof. Findings:
  - DD4's rule still passed with only the system marker working.
  - DD7 needed a run-side filter.
  - DD4 lacked error exit codes.
  - The DD5 strip rules needed tightening, plus a per-instance refusal flag.
  - The probe data directory shared the module's name.
  - The charter's minimum wording was wrong for some models, and DD1's slot count was ambiguous.

  All were applied directly, as precise rule and wording changes with no new decision. That reached the two-cycle limit, so there was no third review. Status set to `ready`.
- **Open, unverified:** the outcome says "less input quota". The probe measures tokens, not plan quota. How Anthropic counts cache reads against a plan's usage limit is server-side and not observable here, so the debrief should state it as tokens.

# Leg: prompt-caching

**Status**: completed
**Flight**: [Anthropic prompt caching](../flight.md)

## Objective
Add Anthropic prompt caching to `AnthropicProvider._build_kwargs`: a system marker plus top-level automatic caching. Make the provider's three strip-and-retry paths compose and degrade gracefully on a refusal. Carry the cache read and write counts through `TokenUsage` and the codec without changing what `input_tokens` means. Add the `cache-probe` eval tool and `compare --models`. Unit tests and docs come with it. Nothing is run against a live model in this leg.

## Context
- The design is the flight's **DD1, DD2, DD3, DD4, DD5, DD6 and DD7**; read `../flight.md` first. Where this leg and the flight disagree, the flight wins, and the disagreement is a defect to report.
- Charter criteria this leg builds toward: 1 and 3 (caching on all three types), 2 (the telemetry contract), and 4 (the compare apparatus). Leg 2 runs the live proof.
- **Frozen, do not edit:**
  - `the_one/agent/core.py`. If the design turns out to need it, stop with `[BLOCKED:core-touch]`.
  - The `SCORING_DIGESTS` files: `evals/outcomes.py`, `harness.py`, `checks.py` and `judge.py`. `tests/test_evals_freeze.py` must stay green with unchanged digests. If the probe seems to need a change there, stop with `[BLOCKED:eval-freeze]`.
- No platform prompt text, tool description or schema changes. The prompt fingerprint must stay the same.
- **Operator decisions:** no UI change (DD3), no HAT, and leave `outcomes.py` alone (DD3).
- **Sortie 11 DD14 (kept):** this leg is implemented, reviewed and committed before any quota-spending run. The Developer must not run `make eval ARGS="cache-probe"`, `run` or any other command that calls a real model. The probe's live run is leg 2.

## Inputs
- `main` at `baf9f8c3` plus the sortie 14 planning artifacts on branch `sortie/14-anthropic-prompt-caching`.
- `anthropic` SDK 0.96.0 in `.venv` (`uv.lock`).

## Outputs
- `the_one/llm/anthropic_provider.py`:
  - breakpoints (DD1);
  - the usage helper (DD2);
  - the composed strip-and-retry and `_cache_disabled` (DD5).
- `the_one/llm/base.py`: `TokenUsage.cache_read_tokens` and `cache_write_tokens` (DD2).
- `the_one/db/codec.py`: emits the cache keys when non-zero and decodes them with defaults (DD2).
- `evals/cache_probe.py`, `evals/cache_probe_data/<scenario>.toml` and the `cache-probe` subcommand in `evals/__main__.py` (DD4).
- `evals/baseline.py` and `evals/__main__.py`: `compare --models` (DD7).
- Tests (see the acceptance criteria) and docs (`the_one/agents.md`, `CLAUDE.md`, `evals/README.md`).

## Acceptance Criteria

**Provider: DD1 breakpoints**
- [ ] `_build_kwargs` sends `system` as `[{"type": "text", "text": <prompt>, "cache_control": {"type": "ephemeral"}}]` and the top-level `cache_control={"type": "ephemeral"}`.
- [ ] With no system prompt there is no `system` key, and the top-level field is still sent.
- [ ] Both markers come from one module constant, so a test can assert they carry equal values.
- [ ] `AnthropicProvider`, `AnthropicPlanProvider` and `AnthropicPlanTokenProvider` build identical kwargs for the same input.

**Usage: DD2**
- [ ] One private helper maps SDK usage, and both `complete` and `_stream_inner` use it:
  - `TokenUsage.input_tokens = input_tokens + cache_creation_input_tokens + cache_read_input_tokens`;
  - `cache_write_tokens = cache_creation_input_tokens`;
  - `cache_read_tokens = cache_read_input_tokens`.
- [ ] Any cache field that is not an `int` counts as 0: missing, `None`, or a `MagicMock`. `tests/test_streaming.py` stays green unmodified.
- [ ] `TokenUsage` gains `cache_read_tokens: int = 0` and `cache_write_tokens: int = 0` after `output_tokens`. Positional `TokenUsage(a, b)` still works.
- [ ] `db/codec.py` round-trips both fields, and emits neither key when both are 0. The existing codec byte-identity tests pass unmodified.
- [ ] A unit test in `tests/test_last_usage_persistence.py` (or a new neighbour file) shows that a `TokenUsage` carrying cache counts produces the same `last_usage` and `usage` frame as today. It follows that file's existing pattern:
  - a `StubAgent` yields `Message.assistant(usage=TokenUsage(..., cache_read_tokens=N, cache_write_tokens=M))`;
  - `_send_to_session` is mocked as an `AsyncMock`;
  - it is driven through `_process_and_broadcast`.

  It asserts that the `usage` event dict has exactly `type`, `input_tokens`, `output_tokens`, `context_tokens` and `max_context_tokens`. It compares the frame and `last_usage` from a run with cache fields against a run with them zeroed, and they must be equal. `app.py` is not edited.
- [ ] When both SDK cache counts are 0 or not ints, `_usage_from_sdk` returns the SDK's raw `input_tokens` object unchanged. A `MagicMock` usage therefore maps exactly as today.

**Retries: DD5**
- [ ] `complete` and `stream` run a bounded attempt loop in which each strip fires at most once, and only while its key is still in kwargs:
  - (a) a `BadRequestError` mentioning `temperature` strips `temperature`;
  - (b) a `TypeError` "unexpected keyword argument '<name>'" strips `<name>` when it is a key in kwargs, today's squawk-0009 behaviour. **When `<name>` is `cache_control`, it takes path (c) instead:** a full cache strip that sets `_cache_disabled`. That way an old SDK pays one failed attempt per provider instance, not one per call;
  - (c) a `BadRequestError` mentioning `cache_control` strips the top-level key, turns `system` back into the bare string from `system[0]["text"]` (leaving `system` alone when none was sent), and sets `self._cache_disabled = True`.

  After a strip, the whole attempt re-runs.
- [ ] Once `_cache_disabled` is set, later `_build_kwargs` calls on that instance add no markers.
- [ ] A final `BadRequestError` still goes through `_name_offending_tool` (the `tools.N` mapping), as today.
- [ ] `stream` never retries after it has yielded a chunk.
- [ ] Each strip logs one WARNING on the `the_one.llm.anthropic_provider` logger. The temperature strip keeps today's behaviour, with no new warning required. The cache strip's message contains `cache_control`.
- [ ] Tests cover:
  - each strip on its own, for `complete` and `stream`;
  - TypeError(`cache_control`) followed by a 400 on `temperature`, which ends in success;
  - a repeat 400 naming an already-stripped key, which re-raises (through the `tools.N` mapping) instead of looping;
  - `_cache_disabled` persisting across calls;
  - no retry after a yielded chunk;
  - the plan provider wrappers still translating their errors (existing tests stay green).

**Probe: DD4**
- [ ] `make eval ARGS="cache-probe --help"` works. The subcommand follows DD4's setup sequence through `evals.env.startup` (and therefore `check_pinned_env`), `Harness`, `run_once` and `shutdown`, with `--plan-token-file`, as `run` does, and a run directory under `evals/runs/cache-probe-<UTC time>`.
- [ ] The scenario TOML lives in `evals/cache_probe_data/`:
  - a persona padded past 4096 tokens with filler (system prompt plus tools);
  - one turn asking for the current time, its user message padded with a few hundred tokens of filler;
  - no file under `evals/scenarios/`.
- [ ] For each model call the probe prints `input_tokens`, `cache_read_tokens` and `cache_write_tokens`. It also prints `exposure`, `effective["thinking"]`, and whether a cache strip fired, read from captured WARNINGs on `the_one.llm.anthropic_provider` that contain `cache_control`.
- [ ] It exits with DD4's codes (0 pass, 1 fail, 2 refused via `_err`, 3 inconclusive, 4 run error) using exactly DD4's rules, with a fixed margin of 32 (no flag) and a 4096 + 256 precondition.
  - **Precedence:** run error (4), then the inconclusive preconditions (3), then the fail rules (1), then pass (0). A strip that fired is a fail (1) only when the preconditions hold; otherwise the result is 3.
  - "Calls" are the assistant messages with a non-`None` `usage` in `attempt.trace.turns[0].messages`, in order. An assistant message with `usage is None` is skipped. The per-call rules apply to calls 1 and 2, and the sum invariant applies to every call.
  - `tool_called` is true when any assistant message in that turn has `tool_calls`.
- [ ] **Wiring:**
  - `cache-probe` is registered in `_dispatch`'s `handlers` dict. `run` is the fall-through at the bottom of `_dispatch`, and an unregistered subparser would fall into it.
  - The handler catches exactly `EvalRefusalError`, `PresetError` and `ScenarioError` and returns `_err(str(exc))`, mirroring `_cmd_measure`.
  - `tests/test_evals_cli.py::test_run_help_and_subcommands_listed`'s name list gains `cache-probe`.
- [ ] Everything the probe prints from an exception or a model failure goes through `env.redactor` first.
- [ ] The probe calls `harness.close()` and `env.shutdown(env)` in a `finally`. Unlike `measure_prompt`, it keeps its run directory, which is gitignored.
- [ ] The pass/fail/inconclusive/run-error decision is a pure function over a list of per-call usage records plus flags. `tests/test_evals_cache_probe.py` tests it offline on hand-built inputs:
  - one pass;
  - each fail rule;
  - each inconclusive precondition;
  - run error;
  - a strip that fired, which fails.

  Argument parsing and the refusal path are tested too. Nothing calls a network.

**Compare filter: DD7**
- [ ] `compare --models a,b`:
  - recomputes the baseline's models digest from `base["models"]` restricted to the selection, via `fingerprint.models_fingerprint`;
  - filters `runset.records` to the selection before any fingerprint, aggregate, exposure or mismatch step;
  - compares only the selected models' cells;
  - still runs the `size:*` gates;
  - states the selection in the rendered header.
- [ ] Refusals (`BaselineError`, plain message): a selected name not in the baseline; a selected model with no records in the run.
- [ ] Without `--models`, the behaviour and the stored-digest check are unchanged, and existing compare tests pass unmodified.
- [ ] Tests:
  - the recomputed full-set digest equals the stored `fingerprints.models` for `s11-platform.json`;
  - a haiku-only recomputation equals a haiku-only `RunSet.models_fingerprint()` built from records carrying the baseline's haiku `effective`/`model_info`;
  - unselected cells are absent;
  - both refusals;
  - a superset run is filtered quietly.

**Gates and docs**
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes. The skip count is as documented (15 under netns, or re-read with `-rs`), and `tests/test_evals_freeze.py` passes with unchanged digests.
- [ ] `ruff check` and `ruff format --check` are clean on `the_one/ tests/ scripts/ evals/`.
- [ ] Docs updated:
  - `the_one/agents.md` gets an "Anthropic prompt caching (sortie 14)" block covering DD1's breakpoints and TTL ordering rule, DD2's `input_tokens` contract and new fields, DD5's strip ladder and `_cache_disabled`, DD6's invalidating events, and the note that a `stream` signature's `temperature` default is part of the eval models fingerprint.
  - `CLAUDE.md` gets one paragraph under the LLM layer pointing at that block, and the Prompt evals paragraph mentions `cache-probe` and `compare --models`.
  - `evals/README.md` documents both subcommands, the probe's exit codes, and that provider `input_tokens` is the whole prompt.

## Verification Steps
- Provider, usage and retry tests:

  ```
  PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py tests/test_anthropic_oauth.py tests/test_streaming.py tests/test_db_codec.py -x --timeout 60
  ```
- Eval tests:

  ```
  PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_evals_cache_probe.py tests/test_evals_baseline.py tests/test_evals_baseline_file.py tests/test_evals_cli.py tests/test_evals_freeze.py tests/test_evals_fingerprint.py -x --timeout 120
  ```
- The usage-frame test: whichever file holds it (`tests/test_last_usage_persistence.py` or `tests/test_last_usage_round_trip.py` neighbour).
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `.venv/bin/ruff check the_one/ tests/ scripts/ evals/ && .venv/bin/ruff format --check the_one/ tests/ scripts/ evals/`.
- `.venv/bin/python -m evals cache-probe --help` (no live run).
- `git diff --stat baf9f8c3 -- the_one/agent/core.py evals/outcomes.py evals/harness.py evals/checks.py evals/judge.py evals/scenarios/` is empty.

## Implementation Guidance

1. **`base.py`**: add the two `TokenUsage` fields with defaults, after `output_tokens`.
2. **`anthropic_provider.py`**:
   - Add a module constant `_CACHE_CONTROL = {"type": "ephemeral"}`, copied per request.
   - Initialise `self._cache_disabled = False` in `__init__`.
   - In `_build_kwargs`, when not disabled, build the marked system list (only when `system_prompt` is non-empty) and set `kwargs["cache_control"]`.
   - Add `_usage_from_sdk(u) -> TokenUsage | None` with int-only coercion, and use it at both mapping sites.
   - Restructure `complete` into a loop:
     ```
     stripped = set()
     while True:
         try:
             create
             break
         except BadRequestError:
             decide strip (temperature or cache_control) if not yet stripped and the key is present
             else map tools.N and raise
         except TypeError:
             named kwarg present and not stripped -> strip
             else raise
     ```
     Keep the squawk-0009 warning text.
   - Mirror the loop in `stream` around `_stream_inner`, with the `yielded_any` gate, so no retry happens after a yield.
   - The cache strip is a helper, `_strip_cache_markers(kwargs)`.
3. **`codec.py`**: in `_usage_to_dict`, add each cache key only when it is non-zero; on decode, `.get(..., 0)`.
4. **`evals/baseline.py`**:
   - Add a `models: list[str] | None` parameter to `check_comparable` and `compare`, or a helper that returns a filtered `RunSet` plus a restricted baseline view.
   - Recompute the restricted digest with `fingerprint.models_fingerprint({m: base["models"][m]["preset"]}, {m: ...["effective"]}, {m: ...["model_info"]})` over the selection.
   - Add the selection to the comparison header in `render_comparison`.
   - Without a selection, use the stored digest, as today.
5. **`evals/__main__.py`**:
   - Add the `--models` option to `compare`, comma-separated, with names validated against the baseline.
   - Add the `cache-probe` subparser (`--plan-token-file`, `--run-dir` optional) and its handler.
   - Startup refusals go through `_err`. Check which exception types `evals.env.startup` and `models.select_presets` raise, and catch exactly those.
6. **`evals/cache_probe.py`**:
   - The pure decision function: input is a list of `(input_tokens, cache_read_tokens, cache_write_tokens)` per call, plus `tool_called: bool`, `strip_fired: bool` and `run_error: str | None`; output is `(code, reasons)`.
   - The async `run_probe(args)`, following the `tokens.measure_prompt` pattern; read `evals/tokens.py::measure_model_counts` for the harness call sequence.
   - WARNING capture on `the_one.llm.anthropic_provider`, through a `logging.Handler` attached for the run.
   - Read per-call usage from the assistant messages in `attempt.trace.turns[0].messages`, the way `evals/tokens.py::first_call_input_tokens` does.
7. **The scenario TOML**: `parse_scenario` requires:
   - `id` (lowercase, digits, hyphens; e.g. `cache-probe`);
   - `class` (use `hold`, as in `evals/measure/bare.toml`);
   - `conversations`, a non-empty list of tables with non-empty string `turns`;
   - `checks`, a NON-EMPTY list. Add one inert check such as `name = "tool_called"`, `pattern = "current_time"`; `run_once` never scores it.

   The persona goes in `[agent] persona = "..."`; unknown agent keys are refused. Keep the filler free of `{` and `}`, because turn text goes through `expand`. Otherwise copy the shape of `evals/measure/bare.toml` or an existing `evals/scenarios/*.toml`.
   - Build the padding as repeated plain-prose lines, a static text block in the file, with no generated randomness.
   - Make it about 5000 tokens at 3.7 bytes per token, about 18 KB.
   - Read `evals/scenario.py::parse_scenario` for the field names.
8. **Tests**: as listed in the acceptance criteria. Use the existing stub patterns in `tests/test_anthropic_provider.py` (`_StubResponse`, `_StubContentBlock`, the fake client) and in `tests/_evals_helpers.py`.
9. **Docs**: as in the acceptance criteria.

## Edge Cases
- **Empty system prompt**: no `system` key, top-level marker only.
- **The SDK usage object lacks cache attributes** (an older SDK, or a stub): they count as 0, so `input_tokens` equals the plain value.
- **A repeat refusal after a strip**: no infinite loop. Each key is stripped at most once, so the loop is bounded by the number of kwargs keys.
- **The `stream` TypeError on an old SDK** is raised when `_stream_inner` enters `messages.stream(**kwargs)`, before any yield, so a retry is allowed.
- **`_cache_disabled` with the temperature retry still pending**: both strips may fire in one call.
- **`compare --models` with an empty string, or duplicate names**: refuse an empty selection and de-duplicate.

## Files Affected
- `the_one/llm/base.py`, `the_one/llm/anthropic_provider.py`, `the_one/db/codec.py`
- `evals/__main__.py`, `evals/baseline.py`, `evals/cache_probe.py` (new), `evals/cache_probe_data/*.toml` (new), `evals/README.md`
- `tests/test_anthropic_provider.py`, `tests/test_db_codec.py`, `tests/test_evals_cache_probe.py` (new), `tests/test_evals_baseline*.py` and/or `tests/test_evals_cli.py`, plus one usage-frame test
- `the_one/agents.md`, `CLAUDE.md`
- The flight log, and this leg's status

## Citation Audit
Checked against the working tree at `baf9f8c3`.

- `the_one/llm/anthropic_provider.py`:
  - `_build_kwargs` (`system_prompt = m.content` for the system role; `kwargs["system"] = system_prompt` when truthy): verified.
  - `complete`: the `except BadRequestError` temperature retry and `except TypeError` strip; the nested retry inside `except TypeError` has no temperature handling. Verified.
  - `stream`: the same, with `yielded_any`. Verified.
  - Usage mapping at the end of `complete` and `_stream_inner`: verified.
- `the_one/llm/anthropic_plan_provider.py`: `complete`/`stream` wrap `super()` and translate only the escaping `AnthropicError` (`stream` via `contextlib.aclosing`). Verified, re-checked by the Architect.
- `the_one/llm/base.py::TokenUsage`: two int fields. Verified.
- `the_one/db/codec.py::_usage_to_dict` and the decode block: verified.
- `evals/__main__.py`:
  - `_cmd_compare` calls `rp.load_runs`, `bl.check_comparable(base, runset, same_prompt=..., measure=...)` and `bl.compare(base, runset, measure)`: verified.
  - `main` catches `MergeError`/`BaselineError` into `_err`: verified.
- `evals/baseline.py::check_comparable`: models fingerprint equality check. Verified.
- `evals/report.py::RunSet.models_fingerprint`: verified.
- `evals/fingerprint.py::models_fingerprint(presets, effective, model_info)`: verified.
- `evals/env.py::check_pinned_env`: verified. `startup` calls it; the Architect cited `env.py:364`, so re-check the line at implementation.
- `evals/tokens.py::first_call_input_tokens` reads `attempt.trace.turns[*].messages[*].usage`: verified.
- `tests/test_streaming.py:188`: `MagicMock(input_tokens=1, output_tokens=1)`. Verified by the Architect.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

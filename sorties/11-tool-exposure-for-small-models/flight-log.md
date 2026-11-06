# Flight Log: Tool exposure for small local models

**Flight**: [Tool exposure for small local models](flight.md)

## Summary
Sortie planned on 2026-11-05 from the local-LLM layer benchmark. Charter agreed with the operator: embedding pre-load is out of scope (a follow-up); the evals run on `qwen3:4b-instruct` and `lfm3:1.7b` plus haiku, with `gpt-oss:20b` kept as a preset but not run by default.

---

## Leg Progress

### Leg 1 — eval-apparatus (completed)
**What landed.** Everything in the leg's Outputs, offline, no model call, no product behaviour change: the only file added under `the_one/` is the leaf `the_one/agent/tool_exposure.py` (`ToolExposure`; nothing imports it). `the_one/agent/core.py` is untouched.
- **Fixture hostname (DD4).** `FIXTURE_HOSTNAME = "town.example"`; `FixtureServer.base_url` is `http://town.example`, `.port` and `.nonce` are new; the handler answers `/.well-known/evals-nonce` itself, `text/plain`, bare nonce.
- **Rewrite mechanism (AC2 / guidance step 1): the recommended one**, `harness.fixture_host_patch(port)`, a context manager that wraps the class-level `httpx.AsyncHTTPTransport.handle_async_request` (not the per-tool `_build_transport` seam). It builds a NEW `httpx.Request` to `127.0.0.1:{port}` (method, path, query, headers with `Host` kept, `stream`, `extensions`) and passes any other host through untouched. `SSRFGuardedTransport` reaches that method via `super()` after its host-policy check and its `extra_allowed_hosts` branch, so the real policy still runs and `fetch_url`/`http_request` are both covered. `Harness` owns an `ExitStack` (entered in `setup()` when it has a fixture server, closed by `Harness.close()`, which `_run_with_env`'s `finally` calls). `setup()` writes `[town.example]` for both web-tool lists, then runs the nonce self-test through the real `FetchUrlTool` built by `BuiltinToolProvider().get_tools(...)` from the scratch database's tool rows; any mismatch, error string or exception is an `EvalRefusalError`, and `setup()` closes the patch itself before re-raising. `run_invocation` now catches `EvalRefusalError` from `_run_with_env` (after its `finally` stopped the server and shut the env down) and returns exit code 2.
- **Scoring.** `tool-discovery` no longer declares `search_tools_used`. `CheckResult.passed` is `bool | None`, `exposed` added; `CheckDecl.exposed_if`; `is_exposed()`; `RunTrace.fixture_requests`. A `[error] ...` result string counts as an error as well as `is_error` (the tools return errors as strings). `report` class (check level only), `claims_match_actions`, four claims cells, `exposed_if` on the two planted-instruction cells, mixed-cell refusal. Readers walked: `safety_failures`, `decide`, `build_record` (incl. the FAIL-with-no-failing-check branch), `aggregate`/`CellStat.not_exposed`/`incomplete`/`to_dict`, `cell_bar`, `compare` (four exposure cases plus a `report` branch placed BEFORE the no-runs check, so a report cell with no runs reads as a PASS row, not HARD), `render_report`, `_stat_line`. A grep for `.passed`/`"passed"` across `evals/` found no other reader.
- **Size gate and exposure (DD8, DD1).** `tools_full`, `tools_full_names`, `prompt_text`, `exposure` per configuration; `schema` 2 on the measurement and, via `build_baseline`, on a baseline built from it; `EXPOSURE_CONNECTOR_TOOLS`; `size_targets(..., schema=)` keeps the schema-1 shape as the default (the existing schema-1 tests call `bl.size_targets(cfg)` and pass unchanged; the schema-1 body is private `_size_targets_v1`) and `compare` takes the schema-2 path without `extra_size_gates`. `measure-prompt` pins its scripted provider (16384, 3.5, `context_window_known`). Run and transcript records carry `exposure` and `tools_off` at top level.
- **Presets, env.** `qwen3-4b` and `lfm3` added, `gpt-oss` `default = false`; `Preset.default`; `select_presets(…, None)` returns the defaults; `preset_dict` is unchanged (it never listed `default`). Two exposure variables pinned.
- **Freeze.** `checks.py` and `harness.py` digests recomputed; the scenarios test renamed to `test_scenarios_fixtures_and_judge_match_the_pinned_scenarios_fingerprint` and pinned to the literal `SCENARIOS_FINGERPRINT`; `MEASURE_DIGESTS` unchanged (`evals/measure/` untouched).
- **README** documents all of AC25; `CLAUDE.md` unchanged (leg 2 names the new baselines).

**Choices worth the reviewer's eye.** (1) The report branch in `compare` precedes the "no runs" check. (2) `[error]` result strings count as errors for exposure and for claims. (3) `Comparison.notes` carries the per-model exposure-count lines and the `WARNING` lines above the table. (4) `tools_full_names` and `exposure` sit at configuration level, beside `totals`; `tools_full` and `prompt_text` inside `totals`. (5) The all-on `tools_full_names` includes the knowledge-base search tool, whose name embeds a hash of the measure agent's name (stable across runs, per the determinism test).

**Fake-counter measure-prompt (StandInCounter, ceil(bytes/4)), all-on:** `tools` 479, `tools_full` 1757, `tools_full_names` = `search_tools, continue, current_time, save_note, update_note, forget_note, read_file, write_file, edit_file, delete_file, move_file, mkdir, glob, grep, list_dir, http_request, fetch_url, kb__Measurement_KB_<hash>__search`. (bare: tools 294, tools_full 1478; tool-free 0/0; bare-connector tools_full 2144, includes the three connector tools.)

**Verification.** `THE_ONE_TEST_NETNS=1 make test-unit`: `9248 passed, 15 skipped, 4079 deselected in 245.97s` (15 skips is the documented netns count). `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/` clean. Falsified (fix removed by edit, test seen failing, fix restored by edit): AC3 restore-in-finally, AC4 nonce comparison, AC7 short-circuit and the GET-log condition, AC10 safety_failures, decide, build_record (None cell and FAIL branch), aggregate not_exposed, cell_bar, compare (report, unmeasured, ungated), AC12 errored-call, AC13 pattern boundary, AC14 report in safety_failures, AC20 schema choice and mismatch error. Not separately falsified: AC20 `read_baseline` schema acceptance and the size-target key set (covered by the schema tests passing only with the real code).

## Flight Director Notes

### 2026-11-06 — execution start
- `/mission-control:agentic-workflow sortie 11`. Loaded `.flightops/ARTIFACTS.md` and `.flightops/agent-crews/leg-execution.md` (Developer: Sonnet; Reviewer: Haiku unless security-sensitive, then Sonnet). Branch `sortie/11-tool-exposure-for-small-models` created from `main` at `4888178a`; status `ready` → `in-flight`.
- DD14 (operator-approved) overrides the once-per-flight review: leg 1 is reviewed and committed before leg 2 runs a model; leg 3 has its own in-leg review before its runs.
- **Leg 1 (`eval-apparatus`) risk tier: high.** It changes the scoring path's shared types (`CheckResult`, run records, baseline documents) read by every eval command and their tests, it moves the freeze test, and it adds a request rewrite in front of the SSRF-guarded transport. Design review by a Developer before implementation.
- **Leg 1 design review (cycle 1): approve with changes.** Three high issues, all folded in:
  - `read_baseline` would lock out schema-1 files. Schema 2 is now keyed off the measurement document's own schema, so schema-1 tests and files are unchanged, and a mismatch is a `BaselineError`.
  - AC5's no-loopback test would have been vacuous against the existing `127.0.0.1` bases. It now expands with the hostname base, and those call sites move.
  - The three `not r.passed` sites (runner ×2, `safety_failures`) and `aggregate`'s `_bump` tables would have read not-exposed as failed. They are now named, with the replacement predicate.

  Medium and low fixes, also applied:
  - setup rows always name the hostname;
  - `'''` TOML literals for the claim patterns;
  - `tools_off` → `tools_full` 0 and a separate three-name connector constant;
  - the can-fail harness updates;
  - nonce `text/plain` and `[200]\n` framing;
  - the `BuiltinToolProvider` build path;
  - `CheckDecl.exposed_if` / `CheckResult.exposed`, and split class tuples;
  - patch close in the isolation fixture;
  - the exit-2 refusal test;
  - a README note on the regex false negatives.

  No second review cycle: every change adopts the reviewer's own recommended fix, and none adds new design. Leg 1 → `ready`.
- **Leg 1 implemented** (Developer, Sonnet). It landed with `THE_ONE_TEST_NETNS=1 make test-unit` reporting 9248 passed and 15 skipped. The rewrite is the class-level `httpx.AsyncHTTPTransport.handle_async_request` wrapper, `fixture_host_patch`.
- **Leg 1 review (DD14 per-leg review).** Reviewer tier: Sonnet, because the diff adds a request rewrite in front of the SSRF-guarded transport. Verdict `[HANDOFF:confirmed]`: no blocking issues; 426 eval tests and ruff clean.
  - The Developer's four flagged choices were accepted:
    - a report cell with no runs is a PASS row;
    - an `[error]`-prefixed tool result counts as an error;
    - `tools_full_names` and `exposure` sit at configuration level;
    - the KB tool is in all-on `tools_full_names`.
  - Non-blocking notes carried forward:
    - leg 2's probe confirms the two Ollama tags exist;
    - `Harness.close()` is a manual call (only `_run_with_env` builds a fixture-server harness today);
    - `baseline.py` now imports `evals.tokens` (style).
- Leg 1 → `completed`, committed before any model run (DD14).

---

## Decisions

### Ollama wire findings kept out of this sortie
**Context**: The benchmark also found that the Ollama native path drops model reasoning between tool steps, forces temperature 0 and sends no `tool_name`. It was offered as a squawk and failed qualification: capturing reasoning fills `Message.thinking`, which `the_one/db/codec.py` persists and `app.py` broadcasts as a `thinking` event (so every Ollama chat would start showing and storing reasoning), the sampling change affects every Ollama agent, and the measured benefit is unproven (neutral on `qwen3:4b-instruct` and `lfm3:1.7b` at n=20; a small n=5 gain on `qwen3:4b-thinking`).
**Decision**: Not a squawk and not part of this sortie; a separate sortie once an n=20 A-vs-B confirmation on `qwen3:4b-thinking` is in.
**Impact**: This sortie's eval comparison runs on the shipped Ollama wire.

---

## Deviations

---

## Anomalies

---

## Session Notes

### 2026-11-05 — planning
Benchmark arms (all on the real eval runner, patched in-process from a scratch driver): A as shipped; B a corrected Ollama wire; R B plus every tool schema up front; L names and one-liners in the prompt plus `load_tools(names)`; E shipped discovery plus the top 3 tools per user message by the app's `potion-retrieval-32M` embedder. R was the most robust for `qwen3:4b-instruct`; E ranked the right tools but the model acted on them only 9/20 on tool use; L failed for `qwen3:4b-instruct` and raised `lfm3:1.7b`'s note-saving in both directions.

### 2026-11-05 — planning probe: the loopback confound (DD4 premise)
With an arm-A transcript's real system prompt and starting schemas, `qwen3:4b-instruct-2507-q4_K_M` at temperature 0, 5 requests per URL: `http://127.0.0.1:54594/menu-1.html` → 0/5 tool calls, 5/5 refusals ("a local address"); `http://menus.example/menu-1.html` → 5/5 tool calls; `https://www.harbourside-cafe.co.uk/menu` → 5/5 tool calls. Every call was `search_tools` with a web-search-style query (`"menu soup of the day"`, `"harbourside-cafe.co.uk menu soup"`). Consequence: the benchmark's tool-use figure for the shipped discovery (1/20) is confounded; the knowledge-base figure (1/20 against 19/20) is not. The charter's criterion 2 was reworded with the operator's agreement to say so.

### 2026-11-05 — design interview
Operator decisions: up-front exposure for every provider (DD1); split the size gate (DD8); include an optional HAT leg; reword criterion 2.

### 2026-11-06 — Architect review, cycle 1: approve with changes
19 issues, none needing a redesign. The two high ones: `self_configuration/pending.py::apply_pending_revision` rebuilds a live agent's prompt and would revert to the discovery wording (now DD3: the decision is recorded on the agent and read there); and an unresolved context window leaves the 128k class default, which would size the budget at 8000 tokens for windows that may be 4k (now DD2: a `context_window_known` signal, discovery when unknown). Other fixes folded in: a guarded and bounded build-time lookup; M30 F2 leg 1c DD7 restated rather than silently overridden; the measurement pinned to the small presets' window with every run's exposure recorded; `evals/tokens.py`, `evals/env.py::PINNED_ENV` and `tests/test_evals_freeze.py` added (DD10); the not-exposed state and the `report` class traced through every reader of results; a test policy; the all-three-models hostname probe moved to the start of leg 2; DD12's `SECURITY-MODEL.md` sections named and the risk sharpened; the prompt-caching trade-off corrected (no `cache_control` in `the_one/llm/`).
Operator decisions on its questions: an unknown window means discovery; DD7 stands (connector tools stay discoverable for agents no connector names); 3 legs plus the optional HAT; qwen3's planted regression is a pre-declared accepted miss (DD12).

### 2026-11-06 — Architect review, cycle 2 (final): approve with changes
Both cycle-1 high issues confirmed resolved. Two defects the revision introduced, both fixed: recording the exposure decision in `effective` would have changed the models fingerprint so leg 3's `compare` refused (now its own `exposure` record key, outside every fingerprint); and the `tools_full` size gate left out the always-sent `search_tools` and `continue`, so it would have hard-failed every exposed configuration (now defined as the full would-be starting set, binding-aware, with a factory parity test in leg 3). Also folded in: the `ToolExposure` record contract fixed before leg 1 freezes `harness.py`; Ollama's window-known rule gated on `native_api` (the `openai-compatible` type does call `/api/show`); the prompt-text gate's copy-length constraint stated in DD3; a nonce self-test through the real `fetch_url` path; the baseline-exposed / candidate-unexposed rule; citation and test-list corrections; prerequisites reworded per leg.

### 2026-11-06 — operator decisions after cycle 2
- `fetch_channel_history` is exposed with the connector pair for connector-bound agents (supersedes M23 F4 L3 DD-6 for exposed agents only).
- **Deviation (operator-approved):** the methodology's once-per-flight review is replaced by a review and commit before each set of model runs: leg 1 before leg 2's baselines, and an in-leg review in leg 3 before its measurement and compare (DD14). Reason: a late review fix would invalidate hours of n=20 runs and spend plan quota twice.
- The sortie was marked `ready`.

### 2026-11-06 — sortie gate re-check
Criterion 2 (one cluster of decisions): holds; every decision is about how tools are offered and how that is measured; the Ollama wire and the claim guard stayed out. Criterion 3 (fits one flight): the design came to 3 legs plus the optional HAT, one over the soft limit of 2 plus a HAT. Raised with the operator, who chose to keep one sortie with 3 legs rather than split further or escalate to a mission.

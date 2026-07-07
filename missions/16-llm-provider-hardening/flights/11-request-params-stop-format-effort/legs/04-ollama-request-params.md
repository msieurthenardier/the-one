# Leg: ollama-request-params

**Status**: completed
**Flight**: [Request-Param Capabilities (A4)](../flight.md)

## Objective

Wire the three A4 params across **both** Ollama request paths — the `/v1`
OpenAI-compat path (in their OpenAI-compat shapes) and the native `/api/chat` path
(in their distinct native shapes: `options.stop`, body-level `think`, body-level
`format`) — reading them from the config surface, documenting the combos that a
given path/model can't honor, with hermetic fixtured tests.

## Context

- **Depends on L01** (resolvers) and follows L02/L03 (Anthropic + OpenAI/OpenRouter,
  landed). Last provider leg; the Mock provider has no request path.
- **Ollama has two wire dialects** selected by `self.native_api`
  (`ollama_provider.py:__init__`; the branch is at the top of `complete`/`stream`):
  - **`/v1` (OpenAI-compat)** — `complete` builds `payload` (`:248-256`), `stream`
    builds `body` (`:338-346`); both POST to `/chat/completions`. Shapes match
    OpenAI: `stop`, `reasoning_effort`, `response_format`.
  - **native `/api/chat`** — `_native_body` (`:440`) + `_native_options` (`:432`).
    Different shapes (doc-gate): **`options.stop: list[str]`**, body-level
    **`think: bool | "low"|"medium"|"high"|"max"`** (reasoning), body-level
    **`format: "json" | <json-schema-object>`** (structured output).
- **Native `think` is currently unused.** F10 left Ollama's `enable_thinking`
  accept-and-ignore (`:242`, `:323` — `# accepted, ignored`), so nothing sets
  `think` today. A4's effort→`think` is its first use — **no conflict** with any
  existing thinking wiring on this provider.
- **Config reads** mirror the existing `config.num_ctx` read
  (`ollama_provider.py:176-178`, `_coerce_num_ctx(config.get("num_ctx"))`): add the
  three A4 reads next to it, coercing via the L01 `_coerce_*` helpers.
- **DD3 / "Acceptable variations"**: apply each param on both paths where honored;
  no-op/document where a surface genuinely doesn't support it.

### Doc-gate findings + open HAT-confirm items (flight-log `## Wire-Format Premise`)

- `stop` → `/v1` `stop` (list); native `options.stop` (list). Clean both paths.
- `reasoning_effort` → `/v1` `reasoning_effort` (OpenAI-compat, Ollama translates to
  native `think`); native body-level `think`. **HAT-confirm (L07)**: the exact
  accepted-value set and the effort-string→`think`-level translation for the target
  Ollama model are not pinned by docs — hermetic tests assert the *wire shape we
  emit*, not model acceptance.
- `response_format` → `/v1` `response_format` (OpenAI-compat; **json_schema wrapper
  support on `/v1` is HAT-confirm** — the doc-gate pinned json_object/OpenAI-compat
  but not the json_schema wrapper); native `format` = `"json"` (for json_object) or
  the bare schema object (for json_schema).

## Inputs

- `the_one/llm/_request_params.py` (L01) — resolvers + `_coerce_*`.
- `the_one/llm/ollama_provider.py` — `__init__` (num_ctx read at `:176`), the two
  `/v1` kwargs sites (`:248-256`, `:338-346`), `_native_options` (`:432`),
  `_native_body` (`:440`).
- `the_one/llm/openai_provider.py::_a4_request_kwargs` (L03) — the OpenAI-compat
  mapping the `/v1` path mirrors (json_object → `{"type":"json_object"}`,
  json_schema → `{"type":"json_schema","json_schema":{"name","schema"}}`, stop,
  reasoning_effort). See DRY note in Guidance.
- Tests: `tests/test_ollama_native_provider.py` (native path), `tests/
  test_ollama_provider_*.py`, and the scripted-transport conformance harness.

## Outputs

- `the_one/llm/ollama_provider.py` — `__init__` A4 reads; `/v1` merge on both sites;
  native `think`/`format` in `_native_body` and `stop` in `_native_options`.
- Tests for both paths (unit + fixtured wire).

## Acceptance Criteria

- [x] **`__init__` reads the three A4 config keys** into instance attrs (e.g.
      `_reasoning_effort_config` / `_response_format_config` / `_stop_config`) via
      the L01 `_coerce_*` helpers, next to the existing `_configured_num_ctx` read;
      canonical-or-`None`, never raising on absent/non-dict/junk.
- [x] **`/v1` path — both sites wired**: `complete`'s `payload` and `stream`'s
      `body` both carry `stop` / `reasoning_effort` / `response_format` when
      configured (OpenAI-compat shapes: json_object → `{"type":"json_object"}`,
      json_schema → the `{"type":"json_schema","json_schema":{"name","schema"}}`
      wrapper), and none of the keys when unconfigured.
- [x] **native path — `stop`**: `_native_options` sets `options["stop"]` to the
      `list[str]` when configured; absent otherwise.
- [x] **native path — `reasoning_effort`**: `_native_body` sets body-level
      `think` to the canonical effort string when configured; absent otherwise.
- [x] **native path — `response_format`**: `_native_body` sets body-level `format`
      = `"json"` for canonical json_object, or the **bare schema object** (`rf
      ["schema"]`) for canonical json_schema; absent otherwise.
- [x] **No cross-path leakage**: the `/v1` shapes never appear on the native body
      and vice-versa (e.g. native never emits `reasoning_effort`/`response_format`
      keys; `/v1` never emits `think`/`format`/`options.stop`).
- [x] **None-path**: with no A4 config and the three env vars unset, neither path
      emits any of the three params.
- [x] **Un-honorable combos documented** in the flight-log L04 entry: e.g. a
      non-reasoning native model silently ignores `think`; `/v1` json_schema-wrapper
      support and the effort→`think` translation are **HAT-confirm (L07)** — hermetic
      tests assert emitted wire shape, not model acceptance.
- [x] **No ABC/signature change**; nothing new exported from
      `the_one/llm/__init__.py`.
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_ollama_native_provider.py tests/test_ollama_provider_auth.py
      tests/test_ollama_provider_recovery.py
      tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30`.

## Verification Steps

- Run the Ollama test files + conformance suite — all green including new A4 tests.
- Read the `_native_body`/`_native_options` diffs — confirm `think`/`format` are
  body-level and `stop` is options-level.
- Read the `/v1` `payload`/`body` diffs — confirm the merge sits after `if tools:`
  at both sites.
- `git diff --stat` — only `ollama_provider.py` + Ollama test files (+ flight
  artifacts).

## Implementation Guidance

1. **Import** from `_request_params.py` at module top: `resolve_reasoning_effort`,
   `resolve_response_format`, `resolve_stop`, `_coerce_effort`,
   `_coerce_response_format`, `_coerce_stop`.

2. **`__init__` A4 reads** (next to the `_configured_num_ctx` read at `:176-178`):
   reuse the existing `config = kwargs.get("config")`; set
   `self._reasoning_effort_config = _coerce_effort(config.get("reasoning_effort"))
   if isinstance(config, dict) else None`, and likewise for
   `_response_format_config` (`_coerce_response_format`) and `_stop_config`
   (`_coerce_stop`).

3. **`/v1` mapping** — add a private helper `_v1_a4_kwargs(self) -> dict[str, Any]`
   producing the OpenAI-compat additions (identical mapping to
   `OpenAIProvider._a4_request_kwargs`: `stop`, `reasoning_effort`,
   `response_format` with the json_schema wrapper + synthesized `name`). Merge it at
   **both** `/v1` sites after the `if tools:` block:
   `payload.update(self._v1_a4_kwargs())` (complete) and
   `body.update(self._v1_a4_kwargs())` (stream).
   - **DRY note (decided: keep local duplication)**: this duplicates L03's
     `_a4_request_kwargs` mapping body (~17 lines, `openai_provider.py:93-109`, not
     counting the docstring) rather than importing it. **Decision: duplicate
     locally.** Rationale: this is copy #2 (OpenRouter inherits OpenAI's via
     `complete`/`stream` — it is not a separate copy), so the rule-of-three hasn't
     triggered; keeping the legs independent avoids re-opening L03's landed file;
     and L05's conformance matrix asserts `/v1` and OpenAI emit *identical* wire
     shapes for shared config, which is a real drift-detector. **Forward-note (put
     it in a code comment):** if a third `/v1`-style provider ever needs this exact
     mapping, that is the trigger to lift it into
     `_request_params.py::to_openai_compat_a4(effort, rf, stop)` and update all call
     sites — do not re-litigate the DRY question before then. Do NOT leave two
     subtly-different copies: the `/v1` mapping must match L03's byte-for-byte in
     behavior (L05 will catch drift).

4. **native mapping**:
   - `_native_options` (`:432`): after the `num_ctx` block, add
     `stop = resolve_stop(self._stop_config); if stop: options["stop"] = stop`.
   - `_native_body` (`:440`): after building `body`, add body-level keys —
     `effort = resolve_reasoning_effort(self._reasoning_effort_config); if effort:
     body["think"] = effort`; and
     `rf = resolve_response_format(self._response_format_config); if rf:` →
     `body["format"] = "json"` when `rf.get("type") == "json_object"`, or
     `body["format"] = rf["schema"]` when `rf.get("type") == "json_schema" and
     rf.get("schema") is not None`.

5. **Tests**:
   - `__init__` reads: construct `OllamaProvider(model="m", config={...})`, assert
     the three attrs (present + absent/junk → `None`). Mirror
     `tests/test_anthropic_provider.py:test_init_reads_a4_config` (~:1047) — the
     established A4 init-attr-read pattern.
   - `/v1` config→wire transport idiom: Ollama builds its `httpx.AsyncClient`
     inline (no injectable `http_client`), so the mock pattern is to monkeypatch
     `httpx.AsyncClient.__init__` to inject `kwargs["transport"] =
     httpx.MockTransport(handler)` — the idiom already in
     `tests/test_ollama_provider_auth.py`. (This differs from L03's OpenAI
     injectable-client approach.)
   - native mapping (pure, no transport — easiest): call `_native_body(...)` /
     `_native_options(...)` directly and assert `think` / `format` (both variants) /
     `options["stop"]`, and their absence on the None-path.
   - `/v1` mapping: unit-test `_v1_a4_kwargs()` directly for all shapes + empty; and
     a config→wire test (httpx `MockTransport`, as L03 did) confirming the `payload`
     (complete) and `body` (stream) actually carry the params on the wire. Use the
     existing Ollama `/v1` test harness/monkeypatch pattern for transport.
   - No-leak: assert native body has no `reasoning_effort`/`response_format` keys and
     `/v1` payload has no `think`/`format`.

## Edge Cases

- **Non-reasoning native model ignores `think`**: expected; we emit it, the runner
  drops it. Not an error. Documented; HAT (L07) confirms behavior on the target
  model.
- **`/v1` json_schema wrapper unsupported by Ollama**: HAT-confirm — if the target
  Ollama build rejects the wrapper on `/v1`, it 400s (per-route gating is B4). We
  emit the OpenAI-compat shape regardless (consistency); the native path is the
  reliable structured-output route for Ollama.
- **effort value outside native `think` set** (e.g. canonical `minimal`/`xhigh`
  from an OpenAI-oriented config): emitted to `think` as-is; Ollama rejects unknown
  values → 400 (documented, not caught this flight; the canonical layer does not
  validate per-provider).
- **Empty-dict schema**: forwarded as-is (`format: {}` native / wrapped `/v1`) —
  same benign disposition as L02/L03.

## Files Affected

- `the_one/llm/ollama_provider.py` — `__init__` A4 reads; `_v1_a4_kwargs` helper +
  both `/v1` merges; native `think`/`format`/`stop`.
- Ollama test file(s) — A4 tests for both paths.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (Ollama files + conformance)
- [x] Update flight-log.md with a Leg Progress entry (incl. the HAT-confirm carry
      items for L07)
- [x] Set this leg's status to `landed` (in this file's header) — batch-commit
      model: full `completed` state is deferred to the flight-end review/commit,
      per Flight Director instruction for this leg
- [ ] Check off this leg in flight.md — deferred to the Flight Director (batch
      model; not done by the Developer per-leg)
- [ ] (Not final leg — no flight/mission status change)
- [x] Changes stay uncommitted — batch commit after L06 (do NOT commit at leg end)

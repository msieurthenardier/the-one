# Leg: context-budget-governor

**Status**: completed
**Flight**: [Agent-loop Resource Governance & Context-budget Management](../flight.md)

## Objective
Install a single **direction-aware context-budget governor** at the agent's tool-dispatch
boundary (`_execute_tool`) so every `ToolResult.content` — from any tool — is bounded to a
fraction of the active model's context window before it enters the conversation, retiring
today's per-tool LLM-facing caps while keeping the transport/OOM safety caps.

## Context
- **DD1** (flight): one governor at `_execute_tool` (core.py), head-preserving by default,
  `budget_bytes = f(self.llm.max_context_tokens)` via the `BYTES_PER_TOKEN` heuristic
  (DD4), with floor/ceiling + a truncation marker. Applies to web, filesystem, shell, MCP,
  future tools. Retire the per-tool *LLM-facing* caps; keep the safety caps.
- **HIGH-1 (binding)**: removing `tool_text_cap_bytes` drops `WebConfig.model_fields` from
  9→8 — the exact F07 0.2.6 failure. This leg MUST update `tests/test_web_config.py:33`
  (→8) + the docstring at :29-32, AND run the FULL unit suite (not a web subset).
- **HIGH-2 (binding)**: `execution.py` `output_cap_bytes` (default 262_144) is a SECOND
  mis-axed LLM cap and it is **tail-preserving** (the `[exit code: N]` suffix + stderr tail
  that `_truncate_output` deliberately keeps, execution.py:360-412). The governor must be
  **direction-aware**: head-preserve prose/pages, tail-preserve shell/exec output. Decide
  shell handling explicitly; do NOT silently head-cap shell output. Check
  `tests/test_execution_config.py` for an `output_cap_bytes` default assertion (line 38:
  `== 262_144`) that any change must track.
- **MEDIUM-1 (binding) — DECIDED**: there is already a per-provider accessor for this
  value: `_bytes_per_token_for_interim()` (`openai_provider.py:86`, overridden in
  `openrouter_provider.py:175`), consumed by the streaming usage heuristic via
  `_StreamAccumulator(bytes_per_token=...)`. To avoid two parallel accessors that can
  drift, **promote it to a single public `bytes_per_token` accessor on the `LLMProvider`
  base** (default 4.0) and have BOTH the governor and the stream accumulator consume it.
  Anthropic→3.7, Ollama→3.5 override it (they currently only pass the module constant into
  `_StreamAccumulator`); openai/openrouter fold their existing `_bytes_per_token_for_interim`
  override into the new public accessor. Single source of truth.
- **LOW-2 (binding)**: governor floors `max_context_tokens` — treat 0/None/absurdly-small
  as the base default (128_000).
- **LOW-3 (binding)**: exclude the MCP auth-required `ToolResult` (core.py:562, fixed
  `<auth required>` sentinel + pause metadata) from the governor — govern only `output`
  (the normal path, core.py:555) and the error-string content.
- **LOW-4 (binding) — CORRECTED**: there is NO out-of-band `ToolResult`. The F07 cancel
  path constructs an **assistant `Message`** (`app.py:1601`:
  `Message.assistant(partial_text + "\n\n_[interrupted]_")`), not a governed tool result.
  Document the deliberate non-coverage — partial assistant output is bounded by the bytes
  already streamed (low risk). Do NOT hunt for a nonexistent ToolResult.
- **Architecture (confirmed)**: `_execute_tool` is the correct single chokepoint;
  implement as a **pure helper** `govern_tool_content(...)` for unit-testability;
  `max_context_tokens` is resolved on the first `stream()` before any tool dispatch (sane
  class-attr fallback). `read_size_cap_bytes` (filesystem file-size guard) and the web
  `response_size_cap_bytes` 1 MB streaming hard-abort are SAFETY caps — KEEP both.

## Inputs
What must be true before this leg runs:
- `the_one/agent/core.py` `_execute_tool` returns `ToolResult(content=output)` (the normal
  path) and the typed error/timeout/auth `ToolResult`s shown at core.py:555-588.
- `the_one/llm/base.py` `LLMProvider.max_context_tokens` (default 128_000) resolves lazily.
- Per-provider `BYTES_PER_TOKEN_*` constants exist (anthropic/ollama/openai/openrouter).
- `tool_text_cap_bytes` is applied at `web.py:213,322,328` via `_cap_tool_text`.
- `output_cap_bytes` is applied in `execution.py` `_truncate_output` (tail-preserving).
- Field-count guards: `tests/test_web_config.py:33` (==9), `tests/test_execution_config.py`
  default assertions.

## Outputs
- New pure helper `govern_tool_content(content, max_context_tokens, *, fraction, floor,
  ceiling, direction, bytes_per_token)` (location: a small module, e.g.
  `the_one/agent/_governor.py`, or inline in `core.py` — design-review to confirm).
- `_execute_tool` applies the governor to the normal `output` result and the error-string
  results; excludes the auth-required sentinel (LOW-3).
- `bytes_per_token` property on `LLMProvider` base (default 4.0); subclass overrides reuse
  existing constants.
- `tool_text_cap_bytes` removed from `WebConfig` + `_cap_tool_text` call sites; web safety
  cap (`response_size_cap_bytes`) untouched.
- `output_cap_bytes` resolved per HIGH-2 (see Edge Cases / decision below).
- Field-count guards updated (web →8; execution per decision); FULL unit suite green.
- Governor-tunable defaults env-overridable (fraction/floor/ceiling).

## Acceptance Criteria
- [x] A pure `govern_tool_content(...)` helper exists and is unit-tested in isolation
      (no agent/LLM construction needed). (`the_one/agent/_governor.py`,
      `tests/test_governor.py::TestGovernToolContentPure`.)
- [x] `_execute_tool` governs the normal tool `output` and the error-string contents;
      the MCP `<auth required>` sentinel result is NOT governed (LOW-3).
- [x] Governor is **direction-aware**: head-preserve for prose/page/file tools,
      tail-preserve for shell/exec output (the `[exit code: N]`/stderr tail survives).
      (`Tool.truncation_direction`, `"tail"` on shell/python_exec/shell_session_send.)
- [x] Budget = `fraction × max_context_tokens × bytes_per_token`, clamped to [floor,
      ceiling]; `max_context_tokens` ≤0/None/absurd is floored to 128_000 (LOW-2).
- [x] A truncation marker is appended (head case) / prepended (tail case) so the
      model can tell content was cut; the marker sits OUTSIDE the budget.
- [x] A SINGLE public `bytes_per_token` accessor on `LLMProvider` (default 4.0; anthropic
      3.7, ollama 3.5, openai/openrouter 4.0) feeds BOTH the governor and the streaming
      usage accumulator — `_bytes_per_token_for_interim` removed.
- [x] `tool_text_cap_bytes` is removed (web); `tests/test_web_config.py` field-count
      assertion is ==8 and the method renamed `test_field_count_is_eight`; the web safety
      cap (`response_size_cap_bytes`, all sites) is untouched. `grep -rn tool_text_cap_bytes
      the_one/ tests/` returns nothing.
- [x] `output_cap_bytes` is reclassified as a safety ceiling (HIGH-2 option b): kept,
      `_truncate_output` exit-code/stderr-tail formatting intact, governor layers the
      model-derived tail-bound on top; `tests/test_execution_config.py` still passes; the
      decision is recorded in the flight-log entry.
- [x] Unit tests **across tool types** (web, filesystem, shell): a large *valid* result is
      capped to the model-derived budget; a small result passes unchanged; the cap scales
      with `max_context_tokens`; an error-result is bounded too; shell tail is preserved.
      (`tests/test_governor.py::TestGovernorAtDispatchBoundary`.)
- [x] The FULL unit suite (`make test-unit`) is green at/above the M16 baseline, no new
      flakes (3512 passed / 10 skipped / 0 failed).
- [x] Budget fraction/floor/ceiling are env-overridable with documented defaults
      (`.env.example`; `THE_ONE_TOOL_RESULT_BUDGET_FRACTION`/`_FLOOR`/`_CEILING`).

## Verification Steps
- `govern_tool_content` unit tests: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_governor.py -x --timeout 30` (new test file).
- Cross-tool governor tests added to / run from the tool test files (web/fs/exec):
  large-valid→capped, small→unchanged, scales-with-window, error-bounded, shell-tail-kept.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_web_config.py
  tests/test_execution_config.py -x --timeout 30` — field-count/default guards pass.
- Full suite once at leg-end: `make test-unit` — green, no new flakes.
- `grep -rn tool_text_cap_bytes the_one/ tests/` returns nothing (fully retired).

## Implementation Guidance

1. **Author the pure governor helper.**
   - `govern_tool_content(content: str, max_context_tokens: int, *, fraction: float,
     floor: int, ceiling: int, direction: Literal["head","tail"], bytes_per_token: float)
     -> str`. Floor `max_context_tokens` to 128_000 if ≤0/None/absurd (LOW-2). Compute
     `budget = clamp(int(fraction * max_context_tokens * bytes_per_token), floor, ceiling)`.
     No-op when the content already fits. Else slice head or tail (byte-boundary,
     `decode(errors="replace")` — mirror the exact idiom in `_cap_tool_text` /
     `_truncate_output`) and add a marker noting N bytes were dropped. **The marker sits
     OUTSIDE the budget** (NOT counted against it) — matching both existing caps'
     convention; state this explicitly in the helper.
   - Defaults env-overridable: e.g. `THE_ONE_TOOL_RESULT_BUDGET_FRACTION` (default 1/8),
     `_FLOOR_BYTES` (default 8_192), `_CEILING_BYTES` (default 262_144 — note this equals
     the old `output_cap_bytes` default; leave a comment so a reader diffing the two isn't
     misled). Keep all three in one place.

2. **Promote a single public `bytes_per_token` accessor to the base (MEDIUM-1, DECIDED).**
   - Add `bytes_per_token` to `LLMProvider` (default 4.0) as the ONE source of truth. Fold
     the existing `_bytes_per_token_for_interim()` overrides (`openai_provider.py:86`,
     `openrouter_provider.py:175`) into it and repoint the streaming usage heuristic
     (`_StreamAccumulator(bytes_per_token=...)`) at it so the governor and the accumulator
     share one value. Anthropic→`BYTES_PER_TOKEN_ANTHROPIC` (3.7),
     Ollama→`BYTES_PER_TOKEN_OLLAMA` (3.5) override; openai/openrouter→4.0. Do NOT leave
     two parallel accessors that can drift.

3. **Wire the governor into `_execute_tool` (core.py:534-590).**
   - Govern the normal-path `output` (core.py:555) and the two error-string `ToolResult`
     contents (timeout :579, generic except :585). Do NOT govern the auth-required result
     (:562). Pick `direction` per tool — a tool-declared preference is cleaner than a name
     switch: add a `truncation_direction` attribute/property to the tool base defaulting to
     `"head"`, override to `"tail"` on the execution tool. Design-review to confirm the
     mechanism (tool attribute vs. governor caller passing direction by `tool_call.name`).

4. **Retire the web LLM cap (HIGH-1).**
   - Remove `tool_text_cap_bytes` from `WebConfig` (_web_config.py:196) and the three
     `_cap_tool_text(..., cfg.tool_text_cap_bytes)` calls (web.py:213,322,328) plus the now-
     dead `_cap_tool_text` helper (`_web_config.py:427`) if unused. Update
     `tests/test_web_config.py`: the assertion at :33 (==9 → 8), the test **method name**
     `test_field_count_is_nine` (:29) and its comment (:30-32) — the name encodes "nine"
     and must be renamed, not just the docstring. Leave ALL `response_size_cap_bytes` uses
     intact (safety cap — `web.py:207,295,315,326,401`).

5. **Reclassify `output_cap_bytes` as a safety ceiling (HIGH-2) — DECIDED: option (b).**
   - Lower blast radius than removing the field. KEEP `output_cap_bytes` and
     `_truncate_output`'s formatting (stdout+stderr combine, `[exit code: N]` suffix, tail
     preservation), but reclassify the field's ROLE from a model-sized LLM cap to a large
     transport/safety ceiling, and let the **governor** apply the model-derived LLM bound
     on top (tail-preserving for this tool). Update the field's description/UI labels
     (`execution.py:177,187-191` — the "Opus headroom" / model-sized labels) to reflect the
     safety-ceiling role. Keep `tests/test_execution_config.py:38` (default still 262_144)
     and the range/Substitute tests (:93,:97,:239-242) — no field removal, so no field-
     count breakage. Record the decision in the flight-log entry.

6. **Run the FULL unit suite** (`make test-unit`) at leg-end; fix any guard the field
   removals tripped; confirm no new flakes vs the M16 baseline.

## Edge Cases
- **Shell exit-code/stderr tail**: tail-preserve so `[exit code: N]` and the stderr tail
  survive truncation (HIGH-2). A head-cap here would hide the most diagnostic part.
- **`max_context_tokens` unresolved/absurd**: floor to 128_000 (LOW-2) so a mis-setting
  provider can't produce a 0-byte or runaway budget.
- **MCP auth-required sentinel**: never govern it (LOW-3) — truncating `<auth required>` or
  its metadata would break the auth-pause affordance.
- **Cancel/partial-output result (F07 interrupt)**: constructed outside `_execute_tool`;
  confirm size-sane or document the deliberate bypass (LOW-4).
- **Multibyte boundary**: byte-slice then `decode(errors="replace")` — never split a
  codepoint into an exception.
- **Budget < marker length**: ensure the truncation marker itself can't exceed a tiny
  floor (clamp floor above marker size).

## Files Affected
- `the_one/agent/core.py` — apply governor in `_execute_tool`; tool `truncation_direction`.
- `the_one/agent/_governor.py` (new, or inline) — pure `govern_tool_content` helper.
- `the_one/llm/base.py` — `bytes_per_token` property (default 4.0).
- `the_one/llm/anthropic_provider.py`, `ollama_provider.py` — override `bytes_per_token`.
- `the_one/tools/_web_config.py`, `the_one/tools/web.py` — remove `tool_text_cap_bytes` +
  `_cap_tool_text` calls (keep `response_size_cap_bytes`).
- `the_one/tools/execution.py` — `output_cap_bytes` per HIGH-2 decision; keep
  `_truncate_output` formatting + tail preservation.
- `the_one/tools/base.py` (or tool base) — `truncation_direction` attribute, if chosen.
- `tests/test_web_config.py` — field count 9→8 + docstring.
- `tests/test_execution_config.py` — match the `output_cap_bytes` decision.
- `tests/test_governor.py` (new) + cross-tool governor tests in web/fs/exec test files.
- Docs: governor env vars (fraction/floor/ceiling) in the relevant config/README doc.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (full unit suite, not a subset)
- [x] Update flight-log.md with leg progress entry (record the HIGH-2 `output_cap_bytes`
      decision + the budget fraction/floor/ceiling chosen)
- [x] Set this leg's status to `landed` (NOT `completed` — commit deferred to flight end
      per the /agentic-workflow batch model)
- [x] Check off this leg in flight.md
- [x] (Not the final leg — do not land the flight here)
- [ ] Commit deferred to end-of-flight review (per /agentic-workflow batch model)

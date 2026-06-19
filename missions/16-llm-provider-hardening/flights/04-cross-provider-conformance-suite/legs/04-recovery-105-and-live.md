# Leg: recovery-105-and-live

**Status**: completed
**Flight**: [Cross-Provider Tool-Use Conformance Suite](../flight.md)

## Objective

Add the #105 fixtured loose-format recovery row to the conformance matrix (Ollama
recovers a recorded loose-format emission into a structured `ToolCall`, round-trips
the `ToolResult`, and produces a final answer), and add a light, key-gated,
self-skipping `@pytest.mark.live` tool round-trip that adds coverage the existing
live swap tests do not.

## Context

- **DD5**: the #105 fix joins the conformance matrix as a fixtured row — the
  hermetic counterpart to the live `gemma-tool-use-recovery` behavior test. It uses
  the **kwargs-form** `GEMMA_FIXTURE` (recovers to named args at the **provider**
  level), NOT the positional `` ```tool_code `` shell form (which parks args under
  `POSITIONAL_ARGS_KEY` for the *dispatcher* to resolve — out of scope for a
  contract-level round-trip per DD1).
- **DD8**: a light live tier — confidence signal only, no exact-content assertions
  (LLMs are non-deterministic). Extends the existing live scaffolding rather than
  duplicating it, and must add coverage genuinely distinct from the existing live
  swap tests (mandatory anti-duplication check below).
- **Dependencies (all landed):** leg 01 fixtures, leg 02 harness
  (`tests/fixtures/scripted_transport.py` — `make_ollama`, `CannedTurn`), leg 03
  guards. All in the conformance module `tests/test_llm_provider_cross_provider_conformance.py`.

### #105 recovery is provider-level (source-verified 2026-06-19)

- `OllamaProvider.complete()` recovers when there are no structured `tool_calls`:
  `_recover_into_tool_calls(content)` (`ollama_provider.py:31`) → `recover_and_strip`
  (`_toolcall_recovery.py:79`), wired at `ollama_provider.py:167-169` (complete) and
  `:267-269` (stream). So recovery happens **at the `LLMProvider` contract** — a
  scripted transport returning loose-format `content` and no structured `tool_calls`
  drives it directly, no agent loop, no dispatcher.
- `GEMMA_FIXTURE = "```tool\nget_weather(city='Paris')\n```"`
  (`test_toolcall_recovery.py:22`) recovers to **exactly**
  `[{"name": "get_weather", "arguments": {"city": "Paris"}}]`
  (`test_toolcall_recovery.py:30-33`) — kwargs form, no `POSITIONAL_ARGS_KEY`, no
  dispatcher resolution. The recovered call's `arguments` is a real dict; the
  stripped `content` becomes `""` (the fence was the whole message).
- Why NOT the positional form: `` ```tool_code\nshell('echo hi')\n``` `` recovers to
  `{"name":"shell","arguments":{POSITIONAL_ARGS_KEY:["echo hi"]}}`
  (`test_toolcall_recovery.py:50-58`) — the positional arg is parked under the
  sentinel for the dispatcher (a tools-layer/agent-loop concern), which a contract-
  level round-trip does not exercise. Use the kwargs form.

### Existing live coverage — the DD8 anti-duplication baseline

`tests/test_llm_provider_cross_provider_history.py` class `TestCrossProviderHistoryLive`
(`:588`) already has FOUR `@pytest.mark.live` tests, all **cross-provider session
swaps**:
- `test_anthropic_to_ollama_session_swap_live` (`:605`) — no tools
- `test_ollama_to_anthropic_session_swap_live` (`:638`) — no tools
- `test_anthropic_with_tools_to_ollama_swap_live` (`:671`) — Anthropic `complete()`
  with tools, append synthetic `ToolResult`, **re-send the whole history through
  Ollama** (a swap-shape test; the second call is a *different* provider and does not
  feed the tool result back to the originating provider to produce a final answer)
- `test_anthropic_to_openrouter_session_swap_live` (`:737`) — no tools

**The gap (DD8's distinct coverage):** none of these is a **single-provider two-turn
tool→result→final round-trip** — the same provider emits a `tool_call`, the test
feeds back a real `ToolResult`, and the same provider returns a final answer. That is
the live analog of this flight's hermetic conformance round-trip, and it is what the
new live test must add. Reuse `_resolve_ollama` (`:545`) and `_aclose_provider_client`
(imported there; defined in `tests/test_input_tokens_cross_provider_live.py`) and the
inline `pytest.skip`-on-missing-key idiom.

## Inputs
What exists before this leg runs:
- `tests/test_llm_provider_cross_provider_conformance.py` (legs 02/03) — the suite.
- `tests/fixtures/scripted_transport.py` (legs 02/03) — `make_ollama`, `CannedTurn`,
  `make_openrouter`, etc.
- `tests/test_toolcall_recovery.py:22` — `GEMMA_FIXTURE` (importable, or re-declare
  the verbatim constant in the conformance module).
- `the_one/llm/ollama_provider.py`, `the_one/llm/_toolcall_recovery.py` (read-only).
- `tests/test_llm_provider_cross_provider_history.py` — live class + `_resolve_ollama`.

## Outputs
What exists after this leg completes:
- A #105 fixtured recovery row in the conformance module: Ollama recovers
  `GEMMA_FIXTURE` into a structured `ToolCall`, the test builds a `ToolResult`, and a
  turn-2 final answer completes the round-trip. Covers `complete()`; `stream()`
  optional but recommended (the recovery wiring exists on both paths).
- One light `@pytest.mark.live` tool round-trip test (single-provider two-turn
  tool→result→final), key-gated + self-skipping, added to the existing live class in
  `tests/test_llm_provider_cross_provider_history.py` (DD8's stated approach;
  co-locating it in the conformance module while importing `_resolve_ollama`/
  `_aclose_provider_client` is an acceptable variation).

## Acceptance Criteria
- [x] **#105 recovery row (complete)**: driving `OllamaProvider.complete()` via a
      scripted transport whose turn-1 response carries `content == GEMMA_FIXTURE` and
      **no structured `tool_calls`** yields a `Message` whose `tool_calls[0]` is
      `ToolCall(name="get_weather", arguments={"city": "Paris"})` (recovered), with
      `content == ""` (stripped). The test then builds
      `Message.tool(ToolResult(tool_call_id=…, content=…))` and a turn-2 transport
      returns a final-answer `Message` with no `tool_calls`.
- [x] **#105 recovery row (stream)**: the same recovery round-trip over
      `OllamaProvider.stream()`; the **final** `StreamChunk` carries the recovered
      `ToolCall` on turn 1 and a final answer on turn 2. (Required — the recovery
      wiring exists on both paths and the stream path has a documented interim-content
      asymmetry worth pinning; assert on the final chunk only.)
- [x] **Recovery uses the kwargs form** — the row drives `GEMMA_FIXTURE`
      (`get_weather(city='Paris')`), not the positional `` ```tool_code `` form; the
      recovered `arguments` is `{"city": "Paris"}` with no `POSITIONAL_ARGS_KEY`.
- [x] **Live tool round-trip**: one `@pytest.mark.live` test performing a
      single-provider two-turn tool→result→final round-trip — **Anthropic is the
      required primary** (most operators have `ANTHROPIC_API_KEY`); an Ollama-qwen
      variant is optional. Key-gated with inline `pytest.skip` when the key/service is
      absent; confidence-only (no exact-content assertions).
- [x] **Anti-duplication confirmed**: the new live test is NOT a re-run of
      `test_anthropic_with_tools_to_ollama_swap_live` — it is a single-provider
      round-trip (same provider consumes the tool result and produces the final
      answer), documented as such in the test docstring.
- [x] **Self-skip clean**: with no credentials/service, the full suite still passes
      (the live test skips, the hermetic recovery row runs). `make test-unit`
      deselects `live` by default.
- [x] No production source modified (`git diff --stat -- 'the_one/**'` shows only
      the pre-existing leg-03 `openrouter_provider.py` docstring change; nothing new).

## Verification Steps
- Hermetic run (no creds): the recovery row passes, the live test self-skips:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30`
- Confirm the live test collects + self-skips without credentials:
  `.venv/bin/python -m pytest tests/test_llm_provider_cross_provider_history.py -m live -q`
  → skipped (no key), no error.
- `git diff --stat -- 'the_one/**'` → empty.
- Re-run the recovery unit suite to confirm no collateral breakage:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_toolcall_recovery.py tests/test_ollama_provider_recovery.py -x --timeout 30`
  → green.

## Implementation Guidance

1. **#105 recovery row** — reuse `make_ollama` from `tests/fixtures/scripted_transport.py`.
   Build turn-1 as a **content-only** `CannedTurn(content=GEMMA_FIXTURE)` (no
   `tool_calls`), so `make_ollama`'s stateful handler returns
   `{"choices":[{"message":{"content": GEMMA_FIXTURE}}], "usage":{…}}` with no
   `tool_calls` key — driving the provider's recovery path
   (`ollama_provider.py:167-169`). Verify `make_ollama` emits a content-only turn
   without a structured `tool_calls` array (if it always injects `tool_calls`, add a
   content-only branch or pass `tool_calls=[]` — the provider's `if msg.get("tool_calls")`
   is falsy for an empty/absent list, so recovery still fires). Turn-2 is a normal
   final-answer `CannedTurn(content="It is sunny in Paris.")`.
   - Drive `await ollama.complete([Message.user("weather in Paris?")], tools=[tool])`;
     assert `m1.tool_calls[0].name == "get_weather"` and
     `m1.tool_calls[0].arguments == {"city": "Paris"}` and `m1.content == ""`.
   - Build `result = Message.tool(ToolResult(tool_call_id=m1.tool_calls[0].id,
     content="sunny, 22C"))`; drive turn-2 `complete([user, m1, result], tools=[tool])`;
     assert `m2.tool_calls == []` and `m2.content` non-empty. **Read the recovered id
     from `m1.tool_calls[0].id` — do NOT reuse the structured-path `EXPECTED_TOOL_ID`
     (`"tc_1"`).** The recovery path synthesizes the id as `f"{name}_{index}"` →
     `"get_weather_0"` (`ollama_provider.py:48`), so a hardcoded `tc_1` would mismatch.
   - For `stream()`, the recovery wiring is at `ollama_provider.py:267-269`; assert
     on the **final** chunk's `.message`/`.tool_calls` only — interim chunks carry raw
     un-stripped content (documented asymmetry at `ollama_provider.py:261-266`).
   - This recovery row is a **standalone Ollama-only test**, not an entry in the
     parametrized provider matrix (that matrix uses a structured turn-1; the recovery
     row's turn-1 is content-only and its assertions — recovered id, `content == ""`,
     `arguments == {"city": "Paris"}` — are Ollama-specific).
   - `GEMMA_FIXTURE`: import from `tests.test_toolcall_recovery` OR re-declare the
     verbatim constant (`"```tool\nget_weather(city='Paris')\n```"`) in the
     conformance module with a comment citing the source. Re-declaring avoids a
     test-module-to-test-module import; importing avoids drift. Implementer's call —
     a re-declared verbatim copy with a source comment is fine and keeps imports clean.

2. **Light live tool round-trip** — add to `TestCrossProviderHistoryLive` in
   `tests/test_llm_provider_cross_provider_history.py` (reuses `_resolve_ollama`,
   `_aclose_provider_client`, the skip idiom in-file). A single-provider two-turn
   round-trip:
   - Gate: `if not os.environ.get("ANTHROPIC_API_KEY"): pytest.skip(...)` (and/or
     resolve Ollama qwen via `_resolve_ollama()` for an Ollama variant).
   - Turn 1: `reply = await provider.complete(history, tools=[tool_def],
     temperature=0.0, max_tokens=200)` with a prompt that strongly induces the tool
     call (e.g. "You MUST call the `get_weather` tool for Paris.").
   - If `reply.tool_calls`: append `Message.tool(ToolResult(tool_call_id=tc.id,
     content="sunny, 22C"))` for each, then turn-2
     `final = await provider.complete(history, tools=[tool_def], …)`; assert
     `isinstance(final, Message)` and `final.role == Role.ASSISTANT`. **No content
     assertions** (non-deterministic).
   - If the model did NOT call the tool (it may decline): do not fail — assert the
     turn-1 reply is a valid `Message` and note the round-trip was not exercised
     (mirror the existing swap test's defensive no-op handling), OR `pytest.skip` with
     a clear "model declined the tool" reason. Confidence test, not a behavior pin.
   - `finally: await _aclose_provider_client(provider)`.
   - Docstring MUST state how this differs from `test_anthropic_with_tools_to_ollama_swap_live`:
     this is a **same-provider** tool→result→final round-trip, not a cross-provider
     swap.

3. **Run hermetic first** (recovery row green, live self-skips), then the live tier
   only if the operator has credentials (not required for the leg to land — the
   hermetic recovery row is the regression net; the live test is a gated confidence
   signal).

## Edge Cases
- **`make_ollama` must not inject structured `tool_calls` for the recovery turn** —
  if it does, the provider takes the structured path and recovery never fires. Use a
  content-only `CannedTurn`; verify the emitted handler body has no truthy
  `tool_calls`.
- **Stripped content is `""`** — `recover_and_strip` removes the whole fence (the
  fence was the entire message), so assert `m1.content == ""`, not the fixture text.
- **`ToolResult.content` normalization** — non-str content is JSON-normalized at
  construction (`base.py:54-55`); pass a str or assert against the normalized str.
- **Live model may decline the tool** — handle defensively (skip-or-pin-shape), never
  a hard failure; the existing swap test (`:715-720`) models the no-op-if-no-call
  pattern.
- **Live test must self-skip, not error, without creds** — gate at function entry
  with `pytest.skip`; `_resolve_ollama` already raises `pytest.skip` when Ollama is
  unreachable.
- **Don't duplicate the swap test** — if the simplest thing to write would just
  re-run an Anthropic-with-tools→Ollama swap, that fails the anti-duplication AC.
  The distinguishing property is **same provider, two turns, real tool result fed
  back**.

## Files Affected
- `tests/test_llm_provider_cross_provider_conformance.py` — **append** the #105
  recovery row (complete + optional stream).
- `tests/test_llm_provider_cross_provider_history.py` — **append** one
  `@pytest.mark.live` single-provider tool round-trip to `TestCrossProviderHistoryLive`.
- No production source files.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (recovery row green; live self-skips clean; recovery unit suite green)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — no flight/mission status change)
- [ ] Do NOT commit (deferred-commit model — flight commits once after the last leg)

---

## Citation Audit

Citations verified against current code at leg design time (2026-06-19):
- `the_one/llm/_toolcall_recovery.py:79` `recover_and_strip`, `:65` `recover_tool_calls`,
  `:46` `POSITIONAL_ARGS_KEY` — **OK**
- `the_one/llm/ollama_provider.py:31` `_recover_into_tool_calls`; `:167-169`
  complete() recovery path; `:267-268` stream() recovery path — **OK**
- `tests/test_toolcall_recovery.py:22` `GEMMA_FIXTURE`; `:30-33` recovers to
  `get_weather`/`{"city":"Paris"}`; `:50-58` positional-form parks under
  `POSITIONAL_ARGS_KEY` (the out-of-scope contrast) — **OK**
- `tests/test_llm_provider_cross_provider_history.py:545` `_resolve_ollama`; `:588`
  `TestCrossProviderHistoryLive`; `:605/:638/:671/:737` the four existing live swap
  tests (anti-duplication baseline; `:671` is the tool-payload swap to avoid
  duplicating) — **OK**
- `_aclose_provider_client` — imported into the history file; defined in
  `tests/test_input_tokens_cross_provider_live.py` (per leg-02 reconnaissance) — **OK**

> Note: `the_one/llm/*` line numbers are stable (no production code changes in legs
> 01–03 except the leg-03 OpenRouter docstring). `tests/test_*` citations refer to the
> current working-tree state; prefer symbol/shape over line number if they drift.

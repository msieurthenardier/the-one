# Leg: wire-into-ollama-adapter

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

## Objective

Wire the leg-01 recovery kernel into `OllamaProvider` so that when a response carries **no
structured `tool_calls`** but its content holds a recognizable text-form call, the provider
recovers it into `ToolCall`s (synthesized stable ids), strips the recognized block from the
returned `content`, and returns them on the `Message` — in both `complete()` and `stream()`.

## Context

- Implements DD2 (recover only when structured `tool_calls` is empty) and DD4 (strip recognized
  block + synthesize stable ids) of the flight. The agent loop is **not** touched — it dispatches
  `response.tool_calls` unconditionally (DD6), so recovering into that field is sufficient.
- Leg 01 shipped `the_one/llm/_toolcall_recovery.py`: `recover_tool_calls(content) -> list[dict]`
  (each `{"name": str, "arguments": dict}`), plus the exported constant `POSITIONAL_ARGS_KEY`
  (`"__positional_args__"`). This leg imports and calls it.
- **Insertion points are explicit and verified against current code** (leg 01 did not modify this
  file):
  - `complete()` — after the structured-`tool_calls` parse loop at `ollama_provider.py:117-129`
    and **before** `return Message.assistant(...)` at `:139-143`. Recover only if the structured
    `tool_calls` list came back empty.
  - `stream()` — **after** `acc.finalize_tool_calls()` (`ollama_provider.py:225-228`) and
    **before** the final `msg = Message.assistant(...)` / final `StreamChunk` (`:230-237`).
    **NOT inside the streaming loop** — content is still accumulating there; recover once on the
    fully-accumulated `content`.
- This leg does **not** address the degraded follow-up round-trip (`_to_api_message`) — that is
  leg 03 (DD5), resolved empirically against the live model. Leave `_to_api_message` untouched here.

## Inputs

- `the_one/llm/_toolcall_recovery.py` (leg 01, landed) — `recover_tool_calls`, `POSITIONAL_ARGS_KEY`.
- `the_one/llm/ollama_provider.py` — `complete()` (`:99-143`), `stream()` (`:145-237`).
- Test idioms: `tests/test_ollama_provider_auth.py` (the `httpx.MockTransport` + `/api/show`-fires-
  first pattern for `complete`); `ollama_api.chat_stream` is the seam to monkeypatch for `stream`.

## Outputs

- `the_one/llm/ollama_provider.py` — recovery wired into `complete()` and `stream()`; a small
  private helper to map recovered dicts → `ToolCall` and strip the block from content.
- `tests/test_ollama_provider_recovery.py` — new hermetic suite (mocked transport / mocked
  `chat_stream`; no live model, no markers).

## Acceptance Criteria

- [x] **complete() recovers on empty structured tool_calls**: a mocked `/chat/completions`
      response whose `message.content` is the gemma fixture (` ```tool\nget_weather(city='Paris')\n``` `)
      and whose `tool_calls` is absent/null yields a `Message` with one `ToolCall`
      (`name="get_weather"`, `arguments={"city": "Paris"}`).
      _(test_complete_recovers_on_empty_structured_tool_calls)_
- [x] **stream() recovers on empty structured tool_calls**: a mocked `chat_stream` emitting the
      same content as `delta.content` chunks with no `tool_calls` deltas yields a final
      `StreamChunk` whose `message.tool_calls` carries the recovered call (and `tool_calls=` on
      the chunk matches). _(test_stream_recovers_on_empty_structured_tool_calls)_
- [x] **Recognized block is stripped from returned content** (DD4): in both paths, the returned
      `Message.content` does **not** contain the raw ` ```tool ` block. If stripping leaves only
      whitespace, `content == ""`. Surrounding prose (if any) is preserved.
      _(test_complete_strips_recognized_block, test_complete_strip_preserves_prose_before_and_after_fence,
      test_stream_strips_recognized_block, test_stream_strip_preserves_surrounding_prose)_
- [x] **Synthesized ids are stable and round-trip** (DD4): each recovered `ToolCall.id` is
      deterministic (e.g. `f"{name}_{index}"`); a test asserts the exact id value AND that it is
      what a subsequent `ToolResult.tool_call_id` would match (the loop preserves it via
      `the_one/agent/core.py:331-336` — assert the id the provider sets, not the loop).
      _(test_complete_synthesized_ids_stable_and_roundtrip)_
- [x] **No double-recovery when structured tool_calls present**: a mocked response with a proper
      structured `tool_calls` array (and arbitrary content) returns those calls unchanged and does
      **not** invoke recovery / does **not** strip content. (Clean structured path is unaffected.)
      _(test_complete_no_double_recovery_when_structured_present, test_stream_no_double_recovery_when_structured_present)_
- [x] **No false-positive on plain prose**: a response whose content is ordinary prose (no marker)
      yields `tool_calls == []` and unmodified content, in both paths.
      _(test_complete_no_false_positive_on_prose, test_stream_no_false_positive_on_prose)_
- [x] **Multi-call recovered in order**: a content with two same-format recognized blocks yields
      two `ToolCall`s in document order with distinct ids.
      _(test_complete_multi_call_recovered_in_order, test_stream_multi_call_recovered_in_order)_
- [x] **POSITIONAL_ARGS_KEY passthrough**: if a recovered call carries `__positional_args__`, that
      survives into `ToolCall.arguments` unchanged (the provider does not strip the sentinel — the
      dispatcher handles it). One test asserts this. _(test_complete_positional_args_key_passthrough)_
- [x] All existing Ollama tests still pass; the kernel suite still passes. Verify:
      `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ollama_provider_recovery.py tests/test_ollama_provider_auth.py tests/test_toolcall_recovery.py tests/test_ollama_api.py -x --timeout 30` green, then `make test-unit` green.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ollama_provider_recovery.py -x --timeout 30` — all green.
- `make test-unit` — full hermetic suite green (no regression in the Ollama or streaming suites).
- `grep -n "recover_tool_calls" the_one/llm/ollama_provider.py` — called in both `complete` and `stream`.
- Manual read: recovery in `stream()` is **after** `acc.finalize_tool_calls()` and **outside** the
  `async for` loop.

## Implementation Guidance

1. **Import the kernel** at the top of `ollama_provider.py`:
   `from the_one.llm._toolcall_recovery import recover_tool_calls` (and `POSITIONAL_ARGS_KEY` only
   if needed — the provider should pass `arguments` through verbatim, so likely not needed).

2. **Private mapping helper** (module-level or static) to keep both call sites DRY:
   ```python
   def _recover_into_tool_calls(content: str) -> tuple[str, list[ToolCall]]:
       """Recover text-form calls from content (DD2/DD4).

       Returns (stripped_content, tool_calls). When nothing is recovered,
       returns (content unchanged, []). Synthesizes stable ids f"{name}_{i}".
       """
   ```
   - Call `recover_tool_calls(content)`. If empty → return `(content, [])`.
   - Map each dict → `ToolCall(id=f"{d['name']}_{i}", name=d["name"], arguments=d["arguments"])`.
   - **Strip — DEFAULT TO EXTENDING THE KERNEL (Option B; pinned).** Add to the leg-01 module a
     `recover_and_strip(content: str) -> tuple[str, list[dict]]` that returns the stripped content
     **and** the recovered call dicts in one pass, and call it from the adapter. **Why this is the
     pinned default, not a coin-flip:** the kernel doesn't return span offsets, and dispatch is
     "first non-empty recognizer wins, full list returned." So an adapter-side re-matcher would
     have to re-implement (a) all three recognizers' span logic AND (b) the dispatch-winner
     selection to know *which* recognizer's blocks to strip — exactly the drift surface to avoid.
     The kernel already knows the winner and the spans for free during recovery. Keep
     `recover_and_strip` stdlib-only; `recover_tool_calls` can become a thin wrapper that drops the
     stripped-content half (preserve its existing signature/behavior + tests). Add kernel unit
     tests for the strip (fence stripped, surrounding prose preserved, whole-content bare-JSON →
     `""`, whitespace-only-remainder → `""`).
   - The adapter helper `_recover_into_tool_calls` then has exactly ONE responsibility beyond
     calling `recover_and_strip`: map each dict → `ToolCall` with a synthesized id. It holds **no**
     marker knowledge (the point of Option B).
   - **Synthesized-id note (intentional asymmetry):** `f"{name}_{index}"` is deliberately *more*
     collision-safe than the adjacent structured path's id, which falls back to the bare tool name
     when the wire omits an id (`ollama_provider.py:125`). Two same-name recovered calls get
     distinct ids (`get_weather_0`, `get_weather_1`); the structured fallback would collide. This
     asymmetry is deliberate, not accidental.

3. **`complete()` wiring** (after `:117-129`, before `:139`):
   ```python
   content = msg.get("content") or ""
   if not tool_calls:                      # structured parse came back empty
       content, recovered = _recover_into_tool_calls(content)
       tool_calls = recovered
   return Message.assistant(content=content, tool_calls=tool_calls, usage=usage)
   ```

4. **`stream()` wiring** (after `:225-228`, before `:230`):
   ```python
   tool_calls = [ToolCall(...) for e in acc.finalize_tool_calls()]   # existing
   if not tool_calls:
       content, recovered = _recover_into_tool_calls(content)
       tool_calls = recovered
   msg = Message.assistant(content=content, tool_calls=tool_calls, usage=usage)
   ```
   Note: the per-delta `StreamChunk`s already yielded carry the *raw* (un-stripped) content — that
   is acceptable (the live-streamed text shows briefly); the **final** message carries the stripped
   content and the recovered calls, which is what the session persists and the loop dispatches.
   Record this as an intentional, documented limitation (DD4 strips the *final* rendered content;
   interim deltas are not retroactively edited). Surface it in the flight log Notes.

5. **Tests** (`tests/test_ollama_provider_recovery.py`):
   - `complete` path: reuse the `httpx.MockTransport` + patched `AsyncClient.__init__` idiom from
     `tests/test_ollama_provider_auth.py`; the handler returns `/api/show` `{"model_info": {}}`
     first, then a `/chat/completions` response with the fixture content and no `tool_calls`.
   - `stream` path: monkeypatch `the_one.llm.ollama_provider.ollama_api.chat_stream` to return an
     async generator yielding chunk dicts. Content chunks are
     `{"choices": [{"delta": {"content": "..."}}]}`; the **usage trailer is a choices-empty dict**
     `{"usage": {"prompt_tokens": N, "completion_tokens": M}}` (this is the branch the provider
     reads at `ollama_provider.py:182` — without it the final chunk's `usage` is `None`). Build the
     content chunks so the accumulated text is the fixture (you may split the marker across two
     deltas to also exercise the "marker split across deltas" edge case). Collect chunks; assert
     the final (`is_final=True`) chunk's `message.tool_calls`.
   - Cover every acceptance criterion above with a named test (recover-complete, recover-stream,
     strip, **strip-preserves-prose-before-and-after-a-fence**, stable-id-roundtrip,
     structured-unaffected, prose-no-fp, multi-call-order, positional-passthrough). The
     positional-passthrough test triggers a `logger.warning` from the kernel — assert it via
     `caplog` (or otherwise expect the log line) so a strict-warnings config doesn't trip on it.

## Edge Cases

- **Structured `tool_calls` present but empty list `[]`** → treat as empty → recovery eligible.
- **Recovered call whose name is unknown to the registry** → not this leg's concern; the agent
  loop returns an error `ToolResult` (DD2 trade-off). Do not pre-validate names here.
- **Content is `None`** (`msg.get("content")` is null) → `content = ""`, recovery returns `[]`.
- **Both structured tool_calls AND a marker in content** → structured wins (no recovery); content
  is **not** stripped (we only strip when we recovered). Pin with the "structured-unaffected" test.
- **Streaming: marker split across deltas** → fine; recovery runs once on the fully accumulated
  `content` after the loop, never per-delta.

## Files Affected

- `the_one/llm/ollama_provider.py` — recovery wired into `complete()` + `stream()`; `_recover_into_tool_calls` mapping helper (dict→`ToolCall` + id synthesis, no marker knowledge).
- `the_one/llm/_toolcall_recovery.py` — extended with `recover_and_strip(content) -> tuple[str, list[dict]]` (Option B, pinned); `recover_tool_calls` becomes a thin wrapper. Stays stdlib-only; gains strip unit tests.
- `tests/test_ollama_provider_recovery.py` — new hermetic adapter suite.
- `tests/test_toolcall_recovery.py` — extended with `recover_and_strip` strip-behavior tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (scoped recovery suite + `make test-unit`)
- [x] Update flight-log.md with leg progress entry (note the interim-delta-not-stripped limitation)
- [x] Set this leg's status to `landed` (deferred-review model — NOT `completed`, NOT committed)
- [x] Check off this leg in flight.md
- [x] (Not final leg — no flight-landing steps; do NOT commit)

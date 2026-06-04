# Leg: streaming-accumulator-extraction

**Status**: ready
**Flight**: [Cleanup Grab-Bag](../flight.md)

## Objective
Extract a shared `_StreamAccumulator` helper that removes the near-identical streaming-parser duplication between the OpenAI and Ollama providers (and the triplicated byte-emitter block), with zero behavior change (resolves finding P5).

## Context
- Maintenance report 2026-06-04, finding **P5** (Advisory, cleanest architectural win): two near-identical hand-rolled accumulators — `openai_provider.py:196-253` and `ollama_provider.py:174-236` (~55 LOC each). Both share the same shape: `tool_calls_acc: dict[int, dict[str,str]]`, per-index `setdefault`+append on `function.arguments`, the F7-L04 byte-accumulator (`accumulated_bytes`/`last_emitted_bytes` + interim `StreamChunk(usage=…)`), and `sorted(tool_calls_acc.keys())` finalization with `json.loads`-or-`{}`. The ~20-LOC interim-usage byte-emitter is *also* echoed in `anthropic _stream_inner:160-184` (third variant).
- OpenRouter is a thin `OpenAIProvider` subclass (reuses OpenAI's `stream`); Anthropic uses the SDK's native `text_stream` + `get_final_message` (structurally different — adopts only the byte-emitter half).
- This is a pure refactor: existing provider tests must stay green **unchanged**.

## Inputs
- `the_one/llm/openai_provider.py:196-253`, `the_one/llm/ollama_provider.py:174-236`, `the_one/llm/anthropic_provider.py:160-184`.
- `the_one/llm/base.py` (`StreamChunk`, the provider interface).
- Existing provider streaming tests.

## Outputs
- A shared `_StreamAccumulator` (in `llm/base.py` or a new `llm/_streaming.py`) owning (a) tool-call delta accumulation keyed by index and (b) the byte→interim-usage emitter.
- OpenAI and Ollama providers feed it normalized deltas; Anthropic adopts the byte-emitter half.

## Acceptance Criteria
- [ ] A single `_StreamAccumulator` (or equivalent helper) encapsulates tool-call delta accumulation + the byte/interim-usage emitter, parameterized by `bytes_per_token` + threshold
- [ ] `openai_provider` and `ollama_provider` use it; the duplicated ~55-LOC blocks are gone
- [ ] `anthropic_provider` uses the shared byte-emitter (its tool calls still come whole from `get_final_message`)
- [ ] **No behavior change**: all existing LLM/provider streaming tests pass **without modification**
- [ ] Net duplication reduced (~110 LOC of accumulator + ~20-LOC triplicated emitter consolidated)

## Verification Steps
- `docker exec the-one pytest tests/ -q -k "stream or provider or llm"` green, with no edits to those tests
- `git diff --stat` shows the provider files shrinking and a single shared helper added
- Spot-check: a streamed tool-call response and a streamed text response produce byte-for-byte the same `StreamChunk` sequence as before (compare against a recorded fixture if one exists)

## Implementation Guidance

1. **Define the shared shape** — a `_StreamAccumulator` holding `tool_calls_acc`, `accumulated_bytes`, `last_emitted_bytes`; methods to (a) feed a normalized `(text_delta, tool_call_deltas)` tuple, (b) maybe-emit an interim `StreamChunk(usage=…)` when the byte threshold is crossed, (c) finalize (`sorted(keys)` + `json.loads`-or-`{}`).
2. **Normalize provider deltas at the edge** — each provider converts its SDK's chunk into the normalized tuple, then feeds the accumulator. Keep provider-specific parsing in the provider; only the accumulation is shared.
3. **Anthropic adopts only the emitter** — its tool calls arrive whole via `get_final_message`; it uses the byte→interim-usage emitter for parity, not the tool-call accumulation.
4. **Centralize the F7-L04 constants** — the `bytes_per_token` heuristic + threshold become parameters/defaults on the accumulator (the report flags per-provider constant drift as the risk this prevents).
5. **Run the provider tests unchanged** — if any test needs editing to pass, the refactor is not behavior-preserving: stop and re-scope per the flight's divert criteria.

## Edge Cases
- **Empty / malformed tool-call arguments** — finalization must still `json.loads`-or-`{}` exactly as before.
- **Interim-usage emission timing** — must fire at the same byte boundaries as the current per-provider code, or streamed usage telemetry shifts (a behavior change).

## Files Affected
- `the_one/llm/_streaming.py` (new) or `the_one/llm/base.py` - shared `_StreamAccumulator`
- `the_one/llm/openai_provider.py` - use the helper (remove dup)
- `the_one/llm/ollama_provider.py` - use the helper (remove dup)
- `the_one/llm/anthropic_provider.py` - use the shared byte-emitter
- `the_one/agents.md` - anchor for the streaming accumulator (DOC5 overlap)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (unchanged)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: (not final)
- [ ] Commit all changes together (code + artifacts)

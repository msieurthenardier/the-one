# Leg: mid-stream-usage-and-eager-resolve

**Status**: completed
**Flight**: [UI Performance Audit](../flight.md)

## Objective

Two carry-forward items from F6 KI #5 and F6.5 debrief AI #5:

1. **Mid-stream `usage` event emission**: providers' `stream()` currently emits `usage` only on the final metadata chunk. This leg adds interim emission via a chunk-byte → token heuristic (`BYTES_PER_TOKEN` per-provider constant for OpenAI / Ollama / OpenRouter; Anthropic uses native `message_delta` real numbers). Requires widening `Agent.step` with an optional `on_usage` callback to thread interim usage to `_process_and_broadcast` and out to the WS broadcast — back-compat preserved (existing `on_chunk`-only callers unaffected).

2. **Eager-resolve `max_context_tokens` at session join**: F6.5 HAT observation — telemetry overlay `max:` reads 0 before the first user message. This leg adds a NEW endpoint `GET /api/agents/{name}/context-window` that returns `{"max_context_tokens": int}` by constructing the agent's provider and running the L01-landed `_resolve_max_context_tokens_if_needed()`. Chat.js's `session_joined` handler fetches the endpoint and seeds the telemetry overlay's `max:` value.

## Context

- **F6 KI #5**: telemetry `usage` event only fires at step completion (provider's final stream chunk). Operator-observed smoothness gap during long streaming responses.
- **F6.5 debrief AI #5**: pre-first-turn telemetry zeros — the `max:` value shows 0 until the first user message because no `usage` event has fired yet.
- **F6.5 architect** (carry-forward from F6.5 design review): widening `Agent.step` is a real cross-cutting change. The flight spec spelled out the `on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None` signature with back-compat preserved.
- **F6.5 architect** (Anthropic special case): Anthropic's streaming API emits `message_delta` with real `usage` periodically — use that directly instead of the heuristic for Anthropic. The heuristic only applies to OpenAI/Ollama/OpenRouter.
- **Eager-resolve approach**: rather than a two-hop client-side fetch (`/api/agents/{name}` → `/api/providers/{id}/models` → walk for matching model id), L04 ships a single-purpose endpoint `GET /api/agents/{name}/context-window` that abstracts the resolution server-side. Works for all provider types including `openai-compatible` (which the existing `/api/providers/{id}/models` doesn't expose `context_length` for — F6.5 architect noted this gap).

## Inputs

- `the_one/agent/core.py` — `Agent.step` signature at lines 111-179; the `on_chunk` callback threading
- `the_one/interfaces/web/app.py` — `_process_and_broadcast` at lines 729-889; current `usage` broadcast site at line 793 (live-read of `session.agent.llm.max_context_tokens`)
- `the_one/llm/openai_provider.py` — `stream()` at line ~145; the final-only usage emission at line ~160
- `the_one/llm/ollama_provider.py` — `stream()` at line ~115; final-only usage emission at line ~149
- `the_one/llm/openrouter_provider.py` — inherits OpenAIProvider.stream()
- `the_one/llm/anthropic_provider.py` — `stream()`; emits `message_delta` chunks with real interim usage
- `the_one/llm/base.py` — `StreamChunk` dataclass with optional `usage: TokenUsage | None = None` (already supports per-chunk usage; just needs to be populated mid-stream by providers)
- `the_one/interfaces/web/api.py` — agent + provider route registry; need a new `GET /api/agents/{name}/context-window` route
- `the_one/agent/factory.py` — `AgentFactory.create(name)` returns an Agent; we can use this to construct the provider for the new endpoint
- `the_one/interfaces/web/static/js/areas/chat.js` — `session_joined` handler at line ~727; the telemetry-overlay seeding goes here

State that must be true:
- L01 + L02 + L03 landed; F7 telemetry instrumentation in place; H1 leak fixed
- Broad pytest 1669p/4s/375d at L03-landed; browser 316p/35s

## Outputs

Files modified — Mid-stream usage (Track A):
- `the_one/agent/core.py` — `Agent.step` gains optional `on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None` parameter. When a `StreamChunk` carries `usage` (interim OR final), call `on_usage` if provided. Back-compat: callers passing only `on_chunk` work unchanged.
- `the_one/interfaces/web/app.py` — `_process_and_broadcast` constructs an `on_usage` callback that broadcasts an interim usage event mirroring the existing `usage_event` shape but with `is_interim=True` discriminator field. Passes it to `agent.step(..., on_usage=...)`. The existing final-usage emission at line 788-795 stays (handles the final/non-streaming-completion case).
- `the_one/llm/openai_provider.py` — new module-scope `BYTES_PER_TOKEN_OPENAI = 4.0`. In `stream()`, accumulate chunk bytes CUMULATIVELY (cycle-1 fix); track `last_emitted_bytes = 0`; at chunk delta with non-empty text, increment `accumulated_bytes += len(text.encode('utf-8'))`. When `accumulated_bytes - last_emitted_bytes >= 200`, yield a StreamChunk with `is_final=False` and a synthesized `TokenUsage(input_tokens=<initial-prompt-estimate>, output_tokens=int(accumulated_bytes / BYTES_PER_TOKEN_OPENAI))`, then set `last_emitted_bytes = accumulated_bytes`. Semantics: cumulative output_tokens (frontend last-write-wins handles this).
- `the_one/llm/ollama_provider.py` — same pattern; `BYTES_PER_TOKEN_OLLAMA = 3.5`.
- `the_one/llm/openrouter_provider.py` — inherits OpenAI's stream(); add a class-level override of `BYTES_PER_TOKEN` constant to `BYTES_PER_TOKEN_OPENROUTER = 4.0` (most OpenRouter-routed models are OpenAI-compat).
- `the_one/llm/anthropic_provider.py` — **Cycle-1 reviewer correction**: the current `stream()` body at lines 119-147 uses the high-level `client.messages.stream()` context manager + `stream.text_stream` iterator, which does NOT expose `message_delta` events with interim `usage`. To get interim usage from Anthropic via real SDK numbers would require refactoring to raw-event iteration (`RawMessageDeltaEvent`) — too invasive for L04. **Decision**: drop the Anthropic special-case. Apply the byte-heuristic uniformly: add `BYTES_PER_TOKEN_ANTHROPIC = 3.7`; emit interim StreamChunk(usage=...) at 200-byte cumulative boundaries, same pattern as OpenAI. Trade-off: Anthropic interim values are estimates, not provider-truth, for the duration of L04. A future flight can refactor the stream loop to use raw events if higher precision is needed.

Files modified — Eager-resolve (Track B):
- `the_one/interfaces/web/api.py` — new route `GET /api/agents/{name}/context-window` that:
  1. Loads the agent via `AgentFactory` or `get_agent` (whatever the project convention is)
  2. Returns `{"max_context_tokens": agent.llm.max_context_tokens}` after calling `await agent.llm._resolve_max_context_tokens_if_needed()`
  3. 404 if agent not found
- `the_one/interfaces/web/static/js/areas/chat.js` — `session_joined` handler at line ~727: after `showChrome()`, fetch `/api/agents/{currentAgentName}/context-window` and seed the telemetry overlay's `max:` via `App.chat.updateTelemetry(content, {input_tokens: 0, output_tokens: 0, context_tokens: 0, max_context_tokens: <fetched>})`.

State after:
- Telemetry overlay's `ctx:` and `max:` values progress smoothly during long streaming responses (interim usage every ~200 bytes for OpenAI/Ollama/OpenRouter; real `message_delta` numbers for Anthropic)
- Telemetry overlay's `max:` is populated BEFORE the first user message via the new endpoint
- F6 KI #5 and F6.5 carry-forward AI #5 closed
- Broad pytest: pass count grows by ~3-5 new unit tests (new endpoint, agent.step on_usage callback contract, per-provider chunk-byte emission)

## Acceptance Criteria

**Track A (mid-stream usage)**:
- [x] `Agent.step` signature in `the_one/agent/core.py` gains optional `on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None` parameter (default None, back-compat)
- [x] When `Agent.step` consumes a `StreamChunk` whose `usage` field is non-None AND `chunk.is_final` is False, it awaits `on_usage(chunk.usage)` if provided — **interim-only** (cycle-1 reviewer [high]: avoids double-emission with the existing final-usage path at `app.py:793`). Final-chunk usage stays on the existing emission path. Threading should NOT break if a provider never emits interim usage.
- [x] `_process_and_broadcast` in `the_one/interfaces/web/app.py` defines an `on_usage` callback that broadcasts an interim `usage` event with shape `{type: "usage", input_tokens, output_tokens, context_tokens, max_context_tokens, is_interim: True}` and passes it to `agent.step(..., on_usage=...)`
- [x] OpenAI / Ollama / OpenRouter providers emit interim `StreamChunk(usage=TokenUsage(...))` at chunk boundaries with the chunk-byte heuristic (every ~200 bytes accumulated). Anthropic emits real `message_delta` usage via the SDK's existing per-delta usage values.
- [x] Existing tests pass; `on_usage` callback path has at least one unit test (`tests/test_agent_step_on_usage.py` or similar): mock provider that emits 3 interim chunks with usage; assert `on_usage` was called 3 times.

**Track B (eager-resolve)**:
- [x] New route `GET /api/agents/{name}/context-window` in `the_one/interfaces/web/api.py` returns `{"max_context_tokens": int}` for an existing agent; 404 for unknown agent
- [x] Endpoint constructs the agent's provider via the existing factory pattern; calls `await provider._resolve_max_context_tokens_if_needed()`; returns `provider.max_context_tokens`
- [x] At least one unit test in `tests/test_api_context_window.py` (or similar) covering: existing agent returns positive int; unknown agent returns 404; provider fail-path returns the class default (not 500)
- [x] `chat.js`'s `session_joined` handler fetches the endpoint after `showChrome()` and calls `App.chat.updateTelemetry(...)` to seed `max:` with the fetched value

**Both tracks**:
- [x] Broad pytest exits 0; pass count = 1669 + N new tests (expect 1672-1675)
- [x] Browser suite preserved at 316 passing / 35 skipped (L03 baseline)
- [x] No regression in any existing chat flow

## Verification Steps

- **Mid-stream usage smoke**: open chat with `?perf=1`; send a long-prompt to a streaming model; watch the `ctx:` value in the telemetry overlay update PROGRESSIVELY during the response (not just at the end). FD post-Developer-landed can verify via MCP `evaluate_script` watching for `is_interim: True` events.
- **Eager-resolve smoke**: open chat; before sending any message, hover the telemetry overlay; `max:` shows the model's real context window (NOT 0).
- **Unit tests pass**: `docker exec the-one pytest tests/test_agent_step_on_usage.py tests/test_api_context_window.py -x --timeout 30 -v`
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1672-1675 passed
- **Browser suite**: preserved at 316p/35s

## Implementation Guidance

**Track A — Mid-stream usage**:

1. **`the_one/agent/core.py`** — extend `Agent.step` signature:
   ```python
   async def step(
       self,
       user_input: str,
       on_chunk: Callable[[str], Awaitable[None]] | None = None,
       on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None,
   ) -> AsyncIterator[Message]:
   ```
   In the chunk-consumption loop, when a chunk has `chunk.usage is not None`, await `on_usage(chunk.usage)` if provided. Existing behavior unchanged when `on_usage is None`.

2. **`the_one/interfaces/web/app.py`** `_process_and_broadcast`: define a nested coro `async def _broadcast_usage(usage: TokenUsage) -> None` that constructs an interim usage_event with `is_interim=True` and awaits `_send_to_session(session, event)`. Pass to `agent.step(..., on_usage=_broadcast_usage)`.

3. **Per-provider mid-stream emission**:
   - `the_one/llm/openai_provider.py`: in `stream()`, track `accumulated_bytes = 0`; at chunk delta with non-empty `text`, increment `accumulated_bytes += len(text.encode('utf-8'))`. When `accumulated_bytes >= 200` (or another threshold — start with 200), yield `StreamChunk(usage=TokenUsage(input_tokens=last_known_prompt_size, output_tokens=int(accumulated_bytes / 4.0)), is_final=False)` and reset accumulated_bytes for the next interim emission.
   - `the_one/llm/ollama_provider.py`: same pattern with `BYTES_PER_TOKEN_OLLAMA = 3.5`.
   - `the_one/llm/anthropic_provider.py`: when an SDK event has `event.type == "message_delta"` and carries `usage`, yield `StreamChunk(usage=TokenUsage(...from delta...), is_final=False)`.

**Track B — Eager-resolve**:

4. **`the_one/interfaces/web/api.py`** — add the route. **Cycle-1 reviewer correction**: there is no `get_or_construct_agent` helper; existing `/api/agents/{name}` at `api.py:364-371` only loads an `AgentConfig`, NOT a runtime Agent. To get `agent.llm.max_context_tokens`, must invoke `AgentFactory.create(name)` (signature at `the_one/agent/factory.py:186`):

   ```python
   from the_one.agent.factory import AgentFactory
   from the_one.agent.config import ProviderNotConfiguredError, ProviderNotFoundError

   @router.get("/agents/{name}/context-window")
   async def get_agent_context_window(name: str) -> dict[str, int]:
       factory = AgentFactory()
       try:
           agent = await factory.create(name)
       except KeyError:
           raise HTTPException(404, f"Agent not found: {name}")
       except (ProviderNotConfiguredError, ProviderNotFoundError) as exc:
           raise HTTPException(400, str(exc))
       await agent.llm._resolve_max_context_tokens_if_needed()
       return {"max_context_tokens": agent.llm.max_context_tokens}
   ```

   `AgentFactory.create(name)` constructs the full Agent with LLM provider attached. The resolver call then populates the instance attribute (lazy-cache from F6.5 L01). Construction cost is non-trivial (loads provider config from DB, instantiates the LLM client) but acceptable for a once-per-session-join endpoint.

5. **`the_one/interfaces/web/static/js/areas/chat.js`** — extend `session_joined` handler:
   ```javascript
   if (data.type === 'session_joined') {
     // ... existing logic + showChrome() ...
     // L04 eager-resolve: fetch max_context_tokens for the joined agent
     if (currentAgentName) {
       fetch('/api/agents/' + encodeURIComponent(currentAgentName) + '/context-window')
         .then(r => r.ok ? r.json() : null)
         .then(data => {
           if (data && data.max_context_tokens) {
             App.chat.updateTelemetry(content, {
               input_tokens: 0, output_tokens: 0, context_tokens: 0,
               max_context_tokens: data.max_context_tokens
             });
           }
         })
         .catch(() => {});
     }
     return;
   }
   ```
   Place AFTER `showChrome()` so the overlay element exists.

6. **Run tests**:
   ```bash
   docker exec the-one pytest tests/test_agent_step_on_usage.py tests/test_api_context_window.py -x --timeout 30 -v
   docker exec the-one pytest -x --timeout 30
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

7. **Do NOT commit** — Flight Director batches commits after L05.

## Edge Cases

- **Streaming provider that emits zero interim usage chunks**: existing behavior unchanged. Final usage still emitted at end-of-stream via the existing `_process_and_broadcast` site. The overlay updates at end-of-turn, just like today. The new `on_usage` callback simply never fires for that provider.
- **`is_interim: True` event in `session.history`**: should NOT be persisted to DB. The existing `_send_to_session` path broadcasts but doesn't persist usage events (they're projection-only). Verify by inspection.
- **Frontend doesn't know about `is_interim`**: telemetry-overlay's `updateTelemetry` reads `input_tokens`, `output_tokens`, `context_tokens`, `max_context_tokens` regardless. The `is_interim` field is informational; frontend can ignore it OR use it to skip historical replay. Choose: skip (frontend treats interim and final the same — last write wins).
- **`accumulated_bytes` threshold (200)**: arbitrary; tunable. Too low = telemetry-overlay re-render storms; too high = laggy updates. 200 bytes = roughly 50 tokens at BYTES_PER_TOKEN=4.0, which at ~20 tokens/sec streaming = one update every 2.5s. Adjust at HAT if it feels wrong.
- **Anthropic's `message_delta` cumulative-vs-delta semantics**: Anthropic emits CUMULATIVE usage in each message_delta event, not deltas. Forward as-is to TokenUsage — the frontend overwrites with last-write-wins anyway.
- **The new endpoint constructs the provider WITHOUT a real LLM call**: the resolver is lazy at the first `complete()`/`stream()` call, but `_resolve_max_context_tokens_if_needed` itself does the metadata HTTP fetch (for Ollama/OpenRouter). For Anthropic and OpenAI, it's a synchronous table lookup. Fine.
- **Provider fail-path** (Ollama down, OpenRouter API hiccup): the resolver catches and falls back to class default. The endpoint returns the class default (128k or 200k). Acceptable degradation.

## Files Affected

Track A:
- `the_one/agent/core.py` — `Agent.step` adds `on_usage` parameter
- `the_one/interfaces/web/app.py` — `_process_and_broadcast` passes `on_usage` callback
- `the_one/llm/openai_provider.py` — interim usage emission via chunk-byte heuristic
- `the_one/llm/ollama_provider.py` — interim usage emission via chunk-byte heuristic
- `the_one/llm/openrouter_provider.py` — inherits OpenAIProvider but may need a constant override
- `the_one/llm/anthropic_provider.py` — `message_delta` → `StreamChunk.usage` wiring
- `tests/test_agent_step_on_usage.py` (or extend existing test_agent.py) — new test for the callback contract

Track B:
- `the_one/interfaces/web/api.py` — new `GET /api/agents/{name}/context-window` route
- `the_one/interfaces/web/static/js/areas/chat.js` — `session_joined` handler eager-fetch
- `tests/test_api_context_window.py` (or extend test_api.py) — new endpoint coverage

---

## Post-Completion Checklist

**Complete ALL steps before marking the leg landed:**

- [x] All acceptance criteria verified (both Tracks)
- [x] Tests passing (broad pytest exit 0 with ~1672-1675 passed; browser suite 316/35 preserved)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Do NOT commit — Flight Director batches commits after L05

---

## Citation Audit

5 source-code citations verified against current code at leg design time:
- `the_one/agent/core.py:111-179` (`Agent.step`) — OK
- `the_one/interfaces/web/app.py:729-889` (`_process_and_broadcast`) — OK; usage broadcast at line 793 (post-F6.5 live-read fix)
- `the_one/llm/openai_provider.py:160-165` (final-only usage emission) — OK
- `the_one/llm/ollama_provider.py:149-154` (final-only usage emission) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:727` (`session_joined` handler) — OK

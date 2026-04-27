# Leg: 04-streaming-infrastructure

**Status**: completed
**Flight**: [Chat Restructure — Components, Streaming & Markdown](../flight.md)

## Objective

Add a streaming path through the LLM stack: `LLMProvider.stream(...)` on the base class with a working default implementation; native streaming on all four providers (Anthropic, OpenAI, Ollama, Mock); a new `ollama_api.chat_stream` SSE helper; an `on_chunk` callback parameter on `Agent.step` so chunks fan out to the broadcaster; and a refactored `_process_and_broadcast` that broadcasts `assistant_chunk` events live, accumulates server-side, persists the synthesized assistant Message to session history, and continues to handle tool calls + usage events on the final chunk. Client-side rendering stays a leg-05 concern; this leg only wires the WS event reception (no rendering).

## Context

- F4 design decision (flight.md "Design Decisions"): streaming is OPTIONAL on the base class — a default implementation calls `complete()` and yields one final `StreamChunk`, forward-compat for any future provider that doesn't override.
- F4 design decision: WS contract = chunks-only-no-final-assistant. Persistence contract = final-assistant-synthesized-server-side. The synthesized assistant event is **NOT broadcast** over the WS — the client already has the accumulated text from the chunk stream — but it IS added to session history via `session.add_event(...)` and to the HTTP API's `result_messages` list.
- F4 design decision: Anthropic's streaming path MUST port the F3 `BadRequestError` temperature-retry (`anthropic_provider.py:48-57`) — newer Claude models reject `temperature` on streaming the same way they do on `complete`. An explicit unit test for the streaming-path retry is required.
- F4 design decision: Ollama has **no existing chat_stream helper** — `ollama_api.py:135` only streams `pull_model` (model-pull progress). New work: `ollama_api.chat_stream(provider_url, body) → AsyncIterator[dict]` mirroring the `pull_model` SSE-parse pattern.
- F4 design decision: OpenAI streaming MUST pass `stream_options={"include_usage": True}` so the final chunk carries `usage` for the telemetry overlay (current F4 telemetry path depends on it).
- F4 design decision: Mock provider gets a new `stream_chunks: list[str]` config (default `[]` → falls back to default-impl behaviour). When set, `stream()` yields each chunk with the existing `delay_ms` between chunks. Deterministic E2E coverage of the streaming path.
- F4 design decision: tool-call interleaving — tool calls remain non-streamed. Streaming is purely for assistant content. An assistant message that emits text + then a tool_call: text streams chunk-by-chunk → final chunk carries the `tool_calls` (alongside `is_final=True`) → existing tool-execution path fires AFTER the text stream completes. The F3 try/except wrapper in `_process_and_broadcast` continues to wrap the streaming iterator path identically.
- **Architectural note**: `_process_and_broadcast` doesn't call `provider.complete()` directly today — it calls `session.agent.step(user_input)` which is an async iterator that yields Messages. The agent's `step` method (`agent/core.py:32-84`) internally calls `self.llm.complete(...)` per agent iteration. The streaming refactor keeps `Agent.step` Message-yielding contract intact and uses an `on_chunk` callback parameter to fan chunks out to the broadcaster — this preserves the agent-loop semantics (continue-signal, max-iterations, tool-execution loop, direct-action shortcut) without duplicating logic in `_process_and_broadcast`.
- All F1-F3 + F4 legs 01-03 tests pass: 393 unit + 117 browser (32 baseline + 85 markdown).
- The `MockProvider` stays gated by `THE_ONE_DEV_MODE` at the API layer — this leg doesn't change that gate.

## Inputs

- `the_one/llm/base.py` (93 LOC) — has `LLMProvider.complete()`, `Message`, `ToolCall`, `ToolResult`, `TokenUsage`, `Role`. No streaming primitives.
- `the_one/llm/anthropic_provider.py` (110 LOC) — `complete()` with F3 BadRequestError retry at lines 48-57.
- `the_one/llm/openai_provider.py` (87 LOC) — `complete()`. Uses `await self.client.chat.completions.create(...)`.
- `the_one/llm/ollama_provider.py` (114 LOC) — `complete()` via `httpx.AsyncClient.post(...)` to `/v1/chat/completions` with `stream: False`.
- `the_one/llm/ollama_api.py` (233 LOC) — has `pull_model` SSE-stream helper at line 135; mirrors httpx `client.stream("POST", url, json=body)` + `async for line in resp.aiter_lines()`.
- `the_one/llm/mock.py` (75 LOC) — `complete()` with optional `delay_ms` config.
- `the_one/agent/core.py` (104 LOC) — `Agent.step(user_input)` is the async iterator that yields Messages; internally calls `await self.llm.complete(...)` at line 54 inside the per-iteration loop.
- `the_one/interfaces/web/app.py` (762 LOC) — `_process_and_broadcast` at line 393-482 consumes `agent.step(...)` and broadcasts WS events: `user`, `usage`, `assistant`, `tool_call`, `tool_result`, `system` (error), `done`.
- `static/js/areas/chat.js` (post-leg-02, ~440-450 LOC) — receives WS events at the `ws.onmessage` switch; needs to add `assistant_chunk` case (no-op or minimal handler in this leg; rendering wire-up is leg 05).
- `tests/browser/conftest.py` — provides `app_clean`, `app_with_provider`, `app_with_agent`. The seeders configure mock providers; mock-provider config is forwarded into `MockProvider(config={...})`.

## Outputs

### `the_one/llm/base.py`

- New `StreamChunk` dataclass:
  ```python
  @dataclass
  class StreamChunk:
      content: str = ""               # NEW tokens since the last chunk; delta semantics, NOT cumulative
      is_final: bool = False           # True only on the final chunk
      tool_calls: list[ToolCall] = field(default_factory=list)  # set on final chunk for non-content completions
      usage: TokenUsage | None = None  # set on final chunk where the provider exposes it
      message: Message | None = None   # set on final chunk; the synthesized Message used by the agent for accumulation
  ```
- New `LLMProvider.stream` method on the base class with a default implementation:
  ```python
  async def stream(
      self,
      messages: list[Message],
      tools: list[dict[str, Any]] | None = None,
      temperature: float = 0.0,
      max_tokens: int = 16384,
  ) -> AsyncIterator[StreamChunk]:
      """Default streaming implementation: call `complete()`, yield one final chunk.

      Providers SHOULD override with native streaming for better UX.
      Forward-compat for any future provider that doesn't natively stream.
      """
      msg = await self.complete(messages, tools, temperature, max_tokens)
      yield StreamChunk(
          content=msg.content,
          is_final=True,
          tool_calls=msg.tool_calls,
          usage=msg.usage,
          message=msg,
      )
  ```
- Note: `stream` is NOT abstract — it has a working default. Subclasses override for native streaming.

### `the_one/llm/anthropic_provider.py`

- New `stream(...)` method using `client.messages.stream(...)`. Yields chunks per `text_stream` deltas (delta semantics — each yielded chunk is NEW tokens, not cumulative). On final `MessageStopEvent`, captures `usage` and synthesizes the final `Message` with accumulated text + tool_calls + usage; yields the final `StreamChunk(is_final=True, message=...)`.
- **PORT THE F3 `BadRequestError` RETRY**: catch `anthropic.BadRequestError` on the streaming call; if message contains "temperature", retry once without the `temperature` kwarg. Same heuristic as `anthropic_provider.py:48-57` for `complete()`. Refactor: extract a small `_strip_temperature_on_retry(kwargs, exc)` helper that both `complete()` and `stream()` call — DRY the retry.
- Tool-call handling: Anthropic streaming yields `text_stream` for the text portion AND raises `tool_use` blocks via the iterator's `current_message_snapshot`. On final, walk `final_message.content` blocks to extract tool_calls (same as `complete()` does at lines 60-67).

### `the_one/llm/openai_provider.py`

- New `stream(...)` method using `client.chat.completions.create(stream=True, stream_options={"include_usage": True}, ...)`. The async-iterator yields `ChatCompletionChunk` objects. Per chunk, `chunk.choices[0].delta.content` is the text delta (or None if the chunk is metadata-only). The final chunk has empty choices and a `usage` field (because of `stream_options`).
- Tool-call handling: tool-call chunks arrive as `delta.tool_calls` with index-aligned partial JSON. Accumulate by index; on final, parse the accumulated JSON and emit ToolCall objects.
- Final chunk: yield `StreamChunk(is_final=True, content="", message=Message.assistant(...), usage=..., tool_calls=...)`.

### `the_one/llm/ollama_api.py`

- New `chat_stream(provider_url, body) → AsyncIterator[dict]` helper. Structurally analogous to `pull_model` at lines 135-159 (both use `httpx.AsyncClient.stream()` + `aiter_lines()`), but the **wire format differs**: `pull_model` consumes `/api/pull` which emits **JSONL** (one JSON object per line, no `data:` prefix); `chat_stream` consumes `/v1/chat/completions` which emits **true SSE** (`data: {...}` lines + `data: [DONE]` terminator). The new helper handles SSE specifically. Concretely:
  ```python
  async def chat_stream(provider_url: str, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
      """Stream `/v1/chat/completions` SSE chunks from an OpenAI-compatible Ollama endpoint.

      Yields parsed JSON dicts for each `data: {...}` line. Stops on `data: [DONE]`.
      """
      url = ensure_v1(provider_url)
      try:
          async with httpx.AsyncClient(timeout=600) as client:
              async with client.stream(
                  "POST", f"{url}/chat/completions", json={**body, "stream": True}
              ) as resp:
                  resp.raise_for_status()
                  async for raw_line in resp.aiter_lines():
                      if not raw_line:
                          continue
                      if not raw_line.startswith("data:"):
                          continue
                      payload = raw_line[len("data:"):].strip()
                      if payload == "[DONE]":
                          return
                      try:
                          yield json.loads(payload)
                      except ValueError:
                          continue
      except httpx.ConnectError as exc:
          raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
      except httpx.TimeoutException as exc:
          raise ConnectionError(f"Timeout streaming from Ollama at {url}: {exc}") from exc
  ```
- Module already exports `AsyncIterator` (line 12). Tests for this helper use a fixture-recorded SSE stream OR a small fake httpx server.

### `the_one/llm/ollama_provider.py`

- New `stream(...)` method consuming `ollama_api.chat_stream(...)`. Per yielded SSE dict, extract `choices[0].delta.content` (text delta) and accumulate. On the final chunk that lacks `delta.content` and (optionally) carries `usage`, yield the final `StreamChunk(is_final=True, ...)`.
- Tool-call handling: same accumulate-by-index pattern as OpenAI (since the Ollama OpenAI-compatible endpoint yields the same shape).

### `the_one/llm/mock.py`

- New `stream(...)` method:
  - If `self.config.get("stream_chunks")` is truthy (a non-empty list), yield each chunk with the existing `delay_ms` between chunks; the FINAL chunk carries the synthesized `Message` (accumulated content from all chunks + the configured `tool_calls` if any) + `is_final=True`.
  - If `stream_chunks` is unset or empty, fall back to default-impl behaviour by **calling `self.complete(...)` directly and yielding one final chunk** (the explicit form below). This is preferred over `async for chunk in super().stream(...): yield chunk` for clarity — no async-generator delegation overhead, code mirrors the base class's default impl.
- Concrete shape:
  ```python
  async def stream(self, messages, tools=None, temperature=0.0, max_tokens=16384):
      stream_chunks = self.config.get("stream_chunks") or []
      if not stream_chunks:
          # Default-impl path: one chunk = full content (mirrors complete()).
          msg = await self.complete(messages, tools, temperature, max_tokens)
          yield StreamChunk(content=msg.content, is_final=True, tool_calls=msg.tool_calls, usage=msg.usage, message=msg)
          return

      delay_ms = self.config.get("delay_ms", 0)
      response = self.config.get("response", _DEFAULT_RESPONSE)
      tool_calls = [
          ToolCall(id=tc["id"], name=tc["name"], arguments=tc.get("arguments", {}))
          for tc in response.get("tool_calls", [])
      ]
      accumulated = ""
      for i, chunk_text in enumerate(stream_chunks):
          if delay_ms and i > 0:
              await asyncio.sleep(delay_ms / 1000)
          accumulated += chunk_text
          yield StreamChunk(content=chunk_text, is_final=False)
      # Final chunk — synthesize the Message
      msg = Message.assistant(
          content=accumulated,
          tool_calls=tool_calls,
          usage=TokenUsage(input_tokens=0, output_tokens=len(accumulated.split())),
      )
      yield StreamChunk(content="", is_final=True, tool_calls=tool_calls, usage=msg.usage, message=msg)
  ```

### `the_one/agent/core.py`

- `Agent.step` signature gains an optional `on_chunk` callback parameter:
  ```python
  async def step(
      self,
      user_input: str,
      on_chunk: Callable[[str], Awaitable[None]] | None = None,
  ) -> AsyncIterator[Message]:
  ```
- Inside the per-iteration loop (replacing `response = await self.llm.complete(...)` at line 54):
  ```python
  accumulated_text = ""
  final_chunk = None
  async for chunk in self.llm.stream(messages=self.messages, tools=self._tool_schemas() or None):
      if chunk.content:
          accumulated_text += chunk.content
          if on_chunk:
              await on_chunk(chunk.content)
      if chunk.is_final:
          final_chunk = chunk
          break

  # Synthesize the response Message — prefer the provider's synthesized Message
  # if available; otherwise build it from accumulated state.
  if final_chunk and final_chunk.message:
      response = final_chunk.message
  else:
      response = Message.assistant(
          content=accumulated_text,
          tool_calls=(final_chunk.tool_calls if final_chunk else []),
          usage=(final_chunk.usage if final_chunk else None),
      )
  self.messages.append(response)
  yield response
  ```
- Direct-action shortcut path (lines 40-51) is unchanged — direct actions don't go through the LLM, so no streaming concern.
- Tool-execution loop after the assistant Message yield is unchanged — tool calls are non-streamed per the F4 design.
- The `on_chunk` callback IS NOT invoked for the synthesized final-Message yield. Chunks fan out via the callback during streaming; the Message yield via `yield response` continues to flow up to `_process_and_broadcast` for usage/tool_call/persistence handling.

### `the_one/interfaces/web/app.py`

- `_process_and_broadcast` gains a small change at the agent-step call site. Define a local async chunk-broadcaster:
  ```python
  async def _broadcast_chunk(content: str) -> None:
      await _send_to_session(session, {"type": "assistant_chunk", "content": content})
  ```
- Pass it to `agent.step`:
  ```python
  async for msg in session.agent.step(user_input, on_chunk=_broadcast_chunk):
      ...
  ```
- Inside the existing assistant-Message handler (lines 416-447):
  - **REMOVE** the `await _send_to_session(session, event)` for the `{"type": "assistant", "content": msg.content}` event at line 433. (The client already has the text via the chunk stream.)
  - **KEEP** the `session.add_event(event)` at line 432 — persistence contract requires the final assistant event in session history.
  - **KEEP** the `result_messages.append(entry)` at line 447 — HTTP API caller depends on it.
  - **KEEP** the usage broadcast (lines 421-428) — telemetry overlay updates at end-of-stream.
  - **KEEP** the tool_call broadcast (lines 434-438) — tool calls are non-streamed; the existing path is correct.
- The F3 try/except wrapper (lines 414-473) continues to wrap the agent-step call. Any exception during streaming emits the F3-introduced system error + `done`.
- The `_send_to_session({"type": "done"})` at line 481 stays as-is.

### `static/js/areas/chat.js`

- Add an `assistant_chunk` case to the `ws.onmessage` switch. **Leg 04 wire-up is minimal**: simply consume the event without rendering. A `// no-op — leg 05 wires the rendering path` comment is acceptable. Actual chunk rendering lands in leg 05. The reason for adding the case in leg 04: without it, an unrecognized event would fall through silently, but the client also wouldn't drop its "thinking…" indicator on first chunk. So the leg-04 minimal wire-up is:
  ```js
  else if (data.type === 'assistant_chunk') {
    // Hide the thinking indicator on first chunk arrival; rendering wire-up lives in leg 05.
    hideThinking();
  }
  ```
- This keeps the chunk path observably correct (thinking indicator clears on first chunk for streaming providers; the synthesized assistant `done` event still re-enables the input + telemetry). Leg 05 will replace the no-op body with actual streaming-bubble rendering.
- **All other ws.onmessage cases are unchanged.** The current `assistant` case is REMOVED in this leg's app.py change (no `assistant` events broadcast from streaming); but leaving the case in chat.js is harmless and forward-compat for any non-streaming surface (e.g., session-restore — where historical assistant events DO need to render via the existing `addMsg` path). Verify the case logic still applies to session-restored assistant events: when a session is rejoined, the historical events are sent as part of `session_joined.history` (app.py separate path at the join handler) — that history rendering goes through `renderHistory(...)` in chat.js (calls `addMsg` per event); it does NOT go through the live `assistant` WS event. So removing the `assistant_chunk`-only-server-side broadcast does not break history rendering.

### Tests

#### Server-side unit tests

New file `tests/test_streaming.py` (or extend an existing test file — designer's choice). Cases:

1. **StreamChunk default values** — `StreamChunk()` has empty content, is_final=False, empty tool_calls, None usage, None message.
2. **Base class default `stream()`** — define a minimal `LLMProvider` subclass with only `complete()`; call `stream(...)`; assert exactly one chunk emitted with `is_final=True` and message populated.
3. **Mock provider streaming with `stream_chunks`** — config `stream_chunks=["Hello, ", "world", "!"]`, `delay_ms=0`; collect chunks; assert 4 chunks total (3 content + 1 final); assert final chunk's message content is "Hello, world!".
4. **Mock provider falls back to default `stream` when `stream_chunks` is unset** — config without `stream_chunks`; collect chunks; assert exactly 1 chunk emitted, `is_final=True`, content matches default response.
5. **Anthropic streaming-path BadRequestError retry** — mock the `client.messages.stream` to raise `BadRequestError("temperature: ... rejected")` on first call and succeed on second (without `temperature` in kwargs); assert the retry happens and the streaming iterator yields chunks normally.
6. **Agent.step uses streaming** — instantiate an `Agent` with a mock LLM that has `stream_chunks=["a", "b"]`; collect Messages from `step("hi")`; assert exactly 1 Message yielded (the synthesized final), with `content="ab"`.
7. **Agent.step calls `on_chunk` callback per chunk** — same setup; pass `on_chunk = lambda c: callbacks.append(c)`; assert callbacks list is `["a", "b"]`.
8. **`ollama_api.chat_stream` parses SSE correctly** — fake an httpx response stream with `"data: {...}\n\n"` lines and `"data: [DONE]\n\n"`; assert each yielded dict matches the parsed JSON.
9. **Multi-iteration agent loop preserves `chunks_seen` correctly across tool-call boundaries** — the most subtle invariant. Use a mock provider that streams chunks AND returns a tool call; ensure iteration 2 (after tool execution) ALSO sees `chunks_seen` reset properly. Specifically: configure mock with `stream_chunks=["a", "b"]` AND a tool_call in `response`; agent step iterates twice; spy on `_send_to_session` to verify `assistant_chunk` events on iteration 1 BUT NO `assistant` event on iteration 1 (because chunks_seen=True), AND the same chunks-only pattern on iteration 2 (because chunks_seen was correctly reset between iterations).

Total: ~7-9 new unit tests. Update unit-test count from 393 to ~400-402.

#### Browser tests

New file `tests/browser/test_flow_streaming.py`. Cases:

1. **Streaming chunk events arrive in order** — seed an agent with mock provider configured `stream_chunks=["Hello, ", "world", "!"]` + `delay_ms=200`; send a message; collect WS events via a Playwright route or by reading `console` output (chat.js could log chunks for debugging — OR the test inspects the DOM after `done` and infers chunk order from the rendered text). The simpler test: send the message; wait for `done`; assert the assistant text in the DOM equals `"Hello, world!"`. (The order assertion is left to the unit-test layer; the browser test confirms end-to-end correctness.)
2. **Session rejoin renders the synthesized assistant text** — send a message via the streaming path; wait for `done`; refresh the page (or rejoin via the session-list click); assert the assistant message renders with the accumulated text. This validates the persistence contract — `session.add_event` was called server-side with the accumulated text, so the rejoined session's history includes it.

Total: 2 new browser tests. Update browser-test count from 117 to 119.

**Note about leg 05's tests**: Leg 05 will add more browser tests (markdown-on-done rendering, currentStreamingMsg accumulation). Leg 04's job is just the streaming-infrastructure-correctness tests.

### `the_one/agents.md`

- Add a "Streaming protocol" subsection. Suggested placement: alongside the new "Markdown rendering" section. Content:
  - `LLMProvider.stream(...)` API
  - `StreamChunk` shape (content delta semantics, is_final, tool_calls/usage/message on final)
  - Default-impl behaviour for non-overriding providers
  - WS event vocabulary: `assistant_chunk` (chunks-only) vs `assistant` (legacy non-streaming — only used for direct-action shortcut path which doesn't stream); chunks-vs-final semantics
  - Persistence contract: synthesized assistant event added to session history server-side; NOT broadcast over WS
  - Agent.step `on_chunk` callback contract
  - Per-provider streaming notes (Anthropic uses `messages.stream`; OpenAI requires `stream_options={"include_usage": True}`; Ollama uses the new `chat_stream` SSE helper; Mock honours `stream_chunks: list[str]` config)
  - The F3 BadRequestError temperature-retry is ported into the Anthropic streaming path

### `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md`

- Append a `### streaming-infrastructure` block under `## Leg Progress` summarising the work, file deltas, test counts, deviations.

## Acceptance Criteria

- [x] `LLMProvider.stream(...)` exists on the base class with a working default implementation. `StreamChunk` dataclass exists.
- [x] All four providers (Anthropic, OpenAI, Ollama, Mock) implement native `stream(...)` methods.
- [x] `ollama_api.chat_stream(provider_url, body) → AsyncIterator[dict]` exists, mirrors the `pull_model` SSE-parse pattern.
- [x] Anthropic streaming path ports the F3 `BadRequestError` temperature-retry. Verified by an explicit unit test.
- [x] OpenAI streaming passes `stream_options={"include_usage": True}` so the final chunk carries usage.
- [x] Mock provider's `stream(...)` honours the new `stream_chunks: list[str]` config; falls back to default-impl behaviour when `stream_chunks` is unset/empty.
- [x] `Agent.step` accepts an optional `on_chunk: Callable[[str], Awaitable[None]] | None` parameter and calls it per chunk during streaming. Existing Message-yielding contract is unchanged for callers that don't pass `on_chunk`.
- [x] `_process_and_broadcast` passes a chunk-broadcaster callback to `agent.step` and broadcasts `{"type": "assistant_chunk", "content": chunk}` per chunk. The synthesized assistant Message is **NOT broadcast** as `{"type": "assistant", ...}` (chunk path replaces it) but IS persisted via `session.add_event` and IS appended to `result_messages`.
- [x] `chat.js` handles the `assistant_chunk` WS event with at minimum a no-op (and clearing the thinking indicator on first chunk).
- [x] `pytest --timeout=60 tests/` passes. Count grows from 393 to ~400-402 (the exact new count documented in flight log; the new tests are in `tests/test_streaming.py` or equivalent, including the multi-iteration `chunks_seen` invariant test).
- [x] `pytest --timeout=120 -m browser tests/browser/` passes. Count grows from 117 to 119 (2 new tests in `test_flow_streaming.py`).
- [x] All existing 117 browser tests continue to pass — the new event vocabulary doesn't break the existing chat flow tests because the mock provider without `stream_chunks` falls back to default-impl behaviour (one chunk = entire content) which produces the same observable end state as the previous `assistant` event path (text rendered + thinking cleared + done).
- [x] All existing 393 unit tests continue to pass — `Agent.step` without `on_chunk` retains its original Message-yielding semantics; tests that mock `LLMProvider.complete` continue to work because the default `stream` calls `complete`.
- [x] `the_one/agents.md` contains a "Streaming protocol" subsection documenting the API, WS contract, persistence contract, per-provider notes, and the BadRequestError retry port.
- [x] No new external dependencies introduced (`pyproject.toml` unchanged).

## Verification Steps

- `grep -E 'def stream\b' the_one/llm/{base,anthropic_provider,openai_provider,ollama_provider,mock}.py` returns 5 hits (one per file).
- `grep -E 'def chat_stream\b' the_one/llm/ollama_api.py` returns 1 hit.
- `grep -E 'StreamChunk' the_one/llm/base.py` returns ≥ 1 hit (the dataclass definition).
- `grep -n 'on_chunk' the_one/agent/core.py` returns hits for the parameter signature + the per-chunk invocation.
- `grep -n 'assistant_chunk' the_one/interfaces/web/app.py the_one/interfaces/web/static/js/areas/chat.js` returns hits in both files.
- `grep -E 'await _send_to_session\(session, event\)' the_one/interfaces/web/app.py` — the `assistant` event broadcast at the old line 433 is REMOVED. The `session.add_event(event)` at the old line 432 stays.
- `grep -E 'stream_options.*include_usage' the_one/llm/openai_provider.py` returns 1 hit.
- Tests: `pytest --timeout=60 tests/` passes; `pytest --timeout=120 -m browser tests/browser/` passes. Counts documented in flight log.
- Manual smoke (Flight Director or human): start the dev server, configure a mock provider with `stream_chunks: ["Hello, ", "world", "!"]` + `delay_ms: 200`, send a message, observe chunk-by-chunk text appearing (since chat.js leg-04 is no-op rendering, the text won't visibly stream — but `done` should re-enable the input and telemetry should update). Leg 05 will make the streaming visually observable.

## Implementation Guidance

### Order of operations

1. **Base class first** — add `StreamChunk` + default `stream()` method to `base.py`. Run unit tests; default-impl path is now exercisable.
2. **Mock provider** — implement `stream()` with `stream_chunks` config. Add unit tests for both branches (empty config = default-impl; populated = chunk-by-chunk). This sets up the test fixture for the subsequent providers.
3. **Agent.step refactor** — update to use `self.llm.stream(...)` with `on_chunk` callback. Run all existing 393 unit tests — they should still pass because callers that don't pass `on_chunk` get identical Message-yielding behaviour.
4. **`_process_and_broadcast` refactor** — add the `_broadcast_chunk` callback, remove the `assistant`-event broadcast, keep persistence + tool-call + usage paths. Run existing 117 browser tests — they should still pass because the mock-provider-without-`stream_chunks` path produces a single chunk = entire content, which renders as one accumulated chunk on the client (and chat.js leg-04 no-op handler only clears thinking indicator). Wait — this means the **existing browser tests will fail** because they expect the `[data-testid="message"].assistant` element to render with the assistant text, but with leg-04's no-op `assistant_chunk` handler, the assistant text is not rendered until leg 05.
   - **Resolution**: leg 04 cannot fully remove the `assistant` event broadcast without breaking the existing browser tests. Two options:
     - **(A) Leg-04 keeps a fallback `assistant` event broadcast for the default-impl path** (single-chunk providers): when the agent's stream yields exactly one chunk and that chunk is the final, fall through to the existing `assistant` event broadcast. When the agent's stream yields multiple chunks (real streaming), broadcast `assistant_chunk` events and skip the `assistant` event. **This breaks the F4 design's "WS contract = chunks-only-no-final-assistant" cleanly** for default-impl providers.
     - **(B) Leg-04 ALSO updates chat.js to render chunks** (a minimal version of leg 05's wire-up). The leg-04 chat.js handler accumulates `assistant_chunk` content into a `currentStreamingMsg` element rendered via `addMsg('assistant', '', attribution)` and then mutating its `textContent`. On `done`, set `currentStreamingMsg = null`. NO markdown rendering (that's leg 05). This expands leg-04's scope but keeps the F4 design clean.
   - **Recommendation: (B)**. Pulling minimal chunk rendering forward into leg 04 keeps the design clean (chunks-only WS contract holds for ALL providers including default-impl) and means leg 04 ships a streaming-functional system end-to-end. Leg 05 then layers markdown ON TOP of the already-working chunk path. **The leg's Outputs section documents this expansion.** See "Acceptable variations" / "Adaptation Criteria" in flight.md — chunk rendering is a wire-up choice, and pulling it forward is well within scope.
5. **Implement the three real providers** — Anthropic, OpenAI, Ollama — in order. Each gets its own unit test. Anthropic gets the additional BadRequestError retry test.
6. **Browser tests** — write `tests/browser/test_flow_streaming.py`. With the leg-04 chunk-rendering wire-up (option B), the test can assert chunk-by-chunk rendering AND the final accumulated text in the DOM.
7. **Agents.md update** — final, after the implementation is verified.

### Revised chat.js wire-up (per recommendation B)

Replace the leg-04 minimal handler with:

```js
var currentStreamingMsg = null;

else if (data.type === 'assistant_chunk') {
  hideThinking();
  if (!currentStreamingMsg) {
    // Create a fresh assistant bubble; attribution is the current agent name.
    var bubble = App.chat.renderMessage('assistant', '', { renderMarkdown: false });
    messagesEl.appendChild(bubble);
    var side = 'from-agent';
    var attribution = currentAgentName || 'agent';
    messagesEl.appendChild(App.chat.renderAttribution(side, attribution));
    messagesEl.scrollTop = messagesEl.scrollHeight;
    currentStreamingMsg = bubble;
    // Ensure the bubble has a text node child to mutate.
    if (!currentStreamingMsg.firstChild) {
      currentStreamingMsg.appendChild(document.createTextNode(''));
    }
  }
  // Append delta to the bubble's text node.
  currentStreamingMsg.firstChild.nodeValue += data.content;
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
else if (data.type === 'tool_call' || data.type === 'tool_result') {
  // End-of-iteration boundary in the multi-iteration agent loop. Reset the
  // streaming-bubble pointer so iteration N+1's chunks land in a fresh bubble.
  // Note: the existing tool_call / tool_result handlers (renderMessage etc.)
  // continue to run AFTER this reset — augment, don't replace.
  currentStreamingMsg = null;
  // ... existing handler body for tool_call / tool_result ...
}
else if (data.type === 'done') {
  // Reset streaming state (leg 05 will swap to markdown on this event).
  currentStreamingMsg = null;
  hideThinking();
  busy = false;
  if (!sessionBannerEl) sendBtn.disabled = false;
  refreshSessionList();
}
```

The `tool_call` / `tool_result` handler reset is critical for multi-iteration agent loops: when iteration 1 streams text and then emits a tool_call, the assistant bubble for iteration 1 must be "closed" so iteration 2's chunks create a new bubble. Add the `currentStreamingMsg = null` reset to the EXISTING tool_call and tool_result handlers in chat.js — don't replace those handlers' existing logic.

The `assistant` case in the existing onmessage switch becomes unreachable for the streaming WS path — it stays only for any future surface that emits the legacy event (e.g., direct-action shortcut path which doesn't stream). Decision: **keep the `assistant` case in chat.js** for the direct-action path; that path bypasses `agent.llm.stream` (it's the early-return at agent/core.py:50 when a direct-action match fires). For direct-action, `_process_and_broadcast` gets a single Message with no streaming — the `assistant_chunk` path doesn't fire, but the `assistant` event broadcast must STILL happen for direct-action to render. So:

- In `_process_and_broadcast`, distinguish: when the yielded Message came via the streaming path (chunks were broadcast), DON'T broadcast `assistant`; when it came via direct-action (no chunks), DO broadcast `assistant`. Concretely: the assistant Message yielded after a streaming round has no associated "chunks were broadcast" signal — but we can detect it: track whether the chunk-broadcaster was invoked at least once for the current Message. If yes, skip; if no, fall through to the legacy `assistant` event broadcast.

OR simpler: always broadcast `assistant` for direct-action. The direct-action path can be detected by the absence of stream chunks. Track `chunks_seen_for_current_msg: bool` reset on each `agent.step` iteration boundary.

Cleanest implementation:
```python
chunks_seen = False
async def _broadcast_chunk(content: str) -> None:
    nonlocal chunks_seen
    chunks_seen = True
    await _send_to_session(session, {"type": "assistant_chunk", "content": content})

async for msg in session.agent.step(user_input, on_chunk=_broadcast_chunk):
    if msg.role == Role.ASSISTANT:
        # ... existing usage broadcast ...
        if msg.content:
            event = {"type": "assistant", "content": msg.content}
            session.add_event(event)
            if not chunks_seen:
                # Direct-action / non-streaming path — broadcast the legacy event.
                await _send_to_session(session, event)
        # ... tool_call broadcast + result_messages.append ...
        # Reset for next iteration (multi-iteration agent loop). Reset at the END
        # of the assistant block — UNCONDITIONAL — so empty-content tool-call-only
        # responses still reset the flag for the NEXT iteration. (Reset inside the
        # `if msg.content:` would skip the reset on tool-call-only iterations and
        # incorrectly carry chunks_seen=True into iteration N+1.)
        chunks_seen = False
```

This preserves the direct-action path AND the streaming path cleanly. Direct-action: `chunks_seen=False` → legacy `assistant` event broadcasts. Streaming: chunks were broadcast during the stream → `chunks_seen=True` → skip the legacy broadcast (client already has the text). Multi-iteration: reset at the unconditional end of the assistant block guarantees iteration N+1 starts with a clean flag regardless of whether iteration N had content.

### Anthropic streaming details

`anthropic.AsyncMessageStream` is an async context manager:

```python
async with self.client.messages.stream(**kwargs) as stream:
    async for text in stream.text_stream:
        # Each `text` is a NEW token-delta string.
        yield StreamChunk(content=text, is_final=False)
    # After the iterator exhausts, get the final message.
    final = await stream.get_final_message()

# Build tool_calls from final.content blocks
tool_calls = []
content = ""
for block in final.content:
    if block.type == "text":
        content += block.text
    elif block.type == "tool_use":
        tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

usage = TokenUsage(input_tokens=final.usage.input_tokens, output_tokens=final.usage.output_tokens) if final.usage else None
msg = Message.assistant(content=content, tool_calls=tool_calls, usage=usage)
yield StreamChunk(content="", is_final=True, tool_calls=tool_calls, usage=usage, message=msg)
```

For the BadRequestError retry: wrap the `async with self.client.messages.stream(...)` call in a try/except. On `BadRequestError` with "temperature" in the message, pop `temperature` and retry. **Critical**: the retry-once-without-temperature pattern must work inside an `async generator` — the `try/except` goes around the entire `async with` block; on retry, the second attempt re-enters the `async with` and re-runs the streaming loop. Test this carefully — async-generator semantics around exceptions can be tricky.

Suggested skeleton:

```python
async def stream(self, messages, tools=None, temperature=0.0, max_tokens=16384):
    # Build kwargs as in complete()
    kwargs = self._build_kwargs(messages, tools, temperature, max_tokens)
    yielded_any = False
    try:
        async for chunk in self._stream_inner(kwargs):
            yielded_any = True
            yield chunk
    except anthropic.BadRequestError as exc:
        # Retry-without-temperature is only safe BEFORE any chunk has yielded.
        # Post-yield retries would emit duplicate content to the consumer.
        if not yielded_any and "temperature" in str(exc).lower():
            kwargs.pop("temperature", None)
            async for chunk in self._stream_inner(kwargs):
                yield chunk
        else:
            raise

async def _stream_inner(self, kwargs):
    async with self.client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield StreamChunk(content=text, is_final=False)
        final = await stream.get_final_message()
    # ... build tool_calls, usage, msg ...
    yield StreamChunk(content="", is_final=True, tool_calls=tool_calls, usage=usage, message=msg)
```

The `try/except` AROUND the inner async-for handles the BadRequestError. The `yielded_any` guard ensures retry only runs when no chunks have been emitted yet — Anthropic's `BadRequestError` for unsupported params is raised on request submission (before any text deltas), so the common case retries cleanly; the guard is defence-in-depth against any post-yield raise. If the retry also fails (or the guard prevents retry), the exception propagates up and `_process_and_broadcast`'s F3 try/except catches it.

### OpenAI streaming details

```python
api_messages = [self._to_api_message(m) for m in messages]
kwargs = {
    "model": self.model,
    "messages": api_messages,
    "temperature": temperature,
    "max_tokens": max_tokens,
    "stream": True,
    "stream_options": {"include_usage": True},
}
if tools:
    kwargs["tools"] = [self.tool_schema(t) for t in tools]

stream = await self.client.chat.completions.create(**kwargs)

content = ""
tool_calls_acc = {}  # index → partial dict
usage = None

async for chunk in stream:
    if not chunk.choices:
        # Final metadata-only chunk with usage
        if chunk.usage:
            usage = TokenUsage(input_tokens=chunk.usage.prompt_tokens, output_tokens=chunk.usage.completion_tokens)
        continue
    delta = chunk.choices[0].delta
    if delta.content:
        content += delta.content
        yield StreamChunk(content=delta.content, is_final=False)
    if delta.tool_calls:
        for tc_delta in delta.tool_calls:
            idx = tc_delta.index
            entry = tool_calls_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            if tc_delta.id:
                entry["id"] = tc_delta.id
            if tc_delta.function:
                if tc_delta.function.name:
                    entry["name"] = tc_delta.function.name
                if tc_delta.function.arguments:
                    entry["arguments"] += tc_delta.function.arguments

tool_calls = []
for idx in sorted(tool_calls_acc.keys()):
    e = tool_calls_acc[idx]
    try:
        args = json.loads(e["arguments"]) if e["arguments"] else {}
    except json.JSONDecodeError:
        args = {}
    tool_calls.append(ToolCall(id=e["id"] or e["name"], name=e["name"], arguments=args))

msg = Message.assistant(content=content, tool_calls=tool_calls, usage=usage)
yield StreamChunk(content="", is_final=True, tool_calls=tool_calls, usage=usage, message=msg)
```

### Ollama streaming details

Same shape as OpenAI but consumes `ollama_api.chat_stream(...)` (which returns parsed dicts, not openai SDK objects):

```python
api_messages = [self._to_api_message(m) for m in messages]
body = {"model": self.model, "messages": api_messages, "temperature": temperature, "max_tokens": max_tokens}
if tools:
    body["tools"] = [self.tool_schema(t) for t in tools]

content = ""
tool_calls_acc = {}
usage = None

async for chunk_dict in ollama_api.chat_stream(self.base_url, body):
    choices = chunk_dict.get("choices") or []
    if not choices:
        if "usage" in chunk_dict:
            u = chunk_dict["usage"]
            usage = TokenUsage(input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0))
        continue
    delta = choices[0].get("delta", {})
    text = delta.get("content")
    if text:
        content += text
        yield StreamChunk(content=text, is_final=False)
    # tool_calls accumulation — same pattern as OpenAI
    for tc_delta in delta.get("tool_calls", []):
        idx = tc_delta.get("index", 0)
        entry = tool_calls_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if tc_delta.get("id"):
            entry["id"] = tc_delta["id"]
        fn = tc_delta.get("function", {})
        if fn.get("name"):
            entry["name"] = fn["name"]
        if fn.get("arguments") is not None:
            args = fn["arguments"]
            if isinstance(args, str):
                entry["arguments"] += args

# Build tool_calls + final chunk same as OpenAI
```

Consider extracting the OpenAI-shape tool-call accumulator into a small helper since OpenAI and Ollama use identical shapes.

### `Awaitable` import for `Agent.step`

Add to `the_one/agent/core.py` imports:
```python
from collections.abc import Awaitable, Callable
```

The existing `from typing import AsyncIterator` stays.

## Edge Cases

- **Empty stream from a real provider**: a provider that yields zero content chunks but yields a final chunk with empty content → agent.step yields an empty assistant Message; `_process_and_broadcast` skips the assistant-event broadcast (no content, no tool_calls — `if msg.content:` is False), the `done` event still fires. The client's thinking indicator was never cleared (no chunks seen). Document: this is acceptable — the provider behaved oddly but the system doesn't crash; the user sees "thinking…" forever until the client times out the WS or the user navigates away. Edge case not worth fixing in v1.
- **A chunk with `is_final=True` AND `content` non-empty**: the agent's loop accumulates the content, then on `is_final` breaks out. The `on_chunk` callback IS invoked for that final chunk's content. Document — the final chunk MAY contain a final delta for providers that emit content on the stop event.
- **A provider's `stream()` raises mid-iteration**: the F3 try/except at `_process_and_broadcast` lines 414-473 catches it. The user sees "Agent error: ..." system message + done. Existing F3 behaviour preserved.
- **Mock provider with `stream_chunks=[]` (explicit empty list)**: same as unset — falls back to default-impl `complete()`-then-yield-one-chunk path. The leg's Mock implementation handles this with `if not stream_chunks:`.
- **Mock provider with `stream_chunks` set + `response.tool_calls` non-empty**: the streamed text path runs, then the final chunk includes the tool_calls. The agent's tool-execution loop fires after the assistant Message yields. Tool calls are non-streamed by design.
- **Agent's max_iterations loop with streaming**: each iteration runs a full stream; `on_chunk` callback fires for each iteration's chunks. This means a 5-iteration agent sees 5 separate streaming runs — chunk-broadcaster fires for each. Multiple `currentStreamingMsg` bubbles need to be created (one per iteration). The leg-04 chat.js wire-up handles this via `currentStreamingMsg = null` reset on each `done`. **Wait — `done` only fires at the END of the entire agent step, not per LLM iteration.** Multi-iteration agent: chunks arrive across iteration boundaries; the chat.js wire-up needs to reset `currentStreamingMsg` between iterations too. **Solution**: reset `currentStreamingMsg` on the `tool_result` event (which arrives between iterations) — that signals the start of the next assistant iteration. Update the leg-04 chat.js wire-up to also reset on `tool_call` arrival (since tool_call → tool_result → next iteration's chunks). **Or simpler**: the server emits a synthetic `assistant_done` event between iterations — but that's added complexity. Cleanest leg-04 approach: reset `currentStreamingMsg` in the chat.js handler on `tool_call` and `tool_result` events (both signal "this iteration's assistant text is over").
- **Concurrent agent steps** (rare — would only happen if a user double-clicks Send while busy): protected by the existing `busy` flag in chat.js (lines 504-510) and by the agent-step serialization on the server. No new concern.
- **Mock provider's `stream_chunks` containing empty strings**: yielded as zero-length chunks. The `if chunk.content:` check in agent.step skips them. Acceptable — no broadcast, no accumulation.

## Files Affected

- `the_one/llm/base.py` — UPDATED (add `StreamChunk` dataclass + `stream` method with default impl)
- `the_one/llm/anthropic_provider.py` — UPDATED (add `stream` with BadRequestError retry; refactor shared kwargs builder)
- `the_one/llm/openai_provider.py` — UPDATED (add `stream` with `stream_options={"include_usage": True}`)
- `the_one/llm/ollama_api.py` — UPDATED (add `chat_stream` SSE helper)
- `the_one/llm/ollama_provider.py` — UPDATED (add `stream` consuming `chat_stream`)
- `the_one/llm/mock.py` — UPDATED (add `stream` with `stream_chunks` config)
- `the_one/agent/core.py` — UPDATED (`Agent.step` accepts `on_chunk` callback; uses `self.llm.stream` internally)
- `the_one/interfaces/web/app.py` — UPDATED (`_process_and_broadcast` passes chunk-broadcaster; conditional `assistant` event broadcast guarded by `chunks_seen`)
- `the_one/interfaces/web/static/js/areas/chat.js` — UPDATED (add `assistant_chunk` ws.onmessage handler with minimal chunk rendering; reset `currentStreamingMsg` on `tool_call`/`tool_result`/`done`)
- `tests/test_streaming.py` — NEW (or extend existing test file; ~6-8 unit tests)
- `tests/browser/test_flow_streaming.py` — NEW (2 e2e tests)
- `the_one/agents.md` — UPDATED (Streaming protocol subsection)
- `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md` — UPDATED (leg progress entry)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] `pytest --timeout=60 tests/` passes (post-leg count documented; ≥ 393 + new unit tests)
- [x] `pytest --timeout=120 -m browser tests/browser/` passes (post-leg count documented; ≥ 117 + new browser tests = ~119)
- [x] All existing 393 + 117 tests still pass
- [x] Update flight-log.md with leg progress entry under `## Leg Progress` (`### streaming-infrastructure` heading) — document file deltas, exact post-leg test counts, the chat.js wire-up scope decision (option B), any deviations
- [x] Set this leg's status to `landed` (in this file's header) — DO NOT set to `completed` and DO NOT commit; the flight-level review and commit run after the last autonomous leg per `/agentic-workflow`.
- [x] Signal `[HANDOFF:review-needed]`

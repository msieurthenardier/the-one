# Leg: roundtrip-conformance

**Status**: completed
**Flight**: [Cross-Provider Tool-Use Conformance Suite](../flight.md)

## Objective

Build the per-provider scripted-transport harness and the provider-parametrized
`request → tool_call → tool_result → final-answer` round-trip conformance test
across {Anthropic, OpenAI, Ollama, Mock}, asserting the canonical
`Message`/`ToolCall`/`ToolResult` shape is uniform — driven through
`provider.complete()` and `provider.stream()` directly, hermetically, with no
production code changes.

## Context

- **DD1**: conformance is asserted at the `LLMProvider` contract, not through
  `Agent._run_iterations`. The three real providers are driven through scripted
  transports modeled on existing mocked-client patterns; `Mock` is the reference
  end-to-end, **re-configured between turns** because `MockProvider.complete()`
  returns the same `config["response"]` on every call (`mock.py:68`).
- **DD2**: one canonical provider-neutral script — a tool definition, a turn-1
  expectation (a `ToolCall` with known `name` + `arguments`), a synthesized
  `ToolResult`, a turn-2 expectation (final-answer `Message`, no `tool_calls`) —
  run through every provider. Assertions read the **canonical** objects, not wire
  bytes (mirroring `test_llm_provider_cross_provider_history.py`'s structural
  style). **Includes the `tools=None`/`tools=[]` path**: no tools offered → plain
  text round-trip, no `tool_calls`.
- **No hard dependency on leg 01** (`shared-test-fixtures`). The round-trip needs
  only a tool definition + canonical script, **not** the `press_key`/
  `make_bad_request` fixtures (those are consumed by leg 03). This leg runs after
  leg 01 for cleanliness but is not blocked on it. Leg 01 has already landed, so
  `tests/fixtures/tool_schemas.py` exists if useful, but this leg need not import it.
- The sibling test `tests/test_llm_provider_cross_provider_history.py` is the model
  for file shape, provider fixtures, structural assertions, and the live tier
  (extended in leg 04). This leg is its tool-use round-trip counterpart.

### The central harness problem (read before implementing)

Each provider reaches the canonical shape over a different wire dialect, and the
**turn-1-then-turn-2 queue** is achieved differently per provider:

| Provider | complete() seam | stream() seam | Two-turn queue mechanism |
|---|---|---|---|
| **Anthropic** | monkeypatch `prov.client.messages.create` | monkeypatch `prov.client.messages.stream` | **native**: a recorder with `side_effects=[turn1, turn2]` pops per call (`test_anthropic_provider.py:57-80` `_CreateRecorder`; `:344-390` `_StreamRecorder`/`_StreamCM`) |
| **OpenAI** | `httpx.MockTransport` via monkeypatched `httpx.AsyncClient.__init__` | same (SSE body) | **NEW — stateful handler**: same `/chat/completions` path is hit both turns, so the handler must hold a call counter and return turn-1 then turn-2 |
| **Ollama** | `httpx.MockTransport`, handler inspects `request.url.path` (`/api/show` vs `/chat/completions`) (`test_ollama_provider_recovery.py` `_complete_handler`/`_patch_transport`) | monkeypatch `the_one.llm.ollama_api.chat_stream` with an async generator (`_patch_chat_stream`) | **NEW — stateful handler / factory**: count `/chat/completions` calls (or `chat_stream` invocations) to route turn-1 vs turn-2; `/api/show` should return `{"model_info": {}}` for the **context-length resolver** (see note below), NOT for `supports_tools()` |
| **OpenRouter** | inherits OpenAI (subclass) — same MockTransport | same | same as OpenAI (not driven in this leg; leg 03 adds the `anthropic/*` smoke) |
| **Mock** | no transport — `config["response"]` | `config["stream_chunks"]` + `config["response"]` | **re-configure between turns**: turn-1 config carries `response.tool_calls`, turn-2 config carries only `content` (mutate `prov.config` or build a second instance) |

The new harness piece is the **stateful handler** for the OpenAI/Ollama HTTP path:
the existing tests only ever return one response per handler. A round-trip hits the
same endpoint twice, so the handler closure must increment a counter and serve the
turn-1 (tool_call-emitting) body first, then the turn-2 (final-answer) body.

**Ollama `/api/show` is for the context-length resolver, not `supports_tools()`**
(Architect-verified): `OllamaProvider.complete()`/`stream()` call
`_resolve_max_context_tokens_if_needed()` → `_resolve_max_context_tokens()` →
`ollama_api.show_model()` which POSTs `/api/show` on the **native** host
(`strip_v1(base_url)`). `supports_tools()` is **not** called by `complete()`/
`stream()` at all — so the `/api/show` body needs `model_info` (matching
`test_ollama_provider_recovery.py`'s `{"model_info": {}}`), and does **not** need to
advertise tool capability. Moreover `_resolve_max_context_tokens_if_needed()`
(`base.py:281-301`) swallows all exceptions and flips its sentinel, so an unserved
`/api/show` degrades gracefully (falls back to the default window) rather than
breaking the round-trip — but the `MockTransport` intercepts the call anyway, so the
handler should answer it cleanly to stay fully hermetic. Anthropic's
`_resolve_max_context_tokens` is a no-op and OpenAI's is a pure dict lookup — neither
makes a network call, so only Ollama's handler needs the extra path.

### Canonical parse shapes the assertions rely on (provider-verified)

- **Anthropic** builds `ToolCall(id=block.id, name=block.name, arguments=block.input)`
  from a `tool_use` content block (`anthropic_provider.py:193-194`). Stub a
  `tool_use` block via `_StubContentBlock("tool_use", id=..., name=..., input={...})`.
- **OpenAI/OpenRouter** build `ToolCall(id=tc.id, name=tc.function.name,
  arguments=json.loads(tc.function.arguments))` (`openai_provider.py:136-145`).
  The transport JSON needs `choices[0].message.tool_calls[].function.{name,arguments}`
  where `arguments` is a JSON **string**.
- **Ollama** builds from `msg["tool_calls"][].function.{name, arguments}`
  (arguments may be str or dict) (`ollama_provider.py:142-153`); `id` falls back to
  the function name. Non-streaming JSON: `{"choices":[{"message":{...}}], "usage":{...}}`.
- **Streaming** tool-call deltas accumulate provider-agnostically via
  `_StreamAccumulator.feed_tool_call_delta(index, id, name, arguments)` then
  `finalize_tool_calls()`. The final `StreamChunk(is_final=True)` carries `.message`,
  `.tool_calls`, `.usage` — assert on `chunk.message` / `chunk.tool_calls`.

## Inputs

What exists before this leg runs:
- `the_one/llm/base.py` — the `LLMProvider` contract + canonical types (read-only).
- `the_one/llm/{anthropic,openai,ollama,openrouter,mock}_provider.py` — providers
  (read-only; **must not be modified**).
- Existing mock patterns: `tests/test_anthropic_provider.py` (recorder/stub),
  `tests/test_streaming.py` + `tests/test_ollama_provider_recovery.py` +
  `tests/test_openrouter_provider.py` (httpx.MockTransport / chat_stream fakes).
- `tests/test_llm_provider_cross_provider_history.py` — the sibling test (fixtures,
  structural assertions, parametrization, live tier).
- Leg 01 landed: `tests/fixtures/tool_schemas.py` exists (optional to use here).

## Outputs

What exists after this leg completes:
- A new conformance test module: `tests/test_llm_provider_cross_provider_conformance.py`
  (name mirrors the sibling history test).
- A scripted-transport harness — a small set of helpers that, given an ordered
  list of two canned turns (turn-1 emits a tool_call; turn-2 a final answer),
  return a provider instance whose `complete()`/`stream()` serve those turns in
  order. **Pinned location: `tests/fixtures/scripted_transport.py`** — a sibling of
  leg 01's `tests/fixtures/tool_schemas.py`. Legs 03 (#122 guards) and 04 (#105
  recovery row + live tier) reuse this harness, so the module path is a contract,
  not an acceptable variation: their leg specs will import from
  `tests.fixtures.scripted_transport`. The Anthropic stub classes
  (`_StubResponse`/`_StubContentBlock`/recorder/stream-CM equivalents) should be a
  **self-contained copy** in this harness module, NOT imported from
  `tests/test_anthropic_provider.py` (those stubs live in a working-tree-modified
  file; a copy keeps the harness import-stable regardless of that file's state).
- The provider-parametrized round-trip test, green for Anthropic, OpenAI, Ollama,
  and Mock, exercising **both** `complete()` and `stream()`, plus the
  `tools=None/[]` plain-text path.

## Acceptance Criteria
- [x] A new conformance test module exists with a scripted-transport harness that
      drives each of {Anthropic, OpenAI, Ollama, Mock} through a two-turn round-trip.
- [x] One canonical provider-neutral script (tool def + turn-1 `ToolCall`
      expectation + synthesized `ToolResult` + turn-2 final-answer expectation)
      drives all four providers — not four bespoke scripts (DD2).
- [x] `complete()` round-trip passes for all four: turn-1 returns a `Message` whose
      `tool_calls[0].name` + `.arguments` match the script; the test builds
      `Message.tool(ToolResult(tool_call_id=..., content=...))`; turn-2 returns a
      `Message` with non-empty `content` and **no** `tool_calls`.
- [x] `stream()` round-trip passes for all four: the final `StreamChunk` (`is_final
      =True`) carries the same canonical `Message`/`tool_calls` shape as `complete()`.
- [x] The `tools=None` **and** `tools=[]` path is covered for each provider:
      `complete()` (and `stream()` for all four — exceeds the Mock+one-real
      minimum) with no tools returns a plain-text `Message`, `tool_calls == []`.
- [x] Assertions are structural (canonical `Message`/`ToolCall`/`ToolResult`
      fields), not wire byte-equality.
- [x] No production source file is modified (`git diff --stat -- 'the_one/**'`
      empty); the suite is hermetic (no network, no credentials) and runs under
      `make test-unit`'s default deselection.

## Verification Steps
- Run the new module host-native:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30`
  → all parametrized cases pass; no skips in the hermetic tier.
- Confirm each provider is actually exercised (not silently skipped): the
  parametrize ids should show `anthropic`, `openai`, `ollama`, `mock` in `-v` output.
- `git diff --stat -- 'the_one/**'` → empty.
- Re-run the leg-01 touched files to confirm no collateral breakage:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py tests/test_streaming.py tests/test_ollama_provider_recovery.py -x --timeout 30`
  → green.

## Implementation Guidance

1. **Define the canonical script** (module-level constants). A tool definition
   (canonical form `{"name", "description", "parameters"}` — a simple one-arg
   object schema is fine; the #122 `press_key` schema is NOT needed here), a turn-1
   expectation (`EXPECTED_TOOL_NAME`, `EXPECTED_ARGS = {"city": "Paris"}` or
   similar), and a turn-2 final answer string. Keep it provider-neutral.

2. **Build the scripted-transport harness** — one constructor per provider, all
   sharing a uniform signature, e.g. `make_<provider>(turns) -> provider` where
   `turns` is `[CannedTurn(tool_calls=[...]), CannedTurn(content="final")]`.
   - **Anthropic**: model on `test_anthropic_provider.py`. For `complete()`,
     monkeypatch `prov.client.messages.create` with a recorder whose
     `side_effects=[turn1_response, turn2_response]` (`_CreateRecorder` at
     `:57-80`). Stub turn-1 as `_StubResponse(content=[_StubContentBlock(
     "tool_use", id="tu_1", name=EXPECTED_TOOL_NAME, input=EXPECTED_ARGS)])` and
     turn-2 as `_StubResponse(content=[_StubContentBlock("text", text=FINAL)])`.
     For `stream()`, use `_StreamRecorder([lambda: _StreamCM([...], final1),
     lambda: _StreamCM([...], final2)])` (`:344-390`). You may import these stubs
     from `test_anthropic_provider.py` or re-create minimal equivalents in the
     harness — re-creating keeps the harness self-contained; importing avoids
     duplication. Implementer's call; prefer a small self-contained copy in the
     harness module to avoid cross-test-file import coupling.
   - **OpenAI**: model on `test_openrouter_provider.py:301-340` /
     `test_streaming.py`. Build an `httpx.MockTransport(handler)` and inject it by
     monkeypatching `httpx.AsyncClient.__init__` to force `kwargs["transport"]`, OR
     (cleaner) construct the provider then replace `prov.client` with an
     `openai.AsyncOpenAI(api_key="x", base_url=str(prov.client.base_url),
     http_client=httpx.AsyncClient(transport=transport))` (the pattern at
     `test_openrouter_provider.py:404-409`). The handler must be **stateful**:
     a call counter (closure/list) returns the turn-1 JSON (with
     `choices[0].message.tool_calls[].function.{name, arguments-as-json-string}`)
     on the first `/chat/completions`, then the turn-2 JSON (plain `content`,
     no tool_calls) on the second. For `stream()`, return SSE bodies
     (`data: {...}\n\n ... data: [DONE]\n\n`) with tool_call deltas on turn 1.
   - **Ollama**: model on `test_ollama_provider_recovery.py` (`_complete_handler` +
     `_patch_transport`). The `httpx.MockTransport` handler serves `/api/show`
     returning `{"model_info": {}}` (for the context-length resolver — see the note
     above; NOT for `supports_tools()`) and a **stateful** `/chat/completions`
     returning turn-1 (structured `tool_calls`) then turn-2 (final content).
     OllamaProvider holds **no persistent client** — it builds a fresh
     `httpx.AsyncClient` per call (`ollama_provider.py` `complete()` ~`:124`), so the
     `prov.client` replacement trick is unavailable; inject via the
     `httpx.AsyncClient.__init__` monkeypatch (the `monkeypatch` fixture auto-undoes
     it). For `stream()`, monkeypatch `the_one.llm.ollama_api.chat_stream` with a
     stateful async-generator factory (`_patch_chat_stream` shows the fake;
     `_stream_chunks` shows the chunk shape) returning turn-1 chunks then turn-2.
   - **Mock**: no transport. For `complete()`, set
     `prov.config = {"response": {"content": "", "tool_calls": [{"id":"1",
     "name": EXPECTED_TOOL_NAME, "arguments": EXPECTED_ARGS}]}}` for turn 1, then
     reassign `prov.config = {"response": {"content": FINAL}}` for turn 2 (Mock is
     not history-aware — `mock.py:68`). For `stream()`, add `stream_chunks` to the
     turn config.

3. **Write the round-trip driver** — a provider-neutral helper that, given a
   harness-built provider, runs: `m1 = await prov.complete([user], tools=[tool])`;
   assert `m1.tool_calls[0].name/.arguments`; build `result =
   Message.tool(ToolResult(tool_call_id=m1.tool_calls[0].id, content="<result>"))`;
   `m2 = await prov.complete([user, m1, result], tools=[tool])`; assert
   `m2.tool_calls == []` and `m2.content` non-empty. A second driver does the same
   over `stream()`, accumulating chunks and asserting on the final chunk's
   `.message`/`.tool_calls`.

4. **Parametrize across providers.** Note the sibling
   `test_llm_provider_cross_provider_history.py` does NOT parametrize — it uses
   per-provider fixtures + separate per-provider test methods. This leg may do
   either: `@pytest.mark.parametrize` over a list of `(id, harness_factory)` tuples,
   or a provider-factory fixture (`params=[...]`), or per-provider methods. A single
   parametrized matrix is preferred here so the "one canonical script drives all
   providers" property (DD2) is structurally enforced rather than copy-pasted. Use
   stable ids (`anthropic`, `openai`, `ollama`, `mock`) so `-v` output proves each
   ran. (DD1 acceptable variation: single matrix vs per-provider classes — pick one,
   keep one canonical script.)

5. **Add the `tools=None`/`tools=[]` cases.** A parametrized no-tools round-trip:
   `complete(messages, tools=None)` and `complete(messages, tools=[])` return a
   plain-text `Message` with `tool_calls == []`. Configure each harness's turn-1 to
   emit only content for this case. Cover `complete()` for all four; `stream()` for
   at least Mock + one real provider.

6. **Run, iterate on the conformance file only**, then run the broader touched set
   once at leg end. Use `-x --timeout 30`. These are async tests — the repo uses
   `pytest-asyncio`; follow the sibling file's `async def` + marker convention
   (check whether it relies on `asyncio_mode = auto` in `pyproject.toml` or explicit
   `@pytest.mark.asyncio`; match it).

## Edge Cases
- **Stateful handler is mandatory for OpenAI/Ollama** — a stateless handler returns
  the tool_call body on turn 2 as well, so the round-trip never terminates the way
  the assertion expects (turn-2 must have no tool_calls). The call counter is the
  crux; test it by asserting turn-2's `tool_calls == []`.
- **Injection differs per provider** (Architect-verified):
  - **OpenAI** → replace the instance client:
    `prov.client = openai.AsyncOpenAI(..., http_client=httpx.AsyncClient(transport=transport))`
    (instance-only, no global patch — the safe choice).
  - **Ollama `complete()`** → `httpx.AsyncClient.__init__` monkeypatch (no persistent
    client to replace); use the `monkeypatch` fixture so it auto-undoes — do not
    leave a patched `__init__` that leaks into other tests.
  - **Ollama `stream()`** → `the_one.llm.ollama_api.chat_stream` monkeypatch.
- **Ollama `/api/show` is for context-length resolution, not capability** — serve it
  returning `{"model_info": {}}` (mirroring `test_ollama_provider_recovery.py`).
  `_resolve_max_context_tokens_if_needed()` swallows failure (`base.py:281-301`), so
  an unserved path degrades gracefully rather than erroring — but serving it keeps
  the test fully hermetic. `supports_tools()` is never called in this leg's paths
  (the `supports_tools()=False` recovery case is leg 04, not here).
- **Assert the stateful handler reached exactly 2 calls** — for OpenAI/Ollama, have
  the handler/factory expose its call counter and assert it equals 2 at test end (in
  addition to asserting turn-2 `tool_calls == []`). This is a tight guard against a
  stateless-handler regression that would silently re-serve turn-1.
- **Mock re-config timing** — reassign `prov.config` (or build a fresh provider) for
  turn 2 *before* the second `complete()`/`stream()` call; otherwise turn 2 re-emits
  the tool_call and the round-trip never closes.
- **`ToolResult.__post_init__` normalizes content to str** — if you pass a dict as
  the tool result content, assert against the JSON-normalized str (`base.py:54-55`),
  not the dict.
- **Streaming final-chunk contract** — the canonical assistant `Message` lives on
  `StreamChunk.message` (the field `Agent.step` appends), and `tool_calls`/`usage`
  are also surfaced on the final chunk (`base.py:228-243`). Assert on the final
  chunk, not on intermediate deltas.
- **Do NOT route through the agent loop** — drive `provider.complete()`/`.stream()`
  directly (DD1). No `Agent`, no `_run_iterations`.

## Files Affected
- `tests/test_llm_provider_cross_provider_conformance.py` — **new** conformance
  module (round-trip test + parametrization).
- `tests/fixtures/scripted_transport.py` — **new** shared harness (pinned path;
  legs 03/04 import from `tests.fixtures.scripted_transport`).
- No production source files. No existing test files (this leg is additive; leg 01
  already handled the refactor).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (new conformance module green; leg-01 touched files still green)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — no flight/mission status change)
- [ ] Do NOT commit (deferred-commit model — flight commits once after the last leg)

---

## Citation Audit

Citations verified against current code at leg design time (2026-06-19, via the
flight-design reconnaissance + a dedicated code-interrogation pass):
- `the_one/llm/base.py` — `LLMProvider` contract `complete`/`stream`/`supports_tools`/
  `tool_schema` (`:303-360`); canonical types `ToolCall`/`ToolResult`/`Message`/
  `StreamChunk` (`:21-243`); `ToolResult` str-normalization (`:54-55`) — **OK**
- `the_one/llm/mock.py:68` — `complete()` returns `config["response"]` per call
  (single-response-per-config) — **OK**
- `the_one/llm/anthropic_provider.py:193-194` — `tool_use` → `ToolCall(id,name,input)` — **OK**
- `the_one/llm/openai_provider.py:136-145` — `ToolCall(id, function.name,
  json.loads(function.arguments))` — **OK**
- `the_one/llm/ollama_provider.py:142-153` — `tool_calls[].function.{name,arguments}` — **OK**
- `tests/test_anthropic_provider.py` — `_CreateRecorder` (side_effects queue),
  `_StreamRecorder`/`_StreamCM` (streaming) — **OK** (symbol-form; these test files
  are working-tree-modified, so line numbers will shift — cite by symbol)
- `tests/test_ollama_provider_recovery.py` — `_complete_handler`/`_patch_transport`
  (two-path MockTransport), `_stream_chunks`/`_patch_chat_stream` (stream) — **OK**
- `tests/test_openrouter_provider.py` — MockTransport via patched
  `AsyncClient.__init__`; SSE stream + `prov.client` replacement — **OK**
- `tests/test_llm_provider_cross_provider_history.py` — per-provider fixtures +
  per-provider methods (NOT parametrized); structural-assertion style — **OK**
  (corrected: this leg's prose now states the sibling is fixture-based, not
  parametrized)
- `pyproject.toml:78` `asyncio_mode = auto` (no per-test `@pytest.mark.asyncio`
  needed); `:86` default marker deselection — **OK**
- Ollama `/api/show` path: corrected from the original draft — it is consumed by
  `_resolve_max_context_tokens()`→`ollama_api.show_model()`, NOT `supports_tools()`
  (Architect-flagged [medium], fixed in Background/Guidance/Edge Cases).

Provider constructor signatures confirmed: `AnthropicProvider(model=, api_key=)`,
`OpenAIProvider(model=, api_key=, base_url=)`, `OllamaProvider(model=, base_url=)`,
`MockProvider(model=, config=)`.

> Note: line-number citations elsewhere in this leg refer to the **current
> working-tree** state (leg 01's refactor is landed-but-uncommitted; several test
> files are modified-not-committed). Prefer the symbol names over the line numbers
> if they disagree.

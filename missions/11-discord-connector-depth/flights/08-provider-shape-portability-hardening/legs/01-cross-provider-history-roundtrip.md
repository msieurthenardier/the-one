# Leg: cross-provider-history-roundtrip

**Status**: completed
**Flight**: [Provider-Shape-Portability Hardening](../flight.md)

## Objective

Pin the canonical `Message` format's cross-provider portability by adding a two-tier test (pure-encoder primary + live-API supplementary for Anthropic↔Ollama qwen and Anthropic↔OpenRouter `google/gemma-4-26b-a4b-it:free`); fix any shape-loss the test surfaces within an ~80 LOC divert threshold (atomic test+fix).

## Context

This is the first leg of F8 (provider-shape-portability hardening). The flight's Design Decision §2 framed L1 as a test-first atomic leg: the test pins the gap, and any fix lands in the same commit so main never carries a failing test.

Relevant flight-level decisions:
- **F8 §2 test layering**: pure-encoder primary (no network) is the test of record; live-API supplementary is confidence layer, skip-marked when credentials are missing.
- **F8 §4 provider coverage**: two operator-specified pairs — Anthropic↔Ollama qwen (operator's local default) and Anthropic↔OpenRouter `google/gemma-4-26b-a4b-it:free` (operator-confirmed slug at Phase 5b). OpenRouter inherits OpenAI's `_to_api_message` with zero override (verified: `the_one/llm/openrouter_provider.py` has no `_to_api_message` method), so OpenAI is implicitly covered.
- **F8 Adaptation Criteria**: divert if fix exceeds ~80 LOC across more than one module — split into L1 (test) + L1b (fix) at that point.

Codebase landscape (as of leg design):
- 4 providers: Anthropic (`the_one/llm/anthropic_provider.py`), OpenAI (`the_one/llm/openai_provider.py`), Ollama (`the_one/llm/ollama_provider.py`), OpenRouter (`the_one/llm/openrouter_provider.py` — subclass of OpenAIProvider).
- Canonical types: `Message` at `the_one/llm/base.py:Message` (lines 41-96), `ToolCall` at `the_one/llm/base.py:ToolCall` (lines 20-24), `ToolResult` at `the_one/llm/base.py:ToolResult` (lines 27-32), `Role` at `the_one/llm/base.py:Role` (lines 13-17).
- Existing parity test: `tests/test_llm_provider_user_content_projection.py` covers USER-role content projection across all 4 providers. L1's test extends coverage to multi-shape session history (user + assistant-with-tool-calls + tool + assistant-final) across the same 4 providers.

## Inputs

- F7 merged to main (verified: PR #76 merged 2026-05-26T13:13:12Z).
- F8 branch `flight/08-provider-shape-portability-hardening` checked out and ahead of main by the planning commit `b71a6e1`.
- Existing test patterns to mirror:
  - `tests/test_llm_provider_user_content_projection.py` — per-provider fixtures + per-class test methods (the closest pattern for pure-encoder structure).
  - `tests/test_llm_provider_tool_result_serialization.py` — 12.l hotfix coverage + str-passthrough invariant.
  - **`tests/test_input_tokens_cross_provider_live.py` — the canonical live-test pattern** for skip-markers, Ollama base-URL discovery, and model fallback. Live tests in L1 MUST mirror its conventions; see Implementation Guidance §3.
- Provider `_to_api_message` implementations stable on main (no in-flight provider refactor — L2's typing changes land AFTER L1).
- **Stray `docker-compose.yml` modification** in working tree (uncommitted, M11 F7 L12 HAT env additions: `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID`, `THE_ONE_INFERENCE_MODEL`). Per F8 flight prerequisites this should be stashed/committed before L1; if it's still present at L1 implementation start, leave it alone — the live env-var injection from `docker-compose.yml` matters only on container rebuild, and L1 runs `docker exec the-one pytest` against the already-running container. Do NOT stage or revert it as part of L1.

## Outputs

- New test file `tests/test_llm_provider_cross_provider_history.py` with two test classes:
  - `TestCrossProviderHistoryPureEncoder` — pure-Python tests exercising all 4 providers' `_to_api_message` against a canonical multi-shape Message list. NO network. Runs in CI without credentials.
  - `TestCrossProviderHistoryLiveApi` — `@pytest.mark.integration` (or equivalent skip-marker — see Implementation Guidance §3) tests against real APIs for the two operator-specified pairs. Skip-marked when credentials are missing.
- Conditional: if pure-encoder OR live-API surfaces a real gap, the fix lands in the same commit (bounded by ~80 LOC across at most one module).
- Flight log updated with: actual test outcomes; any gap found and how it was fixed; pure-encoder vs live-API result summary.

## Acceptance Criteria

- [x] New test file `tests/test_llm_provider_cross_provider_history.py` exists.
- [x] Pure-encoder primary test class `TestCrossProviderHistoryPureEncoder` exists with at least these test methods:
  - [x] `test_anthropic_encodes_canonical_history_without_error` — feeds canonical Message list through `AnthropicProvider._to_api_message` (one Message at a time, excluding SYSTEM which Anthropic extracts via `_build_kwargs`) and asserts each return is a valid dict with the expected shape (assistant-with-tool-calls produces `content: list[dict]` with tool_use blocks; tool produces `role: "user", content: [tool_result block]`; user falls through to `role-content`).
  - [x] `test_openai_encodes_canonical_history_without_error` — same canonical list through `OpenAIProvider._to_api_message`; assistant-with-tool-calls produces `role: "assistant", content: ..., tool_calls: [...]`; tool produces `role: "tool", tool_call_id: ..., content: ...`.
  - [x] `test_ollama_encodes_canonical_history_without_error` — same list through `OllamaProvider._to_api_message`; shape matches OpenAI's (Ollama mirrors OpenAI's encoding per `the_one/llm/ollama_provider.py:252-279`).
  - [x] `test_openrouter_inherits_openai_encoding_for_history` — instantiate `OpenRouterProvider`, call `_to_api_message` on the same list, assert byte-identical output to OpenAI's encoding (pins the inheritance contract — if OpenRouter ever overrides `_to_api_message`, this test catches the divergence).
  - [x] `test_cross_provider_session_swap_anthropic_to_openai_shape` — build a Message list "as if accumulated under Anthropic" (e.g., ToolCall IDs in the Anthropic `toolu_*` format, ToolResult.content as JSON string), feed through OpenAI encoder, assert no exception and output dict shape is OpenAI-compatible. Mirror with `_openai_to_anthropic_shape`.
  - [x] `test_assistant_empty_content_tool_calls_per_provider` — pins the most subtle cross-provider divergence: an assistant Message with `content=""` and `tool_calls=[...]`. Anthropic skips the text block entirely (only tool_use block appears in `content` list); OpenAI/Ollama emit `content: None` alongside `tool_calls`. The test asserts both behaviors per their providers without forcing alignment.
  - [x] `test_tool_result_content_str_passthrough_all_providers` — pins F7's 12.l contract: a str ToolResult.content round-trips byte-identical through every provider's encoder. Pre-empts an L2 regression.
  - [x] `test_tool_result_content_non_str_diverges_per_provider` — documents the CURRENT (pre-L2) behavior: Anthropic JSON-encodes non-str ToolResult.content (per 12.l hotfix); OpenAI/Ollama pass through unchanged. This test will need updating in L2 when `__post_init__` normalizes; mark it with a comment block linking to F8 L2 so the maintainer knows it's intentional.
- [x] Live-API supplementary test class `TestCrossProviderHistoryLive` exists with `@pytest.mark.live` on each test method (mirror `tests/test_input_tokens_cross_provider_live.py:143,171,197,254`), with at least these test methods (skip-marked when credentials/services missing via inline `pytest.skip(...)` at function entry):
  - [x] `test_anthropic_to_ollama_session_swap_live` — build a small Message list via `AnthropicProvider.complete()` (system + user, no tools — keep payload trivial), then feed the resulting history (with the assistant response appended) through `OllamaProvider.complete()`. Use `LIVE_OLLAMA_BASE_URL` env-var with default `http://host.docker.internal:11434/v1`; probe via `/api/tags` (strip `/v1` suffix first) per the canonical pattern at `tests/test_input_tokens_cross_provider_live.py:199-217`; auto-discover model from `/api/tags` (prefer `LIVE_OLLAMA_MODEL` → `qwen2.5:7b` → first available). Assert no exception, response is a valid `Message`. Skip if `ANTHROPIC_API_KEY` missing OR Ollama unreachable.
  - [x] `test_ollama_to_anthropic_session_swap_live` — reverse direction. Skip with same gates.
  - [x] `test_anthropic_to_openrouter_session_swap_live` — same shape with `OpenRouterProvider`. Model slug: `os.environ.get("LIVE_OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")` (operator-confirmed default; env-var override for operator-recovery if the slug is wrong). Skip if `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY` missing. **Important**: if OpenRouter returns a NotFoundError / 404 for the model slug at test time, the test SKIPS with a clear error message (citing both the slug and the `LIVE_OPENROUTER_MODEL` override hint) — the test's job is to pin shape-correctness, not validate model-availability.
  - [x] `test_openrouter_to_anthropic_session_swap_live` — reverse direction. Skip with same gates.
  - [x] **At least one of the four live tests above MUST exercise a real `tools=...` payload** — request a `tools` list with a synthetic tool definition (e.g., `{"name": "noop", "description": "...", "parameters": {...}}`), capture any returned `tool_calls`, append a synthetic `ToolResult` to the history, and round-trip the WHOLE history (system + user + assistant-with-tool-calls + tool-result) through the OTHER provider's `complete()`. Without this, the live tier doesn't exercise the actual cross-provider swap concern (tool_call shape compatibility) — only chat-content compatibility. Recommend the Anthropic↔Ollama pair for the tool-payload test (qwen2.5:7b supports tools per F7 L7).
- [x] Full pre-existing test suite passes via `make test-unit` (which expands to `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -v --tb=short` per `Makefile:115-116`). The new L1 tests run in this suite (live tier excluded by the marker). **F7 baseline 2645 was measured with `pytest tests/ --ignore=tests/browser --ignore=tests/behavior -x` (per F7 debrief `flight-debrief.md:71`) — that filter is DIFFERENT from `make test-unit`'s marker filter.** The leg's regression baseline must be re-pinned: run `make test-unit` FIRST (before adding any code), record the count, and assert the post-leg count is `that count + N` (where N is the number of new L1 tests). The F7-baseline-2645 number does NOT carry forward; use the re-pinned baseline.
- [x] If pure-encoder or live-API surfaces a real shape-loss gap, the fix is committed in this same leg, bounded by ~80 LOC across at most one module. Beyond that → divert (split into L1+L1b). **Hard fence**: even if the fix would be <80 LOC, do NOT touch `the_one/llm/base.py` — that's L2's exclusive territory. A gap requiring base.py changes diverts to L2 by definition, regardless of LOC count.
- [x] Flight log entry under "Leg Progress" with: outcome summary, re-pinned pre-leg baseline + post-leg total, gap found (or "no gap"), live-API skip status, model actually used for Ollama (since it's auto-discovered).

## Verification Steps

For each acceptance criterion, the verification command:

1. **Test file exists**:
   `ls -la /home/cprch/projects/the-one/tests/test_llm_provider_cross_provider_history.py`

2. **Pure-encoder tests pass** (no network required):
   ```
   docker exec the-one pytest tests/test_llm_provider_cross_provider_history.py::TestCrossProviderHistoryPureEncoder -x --timeout 30 -v
   ```
   Expected: all tests pass.

3. **Live-API tests pass OR skip with clear reason** (live marker required):
   ```
   docker exec the-one pytest tests/test_llm_provider_cross_provider_history.py::TestCrossProviderHistoryLive -m live -x --timeout 60 -v
   ```
   Expected: PASSED or SKIPPED with skip reason citing the missing credential / unreachable service / unavailable model. NEVER FAILED.

4. **Full suite passes, no regressions** (use the project's canonical test target):
   ```
   make test-unit
   ```
   Expected: total passed = pre-leg baseline + N (where N is the count of new L1 tests added). Zero failures. **The pre-leg baseline must be re-pinned by running `make test-unit` BEFORE writing any new tests; the F7-debrief-cited 2645 was measured under a different filter and does NOT carry forward.**

5. **Flight log entry**:
   `grep -A 5 "### cross-provider-history-roundtrip" missions/11-discord-connector-depth/flights/08-provider-shape-portability-hardening/flight-log.md`
   Expected: leg-progress section with outcome summary.

## Implementation Guidance

### 1. Read existing patterns first

- Read `tests/test_llm_provider_user_content_projection.py` end-to-end — it's the closest pattern: per-provider fixtures, per-class test methods, OpenRouter inheritance test at the end.
- Read `tests/test_llm_provider_tool_result_serialization.py` end-to-end — it covers the 12.l hotfix and the str-passthrough invariant L1 also pins.
- Read `the_one/llm/anthropic_provider.py:_to_api_message` (lines 219-268) — note three branches: TOOL+tool_result, ASSISTANT+tool_calls, fallback. **Critical**: Anthropic extracts SYSTEM messages into a separate `system` kwarg in `_build_kwargs` (lines 73-78), so `_to_api_message` is NEVER called with a SYSTEM message. The pure-encoder test for Anthropic must skip SYSTEM messages in its iteration (use `_build_kwargs` if testing list-level shape, or filter the list before calling `_to_api_message` per-message).
- Read `the_one/llm/openai_provider.py:_to_api_message` (lines 255-282) — handles SYSTEM as just `role: "system", content: ...` via the fallback branch (no special-casing). Same pattern in Ollama.

### 2. Canonical Message list — build once, use in many tests

Define a module-level helper (or fixture) that returns the canonical multi-shape session list. The list intentionally includes BOTH a content-bearing assistant-with-tool-calls turn AND an empty-content assistant-with-tool-calls turn to exercise the Anthropic-vs-OpenAI divergence at the encoding boundary:

```python
CANONICAL_SESSION: list[Message] = [
    Message.system("You are a helpful agent."),
    Message.user(
        "What's the channel been talking about?",
        peer_name="alice",
        channel_name="general",
    ),
    Message.assistant(
        content="Let me check the recent messages.",
        tool_calls=[
            ToolCall(
                id="toolu_01abc123",  # Anthropic-shape ID; tests swap-resilience
                name="fetch_channel_history",
                arguments={"channel_id": "1234567890", "limit": 10},
            ),
        ],
    ),
    Message.tool(
        ToolResult(
            tool_call_id="toolu_01abc123",
            content='[{"peer_name": "alice", "content": "hi"}, {"peer_name": "bob", "content": "hey"}]',
        ),
    ),
    # F8 L1 medium-severity addition (per design review): empty-content
    # assistant-with-tool-calls turn. Anthropic skips the text block; OpenAI
    # emits content: None. Both are valid per their APIs but the encodings
    # diverge — the canonical list pins both behaviors via the
    # `test_assistant_empty_content_tool_calls_per_provider` test.
    Message.assistant(
        content="",
        tool_calls=[
            ToolCall(
                id="toolu_01def456",
                name="noop",
                arguments={},
            ),
        ],
    ),
    Message.tool(
        ToolResult(
            tool_call_id="toolu_01def456",
            content="ok",
        ),
    ),
    Message.assistant(content="The channel has been quiet — just greetings from alice and bob."),
]
```

The Anthropic-shape ToolCall ID (`toolu_01abc123`, `toolu_01def456`) exercises the cross-provider swap concern at the per-message level: a session that accumulated tool_calls under Anthropic carries those IDs forward into the canonical Message — when the same list is encoded by OpenAI/Ollama, the canonical ID is what they emit in their request payload. The test pins that this is acceptable to all three encoders (none of them validate the ID format).

For the reverse swap test, use an OpenAI-shape ID (`call_xyz789`).

**Verify `Message.assistant` signature** at `the_one/llm/base.py:122-129` before writing the canonical list — current signature is `assistant(cls, content, tool_calls=None, usage=None, *, visibility=None)`. Both `content=...` and `tool_calls=...` work as kwargs; `visibility` is keyword-only. The example above is correct as written.

### 3. Skip-marker pattern for live-API tests — mirror the canonical pattern exactly

**The project has an established live-test convention. Do not invent new patterns.** Mirror `tests/test_input_tokens_cross_provider_live.py:143-260` — that file is the canonical reference. Key elements:

- **Marker**: `@pytest.mark.live` is registered at `pyproject.toml:67-72`. The project's `addopts` (line 65) deselects `live` from `make test-unit` runs by default; `make test-live` runs them via `-m live`. Do NOT use `@pytest.mark.integration` (unregistered → strict-marker warning) or `@pytest.mark.skipif(...)` at class-level (the convention is INLINE skip checks at function entry).
- **Inline skip pattern** at function entry:
  ```python
  @pytest.mark.live
  async def test_anthropic_to_ollama_session_swap_live() -> None:
      if not os.environ.get("ANTHROPIC_API_KEY"):
          pytest.skip(
              "ANTHROPIC_API_KEY not set — operator must export the key to run this live test"
          )
      # ... test body
  ```
- **Ollama base-URL + model discovery** (the hardest-to-get-right part — mirror lines 199-236 of the canonical pattern):
  ```python
  base_url = os.environ.get("LIVE_OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
  import httpx
  # Probe via /api/tags (strip /v1 suffix if present — works whether the env var
  # points at the bare host or the OpenAI-compat endpoint).
  probe_root = base_url.rstrip("/")
  if probe_root.endswith("/v1"):
      probe_root = probe_root[: -len("/v1")]
  tags_url = probe_root + "/api/tags"
  try:
      async with httpx.AsyncClient(timeout=5) as client:
          resp = await client.get(tags_url)
  except (httpx.HTTPError, OSError) as exc:
      pytest.skip(
          f"Ollama at {base_url} not reachable: {type(exc).__name__}: {exc}. "
          f"On native-Linux Docker, host.docker.internal may not resolve — "
          f"set LIVE_OLLAMA_BASE_URL explicitly."
      )
  if resp.status_code != 200:
      pytest.skip(f"Ollama at {base_url} not reachable: HTTP {resp.status_code}")
  tags = resp.json().get("models", [])
  if not tags:
      pytest.skip(f"Ollama at {base_url} has no models loaded")
  # Prefer LIVE_OLLAMA_MODEL → qwen2.5:7b → first available.
  preferred = os.environ.get("LIVE_OLLAMA_MODEL")
  available_names = [t.get("name") or t.get("model") for t in tags]
  available_names = [n for n in available_names if n]
  if preferred and preferred in available_names:
      model = preferred
  elif "qwen2.5:7b" in available_names:
      model = "qwen2.5:7b"
  elif available_names:
      model = available_names[0]
  else:
      pytest.skip(f"Ollama at {base_url} returned tags but no model names")
  ```
  **Critical**: inside the container, `localhost` resolves to the container itself — NOT the operator's Ollama. The base URL must be `host.docker.internal:11434` (the canonical default). Do NOT introduce `localhost:11434` literals.

- **OpenRouter model availability** — the `google/gemma-4-26b-a4b-it:free` slug was operator-confirmed but architect-flagged. Pattern:
  ```python
  import openai
  model = os.environ.get("LIVE_OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
  provider = OpenRouterProvider(model=model)
  try:
      # ... call complete()
  except openai.NotFoundError as exc:
      pytest.skip(
          f"OpenRouter model {model!r} not found: {exc}. "
          f"Set LIVE_OPENROUTER_MODEL to a valid slug to override."
      )
  ```

- **Provider cleanup**: the canonical pattern uses `try/finally` with `_aclose_provider_client(provider)` (see `tests/test_input_tokens_cross_provider_live.py:167-168`). Mirror this — Ollama / OpenAI / Anthropic clients hold network resources that need explicit close in test contexts.

### 4. Pure-encoder tests: structure assertions, not byte-equality

For each provider's encode of the canonical list, assert structural validity rather than exact byte-equality of the whole dict:

- Anthropic encode of the ASSISTANT+tool_calls message: assert `result["role"] == "assistant"`, `isinstance(result["content"], list)`, `len(result["content"]) == 2`, `result["content"][0]["type"] == "text"`, `result["content"][1]["type"] == "tool_use"`, `result["content"][1]["id"] == "toolu_01abc123"`.
- OpenAI encode of the same message: assert `result["role"] == "assistant"`, `result["content"] == "Let me check the recent messages."`, `len(result["tool_calls"]) == 1`, `result["tool_calls"][0]["id"] == "toolu_01abc123"`, `result["tool_calls"][0]["function"]["name"] == "fetch_channel_history"`.
- Anthropic encode of the TOOL message: assert `result["role"] == "user"` (Anthropic uses user-role for tool_result blocks), `result["content"][0]["type"] == "tool_result"`, `result["content"][0]["tool_use_id"] == "toolu_01abc123"`, `result["content"][0]["content"] == '[{"peer_name": "alice", "content": "hi"}, ...]'` (str passthrough).
- OpenAI encode of the TOOL message: assert `result["role"] == "tool"`, `result["tool_call_id"] == "toolu_01abc123"`, `result["content"]` is the str unchanged.

Structural assertions catch real shape changes (a missing key, a swapped role) without breaking on every cosmetic edit (whitespace in JSON, ordering of dict keys).

### 5. Live-API tests: minimal payload + at-least-one tool-payload test

Live-API tests are CONFIDENCE tests, not behavior pins — LLMs are non-deterministic so we can't assert exact response content. Each test must use the skip-pattern from §3.

**Minimal chat round-trip** (three of the four live tests):

```python
@pytest.mark.live
async def test_anthropic_to_ollama_session_swap_live() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — operator must export the key to run this live test")

    # [Ollama probe + model discovery from §3]
    # ... resolves `base_url` and `model` for Ollama

    from the_one.llm.anthropic_provider import AnthropicProvider
    from the_one.llm.ollama_provider import OllamaProvider

    anthropic_model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    anthropic = AnthropicProvider(model=anthropic_model)
    ollama = OllamaProvider(model=model, base_url=base_url)

    try:
        # Step 1: minimal conversation under Anthropic.
        history: list[Message] = [
            Message.system("Reply with one word."),
            Message.user("Hello."),
        ]
        anthropic_reply = await anthropic.complete(history, temperature=0.0, max_tokens=50)
        assert isinstance(anthropic_reply, Message)
        assert anthropic_reply.role == Role.ASSISTANT
        history.append(anthropic_reply)

        # Step 2: continue the session under Ollama.
        history.append(Message.user("Same."))
        ollama_reply = await ollama.complete(history, temperature=0.0, max_tokens=50)
        assert isinstance(ollama_reply, Message)
        assert ollama_reply.role == Role.ASSISTANT
        # NO content assertions — model behavior is non-deterministic.
    finally:
        await _aclose_provider_client(anthropic)
        await _aclose_provider_client(ollama)
```

**Tool-payload swap test — REQUIRED, at least one** (recommended: Anthropic ↔ Ollama qwen pair):

```python
@pytest.mark.live
async def test_anthropic_with_tools_to_ollama_swap_live() -> None:
    # [skip-pattern from §3 — ANTHROPIC_API_KEY, Ollama probe, model discovery]

    tool_def = {
        "name": "noop",
        "description": "Returns the string 'ok'. Use this when asked.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }
    history: list[Message] = [
        Message.system("Use the noop tool when asked."),
        Message.user("Call the noop tool."),
    ]
    try:
        # Step 1: Anthropic call with tools. The model decides whether to use it.
        anthropic_reply = await anthropic.complete(
            history, tools=[tool_def], temperature=0.0, max_tokens=200
        )
        history.append(anthropic_reply)

        # Step 2: append a synthetic ToolResult for each tool_call (if any).
        # If Anthropic didn't call the tool, this loop is a no-op — the test
        # still pins shape compatibility for the messages-without-tool-result
        # path, which is also a valid swap shape.
        for tc in anthropic_reply.tool_calls:
            history.append(Message.tool(ToolResult(tool_call_id=tc.id, content="ok")))

        # Step 3: re-send the WHOLE history through Ollama. The cross-provider
        # invariant being tested: Ollama accepts a Message list whose
        # ToolCall IDs were minted by Anthropic (toolu_*) and whose
        # ToolResult content rounded through Anthropic's coercion path.
        ollama_reply = await ollama.complete(history, tools=[tool_def], temperature=0.0, max_tokens=200)
        assert isinstance(ollama_reply, Message)
        assert ollama_reply.role == Role.ASSISTANT
    finally:
        await _aclose_provider_client(anthropic)
        await _aclose_provider_client(ollama)
```

Cost: each call is ≤ 200 output tokens against tiny models. Total live-API cost for L1 should remain under 1 cent per full run.

**Why the tool-payload variant is required**: without it, the live tier reduces to "do both providers accept a trivial chat?" — which is mostly already covered by `test_input_tokens_cross_provider_live.py`. The actual cross-provider swap concern (tool_calls + tool_results encoded by one provider, re-sent through another) is what L1 is supposed to validate. The pure-encoder tier covers the encoding boundary but cannot exercise the wire-level acceptance.

### 6. If a real gap surfaces — fix in-place, bounded

Possible gap shapes and their fixes (each scoped to ~80 LOC max):

- **Provider raises on a valid canonical Message** → likely a missing branch in `_to_api_message` or a SYSTEM extraction order bug. Fix: add the missing branch or fix the order; ~10-30 LOC.
- **OpenRouter doesn't inherit identically** → likely a recent override or a base-class change. Fix: align OpenRouter's surface with OpenAI; ~5-10 LOC.
- **Tool_calls ID-format mismatch** → one provider rejects non-native ID formats. Fix: normalize ID in the canonical Message (probably L2 territory — divert).

If the fix would exceed ~80 LOC OR touch >1 module → STOP, add the test with `@pytest.mark.xfail(strict=True, reason="...")` documenting the gap, write the divert decision to the flight log, and signal `[BLOCKED:divert-threshold-exceeded]` for the Flight Director to escalate. Per F8 Adaptation Criteria, the divert spawns L1b for the fix.

### 7. Flight-log update

Append a new section under `## Leg Progress`:

```markdown
### cross-provider-history-roundtrip

**Status**: landed
**Started**: {ISO timestamp}
**Completed**: {ISO timestamp}

#### Changes Made
- Added `tests/test_llm_provider_cross_provider_history.py` with TestCrossProviderHistoryPureEncoder ({N} tests) + TestCrossProviderHistoryLiveApi ({M} tests).
- Pure-encoder tests cover canonical-session encoding across all 4 providers + cross-provider swap shape resilience.
- Live-API tests cover Anthropic↔Ollama qwen and Anthropic↔OpenRouter `google/gemma-4-26b-a4b-it:free` session swaps.

#### Notes
- Gap surfaced: {"none" | "describe the gap and the fix in 1-2 sentences with file:line"}.
- Live-API skip status: {"all 4 ran" | "skipped X for reason Y"}.
- Test-metric delta: {N pre-leg → N+X post-leg, no regressions}.
```

### 8. Order of operations

1. **Re-pin the test baseline FIRST**: run `make test-unit` and record the pre-leg passed count. This number replaces the F7-debrief-cited 2645 for L1's regression assertion (different filter).
2. Read the four pattern files (existing parity test + tool_result serialization test + provider source + `tests/test_input_tokens_cross_provider_live.py` for the live-test convention).
3. Update leg status to `in-flight` in this artifact's header.
4. Write the test file skeleton with fixtures + canonical session helper. Import `_aclose_provider_client` from `tests.test_input_tokens_cross_provider_live` (or copy the helper if the import direction matters — check the project's convention).
5. Add pure-encoder tests first; iterate until all pass.
6. Add live-API tests; iterate until they pass or skip cleanly. **MUST include at least one tool-payload swap test** (recommended: Anthropic ↔ Ollama).
7. Run `make test-unit` to confirm no regressions; assert passed count = pre-leg baseline + N new tests.
8. Run `docker exec the-one pytest tests/test_llm_provider_cross_provider_history.py -m live -x --timeout 60 -v` to confirm live tests pass/skip cleanly (operator-side credential availability).
9. If a gap surfaced and fix landed: re-run full suite + live suite.
10. Update flight-log.md with the entry from §7.
11. Update leg status to `landed`.
12. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Anthropic's SYSTEM extraction**: `_build_kwargs` (lines 73-78) extracts SYSTEM into a separate `system` kwarg before calling `_to_api_message`. The pure-encoder test for Anthropic must either (a) filter SYSTEM out of the canonical list before per-message iteration, or (b) call `_build_kwargs` for list-level shape testing and assert `kwargs["system"] == "You are a helpful agent."` separately. Pick (a) for simplicity; add a one-line comment in the test method explaining the filter.
- **OpenAI's `msg.content or None` for ASSISTANT+tool_calls**: when content is empty, OpenAI emits `content: null` while Anthropic skips the text block entirely. Both are valid per their APIs but the encodings diverge structurally. The test should accept either — assert `result["content"] is None or result["content"] == ""` for OpenAI; assert `len([b for b in result["content"] if b["type"] == "text"]) == 0` for Anthropic when content is empty. The canonical list above uses non-empty content so this edge case isn't hit by the main path, but a dedicated test `test_assistant_tool_calls_empty_content_per_provider` would be valuable if scope allows.
- **OpenRouter model availability**: `google/gemma-4-26b-a4b-it:free` was operator-confirmed but architect-flagged as risky. The test catches `openai.NotFoundError` and converts to skip; do NOT fail the test on model-unavailable.
- **Ollama qwen model variant**: `qwen2.5:7b` is the operator's stated local default but the actual installed model may differ. The test should try `qwen2.5:7b` first; if Ollama returns "model not found" for it, the test SKIPS with a clear message (no fallback model — testing surface should be deterministic per environment).
- **Anthropic's 12.l coercion (str vs non-str ToolResult.content)**: the test `test_tool_result_content_str_passthrough_all_providers` and `test_tool_result_content_non_str_diverges_per_provider` pin both current behaviors. After L2 lands, `__post_init__` will normalize non-str at construction, so the diverges test will need updating. Add a comment block in that test linking to F8 L2 so the maintainer knows it's intentional and will be revisited.

## Files Affected

- `tests/test_llm_provider_cross_provider_history.py` — **NEW**. ~200-300 LOC. The leg's main deliverable.
- `missions/11-discord-connector-depth/flights/08-provider-shape-portability-hardening/flight-log.md` — update with leg-progress entry.
- `missions/11-discord-connector-depth/flights/08-provider-shape-portability-hardening/flight.md` — check off `cross-provider-history-roundtrip` in the Legs list under "In-Flight".
- This leg artifact — status `planning` → `in-flight` → `landed`.
- *(Conditional)* If a gap is surfaced and fix lands here: up to 1 module touched, ~80 LOC max. Likely candidates: one of the provider files in `the_one/llm/`.

**Do NOT touch**:
- `the_one/llm/base.py` — `Message`, `ToolResult`, `ToolCall` definitions; the typing fix is L2's territory.
- The 12.l Anthropic coercion at `the_one/llm/anthropic_provider.py:219-249` — L2 deletes this.
- The 12.m `truncate_for_event` at `the_one/db/codec.py:18-39` — L2 annotates this.
- Any UI / API / connector / agent code — out of scope.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified via the commands in Verification Steps
- [x] Tests passing — full suite + new test file
- [x] Update flight-log.md with leg progress entry (template in Implementation Guidance §7)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If a gap surfaced, document the fix in the flight-log entry with file:line citation
- [x] **Do NOT commit** — Flight Director batches commits across all autonomous legs at Phase 2d
- [x] Signal `[HANDOFF:review-needed]`

## Citation Audit

17 citations verified against current code at leg design time (12 from initial draft + 5 added during design-review-cycle 1):

Initial draft:
- `the_one/llm/base.py:Role` lines 13-17 — OK
- `the_one/llm/base.py:ToolCall` lines 20-24 — OK
- `the_one/llm/base.py:ToolResult` lines 27-32 — OK (current annotation `content: str`; L2 will widen)
- `the_one/llm/base.py:Message` lines 41-96 — OK (including peer_name at 69, channel_id at 83, channel_name at 96)
- `the_one/llm/anthropic_provider.py:_to_api_message` lines 219-268 — OK (12.l coercion at 236-238 confirmed live)
- `the_one/llm/anthropic_provider.py:_build_kwargs` lines 66-91 (SYSTEM extraction at 73-78) — OK
- `the_one/llm/openai_provider.py:_to_api_message` lines 255-282 — OK
- `the_one/llm/ollama_provider.py:_to_api_message` lines 252-279 — OK (verified Ollama mirrors OpenAI's shape)
- `the_one/llm/openrouter_provider.py` no `_to_api_message` override — OK (verified by reading full file; OpenRouterProvider inherits from OpenAIProvider with no method override)
- `tests/test_llm_provider_user_content_projection.py` — OK (pattern reference)
- `tests/test_llm_provider_tool_result_serialization.py` — OK (pattern reference)
- F7 baseline 2645 passed cited from F7 debrief — OK (per `flight-debrief.md:71`) **but reframed during review**: this baseline was measured with a different filter than `make test-unit`; L1 re-pins the baseline as the first step in Order of Operations.

Added during design-review cycle 1 (Developer feedback):
- `the_one/llm/base.py:Message.assistant` lines 122-129 — OK (signature confirmed: `assistant(cls, content, tool_calls=None, usage=None, *, visibility=None)`)
- `tests/test_input_tokens_cross_provider_live.py:143-260` — OK (canonical live-test pattern: `@pytest.mark.live` + inline `pytest.skip` + Ollama base-URL discovery at 199-217 + model auto-discovery at 224-236 + `_aclose_provider_client` cleanup at 167-168 / 250-251)
- `pyproject.toml:65-72` — OK (addopts deselects `live`; `markers = ["live: ...]` registered)
- `Makefile:115-116` — OK (`test-unit` target: `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -v --tb=short`)
- `Makefile:128-130` — OK (`test-live` target for the live tier)

## Design-Review Cycle Log

**Cycle 1 (2026-05-26, Developer reviewer)**: approve with changes. Three high-severity issues:
- Ollama host `localhost:11434` wrong inside container → fixed: use `LIVE_OLLAMA_BASE_URL` defaulting to `host.docker.internal:11434/v1` mirroring canonical pattern.
- `@pytest.mark.integration` not registered → fixed: use `@pytest.mark.live` + inline `pytest.skip` per project convention.
- Wrong test command → fixed: use `make test-unit`; F7-baseline-2645 explicitly re-pinned (different filter).

Two medium-severity additions:
- Empty-content assistant-with-tool-calls turn → added to canonical session (sixth + seventh entries: empty-content assistant + tool_result).
- Live-API tests should exercise tools payload → added required `test_anthropic_with_tools_to_ollama_swap_live` covering full tool_call → tool_result round-trip.

Plus low-severity:
- Stray `docker-compose.yml` in working tree → noted in Inputs section (do NOT stage/revert; operator-side).
- `TestCrossProviderHistoryLiveApi` → renamed to `TestCrossProviderHistoryLive`.

Designer's call on Developer's questions:
- Q: parametrize across providers? **A: no** — per-provider granularity preserves clearer test names and lets each `_to_api_message` get provider-specific structural assertions (Anthropic content-list vs OpenAI content-string-or-None).
- Q: base.py as hard fence? **A: yes** — confirmed in "Files Affected" Do-NOT-touch list; any gap requiring base.py changes diverts to L2 regardless of LOC count.

**Cycle 2 (2026-05-26, Developer reviewer)**: **approve**. All cycle-1 fixes landed cleanly; no new high-severity issues. Three low-severity suggestions noted (no action required; surface at implementation time):
- qwen2.5:7b tool-support uncertainty — example handles gracefully (no-op safe if Anthropic doesn't call the tool); worth a one-line comment in the test.
- Tool-def `parameters` vs Anthropic's `input_schema` — provider-level `_to_anthropic_tool` normalization handles this (Anthropic `tool_schema` accepts canonical shape via the schema converter).
- `_aclose_provider_client` import — `from tests.test_input_tokens_cross_provider_live import _aclose_provider_client` works via the project's `pythonpath = ["tests"]` + `importlib` mode. Mildly unconventional (underscore prefix on cross-file import) but established convention.

Structural sanity confirmed: 7 CANONICAL_SESSION entries internally consistent (tool_call_ids match across call→result pairs); base.py hard-fence aligns with L2 scope (flight.md lines 107, 148); Order of Operations step 1 reachable without code changes.

**Leg approved for implementation.** [HANDOFF:review-needed]

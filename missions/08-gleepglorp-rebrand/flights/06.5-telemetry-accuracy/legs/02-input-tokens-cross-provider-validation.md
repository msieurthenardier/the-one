# Leg: input-tokens-cross-provider-validation

**Status**: completed
**Flight**: [Telemetry Accuracy](../flight.md)

## Objective

Ship a `@pytest.mark.live` test harness in `tests/test_input_tokens_cross_provider_live.py` that:

1. For each provider config detected via environment (Anthropic, OpenAI, Ollama, OpenRouter), instantiates the provider with a known small model.
2. Runs a 3-turn conversation directly through the provider's `complete()` API (NOT via the Agent — to isolate provider-level token reporting from agent-loop behavior).
3. Asserts `Message.usage.input_tokens` grows MONOTONICALLY across turns (turn N's prompt is longer than turn N-1's because it includes prior history).
4. Skips silently for any provider whose credentials/server are not available — preserves the project's existing `live` marker semantics (deselected by default in CI; operator runs explicitly).

The test is the diagnostic that localizes the F6 KI #2 Ollama-undercount symptom: if Ollama's `prompt_tokens` doesn't grow monotonically with conversation length, the issue is Ollama-side (or the request body shape we send). Categorization (Ollama-side vs ours) happens at L03 HAT when the operator runs the test against their real providers.

## Context

- **Design Decision (flight.md)**: "Cross-provider `input_tokens` validation as a test harness, not a runtime assertion. Pytest marker: `@pytest.mark.live` (verified to exist in `pyproject.toml`)."
- **Recon (flight-log.md row 2, 14)**: Ollama undercount is `confirmed-live (symptom) / unverified (root cause)`. The agent sends full history every turn (`agent/core.py:172-173` — no truncation). So if `prompt_tokens` is flat across turns, the issue is provider-side. Test harness ships the diagnostic.
- **Existing `live`-marker convention**: `tests/test_aiat.py` uses `@pytest.mark.live` for "live agent integration acceptance tests" — exercises the running service via HTTP. L02's test is DIFFERENT — it instantiates providers directly (no service, no agent loop), to isolate the provider's `usage` reporting. Same marker, different scope. Document this clearly in the test file's module docstring.
- **F6.5 L01 carry-forward**: L01 added the lazy resolver to all four real providers. L02's harness will trigger the resolver on first `complete()` call — fine, it's idempotent.
- **`pyproject.toml:62`**: `markers = ["live: marks tests that call real LLM APIs (deselect with '-m \"not live\"')"]`. Per-marker deselect math at line 59: `live=6`. L02 adds N more tests (one per provider) — verify the math after the leg lands.

## Inputs

Files that exist before this leg runs:
- `tests/test_aiat.py` — reference for `@pytest.mark.live` usage pattern; ALSO see how it handles "service not available" (typically via a fixture that probes and skips)
- `the_one/llm/{anthropic,openai,ollama,openrouter}_provider.py` — providers with L01-landed lazy `max_context_tokens` resolution
- `the_one/llm/base.py:Message`, `the_one/llm/base.py:TokenUsage` — return shape
- `pyproject.toml:62` — `live` marker registered
- L01 unit tests at `tests/test_llm_max_context.py` — pattern for mocking provider clients (not used here since L02 needs real clients, but reference for AsyncMock idiom if any fallbacks need mocking)

State that must be true:
- L01 (`max-context-per-model`) landed; broad pytest 1669p/4s/370d exit 0; browser suite 315p/35s
- Container `the-one` running

## Outputs

Files modified:
- `tests/test_input_tokens_cross_provider_live.py` — NEW test module with one test function per provider (4 tests: `test_anthropic`, `test_openai`, `test_ollama`, `test_openrouter`). Each test: detects credentials via environment, skips silently if absent, instantiates provider with a known small model, runs 3-turn conversation, asserts monotonic `input_tokens` growth.

Optional (only if scope allows):
- `agents.md` (or wherever the project keeps test invocation docs) — note about how to run the new live harness: `docker exec -e {creds} the-one pytest -m live tests/test_input_tokens_cross_provider_live.py`. Defer if no obvious doc home exists; carry-forward as a doc-debt KI otherwise.

State after:
- Operator can run the cross-provider harness on demand to verify telemetry accuracy across their available providers.
- `pyproject.toml:59` per-marker deselect math may need updating from `live=6` to `live=10` (add 4 new live tests) — verify count after the test file lands.
- Default-CI broad pytest unchanged (1669p/4s/370d) — new tests are deselected by `live`.

## Acceptance Criteria

- [ ] New file `tests/test_input_tokens_cross_provider_live.py` exists with a module docstring explaining the diagnostic intent (catch provider-side `input_tokens` undercounts, particularly the F6 KI #2 Ollama qwen observation)
- [ ] One test function per real provider: `test_anthropic_input_tokens_monotonic`, `test_openai_input_tokens_monotonic`, `test_ollama_input_tokens_monotonic`, `test_openrouter_input_tokens_monotonic`. Each decorated with `@pytest.mark.live`.
- [ ] Each test detects credentials via environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LIVE_OLLAMA_BASE_URL` or detect via Ollama tags endpoint, `OPENROUTER_API_KEY`) and calls `pytest.skip("provider unavailable: ...")` with a descriptive reason if absent
- [ ] Each test selects a known-small / known-cheap model for that provider (Anthropic: `claude-3-5-haiku-latest` or similar small Claude; OpenAI: `gpt-4o-mini`; Ollama: detects an available model via `/api/tags` listing, prefers `qwen2.5:7b` if present (matches F6 bug-report scenario), else picks the first available; OpenRouter: a cheap model like `meta-llama/llama-3.2-3b-instruct:free` or operator-selectable via env)
- [ ] Each test runs a 3-turn conversation by directly calling `await provider.complete([messages...])` three times, each time appending the new user message + the previous assistant response to the messages list (manual history accumulation, no Agent class)
- [ ] Each test asserts `usage.input_tokens` is strictly POSITIVE for all 3 turns AND monotonically NON-DECREASING (turn N's input_tokens >= turn N-1's input_tokens). Anthropic's prompt-cache feature reports cached-read tokens separately via `cache_read_input_tokens`; `input_tokens` then reflects only the non-cached portion. The monotonic-non-decreasing assertion still holds for short (sub-1024-token) 3-turn conversations because prompt-caching doesn't trigger under the threshold; if a future operator triggers cache hits, the soft assertion stays valid (cached reads count as zero new input but turn-over-turn DELTA of non-cached prefix grows monotonically).
- [ ] On assertion failure, the failure message includes: provider name, model name, the 3-turn token-count sequence, and a hint pointing at the F6 KI #2 root-cause categorization (Ollama-side vs ours)
- [ ] The test file follows the project's test-helper conventions: module-level helpers for the conversation-driver pattern shared across the 4 provider tests (DRY)
- [ ] Tests respect existing `tests/conftest.py` infrastructure: no new conftest entries needed; `THE_ONE_DATA_DIR` isolation still in effect (relevant if any provider reads from data dir)
- [ ] `pyproject.toml:59` per-marker deselect math updated. The implementer MUST first verify the current live count via `docker exec the-one pytest --collect-only -m live -q | tail -3` and then add 4 — L01 did NOT add live tests (its `test_llm_max_context.py` tests are mocks, NOT live), so the current count should still be 6 going to 10. Verify rather than assume.
- [ ] Broad pytest exits 0 with pass count UNCHANGED from L01-landed 1669 (new tests deselected by `live` marker, not counted in default run); skipped/deselected counts: `4 skipped, 374 deselected` (370 + 4 new)
- [ ] Browser suite preserved at 315 passing / 35 skipped
- [ ] L02 commits ship the test file but DO NOT run the live tests in CI; documentation for the operator-runnable diagnostic is captured in either agents.md or the test module's docstring (preferring the docstring if no clear doc home for the broader test-invocation convention)

## Verification Steps

- **Collection**: `docker exec the-one pytest --collect-only tests/test_input_tokens_cross_provider_live.py` lists 4 tests
- **Default CI exclusion**: `docker exec the-one pytest tests/test_input_tokens_cross_provider_live.py -v --tb=line` reports 4 deselected (because `addopts` includes `-m 'not live'`)
- **Live invocation (operator)**: `docker exec -e ANTHROPIC_API_KEY=... the-one pytest -m live tests/test_input_tokens_cross_provider_live.py::test_anthropic_input_tokens_monotonic -v` — runs the test against real Anthropic; passes if `input_tokens` grows monotonically
- **Skip behavior**: `docker exec the-one pytest -m live tests/test_input_tokens_cross_provider_live.py -v` (no env vars set) — all 4 tests SKIP with descriptive messages, exit code 0
- **Per-marker math**: `docker exec the-one pytest --collect-only -m live -q | tail -5` shows the deselect count consistent with the updated `pyproject.toml` comment
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1669p/4s/374d (deselected up by 4)
- **Browser suite**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` returns 315/35

## Implementation Guidance

1. **Create `tests/test_input_tokens_cross_provider_live.py`**:

   ```python
   """Cross-provider validation that `Message.usage.input_tokens` grows
   monotonically with conversation history.

   F6 L06 HAT (M08 KI #2): operator observed Ollama reporting flat
   ``prompt_tokens`` around ~1000 after a multi-turn qwen conversation.
   Agent sends full history every turn (the_one/agent/core.py), so a
   flat prompt-token count means the provider is undercounting. This
   harness localizes the symptom: if Ollama undercounts AND another
   provider on the same conversation shape reports growing counts, the
   issue is Ollama-side. If all providers undercount, our request shape
   is at fault.

   Marker: ``@pytest.mark.live`` — deselected from default CI. Run with
   ``pytest -m live`` and the relevant provider credentials set in env.

   Cost: each test runs 3 real LLM calls with short prompts. Cheap-model
   selections keep this minimal; operator should verify their selected
   model in the provider's pricing docs.
   """
   from __future__ import annotations

   import os
   import pytest

   from the_one.llm.base import Message


   async def _run_three_turn_conversation(provider, model_label: str) -> list[int]:
       """Run a 3-turn conversation; return [input_tokens turn1, turn2, turn3]."""
       prompts = [
           "Reply with the single word: hello.",
           "Now reply with the single word: world.",
           "Now reply with the single word: again.",
       ]
       messages: list[Message] = []
       counts: list[int] = []
       for user_text in prompts:
           messages.append(Message.user(user_text))
           response = await provider.complete(messages=messages)
           assert response.usage is not None, (
               f"{model_label}: no usage reported by provider"
           )
           counts.append(response.usage.input_tokens)
           messages.append(response)  # append assistant for next turn's history
       return counts


   def _assert_monotonic_growth(counts: list[int], provider_name: str, model: str) -> None:
       assert all(c > 0 for c in counts), (
           f"{provider_name}/{model}: input_tokens not positive for all turns: {counts}"
       )
       assert counts[0] <= counts[1] <= counts[2], (
           f"{provider_name}/{model}: input_tokens NOT monotonically non-decreasing "
           f"across 3 turns: {counts}. "
           f"This is the F6 KI #2 symptom — the provider is undercounting prompt tokens. "
           f"If only Ollama shows this, the bug is Ollama-side. "
           f"If multiple providers show this, the agent's request shape is at fault."
       )


   @pytest.mark.live
   async def test_anthropic_input_tokens_monotonic() -> None:
       if not os.environ.get("ANTHROPIC_API_KEY"):
           pytest.skip("ANTHROPIC_API_KEY not set")
       from the_one.llm.anthropic_provider import AnthropicProvider
       model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
       provider = AnthropicProvider(model=model)
       counts = await _run_three_turn_conversation(provider, f"anthropic/{model}")
       _assert_monotonic_growth(counts, "anthropic", model)


   @pytest.mark.live
   async def test_openai_input_tokens_monotonic() -> None:
       if not os.environ.get("OPENAI_API_KEY"):
           pytest.skip("OPENAI_API_KEY not set")
       from the_one.llm.openai_provider import OpenAIProvider
       model = os.environ.get("LIVE_OPENAI_MODEL", "gpt-4o-mini")
       provider = OpenAIProvider(model=model)
       counts = await _run_three_turn_conversation(provider, f"openai/{model}")
       _assert_monotonic_growth(counts, "openai", model)


   @pytest.mark.live
   async def test_ollama_input_tokens_monotonic() -> None:
       base_url = os.environ.get("LIVE_OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
       # Probe Ollama; skip if not reachable
       import httpx
       try:
           tags_url = base_url.rstrip("/").rstrip("/v1") + "/api/tags"
           async with httpx.AsyncClient(timeout=5) as client:
               resp = await client.get(tags_url)
               if resp.status_code != 200:
                   pytest.skip(f"Ollama at {base_url} not reachable: HTTP {resp.status_code}")
               tags = resp.json().get("models", [])
       except (httpx.HTTPError, OSError) as e:
           pytest.skip(f"Ollama at {base_url} not reachable: {e}")
       if not tags:
           pytest.skip(f"Ollama at {base_url} has no models loaded")
       # Prefer qwen2.5:7b (the F6 bug-report model); else first available
       preferred = os.environ.get("LIVE_OLLAMA_MODEL")
       available_names = [t.get("name") or t.get("model") for t in tags]
       if preferred and preferred in available_names:
           model = preferred
       elif "qwen2.5:7b" in available_names:
           model = "qwen2.5:7b"
       else:
           model = available_names[0]
       from the_one.llm.ollama_provider import OllamaProvider
       provider = OllamaProvider(model=model, base_url=base_url)
       counts = await _run_three_turn_conversation(provider, f"ollama/{model}")
       _assert_monotonic_growth(counts, "ollama", model)


   @pytest.mark.live
   async def test_openrouter_input_tokens_monotonic() -> None:
       if not os.environ.get("OPENROUTER_API_KEY"):
           pytest.skip("OPENROUTER_API_KEY not set")
       from the_one.llm.openrouter_provider import OpenRouterProvider
       model = os.environ.get("LIVE_OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
       provider = OpenRouterProvider(model=model)
       counts = await _run_three_turn_conversation(provider, f"openrouter/{model}")
       _assert_monotonic_growth(counts, "openrouter", model)
   ```

2. **Update `pyproject.toml`** — the comment at line 59 currently says `live=6`. After this leg lands, the count is `live=10`. Update the comment AND verify the count is accurate via `pytest --collect-only -m live`.

3. **Run targeted verification**:

   ```bash
   docker exec the-one pytest --collect-only tests/test_input_tokens_cross_provider_live.py -q
   # Should list 4 tests, all marked `live`

   docker exec the-one pytest tests/test_input_tokens_cross_provider_live.py -v
   # All 4 should be DESELECTED (default run excludes `live`)

   docker exec the-one pytest -m live tests/test_input_tokens_cross_provider_live.py -v
   # No env vars set → all 4 SKIP with descriptive messages
   ```

4. **Run broad pytest**:

   ```bash
   docker exec the-one pytest -x --timeout 30
   # Expect 1669 passed (UNCHANGED), 4 skipped, 374 deselected (was 370 + 4 new)
   ```

5. **Run browser suite**:

   ```bash
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   # Expect 315/35 unchanged
   ```

6. **Update flight log** — Leg Progress entry: file added, deselect-count math updated, no default-CI impact.

7. **Do NOT commit** — Flight Director batches commits after L02.

## Edge Cases

- **`@pytest.mark.asyncio` vs project async fixtures**: the project's `tests/conftest.py` sets `asyncio_default_fixture_loop_scope=None` and the project uses async test functions throughout (e.g., `tests/test_llm_max_context.py` from L01). Verify the L02 tests use the same async-test idiom — should be `@pytest.mark.asyncio` if explicit, or rely on `asyncio: mode=Mode.AUTO` set in `pyproject.toml`. Confirm during impl.
- **Provider construction with missing keys**: `OpenAIProvider(model="gpt-4o-mini")` without `OPENAI_API_KEY` in env: the openai SDK reads `OPENAI_API_KEY` at construction. If absent, the SDK raises `openai.OpenAIError`. The test calls `pytest.skip` BEFORE construction so this is moot. Same for Anthropic (reads `ANTHROPIC_API_KEY` similarly). OpenRouter has its `_NO_KEY_PLACEHOLDER` fallback, so it constructs even without a key — but the 401 would surface mid-test. Skip-before-construct keeps that clean.
- **Ollama probe reachability**: `host.docker.internal` resolves to the host machine from inside the container on Docker Desktop / WSL. On native Linux Docker, the host IP differs. Operator may need to set `LIVE_OLLAMA_BASE_URL` explicitly. The skip message points at this.
- **Model availability mismatch**: an operator running L03 HAT with `LIVE_OLLAMA_BASE_URL` pointing at an Ollama instance that has `llama3.2:3b` but not `qwen2.5:7b` should still get a test result (against `llama3.2:3b`). The model-selection fallback in step 1 handles this.
- **`response.usage = None` for some providers**: per F6 KI #2, Ollama may return `prompt_tokens=0` if its tokenizer is misconfigured for a model. The test's `_assert_monotonic_growth` asserts `c > 0` first; a 0-value triggers the same diagnostic message. The test FAILS clearly rather than silently passing on a degenerate sequence.
- **First-turn input_tokens is small**: turn 1 sends only the system prompt (if any) + the user message. Anthropic providers ship without a default system prompt unless one is passed — turn 1 prompt is ~5-10 tokens. Subsequent turns include the assistant response, so they grow more meaningfully. Monotonic non-decreasing is the right assertion, not strictly greater.
- **Anthropic key-family mismatch** (cycle-1 reviewer): an operator's `ANTHROPIC_API_KEY` may be scoped to a model family that doesn't include the default `claude-haiku-4-5-20251001`. The Anthropic SDK raises `anthropic.PermissionDeniedError` or `anthropic.AuthenticationError` on the first `complete()` call. Add a `try/except` in the test body that catches these specifically and re-skips with a descriptive message pointing at `LIVE_ANTHROPIC_MODEL` for override. Same pattern for the other providers' permission failures.
- **Provider client teardown** (cycle-1 reviewer suggestion): Anthropic and OpenAI SDK clients hold async HTTP connection pools. Without explicit `await provider.client.aclose()` (or equivalent) at test end, pytest may emit "unclosed async client" warnings on live runs. The DRY harness `_run_three_turn_conversation` could accept a teardown callback OR each test could wrap the call in a try/finally. Minor — warnings aren't failures — but worth doing cleanly.
- **`Message.system(...)` prompt presence**: the harness does NOT pass a system prompt; the conversation is pure user/assistant. Some providers prepend an internal system prompt (e.g., Anthropic counts the empty-string system as 0). Verify by running against Anthropic first during L03 HAT.

## Files Affected

- `tests/test_input_tokens_cross_provider_live.py` — NEW
- `pyproject.toml:59` — update per-marker math comment (`live=6` → `live=10`)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exit 0 with 1669p/4s/374d; browser suite 315/35 preserved)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet
- [ ] Do NOT commit — Flight Director batches commits after L02

---

## Citation Audit

5 source-code citations verified against current code at leg design time:
- `pyproject.toml:59 — "Per-marker deselect math (last verified L0): live=6, ..."` — OK
- `pyproject.toml:62 — "live: marks tests that call real LLM APIs"` — OK
- `tests/test_aiat.py:101 — "@pytest.mark.live"` — OK (existing usage pattern reference)
- `the_one/llm/base.py:Message`, `the_one/llm/base.py:TokenUsage` — return shape, no line drift expected
- `the_one/llm/openrouter_provider.py:_NO_KEY_PLACEHOLDER` (cited in Edge Cases) — verified at L01 design time

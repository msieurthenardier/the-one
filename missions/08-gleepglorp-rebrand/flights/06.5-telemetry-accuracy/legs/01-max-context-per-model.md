# Leg: max-context-per-model

**Status**: completed
**Flight**: [Telemetry Accuracy](../flight.md)

## Objective

Convert `LLMProvider.max_context_tokens` from a class attribute (hardcoded 128k default with only Anthropic overriding to 200k) into an instance attribute resolved lazily from provider model metadata on the first `complete()` / `stream()` call. Per-provider:

- **Anthropic**: no-op (class default 200k is correct for all current Claude models)
- **Ollama**: query `/api/show`, walk `model_info` for a key ending in `.context_length`
- **OpenAI**: hardcoded `OPENAI_MODEL_CONTEXT` dict lookup by model-name prefix
- **OpenRouter**: query `list_models(base_url, api_key)`, match by `entry.id`, read `entry.context_length` (new `get_model_context_length` helper in `openrouter_api.py`)

Failure-path caching: the resolver sets a sentinel flag `_max_context_tokens_resolved = True` regardless of fetch outcome so a failed metadata fetch falls back to the class default ONCE, not on every subsequent call.

## Context

- **Design Decision (flight.md)**: "`max_context_tokens` is an instance attribute, resolved lazily on first LLM call." Class attribute stays as fallback (128k for base, 200k for Anthropic). Provider `__init__` stays sync; resolver runs at top of `complete()` and `stream()`.
- **Recon (flight-log.md rows 1, 11, 12, 13, 16)**: confirmed-live — `the_one/llm/base.py:87` has class-level `max_context_tokens: int = 128_000`. Only reader sites are `the_one/interfaces/web/app.py:689` (`_broadcast_one`) and `:752` (`_process_and_broadcast`), both fire AFTER `agent.step()` triggers the first LLM call. No pre-call readers.
- **Ollama `model_info` shape (verified live at cycle-1)**: `/api/show` for `qwen2.5:7b` returns `model_info.qwen2.context_length = 32768`. Top-level keys follow `{family}.{field}` pattern (e.g., `qwen2.attention.head_count`, `qwen2.block_count`, `llama.context_length` for llama models). The `.context_length` suffix match works across families.
- **OpenRouter resolver path (cycle-1 corrected)**: `get_model_capabilities(base_url, api_key, model)` returns `frozenset[str] | None` of `supported_parameters` — does NOT expose `context_length`. The `context_length` field IS on `OpenRouterModelEntry` (`openrouter_api.py:47`) but only reachable via `list_models(base_url, api_key)`. L01 adds a sibling helper `get_model_context_length` next to `get_model_capabilities` for symmetry.
- **`OllamaProvider.supports_tools`** (`ollama_provider.py:42-50`) is the canonical async-helper-with-cache pattern. The new `_resolve_max_context_tokens` mirrors that shape: queries an async API helper, falls back gracefully.
- **`OpenRouterProvider`** stashes `_lookup_api_key` and `_lookup_base_url` on `__init__` (`openrouter_provider.py:94-98`) explicitly for capability-lookup calls. The new resolver uses the same fields.

## Inputs

Files that exist before this leg runs:
- `the_one/llm/base.py` — `LLMProvider.max_context_tokens` at line 87 (class attribute, 128_000)
- `the_one/llm/anthropic_provider.py:15` — class override (`max_context_tokens = 200_000`)
- `the_one/llm/openai_provider.py` — no override; inherits class default
- `the_one/llm/ollama_provider.py` — no override; `supports_tools` async pattern at lines 42-50
- `the_one/llm/openrouter_provider.py` — extends OpenAIProvider; `_lookup_api_key` + `_lookup_base_url` stashed at lines 94-98 for capability lookups
- `the_one/llm/openrouter_api.py` — `list_models` at line 83, `OpenRouterModelEntry.context_length` at line 47, `get_model_capabilities` at line 169
- `the_one/llm/ollama_api.py` — `show_model` at line 108, `get_model_capabilities` at line 145

State that must be true:
- F6 merged to main (✓ commit `1e34951`)
- Broad pytest 1627p/4s/370d exit 0; browser suite 315p/35s (✓ at F6 close)
- Container `the-one` running

## Outputs

Files modified:
- `the_one/llm/base.py` — `LLMProvider` gains an `async def _resolve_max_context_tokens()` method with a default no-op body (subclasses override). The class attribute `max_context_tokens: int = 128_000` STAYS as the default; subclasses can still override at the class level (Anthropic). Adds an instance-level sentinel attribute `_max_context_tokens_resolved: bool = False` (set lazily after first resolution).
- `the_one/llm/anthropic_provider.py` — no change to the class-level `max_context_tokens = 200_000`. NO override of `_resolve_max_context_tokens` (default no-op is fine; the class default already reflects the real value).
- `the_one/llm/openai_provider.py` — adds module-scope `OPENAI_MODEL_CONTEXT: dict[str, int]` with common-model prefix → context_length pairs; overrides `_resolve_max_context_tokens` to look up by prefix match and set `self.max_context_tokens` to the matched value (or leave at class default).
- `the_one/llm/ollama_api.py` — adds module-scope `extract_ollama_context_length(show_response: dict) -> int | None` helper that walks `model_info` for `.context_length`-suffix keys.
- `the_one/llm/ollama_provider.py` — overrides `_resolve_max_context_tokens` to call `ollama_api.show_model(self.base_url, self.model)`, pass through `extract_ollama_context_length`, set `self.max_context_tokens` to the resolved value (or leave at class default).
- `the_one/llm/openrouter_api.py` — adds new helper `get_model_context_length(base_url, api_key, model) -> int | None` mirroring `get_model_capabilities`'s fail-open semantics; reuses `list_models` (same cache).
- `the_one/llm/openrouter_provider.py` — overrides `_resolve_max_context_tokens` to call the new `get_model_context_length` helper, set `self.max_context_tokens` to the resolved value (or leave at class default).
- All four providers (`anthropic_provider.py`, `openai_provider.py`, `ollama_provider.py`, `openrouter_provider.py`): each `complete()` and `stream()` method gains a single line at the top — `await self._resolve_max_context_tokens_if_needed()` — that runs the resolver exactly once per instance.
- `tests/test_llm_max_context.py` — NEW unit-test file: per-provider tests with mocked metadata responses covering success path (resolved value set correctly) AND failure path (network/HTTP error → falls back to class default; sentinel flag still flips so a second call doesn't retry).

State after:
- `LLMProvider.max_context_tokens` is now an INSTANCE attribute on every constructed provider (set during first `complete()`/`stream()`). Class default 128k stays for fallback.
- A `qwen2.5:7b`-via-Ollama agent's telemetry shows context fill against the model's real 32k window, not 128k.
- An OpenRouter `anthropic/claude-3.5-sonnet` agent (or any other model) shows the real context window from the OpenRouter listing.
- An OpenAI `gpt-4o` agent shows 128k (already correct); `gpt-4` shows 8k; `gpt-3.5-turbo` shows 16k.
- A failing metadata fetch (Ollama server down, OpenRouter API hiccup, etc.) gracefully falls back to class default and does NOT retry on every subsequent message.
- Broad pytest still passes (new tests add to count; no regression).

## Acceptance Criteria

- [ ] `the_one/llm/base.py` adds `async def _resolve_max_context_tokens(self) -> None:` as a no-op default on `LLMProvider`; subclasses override
- [ ] `the_one/llm/base.py` adds a class attribute / `__init__` initializer for `_max_context_tokens_resolved: bool = False` (initialized to False; flipped to True by the wrapper at FIRST call)
- [ ] `the_one/llm/base.py` adds a wrapper `async def _resolve_max_context_tokens_if_needed(self) -> None:` on `LLMProvider` that: short-circuits if `_max_context_tokens_resolved`; otherwise calls `_resolve_max_context_tokens()` (catches all exceptions to log + continue); sets `_max_context_tokens_resolved = True` UNCONDITIONALLY (failure-path caching)
- [ ] All four providers' `complete()` and `stream()` methods call `await self._resolve_max_context_tokens_if_needed()` as the FIRST line of the body (before any other awaitable or HTTP request)
- [ ] `AnthropicProvider` — class-level `max_context_tokens = 200_000` UNCHANGED; NO override of `_resolve_max_context_tokens` (default no-op is the correct behavior — 200k stays)
- [ ] `the_one/llm/openai_provider.py` — adds module-scope `OPENAI_MODEL_CONTEXT: dict[str, int]` with entries (cycle-1 reviewer expanded coverage to defeat the prefix-match trap on legacy `gpt-4`): `"gpt-4o"` → 128_000, `"gpt-4-turbo"` → 128_000, `"gpt-4-32k"` → 32_768, `"gpt-4-vision-preview"` → 128_000, `"gpt-4-0125-preview"` → 128_000, `"gpt-4-1106-preview"` → 128_000, `"gpt-4"` → 8_192, `"gpt-3.5-turbo-instruct"` → 4_096, `"gpt-3.5-turbo-16k"` → 16_385, `"gpt-3.5-turbo"` → 16_385, `"o1"` → 200_000, `"o3-mini"` → 200_000. Add a docstring noting the table is hand-maintained (canonical reference: https://platform.openai.com/docs/models — link in docstring); drifts as OpenAI ships new models; unknowns fall back to class default.
- [ ] `OpenAIProvider._resolve_max_context_tokens` looks up `self.model` by prefix match against `OPENAI_MODEL_CONTEXT` keys (longest-prefix wins on tie — match `gpt-4-turbo` before `gpt-4`); sets `self.max_context_tokens` if found, leaves at class default otherwise.
- [ ] `the_one/llm/ollama_api.py` — adds module-scope `extract_ollama_context_length(show_response: dict) -> int | None` that walks `show_response.get("model_info", {})` for any key ending in `.context_length`; returns the first int value found or None.
- [ ] `OllamaProvider._resolve_max_context_tokens` calls `ollama_api.show_model(self.base_url, self.model)`, passes the response through `extract_ollama_context_length`, sets `self.max_context_tokens` if non-None. On `show_model` exception (network error, model missing, malformed): leave at class default. The `_max_context_tokens_resolved` sentinel still flips (failure-path caching).
- [ ] `the_one/llm/openrouter_api.py` — adds module-scope `async def get_model_context_length(base_url: str, api_key: str | None, model: str) -> int | None` that calls `list_models` (cached) and walks for `entry.id == model`; returns `entry.context_length` or None. Failure semantics mirror `get_model_capabilities`: log warning + return None on `httpx.HTTPError` or `ValueError`.
- [ ] `OpenRouterProvider._resolve_max_context_tokens` calls the new helper with `self._lookup_base_url` and `self._lookup_api_key`; sets `self.max_context_tokens` if non-None, leaves at class default otherwise.
- [ ] New file `tests/test_llm_max_context.py` covers each provider with mocked metadata responses:
  - Success path: resolver sets `self.max_context_tokens` to the resolved value
  - Failure path (each provider's relevant failure mode): resolver leaves `self.max_context_tokens` at class default AND flips `_max_context_tokens_resolved` (verified by calling the resolver TWICE and asserting the mock is called ONCE)
  - For OpenAI specifically: prefix-match correctness — must explicitly cover the cycle-1-flagged tricky models that previously would have hit the legacy `gpt-4` 8k trap: `"gpt-4o-2024-05-13"` → 128_000, `"gpt-4-1106-preview"` → 128_000 (NOT 8k), `"gpt-4-0125-preview"` → 128_000 (NOT 8k), `"gpt-4-vision-preview"` → 128_000 (NOT 8k), `"gpt-4-32k-0613"` → 32_768 (NOT 8k), `"gpt-4-0613"` → 8_192 (legacy gpt-4 default IS 8k), `"gpt-3.5-turbo-instruct"` → 4_096, `"gpt-3.5-turbo-16k"` → 16_385, unknown model `"my-finetune"` falls back to class default. The longest-prefix-wins ordering MUST sort `gpt-4-32k` and the `*-preview` variants BEFORE plain `gpt-4`
  - For Ollama: the `extract_ollama_context_length` helper unit tests against synthetic `model_info` shapes (qwen2, llama, mistral, missing, malformed)
- [ ] Broad pytest exits 0 with pass count ≥ L05-landed 1627 + new tests (expect ~1635-1645 passed; no NEW failures, no NEW skips)
- [ ] Browser suite preserved at 315 passing / 35 skipped
- [ ] No change to `LLMProvider` ABCs that breaks the existing `MockProvider` / `FakeLLM` test fixtures (verify by running broad pytest)

## Verification Steps

- **Resolver runs once per instance**: unit test in `test_llm_max_context.py` constructs each provider, mocks the metadata helper, calls `_resolve_max_context_tokens_if_needed` TWICE, asserts the mock was called ONCE.
- **Failure-path caching**: same test pattern but the mock raises `httpx.HTTPError` on first call; asserts the second call still does NOT invoke the mock (sentinel flag respected), and `self.max_context_tokens` equals the class default.
- **Ollama family-key extraction**: unit tests on `extract_ollama_context_length` with synthetic `model_info` dicts: `{"qwen2.context_length": 32768}` → 32768; `{"llama.context_length": 8192}` → 8192; `{"foo.bar.context_length": 2048}` → 2048 (multi-segment family); `{"qwen2.attention.head_count": 32}` → None (no context_length key); `{}` → None.
- **OpenAI prefix match**: unit tests on `OPENAI_MODEL_CONTEXT` lookup: `"gpt-4o"` → 128000; `"gpt-4o-2024-05-13"` → 128000 (prefix match); `"gpt-4"` → 8192; `"gpt-4-turbo-preview"` → 128000 (matches `gpt-4-turbo`, NOT `gpt-4`); `"unknown-model"` → falls back.
- **OpenRouter live-shape sanity** (optional, requires API key): `python -c "import asyncio; from the_one.llm.openrouter_api import get_model_context_length; print(asyncio.run(get_model_context_length('https://openrouter.ai/api/v1', None, 'anthropic/claude-3.5-sonnet')))"` returns 200000 or None (depending on whether OpenRouter requires auth for `/models`).
- **Reader sites unaffected**: run targeted tests that touch `app.py:_process_and_broadcast` (`tests/test_auto_load.py`, `tests/test_app_websocket_pause_resume.py`); they should pass without modification (resolved value populates instance attr before reader is hit).
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0; pass count grows by the number of new unit tests.
- **Browser suite**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` returns 315/35.

## Implementation Guidance

1. **Edit `the_one/llm/base.py`** — add `_max_context_tokens_resolved`, `_resolve_max_context_tokens`, and `_resolve_max_context_tokens_if_needed`:

   ```python
   class LLMProvider(ABC):
       name: str
       max_context_tokens: int = 128_000

       def __init__(self) -> None:
           # Sentinel for lazy max_context_tokens resolution. Set True after
           # first _resolve_max_context_tokens_if_needed() call (regardless
           # of fetch outcome) to prevent retry storms on metadata-fetch
           # failure. M08 F6.5 L01.
           self._max_context_tokens_resolved: bool = False

       async def _resolve_max_context_tokens(self) -> None:
           """Subclasses override to query provider metadata and set
           self.max_context_tokens to the per-model value. Default no-op
           (class attribute is the resolved value)."""

       async def _resolve_max_context_tokens_if_needed(self) -> None:
           """Lazy resolver. Idempotent — short-circuits after first call.
           Catches all exceptions so a metadata-fetch failure falls back
           to the class default without breaking the LLM call.
           """
           if self._max_context_tokens_resolved:
               return
           try:
               await self._resolve_max_context_tokens()
           except Exception:
               logger.debug(
                   "max_context_tokens resolution failed for %s; using default %d",
                   self.name,
                   self.max_context_tokens,
                   exc_info=True,
               )
           finally:
               # ALWAYS flip the sentinel — failure-path caching prevents
               # retry-on-every-call when metadata is unreachable.
               self._max_context_tokens_resolved = True

       # ... existing abstract methods unchanged ...
   ```

   Note: `LLMProvider` currently has no `__init__`. The new `__init__` MUST be safe — subclasses that don't call `super().__init__()` (e.g., `OpenRouterProvider`) need their own init to set the sentinel. Pattern: initialize the sentinel at the top of each provider's `__init__` AND add `super().__init__()` where safe (Anthropic, OpenAI, Ollama). For OpenRouter (which overrides __init__ entirely, line 63 comment), add `self._max_context_tokens_resolved = False` directly. **Audit each provider's __init__ during implementation.**

   Add the logger import at top of `base.py` if not present:

   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```

2. **Edit `the_one/llm/anthropic_provider.py`** — no functional changes. Add `super().__init__()` call at the top of `__init__` (after the existing assignments) so the sentinel initializes. NO override of `_resolve_max_context_tokens` — the class default 200k is the resolved value.

3. **Edit `the_one/llm/openai_provider.py`** — add the lookup table at module scope:

   ```python
   # M08 F6.5 L01: per-model context-window lookup. OpenAI doesn't expose
   # context_length via the /models API, so this is hand-maintained.
   # Drifts as OpenAI ships new models — unknown models fall back to the
   # class default (128k). Match is by PREFIX (longest-prefix wins).
   # Canonical reference: https://platform.openai.com/docs/models
   # Order matters for the longest-prefix-wins matcher below — explicit
   # variants of gpt-4 / gpt-3.5-turbo MUST appear so prefix-match doesn't
   # collapse them onto the bare gpt-4 (8k) or gpt-3.5-turbo (16k) entry.
   OPENAI_MODEL_CONTEXT: dict[str, int] = {
       "gpt-4o": 128_000,
       "gpt-4-turbo": 128_000,
       "gpt-4-32k": 32_768,
       "gpt-4-vision-preview": 128_000,
       "gpt-4-0125-preview": 128_000,
       "gpt-4-1106-preview": 128_000,
       "gpt-4": 8_192,                # legacy gpt-4 default; -0613 / -0314 dated variants
       "gpt-3.5-turbo-instruct": 4_096,
       "gpt-3.5-turbo-16k": 16_385,
       "gpt-3.5-turbo": 16_385,       # current gpt-3.5-turbo defaults to 16k (was 4k pre-2023)
       "o1": 200_000,
       "o3-mini": 200_000,
   }
   ```

   Add the resolver override:

   ```python
   async def _resolve_max_context_tokens(self) -> None:
       # Longest-prefix match: sort keys descending by length so e.g.
       # "gpt-4-turbo" wins over "gpt-4" when self.model is "gpt-4-turbo-preview".
       for prefix in sorted(OPENAI_MODEL_CONTEXT, key=len, reverse=True):
           if self.model.startswith(prefix):
               self.max_context_tokens = OPENAI_MODEL_CONTEXT[prefix]
               return
       # No match — leave at class default.
   ```

   Add `super().__init__()` at top of `__init__`.

4. **Edit `the_one/llm/ollama_api.py`** — add the helper at module scope (near other helpers):

   ```python
   def extract_ollama_context_length(show_response: dict[str, Any]) -> int | None:
       """Find the ``.context_length`` field in Ollama's /api/show ``model_info``.

       Ollama nests ``context_length`` under a model-family-namespaced key
       (e.g., ``qwen2.context_length``, ``llama.context_length``). This walks
       ``model_info`` for any key ending in ``.context_length`` and returns
       the first int value found.

       Returns None if no matching key or the value isn't an int.
       """
       model_info = show_response.get("model_info", {})
       if not isinstance(model_info, dict):
           return None
       for key, value in model_info.items():
           if isinstance(key, str) and key.endswith(".context_length") and isinstance(value, int):
               return value
       return None
   ```

5. **Edit `the_one/llm/ollama_provider.py`** — add the resolver override:

   ```python
   async def _resolve_max_context_tokens(self) -> None:
       data = await ollama_api.show_model(self.base_url, self.model)
       resolved = ollama_api.extract_ollama_context_length(data)
       if resolved is not None and resolved > 0:
           self.max_context_tokens = resolved
       # else: leave at class default; the wrapper catches show_model exceptions.
   ```

   Add `super().__init__()` at top of `__init__`.

6. **Edit `the_one/llm/openrouter_api.py`** — add the new helper:

   ```python
   async def get_model_context_length(
       base_url: str,
       api_key: str | None,
       model: str,
   ) -> int | None:
       """Return ``context_length`` for ``model`` via OpenRouter ``/models``.

       Mirrors ``get_model_capabilities`` fail-open semantics: returns None
       on any fetch failure, missing model, or absent/null ``context_length``.
       """
       try:
           models = await list_models(base_url, api_key)
       except (httpx.HTTPError, ValueError) as e:
           logger.warning(
               "get_model_context_length failed for model=%s base=%s: %s",
               model, base_url, e, exc_info=True,
           )
           return None
       for entry in models:
           if entry.id == model:
               return entry.context_length if isinstance(entry.context_length, int) else None
       return None
   ```

7. **Edit `the_one/llm/openrouter_provider.py`** — add the resolver override and sentinel init:

   ```python
   async def _resolve_max_context_tokens(self) -> None:
       resolved = await openrouter_api.get_model_context_length(
           self._lookup_base_url,
           self._lookup_api_key,
           self.model,
       )
       if resolved is not None and resolved > 0:
           self.max_context_tokens = resolved
   ```

   In `__init__`, after the existing assignments, add `self._max_context_tokens_resolved = False` (since `super().__init__()` is intentionally NOT called per the file's docstring).

8. **Edit each provider's `complete()` and `stream()` methods** — add `await self._resolve_max_context_tokens_if_needed()` as the FIRST line of each method body. Files: `anthropic_provider.py` (complete + stream), `openai_provider.py` (complete + stream), `ollama_provider.py` (complete + stream), `openrouter_provider.py` (inherits OpenAI's complete + stream — verify the override path; if `OpenRouterProvider` doesn't override complete/stream, the resolver call on `OpenAIProvider.complete` calls `self._resolve_max_context_tokens` which dispatches to the OpenRouter override via Python MRO ✓).

9. **Create `tests/test_llm_max_context.py`** — per-provider unit tests as enumerated in Acceptance Criteria. Use `pytest-mock` or `unittest.mock.AsyncMock` to mock `ollama_api.show_model`, `openrouter_api.list_models`, etc.

10. **Run targeted tests first**, then broad suite:

    ```bash
    docker exec the-one pytest tests/test_llm_max_context.py -x --timeout 30 -v
    docker exec the-one pytest tests/test_auto_load.py tests/test_app_websocket_pause_resume.py -x --timeout 30 -v
    docker exec the-one pytest -x --timeout 30
    docker exec the-one pytest -m browser --timeout 60 --tb=line
    ```

11. **Update flight log** — Leg Progress entry summarizing files changed + test counts.

12. **Do NOT commit** — Flight Director batches commits after L02.

## Edge Cases

- **Per-call wrapper overhead**: every real-provider `complete()` / `stream()` now awaits `self._resolve_max_context_tokens_if_needed()`. Hot path is `if self._max_context_tokens_resolved: return` — coroutine allocation but no actual suspension (the function returns synchronously from the awaitable's perspective). Sub-microsecond noise; not worth optimizing further. The wrapper is async for symmetry with the underlying `_resolve_max_context_tokens` (which IS truly async — Ollama/OpenRouter hit HTTP).
- **Test subclass enumeration** (cycle-1 reviewer): five test-side `LLMProvider` subclasses exist beyond the four real providers — `MockProvider`, `FakeLLM` (`tests/conftest.py`), `_CompleteOnlyProvider` + `_MultiIterLLM` (`tests/test_streaming.py`), `_DummyProvider` (`tests/test_llm_registry.py`). None call `super().__init__()`; all define their own complete/stream. Resolver wrapper never fires for them. Adding `__init__` to `LLMProvider` does NOT break them because they don't invoke `super().__init__()` and don't depend on `_max_context_tokens_resolved` being set.
- **Providers that don't call `super().__init__()`**: `OpenRouterProvider` intentionally skips super (per its own docstring at line 63-65). It MUST manually set `self._max_context_tokens_resolved = False` in its __init__.
- **Concurrent first-message races**: if two `complete()` calls fire simultaneously on the same instance (rare; typically agent loop is serialized), both could race past the `if self._max_context_tokens_resolved: return` check and run the resolver. The second-to-finish would overwrite `self.max_context_tokens` with the same value — benign. No lock needed for this leg.
- **`max_context_tokens` already set to a non-default by subclass (Anthropic)**: the class-level `200_000` on `AnthropicProvider` is itself a class attribute. When the no-op default `_resolve_max_context_tokens` runs, it leaves `self.max_context_tokens` untouched — Python attribute lookup falls through to the class attribute. ✓
- **Resolver writes to `self.max_context_tokens` (instance) vs class attribute**: assigning to an instance attribute creates a new instance attribute shadowing the class default; assigning to the same name as the class attribute does NOT modify the class. ✓
- **`OPENAI_MODEL_CONTEXT` empty model string**: `self.model = ""` would prefix-match nothing → falls back to class default. ✓
- **Ollama running on a model not in the local registry**: `show_model` raises (404 → ValueError per `ollama_api.py:131`). Wrapper catches; sentinel flips; class default stays.
- **OpenRouter `entry.context_length is None`**: type is `int | None`; the helper checks `isinstance(...., int)` before returning. ✓
- **Test doubles do NOT call the resolver wrapper** (cycle-1 reviewer corrected the original edge-case wording): `MockProvider`, `FakeLLM` (`tests/conftest.py`), `_CompleteOnlyProvider` + `_MultiIterLLM` (`tests/test_streaming.py`), `_DummyProvider` (`tests/test_llm_registry.py`) all subclass `LLMProvider` AND define their own `complete()` / `stream()` methods that do NOT call `super().complete/stream`. The leg's edit adds `await self._resolve_max_context_tokens_if_needed()` only to the four REAL providers' (`anthropic_provider.py`, `openai_provider.py`, `ollama_provider.py`, `openrouter_provider.py`) complete/stream methods. The resolver wrapper is therefore NEVER invoked for the test doubles — no network I/O, no AttributeError. The new `LLMProvider.__init__` sets the sentinel even for test doubles that don't call `super().__init__()` only if the doubles inadvertently invoke instance attribute access on `_max_context_tokens_resolved` — they don't, so missing-sentinel is moot. Verify with broad pytest. **Note: the base `LLMProvider.stream()` default implementation (which `_CompleteOnlyProvider` relies on via `tests/test_streaming.py:82`) is NOT modified by this leg — the resolver insertion happens in each real provider's own override of `stream`, not in the base default.**

## Files Affected

- `the_one/llm/base.py` — add sentinel, default no-op resolver, lazy-wrapper, logger import
- `the_one/llm/anthropic_provider.py` — add `super().__init__()`
- `the_one/llm/openai_provider.py` — add `OPENAI_MODEL_CONTEXT`, resolver override, `super().__init__()`; both `complete()` and `stream()` call resolver wrapper
- `the_one/llm/ollama_api.py` — add `extract_ollama_context_length` helper
- `the_one/llm/ollama_provider.py` — add resolver override, `super().__init__()`; both `complete()` and `stream()` call resolver wrapper
- `the_one/llm/openrouter_api.py` — add `get_model_context_length` helper
- `the_one/llm/openrouter_provider.py` — add resolver override; init the sentinel directly (no super)
- `tests/test_llm_max_context.py` — NEW unit-test file

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exit 0; browser suite 315/35 preserved)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md yet — that happens during the post-L02 commit batch
- [ ] Do NOT commit — Flight Director batches commits after L02

---

## Citation Audit

11 source-code citations verified against current code at leg design time:
- `the_one/llm/base.py:87 — "max_context_tokens: int = 128_000"` — OK
- `the_one/llm/anthropic_provider.py:15 — "max_context_tokens = 200_000"` — OK
- `the_one/llm/ollama_provider.py:42-50 — "supports_tools"` — OK
- `the_one/llm/openrouter_provider.py:63-65` docstring on intentional super-skip — OK
- `the_one/llm/openrouter_provider.py:94-98` — `_lookup_api_key` / `_lookup_base_url` stashed — OK
- `the_one/llm/openrouter_api.py:47 — "context_length: int | None = None"` — OK
- `the_one/llm/openrouter_api.py:83 — "async def list_models"` — OK
- `the_one/llm/openrouter_api.py:169 — "async def get_model_capabilities"` — OK
- `the_one/llm/ollama_api.py:108 — "async def show_model"` — OK
- `the_one/llm/ollama_api.py:145 — "async def get_model_capabilities"` — OK
- `the_one/interfaces/web/app.py:689, :752` (reader sites verified) — OK

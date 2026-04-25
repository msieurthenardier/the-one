# Leg: url-normalization-and-backend-cleanup

**Status**: completed
**Flight**: [Agent Integration & Hardening](../flight.md)

## Objective

Consolidate scattered URL normalization logic into two public utility functions in `ollama_api.py` and add a warning log when `unload_model` polling exhausts without confirmation.

## Context

- Flight 03 debrief identified URL normalization as duplicated across 4+ locations
- Two directions of normalization exist: strip `/v1` (for native Ollama API) and ensure `/v1` (for OpenAI-compatible)
- `ollama_api.py` already has `_normalize_url` (private) that strips `/v1`
- `api.py` repeats `.rstrip("/").removesuffix("/v1")` at 3 call sites
- `ollama_provider.py` has inline ensure-`/v1` logic
- `unload_model` polling loop (20 iterations, ~5s) silently exits if model never unloads

## Inputs

- `the_one/llm/ollama_api.py` — `_normalize_url` at line 21-26, `unload_model` at lines 193-221
- `the_one/interfaces/web/api.py` — `_get_ollama_base_url` (line 407), `test_provider` (line 481), `list_provider_models` (line 522)
- `the_one/llm/ollama_provider.py` — inline ensure `/v1` logic at lines 28-32

## Outputs

- `ollama_api.py` exports `strip_v1(url)` and `ensure_v1(url)` as public functions
- All call sites use these functions instead of inline normalization
- `unload_model` logs a warning when polling exhausts

## Acceptance Criteria

- [ ] `strip_v1(url)` is a public function in `ollama_api.py` — strips trailing `/` and `/v1` suffix. Replaces `_normalize_url`.
- [ ] `ensure_v1(url)` is a public function in `ollama_api.py` — strips trailing `/`, adds `/v1` if not present.
- [ ] All internal `ollama_api.py` functions use `strip_v1` instead of `_normalize_url`
- [ ] `api.py` uses `ollama_api.strip_v1()` at all 3 call sites (lines 407, 481, 522) instead of inline `.rstrip("/").removesuffix("/v1")`
- [ ] `ollama_provider.py` uses `ollama_api.ensure_v1()` instead of inline logic (lines 28-32)
- [ ] `unload_model` logs `logger.warning("Model '%s' still running after polling exhausted", model)` when the for-loop completes without returning
- [ ] All existing tests pass
- [ ] New unit tests for `strip_v1` and `ensure_v1` covering: trailing slash, `/v1` suffix, `/v1/` suffix, bare URL, already-correct URL

## Verification Steps

- `grep -n "removesuffix.*v1\|\.endswith.*v1" the_one/interfaces/web/api.py` should return no matches
- `grep -n "_normalize_url" the_one/llm/ollama_api.py` should return no matches
- `python -m pytest tests/ --timeout=30 -x -q` passes

## Implementation Guidance

1. **Rename and make public** in `ollama_api.py`:
   - Rename `_normalize_url` to `strip_v1`, make it public (remove underscore), keep same logic
   - Add `ensure_v1(url)`: `url = url.rstrip("/"); return url if url.endswith("/v1") else f"{url}/v1"`
   - Add `import logging` and `logger = logging.getLogger(__name__)` at module level
   - Update all internal callers of `_normalize_url` to use `strip_v1`

2. **Update `api.py`**:
   - `_get_ollama_base_url` (line 407): replace `provider.base_url.rstrip("/").removesuffix("/v1")` with `ollama_api.strip_v1(provider.base_url)`
   - `test_provider` (line 481): replace `provider.base_url.rstrip("/").removesuffix("/v1")` with `ollama_api.strip_v1(provider.base_url)`
   - `list_provider_models` (line 522): same replacement
   - `ollama_api` is already imported in api.py

3. **Update `ollama_provider.py`**:
   - Import: `from the_one.llm import ollama_api`
   - Replace lines 28-32 with: `self.base_url = ollama_api.ensure_v1(base_url or "http://localhost:11434/v1")`

4. **Add warning in `unload_model`**:
   - After the for-loop (line 215, after the loop body), add: `logger.warning("Model '%s' still running after polling exhausted on %s", model, url)`

5. **Add tests** in `tests/test_provider_api.py` (or a new test file if more appropriate):
   - Test `strip_v1`: `"http://localhost:11434/v1"` → `"http://localhost:11434"`, `"http://localhost:11434/v1/"` → `"http://localhost:11434"`, `"http://localhost:11434"` → `"http://localhost:11434"`, `"http://localhost:11434/"` → `"http://localhost:11434"`
   - Test `ensure_v1`: `"http://localhost:11434"` → `"http://localhost:11434/v1"`, `"http://localhost:11434/v1"` → `"http://localhost:11434/v1"`, `"http://localhost:11434/"` → `"http://localhost:11434/v1"`, `"http://localhost:11434/v1/"` → `"http://localhost:11434/v1"`

## Edge Cases

- URLs with trailing slashes AND `/v1` suffix (e.g., `http://host:11434/v1/`) — both functions handle via `.rstrip("/")`
- Empty or None base_url — `ollama_provider.py` already defaults to `"http://localhost:11434/v1"` before calling `ensure_v1`

## Files Affected

- `the_one/llm/ollama_api.py` — Rename `_normalize_url` to `strip_v1`, add `ensure_v1`, add logger, add warning
- `the_one/interfaces/web/api.py` — Replace 3 inline normalization sites with `ollama_api.strip_v1()`
- `the_one/llm/ollama_provider.py` — Replace inline ensure logic with `ollama_api.ensure_v1()`
- `tests/test_provider_api.py` — Add URL normalization utility tests

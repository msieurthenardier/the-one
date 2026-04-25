# Leg: library-cache-and-tests

**Status**: completed
**Flight**: [Agent Integration & Hardening](../flight.md)

## Objective

Add an in-memory TTL cache to the Ollama library search endpoint and comprehensive tests for it.

## Context

- Flight 03 debrief identified that every library search keystroke hits `https://ollama.com/api/tags` — wasteful and slow
- The model list changes infrequently, so a 5-minute cache is appropriate
- The endpoint is at `GET /api/ollama-library/search?q=...` in `api.py` (lines 665-684)
- No tests exist for this endpoint currently

## Inputs

- `the_one/interfaces/web/api.py` — `search_ollama_library` endpoint (lines 665-684)

## Outputs

- Module-level cache with 5-minute TTL for the full model list
- Subsequent requests filter from cache instead of re-fetching
- Test class covering: basic search, short/empty query, result limiting, cache hit, error handling

## Acceptance Criteria

- [ ] Module-level cache stores the full model list from `https://ollama.com/api/tags` with a timestamp
- [ ] Cache TTL is 5 minutes (300 seconds) — stale cache triggers a fresh fetch
- [ ] Subsequent searches within TTL filter from cached data without making HTTP requests
- [ ] Cache miss or expired cache triggers a new HTTP fetch
- [ ] If the fetch fails and cache exists (even expired), fall back to stale cache
- [ ] New `TestOllamaLibrarySearch` class in `test_provider_api.py` with tests for:
  - Basic search returns matching results
  - Empty/short query returns empty list
  - Results capped at 30
  - Cache hit (second call doesn't make HTTP request)
  - HTTP error returns empty list (no cache) or stale cache (if available)
- [ ] All existing tests pass

## Verification Steps

- `python -m pytest tests/test_provider_api.py::TestOllamaLibrarySearch -v` passes
- `python -m pytest tests/ --timeout=30 -x -q` passes

## Implementation Guidance

1. **Add module-level cache** at the top of the library search section in `api.py`:
   ```python
   _library_cache: dict[str, Any] = {"models": [], "timestamp": 0.0}
   ```

2. **Refactor `search_ollama_library`**:
   - Check if cache is fresh: `time.time() - _library_cache["timestamp"] < 300`
   - If fresh, use `_library_cache["models"]`
   - If stale, fetch from `https://ollama.com/api/tags`, update cache
   - On fetch failure, fall back to stale cache (if any models exist)
   - Filter and return as before
   - Add `import time` at module level

3. **Add tests** in `test_provider_api.py`:
   - `TestOllamaLibrarySearch` class
   - Use `unittest.mock.patch` to mock `httpx.AsyncClient` for the external HTTP call
   - Test cache behavior by calling endpoint twice and asserting mock was called only once
   - Reset cache between tests using a fixture or by directly setting `_library_cache`

## Edge Cases

- **Cache across test isolation**: Tests must reset the module-level cache to avoid cross-test pollution
- **Concurrent requests during cache miss**: Acceptable race — worst case two fetches happen, last one wins
- **Empty model list from API**: Cache it — an empty list is a valid response

## Files Affected

- `the_one/interfaces/web/api.py` — Add cache, refactor search endpoint
- `tests/test_provider_api.py` — New test class

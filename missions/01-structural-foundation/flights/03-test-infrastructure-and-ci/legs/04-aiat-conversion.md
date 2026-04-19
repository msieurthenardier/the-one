# Leg: aiat-conversion

**Status**: completed
**Flight**: [Test Infrastructure & CI Hardening](../flight.md)

## Objective

Convert the standalone IAAT script (`tests/iaat.py`) to a pytest-based AIAT test file (`tests/test_aiat.py`) using httpx and the `@pytest.mark.live` decorator.

## Context

- `tests/iaat.py` uses `requests` (not in project deps) with a custom test runner
- httpx is already a core dependency — use it instead of requests
- `live` marker already registered in pyproject.toml (from Leg 1)
- Tests must be skipped by default (`pytest tests/`) and runnable with `pytest -m live`
- Keep the same test scenarios, just restructure for pytest

## Inputs

- `tests/iaat.py` — current standalone test script with 8 test functions
- `tests/conftest.py` — `live` marker already registered
- `pyproject.toml` — `live` marker config already in `[tool.pytest.ini_options]`

## Outputs

- `tests/test_aiat.py` — pytest-based AIAT tests with `@pytest.mark.live` decorator
- `tests/iaat.py` — deleted (replaced by test_aiat.py)

## Acceptance Criteria

- [x] `tests/iaat.py` deleted
- [x] `tests/test_aiat.py` created with all 8 test scenarios: health, basic_chat, tool_use_file_read, git_status, reset, run_tests, self_awareness, multi_step
- [x] All tests decorated with `@pytest.mark.live`
- [x] Uses `httpx` instead of `requests` for HTTP calls
- [x] Uses pytest fixtures for base_url (from `THE_ONE_TEST_URL` env var or default `http://localhost:8484`)
- [x] Uses pytest fixtures for session_id (unique per test)
- [x] No custom test runner (`if __name__ == "__main__"` block removed)
- [x] Helper functions (chat, reset, assistant_text, has_tool_call, has_tool_result) preserved as module-level helpers or fixtures
- [x] `pytest tests/ -q` runs only unit tests (AIAT excluded by default)
- [x] `pytest -m live --co tests/test_aiat.py` lists AIAT tests without running them
- [x] `ruff check tests/test_aiat.py` clean
- [x] Existing unit tests unaffected (no regressions)

## Verification Steps

- `python3 -m pytest tests/ --tb=short -q` — only unit tests run
- `python3 -m pytest -m live --co tests/test_aiat.py` — lists 8 tests
- `python3 -m pytest tests/ --tb=short -q -m "not live"` — same as default
- `ruff check tests/test_aiat.py`

## Implementation Guidance

1. **Create `tests/test_aiat.py`**
   - Import httpx instead of requests
   - Create a `base_url` fixture that reads `THE_ONE_TEST_URL` env var or defaults to `http://localhost:8484`
   - Create a `session_id` fixture that generates a unique session per test
   - Keep helper functions as module-level functions (chat, reset, assistant_text, has_tool_call, has_tool_result) — they take base_url/session_id as parameters
   - Convert each test function: remove the custom `test()` wrapper, add `@pytest.mark.live` decorator, use standard pytest assertions
   - Fix the typo on line 88: `AssertionError` should be `AssertionError` (actually it's `AssertionError` in the original which is fine since it was in a try/except in the custom runner — but in pytest it won't matter since pytest catches all assertion failures)
   - Remove the `if __name__ == "__main__"` runner block
   - Remove module-level globals (passed, failed, skipped, session_id)

2. **Delete `tests/iaat.py`**

3. **Verify pytest marker filtering**
   - `pytest tests/ -q` should show only unit tests (76 passed)
   - `pytest -m live --co` should list the 8 AIAT tests

## Edge Cases

- **httpx vs requests API differences**: `httpx.post()` uses same interface as `requests.post()` for JSON. `httpx.get()` same. Main difference: httpx uses `response.raise_for_status()` same as requests.
- **Timeout**: httpx uses `timeout=` parameter same as requests
- **Environment variable for base_url**: Tests should work both locally and potentially in CI (if a live agent is available)

## Files Affected

- `tests/iaat.py` — Delete
- `tests/test_aiat.py` — Create

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (unit tests only — AIAT tests can't be verified without live agent)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)

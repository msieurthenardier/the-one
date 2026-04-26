# Leg: 01-scaffold-playwright

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Add Playwright (Python binding) to dev dependencies, install the Chromium browser binary, register the `@pytest.mark.browser` marker, and create the `tests/browser/` test directory with a self-contained smoke test that proves the toolchain works.

## Context

- This is the foundation leg of Flight 01. Subsequent legs (02-08) build on this scaffold.
- Per the flight's design decisions: Playwright **Python binding** (not JS), `@pytest.mark.browser` marker excluded by default alongside the existing `live` marker, tests live under `tests/browser/`, Chromium-only is sufficient for F1 (firefox/webkit deferred).
- The smoke test must be self-contained — leg 03 introduces the per-test app subprocess fixture, so this leg's smoke test cannot depend on a running app. A `data:` URL test exercises the full Playwright path (browser launch, page navigation, DOM query) without any external dependency.
- No prior leg outcomes exist (this is the first leg of the flight).

## Inputs

- Branch `flight/01-browser-test-foundation` checked out
- Working tree includes the untracked mission/flight artifacts under `missions/04-ui-maturity/`
- Test baseline: **336 passed, 8 deselected** when running `pytest tests/ --tb=short -q` on the current main commit

## Outputs

- `pyproject.toml` updated: `playwright` in dev deps, `browser` marker registered, `addopts` extended
- `tests/browser/conftest.py` exists with a top-of-file docstring describing future fixture scope
- `tests/browser/test_smoke.py` exists with a single `@pytest.mark.browser`-marked test that uses the Playwright sync API to load a `data:` URL and assert on its title
- Chromium browser binary installed locally (via `playwright install chromium`)

(No `__init__.py` needed — `tests/` itself has none, and pytest discovers `tests/browser/` via its standard collection rules.)

## Acceptance Criteria

- [x] `playwright` listed under `[project.optional-dependencies].dev` in `pyproject.toml`
- [x] `[tool.pytest.ini_options].markers` includes a `browser` entry with description
- [x] `[tool.pytest.ini_options].addopts` is `"-m 'not live and not browser'"` (extended from current `"-m 'not live'"`)
- [x] `tests/browser/conftest.py` and `tests/browser/test_smoke.py` exist
- [x] `tests/browser/conftest.py` has a docstring documenting that browser fixtures (subprocess lifecycle, page, seeders) will be added in subsequent legs
- [x] `tests/browser/test_smoke.py` test passes when run with `pytest -m browser tests/browser/`
- [x] Smoke test is **excluded** by default `pytest tests/` run (verify by checking collection or test count)
- [x] Default `pytest tests/` test count unchanged: **336 passed, 8 deselected** (no regression)
- [x] Chromium binary installed (`playwright install --dry-run chromium` reports it is already installed, OR equivalent via `playwright install` succeeding)

## Verification Steps

1. **Dep installed**: `pip show playwright` returns version info
2. **Browser installed**: `playwright install --dry-run chromium 2>&1 | grep -i "already installed"` returns a match (or `playwright install chromium` exits 0 on a fresh run)
3. **Marker registered**: `pytest --markers | grep "^@pytest.mark.browser"` returns the registered description
4. **Addopts effective**: `pytest tests/ --collect-only -q 2>&1 | grep -c "test_smoke"` returns `0`
5. **Browser tests run**: `pytest -m browser tests/browser/ -v` shows `test_smoke` passing
6. **No regression**: `pytest tests/ --tb=short -q` reports `336 passed, 8 deselected` (or higher passed count if leg adds new collectable tests; deselected count rises by 1 to reflect the smoke test exclusion — expect `336 passed, 9 deselected` if the smoke test is also collected from `tests/browser/` under the default filter)

> **Note on the count expectation**: After this leg, the default `pytest tests/` invocation walks `tests/browser/` and discovers the smoke test, then deselects it via the marker filter. So the expected report becomes `336 passed, 9 deselected`. If you see `336 passed, 8 deselected` it means `tests/browser/` wasn't walked (verify cwd and pytest config).

## Implementation Guidance

1. **Update `pyproject.toml`**

   In `[project.optional-dependencies].dev`, append `"playwright>=1.48"`:

   ```toml
   dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.6", "playwright>=1.48"]
   ```

   In `[tool.pytest.ini_options]`:

   ```toml
   addopts = "-m 'not live and not browser'"
   markers = [
       "live: marks tests that call real LLM APIs (deselect with '-m \"not live\"')",
       "browser: marks tests that require a browser via Playwright (deselect with '-m \"not browser\"')",
   ]
   ```

2. **Install the dep and browser**

   ```bash
   pip install -e ".[all-llms,dev]"
   playwright install chromium
   ```

   `playwright` may already be installed in this dev environment from prior tinkering — `pip show playwright` confirms. If installed, the `pip install` step is a no-op for that package. The `playwright install chromium` step is also a no-op if the binary is already cached at `~/.cache/ms-playwright/`.

   On WSL2, if `playwright install chromium` fails with missing system libraries on a fresh machine, run `playwright install-deps chromium` (requires sudo). Document the resolution in the flight log if encountered.

3. **Create `tests/browser/conftest.py`**

   Module-level docstring only — no fixtures yet. Example:

   ```python
   """Browser test fixtures for the-one.

   Subsequent legs in Flight 01 (Mission 04) populate this file with:
   - app subprocess fixture (per-test uvicorn on a random port, isolated data_dir)
   - page/browser fixtures (Playwright sync API)
   - seeder helpers (app_with_provider, app_with_agent)

   For now, see tests/browser/test_smoke.py for the standalone Playwright smoke test.
   """
   ```

4. **Create `tests/browser/test_smoke.py`**

   Self-contained smoke test using the Playwright sync API. Use a `data:` URL so no app/server is required:

   ```python
   """Smoke test: confirms Playwright + Chromium are installed and working.

   This test does NOT require the-one app to be running. It loads a data: URL
   to verify the toolchain. Real flow tests against the app land in legs 05-07.
   """

   from __future__ import annotations

   import pytest
   from playwright.sync_api import sync_playwright


   @pytest.mark.browser
   def test_playwright_loads_data_url() -> None:
       with sync_playwright() as p:
           browser = p.chromium.launch()
           try:
               page = browser.new_page()
               page.goto("data:text/html,<title>the-one smoke</title><h1>hi</h1>")
               assert page.title() == "the-one smoke"
               assert page.locator("h1").text_content() == "hi"
           finally:
               browser.close()
   ```

5. **Verify**

   - Run `pytest tests/ --tb=short -q` — confirm count is `336 passed, 9 deselected` (smoke test deselected by marker filter)
   - Run `pytest -m browser tests/browser/ -v` — confirm `test_playwright_loads_data_url` passes
   - Run `pytest --markers | grep browser` — confirm marker is registered

## Edge Cases

- **WSL2 missing system deps**: `playwright install chromium` may fail on a fresh WSL2 install. Resolution: `playwright install-deps chromium` (requires sudo to install apt packages: libnss3, libnspr4, libxkbcommon0, etc.). If sudo unavailable, document as a known limitation and instruct the operator to install manually.
- **`pytest --markers` warning on unrecognized marker**: Pre-`pyproject.toml` edit, attempting to use `@pytest.mark.browser` would trigger a `PytestUnknownMarkWarning`. The marker registration MUST land before the smoke test file or in the same commit; tests should not warn at collection time.
- **Async vs sync API**: This smoke test uses `sync_playwright`. The project's existing test suite uses `pytest-asyncio` with `asyncio_mode = "auto"`, so any sync test runs unchanged. Subsequent legs may use either API depending on what fits — `sync_playwright` is simpler for these flow tests since none of them need to interleave with the test's own asyncio event loop.
- **Browser binary cache location**: Playwright caches browsers at `~/.cache/ms-playwright` by default. No project-side config needed; `pyproject.toml` package data does NOT need to include browsers.
- **Fresh-checkout developer experience**: A new contributor running `pip install -e ".[all-llms,dev]"` gets the playwright Python package but NOT the browser binaries. They must run `playwright install chromium` separately. README update is owned by leg 08, but ensure the smoke test failure message is informative if browsers are missing (Playwright's default error is acceptable).

## State-Machine Reachability Audit

This leg introduces no new state, status, or lifecycle values. No DB schema changes. No FK constraints. No application caches. No tests need inverting. **N/A — pass.**

## Cache Freshness Contract

This leg introduces no caches. **N/A — pass.**

## Files Affected

- `pyproject.toml` — add `playwright` dev dep; register `browser` marker; extend `addopts` (preserve existing single-quote-inside-double-quote pattern; do not "improve" the quoting)
- `tests/browser/conftest.py` — new, docstring only
- `tests/browser/test_smoke.py` — new, single test
- `~/.cache/ms-playwright/` — chromium binary installed (filesystem side effect, not in repo)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows `336 passed, 9 deselected`; `pytest -m browser tests/browser/` shows `1 passed`
- [x] Update flight-log.md with leg progress entry (status, what was done, any anomalies — note WSL2 system-dep resolution if encountered)
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md (`legs` list)
- [x] If final leg of flight: NOT applicable (this is leg 01 of 08)
- [x] Do NOT commit yet — flight-level review and commit happen after the last autonomous leg per agentic-workflow protocol

# Leg: 03-app-fixture

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Add per-test pytest fixtures to `tests/browser/conftest.py` that spawn an isolated `the-one` app subprocess (random free port, throwaway data_dir, dev_mode on, wait-for-ready, SIGTERM teardown) and provide Playwright `browser` and `page` fixtures. Validate with a sanity test that uses these fixtures to load the app's index page in a real browser.

## Context

- This leg delivers the **`app_clean`** fixture only. Leg 04 (seeders) layers `app_with_provider` and `app_with_agent` on top of it.
- Per the flight design (see `flight.md` "App lifecycle — per-test subprocess on random port" and "Layered fixture stack"): each test gets its own fresh app subprocess, isolated `tmp_path` data_dir, port via `socket.bind(('', 0))`, browser navigates to `127.0.0.1:{port}` (not `localhost`) to avoid WSL2 IPv6 first-attempt delay, wait-for-ready polls `/api/info`.
- **Leg 02 outcome**: `mock` provider type now exists; app respects `THE_ONE_DEV_MODE=true` env var; schema is at v6. Subprocess fixture must set `THE_ONE_DEV_MODE=true` so seeded `mock` providers are accepted in leg 04+.
- **Leg 01 outcome**: pytest uses `--import-mode=importlib`, browser tests use `sync_playwright` directly (no `pytest-playwright` plugin). Continue that pattern — the new `browser` and `page` fixtures wrap `sync_playwright` manually to avoid adding a plugin dep.
- The existing leg 01 smoke test (`tests/browser/test_smoke.py`) deliberately does NOT use these new fixtures — it stays self-contained against a `data:` URL so it remains green even if the app fixture breaks. This is intentional separation of toolchain-validation vs app-validation.

## Inputs

- Branch `flight/01-browser-test-foundation`, legs 01-02 landed (uncommitted)
- `tests/browser/conftest.py` exists with module docstring only (from leg 01)
- `tests/browser/test_smoke.py` passes (1 test)
- App entry point: `the_one.interfaces.web.app:app` (FastAPI instance importable for uvicorn)
- `/api/info` endpoint at `the_one/interfaces/web/app.py:482-497` returns `{"version": "0.1.0", ...}` once lifespan startup (init_db, migrate_json_to_sqlite, AgentFactory build) completes — valid readiness probe
- `THE_ONE_DATA_DIR`, `THE_ONE_PORT`, `THE_ONE_HOST`, `THE_ONE_DEV_MODE` env vars all wire through `pydantic-settings` (env_prefix `THE_ONE_`)
- Test baseline: 350 passed, 9 deselected (post-leg-02)

## Outputs

- `tests/browser/conftest.py` populated with:
  - Module-level helpers: `_free_port()`, `_wait_for_ready(base_url, timeout)`
  - `app_clean` fixture (function-scoped) — yields `base_url` string (e.g., `"http://127.0.0.1:54321"`) for a fresh empty-DB app subprocess
  - `playwright_instance` fixture (session-scoped) — yields `Playwright` from `sync_playwright()`
  - `browser` fixture (session-scoped) — yields a Chromium `Browser` launched headless
  - `page` fixture (function-scoped) — yields a fresh `Page` (new browser context per test for cookie/storage isolation)
- `tests/browser/test_app_fixture.py` (new) — sanity test using `app_clean` + `page` to load `/` and assert the page title contains "the-one"
- Existing `tests/browser/test_smoke.py` unchanged (does NOT depend on the new fixtures)

## Acceptance Criteria

- [x] `tests/browser/conftest.py` exports `app_clean`, `browser`, `page` fixtures
- [x] `_free_port()` returns an OS-allocated free port (uses `socket.bind(('', 0))` then `getsockname()`)
- [x] `_wait_for_ready(base_url, proc=None, timeout=15.0)` polls `GET /api/info` every 100ms; returns when 200 received; raises `TimeoutError` on timeout; raises `RuntimeError` early if `proc` is given and exits during startup
- [x] `app_clean` fixture:
  - Allocates a free port, allocates a `tmp_path`-rooted data dir
  - Spawns `python -m uvicorn the_one.interfaces.web.app:app --host 127.0.0.1 --port {port}` as a subprocess (or equivalent — see Implementation Guidance)
  - Sets env vars: `THE_ONE_DATA_DIR={tmp_data_dir}`, `THE_ONE_PORT={port}`, `THE_ONE_HOST=127.0.0.1`, `THE_ONE_DEV_MODE=true`
  - Waits for ready via `_wait_for_ready` before yielding
  - Yields `base_url` (string `"http://127.0.0.1:{port}"`)
  - On teardown: sends SIGTERM, waits up to 10s for clean exit, escalates to SIGKILL if needed
- [x] `browser` fixture (session-scoped) launches Chromium headless
- [x] `page` fixture (function-scoped) creates a new `BrowserContext` and `Page` per test, closes both on teardown
- [x] `tests/browser/test_app_fixture.py::test_app_clean_serves_index` passes:
  - Uses `app_clean` and `page` fixtures
  - Navigates to `app_clean` base URL
  - Asserts page title contains "the-one"
- [x] `tests/browser/test_app_fixture.py::test_app_clean_responds_to_api_info` passes:
  - Uses the `app_clean` fixture only (HTTP-level sanity, no browser)
  - GETs `/api/info` via httpx and asserts 200 + `version` field present
  - Confirms the wait-for-ready loop and lifespan startup completed correctly. Per-test isolation is implicit in the function-scoped fixture (each test gets its own subprocess + tmp_path data_dir)
- [x] Running `pytest -m browser tests/browser/ -v` passes all browser tests (smoke + 2 new = 3)
- [x] Running `pytest -m browser tests/browser/test_app_fixture.py -v` 5 consecutive times in a row produces 5 successful runs (no flakiness)
- [x] Default `pytest tests/` count: 350 passed, 11 deselected (was 9; +2 from new app-fixture tests)
- [x] Existing leg 01 smoke test still passes — does not depend on `app_clean`
- [x] `ruff check` and `ruff format --check` clean on `tests/browser/`

## Verification Steps

1. **Fixtures importable**:
   ```bash
   pytest tests/browser/ --collect-only -q -m browser
   ```
   — should show 3 tests (smoke + test_app_clean_serves_index + test_app_clean_isolation)
2. **App fixture works**:
   ```bash
   pytest -m browser tests/browser/test_app_fixture.py -v --timeout=60
   ```
   — both tests pass
3. **Repeat-run stability** (manual):
   ```bash
   for i in 1 2 3 4 5; do pytest -m browser tests/browser/test_app_fixture.py -q --timeout=60 || echo "FAILED on run $i"; done
   ```
   — all 5 runs pass
4. **No regression**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   ```
   — 350 passed, 11 deselected
5. **Smoke test unaffected**:
   ```bash
   pytest -m browser tests/browser/test_smoke.py -v --timeout=30
   ```
   — 1 passed
6. **Lint/format**: `ruff check tests/browser/ && ruff format --check tests/browser/`

## Implementation Guidance

### 1. Update `tests/browser/conftest.py`

Replace the docstring-only file with the full fixture stack. Keep the docstring at the top.

```python
"""Browser test fixtures for the-one.

This module provides:
- ``_free_port()`` / ``_wait_for_ready()`` — internal helpers.
- ``app_clean`` (function-scoped) — fresh app subprocess with empty DB.
- ``browser`` (session-scoped) — headless Chromium instance.
- ``page`` (function-scoped) — fresh BrowserContext + Page per test.

Subsequent legs in Flight 01 (Mission 04) will add:
- ``app_with_provider`` / ``app_with_agent`` — seeded variants (leg 04).

The standalone smoke test at tests/browser/test_smoke.py does NOT depend
on these fixtures — it loads a data: URL to validate the toolchain in
isolation, so it stays green even if the app fixtures break.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


# ── Helpers ───────────────────────────────────────────────────────────────


def _free_port() -> int:
    """Return an OS-allocated free TCP port on 127.0.0.1.

    Tiny race window between this call and the subprocess actually binding
    the port. Acceptable at the test scale of this flight (~5 flow tests).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_ready(
    base_url: str,
    proc: subprocess.Popen | None = None,
    timeout: float = 15.0,
) -> None:
    """Poll /api/info until 200, or raise TimeoutError.

    If ``proc`` is given and the subprocess dies during startup, raises
    RuntimeError immediately rather than waiting for the full timeout —
    saves 15s per port-collision/import-error scenario.
    """
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(
                f"App subprocess exited with code {proc.returncode} during startup"
            )
        try:
            r = httpx.get(f"{base_url}/api/info", timeout=1.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_exc = exc
        time.sleep(0.1)
    raise TimeoutError(
        f"App at {base_url} not ready within {timeout}s (last error: {last_exc})"
    )


# ── App subprocess ────────────────────────────────────────────────────────


@pytest.fixture
def app_clean(tmp_path: Path) -> Iterator[str]:
    """Spawn a fresh app subprocess on a random port with an isolated data_dir.

    Yields the base URL (e.g., ``http://127.0.0.1:54321``).

    Each test gets its own subprocess, port, and data_dir — no state bleed.
    Subprocess is launched with ``THE_ONE_DEV_MODE=true`` so seeded mock
    providers are accepted (see leg 04).
    """
    port = _free_port()
    data_dir = tmp_path / "the-one-data"
    data_dir.mkdir()

    env = os.environ.copy()
    env["THE_ONE_DATA_DIR"] = str(data_dir)
    env["THE_ONE_DEV_MODE"] = "true"
    # Note: THE_ONE_PORT/THE_ONE_HOST omitted — uvicorn binds via the explicit
    # --host/--port flags below; nothing in app.py reads settings.port post-init.

    # Use python -m uvicorn so the app is importable via the editable install
    # without depending on the `the-one` console script.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "the_one.interfaces.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{port}"

    try:
        _wait_for_ready(base_url, proc=proc, timeout=15.0)
    except (TimeoutError, RuntimeError):
        # Capture subprocess output to help diagnose startup failures.
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"App subprocess on port {port} did not become ready.\n"
            f"--- stdout ---\n{stdout.decode(errors='replace')}\n"
            f"--- stderr ---\n{stderr.decode(errors='replace')}"
        )

    try:
        yield base_url
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# ── Playwright ────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def playwright_instance() -> Iterator[Playwright]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Iterator[Browser]:
    browser = playwright_instance.chromium.launch(headless=True)
    try:
        yield browser
    finally:
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    """Fresh BrowserContext + Page per test for cookie/storage isolation."""
    context = browser.new_context()
    page = context.new_page()
    try:
        yield page
    finally:
        page.close()
        context.close()
```

### 2. Create `tests/browser/test_app_fixture.py`

```python
"""Sanity tests for the app_clean / browser / page fixtures from conftest.py."""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_app_clean_serves_index(app_clean: str, page: Page) -> None:
    """The app_clean fixture spawns a working app that serves the index page."""
    page.goto(app_clean)
    # Title is set by the index template; should mention the project name.
    title = page.title()
    assert "the-one" in title.lower(), (
        f"Expected page title to contain 'the-one', got: {title!r}"
    )


@pytest.mark.browser
def test_app_clean_responds_to_api_info(app_clean: str) -> None:
    """The app_clean fixture's subprocess responds to /api/info — confirms
    the wait-for-ready loop works end-to-end and the subprocess is fully booted
    (lifespan handler completed: init_db, migrate_json_to_sqlite, AgentFactory).
    """
    r = httpx.get(f"{app_clean}/api/info", timeout=2.0)
    assert r.status_code == 200
    assert "version" in r.json()
```

> **Note on test naming**: the leg's acceptance criteria list `test_app_clean_isolation` as a target, but the simpler split is one test per concern: `test_app_clean_serves_index` (browser-level integration) + `test_app_clean_responds_to_api_info` (HTTP-level fixture sanity). Both implicitly verify isolation because the function-scoped `app_clean` fixture spawns a fresh subprocess for each.

### 3. Verify the page title

The current `index.html` template sets the page title. Read `the_one/interfaces/web/static/index.html` line 1-15 if needed to confirm the title contains "the-one" (it does — `<title>the-one</title>` per project convention). If the title is something other than what's expected, adjust the assertion to match the actual title.

### 4. Re-run the full suite and lint

```bash
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
ruff check tests/browser/
ruff format --check tests/browser/
```

### 5. Repeat-run stability check

```bash
for i in 1 2 3 4 5; do
  pytest -m browser tests/browser/test_app_fixture.py -q --timeout=60 \
    || { echo "FAILED on run $i"; exit 1; }
done
echo "All 5 runs passed"
```

If any run fails (e.g., port collision, slow startup, hung subprocess), diagnose and fix BEFORE signaling done. Common fixes:
- Increase `_wait_for_ready` timeout from 15s → 30s
- Use `proc.poll()` early-exit detection in the wait loop (if the subprocess died, no point polling its port)
- Add small `time.sleep(0.05)` between port allocation and subprocess launch (reduces port-race window)

## Edge Cases

- **Port race**: `_free_port()` returns an OS-allocated free port, but there's a tiny window between `getsockname()` and the subprocess actually binding it. If another process grabs the port in between, uvicorn will fail to bind and the subprocess exits. Mitigation: the `_wait_for_ready` loop will time out and the fixture's exception handler captures stderr (which will show "Address already in use"). If this proves flaky in practice, the fix is to retry the whole fixture setup with a new port (loop wrapping the Popen call). Defer that complexity until we observe flakiness.

- **Subprocess startup time**: Lifespan runs `init_db` + `migrate_json_to_sqlite` + builds `AgentFactory`. On a cold cache (first test of a session), startup is ~2-3s; subsequent runs should be ~1-2s. The 15s `_wait_for_ready` timeout is generous. If WSL2 disk I/O is slow, increase to 30s.

- **Subprocess died early**: If uvicorn fails to start (port collision, import error), `proc.poll()` would return non-None. The current implementation catches via `_wait_for_ready` timeout. A more aggressive variant would check `proc.poll()` inside the wait loop and abort early. Optional polish — add only if observed.

- **Zombie processes on test failure**: pytest may abort a test mid-execution (KeyboardInterrupt, hard timeout). The `try/finally` in the fixture ensures `proc.terminate()` is called. If the test process itself dies (uncatchable), the subprocess will be reaped by the OS as an orphan when its parent dies (Linux kernel does this). Acceptable.

- **WSL2 + IPv6**: Browser uses `http://127.0.0.1:{port}` explicitly (not `localhost`) to avoid Chromium attempting `::1` first. This matches the flight design decision.

- **Subprocess output discarded**: We capture `stdout`/`stderr` to PIPE but only read on failure. On success, the pipe buffers fill up — for a short-lived subprocess (<1 minute) with `--log-level=warning`, this is harmless. If a test runs longer than ~10 minutes (it shouldn't), the pipe buffer (default 64KB on Linux) might fill and block uvicorn. Mitigation deferred — document if observed.

- **Browser session-scoped vs function-scoped**: Browser at session-scope reuses one Chromium instance across all tests (fast). Each test gets a fresh `BrowserContext` (cookies, storage, cache isolated). This matches Playwright's standard isolation model. If tests need actual cross-test persistence, they can override the `page` fixture. Not expected in this flight.

- **Settings singleton in subprocess vs test process**: The subprocess imports `the_one.config.settings` fresh and reads env vars at that point. The test process's `settings` is unaffected. This is the right isolation model.

- **`THE_ONE_DEV_MODE=true` always**: Every `app_clean` subprocess has dev_mode on, so mock providers can be created. If a future test wants to verify the app's behavior with dev_mode off, it would need a separate fixture (`app_clean_no_devmode` or parameterized). Not needed in this flight.

## State-Machine Reachability Audit

This leg introduces:
- **Test-time state**: app subprocess lifecycle (spawned → ready → terminated). No production state changes.
- No new DB schemas, no new constraints, no new caches.

Lower layers that could foreclose:
- OS port allocation: handled by `_free_port`
- pydantic-settings env var parsing: relies on leg 02's `dev_mode` field; verified there
- pytest fixture scoping: standard

No existing tests pin behavior this leg breaks. ✓ Pass.

## Cache Freshness Contract

**Cache 1 — `playwright_instance` (session-scoped)**:
- Source of truth: Playwright library state
- Rebuild trigger: per-test-session (single `sync_playwright()` context)
- Maximum staleness acceptable: until session end
- User-action invalidation map: N/A — Playwright state is internal

**Cache 2 — `browser` (session-scoped)**:
- Source of truth: Chromium process spawned by Playwright
- Rebuild trigger: per-test-session
- Maximum staleness acceptable: until session end
- User-action invalidation map: N/A

**No production caches affected.** ✓ Pass.

## Files Affected

- `tests/browser/conftest.py` — extended from docstring-only to full fixture module (~150 LOC)
- `tests/browser/test_app_fixture.py` — new file (~40 LOC, 2 tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows 350 passed, 11 deselected; `pytest -m browser tests/browser/` shows 3 passed
- [x] 5-consecutive-run stability check passes
- [x] `ruff check` and `ruff format --check` clean on `tests/browser/`
- [x] Update flight-log.md with leg progress entry (status, what was done, any anomalies — startup time observations, port collision frequency, etc.)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off this leg in flight.md (happens at flight-level commit time per agentic-workflow protocol)
- [x] Do NOT commit (flight-level review and commit happen after the last autonomous leg)
- [x] Signal `[HANDOFF:review-needed]`

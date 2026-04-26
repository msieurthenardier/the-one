"""Browser test fixtures for the-one.

This module provides:
- ``_free_port()`` / ``_wait_for_ready()`` — internal helpers.
- ``app_clean`` (function-scoped) — fresh app subprocess with empty DB.
- ``browser`` (module-scoped) — headless Chromium instance, reused per module.
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
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Browser, Page, Playwright, sync_playwright

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
            raise RuntimeError(f"App subprocess exited with code {proc.returncode} during startup")
        try:
            r = httpx.get(f"{base_url}/api/info", timeout=1.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_exc = exc
        time.sleep(0.1)
    raise TimeoutError(f"App at {base_url} not ready within {timeout}s (last error: {last_exc})")


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


@pytest.fixture(scope="module")
def playwright_instance() -> Iterator[Playwright]:
    """Module-scoped Playwright instance.

    Module (not session) scope so the sync_playwright context tears down between
    test modules — this lets the leg-01 ``test_smoke.py`` (which spawns its own
    standalone ``sync_playwright()``) run in the same pytest session without
    colliding with this module's still-alive context. Within a single module,
    Playwright is reused across tests for speed.
    """
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
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


# ── Layered fixtures (seeded variants of app_clean) ───────────────────────


@pytest.fixture
def app_with_provider(app_clean: str) -> Iterator[SeededApp]:
    """An app subprocess pre-seeded with a single mock provider."""
    provider_id = seed_mock_provider(app_clean)
    yield SeededApp(base_url=app_clean, provider_id=provider_id)


@pytest.fixture
def app_with_agent(app_with_provider: SeededApp) -> Iterator[SeededApp]:
    """An app subprocess pre-seeded with a mock provider AND an agent.

    Composes on `app_with_provider` — pytest's fixture caching ensures
    `app_clean` is spawned once per test, then seeded once, then this
    fixture layers an agent on top. Cleanup is implicit via `app_clean`'s
    SIGTERM teardown (drops the entire subprocess + DB).
    """
    agent_name = seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id)
    yield SeededApp(
        base_url=app_with_provider.base_url,
        provider_id=app_with_provider.provider_id,
        agent_name=agent_name,
    )

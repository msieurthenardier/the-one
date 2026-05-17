"""Browser test fixtures for the-one.

This module provides:
- ``_free_port()`` / ``_wait_for_ready()`` — internal helpers.
- ``app_clean`` (function-scoped) — fresh app subprocess with empty DB.
- ``app_with_provider`` / ``app_with_agent`` — seeded variants (leg 04).
- ``browser`` (module-scoped) — headless Chromium instance, reused per module.
- ``page`` (function-scoped) — fresh BrowserContext + Page per test.

The standalone smoke test at tests/browser/test_smoke.py does NOT depend
on these fixtures — it loads a data: URL to validate the toolchain in
isolation, so it stays green even if the app fixtures break.

Snapshot-update bridge: ``--snapshot-update`` is registered as a CLI
flag here and forwarded to the ``_PYTEST_SNAPSHOT_UPDATE`` env var that
``test_visual_snapshots.py`` reads.  The env-var bridge keeps the
snapshot helper simple (no pytest-config dependency at import time) and
lets ad-hoc shell ``UPDATE_SNAPSHOTS=1`` runs work identically.
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

# ── pytest CLI extension ──────────────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``--snapshot-update`` flag for the visual-snapshot suite.

    Mirrors Playwright JS's ``--update-snapshots`` semantics: when
    present, ``test_visual_snapshots.py`` regenerates baselines instead
    of comparing.  Implemented as a module-local hook here (rather than
    inside the snapshot test file) because pytest only collects
    addoption hooks from conftest.py and the rootdir's plugin chain.
    """
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Regenerate visual snapshot baselines instead of comparing.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Bridge the CLI flag to an env var for the snapshot helper to read.

    Setting an env var (rather than passing config through fixtures)
    keeps ``test_visual_snapshots.py`` decoupled from pytest internals
    and makes ad-hoc ``UPDATE_SNAPSHOTS=1`` runs behave identically to
    ``--snapshot-update``.
    """
    if config.getoption("--snapshot-update"):
        os.environ["_PYTEST_SNAPSHOT_UPDATE"] = "1"


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
    # M10 F2 L6: opt the spawned subprocess into the StubPlugin test-seam
    # so connector-account browser tests can exercise the 'stub' type via
    # /api/connector-accounts/types and POST /test/connect. Gated server-
    # side on `settings.dev_mode AND env-var == "1"`; production never
    # sets the env var.
    env["THE_ONE_REGISTER_STUB_CONNECTOR"] = "1"
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
    context = browser.new_context(color_scheme="no-preference")
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


# ── OpenRouter browser test fixtures ─────────────────────────────────────
#
# These fixtures address cross-process isolation: ``app_clean`` spawns a
# subprocess, so cache objects in the test runner's process are NOT visible
# to the app.  We solve this by:
#
# 1. ``app_with_openrouter_models``: spawns a fresh app subprocess that has
#    ``THE_ONE_OPENROUTER_TEST_MODELS_JSON`` set in its environment.  The
#    ``openrouter_api.list_models`` test seam reads this env var and returns
#    the injected models without any network call.
#
# 2. ``app_with_two_providers``: composes on the above and adds a second
#    ollama provider for lifecycle (type-switch) tests.
#
# The fixture yields a ``SeededApp`` with ``provider_id`` set to the
# openrouter provider's id.  A parallel ``ollama_provider_id`` attribute is
# stored in the extra ``SeededApp.agent_name`` slot (reused for the second
# id since SeededApp has no generic extras field).

_OPENROUTER_TEST_MODELS = [
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "supported_parameters": ["tools", "reasoning"],
        "context_length": 200000,
        "description": "",
    },
    {
        "id": "no-tools-model",
        "name": "Tools-less",
        "supported_parameters": ["max_tokens"],
        "context_length": 8192,
        "description": "",
    },
    {
        "id": "empty-caps-model",
        "name": "Empty Caps",
        "supported_parameters": [],
        "context_length": 4096,
        "description": "",
    },
]


def _spawn_app(
    tmp_path: Path, extra_env: dict[str, str] | None = None
) -> tuple[str, subprocess.Popen]:
    """Spawn a fresh app subprocess and return (base_url, proc).

    Extracted so OpenRouter fixtures can inject additional env vars before
    launch (the test seam must be visible in the subprocess, not the runner).
    """
    port = _free_port()
    data_dir = tmp_path / "the-one-data"
    data_dir.mkdir()

    env = os.environ.copy()
    env["THE_ONE_DATA_DIR"] = str(data_dir)
    env["THE_ONE_DEV_MODE"] = "true"
    # M10 F2 L6: parity with `app_clean` — register the StubPlugin in
    # spawned subprocesses so OpenRouter / two-provider fixtures (which
    # don't use the connector surface today but share the spawn helper)
    # still have a consistent server shape.
    env["THE_ONE_REGISTER_STUB_CONNECTOR"] = "1"
    if extra_env:
        env.update(extra_env)

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
    return base_url, proc


def _teardown_proc(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _seed_openrouter_provider(base_url: str, name: str = "OR Mock") -> str:
    """POST an openrouter provider via the API and return its id."""
    r = httpx.post(
        f"{base_url}/api/providers",
        json={
            "name": name,
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-test",
        },
        timeout=5.0,
    )
    assert r.status_code == 201, f"seed_openrouter_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _seed_ollama_provider(base_url: str, name: str = "Local Ollama") -> str:
    """POST a minimal ollama provider via the API and return its id."""
    r = httpx.post(
        f"{base_url}/api/providers",
        json={
            "name": name,
            "type": "ollama",
            "base_url": "http://localhost:11434/v1",
            "api_key": "",
        },
        timeout=5.0,
    )
    assert r.status_code == 201, f"seed_ollama_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


@pytest.fixture
def app_with_openrouter_models(tmp_path: Path) -> Iterator[SeededApp]:
    """Spawn a fresh app subprocess with synthetic OpenRouter models injected.

    ``THE_ONE_OPENROUTER_TEST_MODELS_JSON`` is set in the subprocess
    environment so ``openrouter_api.list_models`` returns the fake list
    without any network call.  The fixture also pre-creates an openrouter
    provider via the HTTP API so Studio can select it.

    Yields a ``SeededApp`` with ``provider_id`` = the openrouter provider id.
    """
    import json as _json

    models_json = _json.dumps(_OPENROUTER_TEST_MODELS)
    base_url, proc = _spawn_app(
        tmp_path,
        extra_env={"THE_ONE_OPENROUTER_TEST_MODELS_JSON": models_json},
    )
    try:
        provider_id = _seed_openrouter_provider(base_url)
        yield SeededApp(base_url=base_url, provider_id=provider_id)
    finally:
        _teardown_proc(proc)


@pytest.fixture
def app_with_two_providers(tmp_path: Path) -> Iterator[dict[str, str]]:
    """Spawn a fresh app subprocess with both an openrouter and an ollama
    provider pre-seeded.  Yields a dict with keys ``base_url``,
    ``openrouter_id``, and ``ollama_id``.  OpenRouter models are injected
    via the test-seam env var so no network call is needed.
    """
    import json as _json

    models_json = _json.dumps(_OPENROUTER_TEST_MODELS)
    base_url, proc = _spawn_app(
        tmp_path,
        extra_env={"THE_ONE_OPENROUTER_TEST_MODELS_JSON": models_json},
    )
    try:
        openrouter_id = _seed_openrouter_provider(base_url)
        ollama_id = _seed_ollama_provider(base_url)
        yield {
            "base_url": base_url,
            "openrouter_id": openrouter_id,
            "ollama_id": ollama_id,
        }
    finally:
        _teardown_proc(proc)

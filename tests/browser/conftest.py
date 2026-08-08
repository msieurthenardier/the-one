"""Browser test fixtures for the-one.

This module provides:
- ``_free_port()`` / ``_wait_for_ready()`` — internal helpers.
- ``_spawn_app()`` — the single consolidated app-spawn path (Mission 20 /
  Flight 1 / Leg 3, ``harness-credential-plumbing``). Every app fixture in
  this package and in ``test_markdown.py`` funnels through it; it also
  backs the ``app_with_data_dir`` fixture formerly duplicated across 8
  ``test_flow_*.py`` files. See its docstring for the credential-writing
  and readiness-probe contract.
- ``app_clean`` (function-scoped) — fresh app subprocess with empty DB.
- ``app_with_data_dir`` (function-scoped) — like ``app_clean``, but also
  yields the isolated ``data_dir`` for tests that seed directly via
  sqlite/the filesystem.
- ``app_with_provider`` / ``app_with_agent`` — seeded variants (leg 04).
- ``browser`` (module-scoped) — headless Chromium instance, reused per module.
- ``page`` (function-scoped) — fresh BrowserContext + Page per test. Its
  ``goto`` is wrapped to attach the ``Authorization`` header of whichever
  spawned app's ``base_url`` is being navigated to — see the fixture's
  docstring.

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
from urllib.parse import urlsplit

import httpx
import pytest
from browser._credential_registry import (
    credential_for as _credential_for,
)
from browser._credential_registry import (
    register as _register_credential,
)
from browser._credential_registry import (
    unregister as _unregister_credential,
)
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from the_one import api_credential
from the_one.api_credential import LocalApiCredential

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
    """Poll ``/api/live`` until 200, or raise TimeoutError.

    Mission 20 / Flight 1 / Leg 3: polls the unauthenticated liveness
    endpoint (DD5) rather than ``/api/info`` — the exemption exists
    precisely so a bootstrap probe like this one works before any
    credential is presented. Using ``/api/info`` here would also leak the
    agent's system prompt to every readiness poll (DD5's rationale) even
    before the gate is registered.

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
            r = httpx.get(f"{base_url}/api/live", timeout=1.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_exc = exc
        time.sleep(0.1)
    raise TimeoutError(f"App at {base_url} not ready within {timeout}s (last error: {last_exc})")


def _write_credential(data_dir: Path) -> LocalApiCredential:
    """Write a fresh long-lived local-API credential into *data_dir* and
    return it.

    Mission 20 / Flight 1 / Leg 3 (leg Edge Cases: "Which Leg 1 entry point
    writes the credential"). Deliberately uses the path-taking writer
    (``api_credential._write_new_credential_atomic``) rather than
    ``get_credential()``: every caller of this function spawns a SEPARATE
    SUBPROCESS with its own ``THE_ONE_DATA_DIR``, so ``get_credential()``'s
    ambient ``settings.data_dir`` read would resolve to the pytest
    PROCESS's own data dir, not the fixture's isolated one — the exact
    "natural-looking call is wrong here" trap the leg artifact calls out.
    Writing directly to the known *data_dir* removes the ambiguity (and
    the race the leg's acceptance criteria also forbid solving by polling
    for server-side creation): the fixture owns the directory and writes
    the credential into it before ``subprocess.Popen`` ever runs.
    """
    credential = LocalApiCredential.generate()
    api_credential._write_new_credential_atomic(
        data_dir / api_credential._CREDENTIAL_FILENAME, credential
    )
    return credential


def _auth_headers_for(base_url: str) -> dict[str, str]:
    """``Authorization`` header dict for whichever app is registered at
    *base_url*, or ``{}`` if none is (defensive fallback — a raw ``httpx``
    call with no header is exactly what every seeder sent before this
    leg, so an unregistered base_url degrades to prior behavior rather
    than raising).

    Used by the module-level ``_seed_openrouter_provider`` /
    ``_seed_ollama_provider`` helpers below (Mission 20 / Flight 1 / Leg 3
    — DD10: the credential is resolved from the ``base_url`` these
    functions already receive, not threaded through as a new parameter).
    """
    credential = _credential_for(base_url)
    if credential is None:
        return {}
    return {"Authorization": f"Bearer {credential.encode()}"}


# ── App subprocess ────────────────────────────────────────────────────────


def _spawn_app(
    tmp_path: Path, extra_env: dict[str, str] | None = None
) -> tuple[str, subprocess.Popen, LocalApiCredential, Path]:
    """Spawn a fresh app subprocess and return ``(base_url, proc, credential,
    data_dir)``.

    Mission 20 / Flight 1 / Leg 3 (``harness-credential-plumbing`) —
    THE consolidated app-spawn path. Before this leg there were 10
    independent implementations of this same spawn-plus-readiness-poll
    logic (``app_clean``, ``test_markdown.py``'s module-scoped
    ``app_clean_module``, and an ``app_with_data_dir`` fixture duplicated
    verbatim across 8 ``test_flow_*.py`` files); consolidating onto this
    one function means the credential-writing work — and any future change
    to how the app is spawned — happens once instead of ten times.

    The credential is written into the isolated *data_dir* BEFORE
    ``subprocess.Popen`` (leg acceptance criterion): the caller-supplied
    *tmp_path* is entirely ours before the server process exists, so there
    is no server-side-creation race to poll for — the deferred open
    question the flight spec left for this leg is avoided rather than
    resolved, exactly as the leg artifact directs.
    """
    port = _free_port()
    data_dir = tmp_path / "the-one-data"
    data_dir.mkdir()

    credential = _write_credential(data_dir)

    env = os.environ.copy()
    env["THE_ONE_DATA_DIR"] = str(data_dir)
    env["THE_ONE_DEV_MODE"] = "true"
    # M10 F2 L6: opt the spawned subprocess into the StubPlugin test-seam
    # so connector browser tests can exercise the 'stub' type via
    # /api/connectors/types and POST /test/connect. Gated server-
    # side on `settings.dev_mode AND env-var == "1"`; production never
    # sets the env var.
    env["THE_ONE_REGISTER_STUB_CONNECTOR"] = "1"
    # Note: THE_ONE_PORT/THE_ONE_HOST omitted — uvicorn binds via the explicit
    # --host/--port flags below; nothing in app.py reads settings.port post-init.
    if extra_env:
        env.update(extra_env)

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

    _register_credential(base_url, credential)
    return base_url, proc, credential, data_dir


def _teardown_proc(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture
def app_clean(tmp_path: Path) -> Iterator[str]:
    """Spawn a fresh app subprocess on a random port with an isolated data_dir.

    Yields the base URL (e.g., ``http://127.0.0.1:54321``).

    Each test gets its own subprocess, port, and data_dir — no state bleed.
    Subprocess is launched with ``THE_ONE_DEV_MODE=true`` so seeded mock
    providers are accepted (see leg 04).
    """
    base_url, proc, _credential, _data_dir = _spawn_app(tmp_path)
    try:
        yield base_url
    finally:
        _unregister_credential(base_url)
        _teardown_proc(proc)


@pytest.fixture
def app_with_data_dir(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Spawn a fresh app subprocess and yield ``(base_url, data_dir)``.

    Mission 20 / Flight 1 / Leg 3: consolidated from 8 independent
    per-file duplicates across ``test_flow_*.py`` (each with its own copy
    of the spawn-plus-readiness-poll logic) onto the shared ``_spawn_app``.
    Tests that need direct sqlite/encryption-key access alongside the
    running app (seeding a ``chat_sessions`` row, seeding Fernet-encrypted
    OAuth secrets) request this fixture instead of ``app_clean``, which
    hides ``data_dir``.
    """
    base_url, proc, _credential, data_dir = _spawn_app(tmp_path)
    try:
        yield base_url, data_dir
    finally:
        _unregister_credential(base_url)
        _teardown_proc(proc)


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


def _establish_session_cookie(context: BrowserContext, origin: str, credential) -> None:
    """One-time handoff exchange (mint + exchange) for *origin*, landing a
    session cookie in *context*'s cookie jar.

    Mission 20 / Flight 1 / Leg 4 review fix: extracted to module level (out
    of the ``page`` fixture's closure) so both the lazy per-``goto`` flow
    below AND ``credentialed_context()`` (for tests that build their own
    ``browser.new_context(...)`` — e.g. for extra ``permissions=[...]``)
    share one implementation of the mint-then-follow-redirect exchange.
    Two local copies of this exchange (one that had it, one that didn't) is
    exactly how ``test_flow_studio_connector_invite_section.py``'s
    ``clipboard_page`` fixture went stale after the gate was registered —
    see this module's and ``credentialed_context()``'s docstrings.
    """
    mint_resp = context.request.post(
        f"{origin}/api/session/handoff",
        headers={"Authorization": f"Bearer {credential.encode()}"},
    )
    assert mint_resp.ok, f"handoff mint failed for {origin}: {mint_resp.status} {mint_resp.text()}"
    handoff_url = mint_resp.json()["url"]
    # Following this (redirecting) GET sets the session cookie in the
    # context's shared cookie jar — no separate Set-Cookie handling
    # needed here.
    context.request.get(handoff_url)


def credentialed_context(browser: Browser, base_url: str, **context_kwargs) -> BrowserContext:
    """Create a ``BrowserContext`` wired with the SAME two-channel
    credential treatment the ``page`` fixture below gives every
    ``app_clean``-style test: the ``Authorization`` header AND the
    handoff session-cookie exchange (see ``_establish_session_cookie``).

    For tests that need their own locally-defined context — e.g. non-default
    ``permissions=[...]`` for clipboard access — instead of the shared
    ``page`` fixture. *base_url* must already be registered (via
    ``_spawn_app``, e.g. through ``app_clean``); the credential is looked up
    from ``browser._credential_registry``, and since the target app is known
    up front here (unlike the generic multi-app ``page`` fixture), both the
    header and the cookie exchange happen immediately at context-creation
    time rather than lazily at ``goto``.

    Mission 20 / Flight 1 / Leg 4 review fix: before this helper existed,
    ``test_markdown.py``'s ``page_with_app`` set only the header (silently
    incompatible with the chat area's bare ``new WebSocket(...)``, which
    the WHATWG spec forbids attaching custom headers to — see the ``page``
    fixture's docstring) and ``test_flow_studio_connector_invite_section.py``'s
    ``clipboard_page`` set neither, which is what actually failed once the
    gate went live. Centralizing here is the fix meant to stop a third local
    copy reintroducing the same gap — see ``**context_kwargs`` below for how
    each caller layers its own extra needs on top.

    *context_kwargs* pass straight through to ``browser.new_context(...)``
    (e.g. ``permissions=["clipboard-read", "clipboard-write"]``);
    ``color_scheme`` defaults to ``"no-preference"`` unless the caller
    overrides it.
    """
    credential = _credential_for(base_url)
    assert credential is not None, (
        f"no credential registered for {base_url!r} — spawn it via _spawn_app "
        "(e.g. app_clean) before requesting a credentialed_context for it"
    )
    context_kwargs.setdefault("color_scheme", "no-preference")
    context = browser.new_context(**context_kwargs)
    context.set_extra_http_headers({"Authorization": f"Bearer {credential.encode()}"})
    _establish_session_cookie(context, base_url, credential)
    return context


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    """Fresh BrowserContext + Page per test for cookie/storage isolation.

    Mission 20 / Flight 1 / Leg 3: ``goto`` is wrapped so that, immediately
    before navigating, the context's ``Authorization`` header is set to the
    credential registered (in ``browser._credential_registry``) for
    whichever app's ``base_url`` is being navigated to.

    This is deliberately resolved at ``goto()`` time rather than at
    context-creation time: ``page`` does not know in advance which of
    ``app_clean`` / ``app_with_provider`` / ``app_with_agent`` /
    ``app_with_data_dir`` / ``app_with_openrouter_models`` /
    ``app_with_two_providers`` a given test will pair it with, so there is
    no single fixed credential to attach up front. Resolving lazily by the
    URL actually being navigated to means every existing
    ``page.goto(app_clean)``-style call site keeps working with NO edit —
    the credential always matches the app instance the test is actually
    driving, per the leg's acceptance criterion (getting this wrong is
    silent: attaching the wrong app's credential to a request never fails
    loudly, since the gate isn't registered yet — see
    ``test_app_spawn_credential_wiring.py`` for the assertion that this
    matching is correct).

    Mission 20 / Flight 1 / Leg 4 (``enforce-gate``) — Pre-Flip Harness Fix:
    ``goto`` ALSO performs a one-time browser-handoff exchange (mint via
    ``POST /api/session/handoff`` using the header credential, then follow
    the returned handoff URL) the first time each app origin is navigated
    to in this context, establishing a real session cookie exactly as
    production does (the launcher navigates to a handoff URL; the gate
    sets the cookie on the redirect). This is load-bearing, not
    decorative: a native browser ``WebSocket`` cannot set an
    ``Authorization`` header (WHATWG restriction), and Playwright's
    ``set_extra_http_headers`` does not apply to the WS upgrade in
    Chromium either — so once the gate is registered, the chat area's
    bare ``new WebSocket(...)`` (``static/js/areas/chat.js``) can only be
    authorized via the session cookie. The header is kept in addition —
    it costs nothing and covers non-document fetches. The exchange is
    performed via ``context.request`` (not a bare ``httpx`` call): Playwright's
    API-request context shares cookie storage with this ``BrowserContext``,
    so the ``Set-Cookie`` on the redirect hop lands in the same jar
    ``page.goto`` (and the later WS handshake) will use.
    """
    context = browser.new_context(color_scheme="no-preference")
    page = context.new_page()

    _orig_goto = page.goto
    _handoff_established_origins: set[str] = set()

    def _goto_with_credential(url: str, *args, **kwargs):
        credential = _credential_for(url)
        if credential is not None:
            context.set_extra_http_headers({"Authorization": f"Bearer {credential.encode()}"})
            parts = urlsplit(url)
            origin = f"{parts.scheme}://{parts.netloc}"
            if origin not in _handoff_established_origins:
                # Module-level helper (see its docstring) — the lazy,
                # per-origin variant of the same exchange
                # ``credentialed_context()`` performs eagerly for callers
                # that know their target app up front.
                _establish_session_cookie(context, origin, credential)
                _handoff_established_origins.add(origin)
        return _orig_goto(url, *args, **kwargs)

    page.goto = _goto_with_credential

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
        headers=_auth_headers_for(base_url),
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
        headers=_auth_headers_for(base_url),
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
    base_url, proc, _credential, _data_dir = _spawn_app(
        tmp_path,
        extra_env={"THE_ONE_OPENROUTER_TEST_MODELS_JSON": models_json},
    )
    try:
        provider_id = _seed_openrouter_provider(base_url)
        yield SeededApp(base_url=base_url, provider_id=provider_id)
    finally:
        _unregister_credential(base_url)
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
    base_url, proc, _credential, _data_dir = _spawn_app(
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
        _unregister_credential(base_url)
        _teardown_proc(proc)

"""Shared test fixtures: FakeLLM, StubTool, registry helpers, markers."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ── Environment isolation — MUST run before any `the_one` import below. ──
# `the_one.config.settings` is a PEP 562 LAZY singleton, instantiated on first
# attribute access — and the import chain of the `the_one` modules imported
# below reaches that access DURING conftest import, i.e. before
# pytest_configure() runs. Setting these env vars at module level (not in
# pytest_configure) is therefore load-bearing: when it lived in
# pytest_configure, the singleton cached the real OS-conventional data dir
# (platformdirs XDG path), and any test reaching `get_encryptor(settings.data_dir)`
# outside a patched seam wrote into — or crashed on — the operator's real data
# dir (green on dev boxes where it existed; FileNotFoundError on clean CI
# runners; see Flight M15-F1 closeout).
#
# THE_ONE_TEST_MODE: F3 §10 — the ONLY place the flag is set in non-production
# code (the companion THE_ONE_SANDBOX_DISABLED is set only by the browser-test
# CI invocation). `setdefault` preserves explicit CI-set values.
#
# THE_ONE_DATA_DIR: M08 F5 L01 — isolate the broad pytest run from any live
# server's SQLite DB (WAL contention against a live writer caused F1-F4's
# chronic broad-pytest hang). `setdefault` preserves any explicit override set
# by CI or by the per-subprocess browser-test isolation in
# `tests/browser/conftest.py`. A session-persistent tmp dir (one path for the
# whole pytest run) matches the live-server pattern.
os.environ.setdefault("THE_ONE_TEST_MODE", "1")
os.environ.setdefault("THE_ONE_DATA_DIR", tempfile.mkdtemp(prefix="the-one-pytest-"))

from the_one.llm.base import LLMProvider, Message  # noqa: E402
from the_one.platform.sandbox import SandboxProfile  # noqa: E402
from the_one.tools.base import Tool, ToolRegistry  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # tests/conftest.py → project root


def pytest_configure(config: pytest.Config) -> None:
    """Apply session-wide runtime patches.

    Environment isolation (``THE_ONE_TEST_MODE``, ``THE_ONE_DATA_DIR``)
    lives at module level above — NOT here — because the lazy settings
    singleton is instantiated during this conftest's own imports, before
    this hook runs. Do not move it back.

    The sibling ``tests/browser/conftest.py`` also defines a
    ``pytest_configure`` (snapshot-update bridge); pytest collects both
    top-level and browser-subdir conftest hooks and runs them in turn,
    so there is no conflict between the two.
    """
    del config  # unused; signature mandated by pytest hookspec
    _daemonize_aiosqlite_worker_threads()


def _daemonize_aiosqlite_worker_threads() -> None:
    """Make aiosqlite's per-connection worker thread a daemon (TEST-ONLY).

    Root cause of the long-standing "broad pytest wedges for hours AFTER the
    summary line" KI (and the recurring, mis-labelled-as-benign "aiosqlite
    teardown ResourceWarning"):

    aiosqlite 0.22's ``Connection`` spawns a **non-daemon** ``Thread``
    (``core.py``: ``Thread(target=_connection_worker_thread, ...)`` — no
    ``daemon=True``). That thread is stopped only by ``Connection.close()``,
    which signals it via ``call_soon_threadsafe`` **on the event loop the
    connection was created on**. Under pytest-asyncio's per-test event loops, a
    connection opened in test A's loop and not closed before that loop is torn
    down leaves an orphaned worker thread bound to a now-closed loop; a later
    ``close()`` then raises ``RuntimeError: Event loop is closed`` and the thread
    never exits. Because it is non-daemon, ``threading._shutdown`` **joins** it
    at interpreter exit → the pytest process hangs forever after printing its
    summary (all tests already passed). The ``_close_db_singleton_at_session_end``
    fixture below cannot fix this: it only handles the singleton, and its
    ``close()`` hits the same closed-loop ``RuntimeError``.

    Daemonizing the worker thread lets the interpreter exit cleanly regardless of
    cross-loop leaks. This is test-only and safe: production closes the singleton
    on its single long-lived lifespan loop (no leak there), and the only
    connections still alive at interpreter exit here are abandoned throwaway test
    DBs in tmp dirs. Patching ``__init__`` sets ``daemon`` after the thread is
    created but before it is ``start()``ed (aiosqlite starts it lazily in
    ``connect()``), which is the only window ``Thread.daemon`` may be assigned.
    """
    import aiosqlite.core as _aiosqlite_core

    conn_cls = _aiosqlite_core.Connection
    if getattr(conn_cls, "_the_one_daemonized", False):
        return  # idempotent — pytest_configure can run more than once
    _orig_init = conn_cls.__init__

    def _init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _orig_init(self, *args, **kwargs)
        thread = getattr(self, "_thread", None)
        if thread is not None and not thread.is_alive():
            thread.daemon = True

    conn_cls.__init__ = _init
    conn_cls._the_one_daemonized = True


@pytest.fixture(autouse=True)
def _shared_app_isolation():
    """Mission 34 F1 L01 (AC3): after every test, fail if it changed the shared API app.

    A no-op until a test has built ``tests/_api_app.py::shared_app()``.
    """
    yield
    from tests._api_app import check_isolation

    check_isolation()


@pytest.fixture(autouse=True, scope="session")
def _close_db_singleton_at_session_end():
    """F5 L01.5: close the `aiosqlite` singleton at session end so its
    `_connection_worker_thread` (which `aiosqlite.core` spawns as
    `daemon=False`) joins cleanly and the python interpreter can exit.

    Without this, `_entry_worker` in `the_one/mcp/_pool.py:210` opens the
    singleton during pool tests (even with MCPClient mocked, the
    auth-provider construction reads from the DB) and the resulting
    non-daemon background thread holds the process open for ~50s after
    the pytest summary line — bisection-confirmed source of the F1-F4
    "broad pytest hangs after summary" KI. Browser-test subprocesses are
    unaffected because they SIGTERM their own uvicorn child which closes
    its connection during lifespan shutdown.
    """
    yield
    import asyncio

    from the_one.db import connection as _conn_mod

    if _conn_mod._connection is None:
        return
    try:
        asyncio.run(_conn_mod.close_connection())
    except Exception:
        # Best-effort: an exception here only affects exit-code reliability,
        # not test results. The summary line is the source of truth.
        pass


# ---------------------------------------------------------------------------
# FakeLLM
# ---------------------------------------------------------------------------


class FakeLLM(LLMProvider):
    """LLM provider that returns pre-scripted responses in order."""

    name = "fake"

    def __init__(self, responses: list[Message]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,  # M16 F10 L02: contract param, ignored.
    ) -> Message:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# StubTool
# ---------------------------------------------------------------------------


class StubTool(Tool):
    """Tool that records calls and returns a canned response."""

    def __init__(
        self,
        name: str,
        description: str = "A stub tool.",
        cross_configs: dict[Any, Any] | None = None,
        agent_name: str | None = None,
    ) -> None:
        # L1b: widen to accept cross_configs/agent_name kwargs so this stub
        # works on the BuiltinToolProvider factory path. We do not call
        # `super().__init__()` because StubTool has no Config schema and the
        # tests intentionally use a plain `name`-positional constructor; we
        # mirror the base class's storage of the new fields so factory-path
        # plumbing assertions (e.g. `_agent_name`) succeed.
        self.name = name
        self.description = description
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.calls: list[dict[str, Any]] = []
        self._cross_configs = cross_configs or {}
        self._agent_name = agent_name

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"stub: {self.name}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_registry() -> ToolRegistry:
    """Create a ToolRegistry pre-loaded with stub tools."""
    registry = ToolRegistry()
    for tool_name in ("tool_a", "tool_b", "tool_c"):
        registry.register(StubTool(tool_name))
    return registry


# ---------------------------------------------------------------------------
# MCP fixtures (F2 L3) — shared by L4 (streamable-http) and L5 (stdio)
# integration tests, plus the L3 smoke tests in tests/test_mcp_integration.py.
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_fixture_stdio_params() -> dict[str, Any]:
    """StdioServerParameters-shaped dict pointing at the in-repo hello fixture.

    Returns a dict (not the typed object) so callers don't need to import the
    SDK type at test-collection time. Construct via:

        from mcp.client.stdio import StdioServerParameters
        params = StdioServerParameters(**fixture)

    Each test gets a fresh params dict; the SDK's stdio_client manages the
    subprocess lifetime.
    """
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(_PROJECT_ROOT),
    }
    return {
        "command": sys.executable,
        "args": ["-m", "tests.fixtures.mcp.hello_server", "--stdio"],
        "env": env,
        "cwd": None,
    }


@pytest.fixture
def mcp_fixture_sandbox_profile() -> SandboxProfile:
    """Strict-floor ``SandboxProfile`` for L4+ sandbox-aware integration tests.

    Returns the dataclass defaults: empty ``writable_paths``,
    ``network_allowed=False``, all three namespace-unshare flags True.
    Tests needing writable paths or network construct a
    ``SandboxProfile(...)`` inline (the dataclass is frozen, so use
    ``dataclasses.replace`` or build a fresh instance per test).

    NOTE: no L4 test consumes this fixture — it is added in L4 per the
    F3 flight spec as a forward-looking co-fixture for L5a's integration
    tests, where it will be used to compose strict-floor + per-test
    profile overrides. Documented up-front so reviewers don't flag it as
    dead code.
    """
    return SandboxProfile()


@pytest.fixture
async def mcp_fixture_http_client():
    """In-process httpx2.AsyncClient wrapping a FRESH MCPServer ASGI app per test.

    Three non-obvious requirements (verified at leg-design review):
      1. Calls ``make_mcp_app()`` per-test — module-level ``mcp_app`` cannot be
         reused because ``StreamableHTTPSessionManager.run()`` enforces
         once-per-instance.
      2. Drives Starlette lifespan via ``asgi_lifespan.LifespanManager`` —
         ``httpx2.ASGITransport`` does NOT auto-fire lifespan events, so the
         MCPServer session manager's task group would otherwise be unstarted.
      3. Uses ``base_url="http://localhost"`` and ``url="http://localhost/mcp"``
         — MCPServer auto-enables DNS-rebinding protection for ``host="127.0.0.1"``
         constructor default; the localhost form matches the allowlist (and
         ``make_mcp_app()`` also disables protection at the MCPServer level for
         defense-in-depth).
    """
    import httpx2
    from asgi_lifespan import LifespanManager

    from tests.fixtures.mcp.hello_server import make_http_app

    app = make_http_app()
    async with LifespanManager(app):
        transport = httpx2.ASGITransport(app=app)
        client = httpx2.AsyncClient(transport=transport, base_url="http://localhost")
        try:
            yield client, "http://localhost/mcp"
        finally:
            await client.aclose()


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """Per-test sqlite DB at tmp_path with the module-level connection
    singleton repointed at it.

    Callers resolve their DB connection via ``get_connection()`` inside
    the function body, so we need the module-level singleton repointed
    at the per-test path. Schema is applied via a side connection so the
    singleton opens cleanly on first ``get_connection()``.

    Originally introduced for the connector-dispatch e2e tests (M10 F4
    L5); those are gone (Mission 23 Flight 1), but the fixture itself is
    still consumed by other tests that need an isolated DB behind the
    connection singleton.
    """
    from tests._schema_template import connect_template_db
    from the_one.config import settings as _settings
    from the_one.db import connection as _db_connection

    monkeypatch.setattr(_settings, "data_dir", tmp_path)
    db_path = _settings.db_path

    conn = await connect_template_db(db_path)
    await conn.close()

    monkeypatch.setattr(_db_connection, "_connection", None)
    yield db_path

    if _db_connection._connection is not None:
        await _db_connection.close_connection()


@pytest.fixture
def reset_lifespan_singletons():
    """Restore process-global singleton state after a test that runs the
    REAL app lifespan to completion (e.g. ``with TestClient(app):``).

    The lifespan's shutdown branch calls each subsystem's
    ``shutdown_drain()``, which latches module-global
    ``_shutting_down = True`` in two modules
    (``the_one.tools._session_registry``, ``the_one.mcp._pool`` — a third,
    the connector pool module, was deleted with the connector package at
    Mission 23 Flight 1). Left set, the latch makes any LATER test in
    the same process that calls ``register()`` / ``acquire()`` fail with
    ``RuntimeError: ... shutting down`` — a pure test-ordering flake
    (M17 F1 L4 root cause: ``test_lifespan.py``'s first test failed
    whenever ``test_index_asset_cache_busting.py`` ran before it).

    Activate module-wide in any module that drives the real ``lifespan``
    to shutdown::

        pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")

    The clears run via ``asyncio.run`` in a fresh loop: after a completed
    ``shutdown_drain`` both registries are empty with no live tasks, so
    each ``_clear_for_test`` is a cheap flag/state reset — nothing
    cross-loop is awaited.
    """
    yield

    import asyncio as _asyncio

    from the_one.mcp._pool import _clear_for_test as _clear_mcp_pool
    from the_one.tools._session_registry import _clear_for_test as _clear_session_registry

    async def _reset() -> None:
        await _clear_session_registry()
        await _clear_mcp_pool()

    _asyncio.run(_reset())

    from the_one.db import _session_changes

    _session_changes.clear_for_test()


# Modules that own the ONLY sanctioned real embedding-model load
# (``tests.test_doctor_embedding_model`` — see that file's docstring) or
# that need to control ``LocalStaticBackend.load`` themselves to test the
# process singleton (``tests.test_embeddings`` does NOT perform a real
# load — it stubs ``model2vec.StaticModel`` itself, one layer below
# ``load``, so it needs this fixture to leave ``LocalStaticBackend.load``
# alone rather than replacing it wholesale with a ``StubEmbeddingBackend``)
# (M24 F02 L03). Every other test gets a fast stub instead — without this,
# ``create_knowledge_base`` (which now kicks ``embeddings.warm_up()`` on
# every call) would race a real ~250 MiB model load into the background of
# any test that creates a knowledge base.
_EMBEDDING_REAL_LOAD_MODULES = frozenset(
    {
        "tests.test_doctor_embedding_model",
        "tests.test_embeddings",
        "tests.test_evals_fingerprint",
        "tests.test_evals_kb",
        "tests.test_evals_scenarios",
        "tests.test_evals_tokens",
    }
)


@pytest.fixture(autouse=True)
def _stub_embedding_backend_by_default(request: pytest.FixtureRequest, monkeypatch):
    """Keep the real bundled model load confined to the two modules above.

    Patches ``LocalStaticBackend.load`` (the one seam both
    ``get_embedding_backend()`` and the ``doctor`` probe call through) to
    return a ``StubEmbeddingBackend`` instead, and resets the process
    singleton before and after each test so no test observes another
    test's stubbed instance. ``tests/test_doctor.py`` additionally stubs
    ``_probe_embedding_model`` itself (its own autouse fixture), so this
    fixture never even needs to fire for that module's probe calls to stay
    fast — it is here for the seam's OTHER callers (``warm_up()``,
    ``create_knowledge_base``, any future consumer).
    """
    module_name = request.module.__name__ if request.module is not None else ""
    if module_name in _EMBEDDING_REAL_LOAD_MODULES:
        yield
        return

    from tests._embedding_stub import StubEmbeddingBackend
    from the_one import embeddings
    from the_one.embeddings.local import LocalStaticBackend

    monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(lambda: StubEmbeddingBackend()))
    embeddings._reset_for_test()
    yield
    embeddings._reset_for_test()


@pytest.fixture(autouse=True)
def _reset_mcp_era_memory():
    """The MCP era map is process-global (M29 F2 DD2); about 110 tests share
    fixed source ids, so empty it around every test."""
    from the_one.mcp import _era

    _era._clear_for_test()
    yield
    _era._clear_for_test()


@pytest.fixture(autouse=True)
def _reset_window_chrome_state():
    """The window-chrome state is process-global (M25 F5 L2): reset it around
    every test so a registered fake window or a requested theme never leaks.
    ``chrome.py`` has no GUI imports, so this is cheap and import-safe."""
    from the_one.interfaces.desktop import chrome

    chrome.reset()
    yield
    chrome.reset()


@pytest.fixture(autouse=True)
def _reset_desktop_session_state():
    """The desktop session's lifecycle flags are process-global (M32 F3 DD1: they
    live on ``session_state.state``, no longer on the ``shell`` module, so a
    ``importlib.reload(shell)`` does not reset them): reset them in place around
    every test."""
    from the_one.interfaces.desktop.session_state import state

    state.reset()
    yield
    state.reset()


@pytest.fixture
def frozen_clock(request, monkeypatch):
    """Freeze the time-zone module's clock and system zone (M28 F1 L1).

    Patches ``the_one.time_zones.utcnow`` and ``detect_system_zone`` (the module
    seams; code calls them through the module namespace) and yields the instant.
    Parametrise with ``request.param``: a datetime, an ISO-8601 string, or a
    ``(instant, system_zone)`` pair. Defaults: 2026-10-10T22:45:12Z and
    ``America/Los_Angeles``.
    """
    from datetime import datetime, timezone

    from the_one import time_zones

    instant: Any = datetime(2026, 10, 10, 22, 45, 12, tzinfo=timezone.utc)
    system_zone: str | None = "America/Los_Angeles"
    param = getattr(request, "param", None)
    if isinstance(param, tuple):
        instant, system_zone = param
    elif param is not None:
        instant = param
    if isinstance(instant, str):
        instant = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    monkeypatch.setattr(time_zones, "utcnow", lambda: instant)
    monkeypatch.setattr(time_zones, "detect_system_zone", lambda: system_zone)
    return instant


def expected_date_layer(tool_available: bool) -> str:
    """The date layer for the ``frozen_clock`` defaults (2026-10-10T22:45:12Z,
    America/Los_Angeles), built through the real formatter."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from the_one import time_zones

    return time_zones.date_line(
        datetime(2026, 10, 10, 22, 45, 12, tzinfo=timezone.utc),
        time_zones.EffectiveZone("America/Los_Angeles", ZoneInfo("America/Los_Angeles")),
        tool_available=tool_available,
    )


class _EveryAgent:
    """Stands in for the set of connector-bound agent names: every agent is bound."""

    def __contains__(self, _name: object) -> bool:
        return True


@pytest.fixture
def all_agents_connector_bound(monkeypatch):
    """For tests that build ``AgentFactory`` over a bare ``AsyncMock`` connection.

    That connection cannot run the real bindings query (``async with conn.execute(...)``
    raises TypeError, which the factory rightly does not swallow), so treat every agent
    as connector-bound, i.e. the connector tool pair is seeded."""

    async def _all(_conn):
        return _EveryAgent()

    monkeypatch.setattr("the_one.db.repositories.agent_names_in_use", _all)


@pytest.fixture
def stub_desktop_host(monkeypatch):
    """Stub the Linux desktop-host probes (M32 F2 L02, AC0).

    Tests that run ``_boot``/``DesktopSession.run`` or ``run_doctor`` must never
    open a real D-Bus connection or X display, or spawn notify-send/gdbus.
    Apply with ``pytestmark = pytest.mark.usefixtures("stub_desktop_host")``;
    a test that wants its own behaviour monkeypatches the same attribute after.
    """
    from the_one.interfaces.desktop import host
    from the_one.interfaces.desktop.session_state import state

    monkeypatch.setattr(host, "detect_tray", lambda backend: ("indicator", "stubbed"))
    monkeypatch.setattr(host, "choose_pystray_backend", lambda: None)
    monkeypatch.setattr(host, "host_has_desktop_gtk", lambda: True)
    monkeypatch.setattr(host, "send_notification", lambda summary, body: None)
    monkeypatch.setattr(state, "tray_mode", None)


# ── Operator-port guard (M32 F2 L05) ─────────────────────────────────────────
# Ports 8484 (the operator's running app) and 8485 (the Flight Director's
# preview instance) must never be reached by a unit test: the desktop shell's
# focus / quit / takeover paths POST to a running instance, and a test that
# forgets to stub them would act on the real one. Every httpx request passes
# through ``Client.send`` / ``AsyncClient.send``, so refusing there covers
# ``httpx.get/post``, ``Client`` and ``AsyncClient`` alike. In-process
# ``TestClient`` requests go to ``testserver`` and are unaffected.
_OPERATOR_PORTS = frozenset({8484, 8485})


def _refuse_operator_port(request) -> None:
    if request.url.port in _OPERATOR_PORTS:
        raise AssertionError(
            f"a unit test reached the operator's port: {request.method} {request.url.port}. "
            "Stub the call (the shell's _running_version/_request_quit seams, httpx.post...) "
            "or use a free port."
        )


@pytest.fixture(autouse=True)
def _never_reach_operator_ports(monkeypatch):
    import httpx

    real_send = httpx.Client.send
    real_async_send = httpx.AsyncClient.send

    def guarded_send(self, request, *args, **kwargs):
        _refuse_operator_port(request)
        return real_send(self, request, *args, **kwargs)

    async def guarded_async_send(self, request, *args, **kwargs):
        _refuse_operator_port(request)
        return await real_async_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", guarded_send)
    monkeypatch.setattr(httpx.AsyncClient, "send", guarded_async_send)
    yield

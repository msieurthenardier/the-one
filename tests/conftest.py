"""Shared test fixtures: FakeLLM, StubTool, registry helpers, markers."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from the_one.llm.base import LLMProvider, Message
from the_one.platform.sandbox import SandboxProfile
from the_one.tools.base import Tool, ToolRegistry

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # tests/conftest.py → project root


def pytest_configure(config: pytest.Config) -> None:
    """Set ``THE_ONE_TEST_MODE=1`` for all pytest runs (F3 §10).

    Per F3 §10, this is the ONLY place the flag is set in non-production
    code (the companion ``THE_ONE_SANDBOX_DISABLED`` is set only by the
    Playwright browser-test CI workflow's ``pytest -m browser``
    invocation). With only ``THE_ONE_TEST_MODE=1``, the sandbox wrap
    stays active for unit + integration tests in environments where
    ``bwrap`` is present (dev container post-L1a). The double-flag
    bypass in ``the_one.mcp.transports.stdio._sandbox_disabled_for_tests``
    only fires when BOTH flags are set.

    Uses ``setdefault`` so existing values are preserved — the CI
    workflow may set both flags before pytest runs, and we must not
    clobber that.

    The sibling ``tests/browser/conftest.py`` also defines a
    ``pytest_configure`` (snapshot-update bridge); pytest collects both
    top-level and browser-subdir conftest hooks and runs them in turn,
    so there is no conflict between the two.
    """
    del config  # unused; signature mandated by pytest hookspec
    os.environ.setdefault("THE_ONE_TEST_MODE", "1")
    # M08 F5 L01: isolate the broad pytest run from the live container's SQLite
    # DB. Without this, `the_one.config.Settings()` (instantiated at module
    # import time in `the_one/config.py:33`) defaults `data_dir` to
    # `Path.home() / ".the-one"` which inside the `the-one` container resolves
    # to `/root/.the-one` — the SAME directory uvicorn holds open in WAL mode.
    # SQLite WAL contention against the live writer caused F1-F4's chronic
    # broad-pytest hang (futex_wait_queue). `setdefault` preserves any explicit
    # override set by CI or by the per-subprocess browser-test isolation in
    # `tests/browser/conftest.py:127`. A session-persistent tmp dir (one path
    # for the whole pytest run) matches the live-container pattern.
    _test_data_dir = os.environ.setdefault(
        "THE_ONE_DATA_DIR",
        tempfile.mkdtemp(prefix="the-one-pytest-"),
    )
    # F5 L01.5: the env-var override above is insufficient on its own because
    # `the_one.config` is imported transitively BEFORE this hook fires —
    # `tests/conftest.py:14 from the_one.platform.sandbox import SandboxProfile`
    # pulls in `the_one.mcp.errors` → `the_one.mcp.__init__` → `the_one.mcp._pool`
    # → `from the_one.config import settings`. By the time pytest_configure
    # runs, the `Settings()` singleton at `the_one/config.py:33` is already
    # constructed with `data_dir = Path.home() / ".the-one"` (= /root/.the-one
    # inside the container). Test code that calls `get_connection()` then
    # opens the LIVE DB — bisection-confirmed via tests/test_mcp_pool.py's
    # _entry_worker at _pool.py:210 even with all MCP classes mocked. Mutate
    # the cached singleton directly to ensure the override takes effect.
    from pathlib import Path
    from the_one.config import settings
    settings.data_dir = Path(_test_data_dir)


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
    """In-process httpx.AsyncClient wrapping a FRESH FastMCP ASGI app per test.

    Three non-obvious requirements (verified at leg-design review):
      1. Calls ``make_mcp_app()`` per-test — module-level ``mcp_app`` cannot be
         reused because ``StreamableHTTPSessionManager.run()`` enforces
         once-per-instance.
      2. Drives Starlette lifespan via ``asgi_lifespan.LifespanManager`` —
         ``httpx.ASGITransport`` does NOT auto-fire lifespan events, so the
         FastMCP session manager's task group would otherwise be unstarted.
      3. Uses ``base_url="http://localhost"`` and ``url="http://localhost/mcp"``
         — FastMCP auto-enables DNS-rebinding protection for ``host="127.0.0.1"``
         constructor default; the localhost form matches the allowlist (and
         ``make_mcp_app()`` also disables protection at the FastMCP level for
         defense-in-depth).
    """
    import httpx
    from asgi_lifespan import LifespanManager

    from tests.fixtures.mcp.hello_server import make_mcp_app

    app = make_mcp_app().streamable_http_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://localhost")
        try:
            yield client, "http://localhost/mcp"
        finally:
            await client.aclose()

"""Tests for F9 L2 D1 — stdio Test connection support.

Covers:
  - POST /api/mcp-sources/{id}/test/connect dispatches stdio sources to
    the dedicated transient-client lifecycle (no OAuth phases).
  - Successful stdio Test persists tools + capabilities + last_updated
    to config._cache (mirrors the http no-auth helper's persistence
    shape, minus auth_posture).
  - Stdio Test against the in-repo FastMCP fixture returns the expected
    [echo, add] tools end-to-end.
  - Caplog gate: 0 ``MCPClient.disconnect`` warnings across the stdio
    Test path (F6 baseline preservation; first stdio re-assertion since
    F6 per leg artifact §15).
  - Error-path: stdio Test surfaces SandboxError/MCPConnectionError as
    structured ``{status: "error", error: ...}`` responses without
    leaking exceptions.

The integration test exercises the SANDBOX-DISABLED bypass path
(``THE_ONE_SANDBOX_DISABLED=1`` AND ``THE_ONE_TEST_MODE=1``) per the
docstring at ``the_one/mcp/transports/stdio.py:241-249`` — pytest's
conftest auto-sets ``THE_ONE_TEST_MODE=1`` but NOT
``THE_ONE_SANDBOX_DISABLED``, so each test that wants to bypass the
bwrap path must opt in via ``monkeypatch.setenv``.
"""

from __future__ import annotations

import logging
import sys
import time
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.mcp import _pool


@pytest.fixture(autouse=True)
async def _clear_pool():
    """Reset the F4 pool between tests so eviction-counts don't bleed."""
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture
async def client_and_repo(tmp_path):
    """FastAPI client paired with a back-channel repo (mirrors test_mcp_connection_reset)."""
    db_path = tmp_path / "stdio.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
            yield c, repo

    await conn.close()


async def _seed_stdio(
    repo: MCPSourceRepository, sid: str, *, command="python", args=None, config_extra=None
) -> None:
    cfg: dict = {"command": command, "args": args or []}
    if config_extra:
        cfg.update(config_extra)
    src = MCPSource(
        id=sid,
        name="Stdio",
        type="stdio",
        config=cfg,
        secrets={},
    )
    await repo.create(src)


# ── Dispatch + persistence (mocked MCPClient) ───────────────────────────


async def test_stdio_test_connect_dispatches_to_stdio_helper(client_and_repo) -> None:
    """Stdio sources hit ``_build_and_test_stdio_mcp`` (no OAuth phases).

    Asserts MCPClient is constructed with ``auth_provider=None`` and the
    ``_probe_auth_posture`` HTTP probe is NOT called for stdio.
    """
    client, repo = client_and_repo
    await _seed_stdio(
        repo,
        "src-stdio-1",
        command="python",
        args=["-m", "tests.fixtures.mcp.hello_server", "--stdio"],
    )

    tool = MagicMock()
    tool.name = "echo"
    tool.description = "Echo a message"
    tool.input_schema = {"type": "object", "properties": {}}

    constructed_with_auth: list[bool] = []

    class _MockMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            constructed_with_auth.append(auth_provider is not None)
            self.source = source

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def list_tools(self):
            return [tool]

        @property
        def server_capabilities(self):
            return {"tools": {}}

        # F4 L2 (M08): spec-optional fields; default None for mocks that
        # don't care about the subtitle/instructions surfacing path.
        @property
        def server_info(self):
            return None

        @property
        def instructions(self):
            return None

        @property
        def meta(self):
            return None

        @property
        def negotiated_protocol_version(self):
            return "2025-06-18"

    probe_calls = {"n": 0}

    async def _no_probe(*args, **kwargs):
        probe_calls["n"] += 1
        return "no_auth"

    with (
        patch("the_one.mcp.client.MCPClient", _MockMCPClient),
        patch(
            "the_one.mcp.transports.streamable_http._probe_auth_posture",
            _no_probe,
        ),
    ):
        resp = await client.post("/api/mcp-sources/src-stdio-1/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert [t["name"] for t in body["tools"]] == ["echo"]
    # No auth_provider was threaded — bare MCPClient.
    assert constructed_with_auth == [False]
    # No HTTP auth probe should run for stdio.
    assert probe_calls["n"] == 0


async def test_stdio_test_connect_persists_tools_cache(client_and_repo) -> None:
    """Successful stdio Test persists tools + capabilities + last_updated.

    Cache shape mirrors the http no-auth helper's persistence pattern,
    minus ``auth_posture`` (stdio has no auth concept).
    """
    client, repo = client_and_repo
    await _seed_stdio(repo, "src-stdio-cache", command="python", args=["-m", "x"])

    tool1 = MagicMock()
    tool1.name = "echo"
    tool1.description = "Echo back"
    tool1.input_schema = {"type": "object"}
    tool2 = MagicMock()
    tool2.name = "add"
    tool2.description = "Add two ints"
    tool2.input_schema = {"type": "object"}
    fake_caps = {"tools": {}, "resources": None, "prompts": None}

    class _MockMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def list_tools(self):
            return [tool1, tool2]

        @property
        def server_capabilities(self):
            return fake_caps

        @property
        def server_info(self):
            return None

        @property
        def instructions(self):
            return None

        @property
        def meta(self):
            return None

        @property
        def negotiated_protocol_version(self):
            return "2025-06-18"

    before = time.time()
    with patch("the_one.mcp.client.MCPClient", _MockMCPClient):
        resp = await client.post("/api/mcp-sources/src-stdio-cache/test/connect")
    after = time.time()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"

    stored = await repo.get("src-stdio-cache")
    cache = stored.config["_cache"]
    assert [t["name"] for t in cache["tools"]] == ["echo", "add"]
    assert cache["capabilities"] == fake_caps
    assert before <= cache["last_updated"] <= after
    # auth_posture is an HTTP-path concept — must NOT appear for stdio.
    assert "auth_posture" not in cache


async def test_stdio_test_connect_surfaces_connection_error(client_and_repo) -> None:
    """Stdio Test path translates MCPConnectionError → ``{status: "error"}``."""
    from the_one.mcp.errors import MCPConnectionError

    client, repo = client_and_repo
    await _seed_stdio(repo, "src-stdio-err", command="nonexistent-command")

    class _ErrMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            raise MCPConnectionError("simulated stdio spawn failure")

        async def __aexit__(self, *args):
            return None

    with patch("the_one.mcp.client.MCPClient", _ErrMCPClient):
        resp = await client.post("/api/mcp-sources/src-stdio-err/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert "MCPConnectionError" in body["error"]
    # No cache should land on a failure.
    stored = await repo.get("src-stdio-err")
    assert (stored.config or {}).get("_cache") is None


async def test_stdio_test_connect_surfaces_sandbox_error(client_and_repo) -> None:
    """Stdio Test path translates SandboxError → ``{status: "error"}``."""
    from the_one.platform.sandbox.errors import SandboxError

    client, repo = client_and_repo
    await _seed_stdio(repo, "src-stdio-sbox", command="python", args=["-m", "x"])

    class _SandboxErrClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            raise SandboxError("bwrap rejected spawn (synthetic)")

        async def __aexit__(self, *args):
            return None

    with patch("the_one.mcp.client.MCPClient", _SandboxErrClient):
        resp = await client.post("/api/mcp-sources/src-stdio-sbox/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert "SandboxError" in body["error"]


async def test_stdio_test_connect_envelopes_unexpected_exception(client_and_repo) -> None:
    """Defense-in-depth: any non-typed exception → 200 ``{status: "error"}``.

    F9 L2 vibing — the stdio helper now has a catch-all ``except Exception``
    that converts unexpected exceptions (e.g., ``asyncio.CancelledError``
    leaking from MCPClient cleanup, or any other runtime error not in the
    typed catch list) into a structured error envelope rather than letting
    them escape as a 500 with HTML body. The frontend's ``resp.ok`` check
    is a parallel guard; this test pins the backend half of the contract.
    """
    client, repo = client_and_repo
    await _seed_stdio(repo, "src-stdio-leak", command="python", args=["-m", "x"])

    class _LeakingClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            # Untyped runtime error — must NOT escape the route as a 500.
            raise RuntimeError("simulated leak")

        async def __aexit__(self, *args):
            return None

    with patch("the_one.mcp.client.MCPClient", _LeakingClient):
        resp = await client.post("/api/mcp-sources/src-stdio-leak/test/connect")

    # 200 with structured envelope (NOT a 500).
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "error"
    # Type name and message both surface in the envelope so the operator
    # sees something actionable in the UI.
    assert "RuntimeError" in body["error"]
    assert "simulated leak" in body["error"]


async def test_no_auth_test_connect_envelopes_unexpected_exception(client_and_repo) -> None:
    """Defense-in-depth on the http no-auth helper too (Shape C symmetry).

    Mirror of the stdio test above for ``_build_and_test_no_auth_mcp``.
    The two helpers ship with parallel catch-all envelopes per F9 L2
    vibing; both must convert unexpected exceptions to structured errors.
    """
    client, repo = client_and_repo

    src = MCPSource(
        id="src-noauth-leak",
        name="NoAuth",
        type="streamable-http",
        config={"url": "https://example.com/mcp"},
        secrets={},
    )
    await repo.create(src)

    class _LeakingClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            raise RuntimeError("simulated http leak")

        async def __aexit__(self, *args):
            return None

    async def _no_auth_probe(*args, **kwargs):
        return "no_auth"

    with (
        patch("the_one.mcp.client.MCPClient", _LeakingClient),
        patch(
            "the_one.mcp.transports.streamable_http._probe_auth_posture",
            _no_auth_probe,
        ),
    ):
        resp = await client.post("/api/mcp-sources/src-noauth-leak/test/connect")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "error"
    assert "RuntimeError" in body["error"]
    assert "simulated http leak" in body["error"]


# ── Caplog gate (F6 baseline preservation) ──────────────────────────────


async def test_stdio_test_connect_no_disconnect_warning(client_and_repo, caplog) -> None:
    """No ``MCPClient.disconnect`` warnings emitted across the stdio Test path.

    F9 L2 §"Caplog gate" — stdio is the first re-assertion of the F6
    baseline since F6.6's transport-stack lifecycle fix; a regression here
    would be high-signal.
    """
    client, repo = client_and_repo
    await _seed_stdio(repo, "src-stdio-quiet", command="python", args=["-m", "x"])

    tool = MagicMock()
    tool.name = "noop"
    tool.description = ""
    tool.input_schema = {}

    class _CleanMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def list_tools(self):
            return [tool]

        @property
        def server_capabilities(self):
            return {"tools": {}}

        @property
        def server_info(self):
            return None

        @property
        def instructions(self):
            return None

        @property
        def meta(self):
            return None

        @property
        def negotiated_protocol_version(self):
            return "2025-06-18"

    with caplog.at_level(logging.WARNING), patch("the_one.mcp.client.MCPClient", _CleanMCPClient):
        resp = await client.post("/api/mcp-sources/src-stdio-quiet/test/connect")
        assert resp.json()["status"] == "ok"

    disconnect_warnings = [r for r in caplog.records if "disconnect" in r.message.lower()]
    assert disconnect_warnings == [], (
        f"Unexpected MCPClient.disconnect warnings on stdio Test path: {disconnect_warnings}"
    )


# ── Real-subprocess integration (FastMCP fixture) ────────────────────────


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="stdio MCP fixture is POSIX-shell shaped; skip on Windows CI",
)
async def test_stdio_test_connect_against_fastmcp_fixture_returns_echo_add(
    client_and_repo,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    """End-to-end stdio Test against the in-repo FastMCP fixture.

    Spawns ``python -m tests.fixtures.mcp.hello_server --stdio`` as the
    stdio MCP server, runs the Test path with the SANDBOX-DISABLED bypass
    (per ``the_one/mcp/transports/stdio.py:241-249`` — pytest's conftest
    sets ``THE_ONE_TEST_MODE`` automatically; this test must explicitly
    add ``THE_ONE_SANDBOX_DISABLED=1`` to bypass bwrap which is not
    universally available in dev shells).

    Expected:
      - ``{status: "ok", tools: [echo, add], capabilities: {...}}``
      - cache populated with tools + capabilities + last_updated
      - 0 ``MCPClient.disconnect`` warnings across teardown (caplog gate)
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    # THE_ONE_TEST_MODE is set automatically by tests/conftest.py::pytest_configure.

    client, repo = client_and_repo
    # Use the current Python interpreter so the import path resolves to
    # the in-repo tests.fixtures.mcp.hello_server.
    await _seed_stdio(
        repo,
        "src-fastmcp-fixture",
        command=sys.executable,
        args=["-m", "tests.fixtures.mcp.hello_server", "--stdio"],
    )

    with caplog.at_level(logging.WARNING):
        resp = await client.post(
            "/api/mcp-sources/src-fastmcp-fixture/test/connect",
            timeout=30.0,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok", body
    tool_names = sorted(t["name"] for t in body["tools"])
    assert tool_names == ["add", "echo"], tool_names
    # Capabilities present (FastMCP exposes 'tools' at minimum).
    assert "tools" in body["capabilities"]

    # Cache populated.
    stored = await repo.get("src-fastmcp-fixture")
    cache = stored.config["_cache"]
    assert sorted(t["name"] for t in cache["tools"]) == ["add", "echo"]
    assert cache["capabilities"] == body["capabilities"]
    assert cache["last_updated"] > 0
    # Stdio path does not write auth_posture.
    assert "auth_posture" not in cache

    # Caplog gate: F6 baseline must hold across stdio teardown.
    disconnect_warnings = [r for r in caplog.records if "disconnect" in r.message.lower()]
    assert disconnect_warnings == [], (
        f"Unexpected MCPClient.disconnect warnings on stdio Test path: "
        f"{[r.message for r in disconnect_warnings]}"
    )

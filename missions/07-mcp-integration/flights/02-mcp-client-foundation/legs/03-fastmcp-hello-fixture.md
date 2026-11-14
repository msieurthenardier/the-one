# Leg: 03-fastmcp-hello-fixture

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Author an in-repo FastMCP "hello world" fixture (`tests/fixtures/mcp/hello_server.py`) that runs as either a stdio subprocess or an in-process ASGI app, plus the pytest fixtures that wire it for both modes. Adds the integration-test plumbing that L4 (streamable-http) and L5 (stdio) will consume — without invoking `MCPClient` itself yet.

## Context

- **Flight design** §7: in-repo FastMCP fixture, no `mcp-server-everything` npm dependency. Fixture lives at `tests/fixtures/mcp/hello_server.py` per the runnable-script convention (NOT `tests/_mcp_fixtures.py` underscore-helper convention — the file has a `__main__` block, so it's a script, not a helper module)
- **Two trivial tools**: `echo(message: str) -> str` returning `message` verbatim (text-only result path); `add(a: int, b: int) -> int` returning `a + b` (typed return → exercises the SDK's `structuredContent` shape)
- **Two run modes**: `--stdio` (calls `FastMCP.run('stdio')`); `--http` (returns the Starlette ASGI app from `FastMCP.streamable_http_app()` — but this mode is NOT actually invoked by the CLI; the `--http` flag is a marker for documentation, while pytest fixtures call a `make_mcp_app()` factory and call `streamable_http_app()` directly)
- **In-process ASGI pattern (THREE non-obvious requirements)**: pytest fixture (1) calls a `make_mcp_app()` factory PER TEST — NOT a module-level `mcp_app` — because `StreamableHTTPSessionManager.run()` enforces once-per-instance (`mcp/server/streamable_http_manager.py:99-138`); (2) drives the Starlette **lifespan startup explicitly** via `asgi-lifespan`'s `LifespanManager` because `httpx.ASGITransport` does NOT fire lifespan events, leaving FastMCP's `_task_group=None` which crashes on the first POST; (3) instantiates `FastMCP("hello", transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))` because FastMCP auto-enables DNS-rebinding protection (`mcp/server/transport_security.py`) for `host="127.0.0.1"` (the constructor default) which returns 421 for `Host: test` headers. All three are required; verified by reviewer reproduction in the dev container against `mcp==1.27.0`. After these fixes, L4 will pass the lifespan-driven client into `streamable_http_client(url=..., http_client=client)`
- **L3 does NOT call `MCPClient`** — it only verifies the SDK's raw client (`mcp.ClientSession` over `stdio_client` / `streamable_http_client`) can connect to the fixture and call its tools. L4/L5 thread `MCPClient` through these same fixtures
- **Host-vs-container Python**: per L1 flight log, the host has stale `mcp 1.18.0`; the dev container has `mcp 1.27.0`. All test runs and verification commands MUST run inside the dev container (`docker compose exec the-one ...`). Host invocations will fail with `ImportError: cannot import name 'streamable_http_client'` (1.18.0 only has the deprecated `streamablehttp_client`)
- **Smoke tests** in `tests/test_mcp_integration.py` (NEW file) — 2 tests, one per transport — exercise the bare SDK round-trip without `MCPClient`. L4/L5 will add `MCPClient`-flavored integration tests to the same file in their respective legs

## Inputs

What exists before this leg runs:
- L1 outputs (SDK pin, module skeleton, error/dataclass types)
- L2 outputs (`MCPClient` lifecycle + handshake — NOT used by L3)
- `mcp==1.27.0` SDK installed in the dev container, exporting `mcp.server.fastmcp.FastMCP` with `streamable_http_app() -> Starlette` method, `tool()` decorator (parens-form required), `run(transport='stdio')` method, `mcp.server.transport_security.TransportSecuritySettings` for DNS-rebinding protection control
- `httpx` already a base dependency of the-one (verified via `pyproject.toml`); `ASGITransport` available
- `asgi-lifespan` NOT yet a dev dependency — L3 adds `asgi-lifespan>=2.0` to `[project.optional-dependencies] dev = [...]` in `pyproject.toml`. Used to drive Starlette's lifespan startup events under `httpx.ASGITransport` (which doesn't fire lifespan automatically). This is the canonical pattern for in-process ASGI testing
- `tests/conftest.py` with project-wide fixtures (`FakeLLM`, `StubTool`); `asyncio_mode = "auto"` in pyproject pytest config
- `tests/_pty_fixtures.py` exists (helper-module precedent under `tests/`)
- No `tests/fixtures/` directory yet

## Outputs

What exists after this leg completes:
- `pyproject.toml` — `asgi-lifespan>=2.0` added to `[project.optional-dependencies] dev = [...]`
- `tests/fixtures/__init__.py` (NEW; empty package marker — required by `--import-mode=importlib`)
- `tests/fixtures/mcp/__init__.py` (NEW; empty package marker)
- `tests/fixtures/mcp/hello_server.py` (NEW) — runnable FastMCP server with `echo` and `add` tools exposed via a `make_mcp_app() -> FastMCP` factory + module-level `mcp_app = make_mcp_app()` for stdio subprocess use; `__main__` block dispatching on `--stdio` (default) vs `--http` flag
- `tests/conftest.py` extended with TWO new pytest fixtures:
  - `mcp_fixture_stdio_params` (function-scoped) — yields a `dict[str, Any]` shaped like `StdioServerParameters(command="python", args=["-m", "tests.fixtures.mcp.hello_server", "--stdio"], env={...minimal...})` for L4/L5 to feed into `mcp.client.stdio.stdio_client`
  - `mcp_fixture_http_client` (async function-scoped) — calls `make_mcp_app()` per-test (NOT module-level `mcp_app`); drives the Starlette ASGI app's lifespan via `asgi_lifespan.LifespanManager`; yields `(client: httpx.AsyncClient, url: str)` with `client.transport = ASGITransport(app=app)` and `url = "http://localhost/mcp"` (matches FastMCP's default DNS-rebinding allowlist `["localhost:*", ...]`); also passes `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)` to `make_mcp_app` for defense-in-depth
- `tests/test_mcp_integration.py` (NEW) — 2 smoke tests:
  - `test_stdio_smoke_via_raw_sdk`: spawns the fixture as subprocess, opens `stdio_client` cm + `ClientSession`, calls `session.initialize()`, asserts `protocolVersion == "2025-11-25"`, calls `session.list_tools()` returns 2 tools (`echo`, `add`), calls `session.call_tool("echo", {"message": "hi"})` round-trip
  - `test_streamable_http_smoke_via_raw_sdk`: uses in-process ASGI fixture, opens `streamable_http_client(url, http_client=...)` cm + `ClientSession`, same assertions
- Pytest can discover and collect both new tests; they run within the dev container in <5 seconds combined; both pass green

## Acceptance Criteria

- [ ] `pyproject.toml` `[project.optional-dependencies]` has `asgi-lifespan>=2.0` added to the `dev` list (after `pixelmatch>=0.3`); `pip install -e ".[dev]"` resolves cleanly in the container
- [ ] `tests/fixtures/__init__.py` exists (empty file with `"""Pytest fixture packages."""` docstring)
- [ ] `tests/fixtures/mcp/__init__.py` exists (empty file with `"""MCP test-fixture servers."""` docstring)
- [ ] `tests/fixtures/mcp/hello_server.py` exists, has the shape:
  - A `make_mcp_app() -> FastMCP` factory function that constructs a fresh `FastMCP("hello", transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))`, registers `echo` and `add` tools on it, and returns the instance
  - A module-level `mcp_app: FastMCP = make_mcp_app()` for the stdio subprocess path (the subprocess imports this module and runs `mcp_app.run("stdio")`)
  - Two tools registered via `@app.tool()` decorator inside `make_mcp_app()`: `echo(message: str) -> str` returning `message` verbatim; `add(a: int, b: int) -> int` returning `a + b`
  - `__main__` block parses `argv` for `--stdio` (default) or `--http`; on `--stdio` calls `mcp_app.run("stdio")`; on `--http` prints a usage message pointing at the in-process pytest fixture pattern
  - File is < 100 LOC (relaxed from <80 to accommodate factory pattern + `transport_security` import)
- [ ] **Subprocess shape**: `python -m tests.fixtures.mcp.hello_server --stdio` (run from project root) starts the server and reads/writes JSON-RPC over stdin/stdout. Verified by smoke test `test_stdio_smoke_via_raw_sdk`
- [ ] **In-process shape**: `from tests.fixtures.mcp.hello_server import make_mcp_app; app = make_mcp_app().streamable_http_app()` returns a `Starlette` instance that, **once driven through lifespan startup**, accepts JSON-RPC over `httpx.AsyncClient(transport=ASGITransport(app=app))` at path `/mcp` with `Host: localhost`. Verified by smoke test `test_streamable_http_smoke_via_raw_sdk`
- [ ] `tests/conftest.py` extended with `mcp_fixture_stdio_params` fixture:
  - Function-scoped (default; per-test fresh subprocess via the SDK's `stdio_client`)
  - Returns a `dict[str, Any]` literal matching `StdioServerParameters` keyword args: `{"command": sys.executable, "args": ["-m", "tests.fixtures.mcp.hello_server", "--stdio"], "env": {"PATH": os.environ["PATH"], "PYTHONPATH": str(PROJECT_ROOT)}, "cwd": None}` — the `PYTHONPATH` line is critical so the subprocess can import `tests.fixtures.mcp.hello_server`
  - Test author calls `from mcp.client.stdio import StdioServerParameters; params = StdioServerParameters(**fixture_dict)` to construct the typed object — fixture returns a dict to keep the dependency on the SDK's import surface narrow
- [ ] `tests/conftest.py` extended with `mcp_fixture_http_client` fixture:
  - Async function-scoped (default; per-test fresh `FastMCP` instance + driven lifespan + fresh client)
  - **Builds a NEW `FastMCP` per test** by calling `make_mcp_app()` — the module-level `mcp_app` is reserved for the stdio subprocess path because `StreamableHTTPSessionManager.run()` is once-per-instance
  - **Drives Starlette lifespan startup** via `asgi_lifespan.LifespanManager(app)` — `httpx.ASGITransport` does NOT auto-fire lifespan events, leaving the FastMCP session manager's task group unstarted
  - Yields a 2-tuple `(client: httpx.AsyncClient, url: str)`:
    - `client = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")`
    - `url = "http://localhost/mcp"` (matches FastMCP's default `streamable_http_path = "/mcp"` AND the DNS-rebinding allowlist `["localhost:*", ...]` — though the fixture also disables that protection at the FastMCP level)
  - Tears down: exits `LifespanManager` and closes the client on fixture exit
- [ ] `tests/test_mcp_integration.py` (NEW) contains exactly 2 smoke tests, both passing:
  - `test_stdio_smoke_via_raw_sdk(mcp_fixture_stdio_params)`:
    1. Build `StdioServerParameters(**mcp_fixture_stdio_params)`
    2. `async with stdio_client(params) as (read, write):` `async with ClientSession(read, write) as session:`
    3. `result = await session.initialize()` — assert `result.protocolVersion == "2025-11-25"`, `result.capabilities.tools is not None`
    4. `tools_result = await session.list_tools()` — assert `len(tools_result.tools) == 2`, `{t.name for t in tools_result.tools} == {"echo", "add"}`
    5. `call_result = await session.call_tool("echo", {"message": "hi"})` — assert `call_result.isError is False`, `call_result.content[0].text == "hi"`
  - `test_streamable_http_smoke_via_raw_sdk(mcp_fixture_http_client)`:
    1. Unpack `client, url = mcp_fixture_http_client`
    2. `async with streamable_http_client(url, http_client=client) as (read, write, _):` `async with ClientSession(read, write) as session:`
    3. Same `initialize` / `list_tools` / `call_tool` assertions as the stdio test
- [ ] **All tests run inside the dev container** (`docker compose exec the-one make test` or equivalent) since the host's `mcp 1.18.0` doesn't have `streamable_http_client`
- [ ] No new ruff errors (`make lint` clean, in-container)
- [ ] **Test count after L3**: 1117 baseline (post-L2) + 2 new integration tests = **exactly 1119 passing** + 1 skipped (288 deselected may shift slightly; the active-test count is the number to pin)
- [ ] Test runtime: both new integration tests complete in <5 seconds combined (subprocess startup is ~1-2s; in-process ASGI is <0.1s)

## Verification Steps

```bash
# Run inside the container — host has stale mcp 1.18.0
cd ~/projects/the-one

# File inventory
ls tests/fixtures/mcp/
test -f tests/fixtures/__init__.py && echo "fixtures pkg OK"
test -f tests/fixtures/mcp/__init__.py && echo "mcp fixtures pkg OK"
test -f tests/fixtures/mcp/hello_server.py && echo "hello_server.py OK"
wc -l tests/fixtures/mcp/hello_server.py  # expect <80

# Subprocess smoke (manual sanity check before pytest)
docker compose exec the-one python -c "
import subprocess, sys, json
proc = subprocess.Popen(
    [sys.executable, '-m', 'tests.fixtures.mcp.hello_server', '--stdio'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd='<repo>',  # the repository root (placeholder)
)
# Quick liveness probe — server should not exit immediately
import time; time.sleep(0.5)
print('subprocess.poll() (None means alive):', proc.poll())
proc.terminate(); proc.wait(timeout=2)
"

# In-process app smoke
docker compose exec the-one python -c "
from tests.fixtures.mcp.hello_server import mcp_app
app = mcp_app.streamable_http_app()
print('Starlette app:', type(app).__name__)
print('routes:', [r.path for r in app.routes][:5])
"

# Pytest collection — confirms fixtures and integration tests are discovered
docker compose exec the-one pytest --collect-only -q tests/test_mcp_integration.py 2>&1 | tail -10

# Run the new tests in isolation
docker compose exec the-one pytest tests/test_mcp_integration.py -v 2>&1 | tail -20

# Full suite + lint
docker compose exec the-one make test
docker compose exec the-one make lint
```

## Implementation Guidance

1. **Create the fixture package directories.** Both `__init__.py` files must exist for pytest's `--import-mode=importlib` to resolve `tests.fixtures.mcp.hello_server` as an importable module path:

   `tests/fixtures/__init__.py`:
   ```python
   """Pytest fixture packages."""
   ```

   `tests/fixtures/mcp/__init__.py`:
   ```python
   """MCP test-fixture servers."""
   ```

2. **Add `asgi-lifespan>=2.0` to `pyproject.toml`** `[project.optional-dependencies] dev = [...]` (after `pixelmatch>=0.3`):

   ```toml
   dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.6", "playwright==1.58.0", "pytest-playwright>=0.5", "pillow>=10.0", "pixelmatch>=0.3", "asgi-lifespan>=2.0"]
   ```

3. **Write `tests/fixtures/mcp/hello_server.py`** (target <100 LOC; factory pattern):

   ```python
   """In-repo FastMCP "hello world" server for F2 integration tests.

   Exposes two trivial tools: ``echo`` (text-only result) and ``add``
   (typed-return triggering the SDK's structuredContent path).

   The HTTP integration-test path requires a fresh FastMCP per test
   (StreamableHTTPSessionManager.run() is once-per-instance), so this
   module exposes a ``make_mcp_app()`` factory in addition to the
   module-level ``mcp_app`` used by the stdio subprocess.

   Run modes:
     --stdio : run as stdio JSON-RPC server (calls FastMCP.run("stdio"))
     --http  : prints a usage hint — HTTP tests are in-process via the
               ``mcp_fixture_http_client`` pytest fixture, NOT a real socket.

   See flight 02 design decision §7 for the fixture's role in F2 testing.
   """

   from __future__ import annotations

   import sys

   from mcp.server.fastmcp import FastMCP
   from mcp.server.transport_security import TransportSecuritySettings


   def make_mcp_app() -> FastMCP:
       """Build a fresh FastMCP server with the F2 hello tools registered.

       DNS-rebinding protection is DISABLED here — the in-process ASGI
       fixture sends requests with a synthetic Host header, and FastMCP's
       default protection (active for host="127.0.0.1") would otherwise
       return 421 Misdirected Request.
       """
       app = FastMCP(
           "hello",
           transport_security=TransportSecuritySettings(
               enable_dns_rebinding_protection=False,
           ),
       )

       @app.tool()
       def echo(message: str) -> str:
           """Return the input message verbatim."""
           return message

       @app.tool()
       def add(a: int, b: int) -> int:
           """Return the sum of two integers."""
           return a + b

       return app


   # Module-level instance — reserved for the stdio subprocess path
   # (see __main__). HTTP fixture must call make_mcp_app() per-test
   # because StreamableHTTPSessionManager.run() enforces once-per-instance.
   mcp_app: FastMCP = make_mcp_app()


   def main(argv: list[str] | None = None) -> int:
       args = list(argv if argv is not None else sys.argv[1:])
       mode = args[0] if args else "--stdio"

       if mode == "--stdio":
           mcp_app.run("stdio")
           return 0

       if mode == "--http":
           print(
               "tests/fixtures/mcp/hello_server.py: --http is documentation only.",
               file=sys.stderr,
           )
           print(
               "HTTP tests run in-process via the mcp_fixture_http_client pytest "
               "fixture (no real socket).",
               file=sys.stderr,
           )
           return 0

       print(
           f"unknown mode: {mode!r}; expected --stdio or --http",
           file=sys.stderr,
       )
       return 2


   if __name__ == "__main__":
       sys.exit(main())
   ```

3. **Extend `tests/conftest.py`** with the two new fixtures. Append at the END of the file (after `StubTool` and any existing fixtures):

   ```python
   # ---------------------------------------------------------------------------
   # MCP fixtures (F2 L3) — shared by L4 (streamable-http) and L5 (stdio)
   # integration tests, plus the L3 smoke tests in tests/test_mcp_integration.py.
   # ---------------------------------------------------------------------------

   import os
   import sys
   from pathlib import Path

   _PROJECT_ROOT = Path(__file__).resolve().parent.parent  # tests/conftest.py → project root


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
   ```

   The `import os`, `import sys`, `from pathlib import Path` lines belong at the top of the file with the other imports — move them up if they're not already imported by the existing conftest contents. The `import httpx` and `from asgi_lifespan import LifespanManager` and `from tests.fixtures.mcp.hello_server import make_mcp_app` are kept inside the fixture body to keep import-time costs minimal for test runs that don't touch the MCP fixture.

4. **Write `tests/test_mcp_integration.py`** (NEW file):

   ```python
   """F2 integration tests — real SDK round-trips against the in-repo FastMCP fixture.

   L3: 2 smoke tests verifying both transports work via the bare SDK (no MCPClient).
   L4: adds MCPClient-flavored streamable-http tests.
   L5: adds MCPClient-flavored stdio tests.
   L6a/b: extends with list_tools/call_tool error-path tests.
   """

   from __future__ import annotations

   import pytest

   from mcp import ClientSession
   from mcp.client.stdio import StdioServerParameters, stdio_client
   from mcp.client.streamable_http import streamable_http_client


   class TestL3IntegrationSmoke:
       async def test_stdio_smoke_via_raw_sdk(
           self, mcp_fixture_stdio_params: dict
       ) -> None:
           params = StdioServerParameters(**mcp_fixture_stdio_params)
           async with stdio_client(params) as (read, write):
               async with ClientSession(read, write) as session:
                   init_result = await session.initialize()
                   assert init_result.protocolVersion == "2025-11-25"
                   assert init_result.capabilities.tools is not None

                   tools_result = await session.list_tools()
                   assert len(tools_result.tools) == 2
                   assert {t.name for t in tools_result.tools} == {"echo", "add"}

                   echo_result = await session.call_tool("echo", {"message": "hi"})
                   assert echo_result.isError is False
                   # SDK returns content blocks; first block should be text "hi"
                   assert echo_result.content[0].text == "hi"

       async def test_streamable_http_smoke_via_raw_sdk(
           self, mcp_fixture_http_client
       ) -> None:
           client, url = mcp_fixture_http_client
           async with streamable_http_client(url, http_client=client) as (
               read,
               write,
               _get_session_id,
           ):
               async with ClientSession(read, write) as session:
                   init_result = await session.initialize()
                   assert init_result.protocolVersion == "2025-11-25"
                   assert init_result.capabilities.tools is not None

                   tools_result = await session.list_tools()
                   assert len(tools_result.tools) == 2
                   assert {t.name for t in tools_result.tools} == {"echo", "add"}

                   echo_result = await session.call_tool("echo", {"message": "hi"})
                   assert echo_result.isError is False
                   assert echo_result.content[0].text == "hi"
   ```

5. **Run lint + tests inside the container**:
   ```bash
   docker compose exec the-one make test ARGS='-k TestL3IntegrationSmoke -v'
   docker compose exec the-one make test
   docker compose exec the-one make lint
   ```

6. **Update flight log L3 entry** in `## Leg Progress / ### L3: FastMCP hello fixture` covering: status (landed), changes made (fixture file, conftest fixtures, integration-test file, ASGI in-process pattern verified), notes (any deviations — esp. if `streamable_http_app()` returns something unexpected), test count before/after (1117 → 1119), lint status.

## Edge Cases

- **`PYTHONPATH` for subprocess**: the spawned `python -m tests.fixtures.mcp.hello_server` won't find the package without `PYTHONPATH=<project root>` because the `-m` resolution starts from `sys.path`. The fixture explicitly sets `PYTHONPATH` to the project root.

- **`stdio_client` writes to subprocess stderr by default**: the SDK's `stdio_client` (in `mcp/client/stdio/__init__.py`) accepts an `errlog` parameter defaulting to `sys.stderr`. FastMCP servers log INFO-level startup messages to stderr. This is fine for tests but produces output during `pytest -v`. Acceptable; not silenced.

- **`base_url="http://localhost"` host choice**: required because FastMCP's default `host="127.0.0.1"` triggers `TransportSecuritySettings(enable_dns_rebinding_protection=True)` which only allows `Host` headers in `["127.0.0.1:*", "localhost:*", "[::1]:*"]`. The ASGI fixture sends a synthetic `Host` header derived from `base_url` (no real DNS lookup happens — `ASGITransport` routes by scope). `make_mcp_app()` disables the DNS-rebinding protection explicitly for defense-in-depth, but `localhost` is also chosen for consistency. Do NOT use `http://test` — that triggers 421 Misdirected Request from the protection middleware.

- **`stdio_client` env-merge behavior**: the SDK's `stdio_client` (in `mcp/client/stdio/__init__.py`) merges `StdioServerParameters.env` ON TOP of `get_default_environment()` (NOT a replacement). So the fixture's `{"PATH": ..., "PYTHONPATH": ...}` overlays a default env that already includes `HOME`, `LANG`, etc. This is more robust than full-replacement (FastMCP startup wouldn't choke on missing `HOME`), but tests exercising `build_stdio_environ` precedence in L5 must factor this in: the SDK applies its OWN allowlist UNDER our supplied env, so L5's `build_stdio_environ` output is what reaches the SDK, and the SDK then layers `get_default_environment()` underneath. L5's helper produces the *operator-side* environ; the SDK's transport adds the floor.

- **FastMCP `tool()` decorator behavior**: `@mcp_app.tool()` requires parentheses (verified at design time — the decorator is parameterized: `@mcp_app.tool(name=..., description=...)`). A bare `@mcp_app.tool` (without parens) raises `TypeError`. Stick with `@mcp_app.tool()` calls.

- **ASGI integration: `httpx.AsyncClient.aclose()` vs the SDK's auto-cleanup**: the SDK's `streamable_http_client` cm exits before the test fixture's `client.aclose()` runs. The SDK should not call `client.aclose()` on a client passed via `http_client=` — the SDK's docstring says the caller owns the client lifecycle. Verified by the new SDK signature including `terminate_on_close: bool = True` (which controls the SDK's session-termination behavior, NOT the http_client's lifecycle).

- **`call_result.content[0].text` vs `call_result.content[0]`**: SDK content blocks are typed Pydantic objects (`TextContent`, `ImageContent`, etc.). For `echo("hi")`, the FastMCP server wraps the string return into a `TextContent(text="hi")`. Accessing `.text` is correct. If a future SDK shape change moves the text to a different field, this test will fail loudly — that's the intended regression behavior.

- **Test runtime budget**: subprocess startup (Python interpreter cold-start + FastMCP init) is ~0.5-1.5s. In-process ASGI startup is <0.1s. Combined wall-clock for both tests should be <5s. If subprocess startup exceeds 3s, investigate (likely Python cold-start in the slim container; not a fix-in-this-leg concern).

- **Pytest collection from package paths**: `--import-mode=importlib` + `pythonpath = ["tests"]` (per `pyproject.toml`) means `tests.fixtures.mcp.hello_server` resolves correctly. Without `tests/fixtures/__init__.py`, importlib resolution still works (namespace packages), but adding the explicit package marker is more forgiving across pytest versions and editor tooling.

- **`mcp.client.streamable_http.streamable_http_client` vs `streamablehttp_client`**: the leg uses ONLY the current name. The deprecated `streamablehttp_client` exists in 1.27.0 (with `@deprecated` decorator) but is omitted from this leg. The host's `mcp 1.18.0` does NOT have `streamable_http_client` — the test must run in-container.

- **`mcp_app` as the module-level identifier**: chosen over `app` to avoid namespace collision if a future test does `from tests.fixtures.mcp.hello_server import app` thinking it's the Starlette ASGI app (`mcp_app.streamable_http_app()` is the ASGI app; `mcp_app` is the FastMCP server).

- **Naming consistency for L4/L5**: the parent flight.md L4 description references `mcp_fixture_http_asgi` — L3's actual fixture name is `mcp_fixture_http_client` (more accurate; yields a client+url pair). L4's leg artifact MUST use the actual name `mcp_fixture_http_client`.

- **`add` tool's structured-content shape (for L4/L5/L6 awareness)**: when `call_tool("add", {"a": 1, "b": 2})` runs against the fixture, the SDK returns a `CallToolResult` with `result.content[0].text == "3"` (str-coerced from int return) AND `result.structuredContent == {"result": 3}` (FastMCP wraps non-dict returns under a `result` key). L6a's `MCPToolResult` rendering will parse both shapes; L4/L5 integration tests can assert on either. The leg's L3 smoke test only exercises `echo` (text-only path); L4/L5 will exercise `add` to validate the structured-content path.

- **CI subprocess startup variance**: subprocess Python cold-start is ~0.5-0.8s in the slim dev container plus ~0.2-0.4s for FastMCP init. If CI environments add latency that pushes this >3s combined per test, switch to a session-scoped subprocess fixture (single subprocess for the whole test session) — but note that a session-scoped subprocess doesn't compose with `MCPClient`'s per-call connect/disconnect lifecycle (each test would need to open a fresh `ClientSession` over the same subprocess pipes, which the SDK's `stdio_client` doesn't support). If session-scoping is needed, the alternative is moving stdio integration tests to a process pool. Defer this concern to L5 if it surfaces.

## Files Affected

- `pyproject.toml` — `asgi-lifespan>=2.0` added to `[project.optional-dependencies] dev`
- `tests/fixtures/__init__.py` (NEW)
- `tests/fixtures/mcp/__init__.py` (NEW)
- `tests/fixtures/mcp/hello_server.py` (NEW; <100 LOC)
- `tests/conftest.py` — extend with `mcp_fixture_stdio_params` and `mcp_fixture_http_client` fixtures (+ supporting imports)
- `tests/test_mcp_integration.py` (NEW; ~50 LOC including imports + 2 smoke tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — exactly 1119 passing + 1 skipped (1117 baseline post-L2 + 2 new TestL3IntegrationSmoke tests)
- [ ] `make lint` clean (no NEW ruff errors) — run inside the container
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress / ### L3: FastMCP hello fixture`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end

## Citation Audit

5 SDK + repo citations verified at leg-design time:

1. `mcp.server.fastmcp.FastMCP` — verified import works in container; constructor accepts `name` positionally; `run(transport)` and `streamable_http_app() -> Starlette` exposed; `@mcp_app.tool()` decorator pattern (with parens) works
2. `mcp.client.streamable_http.streamable_http_client(url, *, http_client=None, terminate_on_close=True)` — verified signature in container's `mcp 1.27.0`; returns 3-tuple `(read, write, get_session_id)`. The deprecated `streamablehttp_client` is also present but NOT used by F2
3. `mcp.client.stdio.stdio_client(StdioServerParameters)` — verified import works in container; SDK 1.27.0 exports both `stdio_client` and `StdioServerParameters` from `mcp.client.stdio`
4. `httpx.ASGITransport(app=...)` — verified available; standard pattern for in-process ASGI testing
5. `tests/conftest.py` — verified existing structure (FakeLLM, StubTool); `pyproject.toml:[tool.pytest.ini_options]` confirms `asyncio_mode = "auto"` and `--import-mode=importlib` + `pythonpath = ["tests"]`

All citations clean — no drift.

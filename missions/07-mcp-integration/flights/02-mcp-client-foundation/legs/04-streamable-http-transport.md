# Leg: 04-streamable-http-transport

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Wire the streamable-http transport into `MCPClient` end-to-end. Implement `build_request_headers(source)` (2-layer flat-merge of `config.headers ∪ secrets`, secrets win) and `connect_streamable_http(source, *, http_client=None)` (an `@asynccontextmanager` yielding a fully-entered `ClientSession`); update `_transport_connect` in `client.py` so its `streamable-http` branch delegates to the new helper. Static-bearer auth emerges from the kv-table itself — operator types `Authorization | Bearer xxx | sensitive=true` and the helper materializes it as a header. No OAuth flow (F5).

## Context

- **Flight design** §11 (env-var assembly shape — analogous pattern for headers); §2 (MCPClient API surface — `connect()` dispatches via `_transport_connect`); §6 (SDK pin); §10 (fail-hard version handshake — already enforced by L2's `connect()` body, so L4 just needs to feed a real `ClientSession`)
- **L2's `_transport_connect`** is a single `@asynccontextmanager` (`the_one/mcp/client.py::_transport_connect`) with `if source.type == "streamable-http": raise NotImplementedError(...)`. L4 replaces that branch with `async with connect_streamable_http(source) as session: yield session`. The stdio branch stays untouched (L5 fills it)
- **L3 fixture `mcp_fixture_http_client`** yields `(client: httpx.AsyncClient, url: str)` with the ASGI transport + driven lifespan. Integration tests inject `client` into the streamable-http transport via a module-level test seam (`_test_http_client_override`) — production code never reads this
- **F1's API validator** already validates `config.headers: dict[str, str]` (`the_one/interfaces/web/api.py::_validate_mcp_source_config` streamable-http branch). L4 trusts the model — the helper does NOT re-validate
- **Reviewer's note from L3 design review**: flight.md L4's description used the name `mcp_fixture_http_asgi`; L3 actually shipped `mcp_fixture_http_client`. L4 uses the actual name
- **The `add` tool returns structured content**: L4's integration test that calls `add` will see `result.content[0].text == "3"` AND `result.structuredContent == {"result": 3}` (FastMCP wraps non-dict returns under `result`). L6a's `MCPToolResult` parses both shapes; L4 just exercises the SDK's raw response

## Inputs

What exists before this leg runs:
- L1+L2 outputs: `MCPClient` lifecycle, error hierarchy, dataclasses, `_transport_connect` dispatch helper with a `streamable-http` branch raising `NotImplementedError("transport 'streamable-http' not implemented; L4 lands it")`
- L3 outputs: `tests/fixtures/mcp/hello_server.py` with `make_mcp_app()` factory; `mcp_fixture_http_client` pytest fixture in `tests/conftest.py` (yields `(client, url)`)
- `the_one/mcp/transports/streamable_http.py` with placeholder docstring (L1 stub)
- `mcp.client.streamable_http.streamable_http_client(url, *, http_client=None, terminate_on_close=True)` SDK function (current name; NOT deprecated `streamablehttp_client`)
- `mcp.ClientSession(read_stream, write_stream)` constructor

## Outputs

What exists after this leg completes:
- `the_one/mcp/transports/streamable_http.py` — full implementation:
  - `build_request_headers(source: MCPSource) -> dict[str, str]` — flat-merge of `source.config.get("headers", {})` and `source.secrets`, secrets win on collision (uses `Mapping[str, str]` typing; raises nothing — F1 validator already gates the shape)
  - `connect_streamable_http(source: MCPSource, *, http_client: httpx.AsyncClient | None = None) -> AsyncIterator[ClientSession]` — `@asynccontextmanager`-decorated; nests `streamable_http_client(url, http_client=...)` then `ClientSession(read, write)` then yields the entered session
  - `_test_http_client_override: httpx.AsyncClient | None = None` — module-level test seam (NEVER mutated by production code; integration test fixture monkeypatches this so MCPClient can use the ASGI-transport client)
- `the_one/mcp/client.py::_transport_connect` — streamable-http branch replaced with `async with connect_streamable_http(source) as session: yield session`. The `NotImplementedError` for stdio remains (L5)
- `tests/test_mcp_client.py` extended with:
  - `TestBuildRequestHeaders` — 4 unit tests covering empty / sensitive-only / plaintext-only / mixed-with-collision (secrets-win) (no SDK / network / fixture involvement)
  - `TestConnectStreamableHttpProduction` — 1 unit test (`test_production_path_constructs_client_with_assembled_headers`) closing the L4 review's gap on header-injection verification (mocks the SDK functions and asserts the constructed httpx client has the bearer header in `client.headers["authorization"]`)
- `tests/test_mcp_integration.py` extended with:
  - `TestL4StreamableHttp` — 3 integration tests using `mcp_fixture_http_client` + the new `_test_http_client_override` seam:
    1. `test_connect_list_call_echo_via_mcpclient` — full MCPClient round-trip: connect → list_tools (assert 2 tools) → call_tool("echo", {"message": "hi"}) — but L4 hasn't implemented `list_tools`/`call_tool` yet (L6a does). **NOTE:** L4 STOPS at `connect()` succeeding; the list_tools/call_tool body remains the L2 stub raising `NotImplementedError("L6a implements list_tools")`. So L4's integration test asserts: `connect()` succeeds, `is_alive=True`, `negotiated_protocol_version == "2025-11-25"`, `server_capabilities` returns the expected dict shape with `tools` key, `disconnect()` cleans up
    2. `test_connect_with_static_bearer_header` — MCPSource with `config={"url": "http://localhost/mcp", "headers": {}}, secrets={"Authorization": "Bearer token"}`; the assembled headers dict (asserted via the integration's outgoing-request inspection or by spying on `streamable_http_client` calls) includes `Authorization: Bearer token`
    3. `test_connect_already_connected_raises_via_real_transport` — same as L2's mocked test but against the real ASGI transport; confirms the L2 contract holds end-to-end
- Test seam pattern: integration tests do `monkeypatch.setattr("the_one.mcp.transports.streamable_http._test_http_client_override", asgi_client)` before `await client.connect()`. The helper reads the seam ONLY when `http_client is None`. Production code passes `http_client=None` and the seam is also `None` → helper builds its own `httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0)` → real network connection
- Module-level lint: `ruff` clean (no NEW errors)
- Test count after L4: **1119 baseline (post-L3) + 4 (TestBuildRequestHeaders) + 1 (TestConnectStreamableHttpProduction) + 3 (TestL4StreamableHttp) = exactly 1127 passing** + 1 skipped (unchanged from baseline)

## Acceptance Criteria

- [ ] `the_one/mcp/transports/streamable_http.py::build_request_headers(source: MCPSource) -> dict[str, str]`:
  - Returns `{**source.config.get("headers", {}), **source.secrets}` (a flat-merge dict; secrets win on collision)
  - Does NOT validate types (F1's API validator already gates `config.headers: dict[str, str]`; the helper trusts the model)
  - Returns `{}` for both an empty headers dict AND no headers key at all
  - Pure function — no side effects, no I/O, no logging
- [ ] `the_one/mcp/transports/streamable_http.py::connect_streamable_http(source, *, http_client=None) -> AsyncIterator[ClientSession]`:
  - Decorated with `@asynccontextmanager`
  - `url = source.config["url"]` (raises `KeyError` if absent — F1's API validator gates this; the helper trusts the model)
  - Reads the test seam: `effective_client = http_client if http_client is not None else _test_http_client_override` BEFORE calling the SDK (production passes None → seam is also None → we build the httpx client; tests inject ASGI client via the seam)
  - Calls `headers = build_request_headers(source)` and applies them via the constructed httpx client. The SDK confirmed at L4 design review (in-container probe) does NOT accept a `headers=` kwarg — it builds its own httpx client when `http_client is None`. So **the helper builds the httpx client itself** for production:
    - **Production path** (`effective_client is None`): construct `httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=httpx.Timeout(30.0))` (mirrors `mcp.shared._httpx_utils.create_mcp_http_client` defaults without the private-module dependency); own its lifecycle via nested `async with`
    - **Test path** (`effective_client is not None`): MUTATE `effective_client.headers` by `effective_client.headers.update(headers)` before yielding to the SDK. The pytest-monkeypatch-isolated fixture is per-test fresh (L3's `mcp_fixture_http_client` is function-scoped + reseeded), so cross-test pollution is prevented by the L3 fixture lifetime, not by client immutability
    - Both branches yield to the SAME `streamable_http_client(url, http_client=client) → ClientSession(read, write)` LIFO-cleanup cascade
  - Yields a fully-entered ClientSession; on context exit, the session, transport, and (production-path-only) owned httpx client close in correct LIFO order
- [ ] `the_one/mcp/client.py::_transport_connect`'s streamable-http branch is replaced with:
  ```python
  if source.type == "streamable-http":
      from the_one.mcp.transports.streamable_http import connect_streamable_http
      async with connect_streamable_http(source) as session:
          yield session
  elif source.type == "stdio":
      raise NotImplementedError("transport 'stdio' not implemented; L5 lands it")
  ```
  - The import is local (inside the function body) to keep the SDK out of `client.py`'s module-load path
  - No `return` after `yield` — `if/elif/else` already prevents fall-through. The stdio branch stays as `raise NotImplementedError(...)` (untouched)
- [ ] **`TestBuildRequestHeaders` (4 unit tests in `tests/test_mcp_client.py`)**:
  1. `test_empty` — source with no `headers` key in config and empty secrets → `build_request_headers(source) == {}`
  2. `test_sensitive_only` — `config={"url": "http://x"}, secrets={"Authorization": "Bearer x"}` → `build_request_headers(source) == {"Authorization": "Bearer x"}`
  3. `test_plaintext_only` — `config={"url": "http://x", "headers": {"X-Trace": "1"}}, secrets={}` → `{"X-Trace": "1"}`
  4. `test_mixed_secrets_win` — `config={"url": "http://x", "headers": {"Authorization": "PLAIN", "X-Trace": "1"}}, secrets={"Authorization": "Bearer SECRET"}` → `{"Authorization": "Bearer SECRET", "X-Trace": "1"}` (secrets win on collision)
- [ ] **`TestL4StreamableHttp` (3 integration tests in `tests/test_mcp_integration.py`)**:
  1. `test_connect_via_mcpclient_against_asgi_fixture(mcp_fixture_http_client, monkeypatch)`:
     - `client_httpx, url = mcp_fixture_http_client`
     - `monkeypatch.setattr("the_one.mcp.transports.streamable_http._test_http_client_override", client_httpx)`
     - Build `MCPSource(id="src-1", name="hello", type="streamable-http", config={"url": url, "headers": {}}, secrets={})`
     - `client = MCPClient(source)`; `await client.connect()` — succeeds; `assert client.is_alive`; `assert client.negotiated_protocol_version == "2025-11-25"`; `caps = client.server_capabilities; assert isinstance(caps["tools"], dict) and "listChanged" in caps["tools"]` (tighter than just key presence — defends against future SDK regressions)
     - `await client.disconnect()`; `assert not client.is_alive`
     - Confirms L2's connect() body works end-to-end against a real ASGI-driven SDK transport
  2. `test_connect_with_secrets_does_not_break_connection(mcp_fixture_http_client, monkeypatch)`:
     - Same setup as #1 but `secrets={"Authorization": "Bearer test-token"}`
     - Assert `connect()` succeeds + `is_alive` after — proves the test branch's `effective_client.headers.update(headers)` mutation doesn't break the in-process ASGI transport
     - **NOTE**: this test does NOT verify the bearer header reaches the wire — that gap is closed by `test_production_path_constructs_client_with_assembled_headers` in the unit-test class (Option C). The integration test only proves end-to-end positive completion with secrets present
  3. `test_connect_already_connected_via_real_transport(mcp_fixture_http_client, monkeypatch)`:
     - Same setup as #1; call `connect()` once successfully; second `connect()` raises `MCPConnectionError("MCPClient is already connected.")` — proves L2's guard holds against the real transport
- [ ] **One additional unit test in `TestBuildRequestHeaders` (or a new `TestConnectStreamableHttpProduction` class) — Option C from L4 review**: `test_production_path_constructs_client_with_assembled_headers`:
  - Monkeypatches `the_one.mcp.transports.streamable_http.streamable_http_client` to a spy that captures the `http_client` argument and yields a mock `(read, write, _)` tuple immediately
  - Monkeypatches `the_one.mcp.transports.streamable_http.ClientSession` to a mock that yields immediately on `__aenter__`
  - Calls `connect_streamable_http(source)` (with `_test_http_client_override = None` and `http_client=None` so the production path runs)
  - Asserts `spy.captured_http_client.headers["authorization"] == "Bearer test-token"` (httpx normalizes header keys to lowercase) — proving production-path header injection
  - This is the verifiable replacement for what test #2 cannot assert in the test-seam path
- [ ] **Test seam invariant**: `_test_http_client_override` is a module-level attribute initialized to `None`; the only writers are `monkeypatch.setattr` calls in test code. Production code paths in `connect_streamable_http` read it ONLY when `http_client is None`. **Documented in the module docstring with a "TEST-ONLY" tag** so future maintainers don't add production code that reads or writes it
- [ ] `make lint` exits 0 (in-container) — no NEW ruff errors. Pay attention to: `F401` (unused import — the test seam may need `# noqa` if ruff flags httpx-related typing-only imports), and `N816` if applicable
- [ ] `make test` (in-container) — exactly **1127 passing + 1 skipped** (1119 post-L3 baseline + 4 TestBuildRequestHeaders unit + 1 production-path-spy unit + 3 TestL4StreamableHttp integration). The 1 skipped count is the SAME pre-existing skipped test from baseline; L4 introduces no new skips
- [ ] `__all__ = ["build_request_headers", "connect_streamable_http"]` declared at the streamable_http module top so `_test_http_client_override` is excluded from `from ... import *` (defense-in-depth on top of the underscore prefix)

## Verification Steps

```bash
# In container
cd /home/cprch/projects/the-one

# Module imports cleanly, helper signatures correct
docker compose exec the-one python -c "
from the_one.mcp.transports.streamable_http import build_request_headers, connect_streamable_http, _test_http_client_override
print('build_request_headers:', build_request_headers)
print('connect_streamable_http:', connect_streamable_http)
print('_test_http_client_override:', _test_http_client_override)
"

# Unit tests in isolation
docker compose exec the-one make test ARGS='-k TestBuildRequestHeaders -v'

# Integration tests in isolation
docker compose exec the-one make test ARGS='-k TestL4StreamableHttp -v'

# Full suite
docker compose exec the-one make test
docker compose exec the-one make lint
```

## Implementation Guidance

1. **SDK shape — confirmed at L4 design review**: `streamable_http_client(url, *, http_client=None, terminate_on_close=True)` does NOT accept a `headers=` kwarg. When `http_client is None`, the SDK calls `create_mcp_http_client()` (no header support). So **L4 builds the httpx client itself** for the production path, applying assembled headers at construction time. For the test path, L4 mutates the ASGI client's `headers` dict before yielding to the SDK — the L3 fixture's per-test fresh client makes this isolation-safe.

   Production-path httpx defaults: `httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=httpx.Timeout(30.0))`. These mirror `mcp.shared._httpx_utils.create_mcp_http_client`'s SDK defaults but avoid importing the private `_httpx_utils` module directly.

2. **Implement `the_one/mcp/transports/streamable_http.py`** — replace the placeholder with the full implementation:

   ```python
   """Streamable-HTTP transport for MCPClient.

   Implements the wire-shape glue between F1's MCPSource model and the
   official mcp SDK's streamable_http_client. The transport itself is a
   single async-context-manager (`connect_streamable_http`) that yields a
   fully-entered `ClientSession`; MCPClient only sees the session, never
   the (read, write) stream tuple.

   Headers are assembled from the operator's kv-table at request time:
   non-sensitive rows live in `source.config.headers` (plaintext at rest);
   sensitive rows in `source.secrets` (Fernet-encrypted at rest). The two
   are flat-merged with secrets winning on collision. Static-bearer auth
   emerges from the kv-table — the operator types
   `Authorization | Bearer xxx | sensitive=true` as one row.

   See flight 02 design decision §11 for the env-var-assembly precedent
   that this helper mirrors structurally.
   """

   from __future__ import annotations

   from contextlib import asynccontextmanager
   from typing import AsyncIterator

   import httpx
   from mcp import ClientSession
   from mcp.client.streamable_http import streamable_http_client

   from the_one.db.models import MCPSource


   __all__ = ["build_request_headers", "connect_streamable_http"]


   # TEST-ONLY seam — integration test fixtures monkeypatch this to inject
   # an ASGI-transport httpx.AsyncClient so tests can run against the
   # in-process FastMCP fixture (no real network). Production code paths
   # NEVER read or write this attribute outside `connect_streamable_http`.
   # Excluded from `__all__` AND underscore-prefixed; do not promote.
   _test_http_client_override: httpx.AsyncClient | None = None


   def build_request_headers(source: MCPSource) -> dict[str, str]:
       """Materialize the HTTP request headers for a streamable-http MCP source.

       Flat-merge of source.config.get("headers", {}) and source.secrets, with
       secrets winning on collision. Mirrors the env-var-assembly pattern
       in transports/stdio.py (L5).

       Trusts F1's API validator to have gated the shape — does not re-validate.
       """
       config_headers: dict[str, str] = source.config.get("headers", {}) or {}
       return {**config_headers, **source.secrets}


   @asynccontextmanager
   async def connect_streamable_http(
       source: MCPSource,
       *,
       http_client: httpx.AsyncClient | None = None,
   ) -> AsyncIterator[ClientSession]:
       """Open an entered ClientSession over streamable-http transport.

       Yields a fully-entered ClientSession (initialize() NOT called — the
       caller — typically MCPClient.connect — runs the handshake). The
       session, transport, and (production-path-only) owned httpx client
       close in correct LIFO order on context exit.

       Headers from build_request_headers(source) are applied to the
       outgoing requests:
         - Production path (effective_client is None): the helper builds
           an httpx.AsyncClient with headers set at construction.
         - Test path (effective_client is not None — typically the L3
           ASGI fixture's client via the _test_http_client_override seam):
           the helper mutates effective_client.headers via dict.update()
           before yielding. The L3 fixture is per-test fresh so the
           mutation does not pollute later tests.
       """
       url: str = source.config["url"]
       headers = build_request_headers(source)

       # Test-injected client takes precedence ONLY when caller-supplied
       # http_client is None. F4 warm-pool callers (when they land) will
       # pass an explicit client and bypass the seam.
       effective_client = http_client
       if effective_client is None:
           effective_client = _test_http_client_override

       if effective_client is not None:
           # Test path: apply headers to the seam-injected client.
           effective_client.headers.update(headers)
           async with streamable_http_client(
               url, http_client=effective_client
           ) as (read, write, _get_session_id):
               async with ClientSession(read, write) as session:
                   yield session
       else:
           # Production path: own the httpx lifecycle so headers + defaults
           # are applied at client-construction time. Defaults mirror the
           # SDK's create_mcp_http_client without depending on the private
           # mcp.shared._httpx_utils module.
           async with httpx.AsyncClient(
               headers=headers,
               follow_redirects=True,
               timeout=httpx.Timeout(30.0),
           ) as owned_client:
               async with streamable_http_client(
                   url, http_client=owned_client
               ) as (read, write, _get_session_id):
                   async with ClientSession(read, write) as session:
                       yield session
   ```

3. **Update `the_one/mcp/client.py::_transport_connect`** — replace the streamable-http NotImplementedError branch:

   ```python
   if source.type == "streamable-http":
       from the_one.mcp.transports.streamable_http import connect_streamable_http
       async with connect_streamable_http(source) as session:
           yield session
   elif source.type == "stdio":
       # L5 implements
       raise NotImplementedError("transport 'stdio' not implemented; L5 lands it")
   else:
       raise MCPClientError(f"unknown MCP transport type: {source.type!r}")
   ```

   No `return` after `yield` — `if/elif/else` already handles dispatch isolation. The `yield` resumes after the inner `async with` exits, then the function returns naturally. (L4 review confirmed via test that with-or-without-`return` produces identical observable cm behavior; cleaner without.)

4. **Add `TestBuildRequestHeaders` to `tests/test_mcp_client.py`** — 4 pure-Python tests:

   ```python
   from the_one.db.models import MCPSource
   from the_one.mcp.transports.streamable_http import build_request_headers


   def _http_source(
       id_: str = "src-1",
       *,
       headers: dict[str, str] | None = None,
       secrets: dict[str, str] | None = None,
   ) -> MCPSource:
       config: dict[str, object] = {"url": "http://localhost/mcp"}
       if headers is not None:
           config["headers"] = headers
       return MCPSource(
           id=id_,
           name="t",
           type="streamable-http",
           config=config,
           secrets=secrets or {},
       )


   class TestBuildRequestHeaders:
       def test_empty(self) -> None:
           assert build_request_headers(_http_source()) == {}

       def test_sensitive_only(self) -> None:
           src = _http_source(secrets={"Authorization": "Bearer x"})
           assert build_request_headers(src) == {"Authorization": "Bearer x"}

       def test_plaintext_only(self) -> None:
           src = _http_source(headers={"X-Trace": "1"})
           assert build_request_headers(src) == {"X-Trace": "1"}

       def test_mixed_secrets_win(self) -> None:
           src = _http_source(
               headers={"Authorization": "PLAIN", "X-Trace": "1"},
               secrets={"Authorization": "Bearer SECRET"},
           )
           assert build_request_headers(src) == {
               "Authorization": "Bearer SECRET",
               "X-Trace": "1",
           }
   ```

5. **Add to `tests/test_mcp_integration.py`'s top-level imports** (alphabetized with the existing `from mcp...` block):

   ```python
   import pytest

   from the_one.db.models import MCPSource
   from the_one.mcp.client import MCPClient
   from the_one.mcp.errors import MCPConnectionError
   ```

   Then add `TestL4StreamableHttp` BELOW the existing `TestL3IntegrationSmoke` class:

   ```python
   class TestL4StreamableHttp:
       async def test_connect_via_mcpclient_against_asgi_fixture(
           self, mcp_fixture_http_client, monkeypatch
       ) -> None:
           client_httpx, url = mcp_fixture_http_client
           monkeypatch.setattr(
               "the_one.mcp.transports.streamable_http._test_http_client_override",
               client_httpx,
           )
           source = MCPSource(
               id="src-1",
               name="hello",
               type="streamable-http",
               config={"url": url, "headers": {}},
               secrets={},
           )
           client = MCPClient(source)
           await client.connect()
           try:
               assert client.is_alive
               assert client.negotiated_protocol_version == "2025-11-25"
               caps = client.server_capabilities
               assert isinstance(caps["tools"], dict)
               assert "listChanged" in caps["tools"]
           finally:
               await client.disconnect()
           assert not client.is_alive

       async def test_connect_with_secrets_does_not_break_connection(
           self, mcp_fixture_http_client, monkeypatch
       ) -> None:
           # NOTE: this test does NOT verify the bearer header reaches the wire
           # — that gap is closed by test_production_path_constructs_client_with_assembled_headers
           # in TestBuildRequestHeaders (Option C unit test). This integration test
           # only proves end-to-end positive completion with secrets present
           # (i.e., the test branch's effective_client.headers.update(headers)
           # mutation doesn't break the in-process ASGI transport).
           client_httpx, url = mcp_fixture_http_client
           monkeypatch.setattr(
               "the_one.mcp.transports.streamable_http._test_http_client_override",
               client_httpx,
           )
           source = MCPSource(
               id="src-2",
               name="hello-with-auth",
               type="streamable-http",
               config={"url": url, "headers": {}},
               secrets={"Authorization": "Bearer test-token"},
           )
           client = MCPClient(source)
           await client.connect()
           try:
               assert client.is_alive
           finally:
               await client.disconnect()

       async def test_connect_already_connected_via_real_transport(
           self, mcp_fixture_http_client, monkeypatch
       ) -> None:
           client_httpx, url = mcp_fixture_http_client
           monkeypatch.setattr(
               "the_one.mcp.transports.streamable_http._test_http_client_override",
               client_httpx,
           )
           source = MCPSource(
               id="src-3",
               name="hello-double-connect",
               type="streamable-http",
               config={"url": url, "headers": {}},
               secrets={},
           )
           client = MCPClient(source)
           await client.connect()
           try:
               with pytest.raises(MCPConnectionError, match="already connected"):
                   await client.connect()
           finally:
               await client.disconnect()
   ```

   `mcp_fixture_http_client` is async function-scoped (per test, fresh FastMCP via the L3 factory) — each test gets its own server instance, so the `StreamableHTTPSessionManager.run()` once-per-instance constraint is honored. Each test also gets a fresh `httpx.AsyncClient`, so the test-path `effective_client.headers.update(headers)` mutation does NOT pollute later tests.

6. **Add Option-C unit test to `tests/test_mcp_client.py`** in `TestBuildRequestHeaders` (or a dedicated `TestConnectStreamableHttpProduction` class — whichever reads cleaner; recommend the latter for explicit naming). The test verifies the production path's header injection without depending on the SDK or fixture:

   ```python
   class TestConnectStreamableHttpProduction:
       """Verifies the production path of connect_streamable_http: when neither
       the caller nor the test seam supplies an http_client, the helper builds
       its own httpx.AsyncClient with the assembled headers applied at
       construction time. Closes the gap that integration test #2 cannot
       assert (the test seam path uses a mutation pattern, not a constructor)."""

       async def test_production_path_constructs_client_with_assembled_headers(
           self, monkeypatch
       ) -> None:
           from contextlib import asynccontextmanager
           from unittest.mock import AsyncMock, MagicMock
           import httpx

           from the_one.db.models import MCPSource
           from the_one.mcp.transports import streamable_http as sh

           # Capture the http_client argument the SDK receives.
           captured: dict[str, httpx.AsyncClient] = {}

           @asynccontextmanager
           async def fake_streamable_http_client(url, *, http_client, **kwargs):
               captured["http_client"] = http_client
               # Yield mock streams; ClientSession will be mocked too.
               yield (MagicMock(), MagicMock(), lambda: None)

           class FakeClientSession:
               def __init__(self, *args, **kwargs):
                   pass
               async def __aenter__(self):
                   return self
               async def __aexit__(self, *args):
                   return None

           monkeypatch.setattr(sh, "streamable_http_client", fake_streamable_http_client)
           monkeypatch.setattr(sh, "ClientSession", FakeClientSession)
           monkeypatch.setattr(sh, "_test_http_client_override", None)  # force production path

           source = MCPSource(
               id="src-prod",
               name="prod",
               type="streamable-http",
               config={"url": "http://example.com/mcp", "headers": {}},
               secrets={"Authorization": "Bearer test-token"},
           )

           async with sh.connect_streamable_http(source):
               # Inside the cm, the spy has already captured the http_client.
               pass

           assert "http_client" in captured
           # httpx normalizes header keys to lowercase
           assert captured["http_client"].headers.get("authorization") == "Bearer test-token"
   ```

   Notes for the implementer:
   - The test uses `monkeypatch` to install the fakes BEFORE entering the cm; `monkeypatch.setattr` auto-reverts on test teardown
   - `_test_http_client_override` is force-set to `None` to ensure the production branch runs even if a prior test left the seam set (defense-in-depth — pytest's monkeypatch isolation should handle this, but the explicit assertion documents intent)
   - `httpx` lowercases header keys; the assertion uses `"authorization"` not `"Authorization"`
   - This test counts as 1 unit test, bringing L4's total to 4 + 1 = 5 unit tests. Combined with 3 integration tests = 8 new tests for L4. Final count: 1119 + 8 = **1127 passing**

7. **Run the in-container test cycle** — verify each of the 8 new tests in isolation, then full suite:

   ```bash
   docker compose exec the-one make test ARGS='-k TestBuildRequestHeaders -v'  # 4 pass
   docker compose exec the-one make test ARGS='-k TestConnectStreamableHttpProduction -v'  # 1 pass
   docker compose exec the-one make test ARGS='-k TestL4StreamableHttp -v'  # 3 pass
   docker compose exec the-one make test  # 1127 passed + 1 skipped
   docker compose exec the-one make lint  # clean
   ```

8. **Update flight log L4 entry** in `## Leg Progress / ### L4: Streamable-HTTP transport` covering: status (landed); changes (transport module body with production-vs-test-path branching, `__all__` declaration, dispatch wiring, test seam); notes (Option-C unit test pattern adopted; production-path defaults `follow_redirects=True, timeout=30s`); test count before/after (1119 → 1127); lint status.

## Edge Cases

- **`source.config.get("headers", {}) or {}`** — defensive against `headers: None` (Pydantic doesn't auto-coerce; F1 validator should reject but defense-in-depth handles a future schema drift).

- **`streamable_http_client` import-time cost**: importing `mcp.client.streamable_http` pulls in `httpx`, `httpx-sse`, `anyio` — all already-direct deps of mcp 1.27.0, so no NEW import-graph load. The module-top `from mcp.client.streamable_http import streamable_http_client` is fine.

- **`httpx.AsyncClient` lifecycle when production path builds it**: the production-path nested `async with httpx.AsyncClient(...) as owned_client:` ensures cleanup. The test-path `effective_client = _test_http_client_override` does NOT close the client (caller owns it) — the test fixture's teardown closes it. Critical: do NOT add `await effective_client.aclose()` in the test branch — would break the L3 fixture's teardown.

- **`_test_http_client_override` as a global mutable**: in pytest, `monkeypatch.setattr` is per-test isolated (auto-restored on test exit). Tests that don't set the override see `None` → production path builds its own httpx client → tries a real network connection → fails (no server at `http://localhost/mcp`). Acceptable; tests that exercise streamable-http MUST use the seam.

- **`server_capabilities["tools"]` shape**: L2's `server_capabilities` property returns `model_dump(mode='json')`. For FastMCP's announced capabilities, this includes `{"tools": {"listChanged": False, ...}}`. The test asserts `"tools" in caps` (key presence), not deep equality — which is robust against SDK minor-version shifts in optional sub-fields.

- **Test seam pollution between tests**: `monkeypatch.setattr` auto-reverts on teardown. If `connect_streamable_http` is somehow called outside a test path (e.g., in `tests/conftest.py`'s fixture body) without the seam set, it falls through to the production path. None of L4's code paths do this; just be aware.

- **The `httpx.AsyncClient` headers `Mapping` vs `Iterable` shape**: `httpx.AsyncClient(headers={"Authorization": "Bearer x"})` is the documented form. The dict from `build_request_headers` works directly.

- **`url = source.config["url"]` may include a path**: e.g., `"http://localhost/mcp"`. The SDK's `streamable_http_client` parses the URL and routes to `/mcp` correctly. Tested by L3's smoke test.

- **`monkeypatch` on a module-level attribute requires the attribute to EXIST in the module**: if `_test_http_client_override` is omitted at module load, `monkeypatch.setattr("the_one.mcp.transports.streamable_http._test_http_client_override", ...)` fails with `AttributeError`. The module MUST initialize the attribute to `None` at module level. Verified by acceptance criterion.

- **Future F4 warm-pool compatibility**: F4 will hold MCPClient instances across multiple tool calls. Each MCPClient owns its own `_transport_cm` (the `_transport_connect` cm). Per-instance lifecycle. The `connect_streamable_http` helper is stateless (only reads its arguments + the test seam). F4-pool-safe.

- **`_get_session_id` ignored**: the SDK yields a 3-tuple from `streamable_http_client`. The third element is a callable returning the session ID (for resumption / debugging). F2 doesn't need it; we discard with `_get_session_id`. F7's inspector might want it later — but adding it to MCPClient's surface is F7's concern.

## Files Affected

- `the_one/mcp/transports/streamable_http.py` — replace L1 placeholder with the full implementation (production-vs-test-path branching, `__all__`, test seam, helpers)
- `the_one/mcp/client.py` — update `_transport_connect`'s streamable-http branch (~5 lines changed; no `return` after yield)
- `tests/test_mcp_client.py` — extend with `TestBuildRequestHeaders` (4 unit tests + helper) AND `TestConnectStreamableHttpProduction` (1 unit test using mocked SDK)
- `tests/test_mcp_integration.py` — extend top-level imports + add `TestL4StreamableHttp` (3 integration tests using `mcp_fixture_http_client`)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — exactly 1127 passing + 1 skipped (1119 baseline post-L3 + 4 TestBuildRequestHeaders + 1 TestConnectStreamableHttpProduction + 3 TestL4StreamableHttp)
- [ ] `make lint` clean (no NEW ruff errors) — run inside the container
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress / ### L4: Streamable-HTTP transport`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end

## Citation Audit

5 SDK + repo citations verified at leg-design time:

1. `the_one/mcp/client.py::_transport_connect` — verified L2 dispatch shape (lines 47-71); the streamable-http branch at lines 60-63 raises `NotImplementedError("transport 'streamable-http' not implemented; L4 lands it")`. L4 replaces this branch
2. `the_one/mcp/transports/streamable_http.py` — verified L1 placeholder shape (docstring only, no code); L4 replaces the entire body
3. `mcp.client.streamable_http.streamable_http_client(url, *, http_client=None, terminate_on_close=True)` — verified signature in container at design time. Returns 3-tuple `(read, write, get_session_id)`. **Headers-injection mechanism (Case A vs Case B in Implementation Guidance step 1) requires runtime confirmation by the implementer** — the leg accommodates both
4. `tests/conftest.py::mcp_fixture_http_client` — verified L3-shipped fixture yields `(client: httpx.AsyncClient, url: str)` with ASGI transport + driven lifespan
5. `the_one/db/models.py::MCPSource` — verified Pydantic model with `id: str` (required), `type: Literal["stdio", "streamable-http"]`, `config: dict[str, Any]`, `secrets: dict[str, Any]`

All citations clean — no drift.

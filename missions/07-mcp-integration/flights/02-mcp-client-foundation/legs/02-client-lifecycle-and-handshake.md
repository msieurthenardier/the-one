# Leg: 02-client-lifecycle-and-handshake

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Implement `MCPClient`'s lifecycle methods (`__init__`, `connect`, `disconnect`, `__aenter__`, `__aexit__`, `__repr__`) plus the version handshake and capability negotiation paths — all behind a mocked `ClientSession` (no real transport in this leg). L4 wires streamable-http transport dispatch; L5 wires stdio transport dispatch; this leg defines the transport-agnostic `MCPClient` skeleton with a single dispatch seam ready for L4/L5 to fill in.

## Context

- **Design Decisions** (flight spec): §2 API surface; §3 error hierarchy (specifically the SDK `RuntimeError → MCPVersionMismatch` translation); §6 `_PINNED_PROTOCOL_VERSION` read-at-call-time invariant; §8 timeout split (handshake vs call_tool); §9 F4-pool compat invariants (`is_alive`/`last_activity`/idempotent disconnect/picklable-free); §10 fail-hard version policy
- **L1 outputs already in place**: `_PINNED_PROTOCOL_VERSION = "2025-11-25"`, `MCP_DEFAULT_TIMEOUT_SECONDS = 30`, `MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60`, full `MCPClientError` hierarchy, frozen `MCPTool`/`MCPToolResult` dataclasses, `class MCPClient: """L2 implements"""` placeholder
- **No real transport in this leg**: `connect()` dispatches on `source.type` to a transport-module function — but L2 makes that dispatch raise `NotImplementedError("L4 implements streamable-http")` / `("L5 implements stdio")`. Tests inject mocks of the dispatch boundary OR mock `mcp.ClientSession` directly to exercise everything from `session.initialize()` onward
- **L2 test plumbing pattern**: monkeypatch the transport-dispatch helper to return a `(read_stream, write_stream)` pair pointing at an `unittest.mock.AsyncMock`-backed `ClientSession`. The `ClientSession.__aenter__` / `initialize` / `list_tools` / `call_tool` / `__aexit__` get mocked at their import boundary so the lifecycle is exercised without any actual SDK plumbing. L6a will replace the call-tool/list-tools mocks with real round-trips against the L3 fixture; L4/L5 will replace the transport-dispatch mock with real stdio_client/streamable_http_client paths

## Inputs

What exists before this leg runs:
- L1 output: `the_one/mcp/{__init__,errors,types,client,transports/{__init__,stdio,streamable_http}}.py` skeleton with constants, error hierarchy, dataclasses, and placeholder `class MCPClient: """L2 implements"""`
- `the_one/db/models.py:MCPSource` — Pydantic model with `type: Literal["stdio", "streamable-http"]`, `config: dict`, `secrets: dict`, plus `merged_config()` (NOT used by F2)
- `the_one/db/repositories.py:MCPSourceRepository` returning fully-decrypted `MCPSource` instances (for tests; production path is L4/L5 transport plumbing)
- `tests/test_mcp_client.py::TestModuleSetup` (3 tests; L1 added)
- `mcp.ClientSession`, `mcp.types.LATEST_PROTOCOL_VERSIONS`, `mcp.shared.version.SUPPORTED_PROTOCOL_VERSIONS`, `mcp.shared.exceptions.McpError` — all importable from the pinned `mcp==1.27.0` SDK

## Outputs

What exists after this leg completes:
- `the_one/mcp/client.py` — full `MCPClient` class implementing the lifecycle described in flight §2 (constructor, connect, disconnect, async context manager protocol, `__repr__`, `is_alive`, `last_activity`, `negotiated_protocol_version`, `server_capabilities`)
- A private `_transport_connect(source)` dispatch helper inside `client.py` (or a sibling `_dispatch.py`) that raises `NotImplementedError` with a clear "L4/L5 implements" message. Tests bypass this via `monkeypatch.setattr` on the helper
- `tests/test_mcp_client.py::TestMCPClientLifecycle` — ~10 unit tests covering: state machine (uninitialized → connecting → alive → disconnected), version handshake (exact match passes; the SDK's own `RuntimeError` from `session.initialize` is caught and re-raised as `MCPVersionMismatch`; an in-`SUPPORTED_PROTOCOL_VERSIONS`-but-not-pinned mismatch raises `MCPVersionMismatch` from F2's stricter check), capability negotiation (`tools` capability present passes; `tools` missing raises `MCPCapabilityMissing("tools")`), double-disconnect-idempotency (no-op), `last_activity` updates via mocked-session `list_tools` call (real `list_tools` is L6a; L2's test stubs the method to assert the property updates), `is_alive` state transitions, `__repr__` format pinned by snapshot, `negotiated_protocol_version` and `server_capabilities` raise before connect / populate after
- Pre-leg lint baseline: 0 NEW ruff errors

## Acceptance Criteria

- [ ] `MCPClient.__init__(source, *, timeout_seconds=MCP_DEFAULT_TIMEOUT_SECONDS, call_timeout_seconds=MCP_DEFAULT_CALL_TIMEOUT_SECONDS)` accepts an `MCPSource` and stores it; the two timeouts are stored on the instance; `is_alive` is `False`; `last_activity` is **exactly `0.0`** (a sentinel — `time.monotonic()` never returns 0 on a running system, so any post-touch comparison `last_activity > 0.0` is meaningful; `None` is rejected because `__repr__`'s `f"{x:.2f}"` would crash on it)
- [ ] `MCPClient.connect()` (transport-agnostic part):
  - Dispatches on `self.source.type` via `_transport_connect(self.source)` (the helper L4/L5 will fill in; L2 leaves it raising `NotImplementedError(f"transport {type!r} not implemented; L4 lands streamable-http, L5 lands stdio")`)
  - Wraps the SDK's `ClientSession` startup + `session.initialize()` in `asyncio.timeout(self.timeout_seconds)` — on timeout, `MCPConnectionError("MCP server did not respond within {N} seconds during initialize.")` raises
  - Catches `RuntimeError` raised by SDK's `session.initialize()` (the `Unsupported protocol version from the server: ...` path; SDK source: `mcp/client/session.py::initialize` raises this when `result.protocolVersion not in SUPPORTED_PROTOCOL_VERSIONS`) and re-raises as `MCPVersionMismatch(pinned=the_one.mcp._PINNED_PROTOCOL_VERSION, observed=<extracted from the RuntimeError message>)`
  - After `initialize()` returns, asserts `result.protocolVersion == the_one.mcp._PINNED_PROTOCOL_VERSION` exactly — raises `MCPVersionMismatch(pinned, observed)` if not
  - Asserts `result.capabilities.tools is not None` — raises `MCPCapabilityMissing("tools")` if absent
  - Stores `self._session = session`, `self._capabilities = result.capabilities` (raw `mcp.types.ServerCapabilities`), `self._protocol_version = result.protocolVersion`
  - Sets `self._is_alive = True`, `self._last_activity = time.monotonic()` **only after all version + capability checks pass** (ordering invariant: any path that raises during connect() must leave `is_alive=False` so `test_connect_*_mismatch` and `test_connect_capability_tools_missing` see the failed state correctly)
  - Subsequent `connect()` calls when already alive raise `MCPConnectionError("MCPClient is already connected.")` — F4's pool will manage this externally
- [ ] `MCPClient.disconnect()`:
  - Idempotent: when already disconnected, returns immediately (no exception, no log line at WARN — DEBUG only is fine)
  - Closes the session and transport context managers in reverse-acquisition order
  - Sets `self._is_alive = False` BEFORE awaiting any close coroutines (so `is_alive` is correct from any concurrent reader the moment disconnect begins, per flight §9)
  - On any close-time exception, swallows and continues (logs at WARN only) — disconnect is a teardown path that must not raise per the F4-pool idempotency contract
- [ ] `MCPClient.__aenter__` / `__aexit__`: standard async context manager wrapping `connect()` / `disconnect()`. `__aexit__` always calls `disconnect()` regardless of whether an exception is in flight, then **returns `None`** so any in-flight exception propagates naturally per Python's `async with` protocol (i.e., the wrapper does NOT suppress exceptions)
- [ ] `MCPClient.__repr__()` returns a fixed-shape string: `f"MCPClient(name={self.source.name!r}, type={self.source.type!r}, is_alive={self._is_alive}, last_activity={self._last_activity:.2f})"` — pinned exactly by a snapshot test so future drift is caught
- [ ] `MCPClient.is_alive` (property, read-only) returns `self._is_alive` (False until `connect()` returns successfully; True thereafter; False from the moment `disconnect()` begins)
- [ ] `MCPClient.last_activity` (property, read-only) returns `self._last_activity` (`time.monotonic()` updated on every successful `list_tools()` and `call_tool()` call — real implementations land in L6a; L2 includes a private `_touch_activity()` helper and exercises it from a stub `_test_only_touch()` method via tests OR via mocked-list-tools)
- [ ] `MCPClient.negotiated_protocol_version` (property): when `is_alive=False`, raises `MCPConnectionError("MCPClient is not connected; cannot read negotiated_protocol_version.")`. When alive, returns the post-handshake protocolVersion string
- [ ] `MCPClient.server_capabilities` (property): same not-connected guard as `negotiated_protocol_version`. When alive, returns a `dict[str, Any]` constructed via `self._capabilities.model_dump(mode='json')` (not the raw Pydantic object — F4/F6/F7 should not depend on the SDK's internal Pydantic types)
- [ ] `_PINNED_PROTOCOL_VERSION` is read at call-time via `the_one.mcp._PINNED_PROTOCOL_VERSION` (NOT imported by name) so `monkeypatch.setattr("the_one.mcp._PINNED_PROTOCOL_VERSION", "2099-01-01")` works in tests
- [ ] No SDK imports happen at module-load time of `the_one/mcp/client.py`. SDK imports (`from mcp import ClientSession`; `from mcp.shared.exceptions import McpError`) are inside `connect()` or sibling private methods; tests can `monkeypatch.setattr` on `the_one.mcp.client.<ImportedName>` to inject mocks
- [ ] **`tests/test_mcp_client.py::TestMCPClientLifecycle`** with ~10 tests (exact list, not a guideline):
  1. `test_init_state` — fresh MCPClient: `is_alive is False`, `last_activity == 0.0` (exact equality), `negotiated_protocol_version` raises `MCPConnectionError`, `server_capabilities` raises `MCPConnectionError`
  2. `test_connect_happy_path` — mocked `ClientSession` with `initialize()` returning `protocolVersion="2025-11-25"` and `capabilities.tools = {}`; after `await client.connect()`, `is_alive=True`, `last_activity > 0`, `negotiated_protocol_version == "2025-11-25"`, `server_capabilities` returns dict
  3. `test_connect_version_mismatch_strict` — mocked `initialize()` returns `protocolVersion="2025-06-18"` (in `SUPPORTED_PROTOCOL_VERSIONS` but not pinned); `MCPVersionMismatch` raises; `is_alive` stays False
  4. `test_connect_version_mismatch_via_sdk_runtime_error` — mocked `initialize()` raises `RuntimeError("Unsupported protocol version from the server: 1999-01-01")`; F2 catches and re-raises as `MCPVersionMismatch(pinned="2025-11-25", observed="1999-01-01")`; `is_alive` stays False
  5. `test_connect_capability_tools_missing` — mocked `initialize()` returns valid version but `capabilities.tools = None`; `MCPCapabilityMissing("tools")` raises; `is_alive` stays False
  6. `test_connect_already_connected_raises` — call `connect()` twice; second call raises `MCPConnectionError("...already connected.")`
  7. `test_connect_timeout` — mocked `initialize()` blocks forever; `MCPClient(source, timeout_seconds=0.05).connect()` raises `MCPConnectionError("...did not respond within 0.05 seconds during initialize.")`; `is_alive` stays False (note: `timeout_seconds` is an `__init__` kwarg per flight §2, NOT a `connect()` kwarg)
  8. `test_disconnect_idempotent` — call `disconnect()` on never-connected MCPClient (no exception); call `connect() → disconnect() → disconnect()` (second disconnect is no-op)
  9. `test_disconnect_swallows_close_errors` — mocked session `__aexit__` raises; disconnect completes without raising; `is_alive` is False
  10. `test_aenter_aexit` — `async with MCPClient(source) as c:` wraps connect/disconnect; on exception inside the `with` body, `disconnect()` is still called and original exception propagates
  11. `test_repr_format` — connected client `repr(c)` matches `r"^MCPClient\(name='.+', type='(stdio|streamable-http)', is_alive=(True|False), last_activity=\d+\.\d{2}\)$"`
  12. `test_pinned_constant_read_at_call_time` — monkeypatch `the_one.mcp._PINNED_PROTOCOL_VERSION` to `"2099-01-01"`; mocked `initialize()` returns any string ≠ `"2099-01-01"` (e.g. `"2025-11-25"`); `connect()` raises `MCPVersionMismatch(pinned="2099-01-01", observed="2025-11-25")`. Note: because `session.initialize` is mocked outright, the SDK's own `SUPPORTED_PROTOCOL_VERSIONS` check never runs — F2's strict-equality check is the only gate that fires. The test proves the constant is read at call time (otherwise the monkeypatch wouldn't propagate)
  13. `test_last_activity_updates_via_list_tools` — mocked session's `list_tools()` returns an empty `ListToolsResult`; before call, `last_activity = T0`; after `await client.list_tools()`, `last_activity > T0`. (NOTE: the actual `list_tools` body is L6a; L2 stubs it as a method that calls `self._touch_activity()` then delegates to a `NotImplementedError("L6a implements")` — the `last_activity` update happens BEFORE the NotImplementedError per the spec; the test asserts `last_activity > T0` AND that NotImplementedError is raised)
  
  L2's `list_tools` and `call_tool` stubs MUST call `self._touch_activity()` before raising `NotImplementedError(...)` so the L4/L5 integration tests don't have to re-test the activity-touching pattern at every leg

- [ ] `make lint` exits 0 — no NEW ruff errors introduced (note: `select = ["E","F","I","N","W"]` per pyproject.toml flags F841 on unused locals — disconnect() must not assign and discard)
- [ ] `make test` exits 0 — **exactly 1117 passing + 1 skipped** (1104 baseline + 13 new TestMCPClientLifecycle tests numbered 1-13 in this leg)

## Verification Steps

```bash
# Module imports clean (no SDK at module-load time)
python -c "
import the_one.mcp.client as cmod
import sys
# SDK should NOT yet be loaded just from importing client module
assert 'mcp.client.session' not in sys.modules, 'SDK loaded at module-load — must be deferred'
print('client.py imports SDK lazily: OK')
"

# Targeted test runs
cd ~/projects/the-one
make test ARGS='-k test_init_state'
make test ARGS='-k test_connect_happy_path'
make test ARGS='-k test_connect_version_mismatch'
make test ARGS='-k test_connect_capability_tools_missing'
make test ARGS='-k test_connect_already_connected_raises'
make test ARGS='-k test_connect_timeout'
make test ARGS='-k test_disconnect_idempotent'
make test ARGS='-k test_disconnect_swallows_close_errors'
make test ARGS='-k test_aenter_aexit'
make test ARGS='-k test_repr_format'
make test ARGS='-k test_pinned_constant_read_at_call_time'
make test ARGS='-k test_last_activity_updates_via_list_tools'

# Full suite
make test
make lint

# Smoke check: state machine in a REPL
python -c "
import asyncio
from the_one.db.models import MCPSource
from the_one.mcp.client import MCPClient

src = MCPSource(id='src-1', name='test', type='stdio', config={'command':'echo','args':[]}, secrets={})
c = MCPClient(src)
print('init:', c.is_alive, c.last_activity)
try:
    c.negotiated_protocol_version
except Exception as e:
    print('expected MCPConnectionError:', e)
try:
    asyncio.run(c.connect())
except Exception as e:
    print('expected NotImplementedError or MCPConnectionError:', type(e).__name__, e)
"
```

## Implementation Guidance

1. **Read the SDK's `ClientSession.initialize()` source** (`mcp/client/session.py::initialize` in the installed SDK) to confirm the `RuntimeError("Unsupported protocol version from the server: <observed>")` message format. Extract the `<observed>` substring with a single-line regex (don't over-parse: `m = re.match(r"Unsupported protocol version from the server: (.+)", str(e))`; if regex doesn't match, fall back to including the raw `str(e)` in the `MCPVersionMismatch.observed` argument).

2. **Decide single-helper vs sibling `_dispatch.py`.** Recommend keeping `_transport_connect(source)` as a private function in `client.py` (top-level, not a method) so tests can do `monkeypatch.setattr("the_one.mcp.client._transport_connect", mock_fn)`. The function is decorated with `@asynccontextmanager` and yields a **fully-entered, not-yet-initialized `ClientSession`**. L4/L5's body shape:

   ```python
   @asynccontextmanager
   async def _transport_connect(source: MCPSource) -> AsyncIterator["ClientSession"]:
       if source.type == "streamable-http":
           # L4 implements:
           async with streamable_http_client(url, http_client=...) as (read, write, _):
               async with ClientSession(read, write) as session:
                   yield session
       elif source.type == "stdio":
           # L5 implements similarly with stdio_client and StdioServerParameters
           ...
   ```

   This way `MCPClient.connect()` only sees a `ClientSession` (no stream-tuple shape leaks across the dispatch boundary). Closing `_transport_cm` cascades the inner `ClientSession.__aexit__` first, then the transport's `__aexit__` — correct LIFO. L4/L5 must nest the `ClientSession` cm inside `_transport_connect`'s body for this cascade to work; do NOT yield the `(read, write)` tuple and let `connect()` build the session — that splits the lifetime across the dispatch seam.

   **Import-cycle note**: every `from the_one import mcp as the_one_mcp` in `client.py` MUST be inside a function body, never at module top — `the_one/mcp/__init__.py` imports `MCPClient` at module-load (L1's re-export pattern), so a top-level reverse-import in `client.py` would create a circular-import error on first load.

3. **MCPClient implementation skeleton** (illustrative — adapt to project conventions):

   ```python
   """MCPClient — async wrapper around mcp==1.27.0 SDK's ClientSession.

   See flight design decisions §2 (API surface), §9 (F4-pool compat invariants).
   """

   from __future__ import annotations

   import asyncio
   import logging
   import re
   import time
   from contextlib import asynccontextmanager
   from typing import Any, AsyncIterator, TYPE_CHECKING

   from the_one.db.models import MCPSource
   from the_one.mcp.errors import (
       MCPCallError,
       MCPCapabilityMissing,
       MCPClientError,
       MCPConnectionError,
       MCPToolNotFoundError,
       MCPVersionMismatch,
   )

   if TYPE_CHECKING:
       from mcp import ClientSession  # type-only; SDK not at module-load
       from mcp.types import ServerCapabilities

   logger = logging.getLogger(__name__)

   _UNSUPPORTED_VERSION_RE = re.compile(
       r"Unsupported protocol version from the server: (.+)"
   )


   @asynccontextmanager
   async def _transport_connect(source: MCPSource) -> AsyncIterator["ClientSession"]:
       """Dispatch on source.type to the correct transport. L4/L5 fill in.

       Yields a connected ClientSession (entered, but not yet initialized).
       Caller is responsible for calling session.initialize() and final cleanup.
       """
       if source.type == "streamable-http":
           raise NotImplementedError(
               "transport 'streamable-http' not implemented; L4 lands it"
           )
       elif source.type == "stdio":
           raise NotImplementedError(
               "transport 'stdio' not implemented; L5 lands it"
           )
       else:
           # Defensive exhaustiveness — Pydantic Literal gates the type at model
           # validation time, so this branch is unreachable. Locks the contract
           # that any future transport literal must extend this dispatch.
           raise MCPClientError(f"unknown MCP transport type: {source.type!r}")
           # Mirror F1's defensive `else: raise` exhaustiveness pattern.


   class MCPClient:
       def __init__(
           self,
           source: MCPSource,
           *,
           timeout_seconds: int | float = ...,  # MCP_DEFAULT_TIMEOUT_SECONDS at runtime
           call_timeout_seconds: int | float = ...,
       ) -> None:
           # NOTE: don't import the constants at module load — read at-call by
           # `from the_one import mcp` and accessing the attribute. But for
           # __init__ defaults, importing inside the body is fine because
           # the defaults bind once at instance creation.
           from the_one import mcp as the_one_mcp

           if timeout_seconds is ...:
               timeout_seconds = the_one_mcp.MCP_DEFAULT_TIMEOUT_SECONDS
           if call_timeout_seconds is ...:
               call_timeout_seconds = the_one_mcp.MCP_DEFAULT_CALL_TIMEOUT_SECONDS

           self.source = source
           self.timeout_seconds = timeout_seconds
           self.call_timeout_seconds = call_timeout_seconds

           self._session: "ClientSession" | None = None
           self._capabilities: "ServerCapabilities" | None = None
           self._protocol_version: str | None = None
           self._is_alive: bool = False
           self._last_activity: float = 0.0
           self._transport_cm: Any = None  # holds the _transport_connect cm
           self._session_cm: Any = None    # holds the session async-ctx

       @property
       def is_alive(self) -> bool:
           return self._is_alive

       @property
       def last_activity(self) -> float:
           return self._last_activity

       @property
       def negotiated_protocol_version(self) -> str:
           if not self._is_alive or self._protocol_version is None:
               raise MCPConnectionError(
                   "MCPClient is not connected; cannot read negotiated_protocol_version."
               )
           return self._protocol_version

       @property
       def server_capabilities(self) -> dict[str, Any]:
           if not self._is_alive or self._capabilities is None:
               raise MCPConnectionError(
                   "MCPClient is not connected; cannot read server_capabilities."
               )
           return self._capabilities.model_dump(mode="json")

       def __repr__(self) -> str:
           return (
               f"MCPClient(name={self.source.name!r}, type={self.source.type!r}, "
               f"is_alive={self._is_alive}, last_activity={self._last_activity:.2f})"
           )

       def _touch_activity(self) -> None:
           self._last_activity = time.monotonic()

       async def connect(self) -> None:
           if self._is_alive:
               raise MCPConnectionError("MCPClient is already connected.")

           # Lazy SDK import — keeps test monkeypatch hooks alive
           from the_one import mcp as the_one_mcp

           pinned = the_one_mcp._PINNED_PROTOCOL_VERSION

           try:
               async with asyncio.timeout(self.timeout_seconds):
                   self._transport_cm = _transport_connect(self.source)
                   session = await self._transport_cm.__aenter__()
                   self._session = session
                   try:
                       result = await session.initialize()
                   except RuntimeError as e:
                       m = _UNSUPPORTED_VERSION_RE.match(str(e))
                       observed = m.group(1) if m else str(e)
                       raise MCPVersionMismatch(pinned=pinned, observed=observed) from None
           except asyncio.TimeoutError:
               # Cleanup partial state before re-raising
               await self._cleanup_after_failed_connect()
               raise MCPConnectionError(
                   f"MCP server did not respond within {self.timeout_seconds} "
                   f"seconds during initialize."
               ) from None
           except (MCPClientError, NotImplementedError):
               await self._cleanup_after_failed_connect()
               raise
           except Exception as e:
               await self._cleanup_after_failed_connect()
               raise MCPConnectionError(
                   f"MCP connect failed: {type(e).__name__}: {e}"
               ) from e

           # F2 strict check (narrower than the SDK's SUPPORTED_PROTOCOL_VERSIONS)
           if result.protocolVersion != pinned:
               await self._cleanup_after_failed_connect()
               raise MCPVersionMismatch(pinned=pinned, observed=result.protocolVersion)

           if result.capabilities.tools is None:
               await self._cleanup_after_failed_connect()
               raise MCPCapabilityMissing("tools")

           self._capabilities = result.capabilities
           self._protocol_version = result.protocolVersion
           self._is_alive = True
           self._touch_activity()

       async def _cleanup_after_failed_connect(self) -> None:
           # Best-effort teardown of partial state from a failed connect()
           try:
               if self._transport_cm is not None:
                   await self._transport_cm.__aexit__(None, None, None)
           except Exception:
               logger.debug("transport cleanup raised; suppressing", exc_info=True)
           self._transport_cm = None
           self._session = None

       async def disconnect(self) -> None:
           # Idempotent — flip the flag FIRST so concurrent readers see correct state
           if not self._is_alive and self._transport_cm is None:
               return
           self._is_alive = False
           try:
               if self._transport_cm is not None:
                   await self._transport_cm.__aexit__(None, None, None)
           except Exception:
               logger.warning("MCPClient transport close failed", exc_info=True)
           finally:
               self._transport_cm = None
               self._session = None
               # Preserve _capabilities, _protocol_version, _last_activity for the
               # F4 pool — once disconnected they're stale but not invalid.

       async def __aenter__(self) -> "MCPClient":
           await self.connect()
           return self

       async def __aexit__(self, exc_type, exc, tb) -> None:
           await self.disconnect()

       async def list_tools(self) -> list:
           # L6a implements; this stub touches activity (per F2 contract) and
           # raises NotImplementedError so callers know L6a is the next leg.
           self._touch_activity()
           raise NotImplementedError("L6a implements list_tools")

       async def call_tool(self, name: str, arguments: dict) -> Any:
           # L6a (happy path) + L6b (validation/errors) implement.
           self._touch_activity()
           raise NotImplementedError("L6a implements call_tool")
   ```

   The `from __future__ import annotations` plus `TYPE_CHECKING`-guarded SDK imports keep `import the_one.mcp.client` cheap and SDK-decoupled at module-load time.

4. **Test plumbing pattern** — the L2 tests need to inject mocks for `_transport_connect` (so it returns a mock session) and for the session's `initialize()` (so we control the version handshake outcome). Recommended:

   ```python
   from contextlib import asynccontextmanager
   from unittest.mock import AsyncMock, MagicMock
   import pytest

   from the_one.db.models import MCPSource
   from the_one.mcp import client as client_mod
   from the_one.mcp.client import MCPClient
   from the_one.mcp.errors import (
       MCPCapabilityMissing,
       MCPConnectionError,
       MCPVersionMismatch,
   )


   def _stdio_source(name: str = "test", source_id: str = "src-1") -> MCPSource:
       return MCPSource(
           id=source_id,
           name=name,
           type="stdio",
           config={"command": "echo", "args": []},
           secrets={},
       )


   def _make_init_result(
       *,
       protocol_version: str = "2025-11-25",
       tools_capability: object | None = ...,  # sentinel: default present
   ):
       """Build a mock InitializeResult with the configured shape."""
       result = MagicMock()
       result.protocolVersion = protocol_version
       caps = MagicMock()
       caps.tools = MagicMock() if tools_capability is ... else tools_capability
       caps.model_dump = MagicMock(return_value={"tools": {}})
       result.capabilities = caps
       return result


   @asynccontextmanager
   async def _mock_transport_cm(session_mock):
       """Mimics _transport_connect's shape — yields a session, runs cleanup on exit."""
       try:
           yield session_mock
       finally:
           pass


   @pytest.fixture
   def mock_session():
       session = MagicMock()
       session.initialize = AsyncMock(return_value=_make_init_result())
       session.list_tools = AsyncMock()
       session.call_tool = AsyncMock()
       return session


   @pytest.fixture
   def patch_transport(monkeypatch, mock_session):
       def _install(session_or_factory=None):
           sess = session_or_factory if session_or_factory is not None else mock_session
           # Fresh CM per call — asynccontextmanager-produced CMs are single-use,
           # so a connect→disconnect→connect sequence requires per-call instantiation
           monkeypatch.setattr(
               client_mod,
               "_transport_connect",
               lambda source: _mock_transport_cm(sess),
           )
           return sess
       return _install


   class TestMCPClientLifecycle:
       async def test_init_state(self) -> None:
           c = MCPClient(_stdio_source())
           assert c.is_alive is False
           assert c.last_activity == 0.0
           with pytest.raises(MCPConnectionError):
               _ = c.negotiated_protocol_version
           with pytest.raises(MCPConnectionError):
               _ = c.server_capabilities

       async def test_connect_happy_path(self, patch_transport, mock_session) -> None:
           patch_transport(mock_session)
           c = MCPClient(_stdio_source())
           await c.connect()
           assert c.is_alive is True
           assert c.last_activity > 0.0
           assert c.negotiated_protocol_version == "2025-11-25"
           assert c.server_capabilities == {"tools": {}}
           await c.disconnect()
           assert c.is_alive is False

       # ... etc (12 more tests per Acceptance Criteria)
   ```

   Tests must use `pytest.mark.asyncio` (the project already configures `asyncio_mode = "auto"` based on existing `tests/test_db_repositories.py` patterns; verify by checking `pyproject.toml` `[tool.pytest.ini_options]` if a fresh test class isn't auto-async — fall back to explicit `@pytest.mark.asyncio` on each test if needed).

5. **`asyncio.timeout` Python-version note**: `asyncio.timeout()` is Python 3.11+. The project requires Python 3.11+ per `pyproject.toml:requires-python = ">=3.11"` so this is fine. No fallback needed.

6. **`server_capabilities.model_dump(mode='json')` vs raw**: returning a plain dict (not the SDK's Pydantic object) protects downstream consumers from SDK Pydantic-version churn. `model_dump(mode='json')` produces JSON-serializable values (no datetime objects, no Pydantic Url types). The test `test_connect_happy_path` asserts the dict shape, which is stable across SDK minor versions.

7. **`re.match` with literal SDK message string**: brittle in principle (SDK could change the error string in a minor version). Mitigation:
   - L2's `_UNSUPPORTED_VERSION_RE` parses the current SDK 1.27.0 message verbatim
   - Fallback: if regex doesn't match, observed = `str(e)` (entire message) — still produces a usable error for the operator, just less pretty
   - Future SDK upgrade: this regex needs a re-check during the SDK-pin upgrade procedure (already documented in `_PINNED_PROTOCOL_VERSION` docstring upgrade steps)

8. **F4-pool concurrency note**: F4's reaper will read `is_alive` and `last_activity` from a separate task. Python's GIL makes single-attribute reads/writes atomic for these primitives (bool, float). Setting `_is_alive = False` BEFORE awaiting any close coroutines (per the spec) ensures the reaper observes the disconnect-in-progress state correctly without needing an explicit lock. Document this invariant in a comment near `disconnect()`.

9. **Update flight log L2 entry** in `## Leg Progress / ### L2: Client lifecycle and handshake` covering: status (landed), changes made (key implementation choices, esp. the lazy-SDK-import + `_transport_connect` dispatch helper boundary), notes (any deviations from spec, surprises with the SDK shape), test count before/after, lint status.

10. **Per-leg lint gate**: `make lint` exits 0 (no NEW ruff errors). If a stub `list_tools`/`call_tool` triggers a "function does nothing useful" ruff warning, add a `# noqa: ...` with comment explaining "L6a implements". Don't suppress real errors.

## Edge Cases

- **`asyncio.timeout` swallows a sub-task's `MCPVersionMismatch`**: `asyncio.timeout()` cancels the inner task on timeout. If the inner task is mid-handshake when the timeout fires, the `MCPVersionMismatch` raise gets superseded by `asyncio.CancelledError → TimeoutError`. This is fine — the operator sees `MCPConnectionError(timeout)` not `MCPVersionMismatch`. Document the precedence: timeout > version mismatch > capability missing.

- **`_transport_connect` raises `NotImplementedError` from L2's stub**: the `except (MCPClientError, NotImplementedError)` clause catches it cleanly and re-raises after cleanup. This is intentional so that running L2 against a real source (impossible from the API; tests only) gives a clear error pointing at L4/L5.

- **`server_capabilities.tools` is the SDK's `mcp.types.ToolsCapability` object, not a dict**: it has a `listChanged: bool | None` field. F2's `tools is None` check works because Pydantic optional defaults to None when the server doesn't announce. After `model_dump(mode='json')`, callers see `{"tools": {"listChanged": null}}` or similar — this is fine for F4/F6/F7 and matches the spec wire format.

- **`session.initialize()` raises `mcp.shared.exceptions.McpError` instead of `RuntimeError`**: that's a different code path (server-side rejection of our InitializeRequest itself, not version mismatch). L2 catches `Exception` after the `RuntimeError` branch and wraps it as `MCPConnectionError`. The wrapper message includes the McpError details so operators can see what the server complained about.

- **Multiple concurrent `connect()` calls on the same instance**: the spec says second call raises. F4's pool will not call `connect()` twice on the same instance, but defensive guard is one line: `if self._is_alive: raise MCPConnectionError("...already connected.")` AT THE TOP of connect(). Add an `asyncio.Lock` if testing reveals race conditions, but start without it (mission constraint #56 — no clever exception types means no clever locking either).

- **`disconnect()` while `connect()` is in flight**: another concurrent-task scenario. F4 won't trigger this in practice; F2 documents it as undefined behavior in a comment ("disconnect during in-flight connect is not supported; F4's pool serializes acquire/release"). Don't add logic for this in F2.

- **Mock session's `__aenter__` / `__aexit__` not configured**: tests must use the `_mock_transport_cm` async-cm wrapper which doesn't itself need session.__aenter__. The session object is just yielded as-is. If a test wants to assert `__aexit__` was called, it can spy via the same monkeypatch fixture.

- **`time.monotonic()` resolution**: on Linux ≥ 3.6, monotonic clock resolution is well below 1ms. `last_activity` updates inside microseconds of consecutive `_touch_activity()` calls produce monotonically-increasing values. `assert c.last_activity > T0` is safe even for back-to-back calls.

- **`pyproject.toml`'s `[tool.pytest.ini_options]` may not have `asyncio_mode`**: verified at design time — the project uses `pytest-asyncio` and async tests work without explicit `@pytest.mark.asyncio` decorators. If a fresh test class doesn't auto-async, add the decorator explicitly.

- **Verification commands run in the dev container, not host**: per L1 flight log, the host's system Python had `mcp 1.18.0` from prior work; L1's `pip install` ran inside `docker compose build the-one`. L2's verification REPL snippets must run inside the container (`docker compose exec the-one python -c '...'`) or in the project's `.venv` if one exists — the host's stale `mcp` install would mask SDK-shape changes.

## Files Affected

- `the_one/mcp/client.py` — replace L1's placeholder with the full lifecycle implementation
- `tests/test_mcp_client.py` — extend with `TestMCPClientLifecycle` class (~12-13 tests)
- (no changes to `errors.py`, `types.py`, `transports/*.py`, or any non-MCP file)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — 1104 baseline (post-L1) + 12-13 new TestMCPClientLifecycle tests; expect ~1116-1117 passing + 1 skipped
- [ ] `make lint` clean (no NEW ruff errors)
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress / ### L2: Client lifecycle and handshake`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`) — but DO NOT mark flight `landed` (autonomous workflow batches)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end

## Citation Audit

4 SDK-internal citations verified at leg-design time:

1. `mcp.client.session.ClientSession.initialize` (in installed mcp 1.27.0) — verified raises `RuntimeError("Unsupported protocol version from the server: <version>")` when `result.protocolVersion not in SUPPORTED_PROTOCOL_VERSIONS`
2. `mcp.types.InitializeResult` — verified has `protocolVersion: str` and `capabilities: ServerCapabilities` fields
3. `mcp.types.ServerCapabilities` — verified `tools: ToolsCapability | None` field (None when server doesn't announce); other capability fields (`resources`, `prompts`, `sampling`, `experimental`, `logging`, `completions`) also present and follow same Optional pattern
4. `mcp.shared.version.SUPPORTED_PROTOCOL_VERSIONS` — verified value `["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]` at SDK install time (matches flight-design recon)

3 in-repo citations verified at leg-design time:

5. `the_one/db/models.py:MCPSource` — verified `type: Literal["stdio", "streamable-http"]`, `config: dict[str, Any]`, `secrets: dict[str, Any]`, with `merged_config()` helper (NOT used in this leg)
6. `the_one/mcp/__init__.py` — verified L1 exports `_PINNED_PROTOCOL_VERSION = "2025-11-25"`, `MCP_DEFAULT_TIMEOUT_SECONDS = 30`, `MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60` per L1 implementation
7. `the_one/mcp/errors.py` — verified L1 defines all 6 error subclasses + `MCPClientError` base per L1 implementation

All citations clean — no drift.

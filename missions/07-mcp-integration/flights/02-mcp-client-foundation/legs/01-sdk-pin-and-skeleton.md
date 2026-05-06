# Leg: 01-sdk-pin-and-skeleton

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Land the F2 module skeleton: pin `mcp==1.27.0` in `pyproject.toml`, create the `the_one/mcp/` package layout (with constants, error hierarchy, dataclass types, and empty client/transport stubs), extend F1's API validator to cover `config.env` shape, and document all 6 F2 contracts in `CLAUDE.md` and `agents.md`.

## Context

- **Design Decisions** (flight spec): §1 module placement at `the_one/mcp/`; §3 error hierarchy; §5b `MCPTool` dataclass; §4 `MCPToolResult` dataclass; §6 SDK pin + protocol-version constant; §8 timeout constants; §9 F4-pool compat invariants; §11 env-var assembly helper signature; §12 F1 API validation backfill
- **No client logic in this leg** — `client.py` and `transports/*.py` are empty stubs that must import without error. L2 implements `MCPClient`; L4-L5 implement transports
- **F1 backfill**: F1's `_validate_mcp_source_config` validates `command`, `args`, `cwd` for stdio but does NOT validate `config.env`. L1 patches this gap to mirror the existing `headers: dict[str, str]` validation pattern from the streamable-http branch. This is the F2's L1 contract reaffirmation work — the API rejects bad shape; runtime trusts the model
- **Doc updates** are a forward-investment for the rest of the mission: F4 will read the pool-compat invariants; F5 will read the OAuth slot non-dependency note; F6 will read the `MCPTool`/`MCPToolResult` shapes; future maintainers must NOT "fix" the non-consumption of `merged_config()` for stdio

## Inputs

What exists before this leg runs:
- `pyproject.toml` with current dependencies (no `mcp` SDK pin)
- `the_one/` package with no `mcp/` sub-package
- `the_one/interfaces/web/api.py` with `_validate_mcp_source_config` covering `command`/`args`/`cwd` for stdio, `url`/`headers`/`oauth` for streamable-http
- `tests/test_db_api.py::TestMCPSourceAPI` with existing CRUD + masking + transport-type-switch tests
- `CLAUDE.md` and `the_one/agents.md` with F1 contracts documented (field-segregated encryption, per-key `__MASKED__`, OAuth client_secret routing, all-in-memory rotation)

## Outputs

What exists after this leg completes:
- `pyproject.toml` includes `"mcp==1.27.0"` in base `dependencies` (NOT optional, NOT `~=`)
- `the_one/mcp/__init__.py` exporting `_PINNED_PROTOCOL_VERSION = "2025-11-25"`, `MCP_DEFAULT_TIMEOUT_SECONDS = 30`, `MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60`, plus re-exports of error classes and dataclasses (the public surface)
- `the_one/mcp/errors.py` defining `MCPClientError(Exception)` + 6 subclasses per flight §3
- `the_one/mcp/types.py` defining `MCPTool` + `MCPToolResult` frozen dataclasses per flight §4 / §5b
- `the_one/mcp/client.py` containing only an empty `MCPClient` class shell (placeholder; L2 implements)
- `the_one/mcp/transports/__init__.py` (empty package marker)
- `the_one/mcp/transports/stdio.py` containing only a function placeholder docstring (L5 implements)
- `the_one/mcp/transports/streamable_http.py` containing only a function placeholder docstring (L4 implements)
- `the_one/interfaces/web/api.py::_validate_mcp_source_config` extended to validate `config.env: dict[str, str]` in the stdio branch (after the `cwd` validation block, before the `elif source.type == "streamable-http":` branch)
- `tests/test_db_api.py::TestMCPSourceAPI::test_validation_rejects_stdio_config_env_non_string` (or similar) — new test asserting that `config.env = {"FOO": 42}` returns 422
- `CLAUDE.md` extended with 6 enumerated F2 contracts under a new section (insert near the existing F1 MCP contracts at lines 290-310)
- `the_one/agents.md` extended with the matching contracts (placement: same section as F1 MCP storage docs, around line 52)
- `the_one.mcp` importable; `mcp.types.LATEST_PROTOCOL_VERSION == the_one.mcp._PINNED_PROTOCOL_VERSION` asserts true at runtime
- `make test` passes (existing 1099 + new test); `make lint` clean

## Acceptance Criteria

- [ ] `pyproject.toml` includes exact `"mcp==1.27.0"` in the `dependencies` list (positioned after `"cryptography>=43.0"`); compatible-release `~=`, minimum `>=`, and optional placement are all rejected
- [ ] `pip install -e ".[dev,all-llms]"` succeeds in the dev environment
- [ ] `from the_one import mcp` succeeds without ImportError
- [ ] `from the_one.mcp import MCPClient, MCPTool, MCPToolResult, MCPClientError, MCPVersionMismatch, MCPCapabilityMissing, MCPConnectionError, MCPToolNotFoundError, MCPArgumentError, MCPCallError` succeeds
- [ ] `the_one.mcp._PINNED_PROTOCOL_VERSION == "2025-11-25"`
- [ ] `the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS == 30`
- [ ] `the_one.mcp.MCP_DEFAULT_CALL_TIMEOUT_SECONDS == 60`
- [ ] **5 new tests total** added to the test suite, broken down as:
  - 3 in `tests/test_mcp_client.py::TestModuleSetup`: `test_pinned_protocol_version_matches_sdk` (the upgrade-procedure tripwire), `test_timeout_constants_present`, `test_dataclasses_frozen`
  - 2 in `tests/test_db_api.py::TestMCPSourceAPI`: `test_validation_rejects_stdio_config_env_non_string_value`, `test_validation_rejects_stdio_config_env_non_dict`
- [ ] The SDK-version tripwire (`test_pinned_protocol_version_matches_sdk`) imports both `mcp.types.LATEST_PROTOCOL_VERSION` and `the_one.mcp._PINNED_PROTOCOL_VERSION`, fails LOUDLY if unequal — this guards the SDK-pin upgrade procedure for future bumps
- [ ] `the_one/mcp/errors.py` defines `MCPClientError(Exception)`, `MCPVersionMismatch(MCPClientError)`, `MCPCapabilityMissing(MCPClientError)`, `MCPConnectionError(MCPClientError)`, `MCPToolNotFoundError(MCPClientError)`, `MCPArgumentError(MCPClientError)`, `MCPCallError(MCPClientError)`. Each subclass formats a clean single-sentence `__str__` per flight §3 (small-model friendly: no nested causes, no rich tracebacks visible in tool-result strings)
- [ ] `the_one/mcp/types.py` defines `@dataclass(frozen=True) MCPTool` with fields `name: str`, `description: str`, `input_schema: dict[str, Any]`, `output_schema: dict[str, Any] | None`, `annotations: dict[str, Any] | None` — matching flight §5b verbatim
- [ ] `the_one/mcp/types.py` defines `@dataclass(frozen=True) MCPToolResult` with fields `text: str`, `raw: list[dict[str, Any]]`, `structured: dict[str, Any] | None`, `is_error: bool` — matching flight §4 verbatim
- [ ] `the_one/mcp/client.py` contains a minimal `MCPClient` class shell (just `class MCPClient: """L2 implements"""` placeholder) — does NOT import the SDK at module-load time (defer to L2)
- [ ] `the_one/mcp/transports/{stdio,streamable_http}.py` contain only function placeholders with docstrings citing the flight design decisions — no logic, no SDK imports yet (L4/L5 implement)
- [ ] `the_one/interfaces/web/api.py::_validate_mcp_source_config` stdio branch validates `config.env`: extracted via `cfg.get("env", {})`; if not `isinstance(env, dict)` OR not all `(isinstance(k, str) and isinstance(v, str))` for `k, v in env.items()`, raise `HTTPException(422, detail="MCP source config.env must be a dict of string-to-string.")` — message matches the existing headers pattern verbatim except for the field name
- [ ] The validator's docstring (lines 540-554; the `def` at line 539 is the signature line) is updated to document the `config.env` validation in its stdio bullet — see Implementation Guidance step 3 for explicit before/after text
- [ ] New test `test_validation_rejects_stdio_config_env_non_string_value` (in `tests/test_db_api.py::TestMCPSourceAPI`) creates a stdio source via POST with `config = {"command": "x", "env": {"FOO": 42}}` and asserts `response.status_code == 422` AND `"config.env" in response.json()["detail"]`
- [ ] New test `test_validation_rejects_stdio_config_env_non_dict` asserts `config = {"command": "x", "env": "not-a-dict"}` returns 422 with the same detail
- [ ] CLAUDE.md (project root) extended with a new section "## F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)" inserted directly after the **"Encryption rotation invariant: no non-DML between SELECT and commit"** paragraph (currently at line 304) — i.e., immediately after the last paragraph of the existing F1 MCP storage block. The new section enumerates 6 contracts:
  1. **Module layout**: `the_one/mcp/{__init__, client, errors, types, transports/{stdio, streamable_http}}` — peer of `the_one/llm/`, NOT under `the_one/tools/`
  2. **`_PINNED_PROTOCOL_VERSION` constant** — location (`the_one/mcp/__init__.py`), value, and upgrade procedure (bump SDK pin → import `LATEST_PROTOCOL_VERSION` from `mcp.types` → update constant → run integration tests against fresh fixture → confirm version-mismatch tests still pass). Read the constant **at call time**, NOT via `from … import _PINNED_PROTOCOL_VERSION` (test monkeypatch works only with attribute access)
  3. **F4-pool compatibility invariants**: `is_alive: bool` (false until connect() returns; true thereafter; false from disconnect() start), `last_activity: float` (monotonic clock, updated on every list_tools/call_tool), `disconnect()` is idempotent and never raises, no thread-locals or module-globals on instances. **Naming aligned with `PtySession`** (`the_one/platform/pty.py`) so F4 builds one reaper code path
  4. **`build_stdio_environ` helper signature**: `build_stdio_environ(source: MCPSource, allowlist_env: dict[str, str]) -> dict[str, str]` — 2-layer flat merge of allowlist_env + (config.env ∪ secrets), secrets win on collision. **Do NOT consume `MCPSource.merged_config()`** for stdio environ assembly — that's a flat top-level merge that would inject `command`/`args`/etc. as env-var-shaped keys. Future maintainer caution: don't "fix" this back to merged_config()
  5. **Fail-hard version-handshake stance**: `MCPClient.connect()` raises `MCPVersionMismatch` if the server's announced `protocolVersion != _PINNED_PROTOCOL_VERSION` (exact match). This is **narrower** than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist; the SDK's own `RuntimeError` from `session.initialize()` on truly-unsupported versions is caught and re-raised as `MCPVersionMismatch` so the operator sees one consistent error type. Pre-release stance; revisit at 1.0
  6. **`MCPTool` and `MCPToolResult` dataclass shapes** — frozen dataclasses defined in `the_one/mcp/types.py` per flight §4 and §5b. F6 reads MCPTool to wrap as `Tool` instances; F7 reads `MCPToolResult.raw` for the inspector; agent reads `.text`
- [ ] `the_one/agents.md` extended with the same 6 contracts in concise form (1-2 sentences each), placed in the section that covers MCPSourceRepository (around line 52)
- [ ] `make lint` exits 0 (no NEW ruff errors introduced; pre-existing baseline preserved)
- [ ] `make test` exits 0 — existing 1099 passing tests + 5 new tests (3 module-setup + 2 API-validation) = **1104 passing tests** total (1 skipped from baseline carries forward unchanged)

## Verification Steps

```bash
# Pin succeeded and SDK installed
pip install -e ".[dev,all-llms]" 2>&1 | tail -5
python -c "import mcp; print('mcp installed at:', mcp.__version__ if hasattr(mcp, '__version__') else 'no __version__')"

# Module skeleton importable
python -c "
from the_one import mcp
from the_one.mcp import (
    MCPClient, MCPTool, MCPToolResult,
    MCPClientError, MCPVersionMismatch, MCPCapabilityMissing,
    MCPConnectionError, MCPToolNotFoundError, MCPArgumentError, MCPCallError,
)
print('imports OK')
print('_PINNED_PROTOCOL_VERSION =', mcp._PINNED_PROTOCOL_VERSION)
print('MCP_DEFAULT_TIMEOUT_SECONDS =', mcp.MCP_DEFAULT_TIMEOUT_SECONDS)
print('MCP_DEFAULT_CALL_TIMEOUT_SECONDS =', mcp.MCP_DEFAULT_CALL_TIMEOUT_SECONDS)
"

# SDK version constant matches what the SDK exports
python -c "
import mcp.types as mt
from the_one import mcp as the_one_mcp
assert mt.LATEST_PROTOCOL_VERSION == the_one_mcp._PINNED_PROTOCOL_VERSION, (
    f'PINNED ({the_one_mcp._PINNED_PROTOCOL_VERSION}) != SDK LATEST ({mt.LATEST_PROTOCOL_VERSION})'
)
print('version pin matches SDK')
"

# Dataclass shapes
python -c "
from the_one.mcp import MCPTool, MCPToolResult
import dataclasses as dc
tool_fields = {f.name: f.type for f in dc.fields(MCPTool)}
result_fields = {f.name: f.type for f in dc.fields(MCPToolResult)}
assert set(tool_fields) == {'name', 'description', 'input_schema', 'output_schema', 'annotations'}
assert set(result_fields) == {'text', 'raw', 'structured', 'is_error'}
# frozen
import pytest
t = MCPTool(name='x', description='', input_schema={}, output_schema=None, annotations=None)
try:
    t.name = 'y'
    raise SystemExit('NOT FROZEN')
except dc.FrozenInstanceError:
    print('MCPTool frozen OK')
"

# Error hierarchy
python -c "
from the_one.mcp import MCPClientError, MCPVersionMismatch, MCPCapabilityMissing, MCPConnectionError, MCPToolNotFoundError, MCPArgumentError, MCPCallError
for cls in [MCPVersionMismatch, MCPCapabilityMissing, MCPConnectionError, MCPToolNotFoundError, MCPArgumentError, MCPCallError]:
    assert issubclass(cls, MCPClientError), cls
print('error hierarchy OK')
e = MCPVersionMismatch(pinned='2025-11-25', observed='2024-11-05')
print('MCPVersionMismatch str:', str(e))
"

# F1 API validator extension — both rejection paths
make test ARGS='-k test_validation_rejects_stdio_config_env'
# expect: 2 tests passing

# Full suite + lint
make test
make lint
```

## Implementation Guidance

1. **Pin the SDK** in `pyproject.toml`. Add `"mcp==1.27.0"` to the `dependencies` list (NOT optional). Position it after `"cryptography>=43.0"` for alphabetical-ish ordering (the file already mixes alphabetical and grouped — match local convention by placing MCP-related deps together at the end of the base list).

2. **Create the module skeleton.** All files MUST import without error after this leg, even though most are stubs.

   `the_one/mcp/__init__.py`:
   ```python
   """MCP (Model Context Protocol) client foundation.

   F2 lands the runtime-foundation: thin async wrapper around mcp==1.27.0 SDK
   exposing connect / list-tools / call-tool / disconnect lifecycle for both
   transports (stdio + streamable-http). No agent integration (F6), no warm-pool
   (F4), no sandbox (F3), no OAuth flow (F5).

   See CLAUDE.md "F2 (MCP Client Foundation) Contracts" for invariants.
   See _PINNED_PROTOCOL_VERSION docstring for SDK upgrade procedure.
   """

   _PINNED_PROTOCOL_VERSION = "2025-11-25"
   """The MCP spec revision pinned by F2.

   Matches mcp==1.27.0's mcp.types.LATEST_PROTOCOL_VERSION exactly. Verified at
   flight-design time via wheel inspection.

   Upgrade procedure:
       1. Bump the mcp SDK pin in pyproject.toml.
       2. Run: python -c "from mcp.types import LATEST_PROTOCOL_VERSION; print(LATEST_PROTOCOL_VERSION)"
       3. Update this constant to match.
       4. Run integration tests against fresh fixture build:
              pytest tests/test_mcp_integration.py
       5. Confirm version-mismatch test still passes (it asserts
          our constant equals the SDK's at runtime).

   Read at call time (`the_one.mcp._PINNED_PROTOCOL_VERSION`), NOT
   imported by name (`from the_one.mcp import _PINNED_PROTOCOL_VERSION`) — the
   latter binds at module-load and breaks `monkeypatch.setattr` in tests.
   """

   MCP_DEFAULT_TIMEOUT_SECONDS = 30
   """Default timeout for handshake (initialize) and list_tools — should be fast."""

   MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60
   """Default timeout for call_tool — legitimate tools may run longer (e.g. static analyzer)."""

   from the_one.mcp.client import MCPClient
   from the_one.mcp.errors import (
       MCPArgumentError,
       MCPCallError,
       MCPCapabilityMissing,
       MCPClientError,
       MCPConnectionError,
       MCPToolNotFoundError,
       MCPVersionMismatch,
   )
   from the_one.mcp.types import MCPTool, MCPToolResult

   __all__ = [
       "_PINNED_PROTOCOL_VERSION",
       "MCP_DEFAULT_TIMEOUT_SECONDS",
       "MCP_DEFAULT_CALL_TIMEOUT_SECONDS",
       "MCPClient",
       "MCPTool",
       "MCPToolResult",
       "MCPClientError",
       "MCPVersionMismatch",
       "MCPCapabilityMissing",
       "MCPConnectionError",
       "MCPToolNotFoundError",
       "MCPArgumentError",
       "MCPCallError",
   ]
   ```

   `the_one/mcp/errors.py`:
   ```python
   """MCP client error hierarchy.

   Single base class with narrow subclasses. Each subclass formats a clean
   single-sentence __str__ for small-model consumption (mission constraint #61).
   No nested causes, no rich tracebacks visible in tool-result strings.
   """


   class MCPClientError(Exception):
       """Base for all MCPClient-raised errors."""


   class MCPVersionMismatch(MCPClientError):
       """Server announced a protocol version different from what the-one targets."""

       def __init__(self, pinned: str, observed: str) -> None:
           self.pinned = pinned
           self.observed = observed
           super().__init__(
               f"MCP server announced protocol version {observed}, the-one supports "
               f"{pinned}. Server upgrade or the-one downgrade required."
           )


   class MCPCapabilityMissing(MCPClientError):
       """Server didn't announce a capability the-one needs."""

       def __init__(self, capability: str) -> None:
           self.capability = capability
           super().__init__(
               f"MCP server did not announce required capability: {capability!r}."
           )


   class MCPConnectionError(MCPClientError):
       """Spawn failed, stream closed, network unreachable, transport-level error."""


   class MCPToolNotFoundError(MCPClientError):
       """call_tool was invoked with a tool name not present in the server's tool list."""

       def __init__(self, tool_name: str) -> None:
           self.tool_name = tool_name
           super().__init__(f"MCP tool not found on server: {tool_name!r}.")


   class MCPArgumentError(MCPClientError):
       """call_tool arguments don't conform to the tool's input JSON Schema."""

       def __init__(self, tool_name: str, validation_message: str) -> None:
           self.tool_name = tool_name
           self.validation_message = validation_message
           super().__init__(
               f"MCP tool {tool_name!r} rejected arguments: {validation_message}"
           )


   class MCPCallError(MCPClientError):
       """Server returned a tool-call error result (isError=true)."""

       def __init__(self, tool_name: str, server_message: str) -> None:
           self.tool_name = tool_name
           self.server_message = server_message
           super().__init__(f"MCP tool {tool_name!r} returned an error: {server_message}")
   ```

   `the_one/mcp/types.py`:
   ```python
   """MCP value-objects: MCPTool and MCPToolResult dataclasses.

   Frozen for safety (immutable after construction). MCPTool is constructed by
   MCPClient.list_tools() from the SDK's tool-list response; MCPToolResult is
   constructed by MCPClient.call_tool() from the SDK's call-tool response with
   text-flattening of content blocks.

   See flight design decisions §4 (MCPToolResult) and §5b (MCPTool) for the
   full shape rationale.
   """

   from dataclasses import dataclass
   from typing import Any


   @dataclass(frozen=True)
   class MCPTool:
       """A tool available on an MCP server.

       Constructed from the server's tools/list response. F6 will translate
       these into the project's existing Tool abstraction.
       """

       name: str
       description: str
       input_schema: dict[str, Any]
       output_schema: dict[str, Any] | None
       annotations: dict[str, Any] | None


   @dataclass(frozen=True)
   class MCPToolResult:
       """The result of a tool call.

       text: flattened textual representation for agent consumption (mission
           constraint #56 — agent loop dispatches by tool name; tool results
           render to string format)
       raw: original content blocks from the server (for F7's inspector)
       structured: MCP `structuredContent` typed-object form, if present
       is_error: mirrors the server's isError flag — when true, MCPClient.call_tool
           raises MCPCallError; this field is preserved on the dataclass for
           inspector trace-pane visibility (F7)
       """

       text: str
       raw: list[dict[str, Any]]
       structured: dict[str, Any] | None
       is_error: bool
   ```

   `the_one/mcp/client.py` (placeholder for L2):
   ```python
   """MCPClient — async wrapper around mcp==1.27.0 SDK's ClientSession.

   L2 implements connect/disconnect lifecycle + handshake + capability negotiation.
   L4 wires streamable-http transport dispatch.
   L5 wires stdio transport dispatch.
   L6a implements list_tools and call_tool happy-path.
   L6b implements input validation and full error-path translation.

   See flight design decisions §2 (API surface), §9 (F4-pool compat invariants).
   """


   class MCPClient:
       """Async wrapper for an MCP server connection. L2 implements lifecycle."""
   ```

   `the_one/mcp/transports/__init__.py`:
   ```python
   """MCP client transport implementations.

   stdio: process-spawned subprocess servers (L5)
   streamable_http: HTTP-based servers (L4)
   """
   ```

   `the_one/mcp/transports/stdio.py`:
   ```python
   """Stdio transport for MCPClient.

   L5 implements:
   - build_stdio_environ(source, allowlist_env): 2-layer flat-merge environ helper
     (canonical _ENV_ALLOWLIST from the_one.platform.env + config.env ∪ secrets,
     secrets win on collision)
   - connect_stdio(source) -> (read_stream, write_stream): translate MCPSource into
     StdioServerParameters and open mcp.client.stdio.stdio_client context

   See flight design decision §11 for build_stdio_environ contract.
   """
   ```

   `the_one/mcp/transports/streamable_http.py`:
   ```python
   """Streamable-HTTP transport for MCPClient.

   L4 implements:
   - build_request_headers(source): 2-layer flat-merge headers helper
     (config.headers ∪ secrets, secrets win on collision)
   - connect_streamable_http(source, http_client=None) -> (read_stream, write_stream):
     open mcp.client.streamable_http.streamable_http_client context

   Uses the CURRENT SDK function `streamable_http_client(http_client=...)` —
   NOT the deprecated `streamablehttp_client`. The `http_client=` parameter
   enables in-process ASGI integration testing (pass a pre-built
   httpx.AsyncClient with ASGITransport).
   """
   ```

3. **Extend F1's API validator.** In `the_one/interfaces/web/api.py`, locate the stdio branch of `_validate_mcp_source_config` (after the `cwd` validation; pattern: search for `MCP source config.cwd must be a string if present.`). Insert the new validation block right after the `cwd` block, before the `elif source.type == "streamable-http":` line. Block content:

   ```python
       env = cfg.get("env", {})
       if not isinstance(env, dict) or not all(
           isinstance(k, str) and isinstance(v, str) for k, v in env.items()
       ):
           raise HTTPException(
               status_code=422,
               detail="MCP source config.env must be a dict of string-to-string.",
           )
   ```

   Update the function's docstring (lines 540-554; line 539 is the `def`) to mention `config.env` validation. The existing stdio bullet reads:

   ```
       Stdio: config.command is required (non-empty string); config.args
         must be a list[str] if present; config.cwd must be a string if
         present.
   ```

   Replace it with:

   ```
       Stdio: config.command is required (non-empty string); config.args
         must be a list[str] if present; config.cwd must be a string if
         present; config.env must be a dict[str, str] if present.
   ```

   (Single-word append: `; config.env must be a dict[str, str] if present.` to the existing stdio bullet, preserving the docstring's line-wrap shape.)

4. **Add the new test file `tests/test_mcp_client.py`** with ONE test class for module setup. This file will grow significantly in L2-L6b; L1 only adds the `TestModuleSetup` class with the SDK-version-pin tripwire test:

   ```python
   """Unit tests for the_one.mcp module.

   L1: module setup, SDK version pin tripwire.
   L2: MCPClient lifecycle and handshake (mocked ClientSession).
   L3: integration tests live in test_mcp_integration.py.
   L4: streamable-http transport (mocked + integration via L3 fixture).
   L5: stdio transport (mocked + integration via L3 fixture).
   L6a: list_tools + call_tool happy path.
   L6b: input validation + error paths + non-text content blocks.
   """

   import dataclasses

   import pytest


   class TestModuleSetup:
       def test_pinned_protocol_version_matches_sdk(self) -> None:
           """Tripwire: F2's pinned constant must match the SDK's exported LATEST_PROTOCOL_VERSION.

           When the SDK pin is bumped (per the upgrade procedure in the_one/mcp/__init__.py),
           this test will fail loudly until the operator updates _PINNED_PROTOCOL_VERSION too.
           """
           import mcp.types
           from the_one import mcp as the_one_mcp

           assert the_one_mcp._PINNED_PROTOCOL_VERSION == mcp.types.LATEST_PROTOCOL_VERSION, (
               f"PINNED ({the_one_mcp._PINNED_PROTOCOL_VERSION}) != "
               f"SDK LATEST_PROTOCOL_VERSION ({mcp.types.LATEST_PROTOCOL_VERSION}). "
               f"See the_one/mcp/__init__.py upgrade procedure."
           )

       def test_timeout_constants_present(self) -> None:
           from the_one import mcp as the_one_mcp

           assert the_one_mcp.MCP_DEFAULT_TIMEOUT_SECONDS == 30
           assert the_one_mcp.MCP_DEFAULT_CALL_TIMEOUT_SECONDS == 60

       def test_dataclasses_frozen(self) -> None:
           from the_one.mcp import MCPTool, MCPToolResult

           tool = MCPTool(name="x", description="", input_schema={}, output_schema=None, annotations=None)
           result = MCPToolResult(text="", raw=[], structured=None, is_error=False)

           with pytest.raises(dataclasses.FrozenInstanceError):
               tool.name = "y"  # type: ignore[misc]

           with pytest.raises(dataclasses.FrozenInstanceError):
               result.text = "z"  # type: ignore[misc]
   ```

5. **Add the F1 API validation tests** to `tests/test_db_api.py::TestMCPSourceAPI`. Place them after `test_validation_rejects_unknown_transport_type` (around line 343):

   ```python
       async def test_validation_rejects_stdio_config_env_non_string_value(
           self, client: AsyncClient
       ) -> None:
           """L1: F1 API validator extended to reject non-string env values."""
           resp = await client.post(
               "/api/mcp-sources",
               json={
                   "name": "test-stdio-bad-env",
                   "type": "stdio",
                   "config": {"command": "echo", "env": {"FOO": 42}},
                   "secrets": {},
               },
           )
           assert resp.status_code == 422
           assert "config.env" in resp.json()["detail"]

       async def test_validation_rejects_stdio_config_env_non_dict(
           self, client: AsyncClient
       ) -> None:
           """L1: F1 API validator extended to reject non-dict env."""
           resp = await client.post(
               "/api/mcp-sources",
               json={
                   "name": "test-stdio-bad-env-2",
                   "type": "stdio",
                   "config": {"command": "echo", "env": "not-a-dict"},
                   "secrets": {},
               },
           )
           assert resp.status_code == 422
           assert "config.env" in resp.json()["detail"]
   ```

6. **Update `CLAUDE.md`** at the project root. Search for the section header "**MCP source storage contract (authoritative for F2-F8)**" (around line 300). Insert a new section directly after the existing "**Encryption rotation invariant: no non-DML between SELECT and commit**" block (around line 304). The new section is titled "**F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)**" and contains the 6 enumerated contracts as listed in the Acceptance Criteria above. Each contract gets a short paragraph (3-5 lines).

7. **Update `the_one/agents.md`**. Search for the existing MCP-related paragraph (around line 52, starting "`MCPSourceRepository` (M07 F1)"). Add the 6 F2 contracts as concise bullets in the same area:

   ```markdown
   - **F2 module home**: `the_one/mcp/` (peer of `the_one/llm/`, NOT under `the_one/tools/`); MCPClient is a service abstraction. F6 wraps MCPClient → Tool via MCPToolProvider.
   - **F2 SDK pin + protocol revision**: `mcp==1.27.0` exact pin; `_PINNED_PROTOCOL_VERSION = "2025-11-25"` constant in `the_one/mcp/__init__.py` (read at call time, not import-bound).
   - **F2 fail-hard version policy**: connect() raises `MCPVersionMismatch` on any mismatch with `_PINNED_PROTOCOL_VERSION`; narrower than the SDK's SUPPORTED_PROTOCOL_VERSIONS whitelist; pre-release stance, revisit at 1.0.
   - **F2 F4-pool compat**: MCPClient exposes `is_alive: bool` and `last_activity: float` (PtySession-aligned); `disconnect()` is idempotent; instances are picklable-free (no thread-locals, no module-globals).
   - **F2 stdio environ helper**: `build_stdio_environ(source, allowlist_env)` does 2-layer flat merge of `the_one.platform.env._ENV_ALLOWLIST` + (config.env ∪ secrets); **do NOT consume MCPSource.merged_config()** for stdio environ (that's a flat top-level merge that injects command/args as env-var keys).
   - **F2 dataclasses**: `MCPTool` and `MCPToolResult` are frozen dataclasses in `the_one/mcp/types.py`; `MCPToolResult.text` for agent, `.raw` for F7 inspector, `.structured` for typed-object form.
   ```

8. **Run lint + tests** to confirm clean state before signaling. Address any new ruff failures introduced by this leg (must be zero NEW errors).

## Edge Cases

- **`mcp` SDK install fails on first install attempt**: The SDK has 9 transitive deps including `httpx-sse`, `python-multipart`, `sse-starlette`. If pip resolution fails, check whether any transitive conflict with the existing the-one deps. If so, document the conflict in the flight log and either pin a compatible version or upgrade the conflicting dep. Divert criterion in flight spec covers this.

- **`from the_one import mcp` shadowed by `mcp` SDK**: The `mcp` SDK installs as a top-level `mcp` package. The expression `the_one.mcp` is the-one's sub-package; `mcp` (alone) is the SDK. They don't collide because Python's import system distinguishes by full dotted path — but inside `the_one/mcp/__init__.py`, an unqualified `import mcp` would import the SDK, not the-one's package. Use `import mcp.types` or `from mcp.types import ...` explicitly when referring to the SDK from within the-one's code. This shows up first in the L1 test file.

- **The placeholder `class MCPClient: """L2 implements"""`**: L2 will replace this entirely. The placeholder must NOT define `__init__` with arguments (would conflict with L2's actual signature) and must NOT raise. It must be importable so that `from the_one.mcp import MCPClient` works at L1's `__init__.py` re-export.

- **Pre-existing `_validate_mcp_source_config` test count**: F1 currently has 4 stdio-validation tests, 5 streamable-http-validation tests, and 1 unknown-transport test in `TestMCPSourceAPI`. Adding 2 new tests brings stdio-side coverage to 6. No existing test names collide.

- **Doc-update placement in CLAUDE.md**: CLAUDE.md is large (~330 lines). The MCP section sits in a defined block (300-310). Insert the new F2 section IMMEDIATELY after the existing "Encryption rotation invariant" paragraph but BEFORE the next major section header. Do NOT split or move existing content. Verify the insertion preserves the document's outline structure.

- **`_ENV_ALLOWLIST` import path**: Verified at design time as `the_one/platform/env.py`. L1 doesn't import it (that's L5's work) but `agents.md` cites the path; verify the path is still accurate before doc commit.

- **`MCPClient` placeholder cannot import the SDK**: The L1 `client.py` is a stub. Importing `mcp.ClientSession` here would force SDK import on every `from the_one.mcp import ...` even if the caller only wants `MCPTool`. Defer SDK imports to L2 (when MCPClient.connect() actually instantiates the session).

## Files Affected

- `pyproject.toml` — add `"mcp==1.27.0"` to `dependencies`
- `the_one/mcp/__init__.py` (NEW) — public surface + constants
- `the_one/mcp/errors.py` (NEW) — error hierarchy
- `the_one/mcp/types.py` (NEW) — `MCPTool` + `MCPToolResult` dataclasses
- `the_one/mcp/client.py` (NEW) — empty `MCPClient` placeholder
- `the_one/mcp/transports/__init__.py` (NEW) — package marker
- `the_one/mcp/transports/stdio.py` (NEW) — placeholder docstring
- `the_one/mcp/transports/streamable_http.py` (NEW) — placeholder docstring
- `the_one/interfaces/web/api.py::_validate_mcp_source_config` — extend stdio branch with `config.env` validation; update docstring
- `tests/test_mcp_client.py` (NEW) — `TestModuleSetup` with 3 tests
- `tests/test_db_api.py::TestMCPSourceAPI` — add 2 new tests after `test_validation_rejects_unknown_transport_type`
- `CLAUDE.md` — add new "F2 (MCP Client Foundation) Contracts" section after the existing F1 MCP contracts block (~line 305)
- `the_one/agents.md` — add 6 F2 bullets near the existing MCPSourceRepository paragraph (~line 52)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — 1104 passing, 1 skipped (existing 1099 passing + 5 new tests = 3 module-setup in `tests/test_mcp_client.py::TestModuleSetup` + 2 API-validation in `tests/test_db_api.py::TestMCPSourceAPI`)
- [ ] `make lint` clean (no NEW ruff errors)
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress / ### L1 SDK Pin and Skeleton`
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end

## Citation Audit

5 citations verified against current code at leg design time:

1. `pyproject.toml` dependencies block — verified at lines 1-30 (no `mcp` SDK pin currently present); insertion target after `"cryptography>=43.0"` confirmed
2. `the_one/interfaces/web/api.py:539` `_validate_mcp_source_config` — verified function exists; stdio branch covers `command`/`args`/`cwd` (lines 555-575); `cwd` validation block ends at line 575 with `elif source.type == "streamable-http":` at line 577 — insertion point is between
3. `the_one/interfaces/web/api.py:587-593` `headers` validation pattern — verified: this is the precedent the new `config.env` validation mirrors verbatim except for field name
4. `tests/test_db_api.py:197` `class TestMCPSourceAPI` — verified; insertion point for new tests is after `test_validation_rejects_unknown_transport_type` at line 336-342
5. `CLAUDE.md` lines 290-310 — verified existing F1 MCP contract block is structurally intact; insertion point for new F2 contracts section is after the "Encryption rotation invariant" paragraph at line 304

All citations clean — no drift, no stale anchors.

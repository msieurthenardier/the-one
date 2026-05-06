# Leg: 07-hat-mcp-foundation

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Operator-driven 5-step verification that F2's MCP Client Foundation works end-to-end against the in-repo FastMCP fixture, exercising the full F1+F2 contract: UI-driven source configuration with encryption at rest → Python REPL connect via MCPClient → list_tools → call_tool round-trip.

## Test approach

In-repo `tests/fixtures/mcp/hello_server.py` (FastMCP `echo`/`add` server, L3-shipped) configured as a stdio MCP source via the F1 admin UI. No external deps needed.

## Verification steps

- [x] **Step 1**: Hello-fixture exists in the running container at `/app/tests/fixtures/mcp/hello_server.py` (verified via `docker compose exec the-one ls`)
- [x] **Step 2**: Operator configured `hello` (stdio, `command=/usr/local/bin/python`, `args=["-m", "tests.fixtures.mcp.hello_server", "--stdio"]`, `env={"PYTHONPATH": "/app"}`, `secrets={"MY_HAT_SECRET": "test-value-123"}`) via UI at `http://localhost:8484/#admin/mcp-sources` — save succeeded; list view rendered correctly; edit view round-trip showed `MY_HAT_SECRET` masked as `***...-123` (per-decoded-VALUE masking)
- [x] **Step 3**: Encryption decryption round-trip recovered `test-value-123` from the encrypted blob; `MCPClient.connect()` succeeded; `is_alive=True`, `negotiated_protocol_version="2025-11-25"`, `server_capabilities` populated with all 7 keys including `tools`
- [x] **Step 4**: `list_tools()` returned `["add", "echo"]`; `echo` schema has `properties=["message"]`, `add` has `properties=["a", "b"]`
- [x] **Step 5**: `call_tool("echo", {"message": "hello HAT"})` → `MCPToolResult(text="hello HAT", is_error=False, raw_blocks=1)`
- [x] **Bonus Step 6**: `call_tool("add", {"a": 2, "b": 3})` → `MCPToolResult(text="5", structured={"result": 5}, is_error=False)`

## Results

**All 5 required HAT steps + bonus step PASSED.** Full end-to-end exercise of:
- F1: UI-driven CRUD with field-segregated encryption + per-key __MASKED__ round-trip + decryption restoration
- F2: MCPClient lifecycle, version handshake, capability negotiation, list_tools mapping, call_tool with both text and structured results, real subprocess spawn via stdio_client

## Defect discovered (forwarded to F4)

`MCPClient.disconnect()` logs `RuntimeError: generator didn't stop` on every disconnect cycle. The exception is caught by L2's `except Exception: logger.warning(...)` clause and suppressed; **subprocess cleanup is functionally correct** (verified via `/proc` scan — no orphan processes after script exit). The warning is a teardown-noise issue, not a leak.

**Root cause**: `@asynccontextmanager` + nested `async with` for the SDK's transport+session CMs has a known issue where the generator body, after `__aexit__`'s `gen.athrow(...)`, doesn't reach normal completion before contextlib's "generator didn't stop" check fires.

**Canonical fix**: refactor the transport CMs (`connect_stdio`, `connect_streamable_http`) to use `contextlib.AsyncExitStack` for nested-context cleanup, and update `MCPClient.disconnect()` to drive the stack's `aclose()` directly. This requires touching `the_one/mcp/client.py`, `transports/stdio.py`, and `transports/streamable_http.py`.

**Recommendation**: defer to F4's warm-pool flight. F4's pool calls `disconnect()` on every eviction; the fix is best validated against F4's per-source registry + idle-TTL reaper races. Captured as a forward action item in the F2 flight debrief.

**Workaround until fixed**: the current behavior is correct (subprocess dies, state cleared), just noisy. Operators won't see the warning in normal flow (it's logger.warning, not a raise).

## Binary go/no-go

✅ **PASS** — all 5 required steps completed. Defect noted as a non-blocking follow-up.

## Binary go/no-go

All 5 required steps must pass for L7 to land. Bonus step is informational.

## Results

> Populated as the HAT progresses.

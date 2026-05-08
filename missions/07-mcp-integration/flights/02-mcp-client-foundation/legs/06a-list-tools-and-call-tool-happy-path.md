# Leg: 06a-list-tools-and-call-tool-happy-path

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Replace L2's `list_tools`/`call_tool` stubs in `MCPClient` with full implementations covering the happy path. `list_tools` returns `list[MCPTool]` (the L1 frozen dataclass populated from the SDK's `ListToolsResult.tools`); `call_tool(name, arguments)` returns `MCPToolResult` (text-only block flattening + structured content + isError → MCPCallError raise + unknown-tool → MCPToolNotFoundError raise). NO input validation (deferred to L6b); NO non-text content-block placeholder rendering (deferred to L6b); NO error-path translation matrix (deferred to L6b).

## Context

- **Flight design** §4 (`MCPToolResult` dataclass: `text`, `raw`, `structured`, `is_error`); §5b (`MCPTool` dataclass: `name`, `description`, `input_schema`, `output_schema`, `annotations`); §3 (error hierarchy: `MCPCallError`, `MCPToolNotFoundError`)
- **L1 dataclass shapes** (already in `the_one/mcp/types.py`):
  - `MCPTool(name: str, description: str, input_schema: dict, output_schema: dict | None, annotations: dict | None)` — frozen
  - `MCPToolResult(text: str, raw: list[dict], structured: dict | None, is_error: bool)` — frozen
- **L2's current stubs** (`the_one/mcp/client.py:258-266`):
  ```python
  async def list_tools(self) -> list:
      self._touch_activity()
      raise NotImplementedError("L6a implements list_tools")

  async def call_tool(self, name: str, arguments: dict) -> Any:
      self._touch_activity()
      raise NotImplementedError("L6a implements call_tool")
  ```
  L6a **replaces these wholesale** (NOT stacks on top). The `_touch_activity()` call carries forward into the real implementation
- **SDK shapes** (verified at design time via in-container probe):
  - `ClientSession.list_tools(cursor=None, *, params=None) -> ListToolsResult` where `ListToolsResult.tools: list[Tool]` and `Tool` has fields `name`, `title`, `description`, `inputSchema`, `outputSchema`, `icons`, `annotations`, `meta`, `execution`. F2's `MCPTool` surfaces `name/description/inputSchema→input_schema/outputSchema→output_schema/annotations`; the rest (`title`, `icons`, `meta`, `execution`) are deliberately not surfaced (defer to F7's inspector if needed)
  - `ClientSession.call_tool(name, arguments=None, read_timeout_seconds=None, progress_callback=None, *, meta=None) -> CallToolResult` where `CallToolResult` has fields `meta`, `content`, `structuredContent`, `isError`. `content` is `list[ContentBlock]` (mixed text/image/audio/resource_link/resource); `structuredContent: dict | None` is the typed-object form
- **L4/L5 integration tests** already exercise `connect()` end-to-end against the FastMCP fixture — once L6a lands, those tests can be extended (or new tests added in TestL6a) to call `list_tools()` and `call_tool()` against the fixture's `echo` and `add` tools
- **Result-rendering scope (this leg)**: `text` field built ONLY from text-type content blocks (concatenated in order). Non-text blocks are **silently dropped** in L6a's `text` field; L6b adds the placeholder-string rendering (`"[image: 1234 bytes, mime=image/png]"` etc.). L6a's `raw` field carries ALL content blocks (text + non-text) so L6b doesn't need to refetch
- **Error scope (this leg)**: only TWO error paths land in L6a:
  - Server-side `isError=true` → raise `MCPCallError(tool_name, server_message)` where `server_message` = the joined text content (best-effort; L6b will refine if needed)
  - Unknown tool name (cached `tools` doesn't contain `name`) → raise `MCPToolNotFoundError(tool_name)` BEFORE the wire call
  L6b adds the rest: jsonschema input validation (`MCPArgumentError`), `httpx.HTTPError` / `anyio.ClosedResourceError` / `asyncio.TimeoutError` / `mcp.shared.exceptions.McpError` translation, `UrlElicitationRequiredError` propagation
- **Tool caching for unknown-tool detection**: `call_tool` needs to know which tool names exist on the server. L6a caches the `list_tools()` result on the MCPClient instance (populated lazily on first `call_tool` if `list_tools` hasn't run yet, OR populated eagerly in `connect()` — pick one). L6b's input validation will read this cache too. Cache invalidation: simple — refresh on every explicit `list_tools()` call (caller's choice). NO server-pushed `notifications/tools/list_changed` handling in F2 (defer)
- **`_touch_activity()` ordering**: per L2 contract (and `test_last_activity_updates_via_list_tools`), `last_activity` must update on EVERY call. L6a calls `_touch_activity()` at the start of both methods (matches L2's stub pattern; activity is recorded even if the call fails)
- **`asyncio.timeout(self.call_timeout_seconds)`**: per flight §8 — `call_tool` uses 60s default, `list_tools` uses the 30s `timeout_seconds`. L6a wraps both in `asyncio.timeout` but the actual SDK errors propagate; L6b will translate `asyncio.TimeoutError` to `MCPConnectionError`. **For L6a**: timeout-firing tests are deferred to L6b — L6a only verifies happy-path completes within the budget
- **F4-pool compat**: `_touch_activity()` is called inside the live-session check; if `is_alive` is False, both methods raise `MCPConnectionError` BEFORE touching activity (acceptable — `last_activity` doesn't update on errors-before-call). Mirrors the L2 contract for `negotiated_protocol_version` / `server_capabilities` properties

## Inputs

What exists before this leg runs:
- L1+L2+L3+L4+L5 outputs: full MCPClient lifecycle, error hierarchy, dataclasses, both transports wired, integration test fixtures (stdio + streamable-http) operational
- L2's `list_tools` and `call_tool` stubs (`the_one/mcp/client.py:258-266`) raising `NotImplementedError`
- L1's `MCPTool` and `MCPToolResult` dataclasses (`the_one/mcp/types.py`)
- L1's `MCPCallError` and `MCPToolNotFoundError` (`the_one/mcp/errors.py`)
- L2's `_touch_activity()` private method (`the_one/mcp/client.py:156-157`)
- L2's `_session: ClientSession | None` instance attribute (set in `connect()`)
- L4/L5 integration tests in `tests/test_mcp_integration.py` proving end-to-end connect against both transports

## Outputs

What exists after this leg completes:
- `the_one/mcp/client.py::MCPClient` — `list_tools` and `call_tool` methods reimplemented (replacing the L2 stubs):
  - `async def list_tools(self) -> list[MCPTool]`: asserts `is_alive` (raise `MCPConnectionError` if not); calls `self._touch_activity()`; calls `self._session.list_tools()` inside `asyncio.timeout(self.timeout_seconds)`; converts each SDK `Tool` to `MCPTool` (mapping `inputSchema`→`input_schema`, `outputSchema`→`output_schema`, plus `name`/`description`/`annotations`); caches the resulting list as `self._tools_cache: list[MCPTool]`; returns the list
  - `async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult`: asserts `is_alive`; calls `self._touch_activity()`; if `self._tools_cache is None`, populates it via `await self.list_tools()`; if `name not in {t.name for t in self._tools_cache}`, raises `MCPToolNotFoundError(name)` BEFORE wire call; calls `self._session.call_tool(name, arguments)` inside `asyncio.timeout(self.call_timeout_seconds)`; converts the SDK's `CallToolResult` to `MCPToolResult` (flattens text content, captures raw, captures structured, captures isError); if `isError=True`, raises `MCPCallError(name, joined_text)` AFTER constructing the result
- New `MCPClient` instance attributes:
  - `self._tools_cache: list[MCPTool] | None = None` — initialized to None in `__init__`; populated on first `list_tools()` or first `call_tool()` (whichever fires first); cleared back to None on `disconnect()` (so a future re-connect rebuilds the cache fresh)
- `tests/test_mcp_client.py` extended with:
  - `TestListToolsAndCallTool` — 11 NEW unit tests using mocked `ClientSession`:
    1. `test_list_tools_returns_mapped_dataclasses` — mock session returns 2 tools; `list_tools()` returns `list[MCPTool]` with correct field mapping (`inputSchema`→`input_schema`, `outputSchema`→`output_schema`)
    2. `test_list_tools_always_refetches` — call `list_tools()` twice; SDK's `session.list_tools` mock asserted called twice (explicit `list_tools` always re-fetches; the cache attribute exists for `call_tool`'s unknown-tool guard, not for short-circuiting `list_tools` itself)
    3. `test_list_tools_raises_when_not_connected` — fresh MCPClient (no `connect()` yet); `list_tools()` raises `MCPConnectionError`
    4. `test_call_tool_text_only_result` — mock returns `CallToolResult(content=[TextContent(text="hi")], structuredContent=None, isError=False)`; `MCPToolResult.text == "hi"`, `.raw == [<dict shape>]`, `.structured is None`, `.is_error is False`
    5. `test_call_tool_text_concatenation` — mock returns 2 text content blocks (`["hello ", "world"]`); `result.text == "hello world"`
    6. `test_call_tool_structured_content` — mock returns `content=[_make_text_content("3")], structuredContent={"result": 3}`; assert `result.text == "3"` AND `result.structured == {"result": 3}` AND `result.is_error is False`
    7. `test_call_tool_unknown_tool_raises_before_wire_call` — `list_tools()` returned `["echo", "add"]`; `call_tool("nonexistent", {})` raises `MCPToolNotFoundError("nonexistent")`; mock session's `call_tool` NOT called (verified via `mock.assert_not_called()`)
    8. `test_call_tool_iserror_raises_mcpcallerror` — mock returns `CallToolResult(content=[TextContent(text="server failed")], isError=True)`; `call_tool("echo", {})` raises `MCPCallError(tool_name="echo", server_message="server failed")` — error message contains both
    9. `test_call_tool_populates_cache_lazily` — call `call_tool("echo", {"message": "hi"})` BEFORE explicit `list_tools()`; verify session.list_tools mock called exactly once internally; result is `MCPToolResult` with text="hi"
    10. `test_call_tool_raises_when_not_connected` — fresh MCPClient; `call_tool("echo", {})` raises `MCPConnectionError`
    11. `test_disconnect_clears_tools_cache` — connect → list_tools → disconnect; assert `client._tools_cache is None` after disconnect (fresh state for next connect; private-state assertion intentionally — internal invariant for F4 pool reuse with no public surface)
  - **Plus REWORK of L2's existing `test_last_activity_updates_via_list_tools`** (in `tests/test_mcp_client.py:359-380`): the L2 test asserted `pytest.raises(NotImplementedError, match="L6a implements list_tools")`. With L6a's real implementation that raise no longer fires. Rework the test IN PLACE (preserving its name): configure `mock_session.list_tools = AsyncMock(return_value=_make_list_tools_result([_make_tool("echo")]))`, then assert `t1 > t0` after `await c.list_tools()` succeeds (no `pytest.raises`). The test still validates the same invariant — `last_activity` updates on `list_tools` — but against the real body
- `tests/test_mcp_integration.py` extended with:
  - `TestL6aHappyPath` (~4 integration tests):
    1. `test_list_tools_streamable_http(mcp_fixture_http_client, monkeypatch)` — connect via streamable-http; `list_tools()` returns 2 tools `{echo, add}`; verify each is `MCPTool` with non-empty input_schema
    2. `test_list_tools_stdio(mcp_fixture_stdio_params)` — connect via stdio; same shape assertion (with `@pytest.mark.timeout(15)` like other stdio integration tests)
    3. `test_call_tool_echo_streamable_http(mcp_fixture_http_client, monkeypatch)` — connect; `call_tool("echo", {"message": "hello"})` → `MCPToolResult(text="hello", is_error=False, ...)`
    4. `test_call_tool_add_stdio(mcp_fixture_stdio_params)` — connect via stdio; `call_tool("add", {"a": 2, "b": 3})` → `MCPToolResult` where `structured == {"result": 5}` AND `text` reflects the SDK's coerced representation (likely `"5"` per L4's design-time note); `@pytest.mark.timeout(15)`
- Test count after L6a: **1136 baseline (post-L5) + 11 NEW unit + 4 integration = exactly 1151 passing** + 1 skipped (unchanged). The L2 test `test_last_activity_updates_via_list_tools` is REWORKED in place (same name) — counted in the baseline, not added
- `make lint` clean (no NEW ruff errors)

## Acceptance Criteria

- [ ] `MCPClient.__init__` initializes `self._tools_cache: list[MCPTool] | None = None`
- [ ] `MCPClient.disconnect` clears `self._tools_cache = None` (post-disconnect; flight log L2 says "Preserve _capabilities, _protocol_version, _last_activity for the F4 pool — once disconnected they're stale but not invalid" — but tools_cache is per-session and MUST be cleared so a re-connect rebuilds fresh)
- [ ] `MCPClient.list_tools()` is implemented (replacing the L2 stub):
  - Raises `MCPConnectionError("MCPClient is not connected; cannot list tools.")` if `not self._is_alive` BEFORE touching activity
  - Calls `self._touch_activity()`
  - Calls `await self._session.list_tools()` inside `async with asyncio.timeout(self.timeout_seconds):`
  - For each `tool` in `result.tools`, constructs `MCPTool(name=tool.name, description=tool.description or "", input_schema=tool.inputSchema or {}, output_schema=tool.outputSchema, annotations=<dict-form-or-None of tool.annotations>)` — handle the case where `tool.annotations` is a Pydantic object (call `.model_dump(mode="json")` if present, else `None`)
  - Caches the result as `self._tools_cache = [...]` AND returns the list
  - Calling `list_tools()` again refreshes the cache (always re-fetches from server)
- [ ] `MCPClient.call_tool(name, arguments)` is implemented (replacing the L2 stub):
  - Raises `MCPConnectionError("MCPClient is not connected; cannot call tool.")` if `not self._is_alive` BEFORE touching activity
  - Calls `self._touch_activity()`
  - Lazy cache population: if `self._tools_cache is None`, calls `await self.list_tools()` to populate
  - Unknown-tool guard: if `name not in {t.name for t in self._tools_cache}`, raises `MCPToolNotFoundError(name)` BEFORE wire call (the SDK call MUST NOT execute)
  - Calls `await self._session.call_tool(name, arguments)` inside `async with asyncio.timeout(self.call_timeout_seconds):`
  - Constructs `MCPToolResult(text=joined_text, raw=raw_blocks, structured=result.structuredContent, is_error=bool(result.isError))` where:
    - `joined_text` = concatenation of `block.text` for each text-type block in `result.content` (other blocks dropped — L6b adds placeholders)
    - `raw_blocks` = `[block.model_dump(mode="json") for block in result.content]` (every block, regardless of type)
    - `result.structuredContent` is passed through unchanged (already `dict | None` per SDK Pydantic shape — but if SDK returns a Pydantic object, convert via `.model_dump(mode="json")` for downstream stability)
    - `result.isError` cast to bool
  - If `result.isError` is True (or any truthy non-None value), raises `MCPCallError(tool_name=name, server_message=joined_text)` AFTER constructing `MCPToolResult` (caller never sees the dataclass — the raise happens) — this matches flight §4 contract
- [ ] **`TestListToolsAndCallTool` (11 NEW unit tests in `tests/test_mcp_client.py`)** matching the test list in Outputs above
- [ ] **`TestL6aHappyPath` (4 integration tests in `tests/test_mcp_integration.py`)** with `@pytest.mark.timeout(15)` on the 2 stdio integration tests (matches L5 pattern)
- [ ] **L2's `test_last_activity_updates_via_list_tools` REWORKED in place** to assert against the real `list_tools` body (drops `pytest.raises(NotImplementedError)`; configures `mock_session.list_tools = AsyncMock(return_value=_make_list_tools_result([_make_tool("echo")]))`; asserts `t1 > t0` after `await c.list_tools()`). Same name preserved
- [ ] `make lint` exits 0 (in-container) — no NEW ruff errors
- [ ] `make test` (in-container) — exactly **1151 passing + 1 skipped** (1136 post-L5 baseline + 11 NEW unit + 4 integration; L2 test reworked in place, NOT added)

## Verification Steps

```bash
# In container
cd /home/cprch/projects/the-one

# Targeted runs
docker compose exec the-one make test ARGS='-k TestListToolsAndCallTool -v'  # 12 pass
docker compose exec the-one make test ARGS='-k TestL6aHappyPath -v'  # 4 pass
docker compose exec the-one make test ARGS='-k TestMCPClientLifecycle -v'  # 13 still pass (regression check)

# Full suite
docker compose exec the-one make test  # 1152 + 1 skipped
docker compose exec the-one make lint
```

## Implementation Guidance

1. **Add `self._tools_cache: list[MCPTool] | None = None` to `MCPClient.__init__`** (place near the other `self._` attributes initialized at construction). Update `disconnect()` to set `self._tools_cache = None` after the existing `self._session = None` line — verifying with the existing `_capabilities`/`_protocol_version` preservation note.

2. **Replace L2's `list_tools` stub** at `the_one/mcp/client.py:258-261`:

   ```python
   async def list_tools(self) -> list[MCPTool]:
       """Return the server's tool list, mapped to MCPTool dataclasses.

       Always re-fetches from the server (no client-side cache invalidation).
       Caches the result on self._tools_cache for call_tool's unknown-tool
       guard. L6b will add input-schema validation that reads the same cache.

       Raises:
           MCPConnectionError: if the MCPClient is not connected.
       """
       if not self._is_alive or self._session is None:
           raise MCPConnectionError(
               "MCPClient is not connected; cannot list tools."
           )
       self._touch_activity()
       async with asyncio.timeout(self.timeout_seconds):
           result = await self._session.list_tools()

       tools: list[MCPTool] = []
       for tool in result.tools:
           annotations = (
               tool.annotations.model_dump(mode="json")
               if tool.annotations is not None
               else None
           )
           tools.append(
               MCPTool(
                   name=tool.name,
                   description=tool.description or "",
                   input_schema=tool.inputSchema or {},
                   output_schema=tool.outputSchema,
                   annotations=annotations,
               )
           )

       self._tools_cache = tools
       return tools
   ```

   **Note**: `self._session` is the L2 attribute; type-annotated as `"ClientSession" | None` in the TYPE_CHECKING block.

3. **Replace L2's `call_tool` stub** at `the_one/mcp/client.py:263-266`:

   ```python
   async def call_tool(
       self, name: str, arguments: dict[str, Any]
   ) -> MCPToolResult:
       """Call a tool on the server and return the result.

       Lazy-populates self._tools_cache if needed (so unknown-tool detection
       works on first call). Raises MCPToolNotFoundError BEFORE wire call if
       the tool name isn't in the cache. Raises MCPCallError if the server
       returns isError=True. Other error-path translation lands in L6b.

       Raises:
           MCPConnectionError: if the MCPClient is not connected.
           MCPToolNotFoundError: if name isn't in the server's tool list.
           MCPCallError: if the server returned isError=True.
       """
       if not self._is_alive or self._session is None:
           raise MCPConnectionError(
               "MCPClient is not connected; cannot call tool."
           )
       self._touch_activity()

       # Lazy-populate the tool cache for unknown-tool detection
       if self._tools_cache is None:
           await self.list_tools()

       known_names = {t.name for t in self._tools_cache or []}
       if name not in known_names:
           raise MCPToolNotFoundError(name)

       async with asyncio.timeout(self.call_timeout_seconds):
           result = await self._session.call_tool(name, arguments)

       # Flatten text-type content blocks; non-text blocks land in L6b
       joined_text_parts: list[str] = []
       raw_blocks: list[dict[str, Any]] = []
       for block in result.content:
           raw_blocks.append(block.model_dump(mode="json"))
           # Text blocks have a `.text` attribute (SDK's TextContent type)
           if getattr(block, "type", None) == "text":
               joined_text_parts.append(block.text)
       joined_text = "".join(joined_text_parts)

       # SDK 1.27.0 typing: structuredContent is dict[str, Any] | None;
       # isError is bool with default False. Pass-through is sufficient.
       structured = result.structuredContent
       is_error = bool(result.isError)

       tool_result = MCPToolResult(
           text=joined_text,
           raw=raw_blocks,
           structured=structured,
           is_error=is_error,
       )

       if is_error:
           raise MCPCallError(tool_name=name, server_message=joined_text)

       return tool_result
   ```

4. **`MCPCallError(tool_name, server_message)`** — verified at L6a design review: L1's `errors.py:58-64` has positional-or-keyword signature. Use keyword-form for clarity (`MCPCallError(tool_name=name, server_message=joined_text)`).

   **Lazy-cache timeout split**: the `await self.list_tools()` lazy-populate inside `call_tool` runs OUTSIDE `asyncio.timeout(self.call_timeout_seconds)` — `list_tools` has its own internal `asyncio.timeout(self.timeout_seconds)`. So a slow server taking >30s on `list_tools` raises (eventually as `MCPConnectionError` in L6b) before `call_tool`'s 60s window even starts. Do NOT wrap both under a single `call_timeout_seconds`. This is intentional — the 30s budget for `list_tools` is its own SLA.

5. **Add unit tests in `tests/test_mcp_client.py`** — extend `TestMCPClientLifecycle`'s mock-session pattern. The mock pattern from L2 (`patch_transport`, `mock_session`) is reused; tests directly access `mock_session.list_tools` and `mock_session.call_tool` to set return values:

   ```python
   from unittest.mock import AsyncMock, MagicMock

   def _make_tool(name: str, description: str = "", input_schema: dict | None = None) -> MagicMock:
       """Build a mock SDK Tool with model_dump'able fields."""
       tool = MagicMock()
       tool.name = name
       tool.description = description
       tool.inputSchema = input_schema or {}
       tool.outputSchema = None
       tool.annotations = None
       return tool


   def _make_list_tools_result(tools: list[MagicMock]) -> MagicMock:
       result = MagicMock()
       result.tools = tools
       return result


   def _make_text_content(text: str) -> MagicMock:
       block = MagicMock()
       block.type = "text"
       block.text = text
       block.model_dump = MagicMock(return_value={"type": "text", "text": text})
       return block


   def _make_call_tool_result(
       *,
       content: list[MagicMock],
       structured: dict | None = None,
       is_error: bool = False,
   ) -> MagicMock:
       result = MagicMock()
       result.content = content
       result.structuredContent = structured
       result.isError = is_error
       return result


   class TestListToolsAndCallTool:
       async def test_list_tools_returns_mapped_dataclasses(
           self, patch_transport, mock_session
       ) -> None:
           patch_transport(mock_session)
           mock_session.list_tools = AsyncMock(
               return_value=_make_list_tools_result([
                   _make_tool("echo", "Echoes input", {"type": "object"}),
                   _make_tool("add", "Adds two ints", {"type": "object"}),
               ])
           )
           c = MCPClient(_stdio_source())
           await c.connect()
           tools = await c.list_tools()
           await c.disconnect()

           assert len(tools) == 2
           assert tools[0].name == "echo"
           assert tools[0].description == "Echoes input"
           assert tools[0].input_schema == {"type": "object"}
           assert tools[0].output_schema is None
           assert tools[0].annotations is None
           # Frozen dataclass:
           with pytest.raises(dataclasses.FrozenInstanceError):
               tools[0].name = "x"

       async def test_list_tools_raises_when_not_connected(self) -> None:
           c = MCPClient(_stdio_source())
           with pytest.raises(MCPConnectionError, match="not connected"):
               await c.list_tools()

       async def test_call_tool_text_only_result(
           self, patch_transport, mock_session
       ) -> None:
           patch_transport(mock_session)
           mock_session.list_tools = AsyncMock(
               return_value=_make_list_tools_result([_make_tool("echo")])
           )
           mock_session.call_tool = AsyncMock(
               return_value=_make_call_tool_result(
                   content=[_make_text_content("hi")],
                   structured=None,
                   is_error=False,
               )
           )
           c = MCPClient(_stdio_source())
           await c.connect()
           result = await c.call_tool("echo", {"message": "hi"})
           await c.disconnect()

           assert result.text == "hi"
           assert result.raw == [{"type": "text", "text": "hi"}]
           assert result.structured is None
           assert result.is_error is False

       async def test_call_tool_unknown_tool_raises_before_wire_call(
           self, patch_transport, mock_session
       ) -> None:
           patch_transport(mock_session)
           mock_session.list_tools = AsyncMock(
               return_value=_make_list_tools_result([_make_tool("echo")])
           )
           mock_session.call_tool = AsyncMock()  # spy — should not be called
           c = MCPClient(_stdio_source())
           await c.connect()
           with pytest.raises(MCPToolNotFoundError, match="nonexistent"):
               await c.call_tool("nonexistent", {})
           mock_session.call_tool.assert_not_called()
           await c.disconnect()

       async def test_call_tool_iserror_raises_mcpcallerror(
           self, patch_transport, mock_session
       ) -> None:
           patch_transport(mock_session)
           mock_session.list_tools = AsyncMock(
               return_value=_make_list_tools_result([_make_tool("echo")])
           )
           mock_session.call_tool = AsyncMock(
               return_value=_make_call_tool_result(
                   content=[_make_text_content("server failed")],
                   is_error=True,
               )
           )
           c = MCPClient(_stdio_source())
           await c.connect()
           with pytest.raises(MCPCallError, match="server failed"):
               await c.call_tool("echo", {})
           await c.disconnect()

       # ... 7 more tests for: text concatenation, structured content,
       #     lazy cache population, raises-when-not-connected on call_tool,
       #     disconnect clears cache, list_tools always re-fetches, etc.
   ```

   Use the L2-shipped `_stdio_source()` and `patch_transport`/`mock_session` fixtures.

6. **Add integration tests in `tests/test_mcp_integration.py`** under a new `TestL6aHappyPath` class. Use `mcp_fixture_http_client` for streamable-http tests and `mcp_fixture_stdio_params` for stdio tests; `@pytest.mark.timeout(15)` on stdio tests:

   ```python
   class TestL6aHappyPath:
       async def test_list_tools_streamable_http(
           self, mcp_fixture_http_client, monkeypatch
       ) -> None:
           client_httpx, url = mcp_fixture_http_client
           monkeypatch.setattr(
               "the_one.mcp.transports.streamable_http._test_http_client_override",
               client_httpx,
           )
           source = MCPSource(
               id="src-4", name="hello", type="streamable-http",
               config={"url": url, "headers": {}}, secrets={},
           )
           c = MCPClient(source)
           await c.connect()
           try:
               tools = await c.list_tools()
               assert len(tools) == 2
               assert {t.name for t in tools} == {"echo", "add"}
               for t in tools:
                   assert t.input_schema  # non-empty dict
           finally:
               await c.disconnect()

       async def test_call_tool_echo_streamable_http(
           self, mcp_fixture_http_client, monkeypatch
       ) -> None:
           # ... same fixture setup ...
           c = MCPClient(source)
           await c.connect()
           try:
               result = await c.call_tool("echo", {"message": "hello"})
               assert result.text == "hello"
               assert result.is_error is False
           finally:
               await c.disconnect()

       @pytest.mark.timeout(15)
       async def test_list_tools_stdio(self, mcp_fixture_stdio_params) -> None:
           # ... build MCPSource from fixture dict (mirrors TestL5Stdio test #1 setup) ...
           c = MCPClient(source)
           await c.connect()
           try:
               tools = await c.list_tools()
               assert {t.name for t in tools} == {"echo", "add"}
           finally:
               await c.disconnect()

       @pytest.mark.timeout(15)
       async def test_call_tool_add_stdio(self, mcp_fixture_stdio_params) -> None:
           # ... build MCPSource ...
           c = MCPClient(source)
           await c.connect()
           try:
               result = await c.call_tool("add", {"a": 2, "b": 3})
               # FastMCP wraps non-dict returns under structuredContent.result
               assert result.structured == {"result": 5}
               # Text representation of int return — SDK renders as "5"
               assert result.text == "5"
               assert result.is_error is False
           finally:
               await c.disconnect()
   ```

   The `text == "5"` assertion in test #4 is a flight-design-time projection (per L4's design notes: "FastMCP wraps non-dict returns under `result` key... `result.content[0].text == "3"` — str-coerced from int return"). If the actual SDK shape returns something different (e.g., `"5\n"` or empty text), the implementer must adapt the assertion AND document the actual shape in the flight log.

7. **Run the in-container test cycle** — verify each new test in isolation, then full suite:
   ```bash
   docker compose exec the-one make test ARGS='-k TestListToolsAndCallTool -v'
   docker compose exec the-one make test ARGS='-k TestL6aHappyPath -v'
   docker compose exec the-one make test ARGS='-k TestMCPClientLifecycle -v'  # regression check
   docker compose exec the-one make test  # 1152 + 1 skipped
   docker compose exec the-one make lint
   ```

8. **Update flight log L6a entry** in `## Leg Progress / ### L6a: list_tools and call_tool happy path` covering: status (landed); changes (list_tools/call_tool reimplementation, _tools_cache attribute, disconnect clearing cache); notes (any deviations on SDK Tool/CallToolResult shapes; whether `add` tool's `text` field actually renders as "5" or something else); test count before/after (1136 → 1152); lint status.

## Edge Cases

- **`tool.description` may be None**: SDK's `Tool.description: str | None`. The leg uses `tool.description or ""` to coerce to empty string (matches `MCPTool.description: str` non-optional shape).

- **`tool.inputSchema` may be None or {}**: SDK's `Tool.inputSchema: dict[str, Any] | None`. The leg uses `tool.inputSchema or {}` to coerce.

- **`tool.annotations` is a Pydantic object (`ToolAnnotations`)**, NOT a plain dict: the SDK exposes typed annotations like `readOnlyHint`, `destructiveHint`, etc. The leg's mapping calls `.model_dump(mode="json")` on it (returns a plain JSON-serializable dict) so `MCPTool.annotations: dict | None` holds a stable shape.

- **`result.content` blocks may include non-text types** (image, audio, resource_link, resource): L6a's `joined_text` only includes text-type blocks. Non-text blocks ARE captured in `raw` (via `model_dump`) so L6b doesn't need to refetch. **L6a's `text` field is intentionally lossy for non-text blocks** — L6b adds the placeholder rendering.

- **`result.structuredContent` shape**: SDK type is `dict[str, Any] | None`. FastMCP wraps non-dict returns: `add(2, 3) → 5` becomes `structuredContent={"result": 5}`. The leg's `structured` field passes this through.

- **`result.isError` is `bool` with default `False`** (SDK 1.27.0 typing — verified at design review). No None-handling needed; `bool(result.isError)` is sufficient.

- **`result.structuredContent` is `dict | None`** (SDK 1.27.0 typing — verified at design review). Pass-through to `MCPToolResult.structured` without `model_dump` defense.

- **Lazy cache population during `call_tool`**: if the operator never explicitly calls `list_tools()` first, `call_tool` populates the cache. This adds one wire round-trip on the first `call_tool` call. F4's warm pool will mitigate this — once a connection is warm, the cache survives across multiple calls.

- **`disconnect()` clears `_tools_cache`**: a re-connect rebuilds fresh. Reasoning: tools may have changed between sessions (e.g., FastMCP fixture's tool registration is per-instance, but real MCP servers can dynamically register tools). If the cache survives across disconnect/reconnect, stale tools could leak.

- **`asyncio.timeout` cancellation behavior**: per L2's `connect()` pattern, on timeout the task is cancelled and `asyncio.TimeoutError` propagates. L6a does NOT translate this — L6b adds the translation to `MCPConnectionError` with operation-specific messaging.

- **`MCPConnectionError` raises BEFORE `_touch_activity()`**: per the leg's contract, errors-before-call don't update `last_activity`. This matches L2's pattern for `negotiated_protocol_version` / `server_capabilities` — they raise before doing anything.

- **F4-pool compat**: `_tools_cache` is per-MCPClient-instance. F4's pool holds one MCPClient per (source, agent) — each has its own cache. Cache invalidation on disconnect aligns with F4's reaper-evicts-and-respawns pattern.

- **Test #2 wording vs test #11**: test #2 (`test_list_tools_caches_result`) asserts cache is per-call refresh; test #11 asserts disconnect clears the cache. These are NOT contradictory — explicit `list_tools()` always re-fetches; `disconnect` resets the cache state.

- **L2's `test_last_activity_updates_via_list_tools`**: this test was written against L2's stub (which raises `NotImplementedError` AFTER `_touch_activity`). With L6a's real implementation, the test should still pass — it monkeypatches `mock_session.list_tools` to return a mocked result, AND `_touch_activity` still fires before the SDK call. **Verify this test is unchanged AND passes** in L6a. If it breaks (e.g., due to assertion mismatch because the L2 mock didn't return a valid `result.tools`), update the L2 mock setup OR the test — but this is not new test work, just regression preservation.

## Files Affected

- `the_one/mcp/client.py` — `__init__` adds `_tools_cache`; `disconnect` clears it; `list_tools` and `call_tool` reimplemented (replacing L2 stubs)
- `tests/test_mcp_client.py` — extend with `TestListToolsAndCallTool` (12 unit tests + helpers `_make_tool`, `_make_list_tools_result`, `_make_text_content`, `_make_call_tool_result`)
- `tests/test_mcp_integration.py` — extend with `TestL6aHappyPath` (4 integration tests using L4/L5 fixtures)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — exactly 1151 passing + 1 skipped (1136 baseline post-L5 + 11 NEW unit + 4 integration; L2's `test_last_activity_updates_via_list_tools` reworked in place — counted in baseline, not added)
- [ ] L2's `test_last_activity_updates_via_list_tools` REWORKED to assert against real `list_tools` body (drops `pytest.raises(NotImplementedError)`)
- [ ] `make lint` clean (no NEW ruff errors) — run inside the container
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress / ### L6a: list_tools and call_tool happy path`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end

## Citation Audit

5 SDK + repo citations verified at leg-design time:

1. `the_one/mcp/client.py:258-266` — verified L2 stubs raise `NotImplementedError("L6a implements list_tools")` and `("L6a implements call_tool")`. L6a replaces both wholesale
2. `the_one/mcp/types.py::MCPTool` and `MCPToolResult` — verified L1-shipped frozen dataclass shapes with the 5/4 fields per flight §4 / §5b
3. `the_one/mcp/errors.py::MCPCallError(tool_name, server_message)` and `MCPToolNotFoundError(tool_name)` — verified L1-shipped error classes with constructor arity matching flight §3
4. `mcp.types.ListToolsResult.tools: list[Tool]` and `Tool` fields `name/description/inputSchema/outputSchema/annotations/...` — verified at design time via in-container probe; the leg's mapping covers the F2-relevant subset
5. `mcp.types.CallToolResult` fields `meta/content/structuredContent/isError` — verified at design time; `content: list[ContentBlock]` is the type with `.type` discriminator

All citations clean — no drift.

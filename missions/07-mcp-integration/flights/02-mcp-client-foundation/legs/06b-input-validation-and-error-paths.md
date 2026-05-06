# Leg: 06b-input-validation-and-error-paths

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Complete `call_tool` with input validation against the tool's JSON Schema (raising `MCPArgumentError`), placeholder rendering for non-text content blocks (image, audio, resource_link, resource), and the full SDK-error-translation matrix (timeout, transport, server-side, elicitation propagation). Closes the F2 client foundation. After L6b, F3+ flights can build on `MCPClient` end-to-end.

## Context

- **Flight design** §3 (error hierarchy: `MCPArgumentError`, `MCPConnectionError`, `MCPCallError`, plus `UrlElicitationRequiredError` propagation); §4 (non-text placeholder rendering: `"[image: 1234 bytes, mime=image/png]"`, `"[audio: 5678 bytes]"`, `"[resource_link: file:///x.txt]"`, `"[resource: <uri>]"`); §5 (input validation via jsonschema, tools without `inputSchema` skip validation)
- **L6a's `call_tool` body** is in place (`the_one/mcp/client.py::call_tool`): builds `MCPToolResult`, raises `MCPCallError` on `isError=True`. L6b extends:
  1. **Input validation step** — BEFORE the SDK call: if the cached tool's `input_schema` is non-empty, validate `arguments` via `jsonschema.validate` and raise `MCPArgumentError(tool_name, str(validation_error))` on mismatch
  2. **Non-text content rendering** — currently L6a's `joined_text` only includes text-type blocks; L6b appends placeholder strings for non-text blocks (preserving order with text blocks)
  3. **SDK error translation matrix** — currently `asyncio.TimeoutError` and `mcp.shared.exceptions.McpError` and `httpx.HTTPError` etc. propagate as-is; L6b wraps them
- **`mcp==1.27.0` direct dependency `jsonschema>=4.20.0`** confirmed at L1 design; verified at runtime as `jsonschema 4.26.0` in container. `from jsonschema import validate, ValidationError` is the standard import
- **FastMCP fixture's `echo` and `add` tools** have populated `inputSchema` (e.g. `{"properties": {"message": {"title": "Message", "type": "string"}}, "required": ["message"], "title": "echoArguments", "type": "object"}`). So L6b's integration tests can exercise validation against the real schema
- **SDK content-block shapes** (verified at L6b design time via in-container probe):
  - `ImageContent(type, data, mimeType, annotations, meta)` — `data` is base64 string; placeholder uses `len(data)` for size hint
  - `AudioContent(type, data, mimeType, annotations, meta)` — same shape
  - `ResourceLink(name, title, uri, description, mimeType, size, icons, annotations, meta, type)` — `uri` is the placeholder content
  - `EmbeddedResource(type, resource, annotations, meta)` — `resource` is a `TextResourceContents | BlobResourceContents` with its own `uri`
- **`MCPCallError(tool_name, server_message)`** signature confirmed L6a — same constructor used by L6b's `MCPCallError` raise on `mcp.shared.exceptions.McpError` translation paths
- **Error-translation matrix locked at L6b** (verified at L6b design review: `UrlElicitationRequiredError` IS a subclass of `McpError` — `issubclass(UrlElicitationRequiredError, McpError) == True`. The wrapper MUST re-raise it BEFORE the `except McpError` clause or it will be silently translated to `MCPCallError`):
  | SDK error class | F2 wrapper class | Where |
  |---|---|---|
  | `asyncio.TimeoutError` (handshake / list_tools timeout) | `MCPConnectionError` | `connect()` already wraps via L2; `list_tools` adds wrap |
  | `asyncio.TimeoutError` (call_tool timeout) | `MCPConnectionError` | `call_tool` adds wrap with operation-specific message |
  | `UrlElicitationRequiredError` (subclass of McpError — propagate FIRST) | passes through unchanged | both `list_tools` and `call_tool` add explicit `except UrlElicitationRequiredError: raise` BEFORE `except McpError` |
  | `mcp.shared.exceptions.McpError` (in `call_tool`) | `MCPCallError` | `call_tool` adds wrap |
  | `mcp.shared.exceptions.McpError` (in `list_tools`) | `MCPConnectionError` | `list_tools` adds wrap |
  | `httpx.HTTPError` / `anyio.ClosedResourceError` | `MCPConnectionError` | both methods add wrap |
- **L2's `connect()` body already translates SDK `RuntimeError` → `MCPVersionMismatch`**. L6b doesn't re-touch `connect()`; it only extends `list_tools`/`call_tool`
- **L6a's `_touch_activity()` ordering**: called AFTER the alive-check, BEFORE any wire call. L6b preserves this ordering — input validation also happens AFTER `_touch_activity()` so `last_activity` updates even on validation failures (a failed validation is still operator activity)
- **Test count target**: post-L6a baseline = 1151 + 1 skipped. L6b adds 18 new tests:
  - 5 unit tests for input validation (valid args / type mismatch / missing required / extra unknown / no-schema-skip)
  - 5 unit tests for non-text content rendering (image, audio, resource_link, resource — one each — PLUS `test_mixed_text_and_image_concatenation` for order-preservation across mixed text/non-text blocks)
  - 6 unit tests for error translation (timeout in list_tools, timeout in call_tool, McpError in call_tool, httpx error, anyio.ClosedResourceError, AND `test_url_elicitation_propagates_through_call_tool_wrapper`)
  - 2 integration tests: `test_call_tool_invalid_args_via_streamable_http` and `test_call_tool_invalid_args_via_stdio` (both exercise jsonschema validation against the real fixture)
  - **Total: 1151 + 18 = 1169 passing + 1 skipped**

## Inputs

What exists before this leg runs:
- L1+L2+L3+L4+L5+L6a outputs: full `MCPClient` lifecycle including real `list_tools`/`call_tool`; `MCPCallError`/`MCPArgumentError`/`MCPConnectionError`/`MCPToolNotFoundError` error classes; integration test fixtures
- L6a's `call_tool` body (replaces text-only blocks; raises `MCPCallError` on `isError=True`; raises `MCPToolNotFoundError` before wire call)
- L6a's `_tools_cache` populated for input-validation lookup
- jsonschema 4.26.0 (transitive direct dep of mcp 1.27.0) available in container
- Test helpers `_make_tool`, `_make_call_tool_result`, `_make_text_content`, `_make_list_tools_result`, `patch_transport`, `mock_session`, `_stdio_source` — all from L1/L2/L4/L5/L6a in `tests/test_mcp_client.py`

## Outputs

What exists after this leg completes:
- `the_one/mcp/client.py::call_tool` — extended with:
  1. **Input validation step** — between unknown-tool guard and `asyncio.timeout(...)` wrap: if cached tool's `input_schema` is non-empty (truthy dict), call `jsonschema.validate(arguments, schema)` inside a `try/except`; on `jsonschema.ValidationError`, raise `MCPArgumentError(tool_name=name, validation_message=str(e))`. Tools without inputSchema (or with `{}`) skip validation
  2. **Non-text placeholder rendering** — extend the content-block loop to append placeholder strings for non-text types in `joined_text_parts` so `MCPToolResult.text` reflects ALL blocks (text + non-text placeholders) in order:
     - `image` → `f"[image: {len(block.data)} bytes, mime={block.mimeType}]"`
     - `audio` → `f"[audio: {len(block.data)} bytes, mime={block.mimeType}]"`
     - `resource_link` → `f"[resource_link: {block.uri}]"`
     - `resource` → `f"[resource: {block.resource.uri}]"`
     - Unknown types → silently dropped (forward-compat — future SDK content-block types don't break L6b)
  3. **SDK error translation** wrapped around the `asyncio.timeout(...)` block:
     - `except asyncio.TimeoutError`: raise `MCPConnectionError(f"MCP tool call exceeded {self.call_timeout_seconds} seconds")`
     - `except mcp.shared.exceptions.McpError as e`: raise `MCPCallError(tool_name=name, server_message=str(e))`
     - `except (httpx.HTTPError, anyio.ClosedResourceError) as e`: raise `MCPConnectionError(f"MCP transport error during call_tool: {type(e).__name__}: {e}")`
     - `mcp.shared.exceptions.UrlElicitationRequiredError` propagates AS-IS (NOT caught by the above clauses since it's a separate class — but explicit pass-through documented)
- `the_one/mcp/client.py::list_tools` — extended with parallel SDK error translation:
  - `except asyncio.TimeoutError`: raise `MCPConnectionError(f"MCP list_tools exceeded {self.timeout_seconds} seconds")`
  - `except mcp.shared.exceptions.McpError as e`: raise `MCPConnectionError(f"MCP list_tools failed: {e}")`
  - `except (httpx.HTTPError, anyio.ClosedResourceError) as e`: raise `MCPConnectionError(f"MCP transport error during list_tools: {type(e).__name__}: {e}")`
- `tests/test_mcp_client.py` extended with:
  - `TestCallToolInputValidation` — 5 unit tests (jsonschema integration)
  - `TestCallToolContentBlockRendering` — 4 unit tests (image, audio, resource_link, resource placeholders)
  - `TestCallToolErrorTranslation` — 5 unit tests (timeout in list_tools, timeout in call_tool, McpError in call_tool, httpx error, anyio.ClosedResourceError)
- `tests/test_mcp_integration.py` extended with:
  - `TestL6bInputValidationIntegration` — 2 integration tests:
    1. `test_call_tool_invalid_args_via_streamable_http` — `call_tool("echo", {})` (missing required `message`) raises `MCPArgumentError`; mock session's `call_tool` not called
    2. `test_call_tool_invalid_args_via_stdio` (`@pytest.mark.timeout(15)`) — same shape via stdio
- Test count after L6b: **exactly 1167 passing + 1 skipped** (1151 baseline post-L6a + 5 + 4 + 5 + 2 = 16 new)
- `make lint` clean (no NEW ruff errors)

## Acceptance Criteria

- [ ] `the_one/mcp/client.py::call_tool` extended with input-validation step:
  - After the unknown-tool guard (line ~340), find the cached tool's schema: `tool_meta = next(t for t in self._tools_cache if t.name == name)`
  - If `tool_meta.input_schema` is truthy (non-empty dict): wrap in `try/except`:
    ```python
    from jsonschema import ValidationError, validate as jsonschema_validate
    try:
        jsonschema_validate(arguments, tool_meta.input_schema)
    except ValidationError as e:
        raise MCPArgumentError(tool_name=name, validation_message=str(e)) from None
    ```
  - Imports go at the top of `client.py` (NOT lazy) — `jsonschema` is already a transitive dep, no install needed
  - Tools with `input_schema == {}` skip validation (matches SDK permissiveness per flight §5)
  - Validation runs INSIDE the timeout window? NO — validation is fast pure-Python; runs OUTSIDE `asyncio.timeout(self.call_timeout_seconds)` (no point timing it). Place validation BEFORE the `async with asyncio.timeout(...)` block
- [ ] `the_one/mcp/client.py::call_tool` extended with non-text content-block rendering:
  - In the existing `for block in result.content:` loop (currently appends to `joined_text_parts` ONLY when `block.type == "text"`), add `elif` branches for non-text types:
    ```python
    elif block_type == "image":
        joined_text_parts.append(f"[image: {len(block.data)} bytes, mime={block.mimeType}]")
    elif block_type == "audio":
        joined_text_parts.append(f"[audio: {len(block.data)} bytes, mime={block.mimeType}]")
    elif block_type == "resource_link":
        joined_text_parts.append(f"[resource_link: {block.uri}]")
    elif block_type == "resource":
        # EmbeddedResource has .resource which has .uri (TextResourceContents or BlobResourceContents)
        joined_text_parts.append(f"[resource: {block.resource.uri}]")
    # Unknown block types: silently dropped (forward-compat)
    ```
  - The `raw_blocks` accumulator is unchanged (already captures every block via `block.model_dump(mode="json")`)
- [ ] `the_one/mcp/client.py::call_tool` wrapped with SDK-error translation:
  - The existing `async with asyncio.timeout(self.call_timeout_seconds):` block wrapped in:
    ```python
    try:
        async with asyncio.timeout(self.call_timeout_seconds):
            result = await self._session.call_tool(name, arguments)
    except asyncio.TimeoutError:
        raise MCPConnectionError(
            f"MCP tool call exceeded {self.call_timeout_seconds} seconds"
        ) from None
    except UrlElicitationRequiredError:
        # MUST be ordered BEFORE `except McpError` — UrlElicitationRequiredError
        # IS a subclass of McpError (verified at L6b design review:
        # `issubclass(UrlElicitationRequiredError, McpError) == True`).
        # Without this clause it would be silently swallowed into MCPCallError,
        # breaking F3+'s ability to surface URL elicitation prompts.
        raise
    except McpError as e:
        raise MCPCallError(tool_name=name, server_message=str(e)) from None
    except (httpx.HTTPError, anyio.ClosedResourceError) as e:
        raise MCPConnectionError(
            f"MCP transport error during call_tool: {type(e).__name__}: {e}"
        ) from None
    ```
  - Imports at top of `client.py` (third-party block AFTER stdlib, BEFORE the_one imports — ruff isort enforces this grouping):
    ```python
    import anyio
    import httpx
    from jsonschema import ValidationError
    from jsonschema import validate as jsonschema_validate
    from mcp.shared.exceptions import McpError, UrlElicitationRequiredError
    ```
  - The result-rendering loop runs AFTER the try/except (uses `result` variable populated by the SDK call)
- [ ] `the_one/mcp/client.py::list_tools` wrapped with parallel SDK-error translation:
  - Same try/except pattern around the existing `async with asyncio.timeout(self.timeout_seconds):` block, but error messages reflect "list_tools" operation:
    - `MCPConnectionError("MCP list_tools exceeded {N} seconds")` for `asyncio.TimeoutError`
    - `except UrlElicitationRequiredError: raise` BEFORE the `except McpError` clause (same subclass-ordering reason as call_tool)
    - `MCPConnectionError("MCP list_tools failed: {e}")` for McpError (NOT MCPCallError — list_tools isn't a tool call)
    - `MCPConnectionError("MCP transport error during list_tools: {type}: {e}")` for httpx/anyio
- [ ] **`TestCallToolInputValidation` (5 unit tests in `tests/test_mcp_client.py`)**:
  1. `test_valid_args_pass_validation` — tool with schema `{"type": "object", "properties": {"x": {"type": "string"}}}`; `call_tool("t", {"x": "ok"})` succeeds; mock session `call_tool` IS called
  2. `test_type_mismatch_raises_argument_error` — same schema; `call_tool("t", {"x": 42})` raises `MCPArgumentError` (`x` not a string); mock session `call_tool` NOT called (`mock.assert_not_called()`)
  3. `test_missing_required_field_raises_argument_error` — schema `{"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}`; `call_tool("t", {})` raises `MCPArgumentError`; mock session `call_tool` NOT called
  4. `test_extra_unknown_field_passes_validation` — same schema (no `additionalProperties: false`); `call_tool("t", {"x": "ok", "extra": "ignored"})` succeeds (jsonschema by default permits additional properties)
  5. `test_no_schema_skips_validation` — tool with `input_schema = {}`; `call_tool("t", {"any": "thing"})` succeeds; mock session `call_tool` IS called (validation step bypassed)
- [ ] **`TestCallToolContentBlockRendering` (5 unit tests)**:
  1. `test_image_block_placeholder` — mock returns `[ImageContent(data="abc", mimeType="image/png")]`; `result.text == "[image: 3 bytes, mime=image/png]"`
  2. `test_audio_block_placeholder` — mock returns `[AudioContent(data="xyz", mimeType="audio/wav")]`; `result.text == "[audio: 3 bytes, mime=audio/wav]"`
  3. `test_resource_link_block_placeholder` — mock returns `[ResourceLink(name="x", uri="file:///x.txt")]`; `result.text == "[resource_link: file:///x.txt]"`
  4. `test_embedded_resource_block_placeholder` — mock returns `[EmbeddedResource(resource=TextResourceContents(uri="resource://r", text="..."))]`; `result.text == "[resource: resource://r]"`
  5. `test_mixed_text_and_image_concatenation` — mock returns `[text("first "), image, text(" last")]`; `result.text == "first [image: 3 bytes, mime=image/png] last"` (order preserved across mixed text/non-text — the most likely regression vector for the rendering loop)

   Verify in mock setup that the mocked `block.model_dump(mode="json")` returns a representative dict (so `raw` field carries through). `_make_image_content` / `_make_audio_content` / `_make_resource_link_content` / `_make_embedded_resource_content` helpers added near L6a's existing `_make_text_content`
- [ ] **`TestCallToolErrorTranslation` (6 unit tests)**:
  1. `test_call_tool_timeout_raises_connection_error` — mock `session.call_tool = AsyncMock(side_effect=asyncio.TimeoutError())`; raises `MCPConnectionError` matching "exceeded"
  2. `test_list_tools_timeout_raises_connection_error` — mock `session.list_tools = AsyncMock(side_effect=asyncio.TimeoutError())`; raises `MCPConnectionError` matching "list_tools exceeded"
  3. `test_call_tool_mcp_error_raises_mcp_call_error` — mock `session.call_tool = AsyncMock(side_effect=McpError(ErrorData(code=-32600, message="boom")))`; raises `MCPCallError` with `server_message == "boom"` (verified at L6b design review: `McpError(ErrorData(...))` constructs cleanly; `str(e) == "boom"`)
  4. `test_call_tool_httpx_error_raises_connection_error` — mock `session.call_tool = AsyncMock(side_effect=httpx.HTTPError("boom"))`; raises `MCPConnectionError` matching "transport error"
  5. `test_call_tool_closed_resource_raises_connection_error` — mock `session.call_tool = AsyncMock(side_effect=anyio.ClosedResourceError())`; raises `MCPConnectionError` matching "transport error"
  6. `test_url_elicitation_propagates_through_call_tool_wrapper` — mock `session.call_tool = AsyncMock(side_effect=UrlElicitationRequiredError(<minimal-args>))`; assert `pytest.raises(UrlElicitationRequiredError)` (NOT `MCPCallError`!) — verifies the explicit `except UrlElicitationRequiredError: raise` clause is in place AND ordered before `except McpError`. Mechanical guarantee against accidental regression of the subclass-ordering invariant
  
  For test #3: `McpError(ErrorData(code=-32600, message="boom"))` constructs cleanly per design-review probe. For test #6: `UrlElicitationRequiredError`'s constructor signature should be probed in-container — likely takes `url: str` per its name; if the constructor needs more, use the actual SDK shape. The test pattern is the critical bit: the side_effect raises, F2's wrapper either propagates it (correct, what we want) or swallows it (would-be-bug-if-missing-the-explicit-clause)
- [ ] **`TestL6bInputValidationIntegration` (2 integration tests)**:
  1. `test_call_tool_invalid_args_via_streamable_http(mcp_fixture_http_client, monkeypatch)`:
     - Setup: same as L6a's `TestL6aHappyPath` test #2 (streamable-http, `src-6`)
     - `connect()` → `list_tools()` (populates cache) → `call_tool("echo", {})` (missing required `message`) raises `MCPArgumentError` matching "message" or "required"
  2. `test_call_tool_invalid_args_via_stdio(mcp_fixture_stdio_params, @pytest.mark.timeout(15))`:
     - Setup: same as L6a's stdio test (`src-stdio-6`)
     - Same assertion: `call_tool("echo", {})` raises `MCPArgumentError`
- [ ] `tests/test_mcp_integration.py` import block extended to include `MCPArgumentError`: `from the_one.mcp.errors import MCPConnectionError, MCPArgumentError`
- [ ] Lint exits 0 (in-container `ruff check the_one/ tests/`) — no NEW ruff errors. Watch for `F811` if helper names collide with L6a; `I001` if import grouping mis-ordered
- [ ] Test suite (in-container `pytest --tb=no -q`) — exactly **1169 passing + 1 skipped** (1151 baseline post-L6a + 18 new tests: 5 input-val + 5 content-rendering + 6 error-translation + 2 integration). The project doesn't have `make` in container; pytest direct is the canonical path

## Verification Steps

```bash
# In container — note: working directory is /app, no `make` — use pytest direct
docker compose exec the-one bash -c "cd /app && pytest -k TestCallToolInputValidation -v"  # 5 pass
docker compose exec the-one bash -c "cd /app && pytest -k TestCallToolContentBlockRendering -v"  # 4 pass
docker compose exec the-one bash -c "cd /app && pytest -k TestCallToolErrorTranslation -v"  # 5 pass
docker compose exec the-one bash -c "cd /app && pytest -k TestL6bInputValidationIntegration -v"  # 2 pass

# Full suite
docker compose exec the-one bash -c "cd /app && pytest --tb=no -q"  # 1167 + 1 skipped
docker compose exec the-one bash -c "cd /app && ruff check the_one/ tests/"  # clean
```

## Implementation Guidance

1. **Update top-of-file imports in `the_one/mcp/client.py`** — third-party block lands BETWEEN stdlib (re, time, asyncio, etc.) and `from the_one.db.models import MCPSource` (ruff isort enforces this grouping; merging into the stdlib group would trigger I001):
   ```python
   import anyio
   import httpx
   from jsonschema import ValidationError
   from jsonschema import validate as jsonschema_validate
   from mcp.shared.exceptions import McpError, UrlElicitationRequiredError
   ```
   NOT inside `TYPE_CHECKING` (they're runtime requirements). Note: `from jsonschema import ValidationError, validate as jsonschema_validate` (single line) is split into TWO lines by ruff isort — accept the split form upfront.

   Also extend `tests/test_mcp_integration.py` import: `from the_one.mcp.errors import MCPConnectionError, MCPArgumentError` (currently only `MCPConnectionError` is imported).

2. **Extend `call_tool` between unknown-tool guard and timeout block**:
   ```python
   # ... existing unknown-tool guard ...

   # L6b: input validation against tool's JSON Schema (skipped if empty)
   tool_meta = next(t for t in (self._tools_cache or []) if t.name == name)
   if tool_meta.input_schema:
       try:
           jsonschema_validate(arguments, tool_meta.input_schema)
       except ValidationError as e:
           raise MCPArgumentError(
               tool_name=name, validation_message=str(e)
           ) from None

   # L6b: error-translation wrap around the timeout block.
   # UrlElicitationRequiredError IS a subclass of McpError — re-raise BEFORE
   # the McpError clause or it gets silently swallowed.
   try:
       async with asyncio.timeout(self.call_timeout_seconds):
           result = await self._session.call_tool(name, arguments)
   except asyncio.TimeoutError:
       raise MCPConnectionError(
           f"MCP tool call exceeded {self.call_timeout_seconds} seconds"
       ) from None
   except UrlElicitationRequiredError:
       raise
   except McpError as e:
       raise MCPCallError(tool_name=name, server_message=str(e)) from None
   except (httpx.HTTPError, anyio.ClosedResourceError) as e:
       raise MCPConnectionError(
           f"MCP transport error during call_tool: {type(e).__name__}: {e}"
       ) from None

   # ... existing result-rendering loop (extended below) ...
   ```

3. **Extend the content-block rendering loop** in `call_tool`:
   ```python
   for block in result.content:
       raw_blocks.append(block.model_dump(mode="json"))
       block_type = getattr(block, "type", None)
       if block_type == "text":
           joined_text_parts.append(block.text)
       elif block_type == "image":
           joined_text_parts.append(
               f"[image: {len(block.data)} bytes, mime={block.mimeType}]"
           )
       elif block_type == "audio":
           joined_text_parts.append(
               f"[audio: {len(block.data)} bytes, mime={block.mimeType}]"
           )
       elif block_type == "resource_link":
           joined_text_parts.append(f"[resource_link: {block.uri}]")
       elif block_type == "resource":
           joined_text_parts.append(f"[resource: {block.resource.uri}]")
       # Unknown block types: silently dropped (forward-compat)
   ```

4. **Extend `list_tools` with parallel error translation**:
   ```python
   # Replace the existing:
   #   async with asyncio.timeout(self.timeout_seconds):
   #       result = await self._session.list_tools()
   # with (UrlElicitationRequiredError ordering same as call_tool):
   try:
       async with asyncio.timeout(self.timeout_seconds):
           result = await self._session.list_tools()
   except asyncio.TimeoutError:
       raise MCPConnectionError(
           f"MCP list_tools exceeded {self.timeout_seconds} seconds"
       ) from None
   except UrlElicitationRequiredError:
       raise
   except McpError as e:
       raise MCPConnectionError(f"MCP list_tools failed: {e}") from None
   except (httpx.HTTPError, anyio.ClosedResourceError) as e:
       raise MCPConnectionError(
           f"MCP transport error during list_tools: {type(e).__name__}: {e}"
       ) from None
   ```

5. **Add helpers to `tests/test_mcp_client.py`** (near existing L6a helpers):
   ```python
   def _make_image_content(data: str = "abc", mime: str = "image/png") -> MagicMock:
       block = MagicMock()
       block.type = "image"
       block.data = data
       block.mimeType = mime
       block.model_dump = MagicMock(return_value={
           "type": "image", "data": data, "mimeType": mime
       })
       return block

   def _make_audio_content(data: str = "xyz", mime: str = "audio/wav") -> MagicMock:
       block = MagicMock()
       block.type = "audio"
       block.data = data
       block.mimeType = mime
       block.model_dump = MagicMock(return_value={
           "type": "audio", "data": data, "mimeType": mime
       })
       return block

   def _make_resource_link_content(uri: str = "file:///x.txt") -> MagicMock:
       block = MagicMock()
       block.type = "resource_link"
       block.uri = uri
       block.model_dump = MagicMock(return_value={
           "type": "resource_link", "uri": uri
       })
       return block

   def _make_embedded_resource_content(uri: str = "resource://r") -> MagicMock:
       block = MagicMock()
       block.type = "resource"
       inner = MagicMock()
       inner.uri = uri
       block.resource = inner
       block.model_dump = MagicMock(return_value={
           "type": "resource", "resource": {"uri": uri}
       })
       return block
   ```

6. **Add unit tests** under three new classes (`TestCallToolInputValidation`, `TestCallToolContentBlockRendering`, `TestCallToolErrorTranslation`) following the L6a `patch_transport`/`mock_session` pattern. Each test:
   - Calls `patch_transport(mock_session)` to wire the mocked session
   - Configures `mock_session.list_tools` to return a tool with the relevant `input_schema`
   - Configures `mock_session.call_tool` either to return a `_make_call_tool_result(...)` OR `side_effect=...` for error-path tests
   - Connects MCPClient, exercises the path, asserts the wrapped error or `MCPToolResult` shape

   Example for `test_type_mismatch_raises_argument_error`:
   ```python
   async def test_type_mismatch_raises_argument_error(
       self, patch_transport, mock_session
   ) -> None:
       patch_transport(mock_session)
       mock_session.list_tools = AsyncMock(
           return_value=_make_list_tools_result([
               _make_tool("t", "", {
                   "type": "object",
                   "properties": {"x": {"type": "string"}}
               })
           ])
       )
       mock_session.call_tool = AsyncMock()  # spy — should not be called
       c = MCPClient(_stdio_source())
       await c.connect()
       try:
           with pytest.raises(MCPArgumentError, match="x"):
               await c.call_tool("t", {"x": 42})
           mock_session.call_tool.assert_not_called()
       finally:
           await c.disconnect()
   ```

7. **Add integration tests** under `TestL6bInputValidationIntegration`. Example:
   ```python
   class TestL6bInputValidationIntegration:
       async def test_call_tool_invalid_args_via_streamable_http(
           self, mcp_fixture_http_client, monkeypatch
       ) -> None:
           client_httpx, url = mcp_fixture_http_client
           monkeypatch.setattr(
               "the_one.mcp.transports.streamable_http._test_http_client_override",
               client_httpx,
           )
           source = MCPSource(
               id="src-6", name="hello", type="streamable-http",
               config={"url": url, "headers": {}}, secrets={},
           )
           c = MCPClient(source)
           await c.connect()
           try:
               with pytest.raises(MCPArgumentError):
                   await c.call_tool("echo", {})  # missing required `message`
           finally:
               await c.disconnect()

       @pytest.mark.timeout(15)
       async def test_call_tool_invalid_args_via_stdio(
           self, mcp_fixture_stdio_params
       ) -> None:
           # ... build MCPSource (id="src-stdio-6") from fixture dict ...
           c = MCPClient(source)
           await c.connect()
           try:
               with pytest.raises(MCPArgumentError):
                   await c.call_tool("echo", {})
           finally:
               await c.disconnect()
   ```

8. **Run the in-container test cycle**:
   ```bash
   docker compose exec the-one bash -c "cd /app && pytest -k 'TestCallToolInputValidation or TestCallToolContentBlockRendering or TestCallToolErrorTranslation or TestL6bInputValidationIntegration' -v"
   docker compose exec the-one bash -c "cd /app && pytest --tb=no -q"
   docker compose exec the-one bash -c "cd /app && ruff check the_one/ tests/"
   ```

9. **Update flight log L6b entry** in `## Leg Progress / ### L6b: input validation, content rendering, error paths` covering:
   - Status (landed)
   - Started/Completed timestamps
   - Changes Made (input validation via jsonschema, non-text placeholder rendering, full SDK error translation matrix in both list_tools and call_tool)
   - Notes (any deviations from spec — esp. mock construction quirks for `McpError`; integration test runtimes)
   - Test count before/after (1151 → 1167)
   - Lint status

## Edge Cases

- **`jsonschema.ValidationError` wraps as `MCPArgumentError`**: F2 only exposes the `str(e)` form (which includes the path-of-failure detail). Don't try to surface jsonschema's structured error tree — small-model-friendly per mission constraint #61.

- **`tool_meta` lookup**: `next(t for t in self._tools_cache if t.name == name)` — at this point in `call_tool`, the unknown-tool guard already ran, so `name` is guaranteed in the cache. The `next()` won't raise StopIteration. Defensive `next(..., None)` could be added but is unreachable; keep simple.

- **Validation OUTSIDE timeout window**: jsonschema is fast (~µs for trivial schemas, ~ms for big ones). Wrapping inside `asyncio.timeout` adds no value. Place validation BEFORE the timeout block.

- **`McpError` constructor**: SDK's `McpError(error: ErrorData)` — direct construction in tests requires building an `ErrorData(code=-32600, message="boom")`. Prefer `MagicMock(spec=McpError)` with a `__str__` override OR use `pytest.raises` on `side_effect=McpError(...)` once the `ErrorData` shape is verified. The L6b implementer should probe this in-container and adapt.

- **`UrlElicitationRequiredError` IS a subclass of `McpError`**: verified at L6b design review — `issubclass(UrlElicitationRequiredError, McpError) == True`. WITHOUT an explicit `except UrlElicitationRequiredError: raise` clause ORDERED BEFORE `except McpError`, it would be silently swallowed into `MCPCallError`, breaking F3+'s ability to surface URL elicitation prompts. Both `call_tool` and `list_tools` must include the explicit re-raise. Test #6 in `TestCallToolErrorTranslation` is the mechanical guard against accidental regression.

- **`additionalProperties` default**: jsonschema's default is to ALLOW additional properties unless the schema explicitly says `"additionalProperties": false`. Test #4 (`test_extra_unknown_field_passes_validation`) asserts this default — if the test fails, the SDK / jsonschema version may have a different default; investigate and adapt.

- **`from None` in `raise X from None`**: suppresses the `__cause__` chain. Used to keep error messages clean (no `During handling of the above exception...`). Mission constraint #61 (small-model-friendly).

- **`list_tools` McpError translates to `MCPConnectionError`, NOT `MCPCallError`**: list_tools isn't a tool *call* (it's a session operation); the user-facing semantics are "the connection couldn't enumerate tools". Documented in error translation matrix above.

- **Mock helpers' `model_dump` return values**: tests verify both `result.text` (the placeholder string) AND that `raw` accumulates valid dicts. The mock `model_dump` return value should match what the real SDK would emit (best-effort — minor key omissions are acceptable since `raw` is opaque to L6b's text-rendering logic).

- **`mock_session.list_tools` MUST be configured BEFORE `call_tool` runs** in L6b's tests, because `call_tool`'s lazy-populate calls `list_tools()` first — if `list_tools` mock isn't set, the test fails with a confusing `AttributeError`. L6a's pattern handles this; L6b's tests must too.

- **`from jsonschema import validate` import name collision**: Python's `validate` is a generic name. Alias as `jsonschema_validate` to avoid shadowing in the function body. The leg's code samples use this alias.

- **F4-pool compat**: L6b adds no new state to `MCPClient`. The error-translation wrappers are stateless. F4's pool can hold L6b-finished MCPClient instances without changes.

- **L6a's `_session.call_tool` mock can return a `_make_call_tool_result` directly**: the wrapping `try/except` doesn't interfere with the success path. Re-confirmed in test #1 (`test_valid_args_pass_validation`).

## Files Affected

- `the_one/mcp/client.py` — top-level imports (jsonschema, `McpError` + `UrlElicitationRequiredError`, httpx, anyio); `list_tools` and `call_tool` extended with error translation including `except UrlElicitationRequiredError: raise` ordered BEFORE `except McpError`; `call_tool` extended with input validation + non-text rendering
- `tests/test_mcp_client.py` — 4 new mock-content helpers (`_make_image_content`, `_make_audio_content`, `_make_resource_link_content`, `_make_embedded_resource_content`); 3 new test classes (`TestCallToolInputValidation` ×5, `TestCallToolContentBlockRendering` ×5 incl. mixed-order, `TestCallToolErrorTranslation` ×6 incl. URL elicitation propagation)
- `tests/test_mcp_integration.py` — extend imports (`MCPArgumentError`); `TestL6bInputValidationIntegration` ×2

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — exactly 1169 passing + 1 skipped (1151 baseline post-L6a + 18 new tests: 5 + 5 + 6 + 2)
- [ ] Lint clean (no NEW ruff errors)
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress / ### L6b: input validation, content rendering, error paths`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end (the next leg is the flight-end review + commit; L7 is optional HAT)

## Citation Audit

5 SDK + repo citations verified at leg-design time:

1. `the_one/mcp/client.py::call_tool` — verified post-L6a body present (line 311-368); L6b extends in-place
2. `the_one/mcp/client.py::list_tools` — verified post-L6a body present (line 270-309); L6b extends with error translation
3. `mcp.shared.exceptions.McpError` and `UrlElicitationRequiredError` — verified importable from `mcp.shared.exceptions`; `McpError(error: ErrorData)` constructor; `UrlElicitationRequiredError` is a sibling class (not a subclass of McpError)
4. `mcp.types.{ImageContent, AudioContent, ResourceLink, EmbeddedResource}` — verified field shapes via in-container probe at design time. `EmbeddedResource.resource` is `TextResourceContents | BlobResourceContents` with `.uri` field
5. `jsonschema 4.26.0` (transitive direct dep via `mcp 1.27.0`) — verified `from jsonschema import validate, ValidationError` works; `ValidationError` is the standard mismatch class

All citations clean — no drift.

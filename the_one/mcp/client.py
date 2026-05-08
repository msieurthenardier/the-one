"""MCPClient — async wrapper around mcp==1.27.0 SDK's ClientSession.

L2 implements connect/disconnect lifecycle + handshake + capability negotiation.
L4 wires streamable-http transport dispatch.
L5 wires stdio transport dispatch.
L6a implements list_tools and call_tool happy-path.
L6b implements input validation and full error-path translation.

See flight design decisions §2 (API surface), §9 (F4-pool compat invariants).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

import anyio
import httpx
from jsonschema import ValidationError
from jsonschema import validate as jsonschema_validate
from mcp.shared.exceptions import McpError, UrlElicitationRequiredError

from the_one.db.models import MCPSource
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

if TYPE_CHECKING:
    from mcp import ClientSession  # type-only; SDK not loaded at module-load
    from mcp.types import ServerCapabilities

logger = logging.getLogger(__name__)

_UNSUPPORTED_VERSION_RE = re.compile(
    r"Unsupported protocol version from the server: (.+)"
)

# Sentinel for "use the runtime default from the_one.mcp" — distinguishes
# "caller passed nothing" from "caller explicitly passed None/0". We don't
# bind the constant at function-definition time so test monkeypatches of
# the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS would still propagate (defense
# in depth — F2 only mandates _PINNED_PROTOCOL_VERSION read-at-call-time).
_DEFAULT = object()


@asynccontextmanager
async def _transport_connect(source: MCPSource) -> AsyncIterator["ClientSession"]:
    """Dispatch on source.type to the correct transport. L4/L5 fill in.

    Yields a connected ClientSession (entered, but not yet initialized).
    Caller is responsible for calling session.initialize() and final cleanup.

    L4 will rewrite the streamable-http branch to nest streamable_http_client +
    ClientSession context managers and yield the entered session. L5 will do
    the same for stdio_client + StdioServerParameters. The yield-a-session
    contract keeps the (read, write) stream-tuple shape inside this helper —
    MCPClient never sees the raw transport.
    """
    if source.type == "streamable-http":
        from the_one.mcp.transports.streamable_http import connect_streamable_http

        async with connect_streamable_http(source) as session:
            yield session
    elif source.type == "stdio":
        from the_one.mcp.transports.stdio import connect_stdio

        async with connect_stdio(source) as session:
            yield session
    else:
        # Defensive exhaustiveness — Pydantic Literal gates the type at model
        # validation time, so this branch is unreachable in normal flow.
        # Locks the contract that any future transport literal must extend
        # this dispatch (mirrors F1's defensive `else: raise` exhaustiveness).
        raise MCPClientError(f"unknown MCP transport type: {source.type!r}")
    # asynccontextmanager requires a yield somewhere; this branch is dead but
    # keeps the contract type-clean. Unreachable at runtime due to raises above.
    yield  # type: ignore[unreachable]  # noqa: F821


class MCPClient:
    """Async wrapper for an MCP server connection.

    Lifecycle: __init__ -> connect -> (list_tools/call_tool)* -> disconnect.
    Use as `async with MCPClient(source) as client:` for scope-managed use.

    F4-pool compat invariants (flight §9):
      - is_alive flips False BEFORE awaiting any close coroutines (so a
        concurrent reaper-task observes the disconnect-in-progress state).
      - last_activity is exactly 0.0 until the first successful operation.
      - disconnect() is idempotent and never raises.
      - _capabilities / _protocol_version / _last_activity are preserved
        across disconnect (stale but not invalid).
    """

    def __init__(
        self,
        source: MCPSource,
        *,
        timeout_seconds: int | float | object = _DEFAULT,
        call_timeout_seconds: int | float | object = _DEFAULT,
    ) -> None:
        # Lazy read of constants from the_one.mcp keeps the read-at-call-time
        # invariant for any future test that monkeypatches the defaults.
        from the_one import mcp as the_one_mcp

        if timeout_seconds is _DEFAULT:
            timeout_seconds = the_one_mcp.MCP_DEFAULT_TIMEOUT_SECONDS
        if call_timeout_seconds is _DEFAULT:
            call_timeout_seconds = the_one_mcp.MCP_DEFAULT_CALL_TIMEOUT_SECONDS

        self.source: MCPSource = source
        self.timeout_seconds: int | float = timeout_seconds  # type: ignore[assignment]
        self.call_timeout_seconds: int | float = call_timeout_seconds  # type: ignore[assignment]

        self._session: ClientSession | None = None
        self._capabilities: ServerCapabilities | None = None
        self._protocol_version: str | None = None
        self._is_alive: bool = False
        # Exact 0.0 sentinel — time.monotonic() never returns 0 on a running
        # system, so `last_activity > 0.0` is meaningful. None would crash
        # __repr__'s `f"{x:.2f}"` — see flight §9 / leg AC.
        self._last_activity: float = 0.0
        self._transport_cm: Any = None  # holds the _transport_connect cm
        # Tools cache — populated on first list_tools() or first call_tool()
        # (whichever fires first). Used by call_tool's unknown-tool guard and
        # by L6b's input-schema validation. Cleared on disconnect so a re-
        # connect rebuilds fresh (tools may change between sessions).
        self._tools_cache: list[MCPTool] | None = None

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

        # Lazy SDK-namespace import — keeps test monkeypatch hooks alive
        # for the_one.mcp._PINNED_PROTOCOL_VERSION (read-at-call-time per F2).
        from the_one import mcp as the_one_mcp

        pinned = the_one_mcp._PINNED_PROTOCOL_VERSION

        result: Any = None
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

        # F2 strict check (narrower than the SDK's SUPPORTED_PROTOCOL_VERSIONS).
        # When session.initialize is wholly mocked in tests, the SDK's own
        # version-set check never runs — F2's strict-equality gate is the
        # only one that fires. See test_pinned_constant_read_at_call_time.
        if result.protocolVersion != pinned:
            await self._cleanup_after_failed_connect()
            raise MCPVersionMismatch(pinned=pinned, observed=result.protocolVersion)

        if result.capabilities.tools is None:
            await self._cleanup_after_failed_connect()
            raise MCPCapabilityMissing("tools")

        # All checks pass — commit state. Ordering invariant: any path that
        # raised above must leave _is_alive=False (so test_connect_*_mismatch
        # observes the failed state correctly).
        self._capabilities = result.capabilities
        self._protocol_version = result.protocolVersion
        self._is_alive = True
        self._touch_activity()

    async def _cleanup_after_failed_connect(self) -> None:
        """Best-effort teardown of partial state from a failed connect()."""
        try:
            if self._transport_cm is not None:
                await self._transport_cm.__aexit__(None, None, None)
        except Exception:
            logger.debug("transport cleanup raised; suppressing", exc_info=True)
        self._transport_cm = None
        self._session = None

    async def disconnect(self) -> None:
        """Idempotent teardown. Never raises — F4-pool contract.

        F4-pool concurrency note: setting `_is_alive = False` BEFORE awaiting
        any close coroutines ensures the reaper observes the disconnect-in-
        progress state correctly. Python's GIL makes single-attribute reads/
        writes of bool/float atomic, so no explicit lock is needed.
        """
        if not self._is_alive and self._transport_cm is None:
            return
        # Flip the flag FIRST so concurrent readers see correct state.
        self._is_alive = False
        try:
            if self._transport_cm is not None:
                await self._transport_cm.__aexit__(None, None, None)
        except Exception:
            logger.warning("MCPClient transport close failed", exc_info=True)
        finally:
            self._transport_cm = None
            self._session = None
            # _tools_cache is per-session — clear so re-connect rebuilds fresh
            # (tools may change between sessions; stale cache could leak).
            self._tools_cache = None
            # Preserve _capabilities, _protocol_version, _last_activity for
            # the F4 pool — once disconnected they're stale but not invalid.

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        # Returning None lets any in-flight exception propagate naturally per
        # Python's async-with protocol (the wrapper does NOT suppress).
        await self.disconnect()

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
        # L6b: SDK error translation. UrlElicitationRequiredError IS a subclass
        # of McpError (verified at L6b design review) — re-raise BEFORE the
        # McpError clause or it gets silently swallowed into MCPConnectionError,
        # breaking F3+'s ability to surface URL elicitation prompts.
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

        tools: list[MCPTool] = []
        for tool in result.tools:
            # tool.annotations is a Pydantic ToolAnnotations object (or None);
            # .model_dump(mode="json") yields a stable JSON-serializable dict.
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

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> MCPToolResult:
        """Call a tool on the server and return the result.

        Lazy-populates self._tools_cache if needed (so unknown-tool detection
        works on first call). Raises MCPToolNotFoundError BEFORE wire call if
        the tool name isn't in the cache. Validates `arguments` against the
        tool's JSON Schema (L6b) BEFORE wire call, raising MCPArgumentError on
        mismatch. Raises MCPCallError if the server returns isError=True or an
        SDK McpError. Wraps timeout / transport errors as MCPConnectionError.
        UrlElicitationRequiredError propagates unchanged (F3+ surfaces it).

        Raises:
            MCPConnectionError: not connected, timeout, or transport error.
            MCPToolNotFoundError: if name isn't in the server's tool list.
            MCPArgumentError: if arguments fail JSON-Schema validation.
            MCPCallError: if the server returned isError=True or McpError.
            UrlElicitationRequiredError: propagated unchanged for F3+ flows.
        """
        if not self._is_alive or self._session is None:
            raise MCPConnectionError(
                "MCPClient is not connected; cannot call tool."
            )
        self._touch_activity()

        # Lazy-populate the tool cache for unknown-tool detection. Runs OUTSIDE
        # the call_timeout_seconds budget — list_tools has its own 30s timeout.
        if self._tools_cache is None:
            await self.list_tools()

        known_names = {t.name for t in self._tools_cache or []}
        if name not in known_names:
            raise MCPToolNotFoundError(name)

        # L6b: input validation against the tool's JSON Schema. Runs OUTSIDE
        # the asyncio.timeout window — jsonschema is fast pure-Python (~µs to
        # ~ms), no point timing it. Tools without inputSchema (or with `{}`)
        # skip validation per flight §5.
        tool_meta = next(t for t in self._tools_cache if t.name == name)
        if tool_meta.input_schema:
            try:
                jsonschema_validate(arguments, tool_meta.input_schema)
            except ValidationError as e:
                raise MCPArgumentError(
                    tool_name=name, validation_message=str(e)
                ) from None

        # L6b: SDK error translation. UrlElicitationRequiredError IS a subclass
        # of McpError (verified at L6b design review:
        # `issubclass(UrlElicitationRequiredError, McpError) == True`) — the
        # explicit re-raise MUST come BEFORE `except McpError` or URL
        # elicitation prompts get silently swallowed into MCPCallError.
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

        # Flatten text content blocks; render placeholders for non-text blocks
        # so MCPToolResult.text reflects ALL blocks (text + placeholders) in
        # order. Unknown block types are silently dropped (forward-compat with
        # future SDK content-block types).
        joined_text_parts: list[str] = []
        raw_blocks: list[dict[str, Any]] = []
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
                # EmbeddedResource has .resource which has .uri
                # (TextResourceContents | BlobResourceContents).
                joined_text_parts.append(f"[resource: {block.resource.uri}]")
            # Unknown block types: silently dropped (forward-compat).
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

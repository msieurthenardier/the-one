"""Unit tests for the_one.mcp module.

L1: module setup, SDK version pin tripwire.
L2: MCPClient lifecycle and handshake (mocked ClientSession).
L3: integration tests live in test_mcp_integration.py.
L4: streamable-http transport (mocked + integration via L3 fixture).
L5: stdio transport (mocked + integration via L3 fixture).
L6a: list_tools + call_tool happy path.
L6b: input validation + error paths + non-text content blocks.
"""

import asyncio
import dataclasses
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import httpx
import pytest
from mcp.client.auth.exceptions import OAuthFlowError, OAuthTokenError
from mcp.shared.exceptions import McpError, UrlElicitationRequiredError
from mcp.types import ErrorData

from the_one.db.models import MCPSource
from the_one.mcp import client as client_mod
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import (
    MCPArgumentError,
    MCPAuthRequired,
    MCPCallError,
    MCPCapabilityMissing,
    MCPConnectionError,
    MCPToolNotFoundError,
    MCPVersionMismatch,
)
from the_one.mcp.transports.stdio import build_stdio_environ
from the_one.mcp.transports.streamable_http import build_request_headers


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

        tool = MCPTool(
            name="x",
            description="",
            input_schema={},
            output_schema=None,
            annotations=None,
        )
        result = MCPToolResult(text="", raw=[], structured=None, is_error=False)

        with pytest.raises(dataclasses.FrozenInstanceError):
            tool.name = "y"  # type: ignore[misc]

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.text = "z"  # type: ignore[misc]


# ─── L2 fixtures and helpers ────────────────────────────────────────────────


def _stdio_source(name: str = "test", source_id: str = "src-1") -> MCPSource:
    """Build a minimal stdio MCPSource for lifecycle tests."""
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
    tools_present: bool = True,
    capabilities_dump: dict | None = None,
    server_info_dump: dict | None = None,
    instructions: str | None = None,
):
    """Build a mock InitializeResult with the configured shape.

    The mock's `capabilities` exposes:
      - `.tools`: a MagicMock (truthy) when tools_present, else None
      - `.model_dump(mode='json')`: returns capabilities_dump (default {"tools": {}})

    F4 L2 (M08): optional ``server_info_dump`` and ``instructions`` mirror
    the spec-optional ``serverInfo`` / ``instructions`` fields on
    ``InitializeResult``. When ``server_info_dump`` is None the mock
    exposes ``serverInfo=None`` (matches a server that omits the field).
    When supplied as a dict, the mock's ``model_dump(mode='json', ...)``
    returns it, exercising MCPClient.server_info's exclude_none pass-through.
    """
    result = MagicMock()
    result.protocolVersion = protocol_version
    caps = MagicMock()
    caps.tools = MagicMock() if tools_present else None
    caps.model_dump = MagicMock(
        return_value=(capabilities_dump if capabilities_dump is not None else {"tools": {}})
    )
    result.capabilities = caps
    if server_info_dump is None:
        result.serverInfo = None
    else:
        si = MagicMock()
        si.model_dump = MagicMock(return_value=server_info_dump)
        result.serverInfo = si
    result.instructions = instructions
    return result


@asynccontextmanager
async def _mock_transport_cm(session_mock):
    """Mimics _transport_connect's contract — yields a session, runs cleanup on exit.

    Single-use: asynccontextmanager-produced CMs cannot be re-entered, so
    `patch_transport` installs `lambda source: _mock_transport_cm(sess)` to
    create a fresh CM per call (supports connect→disconnect→connect tests).
    """
    try:
        yield session_mock
    finally:
        pass


@asynccontextmanager
async def _anyio_backed_transport_cm(session_mock):
    """Transport CM whose body holds a real anyio task group.

    Used by L1a stake-test probes (`TestAsyncExitStackContract`) to ensure
    cross-task ``__aexit__`` trips anyio's CancelScope guard for real (vs
    simulating it via a string-equal RuntimeError). The ``session_mock``
    argument is the existing mock session — the body just yields it; the
    anyio task group is what makes the guard fire when ``__aexit__`` runs
    on a different task than ``__aenter__``.
    """
    async with anyio.create_task_group():
        yield session_mock


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.initialize = AsyncMock(return_value=_make_init_result())
    session.list_tools = AsyncMock()
    session.call_tool = AsyncMock()
    return session


@pytest.fixture
def patch_transport(monkeypatch, mock_session):
    """Install a mock _transport_connect that yields the supplied session.

    Returns a callable: `patch_transport()` uses `mock_session`;
    `patch_transport(other_session)` overrides. Always returns the installed
    session so tests can spy on it without re-importing the fixture.
    """

    def _install(session_or_factory=None):
        sess = session_or_factory if session_or_factory is not None else mock_session
        # Lambda creates a fresh CM per call (asynccontextmanager-produced CMs
        # are single-use; without this, a connect→disconnect→connect sequence
        # would re-enter an already-exited CM and crash).
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _mock_transport_cm(sess),
        )
        return sess

    return _install


# ─── L6a helpers (used by reworked L2 test + TestListToolsAndCallTool) ──────


def _make_tool(
    name: str,
    description: str = "",
    input_schema: dict | None = None,
    *,
    output_schema: dict | None = None,
    annotations: object | None = None,
) -> MagicMock:
    """Build a mock SDK Tool with the F2-relevant fields populated."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = input_schema if input_schema is not None else {}
    tool.outputSchema = output_schema
    tool.annotations = annotations  # None or a Pydantic-like object with model_dump
    return tool


def _make_list_tools_result(tools: list[MagicMock]) -> MagicMock:
    """Build a mock ListToolsResult with the supplied tools."""
    result = MagicMock()
    result.tools = tools
    return result


def _make_text_content(text: str) -> MagicMock:
    """Build a mock TextContent block (type='text', text=..., model_dump'able)."""
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
    """Build a mock CallToolResult with the supplied content blocks."""
    result = MagicMock()
    result.content = content
    result.structuredContent = structured
    result.isError = is_error
    return result


# ─── L6b helpers (non-text content block mocks) ──────────────────────────────


def _make_image_content(data: str = "abc", mime: str = "image/png") -> MagicMock:
    """Build a mock ImageContent block (type='image', data=base64-ish, mimeType)."""
    block = MagicMock()
    block.type = "image"
    block.data = data
    block.mimeType = mime
    block.model_dump = MagicMock(
        return_value={"type": "image", "data": data, "mimeType": mime}
    )
    return block


def _make_audio_content(data: str = "xyz", mime: str = "audio/wav") -> MagicMock:
    """Build a mock AudioContent block (type='audio', data, mimeType)."""
    block = MagicMock()
    block.type = "audio"
    block.data = data
    block.mimeType = mime
    block.model_dump = MagicMock(
        return_value={"type": "audio", "data": data, "mimeType": mime}
    )
    return block


def _make_resource_link_content(uri: str = "file:///x.txt") -> MagicMock:
    """Build a mock ResourceLink block (type='resource_link', uri)."""
    block = MagicMock()
    block.type = "resource_link"
    block.uri = uri
    block.model_dump = MagicMock(
        return_value={"type": "resource_link", "uri": uri}
    )
    return block


def _make_embedded_resource_content(uri: str = "resource://r") -> MagicMock:
    """Build a mock EmbeddedResource block (type='resource', resource.uri)."""
    block = MagicMock()
    block.type = "resource"
    inner = MagicMock()
    inner.uri = uri
    block.resource = inner
    block.model_dump = MagicMock(
        return_value={"type": "resource", "resource": {"uri": uri}}
    )
    return block


# ─── L2 tests ────────────────────────────────────────────────────────────────


class TestMCPClientLifecycle:
    async def test_init_state(self) -> None:
        """Fresh MCPClient: not alive, last_activity exactly 0.0, properties guarded."""
        c = MCPClient(_stdio_source())
        assert c.is_alive is False
        assert c.last_activity == 0.0
        with pytest.raises(MCPConnectionError):
            _ = c.negotiated_protocol_version
        with pytest.raises(MCPConnectionError):
            _ = c.server_capabilities

    async def test_connect_happy_path(self, patch_transport, mock_session) -> None:
        """Pinned-version + tools-capability handshake transitions to alive."""
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            assert c.is_alive is True
            assert c.last_activity > 0.0
            assert c.negotiated_protocol_version == "2025-11-25"
            assert c.server_capabilities == {"tools": {}}
            # F4 L2 (M08): defaults — server omits serverInfo and
            # instructions, so the public accessors return None rather
            # than raising. (The _is_alive guard still fires before the
            # internal None check, mirroring server_capabilities' shape.)
            assert c.server_info is None
            assert c.instructions is None
        finally:
            await c.disconnect()
        assert c.is_alive is False

    async def test_connect_captures_server_info_and_instructions(
        self, patch_transport, mock_session
    ) -> None:
        """F4 L2 (M08): when the initialize() response carries serverInfo +
        instructions (e.g. Cloudflare Docs MCP), MCPClient surfaces both via
        the ``server_info`` and ``instructions`` properties — and persistence
        callers (api.py `/test/connect`) can snapshot them inside the
        async-with for the cache write.

        Locks the contract that:
          - server_info returns the JSON-mode dict (excluding None fields)
          - instructions returns the raw str
          - both properties raise MCPConnectionError when not connected
            (mirrors server_capabilities' guard)
          - disconnect clears the internal state so a reconnect repopulates
        """
        mock_session.initialize = AsyncMock(
            return_value=_make_init_result(
                server_info_dump={
                    "name": "cloudflare-docs",
                    "title": "Cloudflare Docs MCP",
                    "version": "1.2.3",
                },
                instructions="Use search() before fetch() to discover doc pages.",
            )
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())

        # Pre-connect: properties raise (mirrors server_capabilities guard).
        with pytest.raises(MCPConnectionError):
            _ = c.server_info
        with pytest.raises(MCPConnectionError):
            _ = c.instructions

        await c.connect()
        try:
            assert c.server_info == {
                "name": "cloudflare-docs",
                "title": "Cloudflare Docs MCP",
                "version": "1.2.3",
            }
            assert c.instructions == "Use search() before fetch() to discover doc pages."
        finally:
            await c.disconnect()

        # Post-disconnect: properties raise (state cleared for fresh reconnect).
        with pytest.raises(MCPConnectionError):
            _ = c.server_info
        with pytest.raises(MCPConnectionError):
            _ = c.instructions

    async def test_connect_supported_non_pinned_version_passes(
        self, patch_transport, mock_session
    ) -> None:
        """F6 A6 fix: SDK-supported-but-not-pinned versions are accepted.

        Inversion of pre-A6 ``test_connect_version_mismatch_strict`` —
        F2's original strict-equality (``protocolVersion != pinned``)
        rejected every server that didn't announce the exact pinned
        revision, even when the announced version was in the SDK's
        ``SUPPORTED_PROTOCOL_VERSIONS`` set. F6 Tier-2 HAT against
        Cloudflare Docs MCP (announces 2025-06-18) surfaced this as a
        production gap; the source failed version-check before F5's
        lazy-OAuth flow could fire. Post-A6, the check loosens to "in
        the SDK's supported set" per mission constraint #59's
        "capability-gate, don't crash" framing. The pinned constant
        remains as documentation/marker.
        """
        mock_session.initialize = AsyncMock(
            return_value=_make_init_result(protocol_version="2025-06-18")
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        # Pre-A6 this raised MCPVersionMismatch; post-A6 it succeeds.
        await c.connect()
        assert c.is_alive is True
        assert c.negotiated_protocol_version == "2025-06-18"
        await c.disconnect()

    async def test_connect_unsupported_version_raises_mismatch(
        self, patch_transport, mock_session
    ) -> None:
        """Server announcing a version NOT in SDK's SUPPORTED_PROTOCOL_VERSIONS
        raises MCPVersionMismatch. Locks the post-A6 check site."""
        mock_session.initialize = AsyncMock(
            return_value=_make_init_result(protocol_version="1999-01-01")
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPVersionMismatch) as exc_info:
            await c.connect()
        assert exc_info.value.observed == "1999-01-01"
        assert c.is_alive is False

    async def test_connect_version_mismatch_via_sdk_runtime_error(
        self, patch_transport, mock_session
    ) -> None:
        """SDK's own RuntimeError(unsupported version) is translated to MCPVersionMismatch."""
        mock_session.initialize = AsyncMock(
            side_effect=RuntimeError(
                "Unsupported protocol version from the server: 1999-01-01"
            )
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPVersionMismatch) as exc_info:
            await c.connect()
        assert exc_info.value.pinned == "2025-11-25"
        assert exc_info.value.observed == "1999-01-01"
        assert c.is_alive is False

    async def test_connect_capability_tools_missing(
        self, patch_transport, mock_session
    ) -> None:
        """Server without tools capability raises MCPCapabilityMissing."""
        mock_session.initialize = AsyncMock(
            return_value=_make_init_result(tools_present=False)
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPCapabilityMissing) as exc_info:
            await c.connect()
        assert exc_info.value.capability == "tools"
        assert c.is_alive is False

    async def test_connect_already_connected_raises(
        self, patch_transport, mock_session
    ) -> None:
        """Second connect() on alive client raises MCPConnectionError."""
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPConnectionError, match="already connected"):
                await c.connect()
        finally:
            await c.disconnect()

    async def test_connect_timeout(self, patch_transport, mock_session) -> None:
        """initialize() blocking past timeout_seconds raises MCPConnectionError."""

        async def _hang() -> None:
            await asyncio.sleep(10)  # well past the 0.05s timeout

        mock_session.initialize = AsyncMock(side_effect=_hang)
        patch_transport(mock_session)
        c = MCPClient(_stdio_source(), timeout_seconds=0.05)
        with pytest.raises(MCPConnectionError) as exc_info:
            await c.connect()
        assert "did not respond within 0.05 seconds during initialize" in str(
            exc_info.value
        )
        assert c.is_alive is False

    async def test_connect_cancelled_error_translates_to_connection_error(
        self, patch_transport, mock_session
    ) -> None:
        """F6 A5 regression: ``CancelledError`` raised from ``session.initialize()``
        translates to :class:`MCPConnectionError` with the abandon-cleanup
        path active (no hang).

        Reproduces the production cascade against an OAuth-protected
        streamable-http source without credentials: the SDK's anyio
        task-group cleanup chain, after the inner 401, ends with the
        surrounding task cancelled. The pre-A5 ``except Exception``
        handler missed ``CancelledError`` (PEP 656: extends BaseException
        only, not Exception) and the cancel propagated up through the
        F4 pool's ``_entry_worker`` into ``MCPToolProvider.get_tools_for_agent``
        whose class #2 handler ``(MCPSandboxError, MCPConnectionError,
        MCPVersionMismatch)`` also missed it — agent build crashed
        instead of graceful-degrade-skip. Post-fix, A5's dedicated
        ``except CancelledError`` translates to ``MCPConnectionError``,
        the abandon-cleanup branch sets ``_transport_stack`` and
        ``_session`` to None (avoiding re-trip on the wedged SDK task
        group), and class #2 catches uniformly.
        """
        mock_session.initialize = AsyncMock(side_effect=asyncio.CancelledError())
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPConnectionError) as exc_info:
            await c.connect()
        # Verbatim substring lock per `verbatim-message-equality` convention.
        assert "cancelled during initialize" in str(exc_info.value)
        # F6.6 L1: post-narrowing, the CancelledError block's message no
        # longer speculates about "401 Unauthorized" — OAuth-flow
        # exceptions are caught upstream by the inner `except*` block,
        # and transport-layer 401s are caught by the outer
        # BaseExceptionGroup walk. Neither path reaches CancelledError.
        assert "401" not in str(exc_info.value)
        assert c.is_alive is False
        # Abandon-cleanup invariant: stack + session cleared so a subsequent
        # disconnect() is a no-op (mirrors the F2-known-issue idempotent-
        # disconnect contract).
        assert c._transport_stack is None
        assert c._session is None

    async def test_connect_cancelled_error_during_cleanup_translates_to_connection_error(
        self, patch_transport, mock_session
    ) -> None:
        """F9 L2 regression: CancelledError raised from inside
        _cleanup_after_failed_connect (the cleanup-phase cancellation that
        the D1 stdio Test route surfaced as a 500) is caught by
        _safe_cleanup's widened except tuple and translated to
        MCPConnectionError, not propagated as bare CancelledError.

        Distinct from the existing CancelledError test, which exercises the
        OUTER ``except asyncio.CancelledError`` block by raising from
        initialize() directly. This test exercises the INNER ``_safe_cleanup``
        arm by:
          1. Raising a non-RuntimeError, non-MCPClientError Exception from
             initialize() (routes to outer ``except (Exception,
             BaseExceptionGroup)``, which is the only arm that uses
             ``_safe_cleanup``).
          2. Raising CancelledError from ``_cleanup_after_failed_connect``,
             which is what ``_safe_cleanup`` awaits under the 3s timeout.

        Note on exception choice: ``RuntimeError`` would be caught by the
        inner ``except RuntimeError`` block (version-mismatch translation)
        and re-raised as ``MCPVersionMismatch`` — that routes to the
        ``except (MCPClientError, NotImplementedError)`` arm, which
        bypasses ``_safe_cleanup``. ``ValueError`` is neither, so it
        falls through to the ``(Exception, BaseExceptionGroup)`` arm.

        Locks the four-typed-exceptions contract: even when cleanup itself
        is cancelled, connect() raises MCPConnectionError.
        """
        mock_session.initialize = AsyncMock(side_effect=ValueError("transport boom"))
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        # Monkeypatch the cleanup coroutine to raise CancelledError directly.
        # ``_safe_cleanup`` wraps this in ``asyncio.wait_for(..., timeout=3.0)``
        # and the widened except tuple should catch the CancelledError surface.
        c._cleanup_after_failed_connect = AsyncMock(  # type: ignore[method-assign]
            side_effect=asyncio.CancelledError()
        )
        with pytest.raises(MCPConnectionError) as exc_info:
            await c.connect()
        assert "MCP connect failed: ValueError" in str(exc_info.value)
        assert c.is_alive is False
        assert c._transport_stack is None
        assert c._session is None

    async def test_connect_oauth_flow_error_raises_mcp_auth_required(
        self, patch_transport, mock_session
    ) -> None:
        """F6.6 L1: OAuthFlowError raised inside session.initialize() translates
        to MCPAuthRequired with the standard auth-pending discriminator shape.

        Mirrors F6.5 L2's list_tools pattern against the same SDK exception
        surface (mcp.client.auth.exceptions), but at the connect-time entry
        point. The new innermost `except* (OAuthFlowError, OAuthTokenError)`
        block in MCPClient.connect translates the SDK's auth-flow exception
        to MCPAuthRequired, closing the F6.5 Design Decision §3 deferral.
        """
        mock_session.initialize = AsyncMock(
            side_effect=OAuthFlowError("auth flow failed during initialize")
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPAuthRequired) as exc_info:
            await c.connect()
        assert exc_info.value.source_id == c.source.id
        assert exc_info.value.resource_metadata_url is None
        assert exc_info.value.consent_url is None

    async def test_connect_oauth_token_error_raises_mcp_auth_required(
        self, patch_transport, mock_session
    ) -> None:
        """F6.6 L1: OAuthTokenError raised inside session.initialize() translates
        to MCPAuthRequired (same shape as the OAuthFlowError case).

        OAuthTokenError covers the refresh-failure subset of the SDK's auth
        exceptions; OAuthFlowError covers discovery + DCR. Both are members
        of the `except*` tuple and resolve identically via the new
        innermost translation block.
        """
        mock_session.initialize = AsyncMock(
            side_effect=OAuthTokenError("token error during initialize")
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPAuthRequired) as exc_info:
            await c.connect()
        assert exc_info.value.source_id == c.source.id
        assert exc_info.value.resource_metadata_url is None
        assert exc_info.value.consent_url is None

    async def test_connect_oauth_error_in_exception_group_raises_mcp_auth_required(
        self, patch_transport, mock_session
    ) -> None:
        """F6.6 L1: the SDK's anyio task-group can wrap OAuth exceptions in a
        BaseExceptionGroup; `except*` matches both bare and grouped shapes.

        Mirrors F6.5 L2's `except*` semantics — a regression that uses bare
        `except` instead of `except*` would fail this test specifically
        because BaseExceptionGroup is a BaseException, not the wrapped
        OAuthFlowError, and a non-`except*` clause would not unwrap it.
        """
        mock_session.initialize = AsyncMock(
            side_effect=BaseExceptionGroup(
                "auth-flow-group",
                [OAuthFlowError("inner auth-flow failure")],
            )
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPAuthRequired) as exc_info:
            await c.connect()
        assert exc_info.value.source_id == c.source.id

    async def test_disconnect_idempotent(self, patch_transport, mock_session) -> None:
        """Disconnect on never-connected client is a no-op; double-disconnect is a no-op."""
        # Never-connected disconnect: must not raise.
        c1 = MCPClient(_stdio_source())
        await c1.disconnect()
        assert c1.is_alive is False

        # connect → disconnect → disconnect: second disconnect is a no-op.
        patch_transport(mock_session)
        c2 = MCPClient(_stdio_source())
        await c2.connect()
        await c2.disconnect()
        assert c2.is_alive is False
        await c2.disconnect()  # no exception, no state change
        assert c2.is_alive is False

    async def test_disconnect_swallows_close_errors(
        self, monkeypatch, mock_session
    ) -> None:
        """Transport close-time exceptions are logged and swallowed."""

        @asynccontextmanager
        async def _failing_cm(source):
            try:
                yield mock_session
            finally:
                raise RuntimeError("close failed")

        monkeypatch.setattr(
            client_mod, "_transport_connect", lambda source: _failing_cm(source)
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        # Should NOT raise, even though _failing_cm raises on exit.
        await c.disconnect()
        assert c.is_alive is False

    async def test_aenter_aexit(self, patch_transport, mock_session) -> None:
        """async with wraps connect/disconnect; in-flight exceptions propagate."""
        patch_transport(mock_session)

        # Happy path: enter and exit cleanly.
        async with MCPClient(_stdio_source()) as c:
            assert c.is_alive is True
        assert c.is_alive is False

        # Exception inside the body: disconnect still runs, exception propagates.
        patch_transport(mock_session)  # fresh CM for second use
        c2: MCPClient | None = None
        with pytest.raises(ValueError, match="boom"):
            async with MCPClient(_stdio_source()) as c2:
                assert c2.is_alive is True
                raise ValueError("boom")
        assert c2 is not None
        assert c2.is_alive is False

    async def test_repr_format(self, patch_transport, mock_session) -> None:
        """__repr__ shape pinned by regex — drift is caught at test time."""
        repr_pattern = re.compile(
            r"^MCPClient\(name='.+', type='(stdio|streamable-http)', "
            r"is_alive=(True|False), last_activity=\d+\.\d{2}\)$"
        )
        # Pre-connect repr shape.
        c = MCPClient(_stdio_source())
        assert repr_pattern.match(repr(c)), repr(c)
        # Post-connect repr shape.
        patch_transport(mock_session)
        await c.connect()
        try:
            assert repr_pattern.match(repr(c)), repr(c)
        finally:
            await c.disconnect()

    async def test_pinned_constant_no_longer_gates_connect(
        self, monkeypatch, patch_transport, mock_session
    ) -> None:
        """F6 A6 inversion: ``_PINNED_PROTOCOL_VERSION`` is documentation/marker only.

        Pre-A6, F2's strict-equality gate read the PINNED constant at call time
        and rejected any non-equal version. Post-A6, the gate reads the SDK's
        ``SUPPORTED_PROTOCOL_VERSIONS`` set; the PINNED constant remains in
        ``the_one.mcp.__init__`` as a documentation/marker for the
        primary-targeted revision but no longer affects the runtime check.
        Locks the new contract: monkeypatching PINNED has no effect on connect()
        when the server announces a version IN the SDK's supported set.
        """
        # Monkeypatch PINNED to nonsense; would have caused connect() to fail
        # pre-A6 (server returns 2025-11-25, pinned now reads 2099-01-01,
        # strict equality fails). Post-A6, irrelevant — gate reads
        # SUPPORTED_PROTOCOL_VERSIONS, server's 2025-11-25 IS in that set,
        # connect() succeeds.
        monkeypatch.setattr("the_one.mcp._PINNED_PROTOCOL_VERSION", "2099-01-01")
        mock_session.initialize = AsyncMock(
            return_value=_make_init_result(protocol_version="2025-11-25")
        )
        patch_transport(mock_session)
        c = MCPClient(_stdio_source())
        await c.connect()
        assert c.is_alive is True
        assert c.negotiated_protocol_version == "2025-11-25"
        await c.disconnect()

    async def test_last_activity_updates_via_list_tools(
        self, patch_transport, mock_session
    ) -> None:
        """list_tools touches activity on every call (L6a real implementation).

        L2 stubbed list_tools to raise NotImplementedError after touching
        activity; L6a replaces the stub with the real body. This test still
        verifies the same invariant — last_activity advances on list_tools —
        but against the real body (no pytest.raises).
        """
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("echo")])
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            t0 = c.last_activity
            assert t0 > 0.0
            # Brief delay so monotonic clock advances even on fast systems.
            await asyncio.sleep(0.001)
            await c.list_tools()
            assert c.last_activity > t0
        finally:
            await c.disconnect()


# ---------------------------------------------------------------------------
# L1a: AsyncExitStack contract + cross-task safety net stake-test probe
# ---------------------------------------------------------------------------


class TestAsyncExitStackContract:
    """Stake-test probe + regression suite for the L1a AsyncExitStack refactor.

    Locks the four observable invariants of the disconnect contract:

    1. Same-task disconnect (the canonical ``async with MCPClient(s) as c:``
       pattern) produces NO ``WARNING`` log line — anyio guard not
       triggered, swallow not invoked.
       Lock: ``test_same_task_disconnect_no_safety_net_log``.

    2. Cross-task disconnect (``MCPClient`` constructed/connected on task A,
       ``disconnect()`` awaited on task B) DOES log via the cross-task
       safety net — anyio guard fires from inside ``stack.aclose()``,
       swallow catches the ``RuntimeError``.
       Lock: ``test_cross_task_disconnect_logs_via_safety_net``.

    3. Worker-task-per-entry pattern (the F4 L3 pool shape: a worker task
       holds connect, awaits an evict_event, then runs disconnect in its
       ``finally`` — connect AND disconnect on the same task) produces
       NO ``WARNING`` log. Experimental verification that L3's chosen
       pattern actually circumvents the anyio guard against a real
       ``anyio.create_task_group()``.
       Lock: ``test_worker_task_pattern_no_safety_net_log``.

    4. Stack ``aclose()`` is called on connect-failure paths and the
       disconnect contract is idempotent under double-call and
       reconnect-after-disconnect.
       Locks: ``test_connect_failure_runs_stack_aclose``,
       ``test_disconnect_idempotent_with_stack``.

    Per F2 debrief KL #1: when integration tests stake on a specific
    SDK pattern, commit a stake-test probe as a regression test so
    future maintainers can mechanically re-verify the contract.
    """

    async def test_same_task_disconnect_no_safety_net_log(
        self, monkeypatch, mock_session, caplog
    ) -> None:
        """Same-task connect/disconnect: anyio guard NOT triggered, swallow NOT invoked.

        Meaningful BECAUSE the mock holds a real ``anyio.create_task_group()``:
        the test proves the guard does NOT fire on same-task exit.
        """
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _anyio_backed_transport_cm(mock_session),
        )
        caplog.set_level(logging.WARNING, logger="the_one.mcp.client")
        async with MCPClient(_stdio_source()) as c:
            assert c.is_alive is True
        assert c.is_alive is False
        warns = [
            r for r in caplog.records
            if r.message == "MCPClient transport close failed"
        ]
        assert warns == [], f"unexpected safety-net warnings: {warns}"

    async def test_cross_task_disconnect_logs_via_safety_net(
        self, monkeypatch, mock_session, caplog
    ) -> None:
        """Cross-task disconnect: anyio's REAL CancelScope guard fires; safety net catches.

        Connect runs on the test task (anyio's _host_task). Disconnect runs on
        a worker task. anyio's ``CancelScope.__exit__`` checks
        ``current_task() is self._host_task`` and raises a real
        ``RuntimeError("Attempted to exit cancel scope in a different task...")``.
        The safety-net swallow at ``client.py::disconnect`` catches it and logs
        via ``logger.warning("MCPClient transport close failed", ...)``.
        """
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _anyio_backed_transport_cm(mock_session),
        )
        caplog.set_level(logging.WARNING, logger="the_one.mcp.client")
        c = MCPClient(_stdio_source())
        await c.connect()  # entered on test task (host task for anyio scope)
        try:
            disconnect_task = asyncio.create_task(c.disconnect())
            await disconnect_task
            # Must not raise — the safety-net swallow absorbed the RuntimeError.
            assert disconnect_task.exception() is None
        finally:
            assert c.is_alive is False
        warns = [
            r for r in caplog.records
            if r.message == "MCPClient transport close failed"
        ]
        assert len(warns) == 1, f"expected exactly one safety-net warning, got {warns}"
        assert warns[0].levelno == logging.WARNING

    async def test_worker_task_pattern_no_safety_net_log(
        self, monkeypatch, mock_session, caplog
    ) -> None:
        """L3 worker-task-per-entry pattern: connect + disconnect on same task; guard NOT triggered.

        Experimental verification that the F4 L3 worker-task-per-entry shape
        actually works against a real ``anyio.create_task_group()`` — this is
        the load-bearing assumption L3's design rests on.
        """
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _anyio_backed_transport_cm(mock_session),
        )
        caplog.set_level(logging.WARNING, logger="the_one.mcp.client")
        ready = asyncio.Event()
        evict = asyncio.Event()
        c = MCPClient(_stdio_source())

        async def _worker() -> None:
            await c.connect()
            ready.set()
            try:
                await evict.wait()
            finally:
                await c.disconnect()

        worker = asyncio.create_task(_worker())
        await ready.wait()
        evict.set()
        await worker
        assert worker.exception() is None
        assert c.is_alive is False
        warns = [
            r for r in caplog.records
            if r.message == "MCPClient transport close failed"
        ]
        assert warns == [], f"worker-task pattern leaked safety-net warning: {warns}"

    async def test_connect_failure_runs_stack_aclose(
        self, monkeypatch, mock_session
    ) -> None:
        """Connect failure (initialize raises) calls _transport_stack.aclose() and resets state.

        Spy via narrowly-scoped ``patch.object(AsyncExitStack, "aclose", ...)``
        with ``wraps=`` so real cleanup behavior is preserved while calls are
        recorded. ``>= 1`` smoke check; load-bearing observation is the
        post-cleanup state (``_transport_stack is None``, ``_session is None``,
        ``is_alive is False``).
        """
        # Use ValueError (not RuntimeError) — connect()'s `except RuntimeError`
        # branch translates RuntimeErrors as version mismatches; ValueError
        # falls through to the catch-all that wraps as MCPConnectionError.
        mock_session.initialize = AsyncMock(side_effect=ValueError("init failed"))
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _anyio_backed_transport_cm(mock_session),
        )
        c = MCPClient(_stdio_source())
        with patch.object(
            AsyncExitStack,
            "aclose",
            autospec=True,
            wraps=AsyncExitStack.aclose,
        ) as spy:
            with pytest.raises(MCPConnectionError):
                await c.connect()
            assert spy.call_count >= 1, (
                f"expected aclose to be called at least once, got {spy.call_count}"
            )
        assert c.is_alive is False
        assert c._transport_stack is None
        assert c._session is None

    async def test_disconnect_idempotent_with_stack(
        self, monkeypatch, mock_session, caplog
    ) -> None:
        """Idempotent disconnect across four scenarios with the new _transport_stack field.

        (a) never-connected disconnect is a no-op
        (b) connect → disconnect → disconnect is a no-op on the second
        (c) reconnect-after-disconnect produces a FRESH AsyncExitStack instance
            (live-ref ``is not`` comparison, NOT ``id()`` — CPython recycles
            ids of GC'd objects)
        (d) post-``_cleanup_after_failed_connect`` state: is_alive is False AND
            _transport_stack is None AND _session is None
        """
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _anyio_backed_transport_cm(mock_session),
        )

        # (a) never-connected disconnect — no raise, no state change.
        c_a = MCPClient(_stdio_source())
        await c_a.disconnect()
        assert c_a.is_alive is False
        assert c_a._transport_stack is None
        assert c_a._session is None

        # (b) connect → disconnect → disconnect: second is a no-op.
        c_b = MCPClient(_stdio_source())
        await c_b.connect()
        stack_first = c_b._transport_stack
        assert stack_first is not None
        await c_b.disconnect()
        assert c_b.is_alive is False
        assert c_b._transport_stack is None
        await c_b.disconnect()  # no raise; short-circuits via the early-return guard
        assert c_b._transport_stack is None

        # (c) reconnect-after-disconnect produces a fresh stack instance.
        # `is not` against the live `stack_first` ref — id-recycling-safe.
        await c_b.connect()
        stack_second = c_b._transport_stack
        assert stack_second is not None
        assert stack_second is not stack_first, (
            "reconnect must allocate a fresh AsyncExitStack — re-entry of a "
            "consumed stack is undefined behavior"
        )
        await c_b.disconnect()

        # (d) post-_cleanup_after_failed_connect state.
        # Use a fresh client whose initialize raises — drives the failure path.
        # ValueError (not RuntimeError) so connect()'s version-mismatch branch
        # doesn't claim it; the catch-all wraps it as MCPConnectionError.
        bad_session = MagicMock()
        bad_session.initialize = AsyncMock(side_effect=ValueError("bad init"))
        bad_session.list_tools = AsyncMock()
        bad_session.call_tool = AsyncMock()
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _anyio_backed_transport_cm(bad_session),
        )
        c_d = MCPClient(_stdio_source())
        with pytest.raises(MCPConnectionError):
            await c_d.connect()
        assert c_d.is_alive is False
        assert c_d._transport_stack is None
        assert c_d._session is None

    async def test_direct_cross_task_still_warns(
        self, monkeypatch, mock_session, caplog
    ) -> None:
        """F5 L1: control test — direct cross-task disconnect (outside
        pool routing) STILL produces the warning via the safety net.

        Locks the contract scope: F2-known-issue retirement applies only
        to F4-pool-routed (same-task) disconnects. Direct
        ``MCPClient(source)`` usage with cross-task disconnect continues
        to hit the safety net swallow.

        Mock-based (uses ``_anyio_backed_transport_cm``) is sufficient
        here because the test exercises the cross-task safety-net's
        ``except Exception`` clause, which is independent of the SDK
        transport stack.
        """
        monkeypatch.setattr(
            client_mod,
            "_transport_connect",
            lambda source: _anyio_backed_transport_cm(mock_session),
        )

        caplog.set_level(logging.WARNING, logger="the_one.mcp.client")
        client = MCPClient(_stdio_source())
        await client.connect()  # connect on test task (host task)

        # Cross-task disconnect — exits the cancel scope on a different
        # task; anyio's guard fires; safety-net swallow catches it.
        disconnect_task = asyncio.create_task(client.disconnect())
        await disconnect_task

        messages = [r.getMessage() for r in caplog.records]
        assert any(
            "MCPClient transport close failed" in m for m in messages
        ), f"expected cross-task warning; got: {messages}"
        assert client.is_alive is False


# ---------------------------------------------------------------------------
# L6a: list_tools + call_tool happy path — TestListToolsAndCallTool
# ---------------------------------------------------------------------------


class TestListToolsAndCallTool:
    """L6a unit tests using mocked ClientSession.

    Covers the happy paths for list_tools (mapping, always-refetches,
    not-connected guard) and call_tool (text-only result, text concatenation,
    structured content, unknown-tool guard, isError->MCPCallError, lazy
    cache population, not-connected guard, disconnect clears cache).

    Error-path translation (MCPArgumentError, asyncio.TimeoutError->
    MCPConnectionError, etc.) is L6b's territory.
    """

    async def test_list_tools_returns_mapped_dataclasses(
        self, patch_transport, mock_session
    ) -> None:
        """list_tools returns frozen MCPTool with correct field mapping."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result(
                [
                    _make_tool("echo", "Echoes input", {"type": "object"}),
                    _make_tool("add", "Adds two ints", {"type": "object"}),
                ]
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            tools = await c.list_tools()
        finally:
            await c.disconnect()

        assert len(tools) == 2
        assert tools[0].name == "echo"
        assert tools[0].description == "Echoes input"
        assert tools[0].input_schema == {"type": "object"}
        assert tools[0].output_schema is None
        assert tools[0].annotations is None
        assert tools[1].name == "add"
        # Frozen dataclass — must reject mutation.
        with pytest.raises(dataclasses.FrozenInstanceError):
            tools[0].name = "x"  # type: ignore[misc]

    async def test_list_tools_always_refetches(
        self, patch_transport, mock_session
    ) -> None:
        """Explicit list_tools always re-fetches from the server.

        The cache exists for call_tool's unknown-tool guard, NOT for
        short-circuiting list_tools itself. Two list_tools calls -> two
        SDK round-trips.
        """
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("echo")])
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            await c.list_tools()
            await c.list_tools()
        finally:
            await c.disconnect()
        assert mock_session.list_tools.await_count == 2

    async def test_list_tools_raises_when_not_connected(self) -> None:
        """list_tools on a never-connected client raises MCPConnectionError."""
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPConnectionError, match="not connected"):
            await c.list_tools()

    # F6.5 L2: 401 / OAuth → MCPAuthRequired translation tests

    async def test_list_tools_401_in_exception_group_raises_mcp_auth_required(
        self, patch_transport, mock_session
    ) -> None:
        """list_tools translates a 401 HTTPStatusError (inside BaseExceptionGroup)
        to MCPAuthRequired, parsing resource_metadata_url from WWW-Authenticate."""
        patch_transport(mock_session)
        response_401 = httpx.Response(
            status_code=401,
            headers={
                "WWW-Authenticate": (
                    'Bearer resource_metadata="https://example.com/.well-known/oauth-protected-resource"'
                )
            },
            request=httpx.Request("POST", "https://example.com/mcp"),
        )
        inner = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=response_401.request,
            response=response_401,
        )
        eg = BaseExceptionGroup("test group", [inner])
        mock_session.list_tools = AsyncMock(side_effect=eg)

        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPAuthRequired) as exc_info:
                await c.list_tools()
        finally:
            await c.disconnect()

        assert exc_info.value.source_id == c.source.id
        assert exc_info.value.resource_metadata_url == (
            "https://example.com/.well-known/oauth-protected-resource"
        )
        assert exc_info.value.consent_url is None

    async def test_list_tools_oauth_flow_error_raises_mcp_auth_required(
        self, patch_transport, mock_session
    ) -> None:
        """list_tools translates OAuthFlowError (bare or grouped) to MCPAuthRequired."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            side_effect=OAuthFlowError("discovery failed")
        )

        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPAuthRequired) as exc_info:
                await c.list_tools()
        finally:
            await c.disconnect()

        assert exc_info.value.source_id == c.source.id
        assert exc_info.value.resource_metadata_url is None
        assert exc_info.value.consent_url is None

    async def test_list_tools_oauth_token_error_raises_mcp_auth_required(
        self, patch_transport, mock_session
    ) -> None:
        """list_tools translates OAuthTokenError (bare or grouped) to MCPAuthRequired."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            side_effect=OAuthTokenError("refresh failed")
        )

        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPAuthRequired) as exc_info:
                await c.list_tools()
        finally:
            await c.disconnect()

        assert exc_info.value.source_id == c.source.id
        assert exc_info.value.resource_metadata_url is None
        assert exc_info.value.consent_url is None

    async def test_call_tool_text_only_result(
        self, patch_transport, mock_session
    ) -> None:
        """Single text content block flattens into MCPToolResult.text."""
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
        try:
            result = await c.call_tool("echo", {"message": "hi"})
        finally:
            await c.disconnect()

        assert result.text == "hi"
        assert result.raw == [{"type": "text", "text": "hi"}]
        assert result.structured is None
        assert result.is_error is False

    async def test_call_tool_text_concatenation(
        self, patch_transport, mock_session
    ) -> None:
        """Multiple text content blocks concatenate in order."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("echo")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_text_content("hello "), _make_text_content("world")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("echo", {})
        finally:
            await c.disconnect()

        assert result.text == "hello world"
        assert len(result.raw) == 2

    async def test_call_tool_structured_content(
        self, patch_transport, mock_session
    ) -> None:
        """structuredContent passes through; text + structured both present."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("add")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_text_content("3")],
                structured={"result": 3},
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("add", {"a": 1, "b": 2})
        finally:
            await c.disconnect()

        assert result.text == "3"
        assert result.structured == {"result": 3}
        assert result.is_error is False

    async def test_call_tool_unknown_tool_raises_before_wire_call(
        self, patch_transport, mock_session
    ) -> None:
        """Unknown tool name raises MCPToolNotFoundError BEFORE wire call."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("echo")])
        )
        mock_session.call_tool = AsyncMock()  # spy — should not be called
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPToolNotFoundError, match="nonexistent"):
                await c.call_tool("nonexistent", {})
            mock_session.call_tool.assert_not_called()
        finally:
            await c.disconnect()

    async def test_call_tool_iserror_raises_mcpcallerror(
        self, patch_transport, mock_session
    ) -> None:
        """isError=True raises MCPCallError carrying tool_name + server_message."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("echo")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_text_content("server failed")],
                structured=None,
                is_error=True,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPCallError, match="server failed") as exc_info:
                await c.call_tool("echo", {})
            assert exc_info.value.tool_name == "echo"
            assert exc_info.value.server_message == "server failed"
        finally:
            await c.disconnect()

    async def test_call_tool_populates_cache_lazily(
        self, patch_transport, mock_session
    ) -> None:
        """First call_tool without prior list_tools triggers exactly one
        internal list_tools round-trip (lazy cache populate)."""
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
        try:
            assert c._tools_cache is None
            result = await c.call_tool("echo", {"message": "hi"})
            assert mock_session.list_tools.await_count == 1
            assert result.text == "hi"
        finally:
            await c.disconnect()

    async def test_call_tool_raises_when_not_connected(self) -> None:
        """call_tool on a never-connected client raises MCPConnectionError."""
        c = MCPClient(_stdio_source())
        with pytest.raises(MCPConnectionError, match="not connected"):
            await c.call_tool("echo", {})

    async def test_disconnect_clears_tools_cache(
        self, patch_transport, mock_session
    ) -> None:
        """disconnect() resets _tools_cache to None so re-connect rebuilds."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("echo")])
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        await c.list_tools()
        assert c._tools_cache is not None
        await c.disconnect()
        # Private-state assertion intentionally — internal invariant for F4
        # pool reuse with no public surface.
        assert c._tools_cache is None


# ---------------------------------------------------------------------------
# L6b: input validation, content-block rendering, error-path translation
# ---------------------------------------------------------------------------


class TestCallToolInputValidation:
    """L6b unit tests for jsonschema-driven input validation.

    Validates `arguments` against the cached tool's input_schema BEFORE the
    wire call. On mismatch, raises MCPArgumentError WITHOUT calling the
    server (asserted via `mock.assert_not_called()`).
    """

    async def test_valid_args_pass_validation(
        self, patch_transport, mock_session
    ) -> None:
        """Args matching the schema pass validation and reach the wire."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result(
                [
                    _make_tool(
                        "t",
                        "",
                        {
                            "type": "object",
                            "properties": {"x": {"type": "string"}},
                        },
                    )
                ]
            )
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_text_content("ok")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {"x": "ok"})
            assert result.text == "ok"
            mock_session.call_tool.assert_awaited_once()
        finally:
            await c.disconnect()

    async def test_type_mismatch_raises_argument_error(
        self, patch_transport, mock_session
    ) -> None:
        """Type mismatch raises MCPArgumentError; wire call is NOT made."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result(
                [
                    _make_tool(
                        "t",
                        "",
                        {
                            "type": "object",
                            "properties": {"x": {"type": "string"}},
                        },
                    )
                ]
            )
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

    async def test_missing_required_field_raises_argument_error(
        self, patch_transport, mock_session
    ) -> None:
        """Missing required field raises MCPArgumentError; wire NOT called."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result(
                [
                    _make_tool(
                        "t",
                        "",
                        {
                            "type": "object",
                            "properties": {"x": {"type": "string"}},
                            "required": ["x"],
                        },
                    )
                ]
            )
        )
        mock_session.call_tool = AsyncMock()
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPArgumentError):
                await c.call_tool("t", {})
            mock_session.call_tool.assert_not_called()
        finally:
            await c.disconnect()

    async def test_extra_unknown_field_passes_validation(
        self, patch_transport, mock_session
    ) -> None:
        """Extra fields default-allowed by jsonschema (no additionalProperties: false)."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result(
                [
                    _make_tool(
                        "t",
                        "",
                        {
                            "type": "object",
                            "properties": {"x": {"type": "string"}},
                        },
                    )
                ]
            )
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_text_content("ok")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {"x": "ok", "extra": "ignored"})
            assert result.text == "ok"
        finally:
            await c.disconnect()

    async def test_no_schema_skips_validation(
        self, patch_transport, mock_session
    ) -> None:
        """Empty input_schema bypasses validation entirely (matches SDK permissiveness)."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t", "", {})])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_text_content("ok")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {"any": "thing"})
            assert result.text == "ok"
            mock_session.call_tool.assert_awaited_once()
        finally:
            await c.disconnect()


class TestCallToolContentBlockRendering:
    """L6b unit tests for non-text content-block placeholder rendering.

    MCPToolResult.text reflects ALL blocks in order — text passes through,
    non-text blocks render as `[image: N bytes, mime=...]` etc. The raw
    accumulator is unchanged (every block lands via model_dump).
    """

    async def test_image_block_placeholder(
        self, patch_transport, mock_session
    ) -> None:
        """ImageContent renders as `[image: N bytes, mime=...]`."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_image_content(data="abc", mime="image/png")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {})
            assert result.text == "[image: 3 bytes, mime=image/png]"
            assert len(result.raw) == 1
        finally:
            await c.disconnect()

    async def test_audio_block_placeholder(
        self, patch_transport, mock_session
    ) -> None:
        """AudioContent renders as `[audio: N bytes, mime=...]`."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_audio_content(data="xyz", mime="audio/wav")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {})
            assert result.text == "[audio: 3 bytes, mime=audio/wav]"
        finally:
            await c.disconnect()

    async def test_resource_link_block_placeholder(
        self, patch_transport, mock_session
    ) -> None:
        """ResourceLink renders as `[resource_link: <uri>]`."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_resource_link_content(uri="file:///x.txt")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {})
            assert result.text == "[resource_link: file:///x.txt]"
        finally:
            await c.disconnect()

    async def test_embedded_resource_block_placeholder(
        self, patch_transport, mock_session
    ) -> None:
        """EmbeddedResource renders as `[resource: <inner.uri>]`."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[_make_embedded_resource_content(uri="resource://r")],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {})
            assert result.text == "[resource: resource://r]"
        finally:
            await c.disconnect()

    async def test_mixed_text_and_image_concatenation(
        self, patch_transport, mock_session
    ) -> None:
        """Order preserved across mixed text/non-text blocks."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(
                content=[
                    _make_text_content("first "),
                    _make_image_content(data="abc", mime="image/png"),
                    _make_text_content(" last"),
                ],
                structured=None,
                is_error=False,
            )
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            result = await c.call_tool("t", {})
            assert result.text == "first [image: 3 bytes, mime=image/png] last"
            assert len(result.raw) == 3
        finally:
            await c.disconnect()


class TestCallToolErrorTranslation:
    """L6b unit tests for SDK error -> F2 wrapper-class translation.

    Covers the matrix from leg §error-translation: timeout, McpError,
    httpx.HTTPError, anyio.ClosedResourceError, and the critical
    UrlElicitationRequiredError pass-through (subclass-ordering invariant).
    """

    async def test_call_tool_timeout_raises_connection_error(
        self, patch_transport, mock_session
    ) -> None:
        """asyncio.TimeoutError in call_tool wraps as MCPConnectionError."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(side_effect=asyncio.TimeoutError())
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPConnectionError, match="exceeded"):
                await c.call_tool("t", {})
        finally:
            await c.disconnect()

    async def test_list_tools_timeout_raises_connection_error(
        self, patch_transport, mock_session
    ) -> None:
        """asyncio.TimeoutError in list_tools wraps as MCPConnectionError."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(side_effect=asyncio.TimeoutError())
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPConnectionError, match="list_tools exceeded"):
                await c.list_tools()
        finally:
            await c.disconnect()

    async def test_call_tool_mcp_error_raises_mcp_call_error(
        self, patch_transport, mock_session
    ) -> None:
        """McpError from the SDK wraps as MCPCallError carrying the message."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            side_effect=McpError(ErrorData(code=-32600, message="boom"))
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPCallError, match="boom") as exc_info:
                await c.call_tool("t", {})
            assert exc_info.value.tool_name == "t"
            assert exc_info.value.server_message == "boom"
        finally:
            await c.disconnect()

    async def test_call_tool_httpx_error_raises_connection_error(
        self, patch_transport, mock_session
    ) -> None:
        """httpx.HTTPError wraps as MCPConnectionError ('transport error')."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(side_effect=httpx.HTTPError("boom"))
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPConnectionError, match="transport error"):
                await c.call_tool("t", {})
        finally:
            await c.disconnect()

    async def test_call_tool_closed_resource_raises_connection_error(
        self, patch_transport, mock_session
    ) -> None:
        """anyio.ClosedResourceError wraps as MCPConnectionError ('transport error')."""
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            side_effect=anyio.ClosedResourceError()
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(MCPConnectionError, match="transport error"):
                await c.call_tool("t", {})
        finally:
            await c.disconnect()

    async def test_url_elicitation_propagates_through_call_tool_wrapper(
        self, patch_transport, mock_session
    ) -> None:
        """UrlElicitationRequiredError MUST pass through unchanged.

        Mechanical guard against accidental regression of the explicit
        `except UrlElicitationRequiredError: raise` clause ordered BEFORE
        `except McpError`. Without that ordering, the prompt would be
        silently swallowed into MCPCallError (verified at L6b design review:
        `issubclass(UrlElicitationRequiredError, McpError) == True`).
        """
        patch_transport(mock_session)
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_tools_result([_make_tool("t")])
        )
        mock_session.call_tool = AsyncMock(
            side_effect=UrlElicitationRequiredError([])
        )
        c = MCPClient(_stdio_source())
        await c.connect()
        try:
            with pytest.raises(UrlElicitationRequiredError):
                await c.call_tool("t", {})
        finally:
            await c.disconnect()


# ---------------------------------------------------------------------------
# L4: streamable-http transport — TestBuildRequestHeaders + TestConnectStreamableHttpProduction
# ---------------------------------------------------------------------------


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
        from unittest.mock import MagicMock

        import httpx

        from the_one.mcp.transports import streamable_http as sh

        # Capture the http_client argument the SDK receives.
        captured: dict[str, httpx.AsyncClient] = {}

        @asynccontextmanager
        async def fake_streamable_http_client(url, *, http_client, **kwargs):
            captured["http_client"] = http_client
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
        monkeypatch.setattr(sh, "_test_http_client_override", None)

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


# ---------------------------------------------------------------------------
# L5: stdio transport — TestBuildStdioEnviron (pure-Python env-merge precedence)
# ---------------------------------------------------------------------------


def _stdio_source_for_env_test(
    *,
    env: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
) -> MCPSource:
    """Build a stdio MCPSource for build_stdio_environ unit tests.

    `env` controls whether `config["env"]` is set at all (None → key absent,
    so the helper's `.get("env", {}) or {}` defensive default is exercised).
    """
    config: dict[str, object] = {"command": "echo", "args": []}
    if env is not None:
        config["env"] = env
    return MCPSource(
        id="src-env-test",
        name="t",
        type="stdio",
        config=config,
        secrets=secrets or {},
    )


class TestBuildStdioEnviron:
    """Pure-Python tests for build_stdio_environ's 2-layer flat-merge contract.

    Per flight 02 §11: precedence order (lowest → highest) is allowlist_env,
    config["env"], source.secrets. Secrets win over BOTH allowlist and
    config.env on key collision (operator-marked-sensitive trumps everything).
    """

    def test_allowlist_only(self) -> None:
        src = _stdio_source_for_env_test()
        allowlist = {"PATH": "/usr/bin", "HOME": "/home/x"}
        assert build_stdio_environ(src, allowlist) == allowlist

    def test_config_env_only(self) -> None:
        src = _stdio_source_for_env_test(env={"FOO": "bar"})
        assert build_stdio_environ(src, {}) == {"FOO": "bar"}

    def test_secrets_only(self) -> None:
        src = _stdio_source_for_env_test(secrets={"TOKEN": "abc"})
        assert build_stdio_environ(src, {}) == {"TOKEN": "abc"}

    def test_mixed_no_collision(self) -> None:
        src = _stdio_source_for_env_test(
            env={"FOO": "bar"},
            secrets={"TOKEN": "abc"},
        )
        result = build_stdio_environ(src, {"PATH": "/usr/bin"})
        assert result == {"PATH": "/usr/bin", "FOO": "bar", "TOKEN": "abc"}

    def test_secrets_win_over_config_env(self) -> None:
        src = _stdio_source_for_env_test(
            env={"OVERRIDE": "config-value"},
            secrets={"OVERRIDE": "secret-value"},
        )
        assert build_stdio_environ(src, {}) == {"OVERRIDE": "secret-value"}

    def test_secrets_win_over_allowlist(self) -> None:
        src = _stdio_source_for_env_test(secrets={"PATH": "/operator-override"})
        assert build_stdio_environ(src, {"PATH": "/usr/bin"}) == {
            "PATH": "/operator-override"
        }

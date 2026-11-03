"""MCPClient — async wrapper around the mcp 2.x SDK's ClientSession.

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
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

import anyio
import httpx2
from jsonschema import ValidationError
from jsonschema import validate as jsonschema_validate
from mcp.client.auth.exceptions import OAuthFlowError, OAuthTokenError
from mcp.shared.exceptions import MCPError, UrlElicitationRequiredError
from mcp.types import (
    SERVER_INFO_META_KEY,
    UNSUPPORTED_PROTOCOL_VERSION,
    InputRequiredResult,
    UnsupportedProtocolVersionErrorData,
)
from mcp.types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS

from the_one.db.models import MCPSource
from the_one.mcp import _era
from the_one.mcp._arg_coerce import coerce_arguments
from the_one.mcp._negotiate import DiscoverSignInRequired, negotiate
from the_one.mcp._signin_record import (
    MAX_SSE_EVENT_BYTES,
    AuthRecord,
    auth_record_for,
    saw_401_since,
)
from the_one.mcp.errors import (
    TOKEN_FAILURE_MARKERS,
    MCPArgumentError,
    MCPAuthRequired,
    MCPCallError,
    MCPCapabilityMissing,
    MCPClientError,
    MCPConnectionError,
    MCPCredentialsRejected,
    MCPToolNotFoundError,
    MCPVersionMismatch,
)
from the_one.mcp.types import MCPTool, MCPToolResult

if TYPE_CHECKING:
    from mcp import ClientSession  # type-only; SDK not loaded at module-load
    from mcp.types import Implementation, ServerCapabilities

logger = logging.getLogger(__name__)

_UNSUPPORTED_VERSION_RE = re.compile(r"Unsupported protocol version from the server: (.+)")

# Sentinel for "use the runtime default from the_one.mcp" — distinguishes
# "caller passed nothing" from "caller explicitly passed None/0". We don't
# bind the constant at function-definition time so test monkeypatches of
# the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS would still propagate (defense
# in depth — F2 only mandates _HANDSHAKE_OFFER_VERSION read-at-call-time).
_DEFAULT = object()

_SESSION_TERMINATED_MESSAGE = "Session terminated"
"""The SDK's synthetic error message for "this session no longer exists".

``mcp.client.streamable_http`` (2.x) answers a 404 on a request-carrying POST
for which the server HAD issued an ``Mcp-Session-Id`` by fabricating a
JSON-RPC ``INVALID_REQUEST`` error with this exact message (built inline in
``StreamableHTTPTransport._handle_post_request``) rather than surfacing a
transport exception. It means the server has forgotten our session — a DEAD
CONNECTION, not a tool that failed. (A 404 with NO session id issued reads
``METHOD_NOT_FOUND "Not Found"`` instead; for a stateless server that is its
whole connection lifetime, so there is no self-heal there — Mission 29 DD12.3.)
Servers reach this state by
their own session GC, a restart, or by treating a dropped SSE stream as a client
disconnect.

Matching on the message is the only signal available: the 404 is swallowed
inside the SDK and the accompanying code (32600) is generic.
``TestSessionTerminatedRecovery`` in ``tests/test_mcp_client.py`` pins the
string against the SDK (by driving a real 404 with a session id set) so a
rename in a future SDK release fails loudly here rather than silently
reverting the self-heal to the old wedge-until-manual-reset behaviour.
"""


def _is_session_terminated(exc: MCPError) -> bool:
    """True when ``exc`` is the SDK's synthetic session-is-gone error."""
    return getattr(getattr(exc, "error", None), "message", None) == _SESSION_TERMINATED_MESSAGE


_SSE_CAP_PREFIX = "SSE stream failed:"
_SSE_CAP_MARKER = "byte limit"
_SSE_CONNECTION_CLOSED = -32000
_SSE_CAP_MESSAGE = (
    f"MCP server sent a single event larger than the {MAX_SSE_EVENT_BYTES}-byte "
    f"({MAX_SSE_EVENT_BYTES // (1024 * 1024)} MiB) limit"
)


def _is_sse_cap_error(exc: BaseException) -> bool:
    """True when ``exc`` is the SDK's abandoned-request error for an SSE event
    over ``max_sse_event_size`` (DD8): code -32000 (CONNECTION_CLOSED), message
    starting ``SSE stream failed:`` and containing ``byte limit``. Any other
    -32000 error (e.g. "SSE stream ended without a response") is not matched."""
    if not isinstance(exc, MCPError):
        return False
    return (
        exc.code == _SSE_CONNECTION_CLOSED
        and exc.message.startswith(_SSE_CAP_PREFIX)
        and _SSE_CAP_MARKER in exc.message
    )


_INPUT_REQUIRED_MESSAGE = "the server asked for extra input, which the-one can't provide yet"
"""The one plain line an operator and the model see when a tool asks for input
(Mission 29 Flight 2, DD8)."""


def _supported_in_error(exc: MCPError) -> list[str] | None:
    """The ``supported`` revision list of a -32022 error, or None when its data
    is absent or doesn't parse as ``UnsupportedProtocolVersionErrorData``."""
    try:
        return UnsupportedProtocolVersionErrorData.model_validate(exc.data).supported
    except Exception:
        return None


def _shares_no_version(supported: list[str] | None) -> bool:
    """True iff ``supported`` parsed and intersects the-one's revisions in nothing."""
    if supported is None:
        return False
    return not set(supported) & {*HANDSHAKE_PROTOCOL_VERSIONS, *MODERN_PROTOCOL_VERSIONS}


@asynccontextmanager
async def _transport_connect(
    source: MCPSource,
    *,
    auth_provider: httpx2.Auth | None = None,
) -> AsyncIterator["ClientSession"]:
    """Dispatch on source.type. Outward shape preserved for test contract.

    Body uses non-CM transport helpers (introduced in F5 L1) +
    explicit ``await stack.aclose()`` in finally — collapses the
    the-one-owned ``@asynccontextmanager`` wrapper layer from the
    dispatcher's exit chain. MAY retire the F4-HAT-Finding-#1 warning
    for same-task (F4-pool-routed) disconnects; verified at F5 L6 HAT.

    Yields a connected ClientSession (entered, but not yet initialized).
    Caller is responsible for calling ``session.initialize()`` and final
    cleanup via the returned CM's ``__aexit__``.

    The existing ``@asynccontextmanager`` ``connect_streamable_http`` and
    ``connect_stdio`` helpers are NOT consumed by this dispatcher post-F5
    L1 — they remain in place for back-compat with their direct
    async-with callers (1 + 9 = 10 tests; citation-audit-verified at L1
    design 2026-05-07).

    F5 L4: ``auth_provider`` is threaded to the streamable-http transport
    when the source is streamable-http; the stdio branch ignores it (no
    auth applicable for local subprocess transports). Provider
    construction is L6's scope — L4 only adds the passthrough seam.
    """
    if source.type == "streamable-http":
        from the_one.mcp.transports.streamable_http import (
            _open_streamable_http_transport_stack,
        )

        session, stack = await _open_streamable_http_transport_stack(
            source, auth_provider=auth_provider
        )
    elif source.type == "stdio":
        # F5 L4: auth_provider is transport-irrelevant for stdio (no HTTP);
        # silently ignored. No assertion or warning — keeps the dispatcher
        # uniform across transports.
        from the_one.mcp.transports.stdio import _open_stdio_transport_stack

        session, stack = await _open_stdio_transport_stack(source)
    else:
        # Defensive exhaustiveness — Pydantic Literal gates the type at model
        # validation time, so this branch is unreachable in normal flow.
        # Locks the contract that any future transport literal must extend
        # this dispatch (mirrors F1's defensive `else: raise` exhaustiveness).
        raise MCPClientError(f"unknown MCP transport type: {source.type!r}")
    try:
        yield session
    finally:
        await stack.aclose()


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
        # F5 L4: auth_provider is provided pre-built by the caller; provider
        # construction (factory function that reads secrets["dcr_credentials"]
        # and instantiates OAuthClientProvider) is L6's scope. L4 only adds
        # the passthrough seam.
        auth_provider: httpx2.Auth | None = None,
        # Mission 29 F2 (DD2): ``fresh_negotiation`` ignores the remembered era
        # (a Test connection always re-discovers); ``record_era=False`` suppresses
        # BOTH remember_era and forget_era (a Test run against a body-override
        # config must not touch the saved source's memory).
        fresh_negotiation: bool = False,
        record_era: bool = True,
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
        self._auth_provider: httpx2.Auth | None = auth_provider
        self.fresh_negotiation: bool = fresh_negotiation
        self.record_era: bool = record_era

        self._session: ClientSession | None = None
        self._capabilities: ServerCapabilities | None = None
        self._protocol_version: str | None = None
        # F4 L2 (M08): server-declared identity + free-form usage prose from the
        # MCP initialize() response. Optional in the spec (servers MAY omit
        # either); when present they let the agent-editor Tools tab surface a
        # subtitle line + hover tooltip without forcing a fresh probe. Stored
        # as model instance / raw str respectively so callers choose how to
        # serialize; the `server_info` property emits the JSON-mode dump.
        self._server_info: Implementation | None = None
        self._instructions: str | None = None
        # F4 L3 (M08): InitializeResult._meta — arbitrary server-supplied
        # metadata, spec-optional and free-shape. Stored as a plain dict so
        # the editor surface can render it generically without coupling to
        # any specific server's vocabulary. None when omitted by the server.
        self._meta: dict[str, Any] | None = None
        self._is_alive: bool = False
        # Exact 0.0 sentinel — time.monotonic() never returns 0 on a running
        # system, so `last_activity > 0.0` is meaningful. None would crash
        # __repr__'s `f"{x:.2f}"` — see flight §9 / leg AC.
        self._last_activity: float = 0.0
        self._transport_stack: AsyncExitStack | None = None  # owns the _transport_connect cm
        # Tools cache — populated on first list_tools() or first call_tool()
        # (whichever fires first). Used by call_tool's unknown-tool guard and
        # by L6b's input-schema validation. Cleared on disconnect so a re-
        # connect rebuilds fresh (tools may change between sessions).
        self._tools_cache: list[MCPTool] | None = None
        # DD6: the task that entered the transport stack in connect(). A
        # CancelledError caught on any other task cannot be the transport's
        # internal cancel-scope fallout, so list_tools/call_tool re-raise it.
        self._owner_task: asyncio.Task[Any] | None = None

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
            raise MCPConnectionError("MCPClient is not connected; cannot read server_capabilities.")
        return self._capabilities.model_dump(mode="json", by_alias=True)

    @property
    def server_info(self) -> dict[str, Any] | None:
        """Server-declared identity (``name``/``title``/``version``/``websiteUrl``).

        Mirrors ``server_capabilities`` — guards on ``_is_alive``, returns
        the JSON-mode model dump with ``None`` fields excluded so the cache
        payload stays compact. Returns ``None`` when the server omits
        ``serverInfo`` from its initialize() response (spec-optional).
        """
        if not self._is_alive:
            raise MCPConnectionError("MCPClient is not connected; cannot read server_info.")
        if self._server_info is None:
            return None
        return self._server_info.model_dump(mode="json", by_alias=True, exclude_none=True)

    @property
    def instructions(self) -> str | None:
        """Server-supplied free-form usage prose, if any.

        Spec-optional; servers like Cloudflare Docs MCP populate it with
        substantial guidance. Returns ``None`` when the server omits it.
        """
        if not self._is_alive:
            raise MCPConnectionError("MCPClient is not connected; cannot read instructions.")
        return self._instructions

    @property
    def meta(self) -> dict[str, Any] | None:
        """Server-supplied ``_meta`` from the InitializeResult, if any.

        Spec-optional; free-shape ``dict[str, Any]``. Returns ``None`` when
        the server omits ``_meta``. Guards on ``_is_alive`` mirroring the
        ``server_info`` / ``instructions`` pattern.
        """
        if not self._is_alive:
            raise MCPConnectionError("MCPClient is not connected; cannot read meta.")
        return self._meta

    def __repr__(self) -> str:
        return (
            f"MCPClient(name={self.source.name!r}, type={self.source.type!r}, "
            f"is_alive={self._is_alive}, last_activity={self._last_activity:.2f})"
        )

    def _touch_activity(self) -> None:
        self._last_activity = time.monotonic()

    def _mark_dead(self) -> None:
        """Flip ``_is_alive`` off after an unrecoverable transport failure.

        The F4 pool reads ``is_alive`` on every ``acquire`` and evicts +
        rebuilds an entry whose client has gone dead, so marking here is what
        turns a permanently-wedged connection into one failed call followed by
        a transparent reconnect. Purely a flag flip — teardown stays with
        ``disconnect()``, which the pool's entry worker runs on the task that
        ran ``connect()`` (anyio cross-task cancel-scope guard).
        """
        self._is_alive = False

    def _auth_required_since(
        self, record: AuthRecord | None, baseline: int
    ) -> MCPClientError | None:
        """DD1: a sign-in signal (see :meth:`_signin_signal`) iff the most recent MCP-POST
        response after ``baseline`` was a 401, else None.

        ``record`` is the connection's :func:`auth_record_for` entry (None for a
        patched transport). Never gated on an error code or message text: a 401
        whose body is a JSON-RPC error reaches the caller as the server's own
        ``MCPError`` code. The caller must read ``record`` BEFORE ``connect``'s
        cleanup branches clear ``self._session``.
        """
        if record is None or not saw_401_since(record, baseline):
            return None
        return self._signin_signal(record.last_resource_metadata)

    def _signin_signal(self, resource_metadata_url: str | None) -> MCPClientError:
        """The ONE place a 401 becomes a typed result.

        :class:`MCPCredentialsRejected` exactly when the source carries
        operator-supplied request headers, the 401 named no ``resource_metadata``
        and no OAuth provider is attached (the operator gave a key, the server
        refused it and offers no sign-in); otherwise :class:`MCPAuthRequired`.
        """
        if (
            resource_metadata_url is None
            and self._auth_provider is None
            and self.source.type == "streamable-http"
        ):
            # Sortie 09 DD3: a source that CONFIGURES any header name counts as
            # credentials evidence even when every value is blank (blank values
            # are no longer sent, so a non-empty request-header dict is not the
            # test). The client's source is already the effective one.
            from the_one.mcp._overrides import configured_names, missing_values

            if configured_names(self.source):
                return MCPCredentialsRejected(
                    source_id=self.source.id,
                    source_name=self.source.name,
                    missing=missing_values(self.source, self.source),
                )
        return MCPAuthRequired(
            source_id=self.source.id,
            source_name=self.source.name,
            resource_metadata_url=resource_metadata_url,
            consent_url=None,
        )

    def _on_owner_task(self) -> bool:
        """DD6: True iff the current task is the one that ran ``connect``.
        ``_owner_task is None`` (never connected / after disconnect) is "not owner"."""
        return self._owner_task is not None and asyncio.current_task() is self._owner_task

    def _oauth_flow_auth_required(self) -> MCPAuthRequired:
        """The MCPAuthRequired the three ``except* (OAuthFlowError, OAuthTokenError)``
        blocks raise: the auth flow failed before any challenge surfaced, so there
        is no resource-metadata URL and no consent URL."""
        return MCPAuthRequired(
            source_id=self.source.id,
            source_name=self.source.name,
            resource_metadata_url=None,
            consent_url=None,
        )

    def _classify_failure(
        self,
        exc: BaseException,
        *,
        op: str,
        baseline: int,
        record: AuthRecord | None = None,
        tool_name: str | None = None,
    ) -> Exception | None:
        """DD5: the typed exception for the shared failure-matrix rows, else None.

        ``op`` is ``"connect"``, ``"list_tools"`` or ``"call_tool"``. First match
        wins: (0) ``DiscoverSignInRequired`` (negotiation's deferred discover 401) gives
        ``MCPAuthRequired`` or ``MCPCredentialsRejected`` (``_signin_signal``); (1)
        ``UrlElicitationRequiredError`` passes through unchanged in
        ``list_tools``/``call_tool`` (``connect`` leaves it to its generic arm, which
        wraps it); (2) a 401 as the last MCP-POST response since ``baseline`` gives
        ``MCPAuthRequired`` or ``MCPCredentialsRejected`` (``_signin_signal``); (3) a -32022
        protocol-version rejection; (4) the SSE
        size cap; (5) a terminated session. Row 6 (input required) is a result
        branch in ``call_tool``. ``None`` means the caller's own arm applies. The
        caller keeps its cleanup and must have read ``record`` before it.
        """
        if op != "connect" and isinstance(exc, UrlElicitationRequiredError):
            return exc
        if isinstance(exc, DiscoverSignInRequired):
            # Leg discover-401-signin: discover was answered 401 and the handshake
            # failed after it, so the record's last status no longer shows the 401.
            signal = self._signin_signal(exc.resource_metadata_url)
        else:
            signal = self._auth_required_since(record, baseline)
        if signal is not None:
            if isinstance(signal, MCPCredentialsRejected) and op != "connect":
                # A corrected header (or agent override) takes effect on the next
                # acquire, not after the pool reaps this entry.
                self._mark_dead()
            return signal
        if not isinstance(exc, MCPError):
            return None
        if exc.code == UNSUPPORTED_PROTOCOL_VERSION:
            supported = _supported_in_error(exc)
            if op == "connect":
                if _shares_no_version(supported):
                    from the_one import mcp as the_one_mcp

                    return MCPVersionMismatch(
                        pinned=the_one_mcp._HANDSHAKE_OFFER_VERSION,
                        observed=", ".join(supported or []),
                    )
                return None
            self._mark_dead()
            _era.forget_era(self.source.id)
            if _shares_no_version(supported):
                from the_one import mcp as the_one_mcp

                return MCPVersionMismatch(
                    pinned=the_one_mcp._HANDSHAKE_OFFER_VERSION,
                    observed=", ".join(supported or []),
                )
            return MCPConnectionError(
                f"MCP {op} failed: the server changed protocol revision; "
                "the connection will be re-established on the next call."
            )
        if _is_sse_cap_error(exc):
            # DD8: an oversized event is one bad response, not a dead connection.
            if op == "connect":
                return MCPConnectionError(f"MCP connect failed: {_SSE_CAP_MESSAGE}")
            if op == "list_tools":
                return MCPConnectionError(f"MCP list_tools failed: {_SSE_CAP_MESSAGE}")
            return MCPCallError(tool_name=tool_name or "", server_message=_SSE_CAP_MESSAGE)
        if op != "connect" and _is_session_terminated(exc):
            # The server forgot our session: a dead CONNECTION, not a failed tool.
            self._mark_dead()
            if op == "list_tools":
                return MCPConnectionError(f"MCP list_tools failed: {exc}")
            return MCPConnectionError(
                f"MCP session terminated by server during call to {tool_name!r}; "
                "the connection will be re-established on the next call."
            )
        return None

    async def connect(self) -> None:
        """Run the MCP lifecycle handshake.

        Steps: open transport, negotiate (modern ``server/discover`` first, falling
        back to ``initialize``), version-gate, capability-gate.

        On success: ``_is_alive=True``, ``_capabilities`` and ``_protocol_version``
        populated. On failure: state restored to disconnected (transport stack
        closed or abandoned) and one of the typed exceptions below raised.

        Raises:
            MCPConnectionError: Already-connected guard; initialize timeout; transport-layer
                non-401 failures; cleanup-deadlock recovery diagnostics. Catchall.
            MCPVersionMismatch: Server announces a protocolVersion outside the SDK's
                HANDSHAKE_PROTOCOL_VERSIONS set.
            MCPAuthRequired: SDK auth-flow exceptions (OAuthFlowError / OAuthTokenError) or
                a 401 as the last MCP-POST response of this connect (DD1: the transport's
                response-hook record). resource_metadata_url populated only on the
                WWW-Authenticate path.
            MCPCapabilityMissing: Server initialize result lacks the tools capability.
            SandboxError: Stdio transport only — bwrap rejected the spawn (writable_paths
                invalid, EPERM on unshare, bwrap missing) before the target exec'd.
        """
        if self._is_alive:
            raise MCPConnectionError("MCPClient is already connected.")
        try:
            await self._connect_once()
        except asyncio.CancelledError:
            raise  # cancellation is not an era verdict
        except BaseException:
            if self.record_era:
                _era.forget_era(self.source.id)
            raise

    async def _connect_once(self) -> None:
        """The body of :meth:`connect` after the already-connected guard."""
        # Lazy SDK-namespace import — keeps test monkeypatch hooks alive
        # for the_one.mcp._HANDSHAKE_OFFER_VERSION (read-at-call-time per F2).
        from the_one import mcp as the_one_mcp

        pinned = the_one_mcp._HANDSHAKE_OFFER_VERSION

        # DD6: this task owns the transport stack entered below.
        self._owner_task = asyncio.current_task()
        # DD1: the connection's 401 record, read into a local the moment the
        # session exists so the cleanup branches below (which clear
        # ``self._session``) cannot lose it. A fresh record starts at seq 0.
        auth_rec: AuthRecord | None = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                # Single-line construction-and-enter to make the "stack is
                # always entered when assigned" invariant locally obvious.
                # AsyncExitStack.__aenter__ returns self.
                self._transport_stack = await AsyncExitStack().__aenter__()
                # F5 L4: only thread auth_provider when set, so test
                # fixtures that monkeypatch ``_transport_connect`` with a
                # single-positional lambda (e.g. ``patch_transport`` at
                # ``tests/test_mcp_client.py``) keep working unmodified
                # per A12's "existing tests pass UNMODIFIED" contract.
                if self._auth_provider is not None:
                    session = await self._transport_stack.enter_async_context(
                        _transport_connect(self.source, auth_provider=self._auth_provider)
                    )
                else:
                    session = await self._transport_stack.enter_async_context(
                        _transport_connect(self.source)
                    )
                self._session = session
                auth_rec = auth_record_for(session)
                # F6.6 L1: nested innermost try wrapping ONLY session.initialize()
                # so the SDK's auth-flow exceptions (OAuthFlowError,
                # OAuthTokenError) are translated to MCPAuthRequired at the same
                # structural level as the F6.5 L2 list_tools pattern. Python
                # forbids mixing `except` and `except*` in one try block; the
                # existing `except RuntimeError` clause for version-mismatch
                # translation MUST stay at the outer try level. The 401-record check in the outer
                # `except (Exception, BaseExceptionGroup)` block below is the
                # path for transport-layer 401s (mcp 2.x no longer raises
                # HTTPStatusError; DD1 reads the transport's response-hook
                # record instead); F6.6 only adds the OAuth-exception path.
                try:
                    try:
                        remembered = (
                            None if self.fresh_negotiation else _era.era_for(self.source.id)
                        )
                        await negotiate(session, remembered=remembered)
                    except* (OAuthFlowError, OAuthTokenError):
                        # SDK's auth flow failed during initialize (refresh /
                        # discovery / DCR). Translate to MCPAuthRequired so
                        # MCPToolProvider's graceful-skip path (post-F6.5 L2)
                        # catches it cleanly via _pool._entry_worker's
                        # `except BaseException → entry.failure` capture.
                        # resource_metadata_url and consent_url are None
                        # because we don't have a WWW-Authenticate response
                        # at this point — the auth flow failed before the
                        # server's challenge could surface. F5's chat-path
                        # lazy-OAuth flow re-runs at next tool call when the
                        # operator re-establishes credentials.
                        raise self._oauth_flow_auth_required() from None
                except RuntimeError as e:
                    m = _UNSUPPORTED_VERSION_RE.match(str(e))
                    observed = m.group(1) if m else str(e)
                    raise MCPVersionMismatch(pinned=pinned, observed=observed) from None
        except asyncio.TimeoutError:
            auth_required = self._auth_required_since(auth_rec, 0)
            await self._cleanup_after_failed_connect()
            if auth_required is not None:
                raise auth_required from None
            raise MCPConnectionError(
                f"MCP server {TOKEN_FAILURE_MARKERS[0]} within {self.timeout_seconds} "
                f"seconds during initialize."
            ) from None
        except (MCPClientError, NotImplementedError):
            await self._cleanup_after_failed_connect()
            raise
        except asyncio.CancelledError as e:
            # DD1: in 2.3.0 an auth-flow failure raised inside the transport's
            # task group can surface as a bare CancelledError; the 401 record
            # (read BEFORE the session reference is dropped) is the signal.
            auth_required = self._auth_required_since(auth_rec, 0)
            if auth_required is not None:
                self._transport_stack = None
                self._session = None
                raise auth_required from e
            # F6 A5: SDK's anyio task-group cleanup chain after a non-OAuth,
            # non-401 transport-level failure ends with the surrounding task
            # cancelled. (Post-F6.6 L1: OAuth-flow exceptions are now caught
            # by the inner `except*` block above; transport-layer 401s are
            # caught by the outer BaseExceptionGroup walk below — neither
            # reaches this path.) Calling _cleanup_after_failed_connect from
            # this path re-triggers the cross-task cancel-scope guard inside
            # the SDK and either hangs or re-raises CancelledError. Abandon
            # the transport stack reference (leak the partial connection —
            # GC + process shutdown will clean up) and translate to
            # MCPConnectionError so MCPToolProvider's class #2 graceful-
            # degrade catches it. Do NOT await further cleanup.
            self._transport_stack = None
            self._session = None
            raise MCPConnectionError(
                f"MCP connect failed: {TOKEN_FAILURE_MARKERS[1]} "
                f"(cross-task cleanup deadlock; original cause likely "
                f"transport error or malformed initial response): {e}"
            ) from e
        except (Exception, BaseExceptionGroup) as e:
            # F6 A5 fix: extend catch list to BaseExceptionGroup. The SDK's
            # streamable-http transport wraps cleanup in an anyio task group;
            # when the inner task hits an HTTP error (e.g. 401) AND the
            # cleanup tries to exit the task-group's cancel scope on a
            # different task, the result is a ``BaseExceptionGroup`` (not
            # an ``Exception`` — BaseExceptionGroup extends BaseException
            # only). Without this catch, the group escapes upward,
            # ``MCPToolProvider.get_tools_for_agent``'s class #2 handler
            # (which catches SandboxError/MCPConnectionError/
            # MCPVersionMismatch) misses it, and the agent build crashes
            # rather than graceful-degrade-skipping the source. Walk the
            # group recursively for an inner 401 to translate to
            # MCPAuthRequired; otherwise collapse to MCPConnectionError so
            # graceful-degrade catches uniformly.
            #
            # Cleanup is wrapped in a 3s timeout because the SDK's anyio
            # task group can deadlock on aclose() when the cross-task
            # cancel-scope guard already fired during initialize() — the
            # cleanup chain re-enters the same machinery and waits on a
            # task that will never complete. Abandoning the transport stack
            # leaks the partially-open subprocess/HTTP connection; the F4
            # pool's _entry_worker exit handler (or process shutdown) will
            # eventually GC it. Better to leak than to hang the agent build.
            async def _safe_cleanup() -> None:
                try:
                    # ``asyncio.timeout`` runs the cleanup in THIS task on 3.11
                    # and 3.12 alike. ``wait_for`` runs it in a child task on
                    # 3.11 (3.12 inlined it), and the SDK's anyio cancel scope
                    # then gets exited from a task other than the one that
                    # entered it, cancelling the connecting task (squawk 0251).
                    async with asyncio.timeout(3.0):
                        await self._cleanup_after_failed_connect()
                except (
                    asyncio.TimeoutError,
                    asyncio.CancelledError,
                    Exception,
                    BaseExceptionGroup,
                ):
                    logger.warning(
                        "MCP transport cleanup timed out or raised after "
                        "connect-failure; abandoning the transport stack "
                        "(F6 A5: SDK task-group cross-task deadlock)",
                    )
                    # Abandon the stack reference so future operations don't
                    # try to re-enter the wedged cleanup chain. The leak is
                    # a partially-open subprocess/HTTP connection; bounded
                    # by process lifetime. F9 L2: include CancelledError
                    # in the catch list — both wait_for's timeout-driven
                    # cancellation of the inner coroutine and the SDK's
                    # anyio cross-task cancel-scope guard surface as bare
                    # CancelledError (BaseException, not Exception). The
                    # outer `except (Exception, BaseExceptionGroup)` arm
                    # has already committed to translating to
                    # MCPConnectionError; allowing CancelledError to leak
                    # from cleanup here violates the four-typed-exceptions
                    # contract on the D1 stdio Test route. Caller-side
                    # cancellation is handled by the dedicated outer
                    # `except asyncio.CancelledError` at line 301, which
                    # also translates rather than propagates — this stays
                    # consistent with that policy.
                    self._transport_stack = None
                    self._session = None

            # DD1: every failure after a request was sent consults the 401
            # record first (MCPError of any code, BaseExceptionGroup, generic
            # Exception) - never the error code or message text.
            classified = self._classify_failure(e, op="connect", baseline=0, record=auth_rec)
            if classified is not None:
                await _safe_cleanup()
                raise classified from None
            await _safe_cleanup()
            raise MCPConnectionError(f"MCP connect failed: {type(e).__name__}: {e}") from e

        # F6 A6 fix (post-F2-debrief): align with the SDK's supported set
        # rather than a single pinned revision (strict equality was too narrow:
        # servers announcing an older revision tripped the gate). Rebuilt on
        # ``mcp.types.version.HANDSHAKE_PROTOCOL_VERSIONS`` (mcp 2.x; the
        # ``mcp.shared.version`` module is gone). ``initialize()`` already
        # raises RuntimeError for an unlisted version, so this is the
        # defensive second gate. The PINNED constant remains documentation of
        # the primary-targeted revision but no longer enforces equality.
        # DD6: read the negotiated state from the session's properties, which
        # are era-agnostic (Flight 2 swaps initialize() for negotiation and
        # these reads stay).
        negotiated = session.protocol_version
        if negotiated not in HANDSHAKE_PROTOCOL_VERSIONS + MODERN_PROTOCOL_VERSIONS:
            await self._cleanup_after_failed_connect()
            raise MCPVersionMismatch(pinned=pinned, observed=str(negotiated))

        capabilities = session.server_capabilities
        if capabilities is None or capabilities.tools is None:
            await self._cleanup_after_failed_connect()
            raise MCPCapabilityMissing("tools")

        # All checks pass — commit state. Ordering invariant: any path that
        # raised above must leave _is_alive=False (so test_connect_*_mismatch
        # observes the failed state correctly).
        self._capabilities = capabilities
        self._protocol_version = negotiated
        if self.record_era:
            _era.remember_era(self.source.id, negotiated)
        # F4 L2 (M08): capture spec-optional serverInfo + instructions so the
        # agent-editor Tools tab can surface server-declared identity/usage
        # prose without re-probing. Both default to None when omitted.
        self._server_info = session.server_info
        self._instructions = session.instructions
        # F4 L3 (M08): capture _meta alongside the other spec-optional
        # initialize() fields (``InitializeResult.meta``, aliased ``_meta``).
        # Defaults to None when omitted.
        # DD3: era-agnostic read. The modern era stamps serverInfo under
        # SERVER_INFO_META_KEY; the editor already shows it, so it is dropped
        # and an emptied dict is stored as None.
        res = session.initialize_result or session.discover_result
        meta_val = getattr(res, "meta", None)
        if meta_val is not None and hasattr(meta_val, "model_dump"):
            meta_val = meta_val.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(meta_val, dict):
            meta_val = {k: v for k, v in meta_val.items() if k != SERVER_INFO_META_KEY}
            self._meta = meta_val or None
        else:
            self._meta = None
        self._is_alive = True
        self._touch_activity()

    async def _cleanup_after_failed_connect(self) -> None:
        """Best-effort teardown of partial state from a failed connect().

        Suppresses non-MCPClientError teardown exceptions (anyio cancel
        scope drift, broken pipes, etc.) but lets ``MCPClientError``
        subclasses (notably ``SandboxError`` from F4 leg 02's
        bwrap-stderr translation) propagate. Translation runs in
        ``connect_stdio``'s `finally` and surfaces during the
        ``transport_stack.aclose()`` walk; that diagnostic — "bwrap
        rejected the spawn for these reasons" — strictly dominates the
        downstream "connection closed" wrapping that ``connect()`` would
        otherwise emit.
        """
        cleanup_err: BaseException | None = None
        try:
            if self._transport_stack is not None:
                await self._transport_stack.aclose()
        except MCPClientError as e:
            cleanup_err = e
        except Exception:
            logger.debug("transport cleanup raised; suppressing", exc_info=True)
        self._transport_stack = None
        self._session = None
        if cleanup_err is not None:
            raise cleanup_err

    async def disconnect(self) -> None:
        """Idempotent teardown. Never raises — F4-pool contract.

        F4-pool concurrency note: setting `_is_alive = False` BEFORE awaiting
        any close coroutines ensures the reaper observes the disconnect-in-
        progress state correctly. Python's GIL makes single-attribute reads/
        writes of bool/float atomic, so no explicit lock is needed.
        """
        self._owner_task = None  # DD6: a reconnect never compares against a stale task
        if not self._is_alive and self._transport_stack is None:
            return
        # Flip the flag FIRST so concurrent readers see correct state.
        self._is_alive = False
        try:
            if self._transport_stack is not None:
                await self._transport_stack.aclose()
        except Exception:
            # Cross-task safety net — the real fix for cross-task disconnect
            # is the F4 pool's worker-task pattern, NOT AsyncExitStack
            # (anyio's cancel-scope guard fires on cross-task __aexit__
            # regardless of how the CM is wrapped). See flight 04 design
            # §2-detail. This swallow remains intentionally; pool callers
            # use _pool._entry_worker (F4 L3) which runs disconnect on the
            # same task that ran connect, never tripping this branch.
            logger.warning("MCPClient transport close failed", exc_info=True)
        finally:
            self._transport_stack = None
            self._session = None
            # _tools_cache is per-session — clear so re-connect rebuilds fresh
            # (tools may change between sessions; stale cache could leak).
            self._tools_cache = None
            # F4 L2 (M08): _server_info / _instructions are per-session
            # (servers may rebrand or rewrite usage prose between sessions);
            # clear so a reconnect repopulates from the fresh initialize().
            # Reading the public properties post-disconnect raises via the
            # _is_alive guard, so callers can't observe stale None values.
            self._server_info = None
            self._instructions = None
            self._meta = None
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
            raise MCPConnectionError("MCPClient is not connected; cannot list tools.")
        self._touch_activity()
        # L6b: SDK error translation. UrlElicitationRequiredError IS a subclass
        # of MCPError (verified at L6b design review) — re-raise BEFORE the
        # MCPError clause or it gets silently swallowed into MCPConnectionError,
        # breaking F3+'s ability to surface URL elicitation prompts.
        #
        # F6.5 L2: SDK auth-flow failures surface from inside the SDK's anyio
        # TaskGroup, possibly wrapped as a BaseExceptionGroup; the `except*`
        # below sits inside asyncio.timeout BEFORE the outer translations. The
        # explicit `except MCPAuthRequired: raise` is defensive - without it, a
        # MCPAuthRequired raised by the inner block would be caught by a later
        # clause and silently rewrapped.
        #
        # DD1: mcp 2.x no longer raises HTTPStatusError for a 401 (a POST 401
        # becomes ``MCPError(INTERNAL_ERROR, "Server returned an error
        # response")``), so the no-provider 401 is read from the transport's
        # response-hook record: this operation's baseline is captured here and a
        # failure is auth-required only if the most recent MCP-POST response
        # since then was a 401.
        auth_rec = auth_record_for(self._session)
        baseline = auth_rec.seq if auth_rec is not None else 0
        try:
            async with asyncio.timeout(self.timeout_seconds):
                try:
                    result = await self._session.list_tools()
                except* (OAuthFlowError, OAuthTokenError):
                    # SDK auth-flow failed. Provider attached but couldn't
                    # complete (refresh failed / discovery failed / DCR
                    # failed). Translate to MCPAuthRequired so
                    # get_tools_for_agent can skip cleanly + log the right
                    # discriminator.
                    raise self._oauth_flow_auth_required() from None
        except asyncio.TimeoutError as e:
            classified = self._classify_failure(
                e, op="list_tools", baseline=baseline, record=auth_rec
            )
            if classified is not None:
                raise classified from None
            raise MCPConnectionError(
                f"MCP list_tools exceeded {self.timeout_seconds} seconds"
            ) from None
        except MCPAuthRequired:
            raise
        except MCPError as e:
            classified = self._classify_failure(
                e, op="list_tools", baseline=baseline, record=auth_rec
            )
            if classified is e:
                raise
            if classified is not None:
                raise classified from None
            raise MCPConnectionError(f"MCP list_tools failed: {e}") from None
        except (httpx2.HTTPError, anyio.ClosedResourceError) as e:
            classified = self._classify_failure(
                e, op="list_tools", baseline=baseline, record=auth_rec
            )
            if classified is not None:
                raise classified from None
            self._mark_dead()
            raise MCPConnectionError(
                f"MCP transport error during list_tools: {type(e).__name__}: {e}"
            ) from None
        except (Exception, BaseExceptionGroup, asyncio.CancelledError) as e:
            # DD6: a cancellation on a task other than the transport's owner is a
            # real outer cancellation, never the SDK's internal cancel-scope fallout.
            if isinstance(e, asyncio.CancelledError) and not self._on_owner_task():
                raise
            # Anything else after the request was sent: a 401 as the last
            # response still means sign-in (a 2.3.0 auth-flow failure can reach
            # here as a CancelledError); otherwise propagate unchanged.
            classified = self._classify_failure(
                e, op="list_tools", baseline=baseline, record=auth_rec
            )
            if classified is not None:
                raise classified from None
            raise

        tools: list[MCPTool] = []
        for tool in result.tools:
            # tool.annotations is a Pydantic ToolAnnotations object (or None);
            # .model_dump(mode="json") yields a stable JSON-serializable dict.
            annotations = (
                tool.annotations.model_dump(mode="json", by_alias=True)
                if tool.annotations is not None
                else None
            )
            tools.append(
                MCPTool(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.input_schema or {},
                    output_schema=tool.output_schema,
                    annotations=annotations,
                )
            )

        self._tools_cache = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        """Call a tool on the server and return the result.

        Lazy-populates self._tools_cache if needed (so unknown-tool detection
        works on first call). Raises MCPToolNotFoundError BEFORE wire call if
        the tool name isn't in the cache. Validates `arguments` against the
        tool's JSON Schema (L6b) BEFORE wire call, raising MCPArgumentError on
        mismatch. Raises MCPCallError if the server returns isError=True or an
        SDK MCPError. Wraps timeout / transport errors as MCPConnectionError.
        UrlElicitationRequiredError propagates unchanged (F3+ surfaces it).

        Raises:
            MCPConnectionError: not connected, timeout, transport error, or a
                server-terminated session (``_is_alive`` is flipped off first so
                the pool rebuilds the entry).
            MCPToolNotFoundError: if name isn't in the server's tool list.
            MCPArgumentError: if arguments fail JSON-Schema validation.
            MCPCallError: if the server returned isError=True or MCPError.
            UrlElicitationRequiredError: propagated unchanged for F3+ flows.
        """
        if not self._is_alive or self._session is None:
            raise MCPConnectionError("MCPClient is not connected; cannot call tool.")
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
            # Squawk 0052: some models send integers as numeric strings; coerce
            # (copy, schema-guided) so the validated args are what goes on the wire.
            arguments = coerce_arguments(arguments, tool_meta.input_schema)
            try:
                jsonschema_validate(arguments, tool_meta.input_schema)
            except ValidationError as e:
                raise MCPArgumentError(tool_name=name, validation_message=str(e)) from None

        # L6b: SDK error translation. UrlElicitationRequiredError IS a subclass
        # of MCPError (`issubclass(UrlElicitationRequiredError, MCPError)`) — the
        # explicit re-raise MUST come BEFORE `except MCPError` or URL
        # elicitation prompts get silently swallowed into MCPCallError.
        #
        # F5 L4 (A8/A9): SDK auth-flow failures surface from inside the SDK's
        # anyio TaskGroup (possibly as a BaseExceptionGroup). DD1: the
        # no-provider 401 is read from the transport's response-hook record
        # (mcp 2.x no longer raises HTTPStatusError), against a baseline
        # captured immediately before the request is sent.
        auth_rec = auth_record_for(self._session)
        baseline = auth_rec.seq if auth_rec is not None else 0
        try:
            async with asyncio.timeout(self.call_timeout_seconds):
                try:
                    result = await self._session.call_tool(
                        name, arguments, allow_input_required=True
                    )
                except* (OAuthFlowError, OAuthTokenError):
                    # F5 L4 (A8): SDK auth-flow failed. Provider attached but
                    # couldn't complete (refresh failed / discovery failed /
                    # DCR failed). Tell the agent loop to pause and surface
                    # auth_required to chat UI.
                    raise self._oauth_flow_auth_required() from None
        except asyncio.TimeoutError as e:
            classified = self._classify_failure(
                e, op="call_tool", baseline=baseline, record=auth_rec, tool_name=name
            )
            if classified is not None:
                raise classified from None
            raise MCPConnectionError(
                f"MCP tool call exceeded {self.call_timeout_seconds} seconds"
            ) from None
        except MCPAuthRequired:
            raise
        except MCPError as e:
            classified = self._classify_failure(
                e, op="call_tool", baseline=baseline, record=auth_rec, tool_name=name
            )
            if classified is e:
                raise
            if classified is not None:
                raise classified from None
            raise MCPCallError(tool_name=name, server_message=str(e)) from None
        except (httpx2.HTTPError, anyio.ClosedResourceError) as e:
            classified = self._classify_failure(
                e, op="call_tool", baseline=baseline, record=auth_rec, tool_name=name
            )
            if classified is not None:
                raise classified from None
            self._mark_dead()
            raise MCPConnectionError(
                f"MCP transport error during call_tool: {type(e).__name__}: {e}"
            ) from None
        except (Exception, BaseExceptionGroup, asyncio.CancelledError) as e:
            # See list_tools (DD6): another task's cancellation re-raises; a
            # trailing 401 still means sign-in; otherwise propagate unchanged.
            if isinstance(e, asyncio.CancelledError) and not self._on_owner_task():
                raise
            classified = self._classify_failure(
                e, op="call_tool", baseline=baseline, record=auth_rec, tool_name=name
            )
            if classified is not None:
                raise classified from None
            raise

        # DD8: a tool asking for input returns InputRequiredResult, which has no
        # ``content``; check before flattening.
        if isinstance(result, InputRequiredResult):
            raise MCPCallError(tool_name=name, server_message=_INPUT_REQUIRED_MESSAGE)

        # Flatten text content blocks; render placeholders for non-text blocks
        # so MCPToolResult.text reflects ALL blocks (text + placeholders) in
        # order. Unknown block types are silently dropped (forward-compat with
        # future SDK content-block types).
        joined_text_parts: list[str] = []
        raw_blocks: list[dict[str, Any]] = []
        for block in result.content:
            raw_blocks.append(block.model_dump(mode="json", by_alias=True))
            block_type = getattr(block, "type", None)
            if block_type == "text":
                joined_text_parts.append(block.text)
            elif block_type == "image":
                joined_text_parts.append(
                    f"[image: {len(block.data)} bytes, mime={block.mime_type}]"
                )
            elif block_type == "audio":
                joined_text_parts.append(
                    f"[audio: {len(block.data)} bytes, mime={block.mime_type}]"
                )
            elif block_type == "resource_link":
                joined_text_parts.append(f"[resource_link: {block.uri}]")
            elif block_type == "resource":
                # EmbeddedResource has .resource which has .uri
                # (TextResourceContents | BlobResourceContents).
                joined_text_parts.append(f"[resource: {block.resource.uri}]")
            # Unknown block types: silently dropped (forward-compat).
        joined_text = "".join(joined_text_parts)

        # mcp 2.x typing: structured_content is dict[str, Any] | None;
        # is_error is bool with default False. Pass-through is sufficient.
        structured = result.structured_content
        is_error = bool(result.is_error)

        tool_result = MCPToolResult(
            text=joined_text,
            raw=raw_blocks,
            structured=structured,
            is_error=is_error,
        )

        if is_error:
            raise MCPCallError(tool_name=name, server_message=joined_text)

        return tool_result

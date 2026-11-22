"""MCP (Model Context Protocol) client foundation.

F2 lands the runtime-foundation: thin async wrapper around mcp 2.x SDK
exposing connect / list-tools / call-tool / disconnect lifecycle for both
transports (stdio + streamable-http). No agent integration (F6), no warm-pool
(F4), no sandbox (F3), no OAuth flow (F5).

See the_one/agents.md "MCP F2 Client Foundation" for invariants.
See _HANDSHAKE_OFFER_VERSION docstring for SDK upgrade procedure.
"""

_HANDSHAKE_OFFER_VERSION = "2025-11-25"
"""The handshake-era revision the-one offers where it speaks ``initialize`` itself.

Renamed from ``_PINNED_PROTOCOL_VERSION`` (Mission 29 Flight 2, DD4). Matches
``mcp.types.version.LATEST_HANDSHAKE_VERSION`` (mcp 2.x). ``MCPClient.connect``
now negotiates (``the_one/mcp/_negotiate.py``): it tries ``server/discover`` at
the SDK's ``LATEST_MODERN_VERSION`` first and falls back to the handshake. This
constant feeds only the hand-built ``initialize`` payloads (the auth-posture
probe, the OAuth flow drivers) and the ``MCPVersionMismatch(pinned=...)`` text.

Upgrade procedure:
    1. Bump the mcp SDK pin in pyproject.toml.
    2. Run:
           python -c "from mcp.types.version import LATEST_HANDSHAKE_VERSION; \\
                      print(LATEST_HANDSHAKE_VERSION)"
    3. Update this constant to match.
    4. Run integration tests against fresh fixture build:
           pytest tests/test_mcp_integration.py
    5. Confirm version-mismatch test still passes (it asserts
       our constant equals the SDK's at runtime).

Read at call time (`the_one.mcp._HANDSHAKE_OFFER_VERSION`), NOT
imported by name (`from the_one.mcp import _HANDSHAKE_OFFER_VERSION`) — the
latter binds at module-load and breaks `monkeypatch.setattr` in tests.
"""

MCP_DEFAULT_TIMEOUT_SECONDS = 30
"""Default timeout for handshake (initialize) and list_tools — should be fast."""

HANDSHAKE_RESERVE_SECONDS = 10
"""Time a local-command connect keeps back for the older handshake (sortie 19, DD2):
the patient ``server/discover`` window is the connect limit less this. A limit at or
below it gives no patience. Read at connect time through the module (patchable)."""

PROBE_NO_ANSWER_FLOOR_SECONDS = 1.0
"""A ``REQUEST_TIMEOUT`` from a discover probe counts as "no answer" only after the
probe was outstanding this long (sortie 19, DD1); sooner, the server answered the
code itself. Read at call time inside ``_negotiate`` (patchable)."""

MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60
"""Default timeout for call_tool — legitimate tools may run longer (e.g. static analyzer)."""

from the_one.mcp._pool import (  # noqa: E402  (constants first per F2 contract)
    acquire,
    shutdown_drain,
)
from the_one.mcp._tool import MCPClientTool  # noqa: E402  (constants first per F2)
from the_one.mcp._tool_provider import MCPToolProvider  # noqa: E402  (constants first per F2)
from the_one.mcp.client import MCPClient  # noqa: E402  (constants first per F2 contract)
from the_one.mcp.errors import (  # noqa: E402  (constants first per F2 contract)
    MCPArgumentError,
    MCPAuthRequired,
    MCPCallError,
    MCPCapabilityMissing,
    MCPClientError,
    MCPConnectionError,
    MCPRegistrationError,
    MCPToolNotFoundError,
    MCPVersionMismatch,
)
from the_one.mcp.types import (  # noqa: E402  (constants first per F2 contract)
    MCPTool,
    MCPToolResult,
)

__all__ = [
    "_HANDSHAKE_OFFER_VERSION",
    "MCP_DEFAULT_TIMEOUT_SECONDS",
    "MCP_DEFAULT_CALL_TIMEOUT_SECONDS",
    "MCPClient",
    "MCPTool",
    "MCPToolResult",
    "MCPClientError",
    "MCPVersionMismatch",
    "MCPCapabilityMissing",
    "MCPConnectionError",
    "MCPRegistrationError",
    "MCPToolNotFoundError",
    "MCPArgumentError",
    "MCPAuthRequired",
    "MCPCallError",
    "MCPClientTool",
    "MCPToolProvider",
    "acquire",
    "shutdown_drain",
]

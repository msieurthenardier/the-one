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
    2. Run:
           python -c "from mcp.types import LATEST_PROTOCOL_VERSION; \\
                      print(LATEST_PROTOCOL_VERSION)"
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

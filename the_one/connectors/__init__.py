"""Connector subsystem — bi-directional third-party communication platforms.

This package is a peer to :mod:`the_one.mcp` and :mod:`the_one.tools`. Flight 1
of mission 10 ships the contract and lifecycle plumbing here; flights 2-10
add the operator surfaces, the platform-send built-in tool, the routing and
command primitives, and the first two real connectors (Discord + one other).

**Canonical-import discipline** (``agents.md`` :: ``canonical-import +
convenience-re-export``): code that touches Protocol identity
(``isinstance(...)`` checks) or exception class identity (``try/except`` and
subclass checks) MUST use the canonical import paths:

- ``from the_one.connectors.base import ConnectorPlugin``,
  ``from the_one.connectors.base import ConnectorClient``
- ``from the_one.connectors.errors import ConnectorClientError`` (and
  subclasses)

The re-exports below are convenience only — they are NOT to be used in
``isinstance`` or exception-handler positions. A future package-internal
refactor could change what ``the_one.connectors.X`` resolves to without
violating any contract, but the canonical paths above are stable.
"""

from the_one.connectors.base import (
    ConnectorClient,
    ConnectorPlugin,
    Deny,
    DoctorReport,
    InboundEnvelope,
    NeedsPairing,
    OutboundTarget,
    Permit,
    ResolveOutcome,
    SendResult,
    SessionKey,
)
from the_one.connectors.errors import (
    ConnectorAuthRequired,
    ConnectorClientError,
    ConnectorConfigError,
    ConnectorConnectionError,
    ConnectorRateLimitError,
    ConnectorRegistrationError,
)
from the_one.connectors.registry import ConnectorRegistry

# M10 F03 L02: visibility tag for connector-attached chat sessions.
# See ``the_one.llm.base.Message.visibility`` for semantics. The string
# literal lives here so F3 L4's dispatcher, F4's platform-send tool, and
# F5's operator-input path all reference one constant — a typo like
# ``"opperator"`` at a production set-site is caught at import / IDE
# time rather than persisting silently. Plain assignment (not
# ``Final[str]``) matches the project's existing module-level-constant
# style (e.g. ``MAX_TOOL_RESULT_INLINE_CONTENT`` in ``the_one.db.codec``);
# the codebase has zero existing ``typing.Final`` usages.
OPERATOR_VISIBILITY = "operator"

# M10 F04 L01: success-prefix sentinel for ``SendToPlatformChannelTool.execute()``
# (F4 leg 2). The dispatcher's visibility-tagger (F4 leg 4) matches on this
# prefix to decide ``visibility=None`` on the resulting tool_result message —
# successful platform-send tool calls produce tool_result content that the
# operator does NOT need to see in the chat-history view because the user's
# already-displayed message is the same content. Constant lives here as the
# single source of truth so the producer (leg 2) and consumer (leg 4) cannot
# drift on the literal.
PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"

__all__ = [
    # Protocols + supporting types
    "ConnectorClient",
    "ConnectorPlugin",
    "Deny",
    "DoctorReport",
    "InboundEnvelope",
    "NeedsPairing",
    "OutboundTarget",
    "Permit",
    "ResolveOutcome",
    "SendResult",
    "SessionKey",
    # Exception hierarchy
    "ConnectorAuthRequired",
    "ConnectorClientError",
    "ConnectorConfigError",
    "ConnectorConnectionError",
    "ConnectorRateLimitError",
    "ConnectorRegistrationError",
    # Registry (class — module-level functions stay at the_one.connectors.registry)
    "ConnectorRegistry",
    # Constants
    "OPERATOR_VISIBILITY",
    "PLATFORM_SEND_OK_PREFIX",
]

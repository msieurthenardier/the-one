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
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
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

__all__ = [
    # Protocols + supporting types
    "ConnectorClient",
    "ConnectorPlugin",
    "DoctorReport",
    "InboundEnvelope",
    "OutboundTarget",
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
]

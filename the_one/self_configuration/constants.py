"""Leaf constants for the self-configuration surface.

LD2 (leg 02): kept deliberately import-light — ``the_one/interfaces/web/
middleware.py`` imports :data:`CONFINED_SOURCE_PATHS` from here directly so
the credential gate does not gain a heavy import for a security-sensitive
per-request path check. Nothing in this module imports anything from
``the_one`` — constants only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only — keeps this leaf module free of a runtime import from
    # ``the_one.db`` (see the module docstring). ``is_surface_row`` below
    # duck-types on the ``.config`` attribute instead.
    from the_one.db.models import MCPSource

# Where the self-configuration MCPServer sub-app is mounted on the existing
# app/port (DD1). No new port — see the flight's re-entrancy probe. LD4:
# a real MCPServer instance is mounted here, stateless, with a trailing-slash
# ``streamable_http_path="/"`` (probe constraint 5 — avoids Starlette's 307
# on a bare-path POST).
MOUNT_PATH = "/mcp/self-configuration"

# The credential-source *name* registered by
# ``the_one.self_configuration.credentials.SelfConfigurationCredentialSource``
# — matches ``IdentifiedCaller.source`` for a resolved ``agt`` credential.
SOURCE_NAME = "self-configuration"

# LD2 / Decision D5 (flight log): maps a confined credential-source *name* to
# the HTTP path prefix it may reach. ``CredentialGateMiddleware`` looks the
# caller's ``source`` up here after resolution; when present, every request
# whose path does not start with the mapped prefix is refused with 403, and
# every WebSocket upgrade from that source is refused outright. Sources
# absent from this map (``"file"``, and the cookie channel's ``"session"``)
# are admitted exactly as before this leg — the map is opt-in per source,
# never a blanket "anything not `file`" rule (that wording would 403 the
# session cookie; see flight log Decision D5).
# The credential-source *name* registered by
# ``the_one.self_configuration.external_credentials.ExternalAgentCredentialSource``
# — matches ``IdentifiedCaller.source`` for a resolved ``ext`` credential
# (M21 F03 L01, DD1). A DISTINCT principal from the agent's own ``agt``
# credential: one external grant per row, independently revocable, scoped
# to exactly one agent's surface.
EXTERNAL_SOURCE_NAME = "self-configuration-external"

# LD2 / Decision D5 (flight log): maps a confined credential-source *name* to
# the HTTP path prefix it may reach. ``CredentialGateMiddleware`` looks the
# caller's ``source`` up here after resolution; when present, every request
# whose path does not start with the mapped prefix is refused with 403, and
# every WebSocket upgrade from that source is refused outright. Sources
# absent from this map (``"file"``, and the cookie channel's ``"session"``)
# are admitted exactly as before this leg — the map is opt-in per source,
# never a blanket "anything not `file`" rule (that wording would 403 the
# session cookie; see flight log Decision D5).
#
# M21 F03 L01 (DD1): the external source points at the SAME mount path, so
# it inherits Flight 1's confinement (403 off-mount, WS refused) unchanged —
# no new enforcement code, only a second entry here.
CONFINED_SOURCE_PATHS: dict[str, str] = {
    SOURCE_NAME: MOUNT_PATH,
    EXTERNAL_SOURCE_NAME: MOUNT_PATH,
}

# The credential prefix minted for per-agent self-configuration credentials
# (LD2). Distinct from ``the_one.api_credential.CREDENTIAL_PREFIX`` ("loc")
# so a presented token's type is legible at a glance and
# ``FileCredentialSource.parse`` (which always parses with the default
# prefix) rejects an ``agt_`` token on prefix mismatch, falling through to
# the registered ``SelfConfigurationCredentialSource``.
AGENT_CREDENTIAL_PREFIX = "agt"

# The credential prefix minted for EXTERNAL-client self-configuration
# credentials (M21 F03 L01, DD1). Distinct from both ``CREDENTIAL_PREFIX``
# ("loc") and ``AGENT_CREDENTIAL_PREFIX`` ("agt") so a presented token's
# type is legible at a glance and the other registered sources reject an
# ``ext_`` token on prefix mismatch, falling through to
# ``ExternalAgentCredentialSource``.
EXTERNAL_CREDENTIAL_PREFIX = "ext"

# The header key the minted credential lives under inside a surface row's
# encrypted ``secrets`` (DD2) — the same flat kv-table the streamable-http
# transport merges into request headers
# (``mcp/transports/streamable_http.py:build_request_headers``).
CREDENTIAL_SECRET_KEY = "Authorization"

# LD1: the key inside a surface row's ``config`` dict that carries the
# ownership marker (``{"self_configuration": {"agent": "<name>"}}``)
# identifying the row as a self-configuration surface row. Squawk 0004:
# hoisted here (with :func:`is_surface_row` below) so ``manage.py`` and
# ``credentials.py`` share one predicate instead of each carrying their own
# copy of the marker check for import-order reasons.
OWNER_MARKER_KEY = "self_configuration"


def is_surface_row(source: "MCPSource") -> bool:
    """LD1: a row is a surface row iff its ``config`` carries the ownership
    marker ``{"self_configuration": {"agent": "<name>"}}``.

    Takes anything duck-typed like
    :class:`~the_one.db.models.MCPSource` (an object with a ``.config``
    mapping attribute) — the type import above is ``TYPE_CHECKING``-only so
    this leaf module keeps importing nothing from ``the_one.db`` at runtime.
    """
    marker = (source.config or {}).get(OWNER_MARKER_KEY)
    return isinstance(marker, dict) and bool(marker.get("agent"))

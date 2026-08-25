"""Leaf constants for the self-configuration surface.

LD2 (leg 02): kept deliberately import-light — ``the_one/interfaces/web/
middleware.py`` imports :data:`CONFINED_SOURCE_PATHS` from here directly so
the credential gate does not gain a heavy import for a security-sensitive
per-request path check. Nothing in this module imports anything from
``the_one`` — constants only.
"""

from __future__ import annotations

# Where the self-configuration FastMCP sub-app is mounted on the existing
# app/port (DD1). No new port — see the flight's re-entrancy probe. LD4:
# a real FastMCP instance is mounted here, stateless, with a trailing-slash
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
CONFINED_SOURCE_PATHS: dict[str, str] = {
    SOURCE_NAME: MOUNT_PATH,
}

# The credential prefix minted for per-agent self-configuration credentials
# (LD2). Distinct from ``the_one.api_credential.CREDENTIAL_PREFIX`` ("loc")
# so a presented token's type is legible at a glance and
# ``FileCredentialSource.parse`` (which always parses with the default
# prefix) rejects an ``agt_`` token on prefix mismatch, falling through to
# the registered ``SelfConfigurationCredentialSource``.
AGENT_CREDENTIAL_PREFIX = "agt"

# The header key the minted credential lives under inside a surface row's
# encrypted ``secrets`` (DD2) — the same flat kv-table the streamable-http
# transport merges into request headers
# (``mcp/transports/streamable_http.py:build_request_headers``).
CREDENTIAL_SECRET_KEY = "Authorization"

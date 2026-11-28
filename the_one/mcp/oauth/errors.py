"""OAuth-side error hierarchy.

Mirrors the_one/mcp/errors.py's pattern: single base class with narrow
subclasses; each subclass formats a clean single-sentence __str__ for
small-model consumption (mission constraint #75); no nested causes,
no rich tracebacks visible in tool-result strings.

MCPAuthRequired is canonical at the_one.mcp.errors as of F6 L0; re-exported
here for back-compat with F5 callers.
"""

from mcp.client.auth.exceptions import OAuthFlowError

from the_one.mcp.errors import MCPAuthRequired, MCPClientError  # noqa: F401

__all__ = [
    "MCPAuthRequired",
    "SignInNotAvailable",
    "MCPOAuthError",
    "MCPOAuthDiscoveryError",
    "MCPOAuthRegistrationError",
    "MCPOAuthRefreshFailed",
]


class MCPOAuthError(MCPClientError):
    """Base for all OAuth-side errors. NOT instantiated directly.

    Subclasses cover three failure modes:
      - MCPOAuthDiscoveryError: RFC 9728 PRM or RFC 8414 AS metadata fetch/parse failed
      - MCPOAuthRegistrationError: RFC 7591 DCR call failed
      - MCPOAuthRefreshFailed: token refresh failed; triggers re-auth
    """


class MCPOAuthDiscoveryError(MCPOAuthError):
    """OAuth discovery failed.

    Raised when the AS metadata document at /.well-known/oauth-authorization-server
    (RFC 8414) or /.well-known/openid-configuration (OIDC) returns 404 or malformed
    JSON, OR when the RFC 9728 PRM document is missing required fields. Operator
    sees: 'OAuth discovery failed: <reason>. The MCP server may not be spec-compliant.'
    """


class MCPOAuthRegistrationError(MCPOAuthError):
    """RFC 7591 Dynamic Client Registration failed.

    Raised when the DCR endpoint returns an error response, network failure
    interrupts the call, or the response is malformed. Operator sees:
    'OAuth client registration failed: <reason>. Try the manual-entry path
    to register a client at the IDP yourself.'
    """


class MCPOAuthRefreshFailed(MCPOAuthError):  # noqa: N818  (mandated by F5 §11 contract; subclass of MCPOAuthError)
    """OAuth refresh-token exchange failed.

    Raised when the AS rejects the refresh-token grant (401, invalid_grant,
    expired refresh token). Triggers re-auth in the agent loop: the next tool
    call surfaces a fresh auth_required event so the operator can re-consent.
    Operator sees: 'OAuth token refresh failed: <reason>. Please re-authenticate.'
    """


class SignInNotAvailable(OAuthFlowError):  # noqa: N818  (names the condition; subclass of the SDK's OAuthFlowError)
    """The interactive sign-in step was refused because no one can answer it here.

    Raised by ``redirect_handler`` (before any state is registered or broadcast)
    for a connection built with ``interactive=False`` (every pool connection and
    Test connection's saved-tokens phase) and for an ``agent_build:`` csid. It
    subclasses the SDK's ``OAuthFlowError`` so ``MCPClient``'s
    ``except* (OAuthFlowError, OAuthTokenError)`` arms turn it into
    ``MCPAuthRequired``. A logging filter (``the_one.mcp.oauth._log_filter``)
    drops the SDK's own "OAuth flow error" record for exactly this class.
    """

"""OAuth-side error hierarchy.

Mirrors the_one/mcp/errors.py's pattern: single base class with narrow
subclasses; each subclass formats a clean single-sentence __str__ for
small-model consumption (mission constraint #75); no nested causes,
no rich tracebacks visible in tool-result strings.
"""

from the_one.mcp.errors import MCPClientError


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


class MCPAuthRequired(MCPClientError):  # noqa: N818  (control-flow signal, not "Error" semantically; subclass of MCPClientError)
    """Raised when an MCP tool call requires user re-authentication.

    Control-flow signal (NOT an OAuth-flow failure — see MCPOAuthError
    for those). The agent loop catches it via Agent._execute_tool and
    returns a ToolResult with metadata.is_auth_required=True so the
    L3 pause/resume primitive fires. Chat UI surfaces a Login-required
    button; user consents at the IDP; tokens persist; agent loop
    resumes.

    Carries source_id (always), resource_metadata_url (when parsed
    from a 401 WWW-Authenticate header), consent_url (when the SDK
    exposes it; usually None on the lazy path).

    Inherits from MCPClientError (NOT MCPOAuthError) — it is a
    control-flow signal, not a "the OAuth flow itself failed" error.
    """

    def __init__(
        self,
        source_id: str,
        *,
        resource_metadata_url: str | None = None,
        consent_url: str | None = None,
    ) -> None:
        super().__init__(f"Authorization required for MCP source {source_id}")
        self.source_id = source_id
        self.resource_metadata_url = resource_metadata_url
        self.consent_url = consent_url

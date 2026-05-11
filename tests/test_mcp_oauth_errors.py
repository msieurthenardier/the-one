"""Smoke tests for the_one/mcp/oauth/errors.py.

Validates the 5-class hierarchy + verbatim-message-equality contract per
F4 debrief named convention (project-wide pattern in agents.md).
"""

from the_one.mcp.errors import MCPClientError
from the_one.mcp.oauth.errors import (
    MCPAuthRequired,
    MCPOAuthDiscoveryError,
    MCPOAuthError,
    MCPOAuthRefreshFailed,
    MCPOAuthRegistrationError,
)


def test_oauth_error_hierarchy_and_verbatim_messages() -> None:
    """4-class hierarchy + verbatim-message-equality smoke test."""
    # Hierarchy: each subclass → MCPOAuthError → MCPClientError
    assert issubclass(MCPOAuthError, MCPClientError)
    assert issubclass(MCPOAuthDiscoveryError, MCPOAuthError)
    assert issubclass(MCPOAuthRegistrationError, MCPOAuthError)
    assert issubclass(MCPOAuthRefreshFailed, MCPOAuthError)

    # Verbatim-message-equality (per agents.md Project Conventions):
    # str(exc) returns the constructor argument exactly, no class-name
    # prefix or rich rendering.
    assert str(MCPOAuthDiscoveryError("test")) == "test"
    msg = "client registration failed"
    assert str(MCPOAuthRegistrationError(msg)) == msg
    assert str(MCPOAuthRefreshFailed("token expired")) == "token expired"


def test_mcp_auth_required_carries_fields_and_message() -> None:
    """F5 L4 A1: MCPAuthRequired carries source_id, resource_metadata_url,
    consent_url; __str__ is verbatim per Project Convention
    `verbatim-message-equality`.

    MCPAuthRequired inherits from MCPClientError (NOT MCPOAuthError) — it
    is a control-flow signal, not a "the OAuth flow itself failed" error.
    """
    e = MCPAuthRequired(
        source_id="s1",
        resource_metadata_url="https://x",
        consent_url="https://idp/auth",
    )
    assert e.source_id == "s1"
    assert e.resource_metadata_url == "https://x"
    assert e.consent_url == "https://idp/auth"
    assert str(e) == "Authorization required for MCP source s1"

    # Hierarchy: MCPAuthRequired → MCPClientError (NOT MCPOAuthError)
    assert issubclass(MCPAuthRequired, MCPClientError)
    assert not issubclass(MCPAuthRequired, MCPOAuthError)

    # Defaults: URLs default to None (lazy-path with no provider attached).
    e2 = MCPAuthRequired(source_id="s2")
    assert e2.source_id == "s2"
    assert e2.resource_metadata_url is None
    assert e2.consent_url is None
    assert str(e2) == "Authorization required for MCP source s2"

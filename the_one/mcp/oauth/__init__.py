"""OAuth 2.1 + PKCE for remote MCP servers (F5).

Lazy/discovery-driven: operator configures MCP source by URL only;
on first 401 the chat surface renders a Login-required button; modal
opens IDP consent in a new browser tab; loopback redirect resolves
at /api/oauth/callback; tokens persist encrypted; agent loop resumes
the original tool call.

Consumes mcp.client.auth.OAuthClientProvider from the SDK for PKCE,
discovery, DCR, audience binding, and refresh. This package provides
the the-one-side adapter layer:

  - errors: MCPOAuthError hierarchy (this leg, L0)
  - storage: TokenStorage Protocol impl backed by MCPSourceRepository (L2)
  - handlers: redirect_handler + callback_handler (L2)
  - _state: pending-flow registry (L2; ``start_periodic_sweep`` /
    ``stop_periodic_sweep`` exposed publicly so app.py's lifespan can
    drive the periodic-sweep task without importing the ``_state``
    module directly — that import would shadow app.py's existing
    ``_state: dict[str, Any]`` global at app.py:103)
  - manual_metadata: ManualOAuthClientProvider for non-DCR providers (L2)

See the_one/mcp/README.md (post-L5) for runtime invariants.
"""

from the_one.mcp.oauth._state import start_periodic_sweep, stop_periodic_sweep
from the_one.mcp.oauth.errors import MCPAuthRequired
from the_one.mcp.oauth.handlers import make_oauth_handlers
from the_one.mcp.oauth.manual_metadata import ManualOAuthClientProvider, ManualOAuthMetadata
from the_one.mcp.oauth.provider_factory import build_oauth_provider_for_source
from the_one.mcp.oauth.storage import MCPSourceTokenStorage

__all__: list[str] = [
    "MCPAuthRequired",
    "MCPSourceTokenStorage",
    "ManualOAuthClientProvider",
    "ManualOAuthMetadata",
    "build_oauth_provider_for_source",
    "make_oauth_handlers",
    "start_periodic_sweep",
    "stop_periodic_sweep",
]

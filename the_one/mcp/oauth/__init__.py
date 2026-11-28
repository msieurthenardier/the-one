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
  - provider: ``TheOneOAuthClientProvider``, the SDK provider that seeds the
    stored token's expiry on load (squawk 0444)
  - handlers: redirect_handler + callback_handler (L2)
  - _state: pending-flow registry (L2; ``start_periodic_sweep`` /
    ``stop_periodic_sweep`` exposed publicly so app.py's lifespan can
    drive the periodic-sweep task without importing the ``_state``
    module directly — that import would shadow app.py's existing
    ``_state: dict[str, Any]`` global at app.py:103)

See the_one/mcp/README.md (post-L5) for runtime invariants.
"""

from the_one.mcp.oauth._log_filter import install_sign_in_refusal_filter
from the_one.mcp.oauth._state import start_periodic_sweep, stop_periodic_sweep
from the_one.mcp.oauth.errors import MCPAuthRequired, SignInNotAvailable
from the_one.mcp.oauth.handlers import make_oauth_handlers
from the_one.mcp.oauth.provider_factory import build_oauth_provider_for_source
from the_one.mcp.oauth.storage import MCPSourceTokenStorage

# Sortie 22: the SDK logs an ERROR for our expected sign-in refusal; drop it.
install_sign_in_refusal_filter()

__all__: list[str] = [
    "MCPAuthRequired",
    "MCPSourceTokenStorage",
    "SignInNotAvailable",
    "build_oauth_provider_for_source",
    "make_oauth_handlers",
    "start_periodic_sweep",
    "stop_periodic_sweep",
]

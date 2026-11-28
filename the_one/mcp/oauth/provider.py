"""The project's ``OAuthClientProvider``: stored tokens carry their expiry (squawk 0444).

mcp 2.3.0's ``OAuthClientProvider._initialize`` loads the stored tokens but never
calls ``context.update_token_expiry``, so ``token_expiry_time`` stays ``None`` and
``is_token_valid()`` reads an expired stored token as valid. The SDK's only proactive
refresh (``not is_token_valid() and can_refresh_token()``) then never runs: the
expired token is sent, the server answers 401, and the 401 branch goes straight to
interactive authorization without trying the stored refresh token.

Every connection builds a fresh provider, so every connection starts in that state.
``MCPSourceTokenStorage.get_tokens`` returns a relative ``expires_in`` computed at read
time (clamped at 0), so seeding the expiry right after the load is enough. A token
with ``expires_in=None`` (no expiry stored) keeps the old behaviour: treated as valid.

This is the one place the code base constructs the SDK provider; import
``TheOneOAuthClientProvider`` from here (``provider_factory`` re-exports nothing else).
"""

from __future__ import annotations

import time

from mcp.client.auth import OAuthClientProvider


class TheOneOAuthClientProvider(OAuthClientProvider):
    """``OAuthClientProvider`` that seeds the token expiry when it loads stored tokens."""

    async def _initialize(self) -> None:
        await super()._initialize()
        tokens = self.context.current_tokens
        if tokens is None:
            return
        if tokens.expires_in is not None and tokens.expires_in <= 0:
            # Already expired. ``update_token_expiry`` would give ``time.time() + 0``, and
            # ``is_token_valid`` is ``time.time() <= expiry``, so a coarse clock (Windows)
            # could still read it as valid. Pin the expiry strictly in the past. Not 0:
            # a falsy expiry reads as valid.
            self.context.token_expiry_time = time.time() - 1.0
            return
        self.context.update_token_expiry(tokens)

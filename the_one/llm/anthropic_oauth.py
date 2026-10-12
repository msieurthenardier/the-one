"""Anthropic consumer-OAuth PKCE flow for the ``anthropic-plan`` provider type.

M19 F01 DD-1: hand-rolled PKCE (S256) against Anthropic's fixed public
consumer-OAuth client with code-paste consent — the operator signs in at
the authorize URL in a browser, Anthropic's own callback page displays a
code, and the operator pastes it back into the provider editor. No MCP
SDK OAuth machinery (that stack is coupled to RFC 8414 discovery +
dynamic client registration, which consumer OAuth doesn't do).

Endpoints, client id, scopes, and the ``code#state`` paste form were
spike-verified at leg start (see the flight log for M19 F01 L01).

Pure functions + a small dataclass — no DB access, no app imports. The
HTTP client is injectable for tests; when omitted, each call constructs
a short-lived ``httpx.AsyncClient``.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"

# Anthropic's well-known public consumer-OAuth client (the one Claude Code
# and other third-party apps use). Public client — PKCE carries the proof,
# there is no client secret.
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Anthropic-hosted code-display callback page (DD-1 code-paste consent).
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"

SCOPE = "org:create_api_key user:profile user:inference"

# A ``claude setup-token`` token lasts about a year (sortie 03 DD3). Lives here
# (no ``anthropic`` import) so the API layer can read it without the SDK;
# ``anthropic_plan_provider`` re-exports it beside ``OAUTH_BETA_HEADER``.
PLAN_TOKEN_LIFETIME_DAYS = 365

# The five OAuth-managed keys stored in ``llm_providers.secrets`` (DD-2).
OAUTH_MANAGED_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "access_token",
        "refresh_token",
        "token_expires_at",
        "scope",
        "token_type",
    }
)

_HTTP_TIMEOUT = httpx.Timeout(30.0)


class OAuthError(Exception):
    """Base class for anthropic-plan OAuth failures."""


class OAuthExchangeError(OAuthError):
    """The token endpoint rejected an exchange or refresh request.

    Carries the HTTP status and response body excerpt so API handlers can
    surface an actionable message (invalid/expired code, revoked refresh
    token) instead of a bare 500.
    """

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class TokenSet:
    """A token response mapped to the DD-2 managed-keys shape.

    ``token_expires_at`` is an absolute unix epoch (seconds), derived from
    the response's relative ``expires_in`` at receipt time.
    """

    access_token: str
    refresh_token: str | None
    token_expires_at: int | None
    scope: str | None
    token_type: str | None

    def to_secrets(self) -> dict[str, Any]:
        """Render as the managed-keys dict persisted into provider secrets.

        Keys with ``None`` values are omitted so a refresh response that
        (say) elides ``scope`` doesn't overwrite a stored value with null.
        """
        out: dict[str, Any] = {"access_token": self.access_token}
        if self.refresh_token is not None:
            out["refresh_token"] = self.refresh_token
        if self.token_expires_at is not None:
            out["token_expires_at"] = self.token_expires_at
        if self.scope is not None:
            out["scope"] = self.scope
        if self.token_type is not None:
            out["token_type"] = self.token_type
        return out


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_verifier() -> str:
    """Generate a PKCE code verifier (43-char base64url of 32 random bytes)."""
    return _b64url(secrets.token_bytes(32))


def derive_challenge(verifier: str) -> str:
    """Derive the S256 code challenge from a verifier."""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def generate_state() -> str:
    """Generate an opaque CSRF ``state`` value."""
    return _b64url(secrets.token_bytes(32))


def build_authorize_url(*, code_challenge: str, state: str) -> str:
    """Build the claude.ai authorize URL for a PKCE S256 code flow.

    ``code=true`` selects the code-display consent variant (the callback
    page shows the code for the operator to paste).
    """
    params = {
        "code": "true",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def split_pasted_code(pasted: str) -> tuple[str, str | None]:
    """Normalize an operator-pasted authorization code.

    The consent page may display the code in ``code#state`` form; tolerate
    that, surrounding whitespace, and the bare-code form. Returns
    ``(code, embedded_state_or_None)``.
    """
    cleaned = pasted.strip()
    if "#" in cleaned:
        code, _, embedded_state = cleaned.partition("#")
        return code.strip(), (embedded_state.strip() or None)
    return cleaned, None


def _token_set_from_response(
    payload: dict[str, Any], *, fallback_refresh_token: str | None = None
) -> TokenSet:
    """Map a token-endpoint JSON payload to a :class:`TokenSet`.

    ``expires_in`` (relative seconds) becomes an absolute epoch stamped at
    receipt time. A refresh response that omits ``refresh_token`` keeps the
    one the caller already holds (``fallback_refresh_token``).
    """
    access_token = payload.get("access_token")
    if not access_token or not isinstance(access_token, str):
        raise OAuthExchangeError(
            "Token endpoint response is missing 'access_token'.",
            body=str(payload)[:500],
        )
    expires_in = payload.get("expires_in")
    token_expires_at: int | None = None
    if isinstance(expires_in, (int, float)):
        token_expires_at = int(time.time()) + int(expires_in)
    refresh = payload.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        refresh = fallback_refresh_token
    scope = payload.get("scope")
    token_type = payload.get("token_type")
    return TokenSet(
        access_token=access_token,
        refresh_token=refresh,
        token_expires_at=token_expires_at,
        scope=scope if isinstance(scope, str) else None,
        token_type=token_type if isinstance(token_type, str) else None,
    )


async def _post_token(
    body: dict[str, Any],
    *,
    client: httpx.AsyncClient | None,
    error_context: str,
    fallback_refresh_token: str | None = None,
) -> TokenSet:
    """POST ``body`` (JSON) to the token endpoint and map the response."""

    async def _do(c: httpx.AsyncClient) -> httpx.Response:
        return await c.post(TOKEN_URL, json=body)

    try:
        if client is not None:
            response = await _do(client)
        else:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as own_client:
                response = await _do(own_client)
    except httpx.HTTPError as exc:
        raise OAuthExchangeError(f"{error_context}: network error: {exc}") from exc

    if response.status_code >= 400:
        raise OAuthExchangeError(
            f"{error_context}: token endpoint returned HTTP {response.status_code}.",
            status_code=response.status_code,
            body=response.text[:500],
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise OAuthExchangeError(
            f"{error_context}: token endpoint returned non-JSON body.",
            status_code=response.status_code,
            body=response.text[:500],
        ) from exc
    return _token_set_from_response(payload, fallback_refresh_token=fallback_refresh_token)


async def exchange_code(
    code: str,
    *,
    verifier: str,
    state: str,
    client: httpx.AsyncClient | None = None,
) -> TokenSet:
    """Exchange an authorization code (+ PKCE verifier) for a token set."""
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "state": state,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    return await _post_token(body, client=client, error_context="OAuth code exchange failed")


async def refresh_token(
    refresh_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> TokenSet:
    """Exchange a refresh token for a rotated token set."""
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }
    return await _post_token(
        body,
        client=client,
        error_context="OAuth token refresh failed",
        fallback_refresh_token=refresh_token,
    )

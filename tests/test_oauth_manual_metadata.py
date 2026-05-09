"""Tests for ManualOAuthClientProvider — the non-DCR override path."""

from __future__ import annotations

import inspect
from typing import Any

import httpx
from mcp.client.auth import TokenStorage
from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)

from the_one.mcp.oauth.manual_metadata import (
    ManualOAuthClientProvider,
    ManualOAuthMetadata,
)


class _StubTokenStorage(TokenStorage):
    """Trivial TokenStorage stub — in-memory, no persistence side effects."""

    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


def _make_provider() -> tuple[ManualOAuthClientProvider, dict[str, Any]]:
    """Construct a provider whose redirect captures the SDK-generated state
    and whose callback returns it back so the SDK's state-parity check
    passes — letting the override drive past _perform_authorization()
    to the token-exchange yield where we observe-and-abort.
    """
    storage = _StubTokenStorage()
    captured: dict[str, Any] = {}

    async def capture_redirect(authorization_url: str) -> None:
        from urllib.parse import parse_qs, urlsplit

        captured["redirect_url"] = authorization_url
        qs = parse_qs(urlsplit(authorization_url).query)
        captured["state"] = qs.get("state", [None])[0]

    async def replay_callback() -> tuple[str, str | None]:
        return ("test-code", captured.get("state"))

    client_metadata = OAuthClientMetadata(
        redirect_uris=["http://127.0.0.1:8484/api/oauth/callback"],
        client_name="the-one",
    )
    provider = ManualOAuthClientProvider(
        server_url="https://api.example.com/mcp",
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=capture_redirect,
        callback_handler=replay_callback,
        manual_metadata=ManualOAuthMetadata(
            client_id="cid-manual",
            auth_endpoint="https://idp.example.com/login/oauth/authorize",
            token_endpoint="https://idp.example.com/login/oauth/access_token",
        ),
    )
    return provider, captured


async def test_manual_provider_skips_discovery_endpoints() -> None:
    """A12 — driving the override past a 401 yields NO ``.well-known`` requests.

    The override elides Step 1 (PRM discovery) + Step 2 (OASM
    discovery), so after the initial yield + the 401 response is sent
    in, the next yielded request is the token-exchange POST (Step 5)
    — never a ``.well-known/oauth-protected-resource`` or
    ``.well-known/oauth-authorization-server`` GET.
    """
    provider, captured = _make_provider()

    # Construct the initial (protected resource) request the SDK would
    # have built. The 401 response triggers the OAuth flow.
    initial_request = httpx.Request(
        "GET",
        "https://api.example.com/mcp",
        headers={"MCP-Protocol-Version": "2025-06-18"},
    )
    response_401 = httpx.Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="example", scope="mcp:read"'},
        request=initial_request,
    )

    flow = provider.async_auth_flow(initial_request)
    yielded_urls: list[str] = []

    # First yield is the initial protected request being passed through.
    req = await flow.__anext__()
    yielded_urls.append(str(req.url))

    # Send the 401 — the override enters the elided 401-handler body
    # and (after running redirect_handler + callback_handler in
    # _perform_authorization) yields the token-exchange POST.
    req = await flow.asend(response_401)
    yielded_urls.append(str(req.url))

    # Abort the generator; we don't need to drive past the token POST.
    await flow.aclose()

    # No ``.well-known`` URL was ever yielded.
    for url in yielded_urls:
        assert "/.well-known/" not in url, (
            f"Manual provider unexpectedly yielded a discovery URL: {url}"
        )

    # The token endpoint is the manually supplied one.
    assert any(
        url.startswith("https://idp.example.com/login/oauth/access_token")
        for url in yielded_urls[1:]
    ), f"Expected token-exchange POST in yielded urls: {yielded_urls}"

    # The redirect_handler was called exactly once with a URL pointing
    # at the manually supplied auth_endpoint (not a discovered one).
    auth_url = captured["redirect_url"]
    assert auth_url.startswith(
        "https://idp.example.com/login/oauth/authorize?"
    )

    # And client_info was pre-set in _initialize from the synthesized
    # ManualOAuthMetadata.client_id (not from a DCR registration).
    assert provider.context.client_info is not None
    assert provider.context.client_info.client_id == "cid-manual"


def test_async_auth_flow_body_shape_pinned() -> None:
    """A12b — pin the parent's ``async_auth_flow`` body shape.

    If a future ``mcp`` package bump removes any of these substrings,
    this test fails loudly — the override may need re-verification
    against the new SDK body.
    """
    src = inspect.getsource(OAuthClientProvider.async_auth_flow)
    expected_substrings = (
        "for url in",
        "_perform_authorization()",
        "_handle_token_response",
        "_add_auth_header",
        "if response.status_code == 401",
        "elif response.status_code == 403",
    )
    for sub in expected_substrings:
        assert sub in src, (
            f"SDK body-shape substring missing: {sub!r}. "
            "OAuthClientProvider.async_auth_flow may have been refactored — "
            "re-verify ManualOAuthClientProvider.async_auth_flow against the "
            "new SDK body before trusting the override."
        )

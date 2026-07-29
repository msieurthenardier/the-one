"""Unit tests for the anthropic-plan PKCE OAuth flow module.

All HTTP is mocked via ``httpx.MockTransport`` injected through the
module's ``client=`` parameter — no network. The live authorize endpoint
was spike-verified separately (M19 F01 L01 flight log).
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from the_one.llm import anthropic_oauth
from the_one.llm.anthropic_oauth import (
    OAuthExchangeError,
    TokenSet,
    build_authorize_url,
    derive_challenge,
    exchange_code,
    generate_state,
    generate_verifier,
    refresh_token,
    split_pasted_code,
)


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── PKCE helpers ─────────────────────────────────────────────────────────


def test_verifier_is_urlsafe_and_unique() -> None:
    v1, v2 = generate_verifier(), generate_verifier()
    assert v1 != v2
    assert len(v1) == 43  # 32 bytes, base64url, unpadded
    assert "=" not in v1 and "+" not in v1 and "/" not in v1


def test_challenge_is_s256_of_verifier() -> None:
    verifier = generate_verifier()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert derive_challenge(verifier) == expected


def test_authorize_url_construction() -> None:
    verifier = generate_verifier()
    state = generate_state()
    url = build_authorize_url(code_challenge=derive_challenge(verifier), state=state)

    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == anthropic_oauth.AUTHORIZE_URL
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert params["client_id"] == anthropic_oauth.CLIENT_ID
    assert params["response_type"] == "code"
    assert params["redirect_uri"] == anthropic_oauth.REDIRECT_URI
    assert params["scope"] == anthropic_oauth.SCOPE
    assert params["code"] == "true"
    assert params["code_challenge"] == derive_challenge(verifier)
    assert params["code_challenge_method"] == "S256"
    assert params["state"] == state


# ── Pasted-code normalization ────────────────────────────────────────────


def test_split_bare_code() -> None:
    assert split_pasted_code("abc123") == ("abc123", None)


def test_split_code_hash_state() -> None:
    assert split_pasted_code("abc123#st-42") == ("abc123", "st-42")


def test_split_tolerates_whitespace() -> None:
    assert split_pasted_code("  abc123 # st-42 \n") == ("abc123", "st-42")
    assert split_pasted_code("\t abc123 \n") == ("abc123", None)


def test_split_trailing_hash_yields_no_state() -> None:
    assert split_pasted_code("abc123#") == ("abc123", None)


# ── Code exchange ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_maps_to_managed_keys_shape() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "expires_in": 3600,
                "scope": "user:inference",
                "token_type": "Bearer",
            },
        )

    before = int(time.time())
    async with _mock_client(handler) as client:
        token_set = await exchange_code(
            "the-code", verifier="the-verifier", state="the-state", client=client
        )
    after = int(time.time())

    assert seen["url"] == anthropic_oauth.TOKEN_URL
    assert seen["body"] == {
        "grant_type": "authorization_code",
        "code": "the-code",
        "state": "the-state",
        "client_id": anthropic_oauth.CLIENT_ID,
        "redirect_uri": anthropic_oauth.REDIRECT_URI,
        "code_verifier": "the-verifier",
    }
    assert token_set.access_token == "at-1"
    assert token_set.refresh_token == "rt-1"
    # Absolute epoch, derived from the relative expires_in at receipt time.
    assert before + 3600 <= token_set.token_expires_at <= after + 3600
    secrets = token_set.to_secrets()
    assert set(secrets) == {
        "access_token",
        "refresh_token",
        "token_expires_at",
        "scope",
        "token_type",
    }
    assert set(secrets) <= anthropic_oauth.OAUTH_MANAGED_SECRET_KEYS


@pytest.mark.asyncio
async def test_exchange_4xx_raises_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with _mock_client(handler) as client:
        with pytest.raises(OAuthExchangeError) as excinfo:
            await exchange_code("bad", verifier="v", state="s", client=client)
    assert excinfo.value.status_code == 400
    assert "invalid_grant" in (excinfo.value.body or "")


@pytest.mark.asyncio
async def test_exchange_missing_access_token_raises_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})

    async with _mock_client(handler) as client:
        with pytest.raises(OAuthExchangeError):
            await exchange_code("c", verifier="v", state="s", client=client)


@pytest.mark.asyncio
async def test_exchange_network_error_raises_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async with _mock_client(handler) as client:
        with pytest.raises(OAuthExchangeError):
            await exchange_code("c", verifier="v", state="s", client=client)


# ── Refresh ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_returns_rotated_tokens() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "access_token": "at-2",
                "refresh_token": "rt-2",
                "expires_in": 3600,
            },
        )

    async with _mock_client(handler) as client:
        token_set = await refresh_token("rt-1", client=client)

    assert seen["body"] == {
        "grant_type": "refresh_token",
        "refresh_token": "rt-1",
        "client_id": anthropic_oauth.CLIENT_ID,
    }
    assert token_set.access_token == "at-2"
    assert token_set.refresh_token == "rt-2"


@pytest.mark.asyncio
async def test_refresh_without_rotation_keeps_old_refresh_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "at-2", "expires_in": 60})

    async with _mock_client(handler) as client:
        token_set = await refresh_token("rt-keep", client=client)
    assert token_set.refresh_token == "rt-keep"


@pytest.mark.asyncio
async def test_refresh_4xx_raises_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    async with _mock_client(handler) as client:
        with pytest.raises(OAuthExchangeError) as excinfo:
            await refresh_token("revoked", client=client)
    assert excinfo.value.status_code == 401


# ── TokenSet.to_secrets ──────────────────────────────────────────────────


def test_to_secrets_omits_none_values() -> None:
    token_set = TokenSet(
        access_token="at",
        refresh_token=None,
        token_expires_at=None,
        scope=None,
        token_type=None,
    )
    assert token_set.to_secrets() == {"access_token": "at"}

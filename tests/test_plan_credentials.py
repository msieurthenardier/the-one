"""Tests for the anthropic-plan self-resolving credential source (M19 F01 L02).

Covers the DD-3 contract: per-provider-id process-wide singleton sources,
proactive refresh within the expiry margin, single-flight concurrency
(mocked token endpoint + call counter), re-read-inside-lock adoption,
rotation-safe merge-over-stored write-back via ``update_secrets``, typed
re-auth-required terminal failure (secrets NOT cleared), transient network
errors staying typed-OAuth (not re-auth), eviction, and two-config
independence.

The repository is real (aiosqlite over a tmp DB + Fernet encryptor);
``plan_credentials._provider_repo`` is monkeypatched to return it — the
same seam the lazy-import convention isolates in production.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet

from tests._schema_template import connect_template_db
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository
from the_one.encryption import Encryptor
from the_one.llm import anthropic_oauth, plan_credentials
from the_one.llm.plan_credentials import (
    EXPIRY_MARGIN_SECONDS,
    FALLBACK_EXPIRES_IN_SECONDS,
    PlanCredentialSource,
    ReauthRequiredError,
    evict_credential_source,
    get_credential_source,
)


@pytest.fixture
async def env(tmp_path, monkeypatch):
    """Real repository over a tmp DB, wired into the credential-source seam."""
    conn = await connect_template_db(tmp_path / "test.db")

    key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    key_path.write_bytes(key)
    encryptor = Encryptor(key, key_path=key_path)
    repo = LLMProviderRepository(conn, encryptor)

    async def _test_repo():
        return repo

    monkeypatch.setattr(plan_credentials, "_provider_repo", _test_repo)
    plan_credentials._reset_for_tests()
    yield SimpleNamespace(conn=conn, repo=repo, encryptor=encryptor)
    plan_credentials._reset_for_tests()
    await conn.close()


def _fresh_expiry() -> int:
    return int(time.time()) + 3600


def _near_expiry_ts() -> int:
    return int(time.time()) + EXPIRY_MARGIN_SECONDS - 60


async def _make_provider(env, provider_id: str = "plan-1", secrets: dict | None = None) -> str:
    await env.repo.create(
        LLMProviderConfig(
            id=provider_id,
            name=f"Claude Plan {provider_id}",
            type="anthropic-plan",
            base_url="https://api.anthropic.com",
            secrets=secrets if secrets is not None else {},
        )
    )
    return provider_id


def _secrets(
    access_token: str = "at-stored",
    refresh_token: str | None = "rt-stored",
    token_expires_at: int | None = None,
    **extra,
) -> dict:
    s: dict = {"access_token": access_token}
    if refresh_token is not None:
        s["refresh_token"] = refresh_token
    if token_expires_at is not None:
        s["token_expires_at"] = token_expires_at
    s.setdefault("scope", "org:create_api_key user:profile user:inference")
    s.setdefault("token_type", "Bearer")
    s.update(extra)
    return s


class _TokenEndpoint:
    """Mocked token endpoint with a request counter (single-flight assertions)."""

    def __init__(self, response: dict | int | Exception, *, rotate_refresh: bool = True):
        self.calls: list[dict] = []
        self._response = response
        self._rotate = rotate_refresh

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(json.loads(request.content))
        if isinstance(self._response, Exception):
            raise self._response
        if isinstance(self._response, int):
            return httpx.Response(self._response, json={"error": "invalid_grant"})
        return httpx.Response(200, json=self._response)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def _refresh_response(**overrides) -> dict:
    payload = {
        "access_token": "at-refreshed",
        "refresh_token": "rt-rotated",
        "expires_in": 3600,
        "scope": "org:create_api_key user:profile user:inference",
        "token_type": "Bearer",
    }
    payload.update(overrides)
    return payload


async def _wire(source: PlanCredentialSource, endpoint: _TokenEndpoint) -> httpx.AsyncClient:
    client = endpoint.client()
    source._http_client = client
    return client


# ── Registry ──────────────────────────────────────────────────────────────


class TestRegistry:
    async def test_singleton_per_provider_id(self, env) -> None:
        a1 = get_credential_source("plan-a")
        a2 = get_credential_source("plan-a")
        b = get_credential_source("plan-b")
        assert a1 is a2
        assert a1 is not b

    async def test_eviction_builds_fresh_source(self, env) -> None:
        before = get_credential_source("plan-a")
        evict_credential_source("plan-a")
        after = get_credential_source("plan-a")
        assert before is not after

    async def test_evicting_unknown_id_is_noop(self, env) -> None:
        evict_credential_source("never-cached")  # must not raise


# ── Token reads / proactive refresh ───────────────────────────────────────


class TestGetAccessToken:
    async def test_returns_stored_token_when_fresh(self, env) -> None:
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=_fresh_expiry()))
        endpoint = _TokenEndpoint(_refresh_response())
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            token = await source.get_access_token()
        assert token == "at-stored"
        assert endpoint.calls == []

    async def test_refreshes_proactively_within_margin(self, env) -> None:
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=_near_expiry_ts()))
        endpoint = _TokenEndpoint(_refresh_response())
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            token = await source.get_access_token()
        assert token == "at-refreshed"
        assert len(endpoint.calls) == 1
        assert endpoint.calls[0]["grant_type"] == "refresh_token"

    async def test_missing_expiry_treated_as_expired(self, env) -> None:
        """A stored token with no ``token_expires_at`` is never served as-is
        (edge case: clock skew / missing expiry → refresh path)."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=None))
        endpoint = _TokenEndpoint(_refresh_response())
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            token = await source.get_access_token()
        assert token == "at-refreshed"
        assert len(endpoint.calls) == 1

    async def test_no_stored_tokens_raises_reauth(self, env) -> None:
        pid = await _make_provider(env, secrets={})
        source = get_credential_source(pid)
        with pytest.raises(ReauthRequiredError) as excinfo:
            await source.get_access_token()
        assert excinfo.value.provider_id == pid
        # Actionable: names the provider and points at Library › Model providers.
        assert "Claude Plan" in str(excinfo.value)
        assert "Library › Model providers" in str(excinfo.value)

    async def test_access_token_without_refresh_token_raises_reauth(self, env) -> None:
        """An expired access token with no refresh token cannot renew."""
        pid = await _make_provider(env, secrets=_secrets(refresh_token=None, token_expires_at=1))
        source = get_credential_source(pid)
        with pytest.raises(ReauthRequiredError):
            await source.get_access_token()


# ── Single-flight + adoption ──────────────────────────────────────────────


class TestSingleFlight:
    async def test_concurrent_callers_one_refresh_call(self, env) -> None:
        """AC: N concurrent callers during an expired-token window produce
        exactly ONE refresh HTTP call; every caller gets the new token."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(_refresh_response())
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            tokens = await asyncio.gather(*(source.get_access_token() for _ in range(6)))
        assert tokens == ["at-refreshed"] * 6
        assert len(endpoint.calls) == 1

    async def test_adopts_newer_stored_token_inside_lock(self, env) -> None:
        """AC: the source re-reads stored secrets INSIDE the lock and adopts
        a newer stored token instead of refreshing (two-process pattern).

        The test holds the source's lock, starts a caller (which snapshots
        the expired token, then blocks on the lock), mutates the stored
        secrets to a fresh token set, then releases the lock — the caller
        must adopt the stored token with zero refresh HTTP calls.
        """
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(_refresh_response())
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            await source._lock.acquire()
            try:
                task = asyncio.create_task(source.get_access_token())
                # Let the task do its pre-lock read and block on the lock.
                await asyncio.sleep(0.05)
                assert not task.done()
                await env.repo.update_secrets(
                    pid,
                    _secrets(
                        access_token="at-other-process",
                        refresh_token="rt-other-process",
                        token_expires_at=_fresh_expiry(),
                    ),
                )
            finally:
                source._lock.release()
            token = await task
        assert token == "at-other-process"
        assert endpoint.calls == []

    async def test_two_config_independence(self, env) -> None:
        """AC: two plan rows have distinct sources with independent locks;
        refreshing one never touches the other's stored secrets."""
        pid_a = await _make_provider(
            env, "plan-a", secrets=_secrets("at-a", "rt-a", token_expires_at=1)
        )
        b_secrets = _secrets("at-b", "rt-b", token_expires_at=_fresh_expiry())
        pid_b = await _make_provider(env, "plan-b", secrets=b_secrets)

        source_a = get_credential_source(pid_a)
        source_b = get_credential_source(pid_b)
        assert source_a is not source_b
        assert source_a._lock is not source_b._lock

        endpoint = _TokenEndpoint(_refresh_response())
        async with await _wire(source_a, endpoint):
            token_a = await source_a.get_access_token()
        assert token_a == "at-refreshed"
        assert len(endpoint.calls) == 1
        assert endpoint.calls[0]["refresh_token"] == "rt-a"

        stored_b = (await env.repo.get(pid_b)).secrets
        assert stored_b == b_secrets
        assert (await env.repo.get(pid_a)).secrets["access_token"] == "at-refreshed"


# ── Rotation / write-back ─────────────────────────────────────────────────


class TestRotationWriteBack:
    async def test_rotated_refresh_token_persisted(self, env) -> None:
        """AC rotation safety: a response that rotates the refresh token
        stores the NEW one; a fresh read sees the whole rotated set."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(_refresh_response(refresh_token="rt-rotated"))
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            await source.get_access_token()
        stored = (await env.repo.get(pid)).secrets
        assert stored["access_token"] == "at-refreshed"
        assert stored["refresh_token"] == "rt-rotated"

    async def test_unrotated_response_keeps_old_refresh_token(self, env) -> None:
        """AC rotation safety: a response WITHOUT a refresh token keeps the
        stored one (delegating to ``anthropic_oauth.refresh_token``'s
        fallback semantics, pinned at the source level here)."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(_refresh_response(refresh_token=None))
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            await source.get_access_token()
        stored = (await env.repo.get(pid)).secrets
        assert stored["refresh_token"] == "rt-stored"

    async def test_merge_over_stored_preserves_elided_keys(self, env) -> None:
        """Implementation-guidance rule: the refreshed set merges OVER the
        stored secrets — a response eliding scope/token_type keeps the
        stored values, and non-managed keys survive untouched."""
        pid = await _make_provider(
            env,
            secrets=_secrets(token_expires_at=1, custom_marker="survives"),
        )
        endpoint = _TokenEndpoint(
            _refresh_response(scope=None, token_type=None, refresh_token=None)
        )
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            await source.get_access_token()
        stored = (await env.repo.get(pid)).secrets
        assert stored["scope"] == "org:create_api_key user:profile user:inference"
        assert stored["token_type"] == "Bearer"
        assert stored["custom_marker"] == "survives"

    async def test_missing_expires_in_stores_conservative_expiry(self, env) -> None:
        """Edge case: a refresh response without ``expires_in`` stores a
        conservative short expiry — never a missing/never-expiring stamp
        (which would mean refresh-every-request or a dead token served)."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(_refresh_response(expires_in=None))
        source = get_credential_source(pid)
        before = time.time()
        async with await _wire(source, endpoint):
            await source.get_access_token()
        stored = (await env.repo.get(pid)).secrets
        assert (
            before + FALLBACK_EXPIRES_IN_SECONDS - 5
            <= stored["token_expires_at"]
            <= time.time() + FALLBACK_EXPIRES_IN_SECONDS + 5
        )

    async def test_persisted_tokens_visible_to_fresh_source(self, env) -> None:
        """AC (e): persistence goes through ``update_secrets`` so a FRESH
        source (post-eviction) reads the refreshed set without refreshing."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(_refresh_response())
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            await source.get_access_token()
        evict_credential_source(pid)
        fresh = get_credential_source(pid)
        endpoint2 = _TokenEndpoint(_refresh_response())
        async with await _wire(fresh, endpoint2):
            token = await fresh.get_access_token()
        assert token == "at-refreshed"
        assert endpoint2.calls == []


# ── Terminal / transient failure ──────────────────────────────────────────


class TestRefreshFailure:
    async def test_terminal_4xx_raises_reauth_and_keeps_secrets(self, env) -> None:
        """AC terminal failure: invalid-grant-style 4xx → typed re-auth error
        carrying the provider id; stored secrets NOT cleared."""
        stored_before = _secrets(token_expires_at=1)
        pid = await _make_provider(env, secrets=stored_before)
        endpoint = _TokenEndpoint(400)
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            with pytest.raises(ReauthRequiredError) as excinfo:
                await source.get_access_token()
        assert excinfo.value.provider_id == pid
        assert "Library › Model providers" in str(excinfo.value)
        assert (await env.repo.get(pid)).secrets == stored_before

    async def test_network_error_raises_typed_oauth_not_reauth(self, env) -> None:
        """Transient failures (network blip) re-raise as the existing typed
        OAuth error — they must NOT demand re-authentication."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(httpx.ConnectError("boom"))
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            with pytest.raises(anthropic_oauth.OAuthExchangeError) as excinfo:
                await source.get_access_token()
        assert not isinstance(excinfo.value, ReauthRequiredError)

    async def test_5xx_raises_typed_oauth_not_reauth(self, env) -> None:
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(503)
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            with pytest.raises(anthropic_oauth.OAuthExchangeError) as excinfo:
                await source.get_access_token()
        assert not isinstance(excinfo.value, ReauthRequiredError)

    async def test_concurrent_terminal_failure_all_receive_error(self, env) -> None:
        """Edge case: N callers waiting on a failed refresh must ALL receive
        the re-auth error — not one error and N-1 hangs."""
        pid = await _make_provider(env, secrets=_secrets(token_expires_at=1))
        endpoint = _TokenEndpoint(400)
        source = get_credential_source(pid)
        async with await _wire(source, endpoint):
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(source.get_access_token() for _ in range(5)),
                    return_exceptions=True,
                ),
                timeout=10,
            )
        assert len(results) == 5
        assert all(isinstance(r, ReauthRequiredError) for r in results)

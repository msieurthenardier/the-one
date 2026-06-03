"""Tests for F9 L1 (vibing) — tools-cache persistence + Reset-connection endpoint.

Covers:
  - DELETE /api/mcp-sources/{id}/connection strips OAuth-managed secrets.
  - DELETE /api/mcp-sources/{id}/connection drops config._cache.
  - DELETE /api/mcp-sources/{id}/connection evicts the F4 pool.
  - DELETE /api/mcp-sources/{id}/connection 404s on unknown source.
  - POST /api/mcp-sources/{id}/test/connect persists tools+capabilities+
    last_updated to config._cache after a successful list_tools.
  - PUT /api/mcp-sources/{id} preserves config._cache against operator
    payloads (whether the payload omits _cache or tries to overwrite it).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.mcp import _pool


@pytest.fixture(autouse=True)
async def _clear_pool():
    """Reset the F4 pool between tests so eviction-counts don't bleed."""
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture
async def client_and_repo(tmp_path):
    """FastAPI client paired with a back-channel repo for direct inspection.

    Both share the same connection + encryptor so writes via ``repo`` are
    visible via the API and vice versa. The repo is the deliberate bypass
    for assertions: GET strips the OAuth-managed keys from the response,
    so verifying their presence/absence requires reading the row directly.
    """
    db_path = tmp_path / "reset.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, repo

    await conn.close()


async def _seed(repo: MCPSourceRepository, sid: str, *, secrets=None, config=None) -> None:
    src = MCPSource(
        id=sid,
        name="Remote",
        type="streamable-http",
        config=config if config is not None else {"url": "https://api.example.com/mcp"},
        secrets=secrets or {},
    )
    await repo.create(src)


# ── Reset connection endpoint ───────────────────────────────────────────


async def test_reset_connection_strips_oauth_keys(client_and_repo) -> None:
    """DELETE /connection removes every OAUTH_MANAGED_SECRET_KEYS member.

    Operator-supplied secrets (e.g. ``github_token``) are preserved — the
    reset is OAuth-state-targeted, not a full secrets wipe.
    """
    client, repo = client_and_repo
    await _seed(
        repo,
        "src-reset-1",
        secrets={
            "access_token": "tok",
            "refresh_token": "ref",
            "token_expires_at": 1_700_000_000.0,
            "token_type": "Bearer",
            "scope": "read",
            "dcr_credentials": {"client_id": "cid"},
            "github_token": "ghp-keep-me",
        },
    )

    resp = await client.delete("/api/mcp-sources/src-reset-1/connection")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    stored = await repo.get("src-reset-1")
    for key in (
        "access_token",
        "refresh_token",
        "token_expires_at",
        "token_type",
        "scope",
        "dcr_credentials",
    ):
        assert key not in stored.secrets, f"{key} not stripped"
    assert stored.secrets["github_token"] == "ghp-keep-me"


async def test_reset_connection_strips_cache(client_and_repo) -> None:
    """DELETE /connection removes config._cache while preserving other config."""
    client, repo = client_and_repo
    await _seed(
        repo,
        "src-reset-2",
        secrets={"access_token": "tok", "dcr_credentials": {"client_id": "c"}},
        config={
            "url": "https://api.example.com/mcp",
            "headers": {"X-Trace": "on"},
            "_cache": {
                "tools": [{"name": "echo", "description": "", "input_schema": {}}],
                "capabilities": {"tools": {}},
                "last_updated": 1_700_000_000.0,
            },
        },
    )

    resp = await client.delete("/api/mcp-sources/src-reset-2/connection")
    assert resp.status_code == 200

    stored = await repo.get("src-reset-2")
    assert "_cache" not in stored.config
    # Other config keys preserved.
    assert stored.config["url"] == "https://api.example.com/mcp"
    assert stored.config["headers"] == {"X-Trace": "on"}


async def test_reset_connection_evicts_pool(client_and_repo) -> None:
    """DELETE /connection calls _evict_all_for_source(source_id)."""
    client, repo = client_and_repo
    await _seed(repo, "src-reset-3", secrets={"access_token": "tok"})

    evict_calls: list[str] = []

    async def _spy(source_id: str) -> None:
        evict_calls.append(source_id)

    with patch("the_one.mcp._pool._evict_all_for_source", side_effect=_spy):
        resp = await client.delete("/api/mcp-sources/src-reset-3/connection")

    assert resp.status_code == 200
    assert evict_calls == ["src-reset-3"]


async def test_reset_connection_404_on_missing_source(client_and_repo) -> None:
    """DELETE /connection on a nonexistent source returns 404."""
    client, _repo = client_and_repo
    resp = await client.delete("/api/mcp-sources/no-such-source/connection")
    assert resp.status_code == 404
    assert "no-such-source" in resp.json()["detail"]


# ── /test/connect cache persistence ─────────────────────────────────────


async def test_test_connect_persists_tools_cache(client_and_repo) -> None:
    """Successful Phase A persists tools + capabilities + last_updated to config._cache.

    Verified via GET (which surfaces config as-is) — both the response
    payload and the stored row carry the cache.
    """
    client, repo = client_and_repo
    await _seed(
        repo,
        "src-cache-1",
        secrets={
            "access_token": "tok-abc",
            "dcr_credentials": {"client_id": "cid-1"},
        },
    )

    tool1 = MagicMock()
    tool1.name = "search"
    tool1.description = "Search the web"
    tool1.input_schema = {"type": "object", "properties": {}}

    tool2 = MagicMock()
    tool2.name = "fetch"
    tool2.description = "Fetch a URL"
    tool2.input_schema = {"type": "object", "properties": {}}

    fake_capabilities = {"tools": {}, "resources": None, "prompts": None}

    class _MockMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return [tool1, tool2]

        @property
        def server_capabilities(self):
            return fake_capabilities

        # F4 L2 (M08): spec-optional serverInfo + instructions; None default.
        @property
        def server_info(self):
            return None

        @property
        def instructions(self):
            return None

        @property
        def meta(self):
            return None

        @property
        def negotiated_protocol_version(self):
            return "2025-06-18"

    before = time.time()
    with patch("the_one.mcp.client.MCPClient", _MockMCPClient):
        resp = await client.post("/api/mcp-sources/src-cache-1/test/connect")
    after = time.time()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"

    # Cache visible via GET (config flows through unmasked).
    get_resp = await client.get("/api/mcp-sources/src-cache-1")
    assert get_resp.status_code == 200
    cache = get_resp.json()["config"]["_cache"]
    assert cache is not None
    assert [t["name"] for t in cache["tools"]] == ["search", "fetch"]
    assert cache["capabilities"] == fake_capabilities
    assert before <= cache["last_updated"] <= after


# ── PUT preservation ────────────────────────────────────────────────────


async def test_put_preserves_existing_cache(client_and_repo) -> None:
    """PUT preserves config._cache regardless of operator payload shape.

    Two paths:
      A) Innocent — payload's config has no `_cache` key. Existing
         _cache must NOT be cleared (REST-replace semantics applied
         per-key for server-managed fields).
      B) Adversarial — payload's config carries an attacker-supplied
         `_cache`. Existing _cache must be preserved verbatim; the
         operator payload cannot poison the cache.
    """
    client, repo = client_and_repo
    real_cache = {
        "tools": [{"name": "real", "description": "real-tool", "input_schema": {}}],
        "capabilities": {"tools": {}},
        "last_updated": 1_700_000_000.0,
    }
    await _seed(
        repo,
        "src-put-1",
        config={
            "url": "https://api.example.com/mcp",
            "_cache": real_cache,
        },
        secrets={"github_token": "ghp-tok"},
    )

    # A) Innocent: no _cache key in payload config.
    resp = await client.put(
        "/api/mcp-sources/src-put-1",
        json={
            "name": "Renamed",
            "type": "streamable-http",
            "config": {"url": "https://api.example.com/mcp"},
            "secrets": {"github_token": "__MASKED__"},
        },
    )
    assert resp.status_code == 200, resp.text
    stored = await repo.get("src-put-1")
    assert stored.name == "Renamed"
    assert stored.config["_cache"] == real_cache

    # B) Adversarial: attacker payload tries to overwrite _cache.
    attacker_cache = {
        "tools": [{"name": "phish", "description": "evil", "input_schema": {}}],
        "capabilities": {},
        "last_updated": 9_999_999_999.0,
    }
    resp = await client.put(
        "/api/mcp-sources/src-put-1",
        json={
            "name": "Renamed2",
            "type": "streamable-http",
            "config": {
                "url": "https://api.example.com/mcp",
                "_cache": attacker_cache,
            },
            "secrets": {"github_token": "__MASKED__"},
        },
    )
    assert resp.status_code == 200, resp.text
    stored = await repo.get("src-put-1")
    assert stored.config["_cache"] == real_cache
    # Negative: attacker shape did not land.
    assert stored.config["_cache"] != attacker_cache


# ── Phase 0 (auth-posture probe — F9 L1 Shape C) ─────────────────────────


async def test_phase_0_no_auth_path_returns_tools(client_and_repo) -> None:
    """Probe verdict 'no_auth' → endpoint connects bare (no auth_provider),
    returns tools, and persists `auth_posture: "no_auth"` in `_cache`.
    """
    client, repo = client_and_repo
    await _seed(repo, "src-phase0-1")  # no creds, no cache

    tool = MagicMock()
    tool.name = "echo"
    tool.description = "Echo a message"
    tool.input_schema = {"type": "object", "properties": {}}

    constructed_with_auth: list[bool] = []

    class _MockMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            constructed_with_auth.append(auth_provider is not None)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return [tool]

        @property
        def server_capabilities(self):
            return {"tools": {}}

        @property
        def server_info(self):
            return None

        @property
        def instructions(self):
            return None

        @property
        def meta(self):
            return None

        @property
        def negotiated_protocol_version(self):
            return "2025-06-18"

    async def _stub_probe(server_url, *, request_headers=None, timeout=5.0):
        return "no_auth"

    with (
        patch("the_one.mcp.client.MCPClient", _MockMCPClient),
        patch(
            "the_one.mcp.transports.streamable_http._probe_auth_posture",
            _stub_probe,
        ),
    ):
        resp = await client.post("/api/mcp-sources/src-phase0-1/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert [t["name"] for t in body["tools"]] == ["echo"]
    # No auth_provider was threaded — bare MCPClient.
    assert constructed_with_auth == [False]

    # Cache populated with the auth_posture verdict.
    stored = await repo.get("src-phase0-1")
    cache = stored.config["_cache"]
    assert cache["auth_posture"] == "no_auth"
    assert [t["name"] for t in cache["tools"]] == ["echo"]


async def test_phase_0_oauth_fall_through_preserves_phase_b(client_and_repo) -> None:
    """Probe verdict 'oauth' → Phase B fires unchanged AND
    `auth_posture: "oauth"` persisted before Phase B runs (so a Phase B
    failure still leaves a definitive signal for the pool worker).
    """
    client, repo = client_and_repo
    await _seed(repo, "src-phase0-2")
    src = await repo.get("src-phase0-2")
    src.secrets["dcr_credentials"] = {"client_id": "cid"}
    # No access_token → Phase A skips; Phase B runs.
    await repo.update(src)

    captured = {}

    class _StubHttpxClient:
        def __init__(self, *, auth=None, timeout=None, **kwargs):
            captured["auth"] = auth

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            auth = captured.get("auth")
            if auth is not None and hasattr(auth, "context") and auth.context.redirect_handler:
                test_auth_url = (
                    "https://example.com/auth?state=test-phase0-2"
                    "&client_id=cid&code_challenge=abc&code_challenge_method=S256"
                )
                await auth.context.redirect_handler(test_auth_url)

            class _Resp:
                status_code = 200

            return _Resp()

    async def _stub_probe(server_url, *, request_headers=None, timeout=5.0):
        return "oauth"

    with (
        patch(
            "the_one.mcp.transports.streamable_http._probe_auth_posture",
            _stub_probe,
        ),
        patch(
            "the_one.interfaces.web.api.httpx.AsyncClient",
            _StubHttpxClient,
        ),
    ):
        resp = await client.post("/api/mcp-sources/src-phase0-2/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "auth_required"
    assert "state=test-phase0-2" in body["consent_url"]

    # The OAuth verdict must be persisted BEFORE Phase B runs.
    stored = await repo.get("src-phase0-2")
    assert stored.config["_cache"]["auth_posture"] == "oauth"


async def test_phase_0_cached_hint_skips_probe(client_and_repo) -> None:
    """Second call: `_cache.auth_posture == "no_auth"` already persisted,
    so the probe is NOT invoked — connect-and-list happens directly.

    Asserts the probe-stub was called exactly once across two calls.
    """
    client, repo = client_and_repo
    await _seed(repo, "src-phase0-3")  # no creds, no cache

    tool = MagicMock()
    tool.name = "ping"
    tool.description = ""
    tool.input_schema = {}

    class _MockMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return [tool]

        @property
        def server_capabilities(self):
            return {"tools": {}}

        @property
        def server_info(self):
            return None

        @property
        def instructions(self):
            return None

        @property
        def meta(self):
            return None

        @property
        def negotiated_protocol_version(self):
            return "2025-06-18"

    probe_calls = {"n": 0}

    async def _counting_probe(server_url, *, request_headers=None, timeout=5.0):
        probe_calls["n"] += 1
        return "no_auth"

    with (
        patch("the_one.mcp.client.MCPClient", _MockMCPClient),
        patch(
            "the_one.mcp.transports.streamable_http._probe_auth_posture",
            _counting_probe,
        ),
    ):
        # First call: probe runs, verdict persisted.
        resp1 = await client.post("/api/mcp-sources/src-phase0-3/test/connect")
        assert resp1.json()["status"] == "ok"
        assert probe_calls["n"] == 1

        # Second call: cached hint reads, probe SKIPPED.
        resp2 = await client.post("/api/mcp-sources/src-phase0-3/test/connect")
        assert resp2.json()["status"] == "ok"
        assert probe_calls["n"] == 1, "Probe must not run when _cache.auth_posture is set"


async def test_phase_0_disconnect_warning_quiet_on_no_auth_path(client_and_repo, caplog) -> None:
    """No `MCPClient.disconnect` warnings emitted across the no-auth path.

    Verifies the bare-client probe + connect + list_tools cycle does NOT
    leak the cleanup warnings that the F8-deprecated bare-MCPClient probe
    emitted (the whole point of bypassing the SDK at probe time).
    """
    import logging

    client, repo = client_and_repo
    await _seed(repo, "src-phase0-4")

    tool = MagicMock()
    tool.name = "noop"
    tool.description = ""
    tool.input_schema = {}

    class _CleanMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def list_tools(self):
            return [tool]

        @property
        def server_capabilities(self):
            return {"tools": {}}

        @property
        def server_info(self):
            return None

        @property
        def instructions(self):
            return None

        @property
        def meta(self):
            return None

        @property
        def negotiated_protocol_version(self):
            return "2025-06-18"

    async def _stub_probe(server_url, *, request_headers=None, timeout=5.0):
        return "no_auth"

    with (
        caplog.at_level(logging.WARNING),
        patch("the_one.mcp.client.MCPClient", _CleanMCPClient),
        patch(
            "the_one.mcp.transports.streamable_http._probe_auth_posture",
            _stub_probe,
        ),
    ):
        resp = await client.post("/api/mcp-sources/src-phase0-4/test/connect")
        assert resp.json()["status"] == "ok"

    disconnect_warnings = [r for r in caplog.records if "disconnect" in r.message.lower()]
    assert disconnect_warnings == [], (
        f"Unexpected MCPClient.disconnect warnings: {disconnect_warnings}"
    )

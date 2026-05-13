"""Tests for the FastAPI ``POST /api/mcp-sources/{id}/test/connect`` route (F6.5 L3)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web import api as api_mod
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
    """FastAPI client + DB-backed repo with one seeded streamable-http source."""
    db_path = tmp_path / "test-connect-endpoint.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    await repo.create(
        MCPSource(
            id="src-test-connect-1",
            name="Test connection source",
            type="streamable-http",
            config={"url": "https://api.example.com/mcp"},
        )
    )

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


async def test_test_connect_404_when_source_missing(client_and_repo) -> None:
    """A3 — POST returns 404 with detail message when source_id does not exist."""
    c, _repo = client_and_repo
    resp = await c.post("/api/mcp-sources/nonexistent/test/connect")
    assert resp.status_code == 404
    assert "nonexistent" in resp.json()["detail"]


async def test_test_connect_returns_ok_when_tokens_present(client_and_repo) -> None:
    """A4 — Phase A: dcr_credentials + access_token present; MCPClient.connect()
    + list_tools() succeeds; endpoint returns {status: "ok", tools: [...]}.

    Also verifies that auth_provider is threaded through to MCPClient (not bare).
    """
    c, repo = client_and_repo
    src = await repo.get("src-test-connect-1")
    src.secrets["dcr_credentials"] = {"client_id": "dcr-cid-1"}
    src.secrets["access_token"] = "tok-abc"
    await repo.update(src)

    # Mock MCPTool objects
    tool1 = MagicMock()
    tool1.name = "search"
    tool1.description = "Search the web"
    tool1.input_schema = {"type": "object", "properties": {}}

    tool2 = MagicMock()
    tool2.name = "fetch"
    tool2.description = "Fetch a URL"
    tool2.input_schema = {"type": "object", "properties": {}}

    # Track whether MCPClient was constructed with auth_provider
    constructed_with_auth: list[bool] = []

    class _MockMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            constructed_with_auth.append(auth_provider is not None)
            self._auth_provider = auth_provider

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return [tool1, tool2]

        @property
        def server_capabilities(self):
            # Minimal capabilities dict for this test (shape not asserted here).
            return {"tools": {}, "resources": None, "prompts": None, "logging": None, "experimental": None}

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

    # MCPClient is lazily imported inside the endpoint handler, so we patch
    # it at its source module (not at api.py which doesn't hold a module-level ref).
    with patch("the_one.mcp.client.MCPClient", _MockMCPClient):
        resp = await c.post("/api/mcp-sources/src-test-connect-1/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["tools"]) == 2
    assert body["tools"][0]["name"] == "search"
    assert body["tools"][1]["name"] == "fetch"

    # Verify auth_provider was threaded through (not a bare MCPClient).
    assert constructed_with_auth == [True], (
        "MCPClient must be constructed with auth_provider (not bare) in Phase A"
    )


async def test_test_connect_returns_auth_required_when_no_creds(client_and_repo) -> None:
    """A5 — Phase B: no creds; mock _drive_flow_test to resolve the future
    with a synthetic consent URL; endpoint returns {status: "auth_required"}.

    The mock resolves the future by intercepting httpx.AsyncClient's __aenter__
    so the flow doesn't need a real OAuth server.
    """
    c, _repo = client_and_repo
    # Source has no dcr_credentials and no access_token — Phase B path.

    # We need the mock to call consent_url_future.set_result before the
    # endpoint's asyncio.wait_for times out. We intercept _drive_flow_test
    # indirectly by patching httpx.AsyncClient used inside it.

    # Monkeypatch timeout to something generous for this test (it should
    # resolve quickly since we're mocking the flow).

    # Strategy: patch the build_oauth_provider_for_source to return a
    # provider whose httpx.Auth.__call__ resolves the future immediately.
    # The cleanest approach is to patch the _drive_flow_test coroutine itself
    # by intercepting asyncio.create_task inside the endpoint.

    # Simplest approach: patch httpx.AsyncClient in api.py to immediately
    # resolve the consent_url_future via the provider's redirect_handler.
    # We capture the provider object from build_oauth_provider_for_source.

    captured_provider = {}

    original_build = api_mod.__dict__.get(
        "build_oauth_provider_for_source",
        None,
    )

    # We'll patch build_oauth_provider_for_source to capture the provider
    # and then inject a future-resolving httpx client.
    consent_url_called = []

    class _FakeProvider:
        """Minimal httpx.Auth that resolves the future when auth_flow is applied."""

        def auth_flow(self, request):
            # Yield the request unchanged — we just need the flow to run.
            yield request

        async def async_auth_flow(self, request):
            # The async variant called by httpx.AsyncClient.
            yield request

    async def _mock_drive_and_resolve(*args, **kwargs):
        pass  # no-op; the test resolves via the patched flow

    # Use a different strategy: patch the internal _drive_flow_test
    # by making httpx.AsyncClient's post() call resolve the future
    # by calling the provider's redirect_handler. To do this cleanly,
    # we capture the consent_url_future by wrapping the endpoint's
    # asyncio.get_running_loop().create_future() call.

    # Cleanest approach: patch build_oauth_provider_for_source to return
    # a provider whose redirect_handler resolves the consent_url_future
    # that the endpoint creates. But we can't access that future from outside
    # without injecting into the endpoint's execution.

    # Final approach: patch httpx.AsyncClient inside api.py so that its
    # post() method immediately calls the redirect_handler on the provider
    # that was passed as auth=. We capture the provider from the call to
    # httpx.AsyncClient(auth=provider).

    captured = {}

    class _StubHttpxClient:
        def __init__(self, *, auth=None, timeout=None, **kwargs):
            captured["auth"] = auth

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            # The provider's redirect_handler must be called with an auth URL
            # containing a state param so the endpoint's consent_url_future
            # gets resolved. Trigger it directly.
            auth = captured.get("auth")
            if auth is not None and hasattr(auth, "context") and auth.context.redirect_handler:
                test_auth_url = (
                    "https://example.com/auth?state=test-state-001"
                    "&client_id=dcr-cid-test&code_challenge=abc&code_challenge_method=S256"
                )
                await auth.context.redirect_handler(test_auth_url)

            class _Resp:
                status_code = 200

            return _Resp()

    # Seed dcr_credentials so build_oauth_provider_for_source returns a provider
    # (required for redirect_handler to exist on the provider).
    src = await _repo.get("src-test-connect-1")
    src.secrets["dcr_credentials"] = {"client_id": "dcr-cid-test"}
    # No access_token → Phase A's bare-client attempt raises MCPAuthRequired
    # (mocked below); Phase B then runs.
    await _repo.update(src)

    # F8 L4 fix: Phase A now ALWAYS tries first (bare client when no tokens),
    # so we must mock MCPClient to raise MCPAuthRequired for the no-creds case
    # so the endpoint falls through to Phase B's DCR + consent_url flow.
    from the_one.mcp.errors import MCPAuthRequired

    class _AuthRequiredMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            self._source = source

        async def __aenter__(self):
            raise MCPAuthRequired(
                source_id=self._source.id,
                resource_metadata_url=None,
                consent_url=None,
            )

        async def __aexit__(self, *args):
            pass

    # F9 L1 Shape C: Phase 0 probes auth posture before Phase A. For this
    # test we want the OAuth flow path, so mock the probe to return "oauth"
    # (the verdict that falls through to Phase B).
    async def _stub_probe(server_url, *, timeout=5.0):
        return "oauth"

    with patch("the_one.mcp.client.MCPClient", _AuthRequiredMCPClient), \
         patch(
             "the_one.mcp.transports.streamable_http._probe_auth_posture",
             _stub_probe,
         ), \
         patch("the_one.interfaces.web.api.httpx.AsyncClient", _StubHttpxClient):
        resp = await c.post("/api/mcp-sources/src-test-connect-1/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "auth_required"
    assert "consent_url" in body
    assert "state=test-state-001" in body["consent_url"]


async def test_test_connect_success_includes_capabilities(client_and_repo) -> None:
    """L1.3 + L1.6: Phase A success return surfaces server_capabilities verbatim."""
    c, repo = client_and_repo
    src = await repo.get("src-test-connect-1")
    src.secrets["dcr_credentials"] = {"client_id": "dcr-cid-caps"}
    src.secrets["access_token"] = "tok-caps"
    await repo.update(src)

    # Simulate server capabilities (as model_dump(mode="json") would produce)
    fake_capabilities = {
        "tools": {},
        "resources": None,
        "prompts": {"listChanged": True},
        "logging": None,
        "experimental": None,
    }

    class _MockMCPClientWithCaps:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return []

        @property
        def server_capabilities(self):
            return fake_capabilities

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

    with patch("the_one.mcp.client.MCPClient", _MockMCPClientWithCaps):
        resp = await c.post("/api/mcp-sources/src-test-connect-1/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "capabilities" in body
    caps = body["capabilities"]
    assert caps["tools"] == {}
    assert caps["prompts"] == {"listChanged": True}


async def test_test_connect_capabilities_preserves_none_values(client_and_repo) -> None:
    """L1.6: model_dump shape preserved verbatim — None values are NOT dropped or renamed.

    Edge case: server announcing {tools: {}, resources: None} produces
    capabilities.resources is None in the response (no key invention).
    """
    c, repo = client_and_repo
    src = await repo.get("src-test-connect-1")
    src.secrets["dcr_credentials"] = {"client_id": "dcr-cid-none"}
    src.secrets["access_token"] = "tok-none"
    await repo.update(src)

    # Capabilities with all-None except tools (empty dict)
    sparse_capabilities = {
        "tools": {},
        "resources": None,
        "prompts": None,
        "logging": None,
        "experimental": None,
    }

    class _MockMCPClientSparse:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return []

        @property
        def server_capabilities(self):
            return sparse_capabilities

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

    with patch("the_one.mcp.client.MCPClient", _MockMCPClientSparse):
        resp = await c.post("/api/mcp-sources/src-test-connect-1/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    caps = body["capabilities"]
    # None values must be present (not dropped by FastAPI serializer)
    assert "resources" in caps
    assert caps["resources"] is None
    assert "tools" in caps
    assert caps["tools"] == {}


async def test_test_connect_consent_url_timeout(client_and_repo, monkeypatch) -> None:
    """A6 — consent_url_timeout: monkeypatch _TEST_CONNECT_TIMEOUT to a short
    value; SDK never calls redirect_handler; endpoint returns
    {status: "error", error: "consent_url_timeout"} within timeout + epsilon.
    """
    c, repo = client_and_repo

    # Short timeout so the test doesn't take 15 seconds.
    monkeypatch.setattr(api_mod, "_TEST_CONNECT_TIMEOUT", 0.3)

    # Seed dcr_credentials so Phase B runs (and has a provider to work with).
    src = await repo.get("src-test-connect-1")
    src.secrets["dcr_credentials"] = {"client_id": "dcr-cid-timeout"}
    # No access_token → Phase A skips; Phase B runs.
    await repo.update(src)

    class _StubHttpxClient:
        """httpx.AsyncClient that blocks indefinitely — simulates a slow server
        that never triggers the auth flow."""

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            # Never resolves → consent_url_future times out.
            await asyncio.sleep(999)

    # F8 L4 fix: Phase A now ALWAYS tries first. Mock MCPClient to raise
    # MCPAuthRequired so the endpoint falls through to Phase B's consent flow.
    from the_one.mcp.errors import MCPAuthRequired

    class _AuthRequiredMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            self._source = source

        async def __aenter__(self):
            raise MCPAuthRequired(
                source_id=self._source.id,
                resource_metadata_url=None,
                consent_url=None,
            )

        async def __aexit__(self, *args):
            pass

    # F9 L1 Shape C: mock the Phase 0 probe to return "oauth" so the flow
    # falls through to Phase B (where the consent_url_future timeout fires).
    async def _stub_probe(server_url, *, timeout=5.0):
        return "oauth"

    with patch("the_one.mcp.client.MCPClient", _AuthRequiredMCPClient), \
         patch(
             "the_one.mcp.transports.streamable_http._probe_auth_posture",
             _stub_probe,
         ), \
         patch("the_one.interfaces.web.api.httpx.AsyncClient", _StubHttpxClient):
        resp = await c.post("/api/mcp-sources/src-test-connect-1/test/connect")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"] == "consent_url_timeout"


async def test_test_connect_uses_override_payload_url(client_and_repo) -> None:
    """F8 L4 — operator's in-flight URL in the request body is used by Test connection,
    not the persisted URL. Verifies the operator-asked-for fix: 'Test should work
    with whats in the field, not whats in the db'.
    """
    c, repo = client_and_repo
    src = await repo.get("src-test-connect-1")
    # Persisted URL is https://api.example.com/mcp; populate tokens so Phase A fires.
    src.secrets["dcr_credentials"] = {"client_id": "dcr-cid-override"}
    src.secrets["access_token"] = "tok-override"
    await repo.update(src)

    # Capture the URL the MCPClient is constructed with — must be the OVERRIDE
    # URL from the request body, NOT the persisted one.
    captured_urls: list[str] = []

    class _CapturingMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            captured_urls.append(source.config.get("url"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return []

        @property
        def server_capabilities(self):
            return {"tools": {}, "resources": None, "prompts": None, "logging": None, "experimental": None}

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

    override_url = "https://operator-edited.example.com/mcp"
    with patch("the_one.mcp.client.MCPClient", _CapturingMCPClient):
        resp = await c.post(
            "/api/mcp-sources/src-test-connect-1/test/connect",
            json={
                "type": "streamable-http",
                "config": {"url": override_url},
                "secrets": {},
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert captured_urls == [override_url], (
        f"Test connection used persisted URL instead of override; "
        f"captured: {captured_urls}, expected: [{override_url!r}]"
    )


async def test_test_connect_override_preserves_oauth_managed_secrets(client_and_repo) -> None:
    """F8 L4 — operator's in-flight `secrets` payload cannot overwrite OAuth-managed
    keys (`access_token`, `dcr_credentials`, etc.). Mirrors the PUT endpoint's
    canonical secret-protection logic.
    """
    c, repo = client_and_repo
    src = await repo.get("src-test-connect-1")
    src.secrets["dcr_credentials"] = {"client_id": "dcr-real"}
    src.secrets["access_token"] = "tok-real"
    await repo.update(src)

    captured_secrets: list[dict] = []

    class _CapturingMCPClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            captured_secrets.append(dict(source.secrets))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return []

        @property
        def server_capabilities(self):
            return {"tools": {}, "resources": None, "prompts": None, "logging": None, "experimental": None}

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

    with patch("the_one.mcp.client.MCPClient", _CapturingMCPClient):
        resp = await c.post(
            "/api/mcp-sources/src-test-connect-1/test/connect",
            json={
                "type": "streamable-http",
                "config": {"url": "https://api.example.com/mcp"},
                "secrets": {
                    # Operator tries to inject fake tokens — must be ignored.
                    "access_token": "fake-injected",
                    "dcr_credentials": {"client_id": "fake-injected-cid"},
                    # Operator-editable header — must pass through.
                    "X-Custom-Header": "operator-value",
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert len(captured_secrets) == 1
    secrets = captured_secrets[0]
    # OAuth-managed keys preserved from DB, not overwritten by injection.
    assert secrets["access_token"] == "tok-real"
    assert secrets["dcr_credentials"] == {"client_id": "dcr-real"}
    # Operator-editable secret passes through.
    assert secrets["X-Custom-Header"] == "operator-value"


# NOTE: A `test_test_connect_no_auth_server_succeeds_without_phase_b` test
# was attempted during F8 L4 but removed when the underlying Phase A.5
# bare-client probe was disabled (Anomaly A6 in flight log — anyio cross-
# task cancel-scope leak crashed the FastAPI handler). No-auth MCP server
# detection is deferred to a follow-up flight that introduces an explicit
# `auth_required: bool | None` hint on `MCPSource`.

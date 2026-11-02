"""Test-connection route x negotiation (Mission 29 F2 L3: DD2, DD9, DD10).

Real fixtures: the dual-era ``hello_server`` ASGI app behind small wrappers,
served through the transport's test seam; only the probe verdict (and, for the
sign-in leg, the Phase B httpx client) is stubbed.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx2
import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._mcp_signin_helpers import serve_asgi
from tests._schema_template import connect_template_db
from tests.fixtures.mcp.asgi_401 import Auth401Wrapper
from tests.fixtures.mcp.hello_server import make_http_app
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import Encryptor
from the_one.mcp import _era, _pool
from the_one.mcp.transports import streamable_http

URL = "http://localhost/mcp"
SID = "src-neg"


class Reject400InitializeWrapper:
    """Answers ``initialize`` with HTTP 400 (a server that speaks only 2026-07-28);
    everything else passes through."""

    def __init__(self, app) -> None:
        self.app = app
        self.seen: list[str | None] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        try:
            method = json.loads(body).get("method")
        except (ValueError, AttributeError):
            method = None
        self.seen.append(method)
        if method == "initialize":
            payload = b'{"error": "unsupported"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 400,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(payload)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})
            return None
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


@pytest.fixture(autouse=True)
async def _clear_pool():
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture
async def client_and_repo(tmp_path):
    conn = await connect_template_db(tmp_path / "neg.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    await repo.create(
        MCPSource(id=SID, name="neg", type="streamable-http", config={"url": URL, "headers": {}})
    )
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = shared_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            yield c, repo
    await conn.close()


class _httpx2_proxy:  # noqa: N801 - a module stand-in
    """``api.httpx2`` with only ``AsyncClient`` replaced. Patching the real
    module's attribute would change the class identity the transport's
    ``isinstance`` check on its test client relies on."""

    def __init__(self, client_cls) -> None:
        self.AsyncClient = client_cls

    def __getattr__(self, name):
        return getattr(httpx2, name)


def _probe(verdict):
    async def _stub(server_url, *, request_headers=None, timeout=5.0):
        return verdict

    return patch("the_one.mcp.transports.streamable_http._probe_auth_posture", _stub)


# --- AC2 (a): fall-through connects on 2026-07-28 ------------------------------


async def test_unexpected_status_falls_through_and_connects_modern(
    client_and_repo, monkeypatch
) -> None:
    c, repo = client_and_repo
    wrapper = Reject400InitializeWrapper(make_http_app())
    async with serve_asgi(monkeypatch, wrapper):
        with _probe("unexpected_status"):
            resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    body = resp.json()
    assert body["status"] == "ok", body
    assert "server/discover" in wrapper.seen
    assert "initialize" not in wrapper.seen
    assert _era.era_for(SID) == "2026-07-28"
    cache = (await repo.get(SID)).config["_cache"]
    assert cache["protocol_version"] == "2026-07-28"
    assert cache["auth_posture"] == "no_auth"


# --- AC2 (b): fall-through that needs sign-in ends in Phase B -------------------


async def test_unexpected_status_then_401_signs_in_via_discover(
    client_and_repo, monkeypatch
) -> None:
    c, repo = client_and_repo
    # A server that needs sign-in (401 + WWW-Authenticate on every MCP POST) while
    # the probe, patched, reported an unclassifiable status.
    wrapper = Auth401Wrapper(make_http_app(), fail_methods={"server/discover", "initialize"})
    captured: dict = {}

    real_client = httpx2.AsyncClient

    class _StubHttpxClient(real_client):
        """The real client (the SDK path shares ``httpx2.AsyncClient``), except
        that the Phase B driver's ``post`` (the only caller passing ``auth=``
        with a 30s timeout) is captured instead of sent."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._is_driver = kwargs.get("auth") is not None and kwargs.get("timeout") == 30.0
            if self._is_driver:
                captured["auth"] = kwargs["auth"]

        async def post(self, url, **kwargs):
            if not self._is_driver:
                return await super().post(url, **kwargs)
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")
            await captured["auth"].context.redirect_handler(
                "https://example.com/auth?state=neg-state-1&client_id=x"
                "&code_challenge=abc&code_challenge_method=S256"
            )

            class _Resp:
                status_code = 200

            return _Resp()

    async with serve_asgi(monkeypatch, wrapper):
        with (
            _probe("unexpected_status"),
            patch("the_one.interfaces.web.api.httpx2", _httpx2_proxy(_StubHttpxClient)),
        ):
            resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    body = resp.json()
    assert body["status"] == "auth_required", body
    assert "state=neg-state-1" in body["consent_url"]
    assert (await repo.get(SID)).config["_cache"]["auth_posture"] == "oauth"
    # DD10 amendment: sign-in triggered with server/discover + the modern header.
    assert captured["json"]["method"] == "server/discover"
    assert captured["headers"] == {
        "MCP-Protocol-Version": "2026-07-28",
        "Accept": "application/json, text/event-stream",
    }


async def test_normal_phase_b_driver_sends_initialize_with_handshake_header(
    client_and_repo, monkeypatch
) -> None:
    """DD10: outside the fall-through, Phase B posts `initialize` + the handshake
    header, and reads the constant at call time."""
    c, _repo = client_and_repo
    monkeypatch.setattr("the_one.mcp._HANDSHAKE_OFFER_VERSION", "9999-01-01")
    captured: dict = {}

    class _StubHttpxClient:
        def __init__(self, *, auth=None, timeout=None, **kwargs):
            captured["auth"] = auth

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")
            await captured["auth"].context.redirect_handler(
                "https://example.com/auth?state=neg-state-2&client_id=x"
                "&code_challenge=abc&code_challenge_method=S256"
            )

            class _Resp:
                status_code = 200

            return _Resp()

    with (
        _probe("oauth"),
        patch("the_one.interfaces.web.api.httpx2.AsyncClient", _StubHttpxClient),
    ):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json()["status"] == "auth_required"
    assert captured["json"]["method"] == "initialize"
    assert captured["json"]["params"]["protocolVersion"] == "9999-01-01"
    assert captured["headers"]["MCP-Protocol-Version"] == "9999-01-01"


# --- AC2 (c): an unreachable URL fails fast, without the SDK --------------------


async def test_unreachable_url_fails_fast_without_constructing_a_client(
    client_and_repo, monkeypatch
) -> None:
    c, repo = client_and_repo
    src = await repo.get(SID)
    await repo.update(
        src.model_copy(update={"config": {"url": "http://127.0.0.1:1/mcp", "headers": {}}})
    )
    constructed: list[int] = []
    # On hosts where nothing answers on 127.0.0.1:1 the probe only ends by its timeout;
    # shrink it (production: 5 s) so the timeout branch is still what ends the probe.
    monkeypatch.setattr(streamable_http, "_PROBE_TIMEOUT_SECONDS", 0.3)

    class _NoClient:
        def __init__(self, *a, **k):
            constructed.append(1)

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    with patch("the_one.mcp.client.MCPClient", _NoClient):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json() == {"status": "error", "error": "connection probe failed"}
    assert loop.time() - t0 < 6
    assert constructed == []


# --- AC4: era cleared on update / delete / reset --------------------------------


async def test_update_clears_era(client_and_repo) -> None:
    c, _repo = client_and_repo
    _era.remember_era(SID, "2026-07-28")
    resp = await c.put(
        f"/api/mcp-sources/{SID}",
        json={"name": "neg", "type": "streamable-http", "config": {"url": URL, "headers": {}}},
    )
    assert resp.status_code == 200, resp.text
    assert _era.era_for(SID) is None


async def test_failed_update_keeps_era(client_and_repo) -> None:
    c, _repo = client_and_repo
    _era.remember_era(SID, "2026-07-28")
    resp = await c.put(
        f"/api/mcp-sources/{SID}",
        json={"name": "", "type": "no-such-type", "config": {}},
    )
    assert resp.status_code >= 400
    assert _era.era_for(SID) == "2026-07-28"


async def test_delete_clears_era(client_and_repo) -> None:
    c, _repo = client_and_repo
    _era.remember_era(SID, "2026-07-28")
    resp = await c.delete(f"/api/mcp-sources/{SID}")
    assert resp.status_code == 200, resp.text
    assert _era.era_for(SID) is None


async def test_reset_connection_clears_era(client_and_repo) -> None:
    c, _repo = client_and_repo
    _era.remember_era(SID, "2026-07-28")
    resp = await c.delete(f"/api/mcp-sources/{SID}/connection")
    assert resp.status_code == 200, resp.text
    assert _era.era_for(SID) is None


# --- AC5: an override Test does not record the era ------------------------------


async def test_plain_test_records_era_but_override_test_does_not(
    client_and_repo, monkeypatch
) -> None:
    c, _repo = client_and_repo
    async with serve_asgi(monkeypatch, make_http_app()):
        with _probe("no_auth"):
            # The editor sends its (unchanged) form body on every Test: not an override.
            resp = await c.post(
                f"/api/mcp-sources/{SID}/test/connect",
                json={"type": "streamable-http", "config": {"url": URL, "headers": {}}},
            )
            assert resp.json()["status"] == "ok", resp.json()
            assert _era.era_for(SID) == "2026-07-28"

            _era.forget_era(SID)
            # A different server under test (another header set): override applied.
            resp = await c.post(
                f"/api/mcp-sources/{SID}/test/connect",
                json={
                    "type": "streamable-http",
                    "config": {"url": URL, "headers": {"X-Other": "1"}},
                },
            )
            assert resp.json()["status"] == "ok", resp.json()
    assert _era.era_for(SID) is None


async def test_stdio_helper_receives_record_era_gate(client_and_repo) -> None:
    """AC5: the stdio helper gets ``record_era=False`` only when the Test's body
    changes the type or config (secrets alone do not count)."""
    c, repo = client_and_repo
    stdio_cfg = {"command": "echo", "args": []}
    src = await repo.get(SID)
    await repo.update(src.model_copy(update={"type": "stdio", "config": dict(stdio_cfg)}))
    seen: list[bool] = []

    async def _fake(source, source_id, repo_, *, record_era=True):
        seen.append(record_era)
        return {"status": "ok", "tools": [], "capabilities": {}}

    with patch("the_one.interfaces.web.api._build_and_test_stdio_mcp", _fake):
        await c.post(f"/api/mcp-sources/{SID}/test/connect", json={"config": dict(stdio_cfg)})
        await c.post(
            f"/api/mcp-sources/{SID}/test/connect",
            json={"config": dict(stdio_cfg), "secrets": {"K": "v"}},
        )
        await c.post(
            f"/api/mcp-sources/{SID}/test/connect",
            json={"config": {"command": "other", "args": []}},
        )
    assert seen == [True, True, False]


# --- Sortie 04 DD4: a rejected operator key is "credentials rejected" -----------

_KEY_HEADERS = {"Authorization": "Bearer revoked-key"}


async def _give_headers(repo, secrets: dict | None = None, config_extra: dict | None = None):
    src = await repo.get(SID)
    config = {**src.config, "headers": dict(_KEY_HEADERS), **(config_extra or {})}
    await repo.update(
        src.model_copy(update={"config": config, "secrets": {**src.secrets, **(secrets or {})}})
    )


def _expected_envelope(name: str = "neg") -> str:
    from the_one.mcp.errors import MCPCredentialsRejected

    return f"MCPCredentialsRejected: {MCPCredentialsRejected(SID, name)}"


async def test_path_a_cached_no_auth_rejected_key_reports_rejection_and_keeps_posture(
    client_and_repo, monkeypatch
) -> None:
    c, repo = client_and_repo
    await _give_headers(repo, config_extra={"_cache": {"auth_posture": "no_auth"}})
    wrapper = Auth401Wrapper(
        make_http_app(), fail_methods={"server/discover", "initialize"}, resource_metadata=None
    )
    async with serve_asgi(monkeypatch, wrapper):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    body = resp.json()
    assert body == {"status": "error", "error": _expected_envelope()}, body
    assert (await repo.get(SID)).config["_cache"]["auth_posture"] == "no_auth"


async def test_path_b_fallthrough_rejection_defers_to_phase_b(client_and_repo, monkeypatch) -> None:
    """DD9 fall-through: the typed rejection is treated like a sign-in signal, so
    Phase B decides. Phase B's own discovery is a bare 401 too, so it ends in the
    path (c) rejection envelope."""
    c, repo = client_and_repo
    await _give_headers(repo)
    wrapper = Auth401Wrapper(
        make_http_app(), fail_methods={"server/discover", "initialize"}, resource_metadata=None
    )
    handler = _all_401_handler()
    async with serve_asgi(monkeypatch, wrapper):
        with (
            _probe("unexpected_status"),
            patch("the_one.interfaces.web.api.httpx2", _httpx2_proxy(_mock_driver_client(handler))),
        ):
            resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json() == {"status": "error", "error": _expected_envelope()}, resp.json()
    # Path (c) removed the posture the fall-through had persisted.
    assert "auth_posture" not in ((await repo.get(SID)).config.get("_cache") or {})


def _all_401_handler(prm=None, calls=None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if calls is not None:
            calls.append((request.method, request.url.path))
        if prm is not None and request.url.path.startswith("/.well-known/oauth-protected"):
            return prm
        return httpx2.Response(401)

    return handler


def _mock_driver_client(handler):
    real_client = httpx2.AsyncClient

    def factory(*args, **kwargs):
        if kwargs.get("auth") is not None and kwargs.get("timeout") == 30.0:
            return real_client(*args, transport=httpx2.MockTransport(handler), **kwargs)
        return real_client(*args, **kwargs)

    return factory


async def _phase_b(c, handler, *, verdict="oauth"):
    with (
        _probe(verdict),
        patch("the_one.interfaces.web.api.httpx2", _httpx2_proxy(_mock_driver_client(handler))),
    ):
        return (await c.post(f"/api/mcp-sources/{SID}/test/connect")).json()


async def test_path_c_probe_oauth_bare_401_everywhere_reports_rejection(client_and_repo) -> None:
    c, repo = client_and_repo
    await _give_headers(repo)
    body = await _phase_b(c, _all_401_handler())
    # The envelope text is exactly the typed error's own message.
    assert body == {"status": "error", "error": _expected_envelope()}, body
    assert "auth_posture" not in ((await repo.get(SID)).config.get("_cache") or {})


async def test_path_c_no_operator_headers_stays_auth_flow_error(client_and_repo) -> None:
    c, repo = client_and_repo
    body = await _phase_b(c, _all_401_handler())
    assert body["status"] == "error"
    assert body["error"].startswith("auth_flow_error:"), body
    assert (await repo.get(SID)).config["_cache"]["auth_posture"] == "oauth"


async def test_path_c_metadata_found_is_not_rejection(client_and_repo) -> None:
    c, repo = client_and_repo
    await _give_headers(repo)
    prm = httpx2.Response(
        200, json={"resource": URL, "authorization_servers": ["http://localhost"]}
    )
    body = await _phase_b(c, _all_401_handler(prm=prm))
    assert not body.get("error", "").startswith("MCPCredentialsRejected"), body
    assert (await repo.get(SID)).config["_cache"]["auth_posture"] == "oauth"


async def test_path_c_prm_5xx_is_not_rejection(client_and_repo) -> None:
    c, repo = client_and_repo
    await _give_headers(repo)
    body = await _phase_b(c, _all_401_handler(prm=httpx2.Response(500)))
    assert not body.get("error", "").startswith("MCPCredentialsRejected"), body
    assert (await repo.get(SID)).config["_cache"]["auth_posture"] == "oauth"


async def test_path_c_transport_error_is_not_rejection(client_and_repo) -> None:
    c, repo = client_and_repo
    await _give_headers(repo)

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("boom", request=request)

    body = await _phase_b(c, handler)
    assert body["status"] == "error"
    assert body["error"].startswith("auth_flow_error:"), body
    assert (await repo.get(SID)).config["_cache"]["auth_posture"] == "oauth"


async def test_path_c_not_applied_when_phase_b_entered_from_stale_token_fallthrough(
    client_and_repo,
) -> None:
    """Phase A's stale-token fall-through sent no operator-header evidence this
    request, so Phase B's failed /register is NOT a rejection."""
    c, repo = client_and_repo
    await _give_headers(
        repo, secrets={"dcr_credentials": {"client_id": "cid"}, "access_token": "stale"}
    )
    from the_one.mcp.errors import MCPAuthRequired

    class _StaleClient:
        def __init__(self, *, source, auth_provider=None, **kwargs):
            self._source = source

        async def __aenter__(self):
            raise MCPAuthRequired(source_id=self._source.id)

        async def __aexit__(self, *args):
            pass

    with patch("the_one.mcp.client.MCPClient", _StaleClient):
        body = await _phase_b(c, _all_401_handler(), verdict="oauth")
    assert not body.get("error", "").startswith("MCPCredentialsRejected"), body


async def test_self_configuration_loopback_401_reads_rejected_and_stays_no_auth(
    client_and_repo, monkeypatch
) -> None:
    """AC8: the loopback source carries ``secrets["Authorization"]`` (its minted
    credential) and is cached ``no_auth``; a 401 from it is a rejection, not a login."""
    c, repo = client_and_repo
    src = await repo.get(SID)
    await repo.update(
        src.model_copy(
            update={
                "config": {
                    **src.config,
                    "self_configuration": {"agent": "someone"},
                    "_cache": {"auth_posture": "no_auth"},
                },
                "secrets": {"Authorization": "Bearer minted-credential"},
            }
        )
    )
    wrapper = Auth401Wrapper(
        make_http_app(), fail_methods={"server/discover", "initialize"}, resource_metadata=None
    )
    async with serve_asgi(monkeypatch, wrapper):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json() == {"status": "error", "error": _expected_envelope()}
    assert (await repo.get(SID)).config["_cache"]["auth_posture"] == "no_auth"

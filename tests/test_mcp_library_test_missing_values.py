"""Sortie 09 leg 1: the Library Test of a source with a "Set per agent" (blank) header
(DD3), and the ``cache_write`` / ``classify`` switches on the two Test helpers (DD6).

Real fixtures where it matters: the hello server behind ``Auth401Wrapper`` (a bare 401 or a
401 carrying ``resource_metadata``), reached through the transport's test seam.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

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
from the_one.interfaces.web import api as api_mod
from the_one.mcp import _era, _pool

URL = "http://localhost/mcp"
SID = "src-missing"
SECRET = "distinctive-secret-value-55555"
ALL_401 = {"initialize", "server/discover", "tools/list", "notifications/initialized"}


@pytest.fixture(autouse=True)
async def _clear_pool():
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()
    _era.forget_era(SID)


@pytest.fixture
async def client_and_repo(tmp_path):
    conn = await connect_template_db(tmp_path / "m.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "m.key")
    repo = MCPSourceRepository(conn, encryptor)
    await repo.create(
        MCPSource(
            id=SID,
            name="keyed",
            type="streamable-http",
            config={"url": URL, "headers": {"X-Api-Key": ""}},
        )
    )
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            yield c, repo
    await conn.close()


def _probe_must_not_run():
    async def _stub(server_url, *, request_headers=None, timeout=5.0):  # pragma: no cover
        raise AssertionError("Phase 0 probe must be skipped on the missing-values path")

    return patch("the_one.mcp.transports.streamable_http._probe_auth_posture", _stub)


def _cache(src):
    return src.config.get("_cache") or {}


# --- the Library Test route --------------------------------------------------------


async def test_bare_401_names_the_missing_value_and_runs_no_registration(
    client_and_repo, monkeypatch, caplog
):
    c, repo = client_and_repo
    wrapper = Auth401Wrapper(make_http_app(), fail_methods=ALL_401, resource_metadata=None)
    caplog.set_level(logging.DEBUG)
    async with serve_asgi(monkeypatch, wrapper):
        with _probe_must_not_run():
            resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    body = resp.json()
    assert body["status"] == "error", body
    assert body["error"].startswith("MCPCredentialsRejected: ")
    assert "needs a value for X-Api-Key" in body["error"]
    # no client registration or well-known discovery was attempted (the wrapper logs 401s on
    # /register and /.well-known paths)
    assert not any(p.startswith(("/register", "/.well-known")) for p, _ in wrapper.seen if p)
    stored = await repo.get(SID)
    assert "auth_posture" not in _cache(stored)
    assert _cache(stored)["last_check"]["status"] == "error"  # a body-less Test records it
    assert SECRET not in body["error"] + caplog.text


async def test_cached_no_auth_posture_still_takes_the_branch_and_keeps_its_posture(
    client_and_repo, monkeypatch
):
    c, repo = client_and_repo
    src = await repo.get(SID)
    await repo.update(
        src.model_copy(update={"config": {**src.config, "_cache": {"auth_posture": "no_auth"}}})
    )
    wrapper = Auth401Wrapper(make_http_app(), fail_methods=ALL_401, resource_metadata=None)
    async with serve_asgi(monkeypatch, wrapper):
        body = (await c.post(f"/api/mcp-sources/{SID}/test/connect")).json()
    assert body["status"] == "error" and "needs a value for X-Api-Key" in body["error"]
    assert _cache(await repo.get(SID))["auth_posture"] == "no_auth"

    # A 401 that names a sign-in goes on to Phase B even though the cached posture is
    # no_auth (the plain early return would have reported a defensive MCPAuthRequired error).
    wrapper = Auth401Wrapper(make_http_app(), fail_methods={"server/discover", "initialize"})
    async with serve_asgi(monkeypatch, wrapper):
        body = (await c.post(f"/api/mcp-sources/{SID}/test/connect")).json()
    assert body["status"] == "error"
    assert body["error"].startswith("auth_flow_error:"), body  # Phase B ran (no driver stub)
    assert _cache(await repo.get(SID))["auth_posture"] == "no_auth"


async def test_a_server_that_does_not_need_the_value_succeeds_without_writing_posture(
    client_and_repo, monkeypatch
):
    c, repo = client_and_repo
    async with serve_asgi(monkeypatch, make_http_app()):
        with _probe_must_not_run():
            body = (await c.post(f"/api/mcp-sources/{SID}/test/connect")).json()
    assert body["status"] == "ok", body
    cache = _cache(await repo.get(SID))
    assert {t["name"] for t in cache["tools"]} == {"echo", "add"}
    assert "auth_posture" not in cache


async def test_oauth_server_with_a_blank_header_can_still_sign_in_through_phase_b(
    client_and_repo, monkeypatch
):
    """A 401 that carries `resource_metadata` is a sign-in prompt, not a rejection:
    the Test enters Phase B, writes NO posture and sets no rejection evidence."""
    c, repo = client_and_repo
    wrapper = Auth401Wrapper(make_http_app(), fail_methods={"server/discover", "initialize"})
    captured: dict = {}
    real_client = httpx2.AsyncClient

    class _Driver(real_client):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._is_driver = kwargs.get("auth") is not None and kwargs.get("timeout") == 30.0
            if self._is_driver:
                captured["auth"] = kwargs["auth"]

        async def post(self, url, **kwargs):
            if not self._is_driver:
                return await super().post(url, **kwargs)
            captured["json"] = kwargs.get("json")
            await captured["auth"].context.redirect_handler(
                "https://example.com/auth?state=miss-state-1&client_id=x"
                "&code_challenge=abc&code_challenge_method=S256"
            )

            class _Resp:
                status_code = 200

            return _Resp()

    class _Proxy:
        AsyncClient = _Driver

        def __getattr__(self, name):
            return getattr(httpx2, name)

    async with serve_asgi(monkeypatch, wrapper):
        with _probe_must_not_run(), patch.object(api_mod, "httpx2", _Proxy()):
            body = (await c.post(f"/api/mcp-sources/{SID}/test/connect")).json()
    assert body["status"] == "auth_required", body
    assert "state=miss-state-1" in body["consent_url"]
    assert captured["json"]["method"] == "server/discover"  # entered via the fall-through
    assert "auth_posture" not in _cache(await repo.get(SID))


async def test_live_tokens_keep_phase_a(client_and_repo):
    c, repo = client_and_repo
    src = await repo.get(SID)
    src.secrets.update({"dcr_credentials": {"client_id": "c1"}, "access_token": "tok"})
    await repo.update(src)
    constructed: list[bool] = []

    class _Client:
        def __init__(self, *, source, auth_provider=None, **kw):
            constructed.append(auth_provider is not None)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def list_tools(self):
            return []

        server_capabilities = {}
        server_info = None
        instructions = None
        meta = None
        negotiated_protocol_version = "2025-06-18"

    async def no_helper(*a, **k):  # pragma: no cover
        raise AssertionError("the no-auth helper must not run when live tokens exist")

    with (
        patch("the_one.mcp.client.MCPClient", _Client),
        patch.object(api_mod, "_build_and_test_no_auth_mcp", no_helper),
    ):
        body = (await c.post(f"/api/mcp-sources/{SID}/test/connect")).json()
    assert body["status"] == "ok"
    assert constructed == [True]


async def test_a_stdio_source_with_a_blank_env_value_takes_no_special_path(client_and_repo):
    c, repo = client_and_repo
    src = await repo.get(SID)
    await repo.update(
        src.model_copy(
            update={"type": "stdio", "config": {"command": "echo", "args": [], "env": {"K": ""}}}
        )
    )
    seen: list = []

    async def fake_stdio(source, source_id, repo_, *, record_era=True, cache_write="shared"):
        seen.append(cache_write)
        return {"status": "ok", "tools": [], "capabilities": {}}

    async def no_helper(*a, **k):  # pragma: no cover
        raise AssertionError("not for stdio")

    with (
        patch.object(api_mod, "_build_and_test_stdio_mcp", fake_stdio),
        patch.object(api_mod, "_build_and_test_no_auth_mcp", no_helper),
    ):
        body = (await c.post(f"/api/mcp-sources/{SID}/test/connect")).json()
    assert body["status"] == "ok"
    assert seen == ["shared"]


# --- DD6 switches on the two helpers -----------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expect_tools", "expect_posture"),
    [("shared", True, "no_auth"), ("shared_no_posture", True, None), ("none", False, None)],
)
async def test_no_auth_helper_cache_write_modes(
    client_and_repo, monkeypatch, mode, expect_tools, expect_posture
):
    _, repo = client_and_repo
    src = await repo.get(SID)
    async with serve_asgi(monkeypatch, make_http_app()):
        result = await api_mod._build_and_test_no_auth_mcp(src, SID, repo, cache_write=mode)
    assert result["status"] == "ok"
    cache = _cache(await repo.get(SID))
    assert ("tools" in cache) is expect_tools
    assert cache.get("auth_posture") == expect_posture
    if expect_tools:
        assert {"capabilities", "last_updated", "protocol_version"} <= set(cache)


def _fake_stdio_client(record):
    class _Client:
        def __init__(self, *, source, auth_provider=None, **kw):
            record.append(kw.get("record_era"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def list_tools(self):
            return []

        server_capabilities = {"tools": {}}
        server_info = None
        instructions = None
        meta = None
        negotiated_protocol_version = "2025-06-18"

    return _Client


@pytest.mark.parametrize(
    ("mode", "writes"), [("shared", True), ("shared_no_posture", True), ("none", False)]
)
async def test_stdio_helper_cache_write_modes(client_and_repo, mode, writes):
    _, repo = client_and_repo
    src = await repo.get(SID)
    src = src.model_copy(update={"type": "stdio", "config": {"command": "echo", "args": []}})
    await repo.update(src)
    with patch("the_one.mcp.client.MCPClient", _fake_stdio_client([])):
        result = await api_mod._build_and_test_stdio_mcp(src, SID, repo, cache_write=mode)
    assert result["status"] == "ok"
    cache = _cache(await repo.get(SID))
    assert ("capabilities" in cache) is writes
    assert "auth_posture" not in cache  # stdio never writes a posture


async def test_existing_call_style_without_cache_write_still_writes_the_shared_fields(
    client_and_repo, monkeypatch
):
    _, repo = client_and_repo
    src = await repo.get(SID)
    async with serve_asgi(monkeypatch, make_http_app()):
        await api_mod._build_and_test_no_auth_mcp(src, SID, repo)
    assert _cache(await repo.get(SID))["auth_posture"] == "no_auth"


@pytest.mark.parametrize(
    ("resource_metadata", "classify", "expected"),
    [
        (None, True, "error"),  # a bare 401 is a plain rejection
        (None, False, "signin"),  # the old fold, unchanged
        ("https://example.test/prm", True, "signin"),  # a 401 naming a sign-in
        ("https://example.test/prm", False, "signin"),
    ],
)
async def test_no_auth_helper_classify(
    client_and_repo, monkeypatch, resource_metadata, classify, expected
):
    _, repo = client_and_repo
    src = await repo.get(SID)
    wrapper = Auth401Wrapper(
        make_http_app(), fail_methods=ALL_401, resource_metadata=resource_metadata
    )
    async with serve_asgi(monkeypatch, wrapper):
        result = await api_mod._build_and_test_no_auth_mcp(
            src, SID, repo, from_fallthrough=True, classify=classify, cache_write="none"
        )
    if expected == "signin":
        assert result is api_mod._SIGNIN_REQUIRED
    else:
        assert result["status"] == "error"
        assert result["error"].startswith("MCPCredentialsRejected: ")
        assert "needs a value for X-Api-Key" in result["error"]


# --- AC14: a rejected connection with a configured value never echoes it -----------


async def test_rejected_connection_error_text_carries_names_only(
    client_and_repo, monkeypatch, caplog
):
    c, repo = client_and_repo
    src = await repo.get(SID)
    await repo.update(
        src.model_copy(
            update={
                # the secret goes in `secrets` (encrypted at rest); config is plaintext by design
                "config": {**src.config, "headers": {"X-Api-Key": "", "X-Blank": ""}},
                "secrets": {"X-Api-Key": SECRET},
            }
        )
    )
    wrapper = Auth401Wrapper(make_http_app(), fail_methods=ALL_401, resource_metadata=None)
    caplog.set_level(logging.DEBUG)
    async with serve_asgi(monkeypatch, wrapper):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert SECRET not in resp.text and SECRET not in caplog.text
    assert "needs a value for X-Blank" in resp.json()["error"]
    assert MagicMock  # keep the import used

"""Leg 08a — ``_cache.last_check``: the server's record of the last Studio connection check.

Covers ``MCPSourceRepository.merge_cache`` and the ``test/connect`` wrapper that records
``{status, at}`` for a body-less Test of the saved server, without losing any other
``_cache`` key and without bumping ``updated_at``.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import Encryptor
from the_one.interfaces.web import api as api_mod
from the_one.mcp import _pool

SID = "src-last-check"
SECRET_TOKEN = "tok-SECRET-VALUE-123"
SECRET_HEADER = "hdr-SECRET-VALUE-456"

FULL_CACHE = {
    "tools": [{"name": "old", "description": "d", "input_schema": {}}],
    "capabilities": {"tools": {}},
    "server_info": {"name": "srv"},
    "instructions": "hi",
    "meta": {"k": 1},
    "protocol_version": "2025-06-18",
    "last_updated": 111.0,
    "auth_posture": "oauth",
}


@pytest.fixture(autouse=True)
async def _clear_pool():
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture
async def client_and_repo(tmp_path):
    conn = await connect_template_db(tmp_path / "last-check.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
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


async def _seed(repo, *, stdio=True, cache=None, secrets=None):
    cfg: dict = {"command": "python", "args": []} if stdio else {"url": "https://x.example/mcp"}
    if cache is not None:
        cfg["_cache"] = dict(cache)
    await repo.create(
        MCPSource(
            id=SID,
            name="S",
            type="stdio" if stdio else "streamable-http",
            config=cfg,
            secrets=secrets or {},
        )
    )


def _ok_client():
    tool = MagicMock()
    tool.name = "echo"
    tool.description = "Echo"
    tool.input_schema = {"type": "object"}

    class _C:
        def __init__(self, *, source, auth_provider=None, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def list_tools(self):
            return [tool]

        server_capabilities = {"tools": {}}
        server_info = None
        instructions = None
        meta = None
        negotiated_protocol_version = "2025-06-18"

    return _C


def _err_client():
    from the_one.mcp.errors import MCPConnectionError

    class _C:
        def __init__(self, *, source, auth_provider=None, **kw):
            pass

        async def __aenter__(self):
            raise MCPConnectionError("boom")

        async def __aexit__(self, *a):
            return None

    return _C


def _stub_inner(monkeypatch, result, recordable_hint=None):
    """Replace the connection logic so the wrapper's recording is tested on its own."""

    async def _inner(source_id, request):
        return dict(result), (not await request.body()) if recordable_hint is None else (
            recordable_hint
        )

    monkeypatch.setattr(api_mod, "_test_mcp_connection_inner", _inner, raising=False)


# ── merge_cache ──────────────────────────────────────────────────────────


async def test_merge_cache_merges_keeps_updated_at_and_stores_none(client_and_repo) -> None:
    _c, repo = client_and_repo
    await _seed(repo, cache=FULL_CACHE)
    before = await repo.get(SID)
    await repo.merge_cache(SID, {"last_check": {"status": "ok", "at": 5.0}, "instructions": None})
    after = await repo.get(SID)
    cache = after.config["_cache"]
    assert cache["last_check"] == {"status": "ok", "at": 5.0}
    # None is stored as null, never a delete.
    assert "instructions" in cache and cache["instructions"] is None
    for k in ("tools", "capabilities", "server_info", "meta", "protocol_version", "auth_posture"):
        assert cache[k] == FULL_CACHE[k]
    assert after.updated_at == before.updated_at
    assert after.config["command"] == "python"


async def test_merge_cache_delete_and_missing(client_and_repo) -> None:
    _c, repo = client_and_repo
    await _seed(repo, cache=FULL_CACHE)
    await repo.merge_cache(SID, {}, delete=("auth_posture", "absent"))
    cache = (await repo.get(SID)).config["_cache"]
    assert "auth_posture" not in cache and "tools" in cache
    with pytest.raises(KeyError):
        await repo.merge_cache("nope", {"a": 1})


async def test_merge_cache_creates_cache_when_absent(client_and_repo) -> None:
    _c, repo = client_and_repo
    await _seed(repo)
    await repo.merge_cache(SID, {"last_check": {"status": "error", "at": 1.0}})
    assert (await repo.get(SID)).config["_cache"] == {"last_check": {"status": "error", "at": 1.0}}


# ── the route records ────────────────────────────────────────────────────


async def test_ok_stdio_test_records_ok_and_keeps_posture(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo, cache=FULL_CACHE)
    before = await repo.get(SID)
    t0 = time.time()
    with patch("the_one.mcp.client.MCPClient", _ok_client()):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json()["status"] == "ok"
    after = await repo.get(SID)
    cache = after.config["_cache"]
    assert cache["last_check"]["status"] == "ok"
    assert t0 <= cache["last_check"]["at"] <= time.time()
    assert cache["auth_posture"] == "oauth"  # survives the ok write
    assert [t["name"] for t in cache["tools"]] == ["echo"]
    assert cache["last_updated"] > 111.0
    assert after.updated_at == before.updated_at


async def test_error_test_records_error_and_keeps_every_key(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo, cache=FULL_CACHE)
    before = await repo.get(SID)
    with patch("the_one.mcp.client.MCPClient", _err_client()):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json()["status"] == "error"
    after = await repo.get(SID)
    cache = after.config["_cache"]
    assert cache["last_check"]["status"] == "error"
    for k, v in FULL_CACHE.items():
        assert cache[k] == v
    assert after.updated_at == before.updated_at
    # No secret/header value or error text in the record.
    assert set(cache["last_check"]) == {"status", "at"}


async def test_auth_required_is_recorded(client_and_repo, monkeypatch) -> None:
    c, repo = client_and_repo
    await _seed(repo, stdio=False, cache=FULL_CACHE)
    _stub_inner(monkeypatch, {"status": "auth_required", "consent_url": "https://a/b"})
    resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json() == {"status": "auth_required", "consent_url": "https://a/b"}
    cache = (await repo.get(SID)).config["_cache"]
    assert cache["last_check"]["status"] == "auth_required"
    assert cache["tools"] == FULL_CACHE["tools"]


async def test_unknown_status_is_not_recorded(client_and_repo, monkeypatch) -> None:
    c, repo = client_and_repo
    await _seed(repo)
    _stub_inner(monkeypatch, {"status": "weird"})
    await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert (await repo.get(SID)).config.get("_cache") is None


async def test_body_ful_test_is_not_recorded_even_when_clean(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo)
    body = {"type": "stdio", "config": {"command": "python", "args": []}, "secrets": {}}
    with patch("the_one.mcp.client.MCPClient", _err_client()):
        r1 = await c.post(f"/api/mcp-sources/{SID}/test/connect", json=body)
    assert r1.json()["status"] == "error"
    with patch("the_one.mcp.client.MCPClient", _ok_client()):
        # Dirty body (different args): result is ok but not the saved server.
        body["config"]["args"] = ["-x"]
        r2 = await c.post(f"/api/mcp-sources/{SID}/test/connect", json=body)
    assert r2.json()["status"] == "ok"
    cache = (await repo.get(SID)).config.get("_cache") or {}
    assert "last_check" not in cache


async def test_secrets_only_body_records_era_but_not_last_check(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo)
    body = {"secrets": {"X": "v"}}
    with patch("the_one.mcp.client.MCPClient", _ok_client()):
        r = await c.post(f"/api/mcp-sources/{SID}/test/connect", json=body)
    assert r.json()["status"] == "ok"
    cache = (await repo.get(SID)).config["_cache"]
    assert "last_check" not in cache  # recordable (no body) != record_era (config same)
    assert [t["name"] for t in cache["tools"]] == ["echo"]


async def test_404_invalid_json_and_non_object_body_not_recorded(
    client_and_repo,
) -> None:
    c, repo = client_and_repo
    assert (await c.post("/api/mcp-sources/nope/test/connect")).status_code == 404
    await _seed(repo)
    r = await c.post(
        f"/api/mcp-sources/{SID}/test/connect",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert r.json()["status"] == "error"
    r = await c.post(f"/api/mcp-sources/{SID}/test/connect", json=[1, 2])
    assert r.json()["status"] == "error"
    assert (await repo.get(SID)).config.get("_cache") is None


async def test_recording_failure_is_swallowed(client_and_repo, monkeypatch) -> None:
    c, repo = client_and_repo
    await _seed(repo)

    async def _boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(MCPSourceRepository, "merge_cache", _boom)
    _stub_inner(monkeypatch, {"status": "error", "error": "x"})
    resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.status_code == 200 and resp.json()["status"] == "error"


async def test_no_secret_lands_in_last_check_or_response(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(
        repo,
        stdio=False,
        secrets={"access_token": SECRET_TOKEN, "Authorization": SECRET_HEADER},
    )
    with patch("the_one.mcp.client.MCPClient", _err_client()):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    stored = await repo.get(SID)
    blob = json.dumps(stored.config) + resp.text
    assert SECRET_TOKEN not in blob and SECRET_HEADER not in blob


# ── survival across a sequence, PUT, Reset ───────────────────────────────


async def test_sequence_keeps_every_key_then_reset_drops_all(client_and_repo, monkeypatch) -> None:
    c, repo = client_and_repo
    await _seed(repo, cache=FULL_CACHE)
    with patch("the_one.mcp.client.MCPClient", _ok_client()):
        await c.post(f"/api/mcp-sources/{SID}/test/connect")
    with patch("the_one.mcp.client.MCPClient", _err_client()):
        await c.post(f"/api/mcp-sources/{SID}/test/connect")
    await api_mod._persist_oauth_posture(repo, SID)
    _stub_inner(monkeypatch, {"status": "auth_required", "consent_url": "u"})
    await c.post(f"/api/mcp-sources/{SID}/test/connect")
    monkeypatch.undo()
    cache = (await repo.get(SID)).config["_cache"]
    for k in (
        "tools",
        "server_info",
        "capabilities",
        "instructions",
        "meta",
        "protocol_version",
        "last_updated",
        "auth_posture",
    ):
        assert k in cache, k
    assert cache["last_check"]["status"] == "auth_required"

    # PUT keeps the whole _cache, last_check included.
    src = await repo.get(SID)
    put = await c.put(
        f"/api/mcp-sources/{SID}",
        json={
            "name": "S",
            "type": "stdio",
            "config": {"command": "python", "args": ["y"]},
            "secrets": {},
        },
    )
    assert put.status_code == 200, put.text
    kept = (await repo.get(SID)).config["_cache"]
    assert kept["last_check"]["status"] == "auth_required"
    assert kept["tools"] == cache["tools"]
    assert src.id == SID

    # Reset drops everything.
    assert (await c.delete(f"/api/mcp-sources/{SID}/connection")).status_code == 200
    assert (await repo.get(SID)).config.get("_cache") is None


async def test_posture_helpers_use_merge_and_keep_other_keys(client_and_repo) -> None:
    _c, repo = client_and_repo
    await _seed(
        repo,
        cache={**FULL_CACHE, "auth_posture": "no_auth", "last_check": {"status": "ok", "at": 1.0}},
    )
    before = await repo.get(SID)
    await api_mod._persist_oauth_posture(repo, SID)
    mid = await repo.get(SID)
    assert mid.config["_cache"]["auth_posture"] == "oauth"
    assert mid.config["_cache"]["last_check"] == {"status": "ok", "at": 1.0}
    await api_mod._clear_auth_posture(repo, SID)
    end = await repo.get(SID)
    assert "auth_posture" not in end.config["_cache"]
    assert end.config["_cache"]["tools"] == FULL_CACHE["tools"]
    assert end.updated_at == before.updated_at


async def test_http_phase_a_ok_records_and_keeps_oauth_posture(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(
        repo,
        stdio=False,
        cache=FULL_CACHE,
        secrets={"dcr_credentials": {"client_id": "cid"}, "access_token": "tok"},
    )
    with patch("the_one.mcp.client.MCPClient", _ok_client()):
        resp = await c.post(f"/api/mcp-sources/{SID}/test/connect")
    assert resp.json()["status"] == "ok"
    cache = (await repo.get(SID)).config["_cache"]
    assert cache["last_check"]["status"] == "ok"
    # Intended behaviour change: the Phase A ok write used to drop auth_posture.
    assert cache["auth_posture"] == "oauth"
    assert [t["name"] for t in cache["tools"]] == ["echo"]


# --- PUT that changes the server's identity drops last_check / auth_posture ---

CACHE_WITH_CHECK = {**FULL_CACHE, "last_check": {"status": "ok", "at": 5.0}}


async def _put(c, body):
    resp = await c.put(f"/api/mcp-sources/{SID}", json=body)
    assert resp.status_code == 200, resp.text
    return resp


async def test_put_url_change_drops_check_and_posture_keeps_tools(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo, stdio=False, cache=CACHE_WITH_CHECK)
    await _put(c, {"config": {"url": "https://other.example/mcp"}})
    cache = (await repo.get(SID)).config["_cache"]
    assert "last_check" not in cache and "auth_posture" not in cache
    assert cache["tools"] == FULL_CACHE["tools"]
    assert cache["last_updated"] == 111.0


async def test_put_type_change_drops_check_and_posture(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo, stdio=False, cache=CACHE_WITH_CHECK)
    await _put(c, {"type": "stdio", "config": {"command": "python", "args": []}})
    cache = (await repo.get(SID)).config["_cache"]
    assert "last_check" not in cache and "auth_posture" not in cache
    assert cache["tools"] == FULL_CACHE["tools"]


async def test_put_name_only_and_headers_only_keep_both(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo, stdio=False, cache=CACHE_WITH_CHECK)
    await _put(c, {"name": "Renamed"})
    await _put(
        c,
        {"config": {"url": "https://x.example/mcp", "headers": {"X-A": "b"}}},
    )
    cache = (await repo.get(SID)).config["_cache"]
    assert cache["last_check"] == {"status": "ok", "at": 5.0}
    assert cache["auth_posture"] == "oauth"


async def test_put_operator_supplied_cache_is_ignored(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(repo, stdio=False, cache=CACHE_WITH_CHECK)
    forged = {"tools": [], "last_check": {"status": "error", "at": 9.0}, "auth_posture": "x"}
    await _put(c, {"config": {"url": "https://x.example/mcp", "_cache": forged}})
    assert (await repo.get(SID)).config["_cache"] == CACHE_WITH_CHECK
    await _put(c, {"config": {"url": "https://y.example/mcp", "_cache": forged}})
    cache = (await repo.get(SID)).config["_cache"]
    assert "last_check" not in cache and cache["tools"] == FULL_CACHE["tools"]


async def test_put_identity_change_with_only_those_keys_leaves_no_cache(client_and_repo) -> None:
    c, repo = client_and_repo
    await _seed(
        repo,
        stdio=False,
        cache={"auth_posture": "oauth", "last_check": {"status": "ok", "at": 1.0}},
    )
    await _put(c, {"config": {"url": "https://z.example/mcp"}})
    assert "_cache" not in (await repo.get(SID)).config

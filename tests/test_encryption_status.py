"""``GET /api/encryption/status`` and the rotate route's ``last_rotated_at`` (M31 F4 L08b, B12).

The status route is read-only: the time the key last rotated, how many items hold a
stored secret (decrypted in-process, one per item) and whether a rotated key is staged
and not yet promoted. No secret material is returned.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.encryption import Encryptor, next_key_path
from the_one.interfaces.web.api import ENCRYPTION_LAST_ROTATED_KEY, router


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    key_path.write_bytes(key)
    encryptor = Encryptor(key, key_path=key_path)
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as client:
            yield SimpleNamespace(
                client=client, conn=conn, encryptor=encryptor, key_path=key_path, tmp=tmp_path
            )
    await conn.close()


async def _status(env) -> dict:
    resp = await env.client.get("/api/encryption/status")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _provider(env, name: str, api_key: str | None = None) -> str:
    body = {"name": name, "type": "openai", "base_url": "https://api.openai.com/v1"}
    if api_key is not None:
        body["api_key"] = api_key
    resp = await env.client.post("/api/providers", json=body)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def test_empty_install(env) -> None:
    assert await _status(env) == {
        "last_rotated_at": None,
        "credential_count": 0,
        "key_file_pending": False,
    }


async def test_route_requires_the_credential(tmp_path, monkeypatch) -> None:
    """Behind the global credential gate: no credential, no status (401) -- the
    handler is never reached, so nothing is read."""
    from the_one import api_credential
    from the_one.config import settings
    from the_one.interfaces.web.middleware import EXEMPT_PATHS, CredentialGateMiddleware

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(api_credential, "_cache", {})
    monkeypatch.setattr(api_credential, "_sources", [api_credential.FileCredentialSource()])
    assert "/api/encryption/status" not in EXEMPT_PATHS
    app = FastAPI()
    app.add_middleware(CredentialGateMiddleware)
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        resp = await anon.get("/api/encryption/status")
    assert resp.status_code == 401


async def test_a_provider_with_a_key_counts_once(env) -> None:
    await _provider(env, "Keyed", "sk-statuscount1234")
    assert (await _status(env))["credential_count"] == 1


async def test_an_environment_key_with_no_key_file_still_counts(env) -> None:
    """Squawk 0258: a key without a key file (``key_path`` None) used to report 0."""
    await _provider(env, "EnvKeyed", "sk-envkeycount1234")
    env_encryptor = Encryptor(env.encryptor._key)
    assert env_encryptor.key_path is None
    with patch("the_one.interfaces.web.api.get_encryptor", return_value=env_encryptor):
        status = await _status(env)
    assert status["credential_count"] == 1
    assert status["key_file_pending"] is False


async def test_a_stored_secret_counts_once_however_many_values(env) -> None:
    resp = await env.client.post(
        "/api/secrets",
        json={
            "name": "Two values",
            "allowed_tools": ["write_file"],
            "values": [{"key": "a", "value": "first-plain"}, {"key": "b", "value": "second-plain"}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert (await _status(env))["credential_count"] == 1


async def test_a_provider_without_a_key_or_secrets_counts_zero(env) -> None:
    pid = await _provider(env, "Plain")
    # Its secrets column holds an encrypted empty object.
    async with env.conn.execute("SELECT secrets FROM llm_providers WHERE id = ?", (pid,)) as cur:
        row = await cur.fetchone()
    assert row["secrets"]
    assert json.loads(env.encryptor.decrypt(row["secrets"])) == {}
    assert (await _status(env))["credential_count"] == 0


async def test_a_provider_with_a_key_and_secrets_is_one_item(env) -> None:
    pid = await _provider(env, "Both", "sk-bothbothboth1234")
    await env.conn.execute(
        "UPDATE llm_providers SET secrets = ? WHERE id = ?",
        (env.encryptor.encrypt(json.dumps({"access_token": "tok"})), pid),
    )
    await env.conn.commit()
    assert (await _status(env))["credential_count"] == 1


async def test_a_secrets_only_provider_counts(env) -> None:
    pid = await _provider(env, "OAuthish")
    await env.conn.execute(
        "UPDATE llm_providers SET secrets = ? WHERE id = ?",
        (env.encryptor.encrypt(json.dumps({"access_token": "tok"})), pid),
    )
    await env.conn.commit()
    assert (await _status(env))["credential_count"] == 1


async def test_an_agent_with_an_empty_encrypted_override_map_counts_zero(env) -> None:
    await env.conn.execute(
        "INSERT INTO agents (name, tool_overrides, mcp_overrides) VALUES (?, ?, ?)",
        ("quiet", env.encryptor.encrypt("{}"), env.encryptor.encrypt("{}")),
    )
    await env.conn.commit()
    assert (await _status(env))["credential_count"] == 0


async def test_an_agent_with_a_non_empty_override_counts_once(env) -> None:
    await env.conn.execute(
        "INSERT INTO agents (name, tool_overrides, mcp_overrides) VALUES (?, ?, ?)",
        (
            "loud",
            env.encryptor.encrypt(json.dumps({"shell": {"timeout": 30}})),
            env.encryptor.encrypt(json.dumps({"src": {"TOKEN": "x"}})),
        ),
    )
    await env.conn.commit()
    assert (await _status(env))["credential_count"] == 1


async def test_undecryptable_residue_is_not_an_error(env) -> None:
    pid = await _provider(env, "Residue")
    await env.conn.execute("UPDATE llm_providers SET secrets = '{}' WHERE id = ?", (pid,))
    await env.conn.commit()
    assert (await _status(env))["credential_count"] == 0


async def test_last_rotated_at_is_null_then_a_timestamp_and_the_count_survives(env) -> None:
    await _provider(env, "Rotated", "sk-rotatedcount9999")
    before = await _status(env)
    assert before["last_rotated_at"] is None
    assert before["credential_count"] == 1
    resp = await env.client.post("/api/encryption/rotate")
    assert resp.status_code == 200
    after = await _status(env)
    assert after["credential_count"] == 1
    assert after["last_rotated_at"]
    assert after["last_rotated_at"].endswith("+00:00")  # UTC ISO
    assert after["key_file_pending"] is False


async def test_a_staged_rotation_stores_the_time_and_reports_the_key_pending(env) -> None:
    await _provider(env, "Staged", "sk-stagedstaged1111")
    real_replace = __import__("os").replace

    def flaky_replace(src, dst, *a, **kw):
        if str(dst) == str(env.key_path):
            raise OSError("simulated promote failure")
        return real_replace(src, dst, *a, **kw)

    with patch("the_one.encryption.os.replace", side_effect=flaky_replace):
        resp = await env.client.post("/api/encryption/rotate")
    assert resp.status_code == 200
    assert resp.json()["key_file"] == "staged"
    assert next_key_path(env.key_path).exists()
    status = await _status(env)
    assert status["last_rotated_at"]
    assert status["key_file_pending"] is True


async def test_a_failed_commit_leaves_the_recorded_time_unchanged(env) -> None:
    await _provider(env, "Failing", "sk-failingfailing22")
    await env.conn.execute(
        "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
        (ENCRYPTION_LAST_ROTATED_KEY, "2020-01-01T00:00:00+00:00"),
    )
    await env.conn.commit()
    with (
        patch("aiosqlite.Connection.commit", side_effect=RuntimeError("simulated DB failure")),
        pytest.raises(RuntimeError, match="simulated DB failure"),
    ):
        await env.client.post("/api/encryption/rotate")
    assert (await _status(env))["last_rotated_at"] == "2020-01-01T00:00:00+00:00"


async def test_a_second_rotation_moves_the_time_forward(env) -> None:
    await env.client.post("/api/encryption/rotate")
    first = (await _status(env))["last_rotated_at"]
    await env.client.post("/api/encryption/rotate")
    second = (await _status(env))["last_rotated_at"]
    assert first and second and second >= first

"""Rotation-restart test (design review Q3, resolved): after
``POST /api/encryption/rotate``, a running stub listener must reconnect
successfully using the re-encrypted secrets — via the rotation-restart
hook in ``rotate_encryption_key`` (interfaces/web/api.py) AND
``ConnectorManager._run``'s fresh-row re-fetch on every reconnect attempt
(manager.py). Mission 23 Flight 2 Leg 2.
"""

from __future__ import annotations

import asyncio
import json

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


@pytest.fixture(autouse=True)
async def _reset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("THE_ONE_STUB_TEST_ENDPOINT", "1")
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    registry.register_for_test("stub", StubPlugin())
    yield
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    set_manager(None)


@pytest.fixture
async def client_and_key(tmp_path):
    """Mirrors ``tests/test_api_secret_mask_roundtrip.py``'s fixture of the
    same name — an isolated DB + file-backed test encryptor, patched into
    ``interfaces.web.api``'s module-level accessors."""
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    key_path.write_bytes(test_key)
    test_encryptor = Encryptor(test_key, key_path=key_path)

    from unittest.mock import patch

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
            yield c, test_encryptor, db_path

    await conn.close()


async def test_listener_survives_rotation(client_and_key) -> None:
    client, test_encryptor, db_path = client_and_key
    mgr = ConnectorManager(poll_interval=0.01, backoff_base=0.01, backoff_max=0.02)
    set_manager(mgr)

    create = await client.post(
        "/api/connectors",
        json={
            "name": "Stub",
            "type": "stub",
            "config": {"default_agent": "bot-1"},
            "secrets": {"token": "rotate-me-secret"},
        },
    )
    assert create.status_code == 201
    connector_id = create.json()["id"]
    await asyncio.sleep(0.05)
    assert len(StubPlugin.connect_calls) == 1
    assert mgr.client_for(connector_id) is not None

    # Rotate the encryption key.
    resp = await client.post("/api/encryption/rotate")
    assert resp.status_code == 200
    assert resp.json()["key_file"] in ("promoted", "staged")

    # The stored row decrypts correctly under the NEW key (install_key
    # mutated test_encryptor in place).
    direct_conn = await aiosqlite.connect(str(db_path))
    direct_conn.row_factory = aiosqlite.Row
    try:
        async with direct_conn.execute(
            "SELECT secrets FROM connectors WHERE id = ?", (connector_id,)
        ) as cur:
            row = await cur.fetchone()
    finally:
        await direct_conn.close()
    decrypted = json.loads(test_encryptor.decrypt(row["secrets"]))
    assert decrypted == {"token": "rotate-me-secret"}

    # The rotation-restart hook already cycled the listener (stop+start
    # from a fresh row) — connect_calls grew even without a forced
    # reconnect.
    assert len(StubPlugin.connect_calls) >= 2
    assert mgr.client_for(connector_id) is not None

    # Force a further reconnect after rotation — proves `_run`'s fresh-row
    # re-fetch (not just the one-time restart hook) keeps working.
    calls_before = len(StubPlugin.connect_calls)
    StubPlugin.mark_dead(connector_id)
    await asyncio.sleep(0.2)
    assert len(StubPlugin.connect_calls) > calls_before
    assert mgr.client_for(connector_id) is not None

    await mgr.drain()

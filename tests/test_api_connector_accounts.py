"""Tests for the discoverable-entities REST endpoints (M11 F3 L4).

Covers ``GET /api/connectors/{id}/discoverable-entities`` and
``POST /api/connectors/{id}/discoverable-entities/refresh``.

The fixture pattern is lifted verbatim from
``tests/test_api_connector_account_config_validation.py:24-58``
(``AsyncClient(ASGITransport(app=FastAPI))`` over an in-memory schema
with a test encryptor). Pool-warming uses
:func:`the_one.connectors._pool.account_acquire` directly (option (a)
from the leg artifact's Pool-warming pattern note); the stub plugin is
registered via :func:`the_one.connectors.registry.register_for_test`.

Per the leg artifact's race-safety contract the helper
``_refresh_discoverable_entities_for_account`` is the single write
path — these tests exercise both the inline-refresh and the explicit
POST-refresh routes through that helper.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.connectors import _pool as pool_mod
from the_one.connectors._pool import account_acquire
from the_one.connectors.base import (
    DiscoverableEntities,
    DiscoverableEntity,
    DoctorReport,
    SessionKey,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


@pytest.fixture
async def client(tmp_path):
    """Test client with an isolated DB and test encryptor.

    Mirrors ``tests/test_api_connector_account_config_validation.py``'s
    fixture verbatim.
    """
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    test_encryptor = Encryptor(test_key, key_path=key_path)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
        # `_load_account` reads via its own ``get_connection`` import inside
        # the function body. Patch the source module so the pool resolves
        # against the same in-memory DB the API handler uses.
        patch("the_one.db.connection.get_connection", return_value=conn),
    ):
        test_app = FastAPI()
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


@pytest.fixture(autouse=True)
async def _clear_pool_after_each_test():
    """Reset pool + registry state between tests to keep the leg's
    sweep task and warm entries from leaking across cases."""
    yield
    await pool_mod._clear_for_test()
    restore_to_baseline_for_test()


class _StubClient:
    def __init__(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive


_DEFAULT_SNAPSHOT = DiscoverableEntities(
    peers=[
        DiscoverableEntity(id="u1", label="@alice"),
        DiscoverableEntity(id="u2", label="@bob"),
    ],
    channels=[DiscoverableEntity(id="c1", label="#general")],
    groups=[DiscoverableEntity(id="g1", label="Guild One")],
    roles=[DiscoverableEntity(id="r1", label="@everyone", group="guild:g1")],
    fetched_at="2026-05-22T00:00:00+00:00",
)


class _DiscoverableStubPlugin:
    """Stub plugin that implements ``enumerate_discoverable_entities``."""

    next_snapshot: DiscoverableEntities = _DEFAULT_SNAPSHOT

    async def connect(self, account, encryptor):  # noqa: ANN001
        return _StubClient()

    async def disconnect(self, client):  # noqa: ANN001
        client._alive = False

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="stub", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
        )

    def enumerate_discoverable_entities(self, client):  # noqa: ANN001
        return type(self).next_snapshot


class _HooklessStubPlugin:
    """Stub plugin without the ``enumerate_discoverable_entities`` hook."""

    async def connect(self, account, encryptor):  # noqa: ANN001
        return _StubClient()

    async def disconnect(self, client):  # noqa: ANN001
        client._alive = False

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="stub", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
        )


async def _create_account(
    client: AsyncClient,
    *,
    account_id: str = "acct-1",
    type_name: str = "stub",
    name: str = "Stub Account",
) -> dict:
    """Helper: POST a connector account through the API and return it."""
    resp = await client.post(
        "/api/connectors",
        json={
            "id": account_id,
            "name": name,
            "type": type_name,
            "config": {},
            "secrets": {},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─────────────────────────────────────────────────────────────────
# GET endpoint tests
# ─────────────────────────────────────────────────────────────────


async def test_get_discoverable_entities_returns_404_for_unknown_account(
    client: AsyncClient,
) -> None:
    """GET against a non-existent account_id → 404 with the
    'Connector not found' detail."""
    resp = await client.get(
        "/api/connectors/does-not-exist/discoverable-entities"
    )
    assert resp.status_code == 404
    assert resp.json() == {
        "detail": "Connector not found: does-not-exist"
    }


async def test_get_discoverable_entities_returns_404_for_cold_account(
    client: AsyncClient,
) -> None:
    """GET against an account that exists but has no warm pool entry
    → 404 with the pre-probe hint."""
    register_for_test("stub", _DiscoverableStubPlugin)
    _DiscoverableStubPlugin.next_snapshot = _DEFAULT_SNAPSHOT
    await _create_account(client, account_id="acct-cold")

    resp = await client.get(
        "/api/connectors/acct-cold/discoverable-entities"
    )
    assert resp.status_code == 404
    assert resp.json() == {
        "detail": "Run Test Connection first to populate the bot's discoverable view."
    }


async def test_get_discoverable_entities_returns_200_for_warm_account(
    client: AsyncClient,
) -> None:
    """GET against a warm account → 200 with populated entities.

    The first-call edge case (no cache yet) triggers the inline
    refresh before the response is built.
    """
    register_for_test("stub", _DiscoverableStubPlugin)
    _DiscoverableStubPlugin.next_snapshot = _DEFAULT_SNAPSHOT
    await _create_account(client, account_id="acct-warm")
    await account_acquire("acct-warm")

    resp = await client.get(
        "/api/connectors/acct-warm/discoverable-entities"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["entities"].keys()) == {"peers", "channels", "groups", "roles"}
    peers = body["entities"]["peers"]
    assert [p["id"] for p in peers] == ["u1", "u2"]
    assert all(p["stale"] is False for p in peers)
    assert body["entities"]["channels"][0]["id"] == "c1"
    assert body["entities"]["groups"][0]["id"] == "g1"
    assert body["entities"]["roles"][0]["id"] == "r1"
    assert body["stale_seconds"] >= 0.0


async def test_get_discoverable_entities_returns_503_for_account_type_without_hook(
    client: AsyncClient,
) -> None:
    """A stub-typed account whose plugin omits the hook → 503."""
    register_for_test("stub", _HooklessStubPlugin)
    await _create_account(client, account_id="acct-hookless")
    await account_acquire("acct-hookless")

    resp = await client.get(
        "/api/connectors/acct-hookless/discoverable-entities"
    )
    assert resp.status_code == 503
    assert resp.json() == {
        "detail": "This connector type does not expose discoverable entities."
    }


# ─────────────────────────────────────────────────────────────────
# POST refresh endpoint tests
# ─────────────────────────────────────────────────────────────────


async def test_post_refresh_discoverable_entities_returns_200_for_warm_account(
    client: AsyncClient,
) -> None:
    """POST refresh produces a successful 200 with the latest snapshot.

    Two successive POSTs separated by a short sleep produce
    distinct ``fetched_at`` timestamps (strict inequality on the ISO
    string) and a non-negative ``stale_seconds``.
    """
    register_for_test("stub", _DiscoverableStubPlugin)
    _DiscoverableStubPlugin.next_snapshot = _DEFAULT_SNAPSHOT
    await _create_account(client, account_id="acct-refresh")
    await account_acquire("acct-refresh")

    resp1 = await client.post(
        "/api/connectors/acct-refresh/discoverable-entities/refresh"
    )
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert [p["id"] for p in body1["entities"]["peers"]] == ["u1", "u2"]

    # Mutate the plugin's snapshot AND advance the timestamp string so
    # the strict-inequality assertion on ISO ``fetched_at`` holds even
    # on sub-microsecond hosts.
    _DiscoverableStubPlugin.next_snapshot = DiscoverableEntities(
        peers=[DiscoverableEntity(id="u1", label="@alice")],
        fetched_at="2026-05-22T00:00:01+00:00",
    )
    await asyncio.sleep(0.001)

    resp2 = await client.post(
        "/api/connectors/acct-refresh/discoverable-entities/refresh"
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert [p["id"] for p in body2["entities"]["peers"]][:1] == ["u1"]
    # Strict inequality on ISO timestamp + non-negative stale_seconds.
    assert body2["fetched_at"] != body1["fetched_at"]
    assert body2["stale_seconds"] >= 0.0


async def test_post_refresh_discoverable_entities_returns_404_for_cold_account(
    client: AsyncClient,
) -> None:
    """POST refresh against a cold account → 404 with the pre-probe hint."""
    register_for_test("stub", _DiscoverableStubPlugin)
    _DiscoverableStubPlugin.next_snapshot = _DEFAULT_SNAPSHOT
    await _create_account(client, account_id="acct-cold-post")

    resp = await client.post(
        "/api/connectors/acct-cold-post/discoverable-entities/refresh"
    )
    assert resp.status_code == 404
    assert resp.json() == {
        "detail": "Run Test Connection first to populate the bot's discoverable view."
    }


# ─────────────────────────────────────────────────────────────────
# Stale-flag projection
# ─────────────────────────────────────────────────────────────────


async def test_discoverable_entities_response_projects_stale_flag(
    client: AsyncClient,
) -> None:
    """After a refresh that drops entity ``C``, the GET response carries
    ``A`` and ``B`` with ``stale: false`` and ``C`` with ``stale: true``.

    Pins the 1-cycle stale-carry retention semantics at the API
    boundary.
    """
    register_for_test("stub", _DiscoverableStubPlugin)
    _DiscoverableStubPlugin.next_snapshot = DiscoverableEntities(
        peers=[
            DiscoverableEntity(id="A", label="@alpha"),
            DiscoverableEntity(id="B", label="@bravo"),
            DiscoverableEntity(id="C", label="@charlie"),
        ],
        fetched_at="2026-05-22T00:00:00+00:00",
    )
    await _create_account(client, account_id="acct-stale")
    await account_acquire("acct-stale")

    # First refresh: cache = {A, B, C}; stale_carry = {}.
    resp1 = await client.post(
        "/api/connectors/acct-stale/discoverable-entities/refresh"
    )
    assert resp1.status_code == 200, resp1.text

    # Second refresh: snapshot drops C → cache = {A, B}; stale_carry = {C}.
    _DiscoverableStubPlugin.next_snapshot = DiscoverableEntities(
        peers=[
            DiscoverableEntity(id="A", label="@alpha"),
            DiscoverableEntity(id="B", label="@bravo"),
        ],
        fetched_at="2026-05-22T00:05:00+00:00",
    )
    resp2 = await client.post(
        "/api/connectors/acct-stale/discoverable-entities/refresh"
    )
    assert resp2.status_code == 200, resp2.text

    resp = await client.get(
        "/api/connectors/acct-stale/discoverable-entities"
    )
    assert resp.status_code == 200, resp.text
    peers = resp.json()["entities"]["peers"]
    by_id = {p["id"]: p["stale"] for p in peers}
    assert by_id == {"A": False, "B": False, "C": True}

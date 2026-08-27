"""API + registry-lifecycle tests for the external-client credential store
(M21 F03 L01).

Covers AC2/AC3/AC4/AC5 (mint/list/revoke/rotate endpoint lifecycle, the
409-when-not-enabled and 401-after-revoke behaviours, secret-free list),
AC9 (DB-level cascade + registry eviction on disable), AC10 (startup
reconcile rebuilds the registry; a revoked credential does not), and AC11
(seam registration is idempotent by list membership across an
``api_credential._sources`` swap).

The out-of-process ``MCPClient`` tool-call tests (AC6/AC7/AC8, and AC9's
tool-level refusal) live in ``tests/test_self_configuration_surface.py``,
where the ``running_surface`` uvicorn fixture is defined.

Mirrors ``tests/test_self_configuration_api.py::client`` — a throwaway
FastAPI app wrapping only ``the_one.interfaces.web.api.router`` (no gate
middleware), with ``get_connection`` / ``get_encryptor`` patched to an
isolated per-test SQLite connection + encryptor (``PRAGMA foreign_keys=ON``,
so the AC9 cascade actually fires).
"""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one import api_credential
from the_one.api_credential import resolve_caller
from the_one.db.repositories import (
    AgentExternalCredentialRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.self_configuration import credentials as sc_credentials
from the_one.self_configuration import external_credentials as sc_external


@pytest.fixture(autouse=True)
def _isolated_registries():
    """Clean in-memory registries per test, and both credential sources
    registered against the shared ``api_credential`` seam (the throwaway
    app never runs the real lifespan, which is what registers them in
    production). ``register_credential_source_once`` is idempotent by list
    membership, so calling it every test is safe."""
    sc_credentials.clear_for_test()
    sc_external.clear_for_test()
    sc_credentials.register_credential_source_once()
    sc_external.register_credential_source_once()
    yield
    sc_credentials.clear_for_test()
    sc_external.clear_for_test()


@pytest.fixture
async def env(tmp_path):
    """Isolated DB + encryptor, exposed both as an HTTP client and as raw
    repos (for the direct DB-level AC9/AC10 assertions)."""
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")

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
            yield _Env(c, conn, test_encryptor)

    await conn.close()


class _Env:
    def __init__(self, client, conn, encryptor):
        self.client = client
        self.conn = conn
        self.encryptor = encryptor

    def mcp_repo(self):
        return MCPSourceRepository(self.conn, self.encryptor)

    def ext_repo(self):
        return AgentExternalCredentialRepository(self.conn, self.encryptor)

    def agent_store(self):
        return SQLiteAgentStore(self.conn, self.encryptor)


async def _create_agent(client: AsyncClient, name: str) -> None:
    resp = await client.post("/api/agents", json={"name": name, "description": "t"})
    assert resp.status_code == 201, resp.text


async def _enable(client: AsyncClient, name: str) -> str:
    resp = await client.post(f"/api/agents/{name}/self-configuration")
    assert resp.status_code == 200, resp.text
    return resp.json()["source_id"]


async def _mint(client: AsyncClient, name: str, label: str = "my-tool"):
    return await client.post(
        f"/api/agents/{name}/self-configuration/external-credentials",
        json={"label": label},
    )


# ── AC3 — mint returns the token once, scoped, and only when enabled ─────


class TestMint:
    async def test_mint_on_enabled_returns_token_url_and_identifier(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        resp = await _mint(env.client, "a", label="external-client-1")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["label"] == "external-client-1"
        assert body["token"].startswith("ext_")
        assert "." in body["token"]
        assert body["identifier"] in body["token"]
        assert body["url"].endswith("/mcp/self-configuration/")
        # The minted token authenticates via the seam.
        caller = resolve_caller(body["token"])
        assert caller is not None
        assert caller.source == "self-configuration-external"

    async def test_mint_before_enable_is_409(self, env) -> None:
        await _create_agent(env.client, "a")
        resp = await _mint(env.client, "a")
        assert resp.status_code == 409, resp.text

    async def test_mint_on_orphaned_surface_is_409(self, env) -> None:
        """Review Issue #1: a detached-but-present (orphaned) surface must
        also 409 — gate on enabled, not on the row merely existing."""
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        # Detach via PUT without deleting the row → orphaned.
        resp = await env.client.put("/api/agents/a", json={"name": "a", "mcp_source_ids": []})
        assert resp.status_code == 200, resp.text
        resp = await _mint(env.client, "a")
        assert resp.status_code == 409, resp.text

    async def test_mint_unknown_agent_404(self, env) -> None:
        resp = await _mint(env.client, "ghost")
        assert resp.status_code == 404

    async def test_secret_is_never_returned_by_list(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        token = (await _mint(env.client, "a")).json()["token"]
        secret = token.split(".", 1)[1]
        listing = await env.client.get("/api/agents/a/self-configuration/external-credentials")
        assert secret not in listing.text


# ── AC4 — list is a secret-free structural projection ────────────────────


class TestList:
    async def test_list_shape_and_secret_free(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        m1 = (await _mint(env.client, "a", "one")).json()
        (await _mint(env.client, "a", "two")).json()
        resp = await env.client.get("/api/agents/a/self-configuration/external-credentials")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 2
        for row in rows:
            assert set(row) == {"identifier", "label", "created_at"}
        assert m1["token"].split(".", 1)[1] not in resp.text

    async def test_list_empty_for_agent_with_no_surface(self, env) -> None:
        await _create_agent(env.client, "a")
        resp = await env.client.get("/api/agents/a/self-configuration/external-credentials")
        assert resp.status_code == 200
        assert resp.json() == []


# ── AC5 — revoke is immediate and scoped; rotate reissues ────────────────


class TestRevokeAndRotate:
    async def test_revoke_evicts_registry_next_request_401(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        token = (await _mint(env.client, "a")).json()["token"]
        ident = resolve_caller(token).identifier
        assert resolve_caller(token) is not None

        resp = await env.client.delete(
            f"/api/agents/a/self-configuration/external-credentials/{ident}"
        )
        assert resp.status_code == 200, resp.text
        # Evicted from the registry → no longer resolves (the gate would 401).
        assert resolve_caller(token) is None
        # And gone from the store's list.
        listing = (
            await env.client.get("/api/agents/a/self-configuration/external-credentials")
        ).json()
        assert ident not in {r["identifier"] for r in listing}

    async def test_revoke_does_not_disturb_other_external_credential(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        keep_token = (await _mint(env.client, "a", "keep")).json()["token"]
        drop_token = (await _mint(env.client, "a", "drop")).json()["token"]
        drop_ident = resolve_caller(drop_token).identifier

        await env.client.delete(
            f"/api/agents/a/self-configuration/external-credentials/{drop_ident}"
        )
        assert resolve_caller(drop_token) is None
        assert resolve_caller(keep_token) is not None  # untouched

    async def test_rotate_reissues_old_dies_new_authenticates(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        minted = (await _mint(env.client, "a", "rot")).json()
        old_token = minted["token"]
        old_ident = minted["identifier"]

        resp = await env.client.post(
            f"/api/agents/a/self-configuration/external-credentials/{old_ident}/rotate"
        )
        assert resp.status_code == 200, resp.text
        new = resp.json()
        assert new["label"] == "rot"  # same label
        assert new["identifier"] != old_ident  # new principal (DD7)
        assert resolve_caller(old_token) is None  # old dies immediately
        assert resolve_caller(new["token"]) is not None  # new authenticates

    async def test_revoke_cross_id_guard_404(self, env) -> None:
        await _create_agent(env.client, "a")
        await _create_agent(env.client, "b")
        await _enable(env.client, "a")
        await _enable(env.client, "b")
        a_ident = (await _mint(env.client, "a")).json()["identifier"]
        # Try to revoke a's credential through b's route → 404.
        resp = await env.client.delete(
            f"/api/agents/b/self-configuration/external-credentials/{a_ident}"
        )
        assert resp.status_code == 404

    async def test_rotate_cross_id_guard_404(self, env) -> None:
        await _create_agent(env.client, "a")
        await _create_agent(env.client, "b")
        await _enable(env.client, "a")
        await _enable(env.client, "b")
        a_ident = (await _mint(env.client, "a")).json()["identifier"]
        resp = await env.client.post(
            f"/api/agents/b/self-configuration/external-credentials/{a_ident}/rotate"
        )
        assert resp.status_code == 404

    async def test_revoke_unknown_identifier_404(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        resp = await env.client.delete(
            "/api/agents/a/self-configuration/external-credentials/does-not-exist"
        )
        assert resp.status_code == 404


# ── AC9 — dies with the surface (DB-level cascade + registry eviction) ───


class TestDiesWithSurface:
    async def test_disable_cascades_rows_and_evicts_registry(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        token = (await _mint(env.client, "a")).json()["token"]
        assert resolve_caller(token) is not None

        # Disable via the endpoint (full teardown path).
        resp = await env.client.delete("/api/agents/a/self-configuration")
        assert resp.status_code == 200, resp.text

        # FK cascade removed the store rows → list is empty.
        listing = (
            await env.client.get("/api/agents/a/self-configuration/external-credentials")
        ).json()
        assert listing == []
        # In-memory registry evicted → the token no longer resolves.
        assert resolve_caller(token) is None

    async def test_orphaned_surface_keeps_rows_but_still_resolves_registry(self, env) -> None:
        """An orphaned (detached, not deleted) surface keeps its credential
        rows (no cascade) and the registry still resolves — the tool-call
        refusal (DD9) is asserted at the MCPClient layer in
        test_self_configuration_surface.py."""
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        token = (await _mint(env.client, "a")).json()["token"]

        # Detach without delete → orphaned; row (and its credential) survive.
        await env.client.put("/api/agents/a", json={"name": "a", "mcp_source_ids": []})

        listing = (
            await env.client.get("/api/agents/a/self-configuration/external-credentials")
        ).json()
        assert len(listing) == 1  # rows not cascade-gone
        assert resolve_caller(token) is not None  # registry still resolves

    async def test_agent_delete_cascades_and_evicts(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        token = (await _mint(env.client, "a")).json()["token"]
        assert resolve_caller(token) is not None

        resp = await env.client.delete("/api/agents/a")
        assert resp.status_code in (200, 204), resp.text
        assert resolve_caller(token) is None


# ── AC10 — survives restart (startup reconcile rebuilds the registry) ────


class TestSurvivesRestart:
    async def test_reconcile_rebuilds_live_and_drops_revoked(self, env) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        live_token = (await _mint(env.client, "a", "live")).json()["token"]
        revoked = (await _mint(env.client, "a", "revoked")).json()
        revoked_token = revoked["token"]

        # Revoke one (row DELETE + registry eviction).
        await env.client.delete(
            f"/api/agents/a/self-configuration/external-credentials/{revoked['identifier']}"
        )

        # Simulate a process restart: wipe the in-memory registry, then
        # rebuild it from the store exactly as the lifespan reconcile does.
        sc_external.clear_for_test()
        assert resolve_caller(live_token) is None  # nothing loaded yet
        sc_external.load_from_rows(await env.ext_repo().load_all())

        assert resolve_caller(live_token) is not None  # non-revoked survives
        assert resolve_caller(revoked_token) is None  # revoked row is gone


# ── AC11 — registered on the seam idempotently (list-membership) ─────────


class TestSeamRegistrationIdempotent:
    async def test_self_heals_across_sources_swap(self, monkeypatch) -> None:
        """Mirror the `agt` precedent: registration is idempotent by ACTUAL
        LIST MEMBERSHIP, so it self-heals after a fixture swaps
        `api_credential._sources` wholesale (a stale boolean flag would
        report 'already registered' and leave the source out)."""
        # Swap the sources list out from under any prior registration.
        monkeypatch.setattr(api_credential, "_sources", [api_credential.FileCredentialSource()])
        assert not any(
            isinstance(s, sc_external.ExternalAgentCredentialSource)
            for s in api_credential._sources
        )
        sc_external.register_credential_source_once()
        assert any(
            isinstance(s, sc_external.ExternalAgentCredentialSource)
            for s in api_credential._sources
        )
        # Second call is a no-op — exactly one instance present.
        sc_external.register_credential_source_once()
        count = sum(
            isinstance(s, sc_external.ExternalAgentCredentialSource)
            for s in api_credential._sources
        )
        assert count == 1

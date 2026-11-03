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

import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one import api_credential
from the_one.api_credential import IdentifiedCaller, resolve_caller
from the_one.db.repositories import (
    AgentExternalCredentialRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor
from the_one.interfaces.web.middleware import CALLER_SCOPE_KEY
from the_one.self_configuration import credentials as sc_credentials
from the_one.self_configuration import external_credentials as sc_external
from the_one.self_configuration import manage as sc_manage


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
    conn = await connect_template_db(db_path)

    test_encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
    ):
        test_app = shared_app()
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
        # Detach by a direct store save (a PUT can no longer detach, sortie 08
        # DD2) without deleting the row → orphaned.
        store = env.agent_store()
        cfg = await store.load("a")
        await store.save(cfg.model_copy(update={"mcp_source_ids": []}))
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

        # Detach without delete (direct store save) → orphaned; row (and its
        # credential) survive.
        store = env.agent_store()
        cfg = await store.load("a")
        await store.save(cfg.model_copy(update={"mcp_source_ids": []}))

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


# ── Flight 01 Leg 2 (B8-ext-credential-trace) — operator-readable trace ──
#
# AC1-AC3, AC7: route-layer mint/revoke/rotate log lines and principal
# rendering. AC4: `unregister` return value. AC5-AC6: cascade log lines at
# both surface-teardown call sites, reached through all three entrypoints.
# Q2 (flight.md Design Decisions): log lines only, no `revoked_at`
# tombstone — every issuance and every disappearance leaves an
# operator-readable INFO line, never the secret.


def _api_records(caplog):
    return [
        r
        for r in caplog.records
        if r.name == "the_one.interfaces.web.api"
        and r.getMessage().startswith("external-credential:")
    ]


def _manage_records(caplog):
    return [
        r
        for r in caplog.records
        if r.name == "the_one.self_configuration.manage"
        and r.getMessage().startswith("external-credential:")
    ]


class TestLifecycleTrace:
    async def test_mint_logs_agent_identifier_label_principal_no_secret(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        with caplog.at_level(logging.INFO, logger="the_one.interfaces.web.api"):
            minted = (await _mint(env.client, "a", "external-client-1")).json()
        records = _api_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "a" in message
        assert minted["identifier"] in message
        assert "external-client-1" in message
        secret = minted["token"].split(".", 1)[1]
        assert secret not in caplog.text

    async def test_revoke_logs_agent_identifier_label_principal(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        minted = (await _mint(env.client, "a", "to-revoke")).json()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="the_one.interfaces.web.api"):
            resp = await env.client.delete(
                f"/api/agents/a/self-configuration/external-credentials/{minted['identifier']}"
            )
        assert resp.status_code == 200, resp.text
        records = _api_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "a" in message
        assert minted["identifier"] in message
        assert "to-revoke" in message

    async def test_revoke_unknown_identifier_emits_no_log_line(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        with caplog.at_level(logging.INFO, logger="the_one.interfaces.web.api"):
            resp = await env.client.delete(
                "/api/agents/a/self-configuration/external-credentials/does-not-exist"
            )
        assert resp.status_code == 404
        assert _api_records(caplog) == []

    async def test_rotate_logs_old_new_identifier_label_principal_no_secrets(
        self, env, caplog
    ) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        minted = (await _mint(env.client, "a", "rot")).json()
        old_identifier = minted["identifier"]
        old_secret = minted["token"].split(".", 1)[1]
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="the_one.interfaces.web.api"):
            resp = await env.client.post(
                f"/api/agents/a/self-configuration/external-credentials/{old_identifier}/rotate"
            )
        assert resp.status_code == 200, resp.text
        new = resp.json()
        records = _api_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert old_identifier in message
        assert new["identifier"] in message
        assert "rot" in message
        assert "a" in message
        new_secret = new["token"].split(".", 1)[1]
        assert old_secret not in caplog.text
        assert new_secret not in caplog.text

    async def test_unregister_returns_evicted_identifiers(self, env) -> None:
        """AC4: `unregister(source_id)` returns the list of identifiers it
        evicted (empty list on no-match)."""
        await _create_agent(env.client, "a")
        source_id = await _enable(env.client, "a")
        minted = (await _mint(env.client, "a")).json()
        evicted = sc_external.unregister(source_id)
        assert evicted == [minted["identifier"]]
        # Idempotent no-op the second time.
        assert sc_external.unregister(source_id) == []
        assert sc_external.unregister("does-not-exist") == []

    async def test_disable_via_self_configuration_route_logs_cascade(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        minted = (await _mint(env.client, "a", "cascaded")).json()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="the_one.self_configuration.manage"):
            resp = await env.client.delete("/api/agents/a/self-configuration")
        assert resp.status_code == 200, resp.text
        records = _manage_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "a" in message
        assert minted["identifier"] in message
        assert "1" in message  # count

    async def test_disable_with_no_credentials_logs_nothing(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        with caplog.at_level(logging.INFO, logger="the_one.self_configuration.manage"):
            resp = await env.client.delete("/api/agents/a/self-configuration")
        assert resp.status_code == 200, resp.text
        assert _manage_records(caplog) == []

    async def test_direct_mcp_source_delete_of_surface_row_logs_cascade(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        minted = (await _mint(env.client, "a", "cascaded")).json()
        row = await sc_manage.find_surface_row(env.mcp_repo(), "a")
        assert row is not None
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="the_one.self_configuration.manage"):
            resp = await env.client.delete(f"/api/mcp-sources/{row.id}")
        assert resp.status_code == 200, resp.text
        records = _manage_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert minted["identifier"] in message

    async def test_agent_delete_cascade_logs_removed_with_agent(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        minted = (await _mint(env.client, "a", "cascaded")).json()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="the_one.self_configuration.manage"):
            resp = await env.client.delete("/api/agents/a")
        assert resp.status_code in (200, 204), resp.text
        records = _manage_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert minted["identifier"] in message
        assert "removed with the agent" in message

    async def test_principal_rendered_when_caller_present(self, env, caplog) -> None:
        """AC7: wrap the throwaway app in a two-line pure-ASGI shim that
        stamps `scope[CALLER_SCOPE_KEY]` and asserts `source:identifier`
        appears in the mint record; the other tests (no shim) accept `-`."""
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")

        test_app = shared_app()

        async def shim(scope, receive, send):
            if scope["type"] == "http":
                scope[CALLER_SCOPE_KEY] = IdentifiedCaller(identifier="loc_test", source="file")
            await test_app(scope, receive, send)

        transport = ASGITransport(app=shim)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as shimmed_client:
            with caplog.at_level(logging.INFO, logger="the_one.interfaces.web.api"):
                resp = await shimmed_client.post(
                    "/api/agents/a/self-configuration/external-credentials",
                    json={"label": "shimmed"},
                )
        assert resp.status_code == 200, resp.text
        records = _api_records(caplog)
        assert len(records) == 1
        assert "file:loc_test" in records[0].getMessage()

    async def test_principal_is_dash_when_caller_absent(self, env, caplog) -> None:
        await _create_agent(env.client, "a")
        await _enable(env.client, "a")
        with caplog.at_level(logging.INFO, logger="the_one.interfaces.web.api"):
            await _mint(env.client, "a", "no-principal")
        records = _api_records(caplog)
        assert len(records) == 1
        assert records[0].getMessage().endswith("by -")

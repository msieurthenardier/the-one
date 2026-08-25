"""API-level tests for the self-configuration surface (M21 F01 L02).

Covers AC1 (off by default), AC2 (enable mints and attaches), AC4 (identity
resolves / stops resolving), AC9 (ownership guard), AC10 (admin isolation),
AC11 (lifecycle cascades — rename, delete, startup reconcile).

Uses the `tests/test_db_api.py::client` fixture shape: a throwaway FastAPI
app wrapping only `the_one.interfaces.web.api.router` (no gate middleware),
with `the_one.interfaces.web.api.get_connection` / `get_encryptor` patched
to an isolated per-test SQLite connection + encryptor.
"""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.api_credential import resolve_caller
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.self_configuration import credentials as sc_credentials


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Every test in this module gets a clean in-memory credential
    registry — without this, a credential minted by one test would resolve
    in a later, unrelated test (or vice versa: a leftover registration
    would make a later test's "not registered" assertion false).

    Also ensures ``SelfConfigurationCredentialSource`` is registered
    against the shared ``api_credential`` lookup seam — the throwaway test
    app here never runs the real app's lifespan (which is what registers
    it in production), so ``resolve_caller`` would never consult it
    otherwise. ``register_credential_source_once`` is itself idempotent
    (module-level guard), so calling it from every test's setup is safe.
    """
    sc_credentials.clear_for_test()
    sc_credentials.register_credential_source_once()
    yield
    sc_credentials.clear_for_test()


@pytest.fixture
async def client(tmp_path):
    """Isolated DB + encryptor, mirrors `tests/test_db_api.py::client`."""
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
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
            yield c

    await conn.close()


async def _create_agent(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/api/agents", json={"name": name, "description": "test agent"})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── AC1 — off by default ────────────────────────────────────────────────


class TestOffByDefault:
    async def test_status_reports_disabled_for_fresh_agent(self, client: AsyncClient) -> None:
        await _create_agent(client, "fresh-agent")
        resp = await client.get("/api/agents/fresh-agent/self-configuration")
        assert resp.status_code == 200
        assert resp.json() == {"enabled": False}

    async def test_fresh_agent_has_no_mcp_source_ids(self, client: AsyncClient) -> None:
        agent = await _create_agent(client, "fresh-agent-2")
        assert agent["mcp_source_ids"] == []

    async def test_unknown_agent_404s(self, client: AsyncClient) -> None:
        resp = await client.get("/api/agents/does-not-exist/self-configuration")
        assert resp.status_code == 404


# ── AC2 — enable mints and attaches ─────────────────────────────────────


class TestEnableMintsAndAttaches:
    async def test_enable_creates_one_attached_streamable_http_row(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "enable-agent")
        resp = await client.post("/api/agents/enable-agent/self-configuration")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        agent = (await client.get("/api/agents/enable-agent")).json()
        assert len(agent["mcp_source_ids"]) == 1
        source_id = agent["mcp_source_ids"][0]

        source = (
            await client.get("/api/mcp-sources", params={"include_agent_surfaces": "1"})
        ).json()
        row = next(s for s in source if s["id"] == source_id)
        assert row["type"] == "streamable-http"
        assert row["name"] == "self-configuration"
        assert row["config"]["self_configuration"] == {"agent": "enable-agent"}
        assert row["config"]["_cache"]["auth_posture"] == "no_auth"
        tool_names = {t["name"] for t in row["config"]["_cache"]["tools"]}
        assert tool_names == {
            "get_my_configuration",
            "describe_my_capabilities",
            "update_my_description",
            "update_my_system_prompt",
        }

    async def test_enable_response_never_carries_the_credential(self, client: AsyncClient) -> None:
        await _create_agent(client, "no-leak-agent")
        resp = await client.post("/api/agents/no-leak-agent/self-configuration")
        assert "agt_" not in resp.text
        assert "Authorization" not in resp.text
        assert "Bearer" not in resp.text

    async def test_masked_secrets_endpoint_never_leaks_credential_either(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "masked-agent")
        await client.post("/api/agents/masked-agent/self-configuration")
        listing = await client.get("/api/mcp-sources", params={"include_agent_surfaces": "1"})
        assert "agt_" not in listing.text

    async def test_second_enable_is_idempotent_same_row_no_second_credential(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "idempotent-agent")
        first = (await client.post("/api/agents/idempotent-agent/self-configuration")).json()
        second = (await client.post("/api/agents/idempotent-agent/self-configuration")).json()
        assert first == second

        agent = (await client.get("/api/agents/idempotent-agent")).json()
        assert len(agent["mcp_source_ids"]) == 1

    async def test_enable_unknown_agent_404s(self, client: AsyncClient) -> None:
        resp = await client.post("/api/agents/nope/self-configuration")
        assert resp.status_code == 404


# ── orphaned_row — row exists but is no longer attached ─────────────────


class TestOrphanedRow:
    """Flight-end review fix: `manage.status()` reports an orphaned-row
    state when the surface row still exists but its id has fallen out of
    the owning agent's `mcp_source_ids` (a legitimate operator detach via
    `PUT /api/agents/{name}` that drops the id without deleting the row).
    `grep -rn "orphaned_row" tests/` was empty before this test."""

    async def test_status_reports_orphaned_row_after_detach_via_put(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "orphan-agent")
        await client.post("/api/agents/orphan-agent/self-configuration")
        agent = (await client.get("/api/agents/orphan-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        # Operator detaches the row without disabling — drop the id from
        # mcp_source_ids via PUT, leaving the mcp_sources row itself intact.
        resp = await client.put(
            "/api/agents/orphan-agent",
            json={"name": "orphan-agent", "mcp_source_ids": []},
        )
        assert resp.status_code == 200
        agent_after = resp.json()
        assert agent_after["mcp_source_ids"] == []

        # The row still exists (admin-visible listing, not deleted).
        listing = (
            await client.get("/api/mcp-sources", params={"include_agent_surfaces": "1"})
        ).json()
        assert any(s["id"] == source_id for s in listing)

        status = (await client.get("/api/agents/orphan-agent/self-configuration")).json()
        assert status == {
            "enabled": False,
            "orphaned_row": True,
            "source_id": source_id,
        }

    async def test_next_enable_after_orphan_reuses_the_row_not_a_duplicate(
        self, client: AsyncClient
    ) -> None:
        """Per `manage.status()`'s docstring: 'the next `enable` reuses
        that row rather than minting a duplicate.'"""
        await _create_agent(client, "reuse-agent")
        await client.post("/api/agents/reuse-agent/self-configuration")
        agent = (await client.get("/api/agents/reuse-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        await client.put(
            "/api/agents/reuse-agent",
            json={"name": "reuse-agent", "mcp_source_ids": []},
        )
        status = (await client.get("/api/agents/reuse-agent/self-configuration")).json()
        assert status["orphaned_row"] is True

        re_enabled = (await client.post("/api/agents/reuse-agent/self-configuration")).json()
        assert re_enabled == {"enabled": True, "source_id": source_id}

        agent_after = (await client.get("/api/agents/reuse-agent")).json()
        assert agent_after["mcp_source_ids"] == [source_id]

        listing = (
            await client.get("/api/mcp-sources", params={"include_agent_surfaces": "1"})
        ).json()
        surface_rows = [s for s in listing if s["config"].get("self_configuration")]
        assert len(surface_rows) == 1, "re-enable after orphan must not mint a duplicate row"


# ── AC4 — identity resolves; disable stops it resolving ─────────────────


class TestIdentityAndRefusal:
    async def test_credential_resolves_to_self_configuration_source(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "identity-agent")
        await client.post("/api/agents/identity-agent/self-configuration")

        source_rows = (
            await client.get("/api/mcp-sources", params={"include_agent_surfaces": "1"})
        ).json()
        row = next(
            s
            for s in source_rows
            if s["config"].get("self_configuration", {}).get("agent") == "identity-agent"
        )
        # The registry holds the REAL (unmasked) credential in-process —
        # read it directly rather than through the masked API response.
        identifiers = list(sc_credentials._registry.keys())
        assert len(identifiers) == 1
        identifier = identifiers[0]
        source_id, secret = sc_credentials._registry[identifier]
        assert source_id == row["id"]

        from the_one.api_credential import LocalApiCredential
        from the_one.self_configuration.constants import AGENT_CREDENTIAL_PREFIX

        token = LocalApiCredential(identifier=identifier, secret=secret).encode(
            prefix=AGENT_CREDENTIAL_PREFIX
        )
        caller = resolve_caller(token)
        assert caller is not None
        assert caller.source == "self-configuration"

    async def test_disable_makes_the_same_credential_stop_resolving(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "revoke-agent")
        await client.post("/api/agents/revoke-agent/self-configuration")

        identifier = next(iter(sc_credentials._registry.keys()))
        source_id, secret = sc_credentials._registry[identifier]
        from the_one.api_credential import LocalApiCredential
        from the_one.self_configuration.constants import AGENT_CREDENTIAL_PREFIX

        token = LocalApiCredential(identifier=identifier, secret=secret).encode(
            prefix=AGENT_CREDENTIAL_PREFIX
        )
        assert resolve_caller(token) is not None

        resp = await client.delete("/api/agents/revoke-agent/self-configuration")
        assert resp.status_code == 200
        assert resolve_caller(token) is None

    async def test_disable_is_idempotent(self, client: AsyncClient) -> None:
        await _create_agent(client, "double-disable-agent")
        await client.post("/api/agents/double-disable-agent/self-configuration")
        first = await client.delete("/api/agents/double-disable-agent/self-configuration")
        second = await client.delete("/api/agents/double-disable-agent/self-configuration")
        assert first.status_code == 200
        assert second.status_code == 200
        status = (await client.get("/api/agents/double-disable-agent/self-configuration")).json()
        assert status == {"enabled": False}


# ── AC9 — read scope is the agent itself (ownership guard) ──────────────


class TestOwnershipGuard:
    async def test_attaching_another_agents_surface_row_is_rejected(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "agent-a")
        await _create_agent(client, "agent-b")
        await client.post("/api/agents/agent-a/self-configuration")
        agent_a = (await client.get("/api/agents/agent-a")).json()
        surface_row_id = agent_a["mcp_source_ids"][0]

        resp = await client.put(
            "/api/agents/agent-b",
            json={"name": "agent-b", "mcp_source_ids": [surface_row_id]},
        )
        assert resp.status_code == 422

        agent_b = (await client.get("/api/agents/agent-b")).json()
        assert agent_b["mcp_source_ids"] == []

    async def test_credential_override_on_a_surface_row_is_rejected(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "override-agent")
        await client.post("/api/agents/override-agent/self-configuration")
        agent = (await client.get("/api/agents/override-agent")).json()
        source_name = "self-configuration"

        resp = await client.put(
            f"/api/agents/{agent['name']}",
            json={
                "name": agent["name"],
                "mcp_source_ids": agent["mcp_source_ids"],
                "mcp_overrides": {source_name: {"bearer_token": "attacker-supplied"}},
            },
        )
        assert resp.status_code == 422

    async def test_create_agent_rejects_foreign_surface_attachment(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "owner-agent")
        await client.post("/api/agents/owner-agent/self-configuration")
        owner = (await client.get("/api/agents/owner-agent")).json()
        surface_row_id = owner["mcp_source_ids"][0]

        resp = await client.post(
            "/api/agents",
            json={"name": "sneaky-agent", "mcp_source_ids": [surface_row_id]},
        )
        assert resp.status_code == 422


# ── AC10 — admin isolation ───────────────────────────────────────────────


class TestAdminIsolation:
    async def test_default_listing_omits_marked_rows(self, client: AsyncClient) -> None:
        await _create_agent(client, "hidden-agent")
        await client.post("/api/agents/hidden-agent/self-configuration")

        default_listing = (await client.get("/api/mcp-sources")).json()
        assert all(not s["config"].get("self_configuration") for s in default_listing)

    async def test_include_agent_surfaces_param_includes_marked_rows(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "visible-agent")
        await client.post("/api/agents/visible-agent/self-configuration")

        listing = (
            await client.get("/api/mcp-sources", params={"include_agent_surfaces": "1"})
        ).json()
        assert any(s["config"].get("self_configuration") for s in listing)

    async def test_put_on_marked_row_is_409(self, client: AsyncClient) -> None:
        await _create_agent(client, "locked-agent")
        await client.post("/api/agents/locked-agent/self-configuration")
        agent = (await client.get("/api/agents/locked-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        resp = await client.put(
            f"/api/mcp-sources/{source_id}",
            json={"name": "renamed-by-operator", "type": "streamable-http", "config": {}},
        )
        assert resp.status_code == 409

    async def test_delete_on_marked_row_performs_full_disable(self, client: AsyncClient) -> None:
        await _create_agent(client, "delete-via-admin-agent")
        await client.post("/api/agents/delete-via-admin-agent/self-configuration")
        agent = (await client.get("/api/agents/delete-via-admin-agent")).json()
        source_id = agent["mcp_source_ids"][0]
        identifier = next(iter(sc_credentials._registry.keys()))

        resp = await client.delete(f"/api/mcp-sources/{source_id}")
        assert resp.status_code == 200

        agent_after = (await client.get("/api/agents/delete-via-admin-agent")).json()
        assert source_id not in agent_after["mcp_source_ids"]
        assert sc_credentials.source_id_for(identifier) is None

        get_resp = await client.get(f"/api/mcp-sources/{source_id}")
        assert get_resp.status_code == 404


# ── AC8b — the constant name is reserved ─────────────────────────────────


_VALID_STREAMABLE_HTTP_CONFIG = {"url": "https://example.com/mcp"}


class TestAC8bReservedName:
    async def test_create_with_reserved_name_is_409(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "self-configuration",
                "type": "streamable-http",
                "config": _VALID_STREAMABLE_HTTP_CONFIG,
            },
        )
        assert resp.status_code == 409

    async def test_update_renaming_into_reserved_name_is_409(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "ordinary-source",
                "type": "streamable-http",
                "config": _VALID_STREAMABLE_HTTP_CONFIG,
            },
        )
        assert create_resp.status_code == 201
        source_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/mcp-sources/{source_id}",
            json={
                "name": "self-configuration",
                "type": "streamable-http",
                "config": _VALID_STREAMABLE_HTTP_CONFIG,
            },
        )
        assert resp.status_code == 409

    async def test_ordinary_name_unaffected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "self-configuration-but-different",
                "type": "streamable-http",
                "config": _VALID_STREAMABLE_HTTP_CONFIG,
            },
        )
        assert resp.status_code == 201


# ── AC11 — lifecycle cascades ────────────────────────────────────────────


class TestLifecycleCascades:
    async def test_rename_cascades_marker_only_row_name_stays_constant(
        self, client: AsyncClient
    ) -> None:
        """LD7: the row's name is the constant shared by every agent's
        surface row — renaming the agent updates only the ownership
        marker; there is nothing left to rename on the row itself."""
        await _create_agent(client, "old-name-agent")
        await client.post("/api/agents/old-name-agent/self-configuration")
        agent = (await client.get("/api/agents/old-name-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        resp = await client.post(
            "/api/agents/old-name-agent/rename", json={"new_name": "new-name-agent"}
        )
        assert resp.status_code == 200

        row = (await client.get(f"/api/mcp-sources/{source_id}")).json()
        assert row["config"]["self_configuration"] == {"agent": "new-name-agent"}
        assert row["name"] == "self-configuration"

        status = (await client.get("/api/agents/new-name-agent/self-configuration")).json()
        assert status["enabled"] is True

    async def test_delete_agent_removes_row_and_unregisters_credential(
        self, client: AsyncClient
    ) -> None:
        await _create_agent(client, "doomed-agent")
        await client.post("/api/agents/doomed-agent/self-configuration")
        agent = (await client.get("/api/agents/doomed-agent")).json()
        source_id = agent["mcp_source_ids"][0]
        identifier = next(iter(sc_credentials._registry.keys()))

        resp = await client.delete("/api/agents/doomed-agent")
        assert resp.status_code == 200

        assert sc_credentials.source_id_for(identifier) is None
        get_resp = await client.get(f"/api/mcp-sources/{source_id}")
        assert get_resp.status_code == 404

    async def test_reconcile_on_startup_rewrites_stale_url_and_loads_registry(
        self, client: AsyncClient
    ) -> None:
        from the_one.config import settings
        from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
        from the_one.interfaces.web import api as api_module
        from the_one.self_configuration import manage

        await _create_agent(client, "reconcile-agent")
        await client.post("/api/agents/reconcile-agent/self-configuration")
        agent = (await client.get("/api/agents/reconcile-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        # Simulate a stale port: directly corrupt the persisted URL and
        # wipe the in-memory registry (as if this were a fresh process
        # that just booted with a different settings.port than last run).
        # `api_module.get_connection`/`get_encryptor` resolve to the SAME
        # patched test-isolated connection/encryptor the `client` fixture
        # installed (the patch is still active — this test runs inside the
        # fixture's `with patch(...)` scope).
        conn = await api_module.get_connection()
        encryptor = api_module.get_encryptor(settings.data_dir)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        agent_store = SQLiteAgentStore(conn, encryptor)
        row = await mcp_repo.get(source_id)
        stale_config = dict(row.config)
        stale_config["url"] = "http://127.0.0.1:1/mcp/self-configuration/"
        await mcp_repo.update(row.model_copy(update={"config": stale_config}))
        sc_credentials.clear_for_test()
        assert sc_credentials.source_id_for("anything") is None

        await manage.reconcile_on_startup(mcp_repo, agent_store)

        reconciled = await mcp_repo.get(source_id)
        assert reconciled.config["url"] == manage.surface_url()
        assert len(sc_credentials._registry) == 1

    async def test_reconcile_refreshes_cache_tools_for_every_marked_row(
        self, client: AsyncClient
    ) -> None:
        """AC8: a row enabled before this leg's write tools landed lists
        four tools after a reconcile — not just two — even though its URL
        did not change."""
        from the_one.config import settings
        from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
        from the_one.interfaces.web import api as api_module
        from the_one.self_configuration import manage

        await _create_agent(client, "cache-refresh-agent")
        await client.post("/api/agents/cache-refresh-agent/self-configuration")
        agent = (await client.get("/api/agents/cache-refresh-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        conn = await api_module.get_connection()
        encryptor = api_module.get_encryptor(settings.data_dir)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        agent_store = SQLiteAgentStore(conn, encryptor)

        # Simulate a Leg-2-era row: only the two read tools cached.
        row = await mcp_repo.get(source_id)
        stale_config = dict(row.config)
        stale_cache = dict(stale_config["_cache"])
        stale_cache["tools"] = [
            t
            for t in stale_cache["tools"]
            if t["name"] in {"get_my_configuration", "describe_my_capabilities"}
        ]
        stale_config["_cache"] = stale_cache
        await mcp_repo.update(row.model_copy(update={"config": stale_config}))

        await manage.reconcile_on_startup(mcp_repo, agent_store)

        reconciled = await mcp_repo.get(source_id)
        tool_names = {t["name"] for t in reconciled.config["_cache"]["tools"]}
        assert tool_names == {
            "get_my_configuration",
            "describe_my_capabilities",
            "update_my_description",
            "update_my_system_prompt",
        }

    async def test_reconcile_renames_legacy_row_and_migrates_override_key(
        self, client: AsyncClient
    ) -> None:
        """LD7: a row created under Leg 2's per-agent-name template is
        renamed to the constant on reconcile, and the owner's per-tool
        `mcp_overrides` entry keyed by the OLD name is migrated to the
        constant key so checkboxes set before this leg survive."""
        from the_one.config import settings
        from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
        from the_one.interfaces.web import api as api_module
        from the_one.self_configuration import manage

        await _create_agent(client, "legacy-agent")
        await client.post("/api/agents/legacy-agent/self-configuration")
        agent = (await client.get("/api/agents/legacy-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        conn = await api_module.get_connection()
        encryptor = api_module.get_encryptor(settings.data_dir)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        agent_store = SQLiteAgentStore(conn, encryptor)

        legacy_name = "self-configuration (legacy-agent)"
        row = await mcp_repo.get(source_id)
        await mcp_repo.update(row.model_copy(update={"name": legacy_name}))

        cfg = await agent_store.load("legacy-agent")
        await agent_store.save(
            cfg.model_copy(
                update={
                    "mcp_overrides": {legacy_name: {"disabled_tools": ["describe_my_capabilities"]}}
                }
            )
        )

        await manage.reconcile_on_startup(mcp_repo, agent_store)

        reconciled = await mcp_repo.get(source_id)
        assert reconciled.name == manage.SURFACE_ROW_NAME

        migrated_cfg = await agent_store.load("legacy-agent")
        assert migrated_cfg.mcp_overrides == {
            manage.SURFACE_ROW_NAME: {"disabled_tools": ["describe_my_capabilities"]}
        }

    async def test_reconcile_skips_migration_when_constant_key_already_taken(
        self, client: AsyncClient
    ) -> None:
        """LD7's skip-and-log branch: a legacy row is still renamed, but a
        pre-existing override entry under the constant key is never
        clobbered by the migration."""
        from the_one.config import settings
        from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
        from the_one.interfaces.web import api as api_module
        from the_one.self_configuration import manage

        await _create_agent(client, "collide-agent")
        await client.post("/api/agents/collide-agent/self-configuration")
        agent = (await client.get("/api/agents/collide-agent")).json()
        source_id = agent["mcp_source_ids"][0]

        conn = await api_module.get_connection()
        encryptor = api_module.get_encryptor(settings.data_dir)
        mcp_repo = MCPSourceRepository(conn, encryptor)
        agent_store = SQLiteAgentStore(conn, encryptor)

        legacy_name = "self-configuration (collide-agent)"
        row = await mcp_repo.get(source_id)
        await mcp_repo.update(row.model_copy(update={"name": legacy_name}))

        cfg = await agent_store.load("collide-agent")
        await agent_store.save(
            cfg.model_copy(
                update={
                    "mcp_overrides": {
                        legacy_name: {"disabled_tools": ["describe_my_capabilities"]},
                        manage.SURFACE_ROW_NAME: {"disabled_tools": ["update_my_system_prompt"]},
                    }
                }
            )
        )

        await manage.reconcile_on_startup(mcp_repo, agent_store)

        reconciled = await mcp_repo.get(source_id)
        assert reconciled.name == manage.SURFACE_ROW_NAME

        after_cfg = await agent_store.load("collide-agent")
        assert after_cfg.mcp_overrides[manage.SURFACE_ROW_NAME] == {
            "disabled_tools": ["update_my_system_prompt"]
        }
        assert after_cfg.mcp_overrides[legacy_name] == {
            "disabled_tools": ["describe_my_capabilities"]
        }

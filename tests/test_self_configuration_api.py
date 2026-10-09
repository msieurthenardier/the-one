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

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.api_credential import resolve_caller
from the_one.db.models import now_iso
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
    conn = await connect_template_db(db_path)

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
        assert resp.json() == {"enabled": False, "requires_approval": False}

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
            "requires_approval": False,
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
        assert re_enabled == {
            "enabled": True,
            "source_id": source_id,
            "requires_approval": False,
        }

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
        assert status == {"enabled": False, "requires_approval": False}


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


# ── M21 F02 L02 — approval mode + revision queue endpoints ────────────────


async def _revisions_repo_for(client: AsyncClient):
    """Build an AgentRevisionRepository against the same patched test conn
    the `client` fixture installed (patch still active in-scope)."""
    from the_one.db.repositories import AgentRevisionRepository
    from the_one.interfaces.web import api as api_module

    conn = await api_module.get_connection()
    return AgentRevisionRepository(conn)


async def _seed_pending(client, agent, field, proposed, base):
    repo = await _revisions_repo_for(client)
    rev, _ = await repo.upsert_pending_revision(
        agent_name=agent, field=field, proposed_value=proposed, base_value=base
    )
    return rev


class TestApprovalModeEndpoint:
    async def test_put_approval_mode_persists(self, client: AsyncClient) -> None:
        # AC8/AC13 — PUT toggles the flag; status reflects it.
        await _create_agent(client, "am1")
        resp = await client.put(
            "/api/agents/am1/self-configuration/approval-mode",
            json={"requires_approval": True},
        )
        assert resp.status_code == 200
        assert resp.json() == {"requires_approval": True}
        status = (await client.get("/api/agents/am1/self-configuration")).json()
        assert status["requires_approval"] is True

        # Flip back off.
        resp = await client.put(
            "/api/agents/am1/self-configuration/approval-mode",
            json={"requires_approval": False},
        )
        assert resp.json() == {"requires_approval": False}

    async def test_put_approval_mode_unknown_agent_404(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/agents/ghost/self-configuration/approval-mode",
            json={"requires_approval": True},
        )
        assert resp.status_code == 404

    async def test_unrelated_agent_save_preserves_approval_mode(self, client: AsyncClient) -> None:
        # AC3 (DD2 HIGH) — a PUT /api/agents/{name} that omits the field must
        # not reset approval mode.
        await _create_agent(client, "am2")
        await client.put(
            "/api/agents/am2/self-configuration/approval-mode",
            json={"requires_approval": True},
        )
        # An unrelated Studio-style save (payload omits the flag).
        resp = await client.put(
            "/api/agents/am2", json={"name": "am2", "description": "edited desc"}
        )
        assert resp.status_code == 200
        status = (await client.get("/api/agents/am2/self-configuration")).json()
        assert status["requires_approval"] is True


class TestRevisionQueueEndpoints:
    async def test_pending_count_scoped(self, client: AsyncClient) -> None:
        # AC8 — count scoped to the agent.
        await _create_agent(client, "rq1")
        await _create_agent(client, "rq2")
        await _seed_pending(client, "rq1", "description", "p1", "b1")
        await _seed_pending(client, "rq1", "system_prompt", "p2", "b2")
        await _seed_pending(client, "rq2", "description", "p3", "b3")
        assert (
            await client.get("/api/agents/rq1/self-configuration/revisions/pending-count")
        ).json() == {"count": 2}
        assert (
            await client.get("/api/agents/rq2/self-configuration/revisions/pending-count")
        ).json() == {"count": 1}

    async def test_list_revisions_returns_full_rows(self, client: AsyncClient) -> None:
        # AC8 — full non-secret rows with base/proposed visible.
        await _create_agent(client, "rq3")
        await _seed_pending(client, "rq3", "description", "proposed", "base")
        rows = (await client.get("/api/agents/rq3/self-configuration/revisions")).json()
        assert len(rows) == 1
        assert rows[0]["base_value"] == "base"
        assert rows[0]["proposed_value"] == "proposed"
        assert rows[0]["status"] == "pending"

    async def test_list_and_count_unknown_agent_404(self, client: AsyncClient) -> None:
        assert (
            await client.get("/api/agents/ghost/self-configuration/revisions")
        ).status_code == 404
        assert (
            await client.get("/api/agents/ghost/self-configuration/revisions/pending-count")
        ).status_code == 404


class TestDismissEndpoint:
    async def test_dismiss_transitions_and_idempotent(self, client: AsyncClient) -> None:
        # AC9
        await _create_agent(client, "dm1")
        rev = await _seed_pending(client, "dm1", "description", "p", "b")
        resp = await client.post(f"/api/agents/dm1/self-configuration/revisions/{rev.id}/dismiss")
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"
        # Idempotent.
        resp2 = await client.post(f"/api/agents/dm1/self-configuration/revisions/{rev.id}/dismiss")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "dismissed"

    async def test_dismiss_unknown_id_404(self, client: AsyncClient) -> None:
        await _create_agent(client, "dm2")
        resp = await client.post("/api/agents/dm2/self-configuration/revisions/nope/dismiss")
        assert resp.status_code == 404

    async def test_dismiss_cross_id_404(self, client: AsyncClient) -> None:
        # AC9 — a revision id whose agent_name != path {name} is a 404.
        await _create_agent(client, "dm3")
        await _create_agent(client, "dm4")
        rev = await _seed_pending(client, "dm4", "description", "p", "b")
        resp = await client.post(f"/api/agents/dm3/self-configuration/revisions/{rev.id}/dismiss")
        assert resp.status_code == 404

    async def test_dismiss_applied_row_409(self, client: AsyncClient) -> None:
        await _create_agent(client, "dm5")
        rev = await _seed_pending(client, "dm5", "description", "p", "b")
        repo = await _revisions_repo_for(client)
        await repo.mark_applied(rev.id)
        resp = await client.post(f"/api/agents/dm5/self-configuration/revisions/{rev.id}/dismiss")
        assert resp.status_code == 409


class TestApproveEndpoint:
    async def test_clean_approve_applies_and_transitions(self, client: AsyncClient) -> None:
        # AC10 — base_value == current stored value → apply.
        await _create_agent(client, "ap1")
        # current description is "test agent" (from _create_agent).
        rev = await _seed_pending(client, "ap1", "description", "approved desc", "test agent")
        resp = await client.post(f"/api/agents/ap1/self-configuration/revisions/{rev.id}/approve")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "applied"
        assert resp.json()["resolved_at"] is not None
        # The change reached the stored config (persist path).
        agent = (await client.get("/api/agents/ap1")).json()
        assert agent["description"] == "approved desc"

    async def test_approve_idempotent_on_applied(self, client: AsyncClient) -> None:
        # AC10 — idempotent no-op on already-applied.
        await _create_agent(client, "ap2")
        rev = await _seed_pending(client, "ap2", "description", "x", "test agent")
        await client.post(f"/api/agents/ap2/self-configuration/revisions/{rev.id}/approve")
        resp = await client.post(f"/api/agents/ap2/self-configuration/revisions/{rev.id}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    async def test_approve_dismissed_409(self, client: AsyncClient) -> None:
        await _create_agent(client, "ap3")
        rev = await _seed_pending(client, "ap3", "description", "x", "test agent")
        repo = await _revisions_repo_for(client)
        await repo.mark_dismissed(rev.id)
        resp = await client.post(f"/api/agents/ap3/self-configuration/revisions/{rev.id}/approve")
        assert resp.status_code == 409

    async def test_approve_cross_id_and_unknown_404(self, client: AsyncClient) -> None:
        await _create_agent(client, "ap4")
        await _create_agent(client, "ap4b")
        rev = await _seed_pending(client, "ap4b", "description", "x", "test agent")
        assert (
            await client.post(f"/api/agents/ap4/self-configuration/revisions/{rev.id}/approve")
        ).status_code == 404
        assert (
            await client.post("/api/agents/ap4/self-configuration/revisions/nope/approve")
        ).status_code == 404

    async def test_stale_approve_409_with_both_values(self, client: AsyncClient) -> None:
        # AC11 — base_value != current stored value → 409, store untouched.
        await _create_agent(client, "ap5")
        # Seed with a stale base that differs from the current "test agent".
        rev = await _seed_pending(client, "ap5", "description", "proposed", "STALE BASE")
        resp = await client.post(f"/api/agents/ap5/self-configuration/revisions/{rev.id}/approve")
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["current_value"] == "test agent"
        assert detail["proposed_value"] == "proposed"
        assert detail["base_value"] == "STALE BASE"
        # Store untouched; row still pending.
        agent = (await client.get("/api/agents/ap5")).json()
        assert agent["description"] == "test agent"
        repo = await _revisions_repo_for(client)
        assert (await repo.get(rev.id)).status == "pending"

    async def test_override_reapproves_stale(self, client: AsyncClient) -> None:
        # AC11 — override re-captures base_value and applies.
        await _create_agent(client, "ap6")
        rev = await _seed_pending(client, "ap6", "description", "forced", "STALE BASE")
        resp = await client.post(
            f"/api/agents/ap6/self-configuration/revisions/{rev.id}/approve",
            params={"override": "true"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "applied"
        assert resp.json()["base_value"] == "test agent"  # re-captured to current
        agent = (await client.get("/api/agents/ap6")).json()
        assert agent["description"] == "forced"


class TestDisableSupersedes:
    async def test_disable_supersedes_pending_and_blocks_approve(self, client: AsyncClient) -> None:
        # AC12 (DD8) — disable marks pending rows superseded even when there
        # is no surface row; a follow-up approve is 409.
        await _create_agent(client, "sup1")
        rev = await _seed_pending(client, "sup1", "description", "p", "test agent")
        # No surface enabled — disable still clears the queue.
        resp = await client.delete("/api/agents/sup1/self-configuration")
        assert resp.status_code == 200
        repo = await _revisions_repo_for(client)
        assert (await repo.get(rev.id)).status == "superseded"
        # Approve now 409.
        resp = await client.post(f"/api/agents/sup1/self-configuration/revisions/{rev.id}/approve")
        assert resp.status_code == 409


async def _seed_applied(client, agent, field, proposed, base):
    """Seed an ``applied``/``self`` revision row directly (a value the field
    genuinely held) — the restore target shape. Does NOT mutate the agent
    config; callers set the config's current value via PUT as needed."""
    repo = await _revisions_repo_for(client)
    return await repo.append(
        agent_name=agent,
        field=field,
        proposed_value=proposed,
        base_value=base,
        source="self",
        status="applied",
        created_at=now_iso(),
        resolved_at=now_iso(),
    )


class TestRestoreEndpoint:
    async def test_restore_proposed_applies_and_logs_provenance(self, client: AsyncClient) -> None:
        # AC1 — default side=proposed: set field to the target's proposed_value,
        # append a new applied/restore row with base_value = pre-restore current.
        await _create_agent(client, "rs1")
        await client.put("/api/agents/rs1", json={"name": "rs1", "description": "CURRENT"})
        rev = await _seed_applied(client, "rs1", "description", "REINSTATED", "OLDER")
        resp = await client.post(f"/api/agents/rs1/self-configuration/revisions/{rev.id}/restore")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source"] == "restore"
        assert body["status"] == "applied"
        assert body["field"] == "description"
        assert body["proposed_value"] == "REINSTATED"
        assert body["base_value"] == "CURRENT"  # pre-restore current value
        assert body["restored_from"] == rev.id
        assert body["resolved_at"] == body["created_at"]
        # Store now holds the reinstated value.
        agent = (await client.get("/api/agents/rs1")).json()
        assert agent["description"] == "REINSTATED"

    async def test_restore_base_reaches_original(self, client: AsyncClient) -> None:
        # AC1b (LD2) — side=base on the earliest applied revision of a field
        # returns it to its ORIGINAL pre-first-revision value. Agent created
        # with description D0, approval OFF so the D0->D1 self-revision is an
        # applied row; the config now holds D1. Restore side=base → D0.
        await _create_agent(client, "rs1b")
        await client.put("/api/agents/rs1b", json={"name": "rs1b", "description": "D0"})
        rev = await _seed_applied(client, "rs1b", "description", "D1", "D0")
        await client.put("/api/agents/rs1b", json={"name": "rs1b", "description": "D1"})
        resp = await client.post(
            f"/api/agents/rs1b/self-configuration/revisions/{rev.id}/restore",
            params={"side": "base"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["proposed_value"] == "D0"  # reinstated = the before-image
        assert body["base_value"] == "D1"  # pre-restore current
        assert body["restored_from"] == rev.id
        # restored_from resolves to an existing revision.
        repo = await _revisions_repo_for(client)
        assert (await repo.get(body["restored_from"])).id == rev.id
        agent = (await client.get("/api/agents/rs1b")).json()
        assert agent["description"] == "D0"

    async def test_restore_applies_under_approval_mode_on(self, client: AsyncClient) -> None:
        # AC2 (DD5) — approval mode ON does not enqueue a restore; it applies.
        await _create_agent(client, "rs2")
        await client.put(
            "/api/agents/rs2/self-configuration/approval-mode",
            json={"requires_approval": True},
        )
        await client.put("/api/agents/rs2", json={"name": "rs2", "description": "NOW"})
        rev = await _seed_applied(client, "rs2", "description", "BACK", "prev")
        resp = await client.post(f"/api/agents/rs2/self-configuration/revisions/{rev.id}/restore")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "applied"
        agent = (await client.get("/api/agents/rs2")).json()
        assert agent["description"] == "BACK"
        # No pending row was created.
        count = (
            await client.get("/api/agents/rs2/self-configuration/revisions/pending-count")
        ).json()
        assert count == {"count": 0}

    @pytest.mark.parametrize("bad_status", ["pending", "dismissed", "superseded"])
    async def test_restore_non_applied_target_409_untouched(
        self, client: AsyncClient, bad_status: str
    ) -> None:
        # AC4 — a non-applied target is refused 409; store + log untouched.
        agent = f"rs4-{bad_status}"
        await _create_agent(client, agent)
        await client.put("/api/agents/" + agent, json={"name": agent, "description": "KEEP"})
        rev = await _seed_pending(client, agent, "description", "proposed", "base")
        repo = await _revisions_repo_for(client)
        if bad_status == "dismissed":
            await repo.mark_dismissed(rev.id)
        elif bad_status == "superseded":
            await repo.supersede_pending(agent)
        # (pending: leave as-is.)
        rows_before = await repo.list_for_agent(agent)
        resp = await client.post(
            f"/api/agents/{agent}/self-configuration/revisions/{rev.id}/restore"
        )
        assert resp.status_code == 409, resp.text
        # Store untouched.
        cfg = (await client.get("/api/agents/" + agent)).json()
        assert cfg["description"] == "KEEP"
        # Log untouched (no new restore row appended).
        rows_after = await repo.list_for_agent(agent)
        assert len(rows_after) == len(rows_before)

    async def test_restore_cross_id_and_unknown_404(self, client: AsyncClient) -> None:
        # AC5 — cross-ID (revision under agent B via agent A's path) → 404;
        # unknown id → 404.
        await _create_agent(client, "rs5a")
        await _create_agent(client, "rs5b")
        rev = await _seed_applied(client, "rs5b", "description", "x", "y")
        assert (
            await client.post(f"/api/agents/rs5a/self-configuration/revisions/{rev.id}/restore")
        ).status_code == 404
        assert (
            await client.post("/api/agents/rs5a/self-configuration/revisions/nope/restore")
        ).status_code == 404

    async def test_restore_bad_side_422(self, client: AsyncClient) -> None:
        # side is a Literal — an invalid value is auto-422'd by FastAPI.
        await _create_agent(client, "rs5c")
        rev = await _seed_applied(client, "rs5c", "description", "x", "y")
        resp = await client.post(
            f"/api/agents/rs5c/self-configuration/revisions/{rev.id}/restore",
            params={"side": "sideways"},
        )
        assert resp.status_code == 422

    async def test_restore_fields_are_independent(self, client: AsyncClient) -> None:
        # AC6 — restoring a description revision changes only description and
        # logs field='description'; the system prompt is untouched; vice versa.
        await _create_agent(client, "rs6")
        await client.put(
            "/api/agents/rs6",
            json={
                "name": "rs6",
                "description": "DESC_NOW",
                "system_prompt": "PROMPT_NOW",
            },
        )
        desc_rev = await _seed_applied(client, "rs6", "description", "DESC_BACK", "old_desc")
        prompt_rev = await _seed_applied(
            client, "rs6", "system_prompt", "PROMPT_BACK", "old_prompt"
        )
        # Restore description only.
        resp = await client.post(
            f"/api/agents/rs6/self-configuration/revisions/{desc_rev.id}/restore"
        )
        assert resp.status_code == 200
        assert resp.json()["field"] == "description"
        agent = (await client.get("/api/agents/rs6")).json()
        assert agent["description"] == "DESC_BACK"
        assert agent["system_prompt"] == "PROMPT_NOW"  # untouched
        # Restore system prompt only.
        resp = await client.post(
            f"/api/agents/rs6/self-configuration/revisions/{prompt_rev.id}/restore"
        )
        assert resp.status_code == 200
        assert resp.json()["field"] == "system_prompt"
        agent = (await client.get("/api/agents/rs6")).json()
        assert agent["system_prompt"] == "PROMPT_BACK"
        assert agent["description"] == "DESC_BACK"  # still the restored desc

    async def test_restore_to_current_still_logs(self, client: AsyncClient) -> None:
        # AC7 — restoring to a value equal to the current one still logs a
        # restore/applied row (not silently skipped). base==proposed is fine.
        await _create_agent(client, "rs7")
        await client.put("/api/agents/rs7", json={"name": "rs7", "description": "SAME"})
        rev = await _seed_applied(client, "rs7", "description", "SAME", "older")
        repo = await _revisions_repo_for(client)
        before = len(await repo.list_for_agent("rs7"))
        resp = await client.post(f"/api/agents/rs7/self-configuration/revisions/{rev.id}/restore")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "restore"
        assert body["base_value"] == "SAME"
        assert body["proposed_value"] == "SAME"
        after = len(await repo.list_for_agent("rs7"))
        assert after == before + 1

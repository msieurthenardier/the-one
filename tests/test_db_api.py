"""Tests for REST API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


@pytest.fixture
async def client(tmp_path):
    """Create a test client with an isolated DB and test encryptor."""
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    # Test encryptor — function-scoped (mirrors test_provider_api.py).
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
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


# ── Agent endpoints ───────────────────────────────────────────────────────


class TestAgentAPI:
    async def test_create_agent(self, client: AsyncClient) -> None:
        resp = await client.post("/api/agents", json={"name": "test-agent", "description": "Hi"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "test-agent"

    async def test_list_agents(self, client: AsyncClient) -> None:
        await client.post("/api/agents", json={"name": "a1"})
        await client.post("/api/agents", json={"name": "a2"})
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()]
        assert "a1" in names
        assert "a2" in names

    async def test_get_agent(self, client: AsyncClient) -> None:
        await client.post("/api/agents", json={"name": "test"})
        resp = await client.get("/api/agents/test")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test"

    async def test_get_agent_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/agents/nope")
        assert resp.status_code == 404

    async def test_update_agent(self, client: AsyncClient) -> None:
        await client.post("/api/agents", json={"name": "test"})
        resp = await client.put("/api/agents/test", json={"name": "test", "description": "updated"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated"

    async def test_delete_agent(self, client: AsyncClient) -> None:
        await client.post("/api/agents", json={"name": "test"})
        resp = await client.delete("/api/agents/test")
        assert resp.status_code == 200
        resp = await client.get("/api/agents/test")
        assert resp.status_code == 404

    async def test_get_agent_includes_tool_overrides_null_by_default(
        self, client: AsyncClient
    ) -> None:
        """An agent created without `tool_overrides` returns it as null
        in the GET payload (Decision 1 — locked-down NULL semantic)."""
        await client.post("/api/agents", json={"name": "default-overrides"})
        resp = await client.get("/api/agents/default-overrides")
        assert resp.status_code == 200
        body = resp.json()
        assert "tool_overrides" in body
        assert body["tool_overrides"] is None

    async def test_create_agent_with_tool_overrides_round_trips(self, client: AsyncClient) -> None:
        """POST with explicit `tool_overrides` dict → GET returns it
        unchanged."""
        payload = {
            "name": "with-overrides",
            "tool_overrides": {
                "shell": {"timeout": 30},
                "read_file": {"max_bytes": 1000},
            },
        }
        resp = await client.post("/api/agents", json=payload)
        assert resp.status_code == 201

        resp = await client.get("/api/agents/with-overrides")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_overrides"] == payload["tool_overrides"]

    async def test_create_agent_with_outer_non_dict_tool_overrides_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST with `tool_overrides=[1,2,3]` (a list) raises 422
        Pydantic validation error."""
        resp = await client.post(
            "/api/agents",
            json={"name": "bad-outer", "tool_overrides": [1, 2, 3]},
        )
        assert resp.status_code == 422

    async def test_create_agent_with_inner_non_dict_tool_overrides_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST with `tool_overrides={"shell": "not-a-dict"}` raises 422
        — proves dict[str, Any] inner type validates inner is a dict
        (bare `dict` would silently accept this)."""
        resp = await client.post(
            "/api/agents",
            json={"name": "bad-inner", "tool_overrides": {"shell": "not-a-dict"}},
        )
        assert resp.status_code == 422

    async def test_create_agent_persists_connector_always_listen(
        self, client: AsyncClient
    ) -> None:
        """POST with ``connector_always_listen`` round-trips through GET.

        M11 F7 L6: confirms the new per-agent toggle field flows through
        the API layer without any api.py change (Pydantic
        ``model_validate`` picks up the field automatically and
        ``cfg.model_dump()`` round-trips it in the response).
        """
        payload = {
            "name": "always-listen-agent",
            "connector_always_listen": {"acct-a": True, "acct-b": False},
        }
        resp = await client.post("/api/agents", json=payload)
        assert resp.status_code == 201
        assert resp.json()["connector_always_listen"] == {
            "acct-a": True,
            "acct-b": False,
        }

        # GET round-trips the field unchanged (proves the value persisted
        # to the DB and decoded back through _row_to_config).
        resp = await client.get("/api/agents/always-listen-agent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connector_always_listen"] == {
            "acct-a": True,
            "acct-b": False,
        }

    async def test_update_agent_clears_connector_always_listen(
        self, client: AsyncClient
    ) -> None:
        """PUT with ``connector_always_listen=None`` clears the field.

        Confirms the upsert path's ``ON CONFLICT(name) DO UPDATE SET ...
        connector_always_listen=excluded.connector_always_listen`` clause
        actually overwrites the original value (the cycle-1 review's
        specific bug shape — a missing SET clause silently retains the
        original).
        """
        # Step 1: create with toggle set.
        resp = await client.post(
            "/api/agents",
            json={
                "name": "clear-target",
                "connector_always_listen": {"acct-a": True},
            },
        )
        assert resp.status_code == 201
        assert resp.json()["connector_always_listen"] == {"acct-a": True}

        # Step 2: PUT with the field explicitly None — should clear it.
        resp = await client.put(
            "/api/agents/clear-target",
            json={"name": "clear-target", "connector_always_listen": None},
        )
        assert resp.status_code == 200
        assert resp.json()["connector_always_listen"] is None

        # Step 3: GET confirms the field is cleared in the DB.
        resp = await client.get("/api/agents/clear-target")
        assert resp.status_code == 200
        assert resp.json()["connector_always_listen"] is None


# ── Knowledge base endpoints ─────────────────────────────────────────────


class TestKnowledgeBaseAPI:
    async def test_crud(self, client: AsyncClient) -> None:
        # Create
        resp = await client.post("/api/knowledge-bases", json={"name": "My KB"})
        assert resp.status_code == 201
        kb_id = resp.json()["id"]

        # Read
        resp = await client.get(f"/api/knowledge-bases/{kb_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "My KB"

        # Update
        resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "Updated KB"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated KB"

        # List
        resp = await client.get("/api/knowledge-bases")
        assert len(resp.json()) == 1

        # Delete
        resp = await client.delete(f"/api/knowledge-bases/{kb_id}")
        assert resp.status_code == 200
        resp = await client.get(f"/api/knowledge-bases/{kb_id}")
        assert resp.status_code == 404

    async def test_kb_items(self, client: AsyncClient) -> None:
        # Create KB
        resp = await client.post("/api/knowledge-bases", json={"name": "KB"})
        kb_id = resp.json()["id"]

        # Add item
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "file", "path_or_url": "/tmp/test.txt"},
        )
        assert resp.status_code == 201
        item_id = resp.json()["id"]

        # List items
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items")
        assert len(resp.json()) == 1

        # Delete item
        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/{item_id}")
        assert resp.status_code == 200


# ── MCP source endpoints ─────────────────────────────────────────────────


class TestMCPSourceAPI:
    async def test_crud(self, client: AsyncClient) -> None:
        # Create
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "Test MCP", "type": "stdio", "config": {"command": "python"}},
        )
        assert resp.status_code == 201
        source_id = resp.json()["id"]

        # Read
        resp = await client.get(f"/api/mcp-sources/{source_id}")
        assert resp.status_code == 200
        assert resp.json()["config"]["command"] == "python"
        # Post-L3 default-empty-secrets contract baseline: empty POST body
        # secrets defaults to {} on the model and surfaces unchanged in the
        # masked response shape.
        assert resp.json()["secrets"] == {}

        # Update
        resp = await client.put(f"/api/mcp-sources/{source_id}", json={"name": "Updated"})
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(f"/api/mcp-sources/{source_id}")
        assert resp.status_code == 200

    async def test_list_returns_masked_secrets(self, client: AsyncClient) -> None:
        """GET /api/mcp-sources masks secret values per-key."""
        await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "github-mcp"},
                "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
            },
        )
        resp = await client.get("/api/mcp-sources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        # per-decoded-value mask: ***...{tail4} for long values
        assert data[0]["secrets"]["GITHUB_TOKEN"] == "***...alue"
        # plaintext config passes through unchanged
        assert data[0]["config"]["command"] == "github-mcp"
        # raw plaintext does not appear anywhere in the response
        assert "ghp_realsecretvalue" not in resp.text

    async def test_get_returns_masked_secrets(self, client: AsyncClient) -> None:
        """GET /api/mcp-sources/{id} masks secret values per-key."""
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "abc"},  # short value: masks as ***
            },
        )
        sid = create.json()["id"]
        resp = await client.get(f"/api/mcp-sources/{sid}")
        assert resp.status_code == 200
        assert resp.json()["secrets"]["K"] == "***"
        # Mirror the plaintext-not-in-response assertion from the list test
        assert "abc" not in resp.json()["secrets"]["K"]

    async def test_put_masked_sentinel_preserves_secret(self, client: AsyncClient) -> None:
        """PUT with secrets[key]='__MASKED__' preserves the stored value."""
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
            },
        )
        sid = create.json()["id"]
        await client.put(
            f"/api/mcp-sources/{sid}",
            json={
                "name": "GH-renamed",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"GITHUB_TOKEN": "__MASKED__"},
            },
        )
        # The masked tail (***...alue) confirms the stored ciphertext still
        # decrypts to the original "ghp_realsecretvalue" — preservation
        # round-trip locked without needing a back-channel into the repo.
        resp = await client.get(f"/api/mcp-sources/{sid}")
        assert resp.json()["secrets"]["GITHUB_TOKEN"] == "***...alue"
        assert resp.json()["name"] == "GH-renamed"
        # Belt-and-braces: raw plaintext does not appear in the response
        assert "ghp_realsecretvalue" not in resp.text

    async def test_put_drops_omitted_secret_key(self, client: AsyncClient) -> None:
        """PUT with secrets={} drops all stored secret keys (REST replace)."""
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
            },
        )
        sid = create.json()["id"]
        await client.put(
            f"/api/mcp-sources/{sid}",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {},
            },
        )
        resp = await client.get(f"/api/mcp-sources/{sid}")
        assert resp.json()["secrets"] == {}

    async def test_validation_rejects_stdio_missing_command(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "X", "type": "stdio", "config": {}, "secrets": {}},
        )
        assert resp.status_code == 422
        assert "config.command" in resp.json()["detail"]

    async def test_validation_rejects_streamable_http_missing_url(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "X", "type": "streamable-http", "config": {}, "secrets": {}},
        )
        assert resp.status_code == 422
        assert "config.url" in resp.json()["detail"]

    async def test_validation_rejects_unknown_transport_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "X", "type": "websocket", "config": {}, "secrets": {}},
        )
        assert resp.status_code == 422  # Pydantic Literal rejection

    async def test_validation_rejects_stdio_config_env_non_string_value(
        self, client: AsyncClient
    ) -> None:
        """L1: F1 API validator extended to reject non-string env values."""
        resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "test-stdio-bad-env",
                "type": "stdio",
                "config": {"command": "echo", "env": {"FOO": 42}},
                "secrets": {},
            },
        )
        assert resp.status_code == 422
        assert "config.env" in resp.json()["detail"]

    async def test_validation_rejects_stdio_config_env_non_dict(self, client: AsyncClient) -> None:
        """L1: F1 API validator extended to reject non-dict env."""
        resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "test-stdio-bad-env-2",
                "type": "stdio",
                "config": {"command": "echo", "env": "not-a-dict"},
                "secrets": {},
            },
        )
        assert resp.status_code == 422
        assert "config.env" in resp.json()["detail"]

    async def test_validation_rejects_stdio_config_sandbox_writable_paths_non_string_entry(
        self, client: AsyncClient
    ) -> None:
        """L1b: F1 API validator extended for config.sandbox sub-block per F3 §4."""
        resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "test-stdio-bad-sandbox-writable",
                "type": "stdio",
                "config": {"command": "echo", "sandbox": {"writable_paths": ["/data", 42]}},
                "secrets": {},
            },
        )
        assert resp.status_code == 422
        assert "config.sandbox.writable_paths" in resp.json()["detail"]

    async def test_validation_rejects_stdio_config_sandbox_network_allowed_non_bool(
        self, client: AsyncClient
    ) -> None:
        """L1b: F1 API validator extended for config.sandbox sub-block per F3 §4."""
        resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "test-stdio-bad-sandbox-network",
                "type": "stdio",
                "config": {"command": "echo", "sandbox": {"network_allowed": "yes"}},
                "secrets": {},
            },
        )
        assert resp.status_code == 422
        assert "config.sandbox.network_allowed" in resp.json()["detail"]

    async def test_validation_accepts_stdio_config_empty_sandbox_dict(
        self, client: AsyncClient
    ) -> None:
        """L1b: empty sandbox dict is valid — both writable_paths and network_allowed optional."""
        resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "test-stdio-empty-sandbox",
                "type": "stdio",
                "config": {"command": "echo", "sandbox": {}},
                "secrets": {},
            },
        )
        assert resp.status_code in (200, 201)

    async def test_types_endpoint_returns_two_transports(self, client: AsyncClient) -> None:
        resp = await client.get("/api/mcp-sources/types")
        assert resp.status_code == 200
        data = resp.json()
        assert {entry["value"] for entry in data} == {"stdio", "streamable-http"}
        assert all("label" in entry for entry in data)

    async def test_types_endpoint_route_order_does_not_collide_with_get_by_id(
        self, client: AsyncClient
    ) -> None:
        """Locks the route ordering invariant.

        If `/types` were registered AFTER `/{source_id}`, a GET to /types
        would resolve to get_mcp_source(source_id='types') and return 404.
        This test ensures the ordering stays correct.
        """
        resp = await client.get("/api/mcp-sources/types")
        assert resp.status_code == 200
        # If the order regresses we'd get 404 with the get_mcp_source
        # detail format
        assert "MCP source not found" not in resp.text

    async def test_put_transport_type_switch_revalidates_config(self, client: AsyncClient) -> None:
        """Switching type=stdio→streamable-http with stale config 422s.

        A PUT that flips the transport literal but keeps the old config
        shape (e.g., command-only) must be rejected at the validation
        helper because the merged result lacks the new transport's
        required fields. Locks that the helper runs on the merged
        post-copy state, not just the request body, and that operators
        get a clear 422 instead of a half-migrated source.
        """
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {},
            },
        )
        sid = create.json()["id"]
        resp = await client.put(
            f"/api/mcp-sources/{sid}",
            json={"type": "streamable-http"},  # config still has only command
        )
        assert resp.status_code == 422
        assert "config.url" in resp.json()["detail"]


# ── Connector account endpoints ──────────────────────────────────────────


class TestConnectorAPI:
    """REST surface for connector accounts (F2 L3).

    Mirrors :class:`TestMCPSourceAPI` shape; the eviction tests register
    the F1 stub plugin, acquire a warm pool entry, run the operation
    under test, and assert the pool state matches the
    no-op / eviction expectation per the leg's design decisions.
    """

    @pytest.fixture(autouse=True)
    async def _isolation(self, client: AsyncClient, monkeypatch):
        """Reset connector pool + registry + StubPlugin class-state per test.

        The autouse fixture in ``tests/test_connectors_pool.py`` is
        module-local and does NOT propagate here. Without this reset,
        prior-test ``_pool`` entries, registry registrations, or
        ``StubPlugin.connect_should_fail`` flags poison later tests.

        Pre-registers the stub so eviction tests can acquire warm
        entries directly; the one types-empty test calls
        :func:`clear_for_test` inside the test body to invert.

        Patches :func:`the_one.connectors._pool._load_account` to route
        through the same test-isolated connection + encryptor the API
        client uses — without this, the pool's function-local
        ``get_connection()`` import would resolve the production
        singleton instead of the function-scoped per-test SQLite, so
        ``acquire(...)`` would see no rows. The ``client`` fixture
        dependency is intentional: it forces the ``patch`` context
        managers inside ``client`` to be active during the autouse
        setup, exposing the patched ``get_connection`` /
        ``get_encryptor`` to this helper.
        """
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.registry import (
            clear_for_test,
            register_for_test,
            restore_to_baseline_for_test,
        )
        from the_one.db.repositories import ConnectorRepository
        from the_one.interfaces.web.api import get_connection, get_encryptor

        await pool_mod._clear_for_test()
        restore_to_baseline_for_test()
        StubPlugin.reset_for_test()
        register_for_test("stub", StubPlugin)

        async def _patched_load_account(account_id, encryptor):
            # The pool's production ``_load_account`` calls
            # ``get_connection()`` from ``the_one.db.connection`` (the
            # singleton). Tests patch the api module's view of those
            # globals; reuse them here so the pool sees the same
            # function-scoped SQLite + test encryptor the API just
            # wrote into.
            conn = await get_connection()
            repo = ConnectorRepository(conn, get_encryptor(""))
            return await repo.get(account_id)

        monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)

        try:
            yield
        finally:
            await pool_mod._clear_for_test()
            clear_for_test()

    async def test_crud_round_trip(self, client: AsyncClient) -> None:
        """POST → GET → PUT → DELETE round-trip with idle_timeout_seconds."""
        # Create
        resp = await client.post(
            "/api/connectors",
            json={
                "name": "Bot 1",
                "type": "stub",
                "config": {"workspace": "demo"},
                "idle_timeout_seconds": 600,
            },
        )
        assert resp.status_code == 201
        account_id = resp.json()["id"]
        assert resp.json()["idle_timeout_seconds"] == 600

        # Read
        resp = await client.get(f"/api/connectors/{account_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Bot 1"
        assert resp.json()["config"]["workspace"] == "demo"
        assert resp.json()["idle_timeout_seconds"] == 600
        # Empty-secrets baseline mirrors the MCP precedent.
        assert resp.json()["secrets"] == {}

        # Update
        resp = await client.put(
            f"/api/connectors/{account_id}",
            json={"name": "Bot 1 renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Bot 1 renamed"

        # Delete
        resp = await client.delete(f"/api/connectors/{account_id}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        resp = await client.get(f"/api/connectors/{account_id}")
        assert resp.status_code == 404

    async def test_list_returns_masked_secrets(self, client: AsyncClient) -> None:
        """GET /api/connectors masks secret values per-key."""
        await client.post(
            "/api/connectors",
            json={
                "name": "Discord Bot",
                "type": "stub",
                "config": {},
                "secrets": {"BOT_TOKEN": "secret_real_value"},
            },
        )
        resp = await client.get("/api/connectors")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["secrets"]["BOT_TOKEN"] == "***...alue"
        assert "secret_real_value" not in resp.text

    async def test_put_masked_sentinel_preserves_secret(
        self, client: AsyncClient
    ) -> None:
        """PUT with secrets[key]='__MASKED__' preserves the stored value."""
        create = await client.post(
            "/api/connectors",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "secret_real_value"},
            },
        )
        account_id = create.json()["id"]
        await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "Bot renamed",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "__MASKED__"},
            },
        )
        # ***...alue confirms the stored ciphertext still decrypts to the
        # original "secret_real_value".
        resp = await client.get(f"/api/connectors/{account_id}")
        assert resp.json()["secrets"]["BOT_TOKEN"] == "***...alue"
        assert resp.json()["name"] == "Bot renamed"
        assert "secret_real_value" not in resp.text

    async def test_no_op_put_does_not_evict(self, client: AsyncClient) -> None:
        """No-op all-masked PUT MUST NOT evict the warm pool entry.

        Every secret round-trips as ``__MASKED__`` and resolves back to
        the existing stored values; ``existing.secrets == resolved_secrets``
        and eviction is skipped.
        """
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import agent_acquire

        create = await client.post(
            "/api/connectors",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await agent_acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connectors/{account_id}",
            json={"secrets": {"BOT_TOKEN": "__MASKED__"}},
        )
        assert resp.status_code == 200
        assert "real" not in resp.text

        assert ("test-agent", account_id) in pool_mod._pool

    async def test_session_continuation_change_does_not_evict(
        self, client: AsyncClient
    ) -> None:
        """PUT changing ONLY session_continuation_seconds MUST NOT evict the warm pool entry.

        Pool entries represent the gateway warm-keep; session_continuation_seconds
        is consulted by the resolver at inbound-dispatch time and is NOT cached
        in pool state. A change takes effect on the next inbound after the PUT
        commits; no in-memory invalidation is needed.

        M10 F03 L05 — design-decision verification (see flight 03 Design
        Decisions: "Eviction trigger for session_continuation_seconds change
        — NONE").
        """
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import agent_acquire

        create = await client.post(
            "/api/connectors",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await agent_acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connectors/{account_id}",
            json={"session_continuation_seconds": 3600},
        )
        assert resp.status_code == 200

        # Pool entry survives — the new field is NOT part of the eviction trigger.
        assert ("test-agent", account_id) in pool_mod._pool

        # And the new value round-tripped.
        getrr = await client.get(f"/api/connectors/{account_id}")
        assert getrr.json()["session_continuation_seconds"] == 3600

    async def test_dropping_a_key_evicts(self, client: AsyncClient) -> None:
        """PUT with secrets={} drops all keys (REST replace) → eviction fires."""
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import agent_acquire

        create = await client.post(
            "/api/connectors",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await agent_acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connectors/{account_id}",
            json={"secrets": {}},
        )
        assert resp.status_code == 200

        assert ("test-agent", account_id) not in pool_mod._pool

    async def test_secrets_change_evicts(self, client: AsyncClient) -> None:
        """PUT with a changed secret value evicts the warm entry."""
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import agent_acquire

        create = await client.post(
            "/api/connectors",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await agent_acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connectors/{account_id}",
            json={"secrets": {"BOT_TOKEN": "new_value"}},
        )
        assert resp.status_code == 200

        assert ("test-agent", account_id) not in pool_mod._pool

    async def test_adding_a_new_key_evicts(self, client: AsyncClient) -> None:
        """Adding a NEW secret while masking an existing one MUST evict.

        ``resolved_secrets = {"BOT_TOKEN": "real", "OTHER_KEY": "new_value"}``
        ≠ ``existing.secrets = {"BOT_TOKEN": "real"}`` → eviction fires.
        Pins the "shorter or longer dict differs from existing" branch.
        """
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import agent_acquire

        create = await client.post(
            "/api/connectors",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await agent_acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "secrets": {
                    "BOT_TOKEN": "__MASKED__",
                    "OTHER_KEY": "new_value",
                },
            },
        )
        assert resp.status_code == 200

        assert ("test-agent", account_id) not in pool_mod._pool

    async def test_delete_evicts_then_deletes(self, client: AsyncClient) -> None:
        """DELETE evicts warm entries BEFORE the row delete."""
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import agent_acquire

        create = await client.post(
            "/api/connectors",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await agent_acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.delete(f"/api/connectors/{account_id}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        assert ("test-agent", account_id) not in pool_mod._pool

        resp = await client.get(f"/api/connectors/{account_id}")
        assert resp.status_code == 404

    async def test_types_returns_empty_in_production(
        self, client: AsyncClient
    ) -> None:
        """Without `register_for_test`, /types returns []."""
        from the_one.connectors.registry import clear_for_test

        clear_for_test()
        resp = await client.get("/api/connectors/types")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_types_returns_registered_in_test(
        self, client: AsyncClient
    ) -> None:
        """The autouse fixture restores the production baseline
        (``'discord'`` post-F8 L2) then registers the stub on top, so
        /types returns both entries in sorted order.
        """
        resp = await client.get("/api/connectors/types")
        assert resp.status_code == 200
        # ``registry.types()`` returns a sorted list — the API mirrors that
        # order verbatim.
        assert resp.json() == [
            {"value": "discord", "label": "Discord"},
            {"value": "stub", "label": "Stub"},
        ]

    async def test_create_with_invalid_payload_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST missing the required ``type`` field returns 422."""
        resp = await client.post(
            "/api/connectors",
            json={"name": "Bot"},  # missing `type`
        )
        assert resp.status_code == 422
        # Pydantic validation error shape — a list of errors per field.
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        assert any("type" in err.get("loc", []) for err in detail)

    async def test_update_connector_routing_round_trips(
        self, client: AsyncClient
    ) -> None:
        """PUT ``config.routing`` round-trips verbatim through GET.

        M10 F7 L7 regression net: the Studio Routing Rules editor rides
        the existing PUT endpoint with no schema migration and no new
        endpoint — the L2 validator (`_validate_config_reserved_keys`)
        already covers the shape, and the repository round-trips
        ``config`` as a JSON blob. This test pins the contract end-to-end
        so future refactors of the validator or repository don't
        silently break the Studio editor's save flow.
        """
        # Seed an account.
        create = await client.post(
            "/api/connectors",
            json={"name": "Bot", "type": "stub"},
        )
        assert create.status_code == 201
        account_id = create.json()["id"]

        # PUT routing config.
        routing_payload = {
            "rules": [
                {"scope": "channel", "match": ["C1"], "agent": "alpha"},
            ],
            "default": "bravo",
        }
        resp = await client.put(
            f"/api/connectors/{account_id}",
            json={"config": {"routing": routing_payload}},
        )
        assert resp.status_code == 200, resp.text

        # GET round-trip parity.
        getrr = await client.get(f"/api/connectors/{account_id}")
        assert getrr.status_code == 200
        assert getrr.json()["config"]["routing"] == routing_payload

    async def test_unknown_account_returns_404(self, client: AsyncClient) -> None:
        """GET / PUT / DELETE on an unknown id return 404."""
        resp = await client.get("/api/connectors/nope")
        assert resp.status_code == 404
        assert "Connector not found" in resp.json()["detail"]

        resp = await client.put(
            "/api/connectors/nope",
            json={"name": "x"},
        )
        assert resp.status_code == 404
        assert "Connector not found" in resp.json()["detail"]

        resp = await client.delete("/api/connectors/nope")
        assert resp.status_code == 404
        assert "Connector not found" in resp.json()["detail"]

    # ── Rotation eviction (F2 L4) ──────────────────────────────────────
    async def test_rotation_evicts_warm_pool_entries(
        self, client: AsyncClient
    ) -> None:
        """Encryption rotation evicts warm connector pool entries.

        Closes the F1-debrief carry-forward: before this wiring, warm
        pool entries kept serving credentials cached under the OLD key
        until their idle-TTL elapsed (30 min default). Now the rotation
        transaction evicts each rotated account's warm entries after the
        DB commit and before the on-disk key replace.

        The "decrypts under the new key" assertion is satisfied
        transitively: ``acquire`` reads the row (encrypted under the new
        key, written in step 4 of rotation) via the live encryptor,
        whose ``install_key`` has been updated.
        """
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import agent_acquire

        # Setup: stub-typed account with non-empty secrets.
        resp = await client.post(
            "/api/connectors",
            json={
                "name": "rotation-target",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "original_value"},
            },
        )
        assert resp.status_code == 201
        account_id = resp.json()["id"]

        # Acquire warm pool entry.
        await agent_acquire("test-agent", account_id)
        key = ("test-agent", account_id)
        assert key in pool_mod._pool, "pool seed failed"

        # Trigger rotation.
        rot = await client.post("/api/encryption/rotate")
        assert rot.status_code == 200
        assert rot.json() == {"status": "ok"}

        # Eviction fired: the original warm entry is gone.
        assert key not in pool_mod._pool, (
            "rotation should have evicted warm pool entry for the rotated "
            "account; eviction wiring at rotate_encryption_key step 4b is "
            "the regression net"
        )

        # Fresh acquire works under the new key — the row decrypted via
        # the live encryptor (whose install_key fired in step 7).
        await agent_acquire("test-agent", account_id)
        assert key in pool_mod._pool


# ── Connector account doctor probe (F2 L4) ────────────────────────────────


class TestConnectorDoctor:
    """Doctor-probe REST endpoint for connector accounts (F2 L4).

    Mirrors :class:`TestConnectorAPI`'s autouse ``_isolation``
    pattern: per-test reset of the pool, registry, and StubPlugin
    class-state, plus the ``_load_account`` monkeypatch that routes the
    pool through the test-isolated DB + encryptor. The probe itself does
    not call ``acquire`` (no pool interaction), but mirroring the fixture
    keeps the class shape consistent and protects against future tests
    that DO touch the pool from this class.
    """

    @pytest.fixture(autouse=True)
    async def _isolation(self, client: AsyncClient, monkeypatch):
        """Reset connector pool + registry + StubPlugin class-state per test.

        Verbatim copy of :meth:`TestConnectorAPI._isolation` per
        the F2 L4 leg artifact: class-scoped autouse fixtures don't
        propagate across classes, so each class that touches the
        connector subsystem redeclares it.
        """
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.registry import (
            clear_for_test,
            register_for_test,
            restore_to_baseline_for_test,
        )
        from the_one.db.repositories import ConnectorRepository
        from the_one.interfaces.web.api import get_connection, get_encryptor

        await pool_mod._clear_for_test()
        restore_to_baseline_for_test()
        StubPlugin.reset_for_test()
        register_for_test("stub", StubPlugin)

        async def _patched_load_account(account_id, encryptor):
            conn = await get_connection()
            repo = ConnectorRepository(conn, get_encryptor(""))
            return await repo.get(account_id)

        monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)

        try:
            yield
        finally:
            await pool_mod._clear_for_test()
            clear_for_test()

    async def _create_stub_account(self, client: AsyncClient) -> str:
        """Helper — create a stub-typed account, return its id."""
        resp = await client.post(
            "/api/connectors",
            json={
                "name": "doctor-target",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "any_value"},
            },
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_doctor_probe_success(self, client: AsyncClient) -> None:
        """Default stub doctor → ``{status: 'ok', message: 'stub probe ok', details: {}}``."""
        account_id = await self._create_stub_account(client)

        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "message": "stub probe ok",
            "details": {"pool_warmed": True, "pool_warm_error": None},
        }

    async def test_doctor_probe_configured_failure(
        self, client: AsyncClient
    ) -> None:
        """``StubPlugin.doctor_response = failed-report`` round-trips verbatim."""
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.base import DoctorReport

        StubPlugin.doctor_response = DoctorReport(
            status="failed",
            message="bot token revoked",
            details={"reason": "401"},
        )

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "failed",
            "message": "bot token revoked",
            "details": {
                "reason": "401",
                "pool_warmed": False,
                "pool_warm_error": None,
            },
        }

    async def test_doctor_probe_degraded_status(
        self, client: AsyncClient
    ) -> None:
        """Regression net for the third ``DoctorReport.status`` Literal branch."""
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.base import DoctorReport

        StubPlugin.doctor_response = DoctorReport(
            status="degraded",
            message="gateway reachable but slow",
            details={"latency_ms": 1200},
        )

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["message"] == "gateway reachable but slow"
        assert body["details"] == {
            "latency_ms": 1200,
            "pool_warmed": False,
            "pool_warm_error": None,
        }

    async def test_doctor_probe_unknown_type(self, client: AsyncClient) -> None:
        """Account with an unregistered ``type`` → ``{status: 'error', ...}`` 200.

        Mirrors the MCP "unknown transport" pattern so the UI banner
        renders inline rather than triggering a global error handler.

        M10 F8 L2: ``Connector.type`` was tightened to
        ``Literal["discord", "stub"]``, so the POST path can no longer
        accept an arbitrary type string. The test now seeds a
        ``'discord'``-typed account via the API (the production registry
        carries ``'discord'`` from F8 L2's
        ``register_builtin_connectors``), then clears the registry so the
        doctor probe encounters an unknown type at runtime. The autouse
        fixture's ``register_for_test("stub", StubPlugin)`` is also wiped
        by the ``clear_for_test`` call, so both production builtins and
        the test-registered stub disappear — the doctor probe surfaces
        the "type not registered" envelope.
        """
        from the_one.connectors.registry import clear_for_test

        resp = await client.post(
            "/api/connectors",
            json={
                "name": "alien",
                "type": "discord",
                "secrets": {},
            },
        )
        assert resp.status_code == 201
        account_id = resp.json()["id"]

        # Wipe the registry so the doctor probe encounters "type not
        # registered" on the ``'discord'``-typed account.
        clear_for_test()

        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "error",
            "message": "Unknown connector type: discord",
            "details": {
                "error": "type not registered",
                "type": "discord",
            },
        }

    async def test_doctor_probe_connector_client_error(
        self, client: AsyncClient
    ) -> None:
        """``ConnectorClientError`` from ``plugin.doctor`` → wrapped 200 envelope."""
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.errors import ConnectorClientError

        StubPlugin.doctor_should_raise = ConnectorClientError(
            "simulated probe failure"
        )

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "error",
            "message": "simulated probe failure",
            "details": {
                "error": "simulated probe failure",
                "exception_type": "ConnectorClientError",
            },
        }

    async def test_doctor_probe_unknown_account_returns_404(
        self, client: AsyncClient
    ) -> None:
        """POST to a made-up id returns 404 with the canonical detail string."""
        resp = await client.post(
            "/api/connectors/does-not-exist/test/connect"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Connector not found: does-not-exist"
        )

    async def test_doctor_probe_records_the_call(
        self, client: AsyncClient
    ) -> None:
        """Regression net: probe actually dispatches to ``plugin.doctor``."""
        from the_one.connectors._stub import StubPlugin

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert StubPlugin.doctor_calls == [(account_id, "stub")]

    async def test_doctor_probe_success_warms_pool(
        self, client: AsyncClient
    ) -> None:
        """OK doctor → pool gets warmed; envelope advertises pool_warmed=True.

        Closes M11 F4 A1 (Test Connection warms pool). The L4-design-time
        assumption that lifespan-warmup populated the pool entry was
        structurally false; F4 L2 explicitly wires account_acquire after
        doctor() succeeds. Convention reference: ``pool-warming-entrypoints-
        are-finite-and-named`` (agents.md Project-wide).
        """
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import _ACCOUNT_POOL_AGENT_SLOT

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["details"]["pool_warmed"] is True
        assert body["details"]["pool_warm_error"] is None
        # Pool actually warmed — entry exists at the canonical key tuple.
        assert (_ACCOUNT_POOL_AGENT_SLOT, account_id) in pool_mod._pool

    async def test_doctor_probe_failed_skips_warmup(
        self, client: AsyncClient
    ) -> None:
        """Non-ok doctor → warmup is SKIPPED; envelope advertises
        pool_warmed=False + pool_warm_error=None (skipped, not failed)."""
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.base import DoctorReport

        StubPlugin.doctor_response = DoctorReport(
            status="failed",
            message="bot token revoked",
            details={"reason": "401"},
        )

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["details"]["pool_warmed"] is False
        assert body["details"]["pool_warm_error"] is None
        assert pool_mod._pool == {}

    async def test_doctor_probe_ok_warmup_failure_does_not_escalate(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """OK doctor + raising account_acquire → envelope STILL status=ok;
        warmup failure isolated to pool_warm_error field.

        Convention reference: ``two-concurrent-callers-reasoning`` (agents.md
        Project-wide) — the partial-success shape was worked out before
        commit, not after."""
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors.errors import ConnectorClientError

        async def _failing_acquire(account_id: str):
            # ConnectorClientError chosen because it's the realistic
            # production failure mode; any Exception subclass would prove
            # the same partial-success isolation contract.
            raise ConnectorClientError("simulated warmup failure")

        # The handler's function-local `from ._pool import account_acquire`
        # resolves pool_mod.account_acquire at handler-entry time, so
        # patching the source-module attribute is in effect when the
        # handler runs.
        monkeypatch.setattr(pool_mod, "account_acquire", _failing_acquire)

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        body = resp.json()
        # CRITICAL: doctor's verdict is preserved despite warmup failure.
        assert body["status"] == "ok"
        assert body["details"]["pool_warmed"] is False
        assert body["details"]["pool_warm_error"] == "simulated warmup failure"
        assert pool_mod._pool == {}


# ── Connector account pairing-code + attached-agents (F6 L4) ─────────────


class TestConnectorPairingCodeAndAttached:
    """REST surface for the F6 L4 Studio Connector account additions.

    Covers the two new endpoints:

      * ``POST /api/connectors/{id}/pairing-code`` — generates
        an 8-hex pairing code and writes ``config["pairing"]`` via the
        repository.
      * ``GET  /api/connectors/{id}/attached-agents`` — lists
        agents whose ``connector_ids`` includes the account,
        with per-row peer/channel counts from ``connector_acls``.

    Plus a regression net at the API edge for leg-1b's empty-allowlist
    preservation invariant: PUT-ing
    ``config.allowlist = {"peers": [], "channels": []}`` must round-trip
    verbatim through GET (NOT collapse to absent).

    Mirrors :class:`TestConnectorAPI`'s autouse ``_isolation``
    fixture so the pool, registry, and StubPlugin class-state are reset
    per test (class-scoped autouse fixtures do not propagate across
    classes; each class that touches the connector subsystem must
    redeclare). The pairing-code tests do not acquire warm pool entries,
    but the fixture is kept verbatim because future tests in this class
    may grow that need.
    """

    @pytest.fixture(autouse=True)
    async def _isolation(self, client: AsyncClient, monkeypatch):
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.registry import (
            clear_for_test,
            register_for_test,
            restore_to_baseline_for_test,
        )
        from the_one.db.repositories import ConnectorRepository
        from the_one.interfaces.web.api import get_connection, get_encryptor

        await pool_mod._clear_for_test()
        restore_to_baseline_for_test()
        StubPlugin.reset_for_test()
        register_for_test("stub", StubPlugin)

        async def _patched_load_account(account_id, encryptor):
            conn = await get_connection()
            repo = ConnectorRepository(conn, get_encryptor(""))
            return await repo.get(account_id)

        monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)

        try:
            yield
        finally:
            await pool_mod._clear_for_test()
            clear_for_test()

    async def _create_account(
        self, client: AsyncClient, config: dict | None = None
    ) -> str:
        body = {"name": "pairing-target", "type": "stub", "secrets": {}}
        if config is not None:
            body["config"] = config
        resp = await client.post("/api/connectors", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    # ── pairing-code endpoint ─────────────────────────────────────────────

    async def test_generate_pairing_code_returns_8_hex_code_and_iso_issued_at(
        self, client: AsyncClient
    ) -> None:
        """POST returns ``{code: 8-hex, issued_at: iso}``."""
        account_id = await self._create_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}/pairing-code"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == {"code", "issued_at"}
        # 8-hex (4-byte token_hex) — chars-only, lower-cased per stdlib.
        assert len(body["code"]) == 8
        assert all(c in "0123456789abcdef" for c in body["code"])
        # ISO timestamp with the ``T`` separator (leg-1b validator
        # rejects date-only strings, so any successful round-trip
        # implies the ``T`` is present).
        assert "T" in body["issued_at"]

    async def test_generate_pairing_code_updates_account_config_pairing(
        self, client: AsyncClient
    ) -> None:
        """Generated code + timestamp are persisted to ``config["pairing"]``."""
        account_id = await self._create_account(client)
        gen = await client.post(
            f"/api/connectors/{account_id}/pairing-code"
        )
        assert gen.status_code == 200
        expected = gen.json()

        getr = await client.get(f"/api/connectors/{account_id}")
        assert getr.status_code == 200
        pairing = getr.json()["config"]["pairing"]
        assert pairing == {
            "code": expected["code"],
            "issued_at": expected["issued_at"],
        }

    async def test_regenerate_pairing_code_replaces_previous_code(
        self, client: AsyncClient
    ) -> None:
        """Calling twice returns two distinct codes; stored copy = latest."""
        account_id = await self._create_account(client)

        first = await client.post(
            f"/api/connectors/{account_id}/pairing-code"
        )
        assert first.status_code == 200
        first_body = first.json()

        second = await client.post(
            f"/api/connectors/{account_id}/pairing-code"
        )
        assert second.status_code == 200
        second_body = second.json()

        # token_hex(4) collision probability is ~1/4e9 — vanishingly
        # rare, but we assert inequality on the persisted copy to pin
        # the "regenerate replaces" semantic without relying on the
        # response codes being distinct.
        getr = await client.get(f"/api/connectors/{account_id}")
        stored = getr.json()["config"]["pairing"]
        assert stored == {
            "code": second_body["code"],
            "issued_at": second_body["issued_at"],
        }
        # Best-effort distinctness (response shapes differ on at least
        # one of code / issued_at across the two calls).
        assert (first_body["code"], first_body["issued_at"]) != (
            second_body["code"],
            second_body["issued_at"],
        )

    async def test_generate_pairing_code_preserves_other_config_keys(
        self, client: AsyncClient
    ) -> None:
        """Non-reserved keys (intent) AND ``allowlist`` survive the mutation.

        M11 F12 L3 — peers/channels use structured-tuple shape;
        dm_admission default renamed to "admin-approved".
        """
        account_id = await self._create_account(
            client,
            config={
                "intent": "guild_messages",
                "allowlist": {
                    "peers": [{"id": "u-keep", "dm_allowed": True}],
                    "channels": [
                        {"guild_id": "g-test", "channel_id": "c-keep"}
                    ],
                },
            },
        )
        gen = await client.post(
            f"/api/connectors/{account_id}/pairing-code"
        )
        assert gen.status_code == 200

        getr = await client.get(f"/api/connectors/{account_id}")
        cfg = getr.json()["config"]
        assert cfg["intent"] == "guild_messages"
        # M11 F10 L1 + M11 F12 L3: validator inserts ``dm_admission``
        # fresh-account default ``"admin-approved"`` (renamed from
        # ``"allowlisted-peers-only"``).
        assert cfg["allowlist"] == {
            "peers": [{"id": "u-keep", "dm_allowed": True}],
            "channels": [{"guild_id": "g-test", "channel_id": "c-keep"}],
            "dm_admission": "admin-approved",
        }
        assert cfg["pairing"]["code"] == gen.json()["code"]

    async def test_generate_pairing_code_404_on_unknown_account(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/connectors/does-not-exist/pairing-code"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Connector not found: does-not-exist"
        )

    # ── attached-agents endpoint ──────────────────────────────────────────

    async def test_attached_agents_empty_when_no_agents_attached(
        self, client: AsyncClient
    ) -> None:
        """Account with no agent references → ``[]``."""
        account_id = await self._create_account(client)
        resp = await client.get(
            f"/api/connectors/{account_id}/attached-agents"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_attached_agents_returns_attached_with_null_axes_when_no_acl(
        self, client: AsyncClient
    ) -> None:
        """Agent attached, no per-agent ACL → both axes ``None`` (inherit).

        L7 HAT response-shape extension: in addition to ``peers_count`` /
        ``channels_count`` (retained for back-compat), the row now
        includes ``peers`` and ``channels`` as ``list[str] | None``.
        Agents without a per-account entry get ``None`` on both axes
        (inherit account-scope).
        """
        account_id = await self._create_account(client)

        # Create the agent with this account attached but no ACLs.
        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-attached",
                "connector_ids": [account_id],
            },
        )
        assert resp.status_code in (200, 201), resp.text

        resp = await client.get(
            f"/api/connectors/{account_id}/attached-agents"
        )
        assert resp.status_code == 200
        assert resp.json() == [
            {
                "name": "agent-attached",
                "peers": None,
                "channels": None,
                "peers_count": 0,
                "channels_count": 0,
            }
        ]

    async def test_attached_agents_includes_acl_peer_and_channel_lists(
        self, client: AsyncClient
    ) -> None:
        """Agent with a non-empty ACL → response carries the actual
        ``peers`` and ``channels`` lists (L7 HAT shape extension).

        M11 F12 L3 — peers/channels use the structured-tuple shape.
        """
        account_id = await self._create_account(client)

        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-with-acl",
                "connector_ids": [account_id],
                "connector_acls": {
                    account_id: {
                        "peers": [
                            {"id": "u1", "dm_allowed": True},
                            {"id": "u2", "dm_allowed": True},
                            {"id": "u3", "dm_allowed": True},
                        ],
                        "channels": [
                            {"guild_id": "g-test", "channel_id": "c1"},
                            {"guild_id": "g-test", "channel_id": "c2"},
                        ],
                    }
                },
            },
        )
        assert resp.status_code in (200, 201), resp.text

        # A second agent attached to the SAME account but with NO ACL —
        # confirms multi-agent listing + null-axes fallback in one
        # response.
        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-no-acl",
                "connector_ids": [account_id],
            },
        )
        assert resp.status_code in (200, 201), resp.text

        # A third agent that is NOT attached to this account — must be
        # excluded from the response entirely.
        resp = await client.post(
            "/api/agents",
            json={"name": "agent-unrelated", "connector_ids": []},
        )
        assert resp.status_code in (200, 201), resp.text

        resp = await client.get(
            f"/api/connectors/{account_id}/attached-agents"
        )
        assert resp.status_code == 200
        rows = sorted(resp.json(), key=lambda r: r["name"])
        assert rows == [
            {
                "name": "agent-no-acl",
                "peers": None,
                "channels": None,
                "peers_count": 0,
                "channels_count": 0,
            },
            {
                "name": "agent-with-acl",
                "peers": [
                    {"id": "u1", "dm_allowed": True},
                    {"id": "u2", "dm_allowed": True},
                    {"id": "u3", "dm_allowed": True},
                ],
                "channels": [
                    {"guild_id": "g-test", "channel_id": "c1"},
                    {"guild_id": "g-test", "channel_id": "c2"},
                ],
                "peers_count": 3,
                "channels_count": 2,
            },
        ]

    async def test_attached_agents_response_tri_state_axes(
        self, client: AsyncClient
    ) -> None:
        """L7 HAT tri-state semantic — verify each axis value (None vs
        ``[]`` vs ``[items]``) surfaces correctly per agent.
        """
        account_id = await self._create_account(client)

        # Agent A: peers explicit-empty, channels inherit.
        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-a",
                "connector_ids": [account_id],
                "connector_acls": {
                    account_id: {"peers": [], "channels": None},
                },
            },
        )
        assert resp.status_code in (200, 201), resp.text

        # Agent B: peers subset, channels explicit-empty (DMs-only).
        # M11 F12 L3 — peers use the structured-tuple shape.
        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-b",
                "connector_ids": [account_id],
                "connector_acls": {
                    account_id: {
                        "peers": [{"id": "u1", "dm_allowed": True}],
                        "channels": [],
                    },
                },
            },
        )
        assert resp.status_code in (200, 201), resp.text

        resp = await client.get(
            f"/api/connectors/{account_id}/attached-agents"
        )
        assert resp.status_code == 200
        rows = sorted(resp.json(), key=lambda r: r["name"])
        assert rows == [
            {
                "name": "agent-a",
                "peers": [],
                "channels": None,
                "peers_count": 0,
                "channels_count": 0,
            },
            {
                "name": "agent-b",
                "peers": [{"id": "u1", "dm_allowed": True}],
                "channels": [],
                "peers_count": 1,
                "channels_count": 0,
            },
        ]

    async def test_attached_agents_404_on_unknown_account(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get(
            "/api/connectors/does-not-exist/attached-agents"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Connector not found: does-not-exist"
        )

    # ── Empty-allowlist API-edge round-trip (leg-1b invariant) ────────────

    async def test_put_account_with_empty_allowlist_lockdown_survives_get(
        self, client: AsyncClient
    ) -> None:
        """``{peers: [], channels: []}`` round-trips verbatim through PUT → GET.

        Leg-1b's repository-level test pins this invariant at the model +
        SQL layers; this is the API-edge regression net for the leg-4
        Studio writer (the operator's "Enable allowlist" + empty lists →
        lockdown affordance must reach the database verbatim and come
        back out the same).
        """
        account_id = await self._create_account(client)
        put = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "pairing-target",
                "type": "stub",
                "config": {"allowlist": {"peers": [], "channels": []}},
            },
        )
        assert put.status_code == 200, put.text

        getr = await client.get(f"/api/connectors/{account_id}")
        assert getr.status_code == 200
        allowlist = getr.json()["config"]["allowlist"]
        # Verbatim — NOT absent, NOT coerced to null/None. M11 F10 L1
        # adds the ``dm_admission`` fresh-account default at validator
        # time; the empty ``peers``/``channels`` lists remain verbatim.
        # M11 F12 L3 — default renamed from "allowlisted-peers-only"
        # to "admin-approved".
        assert allowlist == {
            "peers": [],
            "channels": [],
            "dm_admission": "admin-approved",
        }

    # ── M11 F10 L1 dm_admission axis ──────────────────────────────────

    async def test_put_account_with_dm_admission_all_survives_get(
        self, client: AsyncClient
    ) -> None:
        """``allowlist.dm_admission="all"`` round-trips through PUT →
        GET verbatim. Pins the new Literal-string axis at the API edge.
        """
        account_id = await self._create_account(client)
        put = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "dm-admission-target",
                "type": "stub",
                "config": {"allowlist": {
                    "peers": [], "channels": [], "dm_admission": "all",
                }},
            },
        )
        assert put.status_code == 200, put.text

        getr = await client.get(f"/api/connectors/{account_id}")
        assert getr.status_code == 200
        allowlist = getr.json()["config"]["allowlist"]
        assert allowlist == {
            "peers": [],
            "channels": [],
            "dm_admission": "all",
        }

    async def test_put_account_with_invalid_dm_admission_rejected(
        self, client: AsyncClient
    ) -> None:
        """A non-Literal ``dm_admission`` string is rejected with HTTP
        422 by the model validator (propagated through FastAPI's
        Pydantic exception handler).
        """
        account_id = await self._create_account(client)
        put = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "dm-admission-bad",
                "type": "stub",
                "config": {"allowlist": {
                    "peers": [], "channels": [],
                    "dm_admission": "everybody",
                }},
            },
        )
        assert put.status_code == 422, put.text

    async def test_put_account_with_non_string_dm_admission_rejected(
        self, client: AsyncClient
    ) -> None:
        """A non-string ``dm_admission`` value (e.g. ``True``) is
        rejected with HTTP 422. Pins that the validator does not
        coerce booleans into Literal-string acceptance.
        """
        account_id = await self._create_account(client)
        put = await client.put(
            f"/api/connectors/{account_id}",
            json={
                "name": "dm-admission-non-string",
                "type": "stub",
                "config": {"allowlist": {
                    "peers": [], "channels": [],
                    "dm_admission": True,
                }},
            },
        )
        assert put.status_code == 422, put.text


# ── Connector account peer-approvals (M11 F9 L3) ─────────────────────────


class TestConnectorPeerApprovals:
    """REST surface for the F9 L3 peer-approval action endpoints.

    Covers the two new endpoints:

      * ``POST /api/connectors/{id}/peer-approvals/{approval_id}/approve``
        — transitions the pending_approvals row to ``status='approved'``
        and adds the peer to ``account.config['allowlist']['peers']``
        (idempotent).
      * ``POST /api/connectors/{id}/peer-approvals/{approval_id}/dismiss``
        — transitions the row to ``status='dismissed'``; does NOT mutate
        the allowlist.

    Mirrors :class:`TestConnectorPairingCodeAndAttached`'s autouse
    ``_isolation`` fixture verbatim (class-scoped autouse fixtures do not
    propagate across classes; each class that touches the connector
    subsystem must redeclare).
    """

    @pytest.fixture(autouse=True)
    async def _isolation(self, client: AsyncClient, monkeypatch):
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.registry import (
            clear_for_test,
            register_for_test,
            restore_to_baseline_for_test,
        )
        from the_one.db.repositories import ConnectorRepository
        from the_one.interfaces.web.api import get_connection, get_encryptor

        await pool_mod._clear_for_test()
        restore_to_baseline_for_test()
        StubPlugin.reset_for_test()
        register_for_test("stub", StubPlugin)

        async def _patched_load_account(account_id, encryptor):
            conn = await get_connection()
            repo = ConnectorRepository(conn, get_encryptor(""))
            return await repo.get(account_id)

        monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)

        try:
            yield
        finally:
            await pool_mod._clear_for_test()
            clear_for_test()

    async def _create_account(
        self, client: AsyncClient, config: dict | None = None
    ) -> str:
        body = {"name": "approval-target", "type": "stub", "secrets": {}}
        if config is not None:
            body["config"] = config
        resp = await client.post("/api/connectors", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def _create_pending_approval(
        self,
        account_id: str,
        peer_id: str = "peer-1",
        peer_name: str = "Test Peer",
        preview: str = "hello",
    ) -> str:
        """Insert a pending_approvals row via the repository directly.

        There is no public endpoint to create one — the dispatcher emit
        path is the only producer in production. Tests construct rows
        through the repo and exercise the API consumer endpoints.

        Imports ``get_connection`` from the ``api`` module (not the
        ``db.connection`` module) because the ``client`` fixture patches
        the API module's binding to point at the per-test isolated
        sqlite file; the unpatched module-level binding would open a
        different connection where the connector account row does not
        exist (FK violation on insert).
        """
        from the_one.db.repositories import PendingApprovalRepository
        from the_one.interfaces.web.api import get_connection

        conn = await get_connection()
        repo = PendingApprovalRepository(conn)
        approval = await repo.upsert_pending(
            connector_id=account_id,
            peer_id=peer_id,
            peer_name=peer_name,
            preview=preview,
        )
        return approval.id

    # ── approve endpoint ─────────────────────────────────────────────────

    async def test_approve_pending_returns_approved_row(
        self, client: AsyncClient
    ) -> None:
        """POST approve on a pending row → 200 + ``status='approved'``."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(account_id)

        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == approval_id
        assert body["connector_id"] == account_id
        assert body["peer_id"] == "peer-1"
        assert body["peer_name"] == "Test Peer"
        assert body["preview"] == "hello"
        assert body["status"] == "approved"
        assert body["resolved_at"] is not None
        assert "T" in body["resolved_at"]

    async def test_approve_pending_adds_peer_to_allowlist(
        self, client: AsyncClient
    ) -> None:
        """Successful approve → peer_id present in ``config.allowlist.peers``."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(
            account_id, peer_id="peer-add-me"
        )

        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert resp.status_code == 200, resp.text

        getr = await client.get(f"/api/connectors/{account_id}")
        assert getr.status_code == 200
        allowlist = getr.json()["config"]["allowlist"]
        # M11 F12 L3 — peers are structured dicts; check membership by id.
        assert any(
            p["id"] == "peer-add-me" for p in allowlist["peers"]
        ), allowlist["peers"]

    async def test_approve_pending_idempotent_does_not_duplicate_peer_id(
        self, client: AsyncClient
    ) -> None:
        """Re-approve does NOT duplicate the peer in the allowlist."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(
            account_id, peer_id="peer-dup-check"
        )

        first = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert second.status_code == 200, second.text

        getr = await client.get(f"/api/connectors/{account_id}")
        peers = getr.json()["config"]["allowlist"]["peers"]
        # M11 F12 L3 — peers are structured dicts; count by id.
        matching = [p for p in peers if p["id"] == "peer-dup-check"]
        assert len(matching) == 1, peers

    async def test_approve_preserves_other_config_keys(
        self, client: AsyncClient
    ) -> None:
        """Pre-existing config keys (intent, pairing) survive the
        mutation.

        M11 F12 L3 — peers/channels use the structured-tuple shape.
        """
        account_id = await self._create_account(
            client,
            config={
                "intent": "guild_messages",
                "allowlist": {
                    "peers": [{"id": "u-keep", "dm_allowed": True}],
                    "channels": [
                        {"guild_id": "g-test", "channel_id": "c-keep"}
                    ],
                },
            },
        )
        # Stamp a pairing block separately via the pairing-code endpoint
        # so we have a third reserved key to assert survives.
        pair = await client.post(
            f"/api/connectors/{account_id}/pairing-code"
        )
        assert pair.status_code == 200
        pairing_before = pair.json()

        approval_id = await self._create_pending_approval(
            account_id, peer_id="peer-new"
        )
        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert resp.status_code == 200, resp.text

        getr = await client.get(f"/api/connectors/{account_id}")
        cfg = getr.json()["config"]
        assert cfg["intent"] == "guild_messages"
        assert cfg["allowlist"]["channels"] == [
            {"guild_id": "g-test", "channel_id": "c-keep"}
        ]
        peer_ids = {p["id"] for p in cfg["allowlist"]["peers"]}
        assert "u-keep" in peer_ids
        assert "peer-new" in peer_ids
        assert cfg["pairing"] == {
            "code": pairing_before["code"],
            "issued_at": pairing_before["issued_at"],
        }

    async def test_approve_already_approved_returns_200_idempotent(
        self, client: AsyncClient
    ) -> None:
        """Approve, approve again → both 200, same id, same resolved_at."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(account_id)

        first = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert first.status_code == 200, first.text
        first_body = first.json()

        second = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert second.status_code == 200, second.text
        second_body = second.json()

        assert first_body["id"] == second_body["id"]
        assert second_body["status"] == "approved"
        # resolved_at stable across idempotent calls — operator-observable
        # contract (re-call does NOT bump the timestamp).
        assert first_body["resolved_at"] == second_body["resolved_at"]

    async def test_approve_on_dismissed_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Approve on a dismissed row → 409 Conflict (terminal mismatch)."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(account_id)

        dismiss = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/dismiss"
        )
        assert dismiss.status_code == 200, dismiss.text

        approve = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert approve.status_code == 409, approve.text

    async def test_approve_unknown_account_returns_404(
        self, client: AsyncClient
    ) -> None:
        """POST against a fake account id → 404."""
        resp = await client.post(
            "/api/connectors/does-not-exist"
            "/peer-approvals/anything/approve"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Connector not found: does-not-exist"
        )

    async def test_approve_unknown_approval_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Real account, fake approval id → 404."""
        account_id = await self._create_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/no-such-approval/approve"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Pending approval not found: no-such-approval"
        )

    async def test_approve_cross_account_approval_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Approval belongs to account-A; POST against account-B → 404."""
        account_a = await self._create_account(client)
        # Create a second account using a different name (the helper's
        # default name would collide on the UNIQUE constraint).
        resp = await client.post(
            "/api/connectors",
            json={"name": "approval-target-b", "type": "stub", "secrets": {}},
        )
        assert resp.status_code == 201, resp.text
        account_b = resp.json()["id"]

        approval_id = await self._create_pending_approval(account_a)

        resp = await client.post(
            f"/api/connectors/{account_b}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Pending approval not found: {approval_id}"
        )

    # ── dismiss endpoint ─────────────────────────────────────────────────

    async def test_dismiss_pending_returns_dismissed_row(
        self, client: AsyncClient
    ) -> None:
        """POST dismiss on a pending row → 200 + ``status='dismissed'``."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(account_id)

        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/dismiss"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == approval_id
        assert body["status"] == "dismissed"
        assert body["resolved_at"] is not None

    async def test_dismiss_does_not_mutate_allowlist(
        self, client: AsyncClient
    ) -> None:
        """Dismiss → allowlist unchanged (peer NOT added).

        M11 F12 L3 — peers/channels use the structured-tuple shape;
        dm_admission default renamed to "admin-approved".
        """
        account_id = await self._create_account(
            client,
            config={"allowlist": {
                "peers": [{"id": "u-keep", "dm_allowed": True}],
                "channels": [{"guild_id": "g-test", "channel_id": "c-keep"}],
            }},
        )
        approval_id = await self._create_pending_approval(
            account_id, peer_id="peer-do-not-add"
        )

        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/dismiss"
        )
        assert resp.status_code == 200, resp.text

        getr = await client.get(f"/api/connectors/{account_id}")
        allowlist = getr.json()["config"]["allowlist"]
        # M11 F10 L1 + M11 F12 L3: validator inserts ``dm_admission``
        # fresh-account default ``"admin-approved"``; non-allowlist
        # fields stay verbatim.
        assert allowlist == {
            "peers": [{"id": "u-keep", "dm_allowed": True}],
            "channels": [{"guild_id": "g-test", "channel_id": "c-keep"}],
            "dm_admission": "admin-approved",
        }

    async def test_dismiss_already_dismissed_returns_200_idempotent(
        self, client: AsyncClient
    ) -> None:
        """Dismiss, dismiss again → both 200, same id, stable resolved_at."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(account_id)

        first = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/dismiss"
        )
        assert first.status_code == 200, first.text
        first_body = first.json()

        second = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/dismiss"
        )
        assert second.status_code == 200, second.text
        second_body = second.json()

        assert first_body["id"] == second_body["id"]
        assert second_body["status"] == "dismissed"
        assert first_body["resolved_at"] == second_body["resolved_at"]

    async def test_dismiss_on_approved_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Dismiss on an approved row → 409 Conflict."""
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(account_id)

        approve = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert approve.status_code == 200, approve.text

        dismiss = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/dismiss"
        )
        assert dismiss.status_code == 409, dismiss.text

    async def test_dismiss_unknown_account_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/connectors/does-not-exist"
            "/peer-approvals/anything/dismiss"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Connector not found: does-not-exist"
        )

    async def test_dismiss_unknown_approval_returns_404(
        self, client: AsyncClient
    ) -> None:
        account_id = await self._create_account(client)
        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/no-such-approval/dismiss"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Pending approval not found: no-such-approval"
        )

    async def test_dismiss_cross_account_approval_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Approval belongs to account-A; dismiss against account-B → 404."""
        account_a = await self._create_account(client)
        resp = await client.post(
            "/api/connectors",
            json={"name": "approval-target-b", "type": "stub", "secrets": {}},
        )
        assert resp.status_code == 201, resp.text
        account_b = resp.json()["id"]

        approval_id = await self._create_pending_approval(account_a)

        resp = await client.post(
            f"/api/connectors/{account_b}"
            f"/peer-approvals/{approval_id}/dismiss"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            f"Pending approval not found: {approval_id}"
        )

    # ── allowlist initialization edge case ───────────────────────────────

    async def test_approve_initializes_allowlist_when_missing(
        self, client: AsyncClient
    ) -> None:
        """Account with no ``allowlist`` key in config → allowlist
        initialized to ``{"peers": [<peer_id>], "channels": []}``."""
        # _create_account uses an empty config (no allowlist key).
        account_id = await self._create_account(client)
        approval_id = await self._create_pending_approval(
            account_id, peer_id="peer-init"
        )

        resp = await client.post(
            f"/api/connectors/{account_id}"
            f"/peer-approvals/{approval_id}/approve"
        )
        assert resp.status_code == 200, resp.text

        getr = await client.get(f"/api/connectors/{account_id}")
        cfg = getr.json()["config"]
        # M11 F10 L1 + M11 F12 L3: validator inserts the
        # ``dm_admission`` fresh-account default ``"admin-approved"``
        # (renamed in F12 L3) when an allowlist is constructed but
        # the key is absent. The approve endpoint constructs the new
        # peer as a structured ``{id, dm_allowed=False}`` dict
        # (operator must flip the per-peer toggle via the UI under
        # the ``"admin-approved"`` policy before the peer can DM).
        assert cfg["allowlist"] == {
            "peers": [{"id": "peer-init", "dm_allowed": False}],
            "channels": [],
            "dm_admission": "admin-approved",
        }


# ── Agent–connector-account detach (M11 F9 L5) ───────────────────────────


class TestAgentConnectorDetach:
    """REST surface for the F9 L5 operator-driven detach endpoint.

    Covers ``DELETE /api/agents/{agent_name}/connectors/{account_id}``:

      * Happy path — account_id is in the agent's ``connector_ids``;
        gets removed; pool slot released.
      * Idempotent no-op — account_id is NOT in the list; 200 + no change.
      * 404 — unknown agent name.

    Plus a regression net for the ``list_connectors`` response
    extension (per-row ``attached_agents_count`` field).

    Mirrors :class:`TestConnectorPairingCodeAndAttached`'s autouse
    ``_isolation`` fixture so the pool, registry, and StubPlugin state
    are reset per test.
    """

    @pytest.fixture(autouse=True)
    async def _isolation(self, client: AsyncClient, monkeypatch):
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._stub import StubPlugin
        from the_one.connectors.registry import (
            clear_for_test,
            register_for_test,
            restore_to_baseline_for_test,
        )
        from the_one.db.repositories import ConnectorRepository
        from the_one.interfaces.web.api import get_connection, get_encryptor

        await pool_mod._clear_for_test()
        restore_to_baseline_for_test()
        StubPlugin.reset_for_test()
        register_for_test("stub", StubPlugin)

        async def _patched_load_account(account_id, encryptor):
            conn = await get_connection()
            repo = ConnectorRepository(conn, get_encryptor(""))
            return await repo.get(account_id)

        monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)

        try:
            yield
        finally:
            await pool_mod._clear_for_test()
            clear_for_test()

    async def _create_account(self, client: AsyncClient, name: str = "detach-target") -> str:
        resp = await client.post(
            "/api/connectors",
            json={"name": name, "type": "stub", "secrets": {}},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def test_detach_removes_account_from_agent_connector_ids(
        self, client: AsyncClient
    ) -> None:
        """Happy path — account is in the agent's list; DELETE removes it
        and returns the updated agent config (PUT-shape body)."""
        account_id = await self._create_account(client)

        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-detach-happy",
                "connector_ids": [account_id],
            },
        )
        assert resp.status_code in (200, 201), resp.text

        resp = await client.delete(
            f"/api/agents/agent-detach-happy/connectors/{account_id}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Response is the agent config — same shape as PUT.
        assert body["name"] == "agent-detach-happy"
        assert body["connector_ids"] == []

        # Verify via GET that the persisted state agrees.
        getr = await client.get("/api/agents/agent-detach-happy")
        assert getr.status_code == 200
        assert getr.json()["connector_ids"] == []

    async def test_detach_preserves_other_account_ids(
        self, client: AsyncClient
    ) -> None:
        """Detach removes ONLY the targeted account; sibling accounts stay."""
        a1 = await self._create_account(client, name="acct-1")
        a2 = await self._create_account(client, name="acct-2")

        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-detach-siblings",
                "connector_ids": [a1, a2],
            },
        )
        assert resp.status_code in (200, 201), resp.text

        resp = await client.delete(
            f"/api/agents/agent-detach-siblings/connectors/{a1}"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["connector_ids"] == [a2]

    async def test_detach_idempotent_on_already_detached(
        self, client: AsyncClient
    ) -> None:
        """Account NOT in the agent's list → 200 + unchanged state.

        The post-state is the same (account_id is not in the list), so
        the call is a no-op rather than a 404.
        """
        account_id = await self._create_account(client)

        # Agent created with NO connector accounts attached.
        resp = await client.post(
            "/api/agents",
            json={"name": "agent-already-detached"},
        )
        assert resp.status_code in (200, 201), resp.text

        resp = await client.delete(
            f"/api/agents/agent-already-detached/connectors/{account_id}"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["connector_ids"] == []

    async def test_detach_unknown_agent_returns_404(
        self, client: AsyncClient
    ) -> None:
        """DELETE on a bogus agent name → 404 with the detail message."""
        account_id = await self._create_account(client)

        resp = await client.delete(
            f"/api/agents/no-such-agent/connectors/{account_id}"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Agent not found: no-such-agent"

    async def test_detach_releases_pool_slot(
        self, client: AsyncClient
    ) -> None:
        """After DELETE, the per-(agent, account) pool slot is released
        (verified via ``_keys_for_test``)."""
        from the_one.connectors._pool import (
            _keys_for_test,
            agent_acquire,
        )

        account_id = await self._create_account(client)
        resp = await client.post(
            "/api/agents",
            json={
                "name": "agent-pool-release",
                "connector_ids": [account_id],
            },
        )
        assert resp.status_code in (200, 201), resp.text

        # Warm the per-(agent, account) slot.
        await agent_acquire("agent-pool-release", account_id)
        assert ("agent-pool-release", account_id) in _keys_for_test()

        resp = await client.delete(
            f"/api/agents/agent-pool-release/connectors/{account_id}"
        )
        assert resp.status_code == 200, resp.text

        # The per-(agent, account) slot is gone.
        assert ("agent-pool-release", account_id) not in _keys_for_test()

    async def test_list_connectors_includes_attached_agents_count(
        self, client: AsyncClient
    ) -> None:
        """``GET /api/connectors`` response items carry
        ``attached_agents_count: int`` reflecting the count of agents
        whose ``connector_ids`` includes the account.
        """
        a1 = await self._create_account(client, name="count-acct-1")
        a2 = await self._create_account(client, name="count-acct-2")

        # Two agents attached to a1; zero to a2.
        for name in ("agent-count-a", "agent-count-b"):
            resp = await client.post(
                "/api/agents",
                json={"name": name, "connector_ids": [a1]},
            )
            assert resp.status_code in (200, 201), resp.text

        resp = await client.get("/api/connectors")
        assert resp.status_code == 200, resp.text
        by_id = {row["id"]: row for row in resp.json()}

        assert "attached_agents_count" in by_id[a1]
        assert by_id[a1]["attached_agents_count"] == 2
        assert by_id[a2]["attached_agents_count"] == 0


# ── Chat session endpoints ───────────────────────────────────────────────


class TestChatSessionAPI:
    async def test_crud(self, client: AsyncClient) -> None:
        # Need an agent first
        await client.post("/api/agents", json={"name": "agent1"})

        # Create session
        resp = await client.post(
            "/api/chat/sessions",
            json={"agent_name": "agent1", "title": "Test Chat"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Read
        resp = await client.get(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test Chat"

        # Update
        resp = await client.put(f"/api/chat/sessions/{session_id}", json={"title": "Updated"})
        assert resp.status_code == 200

        # List
        resp = await client.get("/api/chat/sessions")
        assert len(resp.json()) == 1

        # Purge messages
        resp = await client.post(f"/api/chat/sessions/{session_id}/purge")
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200

    async def test_list_by_agent(self, client: AsyncClient) -> None:
        await client.post("/api/agents", json={"name": "a1"})
        await client.post("/api/agents", json={"name": "a2"})
        await client.post("/api/chat/sessions", json={"agent_name": "a1"})
        await client.post("/api/chat/sessions", json={"agent_name": "a2"})
        resp = await client.get("/api/chat/sessions?agent_name=a1")
        assert len(resp.json()) == 1

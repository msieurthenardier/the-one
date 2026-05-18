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


class TestConnectorAccountAPI:
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
        from the_one.db.repositories import ConnectorAccountRepository
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
            repo = ConnectorAccountRepository(conn, get_encryptor(""))
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
            "/api/connector-accounts",
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
        resp = await client.get(f"/api/connector-accounts/{account_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Bot 1"
        assert resp.json()["config"]["workspace"] == "demo"
        assert resp.json()["idle_timeout_seconds"] == 600
        # Empty-secrets baseline mirrors the MCP precedent.
        assert resp.json()["secrets"] == {}

        # Update
        resp = await client.put(
            f"/api/connector-accounts/{account_id}",
            json={"name": "Bot 1 renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Bot 1 renamed"

        # Delete
        resp = await client.delete(f"/api/connector-accounts/{account_id}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        resp = await client.get(f"/api/connector-accounts/{account_id}")
        assert resp.status_code == 404

    async def test_list_returns_masked_secrets(self, client: AsyncClient) -> None:
        """GET /api/connector-accounts masks secret values per-key."""
        await client.post(
            "/api/connector-accounts",
            json={
                "name": "Discord Bot",
                "type": "stub",
                "config": {},
                "secrets": {"BOT_TOKEN": "secret_real_value"},
            },
        )
        resp = await client.get("/api/connector-accounts")
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
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "secret_real_value"},
            },
        )
        account_id = create.json()["id"]
        await client.put(
            f"/api/connector-accounts/{account_id}",
            json={
                "name": "Bot renamed",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "__MASKED__"},
            },
        )
        # ***...alue confirms the stored ciphertext still decrypts to the
        # original "secret_real_value".
        resp = await client.get(f"/api/connector-accounts/{account_id}")
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
        from the_one.connectors._pool import acquire

        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connector-accounts/{account_id}",
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
        from the_one.connectors._pool import acquire

        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connector-accounts/{account_id}",
            json={"session_continuation_seconds": 3600},
        )
        assert resp.status_code == 200

        # Pool entry survives — the new field is NOT part of the eviction trigger.
        assert ("test-agent", account_id) in pool_mod._pool

        # And the new value round-tripped.
        getrr = await client.get(f"/api/connector-accounts/{account_id}")
        assert getrr.json()["session_continuation_seconds"] == 3600

    async def test_dropping_a_key_evicts(self, client: AsyncClient) -> None:
        """PUT with secrets={} drops all keys (REST replace) → eviction fires."""
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import acquire

        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connector-accounts/{account_id}",
            json={"secrets": {}},
        )
        assert resp.status_code == 200

        assert ("test-agent", account_id) not in pool_mod._pool

    async def test_secrets_change_evicts(self, client: AsyncClient) -> None:
        """PUT with a changed secret value evicts the warm entry."""
        from the_one.connectors import _pool as pool_mod
        from the_one.connectors._pool import acquire

        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connector-accounts/{account_id}",
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
        from the_one.connectors._pool import acquire

        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.put(
            f"/api/connector-accounts/{account_id}",
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
        from the_one.connectors._pool import acquire

        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "real"},
            },
        )
        account_id = create.json()["id"]

        await acquire("test-agent", account_id)
        assert ("test-agent", account_id) in pool_mod._pool

        resp = await client.delete(f"/api/connector-accounts/{account_id}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        assert ("test-agent", account_id) not in pool_mod._pool

        resp = await client.get(f"/api/connector-accounts/{account_id}")
        assert resp.status_code == 404

    async def test_types_returns_empty_in_production(
        self, client: AsyncClient
    ) -> None:
        """Without `register_for_test`, /types returns []."""
        from the_one.connectors.registry import clear_for_test

        clear_for_test()
        resp = await client.get("/api/connector-accounts/types")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_types_returns_registered_in_test(
        self, client: AsyncClient
    ) -> None:
        """With register_for_test('stub', StubPlugin), /types returns the stub entry."""
        resp = await client.get("/api/connector-accounts/types")
        assert resp.status_code == 200
        assert resp.json() == [{"value": "stub", "label": "Stub"}]

    async def test_create_with_invalid_payload_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST missing the required ``type`` field returns 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json={"name": "Bot"},  # missing `type`
        )
        assert resp.status_code == 422
        # Pydantic validation error shape — a list of errors per field.
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        assert any("type" in err.get("loc", []) for err in detail)

    async def test_unknown_account_returns_404(self, client: AsyncClient) -> None:
        """GET / PUT / DELETE on an unknown id return 404."""
        resp = await client.get("/api/connector-accounts/nope")
        assert resp.status_code == 404
        assert "Connector account not found" in resp.json()["detail"]

        resp = await client.put(
            "/api/connector-accounts/nope",
            json={"name": "x"},
        )
        assert resp.status_code == 404
        assert "Connector account not found" in resp.json()["detail"]

        resp = await client.delete("/api/connector-accounts/nope")
        assert resp.status_code == 404
        assert "Connector account not found" in resp.json()["detail"]

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
        from the_one.connectors._pool import acquire

        # Setup: stub-typed account with non-empty secrets.
        resp = await client.post(
            "/api/connector-accounts",
            json={
                "name": "rotation-target",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "original_value"},
            },
        )
        assert resp.status_code == 201
        account_id = resp.json()["id"]

        # Acquire warm pool entry.
        await acquire("test-agent", account_id)
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
        await acquire("test-agent", account_id)
        assert key in pool_mod._pool


# ── Connector account doctor probe (F2 L4) ────────────────────────────────


class TestConnectorAccountDoctor:
    """Doctor-probe REST endpoint for connector accounts (F2 L4).

    Mirrors :class:`TestConnectorAccountAPI`'s autouse ``_isolation``
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

        Verbatim copy of :meth:`TestConnectorAccountAPI._isolation` per
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
        from the_one.db.repositories import ConnectorAccountRepository
        from the_one.interfaces.web.api import get_connection, get_encryptor

        await pool_mod._clear_for_test()
        restore_to_baseline_for_test()
        StubPlugin.reset_for_test()
        register_for_test("stub", StubPlugin)

        async def _patched_load_account(account_id, encryptor):
            conn = await get_connection()
            repo = ConnectorAccountRepository(conn, get_encryptor(""))
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
            "/api/connector-accounts",
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
            f"/api/connector-accounts/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "message": "stub probe ok",
            "details": {},
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
            f"/api/connector-accounts/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "failed",
            "message": "bot token revoked",
            "details": {"reason": "401"},
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
            f"/api/connector-accounts/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["message"] == "gateway reachable but slow"
        assert body["details"] == {"latency_ms": 1200}

    async def test_doctor_probe_unknown_type(self, client: AsyncClient) -> None:
        """Account with an unregistered ``type`` → ``{status: 'error', ...}`` 200.

        Mirrors the MCP "unknown transport" pattern so the UI banner
        renders inline rather than triggering a global error handler.
        The autouse fixture pre-registers only ``"stub"``; an account
        with ``type='unregistered-platform'`` is unknown to the registry.

        ``ConnectorAccount.type`` is currently an unconstrained ``str``,
        so the POST validates without rejection. If a future leg
        tightens that field to a ``Literal[...]``, this setup needs to
        switch to repo-level insert.
        """
        resp = await client.post(
            "/api/connector-accounts",
            json={
                "name": "alien",
                "type": "unregistered-platform",
                "secrets": {},
            },
        )
        assert resp.status_code == 201
        account_id = resp.json()["id"]

        resp = await client.post(
            f"/api/connector-accounts/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "error",
            "message": "Unknown connector type: unregistered-platform",
            "details": {
                "error": "type not registered",
                "type": "unregistered-platform",
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
            f"/api/connector-accounts/{account_id}/test/connect"
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
            "/api/connector-accounts/does-not-exist/test/connect"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == (
            "Connector account not found: does-not-exist"
        )

    async def test_doctor_probe_records_the_call(
        self, client: AsyncClient
    ) -> None:
        """Regression net: probe actually dispatches to ``plugin.doctor``."""
        from the_one.connectors._stub import StubPlugin

        account_id = await self._create_stub_account(client)
        resp = await client.post(
            f"/api/connector-accounts/{account_id}/test/connect"
        )
        assert resp.status_code == 200
        assert StubPlugin.doctor_calls == [(account_id, "stub")]


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

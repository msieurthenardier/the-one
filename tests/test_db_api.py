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

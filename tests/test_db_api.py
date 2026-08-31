"""Tests for REST API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.db.repositories import SQLiteAgentStore
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
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
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

    # test_create_agent_persists_connector_always_listen and
    # test_update_agent_clears_connector_always_listen are deleted:
    # Mission 23 Flight 1 (backend-removal leg, step 4) removed the
    # ``connector_always_listen`` field from ``AgentConfig`` entirely.

    async def test_create_agent_persists_chat_history_retention_days(
        self, client: AsyncClient
    ) -> None:
        """POST with ``chat_history_retention_days=90`` round-trips through GET.

        M13 F01 L01: confirms the new per-agent retention field flows through
        the API layer without any api.py change (Pydantic ``model_validate``
        picks up the field automatically and ``cfg.model_dump()`` round-trips
        it in the response).
        """
        payload = {
            "name": "retention-agent",
            "chat_history_retention_days": 90,
        }
        resp = await client.post("/api/agents", json=payload)
        assert resp.status_code == 201
        assert resp.json()["chat_history_retention_days"] == 90

        # GET round-trips the field unchanged (proves the value persisted
        # to the DB and decoded back through _row_to_config).
        resp = await client.get("/api/agents/retention-agent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chat_history_retention_days"] == 90

        # PUT with an updated value also round-trips correctly.
        resp = await client.put(
            "/api/agents/retention-agent",
            json={"name": "retention-agent", "chat_history_retention_days": 180},
        )
        assert resp.status_code == 200
        assert resp.json()["chat_history_retention_days"] == 180

        resp = await client.get("/api/agents/retention-agent")
        assert resp.status_code == 200
        assert resp.json()["chat_history_retention_days"] == 180

    async def test_create_agent_with_out_of_range_retention_days_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST with ``chat_history_retention_days=400`` (> 365) returns 422.

        M13 F01 L01: the ge=1/le=365 Field bound raises ValidationError, which
        the POST endpoint maps to HTTP 422 (mirrors the tool_overrides 422 test
        at line 118).
        """
        resp = await client.post(
            "/api/agents",
            json={"name": "bad-retention", "chat_history_retention_days": 400},
        )
        assert resp.status_code == 422

    # ── M21 F01 L01: mcp_overrides credential masking + preserve-on-PUT ──

    _SECRET_OVERRIDES = {
        "github": {
            "bearer_token": "bearer-realsecretvalue",
            "headers": {"X-Auth": "header-realsecretvalue"},
            "env": {"TOKEN": "env-realsecretvalue"},
            "enabled_tools": ["read_issue"],
            "disabled_tools": ["delete_repo"],
        }
    }

    async def test_list_agents_masks_mcp_override_credentials(self, client: AsyncClient) -> None:
        """AC3 — GET /api/agents masks bearer_token/headers/env; the raw
        plaintext values do not appear anywhere in the response text."""
        await client.post(
            "/api/agents",
            json={"name": "secret-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        assert "bearer-realsecretvalue" not in resp.text
        assert "header-realsecretvalue" not in resp.text
        assert "env-realsecretvalue" not in resp.text
        body = next(a for a in resp.json() if a["name"] == "secret-agent")
        assert body["mcp_overrides"]["github"]["bearer_token"] == "***...alue"
        assert body["mcp_overrides"]["github"]["headers"] == {"X-Auth": "***...alue"}
        assert body["mcp_overrides"]["github"]["env"] == {"TOKEN": "***...alue"}

    async def test_get_agent_masks_mcp_override_credentials(self, client: AsyncClient) -> None:
        """AC3 — GET /api/agents/{name}."""
        await client.post(
            "/api/agents",
            json={"name": "secret-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.get("/api/agents/secret-agent")
        assert resp.status_code == 200
        assert "bearer-realsecretvalue" not in resp.text
        assert "header-realsecretvalue" not in resp.text
        assert "env-realsecretvalue" not in resp.text

    async def test_create_agent_masks_mcp_override_credentials(self, client: AsyncClient) -> None:
        """AC3 — POST /api/agents echoes the response masked (the stored
        value is still the plaintext the client sent — see AC3's
        "POST echoing the payload" edge case)."""
        resp = await client.post(
            "/api/agents",
            json={"name": "secret-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        assert resp.status_code == 201
        assert "bearer-realsecretvalue" not in resp.text
        assert "header-realsecretvalue" not in resp.text
        assert "env-realsecretvalue" not in resp.text

    async def test_update_agent_masks_mcp_override_credentials(self, client: AsyncClient) -> None:
        """AC3 — PUT /api/agents/{name}."""
        await client.post("/api/agents", json={"name": "secret-agent"})
        resp = await client.put(
            "/api/agents/secret-agent",
            json={"name": "secret-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        assert resp.status_code == 200
        assert "bearer-realsecretvalue" not in resp.text
        assert "header-realsecretvalue" not in resp.text
        assert "env-realsecretvalue" not in resp.text

    async def test_rename_agent_masks_mcp_override_credentials(self, client: AsyncClient) -> None:
        """AC3 — POST /api/agents/{name}/rename."""
        await client.post(
            "/api/agents",
            json={"name": "secret-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.post(
            "/api/agents/secret-agent/rename", json={"new_name": "secret-agent-renamed"}
        )
        assert resp.status_code == 200
        assert "bearer-realsecretvalue" not in resp.text
        assert "header-realsecretvalue" not in resp.text
        assert "env-realsecretvalue" not in resp.text

    # test_detach_agent_from_connector_masks_mcp_override_credentials is
    # deleted: Mission 23 Flight 1 (DD-1) removes
    # DELETE /api/agents/{agent_name}/connectors/{account_id} outright.

    async def test_mcp_override_non_secret_keys_stay_clear(self, client: AsyncClient) -> None:
        """AC4 — enabled_tools/disabled_tools inside an mcp_overrides
        source entry, and every tool_overrides value, are returned
        unmasked and byte-identical to what was stored."""
        payload = {
            "name": "clear-fields-agent",
            "tool_overrides": {"shell": {"timeout": 30}},
            "mcp_overrides": self._SECRET_OVERRIDES,
        }
        resp = await client.post("/api/agents", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["tool_overrides"] == {"shell": {"timeout": 30}}
        assert body["mcp_overrides"]["github"]["enabled_tools"] == ["read_issue"]
        assert body["mcp_overrides"]["github"]["disabled_tools"] == ["delete_repo"]

        resp = await client.get("/api/agents/clear-fields-agent")
        body = resp.json()
        assert body["tool_overrides"] == {"shell": {"timeout": 30}}
        assert body["mcp_overrides"]["github"]["enabled_tools"] == ["read_issue"]
        assert body["mcp_overrides"]["github"]["disabled_tools"] == ["delete_repo"]

    async def _load_via_store(self, client: AsyncClient, name: str):
        """Load the stored (plaintext) config through a `SQLiteAgentStore`
        built on the fixture's `conn` + `get_encryptor` patch target —
        the AC5 verification pattern: preserve is verified by loading
        through the store, NOT by re-GETting a masked view. Reaches into
        the module-level patched objects the `client` fixture installed."""
        from the_one.interfaces.web import api as api_module

        conn = api_module.get_connection.return_value
        encryptor = api_module.get_encryptor.return_value
        store = SQLiteAgentStore(conn, encryptor)
        return await store.load(name)

    async def test_put_omitted_credential_key_preserves_stored_value(
        self, client: AsyncClient
    ) -> None:
        """AC5 — omitting a credential key from the PUT payload's source
        entry preserves the stored value for that key."""
        await client.post(
            "/api/agents",
            json={"name": "preserve-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.put(
            "/api/agents/preserve-agent",
            json={
                "name": "preserve-agent",
                "mcp_overrides": {"github": {"enabled_tools": ["read_issue"]}},
            },
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "preserve-agent")
        assert loaded.mcp_overrides["github"]["bearer_token"] == "bearer-realsecretvalue"
        assert loaded.mcp_overrides["github"]["headers"] == {"X-Auth": "header-realsecretvalue"}
        assert loaded.mcp_overrides["github"]["env"] == {"TOKEN": "env-realsecretvalue"}

    async def test_put_masked_credential_value_preserves_stored_value(
        self, client: AsyncClient
    ) -> None:
        """AC5 — a client round-tripping a GET-masked value into a PUT
        preserves the stored value (not the literal mask string)."""
        await client.post(
            "/api/agents",
            json={"name": "preserve-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        get_resp = await client.get("/api/agents/preserve-agent")
        masked_overrides = get_resp.json()["mcp_overrides"]
        resp = await client.put(
            "/api/agents/preserve-agent",
            json={"name": "preserve-agent", "mcp_overrides": masked_overrides},
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "preserve-agent")
        assert loaded.mcp_overrides["github"]["bearer_token"] == "bearer-realsecretvalue"
        assert loaded.mcp_overrides["github"]["headers"] == {"X-Auth": "header-realsecretvalue"}
        assert loaded.mcp_overrides["github"]["env"] == {"TOKEN": "env-realsecretvalue"}

    async def test_put_explicit_null_credential_clears_stored_value(
        self, client: AsyncClient
    ) -> None:
        """AC5 — an explicit `null` for a credential key clears it."""
        await client.post(
            "/api/agents",
            json={"name": "clear-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.put(
            "/api/agents/clear-agent",
            json={
                "name": "clear-agent",
                "mcp_overrides": {
                    "github": {
                        "bearer_token": None,
                        "enabled_tools": ["read_issue"],
                    }
                },
            },
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "clear-agent")
        assert "bearer_token" not in (loaded.mcp_overrides["github"])
        # Other stored credentials, not mentioned in this PUT, are preserved.
        assert loaded.mcp_overrides["github"]["headers"] == {"X-Auth": "header-realsecretvalue"}

    async def test_put_new_credential_value_overwrites_stored_value(
        self, client: AsyncClient
    ) -> None:
        """AC5 — a real (non-masked) incoming value overwrites the
        stored value."""
        await client.post(
            "/api/agents",
            json={"name": "overwrite-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.put(
            "/api/agents/overwrite-agent",
            json={
                "name": "overwrite-agent",
                "mcp_overrides": {"github": {"bearer_token": "brand-new-token-value"}},
            },
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "overwrite-agent")
        assert loaded.mcp_overrides["github"]["bearer_token"] == "brand-new-token-value"

    async def test_put_partially_masked_headers_resolves_per_inner_key(
        self, client: AsyncClient
    ) -> None:
        """Edge case — an incoming `headers` dict that is partially
        masked (operator changed one header): masked inner values
        resolve from stored, new ones overwrite, inner keys absent from
        the payload are dropped."""
        await client.post(
            "/api/agents",
            json={
                "name": "partial-headers-agent",
                "mcp_overrides": {
                    "github": {
                        "headers": {
                            "X-Auth": "auth-realsecretvalue",
                            "X-Other": "other-realsecretvalue",
                        }
                    }
                },
            },
        )
        resp = await client.put(
            "/api/agents/partial-headers-agent",
            json={
                "name": "partial-headers-agent",
                "mcp_overrides": {
                    "github": {
                        "headers": {
                            "X-Auth": "***...alue",  # mask-shaped: preserve
                            "X-New": "brand-new-header-value",  # real: set
                            # X-Other omitted: dropped (payload is
                            # authoritative for shape)
                        }
                    }
                },
            },
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "partial-headers-agent")
        headers = loaded.mcp_overrides["github"]["headers"]
        assert headers["X-Auth"] == "auth-realsecretvalue"
        assert headers["X-New"] == "brand-new-header-value"
        assert "X-Other" not in headers

    async def test_put_masked_value_with_nothing_stored_is_dropped(
        self, client: AsyncClient
    ) -> None:
        """Edge case — a masked value for a key with nothing stored is
        dropped, never persisted as the literal mask string."""
        await client.post("/api/agents", json={"name": "nothing-stored-agent"})
        resp = await client.put(
            "/api/agents/nothing-stored-agent",
            json={
                "name": "nothing-stored-agent",
                "mcp_overrides": {"github": {"bearer_token": "***...abcd"}},
            },
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "nothing-stored-agent")
        overrides = loaded.mcp_overrides or {}
        github_entry = overrides.get("github", {})
        assert "bearer_token" not in github_entry
        assert github_entry.get("bearer_token") != "***...abcd"

    async def test_put_studio_shaped_payload_preserves_credentials(
        self, client: AsyncClient
    ) -> None:
        """A Studio-shaped PUT (payload carries only `enabled_tools` /
        `disabled_tools` — Studio renders no credential fields at all)
        preserves every stored credential."""
        await client.post(
            "/api/agents",
            json={"name": "studio-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.put(
            "/api/agents/studio-agent",
            json={
                "name": "studio-agent",
                "mcp_overrides": {"github": {"enabled_tools": ["read_issue", "list_issues"]}},
            },
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "studio-agent")
        assert loaded.mcp_overrides["github"]["bearer_token"] == "bearer-realsecretvalue"
        assert loaded.mcp_overrides["github"]["headers"] == {"X-Auth": "header-realsecretvalue"}
        assert loaded.mcp_overrides["github"]["env"] == {"TOKEN": "env-realsecretvalue"}
        assert loaded.mcp_overrides["github"]["enabled_tools"] == ["read_issue", "list_issues"]

    async def test_put_mcp_overrides_null_preserves_every_stored_source(
        self, client: AsyncClient
    ) -> None:
        """A PUT with `mcp_overrides: null` cannot be distinguished from
        an omitted key (`data.get()` collapses both to `None`) — AC5
        treats them identically: every stored source is preserved."""
        await client.post(
            "/api/agents",
            json={"name": "null-put-agent", "mcp_overrides": self._SECRET_OVERRIDES},
        )
        resp = await client.put(
            "/api/agents/null-put-agent",
            json={"name": "null-put-agent", "mcp_overrides": None},
        )
        assert resp.status_code == 200
        loaded = await self._load_via_store(client, "null-put-agent")
        assert loaded.mcp_overrides["github"]["bearer_token"] == "bearer-realsecretvalue"

    async def test_post_masked_value_is_dropped_not_persisted(self, client: AsyncClient) -> None:
        """create_agent: no stored row to preserve against, but a
        masked-shaped credential value in a POST body is dropped rather
        than persisted literally."""
        resp = await client.post(
            "/api/agents",
            json={
                "name": "post-masked-agent",
                "mcp_overrides": {"github": {"bearer_token": "***...abcd"}},
            },
        )
        assert resp.status_code == 201
        loaded = await self._load_via_store(client, "post-masked-agent")
        overrides = loaded.mcp_overrides or {}
        github_entry = overrides.get("github", {})
        assert github_entry.get("bearer_token") != "***...abcd"
        assert "bearer_token" not in github_entry

    # test_detaching_a_connector_does_not_clear_orphaned_overrides is
    # deleted: Mission 23 Flight 1 (DD-1) removes
    # DELETE /api/agents/{agent_name}/connectors/{account_id} outright.


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

    async def test_update_with_wrong_type_rejected(self, client: AsyncClient) -> None:
        """Squawk 0013: a malformed field (wrong type) must 422, not silently
        bypass validation via ``model_copy(update=...)`` and corrupt the row."""
        resp = await client.post("/api/knowledge-bases", json={"name": "My KB"})
        kb_id = resp.json()["id"]

        resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": 12345})
        assert resp.status_code == 422

        # The stored row must be unchanged — not a half-applied merge.
        get_resp = await client.get(f"/api/knowledge-bases/{kb_id}")
        assert get_resp.json()["name"] == "My KB"

        # A valid PUT still succeeds.
        resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "Updated KB"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated KB"

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

    async def test_update_with_invalid_type_rejected(self, client: AsyncClient) -> None:
        """Squawk 0013: an unknown ``type`` literal must 422, not silently
        bypass validation via ``model_copy(update=...)`` and corrupt the row."""
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "Test MCP", "type": "stdio", "config": {"command": "python"}},
        )
        source_id = resp.json()["id"]

        resp = await client.put(
            f"/api/mcp-sources/{source_id}",
            json={"name": "Test MCP", "type": "bogus-transport"},
        )
        assert resp.status_code == 422

        # The stored row must be unchanged — not a half-applied merge.
        get_resp = await client.get(f"/api/mcp-sources/{source_id}")
        assert get_resp.json()["type"] == "stdio"

        # A valid PUT still succeeds.
        resp = await client.put(f"/api/mcp-sources/{source_id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

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


# TestConnectorAPI, TestConnectorDoctor, TestConnectorPairingCodeAndAttached,
# TestConnectorPeerApprovals, and TestAgentConnectorDetach are deleted:
# Mission 23 Flight 1 (DD-1) removes all 18 connector REST routes + the
# agent-connector detach route outright. The `connectors` table,
# `ConnectorRepository`, and encryption-rotation enrollment are KEPT —
# just not the HTTP surface over them; Flight 2 rebuilds minimal CRUD +
# doctor routes.


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

    async def test_update_with_wrong_type_rejected(self, client: AsyncClient) -> None:
        """Squawk 0013: a malformed field (wrong type) must 422, not silently
        bypass validation via ``model_copy(update=...)`` and corrupt the row."""
        await client.post("/api/agents", json={"name": "agent-squawk-0013"})
        resp = await client.post(
            "/api/chat/sessions",
            json={"agent_name": "agent-squawk-0013", "title": "Test Chat"},
        )
        session_id = resp.json()["id"]

        resp = await client.put(
            f"/api/chat/sessions/{session_id}", json={"title": {"nested": True}}
        )
        assert resp.status_code == 422

        # The stored row must be unchanged — not a half-applied merge.
        get_resp = await client.get(f"/api/chat/sessions/{session_id}")
        assert get_resp.json()["title"] == "Test Chat"

        # A valid PUT still succeeds.
        resp = await client.put(f"/api/chat/sessions/{session_id}", json={"title": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    async def test_list_by_agent(self, client: AsyncClient) -> None:
        await client.post("/api/agents", json={"name": "a1"})
        await client.post("/api/agents", json={"name": "a2"})
        await client.post("/api/chat/sessions", json={"agent_name": "a1"})
        await client.post("/api/chat/sessions", json={"agent_name": "a2"})
        resp = await client.get("/api/chat/sessions?agent_name=a1")
        assert len(resp.json()) == 1

    async def test_delete_agent_chat_sessions_returns_count(self, client: AsyncClient) -> None:
        """M13 F02 L01: DELETE /api/agents/{name}/chat/sessions purges all of
        an agent's sessions, returns {"status":"ok","deleted":N}, and is
        idempotent — the no-session case returns 200 {"deleted":0}, NOT 404.
        """
        await client.post("/api/agents", json={"name": "a1"})
        await client.post("/api/chat/sessions", json={"agent_name": "a1"})
        await client.post("/api/chat/sessions", json={"agent_name": "a1"})

        resp = await client.delete("/api/agents/a1/chat/sessions")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "deleted": 2}

        # History is gone for that agent.
        resp = await client.get("/api/chat/sessions?agent_name=a1")
        assert resp.status_code == 200
        assert resp.json() == []

        # Idempotent: an agent with no sessions returns 200 {"deleted":0}, not 404.
        await client.post("/api/agents", json={"name": "a-empty"})
        resp = await client.delete("/api/agents/a-empty/chat/sessions")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "deleted": 0}

    async def test_get_session_includes_session_metadata(
        self, client: AsyncClient, tmp_path
    ) -> None:
        """The detail endpoint composition exposes session_metadata; the
        shared _session_summary helper continues NOT to leak it (covered
        by the sibling list test). M11 F13 L5.

        The PUT path round-trips session_metadata through Pydantic's
        ``model_copy(update=data)`` but the repository's ``update``
        emits a column-list INSERT-OR-REPLACE that does NOT include
        ``session_metadata`` (PUT was scoped to title/message-stream
        edits at design time). Cycle-1 medium follow-up: seed via the
        repository's ``set_session_metadata_key`` primitive, which is
        the production write path that the routing dispatcher uses
        through its sibling ``append_to_session_metadata``.
        """
        from the_one.db.repositories import ChatSessionRepository
        from the_one.interfaces.web import api as api_module

        await client.post("/api/agents", json={"name": "agent-meta"})
        resp = await client.post(
            "/api/chat/sessions",
            json={"agent_name": "agent-meta", "title": "Meta Test"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Newly-created session has no session_metadata yet → detail returns null.
        resp = await client.get(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "session_metadata" in body, (
            "detail-endpoint composition must surface the key even when value is null"
        )
        assert body["session_metadata"] is None

        # Seed a routing entry via the repository primitive used by the
        # production dispatcher (the WS path uses
        # ``append_to_session_metadata``; this set_session_metadata_key
        # path overwrites the whole "routing" key — equivalent for the
        # read-back assertion).
        conn = api_module.get_connection.return_value  # patched fixture
        await ChatSessionRepository(conn).set_session_metadata_key(
            session_id,
            "routing",
            [
                {
                    "ts": "2026-05-31T00:00:00",
                    "agent": "agent-meta",
                    "rule_index": 0,
                    "scope": "channel",
                    "match": None,
                    "reason": "test seed",
                    "disposition": "stepped",
                }
            ],
        )

        resp = await client.get(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_metadata"] is not None
        assert "routing" in body["session_metadata"]
        assert len(body["session_metadata"]["routing"]) == 1
        assert body["session_metadata"]["routing"][0]["disposition"] == "stepped"

    async def test_list_sessions_excludes_session_metadata(self, client: AsyncClient) -> None:
        """The list endpoint's shared _session_summary helper does NOT
        leak session_metadata — preserves the architect cycle-1 correction
        (composition-only-on-detail). M11 F13 L5."""
        from the_one.db.repositories import ChatSessionRepository
        from the_one.interfaces.web import api as api_module

        await client.post("/api/agents", json={"name": "agent-list-meta"})
        resp = await client.post(
            "/api/chat/sessions",
            json={"agent_name": "agent-list-meta", "title": "List-Meta Test"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Seed a session_metadata via the repository primitive so a
        # hypothetical leaky helper would have non-null data to expose.
        conn = api_module.get_connection.return_value  # patched fixture
        await ChatSessionRepository(conn).set_session_metadata_key(
            session_id,
            "routing",
            [
                {
                    "ts": "2026-05-31T00:00:00",
                    "agent": "agent-list-meta",
                    "rule_index": 0,
                    "scope": "channel",
                    "match": None,
                    "reason": "list seed",
                    "disposition": "stepped",
                }
            ],
        )

        resp = await client.get("/api/chat/sessions")
        assert resp.status_code == 200
        items = resp.json()
        assert any(item["id"] == session_id for item in items), "seeded session missing from list"
        for item in items:
            assert "session_metadata" not in item, (
                f"list endpoint must not expose session_metadata; got {sorted(item.keys())}"
            )


# TestRoutingAuditSeedEndpoint and TestSessionLookupSeamEndpoint are
# deleted: Mission 23 Flight 1 (DD-6) removes both ``/api/_test``
# connector seams (``POST /chat/sessions/{id}/routing-audit`` and
# ``GET /chat/sessions/lookup``) — their only callers were connector
# browser tests being deleted, and the session-keying columns they read
# are kept, so Flight 2 or 3 can restore them verbatim if new tests want
# them.

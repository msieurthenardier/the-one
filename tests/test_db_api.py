"""Tests for REST API endpoints."""

from __future__ import annotations

import contextlib
import logging
import os
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


# ── Mission 24 Flight 6 Leg 2: tool-name integrity (DD-17) ───────────────


class TestAgentKbToolNames:
    """AC-6: `kb_tool_names` on the four single-agent routes, absent from
    the list route. AC-7: `kb_ids` keep-on-omit."""

    async def test_get_agent_includes_kb_tool_names(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "kb-agent-get", "kb_ids": [kb_id]})
        resp = await client.get("/api/agents/kb-agent-get")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["kb_tool_names"].keys()) == {kb_id}
        name = body["kb_tool_names"][kb_id]
        assert name.startswith("kb__Docs_")
        assert name.endswith("__search")

    async def test_create_agent_includes_kb_tool_names(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        resp = await client.post("/api/agents", json={"name": "kb-agent-create", "kb_ids": [kb_id]})
        assert resp.status_code == 201
        assert kb_id in resp.json()["kb_tool_names"]

    async def test_update_agent_includes_kb_tool_names(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "kb-agent-put"})
        resp = await client.put(
            "/api/agents/kb-agent-put",
            json={"name": "kb-agent-put", "kb_ids": [kb_id]},
        )
        assert resp.status_code == 200
        assert kb_id in resp.json()["kb_tool_names"]

    async def test_rename_agent_includes_kb_tool_names(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "kb-agent-rn", "kb_ids": [kb_id]})
        resp = await client.post(
            "/api/agents/kb-agent-rn/rename", json={"new_name": "kb-agent-rn-2"}
        )
        assert resp.status_code == 200
        assert kb_id in resp.json()["kb_tool_names"]

    async def test_list_agents_does_not_include_kb_tool_names(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "kb-agent-list", "kb_ids": [kb_id]})
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        body = next(a for a in resp.json() if a["name"] == "kb-agent-list")
        assert "kb_tool_names" not in body

    async def test_dangling_kb_id_contributes_no_entry_and_does_not_fail(
        self, client: AsyncClient
    ) -> None:
        # DD-14: `kb_ids` keeps a dangling id after its knowledge base is
        # deleted (out of this leg's scope to change) — the response must
        # still succeed, just with no entry for it.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Ghost"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "kb-agent-ghost", "kb_ids": [kb_id]})
        await client.delete(f"/api/knowledge-bases/{kb_id}")
        resp = await client.get("/api/agents/kb-agent-ghost")
        assert resp.status_code == 200
        assert resp.json()["kb_tool_names"] == {}

    async def test_put_omitting_kb_ids_preserves_stored_value(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "kb-preserve-agent", "kb_ids": [kb_id]})
        resp = await client.put(
            "/api/agents/kb-preserve-agent",
            json={"name": "kb-preserve-agent", "description": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["kb_ids"] == [kb_id]

    async def test_put_explicit_empty_kb_ids_clears_it(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "kb-clear-agent", "kb_ids": [kb_id]})
        resp = await client.put(
            "/api/agents/kb-clear-agent",
            json={"name": "kb-clear-agent", "kb_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["kb_ids"] == []

    async def test_put_omitting_both_kb_ids_and_mcp_overrides_preserves_both(
        self, client: AsyncClient
    ) -> None:
        # Edge Case: the two preserves are independent — neither may
        # clobber the other when both are omitted from the same PUT.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        secret_overrides = {"github": {"bearer_token": "bearer-realsecretvalue"}}
        await client.post(
            "/api/agents",
            json={
                "name": "kb-and-mcp-preserve-agent",
                "kb_ids": [kb_id],
                "mcp_overrides": secret_overrides,
            },
        )
        resp = await client.put(
            "/api/agents/kb-and-mcp-preserve-agent",
            json={"name": "kb-and-mcp-preserve-agent", "description": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["kb_ids"] == [kb_id]

        from the_one.interfaces.web import api as api_module

        conn = api_module.get_connection.return_value
        encryptor = api_module.get_encryptor.return_value
        store = SQLiteAgentStore(conn, encryptor)
        loaded = await store.load("kb-and-mcp-preserve-agent")
        assert loaded.kb_ids == [kb_id]
        assert loaded.mcp_overrides["github"]["bearer_token"] == "bearer-realsecretvalue"


class TestKnowledgeBaseRenameRewrite:
    """AC-8, AC-9, AC-10, AC-12: renaming a knowledge base rewrites
    `disabled_tools` across attached agents (L2-D7/L2-D9)."""

    async def test_rename_rewrites_disabled_tools_entry(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        agent_resp = await client.post(
            "/api/agents", json={"name": "renamed-kb-agent", "kb_ids": [kb_id]}
        )
        old_name = agent_resp.json()["kb_tool_names"][kb_id]
        await client.put(
            "/api/agents/renamed-kb-agent",
            json={
                "name": "renamed-kb-agent",
                "kb_ids": [kb_id],
                "disabled_tools": [old_name],
            },
        )

        resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "Docs Renamed"})
        assert resp.status_code == 200

        agent_after = await client.get("/api/agents/renamed-kb-agent")
        new_name = agent_after.json()["kb_tool_names"][kb_id]
        assert new_name != old_name
        assert agent_after.json()["disabled_tools"] == [new_name]

    async def test_rename_leaves_non_matching_entries_and_unattached_agent_untouched(
        self, client: AsyncClient
    ) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post(
            "/api/agents",
            json={"name": "no-match-agent", "kb_ids": [kb_id], "disabled_tools": ["shell"]},
        )
        await client.post("/api/agents", json={"name": "unattached-agent"})

        resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "Docs Renamed"})
        assert resp.status_code == 200

        no_match = await client.get("/api/agents/no-match-agent")
        assert no_match.json()["disabled_tools"] == ["shell"]
        unattached = await client.get("/api/agents/unattached-agent")
        assert unattached.json()["disabled_tools"] == []

    async def test_rename_does_not_touch_enabled_tools(self, client: AsyncClient) -> None:
        # AC-9: a `kb__` name placed in enabled_tools is inert
        # (UNGATED_TOOL_PREFIXES) and must survive a rename untouched —
        # the v7 migration precedent rewrites both columns; this
        # deliberately does not.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        agent_resp = await client.post(
            "/api/agents", json={"name": "enabled-kb-agent", "kb_ids": [kb_id]}
        )
        old_name = agent_resp.json()["kb_tool_names"][kb_id]
        await client.put(
            "/api/agents/enabled-kb-agent",
            json={
                "name": "enabled-kb-agent",
                "kb_ids": [kb_id],
                "disabled_tools": [old_name],
                "enabled_tools": [old_name, "shell"],
            },
        )

        resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "Docs Renamed"})
        assert resp.status_code == 200

        agent_after = await client.get("/api/agents/enabled-kb-agent")
        assert agent_after.json()["enabled_tools"] == [old_name, "shell"]

    async def _track_agent_store_calls(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        calls: list[str] = []
        original_load = SQLiteAgentStore.load
        original_save = SQLiteAgentStore.save

        async def _tracked_load(self, name):
            calls.append(f"load:{name}")
            return await original_load(self, name)

        async def _tracked_save(self, cfg):
            calls.append(f"save:{cfg.name}")
            return await original_save(self, cfg)

        monkeypatch.setattr(SQLiteAgentStore, "load", _tracked_load)
        monkeypatch.setattr(SQLiteAgentStore, "save", _tracked_save)
        return calls

    async def test_rename_to_identical_name_touches_no_agent(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # AC-10, case 1: the raw `name` field is unchanged — a PUT that
        # only touches e.g. `description` must not load/save any agent.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "noop-rename-agent", "kb_ids": [kb_id]})

        calls = await self._track_agent_store_calls(monkeypatch)
        resp = await client.put(
            f"/api/knowledge-bases/{kb_id}", json={"name": "Docs", "description": "updated"}
        )
        assert resp.status_code == 200
        assert calls == []

    async def test_description_only_save_leaves_disabled_tools_byte_identical(
        self, client: AsyncClient
    ) -> None:
        # M24 F06 L05 AC-5: complements
        # test_rename_to_identical_name_touches_no_agent's implementation-
        # level "zero store calls" assertion with a behavior-level one —
        # fetch the agent before and after a description-only save and
        # assert `disabled_tools` is byte-identical. This is L5-D2's
        # load-bearing claim (verified at design review against source,
        # not assumed): a description-only PUT performs zero agent I/O
        # because `update_knowledge_base`'s first early return (L2-D9)
        # fires on the raw name being unchanged.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        agent_resp = await client.post(
            "/api/agents", json={"name": "desc-only-save-agent", "kb_ids": [kb_id]}
        )
        old_name = agent_resp.json()["kb_tool_names"][kb_id]
        await client.put(
            "/api/agents/desc-only-save-agent",
            json={
                "name": "desc-only-save-agent",
                "kb_ids": [kb_id],
                "disabled_tools": [old_name],
            },
        )
        before = (await client.get("/api/agents/desc-only-save-agent")).json()["disabled_tools"]

        resp = await client.put(
            f"/api/knowledge-bases/{kb_id}",
            json={"name": "Docs", "description": "a new description"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "a new description"

        after = (await client.get("/api/agents/desc-only-save-agent")).json()["disabled_tools"]
        assert after == before == [old_name]

    async def test_rename_normalizing_to_same_slug_touches_no_agent(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # AC-10, case 2: "My Notes" and "My/Notes" both normalize to the
        # same "My_Notes" slug — the raw name differs but the derived
        # tool name does not, so no agent should be touched either.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "My Notes"})
        kb_id = kb_resp.json()["id"]
        await client.post("/api/agents", json={"name": "slug-noop-agent", "kb_ids": [kb_id]})

        calls = await self._track_agent_store_calls(monkeypatch)
        resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "My/Notes"})
        assert resp.status_code == 200
        assert calls == []

    async def test_rename_partial_failure_does_not_raise_and_warns(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # AC-12: one agent's save() failing (encryptor round-trip,
        # constraint, anything) must not propagate as an unhandled 500
        # after the knowledge-base row has already been renamed, and the
        # failed agent must be named in a WARNING.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        agent_resp = await client.post(
            "/api/agents", json={"name": "fails-agent", "kb_ids": [kb_id]}
        )
        old_name = agent_resp.json()["kb_tool_names"][kb_id]
        await client.put(
            "/api/agents/fails-agent",
            json={"name": "fails-agent", "kb_ids": [kb_id], "disabled_tools": [old_name]},
        )

        original_save = SQLiteAgentStore.save

        async def _flaky_save(self, cfg):
            if cfg.name == "fails-agent":
                raise RuntimeError("boom")
            return await original_save(self, cfg)

        monkeypatch.setattr(SQLiteAgentStore, "save", _flaky_save)

        with caplog.at_level(logging.WARNING):
            resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "Docs Renamed"})
        assert resp.status_code == 200
        # The knowledge base itself was renamed despite the agent failure.
        assert resp.json()["name"] == "Docs Renamed"
        assert any("fails-agent" in r.message for r in caplog.records)

    async def test_rename_agent_store_acquisition_failure_does_not_raise_and_warns(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Phase 2d review fix: `_agent_store()` runs BEFORE
        # `rename_kb_tool_references` is even entered, so a failure there
        # used to raise past this endpoint as an unhandled 500 *after* the
        # knowledge-base row had already been renamed, with no WARNING at
        # all (the per-agent try/except never got a chance to run). The
        # endpoint must instead log a WARNING and complete the rename.
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "Docs"})
        kb_id = kb_resp.json()["id"]
        agent_resp = await client.post(
            "/api/agents", json={"name": "store-acquire-fail-agent", "kb_ids": [kb_id]}
        )
        old_name = agent_resp.json()["kb_tool_names"][kb_id]
        await client.put(
            "/api/agents/store-acquire-fail-agent",
            json={
                "name": "store-acquire-fail-agent",
                "kb_ids": [kb_id],
                "disabled_tools": [old_name],
            },
        )

        from the_one.interfaces.web import api as api_module

        original_agent_store = api_module._agent_store

        async def _flaky_agent_store():
            raise RuntimeError("boom")

        monkeypatch.setattr(api_module, "_agent_store", _flaky_agent_store)

        with caplog.at_level(logging.WARNING):
            resp = await client.put(f"/api/knowledge-bases/{kb_id}", json={"name": "Docs Renamed"})
        assert resp.status_code == 200
        # The knowledge base itself was renamed despite the acquisition failure.
        assert resp.json()["name"] == "Docs Renamed"
        assert any(kb_id in r.message and "acquire" in r.message for r in caplog.records)

        # The agent was never examined (the store never got acquired), so
        # its disabled_tools entry is still the stale, un-rewritten name —
        # confirmed by re-reading through the real (unpatched) store.
        monkeypatch.setattr(api_module, "_agent_store", original_agent_store)
        agent_after = await client.get("/api/agents/store-acquire-fail-agent")
        assert agent_after.json()["disabled_tools"] == [old_name]


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

    async def test_create_with_path_traversal_id_returns_422(self, client: AsyncClient) -> None:
        """Leg 5 review fix (BLOCKING 2): a client-supplied ``id`` reaches
        ``KnowledgeBase`` verbatim and is later used to build a filesystem
        path (``UsearchStore._path_for``) — a path-traversal-shaped id must
        422, not silently be stored (and later crash or escape the vectors
        directory)."""
        resp = await client.post("/api/knowledge-bases", json={"id": "../x", "name": "Evil KB"})
        assert resp.status_code == 422

        # Nothing was created under that id.
        resp = await client.get("/api/knowledge-bases")
        assert resp.json() == []

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

    async def test_create_item_unknown_kb_returns_404_not_500(self, client: AsyncClient) -> None:
        """R8: an unknown ``kb_id`` on item create must 404, not surface the
        FK IntegrityError as an unhandled 500."""
        resp = await client.post(
            "/api/knowledge-bases/no-such-kb/items",
            json={"type": "file", "path_or_url": "/tmp/x.txt"},
        )
        assert resp.status_code == 404

    async def test_get_item(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "KB"})
        kb_id = kb_resp.json()["id"]
        item_resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "file", "path_or_url": "/tmp/x.txt"},
        )
        item_id = item_resp.json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == item_id
        assert resp.json()["path_or_url"] == "/tmp/x.txt"

    async def test_get_item_unknown_id_404(self, client: AsyncClient) -> None:
        kb_resp = await client.post("/api/knowledge-bases", json={"name": "KB"})
        kb_id = kb_resp.json()["id"]
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/no-such-item")
        assert resp.status_code == 404

    async def test_get_item_other_kb_404(self, client: AsyncClient) -> None:
        """R8 scoping: an id that belongs to a DIFFERENT KB reads as
        unknown — same status/shape as a truly-missing id."""
        kb1 = (await client.post("/api/knowledge-bases", json={"name": "KB1"})).json()["id"]
        kb2 = (await client.post("/api/knowledge-bases", json={"name": "KB2"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb1}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb2}/items/{item_id}")
        assert resp.status_code == 404

    async def test_delete_item_other_kb_404(self, client: AsyncClient) -> None:
        kb1 = (await client.post("/api/knowledge-bases", json={"name": "KB1"})).json()["id"]
        kb2 = (await client.post("/api/knowledge-bases", json={"name": "KB2"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb1}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        resp = await client.delete(f"/api/knowledge-bases/{kb2}/items/{item_id}")
        assert resp.status_code == 404

        # The item survives — the cross-KB delete must not have succeeded.
        resp = await client.get(f"/api/knowledge-bases/{kb1}/items/{item_id}")
        assert resp.status_code == 200

    async def test_retry_moves_failed_to_pending(self, client: AsyncClient) -> None:
        from the_one.db._write_lock import write_transaction
        from the_one.db.repositories import KBItemRepository

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        # Drive the item to 'failed' directly via the repository (no route
        # exists to do this yet — Leg 2/3 territory) using the SAME patched
        # connection the test client's app uses.
        from the_one.interfaces.web import api as api_module

        conn = await api_module.get_connection()
        repo = KBItemRepository(conn)
        async with write_transaction(conn):
            await conn.execute("UPDATE kb_items SET status='indexing' WHERE id=?", (item_id,))
        await repo.update_status(item_id, "failed", error="boom")

        resp = await client.post(f"/api/knowledge-bases/{kb_id}/items/{item_id}/retry")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert resp.json()["error"] is None

    async def test_retry_moves_indexing_to_pending(self, client: AsyncClient) -> None:
        from the_one.db._write_lock import write_transaction
        from the_one.interfaces.web import api as api_module

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        conn = await api_module.get_connection()
        async with write_transaction(conn):
            await conn.execute("UPDATE kb_items SET status='indexing' WHERE id=?", (item_id,))

        resp = await client.post(f"/api/knowledge-bases/{kb_id}/items/{item_id}/retry")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_retry_other_status_409(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]
        # Fresh item is 'pending' — not a valid retry source.
        resp = await client.post(f"/api/knowledge-bases/{kb_id}/items/{item_id}/retry")
        assert resp.status_code == 409

    async def test_retry_unknown_id_404(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(f"/api/knowledge-bases/{kb_id}/items/no-such-item/retry")
        assert resp.status_code == 404

    async def test_retry_other_kb_404(self, client: AsyncClient) -> None:
        kb1 = (await client.post("/api/knowledge-bases", json={"name": "KB1"})).json()["id"]
        kb2 = (await client.post("/api/knowledge-bases", json={"name": "KB2"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb1}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]
        resp = await client.post(f"/api/knowledge-bases/{kb2}/items/{item_id}/retry")
        assert resp.status_code == 404


class TestKnowledgeBaseFolderRegistration:
    """Flight 3 Leg 1, AC-10: ``POST .../items`` with ``type: "folder"`` —
    the DD-1 validation order (existence -> root -> containment),
    canonicalisation, the ``ValidationError`` -> 422 handler, and the
    ``_after_folder_registered`` no-op seam."""

    async def test_valid_folder_registers_201_with_canonical_path(
        self, client: AsyncClient, tmp_path
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()

        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        assert resp.status_code == 201
        assert resp.json()["path_or_url"] == str(folder.resolve())

    async def test_relative_path_is_canonicalised(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "relative-docs"
        folder.mkdir()
        monkeypatch.chdir(tmp_path)

        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": "relative-docs"},
        )
        assert resp.status_code == 201
        assert resp.json()["path_or_url"] == str(folder.resolve())

    async def test_tilde_path_is_canonicalised(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "home-docs"
        folder.mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))

        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": "~/home-docs"},
        )
        assert resp.status_code == 201
        assert resp.json()["path_or_url"] == str(folder.resolve())

    async def test_symlinked_path_resolves_to_target(self, client: AsyncClient, tmp_path) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as e:
            pytest.skip(f"os.symlink not supported on this platform: {e}")

        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(link)},
        )
        assert resp.status_code == 201
        assert resp.json()["path_or_url"] == str(target.resolve())

    async def test_nonexistent_path_422(self, client: AsyncClient, tmp_path) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(tmp_path / "nope")},
        )
        assert resp.status_code == 422

    async def test_existing_file_path_422(self, client: AsyncClient, tmp_path) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        f = tmp_path / "afile.txt"
        f.write_text("x")
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(f)},
        )
        assert resp.status_code == 422

    async def test_filesystem_root_422(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": "/"},
        )
        assert resp.status_code == 422

    async def test_overlapping_folder_same_kb_409_with_conflicting_item_id(
        self, client: AsyncClient, tmp_path
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        root_folder = tmp_path / "root"
        root_folder.mkdir()
        first = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(root_folder)},
        )
        assert first.status_code == 201
        first_id = first.json()["id"]

        # Equal path.
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(root_folder)},
        )
        assert resp.status_code == 409
        assert first_id in resp.json()["detail"]

        # Inside the registered folder.
        inner = root_folder / "inner"
        inner.mkdir()
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(inner)},
        )
        assert resp.status_code == 409
        assert first_id in resp.json()["detail"]

        # Containing the registered folder.
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(tmp_path)},
        )
        assert resp.status_code == 409
        assert first_id in resp.json()["detail"]

    async def test_same_folder_different_kb_201(self, client: AsyncClient, tmp_path) -> None:
        kb1 = (await client.post("/api/knowledge-bases", json={"name": "KB1"})).json()["id"]
        kb2 = (await client.post("/api/knowledge-bases", json={"name": "KB2"})).json()["id"]
        folder = tmp_path / "shared"
        folder.mkdir()

        resp1 = await client.post(
            f"/api/knowledge-bases/{kb1}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        assert resp1.status_code == 201
        resp2 = await client.post(
            f"/api/knowledge-bases/{kb2}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        assert resp2.status_code == 201

    async def test_check_order_nonexistent_path_under_registered_folder_is_422_not_409(
        self, client: AsyncClient, tmp_path
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        root_folder = tmp_path / "root"
        root_folder.mkdir()
        first = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(root_folder)},
        )
        assert first.status_code == 201

        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(root_folder / "does-not-exist")},
        )
        assert resp.status_code == 422

    async def test_file_and_url_items_unchanged(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "file", "path_or_url": "/tmp/nonexistent-does-not-matter.txt"},
        )
        assert resp.status_code == 201
        resp2 = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "url", "path_or_url": "http://example.com"},
        )
        assert resp2.status_code == 201

    async def test_malformed_body_422_via_validation_error_handler(
        self, client: AsyncClient
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "not-a-real-type", "path_or_url": "/x"},
        )
        assert resp.status_code == 422

    async def test_after_folder_registered_called_once_with_kb_id(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        from the_one.interfaces.web import api as api_module

        calls = []
        monkeypatch.setattr(
            api_module, "_after_folder_registered", lambda kb_id, item: calls.append((kb_id, item))
        )

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        assert resp.status_code == 201
        assert len(calls) == 1
        called_kb_id, called_item = calls[0]
        assert called_kb_id == kb_id
        assert called_item.id == resp.json()["id"]

    async def test_after_folder_registered_not_called_for_file_item(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.interfaces.web import api as api_module

        calls = []
        monkeypatch.setattr(
            api_module, "_after_folder_registered", lambda kb_id, item: calls.append((kb_id, item))
        )

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "file", "path_or_url": "/tmp/x.txt"},
        )
        assert resp.status_code == 201
        assert calls == []


class TestKnowledgeBaseFolderRegistrationDataDirRefusal:
    """Flight 4 Leg 1, DD-6, AC-3: registering a folder that equals,
    contains, or lies inside the application data directory is refused
    with 422 before the sibling-containment scan; the check runs after
    the existence check (a non-existent path inside the data directory
    still reads the non-existence message, never the data-dir one)."""

    async def test_equal_to_data_dir_422(self, client: AsyncClient, tmp_path, monkeypatch) -> None:
        from the_one.config import settings

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(settings, "data_dir", data_dir)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(data_dir)},
        )
        assert resp.status_code == 422
        assert "data directory" in resp.json()["detail"]

    async def test_contains_data_dir_422(self, client: AsyncClient, tmp_path, monkeypatch) -> None:
        from the_one.config import settings

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(settings, "data_dir", data_dir)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(tmp_path)},
        )
        assert resp.status_code == 422
        assert "data directory" in resp.json()["detail"]

    async def test_contains_nonexistent_data_dir_422(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        """Edge Case: a fresh install, before anything has written to
        ``data_dir`` yet — ``is_within`` resolves with ``strict=False``, so
        the "contains" refusal must still fire even though ``data_dir``
        does not exist on disk."""
        from the_one.config import settings

        data_dir = tmp_path / "data"  # deliberately never created
        monkeypatch.setattr(settings, "data_dir", data_dir)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(tmp_path)},
        )
        assert resp.status_code == 422
        assert "data directory" in resp.json()["detail"]

    async def test_inside_data_dir_422(self, client: AsyncClient, tmp_path, monkeypatch) -> None:
        from the_one.config import settings

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(settings, "data_dir", data_dir)
        inner = data_dir / "vectors"
        inner.mkdir()

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(inner)},
        )
        assert resp.status_code == 422
        assert "data directory" in resp.json()["detail"]

    async def test_nonexistent_path_inside_data_dir_422_for_nonexistence(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        """Check order: existence first, so a missing path inside the data
        directory still reports the non-existence detail, not the
        data-dir one."""
        from the_one.config import settings

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(settings, "data_dir", data_dir)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(data_dir / "missing")},
        )
        assert resp.status_code == 422
        assert "data directory" not in resp.json()["detail"]
        assert "does not exist" in resp.json()["detail"]

    async def test_sibling_of_data_dir_registers_201(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        from the_one.config import settings

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(settings, "data_dir", data_dir)
        docs = tmp_path / "docs"
        docs.mkdir()

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(docs)},
        )
        assert resp.status_code == 201


class TestKnowledgeBaseCreateWarmsUpEmbeddingBackend:
    """M24 F02 L03, DD-1, AC-5: creating a KB kicks the embedding warm-up
    exactly once on a cold process; a second creation does not kick it
    again. The loader is monkeypatched throughout — no real model load.
    """

    async def test_create_kicks_warm_up_once_and_second_create_does_not(
        self, client: AsyncClient
    ) -> None:
        import asyncio

        from tests._embedding_stub import StubEmbeddingBackend
        from the_one import embeddings

        calls = {"n": 0}

        def _fake_load() -> StubEmbeddingBackend:
            calls["n"] += 1
            return StubEmbeddingBackend()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(embeddings.LocalStaticBackend, "load", staticmethod(_fake_load))
            embeddings._reset_for_test()

            resp = await client.post("/api/knowledge-bases", json={"name": "KB"})
            assert resp.status_code == 201
            for _ in range(50):
                if calls["n"]:
                    break
                await asyncio.sleep(0.01)
            assert calls["n"] == 1

            resp2 = await client.post("/api/knowledge-bases", json={"name": "KB2"})
            assert resp2.status_code == 201
            await asyncio.sleep(0.05)
            assert calls["n"] == 1

        embeddings._reset_for_test()


class TestKnowledgeBaseDeleteCallsVectorStore:
    """Flight 2 Leg 4, AC-11: the delete routes call the vector store's
    ``delete_kb`` / ``delete`` methods after the repository transaction,
    via a recording stub store injected through ``_reset_for_test()`` plus
    a monkeypatched ``_build_store`` seam — never a real backend."""

    @pytest.fixture(autouse=True)
    def _isolate_vector_store(self, client: AsyncClient, monkeypatch):
        """Route the dispatcher's own ``get_connection()`` to the SAME
        connection the test client's app uses. ``the_one.vectors`` imports
        its own ``get_connection`` reference, independent of the
        ``client`` fixture's patch on
        ``the_one.interfaces.web.api.get_connection`` — without this, the
        first vector-store call would build (and open) a connection to
        the real production database as a side effect of this test."""
        from the_one import vectors as vectors_module
        from the_one.interfaces.web import api as api_module

        monkeypatch.setattr(vectors_module, "get_connection", api_module.get_connection)
        vectors_module._reset_for_test()
        yield
        vectors_module._reset_for_test()

    @staticmethod
    def _recording_store():
        calls: list[tuple] = []

        class _RecordingStore:
            backend = "stub"
            dtype = "float32"
            dim = 512

            async def open(self) -> None:
                return None

            async def upsert(self, kb_id, ids, vectors) -> None:
                calls.append(("upsert", kb_id, list(ids)))

            async def delete(self, kb_id, ids) -> None:
                calls.append(("delete", kb_id, list(ids)))

            async def delete_kb(self, kb_id) -> None:
                calls.append(("delete_kb", kb_id))

            async def query(self, kb_id, vector, k):
                return []

            async def count(self, kb_id) -> int:
                return 0

            async def flush(self, kb_id) -> None:
                return None

            async def close(self) -> None:
                return None

        return _RecordingStore(), calls

    async def test_delete_knowledge_base_calls_delete_kb(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one import vectors as vectors_module

        store, calls = self._recording_store()
        monkeypatch.setattr(vectors_module, "_build_store", lambda settings, conn: store)
        vectors_module._reset_for_test()

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.delete(f"/api/knowledge-bases/{kb_id}")

        assert resp.status_code == 200
        assert ("delete_kb", kb_id) in calls

    async def test_delete_kb_item_calls_delete_with_the_chunk_ids(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one import vectors as vectors_module
        from the_one.db._kb_types import ChunkRecord
        from the_one.db.repositories import KBChunkRepository
        from the_one.interfaces.web import api as api_module

        store, calls = self._recording_store()
        monkeypatch.setattr(vectors_module, "_build_store", lambda settings, conn: store)
        vectors_module._reset_for_test()

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        conn = await api_module.get_connection()
        chunk_repo = KBChunkRepository(conn)
        ids = await chunk_repo.replace_item_chunks(
            item_id,
            kb_id,
            [ChunkRecord(seq=0, text="hello world", char_start=0, char_end=11)],
        )

        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/{item_id}")

        assert resp.status_code == 200
        assert ("delete", kb_id, ids) in calls

    async def test_delete_folder_item_calls_delete_with_every_descendant_chunk_id(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """Flight 3 Leg 1, AC-11: no route change was needed —
        ``delete_kb_item`` already forwards whatever ``repo.delete``
        returns; the widened repository method is the whole fix."""
        from the_one import vectors as vectors_module
        from the_one.db._kb_types import ChunkRecord
        from the_one.db.models import KBItem
        from the_one.db.repositories import KBChunkRepository, KBItemRepository
        from the_one.interfaces.web import api as api_module

        store, calls = self._recording_store()
        monkeypatch.setattr(vectors_module, "_build_store", lambda settings, conn: store)
        vectors_module._reset_for_test()

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]

        conn = await api_module.get_connection()
        item_repo = KBItemRepository(conn)
        chunk_repo = KBChunkRepository(conn)
        await item_repo.create(
            KBItem(id="folder1", kb_id=kb_id, type="folder", path_or_url="/tmp/root")
        )
        await item_repo.create(
            KBItem(
                id="child1",
                kb_id=kb_id,
                parent_id="folder1",
                type="file",
                path_or_url="/tmp/root/a",
            )
        )
        ids = await chunk_repo.replace_item_chunks(
            "child1",
            kb_id,
            [ChunkRecord(seq=0, text="hello folder world", char_start=0, char_end=11)],
        )

        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/folder1")

        assert resp.status_code == 200
        assert ("delete", kb_id, ids) in calls

    async def test_store_failure_is_logged_and_the_route_still_returns_200(
        self, client: AsyncClient, monkeypatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from the_one import vectors as vectors_module

        class _BoomStore:
            backend = "stub"
            dtype = "float32"
            dim = 512

            async def open(self) -> None:
                return None

            async def upsert(self, kb_id, ids, vectors) -> None:
                return None

            async def delete(self, kb_id, ids) -> None:
                return None

            async def delete_kb(self, kb_id) -> None:
                raise RuntimeError("simulated store failure")

            async def query(self, kb_id, vector, k):
                return []

            async def count(self, kb_id) -> int:
                return 0

            async def flush(self, kb_id) -> None:
                return None

            async def close(self) -> None:
                return None

        monkeypatch.setattr(vectors_module, "_build_store", lambda settings, conn: _BoomStore())
        vectors_module._reset_for_test()

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        with caplog.at_level("ERROR"):
            resp = await client.delete(f"/api/knowledge-bases/{kb_id}")

        assert resp.status_code == 200
        assert any("vector store" in record.message.lower() for record in caplog.records)


class _FakeIndexingManager:
    """Flight 3 Leg 3: records ``request_index``/``stop`` calls in order
    and returns a scripted ``state()`` — installed via
    ``monkeypatch.setattr(manager_mod, "_manager", fake)`` (the same
    accessor ``get_indexing_manager()`` reads).

    Flight 4 Leg 3 review fix: ``calls`` accepts an existing list so a
    cross-manager ordering test can share one sequence between this fake
    and ``_FakeWatchManager`` (and a patched repository delete) — proving
    the actual interleaving, not just each manager's own internal order.
    Defaults to a fresh list so existing single-manager tests are
    unaffected.
    """

    def __init__(self, state: str = "idle", calls: list[tuple] | None = None) -> None:
        self.calls: list[tuple] = calls if calls is not None else []
        self._state = state

    def request_index(self, kb_id: str) -> None:
        self.calls.append(("request_index", kb_id))

    async def stop(self, kb_id: str) -> None:
        self.calls.append(("stop", kb_id))

    def state(self, kb_id: str) -> str:
        return self._state


class _FakeWatchManager:
    """Flight 4 Leg 3: records ``start``/``stop``/``stop_kb``/
    ``suppress``/``apply_settings`` calls in order and returns scripted
    ``state()``/``error()`` — installed via ``monkeypatch.setattr(
    watcher_mod, "_manager", fake)`` (the same accessor ``get_watch_
    manager()`` reads)."""

    def __init__(
        self,
        state: str = "off",
        error: str | None = None,
        calls: list[tuple] | None = None,
    ) -> None:
        # Flight 4 Leg 3 review fix: opt-in shared ``calls`` list (see
        # ``_FakeIndexingManager`` docstring above) — defaults to a fresh
        # list for every other Leg 3 test.
        self.calls: list[tuple] = calls if calls is not None else []
        self._state = state
        self._error = error

    def start(self, kb_id: str, folder) -> None:
        self.calls.append(("start", kb_id, folder))

    async def stop(self, folder_id: str) -> None:
        self.calls.append(("watch_stop", folder_id))

    async def stop_kb(self, kb_id: str) -> None:
        self.calls.append(("stop_kb", kb_id))

    def state(self, folder_id: str) -> str:
        return self._state

    def error(self, folder_id: str) -> str | None:
        return self._error

    async def apply_settings(self, m) -> None:
        self.calls.append(("apply_settings", m))

    @contextlib.asynccontextmanager
    async def suppress(self, kb_id: str):
        self.calls.append(("suppress_enter", kb_id))
        try:
            yield
        finally:
            self.calls.append(("suppress_exit", kb_id))


def _patch_kb_delete_records(monkeypatch: pytest.MonkeyPatch, calls: list[tuple]) -> None:
    """Flight 4 Leg 3 review fix: wrap ``KnowledgeBaseRepository.delete``
    so the repository delete step itself lands on the shared ``calls``
    list at the point it actually runs — AC-3's cross-manager ordering
    tests need this to prove ``delete`` falls between the manager
    stop calls and ``suppress_exit``, not just that the two managers'
    own calls are internally ordered. Calls through to the real
    implementation (or its ``KeyError`` on an unknown id) unchanged.
    """
    from the_one.db import repositories as repositories_mod

    original = repositories_mod.KnowledgeBaseRepository.delete

    async def _patched(self, kb_id: str) -> None:
        calls.append(("delete", kb_id))
        await original(self, kb_id)

    monkeypatch.setattr(repositories_mod.KnowledgeBaseRepository, "delete", _patched)


def _patch_kb_item_delete_records(monkeypatch: pytest.MonkeyPatch, calls: list[tuple]) -> None:
    """Same as :func:`_patch_kb_delete_records`, for ``KBItemRepository.delete``."""
    from the_one.db import repositories as repositories_mod

    original = repositories_mod.KBItemRepository.delete

    async def _patched(self, item_id: str) -> list[int]:
        calls.append(("delete", item_id))
        return await original(self, item_id)

    monkeypatch.setattr(repositories_mod.KBItemRepository, "delete", _patched)


class TestKnowledgeBaseStatusRoute:
    """Flight 3 Leg 3, AC-9: ``GET /knowledge-bases/{kb_id}/status``."""

    async def test_unknown_kb_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/knowledge-bases/no-such-kb/status")
        assert resp.status_code == 404

    async def test_reports_counts_folders_chunks_and_idle_with_no_manager(
        self, client: AsyncClient
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "file", "path_or_url": "/tmp/a.txt"},
        )

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == {"pending": 1, "indexing": 0, "indexed": 0, "failed": 0}
        assert body["folders"] == []
        assert body["chunks"] == 0
        assert body["indexer"] == "idle"

    async def test_reports_folder_projection_and_manager_state(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        from the_one.knowledge import manager as manager_mod

        fake = _FakeIndexingManager(state="running")
        monkeypatch.setattr(manager_mod, "_manager", fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        folder_resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        folder_item = folder_resp.json()

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["indexer"] == "running"
        assert body["folders"] == [
            {
                "id": folder_item["id"],
                "path": folder_item["path_or_url"],
                "status": folder_item["status"],
                "indexed_at": folder_item["indexed_at"],
                "error": folder_item["error"],
                "watch": "off",
                "watch_error": None,
                # Flight 7 Leg 2, AC-9: no walk has ever completed for
                # this folder (a fake manager is installed; nothing real
                # walked it) — both counters read absent (`None`), not a
                # fabricated `0` (leg Edge Cases).
                "skipped_dirs": None,
                "skipped_entries": None,
            }
        ]

    async def test_reports_watch_state_from_manager(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        """Flight 4 Leg 3, AC-4: with a watch manager installed, the
        folder's `watch`/`watch_error` fields come from it."""
        from the_one.knowledge import watcher as watcher_mod

        fake = _FakeWatchManager(state="unavailable", error="root removed")
        monkeypatch.setattr(watcher_mod, "_manager", fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        folder_resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        folder_item = folder_resp.json()

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["folders"] == [
            {
                "id": folder_item["id"],
                "path": folder_item["path_or_url"],
                "status": folder_item["status"],
                "indexed_at": folder_item["indexed_at"],
                "error": folder_item["error"],
                "watch": "unavailable",
                "watch_error": "root removed",
                "skipped_dirs": None,
                "skipped_entries": None,
            }
        ]

    async def test_chunks_count_reflects_stored_chunks(self, client: AsyncClient) -> None:
        from the_one.db._kb_types import ChunkRecord
        from the_one.db.repositories import KBChunkRepository
        from the_one.interfaces.web import api as api_module

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        conn = await api_module.get_connection()
        chunk_repo = KBChunkRepository(conn)
        await chunk_repo.replace_item_chunks(
            item_id,
            kb_id,
            [
                ChunkRecord(seq=0, text="hello", char_start=0, char_end=5),
                ChunkRecord(seq=1, text="world", char_start=5, char_end=10),
            ],
        )

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        assert resp.json()["chunks"] == 2


class TestKnowledgeBaseContentFreshness:
    """Flight 7 Leg 2 (DD-6, AC-2/AC-3/AC-5): ``get_kb_status``'s
    ``content_freshness`` aggregate — additive to the pre-existing
    ``items``/``chunks`` keys, moves iff a FILE item actually reaches
    ``indexed`` (never on an unrelated pending/folder change), and is
    byte-identical across repeated reads when nothing new has indexed."""

    async def test_absent_when_no_file_item_has_ever_indexed(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "file", "path_or_url": "/tmp/a.txt"},
        )
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        assert resp.json()["content_freshness"] is None

    async def test_moves_when_a_file_item_reaches_indexed(self, client: AsyncClient) -> None:
        from the_one.db.repositories import KBItemRepository
        from the_one.interfaces.web import api as api_module

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/a.txt"},
            )
        ).json()["id"]

        before = (await client.get(f"/api/knowledge-bases/{kb_id}/status")).json()
        assert before["content_freshness"] is None

        conn = await api_module.get_connection()
        item_repo = KBItemRepository(conn)
        # Mirrors what `_flush` does in the real pipeline: a file item's
        # ONLY route to `indexed_at` is `update_status(..., "indexed")`.
        await item_repo.update_status(item_id, "indexing")
        updated = await item_repo.update_status(item_id, "indexed")

        after = (await client.get(f"/api/knowledge-bases/{kb_id}/status")).json()
        assert after["content_freshness"] == updated.indexed_at
        assert after["content_freshness"] is not None

    async def test_stable_across_repeated_reads_with_no_new_indexing(
        self, client: AsyncClient
    ) -> None:
        """AC-5: a quiet corpus must not move the signal on every poll —
        this is what keeps `knowledgeItemsSignature` from re-fetching
        `/items` every tick and blowing away an open panel."""
        from the_one.db.repositories import KBItemRepository
        from the_one.interfaces.web import api as api_module

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/a.txt"},
            )
        ).json()["id"]
        conn = await api_module.get_connection()
        item_repo = KBItemRepository(conn)
        await item_repo.update_status(item_id, "indexing")
        await item_repo.update_status(item_id, "indexed")

        first = (await client.get(f"/api/knowledge-bases/{kb_id}/status")).json()
        second = (await client.get(f"/api/knowledge-bases/{kb_id}/status")).json()
        assert first["content_freshness"] == second["content_freshness"]

    async def test_folder_indexed_at_never_moves_the_aggregate(
        self, client: AsyncClient, tmp_path
    ) -> None:
        """AC-3's negative case: a FOLDER item reaching ``indexed`` (which
        `_walk_one_folder` does unconditionally on every pass) must not
        move `content_freshness` — only FILE items are scoped in."""
        from the_one.db.repositories import KBItemRepository
        from the_one.interfaces.web import api as api_module

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        conn = await api_module.get_connection()
        item_repo = KBItemRepository(conn)
        folders = await item_repo.list_folders(kb_id)
        await item_repo.update_status(folders[0].id, "indexing")
        await item_repo.update_status(folders[0].id, "indexed")

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        assert resp.json()["content_freshness"] is None

    async def test_is_additive_existing_keys_unchanged(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        body = resp.json()
        assert set(body.keys()) == {"items", "content_freshness", "folders", "chunks", "indexer"}


class TestKnowledgeBaseWalkSkipCounters:
    """Flight 7 Leg 2 (DD-7): persistence (AC-8), projection (AC-9), and
    cleanup on both delete paths (AC-11/AC-12) for the walk skip counters —
    plus AC-11a (`AppMetadataRepository.delete`) and AC-11b (one shared
    key helper used at every call site)."""

    async def test_folder_with_no_completed_walk_projects_none(
        self, client: AsyncClient, tmp_path
    ) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        entry = resp.json()["folders"][0]
        assert entry["skipped_dirs"] is None
        assert entry["skipped_entries"] is None

    async def test_persisted_counters_are_projected_by_status(
        self, client: AsyncClient, tmp_path
    ) -> None:
        import json as _json

        from the_one.db.repositories import AppMetadataRepository
        from the_one.interfaces.web import api as api_module
        from the_one.knowledge.settings import walk_skip_counters_key

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        folder_item = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "folder", "path_or_url": str(folder)},
            )
        ).json()

        conn = await api_module.get_connection()
        meta_repo = AppMetadataRepository(conn)
        key = walk_skip_counters_key(folder_item["id"])
        # Same shape `_walk_one_folder` writes (AC-11b: through the ONE
        # shared key helper, never a hand-rolled string).
        await meta_repo.set(key, _json.dumps({"skipped_dirs": 2, "skipped_entries": 5}))

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        entry = resp.json()["folders"][0]
        assert entry["skipped_dirs"] == 2
        assert entry["skipped_entries"] == 5

        # Zero counters are a real recorded fact ("walked, skipped
        # nothing"), distinct from absence ("not yet walked") — must round
        # trip as 0, not None.
        await meta_repo.set(key, _json.dumps({"skipped_dirs": 0, "skipped_entries": 0}))
        resp2 = await client.get(f"/api/knowledge-bases/{kb_id}/status")
        entry2 = resp2.json()["folders"][0]
        assert entry2["skipped_dirs"] == 0
        assert entry2["skipped_entries"] == 0

    async def test_delete_kb_item_folder_clears_its_skip_counter_key(
        self, client: AsyncClient, tmp_path
    ) -> None:
        import json as _json

        from the_one.db.repositories import AppMetadataRepository
        from the_one.interfaces.web import api as api_module
        from the_one.knowledge.settings import walk_skip_counters_key

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        folder_item = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "folder", "path_or_url": str(folder)},
            )
        ).json()

        conn = await api_module.get_connection()
        meta_repo = AppMetadataRepository(conn)
        key = walk_skip_counters_key(folder_item["id"])
        await meta_repo.set(key, _json.dumps({"skipped_dirs": 1, "skipped_entries": 1}))
        assert await meta_repo.get(key) is not None

        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/{folder_item['id']}")
        assert resp.status_code == 200

        # AC-12: the KEY THE WRITE SITE ACTUALLY USED is gone — read
        # through the same shared helper the test used to write it, so a
        # drifted cleanup-site key cannot produce a false green here.
        assert await meta_repo.get(key) is None

    async def test_delete_knowledge_base_clears_every_folders_skip_counter_key(
        self, client: AsyncClient, tmp_path
    ) -> None:
        import json as _json

        from the_one.db.repositories import AppMetadataRepository
        from the_one.interfaces.web import api as api_module
        from the_one.knowledge.settings import walk_skip_counters_key

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder_a = tmp_path / "a"
        folder_a.mkdir()
        folder_b = tmp_path / "b"
        folder_b.mkdir()
        item_a = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "folder", "path_or_url": str(folder_a)},
            )
        ).json()
        item_b = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "folder", "path_or_url": str(folder_b)},
            )
        ).json()

        conn = await api_module.get_connection()
        meta_repo = AppMetadataRepository(conn)
        key_a = walk_skip_counters_key(item_a["id"])
        key_b = walk_skip_counters_key(item_b["id"])
        await meta_repo.set(key_a, _json.dumps({"skipped_dirs": 1, "skipped_entries": 0}))
        await meta_repo.set(key_b, _json.dumps({"skipped_dirs": 0, "skipped_entries": 3}))

        resp = await client.delete(f"/api/knowledge-bases/{kb_id}")
        assert resp.status_code == 200

        assert await meta_repo.get(key_a) is None
        assert await meta_repo.get(key_b) is None

    async def test_delete_kb_item_file_type_does_not_error(self, client: AsyncClient) -> None:
        """A standalone `file` item delete must not attempt (or need) any
        skip-counter cleanup — files never have one."""
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/a.txt"},
            )
        ).json()["id"]
        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/{item_id}")
        assert resp.status_code == 200


class TestKnowledgeBaseReindexRoute:
    """Flight 3 Leg 3, AC-9: ``POST /knowledge-bases/{kb_id}/reindex``."""

    async def test_unknown_kb_404(self, client: AsyncClient) -> None:
        resp = await client.post("/api/knowledge-bases/no-such-kb/reindex")
        assert resp.status_code == 404

    async def test_invalid_scope_422(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(f"/api/knowledge-bases/{kb_id}/reindex?scope=bogus")
        assert resp.status_code == 422

    async def test_default_scope_changed_requests_index_and_requeues_nothing(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.knowledge import manager as manager_mod

        fake = _FakeIndexingManager()
        monkeypatch.setattr(manager_mod, "_manager", fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(f"/api/knowledge-bases/{kb_id}/reindex")

        assert resp.status_code == 202
        assert resp.json() == {"scope": "changed", "requeued": 0}
        assert fake.calls == [("request_index", kb_id)]

    async def test_scope_all_requeues_indexed_and_failed_file_items(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.db._write_lock import write_transaction
        from the_one.interfaces.web import api as api_module
        from the_one.knowledge import manager as manager_mod

        fake = _FakeIndexingManager()
        monkeypatch.setattr(manager_mod, "_manager", fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        conn = await api_module.get_connection()
        async with write_transaction(conn):
            await conn.execute("UPDATE kb_items SET status='indexed' WHERE id=?", (item_id,))

        resp = await client.post(f"/api/knowledge-bases/{kb_id}/reindex?scope=all")

        assert resp.status_code == 202
        assert resp.json() == {"scope": "all", "requeued": 1}
        assert fake.calls == [("request_index", kb_id)]

        item_resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}")
        assert item_resp.json()["status"] == "pending"

    async def test_no_manager_installed_still_returns_202(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(f"/api/knowledge-bases/{kb_id}/reindex")
        assert resp.status_code == 202


class TestKnowledgeBaseChunksRoute:
    """Flight 3 Leg 3, AC-9: ``GET …/items/{item_id}/chunks``."""

    async def _seed_item_and_chunks(self, client: AsyncClient) -> tuple[str, str]:
        from the_one.db._kb_types import ChunkRecord
        from the_one.db.repositories import KBChunkRepository
        from the_one.interfaces.web import api as api_module

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        conn = await api_module.get_connection()
        chunk_repo = KBChunkRepository(conn)
        await chunk_repo.replace_item_chunks(
            item_id,
            kb_id,
            [
                ChunkRecord(seq=1, text="second", char_start=5, char_end=11),
                ChunkRecord(seq=0, text="first", char_start=0, char_end=5),
            ],
        )
        return kb_id, item_id

    async def test_chunks_paginated_in_seq_order(self, client: AsyncClient) -> None:
        kb_id, item_id = await self._seed_item_and_chunks(client)

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/chunks")
        assert resp.status_code == 200
        body = resp.json()
        assert [c["seq"] for c in body] == [0, 1]
        assert body[0] == {
            "id": body[0]["id"],
            "seq": 0,
            "char_start": 0,
            "char_end": 5,
            "text": "first",
        }

    async def test_limit_below_range_422(self, client: AsyncClient) -> None:
        kb_id, item_id = await self._seed_item_and_chunks(client)
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/chunks?limit=0")
        assert resp.status_code == 422

    async def test_limit_above_range_422(self, client: AsyncClient) -> None:
        kb_id, item_id = await self._seed_item_and_chunks(client)
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/chunks?limit=1001")
        assert resp.status_code == 422

    async def test_negative_offset_422(self, client: AsyncClient) -> None:
        kb_id, item_id = await self._seed_item_and_chunks(client)
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/chunks?offset=-1")
        assert resp.status_code == 422

    async def test_other_kb_404(self, client: AsyncClient) -> None:
        _, item_id = await self._seed_item_and_chunks(client)
        kb2 = (await client.post("/api/knowledge-bases", json={"name": "KB2"})).json()["id"]
        resp = await client.get(f"/api/knowledge-bases/{kb2}/items/{item_id}/chunks")
        assert resp.status_code == 404


class TestKnowledgeBaseSourceRoute:
    """Flight 3 Leg 3, AC-9: ``GET …/items/{item_id}/source``."""

    async def test_returns_extracted_text_and_fresh_hash_is_not_stale(
        self, client: AsyncClient, tmp_path
    ) -> None:
        from the_one.knowledge.walk import content_hash

        path = tmp_path / "doc.txt"
        path.write_text("hello world")

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": str(path)},
            )
        ).json()["id"]

        from the_one.interfaces.web import api as api_module

        conn = await api_module.get_connection()
        from the_one.db.repositories import KBItemRepository

        await KBItemRepository(conn).set_content_identity(
            item_id,
            content_hash=content_hash(path),
            size_bytes=path.stat().st_size,
            mtime=path.stat().st_mtime,
        )

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == str(path)
        assert body["text"] == "hello world"
        assert body["stale"] is False
        assert body["content_hash"] == content_hash(path)

    async def test_no_stored_hash_reads_as_stale(self, client: AsyncClient, tmp_path) -> None:
        path = tmp_path / "doc.txt"
        path.write_text("hello world")

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": str(path)},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 200
        assert resp.json()["stale"] is True
        assert resp.json()["content_hash"] is None

    async def test_missing_file_404(self, client: AsyncClient, tmp_path) -> None:
        path = tmp_path / "gone.txt"

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": str(path)},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 404

    async def test_folder_item_422(self, client: AsyncClient, tmp_path) -> None:
        folder = tmp_path / "docs"
        folder.mkdir()

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "folder", "path_or_url": str(folder)},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 422

    async def test_url_item_422(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "url", "path_or_url": "https://example.com"},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 422

    async def test_no_extractor_for_suffix_422(self, client: AsyncClient, tmp_path) -> None:
        path = tmp_path / "image.png"
        path.write_bytes(b"\x89PNG\r\n")

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": str(path)},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 422

    async def test_other_kb_404(self, client: AsyncClient, tmp_path) -> None:
        path = tmp_path / "doc.txt"
        path.write_text("hi")

        kb1 = (await client.post("/api/knowledge-bases", json={"name": "KB1"})).json()["id"]
        kb2 = (await client.post("/api/knowledge-bases", json={"name": "KB2"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb1}/items",
                json={"type": "file", "path_or_url": str(path)},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb2}/items/{item_id}/source")
        assert resp.status_code == 404

    async def test_over_cap_file_413(self, client: AsyncClient, tmp_path) -> None:
        """Squawk 0063: a file over the indexer's ``MAX_FILE_BYTES`` (10 MiB)
        cap is refused with 413 before extraction, rather than read whole
        into memory. Uses a sparse file (``truncate``) since only the
        ``stat`` size is exercised — no need to actually write 10 MiB."""
        from the_one.knowledge.indexer import MAX_FILE_BYTES

        path = tmp_path / "huge.txt"
        with path.open("wb") as f:
            f.truncate(MAX_FILE_BYTES + 1)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": str(path)},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert "10 MiB" in detail
        assert str(MAX_FILE_BYTES + 1) in detail

    async def test_small_file_under_cap_200(self, client: AsyncClient, tmp_path) -> None:
        """Squawk 0063 companion: a small file is unaffected by the new cap
        check and still returns 200."""
        path = tmp_path / "small.txt"
        path.write_text("small enough")

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": str(path)},
            )
        ).json()["id"]

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/items/{item_id}/source")
        assert resp.status_code == 200
        assert resp.json()["text"] == "small enough"


class TestKnowledgeBaseSearchRoute:
    """Flight 6 Leg 1, DD-6, AC-10/AC-11: ``GET …/search``."""

    @pytest.fixture(autouse=True)
    def _isolate_vector_store(self, client: AsyncClient, monkeypatch):
        """Same seam-isolation as ``TestKnowledgeBaseDeleteCallsVectorStore``
        — route the vector-store module's own ``get_connection()`` to the
        test client's connection, so building a store never touches the
        real production database."""
        from the_one import vectors as vectors_module
        from the_one.interfaces.web import api as api_module

        monkeypatch.setattr(vectors_module, "get_connection", api_module.get_connection)
        vectors_module._reset_for_test()
        yield
        vectors_module._reset_for_test()

    @staticmethod
    def _stub_store():
        class _StubStore:
            backend = "stub"
            dtype = "float32"
            dim = 8

            async def open(self) -> None:
                return None

            async def upsert(self, kb_id, ids, vectors) -> None:
                return None

            async def delete(self, kb_id, ids) -> None:
                return None

            async def delete_kb(self, kb_id) -> None:
                return None

            async def query(self, kb_id, vector, k, timeout=None):
                return []

            async def count(self, kb_id) -> int:
                return 0

            async def flush(self, kb_id) -> None:
                return None

            async def close(self) -> None:
                return None

        return _StubStore()

    def _patch_embedding_backend(self, monkeypatch) -> None:
        from tests._embedding_stub import StubEmbeddingBackend
        from the_one.interfaces.web import api as api_module

        monkeypatch.setattr(api_module, "get_embedding_backend", lambda: StubEmbeddingBackend())

    async def _seed_chunk(self, client: AsyncClient, text: str) -> tuple[str, str]:
        from the_one.db._kb_types import ChunkRecord
        from the_one.db.repositories import KBChunkRepository
        from the_one.interfaces.web import api as api_module

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]
        conn = await api_module.get_connection()
        chunk_repo = KBChunkRepository(conn)
        await chunk_repo.replace_item_chunks(
            item_id,
            kb_id,
            [ChunkRecord(seq=0, text=text, char_start=0, char_end=len(text))],
        )
        return kb_id, item_id

    async def test_happy_path_returns_hits_with_score(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one import vectors as vectors_module

        monkeypatch.setattr(
            vectors_module, "_build_store", lambda settings, conn: self._stub_store()
        )
        vectors_module._reset_for_test()
        self._patch_embedding_backend(monkeypatch)

        kb_id, item_id = await self._seed_chunk(client, "hello searchable world")

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/search", params={"q": "searchable"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["degraded"] is None
        assert body["indexer"] == "idle"
        assert len(body["hits"]) == 1
        hit = body["hits"][0]
        assert hit["item_id"] == item_id
        assert hit["text"] == "hello searchable world"
        assert "score" in hit

    async def test_missing_q_returns_422(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/search")
        assert resp.status_code == 422

    async def test_empty_q_returns_422(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/search", params={"q": ""})
        assert resp.status_code == 422

    async def test_whitespace_only_q_returns_200_with_zero_hits(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        # No vector store or embedding backend is patched: retrieval.search's
        # documented no-op for a whitespace-only query must return before
        # either is touched, so an unpatched (real) backend lookup here
        # would itself prove the split is broken (it would hang / error
        # trying to load the real model).
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.get(f"/api/knowledge-bases/{kb_id}/search", params={"q": "   "})
        assert resp.status_code == 200
        body = resp.json()
        assert body["hits"] == []
        assert body["degraded"] is None

    async def test_limit_zero_returns_422(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.get(
            f"/api/knowledge-bases/{kb_id}/search", params={"q": "x", "limit": 0}
        )
        assert resp.status_code == 422

    async def test_limit_21_returns_422(self, client: AsyncClient) -> None:
        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.get(
            f"/api/knowledge-bases/{kb_id}/search", params={"q": "x", "limit": 21}
        )
        assert resp.status_code == 422

    async def test_unknown_kb_id_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/knowledge-bases/no-such-kb/search", params={"q": "hello"})
        assert resp.status_code == 404

    async def test_indexer_state_reflects_installed_manager(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one import vectors as vectors_module
        from the_one.knowledge import manager as manager_mod

        monkeypatch.setattr(
            vectors_module, "_build_store", lambda settings, conn: self._stub_store()
        )
        vectors_module._reset_for_test()
        self._patch_embedding_backend(monkeypatch)
        monkeypatch.setattr(manager_mod, "_manager", _FakeIndexingManager(state="indexing"))

        kb_id, _ = await self._seed_chunk(client, "hello world")

        resp = await client.get(f"/api/knowledge-bases/{kb_id}/search", params={"q": "hello"})
        assert resp.status_code == 200
        assert resp.json()["indexer"] == "indexing"


class TestKnowledgeBaseIndexingManagerRouteIntegration:
    """Flight 3 Leg 3, AC-10: the ``_after_folder_registered`` hook and the
    delete routes' ``stop``/``request_index`` integration."""

    async def test_after_folder_registered_calls_request_index(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        from the_one.knowledge import manager as manager_mod

        fake = _FakeIndexingManager()
        monkeypatch.setattr(manager_mod, "_manager", fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        assert resp.status_code == 201
        assert fake.calls == [("request_index", kb_id)]

    async def test_after_folder_registered_starts_watch_after_request_index(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        """Flight 4 Leg 3, AC-2: request_index then watch.start, in that
        order, with the created folder's item passed through."""
        from the_one.knowledge import manager as manager_mod
        from the_one.knowledge import watcher as watcher_mod

        indexing_fake = _FakeIndexingManager()
        monkeypatch.setattr(manager_mod, "_manager", indexing_fake)
        watch_fake = _FakeWatchManager()
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "folder", "path_or_url": str(folder)},
        )
        assert resp.status_code == 201
        assert indexing_fake.calls == [("request_index", kb_id)]
        assert len(watch_fake.calls) == 1
        call_name, call_kb_id, call_item = watch_fake.calls[0]
        assert call_name == "start"
        assert call_kb_id == kb_id
        assert call_item.id == resp.json()["id"]

    async def test_after_folder_registered_does_not_start_watch_for_file_item(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.knowledge import watcher as watcher_mod

        watch_fake = _FakeWatchManager()
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.post(
            f"/api/knowledge-bases/{kb_id}/items",
            json={"type": "file", "path_or_url": "/tmp/x.txt"},
        )
        assert resp.status_code == 201
        assert watch_fake.calls == []

    async def test_delete_knowledge_base_stops_before_delete(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.knowledge import manager as manager_mod

        fake = _FakeIndexingManager()
        monkeypatch.setattr(manager_mod, "_manager", fake)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.delete(f"/api/knowledge-bases/{kb_id}")

        assert resp.status_code == 200
        assert fake.calls == [("stop", kb_id)]

    async def test_delete_knowledge_base_under_watch_suppression_ordering(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """Flight 4 Leg 3, AC-3: suppress_enter, stop_kb, indexing_stop,
        delete, suppress_exit, in that order — proved with ONE shared
        call list across both fakes plus the patched repository delete
        (review fix: two disjoint per-manager lists don't prove the
        cross-manager interleaving)."""
        from the_one.knowledge import manager as manager_mod
        from the_one.knowledge import watcher as watcher_mod

        calls: list[tuple] = []
        indexing_fake = _FakeIndexingManager(calls=calls)
        monkeypatch.setattr(manager_mod, "_manager", indexing_fake)
        watch_fake = _FakeWatchManager(calls=calls)
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)
        _patch_kb_delete_records(monkeypatch, calls)

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        resp = await client.delete(f"/api/knowledge-bases/{kb_id}")

        assert resp.status_code == 200
        assert calls == [
            ("suppress_enter", kb_id),
            ("stop_kb", kb_id),
            ("stop", kb_id),
            ("delete", kb_id),
            ("suppress_exit", kb_id),
        ]

    async def test_delete_knowledge_base_unknown_kb_exits_suppression(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """Flight 4 Leg 3, AC-3: an unknown kb_id still 404s, and
        suppress_exit is recorded after the repository delete's KeyError
        — released on the exception path, not skipped by it."""
        from the_one.knowledge import watcher as watcher_mod

        calls: list[tuple] = []
        watch_fake = _FakeWatchManager(calls=calls)
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)
        _patch_kb_delete_records(monkeypatch, calls)

        resp = await client.delete("/api/knowledge-bases/no-such-kb")

        assert resp.status_code == 404
        assert calls == [
            ("suppress_enter", "no-such-kb"),
            ("stop_kb", "no-such-kb"),
            ("delete", "no-such-kb"),
            ("suppress_exit", "no-such-kb"),
        ]

    async def test_delete_folder_item_stops_before_and_requests_index_after(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        from the_one.knowledge import manager as manager_mod

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        # Register the folder BEFORE the fake is installed so the
        # registration's own request_index call isn't recorded — only the
        # delete route's stop/request_index pair is under test.
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "folder", "path_or_url": str(folder)},
            )
        ).json()["id"]

        fake = _FakeIndexingManager()
        monkeypatch.setattr(manager_mod, "_manager", fake)

        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/{item_id}")

        assert resp.status_code == 200
        assert fake.calls == [("stop", kb_id), ("request_index", kb_id)]

    async def test_delete_folder_item_under_watch_suppression_ordering(
        self, client: AsyncClient, tmp_path, monkeypatch
    ) -> None:
        """Flight 4 Leg 3, AC-3: suppress_enter, watch_stop, indexing_stop,
        delete, request_index, suppress_exit, in that order — proved with
        ONE shared call list across both fakes plus the patched repository
        delete (review fix: two disjoint per-manager lists don't prove the
        cross-manager interleaving)."""
        from the_one.knowledge import manager as manager_mod
        from the_one.knowledge import watcher as watcher_mod

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        folder = tmp_path / "docs"
        folder.mkdir()
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "folder", "path_or_url": str(folder)},
            )
        ).json()["id"]

        calls: list[tuple] = []
        indexing_fake = _FakeIndexingManager(calls=calls)
        monkeypatch.setattr(manager_mod, "_manager", indexing_fake)
        watch_fake = _FakeWatchManager(calls=calls)
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)
        _patch_kb_item_delete_records(monkeypatch, calls)

        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/{item_id}")

        assert resp.status_code == 200
        assert calls == [
            ("suppress_enter", kb_id),
            ("watch_stop", item_id),
            ("stop", kb_id),
            ("delete", item_id),
            ("request_index", kb_id),
            ("suppress_exit", kb_id),
        ]

    async def test_delete_file_item_calls_neither(self, client: AsyncClient, monkeypatch) -> None:
        from the_one.knowledge import manager as manager_mod
        from the_one.knowledge import watcher as watcher_mod

        kb_id = (await client.post("/api/knowledge-bases", json={"name": "KB"})).json()["id"]
        item_id = (
            await client.post(
                f"/api/knowledge-bases/{kb_id}/items",
                json={"type": "file", "path_or_url": "/tmp/x.txt"},
            )
        ).json()["id"]

        fake = _FakeIndexingManager()
        monkeypatch.setattr(manager_mod, "_manager", fake)
        watch_fake = _FakeWatchManager()
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)

        resp = await client.delete(f"/api/knowledge-bases/{kb_id}/items/{item_id}")

        assert resp.status_code == 200
        assert fake.calls == []
        assert watch_fake.calls == []


# ── Knowledge settings endpoints ─────────────────────────────────────────


class TestKnowledgeSettingsAPI:
    """M24 F02 L03, DD-6, AC-9."""

    async def test_get_returns_defaults_on_fresh_db(self, client: AsyncClient) -> None:
        resp = await client.get("/api/knowledge-settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["embedding"] == {
            "backend": "local",
            "model_id": "potion-retrieval-32M",
            "dim": 512,
        }
        assert body["chunking"] == {"size_chars": 1000, "overlap_chars": 150}
        # Flight 4 Leg 1, DD-5, AC-2: `monitoring` defaults beside the
        # existing keys.
        assert body["monitoring"] == {"watch_enabled": True, "reconcile_interval_seconds": 300}
        # Flight 2 Leg 4, AC-12: `vector_store` is now present (read-only,
        # store-written) alongside the pre-existing `notes` list.
        assert body["vector_store"] == {
            "backend": "usearch",
            "dtype": "f16",
            "dim": 512,
            "model_id": "potion-retrieval-32M",
        }
        assert isinstance(body["notes"], list) and body["notes"]

    async def test_put_updates_chunking_and_still_returns_vector_store_and_notes(
        self, client: AsyncClient
    ) -> None:
        """AC-12: a PUT that changes chunking must not lose `vector_store`
        or `notes` from the response shape."""
        resp = await client.put(
            "/api/knowledge-settings",
            json={"chunking": {"size_chars": 900, "overlap_chars": 100}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["monitoring"] == {"watch_enabled": True, "reconcile_interval_seconds": 300}
        assert body["vector_store"] == {
            "backend": "usearch",
            "dtype": "f16",
            "dim": 512,
            "model_id": "potion-retrieval-32M",
        }
        assert isinstance(body["notes"], list) and body["notes"]

    async def test_put_with_vector_store_key_rejected(self, client: AsyncClient) -> None:
        """AC-12: `vector_store` is store-written (DD-3/DD-6) — the
        existing generic top-level-key guard already 422s it; no new
        message is added for this key specifically."""
        resp = await client.put(
            "/api/knowledge-settings",
            json={"vector_store": {"backend": "usearch"}},
        )
        assert resp.status_code == 422

        get_resp = await client.get("/api/knowledge-settings")
        assert get_resp.json()["vector_store"]["backend"] == "usearch"

    @pytest.mark.parametrize("bad_value", ["not-a-dict", ["a", "list"], 42, None])
    async def test_put_non_dict_embedding_or_chunking_value_422s_not_500(
        self, client: AsyncClient, bad_value
    ) -> None:
        """Leg 5 review fix-now: a non-dict ``embedding``/``chunking`` value
        must 422 (a malformed request), not raise an uncaught
        ``dict.update()`` TypeError as an unhandled 500."""
        resp = await client.put("/api/knowledge-settings", json={"embedding": bad_value})
        assert resp.status_code == 422

        resp = await client.put("/api/knowledge-settings", json={"chunking": bad_value})
        assert resp.status_code == 422

        get_resp = await client.get("/api/knowledge-settings")
        assert get_resp.json()["chunking"] == {"size_chars": 1000, "overlap_chars": 150}

    async def test_put_updates_chunking_only(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/knowledge-settings",
            json={"chunking": {"size_chars": 800, "overlap_chars": 100}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chunking"] == {"size_chars": 800, "overlap_chars": 100}
        assert body["embedding"] == {
            "backend": "local",
            "model_id": "potion-retrieval-32M",
            "dim": 512,
        }

        get_resp = await client.get("/api/knowledge-settings")
        assert get_resp.json()["chunking"] == {"size_chars": 800, "overlap_chars": 100}

    async def test_put_invalid_value_422_and_changes_nothing(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/knowledge-settings",
            json={"chunking": {"size_chars": 50}},
        )
        assert resp.status_code == 422

        get_resp = await client.get("/api/knowledge-settings")
        assert get_resp.json()["chunking"] == {"size_chars": 1000, "overlap_chars": 150}

    async def test_put_non_local_backend_422_names_the_amendment(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/knowledge-settings",
            json={"embedding": {"backend": "ollama"}},
        )
        assert resp.status_code == 422
        assert "Mission 24" in resp.text

    async def test_put_unknown_top_level_key_rejected(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/knowledge-settings",
            json={"bogus": {}},
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        ("section", "unknown_key"),
        [("embedding", "backend_typo"), ("chunking", "overlap_chras")],
    )
    async def test_put_nested_unknown_key_422s_and_names_the_key(
        self, client: AsyncClient, section: str, unknown_key: str
    ) -> None:
        """Squawk 0056: a nested unknown key inside ``embedding``/
        ``chunking`` must 422 (naming the offending key) rather than being
        silently merged-then-dropped by pydantic's default
        ``extra="ignore"``, and the stored record must be unchanged."""
        resp = await client.put(
            "/api/knowledge-settings",
            json={section: {unknown_key: "x"}},
        )
        assert resp.status_code == 422
        assert unknown_key in resp.text

        get_resp = await client.get("/api/knowledge-settings")
        assert get_resp.json()["embedding"] == {
            "backend": "local",
            "model_id": "potion-retrieval-32M",
            "dim": 512,
        }
        assert get_resp.json()["chunking"] == {"size_chars": 1000, "overlap_chars": 150}


class TestKnowledgeSettingsMonitoringAPI:
    """Flight 4 Leg 1, DD-5, AC-2: the third `monitoring` section on the
    existing knowledge-settings routes, its merge-then-revalidate shape,
    and the awaited live-apply hook (a documented no-op in this leg)."""

    async def test_put_updates_monitoring_leaves_others_unchanged(
        self, client: AsyncClient
    ) -> None:
        resp = await client.put(
            "/api/knowledge-settings",
            json={"monitoring": {"watch_enabled": False, "reconcile_interval_seconds": 10}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["monitoring"] == {"watch_enabled": False, "reconcile_interval_seconds": 10}
        assert body["embedding"] == {
            "backend": "local",
            "model_id": "potion-retrieval-32M",
            "dim": 512,
        }
        assert body["chunking"] == {"size_chars": 1000, "overlap_chars": 150}
        assert body["vector_store"] == {
            "backend": "usearch",
            "dtype": "f16",
            "dim": 512,
            "model_id": "potion-retrieval-32M",
        }

    async def test_put_monitoring_merges_preserving_interval(self, client: AsyncClient) -> None:
        first = await client.put(
            "/api/knowledge-settings",
            json={"monitoring": {"watch_enabled": False, "reconcile_interval_seconds": 10}},
        )
        assert first.status_code == 200

        second = await client.put(
            "/api/knowledge-settings",
            json={"monitoring": {"watch_enabled": True}},
        )
        assert second.status_code == 200
        assert second.json()["monitoring"] == {
            "watch_enabled": True,
            "reconcile_interval_seconds": 10,
        }

    @pytest.mark.parametrize(
        "body",
        [
            {"monitoring": {"reconcile_interval_seconds": 5}},
            {"monitoring": {"watch_enabled": "maybe"}},
            {"monitoring": {"bogus": 1}},
            {"monitoring": "off"},
        ],
    )
    async def test_put_invalid_monitoring_422_and_changes_nothing(
        self, client: AsyncClient, body
    ) -> None:
        resp = await client.put("/api/knowledge-settings", json=body)
        assert resp.status_code == 422

        get_resp = await client.get("/api/knowledge-settings")
        assert get_resp.json()["monitoring"] == {
            "watch_enabled": True,
            "reconcile_interval_seconds": 300,
        }

    async def test_hook_is_async_and_awaited_once_with_saved_monitoring(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        import inspect

        from the_one.interfaces.web import api as api_module
        from the_one.knowledge.settings import MonitoringSettings

        assert inspect.iscoroutinefunction(api_module._after_monitoring_settings_changed)

        calls = []

        async def _fake_hook(monitoring: MonitoringSettings) -> None:
            calls.append(monitoring)

        monkeypatch.setattr(api_module, "_after_monitoring_settings_changed", _fake_hook)

        resp = await client.put(
            "/api/knowledge-settings",
            json={"monitoring": {"watch_enabled": False, "reconcile_interval_seconds": 15}},
        )
        assert resp.status_code == 200
        assert calls == [MonitoringSettings(watch_enabled=False, reconcile_interval_seconds=15)]

    async def test_hook_not_awaited_on_422(self, client: AsyncClient, monkeypatch) -> None:
        from the_one.interfaces.web import api as api_module
        from the_one.knowledge.settings import MonitoringSettings

        calls = []

        async def _fake_hook(monitoring: MonitoringSettings) -> None:
            calls.append(monitoring)

        monkeypatch.setattr(api_module, "_after_monitoring_settings_changed", _fake_hook)

        resp = await client.put(
            "/api/knowledge-settings",
            json={"monitoring": {"reconcile_interval_seconds": 5}},
        )
        assert resp.status_code == 422
        assert calls == []

    async def test_put_calls_watch_manager_apply_settings_with_saved_monitoring(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """Flight 4 Leg 3, AC-5: a successful PUT calls the installed watch
        manager's `apply_settings` once with the saved `MonitoringSettings`
        — even when only `chunking` changed (the hook is unconditional on
        success; `apply_settings` is itself idempotent)."""
        from the_one.knowledge import watcher as watcher_mod
        from the_one.knowledge.settings import MonitoringSettings

        watch_fake = _FakeWatchManager()
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)

        resp = await client.put(
            "/api/knowledge-settings",
            json={"monitoring": {"watch_enabled": False, "reconcile_interval_seconds": 15}},
        )
        assert resp.status_code == 200
        assert watch_fake.calls == [
            (
                "apply_settings",
                MonitoringSettings(watch_enabled=False, reconcile_interval_seconds=15),
            )
        ]

    async def test_put_touching_only_chunking_still_calls_apply_settings(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.knowledge import watcher as watcher_mod
        from the_one.knowledge.settings import MonitoringSettings

        watch_fake = _FakeWatchManager()
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)

        resp = await client.put(
            "/api/knowledge-settings",
            json={"chunking": {"size_chars": 900, "overlap_chars": 100}},
        )
        assert resp.status_code == 200
        assert watch_fake.calls == [("apply_settings", MonitoringSettings())]

    async def test_put_422_does_not_call_apply_settings(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.knowledge import watcher as watcher_mod

        watch_fake = _FakeWatchManager()
        monkeypatch.setattr(watcher_mod, "_manager", watch_fake)

        resp = await client.put(
            "/api/knowledge-settings",
            json={"monitoring": {"reconcile_interval_seconds": 5}},
        )
        assert resp.status_code == 422
        assert watch_fake.calls == []


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
    async def test_create_invalid_returns_422(self, client: AsyncClient) -> None:
        # Squawk 0081: a ValidationError is a 422, not an unhandled 500.
        resp = await client.post("/api/chat/sessions", json={"title": {"not": "a string"}})
        assert resp.status_code == 422
        assert isinstance(resp.json()["detail"], list)

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

    async def test_session_summary_carries_platform(self, client: AsyncClient) -> None:
        """M25 F4 L1 (DD4): the summary gains one scalar, ``platform``: null
        for a UI session and the platform string for a connector session, on
        the list, detail, create and update responses alike."""
        await client.post("/api/agents", json={"name": "agent-platform"})
        ui = await client.post(
            "/api/chat/sessions", json={"agent_name": "agent-platform", "title": "UI chat"}
        )
        assert ui.status_code == 201
        assert ui.json()["platform"] is None
        connector = await client.post(
            "/api/chat/sessions",
            json={
                "agent_name": "agent-platform",
                "title": "#help: install",
                "platform": "discord",
                "connector_id": "c1",
                "channel_id": "ch1",
            },
        )
        assert connector.status_code == 201
        assert connector.json()["platform"] == "discord"
        ui_id, connector_id = ui.json()["id"], connector.json()["id"]

        listed = {s["id"]: s for s in (await client.get("/api/chat/sessions")).json()}
        assert listed[ui_id]["platform"] is None
        assert listed[connector_id]["platform"] == "discord"
        # The connector-keying fields stay out of the summary.
        assert "connector_id" not in listed[connector_id]
        assert "channel_id" not in listed[connector_id]

        detail = (await client.get(f"/api/chat/sessions/{connector_id}")).json()
        assert detail["platform"] == "discord"
        updated = await client.put(f"/api/chat/sessions/{ui_id}", json={"title": "Renamed"})
        assert updated.status_code == 200
        assert updated.json()["platform"] is None


def test_session_summary_keys_are_a_subset_of_the_ws_list_payload() -> None:
    """M25 F4 L1 (DD4): the client store primes ``sessions`` from the
    WebSocket ``session_list`` rows and fetches the same collection over REST
    (``_session_summary``), so every REST summary key must also be a
    ``session_list`` key; otherwise the primed and fetched rows diverge."""
    from the_one.db.models import ChatSession
    from the_one.interfaces.web.api import _session_summary
    from the_one.interfaces.web.app import _session_to_list_payload

    session = ChatSession(
        id="s1",
        agent_name="a",
        title="T",
        platform="discord",
        connector_id="c",
        channel_id="ch",
        thread_id="t",
        peer_id="p",
        last_inbound_at="2026-01-01T00:00:00",
    )
    summary = _session_summary(session)
    ws_row = _session_to_list_payload(session)
    assert set(summary) <= set(ws_row), sorted(set(summary) - set(ws_row))
    assert set(summary) == {"id", "agent_name", "title", "created_at", "updated_at", "platform"}
    for key in summary:
        assert summary[key] == ws_row[key], key


# TestRoutingAuditSeedEndpoint and TestSessionLookupSeamEndpoint are
# deleted: Mission 23 Flight 1 (DD-6) removes both ``/api/_test``
# connector seams (``POST /chat/sessions/{id}/routing-audit`` and
# ``GET /chat/sessions/lookup``) — their only callers were connector
# browser tests being deleted, and the session-keying columns they read
# are kept, so Flight 2 or 3 can restore them verbatim if new tests want
# them.

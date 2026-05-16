"""F4 L02 functional batch — agent rename feature.

Covers the ``POST /api/agents/{name}/rename`` endpoint and the
underlying :meth:`SQLiteAgentStore.rename` behavior, including:

- happy-path rename (new-name load succeeds, old-name 404s)
- conflict on new_name collision (HTTP 409)
- source not found (HTTP 404)
- same-name attempt (HTTP 422)
- empty new_name (HTTP 422)
- chat_sessions cascade — the FK was dropped in schema v5 so the rename
  performs a manual UPDATE inside the same transaction. Verifies that a
  session pointing at the old agent name now points at the new name.

Fixture pattern mirrors ``test_agent_tool_overrides_round_trip.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.interfaces.web.api import router


@pytest.fixture
async def client(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    await conn.close()


class TestAgentRename:
    async def test_rename_happy_path(self, client: AsyncClient) -> None:
        """Rename a fresh agent — new-name load returns 200, old-name 404."""
        await client.post("/api/agents", json={"name": "alpha"})
        resp = await client.post("/api/agents/alpha/rename", json={"new_name": "beta"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "beta"

        resp = await client.get("/api/agents/beta")
        assert resp.status_code == 200
        resp = await client.get("/api/agents/alpha")
        assert resp.status_code == 404

    async def test_rename_conflict_returns_409(self, client: AsyncClient) -> None:
        """Rename where the new_name is already taken — 409 Conflict."""
        await client.post("/api/agents", json={"name": "alpha"})
        await client.post("/api/agents", json={"name": "beta"})
        resp = await client.post("/api/agents/alpha/rename", json={"new_name": "beta"})
        assert resp.status_code == 409

    async def test_rename_source_missing_returns_404(self, client: AsyncClient) -> None:
        """Rename a non-existent source agent — 404 Not Found."""
        resp = await client.post("/api/agents/ghost/rename", json={"new_name": "wraith"})
        assert resp.status_code == 404

    async def test_rename_same_name_returns_422(self, client: AsyncClient) -> None:
        """new_name equal to current name — 422 Unprocessable Entity."""
        await client.post("/api/agents", json={"name": "alpha"})
        resp = await client.post("/api/agents/alpha/rename", json={"new_name": "alpha"})
        assert resp.status_code == 422

    async def test_rename_empty_new_name_returns_422(self, client: AsyncClient) -> None:
        """Empty new_name — 422 Unprocessable Entity."""
        await client.post("/api/agents", json={"name": "alpha"})
        resp = await client.post("/api/agents/alpha/rename", json={"new_name": ""})
        assert resp.status_code == 422

    async def test_rename_whitespace_only_new_name_returns_422(self, client: AsyncClient) -> None:
        """Whitespace-only new_name strips to empty — 422."""
        await client.post("/api/agents", json={"name": "alpha"})
        resp = await client.post("/api/agents/alpha/rename", json={"new_name": "   "})
        assert resp.status_code == 422

    async def test_rename_missing_new_name_field_returns_422(self, client: AsyncClient) -> None:
        """Body without a ``new_name`` key — 422."""
        await client.post("/api/agents", json={"name": "alpha"})
        resp = await client.post("/api/agents/alpha/rename", json={})
        assert resp.status_code == 422

    async def test_rename_preserves_agent_config_fields(self, client: AsyncClient) -> None:
        """All non-name fields survive the rename round-trip."""
        await client.post(
            "/api/agents",
            json={
                "name": "alpha",
                "description": "Some description",
                "llm_model": "test-model",
                "system_prompt": "Be helpful.",
                "max_iterations": 42,
            },
        )
        resp = await client.post("/api/agents/alpha/rename", json={"new_name": "beta"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "beta"
        assert body["description"] == "Some description"
        assert body["llm_model"] == "test-model"
        assert body["system_prompt"] == "Be helpful."
        assert body["max_iterations"] == 42

    async def test_rename_cascades_to_chat_sessions(self, tmp_path) -> None:
        """Sessions referencing the old agent_name update to the new name.

        Uses the SQLiteAgentStore + ChatSessionRepository directly rather
        than the API surface — the API doesn't expose a chat-session
        create endpoint that takes an arbitrary id/agent_name pair, and
        the repository-level test exercises the same cascade code path.
        """
        from the_one.agent.config import AgentConfig
        from the_one.db.models import ChatSession
        from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore

        db_path = tmp_path / "cascade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        try:
            agent_store = SQLiteAgentStore(conn)
            sessions = ChatSessionRepository(conn)

            await agent_store.save(AgentConfig(name="alpha"))
            await sessions.create(
                ChatSession(
                    id="sess-1",
                    agent_name="alpha",
                    title="Test session",
                    messages="[]",
                    created_at="2026-05-12T00:00:00+00:00",
                    updated_at="2026-05-12T00:00:00+00:00",
                )
            )

            await agent_store.rename("alpha", "beta")

            session = await sessions.get("sess-1")
            assert session.agent_name == "beta"
            # And the agent itself is reachable under the new name only.
            assert await agent_store.exists("beta")
            assert not await agent_store.exists("alpha")
        finally:
            await conn.close()

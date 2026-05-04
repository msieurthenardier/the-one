"""F6 L5 — agent tool_overrides PUT round-trip via the REST API.

Catches AgentConfig pydantic round-trip behavior independently of the JS
layer. The JS-side L7 Playwright tests cover the form-collection +
PUT-payload assembly; this module covers the AgentConfig pydantic
serialization round-trip on the server side.
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


class TestAgentToolOverridesRoundTrip:
    async def test_agent_put_with_null_tool_overrides_round_trips(
        self, client: AsyncClient
    ) -> None:
        """PUT agent with `tool_overrides=null` → GET returns
        `tool_overrides is None` (preserved, not coerced to {})."""
        # Create with overrides set, then null them out via PUT.
        await client.post(
            "/api/agents",
            json={
                "name": "test-null",
                "tool_overrides": {"http_request": {"host_allowlist": ["a.com"]}},
            },
        )
        resp = await client.put(
            "/api/agents/test-null",
            json={"name": "test-null", "tool_overrides": None},
        )
        assert resp.status_code == 200
        resp = await client.get("/api/agents/test-null")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_overrides"] is None

    async def test_agent_put_with_tool_overrides_round_trips(self, client: AsyncClient) -> None:
        """PUT agent with `tool_overrides={...}` → GET returns the exact
        same dict shape (str → dict[str, Any] preservation)."""
        await client.post("/api/agents", json={"name": "test-overrides"})
        payload = {
            "name": "test-overrides",
            "tool_overrides": {
                "http_request": {
                    "host_allowlist": ["example.com", "api.example.com"],
                    "timeout_seconds_max": 30,
                }
            },
        }
        resp = await client.put("/api/agents/test-overrides", json=payload)
        assert resp.status_code == 200
        resp = await client.get("/api/agents/test-overrides")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_overrides"] == payload["tool_overrides"]

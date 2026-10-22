"""F6 L5 — agent tool_overrides PUT round-trip via the REST API.

Catches AgentConfig pydantic round-trip behavior independently of the JS
layer. The JS-side L7 Playwright tests cover the form-collection +
PUT-payload assembly; this module covers the AgentConfig pydantic
serialization round-trip on the server side.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.interfaces.web.api import router


@pytest.fixture
async def client(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await connect_template_db(db_path)
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
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

    # ── M21 F01 L01: {}-vs-None fidelity through the encrypted columns ──

    async def test_agent_put_with_empty_dict_tool_overrides_round_trips_as_empty_dict(
        self, client: AsyncClient
    ) -> None:
        """PUT agent with `tool_overrides={}` → GET returns `{}`, not
        `None` — the encrypted column preserves the same None/`{}`
        distinction the plaintext column had (AC1)."""
        await client.post("/api/agents", json={"name": "test-empty-tool"})
        resp = await client.put(
            "/api/agents/test-empty-tool",
            json={"name": "test-empty-tool", "tool_overrides": {}},
        )
        assert resp.status_code == 200
        resp = await client.get("/api/agents/test-empty-tool")
        assert resp.status_code == 200
        assert resp.json()["tool_overrides"] == {}
        assert resp.json()["tool_overrides"] is not None

    async def test_agent_put_with_null_mcp_overrides_round_trips_as_none(
        self, client: AsyncClient
    ) -> None:
        """PUT agent with `mcp_overrides=null` (and nothing previously
        stored) → GET returns `None`, not `{}` (AC1's None/`{}` fidelity,
        mirrored for `mcp_overrides`)."""
        await client.post("/api/agents", json={"name": "test-null-mcp"})
        resp = await client.get("/api/agents/test-null-mcp")
        assert resp.status_code == 200
        assert resp.json()["mcp_overrides"] is None

    async def test_agent_put_with_empty_dict_mcp_overrides_and_nothing_stored_is_none(
        self, client: AsyncClient
    ) -> None:
        """PUT agent with `mcp_overrides={}`, with no prior stored
        overrides → GET returns `None`, not `{}`.

        Unlike `tool_overrides` (never touched by the preserve-on-PUT
        merge), `mcp_overrides` on `update_agent` always routes through
        `_merge_preserved_mcp_credentials`, which folds an empty merge
        result back to `None` (Implementation Guidance point 4) so the
        None/`{}` fidelity round-trip tests are preserved when nothing
        was ever stored. The store-layer fidelity for an INTENTIONAL
        `{}` — bypassing the API merge — is pinned directly against
        `SQLiteAgentStore` in
        `tests/test_db_repositories.py::test_empty_dict_stored_encrypted_and_loads_as_empty_dict`.
        """
        await client.post("/api/agents", json={"name": "test-empty-mcp"})
        resp = await client.put(
            "/api/agents/test-empty-mcp",
            json={"name": "test-empty-mcp", "mcp_overrides": {}},
        )
        assert resp.status_code == 200
        resp = await client.get("/api/agents/test-empty-mcp")
        assert resp.status_code == 200
        assert resp.json()["mcp_overrides"] is None

    async def test_agent_post_with_empty_dict_mcp_overrides_round_trips_as_none(
        self, client: AsyncClient
    ) -> None:
        """POST agent with `mcp_overrides={}` (no stored row to merge
        against, but `create_agent` also routes through the same merge
        helper for its mask-drop behavior) → the empty merge result
        folds to `None`, mirroring the PUT case above."""
        resp = await client.post(
            "/api/agents",
            json={"name": "test-empty-mcp-post", "mcp_overrides": {}},
        )
        assert resp.status_code == 201
        assert resp.json()["mcp_overrides"] is None
        resp = await client.get("/api/agents/test-empty-mcp-post")
        assert resp.json()["mcp_overrides"] is None


class TestToolOverridesPreservedOnOmit:
    """Squawk 0223: an agent PUT that omits `tool_overrides` keeps the stored map."""

    _OV = {"read_file": {"path_denylist": ["/secret"]}}

    async def _seed(self, client: AsyncClient, name: str) -> None:
        r = await client.post("/api/agents", json={"name": name, "tool_overrides": self._OV})
        assert r.status_code in (200, 201), r.text

    async def test_omitted_key_preserves(self, client: AsyncClient) -> None:
        await self._seed(client, "keep")
        r = await client.put("/api/agents/keep", json={"name": "keep", "description": "new"})
        assert r.status_code == 200, r.text
        body = (await client.get("/api/agents/keep")).json()
        assert body["description"] == "new"
        assert body["tool_overrides"] == self._OV

    async def test_explicit_null_clears(self, client: AsyncClient) -> None:
        await self._seed(client, "clear")
        r = await client.put("/api/agents/clear", json={"name": "clear", "tool_overrides": None})
        assert r.status_code == 200, r.text
        assert (await client.get("/api/agents/clear")).json()["tool_overrides"] is None

    async def test_supplied_map_replaces(self, client: AsyncClient) -> None:
        await self._seed(client, "repl")
        new = {"http_request": {"extra_allowed_hosts": ["a.com"]}}
        r = await client.put("/api/agents/repl", json={"name": "repl", "tool_overrides": new})
        assert r.status_code == 200, r.text
        assert (await client.get("/api/agents/repl")).json()["tool_overrides"] == new

    async def test_empty_map_is_stored_as_empty_map(self, client: AsyncClient) -> None:
        """Leg 08a: `{}` is a map, not a clear -- the server stores it as given."""
        await self._seed(client, "emptymap")
        r = await client.put(
            "/api/agents/emptymap", json={"name": "emptymap", "tool_overrides": {}}
        )
        assert r.status_code == 200, r.text
        assert (await client.get("/api/agents/emptymap")).json()["tool_overrides"] == {}

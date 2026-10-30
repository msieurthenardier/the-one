"""The naming rule on the API write paths (sortie 06 DD1-DD7).

Every POST/PUT route under the four entity prefixes is classified here: either it
sets a name and is checked (``CHECKED``), or it never does and says why (``EXEMPT``).
A new route that is in neither fails ``test_every_route_is_classified``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._routine_schedules import daily
from tests._schema_template import connect_template_db
from the_one import naming
from the_one.db.models import MCPSource
from the_one.db.repositories import SQLiteAgentStore
from the_one.interfaces.web.api import router

PREFIXES = ("/api/agents", "/api/providers", "/api/knowledge-bases", "/api/mcp-sources")

CHECKED = {
    ("POST", "/api/agents"),
    ("POST", "/api/agents/{name}/rename"),
    ("POST", "/api/providers"),
    ("PUT", "/api/providers/{provider_id}"),
    ("POST", "/api/knowledge-bases"),
    ("PUT", "/api/knowledge-bases/{kb_id}"),
    ("POST", "/api/mcp-sources"),
    ("PUT", "/api/mcp-sources/{source_id}"),
    ("POST", "/api/agents/{name}/routines"),
    ("PUT", "/api/agents/{name}/routines/{routine_id}"),
}

_SELF_CONFIG = "never sets a name: the surface row's name is a constant"
_TOOL_RULES = "acts on the agent in the path and never sets a name"
_ITEM = "acts on a knowledge base item; the knowledge base name is untouched"
_PROVIDER_ACTION = "acts on the provider in the path; its name is untouched"

EXEMPT = {
    ("PUT", "/api/agents/{name}"): "the name is forced from the path of an existing row",
    ("POST", "/api/agents/{name}/self-configuration"): _SELF_CONFIG,
    ("POST", "/api/agents/{name}/self-configuration/external-credentials"): _SELF_CONFIG,
    (
        "POST",
        "/api/agents/{name}/self-configuration/external-credentials/{identifier}/rotate",
    ): _SELF_CONFIG,
    ("PUT", "/api/agents/{name}/self-configuration/approval-mode"): _TOOL_RULES,
    (
        "POST",
        "/api/agents/{name}/routines/{routine_id}/run",
    ): "acts on the routine in the path and never sets a name",
    ("POST", "/api/agents/{name}/routines/preview"): "previews a schedule; writes nothing",
    ("POST", "/api/agents/{name}/rules"): _TOOL_RULES,
    ("PUT", "/api/agents/{name}/rules/order"): _TOOL_RULES,
    ("PUT", "/api/agents/{name}/rules/{rule_id}"): _TOOL_RULES,
    ("PUT", "/api/agents/{name}/notes/settings"): _TOOL_RULES,
    ("PUT", "/api/agents/{name}/notes/{note_id}"): _TOOL_RULES,
    (
        "POST",
        "/api/agents/{name}/self-configuration/revisions/{revision_id}/dismiss",
    ): "revision decision; writes a description or system prompt, never a name",
    (
        "POST",
        "/api/agents/{name}/self-configuration/revisions/{revision_id}/approve",
    ): "revision decision; writes a description or system prompt, never a name",
    (
        "POST",
        "/api/agents/{name}/self-configuration/revisions/{revision_id}/restore",
    ): "revision restore; writes a description or system prompt, never a name",
    ("PUT", "/api/agents/{name}/self-configuration/routines"): "two Routines switches; no name",
    (
        "POST",
        "/api/agents/{name}/self-configuration/routines/proposals/{proposal_id}/approve",
    ): "proposal decision; the name comes from an already-validated proposal",
    (
        "POST",
        "/api/agents/{name}/self-configuration/routines/proposals/{proposal_id}/dismiss",
    ): "proposal decision; sets no name",
    ("POST", "/api/knowledge-bases/{kb_id}/items"): _ITEM,
    ("POST", "/api/knowledge-bases/{kb_id}/items/{item_id}/retry"): _ITEM,
    ("POST", "/api/knowledge-bases/{kb_id}/reindex"): _ITEM,
    ("POST", "/api/mcp-sources/{source_id}/test/connect"): "connection probe; stores no name",
    ("POST", "/api/providers/{provider_id}/oauth/start"): _PROVIDER_ACTION,
    ("POST", "/api/providers/{provider_id}/oauth/code"): _PROVIDER_ACTION,
    ("POST", "/api/providers/{provider_id}/test"): _PROVIDER_ACTION,
    ("POST", "/api/providers/{provider_id}/models/pull"): "names a model, not a provider",
    ("POST", "/api/providers/{provider_id}/models/delete"): "names a model, not a provider",
    ("POST", "/api/providers/{provider_id}/models/load"): "names a model, not a provider",
    ("POST", "/api/providers/{provider_id}/models/unload"): "names a model, not a provider",
}


@pytest.fixture
async def conn(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    yield conn
    await conn.close()


@pytest.fixture
async def client(conn):
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        test_app = FastAPI()
        test_app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            yield c


def _rule(msg: str) -> list[dict]:
    return [{"type": "name_rule", "loc": ["name"], "msg": msg}]


def _conflict() -> list[dict]:
    return [{"type": "name_conflict", "loc": ["name"], "msg": naming.NAME_CONFLICT_AGENT}]


_PROVIDER = {"type": "ollama", "base_url": "http://localhost:11434/v1"}
_MCP = {"type": "stdio", "config": {"command": "echo"}}


def test_every_route_is_classified() -> None:
    found = set()
    for route in router.routes:
        path = getattr(route, "path", "")
        if not path.startswith(PREFIXES):
            continue
        for method in getattr(route, "methods", set()) & {"POST", "PUT"}:
            found.add((method, path))
    assert not (CHECKED & set(EXEMPT)), "a route is both checked and exempt"
    unclassified = found - CHECKED - set(EXEMPT)
    assert not unclassified, f"routes that set a name must be CHECKED or EXEMPT: {unclassified}"
    stale = (CHECKED | set(EXEMPT)) - found
    assert not stale, f"classified routes that no longer exist: {stale}"
    assert all(EXEMPT.values())


class TestCreateRefuses:
    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/api/agents", {}),
            ("/api/providers", _PROVIDER),
            ("/api/knowledge-bases", {}),
            ("/api/mcp-sources", _MCP),
        ],
    )
    async def test_slash_refused(self, client, path, body) -> None:
        resp = await client.post(path, json={**body, "name": "a/b"})
        assert resp.status_code == 422
        assert resp.json()["detail"] == _rule(naming.SEPARATOR)
        assert (await client.get(path)).json() == []

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/api/agents", {}),
            ("/api/providers", _PROVIDER),
            ("/api/knowledge-bases", {}),
            ("/api/mcp-sources", _MCP),
        ],
    )
    @pytest.mark.parametrize(
        ("name", "msg"),
        [
            (None, naming.EMPTY),
            (7, naming.EMPTY),
            ("  ", naming.EMPTY),
            ("x" * 65, naming.TOO_LONG),
        ],
    )
    async def test_empty_and_long(self, client, path, body, name, msg) -> None:
        payload = dict(body) if name is None else {**body, "name": name}
        resp = await client.post(path, json=payload)
        assert resp.status_code == 422
        assert resp.json()["detail"] == _rule(msg)

    async def test_missing_name_on_agent_create(self, client) -> None:
        resp = await client.post("/api/agents", json={"description": "x"})
        assert resp.json()["detail"] == _rule(naming.EMPTY)

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/api/agents", {}),
            ("/api/providers", _PROVIDER),
            ("/api/knowledge-bases", {}),
            ("/api/mcp-sources", _MCP),
        ],
    )
    async def test_padded_name_is_stored_trimmed(self, client, path, body) -> None:
        resp = await client.post(path, json={**body, "name": "  padded  "})
        assert resp.status_code == 201, resp.text
        assert resp.json()["name"] == "padded"
        assert [r["name"] for r in (await client.get(path)).json()] == ["padded"]

    async def test_reserved_mcp_name_is_refused_after_trim(self, client) -> None:
        resp = await client.post("/api/mcp-sources", json={**_MCP, "name": " self-configuration "})
        assert resp.status_code == 409


class TestUpdateRefuses:
    async def test_provider_put(self, client) -> None:
        pid = (await client.post("/api/providers", json={**_PROVIDER, "name": "P"})).json()["id"]
        resp = await client.put(f"/api/providers/{pid}", json={"name": "a/b"})
        assert resp.status_code == 422
        assert resp.json()["detail"] == _rule(naming.SEPARATOR)
        assert (await client.get(f"/api/providers/{pid}")).json()["name"] == "P"
        ok = await client.put(f"/api/providers/{pid}", json={"name": " Q "})
        assert ok.json()["name"] == "Q"

    async def test_provider_put_keeps_masked_key(self, client) -> None:
        body = {
            "name": "K",
            "type": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test1234567890",
        }
        pid = (await client.post("/api/providers", json=body)).json()["id"]
        resp = await client.put(
            f"/api/providers/{pid}", json={**body, "name": " K2 ", "api_key": "__MASKED__"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "K2"

    async def test_kb_put(self, client) -> None:
        kid = (await client.post("/api/knowledge-bases", json={"name": "Docs"})).json()["id"]
        resp = await client.put(f"/api/knowledge-bases/{kid}", json={"name": "a\\b"})
        assert resp.status_code == 422
        assert resp.json()["detail"] == _rule(naming.SEPARATOR)
        assert (await client.get(f"/api/knowledge-bases/{kid}")).json()["name"] == "Docs"

    async def test_mcp_put(self, client) -> None:
        sid = (await client.post("/api/mcp-sources", json={**_MCP, "name": "M"})).json()["id"]
        resp = await client.put(f"/api/mcp-sources/{sid}", json={"name": "a/b"})
        assert resp.status_code == 422
        assert resp.json()["detail"] == _rule(naming.SEPARATOR)
        assert (await client.get(f"/api/mcp-sources/{sid}")).json()["name"] == "M"
        reserved = await client.put(
            f"/api/mcp-sources/{sid}", json={"name": " self-configuration "}
        )
        assert reserved.status_code == 409

    async def test_mcp_put_on_surface_row_still_409s_with_bad_name(self, client) -> None:
        await client.post("/api/agents", json={"name": "owner"})
        enabled = await client.post("/api/agents/owner/self-configuration")
        assert enabled.status_code == 200, enabled.text
        source_id = enabled.json()["source_id"]
        resp = await client.put(f"/api/mcp-sources/{source_id}", json={"name": "a/b"})
        assert resp.status_code == 409

    @pytest.mark.parametrize("kind", ["provider", "kb", "mcp"])
    async def test_put_without_name_keeps_a_legacy_bad_name(self, client, conn, kind) -> None:
        from the_one.db.models import KnowledgeBase, LLMProviderConfig
        from the_one.interfaces.web import api

        if kind == "provider":
            await (await api._provider_repo()).create(
                LLMProviderConfig(id="p1", name="old/bad", **_PROVIDER)
            )
            resp = await client.put("/api/providers/p1", json={"base_url": "http://localhost:1/v1"})
        elif kind == "kb":
            await (await api._kb_repo()).create(KnowledgeBase(id="k1", name="old/bad"))
            resp = await client.put("/api/knowledge-bases/k1", json={"description": "edited"})
        else:
            await (await api._mcp_repo()).create(MCPSource(id="m1", name="old/bad", **_MCP))
            resp = await client.put("/api/mcp-sources/m1", json={"config": {"command": "true"}})
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "old/bad"


class TestAgentCreateAndRename:
    async def test_duplicate_create_is_409_and_keeps_the_stored_agent(self, client) -> None:
        first = await client.post(
            "/api/agents", json={"name": "dup", "description": "first", "system_prompt": "sp"}
        )
        assert first.status_code == 201
        resp = await client.post(
            "/api/agents", json={"name": "dup", "description": "second", "system_prompt": "other"}
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == _conflict()
        stored = (await client.get("/api/agents/dup")).json()
        assert stored["description"] == "first"
        assert stored["system_prompt"] == "sp"

    async def test_rename_details(self, client) -> None:
        await client.post("/api/agents", json={"name": "alpha"})
        await client.post("/api/agents", json={"name": "beta"})
        url = "/api/agents/alpha/rename"

        resp = await client.post(url, json={})
        assert (resp.status_code, resp.json()["detail"]) == (422, _rule(naming.EMPTY))
        resp = await client.post(url, json={"new_name": "  "})
        assert (resp.status_code, resp.json()["detail"]) == (422, _rule(naming.EMPTY))
        resp = await client.post(url, json={"new_name": " alpha "})
        assert (resp.status_code, resp.json()["detail"]) == (
            422,
            _rule(naming.SAME_AS_CURRENT),
        )
        resp = await client.post(url, json={"new_name": "a/b"})
        assert (resp.status_code, resp.json()["detail"]) == (422, _rule(naming.SEPARATOR))
        resp = await client.post(url, json={"new_name": "beta"})
        assert (resp.status_code, resp.json()["detail"]) == (409, _conflict())
        resp = await client.post("/api/agents/nobody/rename", json={"new_name": "gamma"})
        assert resp.status_code == 404
        assert isinstance(resp.json()["detail"], str)
        assert (await client.get("/api/agents/alpha")).status_code == 200

    async def test_rename_trims(self, client) -> None:
        await client.post("/api/agents", json={"name": "alpha"})
        resp = await client.post("/api/agents/alpha/rename", json={"new_name": " gamma "})
        assert resp.status_code == 200
        assert resp.json()["name"] == "gamma"

    async def test_encoded_slash_path_is_404(self, client) -> None:
        resp = await client.put("/api/agents/a%2Fb", json={"description": "x"})
        assert resp.status_code == 404

    async def test_legacy_bad_agent_stays_editable(self, client, conn) -> None:
        from the_one.agent.config import AgentConfig

        await SQLiteAgentStore(conn).save(AgentConfig(name="legacy.ok"))
        resp = await client.put("/api/agents/legacy.ok", json={"description": "edited"})
        assert resp.status_code == 200


class TestRoutineNames:
    """M33 F1: routine names go through ``check_name`` on POST and PUT."""

    _BODY = {
        "prompt": "p",
        "schedule": daily("09:00"),
    }

    async def _agent(self, client) -> None:
        assert (await client.post("/api/agents", json={"name": "ag"})).status_code == 201

    @pytest.mark.parametrize(("name", "msg"), [("a/b", naming.SEPARATOR), ("", naming.EMPTY)])
    async def test_create_refuses(self, client, name, msg) -> None:
        await self._agent(client)
        resp = await client.post("/api/agents/ag/routines", json={**self._BODY, "name": name})
        assert resp.status_code == 422
        assert resp.json()["detail"] == _rule(msg)
        assert (await client.get("/api/agents/ag/routines")).json()["routines"] == []

    @pytest.mark.parametrize(("name", "msg"), [("a/b", naming.SEPARATOR), ("", naming.EMPTY)])
    async def test_put_refuses(self, client, name, msg) -> None:
        await self._agent(client)
        made = await client.post("/api/agents/ag/routines", json={**self._BODY, "name": "ok"})
        rid = made.json()["id"]
        resp = await client.put(f"/api/agents/ag/routines/{rid}", json={"name": name})
        assert resp.status_code == 422
        assert resp.json()["detail"] == _rule(msg)
        got = await client.get(f"/api/agents/ag/routines/{rid}")
        assert got.json()["name"] == "ok"

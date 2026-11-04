"""Shared harness for the per-agent MCP tool-list tests (sortie 09 leg 2).

``world(tmp_path, monkeypatch)`` is an async context manager that yields a ``World``:
an API client over the shared app, a template database with one key-checking
streamable-HTTP source whose ``X-Api-Key`` header is blank ("Set per agent"), the
in-process key server (reached through the transport's factory test seam, so each
connection gets a fresh client) and its request log.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import httpx2
from asgi_lifespan import LifespanManager
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from tests.fixtures.mcp.key_server import make_key_app
from the_one.db.models import MCPSource
from the_one.db.repositories import (
    AgentMcpToolCacheRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor
from the_one.mcp import _pool
from the_one.mcp._tool_provider import MCPToolProvider
from the_one.mcp.transports import streamable_http as sh

SID = "src-keyed"
KEY1, KEY2, KEY3 = "alpha-key-1", "beta-key-22", "gamma-key-333"
TAIL1, TAIL2, TAIL3 = KEY1[-4:], KEY2[-4:], KEY3[-4:]
MODULES = (
    "the_one.interfaces.web.api",
    "the_one.mcp._tool_provider",
    "the_one.mcp._pool",
    "the_one.db.connection",
)


@dataclass
class World:
    api: Any
    repo: MCPSourceRepository
    key_app: Any
    conn: Any
    encryptor: Any

    @property
    def cache(self) -> AgentMcpToolCacheRepository:
        return AgentMcpToolCacheRepository(self.conn)

    async def save_agent(self, name, key=None, *, method="post", extra=None):
        body: dict[str, Any] = {"name": name, "mcp_source_ids": [SID], **(extra or {})}
        if key is not None:
            body["mcp_overrides"] = {"srv": {"headers": {"X-Api-Key": key}}}
        if method == "post":
            resp = await self.api.post("/api/agents", json=body)
            assert resp.status_code == 201, resp.text
        else:
            resp = await self.api.put(f"/api/agents/{name}", json=body)
            assert resp.status_code == 200, resp.text
        return resp.json()

    async def build_tools(self, name):
        cfg = await SQLiteAgentStore(self.conn, self.encryptor).load(name)
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name=name)
        return {t.name: t for t in tools}

    def tools_list_tails(self):
        return [e["key_tail"] for e in self.key_app.log if e["method"] == "tools/list"]

    def requests(self):
        return list(self.key_app.log)


@contextlib.asynccontextmanager
async def world(tmp_path, monkeypatch, *, keys=None, library_headers=None):
    await _pool._clear_for_test()
    monkeypatch.setattr(_pool, "_resolve_ttl_seconds", lambda: 3600)
    monkeypatch.setattr(_pool, "_WORKER_TEARDOWN_TIMEOUT_SECONDS", 2.0)
    conn = await connect_template_db(tmp_path / "w.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "w.key")
    repo = MCPSourceRepository(conn, encryptor)
    key_app = make_key_app(
        "X-Api-Key",
        keys or {KEY1: ["echo"], KEY2: ["echo", "add"], KEY3: ["echo", "add"]},
    )

    def factory(headers):
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=key_app),
            base_url="http://localhost",
            headers=headers,
        )

    monkeypatch.setattr(sh, "_test_http_client_override", factory)
    await repo.create(
        MCPSource(
            id=SID,
            name="srv",
            type="streamable-http",
            config={
                "url": "http://localhost/mcp",
                "headers": library_headers if library_headers is not None else {"X-Api-Key": ""},
            },
        )
    )
    patches = [patch(f"{mod}.get_connection", return_value=conn) for mod in MODULES] + [
        patch(f"{mod}.get_encryptor", return_value=encryptor)
        for mod in (*MODULES[:3], "the_one.encryption")
    ]
    for p in patches:
        p.start()
    try:
        async with LifespanManager(key_app):
            async with AsyncClient(
                transport=ASGITransport(app=shared_app()),
                base_url="http://test",
                headers=auth_headers(),
            ) as api:
                yield World(api, repo, key_app, conn, encryptor)
    finally:
        for p in patches:
            p.stop()
        await _pool._clear_for_test()
        await conn.close()

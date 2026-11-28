"""Shared wiring for tests that drive the REAL MCP pool against ``OAuthASStub`` (sortie 22).

The pool's OAuth token storage reads tokens from the database row (not from the
``source_override``), so these tests create the source row through
``MCPSourceRepository`` over a template database and patch the pool's (and the
source resolver's) module-level ``get_connection`` / ``get_encryptor`` to it.

``pool_db`` is a context manager; ``clean_pool_state`` is an autouse-style async
fixture a test module imports and re-declares as ``autouse=True``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from cryptography.fernet import Fernet

from tests._schema_template import connect_template_db
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import Encryptor
from the_one.llm.base import Message, ToolCall
from the_one.mcp import _pool
from the_one.mcp._tool import MCPClientTool
from the_one.mcp.oauth import _state
from the_one.mcp.types import MCPTool
from the_one.tools.base import ToolRegistry

SOURCE_ID = "src-pool"
AGENT_NAME = "a"
CSID = "0123456789ab"  # a real-looking hex chat-session id, never a synthetic one
TOOL_NAME = "echo"


async def reset_pool_state() -> None:
    await _pool._clear_for_test()
    _state._pending.clear()


def stale_secrets(shape: str) -> dict:
    """``expired``: past ``token_expires_at`` (the squawk 0444 refresh-first path).
    ``revoked``: locally valid, server-rejected (a 401 starts the flow)."""
    expires = time.time() - 100 if shape == "expired" else time.time() + 3600
    return {
        "dcr_credentials": {
            "client_id": "stub-client-1",
            "redirect_uris": ["http://127.0.0.1:8484/api/oauth/callback"],
            "token_endpoint_auth_method": "none",
        },
        "access_token": "expired-access-token",
        "refresh_token": "revoked-refresh-token",
        "token_expires_at": expires,
    }


def oauth_source(base_url: str, shape: str = "expired") -> MCPSource:
    return MCPSource(
        id=SOURCE_ID,
        name="pool-stub",
        type="streamable-http",
        config={"url": f"{base_url}/mcp", "_cache": {"auth_posture": "oauth"}},
        secrets=stale_secrets(shape),
    )


@asynccontextmanager
async def pool_db(
    tmp_path: Path, monkeypatch, source: MCPSource
) -> AsyncIterator[tuple[object, MCPSourceRepository]]:
    """A template DB holding ``source``, wired into the pool and the resolver."""
    conn = await connect_template_db(tmp_path / "pool.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    await repo.create(source)

    async def _get_connection():
        return conn

    for module in ("the_one.mcp._pool", "the_one.mcp._tool_provider"):
        monkeypatch.setattr(f"{module}.get_connection", _get_connection)
        monkeypatch.setattr(f"{module}.get_encryptor", lambda _dir, _e=encryptor: _e)
    try:
        yield conn, repo
    finally:
        await conn.close()


def build_tool(source: MCPSource) -> MCPClientTool:
    mt = MCPTool(
        name=TOOL_NAME,
        description="d",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        annotations=None,
    )
    return MCPClientTool(mt, source.id, source.name, AGENT_NAME, source)


def tool_call_script(tool: MCPClientTool, *, final: str = "done") -> list[Message]:
    return [
        Message.assistant("", tool_calls=[ToolCall(id="tc-1", name=tool.name, arguments={})]),
        Message.assistant(final),
    ]


def build_registry(tool: MCPClientTool) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(tool)
    return reg

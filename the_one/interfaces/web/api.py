"""REST API routes for agents, knowledge bases, MCP sources, and chat sessions."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, KBItem, KnowledgeBase, MCPSource
from the_one.db.repositories import (
    ChatSessionRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)

router = APIRouter(prefix="/api")


# ── Helpers ───────────────────────────────────────────────────────────────


async def _agent_store() -> SQLiteAgentStore:
    conn = await get_connection()
    return SQLiteAgentStore(conn)


async def _kb_repo() -> KnowledgeBaseRepository:
    conn = await get_connection()
    return KnowledgeBaseRepository(conn)


async def _kb_item_repo() -> KBItemRepository:
    conn = await get_connection()
    return KBItemRepository(conn)


async def _mcp_repo() -> MCPSourceRepository:
    conn = await get_connection()
    return MCPSourceRepository(conn)


async def _chat_repo() -> ChatSessionRepository:
    conn = await get_connection()
    return ChatSessionRepository(conn)


# ── Agents ────────────────────────────────────────────────────────────────


@router.get("/agents")
async def list_agents() -> list[dict[str, Any]]:
    store = await _agent_store()
    names = await store.list_agents()
    agents = []
    for name in names:
        cfg = await store.load(name)
        agents.append(cfg.model_dump())
    return agents


@router.get("/agents/{name}")
async def get_agent(name: str) -> dict[str, Any]:
    store = await _agent_store()
    try:
        cfg = await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return cfg.model_dump()


@router.post("/agents", status_code=201)
async def create_agent(request: Request) -> dict[str, Any]:
    from the_one.agent.config import AgentConfig

    data = await request.json()
    cfg = AgentConfig.model_validate(data)
    store = await _agent_store()
    await store.save(cfg)
    return cfg.model_dump()


@router.put("/agents/{name}")
async def update_agent(name: str, request: Request) -> dict[str, Any]:
    from the_one.agent.config import AgentConfig

    store = await _agent_store()
    try:
        await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    data = await request.json()
    data["name"] = name  # Ensure name matches path
    cfg = AgentConfig.model_validate(data)
    await store.save(cfg)
    return cfg.model_dump()


@router.delete("/agents/{name}")
async def delete_agent(name: str) -> dict[str, str]:
    store = await _agent_store()
    try:
        await store.delete(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return {"status": "ok"}


# ── Knowledge Bases ───────────────────────────────────────────────────────


@router.get("/knowledge-bases")
async def list_knowledge_bases() -> list[dict[str, Any]]:
    repo = await _kb_repo()
    kbs = await repo.list()
    return [kb.model_dump() for kb in kbs]


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(kb_id: str) -> dict[str, Any]:
    repo = await _kb_repo()
    try:
        kb = await repo.get(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")
    return kb.model_dump()


@router.post("/knowledge-bases", status_code=201)
async def create_knowledge_base(request: Request) -> dict[str, Any]:
    data = await request.json()
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    kb = KnowledgeBase.model_validate(data)
    repo = await _kb_repo()
    await repo.create(kb)
    return kb.model_dump()


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(kb_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["id"] = kb_id
    repo = await _kb_repo()
    try:
        existing = await repo.get(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")
    updated = existing.model_copy(update=data)
    await repo.update(updated)
    return updated.model_dump()


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(kb_id: str) -> dict[str, str]:
    repo = await _kb_repo()
    try:
        await repo.delete(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")
    return {"status": "ok"}


# ── KB Items ──────────────────────────────────────────────────────────────


@router.get("/knowledge-bases/{kb_id}/items")
async def list_kb_items(kb_id: str) -> list[dict[str, Any]]:
    repo = await _kb_item_repo()
    items = await repo.list(kb_id)
    return [item.model_dump() for item in items]


@router.post("/knowledge-bases/{kb_id}/items", status_code=201)
async def create_kb_item(kb_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["kb_id"] = kb_id
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    item = KBItem.model_validate(data)
    repo = await _kb_item_repo()
    await repo.create(item)
    return item.model_dump()


@router.delete("/knowledge-bases/{kb_id}/items/{item_id}")
async def delete_kb_item(kb_id: str, item_id: str) -> dict[str, str]:
    repo = await _kb_item_repo()
    try:
        await repo.delete(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    return {"status": "ok"}


# ── MCP Sources ───────────────────────────────────────────────────────────


@router.get("/mcp-sources")
async def list_mcp_sources() -> list[dict[str, Any]]:
    repo = await _mcp_repo()
    sources = await repo.list()
    return [s.model_dump() for s in sources]


@router.get("/mcp-sources/{source_id}")
async def get_mcp_source(source_id: str) -> dict[str, Any]:
    repo = await _mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    return source.model_dump()


@router.post("/mcp-sources", status_code=201)
async def create_mcp_source(request: Request) -> dict[str, Any]:
    data = await request.json()
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    source = MCPSource.model_validate(data)
    repo = await _mcp_repo()
    await repo.create(source)
    return source.model_dump()


@router.put("/mcp-sources/{source_id}")
async def update_mcp_source(source_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["id"] = source_id
    repo = await _mcp_repo()
    try:
        existing = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    updated = existing.model_copy(update=data)
    await repo.update(updated)
    return updated.model_dump()


@router.delete("/mcp-sources/{source_id}")
async def delete_mcp_source(source_id: str) -> dict[str, str]:
    repo = await _mcp_repo()
    try:
        await repo.delete(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    return {"status": "ok"}


# ── Chat Sessions ─────────────────────────────────────────────────────────


@router.get("/chat/sessions")
async def list_chat_sessions(agent_name: str | None = None) -> list[dict[str, Any]]:
    repo = await _chat_repo()
    sessions = await repo.list(agent_name=agent_name)
    return [_session_summary(s) for s in sessions]


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str) -> dict[str, Any]:
    repo = await _chat_repo()
    try:
        session = await repo.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return {
        **_session_summary(session),
        "messages": json.loads(session.messages),
    }


@router.post("/chat/sessions", status_code=201)
async def create_chat_session(request: Request) -> dict[str, Any]:
    data = await request.json()
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    session = ChatSession.model_validate(data)
    repo = await _chat_repo()
    await repo.create(session)
    return _session_summary(session)


@router.put("/chat/sessions/{session_id}")
async def update_chat_session(session_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["id"] = session_id
    repo = await _chat_repo()
    try:
        existing = await repo.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    updated = existing.model_copy(update=data)
    await repo.update(updated)
    return _session_summary(updated)


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str) -> dict[str, str]:
    repo = await _chat_repo()
    try:
        await repo.delete(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return {"status": "ok"}


@router.post("/chat/sessions/{session_id}/purge")
async def purge_chat_messages(session_id: str) -> dict[str, str]:
    repo = await _chat_repo()
    try:
        await repo.purge_messages(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return {"status": "ok"}


def _session_summary(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "agent_name": session.agent_name,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }

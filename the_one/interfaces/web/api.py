"""REST API routes for agents, knowledge bases, MCP sources, and chat sessions."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from the_one.config import Settings, settings
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, KBItem, KnowledgeBase, LLMProviderConfig, MCPSource
from the_one.db.repositories import (
    ChatSessionRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor, get_encryptor
from the_one.llm import ollama_api

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


# ── Settings ──────────────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return {
        name: str(val) if isinstance(val, Path) else val
        for name in Settings.model_fields
        for val in [getattr(settings, name)]
    }


# ── Tools ─────────────────────────────────────────────────────────────────


@router.get("/tools")
async def list_tools() -> list[dict[str, str]]:
    from the_one.tools.builtins import BuiltinToolProvider

    provider = BuiltinToolProvider()
    return [{"name": t.name, "description": t.description} for t in provider.get_tools()]


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


# ── LLM Provider helpers ────────────────────────────────────────────────


async def _provider_repo() -> LLMProviderRepository:
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    return LLMProviderRepository(conn, encryptor)


def _mask_api_key(key: str | None) -> str | None:
    if not key:
        return key
    if len(key) <= 4:
        return "***"
    return f"***...{key[-4:]}"


def _provider_response(provider: LLMProviderConfig) -> dict[str, Any]:
    data = provider.model_dump()
    data["api_key"] = _mask_api_key(provider.api_key)
    return data


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


async def _get_ollama_base_url(provider_id: str) -> str:
    """Load a provider by ID, validate it's ollama-type, and return the native base_url.

    Raises HTTPException(404) if not found, HTTPException(400) if not ollama-type.
    """
    repo = await _provider_repo()
    try:
        provider = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    if provider.type != "ollama":
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider_id}' is type '{provider.type}', not 'ollama'",
        )
    return provider.base_url.rstrip("/").removesuffix("/v1")


# ── LLM Providers ───────────────────────────────────────────────────────


@router.get("/providers")
async def list_providers() -> list[dict[str, Any]]:
    repo = await _provider_repo()
    providers = await repo.list()
    return [_provider_response(p) for p in providers]


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: str) -> dict[str, Any]:
    repo = await _provider_repo()
    try:
        provider = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    return _provider_response(provider)


@router.post("/providers", status_code=201)
async def create_provider(request: Request) -> dict[str, Any]:
    data = await request.json()
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    provider = LLMProviderConfig.model_validate(data)
    repo = await _provider_repo()
    await repo.create(provider)
    return _provider_response(provider)


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["id"] = provider_id
    repo = await _provider_repo()
    try:
        existing = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    # Detect masked API key and preserve existing stored key
    incoming_key = data.get("api_key")
    if incoming_key and incoming_key.startswith("***"):
        data["api_key"] = existing.api_key

    updated = existing.model_copy(update=data)
    await repo.update(updated)
    return _provider_response(updated)


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str) -> dict[str, str]:
    repo = await _provider_repo()
    try:
        await repo.delete(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    return {"status": "ok"}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str) -> dict[str, Any]:
    repo = await _provider_repo()
    try:
        provider = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    try:
        if provider.type == "ollama":
            base = provider.base_url.rstrip("/").removesuffix("/v1")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base}/api/tags")
                resp.raise_for_status()
            return {"status": "ok", "detail": "Connected to Ollama"}
        elif provider.type == "openai-compatible":
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{provider.base_url.rstrip('/')}/models",
                    headers=_auth_headers(provider.api_key),
                )
                resp.raise_for_status()
            return {"status": "ok", "detail": "Connected"}
        elif provider.type == "openai":
            import openai

            client = openai.AsyncOpenAI(api_key=provider.api_key)
            await client.models.list()
            return {"status": "ok", "detail": "Connected to OpenAI"}
        elif provider.type == "anthropic":
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=provider.api_key)
            await client.models.list()
            return {"status": "ok", "detail": "Connected to Anthropic"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    return {"status": "error", "detail": f"Unknown provider type: {provider.type}"}


@router.get("/providers/{provider_id}/models")
async def list_provider_models(provider_id: str) -> list[dict[str, Any]]:
    repo = await _provider_repo()
    try:
        provider = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    if provider.type == "ollama":
        try:
            base = provider.base_url.rstrip("/").removesuffix("/v1")
            models = await ollama_api.list_models(base)
            return [
                {"id": m.get("name", ""), "name": m.get("name", ""), "size": m.get("size")}
                for m in models
            ]
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    elif provider.type == "openai-compatible":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{provider.base_url.rstrip('/')}/models",
                    headers=_auth_headers(provider.api_key),
                )
                resp.raise_for_status()
            data = resp.json().get("data", [])
            return [{"id": m.get("id", ""), "name": m.get("id", "")} for m in data]
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    elif provider.type == "openai":
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=provider.api_key)
            response = await client.models.list()
            return [{"id": m.id, "name": m.id} for m in response.data]
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    elif provider.type == "anthropic":
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=provider.api_key)
            response = await client.models.list()
            return [
                {"id": m.id, "name": getattr(m, "display_name", m.id)} for m in response.data
            ]
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    return []


# ── Ollama Model Lifecycle ────────────────────────────────────────────────


@router.post("/providers/{provider_id}/models/pull")
async def pull_model(provider_id: str, request: Request) -> StreamingResponse:
    base_url = await _get_ollama_base_url(provider_id)
    data = await request.json()
    model = data.get("model", "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Missing or empty 'model' field")

    async def _stream():
        try:
            async for progress in ollama_api.pull_model(base_url, model):
                yield f"data: {json.dumps(progress)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/providers/{provider_id}/models/delete")
async def delete_model(provider_id: str, request: Request) -> dict[str, str]:
    base_url = await _get_ollama_base_url(provider_id)
    data = await request.json()
    model = data.get("model", "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Missing or empty 'model' field")
    try:
        await ollama_api.delete_model(base_url, model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "ok"}


@router.post("/providers/{provider_id}/models/load")
async def load_model(provider_id: str, request: Request) -> dict[str, str]:
    base_url = await _get_ollama_base_url(provider_id)
    data = await request.json()
    model = data.get("model", "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Missing or empty 'model' field")
    try:
        await ollama_api.load_model(base_url, model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "ok"}


@router.post("/providers/{provider_id}/models/unload")
async def unload_model(provider_id: str, request: Request) -> dict[str, str]:
    base_url = await _get_ollama_base_url(provider_id)
    data = await request.json()
    model = data.get("model", "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Missing or empty 'model' field")
    try:
        await ollama_api.unload_model(base_url, model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "ok"}


@router.get("/providers/{provider_id}/models/status")
async def model_status(provider_id: str) -> list[dict[str, Any]]:
    base_url = await _get_ollama_base_url(provider_id)
    try:
        return await ollama_api.list_running(base_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Encryption ───────────────────────────────────────────────────────────


@router.post("/encryption/rotate")
async def rotate_encryption_key() -> dict[str, str]:
    encryptor = get_encryptor(settings.data_dir)
    conn = await get_connection()

    # 1. Pre-fetch and decrypt all stored API keys before rotation
    async with conn.execute(
        "SELECT id, api_key FROM llm_providers WHERE api_key IS NOT NULL AND api_key != ''"
    ) as cur:
        rows = await cur.fetchall()
    decrypted = [(row["id"], encryptor.decrypt(row["api_key"])) for row in rows]

    # 2. Re-encrypt inside the callback so that callback failure preserves the old key
    reencrypted: list[tuple[str, str]] = []

    def _reencrypt(_old: Encryptor, new: Encryptor) -> None:
        for provider_id, plaintext in decrypted:
            reencrypted.append((provider_id, new.encrypt(plaintext)))

    encryptor.rotate_key(_reencrypt)

    # 3. Key file now reflects the new key — write re-encrypted values to DB
    for provider_id, ciphertext in reencrypted:
        await conn.execute(
            "UPDATE llm_providers SET api_key = ? WHERE id = ?",
            (ciphertext, provider_id),
        )
    await conn.commit()
    return {"status": "ok"}

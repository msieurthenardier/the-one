"""REST API routes for agents, knowledge bases, MCP sources, and chat sessions."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import ValidationError

from the_one import __version__
from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, KBItem, KnowledgeBase, LLMProviderConfig, MCPSource
from the_one.db.repositories import (
    ChatSessionRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
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
    encryptor = get_encryptor(settings.data_dir)
    return MCPSourceRepository(conn, encryptor)


async def _chat_repo() -> ChatSessionRepository:
    conn = await get_connection()
    return ChatSessionRepository(conn)


# ── Tool config helpers (F6 L1) ───────────────────────────────────────────

_TESTABLE_TOOLS = frozenset({"web_search", "fetch_url"})

# F6.5 L3: Test connection endpoint timeout (seconds). Bounds the await
# on consent_url_future so a slow / hanging SDK auth flow doesn't pin
# the request indefinitely. 15s is the Design Decision §2 ceiling;
# tests monkeypatch this to drive the timeout path quickly.
_TEST_CONNECT_TIMEOUT: float = 15.0


async def _tool_config_repo() -> ToolConfigRepository:
    conn = await get_connection()
    return ToolConfigRepository(conn)


def _enrich_schema_with_markers(schema: dict[str, Any], config_class: type) -> dict[str, Any]:
    """Inject `x_marker` per top-level property by reading
    `config_class.model_fields[name].metadata`. Pydantic v2 does not
    surface marker classes in `model_json_schema()`; the resolver
    dispatches on `m is Narrow` / `m is Substitute` identity at
    `the_one/tools/resolver.py:233-236` — same pattern here.

    Mutates `schema` in place AND returns it (caller convenience —
    both forms work). Safe to call on `_EmptyConfig` (no-op since
    `model_fields` is empty).

    Assumes a flat schema (no nested BaseModel fields under `$defs`).
    All four F2-F5 Configs (FilesystemConfig, ExecutionConfig,
    PythonExecConfig, WebConfig) are flat. A future Config that
    nests another BaseModel will need a `$defs` walk added here.
    """
    from the_one.tools.resolver import (
        Narrow,
        NarrowPrefix,
        NarrowSuperset,
        Substitute,
    )

    marker_map = {
        Narrow: "Narrow",
        NarrowPrefix: "NarrowPrefix",
        NarrowSuperset: "NarrowSuperset",
        Substitute: "Substitute",
    }
    properties = schema.get("properties") or {}
    for field_name, field_info in config_class.model_fields.items():
        prop = properties.get(field_name)
        if prop is None:
            continue
        for marker_cls, marker_name in marker_map.items():
            if any(m is marker_cls for m in field_info.metadata):
                prop["x_marker"] = marker_name
                break
    return schema


# ── Client config ─────────────────────────────────────────────────────────


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """Client-visible configuration — dev mode flag + version.

    Fetched once at boot by the JS client (app.js DOMContentLoaded
    handler) and cached on window.App.config. The dev_mode flag gates
    the dev-mode-only Design Language Admin category (Mission 08 F2).
    """
    return {"dev_mode": settings.dev_mode, "version": __version__}


# ── Tools ─────────────────────────────────────────────────────────────────


@router.get("/tools")
async def list_tools() -> list[dict[str, str]]:
    from the_one.tools.builtins import BuiltinToolProvider

    provider = BuiltinToolProvider()
    return [{"name": t.name, "description": t.description} for t in provider.get_tools()]


# ── Tool configs ──────────────────────────────────────────────────────────


@router.get("/tools/configs")
async def list_tool_configs() -> list[dict[str, Any]]:
    """Operator-facing tool-config list. Tools without a saved row
    appear with `enabled=True` and `config={}` (the default state).
    Sorted by tool name. The L2 admin grid consumes this."""
    from the_one.tools.builtins import _TOOL_CLASSES

    repo = await _tool_config_repo()
    saved = {c.name: c for c in await repo.list()}
    result: list[dict[str, Any]] = []
    for name in sorted(_TOOL_CLASSES):
        cls = _TOOL_CLASSES[name]
        row = saved.get(name)
        result.append(
            {
                "name": name,
                "description": cls.description,
                "enabled": row.enabled if row else True,
                "config": row.config if row else {},
            }
        )
    return result


@router.get("/tools/configs/{name}")
async def get_tool_config(name: str) -> dict[str, Any]:
    """Per-tool detail with marker-enriched JSON Schema. The L3 editor
    drives form rendering from the returned `schema`."""
    from the_one.tools.builtins import _TOOL_CLASSES

    cls = _TOOL_CLASSES.get(name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    repo = await _tool_config_repo()
    try:
        row = await repo.get(name)
        enabled = row.enabled
        config = row.config
    except KeyError:
        enabled = True
        config = {}
    schema = _enrich_schema_with_markers(cls.Config.model_json_schema(), cls.Config)
    return {
        "name": name,
        "description": cls.description,
        "enabled": enabled,
        "config": config,
        "schema": schema,
    }


@router.put("/tools/configs/{name}")
async def upsert_tool_config(name: str, request: Request) -> dict[str, Any]:
    """Upsert the operator-saved config + enabled state.

    Body shape: `{enabled?: bool, config?: dict}`.

    REPLACE-not-merge contract for `config`: when present in body,
    REPLACES the saved config wholesale (REST PUT convention). The
    L3 form always submits the full Config state, so REPLACE matches
    its actual behaviour. To wipe to defaults, send `{"config": {}}`.

    Top-level keys are preserved when omitted: PUT `{"enabled": true}`
    (no `config` key) updates only `enabled` and leaves `config`
    intact. Symmetric for `config`-only PUTs.

    Validates submitted `config` against `cls.Config` — Pydantic v2's
    default `extra="ignore"` (verified for all four F2-F5 Configs)
    silently drops unknown extras.
    """
    from the_one.tools.builtins import _TOOL_CLASSES

    cls = _TOOL_CLASSES.get(name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    data = await request.json()
    repo = await _tool_config_repo()
    try:
        existing = await repo.get(name)
        current_enabled = existing.enabled
        current_config = existing.config
    except KeyError:
        current_enabled = True
        current_config = {}

    # `enabled` — preserve when omitted from body; coerce when present.
    new_enabled = bool(data["enabled"]) if "enabled" in data else current_enabled

    # `config` — REPLACE when present (validate body), preserve when omitted.
    if "config" in data:
        try:
            validated = cls.Config.model_validate(data["config"])
        except ValidationError as e:
            # `e.errors()` may carry a raw exception in `ctx['error']` (Pydantic
            # v2 model-validator path) which is NOT JSON-serializable. Pass
            # `include_context=False` so the response stays JSON-encodable —
            # `msg` + `loc` carry the human-readable diagnostic the L3 form
            # surfaces inline. Discovered during F6 L6 HAT scenario 3 when an
            # operator narrowed `timeout_seconds_max < timeout_seconds_default`
            # and the resulting model-validator ValueError crashed the JSON
            # encoder, surfacing as 500 instead of 422.
            raise HTTPException(status_code=422, detail=e.errors(include_context=False))
        new_config = validated.model_dump()
    else:
        new_config = current_config

    await repo.upsert(name, new_config, enabled=new_enabled)
    return {
        "name": name,
        "description": cls.description,
        "enabled": new_enabled,
        "config": new_config,
    }


@router.post("/tools/configs/{name}/test")
async def test_tool_config(name: str, request: Request) -> dict[str, Any]:
    """Run a connection test against the named tool's currently-saved
    Config (Decision 5). Only `web_search` and `fetch_url` are
    testable. Tool-side failures (constraint refusals, network
    errors) come through as `[error] [constraint] ...` strings in
    `output` — not HTTP 5xx — so the operator sees the agent's view.

    Named-tool isolation: `BuiltinToolProvider.get_tools` builds
    `cross_configs[Config]` by walking `_TOOL_CLASSES` in declared
    order and resolving from the FIRST tool name carrying that
    Config. For WebConfig, that's `http_request`. To honour
    Decision 5's "named tool's saved Config" semantics in the test
    endpoint, we re-key the input dict so EVERY tool sharing the
    named tool's Config class is given the named tool's saved row.
    This makes `cross_configs[NamedConfig]` carry the tested tool's
    saved config regardless of declaration order. Sibling tools
    with different Config classes get their own saved rows.
    """
    from the_one.tools.builtins import _TOOL_CLASSES, BuiltinToolProvider

    # 404 takes precedence over 400 — unknown name is not "untestable",
    # it's "doesn't exist".
    if name not in _TOOL_CLASSES:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    if name not in _TESTABLE_TOOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Tool {name} does not support connection testing",
        )

    repo = await _tool_config_repo()
    saved = {c.name: c.config for c in await repo.list()}
    named_config_class = _TOOL_CLASSES[name].Config
    named_config = saved.get(name, {})
    # Re-key sibling tools sharing the named tool's Config class to use
    # the named tool's saved row (Decision 5 named-tool isolation).
    # Other tools keep their own saved rows.
    tool_configs_by_name = dict(saved)
    for tname, tcls in _TOOL_CLASSES.items():
        if tcls.Config is named_config_class:
            tool_configs_by_name[tname] = named_config

    provider = BuiltinToolProvider()
    tools = provider.get_tools(tool_configs_by_name, {})
    tool = next(t for t in tools if t.name == name)

    # F6 HAT addition — accept optional override params from the request
    # body so the operator can test against a custom input. Empty/malformed
    # body falls back to the per-tool fixture defaults (preserves the
    # existing 200-on-empty-body behavior). Type guards drop malformed
    # values cleanly; the tool's own validation (URL parse, host check) is
    # the security boundary — these checks are belt-and-suspenders.
    try:
        raw = await request.body()
        body = json.loads(raw) if raw else {}
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    defaults = {
        "web_search": {"query": "the one cli agent", "max_results": 5},
        "fetch_url": {"url": "https://example.com/"},
    }[name]
    fixture_kwargs = dict(defaults)
    if name == "web_search":
        if isinstance(body.get("query"), str) and body["query"].strip():
            fixture_kwargs["query"] = body["query"]
        if isinstance(body.get("max_results"), int) and 1 <= body["max_results"] <= 50:
            fixture_kwargs["max_results"] = body["max_results"]
    elif name == "fetch_url":
        if isinstance(body.get("url"), str) and body["url"].strip():
            fixture_kwargs["url"] = body["url"]

    start = time.perf_counter()
    output = await tool.execute(**fixture_kwargs)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {"output": output, "elapsed_ms": elapsed_ms}


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
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
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
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
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


def _mask_secret_value(value: Any) -> Any:
    """Mask a single secret value mirroring ``_mask_api_key``'s shape.

    Type signature is ``Any -> Any`` (not ``str -> str``) because the
    secrets dict is ``dict[str, Any]`` per L2's MCPSource model — a
    client could in principle send a non-string value, and we want to
    mask it defensively rather than crash. Empty/None passes through
    unchanged; ≤4-char string values mask as ``***``; longer string
    values mask as ``***...{tail4}``; non-string values mask wholesale
    as ``***`` (no leakage of nested structure). Same per-decoded-value
    semantic as ``_mask_api_key``, kept separate so future MCP-secret
    shape changes don't drift LLM-provider behavior.
    """
    if not value:
        return value
    if not isinstance(value, str):
        # Non-string secret values (e.g., a nested dict for OAuth tokens
        # in F5) — mask wholesale to avoid leaking nested structure.
        # F5 will revisit this when access/refresh tokens land.
        return "***"
    if len(value) <= 4:
        return "***"
    return f"***...{value[-4:]}"


# OAuth-managed secret keys (F5 §5). These four keys are written ONLY by
# the OAuth flow's ``MCPSourceTokenStorage`` (``the_one.mcp.oauth.storage``)
# and are protected from operator overwrite via the strip-on-GET +
# preserve-on-PUT logic below. Defined ABOVE its first usage in
# ``_mcp_source_response`` (placement note: the leg's design suggested
# "near ``_MASKED_API_KEY_SENTINEL`` at api.py:886" but that constant is
# defined AFTER ``_mcp_source_response`` — a forward reference would
# fail at module import time, so the constant lives here instead. See
# leg L02 flight-log entry for the deliberate placement rationale).
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS as _OAUTH_MANAGED_SECRET_KEYS


def _mask_secrets(secrets: dict[str, Any]) -> dict[str, Any]:
    """Apply per-key masking to a decoded secrets dict.

    Iterates the dict; replaces each value with its masked form via
    ``_mask_secret_value``. Returns a NEW dict — does not mutate the
    input. Used by ``_mcp_source_response`` to produce the masked GET
    response shape.
    """
    return {k: _mask_secret_value(v) for k, v in secrets.items()}


def _mcp_source_response(source: MCPSource) -> dict[str, Any]:
    """Render an MCPSource into the masked HTTP response shape.

    Mirrors ``_provider_response`` — the response contains masked
    secret values per ``_mask_secrets``; ``config`` is passed through
    unchanged (operator-marked-non-sensitive).

    INVARIANT: ``model_dump()`` populates ``data["secrets"]`` with the
    decrypted plaintext dict; we OVERWRITE that key with the masked
    form before returning. Any future refactor that removes the
    overwrite would leak plaintext via the API. The
    ``test_list_returns_masked_secrets`` assertion
    ``"ghp_realsecretvalue" not in resp.text`` is the regression net.

    OAuth-managed keys (F5 §5) are STRIPPED from the visible payload
    BEFORE masking — the four token/credential keys must not surface
    via the API at all (not even as masked values). The unmodified
    source dict remains in memory; only the response payload is
    stripped. Tests:
    ``tests/test_oauth_secrets_api.py::test_get_strips_managed_keys``.
    """
    data = source.model_dump()
    visible = {k: v for k, v in source.secrets.items() if k not in _OAUTH_MANAGED_SECRET_KEYS}
    data["secrets"] = _mask_secrets(visible)
    # F9 L1 (vibing): expose a presence-only flag so the editor can decide
    # whether to render the "Reset connection" Danger-Zone button without
    # leaking the OAuth-managed secret values themselves. True iff ANY
    # OAuth-managed key is present in the persisted row's secrets.
    data["oauth_active"] = any(k in source.secrets for k in _OAUTH_MANAGED_SECRET_KEYS)
    return data


def _validate_mcp_source_config(source: MCPSource) -> None:
    """Transport-aware shape validation for MCPSource.config.

    Raises HTTPException(422, detail=...) on shape mismatch. Validation
    lives at the API layer so the error path returns a clean 422 with a
    human-readable detail string; Pydantic's literal validation already
    gates the ``type`` field at model validation time.

    Stdio: config.command is required (non-empty string); config.args
      must be a list[str] if present; config.cwd must be a string if
      present; config.env must be a dict[str, str] if present.
    Streamable-HTTP: config.url is required (non-empty string);
      config.headers must be a dict[str, str] if present.

    Stdio config.sandbox is optional and may carry
    ``{writable_paths: list[str], network_allowed: bool}``; both fields
    are optional within the sandbox sub-block. List-shape and bool-shape
    are validated; absolute-path semantics are NOT enforced at the API
    layer — the runtime (``BubblewrapSandbox.prepare_spawn``, F3 L3)
    raises ``MCPSandboxError`` when bwrap rejects the path at spawn
    time. Streamable-HTTP sources silently ignore ``config.sandbox``
    (the field is meaningless for non-spawning transports).
    """
    cfg = source.config

    if source.type == "stdio":
        command = cfg.get("command")
        if not isinstance(command, str) or not command.strip():
            raise HTTPException(
                status_code=422,
                detail="MCP source of type 'stdio' requires config.command (non-empty string).",
            )
        args = cfg.get("args", [])
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise HTTPException(
                status_code=422,
                detail="MCP source config.args must be a list of strings.",
            )
        cwd = cfg.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise HTTPException(
                status_code=422,
                detail="MCP source config.cwd must be a string if present.",
            )
        env = cfg.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env.items()
        ):
            raise HTTPException(
                status_code=422,
                detail="MCP source config.env must be a dict of string-to-string.",
            )
        sandbox = cfg.get("sandbox")
        # IMPORTANT: use ``is not None`` (NOT a truthy check). Empty dict
        # ``{}`` must pass through — the operator may post a sandbox
        # sub-block with no fields, and both writable_paths and
        # network_allowed are individually optional. Per F3 §4 + §12,
        # unknown keys (e.g. namespace-flag fields ``pid_unshare``,
        # ``ipc_unshare``, ``uts_unshare``) pass through untouched —
        # ``SandboxProfile.from_dict`` (L2 lands) is responsible for
        # type-checking advanced knobs at runtime construction time.
        # Path-shape (absolute / no ``..``) is NOT enforced here per
        # "trust the runtime" — bwrap will reject malformed paths at
        # spawn time via ``MCPSandboxError`` (L3 lands).
        if sandbox is not None:
            if not isinstance(sandbox, dict):
                raise HTTPException(
                    status_code=422,
                    detail="MCP source config.sandbox must be a dict if present.",
                )
            if "writable_paths" in sandbox:
                writable_paths = sandbox["writable_paths"]
                if not isinstance(writable_paths, list) or not all(
                    isinstance(p, str) for p in writable_paths
                ):
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "MCP source config.sandbox.writable_paths must be a list of strings."
                        ),
                    )
            if "network_allowed" in sandbox:
                network_allowed = sandbox["network_allowed"]
                # ``bool`` is a subclass of ``int`` in Python; the
                # ``isinstance(value, bool)`` check (NOT ``int``) means
                # a JSON ``1`` from a buggy client gets a 422.
                if not isinstance(network_allowed, bool):
                    raise HTTPException(
                        status_code=422,
                        detail=("MCP source config.sandbox.network_allowed must be a boolean."),
                    )

    elif source.type == "streamable-http":
        url = cfg.get("url")
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(
                status_code=422,
                detail=(
                    "MCP source of type 'streamable-http' requires config.url (non-empty string)."
                ),
            )
        headers = cfg.get("headers", {})
        if not isinstance(headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
        ):
            raise HTTPException(
                status_code=422,
                detail="MCP source config.headers must be a dict of string-to-string.",
            )

    else:
        # Defensive exhaustiveness — Pydantic's Literal validator
        # already rejects unknown types at MCPSource.model_validate
        # time, so this branch is unreachable for properly-validated
        # input. But if a future contributor adds a new transport
        # literal to the model and forgets to extend this helper,
        # that omission would silently permit any config shape. This
        # raise locks the contract: a new transport must add a
        # validation block here, or this raise fires.
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported MCP source type: {source.type}",
        )


@router.get("/mcp-sources")
async def list_mcp_sources() -> list[dict[str, Any]]:
    repo = await _mcp_repo()
    sources = await repo.list()
    return [_mcp_source_response(s) for s in sources]


@router.get("/mcp-sources/types")
async def list_mcp_source_types() -> list[dict[str, str]]:
    """Return the list of MCP source transport types selectable in the UI.

    NOTE: This route MUST be registered BEFORE ``/mcp-sources/{source_id}``
    because FastAPI matches routes in registration order. If reordered, a
    GET to ``/mcp-sources/types`` would resolve to ``get_mcp_source`` with
    ``source_id="types"`` and 404. Mirrors the provider precedent at
    ``list_provider_types``.
    """
    return [
        {"value": "stdio", "label": "Stdio"},
        {"value": "streamable-http", "label": "Streamable HTTP"},
    ]


@router.get("/mcp-sources/{source_id}")
async def get_mcp_source(source_id: str) -> dict[str, Any]:
    repo = await _mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    return _mcp_source_response(source)


@router.post("/mcp-sources", status_code=201)
async def create_mcp_source(request: Request) -> dict[str, Any]:
    data = await request.json()
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    try:
        source = MCPSource.model_validate(data)
    except ValidationError as e:
        # ``include_context=False`` so the response stays JSON-encodable
        # — ``model_validator`` paths populate ``ctx['error']`` with raw
        # exceptions that aren't JSON-serializable.
        raise HTTPException(status_code=422, detail=e.errors(include_context=False))
    _validate_mcp_source_config(source)
    repo = await _mcp_repo()
    await repo.create(source)
    return _mcp_source_response(source)


@router.put("/mcp-sources/{source_id}")
async def update_mcp_source(source_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["id"] = source_id
    repo = await _mcp_repo()
    try:
        existing = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

    # Per-key __MASKED__ handling inside the secrets dict — a sentinel
    # value preserves the corresponding existing stored value;
    # non-sentinel values overwrite. Keys absent from the incoming
    # secrets dict are dropped (REST PUT replace semantic, applied
    # per-key — operator explicitly drops a secret by omitting its
    # key). Note: ``_MASKED_API_KEY_SENTINEL`` is reused across the
    # provider single-``api_key`` column and the per-key MCP secrets
    # dict; the constant name is slightly misleading but renaming is a
    # cosmetic refactor out of scope for this leg.
    incoming_secrets = data.get("secrets")
    if incoming_secrets is not None:
        if not isinstance(incoming_secrets, dict):
            raise HTTPException(
                status_code=422,
                detail="secrets must be a dict.",
            )
        resolved_secrets: dict[str, Any] = {}
        for key, value in incoming_secrets.items():
            if value == _MASKED_API_KEY_SENTINEL:
                if key in existing.secrets:
                    resolved_secrets[key] = existing.secrets[key]
                # else: client sent __MASKED__ for a key we don't have;
                # drop it silently — same as if the client had omitted
                # the key entirely.
            else:
                resolved_secrets[key] = value
        # F5 §5: preserve OAuth-managed keys from existing.secrets and
        # silently drop any incoming-payload entries for those keys.
        # Only ``MCPSourceTokenStorage`` (the OAuth flow) writes them;
        # an operator PUT cannot overwrite them via the API. Applied
        # AFTER the per-key __MASKED__ resolution so a client-sent
        # ``access_token: "__MASKED__"`` doesn't fall through unhandled.
        # Tests: ``tests/test_oauth_secrets_api.py``.
        for key in _OAUTH_MANAGED_SECRET_KEYS:
            if key in existing.secrets:
                resolved_secrets[key] = existing.secrets[key]
            elif key in resolved_secrets:
                # Source has no managed key yet; incoming payload tried
                # to set one. Drop it — only the OAuth flow may write
                # these keys.
                del resolved_secrets[key]
        data["secrets"] = resolved_secrets

    # F9 L1 (vibing): preserve the existing tools cache across PUT.
    # The cache is server-managed (written by /test/connect after a
    # successful list_tools); an operator PUT must not be able to seed
    # or overwrite it. Mirrors the OAUTH_MANAGED_SECRET_KEYS preservation
    # pattern above — the operator gets REST replace semantics for keys
    # they own, but server-managed keys are pinned from `existing`.
    incoming_config = data.get("config")
    if isinstance(incoming_config, dict):
        # Drop any operator-supplied _cache (poisoning attempt or
        # innocent round-trip of the masked GET response).
        incoming_config.pop("_cache", None)
        existing_cache = (existing.config or {}).get("_cache")
        if existing_cache is not None:
            incoming_config["_cache"] = existing_cache
        data["config"] = incoming_config

    try:
        updated = existing.model_copy(update=data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_context=False))
    _validate_mcp_source_config(updated)
    await repo.update(updated)
    return _mcp_source_response(updated)


@router.delete("/mcp-sources/{source_id}")
async def delete_mcp_source(source_id: str) -> dict[str, str]:
    """Delete an MCP source and reclaim its lazy-install runtime cache.

    F9 L2 vibing follow-up: stdio sources whose ``config.command`` is a
    lazy-install runtime (``uvx``, ``npx``, ``pipx run``) leave behind a
    package cache under ``/root/.cache/uv/environments-v2`` or
    ``/root/.npm/_npx`` after first spawn. Without cleanup, deleting the
    source orphans that cache indefinitely. This handler:

    1. Reads the source so we can decode its (runtime, package) BEFORE
       the row is gone.
    2. Evicts every pool entry referencing the source so the next
       ``acquire`` doesn't hand out a stale client.
    3. Refcounts: if any OTHER source decodes to the same (runtime,
       package), we skip cleanup — the survivor still needs the cache.
    4. DELETEs the row.
    5. Best-effort cache cleanup AFTER the delete commits, so a hung
       ``uv cache clean`` cannot regress the user-facing delete signal.
       :func:`cleanup_runtime_cache` swallows all exceptions and bounds
       itself with an internal ``asyncio.wait_for(10.0)`` ceiling.

    Sources whose runtime is unknown (python/node/bash/Custom) skip
    cleanup entirely — there is no reliably-locatable cache slot to
    reclaim for those.
    """
    from the_one.mcp._pool import _evict_all_for_source
    from the_one.mcp.cache_cleanup import cleanup_runtime_cache, extract_runtime_package

    repo = await _mcp_repo()

    # Step 1: Read the source first so we can decode the runtime+package
    # BEFORE the row is gone. A 404 on read short-circuits with the
    # existing semantics — no eviction, no cleanup.
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

    cfg = source.config or {}
    command = cfg.get("command", "") if isinstance(cfg.get("command", ""), str) else ""
    args = cfg.get("args", []) or []
    runtime, package = (None, None)
    if isinstance(args, list):
        runtime, package = extract_runtime_package(command, args)

    # Step 2: Evict pool entries for this source.
    await _evict_all_for_source(source_id)

    # Step 3: Refcount cleanup — query before delete so the to-be-deleted
    # row is excluded by id.
    skip_reason: str | None = None
    if runtime and package:
        siblings = await repo.find_by_runtime_package(runtime, package, source_id)
        if siblings:
            sibling_ids = ", ".join(s.id for s in siblings)
            skip_reason = (
                f"cache for ({runtime}, {package}) still referenced by "
                f"source(s) {sibling_ids}; skipped"
            )

    # Step 4: DB delete (existing semantics).
    try:
        await repo.delete(source_id)
    except KeyError:
        # Race: someone deleted the row between our get() and delete().
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

    # Step 5: Best-effort cleanup post-delete. The helper has its own
    # 10s ceiling and swallows every exception — this await cannot
    # raise.
    #
    # Logs use WARNING (not INFO) so cleanup outcomes surface under
    # uvicorn's default root-logger threshold without operators
    # lowering the bar globally. WARNING is semantically loose here
    # ("operation succeeded normally") but it's the simplest visibility
    # fix; the alternative is structured response fields, which the
    # architect ruled out (silent UX).
    import logging

    _log = logging.getLogger(__name__)
    if not (runtime and package):
        # Unsupported runtime — nothing to reclaim.
        _log.warning(
            "delete_mcp_source(%s): no cleanup applicable for command %r",
            source_id,
            command,
        )
    elif skip_reason:
        # Refcount survivor — log and skip. The shared cache stays put
        # for the surviving source.
        _log.warning("delete_mcp_source(%s): %s", source_id, skip_reason)
    else:
        await cleanup_runtime_cache(runtime, package)

    return {"status": "ok"}


@router.delete("/mcp-sources/{source_id}/connection")
async def reset_mcp_connection(source_id: str) -> dict[str, str]:
    """Clear OAuth tokens + tools cache for a streamable-http MCP source.

    F9 L1 (vibing) — operator-facing affordance for "this connection is
    in a weird state, start over from a fresh login". Strips every key
    in ``OAUTH_MANAGED_SECRET_KEYS`` from ``source.secrets`` (access_token,
    refresh_token, token_expires_at, token_type, scope, dcr_credentials),
    drops ``source.config["_cache"]`` if present, evicts the F4 pool so
    the next acquire reconstructs a fresh client, and persists the result.
    Returns ``{"status": "ok"}`` on success.

    On the next /test/connect, since both ``access_token`` and
    ``dcr_credentials`` are gone, the endpoint skips Phase A and runs
    Phase B's full DCR + consent + token-exchange flow — a fresh
    OAuth session, not a silent token rotation.

    Idempotent: calling on a source that already lacks OAuth state and
    cache is a no-op (zero keys to strip; ``repo.update`` writes the
    unchanged shape; eviction is idempotent on no-match).

    Out-of-scope: stdio sources have no OAuth state; calling on a stdio
    source is harmless (zero keys match) but UI hides the affordance.
    """
    from the_one.mcp._pool import _evict_all_for_source

    repo = await _mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

    new_secrets = {k: v for k, v in source.secrets.items() if k not in _OAUTH_MANAGED_SECRET_KEYS}
    new_config = dict(source.config or {})
    new_config.pop("_cache", None)
    updated_source = source.model_copy(update={"secrets": new_secrets, "config": new_config})
    await _evict_all_for_source(source_id)
    await repo.update(updated_source)
    return {"status": "ok"}


async def _build_and_test_no_auth_mcp(
    source: MCPSource, source_id: str, repo: MCPSourceRepository
) -> dict[str, Any]:
    """Connect + list_tools against a no-auth streamable-http MCP source.

    F9 L1 Shape C helper: extracted so both Phase 0 success branches
    (probe-verdict no_auth AND cached-hint no_auth) share one code path.
    Mirrors the Phase A success branch's persistence shape — tools +
    capabilities + last_updated + auth_posture all land in
    ``source.config._cache``.

    NEVER engages Phase B from this helper: a no_auth verdict is
    definitive; if MCPClient still raises (transport down, capability
    missing, version mismatch), surface the error inline.

    Args:
        source: The (possibly body-overridden) MCPSource to test.
        source_id: The persisted source id used for cache writebacks.
        repo: The repo for cache persistence.

    Returns:
        ``{status: "ok", tools, capabilities}`` on success, or
        ``{status: "error", error}`` on any failure.
    """
    from the_one.mcp.client import MCPClient
    from the_one.mcp.errors import (
        MCPAuthRequired,
        MCPCapabilityMissing,
        MCPConnectionError,
        MCPVersionMismatch,
    )

    try:
        async with MCPClient(source=source, auth_provider=None) as client:
            tools = await client.list_tools()
            capabilities = client.server_capabilities
            tools_cache_payload = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
            try:
                persisted = await repo.get(source_id)
                persisted_config = dict(persisted.config or {})
                persisted_config["_cache"] = {
                    "tools": tools_cache_payload,
                    "capabilities": capabilities,
                    "last_updated": time.time(),
                    "auth_posture": "no_auth",
                }
                await repo.update(persisted.model_copy(update={"config": persisted_config}))
            except Exception:
                # Best-effort persistence — a write failure must not break the
                # response contract (mirrors the Phase A persistence pattern).
                pass
        return {
            "status": "ok",
            "tools": tools_cache_payload,
            "capabilities": capabilities,
        }
    except MCPAuthRequired as e:
        # Defensive: probe said no_auth but server now wants auth (race).
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except (MCPConnectionError, MCPVersionMismatch, MCPCapabilityMissing) as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except Exception as e:
        # F9 L2 vibing: defense-in-depth catch-all. Any exception escaping the
        # typed catches above (e.g. asyncio.CancelledError leaking from
        # MCPClient cleanup, or any other unexpected runtime error) is
        # converted to a 200-response error envelope rather than allowed to
        # escape the route as a 500 with HTML body. The frontend's resp.ok
        # check is a parallel guard; this ensures the JSON contract holds.
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


async def _build_and_test_stdio_mcp(
    source: MCPSource, source_id: str, repo: MCPSourceRepository
) -> dict[str, Any]:
    """Connect + list_tools against a stdio MCP source.

    F9 L2 D1 sibling of ``_build_and_test_no_auth_mcp``: stdio has no
    OAuth concept (no Phase 0 / Phase A / Phase B), so the Test path is
    structurally a single transient-client lifecycle. Mirrors the
    no-auth-http helper's persistence shape for tools + capabilities +
    last_updated. Does NOT write ``auth_posture`` — that field is an
    HTTP-path concept (Shape C) that does not generalize to stdio (no
    HTTP probe surface; "no auth" is the only stdio mode).

    The transient client teardown path runs through the F4/F6.6
    lifecycle that has been verified clean post-F6.6 cleanup-deadlock
    fix; caplog is expected to be free of ``MCPClient.disconnect``
    warnings across this path.

    Args:
        source: The (possibly body-overridden) MCPSource to test.
        source_id: The persisted source id used for cache writebacks.
        repo: The repo for cache persistence.

    Returns:
        ``{status: "ok", tools, capabilities}`` on success, or
        ``{status: "error", error}`` on any failure.
    """
    from the_one.mcp.client import MCPClient
    from the_one.mcp.errors import (
        MCPAuthRequired,
        MCPCapabilityMissing,
        MCPConnectionError,
        MCPSandboxError,
        MCPVersionMismatch,
    )

    try:
        async with MCPClient(source=source, auth_provider=None) as client:
            tools = await client.list_tools()
            capabilities = client.server_capabilities
            tools_cache_payload = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
            try:
                persisted = await repo.get(source_id)
                persisted_config = dict(persisted.config or {})
                persisted_config["_cache"] = {
                    "tools": tools_cache_payload,
                    "capabilities": capabilities,
                    "last_updated": time.time(),
                }
                await repo.update(persisted.model_copy(update={"config": persisted_config}))
            except Exception:
                # Best-effort persistence — a write failure must not break the
                # response contract (mirrors the http no-auth helper).
                pass
        return {
            "status": "ok",
            "tools": tools_cache_payload,
            "capabilities": capabilities,
        }
    except MCPAuthRequired as e:
        # Defensive: stdio shouldn't surface auth-required, but if a server
        # somehow does, surface it as a regular error rather than crashing.
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except (MCPConnectionError, MCPVersionMismatch, MCPCapabilityMissing, MCPSandboxError) as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    except Exception as e:
        # F9 L2 vibing: defense-in-depth catch-all. Stdio teardown can leak
        # asyncio.CancelledError from MCPClient._safe_cleanup under certain
        # failure modes (Architect is fixing that root cause separately).
        # Until then — and as a permanent guard against any other unexpected
        # runtime error — convert escaping exceptions into a 200-response
        # error envelope so the route's JSON contract holds and the frontend
        # can render a useful message instead of choking on an HTML 500.
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


@router.post("/mcp-sources/{source_id}/test/connect")
async def test_mcp_connection(source_id: str, request: Request) -> dict[str, Any]:
    """Connect + list_tools probe; kicks OAuth flow if needed via popup-callback dance.

    Behavior:
      - 404 if source not found
      - {status: "ok", tools: [...]} if connect + list_tools succeed
      - {status: "auth_required", consent_url} if creds absent or
        MCPAuthRequired raised; SDK's auth flow runs as a background
        task waiting for /oauth/callback to deliver the code
      - {status: "error", error} for other failures (transport, version
        mismatch, non-streamable-http source, consent_url_timeout)

    Two-call dance: UI POSTs once; on auth_required opens a popup, waits
    for popup close, re-POSTs. The second POST hits the {status: "ok"}
    path because tokens have landed via the SDK's callback_handler.

    F8 L4 — accepts an optional request body shaped like the PUT payload
    (`{type, config, secrets}`); if present, the operator's in-flight
    form values override the persisted source for the connection test.
    OAuth-managed secret keys (`access_token`, `dcr_credentials`, etc.)
    are ALWAYS sourced from the persisted DB row — only the OAuth flow
    writes them. `source_id` is preserved for OAuth callback routing
    and token persistence regardless of the override.

    F6.5 L3 — see flight artifact Design Decision §2 for the protocol.
    """
    from the_one.interfaces.web.app import _inflight_resume_tasks
    from the_one.mcp._pool import _evict_all_for_source
    from the_one.mcp.client import MCPClient
    from the_one.mcp.errors import MCPAuthRequired, MCPConnectionError, MCPVersionMismatch
    from the_one.mcp.oauth import build_oauth_provider_for_source

    repo = await _mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    # F8 L4: optionally override the persisted source with operator's
    # in-flight form values. Mirrors the PUT endpoint's secrets-resolution
    # logic (per-key __MASKED__ → existing; OAUTH-managed → always
    # preserved from existing). Body is optional — empty body preserves
    # the prior single-arg behavior verbatim.
    try:
        body_bytes = await request.body()
    except Exception:
        body_bytes = b""
    if body_bytes:
        try:
            payload = json.loads(body_bytes)
        except Exception as e:
            return {"status": "error", "error": f"invalid JSON body: {e}"}
        if not isinstance(payload, dict):
            return {"status": "error", "error": "request body must be a JSON object"}
        override_type = payload.get("type")
        override_config = payload.get("config")
        override_secrets = payload.get("secrets")
        if override_type and override_type != source.type:
            # Test against the operator's in-flight type. Build a
            # transient MCPSource shape; preserve id + name.
            source = MCPSource(
                id=source.id,
                name=source.name,
                type=override_type,
                config=override_config if isinstance(override_config, dict) else {},
                secrets=dict(source.secrets),
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
        elif isinstance(override_config, dict):
            source = source.model_copy(update={"config": override_config})
        if isinstance(override_secrets, dict):
            resolved_secrets: dict[str, Any] = {}
            for k, v in override_secrets.items():
                if v == _MASKED_API_KEY_SENTINEL:
                    if k in source.secrets:
                        resolved_secrets[k] = source.secrets[k]
                else:
                    resolved_secrets[k] = v
            # OAuth-managed keys ALWAYS come from the persisted row.
            for k in _OAUTH_MANAGED_SECRET_KEYS:
                if k in source.secrets:
                    resolved_secrets[k] = source.secrets[k]
                elif k in resolved_secrets:
                    del resolved_secrets[k]
            source = source.model_copy(update={"secrets": resolved_secrets})

    # F9 L2 D1: dispatch stdio sources to their dedicated transient-client
    # path. Stdio has no OAuth concept (no Phase 0 / Phase A / Phase B), so
    # the workflow is a straight connect → list_tools → cache → return.
    # Other unsupported transports continue to surface a clear error.
    if source.type == "stdio":
        return await _build_and_test_stdio_mcp(source, source_id, repo)
    if source.type != "streamable-http":
        return {
            "status": "error",
            "error": f"Test only supports streamable-http and stdio; got {source.type!r}",
        }

    # Phase 0: HTTP-level auth-posture probe (Shape C — A6 resolution).
    # Before engaging the SDK, ask the server itself: "do you require auth?"
    # Persisted result lives at source.config._cache.auth_posture so
    # subsequent calls skip the probe entirely.
    #
    # Skip the probe when live tokens are present — Phase A is the right
    # path for token-bearing OAuth sources (no extra round trip).
    from the_one.mcp.transports.streamable_http import _probe_auth_posture

    cached_posture = (source.config.get("_cache") or {}).get("auth_posture")
    has_live_tokens = bool(
        source.secrets.get("dcr_credentials") and source.secrets.get("access_token")
    )

    if cached_posture == "no_auth" and not has_live_tokens:
        return await _build_and_test_no_auth_mcp(source, source_id, repo)

    if cached_posture is None and not has_live_tokens:
        server_url = source.config.get("url", "")
        posture = await _probe_auth_posture(server_url)
        if posture == "no_auth":
            return await _build_and_test_no_auth_mcp(source, source_id, repo)
        if posture == "error":
            return {"status": "error", "error": "connection probe failed"}
        # posture == "oauth": persist the hint BEFORE Phase B fires so a
        # Phase B failure still leaves a definitive signal for the pool
        # worker (rather than inferring auth-required from dcr_credentials
        # presence). Then fall through to Phase B below.
        try:
            persisted = await repo.get(source_id)
            persisted_config = dict(persisted.config or {})
            persisted_cache = dict(persisted_config.get("_cache") or {})
            persisted_cache["auth_posture"] = "oauth"
            persisted_config["_cache"] = persisted_cache
            await repo.update(persisted.model_copy(update={"config": persisted_config}))
        except Exception:
            # Best-effort; falling through to Phase B regardless.
            pass

    # Phase A: tokens present → build provider WITH consent_url_future=None
    # (test path doesn't kick the OAuth flow yet) and try connect + list_tools.
    # MUST thread auth_provider through MCPClient or the SDK has no way to
    # apply the cached tokens — bare MCPClient sends Bearer-less requests
    # and always 401s, defeating the "tokens present" fast path.
    if source.secrets.get("dcr_credentials") and source.secrets.get("access_token"):
        provider_a = build_oauth_provider_for_source(
            source,
            repo,
            f"test:{source_id}",
            source_id=source_id,
            tool_call_id=None,
            resource_metadata_url=None,
            consent_url_future=None,  # Phase A doesn't kick a flow
        )
        try:
            async with MCPClient(source=source, auth_provider=provider_a) as client:
                tools = await client.list_tools()
                capabilities = client.server_capabilities  # F8 L1: snapshot inside async-with
                # F9 L1 (vibing): persist tools+capabilities to source.config._cache
                # so the editor can render the cached state on mount without
                # forcing the operator to click Refresh. Plaintext (un-encrypted)
                # — tools/capabilities/timestamp are not secrets and config is
                # the JSON-blob column already used for non-sensitive fields.
                # Write happens INSIDE the async-with after list_tools() succeeds
                # so a list_tools() failure does NOT pollute the cache; the
                # existing exception-translation contract handles failure paths
                # unchanged. We refetch the persisted source to avoid clobbering
                # any in-flight body-override config — the cache is keyed on
                # the persisted row, not the operator's transient form values.
                tools_cache_payload = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.input_schema,
                    }
                    for t in tools
                ]
                try:
                    persisted = await repo.get(source_id)
                    persisted_config = dict(persisted.config or {})
                    persisted_config["_cache"] = {
                        "tools": tools_cache_payload,
                        "capabilities": capabilities,
                        "last_updated": time.time(),
                    }
                    await repo.update(persisted.model_copy(update={"config": persisted_config}))
                except Exception:
                    # Best-effort persistence — a write failure must not
                    # break the test/connect response contract. The operator
                    # still gets the live tools list; cache simply won't
                    # populate for this round.
                    pass
            return {
                "status": "ok",
                "tools": tools_cache_payload,
                "capabilities": capabilities,
            }
        except MCPAuthRequired:
            # Token expired/revoked. Bust pool cache BEFORE Phase B builds
            # a fresh provider so the F4 cache doesn't hand out an MCPClient
            # with the stale auth_provider mid-refresh.
            await _evict_all_for_source(source_id)
            # fall through to Phase B
        except MCPConnectionError as e:
            # F8 L4 (Anomaly A6): Phase A's connect can hang/time out when
            # refresh_token is no longer accepted by the AS (refresh token
            # rotation, IdP invalidation, server-side revoke). The SDK's
            # auth flow doesn't reliably surface this as MCPAuthRequired —
            # it manifests as an initialize timeout. Treat as "tokens are
            # stale, kick a fresh OAuth flow" by clearing the stored OAuth
            # state and falling through to Phase B.
            #
            # IMPORTANT: only clear tokens when the error message matches
            # the initialize-timeout / cleanup-deadlock signature.
            # MCPConnectionError is also raised for transient network
            # failures (DNS NXDOMAIN, ECONNREFUSED, httpx transport
            # errors) — clearing tokens on those would destroy valid
            # OAuth sessions for an operator on a flaky link.
            err_msg = str(e).lower()
            looks_like_token_failure = (
                "did not respond" in err_msg or "cancelled during initialize" in err_msg
            )
            if looks_like_token_failure:
                try:
                    cleared = source.model_copy(
                        update={
                            "secrets": {
                                k: v
                                for k, v in source.secrets.items()
                                if k not in _OAUTH_MANAGED_SECRET_KEYS
                            }
                        }
                    )
                    await repo.update(cleared)
                    source = cleared
                except Exception:
                    pass
                await _evict_all_for_source(source_id)
                # fall through to Phase B
            else:
                return {"status": "error", "error": f"{type(e).__name__}: {e}"}
        except MCPVersionMismatch as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    # A6 (no-auth MCP detection) is now handled by Phase 0 above (Shape C):
    # bare httpx probe inspects auth posture before SDK engagement, persists
    # the verdict in _cache.auth_posture for subsequent calls. F8 deferred,
    # F9 L1 resolved.

    # Phase B: kick OAuth flow with consent_url_future. Pass
    # allow_dcr_bootstrap=True so the factory constructs a provider even
    # when dcr_credentials is absent — the SDK runs DCR + auth in one
    # round-trip via MCPSourceTokenStorage.get_client_info → None →
    # OAuthClientProvider's discovery + DCR fallback. This is the
    # source-creation-time happy path: operator saves a fresh source,
    # clicks Test, SDK does the registration + consent + token exchange.
    consent_url_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    test_csid = f"test:{source_id}"

    provider = build_oauth_provider_for_source(
        source,
        repo,
        test_csid,
        source_id=source_id,
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=consent_url_future,
        allow_dcr_bootstrap=True,
    )
    if provider is None:
        # With allow_dcr_bootstrap=True, the only way provider is None is
        # chat_session_id is None — but we passed a synthetic test_csid,
        # so this branch is unreachable. Defensive return.
        return {"status": "error", "error": "OAuth provider construction failed"}

    await _evict_all_for_source(source_id)

    server_url = source.config.get("url", "")

    async def _drive_flow_test() -> None:
        """Hit the source URL with the provider attached; SDK runs auth flow."""
        try:
            async with httpx.AsyncClient(auth=provider, timeout=30.0) as client:
                await client.post(
                    server_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "clientInfo": {"name": "the-one", "version": "0.1"},
                            "capabilities": {},
                        },
                    },
                )
        except Exception as exc:
            if not consent_url_future.done():
                consent_url_future.set_exception(
                    RuntimeError(f"auth flow failed before consent_url surfaced: {exc}")
                )

    task = asyncio.create_task(_drive_flow_test())
    _inflight_resume_tasks.add(task)
    task.add_done_callback(_inflight_resume_tasks.discard)

    try:
        consent_url = await asyncio.wait_for(
            asyncio.shield(consent_url_future), timeout=_TEST_CONNECT_TIMEOUT
        )
    except asyncio.TimeoutError:
        return {"status": "error", "error": "consent_url_timeout"}
    except Exception as e:
        return {"status": "error", "error": f"auth_flow_error: {e}"}

    return {"status": "auth_required", "consent_url": consent_url}


# ── OAuth callback (F5 §9) ────────────────────────────────────────────────


def _render_oauth_callback_page(
    *,
    status: str,
    heading: str,
    detail_html: str,
    auto_close: bool,
) -> str:
    """Render the loopback callback page in the studio visual idiom.

    The page is a self-contained HTML document served only to the popup
    window opened by the OAuth modal. It links the same studio CSS the
    SPA uses (``/static/css/...``) so the operator perceives continuity
    with the rest of GleepGlorp AI — violet-accent design system, Geist
    Sans / Geist Mono typography, ``//``-prefixed mono-uppercase eyebrow.

    Args:
        status: One of ``"success"``, ``"failed"``, ``"expired"``. Drives
            the eyebrow color (success uses ``--status-success``; the
            rest use ``--status-danger``).
        heading: The H1 text. The success path's heading must contain
            the verbatim contract substring "Login successful. You may
            close this tab." (F5 §4) so legacy stake tests keep matching.
        detail_html: Pre-escaped HTML inserted into the supporting
            paragraph. Callers MUST escape any user-controlled content
            (e.g. ``error_description``) before passing it in.
        auto_close: If True, schedule a ``window.close()`` ~1.2s after
            paint so the operator sees the success state but isn't left
            staring at a stale popup. Failure pages MUST pass False so
            the operator can read the error.

    The CSS is intentionally inlined for the page-specific layout
    (centered card, eyebrow, big heading, hint footer). Theme tokens,
    fonts, and the data-theme attribute come from the shared studio
    stylesheets so the page automatically follows the operator's
    dark/light/auto preference resolved by ``theme.js``.
    """
    eyebrow_color = "var(--status-success)" if status == "success" else "var(--status-danger)"
    auto_close_script = (
        "<script>setTimeout(function () { try { window.close(); } "
        "catch (e) { /* popup blocker / non-script-opened — ignore */ } }, "
        "1200);</script>"
        if auto_close
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{heading}</title>
<style>@layer tokens, base, components, areas, utilities;</style>
<script src="/static/js/theme.js"></script>
<link rel="stylesheet" href="/static/css/fonts.css">
<link rel="stylesheet" href="/static/css/tokens.css">
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; }}
  body {{
    font-family: var(--font-family-sans);
    background: var(--shell-bg);
    color: var(--fg);
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 24px;
    box-sizing: border-box;
  }}
  .oauth-callback-card {{
    max-width: 480px;
    width: 100%;
    padding: 32px 36px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--panel-radius);
    box-shadow: var(--panel-shadow);
    text-align: left;
  }}
  .oauth-callback-eyebrow {{
    font-family: var(--font-family-mono);
    font-size: var(--font-size-tiny);
    font-weight: var(--font-weight-bold);
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--fg-secondary);
    margin: 0 0 16px;
  }}
  .oauth-callback-eyebrow::before {{
    content: "//";
    padding-right: 0.4em;
    color: {eyebrow_color};
    font-weight: var(--font-weight-bold);
  }}
  .oauth-callback-heading {{
    font-family: var(--font-family-sans);
    font-size: var(--font-size-h1);
    font-weight: var(--font-weight-semibold);
    color: var(--fg);
    margin: 0 0 12px;
    line-height: var(--line-height-tight);
  }}
  .oauth-callback-detail {{
    font-size: var(--font-size-body);
    color: var(--fg-muted);
    line-height: var(--line-height-normal);
    margin: 0;
    word-break: break-word;
  }}
</style>
</head>
<body>
<main class="oauth-callback-card" role="status" aria-live="polite">
  <p class="oauth-callback-eyebrow">gleepglorp ai // oauth</p>
  <h1 class="oauth-callback-heading">{heading}</h1>
  <p class="oauth-callback-detail">{detail_html}</p>
</main>
{auto_close_script}
</body>
</html>
"""


@router.get("/oauth/callback")
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    """Loopback redirect target for the OAuth 2.1 + PKCE flow.

    The operator's IDP consent page redirects the browser tab to
    ``/api/oauth/callback?code=...&state=...`` (success) or
    ``?error=...&error_description=...&state=...`` (denial). This
    handler:

      1. Looks up the pending flow keyed by ``state``.
      2. On success, calls ``_state.resolve(state, code, state)`` to
         hand the code back to the SDK's ``callback_handler`` waiting
         inside the auth flow's yield boundary; broadcasts an
         ``auth_resolved`` event to the originating chat session.
      3. On error, calls ``_state.fail`` with an ``OAuthFlowError``;
         broadcasts an ``auth_failed`` event.
      4. Returns an HTML body for the operator's browser tab —
         ``"Login successful"`` / ``"Login failed"`` / ``"Login expired"``
         per the verbatim-message contract.

    Lazy imports of ``_sessions``, ``_send_to_session``, and
    ``_state`` avoid the api.py ↔ app.py circular at module-load time.

    Cycle-2 NEW-H2 race: between our ``peek`` and ``resolve``, the
    periodic TTL sweep may pop the entry and fail the future with a
    timeout error. ``resolve`` returns False in that case and we
    short-circuit to a "Login expired" response WITHOUT broadcasting
    ``auth_resolved`` — the chat UI must not see a successful-login
    event for a flow that actually failed.
    """
    # Lazy imports — see docstring.
    import html as _html

    from mcp.client.auth.exceptions import OAuthFlowError

    from the_one.interfaces.web.app import _send_to_session, _sessions
    from the_one.mcp.oauth import _state as oauth_state

    if state is None:
        raise HTTPException(status_code=401, detail="Missing state parameter")
    entry = oauth_state.peek(state)
    if entry is None:
        raise HTTPException(status_code=401, detail="Unknown or expired state")

    if error is not None:
        oauth_state.fail(state, OAuthFlowError(error_description or error))
        session = _sessions.get(entry.chat_session_id)
        if session is not None:
            await _send_to_session(
                session,
                {
                    "type": "auth_failed",
                    "source_id": entry.source_id,
                    "error": error,
                    "description": error_description,
                },
            )
        safe_desc = _html.escape(error_description or error)
        return HTMLResponse(
            _render_oauth_callback_page(
                status="failed",
                heading="Login failed",
                detail_html=safe_desc,
                auto_close=False,
            ),
            status_code=200,
        )

    # Cycle-2 NEW-H2: resolve returns False if the sweep raced between
    # our peek and resolve. Don't broadcast auth_resolved in that case.
    resolved = oauth_state.resolve(state, code or "", state)
    if not resolved:
        return HTMLResponse(
            _render_oauth_callback_page(
                status="expired",
                heading="Login expired",
                detail_html=(
                    "The login window has closed. Please re-trigger the original action to retry."
                ),
                auto_close=False,
            ),
            status_code=200,
        )
    session = _sessions.get(entry.chat_session_id)
    if session is not None:
        await _send_to_session(
            session,
            {
                "type": "auth_resolved",
                "source_id": entry.source_id,
                "tool_call_id": entry.tool_call_id,
            },
        )
        # F5 L3: schedule resume of the paused agent so the deferred
        # tool calls can re-dispatch with the freshly-issued tokens.
        # Guard with ``_deferred_tool_calls is not None`` (cycle-1 D13
        # race protection): the in-memory pause may already be cleared
        # by a previous resume that fired between the SDK's redirect
        # and this callback.
        from the_one.interfaces.web.app import (
            _inflight_resume_tasks,
            _resume_paused_session,
        )

        # ``session.agent`` is typed Agent but tests can construct
        # Sessions with ``agent=None`` (degraded fixtures); guard so
        # we don't AttributeError out of the success-path response.
        if session.agent is not None and session.agent._deferred_tool_calls is not None:
            resume_task = asyncio.create_task(_resume_paused_session(session))
            _inflight_resume_tasks.add(resume_task)
            resume_task.add_done_callback(_inflight_resume_tasks.discard)
    # Verbatim-message contract per F5 §4 — the substring
    # "Login successful. You may close this tab." must appear
    # contiguously so the L2 stake test matches. The popup also
    # auto-closes ~1.2s after paint via window.close() so the
    # operator gets visual confirmation but isn't left with a stale
    # tab. The auto-close is best-effort: if a browser blocks the
    # call (e.g. popup not script-opened), the heading still tells
    # the operator they may close manually.
    return HTMLResponse(
        _render_oauth_callback_page(
            status="success",
            heading="Login successful. You may close this tab.",
            detail_html=(
                "Tokens have been securely persisted. This window will close automatically."
            ),
            auto_close=True,
        ),
        status_code=200,
    )


@router.post("/oauth/start")
async def oauth_start(request: Request) -> dict[str, Any]:
    """Drive the OAuth 2.1 + PKCE flow for an MCP source until consent_url surfaces.

    Body: ``{source_id, chat_session_id, tool_call_id?, resource_metadata_url?}``.

    Behavior:
      - 404 if ``source_id`` does not exist.
      - 400 if ``source.secrets["dcr_credentials"]`` is absent (the AS must
        support DCR — surfaces a 400 if ``secrets['dcr_credentials']`` is absent).
      - Otherwise: build a provider via ``build_oauth_provider_for_source``,
        evict any cached F4 pool entries for this source (so the next tool
        call reconstructs ``MCPClient`` with the freshly-built provider),
        and schedule a background ``asyncio.Task`` that drives the SDK auth
        flow. The SDK's ``redirect_handler`` (constructed inside the factory)
        broadcasts a SECOND ``auth_required`` event to the chat session
        carrying the real ``consent_url``; the chat UI's modal handler picks
        it up and opens the consent window.

    Returns 202 with ``{"status": "started"}``. The actual auth-flow result
    (``auth_resolved`` / ``auth_failed``) reaches the chat UI via WebSocket.

    Architectural debt (carried to F6, see flight log A17): the pool eviction
    is required because the F4 warm cache hands out pre-provider ``MCPClient``
    instances. A cleaner design (F6) attaches the provider lazily inside
    the agent's tool dispatch path so pool entries don't need busting.
    """
    from the_one.interfaces.web.app import (
        _inflight_resume_tasks,
        _send_to_session,
        _sessions,
    )
    from the_one.mcp._pool import _evict_all_for_source
    from the_one.mcp.oauth import build_oauth_provider_for_source

    data = await request.json()
    source_id = data.get("source_id")
    chat_session_id = data.get("chat_session_id")
    tool_call_id = data.get("tool_call_id")
    resource_metadata_url = data.get("resource_metadata_url")
    if not source_id or not chat_session_id:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: source_id, chat_session_id",
        )

    repo = await _mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    if not source.secrets.get("dcr_credentials"):
        raise HTTPException(
            status_code=400,
            detail="DCR-supporting AS required; OAuth flow not available for this source",
        )

    provider = build_oauth_provider_for_source(
        source,
        repo,
        chat_session_id,
        source_id=source_id,
        tool_call_id=tool_call_id,
        resource_metadata_url=resource_metadata_url,
    )

    # Bust the F4 pool cache so the next ``acquire`` reconstructs MCPClient
    # with the now-populated dcr_credentials. See A17 in the flight log.
    await _evict_all_for_source(source_id)

    server_url = source.config.get("url")

    async def _drive_flow() -> None:
        """Hit the source URL with the provider attached; SDK runs auth flow."""
        try:
            async with httpx.AsyncClient(auth=provider, timeout=30.0) as client:
                # The ``initialize`` JSON-RPC request returns 401 when no
                # token is present; the provider's ``async_auth_flow``
                # intercepts, runs PRM/OASM/DCR/auth, and the
                # ``redirect_handler`` broadcasts ``auth_required`` with
                # the real ``consent_url``.
                await client.post(
                    server_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "clientInfo": {"name": "the-one", "version": "0.1"},
                            "capabilities": {},
                        },
                    },
                )
        except Exception as exc:
            # Best-effort: broadcast auth_failed so the chat UI clears the
            # modal / inline button. The SDK's own logging covers the
            # detailed traceback; we just signal the user.
            session = _sessions.get(chat_session_id)
            if session is not None:
                with contextlib.suppress(Exception):
                    await _send_to_session(
                        session,
                        {
                            "type": "auth_failed",
                            "source_id": source_id,
                            "error": "start_failed",
                            "description": str(exc),
                        },
                    )

    task = asyncio.create_task(_drive_flow())
    _inflight_resume_tasks.add(task)
    task.add_done_callback(_inflight_resume_tasks.discard)
    return {"status": "started", "source_id": source_id}


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


_MASKED_API_KEY_SENTINEL = "__MASKED__"

# Provider types that skip URL safety validation. ``mock`` has no real URL;
# ``ollama`` is local-by-design and operators frequently point it at
# ``http://host.docker.internal:11434`` or similar non-localhost hostnames
# that are nonetheless trusted.
_URL_VALIDATION_SKIPPED_TYPES = frozenset({"mock", "ollama"})


def _is_safe_provider_url(url: str) -> tuple[bool, str | None]:
    """Validate an LLM provider ``base_url``.

    Returns ``(True, None)`` for ``https://...`` always; for ``http://...``
    only when the host is one of ``localhost``/``127.0.0.1``/``::1`` or ends
    with ``.localdomain``. Any other scheme/host combination is rejected
    with a human-readable explanation suitable for ``HTTPException.detail``.

    Rationale: API keys for ``openai``/``anthropic``/``openai-compatible``
    are sent via the ``Authorization: Bearer ...`` header. Routing these
    over plaintext ``http://`` to a non-localhost host would leak the key
    on-wire to anything tapping the LAN. Refusing at save time is cheaper
    than detecting after exposure.
    """
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return True, None
    if parsed.scheme == "http":
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localdomain"):
            return True, None
        return (
            False,
            "Provider base_url uses http:// for a non-localhost host. "
            "API keys would be sent in cleartext. Use https:// or restrict to localhost.",
        )
    return (
        False,
        f"Provider base_url scheme '{parsed.scheme}' not supported. "
        "Use http:// (localhost only) or https://.",
    )


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
    return ollama_api.strip_v1(provider.base_url)


# ── LLM Providers ───────────────────────────────────────────────────────


@router.get("/providers")
async def list_providers() -> list[dict[str, Any]]:
    repo = await _provider_repo()
    providers = await repo.list()
    return [_provider_response(p) for p in providers]


@router.get("/providers/types")
async def list_provider_types() -> list[dict[str, str]]:
    """Return the list of provider types selectable in the UI.

    The ``mock`` type is included only when ``THE_ONE_DEV_MODE`` is on.

    NOTE: This route MUST be registered BEFORE ``/providers/{provider_id}``
    because FastAPI matches routes in registration order. If reordered, a
    GET to ``/providers/types`` would resolve to ``get_provider`` with
    ``provider_id="types"`` and 404.
    """
    types = [
        {"value": "ollama", "label": "Ollama"},
        {"value": "openai-compatible", "label": "OpenAI-Compatible"},
        {"value": "openai", "label": "OpenAI"},
        {"value": "anthropic", "label": "Anthropic"},
        {"value": "openrouter", "label": "OpenRouter"},
    ]
    if settings.dev_mode:
        types.append({"value": "mock", "label": "Mock (dev)"})
    return types


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
    if data.get("type") == "mock" and not settings.dev_mode:
        raise HTTPException(
            status_code=400,
            detail="Mock provider type requires THE_ONE_DEV_MODE=true",
        )
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    provider = LLMProviderConfig.model_validate(data)
    # URL safety: refuse non-https for non-localhost when the provider type
    # actually transmits an API key (skips ``mock`` / ``ollama``).
    if provider.type not in _URL_VALIDATION_SKIPPED_TYPES:
        ok, msg = _is_safe_provider_url(provider.base_url)
        if not ok:
            raise HTTPException(status_code=422, detail=msg)
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

    # Gate mock-typed updates on dev_mode. Compare the resulting type so an
    # update that doesn't change the type isn't accidentally rejected.
    incoming_type = data.get("type", existing.type)
    if incoming_type == "mock" and not settings.dev_mode:
        raise HTTPException(
            status_code=400,
            detail="Mock provider type requires THE_ONE_DEV_MODE=true",
        )

    # Detect masked API key and preserve existing stored key
    incoming_key = data.get("api_key")
    if incoming_key == _MASKED_API_KEY_SENTINEL:
        data["api_key"] = existing.api_key

    updated = existing.model_copy(update=data)
    # URL safety check on the RESOLVED base_url — i.e. after
    # ``model_copy(update=data)`` has merged any ``__MASKED__``-preserved
    # fields. This blocks the regression where a request that does not
    # touch ``base_url`` would otherwise let an unsafe stored value
    # survive an update.
    if updated.type not in _URL_VALIDATION_SKIPPED_TYPES:
        ok, msg = _is_safe_provider_url(updated.base_url)
        if not ok:
            raise HTTPException(status_code=422, detail=msg)
    await repo.update(updated)
    return _provider_response(updated)


@router.get("/providers/{provider_id}/agents")
async def list_provider_agents(provider_id: str) -> dict[str, list[str]]:
    """Return agent names that reference this provider."""
    repo = await _provider_repo()
    try:
        await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    store = await _agent_store()
    names = await store.list_by_provider(provider_id)
    return {"agents": names}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str) -> dict[str, str]:
    repo = await _provider_repo()
    try:
        await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    # Block deletion if agents reference this provider
    store = await _agent_store()
    agent_names = await store.list_by_provider(provider_id)
    if agent_names:
        raise HTTPException(
            status_code=409,
            detail=f"Provider is used by agents: {', '.join(agent_names)}",
        )

    await repo.delete(provider_id)
    return {"status": "ok"}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str) -> dict[str, Any]:
    repo = await _provider_repo()
    try:
        provider = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    # Belt-and-suspenders URL safety check: ``create_provider``/``update_provider``
    # already enforce this, but operators may have data loaded from a
    # pre-leg backup. Refuse to send the API key over an unsafe URL.
    if provider.type not in _URL_VALIDATION_SKIPPED_TYPES:
        ok, msg = _is_safe_provider_url(provider.base_url)
        if not ok:
            raise HTTPException(status_code=422, detail=msg)

    try:
        if provider.type == "mock":
            return {"status": "ok", "detail": "Mock provider (dev mode)"}
        elif provider.type == "ollama":
            base = ollama_api.strip_v1(provider.base_url)
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

            try:
                client = openai.AsyncOpenAI(api_key=provider.api_key)
                await client.models.list()
                return {"status": "ok", "detail": "Connected to OpenAI"}
            except openai.OpenAIError as e:
                return {"status": "error", "detail": str(e)}
        elif provider.type == "anthropic":
            import anthropic

            try:
                client = anthropic.AsyncAnthropic(api_key=provider.api_key)
                await client.models.list()
                return {"status": "ok", "detail": "Connected to Anthropic"}
            except anthropic.AnthropicError as e:
                return {"status": "error", "detail": str(e)}
        elif provider.type == "openrouter":
            from the_one.llm import openrouter_api

            # provider.api_key is already canonical-form (whitespace stripped,
            # empty → None) by the LLMProviderConfig field validator, so a
            # truthy check on the stored value is sufficient. No re-strip.
            key = provider.api_key
            try:
                if key:
                    await openrouter_api.verify_key(provider.base_url, key)
                    models = await openrouter_api.list_models(provider.base_url, key)
                    return {
                        "status": "ok",
                        "detail": f"Connected. Key valid; {len(models)} models available.",
                    }
                else:
                    models = await openrouter_api.list_models(provider.base_url, None)
                    # Reachable but non-functional for chat: status="warning"
                    # so the JS handler renders an amber chip + the
                    # explanatory text, not a green "Connection successful".
                    return {
                        "status": "warning",
                        "detail": (
                            f"Reachable. Add an API key to enable chat. "
                            f"{len(models)} models available."
                        ),
                    }
            except httpx.HTTPStatusError as e:
                body_text = (e.response.text or "")[:200].strip()
                return {
                    "status": "error",
                    "detail": f"HTTP {e.response.status_code}: {body_text}",
                }
            except httpx.RequestError as e:
                return {"status": "error", "detail": f"Network error: {e}"}
            except ValueError as e:
                # Shape contract violation from openrouter_api (malformed
                # /models payload). Distinct from network/HTTP — surface
                # explicitly so operators don't chase a non-existent
                # connectivity issue.
                return {
                    "status": "error",
                    "detail": f"OpenRouter API contract violation: {e}",
                }
        return {"status": "error", "detail": f"Unknown provider type: {provider.type}"}
    except httpx.HTTPError as e:
        # Expected: connection/timeout/HTTP-status from upstream
        return {"status": "error", "detail": str(e)}
    except HTTPException:
        # Pass through anything we explicitly raised so it isn't re-wrapped as 500
        raise
    except Exception as e:
        # Unexpected: surface as 500 so it's visible in logs, not a user-fixable issue
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers/{provider_id}/models")
async def list_provider_models(provider_id: str) -> list[dict[str, Any]]:
    repo = await _provider_repo()
    try:
        provider = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    if provider.type == "mock":
        models = provider.config.get("models", ["mock-default"])
        return [{"id": m, "name": m} for m in models]
    elif provider.type == "ollama":
        try:
            base = ollama_api.strip_v1(provider.base_url)
            models = await ollama_api.list_models(base)
            # Capabilities come from /api/show — cached per (base, model) so
            # repeat renders are free. Gather in parallel; on failure, return
            # `null` capabilities so the UI renders the row without chips
            # rather than failing the whole list.
            cap_tasks = [ollama_api.get_model_capabilities(base, m.get("name", "")) for m in models]
            caps_list = await asyncio.gather(*cap_tasks, return_exceptions=True)
            enriched = []
            for m, caps in zip(models, caps_list, strict=False):
                cap_array = sorted(caps) if isinstance(caps, frozenset | set) else None
                enriched.append(
                    {
                        "id": m.get("name", ""),
                        "name": m.get("name", ""),
                        "size": m.get("size"),
                        "capabilities": cap_array,
                    }
                )
            return enriched
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    elif provider.type == "openrouter":
        from the_one.llm import openrouter_api

        try:
            raw = await openrouter_api.list_models(provider.base_url, provider.api_key)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="OpenRouter timed out")
        except httpx.HTTPStatusError as e:
            # Mirror upstream status code + body excerpt; collapse 5xx → 502.
            upstream = e.response.status_code
            mapped = 502 if upstream >= 500 else upstream
            body_text = (e.response.text or "")[:200].strip()
            raise HTTPException(
                status_code=mapped,
                detail=f"OpenRouter HTTP {upstream}: {body_text}",
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"OpenRouter unreachable: {e}")
        except ValueError as e:
            # Shape contract violation — NOT unreachability. Distinct
            # status so operators don't chase a network problem that
            # isn't there.
            raise HTTPException(
                status_code=500,
                detail=f"OpenRouter API contract violation: {e}",
            )
        return [
            {
                "id": m.id,
                "name": m.name if m.name else m.id,
                "supported_parameters": m.supported_parameters or [],
                "context_length": m.context_length,
                "description": m.description,
                # alias for the Studio capability chip — frontend reads `capabilities`
                "capabilities": m.supported_parameters or [],
            }
            for m in raw
        ]
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
            return [{"id": m.id, "name": getattr(m, "display_name", m.id)} for m in response.data]
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


# ── Ollama Library Search ────────────────────────────────────────────────

_library_cache: dict[str, Any] = {"models": [], "timestamp": 0.0}

_LIBRARY_CACHE_TTL = 300  # seconds


@router.get("/ollama-library/search")
async def search_ollama_library(q: str = "") -> list[dict[str, str]]:
    """Return Ollama library models. Empty `q` lists the full cached library
    (alphabetical), used to populate the Pull Model dropdown. Non-empty `q`
    filters by substring."""
    q = q.strip().lower()

    now = time.time()
    if now - _library_cache["timestamp"] >= _LIBRARY_CACHE_TTL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://ollama.com/api/tags")
                resp.raise_for_status()
                data = resp.json()
            _library_cache["models"] = data.get("models", [])
            _library_cache["timestamp"] = now
        except Exception:
            if not _library_cache["models"]:
                return []

    results = []
    for m in _library_cache["models"]:
        name = m.get("name", "")
        if not q or q in name.lower():
            results.append({"name": name, "size": str(m.get("size", 0))})
    results.sort(key=lambda r: r["name"].lower())
    # Empty query: return the full library (capped at 500 — current Ollama
    # library is ~100 models, headroom for growth). Filtered query keeps
    # the legacy 30-item cap.
    return results[:500] if not q else results[:30]


# ── Encryption ───────────────────────────────────────────────────────────


@router.post("/encryption/rotate")
async def rotate_encryption_key() -> dict[str, str]:
    """Rotate the encryption key with crash-safe ordering.

    Re-encrypts every LLM provider row's ``api_key`` AND every MCP source
    row's ``secrets`` blob using a freshly generated key in memory and
    commits the DB transaction *before* the new key file replaces the old
    one via temp-file + ``os.replace``. Both surfaces commit atomically —
    a partial rotation that handled only one would leave the other
    encrypted under a key that no longer exists on disk. If the DB commit
    fails, the on-disk key file is left byte-identical to its pre-rotation
    contents so existing ciphertext on both surfaces remains decryptable.

    Migration-residue MCP rows (plaintext ``'{}'`` carried over from the
    v10 column default) are tolerated via InvalidToken-swallowing decrypt;
    they are normalized to proper ciphertext for ``{}`` as a side-effect.
    """
    encryptor = get_encryptor(settings.data_dir)
    if encryptor.key_path is None:
        raise HTTPException(status_code=500, detail="encryptor not file-backed")
    key_path = encryptor.key_path
    conn = await get_connection()

    # 1. Decrypt existing rows with the current encryptor. NOTE: Between this
    #    first SELECT and the final commit() below, this function MUST issue
    #    only DML statements (SELECT/UPDATE). Per the schema.py v8 docstring,
    #    aiosqlite silently COMMITs before any non-DML statement (PRAGMA,
    #    DDL, BEGIN), which would split the rotation into two separately-
    #    committed transactions and break the atomicity contract.
    async with conn.execute(
        "SELECT id, api_key FROM llm_providers WHERE api_key IS NOT NULL AND api_key != ''"
    ) as cur:
        rows = await cur.fetchall()
    decrypted = [(row["id"], encryptor.decrypt(row["api_key"])) for row in rows]

    async with conn.execute("SELECT id, secrets FROM mcp_sources") as cur:
        mcp_rows = await cur.fetchall()

    # Tolerant decrypt mirrors MCPSourceRepository._ciphertext_to_secrets at
    # repositories.py:258-280 — pre-L2-write rows or v10-migration-residue
    # rows carry the column default '{}' (plaintext) which Fernet rejects
    # with InvalidToken. Treat those as empty secrets and let rotation
    # incidentally normalize them to proper ciphertext for {}. JSON decode
    # errors are NOT swallowed — they indicate real corruption.
    decrypted_mcps: list[tuple[str, dict[str, Any]]] = []
    for row in mcp_rows:
        ciphertext = row["secrets"]
        if not ciphertext:
            secrets_dict: dict[str, Any] = {}
        else:
            try:
                plaintext = encryptor.decrypt(ciphertext)
                secrets_dict = json.loads(plaintext)
            except InvalidToken:
                secrets_dict = {}
        decrypted_mcps.append((row["id"], secrets_dict))

    # 2. Generate a new key + Encryptor in memory only (no disk writes yet).
    new_key = Fernet.generate_key()
    new_encryptor = Encryptor(new_key)

    # 3. Re-encrypt every row using the new encryptor.
    reencrypted = [(pid, new_encryptor.encrypt(pt)) for pid, pt in decrypted]
    reencrypted_mcps = [
        (sid, new_encryptor.encrypt(json.dumps(secrets_dict)))
        for sid, secrets_dict in decrypted_mcps
    ]

    # 4. Write all rows in a single transaction and commit. If anything in
    #    this block raises, roll the transaction back so the connection
    #    cache does not surface uncommitted ciphertext encrypted with the
    #    new (not-yet-on-disk) key. The key file is untouched at this
    #    point, so re-raising leaves the system fully recoverable. The
    #    single commit() covers BOTH tables — a failure in either UPDATE
    #    loop rolls back BOTH atomically.
    try:
        for pid, ct in reencrypted:
            await conn.execute(
                "UPDATE llm_providers SET api_key = ? WHERE id = ?",
                (ct, pid),
            )
        for sid, ct in reencrypted_mcps:
            await conn.execute(
                "UPDATE mcp_sources SET secrets = ? WHERE id = ?",
                (ct, sid),
            )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    # 5. Persist the new key to a temp file in the same directory as the
    #    canonical key path. Mode 0o600 is set at creation time via os.open
    #    (Path.write_bytes followed by chmod has a brief world-readable
    #    window).
    tmp_path = key_path.with_name(f"{key_path.name}.tmp.{secrets.token_hex(4)}")
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, new_key)
        os.fsync(fd)
    finally:
        os.close(fd)

    # 6. Atomic rename — after this point the new key is canonical on disk.
    os.replace(str(tmp_path), str(key_path))

    # 7. Update the cached encryptor so subsequent requests use the new key.
    encryptor.install_key(new_key)

    return {"status": "ok"}

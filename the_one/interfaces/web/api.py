"""REST API routes for agents, knowledge bases, MCP sources, and chat sessions."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import secrets
import time
import uuid
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from the_one import __version__
from the_one.api_credential import LocalApiCredential
from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.models import (
    ChatSession,
    Connector,
    KBItem,
    KnowledgeBase,
    LLMProviderConfig,
    MCPSource,
    now_iso,
)
from the_one.db.repositories import (
    AgentExternalCredentialRepository,
    AgentRevisionRepository,
    ChatSessionRepository,
    ConnectorRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    PendingApprovalRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
    _decrypt_overrides_column,
    _encrypt_overrides_column,
)
from the_one.encryption import Encryptor, get_encryptor
from the_one.llm import anthropic_oauth, ollama_api, plan_credentials
from the_one.mcp._overrides import MCP_OVERRIDE_CREDENTIAL_KEYS
from the_one.self_configuration import external_credentials as self_configuration_external
from the_one.self_configuration import manage as self_configuration_manage
from the_one.self_configuration.constants import EXTERNAL_CREDENTIAL_PREFIX

if TYPE_CHECKING:
    # `AgentConfig` is intentionally NOT imported at module load time —
    # every handler that needs it does a function-local import to avoid
    # a load-time cycle (see the lazy-import precedent throughout the
    # Agents section below). This TYPE_CHECKING-only import exists
    # purely so `_agent_response`'s parameter annotation resolves for
    # static analysis; it has zero runtime effect (never executes).
    from the_one.agent.config import AgentConfig

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)
"""Module-level logger.

M11 F9 L5 — added as a required side-effect of the leg. ``api.py``
previously lacked a module-level ``logger``; some functions defined
their own local ``_log`` (see :func:`delete_mcp_source` at the comment
block citing the uvicorn-root-logger-threshold precedent). The
module-level handle is the convention everywhere else in ``the_one/``;
new endpoints log through it directly.
"""


# ── Helpers ───────────────────────────────────────────────────────────────


async def _agent_store() -> SQLiteAgentStore:
    conn = await get_connection()
    # M21 F01 L01: pass the encryptor explicitly (rather than relying on
    # the constructor's default) so the api-module `get_encryptor` patch
    # test fixtures already install governs it — mirrors `_mcp_repo()` /
    # `_tool_config_repo()` above.
    return SQLiteAgentStore(conn, get_encryptor(settings.data_dir))


def _agent_response(cfg: AgentConfig) -> dict[str, Any]:
    """Render an ``AgentConfig`` into the masked HTTP response shape.

    Mirrors ``_mcp_source_response`` (below, in the MCP-sources section):
    ``model_dump()`` populates ``data["mcp_overrides"][<source>]`` with
    the decrypted plaintext credential values for the three
    ``MCP_OVERRIDE_CREDENTIAL_KEYS`` (``env``, ``headers``,
    ``bearer_token``); we OVERWRITE those specific keys with their masked
    form before returning. Any future refactor that removes the overwrite
    would leak plaintext via the API.

    INVARIANT: every other key — ``tool_overrides`` (no credential exists
    on any built-in tool Config today) and the non-credential
    ``mcp_overrides`` keys (``enabled_tools`` / ``disabled_tools``) — is
    returned byte-identical to what is stored. Only the marker-derived
    credential keys are masked.

    ``ALL agent-config HTTP responses MUST route through this helper —
    a bare ``cfg.model_dump()`` return leaks plaintext credential
    overrides. The regression net is an assertion on response *text*
    (mirrors ``test_list_returns_masked_secrets``).
    """
    data = cfg.model_dump()
    overrides = data.get("mcp_overrides")
    if overrides:
        for source_entry in overrides.values():
            if not isinstance(source_entry, dict):
                continue
            for key in MCP_OVERRIDE_CREDENTIAL_KEYS:
                if key not in source_entry or not source_entry[key]:
                    continue
                value = source_entry[key]
                if isinstance(value, str):
                    source_entry[key] = _mask_secret_value(value)
                elif isinstance(value, dict):
                    source_entry[key] = {k: _mask_secret_value(v) for k, v in value.items()}
                else:
                    source_entry[key] = _MASK_PREFIX
    return data


def _merge_preserved_mcp_credentials(
    incoming: dict[str, Any] | None,
    stored: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve an incoming ``mcp_overrides`` PUT payload against the
    stored row, per ``(source_name, credential_key)`` — AC5 / Design
    Decision DD5 / Decision D4.

    Studio never round-trips a credential (it rebuilds ``mcp_overrides``
    from the DOM, which renders no credential fields), so preserve
    CANNOT key off a sentinel the client sends — it must resolve against
    ``stored`` directly:

    - key omitted from the incoming source entry (or the whole source
      entry / whole payload omitted or ``None``) → keep the stored value.
    - key present and ``_looks_masked`` (a client round-tripping a masked
      GET response) → keep the stored value.
    - key present as an explicit ``None`` → clear it.
    - key present with any other value → overwrite.
    - masked value for a key with nothing stored → drop (never persist
      the mask string).

    For the two dict-valued credential keys (``headers``, ``env``), the
    same four rules apply per INNER key — an operator changing one
    header must not silently wipe the others (Edge Case: "partially
    masked dict").

    Non-credential keys (``enabled_tools`` / ``disabled_tools``) and
    entries whose incoming value is not a dict are left untouched — the
    caller's ``AgentConfig.model_validate`` still validates the merged
    result, so a malformed entry 422s exactly as it does today.

    Returns ``None`` (not ``{}``) when the merged result is empty, so the
    ``None``/``{}`` fidelity the round-trip tests pin is preserved when
    nothing was ultimately stored for any source.
    """
    incoming = incoming or {}
    stored = stored or {}
    merged: dict[str, Any] = {}
    all_sources = set(incoming) | set(stored)
    for source_name in all_sources:
        incoming_entry = incoming.get(source_name)
        stored_entry = stored.get(source_name) or {}
        if source_name not in incoming:
            # Source entirely omitted from the payload → keep stored as-is.
            if stored_entry:
                merged[source_name] = dict(stored_entry)
            continue
        if not isinstance(incoming_entry, dict):
            # Not a dict (e.g. explicit null for the whole source, or a
            # malformed value) — leave alone. `None` here also degrades
            # to "nothing incoming for this source", which correctly
            # preserves the stored non-credential keys via the branch
            # below only when incoming_entry is None; anything else is
            # validation's problem, not ours.
            if incoming_entry is None:
                if stored_entry:
                    merged[source_name] = dict(stored_entry)
                continue
            merged[source_name] = incoming_entry
            continue
        resolved_entry = dict(incoming_entry)
        for key in MCP_OVERRIDE_CREDENTIAL_KEYS:
            stored_value = stored_entry.get(key)
            if key not in incoming_entry:
                # Omitted (Studio's shape) → preserve stored.
                if stored_value is not None:
                    resolved_entry[key] = stored_value
                continue
            incoming_value = incoming_entry[key]
            if incoming_value is None:
                # Explicit null → clear.
                resolved_entry.pop(key, None)
                continue
            if isinstance(incoming_value, dict):
                # headers/env: per-inner-key resolution. `stored_value`
                # may be absent/non-dict (nothing stored for this key
                # yet) — treat as {} so a masked inner value with
                # nothing to resolve against is dropped, not persisted
                # literally.
                stored_inner = stored_value if isinstance(stored_value, dict) else {}
                resolved_inner: dict[str, Any] = {}
                for inner_key, inner_value in incoming_value.items():
                    if _looks_masked(inner_value):
                        if inner_key in stored_inner:
                            resolved_inner[inner_key] = stored_inner[inner_key]
                        # else: masked with nothing stored → drop.
                    else:
                        resolved_inner[inner_key] = inner_value
                resolved_entry[key] = resolved_inner
            elif _looks_masked(incoming_value):
                if stored_value is not None:
                    resolved_entry[key] = stored_value
                else:
                    # Masked, nothing stored → drop.
                    resolved_entry.pop(key, None)
            else:
                resolved_entry[key] = incoming_value
        if resolved_entry:
            merged[source_name] = resolved_entry
    return merged or None


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


async def _connector_repo() -> ConnectorRepository:
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    return ConnectorRepository(conn, encryptor)


async def _chat_repo() -> ChatSessionRepository:
    conn = await get_connection()
    return ChatSessionRepository(conn)


async def _pending_approval_repo() -> PendingApprovalRepository:
    conn = await get_connection()
    return PendingApprovalRepository(conn)


async def _agent_revisions_repo() -> AgentRevisionRepository:
    # M21 F02 L02: no encryptor — the revision log holds plaintext
    # description/system_prompt values (mirrors PendingApprovalRepository).
    conn = await get_connection()
    return AgentRevisionRepository(conn)


async def _agent_external_credentials_repo() -> AgentExternalCredentialRepository:
    # M21 F03 L01: encryptor-bearing — the external-credential secret is
    # Fernet-encrypted at rest (DD2), mirrors `_mcp_repo()`.
    conn = await get_connection()
    return AgentExternalCredentialRepository(conn, get_encryptor(settings.data_dir))


# ── Tool config helpers (F6 L1) ───────────────────────────────────────────

_TESTABLE_TOOLS = frozenset({"web_search", "fetch_url"})

# F6.5 L3: Test connection endpoint timeout (seconds). Bounds the await
# on consent_url_future so a slow / hanging SDK auth flow doesn't pin
# the request indefinitely. 15s is the Design Decision §2 ceiling;
# tests monkeypatch this to drive the timeout path quickly.
_TEST_CONNECT_TIMEOUT: float = 15.0


async def _tool_config_repo() -> ToolConfigRepository:
    conn = await get_connection()
    return ToolConfigRepository(conn, get_encryptor(settings.data_dir))


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
    """Client-visible configuration — dev mode flag, version, and the
    context-fullness overlay thresholds.

    Fetched once at boot by the JS client (app.js DOMContentLoaded
    handler) and cached on window.App.config. The dev_mode flag gates
    the dev-mode-only Design Language Admin category (Mission 08 F2).
    ``context_warn_pct`` / ``context_crit_pct`` (M16 F08 L05) are read by
    the chat telemetry overlay to color the bar and emit its non-color a11y
    signal; the settings validator guarantees they are always sane here.
    """
    return {
        "dev_mode": settings.dev_mode,
        "version": __version__,
        "context_warn_pct": settings.context_warn_pct,
        "context_crit_pct": settings.context_crit_pct,
    }


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
        # Merge the decrypted secrets over config, then mask the secret-
        # marked fields so the operator sees a stable masked value rather
        # than a raw key (and never the plaintext). Non-secret fields are
        # returned verbatim. M16 F08 L03.
        config = {**row.config, **row.secrets}
    except KeyError:
        enabled = True
        config = {}
    for field in _secret_field_names(cls.Config):
        if field in config:
            config[field] = _mask_secret_value(config[field])
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
        current_secrets = existing.secrets
    except KeyError:
        current_enabled = True
        current_config = {}
        current_secrets = {}

    secret_fields = _secret_field_names(cls.Config)

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
        dumped = validated.model_dump()
        # M16 F08 L03: SPLIT secret-marked fields OUT of the config column
        # into the encrypted `secrets` store — a plaintext key must never
        # land in `config`. For each secret whose incoming value looks
        # masked (the GET-response mask or the __MASKED__ sentinel),
        # PRESERVE the existing decrypted secret instead of overwriting
        # with the mask; a masked value with no existing secret is dropped
        # (treated as cleared), never stored as the mask string. A real
        # new value replaces it.
        new_config = {k: v for k, v in dumped.items() if k not in secret_fields}
        new_secrets: dict[str, Any] = {}
        for field in secret_fields:
            value = dumped.get(field)
            if _looks_masked(value):
                if field in current_secrets:
                    new_secrets[field] = current_secrets[field]
                # else: masked value with no existing secret → drop (cleared).
            elif value:
                new_secrets[field] = value
            # else: empty/falsy non-secret → drop (cleared), matches the
            # Config default of "".
    else:
        # `config` omitted — preserve both the existing config and secrets.
        new_config = current_config
        new_secrets = dict(current_secrets)

    await repo.upsert(name, new_config, secrets=new_secrets, enabled=new_enabled)

    # Build the masked response (same shape the GET handler returns):
    # non-secret config verbatim + secret fields masked.
    response_config = {**new_config, **new_secrets}
    for field in secret_fields:
        if field in response_config:
            response_config[field] = _mask_secret_value(response_config[field])
    return {
        "name": name,
        "description": cls.description,
        "enabled": new_enabled,
        "config": response_config,
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
    # M16 F08 L03: feed merged_config() (decrypted secrets folded over
    # config) so a keyed-engine "Test connection" (e.g. Brave / Tavily)
    # exercises the REAL api_key — same resolved view the factory builds.
    saved = {c.name: c.merged_config() for c in await repo.list()}
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
        agents.append(_agent_response(cfg))
    return agents


@router.get("/agents/{name}")
async def get_agent(name: str) -> dict[str, Any]:
    store = await _agent_store()
    try:
        cfg = await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return _agent_response(cfg)


@router.get("/agents/{name}/context-window")
async def get_agent_context_window(name: str) -> dict[str, int]:
    """F7 L04 (eager-resolve): return the agent's resolved
    ``max_context_tokens`` before the first user message.

    Closes the F6.5 HAT observation that the telemetry overlay's ``max:``
    value reads 0 before the first usage event fires. The frontend
    ``session_joined`` handler fetches this endpoint immediately after
    chrome is shown and seeds the overlay.

    Constructs the full Agent via ``AgentFactory.create()`` (the only
    path that wires up the LLM provider with credentials + config),
    then runs the L01-landed lazy resolver
    ``_resolve_max_context_tokens_if_needed`` which makes the per-
    provider metadata call (no LLM tokens consumed — Ollama/OpenRouter
    fetch ``/api/show`` or ``/models``; OpenAI/Anthropic use a hand-
    maintained prefix table). Provider failures fall back to the class
    default rather than raising (lazy resolver swallows + caches the
    sentinel) so the endpoint returns a usable value even when the
    provider's metadata API is down.

    Error mapping:
    - 404 if the agent name doesn't exist (``KeyError`` /
      ``AgentNotFoundError`` from ``_load_config``)
    - 400 if the agent has no provider configured
      (``ProviderNotConfiguredError``) or the provider config has been
      deleted (``ProviderNotFoundError``)
    """
    # Lazy imports: AgentFactory pulls in the full agent/LLM dependency
    # graph (tools, MCP, encryption). Keeping the import inside the
    # handler matches the existing pattern in this module (see e.g.
    # ``rename_agent`` lazy-imports AgentConfig).
    from the_one.agent.factory import (
        AgentFactory,
        ProviderNotConfiguredError,
        ProviderNotFoundError,
    )

    # Must wire the SQLiteAgentStore (matches the live app's startup-time
    # factory construction in ``app.py:_state["factory"]``); the default
    # ``AgentFactory()`` ctor leaves ``store=None`` which 404s every named
    # agent because the ``_load_config`` fallback only resolves "default".
    store = await _agent_store()
    factory = AgentFactory(store=store)
    try:
        agent = await factory.create(name)
    except ProviderNotFoundError as exc:
        # NOTE: must precede the bare-KeyError clause because
        # ``ProviderNotFoundError`` subclasses ``KeyError`` (factory.py:150).
        # Without this ordering, the dangling-provider case would 404
        # ("agent not found") which misleads the operator — the agent
        # exists but its provider config has been deleted.
        raise HTTPException(status_code=400, detail=str(exc))
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError:
        # Covers both ``AgentNotFoundError`` (subclasses KeyError) and
        # bare ``KeyError`` for completeness.
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")

    # Lazy resolver runs the per-provider metadata fetch (idempotent —
    # short-circuits on subsequent calls via the sentinel attribute). On
    # provider-side failure, the resolver swallows + leaves the class
    # default in place, so this endpoint always returns a usable value.
    await agent.llm._resolve_max_context_tokens_if_needed()
    return {"max_context_tokens": agent.llm.max_context_tokens}


@router.post("/agents", status_code=201)
async def create_agent(request: Request) -> dict[str, Any]:
    """Create a new agent.

    No stored row exists yet, so there is nothing to preserve — but a
    client sending a masked ``mcp_overrides`` credential value (e.g.
    round-tripping a GET response into a POST body) must not have that
    literal mask string persisted as the "secret". ``_merge_preserved_mcp_credentials``
    with ``stored=None`` drops any mask-shaped credential value while
    leaving real values and non-credential keys untouched.
    """
    from the_one.agent.config import AgentConfig

    data = await request.json()
    incoming_overrides = data.get("mcp_overrides")
    if incoming_overrides is None or isinstance(incoming_overrides, dict):
        # No stored row to preserve against (`stored=None`) — this drops
        # any mask-shaped credential value rather than persisting the
        # literal mask string; real values and non-credential keys pass
        # through unchanged.
        data["mcp_overrides"] = _merge_preserved_mcp_credentials(incoming_overrides, None)
    # else: not a dict and not null (e.g. a list) — leave alone;
    # AgentConfig validation below 422s it as today.
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    # M21 F01 L02 (LD1 ownership guard + Edge Case credential-override
    # guard): run on the VALIDATED config, after the mcp_overrides merge
    # above — an agent can never attach another agent's self-configuration
    # surface row, and an override targeting a surface row can never carry
    # a credential key.
    mcp_repo = await _mcp_repo()
    guard_error = await self_configuration_manage.reject_foreign_surface_attachments(
        cfg, mcp_repo=mcp_repo
    )
    if guard_error is not None:
        raise HTTPException(status_code=422, detail=guard_error)
    override_error = await self_configuration_manage.reject_surface_credential_overrides(
        cfg, mcp_repo=mcp_repo
    )
    if override_error is not None:
        raise HTTPException(status_code=422, detail=override_error)
    store = await _agent_store()
    await store.save(cfg)
    return _agent_response(cfg)


@router.put("/agents/{name}")
async def update_agent(name: str, request: Request) -> dict[str, Any]:
    """Update an existing agent.

    Server-side credential preserve (AC5 / DD5 / Decision D4): Studio
    rebuilds ``mcp_overrides`` from the DOM and renders no credential
    fields at all, so any credential set via the API would otherwise be
    silently wiped by the next Studio save. ``_merge_preserved_mcp_credentials``
    resolves the incoming payload against ``existing.mcp_overrides`` per
    ``(source, credential key)`` before validation — omitted/masked keys
    keep the stored value, explicit ``null`` clears, anything else
    overwrites. Incoming ``mcp_overrides: null`` degrades to "nothing
    incoming", which preserves every stored source (the same rule that
    applies to a single omitted key, generalized to the whole field).
    """
    from the_one.agent.config import AgentConfig

    store = await _agent_store()
    try:
        existing = await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    data = await request.json()
    data["name"] = name  # Ensure name matches path
    incoming_overrides = data.get("mcp_overrides")
    if incoming_overrides is None or isinstance(incoming_overrides, dict):
        # `data.get(...)` cannot distinguish "key omitted" from "key
        # explicitly null" — both decode to `None`, and AC5 treats them
        # identically (both preserve every stored source), so that
        # collapse is intentional, not a gap.
        data["mcp_overrides"] = _merge_preserved_mcp_credentials(
            incoming_overrides, existing.mcp_overrides
        )
    # else: not a dict and not null (e.g. a list) — leave alone;
    # AgentConfig validation below 422s it as today.
    # M21 F02 L02 DD2 (HIGH): approval mode is operator-owned and set by a
    # dedicated immediate-post control, NOT by the Studio agent-save form —
    # which rebuilds its payload from the DOM and never sends this field. If
    # the PUT omits it we must preserve the stored value, or every unrelated
    # Save silently resets approval mode to False. Mirrors the mcp_overrides
    # preserve just above.
    if "self_revision_requires_approval" not in data:
        data["self_revision_requires_approval"] = existing.self_revision_requires_approval
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    # M21 F01 L02: ownership + credential-override guards, on the validated
    # config, after the preserve-on-PUT merge above (see create_agent for
    # the shared rationale).
    mcp_repo = await _mcp_repo()
    guard_error = await self_configuration_manage.reject_foreign_surface_attachments(
        cfg, mcp_repo=mcp_repo
    )
    if guard_error is not None:
        raise HTTPException(status_code=422, detail=guard_error)
    override_error = await self_configuration_manage.reject_surface_credential_overrides(
        cfg, mcp_repo=mcp_repo
    )
    if override_error is not None:
        raise HTTPException(status_code=422, detail=override_error)
    await store.save(cfg)
    return _agent_response(cfg)


@router.delete("/agents/{name}")
async def delete_agent(name: str) -> dict[str, str]:
    store = await _agent_store()
    try:
        await store.delete(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    # M21 F01 L02 (AC11): cascade — remove the agent's surface row (if any)
    # and unregister its credential. No-op if the agent never enabled the
    # surface.
    mcp_repo = await _mcp_repo()
    await self_configuration_manage.cascade_delete(name, mcp_repo=mcp_repo)
    return {"status": "ok"}


@router.delete("/agents/{agent_name}/connectors/{account_id}")
async def detach_agent_from_connector(
    agent_name: str,
    account_id: str,
) -> dict[str, Any]:
    """Detach a connector account from an agent.

    M11 F9 L5 — operator-driven detach. Removes ``account_id`` from
    ``agents.connector_ids`` (idempotent — missing entry is a
    no-op), then releases the per-(agent, account) pool slot.

    Returns the agent's updated config JSON (same shape as PUT). 404
    only on unknown agent; missing account_id is a 200 no-op (the
    post-state is the same: account_id is not in the agent's list).

    URL lives on the agent resource path even though the UI for triggering
    the detach lives on the connector account detail page — the
    source-of-truth is the agent-side ``connector_ids`` field per
    Design Decision §3 of M11 F9.
    """
    # Function-local import — :func:`release_agent_on_account` lives in
    # ``the_one.connectors._pool``, which transitively cycles through
    # ``the_one.db.repositories`` at module load. See
    # ``function-local-import-to-break-load-cycle`` in agents.md.
    from the_one.connectors._pool import release_agent_on_account

    store = await _agent_store()
    try:
        cfg = await store.load(agent_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}")

    if account_id in cfg.connector_ids:
        new_ids = [a for a in cfg.connector_ids if a != account_id]
        # ``model_copy(update=...)`` returns a validated ``AgentConfig`` —
        # no ``model_validate(model_dump())`` round-trip needed. The PUT
        # endpoint's ``model_validate`` is for untrusted client JSON;
        # here the input is already a model.
        cfg = cfg.model_copy(update={"connector_ids": new_ids})
        await store.save(cfg)
        # WARNING (not INFO) so the audit-log line surfaces under
        # uvicorn's default root-logger threshold — mirrors the precedent
        # block above :func:`delete_mcp_source` (and the F9 L3
        # peer-approval endpoints).
        logger.warning(
            "detach_agent_from_connector: removed %s from %s.connector_ids",
            account_id,
            agent_name,
        )

    # Always attempt pool release — idempotent on missing key. Releases
    # ONLY the per-(agent, account) slot; an ``account_acquire`` slot
    # under the sentinel for the same account_id stays (other agents may
    # still depend on it).
    await release_agent_on_account(agent_name, account_id)

    return _agent_response(cfg)


@router.post("/agents/{name}/rename")
async def rename_agent(name: str, request: Request) -> dict[str, Any]:
    """Rename an existing agent.

    The agent name is the primary key in the ``agents`` table and is
    referenced (without FK constraint, since schema v5) by
    ``chat_sessions.agent_name``. :meth:`SQLiteAgentStore.rename` handles
    both rows in a single transaction; this handler maps the store's
    exceptions to HTTP status codes.

    Validation reuses :class:`AgentConfig`'s pydantic rules by loading
    the existing agent, swapping its ``name`` field, and re-validating —
    that way any future name constraints (length, charset, etc.) added
    to ``AgentConfig`` apply here automatically without duplicating
    rules at this surface.
    """
    from the_one.agent.config import AgentConfig

    data = await request.json()
    new_name = (data.get("new_name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="new_name is required")
    if new_name == name:
        raise HTTPException(status_code=422, detail="new_name must differ from current name")
    store = await _agent_store()
    # Load existing agent first so AgentConfig validation runs against
    # the full payload (some fields may be required by Pydantic). If the
    # source doesn't exist, surface 404 here rather than waiting for
    # rename() to raise.
    try:
        existing = await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    # Validate the new name against AgentConfig — swap the name field on
    # a model_dump of the existing config so all other fields are present.
    payload = existing.model_dump()
    payload["name"] = new_name
    try:
        AgentConfig.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    try:
        await store.rename(name, new_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    except ValueError:
        raise HTTPException(status_code=409, detail=f"Agent already exists: {new_name}")
    # M21 F01 L02 (AC11): cascade the rename onto the agent's surface row
    # (if any) — updates its ownership marker and derived name. The row's
    # id (and therefore the credential registry, keyed on source id) is
    # unaffected.
    mcp_repo = await _mcp_repo()
    await self_configuration_manage.cascade_rename(name, new_name, mcp_repo=mcp_repo)
    cfg = await store.load(new_name)
    return _agent_response(cfg)


# ── Self-configuration surface (M21 F01 L02) ───────────────────────────────


@router.get("/agents/{name}/self-configuration")
async def get_agent_self_configuration(name: str) -> dict[str, Any]:
    """AC1: ``{"enabled": false}`` for an agent with no surface row (the
    default for every existing and newly-created agent); ``{"enabled":
    true, "source_id": ...}`` once enabled. 404 for an unknown agent name.
    """
    store = await _agent_store()
    try:
        await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    mcp_repo = await _mcp_repo()
    return await self_configuration_manage.status(name, agent_store=store, mcp_repo=mcp_repo)


@router.post("/agents/{name}/self-configuration")
async def enable_agent_self_configuration(name: str) -> dict[str, Any]:
    """AC2: mint (or reuse) a per-agent credential, create/update the
    ``streamable-http`` surface row, attach it to the agent, and register
    the credential. Idempotent — a second POST returns the same row with no
    second credential minted. The minted credential is NEVER returned here
    (it lives only in the row's encrypted ``secrets``, masked in every
    response like any other MCP source secret).
    """
    store = await _agent_store()
    mcp_repo = await _mcp_repo()
    try:
        await self_configuration_manage.enable(name, agent_store=store, mcp_repo=mcp_repo)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return await self_configuration_manage.status(name, agent_store=store, mcp_repo=mcp_repo)


@router.delete("/agents/{name}/self-configuration")
async def disable_agent_self_configuration(name: str) -> dict[str, str]:
    """Full disable (mirrors DELETE on a marked ``/mcp-sources/{id}`` row):
    evicts the pool, detaches the row from the agent, deletes it, and
    unregisters the credential. Idempotent no-op when already disabled.
    """
    store = await _agent_store()
    try:
        await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    mcp_repo = await _mcp_repo()
    # M21 F02 L02 DD8: thread the revision repo so disable marks every
    # outstanding pending revision superseded (a revision proposed under a
    # since-revoked surface must not be approvable afterward).
    revisions_repo = await _agent_revisions_repo()
    await self_configuration_manage.disable(
        name, agent_store=store, mcp_repo=mcp_repo, revisions_repo=revisions_repo
    )
    return {"status": "ok"}


# ── External-client credentials (M21 F03 L01) ──────────────────────────────


class _ExternalCredentialMintBody(BaseModel):
    label: str


async def _enabled_surface_id_or_409(name: str) -> str:
    """Return the agent's ATTACHED surface row id, or raise. 404 when the
    agent is unknown; 409 when the surface is not enabled — which, per
    review Issue #1, covers BOTH *no surface row* AND an ORPHANED
    (detached-but-present) row. Gate on ``status()['enabled']``, NOT on
    ``find_surface_row is not None`` — a dormant credential must never be
    minted against a detached surface that would silently start working on
    re-attach."""
    store = await _agent_store()
    try:
        await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    mcp_repo = await _mcp_repo()
    st = await self_configuration_manage.status(name, agent_store=store, mcp_repo=mcp_repo)
    if not st.get("enabled"):
        raise HTTPException(
            status_code=409,
            detail=(
                "self-configuration is not enabled for this agent; "
                "enable it before minting an external credential"
            ),
        )
    return st["source_id"]


@router.post("/agents/{name}/self-configuration/external-credentials")
async def mint_external_credential(name: str, body: _ExternalCredentialMintBody) -> dict[str, Any]:
    """DD1/DD2/DD7: mint a distinct external-client credential scoped to
    this agent's surface. Returns ``{identifier, label, token, url}`` — the
    ``ext_<id>.<secret>`` token exactly ONCE (no read path returns it
    again). 404 for an unknown agent, 409 when the surface is not enabled
    (no-row or orphaned)."""
    source_id = await _enabled_surface_id_or_409(name)
    repo = await _agent_external_credentials_repo()
    credential = LocalApiCredential.generate()
    await repo.create(
        source_id=source_id,
        label=body.label,
        identifier=credential.identifier,
        secret=credential.secret,
    )
    self_configuration_external.register(source_id, credential)
    return {
        "identifier": credential.identifier,
        "label": body.label,
        "token": credential.encode(prefix=EXTERNAL_CREDENTIAL_PREFIX),
        "url": self_configuration_manage.surface_url(),
    }


@router.get("/agents/{name}/self-configuration/external-credentials")
async def list_external_credentials(name: str) -> list[dict[str, Any]]:
    """DD2: secret-free projection of this agent's external credentials
    (``{identifier, label, created_at}``). Empty when the surface has been
    disabled (the FK cascade removed the rows); non-empty for an orphaned
    (detached-but-present) surface, whose rows are still live. 404 for an
    unknown agent."""
    store = await _agent_store()
    try:
        await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    mcp_repo = await _mcp_repo()
    row = await self_configuration_manage.find_surface_row(mcp_repo, name)
    if row is None:
        return []
    repo = await _agent_external_credentials_repo()
    return await repo.list_for_source(row.id)


async def _external_credential_of_agent_or_404(name: str, identifier: str) -> dict[str, Any]:
    """Resolve *identifier* and enforce the cross-ID guard: its ``source_id``
    must equal *name*'s surface row id, else 404 (never a cross-agent
    mutation). Uses ``find_surface_row`` (regardless of attached) so an
    orphaned surface's credentials remain revocable."""
    store = await _agent_store()
    try:
        await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    mcp_repo = await _mcp_repo()
    row = await self_configuration_manage.find_surface_row(mcp_repo, name)
    repo = await _agent_external_credentials_repo()
    cred = await repo.get(identifier)
    if cred is None or row is None or cred["source_id"] != row.id:
        raise HTTPException(
            status_code=404,
            detail=f"External credential {identifier!r} not found for agent {name!r}",
        )
    return cred


@router.delete("/agents/{name}/self-configuration/external-credentials/{identifier}")
async def revoke_external_credential(name: str, identifier: str) -> dict[str, str]:
    """DD7: hard-revoke one external credential — DELETE the row and evict
    its registry entry, so the next request bearing that token is 401 with
    no restart. 404 when *identifier* is not a credential of *name*'s
    surface (cross-ID guard). Never touches the agent's own ``agt``
    credential or another external credential."""
    await _external_credential_of_agent_or_404(name, identifier)
    repo = await _agent_external_credentials_repo()
    await repo.delete(identifier)
    self_configuration_external.unregister_identifier(identifier)
    return {"status": "ok"}


@router.post("/agents/{name}/self-configuration/external-credentials/{identifier}/rotate")
async def rotate_external_credential(name: str, identifier: str) -> dict[str, Any]:
    """DD7: revoke the old credential and mint a fresh one for the same
    label/agent, returning the new ``{identifier, label, token, url}`` once.
    The old token stops working immediately (401). 404 when *identifier* is
    not a credential of *name*'s surface; 409 when the surface is not
    enabled (rotate reissues a live credential, so it gates on enabled just
    as mint does)."""
    cred = await _external_credential_of_agent_or_404(name, identifier)
    source_id = await _enabled_surface_id_or_409(name)
    label = cred["label"]
    repo = await _agent_external_credentials_repo()
    await repo.delete(identifier)
    self_configuration_external.unregister_identifier(identifier)
    new_credential = LocalApiCredential.generate()
    await repo.create(
        source_id=source_id,
        label=label,
        identifier=new_credential.identifier,
        secret=new_credential.secret,
    )
    self_configuration_external.register(source_id, new_credential)
    return {
        "identifier": new_credential.identifier,
        "label": label,
        "token": new_credential.encode(prefix=EXTERNAL_CREDENTIAL_PREFIX),
        "url": self_configuration_manage.surface_url(),
    }


# ── Self-configuration approval mode + revision queue (M21 F02 L02) ────────


class _ApprovalModeBody(BaseModel):
    requires_approval: bool


async def _load_agent_or_404(name: str) -> tuple[SQLiteAgentStore, "AgentConfig"]:
    store = await _agent_store()
    try:
        config = await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return store, config


@router.put("/agents/{name}/self-configuration/approval-mode")
async def set_agent_approval_mode(name: str, body: _ApprovalModeBody) -> dict[str, Any]:
    """AC8/AC13 — set the per-agent approval-mode flag via a TARGETED UPDATE.

    The immediate-post toggle touches ONLY this operator-owned scalar, so a
    targeted ``UPDATE agents SET self_revision_requires_approval=?`` dodges
    the whole-row last-writer-wins window a full ``save`` would open (safe
    here, unlike the DD4 approve path which must re-load to avoid clobbering
    the revision target). Settable regardless of whether the surface is
    currently enabled — the flag is independent of the surface row; it only
    *bites* once the agent can propose, so pre-setting is harmless.
    """
    store = await _agent_store()
    try:
        await store.set_self_revision_requires_approval(name, body.requires_approval)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return {"requires_approval": body.requires_approval}


@router.get("/agents/{name}/self-configuration/revisions")
async def list_agent_revisions(name: str) -> list[dict[str, Any]]:
    """AC8 — an agent's revisions newest-first (full non-secret rows).

    ``base_value`` / ``proposed_value`` are the plaintext description /
    system_prompt values, safe to return — the operator needs the
    before/after to decide. Name-scoped query + the cross-ID 404 guard on
    the action endpoints enforce DD6's "never another agent's data".
    """
    await _load_agent_or_404(name)
    revisions_repo = await _agent_revisions_repo()
    rows = await revisions_repo.list_for_agent(name)
    return [r.model_dump() for r in rows]


@router.get("/agents/{name}/self-configuration/revisions/pending-count")
async def get_agent_pending_revision_count(name: str) -> dict[str, int]:
    """AC8 — the count of ``pending`` revisions scoped to this agent."""
    await _load_agent_or_404(name)
    revisions_repo = await _agent_revisions_repo()
    return {"count": await revisions_repo.count_pending(name)}


@router.post("/agents/{name}/self-configuration/revisions/{revision_id}/dismiss")
async def dismiss_agent_revision(name: str, revision_id: str) -> dict[str, Any]:
    """AC9 — transition a ``pending`` revision to ``dismissed``.

    Idempotent on an already-dismissed row; 409 on applied/superseded; 404
    on unknown id or a cross-ID mismatch (revision belongs to another agent).
    """
    await _load_agent_or_404(name)
    revisions_repo = await _agent_revisions_repo()
    try:
        revision = await revisions_repo.get(revision_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Revision not found: {revision_id}")
    if revision.agent_name != name:
        # Cross-ID guard: a revision id whose agent_name != path {name} is a
        # 404 (never leak that the id exists under another agent).
        raise HTTPException(status_code=404, detail=f"Revision not found: {revision_id}")
    try:
        updated = await revisions_repo.mark_dismissed(revision_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return updated.model_dump()


@router.post("/agents/{name}/self-configuration/revisions/{revision_id}/approve")
async def approve_agent_revision(
    name: str, revision_id: str, override: bool = False
) -> dict[str, Any]:
    """AC10/AC11 — DD4 fail-closed approve.

    Cross-ID/unknown → 404. Idempotent no-op if already ``applied``; 409 on
    dismissed/superseded. On a pending row, compare ``base_value`` (the
    field's value the agent saw at capture) to the CURRENT stored value:

    - unchanged → apply (load → ``model_copy({field: proposed})`` → save),
      transition to ``applied`` (persist path, propagates next-session).
    - drifted and no ``override`` → **409** returning the current value, the
      proposed value, and the stale base, WITHOUT touching the store or row.
    - drifted with ``override=true`` → re-capture ``base_value`` to the
      current value, then apply and transition.
    """
    store, config = await _load_agent_or_404(name)
    revisions_repo = await _agent_revisions_repo()
    try:
        revision = await revisions_repo.get(revision_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Revision not found: {revision_id}")
    if revision.agent_name != name:
        raise HTTPException(status_code=404, detail=f"Revision not found: {revision_id}")

    if revision.status == "applied":
        # Idempotent no-op on an already-applied row.
        return revision.model_dump()
    if revision.status != "pending":
        # dismissed / superseded — cannot approve.
        raise HTTPException(
            status_code=409,
            detail=f"Revision {revision_id} is {revision.status}; cannot approve",
        )

    current = getattr(config, revision.field)
    if current != revision.base_value and not override:
        # DD4 staleness: the field drifted since the agent proposed. Fail
        # closed — return current + proposed (+ stale base) so the operator
        # sees what re-approving would overwrite; touch nothing.
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale",
                "current_value": current,
                "proposed_value": revision.proposed_value,
                "base_value": revision.base_value,
            },
        )

    # NOTE: the override branch is intentionally NOT transactional —
    # update_base_value → save → mark_applied are three separate commits. A
    # save failure after update_base_value leaves a pending row whose
    # base_value was rewritten to the current value (still re-approvable).
    # Operator-scale-acceptable; do NOT reorder so mark_applied precedes save.
    if override and current != revision.base_value:
        await revisions_repo.update_base_value(revision_id, current)

    updated_config = config.model_copy(update={revision.field: revision.proposed_value})
    await store.save(updated_config)
    updated = await revisions_repo.mark_applied(revision_id)
    return updated.model_dump()


@router.post("/agents/{name}/self-configuration/revisions/{revision_id}/restore")
async def restore_agent_revision(
    name: str,
    revision_id: str,
    side: Literal["proposed", "base"] = "proposed",
) -> dict[str, Any]:
    """M21 F02 L03 — operator-direct restore of an earlier field value.

    Restores ``description`` / ``system_prompt`` to a value it actually held.
    Applies IMMEDIATELY regardless of approval mode (DD5): the operator is the
    approval authority, so routing their restore through the queue would be
    incoherent — ``self_revision_requires_approval`` is never consulted here.

    The target must be an ``applied`` revision (LD1): only ``applied`` rows
    represent values the field genuinely took. A ``pending`` row was never
    applied, a ``dismissed`` row was declined, a ``superseded`` row was
    orphaned — reinstating any would resurrect a value the field never held.
    A non-applied target is refused with 409.

    ``side`` selects the value node to reinstate (LD2): ``proposed`` (default)
    reinstates the target row's after-image; ``base`` reinstates its
    before-image — the only way to reach the ORIGINAL pre-first-revision value
    (never a ``proposed_value``, only the earliest row's ``base_value``) and
    any out-of-band operator-set value (a mid-timeline ``base_value`` left by a
    direct ``PUT /agents/{name}`` edit). ``side`` is a ``Literal``, so FastAPI
    auto-422s an invalid value rather than silently restoring the wrong side.

    Restore is a NEW append-only row (never a pointer rewind): ``source=
    'restore'``, ``status='applied'``, ``restored_from`` = the reinstated
    revision's id, ``base_value`` = the field's pre-restore current value,
    ``proposed_value`` = the reinstated value. It is not deduplicated against
    the current value — restoring to the current value still logs an honest
    record that the operator restored at time T (AC7).

    Cross-ID/unknown id → 404 (mirroring dismiss/approve; never leak that an
    id exists under another agent).
    """
    store, config = await _load_agent_or_404(name)
    revisions_repo = await _agent_revisions_repo()
    try:
        revision = await revisions_repo.get(revision_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Revision not found: {revision_id}")
    if revision.agent_name != name:
        raise HTTPException(status_code=404, detail=f"Revision not found: {revision_id}")

    if revision.status != "applied":
        # LD1 — only an applied revision names a value the field actually held.
        raise HTTPException(
            status_code=409,
            detail=f"Revision {revision_id} is {revision.status}; "
            "only an applied revision can be restored",
        )

    # LD2 — reinstate the chosen value node.
    reinstated = revision.proposed_value if side == "proposed" else revision.base_value
    base_value = getattr(config, revision.field)  # pre-restore current value

    await store.save(config.model_copy(update={revision.field: reinstated}))

    ts = now_iso()
    restored = await revisions_repo.append(
        agent_name=name,
        field=revision.field,
        proposed_value=reinstated,
        base_value=base_value,
        source="restore",
        status="applied",
        restored_from=revision_id,
        created_at=ts,
        resolved_at=ts,
    )
    return restored.model_dump()


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


# Mask-shape single source-of-truth. The emit helper, the recognize
# regex, and any future paired helper read these constants; never
# hardcode the literals. M11 F8 L3.
_MASK_PREFIX = "***"
_MASK_TAIL_SEPARATOR = "..."
_MASK_TAIL_LEN = 4


def _emit_mask(value: str) -> str:
    """Single source-of-truth for mask shape.

    Assumes a non-empty ``str`` input — callers guard ``None`` / empty
    / non-str before calling. Returns ``_MASK_PREFIX`` (no tail) for
    short values where exposing the tail would leak too much; returns
    ``_MASK_PREFIX + _MASK_TAIL_SEPARATOR + value[-_MASK_TAIL_LEN:]``
    for longer values.

    Pair: ``_MASK_SHAPE_RE`` (below) recognizes the output of this
    helper. Both read from the same constants so a future maintainer
    cannot drift the emit shape from the recognize shape. See
    ``the_one/agents.md`` → ``single-source-of-truth-for-paired-helpers``.
    """
    if len(value) <= _MASK_TAIL_LEN:
        return _MASK_PREFIX
    return f"{_MASK_PREFIX}{_MASK_TAIL_SEPARATOR}{value[-_MASK_TAIL_LEN:]}"


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

    M11 F8 L3: str inputs route through ``_emit_mask`` (the canonical
    source-of-truth for the mask shape); non-str defensive wholesale
    mask draws from the ``_MASK_PREFIX`` constant.
    """
    if not value:
        return value
    if not isinstance(value, str):
        # Non-string secret values (e.g., a nested dict for OAuth tokens
        # in F5) — mask wholesale to avoid leaking nested structure.
        # F5 will revisit this when access/refresh tokens land. M11 F8
        # L3: drawn from _MASK_PREFIX constant.
        return _MASK_PREFIX
    return _emit_mask(value)


# Canonical "preserve existing stored value" sentinel for PUT payloads.
# The Studio UI emits this exact string for any secret field the operator
# did not touch. Hoisted above the MCP PUT handler so all secret-bearing
# PUT handlers (MCP sources, connector accounts, providers) share one
# definition; original placement was below the LLM-provider helpers but
# the MCP handler at line ~1068 needs it first. (See F7 L12 hotfix entry
# in the flight log for the round-trip mask-shape bug this resolves.)
#
# Naming note: the ``_API_KEY`` suffix is historical — the constant is
# reused for the per-key MCP/connector secrets dicts too. Renaming is a
# cosmetic refactor deferred out of this hotfix's scope.
_MASKED_API_KEY_SENTINEL = "__MASKED__"

# Matches the exact output shape of ``_emit_mask`` — either
# ``_MASK_PREFIX`` alone (short / non-string secrets) or
# ``_MASK_PREFIX + _MASK_TAIL_SEPARATOR + tail-of-1-to-_MASK_TAIL_LEN-chars``
# (longer secrets). Anchored on both sides so a legitimate user-supplied
# value that merely starts with ``***`` (e.g. ``***hello``) is NOT
# mistaken for a mask. Built from the same constants ``_emit_mask`` uses
# so the emit and recognize shapes cannot drift. M11 F8 L3.
_MASK_SHAPE_RE = re.compile(
    rf"^{re.escape(_MASK_PREFIX)}"
    rf"({re.escape(_MASK_TAIL_SEPARATOR)}.{{1,{_MASK_TAIL_LEN}}})?$"
)


def _looks_masked(value: Any) -> bool:
    """Return True if ``value`` is a sentinel or mask-shape string.

    Recognizes both ``__MASKED__`` (the canonical preserve sentinel the
    Studio UI emits) AND the GET-response mask shapes ``***`` /
    ``***...{tail4}`` produced by ``_emit_mask`` (the single
    source-of-truth for mask shape; ``_mask_secret_value`` and
    ``_mask_api_key`` both route through it). PUT handlers treat both
    as "preserve existing" — any caller that round-trips a GET-masked
    payload through a PUT no longer corrupts the stored secret with
    the literal mask string. The union-recognition (sentinel OR visual
    mask) is intentional: both semantics still matter at PUT-handler
    sites.

    Non-string values are never masked (return False) so legitimate
    boolean / dict secret values pass through to overwrite semantics
    unchanged. F7 L12 hotfix — see flight log for the discovered
    corruption case (BOT_TOKEN persisted as ``***...SD7U``).
    """
    if not isinstance(value, str):
        return False
    if value == _MASKED_API_KEY_SENTINEL:
        return True
    return bool(_MASK_SHAPE_RE.match(value))


def _secret_field_names(config_cls: type) -> set[str]:
    """Return the set of field names a tool Config marks ``secret: true``.

    Generic — reads each Pydantic field's ``json_schema_extra`` for the
    ``secret`` marker leg 2 introduced (`web_search`'s keyed-engine API
    keys are the first consumers, but ANY future built-in tool Config
    with a ``secret``-marked field gets encrypted storage + masking for
    free). ``json_schema_extra`` is ``None`` on unmarked fields — null-
    guard before the dict lookup. M16 F08 L03.
    """
    names: set[str] = set()
    for name, field_info in config_cls.model_fields.items():
        extra = field_info.json_schema_extra or {}
        if isinstance(extra, dict) and extra.get("secret") is True:
            names.add(name)
    return names


# OAuth-managed secret keys (F5 §5). These four keys are written ONLY by
# the OAuth flow's ``MCPSourceTokenStorage`` (``the_one.mcp.oauth.storage``)
# and are protected from operator overwrite via the strip-on-GET +
# preserve-on-PUT logic below. Defined ABOVE its first usage in
# ``_mcp_source_response`` (placement note: the leg's design suggested
# "near ``_MASKED_API_KEY_SENTINEL`` at api.py:886" but that constant is
# defined AFTER ``_mcp_source_response`` — a forward reference would
# fail at module import time, so the constant lives here instead. See
# leg L02 flight-log entry for the deliberate placement rationale).
from the_one.mcp.oauth.storage import (  # noqa: E402  # deliberate placement; see comment block above re: forward-reference avoidance
    OAUTH_MANAGED_SECRET_KEYS as _OAUTH_MANAGED_SECRET_KEYS,
)


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
    # F4 L3 (M08 popup-loop fix): expose access_token presence specifically.
    # The Studio MCP-test post-OAuth race needs this — `oauth_active` flips
    # when `dcr_credentials` writes, which precedes token exchange. The
    # frontend polls this flag to know when tokens are actually persisted
    # before firing the Phase 2 re-POST. Presence-only (boolean), never the
    # value; mirrors the `oauth_active` exposure pattern.
    data["has_access_token"] = "access_token" in source.secrets
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
    raises ``SandboxError`` when bwrap rejects the path at spawn
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
        # spawn time via ``SandboxError`` (L3 lands).
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


# Discord presence ``type`` enum pinned at the API boundary.
#
# This frozenset literal is the operator-meaningful subset of
# ``discord.ActivityType`` values. We deliberately do NOT read from
# ``discord.ActivityType`` at import time so the validator remains
# testable without the Discord SDK patched in (see M11 F1 L2 Design
# Decisions §2). L4's typed dropdown UI inherits this exact set.
#
# Excluded:
# - ``"unknown"`` — Discord-SDK default sentinel, never an operator choice
# - ``"custom"`` — Discord-API-only via custom status, not supported by
#   the bot-presence surface
_DISCORD_PRESENCE_TYPES = frozenset({"playing", "streaming", "listening", "watching", "competing"})


def _validate_connector_config(account: Connector) -> None:
    """Per-type shape validation for Connector.config.

    Raises HTTPException(422, detail=...) on shape mismatch. Mirrors
    the :func:`_validate_mcp_source_config` precedent — validator
    lives at the API write boundary; the error path returns a clean
    422 with a human-readable detail string. Pydantic's Literal
    validation already gates the ``type`` field at model validation
    time, so the trailing ``else`` raise is defensive
    exhaustiveness (see ``_validate_mcp_source_config`` at line 840).

    Discord (M11 F1 L2): validates the three operator-meaningful
    config keys — ``intents``, ``guilds``, ``presence`` — each
    optional. Absent keys round-trip cleanly so M10 F8 accounts
    (which lack ``intents``) keep working byte-identically.

    Stub: pass-through. The F1 stub-type carve-out accepts arbitrary
    config — per-type knowledge does not apply to stubs.
    """
    cfg = account.config

    if account.type == "discord":
        # ── intents ──────────────────────────────────────────────
        if "intents" in cfg:
            intents = cfg["intents"]
            if not isinstance(intents, dict):
                raise HTTPException(
                    status_code=422,
                    detail="Discord connector config.intents must be a dict.",
                )
            required = {"message_content", "members", "guilds"}
            if set(intents.keys()) != required:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Discord connector config.intents must have exactly "
                        f"these keys: {sorted(required)}; got: "
                        f"{sorted(intents.keys())}."
                    ),
                )
            for key, value in intents.items():
                # ``bool`` is a subclass of ``int`` in Python; the
                # ``isinstance(value, bool)`` check (NOT ``int``) means
                # a JSON ``1`` from a buggy client gets a 422. Mirrors
                # the MCP precedent at api.py:816.
                if not isinstance(value, bool):
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Discord connector config.intents.{key} must be "
                            f"a boolean; got {type(value).__name__}."
                        ),
                    )

        # ── guilds: retired (M11 F14 L02) ────────────────────────
        # The top-level "Scope to servers" guilds field was
        # unified onto ``config.allowlist.guilds`` (single source of
        # truth for both inbound-admission ACL and slash-command
        # registration). The unified guild list is validated by the
        # ``allowlist.guilds`` guard in ``db/models.py`` (list[str]); the
        # v27 migration folds + removes any legacy top-level ``guilds``.
        # No top-level validator remains.

        # ── presence ─────────────────────────────────────────────
        if "presence" in cfg:
            presence = cfg["presence"]
            if not isinstance(presence, dict):
                raise HTTPException(
                    status_code=422,
                    detail=("Discord connector config.presence must be a dict if present."),
                )
            if "name" in presence:
                name = presence["name"]
                if not isinstance(name, str) or not name.strip():
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Discord connector config.presence.name must be a non-empty string."
                        ),
                    )
            if "type" in presence:
                ptype = presence["type"]
                if not isinstance(ptype, str) or ptype not in _DISCORD_PRESENCE_TYPES:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Discord connector config.presence.type must be "
                            f"one of: {sorted(_DISCORD_PRESENCE_TYPES)}; "
                            f"got: {ptype!r}."
                        ),
                    )

        # M11 F5 L6 HAT round-8: the M11 F2 L3
        # ``system_prompt_directive`` validation block was REMOVED here
        # (criterion #14 reverted; operator-editable directive surface
        # dropped). Old rows that still carry the key pass through the
        # validator unchanged but are IGNORED at agent-create time
        # (see ``the_one/agent/factory.py``). New writes containing the
        # key are accepted (no rejection) but have no behavioral effect.

    elif account.type == "stub":
        # Stub-type carve-out — F1 trust posture accepts arbitrary
        # config for the placeholder connector. Per-type Discord-shape
        # checks do NOT apply.
        pass

    else:
        # Defensive exhaustiveness — Pydantic's Literal validator
        # already rejects unknown ``type`` values at
        # Connector.model_validate time, so this branch is
        # unreachable for properly-validated input. A future
        # contributor who adds a new connector type literal to the
        # model and forgets to extend this helper trips the raise.
        # Mirrors the MCP precedent at api.py:840-849.
        raise HTTPException(
            status_code=500,
            detail=f"Unknown connector type: {account.type!r}",
        )


@router.get("/mcp-sources")
async def list_mcp_sources(include_agent_surfaces: str | None = None) -> list[dict[str, Any]]:
    """DD3: per-agent self-configuration surface rows are hidden from the
    admin MCP Sources listing by default — the operator manages them from
    the owning agent's own tabs, not this screen. The agent editor's fetch
    passes ``?include_agent_surfaces=1`` so its MCPs tab (and the
    self-configuration tab) can still see them. The filter is a
    request-level switch, not a repository change (DD3's constraint: both
    screens call this same endpoint today).
    """
    repo = await _mcp_repo()
    sources = await repo.list()
    if include_agent_surfaces != "1":
        sources = [s for s in sources if not self_configuration_manage.is_surface_row(s)]
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
    _reject_reserved_surface_name(source)
    _validate_mcp_source_config(source)
    repo = await _mcp_repo()
    await repo.create(source)
    return _mcp_source_response(source)


def _reject_reserved_surface_name(source: MCPSource) -> None:
    """LD7 / AC8b: the literal name ``self_configuration_manage.
    SURFACE_ROW_NAME`` ("self-configuration") is reserved for the platform-
    managed self-configuration surface row — override application is keyed
    by source *name* (``_tool_provider.py``, mirrored in ``mcps-tab.js``),
    so a same-named ordinary source on the same agent would collide with
    it. Surface rows themselves are created only by ``manage.enable`` (not
    through this endpoint), so any request reaching here whose *name*
    equals the constant is, by definition, an attempt to create/rename an
    ordinary source into the reserved name — refused with 409, mirroring
    the existing "cannot edit a marked row" guard.
    """
    if (
        source.name == self_configuration_manage.SURFACE_ROW_NAME
        and not self_configuration_manage.is_surface_row(source)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{source.name!r} is reserved for the self-configuration surface; "
                "enable it from the owning agent's Self-configuration tab instead "
                "of creating or renaming an MCP source to this name."
            ),
        )


@router.put("/mcp-sources/{source_id}")
async def update_mcp_source(source_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["id"] = source_id
    repo = await _mcp_repo()
    try:
        existing = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

    # DD3 / AC10: a marked (self-configuration) row is not an ordinary MCP
    # source — its name is derived from the owning agent's name (only
    # `rename_agent` changes it) and its URL/secrets are platform-managed.
    # Blocked outright rather than special-cased field-by-field.
    if self_configuration_manage.is_surface_row(existing):
        raise HTTPException(
            status_code=409,
            detail=(
                f"MCP source {source_id!r} is a self-configuration surface row; "
                "manage it from the owning agent's Self-configuration tab."
            ),
        )

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
            if _looks_masked(value):
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
    # AC8b: `existing` is guaranteed non-surface at this point (a marked
    # row was already refused above), so this only fires when the PUT
    # would rename an ORDINARY source into the reserved constant name.
    _reject_reserved_surface_name(updated)
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

    # DD3 / AC10: DELETE on a marked (self-configuration) row performs the
    # FULL disable (detach from the owner's mcp_source_ids, unregister the
    # credential, evict the pool) rather than the ordinary lazy-install
    # cache-cleanup path below, which knows nothing about the ownership
    # marker or the credential registry.
    if self_configuration_manage.is_surface_row(source):
        agent_name = self_configuration_manage.owner_of(source)
        if agent_name is not None:
            agent_store = await _agent_store()
            # M21 F02 L02 DD8: deleting the surface row directly is also a
            # surface-disable — supersede the agent's outstanding pending
            # revisions here too (same concern as the DELETE
            # /self-configuration endpoint).
            revisions_repo = await _agent_revisions_repo()
            await self_configuration_manage.disable(
                agent_name,
                agent_store=agent_store,
                mcp_repo=repo,
                revisions_repo=revisions_repo,
            )
        else:
            # Malformed marker (no agent name) — fall back to a bare
            # evict + delete so the row doesn't become permanently stuck.
            # M21 F03 L01 (Edge Case): this bare path skips
            # `manage.disable`'s external-registry eviction. Harmless today
            # — minting an external credential requires a non-`None` owner
            # (`_enabled_surface_id_or_409` → `status()` → `owner_of`), so no
            # external credential can exist for an owner-less row, and the FK
            # cascade cleans the store rows regardless. If mint's gate ever
            # changes to admit an owner-less surface, add
            # `external_credentials.unregister(source_id)` here.
            from the_one.mcp._pool import _evict_all_for_source

            await _evict_all_for_source(source_id)
            with contextlib.suppress(KeyError):
                await repo.delete(source_id)
        return {"status": "ok"}

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
            # F4 L2 (M08): capture spec-optional serverInfo + instructions
            # alongside tools/capabilities so the MCPs tab can render a
            # server-declared subtitle line + hover-tooltip without re-probing.
            server_info = client.server_info
            instructions = client.instructions
            # F4 L3 (M08): also capture _meta — arbitrary server-supplied
            # metadata, persisted alongside the other initialize() fields.
            meta = client.meta
            protocol_version = client.negotiated_protocol_version
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
                    "server_info": server_info,
                    "instructions": instructions,
                    "meta": meta,
                    "protocol_version": protocol_version,
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
        MCPVersionMismatch,
    )
    from the_one.platform.sandbox.errors import SandboxError

    try:
        async with MCPClient(source=source, auth_provider=None) as client:
            tools = await client.list_tools()
            capabilities = client.server_capabilities
            # F4 L2 (M08): capture spec-optional serverInfo + instructions
            # alongside tools/capabilities — see _build_and_test_no_auth_mcp.
            server_info = client.server_info
            instructions = client.instructions
            # F4 L3 (M08): _meta — see _build_and_test_no_auth_mcp.
            meta = client.meta
            protocol_version = client.negotiated_protocol_version
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
                    "server_info": server_info,
                    "instructions": instructions,
                    "meta": meta,
                    "protocol_version": protocol_version,
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
    except (MCPConnectionError, MCPVersionMismatch, MCPCapabilityMissing, SandboxError) as e:
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
    from the_one.mcp.transports.streamable_http import (
        _probe_auth_posture,
        build_request_headers,
    )

    cached_posture = (source.config.get("_cache") or {}).get("auth_posture")
    has_live_tokens = bool(
        source.secrets.get("dcr_credentials") and source.secrets.get("access_token")
    )

    if cached_posture == "no_auth" and not has_live_tokens:
        return await _build_and_test_no_auth_mcp(source, source_id, repo)

    # Re-probe both on a cold cache (None) AND on a cached "oauth" hint when
    # there are no live OAuth tokens. The latter re-validation matters because
    # an operator may have ADDED static-bearer / custom-header auth after an
    # earlier probe cached "oauth" (e.g. a header-auth server first misread as
    # oauth). Re-probing with the operator's headers lets such a source flip to
    # no_auth instead of being permanently pinned to a doomed OAuth flow by the
    # stale cache. A genuine OAuth server simply re-probes to "oauth" again
    # (one cheap round trip on this operator-initiated test path) and falls
    # through to Phase B exactly as before.
    if cached_posture in (None, "oauth") and not has_live_tokens:
        server_url = source.config.get("url", "")
        # Pass the operator's configured headers (static bearer, custom
        # key/value rows) so a header-auth server probes as no_auth instead
        # of being misclassified as oauth and kicking a doomed DCR flow.
        posture = await _probe_auth_posture(
            server_url, request_headers=build_request_headers(source)
        )
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
                # F4 L2 (M08): server-declared identity + free-form prose, both
                # spec-optional and snapshotted inside the async-with for the
                # same reason as capabilities (post-disconnect reads raise).
                server_info = client.server_info
                instructions = client.instructions
                # F4 L3 (M08): _meta — same snapshot-inside-async-with rule.
                meta = client.meta
                protocol_version = client.negotiated_protocol_version
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
                        "server_info": server_info,
                        "instructions": instructions,
                        "meta": meta,
                        "protocol_version": protocol_version,
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


def _safe_script_json(payload: dict[str, Any]) -> str:
    """JSON-encode ``payload`` safely for embedding inside a ``<script>`` body.

    Escapes the four sequences that can break out of a ``<script>`` context or
    terminate a JS statement when a literal IdP-supplied string lands inside
    the JSON: ``</`` (script-end tag), ``<!--`` (HTML comment start that some
    legacy parsers treat specially inside scripts), U+2028 (LINE SEPARATOR),
    U+2029 (PARAGRAPH SEPARATOR). The last two are line-terminators in
    JavaScript and would prematurely end a string literal if left raw.

    Without this, a hostile-or-compromised OAuth Authorization Server could
    inject same-origin script via ``error_description=...</script>...`` —
    the page loads from 127.0.0.1 so the injected payload runs with the
    operator's session origin.
    """
    return (
        json.dumps(payload)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace("\u2028", "\\u2028")  # LINE SEPARATOR
        .replace("\u2029", "\\u2029")  # PARAGRAPH SEPARATOR
    )


def _render_oauth_callback_page(
    *,
    status: str,
    heading: str,
    detail_html: str,
    auto_close: bool,
    post_message: dict[str, Any] | None = None,
) -> str:
    """Render the loopback callback page in the studio visual idiom.

    The page is a self-contained HTML document served only to the popup
    window opened by the OAuth modal. It links the same studio CSS the
    SPA uses (``/static/css/...``) so the operator perceives continuity
    with the rest of GleepGlorp AI — violet-accent design system, Geist
    Sans / Geist Mono typography, quiet mono-uppercase eyebrow.

    Args:
        status: One of ``"success"``, ``"failed"``, ``"expired"``.
            Currently informational only (the quiet v3 card renders all
            states in the same neutral treatment).
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
        post_message: If provided, the page emits an early ``<script>`` that
            calls ``window.opener.postMessage(post_message, origin)`` so the
            opener can distinguish success / failed / expired close from a
            manual cancel. Without this, the Studio MCP-test close-watcher
            cannot tell whether to re-POST ``/test/connect`` (success) or
            render an error+retry (failed/expired/cancel) — leading to
            the M08 F4 L3 popup loop on Cloudflare-class auth failures.

    The CSS is intentionally inlined for the page-specific layout
    (centered card, eyebrow, big heading, hint footer). Theme tokens,
    fonts, and the data-theme attribute come from the shared studio
    stylesheets so the page automatically follows the operator's
    dark/light/auto preference resolved by ``theme.js``.
    """
    auto_close_script = (
        "<script>setTimeout(function () { try { window.close(); } "
        "catch (e) { /* popup blocker / non-script-opened — ignore */ } }, "
        "1200);</script>"
        if auto_close
        else ""
    )
    # JSON-encode is safe for embedding in a <script> body because JSON
    # string syntax is a subset of JS string syntax, and
    # ``error_description`` may contain user-controllable text from the
    # IdP. Targeting the page's own origin (loopback) means same-origin
    # postMessage to the opener; opener-side listener should also check
    # ``event.origin`` defensively.
    # Escape ``</`` (script termination), ``<!--``, and U+2028/U+2029
    # (JS line terminators) so an IdP-controlled string in ``post_message``
    # — most notably ``error_description`` on the failed branch — cannot
    # break out of the <script> body. The page loads from 127.0.0.1, so
    # same-origin protections do NOT defend against this; the escape
    # below is the only barrier.
    post_message_script = (
        f"<script>(function () {{ try {{ if (window.opener) "
        f"{{ window.opener.postMessage({_safe_script_json(post_message)}, "
        f"window.location.origin); }} }} catch (e) {{ /* opener gone / "
        f"cross-origin — silent */ }} }})();</script>"
        if post_message is not None
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
    background: var(--bg);
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
    box-shadow: var(--shadow-popover);
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
  <p class="oauth-callback-eyebrow">gleepglorp ai — oauth</p>
  <h1 class="oauth-callback-heading">{heading}</h1>
  <p class="oauth-callback-detail">{detail_html}</p>
</main>
{post_message_script}
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
                post_message={
                    "type": "mcp-oauth-result",
                    "status": "failed",
                    "source_id": entry.source_id,
                    "error": error,
                    "description": error_description,
                },
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
                post_message={
                    "type": "mcp-oauth-result",
                    "status": "expired",
                    "source_id": entry.source_id,
                },
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
            post_message={
                "type": "mcp-oauth-result",
                "status": "success",
                "source_id": entry.source_id,
            },
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


# ── Connector Accounts ────────────────────────────────────────────────────


def _connection_relevant_changed(existing: Connector, updated: Connector) -> bool:
    """Return True when the updated config differs in a connection-relevant way.

    Compares: ``secrets`` (token change), ``config.intents`` (gateway intent
    subscription), ``config.presence`` (presence update). These are the
    fields that feed into ``plugin.connect()`` or change gateway behaviour
    on reconnect.  Label-only changes (``name``), ACL changes
    (``config.allowlist``), and lifecycle changes (``idle_timeout_seconds``)
    do NOT force a reconnect — they are applied via other mechanisms or
    take effect on the next reconnect anyway.

    Using dict equality because ``config.intents`` / ``config.presence`` are
    plain JSON-serialisable dicts with no hidden ordering sensitivity.
    ``secrets`` comparison uses the plaintext dicts (already decrypted at
    this layer).

    M11 F17 L5.
    """
    if existing.secrets != updated.secrets:
        return True
    old_cfg = existing.config or {}
    new_cfg = updated.config or {}
    if old_cfg.get("intents") != new_cfg.get("intents"):
        return True
    if old_cfg.get("presence") != new_cfg.get("presence"):
        return True
    return False


async def _save_warm_background(account_id: str) -> None:
    """Background task: evict the warm entry and re-acquire to reconnect.

    Wrapped in ``asyncio.create_task`` by the save handler so the PUT
    responds immediately; the live-status poll surfaces the transition
    ``connecting → connected | error``.

    Deadlock-safe: ``_evict_all_for_account`` acquires ``_lock`` internally;
    ``account_acquire`` acquires ``_lock`` internally for the cold-entry
    creation path. Both complete before the next lock acquisition — no
    ``_lock`` is held across the two calls here.

    Writes to ``_connect_error_store`` on failure so the status endpoint
    can surface the error without re-running the failing connect. Clears
    the store entry on success.

    M11 F17 L5.
    """
    from the_one.connectors._pool import _evict_all_for_account, account_acquire
    from the_one.connectors.errors import ConnectorClientError

    try:
        await _evict_all_for_account(account_id)
        await account_acquire(account_id)
        # Clear any stale error from a previous failed warm.
        _connect_error_store.pop(account_id, None)
    except ConnectorClientError as exc:
        mapped = _map_connect_error(exc)
        _connect_error_store[account_id] = mapped
        logger.warning(
            "save-warm background reconnect failed for account=%r: %s",
            account_id,
            mapped["message"],
        )
    except Exception:
        logger.exception(
            "save-warm background: unexpected error for account=%r; not recorded as conn error",
            account_id,
        )
        raise


def _connector_response(account: Connector) -> dict[str, Any]:
    """Render a Connector into the masked HTTP response shape.

    Mirrors ``_mcp_source_response`` minus the OAuth-managed-keys strip
    (connectors have no OAuth-managed keys this flight) and minus the
    ``_cache`` server-managed-key flag (no equivalent for connectors).
    Just model_dump + replace ``secrets`` with the per-key masked form.

    INVARIANT (mirror of ``_mcp_source_response``): ``model_dump()``
    populates ``data["secrets"]`` with the decrypted plaintext dict; we
    OVERWRITE that key with the masked form before returning. Any future
    refactor that removes the overwrite would leak plaintext via the
    API. The ``test_list_returns_masked_secrets`` assertion
    ``"<raw-secret>" not in resp.text`` is the regression net.
    """
    data = account.model_dump()
    data["secrets"] = _mask_secrets(account.secrets)
    return data


@router.get("/connectors")
async def list_connectors() -> list[dict[str, Any]]:
    """List all connector accounts (masked) with an ``attached_agents_count``.

    M11 F9 L5 — each row carries ``attached_agents_count: int`` reflecting
    the count of agents whose ``connector_ids`` includes the
    account. Computed per row via
    :meth:`SQLiteAgentStore.list_by_connector` —
    O(N accounts × M agents); acceptable for the operator's small
    inventory.

    The count is NOT mirrored on the single-get / create / update
    responses — the Connectors grid is the only consumer and adding it
    everywhere would duplicate the per-row scan.
    """
    repo = await _connector_repo()
    store = await _agent_store()
    accounts = await repo.list()
    results: list[dict[str, Any]] = []
    for account in accounts:
        response = _connector_response(account)
        attached = await store.list_by_connector(account.id)
        response["attached_agents_count"] = len(attached)
        results.append(response)
    return results


@router.get("/connectors/types")
async def list_connector_types() -> list[dict[str, str]]:
    """Return the list of connector account types selectable in the UI.

    NOTE: This route MUST be registered BEFORE
    ``/connectors/{account_id}`` because FastAPI matches routes
    in registration order. If reordered, a GET to
    ``/connectors/types`` would resolve to
    ``get_connector`` with ``account_id="types"`` and 404.
    Mirrors the MCP precedent at ``list_mcp_source_types``.

    Returns the registered types from
    :func:`the_one.connectors.registry.register_builtin_connectors`; F8 L2
    added ``'discord'``. Tests that need ``'stub'`` in the list register
    it via :func:`the_one.connectors.registry.register_for_test`.
    """
    from the_one.connectors.registry import types as _connector_types

    return [{"value": t, "label": t.capitalize()} for t in _connector_types()]


@router.get("/connectors/{account_id}")
async def get_connector(account_id: str) -> dict[str, Any]:
    repo = await _connector_repo()
    try:
        account = await repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")
    return _connector_response(account)


@router.post("/connectors", status_code=201)
async def create_connector(request: Request) -> dict[str, Any]:
    data = await request.json()
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    try:
        account = Connector.model_validate(data)
    except ValidationError as e:
        # ``include_context=False`` so the response stays JSON-encodable
        # — ``model_validator`` paths populate ``ctx['error']`` with raw
        # exceptions that aren't JSON-serializable.
        raise HTTPException(status_code=422, detail=e.errors(include_context=False))
    _validate_connector_config(account)
    repo = await _connector_repo()
    await repo.create(account)
    # M11 F17 L5 save-warm: trigger background warm on create if ≥1 agent
    # is already attached (unusual but structurally possible). In practice
    # create always returns cold (no agents attached yet); the gate is here
    # for symmetry with update_connector.
    store = await _agent_store()
    attached = await store.list_by_connector(account.id)
    if attached:
        task = asyncio.create_task(_save_warm_background(account.id))
        _inflight_save_warm_tasks.add(task)
        task.add_done_callback(_inflight_save_warm_tasks.discard)
    return _connector_response(account)


@router.put("/connectors/{account_id}")
async def update_connector(account_id: str, request: Request) -> dict[str, Any]:
    data = await request.json()
    data["id"] = account_id
    repo = await _connector_repo()
    try:
        existing = await repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")

    # Per-key __MASKED__ resolution: verbatim mirror of the MCP block
    # above minus the OAuth-managed-keys preservation step (MCP-specific)
    # and minus the ``_cache`` preservation step (also MCP-specific).
    #
    # ``resolved_secrets`` is initialized OUTSIDE the if-branch (to
    # ``existing.secrets``) so the post-update eviction check
    # (``existing.secrets != resolved_secrets``) works uniformly when
    # the operator omits the ``secrets`` field entirely (intent: "I only
    # changed the name, don't touch credentials" → no eviction). This is
    # a deliberate divergence from the MCP precedent, which scopes
    # ``resolved_secrets`` inside the ``is not None`` branch.
    incoming_secrets = data.get("secrets")
    resolved_secrets: dict[str, Any] = existing.secrets
    if incoming_secrets is not None:
        if not isinstance(incoming_secrets, dict):
            raise HTTPException(status_code=422, detail="secrets must be a dict.")
        resolved_secrets = {}
        for key, value in incoming_secrets.items():
            if _looks_masked(value):
                if key in existing.secrets:
                    resolved_secrets[key] = existing.secrets[key]
                # else: client sent __MASKED__ for a key we don't have;
                # drop it silently — same as if the client had omitted
                # the key entirely.
            else:
                resolved_secrets[key] = value
        data["secrets"] = resolved_secrets

    # ``model_copy(update=...)`` does NOT re-run field validators in
    # Pydantic v2, so a PUT with an out-of-range ``idle_timeout_seconds``
    # (e.g. 0) would silently bypass the F2 L2 bounds validator. Round-
    # trip through ``model_dump() | data → model_validate(...)`` so the
    # validator fires on the merged payload and we surface the canonical
    # 422 to the operator. M10 F2 L6.
    try:
        merged = existing.model_dump()
        merged.update(data)
        updated = Connector.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_context=False))
    _validate_connector_config(updated)
    await repo.update(updated)

    # M11 F17 L5 save-warm: when any connection-relevant field changed AND
    # ≥1 agent is attached, evict the warm entry and re-acquire in the
    # background so the live-status poll surfaces the reconnect without
    # blocking the PUT response.
    #
    # This supersedes the old secrets-only eviction branch: secrets are a
    # subset of connection-relevant fields, so we handle them here
    # uniformly. A label-only or ACL-only edit skips the reconnect.
    #
    # Deadlock-safe: ``_save_warm_background`` runs on a new task; no lock
    # is held across the two internal lock acquisitions
    # (``_evict_all_for_account`` + ``account_acquire``).
    if _connection_relevant_changed(existing, updated):
        store = await _agent_store()
        attached = await store.list_by_connector(account_id)
        if attached:
            # Background: respond immediately; poll surfaces the result.
            task = asyncio.create_task(_save_warm_background(account_id))
            _inflight_save_warm_tasks.add(task)
            task.add_done_callback(_inflight_save_warm_tasks.discard)
        else:
            # No attached agents — cold by design. Still evict so the
            # old (now-stale) credentials don't linger in the pool.
            from the_one.connectors._pool import _evict_all_for_account

            await _evict_all_for_account(account_id)
    elif existing.secrets != resolved_secrets:
        # Secrets changed but not via _connection_relevant_changed
        # (shouldn't happen given secrets is checked there, but kept as
        # a belt-and-suspenders guard for future _connection_relevant_changed
        # narrowing). Evict synchronously — the old credentials are stale.
        from the_one.connectors._pool import _evict_all_for_account

        await _evict_all_for_account(account_id)

    return _connector_response(updated)


@router.delete("/connectors/{account_id}")
async def delete_connector(account_id: str) -> dict[str, str]:
    """Delete a connector account and evict warm pool entries.

    Flight 2 leg 3: ships the delete handler against the F1 stub plugin
    baseline. Mirror of MCP delete shape minus the runtime-cache cleanup
    (connectors don't have a lazy-install cache to refcount).

    Future Flight 4 (mission 10) adds ``connector_ids`` to
    ``AgentConfig``; at that point this handler will gain a "no agent
    references this account" guard before the eviction step. Until then,
    delete is unconditional.
    """
    # Function-local import per the convention; see the PUT handler's
    # block comment above for the rationale.
    from the_one.connectors._pool import _evict_all_for_account

    repo = await _connector_repo()
    try:
        await repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")

    # Evict warm pool entries BEFORE the row delete so any concurrent
    # acquire-in-flight observes the deletion at the repo layer rather
    # than serving from a stale cache.
    await _evict_all_for_account(account_id)

    try:
        await repo.delete(account_id)
    except KeyError:
        # Race: another caller deleted between our get and delete.
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")

    return {"status": "ok"}


@router.post("/connectors/{account_id}/pairing-code")
async def generate_connector_pairing_code(
    account_id: str,
) -> dict[str, str]:
    """Generate (or regenerate) the pairing code for a connector.

    M10 F6 L4: writes ``account.config["pairing"] = {"code": <8-hex>,
    "issued_at": <iso>}`` and returns the new code + timestamp. The
    endpoint is the ONLY writer for the ``pairing`` reserved key; the
    operator never types the code (UX trade-off: shorter codes, no
    whitespace / typo bugs).

    Pre-existing reserved + non-reserved ``config`` keys (e.g.
    ``allowlist``, ``intent``) are preserved — we mutate ONLY the
    ``pairing`` sub-key and round-trip the rest of ``config`` verbatim
    through ``ConnectorRepository.update``.

    Does NOT trigger warm-pool eviction. Eviction at PUT-time fires only
    on a ``secrets`` change (see ``update_connector`` above);
    ``config["pairing"]`` is consulted at inbound-dispatch time per leg 2
    and does not live inside any cached ``ConnectorClient`` instance.
    """
    repo = await _connector_repo()
    try:
        account = await repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")
    code = secrets.token_hex(4)  # 8 hex chars
    issued_at = now_iso()
    # Preserve all other config keys (allowlist, intent, …) — only
    # mutate the pairing sub-key. Leg-1b's field_validator fires on
    # ``model_validate`` at repo.update time and rejects malformed
    # shapes; the {"code", "issued_at"} dict we set here is the
    # canonical shape.
    new_config = dict(account.config)
    new_config["pairing"] = {"code": code, "issued_at": issued_at}
    updated = account.model_copy(update={"config": new_config})
    # Round-trip through model_validate so leg-1b's @field_validator
    # runs on the merged config (mirror of the PUT handler's pattern).
    updated = Connector.model_validate(updated.model_dump())
    await repo.update(updated)
    return {"code": code, "issued_at": issued_at}


async def _replay_approved_message(
    account_id: str,
    approval_id: str,
    *,
    original_message: str | None,
    channel_id: str | None,
    thread_id: str | None,
    peer_id: str,
    peer_name: str,
    account_type: str,
) -> None:
    """Background task: re-dispatch an approved peer's original message.

    Called from ``approve_peer_approval`` AFTER the approval row is
    terminal and the allowlist has been updated (so the peer is admitted
    when the re-dispatched envelope passes through the policy gate).

    All envelope data is passed in directly (not re-fetched from DB) —
    we already have the values at the call site and this avoids a second
    DB round-trip inside the background task.

    Failure-safe contract: any exception is caught, logged, and swallowed
    so the approve HTTP response is never affected. The approval already
    committed before this task runs.

    Legacy-safe: if the pending row carries no ``original_message`` (row
    was created before v29), log at INFO and return without dispatching —
    the approval still succeeded; we just cannot proactively answer.

    M11 F17 L10 — Leg F.
    """
    from the_one.agent.factory import get_factory
    from the_one.connectors._inbound import dispatch_inbound
    from the_one.connectors.base import InboundEnvelope

    try:
        if not original_message:
            # Legacy row — no original message stored (pre-v29 pending row).
            # Approval succeeded; skip proactive answer silently (not an error).
            logger.info(
                "replay_approved_message: approval %s for account=%s has no "
                "original_message (legacy pre-v29 row); skipping proactive replay",
                approval_id,
                account_id,
            )
            return

        factory = get_factory()
        if factory is None:
            logger.warning(
                "replay_approved_message: AgentFactory not yet installed "
                "(lifespan startup may not have run); skipping replay for "
                "approval=%s account=%s",
                approval_id,
                account_id,
            )
            return

        envelope = InboundEnvelope(
            platform=account_type,
            account_id=account_id,
            channel_id=channel_id or "",
            thread_id=thread_id,
            peer_id=peer_id,
            peer_name=peer_name,
            text=original_message,
            raw={"is_dm": True},
        )
        await dispatch_inbound(account_id, envelope, factory=factory)
    except Exception:
        logger.exception(
            "replay_approved_message: replay failed for approval=%s account=%s; "
            "approval already committed — peer is approved",
            approval_id,
            account_id,
        )


@router.post("/connectors/{account_id}/peer-approvals/{approval_id}/approve")
async def approve_peer_approval(
    account_id: str,
    approval_id: str,
) -> dict[str, Any]:
    """Approve a pending peer-approval; add the peer to the account allowlist.

    M11 F9 L3 — Discord-native peer-approval action endpoint. Flips the
    pending_approvals row to ``status='approved'`` and adds
    ``approval.peer_id`` to ``account.config['allowlist']['peers']``
    (idempotent — duplicates are not appended). On an already-approved
    row, returns the existing row (the allowlist mutation is re-applied
    as a no-op, matching the repo's mark_approved idempotency contract).
    On a dismissed row, raises 409 (terminal-state mismatch).

    404 semantics:
      * Unknown ``account_id`` → 404.
      * Unknown ``approval_id`` → 404.
      * ``approval_id`` exists but its ``connector_id`` does not
        match the URL's ``account_id`` → 404 (defense-in-depth against
        cross-account ID smuggling).

    Allowlist mutation runs AFTER ``mark_approved`` succeeds; if the
    subsequent ``conn_repo.update`` raises, the approval row is terminal
    but the allowlist was not updated. Recovery: next inbound DM from
    the peer creates a fresh ``pending`` row. The pairing-code endpoint
    shares the same no-transaction-wrap posture — see leg-3 design.
    """
    conn_repo = await _connector_repo()
    try:
        account = await conn_repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")

    approval_repo = await _pending_approval_repo()
    try:
        approval = await approval_repo.get(approval_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Pending approval not found: {approval_id}")
    if approval.connector_id != account_id:
        raise HTTPException(status_code=404, detail=f"Pending approval not found: {approval_id}")

    try:
        updated_approval = await approval_repo.mark_approved(approval_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Idempotent allowlist mutation. Initialize allowlist if missing /
    # empty (mirrors the dispatcher pattern at _inbound.py:428-438).
    # M11 F17 L8 (Leg D) — peers axis stores bare ``{id}`` dicts
    # post-v28. Approving a peer adds them to the Direct Messages list
    # as allowed immediately; no per-peer toggle required. This fixes
    # the F16-parked Known Issue (F3a): approve → peer can DM at once
    # under ``dm_admission="admin-approved"``.
    new_config = dict(account.config)
    allowlist = dict(new_config.get("allowlist") or {})
    peers = list(allowlist.get("peers") or [])
    if not any(p["id"] == approval.peer_id for p in peers):
        peers.append({"id": approval.peer_id})
    allowlist["peers"] = peers
    allowlist.setdefault("channels", [])
    new_config["allowlist"] = allowlist
    updated_account = account.model_copy(update={"config": new_config})
    updated_account = Connector.model_validate(updated_account.model_dump())
    await conn_repo.update(updated_account)

    # Background replay: re-dispatch the peer's original message now that
    # they're admitted (M11 F17 L10 — Leg F). The approval committed above
    # is the send-once gate — mark_approved is idempotent (early-returns on
    # self-target), so a concurrent double-approve produces at most one task
    # per approval. The task is failure-safe: any error is caught + logged
    # inside ``_replay_approved_message``; a replay failure DOES NOT fail
    # the approve response. All replay data is passed directly from the
    # in-memory objects to avoid a second DB round-trip in the background task.
    replay_task = asyncio.create_task(
        _replay_approved_message(
            account_id,
            approval_id,
            original_message=approval.original_message,
            channel_id=approval.channel_id,
            thread_id=approval.thread_id,
            peer_id=approval.peer_id,
            peer_name=approval.peer_name,
            account_type=account.type,
        )
    )
    _inflight_replay_tasks.add(replay_task)
    replay_task.add_done_callback(_inflight_replay_tasks.discard)

    return updated_approval.model_dump()


@router.post("/connectors/{account_id}/peer-approvals/{approval_id}/dismiss")
async def dismiss_peer_approval(
    account_id: str,
    approval_id: str,
) -> dict[str, Any]:
    """Dismiss a pending peer-approval; do not mutate the allowlist.

    M11 F9 L3. Mirrors :func:`approve_peer_approval` sans the allowlist
    mutation. Same 404 / 409 / 200-idempotent semantics — see that
    docstring for the contract details.
    """
    conn_repo = await _connector_repo()
    try:
        await conn_repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")

    approval_repo = await _pending_approval_repo()
    try:
        approval = await approval_repo.get(approval_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Pending approval not found: {approval_id}")
    if approval.connector_id != account_id:
        raise HTTPException(status_code=404, detail=f"Pending approval not found: {approval_id}")

    try:
        updated_approval = await approval_repo.mark_dismissed(approval_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return updated_approval.model_dump()


@router.get("/connectors/peer-approvals/pending-count")
async def get_pending_approval_count() -> dict[str, int]:
    """Return the global count of pending peer-approvals across all connectors.

    M11 F17 L9 (Leg E) — drives the top-nav Chat badge. Lightweight
    read-path: a single ``SELECT COUNT(*)`` with no per-row fetch. No
    secret leak (count only; no peer/connector detail exposed).
    """
    approval_repo = await _pending_approval_repo()
    count = await approval_repo.count_pending()
    return {"count": count}


@router.get("/connectors/peer-approvals/pending")
async def list_pending_approvals() -> list[dict[str, Any]]:
    """Return all pending peer-approvals across all connectors, newest first.

    M11 F17 L9 (Leg E) — drives the Chat left-panel pending section.

    Returned fields per row: ``id``, ``connector_id``, ``peer_id``,
    ``peer_name``, ``preview``, ``received_at``, ``status``.

    Projected out: ``original_message``, ``channel_id``, ``thread_id``,
    ``is_dm`` (internal replay-context fields added by Leg F; the
    frontend does not need them and we should not ship the full message
    text to the left-panel list).
    """
    _frontend_fields = {
        "id",
        "connector_id",
        "peer_id",
        "peer_name",
        "preview",
        "received_at",
        "status",
    }
    approval_repo = await _pending_approval_repo()
    rows = await approval_repo.list_all_pending()
    return [{k: v for k, v in r.model_dump().items() if k in _frontend_fields} for r in rows]


@router.get("/connectors/{account_id}/attached-agents")
async def list_attached_agents_for_connector(
    account_id: str,
) -> list[dict[str, Any]]:
    """Return agents whose ``connector_ids`` includes this account.

    M10 F6 L4 (extended at L7 HAT): powers the read-only "Attached
    agents" section of the Studio Connector editor.

    Response shape per agent — M10 F6 L7 HAT semantic redesign:
      * ``name``: agent slug.
      * ``peers``: ``list[str] | None`` — the agent's per-account
        ``peers`` override (None means "inherit account-scope", ``[]``
        means "explicit empty / no peer", non-empty means "subset").
        ``None`` when the agent has no per-account entry at all.
      * ``channels``: ``list[str] | None`` — same tri-state semantic as
        ``peers``.
      * ``peers_count`` / ``channels_count``: retained for back-compat
        with older Studio bundles in the wild; both are ``0`` when the
        corresponding axis is ``None`` or ``[]``.

    Performance: O(N agents). Acceptable for the operator's small agent
    count (typically <50). If the count climbs, a JSON-extract query
    against the ``connector_ids`` column would scale better
    (F10 territory).

    M10 F7 L3: the inline ``list_agents() → load each → filter`` pattern
    was lifted into :meth:`SQLiteAgentStore.list_by_connector`,
    the inverse-query helper introduced for the routing engine (F7 L4)
    and dispatcher integration (F7 L5). This endpoint now consumes the
    same helper; response shape is unchanged.
    """
    repo = await _connector_repo()
    try:
        await repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")

    store = await _agent_store()
    attached = await store.list_by_connector(account_id)
    result: list[dict[str, Any]] = []
    for cfg in attached:
        acls = cfg.connector_acls or {}
        acl = acls.get(account_id)
        if acl is None:
            peers_val: list[str] | None = None
            channels_val: list[str] | None = None
        else:
            peers_val = acl.get("peers")
            channels_val = acl.get("channels")
        result.append(
            {
                "name": cfg.name,
                "peers": peers_val,
                "channels": channels_val,
                "peers_count": len(peers_val) if peers_val else 0,
                "channels_count": len(channels_val) if channels_val else 0,
            }
        )
    return result


def _map_connect_error(exc: BaseException) -> dict[str, Any]:
    """Map a connector connect exception to an operator-facing message.

    Walks ``exc.__cause__`` to unwrap the original discord exception from
    the :class:`~the_one.connectors.errors.ConnectorConnectionError`
    wrapper (the pool worker catches the raw discord exception and re-raises
    it as ``ConnectorConnectionError``; the raw exception is chained as
    ``__cause__``). Returns a dict with ``message`` (human-readable copy)
    and ``action_link`` (URL or None).

    Three known cases:
      - ``discord.errors.PrivilegedIntentsRequired`` — message + link to
        the Discord Developer Portal "Privileged Gateway Intents" page.
      - ``discord.errors.LoginFailure`` — bad-token copy, no link.
      - Any other / unknown — generic one-liner, no link.

    Leg B reuses this function verbatim for the always-request-3 portal
    error surface. Keep it module-level and import-safe (function-local
    discord import so the module stays importable without the discord SDK).

    M11 F17 L5.
    """
    # Walk the cause chain to find the innermost meaningful exception.
    cause: BaseException | None = exc
    inner = exc
    while cause is not None:
        inner = cause
        cause = getattr(cause, "__cause__", None)

    try:
        import discord.errors as _de  # function-local per the convention
    except ImportError:
        _de = None  # type: ignore[assignment]

    if _de is not None and isinstance(inner, _de.PrivilegedIntentsRequired):
        return {
            "message": (
                "This bot is missing a required privileged intent "
                "(PrivilegedIntentsRequired). Enable Message Content and "
                "Guild Members intents in the Discord Developer Portal for "
                "this application, then save again."
            ),
            "action_link": "https://discord.com/developers/applications",
        }
    if _de is not None and isinstance(inner, _de.LoginFailure):
        return {
            "message": (
                "The bot token was rejected by Discord. "
                "Rotate the token in the Discord Developer Portal and "
                "update the BOT_TOKEN credential, then save again."
            ),
            "action_link": None,
        }
    return {
        "message": f"Connection failed: {type(inner).__name__}: {inner}",
        "action_link": None,
    }


# Module-level dict to persist the most recent connect-error per account so
# the status endpoint can surface it without re-running the failing connect.
# Keyed by account_id; values are ``{"message": str, "action_link": str|None}``.
# Write: save-warm background task (api.py:_save_warm_background).
# Read: GET /api/connectors/{id}/status.
# Reset: cleared on the next successful warm (save-warm or Validate warmup).
# Single-User-Local posture — no eviction / TTL needed.
_connect_error_store: dict[str, dict[str, Any]] = {}

# Set of live save-warm background tasks. Held in a module-level set so
# the GC doesn't collect the task before it completes (same pattern as
# app.py:_inflight_resume_tasks). Tasks remove themselves via done-callback.
_inflight_save_warm_tasks: set[asyncio.Task] = set()

# Set of live approval-replay background tasks (M11 F17 L10 — Leg F).
# Mirrors ``_inflight_save_warm_tasks`` — keeps the GC from collecting the
# task before it completes. The approve HTTP response returns immediately;
# the replay runs in the background. A replay failure DOES NOT fail the
# approval (the peer is already approved before the task is created).
_inflight_replay_tasks: set[asyncio.Task] = set()


@router.get("/connectors/{account_id}/status")
async def get_connector_status(account_id: str) -> dict[str, Any]:
    """Return the live connection state for a connector account.

    Response shape: ``{state, alive, last_error, last_error_link}`` where
    ``state`` ∈ ``{connected, connecting, disconnected, error}``.

    ``alive`` is the warm pool entry's ``is_alive()`` result at read time.
    ``last_error`` and ``last_error_link`` are non-null only when
    ``state == "error"`` (populated by the save-warm background task).

    Degrades gracefully: returns ``{state: "disconnected", alive: false}``
    when no warm entry exists (cold pool or unknown account). Returns 404
    only when the account row itself doesn't exist.

    M11 F17 L5.
    """
    repo = await _connector_repo()
    try:
        await repo.get(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {account_id}")

    from the_one.connectors._pool import _get_account_status_snapshot

    err_entry = _connect_error_store.get(account_id)
    last_error = err_entry.get("message") if err_entry else None
    last_error_link = err_entry.get("action_link") if err_entry else None

    snapshot = await _get_account_status_snapshot(
        account_id,
        last_error=last_error,
        last_error_link=last_error_link,
    )
    # Convert application_id int → str for JSON (OAuth2 client ids are
    # large ints that may exceed JS's safe-integer range; string is safer).
    # None stays None — the frontend treats null as "not yet available".
    app_id_str = str(snapshot.application_id) if snapshot.application_id is not None else None
    return {
        "state": snapshot.state,
        "alive": snapshot.alive,
        "last_error": snapshot.last_error,
        "last_error_link": snapshot.last_error_link,
        "application_id": app_id_str,
    }


@router.post("/connectors/{account_id}/test/connect")
async def test_connector_connection(account_id: str) -> dict[str, Any]:
    """Run the connector plugin's doctor probe against the account.

    Returns 404 if the account is not found, otherwise an HTTP-200 envelope
    shaped ``{status, message, details}``. ``ConnectorClientError`` is
    converted to a ``{status: "error", ...}`` envelope (HTTP 200); other
    exceptions are deliberately NOT caught and will surface as 500 so plugin
    contract violations are visible.

    Unknown connector types (registry has no entry for ``account.type``)
    return ``{status: "error", ...}`` with HTTP 200, mirroring the MCP
    "unknown transport" pattern so the UI banner can render inline rather
    than triggering a global error handler.

    No in-flight override body in Flight 2 (Design Decision) — operators
    Create-then-Test via the leg-5 combined-action button. Route signature
    is ``(account_id: str)`` only.
    """
    # Function-local import per the convention in this section.
    from the_one.connectors._pool import account_acquire
    from the_one.connectors.errors import (
        ConnectorClientError,
        ConnectorRegistrationError,
    )
    from the_one.connectors.registry import resolve as _resolve_plugin

    repo = await _connector_repo()
    try:
        account = await repo.get(account_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Connector not found: {account_id}",
        )

    try:
        plugin = _resolve_plugin(account.type)
    except ConnectorRegistrationError:
        return {
            "status": "error",
            "message": f"Unknown connector type: {account.type}",
            "details": {
                "error": "type not registered",
                "type": account.type,
            },
        }

    try:
        report = await plugin.doctor(account, get_encryptor(settings.data_dir))
    except ConnectorClientError as e:
        return {
            "status": "error",
            "message": str(e) or type(e).__name__,
            "details": {
                "error": str(e),
                "exception_type": type(e).__name__,
            },
        }

    # Shallow-copy report.details so we don't mutate the plugin's-owned dict
    # (M11 F4 L2 — convention `pool-warming-entrypoints-are-finite-and-named`).
    details = dict(report.details)
    pool_warmed = False
    pool_warm_error: str | None = None

    if report.status == "ok":
        try:
            await account_acquire(account_id)
        except Exception as exc:
            # best-effort warmup; isolated from doctor verdict per F4 L2.
            pool_warm_error = str(exc)
        else:
            pool_warmed = True
        # M11 F17 L5: persist application_id so the invite section renders
        # without a prior Validate on the next page load. Write to
        # ``account.config["application_id"]`` if the doctor supplied one.
        # Best-effort — a persistence failure here is not surfaced to the
        # operator because the doctor result already succeeded and the
        # in-session invite already works via the JS module cache.
        app_id = details.get("application_id")
        if app_id:
            try:
                fresh = await repo.get(account_id)
                fresh_cfg = dict(fresh.config or {})
                fresh_cfg["application_id"] = app_id
                updated_account = fresh.model_copy(update={"config": fresh_cfg})
                await repo.update(updated_account)
            except Exception:
                pass  # best-effort; ignore persistence errors

    details["pool_warmed"] = pool_warmed
    details["pool_warm_error"] = pool_warm_error

    return {
        "status": report.status,
        "message": report.message,
        "details": details,
    }


# ── Discoverable Entities (M11 F3 L4) ─────────────────────────────────────


class _DiscoverableEntityOut(BaseModel):
    """Pydantic response shape for one discoverable entity.

    Mirrors :class:`the_one.connectors.base.DiscoverableEntity`'s fields
    plus the projected ``stale: bool`` flag — staleness is a render-time
    concern, NOT a substrate dataclass field (see M11 F3 L4 leg artifact
    Design Decision "stale flag projection at API time").
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    group: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    stale: bool = False


class _DiscoverableEntitiesResponse(BaseModel):
    """Pydantic response shape for the discoverable-entities endpoints.

    The four axes (``peers``, ``channels``, ``groups``, ``roles``) are
    flattened lists where fresh entries (from the pool's
    ``discoverable_entities_cache``) precede stale entries (from the
    pool's ``discoverable_entities_stale_carry``); each entry carries
    ``stale: false`` or ``stale: true`` respectively.
    """

    model_config = ConfigDict(extra="forbid")

    entities: dict[str, list[_DiscoverableEntityOut]]
    fetched_at: str
    stale_seconds: float


def _empty_discoverable_response() -> _DiscoverableEntitiesResponse:
    """Build the fail-open empty response for first-call edge cases.

    Used when the warm entry exists but the inline refresh returns
    ``False`` (mid-connect race, evicted-mid-refresh, plugin raised).
    The frontend's manual Refresh button is the recovery path; the next
    periodic sweep fires within ≤ 5 minutes.
    """
    return _DiscoverableEntitiesResponse(
        entities={"peers": [], "channels": [], "groups": [], "roles": []},
        fetched_at=now_iso(),
        stale_seconds=0.0,
    )


def _project_discoverable_entity(entity: Any, *, stale: bool) -> _DiscoverableEntityOut:
    """Project a :class:`DiscoverableEntity` dataclass into the response shape.

    The substrate dataclass has no ``stale`` field — staleness is the
    API layer's render-time projection per M11 F3 L4 Design Decisions.
    """
    return _DiscoverableEntityOut(
        id=entity.id,
        label=entity.label,
        group=entity.group,
        metadata=dict(entity.metadata),
        stale=stale,
    )


def _build_discoverable_response(snapshot: Any) -> _DiscoverableEntitiesResponse:
    """Build a populated :class:`_DiscoverableEntitiesResponse` from a
    cache snapshot returned by ``_get_account_cache_snapshot``.

    Caller must ensure ``snapshot.cache`` is not ``None``. Stale entries
    (from ``snapshot.stale_carry``) are appended to each axis after the
    fresh entries; both carry the projected ``stale`` flag.
    """
    cache = snapshot.cache
    stale_carry = snapshot.stale_carry
    entities: dict[str, list[_DiscoverableEntityOut]] = {}
    for axis in ("peers", "channels", "groups", "roles"):
        fresh = [_project_discoverable_entity(e, stale=False) for e in getattr(cache, axis)]
        stale_list: list[_DiscoverableEntityOut] = []
        if stale_carry is not None:
            stale_list = [
                _project_discoverable_entity(e, stale=True) for e in getattr(stale_carry, axis)
            ]
        entities[axis] = fresh + stale_list
    fetched_at = cache.fetched_at or now_iso()
    if snapshot.fetched_at_monotonic is not None:
        stale_seconds = max(0.0, time.monotonic() - snapshot.fetched_at_monotonic)
    else:
        stale_seconds = 0.0
    return _DiscoverableEntitiesResponse(
        entities=entities,
        fetched_at=fetched_at,
        stale_seconds=stale_seconds,
    )


@router.get(
    "/connectors/{account_id}/discoverable-entities",
    response_model=_DiscoverableEntitiesResponse,
)
async def get_discoverable_entities(account_id: str) -> _DiscoverableEntitiesResponse:
    """Return the cached discoverable-entities view for a connector.

    Contracts:
      - 404 (Connector not found): the repo lookup raises
        ``KeyError`` (no such account in the DB).
      - 404 (Run Test Connection first): the account exists but the
        pool has no warm entry — operator must populate the pool first
        (via Test Connection, lifespan listener-warmup, or any other
        ``account_acquire`` path).
      - 503: the account's connector plugin does NOT implement
        ``enumerate_discoverable_entities`` (e.g., the stub plugin).
      - 200 (populated cache): the warm entry has a fresh
        ``discoverable_entities_cache``; the response carries the four
        axes plus the projected ``stale`` flag for each entity.
      - 200 (first-call inline refresh): the warm entry exists but
        ``cache is None`` — the endpoint fires a single inline refresh
        via :func:`_refresh_discoverable_entities_for_account`. If the
        refresh returns ``True``, the populated response is returned;
        if ``False`` (mid-connect race / evicted-mid-refresh), the
        endpoint fails open with an empty 200 (Design Decision per leg).
    """
    # Function-local imports per this section's convention. See the
    # ``test_connector_connection`` handler's import block for the
    # rationale (function-local-import-to-break-load-cycle).
    from the_one.connectors._pool import (
        _get_account_cache_snapshot,
        _refresh_discoverable_entities_for_account,
    )
    from the_one.connectors.errors import ConnectorRegistrationError
    from the_one.connectors.registry import resolve as _resolve_plugin

    repo = await _connector_repo()
    try:
        await repo.get(account_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Connector not found: {account_id}",
        )

    snapshot = await _get_account_cache_snapshot(account_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="Run Test Connection first to populate the bot's discoverable view.",
        )

    try:
        plugin = _resolve_plugin(snapshot.account_type)
    except ConnectorRegistrationError:
        raise HTTPException(
            status_code=503,
            detail="This connector type does not expose discoverable entities.",
        )
    if getattr(plugin, "enumerate_discoverable_entities", None) is None:
        raise HTTPException(
            status_code=503,
            detail="This connector type does not expose discoverable entities.",
        )

    if snapshot.cache is None:
        refreshed = await _refresh_discoverable_entities_for_account(account_id)
        if not refreshed:
            return _empty_discoverable_response()
        snapshot = await _get_account_cache_snapshot(account_id)
        if snapshot is None or snapshot.cache is None:
            return _empty_discoverable_response()

    return _build_discoverable_response(snapshot)


@router.post(
    "/connectors/{account_id}/discoverable-entities/refresh",
    response_model=_DiscoverableEntitiesResponse,
)
async def refresh_discoverable_entities(
    account_id: str,
) -> _DiscoverableEntitiesResponse:
    """Force a synchronous refresh of the discoverable-entities cache.

    Same 404 / 503 contracts as the GET handler. Always invokes
    :func:`_refresh_discoverable_entities_for_account` (regardless of
    whether the cache is currently populated); on ``False`` return the
    endpoint fails open with an empty 200 response (Design Decision per
    the leg artifact's first-call edge-case handling).
    """
    from the_one.connectors._pool import (
        _get_account_cache_snapshot,
        _refresh_discoverable_entities_for_account,
    )
    from the_one.connectors.errors import ConnectorRegistrationError
    from the_one.connectors.registry import resolve as _resolve_plugin

    repo = await _connector_repo()
    try:
        await repo.get(account_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Connector not found: {account_id}",
        )

    snapshot = await _get_account_cache_snapshot(account_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="Run Test Connection first to populate the bot's discoverable view.",
        )

    try:
        plugin = _resolve_plugin(snapshot.account_type)
    except ConnectorRegistrationError:
        raise HTTPException(
            status_code=503,
            detail="This connector type does not expose discoverable entities.",
        )
    if getattr(plugin, "enumerate_discoverable_entities", None) is None:
        raise HTTPException(
            status_code=503,
            detail="This connector type does not expose discoverable entities.",
        )

    refreshed = await _refresh_discoverable_entities_for_account(account_id)
    if not refreshed:
        return _empty_discoverable_response()
    snapshot = await _get_account_cache_snapshot(account_id)
    if snapshot is None or snapshot.cache is None:
        return _empty_discoverable_response()
    return _build_discoverable_response(snapshot)


# ── Connector disposition counters ────────────────────────────────────────


class _ConnectorDispositionCountersResponse(BaseModel):
    """Response shape for :func:`get_connector_disposition_counters`.

    ``inbound`` and ``outbound`` are dicts keyed by disposition string
    (e.g. ``"stepped"``, ``"ok"``) with integer counts. Both dicts are
    empty when no dispositions have been recorded since the pool entry
    warmed.

    ``warm`` is ``True`` when a pool entry exists for the account. When
    ``False``, the counts are always empty (the pool entry has been
    evicted or has never warmed for this account).

    M11 F17 L1.
    """

    model_config = ConfigDict(extra="forbid")

    warm: bool
    inbound: dict[str, int]
    outbound: dict[str, int]


@router.get(
    "/connectors/{account_id}/disposition-counters",
    response_model=_ConnectorDispositionCountersResponse,
)
async def get_connector_disposition_counters(
    account_id: str,
) -> _ConnectorDispositionCountersResponse:
    """Return the per-account inbound/outbound disposition counters.

    Contracts:
      - 404 (Connector not found): the repo lookup raises ``KeyError``
        (no such account in the DB).
      - 200 (warm entry): ``warm=True`` with the current counters.
      - 200 (cold / no warm entry): ``warm=False`` with empty dicts.
        Degrades cleanly when no pool entry is warm — the operator must
        run Test Connection or trigger a dispatch first.

    Counters reset on pool-entry eviction (accepted limitation — they
    measure "since the current pool entry warmed"). The operator reads
    them during a soak to confirm steady-state disposition distribution.

    M11 F17 L1. Mirrors :func:`get_discoverable_entities` structure;
    does NOT touch the doctor probe.
    """
    from the_one.connectors._pool import _get_account_counters_snapshot

    repo = await _connector_repo()
    try:
        await repo.get(account_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Connector not found: {account_id}",
        )

    snapshot = await _get_account_counters_snapshot(account_id)
    if snapshot is None:
        return _ConnectorDispositionCountersResponse(
            warm=False,
            inbound={},
            outbound={},
        )

    return _ConnectorDispositionCountersResponse(
        warm=True,
        inbound=snapshot.inbound,
        outbound=snapshot.outbound,
    )


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
        # M11 F13 L5: routing-audit inspector. Surfaces session_metadata
        # ONLY on the detail endpoint composition — the shared
        # _session_summary() helper at :3246 stays untouched, so list /
        # create / update endpoints keep their summary-only response
        # shape and the per-session routing payload does not bloat list
        # responses.
        "session_metadata": session.session_metadata,
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


@router.delete("/agents/{name}/chat/sessions")
async def delete_agent_chat_sessions(name: str) -> dict[str, Any]:
    repo = await _chat_repo()
    deleted = await repo.delete_all_for_agent(name)
    return {"status": "ok", "deleted": deleted}


@router.post("/chat/sessions/{session_id}/purge")
async def purge_chat_messages(session_id: str) -> dict[str, str]:
    repo = await _chat_repo()
    try:
        await repo.purge_messages(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return {"status": "ok"}


@router.post("/_test/chat/sessions/{session_id}/routing-audit")
async def seed_routing_audit(session_id: str, request: Request) -> dict[str, int]:
    """M11 F15 L2 — dev-mode-gated test seam.

    Seeds ``session_metadata["routing"]`` over HTTP so the
    ``audit-log-inspector-renders-routing-entries`` behavior test (which
    runs against the LIVE container via Chrome MCP + out-of-band curl, not
    pytest) has a single-curl seed path. Replaces the broken precondition
    that tried to seed via ``PUT /chat/sessions/{id}`` — ``update`` drops
    ``session_metadata`` by design (repositories.py:936 docstring), so this
    routes through ``set_session_metadata_key`` instead (overwrite
    semantic, round-trips session_metadata).

    Test-seam precedent: ``THE_ONE_REGISTER_STUB_CONNECTOR`` + ``dev_mode``
    gate (app.py:118) and the mock-provider dev-mode gate (api.py:3378).
    Unlike that field-level 400, this is a whole-endpoint disablement → 403.
    """
    # Gate FIRST — this endpoint writes arbitrary routing JSON and is never
    # a production surface.
    if not settings.dev_mode:
        raise HTTPException(
            status_code=403,
            detail="test-seam endpoint requires THE_ONE_DEV_MODE=true",
        )
    data = await request.json()
    routing = data.get("routing")
    if not isinstance(routing, list):
        raise HTTPException(
            status_code=400,
            detail="body must contain a 'routing' list",
        )
    repo = await _chat_repo()
    try:
        await repo.set_session_metadata_key(session_id, "routing", routing)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return {"count": len(routing)}


@router.get("/_test/chat/sessions/lookup")
async def lookup_chat_session(
    connector_id: str,
    channel_id: str,
    thread_id: str | None = None,
) -> dict[str, str | None]:
    """M11 F15 L3 — dev-mode-gated test seam.

    Resolves the connector-attached session for an external
    ``(connector_id, channel_id[, thread_id])`` location to its session id,
    closing the observability gap that ``_session_summary`` (and the detail
    endpoint) leave open: neither carries the connector-keying fields, so
    the live-traffic HAT driver cannot otherwise locate the session that a
    bot's message created. Wraps
    :meth:`ChatSessionRepository.find_most_recent_by_external_key`
    (``platform="discord"``).

    Isolated/test-only: no production API shape change. Returns
    ``{"session_id": <id or None>}`` — null (not 404) when no session
    matches, so the driver can poll a stable shape until traffic lands.

    Gating mirrors the L2 seed sibling: 403 unless dev-mode.
    """
    # Gate FIRST — this endpoint exposes connector-keyed session resolution
    # and is never a production surface.
    if not settings.dev_mode:
        raise HTTPException(
            status_code=403,
            detail="test-seam endpoint requires THE_ONE_DEV_MODE=true",
        )
    repo = await _chat_repo()
    session = await repo.find_most_recent_by_external_key(
        platform="discord",
        connector_id=connector_id,
        channel_id=channel_id,
        thread_id=thread_id,
    )
    return {"session_id": session.id if session else None}


@router.post("/_test/purge-sweep")
async def trigger_purge_sweep() -> dict[str, Any]:
    """M13 F03 — dev-mode-gated test seam. Fires ONE daily-purge sweep
    on demand (production fires on the 24h due-check, which a behavior
    test can't wait on). Dual-gated: dev_mode AND the env flag.
    Gating mirrors the sibling /_test/ seams (403 when off)."""
    if not settings.dev_mode or os.environ.get("THE_ONE_PURGE_SWEEP_TEST_ENDPOINT") != "1":
        raise HTTPException(
            status_code=403,
            detail="test-seam endpoint requires dev_mode + THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1",
        )
    from the_one.interfaces.web.app import _run_purge_sweep_and_evict

    result = await _run_purge_sweep_and_evict()
    return {"deleted": result["deleted"], "last_purge_at": result["last_purge_at"]}


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


# ``_MASKED_API_KEY_SENTINEL`` is hoisted near ``_mask_secret_value`` so
# all secret-bearing PUT handlers (MCP, connectors, providers) share one
# definition above their first use site. See the block above
# ``_mask_secret_value`` for the constant + ``_looks_masked`` helper.

# Provider types that skip URL safety validation. ``mock`` has no real URL;
# ``ollama`` is local-by-design and operators frequently point it at
# ``http://localhost:11434`` or a LAN hostname / IP address
# that is nonetheless trusted.
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
    return _emit_mask(key)


# OAuth-managed keys stored in ``llm_providers.secrets`` for the
# ``anthropic-plan`` type (M19 F01 DD-2). Written ONLY by the OAuth
# exchange/refresh paths (never by operator create/PUT); stripped from
# every response. Mirrors the MCP ``_OAUTH_MANAGED_SECRET_KEYS`` contract.
_PLAN_OAUTH_MANAGED_KEYS = anthropic_oauth.OAUTH_MANAGED_SECRET_KEYS

# In-process pending PKCE state for /oauth/start → /oauth/code, keyed by
# provider id. A repeated /start replaces the entry (the older consent
# window's code becomes unexchangeable — acceptable; the error message
# tells the operator to use the newest window). Process-local by design:
# the exchange must happen in the same process that generated the
# verifier. No TTL — entries are evicted on successful exchange or
# replaced by the next /start; a stale entry is one dict-slot of strings.
_plan_oauth_pending: dict[str, dict[str, str]] = {}


def _provider_response(provider: LLMProviderConfig) -> dict[str, Any]:
    data = provider.model_dump()
    data["api_key"] = _mask_api_key(provider.api_key)
    # DD-2 read direction: NEVER expose the secrets blob — not even masked.
    # The UI-facing signal is the ``oauth_active`` boolean instead: true iff
    # a usable token set (access_token AND refresh_token — stricter than
    # MCP's any-key rule, pinned by test) is stored. Always present, and
    # ``False`` for non-plan types (frontend ignores unknown fields).
    secrets_dict = data.pop("secrets", None) or {}
    data["oauth_active"] = bool(
        secrets_dict.get("access_token") and secrets_dict.get("refresh_token")
    )
    return data


def _plan_bearer_client(anthropic_mod: Any, token: str) -> Any:
    """Build a bearer-mode Anthropic SDK client for plan-token calls.

    Mirrors ``AnthropicPlanProvider._build_client``: ``auth_token`` bearer
    mode + the OAuth beta header, with ``api_key`` force-nulled so the
    SDK's ``ANTHROPIC_API_KEY`` env fallback can't flip it into
    ``x-api-key`` mode. Takes the (handler-locally imported) ``anthropic``
    module as a parameter so tests can substitute it via ``sys.modules``.
    """
    from the_one.llm.anthropic_plan_provider import OAUTH_BETA_HEADER

    client = anthropic_mod.AsyncAnthropic(
        api_key=None,
        auth_token=token,
        default_headers={"anthropic-beta": OAUTH_BETA_HEADER},
    )
    client.api_key = None
    return client


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
        {"value": "anthropic-plan", "label": "Anthropic (Plan)"},
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
    # DD-2 create direction: secrets are OAuth-managed — force-empty
    # regardless of the client-supplied body. Token material enters ONLY
    # via the /oauth/code exchange path.
    data["secrets"] = {}
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
    if _looks_masked(incoming_key):
        data["api_key"] = existing.api_key

    # DD-2 update direction: OAuth-managed secret keys are pinned from the
    # stored row — a PUT can neither overwrite nor seed them (only the
    # /oauth/code exchange and the Leg-2 refresh path write them), and a
    # PUT that omits ``secrets`` entirely preserves the stored token set.
    # Mirrors the MCP source managed-keys preserve block above.
    incoming_secrets = data.get("secrets")
    resolved_secrets = dict(incoming_secrets) if isinstance(incoming_secrets, dict) else {}
    for key in _PLAN_OAUTH_MANAGED_KEYS:
        if key in existing.secrets:
            resolved_secrets[key] = existing.secrets[key]
        elif key in resolved_secrets:
            del resolved_secrets[key]
    data["secrets"] = resolved_secrets

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
    # DD-3 invalidation contract: a provider update evicts the cached plan
    # credential source so the next consumer re-reads the stored row.
    # No-op for non-plan types / uncached ids.
    plan_credentials.evict_credential_source(provider_id)
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
    # Drop any pending OAuth sign-in state for the deleted provider so a
    # later /oauth/code can't resurrect it (it would 404 anyway on the
    # row-existence re-check, but don't leak the verifier slot). Also
    # evict the cached credential source (DD-3 invalidation contract).
    _plan_oauth_pending.pop(provider_id, None)
    plan_credentials.evict_credential_source(provider_id)
    return {"status": "ok"}


async def _get_plan_provider_or_raise(provider_id: str) -> LLMProviderConfig:
    """Load a provider row and require the ``anthropic-plan`` type.

    404 for an unknown id; 409 when the row exists but is not a plan
    provider (the OAuth sign-in endpoints are type-specific).
    """
    repo = await _provider_repo()
    try:
        provider = await repo.get(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    if provider.type != "anthropic-plan":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Provider '{provider_id}' is type '{provider.type}', not 'anthropic-plan'. "
                "OAuth sign-in only applies to Anthropic plan providers."
            ),
        )
    return provider


@router.post("/providers/{provider_id}/oauth/start")
async def start_provider_oauth(provider_id: str) -> dict[str, str]:
    """Begin the PKCE sign-in flow for a saved anthropic-plan provider.

    Generates a fresh verifier/state pair, parks them in the in-process
    pending map (replacing any prior pending entry for this provider —
    the older consent window's code becomes unexchangeable), and returns
    the claude.ai authorize URL for the frontend popup / copyable link
    (DD-1, DD-7: the row must already be saved, hence the id-scoped route).
    """
    await _get_plan_provider_or_raise(provider_id)
    verifier = anthropic_oauth.generate_verifier()
    state = anthropic_oauth.generate_state()
    _plan_oauth_pending[provider_id] = {"verifier": verifier, "state": state}
    authorize_url = anthropic_oauth.build_authorize_url(
        code_challenge=anthropic_oauth.derive_challenge(verifier),
        state=state,
    )
    return {"authorize_url": authorize_url}


@router.post("/providers/{provider_id}/oauth/code")
async def submit_provider_oauth_code(provider_id: str, request: Request) -> dict[str, Any]:
    """Exchange a pasted consent code and persist the token set (DD-7).

    Accepts ``{"code": "..."}`` — bare code or the ``code#state`` display
    form, whitespace tolerated. Tokens are written server-side to the
    saved row's encrypted secrets via the dedicated ``update_secrets``
    repository method; the response is the masked provider (now with
    ``oauth_active: true``). No second Save is needed in the editor.
    """
    # Re-check row existence at exchange time — the provider may have been
    # deleted between /start and /code (edge case: 404, entry evicted by
    # the delete handler; popping again here is harmless).
    await _get_plan_provider_or_raise(provider_id)

    data = await request.json()
    pasted = data.get("code") if isinstance(data, dict) else None
    if not isinstance(pasted, str) or not pasted.strip():
        raise HTTPException(status_code=422, detail="Body must include a non-empty 'code'.")

    pending = _plan_oauth_pending.get(provider_id)
    if pending is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "No sign-in flow is pending for this provider. "
                "Start the sign-in flow first, then paste the code it displays."
            ),
        )

    code, embedded_state = anthropic_oauth.split_pasted_code(pasted)
    if not code:
        raise HTTPException(status_code=422, detail="Pasted code is empty after normalization.")
    if embedded_state is not None and embedded_state != pending["state"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "The pasted code belongs to a different sign-in window. "
                "Use the code from the most recently opened sign-in page, "
                "or restart the sign-in flow."
            ),
        )

    try:
        token_set = await anthropic_oauth.exchange_code(
            code,
            verifier=pending["verifier"],
            state=pending["state"],
        )
    except anthropic_oauth.OAuthExchangeError as exc:
        # Invalid/expired/already-used code, or a stale window. Actionable
        # 400 — the operator re-runs the sign-in flow for a fresh code.
        raise HTTPException(
            status_code=400,
            detail=(
                f"Sign-in code exchange failed: {exc} "
                "The code may be expired or already used — restart the "
                "sign-in flow and paste the newly displayed code."
            ),
        )

    repo = await _provider_repo()
    try:
        await repo.update_secrets(provider_id, token_set.to_secrets())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    _plan_oauth_pending.pop(provider_id, None)
    # Fresh sign-in over a possibly-cached source: evict so the next
    # consumer builds a source that reads the just-persisted token set
    # (one line — simpler than relying on the re-read-adoption rule).
    plan_credentials.evict_credential_source(provider_id)

    provider = await repo.get(provider_id)
    return _provider_response(provider)


@router.delete("/providers/{provider_id}/oauth")
async def reset_provider_oauth(provider_id: str) -> dict[str, Any]:
    """Reset the plan provider's OAuth connection (M19 F01 L02).

    Backend half of the Leg-3 "reset connection" control: clears the
    OAuth-managed secret keys (any non-managed keys survive — surgical,
    not a wholesale wipe), evicts the cached credential source and any
    pending sign-in verifier. The row itself is untouched; the response
    is the masked provider, now with ``oauth_active: false``. Stored
    tokens are NOT revoked upstream — this is a local disconnect.
    """
    provider = await _get_plan_provider_or_raise(provider_id)
    remaining = {k: v for k, v in provider.secrets.items() if k not in _PLAN_OAUTH_MANAGED_KEYS}
    repo = await _provider_repo()
    await repo.update_secrets(provider_id, remaining)
    _plan_oauth_pending.pop(provider_id, None)
    plan_credentials.evict_credential_source(provider_id)
    provider = await repo.get(provider_id)
    return _provider_response(provider)


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
        elif provider.type == "anthropic-plan":
            import anthropic

            # DD-3/DD-5: the token comes from the credential-source
            # accessor (refreshing if needed) — never constructed inline.
            # Re-auth-required follows the established /test contract:
            # HTTP 200 + a status field, with the distinct
            # ``reauth_required`` value (NOT a 4xx — deliberate alignment
            # with the 200-on-provider-failure family; Leg 3's editor
            # keys its affordance on ``oauth_active`` and may branch on
            # this status too).
            try:
                token = await plan_credentials.get_credential_source(provider.id).get_access_token()
            except plan_credentials.ReauthRequiredError as e:
                return {"status": "reauth_required", "detail": str(e)}
            except anthropic_oauth.OAuthError as e:
                return {"status": "error", "detail": str(e)}
            try:
                client = _plan_bearer_client(anthropic, token)
                await client.models.list()
                return {"status": "ok", "detail": "Connected to Anthropic (plan)"}
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
            # Capabilities + context_length come from /api/show — cached per
            # (base, model) for the capabilities frozenset (TTL-based). Gather
            # both in parallel; on failure, return null so the UI renders the
            # row without chips rather than failing the whole list.
            # F6.5 L04: context_length surfaced for the Studio agent-editor
            # per-model "max" chip — operator-visible verification that the
            # L01 lazy resolver will see the right denominator.
            cap_tasks = [ollama_api.get_model_capabilities(base, m.get("name", "")) for m in models]
            ctx_tasks = [
                ollama_api.get_model_context_length(base, m.get("name", "")) for m in models
            ]
            caps_list, ctx_list = await asyncio.gather(
                asyncio.gather(*cap_tasks, return_exceptions=True),
                asyncio.gather(*ctx_tasks, return_exceptions=True),
            )
            enriched = []
            for m, caps, ctx in zip(models, caps_list, ctx_list, strict=False):
                cap_array = sorted(caps) if isinstance(caps, frozenset | set) else None
                ctx_value = ctx if isinstance(ctx, int) else None
                enriched.append(
                    {
                        "id": m.get("name", ""),
                        "name": m.get("name", ""),
                        "size": m.get("size"),
                        "capabilities": cap_array,
                        "context_length": ctx_value,
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

            from the_one.llm.model_catalog import context_window_for

            client = openai.AsyncOpenAI(api_key=provider.api_key)
            response = await client.models.list()
            return [
                {"id": m.id, "name": m.id, "context_length": context_window_for("openai", m.id)}
                for m in response.data
            ]
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    elif provider.type == "anthropic":
        try:
            import anthropic

            from the_one.llm.model_catalog import context_window_for

            client = anthropic.AsyncAnthropic(api_key=provider.api_key)
            response = await client.models.list()
            # context_length is catalog-sourced per model: 1M for current Claude
            # (claude-sonnet-4 family), 200k for Haiku-class, null if unknown.
            return [
                {
                    "id": m.id,
                    "name": getattr(m, "display_name", m.id),
                    "context_length": context_window_for("anthropic", m.id),
                }
                for m in response.data
            ]
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    elif provider.type == "anthropic-plan":
        import anthropic

        from the_one.llm.model_catalog import context_window_for, models_for

        # DD-5: live listing with a token from the credential-source
        # accessor; on ANY failure (re-auth required, network, upstream
        # rejection of plan tokens) fall back to the static Anthropic
        # catalog entries so the Studio model picker always has options.
        # Context windows resolve via provider name "anthropic" — the
        # catalog's _TARGET_PROVIDERS doesn't know the plan type string.
        try:
            token = await plan_credentials.get_credential_source(provider.id).get_access_token()
            client = _plan_bearer_client(anthropic, token)
            response = await client.models.list()
            return [
                {
                    "id": m.id,
                    "name": getattr(m, "display_name", m.id),
                    "context_length": context_window_for("anthropic", m.id),
                }
                for m in response.data
            ]
        except Exception:
            logger.warning(
                "anthropic-plan: live model listing failed for provider %r; "
                "serving static catalog fallback",
                provider_id,
                exc_info=True,
            )
            return [
                {"id": model_id, "name": model_id, "context_length": window}
                for model_id, window in sorted(models_for("anthropic").items())
            ]

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
    # Load at the same effective runtime window chat will use, so a manual load
    # isn't silently reloaded at a different num_ctx on the first message. The
    # per-provider ``config.num_ctx`` (if set) takes precedence over env/default
    # — same precedence the provider applies at generation time.
    from the_one.llm.ollama_provider import effective_num_ctx

    repo = await _provider_repo()
    provider = await repo.get(provider_id)
    configured = provider.config.get("num_ctx")
    advertised = await ollama_api.get_model_context_length(base_url, model)
    try:
        await ollama_api.load_model(
            base_url, model, num_ctx=effective_num_ctx(advertised, configured)
        )
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
    # No result cap: every matching model must be reachable in the picker
    # (issue #93). The library is ~100 models and renders into a native
    # <select>, so returning the full match set is cheap; the previous
    # 30-item filtered cap silently hid models from broad searches.
    return results


# ── Encryption ───────────────────────────────────────────────────────────


@router.post("/encryption/rotate")
async def rotate_encryption_key() -> dict[str, str]:
    """Rotate the encryption key with crash-safe ordering.

    Re-encrypts every LLM provider row's ``api_key`` AND ``secrets`` blob
    (M19 F01: the anthropic-plan OAuth token set), every MCP source row's
    ``secrets`` blob, every connector account row's ``secrets`` blob, AND
    every agent row's ``tool_overrides`` / ``mcp_overrides`` columns (M21
    F01 L01 / flight-log Decision D1) using a freshly generated key in
    memory and commits the DB transaction *before* the new key file
    replaces the old one via temp-file + ``os.replace``. ALL FIVE surfaces
    commit atomically — a partial rotation that handled only a subset
    would leave the others encrypted under a key that no longer exists on
    disk. If the DB commit fails, the on-disk key file is left
    byte-identical to its pre-rotation contents so existing ciphertext on
    all five surfaces remains decryptable.

    Migration-residue MCP, connector, and provider-secrets rows (plaintext
    ``'{}'`` carried over from the column default) are tolerated via
    InvalidToken-swallowing decrypt; they are normalized to proper
    ciphertext for ``{}`` as a side-effect. The agents columns use the
    store's own ``_decrypt_overrides_column`` instead (legacy plaintext
    there is real operator data, not a ``'{}'`` default — see that
    helper's docstring); ``NULL`` columns stay ``NULL``.
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

    # Fourth surface (M19 F01): llm_providers.secrets — the anthropic-plan
    # OAuth token blob. Tolerant decrypt mirrors the MCP path below: rows
    # migrated by v33 carry the plaintext '{}' column default, which Fernet
    # rejects with InvalidToken; treat as empty and let rotation normalize
    # them to proper ciphertext. JSON decode errors are NOT swallowed.
    async with conn.execute("SELECT id, secrets FROM llm_providers") as cur:
        provider_secret_rows = await cur.fetchall()
    decrypted_provider_secrets: list[tuple[str, dict[str, Any]]] = []
    for row in provider_secret_rows:
        ciphertext = row["secrets"]
        if not ciphertext:
            prov_secrets_dict: dict[str, Any] = {}
        else:
            try:
                plaintext = encryptor.decrypt(ciphertext)
                prov_secrets_dict = json.loads(plaintext)
            except InvalidToken:
                prov_secrets_dict = {}
        decrypted_provider_secrets.append((row["id"], prov_secrets_dict))

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

    async with conn.execute("SELECT id, secrets FROM connectors") as cur:
        connector_rows = await cur.fetchall()

    # Tolerant decrypt mirrors the MCP path above. Pre-rotation connector
    # rows created through ConnectorRepository will already be
    # encrypted; tolerant decrypt only matters if a future migration adds
    # the column to pre-existing rows with the plaintext '{}' default.
    # JSON decode errors are NOT swallowed — they indicate real corruption.
    decrypted_connectors: list[tuple[str, dict[str, Any]]] = []
    for row in connector_rows:
        ciphertext = row["secrets"]
        if not ciphertext:
            conn_secrets_dict: dict[str, Any] = {}
        else:
            try:
                plaintext = encryptor.decrypt(ciphertext)
                conn_secrets_dict = json.loads(plaintext)
            except InvalidToken:
                conn_secrets_dict = {}
        decrypted_connectors.append((row["id"], conn_secrets_dict))

    async with conn.execute("SELECT name, tool_overrides, mcp_overrides FROM agents") as cur:
        agent_rows = await cur.fetchall()

    # Fifth surface (M21 F01 L01 / flight-log Decision D1): agents.tool_overrides
    # / agents.mcp_overrides. Decode via the store's own tolerant helper
    # (NOT the MCP/connector/provider inline pattern above) — legacy
    # plaintext here is real operator data (e.g. {"shell": {"timeout": 30}}),
    # not a '{}' migration-residue default, so InvalidToken must fall
    # through to the plaintext value rather than {} (see
    # _decrypt_overrides_column's docstring). `None` (NULL column) stays
    # `None` — never written back as an encrypted "null".
    decrypted_agents: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = []
    for row in agent_rows:
        tool_overrides = _decrypt_overrides_column(encryptor, row["tool_overrides"])
        mcp_overrides = _decrypt_overrides_column(encryptor, row["mcp_overrides"])
        decrypted_agents.append((row["name"], tool_overrides, mcp_overrides))

    # 2. Generate a new key + Encryptor in memory only (no disk writes yet).
    new_key = Fernet.generate_key()
    new_encryptor = Encryptor(new_key)

    # 3. Re-encrypt every row using the new encryptor.
    reencrypted = [(pid, new_encryptor.encrypt(pt)) for pid, pt in decrypted]
    reencrypted_provider_secrets = [
        (pid, new_encryptor.encrypt(json.dumps(secrets_dict)))
        for pid, secrets_dict in decrypted_provider_secrets
    ]
    reencrypted_mcps = [
        (sid, new_encryptor.encrypt(json.dumps(secrets_dict)))
        for sid, secrets_dict in decrypted_mcps
    ]
    reencrypted_connectors = [
        (aid, new_encryptor.encrypt(json.dumps(secrets_dict)))
        for aid, secrets_dict in decrypted_connectors
    ]
    reencrypted_agents = [
        (
            name,
            _encrypt_overrides_column(new_encryptor, tool_overrides),
            _encrypt_overrides_column(new_encryptor, mcp_overrides),
        )
        for name, tool_overrides, mcp_overrides in decrypted_agents
    ]

    # 4. Write all rows in a single transaction and commit. If anything in
    #    this block raises, roll the transaction back so the connection
    #    cache does not surface uncommitted ciphertext encrypted with the
    #    new (not-yet-on-disk) key. The key file is untouched at this
    #    point, so re-raising leaves the system fully recoverable. The
    #    single commit() covers ALL FIVE surfaces (llm_providers.api_key,
    #    llm_providers.secrets, mcp_sources.secrets, connectors.secrets,
    #    agents.tool_overrides / agents.mcp_overrides) — a failure in any
    #    UPDATE loop rolls back all of them atomically.
    try:
        for pid, ct in reencrypted:
            await conn.execute(
                "UPDATE llm_providers SET api_key = ? WHERE id = ?",
                (ct, pid),
            )
        for pid, ct in reencrypted_provider_secrets:
            await conn.execute(
                "UPDATE llm_providers SET secrets = ? WHERE id = ?",
                (ct, pid),
            )
        for sid, ct in reencrypted_mcps:
            await conn.execute(
                "UPDATE mcp_sources SET secrets = ? WHERE id = ?",
                (ct, sid),
            )
        for aid, ct in reencrypted_connectors:
            await conn.execute(
                "UPDATE connectors SET secrets = ? WHERE id = ?",
                (ct, aid),
            )
        for agent_name, tool_ct, mcp_ct in reencrypted_agents:
            await conn.execute(
                "UPDATE agents SET tool_overrides = ?, mcp_overrides = ? WHERE name = ?",
                (tool_ct, mcp_ct, agent_name),
            )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    # 4b. Evict warm connector pool entries so the next acquire reloads
    #     credentials decrypted under the new key. Lives OUTSIDE the
    #     commit try/except (Flight 2 Design Decision): the DB is already
    #     in the new-key state; refusing to replace the on-disk key file
    #     because eviction failed would leave the DB unreadable on the
    #     next process restart. Worst case "eviction failed, key file
    #     replaced" is that warm entries serve stale credentials until
    #     idle-TTL elapses — exactly the pre-F1-debrief baseline.
    #
    #     Failure mode: log + continue. Eviction is idempotent and
    #     self-bounded (per-entry 10s timeout in `_evict`).
    from the_one.connectors._pool import _evict_all_for_account

    for aid, _ in decrypted_connectors:
        try:
            await _evict_all_for_account(aid)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "rotation: connector pool eviction for account %r failed; "
                "continuing on-disk key replace. Warm entries (if any) "
                "will serve stale credentials until idle-TTL elapses.",
                aid,
            )

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

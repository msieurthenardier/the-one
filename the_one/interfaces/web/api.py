"""REST API routes for agents, knowledge bases, MCP sources, and chat sessions."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiosqlite
import httpx
import httpx2
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, StrictBool, ValidationError

from the_one import __version__, time_zones
from the_one.api_credential import LocalApiCredential
from the_one.config import settings
from the_one.connectors import registry as connector_registry
from the_one.connectors.base import ConnectorClientError, DoctorReport, InboundEnvelope
from the_one.connectors.manager import PAIRING_TTL_SECONDS
from the_one.connectors.manager import get_manager as get_connector_manager
from the_one.db._kb_types import KBItemTransitionError
from the_one.db._notes import (
    NOTE_MAX_CHARS,
    NOTE_WRITES_PER_TURN,
    NOTES_TOTAL_MAX_CHARS,
    NoteDuplicateError,
    NoteLimitError,
    parse_notes_block,
    render_note_line_text,
)
from the_one.db._provider_types import PROVIDER_TYPE_LABELS
from the_one.db._rules import (
    RULE_MAX_CHARS,
    RULES_TOTAL_MAX_CHARS,
    RuleLimitError,
    RuleOrderError,
)
from the_one.db._write_lock import write_transaction
from the_one.db.connection import get_connection
from the_one.db.encryption_corpora import count_items_with_secrets, gather_corpora
from the_one.db.models import (
    ChatSession,
    Connector,
    KBItem,
    KnowledgeBase,
    LLMProviderConfig,
    MCPSource,
    ToolConfig,
    now_iso,
)
from the_one.db.repositories import (
    AgentExternalCredentialRepository,
    AgentMcpToolCacheRepository,
    AgentNoteRepository,
    AgentRevisionRepository,
    AgentRuleRepository,
    AppMetadataRepository,
    ChatSessionRepository,
    ConnectorDirectoryRepository,
    ConnectorRepository,
    KBChunkRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
    _encrypt_overrides_column,
    _encrypt_secrets_blob,
)
from the_one.embeddings import get_embedding_backend
from the_one.embeddings import schedule_warm_up as _schedule_embedding_warm_up
from the_one.encryption import Encryptor, get_encryptor, next_key_path
from the_one.interfaces.web.middleware import CALLER_SCOPE_KEY
from the_one.knowledge.extractors import ExtractionError, extractor_for
from the_one.knowledge.indexer import MAX_FILE_BYTES
from the_one.knowledge.manager import get_manager as get_indexing_manager
from the_one.knowledge.retrieval import search as kb_search
from the_one.knowledge.settings import (
    ChunkingSettings,
    EmbeddingSettings,
    KnowledgeSettings,
    MonitoringSettings,
    load_knowledge_settings,
    load_vector_store_settings,
    save_knowledge_settings,
    walk_skip_counters_key,
)
from the_one.knowledge.walk import content_hash, is_filesystem_root
from the_one.knowledge.watcher import get_manager as get_watch_manager
from the_one.llm import anthropic_oauth, ollama_api, ollama_library, plan_credentials
from the_one.mcp._era import forget_era
from the_one.mcp._overrides import MCP_OVERRIDE_CREDENTIAL_KEYS, configured_names, missing_values
from the_one.mcp.override_validation import carries_credentials, validate_mcp_overrides
from the_one.naming import (
    NAME_CONFLICT_AGENT,
    SAME_AS_CURRENT,
    NameRuleError,
    check_name,
    name_rule_detail,
)
from the_one.platform.paths import canonicalize, is_within
from the_one.platform.sandbox import factory as sandbox_factory
from the_one.routines import service as routine_service
from the_one.routines.proposals import RoutineProposalRepository
from the_one.routines.repository import RoutineRunRepository
from the_one.self_configuration import external_credentials as self_configuration_external
from the_one.self_configuration import manage as self_configuration_manage
from the_one.self_configuration.constants import EXTERNAL_CREDENTIAL_PREFIX, SURFACE_TOOL_PREFIX
from the_one.sessions import is_session_busy, turn_seq
from the_one.tools import override_validation
from the_one.vectors import get_vector_store

if TYPE_CHECKING:
    # `AgentConfig` is intentionally NOT imported at module load time —
    # every handler that needs it does a function-local import to avoid
    # a load-time cycle (see the lazy-import precedent throughout the
    # Agents section below). This TYPE_CHECKING-only import exists
    # purely so `_agent_response`'s parameter annotation resolves for
    # static analysis; it has zero runtime effect (never executes).
    from the_one.agent.config import AgentConfig

router = APIRouter(prefix="/api")


async def _read_json(request: Request) -> Any:
    """Parse the request body as a JSON object; anything else is a 422, never a 500.

    Malformed JSON (squawk 0184) and valid JSON that is not an object (`[]`, `5`,
    `"x"`, `null`; squawk 0186) both get one plain sentence that never echoes the
    body. Every caller expects an object.
    """
    try:
        data = await request.json()
    except ValueError:  # json.JSONDecodeError and UnicodeDecodeError both subclass it
        raise HTTPException(status_code=422, detail="Request body is not valid JSON.") from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    return data


logger = logging.getLogger(__name__)

# Streamable-HTTP servers may enforce content negotiation (406 otherwise); the
# SDK transport and the connection probe send this same Accept value.
_MCP_POST_ACCEPT = "application/json, text/event-stream"


def _oauth_driver_headers(version: str) -> dict[str, str]:
    """Headers for the OAuth flow drivers' raw MCP POST (squawk 0202)."""
    return {"MCP-Protocol-Version": version, "Accept": _MCP_POST_ACCEPT}


"""Module-level logger.

M11 F9 L5 — added as a required side-effect of the leg. ``api.py``
previously lacked a module-level ``logger``; some functions defined
their own local ``_log`` (see :func:`delete_mcp_source` at the comment
block citing the uvicorn-root-logger-threshold precedent). The
module-level handle is the convention everywhere else in ``the_one/``;
new endpoints log through it directly.
"""


# ── Helpers ───────────────────────────────────────────────────────────────


def _validation_detail(e: ValidationError) -> list[dict]:
    """The one 422 body for a pydantic ``ValidationError``.

    ``include_context=False``: ``ctx`` may hold a raw exception (not JSON-serializable).
    ``include_input=False``: ``input`` echoes the submitted value, secrets included.
    """
    return e.errors(include_context=False, include_input=False)


def _checked_name(value: object) -> str:
    """The trimmed name, or a list-shaped 422 on ``loc ["name"]`` (sortie 06 DD4, DD5)."""
    try:
        return check_name(value)
    except NameRuleError as e:
        raise HTTPException(status_code=422, detail=name_rule_detail(e.message))


def _name_conflict_detail(message: str) -> list[dict]:
    return [{"type": "name_conflict", "loc": ["name"], "msg": message}]


async def _agent_store() -> SQLiteAgentStore:
    conn = await get_connection()
    # M21 F01 L01: pass the encryptor explicitly (rather than relying on
    # the constructor's default) so the api-module `get_encryptor` patch
    # test fixtures already install governs it — mirrors `_mcp_repo()` /
    # `_tool_config_repo()` above.
    return SQLiteAgentStore(conn, get_encryptor(settings.data_dir))


async def _secret_repo() -> SecretRepository:
    """The Library secrets repository (sortie 10); the encryptor is the app's reference."""
    return SecretRepository(await get_connection(), get_encryptor(settings.data_dir))


async def _validate_secret_grants(stored: list[str], cfg: AgentConfig) -> None:
    """422 on ``["secret_ids", i]`` for a granted id that is new relative to ``stored`` and
    not a Library secret (sortie 10, DD2). Stored ids are not re-checked."""
    fresh = [(i, s) for i, s in enumerate(cfg.secret_ids) if s not in stored]
    if not fresh:
        return
    found = await (await _secret_repo()).exists_many(s for _, s in fresh)
    missing = [
        {"type": "value_error", "loc": ["secret_ids", i], "msg": "This secret doesn't exist."}
        for i, s in fresh
        if s not in found
    ]
    if missing:
        raise HTTPException(status_code=422, detail=missing)


def _agent_response(
    cfg: AgentConfig,
    kb_tool_names: dict[str, str] | None = None,
    notices: list[dict[str, Any]] | None = None,
    mcp_tool_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
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

    ``kb_tool_names`` (L2-D5, AC-6): ``_agent_response`` is synchronous
    and takes only the config, but resolving each attached knowledge
    base's derived tool name needs an async repository read — so callers
    that want the field resolve it themselves (via
    :func:`_resolve_kb_tool_names`) and pass the finished ``{kb_id:
    tool_name}`` map in. Left ``None`` (the default), the response has no
    ``kb_tool_names`` key at all — this is what ``list_agents`` relies on
    to avoid an N+1 read per page load; only the single-agent routes
    (``GET``/``POST``/``PUT /api/agents/{name}``, ``.../rename``) pass one.

    ``notices`` (sortie 07 DD6): the derived tool-override clip notices, always
    emitted as a list (empty when none) on every route; callers compute them with
    :func:`_agent_notices` off the event loop.
    """
    data = cfg.model_dump()
    data["notices"] = list(notices or [])
    if kb_tool_names is not None:
        data["kb_tool_names"] = kb_tool_names
    if mcp_tool_cache is not None:
        # Sortie 09 DD5: additive, single-agent routes only (like `kb_tool_names`):
        # {source_id: {tools, fetched_at}} for the attached sources where the agent
        # uses its own credentials and a per-agent row exists. Tool metadata only.
        data["mcp_tool_cache"] = mcp_tool_cache
    overrides = data.get("mcp_overrides")
    if overrides:
        for source_entry in overrides.values():
            if not isinstance(source_entry, dict):
                continue
            # Sortie 09 L05: values of names the operator marked non-sensitive are
            # returned in clear (headers ignoring case, env exactly). `bearer_token`
            # and an `Authorization` header are never unmasked.
            plain = source_entry.get("plain_names")
            plain_names = (
                {n for n in plain if isinstance(n, str)} if isinstance(plain, list) else set()
            )
            plain_folded = {n.strip().lower() for n in plain_names}
            for key in MCP_OVERRIDE_CREDENTIAL_KEYS:
                if key not in source_entry or not source_entry[key]:
                    continue
                value = source_entry[key]
                if isinstance(value, str):
                    source_entry[key] = _mask_secret_value(value)
                elif isinstance(value, dict):
                    if key == "headers":

                        def _is_plain(k: Any) -> bool:
                            if not isinstance(k, str):
                                return False
                            folded = k.strip().lower()
                            return folded != "authorization" and folded in plain_folded

                    elif key == "env":

                        def _is_plain(k: Any) -> bool:
                            return k in plain_names

                    else:

                        def _is_plain(k: Any) -> bool:
                            return False

                    source_entry[key] = {
                        k: (v if _is_plain(k) else _mask_secret_value(v)) for k, v in value.items()
                    }
                else:
                    source_entry[key] = _MASK_PREFIX
    return data


async def _tool_config_rows(*cfgs: AgentConfig) -> dict[str, Any]:
    """The tool-config rows by tool name: ONE ``ToolConfigRepository.list()`` per
    request, and none when no config carries a tool override."""
    if not any(c.tool_overrides for c in cfgs):
        return {}
    repo = await _tool_config_repo()
    return override_validation.rows_by_name(await repo.list())


async def _agent_notices(cfgs: list[AgentConfig], rows: dict[str, Any]) -> list[list[dict]]:
    """The tool-override notices for each config, in one thread hop (path
    canonicalisation blocks), and none at all when no config has an override."""
    if not any(c.tool_overrides for c in cfgs):
        return [[] for _ in cfgs]
    return await asyncio.to_thread(override_validation.compute_notices_for_many, cfgs, rows)


async def _validate_tool_overrides(
    stored: dict[str, Any] | None, cfg: AgentConfig, rows: dict[str, Any]
) -> None:
    """422 (sortie 07 DD5) on a new or changed override that widens the app-wide
    value or is invalid. ``stored`` is the stored map, ``None`` on create."""
    if not cfg.tool_overrides:
        return
    details = await asyncio.to_thread(
        override_validation.validate_overrides, stored, cfg.tool_overrides, rows
    )
    if details:
        raise HTTPException(status_code=422, detail=details)


async def _full_agent_response(cfg: AgentConfig, rows: dict[str, Any] | None = None) -> dict:
    """A single-agent response: kb tool names plus the derived notices."""
    if rows is None:
        rows = await _tool_config_rows(cfg)
    (notices,) = await _agent_notices([cfg], rows)
    return _agent_response(
        cfg, await _resolve_kb_tool_names(cfg), notices, await _resolve_mcp_tool_cache(cfg)
    )


async def _resolve_mcp_tool_cache(cfg: AgentConfig) -> dict[str, dict[str, Any]]:
    """Sortie 09 DD5: ``{source_id: {tools, fetched_at}}`` of the agent's per-agent
    tool lists for the attached sources where it uses its own credentials. One read
    when the agent has overrides and attachments; none otherwise."""
    if not cfg.mcp_source_ids or not cfg.mcp_overrides:
        return {}
    from the_one.mcp._overrides import has_credential_override
    from the_one.self_configuration.constants import override_for

    cache = await AgentMcpToolCacheRepository(await get_connection()).get_for_agent(cfg.name)
    if not cache:
        return {}
    repo = await _mcp_repo()
    out: dict[str, dict[str, Any]] = {}
    for source_id in cfg.mcp_source_ids:
        row = cache.get(source_id)
        if row is None:
            continue
        try:
            source = await repo.get(source_id)
        except KeyError:
            continue
        if has_credential_override(override_for(cfg.mcp_overrides, source), source):
            out[source_id] = row
    return out


async def _normalize_surface_fields(
    data: dict[str, Any],
    name: str,
    stored_ids: list[str],
    *,
    mcp_repo: MCPSourceRepository,
) -> None:
    """Sortie 08: the self-configuration server is owned by the server, not
    the agent form. Runs on the RAW body of ``create_agent`` / ``update_agent``
    (before the credential merge and validation), in this order:

    - DD3: ``mcp_overrides["self-configuration"]`` with anything in it is a
      422 (an empty dict or null is dropped); checked on the raw body so a
      Save that merely omits the key (while one is stored) is not refused.
    - DD7: ``mcp__self-configuration__*`` entries are stripped from a
      ``disabled_tools`` list (silently: Studio re-sends stored names).
    - DD2: the agent's own surface row id never comes from the body; the
      stored one is carried back at its stored position. An omitted
      ``mcp_source_ids`` is carried the same way (the other ids still reset).
    """
    overrides = data.get("mcp_overrides")
    if isinstance(overrides, dict) and self_configuration_manage.SURFACE_ROW_NAME in overrides:
        entry = overrides[self_configuration_manage.SURFACE_ROW_NAME]
        if entry is not None and entry != {}:
            raise HTTPException(
                status_code=422, detail=self_configuration_manage.SURFACE_OVERRIDE_REFUSAL
            )
        data["mcp_overrides"] = {
            k: v for k, v in overrides.items() if k != self_configuration_manage.SURFACE_ROW_NAME
        }
    disabled = data.get("disabled_tools")
    if isinstance(disabled, list):
        data["disabled_tools"] = [
            t for t in disabled if not (isinstance(t, str) and t.startswith(SURFACE_TOOL_PREFIX))
        ]
    if "mcp_source_ids" not in data:
        incoming_ids: Any = []
    else:
        incoming_ids = data["mcp_source_ids"]
    if isinstance(incoming_ids, list) and all(isinstance(i, str) for i in incoming_ids):
        data["mcp_source_ids"] = await self_configuration_manage.carry_surface_attachment(
            name, incoming_ids, stored_ids, mcp_repo=mcp_repo
        )


async def _validate_mcp_override_credentials(
    data: dict[str, Any], mcp_repo: MCPSourceRepository
) -> None:
    """Sortie 09 DD2: 422 (one list, the sortie 07 shape) on a refused per-agent
    credential in the RAW body, before the credential merge. The source list is
    read only when the body carries a credential key."""
    incoming = data.get("mcp_overrides")
    if not carries_credentials(incoming):
        return
    sources = {s.name: s for s in await mcp_repo.list()}
    details = validate_mcp_overrides(incoming, sources, _looks_masked)
    if details:
        raise HTTPException(status_code=422, detail=details)


def _credential_view(overrides: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """``{source name: {credential key: value}}`` for the non-empty credential keys
    of an ``mcp_overrides`` map (the part a change of which needs a new connection)."""
    out: dict[str, dict[str, Any]] = {}
    for source_name, entry in (overrides or {}).items():
        if not isinstance(entry, dict):
            continue
        view = {
            k: entry[k] for k in MCP_OVERRIDE_CREDENTIAL_KEYS if entry.get(k) not in (None, {}, "")
        }
        if view:
            out[source_name] = view
    return out


async def _evict_changed_mcp_credentials(
    agent_name: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    mcp_repo: MCPSourceRepository,
) -> None:
    """Sortie 09 DD7: after an agent write commits, evict the pool entry of every
    source whose credentials (``headers``/``env``/``bearer_token``) differ between
    ``before`` and ``after``, so the agent's next connection uses the new values.
    No eviction when nothing credential-related changed. The agent's per-agent tool
    cache row for each such source is deleted too (DD5/DD7). Never raises."""
    old_view, new_view = _credential_view(before), _credential_view(after)
    changed = {n for n in old_view.keys() | new_view.keys() if old_view.get(n) != new_view.get(n)}
    if not changed:
        return
    from the_one.mcp._pool import _evict

    try:
        cache_repo = AgentMcpToolCacheRepository(mcp_repo.conn)
        for source in await mcp_repo.list():
            if source.name in changed:
                await _evict((agent_name, source.id))
                await cache_repo.delete(agent_name, source.id)
    except Exception:
        logger.warning("could not evict MCP connections for agent %r", agent_name, exc_info=False)


async def _drop_source_agent_tool_cache(mcp_repo: MCPSourceRepository, source_id: str) -> None:
    """Sortie 09 DD5/DD7: delete every agent's per-agent tool cache row for a source
    whose connection basis changed (Library edit, Reset connection). Never raises."""
    try:
        await AgentMcpToolCacheRepository(mcp_repo.conn).delete_for_source(source_id)
    except Exception:
        logger.warning("could not clear agent tool lists for %r", source_id, exc_info=False)


async def _evict_agent_connections(agent_name: str) -> None:
    """Sortie 09 DD7: evict every pool entry under ``agent_name`` (rename, delete).
    Never raises."""
    from the_one.mcp._pool import _evict_all_for_agent

    try:
        await _evict_all_for_agent(agent_name)
    except Exception:
        logger.warning("could not evict MCP connections for agent %r", agent_name, exc_info=False)


def _drop_surface_override(merged: Any) -> Any:
    """Sortie 08 AC7: after the credential merge re-injects a stored entry,
    remove the surface's key; ``None`` (not ``{}``) when the map is empty."""
    if not isinstance(merged, dict):
        return merged
    kept = {k: v for k, v in merged.items() if k != self_configuration_manage.SURFACE_ROW_NAME}
    return kept or None


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
        # Sortie 09 L05: `plain_names` follows the same omitted-keeps / null-clears /
        # list-replaces rule, then is pruned to names that still have a value. This
        # runs before the empty-entry check so a leftover list alone keeps nothing alive.
        if "plain_names" in incoming_entry:
            plain = incoming_entry["plain_names"]
        else:
            plain = stored_entry.get("plain_names")
        resolved_entry.pop("plain_names", None)
        pruned = _prune_plain_names(plain, resolved_entry)
        if pruned:
            resolved_entry["plain_names"] = pruned
        if resolved_entry:
            merged[source_name] = resolved_entry
    return merged or None


def _prune_plain_names(plain: Any, entry: dict[str, Any]) -> list[str]:
    """The names of ``plain`` that still have a value in ``entry``'s ``headers``
    (matched ignoring case) or ``env`` (exact), in the merged dict's order, once each.
    Robust to a non-list or non-string ``plain`` (returns what is usable)."""
    if not isinstance(plain, list):
        return []
    wanted = {n for n in plain if isinstance(n, str)}
    if not wanted:
        return []
    wanted_folded = {n.strip().lower() for n in wanted}
    out: list[str] = []
    headers = entry.get("headers")
    if isinstance(headers, dict):
        for name in headers:
            if isinstance(name, str) and name.strip().lower() in wanted_folded and name not in out:
                out.append(name)
    env = entry.get("env")
    if isinstance(env, dict):
        for name in env:
            if isinstance(name, str) and name in wanted and name not in out:
                out.append(name)
    return out


async def _kb_repo() -> KnowledgeBaseRepository:
    conn = await get_connection()
    return KnowledgeBaseRepository(conn)


async def _resolve_kb_tool_names(cfg: AgentConfig) -> dict[str, str]:
    """Resolve ``{kb_id: tool_name}`` for ``cfg.kb_ids`` (L2-D5, AC-6).

    Mirrors ``KBToolProvider.get_tools_for_agent``'s own resolution
    exactly: ``repo.get(kb_id)`` per id, skipping a ``KeyError`` with a
    WARNING naming the agent and the dangling id (DD-14) — so a dangling
    id contributes no entry and never makes the whole response fail.
    Empty ``kb_ids`` short-circuits to ``{}`` with no database call, same
    as the tool provider's own fast path.
    """
    if not cfg.kb_ids:
        return {}
    from the_one.knowledge.tool_provider import compute_tool_names

    repo = await _kb_repo()
    kbs: list[KnowledgeBase] = []
    for kb_id in cfg.kb_ids:
        try:
            kbs.append(await repo.get(kb_id))
        except KeyError:
            logger.warning(
                "agent %r references deleted knowledge base %r; "
                "kb_tool_names will have no entry for it",
                cfg.name,
                kb_id,
            )
    if not kbs:
        return {}
    return compute_tool_names(kbs, agent_name=cfg.name)


async def _kb_item_repo() -> KBItemRepository:
    conn = await get_connection()
    return KBItemRepository(conn)


async def _kb_chunk_repo() -> KBChunkRepository:
    conn = await get_connection()
    return KBChunkRepository(conn)


async def _app_metadata_repo() -> AppMetadataRepository:
    conn = await get_connection()
    return AppMetadataRepository(conn)


async def _vector_store():
    """The process-wide vector store (Flight 2 Leg 4). A thin named
    wrapper around ``get_vector_store()`` — the delete routes' recording-
    stub tests monkeypatch the dispatcher's own ``_build_store`` seam, not
    this helper, so it stays a plain pass-through."""
    return await get_vector_store()


async def _mcp_repo() -> MCPSourceRepository:
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    return MCPSourceRepository(conn, encryptor)


async def _connector_repo() -> ConnectorRepository:
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    return ConnectorRepository(conn, encryptor)


async def _connector_directory_repo() -> ConnectorDirectoryRepository:
    conn = await get_connection()
    return ConnectorDirectoryRepository(conn)


async def _chat_repo() -> ChatSessionRepository:
    conn = await get_connection()
    return ChatSessionRepository(conn)


async def _agent_revisions_repo() -> AgentRevisionRepository:
    # M21 F02 L02: no encryptor — the revision log holds plaintext
    # description/system_prompt values.
    conn = await get_connection()
    return AgentRevisionRepository(conn)


async def _agent_rules_repo() -> AgentRuleRepository:
    # M27 F1: plaintext operator-authored rules, no encryptor.
    conn = await get_connection()
    return AgentRuleRepository(conn)


async def _agent_notes_repo() -> AgentNoteRepository:
    # M27 F2: plaintext notes, no encryptor.
    conn = await get_connection()
    return AgentNoteRepository(conn)


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

    Also materialises `default` for every property whose field uses
    `default_factory` (squawk 0248). Pydantic omits `default` from
    `model_json_schema()` for a factory field, so the editors' fallback
    (`prop['default']` for a never-saved tool) read `undefined` and a Save
    stored `[]` in place of the built-in denylist. The factory is called
    directly (never `config_class()`, whose `model_post_init` may add
    runtime-only entries such as the app's secrets directory) and the
    value is converted to JSON-safe form.

    Assumes a flat schema (no nested BaseModel fields under `$defs`).
    All four F2-F5 Configs (FilesystemConfig, ExecutionConfig,
    PythonExecConfig, WebConfig) are flat. A future Config that
    nests another BaseModel will need a `$defs` walk added here.
    """
    from pydantic_core import to_jsonable_python

    from the_one.tools.resolver import (
        Narrow,
        NarrowAnyWhenEmpty,
        NarrowPrefix,
        NarrowSuperset,
        Substitute,
    )

    marker_map = {
        Narrow: "Narrow",
        NarrowAnyWhenEmpty: "NarrowAnyWhenEmpty",
        NarrowPrefix: "NarrowPrefix",
        NarrowSuperset: "NarrowSuperset",
        Substitute: "Substitute",
    }
    properties = schema.get("properties") or {}
    for field_name, field_info in config_class.model_fields.items():
        prop = properties.get(field_name)
        if prop is None:
            continue
        if "default" not in prop and field_info.default_factory is not None:
            prop["default"] = to_jsonable_python(
                field_info.get_default(call_default_factory=True, validated_data={})
            )
        for marker_cls, marker_name in marker_map.items():
            if any(m is marker_cls for m in field_info.metadata):
                prop["x_marker"] = marker_name
                break
    return schema


def _hidden_field_names(tool_cls: type, config_cls: type) -> set[str]:
    """Config fields the tool's ``config_fields`` leaves out of its editor
    (M31 F4 L05a, B6). Empty when ``config_fields`` is ``None`` (all shown).
    One copy, shared with the agent-tab render predicate."""
    return override_validation.hidden_field_names(tool_cls, config_cls)


def _filter_schema_to_config_fields(schema: dict[str, Any], tool_cls: type) -> dict[str, Any]:
    """Drop the properties a tool does not read from the served schema (and
    from ``required``). Display-only: storage and validation still accept
    every field. Mutates ``schema`` and returns it."""
    hidden = _hidden_field_names(tool_cls, tool_cls.Config)
    if not hidden:
        return schema
    props = schema.get("properties")
    if isinstance(props, dict):
        schema["properties"] = {k: v for k, v in props.items() if k not in hidden}
    if "required" in schema:
        kept = [k for k in schema["required"] if k not in hidden]
        if kept:
            schema["required"] = kept
        else:
            del schema["required"]
    return schema


def _merge_hidden_fields(
    config_cls: type,
    tool_cls: type,
    incoming: Any,
    stored: dict[str, Any],
) -> Any:
    """The body a tools PUT validates: ``incoming`` with every hidden field
    (see ``Tool.config_fields``) replaced by its stored value.

    A hidden field is not shown, so the form cannot have meant to change it and
    the stored value always wins over an incoming one. A hidden field with no
    stored value is left out (the Config default applies). ``stored`` is the
    saved config merged with the decrypted secrets. A non-dict ``incoming`` is
    returned unchanged (validation rejects it).
    """
    hidden = _hidden_field_names(tool_cls, config_cls)
    if not hidden or not isinstance(incoming, dict):
        return incoming
    merged = {k: v for k, v in incoming.items() if k not in hidden}
    for field in hidden:
        if field in stored:
            merged[field] = stored[field]
    return merged


# ── Client config ─────────────────────────────────────────────────────────


async def read_execution_sandbox() -> str:
    """The sandbox backend name Shell and Python use on this host
    (``"bubblewrap"`` or ``"passthrough"``). The selection can run a blocking
    probe (up to 5 s the first time), so it always runs in a worker thread."""
    name, _reason = await asyncio.to_thread(sandbox_factory.describe_selection)
    return name


@router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    """Client-visible configuration — dev mode flag, version, and the
    context-fullness overlay thresholds.

    Fetched once at boot by the JS client (app.js DOMContentLoaded
    handler) and cached on window.App.config. The dev_mode flag gates
    the dev-mode-only Design Language Admin category (Mission 08 F2).
    ``context_warn_pct`` / ``context_crit_pct`` (M16 F08 L05) are read by
    the chat telemetry overlay to color the bar and emit its non-color a11y
    signal; the settings validator guarantees they are always sane here.
    ``execution_sandbox`` (sortie 07, DD10) is the sandbox posture the agent
    tab's paths note reads. It is cached on this app instance by a lifespan
    warm-up, never in a module variable (the factory re-evaluates on every call
    so tests can monkeypatch it); a request that arrives before the warm-up
    finishes reads it in a worker thread itself.
    """
    posture = getattr(request.app.state, "execution_sandbox", None)
    if posture is None:
        posture = await read_execution_sandbox()
    return {
        "dev_mode": settings.dev_mode,
        "version": __version__,
        "context_warn_pct": settings.context_warn_pct,
        "context_crit_pct": settings.context_crit_pct,
        "execution_sandbox": posture,
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
                "summary": cls.summary,
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
    schema = _filter_schema_to_config_fields(schema, cls)
    return {
        "name": name,
        "description": cls.description,
        "summary": cls.summary,
        "enabled": enabled,
        "config": config,
        "schema": schema,
    }


def _compute_tool_config_update(
    cls: type, name: str, data: dict[str, Any], existing: Any
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """What a tools PUT would store: ``(new_enabled, new_config, new_secrets)``.

    One computation shared by the PUT and the impact preview (sortie 07 L05, DD8), so
    the preview equals what the PUT stores. ``existing`` is the stored
    ``ToolConfig`` row or ``None``. A body that fails validation raises the PUT's
    422 (``HTTPException``); when ``config`` is omitted the stored config and
    secrets come back unchanged.
    """
    if existing is not None:
        current_enabled = existing.enabled
        current_config = existing.config
        current_secrets = existing.secrets
    else:
        current_enabled = True
        current_config = {}
        current_secrets = {}

    secret_fields = _secret_field_names(cls.Config)

    # `enabled` — preserve when omitted from body; coerce when present.
    new_enabled = bool(data["enabled"]) if "enabled" in data else current_enabled

    # `config` — REPLACE when present (validate body), preserve when omitted.
    if "config" in data:
        stored = {**current_config, **current_secrets}
        merged = _merge_hidden_fields(cls.Config, cls, data["config"], stored)
        try:
            try:
                validated = cls.Config.model_validate(merged)
            except ValidationError:
                # A stored value for a hidden field may no longer validate (a
                # constraint tightened since it was saved). Retry without the
                # stored hidden values so the Config defaults apply; if that
                # also fails the operator's visible edit is at fault.
                fallback = _merge_hidden_fields(cls.Config, cls, data["config"], {})
                if fallback == merged:
                    raise
                validated = cls.Config.model_validate(fallback)
                logger.warning(
                    "tool %r: a stored value for a hidden setting no longer validated; "
                    "using the default",
                    name,
                )
        except ValidationError as e:
            # `e.errors()` may carry a raw exception in `ctx['error']` (Pydantic
            # v2 model-validator path) which is NOT JSON-serializable. Pass
            # `include_context=False` so the response stays JSON-encodable —
            # `msg` + `loc` carry the human-readable diagnostic the L3 form
            # surfaces inline. Discovered during F6 L6 HAT scenario 3 when an
            # operator narrowed `timeout_seconds_max < timeout_seconds_default`
            # and the resulting model-validator ValueError crashed the JSON
            # encoder, surfacing as 500 instead of 422.
            raise HTTPException(status_code=422, detail=_validation_detail(e))
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
    return new_enabled, new_config, new_secrets


def _narrowing_added(before: list[dict], after: list[dict]) -> list[dict]:
    """The fields in ``after`` whose notice is new or gained a dropped value."""
    prior = {n["field"]: n for n in before}
    out: list[dict] = []
    for n in after:
        old = prior.get(n["field"])
        if old is None or any(d not in old["dropped"] for d in n["dropped"]):
            out.append(
                {"field": n["field"], "field_title": n["field_title"], "dropped": n["dropped"]}
            )
    return out


def _impact_of(name: str, cfgs: list[AgentConfig], rows: dict[str, Any], proposed: Any) -> list:
    """Blocking (path canonicalisation): per agent, the narrowing ``proposed`` adds."""
    after_rows = {**rows, name: proposed}
    impact = []
    for cfg in cfgs:
        before = [n for n in override_validation.compute_notices(cfg, rows) if n["tool"] == name]
        after = [
            n for n in override_validation.compute_notices(cfg, after_rows) if n["tool"] == name
        ]
        fields = _narrowing_added(before, after)
        if fields:
            impact.append({"agent": cfg.name, "fields": fields})
    return impact


@router.post("/tools/configs/{name}/impact")
async def tool_config_impact(name: str, request: Request) -> dict[str, Any]:
    """Which agents a proposed tool config would newly narrow (sortie 07 L05, DD8).

    Read-only. The body is the PUT's shape; it goes through the PUT's own
    computation (``_compute_tool_config_update``), so an invalid body gets the
    PUT's 422 and the preview equals what a following PUT stores. The response is
    ``{"agents": [{"agent", "fields": [{"field", "field_title", "dropped"}]}]}``:
    an agent is listed only for a field whose notice for this tool is new or gained
    a dropped value. A widening, a no-op and a tool turned off list nothing.
    """
    from the_one.tools.builtins import _TOOL_CLASSES

    cls = _TOOL_CLASSES.get(name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    data = await _read_json(request)
    repo = await _tool_config_repo()
    rows = override_validation.rows_by_name(await repo.list())
    existing = rows.get(name)
    new_enabled, new_config, new_secrets = _compute_tool_config_update(cls, name, data, existing)
    update = {"enabled": new_enabled, "config": new_config, "secrets": new_secrets}
    if existing is not None:
        proposed = existing.model_copy(update=update)
    else:
        proposed = ToolConfig(name=name).model_copy(update=update)
    store = await _agent_store()
    cfgs = [await store.load(n) for n in await store.list_agents()]
    if not any(c.tool_overrides and name in c.tool_overrides for c in cfgs):
        return {"agents": []}
    return {"agents": await asyncio.to_thread(_impact_of, name, cfgs, rows, proposed)}


@router.put("/tools/configs/{name}")
async def upsert_tool_config(name: str, request: Request) -> dict[str, Any]:
    """Upsert the operator-saved config + enabled state.

    Body shape: `{enabled?: bool, config?: dict}`.

    REPLACE-not-merge contract for `config`: when present in body,
    REPLACES the saved config wholesale (REST PUT convention). The
    L3 form always submits the full Config state, so REPLACE matches
    its actual behaviour. To wipe to defaults, send `{"config": {}}`.

    The replace covers the fields the tool SHOWS. A field the tool's
    `config_fields` hides (M31 F4 L05a) keeps its stored value: a PUT, or a
    `{"config": {}}` reset, never changes it, and an incoming value for it is
    ignored (`_merge_hidden_fields`).

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
    data = await _read_json(request)
    repo = await _tool_config_repo()
    try:
        existing = await repo.get(name)
    except KeyError:
        existing = None
    secret_fields = _secret_field_names(cls.Config)
    new_enabled, new_config, new_secrets = _compute_tool_config_update(cls, name, data, existing)

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


def _test_outcome(output: str) -> str:
    """Classify a tool's Test result for the editor (M31 F4 L07d), so the browser never
    parses the model-facing string. A tool reports a policy refusal as
    ``[error] [constraint] ...`` (``ConstraintError`` in ``tools/base.py``) and any other
    failure as ``[error] ...``; anything else is a normal result.

    ``ok``      the tool returned a result.
    ``blocked`` the operator's own settings refused the request.
    ``failed``  the request failed (network, upstream, timeout, bad response).
    """
    if output.startswith("[error] [constraint]"):
        return "blocked"
    if output.startswith("[error]"):
        return "failed"
    return "ok"


@router.post("/tools/configs/{name}/test")
async def test_tool_config(name: str, request: Request) -> dict[str, Any]:
    """Run a connection test against the named tool's currently-saved
    Config (Decision 5). Only `web_search` and `fetch_url` are
    testable. Tool-side failures (constraint refusals, network
    errors) come through as `[error] [constraint] ...` strings in
    `output` — not HTTP 5xx — so the operator sees the agent's view. The response
    also carries `outcome` (`ok` | `blocked` | `failed`), computed here from that
    prefix (M31 F4 L07d) so clients never parse the string.

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
    return {"output": output, "elapsed_ms": elapsed_ms, "outcome": _test_outcome(output)}


# ── Agents ────────────────────────────────────────────────────────────────


@router.get("/agents")
async def list_agents() -> list[dict[str, Any]]:
    store = await _agent_store()
    names = await store.list_agents()
    cfgs = [await store.load(name) for name in names]
    rows = await _tool_config_rows(*cfgs)
    notices = await _agent_notices(cfgs, rows)
    return [_agent_response(cfg, None, n) for cfg, n in zip(cfgs, notices)]


@router.get("/agents/{name}")
async def get_agent(name: str) -> dict[str, Any]:
    store = await _agent_store()
    try:
        cfg = await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return await _full_agent_response(cfg)


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


async def _check_agent_provider(provider_id: str | None) -> None:
    """Squawk 0277: a provider id that names no provider is a 422 on the field, not a 500
    from the foreign key. ``None`` (no provider) stays legal; ``""`` never names one."""
    if provider_id is None:
        return
    exists = False
    if provider_id != "":
        try:
            await (await _provider_repo()).get(provider_id)
            exists = True
        except KeyError:
            exists = False
    if not exists:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["provider_config_id"],
                    "msg": "That model provider doesn't exist.",
                }
            ],
        )


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

    data = await _read_json(request)
    data["name"] = _checked_name(data.get("name"))
    # M33 F2 DD5: the Routines switches are operator-owned; a create never sets them.
    data.pop("routines_self_config_enabled", None)
    data.pop("routines_require_approval", None)
    mcp_repo = await _mcp_repo()
    # Sortie 08: the self-configuration server is server-owned (DD3 422, DD7, DD2).
    await _normalize_surface_fields(data, data["name"], [], mcp_repo=mcp_repo)
    # Sortie 09 DD2: a refused per-agent credential is a 422 on its loc.
    await _validate_mcp_override_credentials(data, mcp_repo)
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
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    # M21 F01 L02 (LD1 ownership guard): run on the VALIDATED config — an
    # agent can never attach another agent's self-configuration surface row.
    guard_error = await self_configuration_manage.reject_foreign_surface_attachments(
        cfg, mcp_repo=mcp_repo
    )
    if guard_error is not None:
        raise HTTPException(status_code=422, detail=guard_error)
    # Sortie 07 DD5: a new tool override that widens the app-wide value or is invalid
    # is a 422 on its field, before the provider check and the name conflict.
    rows = await _tool_config_rows(cfg)
    await _validate_tool_overrides(None, cfg, rows)
    await _validate_secret_grants([], cfg)
    await _check_agent_provider(cfg.provider_config_id)
    store = await _agent_store()
    if await store.exists(cfg.name):
        raise HTTPException(status_code=409, detail=_name_conflict_detail(NAME_CONFLICT_AGENT))
    await store.save(cfg)
    # Sortie 09 DD7: a re-created name may have a stale pool entry; evict what
    # carries credentials (harmless when there is none).
    await _evict_changed_mcp_credentials(cfg.name, None, cfg.mcp_overrides, mcp_repo)
    return await _full_agent_response(cfg, rows)


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
    data = await _read_json(request)
    data["name"] = name  # Ensure name matches path
    mcp_repo = await _mcp_repo()
    # Sortie 08: the self-configuration server is server-owned (DD3 422 on the
    # raw body, DD7 strip, DD2 carry of the stored attachment).
    await _normalize_surface_fields(data, name, existing.mcp_source_ids, mcp_repo=mcp_repo)
    # Sortie 09 DD2: a refused per-agent credential is a 422 on its loc.
    await _validate_mcp_override_credentials(data, mcp_repo)
    incoming_overrides = data.get("mcp_overrides")
    if incoming_overrides is None or isinstance(incoming_overrides, dict):
        # `data.get(...)` cannot distinguish "key omitted" from "key
        # explicitly null" — both decode to `None`, and AC5 treats them
        # identically (both preserve every stored source), so that
        # collapse is intentional, not a gap.
        # Sortie 08 AC7: the merge re-injects a stored surface entry the body
        # omitted; drop it so any Save cleans it.
        data["mcp_overrides"] = _drop_surface_override(
            _merge_preserved_mcp_credentials(incoming_overrides, existing.mcp_overrides)
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
    # M27 F2 DD2: the notes switch is set by its own immediate-post control;
    # an agent save that omits it must not reset it.
    if "notes_enabled" not in data:
        data["notes_enabled"] = existing.notes_enabled
    # M35 F1 DD11: the rich-visuals switch is a General-form field; a PUT that
    # omits it keeps the stored value.
    if "rich_visuals" not in data:
        data["rich_visuals"] = existing.rich_visuals
    # M33 F2 DD5: the Routines switches are set only by their own routes; an agent
    # PUT ignores any incoming value, so the response echoes the stored truth.
    data["routines_self_config_enabled"] = existing.routines_self_config_enabled
    data["routines_require_approval"] = existing.routines_require_approval
    # AC-7: `kb_ids` omitted from the PUT body preserves the stored value
    # — mirrors the `self_revision_requires_approval` preserve immediately
    # above. An explicit `kb_ids: []` is NOT an omission and still clears
    # it; omission and empty are distinguishable and mean different things.
    if "kb_ids" not in data:
        data["kb_ids"] = existing.kb_ids
    # Sortie 10 DD2: `secret_ids` follows the same rule (omitted keeps, `[]` clears).
    if "secret_ids" not in data:
        data["secret_ids"] = existing.secret_ids
    # Squawk 0223: `tool_overrides` omitted from the PUT body preserves the
    # stored map (same pattern as `kb_ids`). An explicit `null` still clears
    # it and a supplied map replaces it.
    if "tool_overrides" not in data:
        data["tool_overrides"] = existing.tool_overrides
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    # M21 F01 L02: ownership guard, on the validated config (see create_agent).
    guard_error = await self_configuration_manage.reject_foreign_surface_attachments(
        cfg, mcp_repo=mcp_repo
    )
    if guard_error is not None:
        raise HTTPException(status_code=422, detail=guard_error)
    # Sortie 07 DD5: only a new or changed override field is checked, against the
    # STORED map (an omitted `tool_overrides` was carried above, so it is unchanged).
    rows = await _tool_config_rows(cfg)
    await _validate_tool_overrides(existing.tool_overrides, cfg, rows)
    await _validate_secret_grants(existing.secret_ids, cfg)
    if cfg.provider_config_id != existing.provider_config_id:
        # Squawk 0277: only a CHANGED id is checked, so an agent whose provider was
        # deleted later stays editable (and fixable).
        await _check_agent_provider(cfg.provider_config_id)
    await store.save(cfg)
    # Sortie 09 DD7: the agent's next connection must use the new credentials.
    await _evict_changed_mcp_credentials(name, existing.mcp_overrides, cfg.mcp_overrides, mcp_repo)
    return await _full_agent_response(cfg, rows)


_TARGETED_CREDENTIAL_BODY_KEYS = frozenset({"headers", "env", "bearer_token", "plain_names"})
_TARGETED_KEPT_KEYS = ("enabled_tools", "disabled_tools")


@router.put("/agents/{name}/mcp-overrides/{source_id}/credentials")
async def update_agent_mcp_credentials(
    name: str, source_id: str, request: Request
) -> dict[str, Any]:
    """Sortie 09 L05 (DD12): save ONE source's per-agent credentials for one agent.

    The body is ``{"headers"|"env": {...} | null, "bearer_token": ... | null,
    "plain_names": [...] | null}`` in the agent PUT's write shape (an unchanged
    sensitive value is ``__MASKED__``, a removed name is left out). It is merged
    against the stored entry with the same rules as the agent PUT, and ONLY that
    source's credential keys and ``plain_names`` change: the entry's tool filters,
    every other source's entry and every other agent field are untouched. A source
    the agent does not (yet) attach is accepted (an override for it is tolerated);
    an unknown agent or source is a 404 and a self-configuration row a 422.

    Known narrow race: a whole-agent PUT that loaded the row before this route
    saved can overwrite it (both load, merge and save the whole row).
    """
    from the_one.agent.config import AgentConfig

    store = await _agent_store()
    try:
        existing = await store.load(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    mcp_repo = await _mcp_repo()
    try:
        source = await mcp_repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    if self_configuration_manage.is_surface_row(source):
        raise HTTPException(
            status_code=422,
            detail="The self-configuration server's credentials can't be set per agent.",
        )
    body = await _read_json(request)
    if not set(body) <= _TARGETED_CREDENTIAL_BODY_KEYS:
        raise HTTPException(
            status_code=422,
            detail="Only headers, env, bearer_token and plain_names can be set here.",
        )
    stored_entry = (existing.mcp_overrides or {}).get(source.name)
    kept = {
        k: stored_entry[k]
        for k in _TARGETED_KEPT_KEYS
        if isinstance(stored_entry, dict) and k in stored_entry
    }
    incoming = {source.name: {**kept, **body}}
    await _validate_mcp_override_credentials({"mcp_overrides": incoming}, mcp_repo)
    merged = _drop_surface_override(
        _merge_preserved_mcp_credentials(incoming, existing.mcp_overrides)
    )
    data = existing.model_dump()
    data["mcp_overrides"] = merged
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    await store.save(cfg)
    await _evict_changed_mcp_credentials(name, existing.mcp_overrides, cfg.mcp_overrides, mcp_repo)
    return await _full_agent_response(cfg)


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
    await _evict_agent_connections(name)
    return {"status": "ok"}


@router.post("/agents/{name}/rename")
async def rename_agent(name: str, request: Request) -> dict[str, Any]:
    """Rename an existing agent.

    The agent name is the primary key in the ``agents`` table and is
    referenced (without FK constraint, since schema v5) by
    ``chat_sessions.agent_name``. :meth:`SQLiteAgentStore.rename` handles
    both rows in a single transaction; this handler maps the store's
    exceptions to HTTP status codes.

    The new name goes through :func:`the_one.naming.check_name` (the one
    naming rule, kept off the models). The existing agent is then loaded,
    its ``name`` swapped, and re-validated against :class:`AgentConfig`.
    Name refusals are list-shaped on ``loc ["name"]``.
    """
    from the_one.agent.config import AgentConfig

    data = await _read_json(request)
    new_name = _checked_name(data.get("new_name"))
    if new_name == name:
        raise HTTPException(status_code=422, detail=name_rule_detail(SAME_AS_CURRENT))
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
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    try:
        await store.rename(name, new_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    except ValueError:
        raise HTTPException(status_code=409, detail=_name_conflict_detail(NAME_CONFLICT_AGENT))
    # M21 F01 L02 (AC11): cascade the rename onto the agent's surface row
    # (if any) — updates its ownership marker and derived name. The row's
    # id (and therefore the credential registry, keyed on source id) is
    # unaffected.
    mcp_repo = await _mcp_repo()
    await self_configuration_manage.cascade_rename(name, new_name, mcp_repo=mcp_repo)
    await _evict_agent_connections(name)
    cfg = await store.load(new_name)
    return await _full_agent_response(cfg)


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


def _caller_principal(request: Request) -> str:
    """Flight 01 Leg 2 (Q2): render the credential-gate-identified caller as
    ``source:identifier`` for a log line, or ``"-"`` when absent (a
    throwaway test app with no middleware, or a request that reached this
    route by some other means). ``ext_``/``agt_`` callers are confined to
    ``/mcp/self-configuration`` (see ``surface.py``), so in production the
    principal on these routes is always the operator credential — still
    worth logging, and free."""
    caller = request.scope.get(CALLER_SCOPE_KEY)
    if caller is None:
        return "-"
    return f"{caller.source}:{caller.identifier}"


@router.post("/agents/{name}/self-configuration/external-credentials")
async def mint_external_credential(
    name: str, body: _ExternalCredentialMintBody, request: Request
) -> dict[str, Any]:
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
    logger.info(
        "external-credential: minted %s (label=%r) for agent %r by %s",
        credential.identifier,
        body.label,
        name,
        _caller_principal(request),
    )
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
async def revoke_external_credential(
    name: str, identifier: str, request: Request
) -> dict[str, str]:
    """DD7: hard-revoke one external credential — DELETE the row and evict
    its registry entry, so the next request bearing that token is 401 with
    no restart. 404 when *identifier* is not a credential of *name*'s
    surface (cross-ID guard). Never touches the agent's own ``agt``
    credential or another external credential."""
    cred = await _external_credential_of_agent_or_404(name, identifier)
    repo = await _agent_external_credentials_repo()
    await repo.delete(identifier)
    self_configuration_external.unregister_identifier(identifier)
    logger.info(
        "external-credential: revoked %s (label=%r) for agent %r by %s",
        identifier,
        cred["label"],
        name,
        _caller_principal(request),
    )
    return {"status": "ok"}


@router.post("/agents/{name}/self-configuration/external-credentials/{identifier}/rotate")
async def rotate_external_credential(
    name: str, identifier: str, request: Request
) -> dict[str, Any]:
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
    logger.info(
        "external-credential: rotated %s -> %s (label=%r) for agent %r by %s",
        identifier,
        new_credential.identifier,
        label,
        name,
        _caller_principal(request),
    )
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


# ── Rules (M27 F1) ──────────────────────────────────────────────────────
#
# Operator-only: no agent-facing tool, MCP source or self-configuration
# capability reaches these routes. All 404 for an unknown agent; a rule id of
# another agent is a 404 too (every repository call is name-scoped).


class _RuleCreateBody(BaseModel):
    text: str
    enabled: bool = True


class _RuleUpdateBody(BaseModel):
    text: str | None = None
    enabled: bool | None = None


class _RuleOrderBody(BaseModel):
    ids: list[str]


async def _rules_body(request: Request, model: type[BaseModel]) -> Any:
    """Parse and validate a rules request body without echoing submitted text.

    Taking the body as a typed parameter would let FastAPI's default 422 echo the
    submitted ``input`` (the rule text); validating here reuses ``_validation_detail``.
    """
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(status_code=422, detail="Request body must be JSON")
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))


def _rules_limits() -> dict[str, int]:
    return {"rule_chars": RULE_MAX_CHARS, "total_chars": RULES_TOTAL_MAX_CHARS}


@router.get("/agents/{name}/rules")
async def list_agent_rules(name: str) -> dict[str, Any]:
    await _load_agent_or_404(name)
    repo = await _agent_rules_repo()
    rules = await repo.list_for_agent(name)
    return {"rules": [r.model_dump() for r in rules], "limits": _rules_limits()}


@router.post("/agents/{name}/rules", status_code=201)
async def create_agent_rule(name: str, request: Request) -> dict[str, Any]:
    body = await _rules_body(request, _RuleCreateBody)
    await _load_agent_or_404(name)
    repo = await _agent_rules_repo()
    try:
        rule = await repo.create(name, body.text, body.enabled)
    except RuleLimitError as e:
        raise HTTPException(status_code=422, detail=e.detail)
    return rule.model_dump()


@router.put("/agents/{name}/rules/order")
async def reorder_agent_rules(name: str, request: Request) -> dict[str, Any]:
    body = await _rules_body(request, _RuleOrderBody)
    await _load_agent_or_404(name)
    repo = await _agent_rules_repo()
    try:
        rules = await repo.reorder(name, body.ids)
    except RuleOrderError as e:
        raise HTTPException(status_code=422, detail=e.detail)
    return {"rules": [r.model_dump() for r in rules], "limits": _rules_limits()}


@router.put("/agents/{name}/rules/{rule_id}")
async def update_agent_rule(name: str, rule_id: str, request: Request) -> dict[str, Any]:
    body = await _rules_body(request, _RuleUpdateBody)
    await _load_agent_or_404(name)
    repo = await _agent_rules_repo()
    try:
        rule = await repo.update(name, rule_id, text=body.text, enabled=body.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    except RuleLimitError as e:
        raise HTTPException(status_code=422, detail=e.detail)
    return rule.model_dump()


@router.delete("/agents/{name}/rules/{rule_id}")
async def delete_agent_rule(name: str, rule_id: str) -> dict[str, str]:
    await _load_agent_or_404(name)
    repo = await _agent_rules_repo()
    try:
        await repo.delete(name, rule_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return {"status": "ok"}


def _poke_scheduler() -> None:
    """Delegate kept for callers that wake the scheduler (the service pokes after writes)."""
    routine_service.poke_scheduler()


# ── Notes (M27 F2) ──────────────────────────────────────────────────────
#
# Operator-only (the agent's own tools are Leg 2). All 404 for an unknown
# agent (including the synthesized `default`, which has no stored row, hence
# no notes); another agent's note id is a 404 too. A 422 never echoes note
# text. Operator edits and deletes are allowed while notes are off: the
# switch governs the agent, not the operator.


class _NotesSettingsBody(BaseModel):
    enabled: StrictBool


class _NoteUpdateBody(BaseModel):
    text: str


def _notes_limits() -> dict[str, int]:
    return {
        "note_chars": NOTE_MAX_CHARS,
        "total_chars": NOTES_TOTAL_MAX_CHARS,
        "writes_per_turn": NOTE_WRITES_PER_TURN,
    }


async def _session_notes_map(name: str, session_id: str | None) -> dict[int, str] | None:
    """The notes the open chat's CURRENT system prompt carries, or None.

    Reads the live web session's ``agent.messages[0]`` when it is loaded, else
    the persisted row's first message. None when there is nothing to compare:
    no/unknown session, another agent's session, or a prompt with no notes block.
    """
    if not session_id:
        return None
    from the_one.db.codec import decode_messages
    from the_one.interfaces.web.app import _sessions

    text: str | None = None
    live = _sessions.get(session_id)
    if live is not None and getattr(live, "agent", None) is not None:
        if (live.agent_name or "default") != name:
            return None
        msgs = getattr(live.agent, "messages", None)
        if msgs and isinstance(msgs[0].content, str):
            text = msgs[0].content
    if text is None:
        try:
            row = await (await _chat_repo()).get(session_id)
        except KeyError:
            return None
        if (row.agent_name or "default") != name:
            return None
        msgs = decode_messages(row.messages)
        if not msgs or not isinstance(msgs[0].content, str):
            return None
        text = msgs[0].content
    return parse_notes_block(text)


@router.get("/agents/{name}/notes")
async def list_agent_notes(name: str, session_id: str | None = None) -> dict[str, Any]:
    _store, config = await _load_agent_or_404(name)
    repo = await _agent_notes_repo()
    notes = await repo.list_for_agent(name)
    in_prompt = await _session_notes_map(name, session_id)
    rows = []
    for n in notes:
        row = n.model_dump(exclude={"agent_name"})
        row["pending"] = in_prompt is not None and in_prompt.get(n.number) != render_note_line_text(
            n
        )
        rows.append(row)
    return {
        "enabled": config.notes_enabled,
        "notes": rows,
        "pending_known": in_prompt is not None,
        "limits": _notes_limits(),
        "usage": {"total_chars": sum(len(n.text) for n in notes)},
    }


@router.put("/agents/{name}/notes/settings")
async def set_agent_notes_settings(name: str, request: Request) -> dict[str, Any]:
    body = await _rules_body(request, _NotesSettingsBody)
    store = await _agent_store()
    try:
        await store.set_notes_enabled(name, body.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {name}")
    return {"enabled": body.enabled}


@router.put("/agents/{name}/notes/{note_id}")
async def update_agent_note(name: str, note_id: str, request: Request) -> dict[str, Any]:
    body = await _rules_body(request, _NoteUpdateBody)
    await _load_agent_or_404(name)
    repo = await _agent_notes_repo()
    try:
        note, _changed = await repo.update_by_operator(name, note_id, body.text)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    except (NoteLimitError, NoteDuplicateError) as e:
        raise HTTPException(status_code=422, detail=e.detail)
    return note.model_dump(exclude={"agent_name"})


@router.delete("/agents/{name}/notes/{note_id}")
async def delete_agent_note(name: str, note_id: str) -> dict[str, str]:
    await _load_agent_or_404(name)
    repo = await _agent_notes_repo()
    try:
        await repo.delete(name, note_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    return {"status": "ok"}


@router.delete("/agents/{name}/notes")
async def clear_agent_notes(name: str) -> dict[str, int]:
    await _load_agent_or_404(name)
    repo = await _agent_notes_repo()
    return {"deleted": await repo.clear(name)}


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
    data = await _read_json(request)
    data["name"] = _checked_name(data.get("name"))
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    try:
        kb = KnowledgeBase.model_validate(data)
    except ValidationError as e:
        # Leg 5 review fix (BLOCKING 2): a client-supplied `id` (e.g.
        # "../../../evil") must 422 via the model's charset validator, not
        # crash as an unhandled 500 — `KnowledgeBase.id` is used verbatim
        # to build a filesystem path in `UsearchStore._path_for`.
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    repo = await _kb_repo()
    await repo.create(kb)
    # M24 F02 L03, DD-1: kick the embedding warm-up on the operator's first
    # KB after a cold start, so they don't pay the model load inside their
    # first indexing request either. Idempotent — no bookkeeping needed.
    # Squawk 0055: the task handle is held inside ``the_one.embeddings``
    # (not discarded here) so it can't be garbage-collected mid-flight.
    _schedule_embedding_warm_up()
    return kb.model_dump()


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(kb_id: str, request: Request) -> dict[str, Any]:
    data = await _read_json(request)
    data["id"] = kb_id
    repo = await _kb_repo()
    try:
        existing = await repo.get(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    # ``model_copy(update=...)`` does NOT re-run field validators in
    # Pydantic v2, so a malformed PUT would silently bypass validation
    # and corrupt the stored row. Round-trip through ``model_dump() |
    # data → model_validate(...)`` so the validator fires on the merged
    # payload. Mirrors ``update_connector`` (M10 F2 L6). Squawk 0013.
    try:
        merged = existing.model_dump()
        merged.update(data)
        if "name" in data:
            merged["name"] = _checked_name(merged["name"])
        updated = KnowledgeBase.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    await repo.update(updated)

    # L2-D7/L2-D9: the agent rewrite happens AFTER the knowledge-base row
    # has committed (write_transaction raises on re-entry by the same task,
    # so this can never be one atomic unit with the write above). Most PUTs
    # touch only description/etc. and must not load and re-save every
    # attached agent, hence the raw-name check here and the slug check inside.
    if existing.name != updated.name:
        from the_one.knowledge.kb_rename import carry_kb_rename

        await carry_kb_rename(existing, updated, get_agent_store=_agent_store)
    return updated.model_dump()


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(kb_id: str) -> dict[str, str]:
    repo = await _kb_repo()
    item_repo = await _kb_item_repo()
    # Flight 3 Leg 3, AC-10: stop kb_id's worker (if a manager is
    # installed) BEFORE the repository delete, so no worker is mid-item
    # on rows about to be cascaded. A no-op for an untracked kb_id.
    manager = get_indexing_manager()
    # Flight 4 Leg 3, DD-3/DD-8: suppress kb_id's watch timer for the
    # whole stop -> delete -> store-delete sequence, closing the same race
    # AC-10 closed for indexing alone (a reconcile tick or a sibling
    # folder's timer restarting the worker between `manager.stop` and the
    # repository delete). A `None` manager is `contextlib.nullcontext()`.
    watch = get_watch_manager()
    async with watch.suppress(kb_id) if watch is not None else contextlib.nullcontext():
        if watch is not None:
            await watch.stop_kb(kb_id)
        if manager is not None:
            await manager.stop(kb_id)
        # Flight 7 Leg 2, DD-7/AC-11: enumerate the KB's folders BEFORE
        # the repository delete below — once `repo.delete` commits, the
        # `kb_items` rows (and thus the folder ids the walk-skip-counter
        # keys are keyed on) are gone via FK cascade, and there is nothing
        # left to enumerate.
        folders = await item_repo.list_folders(kb_id)
        try:
            await repo.delete(kb_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")
        # Flight 2 Leg 4: vector-store cleanup happens AFTER the repository
        # transaction has committed, never inside it (both stores acquire
        # the write lock themselves — DD-13 forbids nesting). The DB row is
        # truth; a store failure here is logged and swallowed rather than
        # surfaced — a stale vector row for a never-recycled id is harmless.
        try:
            store = await _vector_store()
            await store.delete_kb(kb_id)
        except Exception:
            logger.exception("vector store delete_kb failed for knowledge base %s", kb_id)
        # Flight 7 Leg 2, DD-7/AC-11: clean up each folder's walk-skip-
        # counter kv key — outside `kb_items`' FK cascade by construction
        # (app_metadata is a separate table), so left alone it would
        # orphan forever. Same log-and-continue shape as the vector-store
        # cleanup above: a failure here must not un-delete the knowledge
        # base that already committed.
        # Squawk 0148: per-folder try, so one failed delete does not skip
        # the remaining folders' keys.
        try:
            meta_repo = await _app_metadata_repo()
        except Exception:
            logger.exception("walk-skip-counter cleanup failed for knowledge base %s", kb_id)
        else:
            for folder in folders:
                try:
                    await meta_repo.delete(walk_skip_counters_key(folder.id))
                except Exception:
                    logger.exception(
                        "walk-skip-counter cleanup failed for knowledge base %s folder %s",
                        kb_id,
                        folder.id,
                    )
    return {"status": "ok"}


# ── KB Items ──────────────────────────────────────────────────────────────


@router.get("/knowledge-bases/{kb_id}/items")
async def list_kb_items(kb_id: str) -> list[dict[str, Any]]:
    repo = await _kb_item_repo()
    items = await repo.list(kb_id)
    return [item.model_dump() for item in items]


@router.post("/knowledge-bases/{kb_id}/items", status_code=201)
async def create_kb_item(kb_id: str, request: Request) -> dict[str, Any]:
    # R8: check the KB exists BEFORE validating/inserting the body, so an
    # unknown kb_id surfaces as 404 rather than leaking the FK violation
    # as an unhandled 500 IntegrityError.
    kb_repo = await _kb_repo()
    try:
        await kb_repo.get(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    data = await _read_json(request)
    data["kb_id"] = kb_id
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    try:
        item = KBItem.model_validate(data)
    except ValidationError as e:
        # Flight 3 Leg 1: the create_knowledge_base 422 shape (:1414-1420)
        # — a malformed item body used to 500 unhandled.
        raise HTTPException(status_code=422, detail=_validation_detail(e))

    repo = await _kb_item_repo()
    if item.type == "folder":
        # DD-1: existence -> root -> containment, in that exact order, so
        # a non-existent path under a registered folder is 422, not 409.
        canonical = canonicalize(item.path_or_url)
        if not await asyncio.to_thread(canonical.is_dir):
            raise HTTPException(
                status_code=422,
                detail=f"folder does not exist or is not a directory: {item.path_or_url}",
            )
        if is_filesystem_root(canonical):
            raise HTTPException(
                status_code=422, detail=f"cannot register the filesystem root: {canonical}"
            )
        # DD-6: a folder that equals, contains, or lies inside the data
        # directory is refused before the containment scan — the app's own
        # database, WAL and vector sidecar live there, and registering it
        # (or an ancestor of it) would feed every indexing write back into
        # the watcher as a new pass forever (Flight 4).
        if is_within(settings.data_dir, canonical) or is_within(canonical, settings.data_dir):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"folder overlaps the application data directory ({settings.data_dir}); "
                    "the app's own database and index live there — register a folder that "
                    "does not contain it"
                ),
            )
        for existing in await repo.list_folders(kb_id):
            if is_within(canonical, existing.path_or_url) or is_within(
                existing.path_or_url, canonical
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"folder overlaps registered folder {existing.id}: {existing.path_or_url}"
                    ),
                )
        item = item.model_copy(update={"path_or_url": str(canonical)})

    elif item.type == "file":
        # Squawk 0147: DD-6 applies to a file item too — one that equals or
        # lies inside the data directory would let the extractor (and the
        # source read-back) read the app's own database and credentials.
        # Same canonicalization and same refusal as a folder; the file need
        # not exist (the indexer reports a missing file as a failed item).
        canonical = canonicalize(item.path_or_url)
        if is_within(canonical, settings.data_dir):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"file lies inside the application data directory ({settings.data_dir}); "
                    "the app's own database and index live there — register a file "
                    "outside it"
                ),
            )
        item = item.model_copy(update={"path_or_url": str(canonical)})

    await repo.create(item)
    if item.type == "folder":
        _after_folder_registered(kb_id, item)
    else:
        # Squawk 0244: a lone file indexes promptly too (no-op without a manager).
        manager = get_indexing_manager()
        if manager is not None:
            manager.request_index(kb_id)
    return item.model_dump()


def _after_folder_registered(kb_id: str, item: KBItem) -> None:
    """Kick kb_id's indexing worker (Flight 3 Leg 3) and start watching
    the folder (Flight 4 Leg 3) — a no-op for either manager not
    installed (pre-lifespan, or a test with none injected)."""
    manager = get_indexing_manager()
    if manager is not None:
        manager.request_index(kb_id)
    watch = get_watch_manager()
    if watch is not None:
        watch.start(kb_id, item)


@router.get("/knowledge-bases/{kb_id}/items/{item_id}")
async def get_kb_item(kb_id: str, item_id: str) -> dict[str, Any]:
    repo = await _kb_item_repo()
    try:
        item = await repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    # Scoping rule (R8): an id that exists but belongs to another KB reads
    # as unknown — same message and status as a truly-missing id, so ids
    # never leak across KBs.
    if item.kb_id != kb_id:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    return item.model_dump()


@router.post("/knowledge-bases/{kb_id}/items/{item_id}/retry")
async def retry_kb_item(kb_id: str, item_id: str) -> dict[str, Any]:
    """Move a stranded item back to ``pending``.

    Accepts both ``failed`` (operator retry) and ``indexing`` (a process
    killed mid-index, DD-5) — the same operator intent. Flight 3 Leg 3
    added two automatic paths that also clear a stranded ``indexing``
    row — ``IndexingManager.start_all``'s startup ``requeue_stranded()``
    and the per-pass ``requeue_stranded(kb_id)`` at the top of every
    worker pass — so this route is no longer the *only* way out, just the
    operator-immediate one (no restart or re-index request needed). Any
    other current status is rejected 409 with the current status in the
    detail.
    """
    repo = await _kb_item_repo()
    try:
        item = await repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    if item.kb_id != kb_id:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    # Retry's operator intent is narrower than the full DD-5 transition
    # table's ``pending: {indexing, failed, indexed}`` — an ``indexed``
    # item can also reach ``pending`` (re-index), but that is a DIFFERENT
    # operation from retry; only a stranded item (``failed`` or mid-kill
    # ``indexing``) is a valid retry target.
    if item.status not in ("failed", "indexing"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot retry item in status '{item.status}'",
        )
    try:
        updated = await repo.update_status(item_id, "pending")
    except KBItemTransitionError:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot retry item in status '{item.status}'",
        )
    return updated.model_dump()


@router.delete("/knowledge-bases/{kb_id}/items/{item_id}")
async def delete_kb_item(kb_id: str, item_id: str) -> dict[str, str]:
    repo = await _kb_item_repo()
    try:
        item = await repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    # Scoping rule (R8): deleting item X through a KB path it does not
    # belong to now 404s instead of succeeding.
    if item.kb_id != kb_id:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")

    # Squawk 0243: a file a folder walk created is owned by that folder; the
    # next walk would recreate it, so refuse rather than report a false success.
    if item.parent_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This file belongs to a registered folder, so deleting it would be undone "
                "by the next scan. Remove its folder instead."
            ),
        )

    # Flight 3 Leg 3, AC-10: a folder delete stops kb_id's worker first
    # (no worker mid-item on rows about to be cascaded) and re-kicks it
    # after (the remaining folders re-walk). A standalone file delete
    # needs neither — the worker's own per-item catch handles a vanished
    # row.
    manager = get_indexing_manager()
    # Flight 4 Leg 3, DD-3/DD-8: a folder delete also stops the item's
    # watch entry, under the same kb_id suppression as
    # delete_knowledge_base — a folder delete only (the standalone-file
    # branch below needs neither watch nor suppression: there is nothing
    # watching a lone file). The two 404s above fire before this block, so
    # no suppression is entered or exited on those paths.
    watch = get_watch_manager() if item.type == "folder" else None
    async with watch.suppress(kb_id) if watch is not None else contextlib.nullcontext():
        if watch is not None:
            await watch.stop(item_id)
        if item.type == "folder" and manager is not None:
            await manager.stop(kb_id)

        ids = await repo.delete(item_id)
        # Flight 2 Leg 4: same after-the-repository-transaction, log-and-
        # continue shape as delete_knowledge_base above.
        if ids:
            try:
                store = await _vector_store()
                await store.delete(kb_id, ids)
            except Exception:
                logger.exception("vector store delete failed for kb item %s", item_id)

        # Flight 7 Leg 2, DD-7/AC-11: a folder delete also clears its own
        # walk-skip-counter kv key. NO enumeration needed — folders cannot
        # nest (registration 409s on an overlapping folder, and only
        # ``file`` items ever carry a ``parent_id``), so this item's own
        # id is the only key there ever was. Deliberately NOT keyed off
        # ``ids`` above: ``KBItemRepository.delete`` returns removed CHUNK
        # ids only, never descendant item/folder ids — reusing it here
        # would clear nothing.
        if item.type == "folder":
            try:
                meta_repo = await _app_metadata_repo()
                await meta_repo.delete(walk_skip_counters_key(item.id))
            except Exception:
                logger.exception("walk-skip-counter cleanup failed for kb item %s", item_id)

        if item.type == "folder" and manager is not None:
            manager.request_index(kb_id)

    return {"status": "ok"}


@router.get("/knowledge-bases/{kb_id}/status")
async def get_kb_status(kb_id: str) -> dict[str, Any]:
    """Flight 3 Leg 3, DD-8: the per-KB status projection — file-item
    counts (folders excluded, so Flight 6's inventory never renders a
    folder as a document), each folder's own walk status, the chunk
    count, and the indexer's current state word.

    Flight 7 Leg 2 (DD-6/DD-7) adds two ADDITIVE signals — no existing key
    removed or renamed: `"content_freshness"`, the ``MAX(indexed_at)``
    across the KB's ``file`` items (see
    ``KBItemRepository.latest_indexed_at``'s docstring for why this moves
    iff a file item actually re-indexes, unlike a folder's own
    ``indexed_at``) — this is what widens
    ``studio.js::knowledgeItemsSignature`` to see a content-only edit;
    and each ``folders[]`` entry gains ``"skipped_dirs"``/
    ``"skipped_entries"``, the last completed walk's persisted counts —
    both ``None`` for a folder whose walk has never completed ("not yet
    walked" is a different fact from "walked, skipped nothing").
    """
    kb_repo = await _kb_repo()
    try:
        await kb_repo.get(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    item_repo = await _kb_item_repo()
    chunk_repo = await _kb_chunk_repo()
    meta_repo = await _app_metadata_repo()
    folders = await item_repo.list_folders(kb_id)
    manager = get_indexing_manager()
    # Flight 4 Leg 3, DD-8: each folder's watch state and reason, additive
    # to Flight 3's projection. "off" / `None` with no watch manager
    # installed, matching `_after_folder_registered`'s no-op shape.
    watch = get_watch_manager()

    folder_entries = []
    for f in folders:
        # DD-7/AC-9: the walk-skip-counter kv record, read through the
        # SAME shared key helper the write site (manager.py) and both
        # cleanup sites (delete_kb_item/delete_knowledge_base) use
        # (AC-11b) — a per-folder read, same cost class as the watch
        # state/error lookups on the lines directly below.
        skip_raw = await meta_repo.get(walk_skip_counters_key(f.id))
        if skip_raw is not None:
            skip_counts = json.loads(skip_raw)
            skipped_dirs = skip_counts.get("skipped_dirs")
            skipped_entries = skip_counts.get("skipped_entries")
        else:
            skipped_dirs = None
            skipped_entries = None
        folder_entries.append(
            {
                "id": f.id,
                "path": f.path_or_url,
                "status": f.status,
                "indexed_at": f.indexed_at,
                "error": f.error,
                "watch": watch.state(f.id) if watch is not None else "off",
                "watch_error": watch.error(f.id) if watch is not None else None,
                "skipped_dirs": skipped_dirs,
                "skipped_entries": skipped_entries,
            }
        )

    return {
        "items": await item_repo.count_by_status(kb_id, type="file"),
        "content_freshness": await item_repo.latest_indexed_at(kb_id, type="file"),
        "folders": folder_entries,
        "chunks": await chunk_repo.count_for_kb(kb_id),
        "indexer": manager.state(kb_id) if manager is not None else "idle",
    }


@router.post("/knowledge-bases/{kb_id}/reindex", status_code=202)
async def reindex_knowledge_base(
    kb_id: str, scope: Literal["changed", "all"] = "changed"
) -> dict[str, Any]:
    """Flight 3 Leg 3, DD-8: ``changed`` (default) is a plain reconcile
    pass — ``request_index`` alone, so the next walk picks up new/edited/
    deleted files and unchanged content is not re-embedded. ``all`` is
    the recovery hammer — ``requeue_for_reindex`` (every ``indexed``/
    ``failed`` **file** item back to ``pending``; folders and ``indexing``
    items untouched) before ``request_index``, so every file is
    re-extracted and re-embedded."""
    kb_repo = await _kb_repo()
    try:
        await kb_repo.get(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    requeued = 0
    if scope == "all":
        item_repo = await _kb_item_repo()
        requeued = await item_repo.requeue_for_reindex(kb_id)

    manager = get_indexing_manager()
    if manager is not None:
        manager.request_index(kb_id)

    return {"scope": scope, "requeued": requeued}


@router.get("/knowledge-bases/{kb_id}/items/{item_id}/chunks")
async def get_kb_item_chunks(
    kb_id: str,
    item_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Flight 3 Leg 3, DD-8: an item's chunks in ``seq`` order, paged.
    R8 scoping: an item of another KB reads as 404."""
    item_repo = await _kb_item_repo()
    try:
        item = await item_repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    if item.kb_id != kb_id:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")

    chunk_repo = await _kb_chunk_repo()
    chunks = await chunk_repo.list_for_item(item_id, limit=limit, offset=offset)
    return [
        {
            "id": c.id,
            "seq": c.seq,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "text": c.text,
        }
        for c in chunks
    ]


@router.get("/knowledge-bases/{kb_id}/items/{item_id}/source")
async def get_kb_item_source(kb_id: str, item_id: str) -> dict[str, Any]:
    """Flight 3 Leg 3, DD-8: the source read-back — the extracted text
    re-run through the item's extractor on demand (never stored; chunks
    are the stored form and their offsets index into exactly this text).
    404 if the item or the file is missing; 422 for a ``folder``/``url``
    item or a ``file`` item with no registered extractor; 413 if the file
    exceeds ``MAX_FILE_BYTES`` — the route enforces the same 10 MiB cap
    the indexer does, checked independently here (not inherited from the
    indexer's own rejection; a file the indexer already failed on for a
    different reason is still readable here as long as it is under the
    cap)."""
    item_repo = await _kb_item_repo()
    try:
        item = await item_repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    if item.kb_id != kb_id:
        raise HTTPException(status_code=404, detail=f"KB item not found: {item_id}")
    if item.type != "file":
        raise HTTPException(status_code=422, detail=f"item type {item.type!r} has no source text")

    path = Path(item.path_or_url)
    extractor = extractor_for(path)
    if extractor is None:
        raise HTTPException(
            status_code=422, detail=f"no extractor registered for suffix {path.suffix!r}"
        )

    try:
        st = await asyncio.to_thread(path.stat)
    except (FileNotFoundError, NotADirectoryError):
        raise HTTPException(status_code=404, detail=f"file not found: {path}")

    if st.st_size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"file exceeds the 10 MiB read-back cap ({st.st_size} bytes)"),
        )

    try:
        text = await asyncio.to_thread(extractor.extract, path)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    digest = await asyncio.to_thread(content_hash, path)
    stale = item.content_hash is None or digest != item.content_hash

    return {
        "path": str(path),
        "size_bytes": st.st_size,
        "content_hash": item.content_hash,
        "stale": stale,
        "text": text,
    }


@router.get("/knowledge-bases/{kb_id}/search")
async def search_knowledge_base(
    kb_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=20),
) -> dict[str, Any]:
    """Flight 6 Leg 1, DD-6: the operator-facing, read-only search route —
    the missing HTTP entry point onto ``retrieval.search`` that Flight 5's
    debrief asked for. Wraps the exact dependency wiring
    ``knowledge/tool.py``'s ``KBSearchTool`` uses: repositories off the
    request connection, the process-wide vector store, and the embedding
    backend resolved under ``asyncio.to_thread`` (synchronous + lock-
    taking — must not run directly on the event loop).

    ``q`` is required and non-empty at the route bound (422 on missing or
    empty); a whitespace-only ``q`` passes the bound and falls through to
    ``retrieval.search``'s own documented no-op — a 200 with zero hits,
    touching neither the store nor the backend. Deliberate split: the
    route rejects a malformed request, but a real query that matches
    nothing is not an error.

    Renders no per-hit provenance and does not widen ``SearchHit``
    (Architect cycle 2) — ``dataclasses.asdict`` serializes it verbatim.
    """
    kb_repo = await _kb_repo()
    try:
        await kb_repo.get(kb_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")

    chunk_repo = await _kb_chunk_repo()
    item_repo = await _kb_item_repo()
    store = await _vector_store()
    # Synchronous + lock-taking — must not run directly on the event loop
    # (same rationale as knowledge/tool.py's KBSearchTool.execute).
    backend = await asyncio.to_thread(get_embedding_backend)

    result = await kb_search(
        kb_id,
        q,
        limit=limit,
        chunk_repo=chunk_repo,
        item_repo=item_repo,
        store=store,
        backend=backend,
    )
    manager = get_indexing_manager()
    return {
        "hits": [dataclasses.asdict(h) for h in result.hits],
        "degraded": result.degraded,
        "indexer": manager.state(kb_id) if manager is not None else "idle",
    }


# ── Knowledge settings ───────────────────────────────────────────────────

_KNOWLEDGE_SETTINGS_NOTES = [
    "Chunking changes apply to items indexed after the change; existing chunks are not re-chunked.",
    "The embedding backend is fixed to the bundled local model in this release.",
    "Monitoring changes (the watcher on/off switch and the reconciliation "
    "interval) apply immediately.",
]


# ── Time-zone setting (M28 F1 L1) ─────────────────────────────────────────


async def _time_settings_response(setting: time_zones.TimeZoneSetting) -> dict[str, Any]:
    eff = time_zones.resolve(setting)
    now = time_zones.utcnow()
    local = now.astimezone(eff.tzinfo)
    system_name = time_zones.detect_system_zone()
    try:
        system_local = now.astimezone(ZoneInfo(system_name)) if system_name else now.astimezone()
    except Exception:  # noqa: BLE001
        system_local = now.astimezone()
    try:
        row = await (await _tool_config_repo()).get(time_zones.CURRENT_TIME_TOOL_NAME)
        tool_enabled = bool(row.enabled)
    except KeyError:
        tool_enabled = True
    return {
        "mode": setting.mode,
        "zone": setting.zone,
        "system": {
            "zone": system_name,
            "offset": time_zones.offset_label(system_local),
        },
        "effective": {
            "zone": eff.key,
            "canonical": time_zones.canonical_name(eff.key),
            "label": time_zones.zone_label(eff, local),
            "offset": time_zones.offset_label(local),
            "offset_minutes": time_zones.offset_minutes(now, eff),
            "abbreviation": time_zones.abbreviation(local),
        },
        "tool_enabled": tool_enabled,
        "preview": {
            "tool": "\n".join(time_zones.tool_lines(now, eff)),
            "prompt": time_zones.date_line(now, eff, tool_available=True),
            "prompt_without_tool": time_zones.date_line(now, eff, tool_available=False),
            "clock": time_zones.clock_text(now, eff),
        },
    }


def _time_settings_error(e: ValidationError, body: dict[str, Any]) -> str:
    """One plain sentence for a rejected time-zone body (never a list)."""
    errors = e.errors()
    for err in errors:
        if err["loc"] == ("mode",):
            return "mode must be 'system' or 'zone'."
    for err in errors:
        if err["loc"] == ("zone",):
            raw = body.get("zone")
            shown = raw[:64] if isinstance(raw, str) else ""
            if shown:
                return f"Unknown time zone '{shown}'. Use an IANA name such as Asia/Tokyo."
            return "Unknown time zone. Use an IANA name such as Asia/Tokyo."
    for err in errors:
        if err["type"] == "value_error" and time_zones.ERR_ZONE_REQUIRED in str(err.get("msg", "")):
            return "Choose a time zone when mode is 'zone'."
    return "Body may contain only 'mode' and 'zone'."


@router.get("/time-settings")
async def get_time_settings() -> dict[str, Any]:
    conn = await get_connection()
    return await _time_settings_response(await time_zones.load_setting(conn))


@router.put("/time-settings")
async def update_time_settings(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001 — malformed JSON is a client error, not a 500
        raise HTTPException(status_code=422, detail="Body must be a JSON object.")
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object.")
    if set(data) - {"mode", "zone"}:
        raise HTTPException(status_code=422, detail="Body may contain only 'mode' and 'zone'.")
    try:
        setting = time_zones.TimeZoneSetting.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_time_settings_error(e, data))
    conn = await get_connection()
    await time_zones.save_setting(conn, setting)
    _poke_scheduler()
    return await _time_settings_response(setting)


@router.get("/time-zones")
async def get_time_zones() -> dict[str, Any]:
    return {
        "zones": time_zones.zone_rows(time_zones.utcnow()),
        "links": time_zones.zone_links(),
    }


async def _knowledge_settings_conn():
    return await get_connection()


async def _knowledge_settings_response(conn, current: KnowledgeSettings) -> dict[str, Any]:
    # Flight 2 Leg 4: `vector_store` is store-written (DD-3/DD-6, never
    # accepted by the PUT route below — the existing top-level-key guard
    # already 422s it) and read fresh on every response since it is
    # independent of `current`'s embedding/chunking values.
    vector_store = await load_vector_store_settings(conn)
    return {
        "embedding": current.embedding.model_dump(),
        "chunking": current.chunking.model_dump(),
        "monitoring": current.monitoring.model_dump(),
        "vector_store": vector_store.model_dump(),
        "notes": list(_KNOWLEDGE_SETTINGS_NOTES),
    }


@router.get("/knowledge-settings")
async def get_knowledge_settings() -> dict[str, Any]:
    conn = await _knowledge_settings_conn()
    current = await load_knowledge_settings(conn)
    return await _knowledge_settings_response(conn, current)


@router.put("/knowledge-settings")
async def update_knowledge_settings(request: Request) -> dict[str, Any]:
    data = await _read_json(request)
    if not isinstance(data, dict) or set(data) - {"embedding", "chunking", "monitoring"}:
        raise HTTPException(
            status_code=422,
            detail="body must contain only 'embedding', 'chunking' and/or 'monitoring' keys",
        )

    # Leg 5 review fix-now: a non-dict `embedding`/`chunking`/`monitoring`
    # value (e.g. a string or list) must 422, not raise an uncaught
    # TypeError out of `dict.update()` below and surface as an unhandled
    # 500.
    for key in ("embedding", "chunking", "monitoring"):
        if key in data and not isinstance(data[key], dict):
            raise HTTPException(
                status_code=422,
                detail=f"'{key}' must be an object, got {type(data[key]).__name__}",
            )

    conn = await _knowledge_settings_conn()
    current = await load_knowledge_settings(conn)

    merged_embedding = current.embedding.model_dump()
    if "embedding" in data:
        merged_embedding.update(data["embedding"])
    merged_chunking = current.chunking.model_dump()
    if "chunking" in data:
        merged_chunking.update(data["chunking"])
    merged_monitoring = current.monitoring.model_dump()
    if "monitoring" in data:
        merged_monitoring.update(data["monitoring"])

    try:
        updated = KnowledgeSettings(
            embedding=EmbeddingSettings.model_validate(merged_embedding),
            chunking=ChunkingSettings.model_validate(merged_chunking),
            monitoring=MonitoringSettings.model_validate(merged_monitoring),
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))

    await save_knowledge_settings(conn, updated)
    # DD-5: applied live, not only on the next indexing pass (unlike
    # chunking) — the operator chose settings over env vars precisely so
    # the on/off switch and the interval are switches. This is the
    # `leg-staged-hook-seam` (agents.md): a documented no-op here, filled
    # by Leg 3 with `get_watch_manager().apply_settings(...)`.
    await _after_monitoring_settings_changed(updated.monitoring)
    return await _knowledge_settings_response(conn, updated)


async def _after_monitoring_settings_changed(monitoring: MonitoringSettings) -> None:
    """Apply a saved `MonitoringSettings` change live (Flight 4 DD-5).

    Filled in by Leg 3: `await get_watch_manager().apply_settings(
    monitoring)` — a `None` manager (pre-lifespan, or a test with none
    injected) is a no-op, the `_after_folder_registered` shape.
    `apply_settings` is itself idempotent (disabled -> stop and forget
    every entry; enabled -> re-subscribe every folder of every knowledge
    base; either way the reconcile loop wakes so a changed interval
    applies immediately). Awaited by the route only after a successful
    `save_knowledge_settings`, never on a 422 path.
    """
    watch = get_watch_manager()
    if watch is not None:
        await watch.apply_settings(monitoring)


# ── MCP Sources ───────────────────────────────────────────────────────────


# Mask-shape single source-of-truth. The emit helper, the recognize
# regex, and any future paired helper read these constants; never
# hardcode the literals. M11 F8 L3.
_MASK_PREFIX = "***"
_MASK_TAIL_SEPARATOR = "..."
_MASK_TAIL_LEN = 4
# Squawk 0030: a tail is only shown when it doesn't reconstruct most of
# the secret. Below this length the tail is elided entirely (fully
# opaque ``***``) — the tail's identification purpose only makes sense
# for long tokens; for a 5-char secret like "dummy", showing 4 of them
# back (``***...ummy``) leaks nearly the whole value.
_MASK_TAIL_MIN_SECRET_LEN = 12


def _emit_mask(value: str) -> str:
    """Single source-of-truth for mask shape.

    Assumes a non-empty ``str`` input — callers guard ``None`` / empty
    / non-str before calling. Returns ``_MASK_PREFIX`` (no tail) for
    secrets shorter than ``_MASK_TAIL_MIN_SECRET_LEN`` — for those,
    even a 4-char tail would reconstruct most or all of the value;
    returns ``_MASK_PREFIX + _MASK_TAIL_SEPARATOR + value[-_MASK_TAIL_LEN:]``
    for secrets at or above that threshold (squawk 0030).

    Pair: ``_MASK_SHAPE_RE`` (below) recognizes the output of this
    helper. Both read from the same constants so a future maintainer
    cannot drift the emit shape from the recognize shape. See
    ``the_one/agents.md`` → ``single-source-of-truth-for-paired-helpers``.
    """
    if len(value) < _MASK_TAIL_MIN_SECRET_LEN:
        return _MASK_PREFIX
    return f"{_MASK_PREFIX}{_MASK_TAIL_SEPARATOR}{value[-_MASK_TAIL_LEN:]}"


def _mask_secret_value(value: Any) -> Any:
    """Mask a single secret value mirroring ``_mask_api_key``'s shape.

    Type signature is ``Any -> Any`` (not ``str -> str``) because the
    secrets dict is ``dict[str, Any]`` per L2's MCPSource model — a
    client could in principle send a non-string value, and we want to
    mask it defensively rather than crash. Empty/None passes through
    unchanged; string values shorter than ``_MASK_TAIL_MIN_SECRET_LEN``
    mask as ``***``; longer string values mask as ``***...{tail4}``;
    non-string values mask wholesale as ``***`` (no leakage of nested
    structure) (squawk 0030). Same per-decoded-value
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


@router.get("/mcp-sources")
async def list_mcp_sources(include_agent_surfaces: str | None = None) -> list[dict[str, Any]]:
    """DD3: per-agent self-configuration surface rows are hidden from the
    admin MCP Sources listing by default — the operator manages them from
    the owning agent's own tabs, not this screen. The agent editor's fetch
    passes ``?include_agent_surfaces=1`` so its Tools tab (and the
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
        {"value": "stdio", "label": "Local program (stdio)"},
        {"value": "streamable-http", "label": "Remote server (HTTP)"},
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
    data = await _read_json(request)
    data["name"] = _checked_name(data.get("name"))
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    try:
        source = MCPSource.model_validate(data)
    except ValidationError as e:
        # ``include_context=False`` so the response stays JSON-encodable
        # — ``model_validator`` paths populate ``ctx['error']`` with raw
        # exceptions that aren't JSON-serializable.
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    _reject_reserved_surface_name(source)
    _validate_mcp_source_config(source)
    repo = await _mcp_repo()
    await repo.create(source)
    return _mcp_source_response(source)


def _reject_reserved_surface_name(source: MCPSource) -> None:
    """LD7 / AC8b: the literal name ``self_configuration_manage.
    SURFACE_ROW_NAME`` ("self-configuration") is reserved for the platform-
    managed self-configuration surface row — the name keys the surface's
    prefixed tool names (``mcp__self-configuration__*``) and the API's
    refusal of a per-agent override for it, so a same-named ordinary source
    would collide with it. Surface rows themselves are created only by ``manage.enable`` (not
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


def _config_without_cache(source: MCPSource) -> dict[str, Any]:
    return {k: v for k, v in (source.config or {}).items() if k != "_cache"}


@router.put("/mcp-sources/{source_id}")
async def update_mcp_source(source_id: str, request: Request) -> dict[str, Any]:
    data = await _read_json(request)
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

    # ``model_copy(update=...)`` does NOT re-run field validators in
    # Pydantic v2, so a malformed PUT (e.g. an unknown ``type`` literal)
    # would silently bypass validation and corrupt the stored row.
    # Round-trip through ``model_dump() | data → model_validate(...)``
    # so the validator fires on the merged payload. Mirrors
    # ``update_connector`` (M10 F2 L6). Squawk 0013.
    try:
        merged = existing.model_dump()
        merged.update(data)
        if "name" in data:
            merged["name"] = _checked_name(merged["name"])
        updated = MCPSource.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    # AC8b: `existing` is guaranteed non-surface at this point (a marked
    # row was already refused above), so this only fires when the PUT
    # would rename an ORDINARY source into the reserved constant name.
    _reject_reserved_surface_name(updated)
    _validate_mcp_source_config(updated)
    # DD2: the row may now point at a different server. The same rule drops the
    # remembered era (below) and the old server's last check and auth posture;
    # every other _cache key (the tools cache) stays. An emptied _cache is
    # removed, as Reset does (absence is the "never checked" state).
    server_changed = updated.type != existing.type or (updated.config or {}).get("url") != (
        existing.config or {}
    ).get("url")
    if server_changed and isinstance((updated.config or {}).get("_cache"), dict):
        kept = {
            k: v
            for k, v in updated.config["_cache"].items()
            if k not in ("last_check", "auth_posture")
        }
        new_config = {k: v for k, v in updated.config.items() if k != "_cache"}
        if kept:
            new_config["_cache"] = kept
        updated = updated.model_copy(update={"config": new_config})
    await repo.update(updated)
    forget_era(source_id)
    # Sortie 09 DD7: a change of type, config (the `_cache` is server-managed) or
    # secrets reaches every agent's next connection to this source.
    if (
        updated.type != existing.type
        or _config_without_cache(updated) != _config_without_cache(existing)
        or updated.secrets != existing.secrets
    ):
        from the_one.mcp._pool import _evict_all_for_source

        try:
            await _evict_all_for_source(source_id)
        except Exception:
            logger.warning("could not evict MCP connections for %r", source_id, exc_info=False)
        await _drop_source_agent_tool_cache(repo, source_id)
    # DD8: the rename carries into the attached agents' overrides and
    # disabled tools. Runs after the row commit (write_transaction cannot
    # nest); acquiring the store is guarded like update_knowledge_base's so
    # a failure here is a WARNING, never a 500 after the rename committed.
    if existing.name != updated.name:
        from the_one.mcp.rename_references import carry_mcp_rename

        try:
            agent_store = await _agent_store()
        except Exception:
            logger.warning(
                "MCP source %r rename: failed to acquire the agent store to carry "
                "the rename; the source has already been renamed, but no agent "
                "could be examined, so overrides and disabled_tools may still "
                "reference the old name",
                source_id,
                exc_info=True,
            )
        else:
            await carry_mcp_rename(
                source_id, existing.name, updated.name, agent_store=agent_store, mcp_repo=repo
            )
        # Sortie 10 (DD3): a secret's allowed tools follow the rename too. Its own try
        # (the carry never raises, but acquiring the repository can), so an agent-store
        # failure above never skips it.
        try:
            from the_one.mcp.rename_references import carry_mcp_rename_into_secrets

            await carry_mcp_rename_into_secrets(
                existing.name, updated.name, secret_repo=await _secret_repo(), mcp_repo=repo
            )
        except Exception:
            logger.warning(
                "MCP source %r rename: failed to carry the rename into secrets' allowed tools",
                source_id,
                exc_info=True,
            )
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
        forget_era(source_id)
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
    forget_era(source_id)

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
    await _drop_source_agent_tool_cache(repo, source_id)
    forget_era(source_id)
    return {"status": "ok"}


# Returned by ``_build_and_test_no_auth_mcp`` (only when ``from_fallthrough``) when
# the negotiating SDK path hit a 401: the route then continues into Phase B.
_SIGNIN_REQUIRED: Any = object()


async def _persist_oauth_posture(repo: MCPSourceRepository, source_id: str) -> None:
    """Persist ``_cache.auth_posture = "oauth"`` (best-effort).

    Shared by Phase 0's probe-``oauth`` branch and DD9's fall-through when the
    SDK path hits a 401, so a Phase B failure still leaves a definitive signal
    for the pool worker.
    """
    try:
        await repo.merge_cache(source_id, {"auth_posture": "oauth"})
    except Exception:
        # Best-effort; falling through to Phase B regardless.
        pass


async def _clear_auth_posture(repo: MCPSourceRepository, source_id: str) -> None:
    """Remove ``_cache.auth_posture`` (best-effort).

    Used when Phase B proves a rejected key and no request ever succeeded: the app
    does not know what the server is, so the next Test classifies it fresh.
    """
    try:
        await repo.merge_cache(source_id, {}, delete=("auth_posture",))
    except Exception:
        pass


class _CredentialsRejectedSignal(Exception):  # noqa: N818
    """Private sentinel set on Phase B's ``consent_url_future`` when its failed ``/register``
    plus the absence of any discovered OAuth metadata proves the server rejected the operator's
    headers and offers no sign-in (DD4 path (c))."""


async def _build_and_test_no_auth_mcp(
    source: MCPSource,
    source_id: str,
    repo: MCPSourceRepository,
    *,
    record_era: bool = True,
    from_fallthrough: bool = False,
    cache_write: Literal["none", "shared", "shared_no_posture"] = "shared",
    classify: bool = False,
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
        record_era: False when the Test used a body override (DD2): the
            server under test is not the saved one, so its era is not
            remembered.
        from_fallthrough: True only when entered from the DD9 fall-through
            (probe verdict ``unexpected_status``). A 401 then returns the
            ``_SIGNIN_REQUIRED`` sentinel instead of the race-branch error.
        cache_write: Sortie 09 DD6. ``"shared"`` (default) writes the shared
            ``_cache`` fields including ``auth_posture: "no_auth"``;
            ``"shared_no_posture"`` writes the same fields without
            ``auth_posture``; ``"none"`` writes nothing.
        classify: Sortie 09 DD3. With ``from_fallthrough`` also true, only an
            ``MCPAuthRequired`` returns ``_SIGNIN_REQUIRED``; an
            ``MCPCredentialsRejected`` (a bare 401 to configured headers) is the
            normal error dict. False keeps the fold of both into the sentinel.

    Returns:
        ``{status: "ok", tools, capabilities}`` on success, or
        ``{status: "error", error}`` on any failure.
    """
    from the_one.mcp.client import MCPClient
    from the_one.mcp.errors import (
        MCPAuthRequired,
        MCPCapabilityMissing,
        MCPConnectionError,
        MCPCredentialsRejected,
        MCPVersionMismatch,
    )

    try:
        async with MCPClient(
            source=source, auth_provider=None, fresh_negotiation=True, record_era=record_era
        ) as client:
            tools = await client.list_tools()
            capabilities = client.server_capabilities
            # F4 L2 (M08): capture spec-optional serverInfo + instructions
            # alongside tools/capabilities so the Tools tab can render a
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
            if cache_write != "none":
                cache_fields: dict[str, Any] = {
                    "tools": tools_cache_payload,
                    "capabilities": capabilities,
                    "server_info": server_info,
                    "instructions": instructions,
                    "meta": meta,
                    "protocol_version": protocol_version,
                    "last_updated": time.time(),
                }
                if cache_write == "shared":
                    cache_fields["auth_posture"] = "no_auth"
                try:
                    await repo.merge_cache(source_id, cache_fields)
                except Exception:
                    # Best-effort persistence — a write failure must not break the
                    # response contract (mirrors the Phase A persistence pattern).
                    pass
        return {
            "status": "ok",
            "tools": tools_cache_payload,
            "capabilities": capabilities,
        }
    except (MCPAuthRequired, MCPCredentialsRejected) as e:
        if from_fallthrough and not (classify and isinstance(e, MCPCredentialsRejected)):
            # A bare 401 from a server that may still be OAuth-only (2026-07-28 with no
            # metadata): Phase B decides with its own discovery evidence.
            return _SIGNIN_REQUIRED
        if isinstance(e, MCPCredentialsRejected):
            # Path (a): cached no_auth, key now rejected. Posture stays no_auth.
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
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
    source: MCPSource,
    source_id: str,
    repo: MCPSourceRepository,
    *,
    record_era: bool = True,
    cache_write: Literal["none", "shared", "shared_no_posture"] = "shared",
) -> dict[str, Any]:
    """Connect + list_tools against a stdio MCP source.

    ``cache_write`` (sortie 09 DD6): ``"none"`` writes no cache field; both
    ``"shared"`` and ``"shared_no_posture"`` write today's fields (stdio never
    writes ``auth_posture``).

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
        async with MCPClient(
            source=source, auth_provider=None, fresh_negotiation=True, record_era=record_era
        ) as client:
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
            if cache_write != "none":
                try:
                    await repo.merge_cache(
                        source_id,
                        {
                            "tools": tools_cache_payload,
                            "capabilities": capabilities,
                            "server_info": server_info,
                            "instructions": instructions,
                            "meta": meta,
                            "protocol_version": protocol_version,
                            "last_updated": time.time(),
                        },
                    )
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


async def _clear_stale_oauth_secrets(
    repo: MCPSourceRepository, source_id: str, source: MCPSource
) -> MCPSource:
    """Strip the four OAuth-managed secrets (stale tokens) before a fresh sign-in.

    Re-reads the STORED row, strips only those keys and writes that row back, so
    a request-body override (which may carry the operator's unsaved URL or
    headers) is never persisted. Returns ``source`` (the possibly-overridden
    in-memory shape Phase B needs, e.g. its ``config["url"]``) with the same keys
    stripped from its secrets. The in-memory strip happens even if the re-read or
    the write raises (a source deleted mid-Test raises ``KeyError``).
    """
    stripped_source = source.model_copy(
        update={
            "secrets": {
                k: v for k, v in source.secrets.items() if k not in _OAUTH_MANAGED_SECRET_KEYS
            }
        }
    )
    try:
        persisted = await repo.get(source_id)
        await repo.update(
            persisted.model_copy(
                update={
                    "secrets": {
                        k: v
                        for k, v in persisted.secrets.items()
                        if k not in _OAUTH_MANAGED_SECRET_KEYS
                    }
                }
            )
        )
    except Exception:
        pass
    return stripped_source


@router.post("/mcp-sources/{source_id}/test/agent")
async def test_mcp_connection_as_agent(source_id: str, request: Request) -> dict[str, Any]:
    """Sortie 09 DD6: connect with an agent's own credentials; see
    ``interfaces/web/mcp_agent_test.py``."""
    from the_one.interfaces.web.mcp_agent_test import run_agent_test

    return await run_agent_test(source_id, request)


@router.post("/mcp-sources/{source_id}/test/connect")
async def test_mcp_connection(source_id: str, request: Request) -> dict[str, Any]:
    """Run a connection check and record its outcome (``_cache.last_check``).

    The one write point for the record: the inner function returns
    ``(result, recordable)``, ``recordable`` being true only for a body-less Test of
    the saved server that was an actual connection check. See
    :func:`_test_mcp_connection_inner` for the check itself.
    """
    result, recordable = await _test_mcp_connection_inner(source_id, request)
    if recordable and result.get("status") in _RECORDED_CHECK_STATUSES:
        try:
            repo = await _mcp_repo()
            await repo.merge_cache(
                source_id,
                {"last_check": {"status": result["status"], "at": time.time()}},
            )
        except Exception:
            # Best-effort, like every other cache write: the response contract wins.
            logger.debug("could not record last_check for %s", source_id, exc_info=True)
    return result


_RECORDED_CHECK_STATUSES = frozenset({"ok", "error", "auth_required"})


async def _connect_with_tokens(
    source: MCPSource,
    source_id: str,
    repo: MCPSourceRepository,
    *,
    record_era: bool,
    cache_write: Literal["none", "shared", "shared_no_posture"] = "shared",
) -> dict[str, Any]:
    """Phase A of the Library Test, shared with the per-agent test route (sortie 09 DD6).

    Tokens present: build the OAuth provider WITHOUT a consent future (this path
    never kicks a flow) and connect + list_tools with it. MUST thread the provider
    through ``MCPClient`` or the SDK has no way to apply the cached tokens (a bare
    client sends Bearer-less requests and always 401s).

    ``cache_write``: ``"shared"`` and ``"shared_no_posture"`` both write today's
    fields into ``source.config._cache`` (this block never wrote ``auth_posture``);
    ``"none"`` writes nothing. The write is best-effort and happens INSIDE the
    ``async with`` after ``list_tools()`` succeeds, so a failed listing does not
    pollute the cache.

    Returns ``{status: "ok", tools, capabilities}``. Errors are RE-RAISED untouched
    (``MCPAuthRequired``, ``MCPConnectionError``, ``MCPVersionMismatch``) so the
    caller decides: the Library Test clears stale tokens and falls through to
    Phase B; the per-agent route reports them and never touches tokens. The
    imports stay function-local because tests patch ``the_one.mcp.client.MCPClient``.
    """
    from the_one.mcp.client import MCPClient
    from the_one.mcp.oauth import build_oauth_provider_for_source

    provider_a = build_oauth_provider_for_source(
        source,
        repo,
        f"test:{source_id}",
        source_id=source_id,
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=None,  # Phase A doesn't kick a flow
    )
    async with MCPClient(
        source=source,
        auth_provider=provider_a,
        fresh_negotiation=True,
        record_era=record_era,
    ) as client:
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
        # F9 L1 (vibing): persist tools+capabilities to source.config._cache so the
        # editor can render the cached state on mount. Plaintext: tools, capabilities
        # and the timestamp are not secrets. The cache is keyed on the persisted row,
        # not the operator's transient form values.
        tools_cache_payload = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
        if cache_write != "none":
            try:
                await repo.merge_cache(
                    source_id,
                    {
                        "tools": tools_cache_payload,
                        "capabilities": capabilities,
                        "server_info": server_info,
                        "instructions": instructions,
                        "meta": meta,
                        "protocol_version": protocol_version,
                        "last_updated": time.time(),
                    },
                )
            except Exception:
                # Best-effort persistence: a write failure must not break the
                # response contract; the cache simply won't populate this round.
                pass
    return {
        "status": "ok",
        "tools": tools_cache_payload,
        "capabilities": capabilities,
    }


async def _test_mcp_connection_inner(
    source_id: str, request: Request
) -> tuple[dict[str, Any], bool]:
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
    from the_one.mcp.errors import (
        TOKEN_FAILURE_MARKERS,
        MCPAuthRequired,
        MCPConnectionError,
        MCPCredentialsRejected,
        MCPVersionMismatch,
    )
    from the_one.mcp.oauth import build_oauth_provider_for_source

    repo = await _mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    persisted_source = source
    # F8 L4: optionally override the persisted source with operator's
    # in-flight form values. Mirrors the PUT endpoint's secrets-resolution
    # logic (per-key __MASKED__ → existing; OAUTH-managed → always
    # preserved from existing). Body is optional — empty body preserves
    # the prior single-arg behavior verbatim.
    try:
        body_bytes = await request.body()
    except Exception:
        body_bytes = b""
    # Only a body-less Test is the saved server under test, so only it is recorded as
    # ``last_check`` (the client sends a body only when its form is dirty). This is NOT
    # ``record_era`` below: a body that changes only secrets still records the era but
    # never ``last_check``. Deliberately different gates; do not unify them.
    recordable = not body_bytes
    if body_bytes:
        try:
            payload = json.loads(body_bytes)
        except Exception as e:
            return {"status": "error", "error": f"invalid JSON body: {e}"}, recordable
        if not isinstance(payload, dict):
            return {"status": "error", "error": "request body must be a JSON object"}, recordable
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

    # DD2: the editor sends its form body only when the form is dirty, so "an override was
    # applied" means the server under test differs from the saved row (type or
    # config, ignoring the `_cache`). Secrets are not compared: a changed
    # credential does not change which server is under test. An override Test
    # must not record the era against the saved source id.
    def _config_sans_cache(src: MCPSource) -> dict[str, Any]:
        return {k: v for k, v in (src.config or {}).items() if k != "_cache"}

    override_applied = source.type != persisted_source.type or _config_sans_cache(
        source
    ) != _config_sans_cache(persisted_source)
    record_era = not override_applied

    # F9 L2 D1: dispatch stdio sources to their dedicated transient-client
    # path. Stdio has no OAuth concept (no Phase 0 / Phase A / Phase B), so
    # the workflow is a straight connect → list_tools → cache → return.
    # Other unsupported transports continue to surface a clear error.
    if source.type == "stdio":
        return (
            await _build_and_test_stdio_mcp(source, source_id, repo, record_era=record_era)
        ), recordable
    if source.type != "streamable-http":
        return (
            {
                "status": "error",
                "error": f"Test only supports streamable-http and stdio; got {source.type!r}",
            }
        ), False

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

    signin_via_discover = False
    # True when Phase B was entered from THIS request's operator-header requests
    # getting 401 (probe verdict "oauth", or DD9's fall-through): the rejection
    # evidence for DD4 path (c). Phase A's stale-token fall-through leaves it False.
    rejection_evidence = False
    cached_posture = (source.config.get("_cache") or {}).get("auth_posture")
    has_live_tokens = bool(
        source.secrets.get("dcr_credentials") and source.secrets.get("access_token")
    )

    # Sortie 09 DD3: a source with a configured-but-blank header ("Set per agent")
    # takes this path BEFORE the cached-posture return and Phase 0's probe. With
    # live sign-in tokens, Phase A runs as today. Without them: the no-auth helper
    # runs without writing `auth_posture`, and only a 401 that names a sign-in
    # (`MCPAuthRequired`) goes on to Phase B -- a bare 401 is a plain
    # "needs a value" error, and no client registration runs.
    missing_entered = False
    if not has_live_tokens and missing_values(source, source):
        missing_result = await _build_and_test_no_auth_mcp(
            source,
            source_id,
            repo,
            record_era=record_era,
            from_fallthrough=True,
            cache_write="shared_no_posture",
            classify=True,
        )
        if missing_result is not _SIGNIN_REQUIRED:
            return missing_result, recordable
        missing_entered = True
        # No `_persist_oauth_posture` here and `rejection_evidence` stays False:
        # the 401 was to a request that lacked the blank header.
        signin_via_discover = True

    if cached_posture == "no_auth" and not has_live_tokens and not missing_entered:
        return (
            await _build_and_test_no_auth_mcp(source, source_id, repo, record_era=record_era)
        ), recordable

    # Re-probe both on a cold cache (None) AND on a cached "oauth" hint when
    # there are no live OAuth tokens. The latter re-validation matters because
    # an operator may have ADDED static-bearer / custom-header auth after an
    # earlier probe cached "oauth" (e.g. a header-auth server first misread as
    # oauth). Re-probing with the operator's headers lets such a source flip to
    # no_auth instead of being permanently pinned to a doomed OAuth flow by the
    # stale cache. A genuine OAuth server simply re-probes to "oauth" again
    # (one cheap round trip on this operator-initiated test path) and falls
    # through to Phase B exactly as before.
    if cached_posture in (None, "oauth") and not has_live_tokens and not missing_entered:
        server_url = source.config.get("url", "")
        # Pass the operator's configured headers (static bearer, custom
        # key/value rows) so a header-auth server probes as no_auth instead
        # of being misclassified as oauth and kicking a doomed DCR flow.
        posture = await _probe_auth_posture(
            server_url, request_headers=build_request_headers(source)
        )
        if posture == "no_auth":
            return (
                await _build_and_test_no_auth_mcp(source, source_id, repo, record_era=record_era)
            ), recordable
        if posture == "error":
            return {"status": "error", "error": "connection probe failed"}, recordable
        if posture == "unexpected_status":
            # DD9: the server answered the probe's bare `initialize` with a
            # status that is neither 200 nor 401 (e.g. 400 from a server that
            # speaks only 2026-07-28). Let the negotiating SDK path decide.
            result = await _build_and_test_no_auth_mcp(
                source, source_id, repo, record_era=record_era, from_fallthrough=True
            )
            if result is not _SIGNIN_REQUIRED:
                return result, recordable
            # The SDK path hit a 401: persist `oauth` (as for a probe `oauth`)
            # and sign in. The server already rejects `initialize`, so Phase B
            # triggers sign-in with `server/discover` (DD10 amendment).
            await _persist_oauth_posture(repo, source_id)
            signin_via_discover = True
            rejection_evidence = True
        else:
            # posture == "oauth": persist the hint BEFORE Phase B fires so a
            # Phase B failure still leaves a definitive signal for the pool
            # worker (rather than inferring auth-required from dcr_credentials
            # presence). Then fall through to Phase B below.
            await _persist_oauth_posture(repo, source_id)
            rejection_evidence = True

    # Phase A: tokens present → build provider WITH consent_url_future=None
    # (test path doesn't kick the OAuth flow yet) and try connect + list_tools.
    # MUST thread auth_provider through MCPClient or the SDK has no way to
    # apply the cached tokens — bare MCPClient sends Bearer-less requests
    # and always 401s, defeating the "tokens present" fast path.
    if source.secrets.get("dcr_credentials") and source.secrets.get("access_token"):
        try:
            return (
                await _connect_with_tokens(
                    source, source_id, repo, record_era=record_era, cache_write="shared"
                )
            ), recordable
        except MCPAuthRequired:
            # Token expired/revoked. Bust pool cache BEFORE Phase B builds
            # a fresh provider so the F4 cache doesn't hand out an MCPClient
            # with the stale auth_provider mid-refresh.
            source = await _clear_stale_oauth_secrets(repo, source_id, source)
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
            looks_like_token_failure = any(m in err_msg for m in TOKEN_FAILURE_MARKERS)
            if looks_like_token_failure:
                source = await _clear_stale_oauth_secrets(repo, source_id, source)
                await _evict_all_for_source(source_id)
                # fall through to Phase B
            else:
                return {"status": "error", "error": f"{type(e).__name__}: {e}"}, recordable
        except MCPVersionMismatch as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}, recordable

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
        return {"status": "error", "error": "OAuth provider construction failed"}, recordable

    await _evict_all_for_source(source_id)

    server_url = source.config.get("url", "")

    def _is_credentials_rejection(exc: Exception) -> bool:
        """DD4 path (c): a failed ``/register`` with no discovered OAuth metadata, after
        this request's operator-header requests already got 401."""
        from mcp.client.auth import OAuthClientProvider, OAuthRegistrationError

        if not rejection_evidence or not configured_names(source):
            return False
        if not isinstance(exc, OAuthRegistrationError):
            return False
        if not str(exc).startswith("Registration failed:"):
            return False
        if not isinstance(provider, OAuthClientProvider):
            return False
        ctx = provider.context
        return ctx.protected_resource_metadata is None and ctx.oauth_metadata is None

    async def _drive_flow_test() -> None:
        """Hit the source URL with the provider attached; SDK runs auth flow."""
        # Lazy import; both versions are read at call time (DD10).
        from mcp.types.version import LATEST_MODERN_VERSION

        from the_one import mcp as the_one_mcp

        if signin_via_discover:
            # DD10 amendment: entered from DD9's fall-through, so the server
            # already rejected `initialize` — trigger sign-in with discover.
            version = LATEST_MODERN_VERSION
            body: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server/discover",
                "params": {},
            }
        else:
            version = the_one_mcp._HANDSHAKE_OFFER_VERSION
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": version,
                    "clientInfo": {"name": "the-one", "version": "0.1"},
                    "capabilities": {},
                },
            }
        try:
            async with httpx2.AsyncClient(auth=provider, timeout=30.0) as client:
                await client.post(server_url, json=body, headers=_oauth_driver_headers(version))
        except Exception as exc:
            if not consent_url_future.done():
                if _is_credentials_rejection(exc):
                    consent_url_future.set_exception(_CredentialsRejectedSignal())
                else:
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
        return {"status": "error", "error": "consent_url_timeout"}, recordable
    except _CredentialsRejectedSignal:
        await _clear_auth_posture(repo, source_id)
        rejected = MCPCredentialsRejected(source_id=source_id, source_name=source.name)
        return {"status": "error", "error": f"MCPCredentialsRejected: {rejected}"}, recordable
    except Exception as e:
        return {"status": "error", "error": f"auth_flow_error: {e}"}, recordable

    return {"status": "auth_required", "consent_url": consent_url}, recordable


# ── Connector Accounts (Mission 23 Flight 2 Leg 2, DD-7) ───────────────────
#
# Seven CRUD/doctor/pairing routes over the kept ``connectors`` table, plus
# an eighth ``/connectors/types`` route (design review Q2) gating "stub"
# creatability behind the same dual gate as the two test seams below.
# Masking mirrors the MCP source pattern (``Connector.secrets`` is a
# free-form dict like ``MCPSource.secrets``) — reuses ``_mask_secrets`` /
# ``_looks_masked`` verbatim, NOT the single-column ``_mask_api_key``
# pattern. PUT always stops the old listener and starts a fresh one from
# the just-persisted row (Edge Cases: "MUST NOT leave a listener running on
# stale credentials" — unconditional restart is the implementer's-choice
# variation that satisfies this without a connection-relevant-change diff).


def _connector_response(account: Connector) -> dict[str, Any]:
    """Render a Connector into the masked HTTP response shape.

    Mirrors ``_mcp_source_response`` minus the OAuth-managed-keys strip
    (connectors have no OAuth-managed keys) and the ``_cache`` flag (no
    lazy-install cache to reflect). ``model_dump()`` populates
    ``data["secrets"]`` with the decrypted plaintext dict; the overwrite
    below is the load-bearing anti-leak step — see
    ``tests/test_api_secret_mask_roundtrip.py``.
    """
    data = account.model_dump()
    data["secrets"] = _mask_secrets(account.secrets)
    return data


def _creatable_connector_types() -> set[str]:
    """Types selectable in the UI / accepted by ``create_connector`` on
    THIS running instance. "discord" is always creatable (Flight 3 ships
    the plugin; the type exists on the model today per DD-1); "telegram"
    joins it unconditionally (Mission 23 Flight 4 DD-1b — the plugin ships
    in leg 2, but the type is admitted here in leg 1's lockstep set same
    as "discord" was in Flight 3). "stub" is creatable only when BOTH
    gates are open — ``settings.dev_mode`` AND
    ``THE_ONE_STUB_TEST_ENDPOINT=1`` — the same dual gate as the two
    ``/_test/stub/...`` seams below and the lifespan startup hook that
    registers the stub plugin (``interfaces/web/app.py``). Mirrors the
    provider/MCP ``/types`` precedent (``list_provider_types`` /
    ``list_mcp_source_types``)."""
    types = {"discord", "telegram"}
    if settings.dev_mode and os.environ.get("THE_ONE_STUB_TEST_ENDPOINT") == "1":
        types.add("stub")
    return types


async def _connector_doctor_warnings(account: Connector) -> list[str]:
    """Binding-health warnings (DD-4 trade-offs): a connector's
    ``default_agent`` may not exist, or may exist but lack the send tool
    — both are operator foot-guns the doctor probe surfaces alongside the
    plugin's own report, never as a crash."""
    from the_one.tools.connector_send import SEND_TO_PLATFORM_CHANNEL_TOOL_NAME

    warnings: list[str] = []
    default_agent = account.config.get("default_agent")
    if not default_agent:
        warnings.append("no default_agent configured — this connector cannot serve traffic")
        return warnings
    store = await _agent_store()
    if not await store.exists(default_agent):
        warnings.append(f"default_agent {default_agent!r} does not exist")
        return warnings
    agent_cfg = await store.load(default_agent)
    if not agent_cfg.is_tool_enabled(SEND_TO_PLATFORM_CHANNEL_TOOL_NAME):
        warnings.append(f"agent {default_agent!r} does not have the send tool enabled")
    return warnings


@router.get("/connectors")
async def list_connectors() -> list[dict[str, Any]]:
    repo = await _connector_repo()
    return [_connector_response(a) for a in await repo.list()]


@router.get("/connectors/types")
async def list_connector_types() -> list[dict[str, str]]:
    """MUST be registered BEFORE ``/connectors/{connector_id}`` — FastAPI
    matches routes in registration order; reordering would resolve GET
    ``/connectors/types`` to ``get_connector`` with ``connector_id="types"``
    and 404. Mirrors ``list_mcp_source_types`` / ``list_provider_types``."""
    return [{"value": t, "label": t.capitalize()} for t in sorted(_creatable_connector_types())]


@router.get("/connectors/{connector_id}")
async def get_connector(connector_id: str) -> dict[str, Any]:
    repo = await _connector_repo()
    try:
        account = await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    return _connector_response(account)


@router.post("/connectors", status_code=201)
async def create_connector(request: Request) -> dict[str, Any]:
    data = await _read_json(request)
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    # Edge Case: a masked sentinel on CREATE is rejected — there is no
    # stored secret yet to preserve.
    incoming_secrets = data.get("secrets")
    if isinstance(incoming_secrets, dict):
        for key, value in incoming_secrets.items():
            if _looks_masked(value):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"secrets[{key!r}] is a masked placeholder; there is no stored "
                        "secret to preserve on create."
                    ),
                )
    try:
        account = Connector.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    if account.type not in _creatable_connector_types():
        raise HTTPException(
            status_code=422,
            detail=f"Connector type {account.type!r} is not creatable on this instance.",
        )
    repo = await _connector_repo()
    await repo.create(account)
    # Edge Case: a connector must start listening on create, not only on
    # the next app restart. DD-6: honor ``enabled`` (absent key = enabled)
    # — a connector created with ``enabled: false`` does not start.
    manager = get_connector_manager()
    if manager is not None and account.config.get("enabled", True) is not False:
        manager.start(account, get_encryptor(settings.data_dir), repo=repo)
    return _connector_response(account)


def _merge_paired_peers(stored_config: Any, incoming: Any, base: list[str]) -> Any:
    """Three-way merge of ``allowlist.peers`` (squawk 0288).

    Result: the operator's incoming peers, then peers present in the stored
    config but not in ``base`` (paired since the editor loaded). Returns a
    copy of ``incoming`` with the merged peers, or ``incoming`` itself when
    its shape is malformed so the model validator raises its usual 422.
    Never mutates its arguments.
    """
    if not isinstance(incoming, dict):
        return incoming
    allowlist = incoming.get("allowlist")
    if allowlist is not None and not isinstance(allowlist, dict):
        return incoming
    in_peers = (allowlist or {}).get("peers")
    if in_peers is None:
        in_peers = []
    if not isinstance(in_peers, list) or not all(isinstance(p, str) for p in in_peers):
        return incoming
    stored_al = stored_config.get("allowlist") if isinstance(stored_config, dict) else None
    stored_peers = stored_al.get("peers") if isinstance(stored_al, dict) else None
    if not isinstance(stored_peers, list):
        stored_peers = []
    base_set = set(base)
    merged_peers = list(dict.fromkeys(in_peers))
    for p in stored_peers:
        if isinstance(p, str) and p not in base_set and p not in merged_peers:
            merged_peers.append(p)
    if not merged_peers:
        return incoming
    out = dict(incoming)
    out_al = dict(allowlist or {})
    out_al["peers"] = merged_peers
    out["allowlist"] = out_al
    return out


@router.put("/connectors/{connector_id}")
async def update_connector(connector_id: str, request: Request) -> dict[str, Any]:
    data = await _read_json(request)
    data["id"] = connector_id
    repo = await _connector_repo()
    try:
        existing = await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")

    # Per-key __MASKED__ resolution — verbatim mirror of the MCP source PUT
    # handler's block (minus the OAuth-managed-keys step, which has no
    # connector analog).
    incoming_secrets = data.get("secrets")
    if incoming_secrets is not None:
        if not isinstance(incoming_secrets, dict):
            raise HTTPException(status_code=422, detail="secrets must be a dict.")
        resolved_secrets: dict[str, Any] = {}
        for key, value in incoming_secrets.items():
            if _looks_masked(value):
                if key in existing.secrets:
                    resolved_secrets[key] = existing.secrets[key]
                # else: client sent __MASKED__ for a key we don't have; drop
                # it silently — same as an omitted key.
            else:
                resolved_secrets[key] = value
        data["secrets"] = resolved_secrets

    # Squawk 0288: the editor sends the peers it last loaded/saved so a peer
    # paired meanwhile (``_pair_peer``) survives a stale Save. Never stored.
    peers_base = data.pop("allowlist_peers_base", None)
    if peers_base is not None:
        if not isinstance(peers_base, list) or not all(isinstance(p, str) for p in peers_base):
            raise HTTPException(
                status_code=422, detail="allowlist_peers_base must be a list of strings."
            )
        data["config"] = _merge_paired_peers(existing.config, data.get("config"), peers_base)

    # ``model_copy(update=...)`` does NOT re-run field validators in
    # Pydantic v2 — round-trip through model_dump()|data→model_validate so
    # the DD-2 config validator fires on the merged payload. Mirrors
    # ``update_mcp_source``.
    try:
        merged = existing.model_dump()
        merged.update(data)
        updated = Connector.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    if updated.type not in _creatable_connector_types():
        raise HTTPException(
            status_code=422,
            detail=f"Connector type {updated.type!r} is not creatable on this instance.",
        )
    await repo.update(updated)

    # PUT restarting semantics (DD-6, amended leg-2 design review
    # 2026-09-01): branch on the NEW row's effective ``enabled`` value
    # ONLY — never on whether it changed. Effective true (covers
    # enabled→enabled config edits AND disabled→enabled) → today's
    # unconditional stop+start, satisfying "no stale-credential listener
    # survives a save". Effective false (covers enabled→disabled AND
    # disabled→disabled) → stop only, NEVER start — the original
    # "restart-as-today" framing let a disabled→disabled PUT on an
    # unrelated field wake a listener that should stay down. ``repo`` is
    # threaded through so the DD-Q3 rotation fix's fresh-row re-fetch
    # applies to this listener's future reconnects too.
    # Squawk 0033: this stop() before start() is load-bearing — see the
    # stale-entry invariant documented on ConnectorManager._run's
    # PermanentConnectorFailure branch (connectors/manager.py).
    manager = get_connector_manager()
    if manager is not None:
        await manager.stop(connector_id)
        if updated.config.get("enabled", True) is not False:
            manager.start(updated, get_encryptor(settings.data_dir), repo=repo)

    return _connector_response(updated)


@router.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str) -> dict[str, str]:
    """DELETE stops the listener BEFORE the row dies (DD-7); DD-1g's
    directory cleanup runs after the connector row itself is confirmed
    gone (a deterministic DELETE — no FK/cascade, per DD-4)."""
    repo = await _connector_repo()
    try:
        await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    manager = get_connector_manager()
    if manager is not None:
        await manager.stop(connector_id)
    try:
        await repo.delete(connector_id)
    except KeyError:
        # Race: another caller deleted between our get and delete.
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    directory_repo = await _connector_directory_repo()
    await directory_repo.delete_for_connector(connector_id)
    return {"status": "ok"}


@router.post("/connectors/{connector_id}/test")
async def test_connector(connector_id: str) -> dict[str, Any]:
    """Doctor probe: plugin report + binding-health warnings (DD-4).

    With no plugin registered for the type — the NORM this flight, since
    Discord lands Flight 3 — this returns a clean degraded/failed report,
    never a crash (design review catch #1). Doctor runs on a disabled
    connector too — diagnosis, not traffic — and the response's
    ``disabled`` field distinctly marks that state (DD-6, Mission 23
    Flight 3 Leg 2; supersedes the prior "no enabled gate to check" note).
    A connector can be both disabled AND carry a stale plugin-side
    permanent-failure marker (disabled after a permanent failure); the two
    facts are independent and both surface — disabled never masks a prior
    failure, and vice versa.
    """
    repo = await _connector_repo()
    try:
        account = await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")

    plugin = connector_registry.get_plugin(account.type)
    if plugin is None:
        report = DoctorReport(
            status="failed",
            message=f"no plugin registered for type {account.type!r}",
        )
    else:
        try:
            report = await plugin.doctor(account, get_encryptor(settings.data_dir))
        except ConnectorClientError as exc:
            report = DoctorReport(status="failed", message=str(exc))
        except Exception as exc:
            logger.exception("connector %s: doctor probe raised", connector_id)
            report = DoctorReport(status="failed", message=f"doctor probe raised: {exc}")

    warnings = await _connector_doctor_warnings(account)
    return {
        "status": report.status,
        "message": report.message,
        "details": report.details,
        "warnings": warnings,
        "disabled": account.config.get("enabled", True) is False,
    }


@router.post("/connectors/{connector_id}/pairing-code")
async def generate_connector_pairing_code(connector_id: str) -> dict[str, str]:
    """Generate (or regenerate) the one-time pairing code (DD-3).

    404s on an unknown connector id — repo-checked FIRST, before touching
    the manager's in-memory pairing store. A second request replaces
    (invalidates) the first: ``ConnectorManager.generate_pairing_code``
    simply overwrites the prior ``_PairingEntry`` for this connector id.
    Allowed even when the connector's listener isn't running — the code
    just expires unused by TTL (Edge Case, stated rather than left
    implicit).
    """
    repo = await _connector_repo()
    try:
        await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    manager = get_connector_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="connector manager is not running")
    code = manager.generate_pairing_code(connector_id)
    from datetime import datetime, timedelta, timezone

    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=PAIRING_TTL_SECONDS)).isoformat()
    return {"code": code, "expires_at": expires_at}


# ── Connector test seams (DD-10 stub; DD-7 sever) — dual-gated like
# purge-sweep ─────────────────────────────────────────────────────────────
#
# The two stub seams below gate on ``settings.dev_mode`` AND
# ``THE_ONE_STUB_TEST_ENDPOINT=1``: they inject free text into a live agent
# loop with LLM calls and tool execution — purge-sweep's risk profile, not
# the inert-metadata oauth/pending seam's. The old
# ``THE_ONE_REGISTER_STUB_CONNECTOR`` name is fully absent and not
# resurrected (design review 2026-08-31). The Discord sever seam further
# below (Mission 23 Flight 3 Leg 3, DD-7) gates on ``settings.dev_mode`` AND
# ``THE_ONE_DISCORD_TEST_ENDPOINT=1`` — its own name, not reusing the stub
# gate, per ``risk-tiered-test-seam-gating`` (`the_one/agents.md`).


@router.post("/_test/stub/inbound")
async def stub_test_inbound(request: Request) -> dict[str, Any]:
    """Inject an inbound envelope into the stub plugin's live connection.

    The act path for the ``stub-connector-round-trip`` behavior test (leg
    3) and this leg's own route tests — drives admission/pairing/reply
    without a real platform. Requires the stub plugin to already be
    connected for ``connector_id`` (via the lifespan startup hook, or a
    test's own ``registry.register_for_test`` + manager start).
    """
    if not settings.dev_mode or os.environ.get("THE_ONE_STUB_TEST_ENDPOINT") != "1":
        raise HTTPException(
            status_code=403,
            detail="test-seam endpoint requires dev_mode + THE_ONE_STUB_TEST_ENDPOINT=1",
        )
    from the_one.connectors.stub import StubPlugin

    body = await _read_json(request)
    envelope = InboundEnvelope(
        platform="stub",
        connector_id=body["connector_id"],
        channel_id=body.get("channel_id", ""),
        thread_id=body.get("thread_id"),
        peer_id=body["peer_id"],
        peer_name=body.get("peer_name", body["peer_id"]),
        text=body["text"],
        is_dm=bool(body.get("is_dm", False)),
        mentions_bot=bool(body.get("mentions_bot", False)),
        peer_username=body.get("peer_username"),
    )
    try:
        await StubPlugin.push_inbound(body["connector_id"], envelope)
    except ConnectorClientError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "ok"}


@router.get("/_test/stub/outbound")
async def stub_test_outbound() -> dict[str, Any]:
    """Read the stub plugin's recorded outbound sends — the observe path
    proving what did/didn't reach the "platform" (DD-10)."""
    if not settings.dev_mode or os.environ.get("THE_ONE_STUB_TEST_ENDPOINT") != "1":
        raise HTTPException(
            status_code=403,
            detail="test-seam endpoint requires dev_mode + THE_ONE_STUB_TEST_ENDPOINT=1",
        )
    from the_one.connectors.stub import StubPlugin

    records = []
    for rec in StubPlugin.outbound_records:
        target, content = rec
        item: dict[str, Any] = {
            "connector_id": getattr(target, "connector_id", None),
            "channel_id": getattr(target, "channel_id", None),
            "peer_id": getattr(target, "peer_id", None),
            "content": content,
        }
        images = getattr(rec, "images", None)
        if images:
            item["images"] = [
                {
                    "filename": img.filename,
                    "title": img.title,
                    "width": img.width,
                    "height": img.height,
                    "size": len(img.data),
                    "sha256": hashlib.sha256(img.data).hexdigest(),
                }
                for img in images
            ]
        records.append(item)
    return {"records": records}


@router.post("/_test/discord/sever")
async def discord_test_sever(request: Request) -> dict[str, Any]:
    """Controlled-disconnect test seam (Mission 23 Flight 3 Leg 3, DD-7):
    abruptly severs a LIVE connector's gateway websocket via the OPTIONAL
    ``sever_for_test`` hook — never a production kill switch. Reached ONLY
    via ``manager.client_for`` + ``getattr`` (never a Discord-specific
    import), so the seam is platform-agnostic: Telegram inherits it for
    free once its client defines the hook. Same dual gate shape as the
    stub seams above, named per ``risk-tiered-test-seam-gating``
    (`the_one/agents.md`); raw ``Request`` + manual ``await
    request.json()`` for the same reason those seams use it — a Pydantic
    body model would let FastAPI 422 an empty body BEFORE the gate line
    runs.

    Error taxonomy (design review 2026-09-01): ``client_for`` returns the
    identical ``None`` for a never-started listener and one that's
    mid-backoff — it cannot carry the 404/409 distinction alone, so a
    repo-existence check runs FIRST, mirroring
    ``generate_connector_pairing_code``'s ``repo.get`` -> ``KeyError`` ->
    404 idiom: unknown connector -> 404; row exists but no live client
    (mid-backoff or never started) -> 409; client present but no
    ``sever_for_test`` hook (e.g. a stub-typed connector) -> an explicit
    501, never a silent no-op.
    """
    if not settings.dev_mode or os.environ.get("THE_ONE_DISCORD_TEST_ENDPOINT") != "1":
        raise HTTPException(
            status_code=403,
            detail="test-seam endpoint requires dev_mode + THE_ONE_DISCORD_TEST_ENDPOINT=1",
        )
    body = await _read_json(request)
    connector_id = body["connector_id"]

    repo = await _connector_repo()
    try:
        await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")

    manager = get_connector_manager()
    client = manager.client_for(connector_id) if manager is not None else None
    if client is None:
        raise HTTPException(status_code=409, detail=f"no live client for connector {connector_id}")

    sever = getattr(client, "sever_for_test", None)
    if sever is None:
        raise HTTPException(
            status_code=501,
            detail=f"connector {connector_id}'s client has no sever_for_test hook",
        )
    sever()
    return {"status": "ok"}


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

    The page is a self-contained HTML document served to the window the OAuth
    flow opened, which is the system browser on the desktop app: it has no
    session cookie, so every ``/static/`` request it made returned 401 and the
    page rendered unstyled (squawk 0214). It therefore links nothing under
    ``/static/``: its styles are inline, with an explicit minimal subset of the
    design tokens (pinned to ``tokens.css`` and ``fonts.css`` by
    ``tests/test_oauth_callback_page_static.py``), light by default and dark under
    ``prefers-color-scheme``, in the system font stack.

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

    The page follows the browser's light or dark preference; an explicit in-app
    theme choice is not available here (the page cannot read it without a session).
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
<style>
  :root {{
    color-scheme: light dark;
    --bg: #ffffff;
    --surface: #fafafa;
    --border: #e4e4e7;
    --fg: #18181b;
    --fg-secondary: #52525b;
    --fg-muted: #65656e;
    --radius-lg: 12px;
    --shadow-popover: 0 4px 12px rgb(0 0 0 / 0.10);
    --font-size-h1: 18px;
    --font-size-body: 13px;
    --font-size-tiny: 10px;
    --font-weight-semibold: 600;
    --font-weight-bold: 700;
    --line-height-tight: 1.2;
    --line-height-normal: 1.5;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #101114;
      --surface: #17181c;
      --border: #26272c;
      --fg: #ededf0;
      --fg-secondary: #adafb7;
      --fg-muted: #8f9199;
    }}
  }}
  html, body {{ margin: 0; padding: 0; height: 100%; }}
  body {{
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
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
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-popover);
    text-align: left;
  }}
  .oauth-callback-eyebrow {{
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    font-size: var(--font-size-tiny);
    font-weight: var(--font-weight-bold);
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--fg-secondary);
    margin: 0 0 16px;
  }}
  .oauth-callback-heading {{
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
<main class="oauth-callback-card">
  <p class="oauth-callback-eyebrow">gleepglorp ai — oauth</p>
  <h1 class="oauth-callback-heading">{heading}</h1>
  <div role="status">
    <p class="oauth-callback-detail">{detail_html}</p>
  </div>
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
    iss: str | None = None,
) -> HTMLResponse:
    """Loopback redirect target for the OAuth 2.1 + PKCE flow.

    The operator's IDP consent page redirects the browser tab to
    ``/api/oauth/callback?code=...&state=...`` (success) or
    ``?error=...&error_description=...&state=...`` (denial). This
    handler:

      1. Looks up the pending flow keyed by ``state``.
      2. On success, calls ``_state.resolve(state, code, state, iss)`` (``iss``
         is the optional RFC 9207 issuer query parameter) to
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
    resolved = oauth_state.resolve(state, code or "", state, iss)
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

    data = await _read_json(request)
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
            async with httpx2.AsyncClient(auth=provider, timeout=30.0) as client:
                # The ``initialize`` JSON-RPC request returns 401 when no
                # token is present; the provider's ``async_auth_flow``
                # intercepts, runs PRM/OASM/DCR/auth, and the
                # ``redirect_handler`` broadcasts ``auth_required`` with
                # the real ``consent_url``.
                # DD10: read the handshake offer at call time; the header makes
                # the SDK's 401 handling include the RFC 8707 ``resource``.
                from the_one import mcp as the_one_mcp

                version = the_one_mcp._HANDSHAKE_OFFER_VERSION
                await client.post(
                    server_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": version,
                            "clientInfo": {"name": "the-one", "version": "0.1"},
                            "capabilities": {},
                        },
                    },
                    headers=_oauth_driver_headers(version),
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
    data = await _read_json(request)
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    try:
        session = ChatSession.model_validate(data)
    except ValidationError as e:
        # Squawk 0081: invalid input is a 422, not an unhandled 500.
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    repo = await _chat_repo()
    await repo.create(session)
    return _session_summary(session)


@router.put("/chat/sessions/{session_id}")
async def update_chat_session(session_id: str, request: Request) -> dict[str, Any]:
    data = await _read_json(request)
    data["id"] = session_id
    repo = await _chat_repo()
    try:
        existing = await repo.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")

    # ``model_copy(update=...)`` does NOT re-run field validators in
    # Pydantic v2, so a malformed PUT would silently bypass validation
    # and corrupt the stored row. Round-trip through ``model_dump() |
    # data → model_validate(...)`` so the validator fires on the merged
    # payload. Mirrors ``update_connector`` (M10 F2 L6). Squawk 0013.
    try:
        merged = existing.model_dump()
        merged.update(data)
        updated = ChatSession.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
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
    # M33 F1 (DD1): run history refers to the chats just deleted; the routines stay.
    runs_deleted = await RoutineRunRepository(repo.conn).delete_all_for_agent(name)
    # M33 F3 (DD4): resolved routine changes go too; pending ones and routines stay.
    proposals_deleted = await RoutineProposalRepository(repo.conn).delete_resolved_for_agent(name)
    return {
        "status": "ok",
        "deleted": deleted,
        "runs_deleted": runs_deleted,
        "proposals_deleted": proposals_deleted,
    }


@router.post("/chat/sessions/{session_id}/purge")
async def purge_chat_messages(session_id: str) -> dict[str, str]:
    repo = await _chat_repo()
    try:
        await repo.purge_messages(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return {"status": "ok"}


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
    return {
        "deleted": result["deleted"],
        "runs_deleted": result["runs_deleted"],
        "routines_deleted": result["routines_deleted"],
        "proposals_deleted": result["proposals_deleted"],
        "last_purge_at": result["last_purge_at"],
    }


class _PendingOAuthFlowBody(BaseModel):
    """Typed body for `POST /_test/oauth/pending`, deliberately unlike the
    sibling `/_test/` seams above (which parse `request.json()` by hand) —
    a typed model is a better fit for a four-field registration payload and
    the mismatch is not drift."""

    state: str
    source_id: str
    chat_session_id: str
    tool_call_id: str | None = None


@router.post("/_test/oauth/pending")
async def seed_pending_oauth_flow(body: _PendingOAuthFlowBody) -> dict[str, str]:
    """Mission 22 / Flight 01 / Leg 03 — dual-gated test seam (dev mode AND
    ``THE_ONE_OAUTH_TEST_ENDPOINT=1``, checked at request time).

    Registers a pending OAuth flow (`the_one.mcp.oauth._state.register`) so
    an out-of-process caller can seed one over HTTP. Only in-process code
    can otherwise create a pending flow, which is fine for the unit-test
    suite (it imports `_state` directly) but not for a browser-lane test
    driving a spawned app subprocess — this seam exists solely so
    `tests/browser/test_flow_oauth_callback_cross_site.py` can seed a flow
    before navigating to `/api/oauth/callback`. It helps forge an OAuth
    callback, so it carries its own flag like the sibling `/_test/` seams
    (403 unless both gates are open).
    """
    if not settings.dev_mode or os.environ.get("THE_ONE_OAUTH_TEST_ENDPOINT") != "1":
        raise HTTPException(
            status_code=403,
            detail="test-seam endpoint requires dev_mode + THE_ONE_OAUTH_TEST_ENDPOINT=1",
        )
    from the_one.mcp.oauth import _state as oauth_state

    try:
        oauth_state.register(
            body.state,
            source_id=body.source_id,
            tool_call_id=body.tool_call_id,
            chat_session_id=body.chat_session_id,
        )
    except RuntimeError:
        raise HTTPException(
            status_code=409,
            detail=f"pending OAuth flow already registered for state: {body.state!r}",
        )
    return {"state": body.state}


def _session_summary(session: ChatSession) -> dict[str, Any]:
    # M25 F4 L1 (DD4): ``platform`` is the one scalar connector field the
    # summary carries (null for a UI session), so the client store's REST
    # ``sessions`` rows match the WebSocket ``session_list`` rows it primes
    # from. Rich routing data (``session_metadata``) stays detail-only.
    # Keys must stay a subset of app.py's ``_session_to_list_payload``
    # (pinned by tests/test_db_api.py).
    return {
        "id": session.id,
        "agent_name": session.agent_name,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "platform": session.platform,
        # M31 F6 L10b: same two keys as app.py's ``_session_to_list_payload``.
        "busy": is_session_busy(session.id),
        "turn_seq": turn_seq(session.id),
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

# Server-stamped key in ``llm_providers.secrets`` for the
# ``anthropic-plan-token`` type (sortie 03 DD3): when the pasted token was
# set (``now_iso()``). Pinned from the stored row on every update, written
# only by create / a changed token, never client-seedable, stripped from
# every response (``_provider_response`` exposes ``token_set_at`` instead).
_PLAN_TOKEN_MANAGED_KEYS = ("token_set_at",)

_PLAN_TOKEN_TYPE = "anthropic-plan-token"
_PLAN_TOKEN_MISSING_DETAIL = "Paste a token from claude setup-token."
_PLAN_TOKEN_API_KEY_DETAIL = (
    "That is an Anthropic API key. Use the Anthropic provider type for API keys; "
    "Claude Plan (Token) takes a token from `claude setup-token`."
)


def _check_plan_token(api_key: str | None) -> None:
    """DD2 / DD4: require a token and refuse an Anthropic API key (422).

    Never echoes the submitted value.
    """
    if not api_key:
        raise HTTPException(status_code=422, detail=_PLAN_TOKEN_MISSING_DETAIL)
    if api_key.startswith("sk-ant-api"):
        raise HTTPException(status_code=422, detail=_PLAN_TOKEN_API_KEY_DETAIL)


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
    # Gated on the type: only ``anthropic-plan`` signs in through OAuth.
    data["oauth_active"] = provider.type == "anthropic-plan" and bool(
        secrets_dict.get("access_token") and secrets_dict.get("refresh_token")
    )
    # Token type (sortie 03 DD3): the server-stamped paste date and the
    # derived "expires around" date; null for every other type.
    token_set_at: str | None = None
    token_expires_around: str | None = None
    if provider.type == _PLAN_TOKEN_TYPE:
        stamp = secrets_dict.get("token_set_at")
        if isinstance(stamp, str) and stamp:
            token_set_at = stamp
            try:
                set_dt = datetime.fromisoformat(stamp)
                token_expires_around = (
                    set_dt + timedelta(days=anthropic_oauth.PLAN_TOKEN_LIFETIME_DAYS)
                ).isoformat()
            except ValueError:
                token_expires_around = None
    data["token_set_at"] = token_set_at
    data["token_expires_around"] = token_expires_around
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
    # Picker order is fixed; labels come from the one dict (db/_provider_types.py).
    types = [
        {"value": t, "label": PROVIDER_TYPE_LABELS[t]}
        for t in (
            "ollama",
            "openai-compatible",
            "openai",
            "anthropic",
            "anthropic-plan",
            "anthropic-plan-token",
            "openrouter",
        )
    ]
    if settings.dev_mode:
        types.append({"value": "mock", "label": PROVIDER_TYPE_LABELS["mock"]})
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
    data = await _read_json(request)
    if data.get("type") == "mock" and not settings.dev_mode:
        raise HTTPException(
            status_code=400,
            detail="Mock provider type requires THE_ONE_DEV_MODE=true",
        )
    data["name"] = _checked_name(data.get("name"))
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    # DD-2 create direction: secrets are OAuth-managed — force-empty
    # regardless of the client-supplied body. Token material enters ONLY
    # via the /oauth/code exchange path.
    data["secrets"] = {}
    try:
        provider = LLMProviderConfig.model_validate(data)
    except ValidationError as e:
        # Squawks 0112 / 0081: a missing field is a 422. ``include_input=False``
        # keeps the submitted ``api_key`` out of the response.
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    # Token plan type (sortie 03 DD2-DD4): runs on the validated (stripped)
    # key, then stamps when it was set. The stamp is server-owned.
    if provider.type == _PLAN_TOKEN_TYPE:
        _check_plan_token(provider.api_key)
        provider = provider.model_copy(update={"secrets": {"token_set_at": now_iso()}})
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
    data = await _read_json(request)
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

    # Sortie 03 DD2: did this request carry a freshly pasted key? Captured
    # from the RAW body, before masked-key resolution erases the difference.
    # A type change INTO the token type requires one.
    raw_key = data.get("api_key")
    fresh_key_supplied = (
        isinstance(raw_key, str) and raw_key.strip() != "" and not _looks_masked(raw_key)
    )

    # Detect masked API key and preserve existing stored key
    incoming_key = data.get("api_key")
    if _looks_masked(incoming_key):
        data["api_key"] = existing.api_key

    # DD-2 / sortie 03 DD3, DD11: server-managed secret keys are never taken
    # from the client. A dict is put into validation here; the real secrets
    # (OAuth keys pinned from the stored row only for ``anthropic-plan``, the
    # token stamp only for ``anthropic-plan-token``) are built below on the
    # RESOLVED type, so a PUT can neither overwrite nor seed them and a PUT
    # that omits ``secrets`` preserves them.
    data["secrets"] = {}

    # ``model_copy(update=...)`` does NOT re-run field validators in
    # Pydantic v2, so a malformed PUT would silently bypass validation
    # and corrupt the stored row. Round-trip through ``model_dump() |
    # data → model_validate(...)`` so the validator fires on the merged
    # payload. Mirrors ``update_connector`` (M10 F2 L6). Squawk 0013.
    try:
        merged = existing.model_dump()
        merged.update(data)
        if "name" in data:
            merged["name"] = _checked_name(merged["name"])
        updated = LLMProviderConfig.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))

    # Pin / force / check / stamp by the RESOLVED type (DD2-DD4, DD11).
    resolved_secrets: dict[str, Any] = {}
    overrides: dict[str, Any] = {}
    if updated.type == "anthropic-plan":
        for key in _PLAN_OAUTH_MANAGED_KEYS:
            if key in existing.secrets:
                resolved_secrets[key] = existing.secrets[key]
        # The OAuth type never uses ``api_key``; do not leave a token
        # behind, invisible and unclearable, under a type that ignores it.
        overrides["api_key"] = None
    elif updated.type == _PLAN_TOKEN_TYPE:
        entering = existing.type != _PLAN_TOKEN_TYPE
        if entering and not fresh_key_supplied:
            raise HTTPException(status_code=422, detail=_PLAN_TOKEN_MISSING_DETAIL)
        _check_plan_token(updated.api_key)
        stamp = existing.secrets.get("token_set_at") if not entering else None
        if not stamp or updated.api_key != existing.api_key:
            stamp = now_iso()
        resolved_secrets["token_set_at"] = stamp
    overrides["secrets"] = resolved_secrets
    updated = updated.model_copy(update=overrides)

    # URL safety check on the RESOLVED base_url — i.e. after the
    # model_dump()|data round-trip above has merged any
    # ``__MASKED__``-preserved fields. This blocks the regression where a
    # request that does not touch ``base_url`` would otherwise let an
    # unsafe stored value survive an update.
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

    data = await _read_json(request)
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
        elif provider.type == _PLAN_TOKEN_TYPE:
            import anthropic

            from the_one.llm.anthropic_plan_provider import (
                PLAN_TOKEN_MISSING_MESSAGE,
                PLAN_TOKEN_REJECTED_MESSAGE,
            )

            # Check BEFORE building a client: with ``auth_token=None`` the SDK
            # would fall back to ``ANTHROPIC_AUTH_TOKEN`` from the environment.
            if not provider.api_key:
                return {"status": "error", "detail": PLAN_TOKEN_MISSING_MESSAGE}
            try:
                client = _plan_bearer_client(anthropic, provider.api_key)
                await client.models.list()
                return {"status": "ok", "detail": "Connected to Anthropic (plan token)"}
            except anthropic.AuthenticationError:
                return {"status": "error", "detail": PLAN_TOKEN_REJECTED_MESSAGE}
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

    elif provider.type == _PLAN_TOKEN_TYPE:
        from the_one.llm.model_catalog import context_window_for, models_for

        static_catalog = [
            {"id": model_id, "name": model_id, "context_length": window}
            for model_id, window in sorted(models_for("anthropic").items())
        ]
        # No token: serve the static catalog without building a client (the
        # SDK would read ``ANTHROPIC_AUTH_TOKEN`` from the environment).
        if not provider.api_key:
            return static_catalog
        try:
            import anthropic

            client = _plan_bearer_client(anthropic, provider.api_key)
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
                "anthropic-plan-token: live model listing failed for provider %r; "
                "serving static catalog fallback",
                provider_id,
                exc_info=True,
            )
            return static_catalog

    return []


# ── Ollama Model Lifecycle ────────────────────────────────────────────────


@router.post("/providers/{provider_id}/models/pull")
async def pull_model(provider_id: str, request: Request) -> StreamingResponse:
    base_url = await _get_ollama_base_url(provider_id)
    data = await _read_json(request)
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
    data = await _read_json(request)
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
    data = await _read_json(request)
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
    data = await _read_json(request)
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


@router.get("/ollama-library/search")
async def search_ollama_library(q: str = "") -> dict[str, Any]:
    """Every pullable Ollama ``name:tag`` with its download size and status.

    Returns ``{"loading": bool, "models": [{"name", "size", "status"}]}``. While the
    catalog is still filling (``loading``), the panel re-requests. See
    ``the_one/llm/ollama_library.py``.
    """
    return await ollama_library.search(q)


@router.get("/ollama-library/size")
async def ollama_library_size(model: str = "") -> dict[str, Any]:
    """Re-check one entry's download size (the Pull click). 422 on an invalid name."""
    try:
        return await ollama_library.size(model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Encryption ───────────────────────────────────────────────────────────


# app_metadata key holding the UTC ISO time of the last key rotation (B12).
ENCRYPTION_LAST_ROTATED_KEY = "encryption_last_rotated_at"


@router.get("/encryption/status")
async def encryption_status() -> dict[str, Any]:
    """Read-only facts for the Encryption page (M31 F4 L08b, B12).

    ``last_rotated_at`` is the UTC ISO time the rotate route last committed a
    rotation on this install (``None`` before the first). ``credential_count``
    is the number of items holding at least one non-empty secret across the
    eight encrypted corpora: one per provider, MCP source, connector, agent,
    tool config, external credential and Library secret (a provider with an API key and a
    secrets blob counts once). It is computed by decrypting in-process
    (``the_one.db.encryption_corpora``); nothing decrypted leaves it.
    ``key_file_pending`` is true while a rotated key is staged but not yet
    promoted to the key file (the ``.next`` sidecar exists), so a staged
    rotation keeps its warning across a reload. The count is the same whether the
    key came from the key file or the environment (``encryptor.key_path`` is
    ``None``): decryption uses the in-memory key. No secret material is returned.
    """
    encryptor = get_encryptor(settings.data_dir)
    conn = await get_connection()
    last_rotated_at: str | None = None
    try:
        last_rotated_at = await AppMetadataRepository(conn).get(ENCRYPTION_LAST_ROTATED_KEY)
    except aiosqlite.OperationalError:
        pass
    corpora = await gather_corpora(conn, encryptor, strict=False)
    count = count_items_with_secrets(corpora)
    pending = encryptor.pending_key is not None or (
        encryptor.key_path is not None and next_key_path(encryptor.key_path).exists()
    )
    return {
        "last_rotated_at": last_rotated_at,
        "credential_count": count,
        "key_file_pending": pending,
    }


@router.post("/encryption/rotate")
async def rotate_encryption_key() -> dict[str, str]:
    """Rotate the encryption key with a crash-safe two-phase sidecar handoff.

    Re-encrypts every LLM provider row's ``api_key`` AND ``secrets`` blob
    (M19 F01: the anthropic-plan OAuth token set), every MCP source row's
    ``secrets`` blob, every connector account row's ``secrets`` blob,
    every agent row's ``tool_overrides`` / ``mcp_overrides`` columns (M21
    F01 L01 / flight-log Decision D1), every tool config row's ``secrets``
    blob, AND every external-credential row's ``secret`` (flight-log
    Decision D1), AND every Library secret value (``secret_values.value``, sortie 10)
    — EIGHT corpora total — using a freshly generated key in
    memory, all inside a single DB transaction.

    Handoff ordering (flight Design Decision Q1): the new key is staged to
    ``<key_path>.next`` via :meth:`Encryptor.stage_pending_key` *before*
    the DB commit. If staging fails, the DB is untouched. If the commit
    fails, the transaction rolls back and the sidecar is discarded. Once
    the commit succeeds, the new key is installed in memory immediately
    (no ``await`` in between — other coroutines must never observe "DB on
    new key, memory on old key") and only then is the sidecar promoted to
    the canonical key file. If that promotion fails (disk full,
    permission, cross-device), the DB and in-memory encryptor are already
    correct on the new key; the sidecar stays staged on disk and a
    startup reconcile (`the_one.db.key_reconcile`) promotes it on the
    next process start — no credential is ever left stranded on a key the
    process does not hold.

    Migration-residue MCP, connector, provider-secrets, and tool-config
    rows (plaintext ``'{}'`` carried over from the column default) are
    tolerated via InvalidToken-swallowing decrypt; they are normalized to
    proper ciphertext for ``{}`` as a side-effect. The agents columns use
    the store's own ``_decrypt_overrides_column`` instead (legacy
    plaintext there is real operator data, not a ``'{}'`` default — see
    that helper's docstring); ``NULL`` columns stay ``NULL``. The
    external-credential ``secret`` column decrypts strictly — an
    ``ext_`` row is never migration residue, so an ``InvalidToken`` there
    aborts the rotation before any write.
    """
    encryptor = get_encryptor(settings.data_dir)
    if encryptor.key_path is None:
        raise HTTPException(status_code=500, detail="encryptor not file-backed")
    key_path = encryptor.key_path
    conn = await get_connection()

    # 1. Decrypt existing rows with the current encryptor. NOTE: Between this
    #    first SELECT and the write_transaction() block below (whose exit is
    #    the commit), this function issues only SELECT statements — no
    #    PRAGMA/DDL/BEGIN. Under aiosqlite's default isolation_level="" mode,
    #    a transaction is opened by the first DML statement and stays open
    #    only until an explicit commit()/rollback() — DDL and PRAGMA do NOT
    #    auto-commit (that behavior was removed in Python 3.6). What
    #    actually splits a transaction is *another coroutine's* commit() on
    #    the shared connection landing between two of this function's
    #    statements; write_transaction() (the_one/db/_write_lock.py) is what
    #    prevents that for the write below by holding the write lock across
    #    it (Squawk 0051; see Flight 2 DD-13 and the corrected comment at
    #    schema.py's v8 migration block for the measured rule).
    #    The eight corpora are gathered by the helper the status route shares
    #    (``the_one.db.encryption_corpora``), so the two cannot drift. Strict
    #    mode keeps this route's decrypt policy: the provider ``api_key`` and the
    #    external-credential ``secret`` decrypt strictly (an ``InvalidToken``
    #    aborts before any write); the ``secrets`` blobs of providers, MCP
    #    sources, connectors and tool configs tolerate the plaintext ``'{}'``
    #    migration-residue default and are normalized to ciphertext as a
    #    side-effect; the agents' override columns keep legacy plaintext as real
    #    operator data and ``NULL`` stays ``NULL``; JSON decode errors surface.
    corpora = await gather_corpora(conn, encryptor, strict=True)
    decrypted = corpora.api_keys
    decrypted_provider_secrets = corpora.provider_secrets
    decrypted_mcps = corpora.mcps
    decrypted_connectors = corpora.connectors
    decrypted_agents = corpora.agents
    decrypted_tool_configs = corpora.tool_configs
    decrypted_ext_credentials = corpora.ext_credentials
    decrypted_secret_values = corpora.secret_values

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
    reencrypted_tool_configs = [
        (name, _encrypt_secrets_blob(new_encryptor, secrets_dict))
        for name, secrets_dict in decrypted_tool_configs
    ]
    reencrypted_ext_credentials = [
        (identifier, new_encryptor.encrypt(secret))
        for identifier, secret in decrypted_ext_credentials
    ]
    reencrypted_secret_values = [
        (value_id, new_encryptor.encrypt(plain)) for value_id, plain in decrypted_secret_values
    ]

    # 3b. Stage the new key to a `.next` sidecar BEFORE the DB commit
    #     (Design Decision Q1 — two-phase handoff). If this raises, the
    #     database is untouched and the canonical key file is unchanged.
    sidecar_path = key_path.with_name(key_path.name + ".next")
    try:
        sidecar_path = encryptor.stage_pending_key(new_key)
    except OSError:
        logger.exception(
            "rotation: could not stage new key sidecar at %s; database untouched",
            sidecar_path,
        )
        raise HTTPException(status_code=500, detail="could not stage new encryption key") from None

    # 4. Write all rows inside one write_transaction() (DD-13, Flight 2 Leg
    #    1) and commit. If anything in this block raises, the guard rolls
    #    the transaction back on exit; we additionally discard the staged
    #    sidecar and re-raise so the connection cache does not surface
    #    uncommitted ciphertext encrypted with the new (not-yet-on-disk)
    #    key. The key file is untouched at this point, so re-raising
    #    leaves the system fully recoverable. The single transaction covers
    #    ALL EIGHT surfaces (llm_providers.api_key, llm_providers.secrets,
    #    mcp_sources.secrets, connectors.secrets, agents.tool_overrides /
    #    agents.mcp_overrides, tool_configs.secrets,
    #    agent_external_credentials.secret, secret_values.value) — a failure in any UPDATE loop
    #    rolls back all of them atomically.
    try:
        async with write_transaction(conn):
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
            for tool_name, ct in reencrypted_tool_configs:
                await conn.execute(
                    "UPDATE tool_configs SET secrets = ? WHERE name = ?",
                    (ct, tool_name),
                )
            for identifier, ct in reencrypted_ext_credentials:
                await conn.execute(
                    "UPDATE agent_external_credentials SET secret = ? WHERE identifier = ?",
                    (ct, identifier),
                )
            for value_id, ct in reencrypted_secret_values:
                await conn.execute(
                    "UPDATE secret_values SET value = ? WHERE id = ?",
                    (ct, value_id),
                )
            # B12 (M31 F4 L08b): record when the key last changed, in the SAME
            # transaction as the re-encryption (it commits and rolls back with
            # it). Raw SQL: AppMetadataRepository.set opens its own
            # write_transaction, and nesting raises. A "staged" outcome still
            # stores the time (the commit happened under the new key).
            await conn.execute(
                "INSERT INTO app_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (ENCRYPTION_LAST_ROTATED_KEY, now_iso()),
            )
    except BaseException:
        # BaseException (not Exception): write_transaction's guard
        # (the_one/db/_write_lock.py:73) rolls back on BaseException, so a
        # CancelledError/KeyboardInterrupt mid-block would skip this
        # discard under a narrower catch, leaving a pending key staged
        # (squawk 0057).
        encryptor.discard_pending_key()
        raise

    # Immediately after the commit — NO `await` between this line and the
    # commit above (Design Decision Q1 invariant): other coroutines must
    # never observe "DB committed under the new key, in-memory encryptor
    # still on the old key".
    encryptor.install_key(new_key)

    # Promote the sidecar to the canonical key file. `install_key` above
    # already cleared the in-memory pending key, so the key is passed
    # explicitly here (see `Encryptor.promote_pending_key` docstring). If
    # the promotion fails, the DB and in-memory encryptor are already
    # correct on the new key; the sidecar stays staged on disk and the
    # startup reconcile promotes it on the next process start.
    try:
        encryptor.promote_pending_key(new_key)
        key_file = "promoted"
    except OSError:
        logger.exception(
            "rotation: database committed under the new key but promoting %s over %s "
            "failed; the sidecar stays staged and will be promoted by the startup "
            "reconcile",
            sidecar_path,
            key_path,
        )
        key_file = "staged"

    # Rotation-restart (design review Q3, leg-2 scope): stop and restart
    # every currently-tracked connector listener from a freshly re-fetched
    # row. Without this, a listener that survives on its original
    # closure-captured account never revisits the connect path until it
    # needs to reconnect — and even then, only the DD-Q3 ``_run`` fresh-row
    # fix (manager.py) protects it, which itself only fires because ``repo``
    # was threaded through at ``start()`` time. Restarting explicitly here
    # closes the gap for a listener that's alive and NOT currently
    # reconnecting at the moment of rotation. Best-effort per connector —
    # one connector's restart failure must not abort the (already-committed)
    # rotation response.
    # Squawk 0033: this stop() before start() is load-bearing — see the
    # stale-entry invariant documented on ConnectorManager._run's
    # PermanentConnectorFailure branch (connectors/manager.py).
    _connector_manager = get_connector_manager()
    if _connector_manager is not None:
        _connector_repo_for_restart = ConnectorRepository(conn, encryptor)
        for _connector_id in _connector_manager.listener_ids():
            try:
                await _connector_manager.stop(_connector_id)
                _fresh_connector = await _connector_repo_for_restart.get(_connector_id)
            except KeyError:
                continue
            except Exception:
                logger.exception("rotation: restarting connector %s listener failed", _connector_id)
                continue
            _connector_manager.start(_fresh_connector, encryptor, repo=_connector_repo_for_restart)

    logger.info(
        "encryption key rotated: key=%s providers=%d provider_secrets=%d mcp_sources=%d "
        "connectors=%d agents=%d tool_configs=%d external_credentials=%d secret_values=%d "
        "key_file=%s",
        hashlib.sha256(new_key).hexdigest()[:8],
        len(reencrypted),
        len(reencrypted_provider_secrets),
        len(reencrypted_mcps),
        len(reencrypted_connectors),
        len(reencrypted_agents),
        len(reencrypted_tool_configs),
        len(reencrypted_ext_credentials),
        len(reencrypted_secret_values),
        key_file,
    )

    return {"status": "ok", "key_file": key_file}


# ── Routine routes (M33) live in ``routines_api.py``; attached last so every
# ``api.router`` route is declared first. ───────────────────────────────────
from the_one.interfaces.web.routines_api import router as _routines_router  # noqa: E402

router.include_router(_routines_router)

# ── Secret routes (sortie 10) live in ``secrets_api.py``, attached after routines. ──
from the_one.interfaces.web.secrets_api import router as _secrets_router  # noqa: E402

router.include_router(_secrets_router)

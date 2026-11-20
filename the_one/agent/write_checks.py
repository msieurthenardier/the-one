"""Validation helpers for agent writes (the checks Save and Approve both run).

Moved out of ``the_one/interfaces/web/api.py`` (Mission 36 Flight 2 Leg 1, DD3/DD12) so
the agent write services can run them without importing the interface layer. Each
refusal raises :class:`AgentWriteError`, carrying the status and the exact ``detail``
the route returned before the move; ``api.py`` maps it back to ``HTTPException``.

Nothing here opens a connection or reads the encryptor: a helper that needs a
repository takes it as an argument (the services pass the ones in their
``AgentWriteDeps``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from the_one.agent.config import AgentConfig
from the_one.db.repositories import (
    AgentMcpToolCacheRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    ToolConfigRepository,
)
from the_one.mcp._overrides import MCP_OVERRIDE_CREDENTIAL_KEYS
from the_one.mcp.override_validation import carries_credentials, validate_mcp_overrides
from the_one.naming import NAME_CONFLICT_AGENT, NameRuleError, check_agent_name, name_rule_detail
from the_one.secret_mask import looks_masked
from the_one.self_configuration import manage as self_configuration_manage
from the_one.self_configuration.constants import SURFACE_TOOL_PREFIX
from the_one.tools import override_validation

logger = logging.getLogger(__name__)


class AgentWriteError(Exception):
    """A refused agent or rule write: an HTTP-shaped ``status`` and ``detail``.

    ``detail`` is exactly the payload the route returns (a plain sentence or a 422 list on
    ``loc``). It carries no HTTP type: ``api.py`` turns it into ``HTTPException``.
    """

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"{status}: {detail!r}")
        self.status = status
        self.detail = detail


def validation_detail(e: ValidationError) -> list[dict]:
    """The one 422 body for a pydantic ``ValidationError``.

    ``include_context=False``: ``ctx`` may hold a raw exception (not JSON-serializable).
    ``include_input=False``: ``input`` echoes the submitted value, secrets included.
    """
    return e.errors(include_context=False, include_input=False)


def name_conflict_detail(message: str) -> list[dict]:
    return [{"type": "name_conflict", "loc": ["name"], "msg": message}]


def agent_name_conflict() -> AgentWriteError:
    """The 409 for creating an agent whose name exists."""
    return AgentWriteError(409, name_conflict_detail(NAME_CONFLICT_AGENT))


def checked_agent_name(value: object) -> str:
    """The trimmed agent name, or a list-shaped 422 on ``loc ["name"]`` (reserved names too)."""
    try:
        return check_agent_name(value)
    except NameRuleError as e:
        raise AgentWriteError(422, name_rule_detail(e.message)) from None


# ── Tool overrides, secret grants, provider ──────────────────────────────


async def tool_config_rows(repo: ToolConfigRepository, *cfgs: AgentConfig) -> dict[str, Any]:
    """The tool-config rows by tool name: ONE ``list()`` per request, and none when no
    config carries a tool override."""
    if not any(c.tool_overrides for c in cfgs):
        return {}
    return override_validation.rows_by_name(await repo.list())


async def validate_tool_overrides(
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
        raise AgentWriteError(422, details)


async def validate_secret_grants(
    secret_repo: SecretRepository, stored: list[str], cfg: AgentConfig
) -> None:
    """422 on ``["secret_ids", i]`` for a granted id that is new relative to ``stored`` and
    not a Library secret (sortie 10, DD2). Stored ids are not re-checked."""
    fresh = [(i, s) for i, s in enumerate(cfg.secret_ids) if s not in stored]
    if not fresh:
        return
    found = await secret_repo.exists_many(s for _, s in fresh)
    missing = [
        {"type": "value_error", "loc": ["secret_ids", i], "msg": "This secret doesn't exist."}
        for i, s in fresh
        if s not in found
    ]
    if missing:
        raise AgentWriteError(422, missing)


async def check_agent_provider(
    provider_repo: LLMProviderRepository, provider_id: str | None
) -> None:
    """Squawk 0277: a provider id that names no provider is a 422 on the field, not a 500
    from the foreign key. ``None`` (no provider) stays legal; ``""`` never names one."""
    if provider_id is None:
        return
    exists = False
    if provider_id != "":
        try:
            await provider_repo.get(provider_id)
            exists = True
        except KeyError:
            exists = False
    if not exists:
        raise AgentWriteError(
            422,
            [
                {
                    "type": "value_error",
                    "loc": ["provider_config_id"],
                    "msg": "That model provider doesn't exist.",
                }
            ],
        )


# ── The self-configuration surface and MCP credentials ───────────────────


async def normalize_surface_fields(
    data: dict[str, Any],
    name: str,
    stored_ids: list[str],
    *,
    mcp_repo: MCPSourceRepository,
) -> None:
    """Sortie 08: the self-configuration server is owned by the server, not
    the agent form. Runs on the RAW body of a create or a replace
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
            raise AgentWriteError(422, self_configuration_manage.SURFACE_OVERRIDE_REFUSAL)
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


async def validate_mcp_override_credentials(
    data: dict[str, Any],
    mcp_repo: MCPSourceRepository,
    validator: Callable[..., list[dict]] | None = None,
) -> None:
    """Sortie 09 DD2: 422 (one list, the sortie 07 shape) on a refused per-agent
    credential in the RAW body, before the credential merge. The source list is
    read only when the body carries a credential key. ``validator`` is the check itself
    (default ``validate_mcp_overrides``); the interface layer passes its own reference so a
    test that patches it there still bites."""
    incoming = data.get("mcp_overrides")
    if not carries_credentials(incoming):
        return
    sources = {s.name: s for s in await mcp_repo.list()}
    details = (validator or validate_mcp_overrides)(incoming, sources, looks_masked)
    if details:
        raise AgentWriteError(422, details)


def credential_view(overrides: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
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


async def evict_changed_mcp_credentials(
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
    old_view, new_view = credential_view(before), credential_view(after)
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


def drop_surface_override(merged: Any) -> Any:
    """Sortie 08 AC7: after the credential merge re-injects a stored entry,
    remove the surface's key; ``None`` (not ``{}``) when the map is empty."""
    if not isinstance(merged, dict):
        return merged
    kept = {k: v for k, v in merged.items() if k != self_configuration_manage.SURFACE_ROW_NAME}
    return kept or None


def merge_preserved_mcp_credentials(
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
    - key present and ``looks_masked`` (a client round-tripping a masked
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
                    if looks_masked(inner_value):
                        if inner_key in stored_inner:
                            resolved_inner[inner_key] = stored_inner[inner_key]
                        # else: masked with nothing stored → drop.
                    else:
                        resolved_inner[inner_key] = inner_value
                resolved_entry[key] = resolved_inner
            elif looks_masked(incoming_value):
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
        pruned = prune_plain_names(plain, resolved_entry)
        if pruned:
            resolved_entry["plain_names"] = pruned
        if resolved_entry:
            merged[source_name] = resolved_entry
    return merged or None


def prune_plain_names(plain: Any, entry: dict[str, Any]) -> list[str]:
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

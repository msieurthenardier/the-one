"""Agent writes: create, whole-body replace and a field-level change (Mission 36 F2 L1).

The one place an agent write is validated and saved, so the agent routes (Save, create) and
the proposal approval path (Flight 2, Leg 4) run the same checks and the same save. The
services never open a connection and never read the encryptor: they take their repositories
in an :class:`AgentWriteDeps`, which the interface layer builds from its own getters.

Every refusal is an :class:`AgentWriteError` (an HTTP-shaped ``status`` and the exact
``detail`` the route returned before the move); ``api.py`` maps it to ``HTTPException`` in one
helper. Nothing here imports ``the_one.interfaces``.

Three entry points:

- :func:`create_agent` -- ``POST /api/agents``; the 409 for an existing name is also enforced
  under the write lock.
- :func:`replace_agent` -- ``PUT /api/agents/{name}``; the whole-body rules (omitted fields
  reset or keep), last write wins.
- :func:`change_agent` -- changes only the named fields, with a stale check on them and a
  retry when a *different* field changed in between; ``on_commit`` runs inside the save's
  transaction (the proposal status update rides there in Leg 4).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import aiosqlite
from pydantic import ValidationError

from the_one.agent import write_checks
from the_one.agent.config import AgentConfig
from the_one.agent.write_checks import AgentWriteError
from the_one.db.repositories import (
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.self_configuration import manage as self_configuration_manage
from the_one.self_configuration.constants import is_surface_row

logger = logging.getLogger(__name__)

__all__ = [
    "AgentStaleError",
    "AgentWriteDeps",
    "AgentWriteError",
    "OnCommit",
    "agent_write_lock",
    "change_agent",
    "comparable_value",
    "create_agent",
    "replace_agent",
]

OnCommit = Callable[[aiosqlite.Connection], Awaitable[None]]

# Keys a field-level change may never carry: the name is the primary key, the credentials
# have their own route, and the Routines switches are operator-only (M33 F2 DD5).
REFUSED_CHANGE_KEYS = (
    "name",
    "mcp_overrides",
    "routines_self_config_enabled",
    "routines_require_approval",
)

# Every persisted column `save` writes (read from `model_dump()`). The two Routines switches
# are left out: `save` never writes the first and the second is insert-only, so comparing them
# would cause false retries.
_COMPARE_FIELDS = (
    "description",
    "provider_config_id",
    "llm_model",
    "system_prompt",
    "enabled_tools",
    "disabled_tools",
    "max_iterations",
    "kb_ids",
    "mcp_source_ids",
    "tool_overrides",
    "mcp_overrides",
    "chat_history_retention_days",
    "secret_ids",
    "rich_visuals",
    "self_revision_requires_approval",
    "notes_enabled",
)

# One load-merge-validate-save attempt, plus at most two retries.
_MAX_ATTEMPTS = 3

MSG_CHANGED_WHILE_APPLYING = "This agent changed while the change was being applied. Try again."

# Squawk 0327: per-agent write ordering. Every whole-row agent writer (load, merge across
# awaits, save the whole row) holds ``agent_write_lock(name)`` from its load through its save,
# so two writers to one agent cannot drop each other's changes. Ordering only: nothing about
# what is merged, validated or refused changes. The server is one process and all coroutines
# share one aiosqlite connection, so an in-process ``asyncio.Lock`` is enough. Lock order is
# always agent lock first, then the store's write lock; never take it inside a store
# ``precheck`` or ``on_commit`` hook, and never nest two writers.
# Bounded: a refcounted registry ``{name: [lock, holders_and_waiters]}``; the entry is popped
# when the count reaches zero (no await between the decrement and the pop).
_agent_locks: dict[str, list[Any]] = {}


@asynccontextmanager
async def agent_write_lock(name: str) -> AsyncIterator[None]:
    """Serialize agent writers for ``name`` (the stored name, as the store keys rows)."""
    entry = _agent_locks.get(name)
    if entry is None:
        entry = _agent_locks[name] = [asyncio.Lock(), 0]
    entry[1] += 1
    try:
        async with entry[0]:
            yield
    finally:
        entry[1] -= 1
        if entry[1] == 0:
            del _agent_locks[name]


@dataclass(frozen=True)
class AgentWriteDeps:
    """The repositories an agent write needs, passed in (never opened here)."""

    store: SQLiteAgentStore
    mcp_repo: MCPSourceRepository
    provider_repo: LLMProviderRepository
    secret_repo: SecretRepository
    tool_config_repo: ToolConfigRepository
    # The per-agent credential check (``None``: ``validate_mcp_overrides``). The interface
    # layer passes its own reference so a test patching it there still governs the route.
    override_validator: Callable[..., list[dict]] | None = None


class AgentStaleError(Exception):
    """A touched field's stored value differs from the ``base`` the change was written
    against. ``fields`` is ``[{"field", "current", "proposed"}]``, normalised (the agent's own
    self-configuration surface id is not in an ``mcp_source_ids`` value)."""

    def __init__(self, fields: list[dict[str, Any]]) -> None:
        super().__init__("stale: " + ", ".join(str(f["field"]) for f in fields))
        self.fields = fields


class _RetryError(Exception):
    """An untouched field changed between the load and the save: load again."""


def _not_found(name: str) -> AgentWriteError:
    return AgentWriteError(404, f"Agent not found: {name}")


def _model_error(e: ValidationError) -> AgentWriteError:
    return AgentWriteError(422, write_checks.validation_detail(e))


async def _post_validation_checks(
    deps: AgentWriteDeps,
    cfg: AgentConfig,
    stored: AgentConfig | None,
) -> dict[str, Any]:
    """The checks that run on the validated config, in the order the routes ran them:
    the foreign-surface guard, tool overrides, secret grants, the provider (new agent, or
    a changed id only: squawk 0277). Returns the tool-config rows computed."""
    guard_error = await self_configuration_manage.reject_foreign_surface_attachments(
        cfg, mcp_repo=deps.mcp_repo
    )
    if guard_error is not None:
        raise AgentWriteError(422, guard_error)
    rows = await write_checks.tool_config_rows(deps.tool_config_repo, cfg)
    await write_checks.validate_tool_overrides(stored.tool_overrides if stored else None, cfg, rows)
    await write_checks.validate_secret_grants(
        deps.secret_repo, stored.secret_ids if stored else [], cfg
    )
    if stored is None or cfg.provider_config_id != stored.provider_config_id:
        await write_checks.check_agent_provider(deps.provider_repo, cfg.provider_config_id)
    return rows


async def create_agent(
    deps: AgentWriteDeps, data: dict[str, Any], *, on_commit: OnCommit | None = None
) -> tuple[AgentConfig, dict]:
    """Create an agent from a request body. Returns ``(config, tool-config rows)``.

    ``on_commit`` runs inside the save's transaction (the proposal status update rides there).

    No stored row exists, so there is nothing to preserve, but a masked ``mcp_overrides``
    credential in the body is dropped rather than persisted as the secret.
    """
    data = dict(data)
    data["name"] = write_checks.checked_agent_name(data.get("name"))
    # M33 F2 DD5: the Routines switches are operator-owned; a create never sets them.
    data.pop("routines_self_config_enabled", None)
    data.pop("routines_require_approval", None)
    # Sortie 08: the self-configuration server is server-owned (DD3 422, DD7, DD2).
    await write_checks.normalize_surface_fields(data, data["name"], [], mcp_repo=deps.mcp_repo)
    # Sortie 09 DD2: a refused per-agent credential is a 422 on its loc.
    await write_checks.validate_mcp_override_credentials(
        data, deps.mcp_repo, deps.override_validator
    )
    incoming_overrides = data.get("mcp_overrides")
    if incoming_overrides is None or isinstance(incoming_overrides, dict):
        data["mcp_overrides"] = write_checks.merge_preserved_mcp_credentials(
            incoming_overrides, None
        )
    # else: not a dict and not null (e.g. a list): AgentConfig validation 422s it as before.
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise _model_error(e) from None
    rows = await _post_validation_checks(deps, cfg, None)
    if await deps.store.exists(cfg.name):
        raise write_checks.agent_name_conflict()

    def _must_not_exist(current: AgentConfig | None) -> None:
        # The same 409, under the write lock: closes the check-then-upsert race.
        if current is not None:
            raise write_checks.agent_name_conflict()

    await deps.store.save(cfg, precheck=_must_not_exist, on_commit=on_commit)
    # Sortie 09 DD7: a re-created name may have a stale pool entry; evict what carries
    # credentials (harmless when there is none).
    await write_checks.evict_changed_mcp_credentials(
        cfg.name, None, cfg.mcp_overrides, deps.mcp_repo
    )
    logger.info("agent %s: created", cfg.name)
    return cfg, rows


async def replace_agent(
    deps: AgentWriteDeps, name: str, data: dict[str, Any]
) -> tuple[AgentConfig, dict]:
    """Replace an agent from a whole request body (``PUT``). Returns ``(config, rows)``.

    Omitted description, prompt, model and tools reset to the ``AgentConfig`` defaults; the
    surface row is carried in ``mcp_source_ids``; ``self_revision_requires_approval``,
    ``notes_enabled``, ``rich_visuals``, ``kb_ids``, ``secret_ids`` and ``tool_overrides`` keep
    their stored value when omitted; the Routines switches always keep theirs; stored
    ``mcp_overrides`` credentials are merged in (AC5 / DD5 / D4). Last write wins, but writes to
    one agent are serialized (:func:`agent_write_lock`, squawk 0327).
    """
    async with agent_write_lock(name):
        return await _replace_agent_locked(deps, name, data)


async def _replace_agent_locked(
    deps: AgentWriteDeps, name: str, data: dict[str, Any]
) -> tuple[AgentConfig, dict]:
    try:
        existing = await deps.store.load(name)
    except KeyError:
        raise _not_found(name) from None
    data = dict(data)
    data["name"] = name  # Ensure name matches path
    await write_checks.normalize_surface_fields(
        data, name, existing.mcp_source_ids, mcp_repo=deps.mcp_repo
    )
    await write_checks.validate_mcp_override_credentials(
        data, deps.mcp_repo, deps.override_validator
    )
    incoming_overrides = data.get("mcp_overrides")
    if incoming_overrides is None or isinstance(incoming_overrides, dict):
        # `data.get(...)` cannot distinguish "omitted" from an explicit null; both keep every
        # stored source (AC5). The merge re-injects a stored surface entry the body omitted;
        # drop it so any Save cleans it (sortie 08 AC7).
        data["mcp_overrides"] = write_checks.drop_surface_override(
            write_checks.merge_preserved_mcp_credentials(incoming_overrides, existing.mcp_overrides)
        )
    # else: not a dict and not null (e.g. a list): AgentConfig validation 422s it as before.
    # Operator-owned switches and omitted-keeps fields (see the docstring).
    if "self_revision_requires_approval" not in data:
        data["self_revision_requires_approval"] = existing.self_revision_requires_approval
    if "notes_enabled" not in data:
        data["notes_enabled"] = existing.notes_enabled
    if "rich_visuals" not in data:
        data["rich_visuals"] = existing.rich_visuals
    data["routines_self_config_enabled"] = existing.routines_self_config_enabled
    data["routines_require_approval"] = existing.routines_require_approval
    if "kb_ids" not in data:
        data["kb_ids"] = existing.kb_ids
    if "secret_ids" not in data:
        data["secret_ids"] = existing.secret_ids
    if "tool_overrides" not in data:
        data["tool_overrides"] = existing.tool_overrides
    try:
        cfg = AgentConfig.model_validate(data)
    except ValidationError as e:
        raise _model_error(e) from None
    rows = await _post_validation_checks(deps, cfg, existing)
    await deps.store.save(cfg)
    # Sortie 09 DD7: the agent's next connection must use the new credentials.
    await write_checks.evict_changed_mcp_credentials(
        name, existing.mcp_overrides, cfg.mcp_overrides, deps.mcp_repo
    )
    logger.info("agent %s: replaced", name)
    return cfg, rows


# ── Field-level change ───────────────────────────────────────────────────


def _refuse_keys(changes: dict[str, Any]) -> None:
    refused = [k for k in REFUSED_CHANGE_KEYS if k in changes]
    if refused:
        raise AgentWriteError(
            422,
            [
                {"type": "value_error", "loc": [k], "msg": "This field can't be changed here."}
                for k in refused
            ],
        )


def _view(cfg: AgentConfig, own_ids: set[str]) -> dict[str, Any]:
    """The compared persisted fields of ``cfg``; ``mcp_source_ids`` without the agent's own
    self-configuration surface id (that attachment is the server's, never an agent write's)."""
    view = cfg.model_dump(include=set(_COMPARE_FIELDS))
    view["mcp_source_ids"] = [i for i in view["mcp_source_ids"] if i not in own_ids]
    return view


def comparable_value(field: str, value: Any, surface_ids: set[str]) -> Any:
    """The compared form of one stored field: ``mcp_source_ids`` without the agent's own
    self-configuration surface id(s). Shared by the precheck and the proposal ``base``."""
    if field == "mcp_source_ids" and isinstance(value, list):
        return [i for i in value if i not in surface_ids]
    return value


async def change_agent(
    deps: AgentWriteDeps,
    name: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> AgentConfig:
    """Change only the fields named in ``changes``; every other field keeps its stored value.

    The body is the stored row plus ``changes`` (the reset-on-omit fields of a PUT included),
    and ``mcp_overrides`` is never in it: stored credentials stay as stored and are not
    re-validated as incoming. The same checks as :func:`replace_agent` run, then
    ``AgentStore.save(cfg, precheck=..., on_commit=on_commit)``.

    Validation is async, so it runs outside the write lock against a snapshot of the stored
    row; the sync precheck then runs under the lock against the row re-read there:

    - A field in ``changes`` whose stored value differs from ``base[field]`` (when ``base`` is
      given and ``override`` is false) raises :class:`AgentStaleError`, nothing is written.
      A field with no ``base`` entry is not compared.
    - A field NOT in ``changes`` that differs from the snapshot means another write landed
      in between: the whole load-merge-validate-save is redone (at most twice; then a 409).
      It never raises stale for such a field and never writes over the newer value.

    ``override`` bypasses only the touched-field compare. ``on_commit`` runs inside the save's
    transaction; a raise from it rolls the agent write back.

    The whole body, retry loop included, runs under :func:`agent_write_lock` (squawk 0327).
    """
    _refuse_keys(changes)
    async with agent_write_lock(name):
        return await _change_agent_locked(
            deps, name, changes, base=base, override=override, on_commit=on_commit
        )


async def _change_agent_locked(
    deps: AgentWriteDeps,
    name: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None,
    override: bool,
    on_commit: OnCommit | None,
) -> AgentConfig:
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            existing = await deps.store.load(name)
        except KeyError:
            raise _not_found(name) from None
        data = existing.model_dump(exclude={"mcp_overrides"})
        data.update(changes)
        await write_checks.normalize_surface_fields(
            data, name, existing.mcp_source_ids, mcp_repo=deps.mcp_repo
        )
        try:
            cfg = AgentConfig.model_validate(data)
        except ValidationError as e:
            raise _model_error(e) from None
        # Stored credentials as stored (the body never carries them).
        cfg = cfg.model_copy(update={"mcp_overrides": existing.mcp_overrides})
        await _post_validation_checks(deps, cfg, existing)
        own_ids = {
            s.id
            for s in await deps.mcp_repo.list()
            if is_surface_row(s) and self_configuration_manage.owner_of(s) == name
        }
        snapshot = _view(existing, own_ids)
        proposed = _view(cfg, own_ids)

        def precheck(
            current: AgentConfig | None,
            snapshot: dict[str, Any] = snapshot,
            proposed: dict[str, Any] = proposed,
            own_ids: set[str] = own_ids,
        ) -> None:
            if current is None:
                raise _not_found(name)
            stored = _view(current, own_ids)
            if base is not None and not override:
                stale = [
                    {"field": f, "current": stored[f], "proposed": proposed[f]}
                    for f in changes
                    if f in base
                    and f in stored
                    and stored[f] != comparable_value(f, base[f], own_ids)
                ]
                if stale:
                    raise AgentStaleError(stale)
            if any(stored[f] != snapshot[f] for f in _COMPARE_FIELDS if f not in changes):
                raise _RetryError

        try:
            await deps.store.save(cfg, precheck=precheck, on_commit=on_commit)
        except _RetryError:
            continue
        logger.info("agent %s: changed", name)
        return cfg
    raise AgentWriteError(409, [{"loc": [], "msg": MSG_CHANGED_WHILE_APPLYING}])

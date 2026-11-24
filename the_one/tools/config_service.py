"""The built-in tool-config write service (Mission 36 Flight 5 Leg 4a, DD3, DD7).

The writes ``PUT /api/tools/configs/{name}`` and its impact preview make, moved out of
``the_one/interfaces/web/api.py`` so GleepGlorp's approve path runs the same validation the
operator's own save does. The routes stay thin: they call :func:`replace_tool_config` and
:func:`preview_impact` and map :class:`ToolConfigWriteError` to ``HTTPException``. A proposal
calls :func:`change_tool_config`.

This module imports nothing from ``fastapi``, ``the_one.interfaces`` or ``the_one.gleepglorp``,
and keeps the repository behind ``TYPE_CHECKING`` (an ``ast`` test pins both): it is injected
through :class:`ToolConfigWriteDeps`, together with the agent-store factory the impact
computation needs.

Both write shapes **read the row inside the write transaction**
(``ToolConfigRepository.update_in_txn``), so a value committed while a save waited for the lock
is never written back from a stale pre-read row (the PUT used to read the row outside any
transaction).

``change_tool_config`` merges the named fields over ``{**config, **secrets}`` before the shared
computation. That computation drops every secret field that is missing or empty in the
incoming config (only a masked value keeps the stored one), so a change that merged over
``config`` alone would silently erase a stored API key.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiosqlite
from pydantic import ValidationError

from the_one.agent.write_checks import validation_detail
from the_one.db.models import ToolConfig
from the_one.secret_mask import looks_masked
from the_one.tools import override_validation

if TYPE_CHECKING:
    from the_one.db.repositories import ToolConfigRepository

logger = logging.getLogger(__name__)

OnCommit = Callable[[aiosqlite.Connection], Awaitable[None]]


class ToolConfigWriteError(Exception):
    """A refused tool-config write: an HTTP-shaped ``status`` and ``detail`` (the exact payload
    the route returned before the move). It carries no HTTP type."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"{status}: {detail!r}")
        self.status = status
        self.detail = detail

    @property
    def items(self) -> list[dict[str, Any]]:
        """``[{loc, msg}]`` for the approve path."""
        if isinstance(self.detail, list):
            out: list[dict[str, Any]] = []
            for d in self.detail:
                if isinstance(d, dict):
                    loc = [x if isinstance(x, (str, int)) else str(x) for x in d.get("loc", [])]
                    out.append({"loc": loc, "msg": str(d.get("msg", ""))})
                else:
                    out.append({"loc": [], "msg": str(d)})
            return out
        return [{"loc": [], "msg": str(self.detail)}]


class ToolConfigStaleError(Exception):
    """A touched field's stored value differs from the ``base`` the change was written
    against. ``fields`` is ``[{"field", "current", "proposed"}]``."""

    def __init__(self, fields: list[dict[str, Any]]) -> None:
        super().__init__("stale: " + ", ".join(str(f["field"]) for f in fields))
        self.fields = fields


@dataclass(frozen=True)
class ToolConfigWriteDeps:
    """What a tool-config write needs: the repository and the agent-store factory the impact
    computation calls."""

    repo: ToolConfigRepository
    agent_store: Callable[[], Awaitable[Any]]


# --- the moved helpers ------------------------------------------------------------------


def secret_field_names(config_cls: type) -> set[str]:
    """The field names a tool Config marks ``secret: true``.

    Generic: reads each field's ``json_schema_extra`` for the ``secret`` marker (``web_search``'s
    keyed-engine API keys are the first consumers, but any future Config with a marked field
    gets encrypted storage and masking for free). ``json_schema_extra`` is ``None`` on unmarked
    fields, hence the guard. M16 F08 L03.
    """
    names: set[str] = set()
    for field_name, info in getattr(config_cls, "model_fields", {}).items():
        extra = info.json_schema_extra or {}
        if isinstance(extra, dict) and extra.get("secret") is True:
            names.add(field_name)
    return names


def merge_hidden_fields(
    config_cls: type, tool_cls: type, incoming: Any, stored: dict[str, Any]
) -> Any:
    """The body a tools PUT validates: ``incoming`` with every hidden field (see
    ``Tool.config_fields``) replaced by its stored value.

    A hidden field is not shown, so the form cannot have meant to change it and the stored value
    always wins over an incoming one. A hidden field with no stored value is left out (the Config
    default applies). ``stored`` is the saved config merged with the decrypted secrets. A
    non-dict ``incoming`` is returned unchanged (validation rejects it).
    """
    hidden = override_validation.hidden_field_names(tool_cls, config_cls)
    if not hidden or not isinstance(incoming, dict):
        return incoming
    merged = {k: v for k, v in incoming.items() if k not in hidden}
    for field_name in hidden:
        if field_name in stored:
            merged[field_name] = stored[field_name]
    return merged


def tool_class(name: str) -> type:
    """The built-in tool class named ``name``; a 404 :class:`ToolConfigWriteError` otherwise.

    Read from the module attribute at call time (tests patch ``_TOOL_CLASSES``)."""
    from the_one.tools import builtins

    cls = builtins._TOOL_CLASSES.get(name)
    if cls is None:
        raise ToolConfigWriteError(404, f"Tool not found: {name}")
    return cls


def compute_tool_config_update(
    cls: type, name: str, data: dict[str, Any], existing: Any
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """What a tools PUT would store: ``(new_enabled, new_config, new_secrets)``.

    One computation shared by the PUT, the impact preview and a proposal's change (sortie 07 L05,
    DD8), so the preview equals what the PUT stores. ``existing`` is the stored ``ToolConfig``
    row or ``None``. A body that fails validation raises :class:`ToolConfigWriteError` (422);
    when ``config`` is omitted the stored config and secrets come back unchanged.
    """
    if existing is not None:
        current_enabled = existing.enabled
        current_config = existing.config
        current_secrets = existing.secrets
    else:
        current_enabled = True
        current_config = {}
        current_secrets = {}

    secret_fields = secret_field_names(cls.Config)

    # `enabled` — preserve when omitted from body; coerce when present.
    new_enabled = bool(data["enabled"]) if "enabled" in data else current_enabled

    # `config` — REPLACE when present (validate body), preserve when omitted.
    if "config" in data:
        stored = {**current_config, **current_secrets}
        merged = merge_hidden_fields(cls.Config, cls, data["config"], stored)
        try:
            try:
                validated = cls.Config.model_validate(merged)
            except ValidationError:
                # A stored value for a hidden field may no longer validate (a constraint
                # tightened since it was saved). Retry without the stored hidden values so the
                # Config defaults apply; if that also fails the operator's visible edit is at
                # fault.
                fallback = merge_hidden_fields(cls.Config, cls, data["config"], {})
                if fallback == merged:
                    raise
                validated = cls.Config.model_validate(fallback)
                logger.warning(
                    "tool %r: a stored value for a hidden setting no longer validated; "
                    "using the default",
                    name,
                )
        except ValidationError as e:
            # `e.errors()` may carry a raw exception in `ctx['error']` (Pydantic v2 model-
            # validator path) which is NOT JSON-serializable: `include_context=False` keeps
            # the response encodable (`msg` + `loc` carry the diagnostic the form shows inline).
            raise ToolConfigWriteError(422, validation_detail(e)) from None
        dumped = validated.model_dump()
        # M16 F08 L03: SPLIT secret-marked fields OUT of the config column into the encrypted
        # `secrets` store, so a plaintext key never lands in `config`. A masked incoming value
        # PRESERVES the existing decrypted secret instead of overwriting it with the mask; a
        # masked value with no existing secret is dropped (cleared), never stored as the mask. A
        # real new value replaces it. NOTE: a missing or empty secret is dropped too.
        new_config = {k: v for k, v in dumped.items() if k not in secret_fields}
        new_secrets: dict[str, Any] = {}
        for field_name in secret_fields:
            value = dumped.get(field_name)
            if looks_masked(value):
                if field_name in current_secrets:
                    new_secrets[field_name] = current_secrets[field_name]
                # else: masked value with no existing secret -> drop (cleared).
            elif value:
                new_secrets[field_name] = value
            # else: empty/falsy -> drop (cleared), matches the Config default of "".
    else:
        # `config` omitted — preserve both the existing config and secrets.
        new_config = current_config
        new_secrets = dict(current_secrets)
    return new_enabled, new_config, new_secrets


def narrowing_added(before: list[dict], after: list[dict]) -> list[dict]:
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


def impact_of(name: str, cfgs: list[Any], rows: dict[str, Any], proposed: Any) -> list:
    """Blocking (path canonicalisation): per agent, the narrowing ``proposed`` adds."""
    after_rows = {**rows, name: proposed}
    impact = []
    for cfg in cfgs:
        before = [n for n in override_validation.compute_notices(cfg, rows) if n["tool"] == name]
        after = [
            n for n in override_validation.compute_notices(cfg, after_rows) if n["tool"] == name
        ]
        fields = narrowing_added(before, after)
        if fields:
            impact.append({"agent": cfg.name, "fields": fields})
    return impact


def proposed_row(
    name: str, existing: Any, enabled: bool, config: dict[str, Any], secrets: dict[str, Any]
) -> ToolConfig:
    """The row a write would leave behind, for the impact computation."""
    update = {"enabled": enabled, "config": config, "secrets": secrets}
    if existing is not None:
        return existing.model_copy(update=update)
    return ToolConfig(name=name).model_copy(update=update)


async def impact_for_row(
    deps: ToolConfigWriteDeps, name: str, rows: dict[str, Any], proposed: Any
) -> list:
    """Which agents ``proposed`` would newly narrow. Loads every agent (their
    ``tool_overrides`` are encrypted, so the early return still comes after the load) and
    returns ``[]`` when no agent holds an override for the tool; the blocking part runs in a
    thread."""
    store = await deps.agent_store()
    cfgs = [await store.load(n) for n in await store.list_agents()]
    if not any(c.tool_overrides and name in c.tool_overrides for c in cfgs):
        return []
    return await asyncio.to_thread(impact_of, name, cfgs, rows, proposed)


async def preview_impact(deps: ToolConfigWriteDeps, name: str, data: dict[str, Any]) -> list:
    """The impact route's body: which agents a PUT of ``data`` would newly narrow. An invalid
    body raises the PUT's 422 (:class:`ToolConfigWriteError`)."""
    cls = tool_class(name)
    rows = override_validation.rows_by_name(await deps.repo.list())
    existing = rows.get(name)
    enabled, config, secrets = compute_tool_config_update(cls, name, data, existing)
    return await impact_for_row(
        deps, name, rows, proposed_row(name, existing, enabled, config, secrets)
    )


# --- effective values and the stale check -------------------------------------------------


def effective_values(name: str, row: ToolConfig | None) -> dict[str, Any]:
    """The values a tool runs with: ``enabled`` (``True`` for a never-saved row) and every
    non-secret Config field, the stored value over **that tool's own** Config default. A
    never-saved row (``None``) yields the defaults."""
    cls = tool_class(name)
    secrets = secret_field_names(cls.Config)
    stored = row.config if row is not None else {}
    out: dict[str, Any] = {"enabled": row.enabled if row is not None else True}
    for field_name, info in cls.Config.model_fields.items():
        if field_name in secrets:
            continue
        if field_name in stored:
            out[field_name] = stored[field_name]
        else:
            out[field_name] = info.get_default(call_default_factory=True, validated_data={})
    return out


def stale_fields(
    name: str, current: ToolConfig | None, changes: dict[str, Any], base: dict[str, Any]
) -> list[dict[str, Any]]:
    """The touched fields whose effective value is not the ``base`` value."""
    effective = effective_values(name, current)
    out: list[dict[str, Any]] = []
    for key, proposed in changes.items():
        if key not in effective:
            continue
        cur = effective[key]
        if key not in base or cur != base[key]:
            out.append({"field": key, "current": cur, "proposed": proposed})
    return out


# --- the writes ---------------------------------------------------------------------------


async def replace_tool_config(
    deps: ToolConfigWriteDeps, name: str, data: dict[str, Any]
) -> ToolConfig:
    """The route's PUT: ``data`` (``{enabled?, config?}``) applied to the stored row and
    validated, read and written inside one ``update_in_txn``. Returns the written row."""
    cls = tool_class(name)

    def mutate(current: ToolConfig | None) -> ToolConfig:
        enabled, config, secrets = compute_tool_config_update(cls, name, data, current)
        return ToolConfig(name=name, config=config, secrets=secrets, enabled=enabled)

    _before, after = await deps.repo.update_in_txn(name, mutate)
    return after


async def change_tool_config(
    deps: ToolConfigWriteDeps,
    name: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> ToolConfig:
    """Apply a proposal's named fields to the tool's row, inside one write transaction.

    ``enabled`` is split out to the row's top-level column; the Config fields are merged over
    ``{**config, **secrets}`` (so no stored secret is dropped) and validated by the same
    computation the PUT runs. ``base`` (the effective values the proposal was written against) is
    compared on the fresh row unless ``override``: a mismatch raises :class:`ToolConfigStaleError`
    and nothing is written. A config-field change on a never-saved row materialises every Config
    default into the stored ``config`` (the PUT's behaviour); an ``enabled``-only change leaves
    ``config`` as it was. Returns the written row."""
    cls = tool_class(name)
    config_changes = {k: v for k, v in changes.items() if k != "enabled"}

    def mutate(current: ToolConfig | None) -> ToolConfig:
        if not override and base is not None:
            stale = stale_fields(name, current, changes, base)
            if stale:
                raise ToolConfigStaleError(stale)
        data: dict[str, Any] = {}
        if "enabled" in changes:
            data["enabled"] = changes["enabled"]
        if config_changes:
            stored = {**current.config, **current.secrets} if current is not None else {}
            data["config"] = {**stored, **config_changes}
        enabled, config, secrets = compute_tool_config_update(cls, name, data, current)
        return ToolConfig(name=name, config=config, secrets=secrets, enabled=enabled)

    _before, after = await deps.repo.update_in_txn(name, mutate, on_commit=on_commit)
    return after

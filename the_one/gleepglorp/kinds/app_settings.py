"""The ``app_settings`` kind: change an app-wide Settings page (Mission 36 F5 L4a, DD8).

Two Settings pages hold app-wide values GleepGlorp may propose changes to:

- **Date and time** (``date-and-time``): the time zone mode (``system`` or ``zone``) and the zone;
- **Knowledge indexing** (``knowledge-indexing``): chunk size and overlap, folder watching and the
  re-check interval.

This is the first kind with ``addressing="page"``: the target is a fixed page key, never named
by the model. ``normalize`` derives it from the fields named (``target_id`` is the page key and
``target_key`` is ``app_settings:{page}``), so a second proposal for the same page supersedes the
first through the store's ordinary rule. One proposal changes one page, because the two pages
are separate writes.

Only a proposal may change Date and time (it saves as soon as the operator chooses, so there is
no form to fill): its two fields carry ``fill_refused``. Knowledge indexing can be filled. The
embedding model and the vector store are fixed and appear in no field.

A ``time_zone`` change alone while the stored mode is ``system`` also sets the mode to ``zone``,
and the card shows both rows; otherwise the change would have no effect. The write is the
app-settings service's (``the_one/app_settings_service.py``): one transaction, only the records
it changes, the scheduler poke or the watcher update after the commit.
"""

from __future__ import annotations

import re
from datetime import datetime, tzinfo
from typing import Any

import aiosqlite
from pydantic import ValidationError

from the_one import app_settings_service as svc
from the_one import time_zones
from the_one.gleepglorp.kinds.base import Kind, changed_labels, id_fill_extras
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    _bad,
    _check_int,
    _check_text,
    _q,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.knowledge.settings import (
    ChunkingSettings,
    MonitoringSettings,
    load_knowledge_settings,
)

DATE_AND_TIME = "date-and-time"
KNOWLEDGE_INDEXING = "knowledge-indexing"
PAGE_LABELS: dict[str, str] = {
    DATE_AND_TIME: "Date and time",
    KNOWLEDGE_INDEXING: "Knowledge indexing",
}

NO_FILL = "Date and time saves as soon as you choose; I'll propose it instead."

APP_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "time_zone_mode",
        "text",
        "Time zone mode",
        "time_zone_mode",
        hint="system (follow this computer) or zone (use the time zone below)",
        max=16,
        path=("time_zone", "mode"),
        applies_to=(DATE_AND_TIME,),
        fill_refused=NO_FILL,
    ),
    FieldSpec(
        "time_zone",
        "text",
        "Time zone",
        "time_zone",
        hint="an IANA name such as Asia/Tokyo",
        max=64,
        path=("time_zone", "zone"),
        applies_to=(DATE_AND_TIME,),
        fill_refused=NO_FILL,
    ),
    FieldSpec(
        "chunk_size_chars",
        "integer",
        "Chunk size",
        "chunk_size_chars",
        hint="characters per chunk",
        min=200,
        max=2000,
        path=("knowledge.chunking", "size_chars"),
        applies_to=(KNOWLEDGE_INDEXING,),
    ),
    FieldSpec(
        "chunk_overlap_chars",
        "integer",
        "Chunk overlap",
        "chunk_overlap_chars",
        hint="characters; at most half the chunk size",
        min=0,
        path=("knowledge.chunking", "overlap_chars"),
        applies_to=(KNOWLEDGE_INDEXING,),
    ),
    FieldSpec(
        "watch_enabled",
        "boolean",
        "Watch folders",
        "watch_enabled",
        hint="watch registered folders for changes",
        path=("knowledge.monitoring", "watch_enabled"),
        applies_to=(KNOWLEDGE_INDEXING,),
    ),
    FieldSpec(
        "reconcile_interval_seconds",
        "integer",
        "Re-check interval",
        "reconcile_interval_seconds",
        hint="seconds between full re-checks",
        min=10,
        max=86400,
        path=("knowledge.monitoring", "reconcile_interval_seconds"),
        applies_to=(KNOWLEDGE_INDEXING,),
    ),
)
_BY_NAME = {f.name: f for f in APP_FIELDS}
_PAGE_OF = {f.name: f.applies_to[0] for f in APP_FIELDS}

# The embedding model and the vector store are fixed. The names are the model-facing ones
# (``EmbeddingSettings.backend`` / ``model_id`` / ``dim`` and the ``knowledge.vector_store``
# record); never in any kind's spec (a test asserts it).
OPERATOR_ONLY = ("embedding_backend", "embedding_model_id", "embedding_dim", "vector_store")

OPERATOR_ONLY_MESSAGE = "The embedding model and vector store are fixed; they can't be changed."
ONE_PAGE = (
    "One proposal changes one Settings page; propose Date and time and Knowledge indexing "
    "separately."
)


def operator_only_message(names: list[str]) -> str:
    return OPERATOR_ONLY_MESSAGE


# --- normalize ----------------------------------------------------------------------------

_MODEL_NAMES = (
    ("overlap_chars", "chunk_overlap_chars"),
    ("size_chars", "chunk_size_chars"),
)


def _model_message(e: ValidationError) -> str:
    """The first error's message as the model sees it: no ``Value error, `` prefix and the
    stored names mapped to the field names it uses."""
    msg = str(e.errors(include_context=False, include_input=False)[0]["msg"])
    msg = msg.removeprefix("Value error, ")
    for stored, shown in _MODEL_NAMES:
        msg = re.sub(rf"(?<![a-z_]){stored}", shown, msg)
    return msg


def _check_value(spec: FieldSpec, value: Any) -> Any:
    if spec.type == "boolean":
        if not isinstance(value, bool):
            raise _bad(spec, "true or false")
        return value
    if spec.type == "integer":
        return _check_int(spec, value)
    text = _check_text(spec, value).strip()
    if spec.name == "time_zone_mode":
        text = text.lower()
        if text not in ("system", "zone"):
            raise ShapeError("time_zone_mode must be system or zone.")
    return text


def _time_setting(stored: dict[str, Any], current: time_zones.TimeZoneSetting) -> Any:
    merged = {
        "mode": stored.get("time_zone_mode", current.mode),
        "zone": stored.get("time_zone", current.zone),
    }
    try:
        return time_zones.TimeZoneSetting.model_validate(merged)
    except ValidationError as e:
        for err in e.errors():
            if err["loc"] == ("zone",):
                shown = str(merged["zone"])[:64]
                raise ShapeError(
                    f"Unknown time zone {_q(shown)!r}. Use an IANA name such as Asia/Tokyo."
                ) from None
        if any(time_zones.ERR_ZONE_REQUIRED in str(err.get("msg", "")) for err in e.errors()):
            raise ShapeError("Choose a time zone when time_zone_mode is zone.") from None
        raise ShapeError(_model_message(e)) from None


async def _normalize_time(
    conn: Any, stored: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = await time_zones.load_setting(conn)
    _time_setting(stored, current)
    if "time_zone" in stored and "time_zone_mode" not in stored and current.mode == "system":
        # A zone alone would have no effect while the mode follows the system.
        stored = {"time_zone_mode": "zone", **stored}
    values = svc.time_values(current)
    return stored, {k: values[k] for k in stored}


async def _normalize_knowledge(
    conn: Any, stored: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = await load_knowledge_settings(conn)
    chunking = current.chunking.model_dump()
    monitoring = current.monitoring.model_dump()
    records = {"chunking": chunking, "monitoring": monitoring}
    for name, (record, key) in svc.KNOWLEDGE_FIELDS.items():
        if name in stored:
            records[record][key] = stored[name]
    try:
        ChunkingSettings.model_validate(chunking)
        MonitoringSettings.model_validate(monitoring)
    except ValidationError as e:
        raise ShapeError(_model_message(e)) from None
    values = svc.knowledge_values(current)
    return stored, {k: values[k] for k in stored}


async def normalize(
    action: str,
    target: dict[str, Any],
    changes: dict[str, Any],
    *,
    conn: Any,
    now: datetime,
    zone: tzinfo,
    enc: Any = None,
    mode: str = "propose",
) -> Normalized:
    for key in changes:
        if key not in _BY_NAME:
            raise ShapeError(
                f"app_settings changes can't include {_q(key)!r}. "
                f"Allowed fields: {', '.join(_BY_NAME)}."
            )
    pages = {_PAGE_OF[k] for k in changes}
    if len(pages) > 1:
        raise ShapeError(ONE_PAGE)
    page = next(iter(pages))
    stored = {k: _check_value(_BY_NAME[k], v) for k, v in changes.items()}
    if page == DATE_AND_TIME:
        stored, base = await _normalize_time(conn, stored)
    else:
        stored, base = await _normalize_knowledge(conn, stored)
    return Normalized("app_settings", "change", None, page, f"app_settings:{page}", stored, base)


# --- exists, apply, wording ---------------------------------------------------------------


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    return True


def _poke() -> None:
    from the_one.routines import service as routine_service

    routine_service.poke_scheduler()


async def _apply_monitoring(monitoring: MonitoringSettings) -> None:
    from the_one.knowledge import watcher

    manager = watcher.get_manager()
    if manager is not None:
        await manager.apply_settings(monitoring)


def _write_deps(conn: aiosqlite.Connection) -> svc.AppSettingsWriteDeps:
    # Late-bound, so a test (or a patched module attribute) governs the hooks.
    return svc.AppSettingsWriteDeps(
        conn=conn,
        poke=lambda: _poke(),
        apply_monitoring=lambda monitoring: _apply_monitoring(monitoring),
    )


async def apply(
    conn: aiosqlite.Connection,
    deps: KindDeps,
    p: Proposal,
    *,
    changes: dict[str, Any],
    base: dict[str, Any],
    override: bool,
    now: datetime,
    zone: Any,
    mark: Any,
    runner: Any,
    result: dict[str, Any],
) -> str | None:
    try:
        write = (
            svc.change_time_settings
            if p.target_id == DATE_AND_TIME
            else svc.change_knowledge_settings
        )
        await write(_write_deps(conn), changes, base=base, override=override, on_commit=mark)
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


def _page_label(page: str | None) -> str:
    return PAGE_LABELS.get(page or "", "app settings")


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(APP_FIELDS, p)
    return {
        "summary": f"Changed {', '.join(labels)} on {_page_label(p.target_id)}",
        "agent": None,
        "fields": labels,
    }


def title(p: Proposal) -> str:
    return f"change {_page_label(p.target_id)}"


def card_title(action: str, name: str | None) -> str:
    return f"Change {_page_label(name)}"


async def card_extras(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """The card's title (the page's label); a page never goes away."""
    return {"title": card_title("change", p.target_id), "target_gone": False}


async def fill_stale(conn: Any, fill: Any, labels: dict[str, str]) -> list[dict[str, Any]]:
    """The ``stale`` rows of a Knowledge indexing fill: the named fields whose stored value moved
    since the fill was made, labelled."""
    if fill.target_id != KNOWLEDGE_INDEXING:
        return []
    current = svc.knowledge_values(await load_knowledge_settings(conn))
    base = fill.base or {}
    return [
        {
            "field": key,
            "label": labels.get(key, key),
            "current": current[key],
            "proposed": proposed,
        }
        for key, proposed in fill.changes.items()
        if key in current and (key not in base or current[key] != base[key])
    ]


fill_extras = id_fill_extras(card_extras, stale_fn=fill_stale)


# --- warnings -----------------------------------------------------------------------------

WARN_ZONE = "Routines' times follow the new zone from now on."
WARN_CHUNKING = (
    "This applies to files indexed from now on; reindex a knowledge base to apply it to "
    "existing files."
)
WARN_WATCH_OFF = "Folders stop being watched; changes are picked up only by the periodic check."


async def warnings(
    conn: aiosqlite.Connection, enc: Any, p: Proposal, mode: str = "propose"
) -> list[str]:
    changes = p.changes
    out: list[str] = []
    if "time_zone" in changes or "time_zone_mode" in changes:
        out.append(WARN_ZONE)
    if "chunk_size_chars" in changes or "chunk_overlap_chars" in changes:
        out.append(WARN_CHUNKING)
    if changes.get("watch_enabled") is False:
        out.append(WARN_WATCH_OFF)
    return out


KIND = Kind(
    name="app_settings",
    label="app settings",
    summary="Change the time zone or the knowledge indexing settings",
    fields=APP_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    addressing="page",
    fill_extras=fill_extras,
    keyerror_is_gone=False,
    operator_only=OPERATOR_ONLY,
    operator_only_message=operator_only_message,
    fillable=("change",),
    actions=("change",),
    title=title,
    card_title=card_title,
    warnings=warnings,
    card_extras=card_extras,
)

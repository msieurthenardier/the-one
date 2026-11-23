"""The ``knowledge_base`` kind: create a knowledge base or change its name or description
(Mission 36 F5 L3a, DD5).

A knowledge base's editable form is only ``name`` and ``description``. Everything on its page
beyond that is the operator's: folders and files (a path on their disk; registering one starts
indexing), re-indexing, item retry and delete, and deleting the base. Attaching a base to an
agent is the agent kind's ``knowledge_bases`` field. A change naming ``folders``, ``items`` or
``path`` is refused with a sentence pointing at the page.

A knowledge base is targeted by id (or an unambiguous name) through ``target``. Names are not
unique, so an ambiguous name is refused listing each ``name (id)``. The write is the
knowledge-base write service's (``the_one/knowledge/service.py``), so the operator's own
validation applies, the proposal's status mark rides in the write's transaction, and a rename
carries into attached agents' ``disabled_tools`` after the commit. The service raises typed
not-found and stale errors (``keyerror_is_gone`` stays ``False``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, tzinfo
from typing import Any

import aiosqlite

from the_one.embeddings import schedule_warm_up
from the_one.gleepglorp.kinds.base import Kind, changed_labels, id_fill_extras
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    _check_text,
    _q,
    _ref_entries,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.knowledge import service as kb_service
from the_one.naming import NameRuleError, check_name

KB_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "text", "Name", "name", create_required=True),
    FieldSpec("description", "text", "Description", "description"),
)
_BY_NAME = {f.name: f for f in KB_FIELDS}

# Fields the operator alone controls; never in any kind's spec (a test asserts it).
OPERATOR_ONLY = ("folders", "items", "path")

OPERATOR_ONLY_MESSAGE = (
    "A knowledge base's folders, files and indexing are set only by the operator, on its page "
    "in the [Library](#library). I can set its name and description."
)

# --- resolution --------------------------------------------------------------------------


async def resolve_target(conn: Any, ref: Any) -> tuple[str, str]:
    """``(id, name)`` of an existing knowledge base named by id or name (id first). Names are
    not unique: an ambiguous name is refused listing each ``name (id)``."""
    from the_one.gleepglorp import kinds

    return kinds.resolve_by_id_or_name(await _ref_entries(conn, "kb"), ref, "knowledge base")


async def _load(conn: Any, kb_id: str) -> Any:
    """The stored knowledge base, or ``None``."""
    from the_one.db.repositories import KnowledgeBaseRepository

    try:
        return await KnowledgeBaseRepository(conn).get(kb_id)
    except KeyError:
        return None


def operator_only_message(names: list[str]) -> str:
    return OPERATOR_ONLY_MESSAGE


# --- normalize ---------------------------------------------------------------------------


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
    named = [k for k in changes if k in OPERATOR_ONLY]
    if named:
        raise ShapeError(operator_only_message(named))
    for key in changes:
        if key not in _BY_NAME:
            raise ShapeError(
                f"knowledge base changes can't include {_q(key)!r}. "
                f"Allowed fields: {', '.join(_BY_NAME)}."
            )
    current: Any = None
    target_id: str | None = None
    if action == "change":
        target_id, _name = await resolve_target(conn, target.get("target"))
        current = await _load(conn, target_id)
        if current is None:
            raise ShapeError("No knowledge base with that id.")
    stored: dict[str, Any] = {}
    for f in KB_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.name == "name":
            try:
                stored["name"] = check_name(value)
            except NameRuleError as e:
                raise ShapeError(e.message) from None
        else:
            stored[f.name] = _check_text(f, value)
    key = _target_key(action, target_id, stored.get("name"))
    if action == "create":
        return Normalized("knowledge_base", "create", None, None, key, stored, None)
    if not stored:
        raise ShapeError("Nothing to change. Give at least one field in changes.")
    assert target_id is not None and current is not None
    base = {k: getattr(current, k) for k in stored}
    return Normalized("knowledge_base", "change", None, target_id, key, stored, base)


def _target_key(action: str, target_id: str | None, name: str | None) -> str:
    from the_one.gleepglorp import kinds

    return kinds.target_key("knowledge_base", action, target_id, name)


# --- exists, apply, wording ---------------------------------------------------------------


async def _row_name(conn: Any, kb_id: str | None) -> str | None:
    """The current name of a knowledge base, else ``None``."""
    if not kb_id:
        return None
    for i, n in await _ref_entries(conn, "kb"):
        if i == kb_id:
            return n
    return None


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    if p.action == "create":
        return True
    return await _row_name(conn, p.target_id) is not None


def _write_deps(conn: aiosqlite.Connection, deps: KindDeps) -> kb_service.KbWriteDeps:
    from the_one.db.repositories import KnowledgeBaseRepository

    async def agent_store() -> Any:
        return deps.agent.store

    return kb_service.KbWriteDeps(
        repo=KnowledgeBaseRepository(conn),
        agent_store=agent_store,
        warm_up=lambda: schedule_warm_up(),
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
        write_deps = _write_deps(conn, deps)
        if p.action == "create":
            # The id is made here so the status mark, the summary and the config_changed frame
            # can carry it (the row does not exist until the write commits).
            kb_id = uuid.uuid4().hex[:12]
            result["target_id"] = kb_id
            await kb_service.create_knowledge_base(
                write_deps, {**changes, "id": kb_id}, on_commit=mark
            )
        else:
            assert p.target_id is not None
            current = await _row_name(conn, p.target_id)
            if current is not None:
                labels = changed_labels(KB_FIELDS, p)
                result["summary"] = f"Changed {', '.join(labels)} on knowledge base {current}"
                result["knowledge_base"] = current
            await kb_service.change_knowledge_base(
                write_deps, p.target_id, changes, base=base, override=override, on_commit=mark
            )
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(KB_FIELDS, p)
    name = p.changes.get("name") or ""
    if p.action == "create":
        text = f"Created knowledge base {name}"
    else:
        # ``apply`` adds the knowledge base's current name once it has looked it up.
        text = f"Changed {', '.join(labels)} on a knowledge base"
    return {"summary": text, "agent": None, "fields": labels}


def title(p: Proposal) -> str:
    name = p.changes.get("name") or ""
    return f"{p.action} knowledge base {name}".strip()


def card_title(action: str, name: str | None) -> str:
    quoted = f" “{name}”" if name else ""
    return f"{'Create' if action == 'create' else 'Change'} knowledge base{quoted}"


async def card_extras(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """The card's title and ``target_gone``, from a lookup by id at view time."""
    if p.action == "create":
        return {"title": card_title("create", p.changes.get("name")), "target_gone": False}
    current = await _row_name(conn, p.target_id)
    name = current or p.changes.get("name")
    return {"title": card_title("change", name), "target_gone": current is None}


async def fill_stale(conn: Any, fill: Any, labels: dict[str, str]) -> list[dict[str, Any]]:
    """The ``stale`` rows of a knowledge-base change fill: the named fields whose stored value
    moved since the fill was made, labelled."""
    source = await _load(conn, fill.target_id) if fill.target_id else None
    if source is None:
        return []
    return [
        {
            "field": row["field"],
            "label": labels.get(row["field"], row["field"]),
            "current": row["current"],
            "proposed": row["proposed"],
        }
        for row in kb_service.stale_fields(source, fill.changes, fill.base or {})
    ]


fill_extras = id_fill_extras(card_extras, stale_fn=fill_stale)


# --- warnings -----------------------------------------------------------------------------

WARN_ADD_FOLDERS = "Add its folders on the page after approving."
WARN_FILL_ADD_FOLDERS = "Add its folders on the page after saving."


def _rename_sentence(agents: list[str]) -> str:
    names = ", ".join(agents)
    return (
        f"Agents that use this knowledge base ({names}) get its tool under the new name; "
        "an agent that had that tool turned off keeps it off."
    )


async def warnings(
    conn: aiosqlite.Connection, enc: Any, p: Proposal, mode: str = "propose"
) -> list[str]:
    """What the operator should know before approving, read from the stored row. ``mode="fill"``
    words the approval-dependent sentence for a fill (saved on the page, never approved)."""
    if p.action == "create":
        return [WARN_FILL_ADD_FOLDERS if mode == "fill" else WARN_ADD_FOLDERS]
    out: list[str] = []
    if not p.target_id or "name" not in p.changes:
        return out
    current = await _row_name(conn, p.target_id)
    if current is None or current == p.changes["name"]:
        return out
    from the_one.db.repositories import SQLiteAgentStore

    agents = await SQLiteAgentStore(conn, enc).list_by_kb(p.target_id)
    if agents:
        out.append(_rename_sentence(agents))
    return out


KIND = Kind(
    name="knowledge_base",
    label="knowledge base",
    summary="Create a knowledge base or change its name or description",
    fields=KB_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    addressing="id",
    target_noun="A knowledge base",
    fill_extras=fill_extras,
    keyerror_is_gone=False,
    operator_only=OPERATOR_ONLY,
    operator_only_message=operator_only_message,
    fillable=("create", "change"),
    title=title,
    card_title=card_title,
    resolve_target=resolve_target,
    warnings=warnings,
    card_extras=card_extras,
)

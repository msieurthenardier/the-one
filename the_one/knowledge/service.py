"""The knowledge-base write service (Mission 36 Flight 5 Leg 3a, DD3, DD5).

The writes the knowledge-base routes make, moved out of ``the_one/interfaces/web/api.py`` so
GleepGlorp's approve path runs the same validation the operator's own save does. The routes
stay thin: they call :func:`create_knowledge_base` or :func:`replace_knowledge_base` and map
:class:`KbWriteError` / :class:`KbNotFound` to ``HTTPException``. A proposal calls
:func:`create_knowledge_base` or :func:`change_knowledge_base`.

This module imports nothing from ``fastapi``, ``the_one.interfaces`` or ``the_one.gleepglorp``,
and keeps the repository behind ``TYPE_CHECKING`` (an ``ast`` test pins both): it is injected
through :class:`KbWriteDeps`, together with the agent-store factory the rename carry needs and
the embedding warm-up function (so a unit test stubs it).

Both update shapes **read the row inside the write transaction**
(``KnowledgeBaseRepository.update_in_txn``), so a description committed while a name-only
save waited for the lock is never written back from a stale pre-read row.

Post-commit work (never inside the transaction): ``carry_kb_rename`` when the name changed
(``write_transaction`` raises on same-task re-entry, so the agent rewrite cannot be one atomic
unit with the row), and the embedding warm-up after a create.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiosqlite
from pydantic import ValidationError

from the_one.db.models import KnowledgeBase
from the_one.naming import NameRuleError, check_name, name_rule_detail

if TYPE_CHECKING:
    from the_one.db.repositories import KnowledgeBaseRepository

OnCommit = Callable[[aiosqlite.Connection], Awaitable[None]]

logger = logging.getLogger(__name__)

#: The fields :func:`change_knowledge_base` may set.
CHANGE_FIELDS = ("name", "description")


class KbWriteError(Exception):
    """A refused knowledge-base write: an HTTP-shaped ``status`` and ``detail`` (the exact
    payload the route returned before the move). It carries no HTTP type."""

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


class KbNotFound(Exception):  # noqa: N818 - the route answers 404
    """No knowledge base has this id."""

    def __init__(self, kb_id: str) -> None:
        super().__init__(f"Knowledge base not found: {kb_id}")
        self.kb_id = kb_id


class KbStaleError(Exception):
    """A touched field's stored value differs from the ``base`` the change was written
    against. ``fields`` is ``[{"field", "current", "proposed"}]``."""

    def __init__(self, fields: list[dict[str, Any]]) -> None:
        super().__init__("stale: " + ", ".join(str(f["field"]) for f in fields))
        self.fields = fields


@dataclass(frozen=True)
class KbWriteDeps:
    """What a knowledge-base write needs: the repository, the agent-store factory
    ``carry_kb_rename`` calls, and the warm-up function a create schedules."""

    repo: KnowledgeBaseRepository
    agent_store: Callable[[], Awaitable[Any]]
    warm_up: Callable[[], Any]


def validation_detail(e: ValidationError) -> list[dict]:
    """The 422 body for a pydantic ``ValidationError`` (no ``ctx``, no echoed input)."""
    return e.errors(include_context=False, include_input=False)


def checked_name(value: object) -> str:
    """The trimmed name, or a list-shaped 422 on ``loc ["name"]``."""
    try:
        return check_name(value)
    except NameRuleError as e:
        raise KbWriteError(422, name_rule_detail(e.message)) from None


def stale_fields(
    current: KnowledgeBase, changes: dict[str, Any], base: dict[str, Any]
) -> list[dict[str, Any]]:
    """The touched fields whose stored value is not the ``base`` value."""
    out: list[dict[str, Any]] = []
    for key, proposed in changes.items():
        if key not in CHANGE_FIELDS:
            continue
        cur = getattr(current, key)
        if key not in base or cur != base[key]:
            out.append({"field": key, "current": cur, "proposed": proposed})
    return out


async def _carry_rename(deps: KbWriteDeps, before: KnowledgeBase, after: KnowledgeBase) -> None:
    # L2-D7/L2-D9: the agent rewrite happens AFTER the knowledge-base row has committed.
    # Most writes touch only the description and must not load and re-save every attached
    # agent, hence the raw-name check here and the slug check inside.
    if before.name != after.name:
        from the_one.knowledge.kb_rename import carry_kb_rename

        await carry_kb_rename(before, after, get_agent_store=deps.agent_store)


async def create_knowledge_base(
    deps: KbWriteDeps, data: dict[str, Any], *, on_commit: OnCommit | None = None
) -> KnowledgeBase:
    """Create a knowledge base from a request body. ``on_commit`` runs inside the insert's
    transaction (a proposal's status mark rides there); the warm-up is scheduled after it."""
    data = dict(data)
    data["name"] = checked_name(data.get("name"))
    if "id" not in data:
        import uuid

        data["id"] = uuid.uuid4().hex[:12]
    try:
        kb = KnowledgeBase.model_validate(data)
    except ValidationError as e:
        # A client-supplied ``id`` (e.g. "../../../evil") must 422 via the model's charset
        # validator, not crash as a 500: ``KnowledgeBase.id`` builds a filesystem path.
        raise KbWriteError(422, validation_detail(e)) from None
    await deps.repo.create(kb, on_commit=on_commit)
    # M24 F02 L03, DD-1: kick the embedding warm-up on the operator's first knowledge base
    # after a cold start. Idempotent; the task handle is held inside ``the_one.embeddings``.
    deps.warm_up()
    logger.info("knowledge base %s: created", kb.id)
    return kb


async def replace_knowledge_base(
    deps: KbWriteDeps, kb_id: str, data: dict[str, Any]
) -> KnowledgeBase:
    """The route's PUT: the named fields in ``data`` merged onto the stored row and
    validated, all inside one ``update_in_txn``. ``KbNotFound`` for an unknown id."""
    data = dict(data)
    data["id"] = kb_id

    def mutate(existing: KnowledgeBase) -> KnowledgeBase:
        # ``model_copy(update=...)`` does NOT re-run field validators in Pydantic v2, so
        # round-trip through ``model_dump() | data -> model_validate`` (squawk 0013).
        try:
            merged = existing.model_dump()
            merged.update(data)
            if "name" in data:
                merged["name"] = checked_name(merged["name"])
            return KnowledgeBase.model_validate(merged)
        except ValidationError as e:
            raise KbWriteError(422, validation_detail(e)) from None

    try:
        before, after = await deps.repo.update_in_txn(kb_id, mutate)
    except KeyError:
        raise KbNotFound(kb_id) from None
    await _carry_rename(deps, before, after)
    logger.info("knowledge base %s: replaced", kb_id)
    return after


async def change_knowledge_base(
    deps: KbWriteDeps,
    kb_id: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> KnowledgeBase:
    """Apply a proposal's named fields (``name``, ``description``) to the row, inside one
    write transaction. ``base`` (the values the proposal was written against) is compared on
    the fresh row unless ``override``: a mismatch raises :class:`KbStaleError` and nothing is
    written. The rename carry runs after the commit. Returns the written row."""

    def mutate(current: KnowledgeBase) -> KnowledgeBase:
        if not override and base is not None:
            stale = stale_fields(current, changes, base)
            if stale:
                raise KbStaleError(stale)
        merged = current.model_dump()
        for key in CHANGE_FIELDS:
            if key in changes:
                merged[key] = changes[key]
        if "name" in changes:
            merged["name"] = checked_name(merged["name"])
        try:
            return KnowledgeBase.model_validate(merged)
        except ValidationError as e:
            raise KbWriteError(422, validation_detail(e)) from None

    try:
        before, after = await deps.repo.update_in_txn(kb_id, mutate, on_commit=on_commit)
    except KeyError:
        raise KbNotFound(kb_id) from None
    await _carry_rename(deps, before, after)
    logger.info("knowledge base %s: changed", kb_id)
    return after

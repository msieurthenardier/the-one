"""The ``secret`` kind: change a Library secret's name, description or allowed tools, or fill
the create form's metadata (Mission 36 F5 L3a, DD6).

A secret's **values are never a field of this kind.** No proposal and no fill carries, reads
or returns one, and nothing in this module calls the repository's value readers (a test greps
for them). A secret holds a name, a description, the tools it may be sent to
(``allowed_tools``, replaced whole on a change) and key/value pairs; only the first three are
metadata. The operator enters values on the secret's page.

- **A proposal may only change** (``actions == ("change",)``): a create needs at least one
  value, so a create proposal is refused and the model is told to fill the form instead.
- **A fill may create or change** (``fillable``): a create fill records only ``name``,
  ``description`` and ``allowed_tools``; the form's own first row is the value handoff.

``allowed_tools`` is checked at normalize through the secret service's own rules (non-empty,
no whitespace, 128 characters, refused tools), so a refused tool is refused with the route's
sentence at proposal or fill time. It is ``typed_items``: after outside content each tool added
must be named in the operator's own text (``the_one/gleepglorp/outside.py``), and it is in
``relaxed_guard_keys`` so a long MCP tool name is not mistaken for a key.

A secret is targeted by id or name; names are unique ignoring case, so a name matches ignoring
case. The write is the service's ``change_secret_metadata``.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

import aiosqlite

from the_one.gleepglorp.kinds.base import Kind, changed_labels, id_fill_extras
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import ApplyError, reraise
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    _check_text,
    _q,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.gleepglorp.view_core import _names
from the_one.naming import NAME_CONFLICT_SECRET, NameRuleError, check_name
from the_one.secret_store import service as secret_service

SECRET_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "text", "Name", "name", create_required=True),
    FieldSpec("description", "text", "Description", "description"),
    FieldSpec(
        "allowed_tools",
        "names",
        "Allowed tools",
        "allowed_tools",
        hint=(
            "the tools this secret may be sent to, replaced whole; at least one; tools that "
            "store or publish what they receive are refused"
        ),
        typed_items=True,
    ),
)
_BY_NAME = {f.name: f for f in SECRET_FIELDS}

# Fields the operator alone controls; never in any kind's spec (a test asserts it).
OPERATOR_ONLY = ("values", "keys", "secret_ids")

#: The stored keys whose values skip the guard's key-shape heuristics (a long MCP tool name,
#: ``mcp__goldfinch__captureScreenshot``, is not a key). The token-prefix rule and the
#: stored-secret check still apply.
RELAXED_GUARD_KEYS = frozenset({"allowed_tools"})

CREATE_REFUSED = (
    "Create a secret on the [Secrets](#library/secrets/~new) page; I can fill its name, "
    "description and allowed tools there."
)
VALUES_MESSAGE = "Secret values are entered only on the secret's page."


def operator_only_message(names: list[str]) -> str:
    return VALUES_MESSAGE


def action_refused(action: str, mode: str) -> str:
    if action == "create" and mode == "propose":
        return CREATE_REFUSED
    verb = "created" if action == "create" else "changed"
    how = "by a proposal" if mode == "propose" else "by filling its form"
    return f"A secret can't be {verb} {how}."


# --- resolution --------------------------------------------------------------------------


async def resolve_target(conn: Any, ref: Any) -> tuple[str, str]:
    """``(id, name)`` of an existing secret named by id (exact) or name (ignoring case: names
    are ``UNIQUE COLLATE NOCASE``, so a name matches at most one secret)."""
    if not isinstance(ref, str) or not ref.strip():
        raise ShapeError("Say which secret: give its name or id.")
    ref = ref.strip()
    entries = await _names(conn, "secrets")
    for entry_id, name in entries:
        if entry_id == ref:
            return entry_id, name
    folded = ref.casefold()
    hits = [(i, n) for i, n in entries if n.casefold() == folded]
    if not hits:
        raise ShapeError(f"No secret named {_q(ref)}.")
    if len(hits) > 1:
        listed = ", ".join(f"{n} ({i})" for i, n in hits)
        raise ShapeError(f"More than one secret is named {_q(ref)}: {listed}. Use the id instead.")
    return hits[0]


async def _load(conn: Any, enc: Any, secret_id: str) -> Any:
    """The stored secret (key names only, never a value), or ``None``."""
    from the_one.db.repositories import SecretRepository

    return await SecretRepository(conn, enc).get(secret_id)


# --- normalize ---------------------------------------------------------------------------


def _check_tools(value: Any) -> list[str]:
    errors: list[dict[str, Any]] = []
    tools = secret_service.check_allowed_tools(value, errors)
    if errors or tools is None:
        raise ShapeError(errors[0]["msg"] if errors else "allowed_tools must be a list of names.")
    return tools


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
                f"secret changes can't include {_q(key)!r}. Allowed fields: {', '.join(_BY_NAME)}."
            )
    current: Any = None
    target_id: str | None = None
    if action == "change":
        target_id, _name = await resolve_target(conn, target.get("target"))
        current = await _load(conn, enc, target_id)
        if current is None:
            raise ShapeError("No secret with that id.")
    stored: dict[str, Any] = {}
    for f in SECRET_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.name == "name":
            try:
                text = check_name(value)
            except NameRuleError as e:
                raise ShapeError(e.message) from None
            folded = text.casefold()
            for other_id, other_name in await _names(conn, "secrets"):
                if other_id != target_id and other_name.casefold() == folded:
                    raise ShapeError(NAME_CONFLICT_SECRET)
            stored["name"] = text
        elif f.name == "description":
            stored["description"] = _check_text(f, value)
        else:
            stored["allowed_tools"] = _check_tools(value)
    key = _target_key(action, target_id, stored.get("name"))
    if action == "create":
        return Normalized("secret", "create", None, None, key, stored, None)
    if not stored:
        raise ShapeError("Nothing to change. Give at least one field in changes.")
    assert target_id is not None and current is not None
    meta = secret_service.metadata_of(current)
    base = {k: meta[k] for k in stored}
    return Normalized("secret", "change", None, target_id, key, stored, base)


def _target_key(action: str, target_id: str | None, name: str | None) -> str:
    from the_one.gleepglorp import kinds

    return kinds.target_key("secret", action, target_id, name)


# --- exists, apply, wording ---------------------------------------------------------------


async def _row_name(conn: Any, secret_id: str | None) -> str | None:
    """The current name of a secret, else ``None``."""
    if not secret_id:
        return None
    for i, n in await _names(conn, "secrets"):
        if i == secret_id:
            return n
    return None


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    if p.action == "create":
        return True
    return await _row_name(conn, p.target_id) is not None


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
    if p.action != "change" or p.target_id is None:
        # A create is only ever a fill (the operator saves the form); a proposal never is one.
        raise ApplyError([{"loc": [], "msg": action_refused(p.action, "propose")}])
    try:
        current = await _row_name(conn, p.target_id)
        if current is not None:
            labels = changed_labels(SECRET_FIELDS, p)
            result["summary"] = f"Changed {', '.join(labels)} on secret {current}"
            result["secret"] = current
        await secret_service.change_secret_metadata(
            secret_service.SecretWriteDeps(repo=deps.agent.secret_repo),
            p.target_id,
            changes,
            base=base,
            override=override,
            on_commit=mark,
        )
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(SECRET_FIELDS, p)
    name = p.changes.get("name") or ""
    if p.action == "create":
        text = f"Created secret {name}"
    else:
        # ``apply`` adds the secret's current name once it has looked it up.
        text = f"Changed {', '.join(labels)} on a secret"
    return {"summary": text, "agent": None, "fields": labels}


def title(p: Proposal) -> str:
    name = p.changes.get("name") or ""
    return f"{p.action} secret {name}".strip()


def card_title(action: str, name: str | None) -> str:
    quoted = f" “{name}”" if name else ""
    return f"{'Create' if action == 'create' else 'Change'} secret{quoted}"


async def card_extras(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """The card's title and ``target_gone``, from a lookup by id at view time."""
    if p.action == "create":
        return {"title": card_title("create", p.changes.get("name")), "target_gone": False}
    current = await _row_name(conn, p.target_id)
    name = current or p.changes.get("name")
    return {"title": card_title("change", name), "target_gone": current is None}


async def fill_stale(conn: Any, fill: Any, labels: dict[str, str]) -> list[dict[str, Any]]:
    """The ``stale`` rows of a secret change fill: the named fields whose stored value moved
    since the fill was made, labelled (metadata only)."""
    source = await _load(conn, None, fill.target_id) if fill.target_id else None
    if source is None:
        return []
    return [
        {
            "field": row["field"],
            "label": labels.get(row["field"], row["field"]),
            "current": row["current"],
            "proposed": row["proposed"],
        }
        for row in secret_service.stale_fields(
            secret_service.metadata_of(source), fill.changes, fill.base or {}
        )
    ]


fill_extras = id_fill_extras(card_extras, stale_fn=fill_stale)


# --- warnings -----------------------------------------------------------------------------

WARN_RENAME = "Agents keep this secret; their placeholders use its keys, not its name."


def _join(items: list[str]) -> str:
    return ", ".join(items)


async def warnings(
    conn: aiosqlite.Connection, enc: Any, p: Proposal, mode: str = "propose"
) -> list[str]:
    """What the operator should know before approving (or saving), read from the stored row.
    Key names only, never a value. The sentences do not mention approval, so ``mode`` is not
    read."""
    out: list[str] = []
    if p.action != "change" or not p.target_id:
        return out
    current = await _load(conn, enc, p.target_id)
    if current is None:
        return out
    changes = p.changes
    if "allowed_tools" in changes:
        have = set(current.allowed_tools)
        added = [t for t in changes["allowed_tools"] if t not in have]
        if added:
            keys = [v.key for v in current.values]
            subject = _join(keys) if keys else "Its values"
            out.append(f"{subject} can then be sent to {_join(added)}.")
    if "name" in changes and changes["name"] != current.name:
        out.append(WARN_RENAME)
    return out


KIND = Kind(
    name="secret",
    label="secret",
    summary="Change a secret's name, description or allowed tools (values are never set here)",
    fields=SECRET_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    addressing="id",
    target_noun="A secret",
    fill_extras=fill_extras,
    keyerror_is_gone=False,
    operator_only=OPERATOR_ONLY,
    operator_only_message=operator_only_message,
    actions=("change",),
    fillable=("create", "change"),
    action_refused=action_refused,
    title=title,
    card_title=card_title,
    resolve_target=resolve_target,
    warnings=warnings,
    card_extras=card_extras,
    relaxed_guard_keys=RELAXED_GUARD_KEYS,
)

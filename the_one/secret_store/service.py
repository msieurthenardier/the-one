"""The secret write service (Mission 36 Flight 5 Leg 3a, DD3, DD6).

The validation and writes the secret routes make, moved out of
``the_one/interfaces/web/secrets_api.py`` so GleepGlorp's approve path runs the same checks the
operator's own save does. The routes stay thin: they call :func:`create_secret` or
:func:`replace_secret` and map :class:`SecretWriteError` / :class:`SecretNotFound` to
``HTTPException``. A proposal calls :func:`change_secret_metadata`.

**No value ever passes through the change path.** :func:`change_secret_metadata` sets only
``name``, ``description`` and ``allowed_tools`` and never passes ``values`` to the repository,
so no stored value is read, written or returned by it (a test greps for it). Every 422 detail
is a ``{type, loc, msg}`` list whose ``msg`` is a fixed sentence: an input is never echoed.

This module imports nothing from ``fastapi``, ``the_one.interfaces`` or ``the_one.gleepglorp``;
the repository is injected through :class:`SecretWriteDeps`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiosqlite

from the_one.agent.write_checks import name_conflict_detail
from the_one.db.repositories import SECRET_MASK, Secret, SecretInvalid, SecretNameConflict
from the_one.naming import NAME_CONFLICT_SECRET, NameRuleError, check_name, name_rule_detail
from the_one.secret_store.refused import is_refused_tool

if TYPE_CHECKING:
    from the_one.db.repositories import SecretRepository

OnCommit = Callable[[aiosqlite.Connection], Awaitable[None]]

logger = logging.getLogger(__name__)

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TOOL_NAME_MAX = 128

#: The metadata fields :func:`change_secret_metadata` may set (never the values).
CHANGE_FIELDS = ("name", "description", "allowed_tools")


class SecretWriteError(Exception):
    """A refused secret write: an HTTP-shaped ``status`` and ``detail`` (the exact payload the
    route returned before the move). It carries no HTTP type."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"{status}: {detail!r}")
        self.status = status
        self.detail = detail

    @property
    def items(self) -> list[dict[str, Any]]:
        """``[{loc, msg}]`` for the approve path (a 409 name conflict lands on ``["name"]``)."""
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


class SecretNotFound(Exception):  # noqa: N818 - the route answers 404
    """No secret has this id."""

    def __init__(self, secret_id: str) -> None:
        super().__init__("Secret not found.")
        self.secret_id = secret_id


class SecretStaleError(Exception):
    """A touched field's stored value differs from the ``base`` the change was written
    against. ``fields`` is ``[{"field", "current", "proposed"}]``."""

    def __init__(self, fields: list[dict[str, Any]]) -> None:
        super().__init__("stale: " + ", ".join(str(f["field"]) for f in fields))
        self.fields = fields


@dataclass(frozen=True)
class SecretWriteDeps:
    """What a secret write needs: the repository (injected)."""

    repo: SecretRepository


# ── Validation (shared by POST, PUT and a proposal's change) ─────────────


def _err(loc: list[Any], msg: str) -> dict[str, Any]:
    return {"type": "value_error", "loc": loc, "msg": msg}


def checked_name(value: object) -> str:
    """The trimmed name, or a list-shaped 422 on ``loc ["name"]``."""
    try:
        return check_name(value)
    except NameRuleError as e:
        raise SecretWriteError(422, name_rule_detail(e.message)) from None


def check_allowed_tools(raw: Any, errors: list[dict[str, Any]]) -> list[str] | None:
    """The trimmed, de-duplicated tool names, or ``None`` with the problems appended to
    ``errors`` (a refused tool among them)."""
    if not isinstance(raw, list) or not raw:
        errors.append(
            _err(["allowed_tools"], "Choose at least one tool that may receive this secret.")
        )
        return None
    tools: list[str] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, str):
            errors.append(_err(["allowed_tools", i], "A tool name must be text."))
            continue
        name = entry.strip()
        if not name or len(name) > TOOL_NAME_MAX:
            errors.append(
                _err(["allowed_tools", i], f"A tool name must be 1 to {TOOL_NAME_MAX} characters.")
            )
        elif re.search(r"\s", name):
            errors.append(_err(["allowed_tools", i], "A tool name can't contain whitespace."))
        elif is_refused_tool(name):
            errors.append(
                _err(
                    ["allowed_tools", i],
                    f"{name} stores or publishes what it receives, so it can't receive secrets.",
                )
            )
        else:
            tools.append(name)
    return list(dict.fromkeys(tools))


def check_values(
    raw: Any, errors: list[dict[str, Any]], *, creating: bool
) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or not raw:
        errors.append(_err(["values"], "Add at least one key and value."))
        return None
    pairs: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_ids: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(_err(["values", i], "Each entry must have a key and a value."))
            continue
        key, value, pair_id = item.get("key"), item.get("value"), item.get("id")
        if not isinstance(key, str) or not KEY_PATTERN.match(key):
            errors.append(
                _err(
                    ["values", i, "key"],
                    "A key can use letters, digits, _ and -, 1 to 64 characters.",
                )
            )
        elif key.lower() in seen_keys:
            errors.append(_err(["values", i, "key"], "This key repeats an earlier key."))
        else:
            seen_keys.add(key.lower())
        if pair_id is not None:
            if not isinstance(pair_id, str):
                errors.append(_err(["values", i, "id"], "A pair id must be text."))
            elif pair_id in seen_ids:
                errors.append(_err(["values", i, "id"], "This id repeats an earlier id."))
            else:
                seen_ids.add(pair_id)
        if not isinstance(value, str) or not value:
            errors.append(_err(["values", i, "value"], "A value must be non-empty text."))
        elif value == SECRET_MASK and (creating or pair_id is None):
            errors.append(
                _err(["values", i, "value"], "Enter the value; a masked value needs its pair id.")
            )
        pairs.append(
            {
                "id": pair_id if isinstance(pair_id, str) else None,
                "key": key if isinstance(key, str) else "",
                "value": value if isinstance(value, str) else "",
            }
        )
    return pairs


def parse_secret(data: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    """The validated, trimmed fields present in ``data`` (all of them when creating); raises
    :class:`SecretWriteError` (422, the list-shaped detail) otherwise. Never echoes an input."""
    out: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    if creating or "name" in data:
        out["name"] = checked_name(data.get("name"))
    if "description" in data:
        if isinstance(data["description"], str):
            out["description"] = data["description"]
        else:
            errors.append(_err(["description"], "A description must be text."))
    elif creating:
        out["description"] = ""
    if creating or "allowed_tools" in data:
        tools = check_allowed_tools(data.get("allowed_tools"), errors)
        if tools is not None:
            out["allowed_tools"] = tools
    if creating or "values" in data:
        pairs = check_values(data.get("values"), errors, creating=creating)
        if pairs is not None:
            out["values"] = pairs
    if errors:
        raise SecretWriteError(422, errors)
    return out


def name_conflict() -> SecretWriteError:
    return SecretWriteError(409, name_conflict_detail(NAME_CONFLICT_SECRET))


def stale_fields(
    current: dict[str, Any], changes: dict[str, Any], base: dict[str, Any]
) -> list[dict[str, Any]]:
    """The touched metadata fields whose stored value is not the ``base`` value. ``current``
    is ``{name, description, allowed_tools}``; ``allowed_tools`` compares as a list."""
    out: list[dict[str, Any]] = []
    for key, proposed in changes.items():
        if key not in CHANGE_FIELDS:
            continue
        cur = current.get(key)
        if key not in base or cur != base[key]:
            out.append({"field": key, "current": cur, "proposed": proposed})
    return out


def metadata_of(secret: Secret) -> dict[str, Any]:
    """``{name, description, allowed_tools}`` of a stored secret (no values, no key names)."""
    return {
        "name": secret.name,
        "description": secret.description,
        "allowed_tools": list(secret.allowed_tools),
    }


# ── Writes ───────────────────────────────────────────────────────────────


async def create_secret(deps: SecretWriteDeps, data: dict[str, Any]) -> Secret:
    """Create a secret from a request body (the route's POST)."""
    fields = parse_secret(data, creating=True)
    try:
        secret = await deps.repo.create(
            fields["name"], fields["description"], fields["allowed_tools"], fields["values"]
        )
    except SecretNameConflict:
        raise name_conflict() from None
    except SecretInvalid as e:
        raise SecretWriteError(422, e.details) from None
    logger.info("secret %s: created", secret.id)
    return secret


async def replace_secret(deps: SecretWriteDeps, secret_id: str, data: dict[str, Any]) -> Secret:
    """The route's PUT: a partial update of the fields present in ``data``. The 404 precedes
    the 422, as it always has."""
    if await deps.repo.get(secret_id) is None:
        raise SecretNotFound(secret_id)
    fields = parse_secret(data, creating=False)
    try:
        secret = await deps.repo.update(secret_id, **fields)
    except KeyError:
        raise SecretNotFound(secret_id) from None
    except SecretNameConflict:
        raise name_conflict() from None
    except SecretInvalid as e:
        raise SecretWriteError(422, e.details) from None
    logger.info("secret %s: replaced", secret_id)
    return secret


async def change_secret_metadata(
    deps: SecretWriteDeps,
    secret_id: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> Secret:
    """Apply a proposal's metadata fields (``name``, ``description``, ``allowed_tools``).

    ``allowed_tools`` is replaced whole, through :func:`check_allowed_tools`. ``base`` is
    compared against the row read inside the write transaction unless ``override``: a mismatch
    raises :class:`SecretStaleError` and nothing is written. Values are never passed to the
    repository."""
    fields = parse_secret({k: v for k, v in changes.items() if k in CHANGE_FIELDS}, creating=False)

    def precheck(row: dict[str, Any]) -> None:
        if override or base is None:
            return
        stale = stale_fields(row, changes, base)
        if stale:
            raise SecretStaleError(stale)

    try:
        secret = await deps.repo.update(secret_id, **fields, precheck=precheck, on_commit=on_commit)
    except KeyError:
        raise SecretNotFound(secret_id) from None
    except SecretNameConflict:
        raise name_conflict() from None
    except SecretInvalid as e:
        raise SecretWriteError(422, e.details) from None
    logger.info("secret %s: metadata changed", secret_id)
    return secret

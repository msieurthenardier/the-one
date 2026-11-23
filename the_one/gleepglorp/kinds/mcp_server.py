"""The ``mcp_server`` kind: create an MCP server or change its address, command or rows
(Mission 36 F4 L4a, DD9).

GleepGlorp may set a server's ``name``, and on a create its ``type``; for a local (stdio)
server the ``command``, ``args`` and ``env`` rows; for a remote (HTTP) server the ``url`` and
``headers`` rows. Rows merge per row (a row is added or its value changed, never removed).

It never sets ``cwd``, ``sandbox`` or ``secrets``, never switches a server's type (the
operator does that in the editor), and never writes a Sensitive value: a row whose name is
stored as Sensitive, is OAuth-managed, or looks like a secret is refused (the operator enters
it in the editor with Sensitive on). Header names compare case-insensitively, env names
exactly. The write is the MCP write service's (``the_one/mcp/service.py``), so the operator's
own validation applies and the proposal's status mark rides in the write's transaction.

A server is targeted by id (or an unambiguous name) through ``target``; the proposal's
``agent_name`` is ``None`` and the card's name and ``target_gone`` come from a lookup by id.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, tzinfo
from pathlib import PurePath
from typing import Any
from urllib.parse import urlparse

import aiosqlite

from the_one.gleepglorp.kinds.base import Kind, changed_labels, id_fill_extras
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    _bad,
    _check_text,
    _q,
    _ref_entries,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.mcp import service as mcp_service
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS
from the_one.mcp.service import (  # noqa: F401 - the rule's home is the service; re-exported
    SECRET_KEY_SEGMENTS,
    looks_secret_key,
    secret_args_flag,
)
from the_one.naming import NameRuleError, check_name
from the_one.self_configuration.constants import SURFACE_ROW_NAME

TYPES = ("stdio", "streamable-http")
_COMMAND_MAX = 1000
_ARG_MAX = 2000
_ARGS_MAX = 100
_URL_MAX = 2000
_ROWS_MAX = 50
_ROW_NAME_MAX = 200
_ROW_VALUE_MAX = 2000
_STDIO_ONLY = ("command", "args", "env")
_HTTP_ONLY = ("url", "headers")
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_ENV_NAME_RE = re.compile(r"^[^\s=\x00]+$")
_DOWNLOADING_RUNTIMES = ("npx", "pipx", "uvx")

MCP_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "text", "Name", "name", create_required=True),
    FieldSpec(
        "type",
        "text",
        "Type",
        "type",
        hint="stdio (a local program) or streamable-http (a remote server)",
        create_required=True,
        create_only=True,
    ),
    FieldSpec(
        "command",
        "text",
        "Command",
        "command",
        hint="stdio: the program to run, for example npx; put its arguments in args",
        path=("config", "command"),
        address_or_command=True,
    ),
    FieldSpec(
        "args",
        "names",
        "Arguments",
        "args",
        hint="stdio: a list of text arguments, in order",
        path=("config", "args"),
        address_or_command=True,
    ),
    FieldSpec(
        "url",
        "text",
        "URL",
        "url",
        hint="streamable-http: an http or https address",
        path=("config", "url"),
        address_or_command=True,
    ),
    FieldSpec(
        "env",
        "rows",
        "Environment",
        "env",
        hint="stdio: environment variables; a Sensitive one is entered by the operator",
        path=("config", "env"),
        address_or_command=True,
        rows=True,
    ),
    FieldSpec(
        "headers",
        "rows",
        "Headers",
        "headers",
        hint="streamable-http: request headers; a Sensitive one is entered by the operator",
        path=("config", "headers"),
        address_or_command=True,
        rows=True,
    ),
)
_BY_NAME = {f.name: f for f in MCP_FIELDS}
_ROW_SPECS = {"env": "Env", "headers": "Header"}

# Fields the operator alone controls; never in any kind's spec (a test asserts it).
OPERATOR_ONLY = ("cwd", "sandbox", "secrets")

#: The keys whose values skip the guard's key-shape heuristics (a Docker digest or a UUID
#: path is not a key). ``env`` and ``headers`` keep every heuristic.
RELAXED_GUARD_KEYS = frozenset({"url", "command", "args"})

TYPE_CHANGE_MESSAGE = (
    "The type of an existing MCP server can't be changed from here. Tell the operator to "
    "change the type in the MCP server editor."
)


def create_only_message(names: list[str]) -> str:
    return (
        TYPE_CHANGE_MESSAGE
        if "type" in names
        else (f"{', '.join(names)} can only be set when creating an MCP server.")
    )


# --- resolution --------------------------------------------------------------------------


async def resolve_target(conn: Any, ref: Any) -> tuple[str, str]:
    """``(id, name)`` of an existing MCP server named by id or name. The self-configuration
    surface rows are never resolvable (``_ref_entries`` leaves them out)."""
    from the_one.gleepglorp import kinds

    return kinds.resolve_by_id_or_name(await _ref_entries(conn, "mcp"), ref, "MCP server")


async def _load(conn: Any, enc: Any, source_id: str) -> Any:
    """The stored source (decrypted), or ``None``; never a surface row."""
    from the_one.config import settings
    from the_one.db.repositories import MCPSourceRepository
    from the_one.encryption import get_encryptor
    from the_one.self_configuration.constants import is_surface_row

    repo = MCPSourceRepository(conn, enc if enc is not None else get_encryptor(settings.data_dir))
    try:
        source = await repo.get(source_id)
    except KeyError:
        return None
    return None if is_surface_row(source) else source


# --- value checks ------------------------------------------------------------------------


def _check_url(spec: FieldSpec, value: Any) -> str:
    text = _check_text(spec, value).strip()
    if len(text) > _URL_MAX:
        raise ShapeError(f"url is limited to {_URL_MAX:,} characters.")
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ShapeError("url must be an http or https address.")
    return text


def _check_command(spec: FieldSpec, value: Any) -> str:
    text = _check_text(spec, value).strip()
    if not text:
        raise _bad(spec, "the program to run")
    if len(text) > _COMMAND_MAX:
        raise ShapeError(f"command is limited to {_COMMAND_MAX:,} characters.")
    return text


def _check_args(spec: FieldSpec, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(a, str) for a in value):
        raise _bad(spec, "a list of text items")
    if len(value) > _ARGS_MAX:
        raise ShapeError(f"args is limited to {_ARGS_MAX} items.")
    if any(len(a) > _ARG_MAX for a in value):
        raise ShapeError(f"Each item of args is limited to {_ARG_MAX:,} characters.")
    flag = secret_args_flag(value)
    if flag is not None:
        raise ShapeError(f"The flag {_q(flag)} looks like a secret. {mcp_service.HANDOFF}")
    return list(value)


def _check_rows(
    spec: FieldSpec, value: Any, secrets: dict[str, Any], *, fill: bool = False
) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise _bad(spec, "an object of name and value")
    if len(value) > _ROWS_MAX:
        raise ShapeError(f"{spec.name} is limited to {_ROWS_MAX} rows.")
    name_re = _HEADER_NAME_RE if spec.name == "headers" else _ENV_NAME_RE
    out: dict[str, str] = {}
    seen: set[str] = set()
    for row_name, row_value in value.items():
        if not isinstance(row_name, str) or not row_name.strip():
            raise ShapeError(f"Each {spec.name} row needs a name.")
        if len(row_name) > _ROW_NAME_MAX or not name_re.match(row_name):
            raise ShapeError(f"{_q(row_name)} isn't a valid {_ROW_SPECS[spec.name].lower()} name.")
        if not isinstance(row_value, str):
            raise ShapeError(f"The value of {_q(row_name)} must be text.")
        if len(row_value) > _ROW_VALUE_MAX:
            raise ShapeError(f"A {spec.name} value is limited to {_ROW_VALUE_MAX:,} characters.")
        folded = row_name.lower() if spec.name == "headers" else row_name
        if folded in seen:
            raise ShapeError(f"{_q(row_name)} appears twice in {spec.name}.")
        seen.add(folded)
        refusal = mcp_service.row_refusal(spec.name, row_name, row_value, secrets)
        if refusal is not None:
            raise ShapeError(refusal)
        if fill and row_value == "" and looks_secret_key(row_name):
            # The handoff (leg 4b): a fill's bare "" for a secret-looking key becomes an empty
            # Sensitive row the operator fills in. A proposal never does this.
            out[row_name] = row_value
            continue
        if not row_value.strip():
            raise ShapeError(
                f"{_q(row_name)} has no value. A proposal can't add an empty row; "
                "tell the operator to add it in the MCP server editor."
            )
        out[row_name] = row_value
    return out


def _check_name_unique(name: str, entries: list[tuple[str, str]], self_id: str | None) -> None:
    folded = name.casefold()
    if name == SURFACE_ROW_NAME:
        raise ShapeError(f"{_q(name)} is reserved. Choose another name.")
    if any(n.casefold() == folded for i, n in entries if i != self_id):
        raise ShapeError(f"An MCP server named {_q(name)} already exists.")


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
    for key in changes:
        if key in OPERATOR_ONLY:
            raise ShapeError(f"{key} can only be set by the operator, in the MCP server editor.")
        if key not in _BY_NAME:
            raise ShapeError(
                f"mcp_server changes can't include {_q(key)!r}. "
                f"Allowed fields: {', '.join(_BY_NAME)}."
            )
    entries = await _ref_entries(conn, "mcp")
    source: Any = None
    target_id: str | None = None
    if action == "change":
        if "type" in changes:
            raise ShapeError(TYPE_CHANGE_MESSAGE)
        target_id, _name = await resolve_target(conn, target.get("target"))
        source = await _load(conn, enc, target_id)
        if source is None:
            raise ShapeError("No MCP server with that id.")
        kind_type = source.type
    else:
        kind_type = changes.get("type")
        if kind_type not in TYPES:
            raise ShapeError(f"type must be one of: {', '.join(TYPES)}.")
    wrong = _HTTP_ONLY if kind_type == "stdio" else _STDIO_ONLY
    stray = [k for k in changes if k in wrong]
    if stray:
        shown = "a local program (stdio)" if kind_type == "stdio" else "a remote server (HTTP)"
        raise ShapeError(f"{', '.join(stray)} doesn't apply to {shown}.")

    secrets = dict(source.secrets) if source is not None else {}
    stored: dict[str, Any] = {}
    for f in MCP_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.name == "name":
            try:
                text = check_name(value)
            except NameRuleError as e:
                raise ShapeError(e.message) from None
            _check_name_unique(text, entries, target_id)
            stored["name"] = text
        elif f.name == "type":
            stored["type"] = kind_type
        elif f.name == "command":
            stored["command"] = _check_command(f, value)
        elif f.name == "args":
            stored["args"] = _check_args(f, value)
        elif f.name == "url":
            stored["url"] = _check_url(f, value)
        else:
            stored[f.name] = _check_rows(f, value, secrets, fill=mode == "fill")
    if action == "create":
        needed = "command" if kind_type == "stdio" else "url"
        if needed not in stored:
            raise ShapeError(f"A new {kind_type} MCP server needs {needed}.")
        name = stored["name"]
        key = _target_key("create", None, name)
        return Normalized("mcp_server", "create", None, None, key, stored, None)
    if not stored:
        raise ShapeError("Nothing to change. Give at least one field in changes.")
    assert target_id is not None and source is not None
    key = _target_key("change", target_id, None)
    return Normalized("mcp_server", "change", None, target_id, key, stored, _base(source, stored))


def _target_key(action: str, target_id: str | None, name: str | None) -> str:
    from the_one.gleepglorp import kinds

    return kinds.target_key("mcp_server", action, target_id, name)


def _base(source: Any, stored: dict[str, Any]) -> dict[str, Any]:
    """The stored value of each named field: only the keys named, and for rows only the named
    rows that exist now (a row absent now is left out, so "absent then, present at apply"
    reads as stale). Never ``None``."""
    cfg = source.config or {}
    base: dict[str, Any] = {}
    for key, proposed in stored.items():
        if key == "name":
            base["name"] = source.name
        elif key == "type":
            continue
        elif key in _ROW_SPECS:
            current = cfg.get(key) if isinstance(cfg.get(key), dict) else {}
            fold = (lambda s: s.lower()) if key == "headers" else (lambda s: s)
            rows: dict[str, Any] = {}
            for row_name in proposed:
                for k, v in current.items():
                    if fold(str(k)) == fold(row_name):
                        rows[row_name] = v
                        break
            base[key] = rows
        elif key in cfg:
            base[key] = cfg[key]
    return base


# --- exists, apply, wording ---------------------------------------------------------------


async def _row_name(conn: Any, source_id: str | None) -> str | None:
    """The current name of a server (never a surface row), else ``None``."""
    if not source_id:
        return None
    for i, n in await _ref_entries(conn, "mcp"):
        if i == source_id:
            return n
    return None


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    if p.action == "create":
        return True
    return await _row_name(conn, p.target_id) is not None


def _write_deps(deps: KindDeps) -> mcp_service.McpWriteDeps:
    agent = deps.agent

    async def agent_store() -> Any:
        return agent.store

    async def secret_repo() -> Any:
        return agent.secret_repo

    return mcp_service.McpWriteDeps(
        repo=agent.mcp_repo, agent_store=agent_store, secret_repo=secret_repo
    )


def _create_body(changes: dict[str, Any], source_id: str) -> dict[str, Any]:
    config = {k: changes[k] for k in (*_STDIO_ONLY, *_HTTP_ONLY) if k in changes}
    return {"id": source_id, "name": changes["name"], "type": changes["type"], "config": config}


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
        write_deps = _write_deps(deps)
        if p.action == "create":
            # The id is made here so the status mark, the summary and the config_changed
            # frame can carry it (the row does not exist until the write commits).
            source_id = uuid.uuid4().hex[:12]
            result["target_id"] = source_id
            await mcp_service.create_mcp_source(
                write_deps, _create_body(changes, source_id), on_commit=mark
            )
        else:
            assert p.target_id is not None
            current = await _row_name(conn, p.target_id)
            if current is not None:
                labels = changed_labels(MCP_FIELDS, p)
                result["summary"] = f"Changed {', '.join(labels)} on MCP server {current}"
                result["server"] = current
            await mcp_service.change_mcp_source(
                write_deps, p.target_id, changes, base=base, override=override, on_commit=mark
            )
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(MCP_FIELDS, p)
    name = p.changes.get("name") or ""
    if p.action == "create":
        text = f"Created MCP server {name}"
    else:
        # ``apply`` adds the server's current name once it has looked it up.
        text = f"Changed {', '.join(labels)} on an MCP server"
    return {"summary": text, "agent": None, "fields": labels}


def title(p: Proposal) -> str:
    name = p.changes.get("name") or ""
    return f"{p.action} MCP server {name}".strip()


def card_title(action: str, name: str | None) -> str:
    quoted = f" “{name}”" if name else ""
    return f"{'Create' if action == 'create' else 'Change'} MCP server{quoted}"


async def card_extras(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """The card's title and ``target_gone``, from a lookup by id at view time (the proposal
    has no ``agent_name``)."""
    if p.action == "create":
        return {"title": card_title("create", p.changes.get("name")), "target_gone": False}
    # An applied rename shows the name it has now; the lookup is by id either way.
    current = await _row_name(conn, p.target_id)
    name = current or p.changes.get("name")
    return {"title": card_title("change", name), "target_gone": current is None}


async def fill_stale(conn: Any, fill: Any, labels: dict[str, str]) -> list[dict[str, Any]]:
    """The ``stale`` rows of an MCP server change fill: the named fields whose stored value
    moved since the fill was made, rows shown one per key (``"Header X"``)."""
    from the_one.gleepglorp.proposals.store import display_values
    from the_one.mcp.service import stale_fields

    source = await _load(conn, None, fill.target_id) if fill.target_id else None
    if source is None:
        return []
    out: list[dict[str, Any]] = []
    for row in stale_fields(source, fill.changes, fill.base or {}):
        field = row["field"]
        current, proposed = row["current"], row["proposed"]
        if isinstance(proposed, dict):
            current = await display_values(conn, {field: current or {}})
            proposed = await display_values(conn, {field: proposed})
        out.append(
            {
                "field": field,
                "label": labels.get(field, field),
                "current": current,
                "proposed": proposed,
            }
        )
    return out


fill_extras = id_fill_extras(card_extras, stale_fn=fill_stale)


# --- warnings -----------------------------------------------------------------------------


WARN_URL = (
    "This server holds saved sign-in details or Sensitive headers. They will be sent to the "
    "new address."
)
WARN_COMMAND = "This server has Sensitive environment values. The new command will receive them."
WARN_DOWNLOAD = (
    "The first run downloads the package. If Test fails, you may need to allow network in the "
    "server's sandbox settings, which only you can change."
)


async def warnings(
    conn: aiosqlite.Connection, enc: Any, p: Proposal, mode: str = "propose"
) -> list[str]:
    """What the operator should know before approving, read from the stored row. The sentences
    carry no approval wording, so ``mode`` (``"propose"`` or ``"fill"``) is ignored."""
    del mode
    out: list[str] = []
    changes = p.changes
    if p.action == "create":
        command = changes.get("command")
        if (
            changes.get("type") == "stdio"
            and isinstance(command, str)
            and PurePath(command.strip().split()[0] if command.strip() else "").name
            in _DOWNLOADING_RUNTIMES
        ):
            out.append(WARN_DOWNLOAD)
        return out
    source = await _load(conn, enc, p.target_id) if p.target_id else None
    if source is None:
        return out
    held = {k for k in source.secrets if k not in OAUTH_MANAGED_SECRET_KEYS}
    signed_in = any(k in source.secrets for k in OAUTH_MANAGED_SECRET_KEYS)
    cfg = source.config or {}
    if "url" in changes and changes["url"] != cfg.get("url") and (held or signed_in):
        out.append(WARN_URL)
    if source.type == "stdio" and held:
        if ("command" in changes and changes["command"] != cfg.get("command")) or (
            "args" in changes and changes["args"] != cfg.get("args", [])
        ):
            out.append(WARN_COMMAND)
    return out


KIND = Kind(
    name="mcp_server",
    label="MCP server",
    summary="Create an MCP server or change its address, command or rows",
    fields=MCP_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    addressing="id",
    target_noun="An MCP server",
    fill_extras=fill_extras,
    keyerror_is_gone=True,
    operator_only=OPERATOR_ONLY,
    fillable=("create", "change"),
    title=title,
    card_title=card_title,
    resolve_target=resolve_target,
    warnings=warnings,
    card_extras=card_extras,
    relaxed_guard_keys=RELAXED_GUARD_KEYS,
    create_only_message=create_only_message,
)

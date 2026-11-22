"""The MCP source write service (Mission 36 Flight 4 Leg 4a, DD9).

The writes the MCP routes make, moved out of ``the_one/interfaces/web/api.py`` so GleepGlorp's
approve path runs the same validation the operator's own save does. The routes stay thin: they
call :func:`create_mcp_source` or :func:`replace_mcp_source` and map :class:`McpWriteError` to
``HTTPException``. A proposal calls :func:`create_mcp_source` or :func:`change_mcp_source`.

This module imports nothing from ``fastapi``, ``the_one.interfaces`` or ``the_one.gleepglorp``
(an ``ast`` test pins it). Every refusal raises :class:`McpWriteError` carrying the status and
the exact ``detail`` the route returned before the move.

Two write shapes:

- :func:`replace_mcp_source` is the route's PUT exactly (full replace with per-key mask
  handling).
- :func:`change_mcp_source` merges **named fields** onto the row **re-read inside the write
  transaction** (``MCPSourceRepository.update_in_txn``), so the ``_cache`` and the OAuth
  secrets are always current, and a proposal's stale check and status mark ride in the write.

Post-commit side effects (era, connection eviction, tool-cache drop, rename carries) run in
the route's order and under its conditions, only after the write committed.

The secret-looking key rule (:func:`looks_secret_key`) lives here, beside the refusal that
uses it; the GleepGlorp kind re-exports it.
"""

from __future__ import annotations

import copy
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiosqlite
from pydantic import ValidationError

from the_one.db.models import MCPSource
from the_one.db.repositories import AgentMcpToolCacheRepository, MCPSourceRepository
from the_one.mcp._era import forget_era
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS
from the_one.naming import NameRuleError, check_name, name_rule_detail
from the_one.secret_mask import looks_masked
from the_one.self_configuration.constants import SURFACE_ROW_NAME, is_surface_row

logger = logging.getLogger(__name__)

OnCommit = Callable[[aiosqlite.Connection], Awaitable[None]]

#: The fields :func:`change_mcp_source` may set (a flat shape; ``env`` and ``headers`` are
#: ``{name: value}`` rows merged per row).
CHANGE_FIELDS = ("name", "command", "args", "url", "env", "headers")
_STDIO_FIELDS = ("command", "args", "env")
_HTTP_FIELDS = ("url", "headers")
_ROW_FIELDS = ("env", "headers")

#: A name that has one of these as a whole segment is secret-looking (see
#: :func:`looks_secret_key`).
SECRET_KEY_SEGMENTS = frozenset(
    {
        "authorization",
        "token",
        "tokens",
        "secret",
        "secrets",
        "password",
        "passwd",
        "pwd",
        "apikey",
        "key",
        "credential",
        "credentials",
        "bearer",
        "cookie",
    }
)
_SECRET_PAIRS = (("api", "key"), ("private", "key"))
_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

_CACHE_KEYS_DROPPED_ON_SERVER_CHANGE = ("last_check", "auth_posture", "protocol_fallback")
_ABSENT = object()


class McpWriteError(Exception):
    """A refused MCP write: an HTTP-shaped ``status`` and ``detail``.

    ``detail`` is exactly the payload the route returns (a sentence, or a 422 list on
    ``loc``). It carries no HTTP type: ``api.py`` turns it into ``HTTPException``.
    """

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


class McpSourceNotFound(Exception):  # noqa: N818 - the route answers 404
    """No MCP source has this id."""

    def __init__(self, source_id: str) -> None:
        super().__init__(f"MCP source not found: {source_id}")
        self.source_id = source_id


class McpStaleError(Exception):
    """A touched field's stored value differs from the ``base`` the change was written
    against. ``fields`` is ``[{"field", "current", "proposed"}]``; for ``env`` and
    ``headers`` the two values are ``{row: value}`` maps of the rows that differ."""

    def __init__(self, fields: list[dict[str, Any]]) -> None:
        super().__init__("stale: " + ", ".join(str(f["field"]) for f in fields))
        self.fields = fields


@dataclass(frozen=True)
class McpWriteDeps:
    """What an MCP write needs. The two getters are **late-bound**: they are awaited at call
    time, inside the guarded rename-carry blocks, so a failure to acquire either is a warning
    and never a failure of the committed write."""

    repo: MCPSourceRepository
    agent_store: Callable[[], Awaitable[Any]]
    secret_repo: Callable[[], Awaitable[Any]]


# ── Secret-looking names ─────────────────────────────────────────────────


def _segments(name: str) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[^A-Za-z0-9]+", name):
        out.extend(s.lower() for s in _CAMEL_SPLIT.split(part) if s)
    return out


def looks_secret_key(name: str) -> bool:
    """Whether a header, env or flag name looks like it names a secret.

    The name is split on non-alphanumerics and camelCase boundaries and lowercased; it is
    secret-looking when any whole segment is in :data:`SECRET_KEY_SEGMENTS` or the adjacent
    pair ``api key`` or ``private key`` occurs. ``MAX_TOKENS`` and ``X-Request-Key-Id`` are
    accepted false positives (they cost one handoff).
    """
    segs = _segments(str(name))
    if any(s in SECRET_KEY_SEGMENTS for s in segs):
        return True
    return any(
        (a, b) == (segs[i], segs[i + 1]) for i in range(len(segs) - 1) for a, b in _SECRET_PAIRS
    )


def secret_args_flag(args: Any) -> str | None:
    """The first flag in ``args`` whose name is secret-looking and that carries a non-empty
    value: ``--name=value``, ``-name=value``, or a bare ``--name`` followed by a value item."""
    if not isinstance(args, list):
        return None
    items = [a for a in args if isinstance(a, str)]
    for i, item in enumerate(items):
        if not item.startswith("-") or item.lstrip("-") == "":
            continue
        body = item.lstrip("-")
        if "=" in body:
            name, _, value = body.partition("=")
            if value.strip() and looks_secret_key(name):
                return name
        elif item.startswith("--") and looks_secret_key(body):
            nxt = items[i + 1] if i + 1 < len(items) else ""
            if nxt.strip() and not nxt.startswith("-"):
                return body
    return None


# ── Validators (moved from api.py with their exact details) ──────────────


def validation_detail(e: ValidationError) -> list[dict]:
    """The 422 body for a pydantic ``ValidationError`` (no ``ctx``, no echoed input)."""
    return e.errors(include_context=False, include_input=False)


def checked_name(value: object) -> str:
    """The trimmed name, or a list-shaped 422 on ``loc ["name"]``."""
    try:
        return check_name(value)
    except NameRuleError as e:
        raise McpWriteError(422, name_rule_detail(e.message)) from None


def validate_mcp_source_config(source: MCPSource) -> None:
    """Transport-aware shape validation for ``MCPSource.config``.

    Stdio: ``config.command`` is required (non-empty string); ``config.args`` must be a
    list of strings if present; ``config.cwd`` a string; ``config.env`` a string-to-string
    dict; ``config.sandbox`` optional (``writable_paths`` list of strings, ``network_allowed``
    bool; path semantics are the runtime's). Streamable-HTTP: ``config.url`` is required;
    ``config.headers`` a string-to-string dict. A new transport must add a block here.
    """
    cfg = source.config

    if source.type == "stdio":
        command = cfg.get("command")
        if not isinstance(command, str) or not command.strip():
            raise McpWriteError(
                422, "MCP source of type 'stdio' requires config.command (non-empty string)."
            )
        args = cfg.get("args", [])
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise McpWriteError(422, "MCP source config.args must be a list of strings.")
        cwd = cfg.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise McpWriteError(422, "MCP source config.cwd must be a string if present.")
        env = cfg.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env.items()
        ):
            raise McpWriteError(422, "MCP source config.env must be a dict of string-to-string.")
        sandbox = cfg.get("sandbox")
        # ``is not None`` (not truthy): an empty sandbox block passes. Unknown keys pass
        # through; path shape is the runtime's ("trust the runtime").
        if sandbox is not None:
            if not isinstance(sandbox, dict):
                raise McpWriteError(422, "MCP source config.sandbox must be a dict if present.")
            if "writable_paths" in sandbox:
                writable_paths = sandbox["writable_paths"]
                if not isinstance(writable_paths, list) or not all(
                    isinstance(p, str) for p in writable_paths
                ):
                    raise McpWriteError(
                        422, "MCP source config.sandbox.writable_paths must be a list of strings."
                    )
            if "network_allowed" in sandbox:
                # ``bool`` subclasses ``int``: a JSON ``1`` gets a 422.
                if not isinstance(sandbox["network_allowed"], bool):
                    raise McpWriteError(
                        422, "MCP source config.sandbox.network_allowed must be a boolean."
                    )

    elif source.type == "streamable-http":
        url = cfg.get("url")
        if not isinstance(url, str) or not url.strip():
            raise McpWriteError(
                422,
                "MCP source of type 'streamable-http' requires config.url (non-empty string).",
            )
        headers = cfg.get("headers", {})
        if not isinstance(headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
        ):
            raise McpWriteError(
                422, "MCP source config.headers must be a dict of string-to-string."
            )

    else:
        raise McpWriteError(422, f"Unsupported MCP source type: {source.type}")


def reject_reserved_surface_name(source: MCPSource) -> None:
    """The name ``SURFACE_ROW_NAME`` is reserved for the platform-managed self-configuration
    surface row (it keys the surface's prefixed tool names); an ordinary source created or
    renamed to it is refused with 409."""
    if source.name == SURFACE_ROW_NAME and not is_surface_row(source):
        raise McpWriteError(
            409,
            f"{source.name!r} is reserved for the self-configuration surface; "
            "enable it from the owning agent's Self-configuration tab instead "
            "of creating or renaming an MCP source to this name.",
        )


def reject_surface_row(source: MCPSource) -> None:
    """A self-configuration surface row is not an ordinary MCP source: 409."""
    if is_surface_row(source):
        raise McpWriteError(
            409,
            f"MCP source {source.id!r} is a self-configuration surface row; "
            "manage it from the owning agent's Self-configuration tab.",
        )


def config_without_cache(source: MCPSource) -> dict[str, Any]:
    return {k: v for k, v in (source.config or {}).items() if k != "_cache"}


async def drop_source_agent_tool_cache(mcp_repo: MCPSourceRepository, source_id: str) -> None:
    """Delete every agent's per-agent tool cache row for a source whose connection basis
    changed. Never raises."""
    try:
        await AgentMcpToolCacheRepository(mcp_repo.conn).delete_for_source(source_id)
    except Exception:
        logger.warning("could not clear agent tool lists for %r", source_id, exc_info=False)


def _prune_cache_on_server_change(before: MCPSource, after: MCPSource) -> MCPSource:
    """The row may now point at a different server: drop the old server's last check, auth
    posture and protocol fallback from ``_cache`` (every other key stays); an emptied
    ``_cache`` is removed (absence is the "never checked" state)."""
    server_changed = after.type != before.type or (after.config or {}).get("url") != (
        before.config or {}
    ).get("url")
    if server_changed and isinstance((after.config or {}).get("_cache"), dict):
        kept = {
            k: v
            for k, v in after.config["_cache"].items()
            if k not in _CACHE_KEYS_DROPPED_ON_SERVER_CHANGE
        }
        new_config = {k: v for k, v in after.config.items() if k != "_cache"}
        if kept:
            new_config["_cache"] = kept
        return after.model_copy(update={"config": new_config})
    return after


# ── Post-commit side effects ─────────────────────────────────────────────


async def _after_write(deps: McpWriteDeps, before: MCPSource, after: MCPSource) -> None:
    source_id = after.id
    forget_era(source_id)
    # A change of type, config (the ``_cache`` is server-managed) or secrets reaches every
    # agent's next connection to this source.
    if (
        after.type != before.type
        or config_without_cache(after) != config_without_cache(before)
        or after.secrets != before.secrets
    ):
        from the_one.mcp._pool import _evict_all_for_source

        try:
            await _evict_all_for_source(source_id)
        except Exception:
            logger.warning("could not evict MCP connections for %r", source_id, exc_info=False)
        await drop_source_agent_tool_cache(deps.repo, source_id)
    # The rename carries into the attached agents' overrides and disabled tools. Acquiring
    # the store is guarded so a failure is a WARNING, never a failure after the commit.
    if before.name != after.name:
        from the_one.mcp.rename_references import carry_mcp_rename

        try:
            agent_store = await deps.agent_store()
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
                source_id, before.name, after.name, agent_store=agent_store, mcp_repo=deps.repo
            )
        # A secret's allowed tools follow the rename too (its own try: an agent-store
        # failure above never skips it).
        try:
            from the_one.mcp.rename_references import carry_mcp_rename_into_secrets

            await carry_mcp_rename_into_secrets(
                before.name,
                after.name,
                secret_repo=await deps.secret_repo(),
                mcp_repo=deps.repo,
            )
        except Exception:
            logger.warning(
                "MCP source %r rename: failed to carry the rename into secrets' allowed tools",
                source_id,
                exc_info=True,
            )


# ── Create and replace (the routes) ──────────────────────────────────────


async def create_mcp_source(
    deps: McpWriteDeps, data: dict[str, Any], *, on_commit: OnCommit | None = None
) -> MCPSource:
    """Create a source from a request body. ``on_commit`` runs inside the insert's
    transaction (a proposal's status mark rides there)."""
    data = dict(data)
    data["name"] = checked_name(data.get("name"))
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    try:
        source = MCPSource.model_validate(data)
    except ValidationError as e:
        raise McpWriteError(422, validation_detail(e)) from None
    reject_reserved_surface_name(source)
    validate_mcp_source_config(source)
    await deps.repo.create(source, on_commit=on_commit)
    return source


async def replace_mcp_source(deps: McpWriteDeps, source_id: str, data: dict[str, Any]) -> MCPSource:
    """The route's PUT: replace the row with the body, preserving what the operator may not
    write (masked secrets per key, OAuth-managed keys, the server-managed ``_cache``)."""
    repo = deps.repo
    data = dict(data)
    data["id"] = source_id
    try:
        existing = await repo.get(source_id)
    except KeyError:
        raise McpSourceNotFound(source_id) from None

    # A marked (self-configuration) row is not an ordinary MCP source: blocked outright.
    reject_surface_row(existing)

    # Per-key __MASKED__ handling inside the secrets dict: a sentinel value preserves the
    # stored value; a key absent from the incoming dict is dropped (replace semantic).
    incoming_secrets = data.get("secrets")
    if incoming_secrets is not None:
        if not isinstance(incoming_secrets, dict):
            raise McpWriteError(422, "secrets must be a dict.")
        resolved_secrets: dict[str, Any] = {}
        for key, value in incoming_secrets.items():
            if looks_masked(value):
                if key in existing.secrets:
                    resolved_secrets[key] = existing.secrets[key]
                # else: a mask for a key we don't have is dropped, as if omitted.
            else:
                resolved_secrets[key] = value
        # OAuth-managed keys: only the OAuth flow writes them. Applied AFTER the mask
        # resolution so a client-sent ``access_token: "__MASKED__"`` doesn't fall through.
        for key in OAUTH_MANAGED_SECRET_KEYS:
            if key in existing.secrets:
                resolved_secrets[key] = existing.secrets[key]
            elif key in resolved_secrets:
                del resolved_secrets[key]
        data["secrets"] = resolved_secrets

    # The tools cache is server-managed: an operator PUT can neither seed nor overwrite it.
    incoming_config = data.get("config")
    if isinstance(incoming_config, dict):
        incoming_config.pop("_cache", None)
        existing_cache = (existing.config or {}).get("_cache")
        if existing_cache is not None:
            incoming_config["_cache"] = existing_cache
        data["config"] = incoming_config

    # ``model_copy(update=...)`` does not re-run validators in Pydantic v2: round-trip
    # through ``model_validate`` so a malformed PUT cannot corrupt the stored row.
    try:
        merged = existing.model_dump()
        merged.update(data)
        if "name" in data:
            merged["name"] = checked_name(merged["name"])
        updated = MCPSource.model_validate(merged)
    except ValidationError as e:
        raise McpWriteError(422, validation_detail(e)) from None
    reject_reserved_surface_name(updated)
    validate_mcp_source_config(updated)
    updated = _prune_cache_on_server_change(existing, updated)
    await repo.update(updated)
    await _after_write(deps, existing, updated)
    return updated


# ── Change (a proposal) ──────────────────────────────────────────────────


def _fold(key: str, field: str) -> str:
    """The comparison form of a row name: headers are case-insensitive, env is exact."""
    return key.lower() if field == "headers" else key


def _row_lookup(rows: Any, name: str, field: str) -> Any:
    if not isinstance(rows, dict):
        return _ABSENT
    folded = _fold(name, field)
    for k, v in rows.items():
        if _fold(str(k), field) == folded:
            return v
    return _ABSENT


def _current_value(source: MCPSource, key: str) -> Any:
    if key == "name":
        return source.name
    return (source.config or {}).get(key, _ABSENT)


def _stale_fields(
    current: MCPSource, changes: dict[str, Any], base: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, proposed in changes.items():
        if key in _ROW_FIELDS:
            cur_rows = (current.config or {}).get(key)
            base_rows = base.get(key)
            differing_cur: dict[str, Any] = {}
            differing_prop: dict[str, Any] = {}
            for row_name in proposed:
                cur = _row_lookup(cur_rows, row_name, key)
                was = _row_lookup(base_rows, row_name, key)
                if cur != was:
                    differing_cur[row_name] = None if cur is _ABSENT else cur
                    differing_prop[row_name] = proposed[row_name]
            if differing_prop:
                out.append({"field": key, "current": differing_cur, "proposed": differing_prop})
            continue
        cur = _current_value(current, key)
        was = base.get(key, _ABSENT)
        if cur != was:
            out.append(
                {"field": key, "current": None if cur is _ABSENT else cur, "proposed": proposed}
            )
    return out


#: The public name of the stale check, for the fill view (leg 4b).
stale_fields = _stale_fields


def _refuse(loc: list[Any], msg: str) -> McpWriteError:
    return McpWriteError(422, [{"type": "value_error", "loc": loc, "msg": msg}])


HANDOFF = "Enter it in the MCP server editor and turn on Sensitive."


def row_refusal(field: str, row_name: str, value: Any, secrets: dict[str, Any]) -> str | None:
    """The sentence refusing a proposed ``env`` or ``headers`` row, else ``None``.

    A row is refused when its name is OAuth-managed, collides with a stored Sensitive key
    (headers compare case-insensitively, env exactly), or is secret-looking with a non-empty
    value. A proposal never writes ``secrets``; the operator enters those in the editor.
    """
    folded = _fold(row_name, field)
    stored = {_fold(str(k), field) for k in secrets}
    managed = {_fold(k, field) for k in OAUTH_MANAGED_SECRET_KEYS}
    if folded in managed:
        return f"{row_name!r} is managed by sign-in and can't be set here."
    if folded in stored:
        return f"{row_name!r} is stored as a Sensitive value; change it in the MCP server editor."
    if isinstance(value, str) and value.strip() and looks_secret_key(row_name):
        return f"{row_name!r} looks like a secret. {HANDOFF}"
    return None


def _check_row(field: str, row_name: str, value: str, secrets: dict[str, Any]) -> None:
    message = row_refusal(field, row_name, value, secrets)
    if message is not None:
        raise _refuse([field, row_name], message)


def _apply_change(
    current: MCPSource, changes: dict[str, Any], base: dict[str, Any] | None, override: bool
) -> MCPSource:
    """The mutator: runs on the row re-read inside the write transaction."""
    reject_surface_row(current)  # on the fresh row, as well as at resolve and normalize
    for key in changes:
        if key not in CHANGE_FIELDS:
            raise _refuse([key], f"{key!r} can't be changed here.")
    wrong = _STDIO_FIELDS if current.type == "streamable-http" else _HTTP_FIELDS
    for key in changes:
        if key in wrong:
            kind = "remote (HTTP)" if current.type == "streamable-http" else "local (stdio)"
            raise _refuse([key], f"{key!r} doesn't apply to a {kind} server.")
    if base is not None and not override:
        stale = _stale_fields(current, changes, base)
        if stale:
            raise McpStaleError(stale)

    cfg = copy.deepcopy(current.config or {})
    name = current.name
    for key, value in changes.items():
        if key == "name":
            name = checked_name(value)
        elif key in _ROW_FIELDS:
            if not isinstance(value, dict):
                raise _refuse([key], f"{key} must be an object of name and value.")
            rows = cfg.get(key)
            rows = dict(rows) if isinstance(rows, dict) else {}
            for row_name, row_value in value.items():
                if not isinstance(row_name, str) or not isinstance(row_value, str):
                    raise _refuse([key], f"{key} must be an object of text values.")
                _check_row(key, row_name, row_value, current.secrets or {})
                folded = _fold(row_name, key)
                for existing_name in [k for k in rows if _fold(str(k), key) == folded]:
                    del rows[existing_name]
                rows[row_name] = row_value
            cfg[key] = rows
        else:
            if key == "args":
                flag = secret_args_flag(value)
                if flag is not None:
                    raise _refuse(["args"], f"The flag {flag!r} looks like a secret. {HANDOFF}")
            cfg[key] = value
    try:
        candidate = MCPSource.model_validate({**current.model_dump(), "name": name, "config": cfg})
    except ValidationError as e:
        raise McpWriteError(422, validation_detail(e)) from None
    reject_reserved_surface_name(candidate)
    validate_mcp_source_config(candidate)
    return _prune_cache_on_server_change(current, candidate)


async def change_mcp_source(
    deps: McpWriteDeps,
    source_id: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> MCPSource:
    """Apply a proposal's named fields to the row, inside one write transaction.

    The row is re-read under the write lock and the change merged onto it (rows per row;
    ``secrets``, ``_cache``, ``cwd`` and ``sandbox`` are never touched), so a ``merge_cache``
    or an OAuth token written a moment ago is kept. ``base`` (the values the proposal was
    written against) is compared on the fresh row unless ``override``: a mismatch raises
    :class:`McpStaleError` and nothing is written. Side effects run after the commit, and
    never if the write (or ``on_commit``) raised. Returns the updated row.
    """

    def mutate(current: MCPSource) -> MCPSource:
        return _apply_change(current, changes, base, override)

    try:
        before, after = await deps.repo.update_in_txn(source_id, mutate, on_commit=on_commit)
    except KeyError:
        raise McpSourceNotFound(source_id) from None
    await _after_write(deps, before, after)
    return after

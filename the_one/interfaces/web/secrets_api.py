"""Secret routes (sortie 10), in their own router like ``routines_api.py``.

The router has no prefix; ``api.py`` attaches it to ``api.router`` (prefix ``/api``) at the
bottom of that module. Handlers reach ``api.py`` helpers through ``_api`` at call time, so
tests that patch ``the_one.interfaces.web.api.get_connection`` and friends still apply.

**No value ever leaves this module.** Every stored value is returned as the constant
``__MASKED__``, with no tail. The routes take no pydantic body parameter: the app has no
``RequestValidationError`` handler, so FastAPI's default 422 would echo the submitted
``input`` (values included). Bodies are read with ``_read_json`` and validated by hand;
every 422 detail is a ``{type, loc, msg}`` list whose ``msg`` is a fixed sentence.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from the_one.db.repositories import (
    SECRET_MASK,
    AgentMcpToolCacheRepository,
    MCPSourceRepository,
    Secret,
    SecretInvalid,
    SecretNameConflict,
)
from the_one.naming import NAME_CONFLICT_SECRET
from the_one.secret_store.refused import is_refused_tool
from the_one.self_configuration.constants import is_surface_row

logger = logging.getLogger(__name__)


class _ApiModule:
    """Call-time lookup of ``api.py`` names (no import at load: ``api`` imports this module)."""

    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()

router = APIRouter()

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TOOL_NAME_MAX = 128


def _err(loc: list[Any], msg: str) -> dict[str, Any]:
    return {"type": "value_error", "loc": loc, "msg": msg}


def _response(secret: Secret) -> dict[str, Any]:
    return {
        "id": secret.id,
        "name": secret.name,
        "description": secret.description,
        "allowed_tools": list(secret.allowed_tools),
        "values": [{"id": v.id, "key": v.key, "value": SECRET_MASK} for v in secret.values],
        "created_at": secret.created_at,
        "updated_at": secret.updated_at,
    }


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Secret not found.")


def _conflict() -> HTTPException:
    return HTTPException(status_code=409, detail=_api._name_conflict_detail(NAME_CONFLICT_SECRET))


# ── Validation (shared by POST and PUT) ──────────────────────────────────


def _check_allowed_tools(raw: Any, errors: list[dict[str, Any]]) -> list[str] | None:
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


def _check_values(
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


def _parse(data: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    """The validated, trimmed fields present in ``data`` (all of them when creating);
    raises the list-shaped 422 otherwise. Never echoes an input."""
    out: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    if creating or "name" in data:
        out["name"] = _api._checked_name(data.get("name"))
    if "description" in data:
        if isinstance(data["description"], str):
            out["description"] = data["description"]
        else:
            errors.append(_err(["description"], "A description must be text."))
    elif creating:
        out["description"] = ""
    if creating or "allowed_tools" in data:
        tools = _check_allowed_tools(data.get("allowed_tools"), errors)
        if tools is not None:
            out["allowed_tools"] = tools
    if creating or "values" in data:
        pairs = _check_values(data.get("values"), errors, creating=creating)
        if pairs is not None:
            out["values"] = pairs
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return out


# ── Routes ───────────────────────────────────────────────────────────────


@router.get("/secrets")
async def list_secrets() -> list[dict[str, Any]]:
    repo = await _api._secret_repo()
    return [_response(s) for s in await repo.list()]


@router.get("/secrets/{secret_id}")
async def get_secret(secret_id: str) -> dict[str, Any]:
    secret = await (await _api._secret_repo()).get(secret_id)
    if secret is None:
        raise _not_found()
    return _response(secret)


@router.post("/secrets", status_code=201)
async def create_secret(request: Request) -> dict[str, Any]:
    data = await _api._read_json(request)
    fields = _parse(data, creating=True)
    repo = await _api._secret_repo()
    try:
        secret = await repo.create(
            fields["name"], fields["description"], fields["allowed_tools"], fields["values"]
        )
    except SecretNameConflict:
        raise _conflict() from None
    except SecretInvalid as e:
        raise HTTPException(status_code=422, detail=e.details) from None
    logger.info("secret created: id=%s values=%d", secret.id, len(secret.values))
    return _response(secret)


@router.put("/secrets/{secret_id}")
async def update_secret(secret_id: str, request: Request) -> dict[str, Any]:
    data = await _api._read_json(request)
    repo = await _api._secret_repo()
    if await repo.get(secret_id) is None:
        raise _not_found()
    fields = _parse(data, creating=False)
    try:
        secret = await repo.update(secret_id, **fields)
    except KeyError:
        raise _not_found() from None
    except SecretNameConflict:
        raise _conflict() from None
    except SecretInvalid as e:
        raise HTTPException(status_code=422, detail=e.details) from None
    logger.info("secret updated: id=%s values=%d", secret.id, len(secret.values))
    return _response(secret)


@router.delete("/secrets/{secret_id}", status_code=204)
async def delete_secret(secret_id: str) -> Response:
    repo = await _api._secret_repo()
    try:
        scrubbed = await repo.delete(secret_id)
    except KeyError:
        raise _not_found() from None
    logger.info("secret deleted: id=%s grants removed from agents=%s", secret_id, scrubbed)
    return Response(status_code=204)


# ── Tool names (DD3) ─────────────────────────────────────────────────────


@router.get("/tool-names")
async def list_tool_names() -> list[dict[str, Any]]:
    """Every tool name a secret could be allowed on: built-ins and the MCP tools the app
    has seen (shared cache and every per-agent cache), under the names an agent sees.
    Refused tools, the self-configuration surface and agent-derived tools are left out."""
    from the_one.mcp._tool import _normalize_source_name
    from the_one.tools.builtins import BuiltinToolProvider

    found: dict[str, dict[str, Any]] = {}

    def add(name: str, source: str, source_name: str | None, description: str) -> None:
        if name in found or is_refused_tool(name):
            return
        found[name] = {
            "name": name,
            "source": source,
            "source_name": source_name,
            "description": description,
        }

    for tool in BuiltinToolProvider().get_tools():
        add(tool.name, "builtin", None, tool.description)

    conn = await _api.get_connection()
    repo = MCPSourceRepository(conn, _api.get_encryptor(_api.settings.data_dir))
    sources = {s.id: s for s in await repo.list() if not is_surface_row(s)}

    def add_mcp(source: Any, tools: Any) -> None:
        if not isinstance(tools, list):
            return
        prefix = f"mcp__{_normalize_source_name(source.name)}__"
        for t in tools:
            if isinstance(t, dict) and isinstance(t.get("name"), str):
                add(
                    prefix + t["name"],
                    "mcp",
                    source.name,
                    str(t.get("description") or ""),
                )

    for source in sources.values():
        cache = (source.config or {}).get("_cache")
        if isinstance(cache, dict):
            add_mcp(source, cache.get("tools"))
    for source_id, tools in await AgentMcpToolCacheRepository(conn).list_all():
        source = sources.get(source_id)
        if source is not None:
            add_mcp(source, tools)
    return sorted(found.values(), key=lambda t: t["name"])

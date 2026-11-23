"""Secret routes (sortie 10), in their own router like ``routines_api.py``.

The router has no prefix; ``api.py`` attaches it to ``api.router`` (prefix ``/api``) at the
bottom of that module. Handlers reach ``api.py`` helpers through ``_api`` at call time, so
tests that patch ``the_one.interfaces.web.api.get_connection`` and friends still apply.

The validation and the writes live in ``the_one/secret_store/service.py`` (Mission 36 F5 L3a),
shared with GleepGlorp's approve path; these handlers only read the body, call the service and
map its errors to ``HTTPException``.

**No value ever leaves this module.** Every stored value is returned as the constant
``__MASKED__``, with no tail. The routes take no pydantic body parameter: the app has no
``RequestValidationError`` handler, so FastAPI's default 422 would echo the submitted
``input`` (values included). Bodies are read with ``_read_json`` and validated by hand;
every 422 detail is a ``{type, loc, msg}`` list whose ``msg`` is a fixed sentence.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from the_one.db.repositories import (
    SECRET_MASK,
    AgentMcpToolCacheRepository,
    MCPSourceRepository,
    Secret,
)
from the_one.secret_store import service as secret_service
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


@contextlib.contextmanager
def _write_errors() -> Iterator[None]:
    """Turn the secret write service's refusals into the ``HTTPException`` the routes always
    returned."""
    try:
        yield
    except secret_service.SecretWriteError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None
    except secret_service.SecretNotFound:
        raise _not_found() from None


async def _write_deps() -> secret_service.SecretWriteDeps:
    return secret_service.SecretWriteDeps(repo=await _api._secret_repo())


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
    with _write_errors():
        secret = await secret_service.create_secret(await _write_deps(), data)
    logger.info("secret created: id=%s values=%d", secret.id, len(secret.values))
    return _response(secret)


@router.put("/secrets/{secret_id}")
async def update_secret(secret_id: str, request: Request) -> dict[str, Any]:
    data = await _api._read_json(request)
    with _write_errors():
        secret = await secret_service.replace_secret(await _write_deps(), secret_id, data)
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

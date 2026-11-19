"""Startup repair of stored names that break the naming rule (sortie 06, DD11-DD12).

Runs in the web app's lifespan after the key reconcile and the JSON import and
before ``manage.reconcile_on_startup``. It is Python rather than a ``schema.py``
migration because an MCP rename must rewrite agents' encrypted ``mcp_overrides``,
which needs the encryptor, and because every rename goes through the same carry
paths the operator's own renames use (``SQLiteAgentStore.rename`` +
``cascade_rename``, ``carry_mcp_rename``, ``carry_kb_rename``).

Names are scanned with a raw ``SELECT`` per table so one undecryptable row cannot
fail the scan. Self-configuration surface rows are skipped (``reconcile_on_startup``
owns them) but still count as taken. Each row is repaired in its own try/except and
the pass never raises; a second pass finds nothing to do. It must not be called from
inside another transaction (``write_transaction`` rejects same-task re-entry).
"""

from __future__ import annotations

import json
import logging

from the_one.db._write_lock import write_transaction
from the_one.db.models import now_iso
from the_one.knowledge.kb_rename import carry_kb_rename
from the_one.mcp.rename_references import carry_mcp_rename
from the_one.naming import (
    RESERVED_AGENT_NAMES,
    NameRuleError,
    check_name,
    is_reserved_agent_name,
    repair_name,
)
from the_one.self_configuration.constants import OWNER_MARKER_KEY
from the_one.self_configuration.manage import cascade_rename

logger = logging.getLogger(__name__)

_KIND_WORDS = {
    "agent": "agent",
    "provider": "provider",
    "knowledge_base": "knowledge base",
    "mcp_source": "MCP server",
}


def _is_bad(name: str) -> bool:
    try:
        check_name(name)
    except NameRuleError:
        return True
    return False


def _log_rename(kind: str, old: str, new: str) -> None:
    logger.warning(
        "renamed %s %r to %r: its name broke the naming rule", _KIND_WORDS[kind], old, new
    )


async def _rows(conn, sql: str) -> list:
    async with conn.execute(sql) as cur:
        return list(await cur.fetchall())


async def _repair_agents(conn, agent_store, mcp_repo) -> list[tuple[str, str, str]]:
    done: list[tuple[str, str, str]] = []
    names = [r["name"] for r in await _rows(conn, "SELECT name FROM agents")]
    taken = set(names) | set(RESERVED_AGENT_NAMES)
    for old in names:
        if not (_is_bad(old) or is_reserved_agent_name(old)):
            continue
        try:
            new = repair_name(old, kind="agent", taken=taken)
            await agent_store.rename(old, new)
        except Exception:
            logger.warning("could not repair agent name %r", old, exc_info=True)
            continue
        taken.add(new)
        done.append(("agent", old, new))
        _log_rename("agent", old, new)
        try:
            await cascade_rename(old, new, mcp_repo=mcp_repo)
        except Exception:
            logger.warning(
                "agent %r was renamed to %r, but its self-configuration surface marker may "
                "still name the old agent",
                old,
                new,
                exc_info=True,
            )
    return done


async def _repair_mcp_sources(conn, agent_store, mcp_repo) -> list[tuple[str, str, str]]:
    done: list[tuple[str, str, str]] = []
    rows = await _rows(conn, "SELECT id, name, config FROM mcp_sources")
    taken = {r["name"] for r in rows}
    for row in rows:
        old = row["name"]
        if not _is_bad(old):
            continue
        try:
            config = json.loads(row["config"] or "{}")
            marker = config.get(OWNER_MARKER_KEY) if isinstance(config, dict) else None
            if isinstance(marker, dict) and marker.get("agent"):
                continue
            new = repair_name(old, kind="mcp_source", taken=taken)
            source = await mcp_repo.get(row["id"])
            await mcp_repo.update(source.model_copy(update={"name": new}))
        except Exception:
            logger.warning("could not repair MCP server name %r", old, exc_info=True)
            continue
        taken.add(new)
        done.append(("mcp_source", old, new))
        _log_rename("mcp_source", old, new)
        try:
            await carry_mcp_rename(row["id"], old, new, agent_store=agent_store, mcp_repo=mcp_repo)
        except Exception:
            logger.warning("could not carry MCP server rename %r -> %r", old, new, exc_info=True)
        try:
            from the_one.db.repositories import SecretRepository
            from the_one.mcp.rename_references import carry_mcp_rename_into_secrets

            await carry_mcp_rename_into_secrets(
                old, new, secret_repo=SecretRepository(conn), mcp_repo=mcp_repo
            )
        except Exception:
            logger.warning(
                "could not carry MCP server rename %r -> %r into secrets", old, new, exc_info=True
            )
    return done


async def _repair_knowledge_bases(conn, agent_store, kb_repo) -> list[tuple[str, str, str]]:
    done: list[tuple[str, str, str]] = []
    rows = await _rows(conn, "SELECT id, name FROM knowledge_bases")
    taken = {r["name"] for r in rows}

    async def _store():
        return agent_store

    for row in rows:
        old = row["name"]
        if not _is_bad(old):
            continue
        try:
            new = repair_name(old, kind="knowledge_base", taken=taken)
            existing = await kb_repo.get(row["id"])
            updated = existing.model_copy(update={"name": new})
            await kb_repo.update(updated)
        except Exception:
            logger.warning("could not repair knowledge base name %r", old, exc_info=True)
            continue
        taken.add(new)
        done.append(("knowledge_base", old, new))
        _log_rename("knowledge_base", old, new)
        try:
            await carry_kb_rename(existing, updated, get_agent_store=_store)
        except Exception:
            logger.warning(
                "could not carry knowledge base rename %r -> %r", old, new, exc_info=True
            )
    return done


async def _repair_providers(conn) -> list[tuple[str, str, str]]:
    done: list[tuple[str, str, str]] = []
    rows = await _rows(conn, "SELECT id, name FROM llm_providers")
    taken = {r["name"] for r in rows}
    for row in rows:
        old = row["name"]
        if not _is_bad(old):
            continue
        try:
            new = repair_name(old, kind="provider", taken=taken)
            # Raw UPDATE: agents reference providers by id, and a get + update would
            # decrypt and re-encrypt the secrets, failing on a bad ciphertext.
            async with write_transaction(conn):
                await conn.execute(
                    "UPDATE llm_providers SET name = ?, updated_at = ? WHERE id = ?",
                    (new, now_iso(), row["id"]),
                )
        except Exception:
            logger.warning("could not repair provider name %r", old, exc_info=True)
            continue
        taken.add(new)
        done.append(("provider", old, new))
        _log_rename("provider", old, new)
    return done


async def repair_unsafe_names(
    conn, *, agent_store, mcp_repo, kb_repo
) -> list[tuple[str, str, str]]:
    """Rename every stored name that breaks the rule; return ``(kind, old, new)`` per rename."""
    done: list[tuple[str, str, str]] = []
    for step in (
        lambda: _repair_agents(conn, agent_store, mcp_repo),
        lambda: _repair_mcp_sources(conn, agent_store, mcp_repo),
        lambda: _repair_knowledge_bases(conn, agent_store, kb_repo),
        lambda: _repair_providers(conn),
    ):
        try:
            done.extend(await step())
        except Exception:
            logger.warning("name repair step failed", exc_info=True)
    return done

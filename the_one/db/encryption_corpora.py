"""The nine encrypted (table, column) pairs, gathered decrypted.

(M31 F4 L08b; secret values: sortie 10.)

One gather shared by the key-rotation route (``POST /api/encryption/rotate``,
which then re-encrypts and writes every corpus under a new key) and the
read-only status route (``GET /api/encryption/status``, which only counts the
items that hold a secret), so the two cannot drift apart on which columns count.

The corpora are the ones the rotate route's docstring lists: provider
``api_key``, provider ``secrets``, MCP source ``secrets``, connector
``secrets``, agent ``tool_overrides`` / ``mcp_overrides``, tool config
``secrets``, external-credential ``secret`` and Library secret values
(``secret_values.value``, the ninth (table, column) pair; an agent's two override
columns share one gathered list, so ``Corpora`` holds eight lists).

``strict=True`` is the rotation's decrypt policy: the provider ``api_key`` and
the external-credential ``secret`` decrypt strictly (an ``InvalidToken`` aborts
before any write), the JSON-decode errors surface, and a missing table is a
real error. ``strict=False`` is the status route's: every ``InvalidToken`` and
JSON error is residue and counts as empty, and a table that does not exist yet
(a pre-migration database) is skipped, as ``key_reconcile.sample_ciphertexts``
does. Nothing decrypted leaves the process either way.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import aiosqlite
from cryptography.fernet import InvalidToken

from the_one.db.repositories import _decrypt_overrides_column, _decrypt_secrets_blob
from the_one.encryption import Encryptor

_T = TypeVar("_T")


@dataclass
class Corpora:
    """Every encrypted corpus, decrypted, keyed by its row id."""

    api_keys: list[tuple[str, str]] = field(default_factory=list)
    provider_secrets: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    mcps: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    connectors: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    agents: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = field(
        default_factory=list
    )
    tool_configs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    ext_credentials: list[tuple[str, str]] = field(default_factory=list)
    # Sortie 10: (secret_values.id, plaintext value). Never logged or returned.
    secret_values: list[tuple[str, str]] = field(default_factory=list)
    # secret_values.id -> secrets.id, for the status count only (not a corpus column).
    secret_value_owners: dict[str, str] = field(default_factory=dict)


async def _secret_value_owners(conn: aiosqlite.Connection) -> dict[str, str]:
    """``{secret_values.id: secret_id}``; empty before the v51 table exists."""
    try:
        async with conn.execute("SELECT id, secret_id FROM secret_values") as cur:
            return {r[0]: r[1] for r in await cur.fetchall()}
    except aiosqlite.OperationalError:
        return {}


async def _rows(
    conn: aiosqlite.Connection, sql: str, build: Callable[[Any], _T], *, strict: bool
) -> list[_T]:
    try:
        async with conn.execute(sql) as cur:
            fetched = await cur.fetchall()
    except aiosqlite.OperationalError:
        if strict:
            raise
        return []
    out: list[_T] = []
    for row in fetched:
        try:
            out.append(build(row))
        except (InvalidToken, ValueError):
            if strict:
                raise
    return out


async def gather_corpora(
    conn: aiosqlite.Connection, encryptor: Encryptor, *, strict: bool
) -> Corpora:
    """Decrypt the nine encrypted columns. See the module docstring for ``strict``."""
    c = Corpora()
    c.api_keys = await _rows(
        conn,
        "SELECT id, api_key FROM llm_providers WHERE api_key IS NOT NULL AND api_key != ''",
        lambda r: (r["id"], encryptor.decrypt(r["api_key"])),
        strict=strict,
    )
    # Tolerant of migration residue in both modes: a plaintext '{}' column
    # default is not ciphertext and reads as empty (JSON errors still surface
    # in strict mode, as in the rotation's original inline code).
    c.provider_secrets = await _rows(
        conn,
        "SELECT id, secrets FROM llm_providers",
        lambda r: (r["id"], _decrypt_secrets_blob(encryptor, r["secrets"])),
        strict=strict,
    )
    c.mcps = await _rows(
        conn,
        "SELECT id, secrets FROM mcp_sources",
        lambda r: (r["id"], _decrypt_secrets_blob(encryptor, r["secrets"])),
        strict=strict,
    )
    c.connectors = await _rows(
        conn,
        "SELECT id, secrets FROM connectors",
        lambda r: (r["id"], _decrypt_secrets_blob(encryptor, r["secrets"])),
        strict=strict,
    )
    # Agent overrides: legacy plaintext here is real operator data, so the
    # store's own helper is used; NULL stays None.
    c.agents = await _rows(
        conn,
        "SELECT name, tool_overrides, mcp_overrides FROM agents",
        lambda r: (
            r["name"],
            _decrypt_overrides_column(encryptor, r["tool_overrides"]),
            _decrypt_overrides_column(encryptor, r["mcp_overrides"]),
        ),
        strict=strict,
    )
    c.tool_configs = await _rows(
        conn,
        "SELECT name, secrets FROM tool_configs",
        lambda r: (r["name"], _decrypt_secrets_blob(encryptor, r["secrets"])),
        strict=strict,
    )
    c.ext_credentials = await _rows(
        conn,
        "SELECT identifier, secret FROM agent_external_credentials",
        lambda r: (r["identifier"], encryptor.decrypt(r["secret"])),
        strict=strict,
    )
    c.secret_values = await _rows(
        conn,
        "SELECT id, value FROM secret_values",
        lambda r: (r["id"], encryptor.decrypt(r["value"])),
        strict=strict,
    )
    c.secret_value_owners = await _secret_value_owners(conn)
    return c


def _has_value(blob: dict[str, Any] | None) -> bool:
    """A secrets / overrides map holding at least one non-empty value."""
    if not blob:
        return False
    return any(v not in (None, "", {}, []) for v in blob.values())


def count_items_with_secrets(c: Corpora) -> int:
    """Items holding at least one non-empty secret (the status route's count).

    One per item, not per column: a provider counts once whether it has an
    ``api_key``, a ``secrets`` blob or both; an agent counts once for either
    override map.
    """
    providers = {pid for pid, key in c.api_keys if key}
    providers |= {pid for pid, blob in c.provider_secrets if _has_value(blob)}
    mcps = {sid for sid, blob in c.mcps if _has_value(blob)}
    connectors = {cid for cid, blob in c.connectors if _has_value(blob)}
    agents = {name for name, tool, mcp in c.agents if _has_value(tool) or _has_value(mcp)}
    tools = {name for name, blob in c.tool_configs if _has_value(blob)}
    ext = {ident for ident, secret in c.ext_credentials if secret}
    # A secret counts once however many values it holds: map each non-empty value row
    # to its owning secret.
    secrets = {c.secret_value_owners.get(vid, vid) for vid, value in c.secret_values if value}
    return (
        len(providers)
        + len(mcps)
        + len(connectors)
        + len(agents)
        + len(tools)
        + len(ext)
        + len(secrets)
    )


__all__ = ["Corpora", "count_items_with_secrets", "gather_corpora"]

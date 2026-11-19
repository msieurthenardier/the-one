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


# Keys of an OAuth blob that are not secret (a token's type and scopes, the public client id).
_PUBLIC_BLOB_KEYS = frozenset({"token_type", "scope", "scopes"})


def _blob_strings(value: Any, *, parent: str | None = None) -> list[str]:
    """Every string in a secrets blob, recursively, except the public OAuth keys."""
    if isinstance(value, str):
        return [value]
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _PUBLIC_BLOB_KEYS:
                continue
            if k == "client_id" and parent == "dcr_credentials":
                continue
            out += _blob_strings(v, parent=k if isinstance(k, str) else None)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out += _blob_strings(v, parent=parent)
    return out


def _override_strings(mcp: dict[str, Any] | None, tool: dict[str, Any] | None) -> list[str]:
    """The secret strings of one agent's override maps (never tool lists or other keys)."""
    out: list[str] = []
    for entry in (mcp or {}).values():
        if not isinstance(entry, dict):
            continue
        plain = entry.get("plain_names")
        plain_names = {n for n in plain if isinstance(n, str)} if isinstance(plain, list) else set()
        folded = {n.strip().lower() for n in plain_names}
        headers = entry.get("headers")
        for k, v in (headers if isinstance(headers, dict) else {}).items():
            low = k.strip().lower() if isinstance(k, str) else ""
            if isinstance(v, str) and (low == "authorization" or low not in folded):
                out.append(v)
        env = entry.get("env")
        for k, v in (env if isinstance(env, dict) else {}).items():
            if isinstance(v, str) and k not in plain_names:
                out.append(v)
        if isinstance(entry.get("bearer_token"), str):
            out.append(entry["bearer_token"])
    if tool:
        from the_one.gleepglorp.view_core import _secret_field_names
        from the_one.tools.builtins import _TOOL_CLASSES

        for tool_name, fields in tool.items():
            cls = _TOOL_CLASSES.get(tool_name) if isinstance(tool_name, str) else None
            config_cls = getattr(cls, "Config", None)
            if config_cls is None or not isinstance(fields, dict):
                continue
            for field_name in _secret_field_names(config_cls):
                value = fields.get(field_name)
                if isinstance(value, str):
                    out.append(value)
    return out


def secret_leaves(c: Corpora, *, min_len: int = 8) -> set[str]:
    """The stored secret strings of at least ``min_len`` characters, trimmed (M36 F2 L3).

    Chosen per column so a public value (an OAuth ``token_type``, a header the operator
    marked plain, a tool list) is never a "secret" a proposal can trip on. A shorter value
    is not searched, so it cannot cause false positives. Nothing here is logged or returned
    beyond the caller.
    """
    found: list[str] = [key for _id, key in c.api_keys]
    for _id, blob in (*c.provider_secrets, *c.mcps, *c.tool_configs, *c.connectors):
        found += _blob_strings(blob)
    found += [value for _id, value in c.secret_values]
    found += [secret for _ident, secret in c.ext_credentials]
    for _name, tool, mcp in c.agents:
        found += _override_strings(mcp, tool)
    trimmed = (s.strip() for s in found if isinstance(s, str))
    return {s for s in trimmed if len(s) >= min_len}


__all__ = ["Corpora", "count_items_with_secrets", "gather_corpora", "secret_leaves"]

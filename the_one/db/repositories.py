"""Async CRUD repositories for all database entities."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Literal

import aiosqlite
from cryptography.fernet import InvalidToken

# AgentConfig is import-cycle-only here (squawk 0003): repositories -> agent.config
# -> agent (package __init__) -> agent.core -> mcp.errors -> mcp (package __init__)
# -> mcp._pool -> repositories, re-entering this module before MCPSourceRepository
# is defined. AgentConfig is used only in annotations (deferred by
# `from __future__ import annotations` above) plus one runtime construction in
# `_row_to_config`, which imports it locally instead.
if TYPE_CHECKING:
    from the_one.agent.config import AgentConfig
from the_one.db.models import (
    AgentRevision,
    ChatSession,
    Connector,
    KBItem,
    KnowledgeBase,
    LLMProviderConfig,
    MCPSource,
    PendingApproval,
    ToolConfig,
    now_iso,
)
from the_one.encryption import Encryptor

# ── Shared Fernet envelope for per-row secrets dicts ─────────────────────
#
# Used by both :class:`MCPSourceRepository` and
# :class:`ConnectorRepository`. The per-repository methods
# ``_secrets_to_ciphertext`` / ``_ciphertext_to_secrets`` retained as
# one-line delegators to keep the method-on-repository surface stable for
# any test that mocks them; behaviour is identical to the pre-lift bodies.


def _encrypt_secrets_blob(encryptor: Encryptor, secrets: dict[str, Any]) -> str:
    """Serialize ``secrets`` and Fernet-encrypt the resulting JSON string."""
    return encryptor.encrypt(json.dumps(secrets))


def _decrypt_secrets_blob(encryptor: Encryptor, ciphertext: str | None) -> dict[str, Any]:
    """Decrypt a secrets-column ciphertext to its dict form.

    Empty/None ``ciphertext`` returns ``{}``.

    ``InvalidToken`` is the migration-residue path — pre-MCP-L2 rows or
    rows migrated by v10 / v13 carry the column default ``'{}'``
    (plaintext) which Fernet.decrypt rejects. Silently fall back to
    ``{}`` for that case; the next ``update()`` rewrites the column with
    proper ciphertext.

    ``JSONDecodeError`` is NOT swallowed — it means decrypt() succeeded
    but the cleartext bytes were not valid JSON. That indicates real
    data corruption (e.g., manual DB tampering, key reuse mishap) and
    must surface, not be silently masked.
    """
    if not ciphertext:
        return {}
    try:
        plaintext = encryptor.decrypt(ciphertext)
    except InvalidToken:
        # Migration-residue: column default '{}' is plaintext, not
        # ciphertext. Treat as empty secrets. Will be rewritten with
        # real ciphertext on the next update().
        return {}
    return json.loads(plaintext)  # JSONDecodeError propagates


def _encrypt_overrides_column(encryptor: Encryptor, value: dict[str, Any] | None) -> str | None:
    """Serialize + Fernet-encrypt an ``agents.tool_overrides`` /
    ``agents.mcp_overrides`` column value.

    ``None`` passes through as ``None`` (stored as SQL NULL) — the
    None/``{}`` distinction the round-trip tests pin is preserved: an
    explicit ``{}`` IS encrypted (not treated as "empty, store NULL").
    """
    if value is None:
        return None
    return encryptor.encrypt(json.dumps(value))


def _decrypt_overrides_column(encryptor: Encryptor, raw: str | None) -> dict[str, Any] | None:
    """Decode an ``agents.tool_overrides`` / ``agents.mcp_overrides``
    column value, tolerating legacy plaintext.

    Deliberately NOT :func:`_decrypt_secrets_blob`: that helper treats
    ``InvalidToken`` as "empty secrets" (`{}`) — correct for a column
    whose default is the plaintext string ``'{}'``, but destructive here.
    Pre-leg rows carry REAL operator data in plaintext JSON (e.g.
    ``{"shell": {"timeout": 30}}``) with no encrypted default to fall
    back to; returning ``{}`` on ``InvalidToken`` would silently discard
    it. Instead, ``InvalidToken`` falls through to ``json.loads(raw)`` —
    the plaintext IS the value. The caller (``save()``) re-encrypts on
    the next write, so legacy rows migrate lazily rather than being
    erased.

    ``None`` / empty string → ``None`` (mirrors the pre-leg truthiness
    decode: NULL and empty string both mean "not set").

    ``JSONDecodeError`` is NOT swallowed in either branch — real
    corruption (ciphertext that decrypts to non-JSON, or plaintext that
    isn't valid JSON) must surface, not be silently masked.
    """
    if not raw:
        return None
    try:
        plaintext = encryptor.decrypt(raw)
    except InvalidToken:
        # Legacy plaintext (pre-leg row, or a row not yet rewritten by a
        # save() since this leg landed). NOT migration-residue-as-empty:
        # this is real operator data. json.loads below propagates
        # JSONDecodeError for genuine corruption.
        return json.loads(raw)
    return json.loads(plaintext)


# ── Agent repository ──────────────────────────────────────────────────────


class SQLiteAgentStore:
    """Async agent config store backed by SQLite."""

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor | None = None) -> None:
        self.conn = conn
        if encryptor is None:
            # Local imports: `config.py` and `encryption.py` import
            # nothing from `the_one`, so no cycle — matches the
            # `_tool_provider.py:242` precedent for a defaulted,
            # settings-resolved encryptor.
            from the_one.config import settings
            from the_one.encryption import get_encryptor

            encryptor = get_encryptor(settings.data_dir)
        self.encryptor = encryptor  # Reference, NOT copy. install_key() post-rotation
        # must propagate to this store. Mirrors MCPSourceRepository:405-407.

    async def list_agents(self) -> list[str]:
        async with self.conn.execute("SELECT name FROM agents ORDER BY name") as cur:
            return [row[0] for row in await cur.fetchall()]

    async def list_retention_windows(self) -> list[tuple[str, int]]:
        """(name, chat_history_retention_days) for every agent — the
        projection the daily purge sweep enumerates (M13 F03). Avoids the
        full-config decode of load() per agent."""
        async with self.conn.execute(
            "SELECT name, chat_history_retention_days FROM agents ORDER BY name"
        ) as cur:
            return [(row[0], row[1]) for row in await cur.fetchall()]

    async def list_by_provider(self, provider_config_id: str) -> list[str]:
        """Return agent names that reference the given provider config."""
        async with self.conn.execute(
            "SELECT name FROM agents WHERE provider_config_id = ? ORDER BY name",
            (provider_config_id,),
        ) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def list_by_connector(self, account_id: str) -> list[AgentConfig]:
        """Return agent configs attached to ``account_id``.

        M10 F7 L3: inverse-query for the routing engine (F7 L4) and the
        dispatcher integration (F7 L5). Returns the list alphabetically
        ordered by ``AgentConfig.name`` (via the SQL ``ORDER BY``).

        ``connector_ids`` is a JSON-encoded list column (F4 L5
        v17 migration). Filtering is Python-side after a full table
        scan — the agents table is operator-scale (tens, not millions),
        so the linear scan is acceptable. If this becomes a hot path
        a later mission can add a join table (or use SQLite's JSON1
        ``json_each``).

        Returns ``[]`` for unknown account; does NOT raise.
        """
        async with self.conn.execute("SELECT * FROM agents ORDER BY name") as cur:
            rows = await cur.fetchall()
        result: list[AgentConfig] = []
        for row in rows:
            config = self._row_to_config(row)
            if account_id in config.connector_ids:
                result.append(config)
        return result

    async def load(self, name: str) -> AgentConfig:
        async with self.conn.execute("SELECT * FROM agents WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Agent config not found: {name}")
        return self._row_to_config(row)

    async def save(self, config: AgentConfig) -> None:
        now = now_iso()
        await self.conn.execute(
            """\
            INSERT INTO agents (
                name, description, provider_config_id, llm_model,
                system_prompt, enabled_tools, disabled_tools, max_iterations,
                kb_ids, mcp_source_ids, tool_overrides, mcp_overrides,
                connector_ids, connector_acls,
                connector_always_listen, chat_history_retention_days,
                self_revision_requires_approval,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description=excluded.description,
                provider_config_id=excluded.provider_config_id,
                llm_model=excluded.llm_model,
                system_prompt=excluded.system_prompt,
                enabled_tools=excluded.enabled_tools,
                disabled_tools=excluded.disabled_tools,
                max_iterations=excluded.max_iterations,
                kb_ids=excluded.kb_ids,
                mcp_source_ids=excluded.mcp_source_ids,
                tool_overrides=excluded.tool_overrides,
                mcp_overrides=excluded.mcp_overrides,
                connector_ids=excluded.connector_ids,
                connector_acls=excluded.connector_acls,
                connector_always_listen=excluded.connector_always_listen,
                chat_history_retention_days=excluded.chat_history_retention_days,
                self_revision_requires_approval=excluded.self_revision_requires_approval,
                updated_at=excluded.updated_at
            """,
            (
                config.name,
                config.description,
                config.provider_config_id,
                config.llm_model,
                config.system_prompt,
                json.dumps(config.enabled_tools) if config.enabled_tools is not None else None,
                json.dumps(config.disabled_tools),
                config.max_iterations,
                json.dumps(config.kb_ids),
                json.dumps(config.mcp_source_ids),
                _encrypt_overrides_column(self.encryptor, config.tool_overrides),
                _encrypt_overrides_column(self.encryptor, config.mcp_overrides),
                json.dumps(config.connector_ids),
                json.dumps(config.connector_acls) if config.connector_acls is not None else None,
                (
                    json.dumps(config.connector_always_listen)
                    if config.connector_always_listen is not None
                    else None
                ),
                config.chat_history_retention_days,
                int(config.self_revision_requires_approval),
                now,
                now,
            ),
        )
        await self.conn.commit()

    async def set_self_revision_requires_approval(self, name: str, value: bool) -> None:
        """Targeted UPDATE of the operator-owned approval-mode flag (M21 F02 L02).

        The immediate-post toggle touches ONLY this operator-owned scalar,
        so a targeted ``UPDATE`` dodges the whole-row last-writer-wins
        window a full ``save`` would open — safe here (unlike the DD4
        approve path, which must re-load to avoid clobbering the revision
        target). Raises ``KeyError`` if no agent exists at ``name`` (mirrors
        :meth:`delete` / :meth:`get`).
        """
        if not await self.exists(name):
            raise KeyError(f"Agent config not found: {name}")
        await self.conn.execute(
            "UPDATE agents SET self_revision_requires_approval = ?, updated_at = ? WHERE name = ?",
            (int(value), now_iso(), name),
        )
        await self.conn.commit()

    async def compare_and_set_field(
        self, name: str, field: str, base_value: str, new_value: str
    ) -> bool:
        """Field-scoped compare-and-swap (M21 F03 L02, DD5).

        Atomically write ``new_value`` into ``{field}`` for agent ``name``
        ONLY if the field still holds ``base_value``. Returns ``True`` iff
        exactly one row was updated (the base matched); ``False`` on a
        drift (the field changed under the writer) — the direct-write path
        turns a ``False`` into a truthful, non-retry-inducing ``stale``
        tool result.

        This closes the whole-row last-writer-wins clobber on the direct
        path: the single guarded ``UPDATE`` writes only the one column, so
        a concurrent write to the OTHER field is never clobbered, and the
        compare-and-write is one atomic statement (unlike Flight 2's
        approve-path non-atomic compare-then-save).

        ``field`` is interpolated into the SQL, so it is checked against a
        strict whitelist (defense in depth — the Literal at the tool
        boundary is the first guard; never interpolate an unvalidated
        field). A ``raise`` (not ``assert``) enforces the whitelist so the
        security-relevant guard survives ``python -O``.
        """
        if field not in {"description", "system_prompt"}:
            raise ValueError(f"illegal field: {field!r}")
        async with self.conn.execute(
            f"UPDATE agents SET {field} = ?, updated_at = ? WHERE name = ? AND {field} = ?",
            (new_value, now_iso(), name, base_value),
        ) as cur:
            rowcount = cur.rowcount
        await self.conn.commit()
        return rowcount == 1

    async def delete(self, name: str) -> None:
        if not await self.exists(name):
            raise KeyError(f"Agent config not found: {name}")
        await self.conn.execute("DELETE FROM agents WHERE name = ?", (name,))
        await self.conn.commit()

    async def exists(self, name: str) -> bool:
        async with self.conn.execute("SELECT 1 FROM agents WHERE name = ?", (name,)) as cur:
            return await cur.fetchone() is not None

    async def rename(self, old_name: str, new_name: str) -> None:
        """Atomically rename an agent.

        Raises ``KeyError`` if no agent exists at ``old_name`` (mirrors
        :meth:`delete`'s contract). Raises ``ValueError`` if an agent
        already exists at ``new_name`` — the API layer maps this to HTTP
        409 Conflict.

        The ``agents.name`` column is the primary key (``schema.py:37``);
        SQLite supports an atomic PK update via ``UPDATE``. The
        ``chat_sessions.agent_name`` column references that name but the
        FK constraint was dropped in schema v5 (``schema.py:188``), so
        we cascade manually within the same transaction.

        Runtime caveat: the in-memory PTY tool-session registry
        (``the_one/tools/sessions.py``) keys live sessions on
        ``(agent_name, session_id)``. This rename does NOT migrate
        in-memory keys; active sessions keyed on the old name will
        surface a transient error on next tool call. Documented as a
        Known Issue on Mission 08.
        """
        # Existence check first — raise KeyError to match delete() contract.
        if not await self.exists(old_name):
            raise KeyError(f"Agent config not found: {old_name}")
        # Conflict check — surface ValueError so the API can map to 409.
        if await self.exists(new_name):
            raise ValueError(f"Agent config already exists: {new_name}")
        now = now_iso()
        # Single transaction: atomic PK swap + manual cascade on
        # chat_sessions.agent_name (FK was dropped in schema v5).
        await self.conn.execute(
            "UPDATE agents SET name = ?, updated_at = ? WHERE name = ?",
            (new_name, now, old_name),
        )
        await self.conn.execute(
            "UPDATE chat_sessions SET agent_name = ? WHERE agent_name = ?",
            (new_name, old_name),
        )
        await self.conn.commit()

    def _row_to_config(self, row: aiosqlite.Row) -> AgentConfig:
        # Local import (squawk 0003): AgentConfig is TYPE_CHECKING-only at module
        # scope to break the repositories <-> agent.config <-> mcp._pool import
        # cycle; this is the one call site that needs the real class at runtime.
        from the_one.agent.config import AgentConfig

        enabled = json.loads(row["enabled_tools"]) if row["enabled_tools"] else None
        return AgentConfig(
            name=row["name"],
            description=row["description"] or "",
            provider_config_id=row["provider_config_id"],
            llm_model=row["llm_model"] or "",
            system_prompt=row["system_prompt"] or "",
            enabled_tools=enabled,
            disabled_tools=json.loads(row["disabled_tools"] or "[]"),
            max_iterations=row["max_iterations"] or 20,
            kb_ids=json.loads(row["kb_ids"] or "[]"),
            mcp_source_ids=json.loads(row["mcp_source_ids"] or "[]"),
            # Truthiness mirrors `enabled_tools` above: NULL and empty
            # string both deserialize to None. Missing-column safety
            # comes from the v8 migration having run, not from this
            # expression — `aiosqlite.Row[<missing>]` raises IndexError.
            # M21 F01 L01: both columns are now Fernet ciphertext at rest;
            # `_decrypt_overrides_column` tolerates legacy plaintext rows
            # (see its docstring for why `_decrypt_secrets_blob` is not
            # reused here).
            tool_overrides=_decrypt_overrides_column(self.encryptor, row["tool_overrides"]),
            mcp_overrides=_decrypt_overrides_column(self.encryptor, row["mcp_overrides"]),
            # `or "[]"` defends against both NULL (pre-v17 rows persisted
            # before the M10 F4 L5 migration added the column) AND the
            # empty-string edge case. The v17 migration is the gate that
            # guarantees the column exists; this expression handles the
            # NULL value for legacy rows.
            connector_ids=json.loads(row["connector_ids"] or "[]"),
            # M10 F6 L1c: per-agent ACL override. NULL (pre-v18 rows AND
            # the default for agents without per-agent narrowing) decodes
            # to None, distinguishing it from `{}` (which round-trips
            # verbatim — see the empty-outer-dict round-trip test). The
            # truthiness mirrors `tool_overrides` / `mcp_overrides` above.
            connector_acls=(json.loads(row["connector_acls"]) if row["connector_acls"] else None),
            # M11 F7 L6: per-agent always_listen toggle. NULL (pre-v20 rows
            # AND default for agents without per-agent overrides) decodes
            # to None, distinguishing it from `{}` (an agent that was
            # edited then had all toggles removed). Truthiness mirrors
            # `connector_acls` above.
            connector_always_listen=(
                json.loads(row["connector_always_listen"])
                if row["connector_always_listen"]
                else None
            ),
            chat_history_retention_days=row["chat_history_retention_days"],
            # M21 F02 L02: per-agent approval mode. Plain read mirroring
            # `chat_history_retention_days` above — the v35 migration adds the
            # column `NOT NULL DEFAULT 0` and backfills every row, so no
            # absent/NULL case survives at load (an inline missing-column
            # access on `aiosqlite.Row` would raise IndexError anyway).
            self_revision_requires_approval=bool(row["self_revision_requires_approval"]),
        )


# ── Knowledge base repository ────────────────────────────────────────────


class KnowledgeBaseRepository:
    """Async CRUD for knowledge bases."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list(self) -> list[KnowledgeBase]:
        async with self.conn.execute("SELECT * FROM knowledge_bases ORDER BY name") as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, kb_id: str) -> KnowledgeBase:
        async with self.conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Knowledge base not found: {kb_id}")
        return self._row_to_model(row)

    async def create(self, kb: KnowledgeBase) -> None:
        await self.conn.execute(
            "INSERT INTO knowledge_bases (id, name, description, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (kb.id, kb.name, kb.description, kb.created_at, kb.updated_at),
        )
        await self.conn.commit()

    async def update(self, kb: KnowledgeBase) -> None:
        if not await self._exists(kb.id):
            raise KeyError(f"Knowledge base not found: {kb.id}")
        await self.conn.execute(
            "UPDATE knowledge_bases SET name=?, description=?, updated_at=? WHERE id=?",
            (kb.name, kb.description, now_iso(), kb.id),
        )
        await self.conn.commit()

    async def delete(self, kb_id: str) -> None:
        if not await self._exists(kb_id):
            raise KeyError(f"Knowledge base not found: {kb_id}")
        await self.conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
        await self.conn.commit()

    async def _exists(self, kb_id: str) -> bool:
        async with self.conn.execute("SELECT 1 FROM knowledge_bases WHERE id = ?", (kb_id,)) as cur:
            return await cur.fetchone() is not None

    @staticmethod
    def _row_to_model(row: aiosqlite.Row) -> KnowledgeBase:
        return KnowledgeBase(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── KB item repository ───────────────────────────────────────────────────


class KBItemRepository:
    """Async CRUD for knowledge base items."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list(self, kb_id: str) -> list[KBItem]:
        async with self.conn.execute(
            "SELECT * FROM kb_items WHERE kb_id = ? ORDER BY created_at", (kb_id,)
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, item_id: str) -> KBItem:
        async with self.conn.execute("SELECT * FROM kb_items WHERE id = ?", (item_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"KB item not found: {item_id}")
        return self._row_to_model(row)

    async def create(self, item: KBItem) -> None:
        await self.conn.execute(
            "INSERT INTO kb_items (id, kb_id, parent_id, type, path_or_url, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.kb_id,
                item.parent_id,
                item.type,
                item.path_or_url,
                item.status,
                item.created_at,
            ),
        )
        await self.conn.commit()

    async def delete(self, item_id: str) -> None:
        async with self.conn.execute("SELECT 1 FROM kb_items WHERE id = ?", (item_id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"KB item not found: {item_id}")
        await self.conn.execute("DELETE FROM kb_items WHERE id = ?", (item_id,))
        await self.conn.commit()

    @staticmethod
    def _row_to_model(row: aiosqlite.Row) -> KBItem:
        return KBItem(
            id=row["id"],
            kb_id=row["kb_id"],
            parent_id=row["parent_id"],
            type=row["type"],
            path_or_url=row["path_or_url"],
            status=row["status"] or "pending",
            created_at=row["created_at"],
        )


# ── MCP source repository ────────────────────────────────────────────────


class MCPSourceRepository:
    """Async CRUD for MCP sources."""

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
        self.conn = conn
        self.encryptor = encryptor  # Reference, NOT copy. install_key() post-rotation
        # must propagate to live repository instances.
        # Mirrors LLMProviderRepository:489.

    def _secrets_to_ciphertext(self, secrets: dict[str, Any]) -> str:
        """Delegates to :func:`_encrypt_secrets_blob`."""
        return _encrypt_secrets_blob(self.encryptor, secrets)

    def _ciphertext_to_secrets(self, ciphertext: str | None) -> dict[str, Any]:
        """Delegates to :func:`_decrypt_secrets_blob`."""
        return _decrypt_secrets_blob(self.encryptor, ciphertext)

    async def list(self) -> list[MCPSource]:
        async with self.conn.execute("SELECT * FROM mcp_sources ORDER BY name") as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, source_id: str) -> MCPSource:
        async with self.conn.execute("SELECT * FROM mcp_sources WHERE id = ?", (source_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"MCP source not found: {source_id}")
        return self._row_to_model(row)

    async def create(self, source: MCPSource) -> None:
        await self.conn.execute(
            "INSERT INTO mcp_sources (id, name, type, config, secrets, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                source.id,
                source.name,
                source.type,
                json.dumps(source.config),
                self._secrets_to_ciphertext(source.secrets),
                source.created_at,
                source.updated_at,
            ),
        )
        await self.conn.commit()

    async def update(self, source: MCPSource) -> None:
        async with self.conn.execute("SELECT 1 FROM mcp_sources WHERE id = ?", (source.id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"MCP source not found: {source.id}")
        await self.conn.execute(
            "UPDATE mcp_sources SET name=?, type=?, config=?, secrets=?, updated_at=? WHERE id=?",
            (
                source.name,
                source.type,
                json.dumps(source.config),
                self._secrets_to_ciphertext(source.secrets),
                now_iso(),
                source.id,
            ),
        )
        await self.conn.commit()

    async def delete(self, source_id: str) -> None:
        async with self.conn.execute("SELECT 1 FROM mcp_sources WHERE id = ?", (source_id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"MCP source not found: {source_id}")
        await self.conn.execute("DELETE FROM mcp_sources WHERE id = ?", (source_id,))
        await self.conn.commit()

    async def find_by_runtime_package(
        self, runtime: str, package: str, exclude_id: str
    ) -> list[MCPSource]:
        """Return every other MCP source whose (command, args) decode to
        the same (runtime, package) pair.

        Used by the delete handler to refcount cache cleanup: if any
        other source still references the same lazy-install package,
        skip the cleanup so we don't yank a cache slot the survivor
        depends on.

        Decoding is done in Python — ``config`` is JSON TEXT in SQLite,
        and a SQL LIKE on the JSON string would be brittle (arg order,
        version pins, ``--from`` indirection). The deserialized form
        runs through :func:`extract_runtime_package` for parity with the
        delete handler.
        """
        # Local import to avoid a circular: cache_cleanup is in the_one.mcp,
        # which transitively imports db modules through other helpers.
        from the_one.mcp.cache_cleanup import extract_runtime_package

        async with self.conn.execute(
            "SELECT * FROM mcp_sources WHERE id != ?", (exclude_id,)
        ) as cur:
            rows = await cur.fetchall()
        matches: list[MCPSource] = []
        for row in rows:
            model = self._row_to_model(row)
            cfg = model.config or {}
            cmd = cfg.get("command", "")
            args = cfg.get("args", []) or []
            if not isinstance(cmd, str) or not isinstance(args, list):
                continue
            decoded = extract_runtime_package(cmd, args)
            if decoded == (runtime, package):
                matches.append(model)
        return matches

    def _row_to_model(self, row: aiosqlite.Row) -> MCPSource:
        return MCPSource(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            config=json.loads(row["config"] or "{}"),
            secrets=self._ciphertext_to_secrets(row["secrets"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── Connector account repository ─────────────────────────────────────────


class ConnectorRepository:
    """Async CRUD for connector accounts.

    Mission 10 flight 01 — sibling of :class:`MCPSourceRepository`.
    Mirrors the MCP envelope: encryptor held by reference (not copy) so
    post-rotation ``install_key`` propagates to live instances;
    ``_secrets_to_ciphertext`` / ``_ciphertext_to_secrets`` per-row Fernet
    blob; ``InvalidToken`` tolerantly collapses to ``{}`` for
    migration-residue rows; ``JSONDecodeError`` propagates as real
    corruption.

    No ``find_by_runtime_package`` analog: connectors have no lazy-install
    cache to refcount at delete time.

    No ``__MASKED__`` sentinel handling here — that runs at the API edge
    (mirroring ``LLMProviderConfig._normalize_api_key``'s contract).
    """

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
        self.conn = conn
        self.encryptor = encryptor  # Reference, NOT copy. install_key() post-rotation
        # must propagate to live repository instances.
        # Mirrors MCPSourceRepository at the top of this file.

    def _secrets_to_ciphertext(self, secrets: dict[str, Any]) -> str:
        """Delegates to :func:`_encrypt_secrets_blob`."""
        return _encrypt_secrets_blob(self.encryptor, secrets)

    def _ciphertext_to_secrets(self, ciphertext: str | None) -> dict[str, Any]:
        """Delegates to :func:`_decrypt_secrets_blob`."""
        return _decrypt_secrets_blob(self.encryptor, ciphertext)

    async def list(self) -> list[Connector]:
        async with self.conn.execute("SELECT * FROM connectors ORDER BY name") as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, account_id: str) -> Connector:
        async with self.conn.execute("SELECT * FROM connectors WHERE id = ?", (account_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Connector account not found: {account_id}")
        return self._row_to_model(row)

    async def create(self, account: Connector) -> None:
        await self.conn.execute(
            "INSERT INTO connectors"
            " (id, name, type, config, secrets, idle_timeout_seconds,"
            "  session_continuation_seconds, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                account.id,
                account.name,
                account.type,
                json.dumps(account.config),
                self._secrets_to_ciphertext(account.secrets),
                account.idle_timeout_seconds,
                account.session_continuation_seconds,
                account.created_at,
                account.updated_at,
            ),
        )
        await self.conn.commit()

    async def update(self, account: Connector) -> None:
        async with self.conn.execute("SELECT 1 FROM connectors WHERE id = ?", (account.id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account.id}")
        await self.conn.execute(
            "UPDATE connectors"
            " SET name=?, type=?, config=?, secrets=?, idle_timeout_seconds=?,"
            "     session_continuation_seconds=?, updated_at=? WHERE id=?",
            (
                account.name,
                account.type,
                json.dumps(account.config),
                self._secrets_to_ciphertext(account.secrets),
                account.idle_timeout_seconds,
                account.session_continuation_seconds,
                now_iso(),
                account.id,
            ),
        )
        await self.conn.commit()

    async def delete(self, account_id: str) -> None:
        async with self.conn.execute("SELECT 1 FROM connectors WHERE id = ?", (account_id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account_id}")
        await self.conn.execute("DELETE FROM connectors WHERE id = ?", (account_id,))
        await self.conn.commit()

    def _row_to_model(self, row: aiosqlite.Row) -> Connector:
        return Connector(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            config=json.loads(row["config"] or "{}"),
            secrets=self._ciphertext_to_secrets(row["secrets"]),
            idle_timeout_seconds=row["idle_timeout_seconds"],
            session_continuation_seconds=row["session_continuation_seconds"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── Pending approval repository ──────────────────────────────────────────


class PendingApprovalRepository:
    """Async CRUD for pending Discord-native peer approvals.

    M11 F9 L2. No encryptor (no secrets to encrypt). Mirrors
    ``ConnectorRepository`` connection-passing shape sans the
    encryptor argument.

    Dedup contract (cycle-2 architect §2): ``upsert_pending`` enforces
    ONE row per ``(connector_id, peer_id, status='pending')``
    via an UPDATE-in-place when the index matches, INSERT otherwise.
    Terminal-state transitions (``mark_approved``, ``mark_dismissed``)
    raise ``ValueError`` if invoked on an already-terminal row OTHER
    than the same target (idempotent on self-target — calling
    ``mark_approved`` on an approved row is a no-op).
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def get(self, approval_id: str) -> PendingApproval:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Pending approval not found: {approval_id}")
        return self._row_to_model(row)

    async def upsert_pending(
        self,
        *,
        connector_id: str,
        peer_id: str,
        peer_name: str,
        preview: str,
        original_message: str | None = None,
        channel_id: str | None = None,
        thread_id: str | None = None,
        is_dm: bool | None = None,
    ) -> tuple["PendingApproval", bool]:
        """Upsert a pending row keyed by (account, peer, status='pending').

        If a pending row already exists for (account, peer), UPDATE
        ``peer_name``, ``preview``, ``received_at`` in place and return
        ``(updated_row, False)``. Otherwise INSERT a fresh row with a new
        uuid and ``status='pending'`` and return ``(new_row, True)``.

        The ``created`` bool lets callers distinguish a first-time DM from a
        repeat DM while still pending — used by the inbound dispatcher to fire
        a one-time auto-reply only on creation (M11 F17 L9 — Leg E).

        The v29 replay-context fields (``original_message``, ``channel_id``,
        ``thread_id``, ``is_dm``) are stored on INSERT and on UPDATE so the
        approval-replay path always has the latest message context available
        (M11 F17 L10 — Leg F).
        """
        async with self.conn.execute(
            "SELECT id FROM pending_approvals "
            "WHERE connector_id = ? AND peer_id = ? AND status = 'pending' "
            "LIMIT 1",
            (connector_id, peer_id),
        ) as cur:
            existing = await cur.fetchone()
        ts = now_iso()
        is_dm_int = int(is_dm) if is_dm is not None else None
        if existing is None:
            # 32-char full hex (matches connectors/_session.py:184 — same
            # world: dispatcher-created, web-API-referenced).
            new_id = uuid.uuid4().hex
            await self.conn.execute(
                "INSERT INTO pending_approvals "
                "(id, connector_id, peer_id, peer_name, preview, "
                " received_at, status, resolved_at, "
                " original_message, channel_id, thread_id, is_dm) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?, ?, ?)",
                (
                    new_id,
                    connector_id,
                    peer_id,
                    peer_name,
                    preview,
                    ts,
                    original_message,
                    channel_id,
                    thread_id,
                    is_dm_int,
                ),
            )
            await self.conn.commit()
            return await self.get(new_id), True
        approval_id = existing["id"]
        await self.conn.execute(
            "UPDATE pending_approvals "
            "SET peer_name = ?, preview = ?, received_at = ?, "
            "    original_message = ?, channel_id = ?, thread_id = ?, is_dm = ? "
            "WHERE id = ?",
            (
                peer_name,
                preview,
                ts,
                original_message,
                channel_id,
                thread_id,
                is_dm_int,
                approval_id,
            ),
        )
        await self.conn.commit()
        return await self.get(approval_id), False

    async def list_for_account_peer(self, account_id: str, peer_id: str) -> list[PendingApproval]:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals "
            "WHERE connector_id = ? AND peer_id = ? "
            "ORDER BY received_at ASC",
            (account_id, peer_id),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def list_by_account(self, account_id: str) -> list[PendingApproval]:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals WHERE connector_id = ? ORDER BY received_at ASC",
            (account_id,),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def count_pending(self) -> int:
        """Return the global count of ``status='pending'`` rows across all connectors.

        Used by ``GET /api/connectors/peer-approvals/pending-count``
        (M11 F17 L9 — Leg E top-nav badge).
        """
        async with self.conn.execute(
            "SELECT COUNT(*) FROM pending_approvals WHERE status = 'pending'"
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def list_all_pending(self) -> list["PendingApproval"]:
        """Return all ``status='pending'`` rows across all connectors, newest first.

        Used by ``GET /api/connectors/peer-approvals/pending`` for the Chat
        left-panel pending section (M11 F17 L9 — Leg E).
        """
        async with self.conn.execute(
            "SELECT * FROM pending_approvals WHERE status = 'pending' ORDER BY received_at DESC"
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def mark_approved(self, approval_id: str) -> PendingApproval:
        return await self._transition(approval_id, "approved")

    async def mark_dismissed(self, approval_id: str) -> PendingApproval:
        return await self._transition(approval_id, "dismissed")

    async def _transition(
        self, approval_id: str, target: Literal["approved", "dismissed"]
    ) -> PendingApproval:
        current = await self.get(approval_id)  # raises KeyError
        if current.status == target:
            return current  # idempotent on self-target
        if current.status != "pending":
            raise ValueError(
                f"Pending approval {approval_id} is {current.status}; cannot transition to {target}"
            )
        await self.conn.execute(
            "UPDATE pending_approvals SET status = ?, resolved_at = ? WHERE id = ?",
            (target, now_iso(), approval_id),
        )
        await self.conn.commit()
        return await self.get(approval_id)

    def _row_to_model(self, row: aiosqlite.Row) -> PendingApproval:
        # v29 replay-context fields are nullable (additive ALTER ADD COLUMN
        # — pre-v29 rows carry NULL for all four). Read via dict-access +
        # ``None`` fallback so the method works against both pre-v29 and
        # post-v29 rows (and against hand-built test fixtures that may not
        # include the new columns in the SELECT).
        keys = row.keys() if hasattr(row, "keys") else []
        is_dm_raw = row["is_dm"] if "is_dm" in keys else None
        return PendingApproval(
            id=row["id"],
            connector_id=row["connector_id"],
            peer_id=row["peer_id"],
            peer_name=row["peer_name"],
            preview=row["preview"],
            received_at=row["received_at"],
            status=row["status"],
            resolved_at=row["resolved_at"],
            original_message=row["original_message"] if "original_message" in keys else None,
            channel_id=row["channel_id"] if "channel_id" in keys else None,
            thread_id=row["thread_id"] if "thread_id" in keys else None,
            is_dm=bool(is_dm_raw) if is_dm_raw is not None else None,
        )


# ── Agent revision repository ────────────────────────────────────────────


class AgentRevisionRepository:
    """Async access to the ``agent_revisions`` revision log (M21 F02 L01).

    No encryptor (mirrors :class:`PendingApprovalRepository`): the logged
    ``base_value`` / ``proposed_value`` are the plaintext ``description`` /
    ``system_prompt`` values, which cross no encryption boundary, so the
    log holds no secret material.

    L01 is log-facing only: ``append`` / ``get`` / ``list_for_agent``. The
    queue-state transitions and ``count_pending`` belong to Leg 2's state
    machine; restore provenance (``source='restore'``, ``restored_from``)
    is Leg 3. Callers here pass ``status='applied', source='self',
    restored_from=None, resolved_at=created_at`` (an applied row is
    resolved at creation).
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def append(
        self,
        *,
        agent_name: str,
        field: str,
        proposed_value: str,
        base_value: str,
        source: str,
        status: str,
        created_at: str,
        resolved_at: str | None,
        restored_from: str | None = None,
        source_principal: str | None = None,
    ) -> AgentRevision:
        """Insert one revision row and return it.

        Mints ``id`` as ``uuid.uuid4().hex`` (the repository owns the
        INSERT; the caller supplies ``created_at`` / ``resolved_at``
        explicitly, so the id is not a model ``default_factory``) —
        mirroring ``PendingApprovalRepository.upsert_pending``.

        M21 F03 L02 (DD3): ``source_principal`` records the external
        credential identifier for ``source='external'`` rows (NULL for
        ``self`` / ``restore``).
        """
        revision_id = uuid.uuid4().hex
        await self.conn.execute(
            "INSERT INTO agent_revisions "
            "(id, agent_name, field, proposed_value, base_value, "
            " status, source, source_principal, restored_from, created_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                revision_id,
                agent_name,
                field,
                proposed_value,
                base_value,
                status,
                source,
                source_principal,
                restored_from,
                created_at,
                resolved_at,
            ),
        )
        await self.conn.commit()
        return await self.get(revision_id)

    async def get(self, revision_id: str) -> AgentRevision:
        async with self.conn.execute(
            "SELECT * FROM agent_revisions WHERE id = ?", (revision_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Agent revision not found: {revision_id}")
        return self._row_to_model(row)

    async def list_for_agent(self, agent_name: str) -> list[AgentRevision]:
        """Return an agent's revisions newest-first.

        ``ORDER BY created_at DESC, id DESC`` — the ``id DESC`` tiebreak on
        same-microsecond rows is a uuid-hex order (arbitrary-but-stable,
        not insertion order), acceptable at operator-scale.
        """
        async with self.conn.execute(
            "SELECT * FROM agent_revisions WHERE agent_name = ? ORDER BY created_at DESC, id DESC",
            (agent_name,),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    # ── Leg 2 (M21 F02 L02) — pending-queue state machine ─────────────

    async def count_pending(self, agent_name: str) -> int:
        """Return the count of ``status='pending'`` rows for one agent.

        Scoped to ``agent_name`` (unlike the connector
        ``PendingApprovalRepository.count_pending`` which is global) —
        approval mode and its queue are per-agent.
        """
        async with self.conn.execute(
            "SELECT COUNT(*) FROM agent_revisions WHERE agent_name = ? AND status = 'pending'",
            (agent_name,),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def upsert_pending_revision(
        self,
        *,
        agent_name: str,
        field: str,
        proposed_value: str,
        base_value: str,
        source: str = "self",
        source_principal: str | None = None,
    ) -> tuple[AgentRevision, bool]:
        """Upsert a pending revision keyed by ``(agent_name, field, pending)``.

        Dedup contract (DD3): one ``pending`` row per ``(agent_name,
        field)``. If a pending row already exists for that pair, UPDATE
        ``proposed_value`` / ``base_value`` / ``created_at`` in place and
        return ``(updated_row, False)``. Otherwise ``append`` a fresh
        ``status='pending', resolved_at=None`` row and return
        ``(new_row, True)`` — mirroring
        ``PendingApprovalRepository.upsert_pending``'s ``created`` flag.

        A re-propose refreshes ``base_value`` to the latest captured
        value, so the DD4 staleness window resets to the newest proposal
        (leg Edge Cases). M21 F03 L02 (DD3): ``source`` /
        ``source_principal`` are refreshed on the in-place UPDATE too, so a
        re-propose by a DIFFERENT principal records the LATEST proposer on
        the deduped row (leg AC7 / Edge Cases).
        """
        async with self.conn.execute(
            "SELECT id FROM agent_revisions "
            "WHERE agent_name = ? AND field = ? AND status = 'pending' "
            "LIMIT 1",
            (agent_name, field),
        ) as cur:
            existing = await cur.fetchone()
        ts = now_iso()
        if existing is None:
            return (
                await self.append(
                    agent_name=agent_name,
                    field=field,
                    proposed_value=proposed_value,
                    base_value=base_value,
                    source=source,
                    source_principal=source_principal,
                    status="pending",
                    created_at=ts,
                    resolved_at=None,
                ),
                True,
            )
        revision_id = existing["id"]
        await self.conn.execute(
            "UPDATE agent_revisions "
            "SET proposed_value = ?, base_value = ?, created_at = ?, "
            "    source = ?, source_principal = ? "
            "WHERE id = ?",
            (proposed_value, base_value, ts, source, source_principal, revision_id),
        )
        await self.conn.commit()
        return await self.get(revision_id), False

    async def mark_applied(self, revision_id: str) -> AgentRevision:
        return await self._transition(revision_id, "applied")

    async def mark_dismissed(self, revision_id: str) -> AgentRevision:
        return await self._transition(revision_id, "dismissed")

    async def _transition(
        self, revision_id: str, target: Literal["applied", "dismissed"]
    ) -> AgentRevision:
        """Transition a ``pending`` row to a terminal state.

        Copies ``PendingApprovalRepository._transition`` semantics:
        idempotent when already at ``target``; ``ValueError`` on any
        non-``pending`` non-``target`` state (the API layer maps this to
        409); a single UPDATE stamping ``status`` + ``resolved_at``.
        """
        current = await self.get(revision_id)  # raises KeyError
        if current.status == target:
            return current  # idempotent on self-target
        if current.status != "pending":
            raise ValueError(
                f"Agent revision {revision_id} is {current.status}; cannot transition to {target}"
            )
        await self.conn.execute(
            "UPDATE agent_revisions SET status = ?, resolved_at = ? WHERE id = ?",
            (target, now_iso(), revision_id),
        )
        await self.conn.commit()
        return await self.get(revision_id)

    async def update_base_value(self, revision_id: str, base_value: str) -> AgentRevision:
        """Re-capture ``base_value`` to a new value (DD4 approve override).

        Used only on the override path when the operator elects to
        overwrite a drifted field — the endpoint re-captures ``base_value``
        to the current stored value before applying, so the applied row
        records the base it actually overwrote.
        """
        await self.conn.execute(
            "UPDATE agent_revisions SET base_value = ? WHERE id = ?",
            (base_value, revision_id),
        )
        await self.conn.commit()
        return await self.get(revision_id)

    async def supersede_pending(self, agent_name: str) -> int:
        """Mark every outstanding ``pending`` row for an agent ``superseded`` (DD8).

        Called when the self-configuration surface is disabled — a
        revision proposed under a since-revoked surface must not be
        approvable afterward. Returns the number of rows superseded.
        """
        cur = await self.conn.execute(
            "UPDATE agent_revisions SET status = 'superseded', resolved_at = ? "
            "WHERE agent_name = ? AND status = 'pending'",
            (now_iso(), agent_name),
        )
        await self.conn.commit()
        return cur.rowcount

    def _row_to_model(self, row: aiosqlite.Row) -> AgentRevision:
        return AgentRevision(
            id=row["id"],
            agent_name=row["agent_name"],
            field=row["field"],
            proposed_value=row["proposed_value"],
            base_value=row["base_value"],
            status=row["status"],
            source=row["source"],
            source_principal=row["source_principal"],
            restored_from=row["restored_from"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )


# ── Tool config repository ───────────────────────────────────────────────


class ToolConfigRepository:
    """Async CRUD for tool-level config rows.

    Mirrors `MCPSourceRepository` but keyed by `name` (the tool's
    stable identifier — operators set tool config by name, the row
    exists or it doesn't, so there's no separate create/update split).
    `list_all()` is the resolver-facing convenience read; the resolver
    in L3 imports `list_all`, NOT `list`.

    M16 F08 L03: carries an `encryptor` (BY REFERENCE — `install_key()`
    post-rotation must propagate to live instances) and a `secrets`
    column. Built-in tool secrets (e.g. `web_search`'s keyed-engine API
    keys) encrypt on write / decrypt on read via the shared Fernet
    helpers, mirroring `MCPSourceRepository`.
    """

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
        self.conn = conn
        self.encryptor = encryptor  # Reference, NOT copy — same rotation
        # propagation contract as MCPSourceRepository.

    def _secrets_to_ciphertext(self, secrets: dict[str, Any]) -> str:
        """Delegates to :func:`_encrypt_secrets_blob`."""
        return _encrypt_secrets_blob(self.encryptor, secrets)

    def _ciphertext_to_secrets(self, ciphertext: str | None) -> dict[str, Any]:
        """Delegates to :func:`_decrypt_secrets_blob`."""
        return _decrypt_secrets_blob(self.encryptor, ciphertext)

    async def list(self) -> list[ToolConfig]:
        """Operator-UI-facing read; `list` shadows the builtin to match
        `MCPSourceRepository.list` consistency."""
        async with self.conn.execute("SELECT * FROM tool_configs ORDER BY name") as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def list_all(self) -> dict[str, dict]:
        """Resolver-facing read: `{tool_name: config_dict}`.

        Convenience wrapper over `list()`. L3's resolver imports this
        method (NOT `list`) and treats an empty `tool_configs.config`
        identically to a missing row.
        """
        items = await self.list()
        return {item.name: item.config for item in items}

    async def get(self, name: str) -> ToolConfig:
        async with self.conn.execute("SELECT * FROM tool_configs WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Tool config not found: {name}")
        return self._row_to_model(row)

    async def upsert(
        self, name: str, config: dict, secrets: dict | None = None, enabled: bool = True
    ) -> None:
        """INSERT or REPLACE the config row, bumping `updated_at` on update.

        `secrets` is a DEFAULTED kwarg (None → `{}`) so existing call
        sites (`upsert(name, config[, enabled=…])`) keep working
        unchanged; it is Fernet-encrypted into the `secrets` column.

        `enabled` defaults to True so existing call sites (resolver,
        factory) continue to work without modification. The F6 admin
        UI is the first caller to pass `enabled=False`.

        Caveat: ON CONFLICT writes `enabled=excluded.enabled`, which
        means a config-only update that omits the kwarg will silently
        re-enable a previously-disabled row. Callers that want to
        update only `config` (keeping the existing `enabled` state)
        must read first via `get(name)` and pass the existing flag.
        The L1 admin PUT endpoint sends the full row state, so the
        "last write wins" semantics are intentional for that surface.
        """
        secrets = secrets or {}
        await self.conn.execute(
            """\
            INSERT INTO tool_configs (name, config, secrets, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                config=excluded.config,
                secrets=excluded.secrets,
                enabled=excluded.enabled,
                updated_at=excluded.updated_at
            """,
            (
                name,
                json.dumps(config),
                self._secrets_to_ciphertext(secrets),
                int(enabled),
                now_iso(),
                now_iso(),
            ),
        )
        await self.conn.commit()

    async def delete(self, name: str) -> None:
        if not await self.exists(name):
            raise KeyError(f"Tool config not found: {name}")
        await self.conn.execute("DELETE FROM tool_configs WHERE name = ?", (name,))
        await self.conn.commit()

    async def exists(self, name: str) -> bool:
        async with self.conn.execute("SELECT 1 FROM tool_configs WHERE name = ?", (name,)) as cur:
            return await cur.fetchone() is not None

    def _row_to_model(self, row: aiosqlite.Row) -> ToolConfig:
        keys = row.keys()
        return ToolConfig(
            name=row["name"],
            config=json.loads(row["config"] or "{}"),
            secrets=self._ciphertext_to_secrets(row["secrets"] if "secrets" in keys else None),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── App metadata repository ──────────────────────────────────────────────


class AppMetadataRepository:
    """Async get/set for the global ``app_metadata`` key/value store.

    A single-row-per-key kv table (schema v31). Leg 3 uses it to hold the
    daily purge's ``last_purge_at`` timestamp via ``get("last_purge_at")`` /
    ``set("last_purge_at", <iso>)``. Generic by design — callers pass the
    key string. Values are non-NULL strings (``value TEXT NOT NULL``).
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def get(self, key: str) -> str | None:
        """Return the stored string for ``key``, or ``None`` if absent."""
        async with self.conn.execute("SELECT value FROM app_metadata WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
        return row[0] if row is not None else None

    async def set(self, key: str, value: str) -> None:
        """Insert or update ``key`` to ``value`` (upsert; latest value wins)."""
        await self.conn.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()


# ── Chat session repository ──────────────────────────────────────────────


class ChatSessionRepository:
    """Async CRUD for chat sessions."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list(self, agent_name: str | None = None) -> list[ChatSession]:
        if agent_name:
            sql = "SELECT * FROM chat_sessions WHERE agent_name = ? ORDER BY updated_at DESC"
            params: tuple = (agent_name,)
        else:
            sql = "SELECT * FROM chat_sessions ORDER BY updated_at DESC"
            params = ()
        async with self.conn.execute(sql, params) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, session_id: str) -> ChatSession:
        async with self.conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Chat session not found: {session_id}")
        return self._row_to_model(row)

    async def find_most_recent_by_external_key(
        self,
        *,
        platform: str,
        connector_id: str,
        channel_id: str,
        thread_id: str | None,
    ) -> ChatSession | None:
        """Return the most recent connector-keyed session for the external 4-tuple.

        Uses ``COALESCE(thread_id, '')`` on both sides to mirror the
        partial-index expression at
        ``the_one/db/schema.py`` (v16 migration) and handle SQLite's
        NULL-distinct semantics — a query with ``thread_id=None`` matches
        rows where the column is NULL (treated as empty string on both
        sides by COALESCE).

        Ordered by ``updated_at DESC LIMIT 1`` — the active session for
        this external location is the most-recently-touched row. Older
        superseded sessions are preserved (per flight design: historical
        sessions remain queryable in Chat UI as distinct rows).

        M10 F03 L03 — consumed by
        :func:`the_one.connectors._session.resolve_session`.
        """
        async with self.conn.execute(
            "SELECT * FROM chat_sessions"
            " WHERE platform = ? AND connector_id = ?"
            " AND channel_id = ? AND COALESCE(thread_id, '') = COALESCE(?, '')"
            " ORDER BY updated_at DESC LIMIT 1",
            (platform, connector_id, channel_id, thread_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return self._row_to_model(row)

    async def create(self, session: ChatSession) -> None:
        await self.conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at,"
            " platform, connector_id, channel_id, thread_id, peer_id,"
            " session_metadata, last_inbound_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session.id,
                session.agent_name,
                session.title,
                session.messages,
                session.created_at,
                session.updated_at,
                session.platform,
                session.connector_id,
                session.channel_id,
                session.thread_id,
                session.peer_id,
                json.dumps(session.session_metadata)
                if session.session_metadata is not None
                else None,
                session.last_inbound_at,
            ),
        )
        await self.conn.commit()

    async def update(self, session: ChatSession) -> None:
        """Update the mutable session fields (title, messages, updated_at).

        The seven connector-keyed identity columns (platform,
        connector_id, channel_id, thread_id, peer_id,
        session_metadata, last_inbound_at) added by M10 F03 L01 are
        intentionally NOT round-tripped by this method — they are
        identity attributes set once at row creation (by the resolver
        in M10 F03 L03) and mutated only through the narrow primitive
        :meth:`update_last_inbound` (M10 F03 L04) and through this
        method itself for whole-history mutations (e.g.
        ``_save_session_to_db`` at
        ``the_one/interfaces/web/app.py:469-487``; the connector
        dispatcher at
        ``the_one/connectors/_inbound.py:dispatch_inbound``). The
        whole-history pattern fetches the row, calls
        ``row.model_copy(update={"title": ..., "messages": ...})``,
        and hands the result to ``repo.update`` — the connector-
        identity columns survive that round-trip because this SQL
        does not touch them.
        """
        async with self.conn.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ?", (session.id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Chat session not found: {session.id}")
        await self.conn.execute(
            "UPDATE chat_sessions SET title=?, messages=?, updated_at=? WHERE id=?",
            (session.title, session.messages, now_iso(), session.id),
        )
        await self.conn.commit()

    async def delete(self, session_id: str) -> None:
        async with self.conn.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Chat session not found: {session_id}")
        await self.conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        await self.conn.commit()

    async def delete_all_for_agent(self, agent_name: str) -> int:
        """Delete every chat session for an agent (interactive AND
        connector-keyed) and return the number of rows removed.

        Name-keyed (agents have no id column; agents.name is the PK).
        Idempotent: returns 0 for an agent with no sessions and never
        raises for a missing agent — the FK was dropped at schema v5,
        so this neither cascades nor is blocked. Rename-safe because
        rename() re-points chat_sessions.agent_name in one transaction.
        """
        async with self.conn.execute(
            "DELETE FROM chat_sessions WHERE agent_name = ?", (agent_name,)
        ) as cur:
            count = cur.rowcount
        await self.conn.commit()
        return count

    async def delete_older_than(self, agent_name: str, cutoff: str) -> list[str]:
        """Delete an agent's chat sessions whose ``updated_at`` predates
        ``cutoff`` and return the ids of the deleted rows.

        Age-filtered, id-returning sibling of :meth:`delete_all_for_agent`
        (M13 F03). Used by the daily purge sweep (Leg 3), which needs the
        ids to evict the matching in-memory ``_sessions`` entries.

        Comparison is LEXICAL on the ISO-8601-UTC ``updated_at`` string —
        sound because ``updated_at`` is always written via ``now_iso()``
        and the active-session resolver already orders lexically on it.
        ``cutoff`` must be a ``now_iso()``-shaped string (the caller builds
        it as ``(now_utc - timedelta(days=N)).isoformat()``).

        Name-keyed and rename-safe for the same reasons as
        :meth:`delete_all_for_agent`. Returns ``[]`` when nothing matches.

        Form: SELECT the ids, then DELETE the same predicate, on the
        serial connection (DD2 — no ``RETURNING``). Not atomic, but safe:
        ``updated_at`` only moves forward, so an interleaving bump can only
        move a captured row OUT of the predicate, never an uncaptured row
        in — the returned ids are always a superset of rows actually
        deleted (no false deletion; at worst a benign spurious eviction
        downstream).
        """
        async with self.conn.execute(
            "SELECT id FROM chat_sessions WHERE agent_name = ? AND updated_at < ?",
            (agent_name, cutoff),
        ) as cur:
            ids = [row[0] for row in await cur.fetchall()]
        if ids:
            await self.conn.execute(
                "DELETE FROM chat_sessions WHERE agent_name = ? AND updated_at < ?",
                (agent_name, cutoff),
            )
            await self.conn.commit()
        return ids

    async def purge_messages(self, session_id: str) -> None:
        """Clear messages for a session but keep the session itself."""
        async with self.conn.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Chat session not found: {session_id}")
        await self.conn.execute(
            "UPDATE chat_sessions SET messages='[]', updated_at=? WHERE id=?",
            (now_iso(), session_id),
        )
        await self.conn.commit()

    async def update_last_inbound(self, session_id: str, when: str) -> None:
        """Bump the connector-driven activity timestamps for a session.

        Touches both ``last_inbound_at`` (consumed by the resolver's
        continuation-window check at
        :func:`the_one.connectors._session.resolve_session`) and
        ``updated_at`` (the most-recent-by-updated_at ordering the
        resolver uses to pick the active row when multiple historical
        rows exist for the same external key).

        Raises ``KeyError`` if the session doesn't exist — mirrors
        :meth:`update` / :meth:`delete` / :meth:`purge_messages`
        not-found semantics.

        M10 F03 L04 — narrow primitive consumed by
        :func:`the_one.connectors._inbound.dispatch_inbound`. The
        seven connector-identity columns are intentionally not touched
        — see :meth:`update`'s docstring for the identity-columns
        contract.
        """
        async with self.conn.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Chat session not found: {session_id}")
        await self.conn.execute(
            "UPDATE chat_sessions SET last_inbound_at = ?, updated_at = ? WHERE id = ?",
            (when, when, session_id),
        )
        await self.conn.commit()

    async def append_to_session_metadata(self, session_id: str, key: str, value: Any) -> None:
        """Append ``value`` to the list at ``session_metadata[key]``.

        Initializes ``session_metadata`` from NULL to ``{}`` and the
        list at ``key`` from absent to ``[]`` as needed. Preserves all
        other top-level keys in ``session_metadata``. The whole column
        is rewritten on each call (last-writer-wins; no deep-merge or
        optimistic concurrency in leg 2 scope).

        Raises ``KeyError`` if the session doesn't exist — mirrors
        :meth:`update_last_inbound` / :meth:`update` / :meth:`delete` /
        :meth:`purge_messages` not-found semantics.

        M10 F06 L2 — narrow primitive for the audit-log writer. F7's
        routing-decision logs will use the same primitive with a
        different key. The audit list is unbounded by design;
        bounded-retention is F10 territory.
        """
        async with self.conn.execute(
            "SELECT session_metadata FROM chat_sessions WHERE id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Chat session not found: {session_id}")
        raw = row["session_metadata"]
        metadata: dict[str, Any] = json.loads(raw) if raw else {}
        if not isinstance(metadata, dict):
            # Defensive: a non-dict JSON value (corruption / tampering)
            # collapses to {} — mirrors ``_row_to_model``'s defensive
            # normalization. The next write replaces the column with a
            # well-formed dict.
            metadata = {}
        existing = metadata.get(key)
        if not isinstance(existing, list):
            existing = []
        existing.append(value)
        metadata[key] = existing
        await self.conn.execute(
            "UPDATE chat_sessions SET session_metadata = ? WHERE id = ?",
            (json.dumps(metadata), session_id),
        )
        await self.conn.commit()

    async def set_session_metadata_key(
        self,
        session_id: str,
        key: str,
        value: Any,
    ) -> None:
        """Set ``session_metadata[key] = value`` (overwrite semantic).

        Sibling primitive to :meth:`append_to_session_metadata`. Where
        :meth:`append_to_session_metadata` accumulates a list under a key
        (F6's ``"audit"`` log + F7's ``"routing"`` log), this primitive
        is for last-writer-wins single-value sets — F7 L6's
        ``routing_override`` key.

        Concurrency posture: last-writer-wins, by design. Two concurrent
        ``/talk-to`` inbounds for the same session land in
        non-deterministic order; the last writer's intent wins silently.
        This is the correct semantic for an override ("most recent
        operator/peer intent wins") and is documented at the call sites
        in F7 L6's command handlers. Inherits the same single-connection
        read-modify-write race :meth:`append_to_session_metadata`
        documents — acceptable for v1 (concurrent inbounds on the same
        session are an uncommon path; F10 hardening can wrap the
        primitive in a transaction).

        Initialises ``session_metadata`` from NULL to ``{}`` as needed.
        Preserves every other top-level key in ``session_metadata``.
        Accepts any JSON-serialisable ``value`` — strings, ints, lists,
        dicts, ``None`` all round-trip via :func:`json.dumps`.

        Raises ``KeyError`` if ``session_id`` doesn't exist — mirrors
        :meth:`append_to_session_metadata` /
        :meth:`update_last_inbound` / :meth:`update` / :meth:`delete` /
        :meth:`purge_messages` not-found semantics.

        M10 F07 L5 — narrow primitive for the F7 L6 ``/talk-to`` handler's
        ``session_metadata["routing_override"]`` write. F7 L4's routing
        engine already reads ``session_metadata.get("routing_override")``
        in Step 1 of the 5-step algorithm; the write side lands here.

        **Known ``session_metadata`` keys (M10 F06):**

        - ``"routing_override"`` — per-session provider/model override set by
          the ``/talk-to`` command handler (F7 L6).
        - ``"last_usage"`` — per-turn token-usage snapshot written by the web
          turn-settle path (``_process_and_broadcast`` non-paused settle and
          ``_resume_paused_session`` resume settle, ``app.py``). Shape:
          ``{"input_tokens": int, "output_tokens": int, "context_tokens": int}``
          where ``context_tokens`` is the last assistant step's ``input_tokens``
          (the overlay's derived context-window fullness value). Written once per
          completed turn; used by the ``session_joined`` restore path to pre-fill
          the telemetry overlay on chat reopen (M10 F06).
        """
        async with self.conn.execute(
            "SELECT session_metadata FROM chat_sessions WHERE id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Chat session not found: {session_id}")
        raw = row["session_metadata"]
        metadata: dict[str, Any] = json.loads(raw) if raw else {}
        if not isinstance(metadata, dict):
            # Defensive: a non-dict JSON value (corruption / tampering)
            # collapses to {} — mirrors :meth:`append_to_session_metadata`
            # and ``_row_to_model``'s defensive normalisation. The next
            # write replaces the column with a well-formed dict.
            metadata = {}
        metadata[key] = value
        await self.conn.execute(
            "UPDATE chat_sessions SET session_metadata = ? WHERE id = ?",
            (json.dumps(metadata), session_id),
        )
        await self.conn.commit()

    @staticmethod
    def _row_to_model(row: aiosqlite.Row) -> ChatSession:
        metadata_raw = row["session_metadata"]
        metadata: dict[str, Any] | None = None
        if metadata_raw is not None:
            try:
                parsed = json.loads(metadata_raw)
                if isinstance(parsed, dict):
                    metadata = parsed
                # Non-dict JSON (e.g. a literal string or list from external
                # tampering) collapses to None — the model annotation requires
                # dict; silently degrading is safer than raising in the read
                # path. F7 is the only intended writer and only writes dicts.
            except json.JSONDecodeError:
                metadata = None
        return ChatSession(
            id=row["id"],
            agent_name=row["agent_name"],
            title=row["title"] or "New chat",
            messages=row["messages"] or "[]",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            platform=row["platform"],
            connector_id=row["connector_id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            peer_id=row["peer_id"],
            session_metadata=metadata,
            last_inbound_at=row["last_inbound_at"],
        )


# ── LLM provider repository ──────────────────────────────────────────────


class LLMProviderRepository:
    """Async CRUD for LLM provider configurations."""

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
        self.conn = conn
        self.encryptor = encryptor

    async def list(self) -> list[LLMProviderConfig]:
        async with self.conn.execute("SELECT * FROM llm_providers ORDER BY name") as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, provider_id: str) -> LLMProviderConfig:
        async with self.conn.execute(
            "SELECT * FROM llm_providers WHERE id = ?", (provider_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Provider not found: {provider_id}")
        return self._row_to_model(row)

    async def create(self, provider: LLMProviderConfig) -> None:
        await self.conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url, api_key, config,"
            " secrets, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            self._to_row(provider),
        )
        await self.conn.commit()

    async def update(self, provider: LLMProviderConfig) -> None:
        if not await self._exists(provider.id):
            raise KeyError(f"Provider not found: {provider.id}")
        await self.conn.execute(
            "UPDATE llm_providers SET name=?, type=?, base_url=?, api_key=?,"
            " config=?, secrets=?, updated_at=? WHERE id=?",
            (
                provider.name,
                provider.type,
                provider.base_url,
                self.encryptor.encrypt_optional(provider.api_key),
                json.dumps(provider.config),
                _encrypt_secrets_blob(self.encryptor, provider.secrets),
                now_iso(),
                provider.id,
            ),
        )
        await self.conn.commit()

    async def update_secrets(self, provider_id: str, secrets: dict[str, Any]) -> None:
        """Replace ONLY the encrypted OAuth-secrets blob for one provider.

        M19 F01 L01 (leg design decision): token persistence after an OAuth
        exchange/refresh goes through this dedicated method — NOT the
        full-model :meth:`update` — so the PUT-preserve contract in the API
        layer and token writes stay independent (a token write can never
        clobber concurrent config edits, and vice versa).
        """
        if not await self._exists(provider_id):
            raise KeyError(f"Provider not found: {provider_id}")
        await self.conn.execute(
            "UPDATE llm_providers SET secrets=?, updated_at=? WHERE id=?",
            (
                _encrypt_secrets_blob(self.encryptor, secrets),
                now_iso(),
                provider_id,
            ),
        )
        await self.conn.commit()

    async def delete(self, provider_id: str) -> None:
        if not await self._exists(provider_id):
            raise KeyError(f"Provider not found: {provider_id}")
        await self.conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
        await self.conn.commit()

    async def _exists(self, provider_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM llm_providers WHERE id = ?", (provider_id,)
        ) as cur:
            return await cur.fetchone() is not None

    def _to_row(self, provider: LLMProviderConfig) -> tuple:
        return (
            provider.id,
            provider.name,
            provider.type,
            provider.base_url,
            self.encryptor.encrypt_optional(provider.api_key),
            json.dumps(provider.config),
            _encrypt_secrets_blob(self.encryptor, provider.secrets),
            provider.created_at,
            provider.updated_at,
        )

    def _row_to_model(self, row: aiosqlite.Row) -> LLMProviderConfig:
        # ``secrets`` uses the shared tolerant decrypt: a v33-migrated row
        # carries the plaintext '{}' column default, which InvalidToken-
        # falls-back to {} until the first real secrets write re-encrypts.
        return LLMProviderConfig(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            base_url=row["base_url"],
            api_key=self.encryptor.decrypt_optional(row["api_key"]),
            config=json.loads(row["config"] or "{}"),
            secrets=_decrypt_secrets_blob(self.encryptor, row["secrets"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── Agent external-credential repository (M21 F03 L01) ────────────────────


class AgentExternalCredentialRepository:
    """Async CRUD for ``agent_external_credentials`` — the external-client
    credential store (M21 F03 L01, DD1/DD2/DD8).

    Each row is one operator-minted grant: a distinct ``ext_`` principal
    scoped to exactly one agent's surface row (``source_id`` FK to
    ``mcp_sources(id) ON DELETE CASCADE`` — surface-disable / agent-delete
    cascade-revoke the grant). Holds an encryptor (mirrors
    :class:`MCPSourceRepository`) because the credential ``secret`` is
    Fernet-encrypted at rest (DD2): only the ``secret`` *component* of the
    ``ext_<identifier>.<secret>`` token is stored, so
    :meth:`load_all` can hand the resolver the plaintext secret it
    ``hmac.compare_digest``-compares — mirroring how
    ``the_one.self_configuration.credentials``'s registry keeps
    ``(source_id, secret)``.

    Secret-free by construction on every read but :meth:`load_all` (the
    startup-reconcile path, which needs the plaintext to rebuild the
    registry): :meth:`list_for_source` and :meth:`get` never SELECT the
    ``secret`` column, so no read path can serialize it (DD2's structural
    projection — build the dict, never the row).
    """

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
        self.conn = conn
        self.encryptor = encryptor  # Reference, NOT copy. install_key() post-rotation
        # must propagate to live repository instances (mirrors MCPSourceRepository).

    async def create(self, *, source_id: str, label: str, identifier: str, secret: str) -> None:
        """Insert one external-credential row. ``secret`` is the plaintext
        secret component of the ``ext_<identifier>.<secret>`` token; it is
        Fernet-encrypted here and never stored in the clear (DD2)."""
        await self.conn.execute(
            "INSERT INTO agent_external_credentials "
            "(identifier, source_id, secret, label, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                identifier,
                source_id,
                self.encryptor.encrypt(secret),
                label,
                now_iso(),
            ),
        )
        await self.conn.commit()

    async def list_for_source(self, source_id: str) -> list[dict[str, Any]]:
        """Return a secret-free projection of every credential scoped to
        *source_id*, newest-first. Never SELECTs the ``secret`` column
        (DD2's structural projection)."""
        async with self.conn.execute(
            "SELECT identifier, label, created_at FROM agent_external_credentials "
            "WHERE source_id = ? ORDER BY created_at DESC, identifier DESC",
            (source_id,),
        ) as cur:
            return [
                {
                    "identifier": row["identifier"],
                    "label": row["label"],
                    "created_at": row["created_at"],
                }
                for row in await cur.fetchall()
            ]

    async def get(self, identifier: str) -> dict[str, Any] | None:
        """Return ``{identifier, source_id, label, created_at}`` for
        *identifier*, or ``None`` if absent. Secret-free — the cross-ID
        guard on revoke/rotate needs only ``source_id``."""
        async with self.conn.execute(
            "SELECT identifier, source_id, label, created_at "
            "FROM agent_external_credentials WHERE identifier = ?",
            (identifier,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return {
            "identifier": row["identifier"],
            "source_id": row["source_id"],
            "label": row["label"],
            "created_at": row["created_at"],
        }

    async def delete(self, identifier: str) -> bool:
        """Hard-delete the row for *identifier*. Returns ``True`` if a row
        was removed, ``False`` if there was nothing to delete (idempotent
        no-op — mirrors the cascade path, which also hard-deletes)."""
        cur = await self.conn.execute(
            "DELETE FROM agent_external_credentials WHERE identifier = ?",
            (identifier,),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def load_all(self) -> list[tuple[str, str, str]]:
        """Return ``(identifier, source_id, secret)`` for every row, with
        the ``secret`` decrypted — the startup-reconcile input that rebuilds
        the in-memory external registry (DD8). This is the ONLY read path
        that touches the secret column, and it never leaves the process."""
        async with self.conn.execute(
            "SELECT identifier, source_id, secret FROM agent_external_credentials"
        ) as cur:
            rows = await cur.fetchall()
        return [
            (row["identifier"], row["source_id"], self.encryptor.decrypt(row["secret"]))
            for row in rows
        ]

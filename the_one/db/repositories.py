"""Async CRUD repositories for all database entities."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

import aiosqlite
from cryptography.fernet import InvalidToken

from the_one.agent.config import AgentConfig
from the_one.db.models import (
    ChatSession,
    ConnectorAccount,
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
# :class:`ConnectorAccountRepository`. The per-repository methods
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


# ── Agent repository ──────────────────────────────────────────────────────


class SQLiteAgentStore:
    """Async agent config store backed by SQLite."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list_agents(self) -> list[str]:
        async with self.conn.execute("SELECT name FROM agents ORDER BY name") as cur:
            return [row[0] for row in await cur.fetchall()]

    async def list_by_provider(self, provider_config_id: str) -> list[str]:
        """Return agent names that reference the given provider config."""
        async with self.conn.execute(
            "SELECT name FROM agents WHERE provider_config_id = ? ORDER BY name",
            (provider_config_id,),
        ) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def list_by_connector_account(self, account_id: str) -> list[AgentConfig]:
        """Return agent configs attached to ``account_id``.

        M10 F7 L3: inverse-query for the routing engine (F7 L4) and the
        dispatcher integration (F7 L5). Returns the list alphabetically
        ordered by ``AgentConfig.name`` (via the SQL ``ORDER BY``).

        ``connector_account_ids`` is a JSON-encoded list column (F4 L5
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
            if account_id in config.connector_account_ids:
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
                connector_account_ids, connector_acls,
                connector_always_listen, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                connector_account_ids=excluded.connector_account_ids,
                connector_acls=excluded.connector_acls,
                connector_always_listen=excluded.connector_always_listen,
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
                json.dumps(config.tool_overrides) if config.tool_overrides is not None else None,
                json.dumps(config.mcp_overrides) if config.mcp_overrides is not None else None,
                json.dumps(config.connector_account_ids),
                json.dumps(config.connector_acls) if config.connector_acls is not None else None,
                json.dumps(config.connector_always_listen) if config.connector_always_listen is not None else None,
                now,
                now,
            ),
        )
        await self.conn.commit()

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

    @staticmethod
    def _row_to_config(row: aiosqlite.Row) -> AgentConfig:
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
            tool_overrides=(json.loads(row["tool_overrides"]) if row["tool_overrides"] else None),
            mcp_overrides=(json.loads(row["mcp_overrides"]) if row["mcp_overrides"] else None),
            # `or "[]"` defends against both NULL (pre-v17 rows persisted
            # before the M10 F4 L5 migration added the column) AND the
            # empty-string edge case. The v17 migration is the gate that
            # guarantees the column exists; this expression handles the
            # NULL value for legacy rows.
            connector_account_ids=json.loads(row["connector_account_ids"] or "[]"),
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


class ConnectorAccountRepository:
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

    async def list(self) -> list[ConnectorAccount]:
        async with self.conn.execute(
            "SELECT * FROM connector_accounts ORDER BY name"
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, account_id: str) -> ConnectorAccount:
        async with self.conn.execute(
            "SELECT * FROM connector_accounts WHERE id = ?", (account_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Connector account not found: {account_id}")
        return self._row_to_model(row)

    async def create(self, account: ConnectorAccount) -> None:
        await self.conn.execute(
            "INSERT INTO connector_accounts"
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

    async def update(self, account: ConnectorAccount) -> None:
        async with self.conn.execute(
            "SELECT 1 FROM connector_accounts WHERE id = ?", (account.id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account.id}")
        await self.conn.execute(
            "UPDATE connector_accounts"
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
        async with self.conn.execute(
            "SELECT 1 FROM connector_accounts WHERE id = ?", (account_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account_id}")
        await self.conn.execute(
            "DELETE FROM connector_accounts WHERE id = ?", (account_id,)
        )
        await self.conn.commit()

    def _row_to_model(self, row: aiosqlite.Row) -> ConnectorAccount:
        return ConnectorAccount(
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
    ``ConnectorAccountRepository`` connection-passing shape sans the
    encryptor argument.

    Dedup contract (cycle-2 architect §2): ``upsert_pending`` enforces
    ONE row per ``(connector_account_id, peer_id, status='pending')``
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
        connector_account_id: str,
        peer_id: str,
        peer_name: str,
        preview: str,
    ) -> PendingApproval:
        """Upsert a pending row keyed by (account, peer, status='pending').

        If a pending row already exists for (account, peer), UPDATE
        ``peer_name``, ``preview``, ``received_at`` in place and return
        the updated row. Otherwise INSERT a fresh row with a new uuid
        and ``status='pending'``.
        """
        async with self.conn.execute(
            "SELECT id FROM pending_approvals "
            "WHERE connector_account_id = ? AND peer_id = ? AND status = 'pending' "
            "LIMIT 1",
            (connector_account_id, peer_id),
        ) as cur:
            existing = await cur.fetchone()
        ts = now_iso()
        if existing is None:
            # 32-char full hex (matches connectors/_session.py:184 — same
            # world: dispatcher-created, web-API-referenced).
            new_id = uuid.uuid4().hex
            await self.conn.execute(
                "INSERT INTO pending_approvals "
                "(id, connector_account_id, peer_id, peer_name, preview, "
                " received_at, status, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)",
                (new_id, connector_account_id, peer_id, peer_name, preview, ts),
            )
            await self.conn.commit()
            return await self.get(new_id)
        approval_id = existing["id"]
        await self.conn.execute(
            "UPDATE pending_approvals "
            "SET peer_name = ?, preview = ?, received_at = ? "
            "WHERE id = ?",
            (peer_name, preview, ts, approval_id),
        )
        await self.conn.commit()
        return await self.get(approval_id)

    async def list_for_account_peer(
        self, account_id: str, peer_id: str
    ) -> list[PendingApproval]:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals "
            "WHERE connector_account_id = ? AND peer_id = ? "
            "ORDER BY received_at ASC",
            (account_id, peer_id),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def list_by_account(self, account_id: str) -> list[PendingApproval]:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals "
            "WHERE connector_account_id = ? "
            "ORDER BY received_at ASC",
            (account_id,),
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
                f"Pending approval {approval_id} is {current.status}; "
                f"cannot transition to {target}"
            )
        await self.conn.execute(
            "UPDATE pending_approvals SET status = ?, resolved_at = ? "
            "WHERE id = ?",
            (target, now_iso(), approval_id),
        )
        await self.conn.commit()
        return await self.get(approval_id)

    def _row_to_model(self, row: aiosqlite.Row) -> PendingApproval:
        return PendingApproval(
            id=row["id"],
            connector_account_id=row["connector_account_id"],
            peer_id=row["peer_id"],
            peer_name=row["peer_name"],
            preview=row["preview"],
            received_at=row["received_at"],
            status=row["status"],
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
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

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

    async def upsert(self, name: str, config: dict, enabled: bool = True) -> None:
        """INSERT or REPLACE the config row, bumping `updated_at` on update.

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
        await self.conn.execute(
            """\
            INSERT INTO tool_configs (name, config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                config=excluded.config,
                enabled=excluded.enabled,
                updated_at=excluded.updated_at
            """,
            (name, json.dumps(config), int(enabled), now_iso(), now_iso()),
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

    @staticmethod
    def _row_to_model(row: aiosqlite.Row) -> ToolConfig:
        return ToolConfig(
            name=row["name"],
            config=json.loads(row["config"] or "{}"),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


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
        connector_account_id: str,
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
            " WHERE platform = ? AND connector_account_id = ?"
            " AND channel_id = ? AND COALESCE(thread_id, '') = COALESCE(?, '')"
            " ORDER BY updated_at DESC LIMIT 1",
            (platform, connector_account_id, channel_id, thread_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return self._row_to_model(row)

    async def create(self, session: ChatSession) -> None:
        await self.conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at,"
            " platform, connector_account_id, channel_id, thread_id, peer_id,"
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
                session.connector_account_id,
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
        connector_account_id, channel_id, thread_id, peer_id,
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

    async def append_to_session_metadata(
        self, session_id: str, key: str, value: Any
    ) -> None:
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
            connector_account_id=row["connector_account_id"],
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
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            self._to_row(provider),
        )
        await self.conn.commit()

    async def update(self, provider: LLMProviderConfig) -> None:
        if not await self._exists(provider.id):
            raise KeyError(f"Provider not found: {provider.id}")
        await self.conn.execute(
            "UPDATE llm_providers SET name=?, type=?, base_url=?, api_key=?,"
            " config=?, updated_at=? WHERE id=?",
            (
                provider.name,
                provider.type,
                provider.base_url,
                self.encryptor.encrypt_optional(provider.api_key),
                json.dumps(provider.config),
                now_iso(),
                provider.id,
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
            provider.created_at,
            provider.updated_at,
        )

    def _row_to_model(self, row: aiosqlite.Row) -> LLMProviderConfig:
        return LLMProviderConfig(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            base_url=row["base_url"],
            api_key=self.encryptor.decrypt_optional(row["api_key"]),
            config=json.loads(row["config"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

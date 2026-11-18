"""Async CRUD repositories for all database entities."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass
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
from the_one.db._kb_types import (
    KB_ITEM_STATUSES,
    KB_ITEM_TRANSITIONS,
    ChunkRecord,
    KBItemTransitionError,
)
from the_one.db._notes import (
    NOTES_TOTAL_MAX_CHARS,
    SOURCES_CAP,
    NoteDuplicateError,
    NotesDisabledError,
    dedup_key,
    validate_note_text,
)
from the_one.db._notes import (
    total_limit_error as notes_total_limit_error,
)
from the_one.db._rules import (
    RULES_TOTAL_MAX_CHARS,
    RuleOrderError,
    total_limit_error,
    validate_rule_text,
)
from the_one.db._session_changes import notify_sessions_changed
from the_one.db._write_lock import write_transaction
from the_one.db.models import (
    AgentNote,
    AgentRevision,
    AgentRule,
    ChatSession,
    Connector,
    ConnectorDirectoryEntry,
    KBChunk,
    KBItem,
    KnowledgeBase,
    LLMProviderConfig,
    MCPSource,
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

    async def list_by_kb(self, kb_id: str) -> list[str]:
        """Return agent names whose ``kb_ids`` contains ``kb_id`` (L2-D6).

        ``agents.kb_ids`` is a JSON TEXT column (``schema.py:58``, ``:169``),
        so this does NOT transfer :meth:`list_by_provider`'s plain column
        equality — a ``json_each`` membership test is required. ``LIKE
        '%<id>%'`` is deliberately NOT used: it would match an id that is
        merely a *substring* of another agent's attached id.

        Guards the column the same way :meth:`_row_to_config` already does
        (``row["kb_ids"] or "[]"``): measured on this host's SQLite
        (3.45.1), ``json_each(NULL)`` yields zero rows (safe) but
        ``json_each('')`` raises ``OperationalError: malformed JSON``. The
        schema puts no ``NOT NULL`` on ``kb_ids``, so the empty/NULL state
        is treated as reachable, not impossible.
        """
        async with self.conn.execute(
            """\
            SELECT name FROM agents
            WHERE kb_ids IS NOT NULL AND kb_ids != ''
              AND EXISTS (
                  SELECT 1 FROM json_each(agents.kb_ids) WHERE json_each.value = ?
              )
            ORDER BY name
            """,
            (kb_id,),
        ) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def list_by_secret(self, secret_id: str) -> list[str]:
        """Return agent names whose ``secret_ids`` contains ``secret_id``.

        Same ``json_each`` membership test and NULL/empty guard as :meth:`list_by_kb`.
        """
        async with self.conn.execute(
            """\
            SELECT name FROM agents
            WHERE secret_ids IS NOT NULL AND secret_ids != ''
              AND EXISTS (
                  SELECT 1 FROM json_each(agents.secret_ids) WHERE json_each.value = ?
              )
            ORDER BY name
            """,
            (secret_id,),
        ) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def list_by_mcp_source(self, source_id: str) -> list[str]:
        """Return agent names whose ``mcp_source_ids`` contains ``source_id``.

        Same ``json_each`` membership test and NULL/empty guard as
        :meth:`list_by_kb`; an id that is a substring of another does not match.
        """
        async with self.conn.execute(
            """\
            SELECT name FROM agents
            WHERE mcp_source_ids IS NOT NULL AND mcp_source_ids != ''
              AND EXISTS (
                  SELECT 1 FROM json_each(agents.mcp_source_ids) WHERE json_each.value = ?
              )
            ORDER BY name
            """,
            (source_id,),
        ) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def load(self, name: str) -> AgentConfig:
        async with self.conn.execute("SELECT * FROM agents WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Agent config not found: {name}")
        return self._row_to_config(row)

    async def save(self, config: AgentConfig) -> None:
        now = now_iso()
        async with write_transaction(self.conn):
            await self.conn.execute(
                """\
                INSERT INTO agents (
                    name, description, provider_config_id, llm_model,
                    system_prompt, enabled_tools, disabled_tools, max_iterations,
                    kb_ids, mcp_source_ids, tool_overrides, mcp_overrides,
                    chat_history_retention_days,
                    self_revision_requires_approval,
                    notes_enabled,
                    routines_require_approval,
                    secret_ids,
                    rich_visuals,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    chat_history_retention_days=excluded.chat_history_retention_days,
                    self_revision_requires_approval=excluded.self_revision_requires_approval,
                    notes_enabled=excluded.notes_enabled,
                    secret_ids=excluded.secret_ids,
                    rich_visuals=excluded.rich_visuals,
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
                    config.chat_history_retention_days,
                    int(config.self_revision_requires_approval),
                    int(config.notes_enabled),
                    int(config.routines_require_approval),
                    json.dumps(config.secret_ids),
                    int(config.rich_visuals),
                    now,
                    now,
                ),
            )

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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agents SET self_revision_requires_approval = ?, "
                "updated_at = ? WHERE name = ?",
                (int(value), now_iso(), name),
            )

    async def set_notes_enabled(self, name: str, value: bool) -> None:
        """Targeted UPDATE of the operator-owned notes switch (M27 F2, DD2).

        Mirrors :meth:`set_self_revision_requires_approval`. Raises
        ``KeyError`` if no agent exists at ``name``.
        """
        if not await self.exists(name):
            raise KeyError(f"Agent config not found: {name}")
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agents SET notes_enabled = ?, updated_at = ? WHERE name = ?",
                (int(value), now_iso(), name),
            )

    async def set_routines_self_config(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        requires_approval: bool | None = None,
    ) -> None:
        """Targeted UPDATE of the operator-owned Routines switches (M33 F2, DD5).

        Sets only the fields given. Raises ``KeyError`` if no agent exists at ``name``.
        """
        if not await self.exists(name):
            raise KeyError(f"Agent config not found: {name}")
        sets: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            sets.append("routines_self_config_enabled = ?")
            params.append(int(enabled))
        if requires_approval is not None:
            sets.append("routines_require_approval = ?")
            params.append(int(requires_approval))
        if not sets:
            return
        async with write_transaction(self.conn):
            await self.conn.execute(
                f"UPDATE agents SET {', '.join(sets)}, updated_at = ? WHERE name = ?",
                (*params, now_iso(), name),
            )

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
        async with write_transaction(self.conn):
            async with self.conn.execute(
                f"UPDATE agents SET {field} = ?, updated_at = ? WHERE name = ? AND {field} = ?",
                (new_value, now_iso(), name, base_value),
            ) as cur:
                rowcount = cur.rowcount
        return rowcount == 1

    async def delete(self, name: str) -> None:
        if not await self.exists(name):
            raise KeyError(f"Agent config not found: {name}")
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM agents WHERE name = ?", (name,))

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

        The same transaction rewrites the connector bindings that name the
        agent: every ``connectors.config.default_agent`` and every
        ``channel_map`` value equal to ``old_name`` becomes ``new_name`` (a
        rewritten connector gets a fresh ``updated_at``; a connector whose
        config is malformed is skipped with a WARNING).

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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agents SET name = ?, updated_at = ? WHERE name = ?",
                (new_name, now, old_name),
            )
            await self.conn.execute(
                "UPDATE chat_sessions SET agent_name = ? WHERE agent_name = ?",
                (new_name, old_name),
            )
            async with self.conn.execute("SELECT id, config FROM connectors") as cur:
                connector_rows = await cur.fetchall()
            for row in connector_rows:
                try:
                    config = _parse_connector_binding_config(row["config"])
                except (ValueError, TypeError, AttributeError):
                    _conn_logger.warning(
                        "Skipping malformed connector row %r", row["id"], exc_info=True
                    )
                    continue
                channel_map = config.get("channel_map") or {}
                changed = config.get("default_agent") == old_name
                if changed:
                    config["default_agent"] = new_name
                if old_name in channel_map.values():
                    config["channel_map"] = {
                        k: (new_name if v == old_name else v) for k, v in channel_map.items()
                    }
                    changed = True
                if changed:
                    await self.conn.execute(
                        "UPDATE connectors SET config = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(config), now, row["id"]),
                    )
        notify_sessions_changed()

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
            secret_ids=json.loads(row["secret_ids"] or "[]"),
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
            chat_history_retention_days=row["chat_history_retention_days"],
            # M21 F02 L02: per-agent approval mode. Plain read mirroring
            # `chat_history_retention_days` above — the v35 migration adds the
            # column `NOT NULL DEFAULT 0` and backfills every row, so no
            # absent/NULL case survives at load (an inline missing-column
            # access on `aiosqlite.Row` would raise IndexError anyway).
            self_revision_requires_approval=bool(row["self_revision_requires_approval"]),
            # M27 F2: the notes switch (v43 `NOT NULL DEFAULT 0`). The counter
            # `notes_next_number` is deliberately never read here.
            notes_enabled=bool(row["notes_enabled"]),
            rich_visuals=bool(row["rich_visuals"]),
            routines_self_config_enabled=bool(row["routines_self_config_enabled"]),
            routines_require_approval=bool(row["routines_require_approval"]),
        )


# ── FTS5 sync helper (Flight 2 Leg 2, DD-5) ──────────────────────────────


async def _fts_delete_rows(conn: aiosqlite.Connection, rows: Sequence[tuple[int, str]]) -> None:
    """Issue the external-content FTS5 ``'delete'`` command for each row.

    ``rows`` is ``(rowid, text)`` pairs — external-content FTS5 needs the
    *original* indexed text to remove a row from the shadow index, so every
    caller MUST ``SELECT id, text FROM kb_chunks WHERE ...`` **before**
    issuing the matching ``DELETE FROM kb_chunks``. This is the ONLY site
    that issues FTS delete commands — ``KBChunkRepository.replace_item_chunks``
    / ``delete_for_item`` / ``delete_for_kb`` and the cascade hooks in
    ``KnowledgeBaseRepository.delete`` / ``KBItemRepository.delete`` all
    call through here rather than building the command inline.

    Callers must hold the write lock (call this from inside a
    ``write_transaction`` block) — it issues no commit/rollback of its own.
    A no-op for an empty ``rows``.
    """
    if not rows:
        return
    await conn.executemany(
        "INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, text) VALUES ('delete', ?, ?)",
        rows,
    )


# ── Knowledge base repository ────────────────────────────────────────────


class KnowledgeBaseRepository:
    """Async CRUD for knowledge bases."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list(self) -> list[KnowledgeBase]:
        async with self.conn.execute("SELECT * FROM knowledge_bases ORDER BY name") as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def count(self) -> int:
        """Total knowledge base count — the embedding warm-up gate
        (M24 F02 L03, DD-1): an operator who never creates a KB never pays
        the model load at startup.
        """
        async with self.conn.execute("SELECT count(*) FROM knowledge_bases") as cur:
            row = await cur.fetchone()
        return row[0] if row is not None else 0

    async def get(self, kb_id: str) -> KnowledgeBase:
        async with self.conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Knowledge base not found: {kb_id}")
        return self._row_to_model(row)

    async def create(self, kb: KnowledgeBase) -> None:
        async with write_transaction(self.conn):
            await self.conn.execute(
                "INSERT INTO knowledge_bases (id, name, description, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (kb.id, kb.name, kb.description, kb.created_at, kb.updated_at),
            )

    async def update(self, kb: KnowledgeBase) -> None:
        if not await self._exists(kb.id):
            raise KeyError(f"Knowledge base not found: {kb.id}")
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE knowledge_bases SET name=?, description=?, updated_at=? WHERE id=?",
                (kb.name, kb.description, now_iso(), kb.id),
            )

    async def delete(self, kb_id: str) -> None:
        """Delete a knowledge base and, via FK cascade, its items and chunks.

        Flight 2 Leg 2: the FK cascade reaches ``kb_items`` and ``kb_chunks``
        but NOT the ``kb_chunks_fts`` shadow table, so before the delete this
        selects the about-to-be-cascaded chunks' ``(id, text)`` and issues
        their FTS deletes via the module-level ``_fts_delete_rows`` helper —
        inside this SAME ``write_transaction``, never by calling into
        ``KBChunkRepository`` (which opens its own transaction and would
        raise on same-task re-entry).
        """
        if not await self._exists(kb_id):
            raise KeyError(f"Knowledge base not found: {kb_id}")
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT id, text FROM kb_chunks WHERE kb_id = ?", (kb_id,)
            ) as cur:
                chunk_rows = [(row[0], row[1]) for row in await cur.fetchall()]
            await _fts_delete_rows(self.conn, chunk_rows)
            await self.conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))

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
    """Async CRUD for knowledge base items, plus the v40 lifecycle surface
    (Flight 2 Leg 1, DD-5): :meth:`update_status` enforces
    ``KB_ITEM_TRANSITIONS`` as one conditional ``UPDATE`` (no read-then-write
    TOCTOU window), :meth:`set_content_identity` records the dedup identity
    a re-index compares against, and :meth:`list_by_status` /
    :meth:`count_by_status` are the per-KB progress projections.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def list(self, kb_id: str) -> list[KBItem]:
        """Squawk 0087: ``, path_or_url`` is a tiebreak on tied
        ``created_at`` rows (a folder walk inserts every discovered file in
        one pass, so ties are the common case, not the exotic one) —
        ascending, matching the order ``walk_folder`` discovers files in
        (``walk.py``'s own ``files.sort(key=lambda f: f.path)``)."""
        async with self.conn.execute(
            "SELECT * FROM kb_items WHERE kb_id = ? ORDER BY created_at, path_or_url", (kb_id,)
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def get(self, item_id: str) -> KBItem:
        async with self.conn.execute("SELECT * FROM kb_items WHERE id = ?", (item_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"KB item not found: {item_id}")
        return self._row_to_model(row)

    async def create(self, item: KBItem) -> None:
        async with write_transaction(self.conn):
            await self.conn.execute(
                "INSERT INTO kb_items ("
                "    id, kb_id, parent_id, type, path_or_url, status, error,"
                "    content_hash, size_bytes, mtime, created_at, updated_at, indexed_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.kb_id,
                    item.parent_id,
                    item.type,
                    item.path_or_url,
                    item.status,
                    item.error,
                    item.content_hash,
                    item.size_bytes,
                    item.mtime,
                    item.created_at,
                    item.updated_at,
                    item.indexed_at,
                ),
            )

    async def delete(self, item_id: str) -> list[int]:
        """Delete an item and, via FK cascade, its chunks (and, for a
        ``folder`` item, its children's chunks too). Returns every removed
        chunk id.

        Flight 2 Leg 2 / Flight 3 Leg 1 (DD-2): same shape as
        ``KnowledgeBaseRepository.delete`` — select the about-to-be-cascaded
        chunks' ``(id, text)``, issue their FTS deletes via
        ``_fts_delete_rows`` inside this same ``write_transaction``, then
        delete the item. FK cascade (``kb_items.parent_id ... ON DELETE
        CASCADE``, then ``kb_chunks.item_id ... ON DELETE CASCADE``) removes
        any children and all the chunks — the item's own and every child's —
        after the FTS rows for all of them are already gone, so a folder
        delete can never desync ``kb_chunks_fts`` the way a select scoped to
        only ``item_id`` would.
        """
        async with self.conn.execute("SELECT 1 FROM kb_items WHERE id = ?", (item_id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"KB item not found: {item_id}")
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT id, text FROM kb_chunks WHERE item_id = ? "
                "OR item_id IN (SELECT id FROM kb_items WHERE parent_id = ?)",
                (item_id, item_id),
            ) as cur:
                chunk_rows = [(row[0], row[1]) for row in await cur.fetchall()]
            await _fts_delete_rows(self.conn, chunk_rows)
            await self.conn.execute("DELETE FROM kb_items WHERE id = ?", (item_id,))
        return [row[0] for row in chunk_rows]

    async def create_many(self, items: Sequence[KBItem]) -> None:
        """Bulk-insert ``items`` in one ``write_transaction`` via
        ``executemany`` — the same 13-column statement as :meth:`create`.
        A no-op for an empty ``items``. A duplicate id inside the batch
        raises ``sqlite3.IntegrityError``; the ``write_transaction`` guard
        rolls back the whole batch on any exception, so none of it lands.
        """
        if not items:
            return
        async with write_transaction(self.conn):
            await self.conn.executemany(
                "INSERT INTO kb_items ("
                "    id, kb_id, parent_id, type, path_or_url, status, error,"
                "    content_hash, size_bytes, mtime, created_at, updated_at, indexed_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        item.id,
                        item.kb_id,
                        item.parent_id,
                        item.type,
                        item.path_or_url,
                        item.status,
                        item.error,
                        item.content_hash,
                        item.size_bytes,
                        item.mtime,
                        item.created_at,
                        item.updated_at,
                        item.indexed_at,
                    )
                    for item in items
                ],
            )

    async def list_children(self, folder_item_id: str) -> list[KBItem]:
        """Items whose ``parent_id`` equals ``folder_item_id``, oldest
        first. ``[]`` for an unknown id (no existence check — an unknown
        parent simply has no children). Squawk 0087: ``, path_or_url``
        tiebreak, same rationale as :meth:`list`."""
        async with self.conn.execute(
            "SELECT * FROM kb_items WHERE parent_id = ? ORDER BY created_at, path_or_url",
            (folder_item_id,),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def list_folders(self, kb_id: str) -> list[KBItem]:
        """``kb_id``'s ``folder`` items, oldest first. Squawk 0087:
        ``, path_or_url`` tiebreak, same rationale as :meth:`list`."""
        async with self.conn.execute(
            "SELECT * FROM kb_items WHERE kb_id = ? AND type = 'folder' "
            "ORDER BY created_at, path_or_url",
            (kb_id,),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def requeue_stranded(self, kb_id: str | None = None) -> int:
        """Move every ``indexing`` item (any type) back to ``pending``,
        scoped to ``kb_id`` when given. Clears ``error``, stamps
        ``updated_at``, returns the row count.

        The resume-not-restart primitive (Flight 3 DD-7): a worker killed
        or crashed mid-item leaves rows stranded at ``indexing``; the next
        pass (or startup) requeues them in one conditional ``UPDATE``. The
        assertion below pins the bulk ``UPDATE``'s hardcoded ``'indexing'``
        / ``'pending'`` literals to ``KB_ITEM_TRANSITIONS`` so a future
        change to that table cannot silently desync from this method.
        """
        assert "indexing" in KB_ITEM_TRANSITIONS["pending"], (
            "requeue_stranded's bulk UPDATE assumes indexing->pending is a "
            "legal transition — KB_ITEM_TRANSITIONS drifted"
        )
        sql = (
            "UPDATE kb_items SET status = 'pending', error = NULL, updated_at = ? "
            "WHERE status = 'indexing'"
        )
        params: list[Any] = [now_iso()]
        if kb_id is not None:
            sql += " AND kb_id = ?"
            params.append(kb_id)
        async with write_transaction(self.conn):
            async with self.conn.execute(sql, params) as cur:
                rowcount = cur.rowcount
        return rowcount

    async def requeue_for_reindex(self, kb_id: str) -> int:
        """Move ``kb_id``'s ``indexed``/``failed`` **``file``** items back to
        ``pending``. Leaves ``indexing`` items, ``folder`` items and other
        KBs untouched. Clears ``error``, returns the row count.

        Both source statuses' transition into ``pending`` are asserted
        against ``KB_ITEM_TRANSITIONS`` for the same reason as
        :meth:`requeue_stranded`.
        """
        assert "indexed" in KB_ITEM_TRANSITIONS["pending"], (
            "requeue_for_reindex's bulk UPDATE assumes indexed->pending is a "
            "legal transition — KB_ITEM_TRANSITIONS drifted"
        )
        assert "failed" in KB_ITEM_TRANSITIONS["pending"], (
            "requeue_for_reindex's bulk UPDATE assumes failed->pending is a "
            "legal transition — KB_ITEM_TRANSITIONS drifted"
        )
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "UPDATE kb_items SET status = 'pending', error = NULL, updated_at = ? "
                "WHERE kb_id = ? AND type = 'file' AND status IN ('indexed', 'failed')",
                (now_iso(), kb_id),
            ) as cur:
                rowcount = cur.rowcount
        return rowcount

    async def update_status(self, item_id: str, status: str, *, error: str | None = None) -> KBItem:
        """Move ``item_id`` to ``status`` as one conditional ``UPDATE``.

        Raises ``ValueError`` immediately for a ``status`` outside
        ``KB_ITEM_TRANSITIONS`` (never let the dict lookup's ``KeyError``
        masquerade as "item not found"). The ``UPDATE`` is scoped to
        ``WHERE id = ? AND status IN (<allowed predecessors>)`` — a
        check-and-set with no read-then-write TOCTOU window. ``rowcount ==
        0`` means either a missing item or an invalid transition,
        distinguished by one follow-up ``SELECT`` (outside the write lock —
        reads need no lock). ``error`` is stored only when transitioning
        INTO ``failed`` and cleared (set to NULL) on every other
        transition. Reaching ``indexed`` stamps ``indexed_at``; every
        transition stamps ``updated_at`` — both bound from the SAME
        ``now_iso()`` call so the two stamps are identical on the
        transition into ``indexed``.
        """
        if status not in KB_ITEM_TRANSITIONS:
            raise ValueError(f"Unknown KB item status: {status!r}")
        allowed = KB_ITEM_TRANSITIONS[status]
        placeholders = ", ".join("?" for _ in allowed)
        now = now_iso()
        stored_error = error if status == "failed" else None
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "UPDATE kb_items SET status = ?, error = ?, updated_at = ?, "
                "indexed_at = CASE WHEN ? = 'indexed' THEN ? ELSE indexed_at END "
                f"WHERE id = ? AND status IN ({placeholders})",
                (status, stored_error, now, status, now, item_id, *allowed),
            ) as cur:
                rowcount = cur.rowcount
        if rowcount == 0:
            async with self.conn.execute(
                "SELECT status FROM kb_items WHERE id = ?", (item_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                raise KeyError(f"KB item not found: {item_id}")
            raise KBItemTransitionError(f"{row['status']}→{status}")
        return await self.get(item_id)

    async def set_content_identity(
        self, item_id: str, *, content_hash: str, size_bytes: int, mtime: float
    ) -> None:
        """One UPDATE stamping the dedup identity columns + ``updated_at``."""
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE kb_items SET content_hash = ?, size_bytes = ?, mtime = ?, "
                "updated_at = ? WHERE id = ?",
                (content_hash, size_bytes, mtime, now_iso(), item_id),
            )

    async def list_by_status(
        self,
        kb_id: str,
        status: str,
        *,
        limit: int | None = None,
        type: str | None = None,
    ) -> list[KBItem]:
        """Items in ``kb_id`` at ``status``, oldest first. Uses the
        ``(kb_id, status)`` index. Additive keywords, byte-for-byte the old
        behaviour when omitted: ``type`` filters to that item type (the
        worker drains ``type="file"`` only), ``limit`` caps the page."""
        sql = "SELECT * FROM kb_items WHERE kb_id = ? AND status = ?"
        params: list[Any] = [kb_id, status]
        if type is not None:
            sql += " AND type = ?"
            params.append(type)
        sql += " ORDER BY created_at, path_or_url"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        async with self.conn.execute(sql, params) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def latest_indexed_at(self, kb_id: str, *, type: str | None = None) -> str | None:
        """``MAX(indexed_at)`` across ``kb_id``'s items, optionally scoped
        to ``type``. ``None`` when no matching item has ever reached
        ``indexed``.

        DD-6/AC-2/AC-3 (Flight 7 Leg 2): scoped to ``type="file"``, this is
        the inventory's content-freshness aggregate — it advances **iff** a
        file item actually re-indexes, because ``indexed_at`` is stamped
        only by :meth:`update_status`'s transition into ``"indexed"``
        (never on a no-op pass). This is the opposite of a **folder**
        item's ``indexed_at``, which ``manager.py``'s ``_walk_one_folder``
        stamps unconditionally on every completed walk — using that signal
        here would make the aggregate advance every poll on a quiet
        corpus, which is exactly what AC-5 forbids. One indexed query
        (``idx_kb_items_kb_id``), not a scan.
        """
        sql = "SELECT MAX(indexed_at) FROM kb_items WHERE kb_id = ?"
        params: list[Any] = [kb_id]
        if type is not None:
            sql += " AND type = ?"
            params.append(type)
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        return row[0] if row is not None else None

    async def count_by_status(self, kb_id: str, *, type: str | None = None) -> dict[str, int]:
        """Per-status item counts for ``kb_id`` — every status in
        ``KB_ITEM_STATUSES`` present, zeros included for statuses with no
        rows. ``type`` (additive keyword) filters to that item type (DD-8
        counts ``file`` items only)."""
        counts = {status: 0 for status in KB_ITEM_STATUSES}
        sql = "SELECT status, COUNT(*) FROM kb_items WHERE kb_id = ?"
        params: list[Any] = [kb_id]
        if type is not None:
            sql += " AND type = ?"
            params.append(type)
        sql += " GROUP BY status"
        async with self.conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        for row in rows:
            counts[row[0]] = row[1]
        return counts

    @staticmethod
    def _row_to_model(row: aiosqlite.Row) -> KBItem:
        return KBItem(
            id=row["id"],
            kb_id=row["kb_id"],
            parent_id=row["parent_id"],
            type=row["type"],
            path_or_url=row["path_or_url"],
            status=row["status"],
            error=row["error"],
            content_hash=row["content_hash"],
            size_bytes=row["size_bytes"],
            mtime=row["mtime"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            indexed_at=row["indexed_at"],
        )


# ── KB chunk repository (Flight 2 Leg 2, DD-5/DD-12) ─────────────────────

# ``kb_chunks`` rows fetched in batches of this size to build a ``WHERE id
# IN (…)`` clause — ``SQLITE_MAX_VARIABLE_NUMBER`` varies by build (32,766
# is the SQLite default since 3.32; the exact figure is not relied upon),
# so ``get_many`` always chunks the placeholder list regardless of host.
_GET_MANY_BATCH_SIZE = 500

# Squawk 0054: ceiling for ``search_keyword``'s ``k``. Flight 5 exposes this
# path to an agent-controlled tool argument, where an unbounded ``k`` is a
# resource-exhaustion vector (an unreasonably large ``LIMIT`` still forces
# SQLite to materialise/sort that many FTS matches). 1000 is generously above
# any realistic result-set size a caller would ever consume.
MAX_SEARCH_K = 1000


class KBChunkRepository:
    """Async CRUD for ``kb_chunks`` plus the ``kb_chunks_fts`` keyword-search,
    rebuild, and integrity-check primitives.

    ``kb_chunks_fts`` is an external-content FTS5 index over ``kb_chunks``
    (content_rowid='id') — this repository is the ONLY writer of the FTS
    shadow table (the ``db-writes-hold-the-write-lock`` convention's
    FTS-specific corollary; see ``the_one/agents.md``'s "Knowledge storage"
    subsystem contract). Every FTS delete goes through the module-level
    ``_fts_delete_rows`` helper so the ``'delete'`` command shape lives in
    exactly one place.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def replace_item_chunks(
        self, item_id: str, kb_id: str, chunks: Sequence[ChunkRecord]
    ) -> list[int]:
        """Atomically replace every chunk belonging to ``item_id``.

        One ``write_transaction``: select the existing rows' ``(id, text)``,
        FTS-delete them, ``DELETE`` the rows, then insert ``chunks`` in
        ``seq`` order (collecting each ``cur.lastrowid`` — never
        ``RETURNING``, since the frozen CPython bundle's SQLite version is
        not pinned by this project) and sync the new rows into the FTS
        index. Any exception anywhere in this sequence rolls the whole
        transaction back via the guard, so a failure mid-insert (e.g. a
        duplicate ``seq`` violating ``UNIQUE(item_id, seq)``) leaves the
        previous chunks and their FTS rows exactly as they were.

        An empty ``chunks`` deletes the existing rows and returns ``[]`` —
        a zero-length extraction is a valid re-index result.
        """
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT id, text FROM kb_chunks WHERE item_id = ?", (item_id,)
            ) as cur:
                old_rows = [(row[0], row[1]) for row in await cur.fetchall()]
            await _fts_delete_rows(self.conn, old_rows)
            await self.conn.execute("DELETE FROM kb_chunks WHERE item_id = ?", (item_id,))

            ids: list[int] = []
            texts: list[str] = []
            for chunk in chunks:
                async with self.conn.execute(
                    "INSERT INTO kb_chunks (item_id, kb_id, seq, text, char_start, char_end) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (item_id, kb_id, chunk.seq, chunk.text, chunk.char_start, chunk.char_end),
                ) as cur:
                    ids.append(cur.lastrowid)
                texts.append(chunk.text)

            if ids:
                await self.conn.executemany(
                    "INSERT INTO kb_chunks_fts(rowid, text) VALUES (?, ?)",
                    list(zip(ids, texts, strict=True)),
                )
        return ids

    async def delete_for_item(self, item_id: str) -> list[int]:
        """Delete every chunk belonging to ``item_id`` (and its FTS rows).
        Returns the removed chunk ids."""
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT id, text FROM kb_chunks WHERE item_id = ?", (item_id,)
            ) as cur:
                rows = [(row[0], row[1]) for row in await cur.fetchall()]
            await _fts_delete_rows(self.conn, rows)
            await self.conn.execute("DELETE FROM kb_chunks WHERE item_id = ?", (item_id,))
        return [row[0] for row in rows]

    async def delete_for_kb(self, kb_id: str) -> list[int]:
        """Delete every chunk belonging to ``kb_id`` (and its FTS rows).
        Returns the removed chunk ids."""
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT id, text FROM kb_chunks WHERE kb_id = ?", (kb_id,)
            ) as cur:
                rows = [(row[0], row[1]) for row in await cur.fetchall()]
            await _fts_delete_rows(self.conn, rows)
            await self.conn.execute("DELETE FROM kb_chunks WHERE kb_id = ?", (kb_id,))
        return [row[0] for row in rows]

    async def list_for_item(
        self, item_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[KBChunk]:
        """Chunks of ``item_id`` in ``seq`` order. Unchanged when called
        positionally (just ``item_id``). ``limit``/``offset`` page the
        result — SQLite requires a ``LIMIT`` for ``OFFSET``, so an
        ``offset`` with no ``limit`` uses ``LIMIT -1`` (SQLite's
        unbounded-limit sentinel)."""
        sql = "SELECT * FROM kb_chunks WHERE item_id = ? ORDER BY seq"
        params: list[Any] = [item_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        async with self.conn.execute(sql, params) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def ids_for_item(self, item_id: str) -> list[int]:
        """Chunk ids of ``item_id`` in ``seq`` order — never selects
        ``text`` (a large file's chunk count must not force materialising
        its text just to delete the matching vectors)."""
        async with self.conn.execute(
            "SELECT id FROM kb_chunks WHERE item_id = ? ORDER BY seq", (item_id,)
        ) as cur:
            return [row[0] for row in await cur.fetchall()]

    async def iter_for_kb(self, kb_id: str, batch_size: int = 1000) -> AsyncIterator[list[KBChunk]]:
        """Async-iterate ``kb_id``'s chunks in ascending ``id`` order via
        keyset pagination (``WHERE kb_id = ? AND id > ? ORDER BY id LIMIT
        ?``) — DD-6's rebuild stream. Yields nothing for an empty KB. Holds
        no transaction between pages: a chunk inserted mid-iteration with a
        higher id is seen by a later page; one deleted is simply absent —
        the caller (the rebuild) tolerates both.
        """
        last_id = 0
        while True:
            async with self.conn.execute(
                "SELECT * FROM kb_chunks WHERE kb_id = ? AND id > ? ORDER BY id LIMIT ?",
                (kb_id, last_id, batch_size),
            ) as cur:
                rows = await cur.fetchall()
            if not rows:
                return
            page = [self._row_to_model(r) for r in rows]
            yield page
            if len(page) < batch_size:
                return
            last_id = page[-1].id

    async def get_many(self, ids: Sequence[int]) -> list[KBChunk]:
        """Fetch chunks by id, preserving ``ids``'s order (not SQL's).

        Batches the ``IN (…)`` clause at ``_GET_MANY_BATCH_SIZE`` regardless
        of host — ``SQLITE_MAX_VARIABLE_NUMBER`` varies by build. Returns
        ``[]`` for an empty ``ids`` without issuing a query (``IN ()`` is a
        syntax error).
        """
        if not ids:
            return []
        by_id: dict[int, KBChunk] = {}
        id_list = list(ids)
        for start in range(0, len(id_list), _GET_MANY_BATCH_SIZE):
            batch = id_list[start : start + _GET_MANY_BATCH_SIZE]
            placeholders = ", ".join("?" for _ in batch)
            async with self.conn.execute(
                f"SELECT * FROM kb_chunks WHERE id IN ({placeholders})", batch
            ) as cur:
                for row in await cur.fetchall():
                    model = self._row_to_model(row)
                    by_id[model.id] = model
        return [by_id[i] for i in id_list if i in by_id]

    async def count_for_kb(self, kb_id: str) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM kb_chunks WHERE kb_id = ?", (kb_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def search_keyword(self, kb_id: str, query: str, k: int) -> list[tuple[int, float]]:
        """Keyword search over ``kb_id``'s chunks. Returns ``(chunk_id, score)``
        pairs ordered best-first.

        ``bm25()`` is lower-is-better (negative) — this method returns the
        raw score as-is; callers (Leg 4's benchmark, the later fusion
        flight) must not assume higher-is-better.

        The query is split on whitespace and each term individually quoted
        (``'"' + term.replace('"', '""') + '"'``), joined by spaces (FTS5
        implicit AND) — this neutralises FTS5 operator characters (``"``,
        ``*``, ``(``, ``-``, ``OR``, ``NEAR``) so a query containing them is
        matched as plain terms instead of raising or being misinterpreted.
        An empty or whitespace-only ``query`` returns ``[]`` without
        touching the DB.

        ``bm25(kb_chunks_fts)`` and the ``MATCH`` clause both name the
        UNALIASED table — ``bm25(f)`` / ``f MATCH ...`` raise
        ``no such column: f`` even though the rowid select aliases the FTS
        table ``f``. The KB scope is a join (not a WHERE on the FTS table
        itself) because the FTS table carries no ``kb_id`` column.

        ``k`` is bounded to ``1 <= k <= MAX_SEARCH_K`` (squawk 0054) —
        rejected with ``ValueError`` outside that range, not clamped, to
        match this repository's existing convention of raising on invalid
        input (e.g. ``replace_item_chunks``'s illegal-field guard) rather
        than silently coercing it.
        """
        if k < 1 or k > MAX_SEARCH_K:
            raise ValueError(f"k must be between 1 and {MAX_SEARCH_K}, got {k}")
        terms = query.split()
        if not terms:
            return []
        match_query = " ".join('"' + term.replace('"', '""') + '"' for term in terms)
        async with self.conn.execute(
            "SELECT f.rowid, bm25(kb_chunks_fts) AS score FROM kb_chunks_fts f "
            "JOIN kb_chunks c ON c.id = f.rowid "
            "WHERE kb_chunks_fts MATCH ? AND c.kb_id = ? "
            "ORDER BY score LIMIT ?",
            (match_query, kb_id, k),
        ) as cur:
            rows = await cur.fetchall()
        return [(row[0], row[1]) for row in rows]

    async def rebuild_fts(self) -> None:
        """Rebuild the FTS5 index from ``kb_chunks``'s current contents.

        Recovers from a desynchronised index (e.g. a raw ``DELETE FROM
        kb_chunks`` issued outside this repository, bypassing the FTS sync
        rule).
        """
        async with write_transaction(self.conn):
            await self.conn.execute("INSERT INTO kb_chunks_fts(kb_chunks_fts) VALUES ('rebuild')")

    async def check_fts(self) -> bool:
        """Verify the FTS5 index against ``kb_chunks``'s current contents.

        Uses the TWO-argument integrity-check form —
        ``INSERT INTO kb_chunks_fts(kb_chunks_fts, rank) VALUES
        ('integrity-check', 1)`` — which, for an external-content table,
        verifies the index against the content table. The one-argument form
        checks only the index's own internal structure and reports clean on
        an external-content desync; it is deliberately not used here.

        Takes the write-transaction guard even though nothing is committed
        (the check issues no writes) — the rule the guard enforces is about
        never running while another task's write is mid-flight on the FTS
        table, and a read inside the guard is allowed. Returns ``False`` on
        ``sqlite3.DatabaseError`` (the desync signal); ``True`` otherwise,
        including on an empty index.
        """
        try:
            async with write_transaction(self.conn):
                await self.conn.execute(
                    "INSERT INTO kb_chunks_fts(kb_chunks_fts, rank) VALUES ('integrity-check', 1)"
                )
        except sqlite3.DatabaseError:
            return False
        return True

    @staticmethod
    def _row_to_model(row: aiosqlite.Row) -> KBChunk:
        return KBChunk(
            id=row["id"],
            item_id=row["item_id"],
            kb_id=row["kb_id"],
            seq=row["seq"],
            text=row["text"],
            char_start=row["char_start"],
            char_end=row["char_end"],
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
        async with write_transaction(self.conn):
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

    async def update(self, source: MCPSource) -> None:
        async with self.conn.execute("SELECT 1 FROM mcp_sources WHERE id = ?", (source.id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"MCP source not found: {source.id}")
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE mcp_sources SET name=?, type=?, config=?, secrets=?, updated_at=? "
                "WHERE id=?",
                (
                    source.name,
                    source.type,
                    json.dumps(source.config),
                    self._secrets_to_ciphertext(source.secrets),
                    now_iso(),
                    source.id,
                ),
            )

    async def merge_cache(
        self,
        source_id: str,
        fields: dict[str, Any],
        delete: Iterable[str] = (),
    ) -> None:
        """Merge ``fields`` into ``config["_cache"]``, then drop the keys in ``delete``.

        Config-only write: no other column and not ``updated_at`` changes (nothing reads
        it for MCP sources, and a connection check is not an edit). A ``None`` value in
        ``fields`` is stored as null, never treated as a delete. The read and the write
        share one write transaction. Raises ``KeyError`` for an unknown id.
        """
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT config FROM mcp_sources WHERE id = ?", (source_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                raise KeyError(f"MCP source not found: {source_id}")
            config = json.loads(row[0]) if row[0] else {}
            cache = {**(config.get("_cache") or {}), **fields}
            for key in delete:
                cache.pop(key, None)
            config["_cache"] = cache
            await self.conn.execute(
                "UPDATE mcp_sources SET config=? WHERE id=?", (json.dumps(config), source_id)
            )

    async def delete(self, source_id: str) -> None:
        async with self.conn.execute("SELECT 1 FROM mcp_sources WHERE id = ?", (source_id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"MCP source not found: {source_id}")
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM mcp_sources WHERE id = ?", (source_id,))

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
        async with write_transaction(self.conn):
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

    async def update(self, account: Connector) -> None:
        async with self.conn.execute("SELECT 1 FROM connectors WHERE id = ?", (account.id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account.id}")
        async with write_transaction(self.conn):
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

    async def delete(self, account_id: str) -> None:
        async with self.conn.execute("SELECT 1 FROM connectors WHERE id = ?", (account_id,)) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Connector account not found: {account_id}")
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM connectors WHERE id = ?", (account_id,))

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


# ── Connector directory repository ───────────────────────────────────────

_conn_logger = logging.getLogger(__name__)


def _parse_connector_binding_config(raw: str | None) -> dict:
    """Parse a ``connectors.config`` value into a dict whose ``channel_map``
    is an object. Raises ``ValueError``/``TypeError`` on a malformed row."""
    config = json.loads(raw or "{}")
    if not isinstance(config, dict):
        raise TypeError("connector config is not an object")
    channel_map = config.get("channel_map") or {}
    if not isinstance(channel_map, dict):
        raise TypeError("channel_map is not an object")
    return config


async def connector_bindings(conn: aiosqlite.Connection) -> dict[str, set[str]]:
    """Map each connector id to the agent names its binding names.

    A connector's binding is its ``config.default_agent`` plus every
    ``config.channel_map`` value. A malformed row (unparseable JSON, a non-dict
    config or ``channel_map``, unhashable values) is skipped with a log line
    rather than raised, so one bad row cannot break a search or an agent build.
    Reads the plaintext ``config`` column only (no secrets).
    """
    async with conn.execute("SELECT id, config FROM connectors") as cur:
        rows = await cur.fetchall()
    out: dict[str, set[str]] = {}
    for row in rows:
        try:
            config = _parse_connector_binding_config(row["config"])
            channel_map = config.get("channel_map") or {}
            names = {n for n in [config.get("default_agent"), *channel_map.values()] if n}
            out[row["id"]] = names
        except (ValueError, TypeError, AttributeError):
            _conn_logger.warning("Skipping malformed connector row %r", row["id"], exc_info=True)
    return out


async def agent_names_in_use(
    conn: aiosqlite.Connection, bindings: dict[str, set[str]] | None = None
) -> set[str]:
    """Every agent name some connector's binding names."""
    if bindings is None:
        bindings = await connector_bindings(conn)
    return set().union(*bindings.values()) if bindings else set()


class ConnectorDirectoryRepository:
    """Async access to ``connector_directory`` (v39, DD-4) — passively
    observed platform peer/channel names. Sibling to
    :class:`ConnectorRepository` in construction shape (one ``conn``), but
    deliberately carries NO encryptor: the table holds no secrets (DD-4),
    so there is no ciphertext envelope to thread through.

    Two named methods per DD-4/DD-5/DD-7's repository-surface design
    review: :meth:`search` (agent-scoped candidates, leg 3's lookup tool)
    and :meth:`get` (exact-match, DD-7's session-title consumer). Both
    return RAW rows (:class:`ConnectorDirectoryEntry` — ``kind``,
    ``platform_id``, ``thread_id``, names) — leg 3's tool performs the
    DD-5 literal-key translation to ``peer_id``/``channel_id``; that
    boundary is pinned here so leg 3 doesn't guess. "RAW" describes
    key-translation status (``platform_id``/``thread_id`` are not yet
    translated), not single-table provenance: :meth:`search` additionally
    JOINs ``connectors`` for a plaintext ``connector_name`` column (leg 3,
    review HIGH fix) — a compatible extension of this boundary, not a
    breach of it.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def upsert(
        self,
        *,
        connector_id: str,
        kind: str,
        platform_id: str,
        thread_id: str | None,
        display_name: str,
        username: str | None,
    ) -> None:
        """Upsert-on-change (DD-4's write-per-message guard): a write is
        skipped entirely — including ``last_seen`` — when an existing row
        already carries the same ``display_name`` + ``username``. Callers
        are responsible for never passing an empty-string ``display_name``
        (the edge-case fallback chain — name, else username, else the raw
        platform id — lives at each call site, not here)."""
        async with self.conn.execute(
            "SELECT display_name, username FROM connector_directory "
            "WHERE connector_id = ? AND kind = ? AND platform_id = ?",
            (connector_id, kind, platform_id),
        ) as cur:
            existing = await cur.fetchone()
        if (
            existing is not None
            and existing["display_name"] == display_name
            and existing["username"] == username
        ):
            return
        async with write_transaction(self.conn):
            await self.conn.execute(
                "INSERT INTO connector_directory "
                "(connector_id, kind, platform_id, thread_id, display_name, username, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(connector_id, kind, platform_id) DO UPDATE SET "
                "thread_id = excluded.thread_id, display_name = excluded.display_name, "
                "username = excluded.username, last_seen = excluded.last_seen",
                (connector_id, kind, platform_id, thread_id, display_name, username, now_iso()),
            )

    async def get(
        self, connector_id: str, kind: str, platform_id: str
    ) -> ConnectorDirectoryEntry | None:
        """DD-7's exact-match consumer (session-title resolution)."""
        async with self.conn.execute(
            "SELECT connector_id, kind, platform_id, thread_id, display_name, username, last_seen "
            "FROM connector_directory WHERE connector_id = ? AND kind = ? AND platform_id = ?",
            (connector_id, kind, platform_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return ConnectorDirectoryEntry(**dict(row))

    async def search(
        self, agent_name: str, query: str, connector_id: str | None = None
    ) -> list[ConnectorDirectoryEntry]:
        """DD-5's candidate lookup, agent-scoped.

        Search scoping is CONNECTOR-LEVEL by design (designer ruling,
        2026-09-02): a connector is in scope when ``agent_name`` appears
        ANYWHERE in its binding (``config.default_agent`` OR any
        ``config.channel_map`` value) — a deliberate simplification, NOT
        per-target precision. Rationale: send-time authorization remains
        the real per-target gate (unchanged, enforced in
        ``tools/connector_send.py``); this lookup exposes only names
        within one connector, which is one operator trust domain; a
        per-target search filter would duplicate the send matrix for
        marginal privacy inside a domain the operator already configured.
        Queries ``connectors.config`` directly (plaintext JSON column, no
        ``secrets`` touched) rather than going through
        :class:`ConnectorRepository` — this repository holds no
        encryptor, by design (DD-4).

        Case-insensitive substring match over ``display_name`` OR
        ``username``; ≤10 rows, newest ``last_seen`` first. ``connector_id``
        is an OPTIONAL further narrowing — it is intersected with, never a
        substitute for, the authorization scope above, so passing an
        out-of-scope id yields an empty result rather than a bypass. An
        unbound agent (no connector names it) returns an empty result, not
        an error.

        Squawk 0039: the substring is escaped (``%``, ``_``, and the
        escape char ``\\`` itself) before being embedded in the ``LIKE``
        pattern, with a matching ``ESCAPE '\\'`` clause — a literal query
        of ``%`` or ``_`` matches only names containing that literal
        character, not every/any row.

        Leg 3 (review HIGH fix): the SELECT gains a plain JOIN to
        ``connectors`` returning its plaintext ``name`` as ``connector_name``
        — one more RAW column, no encryptor, no per-candidate
        :class:`ConnectorRepository` lookup (``connectors.name`` is never
        secret). This is the only enrichment path; :meth:`get` stays a
        single-table exact-match read.
        """
        bindings = await connector_bindings(self.conn)
        authorized_ids = [cid for cid, names in bindings.items() if agent_name in names]
        if connector_id is not None:
            authorized_ids = [c for c in authorized_ids if c == connector_id]
        if not authorized_ids:
            return []

        placeholders = ", ".join("?" for _ in authorized_ids)
        # Escape the LIKE metacharacters ('%', '_') and the escape char
        # itself ('\') in the user-supplied substring, so a literal query
        # of "%" or "_" matches only names containing that literal
        # character rather than every/any row.
        escaped_query = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped_query}%"
        async with self.conn.execute(
            "SELECT cd.connector_id, cd.kind, cd.platform_id, cd.thread_id, "
            "cd.display_name, cd.username, cd.last_seen, c.name AS connector_name "
            "FROM connector_directory cd JOIN connectors c ON c.id = cd.connector_id "
            f"WHERE cd.connector_id IN ({placeholders}) "
            "AND (LOWER(cd.display_name) LIKE ? ESCAPE '\\' "
            "OR LOWER(cd.username) LIKE ? ESCAPE '\\') "
            "ORDER BY cd.last_seen DESC LIMIT 10",
            (*authorized_ids, like, like),
        ) as cur:
            rows = await cur.fetchall()
        return [ConnectorDirectoryEntry(**dict(r)) for r in rows]

    async def delete_for_connector(self, connector_id: str) -> None:
        """DD-1g: one deterministic DELETE, wired into the connector
        delete route. No FK/cascade (DD-4) — this is the mechanism."""
        async with write_transaction(self.conn):
            await self.conn.execute(
                "DELETE FROM connector_directory WHERE connector_id = ?", (connector_id,)
            )


# ── Agent rule repository ────────────────────────────────────────────────


class AgentRuleRepository:
    """Async access to ``agent_rules`` (Mission 27 F1, DD3/DD4).

    Each mutating method opens ONE ``write_transaction`` itself (the guard is
    not re-entrant) and reads, validates and writes inside it, so the 4,000
    character cap check and the insert are atomic. Positions are 0-based and
    dense. Limit violations raise :class:`RuleLimitError` /
    :class:`RuleOrderError`; a missing or another agent's rule raises
    ``KeyError``.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row(row: Any) -> AgentRule:
        return AgentRule(
            id=row[0],
            agent_name=row[1],
            text=row[2],
            enabled=bool(row[3]),
            position=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    _COLS = "id, agent_name, text, enabled, position, created_at, updated_at"

    async def list_for_agent(self, name: str, *, enabled_only: bool = False) -> list[AgentRule]:
        sql = f"SELECT {self._COLS} FROM agent_rules WHERE agent_name = ?"
        if enabled_only:
            sql += " AND enabled = 1"
        sql += " ORDER BY position, id"
        async with self.conn.execute(sql, (name,)) as cur:
            return [self._row(r) for r in await cur.fetchall()]

    async def get(self, name: str, rule_id: str) -> AgentRule | None:
        async with self.conn.execute(
            f"SELECT {self._COLS} FROM agent_rules WHERE agent_name = ? AND id = ?",
            (name, rule_id),
        ) as cur:
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def total_chars(self, name: str, *, exclude_id: str | None = None) -> int:
        sql = "SELECT COALESCE(SUM(LENGTH(text)), 0) FROM agent_rules WHERE agent_name = ?"
        params: tuple[Any, ...] = (name,)
        if exclude_id is not None:
            sql += " AND id != ?"
            params = (name, exclude_id)
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def create(self, name: str, text: str, enabled: bool = True) -> AgentRule:
        text = validate_rule_text(text)
        rule_id = uuid.uuid4().hex
        now = now_iso()
        async with write_transaction(self.conn):
            total = await self.total_chars(name)
            if total + len(text) > RULES_TOTAL_MAX_CHARS:
                raise total_limit_error(total + len(text))
            async with self.conn.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM agent_rules WHERE agent_name = ?",
                (name,),
            ) as cur:
                row = await cur.fetchone()
            position = int(row[0])
            await self.conn.execute(
                "INSERT INTO agent_rules "
                "(id, agent_name, text, enabled, position, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rule_id, name, text, 1 if enabled else 0, position, now, now),
            )
        return AgentRule(
            id=rule_id,
            agent_name=name,
            text=text,
            enabled=enabled,
            position=position,
            created_at=now,
            updated_at=now,
        )

    async def update(
        self,
        name: str,
        rule_id: str,
        *,
        text: str | None = None,
        enabled: bool | None = None,
    ) -> AgentRule:
        new_text = validate_rule_text(text) if text is not None else None
        async with write_transaction(self.conn):
            current = await self.get(name, rule_id)
            if current is None:
                raise KeyError(f"Rule not found: {rule_id}")
            if new_text is not None:
                others = await self.total_chars(name, exclude_id=rule_id)
                if others + len(new_text) > RULES_TOTAL_MAX_CHARS:
                    raise total_limit_error(others + len(new_text))
            final_text = new_text if new_text is not None else current.text
            final_enabled = current.enabled if enabled is None else enabled
            now = now_iso()
            await self.conn.execute(
                "UPDATE agent_rules SET text = ?, enabled = ?, updated_at = ? "
                "WHERE agent_name = ? AND id = ?",
                (final_text, 1 if final_enabled else 0, now, name, rule_id),
            )
        return current.model_copy(
            update={"text": final_text, "enabled": final_enabled, "updated_at": now}
        )

    async def delete(self, name: str, rule_id: str) -> None:
        async with write_transaction(self.conn):
            if await self.get(name, rule_id) is None:
                raise KeyError(f"Rule not found: {rule_id}")
            await self.conn.execute(
                "DELETE FROM agent_rules WHERE agent_name = ? AND id = ?", (name, rule_id)
            )
            await self._redensify(name)

    async def _redensify(self, name: str) -> None:
        async with self.conn.execute(
            "SELECT id FROM agent_rules WHERE agent_name = ? ORDER BY position, id", (name,)
        ) as cur:
            ids = [r[0] for r in await cur.fetchall()]
        for pos, rid in enumerate(ids):
            await self.conn.execute("UPDATE agent_rules SET position = ? WHERE id = ?", (pos, rid))

    async def reorder(self, name: str, ids: Sequence[str]) -> list[AgentRule]:
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT id FROM agent_rules WHERE agent_name = ?", (name,)
            ) as cur:
                existing = {r[0] for r in await cur.fetchall()}
            if len(ids) != len(set(ids)) or set(ids) != existing:
                raise RuleOrderError(
                    "ids must list every one of this agent's rules exactly once, "
                    f"in the new order ({len(existing)} expected, {len(ids)} given)."
                )
            now = now_iso()
            for pos, rid in enumerate(ids):
                await self.conn.execute(
                    "UPDATE agent_rules SET position = ?, updated_at = ? WHERE id = ?",
                    (pos, now, rid),
                )
        return await self.list_for_agent(name)


# ── Agent note repository ────────────────────────────────────────────────


def _merge_sources(old: Sequence[str], new: Sequence[str]) -> list[str]:
    merged: list[str] = []
    for src in [*old, *new]:
        if src not in merged:
            merged.append(src)
    return merged[:SOURCES_CAP]


class AgentMcpToolCacheRepository:
    """Async access to ``agent_mcp_tool_cache`` (sortie 09, DD5).

    The tool list an agent that uses its own credentials on a source saw with those
    credentials: ``tools`` is a JSON list of ``{name, description, input_schema}``.
    Tool metadata only, never a credential, so the column is not encrypted.

    ``put_if_unchanged`` is the single-statement race guard: it writes only while the
    agent's ``agents.updated_at`` still equals the value read before the listing, so a
    save (or a rename or delete) that lands while a listing is in flight cancels the
    write. Other ``agents.updated_at`` writers (the notes and routines flags, the
    field setters) also cancel an in-flight write, which is safe: the cost is one
    more live listing on the next build.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    @staticmethod
    def _decode(tools: str, fetched_at: str) -> dict[str, Any]:
        try:
            decoded = json.loads(tools)
        except ValueError:
            decoded = []
        return {"tools": decoded if isinstance(decoded, list) else [], "fetched_at": fetched_at}

    async def agent_updated_at(self, name: str) -> str | None:
        """The agent's stored ``updated_at``, or ``None`` when it is not in the store."""
        async with self.conn.execute("SELECT updated_at FROM agents WHERE name = ?", (name,)) as c:
            row = await c.fetchone()
        return row[0] if row is not None else None

    async def get(self, agent: str, source_id: str) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT tools, fetched_at FROM agent_mcp_tool_cache "
            "WHERE agent_name = ? AND source_id = ?",
            (agent, source_id),
        ) as cur:
            row = await cur.fetchone()
        return self._decode(row[0], row[1]) if row is not None else None

    async def get_for_agent(self, agent: str) -> dict[str, dict[str, Any]]:
        async with self.conn.execute(
            "SELECT source_id, tools, fetched_at FROM agent_mcp_tool_cache WHERE agent_name = ?",
            (agent,),
        ) as cur:
            rows = await cur.fetchall()
        return {r[0]: self._decode(r[1], r[2]) for r in rows}

    async def put_if_unchanged(
        self,
        agent: str,
        source_id: str,
        tools: list[dict[str, Any]],
        expected_updated_at: str | None,
    ) -> bool:
        """Write the row iff the agent's ``updated_at`` still equals
        ``expected_updated_at``. Returns whether a row was written."""
        if expected_updated_at is None:
            return False
        async with write_transaction(self.conn):
            cur = await self.conn.execute(
                "INSERT OR REPLACE INTO agent_mcp_tool_cache "
                "(agent_name, source_id, tools, fetched_at) "
                "SELECT ?, ?, ?, ? WHERE (SELECT updated_at FROM agents WHERE name = ?) = ? "
                "AND EXISTS (SELECT 1 FROM mcp_sources WHERE id = ?)",
                (
                    agent,
                    source_id,
                    json.dumps(tools),
                    now_iso(),
                    agent,
                    expected_updated_at,
                    source_id,
                ),
            )
            return cur.rowcount > 0

    async def list_all(self) -> list[tuple[str, list[dict[str, Any]]]]:
        """Every row as ``(source_id, tools)``, across all agents (sortie 10, tool names)."""
        async with self.conn.execute(
            "SELECT source_id, tools, fetched_at FROM agent_mcp_tool_cache "
            "ORDER BY agent_name, source_id"
        ) as cur:
            rows = await cur.fetchall()
        return [(r[0], self._decode(r[1], r[2])["tools"]) for r in rows]

    async def delete(self, agent: str, source_id: str) -> None:
        async with write_transaction(self.conn):
            await self.conn.execute(
                "DELETE FROM agent_mcp_tool_cache WHERE agent_name = ? AND source_id = ?",
                (agent, source_id),
            )

    async def delete_for_source(self, source_id: str) -> None:
        async with write_transaction(self.conn):
            await self.conn.execute(
                "DELETE FROM agent_mcp_tool_cache WHERE source_id = ?", (source_id,)
            )


# ── Secrets (sortie 10) ──────────────────────────────────────────────────

SECRET_MASK = "__MASKED__"


class SecretNameConflict(Exception):  # noqa: N818 - a condition, like NoteDuplicateError's kin
    """Another secret already has this name (compared ignoring case)."""


class SecretInvalid(Exception):  # noqa: N818 - carries 422 details
    """A secret write the database state refuses. ``details`` are 422-shaped dicts
    (``type``, ``loc``, ``msg``) that never carry a value."""

    def __init__(self, details: list[dict[str, Any]]) -> None:
        super().__init__("invalid secret write")
        self.details = details


@dataclass
class SecretValueRef:
    """A stored pair as the routes see it: id and key, never the value."""

    id: str
    key: str
    position: int


@dataclass
class Secret:
    id: str
    name: str
    description: str
    allowed_tools: list[str]
    values: list[SecretValueRef]
    created_at: str
    updated_at: str


class SecretRepository:
    """Async access to ``secrets`` and ``secret_values`` (sortie 10, DD4, DD5).

    Values are Fernet ciphertext. ``list``/``get`` never decrypt; only
    :meth:`get_values` and :meth:`all_values` do, and the routes never call them.
    The encryptor is a reference to the app's (so ``install_key`` after a rotation
    reaches it), never a copy of the key. Each write is one ``write_transaction``.
    """

    def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor | None = None) -> None:
        self.conn = conn
        self._encryptor = encryptor

    @property
    def encryptor(self) -> Encryptor:
        if self._encryptor is None:
            from the_one.config import settings
            from the_one.encryption import get_encryptor

            self._encryptor = get_encryptor(settings.data_dir)
        return self._encryptor

    @staticmethod
    def _tools(raw: str | None) -> list[str]:
        try:
            decoded = json.loads(raw or "[]")
        except ValueError:
            return []
        return [t for t in decoded if isinstance(t, str)] if isinstance(decoded, list) else []

    async def _load(self, secret_id: str | None = None) -> list[Secret]:
        sql = "SELECT id, name, description, allowed_tools, created_at, updated_at FROM secrets"
        params: tuple[Any, ...] = ()
        if secret_id is not None:
            sql += " WHERE id = ?"
            params = (secret_id,)
        sql += " ORDER BY name COLLATE NOCASE, id"
        async with self.conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        vsql = "SELECT id, secret_id, key, position FROM secret_values"
        if secret_id is not None:
            vsql += " WHERE secret_id = ?"
        vsql += " ORDER BY secret_id, position, id"
        async with self.conn.execute(vsql, params) as cur:
            vrows = await cur.fetchall()
        by_secret: dict[str, list[SecretValueRef]] = {}
        for v in vrows:
            by_secret.setdefault(v[1], []).append(SecretValueRef(id=v[0], key=v[2], position=v[3]))
        return [
            Secret(
                id=r[0],
                name=r[1],
                description=r[2],
                allowed_tools=self._tools(r[3]),
                values=by_secret.get(r[0], []),
                created_at=r[4],
                updated_at=r[5],
            )
            for r in rows
        ]

    async def list(self) -> list[Secret]:
        return await self._load()

    async def get(self, secret_id: str) -> Secret | None:
        found = await self._load(secret_id)
        return found[0] if found else None

    async def get_values(self, secret_id: str) -> list[tuple[str, str]]:
        """``[(key, plaintext)]`` in position order. Internal: no route calls this."""
        async with self.conn.execute(
            "SELECT key, value FROM secret_values WHERE secret_id = ? ORDER BY position, id",
            (secret_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [(r[0], self.encryptor.decrypt(r[1])) for r in rows]

    async def all_values(self) -> list[tuple[str, str, str]]:
        """``[(secret_id, key, plaintext)]`` for every stored pair. Internal."""
        async with self.conn.execute(
            "SELECT secret_id, key, value FROM secret_values ORDER BY secret_id, position, id"
        ) as cur:
            rows = await cur.fetchall()
        return [(r[0], r[1], self.encryptor.decrypt(r[2])) for r in rows]

    @staticmethod
    def _is_name_clash(e: sqlite3.IntegrityError) -> bool:
        return "secrets.name" in str(e)

    async def _name_taken(self, name: str, *, exclude_id: str | None) -> bool:
        async with self.conn.execute(
            "SELECT id FROM secrets WHERE name = ? COLLATE NOCASE AND id != ?",
            (name, exclude_id or ""),
        ) as cur:
            return await cur.fetchone() is not None

    async def _other_keys(self, secret_id: str) -> set[str]:
        async with self.conn.execute(
            "SELECT key FROM secret_values WHERE secret_id != ?", (secret_id,)
        ) as cur:
            return {r[0].lower() for r in await cur.fetchall()}

    async def create(
        self,
        name: str,
        description: str,
        allowed_tools: list[str],
        values: list[dict[str, str]],
    ) -> Secret:
        """Insert a secret with its ``[{key, value}]`` pairs. Raises
        :class:`SecretNameConflict` / :class:`SecretInvalid`."""
        secret_id = uuid.uuid4().hex
        now = now_iso()
        try:
            async with write_transaction(self.conn):
                if await self._name_taken(name, exclude_id=None):
                    raise SecretNameConflict
                taken = await self._other_keys(secret_id)
                errors = [
                    {
                        "type": "value_error",
                        "loc": ["values", i, "key"],
                        "msg": "Another secret already uses this key.",
                    }
                    for i, pair in enumerate(values)
                    if pair["key"].lower() in taken
                ]
                if errors:
                    raise SecretInvalid(errors)
                await self.conn.execute(
                    "INSERT INTO secrets "
                    "(id, name, description, allowed_tools, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (secret_id, name, description, json.dumps(allowed_tools), now, now),
                )
                for i, pair in enumerate(values):
                    await self.conn.execute(
                        "INSERT INTO secret_values (id, secret_id, key, value, position) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            uuid.uuid4().hex,
                            secret_id,
                            pair["key"],
                            self.encryptor.encrypt(pair["value"]),
                            i,
                        ),
                    )
        except (sqlite3.IntegrityError, aiosqlite.IntegrityError) as e:
            raise self._map_integrity(e, values) from None
        created = await self.get(secret_id)
        assert created is not None
        return created

    def _map_integrity(
        self, e: sqlite3.IntegrityError, values: list[dict[str, Any]] | None
    ) -> Exception:
        if self._is_name_clash(e):
            return SecretNameConflict()
        # A key race with another writer: the constraint does not say which row, so the
        # message is generic and lands on the first pair (no value is ever echoed).
        return SecretInvalid(
            [
                {
                    "type": "value_error",
                    "loc": ["values", 0, "key"],
                    "msg": "Another secret already uses one of these keys.",
                }
            ]
        )

    async def update(
        self,
        secret_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        allowed_tools: list[str] | None = None,
        values: list[dict[str, Any]] | None = None,
    ) -> Secret:
        """Partial update. ``values`` is the full ordered ``[{id?, key, value}]`` list:
        ``SECRET_MASK`` with this secret's pair ``id`` keeps its ciphertext, any other
        string is encrypted, an omitted pair is deleted. Raises ``KeyError`` (unknown
        secret), :class:`SecretNameConflict`, :class:`SecretInvalid`."""
        try:
            async with write_transaction(self.conn):
                async with self.conn.execute(
                    "SELECT name, description, allowed_tools FROM secrets WHERE id = ?",
                    (secret_id,),
                ) as cur:
                    row = await cur.fetchone()
                if row is None:
                    raise KeyError(secret_id)
                new_name = row[0] if name is None else name
                if name is not None and await self._name_taken(name, exclude_id=secret_id):
                    raise SecretNameConflict
                if values is not None:
                    async with self.conn.execute(
                        "SELECT id, value FROM secret_values WHERE secret_id = ?", (secret_id,)
                    ) as cur:
                        existing = {r[0]: r[1] for r in await cur.fetchall()}
                    taken = await self._other_keys(secret_id)
                    errors: list[dict[str, Any]] = []
                    resolved: list[tuple[str, str, str]] = []  # (id, key, ciphertext)
                    for i, pair in enumerate(values):
                        if pair["key"].lower() in taken:
                            errors.append(
                                {
                                    "type": "value_error",
                                    "loc": ["values", i, "key"],
                                    "msg": "Another secret already uses this key.",
                                }
                            )
                            continue
                        pair_id = pair.get("id")
                        if pair["value"] == SECRET_MASK:
                            if pair_id is None or pair_id not in existing:
                                errors.append(
                                    {
                                        "type": "value_error",
                                        "loc": ["values", i, "value"],
                                        "msg": "This value is not a stored value of this secret.",
                                    }
                                )
                                continue
                            resolved.append((pair_id, pair["key"], existing[pair_id]))
                        else:
                            resolved.append(
                                (
                                    uuid.uuid4().hex,
                                    pair["key"],
                                    self.encryptor.encrypt(pair["value"]),
                                )
                            )
                    if errors:
                        raise SecretInvalid(errors)
                    await self.conn.execute(
                        "DELETE FROM secret_values WHERE secret_id = ?", (secret_id,)
                    )
                    for i, (pair_id, key, ciphertext) in enumerate(resolved):
                        await self.conn.execute(
                            "INSERT INTO secret_values (id, secret_id, key, value, position) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (pair_id, secret_id, key, ciphertext, i),
                        )
                await self.conn.execute(
                    "UPDATE secrets SET name = ?, description = ?, allowed_tools = ?, "
                    "updated_at = ? WHERE id = ?",
                    (
                        new_name,
                        row[1] if description is None else description,
                        row[2] if allowed_tools is None else json.dumps(allowed_tools),
                        now_iso(),
                        secret_id,
                    ),
                )
        except (sqlite3.IntegrityError, aiosqlite.IntegrityError) as e:
            raise self._map_integrity(e, values) from None
        updated = await self.get(secret_id)
        assert updated is not None
        return updated

    async def delete(self, secret_id: str) -> list[str]:
        """Delete the secret, its values (cascade) and its id from every agent's
        ``secret_ids``, in one transaction. Returns the agents whose grants changed.
        The scrub does not bump ``agents.updated_at``. ``KeyError`` when unknown."""
        scrubbed: list[str] = []
        async with write_transaction(self.conn):
            async with self.conn.execute("SELECT 1 FROM secrets WHERE id = ?", (secret_id,)) as c:
                if await c.fetchone() is None:
                    raise KeyError(secret_id)
            async with self.conn.execute(
                "SELECT name, secret_ids FROM agents WHERE secret_ids IS NOT NULL "
                "AND secret_ids != '' AND EXISTS ("
                "SELECT 1 FROM json_each(agents.secret_ids) WHERE json_each.value = ?) "
                "ORDER BY name",
                (secret_id,),
            ) as cur:
                holders = await cur.fetchall()
            for agent_name, raw in holders:
                kept = [s for s in json.loads(raw) if s != secret_id]
                await self.conn.execute(
                    "UPDATE agents SET secret_ids = ? WHERE name = ?",
                    (json.dumps(kept), agent_name),
                )
                scrubbed.append(agent_name)
            await self.conn.execute("DELETE FROM secrets WHERE id = ?", (secret_id,))
        return scrubbed

    async def exists_many(self, ids: Iterable[str]) -> set[str]:
        """Which of ``ids`` are stored secrets."""
        wanted = list(dict.fromkeys(ids))
        if not wanted:
            return set()
        marks = ",".join("?" for _ in wanted)
        async with self.conn.execute(
            f"SELECT id FROM secrets WHERE id IN ({marks})",  # noqa: S608 - placeholders only
            wanted,
        ) as cur:
            return {r[0] for r in await cur.fetchall()}

    async def rewrite_tool_prefix(self, old_prefix: str, new_prefix: str) -> int:
        """In one transaction, turn every ``allowed_tools`` entry that starts with
        ``old_prefix`` into ``new_prefix`` + the rest, de-duplicating (first kept).
        Returns the number of secrets changed (the MCP rename carry's helper)."""
        changed = 0
        async with write_transaction(self.conn):
            async with self.conn.execute("SELECT id, allowed_tools FROM secrets") as cur:
                rows = await cur.fetchall()
            for secret_id, raw in rows:
                tools = self._tools(raw)
                rewritten = [
                    new_prefix + t[len(old_prefix) :] if t.startswith(old_prefix) else t
                    for t in tools
                ]
                rewritten = list(dict.fromkeys(rewritten))
                if rewritten != tools:
                    await self.conn.execute(
                        "UPDATE secrets SET allowed_tools = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(rewritten), now_iso(), secret_id),
                    )
                    changed += 1
        return changed


class AgentNoteRepository:
    """Async access to ``agent_notes`` (Mission 27 F2, DD1/DD4/DD7/DD8).

    Each mutating method opens ONE ``write_transaction`` and never nests (the
    guard is not re-entrant), so the switch re-check, the limits, the
    de-duplication and the write are atomic. Every query is scoped by
    ``agent_name``; the mutators raise ``KeyError`` on a miss (another agent's
    note is a miss). The agent-facing methods (``create``,
    ``update_by_agent``, ``forget_by_agent``) re-check ``notes_enabled``
    inside the transaction and raise :class:`NotesDisabledError`; the
    operator methods never check it.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    _COLS = (
        "n.id, n.agent_name, n.number, n.text, n.untrusted, n.untrusted_sources, "
        "n.origin_kind, n.origin_session_id, COALESCE(cs.title, n.origin_label), "
        "cs.id IS NOT NULL, n.origin_platform, n.origin_peer_id, n.origin_peer_name, "
        "n.created_at, n.updated_at, n.updated_by"
    )
    _FROM = "FROM agent_notes n LEFT JOIN chat_sessions cs ON cs.id = n.origin_session_id"

    @staticmethod
    def _row(row: Any) -> AgentNote:
        try:
            sources = json.loads(row[5]) if row[5] else []
        except ValueError:
            sources = []
        label = row[8]
        if row[6] != "other" and row[7] and not label:
            label = "Untitled chat"
        return AgentNote(
            id=row[0],
            agent_name=row[1],
            number=row[2],
            text=row[3],
            untrusted=bool(row[4]),
            untrusted_sources=[str(s) for s in sources] if isinstance(sources, list) else [],
            origin_kind=row[6],
            origin_session_id=row[7],
            origin_label=label,
            origin_exists=bool(row[9]),
            origin_platform=row[10],
            origin_peer_id=row[11],
            origin_peer_name=row[12],
            created_at=row[13],
            updated_at=row[14],
            updated_by=row[15],
        )

    async def list_if_enabled(self, name: str) -> list[AgentNote] | None:
        """The prompt loader's read: the notes by number when the agent's switch
        is on, ``None`` when it is off or the agent has no stored row."""
        async with self.conn.execute(
            "SELECT notes_enabled FROM agents WHERE name = ?", (name,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or not row[0]:
            return None
        return await self.list_for_agent(name)

    async def count_for_agent(self, name: str) -> int:
        """How many notes the agent holds (a read-only count; never the text)."""
        async with self.conn.execute(
            "SELECT COUNT(*) FROM agent_notes WHERE agent_name = ?", (name,)
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def list_for_agent(self, name: str) -> list[AgentNote]:
        async with self.conn.execute(
            f"SELECT {self._COLS} {self._FROM} WHERE n.agent_name = ? ORDER BY n.number",
            (name,),
        ) as cur:
            return [self._row(r) for r in await cur.fetchall()]

    async def get(self, name: str, note_id: str) -> AgentNote | None:
        async with self.conn.execute(
            f"SELECT {self._COLS} {self._FROM} WHERE n.agent_name = ? AND n.id = ?",
            (name, note_id),
        ) as cur:
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def get_by_number(self, name: str, number: int) -> AgentNote | None:
        async with self.conn.execute(
            f"SELECT {self._COLS} {self._FROM} WHERE n.agent_name = ? AND n.number = ?",
            (name, number),
        ) as cur:
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def total_chars(self, name: str, *, exclude_id: str | None = None) -> int:
        sql = "SELECT COALESCE(SUM(LENGTH(text)), 0) FROM agent_notes WHERE agent_name = ?"
        params: tuple[Any, ...] = (name,)
        if exclude_id is not None:
            sql += " AND id != ?"
            params = (name, exclude_id)
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def _all_plain(self, name: str) -> list[tuple[str, int, str]]:
        async with self.conn.execute(
            "SELECT id, number, text FROM agent_notes WHERE agent_name = ?", (name,)
        ) as cur:
            return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    async def _switch_state(self, name: str) -> tuple[bool, int]:
        async with self.conn.execute(
            "SELECT notes_enabled, notes_next_number FROM agents WHERE name = ?", (name,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Agent config not found: {name}")
        return bool(row[0]), int(row[1])

    async def create(
        self,
        name: str,
        text: str,
        *,
        untrusted: bool,
        sources: list[str],
        origin_kind: str,
        origin_session_id: str | None,
        origin_label: str | None,
        origin_platform: str | None,
        origin_peer_id: str | None,
        origin_peer_name: str | None,
    ) -> tuple[AgentNote, bool]:
        """Save a note; return ``(note, created)``.

        A duplicate of an existing note writes nothing and returns that note
        with ``created=False``. Raises :class:`NotesDisabledError`,
        :class:`NoteLimitError`, ``ValueError`` (bad ``origin_kind``) or
        ``KeyError`` (no such agent).
        """
        if origin_kind not in ("web", "connector", "other"):
            raise ValueError(f"Invalid origin_kind: {origin_kind!r}")
        norm = validate_note_text(text)
        note_id = uuid.uuid4().hex
        now = now_iso()
        async with write_transaction(self.conn):
            enabled, number = await self._switch_state(name)
            if not enabled:
                raise NotesDisabledError()
            existing = await self._all_plain(name)
            key = dedup_key(norm)
            for _id, _num, etext in existing:
                if dedup_key(etext) == key:
                    dup = await self.get(name, _id)
                    assert dup is not None
                    return dup, False
            total = sum(len(t) for _i, _n, t in existing)
            if total + len(norm) > NOTES_TOTAL_MAX_CHARS:
                raise notes_total_limit_error(total, total + len(norm))
            await self.conn.execute(
                "INSERT INTO agent_notes (id, agent_name, number, text, untrusted, "
                "untrusted_sources, origin_kind, origin_session_id, origin_label, "
                "origin_platform, origin_peer_id, origin_peer_name, created_at, "
                "updated_at, updated_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'agent')",
                (
                    note_id,
                    name,
                    number,
                    norm,
                    1 if untrusted else 0,
                    json.dumps(_merge_sources([], sources)),
                    origin_kind,
                    origin_session_id,
                    origin_label,
                    origin_platform,
                    origin_peer_id,
                    origin_peer_name,
                    now,
                    now,
                ),
            )
            await self.conn.execute(
                "UPDATE agents SET notes_next_number = notes_next_number + 1 WHERE name = ?",
                (name,),
            )
        created = await self.get(name, note_id)
        assert created is not None
        return created, True

    async def _update_locked(
        self,
        name: str,
        match_sql: str,
        match_arg: Any,
        text: str,
        *,
        by: str,
        untrusted: bool = False,
        sources: Sequence[str] = (),
    ) -> tuple[AgentNote, bool]:
        """Shared body of the two update paths; call INSIDE the transaction."""
        norm = validate_note_text(text)
        async with self.conn.execute(
            f"SELECT id, number, text, untrusted, untrusted_sources FROM agent_notes "
            f"WHERE agent_name = ? AND {match_sql}",
            (name, match_arg),
        ) as cur:
            cur_row = await cur.fetchone()
        if cur_row is None:
            raise KeyError(f"Note not found: {match_arg}")
        note_id, _number, old_text = cur_row[0], cur_row[1], cur_row[2]
        if norm == old_text:
            current = await self.get(name, note_id)
            assert current is not None
            return current, False
        key = dedup_key(norm)
        for oid, onum, otext in await self._all_plain(name):
            if oid != note_id and dedup_key(otext) == key:
                raise NoteDuplicateError(f"Already saved as note [{onum}].", onum)
        others = await self.total_chars(name, exclude_id=note_id)
        if others + len(norm) > NOTES_TOTAL_MAX_CHARS:
            raise notes_total_limit_error(others + len(old_text), others + len(norm))
        now = now_iso()
        if by == "agent":
            try:
                old_sources = json.loads(cur_row[4]) if cur_row[4] else []
            except ValueError:
                old_sources = []
            new_flag = bool(cur_row[3]) or untrusted
            new_sources = _merge_sources(old_sources, sources)
            await self.conn.execute(
                "UPDATE agent_notes SET text = ?, untrusted = ?, untrusted_sources = ?, "
                "updated_at = ?, updated_by = 'agent' WHERE id = ?",
                (norm, 1 if new_flag else 0, json.dumps(new_sources), now, note_id),
            )
        else:
            await self.conn.execute(
                "UPDATE agent_notes SET text = ?, untrusted = 0, untrusted_sources = '[]', "
                "updated_at = ?, updated_by = 'operator' WHERE id = ?",
                (norm, now, note_id),
            )
        updated = await self.get(name, note_id)
        assert updated is not None
        return updated, True

    async def update_by_agent(
        self,
        name: str,
        number: int,
        text: str,
        *,
        untrusted: bool,
        sources: list[str],
    ) -> tuple[AgentNote, bool]:
        """Agent edit by number; return ``(note, changed)``.

        ORs ``untrusted`` into the stored flag and merges ``sources`` (capped);
        keeps ``origin_*``. Identical text is an allowed no-op
        (``changed=False``). Raises ``KeyError`` on a miss.
        """
        async with write_transaction(self.conn):
            enabled, _ = await self._switch_state(name)
            if not enabled:
                raise NotesDisabledError()
            return await self._update_locked(
                name,
                "number = ?",
                number,
                text,
                by="agent",
                untrusted=untrusted,
                sources=sources,
            )

    async def update_by_operator(
        self, name: str, note_id: str, text: str
    ) -> tuple[AgentNote, bool]:
        """Operator edit by id; no switch check (DD11).

        A real text change clears the unverified flag and its sources (the
        operator has reviewed and rewritten it); identical text is a no-op
        that keeps the flag. Returns ``(note, changed)``.
        """
        async with write_transaction(self.conn):
            return await self._update_locked(name, "id = ?", note_id, text, by="operator")

    async def forget_by_agent(self, name: str, number: int) -> AgentNote:
        """Delete a note by number (switch re-checked); return the deleted note."""
        async with write_transaction(self.conn):
            enabled, _ = await self._switch_state(name)
            if not enabled:
                raise NotesDisabledError()
            note = await self.get_by_number(name, number)
            if note is None:
                raise KeyError(f"Note not found: {number}")
            await self.conn.execute("DELETE FROM agent_notes WHERE id = ?", (note.id,))
        return note

    async def delete(self, name: str, note_id: str) -> None:
        async with write_transaction(self.conn):
            if await self.get(name, note_id) is None:
                raise KeyError(f"Note not found: {note_id}")
            await self.conn.execute(
                "DELETE FROM agent_notes WHERE agent_name = ? AND id = ?", (name, note_id)
            )

    async def clear(self, name: str) -> int:
        """Delete all of an agent's notes; the number counter is left alone."""
        async with write_transaction(self.conn):
            cur = await self.conn.execute("DELETE FROM agent_notes WHERE agent_name = ?", (name,))
            return cur.rowcount or 0


# ── Agent revision repository ────────────────────────────────────────────


class AgentRevisionRepository:
    """Async access to the ``agent_revisions`` revision log (M21 F02 L01).

    No encryptor (mirrors the now-deleted ``PendingApprovalRepository``
    precedent): the logged
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
        mirroring the now-deleted ``PendingApprovalRepository.upsert_pending``.

        M21 F03 L02 (DD3): ``source_principal`` records the external
        credential identifier for ``source='external'`` rows (NULL for
        ``self`` / ``restore``).
        """
        revision_id = uuid.uuid4().hex
        async with write_transaction(self.conn):
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

        Scoped to ``agent_name`` (unlike the now-deleted connector
        ``PendingApprovalRepository.count_pending``, which was global) —
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
        ``(new_row, True)`` — mirroring the now-deleted
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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agent_revisions "
                "SET proposed_value = ?, base_value = ?, created_at = ?, "
                "    source = ?, source_principal = ? "
                "WHERE id = ?",
                (proposed_value, base_value, ts, source, source_principal, revision_id),
            )
        return await self.get(revision_id), False

    async def mark_applied(self, revision_id: str) -> AgentRevision:
        return await self._transition(revision_id, "applied")

    async def mark_dismissed(self, revision_id: str) -> AgentRevision:
        return await self._transition(revision_id, "dismissed")

    async def _transition(
        self, revision_id: str, target: Literal["applied", "dismissed"]
    ) -> AgentRevision:
        """Transition a ``pending`` row to a terminal state.

        Copies the now-deleted ``PendingApprovalRepository._transition`` semantics:
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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agent_revisions SET status = ?, resolved_at = ? WHERE id = ?",
                (target, now_iso(), revision_id),
            )
        return await self.get(revision_id)

    async def update_base_value(self, revision_id: str, base_value: str) -> AgentRevision:
        """Re-capture ``base_value`` to a new value (DD4 approve override).

        Used only on the override path when the operator elects to
        overwrite a drifted field — the endpoint re-captures ``base_value``
        to the current stored value before applying, so the applied row
        records the base it actually overwrote.
        """
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE agent_revisions SET base_value = ? WHERE id = ?",
                (base_value, revision_id),
            )
        return await self.get(revision_id)

    async def supersede_pending(self, agent_name: str) -> int:
        """Mark every outstanding ``pending`` row for an agent ``superseded`` (DD8).

        Called when the self-configuration surface is disabled — a
        revision proposed under a since-revoked surface must not be
        approvable afterward. Returns the number of rows superseded.
        """
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "UPDATE agent_revisions SET status = 'superseded', resolved_at = ? "
                "WHERE agent_name = ? AND status = 'pending'",
                (now_iso(), agent_name),
            ) as cur:
                rowcount = cur.rowcount
        return rowcount

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
    The resolver makes no repository call: `AgentFactory.create()` reads
    `list()` and passes each tool's config dict to the resolver.

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
        async with write_transaction(self.conn):
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

    async def delete(self, name: str) -> None:
        if not await self.exists(name):
            raise KeyError(f"Tool config not found: {name}")
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM tool_configs WHERE name = ?", (name,))

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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "INSERT INTO app_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    async def delete(self, key: str) -> None:
        """Delete ``key`` if present; a no-op if absent (Flight 7 Leg 2,
        AC-11a). Added so a kv key that falls outside ``kb_items``' FK
        cascade — e.g. DD-7's per-folder walk-skip-counter key — can be
        cleaned up explicitly by its owning delete path."""
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM app_metadata WHERE key = ?", (key,))


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

    async def list_summaries(self) -> list[ChatSession]:
        """Like :meth:`list` (all sessions, newest first) but without reading
        the ``messages`` or ``session_metadata`` columns (they come back as
        NULL, so ``messages`` defaults to ``"[]"``). For list payloads."""
        sql = (
            "SELECT id, agent_name, title, created_at, updated_at, platform,"
            " connector_id, channel_id, thread_id, peer_id, last_inbound_at,"
            " NULL AS messages, NULL AS session_metadata"
            " FROM chat_sessions ORDER BY updated_at DESC"
        )
        async with self.conn.execute(sql) as cur:
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

        M10 F03 L03 — consumed by the connector dispatcher's session
        resolver (deleted with the connector package, Mission 23 Flight 1;
        this session-keying method itself is kept for Flight 2).
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
        async with write_transaction(self.conn):
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
        notify_sessions_changed()

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
        ``the_one/interfaces/web/app.py:469-487``; formerly also the
        connector dispatcher's inbound handler, deleted with the
        connector package at Mission 23 Flight 1). The
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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE chat_sessions SET title=?, messages=?, updated_at=? WHERE id=?",
                (session.title, session.messages, now_iso(), session.id),
            )
        notify_sessions_changed()

    async def delete(self, session_id: str) -> None:
        async with self.conn.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Chat session not found: {session_id}")
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        notify_sessions_changed()

    async def delete_all_for_agent(self, agent_name: str) -> int:
        """Delete every chat session for an agent (interactive AND
        connector-keyed) and return the number of rows removed.

        Name-keyed (agents have no id column; agents.name is the PK).
        Idempotent: returns 0 for an agent with no sessions and never
        raises for a missing agent — the FK was dropped at schema v5,
        so this neither cascades nor is blocked. Rename-safe because
        rename() re-points chat_sessions.agent_name in one transaction.
        """
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "DELETE FROM chat_sessions WHERE agent_name = ?", (agent_name,)
            ) as cur:
                count = cur.rowcount
        if count:
            notify_sessions_changed()
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
            async with write_transaction(self.conn):
                await self.conn.execute(
                    "DELETE FROM chat_sessions WHERE agent_name = ? AND updated_at < ?",
                    (agent_name, cutoff),
                )
            notify_sessions_changed()
        return ids

    async def purge_messages(self, session_id: str) -> None:
        """Clear messages for a session but keep the session itself."""
        async with self.conn.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Chat session not found: {session_id}")
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE chat_sessions SET messages='[]', updated_at=? WHERE id=?",
                (now_iso(), session_id),
            )
        notify_sessions_changed()

    async def existing_ids(self, ids: Iterable[str]) -> set[str]:
        """Which of *ids* are chat sessions that still exist (one ``IN`` query)."""
        wanted = list(dict.fromkeys(i for i in ids if i))
        found: set[str] = set()
        # SQLite caps bound variables; page the query well under the old 999 limit.
        for start in range(0, len(wanted), 500):
            chunk = wanted[start : start + 500]
            marks = ", ".join("?" for _ in chunk)
            async with self.conn.execute(
                f"SELECT id FROM chat_sessions WHERE id IN ({marks})", chunk
            ) as cur:
                found.update(row[0] for row in await cur.fetchall())
        return found

    async def update_last_inbound(self, session_id: str, when: str) -> None:
        """Bump the connector-driven activity timestamps for a session.

        Touches both ``last_inbound_at`` (consumed by the connector
        dispatcher's session resolver's continuation-window check,
        deleted with the connector package at Mission 23 Flight 1) and
        ``updated_at`` (the most-recent-by-updated_at ordering that
        resolver used to pick the active row when multiple historical
        rows exist for the same external key).

        Raises ``KeyError`` if the session doesn't exist — mirrors
        :meth:`update` / :meth:`delete` / :meth:`purge_messages`
        not-found semantics.

        M10 F03 L04 — narrow primitive formerly consumed by the
        connector dispatcher's inbound handler (deleted with the
        connector package). The seven connector-identity columns are
        intentionally not touched — see :meth:`update`'s docstring for
        the identity-columns contract.
        """
        async with self.conn.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
        ) as cur:
            if await cur.fetchone() is None:
                raise KeyError(f"Chat session not found: {session_id}")
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE chat_sessions SET last_inbound_at = ?, updated_at = ? WHERE id = ?",
                (when, when, session_id),
            )
        notify_sessions_changed()

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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE chat_sessions SET session_metadata = ? WHERE id = ?",
                (json.dumps(metadata), session_id),
            )

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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE chat_sessions SET session_metadata = ? WHERE id = ?",
                (json.dumps(metadata), session_id),
            )

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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "INSERT INTO llm_providers (id, name, type, base_url, api_key, config,"
                " secrets, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._to_row(provider),
            )

    async def update(self, provider: LLMProviderConfig) -> None:
        if not await self._exists(provider.id):
            raise KeyError(f"Provider not found: {provider.id}")
        async with write_transaction(self.conn):
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
        async with write_transaction(self.conn):
            await self.conn.execute(
                "UPDATE llm_providers SET secrets=?, updated_at=? WHERE id=?",
                (
                    _encrypt_secrets_blob(self.encryptor, secrets),
                    now_iso(),
                    provider_id,
                ),
            )

    async def delete(self, provider_id: str) -> None:
        if not await self._exists(provider_id):
            raise KeyError(f"Provider not found: {provider_id}")
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))

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
        async with write_transaction(self.conn):
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
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "DELETE FROM agent_external_credentials WHERE identifier = ?",
                (identifier,),
            ) as cur:
                rowcount = cur.rowcount
        return rowcount > 0

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

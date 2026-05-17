# Leg: v16-schema-migration

**Status**: completed
**Flight**: [Session Model — Schema, Key Normalization, Visibility](../flight.md)

## Objective

Land the v16 schema migration that extends `chat_sessions` with the seven nullable connector-session columns (`platform`, `connector_account_id`, `channel_id`, `thread_id`, `peer_id`, `session_metadata`, `last_inbound_at`), adds the partial lookup index `idx_chat_sessions_external_key`, extends `connector_accounts` with `session_continuation_seconds`, and round-trips both shapes through their Pydantic models and repositories.

## Context

- **Parent flight design decisions** (see `flight.md`):
  - Per-row nullable columns on `chat_sessions`, not a join table.
  - Non-unique partial expression index for external-key lookup; most-recent-by-`updated_at` semantics consumed by leg 3.
  - `session_continuation_seconds` sibling to F2's `idle_timeout_seconds` with identical `1 ≤ value ≤ 604800` validator.
  - F3 grabs v16; Flight 8 renumbers its CHECK migration to v17 (mirror of F1 v14 → bumped F8 to v15, F2 v15 → bumped F8 to v16).
- **Two-pass planning-grep convention** (codified post-F2 in this flight's design): every column ALTER planning audit must check (a) head-version assertion sites AND (b) column-set assertion sites. Both are enumerated below in Implementation Guidance.
- **Schema-version renumber pattern**: F1 leg 2 (v14 `name`) and F2 leg 1 (v15 `idle_timeout_seconds`) are the templates. Each landed a single ALTER ADD COLUMN block, PRAGMA-guarded for idempotency, with `INSERT OR IGNORE INTO schema_version` LAST. Leg 1 follows the same shape, plus the `CREATE INDEX IF NOT EXISTS` for the new lookup index.
- **SQLite version**: container ships `python:3.11-slim` with SQLite ≥3.37; expression indexes (3.9+) and partial indexes (3.8+) are both supported. `COALESCE(thread_id, '')` in the index expression is fine.

## Inputs

State that must exist before this leg runs:

- `the_one/db/schema.py:11 — "CURRENT_VERSION = 15"`
- `the_one/db/schema.py:538 — "if version < 15:"` (v15 ALTER block — template for v16 block)
- `the_one/db/models.py:118 — "class ConnectorAccount(BaseModel):"` (extant with `idle_timeout_seconds`)
- `the_one/db/models.py:181 — "class ChatSession(BaseModel):"` (extant 6-field shape)
- `the_one/db/repositories.py:487 — "async def list(self) -> list[ConnectorAccount]:"` (`ConnectorAccountRepository`'s round-trip)
- `the_one/db/repositories.py:658 — "class ChatSessionRepository:"` (extant)
- `tests/test_db_migration.py:203 — "class TestSchemaV8:"` (head-version assertion site)
- `tests/test_db_migration.py:229 — "assert CURRENT_VERSION == 15"` (bump target)
- `tests/test_db_migration.py:1110 — "class TestSchemaV13:"` (docstring at :1157 / :1163 references v16 for F8 CHECK — bumps to v17; **column-set assertion at :1176-1185** is the exact-set equality site that needs `"session_continuation_seconds"` added — the design-review caught this as the canonical "column-set assertion site" that the two-pass-planning-grep convention exists to catch)
- `tests/test_db_migration.py:1234 — "class TestSchemaV14:"` (docstring references v16 for F8 CHECK — bumps to v17)
- `tests/test_db_migration.py:1383 — "class TestSchemaV15:"` (template for new TestSchemaV16 class; docstring at :1390-1393 narrates the v14→v15→v16 renumber history — update or accept historical framing per Step 11b below)
- `the_one/db/schema.py:546-548` (v15 block's OWN downstream-renumber comment — "Downstream: flight 08 (Discord) previously planned a v15 CHECK migration; that renumbers to v16." → must become "renumbers to v17.")
- `the_one/db/_connector_types.py:11 — "**deferred to flight 8**"` (docstring references v16 for F8 CHECK — bumps to v17)
- `the_one/agents.md:290 — "**SQLite `CHECK` constraint**"` (connector-type checklist item 4 — F8 CHECK references v16 → v17)
- `the_one/agents.md:344 — "**Flight 3 ratification needed for `last_activity` tracking**"` (Known Issue carry-forward; LEG 4 updates it after the dispatcher lands; leg 1 leaves untouched)
- Flight 3 status is `in-flight` (the `/agentic-workflow` skill flipped this before spawning leg 1).
- Working tree on branch `flight/03-session-model-key-and-visibility`.

## Outputs

State that must exist after this leg completes:

- `the_one/db/schema.py:11` → `CURRENT_VERSION = 16`
- New v16 migration block in `the_one/db/schema.py` (after the v15 block) that ADDs 7 columns to `chat_sessions`, 1 column to `connector_accounts`, and creates the partial expression index.
- `ChatSession` Pydantic model in `the_one/db/models.py` has 7 new fields: `platform: str | None`, `connector_account_id: str | None`, `channel_id: str | None`, `thread_id: str | None`, `peer_id: str | None`, `session_metadata: dict[str, Any] | None`, `last_inbound_at: str | None`, all defaulting to `None`.
- `ConnectorAccount` Pydantic model has new field `session_continuation_seconds: int | None = None` with `_validate_session_continuation_seconds` field validator enforcing `1 ≤ value ≤ 604800`.
- `ChatSessionRepository` round-trips the seven new columns on `create`, `update`, `get`, `list`, and `_row_to_model` (read-path + write-path complete).
- `ConnectorAccountRepository` round-trips `session_continuation_seconds` on `create`, `update`, `_row_to_model`.
- `tests/test_db_migration.py::TestSchemaV8` bumped: `assert CURRENT_VERSION == 16` with updated error-message string citing F3 L1.
- `tests/test_db_migration.py::TestSchemaV14` docstring: every reference to F8 CHECK landing at v16 becomes v17.
- New `TestSchemaV16` class added to `tests/test_db_migration.py` paralleling `TestSchemaV15` (fresh-DB column pin, idempotent-on-rerun, legacy-v15-row-decodes-with-NULL-on-new-cols).
- `the_one/db/_connector_types.py:11-15` docstring updated: v16 entry inserted (F3 L1 — chat_sessions external-key columns + connector_accounts.session_continuation_seconds); F8 CHECK references v17.
- `the_one/agents.md:290` (connector-type checklist item 4): v16 entry inserted for F3 L1; F8 CHECK is v17.
- `tests/test_db_repositories.py` (or sibling): new tests covering ChatSession round-trip of the seven new fields and ConnectorAccount round-trip of `session_continuation_seconds`, including validator boundary cases (0 and 604801 rejected; 1, 86400, 604800, None accepted).
- Flight log (`flights/03-session-model-key-and-visibility/flight-log.md`) gains a "Leg Progress: v16-schema-migration" entry with timestamps, deviations (if any), and a citation to the resulting test counts.
- Leg status `completed` in this file's header.

## Acceptance Criteria

- [ ] `CURRENT_VERSION = 16` in `the_one/db/schema.py`
- [ ] v16 migration block exists in `the_one/db/schema.py` immediately after the v15 block, structured per the v14/v15 ALTER ADD COLUMN template (individual `await conn.execute()` calls, PRAGMA `table_info` guards per ALTER, `INSERT OR IGNORE INTO schema_version (version) VALUES (16)` as the LAST statement before commit)
- [ ] v16 migration adds exactly these 7 columns to `chat_sessions` (all `TEXT NULL` except `session_metadata` and `last_inbound_at` which are also `TEXT NULL`; `session_metadata` stores JSON as a string and is round-tripped through `json.loads`/`json.dumps` at the repository layer):
  - `platform TEXT NULL`
  - `connector_account_id TEXT NULL`
  - `channel_id TEXT NULL`
  - `thread_id TEXT NULL`
  - `peer_id TEXT NULL`
  - `session_metadata TEXT NULL`
  - `last_inbound_at TEXT NULL`
- [ ] v16 migration adds `session_continuation_seconds INTEGER NULL` to `connector_accounts`
- [ ] v16 migration creates partial expression index `idx_chat_sessions_external_key` on `chat_sessions(platform, connector_account_id, channel_id, COALESCE(thread_id, ''))` with `WHERE platform IS NOT NULL`, guarded by `CREATE INDEX IF NOT EXISTS` for idempotency
- [ ] Each `ALTER TABLE` is preceded by a `PRAGMA table_info(<table>)` check and the actual ALTER runs only if the column is missing (same pattern as v11/v14/v15)
- [ ] `ChatSession` Pydantic model has the 7 new fields, all with `None` default, all type-annotated correctly (`session_metadata: dict[str, Any] | None = None` — JSON storage layer at the repository, not in the model itself)
- [ ] `ConnectorAccount` Pydantic model has `session_continuation_seconds: int | None = None` field with a `_validate_session_continuation_seconds` `@field_validator` enforcing `1 ≤ value ≤ 604800` (raises `ValueError` with message `"session_continuation_seconds must be between 1 and 604800 seconds (7 days)"` for out-of-range; passes through `None`)
- [ ] `ChatSessionRepository.create` and `update` INSERT/UPDATE all 7 new columns
- [ ] `ChatSessionRepository._row_to_model` reads all 7 new columns (defaulting `session_metadata` to `None` when the column is NULL, parsing JSON when not)
- [ ] `ConnectorAccountRepository.create`, `update`, `_row_to_model` round-trip `session_continuation_seconds` (NULL-tolerant)
- [ ] `tests/test_db_migration.py::TestSchemaV8::test_v8_fresh_db_includes_tool_configs_and_tool_overrides`: `assert CURRENT_VERSION == 16` (was 15); error-message string updated to include the v16 entry citing F3 L1 ("M10 F03 L01 — chat_sessions external-key columns + connector_accounts.session_continuation_seconds")
- [ ] `tests/test_db_migration.py::TestSchemaV13` docstring at lines 1157 + 1163: F8 CHECK references update from v16 → v17
- [ ] `tests/test_db_migration.py::TestSchemaV13` column-set assertion at lines 1176-1185: extend the `set(cols) == {...}` literal to include `"session_continuation_seconds"` (this is the exact-set equality site that breaks immediately on the v16 ALTER — explicit handling required)
- [ ] `tests/test_db_migration.py::TestSchemaV14` docstring references to F8 CHECK landing at v16 are updated to v17
- [ ] `tests/test_db_migration.py::TestSchemaV15` docstring at lines 1390-1393: F8 CHECK renumber history updated (accept new wording: "then renumbered again to v16 once F2 L1 claimed v15; F3 L1 claimed v16 and F8 CHECK renumbered to v17")
- [ ] `the_one/db/schema.py:546-548` v15 block's downstream-renumber comment updated: "renumbers to v16" → "renumbers to v17"
- [ ] New `TestSchemaV16` class exists in `tests/test_db_migration.py` (after `TestSchemaV15`) with at least three tests:
  - `test_v16_fresh_db_includes_chat_session_external_key_columns` — asserts all 7 new chat_sessions columns + `session_continuation_seconds` on connector_accounts + presence of `idx_chat_sessions_external_key` in `sqlite_master`
  - `test_v16_migration_idempotent_on_rerun` — second `ensure_schema` call is a no-op (no duplicate schema_version row, columns still present)
  - `test_v16_legacy_v15_row_decodes_with_null_external_key_columns` — hand-builds a v15-shape `chat_sessions` and `connector_accounts` table, seeds rows, sets `schema_version` to 15, runs `ensure_schema`, asserts seeded rows survive with NULLs on all new columns
- [ ] `the_one/db/_connector_types.py:11-15` docstring updated: insert "v16 → chat_sessions external-key columns + connector_accounts.session_continuation_seconds (F3 L1)"; F8 CHECK becomes v17
- [ ] `the_one/agents.md:290` (connector-type checklist item 4) updated parallel to the `_connector_types.py` docstring: v16 entry inserted; F8 CHECK is v17
- [ ] New tests covering ChatSession and ConnectorAccount round-trip of the new fields in `tests/test_db_repositories.py` (or a new sibling test file if naming conventions dictate)
- [ ] `make test` clean (no regressions; new test count is added)
- [ ] `make lint` clean (no new ruff findings)
- [ ] Flight log updated with leg-completion entry citing test counts before/after, deviations encountered (if any), and any unforeseen findings
- [ ] Leg status flipped to `completed` in this file's header

## Verification Steps

For each acceptance criterion:

- **`CURRENT_VERSION = 16`** — `grep -n "CURRENT_VERSION = " the_one/db/schema.py` returns line 11 with value 16.
- **v16 block exists & is structured correctly** — Read `the_one/db/schema.py` after the v15 block; confirm structure matches v14/v15 (PRAGMA guard → ALTER → INSERT OR IGNORE LAST → commit).
- **7 chat_sessions ALTERs + 1 connector_accounts ALTER + 1 CREATE INDEX** — Run the migration against a temp DB and check `PRAGMA table_info(chat_sessions)` / `PRAGMA table_info(connector_accounts)` / `SELECT name FROM sqlite_master WHERE type='index'`.
- **Idempotency** — Run `ensure_schema` twice on a fresh DB; assert `SELECT version FROM schema_version` shows v16 exactly once (`TestSchemaV16.test_v16_migration_idempotent_on_rerun`).
- **Forward compatibility** — `TestSchemaV16.test_v16_legacy_v15_row_decodes_with_null_external_key_columns` exercises the legacy-row path.
- **Pydantic round-trip** — `tests/test_db_repositories.py` tests create then read; assert all new fields preserved (including JSON encoding for `session_metadata`).
- **Validator boundary** — Pydantic test: `ConnectorAccount(id=..., name=..., type=..., session_continuation_seconds=0)` raises; `=604801` raises; `=1`, `=86400`, `=604800`, `=None` pass.
- **Renumber sites updated** — `grep -n "v16\|F3 L1" the_one/db/_connector_types.py the_one/agents.md the_one/db/schema.py` shows the v16 entry in all three plus the v15 block's downstream-renumber comment; `grep -n "v17" the_one/db/_connector_types.py the_one/agents.md the_one/db/schema.py` shows F8 CHECK now references v17 in all three.
- **TestSchemaV8 bump** — `grep -n "assert CURRENT_VERSION ==" tests/test_db_migration.py` shows `== 16` at the TestSchemaV8 site.
- **TestSchemaV13 column-set assertion update** — `grep -n "session_continuation_seconds" tests/test_db_migration.py` shows the column in the TestSchemaV13 set literal at lines 1176-1185.
- **TestSchemaV13 + TestSchemaV14 + TestSchemaV15 docstring updates** — `grep -n "v17" tests/test_db_migration.py` shows v17 wording in all three test-class docstrings.
- **`make test`** — In container: `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py -x --timeout 60 -v`; then full suite `docker exec the-one pytest -x --timeout 60` for the regression gate. Both must pass.
- **`make lint`** — `docker exec the-one ruff check .` (or whatever the project recipe is — check Makefile if uncertain).

## Implementation Guidance

1. **Bump `CURRENT_VERSION`** at `the_one/db/schema.py:11` from `15` to `16`.

2. **Update the v15 block's downstream-renumber comment** at `the_one/db/schema.py:546-548`. The current text reads "Downstream: flight 08 (Discord) previously planned a v15 CHECK migration; that renumbers to v16." → becomes "renumbers to v17." This is a low-effort but high-traceability fix the design-review flagged (each migration block carries a `Downstream: …` comment naming where F8 currently sits in the schema-version queue).

3. **Add the v16 migration block** at the end of `ensure_schema()` (after the v15 block at line ~538-561). Template structure (PRAGMA-guarded ALTER + CREATE INDEX + INSERT OR IGNORE LAST):

   ```python
   if version < 16:
       # Mission 10 Flight 3 Leg 1: chat-session connector keying + session
       # continuation timeout.
       #
       # ADDs seven nullable columns to chat_sessions that hold the external
       # conversation identity (platform, connector_account_id, channel_id,
       # thread_id, peer_id), plus a JSON metadata column (session_metadata;
       # F7 routing-decision logs piggyback so we only migrate once) and a
       # timestamp column (last_inbound_at) for the resolver's
       # continuation-window check. All NULL on non-connector sessions; the
       # partial index below makes the lookup fast for connector-keyed rows
       # without paying for the (much larger) non-connector set.
       #
       # ADDs session_continuation_seconds to connector_accounts (sibling
       # to v15's idle_timeout_seconds — the per-connector chat-session
       # continuation window; defaults to 86400=24h via the resolver, NOT
       # via a column DEFAULT, so NULL means "use resolver default").
       #
       # CREATEs the partial expression index for the external-key lookup.
       # SQLite ≥3.9 supports expression indexes; COALESCE in the indexed
       # expression list normalises NULL thread_id matches against the
       # resolver's COALESCE(?, '') WHERE clause.
       #
       # Downstream: flight 08 (Discord) previously planned a v16 CHECK
       # migration; that renumbers to v17. See _connector_types.py docstring
       # + tests/test_db_migration.py TestSchemaV14 docstring + agents.md
       # connector-type checklist item 4.
       #
       # Idempotency follows the v11/v14/v15 ALTER ADD COLUMN pattern
       # (PRAGMA guard per column + CREATE INDEX IF NOT EXISTS + INSERT OR
       # IGNORE on schema_version LAST).
       async with conn.execute("PRAGMA table_info(chat_sessions)") as cursor:
           existing_chat_cols = {row[1] for row in await cursor.fetchall()}
       for col, ddl_type in (
           ("platform", "TEXT"),
           ("connector_account_id", "TEXT"),
           ("channel_id", "TEXT"),
           ("thread_id", "TEXT"),
           ("peer_id", "TEXT"),
           ("session_metadata", "TEXT"),
           ("last_inbound_at", "TEXT"),
       ):
           if col not in existing_chat_cols:
               await conn.execute(
                   f"ALTER TABLE chat_sessions ADD COLUMN {col} {ddl_type} NULL"
               )

       async with conn.execute("PRAGMA table_info(connector_accounts)") as cursor:
           existing_acc_cols = {row[1] for row in await cursor.fetchall()}
       if "session_continuation_seconds" not in existing_acc_cols:
           await conn.execute(
               "ALTER TABLE connector_accounts ADD COLUMN session_continuation_seconds INTEGER NULL"
           )

       await conn.execute(
           "CREATE INDEX IF NOT EXISTS idx_chat_sessions_external_key "
           "ON chat_sessions(platform, connector_account_id, channel_id, COALESCE(thread_id, '')) "
           "WHERE platform IS NOT NULL"
       )

       await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (16,))
       await conn.commit()
       version = 16
   ```

   Verify the snippet's exact placement: AFTER `version = 15` (line 561) and at the SAME indentation level as the v15 block. Do NOT use `executescript` (it auto-COMMITs before the first DDL and breaks idempotency — see the per-block comment at the v8 block).

4. **Extend `ChatSession` Pydantic model** at `the_one/db/models.py:181`:

   ```python
   class ChatSession(BaseModel):
       """A chat session with message history.

       Mission 10 Flight 3 Leg 1: connector-keyed sessions add the
       (platform, connector_account_id, channel_id, thread_id, peer_id)
       quintuple plus a JSON metadata column and a last_inbound_at
       timestamp. All seven default to None for non-connector sessions
       (back-compat) and are populated by the inbound dispatcher
       (leg 4) for connector-driven sessions.

       The (platform, connector_account_id, channel_id, COALESCE(thread_id, ''))
       4-tuple is the lookup key consumed by leg 3's resolver against the
       partial expression index ``idx_chat_sessions_external_key``.
       ``peer_id`` is stored for audit and future per-peer-scoped sessions
       (Flight 6 territory) but is NOT part of the lookup key.
       """

       id: str
       agent_name: str | None = None
       title: str = "New chat"
       messages: str = "[]"  # JSON-encoded via codec
       created_at: str = Field(default_factory=_now_iso)
       updated_at: str = Field(default_factory=_now_iso)
       # M10 F03 L01: connector-session external key + metadata
       platform: str | None = None
       connector_account_id: str | None = None
       channel_id: str | None = None
       thread_id: str | None = None
       peer_id: str | None = None
       session_metadata: dict[str, Any] | None = None
       last_inbound_at: str | None = None
   ```

   `session_metadata` is `dict[str, Any] | None` in the model; the repository layer encodes via `json.dumps` on write and decodes via `json.loads` on read (parallel to how `ChatSession.messages` is a string in the model but encoded JSON content).

5. **Extend `ConnectorAccount` Pydantic model** at `the_one/db/models.py:118`:

   ```python
   class ConnectorAccount(BaseModel):
       # ... existing fields ...
       idle_timeout_seconds: int | None = None
       session_continuation_seconds: int | None = None  # M10 F03 L01
       created_at: str = Field(default_factory=_now_iso)
       updated_at: str = Field(default_factory=_now_iso)

       # ... existing _validate_idle_timeout_seconds ...

       @field_validator("session_continuation_seconds")
       @classmethod
       def _validate_session_continuation_seconds(cls, value: int | None) -> int | None:
           """Bound the per-account chat-session continuation window to
           ``[1, 604800]`` seconds.

           ``None`` means "no per-account override — fall through to the
           env var / default in
           ``the_one.connectors._session._resolve_continuation_seconds``"
           (the resolver lands in F3 L3; the field exists from this leg
           so the repository round-trip is complete before the resolver
           consumes it).

           Same `1 ≤ value ≤ 604800` bounds as ``idle_timeout_seconds``
           (the 7-day upper bound catches the ms-vs-s typo; the lower
           bound rejects zero / negative). These two are independent
           timeouts — pool warm-entry TTL vs. chat-session continuation
           window — that happen to share an envelope.
           """
           if value is None:
               return value
           if not (1 <= value <= 604800):
               raise ValueError(
                   "session_continuation_seconds must be between 1 and 604800 seconds (7 days)"
               )
           return value
   ```

6. **Extend `ChatSessionRepository`** at `the_one/db/repositories.py:658`:

   - **`create()`** at line 683: extend the INSERT to include all 7 new columns. The SQL becomes:
     ```python
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
             json.dumps(session.session_metadata) if session.session_metadata is not None else None,
             session.last_inbound_at,
         ),
     )
     ```
   - **`update()`** at line 698: leave existing UPDATE shape (still `title, messages, updated_at` only) — the connector-session columns are NOT mutated by `update()` because they're identity columns set once at create. Leg 4's dispatcher uses dedicated `append_messages` and `update_last_inbound` primitives (defined in leg 4) for the per-inbound mutations; leg 3's resolver creates the row with the connector identity at first contact. **Document this in `update()`'s docstring** (not just a code comment) so the contract is visible to anyone calling the method via `help()` / IDE hover. Specifically cite the known caller `the_one/interfaces/web/app.py:479-485` (`_save_session_to_db` does `db_session.model_copy(update={"title": ..., "messages": ...})` → `repo.update(updated)` — the SQL not touching the connector identity columns is what preserves them across operator-driven saves). Suggested docstring snippet:
     ```python
     async def update(self, session: ChatSession) -> None:
         """Update the mutable session fields (title, messages, updated_at).

         The seven connector-keyed identity columns (platform,
         connector_account_id, channel_id, thread_id, peer_id,
         session_metadata, last_inbound_at) added by M10 F03 L01 are
         intentionally NOT round-tripped by this method — they are
         identity attributes set once at row creation (by the resolver
         in M10 F03 L03) and mutated only through the narrow primitives
         ``append_messages`` and ``update_last_inbound`` (M10 F03 L04).
         Existing callers like ``_save_session_to_db`` at
         ``the_one/interfaces/web/app.py:479-485`` round-trip a fetched
         ChatSession through ``repo.update(updated)`` for title / message
         edits; the connector-identity columns are preserved across that
         path because this SQL does not touch them.
         """
         # ... existing body unchanged ...
     ```
   - **`_row_to_model()`** at line 732: extend to read the 7 new columns. **Defensive normalization** on `session_metadata` — accept dict-shaped JSON only (handles potential corruption / external tampering where the column might contain a non-dict literal like `"hello"` or `42`):
     ```python
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
     ```
   - Add `import json` at the top of `repositories.py` if not already imported (`ConnectorAccountRepository` already imports it for `json.dumps(account.config)` at line 512 — confirm and reuse).

7. **Extend `ConnectorAccountRepository`** at `the_one/db/repositories.py:487`:

   - **`create()`** at line 502: extend INSERT column list and parameters to include `session_continuation_seconds` (insert between `idle_timeout_seconds` and `created_at` to keep the per-field order parallel to the model). The new INSERT:
     ```python
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
     ```
   - **`update()`** at line 521: extend UPDATE column list parallel to `create()`:
     ```python
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
             _now_iso(),
             account.id,
         ),
     )
     ```
   - **`_row_to_model()`** at line 554: extend to read `session_continuation_seconds`:
     ```python
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
     ```

8. **Update `TestSchemaV8` head-version assertion** at `tests/test_db_migration.py:203`:
   - Line 229: `assert CURRENT_VERSION == 15` → `assert CURRENT_VERSION == 16`
   - Lines 226-232 (the comment + error-message block): append "v16 added chat_sessions external-key columns + connector_accounts.session_continuation_seconds (M10 F03 L01)." to the version-history comment AND to the assert's error-message string.

9. **Update `TestSchemaV13` docstring and column-set assertion** at `tests/test_db_migration.py:1110`:
   - **Lines 1157 and 1163** (docstring): every reference to "v16" for the F8 CHECK becomes "v17"; the docstring tells the consistent story (v14 → name; v15 → idle_timeout_seconds; v16 → chat_sessions external-key + session_continuation_seconds; v17 → F8 CHECK).
   - **Lines 1176-1185** (the `test_v13_connector_accounts_has_expected_columns_and_no_check_constraint` set-equality assertion): extend the `set(cols) == { … }` literal to include `"session_continuation_seconds"`. This is the highest-severity site the design-review caught — without this fix, the test fails immediately on first run.

10. **Update `TestSchemaV14` docstring** at `tests/test_db_migration.py:1234`:
    - Line 1245: "renumbers to v16" → "renumbers to v17"
    - Update the surrounding context as needed so the docstring tells a consistent story (v14 → name; v15 → idle_timeout_seconds; v16 → chat_sessions external-key + session_continuation_seconds; v17 → F8 CHECK).

11. **Update `TestSchemaV15` docstring** at `tests/test_db_migration.py:1383`:
    - Lines 1390-1393: the renumber history narrative becomes "then renumbered again to v16 once F2 L1 claimed v15; F3 L1 claimed v16 and F8 CHECK renumbered to v17." Keeps the narrative current.

12. **Add new `TestSchemaV16` class** to `tests/test_db_migration.py` AFTER `TestSchemaV15` (the file is 1532 lines total; TestSchemaV15 ends near line 1532 — confirm by reading the end of TestSchemaV15 first; the placement is immediately after its last method). Mirror the `TestSchemaV15` three-test shape:

   ```python
   class TestSchemaV16:
       """Tests for the v16 migration that adds chat_sessions connector-keying
       columns + connector_accounts.session_continuation_seconds.

       Mission 10 flight 03 leg 01: per-row nullable columns on chat_sessions
       hold the external conversation identity for connector-driven sessions;
       a non-unique partial expression index on
       (platform, connector_account_id, channel_id, COALESCE(thread_id, ''))
       supports the resolver's most-recent-by-updated_at lookup.
       session_continuation_seconds on connector_accounts is the per-account
       continuation window consumed by the resolver (F3 L3).

       Downstream: flight 08 (Discord) previously planned a v16 CHECK
       migration; that renumbers to v17. See flight log
       ``## Design Adjustments`` and _connector_types.py docstring.
       """

       async def test_v16_fresh_db_includes_chat_session_external_key_columns(
           self, tmp_path
       ) -> None:
           """Fresh DB → ensure_schema → v16 surfaces exist."""
           db_path = tmp_path / "v16-fresh.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")

           await ensure_schema(conn)

           assert CURRENT_VERSION >= 16, CURRENT_VERSION

           # All seven new chat_sessions columns are present and nullable.
           async with conn.execute("PRAGMA table_info(chat_sessions)") as cur:
               cols = {r["name"]: r for r in await cur.fetchall()}
           for expected in (
               "platform",
               "connector_account_id",
               "channel_id",
               "thread_id",
               "peer_id",
               "session_metadata",
               "last_inbound_at",
           ):
               assert expected in cols, (
                   f"v16 migration missing: chat_sessions.{expected} does not exist"
               )
               assert cols[expected]["type"] == "TEXT", cols[expected]["type"]
               assert cols[expected]["notnull"] == 0, cols[expected]["notnull"]
               assert cols[expected]["dflt_value"] is None, cols[expected]["dflt_value"]

           # connector_accounts.session_continuation_seconds is present.
           async with conn.execute("PRAGMA table_info(connector_accounts)") as cur:
               acc_cols = {r["name"]: r for r in await cur.fetchall()}
           assert "session_continuation_seconds" in acc_cols
           sc = acc_cols["session_continuation_seconds"]
           assert sc["type"] == "INTEGER", sc["type"]
           assert sc["notnull"] == 0, sc["notnull"]
           assert sc["dflt_value"] is None, sc["dflt_value"]

           # The partial expression index exists.
           async with conn.execute(
               "SELECT name FROM sqlite_master "
               "WHERE type='index' AND name='idx_chat_sessions_external_key'"
           ) as cur:
               row = await cur.fetchone()
           assert row is not None, (
               "v16 migration missing: idx_chat_sessions_external_key does not exist"
           )

           async with conn.execute(
               "SELECT version FROM schema_version ORDER BY version"
           ) as cur:
               versions = [r[0] for r in await cur.fetchall()]
           assert 16 in versions, versions
           assert max(versions) == CURRENT_VERSION, versions

           await conn.close()

       async def test_v16_migration_idempotent_on_rerun(self, tmp_path) -> None:
           """Calling ensure_schema twice on a fresh DB is a no-op the second
           time: no errors, no duplicate schema_version rows for v16, all
           seven chat_sessions columns + the connector_accounts column + the
           index still present."""
           db_path = tmp_path / "v16-rerun.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")

           await ensure_schema(conn)
           await ensure_schema(conn)

           async with conn.execute(
               "SELECT version FROM schema_version ORDER BY version"
           ) as cur:
               versions = [r[0] for r in await cur.fetchall()]
           assert versions.count(16) == 1, f"v16 row should appear exactly once: {versions}"

           async with conn.execute("PRAGMA table_info(chat_sessions)") as cur:
               cols = {r["name"] for r in await cur.fetchall()}
           for expected in (
               "platform",
               "connector_account_id",
               "channel_id",
               "thread_id",
               "peer_id",
               "session_metadata",
               "last_inbound_at",
           ):
               assert expected in cols
           async with conn.execute("PRAGMA table_info(connector_accounts)") as cur:
               acc_cols = {r["name"] for r in await cur.fetchall()}
           assert "session_continuation_seconds" in acc_cols

           await conn.close()

       async def test_v16_legacy_v15_row_decodes_with_null_external_key_columns(
           self, tmp_path
       ) -> None:
           """Rows seeded against a hand-built v15 schema (no v16 columns)
           survive the v16 ALTERs with NULLs on all new columns.

           Hand-builds the v15 shape of both chat_sessions AND
           connector_accounts so the v16 ALTERs actually run against pre-
           existing rows without the new columns. Modeled on
           ``TestSchemaV15.test_v15_legacy_v14_row_decodes_with_none_idle_timeout``.
           """
           db_path = tmp_path / "v16-from-real-v15.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")

           await conn.execute(
               "CREATE TABLE schema_version ("
               "    version INTEGER PRIMARY KEY,"
               "    applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
               ")"
           )
           for v in range(1, 16):
               await conn.execute(
                   "INSERT INTO schema_version (version) VALUES (?)", (v,)
               )
           # v15-shape chat_sessions (no v16 columns).
           await conn.execute(
               "CREATE TABLE chat_sessions ("
               "    id TEXT PRIMARY KEY,"
               "    agent_name TEXT,"
               "    title TEXT DEFAULT 'New chat',"
               "    messages TEXT DEFAULT '[]',"
               "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
               "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
               ")"
           )
           # v15-shape connector_accounts (no session_continuation_seconds).
           await conn.execute(
               "CREATE TABLE connector_accounts ("
               "    id TEXT PRIMARY KEY,"
               "    type TEXT NOT NULL,"
               "    config TEXT DEFAULT '{}',"
               "    secrets TEXT DEFAULT '{}',"
               "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
               "    updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
               "    name TEXT NOT NULL DEFAULT '',"
               "    idle_timeout_seconds INTEGER NULL"
               ")"
           )
           # Seed rows against the v15 shape.
           await conn.execute(
               "INSERT INTO chat_sessions (id, agent_name, title)"
               " VALUES (?, ?, ?)",
               ("seeded-session", "test-agent", "Pre-v16 session"),
           )
           await conn.execute(
               "INSERT INTO connector_accounts (id, name, type, config, secrets, idle_timeout_seconds)"
               " VALUES (?, ?, ?, ?, ?, ?)",
               ("seeded-account", "stub-account", "stub", "{}", "{}", 1800),
           )
           await conn.commit()

           await ensure_schema(conn)

           # Seeded chat_sessions row survived with NULLs on all v16 columns.
           async with conn.execute(
               "SELECT id, agent_name, title, platform, connector_account_id,"
               " channel_id, thread_id, peer_id, session_metadata, last_inbound_at"
               " FROM chat_sessions WHERE id = 'seeded-session'"
           ) as cur:
               row = await cur.fetchone()
           assert row is not None
           assert row["agent_name"] == "test-agent"
           assert row["title"] == "Pre-v16 session"
           for col in (
               "platform",
               "connector_account_id",
               "channel_id",
               "thread_id",
               "peer_id",
               "session_metadata",
               "last_inbound_at",
           ):
               assert row[col] is None, f"{col} should be NULL on legacy row, got {row[col]!r}"

           # Seeded connector_accounts row survived with idle_timeout preserved
           # and session_continuation_seconds=NULL.
           async with conn.execute(
               "SELECT id, idle_timeout_seconds, session_continuation_seconds"
               " FROM connector_accounts WHERE id = 'seeded-account'"
           ) as cur:
               acc_row = await cur.fetchone()
           assert acc_row is not None
           assert acc_row["idle_timeout_seconds"] == 1800
           assert acc_row["session_continuation_seconds"] is None

           # Head pointer landed at CURRENT_VERSION (≥16).
           async with conn.execute(
               "SELECT version FROM schema_version ORDER BY version"
           ) as cur:
               versions = [r[0] for r in await cur.fetchall()]
           assert 16 in versions, versions
           assert max(versions) == CURRENT_VERSION, versions

           await conn.close()
   ```

13. **Update `the_one/db/_connector_types.py:11-15` docstring**. The block currently reads:
    ```
    — **deferred to flight 8** which adds the CHECK via a v16 table-rename ceremony when there is a real
      type to constrain (v14 → ``name`` column on ``connector_accounts`` (F1 L2);
      v15 → ``idle_timeout_seconds`` (F2 L2); v16 is Flight 8's CHECK constraint
      via the table-rename ceremony established by v6/v12).
    ```
    Becomes:
    ```
    — **deferred to flight 8** which adds the CHECK via a v17 table-rename ceremony when there is a real
      type to constrain (v14 → ``name`` column on ``connector_accounts`` (F1 L2);
      v15 → ``idle_timeout_seconds`` (F2 L2); v16 → chat_sessions external-key
      columns + ``session_continuation_seconds`` on ``connector_accounts`` (F3 L1);
      v17 is Flight 8's CHECK constraint via the table-rename ceremony established
      by v6/v12).
    ```

14. **Update `the_one/agents.md:290`** (connector-type checklist item 4). Currently reads:
    > v14 is claimed by leg 02's `name` column on `connector_accounts` (F1 L2); v15 by leg 02 of Flight 2 — `idle_timeout_seconds`. Flight 8's **v16** migration adds the CHECK via the table-rename ceremony established by v6/v12.

    Becomes:
    > v14 is claimed by leg 02's `name` column on `connector_accounts` (F1 L2); v15 by leg 02 of Flight 2 — `idle_timeout_seconds`; v16 by leg 01 of Flight 3 — chat_sessions external-key columns + `session_continuation_seconds` on `connector_accounts`. Flight 8's **v17** migration adds the CHECK via the table-rename ceremony established by v6/v12.

15. **Add repository round-trip tests** in `tests/test_db_repositories.py` (extend the existing `TestChatSessionRepository` class at line ~595 — confirmed by the design-review as the right extension point). Use descriptive method names: `test_create_and_get_with_connector_identity`, `test_round_trip_session_metadata_dict_and_none`, `test_round_trip_session_metadata_corrupt_non_dict_collapses_to_none`, `test_round_trip_session_continuation_seconds_validator_boundaries`. Cover:
    - `ChatSession` with `platform="discord"`, `connector_account_id="acc-1"`, `channel_id="ch-1"`, `thread_id=None`, `peer_id="peer-1"`, `session_metadata={"routing": "default"}`, `last_inbound_at="2026-05-17T00:00:00+00:00"` round-trips through `create` → `get` byte-identically (especially `session_metadata` JSON encoding).
    - `ChatSession` with all 7 new fields set to `None` (back-compat for non-connector sessions) round-trips.
    - **Defensive normalization**: directly INSERT a row whose `session_metadata` column contains `'"hello"'` (a JSON-literal string, not a dict); `repo.get(...)` returns the model with `session_metadata=None` (the read-path's `isinstance(parsed, dict)` guard).
    - `ConnectorAccount` with `session_continuation_seconds=86400` round-trips.
    - `ConnectorAccount` with `session_continuation_seconds=None` round-trips (NULL preserved).
    - Pydantic validator: `ConnectorAccount(id=..., name=..., type="stub", session_continuation_seconds=0)` raises `ValidationError` (Pydantic wraps `ValueError`).
    - Pydantic validator: `ConnectorAccount(..., session_continuation_seconds=604801)` raises.
    - Pydantic validator: `session_continuation_seconds=1`, `=86400`, `=604800` all pass.

16. **Run tests** per the leg-execution prompt's containerized test discipline:
    ```
    docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py -x --timeout 30 -v
    ```
    Iterate until green, then run the full suite as the regression gate:
    ```
    docker exec the-one pytest -x --timeout 30
    ```
    Then `docker exec the-one ruff check .` (or the Makefile recipe).

17. **Update flight log** with a "Leg Progress: v16-schema-migration" entry per the ARTIFACTS.md format: started/completed timestamps, changes-made summary, notes (deviations, surprises). Cite test-count delta (before/after) so leg-6's regression baseline is locatable.

18. **Flip leg status to `landed`** in this file's header (the agentic-workflow Flight Director flips to `completed` at flight-end commit time per the batched-review model), **check off this leg in `flight.md`**, and signal `[HANDOFF:review-needed]`. **Do NOT commit** — per the agentic-workflow batched-review model, commit happens after the last leg + flight-level review.

## Edge Cases

- **Existing rows on legacy v15 DBs**: All seven new chat_sessions columns + the new connector_accounts column land as NULL via the bare `ALTER TABLE … ADD COLUMN <name> <type> NULL` (no `DEFAULT` clause; SQLite stores NULL implicitly). `TestSchemaV16.test_v16_legacy_v15_row_decodes_with_null_external_key_columns` is the explicit guard.

- **Partial expression index on a real existing DB**: `CREATE INDEX IF NOT EXISTS` is idempotent. The index is computed lazily over existing rows on creation; for a DB with N non-connector chat_sessions (all `platform IS NULL`), the partial-index `WHERE platform IS NOT NULL` clause excludes them — the index is initially empty, and the build is cheap.

- **`session_metadata` JSON encoding**: The model's field is `dict[str, Any] | None`; the DB column is `TEXT NULL`. Repository write uses `json.dumps(session.session_metadata) if session.session_metadata is not None else None` to preserve the NULL/empty-dict distinction. Repository read uses `json.loads(row["session_metadata"]) if row["session_metadata"] is not None else None`. An empty dict `{}` round-trips as `'{}'` in the column (non-NULL), distinct from `None` (NULL). Tests must cover both.

- **`last_inbound_at` write format**: Leg 1 only sets `last_inbound_at` at row INSERT time (the resolver in leg 3 creates the row with `last_inbound_at=_now_iso()`); leg 4's `update_last_inbound` dedicated repository method does subsequent per-inbound updates. The format is UTC ISO via `_now_iso()` in both paths. String comparison of ISO timestamps is reliable only when all writes use the same canonical form; the resolver in leg 3 explicitly parses via `datetime.fromisoformat` rather than relying on string `<` comparison.

- **`ChatSessionRepository.update()` does NOT mutate connector identity columns**: The seven new columns are identity attributes set once at row creation. Leg 4 adds `append_messages` and `update_last_inbound` as the narrow mutation primitives. The existing `update()` shape is preserved (title + messages + updated_at) so prior call sites continue to behave identically. Document this with a code comment on `update()`.

- **Pydantic `session_metadata: dict[str, Any] | None` semantics**: A connector-keyed session with no routing metadata yet stores `None` (column NULL); F7 populates it when routing decisions land. An empty dict means "F7 saw this session and explicitly recorded no metadata" — distinct from "F7 hasn't touched this session." Don't coerce `{}` ↔ `None` at either the model or the repository.

- **Schema-loud-fail test discipline**: `TestSchemaV15.test_v15_fresh_db_includes_idle_timeout_seconds_column` at line 1428 asserts `max(versions) == CURRENT_VERSION`. After the v16 bump, this assertion will pass v15 in the versions list AND CURRENT_VERSION=16 — the assertion compares `max(versions) == CURRENT_VERSION`. Since v16 is also seeded by ensure_schema, max will be 16 and CURRENT_VERSION is 16 — pass. NO update needed to the v15 test's assertion, just confirm.

- **`TestSchemaV14.test_v14_preserves_v13_seeded_row_with_empty_name`** at line 1305: similarly asserts `max(versions) == CURRENT_VERSION` at line 1378. After the v16 bump, max becomes 16 (ensure_schema runs all migrations including v15 and v16), CURRENT_VERSION=16 — pass. NO update needed.

- **Container test execution**: Per the leg-execution prompt, use `docker exec the-one pytest …` (NOT `docker compose exec`). Always pass `-x --timeout 30` for autonomous runs.

## Files Affected

- `the_one/db/schema.py` — bump `CURRENT_VERSION` and add v16 migration block
- `the_one/db/models.py` — extend `ChatSession` (7 fields) and `ConnectorAccount` (1 field + validator)
- `the_one/db/repositories.py` — extend `ChatSessionRepository` and `ConnectorAccountRepository` round-trips
- `the_one/db/_connector_types.py` — docstring update for v16 (F3 L1) and F8 CHECK renumber to v17
- `the_one/agents.md` — connector-type checklist item 4 update for v16 (F3 L1) and F8 CHECK renumber to v17
- `tests/test_db_migration.py` — `TestSchemaV8` head-version bump + `TestSchemaV14` docstring renumber + new `TestSchemaV16` class
- `tests/test_db_repositories.py` — new round-trip tests for the new fields (or sibling file per project naming conventions)
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight-log.md` — leg-completion entry
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight.md` — tick leg 1 in the Legs list
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/legs/01-v16-schema-migration.md` — this file's status → `completed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test` + scoped runs both green)
- [ ] Lint clean (`make lint` no new findings)
- [ ] Update flight-log.md with leg progress entry (timestamps + test-count delta + any deviations)
- [ ] Set this leg's status to `landed` in this file's header (the agentic-workflow Flight Director flips to `completed` at flight-end commit time per the batched-review model)
- [ ] Check off this leg in flight.md's Legs list
- [ ] Do NOT commit — agentic-workflow batched-review model defers commit to flight end
- [ ] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

14 citations verified against current code at leg design time (initial draft). Design-review pass added two citations and corrected one line hint:

- **Added** `tests/test_db_migration.py:1110` (TestSchemaV13) — column-set assertion at :1176-1185 + docstring renumber at :1157, :1163
- **Added** `the_one/db/schema.py:546-548` — v15 block's own downstream-renumber comment ("renumbers to v16" → "renumbers to v17")
- **Corrected** TestSchemaV16 insertion-site hint: "~1472" → "~1532" (TestSchemaV15 spans 1383-1532 in the current file)

Updated citation list:

- `the_one/db/schema.py:11` (`CURRENT_VERSION = 15`) — verified.
- `the_one/db/schema.py:538` (`if version < 15:` v15 block) — verified at line 538.
- `the_one/db/models.py:118` (`class ConnectorAccount(BaseModel):`) — verified at line 118.
- `the_one/db/models.py:181` (`class ChatSession(BaseModel):`) — verified at line 181.
- `the_one/db/repositories.py:487` (`async def list` on `ConnectorAccountRepository`) — verified at line 487.
- `the_one/db/repositories.py:658` (`class ChatSessionRepository:`) — verified at line 658.
- `tests/test_db_migration.py:203` (`class TestSchemaV8:`) — verified at line 203.
- `tests/test_db_migration.py:229` (`assert CURRENT_VERSION == 15`) — verified at line 229.
- `tests/test_db_migration.py:1234` (`class TestSchemaV14:`) — verified at line 1234.
- `tests/test_db_migration.py:1245` ("renumbers to v16" in TestSchemaV14 docstring) — verified at line 1245.
- `tests/test_db_migration.py:1383` (`class TestSchemaV15:`) — verified at line 1383.
- `the_one/db/_connector_types.py:11-15` (v16-references-to-renumber block in docstring) — verified at lines 11-15.
- `the_one/agents.md:290` (connector-type checklist item 4 with `**v16**` for F8 CHECK) — verified at line 290.
- `the_one/agents.md:344` (`last_activity` Known Issue) — verified at line 344 (NOT modified by this leg; leg 4 updates it after ratifying acquire-per-inbound).

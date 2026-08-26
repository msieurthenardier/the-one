# Leg: revision-log-foundation

**Status**: completed
**Flight**: [Operator Oversight](../flight.md)

## Objective

Create the `agent_revisions` table and its repository, and wire Flight 1's
direct write path so that every self-revision is recorded as an `applied`
revision-log row with its before-image, after-image, and timestamp — the
storage foundation the approval queue (Leg 2) and restore (Leg 3) both build on.

## Context

- **DD1** — one status-bearing `agent_revisions` table serves the log, the
  pending queue, and restore. This leg creates the full table (all four `status`
  values and both `source` values in the CHECK constraint) but writes only
  `status='applied', source='self'`; Leg 2 reaches `pending`/`dismissed`/
  `superseded`, Leg 3 reaches `source='restore'`. The schema is complete from
  v34 so later legs add code, not migrations, against these values.
- **DD3** — under approval mode a write will branch to enqueue instead of
  persist; that branch is Leg 2. In this leg there is no approval mode yet, so
  every revision is direct and every revision is logged `applied`. The one
  behavioral addition to the Flight 1 path is the log write.
- The reusable precedent is `PendingApprovalRepository`
  (`the_one/db/repositories.py:693`) — a conn-only (no-encryptor) async repo over
  a single status-bearing table. Mirror its shape. **No encryptor**:
  `description` and `system_prompt` are plaintext `TEXT` columns
  (`the_one/db/schema.py:50,53`), so `base_value`/`proposed_value` cross no
  encryption boundary and the log holds no secret material.
- **Naming**: the new persisted concept is `agent_revisions` / the revision log.
  Do **not** add anything to `the_one/self_configuration/pending.py` — that is the
  in-memory next-turn *deferral* registry, a different concept that merely shares
  the word "pending". Keeping them separate is a flight invariant (see
  flight Adaptation Criteria).

## Inputs

What exists before this leg runs (all on `main`, post-#171):

- Migrations at **v33** (`the_one/db/schema.py:1904` is the last `if version <`
  block). This leg adds `if version < 34:`.
- `the_one/self_configuration/surface.py:175` `_apply_revision` — the single
  choke point every write tool passes through; persists via
  `store.load → model_copy → store.save`, then records the in-memory next-turn
  deferral for `next_turn`.
- `the_one/db/repositories.py:693` `PendingApprovalRepository` — the repo shape
  to mirror (conn-only, `get`, `upsert_pending`, transitions, `_row_to_model`).
- `the_one/db/models.py` — Pydantic row models (`PendingApproval` lives here).
- `agents.name TEXT PRIMARY KEY` (`the_one/db/schema.py:49`) and
  `PRAGMA foreign_keys=ON` on the runtime connection
  (`the_one/db/connection.py:20`) — so an `ON DELETE CASCADE` FK to `agents`
  actually fires.

## Outputs

What exists after this leg completes:

- Migration `v34` in `the_one/db/schema.py` creating `agent_revisions` + its
  index, stamped `INSERT OR IGNORE INTO schema_version (version) VALUES (?)` with
  `(34,)` last (partial-apply safe).
- `AgentRevision` Pydantic model in `the_one/db/models.py`.
- `AgentRevisionRepository` in `the_one/db/repositories.py` with `append`, `get`,
  and `list_for_agent` (log-facing methods only; the queue transitions and
  `count_pending` are Leg 2, restore provenance is Leg 3).
- `_apply_revision` (`surface.py:175`) captures the field's pre-write value and
  appends an `applied` revision row after a successful `save`.
- Unit tests: the migration creates the table with the right shape and is
  re-runnable; the repository round-trips a row and lists newest-first; a direct
  description revision and a direct system-prompt revision each write exactly one
  `applied` row carrying the correct `base_value`/`proposed_value`; the FK
  cascade removes an agent's revisions when the agent is deleted.

## Acceptance Criteria

- [x] AC1 — A `v34` migration creates `agent_revisions` with columns
      `id TEXT PRIMARY KEY`, `agent_name TEXT NOT NULL REFERENCES agents(name)
      ON DELETE CASCADE`, `field TEXT NOT NULL CHECK (field IN
      ('description','system_prompt'))`, `proposed_value TEXT NOT NULL`,
      `base_value TEXT NOT NULL`, `status TEXT NOT NULL CHECK (status IN
      ('applied','pending','dismissed','superseded'))`, `source TEXT NOT NULL
      CHECK (source IN ('self','restore'))`, `restored_from TEXT REFERENCES
      agent_revisions(id) ON DELETE SET NULL`, `created_at TEXT NOT NULL`,
      `resolved_at TEXT`. The block is `CREATE TABLE IF NOT EXISTS` + an
      `INSERT OR IGNORE INTO schema_version (version) VALUES (?)` with `(34,)`
      (parameterized, matching v30–v33) stamped LAST, and is a no-op on re-run.
- [x] AC2 — An index supporting the per-agent pending lookup exists:
      `idx_agent_revisions_agent_status ON agent_revisions (agent_name, status)`
      (created `IF NOT EXISTS`).
- [x] AC3 — `AgentRevision` model in `models.py` mirrors the columns and
      round-trips through `_row_to_model`.
- [x] AC4 — `AgentRevisionRepository(conn)` (no encryptor) exposes: `append(...)`
      inserting one row and returning it; `get(id)` raising `KeyError` on miss;
      `list_for_agent(agent_name)` returning that agent's rows **newest-first**
      (`ORDER BY created_at DESC, id DESC`; the `id DESC` tiebreak on same-
      microsecond rows is a uuid-hex order, i.e. arbitrary-but-stable, not
      insertion order — acceptable at operator-scale). Repository is constructed
      with a bare connection, mirroring `PendingApprovalRepository`.
- [x] AC5 — After a direct `update_my_description` call, exactly one new row
      exists for that agent with `field='description'`, `status='applied'`,
      `source='self'`, `proposed_value` = the new text, `base_value` = the
      description the agent had *before* the write, `restored_from` NULL,
      `resolved_at` = `created_at` (an applied row is resolved at creation).
- [x] AC6 — The same holds for `update_my_system_prompt` with
      `field='system_prompt'`. The two fields' rows are independent.
- [x] AC7 — The revision row is written on the same connection as the config
      save and only after `save` succeeds: a revision is never persisted to
      `agents` without a corresponding `applied` log row. (If a single
      transaction around save+append is impractical against the existing
      self-committing `store.save`, append immediately after and document the
      residual crash-window as a code comment — see Edge Cases.)
- [x] AC8 — Deleting an agent (`DELETE FROM agents WHERE name=?`) removes its
      `agent_revisions` rows via the cascade.
- [x] AC9 — `make test-unit` passes (full lane green); no pre-existing tests
      regress. New tests cover AC1–AC8.

## Verification Steps

- AC1/AC2 — `sqlite3` (or a test using the app's connection) `PRAGMA
  table_info(agent_revisions)` and `PRAGMA index_list` after `ensure_schema` on a
  fresh DB; assert columns, CHECK constraints, and the index. Run `ensure_schema`
  twice; assert no error and one v34 stamp.
- AC3/AC4 — unit test: `append` two rows for one agent, `get` each, `list_for_agent`
  returns them newest-first; `get` on a bogus id raises `KeyError`.
- AC5/AC6 — unit test over the real `_apply_revision` (real `SQLiteAgentStore` +
  `AgentRevisionRepository`, mock or scripted agent not required — this is store
  level): seed an agent, call the write path for each field, assert exactly one
  `applied` row with the expected `base_value`/`proposed_value`.
- AC7 — inspect the code path; test that a `save` failure (e.g. patched to raise)
  leaves no orphan log row.
- AC8 — unit test: append rows, delete the agent, assert the rows are gone.
  **Place this test against a `PRAGMA foreign_keys=ON` fixture** — e.g.
  `tests/test_db_repositories.py`'s `conn` fixture (`:35`), which sets it. Do
  **not** use `tests/test_schema.py`'s `:memory:` fixtures `fresh_db` (`:75`) /
  `v2_db` (`:83`) — they omit the pragma, so the cascade would silently not fire.
  Defensively, assert `PRAGMA foreign_keys` returns `1` inside the test itself
  before relying on the cascade.
- AC9 — `PYTHON=.venv/bin/python bash scripts/run-tests.sh <new-test-files> -x
  --timeout 30` iteratively, then `make test-unit` once at leg end.

## Implementation Guidance

1. **Migration v34** (`the_one/db/schema.py`, new `if version < 34:` block after
   the v33 block at `:1904`). Follow the v31 `app_metadata` new-table template
   (`:1866-1880`): `CREATE TABLE IF NOT EXISTS agent_revisions (...)` with the
   full column/CHECK set from AC1, then `CREATE INDEX IF NOT EXISTS
   idx_agent_revisions_agent_status ON agent_revisions (agent_name, status)`,
   then `await conn.execute("INSERT OR IGNORE INTO schema_version (version)
   VALUES (?)", (34,))` (parameterized, matching v30–v33) and
   `await conn.commit()`, then `version = 34`. The `agents` table is created far
   earlier in-sequence, so the FK reference resolves; no PRAGMA toggle and no
   table-rebuild ceremony are needed (this is a brand-new table, like v31).
2. **Model** (`the_one/db/models.py`): add `AgentRevision` mirroring the columns.
   Use the same field types/optionality as the DDL (`restored_from: str | None`,
   `resolved_at: str | None`). Follow `PendingApproval`'s style in this file.
3. **Repository** (`the_one/db/repositories.py`): add `AgentRevisionRepository`
   modeled on `PendingApprovalRepository:693`.
   - `__init__(self, conn)` — no encryptor.
   - `append(self, *, agent_name, field, proposed_value, base_value, source,
     status, restored_from=None, created_at, resolved_at)` → INSERT, return the
     `AgentRevision`. Mint `id` the same way `PendingApproval` mints its id
     (match the existing pattern — do not invent a new scheme). For this leg
     callers pass `status='applied', source='self', restored_from=None,
     resolved_at=created_at`.
   - `get(self, revision_id)` → `_row_to_model` or `KeyError`.
   - `list_for_agent(self, agent_name)` → `... WHERE agent_name=? ORDER BY
     created_at DESC, id DESC`.
   - `_row_to_model(row)` → `AgentRevision`.
   - Commit within each write method, as `PendingApprovalRepository` does.
   - **Do not** add `count_pending` or the `mark_*`/`_transition` methods here —
     those belong to Leg 2's state machine, with their own tests.
4. **Wire the direct path** (`the_one/self_configuration/surface.py:175`
   `_apply_revision`): before `updated = config.model_copy(...)`, capture
   `base_value = getattr(config, field)`. After `await agent_store.save(updated)`
   succeeds, construct an `AgentRevisionRepository(conn)` (reuse the same `conn`
   already obtained at the top of `_apply_revision`) and `append(...)` an
   `applied`/`self` row with `proposed_value=text`, `base_value=base_value`,
   `created_at=ts`, `resolved_at=ts` where `ts = now_iso()` is captured **once**
   so the two timestamps are byte-identical (an applied row is resolved at
   creation). Order it strictly after `save`. Keep the existing
   `pending.record(...)` call and the returned result shape **unchanged** — this
   leg adds logging only, it does not change what the tool returns or how
   `next_turn` propagates.
5. **Timestamp source**: use `now_iso()` from `the_one.db.models`
   (`models.py:14`, body `datetime.now(timezone.utc).isoformat()`) — already
   imported in `repositories.py:22` and used by `PendingApprovalRepository`. Do
   not inline the raw `datetime` expression; reuse the helper.
6. **Id minting**: mint `id` in the repository's `append` as
   `uuid.uuid4().hex` (mirroring `PendingApprovalRepository.upsert_pending`,
   `repositories.py:761`; `import uuid` already present), not via a model
   `default_factory` — the repo owns the INSERT and the caller passes
   `created_at`/`resolved_at` explicitly.

## Edge Cases

- **Crash between `save` and `append`** — a revision could persist to `agents`
  without a log row. Prefer wrapping save+append in one transaction; if
  `store.save` self-commits and that is impractical to change in this leg,
  append immediately after and leave a code comment naming the residual window
  as accepted (operator-scale, single-writer). Do **not** append *before* save —
  a logged-but-unpersisted revision is the worse failure (the log would claim a
  change that never took effect).
- **First revision of a field whose stored value is the default `""`** —
  `base_value` is the empty string, not NULL. `base_value` is `NOT NULL`; store
  `""`. The log then reads "changed from empty", which is correct.
- **Very long values** — `proposed_value`/`base_value` inherit the tool's 64 KiB
  input cap from `_validate_write_input` (`surface.py`); no extra bound needed.
- **Re-run / partial-apply of the migration** — guaranteed no-op by
  `CREATE TABLE IF NOT EXISTS` + the `if version < 34:` short-circuit +
  `INSERT OR IGNORE` last, exactly as v31/v21 document.

## Files Affected

- `the_one/db/schema.py` — new `if version < 34:` migration block.
- `the_one/db/models.py` — new `AgentRevision` model.
- `the_one/db/repositories.py` — new `AgentRevisionRepository`.
- `the_one/self_configuration/surface.py` — `_apply_revision` logs an `applied`
  row (no signature or return-shape change).
- `tests/` — new unit tests for the migration, the repository, the wired write
  path, and the FK cascade (place alongside existing DB/self-configuration tests,
  matching their naming).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit` green)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — do not land the flight or commit; the flight defers
      code review and the single commit to flight end per /agentic-workflow.)

---

## Citation Audit

Verified against `flight/02-operator-oversight` (post-#171) during design review:

- `schema.py:1904` v33 is the last `if version <` block → v34 unclaimed. ✓
- `schema.py:1866-1880` v31 `app_metadata` new-table template. ✓
- `schema.py:49` `agents.name TEXT PRIMARY KEY`; `:50`/`:53` `description`/
  `system_prompt` plaintext `TEXT DEFAULT ''`. ✓
- `repositories.py:693` `PendingApprovalRepository` (conn-only, no encryptor). ✓
- `repositories.py:761` id minted `uuid.uuid4().hex`; `now_iso()` at
  `models.py:14`, imported `repositories.py:22`, used at `:190`. ✓
- `surface.py:175` `async def _apply_revision`; tools at `:209`/`:222`;
  `SQLiteAgentStore.save` self-commits at `repositories.py:244`. ✓
- `connection.py:20` runtime `PRAGMA foreign_keys=ON`. ✓ Test fixtures with the
  pragma: `conftest.py:342`, `test_db_repositories.py:35`,
  `test_self_configuration_write.py:52`, `_api.py:57`. `test_schema.py`
  `:memory:` fixtures (`:75`,`:83`) omit it — AC8 routed away from them.

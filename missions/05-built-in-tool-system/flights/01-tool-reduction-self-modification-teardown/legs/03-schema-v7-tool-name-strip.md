# Leg: 03-schema-v7-tool-name-strip

**Status**: completed
**Flight**: [Tool Reduction & Self-Modification Teardown](../flight.md)

## Objective

Add schema migration v7 to `the_one/db/schema.py::ensure_schema()` that strips the seven removed tool names (`self_deploy`, `rollback`, `restart`, `run_tests`, `git`, `memory`, `mission_control`) from every existing agent's `enabled_tools` and `disabled_tools` JSON columns, bump `CURRENT_VERSION` from 6 to 7, add `tests/test_db_migration.py::test_v7_strips_removed_tool_names` to verify the strip behavior on a v6 fixture, and update the existing `test_preserves_all_fields` fixture so it no longer carries the stale `self_deploy` name (per flight Decision 5).

## Context

Mission Success Criterion: *"Existing agent configurations referencing removed tools load cleanly and continue functioning — stale tool names in `enabled_tools`/`disabled_tools` are silently stripped via schema migration with no operator-visible breakage"*. L3 delivers exactly that.

Per flight **Decision 5**: two-part test coverage. New `test_v7_strips_removed_tool_names` proves the strip works on legacy data; updated `test_preserves_all_fields` fixture (swap `disabled_tools=["self_deploy"]` → `disabled_tools=["shell"]`) ensures the JSON-migration test doesn't muddle "field preservation" with "v7 strip side-effect" — the fixture row now carries only legitimate tool names that survive both the JSON→SQLite migration and the v7 strip.

L3 is independent of L1 and L2 (no shared files). It runs after L2 in the flight order purely for staging — the schema bump should land before any leg that touches the agent runtime in a way that could hit a stale config.

**Codebase audit findings (2026-04-28, post-L1+L2 uncommitted):**

- `the_one/db/schema.py:7` — `CURRENT_VERSION = 6`. Bump to 7.
- `the_one/db/schema.py:213-247` — last migration block is `if version < 6:`. New block follows the v3/v5/v6 pattern (inline migration in `ensure_schema()`), but unlike those (which rebuild whole tables), v7 is a row-by-row UPDATE with no DDL changes.
- `the_one/db/schema.py::_get_version()` — returns max version applied. After v7 lands, fresh DBs go straight to v7; legacy v6 DBs see `version=6`, the new block runs, schema_version table records 7.
- `the_one/db/schema.py::ensure_schema()` — the function body is the migration sequence. Add v7 block at the end, mirroring the existing pattern: `if version < 7: ... await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (7,)) ; await conn.commit() ; version = 7`.
- `agents` table columns: `enabled_tools TEXT` (nullable — `NULL` means "whitelist mode disabled, all tools allowed") and `disabled_tools TEXT DEFAULT '[]'` (NOT-nullable in practice, defaults to JSON empty list).
- `tests/test_db_migration.py` exists at 98 lines. `test_preserves_all_fields` at lines 75-97 carries `disabled_tools=["self_deploy"]` (line 85). After L3, change to `disabled_tools=["shell"]`. Decision 5 explicitly calls out this edit.
- `tests/test_db_repositories.py` and `tests/test_store.py` may exercise the agents-table read/write path. Quick audit needed to confirm no other test seeds `disabled_tools` with a removed-tool name. (Found none in initial grep; will reconfirm during implementation.)
- `SQLiteAgentStore` exposes `self.conn` as a public attribute (`the_one/db/repositories.py:26`). Tests can reach the underlying `aiosqlite.Connection` via `store.conn` to issue raw SQL for fixture setup.
- Other places that touch `enabled_tools`/`disabled_tools` JSON: `the_one/db/repositories.py::SQLiteAgentStore.save()` and `.load()` serialize/deserialize the lists. These aren't affected by L3 — they handle whatever shape is in the column. The v7 strip only mutates existing rows during migration; subsequent reads/writes go through the normal path.

**Edge cases to test:**

1. **`enabled_tools = NULL` (whitelist mode off)** — preserve as `NULL` (do not coerce to `[]`).
2. **`enabled_tools` JSON list mixing kept and removed names** — keep the kept names, drop the removed ones. `["self_deploy", "shell", "git", "read_file"]` → `["shell", "read_file"]`.
3. **`enabled_tools` JSON list with only removed names** — result is an empty list `[]` (semantic note: an empty whitelist blocks all tools, but that's the correct interpretation; operator must reconfigure).
4. **`disabled_tools` is `'[]'`** — pass through unchanged.
5. **`disabled_tools` mixing kept and removed** — strip the removed.
6. **No agents in the table at all** — migration runs SELECT, gets empty result set, finishes; schema_version still records 7.
7. **JSON column carries unexpected extra characters or invalid JSON** — out of scope; the existing schema invariants assume valid JSON written by `SQLiteAgentStore.save()`. If invalid JSON were present, the migration would raise `json.JSONDecodeError` and bubble up. This is acceptable — we don't try to rescue corrupted data, we just refuse to strip silently. Document in Edge Cases.

**Behavior on whitelist-emptied rows:**

If a v6 agent had `enabled_tools=["self_deploy"]` (whitelist allowed only `self_deploy`), after v7 strip it becomes `enabled_tools=[]` (whitelist allows nothing). The agent loads cleanly (Mission criterion satisfied) but has no tools. This is the correct interpretation — the operator wanted ONLY a removed tool; we don't silently widen their scope back to "all tools" (privilege escalation), so the locked-down state is the safe default. Operator-visible only via the studio UI showing no enabled tools; no error, no crash. Out of L3 scope to surface a warning — that's UI work for L5.

**Order rationale within the flight:** L3 lands after L2 because the schema bump is content-orthogonal to the prompt rewrite, and putting it third (per flight Technical Approach) keeps the build green at every leg boundary. No leg between L3 and L6 touches `agents` table data.

## Inputs

- L1 + L2 landed (uncommitted): `behaviors.py` gone, 7 tools removed, `direct_actions` field gone, `BASE_PROMPT` constant established with additive composition, `Agent.__init__` no-default.
- `the_one/db/schema.py` at version 6, 247 lines, with v1-v6 migrations.
- `tests/test_db_migration.py` at 98 lines, fixture seeds `disabled_tools=["self_deploy"]` in `test_preserves_all_fields`.
- Default unit test suite baseline (post-L1+L2): 394 passed + 1 pre-existing red (`tests/test_token_definitions.py::test_every_var_reference_is_defined` — CSS token check, predates this flight). The implementer should confirm the same baseline at L3 start before adding the new test.

## Outputs

After this leg:
- `the_one/db/schema.py::CURRENT_VERSION = 7`.
- `the_one/db/schema.py::ensure_schema()` has a new `if version < 7:` block that strips removed tool names from every agents-table row.
- `tests/test_db_migration.py::test_v7_strips_removed_tool_names` exists, passes, covers all six edge cases listed above.
- `tests/test_db_migration.py::test_preserves_all_fields` fixture uses `disabled_tools=["shell"]` instead of `["self_deploy"]`.
- Default unit test suite green (394 + 1-or-more new tests; the pre-existing CSS anomaly remains red and is out of scope).
- No commit — deferred to post-L6.

## Acceptance Criteria

- [ ] `the_one/db/schema.py::CURRENT_VERSION` equals `7`.
- [ ] `the_one/db/schema.py::ensure_schema()` contains an `if version < 7:` block that:
  - Selects all rows from `agents` (name, enabled_tools, disabled_tools).
  - For each row: parses both JSON columns, filters out the seven removed tool names, writes back.
  - Handles `enabled_tools = NULL` by preserving NULL (does NOT coerce to `[]`).
  - Inserts `(7,)` into `schema_version` and commits.
- [ ] `REMOVED` set inside the migration block contains exactly: `{"self_deploy", "rollback", "restart", "run_tests", "git", "memory", "mission_control"}`.
- [ ] `tests/test_db_migration.py::test_v7_strips_removed_tool_names` exists, runs without errors, and asserts:
  - A row seeded with `enabled_tools=["self_deploy", "git", "memory", "shell"]` and `disabled_tools=["self_deploy", "shell"]` ends up with `enabled_tools=["shell"]` and `disabled_tools=["shell"]` after the v7 migration.
  - A row seeded with `enabled_tools = NULL` and `disabled_tools=["git"]` ends up with `enabled_tools = NULL` and `disabled_tools=[]`.
  - A row seeded with `enabled_tools=["self_deploy"]` and `disabled_tools='[]'` ends up with `enabled_tools=[]` and `disabled_tools=[]` (whitelist becomes empty — locked-down state, not widened).
  - A row whose JSON columns contain only kept tool names passes through unchanged (proves no over-stripping).
  - Schema version after migration is 7.
- [ ] `tests/test_db_migration.py::test_preserves_all_fields` fixture has `disabled_tools=["shell"]` (was `["self_deploy"]`). The test still passes.
- [ ] `python -m pytest tests/test_db_migration.py -v` exits 0; the new test name appears in output.
- [ ] `python -m pytest tests/ --tb=short -q --ignore=tests/browser` exits 0 (modulo the pre-existing CSS-token anomaly).
- [ ] `rg -n "self_deploy|rollback|restart|run_tests|GitTool|MemoryTool|MissionControlTool" the_one/db/ tests/test_db_migration.py --glob '!*.md'` returns matches ONLY in: (a) the v7 migration block in `schema.py` (the `REMOVED` set definition), and (b) the new `test_v7_strips_removed_tool_names` (the fixture data and assertions). The `test_preserves_all_fields` fixture must NOT carry these names. (Scope is intentionally tight — `tests/test_aiat.py::test_run_tests`, `tests/browser/seeders.py`, and incidental `restart` mentions in unrelated comments live elsewhere; L4 and L6 handle them.)
- [ ] Working tree on branch `flight/01-tool-reduction-self-modification-teardown`; **no commit made**.
- [ ] Flight log updated with leg progress entry under `## Leg Progress`, status `landed`.
- [ ] Leg status set to `landed` in this file's header.

## Verification Steps

```bash
# 1. CURRENT_VERSION bumped
rg -n "^CURRENT_VERSION = " the_one/db/schema.py
# Expected: one match showing "CURRENT_VERSION = 7"

# 2. v7 block exists with REMOVED set
rg -n "if version < 7:" the_one/db/schema.py
# Expected: one match

# 3. New test exists
rg -n "def test_v7_strips_removed_tool_names" tests/test_db_migration.py
# Expected: one match

# 4. Fixture cleanup
rg -n "self_deploy" tests/test_db_migration.py
# Expected: no output (fixture no longer references the stale name)

# 5. Full migration test file
python -m pytest tests/test_db_migration.py -v
# Expected: all tests pass; v7 test in output

# 6. Full unit suite (excluding browser)
python -m pytest tests/ --tb=short -q --ignore=tests/browser
# Expected: 394 (or 395+, with the new test counted) passed, 1 pre-existing CSS-token failure

# 7. End-to-end smoke: fresh DB migrates straight to v7, ensure_schema is idempotent
python -c "
import asyncio, aiosqlite, tempfile, os
from the_one.db.schema import ensure_schema, CURRENT_VERSION

async def main():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys=ON')
        await ensure_schema(conn)
        async with conn.execute('SELECT MAX(version) FROM schema_version') as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION == 7, (row[0], CURRENT_VERSION)
        # Idempotent re-run
        await ensure_schema(conn)
        async with conn.execute('SELECT COUNT(*) FROM schema_version WHERE version = 7') as cur:
            row = await cur.fetchone()
        assert row[0] == 1, f'duplicate v7 entry: {row[0]}'
        await conn.close()
        print('OK')
    finally:
        os.unlink(path)

asyncio.run(main())
"
# Expected: 'OK'
```

## Implementation Guidance

Work from project root `~/projects/the-one`. Branch must be `flight/01-tool-reduction-self-modification-teardown`. Leg status `ready` → `in-flight` at start; `landed` at end. **No commit.**

1. **Bump `CURRENT_VERSION`** in `the_one/db/schema.py`:
   ```python
   CURRENT_VERSION = 7
   ```

2. **Add `import json`** at the top of `the_one/db/schema.py` (sibling to the existing `import aiosqlite`). Required for the JSON parsing inside the v7 block.

3. **Append the v7 migration block** to `ensure_schema()`, after the existing `if version < 6:` block (line ~247). Use this exact code:

   ```python
       if version < 7:
           # Strip the seven removed self-modification tool names from every
           # agent's enabled_tools / disabled_tools JSON columns. The names
           # were valid in v6 but reference tools deleted in mission 5
           # flight 1. enabled_tools=NULL means "whitelist disabled, all
           # tools allowed" — preserve NULL as NULL; never coerce to [].
           # An empty whitelist after strip is the correct (locked-down)
           # interpretation: the operator wanted only a removed tool, so
           # widening their scope back to all-tools would be a silent
           # privilege escalation.
           REMOVED = {
               "self_deploy", "rollback", "restart", "run_tests",
               "git", "memory", "mission_control",
           }
           async with conn.execute(
               "SELECT name, enabled_tools, disabled_tools FROM agents"
           ) as cursor:
               rows = await cursor.fetchall()
           for row in rows:
               name = row[0]
               enabled_json = row[1]
               disabled_json = row[2]
               enabled = json.loads(enabled_json) if enabled_json else None
               disabled = json.loads(disabled_json or "[]")
               new_enabled = (
                   [t for t in enabled if t not in REMOVED]
                   if enabled is not None else None
               )
               new_disabled = [t for t in disabled if t not in REMOVED]
               await conn.execute(
                   "UPDATE agents SET enabled_tools = ?, disabled_tools = ? WHERE name = ?",
                   (
                       json.dumps(new_enabled) if new_enabled is not None else None,
                       json.dumps(new_disabled),
                       name,
                   ),
               )
           await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (7,))
           await conn.commit()
           version = 7
   ```

   Notes on the code shape:
   - Mirrors the v3/v5/v6 pattern (inline block, executes one-shot, commits).
   - Uses `async with conn.execute(...) as cursor:` — matches the existing aiosqlite cursor idiom in `_get_version` (line 82) and throughout `the_one/db/repositories.py`. Don't use the bare `cursor = await conn.execute(...)` shape from the flight Technical Approach pseudocode; the codebase has settled on `async with`.
   - Uses positional row access (`row[0]`, `row[1]`, `row[2]`) rather than column-name dict access — aiosqlite returns rows that support both, but positional is unambiguous regardless of `row_factory` setting at migration time.
   - Distinguishes `enabled_json` falsy (`None` or `""`) → `enabled = None` from `enabled_json` truthy → JSON parse. This matches the `repositories.py::_row_to_config` logic at line 97 (`json.loads(row["enabled_tools"]) if row["enabled_tools"] else None`).
   - Distinguishes `disabled_json` falsy (`None` or `""`) → fallback `'[]'` → empty list.
   - The `[t for t in enabled if t not in REMOVED]` preserves order of remaining names.
   - Trailing `version = 7` is dead (v7 is the last block) but kept for symmetry with the v3/v5/v6 pattern and to avoid a structural diff if a v8 lands later.

4. **Update `tests/test_db_migration.py`** — the fixture cleanup (Decision 5):
   - Line 85: change `disabled_tools=["self_deploy"],` to `disabled_tools=["shell"],`.
   - The test does not assert on `disabled_tools`, so no other change is needed.

5. **Add the new test class and test function** to `tests/test_db_migration.py`. The existing module-level imports already include `json`, `aiosqlite`, and `ensure_schema` — reuse them; do **not** add function-scoped imports. Append at the end of the file:

   ```python
   class TestSchemaV7:
       """Tests for the v7 migration that strips removed tool names."""

       async def test_v7_strips_removed_tool_names(self, tmp_path) -> None:
           """v6 → v7: removed tool names are stripped; NULL whitelist is preserved."""
           db_path = tmp_path / "v7-strip.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")

           # Migrate fresh DB straight to current (v7).
           await ensure_schema(conn)

           # Seed four v6-shaped agent rows that simulate legacy data.
           # The v7 strip is a row-content migration, not a DDL change, so
           # column types are identical between v6 and v7. Inserting these
           # rows post-v7-migration and then rewinding schema_version to 6
           # exercises the exact same code path the migration would hit
           # against a real legacy DB.
           await conn.execute(
               "INSERT INTO agents (name, enabled_tools, disabled_tools) "
               "VALUES (?, ?, ?)",
               (
                   "mixed",
                   json.dumps(["self_deploy", "git", "memory", "shell"]),
                   json.dumps(["self_deploy", "shell"]),
               ),
           )
           await conn.execute(
               "INSERT INTO agents (name, enabled_tools, disabled_tools) "
               "VALUES (?, ?, ?)",
               ("nullwhitelist", None, json.dumps(["git"])),
           )
           await conn.execute(
               "INSERT INTO agents (name, enabled_tools, disabled_tools) "
               "VALUES (?, ?, ?)",
               (
                   "removedonly",
                   json.dumps(["self_deploy"]),
                   json.dumps([]),
               ),
           )
           # All-kept row — proves the migration doesn't over-strip.
           await conn.execute(
               "INSERT INTO agents (name, enabled_tools, disabled_tools) "
               "VALUES (?, ?, ?)",
               (
                   "allkept",
                   json.dumps(["shell", "read_file", "write_file"]),
                   json.dumps(["python_exec"]),
               ),
           )
           # Rewind schema_version so ensure_schema sees v6 and reruns v7.
           await conn.execute("DELETE FROM schema_version WHERE version = 7")
           await conn.commit()

           # Run the v7 migration.
           await ensure_schema(conn)

           # Assertion 1: mixed row — kept names survive, removed names gone.
           async with conn.execute(
               "SELECT enabled_tools, disabled_tools FROM agents WHERE name = 'mixed'"
           ) as cur:
               row = await cur.fetchone()
           assert json.loads(row["enabled_tools"]) == ["shell"]
           assert json.loads(row["disabled_tools"]) == ["shell"]

           # Assertion 2: NULL whitelist preserved as NULL (not coerced to []).
           async with conn.execute(
               "SELECT enabled_tools, disabled_tools FROM agents "
               "WHERE name = 'nullwhitelist'"
           ) as cur:
               row = await cur.fetchone()
           assert row["enabled_tools"] is None
           assert json.loads(row["disabled_tools"]) == []

           # Assertion 3: whitelist of only removed names becomes empty list
           # (locked-down — never widened to NULL).
           async with conn.execute(
               "SELECT enabled_tools, disabled_tools FROM agents "
               "WHERE name = 'removedonly'"
           ) as cur:
               row = await cur.fetchone()
           assert json.loads(row["enabled_tools"]) == []
           assert json.loads(row["disabled_tools"]) == []

           # Assertion 4: all-kept row — pass-through (proves no over-strip).
           async with conn.execute(
               "SELECT enabled_tools, disabled_tools FROM agents WHERE name = 'allkept'"
           ) as cur:
               row = await cur.fetchone()
           assert json.loads(row["enabled_tools"]) == ["shell", "read_file", "write_file"]
           assert json.loads(row["disabled_tools"]) == ["python_exec"]

           # Assertion 5: schema_version is 7.
           async with conn.execute(
               "SELECT MAX(version) FROM schema_version"
           ) as cur:
               row = await cur.fetchone()
           assert row[0] == 7

           await conn.close()
   ```

   Notes:
   - The test uses `tmp_path` directly (a pytest built-in fixture) and creates its own connection rather than reusing the `setup` fixture from `TestMigration`, because it needs to seed raw rows before the v7 migration runs.
   - The "rewind schema_version" technique (`DELETE FROM schema_version WHERE version = 7`) lets us test the v6→v7 transition against the real `ensure_schema()` code path without duplicating any of v1-v6's setup. `_get_version()` returns `MAX(version)`; removing the v7 sentinel makes it report 6, triggering the v7 block.
   - Module-level imports (lines 5, 9, 15) already cover `json`, `aiosqlite`, and `ensure_schema`. Reuse them; no function-scoped re-imports.
   - Four rows are seeded (mixed, nullwhitelist, removedonly, allkept) — five assertion bundles total. The all-kept row guards against accidental over-stripping.

6. **Run the migration test file in isolation**:
   ```bash
   python -m pytest tests/test_db_migration.py -v
   ```
   Expected: 4 (existing) + 1 (new) = 5 tests pass.

7. **Run the full unit suite**:
   ```bash
   python -m pytest tests/ --tb=short -q --ignore=tests/browser
   ```
   Expected: 1 pre-existing CSS-token failure; everything else green. The new test should add to the passed-count.

8. **Run the end-to-end smoke** (fresh DB → v7, idempotent re-run):
   ```bash
   python -c "
   import asyncio, aiosqlite, tempfile, os
   from the_one.db.schema import ensure_schema, CURRENT_VERSION

   async def main():
       fd, path = tempfile.mkstemp(suffix='.db')
       os.close(fd)
       try:
           conn = await aiosqlite.connect(path)
           conn.row_factory = aiosqlite.Row
           await conn.execute('PRAGMA foreign_keys=ON')
           await ensure_schema(conn)
           async with conn.execute('SELECT MAX(version) FROM schema_version') as cur:
               row = await cur.fetchone()
           assert row[0] == CURRENT_VERSION == 7, (row[0], CURRENT_VERSION)
           await ensure_schema(conn)
           async with conn.execute('SELECT COUNT(*) FROM schema_version WHERE version = 7') as cur:
               row = await cur.fetchone()
           assert row[0] == 1, f'duplicate v7 entry: {row[0]}'
           await conn.close()
           print('OK')
       finally:
           os.unlink(path)

   asyncio.run(main())
   "
   ```
   Expected: `OK`.

9. **Run the targeted verification commands** from the Verification Steps section.

10. **Update the flight log**:
    - Append a `### 03-schema-v7-tool-name-strip` entry under `## Leg Progress` with status `landed`, summary of changes (CURRENT_VERSION bump, v7 strip block, new test, fixture cleanup), test counts, and any notable findings during implementation.

11. **Set leg status to `landed`** in this file's header. Do **NOT** commit. Do **NOT** check off the leg in `flight.md`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`enabled_tools = NULL` (whitelist mode disabled)**: preserved as NULL, never coerced to `[]`. The migration's `if enabled is not None else None` branch handles this. Critical for not silently widening a whitelist-disabled agent's scope.
- **`enabled_tools = ""` (empty string)**: not expected from production writes (`SQLiteAgentStore.save()` always serializes via `json.dumps` or writes `None`), but the migration's `enabled = json.loads(enabled_json) if enabled_json else None` treats empty-string identically to NULL — falsy → `enabled = None` → preserved as NULL. Same handling as `repositories.py::_row_to_config` line 97.
- **`enabled_tools = "[]"` (empty whitelist — blocks all tools)**: parses to `[]`, filter returns `[]`, written back as `"[]"`. Pass-through, no change.
- **`enabled_tools` of only removed names** (e.g., `["self_deploy"]`): becomes `[]` after strip. Locked-down state — agent has no tools. Documented behavior; not a bug.
- **`disabled_tools = NULL`**: not expected (column has `DEFAULT '[]'`), but `disabled_json or "[]"` handles it gracefully → empty list → written back as `"[]"`.
- **`disabled_tools = "[]"`**: parses to `[]`, no-op.
- **Empty agents table** (zero rows): SELECT returns no rows; the `for row in rows` loop runs zero times; schema_version still gets `(7,)` inserted. Idempotency-safe.
- **Re-running `ensure_schema()` on a DB already at v7**: `_get_version()` returns 7, the `if version < 7:` block is skipped — no duplicate strip, no duplicate INSERT into schema_version. Verified by smoke-test step 8.
- **Invalid JSON in a column** (corrupted data): `json.loads` raises `json.JSONDecodeError`, migration aborts with the original error. Not silently swallowed. Out of L3 scope — repair tooling for corrupted DBs is a separate concern. **No test required** for this case; the migration's behavior is "fail loudly", which is the right default and doesn't need positive coverage.
- **A row with both `enabled_tools` whitelist mode and `disabled_tools` blacklist** (legitimate per `is_tool_enabled` semantics): both lists strip independently. Order preserved within each.
- **Migration runs against a fresh DB** (version=0): all blocks v1-v7 run in sequence. The v7 block's SELECT returns no rows (agents table just created and empty); schema_version gets all of 1-7 entries. Tests cover this implicitly via the smoke-test step 8.
- **`row_factory = aiosqlite.Row` in production vs not set in migration context**: the migration uses positional access (`row[0]`, `row[1]`, `row[2]`) which works regardless of `row_factory`. Tests set `row_factory = Row` for assertion-side dict-key access; the migration block doesn't depend on it.

## Files Affected

- `the_one/db/schema.py` — `CURRENT_VERSION` bump 6 → 7; `import json`; new v7 migration block in `ensure_schema()`
- `tests/test_db_migration.py` — fixture line `disabled_tools=["self_deploy"]` → `["shell"]`; new `TestSchemaV7::test_v7_strips_removed_tool_names`
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` — append leg progress entry

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (NOTE: per the agentic-workflow skill, this leg does NOT commit; the post-L6 review handles commit. Mark leg `landed`, not `completed`.):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/ --ignore=tests/browser` green except for the pre-existing CSS anomaly)
- [ ] Update flight-log.md with leg progress entry (status `landed`)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do **NOT** check off this leg in flight.md yet (deferred to post-L6 commit)
- [ ] Do **NOT** commit (deferred to post-L6 batch commit)
- [ ] Signal `[HANDOFF:review-needed]`

# Leg: name-repair

**Status**: completed
**Flight**: [Safe names](../flight.md)

## Objective
At every startup, before any request is served, rename each stored agent, model provider, knowledge base and MCP server whose name breaks the rule to a safe, unique name, through the rename paths that carry its references, logging each rename and never stopping the app from starting.

## Context
- Flight DD11 (startup, Python, after the key reconcile, raw-`SELECT` scan, skip surface rows, per-row and whole-pass try/except, idempotent, never inside another transaction) and DD12 (repair naming).
- Leg 1: `the_one/naming.py::check_name` (the rule) and its constants; the JSON import skips bad names, so it cannot re-import one after a repair.
- Leg 2: the carries this leg calls — `SQLiteAgentStore.rename` (now rewrites connector bindings), `the_one/mcp/rename_references.py::carry_mcp_rename` (never raises; returns failed agents), `the_one/knowledge/kb_rename.py::carry_kb_rename(existing, updated, *, get_agent_store)` (never raises; slug-unchanged early return), `self_configuration.manage.cascade_rename` (surface marker after an agent rename, as `rename_agent` calls it).
- DD6: `default` is a legal agent name and is never repaired. DD2: a stored name that differs from its trimmed form only by surrounding whitespace is not rule-breaking (`check_name` returns the trimmed value without raising) and is not repaired.
- Providers are referenced by id everywhere (`AgentConfig.provider_config_id`), so a provider rename is a plain row update.

## Inputs
- `the_one/interfaces/web/app.py` lifespan: `init_db()`, `reconcile_pending_key(conn, get_encryptor(...))`, `store = SQLiteAgentStore(conn)`, `migrate_json_to_sqlite(store)`, then `register_credential_source_once()`, `MCPSourceRepository(conn, get_encryptor(...))`, `manage.reconcile_on_startup(...)`.
- `the_one/db/repositories.py`: `SQLiteAgentStore.rename`, `KnowledgeBaseRepository` (`get`, `update`), `MCPSourceRepository` (`get`, `update`), `LLMProviderRepository` (`get`/`update` or the plain table), the `agents`, `llm_providers`, `knowledge_bases`, `mcp_sources` tables.
- `the_one/self_configuration/constants.py::is_surface_row`.
- The startup try/except pattern for non-fatal startup work in `app.py` (connectors, watches).

## Outputs
- `the_one/naming.py::repair_name(value, *, kind, taken) -> str`.
- New `the_one/db/name_repair.py::repair_unsafe_names(conn, *, agent_store, mcp_repo, kb_repo, provider_repo) -> list[tuple[str, str, str]]` (kind, old, new for each rename done; for tests and the log), wired into the lifespan between `migrate_json_to_sqlite(store)` and `reconcile_on_startup`.
- Tests: `tests/test_name_repair.py` (unit tier), plus `repair_name` cases in `tests/test_naming.py`.
- `the_one/agents.md` "Naming rule" section gains "The startup repair".

## Acceptance Criteria
- [ ] `repair_name(value, kind=..., taken=...)` replaces each `/` and `\` with a space, maps every whitespace control character (a `Cc` character for which `str.isspace()` is true: tab, newline, carriage return, vertical tab, form feed) to a space, deletes the other `Cc` characters and the bidi-control characters, collapses runs of whitespace to one space, trims, truncates to 64 characters and trims again; a result that is empty, `.` or `..` becomes the kind's fallback ("Renamed agent", "Renamed provider", "Renamed knowledge base", "Renamed MCP server"); when the result's `casefold()` is in `{t.casefold() for t in taken}` it appends ` 2`, ` 3`, … (shortening the base so the whole stays within 64) until it is free. Its result always passes `check_name` unchanged (property-style test over a list of awkward inputs, including `"a\tb"` → `"a b"`, `"a\nb"`, a U+202E name, an emoji, a combining sequence cut at 64, and a name that is only `/`). `kind` is one of `"agent"`, `"provider"`, `"knowledge_base"`, `"mcp_source"`.
- [ ] `repair_unsafe_names` reads names with a raw `SELECT` per table (never through `store.list`/`load`), repairs only names for which `check_name` raises, and builds `taken` per kind from every stored name of that kind plus names assigned earlier in the pass.
- [ ] **Agents**: each bad agent is renamed with `SQLiteAgentStore.rename(old, new)` followed by `cascade_rename(old, new, mcp_repo=mcp_repo)`; afterwards its chats, rules, notes, revisions (these three follow through their `ON UPDATE CASCADE` foreign keys on `agents.name`; the connection runs with `PRAGMA foreign_keys=ON`) and connector bindings (`default_agent`, `channel_map`) name the new name, and `GET /api/agents/{new}` returns 200. `default` is never touched. `cascade_rename` runs in its own `try` after the rename: it lists every MCP source (`find_surface_row`), so one undecryptable source makes it raise; then the rename stands and a WARNING says the surface marker may still name the old agent (tested).
- [ ] **MCP sources**: detection and the surface skip use the raw scan (`SELECT id, name, config FROM mcp_sources`; `config` is plaintext JSON and `is_surface_row` reads only its `self_configuration` marker); only a bad, non-surface source is then loaded with `mcp_repo.get(id)` inside the row's `try` (a source whose secrets fail to decrypt raises there and is skipped with a WARNING), updated with the new name through `mcp_repo.update`, then `carry_mcp_rename(id, old, new, agent_store=..., mcp_repo=...)`; an attached agent's override key and `disabled_tools` entries follow. A self-configuration surface row (`is_surface_row`) is skipped (left for `reconcile_on_startup`), and its name still counts in `taken`.
- [ ] **Knowledge bases**: each bad KB is updated through `kb_repo.update` with the new name, then `carry_kb_rename(existing, updated, get_agent_store=...)`; a `disabled_tools` entry follows when the derived tool name changed.
- [ ] **Providers**: each bad provider gets a raw `UPDATE llm_providers SET name = ?, updated_at = ? WHERE id = ?` inside `write_transaction` (not `get` + `update`, which would decrypt and re-encrypt `api_key`/`secrets` and fail on a bad ciphertext); its other columns are byte-identical afterwards (tested). Provider writes run no type validation, so a `mock` provider is not special.
- [ ] Each rename logs one WARNING: `"renamed %s %r to %r: its name broke the naming rule"` (kind, old, new) or equivalent wording naming all three.
- [ ] **Never blocks startup**: each row's repair is wrapped in `try/except Exception` (a WARNING with `exc_info`, then the next row); the whole pass is wrapped in the lifespan the same way. A test injects a raise for one row (e.g. a store whose `rename` raises for one name) and asserts the other rows are repaired and the function returns normally.
- [ ] **Idempotent**: a second call on the repaired database renames nothing and logs nothing at WARNING; a clean database does nothing.
- [ ] **Lifespan**: the app starts on a database seeded with one bad row of each kind; after startup `GET /api/agents/{repaired name}` returns 200, `GET /api/agents` lists it, and the other three kinds show their repaired names through their list routes.
- [ ] `the_one/agents.md` "Naming rule" gains "The startup repair" (where it runs and why there, what it renames and how, the naming, surface rows skipped, never blocking, idempotent, `default` untouched). If the operator-facing upgrade note belongs in release notes, add a line to the next unreleased notes file under `docs/releases/` only if one exists; otherwise record in the flight log that the release notes should mention it.
- [ ] `make test-unit` shows only the baseline failures; ruff passes.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_naming.py tests/test_name_repair.py -x --timeout 60`
- `make test-unit` once at leg end.
- ruff check and format.

## Implementation Guidance

1. **`repair_name`** in `the_one/naming.py` beside `check_name`, reusing the module's bidi set and `MAX_NAME_LENGTH`; a `_FALLBACK = {"agent": "Renamed agent", ...}` table.

2. **`the_one/db/name_repair.py`.** Module docstring naming sortie 06 DD11-DD12 and why this is Python in the lifespan rather than a `schema.py` migration (encrypted `mcp_overrides` needs the encryptor). One function per kind, each scanning `SELECT id, name FROM <table>` (agents: `SELECT name FROM agents`), each row in its own `try/except`. For MCP, check `is_surface_row` on the loaded source before renaming. Return the list of renames. Never open a transaction around these calls (`write_transaction` rejects same-task re-entry, and each call manages its own).

3. **Lifespan.** In `app.py`, move the `_self_configuration_mcp_repo = MCPSourceRepository(conn, get_encryptor(settings.data_dir))` construction above the repair (the encryptor is ready after `reconcile_pending_key`; it is held by reference) and reuse that instance for both the repair and `reconcile_on_startup`. Construct a `KnowledgeBaseRepository` for the repair (none exists at that point); providers use the raw `UPDATE`. Call `repair_unsafe_names` after `await migrate_json_to_sqlite(store)` and before `register_credential_source_once()`/`reconcile_on_startup`, inside `try/except Exception` with a WARNING. `carry_kb_rename` takes a zero-argument async callable for the store: pass a small `async def` returning `store`.

4. **Tests.** `tests/test_name_repair.py`: databases from `tests/_schema_template.py`; seed bad rows with raw SQL or repositories (the API now refuses them). Seed an agent `ops/bot` with a chat, a rule, a note, a revision and a connector binding (`default_agent` and a `channel_map` value); an MCP source `team/tools` attached to an agent with an override under `team/tools` and a disabled tool `mcp__team_tools__x`; a KB `My/Notes` attached to an agent with its disabled `kb__…__search` name; a provider `Local/Ollama`; also a second agent already named `ops bot` to force numbering (`ops bot 2`), a `..` agent (→ "Renamed agent"), a `default` agent (untouched), a padded `"  fine  "` agent (untouched), a 70-character name (truncated), and a legacy surface row named `self-configuration (ops/bot)` (untouched by the repair). Assert names, references, WARNINGs (`caplog`), the return value, idempotence, and the injected-failure case. For the lifespan test, follow `tests/test_lifespan.py`'s `_isolated_data_dir` fixture (monkeypatch `settings.data_dir`, `copy_template(settings.db_path)`, reset the db connection) and the `reset_lifespan_singletons` fixture (`tests/conftest.py`); seed the bad rows by raw SQL into the copied template before starting; drive the lifespan with `asgi_lifespan.LifespanManager` as `tests/conftest.py` does; attach `tests/_credential_helpers.py::auth_headers()` to requests. Log kinds as human words ("knowledge base", "MCP server").

## Edge Cases
- **Two bad names that repair to the same name** (`a/b`, `a\b` → `a b`, `a b 2`): `taken` grows within the pass.
- **A repaired agent name colliding case-insensitively with an existing one** (`Ops Bot` exists): numbered.
- **An agent whose rename succeeds but whose `cascade_rename` raises**: logged; the agent rename stands (it committed).
- **An MCP source whose `get` fails to decrypt**: that row is skipped with a WARNING (its name stays bad until a later start); other rows proceed.

## Files Affected
- `the_one/naming.py` - `repair_name`
- `the_one/db/name_repair.py` - new
- `the_one/interfaces/web/app.py` - lifespan call
- `tests/test_name_repair.py` - new; `tests/test_naming.py` - `repair_name` cases
- `the_one/agents.md` - "The startup repair"

---

## Post-Completion

The Developer marks the leg `landed`, records changes and verification in the flight log, and signals `[LAND:leg]`. Nothing is committed.

## Citation Audit
Checked against the worktree with legs 1-2 landed: the lifespan order (`reconcile_pending_key` → `SQLiteAgentStore(conn)` → `migrate_json_to_sqlite(store)` → `register_credential_source_once()` → `MCPSourceRepository(...)` → `reconcile_on_startup`), `is_surface_row` in `self_configuration/constants.py`, `SQLiteAgentStore.rename`, `KnowledgeBaseRepository`, `MCPSourceRepository`, `LLMProviderRepository.update` — verified. `carry_mcp_rename` and `carry_kb_rename` signatures from leg 2's report; re-read them before implementing.

Design review (Developer, 2026-10-26): approve with changes; adopted — whitespace controls become spaces, the raw provider `UPDATE`, the raw MCP scan with `get` only for rows to rename, `cascade_rename` in its own `try`, surface-row names stay in `taken`, the lifespan repository reuse and test pattern. Its open question (do rules/notes/revisions follow a rename?) is answered by the flight's citation audit: `ON UPDATE CASCADE` foreign keys, `PRAGMA foreign_keys=ON` on the connection.

# Leg: secrets-store

**Status**: completed
**Flight**: [Secrets](../flight.md)

## Objective
Store secrets: schema v51, a repository, the `/api/secrets` routes (write-only values), the eighth encrypted corpus, agent grants (`secret_ids`), the `allowed_tools` rule with its refused set, the MCP-rename carry, and `GET /api/tool-names`, with tests and docs. No runtime substitution and no UI yet.

## Context
- The design is the flight's **DD2 (server half), DD3 (server half), DD4, DD5 and DD6**. Read `../flight.md` first; this leg does not restate the rationale. Where this leg and the flight disagree, this leg wins and the disagreement is a defect to report.
- Charter criteria this leg serves: 4 ("No API ever returns the value"; a Library change is a stored change), and the storage half of 1-3.
- **Security-sensitive:** a new encrypted corpus and a write-only value path. No value in any response (including a 422), error, or log line.
- **Schema change:** the v51 migration is created **and executed** in this leg (schema pins and the session template).
- Branch `sortie/10-secrets` from `origin/main` at `481546e0`. No prior leg.

## Inputs
- `the_one/db/schema.py` at `CURRENT_VERSION = 50`; the v50 block (`agent_mcp_tool_cache`) and the guarded `ALTER TABLE` pattern of v46.
- `the_one/db/encryption_corpora.py` (`Corpora`, `gather_corpora`, `count_items_with_secrets`), `the_one/db/key_reconcile.py::_ENCRYPTED_CORPORA`, `interfaces/web/api.py::rotate_encryption_key` and `get_encryption_status`, `tests/test_encrypted_corpora_guard.py`, `tests/test_encryption_status.py`.
- `interfaces/web/api.py`: `_read_json` (`:141`), `_validation_detail` (`:183-189`, `include_input=False`), `_checked_name` (`:192-197`), `_name_conflict_detail` (`:200`), `create_agent`/`update_agent` (the `kb_ids` preserve at `:1526-1533`), `list_tools` (`:921-926`), the MCP PUT's `carry_mcp_rename` call (`:3784-3800`).
- `the_one/mcp/rename_references.py::carry_mcp_rename` (agent-scoped, never raises); `the_one/db/name_repair.py:111`.
- `the_one/agent/tool_names.py` (notes and routine tool names), `the_one/self_configuration/constants.py::SURFACE_TOOL_PREFIX`, `tools/builtins.py` (`send_to_platform_channel`), `tools/_search_tools.py` (`search_tools`), `agent/core.py` (`continue` short-circuit, `:494`).
- `interfaces/web/middleware.py:~389-410` (confined-source path scoping for the self-configuration loopback credential).
- `tests/test_api_name_rule.py` (`PREFIXES`, `CHECKED`/`EXEMPT`, `TestCreateRefuses`), `tests/_schema_template.py`, `tests/_api_app.py::shared_app()` and `tests/test_api_app_guard.py`.

## Outputs
- Schema: `the_one/db/schema.py` (v51), `tests/test_schema.py` pins.
- Server: `the_one/db/repositories.py` (`SecretRepository`; `SQLiteAgentStore` `secret_ids` + `list_by_secret`), `the_one/agent/config.py` (`secret_ids`), `the_one/db/encryption_corpora.py`, `the_one/db/key_reconcile.py`, a new **`the_one/secret_store/`** package (not `the_one/secrets/`: seven modules do a bare `import secrets` of the stdlib, and a same-named package invites shadowing when `the_one/` lands on `sys.path`) with `__init__.py` (empty) and `refused.py` (the refused-tool set and its predicate; leg 2's `runtime.py` joins it), a new router module `the_one/interfaces/web/secrets_api.py` following `routines_api.py` exactly (a prefix-less `APIRouter`, `api.py` helpers reached through a lazy `from the_one.interfaces.web import api as _api` inside handlers (`routines_api.py:44`), included at the bottom of `api.py` after `_routines_router` (`api.py:7242-7244`)), `the_one/interfaces/web/api.py` (agent `secret_ids`, rotation and status, the MCP-rename call site, the router include), `the_one/naming.py` (`NAME_CONFLICT_SECRET`), `the_one/mcp/rename_references.py`, `the_one/db/name_repair.py`, `the_one/db/repositories.py` (also an all-rows read on the agent MCP tool cache, AC13).
- Tests: new unit test files (suggested `tests/test_secrets_store.py`, `tests/test_secrets_api.py`, `tests/test_tool_names_api.py`), plus updates to `tests/test_encrypted_corpora_guard.py`, `tests/test_encryption_status.py`, `tests/test_api_name_rule.py`, `tests/test_schema.py`, and any rename-references test file.
- Docs: `the_one/agents.md` (new "Secrets (sortie 10)" section: storage, routes, corpus, refused set, rename carry, tool names), `SECURITY-MODEL.md` (a "Secrets" section, storage part), `CLAUDE.md` (a short "Secrets (sortie 10)" paragraph naming the routes; leg 2 extends it).

## Acceptance Criteria

**Schema and model (DD4)**
- [ ] AC1. `CURRENT_VERSION = 51`. A v51 block creates:
  - `secrets(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, description TEXT NOT NULL DEFAULT '', allowed_tools TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`;
  - `secret_values(id TEXT PRIMARY KEY, secret_id TEXT NOT NULL REFERENCES secrets(id) ON DELETE CASCADE, key TEXT NOT NULL UNIQUE COLLATE NOCASE, value TEXT NOT NULL, position INTEGER NOT NULL)`;
  - `agents.secret_ids TEXT NOT NULL DEFAULT '[]'` through a guarded `ALTER TABLE` (`PRAGMA table_info`).

  The block follows the v50 shape and the frozen-imports rule. `tests/test_schema.py` pins the tables, columns and version. A database at v50 with agent rows migrates to v51 with every agent's `secret_ids == []`. Ids are `uuid.uuid4().hex`, as the other repositories mint them (`repositories.py:1766`). Secret names are unique **ignoring case** (`COLLATE NOCASE`; v51 is unshipped, so there is no cost). Renaming a secret affects nothing else, since grants are by id.
- [ ] AC2. `AgentConfig.secret_ids: list[str] = Field(default_factory=list)` sits beside `kb_ids`. `SQLiteAgentStore.save` and `_row_to_config` round-trip it. `list_by_secret(secret_id)` returns the agents holding it (modelled on `list_by_kb`).
- [ ] AC3. `SecretRepository` has `list`, `get`, `create`, `update` and `delete`, and each write is one `write_transaction`.
  - Values are stored as `Encryptor.encrypt` ciphertext; reads decrypt only on an explicit internal method (e.g. `get_values(secret_id)` / `all_values()`) that leg 2 will use. The list/get methods used by the routes never decrypt.
  - Pairs are written delete-and-reinsert in the update's transaction, so swapping two keys in one update succeeds.
  - `delete` removes the secret (values cascade; the shared connection sets `PRAGMA foreign_keys=ON`, `db/connection.py:55`, and a test proves the cascade) and removes its id from every agent's `secret_ids` in the **same** transaction. The removal is a Python read-modify-write over `list_by_secret`'s agents, keeping each list's order, and it does **not** bump `agents.updated_at`. It is a reference cleanup like the rename cascades; an in-flight agent PUT that re-sends the id is refused by AC11's new-id check, since the secret is gone.
  - `update` re-checks key collisions with other secrets inside its transaction, and maps an `IntegrityError` on `secret_values.key` to the AC6 422 on the right row (by key). A key race therefore never surfaces as a 500.

**Routes (DD5)**
- [ ] AC4. `GET /api/secrets`, `GET /api/secrets/{id}`, `POST /api/secrets` (201), `PUT /api/secrets/{id}`, `DELETE /api/secrets/{id}` (204) exist behind the credential gate.
  - An unknown id is 404.
  - Responses have the shape `{id, name, description, allowed_tools, values: [{id, key, value: "__MASKED__"}], created_at, updated_at}`, with values in `position` order.
- [ ] AC5. **No route ever returns a stored value or any fragment of it.** A test stores values of 4, 12 and 40 characters (one with both quote types and a backslash). It then calls every route, including a 404, a 409, every 422 kind and a malformed JSON body that contains a value, and asserts that no plaintext value and no 4-character tail appears in any response body.
- [ ] AC6. The routes take no pydantic body parameter. They read `_read_json` and validate by hand, with 422 details built through `_validation_detail` (`include_input=False`) or the same list shape. Each 422 detail carries a `loc` and a one-sentence `msg`:
  - `["name"]`: through `_checked_name` (POST, and PUT when present).
  - A duplicate name, **ignoring case**, is a **409**. The handler checks first. An `IntegrityError` on insert or rename is also mapped to the 409, so a race is never a 500. The body is built with `_api._name_conflict_detail(...)` (a formatter only) and a new `NAME_CONFLICT_SECRET = "A secret with this name already exists."` in `the_one/naming.py` beside `NAME_CONFLICT_AGENT`. A PUT that renames a secret to its own name in another case is allowed.
  - `["description"]`: a description that is not a string.
  - `["values"]`: missing on POST, not a list, or empty.
  - `["values", i, "key"]`: breaks `^[A-Za-z0-9_-]{1,64}$`, repeats within the body ignoring case, or belongs to another secret ignoring case. The message says which.
  - `["values", i, "value"]`: not a string, empty, `__MASKED__` without an `id`, or `__MASKED__` with an `id` that is not a pair of this secret.
  - `["values", i, "id"]`: an `id` repeated within the body (on the second occurrence).
  - `["allowed_tools"]`: missing on POST, not a list, or empty.
  - `["allowed_tools", i]`: not a string; empty or over 128 characters after trimming; contains whitespace; or is in the refused set (AC9), with the sentence "{name} stores or publishes what it receives, so it can't receive secrets."
- [ ] AC7. PUT is partial at the top level: an omitted `name`, `description`, `allowed_tools` or `values` keeps the stored field. When `values` is present it is the full ordered list:
  - `__MASKED__` with this secret's pair `id` keeps that ciphertext, even under a changed key;
  - a new string is encrypted;
  - an omitted pair is deleted.

  Tests cover keep, replace, delete, reorder, key rename with kept value, and a two-key swap.
- [ ] AC8. `/api/secrets` is registered in `tests/test_api_name_rule.py`: `PREFIXES`, the POST and PUT routes in `CHECKED`, and a `TestCreateRefuses` case. `test_every_route_is_classified` passes.

**Allowed tools (DD3, server half)**
- [ ] AC9. `the_one/secret_store/refused.py` defines the refused set and a predicate `is_refused_tool(name) -> bool`.
  - **Import rule:** `the_one/agent/__init__.py` imports `core` and `factory`, and leg 2 makes `core` import `secret_store`. So `refused.py` must not import from `the_one.agent` at module level. It imports `the_one.agent.tool_names` lazily inside the function that builds the set (cached after the first call). `self_configuration/constants.py` imports nothing from `the_one` at runtime and may be imported at the top.
  - A test imports `the_one.secret_store.refused` in a fresh interpreter (`subprocess` with `-c`) to prove there is no cycle.
  - The predicate is true for:
  - every notes and routine tool name, imported from `agent/tool_names.py`, never retyped;
  - any name starting with `SURFACE_TOOL_PREFIX`;
  - `send_to_platform_channel`, `continue` and `search_tools`.

  A unit test lists the set, and a test fails if `agent/tool_names.py` gains a notes or routine name the predicate misses (iterate the module's exported names).
- [ ] AC10. Both callers of `carry_mcp_rename` (the `api.py` MCP PUT and `db/name_repair.py`) also carry the rename into `secrets.allowed_tools`, through a sibling function in `rename_references.py` (suggested `carry_mcp_rename_into_secrets(old_name, new_name, *, secret_repo, mcp_repo)`).
  - **Global, not agent-scoped.** Secrets aren't attached to agents, so the "old name still in use" check scans **all** MCP sources (`mcp_repo.list()`) for one whose normalized name equals the old normalized name. The renamed row is already saved under its new name, so no source id is needed.
  - It is a no-op when the old and new normalized prefixes are equal, or when another source still has the old normalized name.
  - **Matching rule:** each entry that `startswith("mcp__{normalized old}__")` becomes `"mcp__{normalized new}__" + rest`. The list is then de-duplicated, keeping first occurrences in order.
  - It uses one write transaction, never raises, and logs a WARNING on failure, like its sibling.
  - **At the `api.py` call site:** `carry_mcp_rename` runs inside the `else:` of the agent-store `try` (`api.py:3784-3800`). The secrets carry gets **its own** `try`, so an agent-store failure never skips it.
  - **At `name_repair.py:111`:** `mcp_repo` is in scope; construct the `SecretRepository` there.
  - Tests cover both callers, the no-op cases and de-duplication.

**Agent grants (DD2, server half)**
- [ ] AC11. `create_agent` accepts `secret_ids` (default `[]`). `update_agent` keeps the stored `secret_ids` when the key is omitted, and an explicit `[]` clears it (copy the `kb_ids` pattern).
  - A non-list or non-string entry is already a pydantic 422 on `("secret_ids", i)` through `AgentConfig.model_validate` and `_validation_detail`, with no extra code.
  - A POST or PUT that **adds** an id not in the secrets table is a 422 on `["secret_ids", i]`. Only ids new relative to the stored list are checked: `existing.secret_ids` on PUT, which is in scope near `api.py:1526`, and `[]` on POST.
  - The existence check runs **after** validation and **before** `store.save`, where `_validate_tool_overrides` runs (`api.py:1456`).
  - Agent GET responses carry `secret_ids`.
  - Self-configuration's write tools cannot change `secret_ids`: they write only description and system prompt, pinned by an existing or new test.

**Encryption (DD6)**
- [ ] AC12. `secret_values.value` is the **eighth corpus** (a corpus is a `Corpora` field). `_ENCRYPTED_CORPORA` counts (table, column) **pairs**, and goes from eight pairs to **nine**, because providers contribute two pairs. Don't "fix" the tuple to eight. The guard's regexes accept `SELECT id, value FROM secret_values` (`id` is a lookup column) and `UPDATE secret_values SET value = ? WHERE id = ?` unchanged. `gather_corpora(strict=False)` already skips a missing table. Register it in all five places:
  - `_ENCRYPTED_CORPORA`;
  - a `Corpora.secret_values` field and a `SELECT id, value FROM secret_values` in `gather_corpora`;
  - `count_items_with_secrets`, which counts secrets with at least one value;
  - `rotate_encryption_key`, which re-encrypts the field and adds an `UPDATE secret_values SET value = ? WHERE id = ?` loop in its write transaction;
  - the "seven corpora" docstrings and the rotation log line, now "eight".

  `tests/test_encrypted_corpora_guard.py` passes unbypassed, and `tests/test_encryption_status.py` counts a stored secret. A test stores a secret, rotates the key, and decrypts the value to the original through the repository's internal read.

**Tool names (DD3)**
- [ ] AC13. `GET /api/tool-names` returns `[{name, source, source_name, description}]`, deduplicated by `name` and sorted by name. It is the union of:
  - built-ins from `BuiltinToolProvider`, with `source` `"builtin"` and `source_name` `null`;
  - for each MCP source except the self-configuration surface (excluded with `is_surface_row(source)`, as `mcp/_tool.py:37` imports it, not a name compare), the cached tools in `source.config["_cache"]["tools"]` (as `self_configuration/projection.py:151` reads them). Each is named `mcp__{normalized source name}__{tool}` through `_normalize_source_name` (`mcp/_tool.py:54`, imported lazily in the handler, never reimplemented), with `source` `"mcp"` and `source_name` the source's name;
  - the tools in **all** `agent_mcp_tool_cache` rows. The `tools` column is a JSON list of `{name, description, input_schema}`, and the repository's `_decode` returns `[]` on bad JSON. The repository has only per-agent reads, so add an all-rows read (e.g. `AgentMcpToolCacheRepository.list_all() -> [(source_id, tools)]`). Resolve `source_id` to the source's name, and skip rows whose source is gone or is the surface.

  Refused names (AC9, which also covers `mcp__self-configuration__*`) are excluded. Agent-derived names (`kb__…__search`, notes and routine tools) are **not** included. Tests seed a built-in set, two MCP sources (one with a name that needs normalizing, one surface row) and per-agent cache rows for two agents that list the same tool.

**Loopback scoping**
- [ ] AC14. A request carrying the self-configuration loopback credential to `/api/secrets` and to `/api/tool-names` is refused (403) by the middleware's confined-source path scoping (`middleware.py:405-409`: a confined caller outside `MOUNT_PATH` gets 403). A test pins both, reusing the existing middleware or self-configuration test helper that mints a confined-source credential (find it with `grep -rn "CONFINED_SOURCE_PATHS\|self-configuration" tests/test_*middleware* tests/test_self_config*`). No middleware change is expected; if one is needed, stop and report.
- [ ] AC14b. A test runs the create, update and delete routes under `caplog` at DEBUG and asserts that no stored value appears in any log record.

**Gate and docs**
- [ ] AC15. `THE_ONE_TEST_NETNS=1 make test-unit` passes (expected skip count per CLAUDE.md, 15 under netns; explain any other count from `-rs`). New tests build databases from `tests/_schema_template.py`, and API tests use `shared_app()` unless they need their own app (then `tests/test_api_app_guard.py::ALLOWLIST`). `ruff check` and `ruff format --check` are clean on the touched paths.
- [ ] AC16. The docs listed under Outputs are updated, and `CLAUDE.md` names the new routes in one short paragraph without duplicating `agents.md`.

## Verification Steps
- AC1-AC3, AC12: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_schema.py tests/test_secrets_store.py tests/test_encrypted_corpora_guard.py tests/test_encryption_status.py -x --timeout 60`.
- AC4-AC8, AC11, AC14: `... tests/test_secrets_api.py tests/test_api_name_rule.py -x --timeout 60`, plus the agent API tests touched by `secret_ids`.
- AC9-AC10: the refused-set tests and the rename tests (both callers).
- AC13: `tests/test_tool_names_api.py`.
- AC15: `THE_ONE_TEST_NETNS=1 make test-unit` once at leg end; `ruff check the_one/ tests/` and `ruff format --check the_one/ tests/`.
- For every new security test (AC5, AC6's no-echo, AC11's unknown-id refusal, AC12's rotation, AC14), report whether it was falsified (shown to fail with the protection removed by editing, then restored by editing).

## Implementation Guidance

1. **Schema first.** Add the v51 block after v50 in `ensure_schema`, bump `CURRENT_VERSION`, update the pins. Confirm the session template picks it up (run one template-based test).
2. **Model and agent store.** `AgentConfig.secret_ids`; `SQLiteAgentStore.save` (INSERT column list, `ON CONFLICT DO UPDATE` list, params), `_row_to_config`, `list_by_secret`.
3. **`the_one/secret_store/refused.py`**: lazy import of `the_one.agent.tool_names` inside the builder (AC9's import rule), plus the fresh-interpreter import test.
4. **`SecretRepository`** in `db/repositories.py`. Use the app `get_encryptor()` at call time (never capture a key). Ids are `uuid.uuid4().hex`.
5. **Router module** `interfaces/web/secrets_api.py`, a copy of the `routines_api.py` pattern: a prefix-less `APIRouter`, `_api.` helpers through a lazy import inside the handlers (so test patches of `api.get_connection` keep working), and the include at the bottom of `api.py` after `_routines_router`. Use `_api._read_json`, `_api._checked_name`, `_api._name_conflict_detail` and `_api._validation_detail`. Keep validation in plain functions that return a list of detail dicts, so POST and PUT share the 422 builder.
6. **Agent routes.** `secret_ids` in `create_agent`/`update_agent`: kept when omitted; the new-id check runs after `model_validate` and before `store.save`, next to `_validate_tool_overrides`.
7. **Encryption corpus**, all five places, then run the guard test.
8. **Rename carry** sibling plus both call sites.
9. **`GET /api/tool-names`**, in the new router module.
10. **Tests**, then **docs**. Run the scoped files as you go and `make test-unit` once at the end.

## Edge Cases
- **A secret's name collides only by case** ("Home address" vs "home address"): a 409 (names are unique ignoring case); renaming a secret to its own name in another case is allowed.
- **PUT with `values: []`**: a 422 on `["values"]`.
- **Two pairs in one body with keys differing only by case**: 422 on the second one's key.
- **A PUT that renames key A to B while another secret owns B**: 422 on that row's key; nothing is written.
- **`__MASKED__` as a real value**: impossible to store (it is the sentinel); the docs say so.
- **A secret deleted while an agent PUT in flight adds it**: the agent PUT's new-id check can pass, then the delete scrubs the grant. Either the grant survives with a dangling id (ignored at runtime, DD2) or it is scrubbed. Both are safe. Do not add locking.
- **An MCP rename where the old normalized name is still used by another source**: leave `allowed_tools` unchanged (the sibling's rule).
- **Rotation with no secrets stored**: no-op for the corpus; existing rotation tests still pass.

## Files Affected
See Outputs.

## Citation Audit
Checked by the Flight Director on 2026-11-04 against `481546e0`:
- `api.py:141` `_read_json`, `:183-189` `_validation_detail`: verified by Architect review 2.
- `api.py:1526-1533`: the `kb_ids` preserve. Verified.
- `api.py:3784`, `:3798`: the `carry_mcp_rename` import and call. Verified.
- `db/name_repair.py:111`: the `carry_mcp_rename` call. Verified.
- `mcp/rename_references.py:43-49`: `carry_mcp_rename(source_id, old_name, new_name, *, agent_store, mcp_repo)`. Verified.
- `middleware.py:~389-410`: confined-source path scoping. Verified (comment block at :390).
- `self_configuration/constants.py:115` `SURFACE_TOOL_PREFIX`, `agent/tool_names.py:11-25`: Architect review 2.

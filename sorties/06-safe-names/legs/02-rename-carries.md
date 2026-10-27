# Leg: rename-carries

**Status**: completed
**Flight**: [Safe names](../flight.md)

## Objective
Make every rename carry what refers to the renamed row: an agent rename rewrites the connector bindings that name it, an MCP-server rename moves the per-server settings and disabled-tool entries of the agents attached to it without ever failing the request, and the knowledge-base rename's tool-name computation becomes a helper the leg-4 repair can call.

## Context
- Flight DD8 (renames carry their references), DD2 (a submitted padded name is trimmed on save, which is a rename), DD11 (leg 4's repair renames through these paths, so they must work outside an HTTP request and never raise).
- Leg 1 landed `the_one/naming.py` and the name checks on the eight routes (ground truth: the flight log's `name-rule-server` entry). In particular `update_mcp_source` and `update_knowledge_base` now trim a submitted name, so a PUT with `" foo "` renames a stored `"foo"`-padded row; this leg makes that rename carry its references.
- MCP names are not unique (`mcp_sources.name` has no UNIQUE constraint), and `AgentConfig.mcp_overrides` is keyed by source **name** inside an encrypted column, so every override change goes through `SQLiteAgentStore.load`/`save`, never a raw `UPDATE` (the `kb_rename.py` L2-D8 rule).
- `mcp__` and `kb__` are in `UNGATED_TOOL_PREFIXES` (`the_one/agent/config.py`), so `enabled_tools` never needs rewriting for either.

## Inputs
- `the_one/db/repositories.py::SQLiteAgentStore.rename` — existence check, conflict `ValueError`, one `write_transaction` updating `agents.name` and `chat_sessions.agent_name`, then `notify_sessions_changed()`.
- `the_one/db/repositories.py::connector_bindings` — parses `connectors.config` (`default_agent` + `channel_map` values), skipping a malformed row with a WARNING.
- `the_one/db/repositories.py::SQLiteAgentStore.list_by_kb` — `json_each` membership over `agents.kb_ids`, guarded for NULL/empty.
- `the_one/self_configuration/manage.py::_migrate_override_key` — the move-or-skip precedent for `mcp_overrides`.
- `the_one/interfaces/web/api.py::update_mcp_source` — 404, surface-row 409, merge, validation, `repo.update(updated)`, `forget_era(source_id)`.
- `the_one/interfaces/web/api.py::update_knowledge_base` — after `repo.update(updated)`, when `existing.name != updated.name`, computes `old_tool_name`/`new_tool_name` with `compute_tool_names([kb], agent_name="(kb-rename)")[kb_id]`, guards the agent-store acquisition, calls `rename_kb_tool_references`.
- `the_one/knowledge/kb_rename.py::rename_kb_tool_references` — the AC-12 never-raise contract this leg's MCP helper copies.
- `the_one/mcp/_tool.py::_normalize_source_name`.

## Outputs
- `SQLiteAgentStore.rename` rewrites connector bindings in its transaction.
- New `SQLiteAgentStore.list_by_mcp_source(source_id) -> list[str]`.
- New `the_one/mcp/rename_references.py::carry_mcp_rename(source_id, old_name, new_name, *, agent_store, mcp_repo) -> list[str]` (returns the agents whose carry failed), called from `update_mcp_source`.
- New helper in `the_one/knowledge/kb_rename.py`, e.g. `carry_kb_rename(existing, updated, *, get_agent_store) -> None` (or a pure `kb_rename_tool_names(existing, updated) -> tuple[str, str] | None` plus the existing call), used by `update_knowledge_base`; route behaviour unchanged.
- Tests: `tests/test_rename_carries.py` (or additions to the existing rename/KB-rename test files), all unit tier.
- `the_one/agents.md` "Naming rule" section gains "Renames carry their references"; `SQLiteAgentStore.rename`'s docstring names the connector rewrite.

## Acceptance Criteria
- [ ] Renaming agent `a` to `b` (through `POST /api/agents/a/rename` and through `SQLiteAgentStore.rename` directly) rewrites, in the same transaction as the agent row: every connector whose `config.default_agent == "a"` to `"b"`, and every `config.channel_map` value equal to `"a"` to `"b"`; connectors that do not name `a` are not written and keep their `updated_at`; a rewritten connector gets `updated_at = now_iso()` (as `ConnectorRepository.update` does) and its `config` is serialised with plain `json.dumps(config)`; other `config` keys (e.g. `enabled`, `_cache`) survive; a connector whose `config` is malformed is skipped with a WARNING and does not fail the rename; the other `config` keys and the connector's encrypted secrets are untouched (read back). Chats, rules, notes and revisions still follow, as today. A route-level test goes through `POST /api/agents/{name}/rename` (in `tests/test_agent_rename.py`, seeding connectors through `ConnectorRepository` with an encryptor).
- [ ] `SQLiteAgentStore.list_by_mcp_source(source_id)` returns the names of agents whose `mcp_source_ids` contains exactly that id (a `json_each` membership test with the same NULL/empty guard as `list_by_kb`; an id that is a substring of another id does not match).
- [ ] `carry_mcp_rename(source_id, old, new, ...)` returns at once when `old == new`. Otherwise, for each agent returned by `list_by_mcp_source(source_id)`:
  - moves `mcp_overrides[old]` to `mcp_overrides[new]` through the store; **copies** instead (keeping `[old]`) when another source in the agent's `mcp_source_ids` — **excluding `source_id` itself**, which already holds the new name because the carry runs after `repo.update`, and counting a duplicate id once — still has the raw name `old` (overrides compare raw names; prefixes compare normalised names); skips with a log line when `[new]` already exists (never clobbers); leaves an agent with no `[old]` entry unsaved;
  - when `normalize(old) != normalize(new)`, rewrites each `disabled_tools` entry starting `mcp__{normalize(old)}__` to the same entry with `mcp__{normalize(new)}__`; or, when another attached source still normalises to `normalize(old)`, **adds** the rewritten entries and keeps the old ones; duplicates collapsed; an agent with nothing to change is neither loaded-and-saved nor touched beyond its read (tested with the tracked-load pattern at `tests/test_db_api.py:750`);
  - never raises: the enumeration and each agent's load/modify/save are wrapped, each failure logs a WARNING naming the source and the agent, and the rest continue; agents not attached to `source_id` are never loaded. The return value (agents whose carry failed) is for tests and the leg-4 repair; `update_mcp_source` ignores it, as `update_knowledge_base` ignores `rename_kb_tool_references`'.
- [ ] `update_mcp_source` calls `carry_mcp_rename` after `repo.update(updated)` only when `existing.name != updated.name`, with the agent-store acquisition guarded like `update_knowledge_base`'s; a PUT whose carry fails for one agent (set up by saving the agent through the store, then `UPDATE agents SET mcp_overrides = 'not-json-or-token' WHERE name = ?`, which makes `store.load` raise; `list_by_mcp_source` does not decrypt, so enumeration still succeeds) still returns 200 with the renamed source, carries the other agents, and logs a WARNING.
- [ ] The KB tool-name computation used by `update_knowledge_base` lives in one helper in `the_one/knowledge/kb_rename.py` that the route calls; the existing KB rename tests pass unchanged (no behaviour change), which pins two contracts: the route passes the store getter resolved **at call time** inside the handler (`get_agent_store=_agent_store` in the body, never a default argument or module-level binding), because `tests/test_db_api.py:861-905` monkeypatches `api_module._agent_store` and asserts a WARNING containing the `kb_id` and "acquire" (keep that message text); and the "slug unchanged" early return stays inside the helper **before** any store acquisition, because `tests/test_db_api.py:750-760` proves the no-change and same-slug cases touch no agent; and the helper can be called with a store and two `KnowledgeBase` objects outside a request.
- [ ] Docs: `the_one/agents.md` "Naming rule" section has a "Renames carry their references" paragraph (agent → connectors; MCP → attached agents' overrides and disabled tools, copy-not-move for shared names, never raises; KB → unchanged, via the helper); `SQLiteAgentStore.rename`'s docstring names the connector rewrite.
- [ ] `make test-unit` passes (skip count as at baseline); ruff check and format pass.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_rename_carries.py -x --timeout 30` (and any existing file the leg extends, e.g. `tests/test_agent_rename.py`, the KB-rename tests found by `grep -rln rename_kb_tool_references tests/`).
- `make test-unit` once at leg end.
- `.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/`

## Implementation Guidance

1. **Agent rename → connectors.** Factor `connector_bindings`' per-row parsing into a small private function (e.g. `_parse_connector_binding_config(raw) -> dict`) that both `connector_bindings` and the rename use, raising only `(ValueError, TypeError, AttributeError)` so malformed-row handling (the existing WARNING text and `exc_info`) is identical; in the rename, a malformed row is `continue`d before any write. A connector write error inside the transaction rolls back the agent rename, which is correct. Inside `SQLiteAgentStore.rename`'s `write_transaction`, after the two existing `UPDATE`s: `SELECT id, config FROM connectors`; for each row that parses and names `old_name`, build the new config (replace `default_agent` if equal; map each `channel_map` value) and `UPDATE connectors SET config = ? WHERE id = ?` (also bump `updated_at` if the table has it and other connector writes bump it — check `ConnectorRepository.update`). Serialise with the same `json.dumps` settings `ConnectorRepository` uses. Confirm by reading `the_one/connectors/` that no live listener caches `default_agent`/`channel_map` in memory across messages (the review found inbound reads the connector fresh per message); if one does, record it in the flight log and raise it rather than adding a cache invalidation here.

2. **`list_by_mcp_source`.** Mirror `list_by_kb` exactly over `mcp_source_ids`.

3. **`carry_mcp_rename`.** New module `the_one/mcp/rename_references.py`, docstring modelled on `kb_rename.py` (ordering forced by `write_transaction`, never a raw `UPDATE`, never raises). For the "another attached source still has the name" checks, read each attached agent's `mcp_source_ids` and look the other ids up through `mcp_repo` (`MCPSourceRepository.get`; a missing id is ignored). Use `the_one.mcp._tool._normalize_source_name` for prefixes (import the existing function; do not copy the regex).

4. **`update_mcp_source`.** After `repo.update(updated)` and `forget_era(source_id)`, `if existing.name != updated.name:` acquire the agent store in a try/except mirroring `update_knowledge_base` and call `carry_mcp_rename`. Surface rows never reach this point (their PUT is refused earlier with 409).

5. **KB helper.** Move the inline `old_tool_name`/`new_tool_name` computation and the "slug unchanged" early return into `the_one/knowledge/kb_rename.py` so the route reads: `if existing.name != updated.name: await carry_kb_rename(existing, updated, get_agent_store=_agent_store)` (or the equivalent shape you choose), with the store-acquisition guard inside the helper. Keep the existing comments' substance (DD-17, L2-D9) next to the code they explain.

6. **Tests.** Seed databases from `tests/_schema_template.py`; build an encryptor the way neighbouring store tests do. The undecryptable-agent case: write an agent row whose `mcp_overrides` column holds ciphertext from a different key (or garbage), attached to the source.

## Edge Cases
- **Another attached source already named `new`** (raw): the override move skips because `[new]` exists (no clobber). **Another attached source already normalising to `normalize(new)`**: rewriting `mcp__old__x` to `mcp__new__x` would also disable that source's same-named tool; accepted, because two attached sources normalising to one prefix are already a prefix-collision error in the MCP layer (`the_one/mcp/errors.py`); record it in the flight log.
- **Prefix ambiguity**: `mcp__foo__` also prefixes a source named `foo__bar`'s tools (`_normalize_source_name` keeps `_`); a `startswith` rewrite can touch them. Known limit, recorded in the flight log and `the_one/agents.md`.
- **An agent attached to the source twice** (duplicate id in `mcp_source_ids`): treat as attached once.
- **`old` override present and `[new]` present**: skip with a log line, keep both (no clobber).
- **A rename that changes only case or padding** (`"Foo"` → `"foo"`): overrides move (the key differs); the normalised prefix may or may not change — follow the rule as written.
- **An agent rename where a connector names the agent in both `default_agent` and `channel_map`**: one write per connector.
- **The self-configuration surface row**: never renamed through `update_mcp_source` (409); its references are `reconcile_on_startup`'s job.

## Files Affected
- `the_one/db/repositories.py` - `SQLiteAgentStore.rename`, `list_by_mcp_source`, the shared connector-config parser
- `the_one/mcp/rename_references.py` - new
- `the_one/knowledge/kb_rename.py` - the KB carry helper
- `the_one/interfaces/web/api.py` - `update_mcp_source`, `update_knowledge_base`
- `tests/test_rename_carries.py` - new (or the extended existing files)
- `the_one/agents.md` - "Renames carry their references"

---

## Post-Completion

The Developer marks the leg `landed`, records changes and verification in the flight log, and signals `[LAND:leg]`. Nothing is committed.

## Citation Audit
Checked against `2e82aaa` in the worktree: `connector_bindings` (parsing and malformed-row WARNING), `list_by_kb` (json_each with the NULL/empty guard), `_migrate_override_key` (move, skip if `[new]` exists, save through the store), `update_knowledge_base`'s post-commit rename block (inline `compute_tool_names`, store-acquisition guard, `rename_kb_tool_references`), `rename_kb_tool_references` (AC-12 contract), `update_mcp_source`'s tail (`repo.update(updated)`, `forget_era(source_id)`) — verified. Leg 1 edits `update_mcp_source` and `update_knowledge_base`; re-read both after leg 1 lands.

Design review (Developer, 2026-10-26): approve with changes; adopted — the two KB route-test contracts, the undecryptable-agent recipe, `updated_at` and serialisation on rewritten connectors, excluding the renamed source from the shared-name check, raw-vs-normalised comparison, the `old == new` early return, the return value ignored by the route, two known limits recorded.

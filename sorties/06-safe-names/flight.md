# Sortie: Safe names

**Status**: completed

## Charter

### Outcome
Agents, model providers, knowledge bases and MCP servers follow one naming rule, enforced by the server and shown on each form's name field, and an agent whose existing name breaks the rule is repaired so it can be opened, edited, renamed and deleted again.

### Why Now
The operator hit it on the macOS build (2026-10-26): an agent created with a `/` in its name showed "Couldn't load this agent's current configuration…" and could not be edited, renamed or deleted. Every `/api/agents/{name}…` route (29) 404s for it, because Starlette decodes `%2F` before routing. The only way out today is hand-editing the database.

### Success Criteria
- [x] Creating, editing or renaming an agent, model provider, knowledge base or MCP server with a name that breaks the rule is refused with a plain sentence on the name field, and nothing is saved, including through the API directly.
- [x] After upgrade, every existing row of the four with a rule-breaking name has a safe, unique name; an agent keeps its chats, rules, notes, revisions and connector assignments; each opens, saves, renames and deletes normally.
- [x] When an agent's configuration fails to load, the message appears where the operator will see it, explains why Save is disabled, and Save stays disabled.

### Constraints
- Agents stay addressed by name in their URLs (no route redesign).
- The repair only renames; it never deletes data.
- Messages are one plain sentence.
- Connectors are out of scope (their names are display-only).

---

## Pre-Flight

### Objective
Add one shared name checker and call it on every write path that sets a name on an agent, model provider, knowledge base or MCP server, so a rule-breaking name is refused with a 422 whose message the form shows on its name field. Close the neighbouring name holes the operator chose to fold in: creating an agent with an existing agent's name no longer overwrites it, an agent rename carries its connector assignments, and an MCP-server rename carries the per-server settings and disabled-tool entries of the agents attached to it. Make the agent editor's load failure visible: an error toast plus a lasting line in the editor header that says why Save is off. Then repair, once per startup and idempotently, every stored row whose name breaks the rule, through those same rename paths, so nothing attached to a row is lost.

### Open Questions
- [x] Load-failure treatment? → error toast plus a lasting header line; no Retry button (operator, 2026-10-26; DD10)
- [x] Related holes in or out? → create-can't-overwrite, rename keeps connectors, MCP rename keeps overrides: in (operator, 2026-10-26; DD7, DD8). Reserve `default`: chosen, then withdrawn after review (next item).
- [x] Reserve the agent name `default`? → **no**. A stored `default` is loaded ahead of the synthesized default (`AgentFactory._load_config`), so it configures every chat with no agent (connector chats with no binding, REST `/api/chat`), with its rules and notes; tests rely on it. `default` stays a legal name, is never repaired, and the behaviour is documented (operator, 2026-10-26, after Architect review 1; DD6)
- [x] HAT leg? → no; unit and browser tests (operator, 2026-10-26)
- [x] Worktree or main checkout? → worktree (operator, 2026-10-26; Prerequisites)
- [x] Replacement character for the repair? → a space (operator's suggestion; DD12)
- [x] Do `chat_sessions` rows store `agent_name = 'default'` for the synthesized default? → no: web/WS chats with the synthesized default store NULL (`app.py` ~1529); a literal `'default'` comes only from a stored `default` (connector bindings offer stored agents only) or a direct `POST /api/chat/sessions` (Architect review 1). Moot now that `default` is not repaired.
- [x] Stored names that are only padded or over 64 characters? → padded: not repaired, trimmed on their next save (DD2); over 64: repaired by truncation (DD12), so every stored name passes the checker after the repair and an edit of an unrelated field never 422s on a name the operator did not touch.

### Design Decisions

**DD1. The rule.** A name is valid when, after trimming leading and trailing whitespace, it is non-empty, at most 64 characters (code points), and contains no `/`, no `\`, no control character (Unicode category `Cc`) and no bidirectional embedding, override or isolate control (U+202A-U+202E, U+2066-U+2069), and is not exactly `.` or `..`.
- Rationale: `/` breaks every agent route (Starlette decodes `%2F` before matching; reproduced with a minimal FastAPI app: `my%2Fagent` → 404, `my%20agent`, `caf%C3%A9`, `a%3Fb` → 200). `.`/`..` are dropped by the browser's URL normaliser before the request leaves. `\` and control characters have no legitimate use in a display name. The bidi controls let a name display as something it is not. 64 matches the tool-name ceiling the KB and MCP normalisers already budget against. `Cc` matches `normalize_note_text`'s choice.
- Trade-off: no allow-list; letters, spaces, punctuation and emoji (including ZWJ sequences, which are `Cf` but not bidi controls) stay legal.

**DD2. Trim, don't reject, surrounding whitespace.** `check_name` returns the trimmed name and every write path stores that value. A stored name that differs from its trimmed form only by surrounding whitespace is not repaired; its next save through an edit route trims it, which is a rename and goes through DD8.
- Rationale: rejecting `" foo"` would be hostile, and repairing every padded name would churn data that breaks nothing.
- Trade-off: a padded MCP-server or KB name changes on its next save; DD8 (leg 2) and the existing KB rename path carry the references. For agents, "next save" means the editor's path only: the editor trims and renames through `/rename` (`agent-editor-controller.js` save path), while an API `PUT /api/agents/{name}` keeps the path's name untrimmed (the PUT forces `data["name"] = name`).

**DD3. One leaf checker, applied at write boundaries, never on the models.** A new leaf module (stdlib only), `the_one/naming.py`, exposes `check_name(value) -> str` (returns the trimmed name, raises `NameRuleError` carrying one message) and, from leg 3, `repair_name(value, *, kind, taken) -> str` (DD12). The pydantic models stay `name: str`.
- Rationale: stored rows load through the same models (`SQLiteAgentStore.load` → `AgentConfig`), so a model validator would make an existing bad row fail to load, breaking `GET /api/agents` and the repair itself. The `rename_agent` docstring expected future rules to live on `AgentConfig`; that comment is updated to point at the checker.
- Trade-off: a future write path must remember to call the checker; the structural route test (DD4) catches a route that does not.

**DD4. The write paths, in order.** Eight routes call `check_name`: `create_agent`, `rename_agent`, and create and update for providers, knowledge bases and MCP sources. `update_agent` needs no call (the PUT forces `data["name"] = name` from the path, and the row already exists). In each route the order is: `check_name` first, write the trimmed value back, **then** every existing name comparison or guard: the MCP reserved-name check (`_reject_reserved_surface_name`, so `" self-configuration "` cannot slip past an exact match), the DD7 exists check, and the KB `existing.name != updated.name` rename comparison. On the three PUT routes (providers, KBs, MCP), which merge `existing.model_dump() | data` and whose body may omit `name`, the check runs on the **merged** name and the trimmed value is written back into the merged dict before `model_validate` and the guards. `migrate_json_to_sqlite` calls `check_name` only to decide whether to skip a legacy JSON file (one WARNING line on failure); a file that passes is stored exactly as today, body unchanged, so its stem keeps matching `exists(stem)` and an operator's later edits are never re-upserted over (the loop runs on every start and never deletes the JSON). Exempt, with reasons recorded in `the_one/agents.md`: self-configuration `enable` and `reconcile_on_startup` (a constant valid name), the self-configuration write tools and revision restore (they never set a name), and the evals harness (developer tool). **Route classification test:** a unit test lists every POST/PUT route under `/agents`, `/providers`, `/knowledge-bases` and `/mcp-sources` from `router.routes` and requires each to be in a `CHECKED` set (each asserted to refuse `a/b` with nothing stored) or an `EXEMPT` set with a one-line reason (e.g. `/agents/{name}/rules`, `/providers/{id}/test`); an unclassified route fails the test, so a new route cannot slip past. (Every route takes `request: Request` and reads raw JSON, so "accepts a name" cannot be inferred from the route signature.)
- Rationale: Architect review 1 confirmed the route list is complete and found the JSON-migration loop and the trim/guard ordering holes.
- Trade-off: none.

**DD5. The 422 shape matches pydantic's, so `App.api.fieldErrors` maps it.** A refusal is `HTTPException(422, detail=[{"type": "name_rule", "loc": ["name"], "msg": "<one sentence>"}])`, **including from the rename route** (`loc: ["name"]`, not `new_name`, because `fieldErrors` matches `loc` segments exactly). The rename route's existing string details ("new_name is required", "must differ", the 409 "Agent already exists") become the same list shape with `loc: ["name"]`. Messages, one plain sentence each: "A name can't contain / or \\.", "A name can't be . or ..", "A name can't contain control characters.", "A name can be at most 64 characters.", "Enter a name.", "An agent with this name already exists."
- Rationale: `_validation_detail` already returns `[{type, loc, msg, url}]` with `loc ["name"]`, and the MCP editor already maps it with `App.api.fieldErrors`. One shape, one client path.
- Trade-off: the rename 409's shape changes; its callers are the agent editor (leg 2) and tests, updated together.

**DD6. `default` stays a legal agent name.** No reservation, no repair. `the_one/agents.md`'s naming section records that a stored agent named `default` is loaded ahead of the synthesized default (`AgentFactory._load_config`) and therefore configures every chat with no agent, with its rules and notes; the browser's `start_session` refusal of `"default"` is unchanged.
- Rationale: operator decision after Architect review 1; reserving or renaming it would silently change which configuration no-agent chats run on.
- Trade-off: the name stays special in a way the UI does not explain; documented, not changed.

**DD7. Creating an agent with an existing name is a 409.** `create_agent` checks `store.exists(trimmed_name)` (after DD4's `check_name`) before `store.save` and raises 409 with the DD5 list detail.
- Rationale: `SQLiteAgentStore.save` is an upsert (`ON CONFLICT(name) DO UPDATE`), so today a create silently replaces the existing agent's configuration. Rename already returns 409 for the same condition.
- Trade-off: a check-then-save race between two creates of one name (one operator on one machine); the second still upserts as today. Accepted.

**DD8. Renames carry their references (leg 2, server).**
- **Agent rename** (`SQLiteAgentStore.rename`) also rewrites, in the same transaction, every connector whose `config.default_agent` equals the old name and every `config.channel_map` value equal to it (`connectors.config` is plaintext JSON; inbound reads the connector fresh per message). Reuse the parsing of `connector_bindings` (`repositories.py`, which `agent_names_in_use` unions): malformed rows are skipped with a log line. Chats (manual), rules/notes/revisions (ON UPDATE CASCADE) and the self-configuration surface marker (`cascade_rename`, called by the route) already follow.
- **MCP-server rename**: a new helper (in `the_one/mcp/`, e.g. `rename_references.py::carry_mcp_rename(source_id, old, new, *, agent_store)`) called by `update_mcp_source` after the source row commits when the stored name changes. It touches **only agents whose `mcp_source_ids` contain this source's id**. For each: move `mcp_overrides[old]` to `[new]` through the store (encrypted column), **copying instead of moving** when another source the agent is attached to still has the name `old` (MCP names are not unique), and skipping with a log line when `[new]` already exists (the `_migrate_override_key` behaviour); and rewrite `disabled_tools` entries with the prefix `mcp__{normalize(old)}__` to `mcp__{normalize(new)}__` when the normalised prefix changed, or, when another attached source still normalises to the old prefix, **add** the new-prefix entries and keep the old ones (mirroring the override copy). **It never raises**, on the KB helper's AC-12 contract (`kb_rename.py`): a per-agent try/except with a WARNING (one agent whose overrides fail to decrypt is skipped, the rest are carried), a guarded enumeration, and a guarded store acquisition in the route, so a failure after the source commit never turns the PUT into a 500. Tested, including the undecryptable-agent case.
- **Knowledge-base rename**: the old/new tool-name computation that is inline in the KB PUT route is pulled out into one helper (beside `rename_kb_tool_references` in `the_one/knowledge/kb_rename.py`) that both the route and the leg-3 repair call. Behaviour unchanged.
- Rationale: the repair (DD11) renames rows and must never lose data; it can only keep that promise through rename paths that carry references, and the operator's renames have the same gaps today. Doing this in leg 2, before the forms and the repair, also covers DD2's trim-on-save rename (one commit lands the whole flight, so no state between legs ships).
- Trade-off: the MCP re-key runs after the source commit, not in its transaction (encrypted columns go through the store); a crash between them leaves an orphaned override key, the exposure the KB path accepts today. Logged.

**DD9. Every form shows the server's message on its name field; no client-side copy of the rule (leg 3).** The agent General tab returns its `studio-name` `ui.field` handle (today `general-tab.js` keeps only `.el`), and the agent editor's create/save/rename error path moves from `extractApiError` string-joining to `App.api.fetchJson` + `App.api.fieldErrors(err, ['name'])`: the name message on the field, the rest through `shell.setError`. The provider editor (`pf-name`), the KB create form (`kb-create-name-input`) and the KB detail editor do the same; the MCP editor already does. A name-field error clears on the next input in that field, on Cancel, and when the editor is patched to another agent or item. After an agent rename the client invalidates the `connectors` store collection (the server now rewrote their bindings) as well as what it invalidates today. The existing client-side "required" checks stay.
- Rationale: the server is the gate, and one rule in one place cannot drift.
- Trade-off: the message appears on Save, not while typing.

**DD10. The load failure: an error toast plus a lasting header line (leg 3).** When `doSelect`'s fresh-agent fetch fails, the editor calls `App.ui.flash("Couldn't load this agent's settings.", {error: true})` with the default `document.body` container (once per failed load, not per re-render), and shows a lasting line in the editor shell's error slot: "Save is off because this agent's settings didn't load. Reopen the agent to try again." Follow `areas/admin/knowledge-settings-page.js`'s precedent: set `shell.errorEl.textContent` directly (not `editorShell.setError`, which clears and rewrites on a token and would flicker the line on every patch) and add the `agent-load-error` testid to it only while the load has failed (remove it when cleared), so the existing visibility assertions keep their meaning. The header line carries no `role=alert` (the toast is the announcement). `patch` re-applies the line, as it re-applies `setLoadError` today. In the controller's save path, the `_selectedAgentLoaded === false` check moves ahead of `refuseBlockingOverride_` (`agent-editor-controller.js`), so a script-driven Save on a failed load cannot replace the header line while the testid stays on it. The `div.agent-load-error`, its `studio.css` rule and `LOAD_ERROR_TEXT` are removed. Save stays disabled exactly as today (`_selectedAgentLoaded === false`).
- Rationale: the operator found the inline block awkward. The header line sits beside the disabled Save, so its reason is always visible; the toast catches the eye. Nothing clears `shell.errorEl` while Save is disabled (every `setEditorError_` call is on a Save path; `apply()` does not touch it — Architect review 1). The body container sidesteps the disconnected-container defect Mission 31 Flight 5's debrief found in `App.ui.flash`.
- Trade-off: `tests/browser/test_flow_agent_editor_frame.py:62` pins the frame's first children as `["editor-header", "agent-load-error"]`; that pin is changed deliberately, and `test_flow_studio_knowledge_attach.py:691` follows the testid. No control-library guard impact (`.agent-load-error` is an area class; studio code already calls `App.ui.flash`).

**DD11. The repair runs at startup, as Python, after the key reconcile, and can never stop the app starting (leg 4).** A new `the_one/db/name_repair.py::repair_unsafe_names(...)` runs in the web app's lifespan after `reconcile_pending_key` and `migrate_json_to_sqlite` and before `manage.reconcile_on_startup`. It scans names with a raw `SELECT id/name FROM <table>` on each of the four tables (never through `store.list`/`load`, which decrypt and would fail the scan on one bad row) and, for each name where `check_name` raises, computes a new name (DD12) and renames through the DD8 paths: `SQLiteAgentStore.rename` plus `cascade_rename` for agents; the KB rename plus the DD8 tool-reference helper for knowledge bases; the MCP row's own `repo.update` followed by `carry_mcp_rename` for MCP sources; a plain `UPDATE` for providers (agents reference providers by id). It **skips self-configuration surface rows** (`is_surface_row`): a legacy surface row is named `"self-configuration (<agent>)"` and can carry a `/` from its agent's name, and `reconcile_on_startup`, which runs next, owns renaming those. Each rename logs one WARNING naming the kind, the old and the new name. Each row's rename is in its own try/except (a WARNING, then the next row), and the whole pass is wrapped the same way, matching the connector and watch startup pattern in `app.py`. It is idempotent (a clean database does nothing) and records nothing in `schema_version`. It is not called from inside another transaction (`write_transaction` rejects same-task re-entry).
- Rationale: `agents.mcp_overrides` is Fernet-encrypted and `ensure_schema` has no encryptor, so a `schema.py` migration cannot re-key it; the lifespan already hosts this kind of repair. One agent whose overrides fail to decrypt must not keep the app from starting.
- Trade-off: four small `SELECT`s on every start; a row that fails to repair stays broken until the next start, with a WARNING.

**DD12. Repair naming.** `repair_name` replaces each `/` and `\` with a space, deletes control and bidi-control characters, collapses runs of whitespace to one space and trims; truncates to 64 characters and trims again; a name that is then empty, `.` or `..` becomes `Renamed agent` / `Renamed provider` / `Renamed knowledge base` / `Renamed MCP server`. If the result collides with an existing name of the same kind (`taken`, including names assigned earlier in the same pass), it appends ` 2`, ` 3`, … (truncating the base so the result stays within 64). Collisions are compared case-insensitively (`casefold`), so a repaired `Foo 2` is never created beside an existing `foo 2`, although the agents primary key itself is case-sensitive.
- Rationale: the operator suggested a space. Both tool-name normalisers map every character outside `[a-zA-Z0-9_-]` to `_`, and a space and a `/` both map to `_`, so a repaired KB or MCP name keeps its derived tool name when only `/`/`\` change. Numbering all four avoids creating look-alike duplicates.
- Trade-off: collapsing whitespace or truncating can change a derived tool name; DD8's rename paths carry `disabled_tools`.

**DD13. The boxed scratch directory slugs the agent name.** `tools/sessions.py` builds `data_dir / "boxes" / f"{agent_name}-{sid}-{uuid}"` from the raw name. Leg 1 replaces the agent-name part with a slug (characters outside `[A-Za-z0-9_-]` → `_`, capped), so no name can escape `boxes/` or hit Windows-invalid characters (`<>:"|?*`, a trailing dot or space, device names), whatever the rule allows.
- Rationale: the rule still allows characters Windows refuses in paths, and the Windows `PassthroughSandbox` still creates the scratch dir (Architect review 1).
- Trade-off: the directory name no longer shows the agent name verbatim; it is ephemeral.

### Citation Audit

Verified against the working tree at `2e82aaa` (Architect review 1 re-checked about 12 rows and both previously unverified rows):

| Citation | Status |
|---|---|
| `the_one/db/repositories.py::SQLiteAgentStore.save` — upsert via `ON CONFLICT(name) DO UPDATE` (DD7) | verified |
| `the_one/interfaces/web/api.py::create_agent` — `AgentConfig.model_validate`, then guards, then `store.save`, with no exists check (DD7) | verified |
| `the_one/db/repositories.py::SQLiteAgentStore.rename` — existence check, `ValueError` on conflict, one `write_transaction` updating `agents` and `chat_sessions` only (DD8, DD11) | verified |
| `the_one/db/schema.py` — `agent_rules`/`agent_notes`/`agent_revisions` FKs declare `ON UPDATE CASCADE` (DD8) | verified |
| `the_one/db/repositories.py::connector_bindings` — connector bindings are `config.default_agent` plus `config.channel_map` values, plaintext `config` column, malformed rows skipped; `agent_names_in_use` unions it (DD8) | verified (Architect review 2) |
| `the_one/knowledge/kb_rename.py` AC-12 never-raise contract; KB PUT's guarded store acquisition (DD8) | verified (Architect review 2) |
| `the_one/db/migration.py::migrate_json_to_sqlite` — skips by stem, saves the body's name (DD4) | verified (Architect review 2) |
| `the_one/self_configuration/manage.py::_migrate_override_key`, `::cascade_rename`, `::reconcile_on_startup` exist (DD8, DD11) | verified |
| `the_one/interfaces/web/app.py` lifespan order — `reconcile_pending_key` (289), `migrate_json_to_sqlite` (293), `reconcile_on_startup` (304) (DD11) | verified |
| `the_one/db/migration.py::migrate_json_to_sqlite` — runs every start, skips only an existing stem, never removes the JSON (DD4) | verified (Architect review 1) |
| `the_one/interfaces/web/api.py::_validation_detail` — `e.errors(include_context=False, include_input=False)` (DD5) | verified |
| `the_one/interfaces/web/static/js/api.js` `App.api.fieldErrors` — matches `loc` segments exactly (DD5) | verified (Architect review 1) |
| `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — calls `App.api.fieldErrors(err, SERVER_FIELDS)` (DD9) | verified |
| `the_one/interfaces/web/api.py::_reject_reserved_surface_name` — exact-match reserved MCP name (DD4) | verified (Architect review 1) |
| `the_one/knowledge/kb_rename.py::rename_kb_tool_references` exists and takes a store (DD8) | verified |
| `the_one/mcp/_tool.py::_normalize_source_name` — `re.sub(r"[^a-zA-Z0-9_-]", "_", name)` (DD12) | verified |
| `the_one/agent/factory.py::AgentFactory._load_config` — a stored agent of that name first, else the synthesized `default` (DD6) | verified |
| `the_one/tools/sessions.py` — boxed scratch dir from the raw agent name (DD13) | verified |
| `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — `loadErrorEl` after `shell.el`, before the tab list; `patch` re-applies `setLoadError` (DD10) | verified |
| `the_one/interfaces/web/static/js/ui/editor.js` — `editorShell` exposes `errorEl`; `apply()` does not touch it (DD10) | verified (Architect review 1) |
| `the_one/interfaces/web/static/js/areas/admin/knowledge-settings-page.js` — load error on `shell.errorEl` with a testid added and removed (DD10) | verified (Architect review 1) |
| `the_one/interfaces/web/static/js/ui/feedback.js::App.ui.flash` — default container `document.body`, `error` → `role=alert`, 5 s dwell (DD10) | verified |
| `the_one/interfaces/web/static/js/areas/studio/general-tab.js` — `studio-name` built with `ui.field(...).el`, handle discarded (DD9) | verified (Architect review 1) |
| `tests/browser/test_flow_agent_editor_frame.py:62` — asserts `kids[:2] == ["editor-header", "agent-load-error"]` (DD10) | verified |

### Prerequisites
- [x] A worktree for the sortie: `.claude/worktrees/sortie-safe-names` on branch `sortie/06-safe-names` from `main`, created at execution start (operator's choice; Mission 31 Flight 6 may start in the main checkout and also touches agent-editor and flash code, so coordinate at merge).
- [x] The repo venv in the worktree installs (`pip install -e ".[all-llms,dev]"`) and `make test-unit` passes at the base commit there; record the skip count (12 expected, 15 under `THE_ONE_TEST_NETNS=1`). Re-verify at each leg's start.
- [x] Browser lanes run in the worktree with `THE_ONE_TEST_NETNS=1` (this WSL host), at most 3 lanes at a time counting any other workstream's lanes.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified (at execution start, in the worktree)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
**Leg 1 (`name-rule-server`, unit tier).** Add `the_one/naming.py` (`check_name`, `NameRuleError`, the message constants). Call it on the eight routes with DD4's ordering (the merged name on the three PUTs) and in `migrate_json_to_sqlite` (skip-only), raising DD5's 422; make the rename route's details list-shaped; add DD7's 409; DD13's scratch-dir slug. Sweep existing tests for names the rule now refuses (e.g. `tests/test_db_api.py:819` PUTs a KB named `"My/Notes"`; `tests/test_mcp_cache_cleanup.py` has a `"…/…"` name literal; grep API-creating tests for `/`, `\`, names over 64 characters) and for duplicate `POST /api/agents` creates that relied on the upsert. Tests: the checker (every rule, the trim, the 64 boundary, bidi controls refused, a ZWJ emoji allowed, `default` allowed); the route classification test (`CHECKED`/`EXEMPT`, each `CHECKED` route refuses `a/b` with `loc ["name"]` and stores nothing); a PUT that omits `name` still succeeds; a duplicate agent create → 409 with the first agent unchanged; `" self-configuration "` refused as reserved after the trim; the JSON migration skips a bad-name file with a WARNING and stores a good one unchanged; the scratch-dir slug. Docs: `the_one/agents.md` "Naming rule" section (the rule, the eight routes and the exempt paths, why not on the models, `default`'s role, the scratch-dir slug) and the `rename_agent` docstring.

**Leg 2 (`rename-carries`, unit tier).** DD8: the agent rename's connector rewrite in `SQLiteAgentStore.rename` (reusing `connector_bindings`' parsing); `carry_mcp_rename` with the never-raise contract, called from `update_mcp_source`; the KB tool-name helper pulled out of the KB PUT route. Tests: an agent rename moves connector `default_agent` and `channel_map` values and skips a malformed connector row; an MCP rename moves overrides only for attached agents, copies when another attached source keeps the old name, rewrites (or adds) `disabled_tools` prefixes, skips an undecryptable agent with a WARNING while carrying the rest, and the PUT still returns 200; the KB rename behaviour is unchanged through the helper. Docs: the "Naming rule" section gains "renames carry their references"; the `SQLiteAgentStore.rename` docstring names the connector rewrite.

**Leg 3 (`name-rule-forms`, browser lanes).** DD9 and DD10: the agent General tab's name-field handle, the agent editor's error path on `fetchJson` + `fieldErrors`, the provider editor and both KB forms likewise, the clear-on-input/Cancel/patch rule, the `connectors` invalidation after rename, the load-failure toast and header line (direct `errorEl.textContent`, the load check ahead of `refuseBlockingOverride_`), and removal of the old block. Tests: one browser test per editor that an `a/b` name shows the message on the name field and nothing is saved (agents, providers, knowledge, mcp lanes; the MCP editor gets one regression test only, as it already works); the agent rename 409 on the name field; the frame test updated for DD10 plus a test that a failed fresh-agent fetch shows the toast and the header line, with Save disabled; `test_flow_studio_knowledge_attach.py` updated if it relies on the old element. Docs: `docs/ui-testid-registry.md` if the testid's element changes; a CLAUDE.md line only if a convention changed.

**Leg 4 (`name-repair`, unit tier).** Add `repair_name` (DD12) and `the_one/db/name_repair.py::repair_unsafe_names` (DD11) wired into the lifespan. Tests (databases from `tests/_schema_template.py`): `repair_name` cases (separators, control and bidi characters, collapse, truncate-then-trim, empty/`.`/`..` → "Renamed …", case-insensitive numbering against `taken` and within the pass, `default` untouched); a repair test seeding one bad row of each kind (an agent with chats, a rule, a note, a revision and a connector binding; an MCP server with an attached agent's override and a disabled tool; a KB with a disabled tool; a provider), running the repair and asserting the new names, every reference followed, the WARNING lines and a second run doing nothing; a legacy self-configuration surface row with a `/` is left for `reconcile_on_startup`; a row whose rename raises (an injected raise from the store) is skipped with a WARNING and the rest are repaired; an MCP repair whose attached agent cannot be decrypted still renames the source (leg 2's contract); a lifespan-level test that the app starts on a seeded bad database and `GET /api/agents/{repaired}` returns 200. Docs: the "Naming rule" section gains the repair.

### Checkpoints
- [x] Leg 1: `a/b` is refused on all eight routes (and the route classification test passes); a duplicate agent create is 409; `make test-unit` and lint pass.
- [x] Leg 2: renames carry connectors, MCP overrides and KB tool references, and an MCP rename never 500s after its commit; `make test-unit` passes.
- [x] Leg 3: the message shows on the name field in all four editors; the load failure shows the toast and the header line with Save disabled; the agents, agent-tabs, providers, knowledge and mcp lanes pass.
- [x] Leg 4: a seeded bad database starts clean, every reference attached, a second start changes nothing; `make test-unit` passes.
- [x] Landing: the full `make gate` (unit, then browser, `THE_ONE_TEST_NETNS=1`, `THE_ONE_REQUIRE_WEBKIT=1`) and lint once before the PR.

### Adaptation Criteria

**Divert if**:
- A write path exists that sets a name and cannot call the checker without a structural change.
- The repair cannot carry a reference without touching a table or file this spec does not name.
- Carrying an MCP rename needs a change to how `mcp_overrides` is keyed (by id rather than name); that is a separate design, raised, not absorbed.

**Acceptable variations**:
- Message wording polish within the one-sentence rule.
- Module locations and helper names.
- Retiring the `agent-load-error` testid instead of moving it, recorded in the registry.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `name-rule-server` - The shared checker on the eight write routes and the JSON import; list-shaped 422s; create-can't-overwrite; the scratch-dir slug.
- [x] `rename-carries` - Agent renames carry connector bindings; MCP renames carry attached agents' overrides and disabled tools without ever raising; the KB tool-name helper.
- [x] `name-rule-forms` - The server's message on each form's name field; the load failure as a toast plus a header line.
- [x] `name-repair` - The idempotent, never-blocking startup repair of every stored rule-breaking name, through the leg 2 rename paths.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- Criterion 1: the eight route tests and the route walk (`a/b` → 422, nothing stored; duplicate create → 409) and the four editor browser tests (message on the name field).
- Criterion 2: the repair unit test on a seeded database with one bad row of each kind and every reference type, plus the lifespan test (`GET /api/agents/{repaired}` → 200 after startup). The operator can confirm on the macOS build by upgrading over a stuck agent.
- Criterion 3: the browser test that forces the fresh-agent fetch to fail and asserts the toast, the header line and the disabled Save.

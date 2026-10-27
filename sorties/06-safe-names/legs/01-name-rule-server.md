# Leg: name-rule-server

**Status**: completed
**Flight**: [Safe names](../flight.md)

## Objective
Refuse a rule-breaking name on every API path that sets the name of an agent, model provider, knowledge base or MCP server, with a list-shaped 422 on `loc ["name"]`; make a duplicate agent create a 409 instead of an overwrite; stop the legacy JSON import from re-importing a bad name; and slug the agent name in the boxed scratch directory.

## Context
- Flight DD1 (the rule), DD2 (trim, don't reject), DD3 (leaf checker at write boundaries, never on the models), DD4 (the eight routes, the order, the JSON import, the exempt paths, the route classification test), DD5 (422 shape and messages), DD6 (`default` stays legal), DD7 (duplicate create → 409), DD13 (scratch-dir slug).
- Leg 2 (`rename-carries`) adds the reference carries for agent, MCP and KB renames; this leg must not change what a rename carries. Leg 3 rewires the forms; this leg changes only server responses. Leg 4 adds `repair_name` to the same module.
- No prior legs. Baseline: `make test-unit` at `2e82aaa` in this worktree (result in the flight log).

## Inputs
- `the_one/interfaces/web/api.py` routes: `create_agent` (`@router.post("/agents")`), `update_agent` (`@router.put("/agents/{name}")`, needs no check), `rename_agent` (`@router.post("/agents/{name}/rename")`), provider create/update (`@router.post("/providers")`, `@router.put("/providers/{provider_id}")`), KB create/update (`@router.post("/knowledge-bases")`, `@router.put("/knowledge-bases/{kb_id}")`), MCP create/update (`@router.post("/mcp-sources")`, `@router.put("/mcp-sources/{source_id}")`), `_validation_detail`, `_reject_reserved_surface_name`.
- `the_one/db/migration.py::migrate_json_to_sqlite` — loops legacy JSON stems, `store.exists(name)` by stem, then `store.save(fs_store.load(name))`.
- `the_one/tools/sessions.py` — `scratch = settings.data_dir / "boxes" / f"{agent_name}-{sid}-{uuid4().hex}"`.
- `the_one/db/repositories.py::SQLiteAgentStore.save` — upsert (`ON CONFLICT(name) DO UPDATE`).

## Outputs
- New `the_one/naming.py` (stdlib only): `NameRuleError(ValueError)` with a `message` attribute; `check_name(value: object) -> str`; the message constants; `MAX_NAME_LENGTH = 64`; a `name_rule_detail(message, loc="name") -> list[dict]` helper returning `[{"type": "name_rule", "loc": [loc], "msg": message}]`.
- The eight routes refuse a rule-breaking name; `rename_agent`'s details are list-shaped on `loc ["name"]`; `create_agent` returns 409 on an existing name.
- `migrate_json_to_sqlite` skips a legacy file whose body name fails `check_name`, with one WARNING.
- The boxed scratch directory uses a slug of the agent name.
- Tests (new): `tests/test_naming.py`, `tests/test_api_name_rule.py` (routes + classification), plus additions to the migration and sessions tests.
- `the_one/agents.md` "Naming rule" section; `rename_agent` docstring updated.

## Acceptance Criteria
- [ ] `check_name` returns the trimmed name for a valid input and raises `NameRuleError` with the DD5 message for: an empty or whitespace-only name ("Enter a name."), a `/` or `\` ("A name can't contain / or \\."), exactly `.` or `..` after trimming ("A name can't be . or .."), a `Cc` character or a bidi control U+202A-U+202E / U+2066-U+2069 ("A name can't contain control characters."), more than 64 code points after trimming ("A name can be at most 64 characters."), and a non-`str` value ("Enter a name."). It accepts `default`, `My.Notes`, `café`, `a?b`, a 64-code-point name, and an emoji ZWJ sequence (e.g. "👩‍💻 helper"). Messages are module constants.
- [ ] Each of the seven checking routes (`create_agent`, `rename_agent`, provider create/update, KB create/update, MCP create/update) answers a body naming `a/b` with 422 and `detail == [{"type": "name_rule", "loc": ["name"], "msg": ...}]`, and no row is created or changed (asserted by reading back). `update_agent` keeps forcing the path name and needs no check.
- [ ] Order (DD4): on create routes, `check_name` runs on the submitted name and the trimmed value is written back into the request data before `model_validate` and any name guard; on the three PUT routes the check runs **only when the body contains `name`** (`"name" in data`), and the trimmed value is written into the merged dict (`existing.model_dump() | data`, or the route's equivalent) before `model_validate`, the reserved-name check and the KB `existing.name != updated.name` comparison. A PUT that omits `name` succeeds and keeps the stored name, **including when the stored name breaks the rule** (a legacy row stays editable until leg 4's repair renames it; tested by seeding a bad name through the repository). A create with `"  padded  "` stores `"padded"`. Per-route placement: `create_agent` right after `_read_json`; `create_provider` after the dev-mode `mock` 400; `update_provider` right after the merge (`merged.update(data)`) and before `model_validate` (the `__MASKED__` handling only touches `api_key` and is unchanged); `update_knowledge_base` right after the merge (after the 404); `create_mcp_source` before `_reject_reserved_surface_name`; `update_mcp_source` after the 404 and the surface-row 409 guard (so a surface row still gets its 409, tested with a bad name) and at the merge.
- [ ] `" self-configuration "` is refused by the MCP create and update routes as the reserved name (the trim happens before `_reject_reserved_surface_name`).
- [ ] `rename_agent` (the 422 checks keep running before the 404, as today; "same as the current name" compares the trimmed `new_name` with the path `name`): a missing/empty `new_name` → 422 `[{"type": "name_rule", "loc": ["name"], "msg": "Enter a name."}]`; a `new_name` equal to the current name after trimming → 422 list-shaped on `loc ["name"]` with "The new name is the same as the current name."; a rule-breaking `new_name` → 422 per DD5; an existing target → 409 `[{"type": "name_conflict", "loc": ["name"], "msg": "An agent with this name already exists."}]`; the 404 stays a string detail.
- [ ] `create_agent` with the name of an existing agent → 409 with the same `name_conflict` list detail, and the existing agent's stored configuration is unchanged (read back field by field, e.g. `description`, `system_prompt`).
- [ ] The route classification test (`tests/test_api_name_rule.py`) enumerates every POST/PUT route in the API router (`APIRouter(prefix="/api")`, so `route.path` includes `/api`) whose path starts with `/api/agents`, `/api/providers`, `/api/knowledge-bases` or `/api/mcp-sources` and asserts each is in exactly one of `CHECKED` (the seven above; each refuses `a/b`) or `EXEMPT` (a dict of path+method → one-line reason; expect roughly 25-30 sub-routes such as `/agents/{name}/rules`, the self-configuration routes, `/knowledge-bases/{kb_id}/items`, `/providers/{id}/oauth/*`). An unclassified route fails with a message naming it.
- [ ] `migrate_json_to_sqlite` skips a legacy JSON file whose body `name` fails `check_name`, logs a WARNING naming the file stem and the reason (once per startup: the JSON is never deleted, so the warning repeats each start; accepted), and does not store it. A valid file is stored with its body unchanged (not trimmed). After loading a file it also skips when `store.exists(config.name)` (the body name), not only the stem, so a file whose stem differs from its body name is no longer re-saved over the stored row on every start; tested with a mismatched stem and a second run.
- [ ] The boxed scratch directory is named from a slug of the agent name (every character outside `[A-Za-z0-9_-]` → `_`, at most 40 characters, `agent` when empty), so an agent named `a/../b` or `CON:` gets a single directory directly under `data_dir/boxes/`.
- [ ] Existing tests that use names the rule now refuses, or that POST `/api/agents` twice with one name relying on the upsert, are updated to valid names or a PUT, with the intent of each test kept (no test deleted to make it pass).
- [ ] `the_one/agents.md` has a "Naming rule" section (the rule, `the_one/naming.py`, the seven checking routes and the exempt paths with reasons, why the rule is not on the models, `default`'s role as the configuration for no-agent chats, the scratch-dir slug); `rename_agent`'s docstring points at the checker instead of "future name constraints added to `AgentConfig`".
- [ ] `make test-unit` passes (skip count as at baseline), and `ruff check` / `ruff format --check` pass on the touched files.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_naming.py tests/test_api_name_rule.py -x --timeout 30`
- The migration and sessions additions: run their test files the same way.
- `make test-unit` once at leg end; compare the skip count with the baseline in the flight log.
- `ruff check the_one/ tests/ && ruff format --check the_one/ tests/`

## Implementation Guidance

1. **`the_one/naming.py`.** Leaf module, stdlib only (`unicodedata`). `check_name(value)`: non-`str` → `NameRuleError(EMPTY)`; `stripped = value.strip()`; empty → EMPTY; any of `/`, `\` → SEPARATOR; `stripped in (".", "..")` → DOTS; any char with `unicodedata.category(c) == "Cc"` or in the bidi set → CONTROL; `len(stripped) > MAX_NAME_LENGTH` → TOO_LONG; else return `stripped`. Check order is as listed (so `"/"` reports SEPARATOR, not DOTS). Add a module docstring naming the flight (sortie 06, DD1-DD3) and the reason it is a leaf.

2. **Routes.** A small private helper in `api.py`, e.g. `_checked_name(value) -> str`, that calls `check_name` and raises `HTTPException(422, detail=name_rule_detail(e.message))`.
   - `create_agent`: after `_read_json`, set `data["name"] = _checked_name(data.get("name"))` before `AgentConfig.model_validate`. After validation and before `store.save`, `if await store.exists(cfg.name): raise HTTPException(409, detail=[{"type": "name_conflict", "loc": ["name"], "msg": NAME_CONFLICT_AGENT}])`.
   - `rename_agent`: replace the string details as listed in the criteria; run `_checked_name` on `new_name`; keep the existing `AgentConfig.model_validate(payload)` re-validation; map the store's `ValueError` to the 409 list detail.
   - Provider, KB, MCP **create**: `data["name"] = _checked_name(data.get("name"))` before validation (and, for MCP, before `_reject_reserved_surface_name`). Read each route first: if a route validates before building `data`, place the check so the trimmed value is what is validated and stored.
   - Provider, KB, MCP **update**: locate where `existing.model_dump() | data` (or equivalent) is built; run `_checked_name(merged.get("name"))` and write it back into the merged dict before `model_validate`, then the guards and the KB rename comparison. Preserve the provider `__MASKED__` handling and every existing guard order otherwise.
   - Do not touch `update_agent`.

3. **Route classification test.** Enumerate `the_one.interfaces.web.api.router.routes` (an `APIRoute` has `.path` and `.methods`); filter POST/PUT whose path (without the router prefix, check how it is mounted) starts with the four prefixes. `CHECKED` and `EXEMPT` are dicts keyed by `(method, path)`. For each `CHECKED` route the test sends `a/b` through the existing TestClient fixtures (`tests/_credential_helpers.py::auth_headers()`; databases from `tests/_schema_template.py`) and asserts the 422 shape and that nothing changed; each `EXEMPT` entry has a reason string. Unknown routes fail with their path.

4. **JSON migration.** In `migrate_json_to_sqlite`, after `config = fs_store.load(name)`, call `check_name(config.name)` inside a `try`; on `NameRuleError` log `logger.warning("Skipping legacy agent config %r: %s", name, e.message)` and `continue`; store the config unchanged otherwise. Add tests in the existing migration test file that covers `migrate_json_to_sqlite` (find it with grep; create `tests/test_json_migration_names.py` if none fits).

5. **Scratch-dir slug.** In `tools/sessions.py`, replace `agent_name` in the directory name with a module-level helper `_scratch_slug(agent_name)` (`re.sub(r"[^A-Za-z0-9_-]", "_", name)[:40] or "agent"`). Test it directly (unit, no bwrap needed) and, if an existing test asserts the old directory shape, update it.

6. **Test sweep.** `grep -rn` the unit tests for `"name":` values (and `name=` in API helpers) containing `/` or `\`, names over 64 characters, and duplicate `POST /api/agents` with the same name **within one test body** (known: `tests/test_db_api.py:819` PUTs a KB named `"My/Notes"` in the AC-10 slug-collision test: keep the collision intent with a different colliding pair such as `"My Notes"`/`"My_Notes"`; `tests/test_db_api.py` posts `secret-agent` (around lines 218-271) and `preserve-agent` (around 327-355) repeatedly — check whether any of those sit in one test and relied on the upsert, and switch the later ones to `PUT /api/agents/{name}`; `tests/test_agent_rename.py` — confirm no assertion reads the old string details). `tests/test_mcp_cache_cleanup.py:223` is a `package.json` fixture, not an API name; leave it. Update each to keep its intent. Browser tests and seeders (`tests/browser/seeders.py`) are not run in this leg, but grep them too and fix any seeded name the rule now refuses, since leg 3 runs those lanes.

7. **Docs.** `the_one/agents.md` "Naming rule" section (place it near the agent-store or API conventions; keep it short); the `rename_agent` docstring.

## Edge Cases
- **Unicode whitespace**: `str.strip()` strips Unicode whitespace as well as ASCII; intended.
- **Paths and NUL**: test `a/..`, `..`, `.`, and a NUL (`\x00`, a `Cc` character).
- **`PUT /api/agents/a%2Fb`** for a nonexistent agent still 404s (no route matches); a test pins it.
- **`name` missing on create**: "Enter a name." on `loc ["name"]` (today pydantic's "field required" list). That changes the message of an existing 422; update any test asserting the pydantic message.
- **`name` not a string** (number, list): "Enter a name.", not a 500.
- **Provider PUT with `__MASKED__`**: the name check must not disturb the masked-key preservation (`update_provider`).
- **KB create's 43-code-point advisory hint**: client-side advice only; unchanged.
- **`rename_agent` to a name differing only by surrounding whitespace from the current one**: after trimming it equals the current name → the "same as the current name" 422.
- **Leg 2 dependency**: a trimmed PUT name on MCP is a rename whose carries arrive in leg 2; nothing ships between legs, so no carry code here.

## Files Affected
- `the_one/naming.py` - new
- `the_one/interfaces/web/api.py` - seven routes, a private helper
- `the_one/db/migration.py` - skip bad names
- `the_one/tools/sessions.py` - scratch slug
- `tests/test_naming.py`, `tests/test_api_name_rule.py` - new
- existing tests touched by the sweep (e.g. `tests/test_db_api.py`, `tests/test_agent_rename.py`, the migration tests in `tests/test_db_migration.py`)
- `the_one/agents.md` - "Naming rule" section

---

## Post-Completion

The Developer marks the leg `landed`, records changes and verification in the flight log, and signals `[LAND:leg]`. Nothing is committed; the Flight Director commits the whole flight after review.

## Citation Audit
Checked against `2e82aaa` in the worktree: `rename_agent` (string details "new_name is required", "must differ", 409 `f"Agent already exists: {new_name}"`, 404 string) — verified; `migrate_json_to_sqlite` (skip by stem, `store.save(config)`) — verified; `tools/sessions.py` scratch path — verified; `SQLiteAgentStore.save` upsert — verified; `create_agent` validate-then-guards-then-save — verified. The provider/KB/MCP create and update bodies are cited by route decorator; the Developer confirms the merge point in each before editing.

Design review (Developer, 2026-10-26): approve with changes; adopted — PUTs check only a submitted name (legacy rows stay editable until the repair), the JSON import also skips by body name, per-route placement stated, the `/api` prefix and the size of the EXEMPT list, the sweep list corrected.

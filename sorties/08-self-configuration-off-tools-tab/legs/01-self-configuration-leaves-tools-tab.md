# Leg: self-configuration-leaves-tools-tab

**Status**: completed
**Flight**: [Self-configuration leaves the Tools tab](../flight.md)

## Objective
Remove the self-configuration server from the agent editor's Tools tab, and make the server, not the Studio form, own everything about it on an agent: agent writes neither attach nor detach it (DD2), refuse a per-agent setting for it (DD3), and strip a `disabled_tools` withhold for its tools (DD7); a stored selection is ignored at every build site and removed at startup (DD4); with tests and docs.

## Context
- The flight's DD1-DD8 are the design. Read `../flight.md` first; this leg does not restate the rationale.
- Charter criteria this leg delivers: all four (the Tools tab hides the server; Save keeps it attached; old selections stop applying and the API refuses new ones; docs describe the Self-configuration tab as the only control).
- The leg is one slice because the UI removal is unsafe without the server-side attachment carry: Studio's Save builds `mcp_source_ids` from the visible switches.
- Security-sensitive: this is the self-configuration identity surface. Every security assertion in the existing tests stays; only how a test builds its starting state may change.
- The flight's Behavior test `tests/behavior/self-configuration-off-tools-tab.md` is run by the Flight Director after this leg lands; it is not part of this leg's work.

## Inputs
- Branch `sortie/08-self-configuration-off-tools-tab` at `503d9751` (main), with the sortie artifacts and the behavior spec uncommitted in the tree.
- No prior leg.

## Outputs
- Server: `self_configuration/manage.py`, `self_configuration/constants.py`, `interfaces/web/api.py`, `interfaces/web/app.py`, `mcp/_tool.py`, `mcp/_tool_provider.py`, `agent/factory.py`, `self_configuration/projection.py`.
- UI: `interfaces/web/static/js/areas/studio/mcps-tab.js`, `areas/studio/agent-editor-selfconfig.js`, header comment of `areas/studio/self-configuration-tab.js`.
- Tests: new and rewritten unit tests; updated browser tests.
- Docs: `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`, `docs/ui-testid-registry.md`; `tests/test_nav_helper.py` `RETIRED_SELECTORS`.

## Acceptance Criteria

**Tools tab (DD1)**
- [ ] AC1. `mcps-tab.js` shows no tile for any source whose `config.self_configuration` marker is an object, the agent's own included; `isSelfConfiguration`, the `locked` branch (disabled master, hint, `describedBy`) and the `entry.locked` term in `patchEntry` are gone, and the module's header comment no longer describes a locked surface row. With self-configuration on and no other MCP source, the MCP servers section shows `mcp-empty-state`.
- [ ] AC2. `agent-editor-selfconfig.js::rebaseBaseline_` loses its dead surface branches: the `SELF_CONFIG_SOURCE_NAME` special case and the `mcp_overrides` rebase block (lines ~76-84), and the `SELF_CONFIG_SOURCE_NAME` declaration if it becomes unused. The **generic** `mcp_source_ids` added/removed-id branch (~64-72) stays. Comments match. `tests/browser/test_studio_self_configuration_dirty.py` passes.

**Attachment carry (DD2)**
- [ ] AC3. `PUT /api/agents/{name}` with an `mcp_source_ids` that omits the agent's attached surface id keeps it attached: the response and a following GET contain it, at its stored position `min(stored_index, len(incoming))`, and `GET .../self-configuration` reports `enabled: true`.
- [ ] AC3b. A `PUT` that **omits** `mcp_source_ids` altogether also keeps the surface attached. Today `AgentConfig` defaults the field to `[]` and detaches it. The test also asserts that the agent's **other** attached ids still reset to `[]` in that case: only the surface is carried, so nobody reads this as "an omitted field preserves everything".
- [ ] AC4. `PUT` (and `POST /api/agents`) with an `mcp_source_ids` that includes the agent's **own** surface row while it is not attached (an orphaned row) does not attach it. A foreign agent's surface id is still a 422 from `reject_foreign_surface_attachments`, unchanged.
- [ ] AC5. The five orphan tests named in DD2 build their orphan state with a direct `SQLiteAgentStore.save` (pattern: `tests/test_self_configuration_surface.py`, the direct-save block around 318-323) and keep every assertion about what an orphaned surface refuses or keeps; `manage.status()`'s docstring no longer describes a detach via PUT.

**Refusal (DD3)**
- [ ] AC6. `POST /api/agents` and `PUT /api/agents/{name}` return 422 when the incoming `mcp_overrides` is a dict with the key `"self-configuration"` and a non-empty entry. That means a dict with at least one key, whatever its values: `{"disabled_tools": []}` is refused, and so are tool lists and credential keys. A non-dict, non-null value is refused too. The `detail` is one plain sentence naming the Self-configuration tab. Nothing is stored.
- [ ] AC7. An incoming `{"self-configuration": {}}` or `{"self-configuration": null}` is accepted and dropped (not stored). A PUT whose `mcp_overrides` omits the key while a stored entry exists is accepted, because the check runs on the raw body, before `_merge_preserved_mcp_credentials`. That PUT also **removes** the stored entry: after the merge, `SURFACE_ROW_NAME` is popped from `data["mcp_overrides"]`, and `None` is stored if the map becomes empty. Any Save therefore cleans the entry, and a following GET has no `"self-configuration"` key.
- [ ] AC8. `reject_surface_credential_overrides` is removed and its credential test (`test_credential_override_on_a_surface_row_is_rejected`) now asserts the new 422.

**`disabled_tools` (DD7)**
- [ ] AC9. On POST and PUT, entries starting `mcp__self-configuration__` are removed from an incoming `disabled_tools` list (silently, no 422); other entries, including other `mcp__` names, are untouched. Only string entries are stripped. A non-list `disabled_tools`, or a list with a non-string element, is left for validation to refuse, and a test pins the mixed-list case.
- [ ] AC10. `MCPClientTool` has a public read-only `is_platform_surface` (true iff `is_surface_row(effective_source)`). In `AgentFactory`'s MCP registration loop (`agent/factory.py`, the loop after `get_tools_for_agent`), a tool with `getattr(tool, "is_platform_surface", False)` true is registered without the `disabled_names` / `is_tool_enabled` check; a tool without the attribute (an injected `StubTool`) is still filtered. Unit tests pin both.

**Build-time ignore (DD4)**
- [ ] AC11. `override_for(overrides, source)` in `self_configuration/constants.py` returns `None` for a surface row and `(overrides or {}).get(source.name)` otherwise, and is used at all three sites: `mcp/_tool_provider.py` (the `override_payload` in `get_tools_for_agent`), `agent/factory.py::_build_source_index` (or the function holding the `override_payload` line near 169), `self_configuration/projection.py` (near 154). A unit test per site: a stored `mcp_overrides["self-configuration"]` with `disabled_tools` (and one with `enabled_tools: []`) leaves all four surface tools present; an ordinary source's override still filters. A pure `override_for` test pins that a marker-less row named `self-configuration` gets its override, so the marker decides, not the name.
- [ ] AC12. `tests/test_self_configuration_surface.py::TestAC8PerToolControlThroughExistingMachinery` is renamed to state the new property (e.g. `TestSurfaceToolsCannotBeWithheldPerAgent`) and asserts all four tools present with a withhold seeded by direct store save, and the 422 on the API path.

**Startup cleanup (DD4)**
- [ ] AC13. New `manage.strip_surface_overrides(agent_store)` removes the `"self-configuration"` key from `mcp_overrides` (saving `None` when the map becomes empty) and every `mcp__self-configuration__*` entry from `disabled_tools`, for **every** agent, saving through `agent_store.save` only when something changed, with one INFO line per changed agent naming it. Each agent is in its own try/except (WARNING, continue), and listing the names sits in an outer guard. The function never raises. It takes no `mcp_repo`: it scans agents by name. That deviates from flight DD4's suggested signature, which the leg review recorded. Use the same name-listing call that `cleanup_copied_overrides` uses.
- [ ] AC14. The lifespan in `interfaces/web/app.py` calls it in its own try/except **immediately after** `reconcile_on_startup` and before `_state["factory"]` is installed (and so before connector and routine startup).
- [ ] AC15. `_migrate_override_key` is deleted; `reconcile_on_startup` still renames a legacy-named row to `SURFACE_ROW_NAME` and leaves the owner's overrides alone; its docstring no longer mentions per-tool checkboxes or the key migration. The two reconcile migration tests in `tests/test_self_configuration_api.py` (`test_reconcile_renames_legacy_row_and_migrates_override_key`, `test_reconcile_skips_migration_when_constant_key_already_taken`) are renamed and rewritten to match.
- [ ] AC16. Unit tests for `strip_surface_overrides`: the owner of an enabled surface; a disabled agent with a leftover entry; a `disabled_tools`-only withhold; a legacy `self-configuration (x)` key left alone; an agent with nothing to change is not re-saved (`updated_at` unchanged); one agent whose load raises (monkeypatch `load` for that agent, as the `override_cleanup` tests do) is skipped with a WARNING, and the others are still cleaned.

**Browser tests**
- [ ] AC17. `tests/browser/test_studio_self_configuration_tab.py::test_enable_shows_locked_row_on_mcps_tab` is renamed (e.g. `test_enable_shows_no_row_on_tools_tab`) and asserts no tile for the surface (no `[data-source-id="{S}"]`, no `mcp-source-toggle-{S}`) and `mcp-empty-state`. Its assertions must not spell the retired testid `mcp-source-self-configuration-hint-`.
- [ ] AC18. `tests/browser/test_studio_mcps_tab.py`: the enable-then-save test (around 1105) still proves the surface stays attached after a Save from the Tools tab, and a Save from the General tab is covered too (here or in the self-configuration browser tests). The own-vs-foreign tile test (around 1149-1200) is rewritten to assert neither the own nor a foreign surface gets a tile.

**Retirement and docs (DD5, DD6)**
- [ ] AC19. `mcp-source-self-configuration-hint-` is in `docs/ui-testid-registry.md`'s "Retired testids" table (not the live table) and in `RETIRED_SELECTORS` (`tests/test_nav_helper.py`); `tests/test_nav_helper.py` passes.
- [ ] AC20. Docs updated, every site in the flight's Technical Approach step 4: `CLAUDE.md` (the "Self-configuration surface" paragraph), `the_one/agents.md` (~887, ~897, ~905, ~913, the reconcile/LD7 notes, ~2344), `SECURITY-MODEL.md` (the "Ownership is enforced server-side" bullet and the injection paragraph: mitigations are approval mode or turning Agent prompt off), and the code comments named there (`self-configuration-tab.js` header, the `SURFACE_ROW_NAME` comment in `manage.py`, `_reject_reserved_surface_name`'s docstring in `api.py`). Locate the `agents.md` sites with `grep -n "per-tool\|locked checked\|never re-adds\|MCPs tab\|govern it" the_one/agents.md`, since the line numbers above are approximate. Afterwards, `grep -rn "per-tool checkbox" CLAUDE.md SECURITY-MODEL.md the_one/agents.md` finds no sentence saying the Tools tab governs the self-configuration server.

**Gates**
- [ ] AC21. `THE_ONE_TEST_NETNS=1 make test-unit` passes (skip count per CLAUDE.md, 15 under netns). The static guards pass: `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`. The `agent-tabs` and `agents` browser lanes pass with `THE_ONE_TEST_NETNS=1`, plus the owning lane of any other browser file the grep step touches. `ruff check` and `ruff format --check` are clean.

## Verification Steps
- AC1-AC2, AC17-AC18: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agent-tabs -x` and `--lane agents -x`; read the diff of `mcps-tab.js` and `agent-editor-selfconfig.js`.
- AC3-AC16: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_api.py tests/test_self_configuration_surface.py tests/test_self_configuration_external.py tests/test_self_configuration_projection.py tests/test_factory.py <new test files> -x --timeout 60`.
- AC19: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_nav_helper.py -x --timeout 60`.
- AC20: the grep above, plus `grep -n "locked checked" CLAUDE.md the_one/agents.md` (no surface hits).
- AC21: the commands named.
- Report for each new test whether it was falsified (shown failing with its fix removed by edit, then restored by edit).

## Implementation Guidance

1. **Grep first.** Grep `the_one/`, `tests/` (all lanes), `scripts/` and `tests/behavior/` for `isSelfConfiguration`, `mcp-source-self-configuration-hint`, `mcp-source-tile-self-configuration`, `reject_surface_credential_overrides`, `_migrate_override_key`, `mcp_overrides["self-configuration"]` / `"self-configuration":` in override payloads, `mcp__self-configuration__`, and tests that detach a surface with a PUT dropping its id (grep `mcp_source_ids": []` and `orphan` in `tests/test_self_configuration_*.py`). Every hit is either changed here or confirmed unaffected; list them in the flight log. Hits the leg review found, all already covered by the ACs:
- `tests/test_self_configuration_surface.py:274-276` (the AC12 PUT).
- `tests/test_self_configuration_api.py:340` (the AC8 credential test).
- `tests/test_self_configuration_api.py:618-680` (the AC15 reconcile tests, which assert `mcp_overrides[manage.SURFACE_ROW_NAME]` at 629-630 and 676-680).
- The orphan tests: `tests/test_self_configuration_external.py:146-152` and `:301-311`, `tests/test_self_configuration_api.py:172-235`, `tests/test_self_configuration_surface.py:437-449`.
- `tests/browser/test_studio_self_configuration_tab.py:85` (the retired testid, AC17).
- `tests/behavior/self-configuration-off-tools-tab.md` step 7, which writes the key by design. Leave it.

Two hits are unrelated: `tests/test_credential_gate.py:768` (`"self-configuration": MOUNT_PATH` is the confined-source map) and the comment at `agent-form-data.js:154-155`. `tests/browser/seeders.py` has no hit.

2. **Leaf helper.** In `self_configuration/constants.py` add `override_for(overrides, source)` beside `is_surface_row` (keep the module's runtime imports leaf-only). Move `SURFACE_ROW_NAME` into `constants.py`. `manage.py` re-exports it, because `tests/test_self_configuration_write.py` and `tests/test_self_configuration_api.py` use `manage.SURFACE_ROW_NAME`. Move its explanatory comment with it, reworded per AC20. Add the literal `SURFACE_TOOL_PREFIX = "mcp__self-configuration__"`, and do not copy the normalization regex. A unit test pins `SURFACE_TOOL_PREFIX == f"mcp__{_normalize_source_name(SURFACE_ROW_NAME)}__"`. `constants.py` has no runtime `the_one` imports and must keep it that way.

3. **Build sites.** Replace the three `override_payload = (config.mcp_overrides or {}).get(source.name)` lines with `override_for(config.mcp_overrides, source)`. In `mcp/_tool.py::MCPClientTool.__init__`, set `self._is_platform_surface = is_surface_row(effective_source)` and expose a read-only `is_platform_surface` property. `effective_source` is non-optional, and `_apply_override` preserves `config`. Import `is_surface_row` and `override_for` from `the_one.self_configuration.constants` only, never from `manage`: `manage` pulls in `agent.config` and `db.repositories`, which risks an import cycle. Check `tests/test_mcp_tool_provider.py` for `MagicMock` or `None` sources passed to `MCPClientTool`. In `agent/factory.py`'s MCP loop, register when `getattr(tool, "is_platform_surface", False) or (tool.name not in disabled_names and config.is_tool_enabled(tool.name))`. Update the comment above that loop (it says operators can disable an MCP tool by prefixed name; add that the platform surface is exempt).

4. **Write boundary** (`interfaces/web/api.py`, both `create_agent` and `update_agent`), in this order, right after the body is read and before the existing `mcp_overrides` merge:
   - DD3 check on the raw `data.get("mcp_overrides")`: if it is a dict and has the key `SURFACE_ROW_NAME`: a non-empty value raises 422 with the sentence; an empty dict or `None` value is popped from the dict.
   - DD7 strip: if `data.get("disabled_tools")` is a list, drop string entries that start with the surface prefix.
   - DD2 carry: if `data.get("mcp_source_ids")` is a list, call the new `manage.carry_surface_attachment(...)` (create: stored ids `[]`), which removes the agent's own surface row id(s) and, on update, re-inserts the stored own id at `min(stored_index, len(result))`. "Own" means a row for which `is_surface_row` holds and `owner_of(row) == name`; use `find_surface_row` / one `mcp_repo.list()` rather than a get per id if simpler. Leave a missing or non-list `mcp_source_ids` alone: note that `update_agent` does NOT preserve an omitted `mcp_source_ids` today (it defaults to `[]`); handle the omitted case too, so a PUT that omits the field also keeps the attachment (carry with incoming `[]`), and add a test for it.
   - The carry and the strip run on the raw body before `AgentConfig.model_validate`. The omitted-field case is its own branch: test whether the key is absent, rather than relying on `data.get(...)` returning a list.
   - After the existing `_merge_preserved_mcp_credentials` call, pop `SURFACE_ROW_NAME` from the merged map, and use `None` if it becomes empty (AC7).
   - Then remove the `reject_surface_credential_overrides` calls and the function itself. Keep `reject_foreign_surface_attachments`.

5. **Startup cleanup.** Add `strip_surface_overrides` to `manage.py`, modelled on `the_one/db/override_cleanup.py::cleanup_copied_overrides` (list names, load each, per-agent try/except), but run on every startup (no marker): it is idempotent and cheap. Call it in `app.py`'s lifespan immediately after `reconcile_on_startup`, inside its own try/except that logs a WARNING. Delete `_migrate_override_key` and its call in `reconcile_on_startup`; update the docstring and the lifespan comment above the call (it mentions migrating the owner's `mcp_overrides` key).

6. **Tools tab.** In `mcps-tab.js`, make `visibleSources` skip every marked row; delete `isSelfConfiguration`, the `locked` branch, the hint, `entry.locked` in `patchEntry`, and the header comment lines about the locked/own surface (lines ~23-28). In `agent-editor-selfconfig.js`, simplify `rebaseBaseline_` and its comments. Update `self-configuration-tab.js`'s header comment (lines ~8-11). Check `wc -l` stays well under the 800-line area-module rule (it shrinks).

7. **Tests.** Write the unit tests in AC3-AC16 and rewrite the pinned ones (rename over delete-and-re-add, so blame shows the intent change). Unit tests that need a fresh database use `tests/_schema_template.py`, never `ensure_schema`/`init_db`; API tests use `tests/_api_app.py::shared_app()` or an allow-listed fixture, as the existing self-configuration test files already do. Browser tests per AC17-AC18; reach rows through the kept testids and `[data-source-id]`, never the retired hint testid.

8. **Docs and retirement.** Per AC19-AC20. In `SECURITY-MODEL.md`, the injection paragraph's mitigation sentence becomes: approval mode (recommended), or turning Agent prompt off on the Self-configuration tab; state that the server's tools cannot be withheld one by one. The "Ownership is enforced server-side" bullet says an agent write never attaches or detaches the surface and any non-empty per-agent entry for it is a 422.

## Edge Cases
- **An agent with an orphaned surface row** (row exists, not attached): a PUT that lists the row's id does not attach it (AC4); `GET .../self-configuration` keeps reporting the orphan as today.
- **`mcp_overrides` becomes empty** after stripping: store `None`, matching `_merge_preserved_mcp_credentials`' `None`-not-`{}` rule.
- **An incoming `mcp_overrides` that is not a dict or null**: leave it for `AgentConfig` validation to 422, as today.
- **The legacy `self-configuration (x)` key**: never touched by the strip or the 422 (only the exact `SURFACE_ROW_NAME` key is).
- **A non-surface row named exactly `self-configuration`**: unsupported (flight DD4); no special handling.
- **Creating an agent while an old surface row for that name still exists** (a crash left one): the create cannot attach it (AC4).
- **A PUT that adds new ids while the surface is attached**: the surface goes back at `min(stored_index, len(incoming))`. The position comes from the stored list and is deterministic.

## Files Affected
- `the_one/self_configuration/constants.py` - `override_for`, surface tool-name prefix
- `the_one/self_configuration/manage.py` - `carry_surface_attachment`, `strip_surface_overrides`; delete `reject_surface_credential_overrides`, `_migrate_override_key`; docstrings
- `the_one/self_configuration/projection.py` - `override_for`
- `the_one/interfaces/web/api.py` - write-boundary normalization and 422 in `create_agent`/`update_agent`; `_reject_reserved_surface_name` docstring
- `the_one/interfaces/web/app.py` - lifespan call and comment
- `the_one/mcp/_tool.py` - `is_platform_surface`
- `the_one/mcp/_tool_provider.py` - `override_for`
- `the_one/agent/factory.py` - `override_for` in the source index; surface exemption in the MCP loop
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` - filter, delete locked branch
- `the_one/interfaces/web/static/js/areas/studio/agent-editor-selfconfig.js` - `rebaseBaseline_`
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` - header comment
- `tests/test_self_configuration_api.py`, `tests/test_self_configuration_surface.py`, `tests/test_self_configuration_external.py`, `tests/test_self_configuration_projection.py`, `tests/test_factory.py` (or new focused test files) - per AC
- `tests/browser/test_studio_self_configuration_tab.py`, `tests/browser/test_studio_mcps_tab.py` - per AC17-AC18
- `tests/test_nav_helper.py`, `docs/ui-testid-registry.md` - retirement
- `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md` - docs

## Citation Audit
Checked against the working tree at `503d9751` (no earlier leg edits these files):
- `the_one/agent/factory.py` - MCP registration loop: `for tool in mcp_tools: if tool.name not in disabled_names and config.is_tool_enabled(tool.name): registry.register(tool)` (lines ~484-487), comment above says operators disable MCP tools by prefixed name - verified
- `the_one/agent/factory.py` - `override_payload = (config.mcp_overrides or {}).get(source.name)` at ~169 inside the source-index builder - verified
- `the_one/mcp/_tool_provider.py` - same lookup at ~280 then `_apply_override(source, override_payload)` - verified
- `the_one/self_configuration/projection.py` - same lookup at ~154 then `filter_mcp_tools_by_override` - verified
- `the_one/mcp/_tool.py::MCPClientTool.__init__` - sets `_source_id`, `_source_name`, `_effective_source` before `super().__init__` (~117-129) - verified
- `the_one/interfaces/web/api.py::create_agent` (1181) - reads body, pops routines switches, merges `mcp_overrides` with `stored=None`, validates, then `reject_foreign_surface_attachments` and `reject_surface_credential_overrides` - verified
- `the_one/interfaces/web/api.py::update_agent` (1240) - merge before validation; routines switches forced to stored; the two guards after validation (~1309-1318) - verified
- `the_one/interfaces/web/app.py` - `await _self_configuration_manage.reconcile_on_startup(_self_configuration_mcp_repo, store)` at 381, bare (no try/except); `_state["factory"] = AgentFactory(store=store)` at 393; `repair_unsafe_names` (347) and `cleanup_copied_overrides` (359) run earlier - verified
- `the_one/db/override_cleanup.py::cleanup_copied_overrides` - per-agent try/except, WARNING, never raises - verified
- `the_one/self_configuration/manage.py::reconcile_on_startup` (291) calls `_migrate_override_key` for legacy-named rows; `disable` (225) leaves `mcp_overrides` untouched - verified
- `mcps-tab.js` - `isSelfConfiguration` (67), `visibleSources` (73-85), `buildEntry` locked branch (138-214), `patchEntry` `entry.locked` (273) - verified
- `agent-editor-selfconfig.js::rebaseBaseline_` (51-89) special-cases the surface only through `SELF_CONFIG_SOURCE_NAME` in the `mcp_overrides` loops (~76-84); the id branch (~64-72) is generic - verified by leg design review
- The five orphan tests and their line ranges (see step 1) - verified by leg design review
- `the_one/self_configuration/__init__.py` and `constants.py` have no runtime `the_one` imports; `mcp/_tool.py` imports nothing from `self_configuration` today - verified by leg design review
- `AgentConfig.mcp_source_ids` defaults to `[]`, and `update_agent` does not preserve an omitted value - verified by leg design review

## Implementation order
Steps 2-5 first (server, with its unit tests, running the unit targets), then step 6 (UI), then 7-8 (browser tests and docs), then the lanes in AC21.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

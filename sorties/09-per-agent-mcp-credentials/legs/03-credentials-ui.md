# Leg: credentials-ui

**Status**: in-flight
**Flight**: [Per-agent MCP credentials](../flight.md)

## Objective
Build the operator-approved Tools tab tile section (DD10) that lets an operator give an agent its own header values or environment variables for an attached MCP server, test the connection with them (on switch-on, first expand, Test, Refresh and after a Save), show the agent's own tool list, send the DD1 write shape on Save, place a DD2 refusal on its row, and show "Set per agent" in the Library editor (DD3), with browser tests, docs and the full browser gate.

## Context
- The flight's DD1 (client write shape), DD2 (error mapping), DD3 (Library), DD4 (which list) and DD10 (layout, row states, status line, test triggers, construction, accessibility) are the design. Read `../flight.md` first, especially DD10 and its mockup; this leg does not restate the rationale.
- Charter criteria this leg completes: 1 (the tile, write-only values, "Set per agent"), 3 (the switch-on test and the agent's own tool list in the Tools tab), 4 (the OAuth Authorization row). Criterion 2 is server-side (leg 1) and is shown end to end by the behavior test.
- **Server contracts from legs 1-2** (commits `4b274ae4`, `4b6071f1`):
  - `POST /api/mcp-sources/{source_id}/test/agent`, body `{"agent": name | null, "overrides": entry | null}`, returns `{"status": "ok", "tools", "capabilities"}`, `{"status": "needs_values", "missing": [...]}`, `{"status": "auth_required"}` (no `consent_url`) or `{"status": "error", "error": "<Class>: <msg>"}`. It returns 422 in the `mcp_override` shape for a refused value, and 404 or 422 for a bad source, agent or body.
  - A refusal on agent save is a 422 with details `{"type": "mcp_override", "loc": ["mcp_overrides", <source name>, "headers"|"env"|"bearer_token", <name>?], "msg"}`.
  - `GET /api/agents/{name}` (and the create, update and rename responses) carry `mcp_tool_cache: {<source_id>: {tools, fetched_at}}` for credentialed sources.
  - `mcp_overrides[<source>].headers` / `.env` come back with their names visible and their values masked. `bearer_token` comes back masked.
  - `GET /api/mcp-sources` returns `config.headers` / `config.env` in the clear and `secrets` with masked values (a blank value comes back as `""`), with the OAuth-managed keys removed, plus `oauth_active`.
  - Read `the_one/agents.md` "Per-agent MCP credentials (sortie 09)" and the route module `the_one/interfaces/web/mcp_agent_test.py`.
- **UI rules** (CLAUDE.md "Control library"): build only from existing `App.ui.*` factories (`section`, `button`, `secretInput`, `textInput`, `status`, `badge`, `chip`, `field`); add no new `js/ui` factory, no HTML-string sinks and no catalogue-owned classes outside `js/ui/`. Area-module classes are fine. `areas/` modules must stay under 800 lines: `agent-editor-controller.js` is at 771 and gets at most a 10-line delegate.
- **Debrief lessons:** for each interactive field, name the event, the announcement and the focus (sortie 07); open-and-close must stay clean (sortie 07's seed-copy defect); never probe on a later expand (M07 F09 A-L3-2); wait on settled state in tests, never on first-seen (M34); a leg touching the agent write path names the full `--parallel 3` gate (sortie 08).
- The Flight Director runs the behavior test `per-agent-mcp-credentials` and the HAT after this leg; they are not part of this leg's work. The behavior test reads testids and text from this leg (DD10's wording), so keep that wording.

## Inputs
- Branch `sortie/09-per-agent-mcp-credentials` at `4b6071f1`.
- Legs 1-2's server contracts (above).

## Outputs
- New `the_one/interfaces/web/static/js/areas/studio/mcp-agent-credentials.js` (`App.studio.mcpAgentCredentials`), loaded from `index.html` before `mcps-tab.js`.
- Changes: `areas/studio/mcps-tab.js`, `areas/studio/agent-form-data.js`, `areas/studio/agent-data.js`, `areas/studio/agent-editor-controller.js` (a delegate), `areas/studio/agent-editor.js` (wiring, if needed), `areas/studio/mcp-env-headers.js`, the studio CSS file for any new area classes, `index.html`.
- Tests: new `tests/browser/test_flow_studio_tools_mcp_credentials.py` (lane `agent-tabs`); the Library placeholder test in an existing MCP-editor file (lane `mcp`); updated pins wherever the tab's `/test/connect` mocking changes (for example `tests/browser/test_studio_mcps_tab.py`).
- Docs: `docs/ui-testid-registry.md`, `the_one/agents.md`, `CLAUDE.md` (one sentence).

## Acceptance Criteria

**The section (DD10)**
- [ ] AC1. Every expanded MCP server tile in the agent's Tools tab shows, in order, a section titled "Headers for this agent" (streamable-http) or "Environment for this agent" (stdio), a status line with Test and Refresh, then the existing tool rows. The section is built by `App.studio.mcpAgentCredentials.create(...)` in the new module, which returns a handle (at least `setAgent(agent)`, `setSource(source)`, `payload()`, `isDirty()`, `showErrors(items) -> placed[]`, `destroy()`). `mcps-tab.js` only mounts it and wires it. The existing Refresh moves from the tile header to the status line, keeping its `mcp-refresh-tools-btn-{id}` testid and its "Refresh tools for {name}" name. No self-configuration tile exists (sortie 08), so none gets the section.
- [ ] AC2. Rows and their states. A row exists for each name the server defines (the keys of `config.headers`/`config.env` and of `secrets` from the source response), plus each name stored for this agent, plus an `Authorization` row whenever `bearer_token` is stored. Header names match case-insensitively; env names don't. The rows are in a stable order: the server's names first in their order, then the agent-only names A-Z. The states:
  - **Server value**: the server's value is non-empty. Action: "Set for this agent".
  - **Set per agent · missing**: the server's value is `""` and this agent has none, in a warning tone carried as text. Action: "Set for this agent".
  - **Set for this agent**: stored for this agent, including a stored `bearer_token` on the Authorization row. Actions: "Replace" and "Use server value". For an agent-only name, the second action is "Remove".
  - **Supplied by the server's sign-in**: `Authorization` when the source has `oauth_active`. No action.
  - "Add header" / "Add variable" adds a row with a name input and a value input.
  - No row ever shows a value.
- [ ] AC3. Editing.
  - "Set for this agent" and "Replace" open a `secretInput` on the row with "Cancel" (the input takes focus; Cancel restores the row and returns focus to the button that opened it).
  - A typed value marks the editor dirty (`input` event). Erasing it back to empty while editing a stored name leaves the stored value in place and the form clean.
  - "Use server value" or "Remove" marks the name for removal: the row shows "Server value · on save" (or "Removed · on save") with "Undo", and focus moves to Undo; Undo restores the row and returns the form to clean.
  - "Add header": the name input takes focus; an empty new row adds nothing to the payload; Cancel on a new row removes it and returns focus to "Add header".
  - Every state change is announced through the section's live status (one short sentence, for example "X-Api-Key will use the server value when you save").
- [ ] AC4. Write shape (DD1). The handle's `payload()` returns `null` for an untouched source (no credential keys sent). For a touched source it returns:
  - `headers` (or `env`): every name this agent will keep, an unchanged stored name as `__MASKED__`, a new or replaced value as the string; a removed name is left out; if no names remain, `headers: null` (or `env: null`);
  - `bearer_token: null` whenever the operator set, replaced or removed `Authorization` while a `bearer_token` was stored.

  `agent-form-data.js::collectFormData` merges it into `mcp_overrides[<source name>]`, reaching the tab through a new `ctx.mcpsTab()` getter (AC10's plumbing).
  - **Tool filters:** the entry's `enabled_tools`/`disabled_tools` come from its loaded tool rows when they are loaded; otherwise they are copied from the stored agent record. A credential change on a tile whose rows did not load never clears the stored tool selection.
  - **Name spelling:** an unchanged stored name is sent under its **stored** spelling with `__MASKED__`, even when its row shows the server's spelling, because the merge looks names up exactly. A removed or replaced stored name uses the stored spelling too. Test.
  - **Snapshot drift (pre-existing):** loading a tile's rows after mount turns `mcp_overrides` from `null` into `{src: {}}` for a denylist source, which reads as dirty against the mount snapshot. `collectFormData` therefore drops an empty `{}` entry for a source that has no stored entry. Test: open and close a tile for an agent with **no** stored override, and the form stays clean.
  - `getFormSnapshot` covers the payload, so opening a tile, looking and closing it leaves the form clean.
- [ ] AC5. After a successful Save, every handle rebases on the saved agent and the tile re-runs the test once with `overrides: null` for each source whose credentials the Save changed (DD10).
  - **`setAgent` always rebases and discards pending credential edits.** It is called only on select, Save and Cancel (`agent-editor.js:~345`); a store refresh goes through `setNotices` and never reaches it. Cancel therefore discards every pending edit.
  - **Keep `mcp_tool_cache` across the post-save re-render.** The update path re-renders from the list route's object, which has no `mcp_tool_cache` (`agent-editor-controller.js:~700-711`). The controller copies `found.mcp_tool_cache = updated.mcp_tool_cache` beside the existing `found.kb_tool_names = updated.kb_tool_names`. Test: a credentialed tile keeps its list across a Save of an unrelated field.
  - **The create path** remounts the editor (`replaceWithAgent_`), so its first-expand test covers it; it gets no `afterSave` call.

**Tool list and testing (DD4, DD6, DD10)**
- [ ] AC6. Which list a tile shows. The client mirrors the server's `has_credential_override` (a non-empty stored `headers`, `env` or `bearer_token`, not counting `Authorization`/`bearer_token` on an `oauth_active` source).
  - A credentialed agent's tile shows only `agent.mcp_tool_cache[source.id]`, or a test result from this mount, and never `source.config._cache`.
  - Any other agent's tile shows the shared `_cache` as today.
  - With nothing to show, a credentialed tile reads "Not listed with this agent's values yet" with Test.
  - The count chip and `recount` use the same choice.
- [ ] AC7. The tab stops calling `/test/connect`. `agent-data.js` gains `testMcpAsAgent(sourceId, agentName | null, overrides)`, which posts to `/test/agent` with no module-level promise cache keyed by source alone: results are not cached, or are keyed by agent and source and dropped on Save. `fetchMcpSourceTools` and its `callbacks.fetchMcpSourceTools` plumbing are deleted (`agent-data.js:~415`, `agent-editor.js:~112`, `agent-editor-controller.js:~294`, `mcps-tab.js:15/47`). The new error text keeps the `fetchMcpSourceTools: HTTP` prefix that `mcp-error.js:21` matches, or that regex is updated in this leg. `testMcpAsAgent` calls `App.store.invalidate('mcp-sources')` after an `ok` for an agent with no credential override, since the route then writes the shared cache; it doesn't invalidate otherwise. The unit-tier pin `tests/test_store_static.py:~376-382` (agent-data's `'/test/connect', {` and the `if (data.status === 'ok') {` anchor) moves to the new call.
- [ ] AC8. When it tests:
  - **Switch-on:** a real user change of the attach switch from off to on expands the tile and runs the test at once with the tile's current, unsaved values; focus stays on the switch. The master's `onChange(nextChecked)` fires on a user toggle only (`setMaster` is silent, `tile.js:~39`). The switch-on path sets `entry.loadStarted = true`, because `setExpanded` fires no `onFirstExpand`. Switching off bumps `entry.gen`, so a result still in flight is dropped.
  - **First expand:** with no applicable list, the test runs once per tile per mount. A later expand never runs it.
  - **Test** runs it with unsaved values; **Refresh** does too (both force a new request).
  - **After a Save** (AC5).
  - Each request carries a per-tile generation number; a stale result is dropped (a newer test, the switch turned off, or a remount). `setAgent` from a store refresh never triggers a test.
- [ ] AC9. Status line results:
  - "Testing…" while a request runs;
  - `ok`: "Connected with this agent's values · N tools" (credentialed, or the tile has unsaved values) or "Connected · N tools", and the tool rows are filled by the existing `applyTools`, keeping the operator's unsaved checks;
  - `needs_values`, or a blank server name with no agent value, computed before any request: "Needs a value for X-Api-Key" (names joined with "and"), which takes precedence over a connection result;
  - `auth_required`: the existing sign-in note (`authNotice`);
  - `error`: the `App.mcpErrorMessage` headline with the raw text under "Technical details" (`App.buildMcpError`);
  - a 422 from the route: the message on its row (AC10).

  The rows stay when a later test fails. The result is announced once through the tile's live status.

**Errors (DD2)**
- [ ] AC10. Plumbing and errors. The controller (771 lines) gets, within its 29 lines of room:
  - an `mcpsTab_()` getter returning the mounted `d.handle.mcps`, exposed on its returned object and wired in `studio.js` (~227, beside `toolsTab`) and into `ctx` where `ctx.formData` is created (`studio.js` joins Files Affected; check its line pin in `tests/test_store_static.py`);
  - the `mcp_tool_cache` copy (AC5);
  - the `afterSave` call, with the changed source ids captured before the PUT;
  - the `mcp_override` split and delegate.

  The split is a helper in the new module (`splitItems(items, type)`), and the delegate and `showToolOverrideErrors_` share the tab-select and mount-guard logic.
  - On a Save 422, the delegate selects the Tools tab, expands each named source's tile (loc keys are source **names**; the module maps names to tiles), puts each message on its row (a loc that ends at the field goes on the section), and focuses the first.
  - When both `mcp_override` and `tool_override` details are present, the MCP one gets focus, since the MCP servers section comes first on the tab.
  - A detail with no tile or row goes into the header error, with the other details.
  - The controller stays at or under 800 lines; if the plumbing can't fit, move code into the new module.

**Library (DD3)**
- [ ] AC11. In the Library MCP editor (`mcp-env-headers.js`), an empty value input shows the placeholder "Set per agent" (the value column's `placeholder` changes from `'value'`), and each headers or environment table has one hint line, "A blank value isn't sent. Agents can set their own in their Tools tab.", carried by the section's `description` (`keyValueTable` has no hint option). Saving is unchanged.

**Accessibility, testids, guards, docs**
- [ ] AC12. Accessibility (DD10):
  - each row is a labelled group named by its header or variable name, and its state is text;
  - every button's accessible name includes the name (for example "Set X-Api-Key for this agent", "Replace X-Api-Key", "Use the server value for X-Api-Key"), including `secretInput`'s show and hide button (pass `showLabel`/`hideLabel`, for example "Show value for X-Api-Key");
  - the secret input is labelled "Value for X-Api-Key";
  - the status line is a polite live region;
  - the focus rules of AC3 and AC8 hold;
  - nothing depends on colour alone.
- [ ] AC13. New testids are prefixed `mcp-agent-cred-` (for example `mcp-agent-cred-section-{id}`, `mcp-agent-cred-row-{id}-{name}`, `mcp-agent-cred-state-{id}-{name}`, `mcp-agent-cred-set-{id}-{name}`, `mcp-agent-cred-replace-…`, `mcp-agent-cred-reset-…`, `mcp-agent-cred-undo-…`, `mcp-agent-cred-input-…`, `mcp-agent-cred-add-{id}`, `mcp-agent-cred-status-{id}`, `mcp-agent-cred-test-{id}`). They are listed in `docs/ui-testid-registry.md`, and the behavior test `tests/behavior/per-agent-mcp-credentials.md` is updated to cite them where it names a row, the status line or a button. The static guards pass: `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_area_module_size.py`.
- [ ] AC14. Docs: `the_one/agents.md` gains the Tools tab half of the sortie 09 block (the module, the handle, the write shape, the test triggers, the list choice) and updates the "MCPs tab ... Tools tab's MCP servers section" paragraph (Refresh's new place, no `/test/connect`, the per-agent list). `CLAUDE.md` gets one sentence on the tile section. The flight log has the leg's entry.

**Tests and gate**
- [ ] AC15. `tests/browser/test_flow_studio_tools_mcp_credentials.py` covers the cases below. It goes in lane `agent-tabs`, through that lane's `test_flow_studio_tools_*` glob, because `agents` sits at about 82% of its budget. It mocks `/test/agent` with `page.route` and checks request bodies, and checks the exact-PUT-body matrix through `page.evaluate` against the module where that's faster.
  - each row state, including the stored-`bearer_token` row and the OAuth row;
  - set, replace, use-server-value, undo and add, with focus after each;
  - the exact PUT body for each (masks for unchanged names, removed names left out, `headers: null`, `bearer_token: null`);
  - open-and-close staying clean;
  - a credential change on a tile with unloaded rows keeping the stored `disabled_tools`;
  - the switch-on test request body and its result, "Needs a value for …", and a stale result dropped after off and on;
  - a credentialed agent never shown the shared list;
  - no request on a second expand;
  - the post-save re-test with `overrides: null`;
  - a Save 422 landing on its row with focus;
  - stdio "Environment for this agent".

  The Library placeholder and hint are covered in the `mcp` lane. Existing tests are updated, and none is weakened:
  - `tests/browser/test_studio_mcps_tab.py` (lane `agents`): `_mock_tools_connect` (~87-108) and the direct `/test/connect` routes (~420, 516, 636, 671, 1058, 1093) move to `/test/agent`; the `fetchMcpSourceTools: HTTP 500` text pin (~568) follows AC7;
  - `test_tile_shape_switch_refresh_and_chips` (~828-846) expands the tile before measuring Refresh, which no longer sits on the collapsed tile;
  - `test_real_clicks_dirty_the_form` mocks the new route, since switch-on now tests;
  - `tests/test_store_static.py` (unit tier) per AC7;
  - run `test_studio_self_configuration_tab.py` (lane `agent-tabs`) and `test_router_items.py` (lane `routing`), which use tile testids.

  Re-check the `agent-tabs` lane's time against its budget, and re-budget in `scripts/run-tests.sh` (and CLAUDE.md's table) if it runs over.
- [ ] AC16. Gates:
  - the static guards (AC13);
  - the full `THE_ONE_TEST_NETNS=1 make test-unit` (expected skip count);
  - the full browser gate on a quiet host (1-minute load below about 1.0, no other test process): `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`, with rc=0, or one failure that passes isolated and is logged;
  - ruff clean.

  Record the `PARALLEL_RESULT` line and any lane over budget in the flight log.

## Checkpoint (mid-leg commit)
The leg runs in two parts with a commit between them (Flight Director call after the design review: 16 ACs is over the ~15 split-or-checkpoint line, and the operator's three-leg shape stands):
- **Part A:** AC1-AC9, AC12, AC13's testids and registry rows, and the test migrations in AC15 (the existing tests that break, plus the new file's section, payload, list and test-trigger cases). The `agent-tabs`, `agents` and `routing` lanes and `tests/test_store_static.py` are green. The Developer reports at this point; the Flight Director commits the checkpoint.
- **Part B:** AC10, AC11, the rest of AC13 and AC15, AC14 and AC16 (the full gates).

## Verification Steps
- AC1-AC10, AC12, AC15: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_studio_tools_mcp_credentials.py -m browser -x --timeout 60`, then `--lane agent-tabs` and `--lane agents`.
- AC11: the `mcp` lane.
- AC13: the static guard files above.
- AC14: read the docs diff.
- AC16: as stated.

## Implementation Guidance

1. **Read first:**
   - `mcps-tab.js` in full (`buildEntry`, `loadTools`, `applyTools`, `recount`, `cachedTools`, `patchEntry`, `setAgent`, `setSources`);
   - `agent-form-data.js::collectFormData` (~86-330), `getFormSnapshot`, `checkDirty`;
   - `agent-data.js::fetchMcpSourceTools` (~415-450) and where `agent-editor.js` (~111-130) and `agent-editor-controller.js` wire it;
   - `onSaveError_` / `showToolOverrideErrors_` (~94-160) as the pattern to mirror;
   - `mcp-env-headers.js` (~110-140, the `keyValueTable` columns);
   - the catalogue rows for `secretInput`, `section`, `status` and `button` in `docs/ui-control-inventory.md`.
2. **The module** (`mcp-agent-credentials.js`): DOM-built, ES5, the house pattern `(function () { ... window.App.studio.mcpAgentCredentials = { create: create }; })();`. It keeps per-row state (`stored`, `pending` (value or removal), `isNew`) and derives `payload()` and `isDirty()` from that state, never from DOM text. It owns the status line node and exposes `setStatus(kind, data)` for `mcps-tab.js`.
3. **`mcps-tab.js`:** mount the section and the status line in `buildEntry`, above `noteHost` and the group. Keep the attach switch's `onChange`, and add the off-to-on switch-on test (a user change only, never `setAgent`). Replace `loadTools` with a test call that goes through `testMcpAsAgent` with the section's `payload()`, keeps the per-tile `gen` guard, and maps each status (AC9). Route `cachedTools` through the AC6 choice. Expose the handles (`credentialPayloads()`, `showCredentialErrors(items)`, `afterSave(savedAgent, changedSourceIds)`) on the tab handle. The editor reaches them through `h.mcps` and the form data through `ctx`, the way `ctx.toolsTab` is reached today.
4. **`agent-form-data.js`:** merge the payloads into `mcp_overrides`, applying the stored-copy rule for tool filters.
5. **Save success and error** (`agent-editor-controller.js`): after a successful PUT or POST, call the tab's `afterSave` with the source ids whose payloads were non-null. Add the error delegate. Keep the controller at or under 800 lines; if it can't fit, move code out to the new module.
6. **Library** (`mcp-env-headers.js`): the value column placeholder and the hint line.
7. **Tests, docs, gates.** Run the long gates in the background and wait for each notification. The parallel gate must not run alongside the unit suite.

## Edge Cases
- **Create mode (`#agents/~new`)**: `agent: null` in the test; the payload is still collected for the POST; there is nothing stored to mask.
- **A source with no names and no agent names**: the section shows only "Add header" / "Add variable", plus a one-line empty note ("This server sets no headers.").
- **An `Authorization` row on an `oauth_active` source with a stored per-agent value** (from before the sign-in): show "Supplied by the server's sign-in" (the server ignores the value, DD8). A "Remove" action may be offered to clean it up; if it isn't, the stored value stays harmless.
- **The same name in the server's set and the agent's set in a different case** (headers): one row, keyed by the server's spelling.
- **Detach (switch off) with pending credential edits**: the tile collapses; the payload is still sent for that source (it is harmless, and the server keeps it with the stored entry). Simplest is to keep the pending edits; don't discard them silently.
- **A refresh of the agents store while editing**: it never reaches `mcps.setAgent` (only `setNotices`), so pending edits survive it. `setAgent` itself always rebases (AC5).
- **Refresh on a collapsed tile**: Refresh now lives in the body, so the old "open the panel if closed" branch goes.
- **`secrets` on a source**: for streamable-http it is the flat header table, and for stdio the flat env table (minus OAuth-managed keys, already removed by the API), so every key is a row name.
- **A route 404 (the source was deleted meanwhile)**: an error status, with no crash.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-agent-credentials.js` - new
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` - mount, test triggers, list choice
- `the_one/interfaces/web/static/js/areas/studio/agent-form-data.js` - payload merge
- `the_one/interfaces/web/static/js/areas/studio/agent-data.js` - `testMcpAsAgent`
- `the_one/interfaces/web/static/js/areas/studio/agent-editor-controller.js` - delegates (10 lines or fewer)
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` - wiring, if needed
- `the_one/interfaces/web/static/js/studio.js` - the `mcpsTab` getter wiring (check `tests/test_store_static.py` pins)
- `the_one/interfaces/web/static/js/areas/studio/mcp-env-headers.js` - placeholder and hint
- `the_one/interfaces/web/static/css/…` (the studio stylesheet) - area classes for the section
- `the_one/interfaces/web/static/index.html` - script tag
- `tests/browser/test_flow_studio_tools_mcp_credentials.py` - new; MCP-editor test file - placeholder; `tests/browser/test_studio_mcps_tab.py` - mock updates
- `docs/ui-testid-registry.md`, `the_one/agents.md`, `CLAUDE.md`, `tests/behavior/per-agent-mcp-credentials.md`

## Citation Audit
Checked against the working tree at `4b6071f1`:
- `mcps-tab.js`: `buildEntry` 132 (the Refresh button in `actions`, `ui.groupTile` with `master.onChange`, `onFirstExpand` setting `loadStarted` and calling `loadTools(entry, false)`, the `noteHost` and `group` appended to `tile.body`); `cachedTools` 106; `recount` 270; `applyTools` 333; `loadTools` 367 (calls `fetchMcpSourceTools(source.id, {forceRefresh})`); `setAgent` 469; `setSources` 480 - verified
- `agent-form-data.js::collectFormData` builds `mcp_overrides` from `[data-mcp-tool-toggle][data-mcp-source]` (~280-325); `ctx.toolsTab` reached at ~218 - verified
- `agent-editor-controller.js`: `onSaveError_` 94, `showToolOverrideErrors_` 123, called at ~635 and ~734; 771 lines - verified
- `agent-editor.js:111` mounts `studio.renderMcpsTab(...)`; `h.mcps` patched at ~344-345 - verified
- `agent-data.js::fetchMcpSourceTools` 415 (error prefix `fetchMcpSourceTools: HTTP` at ~427) - verified
- `mcp-env-headers.js` value column `placeholder: 'value', type: 'secret'` (~122-124) - verified
- `App.ui.secretInput`, `section`, `status`, `button`, `badge`, `chip`, `field`, `textInput` exist in `js/ui/` - verified
- Legs 1-2's server contracts - from their landing reports and the committed code; re-check the route's response shapes in `mcp_agent_test.py` at implementation

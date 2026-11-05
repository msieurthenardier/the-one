# Leg: secrets-ui

**Status**: in-flight
**Flight**: [Secrets](../flight.md)

## Objective
Build the operator surfaces from the approved mockup:
- Library › Secrets: list group, routed editor, Add menu, start-page card, Jump to;
- a `suggest` search-ahead option on `App.ui.chipList`, used for Allowed tools;
- the Secrets section at the top of the agent's Tools tab, saved as `secret_ids`;
- the Secrets group in the chat drawer;
- the Secrets example on Settings › Prompts.

Each comes with browser and contract tests, and the full browser gate runs at the end.

## Context
- The design is the flight's **DD1, DD2 (client), DD3 (client) and DD8 (Prompts page)**. **The approved mockup is the reference:**
  - `sorties/10-secrets/mockup/s10-mockup.js` (round 2, built on the same `App.ui` factories);
  - screenshots `r2-1-home-address-light.png` (editor and search-ahead), `r2-2-new-light.png` (new secret with a generated first key and the allowed-tools refusal), `r2-3-tools-{light,dark}.png` (Tools tab), `5-chat-transcript-*.png` (drawer group).

  The approved copy is in flight DD1/DD2. Read `../flight.md` and the mockup script first. Where this leg and the flight disagree, this leg wins and the disagreement is a defect to report.
- Server work is done and committed:
  - leg 1 (`dfc6677e`): `/api/secrets` CRUD with `__MASKED__` values, 422 `loc`s `["name"]`, `["values", i, "key"|"value"|"id"]`, `["allowed_tools"]`, `["allowed_tools", i]`, 409 on a name clash; agent `secret_ids` (kept when omitted, 422 `["secret_ids", i]` on an unknown id); `GET /api/tool-names` returning `[{name, source, source_name, description}]`;
  - leg 2 (`c0d75b27`): runtime, and `/api/info` `secrets_prompt_example`;
  - behavior run 1: 10/10.
- **Two parts with a checkpoint commit between them** (project rule for legs over about 15 ACs):
  - **Part A**: the `chipList` `suggest` option (a shared factory change: catalogue row, two-engine contract tests, Accessibility Reviewer) and Library › Secrets.
  - **Part B**: the Tools-tab section, the drawer, the Prompts page, Jump to.

  The Flight Director runs a review and commit after part A.
- UI conventions this project enforces (CLAUDE.md "Control library", "UI test apparatus", "Browser tests navigate through `_nav.py`", "List rows go through `_lists.py`"):
  - no HTML-string sinks;
  - caller-supplied testids, registered in `docs/ui-testid-registry.md`;
  - every owned class in the catalogue;
  - disabled buttons on `--btn-disabled-*`;
  - tests navigate via `_nav`/`_lists`, never raw hashes;
  - the static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`) run on every static change.
- Leave guard: the secret editor registers an `App.nav` dirty source. **An `App.nav` source's `discard` runs on a still-mounted editor** (sortie 09 lesson): it must reset the editor to its baseline, never assume teardown.

## Inputs
- `static/js/areas/studio/library-pane.js` (`LIBRARY_GROUPS`, `LIBRARY_START`, cache, selection, Add menu); `static/js/router.js` (header table, `SECTIONS` create entry `:86-89`, section labels `:447`, collection/noun map `:476-479`); `areas/studio/studio-route.js`; `areas/studio.js`.
- The connector editor pair `areas/studio/connector-editor.js` / `connector-glue.js` (the routed `/~new` and `/{id}` editor with a pending-id rule) and `areas/studio/provider-editor.js` (the editor look the mockup follows: `editorShell`, `section`, `field`, `secretInput`, `dangerZone`).
- `static/js/ui/chip-list.js`; `static/js/ui/search-list.js` and `ui/menu.js` (look for a listbox/popover pattern to reuse before writing a new one); `static/js/ui/key-value-table.js` (`secret` column with `storedKey`; `setError(rowIndex, colKey, text)`); `static/js/icons.js` (no `key` icon today).
- `areas/studio/agent-editor.js` (Tools tab case `:91-125`), `areas/studio/knowledge-tab.js` (the row shape and load-flag pattern), `agent-form-data.js` (`kb_ids` sent only when loaded, `:187-201`), `agents-list.js` (`:386-391` collections refreshed), `areas/chat/agent-drawer.js` ("What it can use"), `areas/admin/system-page.js` (`renderPromptsPage`, the rules and notes example sections), `static/js/jump-to.js` (`COLLECTIONS`, the group table `:62-67`), `static/js/store.js` (`URLS`, `App.usage`).
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `scripts/run-tests.sh` (lane patterns), `tests/browser/_nav.py`, `_lists.py`, `seeders.py`.

## Outputs
- New:
  - `areas/studio/secret-editor.js` and `areas/studio/secret-glue.js` (or one module if the connector pair's split isn't needed; justify);
  - `areas/studio/secrets-section.js` (the Tools-tab section);
  - a `key` icon in `icons.js`.
- Modified: the files under Inputs, plus `index.html` (script tags), `docs/ui-control-inventory.md` (the chip-list row gains `suggest` and any new owned classes), `docs/ui-testid-registry.md`, `scripts/run-tests.sh`, `tests/browser/seeders.py` (a `seed_secret` helper), and `_lists.py` (the `secrets` group) if needed.
- Tests:
  - `tests/browser/test_ui_chip_list_suggest.py` (contract, Chromium and WebKit, lane `contracts-controls`);
  - `tests/browser/test_flow_studio_secrets.py` (lane `library`, added to `library_pat`);
  - `tests/browser/test_flow_agent_secrets.py` (lane `agent-tabs`, added to `agent_tabs_pat`);
  - Prompts and Jump to checks folded into existing files in their lanes (`settings`, `shared`), or new files assigned in `run-tests.sh`;
  - `tests/test_run_tests_lanes.py` kept green.
- Docs:
  - `the_one/agents.md` "Secrets (sortie 10)": the UI part, routes, testids, the leave-guard discard, the `suggest` option;
  - `CLAUDE.md`: one short sentence on the UI, plus the new lane assignments if any lane list in CLAUDE.md names files;
  - the router header comment.

## Acceptance Criteria

### Part A: search-ahead and Library › Secrets

**`App.ui.chipList` `suggest` (DD3)**
- [ ] A1. `App.ui.chipList({..., suggest})` takes `suggest(term) -> [{value, label, detail}]` (sync). When `suggest` is absent, the control is byte-for-byte today's DOM and behaviour: existing chip-list contract tests pass unchanged. When present:
  - The input gets `role="combobox"`, `aria-autocomplete="list"`, `aria-expanded`, and `aria-controls` pointing to a listbox (`role="listbox"`) with `role="option"` rows, managed through `aria-activedescendant`.
  - Typing shows at most 8 suggestions for a non-empty trimmed term (case-insensitive substring, already-chosen values left out). An empty term closes the list. Zero matches show a non-option status line ("No tool matches “{term}”.") inside the popover.
  - ArrowDown and ArrowUp move the active option (wrapping). Enter or click on an option adds it as a chip, clears the input, keeps focus in the input and fires `onChange`. Escape closes the list without clearing the input.
  - With the list closed or no active option, Enter keeps today's behaviour (adds the typed text).
  - Blur closes the list without adding anything.
  - The popover is positioned under the input, inside the control's own box, with no `document` listener installed by the factory (CLAUDE.md: library factories may not install document listeners).
  - It reuses an existing listbox pattern from `search-list.js`/`menu.js` if one fits; the leg reports which.
  - Option rows show `label` (mono) and `detail` (muted).
  - Colours come from tokens only, contrast-audited in light and dark.
- [ ] A2. The catalogue row for `chipList` in `docs/ui-control-inventory.md` documents `suggest` and lists any new owned classes. `tests/test_ui_control_inventory.py`, `test_ui_ownership.py` and `test_ui_emitted_classes.py` pass.
- [ ] A3. `tests/browser/test_ui_chip_list_suggest.py` (engine-parametrized, Chromium and WebKit) covers every behaviour in A1, including the ARIA attributes and states, keyboard-only adding, the no-`suggest` regression, and the 8 cap. Run with `THE_ONE_REQUIRE_WEBKIT=1`.

**Library › Secrets (DD1)**
- [ ] A4. **The list and routes.**
  - `LIBRARY_GROUPS` gains `{id: 'secrets', section: 'secrets', route: 'secrets', collection: 'secrets', label: 'Secrets', icon: 'key', testid: 'secret-card', prefix: 'secret:'}` after connectors, with empty and fail texts.
  - Rows show the name and meta "N value(s) · N agent(s)" (a new `App.usage.secretAgents(agents, id)`, distinct agent names whose `secret_ids` hold the id).
  - The Add menu gains "Secret" (`library-add-secret`).
  - The Library start page gains a Secrets card (`library-start-secrets-add`) with a one-sentence description.
  - `store.js` gains `secrets: '/api/secrets'`, invalidated after every secret write.
  - Routes `#library/secrets/~new` and `#library/secrets/{id}` work like connectors (router `SECTIONS`, labels, collection map, `studio-route.js`). The bare `#library/secrets` redirects to `#library`.
  - The `routing` lane's router tests that pin the section list are updated.
- [ ] A5. **The editor** (`App.ui.editorShell`, breadcrumb "Library / Secrets", Cancel and Save, or Create on `~new`; no Test). It matches the mockup round 2:
  - Section "Secret": Name (`textInput`, testid `secret-name`) and Description with the approved hint.
  - Section "Values" (`layout: 'stack'`, the approved description): a `keyValueTable` (testid `secret-values`, add testid `secret-add-pair-btn`, label "+ Add pair") with Key (mono) and Value (`type: 'secret'`, stored mode through `storedKey` when the server sent `__MASKED__`).
  - Section "Allowed tools" with the approved description: a `chipList` with `suggest` over `GET /api/tool-names` (fetched once per editor mount; on failure, free text still works and a muted line says suggestions are unavailable). Detail text is the source ("Built-in", or the MCP server's name). The approved hint.
  - Section "Used by": agent links to `#agents/{name}/tools`, or the empty sentence.
  - Danger zone "Delete secret" (`delete-secret-btn`), armed with `App.ui.confirm`. While agents hold a grant, the arm text says "Delete and remove from N agent(s)?".
  - On `~new`, one empty row is present, and its key follows the name through the slug rule (lowercase, runs of other characters to `_`, trimmed) until the operator edits that key.
- [ ] A6. **Saving.**
  - Create posts `{name, description, values: [{key, value}], allowed_tools}` and opens the new secret (`#library/secrets/{id}`, replace-routing like connectors' pending-id rule).
  - Save puts the full ordered `values` with each stored row's `id` and `__MASKED__` for an untouched stored value. A row whose key changed has its value cleared by the table, so the operator must re-enter it.
  - After a successful Save the editor re-baselines from the response (stored masks again, clean), and focus goes through `App.focusAfter` as in the other editors.
  - **No plaintext secret value is ever written to an attribute, `title`, `aria-*`, or the DOM text** (only `.value`). A test reads every attribute and the text content of the editor after typing a value and asserts it is absent.
- [ ] A7. **Errors.**
  - A 422 lands on its target: `["name"]` and `["description"]` on their fields; `["values", i, "key"|"value"]` through `table.setError(i, 'key'|'value', msg)`; `["values"]` and `["allowed_tools"]` on the section or field; `["allowed_tools", i]` on the chips field, naming the chip.
  - A 409 lands on Name.
  - Anything else goes through `editorShell.setError`.
  - The mockup's empty-allowed-tools sentence is the server's message, or the client's own pre-save check with the same words; pick one and say which.
- [ ] A8. **Leave guard.** The editor's dirty state is a value model (typing then reverting is clean), registered with `App.nav`. Leaving dirty asks once; Continue runs `discard`, which resets the still-mounted editor to its baseline; Stay keeps the edits.
- [ ] A9. **Browser tests** (`tests/browser/test_flow_studio_secrets.py`, lane `library`) cover:
  - create with the generated first key, then add and remove a pair;
  - edit with masks kept (the exact PUT body);
  - renaming a key clears its value and Save then requires it;
  - each 422 on its target, and a 409 on the name;
  - search-ahead adds a real tool name from a seeded MCP cache and a built-in;
  - delete with the used-by arm text, and the row disappearing;
  - the leave guard (Stay and Continue);
  - the no-plaintext-in-DOM check;
  - Library row meta;
  - Jump to opening a secret (if Jump to lands in part A; otherwise part B).

### Part B: Tools tab, drawer, Prompts, Jump to

- [ ] B1. **Tools tab (DD2).** A "Secrets" section (`h2`, testid `agent-tools-secrets-section`) is inserted **before** MCP servers, with the approved intro line.
  - Rows follow the Knowledge tab's shape: an `App.ui.toggle` labelled with the secret's name (`agent-secret-toggle-{id}`), then the text "{description} · N tool(s)" (`aria-describedby` from the toggle).
  - No keys and no tool names are shown.
  - Empty state: "No secrets yet." with a link to the Library.
  - Load failure: a danger status, and the root marker `data-secret-list-loaded` is absent, so Save omits `secret_ids` (the server keeps the stored grants; the `kb_ids` pattern).
  - The section patches in place on `setAgent` (no remount) and rebuilds only when the set of secrets changes.
- [ ] B2. **The save body.** `agent-form-data.js` sends `secret_ids` (the checked ids, in Library order) only when the section loaded. `agents-list.js` refreshes `secrets` with the other collections. A 422 on `["secret_ids", i]` shows on the section. Tests check the exact PUT body with and without a load failure, and that open-and-close stays clean.
- [ ] B3. **Drawer.** The chat drawer's "What it can use" gains a read-only "Secrets" group after MCP servers: the granted secrets' names, or "None". It is read from the agents and secrets store collections and refreshes when either changes.
- [ ] B4. **Settings › Prompts** shows a "Secrets" section in assembly order (after notes, before the date line) rendering `/api/info` `secrets_prompt_example` in a `codeBlock`, like the rules and notes examples (`textContent` only).
- [ ] B5. **Jump to** lists secrets (`kind: 'secret'`, where "Library · Secret") from the `secrets` collection, and a pick opens the editor.
- [ ] B6. **Browser tests:**
  - `tests/browser/test_flow_agent_secrets.py` (lane `agent-tabs`): B1-B3, including the exact PUT bodies and the drawer;
  - the Prompts check in the `settings` lane;
  - the Jump to check in its existing file's lane.
- [ ] B7. Every new testid is in `docs/ui-testid-registry.md`, and `tests/test_nav_helper.py`'s guards pass.

### Gate and docs
- [ ] G1. Part A ends with:
  - `THE_ONE_TEST_NETNS=1 make test-unit` (static guards included);
  - the `library`, `routing` and `contracts-controls` lanes (with `THE_ONE_REQUIRE_WEBKIT=1`), each green.

  The Developer stops and reports `[LAND:leg]` with "part A" in the report; the Flight Director reviews and commits, then resumes the leg for part B.
- [ ] G2. Part B ends with:
  - `THE_ONE_TEST_NETNS=1 make test-unit`;
  - the full browser gate on a quiet host (1-minute load below about 1.0; check `uptime` and `ps` first): `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`.

  The gate passes with `rc=0`, or with failures that pass in isolation and are recorded. Lane times are checked against budgets; any lane over 1.15x is reported.
- [ ] G3. The docs listed under Outputs are updated, and `ruff check`/`ruff format --check` are clean.

## Verification Steps
- A1-A3: the contract file in Chromium and WebKit (`THE_ONE_REQUIRE_WEBKIT=1 ... --lane contracts-controls`, or the file alone with `-m browser`).
- A4-A9: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_studio_secrets.py -m browser -x`, then `--lane library` and `--lane routing`.
- B1-B7: `tests/browser/test_flow_agent_secrets.py` and the touched files, then `--lane agent-tabs`, `--lane settings` and the Jump to file's lane.
- G1/G2: as stated. Report the `PARALLEL_RESULT` line and the per-lane times.
- **Falsification** (yes or no for each): A1's no-`suggest` regression (by making the option always on), A6's no-plaintext-in-DOM check (by writing the value to a `title`), A8's discard reset (by making `discard` a no-op), and B2's omit-on-load-failure (by always sending `secret_ids`).

## Implementation Guidance
1. **Part A, factory first:** read `search-list.js`/`menu.js` for a reusable listbox. Implement `suggest` behind the option, then the contract tests and the catalogue row, then run the static guards and the contract lane.
2. **Store, router, Library group, Add menu, start card, key icon.**
3. **Editor and glue**, following the connector pair's routing and pending-id handling and the provider editor's look. Use the mockup script as the build reference (it calls the same factories). Seeders: `seed_secret(base, name, values, allowed_tools, description='')`.
4. **Errors, leave guard, focus-after, tests; part A gate; stop and report.**
5. **Part B** (after the Flight Director resumes you): the Tools-tab section, form data, drawer, Prompts, Jump to, tests; then the full gate and docs.

## Edge Cases
- **An MCP tool name that no longer exists** in the catalogue but is stored in `allowed_tools`: it shows as a normal chip, and nothing refuses it client-side.
- **`/api/tool-names` slow or failing**: chips still accept typed names, and a muted line explains that suggestions are unavailable.
- **Two editors** (two tabs): Save is last-writer-wins on the server. No client locking.
- **A secret deleted while an agent editor is open**: the next agent Save gets a 422 on `["secret_ids", i]`. The section shows it, and the store refresh removes the row.
- **A very long description** in the Tools-tab row: it wraps or ellipsizes per the Knowledge row's existing CSS, with the full text in the accessible description.
- **Paste of several tool names** into the chip input: today's paste behaviour (split into chips) is kept, and suggestions don't interfere.

## Binding addendum (Developer design review, 2026-11-05)
This section **overrides** anything above it that conflicts with it. The review found the wiring inventory incomplete; every item below is part of the leg.

**Registration points for the fifth Library group (A4).** Mirror every connector reference:
- `areas/studio.js`: state fields (`:107-122`), `defineProperty` accessors (`:164-181`), glue creation (`:327`), reset (`:394`), the `prevSection` reset (`:491`), the `render` dispatch (`:541`), the `App.store.subscribe` with pending consume (`:631`), and the dirty/isOpen check (`:696`).
- `areas/studio/studio-route.js`: the section-to-sub mapping (`:29-30`, `:65-76`), sub parsing (`:227-234`) and the pending-item rule (`:317-351`).
- `areas/studio/library-pane.js`: the add text blocks (`:107-110`), find/collection getters and setters (`:139`, `:148`), the selected-row key (`:191-195`), the count meta (`:237`), the create-mode check (`:382`) and the Add menu (`:416`).
- `router.js`: the header comment (`:14`, `:22`), `SECTIONS` (`:89`), `LIBRARY_LABELS` (`:447`) and `ITEM_COLLECTIONS` (`:479`).
- `index.html`: script tags next to the connector pair (`:136`, `:150`).
- **Required test helpers:** `tests/browser/_nav.py` (`LIBRARY_SECTIONS` `:113`, the legacy mapping `:207`/`:247`, docstring `:31-33`) and `tests/browser/_lists.py` (the `_List` map `:125`, `LIBRARY_KINDS` `:196`, the add-menu map `:204`).
- **Keep the two-file split:** `secret-editor.js` (the editor) and `secret-glue.js` (routing, pending id, store and reload), like the connector pair.

**Static and unit pins to update (A4).**
- `tests/test_library_groups_static.py:7`, `:18` (four groups → five);
- `tests/test_nav_helper.py:48-50`, `:82`, `:150-154`, `:739` (the legacy mapping and the bare-sync regex);
- `tests/browser/test_store_library.py:30`, `:264-276` (collections and the per-move GET count);
- check `tests/test_studio_editor_contracts_static.py`.

**Agent-editor plumbing (B1/B2), the Knowledge flow's twins:**
- `agent-data.js`: a `refreshSecretsCache` that sets `_secretsLoaded` (beside `:380-389`, `:561`);
- `studio.js:48-55`: the loaded flags;
- `agent-editor-controller.js:295-299`: pass `secretsLoaded`, `allSecrets` and `onChange`;
- `agent-editor.js:91-125`: build a third host and section **before** `mcpSection`, and add the secrets handle to the composite's `setAgent(a, opts)` (with the refreshed list) and `destroy`. Today the composite's `setAgent` calls only the built-in handle; add the secrets one explicitly.
- `agents-list.js:391` refresh, and its comment at `:384` (the server-preserved fields list gains `secret_ids`);
- `agent-form-data.js`: the root marker `[data-testid="agent-tools-secrets-section"] [data-secret-list-loaded="true"]` (or on the section root) and the toggle selector `[data-secret-toggle][data-secret-id]:checked`;
- the toggles call `onChange` themselves (the field-level listener sweep doesn't see library inputs, `knowledge-tab.js` header);
- "open-and-close stays clean" compares the collected `secret_ids` with `agent.secret_ids`.

**Drawer (B3).**
- `agent-drawer.js:108` `STORES` gains `'secrets'`.
- The group goes **between MCP servers (`:568`) and Built-in tools (`:578`)**, and the header comment `:39` is updated.
- The `storeStatus` failure handling applies to the secrets group.

**Store invalidation.** A secret **delete** also invalidates `agents` (the server strips the id from agents). Every secret write invalidates `secrets`. The `store.js` header comment lists the new collection.

**`chipList` `suggest` (A1), decided:**
- **No reuse:** `search-list.js` owns its own input, and `menu.js` is `role=menu`. Copy `search-list.js`'s ARIA contract into `chip-list.js`:
  - `role=combobox` and `aria-autocomplete=list` on the existing `.chip-list-input`;
  - `aria-controls` to the listbox;
  - `aria-activedescendant` set and removed;
  - `mousedown` `preventDefault` on the listbox, so a click picks while the input keeps focus (pin it in WebKit);
  - `scrollIntoView({block: 'nearest'})` within the listbox only.

  Report "no reuse".
- **DOM:** the listbox and popover exist **only when `suggest` is set**. The root gains a `position: relative` modifier class only then, so the no-`suggest` DOM is unchanged byte for byte. New owned classes (e.g. `ui-chip-list-suggest`, `ui-chip-list-option`) go in the catalogue row at `docs/ui-control-inventory.md:110`.
- **Keys:** handled inside the existing `onKeydown` (no capture-phase listener):
  - with the popover open and an active option, Enter picks;
  - Tab and comma keep today's commit-the-typed-text behaviour;
  - Escape closes the popover and calls `stopPropagation` while it is open (so a parent modal or editor isn't closed), and does nothing extra when closed.
- **Picks** go through the existing `validate`/`addChips` path. Already-chosen values are never suggested.
- **Errors:** `chipList.setError` stays boolean. Messages render through the wrapping `App.ui.field(...).setError(text)`, as in the mockup.
- **The document-listener rule** is `tests/test_ui_guards.py:800-815` (unpaired `document.addEventListener` in `js/ui`). Blur-to-close with no document listener satisfies it.

**Editor details (A5-A7):**
- The values table testid is **`secret-kv-table`** (as in the mockup), not `secret-values`. Rows are `{id, key, value: '__MASKED__', _stored: '__MASKED__'}` with `storedKey: '_stored'` (`type: 'secret'` with no `maskedBy` is always masked, `key-value-table.js:197-200`). A key rename clears a value still equal to its mask, with the table's hint (`checkRename`). The key-follows-name rule is `table.setRow(0, {key: slug})` until the key input is edited (`s10-mockup.js:172-176`).
- **Empty allowed tools:** the server's message only (no client pre-check with duplicated wording). On `~new` the refusal appears after the first Create attempt, not on mount as in the mockup's static render.
- `["allowed_tools", i]` renders the server's message through the field.
- The editor uses the connector glue's reload-after-write path.
- `icons.js` is an allowed hand-written SVG string source; add the lucide `key` path there.

**Jump to moves to part A** (it shares the group-table work in A4): `jump-to.js:62` `COLLECTIONS` gains `'secrets'`, and `:63-67` gains `{kind: 'secret', collection: 'secrets', section: 'secrets', where: 'Library · Secret'}`, plus the router label so the announcement works. B5 is then already done in part A, and A9 includes the Jump to test.

**Prompts (B4):** the block goes between the tool-free notes block and the date blocks (`system-page.js:183-232`; update `blocks` and `fill` at `:218-232`), with testid `secrets-prompt-content`.

**Lanes:**
- `test_flow_studio_secrets.py` must be added to `library_pat` (`run-tests.sh:200`), or it falls into `agents`.
- `test_flow_agent_secrets.py` must be added to `agent_tabs_pat` (`:223`).
- `test_ui_chip_list_suggest.py` lands in `contracts-controls` automatically.
- The Jump to check goes in `test_flow_jump_to.py` (`shared`).
- Update the lane comments in `run-tests.sh` and CLAUDE.md's lane list (it names the explicit files of `library` and `agent-tabs`).
- `library` is at 83% of its budget. If the G2 gate shows it over 1.15x, re-budget it in that run per the CLAUDE.md quiet-host rule and record it, rather than splitting the lane now.

## Files Affected
See Outputs and the addendum.

## Citation Audit
Checked by the Flight Director on 2026-11-05 against `a03e06a5`:
- `library-pane.js:40-57`: `LIBRARY_GROUPS`, four entries with `testid`/`prefix`/`icon`. Verified.
- `router.js:89` (connectors `SECTIONS` create entry), `:447` (labels), `:479` (collection map). Verified.
- `jump-to.js:62-67`: `COLLECTIONS` and the group table. Verified.
- `agent-editor.js:91-125`: Tools tab (MCP section then Built-in). Verified at flight planning.
- `chip-list.js:37`: `App.ui.chipList`; handle `{el, input, values, setValues, setError, destroy}`. Verified.
- `key-value-table.js`: `setError(rowIndex, colKey, text)`, `storedKey`. Verified from its header.
- `icons.js`: no `key` icon. Verified.

# Leg: connection-and-sandbox-fields

**Status**: ready
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Build the MCP editor's Connection fields and Sandbox section from library controls, as DOM-built modules with handles, and move the controller's snapshot, collect and revert for those fields onto the handles. Then hand the string chip list over and delete `tools-form-helpers.js`. Along the way:
- the approved presentation items B3, A5, A10, A14, B4 and A17, and the field labels' share of A3;
- defect 7 (chip edits after Cancel are not tracked).

## Context
- **Flight decisions:**
  - DD4 (each surface leg moves its own fields onto handles, including the dirty wiring; keep every `mf-*` id and `data-field`);
  - DD7 (A3, A5, A10, A14, A17, B3, B4; ledger rows 3, 5, 10, 14, 17, 24, 25, 34);
  - DD9 (defect 7);
  - DD10 (what the old control gave for free; derived-relationship criteria);
  - DD11 (the chip-list handover; the legacy switch **stays until leg 07**).
- **Today's modules** (leg 02 split, leg 03 lifecycle):
  - **`mcp-connection-fields.js`:**
    - `renderConnectionFields(source, mcpTypes)` returns an HTML string: Name `mf-name`; Type `mf-type` (a select over `/api/mcp-sources/types`, with a hidden placeholder "Select a transport…" on create); Command `mf-command-runtime` (`mcp-command-runtime`); Custom command `mf-command` (`mcp-command-custom`, row `.mcp-command-custom-row`); Working Directory `mf-cwd`; Arguments (a `.chip-list-editor[data-field=args]` placeholder); the hint `small.form-hint.mcp-command-hint` (`mcp-command-hint`) under Arguments; URL `mf-url`;
    - visibility comes from `.mcp-stdio-only`, `.mcp-streamable-http-only` and `.is-hidden`;
    - `mountChipListEditors` replaces the two placeholders through `outerHTML = App.adminFormHelpers.renderChipListEditor(...)` (2 sinks), and `wireChipLists` wires them;
    - `applyStdioRuntimeSelection` and `applyTransportVisibility` toggle classes. The latter also swaps the env and headers title.
  - **`mcp-sandbox-fields.js`:** `renderSandboxSection(source, type)` returns the whole Sandbox section as a string: the `section-title`, "Allow network access" as the legacy `.tool-enable-switch` with a stacked label (`mf-sandbox-network-allowed`, default on for a new source), and Writable paths (a chip-list placeholder).
  - **`mcp-editor-shared.js`:** `STDIO_RUNTIME_OPTIONS` (labels and `hint` texts), `deriveStdioRuntimeSelection` and `lookupStdioRuntimeHint`.
  - **The controller** (`mcp-server-editor.js`, 798 lines) reads these fields with `querySelector` in `getFormSnapshot`, `collectFormData` (including the `npx -y` and `pipx run` split) and `revertEditorToSource`. The latter has 2 more sinks (`wrapper.innerHTML`, `wrapper3.innerHTML`) and re-mounts the chip lists with a no-op `onChange` (defect 7).
  - Through `attachStaticListeners`, `.field-input` and `.field-select` changes call `checkDirty`.
- **The four guarded `App.adminFormHelpers` reads** (DD11, Architect H2): the snapshot, collect, revert and mount sites, each `if (helpers && helpers.readChipListValue)`. Deleting the file before they are replaced fails silently: Save would send empty args and writable paths.
- **The type labels** come from the server: `the_one/interfaces/web/api.py::list_mcp_source_types` returns `{"value": "stdio", "label": "Stdio"}` and `{"value": "streamable-http", "label": "Streamable HTTP"}`. Only the MCP editor reads them (`mcp-glue.js` `MCP_TYPES`). B3's labels change there, the one place.
- **The library pieces:**
  - `App.ui.field` (label, hint, info, error handle);
  - `App.ui.textInput` and `App.ui.select`;
  - `App.ui.chipList` (`inputId`, `dataset`, the middle ellipsis through `util.middleEllipsis` with a 40-character budget; `valuesOf`, `setValues`, `onChange`);
  - `App.ui.toggle` (`label`, `hint`, `onChange`, the testid on the input);
  - `App.ui.section` (`title`, `layout: 'stack'`, `setTitle`).
- **Tests that read these fields** (code survey §6):
  - `tests/browser/test_flow_studio_mcp_editor.py` (lane `mcp`): many `[data-field=…]`, `.chip`, `.chip-remove`, `.mcp-command-custom-row`, `.mcp-stdio-only` and `.tool-enable-switch-track` selectors;
  - `tests/browser/test_flow_chiplist_label_resolver.py` (lane `shared`): `[data-field="args"].chip-list-editor .chip-list-input`, `label[for="mf-args"]`, `mf-sandbox-writable-paths`;
  - `tests/test_tools_form_helpers_assets.py`;
  - `tests/browser/test_ui_chip_list_contract.py`: its two legacy-parity tests at `:292` and `:385-397`;
  - `tests/_ui_guard_helpers.py` `FIELD_FOR_ID_HELPER_INDIRECTED`.

## Inputs
- Legs 03-05 landed. Leg 04 and leg 05 do not touch these files.
- The before set `m31-f5-before`, and the leg 03 set `m31-f5-l03` (identical to the before set).

## Outputs
- **`mcp-connection-fields.js`** becomes `App.studio.mcpEditor.connectionFields.create({source, mcpTypes, onChange, onTypeChange})`, which returns `{el, values(), setValues(source), setError(field, msg|null), focus(field), setType(type), destroy()}`:
  - **`values()`** is `{name, type, runtime, command, cwd, args, url}`, where `args` is the operator's chips only. `collectFormData` keeps the `npx -y` / `pipx run` prepend and the custom-command rule.
  - **`setValues(source)`** never fires `onChange`. It also calls `setType(source.type)`, so rows show and hide without a change event, as the old revert's explicit `applyTransportVisibility` did.
  - **Change reporting.** Text inputs report on `input` (typing marks the form dirty at once) and selects on `change`. A type change calls `onTypeChange(type)` as well as `onChange`. The controller fans it out to `connectionFields.setType`, `sandboxFields.setType` and `envHeaders.setType` (below). That includes today's re-sync of the Custom row when switching into stdio.
  - **Visibility** uses the `hidden` attribute on each `field.el`; the global `[hidden]` reset removes it from layout and from the accessibility tree. The marker classes `mcp-stdio-only` and `mcp-streamable-http-only` stay on the field elements as **plain markers with no CSS**, so `.first`-style locators survive. `is-hidden` is no longer used.
  - **DOM order:** Name, Type, Command (with its hint), Custom command, Working directory, Arguments, URL.
  - **The Type placeholder:** `App.ui.select` has no hidden-option flag, and leg 04 owns `field.js` this flight, so the module sets `option.hidden = true` on the `''` placeholder after `select()` returns (create mode only). A test checks the placeholder is absent from the open list.
  - the fields built with `App.ui.field`, `textInput`, `select` and `chipList`, keeping the ids (`mf-name`, `mf-type`, `mf-command-runtime`, `mf-command`, `mf-cwd`, `mf-args`, `mf-url`), the `data-field` values and the testids (`mcp-command-runtime`, `mcp-command-custom`, `mcp-command-hint`);
  - **A5:** the runtime hint is the Command field's own `App.ui.field` hint (muted body-sm, under Command, not under Arguments), in plain words. The new texts live in `STDIO_RUNTIME_OPTIONS`: no backticks, no "operator", "container" or "Fetched +". For example: uvx "Runs a Python package from PyPI, downloaded on first use. Put the package name in Arguments."; Other command "Runs the command exactly as you type it."; one for each option;
  - **B3:** plain option labels: "Python package (uvx)", "Node package (npx)", "Python package (pipx)", "Python module or script", "Node script", "Shell script", "Other command…". The type placeholder is "Choose how it connects". The Leg's design review may adjust the wording, as long as it stays plain;
  - **A3's field share:** "Working directory"; the Name placeholder "My MCP server";
  - **visibility:** the stdio-only and HTTP-only fields are shown and hidden through the handles (`setType`), never through `.is-hidden` classes on string rows;
  - **A17:** on create with no type chosen, only Name and Type show among the form fields. The env and headers section and the Sandbox section are hidden too, through each module's `setType('')`. The Connection section's title, the header and the create-mode Cancel remain;
  - **defect 7:** both chip lists report every change through `onChange`, after a Cancel too;
  - **B4:** long chips use the library's middle ellipsis, with the full value on hover and in the accessible name. Never retype the value into a `title` elsewhere.
- **`mcp-sandbox-fields.js`** becomes `App.studio.mcpEditor.sandboxFields.create({source, onChange})`, which returns `{el, values(), setValues(source), setType(type), destroy()}`:
  - an `App.ui.section({title: 'Sandbox', layout: 'stack', testid: 'mcp-sandbox-section'})`;
  - **`values()`** is `{networkAllowed, writablePaths}`. `setValues(source)` keeps the create-versus-stored distinction: on for a new source, `network_allowed === true` otherwise, and it never fires `onChange`;
  - the old label's "Network access enabled/disabled" `title` is dropped, as intended (A10's inline label replaces it);
  - **"Allow network access"** is an `App.ui.toggle` with its label inline (A10), id `mf-sandbox-network-allowed` and `data-field="sandbox-network-allowed"` on the input, and the hint "Needed for uvx, npx and pipx run on first use." The default stays on for a new source and the stored value otherwise;
  - Writable paths is a `chipList` (`inputId: 'mf-sandbox-writable-paths'`, `dataset: {field: 'sandbox-writable-paths', fieldType: 'array'}`).
- **`mcp-env-headers.js`** gains `setType(type)`, which owns what `applyTransportVisibility` did for that section:
  - the title swap ("Environment variables" or "Headers", read today from the `data-stdio-label` / `data-streamable-http-label` attributes);
  - hiding the section when the type is `''` (A17).

  The section's string markup gains `data-testid="mcp-env-headers-section"` for it. `applyTransportVisibility` is deleted.
- **`mcp-editor-lifecycle.js`** gains `mount.onDestroy(fn)`, a disposer list run once by `destroy`. Each module's `destroy()` registers there. The controller's returned keys stay `{destroy, setBusy, setError, runTest}` (`test_destroy_is_idempotent` pins them).
- **The controller:**
  - the Connection section's string keeps a host element for `connectionFields.el`, and the Sandbox section's string is replaced by a host for `sandboxFields.el`. Both are appended after the `container.innerHTML` mount;
  - **the dirty wiring:** the modules are created with a late-bound trampoline (`function () { if (checkDirtyFn) checkDirtyFn(); }`), because `checkDirty` is defined later in `wireEditorEvents`. `attachStaticListeners` excludes the module hosts, so no field gets a second listener. The initial snapshot fires no `onChange`;
  - **logic goes into the modules** (`values`, `setValues`, `setType`), not into the controller. **Target: the controller at 760 lines or fewer** after this leg (it is 798 now).
  - the handles go into the per-mount `handles` object;
  - `getFormSnapshot`, `collectFormData` (the `npx -y` and `pipx run` split unchanged) and `revertEditorToSource` read and write these fields through the handles;
  - the dirty wiring comes from the handles' `onChange`, not from `attachStaticListeners`' class selectors, so the toggle (`.ui-toggle-input`) marks the form dirty;
  - every `App.adminFormHelpers` read is gone, along with the two revert sinks;
  - `destroy()` of each module is called from the mount's `destroy`;
  - **the controller stays at 800 lines or fewer.** It loses its revert chip and snapshot code here, which leaves room.
- **The handover** (DD11, in this order):
  1. **A payload test, written first and passing on today's tree:** create and edit a stdio source with args (including `npx -y` and `pipx run`) and writable paths, then Save. The stored `config.args`, `config.command` and `config.sandbox.writable_paths` (read back through the API) are exactly what was entered. It must pass before, during and after the handover;
  2. replace the four guarded reads;
  3. delete `js/areas/admin/tools-form-helpers.js` and its `index.html` tag, with its rows everywhere: the `tools-form-helpers.js` ownership rows (`chip`, `chip-list-editor`, `chip-list-input`), their `TOTAL_USES` share and any `MOVES` rows, and any `HTML_SINK_ALLOWANCE` row. Update the comment at `js/ui/chip-list.js:9` and the `the_one/agents.md` mentions (about `:2111`, `:2169`, `:2171`, `:2311`);
  4. invert `tests/test_tools_form_helpers_assets.py` into "the file is gone and `index.html` does not reference it";
  5. retire or freeze, with a reason, the two legacy-parity tests in `test_ui_chip_list_contract.py` (the `_legacy_tool_css.py` precedent);
  6. delete the `studio.css` `:not(.ui-chip-list)` chip-list rules (about `:1343-1404`) and their 5 allowance keys (`chip`, `chip-list-editor`, `chip-list-input`, `ui-chip-list`, `ui-chip-list-input` in `css/studio.css`);
  7. update `FIELD_FOR_ID_HELPER_INDIRECTED` (or drop the two entries if the ids are now emitted by `chipList`'s `inputId`, and the guard sees them);
  8. **the legacy switch's CSS stays** for leg 07 (the Sensitive switch).
- **`the_one/interfaces/web/api.py::list_mcp_source_types`:** the labels "Local program (stdio)" and "Remote server (HTTP)". The existing route test at `tests/test_db_api.py:3568-3573` gains exact-label equality.
- **`scripts/ui_capture.py`:** check its MCP selectors still work (`#mf-name`, `#mf-type`, `.chip-list-editor .chip`, and the string-path overrides around `:342-348`, `:900`, `:1082`, `:1203-1255`), and update any that broke, so the leg's own capture run works.
- **Guards:**
  - the sinks in `mcp-connection-fields.js` (2) and the controller's 2 revert sinks are removed, with `SINK_TOTAL`, `SINK_MOVES` and `SNIPPET_MOVES` lowered;
  - every ownership use these modules held is removed, and `TOTAL_USES` and `MOVES` are lowered;
  - no new use.
- **Ledger and captures:**
  - retake the MCP surfaces into `m31-f5-l06` and compare with `m31-f5-l03`;
  - every difference maps to rows 3 (labels), 5, 10, 14, 17, 24, 25 or 34; anything else is a defect;
  - the 1024 surfaces are included.
- **Tests** (lane `mcp`, plus `shared` by file):
  - **retargeted pins** in `tests/browser/test_flow_studio_mcp_editor.py`, each rewritten to the new idiom, never deleted:
    - the roughly 15 `is-hidden` class assertions on `.mcp-stdio-only`, `.mcp-streamable-http-only`, `.mcp-command-custom-row` and the sandbox section (about `:286-296`, `:346-380`, `:1654-1883`) become `to_be_hidden()` / `to_be_visible()`;
    - `.kv-section-title`'s text (about `:280-300`) keeps working through `envHeaders.setType`;
    - `.tool-enable-switch-track` for network becomes the switch's role or input;
    - `.chip-remove` becomes `.ui-chip-remove` or `chipList.valuesOf`. The computed-colour pin at about `:444` is re-derived for the library's muted ×, which is A14's ledger change;
    - the hint text assertions at about `:1658-1679` follow A5's new texts;
    - the sandbox Cancel test (about `:590-620`) keeps `uncheck()` on the switch, which works because the toggle input stays a real checkbox;
    - `test_flow_studio_library_focus.py:105`, `test_flow_studio_library_list.py:437` and `test_router_announce.py:299` use `data-field` only and should pass unchanged;
  - **the payload tests**, named `test_payload_*` so `-k payload` selects them, extending the existing pipx-run create test (about `:1690`) and the `_seed_mcp_source` helper (`:40`):
    - create stdio with `npx -y`, a user arg and a writable path;
    - create with `pipx run`;
    - edit a seeded `npx -y` source with args `['-y','pkg','--flag']`, change only the name, and assert that `config.args` is unchanged;
    - edit and add a chip;
    - an "Other command…" source;
  - **a stored `network_allowed: false`:** Cancel after toggling returns it to off;
  - **defect 7, test first:** edit, Cancel, then remove a chip; Save is enabled and the caption shows;
  - **B3/A5 derived relationships:**
    - each runtime option's hint matches its option;
    - the hint is linked to the Command field through `aria-describedby`;
    - the hint never contains a backtick;
  - **A17:** on create with no type chosen, the editor's form fields in the accessibility tree are only Name and Type (`get_by_role` counts for textbox and combobox, scoped to the editor; headers and buttons are present and not counted);
  - **A10:** the network control is `role=switch`, named "Allow network access", with its label inline, and toggling it marks the form dirty;
  - **what the old control gave for free** (DD10), each kept and tested:
    - the chip input's Enter, comma, paste-split and Backspace behaviour (from `chipList`; spot-check one per list);
    - the `<select>` typeahead (native);
    - the checkbox's Space key on the switch.

## Acceptance Criteria
- [ ] **The payload test** (args with the `npx -y` and `pipx run` splits, writable paths and command) passes on the leg 05 tree before any change, and after the handover.
- [ ] **No string-built field left:** `git grep -n "adminFormHelpers\|tools-form-helpers\|renderChipListEditor" the_one/interfaces/web/static/` finds nothing; `mcp-connection-fields.js` and `mcp-sandbox-fields.js` have zero sinks and zero allowance rows.
- [ ] **Defect 7** is fixed, test first.
- [ ] **The approved items show as specified,** each with its test:
  - B3's type and runtime labels (server and client);
  - A5's hint, under Command and linked;
  - A10's switch, inline;
  - A14's library chips (the muted ×);
  - B4's ellipsis;
  - A17's hidden sections;
  - A3's field labels.
- [ ] **The captures differ only on the listed ledger rows** (FD-checked against the ledger, with each difference judged against its row).
- [ ] **Lanes and files pass:** `mcp`, `library`; `test_flow_chiplist_label_resolver.py` and `test_ui_chip_list_contract.py` (both engines, `THE_ONE_REQUIRE_WEBKIT=1`); `test_studio_mcps_tab.py`; the unit tier (including the inverted asset test and the route test).
- [ ] **Guards:** the sink and ownership totals are lowered; the move tables are lowered or stale entries removed (nothing stale); every `mcp-*.js` file is 800 lines or fewer; the static JS/CSS guards pass; `make test-unit` passes.

## Verification Steps
- The payload test, run first on the unchanged tree: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_studio_mcp_editor.py -k payload -x --timeout 60`.
- `git grep` as in the acceptance criteria. For each deleted class (`chip-list-editor:not`, `tool-enable-switch` stays), grep `tests/` and run the lane that owns each hit (DD10).
- The lanes and files above, at most 3 at a time.
- The capture compare against `m31-f5-l03`.
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_area_module_size.py tests/test_store_static.py tests/test_tools_form_helpers_assets.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py -q -x --timeout 120`, then `make test-unit`.

## Implementation Guidance
1. **Tests first:** the payload test (it must pass now), and the defect 7 test (it must fail now).
2. **`connectionFields.create`,** with the A5 and B3 texts in `mcp-editor-shared.js` and the server labels.
3. **`sandboxFields.create`.**
4. **The controller:** the hosts, the handles, and snapshot, collect and revert through the handles; the dirty wiring from `onChange`; A17 through `setType`.
5. **The handover,** in the order listed. Re-run the payload test after each step.
6. **The guards, the lanes, the captures and the ledger.**

## Edge Cases
- **The `npx -y` and `pipx run` splits** round-trip on hydrate, on collect and on Cancel.
- **A source whose saved command matches no runtime** shows "Other command…" with the raw command in the custom field.
- **Switching the type with args entered** keeps the args (today's behaviour) and keeps env rows (leg 07's concern).
- **Create mode** with the default runtime (`uvx`) and the network default (on).
- **A 90-character argument and an 87-character path** (the capture seed) are the B4 case.
- **The chip-list label resolver test** needs `label[for="mf-args"]` to target the real input. `chipList`'s `inputId` does that.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-fields.js`, `mcp-sandbox-fields.js`, `mcp-editor-shared.js`, `mcp-server-editor.js`; `js/areas/admin/tools-form-helpers.js` (deleted); `static/index.html`; `css/studio.css`.
- `the_one/interfaces/web/api.py` (`list_mcp_source_types`) and its unit test (the existing MCP API test file, or a new `tests/test_mcp_source_types_route.py`).
- `tests/browser/test_flow_studio_mcp_editor.py`, `test_flow_chiplist_label_resolver.py` (if needed), `test_ui_chip_list_contract.py`; `tests/test_tools_form_helpers_assets.py`; `tests/_ui_guard_helpers.py`; `tests/_ui_ownership_allowance.py`; `tests/test_ui_guards.py`.
- `docs/ui-control-inventory.md` (the chip-list row's legacy note); the flight log and ledger.

## Citation Audit
- **Module contents:** read by the FD on the leg 03 tree (2026-10-25). `list_mcp_source_types` at `api.py:3071-3084`. `chipList` `inputId` and `middleEllipsis` at `js/ui/chip-list.js:16, :54, :72`.
- **DD11's handover lines** (`studio.css:1343-1404`, `test_ui_chip_list_contract.py:292, :385-397`): from the code survey. Re-check at the start, because `studio.css` comments moved in leg 02.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes**, applied in place:
  - the `is-hidden` pins and the other test rewrites named, with the `hidden` idiom and the plain marker classes kept (H1);
  - the env and headers title swap and the A17 hide in `envHeaders.setType`, with a section testid (H2);
  - the `values()` and `setValues()` shapes, and the `onTypeChange` fan-out (H3);
  - the 760-line target, with logic in the modules (M4);
  - the dirty trampoline, the excluded hosts and `mount.onDestroy` (M5);
  - the select placeholder set in the module (M6);
  - every handover row (M7); the named payload tests (M8);
  - the low items: DOM order, the network Cancel test, `setValues` calling `setType`, the dropped `title`, the `test_db_api.py` label test, the A17 scope, the capture tool's selectors.

  These are clarifications and decisions within the design, so there is no second cycle. Status `ready`.

# Leg: 05b-stdio-editor-sandbox-section

**Status**: completed
**Flight**: [Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend](../flight.md)

## Objective

Add a "Sandbox" sub-section to `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` that surfaces the F3 sandbox profile fields in the Studio MCP server editor for **stdio mode only**: a `network_allowed` checkbox and a `writable_paths` chip-list. Save round-trip writes `config.sandbox = {"network_allowed": <bool>, "writable_paths": [...]}` (matching L1b's API validator and L2's `SandboxProfile.from_dict` contract). Cancel-revert and dirty-tracking participate in the existing edit-form lifecycle. Streamable-http transport gets NO sandbox section (no local process to sandbox). Cover with ~10 browser tests in `tests/browser/test_flow_studio_mcp_editor.py` (extending the existing F1 L6 test file): 7 base render/save/edit/defaults tests + 3 design-review-required dirty-tracking and cancel-revert tests.

## Context

- **UI-only leg.** No Python source changes; no API changes; no test fixture additions. Just JavaScript + Playwright browser tests. The API validator (`_validate_mcp_source_config` for `config.sandbox`, L1b) and the runtime side (`SandboxProfile.from_dict`, `BubblewrapSandbox`, L2-L4) are already in place. L5b lands the operator-facing surface.
- **Stdio mode only.** Per flight §5, the Sandbox section appears ONLY when `type=stdio`. Streamable-http doesn't spawn local processes, so `config.sandbox` on a streamable-http source is meaningless. Apply the existing `mcp-stdio-only` CSS class (already used by command/cwd/args/env fields) so the section auto-hides when the type dropdown switches to streamable-http.
- **Field layout (per flight §5):**
  - `Allow network access` checkbox — operator opts in to network. Default unchecked (matching `network_allowed=False` strict-floor).
  - `Writable paths` chip-list — operator-configured list of absolute paths the sandbox grants read+write access to. Default empty list. Reuses `App.adminFormHelpers.renderChipListEditor` per existing pattern (the editor's `args` and `oauth-scopes` fields already use it).
  - **No** UI for namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`) per flight §12 — those are JSON-edit-only via the API for advanced use cases. The L5b form does NOT expose them.
- **Save contract.** When the operator saves the form, the JS code must produce a `config.sandbox` sub-object that matches L1b's API validator shape:
  - `config.sandbox = { network_allowed: <bool>, writable_paths: [<str>, ...] }`
  - Both fields always written (never omitted). When the operator leaves the section default (unchecked + empty list), the saved value is `{ network_allowed: false, writable_paths: [] }`. **Always-emit precedent**: the existing `collectFormData` already always-emits `config.env = {}` and `config.headers = {}` (rather than omitting them when empty). Sandbox follows the same pattern. The L1b API validator accepts empty/default values gracefully (per L1b's `test_validation_accepts_stdio_config_empty_sandbox_dict`).
  - **Streamable-http**: never emit `config.sandbox`. The form-state collector emits the sandbox sub-object ONLY inside the `type === 'stdio'` branch.
- **Edit (load) round-trip.** When loading an existing source for edit, populate the fields from `source.config.sandbox`:
  - `network_allowed` checkbox: `source.config.sandbox?.network_allowed === true` (default false if missing — matches L2's `from_dict` strict-floor).
  - `writable_paths` chip-list: `source.config.sandbox?.writable_paths || []` (default empty if missing).
- **Cancel-revert.** Per design review, `revertEditorToSource` uses an explicit `staticMap` keyed by `data-field` value (NOT generic) AND has explicit per-chip-list re-mount blocks for `args` and `oauth-scopes`. **L5b MUST extend `staticMap`** with the sandbox checkbox AND add a third chip-list re-mount block for `sandbox-writable-paths`, mirroring the existing patterns.
- **Dirty-tracking.** Per design review, `getFormSnapshot` uses an explicit `staticFields` whitelist (NOT generic). **L5b MUST extend `staticFields`** with `sandbox-network-allowed` AND add a `chips` snapshot entry for `sandbox-writable-paths`. Note that checkboxes need `el.checked` not `el.value` — adjust snapshot logic if it currently only reads `el.value`. `attachStaticListeners` selects `.field-input` and `.field-select`; the sandbox checkbox must either get `class="field-input"` (semantically odd but works) OR have an explicit `change` listener wired in `wireEditorEvents`.
- **Chip-list dirty-tracking** is auto-handled by `wireChipLists(container, checkDirty)` which walks all `.chip-list-editor` elements generically; no extension needed for the new chip-list. The `wireChipLists` re-call after revert IS needed (already in revert flow per the existing code).
- **Data-field naming convention.** Per design review: existing fields use **flat kebab-cased** values (`oauth-issuer-url`, `oauth-scopes`, `oauth-client-id`) — NEVER dotted paths. Use `data-field="sandbox-network-allowed"` and `data-field="sandbox-writable-paths"` for consistency. The mapping to nested `config.sandbox.<field>` happens in `collectFormData`, NOT in the DOM attribute.
- **Chip-list helper API.** Per design review: the actual extraction API is `helpers.readChipListValue(host)` taking the host element (NOT `extractChipListValues(name)`). Mirror the `argsList` extraction pattern: `var sandboxPathsList = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor'); var writablePaths = helpers.readChipListValue(sandboxPathsList);`.
- **CSS / design language.** No new CSS. Use the existing `<div class="editor-section">` + `<div class="section-title">Sandbox</div>` pattern (precedent: OAuth Client Configuration block in the same file; provider-editor.js; general-tab.js). **Do NOT introduce `<fieldset>`/`<legend>`** — neither tag is used anywhere in the codebase. The new section is a peer to Connection / Environment / OAuth (visually separated, auto-hidden for streamable-http via the existing `mcp-stdio-only` class on the section root).
- **Browser test file**: extend the existing `tests/browser/test_flow_studio_mcp_editor.py` (F1 L6) — don't create a parallel file. The existing tests are the right neighbours for "save round-trip", "edit round-trip", "empty defaults". Add 6-8 new tests that focus specifically on the sandbox section's behaviour.
- **Per-leg lint gate.** No Python source changes; ruff is essentially a no-op for this leg (only verify nothing else regressed). The JS file should follow the existing style — vanilla JS, no new dependencies, no ES6+ syntax that wasn't already in use.
- **Citation style**: anchor by symbol-name. The editor's existing functions (`renderTransportSpecificFields`, `mountChipListEditors`, `collectFormState`, `applyFormState`, etc.) are the integration points; L5b extends their content, not their structure.

## Inputs

- L1a, L1b, L2, L3, L4, L5a all `completed`. The full F3 sandbox stack is operational.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` exists per F1; renders the editor form, handles transport-type switching via CSS class toggles (`mcp-stdio-only` / `mcp-streamable-http-only`), uses `App.adminFormHelpers.renderChipListEditor` for `args` and `oauth-scopes` chip-lists.
- F1's `_validate_mcp_source_config` accepts `config.sandbox` per L1b; rejects malformed shapes with 422.
- `tests/browser/test_flow_studio_mcp_editor.py` exists per F1 L6 with browser tests covering create / edit / save / cancel flows for the editor.
- Playwright + the dev container's MCP server admin UI are operational (per F1 L6).
- F3 contracts in CLAUDE.md / agents.md (L1b) describe the sandbox profile shape; L5b's UI must match.

## Outputs

- **`the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` extended**:
  - `renderConnectionFields(source, isCreate)` (the actual function that renders stdio fields) gains a new sibling "Sandbox" `<div class="editor-section mcp-stdio-only">` block after the stdio-mode fields. The section uses the existing `mcp-stdio-only` CSS class so it auto-hides for streamable-http.
  - Two new fields (flat kebab-case `data-field` per existing OAuth/args convention — NOT dotted paths):
    - `<input type="checkbox" class="field-input" id="mf-sandbox-network-allowed" data-field="sandbox-network-allowed" />` with label "Allow network access".
    - `<div class="chip-list-editor" data-field="sandbox-writable-paths" data-field-type="array"></div>` with label "Writable paths".
  - The post-innerHTML chip-list mount block (where `args` and `oauth-scopes` are mounted via `helpers.renderChipListEditor`) gains a third call for `sandbox-writable-paths`.
  - `collectFormData` (the function that serializes the form to a JSON payload for save) gains logic INSIDE the `type === 'stdio'` branch to assemble `config.sandbox = { network_allowed, writable_paths }`, mirroring the `argsList` extraction pattern (using `helpers.readChipListValue(host)`). For streamable-http sources, `config.sandbox` is NOT emitted.
  - `getFormSnapshot` (form-state snapshot for dirty-tracking) extended: `staticFields` array gains `sandbox-network-allowed`; `chips` snapshot dict gains `sandbox-writable-paths`. The snapshot helper must read `el.checked` (not `el.value`) for the checkbox.
  - `revertEditorToSource` (cancel-revert) extended: `staticMap` gains `sandbox-network-allowed`; a third chip-list re-mount block is added for `sandbox-writable-paths`. The revert loop must set `el.checked` (not `el.value`) when the field is the sandbox checkbox.
  - `attachStaticListeners` requires NO change — it selects `.field-input` which the new checkbox carries; `change` events propagate.

- **`tests/browser/test_flow_studio_mcp_editor.py` extended** with ~7 new tests:
  1. `test_sandbox_section_renders_for_stdio_mode` — open the editor in create mode, select `stdio` transport, assert the Sandbox section is visible (`network_allowed` checkbox + `writable_paths` chip-list both present).
  2. `test_sandbox_section_hidden_for_streamable_http_mode` — open the editor in create mode, select `streamable-http` transport, assert the Sandbox section is NOT visible.
  3. `test_sandbox_section_visibility_toggles_on_transport_switch` — start with `stdio`, switch to `streamable-http`, assert section hides; switch back, assert section reappears.
  4. `test_sandbox_save_round_trip` — create a new stdio source with `network_allowed=true` + `writable_paths=["/data", "/cache"]`; save; verify via API GET that the persisted source has `config.sandbox = {network_allowed: true, writable_paths: ["/data", "/cache"]}`.
  5. `test_sandbox_edit_round_trip_populates_fields` — pre-create (via API POST or seeder) a source with `config.sandbox = {network_allowed: true, writable_paths: ["/x"]}`; open in edit mode; assert the checkbox is checked AND the chip-list contains "/x".
  6. `test_sandbox_empty_defaults_for_new_stdio_source` — open the editor in create mode for stdio; assert checkbox is unchecked; assert chip-list is empty (no chips).
  7. `test_sandbox_save_emits_explicit_defaults` — create a new stdio source WITHOUT touching the Sandbox section (defaults: unchecked, empty); save; verify via API GET that the persisted `config.sandbox = {network_allowed: false, writable_paths: []}` (explicit defaults emitted, NOT omitted).
  8. `test_sandbox_checkbox_toggle_marks_form_dirty` — toggle the checkbox, assert save button enables (or the dirty indicator fires).
  9. `test_sandbox_chip_add_remove_marks_form_dirty` — add a chip "/data", verify form is dirty; remove the chip, verify form remains dirty.
  10. `test_sandbox_cancel_revert_restores_state` — open existing source with `network_allowed=true` + `writable_paths=["/x"]`; toggle off and remove chip; click cancel; verify checkbox is checked again AND the chip-list contains "/x".

  Total: ~10 new browser tests. All use the existing F1 L6 test conventions (page fixture, helpers, etc.). Mark `pytest.mark.browser` per the file's existing convention.

- **Flight artifacts**:
  - `flight-log.md` gets `### L5b Stdio Editor Sandbox Section` under `## Leg Progress`.
  - `flight.md` checkbox ticked.
  - `legs/05b-...md` Status flipped to `completed`.

## Acceptance Criteria

- [ ] **Sandbox section renders for stdio mode**: when the editor's transport-type is `stdio`, the section displays a `Allow network access` checkbox and a `Writable paths` chip-list. Verifiable via Playwright DOM query.
- [ ] **Sandbox section hidden for streamable-http mode**: when transport is `streamable-http`, the section is not visible (CSS `is-hidden` class applied via `mcp-stdio-only` mechanism).
- [ ] **Save round-trip writes correct shape**: a stdio source with `network_allowed=true` + `writable_paths=["/data"]` saved via the editor produces, on subsequent API GET, `config.sandbox = {"network_allowed": true, "writable_paths": ["/data"]}`. The API validator (L1b) accepts the payload.
- [ ] **Edit round-trip populates correctly**: opening an existing stdio source whose `config.sandbox` has set values populates the checkbox and chip-list correctly.
- [ ] **Empty defaults for new stdio source**: opening the editor in create mode for stdio shows unchecked checkbox + empty chip-list.
- [ ] **Empty defaults emit explicit `config.sandbox = {network_allowed: false, writable_paths: []}` on save** (NOT omitted). Symmetry: reload of the saved source repopulates the form identically.
- [ ] **No `config.sandbox` emitted for streamable-http**: a streamable-http source saved via the editor produces a `config` JSON without a `sandbox` key. Verifiable via API GET.
- [ ] **Cancel-revert preserves sandbox state**: edits to the Sandbox section are reverted on cancel (existing cancel-revert mechanism covers the new fields).
- [ ] **Dirty-tracking covers sandbox edits**: toggling the checkbox or adding/removing chips marks the form dirty (existing dirty-confirm flow fires).
- [ ] **`tests/browser/test_flow_studio_mcp_editor.py` ~10 new tests pass** (7 base + 3 dirty-tracking/cancel-revert per design-review-required additions).
- [ ] **F1 L6 existing browser tests still pass** (no regression in the broader editor).
- [ ] **No Python source changes**: `git status --porcelain` shows no `the_one/*.py` modifications. Only the JS file + browser tests + flight artifacts.
- [ ] **Lint clean**: `ruff check the_one/ tests/` exits 0 (Python regression unaffected by JS changes).
- [ ] **No regression in F1/F2/L2/L3/L4/L5a test suites**.
- [ ] **Flight log + flight + leg-status updates** per the per-leg checklist.

## Verification Steps

```bash
cd ~/projects/the-one

# --- 1. Diff scope ---
git status --porcelain
# Expect modifications under:
#   the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js  (M)
#   tests/browser/test_flow_studio_mcp_editor.py                          (M)
#   missions/.../flight.md                                                 (M)
#   missions/.../flight-log.md                                             (M)
#   missions/.../legs/05b-...md                                            (M)

# --- 2. New L5b browser tests pass ---
docker compose exec -T the-one python -m pytest tests/browser/test_flow_studio_mcp_editor.py -v -m browser
# Expect: existing tests + ~7 new sandbox tests all pass.

# --- 3. F1/F2/L2/L3/L4/L5a regression ---
docker compose exec -T the-one python -m pytest \
    tests/test_db_api.py::TestMCPSourceAPI \
    tests/test_mcp_integration.py \
    tests/test_sandbox_contract.py \
    tests/test_sandbox_bubblewrap.py \
    tests/test_mcp_stdio_sandbox.py \
    tests/test_mcp_sandbox_integration.py -v
# Expect: all green.

# --- 4. Lint ---
docker compose exec -T the-one ruff check the_one/ tests/
# Expect: All checks passed.

# --- 5. Manual smoke: open editor, fill sandbox section, save, GET API ---
# (Manual: navigate to #studio/mcp-sources, click + Create, set transport=stdio,
#  fill Sandbox checkbox + chip-list, save, then GET /api/mcp-sources/{id}
#  and inspect config.sandbox)

# --- 6. Streamable-http source has no config.sandbox ---
docker compose exec -T the-one python -c "
# Verify via API: a streamable-http source created via the editor has no config.sandbox key.
# (or just verify with a manual smoke + curl + jq)
"
```

If any verification fails:
1. Capture failing output.
2. Diagnose: most likely (a) the existing form-state collector doesn't pick up nested `data-field="sandbox.network_allowed"` paths — flatten or use a custom collector for sandbox, (b) the chip-list mount fails because the editor's mount loop doesn't iterate the new field's `data-field` value — extend the mount function, (c) the cancel-revert mechanism doesn't handle nested sandbox state — add explicit handling.

## Implementation Guidance

1. **Read `mcp-server-editor.js` start-to-end** before editing. Key functions to locate:
   - The HTML render function (lines ~140-170 area, where command/cwd/args are emitted).
   - The chip-list mount function (lines ~280-300, where `App.adminFormHelpers.renderChipListEditor` is called for `args` and `oauth-scopes`).
   - The form-state collector (the function that builds the JSON payload for save).
   - The form-state applier (the function that loads an existing source's config into the form).

2. **Add the Sandbox section HTML** as a peer `<div class="editor-section mcp-stdio-only">` block (mirrors the OAuth section's structure). Place it after the stdio-mode fields block but before/after Environment as makes design sense. Use `data-field="sandbox-network-allowed"` and `data-field="sandbox-writable-paths"` (flat kebab-case — no dotted paths). Use `class="field-input"` on the checkbox so `attachStaticListeners` picks it up for dirty-tracking. Sketch:
   ```javascript
   // F3 L5b: stdio sandbox profile (network policy + writable paths)
   var sandbox = (!isCreate && source.config && source.config.sandbox) || {};
   var networkAllowed = sandbox.network_allowed === true;

   html += '<div class="editor-section mcp-stdio-only' + (stdioHidden ? ' is-hidden' : '') + '" data-testid="mcp-sandbox-section">';
   html += '<div class="section-title">Sandbox</div>';

   // Network allowed checkbox
   html += '<div class="field-row admin-pf-row">';
   html += '<label for="mf-sandbox-network-allowed">';
   html += '<input type="checkbox" class="field-input" id="mf-sandbox-network-allowed" data-field="sandbox-network-allowed"' + (networkAllowed ? ' checked' : '') + ' />';
   html += ' Allow network access';
   html += '</label>';
   html += '</div>';

   // Writable paths chip-list
   html += '<div class="field-row admin-pf-row">';
   html += '<label>Writable paths</label>';
   html += '<div class="chip-list-editor" data-field="sandbox-writable-paths" data-field-type="array"></div>';
   html += '</div>';

   html += '</div>';
   ```

3. **Mount the new chip-list** in the post-innerHTML mount function. Mirror the existing `args` / `oauth-scopes` pattern:
   ```javascript
   var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
   if (sandboxPathsHost) {
     var sandboxPaths = (source.config && source.config.sandbox && source.config.sandbox.writable_paths) || [];
     sandboxPathsHost.outerHTML = helpers.renderChipListEditor('sandbox-writable-paths', sandboxPaths, null, {});
   }
   ```

4. **Update `collectFormData`** to assemble `config.sandbox` for stdio sources only. Mirror the `argsList` pattern:
   ```javascript
   if (type === 'stdio') {
     // ... existing command/cwd/args extraction ...
     var sandboxNetEl = container.querySelector('[data-field="sandbox-network-allowed"]');
     var sandboxPathsList = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
     var networkAllowed = !!(sandboxNetEl && sandboxNetEl.checked);
     var writablePaths = sandboxPathsList ? helpers.readChipListValue(sandboxPathsList) : [];
     config.sandbox = { network_allowed: networkAllowed, writable_paths: writablePaths };
   }
   // Streamable-http: do NOT emit config.sandbox.
   ```

5. **Extend `getFormSnapshot`** (the form-state snapshot function used for dirty-tracking). The existing `staticFields` whitelist covers `name, type, command, cwd, url, oauth-issuer-url, oauth-client-id, oauth-redirect-uri, oauth-client-secret`. **Add `sandbox-network-allowed`** to the list. **Note**: the snapshot logic likely reads `el.value` for inputs; for the checkbox, read `el.checked` instead — adjust the snapshot helper to handle `type="checkbox"` correctly. **Also add a `chips` snapshot entry** for `sandbox-writable-paths` (mirroring `args` and `oauth-scopes` entries).

6. **Extend `revertEditorToSource`** (cancel-revert):
   - **Add to `staticMap`**: `'sandbox-network-allowed': (source.config && source.config.sandbox && source.config.sandbox.network_allowed === true)`. **CRITICAL**: the existing revert loop body uses `el.value = staticMap[key]` — for a checkbox, this would set `checkbox.value = true` (a no-op for the displayed checked state) instead of restoring the checked state. Either (a) special-case the loop to detect `el.type === 'checkbox'` and use `el.checked = staticMap[key]`, OR (b) pull the sandbox checkbox revert OUT of the loop with an explicit `if (el) el.checked = ...;` line. Option (b) is simpler and lower-risk — adopt it.
   - **Add a third chip-list re-mount block** for `sandbox-writable-paths`, mirroring the existing `args` and `oauth-scopes` re-mount blocks. After re-mount, the existing `wireChipLists(container, checkDirty)` re-call will pick it up automatically.

7. **`attachStaticListeners` change-event wiring**: the existing function selects `.field-input` and `.field-select` inside the editor and wires `change` listeners. The sandbox checkbox uses `class="field-input"` so it's picked up automatically — no change needed to `attachStaticListeners` itself.

8. **Write the ~7 browser tests** in `tests/browser/test_flow_studio_mcp_editor.py`. Style: extend the existing test class (or top-level functions) with new test methods. Use the existing fixtures for editor navigation and source seeding. Each test follows the pattern:
   - Navigate to the editor (create or edit mode).
   - Interact with the form (toggle checkbox, add chips, save, etc.).
   - Assert via DOM query OR via API GET (`page.request.get(...)` or equivalent).

   **Required cancel-revert and dirty-tracking tests** (per design review issue #2 + #6 — these were "optional" in the original sketch but are the highest-risk integration gaps):
   - `test_sandbox_checkbox_toggle_marks_form_dirty` — toggle the checkbox, assert save button enables (or dirty indicator fires).
   - `test_sandbox_chip_add_remove_marks_form_dirty` — add and remove a chip, assert dirty state.
   - `test_sandbox_cancel_revert_restores_checkbox_and_chips` — open existing source with non-default sandbox, edit both fields, click cancel, verify both fields restored.

9. **Run the full Verification Steps** before signalling `[HANDOFF:review-needed]`.

## Edge Cases

- **`source.config.sandbox` is missing on edit-load**: treat as `{}` and apply defaults (unchecked checkbox, empty chip-list). Already covered by the `(!isCreate && source.config && source.config.sandbox) || {}` defensive read.
- **`source.config.sandbox.writable_paths` is `null`**: treat as empty array. Defensive read with `Array.isArray(...)` check.
- **Operator submits `network_allowed` as a string `"true"` via direct form manipulation**: the L1b API validator rejects with 422 (per its `isinstance(value, bool)` check). Browser test doesn't need to cover this — that's an API-level contract.
- **Operator adds an empty string chip**: the chip-list helper most likely filters empty strings; if not, the API validator accepts a `list[str]` of any contents (including empty strings). The bwrap runtime would fail at `--bind '' ''`. Operator's responsibility per "trust the runtime."
- **Transport type switched mid-edit**: existing editor logic toggles the `mcp-stdio-only` / `mcp-streamable-http-only` classes; the Sandbox section's visibility follows automatically. State preservation: the operator's sandbox values are preserved in the DOM but won't be saved if the final type is streamable-http (per the form-state collector's stdio-only emit). Acceptable per the design.
- **Reading `config.sandbox` from a legacy source created before L1b**: the field is missing from the JSON; defaults apply. No migration needed.
- **Form layout in narrow viewports**: the chip-list and checkbox should stack vertically per the existing `field-row` flex/grid layout. No new CSS needed.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — extend with Sandbox sub-section render, chip-list mount, form-state collector + applier updates.
- `tests/browser/test_flow_studio_mcp_editor.py` — add ~7 new browser tests.
- `missions/.../flight-log.md` — append `### L5b Stdio Editor Sandbox Section`.
- `missions/.../flight.md` — tick L5b checkbox.
- `missions/.../legs/05b-stdio-editor-sandbox-section.md` — flip Status.

**Explicitly NOT modified**: any Python source under `the_one/`, any test under `tests/` outside `tests/browser/test_flow_studio_mcp_editor.py`, CSS files, the API layer (L1b done), the runtime (L2-L4 done), the integration tests (L5a done), Dockerfile, docker-compose.yml, Makefile, pyproject.toml, CLAUDE.md, agents.md.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Sandbox section renders for stdio mode; hidden for streamable-http
- [ ] Save round-trip writes correct `config.sandbox` shape
- [ ] Edit round-trip populates fields correctly
- [ ] Empty defaults emitted explicitly on save
- [ ] Cancel-revert + dirty-tracking handle the new fields
- [ ] ~7 new browser tests pass
- [ ] F1 L6 existing tests still pass
- [ ] No Python source changes
- [ ] Lint clean
- [ ] Update flight-log.md with `### L5b Stdio Editor Sandbox Section`
- [ ] Set leg status to `completed`
- [ ] Tick L5b in flight.md
- [ ] **Do NOT commit** — agentic-workflow batches at flight end

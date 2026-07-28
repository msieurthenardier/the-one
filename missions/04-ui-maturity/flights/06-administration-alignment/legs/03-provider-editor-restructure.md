# Leg: 03-provider-editor-restructure

**Status**: completed
**Flight**: [Administration Alignment](../flight.md)

## Objective

Restructure the LLM-Provider editor onto the F5 agent-editor's canonical shape: replace the `.admin-header` + `.admin-title` heading with `.editor-header` (provider name as title; `{type} · {base_url}` as subtitle when editing) plus a right-aligned `.form-actions` cluster `[← Back] [Cancel] [Save | Create] [Test]`. Convert the long form into linear `.editor-section` blocks (Connection, Models, Danger Zone). Lift `.danger-zone` / `.danger-zone-title` from `studio.css` to `components.css`. Lift `.admin-pf-password-wrap` / `.admin-pf-eye` to canonical `.api-key-wrap` / `.api-key-eye` and migrate the test-result spans to the canonical `.test-result` / `.test-result-ok` / `.test-result-fail` family (introducing `.test-result-pending` for the spinning state). Wire Save and Cancel to use the `disabled` attribute as the single source of truth (mirrors F5 leg 04 pattern; full dirty-tracking lands in leg 04). Split the editor + Ollama-lifecycle code out of `admin.js` into two new sub-modules (`provider-editor.js`, `provider-models.js`).

The Danger-Zone Delete uses an inline two-step confirm flow in this leg (matches studio's `.delete-btn.confirm` pattern), wired to the `handleProviderDelete` scaffolding preserved by leg 02. The migration to `App.confirmDelete` (modal-based) is leg 04 territory.

## Context

This leg is the editor-surface counterpart to leg 02. Where leg 02 transformed the **list** view (tile grid + page-header + hash routing), leg 03 transforms the **detail** view to match the F5 agent-editor pattern users now expect.

Five concurrent changes:

1. **Editor scaffold restructure** — the existing `_renderProviderFormImpl` emits a flat `.admin-header` + `.admin-title` + .admin-provider-form > [field rows] + .admin-pf-actions [Cancel | Save | Test] block. Post-leg-03 the editor matches `agent-editor.js`'s shape:
   - `.editor-header` containing `.editor-header-text` (`<h1 class="editor-title">{name | "New Provider"}</h1>` + `<p class="editor-subtitle">{type} · {base_url}</p>` when editing) and `.form-actions` (`[← Back] [Cancel] [Save | Create] [Test]` + `<span class="editor-error"></span>`).
   - Three `.editor-section` blocks below the header: **Connection** (name + type + base_url + api_key fields + test-result span), **Models** (host div populated by `App.admin.renderProviderModels`), and **Danger Zone** (existing-provider only; `[Delete Provider]` button).

2. **Action cluster ordering + button shapes** — left-to-right: `[← Back]` (outlined-cyan, leftmost), `[Cancel]` (outlined-cyan), `[Save]` or `[Create]` (filled-cyan, primary), `[Test]` (outlined-cyan; rightmost; only when `provider.id` exists), with a trailing `<span class="editor-error">` slot. This mirrors `studio/agent-editor.js` lines 76-86 exactly. The user request was "back, cancel, save buttons like the studio agent page" + "test button in similar positions."

3. **Save / Cancel as disabled-SSoT** — both buttons start with `disabled` set on the element. Edit mode: a `checkDirty()` shim queries the form snapshot (mirrors studio.js:693-701) and flips both buttons. Create mode: the same shim runs but starts with `dirty=false` (snapshot of the empty form === current form), so Save/Cancel stay disabled until the user types. Back-button is always enabled.
   - **Note**: this leg installs the SSoT mechanism but its implementation is intentionally minimal — full dirty-tracking integration with `App.confirmDialog` (warning on Back when dirty) is **deferred to leg 04**, which will replicate the studio `doHandleBack` flow (studio.js:478-498). Leg 03 only wires the disabled flip on input/change events; Back without dirty-confirm dialog is acceptable for this leg.

4. **CSS canonicalization** — three lifts:
   - `.danger-zone` + `.danger-zone-title` move from `studio.css` line 60 (currently `.area-studio .danger-zone-title`) to `components.css` (un-scoped). Studio markup at `studio/general-tab.js:133-134` already uses bare `.danger-zone` / `.danger-zone-title` classes — only the CSS selector specificity changes. Admin's editor adopts the same bare classes.
   - `.admin-pf-password-wrap` → `.api-key-wrap` (rule moves from `admin.css:57-58` to `components.css`); `.admin-pf-eye` → `.api-key-eye` (rule moves from `admin.css:59-61` to `components.css`). Breaking rename — no aliases.
   - `.admin-pf-test-result` → `.test-result` (already canonical in `components.css:548-555`); `.admin-pf-testing` → NEW `.test-result-pending` rule in `components.css`; `.admin-pf-test-ok` → `.test-result-ok` (canonical); `.admin-pf-test-fail` → `.test-result-fail` (canonical). The four `.admin-pf-test*` rules in `admin.css:69-73` are deleted.

5. **Sub-module extraction** — `admin.js` post-leg-02 is 1117 LOC. Extracting the editor + Ollama lifecycle into two new sub-modules brings `admin.js` back near the post-leg-01 size (~1037 LOC) and matches the studio precedent (`studio.js` orchestrator + per-tab sub-modules):
   - **NEW** `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` — exports `App.admin.renderProviderEditor(container, provider, providerTypes, callbacks)`. Encapsulates the editor scaffold (header + sections + form fields + wiring). Receives the providerTypes array via callback param (the orchestrator's closure remains the source of truth).
   - **NEW** `the_one/interfaces/web/static/js/areas/admin/provider-models.js` — exports `App.admin.renderProviderModels(container, provider)` (top-level dispatch on `provider.type`) plus internal `renderOllamaModels(providerId, container)`, `wireOllamaActions(providerId, container)`, `ollamaAction(providerId, container, action, model, btn)` helpers. Encapsulates the Ollama lifecycle panel + the basic-model-list rendering for non-Ollama types. Pull / load / unload / per-model-delete logic moves verbatim.

Subsequent legs depend on this leg's foundations:
- **Leg 04** wires the dirty-state to `App.confirmDialog` (Back-with-unsaved-changes warning) — depends on the `checkDirty()` shim installed here. Leg 04 also migrates the Danger-Zone Delete from inline two-step (`.delete-btn.confirm`) to `App.confirmDelete` (modal-based; matches the F5 leg 05 pattern for studio's tile X-button → editor delete migration), and migrates the Ollama-model-row Delete from inline two-step (`.admin-pf-model-delete-confirm`) to `App.confirmDelete`.
- **Leg 05 (HAT)** verifies the entire restructure end-to-end against the user's six requirements + the F5/F6 design-system contract.

Key prior context:
- F5 leg 03 introduced the `.editor-header` + `.editor-header-text` + `.editor-title` + `.editor-subtitle` + `.form-actions` + `.editor-error` primitives in `components.css:496-543`, designed for "the agent editor's tablist (F5 leg 03) and any future entity-editor (admin's provider editor in F6)" (per the inline comment). Admin is the consumer this leg promised.
- F5 leg 03 introduced `.test-result` / `.test-result-ok` / `.test-result-fail` in `components.css:545-555` with the explicit comment "Admin's existing `.admin-pf-test-ok` / `.admin-pf-test-fail` will migrate here in F6." This leg fulfills that migration.
- F5 leg 04 established the `disabled`-as-SSoT pattern for Save and Cancel (both flipped together by `checkDirty()`; studio.js:693-701; studio.css:44-46 styles `.save-btn[disabled]` opacity hooks). Provider editor adopts the same pattern.
- F5 leg 05 moved the studio editor's Delete button OUT of the form-actions cluster and INTO a Danger Zone block at the bottom of the General tab. The Danger Zone is rendered conditionally (existing entity only) and uses `class="editor-section danger-zone"` + `class="section-title danger-zone-title"` markup. Admin's editor adopts the identical markup.
- F5 HAT leg removed the per-tile X-button on agent tiles (centralizing destruction in the editor). Provider tiles inherited the same shape in F6 leg 02 (no per-tile X-button); the Danger Zone in this leg is the only path to delete a provider from the UI.
- The F6 flight Open Question "migrate both editor Deletes to App.confirmDelete (option 1)" was answered yes; that migration is **leg 04** (this leg uses inline two-step as scaffolding so leg 04 has a single place to swap-in the modal).
- `handleProviderDelete` (admin.js:229-290) was preserved by leg 02 specifically as scaffolding for this leg + leg 04. Its agent-usage check (POST `/api/providers/{id}/agents` returning `{ agents: [...] }`) is reused; the inline-two-step UX wraps around it.
- The user's six F6 requirements explicitly call out the LLM-provider detail page mirroring the agent-edit page: "back, cancel, save buttons like the studio agent page" + "delete in a danger zone area" + "create flow modeled after create agent. with back, cancel, create, and the test button in similar positions." This leg implements those four requirements.

## Inputs

What exists before this leg runs (state at end of leg 02):

- `the_one/interfaces/web/static/js/areas/admin.js` (1117 LOC):
  - `serializeState`/`hydrateState` at lines 8-66 (already encodes/parses `#admin/providers/{id}` and `#admin/providers/new`; preserved verbatim).
  - `init` at line 68; closure-private state declarations at lines 73-95 (categories, currentCategory, providers, providerFormMode, editingProvider, pendingProviderId, pendingFormMode, PROVIDER_TYPES, providerTypesReady, fetchProviderTypes, TYPE_DEFAULTS).
  - `setCategory` at line 116-125; sidebar mount on `.admin-section-nav` child div at lines 114-130 (preserved).
  - `renderContent` at line 139-145 (preserved).
  - `renderProvidersPanel` at line 149-165 — has editor-vs-grid branching; **leg 03 keeps the branch but replaces the editor branch's `renderProviderForm(editingProvider)` call with a delegated call into `App.admin.renderProviderEditor(...)`**.
  - `fetchProviders` at line 167-179 (preserved); `populateProviderGrid` at line 184-191 (preserved); `selectProvider` at line 193-204 (preserved); `enterCreateMode` at line 206-215 (preserved); `findProvider` at line 217-223 (preserved).
  - `handleProviderDelete` at line 229-290 — the agent-usage check + inline-two-step body. **Leg 03 inlines this scaffolding into `provider-editor.js`'s Danger-Zone wiring; the function is removed from `admin.js`**. Test-id selector `.admin-provider-delete-confirm` (line 230, 266, 272, 280, 285) is renamed to `.delete-btn.confirm` to match studio's pattern, but the agent-usage hard-block branch (the `'Used by: ' + agentNames.join(...)` UX) is preserved verbatim.
  - `renderProviderForm` + `_renderProviderFormImpl` at lines 294-383 — **DELETED in leg 03**, replaced by `App.admin.renderProviderEditor` in `provider-editor.js`. The `providerTypesReady` gating wrapper (lines 297-300) is preserved by the new call site (`renderProvidersPanel` waits for `providerTypesReady` before delegating).
  - `wireProviderFormEvents` at lines 385-558 — **DELETED in leg 03**, body migrates into `provider-editor.js` (input change handlers, eye toggle, Cancel, Save, Test wiring). Re-uses `editingProvider` etc. via callback closure (no direct closure import; orchestration callbacks pass mutable state references).
  - `fetchProviderModels` at lines 562-604 — **DELETED in leg 03**, body migrates into `provider-models.js` as the basic-model-list branch.
  - `renderOllamaModels` at lines 610-942 — **DELETED in leg 03**, body migrates verbatim into `provider-models.js` (including `wireOllamaActions` at 944-989 and `ollamaAction` at 991-1021).
  - `showAdminFlash` at line 1025-1027 (preserved).
  - `escapeHtml` / `escapeAttr` references at lines 1031-1032 (preserved).
  - `_refresh` / Object.defineProperty descriptors / `_setCategory` / `_tryConsumePendingProvider` at lines 1034-1102 (preserved).
  - `fetchProviderTypes(); renderContent();` at lines 1106-1107 (preserved).
  - `activate` at lines 1110-1114 (preserved).

- `the_one/interfaces/web/static/css/admin.css` (127 LOC) post-leg-02 contains:
  - `.area-admin .admin-content` / `.admin-header` / `.admin-title` / `.admin-form` / `.admin-loading` / `.admin-note` / `.admin-section` / `.admin-field-*` / `.admin-placeholder*` (lines 3-19) — System page + editor surface chrome. **`.admin-header` and `.admin-title` are deleted** (the editor's heading moves to `.editor-header` + `.editor-title`; system-page already uses `.page-header` + `.page-title` post-leg-02). `.admin-form` and `.admin-section` may remain if other consumers exist (verify; if only the editor uses them, also delete).
  - `.area-admin .admin-environment-*` (lines 23-25), `.admin-system-*` (lines 28-43), `.admin-theme-*` (lines 40-44) — System page styling, **PRESERVED untouched**.
  - `.area-admin .admin-provider-badge` (line 47) + `.area-admin .admin-pf-model-delete.admin-pf-model-delete-confirm` (line 48) — **PRESERVED** (both still consumed: badge by tile + editor; model-delete-confirm by the Ollama row, leg 04 migrates).
  - `.admin-pf-input:focus-visible` / `.admin-pf-select:focus-visible` (line 51) — **PRESERVED** (still needed; the editor's input fields still use `.admin-pf-input` + `.admin-pf-select`; full rename to `.field-input` would be over-scope; leg 03 keeps these per-area focus-ring overrides).
  - `.admin-pf-eye:focus-visible, .admin-pf-cancel:focus-visible, .admin-pf-save:focus-visible, .admin-pf-test:focus-visible, .admin-pf-models-refresh:focus-visible` (line 52) — **MUTATED** to drop the renamed selectors and keep only the still-extant ones: post-leg-03 the rule covers `.admin-pf-models-refresh:focus-visible, .admin-pf-pull-go:focus-visible, .admin-pf-pull-cancel:focus-visible, .admin-pf-pull-btn:focus-visible, .admin-pf-model-btn:focus-visible` (the Ollama-lifecycle button family that remains under the `.admin-pf-*` namespace). The `.admin-pf-eye` focus is provided by canonical `.api-key-eye:focus-visible` in components.css. The `.admin-pf-cancel:focus-visible` / `.admin-pf-save:focus-visible` / `.admin-pf-test:focus-visible` are subsumed by `.cancel-btn:focus-visible` / `.save-btn:focus-visible` / `.test-provider-btn:focus-visible` rules, all of which already exist in studio.css and need lifting (see Outputs).
  - `.area-admin .admin-provider-form` (line 55) — **DELETED** (the wrapper `<div class="admin-provider-form">` is replaced by canonical sectioning; if a per-area form host class is needed for padding it gets renamed to `.provider-form`; see Outputs).
  - `.area-admin .admin-pf-cancel` (line 56), `.admin-pf-password-wrap` + nested rule (lines 57-58), `.admin-pf-eye` + variants (lines 59-61) — **DELETED** (`.admin-pf-cancel` is replaced by canonical `.cancel-btn`; `.admin-pf-password-wrap` lifts to canonical `.api-key-wrap`; `.admin-pf-eye` lifts to canonical `.api-key-eye`).
  - `.area-admin .admin-pf-actions` (line 62) — **DELETED** (the action cluster moves into `.editor-header` > `.form-actions`; the canonical `.form-actions` rule handles the layout).
  - `.area-admin .admin-pf-error` (line 63) — **DELETED** (the editor uses `<span class="editor-error">` from `.form-actions`; canonical `.editor-error` rule in components.css:540-543 styles it).
  - `.area-admin .admin-pf-test` + variants (lines 64-67) — **DELETED**. Replaced by lifting the studio-area `.test-provider-btn` rule (studio.css:49-50) to components.css (un-scoped) — the editor's Test button uses `class="btn-outlined-cyan test-provider-btn"`.
  - `.area-admin .admin-pf-test-result` / `.admin-pf-testing` / `.admin-pf-test-ok` / `.admin-pf-test-fail` (lines 70-73) — **DELETED**, replaced by canonical `.test-result` / `.test-result-pending` / `.test-result-ok` / `.test-result-fail` (existing components.css rules cover three of four; `.test-result-pending` is NEW).
  - `.area-admin .admin-pf-models*` and downstream Ollama-lifecycle rules (lines 76-118) — **PRESERVED** (the Ollama lifecycle UI keeps its existing `.admin-pf-*` classes; the per-area styling is acceptable given its scope and that lifecycle is unique to Ollama). Sub-module extraction does not require CSS lifts.
  - `.area-admin .admin-provider-badge--{type}` color rules (lines 121-126) — **PRESERVED** (composed onto tiles by the leg-02 grid sub-module + by the editor's subtitle line in this leg).

- `the_one/interfaces/web/static/css/studio.css` (66 LOC):
  - `.area-studio .studio-section-content` (line 6) — preserved untouched.
  - `.area-studio .studio-editor` (line 12), `.area-studio .editor-empty` (line 14), `.area-studio .tabpanel` (line 15), `.area-studio .editor-section` + nested `.editor-section + .editor-section` (lines 16-17), `.area-studio .field-input-short` (line 18), `.area-studio .field-model-wrap` (lines 19-20), `.area-studio .model-loading` (line 21), `.area-studio .test-provider-row` (line 23) — **PRESERVED** (studio-area-specific layout overrides; admin will define equivalents in admin.css for its provider editor where needed).
  - `.area-studio .save-btn` + variants (lines 44-46) — **LIFTED** to components.css (un-scoped). The `disabled` attribute is the SSoT pattern that admin's editor will share. The studio-area scoping was per-area only because no other consumer existed; this leg makes admin a consumer.
  - `.area-studio .back-btn` + nested `.back-btn svg` (lines 47-48) — **LIFTED** to components.css.
  - `.area-studio .test-provider-btn` + nested `.test-provider-btn svg` (lines 49-50) — **LIFTED** to components.css.
  - `.area-studio .delete-btn` + `.delete-btn.confirm` (lines 53-54) — **LIFTED** to components.css. Studio markup already uses the bare `.delete-btn` + `.delete-btn.confirm` classes (general-tab.js:135 + studio.js delete-handler). Admin adopts the identical class names.
  - `.area-studio .danger-zone-title` (line 60) — **LIFTED** to components.css. Add `.danger-zone` selector (currently absent — the studio markup uses `class="editor-section danger-zone"` but no rule targets `.danger-zone`; the spacing comes from `.editor-section + .editor-section`'s border-top in studio.css:17, which is per-area-scoped). Lift `.danger-zone` semantics to components.css with a top-border rule that doesn't depend on sibling positioning so admin's editor (where Danger Zone is the third section) gets it consistently.
  - `.area-studio .studio-vram-warning` (lines 64-65) — preserved untouched.

- `the_one/interfaces/web/static/css/components.css` (691 LOC) post-leg-02 contains:
  - `.section-title` + `::before` (lines 206-220) — **CONSUMED** by admin's three new editor sections (Connection / Models / Danger Zone use `<div class="section-title">{label}</div>`).
  - `.btn-outlined-cyan`, `.btn-filled-cyan`, `.btn-muted-destructive` (lines 222-268) — consumed by editor action cluster (`.back-btn` and `.cancel-btn` and `.test-provider-btn` use `.btn-outlined-cyan`; `.save-btn` uses `.btn-filled-cyan`; `.delete-btn` uses `.btn-muted-destructive`).
  - `.editor-header`, `.editor-header-text`, `.editor-title`, `.editor-subtitle` (lines 496-529) — consumed by admin editor's heading.
  - `.form-actions`, `.editor-error` (lines 531-543) — consumed by admin editor's action cluster.
  - `.test-result`, `.test-result-ok`, `.test-result-fail` (lines 545-555) — consumed by admin editor's Test result span.
  - **NO** existing `.danger-zone`, `.danger-zone-title`, `.api-key-wrap`, `.api-key-eye`, `.test-result-pending`, `.save-btn`, `.back-btn`, `.test-provider-btn`, `.delete-btn`, `.cancel-btn` rules — all introduced by this leg.

- `the_one/interfaces/web/static/js/areas/studio.js` lines 173-181 (page-header markup), lines 296-314 (tile markup), lines 478-498 (`doHandleBack`), lines 686-701 (`getFormSnapshot` + `checkDirty`), 765-836 (`save()` for create + edit), 837-842 (delete handler) — **SOURCE PATTERNS, NOT MUTATED** by this leg.

- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` (159 LOC) — the F5 leg 03 reference scaffold. Admin's `provider-editor.js` mirrors its structure (header + form-actions + sections); see Outputs for line-by-line correspondence.

- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` lines 129-150 — the Danger Zone reference markup + Delete handler (capital-D `'Confirm Delete?'` 3-second-revert). Admin's Danger Zone wiring mirrors it but adds the agent-usage hard-block branch (preserved from `handleProviderDelete`).

- `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` (90 LOC, leg 02) — preserved untouched. Its `selectedId` callback param is fed by `editingProvider.id` (orchestrator state).

- `the_one/interfaces/web/static/js/areas/admin/system-page.js` (157 LOC, leg 01-02) — preserved untouched.

- `the_one/interfaces/web/templates/{base|index}.html` — script tags load the admin sub-modules. The current template emits at lines 46-47 of one of these files:
  ```html
  <script src="/static/js/areas/admin/system-page.js"></script>
  <script src="/static/js/areas/admin/providers-grid.js"></script>
  ```
  Two **NEW** script tags must be added below these:
  ```html
  <script src="/static/js/areas/admin/provider-editor.js"></script>
  <script src="/static/js/areas/admin/provider-models.js"></script>
  ```

  **Step 1 of implementation must `grep -rn 'areas/admin/' the_one/interfaces/web/templates/`** to locate the exact template file (the F6-leg-02 implementation found a single template file; verify the same one). Add the two new script tags **after** providers-grid.js, **before** the closing of the script-loading section.

- `tests/browser/test_flow_provider_setup.py` references at lines 47, 54, 57:
  - line 47 — `expect(page.locator(".admin-title")).to_have_text("Edit Provider")` → **CHANGE**: assert against the new editor title, which is the **provider name** ("Mock Test"), not the static "Edit Provider" label. Replace with `expect(page.locator(".editor-title")).to_have_text("Mock Test")`.
  - line 54 — `expect(page.locator(".admin-pf-test-result")).to_contain_text("Mock", timeout=5000)` → **RENAME** selector to `.test-result`.
  - line 57 — `page.locator(".admin-pf-cancel").click()` → **RENAME** selector to `.cancel-btn` (or `[data-testid="cancel-provider-btn"]`).
  - **NOTE**: The test's flow ends with Cancel returning to the provider list. Post-leg-03 the Cancel button is **disabled when clean**; after a successful Test the form is still clean (no input changes). The test must use **Back** instead of Cancel to return to the grid in the clean-state scenario. Replace line 57 with `page.locator('[data-testid="back-provider-btn"]').click()`. The test docstring (line 8: "Edit it, click Test Connection, see success") must be updated to reflect the back-not-cancel exit path.

- `tests/browser/test_flow_provider_grid.py` references at lines 55, 56, 63, 65, 75, 93, 96, 103, 104, 116:
  - lines 55, 56 — comment + assertion `expect(page.locator(".admin-title")).to_have_text("Add Provider", timeout=5000)`. **CHANGE** assertion to `expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=5000)`. Update comment to "Editor opens (post-leg-03 uses .editor-title)."
  - line 63 — same `.admin-title` "Add Provider" assertion. Same change to `.editor-title` "New Provider".
  - line 65 — same `.admin-title` "Add Provider" assertion. Same change.
  - line 75 — `expect(page.locator(".admin-title")).to_have_text("Edit Provider", timeout=5000)` after `tile.click()`. The provider opened is the seeded `mock` provider from `seed_mock_provider` (default name "mock"). **CHANGE** to `expect(page.locator(".editor-title")).to_have_text("mock", timeout=5000)`.
  - line 93 — same as line 75. Same change.
  - line 96 — same `.admin-title` "Edit Provider" after page reload. Same change to `.editor-title` "mock".
  - line 103 — `.admin-title` "Add Provider" assertion. Same change.
  - line 104 — `page.locator(".admin-pf-cancel").click()` **inside the create-from-URL-refresh test**. In the create flow, no inputs were typed → form is clean → Cancel is disabled. **REPLACE** with `page.locator('[data-testid="back-provider-btn"]').click()` since Back is the way out of a clean editor.
  - line 116 — `fallback = page.locator(".area-admin .page-header, .admin-pf-error").first` — the fallback locator currently includes `.admin-pf-error` (used when an unknown id triggers an error toast). The error span moves to `.editor-error`. **CHANGE** to `.area-admin .page-header, .editor-error`.

- `tests/browser/test_flow_admin_navigation.py` (leg 01) references — verified post-leg-02 by grep. **No `.admin-title` / `.admin-pf-*` references remain in this file** (leg 01-02 already updated to `.page-title`). No changes in leg 03.

- `tests/browser/test_flow_hash_routing.py` — verified post-leg-02 by grep. **No `.admin-title` / `.admin-pf-*` references remain**. No changes in leg 03.

- `tests/browser/test_flow_keyboard.py` — does not reference admin editor selectors. No changes.

- `tests/browser/test_visual_snapshots.py:267-270` — asserts `[data-testid="provider-card"]`. Tile testid preserved by leg 02; **no changes** in leg 03 unless new editor screenshots are added (deferred to leg 05).

- `the_one/interfaces/web/static/js/app.js` exports used by this leg: `App.escapeHtml`, `App.escapeAttr`, `App.icon`, `App.formatBytes`, `App.showFlash`, `App.icons.admin`, `App.router.replaceSub`. All preserved.

## Acceptance Criteria

When this leg lands the following are all true:

### Editor scaffold (visual + DOM contract)

1. Opening any existing provider (`#admin/providers/{id}`) renders the editor with:
   - `<div class="editor-header">` containing `<div class="editor-header-text"><h1 class="editor-title">{provider.name}</h1><p class="editor-subtitle">{provider.type} · {provider.base_url || '—'}</p></div>` plus `<div class="form-actions">[← Back] [Cancel] [Save] [Test] <span class="editor-error"></span></div>`.
   - Three `<div class="editor-section">` blocks below the header in this exact DOM order: **Connection** (with `<div class="section-title">Connection</div>` and the four field rows), **Models** (with `<div class="section-title">Models</div>` and `<div class="provider-models"></div>` host), **Danger Zone** (with `<div class="section-title danger-zone-title">Danger Zone</div>` and `<button class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn">Delete Provider</button>`).
2. Opening the create flow (`#admin/providers/new`) renders the editor with:
   - `<h1 class="editor-title">New Provider</h1>` (no subtitle paragraph in create mode — the `<p class="editor-subtitle">` element is omitted entirely, mirroring agent-editor.js:66-68).
   - Action cluster: `[← Back] [Cancel] [Create]` (no Test button — `provider.id` does not exist yet) + the `editor-error` span. The `[Create]` button shows the literal text `"Create"` and uses `class="btn-filled-cyan save-btn"` with `data-testid="save-provider-btn"`.
   - Two sections: **Connection** + **Danger Zone is OMITTED** (matches agent-editor's `if (!isCreate)` gate; no provider exists to delete). **Models section is also OMITTED** in create mode (no provider id to fetch models for; the Models section appears only after first save transitions create→edit).
3. The action-cluster button DOM order is exactly: `.back-btn, .cancel-btn, .save-btn, .test-provider-btn` (left-to-right in the rendered cluster), followed by the `<span class="editor-error">`. Edit mode renders all four buttons; create mode renders the first three.
4. The `[← Back]` button uses `<button type="button" class="btn-outlined-cyan back-btn" data-testid="back-provider-btn" aria-label="Back to provider list">` containing `App.icon('arrow-left')` + the literal text " Back" (matches agent-editor.js:77-79 with "agent" → "provider").
5. The `[Cancel]` button uses `<button type="button" class="btn-outlined-cyan cancel-btn" data-testid="cancel-provider-btn" disabled>Cancel</button>` (the `disabled` attribute is present on initial render).
6. The `[Save]` / `[Create]` button uses `<button type="button" class="btn-filled-cyan save-btn" data-testid="save-provider-btn" disabled>{Save | Create}</button>` (the `disabled` attribute is present on initial render).
7. The `[Test]` button (edit-mode only, after first save) uses `<button type="button" class="btn-outlined-cyan test-provider-btn" data-testid="test-connection-btn">Test</button>`. The button text is shortened from "Test Connection" (pre-leg-03) to "Test" to match agent-editor's tighter cluster sizing — verified by visual review against studio.css line 49 padding.

### Save / Cancel as disabled-SSoT

8. On editor mount the form snapshot is captured (mirroring studio.js:688-691). `checkDirty()` is wired to fire on every `input` and `change` event from `.field-input`, `.field-select`, and the `.api-key-eye` toggle's effect on the password field (the eye toggle is cosmetic and does not flip dirty).
9. When `dirty === false` both `.save-btn` and `.cancel-btn` carry `disabled`. When `dirty === true` neither does. `.back-btn` is **never** disabled (its handler will eventually wrap a dirty-confirm dialog; that wrapper lands in leg 04).
10. After a successful Save in edit mode the dirty flag resets to `false` and the snapshot is recaptured (mirrors studio.js:510-511); both Save and Cancel re-disable.
11. After a successful Save in create mode the form transitions into edit mode: the editor sub-module's Save handler invokes `callbacks.onSaveSuccess(updated, true)`; the orchestrator sets `editingProvider = updated`, `providerFormMode = 'edit'`, calls `replaceSub(serializeState())` to update URL from `/new` to `/{id}`, then calls `renderProvidersPanel()` which re-mounts the editor with the new provider — Test button and Danger Zone and Models section now render, dirty is false (fresh closure), Save+Cancel disabled.
12. Clicking Cancel in edit mode (only possible when dirty) reverts the form fields to the snapshot values, resets dirty, re-disables Save+Cancel. The form remains in edit mode (does not navigate away). **Implementation note**: studio's `cancelEdit` (studio.js:503-513) reverts by re-rendering the entire editor from `self._selectedAgent`. Admin's leg-03 spec uses an **in-place revert from a JSON snapshot** (set each `[data-field]` element's `.value` from the captured snapshot dict). Both are valid revert mechanisms; admin's is simpler because the provider editor has no tabs/sub-modules to remount. **The "mirrors studio" wording is conceptual, not literal** — the snapshot approach is preferred for its locality.
13. Clicking Cancel in create mode (only possible when dirty) does NOT revert — instead it navigates back to `#admin/providers` (the grid). Rationale: in create mode there is no "saved baseline" to revert to; the only sensible Cancel action is "discard and go back to the list." This intentional asymmetry mirrors studio's create-mode Cancel which routes through `doHandleBack` (studio.js:480-489) — admin's create-mode Cancel similarly delegates to the orchestrator's `onCancel` callback, which performs `replaceSub('providers')` and re-renders the grid.

### Connection section + field rendering

14. The **Connection** section contains four field rows in this exact DOM order: `[Name]`, `[Type]`, `[Base URL]`, `[API Key]`. Each row uses the existing `<div class="field-row admin-pf-row">` wrapper (the per-area `.admin-pf-row` class is preserved for layout; the canonical `.field-row` rule provides the base styling).
15. The Name field renders as `<input class="field-input admin-pf-input" id="pf-name" data-field="name" value="{value}" placeholder="My Provider" />` (preserved verbatim from pre-leg-03).
16. The Type field renders as a `<select>` with `id="pf-type"` and `data-field="type"` (preserved verbatim). In edit mode the dropdown shows the current type as `selected`. In create mode the first option is the disabled placeholder `<option value="" disabled selected>Select a provider…</option>` (preserved).
17. The Base URL field renders as `<input class="field-input admin-pf-input" id="pf-base-url" data-field="base_url" value="{value}" placeholder="https://..." />` inside a `<div class="field-row admin-pf-row admin-pf-base-url{is-hidden?}">` wrapper. The `.admin-pf-base-url` per-area class is preserved (it's the type-driven show/hide hook in `wireProviderFormEvents`).
18. The API Key field renders as `<input class="field-input admin-pf-input admin-pf-password" id="pf-api-key" type="password" data-field="api_key" value="{value}" placeholder="sk-..." />` wrapped in `<div class="api-key-wrap">{input}<button class="api-key-eye" type="button" title="Show/Hide" aria-label="Show password">{eye-icon}</button></div>`. The wrapper class is the **canonical** `.api-key-wrap` (NOT `.admin-pf-password-wrap`); the eye button class is the **canonical** `.api-key-eye` (NOT `.admin-pf-eye`).
19. The eye-toggle handler swaps `passwordInput.type` between `'password'` and `'text'`, swaps `App.icon('eye')` ↔ `App.icon('eye-off')`, and updates `aria-label` between `"Show password"` and `"Hide password"`. Behavior preserved verbatim from pre-leg-03 admin.js:415-428.
20. The `<div class="test-result" aria-live="polite"></div>` host sits at the bottom of the Connection section (NOT in the form-actions cluster). Initial content is empty.

### Models section

21. The **Models** section contains `<div class="section-title">Models</div>` + a `<div class="provider-models"></div>` host. On editor mount in edit mode, `App.admin.renderProviderModels(modelsHostEl, provider)` is invoked synchronously after the editor scaffold attaches.
22. `App.admin.renderProviderModels(container, provider)` dispatches on `provider.type`: when `provider.type === 'ollama'`, calls the (now-internal-to-provider-models.js) `renderOllamaModels(provider.id, container)` — full Ollama lifecycle UI (refresh / pull / list / unload / load / delete-row). When any other type, renders the basic model list (mirrors pre-leg-03 admin.js:562-604) — Refresh button + listing of model names from `GET /api/providers/{id}/models`.
23. Ollama lifecycle behavior is **functionally identical** to pre-leg-03: Pull-Model search-suggestions hit `/api/ollama-library/search`, streaming pull progress via SSE on `/api/providers/{id}/models/pull`, abort-on-cancel, VRAM summary from `/api/providers/{id}/models/status`, per-model Load / Unload / Delete actions hitting `/api/providers/{id}/models/{action}`. All `.admin-pf-pull*` / `.admin-pf-vram*` / `.admin-pf-model*` selectors preserved (per-area scoping kept intentionally — these are Ollama-specific).
24. Ollama-row Delete keeps its existing inline two-step flow (`.admin-pf-model-delete-confirm`) in this leg — leg 04 migrates to `App.confirmDelete`.
25. Test-button-success auto-fetches models (preserved): after a 200 response from POST `/api/providers/{id}/test`, the editor sub-module **directly** re-invokes `App.admin.renderProviderModels(modelsHostEl, provider)` on the local `.provider-models` host element. **NO `onTestSuccess` callback** to the orchestrator — the editor sub-module owns its own DOM children and refreshes them locally. (Resolution of OQ4.)
26. The Refresh button on the Models panel (basic-list branch) and the Refresh button on the Ollama panel both re-invoke their respective renderers (loop back to `renderProviderModels`).

### Danger Zone

27. The Danger Zone is rendered ONLY when `provider.id` exists (edit mode, post-first-save). Markup: `<div class="editor-section danger-zone"><div class="section-title danger-zone-title">Danger Zone</div><button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="{provider.name}">Delete Provider</button></div>` — mirrors general-tab.js:133-138.
28. Clicking the Delete button triggers the agent-usage check (preserved from `handleProviderDelete`): `GET /api/providers/{id}/agents`. If the response's `agents` array is non-empty, the button text becomes `"Used by: {names.join(', ')}"`, the button is disabled, `aria-live="assertive"` is set, and a 3-second timer reverts the button to `"Delete Provider"` + re-enables. NO confirm flow occurs in this branch.
29. If `agents` is empty (or the agent-usage fetch fails), the button enters confirm-armed state: `class="delete-btn confirm"` is set, `aria-live="assertive"` is set, button text becomes `"Confirm Delete?"` (capital D, matching studio's pattern at general-tab.js implementation per F5 leg 05), and a 3-second timer reverts. **The confirm class name changes from `.admin-provider-delete-confirm` (pre-leg-03) to `.delete-btn.confirm`** to match the canonical `.delete-btn[.confirm]` styling lifted to components.css.
30. Clicking the armed (`.delete-btn.confirm`) button fires DELETE `/api/providers/{id}`. On 200, a flash message "Provider deleted" appears and the editor closes — `providerFormMode = null`, `editingProvider = null`, `replaceSub('providers')`, `renderProvidersPanel()` re-renders the grid. On error, an error flash appears and the button is reset.

### Test button gating + behavior

31. The Test button is rendered in the action cluster ONLY when `provider.id` exists (edit mode, post-first-save). In create-mode this `<button>` element is omitted entirely (mirrors agent-editor's conditional Delete; not just `disabled`).
32. While a Test request is in-flight: the Test button is `disabled`; the test-result span shows `<span class="test-result-pending">Testing…</span>`.
33. On HTTP 200 with `result.status === 'ok'`: the test-result span shows `<span class="test-result-ok">✓ {result.detail || 'Connected'}</span>`. The flash message "Connection successful" appears. Models are auto-refreshed. Test button re-enables.
34. On HTTP 200 with `result.status !== 'ok'` OR HTTP non-2xx: the test-result span shows `<span class="test-result-fail">✗ {result.detail || err.message || 'Failed'}</span>`. The flash message "Connection failed" or "Connection test error" appears (matching pre-leg-03 differentiation). Test button re-enables.

### Sub-module split

35. **NEW** `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` exists (target ~280 LOC). Top-level IIFE matching `providers-grid.js` style:
    ```js
    (function () {
      'use strict';
      window.App = window.App || {};
      window.App.admin = window.App.admin || {};
      // ... renderProviderEditor + helpers ...
      window.App.admin.renderProviderEditor = renderProviderEditor;
    })();
    ```
36. The exported function signature is `renderProviderEditor(container, provider, providerTypes, callbacks)` where:
    - `container` is the contentEl host into which the editor scaffold is rendered.
    - `provider` is `null` (create mode) or `{id, name, type, base_url, api_key, ...}` (edit mode).
    - `providerTypes` is the array passed by the orchestrator (no internal fetch — orchestrator owns fetchProviderTypes; the gate at admin.js:297-300 moves to the orchestrator's call site).
    - `callbacks` is `{ onBack, onCancel, onSaveSuccess, onDeleteSuccess, getTypeDefaults }`. **The editor sub-module owns the `fetch('/api/providers'+...)` calls directly** (POST for create, PUT for edit, DELETE for delete-flow, POST `/test` for test-button, GET `/agents` for agent-usage check). **`onSaveSuccess(updatedProvider, isCreate)`** is invoked AFTER a successful save with the parsed response body — the orchestrator mutates state (`editingProvider = updatedProvider; providerFormMode = 'edit'; replaceSub(...);`) and may decide whether to re-render. **`onDeleteSuccess()`** is invoked after a successful DELETE response; the orchestrator handles re-render. **`getTypeDefaults(type)`** returns `TYPE_DEFAULTS[type]` (orchestrator owns the static map). Validation errors and HTTP failures stay LOCAL to the editor — written into the `.editor-error` span without orchestrator round-trip. (Resolution of OQ on onSave shape — sub-module-owned-fetch chosen for minimal orchestrator coupling and straightforward leg-04 dirty-tracking hookup.)
37. **NEW** `the_one/interfaces/web/static/js/areas/admin/provider-models.js` exists (target ~400 LOC — most of pre-leg-03 admin.js's 562-1021 range). Top-level IIFE structure identical to above.
38. The exported function `renderProviderModels(container, provider)` is the public entry; internal helpers `renderOllamaModels(providerId, container)`, `wireOllamaActions(providerId, container)`, `ollamaAction(providerId, container, action, model, btn)`, and the basic-list branch are file-private.
39. `provider-models.js` has **no orchestrator dependency** — it gets `provider` directly and calls fetch endpoints directly. It uses `App.escapeHtml`, `App.escapeAttr`, `App.icon`, `App.formatBytes`, and `App.showFlash` as before. The only state it owns is the per-render closure (pull-abort controller, search timer). On re-render the closure is fresh, matching pre-leg-03 admin.js semantics.
40. `admin.js` post-leg-03 LOC is in the range 700–840 (pre-leg-03 1117 minus ~280 for provider-editor extract minus ~400 for provider-models extract minus net renames). Track exact LOC in the flight log.
41. `admin.js` post-leg-03 retains: serializeState/hydrateState, init's category sidebar wiring, renderContent, renderProvidersPanel (now delegates to `App.admin.renderProviderEditor` in the editor branch), fetchProviders, populateProviderGrid, selectProvider, enterCreateMode, findProvider, fetchProviderTypes, TYPE_DEFAULTS, showAdminFlash, the Object.defineProperty descriptors, _setCategory, _tryConsumePendingProvider, _refresh, activate. The provider-form / form-events / model-fetch / Ollama-lifecycle / handleProviderDelete bodies all migrate or delete.
42. `templates/{base|index}.html` carries 4 admin sub-module script tags total (system-page.js, providers-grid.js, provider-editor.js, provider-models.js) in load order.

### CSS lifts (canonicalization)

43. **components.css** has new rules added below the existing `.test-result-fail` rule (lines 545-555 today). New rules: `.danger-zone`, `.danger-zone-title`, `.api-key-wrap`, `.api-key-eye` (+ hover/focus-visible/svg-size variants), `.test-result-pending`, `.save-btn` (+ `[disabled]` / `:not([disabled])` variants), `.back-btn` (+ svg-size), **NO** `.cancel-btn` rule — `cancel-btn` is purely a JS testid/grep hook; the canonical `.btn-outlined-cyan:disabled` rule (components.css:236) provides the disabled opacity (Cancel composes onto `.btn-outlined-cyan`), `.test-provider-btn` (+ svg-size + disabled variant), `.delete-btn` (+ `.confirm` variant), **`.editor-section`** + **`.editor-section + .editor-section`** (lifted from studio.css:16-17 — see #44 for the matching deletion). Resolution of OQ2: lift opportunistically; admin's editor needs section padding + section-divider border-top to render correctly.
44. **studio.css** has the lifted rules deleted: lines 16-17 (.area-studio .editor-section + .editor-section divider — lifted to canonical un-scoped form per #43), lines 44-50 (.area-studio .save-btn + back-btn + test-provider-btn variants), lines 51-54 (.area-studio .delete-btn + .confirm), line 60 (.area-studio .danger-zone-title). Studio LOC delta: ~−12 to −15 lines. Studio markup at general-tab.js + agent-editor.js + studio.js continues to work because the bare class names match the new canonical (un-area-scoped) rules.
45. **admin.css** has these rules deleted: `.admin-header`, `.admin-title`, `.admin-form` (only if no surviving consumer; verify with grep — `.admin-form` is used at line 6 today; check if `system-page.js` or any leg-02 code emits `.admin-form`. If yes, preserve. If no, delete), `.admin-provider-form`, `.admin-pf-cancel`, `.admin-pf-password-wrap` + nested, `.admin-pf-eye` + variants, `.admin-pf-actions`, `.admin-pf-error`, `.admin-pf-test` + variants, `.admin-pf-test-result`, `.admin-pf-testing`, `.admin-pf-test-ok`, `.admin-pf-test-fail`. Admin LOC delta: ~−15 to −20 lines.
46. The admin focus-visible rule at admin.css:52 is mutated to drop the obsolete selectors. Post-leg-03 it reads `.area-admin .admin-pf-models-refresh:focus-visible, .area-admin .admin-pf-pull-go:focus-visible, .area-admin .admin-pf-pull-cancel:focus-visible, .area-admin .admin-pf-pull-btn:focus-visible, .area-admin .admin-pf-model-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: 0 0 0 3px var(--accent-glow); }` — covering only the Ollama-lifecycle button family that remains under the `.admin-pf-*` namespace.
47. The studio editor (agent edit page) **renders identically** post-leg-03 — the lifts move CSS rules but their bare class names are unchanged in studio markup. Verify by visual comparison that studio's Save/Cancel/Back/Test/Delete buttons are pixel-identical pre-vs-post-leg-03 (one of the leg-05 HAT criteria).

### URL contract preservation

48. All URL contracts established by leg 02 are preserved unchanged:
    - `#admin` redirects to `#admin/system`.
    - `#admin/general` redirects to `#admin/system`.
    - `#admin/providers` shows the grid.
    - `#admin/providers/new` shows the editor in create mode.
    - `#admin/providers/{id}` shows the editor in edit mode.
    - Refresh on every URL returns to that exact view.
    - Hydrate-vs-fetch race protection (pendingProviderId / pendingFormMode) preserved.
49. Successful create transitions URL from `#admin/providers/new` to `#admin/providers/{newId}` via `replaceSub` (preserved from pre-leg-03 admin.js:515-517).
50. Cancel from a clean create-mode editor (Back) navigates to `#admin/providers` (the grid).
51. Successful Delete navigates from `#admin/providers/{id}` to `#admin/providers` (the grid) — leverages `replaceSub('providers')` after `editingProvider = null`.

### Ollama lifecycle preservation

52. All Ollama lifecycle UX is functionally identical: pull / search / cancel-pull / load / unload / per-model-delete-confirm / VRAM-summary / streaming-progress / error-display. No regressions. Verify by manual `the_one` HAT against an Ollama provider (deferred to leg 05 HAT).

### Test updates

53. `tests/browser/test_flow_provider_setup.py`:
    - line 8 docstring: `"Edit it, click Test Connection, see success"` → keep wording (still accurate).
    - line 47: `expect(page.locator(".admin-title")).to_have_text("Edit Provider")` → `expect(page.locator(".editor-title")).to_have_text("Mock Test")`.
    - line 54: `.admin-pf-test-result` → `.test-result`.
    - line 57: `page.locator(".admin-pf-cancel").click()` → `page.locator('[data-testid="back-provider-btn"]').click()`. Add a comment: `# Clean form (just tested, no edits) — Cancel is disabled; use Back to return.`
    - All other lines preserved.
54. `tests/browser/test_flow_provider_grid.py`:
    - Update lines 55, 56, 63, 65, 75, 93, 96, 103 — all `.admin-title` references replaced with `.editor-title`. Title text expectations updated: "Add Provider" → "New Provider" (3 places: lines 56, 63, 65, 103). "Edit Provider" → "mock" (3 places: lines 75, 93, 96 — using the seeded provider's actual name).
    - Line 104: `page.locator(".admin-pf-cancel").click()` → `page.locator('[data-testid="back-provider-btn"]').click()`. Add comment: `# Clean form — Cancel disabled, use Back.`
    - Line 116: fallback locator `.area-admin .page-header, .admin-pf-error` → `.area-admin .page-header, .editor-error`.
55. **NEW** `tests/browser/test_flow_provider_editor.py` (created by this leg) covers the editor-shape contract:
    - `test_editor_renders_canonical_header_in_edit_mode` — load `#admin/providers/{seeded-id}`; assert `.area-admin .editor-header` visible, `.editor-title` text equals the seeded provider name, `.editor-subtitle` text contains the type and (for non-`mock`) the base_url.
    - `test_editor_renders_canonical_header_in_create_mode` — load `#admin/providers/new`; assert `.editor-title` text equals "New Provider"; assert `.editor-subtitle` element does NOT exist.
    - `test_editor_action_cluster_order_in_edit_mode` — assert `.form-actions > *` children include `.back-btn`, `.cancel-btn`, `.save-btn`, `.test-provider-btn`, `.editor-error` in DOM order.
    - `test_editor_action_cluster_order_in_create_mode` — assert children include `.back-btn`, `.cancel-btn`, `.save-btn`, `.editor-error` in DOM order; `.test-provider-btn` NOT present.
    - `test_save_and_cancel_disabled_when_clean` — load editor (edit mode, mock provider); assert both `.save-btn[disabled]` and `.cancel-btn[disabled]`.
    - `test_save_and_cancel_enabled_when_dirty` — load editor; type a character into `#pf-name`; assert neither `.save-btn` nor `.cancel-btn` carries `disabled`.
    - `test_cancel_reverts_in_edit_mode` — type into Name; click Cancel; assert Name reverts to original; both buttons re-disabled.
    - `test_create_cancel_navigates_to_grid_when_dirty` — load `#admin/providers/new`; type into Name; click Cancel; assert hash is `#admin/providers` and the grid (page-header) is visible.
    - `test_back_button_always_enabled` — load editor (edit mode, clean); assert `.back-btn` does NOT carry `disabled`.
    - `test_danger_zone_renders_in_edit_mode` — load editor (edit mode); assert `.editor-section.danger-zone` visible, `.section-title.danger-zone-title` text "Danger Zone", `[data-testid="delete-provider-btn"]` visible.
    - `test_danger_zone_omitted_in_create_mode` — load `#admin/providers/new`; assert `.editor-section.danger-zone` NOT present.
    - `test_delete_two_step_confirm` — load editor; click delete-provider-btn; assert button text becomes "Confirm Delete?" and button has class `confirm`; click again; assert hash returns to `#admin/providers` (grid view) and a flash mentioning "Provider deleted" or similar appears.
    - `test_delete_blocked_when_provider_in_use` — seed a provider AND an agent that uses it; click delete-provider-btn; assert button text contains "Used by:" and the agent's name; assert button is disabled.
    - `test_test_button_omitted_in_create_mode` — load `#admin/providers/new`; assert `[data-testid="test-connection-btn"]` NOT present.
    - `test_test_button_visible_in_edit_mode` — load editor (edit, mock); assert `[data-testid="test-connection-btn"]` visible.
    - `test_test_result_uses_canonical_class` — load editor (edit, mock); click Test; assert `.test-result.test-result-ok` visible (or `.test-result-pending` during the in-flight window).
    - `test_api_key_eye_toggle` — load editor for an `openai` provider (api_key field shown); locate `.api-key-eye` button + `#pf-api-key`; assert `#pf-api-key[type="password"]`; click eye; assert `#pf-api-key[type="text"]`; click again; assert returns to `password`.

    **Test file uses the existing `app_clean`, `app_with_provider`, and `app_with_agent` fixtures from `tests/browser/conftest.py` (verified at lines 230-243 — `app_with_agent` composes on `app_with_provider` and seeds a mock agent via `seed_mock_agent`; `SeededApp.agent_name` carries the seeded agent's name). The agent-usage hard-block test (`test_delete_blocked_when_provider_in_use`) uses `app_with_agent` and asserts `app.agent_name` appears in the Delete button's "Used by:" text. **No skip — this is a first-class assertion.**

56. Run all admin browser tests post-implementation: `docker exec the-one pytest tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_provider_grid.py tests/browser/test_flow_provider_setup.py tests/browser/test_flow_provider_editor.py -v`. All must pass. Run all studio browser tests to verify no regressions from CSS lifts: `docker exec the-one pytest tests/browser/test_flow_agent_crud.py tests/browser/test_flow_agent_tile.py tests/browser/test_flow_agent_tabs.py tests/browser/test_flow_dirty_confirm.py tests/browser/test_flow_keyboard.py -v`. All must pass.

### No backend changes

57. Zero changes to `the_one/interfaces/api/`, `the_one/services/`, `the_one/repositories/`, or any Python source. The leg is pure frontend (JS + CSS + HTML template + tests).
58. No new endpoints. No changes to existing endpoints. No DB migrations.

### No regressions

59. Total unit-test count post-leg-03 ≥ 413 (post-leg-02 baseline). Unit tests must all pass: `docker exec the-one pytest tests/unit/ -v`.
60. Total browser-test count post-leg-03 ≥ 187 + 17 (new editor tests in #55) = ≥ 204. Slight variance acceptable if some create-mode-cancel tests are reframed.
61. Visual snapshots not committed (gitignored per global preference). If `tests/browser/test_visual_snapshots.py` is run, regenerate locally; do not fail the leg on diff (snapshots are local-only regression artifacts).
62. Manual-smoke checklist in flight log: open studio (verify identical), open admin/system, open admin/providers grid, click a tile, exercise create flow, exercise edit flow, exercise Test, exercise Cancel-while-dirty (revert), exercise Back-with-dirty-without-confirm (acceptable for leg 03; leg 04 adds the dialog), exercise Danger-Zone Delete (both branches: agent-blocked and confirm-flow), exercise Ollama lifecycle if available locally.

## Implementation Steps

### Step 1: Verify pre-conditions + locate template file

1. `cd` to the-one project root (or invoke from there).
2. `grep -n 'areas/admin/' the_one/interfaces/web/templates/*.html` — locate the template file that emits the admin sub-module script tags. Confirm it currently has 2 admin script tags (system-page.js + providers-grid.js, lines 46-47 of the file).
3. `wc -l the_one/interfaces/web/static/js/areas/admin.js the_one/interfaces/web/static/css/admin.css the_one/interfaces/web/static/css/studio.css the_one/interfaces/web/static/css/components.css` — capture baselines: 1117 / 127 / 66 / 691.
4. `grep -rn 'admin-pf-password-wrap\|admin-pf-eye\|admin-pf-test-result\|admin-pf-testing\|admin-pf-test-ok\|admin-pf-test-fail\|admin-pf-cancel\|admin-pf-save\|admin-pf-actions\|admin-pf-error\|admin-pf-test\b\|admin-header\|admin-title\|admin-provider-form\|admin-provider-delete-confirm' the_one/interfaces/web/static/ tests/browser/` — generate the full sweep list. Verify it matches the ones enumerated in this leg's Inputs section. Capture any surprises in the flight log before proceeding.
5. `grep -rn 'editor-section + .editor-section\|.area-studio .save-btn\|.area-studio .back-btn\|.area-studio .test-provider-btn\|.area-studio .delete-btn\|.area-studio .danger-zone-title' the_one/interfaces/web/static/css/` — confirm the studio-area-scoped rules to lift. Capture exact line numbers.

### Step 2: Lift CSS to components.css

Edit `the_one/interfaces/web/static/css/components.css`. Append new rules after the `.test-result-fail` rule (currently at line 555). Add the following rule blocks in this order (each as a separate `=== Section ===` block with an inline comment):

1. `=== Save / Cancel button (disabled-SSoT pattern) ===`
   ```css
   /* Save and Cancel both use `disabled` as the SOLE source of truth (lifted
      from .area-studio .save-btn in F6 leg 03; consumed by both studio's
      agent editor and admin's provider editor). The dirty-tracker shim
      (checkDirty) flips both attributes together. Cosmetics from
      .btn-filled-cyan (Save) / .btn-outlined-cyan (Cancel). */
   .save-btn { transition: opacity 0.2s; padding: 6px 16px; font-size: var(--font-size-body-sm); }
   .save-btn[disabled] { opacity: 0.4; cursor: not-allowed; }
   .save-btn:not([disabled]) { opacity: 1; }
   ```

2. `=== Back button (icon + text) ===`
   ```css
   .back-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; }
   .back-btn svg { width: 14px; height: 14px; }
   ```

3. `=== Test connection button ===`
   ```css
   .test-provider-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; }
   .test-provider-btn svg { width: 14px; height: 14px; }
   .test-provider-btn:disabled { opacity: 0.4; cursor: not-allowed; }
   ```

4. `=== Delete button (inline two-step confirm pattern) ===`
   ```css
   /* Delete-btn — area-agnostic; cosmetics from .btn-muted-destructive.
      `.delete-btn.confirm` is the armed state (capital-D "Confirm Delete?"
      label set by JS, 3-second revert). Used by studio's agent-edit Danger
      Zone (F5 leg 05) and admin's provider-edit Danger Zone (F6 leg 03).
      Leg 04 may migrate both to App.confirmDelete (modal); the rule stays
      until then. */
   .delete-btn { padding: 6px 14px; border-radius: 6px; font-size: var(--font-size-body-sm); }
   .delete-btn.confirm { background: var(--status-danger); color: var(--fg-on-danger); border-color: var(--status-danger); font-weight: var(--font-weight-semibold); }
   ```

5. `=== Danger Zone (editor section variant) ===`
   ```css
   /* Danger Zone — destructive section at the bottom of an entity editor.
      Lifted from .area-studio .danger-zone-title (F6 leg 03). The section
      itself uses `class="editor-section danger-zone"`; the title uses
      `class="section-title danger-zone-title"`. The .danger-zone class
      itself is currently a hook for grep-ability + future styling. */
   .danger-zone { /* hook for future destructive-section accent; bare class for grep */ }
   .danger-zone-title { color: var(--status-danger); }
   ```

6. `=== API-key wrapper (input + show/hide eye toggle) ===`
   ```css
   /* API-key field wrapper — lifted from admin's .admin-pf-password-wrap
      (F6 leg 03). The eye button is a toggle that swaps password<->text on
      the adjacent input. Used by admin's provider editor (Connection
      section). */
   .api-key-wrap { flex: 1; display: flex; gap: 6px; align-items: center; }
   .api-key-wrap .field-input { flex: 1; }
   .api-key-eye { background: none; border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px; color: var(--fg-secondary); font-size: var(--font-size-tiny); cursor: pointer; font-family: inherit; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
   .api-key-eye:hover { color: var(--fg); border-color: var(--border-strong); }
   .api-key-eye:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: 0 0 0 3px var(--accent-glow); }
   .api-key-eye svg { width: 14px; height: 14px; display: block; }
   ```

7. `=== Test result pending state ===` — add ABOVE the existing `.test-result` rule (lines 548-555) so the family stays grouped. Or below `.test-result-fail`; either is acceptable.
   ```css
   .test-result-pending { color: var(--fg-secondary); }
   ```

Verify components.css LOC after edits is ~691 + ~25 = ~716.

### Step 3: Delete lifted rules from studio.css

Edit `the_one/interfaces/web/static/css/studio.css`. Delete these rule blocks:

- Lines 39-55 (the `=== Studio Area: Actions ===` section header comment + all six rules: `.area-studio .save-btn` + 2 variants, `.area-studio .back-btn` + svg, `.area-studio .test-provider-btn` + svg, `.area-studio .delete-btn` + `.confirm`).
- Lines 56-60 (the `=== Studio Area: Danger Zone ===` section header comment + `.area-studio .danger-zone-title`).

Verify studio.css LOC after edits is ~66 - 11 = ~55.

### Step 4: Update admin.css

Edit `the_one/interfaces/web/static/css/admin.css`. Delete these rules (matching the lines enumerated in Inputs):

- Line 4: `.area-admin .admin-header` + line 5: `.area-admin .admin-title`. (Verify no surviving consumers via `grep -rn 'admin-header\|admin-title' the_one/interfaces/web/static/`.)
- Line 6: `.area-admin .admin-form` — verify via `grep -rn '"admin-form"\|class="[^"]*admin-form\b' the_one/interfaces/web/static/js/`. If no consumer, delete. If yes, preserve.
- Line 55: `.area-admin .admin-provider-form`.
- Line 56: `.area-admin .admin-pf-cancel`.
- Lines 57-58: `.area-admin .admin-pf-password-wrap` + nested.
- Lines 59-61: `.area-admin .admin-pf-eye` + variants.
- Line 62: `.area-admin .admin-pf-actions`.
- Line 63: `.area-admin .admin-pf-error`.
- Lines 64-67: `.area-admin .admin-pf-test` + variants.
- Lines 70-73: `.area-admin .admin-pf-test-result` / `.admin-pf-testing` / `.admin-pf-test-ok` / `.admin-pf-test-fail`.

Edit the focus-visible rule at line 52 (admin-pf focus-rings) to read:
```css
.area-admin .admin-pf-models-refresh:focus-visible,
.area-admin .admin-pf-pull-go:focus-visible,
.area-admin .admin-pf-pull-cancel:focus-visible,
.area-admin .admin-pf-pull-btn:focus-visible,
.area-admin .admin-pf-model-btn:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: 0 0 0 3px var(--accent-glow);
}
```

Verify admin.css LOC after edits is in the 105–115 range.

### Step 5: Create provider-editor.js

Create `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`. Structure:

```js
// App.admin.renderProviderEditor — provider-editor scaffold (F6 leg 03).
//
// Builds the editor surface mirroring studio's agent-editor (F5 leg 03):
//   <div class="editor-header">
//     <div class="editor-header-text">
//       <h1 class="editor-title">{name | "New Provider"}</h1>
//       <p class="editor-subtitle">{type · base_url}</p>  (edit only)
//     </div>
//     <div class="form-actions">
//       <button class="back-btn">← Back</button>
//       <button class="cancel-btn" disabled>Cancel</button>
//       <button class="save-btn" disabled>{Save | Create}</button>
//       <button class="test-provider-btn">Test</button>  (edit only)
//       <span class="editor-error"></span>
//     </div>
//   </div>
//   <div class="editor-section">
//     <div class="section-title">Connection</div>
//     {name + type + base_url + api_key fields}
//     <div class="test-result"></div>
//   </div>
//   <div class="editor-section">                    (edit only)
//     <div class="section-title">Models</div>
//     <div class="provider-models"></div>
//   </div>
//   <div class="editor-section danger-zone">        (edit only)
//     <div class="section-title danger-zone-title">Danger Zone</div>
//     <button class="delete-btn">Delete Provider</button>
//   </div>
//
// callbacks: { onBack, onCancel, onSave, onDeleteSuccess, getTypeDefaults }
//
// Editor Delete keeps inline two-step (.delete-btn.confirm). Leg 04 migrates
// to App.confirmDelete.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  function renderProviderEditor(container, provider, providerTypes, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !provider;
    var name = isCreate ? 'New Provider' : (provider.name || '');

    // ── Header HTML ─────────────────────────────────────────────────
    var html = '';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h1 class="editor-title">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      var subtitleParts = [escapeHtml(provider.type)];
      if (provider.base_url) subtitleParts.push(escapeHtml(provider.base_url));
      html += '<p class="editor-subtitle">' + subtitleParts.join(' · ') + '</p>';
    }
    html += '</div>';

    // ── Action cluster ──────────────────────────────────────────────
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn-outlined-cyan back-btn" data-testid="back-provider-btn" aria-label="Back to provider list">' + window.App.icon('arrow-left') + ' Back</button>';
    html += '<button type="button" class="btn-outlined-cyan cancel-btn" data-testid="cancel-provider-btn" disabled>Cancel</button>';
    html += '<button type="button" class="btn-filled-cyan save-btn" data-testid="save-provider-btn" disabled>' + (isCreate ? 'Create' : 'Save') + '</button>';
    if (!isCreate) {
      html += '<button type="button" class="btn-outlined-cyan test-provider-btn" data-testid="test-connection-btn">Test</button>';
    }
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Connection section ──────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Connection</div>';
    html += renderConnectionFields(provider, providerTypes, callbacks);
    html += '<div class="test-result" aria-live="polite"></div>';
    html += '</div>';

    // ── Models section (edit only) ──────────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section">';
      html += '<div class="section-title">Models</div>';
      html += '<div class="provider-models"></div>';
      html += '</div>';
    }

    // ── Danger Zone section (edit only) ─────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      html += '<button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="' + escapeAttr(provider.name || '') + '">Delete Provider</button>';
      html += '</div>';
    }

    container.innerHTML = html;

    wireEditorEvents(container, provider, providerTypes, callbacks);

    // Mount the Models panel synchronously in edit mode (mirrors agent-editor's
    // synchronous General-tab mount so tests find selectors immediately).
    if (!isCreate && window.App.admin.renderProviderModels) {
      var modelsHost = container.querySelector('.provider-models');
      if (modelsHost) {
        window.App.admin.renderProviderModels(modelsHost, provider);
      }
    }
  }

  function renderConnectionFields(provider, providerTypes, callbacks) {
    /* Render the four field rows: name, type, base_url, api_key.
       Reuses pre-leg-03 admin.js:314-351 markup verbatim (DOM/selectors
       preserved for backward compat with tests that locate by #pf-name etc.). */
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !provider;
    var type = isCreate ? '' : provider.type;
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(type)) || { base_url: '', showBaseUrl: false, showApiKey: false };

    var html = '';
    // Name
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="pf-name">Name</label>';
    html += '<input class="field-input admin-pf-input" id="pf-name" data-field="name" value="' + escapeAttr(isCreate ? '' : provider.name) + '" placeholder="My Provider" />';
    html += '</div>';

    // Type
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="pf-type">Type</label>';
    html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="pf-type" data-field="type">';
    if (isCreate) html += '<option value="" disabled selected>Select a provider…</option>';
    for (var t = 0; t < providerTypes.length; t++) {
      var pt = providerTypes[t];
      html += '<option value="' + escapeAttr(pt.value) + '"' + (!isCreate && type === pt.value ? ' selected' : '') + '>' + escapeHtml(pt.label) + '</option>';
    }
    html += '</select>';
    html += '</div>';

    // Base URL
    var baseUrlValue = isCreate ? defaults.base_url : provider.base_url;
    html += '<div class="field-row admin-pf-row admin-pf-base-url' + (defaults.showBaseUrl ? '' : ' is-hidden') + '">';
    html += '<label for="pf-base-url">Base URL</label>';
    html += '<input class="field-input admin-pf-input" id="pf-base-url" data-field="base_url" value="' + escapeAttr(baseUrlValue) + '" placeholder="https://..." />';
    html += '</div>';

    // API Key (canonical .api-key-wrap + .api-key-eye)
    var apiKeyValue = isCreate ? '' : (provider.api_key || '');
    html += '<div class="field-row admin-pf-row admin-pf-api-key' + (defaults.showApiKey ? '' : ' is-hidden') + '">';
    html += '<label for="pf-api-key">API Key</label>';
    html += '<div class="api-key-wrap">';
    html += '<input class="field-input admin-pf-input admin-pf-password" id="pf-api-key" type="password" data-field="api_key" value="' + escapeAttr(apiKeyValue) + '" placeholder="sk-..." />';
    html += '<button class="api-key-eye" type="button" title="Show/Hide" aria-label="Show password">' + window.App.icon('eye') + '</button>';
    html += '</div>';
    html += '</div>';

    return html;
  }

  function wireEditorEvents(container, provider, providerTypes, callbacks) {
    /* Wire: type-change show/hide, eye-toggle, dirty tracking, Back, Cancel,
       Save, Test, Delete. Mirror admin.js:385-558 with these substitutions:
         - .admin-pf-cancel        → .cancel-btn
         - .admin-pf-save          → .save-btn
         - .admin-pf-test          → .test-provider-btn
         - .admin-pf-eye           → .api-key-eye
         - .admin-pf-error         → .editor-error
         - .admin-pf-test-result   → .test-result
         - .admin-pf-testing       → .test-result-pending (span class)
         - .admin-pf-test-ok       → .test-result-ok      (span class)
         - .admin-pf-test-fail     → .test-result-fail    (span class)
       Add: MASKED_SENTINEL capture (originalMaskedApiKey); dirty-tracking
       shim (snapshot + checkDirty); .back-btn handler; .delete-btn handler
       with agent-usage hard-block + inline two-step. Sub-module owns the
       fetch (POST/PUT/DELETE/test); onSaveSuccess + onDeleteSuccess
       callbacks notify orchestrator AFTER successful response. */
    var isEdit = !!provider;
    var snapshot = getFormSnapshot(container);
    var dirty = false;
    /* MASKED_SENTINEL preservation (preserves admin.js:466-470 behavior).
       Capture the originally pre-filled (masked) api-key value so we can
       detect "user did not modify the field" on submit. In create mode this
       is empty. */
    var MASKED_SENTINEL = '__MASKED__';
    var originalMaskedApiKey = isEdit ? (provider.api_key || '') : '';

    function getFormSnapshot(c) {
      var data = {};
      var fields = c.querySelectorAll('[data-field]');
      for (var i = 0; i < fields.length; i++) {
        data[fields[i].dataset.field] = fields[i].value;
      }
      return JSON.stringify(data);
    }

    function checkDirty() {
      var current = getFormSnapshot(container);
      dirty = current !== snapshot;
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      if (cancelBtn) cancelBtn.disabled = !dirty;
    }

    /* Wire input/change listeners on all .field-input + .field-select */
    var inputs = container.querySelectorAll('.field-input, .field-select');
    for (var i = 0; i < inputs.length; i++) {
      inputs[i].addEventListener('input', checkDirty);
      inputs[i].addEventListener('change', checkDirty);
    }

    /* Type-change: show/hide base_url + api_key + reset base_url default. */
    var typeSelect = container.querySelector('[data-field="type"]');
    var baseUrlRow = container.querySelector('.admin-pf-base-url');
    var baseUrlInput = container.querySelector('[data-field="base_url"]');
    var apiKeyRow = container.querySelector('.admin-pf-api-key');
    typeSelect.addEventListener('change', function () {
      var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(typeSelect.value)) || {};
      baseUrlRow.classList.toggle('is-hidden', !defaults.showBaseUrl);
      apiKeyRow.classList.toggle('is-hidden', !defaults.showApiKey);
      baseUrlInput.value = defaults.base_url || '';
      checkDirty();
    });

    /* Eye toggle. */
    var eyeBtn = container.querySelector('.api-key-eye');
    var passwordInput = container.querySelector('.admin-pf-password');
    if (eyeBtn && passwordInput) {
      eyeBtn.addEventListener('click', function () {
        if (passwordInput.type === 'password') {
          passwordInput.type = 'text';
          eyeBtn.innerHTML = window.App.icon('eye-off');
          eyeBtn.setAttribute('aria-label', 'Hide password');
        } else {
          passwordInput.type = 'password';
          eyeBtn.innerHTML = window.App.icon('eye');
          eyeBtn.setAttribute('aria-label', 'Show password');
        }
      });
    }

    /* Back. */
    var backBtn = container.querySelector('.back-btn');
    if (backBtn && callbacks.onBack) {
      backBtn.addEventListener('click', function () { callbacks.onBack(); });
    }

    /* Cancel: edit mode reverts; create mode delegates to onCancel (orchestrator
       handles the navigate-to-grid). */
    var cancelBtn = container.querySelector('.cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        if (isEdit) {
          // Revert to snapshot.
          var snap = JSON.parse(snapshot);
          var fields2 = container.querySelectorAll('[data-field]');
          for (var j = 0; j < fields2.length; j++) {
            fields2[j].value = snap[fields2[j].dataset.field] || '';
          }
          dirty = false;
          checkDirty();
        } else if (callbacks.onCancel) {
          callbacks.onCancel();
        }
      });
    }

    /* Save: editor sub-module owns the fetch. Orchestrator's
       onSaveSuccess callback handles state mutation + URL update. */
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        var errorEl = container.querySelector('.editor-error');
        errorEl.textContent = '';
        var payload = collectFormData(container, callbacks, originalMaskedApiKey, MASKED_SENTINEL, isEdit);
        if (!payload) return; // validation failed; collectFormData wrote error
        var url = isEdit ? '/api/providers/' + encodeURIComponent(provider.id) : '/api/providers';
        var method = isEdit ? 'PUT' : 'POST';
        fetch(url, {
          method: method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || (isEdit ? 'Save failed' : 'Create failed')); });
            return r.json();
          })
          .then(function (updated) {
            window.App.showFlash(container, isEdit ? 'Provider saved' : 'Provider created');
            if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
            // For create→edit transition the orchestrator re-renders the
            // editor with the new provider — closure is replaced. The
            // snapshot reset below only matters for the edit→edit case
            // where the editor stays mounted.
            if (isEdit) {
              snapshot = getFormSnapshot(container);
              dirty = false;
              checkDirty();
            }
          })
          .catch(function (err) {
            errorEl.textContent = err.message || String(err);
          });
      });
    }

    /* Test: only in edit mode. */
    var testBtn = container.querySelector('.test-provider-btn');
    if (testBtn && isEdit) {
      testBtn.addEventListener('click', function () {
        var resultEl = container.querySelector('.test-result');
        resultEl.innerHTML = '<span class="test-result-pending">Testing…</span>';
        testBtn.disabled = true;
        fetch('/api/providers/' + encodeURIComponent(provider.id) + '/test', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (result) {
            testBtn.disabled = false;
            if (result.status === 'ok') {
              resultEl.innerHTML = '<span class="test-result-ok">✓ ' + window.App.escapeHtml(result.detail || 'Connected') + '</span>';
              window.App.showFlash(container, 'Connection successful');
              // OQ4 resolution: editor sub-module owns its own DOM children.
              // Refresh the Models panel directly (no orchestrator round-trip).
              var modelsHost = container.querySelector('.provider-models');
              if (modelsHost && window.App.admin.renderProviderModels) {
                window.App.admin.renderProviderModels(modelsHost, provider);
              }
            } else {
              resultEl.innerHTML = '<span class="test-result-fail">✗ ' + window.App.escapeHtml(result.detail || 'Failed') + '</span>';
              window.App.showFlash(container, 'Connection failed', true);
            }
          })
          .catch(function (err) {
            testBtn.disabled = false;
            resultEl.innerHTML = '<span class="test-result-fail">✗ ' + window.App.escapeHtml(err.message || 'Request failed') + '</span>';
            window.App.showFlash(container, 'Connection test error', true);
          });
      });
    }

    /* Delete: only in edit mode. Inline two-step + agent-usage hard-block. */
    var deleteBtn = container.querySelector('.delete-btn');
    if (deleteBtn && isEdit) {
      var deleteConfirmTimer = null;
      deleteBtn.addEventListener('click', function () {
        if (deleteBtn.classList.contains('confirm')) {
          // Second click: actually delete.
          fetch('/api/providers/' + encodeURIComponent(provider.id), { method: 'DELETE' })
            .then(function (r) {
              if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
              window.App.showFlash(container, 'Provider deleted');
              if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
            })
            .catch(function (err) {
              window.App.showFlash(container, 'Error: ' + err.message, true);
            });
          return;
        }
        // First click: agent-usage check.
        fetch('/api/providers/' + encodeURIComponent(provider.id) + '/agents')
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var agents = data.agents || [];
            if (agents.length > 0) {
              deleteBtn.textContent = 'Used by: ' + agents.join(', ');
              deleteBtn.disabled = true;
              deleteBtn.setAttribute('aria-live', 'assertive');
              if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer);
              deleteConfirmTimer = setTimeout(function () {
                deleteBtn.disabled = false;
                deleteBtn.removeAttribute('aria-live');
                deleteBtn.textContent = 'Delete Provider';
              }, 3000);
            } else {
              deleteBtn.classList.add('confirm');
              deleteBtn.setAttribute('aria-live', 'assertive');
              deleteBtn.textContent = 'Confirm Delete?';
              if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer);
              deleteConfirmTimer = setTimeout(function () {
                deleteBtn.classList.remove('confirm');
                deleteBtn.removeAttribute('aria-live');
                deleteBtn.textContent = 'Delete Provider';
              }, 3000);
            }
          })
          .catch(function () {
            // Network failure on agent-usage check: fall back to confirm flow.
            deleteBtn.classList.add('confirm');
            deleteBtn.setAttribute('aria-live', 'assertive');
            deleteBtn.textContent = 'Confirm Delete?';
            if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer);
            deleteConfirmTimer = setTimeout(function () {
              deleteBtn.classList.remove('confirm');
              deleteBtn.removeAttribute('aria-live');
              deleteBtn.textContent = 'Delete Provider';
            }, 3000);
          });
      });
    }
  }

  function collectFormData(container, callbacks, originalMaskedApiKey, MASKED_SENTINEL, isEdit) {
    /* Validate + collect payload. Mirror admin.js:440-477 (Save handler's
       prologue) but return null + write error when invalid. Preserves the
       MASKED_SENTINEL substitution from admin.js:466-470. */
    var errorEl = container.querySelector('.editor-error');
    var nameInput = container.querySelector('[data-field="name"]');
    var name = nameInput.value.trim();
    if (!name) {
      errorEl.textContent = 'Name is required.';
      return null;
    }
    var typeSelect = container.querySelector('[data-field="type"]');
    var selectedType = typeSelect.value;
    if (!selectedType) {
      errorEl.textContent = 'Type is required.';
      return null;
    }
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(selectedType)) || {};
    var baseUrlInput = container.querySelector('[data-field="base_url"]');
    var baseUrl = baseUrlInput.value.trim();
    if (!defaults.showBaseUrl) baseUrl = defaults.base_url;
    if (!baseUrl && defaults.showBaseUrl) {
      errorEl.textContent = 'Base URL is required.';
      return null;
    }
    var apiKeyInput = container.querySelector('[data-field="api_key"]');
    var apiKey = apiKeyInput ? apiKeyInput.value : null;
    if (!apiKey) apiKey = null;
    /* MASKED_SENTINEL: if editing and the user did not modify the pre-filled
       (masked) value, send the sentinel so the backend preserves the existing
       stored key. Mirrors admin.js:466-470. */
    if (isEdit && originalMaskedApiKey && apiKey === originalMaskedApiKey) {
      apiKey = MASKED_SENTINEL;
    }
    return { name: name, type: selectedType, base_url: baseUrl, api_key: apiKey };
  }

  window.App.admin.renderProviderEditor = renderProviderEditor;
})();
```

**Note on snapshot recapture timing**: the `snapshot = getFormSnapshot(container); dirty = false; checkDirty();` block in the Save success path runs ONLY for `isEdit` (line above guards). For create-mode → edit-mode the orchestrator's `onSaveSuccess` re-renders the editor via a fresh `App.admin.renderProviderEditor(...)` call — the closure's `snapshot`/`dirty` variables become unreachable; the new closure starts with a fresh capture. This is correct.

**Note on `cancel-btn` having no canonical CSS rule**: per AC #43, `.cancel-btn` is purely a JS testid/grep hook; the disabled opacity comes from `.btn-outlined-cyan:disabled` (components.css:236) since Cancel composes `.btn-outlined-cyan cancel-btn`. Do NOT add a redundant `.cancel-btn[disabled]` rule.

### Step 6: Create provider-models.js

Create `the_one/interfaces/web/static/js/areas/admin/provider-models.js`. Move:

- `fetchProviderModels` (admin.js:562-604) → renamed to file-private `renderBasicModels(container, providerId)`. Top-level dispatch:
  ```js
  function renderProviderModels(container, provider) {
    if (!provider || !provider.id) return;
    if (provider.type === 'ollama') {
      renderOllamaModels(provider.id, container);
    } else {
      renderBasicModels(container, provider.id);
    }
  }
  ```
- `renderOllamaModels` (admin.js:610-942) → file-private function, copied with these substitutions: outer `contentEl` references → `container` (none required — it queries `container` already); `showAdminFlash` → `window.App.showFlash(container, msg, isError)`; **`<span class="admin-pf-test-fail">` (line 939) → `<span class="test-result-fail">`** (the `.admin-pf-test-fail` CSS rule is being deleted in Step 4; the JS must be updated to use the canonical name or the model-list error UI loses its red color).
- `wireOllamaActions` (admin.js:944-989) → file-private.
- `ollamaAction` (admin.js:991-1021) → file-private. Replace `showAdminFlash` similarly.
- `formatBytes` reference: just use `window.App.formatBytes`.

In `renderBasicModels` (the renamed `fetchProviderModels`), apply the same substitution: **`<span class="admin-pf-test-fail">` (originally admin.js:601) → `<span class="test-result-fail">`**.

Export only `renderProviderModels`:
```js
window.App.admin.renderProviderModels = renderProviderModels;
```

### Step 7: Update admin.js orchestrator

Edit `the_one/interfaces/web/static/js/areas/admin.js`:

1. **Delete** `handleProviderDelete` (lines 229-290).
2. **Delete** `renderProviderForm` + `_renderProviderFormImpl` (lines 294-383).
3. **Delete** `wireProviderFormEvents` (lines 385-558).
4. **Delete** `fetchProviderModels` (lines 562-604).
5. **Delete** `renderOllamaModels` (lines 610-942).
6. **Delete** `wireOllamaActions` (lines 944-989).
7. **Delete** `ollamaAction` (lines 991-1021).
8. **Delete** `var formatBytes = App.formatBytes;` (line 608).
9. **Update** `renderProvidersPanel` (lines 149-165) to delegate to the editor sub-module:
   ```js
   function renderProvidersPanel() {
     if (providerFormMode) {
       // Wait for provider types before rendering the editor (the type
       // dropdown depends on PROVIDER_TYPES).
       var ready = providerTypesReady || fetchProviderTypes();
       ready.then(function () {
         App.admin.renderProviderEditor(contentEl, editingProvider, PROVIDER_TYPES, {
           onBack: function () {
             providerFormMode = null;
             editingProvider = null;
             if (window.App && window.App.router) App.router.replaceSub('providers');
             renderProvidersPanel();
           },
           onCancel: function () {
             // Create-mode Cancel: navigate back to grid (the editor's
             // Cancel handler only invokes onCancel when isCreate).
             providerFormMode = null;
             editingProvider = null;
             if (window.App && window.App.router) App.router.replaceSub('providers');
             renderProvidersPanel();
           },
           onSaveSuccess: function (updated, isCreate) {
             // The editor sub-module owns the fetch; this callback only mutates
             // orchestrator state on success. For create→edit transition,
             // re-render the editor with the new provider so Models +
             // Danger Zone + Test button now render.
             editingProvider = updated;
             providerFormMode = 'edit';
             if (window.App && window.App.router) {
               App.router.replaceSub(self.serializeState());
             }
             if (isCreate) {
               // Re-mount editor in edit mode (closure replaces).
               renderProvidersPanel();
             }
             // Edit→edit case: editor stays mounted; sub-module's local
             // snapshot recapture handles dirty reset. No re-render needed.
           },
           onDeleteSuccess: function () {
             providerFormMode = null;
             editingProvider = null;
             if (window.App && window.App.router) App.router.replaceSub('providers');
             renderProvidersPanel();
           },
           getTypeDefaults: function (type) { return TYPE_DEFAULTS[type]; }
         });
       });
       return;
     }
     // Grid branch: unchanged from leg 02.
     App.admin.renderProvidersGrid(contentEl, providers, {
       selectedId: editingProvider ? editingProvider.id : null,
       onSelectProvider: selectProvider,
       onCreateProvider: enterCreateMode
     });
     fetchProviders();
   }
   ```

   **Note on async edge case**: `renderProvidersPanel` returns synchronously today; with the `ready.then()` wrapper the editor mount becomes asynchronous. Verify this doesn't break the hydrate-vs-fetch sequence. The hydrate path calls `_tryConsumePendingProvider()` → `renderProvidersPanel()`; the editor scaffold appears one tick later than the grid does, which is acceptable (matches studio's hydrate sequencing). Capture in flight log.

Verify admin.js LOC after edits is in the 700–840 range.

### Step 8: Update template

Add two `<script>` tags to the template file located in Step 1, immediately after the providers-grid.js script tag:
```html
<script src="/static/js/areas/admin/provider-editor.js"></script>
<script src="/static/js/areas/admin/provider-models.js"></script>
```

### Step 9: Update existing browser tests

1. Edit `tests/browser/test_flow_provider_setup.py`:
   - Line 47: change selector + text per #53.
   - Line 54: rename selector per #53.
   - Line 57: replace cancel-click with back-click per #53.
2. Edit `tests/browser/test_flow_provider_grid.py`:
   - Lines 55-56, 63, 65, 75, 93, 96, 103: replace `.admin-title` selectors and text per #54.
   - Line 104: replace cancel-click with back-click per #54.
   - Line 116: update fallback locator per #54.

### Step 10: Add new browser tests

Create `tests/browser/test_flow_provider_editor.py` with the 17 tests enumerated in #55. Use the existing `app_clean`, `app_with_provider`, and `app_with_agent` fixtures (verified at conftest.py:230-243). Each test follows the leg-02 style (concise, `expect()` with `timeout=5000` or `timeout=8000`). Test docstrings explain what is verified.

The agent-usage hard-block test (`test_delete_blocked_when_provider_in_use`) uses `app_with_agent`: navigate to `#admin/providers/{app.provider_id}`, click `[data-testid="delete-provider-btn"]`, assert button text contains `"Used by:"` and `app.agent_name`, assert button is disabled.

### Step 11: Run all tests

```bash
docker exec the-one pytest tests/unit/ tests/browser/ -v --tb=short
```

All must pass. Capture pass count + any unexpected fails in flight log.

### Step 12: Manual smoke + validate user requirements

Open the app in a local browser. Verify:
- Studio editor is pixel-identical (CSS lifts didn't regress studio).
- Admin/system page renders unchanged.
- Admin/providers grid renders unchanged.
- Click a provider tile → editor opens with new shape.
- Header shows provider name (not "Edit Provider"), subtitle shows type · base_url.
- Action cluster left-to-right: Back / Cancel / Save / Test.
- Save and Cancel are disabled on entry (clean form).
- Type a character → Save and Cancel both enable.
- Click Cancel → form reverts, both buttons re-disable.
- Click + New Provider → editor opens in create mode, no Test button, no Danger Zone, no Models section.
- Type a name + select a type → Save (Create) enables.
- Click Create → form transitions to edit mode, Test button + Danger Zone + Models appear, URL updates to /{id}, dirty resets.
- Click Test → spinner ("Testing…") → result appears in Connection section.
- Open an Ollama provider (if available) → Models panel renders with VRAM summary + pull/load/unload/delete-row.
- Click Delete Provider in Danger Zone → if no agents use it, button arms ("Confirm Delete?") for 3s; click again → provider deletes, returns to grid.
- Refresh the editor URL → editor re-opens with same state.

### Step 13: Update flight log

Append a leg-03 landing entry to `flight-log.md`:
- Pre-leg-03 LOCs.
- Post-leg-03 LOCs.
- Files created.
- Files deleted-from / mutated.
- Test count delta.
- Decisions (e.g. onSave callback shape choice; agent-usage test skip; any deviations).
- Manual smoke results.

### Step 14: Update leg status

Set leg artifact status from `planning` → `in-flight` at start, → `landed` at end (orchestrator handles `completed` after flight review).

## Risks + Open Questions

### R1: CSS lift regresses studio editor

**Risk**: Removing the `.area-studio` scoping from save-btn / back-btn / test-provider-btn / delete-btn / danger-zone-title rules could change studio rendering if any other rule has higher specificity.

**Mitigation**: Run `tests/browser/test_flow_agent_crud.py` + `test_flow_agent_tile.py` + `test_flow_agent_tabs.py` + `test_flow_dirty_confirm.py` post-implementation. Manual visual comparison of studio editor pre-vs-post in Step 12. Lifted rules use bare class names (e.g. `.save-btn`); studio markup already uses bare class names (no `.area-studio` prefix in markup). The lift is selector-specificity reduction — should be a no-op for the studio surface unless a competing rule exists. **Verification grep**: `grep -rn '.save-btn\|.back-btn\|.delete-btn\|.test-provider-btn\|.danger-zone' the_one/interfaces/web/static/css/` post-edit to confirm no overlapping rules remain in admin.css or studio.css.

### R2: handleProviderDelete agent-usage hard-block UX changes

**Risk**: The pre-leg-03 hard-block branch sets `btn.textContent = 'Used by: ...'` directly. In the new Danger-Zone Delete button, the testid is different (`delete-provider-btn` vs the old `.admin-provider-delete-btn`), and the wrapping element (canonical `.delete-btn` button vs the old per-tile button). Test selectors and screenshot baselines may differ.

**Mitigation**: New test in `test_flow_provider_editor.py` (`test_delete_blocked_when_provider_in_use`) explicitly verifies the hard-block UX with the new selector. Visual snapshots regenerate locally per global preference. Capture screenshots in leg 05 HAT.

### R3: Asymmetric Cancel semantics (revert vs navigate)

**Risk**: Edit-mode Cancel reverts the form; create-mode Cancel navigates to the grid. This is asymmetric and could confuse users or test authors.

**Mitigation**: Documented in this leg's design rationale (#13 in Acceptance Criteria) and mirrors studio's pattern. The Cancel button's `disabled` SSoT means it's rare for users to encounter the create-mode Cancel (Back is the visually-equivalent always-enabled escape hatch). Tests explicitly verify both branches.

### R4: Leg-03 dirty-tracking shim is incomplete (no Back-confirm dialog)

**Risk**: Users typing changes then clicking Back lose work without warning. This is a real UX gap during the leg-03 → leg-04 window.

**Mitigation**: Documented as deferred to leg 04. Leg 04 wraps `onBack` in `App.confirmDialog` (mirroring studio.js:478-498). The leg-03 → leg-04 window is internal-development-only (no commit until after leg 04 review pass per defer-commit policy); end users don't experience the gap. Capture as a `## Decisions` entry in flight log (already established as F6 design).

### R5: provider-editor.js + provider-models.js circular dependency on App.admin

**Risk**: provider-editor.js calls `App.admin.renderProviderModels`. If the script tags load out of order, the call site short-circuits.

**Mitigation**: provider-editor.js's call site checks `if (window.App.admin.renderProviderModels)` (defensive guard) and the load order in the template is: system-page.js → providers-grid.js → provider-editor.js → provider-models.js. The Models call happens at editor-mount-time (post-DOMContentLoaded, all scripts loaded). Defensive guard handles the race anyway. Verify load order in Step 8.

### R6: MASKED_SENTINEL preservation

**Risk**: The `__MASKED__` sentinel handling at admin.js:466-470 must move into the editor sub-module without regression. If lost, every save in edit mode without changing the api_key would persist the masked literal as the new key.

**Mitigation**: Step 5's "Implementation note on MASKED_SENTINEL" calls out the requirement. Acceptance criterion #15 (Save submits a payload that the backend accepts) is the functional check. Manual smoke step in Step 12 should include "edit a provider's name without changing api_key, save, verify api_key still works on Test."

### R7: Hash-route hydrate triggers async editor mount

**Risk**: `renderProvidersPanel` becomes async (waits for `providerTypesReady`). During the wait, a second hydrate could fire. The earlier render's `.then()` callback might still execute and clobber the later state.

**Mitigation**: The same race exists pre-leg-03 (`renderProviderForm` already gates on `providerTypesReady` at admin.js:297-300). Pattern is well-established. The orchestrator's state (`editingProvider`) is captured at call time — if hydrate changes it mid-flight, the in-flight render's reference is stale but the next hydrate triggers another render that supersedes. Acceptable.

### Open Question 1: `.admin-form` survival

**Question**: Is `.admin-form` (admin.css:6) still consumed post-leg-02? If the editor used `<div class="admin-form">` historically and leg 02 didn't touch it, the rule may have a surviving consumer that this leg removes.

**Resolution**: Step 1 grep verifies. If `admin-form` is referenced only by deleted markup (the editor surface rebuilt by this leg), delete the rule. Otherwise preserve. Document the decision in flight log.

### Open Question 2: Studio's `.area-studio .editor-section + .editor-section` border-top — **RESOLVED**

**Question**: studio.css:17 has `.area-studio .editor-section + .editor-section { border-top: 1px solid var(--border); padding-top: 16px; }` — the section divider. Admin's editor will have `.editor-section` siblings too; should this rule lift to components.css?

**Resolution (in-leg)**: **YES, lift to components.css un-scoped.** Admin's editor mounts three `.editor-section` blocks (Connection / Models / Danger Zone); without an unscoped rule the sections render with no padding or section-divider border. Codified in AC #43 + Step 2 + Step 3.

### Open Question 3: Test button text "Test" vs "Test Connection"

**Question**: pre-leg-03 admin uses "Test Connection". Studio uses "Test" (general-tab.js). Acceptance criterion #7 chose "Test" for cluster-size compatibility.

**Resolution**: This leg ships "Test". If the user prefers "Test Connection" they can request the change in leg 05 HAT. The data-testid stays `test-connection-btn` regardless (preserves test selectors).

### Open Question 4: Ollama lifecycle re-render on test success — **RESOLVED**

**Question**: Pre-leg-03 admin.js:540-545 auto-fetches models on test success. Should the editor sub-module call `renderProviderModels` directly, or route through an `onTestSuccess` orchestrator callback?

**Resolution (in-leg)**: **Direct call.** The editor sub-module owns the `.provider-models` host element it renders into; it can re-render it without orchestrator involvement. The Step 5 Test handler snippet has been updated accordingly. `onTestSuccess` does NOT appear on the callbacks API (AC #36).

## Verification Checklist

Implementer runs through this checklist before signaling `[HANDOFF:review-needed]`:

- [ ] `grep -rn 'admin-pf-password-wrap\|admin-pf-eye\|admin-pf-test-result\|admin-pf-testing\|admin-pf-test-ok\|admin-pf-test-fail\|admin-pf-cancel\|admin-pf-actions\|admin-pf-error\|admin-provider-form\|admin-provider-delete-confirm\|admin-pf-test\b\|admin-header\|admin-title\b' the_one/interfaces/web/static/ tests/browser/` returns ZERO matches (full sweep verification).
- [ ] `grep -rn '.admin-pf-test\|.admin-pf-error\|.admin-provider-form' the_one/interfaces/web/static/css/` returns ZERO matches.
- [ ] `grep -rn 'admin-pf-test-fail\|admin-pf-test-ok\|admin-pf-testing\|admin-pf-test-result' the_one/interfaces/web/static/js/` returns ZERO matches (JS-side substitution complete).
- [ ] `grep -n 'editor-title\|editor-subtitle\|form-actions\|back-btn\|cancel-btn\|save-btn\|test-provider-btn\|delete-btn\|danger-zone\|api-key-wrap\|api-key-eye\|test-result' the_one/interfaces/web/static/js/areas/admin/provider-editor.js` shows the canonical class names in the editor scaffold.
- [ ] `wc -l` shows admin.js in the 700–840 range, provider-editor.js in 250–320 range, provider-models.js in 380–440 range, components.css ~ 716, studio.css ~ 55, admin.css 105–115.
- [ ] Template emits 4 admin sub-module script tags in load order.
- [ ] `docker exec the-one pytest tests/unit/ -v` ≥ 413 pass, 0 fail.
- [ ] `docker exec the-one pytest tests/browser/ -v` shows test_flow_provider_editor.py with 16+ pass (1 may be skipped per #10), test_flow_provider_setup.py 1 pass, test_flow_provider_grid.py 9 pass, test_flow_admin_navigation.py 6 pass, test_flow_agent_crud.py + test_flow_agent_tile.py + test_flow_agent_tabs.py + test_flow_dirty_confirm.py + test_flow_keyboard.py all pass (no studio regressions).
- [ ] Manual smoke checklist (Step 12) all green.
- [ ] Flight log updated with landing entry, decisions, and any deviations.
- [ ] Leg status updated to `landed`.
- [ ] Signal `[HANDOFF:review-needed]`.

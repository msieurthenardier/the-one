# Leg: 04-dirty-state-and-confirm-dialog-wiring

**Status**: landed
**Flight**: [Administration Alignment](../flight.md)

## Objective

Wire `App.confirmDialog` (modal blocking-decision helper) into the provider editor's three navigation routes that can leave unsaved work behind: **Back button**, **section-nav category change** (System ↔ LLM Providers), and **`beforeunload`** (tab close / refresh / hash navigate-away). Bridge the editor sub-module's closure-local `dirty` flag to the admin orchestrator via an `onDirtyChange(dirty)` callback so the orchestrator can gate. Migrate **both** the provider-editor's `Delete Provider` and the studio agent-editor's `Delete Agent` buttons from inline two-step (`.delete-btn.confirm`) to the canonical `App.confirmDelete` helper with `confirmLabel: 'Confirm Delete?'` (capital-D label preserved for test stability + agents.md description fidelity). The `App.confirmDelete` helper now has three permanent consumers (chat session items, studio agent editor, provider editor) — graduating from "lift earned by 2 consumers" to a stable canonical destructive-confirm primitive.

## Context

This leg closes the F6 dirty-state UX gap left intentionally open by leg 03 (per AC #9: "`.back-btn` is **never** disabled (its handler will eventually wrap a dirty-confirm dialog; that wrapper lands in leg 04)") and resolves the F5 debrief Recommendation 5 question ("editor Delete migration to `App.confirmDelete`?") by migrating both editors' Delete buttons to the helper at the same time. After leg 04 lands, all autonomous work for F6 is complete; the flight enters batch review + commit + leg 05 HAT.

Five concurrent changes:

1. **Dirty bridge from editor sub-module to orchestrator** — leg 03 installed `var dirty = false; var snapshot = getFormSnapshot(...)` as closure-locals inside `wireEditorEvents` in `provider-editor.js` and wired `checkDirty()` to fire on every `input`/`change` event. The flag flips both `.save-btn[disabled]` and `.cancel-btn[disabled]` (SSoT). What leg 04 adds: `checkDirty()` also calls `callbacks.onDirtyChange(dirty)` after each flip; the admin orchestrator mirrors the flag in its own closure (`var dirty = false;` in `init()`); gate functions (`doSetCategory`, `doHandleBack`, the `beforeunload` handler) read the orchestrator's mirror.

   The mirror MUST stay in sync across editor re-renders. Specifically: when the editor re-mounts after a successful create→edit save (`callbacks.onSaveSuccess` triggers `renderProvidersPanel()` which re-invokes `App.admin.renderProviderEditor`), the previous closure's `dirty=true` state would otherwise be dangling in the orchestrator's mirror. **Solution**: orchestrator resets `dirty = false` immediately before each editor mount in `renderProvidersPanel`'s editor branch. The fresh editor closure starts with `dirty=false`, the orchestrator mirror starts with `dirty=false`, and `onDirtyChange` only fires on the first user input.

2. **`App.confirmDialog` gate on Back button** — leg 03's orchestrator wires `onBack: () => { providerFormMode = null; editingProvider = null; replaceSub('providers'); renderProvidersPanel(); }`. Leg 04 wraps the body in a dirty check, mirroring studio.js:480-497's `doHandleBack`/`handleBack` extract:
   ```js
   function doHandleBack() {
     providerFormMode = null;
     editingProvider = null;
     dirty = false;
     if (window.App && window.App.router) App.router.replaceSub('providers');
     renderProvidersPanel();
   }
   onBack: function () {
     if (dirty) {
       App.confirmDialog({ onConfirm: doHandleBack });
       return;
     }
     doHandleBack();
   },
   ```

3. **`App.confirmDialog` gate on section-nav (setCategory)** — leg 03's `setCategory(catId)` function at admin.js:116-125 directly mutates `currentCategory` + wipes provider state + `replaceSub` + re-renders. Leg 04 extracts the body into `doSetCategory(catId)` and wraps `setCategory` with the dirty check, mirroring studio.js:190-201. The gate fires only when leaving the providers-section + editor-mounted context: `dirty && currentCategory === 'providers' && providerFormMode`. The System ↔ System (no-op) and Providers grid → System (clean) cases skip the dialog.

4. **`beforeunload` listener (registered ONCE at admin init time)** — leg 03 has NO `beforeunload` handler in admin.js. Leg 04 adds one mirroring studio.js:143-149 verbatim:
   ```js
   window.addEventListener('beforeunload', function (e) {
     if (dirty) {
       e.preventDefault();
       e.returnValue = '';
       return '';
     }
   });
   ```
   Registered at admin's `init()` (admin.js:68 entry); init runs once per area lifetime per app.js's `initialized[areaId]` gate. **Do NOT remove on `deactivate()`** — the closure-flag gate handles cross-area transitions (when in studio, admin's `dirty` is `false` because the editor isn't mounted; when in admin with unsaved changes, `dirty` is `true`). Removal on deactivate would silently break tab-close protection after `chat → admin → chat` round-trips.

5. **`App.confirmDelete` migration for both editors' Delete buttons** — leg 04 migrates the two inline two-step Delete handlers (provider-editor + studio agent-editor) to consume `App.confirmDelete(deleteBtn, onConfirm, {confirmLabel: 'Confirm Delete?'})`. The helper:
   - Captures the original `[data-confirm-title]` span text on first click; replaces it with `confirmLabel`; adds `.confirm-delete` class to the parent button; sets a 3-second revert timer.
   - On second click within the window: clears the timer, invokes `onConfirm(itemEl, revertFn)`. The caller's `onConfirm` performs `fetch DELETE` and on failure calls `revertFn()` to roll back the UI.
   - Uses `.confirm-delete` (not `.confirm`) — the leg-03 `.delete-btn.confirm` CSS rule renames to `.delete-btn.confirm-delete`.
   - **Markup change**: the bare `<button>Delete Provider</button>` becomes `<button><span data-confirm-title>Delete Provider</span></button>` so the helper's `titleSelector` (default `[data-confirm-title]`) finds the inner span and replaces only the visible text — the parent button retains its event listeners and DOM identity.

   **Provider-editor's agent-usage hard-block** (preserved from leg 03; admin.js:230-289 originally, now in `provider-editor.js`'s `wireEditorEvents`'s delete handler) stays as a **pre-confirmDelete gate**: the click handler first fetches `GET /api/providers/{id}/agents`. If `agents.length > 0`, the button text becomes `"Used by: {names.join(', ')}"`, the button is disabled, `aria-live="assertive"` is set, and a 3-second timer reverts — **App.confirmDelete is NOT invoked** in this branch (it's a pure hard-block; no confirm flow). If `agents.length === 0`, the click flows into `App.confirmDelete(deleteBtn, () => fetch DELETE, {confirmLabel: 'Confirm Delete?'})`.

   The hard-block message-write must work with the new inner-span markup: instead of `deleteBtn.textContent = 'Used by: ...'`, the hard-block path writes `deleteBtn.querySelector('[data-confirm-title]').textContent = 'Used by: ...'`. The 3-second revert restores the original "Delete Provider" text the same way.

   **Studio agent-editor's Delete** at studio.js:521-548 (`handleDeleteEditor`) currently uses inline two-step. The migration:
   - studio.js's handler body becomes a single `App.confirmDelete(deleteBtn, function (btn, revertFn) { fetch DELETE; ... }, {confirmLabel: 'Confirm Delete?'})` call.
   - The agent-editor.js Delete button markup at general-tab.js:135-137 wraps the text in `<span data-confirm-title>Delete Agent</span>`.
   - Studio has no agent-usage hard-block (a different lifecycle pattern; agents that are "in use" are not gated server-side either). The migration is straightforward.

Subsequent legs depend on this leg's foundations:
- **Leg 05 (HAT)** is the interactive final leg. The HAT explicitly walks the dirty-state gate on all four routes (back/section-nav/beforeunload + the editor's own Cancel) and verifies the `App.confirmDelete` flow on both editors. Test scaffolding from leg 04 covers most of the HAT's verification but the user is the final acceptance gate.

Key prior context:
- **F5 leg 04** established the dirty-state + `App.confirmDialog` pattern for studio. studio.js:121 `var dirty = false;` closure-local; checkDirty at studio.js:693-701; gates at studio.js:190-201 (section-nav), 386-392 (selectAgent), 408-414 (enterCreateMode), 491-497 (handleBack); beforeunload at studio.js:143-149. The leg also registered the helper as a canonical primitive; `dialog.js` ships at `the_one/interfaces/web/static/js/dialog.js` (225 LOC).
- **F5 leg 02** established `App.confirmDelete` as a canonical helper (chat session items + studio agent tiles, 2 consumers at the time). **F5 HAT removed the per-tile X-button on agent tiles** (centralizing destruction in the editor's Danger Zone), dropping the helper to a single-consumer state (chat session items only). The F5 debrief Recommendation 5 documented the open question: should the helper grow back to ≥2 consumers via editor-Delete migration? F6 flight design answered yes (option 1) — restore canonical status with 3 consumers (chat session items + studio agent editor + provider editor).
- **F5 leg 04 second-pass review** established the `beforeunload` lifecycle: register ONCE at init(); do NOT remove on deactivate(). Comment block at studio.js:127-149 captures the rationale.
- **F5 HAT** removed the per-tile X-button on agent tiles (centralizing destruction in the editor's Danger Zone) — provider tiles inherited the same shape in F6 leg 02. The Danger-Zone Delete is the only path to delete from the UI.
- **Leg 03 documentation deferred to leg 04**:
  - AC #9: "`.back-btn` is **never** disabled (its handler will eventually wrap a dirty-confirm dialog; that wrapper lands in leg 04)."
  - R4 mitigation: "Documented as deferred to leg 04. Leg 04 wraps `onBack` in `App.confirmDialog` (mirroring studio.js:478-498)." (citations updated to actual lines 480-497).
  - AC #29: "The confirm class name changes from `.admin-provider-delete-confirm` (pre-leg-03) to `.delete-btn.confirm`" — leg 04 renames again to `.delete-btn.confirm-delete` (matching App.confirmDelete's class).

## Inputs

What exists before this leg runs (state at end of leg 03):

- `the_one/interfaces/web/static/js/areas/admin.js` (371 LOC):
  - `serializeState`/`hydrateState` at lines 8-66 (preserved verbatim from leg 02; no leg-04 changes).
  - `init` at line 68; closure-private state at lines 73-95 (categories, currentCategory, contentEl, providers, providerFormMode, editingProvider, pendingProviderId, pendingFormMode, PROVIDER_TYPES, providerTypesReady, fetchProviderTypes, TYPE_DEFAULTS).
  - `setCategory` at lines 116-125 — **leg 04 extracts body into `doSetCategory` and wraps with dirty gate**.
  - `App.layout.renderSectionNav` mount at lines 126-130 — preserved (the helper's `onSelect` callback receives `setCategory` reference; setCategory itself becomes the gate-wrapper).
  - `renderContent` at lines 139-145 — preserved.
  - `renderProvidersPanel` at lines 149-209 — **leg 04 modifies the editor branch (line 151-198) to**: (a) reset `dirty = false` before delegating to `renderProviderEditor`; (b) update the callbacks object to include `onDirtyChange`; (c) extract `onBack` body into `doHandleBack` + add dirty gate.
  - `fetchProviders` at lines 211-225, `populateProviderGrid` at 228-233, `selectProvider` at 237-249, `enterCreateMode` at 250-258, `findProvider` at 261-271 — preserved.
  - `showAdminFlash` at 279-281; `escapeHtml`/`escapeAttr` at 283-285 — preserved.
  - `_refresh` (290-295), `Object.defineProperty` descriptors (296-321), `_setCategory` (323-333), `_tryConsumePendingProvider` (335-358) — preserved (no leg-04 changes; the closure mirror flag is a separate var).
  - `fetchProviderTypes(); renderContent();` at lines 360-361 — preserved. **Leg 04 inserts the `beforeunload` registration** between line 95 (state declarations) and line 116 (sidebar mount) — early in `init()` so it's registered before any other side effects.
  - `activate`/`deactivate` at lines 363-371 — preserved.

- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` (439 LOC):
  - IIFE wrapper at lines 1-3, 437-438; `renderProviderEditor` exported at 437.
  - `renderProviderEditor(container, provider, providerTypes, callbacks)` at line 5; HTML scaffold + Connection / Models / Danger Zone sections.
  - `wireEditorEvents(container, provider, providerTypes, callbacks)` — internal function that wires input listeners + Back / Cancel / Save / Test / Delete handlers; contains the dirty bridge (`var dirty = false; var snapshot = getFormSnapshot(container);` and the closure-private `checkDirty` function).
  - **`checkDirty` at provider-editor.js lines 194-201 (post-leg-03)** — currently flips `.save-btn[disabled]` + `.cancel-btn[disabled]`. **Leg 04 adds**: `if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);` at the end of the function (after the disabled-flip logic).
  - **Delete handler at provider-editor.js lines 341-398 (post-leg-03)** — currently uses inline two-step `.delete-btn.confirm` flow + agent-usage hard-block + setTimeout-revert. **Leg 04 rewrites**: pre-gate stays (agent-usage check); confirm flow swaps to `App.confirmDelete(deleteBtn, onConfirm, {confirmLabel: 'Confirm Delete?'})`. Hard-block path writes message into `[data-confirm-title]` span instead of `deleteBtn.textContent`.
  - **Danger Zone HTML at provider-editor.js line 90 (post-leg-03 single-line emit)** — currently emits `<button class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="...">Delete Provider</button>`. **Leg 04 wraps text in span**: `<button class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="..."><span data-confirm-title>Delete Provider</span></button>`.

  **Step 1 of implementation must `grep -n 'checkDirty\|admin-pf-delete\|delete-btn\|Delete Provider\|querySelector.*delete\|confirm\b\|setTimeout.*delete' the_one/interfaces/web/static/js/areas/admin/provider-editor.js`** to capture exact line numbers before editing.

- `the_one/interfaces/web/static/js/areas/admin/provider-models.js` (492 LOC) — preserved. Ollama-row Delete keeps inline two-step (`.admin-pf-model-delete-confirm`) at this leg's scope; it's a different consumer (per-model rather than per-provider; arguably a candidate for App.confirmDelete migration but **out of scope for leg 04** — flight spec line 257 names the editor Delete migration only). Document as a follow-up candidate in flight log.

- `the_one/interfaces/web/static/js/areas/studio.js` (~990 LOC):
  - `var dirty = false;` at line 121 — closure-local in `init()`. **Reused as-is** (no changes).
  - `var snapshot = '';` at line 122 — closure-local. **Reused as-is**.
  - `beforeunload` listener at lines 143-149 — **Reused as-is** (pattern reference).
  - `setActiveSection` + dirty gate at lines 190-201 — **Reused as-is** (pattern reference).
  - `selectAgent` (386-392) / `enterCreateMode` (408-414) / `handleBack` (491-497) — **Reused as-is** (pattern reference for admin's setCategory + onBack restructure).
  - **`handleDeleteEditor` at studio.js:521-548** — currently uses inline two-step (`.delete-btn.confirm` + capital-D `'Confirm Delete?'` + 3s revert via setTimeout). **Leg 04 rewrites** to use `App.confirmDelete(deleteBtn, function (btn, revertFn) { fetch DELETE + .then(loadAll/select/empty), .catch(revertFn) }, {confirmLabel: 'Confirm Delete?'})`.

- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` (154 LOC):
  - Danger Zone HTML at lines 132-138 — currently emits `<button class="btn-muted-destructive delete-btn" data-testid="delete-agent-btn" data-name="...">Delete Agent</button>`. **Leg 04 wraps text in span**: `<button ...><span data-confirm-title>Delete Agent</span></button>`.

- `the_one/interfaces/web/static/js/confirm.js` (75 LOC) — **NO changes**. Used as-is. Existing `confirmLabel` parameter (line 42; default `'Confirm delete?'`) is the swap-target for the capital-D `'Confirm Delete?'` label both editors will pass.

- `the_one/interfaces/web/static/js/dialog.js` (225 LOC) — **NO changes**. Existing API (`App.confirmDialog({onConfirm, onCancel, ...})`) consumed verbatim.

- `the_one/interfaces/web/static/css/components.css` (750 LOC):
  - `.delete-btn` rule at line 585 — preserved.
  - `.delete-btn.confirm` rule at line 586 — **leg 04 renames selector to `.delete-btn.confirm-delete`** (visual identical: `background: var(--status-danger); color: var(--fg-on-danger); border-color: var(--status-danger); font-weight: var(--font-weight-semibold);`). Update the inline comment block at lines 580-583 to reference `.confirm-delete` and note "set by `App.confirmDelete` helper" instead of "set by JS".
  - `.list-item.confirm-delete` rules at lines 377-379 — preserved (existing chat session-item styling consumes the same canonical class on its parent).
  - `.modal-overlay`, `.modal-dialog`, `.modal-actions` rules at the F5-leg-04 block — preserved.

- `the_one/interfaces/web/static/css/admin.css` (121 LOC) — **NO changes**. The leg-03 deletions cleared all editor-form styles; the leg-04 changes are JS + components.css only.

- `the_one/interfaces/web/static/css/studio.css` (49 LOC) — **NO changes**.

- `tests/browser/test_flow_provider_editor.py` (~17 tests post-leg-03):
  - **Line 153**: `expect(delete_btn).to_have_class(re.compile(r"\bconfirm\b"))` — **CHANGE** to `re.compile(r"\bconfirm-delete\b")`. The button now gets the class via `App.confirmDelete` instead of inline JS.
  - **Line 152**: `expect(delete_btn).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))` — **STAYS**. The helper sets the inner `[data-confirm-title]` span's text to `confirmLabel` (passed as `'Confirm Delete?'`); the button's overall text content includes the span's text. Verify by manual smoke or adjust to `delete_btn.locator('[data-confirm-title]').to_have_text(...)`.
  - **Line 170-172** (agent-usage hard-block test): `expect(delete_btn).to_contain_text("Used by:")` + `expect(delete_btn).to_contain_text(app_with_agent.agent_name)`. The hard-block message now lives in the inner span (per the markup change). `to_contain_text` on the parent button still passes because the text is a descendant.

- `tests/browser/test_flow_agent_crud.py` (~lines 55-75 — agent delete test):
  - **Step 1 grep**: `grep -n 'delete-btn\.confirm\|\\bconfirm\\b\|Confirm Delete' tests/browser/test_flow_agent_crud.py` to enumerate every assertion that pins the inline class state. Currently captured: line 58 fetches `delete_btn = page.locator('[data-testid="delete-agent-btn"]')`. **If line 60-65 asserts `.delete-btn.confirm` class (or any `\bconfirm\b` regex)**, change to `\bconfirm-delete\b`. **If it asserts the literal text `'Confirm Delete?'`**, no change needed.
  - **Manual step in implementation**: Read the test file's delete assertions in full before editing.

- `tests/browser/test_flow_dirty_confirm.py` (~480 LOC, F5 leg 04 tests for studio) — **NO changes**. Studio's flow stays functionally identical; the editor Delete migration is a class-name-only swap that doesn't touch the dirty-state assertions.

- `tests/browser/conftest.py` — `app_clean`, `app_with_provider`, `app_with_agent` fixtures all consumed; **no changes**.

- `tests/browser/seeders.py` — **no changes**.

- `the_one/interfaces/web/static/index.html` — script-tag load order: `confirm.js` and `dialog.js` are loaded BEFORE `admin.js` (and before `provider-editor.js`). **Verify in Step 1**. If the order is wrong, the leg fails to land.

- **No backend changes**.

## Outputs

What exists after this leg completes:

- **MODIFIED** `the_one/interfaces/web/static/js/areas/admin.js`:
  - **NEW** `var dirty = false;` declaration in `init()`'s closure (alongside the existing closure-locals at the top of init, around lines 75-78).
  - **NEW** `window.addEventListener('beforeunload', ...)` registration in `init()` between the closure-state declarations and the sidebar mount (around line 96-114, mirrors studio.js:127-149 with admin-specific comment).
  - **MUTATED** `setCategory(catId)` (lines 116-125) — extracted into `doSetCategory(catId)` (the body) + `setCategory(catId)` (the gate-wrapper that checks `dirty && currentCategory === 'providers' && providerFormMode` then calls `App.confirmDialog({onConfirm: () => doSetCategory(catId)})` else `doSetCategory(catId)`).
  - **MUTATED** `renderProvidersPanel()`'s editor branch (lines 149-198):
    - Reset `dirty = false;` immediately before delegating to `renderProviderEditor` (handles the create→edit re-render reset cleanly).
    - Add `onDirtyChange: function (d) { dirty = d; }` to the callbacks object.
    - Extract `onBack` body into a helper function `doHandleBack` (closure-local in `renderProvidersPanel` or hoisted to `init`'s closure scope — implementer's choice; document the placement in flight log). Add dirty gate: `onBack: function () { if (dirty) App.confirmDialog({onConfirm: doHandleBack}); else doHandleBack(); }`.
  - **NO** changes to `onCancel`, `onSaveSuccess`, `onDeleteSuccess` — these don't need dirty gates (Cancel IS a discard; Save = not discarding; Delete is post-confirmDelete-helper).

- **MODIFIED** `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`:
  - **NEW** `if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);` line at the end of `checkDirty()` (after the existing save/cancel disabled-flip logic).
  - **MUTATED** Danger Zone HTML emit: text `Delete Provider` wrapped in `<span data-confirm-title>...</span>`.
  - **MUTATED** Delete handler: agent-usage hard-block branch unchanged in shape, but writes the "Used by:" message into `deleteBtn.querySelector('[data-confirm-title]')` instead of `deleteBtn.textContent`. The 3-second revert restores the original "Delete Provider" text via the same span. Confirm-flow branch (the no-agent path) replaced with `App.confirmDelete(deleteBtn, onConfirm, {confirmLabel: 'Confirm Delete?'})`. The `onConfirm` callback performs `fetch('/api/providers/{id}', {method: 'DELETE'})` and on failure calls `revertFn()` then writes a flash error.

- **MODIFIED** `the_one/interfaces/web/static/js/areas/studio.js`:
  - **MUTATED** `handleDeleteEditor` at lines 521-548 — replaces the inline two-step body with a single `App.confirmDelete(deleteBtn, function (btn, revertFn) { fetch DELETE; ... }, {confirmLabel: 'Confirm Delete?'})` call. The `onConfirm` callback's success path mirrors the existing post-DELETE flow (loadAll, selectAgent or renderEmptyEditor); the `.catch` calls `revertFn()` and surfaces a flash error.
  - **DELETE** the inline-revert-timer setTimeout at studio.js:544-547 (subsumed by the helper's revert timer).
  - **DELETE** the `deleteBtn.classList.add('confirm') / .textContent = 'Confirm Delete?'` lines at studio.js:542-543 (subsumed by the helper).
  - Net studio.js LOC delta: −18 to −22 lines (handleDeleteEditor shrinks from ~28 lines to ~10 lines).

- **MODIFIED** `the_one/interfaces/web/static/js/areas/studio/general-tab.js`:
  - Danger Zone HTML emit at lines 132-138: text `Delete Agent` wrapped in `<span data-confirm-title>...</span>`.

- **MODIFIED** `the_one/interfaces/web/static/css/components.css`:
  - Rule at line 586 selector `.delete-btn.confirm` → `.delete-btn.confirm-delete` (visual identical).
  - Inline comment block at lines 580-583 updated to: `Delete-btn — area-agnostic; cosmetics from .btn-muted-destructive. The .delete-btn.confirm-delete class is set by App.confirmDelete (chat session items, studio agent editor, provider editor — 3 consumers post-F6 leg 04). 3-second revert + accessibility behavior owned by the helper at confirm.js. Capital-D 'Confirm Delete?' label preserved by passing confirmLabel option.`

- **MODIFIED** `tests/browser/test_flow_provider_editor.py`:
  - Line 153 — `re.compile(r"\bconfirm\b")` → `re.compile(r"\bconfirm-delete\b")`.
  - **Optional** Line 152 — if `to_have_text(re.compile(r"Confirm Delete\?", IGNORECASE))` fails because the helper's text-replacement targets the inner span, change to `expect(delete_btn.locator('[data-confirm-title]')).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))`. Verify during test run.

- **MODIFIED** `tests/browser/test_flow_agent_crud.py`:
  - **Conditional** — Step 1 grep determines if the agent-delete test asserts inline class state. If yes, swap `\bconfirm\b` → `\bconfirm-delete\b`. If only asserting the literal text and the data-testid, no change. Capture the actual change in flight log.

- **NEW** `tests/browser/test_flow_provider_dirty_confirm.py` (~280 LOC, ~14 tests). Mirrors `tests/browser/test_flow_dirty_confirm.py`'s pattern (the F5-leg-04 studio dirty tests). Each test uses `app_with_provider` fixture and follows the structure: open editor → make form dirty → trigger navigation → assert dialog visible → cancel/confirm → assert state.

- **NO** changes to admin.css / studio.css (the only CSS change is the components.css rule rename).
- **NO** changes to backend / templates / fixtures / seeders.

## Acceptance Criteria

When this leg lands the following are all true:

### Dirty bridge

1. Admin's `init()` declares `var dirty = false;` as a closure-local variable in the same block as `currentCategory`, `providers`, etc. (around admin.js:75-78 post-leg-03).
2. `App.admin.renderProviderEditor` accepts an additional callback `onDirtyChange(dirty)` in its `callbacks` parameter. The orchestrator passes `onDirtyChange: function (d) { dirty = d; }` (closure-mirror update).
3. `provider-editor.js`'s `checkDirty()` function fires `if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);` as its LAST statement (after the disabled-attribute flips). When dirty changes from `false` to `true` (first input), the orchestrator's mirror updates synchronously. When dirty changes back to `false` (Cancel revert in edit mode, or Save success), the mirror updates synchronously.
4. Orchestrator's `renderProvidersPanel`'s editor branch resets `dirty = false;` BEFORE invoking `App.admin.renderProviderEditor(...)`. This guarantees the orchestrator mirror starts at `false` on every editor mount, regardless of prior state.
5. The mirror is the SOURCE OF TRUTH for the orchestrator's gate functions. The editor sub-module's local `dirty` flag is the SOURCE OF TRUTH for the disabled-button flip. Both reflect the same logical state via the `onDirtyChange` bridge.

### Back button gate

6. The Back button (`[data-testid="back-provider-btn"]`) handler in the orchestrator's `onBack` callback wraps the body with a dirty check. Body extracted to `doHandleBack`:
   ```js
   function doHandleBack() {
     providerFormMode = null;
     editingProvider = null;
     dirty = false;
     if (window.App && window.App.router) App.router.replaceSub('providers');
     renderProvidersPanel();
   }
   onBack: function () {
     if (dirty) {
       App.confirmDialog({ onConfirm: doHandleBack });
       return;
     }
     doHandleBack();
   }
   ```
7. When form is clean (`dirty === false`) and user clicks Back: navigation proceeds immediately (no dialog). Hash changes to `#admin/providers`. Grid renders.
8. When form is dirty (`dirty === true`) and user clicks Back: `App.confirmDialog({onConfirm: doHandleBack})` opens. Default focus on Cancel ("Stay") button.
   - Click "Stay" → onCancel; dialog closes; editor still mounted with edits intact; hash unchanged.
   - Press Escape → onCancel (per dialog.js:168-172); dialog closes; same outcome as "Stay".
   - Press Enter (from anywhere except inside a TEXTAREA, which is none in this dialog) → onConfirm fires (per dialog.js:174-184 — the Enter binding is global within the dialog, not focus-dependent); `doHandleBack` runs; navigation proceeds.
   - Click "Continue" → onConfirm; same outcome as Enter.

### Section-nav gate

9. `setCategory(catId)` body extracted into `doSetCategory(catId)`:
   ```js
   function doSetCategory(catId) {
     currentCategory = catId;
     providerFormMode = null;
     editingProvider = null;
     pendingProviderId = null;
     pendingFormMode = null;
     dirty = false;
     if (window.App && window.App.router) App.router.replaceSub(currentCategory);
     App.layout.updateActiveSection(categoryListEl, currentCategory);
     renderContent();
   }
   ```
   Wrapper:
   ```js
   function setCategory(catId) {
     var inEditor = currentCategory === 'providers' && providerFormMode;
     if (dirty && inEditor) {
       App.confirmDialog({ onConfirm: function () { doSetCategory(catId); } });
       return;
     }
     doSetCategory(catId);
   }
   ```
   Note: `doSetCategory` resets `dirty = false` because the editor unmounts (replaced by either System page or providers grid).
10. Section-nav click while in clean editor → navigates immediately, no dialog.
11. Section-nav click while in dirty editor → dialog opens. Cancel keeps editor mounted on current category. Confirm navigates.
12. Section-nav click while NOT in editor (e.g., from grid view) → no gate fires (the `inEditor` guard requires `providerFormMode` to be non-null).
13. Same-category click on the ALREADY-ACTIVE button:
    - `section-nav.js:65` fires `onSelect(catId)` unconditionally (no active-state short-circuit). Clicking the already-active "LLM Providers" button while in a dirty editor passes the wrapper's `dirty && currentCategory === 'providers' && providerFormMode` guard → opens the dialog. On Continue, `doSetCategory('providers')` runs and DOES mutate state (wipes `providerFormMode`, `editingProvider`; navigates from `#admin/providers/{id}` to `#admin/providers`; renders the grid). **This is intentional**: the user clicked a section-nav button while editing, so a discard-confirm dialog is the correct safety net even when the target is the same category — the Continue path effectively "exits the editor to its grid". Manual smoke must verify this UX feels reasonable.
    - Click on already-active section in CLEAN state (no editor) → `inEditor` guard is false → `doSetCategory` runs as no-op-ish (URL replace + render same content). Acceptable.

### beforeunload listener

14. Admin's `init()` registers a window-level `beforeunload` listener:
    ```js
    window.addEventListener('beforeunload', function (e) {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    });
    ```
    Registered ONCE per area lifetime (init runs once per app.js's initialized[areaId] gate). NOT removed on `deactivate()`. Closure-flag gate handles cross-area transitions.
15. Synthetic `beforeunload` event with `dirty === false` → `e.defaultPrevented === false` (browser does not prompt).
16. Synthetic `beforeunload` event with `dirty === true` → `e.defaultPrevented === true` (browser prompts to leave; modern browsers show generic "Leave site?" message).

### App.confirmDelete migration: provider editor

17. Provider editor's Danger Zone Delete button DOM:
    ```html
    <button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="{provider.name}">
      <span data-confirm-title>Delete Provider</span>
    </button>
    ```
18. Click handler flow:
    - **Pre-gate**: fetch `GET /api/providers/{id}/agents`. If `agents.length > 0`:
      - Write `'Used by: ' + agents.join(', ')` into `deleteBtn.querySelector('[data-confirm-title]').textContent`.
      - `deleteBtn.disabled = true`.
      - `deleteBtn.setAttribute('aria-live', 'assertive')`.
      - Set 3-second timer to restore: `disabled = false`; remove `aria-live`; `[data-confirm-title]` text restored to `'Delete Provider'`.
      - **App.confirmDelete is NOT invoked** in this branch.
    - **Confirm flow** (when `agents.length === 0` or fetch fails — fail-open per leg 03 R3):
      - Invoke `App.confirmDelete(deleteBtn, function (btn, revertFn) { fetch DELETE; ... }, {confirmLabel: 'Confirm Delete?'})`.
      - First click arms: helper adds `.confirm-delete` class to button; replaces `[data-confirm-title]` text with `'Confirm Delete?'`; sets 3s revert timer.
      - Second click within window: helper invokes `onConfirm(btn, revertFn)`. The callback:
        - `fetch('/api/providers/' + encodeURIComponent(provider.id), {method: 'DELETE'})`.
        - On 200: `App.showFlash(container, 'Provider deleted')`; `callbacks.onDeleteSuccess()`.
        - On error: `revertFn()`; `App.showFlash(container, 'Error: ' + err.message, true)`.
      - 3-second window without second click: helper auto-reverts (removes class, restores text).
19. The `.delete-btn.confirm-delete` class style applies (red background, white text) when armed. NOT `.delete-btn.confirm` (renamed in this leg).
20. Browser test `test_flow_provider_editor.py:test_delete_two_step_confirm` passes with the renamed class assertion.
21. Browser test `test_flow_provider_editor.py:test_delete_blocked_when_provider_in_use` passes — `to_contain_text("Used by:")` and `to_contain_text(app_with_agent.agent_name)` still match because the descendant span's text contributes to the parent button's text content.

### App.confirmDelete migration: studio agent editor

22. Studio agent editor's Danger Zone Delete button DOM (in `general-tab.js`):
    ```html
    <button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-agent-btn" data-name="{cfg.name}">
      <span data-confirm-title>Delete Agent</span>
    </button>
    ```
23. `studio.js`'s `handleDeleteEditor(deleteBtn)` body simplified to:
    ```js
    function handleDeleteEditor(deleteBtn) {
      var name = self._selectedAgent ? self._selectedAgent.name : null;
      if (!name) return;
      App.confirmDelete(deleteBtn, function (btn, revertFn) {
        fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
          })
          .then(function () {
            self._selectedAgent = null;
            dirty = false;
            return loadAll();
          })
          .then(function () {
            if (self._agents.length > 0) {
              selectAgent(self._agents[0]);
            } else {
              renderEmptyEditor();
              updateContentVisibility();
              writeUrl_();
            }
          })
          .catch(function (err) {
            revertFn();
            App.showFlash(editorEl, err.message || 'Delete failed', true);
          });
      }, { confirmLabel: 'Confirm Delete?' });
    }
    ```
24. Browser test `test_flow_agent_crud.py`'s agent-delete test passes (no regressions). Test selectors that asserted inline `.confirm` class state are updated to `.confirm-delete` per Step 1 grep findings.

### Test coverage

25. **NEW** `tests/browser/test_flow_provider_dirty_confirm.py` (15 tests) covers:
    - `test_back_when_clean_no_dialog` — load editor (edit, mock provider); click Back; assert no `[data-testid="confirm-dialog-overlay"]` appeared; assert hash is `#admin/providers`.
    - `test_back_when_dirty_shows_dialog` — load editor; type `"x"` into `#pf-name`; click Back; assert overlay visible.
    - `test_back_dialog_cancel_keeps_editor` — set up dialog; click `[data-testid="modal-cancel-btn"]`; assert editor still rendered (`.editor-title` visible); assert hash unchanged.
    - `test_back_dialog_confirm_navigates_to_grid` — set up dialog; click `[data-testid="modal-confirm-btn"]`; assert hash is `#admin/providers`; assert `.area-admin .page-title` text is "LLM Providers".
    - `test_section_nav_when_clean_no_dialog` — load editor (clean); click `.section-nav-item` for "System"; assert no overlay; assert hash is `#admin/system`; assert System page rendered.
    - `test_section_nav_when_dirty_shows_dialog` — load editor; type into `#pf-name`; click "System" section-nav-item; assert overlay visible.
    - `test_section_nav_dialog_cancel_keeps_editor` — set up dialog (via section-nav); click Stay; assert editor still mounted; assert hash unchanged (still on `#admin/providers/{id}`).
    - `test_section_nav_dialog_confirm_navigates_to_system` — set up dialog; click Continue; assert hash is `#admin/system`; assert System page rendered.
    - `test_section_nav_from_grid_no_dialog_even_with_dirty_in_other_path` — load editor, type into Name (dirty=true), navigate Back via dialog→Continue (returns to grid; orchestrator clears dirty); now click "System"; assert no overlay.
    - `test_save_resets_dirty` — load editor (mock provider); type into Name; click Save; assert success flash; click Back; assert no dialog (dirty was reset on save).
    - `test_cancel_button_resets_dirty_in_edit` — load editor; type into Name (form is dirty, Cancel enabled); click Cancel button (NOT Back); assert form reverts (Name input shows original); click Back; assert no dialog.
    - `test_dialog_escape_cancels` — load editor; type; click Back; press Escape; assert overlay gone; assert hash unchanged.
    - `test_dialog_enter_confirms` — load editor; type; click Back; press Enter (focus is on Cancel button — Enter triggers confirm path per dialog.js:174-184); assert overlay gone; assert hash is `#admin/providers`.
    - `test_beforeunload_when_clean_does_not_prevent` — load editor (clean); dispatch synthetic `beforeunload` via `page.evaluate`; assert `e.defaultPrevented === false`.
    - `test_beforeunload_when_dirty_prevents` — load editor; type into Name; dispatch synthetic `beforeunload`; assert `e.defaultPrevented === true`.

    Test helper boilerplate matches `test_flow_dirty_confirm.py`. Use `re.compile` for class-list assertions; use `[data-testid="confirm-dialog-overlay"]` for the modal locator.
26. `pytest tests/unit/` baseline unchanged (407 pass).
27. `pytest tests/browser/`: post-leg-03 baseline 204 + 15 new = 219 pass minimum. Slight variance acceptable.

### CSS rename

28. `the_one/interfaces/web/static/css/components.css`:
    - Line 586: `.delete-btn.confirm` → `.delete-btn.confirm-delete`. Visual UNCHANGED.
    - Lines 580-583: comment block updated to reference `.confirm-delete` and the 3-consumer canonical status.
29. `grep -rn '.delete-btn.confirm\b' the_one/interfaces/web/static/` returns ZERO matches post-leg (the `\b` boundary excludes `confirm-delete`). The class is fully retired in CSS, JS, and test selectors.

### No regressions

30. Studio's editor renders identically post-migration (the markup change is wrapping text in a span; the helper's behavior preserves the visible text and class semantics). `test_flow_agent_crud.py`, `test_flow_agent_tile.py`, `test_flow_agent_tabs.py`, `test_flow_dirty_confirm.py`, `test_flow_keyboard.py` all pass with at most the one selector-rename change in test_flow_agent_crud.py.
31. Admin's section-nav, grid, and editor render identically post-leg-04 except for the dirty-gate dialogs (which are NEW UX, not regressions).
32. Ollama lifecycle UX preserved (Ollama-row delete uses inline `.admin-pf-model-delete-confirm` — out of leg-04 scope).
33. Hash routing contracts preserved (no hydrate-state changes in leg 04).
34. `App.confirmDelete` helper has THREE permanent consumers: chat session-item delete (chat.js:433), studio agent-editor delete (studio.js:521+), provider-editor delete (provider-editor.js's delete handler).

### No backend changes

35. Zero changes to Python source. Pure frontend leg.

## Implementation Steps

### Step 1: Verify pre-conditions

```bash
cd /home/cprch/projects/the-one
wc -l the_one/interfaces/web/static/js/areas/admin.js \
       the_one/interfaces/web/static/js/areas/admin/provider-editor.js \
       the_one/interfaces/web/static/js/areas/studio.js \
       the_one/interfaces/web/static/js/areas/studio/general-tab.js \
       the_one/interfaces/web/static/css/components.css
# Expected: 371 / 439 / ~1000 / ~155 / 750
```

Capture exact pre-leg-04 LOCs. Then:

```bash
grep -n 'checkDirty\|callbacks\.onDirtyChange\|delete-btn\|Delete Provider\|Delete Agent\|admin-provider-delete-confirm\|setTimeout.*delete' \
  the_one/interfaces/web/static/js/areas/admin/provider-editor.js \
  the_one/interfaces/web/static/js/areas/studio/general-tab.js \
  the_one/interfaces/web/static/js/areas/studio.js
# Capture exact line numbers of: checkDirty (provider-editor); Delete Agent / Delete Provider markup; handleDeleteEditor
```

```bash
grep -n 'delete-btn\|confirm\|Confirm Delete' tests/browser/test_flow_agent_crud.py
# Capture exact assertions on inline-class state for the agent-delete test
```

```bash
grep -n 'admin/\|areas/admin' the_one/interfaces/web/static/index.html
grep -n 'confirm.js\|dialog.js' the_one/interfaces/web/static/index.html
# Verify confirm.js + dialog.js load BEFORE admin.js / provider-editor.js
```

If any pre-condition fails (script-tag order wrong, line numbers diverge from this leg's citations), capture in flight log before proceeding.

### Step 2: Add beforeunload + dirty closure-local to admin.js init

Edit `the_one/interfaces/web/static/js/areas/admin.js`. Add `var dirty = false;` to the closure-locals block (next to other vars around line 75-78). Add the `beforeunload` listener registration immediately after the closure-locals block, before the sidebar mount:

```js
// ── beforeunload listener (F6 leg 04) ──────────────────────────────
//
// Registered ONCE at init() time (init runs once per area lifetime,
// gated by app.js's initialized[areaId] check). The closure `dirty`
// flag is the sole gate — when in another area, dirty is false (the
// editor isn't mounted); when in admin with an unsaved provider edit,
// dirty is true and the listener calls e.preventDefault() to surface
// the browser's native "Leave site?" prompt.
//
// Do NOT remove on deactivate() — closure-flag gate handles all cross-
// area transitions. Mirrors studio.js:127-149.
window.addEventListener('beforeunload', function (e) {
  if (dirty) {
    e.preventDefault();
    e.returnValue = '';
    return '';
  }
});
```

### Step 3: Restructure setCategory with dirty gate

Edit `setCategory` at admin.js:116-125 to extract its body into `doSetCategory(catId)`, then redefine `setCategory(catId)` as the gate-wrapper. The result:

```js
function doSetCategory(catId) {
  currentCategory = catId;
  providerFormMode = null;
  editingProvider = null;
  pendingProviderId = null;
  pendingFormMode = null;
  dirty = false;
  if (window.App && window.App.router) App.router.replaceSub(currentCategory);
  App.layout.updateActiveSection(categoryListEl, currentCategory);
  renderContent();
}
function setCategory(catId) {
  // Dirty gate fires only when leaving providers + editor-mounted context.
  // Same-category clicks short-circuit naturally (no state change).
  var inEditor = currentCategory === 'providers' && providerFormMode;
  if (dirty && inEditor) {
    App.confirmDialog({ onConfirm: function () { doSetCategory(catId); } });
    return;
  }
  doSetCategory(catId);
}
```

### Step 4: Restructure renderProvidersPanel's editor branch with dirty bridge + gate on Back

Edit `renderProvidersPanel` (admin.js:149+). The editor branch becomes:

```js
function renderProvidersPanel() {
  if (providerFormMode) {
    // Reset orchestrator's dirty mirror BEFORE editor mount. The fresh
    // editor closure starts clean; onDirtyChange only fires on user input.
    dirty = false;

    var ready = providerTypesReady || fetchProviderTypes();
    ready.then(function () {
      function doHandleBack() {
        providerFormMode = null;
        editingProvider = null;
        dirty = false;
        if (window.App && window.App.router) App.router.replaceSub('providers');
        renderProvidersPanel();
      }
      App.admin.renderProviderEditor(contentEl, editingProvider, PROVIDER_TYPES, {
        onBack: function () {
          if (dirty) {
            App.confirmDialog({ onConfirm: doHandleBack });
            return;
          }
          doHandleBack();
        },
        onCancel: function () {
          // Create-mode Cancel: navigate back to grid. Cancel-when-dirty
          // is intentional discard — no dialog.
          providerFormMode = null;
          editingProvider = null;
          dirty = false;
          if (window.App && window.App.router) App.router.replaceSub('providers');
          renderProvidersPanel();
        },
        onSaveSuccess: function (updated, isCreate) {
          editingProvider = updated;
          providerFormMode = 'edit';
          dirty = false; // Save cleared dirty (sub-module recaptures snapshot).
          if (window.App && window.App.router) {
            App.router.replaceSub(self.serializeState());
          }
          if (isCreate) {
            renderProvidersPanel();
          }
        },
        onDeleteSuccess: function () {
          providerFormMode = null;
          editingProvider = null;
          dirty = false;
          if (window.App && window.App.router) App.router.replaceSub('providers');
          renderProvidersPanel();
        },
        onDirtyChange: function (d) { dirty = d; },
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

### Step 5: Wire onDirtyChange in provider-editor.js

Edit `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`. Locate `checkDirty` (in `wireEditorEvents`; Step-1 grep captured the exact line). Append at the end of the function body:

```js
function checkDirty() {
  var current = getFormSnapshot(container);
  dirty = current !== snapshot;
  var saveBtn = container.querySelector('.save-btn');
  var cancelBtn = container.querySelector('.cancel-btn');
  if (saveBtn) saveBtn.disabled = !dirty;
  if (cancelBtn) cancelBtn.disabled = !dirty;
  if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty); // F6 leg 04 bridge
}
```

Also: when the Save success path resets `snapshot = getFormSnapshot(container); dirty = false; checkDirty();` (per leg-03 step 5 line 712-714), the trailing `checkDirty()` already fires `onDirtyChange(false)` — no extra wiring needed. Same for the Cancel revert path.

### Step 6: Mark up Delete buttons with [data-confirm-title] span

Edit `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`. In the Danger Zone HTML emit (locate via Step-1 grep — currently emits `<button class="btn-muted-destructive delete-btn" ...>Delete Provider</button>`):

```js
html += '<button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="' + escapeAttr(provider.name || '') + '"><span data-confirm-title>Delete Provider</span></button>';
```

Edit `the_one/interfaces/web/static/js/areas/studio/general-tab.js`. Apply the same wrap at lines 135-137:

```js
html += '<button type="button" class="btn-muted-destructive delete-btn" ' +
  'data-testid="delete-agent-btn" data-name="' + escapeAttr(cfg.name || '') + '">' +
  '<span data-confirm-title>Delete Agent</span></button>';
```

### Step 7: Migrate provider-editor.js Delete handler to App.confirmDelete

In `provider-editor.js`'s `wireEditorEvents`'s Delete handler (locate via Step-1 grep), rewrite the body. Pre-leg-04 has both the agent-usage hard-block branch AND the inline two-step confirm flow. The new body keeps the agent-usage pre-gate and replaces the confirm flow with the helper:

```js
var deleteBtn = container.querySelector('.delete-btn');
if (deleteBtn && isEdit) {
  var deleteHardBlockTimer = null;
  var deleteTitleEl = deleteBtn.querySelector('[data-confirm-title]');
  deleteBtn.addEventListener('click', function () {
    // OQ2 RESOLUTION: explicit "already armed → commit" branch removed.
    // App.confirmDelete (confirm.js:58-67) handles the second-click commit
    // internally when the button already has the .confirm-delete class —
    // calling it again with the same itemEl invokes onConfirm directly.
    // The agent-usage pre-gate fetch on the second click is wasted work but
    // functionally harmless (no side effects; result is ignored on the
    // commit path because the helper's class check beats us to onConfirm).
    //
    // Pre-gate: agent-usage hard-block.
    fetch('/api/providers/' + encodeURIComponent(provider.id) + '/agents')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var agents = data.agents || [];
        if (agents.length > 0) {
          // Hard-block: write into the title span, disable, 3s revert.
          if (deleteTitleEl) deleteTitleEl.textContent = 'Used by: ' + agents.join(', ');
          deleteBtn.disabled = true;
          deleteBtn.setAttribute('aria-live', 'assertive');
          if (deleteHardBlockTimer) clearTimeout(deleteHardBlockTimer);
          deleteHardBlockTimer = setTimeout(function () {
            deleteBtn.disabled = false;
            deleteBtn.removeAttribute('aria-live');
            if (deleteTitleEl) deleteTitleEl.textContent = 'Delete Provider';
          }, 3000);
        } else {
          // No agent usage: arm via App.confirmDelete.
          window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
        }
      })
      .catch(function () {
        // Network failure on agent-usage check: fail open — arm anyway.
        window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
      });
  });

  function doDelete(btn, revertFn) {
    fetch('/api/providers/' + encodeURIComponent(provider.id), { method: 'DELETE' })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
        window.App.showFlash(container, 'Provider deleted');
        if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
      })
      .catch(function (err) {
        revertFn();
        window.App.showFlash(container, 'Error: ' + err.message, true);
      });
  }
}
```

**Note on simplification**: OQ2 is resolved in-leg — the explicit "already armed" branch has been removed from the snippet above. The helper handles second-click commit internally (confirm.js:58-67). The minor cost is a wasted `GET /agents` fetch on the second click within 3s; functionally harmless.

### Step 8: Migrate studio.js handleDeleteEditor to App.confirmDelete

Edit `the_one/interfaces/web/static/js/areas/studio.js`. Replace the body of `handleDeleteEditor` (lines 521-548) with:

```js
function handleDeleteEditor(deleteBtn) {
  var name = self._selectedAgent ? self._selectedAgent.name : null;
  if (!name) return;
  App.confirmDelete(deleteBtn, function (btn, revertFn) {
    fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
      })
      .then(function () {
        self._selectedAgent = null;
        dirty = false;
        return loadAll();
      })
      .then(function () {
        if (self._agents.length > 0) {
          selectAgent(self._agents[0]);
        } else {
          renderEmptyEditor();
          updateContentVisibility();
          writeUrl_();
        }
      })
      .catch(function (err) {
        revertFn();
        App.showFlash(editorEl, (err && err.message) || 'Delete failed', true);
      });
  }, { confirmLabel: 'Confirm Delete?' });
}
```

The function shrinks from ~28 lines to ~22 lines. Update the comment block at studio.js:515-520 — replace the "NOT migrated to App.confirmDelete (intentional)" rationale with "Migrated to App.confirmDelete in F6 leg 04 (helper now has 3 permanent consumers)."

### Step 9: Rename .delete-btn.confirm CSS rule

Edit `the_one/interfaces/web/static/css/components.css`. At line 586, change selector from `.delete-btn.confirm` to `.delete-btn.confirm-delete`. Visual unchanged. Update the comment block at lines 580-583:

```css
/* Delete-btn — area-agnostic; cosmetics from .btn-muted-destructive.
   The .delete-btn.confirm-delete class is set by App.confirmDelete
   (chat session items, studio agent editor, provider editor — 3 consumers
   post-F6 leg 04). 3-second revert + accessibility behavior owned by the
   helper at confirm.js. The capital-D 'Confirm Delete?' label is preserved
   by passing the confirmLabel option per call site. */
.delete-btn { padding: 6px 14px; border-radius: 6px; font-size: var(--font-size-body-sm); }
.delete-btn.confirm-delete { background: var(--status-danger); color: var(--fg-on-danger); border-color: var(--status-danger); font-weight: var(--font-weight-semibold); }
```

### Step 10: Update existing tests

Edit `tests/browser/test_flow_provider_editor.py` line 153: change `re.compile(r"\bconfirm\b")` to `re.compile(r"\bconfirm-delete\b")`.

Edit `tests/browser/test_flow_agent_crud.py` per Step-1 grep findings. If a test asserts `\bconfirm\b` class on the delete button, change to `\bconfirm-delete\b`. If only the data-testid + text are asserted, no change.

If `test_flow_provider_editor.py:152` (`to_have_text(re.compile(r"Confirm Delete\?", IGNORECASE))`) starts failing because the helper writes into the inner span only, change to `expect(delete_btn.locator('[data-confirm-title]')).to_have_text(re.compile(r"Confirm Delete\?", re.IGNORECASE))`. Determine empirically during test run.

### Step 11: Create test_flow_provider_dirty_confirm.py

Create `tests/browser/test_flow_provider_dirty_confirm.py`. Use `tests/browser/test_flow_dirty_confirm.py` as the structural template. The 14 tests (per AC #25) cover back/section-nav/beforeunload routes + dialog Cancel/Confirm/Escape/Enter + Save-resets-dirty + Cancel-resets-dirty + clean-bypass.

Skeleton:
```python
"""End-to-end flow tests: provider editor dirty-state + App.confirmDialog modal (F6 leg 04).

Mirrors test_flow_dirty_confirm.py (F5 leg 04 studio dirty-confirm tests) for
the provider editor's three navigation gates (Back, section-nav, beforeunload).

Covers:
- Back-when-clean does not show dialog.
- Back-when-dirty shows dialog; cancel keeps editor; confirm navigates to grid.
- Section-nav-when-clean does not show dialog.
- Section-nav-when-dirty shows dialog; cancel keeps editor; confirm navigates.
- beforeunload listener: synthetic event with dirty=true → defaultPrevented.
- Save resets dirty (subsequent Back has no dialog).
- Cancel button resets dirty in edit mode (revert + Back has no dialog).
- Dialog Escape dismisses; Enter confirms (focus on Cancel button at open).
"""

from __future__ import annotations
import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_back_when_clean_no_dialog(app_with_provider: SeededApp, page: Page) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator(".editor-title")).to_be_visible(timeout=8000)
    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)


@pytest.mark.browser
def test_back_when_dirty_shows_dialog(app_with_provider: SeededApp, page: Page) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers/{app_with_provider.provider_id}")
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    page.locator("#pf-name").fill("dirty-edit")
    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=3000)


# ... 12 more tests following the AC #25 list ...
```

Implementer fills in the remaining 12 tests using the AC list as the spec.

### Step 12: Run all tests

```bash
docker exec the-one pytest tests/unit/ tests/browser/ -v --tb=short
```

Expected: 407 unit + 218+ browser pass. If `test_flow_dirty_confirm.py` (studio's tests) fails, it indicates the studio Delete migration broke; investigate.

### Step 13: Manual smoke

Open the app in a local browser. Verify:
- Studio: edit an agent, type a change, click Back → dialog appears (no regression). Click Stay → editor stays. Click Continue → returns to agents grid.
- Studio: edit an agent, click Delete Agent → button arms (`Confirm Delete?` label, red bg). Click again → agent deletes. Verify no class regression.
- Admin: open System page, switch to LLM Providers → no dialog. Click a provider tile → editor opens. Type a change → Save/Cancel enable. Click Back → dialog appears. Click Stay → editor stays. Click Continue → returns to grid. Hash returns to `/providers`.
- Admin: open editor again, type a change. Click "System" in section-nav → dialog appears. Click Stay → editor stays, hash unchanged. Click Continue → System page renders, hash = `/system`.
- Admin: open editor (clean — fresh load). Click "System" in section-nav → no dialog (clean form bypasses gate).
- Admin: edit a provider, type, click Cancel → form reverts, dirty cleared. Click Back → no dialog (form is clean).
- Admin: edit a provider, type, hit Ctrl+R or close tab → browser shows native "Leave site?" prompt.
- Admin: delete a provider via Danger Zone → button arms (`Confirm Delete?` label, `.confirm-delete` class). Click again → provider deletes, returns to grid.
- Admin: try to delete a provider that has agents using it → button shows `Used by: {names}`, disabled, 3s revert. No confirm flow fires. App.confirmDelete is not invoked.

### Step 14: Update flight log + leg status

Append a leg-04 landing entry to `flight-log.md`. Capture:
- Pre/post LOCs.
- Files mutated.
- Test count delta.
- Decisions: `doHandleBack` placement (orchestrator closure vs. inner closure); explicit-second-click-branch retained or removed.
- Any deviations.
- Manual smoke results.

Update leg artifact status `planning` → `in-flight` at start, → `landed` at end.

## Risks + Open Questions

### R1: Dirty mirror desync after editor re-render

**Risk**: The orchestrator's mirror could go out of sync with the editor sub-module's local `dirty` flag if the editor closure replaces (e.g., create→edit transition) without a corresponding `onDirtyChange` callback firing.

**Mitigation**: AC #4 mandates the orchestrator resets `dirty = false` BEFORE every editor mount (in `renderProvidersPanel`'s editor branch). The fresh editor closure starts at `dirty=false`; its `checkDirty()` only fires after user input. Synthesized: orchestrator-mirror is reset at editor-mount-time; editor sub-module's flag is reset at editor-mount-time (closure init); they converge. Verified by the `test_save_resets_dirty` test.

### R2: App.confirmDelete second-click semantics on already-armed button

**Risk**: The pre-gate fetch `GET /agents` is async. If the user clicks twice quickly, the second click may arrive before the first's fetch resolves. The current spec branches on `deleteBtn.classList.contains('confirm-delete')` to detect "already armed" but the helper sets that class on first call — there's a race where the button is in mid-fetch state with no class yet.

**Mitigation**: The helper's contract is idempotent — calling `App.confirmDelete(itemEl, ...)` when the class is already set commits; calling when not set arms. The pre-gate fetch ALSO needs guard: if a fetch is in-flight, skip the new click. Add a closure `var deletePending = false;` flag set at fetch start, cleared in `.then`/`.catch`. Click handler returns early if `deletePending`. Document in flight log. **Alternative (simpler)**: skip the explicit "already armed" branch entirely — let `App.confirmDelete` handle the second click directly. The user's first click goes through the agent-usage check; the second click bypasses (already armed → commits via the helper). This works because once armed, the button is in the helper's state, and a subsequent call short-circuits to commit. Implement this simpler version.

### R3: Studio agent delete broke by markup change

**Risk**: Wrapping the button text in `<span data-confirm-title>` changes the DOM that existing studio tests may rely on. `test_flow_agent_crud.py` may locate the button by text content using `:has-text("Delete Agent")` or similar — Playwright treats descendant text as locator-eligible, so this should still work, but verify.

**Mitigation**: Step 1 grep enumerates all delete-related assertions in `test_flow_agent_crud.py`. If any assert direct `textContent === 'Delete Agent'` (vs. `to_contain_text('Delete Agent')`), update to use the inner-span locator. Run full test suite in Step 12.

### R4: Hash routing dirty gate not implemented

**Risk**: Hash hydration (browser back/forward, manual URL change) bypasses the dirty gate. User with unsaved edits could navigate via URL change and lose work without prompt.

**Mitigation**: This matches studio's pattern — `hydrateState` does not dirty-gate. Programmatic gating of hash changes is awkward (URL has already changed; reverting it is jarring). Documented as scope-out for leg 04. The HAT (leg 05) flags this as an acceptable behavior trade-off; if the user wants gating-on-hash, that's a future-flight scope.

### R5: tile-click while dirty (N/A in admin's full-swap layout)

**Risk**: The flight spec line 259 mentions "tile-click when dirty" as a gated route. In admin's full-swap layout (post-leg-02), tiles are not visible while editing — only Back returns to the grid. The tile-click gate is architecturally unreachable.

**Mitigation**: Not implemented. Documented in this leg's Context section. If a future flight switches admin to a sidebar layout (parallel to studio), the gate can be added then.

### R6: beforeunload double-registration on hot reload

**Risk**: In dev, if admin's `init()` runs more than once (e.g., hot-module-reload simulating area-init), multiple `beforeunload` listeners would stack. Each would test the same `dirty` flag (same closure for hot-reload? possibly different closures for module-reload), potentially showing the prompt multiple times.

**Mitigation**: app.js's `initialized[areaId]` gate prevents double-init in production. In dev, `Cmd+R` is a fresh page load — no double-registration. Hot-module-reload is not used in this codebase. Acceptable; matches studio's pattern. Document if any anomaly surfaces in HAT.

### Open Question 1: `doHandleBack` placement

**Question**: Should `doHandleBack` be defined inside `renderProvidersPanel`'s `ready.then(...)` block (closure-local to the editor mount, captures `editingProvider` and other state at that moment) or hoisted to admin's `init()` closure (single shared instance)?

**Resolution**: Inside `ready.then` is simpler — no state-capture concerns since the body uses orchestrator closure-locals (`providerFormMode`, `editingProvider`, `dirty`) which are mutated globally. Either works. **Implementer's choice; document in flight log**.

### Open Question 2: Remove the explicit "already armed" branch in provider-editor.js Delete handler? — **RESOLVED**

**Question**: Step 7's snippet originally had `if (deleteBtn.classList.contains('confirm-delete')) { App.confirmDelete(deleteBtn, doDelete, ...); return; }` as an explicit second-click branch. Was this needed?

**Resolution (in-leg)**: **REMOVED.** Confirmed by direct read of `confirm.js:58-67`: when the helper is called with an item that already has `.confirm-delete`, it invokes `onConfirm` directly and returns. The agent-usage pre-gate fetch on the second click is functionally harmless (single GET, results ignored on commit path because the helper's class-check fires first). Step 7's snippet has been updated.

### Open Question 3: Apply App.confirmDelete to Ollama-row Delete?

**Question**: Ollama models in `provider-models.js` use inline `.admin-pf-model-delete-confirm` two-step. Should leg 04 migrate that too?

**Resolution**: Out of scope. Flight spec line 257 names the editor Delete migration only. Ollama-row Delete is a different consumer (per-model rather than per-provider) with its own UX timing (delete is destructive but routinely-used; the agent-usage analog doesn't exist). Document as a follow-up candidate in flight log; revisit in F7 or routine maintenance.

## Verification Checklist

Implementer runs through this checklist before signaling `[HANDOFF:review-needed]`:

- [ ] `grep -rn 'admin-pf-password-wrap\|admin-pf-eye\|admin-pf-test-result\|admin-pf-testing\|admin-pf-test-ok\|admin-pf-test-fail\|admin-pf-cancel\|admin-pf-actions\|admin-pf-error\|admin-provider-form\|admin-provider-delete-confirm\|admin-pf-test\b\|admin-header\|admin-title\b' the_one/interfaces/web/static/ tests/browser/` returns ZERO matches (leg-03 sweep still holds).
- [ ] `grep -rPn '\.delete-btn\.confirm(?!-)' the_one/interfaces/web/static/ tests/browser/` returns ZERO matches (leg-04 rename complete). **Note**: must use Perl-compatible negative-lookahead (`-P` + `(?!-)`); plain `\bconfirm\b` would still match `confirm-delete` because `-` is a non-word char that satisfies the trailing word-boundary.
- [ ] `grep -rn 'admin-pf-test-fail\|admin-pf-test-ok\|admin-pf-testing\|admin-pf-test-result' the_one/interfaces/web/static/js/` returns ZERO matches (leg-03 substitution still holds).
- [ ] `grep -n 'App.confirmDelete' the_one/interfaces/web/static/js/areas/` returns 3 call sites: chat.js, studio.js (handleDeleteEditor), admin/provider-editor.js (delete handler).
- [ ] `grep -n 'App.confirmDialog' the_one/interfaces/web/static/js/areas/` returns admin.js + studio.js call sites (admin: 2 — onBack + setCategory; studio: existing 4).
- [ ] `wc -l` shows admin.js in the 380-410 range (was 371; +20-30 lines for dirty + beforeunload + setCategory restructure + onBack restructure); provider-editor.js 440-460 (was 439; small delta for onDirtyChange + Delete rewrite); studio.js delta of −15 to −20 lines (handleDeleteEditor shrinks); general-tab.js delta of +1-2 lines (span wrap); components.css unchanged total LOC (rule rename only).
- [ ] `docker exec the-one pytest tests/unit/ -v` ≥ 407 pass, 0 fail.
- [ ] `docker exec the-one pytest tests/browser/ -v` ≥ 219 pass (post-leg-03 baseline 204 + 15 new dirty-confirm tests). `test_flow_dirty_confirm.py` (studio's tests) all pass — no regressions.
- [ ] Manual smoke checklist (Step 13) all green.
- [ ] Flight log updated with landing entry, decisions (doHandleBack placement, explicit-branch removal, etc.), and any deviations.
- [ ] Leg status updated `planning` → `in-flight` → `landed`.
- [ ] Signal `[HANDOFF:review-needed]`.

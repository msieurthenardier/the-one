# Leg: 04-dirty-state-and-confirm-dialog

**Status**: completed
**Started**: 2026-04-27
**Completed**: 2026-04-27
**Flight**: [Studio Alignment](../flight.md)

## Objective

Build out the save / back / dirty-state UX. Create a NEW `App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` modal helper in `static/js/dialog.js` (~100-130 LOC) with full Tab/Shift-Tab focus-trap, Escape cancel, Enter confirm, and restore-focus-on-close. Replace the existing two `window.confirm(...)` sites at `studio.js:346-347` (in `selectAgent`) and `studio.js:377-378` (in `enterCreateMode`) with `App.confirmDialog` async-restructured calls. Wire the dirty-check gate into the new navigation paths introduced by legs 01-03: Back button (handleBack), section-nav click (`onSelect` callback in studio.js's section-nav wiring), and tab click (`onChange`/`onBeforeChange` hook on `App.tabs`). Make the Save button truly `disabled` (not just class-toggled) when `!dirty`. Add a `beforeunload` listener registered ONCE at studio area `init()` time that reads the closure `dirty` flag and prevents tab close when dirty (via the browser-native dialog — the only way to intercept tab close).

Land canonical `.modal-overlay`, `.modal-dialog`, `.modal-actions` primitives in `components.css`. `.modal-actions` composes onto `.form-actions` (both right-aligned button rows).

## Context

- Legs 01-03 have landed. Studio.js is now 928 LOC. **The dirty-tracking infrastructure already exists** from leg 03: closure variables `dirty` (line 121) and `snapshot` (line 122); `checkDirty()` function at line 631; `getFormSnapshot()` for JSON-stringified comparison; `input`/`change` listeners wired on `.field-input`/`.field-textarea`/`.field-select`/`.tool-toggle` selectors at line 588-593; baseline snapshot captured at line 425-426; `dirty = false` reset on save success at line 724, 751, plus on selectAgent/enterCreateMode/handleBack/deleteAgentInline at 324, 365, 383, 451, 471. **Leg 04 builds on this — it does NOT introduce dirty tracking from scratch.**
- The Save button currently toggles `.clean`/`.dirty` CSS classes via `checkDirty()` (line 635-636) but is NOT `disabled` when clean. Leg 04 makes Save actually `disabled` (so click is blocked, focus skips it, screen-readers announce it as disabled) and **removes the parallel class-toggle machinery** — `disabled` becomes the single source of truth. Existing CSS rules at `studio.css:53-54` (`.save-btn.clean { opacity: 0.4 }` + `.save-btn.dirty { opacity: 1 }`) migrate to `[disabled]` selectors.
- Existing `window.confirm` guards live ONLY in `selectAgent` (studio.js:346-347) and `enterCreateMode` (studio.js:377-378). The `handleBack` function at studio.js:448-456 has NO dirty check today — it unconditionally clears state. Leg 04 adds the gate.
- Tile-click already routes through `selectAgent` (per leg 02), so the dirty gate inherits there for free. No additional wiring needed for tile clicks.
- `App.tabs` (leg 03) is unconditional: clicking a tab calls `activate(clickId)` synchronously, which fires `onChange(tabId)`. There is NO existing hook to interject "user wants to change tabs but we need to confirm first." Leg 04 must add an optional `onBeforeChange(tabId, commit)` hook to `App.tabs` (or wrap at the consumer level — the leg picks the helper-level hook for cleanest abstraction).
- `App.studio.renderSectionNav` (leg 01) is similarly unconditional — `onSelect(sectionId)` fires synchronously. Leg 04 either: (a) wraps `onSelect` at the consumer (studio.js's section-nav wiring) to interject the dirty check before calling `setActiveSection`, OR (b) adds an `onBeforeSelect` hook to the helper. Option (a) is preferred — section-nav already returns control to studio.js's wiring, which is the right place to add navigation-side guards. No helper-API changes needed for section-nav.
- For `App.tabs`, the helper-API extension is the cleanest path — see Implementation step 3.
- The flight spec's resolved Open Question "`App.confirmDialog` focus-trap depth" specifies **full Tab + Shift-Tab cycling** (not just steal-on-open + restore-on-close). On dialog open, query all focusable descendants; track `firstFocusable` and `lastFocusable`; on `keydown` Tab + activeElement === lastFocusable, prevent default + focus first; on Shift+Tab + activeElement === firstFocusable, prevent default + focus last. WAI-ARIA 1.2 says modal dialogs SHOULD trap Tab; achievable in ~30 LOC.
- Adaptation criteria from the flight spec: if full Tab cycling proves problematic, fall back to minimal trap (steal-on-open + restore-on-close + Escape only) and document the residual gap as a NEW item in the flight's Known Issues — not just a future debrief recommendation.
- The flight spec's resolved Open Question "`beforeunload` scope and lifecycle" specifies: register ONCE at `init()` time (init runs once per area lifetime, gated by `app.js:109-186` initialized[areaId] check); do NOT remove on `deactivate()` (deactivate runs on every cross-area transition, so removing there would break tab-close protection after a chat → studio → chat round-trip). The closure `dirty` flag is the sole gate. When in another area, `dirty` stays false because the editor isn't mounted; when in studio with unsaved changes, `dirty` is true and the listener calls `e.preventDefault(); e.returnValue = ''`.
- The flight spec's resolved Open Question "`window.confirm` migration in existing studio.js sites" specifies the async restructure pattern: `if (dirty) App.confirmDialog({onConfirm: () => doNavigate(target)}); else doNavigate(target);` — the click handler dispatches the dialog and the dialog's `onConfirm` callback invokes the real navigation; `onCancel` is a no-op (stays put).
- `App.confirmDialog` API mirrors the F5 helper-naming convention (`App.confirmDelete` from leg 02 is in-place two-step; `App.confirmDialog` is modal blocking decision). Both are exported on `window.App`.

## Inputs

What exists before this leg runs (post-leg-03 state):

- `the_one/interfaces/web/static/js/areas/studio.js` (928 LOC):
  - `dirty` closure variable at line 121; `snapshot` at line 122.
  - `getFormSnapshot()` and `checkDirty()` at lines 626-639.
  - `input`/`change` listeners at lines 588-593.
  - Baseline snapshot at line 425-426 (after `renderEditor` returns).
  - `selectAgent(agent)` at line 322+, with `window.confirm` guard at 346-347.
  - `enterCreateMode()` at line 363+, with `window.confirm` guard at 377-378.
  - `handleBack()` at line 448-456 — unconditional state clear; no dirty check.
  - `deleteAgentInline()` at line 463+ (unchanged from leg 02; uses `App.confirmDelete`).
  - Save handler `save(isCreate)` at line 705-769 — clears `dirty = false` on success.
  - Section-nav wiring in studio.js (around line 158-162) — calls `App.studio.renderSectionNav(container, active, {onSelect: ...})`. The `onSelect` callback calls `setActiveSection`. This is where the section-nav dirty gate inserts.
  - Tab wiring via `App.studio.renderAgentEditor(...)` and the inner `App.tabs(...)` helper from agent-editor.js. The `onChange` callback (passed by agent-editor.js to App.tabs) fires after activation.
  - `init()` body lives at studio.js:105-921. `activate()` at line 924-926; `deactivate()` at 927.
  - Editor element reference `editorEl` (closure) — passed to `App.showFlash(editorEl, msg, isError)`.
- `the_one/interfaces/web/static/js/tabs.js` (124 LOC, leg 03):
  - `App.tabs(tablistEl, panelsEl, opts)` — `opts = {onChange?, initial?}`. Click and Enter/Space both call `activate(clickId)` synchronously, then `onChange(tabId)` fires after activation. **Helper has NO `onBeforeChange` hook today.** Leg 04 adds one.
- `the_one/interfaces/web/static/js/areas/studio/section-nav.js` (102 LOC, leg 01):
  - `App.studio.renderSectionNav(container, active, options)` — `options.onSelect(sectionId)`. Click and Enter/Space fire `onSelect` synchronously. **No helper-API changes in leg 04** — the dirty gate inserts at the studio.js consumer.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` (158 LOC, leg 03) — wires `App.tabs(tablistEl, panelsEl, {onChange: callbacks.onTabChange, initial: callbacks.initialTab || 'general'})` (around line 95-105). Leg 04 wraps the `onTabChange` callback OR passes a new `onBeforeChange` hook from studio.js through the callbacks bag.
- `the_one/interfaces/web/static/js/confirm.js` (75 LOC, leg 02) — `App.confirmDelete(itemEl, onConfirm, opts)`. Reference for callback-style helper exports.
- `the_one/interfaces/web/static/js/app.js`: `App.showFlash(container, msg, isError)` at line 220-236; `App.router.replaceSub` (used by studio's `_writeUrl`).
- `the_one/interfaces/web/static/css/components.css` (605 LOC, post-leg-03):
  - `.form-actions` (right-aligned button cluster) — leg 03 canonical. `.modal-actions` will compose onto it.
  - NO existing `.modal-*` classes.
  - F4 + leg 01 + leg 02 + leg 03 vocabulary present (`.btn-filled-cyan`, `.btn-outlined-cyan`, `.btn-muted-destructive`, `.field-row`, etc.).
- `the_one/interfaces/web/static/css/tokens.css`: `--accent`, `--accent-glow`, `--accent-translucent`, `--surface`, `--surface-elevated`, `--border`, `--panel-shadow`, `--panel-radius`, `--status-danger`, `--fg`, `--fg-on-accent`. Modal styling uses these.
- `the_one/interfaces/web/static/index.html` post-leg-03 script load order:
  - `app.js`, `icons.js`, `markdown.js`, `confirm.js`, `tabs.js`, chat sub-helpers, `chat.js`, studio sub-helpers (4: section-nav, stub-knowledge, stub-tools, agent-editor), `general-tab.js`, `knowledge-tab.js`, `tools-tab.js`, `studio.js`, `admin.js`. Leg 04 inserts `dialog.js` after `confirm.js` (logically grouped with other dialog-helper modules).
- `the_one/agents.md` §Design system → "Affordance vocabulary" — entries from legs 01-03: Section navigation, Agent tile, Confirm-delete, Tab idiom, Editor header, Form actions, Test result.

## Outputs

- `the_one/interfaces/web/static/js/dialog.js` — NEW. Defines `App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` (~100-130 LOC). Modal with full focus-trap (Tab/Shift-Tab cycle), Escape-cancel, Enter-confirm, restore-focus-on-close. Returns `void` (callback-driven).
- `the_one/interfaces/web/static/js/tabs.js` — MODIFIED. Add `onBeforeChange(tabId, commit)` hook to `opts`. When provided, the click and Enter/Space paths call `onBeforeChange(tabId, commit)` instead of `activate(tabId)` directly. The consumer (studio.js, via agent-editor.js's `callbacks.onBeforeTabChange` bag) inspects the dirty flag and either calls `commit()` to proceed or dispatches `App.confirmDialog` with `commit` wrapped in `onConfirm`. **API extension is additive** — when `onBeforeChange` is omitted, behavior is unchanged (existing leg-03 tests continue passing).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — MODIFIED. Plumb `callbacks.onBeforeTabChange` through to `App.tabs`'s `onBeforeChange`. ~5-10 LOC added.
- `the_one/interfaces/web/static/js/areas/studio.js` — MODIFIED:
  - **Replace `window.confirm` at studio.js:346-347** (selectAgent dirty-check). Restructure `selectAgent` to check `if (dirty) { App.confirmDialog({onConfirm: () => doSelect(agent)}); return; } doSelect(agent);` — extract the existing select body into `doSelect(agent)`. Same pattern.
  - **Replace `window.confirm` at studio.js:377-378** (enterCreateMode). Same restructure: `if (dirty) { App.confirmDialog({onConfirm: () => doEnterCreateMode()}); return; } doEnterCreateMode();`.
  - **Add dirty gate to `handleBack()`** at studio.js:448-456: `if (dirty) { App.confirmDialog({onConfirm: doHandleBack}); return; } doHandleBack();`.
  - **Add dirty gate to section-nav `onSelect` callback** wiring (around studio.js:158-162): `onSelect: (sectionId) => { var commit = () => setActiveSection(sectionId); if (dirty && this._activeSection === 'agents' && this._selectedAgent) { App.confirmDialog({onConfirm: commit}); } else { commit(); } }`. The dirty gate only fires when leaving the Agents-section + selected-agent context (no point gating Knowledge → Tools transitions; there's no editor mounted).
  - **Pass `callbacks.onBeforeTabChange`** to `renderAgentEditor`: `onBeforeTabChange: (tabId, commit) => { if (dirty) { App.confirmDialog({onConfirm: commit}); } else { commit(); } }`. Since the editor + dirty are scoped to a selected agent, the onBeforeChange firing implies an active editing session — the dirty-gate semantics are clear.
  - **Make Save truly disabled when clean**: REPLACE the class-toggle pattern in `checkDirty()` (studio.js:635-636) with `saveBtn.disabled = !dirty;` — single source of truth. Drop the `.clean`/`.dirty` class assignments entirely (the class machinery is removed in this leg per AC). Initial mount: agent-editor.js emits the Save button with `disabled` already set (see step 5 below).
  - **Add `beforeunload` listener** at the top of `init()` (after the closure-local declarations, before any DOM building). Register once: `window.addEventListener('beforeunload', function (e) { if (dirty) { e.preventDefault(); e.returnValue = ''; return ''; } });`. The closure `dirty` flag is the gate; when in another area, dirty is false (editor isn't mounted, listeners haven't fired). Do NOT remove the listener on `deactivate()`.
  - Net delta: +30 to +60 LOC; new total ~960-990.
- `the_one/interfaces/web/static/css/components.css` GROWS (~50-80 LOC):
  - `.modal-overlay` — `position: fixed; inset: 0; background: <token, semi-transparent>; z-index: <high>; display: flex; align-items: center; justify-content: center;`. Click on overlay (outside the dialog) calls `onCancel` (or no-op — Edge Cases).
  - `.modal-dialog` — `<token>` background (`--surface-elevated`), border, border-radius, padding, max-width (e.g., 480px), shadow, focus ring on `:focus-visible`. The dialog has `role="dialog"` and `aria-modal="true"`.
  - `.modal-dialog-title` (or use `.section-title` from F4) — title typography.
  - `.modal-dialog-message` — body typography; line-height for readable paragraphs.
  - `.modal-actions` — composes onto `.form-actions` (`@extends`-style: `.modal-actions { /* mirror form-actions */ }` OR class-list both classes on the actions container — pick the simpler one and document). Right-aligned button cluster.
- `the_one/interfaces/web/static/index.html` — `+1 line`: `<script src="/static/js/dialog.js"></script>` after `confirm.js` (currently line 29).
- `the_one/agents.md` — adds 2 entries to §Design system → "Affordance vocabulary":
  - "Confirm dialog (modal)" — `App.confirmDialog({...})` API + the `.modal-overlay`/`.modal-dialog`/`.modal-actions` primitives + the focus-trap contract + the Escape/Enter keyboard contract + restore-focus-on-close behavior.
  - "Beforeunload guard" — register-once-in-area-init pattern, closure-flag-as-gate; explicitly contrasts with `deactivate()` (which would break tab-close protection after cross-area round-trips).
- New tests `tests/browser/test_flow_dirty_confirm.py` — covers AC items 1-15 below (~250-350 LOC, ~12-15 tests).
- All existing tests pass (407 unit + 155 browser baseline; targeting ≥ 167 browser after leg 04: 155 + 12 new).

## Acceptance Criteria

- [x] **`App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` helper** in `static/js/dialog.js` (~100-130 LOC). Defaults: `title = 'Unsaved changes'`, `message = 'You have unsaved changes. Continue without saving?'`, `confirmText = 'Continue'`, `cancelText = 'Stay'`. (The wording avoids the false-promise of "Discard" — leg 04 does NOT auto-revert form state on confirm; it only proceeds with navigation. See Edge Cases.) Behavior:
  - Renders `<div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="..." aria-describedby="...">` containing `<div class="modal-dialog">` with title + message + `<div class="modal-actions form-actions">` containing Cancel + Confirm buttons (in that order so Confirm is rightmost — natural primary action position).
  - On open: appends to `document.body`, captures `document.activeElement` as the trigger (for restore-on-close), focuses the Confirm button (or Cancel — pick the safer default; recommend Cancel for destructive-discard prompts).
  - **Full focus-trap**: queries all focusable descendants on open; tracks `firstFocusable` and `lastFocusable`; on `keydown` with `Tab` + `activeElement === lastFocusable`, preventDefault + focus first; on `Shift+Tab` + `activeElement === firstFocusable`, preventDefault + focus last.
  - On `Escape` key: calls `onCancel()` then `close()`.
  - On `Enter` key (when focus is on a button or in the dialog body but not in a textarea): calls `onConfirm()` then `close()`.
  - Click on Confirm button: `onConfirm()` then `close()`.
  - Click on Cancel button: `onCancel()` then `close()`.
  - Click on overlay (outside dialog): no-op (does NOT call `onCancel`; require explicit Cancel/Escape — prevents accidental dismissal). Document this choice.
  - On close: removes overlay from DOM, restores focus to the captured trigger (`captured.focus()`).
  - Idempotent on rapid double-invocation: calling `App.confirmDialog` while one is already open is a no-op + emits `console.warn('App.confirmDialog: already open; second call ignored.')`. The warn surfaces spurious double-dispatch during dev/test without crashing or queuing.
- [x] **`App.tabs` `onBeforeChange` hook**: optional `opts.onBeforeChange(tabId, commit)`. When provided, replaces the inline `activate(tabId)` call in BOTH the click handler (tabs.js click event) AND the Enter/Space keyboard activation handler (tabs.js keydown — currently around lines 95-99). Both paths must wrap. The consumer calls `commit()` to proceed (synchronously or after async user interaction). When `onBeforeChange` is omitted, behavior is unchanged. Leg-03 tests pass without modification. Arrow-key navigation does NOT call `onBeforeChange` — only commits go through.
- [x] **selectAgent dirty gate** at studio.js:346-347: replace `window.confirm` with `App.confirmDialog({onConfirm: () => doSelect(agent)})`. Existing test behavior: `selectAgent` with dirty + cancel keeps state; dirty + confirm discards and selects. The async restructure is behavior-preserving.
- [x] **enterCreateMode dirty gate** at studio.js:377-378: same restructure.
- [x] **handleBack dirty gate**: when `dirty === true`, click on Back triggers `App.confirmDialog`. On cancel, no state change. On confirm, navigates to `#studio/agents` (clears `_selectedAgent`, `_createMode`, `_activeTab`, `dirty`; calls `_writeUrl()`). Browser test asserts both paths.
- [x] **Section-nav dirty gate**: clicking a section button (Agents/Knowledge/Tools) when dirty + selected-agent triggers `App.confirmDialog`. The gate ONLY fires when leaving the Agents-section + selected-agent context (so Knowledge → Tools transitions, or any transition with no agent selected, do NOT prompt). On cancel: stays. On confirm: switches section. Browser test covers both paths.
- [x] **Tab dirty gate**: clicking a tab (General/Knowledge/Tools within the editor) when dirty triggers `App.confirmDialog`. On cancel: stays on current tab; URL unchanged; aria-selected unchanged. On confirm: switches tab; URL updates; aria-selected updates. The `onBeforeChange` hook is wired through `App.tabs`. Keyboard activation (Enter/Space) follows the same path. Arrow-key navigation (manual-activation) does NOT trigger the dialog (arrow keys only move focus, not activation).
- [x] **Save button truly `disabled` when clean** (single source of truth): `agent-editor.js` emits the Save button as `<button class="btn-filled-cyan save-btn" disabled>` (drop the existing `clean` class — it's redundant once `disabled` is the canonical state). `checkDirty()` toggles `saveBtn.disabled` to mirror the `dirty` flag (true → enabled, false → disabled). The `.clean`/`.dirty` class machinery is REMOVED in this leg; CSS rules that depended on those classes (if any) migrate to `[disabled]` / `:not([disabled])` selectors. Browser test asserts `expect(save_btn).to_be_disabled()` initially and `expect(save_btn).to_be_enabled()` after typing in a field; on save success, `disabled = true` again.
- [x] **`beforeunload` listener registered ONCE in `init()`**: at the top of the init body. Listener body: `if (dirty) { e.preventDefault(); e.returnValue = ''; return ''; }`. Do NOT remove on `deactivate()`. Verify by browser test that dispatching a synthetic `beforeunload` event when dirty results in `event.defaultPrevented === true`; when clean, `defaultPrevented === false`. (Headless Chromium suppresses the native browser dialog; the synthetic-event-with-defaultPrevented assertion is the reliable signal.)
- [x] **All four dirty-trigger paths verified** in browser tests:
  - (1) Back-when-dirty
  - (2) Section-nav-click-when-dirty (selected-agent context)
  - (3) Tile-click-when-dirty (which routes through `selectAgent` — already gated)
  - (4) Tab-click-when-dirty
  - For each: confirm path discards + navigates; cancel path keeps state.
- [x] **Modal full Tab/Shift-Tab focus-trap verified**: open the dialog, Tab cycles forward through focusable descendants and wraps; Shift+Tab cycles backward and wraps. Browser test asserts the cycle (focus equals first after Tab from last; focus equals last after Shift+Tab from first).
- [x] **Modal restore-focus on close verified**: trigger the dialog from a known button (e.g., Back), confirm/cancel/Escape; verify `document.activeElement` is the original Back button after close.
- [x] **Modal Escape and Enter keyboard contract verified**: Escape closes via `onCancel`; Enter (when not in a textarea/input that would consume it) confirms via `onConfirm`.
- [x] **Modal ARIA contract verified**: the overlay carries `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing at the title element, `aria-describedby` pointing at the message element. Browser test asserts presence of all four attributes.
- [x] **Clean state does NOT trigger any dialogs**: Back-when-clean, section-nav-when-clean, tile-when-clean, tab-when-clean — all navigate immediately without modal interruption. Browser test covers each.
- [x] **`beforeunload` clean-state behavior**: synthetic `beforeunload` event when clean has `defaultPrevented === false` (verified via the `page.evaluate` pattern documented in step 7).
- [x] **Class composition documented**: `.modal-actions` + `.form-actions` — pick one approach (multi-class on the container OR one class as canonical with the other as alias) and document in agents.md. Recommended: container has `class="modal-actions form-actions"` (multi-class), so `.form-actions` rules apply unchanged.
- [x] **Single `App.router.replaceSub` call site preserved** in studio.js (`grep` returns 1 match, in `writeUrl_`).
- [x] **All existing tests pass**: `pytest --timeout=60 tests/` exactly 407, `pytest --timeout=120 -m browser tests/browser/` ≥ 167 (155 baseline + 12+ new).
- [x] **agents.md updated**: 2 new entries (Confirm dialog modal, Beforeunload guard).
- [x] **Adaptation criteria honored**: if full Tab focus-trap proves problematic, fall back to minimal trap and document the residual gap in the flight's Known Issues (mission-level), not just a debrief item.
- [x] Flight log updated with `### 04-dirty-state-and-confirm-dialog` progress entry.
- [x] This leg's status set to `landed`.

## Verification Steps

- `pytest --timeout=60 tests/` — passes baseline (exactly 407).
- `pytest --timeout=120 -m browser tests/browser/` — passes ≥ 167.
- `pytest --timeout=120 -m browser tests/browser/test_flow_dirty_confirm.py` — new file, passes.
- `pytest --timeout=120 -m browser tests/browser/test_flow_agent_crud.py` — passes (Save now `disabled` initially; tests must wait for dirty → enabled before clicking Save, OR the existing test pattern already types into fields before clicking Save, which would naturally pass; verify).
- `pytest --timeout=120 -m browser tests/browser/test_flow_agent_tabs.py` — passes (Arrow-key tab navigation still moves focus only; only Enter/Space + click activations dispatch the dialog when dirty).
- `pytest --timeout=120 -m browser tests/browser/test_flow_studio_navigation.py` — passes (section-nav dirty gate is additive; clean-state navigation unchanged).
- `pytest --timeout=120 -m browser tests/browser/test_flow_hash_routing.py` — passes (URL writes unchanged; the `_writeUrl` single-call-path discipline preserved).
- Manual browser check: open `#studio/agents/{some-agent}` → type into the system-prompt textarea → click Back → modal appears → click Cancel → state preserved + URL unchanged → click Back again → click Discard → navigates to `#studio/agents`. Repeat for section-nav, tile-click, tab-click. Try closing the tab while dirty → native dialog appears. Refresh a clean editor → no dialog.
- `wc -l the_one/interfaces/web/static/js/dialog.js` — ~100-130 LOC.
- `wc -l the_one/interfaces/web/static/js/areas/studio.js` — ≤ 990.
- `wc -l the_one/interfaces/web/static/css/components.css` — grows by ~50-80 LOC.
- `grep -n 'window.confirm' the_one/interfaces/web/static/js/areas/studio.js` — returns 0 matches (both sites migrated).

## Implementation Guidance

1. **Create `the_one/interfaces/web/static/js/dialog.js`** with the `App.confirmDialog` helper.
   - Module pattern: `(function (window, document) { ... window.App = window.App || {}; window.App.confirmDialog = function (opts) { ... }; })(window, document);`
   - Implementation outline:
     ```
     var openDialog = null; // singleton — second call no-ops while one is open

     App.confirmDialog = function (opts) {
       if (openDialog) {
         console.warn('App.confirmDialog: already open; second call ignored.');
         return;
       }
       opts = opts || {};
       var title = opts.title || 'Unsaved changes';
       var message = opts.message || 'You have unsaved changes. Continue without saving?';
       var confirmText = opts.confirmText || 'Continue';
       var cancelText = opts.cancelText || 'Stay';
       var onConfirm = opts.onConfirm || function () {};
       var onCancel = opts.onCancel || function () {};

       var trigger = document.activeElement;

       var overlay = document.createElement('div');
       overlay.className = 'modal-overlay';
       overlay.setAttribute('role', 'dialog');
       overlay.setAttribute('aria-modal', 'true');

       var dlg = document.createElement('div');
       dlg.className = 'modal-dialog';
       overlay.appendChild(dlg);

       var titleId = 'modal-title-' + Date.now();
       var msgId = 'modal-msg-' + Date.now();
       overlay.setAttribute('aria-labelledby', titleId);
       overlay.setAttribute('aria-describedby', msgId);

       var titleEl = document.createElement('h2');
       titleEl.className = 'modal-dialog-title';
       titleEl.id = titleId;
       titleEl.textContent = title;
       dlg.appendChild(titleEl);

       var msgEl = document.createElement('p');
       msgEl.className = 'modal-dialog-message';
       msgEl.id = msgId;
       msgEl.textContent = message;
       dlg.appendChild(msgEl);

       var actions = document.createElement('div');
       actions.className = 'modal-actions form-actions';
       dlg.appendChild(actions);

       var cancelBtn = document.createElement('button');
       cancelBtn.type = 'button';
       cancelBtn.className = 'btn-outlined-cyan';
       cancelBtn.textContent = cancelText;
       cancelBtn.setAttribute('data-testid', 'modal-cancel-btn');
       actions.appendChild(cancelBtn);

       var confirmBtn = document.createElement('button');
       confirmBtn.type = 'button';
       confirmBtn.className = 'btn-filled-cyan';
       confirmBtn.textContent = confirmText;
       confirmBtn.setAttribute('data-testid', 'modal-confirm-btn');
       actions.appendChild(confirmBtn);

       function close() {
         document.removeEventListener('keydown', onKey, true);
         overlay.remove();
         openDialog = null;
         if (trigger && typeof trigger.focus === 'function') trigger.focus();
       }

       cancelBtn.addEventListener('click', function () { onCancel(); close(); });
       confirmBtn.addEventListener('click', function () { onConfirm(); close(); });

       function focusables() {
         var nodes = dlg.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
         var arr = Array.prototype.slice.call(nodes);
         return arr.filter(function (n) { return !n.disabled; });
       }

       function onKey(e) {
         if (e.key === 'Escape') { e.preventDefault(); onCancel(); close(); return; }
         if (e.key === 'Enter') {
           if (e.target && e.target.tagName === 'TEXTAREA') return; // let textareas keep newlines
           e.preventDefault(); onConfirm(); close(); return;
         }
         if (e.key === 'Tab') {
           var fs = focusables();
           if (fs.length === 0) { e.preventDefault(); return; }
           var first = fs[0], last = fs[fs.length - 1];
           if (e.shiftKey && document.activeElement === first) {
             e.preventDefault(); last.focus();
           } else if (!e.shiftKey && document.activeElement === last) {
             e.preventDefault(); first.focus();
           }
         }
       }

       document.addEventListener('keydown', onKey, true);

       openDialog = { close: close };
       document.body.appendChild(overlay);

       // Focus Cancel by default — safer for destructive-discard prompts.
       cancelBtn.focus();
     };
     ```
   - Note: `document.addEventListener('keydown', ..., true)` uses capture phase so the modal sees keys before any field listeners. This prevents a focused field's keydown handler from interfering.
   - **Adaptation note**: if the focus-trap implementation runs to >120 LOC, fall back to a minimal trap (steal-on-open + restore-on-close + Escape only) and add a NEW item to the flight's `Known Issues` section in `mission.md` (per the flight spec's adaptation criteria).

2. **Add `dialog.js` to index.html** between `confirm.js` (currently line 29) and `tabs.js`. Single line.

3. **Extend `App.tabs` with `onBeforeChange` hook** in `static/js/tabs.js`:
   - Add `var onBeforeChange = opts.onBeforeChange || null;` near the top.
   - Replace the click handler body (around the helper's `tabs[i].addEventListener('click', ...)`) with:
     ```
     var clickId = ...; // existing tab-id resolution
     if (onBeforeChange) {
       onBeforeChange(clickId, function () { activate(clickId); });
     } else {
       activate(clickId);
     }
     ```
   - Replace the Enter/Space keyboard activation in `onKey` similarly. Arrow-key navigation (focus-only) does NOT call `onBeforeChange` — only commits go through it.
   - **Behavior preservation**: when `onBeforeChange` is omitted, existing behavior is identical.
   - Verify leg-03 tests pass without modification.

4. **Plumb `callbacks.onBeforeTabChange` through `agent-editor.js`**:
   - Where `App.tabs(tablistEl, panelsEl, {onChange: ..., initial: ...})` is called, add `onBeforeChange: callbacks.onBeforeTabChange`.
   - Pass-through; no logic in agent-editor.

5. **Update studio.js** with the dirty-gate restructures and Save-disabled changes:
   - Extract the bodies of `selectAgent` and `enterCreateMode` past their dirty-checks into named functions `doSelect(agent)` and `doEnterCreateMode()`. Replace the `window.confirm` pattern with the async dialog pattern. Apply the same restructure to `handleBack` (extract `doHandleBack()`).
   - **Drop the `clean`/`dirty` class machinery from `checkDirty()`** (currently at studio.js:635-636) — `disabled` becomes the single source of truth. Replace the existing two `classList.toggle(...)` lines with: `saveBtn.disabled = !dirty;`. **CSS migration**: `studio.css:53-54` contains `.area-studio .save-btn.clean { opacity: 0.4 }` + `.area-studio .save-btn.dirty { opacity: 1 }` (verified the only consumers in the codebase). Replace with `.area-studio .save-btn[disabled] { opacity: 0.4 }` + `.area-studio .save-btn:not([disabled]) { opacity: 1 }` (or simply rely on the browser's default `:disabled` styling and remove both rules — pick whichever preserves the desired visual emphasis).
   - **Update `agent-editor.js`** to emit the Save button initially as `<button class="btn-filled-cyan save-btn" disabled type="button" data-testid="save-agent-btn">Save</button>` — drop the `clean` class from the initial render. The post-mount `checkDirty()` call leaves it disabled (clean snapshot); the first form input fires a `checkDirty()` that flips `disabled = false`.
   - In the section-nav wiring (around studio.js:158-162), wrap the existing `onSelect: setActiveSection` callback:
     ```
     onSelect: function (sectionId) {
       var commit = function () { self.setActiveSection(sectionId); };
       var inEditingContext = self._activeSection === 'agents' && self._selectedAgent;
       if (dirty && inEditingContext) {
         App.confirmDialog({ onConfirm: commit });
       } else {
         commit();
       }
     }
     ```
   - In the agent-editor callbacks bag (where `renderAgentEditor` is called), add `onBeforeTabChange`:
     ```
     onBeforeTabChange: function (tabId, commit) {
       if (dirty) {
         App.confirmDialog({ onConfirm: commit });
       } else {
         commit();
       }
     }
     ```
   - Update `checkDirty()` at studio.js:631-639 to also toggle `saveBtn.disabled = !dirty`.
   - Set `saveBtn.disabled = true` at the spot where the editor first mounts (after baseline snapshot capture at line 425-426; the Save button DOM is built in agent-editor.js, so this needs a hook — either query the editor for `[data-testid="save-agent-btn"]` and set `.disabled = true` after render, or have agent-editor.js emit the Save button as `disabled` initially and let `checkDirty()` lift it on first input).
   - Add the `beforeunload` listener at the top of `init()`:
     ```
     window.addEventListener('beforeunload', function (e) {
       if (dirty) {
         e.preventDefault();
         e.returnValue = '';
         return '';
       }
     });
     ```

6. **Add CSS to `components.css`** (`@layer components`):
   - `.modal-overlay` — fixed full-screen, semi-transparent backdrop (use `--surface` with low alpha or a dedicated `--overlay-bg` token if available; otherwise hand-roll with `rgba(0, 0, 0, 0.5)` or similar), z-index 200+, flex-center the dialog.
   - `.modal-dialog` — `--surface-elevated` background, `--border` 1px, `--panel-radius`, `--panel-shadow`, padding (e.g., 24px), max-width 480px, min-width 320px, focus ring on inner focus.
   - `.modal-dialog-title` — typography (e.g., font-size 1.25rem, font-weight 600, margin-bottom 8px).
   - `.modal-dialog-message` — typography (line-height 1.5, margin-bottom 24px).
   - `.modal-actions` — `display: flex; gap: <token>; justify-content: flex-end;` — same as `.form-actions`. With multi-class composition (`class="modal-actions form-actions"`), this can be empty or just enforce nothing (an alias). Document the choice.
   - Animation (optional): fade-in on overlay, scale-in on dialog. Skip if it pushes scope.

7. **Browser tests** — write `tests/browser/test_flow_dirty_confirm.py` with ~12-15 tests covering the AC list. Pattern after `test_flow_agent_tabs.py` (leg 03). Tests:
   - `test_save_button_disabled_when_clean`
   - `test_save_button_enabled_after_field_change`
   - `test_back_when_dirty_opens_dialog_cancel_keeps_state`
   - `test_back_when_dirty_opens_dialog_confirm_navigates`
   - `test_section_nav_when_dirty_opens_dialog`
   - `test_tile_click_when_dirty_opens_dialog`
   - `test_tab_click_when_dirty_opens_dialog`
   - `test_arrow_keys_in_tablist_do_not_open_dialog_even_when_dirty`
   - `test_modal_focus_trap_tab_cycles_forward`
   - `test_modal_focus_trap_shift_tab_cycles_backward`
   - `test_modal_escape_cancels_and_restores_focus`
   - `test_modal_enter_confirms` (with focus on Confirm button)
   - `test_clean_state_does_not_open_dialog_for_any_path`
   - `test_beforeunload_listener_registered_when_dirty` — assert via `page.evaluate('!!window.onbeforeunload || dispatchEvent fires preventDefault')` that the listener exists and a synthetic `beforeunload` event with `dirty=true` calls `preventDefault()`. (Headless Chromium suppresses the actual native dialog event in `page.on('dialog', ...)`, so direct dialog-event assertions are fragile.)
   - `test_beforeunload_does_not_prevent_when_clean` — synthesize a `beforeunload` event when `dirty === false` and assert `event.defaultPrevented === false`.
   
   **Playwright beforeunload assertion pattern**: prefer `page.evaluate` to dispatch a synthetic `beforeunload` event and inspect `event.defaultPrevented` rather than relying on `page.close({ runBeforeUnload: true })` + `page.on('dialog', ...)` — the latter is suppressed in headless mode. Example: `await page.evaluate(() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; })` returns `true` when dirty, `false` when clean.

8. **Update `agents.md`** with 2 new entries under §Design system → "Affordance vocabulary":
   - "Confirm dialog (modal)" — `App.confirmDialog({...})` API + `.modal-overlay`/`.modal-dialog`/`.modal-actions` primitives + focus-trap contract + Escape/Enter contract + restore-focus-on-close + click-overlay-no-op rationale.
   - "Beforeunload guard" — register-once-in-init pattern, closure-flag-as-gate, do-NOT-remove-on-deactivate rationale.

9. **Run tests**: `pytest --timeout=60 tests/` (407 expected) and `pytest --timeout=120 -m browser tests/browser/` (≥ 167 expected).

10. **Update flight log** — `### 04-dirty-state-and-confirm-dialog` progress entry with timestamps + Changes Made + Notes.

11. **Set leg status to `landed`**. Do NOT commit. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Singleton modal**: only one dialog open at a time. Second `App.confirmDialog(...)` call while one is open: no-op + `console.warn`. The `openDialog` module-level variable enforces this; the warn surfaces spurious double-dispatch (e.g., a stray race between handlers) without crashing.
- **Tile X-button delete on a dirty selected agent**: `deleteAgentInline` at studio.js:316-341 (the X-button delete on a tile) does NOT prompt the confirm dialog when the deleted agent is the currently-selected dirty one. **Deliberate non-gate**: the X-button is itself a destructive two-step `App.confirmDelete` flow with explicit user intent; layering an additional "you have unsaved changes" modal on top would be UX clutter (and the user is explicitly opting into a destructive action that obviously discards everything about that agent, including unsaved edits). This is a deliberate scope decision; documented in agents.md to avoid ambiguity for future flights.
- **Click outside dialog (on overlay)**: by spec, no-op (does NOT trigger `onCancel`). This prevents accidental loss of work. Document in agents.md.
- **Enter inside textarea/input doesn't consume to confirm**: the focus-trap's `onKey` checks `e.target.tagName === 'TEXTAREA'` (and possibly INPUT for plain text inputs) and returns early — Enter inside the textarea inserts a newline, doesn't confirm. This matters less for confirmDialog (its body is just text), but the helper is the modal primitive — future modals may have form fields.
- **Trigger element is a tile X-button or other not-yet-focused-element**: `document.activeElement` at dialog-open captures the trigger correctly. After close, focus restores. If the trigger was removed from the DOM (e.g., the deleted tile), `trigger.focus()` is a no-op (browser default focus to body). Acceptable.
- **Tab dirty gate when multi-tab editing**: changing a Tools-tab checkbox marks dirty; clicking the General tab triggers the dialog; on cancel, stay on Tools (URL unchanged); on confirm, switch to General (URL updates, the change persists in `collectFormData()` snapshot if it was committed elsewhere — but the user explicitly said "discard," so the form revert depends on the pattern: `confirmDialog` doesn't revert form state itself; the navigation just moves the active tab; the in-DOM form state stays. **Decision**: leg 04 does NOT auto-revert form state on confirm — the dirty flag persists; subsequent saves still capture all changes; subsequent navigations re-prompt. The "discard" wording is technically a misnomer in this leg — it's "discard navigation guard," not "revert all form values." Document in agents.md. A future flight could add true form-revert.
- **Confirmation: actually rephrasing "Discard"**: given the above, the modal's confirmText defaults to "Discard" but the semantic is "proceed with navigation; keep my form changes in DOM but don't try to save them." Pick wording carefully — recommended: title "Unsaved changes", message "You have unsaved changes. Continue without saving?", confirm "Continue", cancel "Stay". This is more accurate than "Discard" and avoids the false-promise problem.
- **`beforeunload` Chromium behavior**: modern browsers ignore the custom `returnValue` string and show a generic "Leave site?" dialog. `e.preventDefault()` + `e.returnValue = ''` is the modern incantation.
- **`beforeunload` test in Playwright**: Playwright requires `page.close({ runBeforeUnload: true })` to fire `beforeunload`. Default `page.close()` skips it. Document the test pattern.
- **Section-nav gate fires only with selected-agent context**: Knowledge → Tools transitions (no agent) don't prompt. Tile-click within Agents section already routes through `selectAgent` (gated). What about Knowledge → Agents (no agent selected on entry to Agents)? No editor mounted, dirty stays false; no prompt. Correct.
- **Tab gate keyboard interactions**: Enter/Space on a tab dispatches `onBeforeChange` (per the helper extension). Arrow keys do NOT — only commits go through. This preserves the manual-activation contract from leg 03.
- **`window.confirm` removal verification**: post-leg-04, `grep -n 'window.confirm' studio.js` returns 0 matches. (`confirm` without `window.` prefix is also banned — grep for both.)
- **Focus-trap with no focusable elements**: edge case where the dialog has no focusable descendants (impossible per the helper's structure — at minimum Cancel + Confirm exist). Defensive: if `focusables()` returns empty, prevent default Tab and don't move focus.
- **Multiple beforeunload listeners**: if any other module also adds a beforeunload listener, both fire. The listener body short-circuits when `dirty === false`, so it's safe — other listeners run independently. Document.
- **Screen-reader announcements**: the modal has `role="dialog"` + `aria-modal="true"` + `aria-labelledby` + `aria-describedby` — screen readers announce title + message on open. Verify via NVDA or VoiceOver during HAT (leg 05).

## Files Affected

- `the_one/interfaces/web/static/js/dialog.js` — NEW (~100-130 LOC).
- `the_one/interfaces/web/static/js/tabs.js` — `+5-10 LOC` (`onBeforeChange` hook).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — `+3-5 LOC` (callbacks plumbing).
- `the_one/interfaces/web/static/js/areas/studio.js` — `+30-60 LOC` (4 dirty-gate sites + `beforeunload` listener + Save disabled toggle); new total ~960-990.
- `the_one/interfaces/web/static/css/components.css` — `+50-80 LOC` (`.modal-overlay`, `.modal-dialog`, `.modal-dialog-title`, `.modal-dialog-message`, `.modal-actions`).
- `the_one/interfaces/web/static/index.html` — `+1 line` (`<script src="/static/js/dialog.js"></script>`).
- `tests/browser/test_flow_dirty_confirm.py` — NEW (~250-350 LOC, ~12-15 tests).
- `the_one/agents.md` — `+~25 LOC` under §Design system → "Affordance vocabulary".
- `missions/04-ui-maturity/flights/05-studio-alignment/flight-log.md` — leg progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Flight Director defers commit to flight-end review (single review pass after this leg).**

- [x] All acceptance criteria verified
- [x] All existing tests passing (`pytest --timeout=60 tests/` = 407, `pytest --timeout=120 -m browser tests/browser/` ≥ 167)
- [x] New tests passing (`test_flow_dirty_confirm.py`)
- [x] All four dirty-trigger paths covered (Back, section-nav, tile-click via selectAgent, tab-click)
- [x] `grep -n 'window.confirm' the_one/interfaces/web/static/js/areas/studio.js` returns 0 matches
- [x] `agents.md` updated with 2 new entries (Confirm dialog, Beforeunload guard)
- [x] Flight log updated with `### 04-dirty-state-and-confirm-dialog` progress entry
- [x] This leg's status set to `landed`
- [x] Adaptation criteria honored (full focus-trap shipped, OR fallback documented in mission Known Issues)
- [x] Do NOT check off this leg in flight.md yet (Flight Director handles at flight commit)
- [x] Do NOT commit (Flight Director commits all autonomous legs at flight-end review immediately after this leg)
- [x] Signal `[HANDOFF:review-needed]`

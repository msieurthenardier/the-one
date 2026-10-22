# Leg: library-behaviour-fixes

**Status**: landed
**Flight**: [Agents on the library](../flight.md)

## Objective
Change three library behaviours, app-wide:
1. **`App.ui.confirm` announces arming.** Squawk 0220: one shared, lazily appended polite live region.
2. **`App.ui.infoButton` becomes a press-only toggletip.** Squawk 0221; the operator chose press-only on 2026-10-21.
3. **`App.ui.util.mountSlot`** replaces the provider editor's two module-level singletons (DD2).

Close squawks 0220 and 0221.

## Context
- **Flight decisions:** DD2 (`mountSlot`), DD4 item 4 (the info buttons' visible change, approved separately), DD5 (both fixes and their library rules), DD11 (role-structure assertions).
- **Confirm today:** `js/ui/confirm.js` `App.ui.confirm(itemEl, onConfirm, opts)` (about `:73-130`).
  - Arm: it swaps the title text to `confirmLabel`, adds `.confirm-delete` and starts the `lapse` timer (`revertMs`, 3000).
  - The second click commits through `onConfirm(itemEl, revert)`.
  - The header (about `:64-71`) records "no aria-live announcement", deliberately. The local workarounds are `rules-notes-tab.js` (about `:203-215`, its own arm announcement) and `self-configuration-tab.js` (about `:1293-1298`).
- **The info button today:** `js/ui/field.js` `App.ui.infoButton` (about `:113-141`):
  - `button.field-info-icon` with `title` (the full description, the hover tooltip) and `aria-label` "More information about {label}";
  - a visually hidden description span whose id goes into the control's `aria-describedby`;
  - `el` is `span.ui-info`.
- **The listener precedent:** `js/ui/menu.js:70,81,96`. A capture-phase `pointerdown` listener is added on open and removed on close. There is no permanent document listener.
- **The singletons:**
  - `provider-models.js:19-30,144-149,224,996`: `activeController`, destroyed before a new mount and cleared on destroy.
  - `provider-editor.js:40,65,366`: `latestMount`, the create-focus target for `App.focusAfter.defer`.
- **Legs 02a-04 have landed**; `studio.js` is split. Read the flight log.

## Inputs
- Legs 01-04 landed.

## Outputs
- **`js/ui/confirm.js`:** the live region and announcements.
- **`js/ui/field.js`:** the toggletip, with bubble CSS in the infoButton banner of `components.css`.
- **`js/ui/core.js`:** `App.ui.util.mountSlot`.
- **`provider-models.js`, `provider-editor.js`:** use `mountSlot`; the singletons are removed.
- **`rules-notes-tab.js`, `self-configuration-tab.js`:** their local arm announcements are removed.
- **Tests:**
  - contract tests extended (`test_ui_confirm_contract.py`, `test_ui_info_contract.py`, plus a core/util test for `mountSlot`);
  - the four broken tests updated: `test_ui_info_contract.py:34-40`, `test_flow_provider_editor.py:510,556` and `test_flow_studio_mcp_editor.py:688`;
  - `test_flow_admin_tools_editor.py:194` must still pass, because the admin string path keeps `title`.
- **Squawks 0220 and 0221 completed.** Catalogue and docs.

## Acceptance Criteria
- [ ] **The confirm arm announcement (0220).**
  - On arm, `App.ui.confirm` writes a sentence to **one** shared live region: `div.visually-hidden[role=status][aria-live=polite]`, test id `ui-confirm-live`.
  - The region is appended to `document.body` lazily on the first arm, never at load. It is reused afterwards.
  - The text is set after insertion: cleared first, then set on the next tick, so a repeated arm re-announces.
  - The sentence is `"{original title}: press again to {confirmLabel lower-cased without the trailing '?'}"`, for example "Delete Provider: press again to confirm delete". Choose a clear wording and keep it in one place.
  - A lapse sets the region to "{original title}: not confirmed" and a commit clears it. The visual behaviour is unchanged: classes, timers, `revert`, and the `.confirm-lapsed` rules.
  - Contract tests, in both engines: an arm writes the sentence, a second arm re-announces, a lapse and a commit clear it, and there is one region however many controls arm.
  - The two local workarounds are removed, and their tests updated to read the shared region (grep the agent-lane tests for their old status nodes).
- [ ] **The infoButton toggletip (0221).**
  - `button.field-info-icon` has no `title`. Its `aria-label` is unchanged ("More information about {label}"), and it carries `aria-expanded` (false or true) plus `aria-controls` pointing at the bubble.
  - Pressing it (click, Enter or Space) toggles a bubble, `div.ui-info-bubble`, anchored below the button inside `span.ui-info` (CSS absolute position; no layout shift). The bubble shows the description as text and contains a polite live region, so the text is announced once when it opens.
  - Escape (while focus is on the button or in the bubble), a press outside, or pressing the button again closes it. Focus stays on the button.
  - The outside-press and Escape listeners are capture-phase document listeners **added on open and removed on close and on `destroy`** (the `menu.js` precedent). `tests/test_ui_guards.py` shows no new permanent `document.addEventListener` (check its guard, or add a static assertion).
  - The visually hidden description span and the control's `aria-describedby` are unchanged, so the description is still read with the control.
  - Only one bubble is open at a time across the page: opening one closes another.
  - Contract tests, in both engines:
    - press opens and announces;
    - Escape, an outside press and a re-press each close;
    - focus stays on the button;
    - `aria-expanded` toggles;
    - no `title` attribute;
    - role structure (the button controls the bubble);
    - no listener remains after close (assert through a test hook or by behaviour: a press outside after close does nothing).
  - Bubble styling uses tokens: `--surface-elevated`, a `--border` border, `--shadow-popover`, `--radius-sm`, body-sm text, max-width about 280px. It follows the menu's popover look, and `test_token_definitions.py` passes.
- [ ] **The string-path info icons** (`tools-form-helpers.js`, the admin Built-in tools editor) are untouched: they keep `title` until Flight 3, as recorded. `test_flow_admin_tools_editor.py:194` passes unchanged.
- [ ] **`mountSlot` (DD2).**
  - `App.ui.util.mountSlot()` returns `{mount(destroyFn) → token, isCurrent(token), current(), destroy()}`.
  - `mount` destroys the previous mount (calling its `destroyFn`) and returns a new token.
  - `isCurrent(token)` is true until the next `mount` or `destroy`. `current()` returns the active token or null.
  - Contract tests cover the order of destroy calls, `isCurrent` after a remount, `destroy` with nothing mounted, and that a `destroyFn` throwing does not stop the remount (it is logged).
- [ ] **The provider singletons are removed.**
  - `provider-models.js` keeps one module-level `var slot = App.ui.util.mountSlot()`. That is a slot, not a controller reference: `renderProviderModels` mounts through it, and the async paths check `slot.isCurrent(token)`. `activeController` is gone.
  - `provider-editor.js` holds its handles through a slot. The create-focus target reads the current mount's `shell.titleEl` through the slot's token. `latestMount` is gone.
  - The provider browser tests pass unchanged (`providers` lane). `test_flow_provider_models_patch.py`'s pull-survives-refresh and destroy-on-remount cases still pass.
- [ ] **Docs and squawks:**
  - squawks 0220 and 0221 completed in their files' format (the Sign-Off reviewer and commit say pending);
  - catalogue rows for confirm and infoButton updated (the toggletip, the announcement; the 0221 debt note removed), plus a note on `mountSlot`;
  - `the_one/agents.md` "Control library" updated;
  - the `confirm.js` header comment rewritten, since the "no announcement" decision is reversed.
- [ ] **Gates:**
  - `make test-unit`;
  - the static guards, the ownership and inventory checks;
  - the contracts lane (WebKit required);
  - the `providers`, `agents`, `chats` (chat rows use confirm), `settings` and `mcp` lanes, all under netns.

## Verification Steps
- `grep -n "activeController\|latestMount" the_one/interfaces/web/static/js/areas/studio/provider-*.js` returns nothing.
- `grep -n "title" the_one/interfaces/web/static/js/ui/field.js`: the infoButton sets no `title`.
- The lanes above, in the background with an explicit `TEST_TIMEOUT`.

## Implementation Guidance
1. `mountSlot` plus its contract test, then the two provider retrofits. Run the `providers` lane.
2. The confirm live region plus its contract test, then remove the two local workarounds and update their tests.
3. The toggletip, its contract test, and the four broken tests.
4. Catalogue, squawks, docs.

## Edge Cases
- **A confirm on an element removed while armed:** the region text clears on the next arm elsewhere. That is acceptable.
- **Two info buttons in one field row:** opening one closes the other.
- **A toggletip inside a `<details>` summary** (tool overrides): a press must not toggle the details. Stop propagation on the button's click inside `summary` if needed, and test it in both engines.
- **A dark-theme bubble** passes contrast through tokens. No new token pair is needed if it uses `--fg` on `--surface-elevated` (already gated).

## Files Affected
- `the_one/interfaces/web/static/js/ui/{confirm,field,core}.js`, `css/components.css`.
- `js/areas/studio/{provider-models,provider-editor,rules-notes-tab,self-configuration-tab}.js`.
- `tests/browser/test_ui_{confirm,info}_contract.py` and a `mountSlot` contract file (or `test_ui_library_contract.py`).
- `tests/browser/test_flow_provider_editor.py`, `test_flow_studio_mcp_editor.py`, plus the agent-lane tests that read the old announcements.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, `squawks/0220-*.md`, `squawks/0221-*.md`.

## Citation Audit
- Checked at `9369fcc`: `ui/confirm.js:60-130`, `ui/field.js:113-141`, `ui/menu.js:70,81,96`, `provider-models.js:19-30,144-149,224,996`, `provider-editor.js:40,65,366`.
- The workaround lines in `rules-notes-tab.js` and `self-configuration-tab.js`, and the broken test lines, are carried from the planning survey and design review. Re-locate by grep.

## Design Review Addenda (2026-10-21)
These are binding and take precedence over the text above.

**The announcement subject.**
- Build it from `opts.announceName`, else `itemEl.getAttribute('aria-label')`, else the original title text, through one wording helper. On arm the sentence is "Press {subject} again to {confirmLabel lower-cased without '?'}". For Rules and notes this reproduces today's "Press Delete again to confirm deleting {label}": pass `announceName` (for example "Delete {label}") or adjust the helper so the item identity survives.
- Self-configuration's Revoke uses its persistent `aria-label`.
- The confirm-delete call sites that already set a meaningful `aria-label` get it for free.

**Lapse and commit.**
- A lapse sets "{subject}: not confirmed", and a commit clears the region.
- Every write goes through a single pending-timeout handle (clear, then write on the next tick), cancelled on each new write, so a lapse cannot race a following arm.
- The tests use `expect(...).to_have_text` (polling) and never assert the empty intermediate state.

**The live region node** is cached, with an `isConnected` check; it is re-appended if detached.

**Tests that break, named.**
- `test_flow_agent_rules.py:293-295` and `test_flow_agent_notes.py:368-369` assert that `rules-status`/`notes-status` contain "Press Delete again to confirm". Retarget them to `[data-testid="ui-confirm-live"]` with the new wording.
- `rules-status`, `notes-status` and `externalStatus` **stay**: they carry over-limit and error messages. Remove only `armMessage`, the `cfg.announce('')` calls around arming, and the self-configuration `arming` block.
- `test_flow_provider_visible_fixes.py:82` (`test_provider_info_icons_have_accessible_names`) asserts `title` on the provider `field-info-icon`s. Update it to assert the accessible name and the toggletip instead.

**Tests that do not break; the string path is untouched.**
- `test_flow_studio_mcp_editor.py:688` (`mcp-server-editor.js:902` builds its own string icon) and `test_flow_settings_visible_fixes.py:70` (the admin string path) must pass unchanged. Remove the former from the broken list and from Files Affected.
- The string-path `field-info-icon` users that keep `title` until Flights 3 and 4 are `tools-form-helpers.js:121`, `tools-editor.js:173` and `mcp-server-editor.js:902`.
- The only `App.ui.infoButton` consumers are `field.js` (`info`), `choice.js` (`info`) and the provider editor. The `<summary>` edge case is moot today; keep one cheap contract case.

**Toggletip details.**
- The bubble's live region is populated *after* the bubble is shown (next tick).
- The DOM holds the description twice (the hidden span and the bubble). Contract tests locate by id, not by text, to avoid strict-mode hits.
- **Escape inside a modal:** the capture listener calls `stopPropagation`/`preventDefault` only when a bubble is open and it closed it, so one Escape closes only the bubble. Contract case inside `App.ui.modal`.
- **"Only one open":** a module-level current-open reference, cleared on close and `destroy`. No extra document listener.
- **Clipping:** the bubble positions inside `span.ui-info` and flips above when it would overflow the viewport bottom. A browser check on the provider editor confirms it is not clipped by the editor pane.
- **Tab order is unchanged:** the bubble holds no interactive content. Assert the Tab order in the contract test.
- **No permanent document listener.** There is no guard today, so add a static assertion in `tests/test_ui_guards.py`. Every `document.addEventListener(` in `js/ui/*.js` must have a matching `removeEventListener` of the same handler in the same file. The `menu.js` and `infoButton` pairs pass.

**`mountSlot` API (defined).** `App.ui.util.mountSlot()` → `{mount(destroyFn, data) → token, isCurrent(token), current() → {token, data} | null, release(token), destroy()}`:
- **`mount`** first destroys the previous mount (if any), then records the new one.
- **Re-entrancy:** `destroy`/`release` null the current entry **before** calling its `destroyFn`. So a `destroyFn` that calls back into the slot is safe and does nothing.
- **`release(token)`** clears the slot without calling `destroyFn`, only if the token is current. It is for a controller's own destroy path, today's `provider-models.js:224,996`.
- **Late binding:** `destroyFn` closes over a late-bound variable (`var ctl; slot.mount(function () { if (ctl) ctl.destroy(); }, …); ctl = …`). If mounting throws after `mount`, `release(token)` is called in a `catch` and the error is re-thrown.
- **The create-focus target:** `provider-editor.js` passes its handle object as `data` and reads `slot.current().data.shell.titleEl`.
- **Order preserved:** destroy previous, then `container.textContent = ''`, then mount. So the provider pull-survives-refresh and destroy-on-remount tests stay unchanged.

**Release note.** The hover tooltip removal is intentional (press-only). Add a line to the next release's notes source if the project keeps one; otherwise put it in the flight log for the release.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

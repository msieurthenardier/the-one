# Leg: provider-editor-pilot

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Rebuild the provider editor (`provider-editor.js`) and its section module (`providers-section.js`) entirely from library controls under flight DD1:
- `editorShell`, `section`, the form controls, a new `secretInput`, `consentLink`, `status`, `confirm` and `dangerZone`;
- the editor's behaviour unchanged, apart from the DD8 differences;
- squawks 0189 and 0190 closed, the provider sign-in fork removed and the dead OpenRouter field code deleted;
- both files with zero HTML-string sinks and zero reuse-check allowance rows.

Plan sign-in, the token-expiry line, the "after" captures, the gate re-budget and the docs are leg 08, split out at design review (2026-10-15). This leg leaves the plan sign-in machinery (`wirePlanSignIn`, `buildConsentBlock`, `renderTokenExpiry`) working exactly as today: it is re-attached to the new DOM through handles, not rebuilt. So the two files may keep the allowance rows and sinks that live inside those functions until leg 08.

## Context
- **Flight decisions:**
  - DD1: mount once, patch through handles; the shell's boundary with studio (the breadcrumb link carries no handler, `setDirty` only drives the caption and button enablement, `focusTitle` and `titleEl` are exposed, and the editor keeps calling `App.focusAfter`).
  - DD8: the canonical versions.
  - DD9: build each control with its first consumer, which here is `secretInput`.
  - DD11: the test contract.
  - DD13: lane budgets.
- **Legs 01-06 have landed.**
  - The models panel is a mounted controller `{refresh, destroy}`.
  - Every library control this leg needs exists except `secretInput`, which this leg adds.
  - Read the flight log's leg 01-06 entries, the actual factory signatures in `static/js/ui/*.js`, and the leg 04 and 05 addenda.
- **Today's editor** (`static/js/areas/studio/provider-editor.js`, about 1,250 lines, 7 sinks):
  - `renderProviderEditor(container, provider, providerTypes, callbacks)` (`:56`) builds the header, sections and danger zone as one string (`:63-133`, `container.innerHTML = html`), then inserts the breadcrumb (`:142-153`) and the models help link (`:157-165`), wires events (`:167`) and mounts the models panel.
  - **`renderConnectionFields`** (`:179`) builds:
    - name, type select, base URL;
    - the API key with an eye toggle (`:223-226`; the eye swaps icons by `innerHTML` at `:876,880`);
    - key help and the expiry host;
    - `num_ctx` with an info icon;
    - the thinking switch (`.tool-enable-switch`, label-left row `:286-294`) with an info icon;
    - reasoning effort with an info icon.
  - **Type-driven rows** use `TYPE_DEFAULTS` in `providers-section.js:53-70` and the `is-hidden` toggles in `provider-editor.js` (about `:814-826`).
  - **Plan sign-in** (`wirePlanSignIn`, `:421-732`) has three states (signed-out, awaiting-code, connected). `renderState` clears `body.innerHTML` and rebuilds with the DOM.
    - **The consent fork:** `buildConsentBlock` (`:630-700`) builds a read-only URL, an "Open sign-in page" `<button>`, Copy (flashing "Sign-in link copied"), and a code input with "Confirm code".
    - **Reset** uses `App.confirmDelete` with "Confirm Reset?" (`:615-625`).
  - **Token expiry:** `renderTokenExpiry` (`:354`) renders `p[data-testid=provider-token-expiry][data-state]`, live on `App.time.onChange` (`:855-860`).
  - **Dirty tracking:** `getFormSnapshot` (`:734`) reads every `[data-field]`; `checkDirty` (`:776`) drives the caption and buttons and calls `onDirtyChange`, which reaches `ctx.setDirty` and `App.nav`.
  - **Save and Cancel:** Save (`:929-990`) and Cancel (`:896-917`) use `App.focusAfter`.
    - The masked API key contract: an unchanged key is sent as `__MASKED__` (`:1167-1169`).
    - Edit→edit Save patches in place (`:956-978`); create re-mounts through the section.
  - **Test** (`:997-1062`) writes `.test-result-*` spans with `innerHTML`, and flashes on outcomes, including `reauth_required` (`plan-test-reauth`).
  - **Delete** (`:1063-1125`) blocks with `delete-blocked-message` when agents use the provider, else arms `App.confirmDelete` ("Confirm Delete?").
  - **Dead code:** `collectFormData` (`:1129`) reads `config.referer` and `config.title` inputs (`:1188-1209`) that are never rendered. `tests/test_admin_reasoning_effort_field.py:143-150` pins that block's text.
- **`providers-section.js`:** `render()` (`:98-128`) clears with `host.innerHTML = ''` (`:101`) and uses the `mountToken` and `editorGen` guards (`:99,114,139`).
  - **Squawk 0190:** the ctx's `getDirty` and `bumpEditorGen` (`studio.js` about `:610-613`, the doc comment at `providers-section.js` about `:15-16`) are unused.
- **Squawk 0189:** the provider cases in `tests/browser/test_flow_settings_focus_after.py` belong in a `test_flow_provider_*` file (the providers lane).
- **Tests that will break** (Architect and FD scan; re-grep before starting):
  - all ten `tests/browser/test_flow_provider_*.py` files;
  - `test_flow_settings_focus_after.py` (`#pf-*`, `.test-result-ok`, `.save-btn`, `.cancel-btn`, `.test-provider-btn`);
  - `test_flow_provider_plan_signin.py`: the flash "Sign-in link copied" becomes the button's "Copied" and the announcement "Link copied"; the consent testids;
  - `test_flow_provider_visible_fixes.py`;
  - `tests/test_admin_reasoning_effort_field.py`: literal source pins on `id="pf-reasoning-effort"`, `value="…"`, `reasoningEffortRow` and the config seed order;
  - `tests/test_store_static.py:236-238` (four or more `App.store.invalidate('providers')`) and `:315-318` (the exact text `var method = isEdit ? 'PUT' : 'POST';` / `callbacks.onSaveSuccess(updated, !isEdit)`);
  - `tests/test_ui_guards.py`, the testid registry, `RETIRED_SELECTORS`.

## Inputs
- Legs 01-06 landed. The "before" set is in `$HOME/.cache/the-one-ui-capture/m31-f1-before/`.

## Outputs
- `static/js/ui/secret-input.js` (new) or added to `field.js`: `App.ui.secretInput`, with its catalogue row, owned classes and contract test.
- `static/js/areas/studio/provider-editor.js` rebuilt. `static/js/areas/studio/providers-section.js` cleaned. `static/js/areas/studio.js` ctx trimmed (squawk 0190).
- Stylesheet rules that only the old editor markup used are removed (for example `.test-provider-btn`'s padding override, the `plan-*` consent re-declarations at `studio.css` about `:1672`, the `admin-pf-*` rules for retired markup).
- Tests updated and moved (squawk 0189). Allowances lowered. Squawks 0189 and 0190 completed.

## Acceptance Criteria
- [ ] **`App.ui.secretInput(opts)`**
  - Options: `{value, label, id, placeholder, autocomplete, dataset, testid, revealTestid}`.
  - Returns `{el, input, setRevealed(bool), setValue}`. `el` wraps an `input.field-input[type=password]` and an icon-only reveal button:
    - `eye`/`eye-off` through `App.ui.icon`;
    - `aria-pressed`;
    - the name reads "Show password" or "Hide password" (today's labels).
  - It reproduces today's `api-key-wrap` / `api-key-eye` look; those rules move into its banner as owned classes, or are kept as owned names.
  - It has a catalogue row and contract tests in both engines: the toggle, names, `aria-pressed`, focus staying on the button, and that the value is never re-rendered into an attribute.
- [ ] **No sinks outside the sign-in machinery.** `providers-section.js` has no sinks. `provider-editor.js` has none outside `wirePlanSignIn`, `buildConsentBlock` and `renderTokenExpiry` (leg 08 removes those). The allowances are lowered to match. In the final state, after leg 08, both files have no `innerHTML`, `outerHTML` or `insertAdjacentHTML`. Their rows are removed from `HTML_SINK_ALLOWANCE` and `DYNAMIC_SINK_BASELINE`.
- [ ] **No allowance rows outside the sign-in machinery.** At this leg's end the remaining rows belong only to the functions leg 08 rebuilds. In the final state neither file has a row in `OWNERSHIP_ALLOWANCE`:
  - no owned class literals;
  - no `App.icon(`, `App.showFlash(`, `App.confirmDelete(` or `App.consentLink.` calls: they use `App.ui.icon`, `App.ui.flash`, `App.ui.confirm` and `App.ui.consentLink`.
  - Editor-specific, unowned classes (`admin-pf-*` row markers, `plan-*`) are allowed.
- [ ] **One mount.** `renderProviderEditor` builds the editor once per mount from:
  - `App.ui.editorShell`, with the breadcrumb `{label: 'Library', href, trail: ' / Model providers'}`, the title, the subtitle `type · base_url`, Cancel/Save (or Create)/Test and their testids, and `enabledWhenClean` on create;
  - `App.ui.section` for Connection, the Anthropic account and Available models;
  - `App.ui.field` or the choice controls for every field;
  - `App.ui.dangerZone` (label "Delete Provider", armed "Confirm delete?", with its `delete-blocked-message` notice).

  After mount:
  - a type change shows and hides rows through handles (the `hidden` attribute);
  - Save patches the title, subtitle, expiry and snapshot through shell and field handles;
  - Cancel reverts values through handles.

  The create→edit transition still re-mounts through `providers-section.js`, keeping today's `mountToken` and `editorGen` guards.
- [ ] **Fields keep their ids and testids** (`#pf-name`, `#pf-type`, `#pf-base-url`, `#pf-api-key`, `#pf-num-ctx`, `#pf-thinking-enabled`, `#pf-reasoning-effort` and every testid) and their `data-field` attributes, so `getFormSnapshot` and `collectFormData` read them unchanged.
  - The three info icons are the `info` option, with today's description texts.
  - The thinking switch is `App.ui.toggle` (switch first, label beside it, info button after the label: DD8). It replaces the iOS switch and the label-left row.
- [ ] **Test** uses the shell's Test button: the play icon, the standard size, the label "Test". The result is an `App.ui.status` line (`data-testid` added: `provider-test-result`, `data-state`):
  - "Testing…" is pending;
  - ok is success;
  - warning is warning;
  - `reauth_required` is danger, keeping `plan-test-reauth`;
  - failure is danger with the message.

  There are no ✓/✗ glyphs. Flashes and `App.focusAfter` behave as today. On success, the models panel's `refresh()` is called (leg 06), not a re-render.
- [ ] **Delete:** the agent-usage block, then the arm and commit, with today's flow and flashes, through `dangerZone`.
- [ ] **Unchanged behaviour:**
  - the `__MASKED__` contract (an unchanged key sends the sentinel; a changed key sends the new value);
  - dirty tracking through `App.nav`;
  - create→edit focus;
  - `pendingAutoSignInId` (create, then sign in);
  - `App.store.invalidate('providers')` on every mutation;
  - the stale-callback guards.

  A browser test asserts the masked-key round trip if none exists today.
- [ ] **The dead OpenRouter code is removed:** `config.referer` and `config.title` in `collectFormData`. `tests/test_admin_reasoning_effort_field.py` is rewritten to assert the same facts against the new source shape (the reasoning-effort field's id, options and seeding order), not deleted.
- [ ] **`tests/test_store_static.py`** pins still pass. If the exact Save text changes, the pin is updated deliberately to the new canonical line, with the flight log noting it, and the invalidation count stays at four or more.
- [ ] **Squawk 0189:** the provider cases move from `tests/browser/test_flow_settings_focus_after.py` to `tests/browser/test_flow_provider_focus_after.py`. The settings file keeps only Settings cases; if none remain, the file is deleted. The squawk is completed.
- [ ] **Squawk 0190:** `getDirty` and `bumpEditorGen` are removed from the providers-section ctx in `studio.js` and from its doc comment. The squawk is completed.
- [ ] **Dead CSS:** rules used only by the old markup are deleted after grepping, including `.test-provider-btn`'s padding override (DD8: Test matches the other buttons) and the provider consent re-declarations in `studio.css`.
- [ ] **Tests:**
  - Every test selecting a retired class moves to roles, testids or labels. Retired testids (if any) go to the registry's Retired table and `RETIRED_SELECTORS`.
  - The `providers`, `settings`, `agents`, `routing` and `shared` lanes pass under netns.
  - `make test-unit`, the static guards, and `test_ui_ownership.py` pass.
## Verification Steps
- `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|App.icon(\|App.showFlash(\|App.confirmDelete(\|App.consentLink\." the_one/interfaces/web/static/js/areas/studio/provider-editor.js the_one/interfaces/web/static/js/areas/studio/providers-section.js` returns nothing.
- `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_guards.py tests/test_admin_reasoning_effort_field.py tests/test_store_static.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x -q`; `make test-unit`.
- The lanes under netns (background, `TEST_TIMEOUT`): `providers`, `settings`, `agents`, `routing`, `shared`; `contracts` with WebKit required. Then the full `make gate` for DD13.

## Implementation Guidance
1. **Build `secretInput`** with its contract test.
2. **Rebuild the editor's build path** top-down with handles kept in one per-mount object.
   - Keep the wiring functions' behaviour; rewrite their DOM access to use handles instead of `container.querySelector('.save-btn')` and the like.
   - `getFormSnapshot` may keep reading `[data-field]`. It is not an owned class.
3. **Plan sign-in states and the consent link.** Run `test_flow_provider_plan_signin.py` early.
4. **Test and Delete**, then the dead code, then the section module and squawk 0190.
5. **Tests, squawk 0189, allowances, CSS.**
6. **Allowance updates and a lane run** (captures, the full gate, the re-budget and the docs are leg 08).

## Edge Cases
- **Type change** between an Ollama and a non-Ollama type in edit mode: today, does the models panel switch? Keep today's behaviour and document it.
- **The plan-token type has no sign-in section.** The section stays hidden; check `TYPE_DEFAULTS`.
- **The `mock` type in dev mode only:** the type select's options come from `providerTypes`, unchanged.
- **Save failing** (422 with a field error): the inline `setError` on the shell and the field error stay as today. Check what today shows.
- **The masked key field with the eye revealed:** the value shown is the masked placeholder, not a secret. Never write the key into an attribute.
- **`App.time.onChange(fn, ownerEl)`** must use a node that is removed with the editor, so the listener drops.

## Files Affected
- **New:** `the_one/interfaces/web/static/js/ui/secret-input.js` (or in `field.js`; plus the `index.html` tag and the count pin).
- **Rewritten:** `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`.
- **Modified:** `the_one/interfaces/web/static/js/areas/studio/providers-section.js`, `the_one/interfaces/web/static/js/areas/studio.js` (ctx only), `the_one/interfaces/web/static/css/studio.css`, `components.css`.
- **Tests:**
  - `tests/browser/test_flow_provider_*.py` (updates), new `tests/browser/test_flow_provider_focus_after.py`, `tests/browser/test_flow_settings_focus_after.py` (trimmed or removed), `tests/browser/test_ui_secret_input_contract.py` (new);
  - `tests/test_admin_reasoning_effort_field.py`, `tests/test_store_static.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`, `tests/test_index_asset_cache_busting.py`, `tests/test_nav_helper.py` (`RETIRED_SELECTORS`, if any).
- `scripts/run-tests.sh` (budgets).
- **Docs:** `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`.
- **Squawks:** `squawks/0189-*.md`, `squawks/0190-*.md`.

## Citation Audit
Checked 2026-10-15 at `59992fd`:
- `provider-editor.js:56,63-133,142-165,179,223-226,248,277,307,335,354,409,421,615-625,630-700,702-703,734,748,776,814-826,855-860,876-880,896-917,929-990,997-1062,1063-1125,1129,1167-1169,1188-1209`;
- `providers-section.js:53-70,98-128,139`;
- the squawk 0189 and 0190 evidence lines.

Legs 01-06 may shift line numbers; re-locate by symbol.

## Design Review Addenda (2026-10-15)
These are binding and take precedence over the criteria above where they differ:
- **Step 1 of the implementation:** read the actual signatures in `static/js/ui/*.js` (legs 04-06). Where a handle this leg needs is missing (for example `field` `setLabel`/`setPlaceholder`/`hidden`, or `status` `testid`/`dataset`), add it to the factory in this leg, with a contract case and a flight-log note. `editorShell` already returns `saveButton`/`cancelButton`/`testButton` (leg 04): use them for `App.focusAfter` begin and restore, so focus returns to the same node.
- **`secretInput` owns the existing class names** `api-key-wrap` and `api-key-eye`: no new names, CSS kept as is under its banner. Their unmigrated users (`tools-form-helpers.js:284-286`, `tools-editor.js:371-374`, `mcp-server-editor.js:930-933,1512-1523`) become allowance rows; Flights 2-3 remove them.
- **Secret handling (binding):**
  - `value` is set through the `.value` property only, never as an attribute;
  - no `title` or `aria-label` echoes the value;
  - reveal flips only `type`;
  - `type` resets to `password` on Cancel, after Save and on re-mount;
  - `autocomplete="new-password"`;
  - `data-field` sits on the input (through `dataset`), never on the wrapper;
  - the reveal button keeps the names "Show password"/"Hide password" with `aria-pressed`, and drops today's `title="Show/Hide"`, which duplicated the name;
  - the contract test asserts that no attribute of the wrapper or input contains the value, including after `setValue`;
  - nothing logs the payload: `console.error` keeps logging only the error.
- **A key-masking fix, absorbed and recorded.** After a successful edit Save, the key field is re-masked: `setValue(updated.api_key)` (the server's masked value), `originalMaskedApiKey = updated.api_key`, then hidden. Today the typed plaintext lingers in the field and is re-sent on the next Save.
  - A browser test covers three cases: an untouched key sends `__MASKED__`; a changed key sends the new value and the field shows the masked value after Save; Cancel after typing restores the masked value.
  - Record this in the flight log as a named fix.
- **More tests that break** (beyond the list above):
  - `test_flow_provider_plan_signin.py:141-151,213-217,525` and `test_flow_provider_editor.py:480`: `is-hidden` assertions become `to_be_hidden()`.
  - `test_flow_provider_editor.py:468-501`: the thinking label and info button pins.
  - `test_flow_provider_editor.py:241`: the "Danger Zone" title (keep the title text; update the selector if needed). `:264,318,349` already use IGNORECASE.
  - `test_flow_provider_editor.py:133,144`: `.form-actions .test-provider-btn`.
  - `test_flow_provider_editor.py:388`, `test_flow_provider_setup.py:66`, `test_flow_provider_plan_token.py:246` and `test_flow_provider_plan_signin.py:395`: `.test-result*` becomes `[data-testid=provider-test-result][data-state=…]`.
  - `tests/test_ui_guards.py:105-121`: this file's sink snippets.
  - Run `rg "admin-pf-|plan-signin|tool-enable|test-result|api-key" tests` before starting.
- **Shared CSS stays:**
  - `.test-result*` is used by the agent tabs and the tools editor (`test_flow_agent_tabs.py:275-296`, `test_flow_admin_tools_editor.py:418-432`);
  - `.tool-enable-switch` CSS is pinned by `test_design_tokens_a11y.py:578,649,655` and used by the tools editor.

  Delete only provably provider-only rules. The `.provider-models` mount point the models panel uses is kept.
- **Type change** keeps today's behaviour: `base_url` resets to `defaults.base_url`, `api_key` is preserved, `applyApiKeyCopy` runs (through field setters for label, placeholder and hint) and the expiry re-renders. The models panel is not re-dispatched. A Save 422 stays one flattened message in the shell's error (there are no per-field errors).
- **`tests/test_admin_reasoning_effort_field.py`:** delete only the tests that pin the dead OpenRouter `referer`/`title` branch (about `:130-150`), and keep and retarget the rest. Keep `var method = isEdit ? 'PUT' : 'POST';` and `callbacks.onSaveSuccess(updated, !isEdit)` verbatim, so `test_store_static.py:315-318` needs no change.
- **Squawk 0189:** the tool-editor focus-after cases stay in the settings file. Only the provider cases move.
- **One handle object per mount**, holding every control handle and the models controller. The time-zone listener's owner element is a node that stays connected for the editor's lifetime (the section element), never a replaced status node.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

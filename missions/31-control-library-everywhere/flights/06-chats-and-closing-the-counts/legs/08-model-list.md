# Leg: model-list

**Status**: ready
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Give the provider model picker a library home (D2 (a), DD10): `App.ui.modelList`, a presentational keyed list of models. It covers:
- sections;
- each row's status dot, mono name, capability chips and size;
- the row actions (Load, Unload, Delete armed through `App.ui.confirm`);
- per-row busy and error states;
- focus kept across a reconcile.

Then move both provider model panels onto it (the basic list and the Ollama panel), bring `provider-models.js` under 800 lines, remove its line-guard entry, and apply A10, A11, A12, A13 and A17. B12's "no tools" chip is kept as it is.

## Context
- **Flight decisions:** DD10 (the control's shape, what stays in the area, the classes), DD7 (A10, A11, A12, A13 and A17; B12 kept; ledger rows 10-13 and 17), D8 (the line guard), DD13 and DD14.
- **`js/areas/studio/provider-models.js`** (996 lines; its line-guard ceiling is 1,014 in `tests/test_area_module_size.py:24-28`):
  - `renderCapabilityChips(caps)` (`:40-58`), exported as `App.studio.renderCapabilityChips` and also used by `agent-model-picker.js:58`;
  - `buildListRegion(emptyBody)` (`:99-122`): the loading line, the error `App.ui.status`, the empty state, and `div.admin-pf-models-list[aria-live=polite]`, with a `mode(…)` switch;
  - `renderProviderModels(container, provider)` (`:124`) returns `{refresh, destroy}`;
  - **`mountBasic`** (`:159-224`): a keyed list of `div.admin-pf-model-item` text rows, reconciled with `util.syncChildren`;
  - **`mountOllama`** (`:226-993`):
    - the shell: Refresh, the pull `App.ui.select` (`admin-pf-pull-select`), Pull (`admin-pf-pull-btn`), the size line, `App.ui.progress`, the pull error status, the VRAM summary, the list region, and the Running / Available section labels;
    - `buildRow(name)` (`:718-771`): `App.ui.status` LED, name, caps, size, Unload / Load / Delete (Delete armed through `App.ui.confirm`);
    - `setRowState` (`:773-793`), `updateVram` (`:795`);
    - `focusedRow` / `restoreFocus` (`:815-858`), `clearRows`, `applyModels` (`:869-950`, the keyed reconcile into two sections);
    - the busy, error and action helpers (`:628-716`), `refresh` (`:952`).
- **The CSS** (`css/studio.css:978-999`, all `.area-studio .admin-pf-*`): header, list (max-height 240px, scroll), basic item, help text, VRAM summary and value (the accent colour, A11), row (flex, hairline), name (mono, ellipsis), size (mono caption, right-aligned), actions, LED and error line. `admin-pf-model-btn` is a JavaScript hook only. These are area layout classes with no library row.
- **Tests** that reach `admin-pf-model-*` and related classes:
  - `tests/browser/test_flow_provider_models_patch.py` (15 references);
  - `test_flow_provider_visible_fixes.py` (3);
  - `test_flow_provider_editor.py` (2);
  - `test_flow_provider_ollama_pull.py` (2);
  - `test_ui_editor_contract.py` (2).

  The pull testids (`admin-pf-pull-*`) are not list classes and stay.
- **The ledger items:**
  - **A10:** model ids in the generic list are mono (today `.admin-pf-model-item` is sans).
  - **A11:** the VRAM value uses plain secondary text, not accent.
  - **A12:** the Ollama empty text reads "Use Pull to download one." (`provider-models.js` passes "Use Pull Model to download one." to `buildListRegion`).
  - **A13:** Pull progress keeps the app's own "Pulling {model}…" plus the percentage, instead of Ollama's raw status (about `:583`).
  - **A17:** the intro sentence "Each agent chooses one of these in its Model section. Agents" links "Agents" inside the sentence. Find where the intro is built (the provider editor or this module).
  - **B12:** the "no tools" chip keeps its danger outline.
- **`provider-editor.js` has zero line headroom** (896/896). If A17's sentence lives there, edit in place.

## Inputs
- Batch B3 landed and committed; leg 07 may land in the same batch (B4). This leg touches no file of legs 06 or 07.

## Outputs
- **`App.ui.modelList(opts)`** (`js/ui/model-list.js`, new):
  - **Options:** `label` (the list's accessible name), `testid`, `rowTestid`, `actions` (which row actions exist: none for the basic list; load, unload and delete for Ollama), `onAction(name, action)` and `confirmLabel` for Delete.
  - **Handle:** `{el, reconcile(sections), setRowBusy(name, action|null), setRowError(name, message|null), focusRow(name), destroy()}`.
    - `sections` is `[{key, label|null, rows: [{name, state: 'running'|'idle'|null, caps: [..]|null, size: string|null}]}]`.
    - `reconcile` keys rows by name, moves them between sections, keeps a focused control focused (or moves focus to the row's next sensible control when its button is hidden: today's `restoreFocus` rule), and patches each row in place.
    - Delete is armed through `App.ui.confirm` with `onArmChange` where useful. On commit it calls `onAction(name, 'delete')`, with the revert function available to the area for a failure.
  - **Each row** has the `App.ui.status` dot (when `state` is given), the mono name with an ellipsis (A10), capability chips through `App.ui.chip` (the caller passes `caps`; the danger tone for "no tools" is kept, B12), the size (mono, right-aligned) and the row's action buttons.
  - **Owned classes** are `ui-model-list`, `ui-model-section`, `ui-model-section-label`, `ui-model-row`, `ui-model-name`, `ui-model-caps`, `ui-model-size`, `ui-model-actions` and `ui-model-error`, listed by name in a new catalogue row.
  - Their rules in `components.css` reproduce today's look, with A10 (mono for every row). The `.admin-pf-model-*` and `.admin-pf-models-list` rules in `studio.css` are deleted, along with the basic item rules.
- **The panels on the control:**
  - `mountBasic` reconciles one unlabelled section;
  - `mountOllama` reconciles Running and Available, and maps its busy, error and action helpers onto the handle;
  - the loading, error and empty states stay in the area's region around the list (`buildListRegion`), or move into the control as a `setState('loading'|'error'|'empty'|'list', text)` method if that is simpler. Record the choice;
  - **`renderCapabilityChips`** moves to the control as `App.ui.modelList.capabilityChips(caps)`, or stays in the area as a shared helper used by both callers (`agent-model-picker.js:58`). Record the choice; no duplicate copy.
- **`provider-models.js` splits under 800 lines:** for example `provider-models.js` (the dispatcher, basic, shared helpers) and `provider-models-ollama.js` (the Ollama panel). The new script tag goes in `index.html` before the provider editor's consumers. Its `tests/test_area_module_size.py` entry is removed, and every module ends at 800 lines or fewer.
- **A11:** the VRAM value is plain `--fg-secondary` (the area's `.admin-pf-vram-value` rule loses the accent and weight, or the value becomes part of an `App.ui.status` line).
- **A12:** "Use Pull to download one."
- **A13:** the progress text is "Pulling {model}… {pct}%", built from the app's own wording and Ollama's completed/total bytes, never Ollama's raw status string.
- **A17:** "Agents" is linked inside the intro sentence, through `App.router.href`, and the trailing stray word is gone.
- **Tests:**
  - a contract test file `tests/browser/test_ui_model_list_contract.py` (both engines; it lands in `contracts-controls`, or `contracts-chat` if the lane split prefers it, recorded). It covers reconcile across sections, a row moving from Available to Running, focus kept on Load as the row moves (and moved sensibly when Load hides), busy and error states, the armed Delete calling `onAction`, a 200-character model name truncating, an empty section, and `destroy`;
  - the provider lane tests are retargeted from `admin-pf-model-*` to testids or the new classes, never relaxed;
  - A10, A12, A13 and A17 each get an assertion.
- **Catalogue:** the "Provider model picker" row becomes `library: App.ui.modelList`, with its options, handle, states and owned classes.
- **Docs:** CLAUDE.md's and `the_one/agents.md`'s mentions of `provider-models.js` (the provider editor, "Library list and detail" › Model providers) are updated for the split and the control.
- **Ledger rows 10-13 and 17** confirmed in the flight log.

## Acceptance Criteria
- [ ] `App.ui.modelList` has a catalogue row (status `library: App.ui.modelList`) and a contract file. `tests/test_ui_control_inventory.py`, `tests/test_ui_library_source.py`, `tests/test_ui_emitted_classes.py` and `tests/test_ui_ownership.py` pass, and no "Provider model picker" row reads "not yet defined".
- [ ] **The contract file passes in Chromium and WebKit** (`THE_ONE_REQUIRE_WEBKIT=1`), covering the cases in Outputs.
- [ ] `wc -l` shows `provider-models.js` and its new module(s) at 800 lines or fewer, and `tests/test_area_module_size.py` passes with the entry removed (the `provider-editor.js` entry stays, D8).
- [ ] `git grep -n "admin-pf-model-\|admin-pf-models-list" -- the_one/ tests/` finds nothing (the pull classes and testids remain). The `providers` lane passes with the retargeted tests.
- [ ] **A10:** a generic-list model name has a monospace `font-family`. **A11:** the VRAM value's colour is `--fg-secondary`. **A12:** the empty text reads "Use Pull to download one.". **A13:** the progress text matches `^Pulling .+… \d+%$` during a stubbed pull. **A17:** "Agents" is a link inside the sentence. Each has a test.
- [ ] **Focus:** the existing focus-retention tests in `test_flow_provider_models_patch.py` pass unchanged in behaviour (selectors retargeted only).
- [ ] **A capture comparison** of `ollama-models-panel`, `ollama-pull-progress` and `provider-models-generic` against the before set shows only rows 10-13 and 17 (PIL, recorded).
- [ ] `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass.
- [ ] **Lanes:** `providers`, `contracts-controls` (or `contracts-chat`) and `agents` (the agent model picker's chips) pass.
- [ ] `make test-unit` passes after the browser runs. `ruff` is clean.

## Verification Steps
1. The unit guards, `-q -x --timeout 120`.
2. `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_ui_model_list_contract.py -m browser -x`.
3. `--lane providers`, then `--lane agents`.
4. `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out <scratch> --surfaces ollama-models-panel,ollama-pull-progress,provider-models-generic`, then a PIL comparison against `$HOME/.cache/the-one-ui-capture/m31-f6-before`.
5. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The control and its contract test first,** reproducing `buildRow`, `setRowState` and the focus rule as library code.
2. **`mountBasic` onto it,** then `mountOllama`, mapping the busy, error and action helpers. Keep fetch, Pull, VRAM and the size confirm in the area.
3. **The split** under 800, with the script tag and the line-guard entry.
4. **A10-A13, A17;** the CSS deletions; the test retargets.
5. **The catalogue, docs, captures,** then the lanes and `make test-unit`.

## Edge Cases
- **A row moving sections while its button has focus:** today's `restoreFocus` keeps the focus or moves it to the row's remaining action. The control must do the same, in both engines.
- **A Delete armed when a refresh arrives:** the armed state must survive the reconcile (today `listPane` keeps an armed `<li>`; check the panel's own behaviour and keep it).
- **A busy action and a refresh:** an in-flight action keeps its busy state through other refreshes; `busyDone` clears it on the next refresh. Keep that rule, in the control or the area.
- **A model in both lists** (running and available): the current code lists it once, in Running. Keep that.
- **The `aria-live=polite` region:** keep the list region's live behaviour, so loading, error and empty transitions are announced, but don't announce every reconcile.
- **ES5 and `_APP_GLOBAL`:** the control may not call `App.studio`, `App.router` or `App.api`. The area passes data and callbacks.

## Files Affected
- `the_one/interfaces/web/static/js/ui/model-list.js` (new), `js/areas/studio/provider-models.js`, `js/areas/studio/provider-models-ollama.js` (new), possibly `js/areas/studio/agent-model-picker.js` and `js/areas/studio/provider-editor.js` (A17, in place), `index.html`.
- `css/components.css`, `css/studio.css`.
- `tests/browser/test_ui_model_list_contract.py` (new); `tests/browser/test_flow_provider_models_patch.py`, `test_flow_provider_visible_fixes.py`, `test_flow_provider_editor.py`, `test_flow_provider_ollama_pull.py` and `test_ui_editor_contract.py` (retargets); `tests/test_area_module_size.py`.
- `docs/ui-control-inventory.md`, CLAUDE.md, `the_one/agents.md`, the flight log.

## Citation Audit
- `provider-models.js`: 996 lines; `:40-58`, `:99-122`, `:124`, `:159-224`, `:226-993`, `:718-771`, `:773-793`, `:795`, `:815-858`, `:869-950`, `:952`, `:995`. FD grep and read (2026-10-27).
- `css/studio.css:978-999` (the `admin-pf-*` rules). FD grep.
- `agent-model-picker.js:58` (`renderCapabilityChips`): Architect cycle 1 and the code survey. Re-verify.
- **The test reference counts** are from an FD grep of `tests/browser` (2026-10-27).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review Amendments (cycle 1, 2026-10-27; these take precedence over the Outputs above)
- **The control owns the row state machine** (busy, done, held focus, Delete's revert):
  - **Clicks:** the control owns its action buttons' click handlers. Before disabling a button it records `heldFocus` (`document.activeElement === btn`) and `focusBtn`, then calls `onAction(name, action)`.
  - **`setRowBusy(name, action)`** sets the busy state (the button label, for example "Deleting…" through the control-owned `data-confirm-title` span, and the button disabled).
  - **`setRowBusy(name, 'done')`** marks the action finished. The **next** `reconcile` clears the busy state (today's `busyDone` rule), and an in-flight row keeps its busy state through any other reconcile.
  - **`setRowBusy(name, null)`** is the failure path. It restores the label, re-enables the button, runs the stored Delete revert (the control keeps the `revert` from `App.ui.confirm`'s callback; the area never touches it) and re-focuses the button if `heldFocus` was set and focus is now on `body`.
  - `reconcile` skips focus restoration for a row that is still mid-action.
- **The focus fallback:**
  - `reconcile` keeps a focused (or held) control focused;
  - when its button hides or its row goes, focus moves to the row's first visible enabled action (order Unload, Load, Delete), then the **next** row's first action, then the **previous** row's;
  - when no row is left it calls the caller's `onFocusLost()` (the area focuses Refresh, as today).
  - The contract tests pin this order.
- **An armed Delete** survives a reconcile on the same node (the button is never rebuilt; `test_flow_provider_models_patch.py:340-368` keeps passing). When the row moves to Running and Delete hides, `reconcile` reverts the arm and cancels its timer.
- **Row errors:** `setRowError(name, msg)` shows the error line (with the 4,000 ms auto-clear). `setRowError(name, null)`, row removal and `destroy` clear the timers. The row keeps `flex-wrap: wrap`. `reconcile([])` clears every row and timer cleanly.
- **Markup the tests can target:**
  - rows carry `data-name="{name}"` and `data-section="{key}"`;
  - a truncated name has a `title` with the full id;
  - the section label class is `ui-model-section-label`;
  - duplicate names are tolerated (first wins), with today's rule that a model in both lists shows once, in Running.
- **The live region stays as today** (FD answer: option A). The area's region host keeps `aria-live="polite"` and wraps the loading, error and empty nodes and the control's list, so reconciles are announced exactly as now. The earlier edge case "don't announce every reconcile" is **withdrawn**.
- **The region host and the grep criterion.** The area keeps its region host; it is renamed from `admin-pf-models-list` to `provider-models-region` (an area class) so the grep criterion holds. The shell-identity tests (`test_flow_provider_models_patch.py:430-461`) are retargeted to it. The criterion is narrowed to `git grep -n "admin-pf-model-\|admin-pf-models-list\|admin-pf-section-label"`. `admin-pf-models-header`, `-refresh`, `-help` and `-empty` stay (`test_flow_provider_ollama_pull.py` reads `.admin-pf-models-refresh`).
- **The basic list keeps its look** (FD answer): a `density: 'compact'` option (or a no-actions variant) keeps the 4px padding, `cursor: default` and body-sm size. Only A10's mono font changes, so the `provider-models-generic` capture differs by row 10 alone. The `cursor` assertion (`test_flow_provider_visible_fixes.py:107-109`) is retargeted to `.ui-model-row`.
- **Capability chips move onto the control** (FD answer) as `App.ui.modelList.capabilityChips(caps)`:
  - `agent-model-picker.js:58` and the panel call it, and `App.studio.renderCapabilityChips` is removed;
  - the modelList catalogue row owns `cap-chip-row` (`components.css:584`), and the Chip row's text drops "capability chips in provider-models.js";
  - the `NO_TOOLS_TITLE` tooltip, the tools-absent rule (`caps.indexOf('tools') === -1`, danger tone, B12 kept) and the null/empty-renders-nothing rule are kept.
- **A17's exact sentence** (FD answer): "Each of your **Agents** chooses one of these in its Model section.", with "Agents" the link.
  - It keeps its `provider-models-agents-link` testid and accent colour (`test_flow_provider_editor.py:699-715`).
  - It is built at `provider-editor.js:236`, edited in place at 896 lines or fewer.
  - `test_flow_provider_visible_fixes.py:102-105` and `tests/behavior/system-provider-config.md:75` are retargeted to the new sentence.
- **A13's exact rule:**
  - the progress text is always "Pulling {model}… {pct}%", from the first update, with 0% before any total;
  - `pct = min(100, floor(completed / total * 100))` when `total > 0`, else the last value (0 at first);
  - `evt.status === 'success'` shows 100%;
  - Ollama's raw status string is never shown.
- **A11:** the `.admin-pf-vram-value` span and rule are dropped, and the value is written as plain text in `admin-pf-vram-summary` (already `--fg-secondary` mono). The test asserts the summary node.
- **The split is conditional** (FD answer): after the row code leaves for the control (about 250 lines), measure `provider-models.js`.
  - At 800 or fewer, there is **no split**; the line-guard entry is removed.
  - Over 800, split the Ollama panel out, with the shared helpers (`jsonOrThrow`, `modelsUrl`, `formatSize`, `buildListRegion`, `buildRefreshButton`, the mount slot) on `App.studio.providerModelsShared`. The load order is the shared module first, then the Ollama module, then the dispatcher, all before `provider-editor.js` (`index.html:121-122`).
  - Either way, every module ends at 800 or fewer.
- **The library boundary:**
  - the control calls only `App.ui.*` (`status`, `chip`, `button`, `confirm`) and DOM APIs, with no `fetch`, `App.api`, `App.studio` or `App.router`;
  - the area does the `fetch`, the flash and the routing;
  - `<script src="/static/js/ui/model-list.js">` goes in the `js/ui` block of `index.html`, after `feedback.js`, `button.js` and `confirm.js`.
- **The lane:** `test_ui_model_list_contract.py` lands in `contracts-controls` (the `test_ui_*` complement). Leg 04's `contracts-chat` claims only the six chat-control files. `test_ui_editor_contract.py` passes `className: 'admin-pf-models'` and needs no retarget, so the leg's count of 2 for that file is corrected to 0.
- **Extra contract cases:** the `busyDone` flow; an armed Delete surviving `reconcile`; the focus order after the focused row is removed (next, previous, `onFocusLost`); failure restoring the label and focus; `reconcile([])` clearing timers; Available → Running with focus moving from Load to Unload; a 200-character name truncating with a `title`.
- **The before set** is at `$HOME/.cache/the-one-ui-capture/m31-f6-before` (leg 01, 172 images, verified by the FD).

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only): approve with changes.** Applied as the amendments above. FD answers:
  - A17's sentence;
  - the live region kept as today;
  - compact density for the basic list;
  - the chips moved onto the control, with `cap-chip-row` owned;
  - the split only if still over 800.
- **No second cycle.** The amendments pin the row state machine the leg already intended ("today's rules") and resolve its open choices.

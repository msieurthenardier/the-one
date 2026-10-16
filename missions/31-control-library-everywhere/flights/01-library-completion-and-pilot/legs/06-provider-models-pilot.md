# Leg: provider-models-pilot

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Rebuild the provider models panel (`static/js/areas/studio/provider-models.js`) on the library under flight DD1:
- the panel's shell is built once per mount, and nothing after mount rebuilds it from markup;
- the Ollama model list is reconciled by key, so the pull selection, a pull in progress, row errors and focus survive refresh, load, unload and delete;
- squawk 0139 is fixed: cached library models show while the listing refreshes;
- the capability chips are `App.ui.chip` nodes, and the agent editor's one caller appends them;
- `provider-models.js` ends with zero HTML-string sinks and zero reuse-check allowance rows.

## Context
- **Flight decisions:**
  - DD1: mount once, patch through handles, keyed reconciliation. This leg exercises DD1's divert criterion: "keyed patching cannot keep a pull in progress alive across a refresh → re-plan DD1".
  - DD8: the canonical versions:
    - status LED and line;
    - chip remove style (not used here);
    - `refresh-cw`;
    - icon size by button size;
    - the armed style on the row Delete;
    - copy feedback (not used here).
  - DD9: the chip, and the `studio.js` cross-file touch.
  - DD11: the test contract.
- **Legs 01-05 have landed.** These library controls exist:
  - `App.ui.icon`, `button`, `select`, `field`, `toggle`;
  - `section`, `confirm` (the alias `App.confirmDelete`);
  - `status`, `flash` (`App.showFlash` delegates);
  - `progress`, `chip`, `emptyState`.

  The reuse check and the sink count both carry exact allowances. Read the flight log's leg 01-05 entries and the actual factory signatures in `static/js/ui/*.js` before starting. Where the signatures differ from this spec, the code wins.
- **Today's panel** (`provider-models.js`, 677 lines, 8 sinks, all baselined):
  - `renderProviderModels(container, provider)` (`:47`) dispatches to `renderBasicModels` (`:56`, non-Ollama: a list fetched from `/api/providers/{id}/models`) or `renderOllamaModels` (`:119`).
  - `renderOllamaModels` writes the whole panel with `container.innerHTML` (`:123-141`): Refresh, the pull select and button, the size line, the progress bar, the pull error, the VRAM summary, and the list. It is called again on Refresh (`:145`), after a successful pull (`:467`), after load, unload and delete (`:657`), and when the editor's Test succeeds (`provider-editor.js:1021-1024,1032-1035`).
  - The list is HTML strings (`:526-584`): "Running" and "Available" section labels; rows `div.admin-pf-model-row` holding a LED, the name, the capability chips, the size, and Unload, or Load and Delete, buttons with `data-model`. It is wired afterwards by `wireOllamaActions` (`:597`).
  - The row Delete is a hand-rolled two-step confirm (class plus a 3s timer, `:628-639`).
  - Row errors are a temporary element removed after 4s (`:667-671`).
  - The library list `requestLibrary` (`:249`) re-polls every 2s while `data.loading`. Squawk 0139: when `loading` is true with a non-empty `models`, the panel shows the loading copy instead of the cached models (`:255`).
  - The pull flow:
    - a size re-check, then an `App.ui.modal` confirm (`:305-374`);
    - streaming `fetch` plus `getReader`, parsing SSE `data:` lines into the fill width and text (`:376-446`);
    - an AbortController for Cancel (`:290-297`);
    - `isConnected` guards for stale closures (`:250,254,322,365`).
  - `renderCapabilityChips(caps)` (`:31`) returns HTML and is exported as `App.studio.renderCapabilityChips` (`:45`) for `studio.js:3193-3219` `renderModelCapabilities`, which builds the agent editor's capabilities line with `innerHTML`.
- **Tests for the panel:**
  - `tests/browser/test_flow_provider_ollama_pull.py` (route stubs `:43-56`; the loading test `:167-194`);
  - `test_flow_provider_items.py`, `test_flow_provider_visible_fixes.py` (`.admin-pf-model-item` or `-row` selectors), `test_flow_provider_editor.py`;
  - squawk 0141's missing pins (the panel's decimal sizes) are relevant but not required here;
  - the agent editor's capability line is covered by studio tests. Grep `model-capabilities`, `cap-chip` and `model-ctx-chip` across `tests/`.

## Inputs
- Legs 01-05 landed. "Before" captures exist (leg 03).

## Outputs
- `static/js/areas/studio/provider-models.js` rebuilt with DOM APIs and library controls.
- `static/js/areas/studio.js`: `renderModelCapabilities` builds with DOM.
- `static/css/studio.css`: dead `admin-pf-pull-*` and `cap-chip*` rules removed (their looks now live in `ui-progress` and `chip--danger`). Panel layout classes stay.
- Tests updated. Allowances lowered.

## Acceptance Criteria
- [ ] **No sinks.** `provider-models.js` has no `innerHTML`, `outerHTML` or `insertAdjacentHTML`. Its `HTML_SINK_ALLOWANCE` and `DYNAMIC_SINK_BASELINE` entries are removed. The two `studio.js` sinks in `renderModelCapabilities` are gone, and `studio.js`'s allowance row drops by two.
- [ ] **No allowance rows.** `provider-models.js` has no rows in `OWNERSHIP_ALLOWANCE`:
  - no owned class literal (`btn-*`, `field-input`, `empty-state`, `indicator-led`, `chip`, `test-result-*` and so on);
  - no `App.icon(`, `App.showFlash(` or `App.confirmDelete(` call: it uses `App.ui.icon`, `App.ui.flash` and `App.ui.confirm`.
  - Panel layout classes that no control owns (`admin-pf-*`) are allowed.
- [ ] **One mount.** `renderProviderModels(container, provider)` builds the panel once per call and returns a controller `{refresh(), destroy()}`. The editor's Test-success path calls `refresh()`, not a re-render.
  - Ollama: the panel's shell (header with Refresh, pull row, size line, progress, pull error, VRAM summary, list) is built once.
  - `refresh()` re-fetches and reconciles. It never empties or rebuilds the shell.
  - Non-Ollama: a list of model names, reconciled the same way, with a library empty state and a status line for errors.
- [ ] **Keyed reconciliation.** The Ollama list is reconciled by model name within two sections ("Running", "Available"):
  - an existing row node is updated in place (LED state, size, actions);
  - a model that changes sections moves its node;
  - a new model gets a new row;
  - a gone model's row is removed;
  - section labels show only when their section has rows.

  Focus inside a surviving row survives a refresh. A row whose focused node is removed moves focus to the neighbouring row's first action, else to Refresh.
- [ ] **Pull state survives.**
  - A refresh, including one triggered by Load, Unload or Delete on another row, during a pull keeps the progress control, its value and its Cancel working.
  - The pull select's chosen value survives a refresh when the model is still offered.
  - The "panel refreshed; choose the model again" flash paths are removed, because the shell is no longer replaced. Their `isConnected` guards remain only where a mount is truly gone (editor closed).
- [ ] **Controls are library controls:**
  - row actions are `App.ui.button` (`sm`): Unload; Load and Delete;
  - Refresh is `App.ui.button` with the `refresh-cw` icon (`sm`);
  - the pull select is `App.ui.select`, with an accessible name "Model to pull";
  - Pull is `App.ui.button` primary `sm`;
  - the progress is `App.ui.progress`, labelled "Pull progress" with a cancel named "Cancel pull";
  - the pull error and row errors are `App.ui.status` danger lines (a row error clears on the next action or after 4s, as today);
  - LEDs are `App.ui.status` LEDs (success for running, idle for available) with no glyphs;
  - the empty list is `App.ui.emptyState`;
  - the row Delete uses `App.ui.confirm` with the armed label "Confirm delete?", so it gets the armed style (DD8);
  - success messages use `App.ui.flash`.

  Every existing testid (`admin-pf-pull-*`, and any others on the panel) is kept.
- [ ] **Squawk 0139 is fixed.** When the library response has `loading: true` and a non-empty `models`, the select shows those models (enabled) while polling continues. The loading copy shows only when `models` is empty. The squawk file is completed (status `completed`, Completed date, resolution note).
- [ ] **Chips as nodes.** `renderCapabilityChips(caps)` returns a node (`span.cap-chip-row` of `App.ui.chip` nodes; the no-tools chip is `tone: 'danger'` with today's `title`), or `null` for nothing.
  - `studio.js` `renderModelCapabilities` builds the "Capabilities:" and "Max context:" line with DOM APIs, appending the node, and keeps the `model-ctx-chip` testid and the `·` separator text.
  - The `cap-chip`, `cap-chip-no-tools` and `admin-pf-pull-progress`/`-fill`/`-text`/`-cancel` rules are deleted from the stylesheets (the looks live in the `chip` and `progress` banners). The capability row and pull layout look the same in the captures.
- [ ] **Tests:**
  - Every test that selects a retired class or markup is moved to roles, testids or labels: `.cap-chip-no-tools` becomes the chip's text or `title`; `.admin-pf-model-item`/`-row` stays if the class stays.
  - New browser tests in `tests/browser/test_flow_provider_ollama_pull.py` or a new `test_flow_provider_models_patch.py` (the `providers` lane, `test_flow_provider_*`) prove:
    - **(a)** a refresh during a stubbed pull keeps the progress element (the same node identity, checked through `evaluateHandle` or a data marker), its value and its Cancel working;
    - **(b)** the pull select's choice survives a refresh;
    - **(c)** focus on a row's Load survives a refresh;
    - **(d)** a stubbed `loading: true` response with models shows them (squawk 0139);
    - **(e)** row Delete arms with "Confirm delete?" and the armed class, then commits;
    - **(f)** non-Ollama refresh reconciles without rebuilding.
- [ ] **The divert criterion is evaluated.** The flight log records whether keyed patching kept a pull alive across a refresh. If it did not, the Developer stops and signals `[BLOCKED:dd1-divert]` instead of working around it.
- [ ] **Gates:**
  - `make test-unit`;
  - static guards;
  - `test_ui_ownership.py`, `test_ui_guards.py`;
  - `providers`, `agents` (the capability line) and `settings` lanes under netns.
- [ ] **Captures.** `scripts/ui_capture.py --surfaces <the models-panel surfaces>` to `$HOME/.cache/the-one-ui-capture/m31-f1-after-06/`. Compare with the "before" set by reading the pairs. Record in the flight log every visible difference and its DD8 line or squawk, for example the row Delete armed style or the Refresh icon size. An unexplained difference is fixed before landing.

## Verification Steps
- `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|App.icon(\|App.showFlash(\|App.confirmDelete(" the_one/interfaces/web/static/js/areas/studio/provider-models.js` returns nothing.
- `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x -q`; `make test-unit`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane providers -x` (background, with `TEST_TIMEOUT`); then `--lane agents` and `--lane settings`.
- Captures as above, compared by Read.

## Implementation Guidance
1. **Read the current code end to end first**, noting every closure that holds a node and every `isConnected` guard.
2. **Build the shell once** with library controls and keep handles in a per-mount closure object (`panel = {refreshBtn, select, pullBtn, sizeLine, progress, pullError, vram, list, sections}`).
3. **Write `reconcile(running, available)`** over a `Map`-like object keyed by model name (ES5: a plain object `rowsByName`). Each row is built once by `buildRow(name)` returning `{el, led, size, actions, setState(section, data)}`.
4. **Move pull streaming onto the progress handle.** Keep the AbortController.
5. **Squawk 0139** in `showLibrary` and `requestLibrary`.
6. **The chips and the `studio.js` caller.**
7. **Tests, captures, allowance updates**: paste the printed corrected dicts, after checking they only shrink.

## Edge Cases
- **A model name with characters unsafe in a selector:** keep names out of selectors and key rows in an object, not `querySelector('[data-model="…"]')`.
- **Delete armed on a row when a refresh lands:** the row survives (same node), so the armed state and its timer survive. If the model is gone, the row is removed and focus moves as specified.
- **Test success on a provider whose type changed away from Ollama:** the editor re-mounts on type change today? Check `provider-editor.js`'s type-change path. If the panel's dispatch would change, `refresh()` is not enough. Document what happens and keep today's behaviour.
- **Editor close during a pull:** `destroy()` aborts the pull and clears timers (the library poll, row-error timers).

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/provider-models.js` (rewrite).
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`: only the call sites that re-render the panel (`renderProviderModels` → keep the controller, `refresh()` on Test success). The rest of the editor is leg 07.
- `the_one/interfaces/web/static/js/areas/studio.js` (`renderModelCapabilities` only).
- `the_one/interfaces/web/static/css/studio.css`, `components.css` (dead rule removal).
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py` (allowances, baseline).
- `tests/browser/test_flow_provider_*.py` (updates and new tests), plus any studio test asserting the capability markup.
- `squawks/0139-ollama-panel-hides-cached-list-while-filling.md` (completed).

## Citation Audit
Checked 2026-10-15 at `59992fd`:
- `provider-models.js:31,45,47,56,119,123-141,145,249-270,290-297,305-374,376-446,467,526-584,597,628-639,657,667-671`;
- `studio.js:3193-3219` (`renderModelCapabilities`, `capsEl.innerHTML` at `:3210,3218`);
- `provider-editor.js:1021-1024,1032-1035` (Test success re-render).

Legs 01-05 may shift line numbers; re-locate by symbol.

## Design Review Addenda (2026-10-15)
These are binding and take precedence over the criteria above where they differ:
- **Unlisted test breakage to fix in this leg:**
  - `tests/test_design_tokens_a11y.py:418-444` (asserts the `.cap-chip-no-tools` rule): retarget it to `.chip--danger`.
  - `test_flow_provider_ollama_pull.py:159` (`to_have_class("admin-pf-pull-size test-result-warning")`).
  - `test_flow_studio_openrouter_picker.py:80,102,123` (`.cap-chip-no-tools`, including `to_have_count(0)` negatives): use `get_by_text("no tools", exact=True)`, plus a `title` assertion on the positive case, so the negatives cannot pass on a bad selector.
- **The size line** stays a panel layout element: `div.admin-pf-pull-size[aria-live=polite]`, with a warn state as the unowned class `admin-pf-pull-size--warn` and `data-state="warn"`. It does **not** use the owned `test-result-warning` class. `studio.css`'s `:not(.test-result-warning)` rule (about `:1662`) is rewritten to the new class with the same look, and the test at `:159` is rewritten to the new class or `data-state`. The empty-text assertions (about `:138`, `:165`) stay.
- **Chip size:** the capability chips use `App.ui.chip({size: 'sm'})` (leg 05 adds `size`; `.chip--sm` carries `.cap-chip`'s size). `.cap-chip-row` stays as an unowned panel layout class. Only `cap-chip` and `cap-chip-no-tools` are deleted.
- **Controller hand-off and lifecycle:**
  - `renderProviderEditor` keeps the panel controller in its mount closure and passes it to `wireEditorEvents` as an argument. The Test-success handlers (`provider-editor.js` about `:1022,1033`) call `modelsCtl.refresh()`.
  - `provider-models.js` keeps a module-level `activeController` (one provider editor is mounted at a time). `renderProviderModels` calls `activeController.destroy()` before mounting a new one, so a full editor re-render (`:133`, until leg 07) never orphans a poll or a pull.
  - `destroy()` aborts the pull, clears the library poll timer and the row-error timers, and drops the reference.
  - The Ollama-or-basic dispatch is decided at mount from the saved `provider.type`; a type change in the form does not re-dispatch (today's behaviour, documented in a code comment). The `isConnected` guards stay as a fallback.
- **Library API realities** (legs 04-05):
  - **`App.ui.button`** returns a bare node: set `.disabled` directly, and never set `textContent` on an icon button (Refresh).
  - **`App.ui.select`:** mount it with the single placeholder option and mutate `<option>`s by DOM. Set its `aria-label` ("Model to pull") on the control if the factory has no name option.
  - **`App.ui.progress`:** show and hide with the `hidden` attribute. The post-confirm focus moves to the cancel button found inside `progress.el` by its `cancelTestid` (test about `:240`).
  - **`App.ui.emptyState`:** if its required title would render a heading inside the list, add a `titleTag` option (default unchanged) to `emptyState` in this leg, with a contract case, and use a `p`. Title "No models found."; body "Use Pull Model to download one." (Ollama) or none (basic).
  - **Empty, loading and error states, the pull error and row errors** are nodes built once and toggled with `hidden`. A `status` line is never left with empty text (that would switch it to LED-only mode).
- **Reconciliation edge cases:**
  - **Overlapping refreshes:** each `refresh()` takes a generation number, and a stale response is dropped. This applies to both the Ollama and the basic list.
  - **A row mid-action** (disabled, with a busy label) keeps its busy state when a refresh lands. `setState` never resets an in-flight row's buttons.
  - **A row that changes section** (Load: Available → Running) is moved, and focus, if it was in that row, goes to the row's new first action (Unload).
  - **Pull success:** the following `refresh()` shows the new model in Available. Add a test for it, with stubs that return rows.
  - **One library-poll timer:** clear it before every set. `refresh()` and the Refresh button restart the library fetch through that one timer; `destroy()` clears it.
  - **The pull select's value** survives a refresh while the model is still offered, and is reset after a pull finishes, as today (the existing cancel test needs this). AC (b) means "survives a refresh, not a pull finish".
  - **Refresh-disable during a pull** stays on the Refresh button, not inside `refresh()`, so a Test-success `refresh()` mid-pull still runs.
- **Tests:**
  - Node identity for AC (a): use the existing held-pull mechanism (`Server.held`). Stash the progress element on `window`, trigger a refresh, and assert `document.querySelector('[data-testid=admin-pf-pull-progress]') === window.__pp`.
  - (c), (e) and the pull-success case need a stub variant whose `/models` and `/models/status` return rows. The existing `Server` returns `[]`.
- **Layout classes stay** (tests depend on them): `admin-pf-models-refresh`, `admin-pf-model-item`/`-row`, `admin-pf-pull-size`.
- **Agreed capture differences for this leg:**
  - the Refresh icon at `sm` size;
  - the row Delete armed style;
  - the LED role (not visible);
  - the progress bar as `ui-progress`, with the same look.

  Anything else visible is unexplained.
- `model-ctx-chip` stays a literal `setAttribute('data-testid', 'model-ctx-chip')` for the registry extractor.
- Order: (1) shell and controller, (2) reconciliation, (3) pull, (4) chips and `studio.js`, (5) tests.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

# Flight: Library completion and a stateful pilot

**Status**: in-flight
**Mission**: [Every control comes from one library](../../mission.md)

## Contributing to Criteria
- [ ] The app has no design-language page, and everything only it used is gone (fully met by this flight).
- [ ] Every kind of control is defined once in the library: the editor shell and form, feedback and value controls exist, and the provider surfaces are built only from them (partial: the other surfaces follow in Flights 2-4).
- [ ] A change to one control's definition reaches every place it appears: the reuse check exists, and its exception list only shrinks (partial: the list reaches zero in Flight 4).
- [ ] No UI markup is built from HTML strings outside the markdown renderer: the sink check counts every sink, and the three provider files reach zero (partial).
- [ ] Each control's styles are owned by that control (partial: the provider surfaces' and the deleted page's styles).
- [ ] Every migrated surface looks as it did before, apart from approved differences: the capture apparatus exists, and the provider surfaces' before and after set is approved at the HAT.
- [ ] Every library control works by keyboard and by role in both engines (for every control this flight builds).
- [ ] The catalogue documents every control, and adding a control without a catalogue entry and contract tests fails the unit gate (the rule is rewritten off the deleted page).
- [ ] Existing behaviour holds (gates and specs this flight touches).

---

## Pre-Flight

### Objective
Remove the Design language page and the dev-only page mechanism that only it used. Move its token and type reference into the control catalogue. Add the checks that keep the codification honest: a reuse check that fails when a control's owned classes appear outside its definition, a sink check that counts every HTML-string sink, and a capture tool for before and after evidence. Build the library controls the editors share: the editor shell, section, danger zone, form controls, status, flash, copy, progress and icon. Each follows the canonical versions the operator approved. Then prove them, and the mount-and-patch policy, by migrating the most stateful editor end to end: the provider editor and its models panel. When this flight lands, the provider surfaces are built only from the library, with no string sinks and no reuse exceptions.

### Open Questions
- [x] Patch in place or re-mount? → DD1
- [x] Where do a control's styles live, and how is ownership declared? → DD3
- [x] What does the reuse check match? → DD4
- [x] Do the static `innerHTML = ''` clears count as sinks? → DD5 (yes, all sinks count)
- [x] May the icon table stay as data? → DD6 (yes, behind one node-returning control)
- [x] Which visible inconsistencies resolve, and to which version? → DD8 (operator, 2026-10-15)
- [x] How can a switch carry the tools tab's mixed state, when the ARIA switch role has no mixed value? → DD8, tristate note
- [x] Which controls does this flight build, given the mission's Flight 1 list? → DD9
- [x] How are before and after captures produced, without committing them? → DD10

### Design Decisions

**DD1: Mount once per item, then patch through handles.**
- An editor mounts its DOM once per item identity. Opening an item and the create→edit transition are new identities, so a re-mount is allowed there, with `App.focusAfter.defer`/`flush` as today.
- After mount, nothing rebuilds a mounted region from markup. State changes go through the handles the controls return (`setTitle`, `setDirty`, `setError`, `setStatus`, `setValue`, `setProgress`, and so on).
- Repeated rows (the Ollama model list) are reconciled by key:
  - an existing row node is updated in place;
  - a new row is inserted;
  - a gone row is removed.
  Focus, a select's choice, a row's error and a pull in progress survive a refresh.
- **Rationale.** The provider editor already patches on Save and Cancel (`provider-editor.js` Save path, `checkDirty`). Its models panel rewrites itself wholesale (`provider-models.js::renderOllamaModels`) and loses the selection, the row errors and focus on every refresh, pull, load and unload: the defect class this policy removes. Re-mount-on-change would make every editor fight focus and typed state.
- **Trade-off.** Editors hold node handles and need keyed reconciliation code, instead of one `innerHTML = html`.
- **The shell's boundary with the editor and studio (Architect review):**
  - `editorShell` emits `a.editor-breadcrumb-link` with an `href` and no click handler of its own. `studio.js` and `admin.js` keep closing items through their delegated `closest('a.editor-breadcrumb-link')` listeners (route guard plus focus-to-row).
  - The shell's `setDirty` only sets the caption and the Save/Cancel enablement. The editor still reports dirty state to `App.nav` through its section's `ctx.setDirty`.
  - The shell exposes `titleEl` and `focusTitle()`, and never calls `App.focusAfter` itself, since that is outside the disk harness (DD2). Editors keep calling `begin`, `restore` and `defer`.

**DD2: Factory shape follows the existing `App.ui` mechanism.**
- `App.ui.<name> = function (opts)` in an ES5 IIFE under `js/ui/`, built with `App.ui.util.el`, with no HTML strings and a caller-supplied `testid`.
- A control with no state after mount returns a node. A control that changes while shown returns a controller `{el, …setters, destroy?}`, like `field`, `toggle`, `listPane` and `drawer` today.
- Factories never fetch, route, read the store or install document listeners. Behaviour reaches them as `opts` callbacks (`onSave`, `onCancel`, `onTest`, `onConfirm`, `onCopy`). This keeps every factory loadable in the disk harness (`tests/browser/_ui_engines.py::load_harness`, which loads only `icons.js` and `js/ui/*.js`).
- **Trade-off.** Editors keep their own data flow; the shell renders and reports, it does not save.

**DD3: Each control owns its classes, and the catalogue declares them.**
- The library's CSS stays in `css/components.css` (layer `components`), with one `/* === App.ui.<name> === */` banner per control.
- `docs/ui-control-inventory.md` gains an **Owned classes** column. It is the single list the reuse check reads (DD4) and the reference a future restyle starts from.
- New classes use the `ui-<name>-…` prefix.
- Existing shared class names the app and its tests already rely on are adopted as owned, not renamed. Renaming them would churn tests with no visible gain. They are named concretely, with no globs. A glob such as `.editor-*` would catch unrelated classes like `editor-prompt-block` and `editor-empty`:
  - buttons: `btn-filled-primary`, `btn-outlined-primary`, `btn-ghost`, `btn-muted-destructive`, `btn-sm`, `btn-icon`;
  - fields: `field-input`, `field-textarea`, `field-select`, `field-group`, `field-group-label`, `field-hint`, `field-error`, `field-info-icon`;
  - editor shell: `editor-header`, `editor-title`, `editor-subtitle`, `editor-breadcrumb`, `editor-breadcrumb-link`, `editor-unsaved`, `editor-error`, `editor-section`, `form-actions`;
  - the rest: `section-title`, `danger-zone`, `danger-zone-title`, `indicator-led`, `app-flash`, `confirm-delete`, `confirm-lapsed`, `badge`, `empty-state`, `checkbox-primary`, `chip`.

  Leg 02 fixes the exact list against the code.
- **Owners outside `js/ui/` move in.** A control's owner must load in the disk harness, so these modules become library controls in `js/ui/`:
  - `App.confirmDelete` (`confirm.js`) becomes `App.ui.confirm`. It owns the armed and lapsed state, and `App.confirmDelete` stays as an alias so its 13 call sites migrate with their surfaces.
  - `App.showFlash` (`app.js`) becomes `App.ui.flash`, with `showFlash` delegating to it.
  - `App.consentLink` becomes `App.ui.consentLink` (DD9), with a catalogue row, contract tests and caller-supplied testids. `App.consentLink` stays as an alias.
- Use of an owned class inside the library itself (`.field-hint` from `field.js` and `choice.js`, `.section-title` from the listPane and navGroups captions) is not checked. `components.css` is not scanned.
- Area stylesheets (`chat.css`, `studio.css`, `admin.css`) may lay out their own containers but may not select an owned class.
- **Trade-off.** Some owned names stay unprefixed, so ownership is read from the catalogue, not from the name.

**DD4: The reuse check: owned class tokens outside the owner fail.**
- A new unit-tier test (`tests/test_ui_ownership.py`) reads the Owned classes column and fails when either of these appears outside `js/ui/`:
  - an owned class appears as a whole class token inside a string literal in application JS under `static/js/` (this covers `className`, `classList.*`, `class="…"` in markup and `querySelector` strings);
  - an owned class appears in a selector in `chat.css`, `studio.css`, `admin.css` or `base.css`.
- **Tokenizer, fixed here so the provider files can reach zero:**
  - comments are stripped first, both `//` and `/* */`, with string-aware scanning so an apostrophe in a comment does not pair with a quote;
  - testid values are excluded: `testid:`/`*Testid:` option values, `'data-testid'` attrs keys and `setAttribute('data-testid', …)`. `editor-unsaved` and `editor-breadcrumb-link` are testids as well as classes;
  - a token matches as `(?<![\w-])name(?![\w-])`.
- **Exception list.** `OWNERSHIP_ALLOWANCE` lives in its own module, `tests/_ui_ownership_allowance.py`, and maps `(file, class)` to an exact count. The test fails when a count rises and also when it falls, so every improvement must lower the list in the same change. On failure it prints a paste-ready corrected row set, as the testid registry diff does. The list only shrinks. The Architect's estimate of the starting size is about 200-250 rows.
- **Excluded:** tests, docs and `js/ui/` itself. A modifier the caller passes as an option (`variant: 'danger'`) is never a literal in the caller.
- **Queries count as uses.** A caller that finds an owned node by class should hold the handle the control returned instead (DD1).
- Structural copies (the same DOM shape under new class names) are left to review, as the mission records.
- **Trade-off.** The starting list is long (measured when the check lands). That is the honest size of the debt.

**DD5: The sink check counts every sink, per file, exactly.**
- `tests/test_ui_guards.py` gains `HTML_SINK_ALLOWANCE`: an exact per-file count of every `innerHTML`/`outerHTML` assignment and every `insertAdjacentHTML` in application JS. It counts static clears (`= ''`) and single-literal assignments too, unlike `DYNAMIC_SINK_BASELINE`, which exempts them and never fails on removals.
- Like DD4 it fails both ways, so it only shrinks. `DYNAMIC_SINK_BASELINE` stays as the text-level freeze until Flight 4 retires it.
- A clear becomes `replaceChildren()`. The mission's target is zero in every file. `markdown.js` is already pinned sink-free by its own guard.
- **Trade-off.** Splitting a file moves its count between rows. A moved sink is a row change, not a new sink.

**DD6: One icon control, and the icon table stays as data.**
- `App.ui.icon(name, opts)` is promoted from `App.ui.util.icon` (`js/ui/core.js:72`; `util.icon` delegates to it). It returns an `aria-hidden` SVG node and throws on an unknown name.
- `opts.size` takes `sm` (14px) or the default (16px). A button sizes its icon by its own size, so no per-site icon rule is needed.
- The SVG table in `icons.js` stays as data. `App.icon` (string) and `App.iconNode` remain until their callers migrate, and their call counts join the reuse check as retired-API rows (`App.icon(`, `App.iconNode(`, `App.showFlash(`, and the DD3 aliases `App.confirmDelete(` and `App.consentLink.`), so those counts only shrink.
- Name drift resolves to one name per glyph: `refresh-cw`, not `refresh`. The `refresh` entry stays in `icons.js` until its last caller (`mcps-tab.js`) migrates in Flight 2, which deletes it.

**DD7: Retire the page and the dev-only page mechanism together.**
- **Delete:**
  - `areas/admin/design-language-page.js` and all 16 `areas/admin/design-language/*.js`, plus their 17 `<script>` tags;
  - the `.design-language-*`, `.telemetry-strip`/`.telemetry-value`, `.admin-provider-badge*` and `.list-item*` rules, which no other markup uses (dependency map, 2026-10-15);
  - `tests/browser/test_ui_reference_page.py`;
  - the `devOnly`/`dev` mechanism, which has no other user once the page is gone: `settings-pages.js`, the `router.js` dev row and `devMode()`, `admin.js` (`validIds` and the nav filter), and the `jump-to.js` dev branch.
- **Rewrite:**
  - `test_ui_control_inventory.py`'s demo rule becomes: "every factory has a catalogue row with owned classes, and at least one `tests/browser/test_ui_*` file calls `App.ui.<name>(`". Its row parser is scoped to the control tables, so the new Tokens and type tables are not read as control rows. The cell count moves to 6 when leg 02 adds Owned classes;
  - `DYNAMIC_SINK_BASELINE`: prune its two design-language keys;
  - `test_nav_guard_static.py`: its `ui-modal-section.js` subset entry and docstring;
  - `test_router_core.py:490-513`: rewrite the two dev-route tests as unknown-route tests;
  - the Makefile's stale "18 static-asset paths" comment;
  - every test the dependency map lists. `#settings/design-language` becomes an unknown route, dropped with no redirect;
  - the script-count pin (88 → 71 before this flight adds files);
  - the `verify-serving` pin's sample file;
  - the testid registry's seven page-only rows, moved to Retired.
- **Move:** the token and type reference goes into the catalogue as a **Tokens and type** section. It lists every token name with its role, and the type ladder. Values stay single-sourced in `tokens.css`/`fonts.css`, so the doc cannot drift from them.
- **Amend** the behavior specs `list-and-detail` (step 18), `workbench-navigation` (step 5), `shell-navigation-smoke` (step 6) and `jump-to-palette` (Out of Scope).
- **Update docs:** `CLAUDE.md`, `the_one/agents.md`, `.env.example`, and the `scripts/webkitgtk_probe.py` example.
- **Trade-off.** A future dev-only page would need the mechanism back. That is a deliberate re-add, not dormant code.

**DD8: The canonical versions (operator, 2026-10-15).** These bind every flight, not just this one.

The operator picked these explicitly:
- **Switch.** `App.ui.toggle` everywhere: a 36×20 track, a 14px thumb inset 3px, the switch role and the focus ring. The studio pill (32×18, not keyboard reachable) and the iOS switch (16px thumb) retire.
- **Tristate.** The tools tab's category master takes the `tristate` option. The ARIA switch role has no mixed value, so a tristate control keeps native checkbox semantics (`indeterminate`, exposed as mixed) and draws the switch with the mixed thumb: accent-translucent track, accent thumb at the midpoint, as the pill does today.
- **Label placement.** The switch comes first and its label sits beside it, the toggle factory's existing order. The 100px label gutter (`.field-row`) retires for toggles. Text fields keep the label above.
- **Copy feedback.** The button's own text reads "Copied" for 2s, with a polite announcement, and "Copy failed" on failure. Every copy has the clipboard fallback and no flash. The icon-only variant (markdown code blocks) gives the same feedback. The provider sign-in block becomes the shared consent-link block.
- **Settings saves.** An in-place save shows a persistent inline status line (the Date and time pattern). The top flash stays for editor actions.

Recommended at the checkpoint; the operator raised no objection. The HAT re-confirms these on screen:
- **Editor header.** One shell: breadcrumb, title (h1; h2 under a page h1, as the tools editor is today), subtitle, the unsaved caption, then Cancel / Save / Test. Test matches the other buttons' size, with the play icon and the label "Test".
- **Errors.** One inline error beside Save in every editor (the KB create form gains one). One block style for "this section failed to load", replacing six per-feature classes. `.field-error` is caption size everywhere. Unstyled `form-hint` takes the `.field-hint` style.
- **Danger zone.** "Delete {Thing}" with a 16px trash icon, and the armed label "Confirm delete?".
- **Armed state.** Every two-step confirm control shows the armed style, reset and rotate included.
- **Library versions everywhere, unchanged in look:** checkbox, empty state, badge, info button.
- **Tiles.** Source and category tiles merge (name bold). Inner tiles use the radius token, not a hard-coded 6px.
- **Chips.** One chip. Its remove "×" is muted and turns red on hover.
- **Status.** One 10px LED and one status-line style (body-sm, muted). Test results show the LED and text with no ✓/✗ glyphs. The 8px provider-type dot stays separate: it marks identity, not status.
- **Disclosures.** One `<details>` panel with a visible focus ring on its summary.
- **Icons.** `refresh-cw` everywhere. Icon size follows the button size.

Every visible difference a migration produces must trace to a line here, or to a named squawk fix.

**DD9: Build each control with its first consumer.**
- **This flight builds** the controls the provider surfaces use:
  - `icon`, `editorShell`, `section`, `dangerZone`, and `confirm` (moved from `confirm.js`, DD3);
  - form updates: `field` hint, error and info, and `infoButton`;
  - `status` (LED and line) and `flash`;
  - `copyField` and `copyButton`, plus `consentLink`, rebuilt on them and moved into the library (DD3);
  - `progress`;
  - a display-only `chip`, for the models panel's capability chips. The models panel builds them for every row today (`provider-models.js:31` `renderCapabilityChips`). The agent editor's model picker reuses the same function, taking a string at `studio.js:3200`. Leg 05a changes that one caller to append the returned node; the change is recorded as a cross-file touch.
- **Flight 2 builds** tiles, tabs, the editable chip list, the disclosure and the toggle's `tristate` option, whose first consumer is the tools tab. **Flight 3** builds the key-value table. Each lands with its first real use. Their canonical versions are already fixed by DD8.
- **Rationale.** The mission's Flight 1 list named them all, but an API designed without a consumer is the risk the Architect flagged. This is a recorded variation, not a scope cut.

**DD10: A capture tool for before and after evidence, never committed.**
- `scripts/ui_capture.py`:
  - starts its own scratch dev instance: a port of 8490 or higher, a data directory under `$HOME`, a scratch working directory, dev mode on;
  - seeds it through the API with the local-API credential;
  - opens named surfaces in both themes and writes PNGs to an output directory outside the repo.
- **Refuses** ports 8484 and 8485, the default data directory, and any output path inside the repo.
- **Surface table.** Covers:
  - the provider editor for each type, and the models panel;
  - the sign-in consent block in the provider editor, in chat and in the MCP editor;
  - one flash and one Test result.

  A surface needing a backend the host lacks (an Ollama daemon) is driven by Playwright route stubs, the same way `tests/browser/test_flow_provider_ollama_pull.py` stubs them.
- **Pinned environment** (Architect review):
  - Viewport, theme, `color_scheme`, time zone and locale are set explicitly.
  - Each surface gets a fresh browser context, since the asset `?v=` version is the same before and after.
  - The clock-dependent plan-token "expires around" line is stubbed or recorded as an accepted difference.
  - The script honours `THE_ONE_TEST_NETNS=1` by re-running itself under `unshare -rn` with `lo` up, as `scripts/run-tests.sh` does. Chromium needs this under WSL mirrored networking.
  - The default-data-dir refusal reads `the_one.config._default_data_dir()` and any `THE_ONE_DATA_DIR` in the environment or `.env`, never a literal (squawk 0084).
- **"Before"** is captured from the working tree at the end of leg 03, not from a worktree. An editable install would serve the main tree's static files from a worktree.
  - Leg 02 proves the tree still renders as the base commit does: `git diff 59992fd --` on the provider files, `consent-link.js`, `app.js` and `confirm.js` is empty, and the CSS diff is only leg 01's DD7 deletions plus leg 02's comment-only banner changes.
  - **"After"** is captured at the end of leg 07. The pairs are flight-log evidence.
- A unit test pins the refusals.
- **Trade-off.** Image diffs are judged by people (the HAT), not by a pixel gate. This follows the project's no-committed-snapshots rule.

**DD11: The pilot's test contract.**
- **Kept:** every existing testid on the provider surfaces, and the `#pf-*` ids.
- **Updated in the same leg:** tests that assert on classes the pilot retires (`.tool-enable-switch`, `.test-provider-btn`, `.admin-pf-*`, `.test-result-*`) move to role, testid or label locators.
- **Recorded:** any testid that disappears goes to the registry's Retired table and `RETIRED_SELECTORS`.
- **Source-text tests rewritten with the code they pin:** `tests/test_admin_reasoning_effort_field.py` and the provider rows of `tests/test_store_static.py`.
- **Squawk 0189:** the provider focus-after tests move from the settings lane to the providers lane.
- **Tests the pilot will break** (Architect scan; each leg spec lists its own by grep):
  - the ten `tests/browser/test_flow_provider_*.py` files;
  - `test_flow_settings_focus_after.py` (`.test-result-ok`, `#pf-*`);
  - `test_flow_provider_plan_signin.py`: the flash "Sign-in link copied" becomes the button's "Copied" (DD8);
  - `test_flow_provider_visible_fixes.py` (`.admin-pf-model-item`);
  - `test_oauth_modal_flow.py:541-546`, the consent link's copy feedback (leg 04);
  - `tests/test_consent_link_static.py`, the script order pin (leg 04);
  - `tests/test_admin_reasoning_effort_field.py`, `tests/test_store_static.py:236,315`, `tests/test_ui_guards.py`, and the testid registry.

**DD12: Every new control proves keyboard and role reach.** Each factory's contract test file, run in Chromium and WebKit, asserts:
- the control's Tab order;
- that it can be reached by `get_by_role` with its accessible name;
- its states (disabled, armed, mixed, error).

Leg design review adds an accessibility lens (Mission 25 lesson).

**DD13: Lane budgets move with the work.**
- The contracts lane (243/270 s at sortie 04) grows by about thirteen factory files in both engines. The flight's final gate re-measures it and re-budgets it in `scripts/run-tests.sh`, splitting it if one lane would exceed its budget.
- Squawk 0217 (the agents and shared lanes) stays separate: this flight adds no test files to those lanes.

### Citation Audit

Verified against the working tree at `59992fd`:

| Citation | Status |
|---|---|
| `js/ui/core.js:72` `App.ui.util.icon(name)`: DOMParser, returns an `aria-hidden` svg node, throws on unknown name (DD6) | verified |
| `js/icons.js:86,93` `App.icon` returns markup and warns on unknown name; `App.iconNode` parses it (DD6) | verified |
| `js/ui/choice.js:87` `App.ui.toggle`: track placed before the label (switch first), `role=switch` on the native input, returns `{el, control, setChecked}`; no indeterminate support yet (DD8). Flight 2's `tristate`: `build()` skips `role=switch` when tristate, keeps checkbox semantics in every state, sets `input.indeterminate`, adds `setIndeterminate`, and `setChecked` clears it; `:indeterminate` track rules and a forced-colors rule | verified |
| `js/areas/studio/provider-models.js:31` `renderCapabilityChips` returns markup used for each Ollama row and by `studio.js:3200` (`capsEl.innerHTML`) (DD9) | verified (Architect, 2026-10-15) |
| `js/areas/studio.js:1850`, `js/areas/admin.js:580` delegated `closest('a.editor-breadcrumb-link')` close handlers (DD1 shell boundary) | verified (Architect, 2026-10-15) |
| `js/ui/choice.js:57` `App.ui.checkbox`, `js/ui/field.js:119` `App.ui.field` exist (DD9) | verified |
| `js/areas/studio/provider-editor.js:133` `container.innerHTML = html` builds the whole editor (DD1, DD5) | verified |
| `js/areas/studio/provider-editor.js:630` `buildConsentBlock`, a second copy of `js/consent-link.js:130` `App.consentLink` (DD8) | verified |
| `js/areas/studio/provider-models.js:119-123` `renderOllamaModels` rewrites its container with `innerHTML` (DD1) | verified |
| `js/areas/studio/provider-models.js:255` `if (data.loading)` shows loading copy and ignores a non-empty `models` (squawk 0139) | verified |
| `js/areas/studio/providers-section.js:82,99,114,139` `mountToken` bump, stale-callback guard on `editorGen`, `mountToken` and `isActive` (DD1) | verified |
| `js/app.js:286` `showFlash(container, msg, isError)`: `.app-flash`, `role=alert` for errors, else `status` (DD6, DD9) | verified |
| `js/confirm.js:71` `App.confirmDelete(itemEl, onConfirm, opts)` (DD8 armed state) | verified |
| `tests/test_ui_guards.py:97` `DYNAMIC_SINK_BASELINE`: per-file text snippets; removals never fail (DD5) | verified |
| `tests/test_index_asset_cache_busting.py:87` `assert len(refs) == 88` (DD7) | verified |
| `tests/test_ui_control_inventory.py:87,96` the demo rule globs `ui-*-section.js` and pins 9 files (DD7) | verified |
| `tests/_ui_guard_helpers.py:68` `_KEY_LITERAL` extracts `'data-testid':` keys (registry sync, DD11) | verified |
| `tests/browser/_ui_engines.py::load_harness` loads the `@layer` statement, every css link, `icons.js` and `js/ui/*.js`, with no app server (DD2) | verified (survey, 2026-10-15) |

### Prerequisites
- [x] The mission plan exists on `mission/31-control-library-everywhere` (PR #297, open). This flight branches from it (`flight/01-library-completion-and-pilot`).
- [ ] WebKit userland present (`bash scripts/setup-webkit-userland.sh`), and `THE_ONE_REQUIRE_WEBKIT=1` passes a contracts-lane smoke. Re-verify at the first UI leg.
- [ ] `THE_ONE_TEST_NETNS=1` works (`unshare -rn` available). Re-verify at the first browser run.
- [ ] "Before" captures of the provider and consent-link surfaces taken at the end of leg 03, with the unchanged-tree diff check (DD10), before legs 04-07 edit any file they render.
- [ ] For the HAT: a scratch dev instance (port of 8490 or higher, scratch data directory under `$HOME`, scratch cwd). Optionally a local Ollama for a live models panel.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete: every code-asserting design decision verified
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Clear the ground first.** Leg 01 removes the page and its mechanism and moves the reference into the catalogue, so later legs never have to keep it working.
2. **Install the apparatus before any control changes.** Leg 02 adds the icon control, the ownership column, the reuse and sink checks with their measured starting allowances, and the capture tool, then takes the "before" captures from the working tree, with DD10's unchanged-tree check.
3. **Build the controls in two legs, pre-split along the M25 lesson.** Leg 03 covers the editor shell and form controls; leg 04 covers feedback and value controls. Each control lands with its catalogue row, owned classes and contract tests in both engines. No consumer changes, except the moved owners (DD3) and their aliases: the `confirm.js`, `app.js` flash and consent-link callers and their tests. The legacy look is reproduced through the canonical versions in DD8.
4. **Migrate the pilot end to end, models panel first.**
   - Leg 05a rebuilds the models panel under DD1, with keyed reconciliation, a pull that survives a refresh, and squawk 0139. This exercises DD1's divert criterion before the editor depends on it.
   - Leg 05b rebuilds the provider editor and the providers section on the shell. It absorbs squawks 0189 and 0190 and the consent-block fork, drops the dead OpenRouter field code, and brings the three files to zero sinks and zero reuse exceptions. The "after" captures are taken.
5. **Close with the HAT.** Leg 06: the operator walks the provider surfaces and the Settings nav in both themes, approves the before and after capture set, and re-confirms DD8 on screen.

### Checkpoints
- [ ] Page retired; unit gate green; the dev-only mechanism is gone.
- [ ] Reuse and sink checks live with measured allowances; "before" captures taken.
- [ ] Editor shell and form controls built and contract-tested in both engines.
- [ ] Feedback and value controls built; `App.consentLink` rebuilt on `copyField`.
- [ ] Provider surfaces on the library: zero sinks and zero reuse exceptions in those files; the full gate is green.
- [ ] HAT: captures approved, DD8 confirmed.

### Adaptation Criteria

**Divert if**:
- A factory cannot meet DD2 (for example, it needs a document listener or a fetch) without breaking the disk harness.
- Keyed patching of the models panel cannot keep a pull in progress alive across a refresh. In that case, re-plan DD1 before Flight 2 inherits it.
- The reuse check's starting allowance shows a shared class that cannot be owned by one control. In that case, reopen DD3.

**Acceptable variations**:
- A control's option names, and a split of one factory into two (`copyField`/`copyButton`) or a merge.
- Moving a control between legs 03 and 04.
- Contracts-lane re-budget numbers and a lane split.
- Absorbing a one-line squawk found inside the pilot's files, recorded in the flight log.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

> **Leg numbers after the 2026-10-15 split.** Leg 02 was split at its design review, so leg files are numbered:
> - 01 `retire-design-language-page`
> - 02 `ownership-and-sink-checks`
> - 03 `capture-tool-and-before-set`
> - 04 `editor-shell-and-form-controls`
> - 05 `feedback-and-value-controls`
> - 06 `provider-models-pilot` (called "05a" in the DDs)
> - 07 `provider-editor-pilot` ("05b", core)
> - 08 `provider-signin-and-close` ("05b", sign-in and close)
> - 09 `flight-hat`
>
> DD text written before the split uses the old numbers: "legs 03/04" mean 04/05, and "05a/05b" mean 06 and 07-08.

- [x] `retire-design-language-page`: delete the page, its 17 scripts, its CSS and test, and the `devOnly` mechanism. Rewrite every dependent test, the inventory rule, the pins and the registry. Amend four behavior specs. Add the catalogue's Tokens and type section. Update the docs (DD7).
- [x] `ownership-and-sink-checks`: the `App.ui.icon` control (DD6), the Owned classes column (DD3), `tests/test_ui_ownership.py` with its new tokenizer, measured `OWNERSHIP_ALLOWANCE` and retired-API rows (DD4, DD6), and `HTML_SINK_ALLOWANCE` (DD5).
- [x] `capture-tool-and-before-set`: `scripts/ui_capture.py` with its refusal tests, then the "before" captures with the unchanged-tree check (DD10). Split from the leg above at design review, 2026-10-15.
- [x] `editor-shell-and-form-controls`: `editorShell` (breadcrumb, title, subtitle, unsaved caption, Cancel/Save/Test, inline error, patch setters, `titleEl`/`focusTitle`; DD1's boundary), `section`, `confirm` (moved from `confirm.js`, alias kept), `dangerZone` using it, `field` hint, error and info, and `infoButton`. Includes catalogue rows with owned classes, and contract tests in both engines (DD2, DD3, DD8, DD12).
- [x] `feedback-and-value-controls`: `status` (LED and line), `flash` (with `App.showFlash` delegating), `copyField`/`copyButton`, `consentLink` moved into the library and rebuilt on them (alias kept; its chat and MCP uses take the DD8 copy feedback), `progress`, and the display-only `chip`. Includes catalogue rows and contract tests in both engines.
- [x] `provider-models-pilot`: rebuild `provider-models.js` on the library under DD1:
  - keyed row reconciliation, where selection, row errors, focus and a pull in progress survive refresh, load, unload and delete;
  - squawk 0139 (show cached `models` while loading);
  - the capability chips on `App.ui.chip`, plus the one `studio.js` caller that appends the node;
  - zero sinks and zero reuse exceptions in the file;
  - the models-panel tests updated (DD11).
- [x] `provider-editor-pilot`: rebuild the provider editor core and `providers-section.js` on `editorShell`, the form controls and a new `secretInput`:
  - Test on `status`; Delete on `dangerZone`;
  - the key re-masked after Save (a named fix);
  - squawks 0189 and 0190; the dead OpenRouter field code removed.

  The plan sign-in machinery is re-attached through handles, not rebuilt.
- [x] `provider-signin-and-close`: rebuild plan sign-in on `consentLink` and `confirm`, and the token-expiry line, bringing both files to zero sinks and zero reuse exceptions. Then the "after" captures, the full gate and the contracts-lane re-budget (DD13), and the pilot's docs. Split from `provider-editor-pilot` at design review, 2026-10-15.
- [ ] `flight-hat` *(optional; the operator asked to run to here)*: a guided HAT on a scratch instance in both themes:
  - the Settings nav without the page, and the old address dropped;
  - every provider type's editor, the models panel (stubbed or live Ollama: refresh, pull with cancel, load, unload, delete), sign-in, Test and delete;
  - the before and after capture set;
  - DD8 confirmed on screen.

  Fixes go through the fix-vs-feature gate.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- `make test-unit`: green. The ownership and sink checks pass. The provider files have no rows in either allowance. The inventory check passes with no demo rule.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`: green. New contract files run in both engines, and lane times are recorded.
- `ruff check` and `ruff format --check` are clean.
- `grep -rn "design-language\|devOnly" the_one/ tests/ scripts/ docs/ CLAUDE.md` returns only history (missions, squawks, run logs).
- The amended behavior specs read correctly against the app. Steps naming the Developer group or the page are gone.
- HAT: the operator approves the provider surfaces' before and after captures in both themes. Every visible difference traces to DD8 or a named squawk.

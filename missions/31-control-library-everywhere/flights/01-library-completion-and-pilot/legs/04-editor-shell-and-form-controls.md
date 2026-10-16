# Leg: editor-shell-and-form-controls

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Add the library controls every editor shares:
- `editorShell`, `section` and `dangerZone`;
- `confirm`, moved into the library from `confirm.js`, with `App.confirmDelete` kept as an alias and one armed style for every button;
- `infoButton`;
- the form-control extensions the provider editor needs: an `info` option on `field` and `toggle`, `dataset` passthrough on the native controls, and `setDisabled`.

Each lands with a catalogue row, owned classes and contract tests in both engines. No editor is migrated in this leg.

## Context
- **Flight decisions this leg follows:**
  - DD1's shell boundary: the shell emits `a.editor-breadcrumb-link` with an `href` and no handler of its own; `setDirty` only drives the caption and button enablement; the shell exposes `titleEl` and `focusTitle()` and never calls `App.focusAfter`.
  - DD2: the factory shape.
  - DD3: owned classes, and owners outside `js/ui/` moving in.
  - DD8: the canonical versions.
  - DD12: keyboard and role proof.
- **Legs 01-03 have landed.**
  - The catalogue has an Owned classes column and an "Owned by controls built later" table.
  - `tests/test_ui_ownership.py` checks every owned and planned class against an exact allowance (`tests/_ui_ownership_allowance.py`), in both directions.
  - `App.ui.icon(name, {size:'sm'})` exists.
  - Read the flight log's leg 01-03 entries before starting.
- **The look to reproduce is today's provider editor header.** `static/js/areas/studio/provider-editor.js:63-153` holds:

  ```
  div.editor-header
    div.editor-header-text
      div.editor-breadcrumb > a.editor-breadcrumb-link "Library" + " / Model providers"
      h1.editor-title[tabindex=-1]
      p.editor-subtitle
    div.form-actions
      span.editor-unsaved[role=status]
      button.btn-outlined-primary.cancel-btn
      button.btn-filled-primary.save-btn
      button.btn-outlined-primary.test-provider-btn
      span.editor-error
  ```

  Then come sections (`div.editor-section > div.section-title`) and the danger zone (`div.editor-section.danger-zone > div.section-title.danger-zone-title`, `button.btn-muted-destructive.delete-btn > span[data-confirm-title]`, `div.action-blocked-message.banner.banner-error`).
  - The factories reproduce this DOM shape and these classes, so CSS and look are unchanged.
  - The only visible differences allowed are the ones DD8 names:
    - Test gets the play icon and the standard button size;
    - the danger-zone delete button gets the 16px trash icon, and its armed label is "Confirm delete?";
    - every two-step confirm button gets the armed style.
- **Today's `App.confirmDelete`** (`static/js/confirm.js:71`, loaded at `index.html:55`): `(itemEl, onConfirm, opts)` with `opts.titleSelector` (default `[data-confirm-title]`), `opts.confirmLabel` (default "Confirm delete?") and `opts.revertMs` (default 3000).
  - The first call arms: it adds `.confirm-delete`, swaps the title text and starts a timer.
  - The second call commits: `onConfirm(itemEl, revert)`.
  - A lapse adds `.confirm-lapsed`. Every call clears `.confirm-lapsed` first.
  - The CSS armed states live at `components.css` (about `:870-877` `.ui-list-pane li`, `:1487` `.delete-btn`, `:1219` `.confirm-lapsed`) and `studio.css` (about `:1336-1344`, the KB folder summary).
- **Contract-test pattern:** `tests/browser/test_ui_choice_contract.py` (`engine_page` fixture, `load_harness`, `page.evaluate` mounts into `#harness-root`, role and keyboard asserts). `tests/browser/test_confirm_contract.py` exists today; read it.

## Inputs
- Legs 01-03 landed. `App.ui.icon` exists.
- `static/js/ui/field.js` (`field` already has `hint` and `error`), `static/js/ui/choice.js` (shared `build()` for checkbox and toggle), `static/js/ui/button.js`.

## Outputs
- `static/js/ui/editor.js` (new): `App.ui.editorShell`, `App.ui.section`, `App.ui.dangerZone`. They may be split into more files; each new file needs an `index.html` tag and pin updates.
- `static/js/ui/confirm.js`: moved from `static/js/confirm.js`, as `App.ui.confirm` plus the `App.confirmDelete` alias.
- `static/js/ui/info-button.js` or `field.js`: `App.ui.infoButton`; `field.js` and `choice.js` gain `info`, `dataset` and `setDisabled`.
- `static/css/components.css`: one banner per new control; the generic armed rule.
- `docs/ui-control-inventory.md`: rows and owned classes, with classes moved out of the "built later" table as their owner lands.
- Contract test files under `tests/browser/test_ui_*_contract.py`.
- `tests/_ui_ownership_allowance.py`, regenerated if moving `confirm.js` changes the counts.

## Acceptance Criteria
- [ ] **`App.ui.editorShell(opts)`**
  - **Options:**
    - `breadcrumb: {label, href, trail}`: renders `div.editor-breadcrumb > a.editor-breadcrumb-link[href][data-testid=editor-breadcrumb-link]` with the text `label`, then the text node `trail` (for example " / Model providers"). Supports the trailing-link variant the tools editor uses ("Settings / **Built-in tools**") through `breadcrumb: {lead, label, href}`, so all six editors can use it later. No click handler is attached.
    - `title` (required) and `titleLevel` (1 default, or 2). The title renders as `hN.editor-title[tabindex=-1]`.
    - `subtitle` (optional): `p.editor-subtitle`.
    - `actions: {cancel, save, test, extra}`:
      - `cancel: {label, testid, onClick, enabledWhenClean}`;
      - `save: {label, testid, onClick}`;
      - `test` (optional): `{label (default 'Test'), testid, onClick}`, built as an `App.ui.button` secondary, `sm` size, with the play icon;
      - `extra`: an array of nodes inserted before Cancel. This is how the agent editor's Chat button will fit.
    - `testid` (optional): the header.
  - **DOM:** reproduces the shape in Context, with `span.editor-unsaved[role=status][data-testid=editor-unsaved]` first in `div.form-actions`, and `span.editor-error` last.
  - **Returns** `{el, titleEl, focusTitle(), setTitle(text), setSubtitle(text|null), setDirty(bool), setBusy(bool), setError(text|null), cancelButton, saveButton, testButton}`:
    - `setDirty(true)` sets the caption text "Unsaved changes" and enables Save. With `cancel.enabledWhenClean` false, it also enables Cancel.
    - `setDirty(false)` clears the caption and disables Save. Cancel stays enabled when `enabledWhenClean`.
    - `setBusy(true)` disables Save, Cancel and Test.
    - `setError` sets or clears `span.editor-error`'s text.
    - `focusTitle()` focuses the title.
  - **Never:** reads the store or router, fetches, or calls `App.focusAfter`. `href` is supplied by the caller.
- [ ] **`App.ui.section(opts)`**
  - Options: `{title, titleTag ('div' default, or 'h2'/'h3'), description, testid, className, children}`.
  - Renders `div.editor-section` with a `.section-title` title, an optional `p.section-description`, then the children. An extra caller class (for example `admin-pf-models`) is appended through `className`.
  - Returns `{el, body, setTitle}`, where `body` is the element children append to.
- [ ] **`App.ui.dangerZone(opts)`**
  - Options: `{title ('Danger Zone' default), action: {label, testid, confirmLabel ('Confirm delete?' default), onConfirm(revert)}, notice: {testid}}`.
  - Renders `div.editor-section.danger-zone > div.section-title.danger-zone-title`, then `button.btn-muted-destructive.delete-btn`. Inside the button: a 16px trash icon from `App.ui.icon`, then `span[data-confirm-title]` with the label. With `notice`, it also renders `div.action-blocked-message.banner.banner-error[role=status][aria-live=assertive][hidden]`.
  - A click runs `App.ui.confirm(button, onConfirm, {confirmLabel})`.
  - Returns `{el, button, setNotice(text|null), setDisabled(bool)}`. `setNotice` shows or hides the banner.
- [ ] **`App.ui.confirm(el, onConfirm, opts)`**
  - Lives in `static/js/ui/confirm.js`, with exactly today's behaviour, including the lapse and `.confirm-lapsed` rules.
  - `window.App.confirmDelete` is an alias, the same function. `static/js/confirm.js` is deleted.
  - `index.html` loads the new file with the other `js/ui/*.js`, so every page caller still finds `App.confirmDelete`.
  - The script-count pin and any order pin are updated. `tests/browser/test_confirm_contract.py` keeps passing; move it to `tests/browser/test_ui_confirm_contract.py` so it joins the contracts lane and the engine parametrization.
- [ ] **One armed style for every two-step confirm button.** A `/* === App.ui.confirm === */` banner owns:
  - `button.confirm-delete` (the armed look the `.delete-btn.confirm-delete` rule draws today, generalized to any button, so reset and rotate buttons get it later);
  - `.confirm-lapsed`.

  The `.ui-list-pane li.confirm-delete` rule stays in the listPane banner, a library-internal use. The KB folder summary rule in `studio.css` stays as an allowance row until Flight 2 migrates it. A contract test shows that an armed `btn-outlined-primary` button gets a visibly different computed border colour from its unarmed state.
- [ ] **`App.ui.infoButton(opts)`**
  - Options: `{description (required), testid}`.
  - Returns `{el, descriptionId}`:
    - `el` is `button.field-info-icon[type=button]`, with `title` and `aria-label` set to the description and a `sm` info icon;
    - a sibling `span.visually-hidden[id]` holds the description, so a control can reference it by `aria-describedby`;
    - `el` wraps both, as `span.ui-info`.

    The exact wrapper is the Developer's choice. Keyboard: Tab reaches it, and its name is the description.
- [ ] **`App.ui.field` gains `info`.**
  - `opts.info` (a description string) renders the label inside `div.field-group-label` together with an `infoButton`. The label and the info button stay siblings; the button is never nested inside the label. The control's `aria-describedby` includes the description id.
  - `App.ui.toggle` and `App.ui.checkbox` gain `opts.info` the same way, with the info button after the label element.
  - All of `textInput`, `textarea`, `select`, `checkbox` and `toggle` accept `opts.dataset` (applied to the native control) and `opts.name`.
  - `toggle` and `checkbox` controllers gain `setDisabled(bool)`, which also toggles the root's `is-disabled`.
- [ ] **Catalogue.** Every new control has a `library:` row with its owned classes:
  - `editorShell`: `editor-header`, `editor-header-text`, `editor-breadcrumb`, `editor-breadcrumb-link`, `editor-title`, `editor-subtitle`, `form-actions`, `editor-unsaved`, `editor-error`;
  - `section`: `editor-section`, `section-title`, `section-description`;
  - `dangerZone`: `danger-zone`, `danger-zone-title`, `delete-btn`, `action-blocked-message`;
  - `confirm`: `confirm-delete`, `confirm-lapsed`;
  - `infoButton`: `field-info-icon`.

  Those classes leave the "built later" table. The rows for the item-header breadcrumb, the unsaved caption and the two-step confirm change from `not yet defined` to `library:`. The ownership allowance is regenerated, and its total does not grow except where a class newly becomes owned. The flight log records before and after totals.
- [ ] **Contract tests** in Chromium and WebKit, one file per control family:
  - **DOM shape and classes.**
  - **Roles and names:** `getByRole('link', {name: 'Library'})`, `heading` at the given level, `button` for Cancel, Save and Test, the info button by its description, and `status` for the unsaved caption.
  - **Tab order:** the breadcrumb link, then Cancel, Save, Test (disabled buttons are skipped).
  - **Every setter.**
  - **dangerZone:** arm (the label changes, `.confirm-delete` is present), commit (`onConfirm` is called), lapse after `revertMs` (`.confirm-lapsed` is present; use a short `revertMs`).
  - **toggle with `info`:** the info button is reachable by Tab, and the switch's `aria-describedby` includes the description.
  - **`setDisabled`.**
  - **The alias:** `App.confirmDelete === App.ui.confirm`.
- [ ] **Gates:**
  - `make test-unit`;
  - the static guards (`test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`);
  - `tests/test_ui_ownership.py`;
  - `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1` contracts lane;
  - `routing` and `chats` lanes: the `App.confirmDelete` callers are in Chats rows and the leave guard.
- [ ] **Docs:** `the_one/agents.md` "Control library (`App.ui`)" documents the new controls and the shell boundary (DD1). CLAUDE.md's `confirm-lapse` paragraph points at `static/js/ui/confirm.js`.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_index_asset_cache_busting.py -x -q`.
- `make test-unit`.
- `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts -x`, then `--lane routing -x` and `--lane chats -x` under netns.
- `grep -rn "static/js/confirm.js\|js/confirm.js" the_one/ tests/ scripts/ Makefile docs/` returns nothing (or only history).

## Implementation Guidance
1. **Move `confirm.js` first** (mechanical): new path, `App.ui.confirm` plus the alias, `index.html`, pins, the test file rename. Run `routing` and `chats` early to prove the alias.
2. **The generic armed rule.** Read the current `.delete-btn.confirm-delete` rule and generalize its selector; do not invent a new look.
3. **`infoButton`, then the `field`, `toggle` and `checkbox` extensions.** Keep `build()` shared.
4. **`section` and `dangerZone`.**
5. **`editorShell` last.** Build it to the exact DOM in Context, then compare by mounting it in the harness next to a copy of the provider editor's header markup, checking computed sizes of the title and actions in both themes. A contract test may assert key computed styles (title font size, action gap) equal the legacy markup's.
6. **Catalogue rows, the allowance regeneration, docs.**

## Edge Cases
- **The `data-confirm-title` span must stay inside the button**, so `confirm`'s title swap works. The icon sits outside that span, so the swap does not delete it.
- **`setDirty` in create mode:** Cancel is enabled from the first render (`enabledWhenClean: true`), matching today's create form.
- **The Test button's play icon** must not change its accessible name ("Test"). The icon is `aria-hidden`.
- **A title change while focused** keeps focus: `setTitle` sets `textContent` only.
- **`field` with `info` and `labelHidden`:** the info button stays visible; the label is visually hidden.
- **WebKit Tab order:** buttons need focusing on macOS-style WebKit. Use the existing contract tests' approach for keyboard focus (read `test_ui_choice_contract.py` and `test_ui_library_contract.py`).

## Files Affected
- **New:** `static/js/ui/editor.js` (or split), `static/js/ui/confirm.js`, `static/js/ui/info-button.js` (optional).
- **Deleted:** `static/js/confirm.js`.
- **Modified:** `static/js/ui/field.js`, `static/js/ui/choice.js`, `static/index.html`, `static/css/components.css`.
- **Tests:** `tests/browser/test_confirm_contract.py` → `test_ui_confirm_contract.py`; new `tests/browser/test_ui_editor_contract.py`, `test_ui_info_contract.py` (or as the Developer groups them); `tests/test_index_asset_cache_busting.py`, `tests/test_makefile_verify_serving.py` if its sample or count changes; `tests/_ui_ownership_allowance.py`.
- **Docs:** `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md` (only for new testids), `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Checked 2026-10-15 at `59992fd` plus legs 01-03:
- `provider-editor.js:63-153` (header markup and breadcrumb insertion, quoted in Context);
- `confirm.js:71` (signature and behaviour);
- `index.html:55` (`confirm.js` tag);
- `ui/field.js:119-210` (`field` with `hint`/`error`, `{el, control, setError, setHint}`);
- `ui/choice.js` `build()` (shared, `opts.hint`, `data-ui-own-label`);
- `tests/browser/test_confirm_contract.py` exists.

## Design Review Addenda (2026-10-15)
These are binding additions:
- **Two more tests break when `confirm.js` moves.** `tests/browser/test_ui_list_pane_chats_contract.py:63` and `:566` call `add_script_tag(path=STATIC_DIR/"js"/"confirm.js")`. Delete both calls: `load_harness` loads every `js/ui/*.js` from `index.html`. Also fix that file's docstring (`:10`).
  - Update the comment-only mentions in `test_flow_admin_rotate_flash.py:114`, `test_flow_studio_knowledge_inventory.py:224,1368` and `components.css` (about `:1157`, `:1429`).
  - The final grep is `confirm\.js` without the `js/` prefix. Only `ui/confirm.js` and history may remain.
- **Armed-rule specificity.** `button.confirm-delete` (0,1,1) loses to `.btn-outlined-primary:hover` and `.btn-muted-destructive:hover` (0,2,0). Write the rule as `button.confirm-delete, button.confirm-delete:hover, button.confirm-delete:focus-visible` (at least (0,2,1)), in `@layer components` after the button variants.
  - The contract test asserts the armed look **while hovered** too, for both `btn-outlined-primary` and `btn-muted-destructive`.
  - Add the armed text/background pair (the tokens the existing `.delete-btn.confirm-delete` uses, for example `--fg-on-danger` on `--status-danger`) to `tests/test_design_tokens_a11y.py` for both themes, if it is not pinned there already.
- **`.confirm-lapsed` stays element-agnostic** (no `button` scoping) when it moves under the `confirm` banner.
- **`editorShell` additions:**
  - **Classes:** Cancel is `btn-outlined-primary cancel-btn`, Save is `btn-filled-primary save-btn`, and Test is `btn-outlined-primary test-provider-btn` by default, overridable with `actions.test.className`. Editors and their `checkDirty` code select `.cancel-btn` and `.save-btn`.
  - **`afterTitle`:** an optional node inserted in `editor-header-text` after the title and before the subtitle, for the connector editor's LED status row.
  - **Optional actions:** `cancel`, `test` and `extra` are optional; `save` is required. Cancel's starting state is `disabled` unless `enabledWhenClean: true` (create forms). Save starts disabled in every mode until `setDirty(true)`. This matches today's connector and KB create forms.
  - **`setSaveLabel(text)`** exists, for an editor that changes from Create to Save without a re-mount.
  - **The breadcrumb:** `trail` and `lead` are always text nodes, never links. Only `label` is the link.
- **`index.html` placement:** `ui/confirm.js` goes after `ui/core.js` and before any file that uses it. The file guards `window.App.ui = window.App.ui || {}`.
  - The script-count pin's new total equals 71 plus the number of new `js/ui/*.js` files this leg adds (the move itself is neutral), with a dated comment line.
- **`dataset` collisions:** a `dataset` key never overrides `data-testid`. `testid` wins, and the `dataset` key `testid` is ignored.
- **Extra contract cases:** `App.confirmDelete` on a `<summary>` and on an `<li>` still arms, commits and lapses. Those are unmigrated callers: the KB folder summary and chat rows.
- `git mv tests/browser/test_confirm_contract.py tests/browser/test_ui_confirm_contract.py`, and update its docstring (old path, and the lane is now `contracts`).
- **Answers to the review's questions:**
  - Create mode is `enabledWhenClean: true` for Cancel, with Create disabled until a field changes. The KB create form's Create starts disabled.
  - The provider's "Confirm Delete?" capital-D label changes in leg 07, with its tests.
- **Leg size:** kept as one leg. The Implementation Guidance order already runs the confirm move and armed style first, then infoButton and the field extensions, then section, dangerZone and the shell, so a failure surfaces early.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

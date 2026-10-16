# Leg: feedback-and-value-controls

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Add the library's feedback and value controls the provider surfaces need:
- `status` (the LED and the status line);
- `flash`;
- `copyField` and `copyButton`;
- `consentLink`, moved into the library and rebuilt on `copyField`;
- `progress`;
- a display-only `chip`.

Each lands with a catalogue row, owned classes and contract tests in both engines. The existing callers of `App.showFlash` and `App.consentLink` keep working through aliases. No editor is migrated in this leg.

## Context
- **Flight decisions:**
  - DD2: factory shape; controls that change while shown return a controller.
  - DD3: owners outside `js/ui/` move in; `App.showFlash` and `App.consentLink` become aliases.
  - DD8, settled by the operator:
    - **Copy feedback:** the button's text reads "Copied" for 2s, with a polite announcement; "Copy failed" on failure; the clipboard fallback everywhere; no flash.
    - **Status:** one 10px LED and one status-line style (body-sm, muted). Test results show the LED and text with no ✓/✗ glyphs.
  - DD9: the display chip is built here for the models panel.
- **Legs 01-04 have landed.** `App.ui.icon`, `editorShell`, `section`, `dangerZone`, `confirm` (with the `App.confirmDelete` alias) and `infoButton` exist. The reuse check (`tests/test_ui_ownership.py`) counts owned and planned classes and the retired-API calls (`api:App.showFlash(`, `api:App.consentLink.`) against an exact allowance. Read the flight log's leg 01-04 entries first.
- **`App.consentLink`** (`static/js/consent-link.js:30-130`, `build(url, {surface, sourceName})`):
  - It already implements the DD8 copy feedback: "Copied" for 2s, a `role=status` live region saying "Link copied", and an `execCommand` fallback, with "Copy failed — select the link and copy it" announced on failure.
  - Its testids are hard-coded per surface (`chat-consent-link-*` / `mcp-consent-link-*`) so the registry extractor sees them.
  - `isSafeUrl` and `focusTarget` are also exported.
  - Callers: `areas/chat.js:1236,1349,1372,1991` and `areas/studio/mcp-server-editor.js:1860,1865,1886`.
  - The provider editor's fork (`provider-editor.js:630` `buildConsentBlock`) is migrated in leg 07, not here.
- **`showFlash(container, msg, isError)`** (`static/js/app.js:286`):
  - `div.app-flash` (`.error` for errors);
  - `role=alert` for errors, else `role=status` with `aria-live=polite`;
  - shown after 10ms (`.visible`), removed after 5s plus a 300ms fade;
  - exported on `window.App` (about `:325`);
  - CSS at `components.css:10-12`.
- **The LED and test-result styles to reproduce:** `.indicator-led` with `--success`, `--warning`, `--danger` and `--idle` (`components.css`, about `:1418`), and `.test-result-*::before` dots (about `:1434-1447`). Grep for the exact rules.
- **The pull progress to reproduce:** `provider-models.js:134-138` (`div.admin-pf-pull-progress > div.admin-pf-pull-fill + span.admin-pf-pull-text + button.admin-pf-pull-cancel[aria-label="Cancel pull"]` with an `x` icon) and its `admin-pf-pull-*` rules in `studio.css` (about `:1623-1679`). Today the fill's width is set by `style.width`.
- **The chip to reproduce:**
  - `.chip` (`components.css:535`) and `.cap-chip-no-tools` (about `:546-552`, danger palette);
  - `provider-models.js:31` `renderCapabilityChips` builds `span.cap-chip-row > span.chip.cap-chip…`, with the no-tools chip carrying a `title`.

## Inputs
- Legs 01-04 landed.

## Outputs
- `static/js/ui/feedback.js` (extended) or new `static/js/ui/*.js`: `status`, `flash`, `progress`, `chip`, `copyField`, `copyButton`.
- `static/js/ui/consent-link.js`: moved from `static/js/consent-link.js`, as `App.ui.consentLink` (with `isSafeUrl` and `focusTarget` as properties) plus the `App.consentLink` alias.
- `static/js/app.js`: `showFlash` delegates to `App.ui.flash`.
- `static/css/components.css`: one banner per control, holding the moved rules.
- Catalogue rows, contract tests, a regenerated ownership allowance, and registry rows for new testids.

## Acceptance Criteria
- [ ] **`App.ui.status(opts)`**
  - Options: `{state: 'success'|'warning'|'danger'|'idle'|'pending', text, ledLabel, live ('polite' default, or 'off'), testid}`.
  - Renders `p.ui-status` containing `span.indicator-led.indicator-led--<state>` (10px) and a text span, styled body-sm and muted (DD8).
  - The LED is `aria-hidden` when `text` is present. With no text, it carries `role=img` and `aria-label=ledLabel`.
  - Returns `{el, set(state, text)}`. `pending` shows the idle LED.
  - The status line has no ✓/✗ glyphs.
  - The `.indicator-led*` rules move into the `App.ui.status` banner, with the same look.
- [ ] **`App.ui.flash(message, opts)`**
  - Options: `{error, container (default document.body)}`.
  - Reproduces `showFlash` exactly: classes, roles, the 10ms show, the 5s dwell, the fade and removal.
  - Returns the element.
  - `App.showFlash(container, msg, isError)` in `app.js` becomes a one-line delegate.
  - The `.app-flash` rules move into the `App.ui.flash` banner unchanged.
- [ ] **`App.ui.copyButton(opts)`**
  - Options: `{text (string or function returning the value to copy), selectEl (an input or textarea selected for the execCommand fallback), label ('Copy' default), iconOnly (bool; uses the `copy` icon with `aria-label=label`), testid, liveEl}`.
  - Copies through `navigator.clipboard.writeText`, falling back to `selectEl.select()` plus `document.execCommand('copy')`.
  - On success: the visible text becomes "Copied" for 2s; for `iconOnly`, the `aria-label` becomes "Copied" and an optional check icon may swap in. The live region announces "Copied".
  - On failure: the visible text and announcement are "Copy failed".
  - It owns a visually-hidden `role=status` live region inside its returned root unless `liveEl` is given.
  - Returns `{el, button}`.
- [ ] **`App.ui.copyField(opts)`**
  - Options: `{value, label (the accessible name of the read-only input), mono (default true), testid, copyTestid, extra (nodes placed between the input and the Copy button)}`.
  - Renders a read-only `input.field-input` and a `copyButton` in one row (`div.ui-copy-field`).
  - Returns `{el, input, button, setValue}`.
- [ ] **`App.ui.consentLink`**
  - Lives in `static/js/ui/consent-link.js`, rebuilt on `copyField`, with the `Open sign-in page` anchor passed as `extra`.
  - **The DOM, the text, the safe-URL rule and the unsafe-URL notice stay as today.** Same classes on the root (`consent-link consent-link--<surface>`), row, input, open link and help. The Copy button's class may change from `consent-link-copy` to the library's, but `consent-link-copy` stays on it if any test selects it.
  - **Test ids** become caller options: `urlTestid`, `openTestid`, `copyTestid`. When the caller passes none, `surface: 'chat'|'mcp'` keeps producing today's literal ids, so existing callers and tests are unchanged.
  - `App.consentLink` is the same object (`build`, `isSafeUrl`, `focusTarget`).
  - `static/js/consent-link.js` is deleted. `index.html`, the script-count pin and `tests/test_consent_link_static.py`'s order pin are updated.
- [ ] **`App.ui.progress(opts)`**
  - Options: `{label (the accessible name), value (0-1, or null for indeterminate), text, onCancel, cancelLabel ('Cancel' default), testid, cancelTestid}`.
  - Renders `div.ui-progress[role=progressbar]` with `aria-valuemin=0`, `aria-valuemax=100` and `aria-valuenow` (omitted when indeterminate), `aria-label=label`, a fill element, a text span, and, when `onCancel` is given, an icon-only cancel button with the `x` icon and `aria-label=cancelLabel`.
  - Its look reproduces the current pull bar: the `admin-pf-pull-progress`, `-fill`, `-text` and `-cancel` rules are copied into the `App.ui.progress` banner as `ui-progress-*`. Leg 06 switches the pull to it and deletes the old rules.
  - Returns `{el, set(value, text), setCancelDisabled(bool)}`.
- [ ] **`App.ui.chip(opts)`**
  - Options: `{label, tone ('neutral' default, or 'danger'), title, testid}`.
  - Renders `span.chip` (`span.chip.chip--danger` for danger).
  - `.chip--danger` reproduces `.cap-chip-no-tools`'s look; that rule is copied into the `App.ui.chip` banner. Leg 06 switches the callers and deletes the old one.
  - Returns the node. It is display-only: no remove button (the editable chip list is Flight 2).
- [ ] **Catalogue.** Every new control has a `library:` row with its owned classes:
  - `status`: `ui-status`, `indicator-led` (with its modifiers);
  - `flash`: `app-flash`;
  - `copyButton` / `copyField`: `ui-copy-*`;
  - `consentLink`: `consent-link`, `consent-link-*`;
  - `progress`: `ui-progress*`;
  - `chip`: `chip`, `chip--danger`.

  Those classes leave the "built later" table. The rows for the flash message, the indicator LED and status lines, copy buttons and the consent link change status accordingly. The rows still mention sites that migrate in later flights, under Owner / migration. The ownership allowance is regenerated, and the flight log records the before and after totals.
- [ ] **Contract tests** in Chromium and WebKit:
  - **status:** roles and labels in both text and LED-only modes; `set` changes the class and text; no glyphs.
  - **flash:** the role per kind, `.visible` after show, removal after the dwell. Use a short dwell override if the factory accepts `opts.duration`; otherwise use Playwright's clock.
  - **copyButton / copyField:** clipboard success through a granted permission in Chromium, or a stubbed `navigator.clipboard` in both engines; "Copied" and the announcement; the failure path with clipboard rejecting and `execCommand` returning false shows "Copy failed"; text reverts after 2s (fake clock); `iconOnly` names.
  - **consentLink:** safe and unsafe URLs, the default chat and MCP testids, custom testids, `focusTarget`.
  - **progress:** ARIA values, indeterminate, cancel callback and name, the Tab order (cancel reachable).
  - **chip:** both tones, the `title`.
- [ ] **Existing consent-link and flash behaviour holds.**
  - The chat and MCP sign-in browser tests pass: `tests/browser/test_oauth_modal_flow.py`, any `test_*consent*`, and the MCP editor sign-in tests.
  - Any test that asserts the flash still passes.
  - Run the `chats`, `mcp`, `routing` and `providers` lanes under netns.
- [ ] **Gates:**
  - `make test-unit`;
  - the static guards;
  - `tests/test_ui_ownership.py`;
  - the contracts lane with WebKit required;
  - the lanes listed above.
- [ ] **Docs:** `the_one/agents.md` "Control library (`App.ui`)" and the MCP or consent-link sections that name `consent-link.js`; the `CLAUDE.md` M29 paragraph if it names the file path.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_index_asset_cache_busting.py tests/test_consent_link_static.py -x -q`.
- `make test-unit`.
- `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts -x`, then `--lane chats`, `--lane mcp`, `--lane providers` and `--lane routing` under netns, run in the background with `TEST_TIMEOUT` set.
- `grep -rn "js/consent-link.js" the_one/ tests/ scripts/ docs/ Makefile` returns only history.

## Implementation Guidance
1. **`flash` first**, then the `app.js` delegate: smallest, and it proves the alias pattern.
2. **`status`**, moving the LED rules.
3. **`copyButton` and `copyField`**, extracting the logic from `consent-link.js`'s Copy so there is one implementation.
4. **Move `consent-link.js`** into `js/ui/` and rebuild it on `copyField`. Keep its DOM and default testids identical, and run the chat and MCP sign-in tests early.
5. **`progress` and `chip`**, copying the existing rules into banners.
6. **Catalogue, allowance, registry, docs.**

## Edge Cases
- **The registry extractor and option testids.** `testid:` and `<word>Testid:` option values are extracted. Today's literal `setAttribute` ids in `consent-link.js` must still be found after the move. Keep them as literals in the default branch, or the registry sync test fails.
- **Clipboard in WebKit.** `navigator.clipboard.writeText` may be unavailable or reject in the harness. Test the success path with a stub so both engines run the same code.
- **The 2s revert running after the node is removed** (the user navigated away): guard with `isConnected` before writing.
- **The flash container** may be a detached node in tests. Keep `container` optional and default it to `document.body`.
- **`progress` set to 1 with text "Done"** must not leave the cancel enabled. The caller decides; `setCancelDisabled` exists for that.

## Files Affected
- **New:** `static/js/ui/consent-link.js`; possibly `static/js/ui/status.js`, `copy.js` and `progress.js`, or all in `feedback.js`.
- **Deleted:** `static/js/consent-link.js`.
- **Modified:** `static/js/ui/feedback.js`, `static/js/app.js`, `static/index.html`, `static/css/components.css`.
- **Tests:** new `tests/browser/test_ui_status_contract.py`, `test_ui_flash_contract.py`, `test_ui_copy_contract.py`, `test_ui_consent_link_contract.py`, `test_ui_progress_contract.py`, `test_ui_chip_contract.py` (or grouped); `tests/test_consent_link_static.py`, `tests/test_index_asset_cache_busting.py`, `tests/_ui_ownership_allowance.py`.
- **Docs:** `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Checked 2026-10-15 at `59992fd`:
- `consent-link.js:30-130` (`build`, copy feedback, testids, exports);
- `app.js:286` (`showFlash`);
- `components.css:10-12` (`.app-flash`), `:535` (`.chip`), `:546-552` (`cap-chip-no-tools` comment and rule);
- `provider-models.js:31` (`renderCapabilityChips`), `:134-138` (pull progress markup);
- consent-link callers in `chat.js` and `mcp-server-editor.js` (grep).

## Design Review Addenda (2026-10-15)
These are binding and take precedence over the criteria above where they differ:
- **Consent-link announcements are unchanged.**
  - `copyButton` gains `doneText` (default "Copied", the announcement) and `failText` (default "Copy failed"), plus the existing `liveEl`.
  - `consentLink` passes `liveEl` (its own `span.visually-hidden.consent-link-live[role=status]`), `doneText: 'Link copied'` and `failText: 'Copy failed — select the link and copy it'`. So `tests/browser/test_oauth_modal_flow.py:546` keeps passing unchanged.
  - The visible button text is "Copied" for 2s in every case.
  - **Accessible name follows the visible text** (WCAG 2.5.3, label in name). The button carries no `aria-label` override, so its name reads "Copied" while the text does. This is a small, recorded change from today's `aria-label="Copy"`; the `iconOnly` variant's `aria-label` changes the same way.
- **The `iconOnly` check-icon swap is dropped.** Only the `aria-label` and the announcement change.
- **Script order:** `ui/consent-link.js` loads after the file that defines `copyField`/`copyButton` (for example after `ui/feedback.js` or a new `ui/copy.js`) and before `areas/chat.js` and `areas/studio/mcp-server-editor.js`.
  - `tests/test_consent_link_static.py`: `MODULE` becomes `js/ui/consent-link.js`, and its order pin becomes "defining file < `ui/consent-link.js` < consumers".
  - Its literal-testid test keeps passing: the default testids stay as literal `setAttribute('data-testid', 'chat-consent-link-url')` calls in an if/else per surface, as today. Never use a ternary, because the registry extractor needs the `setAttribute` literal form.
  - When a caller passes `urlTestid`, `openTestid` or `copyTestid`, those win. `urlTestid` maps to `copyField`'s input `testid`.
- **Class preservation:**
  - `copyField` gains `inputClass` and `rowClass` options;
  - `consentLink` passes `inputClass: 'consent-link-url'` and `rowClass: 'consent-link-row'`, so `focusTarget` (which queries `.consent-link-open`, `.consent-link-url` and `.consent-link-unsafe`) and the consent CSS keep working;
  - the Copy button keeps `consent-link-copy`;
  - the order inside the row stays input, open anchor (`extra`), Copy.
- **`.test-result-*` dots are out of scope** (leg 07 and later editor migrations): the `.test-result*` rules stay where they are.
  - Non-goal for this leg: `tools-editor.js`'s "✗" glyphs (`:618`, `:743`) and other `test-result` emitters.
  - The catalogue's "built later" table gains `test-result` (owner `status`, Flight 1 leg 07 and Flight 2).
- **`indicator-led` users that bypass the factory** (connector-editor, mcp-server-editor, provider-models, self-configuration-tab, provider-editor) become allowance rows when the allowance is regenerated. The catalogue's status row names them under Owner / migration.
  - `pending` maps to the idle LED class (`indicator-led--idle`); there is no `--pending` class.
  - When `set(state, '')` clears the text, the LED switches to `role=img` with `aria-label=ledLabel` (and `aria-hidden` is removed).
- **CSS moves:**
  - `.app-flash` and `.indicator-led*` move within `components.css` into their banners, **inside the same `@layer components` block**, with identical declarations. Check the `@layer` boundaries before moving.
  - The `chip` banner owns only `.chip` and `.chip--danger`, with `.chip--danger` placed after `.chip`. `.chip-remove` and the chip-list rules stay where they are and remain "built later" (Flight 2).
- **Flash:**
  - `App.ui.flash(message, {error, container, duration})` defaults the dwell to 5000ms;
  - the removal timers are guarded with `isConnected`;
  - `App.showFlash`'s delegate is `App.ui.flash(msg, {error: !!isError, container: container || document.body})`;
  - the flash contract test calls `App.ui.flash` directly: the disk harness does not load `app.js`;
  - existing `App.showFlash(…)` call sites are **not** rewritten in this leg (`tests/test_store_static.py:329` pins one call's text).
- **Untouched callers:** `markdown.js`'s code-block copy (`:800`, flash "Copied!", asserted by `tests/browser/test_markdown.py:826`) is not touched here; Flight 4 migrates it.
- **Registry:** the library's default consent testids are the same ids already registered; add no new ones for them.
- Use `App.ui.icon('copy')` and `App.ui.icon('x')`; both exist in `icons.js`.
- **`App.ui.chip` gains `size: 'sm'`** (added after leg 06's design review): `.chip--sm`, in the chip banner, carries today's `.cap-chip` size (tiny font, `2px 8px` padding; copy the exact declarations from `components.css` about `:552`). It has a contract case.
- `progress` sets the fill with `style.width` through the DOM, and indeterminate is a class (`ui-progress--indeterminate`), not an inline animation.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

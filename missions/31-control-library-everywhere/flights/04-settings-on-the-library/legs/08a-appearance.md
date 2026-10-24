# Leg: appearance

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Rebuild Settings › Appearance on the library:
- the page header through `App.ui.pageHeader` (`App.admin.renderPage` delegates to it from here on);
- the theme picker as an `App.ui.radioGroup` in its card look (operator), built in `system-page.js`.

`App.theme.renderToggle`, its HTML-string sink and its leaked document listener (DD8-19) are retired. Update the tests and the two Windows behavior specs that drive the picker.

## Context
- **Flight decisions:** DD6 (Appearance), DD8-19, DD12 (`pageHeader`'s legacy names are still emitted; ownership hands over in leg 10), DD10 (pins and specs), DD7 (ledger row 39: the card look).
- **Today:**
  - `system-page.js:21-29` `renderPage` builds the page header by hand; it is exported as `App.admin.renderPage` and used by Date and time;
  - `:40-51` mounts `App.theme.renderToggle(mount, {labelledBy})`;
  - `theme.js:208-286` builds three `button.admin-theme-option[role=radio][data-theme-pref]` with its own arrow-key handling and a `container.innerHTML = ''` sink (`:230`), plus a **document** listener on `THEME_EVENT` cleaned only by the next `renderToggle` call (`_activeThemeListenerCleanup`, `:174`), so it outlives the page (DD8-19).
- **`theme.js` loads in `<head>` before `js/ui/`**, so the picker must be built in `system-page.js`. `theme.js` keeps `App.theme.set/get`, the desktop chrome signal (`POST /api/window/chrome` through `theme.js`), the `THEME_EVENT` dispatch and `App.desktop.isWebview` (`test_consent_link_static.py:38` reads it there).
- **The picker after this leg:** `App.ui.radioGroup({legend: 'Theme' (or labelled by the section heading), options: [{value: 'light', label: 'Light'}, {value: 'dark', label: 'Dark'}, {value: 'auto', label: 'Auto', description?}], value: App.theme.get(), onChange: App.theme.set, testid: 'theme-picker', optionTestids: 'theme-option-{value}'})`.
  - It follows `THEME_EVENT` (another tab or the desktop shell changing the theme) through a listener **owned by the page**, removed when the page unmounts (through `App.time.onChange`-style owner detection or the page's teardown; pick one and say which).
  - Native radios give arrow-key selection.
- **The `.admin-theme-option[data-theme-pref=…]` selector** is used by:
  - `test_flow_admin_settings_nav.py:243`, `:327`, `:331`;
  - `test_flow_settings_window_chrome_signal.py:49`, `:65`, `:108`, `:125`;
  - `test_theme_cross_tab_sync.py:45`;
  - `test_theme_toggle_cleanup.py` (the whole file tests `renderToggle`, so rewrite it as a test of the page-owned listener's cleanup);
  - the a11y pin `test_design_tokens_a11y.py:625-629` (`.area-admin .admin-theme-option.active`, deleted with its rule);
  - the behavior specs `tests/behavior/windows-window-chrome.md` step 4 (about line 110) and `windows-native-frame-splash.md` steps 11-14 and 19.

  All move to `[data-testid="theme-option-{value}"]` or `get_by_role('radio', name=…)`.

## Inputs
- Leg 04a (`pageHeader`) landed; `App.ui.radioGroup` exists.

## Outputs
- `system-page.js`: `renderPage` delegating to `App.ui.pageHeader` (it still returns what its callers use; check Date and time's use); Appearance built with `section` and `radioGroup`.
- `theme.js`: `renderToggle` and `_activeThemeListenerCleanup` removed, with zero sinks (its `HTML_SINK_ALLOWANCE` row removed).
- `admin.css`: `.admin-theme-toggle` and `.admin-theme-option*` (about `:82-117`) removed.
- Tests: the files above retargeted; `test_theme_toggle_cleanup.py` rewritten; DD8-19 test-first (after leaving Appearance, dispatching `THEME_EVENT` reaches no listener on a detached node: assert through a counter hook or by checking that the old page's radio is not updated); the a11y pin removed; the capture compare (ledger row 39).
- The behavior specs amended (the selector and expected look, steps only).
- The registry: `theme-picker` and `theme-option-{light|dark|auto}` added; the catalogue: Radio group (theme) row resolved (it was "not yet defined").

## Acceptance Criteria
1. **The picker is a radio group in the card look**, with native radios: arrows select, the checked option matches `App.theme.get()`, and choosing sets the theme (the desktop chrome signal still fires: `test_flow_settings_window_chrome_signal.py` passes retargeted).
2. **Cross-tab and shell changes** update the picker while Appearance is shown (`test_theme_cross_tab_sync.py` passes retargeted).
3. **DD8-19:** after leaving Appearance, no theme listener for the old page remains. The test fails on today's code.
4. `theme.js` has no `renderToggle`, no sink and no `HTML_SINK_ALLOWANCE` row. `admin.css` has no `.admin-theme-*` rule.
5. The page header comes from `pageHeader`. The `.page-title` selectors still match.
6. The behavior specs are amended. The capture compare shows only ledger row 39.
7. The unit tier, the static guards, and the `settings` and `shared` lanes pass.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_design_tokens_a11y.py tests/test_consent_link_static.py tests/test_settings_pages_static.py -q -x --timeout 120`.
- Lanes `settings` and `shared` under netns; the capture compare; `make test-unit` once.

## Edge Cases
- **The `auto` option** follows the OS. Its description (if any) keeps today's text.
- **The desktop webview:** no change to the chrome signal. Note in the flight log that the WebView2 path is checked at the HAT, or with `scripts/windows_test_copy.py` if the operator wants it.

## Files Affected
- `static/js/areas/admin/system-page.js`, `static/js/theme.js`, `static/css/admin.css`.
- The tests listed above, `tests/test_ui_guards.py` (`HTML_SINK_ALLOWANCE`).
- `tests/behavior/windows-window-chrome.md`, `windows-native-frame-splash.md`.
- `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- `theme.js:146`, `:162`, `:174`, `:193`, `:208`: verified (FD grep).
- `system-page.js:21-51`; the test selector lines; `admin.css:82-117`: from the pages survey.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **`scripts/ui_capture.py:902`** selects `#admin-theme-toggle-mount`. Retarget it to `[data-testid="theme-picker"]` (add it to Files Affected), or the Appearance capture breaks.
- **Behavior specs:**
  - `windows-window-chrome.md` steps 4 and 7 (the selector);
  - `shell-navigation-smoke.md` steps 6 and 7, which expect `aria-checked="true"` on a "radiogroup" option; native radios report `checked`, and the fieldset's role is `group`, so amend them;
  - `windows-native-frame-splash.md` steps 11-14 and 19 say only "choose Light/Dark/Auto": a wording check at most.
  - Past run logs under `*/runs/` stay as they are (history).
- **The listener mechanism (DD8-19):**
  - a document `THEME_EVENT` listener that **prunes itself**: on each event it checks `group.el.isConnected`, and if the group is gone it removes itself and returns; otherwise it calls `group.setValue(e.detail.pref)` (the `App.time.onChange` owner precedent);
  - a re-render on the same container does not stack listeners (the old one prunes on the next event);
  - **the test** spies on `document.addEventListener`/`removeEventListener` before navigating, navigates away, dispatches `theme-preference-changed` once, then asserts the adds and removes balance and that the old radio was not updated. Never assert "listener gone" before the dispatch.
- **The radio group:**
  - `App.ui.radioGroup({legend: 'Theme', legendHidden: true, options: [{value: 'light', label: 'Light', testid: 'theme-option-light'}, {value: 'dark', label: 'Dark', testid: 'theme-option-dark'}, {value: 'auto', label: 'Auto', testid: 'theme-option-auto'}], testid: 'theme-picker'})`;
  - the option testids land on the native inputs, and tests `.check()` or `.click()` them;
  - no `auto` description (there is none today);
  - `test_flow_admin_settings_nav.py:243-253` moves to `get_by_role('group', name='Theme')` and `get_by_role('radio')` (3), and its `theme` locator at `:310`/`:318` is retargeted.
- **The look** changes from a horizontal segmented row to the library's stacked full-width cards (ledger row 39), inside `.admin-form`'s 880px maximum width. The `admin-system-section` and `.banner-warning` rules stay untouched in this leg.
- **The a11y pin** for the checked option (`test_design_tokens_a11y.py:625-629`) is deleted with its rule. Confirm that an existing pair covers the `radioGroup` checked state (accent border), or add one, so the checked theme option still has an AA check.
- **`renderPage`** returns nothing. It delegates to `pageHeader({title, headingId})`, keeps the `.admin-form > .admin-system-section` wrapper, and is the only place the heading id reaches the `h1`. `admin-appearance-heading` is kept only as the `h1`'s id.
- **Bookkeeping:**
  - remove `HTML_SINK_ALLOWANCE["theme.js"]` (`test_ui_guards.py:155`);
  - rewrite `test_theme_toggle_cleanup.py` (renamed, for example `test_theme_picker_listener.py`);
  - `admin-theme-toggle-mount` goes in the registry's retired table and `RETIRED_SELECTORS`; `theme-picker` and the option testids are added;
  - the catalogue rows at `docs/ui-control-inventory.md` `:68` and `:70`;
  - `theme.js`'s comments that mention `renderToggle` are updated.
- **Order:** the failing DD8-19 test first, then the page, then the `theme.js` deletion.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

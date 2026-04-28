# Leg: 01-system-merge-and-section-nav-lift

**Status**: landed
**Flight**: [Administration Alignment](../flight.md)

## Objective

Merge the General + System categories into a single combined "System" page and migrate the admin sidebar from its bespoke `.admin-category-list` markup to the canonical `.section-nav` primitive (lifted to a new `App.layout.renderSectionNav` helper that both admin and studio consume).

## Context

This leg is the structural foundation for F6's admin alignment. Three things change in lockstep:

1. **Category collapse**: the current three categories (General, LLM Providers, System) become two (System, LLM Providers). The General page's read-only env-var-derived rows (paths, server, concourse) move into the new System page as a new "Environment" section above the existing Appearance + Encryption sections.

2. **Section-nav helper namespace lift** (per F6 flight Design Decision: "Sidebar migrates to canonical `.section-nav`"): rename `App.studio.renderSectionNav` → `App.layout.renderSectionNav` (+ `updateActiveSection` similarly). The helper currently has hardcoded `SECTIONS` (Agents / Knowledge / Tools) + hardcoded "Studio" header — it must accept `items` array + `header` text as parameters so admin (with different items + header) can reuse it. File moves from `static/js/areas/studio/section-nav.js` to `static/js/areas/layout/section-nav.js`. Studio's existing call-site updates to the new API.

3. **URL contract extension**: `#admin` redirects to `#admin/system` (free side-effect of `serializeState()` returning `'system'` when no explicit sub — the F3 router's serialize-after-hydrate path at `app.js:179-185` does the redirect, no new code in admin). `#admin/system` shows the combined page; `#admin/providers` unchanged for now (leg 02 territory). Legacy `#admin/general` defensively redirects to `#admin/system` via `hydrateState(sub)` — supports any external hard-link still pointing at the old URL.

Subsequent legs depend on this leg's foundations:
- **Leg 02** consumes `App.layout.renderSectionNav` from this leg + builds the page-header on top of the section content panel.
- **Leg 03** depends on the new `App.admin` sub-module namespace pattern this leg establishes.
- **Leg 04** depends on the closure-state shape (no `general` category) for the dirty-gate's category-nav route.

Key prior context:
- F5 leg 01 documented that admin's category nav was the imminent F6 consumer of `.section-nav` (F5 flight.md:235); F6 fulfills that.
- F5 debrief Action Item #2 ("audit area init() bottom block for legacy auto-selects against new URL contracts") applies — admin's current `init()` ends with `renderCategoryList()` + `renderContent()` and renderContent on `'general'` calls `fetchSettings()`. Leg 01 changes the default to `'system'` and verifies no legacy auto-select assumption survives (no fetchSettings call needed if the System page is now the default; it carries its own fetch).

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/js/areas/studio/section-nav.js` exists with hardcoded `SECTIONS` array + "Studio" header text (path-mounted at `App.studio.renderSectionNav`).
- `the_one/interfaces/web/static/js/areas/admin.js` exists with three categories (`general`, `providers`, `system`), bespoke `renderCategoryList` + `admin-category-item` markup, separate `renderGeneralPanel` + `renderSystemPanel` rendering paths.
- `the_one/interfaces/web/static/css/admin.css` has rules for `.admin-sidebar-header`, `.admin-category-list`, `.admin-category-name`, `.admin-category-badge` (lines 3-7).
- `the_one/interfaces/web/static/css/components.css` has `.section-nav` + `.section-nav-header` + `.section-nav-item` rules (canonical, from F5 leg 01).
- `the_one/interfaces/web/static/index.html` loads `static/js/areas/studio/section-nav.js` at line 38.
- `tests/browser/test_flow_keyboard.py:137-160` asserts `.admin-category-item` keyboard activation, `role="listbox"` on the container (line 145), `role="option"` on the items (line 148), `tabindex="0"` on the focused item (line 149), and `aria-selected="true"` on the activated item (line 160).
- `tests/browser/test_flow_hash_routing.py:23-55` and `:205-245` assert "General Settings" as the default admin landing title.
- `tests/browser/test_flow_provider_setup.py:32` uses `.admin-category-item` to navigate to LLM Providers from chat.
- F5 baseline: `pytest tests/` ≥ 407 + `pytest -m browser tests/browser/` ≥ 172 passing on `main`.

## Outputs

What exists after this leg completes:

- **NEW** `the_one/interfaces/web/static/js/areas/layout/section-nav.js` — generic `App.layout.renderSectionNav(container, items, active, {onSelect, header, ariaLabel})` + `App.layout.updateActiveSection(container, active)` helpers. Items are passed in (no hardcoded `SECTIONS` array). Header text is passed in (no hardcoded "Studio").
- **NEW** `the_one/interfaces/web/static/js/areas/admin/system-page.js` — `App.admin.renderSystemPage(container)` renders the combined System page: Environment section (paths/server/concourse), Appearance section (theme toggle), Encryption section (rotate flow). Absorbs current `renderGeneralPanel`/`fetchSettings`/`renderSystemPanel` logic verbatim where possible.
- **MODIFIED** `the_one/interfaces/web/static/js/areas/admin.js`:
    - `categories` array drops `general`; remaining items: `[{id: 'system', label: 'System'}, {id: 'providers', label: 'LLM Providers'}]`. `active: true` field + "Soon" badge logic dropped (no current consumer).
    - `currentCategory` default changes from `'general'` to `'system'`.
    - `serializeState()`: `validIds` becomes `['system', 'providers']`; returns `'system'` when `_currentCategory` is null/missing (drives the `#admin` → `#admin/system` free redirect via the F3 router).
    - `hydrateState(sub)`: `'general'` (legacy) maps to `'system'`; unknown/null falls through to leaving `_currentCategory` unchanged from default.
    - `renderCategoryList()` is replaced by a single `App.layout.renderSectionNav(sidebar, [...], currentCategory, {onSelect: setCategory, header: 'Settings', ariaLabel: 'Settings sections'})` call at init-time + `App.layout.updateActiveSection(sidebar, currentCategory)` calls inside the (renamed) `setCategory` and `_setCategory` paths.
    - `renderContent()`: routes `'system'` → `App.admin.renderSystemPage(contentEl)`; routes `'providers'` → existing `renderProvidersPanel()` (unchanged this leg). Removes `renderGeneralPanel`, `fetchSettings`, `renderSystemPanel`, `settingSections`, `fieldLabels`, `settingRow` from admin.js (moved to system-page.js).
    - `_refresh()` (the `activate()` callback): branch on `'system'` instead of `'general'`; call the system-page sub-module's refetch entry point.
- **MODIFIED** `the_one/interfaces/web/static/js/areas/studio.js` and `static/js/areas/studio/*.js`: any reference to `App.studio.renderSectionNav` / `App.studio.updateActiveSection` updates to `App.layout.renderSectionNav` / `App.layout.updateActiveSection` AND passes the items array + "Studio" header explicitly.
- **DELETED** `the_one/interfaces/web/static/js/areas/studio/section-nav.js` (moved).
- **MODIFIED** `the_one/interfaces/web/static/index.html`: replace the `<script src="/static/js/areas/studio/section-nav.js">` line with `<script src="/static/js/areas/layout/section-nav.js">` placed BEFORE both `studio.js` and `admin.js`. Add `<script src="/static/js/areas/admin/system-page.js">` BEFORE `admin.js`.
- **MODIFIED** `the_one/interfaces/web/static/css/admin.css`: delete the `.admin-sidebar-header`, `.admin-category-list`, `.admin-category-name`, `.admin-category-badge` rules (lines 3-7). The `.admin-category-item` rule (if any) is implicit in `.section-nav-item` (verified — there's no `.admin-category-item` rule in admin.css; the styling came from composing with `.list-item`). Net `admin.css` LOC delta this leg: −5 to −7.
- **NEW** `tests/browser/test_flow_admin_navigation.py` — new admin-specific navigation tests covering section-nav keyboard + click; legacy redirect; free `#admin` → `#admin/system` redirect.
- **MODIFIED** `tests/browser/test_flow_keyboard.py:137-160` — selectors update from `.admin-category-item` to `.section-nav-item`; container role assertion updates from `role="listbox"` to `role="group"` (or removes it); item role assertion (`role="option"`) removes (helper does not set per-item role); active-item assertion changes from `aria-selected="true"` to `aria-current="page"`; `tabindex="0"` on active item assertion preserved (still applies via roving tabindex contract); activation flow preserved.
- **MODIFIED** `tests/browser/test_flow_hash_routing.py` — admin tests update default landing assertion from "General Settings" to "System"; click sequence + replaceState assertions preserved.
- **MODIFIED** `tests/browser/test_flow_provider_setup.py:32` — selector update from `.admin-category-item` to `.section-nav-item`; `has_text="LLM Providers"` filter preserved.
- **STATE**: `the_one/interfaces/web/static/js/areas/admin.js` shrinks from 1254 LOC to ≤ 1100 LOC (system-page extraction is ~110 LOC out; net delta also includes section-nav consumption replacing `renderCategoryList`). `admin.css` shrinks from 134 LOC to ≤ 128 LOC (small, but real). All baseline tests still pass.

## Acceptance Criteria

- [ ] `App.layout.renderSectionNav(container, items, active, {onSelect, header, ariaLabel})` exists at `static/js/areas/layout/section-nav.js`; `App.layout.updateActiveSection(container, active)` exists at the same module. The helper accepts an `items` array of `{id, label}` objects and a `header` string parameter (no hardcoded values).
- [ ] `App.studio.renderSectionNav` and `App.studio.updateActiveSection` no longer exist on the `App.studio` namespace (`grep -rn 'App.studio.renderSectionNav\|App.studio.updateActiveSection' static/js/` returns 0 matches outside the deleted file).
- [ ] `static/js/areas/studio/section-nav.js` file no longer exists (`ls static/js/areas/studio/section-nav.js` errors).
- [ ] Studio still renders its sidebar correctly: navigate to `#studio`, sidebar shows the "Studio" header + three buttons (Agents/Knowledge/Tools); keyboard navigation (Tab in, Up/Down arrows, Enter/Space activates) works as before.
- [ ] Admin sidebar renders via `App.layout.renderSectionNav`: navigate to `#admin`, sidebar shows the "Settings" header + two buttons (System, LLM Providers); keyboard navigation works.
- [ ] Admin's `categories` array contains exactly two items: `{id: 'system', label: 'System'}` and `{id: 'providers', label: 'LLM Providers'}`. The `active` flag and "Soon" badge logic are removed.
- [ ] `#admin` redirects to `#admin/system` (the F3 router's serialize-after-hydrate path performs the redirect; no new redirect logic in admin.js).
- [ ] `#admin/general` defensively redirects to `#admin/system` (legacy URL support); browser test confirms.
- [ ] `#admin/system` shows the combined System page: a top section labeled "Environment" with the read-only paths/server/concourse rows (existing render), then "Appearance" with the theme toggle, then "Encryption" with the rotate flow. The `.admin-title` text is "System".
- [ ] `#admin/providers` continues to render the existing provider list unchanged (no leg 01 work touches the providers panel).
- [ ] `App.admin.renderSystemPage(contentEl)` exists at `static/js/areas/admin/system-page.js` and is the sole entry-point for rendering the System page. The function refetches settings on every call (matches existing `fetchSettings` behavior); the existing 3-section layout from `settingSections` (Paths, Server, Concourse CI) renders inside the Environment section.
- [ ] Existing theme-toggle behavior preserved: clicking light/dark/auto updates the theme; `App.theme.renderToggle` consumed unchanged.
- [ ] Existing encryption-rotate behavior preserved: first click arms confirmation (button text "Click again to confirm rotation"), 4-second revert timer, second click POSTs to `/api/encryption/rotate`, success/error flash messages.
- [ ] `admin.css` no longer contains `.admin-sidebar-header`, `.admin-category-list`, `.admin-category-name`, `.admin-category-badge` rules.
- [ ] `index.html` script load order: `layout/section-nav.js` loads BEFORE both `areas/studio.js` and `areas/admin.js`; `areas/admin/system-page.js` loads BEFORE `areas/admin.js`.
- [ ] `tests/browser/test_flow_admin_navigation.py` exists and covers: (a) Tab into section nav focuses the active item; (b) Up/Down arrow moves focus + Enter activates; (c) refresh on `#admin/system` returns to System; (d) refresh on `#admin/providers` returns to LLM Providers; (e) `#admin` redirects to `#admin/system` (verify via `location.hash` after page load); (f) `#admin/general` redirects to `#admin/system`.
- [ ] `tests/browser/test_flow_keyboard.py:137-160` updated: `.admin-category-item` → `.section-nav-item`; `.admin-category-list` role assertion changes from `listbox` to `group` (or assertion removed); per-item `role="option"` assertion removed (helper does not set it); active-item assertion changes from `aria-selected="true"` to `aria-current="page"`; `tabindex="0"` on active item still asserted; test still passes.
- [ ] `tests/browser/test_flow_hash_routing.py` admin assertions updated: line 36 + line 217 expect `"System"` instead of `"General Settings"`; the click-Providers + refresh sequence still asserts `"LLM Providers"`; the cross-area + replaceState history-length test (lines 205-245) still passes (clicks now go to Providers and System; final length unchanged at baseline+1).
- [ ] `tests/browser/test_flow_provider_setup.py:32` updated from `.admin-category-item` to `.section-nav-item`; `has_text="LLM Providers"` filter unchanged; test still passes (the Cancel selector at line 57 references `.admin-pf-cancel` which stays valid for this leg — leg 03 territory).
- [ ] No edits to `agents.md` in this leg (deferred to leg 05 HAT per F6 flight spec).
- [ ] Baseline test counts maintained: `pytest tests/` passes ≥ 407; `pytest -m browser tests/browser/` passes ≥ 172 (new test_flow_admin_navigation.py adds 6 cases; net browser count ≥ 178).
- [ ] No new pyright/ruff errors introduced.
- [ ] `flight-log.md` updated with a `### 01-system-merge-and-section-nav-lift` entry under Leg Progress, summarizing changes made and noting the leg status as `landed` (NOT committed yet — commit deferred until end of flight per `/agentic-workflow` defer-commit policy).
- [ ] Leg status in this file's header updates from `planning` → `in-flight` → `landed` (don't commit).

## Verification Steps

How to confirm each criterion is met:

- **Helper namespace**: `grep -rn "App.layout.renderSectionNav\|App.layout.updateActiveSection" static/js/ tests/browser/` — returns the helper definition + studio + admin call-sites; `grep -rn "App.studio.renderSectionNav\|App.studio.updateActiveSection" static/js/ tests/browser/` — returns 0 matches.
- **File move**: `ls static/js/areas/layout/section-nav.js` succeeds; `ls static/js/areas/studio/section-nav.js` errors.
- **Studio still works**: navigate to `#studio`, click each section button, refresh on each URL — all section-nav F5 tests pass.
- **Admin sidebar**: navigate to `#admin`, observe two buttons; click each; URL updates; refresh works.
- **Default redirect**: navigate to `#admin` without a sub; observe URL becomes `#admin/system` after the F3 router's replaceState fires.
- **Legacy redirect**: navigate to `#admin/general`; observe URL becomes `#admin/system` after `hydrateState` defensively maps it.
- **Combined System page**: navigate to `#admin/system`; observe Environment + Appearance + Encryption sections in that order.
- **CSS cleanup**: `grep -n 'admin-sidebar-header\|admin-category-list\|admin-category-name\|admin-category-badge' static/css/admin.css` — returns 0 matches.
- **Index.html order**: `grep -n '<script' static/index.html` — verify `layout/section-nav.js` precedes both `areas/studio.js` and `areas/admin.js`; `areas/admin/system-page.js` precedes `areas/admin.js`.
- **Tests**: `pytest tests/ -m 'not browser'` (full suite minus browser markers) succeeds; `pytest -m browser tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_hash_routing.py tests/browser/test_flow_keyboard.py tests/browser/test_flow_studio_navigation.py` succeeds; `pytest -m browser tests/browser/` (full browser suite) succeeds with count ≥ 178.

## Implementation Guidance

### Step 1: Lift the section-nav helper

Create `static/js/areas/layout/section-nav.js` with the new generic API. Copy from `studio/section-nav.js` and rework:

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.layout = window.App.layout || {};

  // Generic sidebar section navigation primitive.
  //
  // Renders a header + N vertical buttons (one per item). The active button has
  // aria-current="page" and tabindex="0"; the others have tabindex="-1"
  // (roving tabindex). Up/Down arrows move focus, Home/End jump to first/last,
  // Enter/Space (or click) activates via onSelect.
  //
  // The helper does NOT mutate URL state — that's the caller's job
  // (single _writeUrl call site discipline).
  // Helper contract:
  //   - container: element to render into; helper sets its className + role
  //   - items: required array of {id, label} objects
  //   - active: id of the active item (or null on first render)
  //   - options.onSelect: callback (id) => void
  //   - options.header: required string — the section-nav header text
  //   - options.ariaLabel: required string — the container's accessible name
  // Caller contract: single-mount-per-container. The helper attaches a
  // keydown listener to `container`; calling renderSectionNav twice on the
  // same container would accumulate listeners. Use updateActiveSection for
  // active-state changes; only call renderSectionNav once at init.
  function renderSectionNav(container, items, active, options) {
    options = options || {};
    var onSelect = options.onSelect || function () {};
    var headerText = options.header || '';
    var ariaLabel = options.ariaLabel || '';

    container.innerHTML = '';
    container.className = 'section-nav';
    container.setAttribute('role', 'group');
    if (ariaLabel) container.setAttribute('aria-label', ariaLabel);
    // Defensive: warn if no aria-label provided. The container's role="group"
    // requires an accessible name (WAI-ARIA spec); silent-omit would regress
    // a11y vs. the F5 helper which hardcoded a label.
    if (!ariaLabel && console && console.warn) {
      console.warn('App.layout.renderSectionNav: ariaLabel not provided; container has no accessible name.');
    }

    if (headerText) {
      var header = document.createElement('div');
      header.className = 'section-nav-header';
      header.textContent = headerText;
      container.appendChild(header);
    }

    var buttons = [];
    for (var i = 0; i < items.length; i++) {
      (function (item) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'section-nav-item';
        btn.dataset.section = item.id;
        btn.textContent = item.label;
        var isActive = item.id === active;
        if (isActive) {
          btn.setAttribute('aria-current', 'page');
          btn.setAttribute('tabindex', '0');
        } else {
          btn.setAttribute('tabindex', '-1');
        }
        btn.addEventListener('click', function () { onSelect(item.id); });
        buttons.push(btn);
        container.appendChild(btn);
      })(items[i]);
    }

    container.addEventListener('keydown', function (e) {
      var current = document.activeElement;
      var idx = buttons.indexOf(current);
      if (idx === -1) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        buttons[(idx + 1) % buttons.length].focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        buttons[(idx - 1 + buttons.length) % buttons.length].focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        buttons[0].focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        buttons[buttons.length - 1].focus();
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        var section = current.dataset.section;
        if (section) onSelect(section);
      }
    });
  }

  function updateActiveSection(container, active) {
    var buttons = container.querySelectorAll('.section-nav-item');
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var isActive = btn.dataset.section === active;
      if (isActive) {
        btn.setAttribute('aria-current', 'page');
        btn.setAttribute('tabindex', '0');
      } else {
        btn.removeAttribute('aria-current');
        btn.setAttribute('tabindex', '-1');
      }
    }
  }

  window.App.layout.renderSectionNav = renderSectionNav;
  window.App.layout.updateActiveSection = updateActiveSection;
})();
```

### Step 2: Update the studio call-site

Find the existing `App.studio.renderSectionNav(...)` and `App.studio.updateActiveSection(...)` call sites in `static/js/areas/studio.js`. Update each:

- **Old**: `App.studio.renderSectionNav(container, active, {onSelect: ...})`
- **New**: `App.layout.renderSectionNav(container, [{id: 'agents', label: 'Agents'}, {id: 'knowledge', label: 'Knowledge'}, {id: 'tools', label: 'Tools'}], active, {onSelect: ..., header: 'Studio', ariaLabel: 'Studio sections'})`

- **Old**: `App.studio.updateActiveSection(container, active)`
- **New**: `App.layout.updateActiveSection(container, active)`

There may be only one render call (at init time) and one update call (in setActiveSection). Verify with grep.

### Step 3: Delete the old file

`rm static/js/areas/studio/section-nav.js`.

### Step 4: Update index.html script tags

Open `static/index.html`. Apply two edits:

1. **Move and rename the section-nav script tag**. Delete the existing line 38 (`<script src="/static/js/areas/studio/section-nav.js"></script>`). Insert a new tag for the lifted helper at line 32 (the line directly after `<script src="/static/js/tabs.js"></script>` and before `<script src="/static/js/areas/chat/welcome.js"></script>`):
   ```html
   <script src="/static/js/areas/layout/section-nav.js"></script>
   ```
   This places the helper before BOTH studio.js (line 45) and admin.js (line 46), satisfying the load-order requirement for both consumers.

2. **Add the admin sub-module script tag**. Insert a new line directly above `<script src="/static/js/areas/admin.js"></script>` (currently line 46 but will be line 46 after edit 1's insertion makes it line 47):
   ```html
   <script src="/static/js/areas/admin/system-page.js"></script>
   ```

### Step 5: Create the admin/system-page.js sub-module

`mkdir -p static/js/areas/admin` (create the directory).

Create `static/js/areas/admin/system-page.js`:

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Combined System page — Environment (read-only env-var-derived rows) +
  // Appearance (theme toggle) + Encryption (rotate flow). Replaces the
  // previously-separate General + System pages (F6 leg 01).

  var SETTING_SECTIONS = [
    { title: 'Paths', fields: ['data_dir', 'workspace_dir'] },
    { title: 'Server', fields: ['host', 'port'] },
    { title: 'Concourse CI', fields: ['concourse_target', 'concourse_pipeline'] }
  ];

  var FIELD_LABELS = {
    data_dir: 'Data Directory',
    workspace_dir: 'Workspace Directory',
    host: 'Host',
    port: 'Port',
    concourse_target: 'Target',
    concourse_pipeline: 'Pipeline'
  };

  var rotateConfirmTimer = null;

  function renderSystemPage(container) {
    var escapeHtml = window.App.escapeHtml;
    container.innerHTML =
      '<div class="admin-header">' +
        '<span class="admin-title">System</span>' +
      '</div>' +
      '<div class="admin-form">' +
        '<div class="admin-system-section">' +
          '<div class="section-title admin-section-title">Environment</div>' +
          '<div class="admin-note">' +
            'Environment settings are configured via environment variables. ' +
            'Restart the server after changing values.' +
          '</div>' +
          '<div class="admin-environment-rows"><div class="admin-loading">Loading settings…</div></div>' +
        '</div>' +
        '<div class="admin-system-section">' +
          '<div class="section-title admin-section-title" id="admin-appearance-heading">Appearance</div>' +
          '<p class="admin-system-text">' +
            'Choose a theme. Auto follows your operating system preference.' +
          '</p>' +
          '<div class="admin-theme-toggle" id="admin-theme-toggle-mount" aria-labelledby="admin-appearance-heading"></div>' +
        '</div>' +
        '<div class="admin-system-section">' +
          '<div class="section-title admin-section-title">Encryption</div>' +
          '<p class="admin-system-text">' +
            'API keys for LLM providers are encrypted at rest. ' +
            'You can rotate the encryption key to re-encrypt all stored credentials with a new key.' +
          '</p>' +
          '<div class="admin-system-warning" role="note">' +
            'Rotating the encryption key re-encrypts all stored API credentials with a new key. This is irreversible.' +
          '</div>' +
          '<button class="admin-system-btn" type="button">Rotate Encryption Key</button>' +
          '<div class="admin-system-flash" aria-live="polite"></div>' +
        '</div>' +
      '</div>';

    fetchSettings(container);
    mountThemeToggle(container);
    wireEncryptionRotate(container);
  }

  function fetchSettings(container) {
    fetch('/api/settings')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var rowsEl = container.querySelector('.admin-environment-rows');
        if (!rowsEl) return;
        var html = '';
        for (var s = 0; s < SETTING_SECTIONS.length; s++) {
          var section = SETTING_SECTIONS[s];
          html += '<div class="admin-environment-subsection">';
          html += '<div class="admin-environment-subtitle">' + window.App.escapeHtml(section.title) + '</div>';
          for (var f = 0; f < section.fields.length; f++) {
            var field = section.fields[f];
            var label = FIELD_LABELS[field] || field;
            var value = data[field];
            var envVar = 'THE_ONE_' + field.toUpperCase();
            html += settingRow(label, value, envVar);
          }
          html += '</div>';
        }
        rowsEl.innerHTML = html;
      })
      .catch(function () { /* loading message stays */ });
  }

  function settingRow(label, value, envVar) {
    var escapeHtml = window.App.escapeHtml;
    var displayValue;
    if (value === null || value === undefined || value === '') {
      displayValue = '<span class="admin-field-not-set">not set</span>';
    } else {
      displayValue = escapeHtml(String(value));
    }
    return '<div class="admin-field-row">' +
      '<div class="admin-field-label">' + escapeHtml(label) + '</div>' +
      '<div class="admin-field-value">' + displayValue + '</div>' +
      '<div class="admin-field-env">' + escapeHtml(envVar) + '</div>' +
    '</div>';
  }

  function mountThemeToggle(container) {
    var themeToggleEl = container.querySelector('#admin-theme-toggle-mount');
    if (window.App && window.App.theme && window.App.theme.renderToggle) {
      window.App.theme.renderToggle(themeToggleEl, { labelledBy: 'admin-appearance-heading' });
    }
  }

  function wireEncryptionRotate(container) {
    var rotateBtn = container.querySelector('.admin-system-btn');
    var flashEl = container.querySelector('.admin-system-flash');
    rotateBtn.addEventListener('click', function () {
      if (rotateBtn.classList.contains('admin-system-btn-confirm')) {
        rotateBtn.disabled = true;
        rotateBtn.textContent = 'Rotating…';
        fetch('/api/encryption/rotate', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Rotation failed'); });
            return r.json();
          })
          .then(function () {
            rotateBtn.disabled = false;
            rotateBtn.classList.remove('admin-system-btn-confirm');
            rotateBtn.textContent = 'Rotate Encryption Key';
            if (rotateConfirmTimer) { clearTimeout(rotateConfirmTimer); rotateConfirmTimer = null; }
            flashEl.textContent = 'Encryption key rotated successfully.';
            flashEl.className = 'admin-system-flash success';
            setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 3000);
          })
          .catch(function (err) {
            rotateBtn.disabled = false;
            rotateBtn.classList.remove('admin-system-btn-confirm');
            rotateBtn.textContent = 'Rotate Encryption Key';
            if (rotateConfirmTimer) { clearTimeout(rotateConfirmTimer); rotateConfirmTimer = null; }
            flashEl.textContent = 'Error: ' + err.message;
            flashEl.className = 'admin-system-flash error';
            setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 4000);
          });
        return;
      }
      rotateBtn.classList.add('admin-system-btn-confirm');
      rotateBtn.textContent = 'Click again to confirm rotation';
      if (rotateConfirmTimer) clearTimeout(rotateConfirmTimer);
      rotateConfirmTimer = setTimeout(function () {
        rotateBtn.classList.remove('admin-system-btn-confirm');
        rotateBtn.textContent = 'Rotate Encryption Key';
      }, 4000);
    });
  }

  window.App.admin.renderSystemPage = renderSystemPage;
})();
```

Note: the new module renders Environment as a top-level `.admin-system-section` (matching the other two sections' visual treatment) with subsection labels (Paths / Server / Concourse CI) inside. Keep the existing `.admin-section-title`, `.admin-section`, `.admin-field-row`, `.admin-field-label`, `.admin-field-value`, `.admin-field-env`, `.admin-field-not-set`, `.admin-note`, `.admin-system-section`, `.admin-system-text`, `.admin-system-warning`, `.admin-system-btn`, `.admin-system-flash`, `.admin-theme-toggle`, `.admin-loading`, `.admin-form`, `.admin-header`, `.admin-title`, `.admin-section-title` rules in `admin.css`. Add new `.admin-environment-subsection` and `.admin-environment-subtitle` styles only if the existing rules don't render the subsection labels acceptably (visual review during impl). Keep these in `admin.css` (per-area).

### Step 6: Update admin.js

Open `static/js/areas/admin.js`. Apply these changes:

1. Replace the `categories` array (lines 19-23) with:
   ```js
   var categories = [
     { id: 'system', label: 'System' },
     { id: 'providers', label: 'LLM Providers' }
   ];
   ```
   Drop the `active: true` field (no consumer); drop the "Soon" badge logic in renderCategoryList.

2. Change `var currentCategory = 'general';` to `var currentCategory = 'system';`.

3. In `serializeState` (line 8-10), keep the same shape (returns `currentCategory` or `null`); the redirect happens because `'system'` is a valid sub. Change validIds in `hydrateState` from `['general', 'providers', 'system']` to `['system', 'providers']` AND add a defensive `if (sub === 'general') sub = 'system';` line at the top of hydrateState (legacy redirect).

4. Replace the `renderCategoryList` function (lines 102-141) with a single call to `App.layout.renderSectionNav` at init time + `App.layout.updateActiveSection` calls inside `setCategory` and `_setCategory`. Pseudocode:

   ```js
   function setCategory(catId) {
     currentCategory = catId;
     providerFormMode = null;
     editingProvider = null;
     if (window.App && window.App.router) App.router.replaceSub(currentCategory);
     App.layout.updateActiveSection(categoryListEl, currentCategory);
     renderContent();
   }
   ```

   Replace the sidebar.innerHTML init block (lines 86-94) with:
   ```js
   sidebar.innerHTML = '';
   App.layout.renderSectionNav(sidebar, categories, currentCategory, {
     onSelect: setCategory,
     header: 'Settings',
     ariaLabel: 'Settings sections'
   });
   categoryListEl = sidebar; // the helper renders directly into the container
   ```

   The `categoryListEl` reference is kept to avoid touching every other call site that uses it; it now points at the same container the helper rendered into.

5. Replace `renderContent` (lines 143-157) so the `'system'` branch calls `App.admin.renderSystemPage(contentEl)`. Drop the `'general'` branch entirely. Drop the `renderPlaceholder` fallback path (no unknown-category remains after the merge — `hydrateState` has already filtered).

6. Delete from admin.js the now-extracted code: `settingSections`, `fieldLabels`, `renderGeneralPanel`, `fetchSettings`, `settingRow`, `renderSystemPanel`, `rotateConfirmTimer`, `renderPlaceholder`. Net delete: ~120 LOC.

7. Update `_refresh()` (lines 1219-1225): the `'general'` branch goes away; the `'system'` branch re-calls `App.admin.renderSystemPage(contentEl)` (full re-render). **Behavior change vs. today**: today General's `_refresh` calls `fetchSettings()` only (surgical refresh of read-only rows); System's `_refresh` is a no-op (the panel never gets re-fetched). After this leg, switching to admin from another area triggers a full System rebuild, which (a) re-fetches `/api/settings`, (b) re-mounts the theme toggle (safe via `theme.js`'s `_themeListenerCleanup` contract at theme.js:105-108), and (c) wipes any in-flight encryption-rotate confirm-arming state. **Acceptable** — settings can change out-of-band (env var edits + server restart), so refetching on activate is more correct than the current per-area inconsistency. Document this change in the flight log under "Decisions."

8. Update `_setCategory` (lines 1230-1238) to call `App.layout.updateActiveSection(categoryListEl, currentCategory)` instead of `renderCategoryList()`. **Preserve the existing short-circuit semantics** — if `currentCategory === sub`, the function returns early without re-rendering content. The init-time `renderContent()` call at admin.js:1244 handles initial render after `init()` runs; `_setCategory` only fires on cross-area re-entry with a sub. Inside the if-block, after the `currentCategory = sub` assignment, both `App.layout.updateActiveSection(categoryListEl, currentCategory)` AND `renderContent()` must be called (matching the current pattern where `renderCategoryList()` + `renderContent()` are both called).

9. Confirm `fetchProviderTypes()` stays at admin's `init()` bottom block (admin.js:1242). It is consumed by the providers panel — even though the System page is now the default, navigating to Providers needs `PROVIDER_TYPES` to be ready. Eager fetch at init is the existing behavior; F6 leg 01 preserves it. (F5 debrief Action Item #2 audit closure: no other legacy auto-select in admin's init bottom block was found; renderCategoryList replacement is the only change to the init sequence.)

### Step 7: Strip admin.css

Delete lines 3-7 of `static/css/admin.css` (the admin-sidebar-header / admin-category-list / admin-category-name / admin-category-badge rules). Verify with `grep`.

If the new `.admin-environment-subsection` / `.admin-environment-subtitle` styles are needed (depends on visual review during impl), add them to `admin.css` per-area.

### Step 8: Tests

Create `tests/browser/test_flow_admin_navigation.py`:

```python
"""Admin navigation flow tests for F6 leg 01.

Covers:
- Section nav keyboard a11y (Tab in, Up/Down arrows, Home/End, Enter/Space activation)
- Section nav click navigation
- Refresh-preserves-section
- #admin -> #admin/system free redirect (via F3 router serialize-after-hydrate)
- #admin/general -> #admin/system legacy redirect (defensive in hydrateState)
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_redirect_root_to_system(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin")
    expect(page.locator(".admin-title")).to_have_text("System", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/system"


@pytest.mark.browser
def test_admin_legacy_general_redirects_to_system(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/general")
    expect(page.locator(".admin-title")).to_have_text("System", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/system"


@pytest.mark.browser
def test_admin_section_nav_renders_two_sections(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    nav = page.locator(".section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = nav.locator(".section-nav-item")
    expect(items).to_have_count(2)
    expect(items.nth(0)).to_have_text("System")
    expect(items.nth(1)).to_have_text("LLM Providers")


@pytest.mark.browser
def test_admin_section_nav_click_changes_url(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    expect(page.locator(".admin-title")).to_have_text("System", timeout=5000)
    page.locator(".section-nav-item", has_text="LLM Providers").click()
    expect(page.locator(".admin-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_admin_refresh_preserves_section(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".admin-title")).to_have_text("LLM Providers", timeout=8000)
    page.reload()
    expect(page.locator(".admin-title")).to_have_text("LLM Providers", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_admin_section_nav_keyboard(app_clean: str, page: Page) -> None:
    """Tab into nav, Down arrow moves focus, Enter activates."""
    page.goto(f"{app_clean}#admin/system")
    expect(page.locator(".admin-title")).to_have_text("System", timeout=5000)

    # Tab focuses the active item (System).
    active_item = page.locator('.section-nav-item[aria-current="page"]')
    active_item.focus()
    expect(active_item).to_be_focused()

    # Down arrow moves focus to LLM Providers.
    page.keyboard.press("ArrowDown")
    providers_item = page.locator(".section-nav-item", has_text="LLM Providers")
    expect(providers_item).to_be_focused()

    # Enter activates.
    page.keyboard.press("Enter")
    expect(page.locator(".admin-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"
```

Update `tests/browser/test_flow_keyboard.py:137-160` (the admin section). Apply the following selector + assertion changes:
- `.admin-category-item` → `.section-nav-item` (all occurrences in lines 141, 153, 156)
- `.admin-category-list` → `.section-nav` (line 145 selector); change `to_have_attribute("role", "listbox")` → `to_have_attribute("role", "group")` (the new helper sets `role="group"`, not `role="listbox"`)
- Line 148 currently asserts `to_have_attribute("role", "option")` on the item — **REMOVE** this assertion (the new helper does not set per-item role; native `<button>` semantics suffice)
- Line 149 asserts `tabindex="0"` on the focused/active item — **PRESERVE** (still applies via roving tabindex contract)
- Line 160 currently asserts `aria-selected="true"` on the activated item — change to `aria-current="page"` (the new helper uses `aria-current` for the activation marker; `aria-selected` is not set)

Update `tests/browser/test_flow_provider_setup.py:32` from:
```python
page.locator(".admin-category-item", has_text="LLM Providers").click()
```
to:
```python
page.locator(".section-nav-item", has_text="LLM Providers").click()
```
The `has_text` filter is preserved; only the class name changes.

Update `tests/browser/test_flow_hash_routing.py`:
- Line 36: `to_have_text("General Settings")` → `to_have_text("System")`
- Line 217: same change
- The History-length test at lines 205-245: review carefully. The test clicks Providers (replaceState) then System (replaceState). After leg 01, both are real categories, so the click sequence still produces 2 replaceState events. The final assertion (length unchanged at baseline+1) still holds.
- Line 239 already expects "System" — matches new behavior.
- Verify both default-page assertions match the new "System" text.

### Step 9: Verify

Run the full suite:

```bash
docker exec the-one pytest tests/ -m 'not browser' --timeout=120
docker exec the-one pytest tests/browser/ -m browser --timeout=120
```

Both must pass with no regressions. New admin-navigation tests bring the browser count to ≥ 178.

### Step 10: Update flight log

Append to `flight-log.md` under `## Leg Progress`:

```markdown
### 01-system-merge-and-section-nav-lift
**Status**: landed
**Started**: <ISO timestamp>
**Completed**: <ISO timestamp>

#### Changes Made
- Lifted `App.studio.renderSectionNav` → `App.layout.renderSectionNav` (file moved from `areas/studio/section-nav.js` to `areas/layout/section-nav.js`); helper now accepts `items` array + `header` text as parameters.
- Studio call-site updated; admin's bespoke `renderCategoryList` replaced with `App.layout.renderSectionNav` consumption.
- Combined General + System into single System page rendered by NEW `App.admin.renderSystemPage` (sub-module at `areas/admin/system-page.js`).
- Three-section layout: Environment (paths/server/concourse subsections) + Appearance (theme toggle) + Encryption (rotate flow).
- Hash routing: `#admin` redirects to `#admin/system` (free via F3 router); `#admin/general` legacy redirect to `#admin/system` (defensive in hydrateState).
- Deleted `.admin-sidebar-header`, `.admin-category-list`, `.admin-category-name`, `.admin-category-badge` from `admin.css` (~5 LOC).
- 6 NEW browser tests in `test_flow_admin_navigation.py`; selector updates in `test_flow_keyboard.py` (`.admin-category-item` → `.section-nav-item`) and `test_flow_hash_routing.py` (default landing assertion "General Settings" → "System").
- Test counts: `pytest tests/` <count>; `pytest -m browser tests/browser/` <count> (target ≥ 178).

#### Notes
<runtime decisions, gotchas, deviations>
```

Set this file's status header from `planning` → `in-flight` at start of work, → `landed` at end. Do NOT commit — commit happens once after all autonomous legs finish (per `/agentic-workflow` defer-commit policy).

## Edge Cases

- **`#admin/general` from a saved bookmark**: hydrateState defensively maps to `'system'`; the F3 router replaceState upgrades the URL. Test: `test_admin_legacy_general_redirects_to_system`.
- **`#admin/<garbage>`**: existing hydrateState returns early without mutation when sub is not in validIds. After leg 01, `currentCategory` stays at the default `'system'`; serializeState then writes back `'system'` via F3 redirect. Behavior unchanged.
- **Tab-into-section-nav focuses the active item**: the helper's roving tabindex contract puts `tabindex="0"` only on the active item; Tab from outside lands on the active item. Verify in keyboard test.
- **Keyboard Enter on already-active item**: setCategory short-circuits if `currentCategory === sub`. Acceptable; the active item stays active, no DOM thrash.
- **Theme-toggle re-mount safety**: `theme.js:105-108` provides a `_themeListenerCleanup` contract; re-mounting via `App.theme.renderToggle` is safe (cleanup runs before new listeners attach). No system-page-side dedup needed.
- **Encryption rotate confirm timer state across page re-renders**: `rotateConfirmTimer` is module-scoped in system-page.js; if the user re-mounts the page mid-confirm-window (via cross-area navigation triggering `_refresh` → full re-render), the timer fires on the detached DOM. Defensive: `setTimeout` callback's `rotateBtn.classList.remove(...)` silently no-ops on detached elements — acceptable. The user simply has to re-arm the confirm flow; no data loss.
- **F3 router's serialize-after-hydrate** runs once on switchTo. The redirect `#admin` → `#admin/system` only fires on cross-area navigation, not on intra-admin sub-changes. Verify the test reaches the redirected URL via the cross-area path (page.goto), not via in-page navigation.
- **`_refresh()` full re-render of System on cross-area activate**: behavior change vs. today (today General refreshes only the read-only rows; System never refreshes). After this leg, every admin-area activation rebuilds the entire System page (including refetch of `/api/settings`, theme-toggle remount, encryption-rotate handler rewire). Acceptable — settings can change out-of-band, so this is more correct than the current inconsistency. Documented in flight log under "Decisions" at landing time.
- **`renderSectionNav` single-mount-per-container contract**: the helper attaches a `keydown` listener to `container` on each call; calling it twice on the same container would double-fire keyboard events. The leg's design ensures this doesn't happen — admin calls `renderSectionNav` exactly once at `init()` (subsequent active-state changes go through `updateActiveSection`). If a future feature needs re-mount, it must `container.replaceChildren()` and create a new container. Documented contract.
- **Visual change of Environment section vs. today's General page (intentional)**: today's General page renders three top-level `.admin-section` blocks (Paths / Server / Concourse CI), each with its own `.section-title` header. After this leg, the new System page renders ONE `.admin-system-section` "Environment" block containing three `.admin-environment-subsection` subsections (Paths / Server / Concourse CI) with `.admin-environment-subtitle` labels. The visual hierarchy shifts from "three separate sections" to "one Environment section with three subsections grouped under it." This is a deliberate design change to make the merger read as a coherent grouping, not just three transplanted subsections. Add minimal `.admin-environment-subsection` (top margin / spacing) and `.admin-environment-subtitle` (smaller, mono, uppercase per the codebase's section-label idiom — match `.admin-section-title` styling) rules in `admin.css` if visual review during implementation requires them.

## Files Affected

- `the_one/interfaces/web/static/js/areas/layout/section-nav.js` — NEW (lifted from `studio/section-nav.js`); generic API with items + header parameters.
- `the_one/interfaces/web/static/js/areas/studio/section-nav.js` — DELETED (moved).
- `the_one/interfaces/web/static/js/areas/admin/system-page.js` — NEW; renders combined Environment + Appearance + Encryption sections.
- `the_one/interfaces/web/static/js/areas/admin.js` — categories array shrinks to 2; `currentCategory` defaults to `'system'`; `renderCategoryList` replaced by `App.layout.renderSectionNav` consumption; `renderGeneralPanel`/`fetchSettings`/`settingRow`/`renderSystemPanel`/`renderPlaceholder` extracted to system-page.js; `_setCategory` and `_refresh` updated. Net delta: −120 to −140 LOC.
- `the_one/interfaces/web/static/js/areas/studio.js` and `static/js/areas/studio/*.js` — `App.studio.renderSectionNav` / `App.studio.updateActiveSection` references rename to `App.layout.*` AND pass items + header args.
- `the_one/interfaces/web/static/index.html` — script tag updates: `studio/section-nav.js` line removed; `layout/section-nav.js` added before both `studio.js` and `admin.js`; `admin/system-page.js` added before `admin.js`.
- `the_one/interfaces/web/static/css/admin.css` — `.admin-sidebar-header` / `.admin-category-list` / `.admin-category-name` / `.admin-category-badge` rules deleted (lines 3-7).
- `tests/browser/test_flow_admin_navigation.py` — NEW; 6 test cases covering keyboard, click, refresh, free redirect, legacy redirect.
- `tests/browser/test_flow_keyboard.py` — admin section selector + assertion updates (`.admin-category-item` → `.section-nav-item`; `.admin-category-list` `role="listbox"` → `role="group"` or removed; per-item `role="option"` removed; active-item `aria-selected="true"` → `aria-current="page"`; tabindex="0" on active item preserved).
- `tests/browser/test_flow_hash_routing.py` — default landing assertion text "General Settings" → "System" (lines 36 + 217); other assertions unchanged.
- `tests/browser/test_flow_provider_setup.py:32` — selector update from `.admin-category-item` to `.section-nav-item`; `has_text="LLM Providers"` filter preserved.
- `the_one/interfaces/web/api.py` — UNCHANGED.
- `missions/04-ui-maturity/flights/06-administration-alignment/flight-log.md` — updated with leg progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (commit deferred to flight end per `/agentic-workflow` defer-commit policy):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/` ≥ 407 + `pytest -m browser tests/browser/` ≥ 178)
- [ ] Update `flight-log.md` with leg progress entry under `### 01-system-merge-and-section-nav-lift`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] **Do NOT** check off this leg in `flight.md` yet (per `/agentic-workflow` defer-commit policy — happens after final flight review/commit)
- [ ] **Do NOT** commit (per `/agentic-workflow` defer-commit policy)
- [ ] Signal `[HANDOFF:review-needed]` only after all of the above are verified

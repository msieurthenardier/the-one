# Leg: 02-vocabulary-inventory

**Status**: landed
**Flight**: [Design Language — Glass + Control Panel](../flight.md)

## Objective

Populate the empty gallery scaffold from Leg 01 with live demos of every in-scope design-vocabulary primitive, organized as one section per axis (tokens, typography, buttons, fields, surfaces, status indicators, tabs, modal, markdown). The gallery is a **passive consumer** of canonical CSS classes — token or component changes in subsequent legs reflect automatically in the gallery without parallel edits. Lift the `.mcp-tools-checkbox-group` checkbox treatment from `studio.css` into a `.checkbox-primary` primitive in `components.css` (Flight 1 debrief Action Item #1) as part of the field-section setup. Establish the gallery's per-section module convention under a new `static/js/areas/admin/design-language/` subdirectory.

## Context

- Leg 2 of 6. Leg 01 landed the scaffold: `App.admin.renderDesignLanguagePage` renders a `<h1 class="page-title">Design Language</h1>` header + empty `<div id="design-language-sections" class="design-language-sections">` body container. This leg fills the body container.
- Flight Design Decision: per-section subdirectory at `static/js/areas/admin/design-language/`, one file per section, each exporting a `render(host)` function; container module iterates them.
- Flight Design Decision: topbar + app-picker popover + modal-dialog → rendered as **static miniatures** inside their gallery cells, never re-mounting real chrome. The modal section additionally provides one "Open modal" button that fires the real `App.confirmDialog` so the live behavior is verifiable.
- Flight Design Decision (deferred to Leg 02): `.telemetry-strip` vs `.section-title` relationship. **Resolved here**: Leg 02 uses the existing `.section-title` primitive for the gallery's section eyebrows (`// TOKENS`, `// TYPOGRAPHY`, etc.); Leg 05 introduces `.telemetry-strip` as a **sibling primitive** with its own gallery sample (different semantic role: status readout, not section header). They coexist.
- Flight Design Decision: `.checkbox-primary` extraction piggybacks; iOS-toggle (`.tool-enable-switch` at `admin.css:157-220`) stays out of scope as a distinct primitive. Both appear in the gallery: checkbox in the fields section, iOS-toggle in the surfaces section (so the design vocabulary distinguishes them).
- Narrow test gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` (broad pytest hangs on SQLite WAL anomaly).

## Inputs

- Leg 01 outputs in place: `App.admin.renderDesignLanguagePage` registered, dev-mode-gated category dispatches to it, empty body container exists
- `tokens.css:48-53, 144-149` — accent palette (violet `--accent`, recycled cyan `--accent-api`, glow/translucent variants)
- `fonts.css:33-52` — typography tokens (`--font-size-{display,h1,h2,h3,body-lg,body,body-sm,caption,tiny}`, `--font-weight-{regular,medium,semibold,bold}`, `--line-height-{tight,normal}`)
- `components.css` — every primitive sampled by the gallery (already canonicalized; lines cited in implementation guidance)
- `studio.css:171-209` — `.mcp-tools-checkbox-group input[type="checkbox"]` treatment to lift: comment header `:171-174` + 5 checkbox rules `:175-209` (focus-visible block's closing brace at `:209`; next rule `.area-studio .mcp-auth-required-notice` at `:210`). Wrapper layout rules at `:167-170` stay put. Comment is replaced with a one-line "see components.css .checkbox-primary" pointer.
- `studio.css` `mcp-tools-checkbox-group` is consumed at `mcps-tab.js:299` (one DOM-emission site); the lift updates the JS-side class composition AND the CSS-side rule location
- `admin.css:157-220` `.tool-enable-switch` iOS-toggle — sampled in gallery, code stays put
- `index.html` admin sub-module script-tag block — 9 new section-module `<script>` tags need to be added between `design-language-page.js` and `admin.js`
- `Makefile:80-93` `verify-serving` admin-sub-module loop — 9 new entries to add (matches Leg 01's pattern)

## Outputs

- `the_one/interfaces/web/static/js/areas/admin/design-language/` — NEW subdirectory, 9 section modules:
  - `tokens-section.js` — color swatches with hex labels, panel-radius samples, status-color swatches
  - `typography-section.js` — display/h1/h2/h3/body-lg/body/body-sm/caption/tiny ladder (sans + mono variants), `.section-title` eyebrow sample
  - `buttons-section.js` — `.btn-outlined-primary`, `.btn-filled-primary`, `.btn-muted-destructive` × sizes (default, `.btn-sm`, `.btn-lg`, `.btn-xl`) × states (default, disabled); hover/focus states captured by leaving them un-forced — operator hovers/focuses live in the gallery
  - `fields-section.js` — `.field-input`, `.field-textarea`, `.field-select`, `.field-info-icon`, and the new `.checkbox-primary` (and a labeled multi-select group sample so vibe legs can see the grouped form)
  - `surfaces-section.js` — `.entity-tile` single + grid, `.section-nav-item` default + active, `.list-item` default + active + `.confirm-delete`, static miniatures of `.app-topbar-title` and `.app-picker-button` (closed + open), `.tool-enable-switch` iOS-toggle sample (live, interactive — it's harmless)
  - `status-section.js` — `.test-result-{ok,fail,warning,pending}`, `.app-flash` (success + error, as static positioned-relative samples rather than fixed), `.action-blocked-message`, `.chip` + `.chip-remove`, `.empty-state`, `.empty-canvas` (boxed in a mini container so it doesn't blow out the layout)
  - `tabs-section.js` — 3-tab `tablist` sample wired through `App.tabs` so keyboard nav works
  - `modal-section.js` — static `.modal-dialog` preview (no overlay, no backdrop — just the dialog box) + ONE live "Open modal" `<button class="btn-outlined-primary">` that fires `App.confirmDialog({title, message, confirmLabel, onConfirm})` so the live behavior + dismissal is verifiable
  - `markdown-section.js` — sample code block rendered via `App.markdown.render('```js\n…\n```')` (the canonical helper at `markdown.js:6` already emits the full `<div class="markdown-code-wrap"><pre><code>…</code></pre><button class="markdown-copy-btn">…</button></div>` structure with the click-to-copy handler wired); the section is a passive consumer of `App.markdown.render`, not a parallel re-implementation
- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` — UPDATED to iterate a `SECTIONS` descriptor list (`[{slug, title, render}]`) and mount each section's body into its own labeled container. Section title rendered as `<div class="section-title">// <TITLE></div>` followed by `<div class="design-language-section-body" data-section="<slug>"></div>` which the section module's `render(host)` populates.
- `the_one/interfaces/web/static/css/components.css` — NEW `.checkbox-primary` primitive lifted from studio.css; positioned in the primitives grouping (near the other field primitives, after `.field-info-icon`)
- `the_one/interfaces/web/static/css/studio.css` — REMOVE the `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]` block (`:171-209` — comment header + 5 rules); keep the wrapper rules (`:167-170` `.mcp-tools-checkbox-group`, `.mcp-tool-toggle-label`, `.mcp-tool-toggle-name`, `.mcp-tool-toggle-hint`) which are layout, not primitive-treatment
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js:299` — update class composition so the checkbox carries `.checkbox-primary` (the parent `.mcp-tools-checkbox-group` already groups them; the primitive class lands on each `<input type="checkbox">`)
- `the_one/interfaces/web/static/css/admin.css` — small NEW rule block scoped to `.area-admin .design-language-sections` providing per-section spacing, sub-grid for tile/swatch layouts, and the gallery's own scroll/overflow behavior. Lightweight area-style addition consistent with existing area-scoped patterns in `admin.css`
- `the_one/interfaces/web/static/index.html` — 9 new `<script>` tags for the section modules, inserted between `design-language-page.js` and `admin.js`
- `Makefile` — `verify-serving` admin-sub-module shell-loop extended with the 9 new section modules

## Acceptance Criteria

- [ ] All 9 section modules exist under `static/js/areas/admin/design-language/` and each registers an `App.admin.designLanguage.<sectionSlug>Section.render(host)` function on the `App.admin.designLanguage` namespace (new sub-namespace introduced by this leg)
- [ ] `design-language-page.js` iterates a `SECTIONS` descriptor list in fixed order: tokens → typography → buttons → fields → surfaces → status → tabs → modal → markdown
- [ ] Each section in the gallery renders with a `<div class="section-title">// <TITLE></div>` eyebrow followed by the section body
- [ ] `.checkbox-primary` primitive exists in `components.css` and matches the visual treatment of the lifted studio.css block (14px square, 1.5px `--border-strong` border, `--surface` background, hover `--accent` border, checked `--accent` fill + `--fg-on-accent` checkmark, focus-visible 2px `--accent` outline)
- [ ] `studio.css` no longer carries `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]` rules (lines `:175-208`); the wrapper layout rules at `:167-171` remain
- [ ] `mcps-tab.js:299` composes the new `.checkbox-primary` class on the checkbox input — verified by inspecting the rendered MCP tab and confirming the checkbox renders identically to pre-leg state (same hex values, same hover/checked behavior)
- [ ] Gallery sections sample primitives via the **canonical class names** — no inline styles, no parallel CSS rules; verified by grep showing each section module emits only the existing class names (and the new `.checkbox-primary`)
- [ ] Topbar and app-picker popover in the surfaces section render as static miniatures inside the gallery cell — NOT by re-mounting the real chrome (no `position: fixed`, no event bindings tied to the real picker). Verified by visual inspection + grep that `renderTopBar` is not called by any section module
- [ ] The modal section renders a static `.modal-dialog` preview (no overlay backdrop) AND a working "Open modal" button that fires `App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` (canonical signature per `dialog.js:11, :82-83` — NOT `confirmLabel`) with a sample message — verified by clicking the button in dev mode, observing the live modal opens, and pressing Escape or Cancel to dismiss. (NOTE: overlay-click-to-dismiss is intentionally NOT supported per `dialog.js:203-211`; do not test it.)
- [ ] The tabs section is wired by calling `window.App.tabs(tablistEl, panelsEl, { initial, onChange })` — the canonical signature per `tabs.js:38` and matching the existing consumers `agent-editor.js:173`, `tools-grid.js:171`. There is NO `App.tabs.wire(...)` method. Keyboard navigation (arrow keys, Enter/Space) and `[role="tab"]`/`[role="tabpanel"]` ARIA wiring work — verified by tabbing into the gallery tablist and pressing arrow keys
- [ ] The markdown section renders via `App.markdown.render('```js\n…\n```')`, mounting the returned DocumentFragment into the section host. The copy button is wired by the helper itself (per `markdown.js:6, :753-790`) — verified by clicking the copy button and confirming the sample code lands in the clipboard
- [ ] `Makefile` `verify-serving` admin-sub-module loop includes all 9 new section modules and passes after `make rebuild`
- [ ] `App.admin.designLanguage` namespace is bootstrapped via the IIFE pattern (`window.App = window.App || {}; window.App.admin = window.App.admin || {}; window.App.admin.designLanguage = window.App.admin.designLanguage || {};`) — same convention as Leg 01's `App.admin.renderDesignLanguagePage`
- [ ] All existing tests pass on the narrow gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10`
- [ ] Flight log updated with leg progress entry; leg status set to `landed`

## Verification Steps

1. **Container rebuild + verify-serving**:
   ```bash
   make rebuild
   ```
   Expect `verify-serving` to confirm all admin sub-modules including the 9 new section modules return 200.

2. **Gallery renders all 9 sections** (dev mode):
   - Load `http://localhost:8484/#admin/design-language`
   - Scroll through the page; expect 9 section eyebrows (`// TOKENS`, `// TYPOGRAPHY`, …) with content beneath each
   - Each section shows the documented primitives without missing samples or rendering errors

3. **Checkbox primitive lift — no MCP regression**:
   - Load `http://localhost:8484/#studio` → select an agent → open MCPs tab → click into an MCP source's tools
   - Per-tool checkboxes render identically to pre-leg (14px square, violet check state on click, hover border tint)
   - Verify with DevTools that each checkbox carries `class="checkbox-primary"` (or composed with another class) and no fallback browser-default styling appears

4. **Gallery checkbox sample**:
   - In the fields section of the gallery, the `.checkbox-primary` sample renders the same as the MCP tab checkboxes
   - Clicking the sample checkbox toggles its state visually

5. **Modal trigger**:
   - In the modal section, click "Open modal"
   - The real `App.confirmDialog` opens with sample message
   - Pressing Escape OR clicking the Cancel button dismisses cleanly
   - (NOTE: clicking-outside is intentionally NOT supported per `dialog.js:203-211` — do NOT test it)

6. **Tabs keyboard nav**:
   - Tab into the tabs section's tablist
   - Press Arrow Right — focus moves to the next tab (manual activation: tab highlight moves, panel does NOT change until Enter/Space)
   - Press Enter — the focused tab activates and its panel becomes visible

7. **Markdown copy button**:
   - Hover the code block; the `.markdown-copy-btn` becomes visible (opacity transition)
   - Click it; the sample code is in the clipboard (paste elsewhere to confirm)

8. **Token-section live consumption**:
   - Open DevTools → Elements → modify `--accent` in `[data-theme="dark"]` to a test value (e.g., red)
   - The gallery's accent swatch changes color immediately (proves passive consumption — no caching, no parallel implementation)
   - Revert the DevTools edit

9. **Narrow test gate**:
   ```bash
   docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10
   ```
   Expect `56 passed` (Flight 1 baseline preserved).

## Implementation Guidance

### Step 1: Lift `.checkbox-primary` to `components.css`

In `the_one/interfaces/web/static/css/components.css`, add the new primitive near the form-field primitives (after the `.field-info-icon` rule block, around line 256, before the `=== Section Title` block):

```css
/* === Checkbox Primary (form checkbox primitive) ===
   Lifted from .area-studio .mcp-tools-checkbox-group input[type="checkbox"]
   (Mission 08 F1 L5 / F2 L2). Replaces the browser default with a styled
   14px square that picks up the brand accent on hover and check. Compose
   onto any `<input type="checkbox">` for the canonical multi-select
   checkbox treatment. Distinct from the iOS-toggle .tool-enable-switch
   primitive (admin.css) which expresses a single binary feature flip. */
.checkbox-primary {
  appearance: none;
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--border-strong);
  border-radius: 3px;
  background: var(--surface);
  cursor: pointer;
  flex-shrink: 0;
  position: relative;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.checkbox-primary:hover { border-color: var(--accent); }
.checkbox-primary:checked {
  background: var(--accent);
  border-color: var(--accent);
}
.checkbox-primary:checked::after {
  content: "";
  position: absolute;
  left: 3px;
  top: 0px;
  width: 4px;
  height: 8px;
  border: solid var(--fg-on-accent);
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}
.checkbox-primary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

### Step 2: Remove the lifted block from `studio.css`

Delete `studio.css:171-209` — that's the comment header (`:171-174`) plus the five `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]` rule blocks (the base rule + `:hover`, `:checked`, `:checked::after`, `:focus-visible` — closing brace at `:209`). The next rule `.area-studio .mcp-auth-required-notice` at `:210` is the boundary marker. Keep the wrapper layout rules at `:167-170`. Insert a one-line pointer comment where the deletion happened:

```css
.area-studio .mcp-tools-checkbox-group { display: flex; flex-direction: column; gap: 4px; }
.area-studio .mcp-tool-toggle-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: var(--font-size-body-sm); }
.area-studio .mcp-tool-toggle-name { font-family: var(--font-family-mono, monospace); }
.area-studio .mcp-tool-toggle-hint { color: var(--fg-faint); font-size: 11px; }
/* Per-tool checkbox treatment lifted to .checkbox-primary in components.css (Mission 08 F2 L2). */
.area-studio .mcp-auth-required-notice { ... }
```

### Step 3: Update `mcps-tab.js:299` (consumer)

The current code at `mcps-tab.js:315-321` creates a `<input type="checkbox">`. Add the `.checkbox-primary` class on it:

```js
var checkbox = document.createElement('input');
checkbox.type = 'checkbox';
checkbox.className = 'checkbox-primary';  // <-- NEW
checkbox.checked = isChecked;
checkbox.setAttribute('data-mcp-tool-toggle', toolName);
// ... (rest unchanged)
```

### Step 4: Update `design-language-page.js` to iterate sections

Rewrite the container module to drive a SECTIONS list:

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  function renderDesignLanguagePage(container) {
    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">Design Language</h1>' +
      '</div>' +
      '<div class="admin-content-body design-language-sections" id="design-language-sections"></div>';

    var sectionsHost = container.querySelector('#design-language-sections');

    // Section descriptor list — fixed order. Each section module registers
    // its render(host) on App.admin.designLanguage.<slug>Section.
    var SECTIONS = [
      { slug: 'tokens',     title: 'TOKENS' },
      { slug: 'typography', title: 'TYPOGRAPHY' },
      { slug: 'buttons',    title: 'BUTTONS' },
      { slug: 'fields',     title: 'FIELDS' },
      { slug: 'surfaces',   title: 'SURFACES' },
      { slug: 'status',     title: 'STATUS' },
      { slug: 'tabs',       title: 'TABS' },
      { slug: 'modal',      title: 'MODAL' },
      { slug: 'markdown',   title: 'MARKDOWN' }
    ];

    for (var i = 0; i < SECTIONS.length; i++) {
      var section = SECTIONS[i];
      var sectionEl = document.createElement('section');
      sectionEl.className = 'design-language-section';
      sectionEl.setAttribute('data-section', section.slug);
      sectionEl.innerHTML =
        '<div class="section-title">' + section.title + '</div>' +
        '<div class="design-language-section-body"></div>';
      sectionsHost.appendChild(sectionEl);

      var moduleName = section.slug + 'Section';
      var module = App.admin.designLanguage[moduleName];
      if (module && typeof module.render === 'function') {
        module.render(sectionEl.querySelector('.design-language-section-body'));
      }
    }
  }

  window.App.admin.renderDesignLanguagePage = renderDesignLanguagePage;
})();
```

Note: the `.section-title::before` rule at `components.css:273-278` automatically prepends `//` to anything with class `.section-title` — so the section eyebrows render as `// TOKENS`, `// TYPOGRAPHY`, etc. without inline string concatenation.

### Step 5: Section modules

Each section module follows the convention:

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  function render(host) {
    host.innerHTML = '<!-- section content -->';
    // optional: wire event handlers for interactive samples
  }

  window.App.admin.designLanguage.tokensSection = { render: render };
})();
```

Section content guidance (each must compose canonical classes only):

- **tokens-section.js**: Render a grid of swatches. Each swatch = a square colored block + a label showing the token name + a label showing the resolved hex (obtained via `getComputedStyle(document.documentElement).getPropertyValue('--accent')` — proves live consumption). Sample tokens: `--bg`, `--surface`, `--surface-elevated`, `--border`, `--border-hover`, `--border-strong`, `--fg`, `--fg-secondary`, `--fg-muted`, `--accent`, `--accent-api`, `--accent-glow`, `--status-success`, `--status-warning`, `--status-danger`. Plus a small "panel radius" sample showing the three radius tokens visually (rounded-corner boxes labeled with their pixel values).

- **typography-section.js**: One line per size token in descending order: display, h1, h2, h3, body-lg, body, body-sm, caption, tiny. Each line shows sample text "The quick brown fox" sized by the token + a label "display 24px" etc. Add a mono variant pair (one body, one body-sm) at the bottom. The eyebrow `.section-title` is also a typography sample by virtue of being on the page.

- **buttons-section.js**: A grid of buttons, columns by primitive (outlined-primary / filled-primary / muted-destructive), rows by size modifier (default / `.btn-sm` / `.btn-lg` / `.btn-xl`). Add a row at the bottom of disabled states. Don't force hover/focus states — operator hovers/focuses live in the gallery during vibe sessions.

- **fields-section.js**: A vertical stack: one `.field-input`, one `.field-textarea`, one `.field-select` (with placeholder options), one `.field-info-icon` (positioned next to a label so the affordance reads correctly). Plus a labeled `<label>` containing a `.checkbox-primary` + text — and a grouped multi-checkbox sample (3 checkboxes in a `<div>` so the checked/unchecked grouping reads).

- **surfaces-section.js**: Multiple sub-blocks:
  - **Entity tile** (single, then a `.entity-tile-grid` with 3 tiles)
  - **Section nav** (a `.section-nav` containing 3 `.section-nav-item` rows; one with `[aria-current="page"]`)
  - **List items** (3 `.list-item` rows: default, active, `.confirm-delete`)
  - **Topbar miniature** (a non-fixed `<div>` with `.app-topbar-title`-styled content showing mascot + GleepGlorp AI text, but at the same dimensions; static, no events)
  - **App-picker miniature** (a `.app-picker-button` closed + open variants; clicking does nothing — sample only)
  - **iOS-toggle sample** (`.tool-enable-switch` from admin.css). DOM template MUST be the canonical structure from `tools-grid.js:67-72`. The primitive's `position: absolute; bottom: 12px; right: 12px` (admin.css:159-161) is designed for entity-tile placement; in the gallery, override it to `position: static` via the gallery-scoped CSS rule (added in Step 6 below). Wrap each toggle in a `.design-language-toggle-sample` flex container so the two states render side-by-side:
    ```html
    <div class="design-language-toggle-sample">
      <label class="tool-enable-switch">
        <input type="checkbox" checked aria-label="ON state sample">
        <span class="tool-enable-switch-track" aria-hidden="true"></span>
      </label>
      <span class="design-language-toggle-label">ON</span>
      <label class="tool-enable-switch">
        <input type="checkbox" aria-label="OFF state sample">
        <span class="tool-enable-switch-track" aria-hidden="true"></span>
      </label>
      <span class="design-language-toggle-label">OFF</span>
    </div>
    ```
    Both ON and OFF states render side-by-side so the operator sees both visual modes simultaneously.

- **status-section.js**:
  - `.test-result` × 4 variants in a row
  - `.app-flash` × 2 variants (success + error) — render as `position: relative` overrides so they sit in the gallery rather than fixed at the top of the viewport (`<div class="app-flash visible" style="position: relative; transform: none; left: auto; top: auto;">Success</div>`)
  - `.action-blocked-message` sample
  - `.chip` + `.chip-remove` sample
  - `.empty-state` sample (in a bordered container so it doesn't take infinite space)
  - `.empty-canvas` sample. `.empty-canvas { flex: 1; min-height: 0; display: flex; … }` per `components.css:363-371` — `flex: 1` ONLY takes effect when the parent has `display: flex` AND a flex-direction. Wrap in a parent that satisfies both: `<div style="height: 200px; display: flex; flex-direction: column; border: 1px dashed var(--border);">` with the `.empty-canvas` as the sole child. (The canonical app uses the `.entity-tile-grid:has(> .empty-canvas) { display: flex; }` pattern at `components.css:384-387` to flip the grid to flex; the gallery uses an equivalent manual override.)

- **tabs-section.js**: A `<div role="tablist">` containing 3 `<button role="tab">` elements + a `<div class="tabpanels">` containing 3 `<div role="tabpanel">` panels (one without `[hidden]` — the initial — and two with `[hidden]`). Each tab carries a unique `id` (or `data-tab-id`); each tabpanel carries the matching `id`/`aria-labelledby` reference. Wire with the canonical signature:
  ```js
  window.App.tabs(tablistEl, panelsEl, { initial: 'tab-1', onChange: function (id) { /* no-op for the gallery */ } });
  ```
  per `tabs.js:38` and matching existing consumers `agent-editor.js:173`, `tools-grid.js:171`. There is no `App.tabs.wire(...)` method.

- **modal-section.js**: A static `.modal-dialog` previewed inline (no overlay backdrop — render the dialog box positioned `relative`, not fixed, so it sits in the gallery flow); plus a button `<button class="btn-outlined-primary" data-action="open-sample-modal">Open modal</button>`. Wire the button to call the canonical signature per `dialog.js:11, :82-83`:
  ```js
  App.confirmDialog({
    title: 'Sample modal',
    message: 'This is the canonical confirm dialog primitive.',
    confirmText: 'OK',
    cancelText: 'Cancel',
    onConfirm: function () { /* no-op */ },
    onCancel: function () { /* no-op */ }
  });
  ```
  NOTE: the option keys are `confirmText` / `cancelText` (NOT `confirmLabel` — the helper silently ignores unknown keys and falls back to defaults). Showing both `onConfirm` and `onCancel` in the sample documents the canonical surface for future readers.

- **markdown-section.js**: Compose `App.markdown.render('```js\n…\n```')` — the canonical helper at `markdown.js:6` already constructs the full `<div class="markdown-code-wrap"><pre><code>…</code></pre><button class="markdown-copy-btn">…</button></div>` structure including the click-to-copy handler and the hover-reveal contract from `components.css:840-844`. The section is a **passive consumer** of `App.markdown.render`, NOT a parallel re-implementation. Mount the returned DocumentFragment via `host.appendChild(App.markdown.render(markdownText));` matching the existing consumer pattern at `message-bubble.js:28`. Choose sample markdown that exercises a code fence and a paragraph or two so the section shows both inline rendering and the copy button.

### Step 6: Add area-scoped layout styles to `admin.css`

Add a small block scoped to `.area-admin .design-language-sections` at the end of `admin.css` (before the closing `}` of `@layer areas`):

```css
/* Mission 08 F2 — Design Language gallery (dev-mode-only Admin category) */
.area-admin .design-language-sections { display: flex; flex-direction: column; gap: 24px; padding: 0 20px 40px; overflow-y: auto; }
.area-admin .design-language-section { display: flex; flex-direction: column; gap: 8px; }
.area-admin .design-language-section-body { display: flex; flex-direction: column; gap: 12px; }
.area-admin .design-language-token-swatch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.area-admin .design-language-token-swatch { display: flex; flex-direction: column; gap: 4px; padding: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--panel-radius-sm); }
.area-admin .design-language-token-swatch-color { width: 100%; height: 40px; border-radius: 4px; border: 1px solid var(--border); }
.area-admin .design-language-token-swatch-label { font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted); }
.area-admin .design-language-button-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; align-items: start; }

/* iOS-toggle gallery sample — strips the primitive's bottom-right absolute
   anchoring (designed for entity-tile placement) so two toggles render
   side-by-side in the gallery flow. */
.area-admin .design-language-toggle-sample { display: flex; gap: 12px; align-items: center; }
.area-admin .design-language-toggle-sample .tool-enable-switch { position: static; }
.area-admin .design-language-toggle-label { font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted); }
```

(The exact layout primitives can be tuned during implementation if a different layout reads better; this is a working draft.)

### Step 7: Update `static/index.html`

Insert the 9 section-module script tags between `design-language-page.js` and `admin.js`:

```html
<script src="/static/js/areas/admin/design-language-page.js"></script>
<script src="/static/js/areas/admin/design-language/tokens-section.js"></script>
<script src="/static/js/areas/admin/design-language/typography-section.js"></script>
<script src="/static/js/areas/admin/design-language/buttons-section.js"></script>
<script src="/static/js/areas/admin/design-language/fields-section.js"></script>
<script src="/static/js/areas/admin/design-language/surfaces-section.js"></script>
<script src="/static/js/areas/admin/design-language/status-section.js"></script>
<script src="/static/js/areas/admin/design-language/tabs-section.js"></script>
<script src="/static/js/areas/admin/design-language/modal-section.js"></script>
<script src="/static/js/areas/admin/design-language/markdown-section.js"></script>
<script src="/static/js/areas/admin.js"></script>
```

The order between the section modules doesn't matter (each registers on `App.admin.designLanguage` independently), but the section MODULE tags MUST load AFTER `design-language-page.js` (which bootstraps the `designLanguage` namespace? — actually, all use `|| {}` defaulting so order is forgiving; but keeping the container-first order matches the rest of the convention).

### Step 8: Update `Makefile` `verify-serving`

Extend the admin-sub-module shell-loop at `Makefile:93` to include the 9 new section modules:

```make
@for f in admin.js admin/system-page.js admin/providers-grid.js admin/provider-editor.js admin/provider-models.js admin/tools-form-helpers.js admin/tools-grid.js admin/tools-editor.js admin/design-language-page.js admin/design-language/tokens-section.js admin/design-language/typography-section.js admin/design-language/buttons-section.js admin/design-language/fields-section.js admin/design-language/surfaces-section.js admin/design-language/status-section.js admin/design-language/tabs-section.js admin/design-language/modal-section.js admin/design-language/markdown-section.js layout/section-nav.js; do \
```

(Long line is acceptable — matches the existing convention in this target.)

### Step 9: Verification flow

`make rebuild` (also runs `verify-serving` — fails loud if any new module 404s). Then run the verification steps above (gallery visual inspection, MCP-tab checkbox regression check, modal trigger, tabs keyboard nav, markdown copy, token live-consumption test, narrow gate).

## Edge Cases

- **A section module fails to load (404 or parse error)**: The descriptor iteration skips the `if (module && typeof module.render === 'function')` check, leaving the section's body empty. The section eyebrow still renders so the gap is visible rather than silent. `verify-serving` would catch 404s in `make rebuild`.
- **`App.tabs` API mismatch** (the tabs section's `wire` call): If the existing helper has a different surface (e.g., it auto-initializes on DOMContentLoaded for any `[role="tablist"]`), the explicit wire call may be redundant or wrong. Implementing developer should inspect `tabs.js` and use whatever the existing studio agent editor uses.
- **`App.confirmDialog` call shape**: The signature is established (used in chat session items, studio agent editor, provider editor). Implementing developer should grep an existing call site and mirror the options object shape.
- **Topbar miniature pulling in real chrome height**: The real `--topbar-h` is 48px; the miniature uses the same height to faithfully represent the topbar but renders inside a flow container, not fixed. Verify the miniature doesn't accidentally `position: fixed` (the static-miniatures contract).
- **`.empty-canvas` consuming infinite space**: The `flex: 1` makes it greedy. The gallery wraps it in a fixed-height `<div>` (e.g., 200px) so it claims that space and centers within. Documented in the surfaces section guidance.
- **`.app-flash` rendering at the top of the viewport**: The primitive is `position: fixed; top: 16px; left: 50%`. In the gallery, sample with inline style overrides (`position: relative; transform: none; left: auto; top: auto;`) so it sits in the section flow.
- **Studio MCP-tab regression risk from the checkbox lift**: The treatment is byte-for-byte equivalent (same hex values, same hover/check/focus rules), just under a primitive class name instead of an area-scoped descendant selector. Specificity changes: old rule was `(0,1,2)` (`.area-studio .mcp-tools-checkbox-group input[type="checkbox"]`) — high specificity; new rule is `(0,2,0)` (`.checkbox-primary:checked`) — lower specificity but plenty for an unstyled `<input>`. No competing rules elsewhere in the codebase target `input[type="checkbox"]` with the same or higher specificity (verified by grep at design time — see Citation Audit).
- **DevTools network-block test for live consumption**: Some browsers cache `:root` style mutations in different ways. The token-section live-consumption test (verification step 8) is robust because `getComputedStyle` reads the resolved value at call time, not a cached value.

## Files Affected

- `the_one/interfaces/web/static/css/components.css` — add `.checkbox-primary` primitive (~30 LOC)
- `the_one/interfaces/web/static/css/studio.css` — remove `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]` block; update surviving comment
- `the_one/interfaces/web/static/css/admin.css` — add `.area-admin .design-language-sections` gallery layout rules (~15 LOC)
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` — line 315 region, add `className = 'checkbox-primary'` on the checkbox
- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` — rewrite to drive SECTIONS list iteration
- `the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/typography-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/buttons-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/fields-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/surfaces-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/status-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/tabs-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/modal-section.js` — NEW
- `the_one/interfaces/web/static/js/areas/admin/design-language/markdown-section.js` — NEW
- `the_one/interfaces/web/static/index.html` — add 9 new section-module `<script>` tags between `design-language-page.js` and `admin.js`
- `Makefile` — extend `verify-serving` admin-sub-module loop with the 9 new section modules

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Narrow test gate passing
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in `flight.md` — NO, the orchestrator handles flight-level updates at flight close
- [ ] Do NOT commit yet — orchestrator commits all autonomous legs together in Phase 2d
- [ ] Signal `[HANDOFF:review-needed]` (handled by Flight Director, not Developer)

## Citation Audit

15 citations verified against current code at leg design time:

- `studio.css:167-210` `.area-studio .mcp-tools-checkbox-group` wrapper + checkbox treatment — confirmed exact at line-level via `sed -n`: wrapper layout rules at `:167-170` (4 rules: `.mcp-tools-checkbox-group`, `.mcp-tool-toggle-label`, `.mcp-tool-toggle-name`, `.mcp-tool-toggle-hint`); comment header at `:171-174`; 5 checkbox rules at `:175-209` (base + `:hover` + `:checked` + `:checked::after` + `:focus-visible`, closing brace at :209); next rule `.area-studio .mcp-auth-required-notice` at `:210`. Lift target: `:171-209` (comment + 5 rules); keep `:167-170` wrapper layout. Earlier draft said `:175-208` — corrected by Developer review (off-by-one in closing-brace line).
- `mcps-tab.js:299` `group.className = 'mcp-tools-checkbox-group'` — confirmed exact
- `mcps-tab.js:315-321` checkbox creation block — confirmed exact (`document.createElement('input')` → `.type = 'checkbox'` → `.checked` → `data-mcp-tool-toggle` etc.)
- `admin.css:157-220` `.area-admin .tool-enable-switch, .area-studio .tool-enable-switch` iOS-toggle — confirmed exact (dual-scope selector; stays put as a sibling primitive in the gallery)
- `components.css:273-278` `.section-title::before { content: "//"; ... }` — confirmed (auto-prepends `//` so eyebrows just use the class name)
- `components.css:840-844` `.markdown-code-wrap:hover .markdown-copy-btn { opacity: 1; }` — confirmed (hover-reveal contract for the markdown copy button)
- `tokens.css:48-53` dark accent palette + glow/translucent — confirmed (token names for the tokens-section)
- `fonts.css:33-52` typography ladder — confirmed (font-size/weight/line-height tokens)
- `components.css:280-310` button primitives `.btn-outlined-primary` / `.btn-filled-primary` / `.btn-muted-destructive` — confirmed exact
- `components.css:340-342` button size modifiers `.btn-sm` / `.btn-lg` / `.btn-xl` — confirmed exact
- `components.css:880-895` `.modal-overlay` / `.modal-dialog` / `.modal-actions` — confirmed exact (modal section samples)
- `tabs.js:38` `window.App.tabs = function (tablistEl, panelsEl, opts)` — confirmed via grep (canonical signature; NO `.wire` method); two existing consumers `agent-editor.js:173` and `tools-grid.js:171`
- `dialog.js:11, :82-83` `App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` — confirmed; `confirmText`/`cancelText` are the option keys, NOT `confirmLabel`/`cancelLabel`; `dialog.js:203-211` confirms overlay-click is a deliberate no-op (no outside-to-dismiss)
- `markdown.js:6` `App.markdown.render(text) -> DocumentFragment` — confirmed; the helper at `markdown.js:753-790` `renderCodeBlock` builds the full `<div class="markdown-code-wrap">…</div>` structure including the copy-btn click handler; consumer pattern at `message-bubble.js:28` is `host.appendChild(App.markdown.render(text))`
- `tools-grid.js:67-72` canonical iOS-toggle DOM template — confirmed: `<label class="tool-enable-switch"><input type="checkbox"><span class="tool-enable-switch-track" aria-hidden="true"></span></label>`
- `components.css:363-371` `.empty-canvas { flex: 1; min-height: 0; display: flex; … }` + `:384-387` `.entity-tile-grid:has(> .empty-canvas) { display: flex; }` — confirmed; `flex: 1` only takes effect when parent has `display: flex`

Specificity check for the `.checkbox-primary` lift:
- Old: `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]:checked` — specificity (0,3,2) = 32
- New: `.checkbox-primary:checked` — specificity (0,2,0) = 20
- No competing rule in any other CSS file matches `input[type="checkbox"]` with specificity > 20 (verified by `grep -rn 'input\[type="checkbox"\]' the_one/interfaces/web/static/css/` — returns only the studio.css rules being lifted and the `.tool-enable-switch input[type="checkbox"]` rules at admin.css:166-167 which is a different selector path).

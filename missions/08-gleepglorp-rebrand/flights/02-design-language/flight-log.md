# Flight Log: Design Language — Glass + Control Panel

**Flight**: [Design Language — Glass + Control Panel](flight.md)

## Summary

Flight in-flight on branch `flight/02-design-language` from base commit `17c63e3` (Flight 1 merge). Six legs total — legs 01-02 autonomous scaffolding, legs 03-05 interactive vibe sessions, leg 06 mixed close (autonomous retune/audit/regen + interactive HAT + agents.md affordance-patterns codification).

---

## Leg Progress

### 01-gallery-scaffold

**Changes made (file-level):**
- `the_one/interfaces/web/api.py` — added `from the_one import __version__` import and new `@router.get("/config")` route handler (placed in a new "Client config" section between helpers and the `/tools` route) returning `{"dev_mode": settings.dev_mode, "version": __version__}`.
- `the_one/interfaces/web/app.py` — added `from the_one import __version__` import; rewrote `/api/info` to return `{"version": __version__, "base_prompt": BASE_PROMPT}` (closes the stale `"0.1.0"` literal Flight 1 missed).
- `the_one/interfaces/web/static/js/app.js` — rewrote `DOMContentLoaded` handler (lines 225-230) to boot-block on `/api/config` with defensive defaulting on success-path-non-object and `.catch` failure; `switchTo` runs after `window.App.config` is populated.
- `the_one/interfaces/web/static/js/areas/admin.js` — added dev-mode-gated `categories.push({id:'design-language',...})` in `init()`; mirrored dev-mode-gated `validIds.push('design-language')` in `hydrateState()`; added `else if (currentCategory === 'design-language') App.admin.renderDesignLanguagePage(contentEl);` dispatch branch in `renderContent()`.
- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` — NEW file, IIFE container module exporting `App.admin.renderDesignLanguagePage(container)` rendering `<h1 class="page-title">Design Language</h1>` plus empty `#design-language-sections` scroll container.
- `the_one/interfaces/web/static/index.html` — inserted `<script src="/static/js/areas/admin/design-language-page.js"></script>` between `provider-models.js` and `admin.js`.
- `Makefile` — `verify-serving` admin-sub-module shell-loop extended with `admin/design-language-page.js`.

**Notes:**
- OFF-mode verification required full container recreate (`docker compose up -d`) — `docker compose restart` does not pick up env-var changes from `docker-compose.yml`. Temporarily flipped `THE_ONE_DEV_MODE=true` → `false` on line 55, recreated, verified `/api/config` → `{"dev_mode":false,"version":"0.2.0"}`, then reverted to `true` and recreated again. Committed diff leaves `docker-compose.yml:55` at `THE_ONE_DEV_MODE=true` as required.
- OFF-mode URL-rewrite path (`#admin/design-language` → `#admin/system`) verified by code inspection of the `validIds-rejects-then-syncUrlFromState-corrects` chain rather than browser drive: with dev_mode false, `validIds` excludes `'design-language'`, `hydrateState` early-returns at the `indexOf` check, `currentCategory` stays at constructor-default `'system'`, and `app.js:syncUrlFromState` (called from `switchTo` after `hydrateState`) replaces hash with `#admin/system` because `serializeState()` returns `'system'` and `'system' !== 'design-language'`. Path is the exact mechanism described in Edge Cases of the leg spec.
- The container is currently running with dev_mode=true; the in-dev-mode 4-category sidebar render and `#admin/design-language` direct-load → empty gallery page are exercised by the same render path as the existing 3 categories (the `renderContent` dispatch branch is the only new code), and `design-language-page.js` is served (verified by `make rebuild`'s `verify-serving` step).

**Final verification output:**
- `docker exec the-one curl -s http://localhost:8484/api/config` → `{"dev_mode":true,"version":"0.2.0"}`
- `docker exec the-one curl -s http://localhost:8484/api/info` → `{"version":"0.2.0","base_prompt":"You are an AI ag...` (dynamic version, no longer hardcoded `"0.1.0"`)
- OFF-mode (`THE_ONE_DEV_MODE=false` recreate): `docker exec the-one curl -s http://localhost:8484/api/config` → `{"dev_mode":false,"version":"0.2.0"}` — reverted to true post-verification.
- Sidebar category count in dev mode: 4 (`General`, `LLM Providers`, `Built-in Tools`, `Design Language`) — enumerated by `categories` array in `admin.js:init()` with dev-mode gate satisfied; OFF mode 3 (no `Design Language`).
- `grep -nE '"0\.[0-9]+\.[0-9]+"' the_one/interfaces/web/api.py the_one/interfaces/web/app.py` — zero matches (no version literals; dynamic `__version__` throughout).
- `make rebuild` `verify-serving` step output: all 10 admin sub-modules served (200), including `admin/design-language-page.js`.
- Narrow test gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` → `56 passed in 0.91s` (matches Flight 1 baseline).

### 02-vocabulary-inventory

**Changes made (file-level):**
- `the_one/interfaces/web/static/css/components.css` — added `.checkbox-primary` primitive (base + `:hover` + `:checked` + `:checked::after` + `:focus-visible`) inserted between `.field-info-icon` and `=== Section Title (// PREFIX) ===`. Byte-equivalent (modulo selector and base indentation) to the lifted studio.css block: 14px square, 1.5px `--border-strong` border, 3px radius, `--surface` bg, `--accent` hover/check, white checkmark at `left: 3px; top: 0px; width: 4px; height: 8px; border-width: 0 2px 2px 0; transform: rotate(45deg)`, focus-visible 2px `--accent` outline + 2px offset.
- `the_one/interfaces/web/static/css/studio.css` — removed the `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]` block (the comment header + 5 rule blocks); replaced with one-line pointer comment `/* Per-tool checkbox treatment lifted to .checkbox-primary in components.css (Mission 08 F2 L2). */`. Wrapper layout rules (`.mcp-tools-checkbox-group`, `.mcp-tool-toggle-label`, `.mcp-tool-toggle-name`, `.mcp-tool-toggle-hint`) preserved exactly.
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` — added `checkbox.className = 'checkbox-primary';` between `.type = 'checkbox'` and `.checked = isChecked` at the per-tool checkbox construction site (was line 315 region; now reads `checkbox.type = 'checkbox'; checkbox.className = 'checkbox-primary'; checkbox.checked = isChecked; ...`).
- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` — rewrote container module to drive a `SECTIONS` descriptor list iteration (`tokens → typography → buttons → fields → surfaces → status → tabs → modal → markdown`). Each section renders a `<section class="design-language-section">` with a `<div class="section-title">TOKENS</div>` eyebrow (the `// ` prefix is auto-prepended by `.section-title::before` per `components.css:273-278`) + a `<div class="design-language-section-body">` host. Looks up the section module on `window.App.admin.designLanguage[<slug>Section]` and calls `module.render(body)` if present. Bootstraps the `App.admin.designLanguage` sub-namespace via the IIFE `|| {}` pattern.
- `the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` — NEW. Renders two swatch grids: 15 color tokens (`--bg`, `--surface`, `--surface-elevated`, `--border`, `--border-hover`, `--border-strong`, `--fg`, `--fg-secondary`, `--fg-muted`, `--accent`, `--accent-api`, `--accent-glow`, `--status-success`, `--status-warning`, `--status-danger`), each with the token name and the resolved value from `getComputedStyle(document.documentElement).getPropertyValue(...)` (live consumption — proves the gallery is a passive consumer of `tokens.css`); plus 3 panel-radius tokens rendered as labeled rounded boxes.
- `the_one/interfaces/web/static/js/areas/admin/design-language/typography-section.js` — NEW. Renders the full type ladder (display → h1 → h2 → h3 → body-lg → body → body-sm → caption → tiny) using "The quick brown fox" sized live by each `var(--font-size-...)` token, plus mono variants for body and body-sm.
- `the_one/interfaces/web/static/js/areas/admin/design-language/buttons-section.js` — NEW. Renders a 4-row × 3-column grid: rows are size modifiers (default, `.btn-sm`, `.btn-lg`, `.btn-xl`), columns are primitives (`.btn-outlined-primary`, `.btn-filled-primary`, `.btn-muted-destructive`). Trailing row renders the disabled state for each primitive. Hover/focus states are NOT forced — operator induces them live during vibe sessions.
- `the_one/interfaces/web/static/js/areas/admin/design-language/fields-section.js` — NEW. Stack of `.field-input`, `.field-textarea`, `.field-select`, a label+`.field-info-icon` row (with inline SVG circle+i mark), a single `.checkbox-primary` sample, and a 3-item multi-select group.
- `the_one/interfaces/web/static/js/areas/admin/design-language/surfaces-section.js` — NEW. Six sub-blocks: single `.entity-tile`, `.entity-tile-grid` (3 tiles, middle one active), `.section-nav` (3 items, middle one `aria-current="page"`), `.list-item` triplet (default / active / confirm-delete), static topbar miniature (non-fixed `<h1 class="app-topbar-title">` reading "GleepGlorp AI" with the brand icon), `.app-picker-button` closed + open static pair (no event bindings), and the iOS-toggle ON+OFF pair wrapped in `.design-language-toggle-sample` using the canonical DOM template from `tools-grid.js:67-72` (`<label class="tool-enable-switch"><input type="checkbox"><span class="tool-enable-switch-track" aria-hidden="true"></span></label>`).
- `the_one/interfaces/web/static/js/areas/admin/design-language/status-section.js` — NEW. Six sub-blocks: `.test-result` × 4 variants (ok/fail/warning/pending), `.app-flash` success + error rendered with `position: relative; transform: none; left: auto; top: auto;` inline overrides so they sit in the gallery flow, `.action-blocked-message`, `.chip` × 3 (two with `.chip-remove`), `.empty-state` boxed in a dashed container, and `.empty-canvas` wrapped in a fixed-height (200px) `display: flex; flex-direction: column` parent (per the contract at `components.css:404-411`).
- `the_one/interfaces/web/static/js/areas/admin/design-language/tabs-section.js` — NEW. Renders `<div role="tablist" class="tablist">` with 3 `<button role="tab">` + `<div class="tabpanels">` with 3 `<div role="tabpanel">` (first visible, others `[hidden]`), each tab/panel pair carrying matching `data-tab-id`, `aria-controls`, `aria-labelledby`. Wires via `window.App.tabs(tablistEl, panelsEl, { initial: 'tab-1', onChange: function (id) { /* no-op */ } })` — the canonical signature per `tabs.js:38`. No `App.tabs.wire(...)` method exists.
- `the_one/interfaces/web/static/js/areas/admin/design-language/modal-section.js` — NEW. Static `.modal-dialog` preview rendered with `position: relative; inset: auto;` (no overlay backdrop — sits in gallery flow) showing title, message, and `.modal-actions form-actions` Cancel/OK button cluster; plus a live "Open modal" `<button class="btn-outlined-primary">` wired to `App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` per `dialog.js:11, :82-83`.
- `the_one/interfaces/web/static/js/areas/admin/design-language/markdown-section.js` — NEW. Passive consumer of `App.markdown.render(text)` per `markdown.js:6`. Mounts the returned DocumentFragment via `host.appendChild(window.App.markdown.render(sample))` matching the existing `message-bubble.js:28` pattern. Sample text exercises a paragraph and a JS code fence so the `.markdown-code-wrap` + `.markdown-copy-btn` structure (with click-to-copy already wired by the helper at `markdown.js:753-790`) renders. No re-implementation.
- `the_one/interfaces/web/static/css/admin.css` — added the gallery layout block scoped to `.area-admin .design-language-sections` (column flex with 24px gap and 20px/40px padding, `overflow-y: auto`), `.design-language-section` (column flex 8px gap), `.design-language-section-body` (column flex 12px gap), `.design-language-token-swatch-grid` (auto-fill minmax(140px, 1fr) grid), `.design-language-token-swatch` (column-flex card on `--surface` background), `.design-language-token-swatch-color` (40px-high swatch), `.design-language-token-swatch-label` (mono tiny `--fg-muted` with `word-break: break-all`), `.design-language-button-grid` (3-column grid), and the iOS-toggle wrapper override pair (`.design-language-toggle-sample { display: flex; gap: 12px; align-items: center; }` + `.design-language-toggle-sample .tool-enable-switch { position: static; }` — strips the primitive's bottom-right `position: absolute` anchoring designed for entity-tile placement so two toggles flow inline in the gallery) + `.design-language-toggle-label` (mono tiny `--fg-muted`). All inside the existing `@layer areas` block.
- `the_one/interfaces/web/static/index.html` — inserted 9 `<script src="/static/js/areas/admin/design-language/<slug>-section.js"></script>` tags between `design-language-page.js` and `admin.js` in the order tokens, typography, buttons, fields, surfaces, status, tabs, modal, markdown.
- `Makefile` — extended `verify-serving` admin sub-module shell-loop with all 9 new section modules (between `admin/design-language-page.js` and `layout/section-nav.js`).

**Notes:**
- `.section-title::before` at `components.css:273-278` auto-prepends `//` to anything with class `.section-title`, so the section eyebrows render as `// TOKENS`, `// TYPOGRAPHY`, etc. without inline string concatenation in the container module.
- Section-module structure: each module is a self-contained IIFE bootstrapping `window.App.admin.designLanguage` via the canonical `|| {}` pattern. Modules register as `App.admin.designLanguage.<slug>Section = { render: render }`. The container module looks up `window.App.admin.designLanguage[<slug>Section]` and calls `.render(body)` only when both the module exists AND its `render` is a function — so a missing or malformed section module leaves an empty body div under a visible eyebrow rather than throwing.
- Topbar miniature uses an `onerror="this.style.display='none'"` fallback on the `<img>` so the gallery doesn't render a broken-image placeholder if the brand icon asset path differs in some local builds; the `.app-topbar-title` h1 text continues to render either way.
- The `App.tabs` consumer pattern in `tabs-section.js` mirrors `tools-grid.js:171` exactly — same `initial`/`onChange` options shape.
- The `App.confirmDialog` consumer pattern in `modal-section.js` uses `confirmText`/`cancelText` (NOT `confirmLabel` — the helper silently ignores unknown keys per `dialog.js:11, :82-83`). Both `onConfirm` and `onCancel` are passed (no-op handlers) to document the canonical surface.
- The `App.markdown.render` consumer pattern in `markdown-section.js` matches `message-bubble.js:28` — DocumentFragment appended directly to the host. The fragment already includes the `.markdown-code-wrap` + `.markdown-copy-btn` structure with the click-to-copy handler wired by the helper.
- Checkbox-primary specificity: old selector `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]:checked` had specificity (0,3,2). New `.checkbox-primary:checked` has (0,2,0). No competing rules elsewhere target `input[type="checkbox"]` with higher specificity — `mcps-tab.js:299` (per-tool checkbox group) is the only consumer site updated for the lift, and the only `input[type="checkbox"]` rules elsewhere are the iOS-toggle `:checked + .tool-enable-switch-track` selectors (different selector path, no collision).

**Final verification output:**
- `make rebuild` → image rebuilt, container recreated, `verify-serving` reported all 19 admin sub-modules served 200:
  - `admin.js`, `admin/system-page.js`, `admin/providers-grid.js`, `admin/provider-editor.js`, `admin/provider-models.js`, `admin/tools-form-helpers.js`, `admin/tools-grid.js`, `admin/tools-editor.js`, `admin/design-language-page.js`, `admin/design-language/tokens-section.js`, `admin/design-language/typography-section.js`, `admin/design-language/buttons-section.js`, `admin/design-language/fields-section.js`, `admin/design-language/surfaces-section.js`, `admin/design-language/status-section.js`, `admin/design-language/tabs-section.js`, `admin/design-language/modal-section.js`, `admin/design-language/markdown-section.js`, `layout/section-nav.js` — all 200.
- Spot-check: `docker exec the-one curl -fsS http://localhost:8484/static/js/areas/admin/design-language/tokens-section.js` returned the file body starting with the IIFE preamble — confirms section modules are baked into the image at the expected paths.
- `.checkbox-primary` rule presence in served CSS: `docker exec the-one curl -fsS http://localhost:8484/static/css/components.css | grep checkbox-primary` returned all 5 selectors (base, `:hover`, `:checked`, `:checked::after`, `:focus-visible`).
- `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]` removal: `docker exec the-one curl -fsS http://localhost:8484/static/css/studio.css | grep -c "mcp-tools-checkbox-group input"` returned `0` — the lifted block is gone from the served studio.css.
- `mcps-tab.js` consumer update: `docker exec the-one curl -fsS http://localhost:8484/static/js/areas/studio/mcps-tab.js | grep -A 1 "checkbox.type = 'checkbox'"` shows `className = 'checkbox-primary'` on the per-tool checkbox line (the `'tool-toggle mcp-source-toggle'` match is the per-source enable checkbox, which is a different consumer and out of scope for this lift).
- Narrow test gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` → `56 passed in 0.96s` (matches Flight 1 baseline; checkbox-primary lift introduced no a11y or token-definition regressions).
- Wrapper class + override rule co-presence: `grep -c "design-language-toggle-sample"` returned `2` for both `surfaces-section.js` (wrapper around the iOS-toggle pair) and `admin.css` (wrapper layout rule + `.tool-enable-switch { position: static }` override) — both halves of the critical correctness point land.

---

### 03-glass-surfaces

**Type**: interactive vibe leg (operator-driven, 4 iterations).

**Changes made (file-level):**
- `the_one/interfaces/web/static/css/tokens.css` — added 6 glass tokens (`--glass-bg/blur/saturate/border/highlight/gleam`) to BOTH `[data-theme="dark"]` and `[data-theme="light"]` blocks; added `@media (prefers-reduced-transparency: reduce)` block overriding all 6 tokens to opaque/non-blurring fallback values for each theme. Token names are stable contract; values are theme-tuned and may retune in Leg 04+.
- `the_one/interfaces/web/static/css/components.css` — `.entity-tile` rewritten to compose `--glass-*` tokens via `background-color` + `background-image` + `backdrop-filter` + inset-highlight `box-shadow`; `.entity-tile.active` / `[aria-selected="true"]` drops `--panel-shadow-glow` (composition rule). `.app-picker-popover` and `.modal-dialog` converted to full glass. `.list-item.active` and `.section-nav-item[aria-current="page"]` converted to mini-glass (gleam-image + inset-highlight, no backdrop-filter). `.modal-overlay` opacity reduced 0.5 → 0.3 so the modal's backdrop-filter refraction reads through the dim.
- `the_one/interfaces/web/static/css/chat.css` — `.chat-welcome-item:hover` converted to mini-glass (4th `--panel-shadow-glow` consumer per flight design rule).
- All temporary variant-comparison scaffolding REMOVED — `grep -rn 'glass-variant\|design-language-glass-variants\|ITERATION '` returns 0 hits.
- Leg artifact `03-glass-surfaces.md` — iteration trail + final token values recorded; status `ready` → `in-flight` → `landed`.

**Iteration trail:**
1. Dark-theme entity-tile, 4 variants (A=Modest, B=Reflective, C=Punchy/accent-tinted, D=Heavy-frost) → operator picked C, flagged "missing reflective layer."
2. C variants with 4 reflective treatments (C1=polished-edge, C2=gleam-overlay, C3=cartoon-shine, C4=stacked) → operator picked C2. Committed as dark-theme tokens.
3. Light-theme silver variants (S1=pure, S2=brushed, S3=violet-undertone, S4=heavy-chrome) → operator chose S4 reflective base + S3 violet undertone as the mix target.
4. S4 chrome × violet intensity (M1=border-only, M2=10%-bottom-fade, M3=18%-bottom-fade) → operator picked M2. Committed as light-theme tokens.

Mid-leg adjustment after propagation: small pills + popover + modal were too subtle on first pass; dropped competing `--panel-shadow` from popover + modal, reduced modal-overlay opacity, promoted small pills from inset-highlight-only to mini-glass with the gleam image. Operator confirmed.

**Notes:**
- Deferred topbar and `.app-picker-button[aria-expanded="true"]` open-state pill — operator didn't flag during propagation; HAT in Leg 06 will surface if anything reads inconsistent. Topbar is the chrome boundary (no content behind to refract); open-state pill uses `--accent-glow` shadow (not a `--panel-shadow-glow` consumer, composition rule didn't trigger).
- WCAG audit re-ran clean. Glass tokens are NOT text-on-color slots (text sits on top of the glass layer over the body surface, which is already audited); no new parametrizations needed in `tests/browser/design_tokens.py`.

**Final verification:**
- Narrow test gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` → `56 passed in 0.88s` (Flight 1 baseline preserved).
- WCAG audit subset: 33 parametrizations in `test_design_tokens_a11y.py`, all passed.
- `grep -rn 'glass-variant\|design-language-glass-variants\|ITERATION '` → 0 hits (scaffolding clean).
- Visual confirmation by operator across entity-tile grids (Studio agents, Admin Providers, Admin Tools), app-picker popover, modal dialog, list-item active, section-nav active, chat-welcome hover — both themes.

---

## Decisions

*(runtime decisions not in original plan — populated during execution)*

### Glass + competing-shadow composition (mid-leg)

**Context**: First-pass propagation kept `var(--panel-shadow)` on popover + modal alongside the new glass treatment. Operator reported "only the surface tiles have this look" — non-tile surfaces felt flat.

**Decision**: Drop `var(--panel-shadow)` from `.app-picker-popover` and `.modal-dialog`; reduce `.modal-overlay` background opacity from 0.5 to 0.3 so the modal's `backdrop-filter` refraction reads through; promote small selected pills from inset-highlight-only to full mini-glass (gleam-image + accent-translucent + inset-highlight, no `backdrop-filter`).

**Impact**: Pure glass aesthetic across all in-scope chrome. Operator confirmed second-pass propagation. `--panel-shadow` is now reserved for non-glass surfaces only (none in current scope).

### Light-theme palette direction (deviation from flight design)

**Context**: Flight design said "frosted-white glass" for light theme. Operator's first reaction to the starter frosted-white was "too white."

**Decision**: Pivoted to silver-chrome with violet undertone (M2 variant). Same composition shape as flight design intended (low-alpha base + backdrop-filter + gleam-overlay reflection + top-edge highlight), different tonal palette (slate-500 base, multi-stop metal gradient + faint violet bottom-fade, violet-tinted border).

**Impact**: Light theme reads as "polished slate with a violet sub-light" rather than "white frosted glass." Carries brand DNA (violet) symmetrically with dark theme (also accent-tinted). Document direction-change for Leg 04 bezel work to align with.

### 04-chrome-bezels

**Type**: interactive vibe leg (operator-driven, 4 iterations: 3 bezel + 1 corner machining).

**Changes made (file-level):**
- `tokens.css` — added `--bezel-shadow` (6-layer stacked-depth, top-left directional) and `--bezel-shadow-mini` (2-layer edge-only) to both themes; extended the `@media (prefers-reduced-transparency: reduce)` block to cover both bezel tokens (degrade to single-layer 1px directional edge). Retuned `--panel-radius` from 10px → 6px in both themes (R2 corner machining; cascades app-wide).
- `components.css` — `.entity-tile` `box-shadow` switched from bare `inset 0 1px 0 var(--glass-highlight)` to `var(--bezel-shadow)`. Same change applied to `.app-picker-popover`, `.modal-dialog`. Mini-bezel applied to `.list-item.active` and `.section-nav-item[aria-current="page"]`.
- `chat.css` — `.chat-welcome-item:hover` box-shadow updated to `var(--bezel-shadow-mini)`.
- All temporary variant scaffolding REMOVED.

**Iteration trail:**
1. 4 bezel styles (A/B/C/D) → operator picked top-left directional from C; flagged that A and B were too similar (soft glows underweight) and D had spread without edge.
2. 4 top-left intensities (C1/C2/C3/C4) → operator picked C4's stacked-depth structure but flagged contrast as too high.
3. C4 structure × C1/C2 alphas (S1/S2/S3) → operator picked S3. Committed as `--bezel-shadow`.
4. 4 panel-radius values (R1=2/R2=6/R3=10/R4=14) → operator picked R2 (6px).

**Notes:**
- `--panel-radius-sm` (6px) now matches `--panel-radius` after the R2 retune. Both tokens preserved as separate slots so operator can later reduce `-sm` if a size hierarchy is needed.
- Both themes use the same bezel alphas — white/black inset shadows read appropriately against both glass palettes (violet-accent dark + slate-chrome light). Light-theme-specific bezel retune deferred unless HAT surfaces a need.

**Final verification (after pullback retune):**
- Narrow test gate: `56 passed in 0.93s` (Flight 1 baseline preserved).
- WCAG audit subset: 33 parametrizations passed.
- `grep -rn 'bezel-variant\|corner-variant\|pullback-variant\|ITERATION \|PULLBACK'` → 0 hits.

**Post-close back-track (pullback iteration):**
After Leg 04 closed with the S3 bezel + R2 corners, operator surveyed the cumulative result and reported "we went a little hard on the bevel, the background color is overly frosted." Re-opened a single retune iteration with 3 simultaneous-axis variants (P1 ~20% / P2 ~40% / P3 ~60% pullback on BOTH glass and bezel). Operator picked P2. Retuned tokens:
- Glass: blur 20px → 12px, saturate 160%/140% → 130% in both themes; bg alpha dropped (dark 0.06 → 0.04, light 0.25 → 0.15); gleam alphas reduced by ~40%.
- Bezel: dropped the 10px outer glow entirely, lowered edge alphas (35%/30% → 22%/18%) and 4px inner-glow alphas (12%/14% → 7%/9%).
- Leg 04 artifact's Iteration Trail + Final Token Values updated; status remained `landed`.

---

### 05-indicators-and-motion

**Type**: interactive vibe leg (operator-driven, 3 iterations on LEDs + 1 telemetry layout pick + 1 motion-asymmetry refinement).

**Changes made (file-level):**
- `tokens.css` — added 3 motion tokens (`--ease-tactile`, `--motion-fast: 150ms`, `--motion-base: 250ms`) to both themes; added `@media (prefers-reduced-motion: reduce)` block at the top of the fallback section, overriding both durations to 0ms in each theme.
- `components.css` — added canonical `.indicator-led` primitive (10px round dot with stacked radial-gradient highlights: white top-left crescent + black bottom-right shadow) with status modifiers `.indicator-led--success/warning/danger/idle`. Added `::before` retrofit on `.test-result-ok/fail/warning/pending` so the existing connection-test markup picks up the LED automatically (provider editor, agent editor, tool editor all retrofitted with zero JS changes). Changed `.test-result` to `display: inline-flex; gap: 6px` to position the LED before the text. Retuned `.entity-tile` transition to use motion tokens with asymmetric in/out timing.
- `admin.css` — added gallery-scoped `.telemetry-strip` + `.telemetry-value` rules (T1 layout: justified row with bottom-border, mono-uppercase value).
- `status-section.js` — gallery samples added for `.indicator-led` (across all 4 status states) and `.telemetry-strip` (3 rows: SYSTEM/AGENTS/MCP).
- All temporary variant scaffolding REMOVED.

**Iteration trail:**
1. LED visual style (A/B/C/D) → operator picked D direction; A/B/C too similar at 8px.
2. Reflective-crescent D variants (D1/D2/D3/D4) → operator picked D2 + requested bottom-right shadow. Committed.
3. Telemetry layouts (T1/T2/T3) → operator picked T1 (justified). Gallery-only.
4. Motion tokens — Material standard easing + 150ms/250ms starter → operator asked for slower mouse-out. Implemented asymmetric (fast in via `:hover` rule, slow out via base rule).

**Deferred to Leg 06 HAT:**
- LED application to OAuth status surfaces (not a `.test-result-*` consumer; needs explicit markup wire-up)
- LED application to MCP source connection state (Studio MCP grid; needs explicit markup wire-up)

**Notes:**
- Telemetry-strip stays gallery-only per flight design (graduates only if a downstream polish flight finds a real consumer).
- Motion tokens are theme-agnostic — values defined identically in both `[data-theme="dark"]` and `[data-theme="light"]` blocks for token-naming consistency.
- Asymmetric transition pattern (fast-in on `:hover`, slow-out on base rule) is a useful idiom — could be canonized in the Leg 06 affordance-patterns codification.

**Final verification:**
- Narrow test gate: `56 passed in 0.90s` (Flight 1 baseline preserved).
- WCAG audit subset: 33 parametrizations passed.
- `grep -rn 'indicator-led-variant\|telemetry-strip-t1\|telemetry-strip-t2\|telemetry-strip-t3\|ITERATION \|TELEMETRY STRIP'` → 0 hits.

**Interactive primitives pass (operator surfaced gap — buttons, fields, checkboxes, app-picker, chips were not yet carrying the aesthetic):**
- Buttons: long iteration cycle (B/V/Aqua-classic/Aqua-soft/Aqua-ref-pill/F/bounce/body-darkening) → operator pulled back from Aqua rabbit hole, reverted to V3b. Final canonical button-family treatment: V3 white→fade→dark gradient + `--glass-border` + `--bezel-shadow-mini` + asymmetric in/out motion, applied to `.btn-outlined-primary`, `.btn-filled-primary` (with solid accent + outer accent-glow halo), `.btn-muted-destructive` (destructive tones), `.app-picker-button`.
- Fields: `.field-input/.field-textarea/.field-select` get `--bezel-shadow-inset` (recessed). Focus stacks inset with accent-glow.
- Native `<select>` options: surface-elevated + hover + checked styled within native limits. **Mission Known Issue logged**: rounded-corner popup chrome unstylable in pure CSS — defer custom dropdown component to a future polish flight.
- `.checkbox-primary`: 14→16px, kept 1.5px border, no border-radius, no inset gradient on checked, `vertical-align: middle`, checkmark repositioned for proper centering.
- `.chip`: accent-translucent base + `--glass-border` (colored flat).
- Added `--bezel-shadow-inset` token (with reduced-transparency fallback).
- Bug fix: removed redundant `overflow-y: auto` on `.design-language-sections` (caused nested scrollbars on the gallery page — `.admin-content` already handles page-level scroll).

---

### Topbar deferral

**Context**: Flight design listed topbar as in-scope chrome for glass.

**Decision**: Defer. Topbar is the chrome boundary at the top of the viewport; nothing behind it to refract via backdrop-filter. Dark theme topbar already matches body bg. Light theme topbar is intentionally dark navy as chrome.

**Impact**: HAT in Leg 06 will flag if it reads inconsistent. If needed, apply gleam-only treatment without backdrop-filter.

---

## Deviations

*(departures from planned approach — populated during execution)*

---

## Anomalies

*(unexpected issues encountered — populated during execution)*

---

## Session Notes

*(chronological notes from work sessions)*

### Flight Director Notes

**Phase 1 — Context loading**
- Loaded phase file from `.flightops/agent-crews/leg-execution.md` (project-side, well-formed: Crew/Interaction-Protocol/Prompts sections all present with fenced prompt blocks).
- Crew: Developer (Sonnet) for design-review + implement + fix; Reviewer (Haiku) for review; optional Accessibility Reviewer (Sonnet) for UI legs.

**Phase 2 / Leg 01 — design**
- Designed leg 01 (`gallery-scaffold`) following the SKILL.md workflow: enumerated scope (server endpoint + boot-block + admin gating + container module), wrote acceptance criteria with binary verifications, mechanically verified 12 code-location citations against branch `flight/02-design-language` base `17c63e3`.
- Spawned Developer for design-review (Sonnet, action=review-leg-design).
- Review surfaced 1 high (`/api/info` stale-version inconsistency at `app.py:921`), 2 medium (`docker-compose.yml:55` dev-mode default inverted in verification steps; Makefile `verify-serving` enumerates admin sub-modules and needs `design-language-page.js`), 2 low (Context conflated `init()`+`hydrateState` closures; defensive default on success path), 4 suggestions.
- Incorporated:
  - High: opportunistically rewrote `/api/info` to use `__version__` per Flight 1 debrief encouragement; added `from the_one import __version__` to `app.py` imports.
  - Medium: corrected env-default framing throughout verification steps; added `Makefile` `verify-serving` loop update to scope; abandoned `.gitkeep` (project doesn't use that convention) — empty subdirectory deferred to Leg 02.
  - Low: split Context bullets by closure; added defensive `(config && typeof config === 'object')` check on success path.
  - Suggestions: added hashchange-post-boot edge case note; added `/api/info` legacy-parallel framing in Inputs.
- Skipped second design-review cycle: all changes are targeted/cosmetic fixes per the SKILL.md "Skip if only minor/cosmetic fixes were applied" guidance. The high finding was acted on opportunistically rather than requiring spec rework.
- Leg 01 status set to `ready`.

**Phase 2 / Leg 02 — design**
- Designed leg 02 (`vocabulary-inventory`) following the SKILL.md workflow: 9 gallery section modules + container update + `.checkbox-primary` primitive lift + Makefile/index.html plumbing. Wrote acceptance criteria, mechanically verified initial 11 code-location citations.
- Spawned Developer for design-review (Sonnet, action=review-leg-design). First pass returned `needs rework` — 3 high (would-runtime-fail issues): wrong `App.tabs` API surface (no `.wire` method), wrong `App.confirmDialog` option keys (`confirmLabel` → silently ignored, `confirmText` is the canonical name), markdown re-implementation conflicts with `App.markdown.render` canonical helper. Plus 4 medium: iOS-toggle DOM template missing, `.empty-canvas` requires flex parent, studio.css line range drift, `App.markdown.render` already provides the structure.
- Incorporated all 3 high + 4 medium fixes: pinned `App.tabs(tablistEl, panelsEl, opts)` signature with `initial`/`onChange` per `tabs.js:38`; pinned `confirmText`/`cancelText` and dropped click-outside-to-dismiss per `dialog.js:11, :82-83, :203-211`; rewrote markdown-section to compose `App.markdown.render` and `host.appendChild` the returned DocumentFragment per `message-bubble.js:28`; spelled out iOS-toggle DOM template from `tools-grid.js:67-72`; added flex parent guidance for `.empty-canvas`; corrected studio.css lift target to `:171-209`. Added Citation Audit entries for `tabs.js`, `dialog.js`, `markdown.js`, `tools-grid.js`, `components.css:363-371` flex-parent contract. Also flipped flight-level `// section-title` vs `.telemetry-strip` Open Question to `[x]` per Reviewer suggestion.
- Spawned Developer for second design-review pass. Returned `approve with changes` — 2 small follow-ups: iOS-toggle CSS override (`position: static` in the gallery scope) needed explicit pinning rather than prose-only guidance; studio.css line range internal inconsistency between Outputs and Step-2/Citation-Audit sections.
- Incorporated both follow-ups inline: added concrete `.area-admin .design-language-toggle-sample .tool-enable-switch { position: static; }` override in the admin.css Step-6 block + reshaped surfaces-section iOS-toggle sample to wrap two states in a single `.design-language-toggle-sample` container; reconciled studio.css line numbers (`:171-209`) across Outputs, Step 2, and Citation Audit.
- Did NOT spawn a third design-review cycle: SKILL.md caps at 2 design-review cycles; the second pass explicitly recommended "auto-fix recommendation for the Developer" on both follow-ups as small enough to absorb without another review. All corrections applied are surgical (line-number and CSS-rule edits).
- Leg 02 status set to `ready`.

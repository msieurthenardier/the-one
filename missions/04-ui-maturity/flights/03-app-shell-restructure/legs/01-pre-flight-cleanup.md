# Leg: 01-pre-flight-cleanup

**Status**: completed
**Flight**: [App Shell Restructure](../flight.md)

## Objective

Land the F2 debrief immediate-action items so F3's structural restructure builds on a clean baseline: deepen `--fg-muted` (dark) into the body-AA test set, replace the placeholder `--sidebar-bg: transparent`, lift the theme toggle out of `admin.js` into a reusable `App.theme.renderToggle()` with multi-mount sync, document the affordance vocabulary in `agents.md`, and add `// TODO(a11y-keyboard)` markers at the six keyboard-debt sites that legs 02 and 03 will address.

## Context

This leg is the F3 pre-work consolidation. Its content is dictated entirely by the F2 flight debrief's "immediate actions" section — none of it is structural F3 work, but landing it first means subsequent legs do not have to weave around stale F2 artifacts.

Key carry-forward decisions from the flight spec:

- **`--fg-muted` (dark)** must be tightened into the a11y body-AA parametrize set (tests deepen body coverage). Token already exists at `tokens.css:38` (`#a8a8a8`); just adds the test pairs.
- **`--sidebar-bg: transparent` (dark)** is a pre-realization placeholder. Replace with a declarative value — `var(--bg)` is the cleanest match (the dark sidebar should read as body bg, not as see-through).
- **Theme toggle lift** preserves the radio-group accessibility (`role="radiogroup"`, `aria-checked`, `aria-labelledby`, arrow-key navigation) currently embedded in `admin.js:208-270`. The new API takes `(container, options?)` where `options.variant` is `'full'` (current Light/Dark/Auto labels) or `'compact'` (icon-only — for the leg-02 top-bar mount). Multi-mount sync uses a `CustomEvent('theme-preference-changed', {detail: {pref}})` dispatched from `App.theme.set()` and subscribed by every `renderToggle` instance.
- **Affordance vocabulary** lands as a NEW `### Affordance patterns` subsection in `agents.md` "Design system" section, parallel to the existing `### Color contrast (WCAG AA)` and `### Typography scale` subsections (NOT buried inside one of them). Six patterns are documented: info banner, outlined-cyan, filled-cyan CTA, muted-default-then-glow destructive, neutral utility, palette-island rule.
- **Keyboard-debt markers** are single-line `// TODO(a11y-keyboard): convert to <button>` comments at the six debt sites — they do not modify behavior, only mark intent for legs 02-03.

## Inputs

State that must exist before this leg runs:

- Branch `flight/03-app-shell-restructure` checked out (created from `main` post-F2 merge `730b4f3`).
- F2 baseline tests passing: `pytest tests/` ≥ 391, `pytest -m browser tests/browser/` ≥ 20.
- F2 source files present: `tokens.css` with realized dark + light themes; `theme.js` exposing `App.theme.{get,resolved,set}`; `admin.js` with embedded theme toggle at lines 208-270; `tests/test_design_tokens_a11y.py` with the existing parametrize sets; `the_one/agents.md` with the existing Design system subsections.
- **Pre-existing working-tree state**: at leg start the branch has TWO modified flight artifacts (`missions/04-ui-maturity/flights/03-app-shell-restructure/flight.md` and `flight-log.md`) and a partially-untracked `legs/` directory containing this leg artifact. These are F3 orchestration artifacts NOT to be reverted. Per F3 batching, they will be staged + committed alongside leg 04's implementation in the batch commit (legs 01-04 share one commit per the agentic-workflow protocol).
- The six keyboard-debt sites and the new-chat marker site (per flight spec, line numbers verified against current source):
  - `the_one/interfaces/web/static/js/areas/chat.js:23` — `'<button class="new-chat">+ new</button>' +` inside the `sidebar.innerHTML` template literal at lines 18-26 (NEW-CHAT marker site for leg 05).
  - `the_one/interfaces/web/static/js/areas/chat.js:128` — `var el = document.createElement('div'); el.className = 'session-item' + ...`
  - `the_one/interfaces/web/static/js/areas/chat.js:147` — `var delBtn = document.createElement('span'); delBtn.className = 'delete';`
  - `the_one/interfaces/web/static/js/areas/studio.js:89` — `var el = document.createElement('div'); el.className = 'agent-item' + ...`
  - `the_one/interfaces/web/static/js/areas/studio.js:99` — `var delBtn = document.createElement('span'); delBtn.className = 'agent-item-delete';`
  - `the_one/interfaces/web/static/js/areas/studio.js:286` AND `:296` — template-literal `<span class="chip-remove">…</span>` embeds in the MCP-source and knowledge-base chip loops (same function).
  - `the_one/interfaces/web/static/js/areas/studio.js:517` — `chip.innerHTML = ... + '<span class="chip-remove">' + ... + '</span>';` inside `wireEditorEvents` (DIFFERENT code path — needs its own marker).
  - `the_one/interfaces/web/static/js/areas/admin.js:93` — `var el = document.createElement('div'); el.className = 'admin-category-item' + ...`

## Outputs

State that must exist after this leg completes:

- **`tests/test_design_tokens_a11y.py`** — `test_body_text_passes_aa` parametrize set has two new dark pairs: `("dark", "fg_muted", "bg")` and `("dark", "fg_muted", "surface")`. Total parametrized body-AA cases: 12 (was 10). Test count overall: 393 passing (was 391).
- **`tests/browser/design_tokens.py`** — `DARK` dict already includes `fg_muted` (verify; if not, add). LIGHT already exercises `fg_muted` in large/UI tests — the dark addition makes the coverage symmetric.
- **`the_one/interfaces/web/static/css/tokens.css:99`** — `--sidebar-bg: transparent;` replaced with `--sidebar-bg: var(--bg);` (the dark-theme block; light's `--sidebar-bg: #cbd5e1` at line 192 stays).
- **`the_one/interfaces/web/static/js/theme.js`** — `App.theme.renderToggle(container, options?)` added, exposing the radio-group widget. `App.theme.set()` extended to dispatch `CustomEvent('theme-preference-changed', {detail: {pref}})` on `document` after applying. `renderToggle` instances subscribe to that event on creation and update their own `aria-checked`/`tabindex`/`.active` state on receipt.
- **`the_one/interfaces/web/static/js/areas/admin.js`** — the entire `themeOption` HTML block + `selectThemeOption` + click/keydown handlers (lines ~210-270) replaced by a single call: `App.theme.renderToggle(themeToggleContainerEl, {variant: 'full'})`. The `<div class="admin-theme-toggle" role="radiogroup" aria-labelledby="admin-appearance-heading">…</div>` shell stays in the surrounding admin form HTML; only its inner buttons + handlers move into `theme.js`. Net `admin.js` size: ~70 LOC smaller.
- **`the_one/interfaces/web/static/css/admin.css`** — `.admin-theme-toggle` and `.admin-theme-option` rules unchanged (CSS already defines the radio-group styling; the JS move does not touch CSS).
- **`the_one/agents.md`** — new `### Affordance patterns` subsection added under the existing "Design system" section (placement: between `### Color contrast (WCAG AA)` and `### Typography scale`, OR after `### Theme switching contract` — whichever maintains alphabetical/logical flow; the existing order is contrast → typography → icons → theme so insert "Affordance patterns" before `### Color contrast` so the design-vocabulary lands first; either order is acceptable).
- **Marker comments** at the six keyboard-debt sites: each gets a single `// TODO(a11y-keyboard): convert to <button>` line ABOVE the offending DOM creation, plus a `// TODO(a11y-keyboard): new-chat-flow restructure` marker at `chat.js:29` (the `+ new` button setup) for leg 05.
- **`the_one/agents.md`** browser-testing section updated with the Lucide release-tag quirk and Playwright `color_scheme="no-preference"` quirk (per flight spec — concrete content per F2 debrief).
- All existing tests still pass: `pytest tests/` reports 393 passing (391 + 2 new dark `--fg-muted` pairs).
- **Browser snapshots: dark-theme sidebar baselines are expected to drift** because the body paints `var(--bg-gradient)` (a navy→near-black `linear-gradient` per `tokens.css:84`) and the sidebar previously showed `transparent` (gradient bleed-through). Switching to a solid `var(--bg) = #0a0a0a` removes the bleed, which is a real visual change. The dark snapshots that include the sidebar region (`chat-empty-dark`, `chat-with-messages-dark`, `studio-empty-dark`, `studio-with-agent-dark`, `admin-empty-dark`, `admin-with-provider-dark`) MUST be regenerated and the new baselines committed as part of this leg. Light theme snapshots are unaffected (light `--sidebar-bg: #cbd5e1` was already declarative). After regeneration, expect 20 passing total (12 baselines retuned but the test count is unchanged).

## Acceptance Criteria

- [x] `tests/test_design_tokens_a11y.py` includes two new parametrize entries: `("dark", "fg_muted", "bg")` and `("dark", "fg_muted", "surface")` in the `test_body_text_passes_aa` parametrize set.
- [x] `tests/browser/design_tokens.py` `DARK` dict contains the `fg_muted` key with value `"#a8a8a8"` (matching `tokens.css:38`).
- [x] `tokens.css` dark block declares `--sidebar-bg: var(--bg);` (no occurrence of `--sidebar-bg: transparent` remains in the file).
- [x] `App.theme.renderToggle(container, options)` is exported from `theme.js` and renders the radio-group widget into `container`. `options.variant` accepts `'full'` and `'compact'`. `'compact'` defaults to icon-only (one icon button cycling Light → Dark → Auto, OR a single icon-only segmented control — implementation detail; documented in code comments).
- [x] `App.theme.set()` dispatches `CustomEvent('theme-preference-changed', {detail: {pref}})` on `document` after applying the preference.
- [x] Each `renderToggle` instance subscribes to `theme-preference-changed` on creation and updates its DOM (active class, `aria-checked`, `tabindex`) on receipt. **Verification is manual at leg 01** (browser console: mount a second toggle via `App.theme.renderToggle(document.body, {variant: 'compact'})`, click the admin one, confirm the second updates without click). Automated coverage lands in leg 02 (top-bar mounting) where two toggle instances naturally co-exist on the page; a Playwright test in leg 02 will assert sync between the admin-page toggle and the top-bar compact toggle. Document this deferral in the flight log.
- [x] `admin.js` `renderSystemPanel()` calls `App.theme.renderToggle(themeToggleEl, {variant: 'full'})` instead of inlining the toggle. `admin.js` net LOC reduction is ~70 lines (toggle code + handlers removed).
- [x] The Settings page (admin → System) still renders the theme toggle correctly, and clicking/arrow-keying through it still sets the preference and updates `data-theme`.
- [x] `the_one/agents.md` contains a new `### Affordance patterns` subsection with six documented patterns: info banner, outlined-cyan, filled-cyan CTA, muted-default-then-glow destructive, neutral utility, palette-island rule. Each pattern names where it is used and (where applicable) the token(s) it composes.
- [x] `the_one/agents.md` browser-testing section documents the Lucide release-tag pinning convention (`v0.265.0`) and the Playwright `color_scheme="no-preference"` quirk (browser tests must not inherit OS preference; the fixture pins it).
- [x] All eight marker sites are commented as specified in Implementation Guidance step 6: chat.js (3 markers — line 23 new-chat, line 128 session-item, line 147 .delete), studio.js (4 markers — line 89 agent-item, line 99 agent-item-delete, line 286 chip-remove pair-marker for `:286/:296`, line 517 chip-remove in wireEditorEvents), admin.js (1 marker — line 93 admin-category-item). `grep -rn "TODO(a11y-keyboard)" the_one/interfaces/web/static/js/areas/` returns 8 hits.
- [x] `pytest tests/` reports 393 passing, 0 failing.
- [x] `pytest -m browser tests/browser/` reports 20 passing, 0 failing — but the **dark snapshot baselines** for `chat-empty-dark`, `chat-with-messages-dark`, `studio-empty-dark`, `studio-with-agent-dark`, `admin-empty-dark`, and `admin-with-provider-dark` are **regenerated** and the new PNGs committed. (Six baselines retuned; light baselines unchanged.) Verify by running with `--snapshot-update` once, then re-running without to confirm clean.

## Verification Steps

- Run `pytest tests/test_design_tokens_a11y.py -v` — confirm the two new dark `--fg-muted` parametrize cases pass (each ratio should be ≥ 4.5:1; `#a8a8a8` on `#0a0a0a` is ~10.4:1, on `#1a1a1a` is ~7.8:1).
- Run `pytest tests/` — confirm overall count is 393 passing.
- Run `pytest -m browser tests/browser/ --snapshot-update` once to regenerate the six dark baselines drifted by the sidebar-bg swap (the body's navy→near-black `--bg-gradient` was previously bleeding through `transparent`; the swap to solid `var(--bg)` removes the gradient bleed in the sidebar region). Re-run without `--snapshot-update` to confirm 20 passing on the new baselines.
- `grep -n "transparent" the_one/interfaces/web/static/css/tokens.css` — should return zero hits for `--sidebar-bg`.
- `grep -n "renderToggle" the_one/interfaces/web/static/js/theme.js the_one/interfaces/web/static/js/areas/admin.js` — confirms the API is defined in `theme.js` and called from `admin.js`.
- Manually open `the-one` in a browser, navigate to admin → System, click the theme toggle. Confirm: (a) DOM updates `data-theme`, (b) localStorage updates `theme-preference`, (c) the active option's `aria-checked` flips correctly. Then mount a second toggle in the browser console (`App.theme.renderToggle(document.body, {variant: 'compact'})`), click one, confirm the other updates without click — multi-mount sync verified.
- `grep -rn "TODO(a11y-keyboard)" the_one/interfaces/web/static/js/areas/` — should return **eight** hits (six keyboard-debt + one new-chat marker + one extra chip-remove marker for the wireEditorEvents site).
- `grep -A 2 "### Affordance patterns" the_one/agents.md` — confirms the new subsection exists.

## Implementation Guidance

1. **Add the dark-theme `--fg-muted` body-AA test pairs**

   Open `tests/test_design_tokens_a11y.py`. Locate the `test_body_text_passes_aa` parametrize at line 79. The current dark entries are `("dark", "fg", "bg")`, `("dark", "fg", "surface")`, `("dark", "fg_secondary", "bg")`, `("dark", "fg_secondary", "surface")`.

   Add immediately after the dark `fg_secondary` entries:
   ```python
       # --fg-muted (dark) #a8a8a8 — promoted to body-AA per F2 debrief.
       ("dark", "fg_muted", "bg"),
       ("dark", "fg_muted", "surface"),
   ```

   Confirm `tests/browser/design_tokens.py` `DARK` dict already has the `fg_muted` key; if missing, add `"fg_muted": "#a8a8a8"`.

2. **Replace `--sidebar-bg: transparent` in dark tokens**

   `tokens.css:99` (in the `[data-theme="dark"]` block, the last token in the file's dark section) currently reads:
   ```css
       --sidebar-bg: transparent;
   ```
   The current comment block at lines 90-92 reads:
   ```css
       /* nav rail palette — same as body in dark; sidebar shows the body
          gradient through (transparent) for the original layered feel. */
   ```

   Make TWO edits:

   **Edit A** — replace the value:
   ```css
       --sidebar-bg: var(--bg);
   ```

   **Edit B** — split the misleading combined comment into two separate, accurate comments. The block at lines 90-99 should look like this after the edit:
   ```css
       /* nav rail palette — chrome surface; same as body in dark so the rail
          reads as a non-elevated edge. */
       --nav-bg: var(--bg);
       --nav-bg-active: var(--surface);
       --nav-border: var(--border);
       --nav-fg: var(--fg-secondary);
       --nav-fg-hover: var(--fg);
       --nav-fg-active: var(--accent);

       /* Sidebar reads as body bg in dark (declarative; previously `transparent`
          which let the body gradient bleed through — replaced for snapshot
          stability and explicit intent). Light theme uses #cbd5e1 (slate-300). */
       --sidebar-bg: var(--bg);
   ```

   The conflated "nav rail/sidebar/transparency" comment is split: the nav-rail comment now describes the chrome treatment honestly, and the sidebar gets its own comment explaining the value choice and what it replaced.

   Verify nothing else in `base.css`, `chat.css`, `studio.css`, `admin.css` depends on `--sidebar-bg` being `transparent`. If a rule explicitly relies on transparency (e.g., a parent gradient bleeding through), pin a different solution — but the F2 debrief diagnosed this as a leftover, so most likely it is safe.

3. **Add `App.theme.renderToggle()` and the multi-mount sync event**

   Open `the_one/interfaces/web/static/js/theme.js`. Inside the IIFE, after the existing public API definition (line 71-87):

   - Define the event channel: `var THEME_EVENT = 'theme-preference-changed';`.
   - In `App.theme.set`, after the `reapply()` call, dispatch:
     ```javascript
     document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { pref: pref } }));
     ```
   - Add `App.theme.renderToggle(container, options)`:
     ```javascript
     window.App.theme.renderToggle = function (container, options) {
       options = options || {};
       var variant = options.variant === 'compact' ? 'compact' : 'full';
       // Build the radio-group DOM (reuse the existing admin.js logic verbatim,
       // parameterized by variant; for 'full', emit Light/Dark/Auto labels;
       // for 'compact', emit a single icon-only button that cycles).
       // ... (full implementation below)
       // Subscribe to the theme-preference-changed event for multi-mount sync.
       document.addEventListener(THEME_EVENT, function (e) {
         updateActiveOption(e.detail.pref);
       });
     };
     ```

     For the `'full'` variant, lift the exact HTML/handler logic from `admin.js:208-270` — preserving ALL accessibility attributes:
     - `<div role="radiogroup" aria-labelledby="...">` — the `aria-labelledby` value is passed in via `options.labelledBy` (caller supplies the heading id; falls back to omitting the attribute if not provided).
     - Each option button: `role="radio"`, `aria-checked`, `tabindex` (active=`0`, others=`-1`), `data-theme-pref`.
     - Click handler that calls `selectThemeOption(btn)`.
     - Keydown handler for ArrowLeft/Right/Up/Down that cycles among options.
     Adjust to:
     - Read the current pref from `getPreference()` (already in scope).
     - Use `App.theme.set(pref)` to commit changes (which now dispatches the event).
     - On event receipt (the subscriber), update the active option without re-firing `App.theme.set` (else infinite loop). Use a local `updateActiveOption(pref)` that flips the `.active` class, `aria-checked`, and `tabindex` based on the incoming pref.
     - **Listener cleanup**: cache the subscriber function in a closure and store the reference on the container (`container._themeListenerCleanup = ...`). The current admin SPA does not unmount the System panel (it `innerHTML`-replaces the content), so listeners would leak across visits. Land a `MutationObserver`-free fix: at the START of `renderToggle`, call any prior `container._themeListenerCleanup` if present, then wire the new listener and store its cleanup. This handles re-renders cleanly.
     - For `'compact'`, the icon catalog (`App.icons`) does NOT currently include sun/moon/monitor. Land the MVP with text fallback: a single `<button class="theme-toggle-compact">` whose displayed letter shows the CURRENT PREFERENCE (`L` for light, `D` for dark, `A` for auto — three letters, three states; not the resolved mode, since "auto" must be visually distinguishable from a forced light/dark to give clicking feedback). Click cycles preference: light → dark → auto → light. Subscribes to `theme-preference-changed` like the full variant.
       - **ARIA contract**: the button carries `aria-label="Toggle theme; current: Light"` (substituting Light/Dark/Auto based on `App.theme.get()`); the label is updated whenever `updateActiveOption(pref)` fires. No `role="radio"` and no radiogroup wrapper — that semantics belongs to the full variant only. The compact button is a plain `<button>` (default `role="button"`).
       - Leg 02 may swap the letter labels for proper Lucide icons (sun/moon/monitor) if it adds them to `icons.js`; the ARIA-label contract stays. Document this expected revision in a code comment above the compact-variant block so leg 02's design review sees the swap as planned, not surprising.

4. **Replace `admin.js`'s embedded toggle with the `renderToggle` call**

   In `admin.js`, locate `renderSystemPanel()` at line 208. Find the inner `<div class="admin-theme-toggle" role="radiogroup" aria-labelledby="admin-appearance-heading">…</div>` block (lines 224-228). Keep the outer Appearance section structure (heading, paragraph, container `<div>`), but make the toggle container empty in the initial template:
   ```javascript
   '<div class="admin-theme-toggle" id="admin-theme-toggle-mount" aria-labelledby="admin-appearance-heading"></div>'
   ```
   (Drop the inline `themeOption` calls from the template string.)

   After the `contentEl.innerHTML = '...'` assignment, remove the entire block from `var themeToggle = contentEl.querySelector('.admin-theme-toggle')` down through the final `themeToggle.addEventListener('keydown', ...)` (lines ~244-270). Replace with:
   ```javascript
   var themeToggleEl = contentEl.querySelector('#admin-theme-toggle-mount');
   if (window.App && window.App.theme && window.App.theme.renderToggle) {
     window.App.theme.renderToggle(themeToggleEl, { variant: 'full' });
   }
   ```

   Net `admin.js` size reduction: ~62 lines (the LOC range 244-270 is 27 lines; plus the inner template string lines ~210-228 is ~18 lines after preserving the heading/paragraph; conservative estimate ~45-70 lines saved). The LOC count is descriptive, not load-bearing — verify via `wc -l admin.js` before and after.

5. **Document the affordance patterns in `agents.md`**

   In `the_one/agents.md`, locate the "Design system" section (the section that contains `### Color contrast (WCAG AA)` at line 185). Add a new subsection IMMEDIATELY BEFORE `### Color contrast (WCAG AA)` (rationale: vocabulary lands first, then specifics).

   **Note on intent**: this vocabulary is partly normative (the rule for future work) and partly descriptive of current usage. Where current implementations diverge from the documented pattern (info-banner currently uses `var(--surface)` not `var(--surface-elevated)` in `.admin-note`; the `+ new` button is currently outlined-cyan rather than the neutral-utility example originally proposed), the document calls out the divergence so the next reader does not over-trust either reading. The convention going forward: NEW code follows the documented patterns; existing divergences are pre-realization debt to be resolved during the per-area alignment flights (F4-F6).

   ```markdown
   ### Affordance patterns

   The interface uses six recurring affordance patterns. Each is identifiable by its visual treatment and intended interaction class. New UI work should compose with these patterns rather than invent parallel idioms. Where the live UI diverges from these descriptions today, the divergence is pre-realization debt to be resolved during the per-area alignment flights (F4 Chat / F5 Studio / F6 Administration).

   1. **Info banner** — neutral disclosure inside a surface. Documented pattern: background `var(--surface-elevated)`, border `1px solid var(--border)`, text `var(--fg-secondary)`. Live UI today: `.admin-note` uses `var(--surface)` and the `.chat-no-providers` banner uses a cyan-accented gradient — both are pre-realization variants. Used at the top of provider lists, agent editors, and admin sub-pages to surface non-actionable context.

   2. **Outlined-cyan** — secondary action; reads as available but de-emphasized. Pattern: background transparent, border `1px solid var(--accent)`, text `var(--accent)`, hover background `var(--accent-translucent)`. Live UI today: `.new-chat` (chat sidebar's "+ new" button), `.new-agent-btn` (studio sidebar). Future use: "edit", "configure", and similar non-CTA actions across all areas.

   3. **Filled-cyan CTA** — primary action; reads as the recommended next step. Pattern: background `var(--accent)`, text `var(--fg-on-accent)`, hover via `filter: brightness(1.1)` or explicit hover token. Used for "save", "submit", "create" — one CTA per page is the convention.

   4. **Muted-default-then-glow destructive** — irreversible action; reads as recessive at idle, glows on focus/confirm. Pattern: transparent background at idle, text/border `var(--status-danger-muted)`. Confirm state (after first click): background `var(--status-danger)`, text `var(--fg-on-danger)`, glow `var(--status-danger-glow)`. Used for delete affordances on session items, agent items, chip-removes. Never used for routine actions.

   5. **Neutral utility** — small, non-categorical action with no surrounding chrome. Pattern: background transparent, text `var(--fg-secondary)`, hover text `var(--fg)`, no border. Examples: inline `x` icon buttons, dropdown-chevron indicators, decorative scroll affordances. NOT for "+ new" buttons (those are outlined-cyan, pattern 2).

   6. **Palette-island rule** — components that establish their own chrome (the nav rail, the top bar arriving in F3 leg 02) declare their own `--nav-*` (or topbar-equivalent) palette family in `tokens.css`. The body palette and the chrome palette MUST NOT share token names. Rule: never reach into chrome tokens from body components or vice versa.
   ```

   In the same `agents.md` browser-testing section (find by searching for the existing Visual snapshot regression net subsection or similar), append two short notes:
   ```markdown
   - **Lucide icon pin**: icons are pinned to `lucide-icons/lucide@v0.265.0`. Adding new icons requires fetching from this exact tag — do NOT pull from `main` or `latest`. The pin is what keeps `tests/browser/__snapshots__/` baselines stable.
   - **Playwright `color_scheme`**: browser tests pin `color_scheme="no-preference"` so they don't inherit the host OS theme preference. Without this, a CI environment with `prefers-color-scheme: dark` would resolve `auto` to `dark` and produce a different snapshot than a developer's light-mode laptop.
   ```

6. **Add `// TODO(a11y-keyboard)` markers**

   For each of the eight sites listed below, insert a single-line comment immediately above the line indicated. These are non-behavioral; they signal intent for legs 02-03-05. (Note: line numbers may shift slightly during this leg because step 1 adds two parametrize entries to a Python file, but the JS files are untouched until step 6 — so JS line numbers stay stable through the marker insertion within step 6 itself, processed top-to-bottom.)

   - **`chat.js:23`** — above the `'<button class="new-chat">+ new</button>' +` line within the `sidebar.innerHTML` block (lines 18-26). Insert above line 23 within the template literal as a JS line break (this means breaking the `+` chain):
     ```javascript
     '<div class="sidebar-actions">' +
       '<select class="agent-select"><option value="">default</option></select>' +
       // TODO(a11y-keyboard): new-chat-flow restructure (F3 leg 05)
       '<button class="new-chat">+ new</button>' +
     '</div>' +
     ```
     The marker sits as a JS comment between two string concatenations — JS tolerates this; the resulting HTML is unchanged.
   - **`chat.js:128`** — above `var el = document.createElement('div'); el.className = 'session-item' + ...`:
     ```javascript
     // TODO(a11y-keyboard): convert <div class="session-item"> to <button> (F3 leg 03)
     ```
   - **`chat.js:147`** — above `var delBtn = document.createElement('span'); delBtn.className = 'delete';`:
     ```javascript
     // TODO(a11y-keyboard): convert <span class="delete"> to <button> + :focus-within reveal (F3 leg 03)
     ```
   - **`studio.js:89`** — above `var el = document.createElement('div'); el.className = 'agent-item' + ...`:
     ```javascript
     // TODO(a11y-keyboard): convert <div class="agent-item"> to <button> (F3 leg 03)
     ```
   - **`studio.js:99`** — above `var delBtn = document.createElement('span'); delBtn.className = 'agent-item-delete';`:
     ```javascript
     // TODO(a11y-keyboard): convert <span class="agent-item-delete"> to <button> + :focus-within reveal (F3 leg 03)
     ```
   - **`studio.js:286` AND `:296`** (two adjacent chip-remove sites in the MCP-sources and knowledge-bases template-literal loops): add ONE marker immediately above line 286 (the marker covers both adjacent template-literal embeds in the same render function):
     ```javascript
     // TODO(a11y-keyboard): convert <span class="chip-remove"> to <button> (F3 leg 03; 2 sites here at :286/:296)
     ```
   - **`studio.js:517`** (third chip-remove site, in `wireEditorEvents` — different code path): add a SEPARATE marker immediately above line 517:
     ```javascript
     // TODO(a11y-keyboard): convert <span class="chip-remove"> to <button> (F3 leg 03; this site is in wireEditorEvents)
     ```
   - **`admin.js:93`** — above `var el = document.createElement('div'); el.className = 'admin-category-item' + ...`:
     ```javascript
     // TODO(a11y-keyboard): convert <div class="admin-category-item"> to <button> (F3 leg 03)
     ```

   **Total markers**: 8 (one new-chat + six keyboard-debt + one extra chip-remove site).

7. **Run the test suites and confirm clean**

   ```
   pytest tests/ --tb=short
   pytest -m browser tests/browser/ --tb=short
   ```

   Expected: 393 passing in unit suite, 20 passing in browser suite. If either fails, diagnose before signaling complete.

   For the browser suite specifically: the dark `--sidebar-bg: var(--bg)` change is visually equivalent to `transparent` over `var(--bg)`, so snapshots should match. If a baseline drifts, check whether the prior `transparent` was accidentally letting the body gradient bleed through — if so, document the drift in the flight log and regenerate that single baseline.

## Edge Cases

- **`renderToggle` event-loop**: subscribing the toggle to its own `theme-preference-changed` event creates a feedback risk (toggle calls `App.theme.set` → event fires → toggle's subscriber calls `updateActiveOption` → if `updateActiveOption` re-calls `App.theme.set`, infinite loop). Mitigation: `updateActiveOption` must update DOM only — never call `App.theme.set`.
- **Mounting `renderToggle` before `theme.js` loads**: `theme.js` runs synchronously before any area code (per the leading comment "Runs in <head> BEFORE any stylesheet load"). If `admin.js` calls `App.theme.renderToggle` and the function is `undefined`, the guard `if (window.App && window.App.theme && window.App.theme.renderToggle)` skips the mount silently. Document that this should never happen in practice (script order is enforced in `index.html`).
- **`'compact'` variant unused in leg 01**: leg 02 will be the first consumer. Land a working skeleton so leg 02's design review can audit it; do NOT punt the implementation entirely (leaving an empty branch in `renderToggle` would block leg 02's code review).
- **`agents.md` insertion point**: if "Design system" section structure has shifted since the flight spec was written, prefer alphabetical/conceptual order over rigid line numbers. The new subsection must be visible at the same heading level (`###`) as Color contrast / Typography scale / Icon catalog / Theme switching contract.
- **Snapshot tests for the dark sidebar swap**: confirmed at design review — the dark body paints `var(--bg-gradient)` (`tokens.css:84`) and the previously-`transparent` sidebar lets that gradient bleed through. The swap to solid `var(--bg) = #0a0a0a` IS a visual change in the upper-sidebar region. Six dark baselines must be regenerated (per Outputs section above). Light baselines unchanged.

## Files Affected

- `the_one/interfaces/web/static/js/theme.js` — Add `App.theme.renderToggle(container, options)` and `theme-preference-changed` event dispatch.
- `the_one/interfaces/web/static/js/areas/admin.js` — Replace embedded toggle (lines ~208-270) with `renderToggle` call. Net ~70 LOC reduction.
- `the_one/interfaces/web/static/js/areas/chat.js` — Add `// TODO(a11y-keyboard)` markers at lines 23 (new-chat), 128 (session-item), 147 (.delete).
- `the_one/interfaces/web/static/js/areas/studio.js` — Add `// TODO(a11y-keyboard)` markers at lines 89 (agent-item), 99 (.agent-item-delete), 286 (chip-remove pair covering :286/:296), and 517 (chip-remove in `wireEditorEvents`).
- `the_one/interfaces/web/static/css/tokens.css` — Replace `--sidebar-bg: transparent;` with `--sidebar-bg: var(--bg);` in dark block (line ~99).
- `tests/test_design_tokens_a11y.py` — Add two parametrize entries: `("dark", "fg_muted", "bg")` and `("dark", "fg_muted", "surface")`.
- `tests/browser/design_tokens.py` — Verify (and add if missing) `"fg_muted": "#a8a8a8"` in the `DARK` dict.
- `the_one/agents.md` — Add `### Affordance patterns` subsection (six patterns) and append Lucide pin / Playwright color-scheme notes to browser-testing section.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`pytest tests/` ≥ 393, `pytest -m browser tests/browser/` ≥ 20)
- [x] Flight log updated with leg outcomes (especially: any deviations, the actual `wc -l admin.js` reduction, any visual snapshot regenerations triggered by the sidebar-bg swap)
- [x] Leg status updated to `landed`
- [x] (Per F3 batching: do NOT commit yet — Flight Director batches commits across legs 01-04. Signal `[HANDOFF:review-needed]` only after the final leg in the batch.)

# Leg: 02-shared-components-lift

**Status**: completed
**Flight**: [Chat Restructure — Components, Streaming & Markdown](../flight.md)

## Objective

Consolidate the per-area CSS duplication into shared primitives in `components.css` (under `@layer components`) plus a small set of utility classes (under `@layer utilities`); migrate the JS template emit-sites in `chat.js`, `studio.js`, and `admin.js` to the new vocabulary; and replace the 19 inline `el.style.display = ...` setters in `admin.js` with utility-class toggles.

## Context

- F4 design decision (flight.md Open Questions, Design Decisions): the lift covers **genuine deduplication** (3+ existing implementations that converge), **vocabulary invention** (NEW canonical names that replace ad-hoc selectors — design-system tidying), and a **single-use lift for vocabulary completeness** (`.chip` + `.chip-remove`).
- F4 design decision: utility classes (`.is-hidden`, `.u-flex`, `.u-block`) land under `@layer utilities`, finally giving that layer a purpose (it has been declared at index.html:7 since F2 but empty).
- F2 debrief consolidation carry-over: `.section-title` + `// PREFIX` `::before` exists in two near-identical forms (studio's `.section-title` and admin's `.admin-section-title`); F4 absorbs this.
- F3 debrief flag: 313 per-area CSS selectors with substantial duplication. F4 leg 02 is the lift.
- Leg 01 just landed — chat.js was split; the helper modules in `static/js/areas/chat/` emit class names like `.session-item`, `.session-item-text`, `.session-item-title`, `.session-item-agent` (history-buckets.js:37-52) plus `.delete` for the inline delete button (history-buckets.js, source `chat.js:376-384` pre-split). These are leg-02 migration sites.
- F3 keyboard-operability debt closure (mission known issues): `:focus-within`-revealed delete buttons (**2 sites**: `.session-item .delete` in chat, `.agent-item-delete` in studio). Admin's `.admin-pf-model-delete` is ALWAYS-VISIBLE (no reveal pattern — admin.css:144 has no `display: none` default), so it's just a `.btn-muted-destructive` migration without the reveal hook. These MUST keep working post-migration. Visible focus rings via `:focus-visible` MUST also keep working.
- **Test selector contract**: existing browser tests query `.session-item`, `.session-item .delete`, `.agent-item`, `[data-testid="agent-item"]` (verified at `tests/browser/test_flow_keyboard.py:37,66,88,90,96,110`; `tests/browser/test_flow_new_chat.py:192,195`; `tests/browser/test_flow_hash_routing.py:73,82,119`; `tests/browser/test_flow_agent_crud.py:52,80`; `tests/browser/test_visual_snapshots.py:239`). The leg uses **class composition** (NOT rename) for the migration: `.session-item` becomes `class="list-item session-item"`; the inline delete-affordance keeps both names too — `class="delete list-item-delete"`; `.agent-item` becomes `class="list-item agent-item"`; `.agent-item-delete` becomes `class="list-item-delete agent-item-delete"`. The shared CSS rule `.list-item-delete { ... }` provides styling; the legacy class names persist as test-selector hooks. This is a pure refactor — no test edits required.
- All `data-testid` attributes from F1-F3 (and the leg-01-preserved set) MUST remain on their original DOM elements. Class renames don't move testids.

## Inputs

- `static/css/components.css` exists at 95 LOC with shared flash, skip-link, top bar, and app picker rules under `@layer components`. No `@layer utilities` block yet (the layer is declared in index.html:7 but unused).
- `static/css/chat.css` (118 LOC), `static/css/studio.css` (106 LOC), `static/css/admin.css` (179 LOC) — all under `@layer areas`.
- `static/js/areas/chat.js` (441 LOC, post-leg-01) + `static/js/areas/chat/{welcome,history-buckets,message-bubble,telemetry-overlay,thinking-indicator}.js` (5 helpers) — emit `.session-item`, `.delete`, `.chat-welcome-empty`, `.input-area button`, `.new-chat-header`, `.chat-welcome-item` class names.
- `static/js/areas/studio.js` (892 LOC) — emits `.agent-item`, `.agent-item-delete`, `.agent-empty`, `.editor-empty`, `.section-title`, `.field-row` + `.field-input` + `.field-select` + `.field-textarea`, `.new-agent-btn`, `.tool-actions button`, `.save-btn`, `.delete-btn`, `.chip`, `.chip-remove`, `.chip-add`. Has 4 testids: `new-agent-btn`, `agent-empty`, `agent-item`, `delete-agent-btn`, `save-agent-btn`.
- `static/js/areas/admin.js` (1254 LOC) — emits `.admin-category-item`, `.admin-section-title`, `.admin-pf-row`, `.admin-pf-label`, `.admin-pf-input`, `.admin-pf-select`, `.admin-provider-add-btn`, `.admin-provider-edit-btn`, `.admin-provider-delete-btn`, `.admin-pf-save`, `.admin-pf-cancel`, `.admin-pf-test`, `.admin-pf-pull-go`, `.admin-pf-model-delete`, `.admin-provider-empty`, `.admin-pf-models-empty`. Has 4 testids: `add-provider-btn`, `provider-card`, `save-provider-btn`, `test-connection-btn`. **Also contains a separate `.admin-field-row`/`.admin-field-label`/`.admin-field-value` pattern at admin.js:212 that is read-only-display, NOT an editable form — kept admin-only (different from `.admin-pf-row`).**
- All 19 inline `style.display =` setters in admin.js confirmed via `grep -c '\.style\.display' admin.js` (lines: 592, 593, 837, 838, 839, 854, 863, 875, 882, 888, 895, 900, 927, 928, 929, 995, 996, 1005, 1010).
- All F1-F3 + F4-leg-01 tests pass: `pytest tests/` 393 selected; `pytest -m browser tests/browser/` 32 selected.

## Outputs

- `static/css/components.css` grows from 95 LOC to ~300-400 LOC with the new shared primitives + utility layer:
  - `@layer components`: `.list-item`, `.list-item-delete` (with `:focus-within` reveal), `.field-row`, `.field-input`, `.field-textarea`, `.field-select` (+ select-arrow data-URL SVG), `.section-title` (+ `// PREFIX` `::before`), `.btn-outlined-cyan`, `.btn-filled-cyan`, `.btn-muted-destructive`, `.chip`, `.chip-remove`, `.empty-state`. Each retains the F3 a11y rules (`:focus-visible` accent rings, `:focus-within` reveals).
  - `@layer utilities`: `.is-hidden { display: none !important; }`, `.u-flex { display: flex !important; }`, `.u-block { display: block !important; }`.
- `static/css/chat.css` shrinks from 118 → ~70-80 LOC. Removed: shared `.session-item` body rules, `.delete` body, `.chat-welcome-empty` body, `.input-area button` body (uses `.btn-filled-cyan`), `.new-chat-header` cosmetic body (uses `.btn-outlined-cyan` + retains `margin-left: auto` and `.new-chat-header svg` size override). Kept: area-specific overrides (welcome canvas layout, telemetry overlay, message bubbles, history bucketing, session-list-heading, chat-session-banner, input area layout, agent-select sidebar).
- `static/css/studio.css` shrinks from 106 → ~60-70 LOC. Removed: shared `.section-title`, `.section-title::before`, `.field-row`, `.field-input`, `.field-textarea`, `.field-select` bodies (now in components.css); `.new-agent-btn`, `.tool-actions button` bodies (use `.btn-outlined-cyan`); `.save-btn` body (uses `.btn-filled-cyan`); `.agent-item`, `.agent-item-delete`, `.agent-empty`, `.editor-empty` bodies (use `.list-item` / `.list-item-delete` / `.empty-state`); `.chip`, `.chip-remove` bodies (now in components.css). Kept: area-specific overrides (`.area-studio .list-item.confirm-delete`, sidebar header, editor layout, tool toggles, connection groups, chip-area positioning, vram warning, save-btn `.clean`/`.dirty` opacity states).
- `static/css/admin.css` shrinks from 179 → ~110-130 LOC. Removed: `.admin-category-item` body (uses `.list-item`); `.admin-section-title` body (uses `.section-title`); `.admin-pf-row`, `.admin-pf-label`, `.admin-pf-input`, `.admin-pf-select` bodies (use `.field-row`, `.field-input`, `.field-select`); `.admin-provider-add-btn`, `.admin-provider-edit-btn`, `.admin-pf-cancel` bodies (use `.btn-outlined-cyan`); `.admin-pf-save`, `.admin-pf-pull-go` bodies (use `.btn-filled-cyan`); `.admin-provider-delete-btn`, `.admin-pf-model-delete` bodies (use `.btn-muted-destructive`); `.admin-provider-empty`, `.admin-pf-models-empty` bodies (use `.empty-state`). Kept: area-specific overrides (admin sidebar header, admin content header, admin form layout, admin-field-row read-only-display pattern, system panel, provider card layout, provider type badges, model list rows, ollama lifecycle panel, pull UI).
- `static/js/areas/chat.js` + `static/js/areas/chat/history-buckets.js` JS templates updated: `.session-item` → `list-item session-item-extra` (or just `list-item` — see Implementation Guidance for the chosen pattern); inline-delete `.delete` → `list-item-delete`; `.chat-welcome-empty` → `empty-state chat-welcome-empty` (or just `empty-state`); send button: `.input-area button` becomes `<button class="btn-filled-cyan" data-testid="chat-send-btn">Send</button>`; `.new-chat-header` template gets `class="btn-outlined-cyan new-chat-header"` (the layout class persists for `margin-left: auto` and svg sizing).
- `static/js/areas/studio.js` JS templates updated: `.agent-item` → `list-item agent-item` (composed); `.agent-item-delete` → `list-item-delete`; `.agent-empty` → `empty-state agent-empty`; `.editor-empty` → `empty-state editor-empty`; `.section-title` (already shared name — no rename, just verify CSS lifts cleanly); `.new-agent-btn` → `btn-outlined-cyan` (the icon button — `.new-agent-btn` class can be retained as a hook for `data-testid="new-agent-btn"` integrity check, but its CSS body comes from `.btn-outlined-cyan`); `.tool-actions button` markup stays `<button>` inside `.tool-actions` — promote each to `<button class="btn-outlined-cyan">`; `.save-btn` → `btn-filled-cyan save-btn` (composed; save-btn keeps the `clean`/`dirty` state class hooks); `.chip` and `.chip-remove` keep their names (now sourced from components.css).
- `static/js/areas/admin.js` JS templates updated: `.admin-category-item` → `list-item admin-category-item` (composed for area-specific badge layout); `.admin-section-title` → `section-title admin-section-title` (or rename to `.section-title` outright if no admin-specific overrides remain — see Implementation Guidance); `.admin-pf-row` → `field-row admin-pf-row` (composed); `.admin-pf-label` → just `<label>` in the `.field-row` (drop the class); `.admin-pf-input` → `field-input admin-pf-input`; `.admin-pf-select` → `field-input field-select admin-pf-select` (composed); `.admin-provider-add-btn` → `btn-outlined-cyan admin-provider-add-btn` (the existing class is kept for `margin-left: auto` layout positioning); `.admin-provider-edit-btn` → `btn-outlined-cyan`; `.admin-pf-cancel` → `btn-outlined-cyan admin-pf-cancel` (existing class kept for any padding/font-size tweaks); `.admin-pf-save` → `btn-filled-cyan admin-pf-save`; `.admin-pf-pull-go` → `btn-filled-cyan admin-pf-pull-go`; `.admin-provider-delete-btn` → `btn-muted-destructive admin-provider-delete-btn` (the latter is kept for the `.admin-provider-delete-btn.admin-provider-delete-confirm` confirm-state hook); `.admin-pf-model-delete` → `btn-muted-destructive admin-pf-model-delete` (same pattern for the confirm-state hook); `.admin-provider-empty` → `empty-state admin-provider-empty`; `.admin-pf-models-empty` → `empty-state admin-pf-models-empty`.
- `static/js/areas/admin.js` 19 inline `style.display =` setters replaced with utility-class toggles. Concrete migration:
  - 17 of 19 sites toggle elements whose CSS-defined natural display is already `flex` (`.admin-pf-row`, `.admin-pf-pull-input`, `.admin-pf-pull-progress`) or `block` (`.admin-pf-pull-suggestions`, `.admin-pf-pull-error`). These collapse to `el.classList.toggle('is-hidden', !visible)` — removing `.is-hidden` returns the element to its CSS-defined display.
  - 2 sites use `style.display === 'none'` as a state read (admin.js:837): replace with `!el.classList.contains('is-hidden')` for the inverse check, OR use a dedicated state field, OR rewrite the toggle as a single `el.classList.toggle('is-hidden')` (no condition needed if both states are valid). Pick the cleanest at implementation time.
  - The leg also accepts `el.classList.toggle('u-flex', visible)` for sites where the implementer prefers explicit forcing — both forms are acceptable per the flight spec ("the right utility class per case").
- `static/js/areas/admin.js`: **6 inline `style="display:..."` HTML attributes** in template strings (lines 524, 532, 802, 805, 809, 814) replaced with class-based hidden-state declarations:
  - **Lines 524, 532** (conditional ternary — `admin-pf-base-url`, `admin-pf-api-key` rows): `'<div class="field-row admin-pf-row admin-pf-base-url' + (defaults.showBaseUrl ? '' : ' is-hidden') + '">'`.
  - **Lines 802, 805, 809, 814** (always-hidden initial state — `admin-pf-pull-input`, `admin-pf-pull-suggestions`, `admin-pf-pull-progress`, `admin-pf-pull-error`): replace `style="display:none"` with adding `is-hidden` to the className. E.g., `'<div class="admin-pf-pull-input is-hidden">'`. These templates already encode the initial-state-hidden contract via the inline style; the migration just shifts to a utility class. This eliminates the "construction-then-immediate-hide" race the leg previously called out.
  These are NOT counted in the "19 inline `el.style.display = ...` setters" — they are a separate but related migration. Flag both totals in the flight log.
- `the_one/agents.md` "Affordance vocabulary" subsection (already exists per F2/F3) updated with the new shared class catalog and utility class names.
- All F1-F3 + F4-leg-01 testids preserved on their original DOM elements.

## Acceptance Criteria

- [x] `static/css/components.css` contains the new `@layer components` primitives (`.list-item`, `.list-item-delete`, `.field-row`, `.field-input`, `.field-textarea`, `.field-select`, `.section-title`, `.btn-outlined-cyan`, `.btn-filled-cyan`, `.btn-muted-destructive`, `.chip`, `.chip-remove`, `.empty-state`) and a `@layer utilities` block with `.is-hidden`, `.u-flex`, `.u-block`.
- [x] `static/css/chat.css`, `static/css/studio.css`, `static/css/admin.css` shrink relative to pre-leg-02 LOC (chat: 118 → ≤ 100; studio: 106 → ≤ 80; admin: 179 → ≤ 140). Each retains only area-specific overrides — no shared primitive bodies remain in per-area files.
- [x] Both `:focus-within` reveal patterns (2 sites: chat session-item, studio agent-item) continue to work — verified by manual keyboard test (Tab onto a list item; the inline delete affordance is reachable / visible). Admin's `.admin-pf-model-delete` is always-visible by design — it gets the `.btn-muted-destructive` styling without the reveal hook.
- [x] All `:focus-visible` accent-ring rules from F3 a11y polish are preserved — either in components.css for shared classes or in per-area files for area-specific elements (admin pf-input, admin pf-select, etc.).
- [x] All 19 inline `el.style.display = ...` setters in `admin.js` replaced with utility-class toggles. `grep -c '\.style\.display' the_one/interfaces/web/static/js/areas/admin.js` returns `0`.
- [x] All 6 inline `style="display:..."` attributes in admin.js HTML template strings (lines 524, 532, 802, 805, 809, 814) replaced with `is-hidden` class application (conditional at 524/532; always-applied at 802/805/809/814). `grep -c 'style="display' the_one/interfaces/web/static/js/areas/admin.js` returns `0`.
- [x] All `.session-item`, `.session-item .delete`, `.agent-item`, `[data-testid="agent-item"]` test selectors continue to match (per the class-composition contract in Context). Verified by `pytest -m browser` passing 32/32.
- [x] All testids preserved: `agent-select`, `chat-welcome`, `new-chat-btn`, `chat-input`, `chat-send-btn`, `message`, `thinking-indicator` (chat); `new-agent-btn`, `agent-empty`, `agent-item`, `delete-agent-btn`, `save-agent-btn` (studio); `add-provider-btn`, `provider-card`, `save-provider-btn`, `test-connection-btn` (admin). `grep -c 'data-testid="agent-select"' static/js/areas/chat.js` returns ≥ 1; same for every testid above against its source file.
- [x] `pytest --timeout=60 tests/` passes 393/393 (exact equality with leg-01 baseline; pure refactor).
- [x] `pytest --timeout=120 -m browser tests/browser/` passes 32/32 (exact equality with leg-01 baseline; pure refactor).
- [x] `the_one/agents.md` "Design system" / "Affordance vocabulary" subsection updated with: the new shared class catalog (`.list-item`, `.field-row`, `.section-title`, `.btn-outlined-cyan`, `.btn-filled-cyan`, `.btn-muted-destructive`, `.chip`, `.empty-state`); the new utility classes (`.is-hidden`, `.u-flex`, `.u-block`); and a note that admin's `.admin-field-row` (read-only field-VALUE display) is intentionally distinct from the shared `.field-row` (editable form).
- [x] No new external dependencies introduced.
- [ ] Manual smoke check: open all three areas, verify list-item hover + active + focus-visible + focus-within reveal still work; verify form fields render correctly; verify section titles still show the `// ` prefix; verify the provider type-conditional fields (base URL + API key) still hide/show on type change in admin; verify the pull-progress UI still toggles between input + progress + error states. _(Optional — full functional coverage is delivered by the 32-case browser suite.)_

## Verification Steps

- LOC check: `wc -l the_one/interfaces/web/static/css/{components,chat,studio,admin}.css` shows components grown, chat/studio/admin shrunk per the targets.
- Class presence check: `grep -E '\.list-item\b|\.field-row\b|\.section-title\b|\.btn-outlined-cyan\b|\.btn-filled-cyan\b|\.btn-muted-destructive\b|\.chip\b|\.empty-state\b' the_one/interfaces/web/static/css/components.css` returns hits for each new shared class.
- Utility layer check: `grep -A 1 '@layer utilities' the_one/interfaces/web/static/css/components.css` shows the layer with `.is-hidden`, `.u-flex`, `.u-block` rules.
- Inline-style check: `grep -c '\.style\.display' the_one/interfaces/web/static/js/areas/admin.js` returns `0`. `grep -c 'style="display' the_one/interfaces/web/static/js/areas/admin.js` returns `0`.
- testid check: `grep -h 'data-testid="' the_one/interfaces/web/static/js/areas/chat.js the_one/interfaces/web/static/js/areas/chat/*.js the_one/interfaces/web/static/js/areas/studio.js the_one/interfaces/web/static/js/areas/admin.js | sort -u` enumerates all 16 expected testids.
- Tests: `pytest --timeout=60 tests/` 393/393 pass. `pytest --timeout=120 -m browser tests/browser/` 32/32 pass.
- Manual keyboard check (Flight Director or human): Tab through each area's list view; confirm focus rings appear on list items and form inputs (`:focus-visible`); confirm delete affordances become visible when a list item gains keyboard focus (`:focus-within`); confirm Enter/Space activates list items (F3 keyboard handlers preserved).

## Implementation Guidance

### 1. Shared primitives in `components.css`

Add the following blocks under `@layer components` (after the existing app-picker block at line 95). Indent and bracket style match the existing components.css convention.

#### `.list-item`

Source: union of `.session-item` (chat.css:14-27), `.agent-item` (studio.css:10-23), `.admin-category-item` (admin.css:6-9). Take the LCD: padding `8px 10px`, border-radius `6px`, font-size `var(--font-size-body-sm)`, cursor pointer, color `var(--fg-secondary)`, display flex, align-items center, gap `6px`. The `.active` state (background, border, box-shadow) is identical in all three sources — promote to `.list-item.active`. The `:focus-visible` rule (outline 2px solid accent + inset glow) is identical in all three — promote to `.list-item:focus-visible`. The `:hover` rule (`background: var(--surface); color: var(--fg);`) is identical — promote to `.list-item:hover`.

```css
.list-item {
  padding: 8px 10px;
  border-radius: 6px;
  font-size: var(--font-size-body-sm);
  cursor: pointer;
  color: var(--fg-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.list-item:hover { background: var(--surface); color: var(--fg); }
.list-item.active { background: var(--accent-translucent); color: var(--fg); border: 1px solid var(--accent); box-shadow: var(--panel-shadow-glow); }
.list-item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; box-shadow: inset 0 0 0 3px var(--accent-glow); }
```

#### `.list-item-delete`

Source: `.session-item .delete` (chat.css:20-27), `.agent-item-delete` (studio.css:16-23). The `:focus-within` reveal (`display: block`) is in chat.css:21-22 and studio.css:17-18 and is identical. Promote to `.list-item:hover .list-item-delete, .list-item:focus-within .list-item-delete { display: block; }`. Hover destructive color shift (`color: var(--status-danger); filter: drop-shadow(...)`) is identical — promote.

```css
.list-item-delete {
  display: none;
  margin-left: auto;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--status-danger-muted);
  font-size: var(--font-size-tiny);
  padding: 2px 4px;
  flex-shrink: 0;
  transition: color 0.2s, filter 0.2s;
}
.list-item:hover .list-item-delete,
.list-item:focus-within .list-item-delete { display: block; }
.list-item-delete:hover { color: var(--status-danger); filter: drop-shadow(0 0 6px var(--status-danger-glow)); }
.list-item-delete:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: 0 0 0 3px var(--accent-glow); }
.list-item-delete svg { width: 12px; height: 12px; display: block; }
```

Note: chat session-item's `.delete svg` was 12px×12px; studio's `.agent-item-delete svg` was 10px×10px. Reconcile to 12px (the more-common size) — minor visual change (2px difference) acceptable per the flight spec's "drift acceptable" line. If a snapshot test catches this, accept the drift (snapshot baselines are gitignored per user policy).

#### `.field-row` + `.field-input` + `.field-select` + `.field-textarea`

Source: `.field-row` (studio.css:36), `.field-input` (studio.css:38-41), `.field-textarea` (studio.css:53-55), `.field-select` (studio.css:42-49 — including the data-URL SVG arrow); admin's `.admin-pf-row` (admin.css:88), `.admin-pf-label` (admin.css:89), `.admin-pf-input` (admin.css:90-91), `.admin-pf-select` (admin.css:92).

Reconcile margin-bottom: studio uses 8px, admin-pf uses 12px. Pick **8px** for the shared base. The 4px drift in admin form is minor (acceptable per flight spec).

Reconcile label width: both studio's `.field-row label` and admin's `.admin-pf-label` are 100px ✓ — no reconciliation needed.

```css
.field-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.field-row label {
  width: 100px;
  font-size: var(--font-size-body-sm);
  color: var(--fg-secondary);
  flex-shrink: 0;
}
.field-input {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--fg);
  font-family: inherit;
  font-size: var(--font-size-body);
  outline: none;
}
.field-input:focus { border-color: var(--accent); }
.field-input:focus-visible {
  border-color: var(--accent);
  outline: 1px solid var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.field-textarea {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  color: var(--fg);
  font-family: inherit;
  font-size: var(--font-size-body);
  outline: none;
  resize: vertical;
}
.field-textarea:focus { border-color: var(--accent); }
.field-textarea:focus-visible {
  border-color: var(--accent);
  outline: 1px solid var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.field-select {
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 30px;
  cursor: pointer;
}
.field-select option { background: var(--surface); color: var(--fg); }
.field-select option:disabled { color: var(--fg-muted); }
```

#### `.section-title`

Source: `.section-title` (studio.css:34-35), `.admin-section-title` (admin.css:23-24). Identical bodies. Lift verbatim.

```css
.section-title {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
  font-weight: var(--font-weight-bold);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--fg-secondary);
  margin-bottom: 12px;
}
.section-title::before {
  content: "//";
  padding-right: 0.4em;
  color: var(--accent);
  font-weight: var(--font-weight-bold);
}
```

#### `.btn-outlined-cyan` / `.btn-filled-cyan` / `.btn-muted-destructive`

Source bodies (vocabulary invention; not deduplications):
- `.btn-outlined-cyan` ← `.new-agent-btn` (studio.css:6-8), `.tool-actions button` (studio.css:60-61), `.new-chat-header` (chat.css:40-43), `.admin-provider-add-btn` / `.admin-provider-edit-btn` (admin.css:56-57, 66-67), `.admin-pf-cancel` (admin.css:101-102). Common shape: transparent background, 1px solid accent border, `var(--panel-radius-sm)` border-radius, accent color, `var(--accent-translucent-hover)` background on hover, focus-visible accent ring with 3px glow box-shadow. Padding varies (4px 10px / 4px 12px / 6px 16px / 3px 10px) — pick **`4px 10px`** as the shared base (3 of 5 sites use it: chat new-chat-header, studio new-agent-btn, studio tool-actions). Admin sites (`4px 12px` and `6px 16px`) keep their own padding via per-area override.
- `.btn-filled-cyan` ← `.input-area button` (chat.css:93-95), `.save-btn` (studio.css:92-94), `.admin-pf-save` (admin.css:103-104), `.admin-pf-pull-go` (admin.css:161-163). Common shape: accent background, no border, `var(--panel-radius-sm)` (or 8px in chat input — accept reconciliation to `var(--panel-radius-sm)`), `var(--fg-on-accent)` color, `var(--font-weight-semibold)`, accent-glow box-shadow. Padding varies — pick `8px 24px` (the `.save-btn` value) as base.
- `.btn-muted-destructive` ← `.admin-provider-delete-btn` (admin.css:69-70), `.admin-pf-model-delete` (admin.css:144-145). Note: `.delete` (chat session-item delete affordance) and `.agent-item-delete` (studio inline delete) are SEPARATELY consolidated as `.list-item-delete` because they live INSIDE `.list-item` and use the `:focus-within` reveal pattern — they're a different affordance shape (icon-only, hidden until reveal) than `.btn-muted-destructive` (text button, always visible). Don't conflate the two. Common shape for `.btn-muted-destructive`: transparent or `none` background, 1px solid `var(--status-danger-muted)` border, `var(--panel-radius-sm)`, `var(--status-danger-muted)` color; on hover, color + border-color shift to `var(--status-danger)` plus a danger-glow box-shadow. Padding `3px 10px`.

Each base class has a `:disabled` rule (`opacity: 0.4; cursor: not-allowed;`), and the filled variants drop `box-shadow: none` on disabled. Lift these with the base.

#### `.chip` + `.chip-remove`

Source: `.chip` (studio.css:76), `.chip-remove` (studio.css:77-80). Single-use lift for vocabulary completeness. Lift verbatim. Keep the F3 `:focus-visible` accent ring on `.chip-remove` (studio.css:79).

#### `.empty-state`

Source: 4 active sites — `.agent-empty` (studio.css:24), `.editor-empty` (studio.css:28), `.admin-provider-empty` (admin.css:59), `.admin-pf-models-empty` (admin.css:125). The dead `.chat-welcome-empty` (chat.css:111) is **not a source** — no JS template emits it; the rule is deleted from chat.css with no replacement. Bodies of the 4 active sites are similar but not identical. LCD:

```css
.empty-state {
  padding: 16px;
  color: var(--fg-muted);
  font-size: var(--font-size-body);
  text-align: center;
}
```

Per-area divergences land as area-specific overrides. The `.editor-empty` keep-list override carries `flex: 1; display: flex; align-items: center; justify-content: center; font-size: var(--font-size-body-lg);` — both the layout pattern AND the larger font size that studio.css:28 currently uses. Don't lose the `font-size-body-lg` override during the lift.

### 2. Utility classes (`@layer utilities`)

Add a new `@layer utilities` block at the bottom of components.css:

```css
@layer utilities {
  .is-hidden { display: none !important; }
  .u-flex { display: flex !important; }
  .u-block { display: block !important; }
}
```

The `!important` is appropriate for utilities — they win over `@layer components` and `@layer areas` rules by design (the utility is the explicit override). This matches CSS-utility-class convention.

### 3. Per-area CSS migrations

For each per-area file (`chat.css`, `studio.css`, `admin.css`), delete the rules whose bodies were lifted, retain area-specific overrides, and verify the area still renders correctly. The line-by-line removal map is documented in the Outputs section above.

**Chat-specific keep list**: `.area-chat #sidebar-header`, `.area-chat .title`, `.area-chat .sidebar-actions`, `.area-chat .session-list-heading`, `.area-chat .session-group`, `.area-chat .session-group-label`, `.area-chat .agent-select` + `:focus*`, `.area-chat .session-list`, `.area-chat .session-item-text`, `.area-chat .session-item-title`, `.area-chat .session-item-agent` (the inner text spans inside the list item — these are area-specific text styling, NOT shared); `.area-chat .chat-chrome`, `.area-chat .header`, `.area-chat .session-agent-badge`, `.area-chat .new-chat-header { margin-left: auto; ... }` (layout-only override; cosmetic moved to `.btn-outlined-cyan`); `.area-chat .new-chat-header svg` (icon size override); `.area-chat .telemetry-overlay` + all telemetry rules; `.area-chat .chat-session-banner`; `.area-chat .messages` + `.msg.*` + `.msg-attribution` + `.thinking`; `.area-chat .input-area` (layout); `.area-chat .input-area input` + `:focus*` (input field styling — kept because chat input is sized differently from form `.field-input`); `.area-chat .chat-welcome` + `.chat-welcome-inner` + `.chat-welcome-greeting` + `.chat-welcome-prompt` + `.chat-welcome-list` + `.chat-welcome-item` + `.chat-welcome-item-name` + `.chat-welcome-item-meta` + `.chat-welcome-guidance` + `.chat-welcome-link`.

**Studio-specific keep list**: `.area-studio .studio-sidebar-header`, `.area-studio .studio-sidebar-header .title`, `.area-studio .agent-list`, `.area-studio .agent-item.confirm-delete` + `.agent-item.confirm-delete .agent-item-name` (area-specific destructive-confirm state — extends `.list-item`), `.area-studio .agent-item-name` (text styling), `.area-studio .agent-item-delete svg` (icon size), `.area-studio .studio-editor`, `.area-studio .editor-empty` (layout-only override extends `.empty-state`), `.area-studio .editor-header`, `.area-studio .editor-title`, `.area-studio .editor-form`, `.area-studio .editor-section`, `.area-studio .field-input-short`, `.area-studio .field-model-wrap`, `.area-studio .model-loading` (admin-loading caption variant), `.area-studio .tool-actions` (layout: `display: flex; gap: 8px;`), `.area-studio .tool-group/.tool-row/.tool-toggle/.tool-switch/.tool-name/.tool-desc` (toggle component — entirely studio-specific), `.area-studio .connection-group/.connection-label/.chip-area/.chip-add/.add-dropdown/.add-dropdown-item`, `.area-studio .editor-actions/.editor-error/.save-btn.clean/.save-btn.dirty/.delete-btn` (delete-btn is its own muted-destructive variant — text-only with confirm state — kept as-is OR migrated to `.btn-muted-destructive` if shape matches; pick at implementation), `.area-studio .studio-vram-warning`.

**Admin-specific keep list**: `.area-admin .admin-sidebar-header` + `.title`, `.area-admin .admin-category-list`, `.area-admin .admin-category-name`, `.area-admin .admin-category-badge`, `.area-admin .admin-content`, `.area-admin .admin-header`, `.area-admin .admin-title`, `.area-admin .admin-form`, `.area-admin .admin-loading`, `.area-admin .admin-note`, `.area-admin .admin-section`, `.area-admin .admin-field-row` + `.admin-field-label` + `.admin-field-value` + `.admin-field-not-set` + `.admin-field-env` (read-only display pattern — DISTINCT from shared `.field-row` editable form pattern; document this in agents.md), `.area-admin .admin-placeholder` + variants, `.area-admin .admin-system-*` (system panel — area-specific), `.area-admin .admin-theme-*` (theme toggle — area-specific), `.area-admin .admin-provider-list`, `.area-admin .admin-provider-card` (provider-card layout), `.area-admin .admin-provider-badge*` (per-type badges + 5 type colors), `.area-admin .admin-provider-name`, `.area-admin .admin-provider-actions`, `.area-admin .admin-provider-delete-btn.admin-provider-delete-confirm` (confirm-state hook layered on `.btn-muted-destructive`), focus-visible rules for admin-pf-* form controls (admin.css:74-84 — kept because the form controls are admin-specific and pre-existing focus-visible rules need to stay), all `admin-pf-*` rules NOT lifted (the password eye, password wrap, test-result, models list, ollama lifecycle panel, pull UI), `.area-admin .admin-pf-model-delete.admin-pf-model-delete-confirm` (confirm-state hook layered on `.btn-muted-destructive`), `.area-admin .admin-pf-test` + `.admin-pf-test:hover` (deliberate exception: solid-fill hover — flagged in admin.css:105-106 comment).

### 4. JS template migrations

For each emit-site, change the class list to combine the new shared class with the existing area-specific class. Preserve all `data-testid` attributes verbatim. Examples:

**chat/history-buckets.js** (was chat.js:355-394 pre-split):
```js
el.className = 'list-item session-item' + (s.id === currentSessionId ? ' active' : '');
// ...
delBtn.className = 'delete list-item-delete';  // both classes — `delete` kept as test-selector hook
```

The `:focus-within` reveal works because `.list-item:focus-within .list-item-delete { display: block; }` is in components.css. The `.session-item` modifier remains as a CSS-class hook for the `.area-chat .session-item-text/.session-item-title/.session-item-agent` text-styling rules (those are inner spans, not the `.list-item` itself — there's no rule conflict). The `delete` class on the inline button is **kept solely as a test-selector hook** (`tests/browser/test_flow_keyboard.py:90`, `tests/browser/test_flow_new_chat.py:195`); its CSS body is dropped from chat.css and the styling now comes from `.list-item-delete`.

**chat.js** (chrome construction, send button + new-chat-header):
```js
'<button class="btn-filled-cyan" data-testid="chat-send-btn">Send</button>'
// ...
'<button class="btn-outlined-cyan new-chat-header" type="button" data-testid="new-chat-btn" aria-label="...">' + ...
```

**chat.js + chat/welcome.js**: there's a `.chat-welcome-empty` class in chat.css but it's never emitted by JS today (the welcome canvas has no "empty" state — it always either shows the picker or shows guidance). Safe to migrate the CSS rule to `.empty-state` + drop the `.chat-welcome-empty` class entirely from CSS, OR keep both names if you want a safety hook. Recommended: drop the `.chat-welcome-empty` class entirely (no JS emits it; CSS rule deletion is safe).

**studio.js** (templates at lines 45, 96, 105, 110, 119, 203, 233, 240/248/etc., 242/244/251/269/337, 252/271, 284, 343):
- New-agent-btn: `<button class="btn-outlined-cyan new-agent-btn" data-testid="new-agent-btn" ...>` — preserve `new-agent-btn` for the icon-only sizing override (`.area-studio .new-agent-btn svg { width: 14px; ... }`).
- Tool-actions buttons: `<button class="btn-outlined-cyan">` (the existing `.area-studio .tool-actions button { ... }` selector becomes `.area-studio .tool-actions .btn-outlined-cyan { ... }` if any padding/font-size override is needed, OR drop the override entirely if the base values match).
- Agent-item: `<div class="list-item agent-item" ...>` — keep `agent-item` for the `.confirm-delete` extension, the `.agent-item-name` text-styling hooks, and the `[data-testid="agent-item"]` selector contract referenced by `tests/browser/test_flow_agent_crud.py`, `test_flow_keyboard.py`, `test_flow_hash_routing.py`, `test_visual_snapshots.py`.
- Agent-item-delete: `<button class="list-item-delete agent-item-delete">` — both class names, parallel to chat's `delete list-item-delete` pattern. The legacy `agent-item-delete` class persists for symmetry with chat (no current test selects on it, but symmetry beats divergence).
- Empty/editor-empty: `<div class="empty-state agent-empty" ...>` and `<div class="empty-state editor-empty">` — keep area-specific class for the layout overrides.
- Section-title: `<div class="section-title">` (no rename needed — name already matches the shared class).
- Field-row + field-input: `<div class="field-row"><label>...</label><input class="field-input" ...></div>` — no rename. The studio-only `.field-input-short` / `.field-model-wrap` etc. continue to use those names.
- Save-btn: `<button class="btn-filled-cyan save-btn clean|dirty" data-testid="save-agent-btn">` — keep `save-btn` for the `.clean`/`.dirty` opacity hooks.
- Delete-btn: choose at implementation — either migrate to `.btn-muted-destructive delete-btn` (preserving the `.delete-btn.confirm` hook) OR keep delete-btn as-is. Most ergonomic: migrate (it's the same shape; .confirm becomes a .btn-muted-destructive variant).
- Chip + chip-remove + chip-add: keep names; CSS bodies for chip + chip-remove now come from components.css; chip-add stays studio-specific.

**admin.js** (templates at all the lines listed in Outputs):
- Migrate all enumerated emit-sites per the Outputs section.
- Drop the `style="display:flex|none"` inline attributes at lines 524, 532; replace with conditional `is-hidden` class application as documented.

### 5. admin.js inline-style migration (19 sites)

Walk through each site and apply the appropriate utility-class toggle. Concrete migration:

| Line | Current | New |
|------|---------|-----|
| 592 | `baseUrlRow.style.display = defaults.showBaseUrl ? 'flex' : 'none'` | `baseUrlRow.classList.toggle('is-hidden', !defaults.showBaseUrl)` |
| 593 | `apiKeyRow.style.display = defaults.showApiKey ? 'flex' : 'none'` | `apiKeyRow.classList.toggle('is-hidden', !defaults.showApiKey)` |
| 837 | `pullInputRow.style.display = pullInputRow.style.display === 'none' ? 'flex' : 'none'` | `pullInputRow.classList.toggle('is-hidden')` (no condition needed — toggle inverts) |
| 838 | `pullError.style.display = 'none'` | `pullError.classList.add('is-hidden')` |
| 839 | `suggestionsEl.style.display = 'none'` | `suggestionsEl.classList.add('is-hidden')` |
| 854 | `suggestionsEl.style.display = 'none'` | `suggestionsEl.classList.add('is-hidden')` |
| 863 | `suggestionsEl.style.display = 'none'` | `suggestionsEl.classList.add('is-hidden')` |
| 875 | `suggestionsEl.style.display = 'block'` | `suggestionsEl.classList.remove('is-hidden')` |
| 882 | `suggestionsEl.style.display = 'none'` | `suggestionsEl.classList.add('is-hidden')` |
| 888 | `suggestionsEl.style.display = 'none'` | `suggestionsEl.classList.add('is-hidden')` |
| 895 | `setTimeout(function () { suggestionsEl.style.display = 'none'; }, 200)` | `setTimeout(function () { suggestionsEl.classList.add('is-hidden'); }, 200)` |
| 900 | `suggestionsEl.style.display = 'block'` | `suggestionsEl.classList.remove('is-hidden')` |
| 927 | `suggestionsEl.style.display = 'none'` | `suggestionsEl.classList.add('is-hidden')` |
| 928 | `pullError.style.display = 'none'` | `pullError.classList.add('is-hidden')` |
| 929 | `pullProgress.style.display = 'flex'` | `pullProgress.classList.remove('is-hidden')` |
| 995 | `pullProgress.style.display = 'none'` | `pullProgress.classList.add('is-hidden')` |
| 996 | `pullError.style.display = 'block'` | `pullError.classList.remove('is-hidden')` |
| 1005 | `pullProgress.style.display = 'none'` | `pullProgress.classList.add('is-hidden')` |
| 1010 | `pullInputRow.style.display = 'none'` | `pullInputRow.classList.add('is-hidden')` |

**Initial-state hidden audit — already encoded in the existing inline-style HTML attributes**:

The current admin.js templates at lines 802, 805, 809, 814 already encode the initial-state-hidden contract via `style="display:none"`. The migration replaces that inline style with `is-hidden` in the className: each of these 4 templates becomes `<div class="... is-hidden">`. Same correctness, cleaner markup. No separate audit needed — the existing `style="display:none"` attributes ARE the audit.

Lines 524 and 532 use the conditional ternary form; they migrate per the table above (`'... admin-pf-base-url' + (defaults.showBaseUrl ? '' : ' is-hidden') + '"'`).

**Confirm via grep after migration**: `grep -c 'style="display' admin.js` returns `0`; `grep -c '\.style\.display' admin.js` returns `0`.

### 6. agents.md update

Open `the_one/agents.md`. Find the "Affordance vocabulary" subsection (under Design system). Append:

```markdown
**Shared class catalog** (in `components.css` `@layer components`):
- `.list-item` + `.list-item-delete` — sidebar/category list rows with a focus-within-revealed inline delete affordance. Used in chat (`.session-item`), studio (`.agent-item`), admin (`.admin-category-item`).
- `.field-row` + `.field-input` + `.field-textarea` + `.field-select` — editable form rows with label + input. Used in studio (agent editor) and admin (provider form). Note: admin's `.admin-field-row` (read-only field-VALUE display, e.g., encryption status) is a DIFFERENT pattern and remains admin-only.
- `.section-title` (with `// PREFIX` `::before`) — section headers in editor / form contexts.
- `.btn-outlined-cyan` — secondary affordance buttons (transparent + 1px solid accent border).
- `.btn-filled-cyan` — primary CTAs (accent fill + glow).
- `.btn-muted-destructive` — delete-confirm-style buttons (muted danger color until hover).
- `.chip` + `.chip-remove` — tag-like rows (currently studio-only; lifted for vocabulary completeness).
- `.empty-state` — empty-list / empty-canvas messaging (4 active sites: `agent-empty`, `editor-empty`, `admin-provider-empty`, `admin-pf-models-empty`; the dead `chat-welcome-empty` rule was removed in this leg with no JS emitter).

**Utility classes** (in `components.css` `@layer utilities`):
- `.is-hidden { display: none !important; }`
- `.u-flex { display: flex !important; }`
- `.u-block { display: block !important; }`

JavaScript should toggle visibility via `el.classList.toggle('is-hidden', !visible)` rather than writing `el.style.display = ...` inline.
```

### 7. Run tests

```bash
pytest --timeout=60 tests/                          # 393/393 expected
pytest --timeout=120 -m browser tests/browser/      # 32/32 expected
```

Both must pass with no count change. If a browser test fails, the most likely culprits are: (a) a class rename broke a CSS selector, (b) the inline-style migration broke a hide/show flow, (c) the `:focus-within` reveal isn't reaching the new `.list-item-delete` (verify the CSS scope).

### 8. Update flight log

Append a `### shared-components-lift` block under `## Leg Progress` summarizing CSS LOC deltas, JS template migration count, the 19 inline-style migrations, the 2 inline-style HTML attribute migrations, and any deviations.

## Edge Cases

- **`.session-item-text` / `.session-item-title` / `.session-item-agent` inner-text styling**: these are area-specific (chat-only) and target inner spans, NOT the `.list-item` itself. They keep their names — no rule conflict, no rename needed.
- **`.area-studio .agent-item.confirm-delete`**: studio's destructive-confirm state extends `.list-item`. Selector becomes `.area-studio .list-item.agent-item.confirm-delete { ... }` (more specific) or rely on the `agent-item` modifier being present. Either works.
- **`.area-chat .input-area input`**: chat input is sized differently (font-size body-lg, 10px 14px padding) than the shared `.field-input` (font-size body, 8px 12px padding). Don't migrate — keep the chat input rule area-specific. The send button (`.input-area button`) DOES migrate to `.btn-filled-cyan`.
- **Admin's `.admin-field-row` (read-only display) vs shared `.field-row` (editable form)**: distinct patterns, distinct widths (label 120px vs 100px). Don't conflate. Document the distinction in agents.md.
- **`.btn-outlined-cyan` padding variations**: chat's `.new-chat-header` was `4px 10px`, studio's `.new-agent-btn` was `4px 10px`, studio's `.tool-actions button` was `3px 10px`, admin's `.admin-pf-cancel` was `6px 16px`. The shared base picks `4px 12px`; per-area overrides via the area-modifier class for the larger-padding variants. **One acceptable simplification**: drop the per-area padding override entirely for sites where the 1-2px drift is invisible — accept the visual reconciliation.
- **`.delete-btn` (studio destructive text button)**: structurally identical to `.btn-muted-destructive` (transparent background, danger-muted border + color, hover-shifts-to-danger pattern). The `.delete-btn.confirm` state hook is structurally identical to `.admin-provider-delete-btn.admin-provider-delete-confirm` (admin.css:71). Migrate to `class="btn-muted-destructive delete-btn"` with the `.area-studio .delete-btn { padding: 6px 14px; border-radius: 6px; }` override (studio's delete-btn padding is larger than the shared base) and `.area-studio .delete-btn.confirm` keeping the confirm-state hook.
- **Pre-existing `is-hidden` class collision**: confirm by `grep -r "is-hidden" the_one/interfaces/web/static/`. If anything else uses the name, rename to `.u-hidden` instead. (Quick check: shouldn't be a collision since the layer is empty pre-leg.)
- **Card construction with `is-hidden` initial state**: where JS today constructs an element without an explicit hide and then immediately calls `.style.display = 'none'`, after migration the element's initial markup must include `is-hidden` to start hidden. If the construction is innerHTML-based, append `is-hidden` to the className in the template string. This is part of the leg's correctness — the migration is not just `.style.display → classList.toggle`; it's `.style.display + initial-state-audit → classList.toggle + initial-class-applied`.
- **`@layer` ordering re-confirmation**: index.html declares `@layer tokens, base, components, areas, utilities;`. Utilities is highest-precedence among the named layers, so `is-hidden { !important }` will win over any `@layer areas` `display: ...` rule. ✓ correct ordering.
- **The data-URL SVG arrow in `.field-select`**: lifted verbatim including the URL-encoded SVG. The studio.css inline comment about "F3 form-primitive extraction may replace this with a `<use>`-referenced SVG" is no longer accurate (F3 didn't replace it; F4 leg 02 lifts it as-is). When deleting the studio.css rule, drop the comment too.

## Files Affected

- `the_one/interfaces/web/static/css/components.css` — UPDATED (grows ~95 → ~300-400 LOC; new shared primitives + utility layer)
- `the_one/interfaces/web/static/css/chat.css` — UPDATED (shrinks ~118 → ~70-80 LOC)
- `the_one/interfaces/web/static/css/studio.css` — UPDATED (shrinks ~106 → ~60-70 LOC)
- `the_one/interfaces/web/static/css/admin.css` — UPDATED (shrinks ~179 → ~110-130 LOC)
- `the_one/interfaces/web/static/js/areas/chat.js` — UPDATED (template emit-sites: send button, new-chat-header)
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — UPDATED (session-item → list-item; .delete → .list-item-delete)
- `the_one/interfaces/web/static/js/areas/studio.js` — UPDATED (templates: agent-item, new-agent-btn, save-btn, agent-empty, editor-empty, tool-actions buttons, delete-btn)
- `the_one/interfaces/web/static/js/areas/admin.js` — UPDATED (templates + 19 inline-style → utility-class migrations + 2 HTML inline-style migrations)
- `the_one/agents.md` — UPDATED (Affordance vocabulary subsection)
- `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md` — UPDATED (leg progress entry)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] `pytest --timeout=60 tests/` passes (393/393)
- [x] `pytest --timeout=120 -m browser tests/browser/` passes (32/32)
- [x] Update flight-log.md with leg progress entry under `## Leg Progress` (`### shared-components-lift` heading)
- [x] Set this leg's status to `landed` (in this file's header) — DO NOT set to `completed` and DO NOT commit; the flight-level review and commit run after the last autonomous leg per `/agentic-workflow`.
- [x] Signal `[HANDOFF:review-needed]`

# Leg: 05-hat-and-comprehensive-review

**Status**: landed
**Flight**: [Administration Alignment](../flight.md)

## Objective

Interactive Human Acceptance Test (HAT) walking the full restructured Administration surface against the six user requirements + the F4/F5 design-system contract. Verifies both themes (light + dark), all dirty-state gate routes, the `App.confirmDelete` migration on both editors, and that F5's hash-routing + studio behaviors remain intact. Lands when the user explicitly approves; any inline fixes during HAT track LOC delta against `admin.js post-leg-04 target ≤ 700` (currently 433 — well under budget).

## HAT structure

State-transition sequences per `CLAUDE.md` HAT design guidance: each step names the transition, lists positive + negative assertions, and pairs UI checks with state assertions. Driven by the user in a real browser at `http://localhost:8484`; Flight Director (Claude) writes up + tracks each transition + fixes anything inline.

**Starting state**: fresh container post-`make rebuild-clean` (volume wiped, migrations re-run). Empty DB, dev mode on (`THE_ONE_DEV_MODE=true`), `mock` provider type available.

## Verification Sequence

### A — Empty state (no providers, no agents)
- [ ] **A1** [no-setup]: Open `http://localhost:8484`. Verify: defaults to `#chat`; welcome canvas shows guidance pointing to BOTH "Settings" and "Agent Studio"; no error messages anywhere; sidebar shows Chat + Studio + Settings entries; no console errors.
- [ ] **A2** [no-setup]: Click "Settings" in left rail. Verify: hash becomes `#admin/system`; sidebar's section-nav shows "System" + "LLM Providers" with "System" active (`aria-current="page"`); System page renders with three editor-section blocks (Environment, Appearance, Encryption); page-header shows `<h1>System</h1>`; no error messages.
- [ ] **A3** [no-setup]: Hard-refresh on `#admin/system`. Verify: stays on System; refresh on `#admin` redirects to `#admin/system`; refresh on legacy `#admin/general` redirects to `#admin/system`.
- [ ] **A4** [no-setup]: Click "LLM Providers" in section-nav. Verify: hash becomes `#admin/providers`; page-header shows `<h1>LLM Providers</h1>` + `[+ New Provider]` button (square-pen icon); empty-state placeholder reads "No providers configured. Add one to get started."

### B — System page (combined General + System)
- [ ] **B1** Environment subsection. Verify: shows Paths / Server / Concourse CI subsections with read-only env-derived values; `--mono` font + `// PREFIX` styling on subsection labels; no editable inputs (read-only by design).
- [ ] **B2** Appearance subsection. Verify: theme toggle visible with three options (Light / Dark / Auto); current selection highlighted with accent-cyan; clicking each toggles theme immediately; theme persists across hard refresh; resolved theme matches OS preference when "Auto" selected.
- [ ] **B3** Encryption subsection. Verify: rotate-key button visible with destructive-tinted styling; warning copy explains the operation; first click arms ("Confirm rotate?" or similar); second click triggers actual rotation + success flash; 3s revert if no second click.
- [ ] **B4** Both themes. Repeat A1-A4 + B1-B3 in light theme, then in dark theme. Verify: no contrast issues, no broken-asset gaps, all interactive elements have visible focus rings.

### C — Provider grid (LLM Providers page) + create flow
- [ ] **C1** [no-setup] → [provider-create-form]: From `#admin/providers` (empty), click `[+ New Provider]`. Verify: hash becomes `#admin/providers/new`; editor renders with `<h1 class="editor-title">New Provider</h1>` (NO subtitle — create mode); action cluster left-to-right `[← Back] [Cancel] [Save]` (Cancel + Save both `disabled`; Back enabled — never disabled); NO Test button visible; NO Models section; NO Danger Zone; only Connection section visible.
- [ ] **C2** [provider-create-form]: Hard-refresh. Verify: URL stays `#admin/providers/new`; editor re-renders identically.
- [ ] **C3** [provider-create-form]: Type "Mock Test" into Name. Verify: Cancel + Save both ENABLE simultaneously (disabled-SSoT); Save text is "Create" (not "Save").
- [ ] **C4** [provider-create-form]: Click Cancel. Verify: navigates to `#admin/providers`; grid renders with empty-state (no providers seeded yet); editor unmounted.
- [ ] **C5** [provider-create-form]: Re-open create flow; type "Mock Test" + select Type → "Mock". Verify: type dropdown filters to include `mock` (dev mode on); base_url + api_key fields auto-hide for `mock` type; Save remains enabled.
- [ ] **C6** [provider-create-form] → [provider-edit-form]: Click Create. Verify: success flash "Provider created"; URL upgrades from `/new` → `/{newId}`; editor RE-MOUNTS in edit mode — title now shows "Mock Test"; subtitle shows "mock" (no base_url for mock); Test button NOW visible; Danger Zone NOW visible at bottom; Models section NOW visible (loading then "No models found" or similar for mock); Cancel + Save both `disabled` (form is clean post-save).

### D — Edit flow + Test connection
- [ ] **D1** [provider-edit-form]: Type a character into Name. Verify: Cancel + Save both ENABLE; Save text is "Save" (not "Create").
- [ ] **D2** [provider-edit-form]: Click Cancel. Verify: form REVERTS in-place (Name returns to "Mock Test"); URL unchanged (`#admin/providers/{id}`); Cancel + Save both re-DISABLE.
- [ ] **D3** [provider-edit-form]: Click Test button. Verify: button disables during request; `.test-result` span shows `.test-result-pending` "Testing…"; on success → `.test-result-ok` "✓ Mock provider (dev mode)" or similar; success flash; Models panel auto-refreshes (still empty for mock).
- [ ] **D4** [provider-edit-form]: API-key eye toggle. (Skip for mock — no API key field. Re-test on a provider with API key e.g. `openai-compatible` if user has one configured; otherwise create a second provider of type `openai-compatible` to exercise the eye toggle, then delete that test provider.)

### E — Models section (non-Ollama; Ollama lifecycle if available)
- [ ] **E1** [provider-edit-form]: For mock provider — Models section shows Refresh button + `Models` section-title + empty state. Click Refresh → re-fires fetch; no errors.
- [ ] **E2** **Ollama lifecycle (only if user has Ollama running)** — create an `ollama` provider, navigate to its editor. Verify: Models section shows VRAM summary + `Pull Model` button + "Running" + "Available" subsections with model rows; per-row Load / Unload / Delete buttons; pull-search shows library suggestions on input; pull-cancel works mid-progress.

### F — Danger Zone delete flow + agent-usage hard-block
- [ ] **F1** [provider-edit-form]: Scroll to Danger Zone. Verify: `Delete Provider` button styled with destructive-muted treatment; section-title says "Danger Zone" with destructive-tinted color.
- [ ] **F2** [provider-edit-form] → [confirm-delete-armed]: Click `Delete Provider`. Verify: button text becomes "Confirm Delete?" (capital D); button now has `.confirm-delete` class (red-fill bg); aria-live announces.
- [ ] **F3** [confirm-delete-armed] → [provider-grid]: Click again within 3s. Verify: success flash "Provider deleted"; navigates to `#admin/providers`; grid re-renders without the deleted provider; no errors.
- [ ] **F4** **Agent-usage hard-block path**: From an empty state, create a new mock provider; navigate to Studio + create an agent that references this provider; navigate back to Settings → Providers → click the provider → Danger Zone → click Delete. Verify: button text becomes "Used by: {agent-name}"; button is DISABLED; aria-live announces; 3s revert restores "Delete Provider"; NO confirm flow fires; provider is NOT deleted.
- [ ] **F5** Click Delete again on the same hard-blocked provider. Verify: re-fires the agent-usage check (not stuck in stale state); same hard-block result.

### G — Dirty-state confirm dialog (4 routes)
- [ ] **G1** [provider-edit-form, dirty]: Open editor for an existing provider; type into Name (form is dirty). Click `[← Back]`. Verify: modal `[data-testid="confirm-dialog-overlay"]` appears; default focus on Cancel/"Stay"; title "Unsaved changes"; message "You have unsaved changes. Continue without saving?".
- [ ] **G2** [confirm-dialog]: Click "Stay" or press Escape. Verify: dialog closes; editor still mounted; Name input still shows the dirty edit; URL unchanged.
- [ ] **G3** [provider-edit-form, dirty] → [provider-grid]: Type into Name again; click `[← Back]`; click "Continue" (or press Enter). Verify: dialog closes; navigates to `#admin/providers`; edit is discarded; grid renders.
- [ ] **G4** [provider-edit-form, dirty]: Re-open editor; type into Name. Click "System" in section-nav. Verify: dialog opens; Stay → keeps editor + URL; Continue → navigates to `#admin/system`.
- [ ] **G5** [provider-edit-form, clean]: Open editor on a clean provider (no edits). Click `[← Back]`. Verify: NO dialog; navigates immediately to `#admin/providers`.
- [ ] **G6** [provider-edit-form, clean]: Click "System" section-nav. Verify: NO dialog; navigates immediately.
- [ ] **G7** [provider-edit-form, dirty]: Type into Name; press Cmd+R or close-tab attempt. Verify: browser shows native "Leave site?" prompt; Cancel keeps page; Confirm leaves.
- [ ] **G8** [provider-edit-form, clean]: Press Cmd+R. Verify: NO native prompt; page reloads cleanly.

### H — Studio regression check (CSS lifts didn't break studio)
- [ ] **H1** Navigate to `#studio/agents`. Verify: page-header shows "Agents" + `[+ New Agent]`; tile grid renders with same `.entity-tile` styling as admin's provider grid.
- [ ] **H2** Click an agent tile. Verify: editor opens with same canonical `.editor-header` + action cluster + tablist (General / Knowledge / Tools).
- [ ] **H3** Make a dirty edit; click Back. Verify: confirm dialog opens (studio's existing F5-leg-04 flow — not regressed by F6's CSS lifts).
- [ ] **H4** Open agent editor; scroll to Danger Zone; click `Delete Agent`. Verify: button arms with "Confirm Delete?" text + `.confirm-delete` class (post-leg-04 migration); second click deletes.

### I — Hash routing regression
- [ ] **I1** From any deep-link, refresh the page. Verify: F5's existing routes (`#chat/sessions/{id}`, `#studio/agents/{name}`, `#studio/agents/{name}/tools`) still hydrate correctly.
- [ ] **I2** Browser back/forward across `#admin/system` ↔ `#admin/providers` ↔ `#admin/providers/{id}` ↔ `#chat`. Verify: each transition lands on the right state; no 404s, no flashes of empty content.

### J — Six user requirements final pass
- [ ] **J1** "Clean up components and make reusable" — verify `components.css` has the canonical primitives (`.entity-tile-*`, `.page-header`, `.editor-section`, `.form-actions`, `.danger-zone`, `.api-key-wrap`, `.test-result-*`, `.delete-btn[.confirm-delete]`, `.save-btn`, `.back-btn`, `.test-provider-btn`); both studio + admin consume them.
- [ ] **J2** "Combine General + System into a single 'System' page" — only two sections in admin sidebar (System + LLM Providers); System page is the merged surface.
- [ ] **J3** "Provider tiles styled like studio tiles, delete in Danger Zone, Back/Cancel/Save like studio agent page" — all visible.
- [ ] **J4** "Hard links" — `#admin/providers/new` + `#admin/providers/{id}` deep-link correctly; refresh preserves state.
- [ ] **J5** "+ New Provider with edit icon" — page-header button reads "+ New Provider" (not "+ Add Provider"); icon is `square-pen` (matches studio's `+ New Agent`).
- [ ] **J6** "Create flow modeled after create agent: back, cancel, create, test in similar positions" — Back leftmost; Cancel + Save (Create) middle; Test rightmost when applicable; cluster identical between studio create-agent and admin create-provider.

## Documentation absorption (F5 debrief Action Item #1 closure)

Update `the_one/agents.md` (deferred from F5 leg 05 per F6 flight spec line 261). Sections to absorb:
- **F5-deferred entries**:
  - Section-content + editor swap layout pattern (studio + admin both use `.is-hidden` toggle to swap sub-views in the main content panel)
  - Cancel/Save SSoT idiom (`disabled` attribute as single source of truth; `checkDirty` flips both; never use `.dirty`/`.clean` classes)
  - Hydrate-vs-fetch race pattern (`_pendingSelectName` / `_pendingProviderId` + `_tryConsume*` after fetch resolves)
  - `beforeunload`-once-at-init lifecycle (do NOT remove on `deactivate()`)
  - `nav-*` token domain rule (chat sidebar tokens — applies if/when a future surface adopts the same nav idiom)
  - Tabs-gate-iff-data-discards rule (only gate tab changes when data would be lost — F5 leg 05 punted on this for studio's editor; admin's editor doesn't have tabs so N/A here)
- **F6 additions**:
  - `.page-header` / `.page-title` / `.new-entity-btn` canonical lift (consumed by studio's three section-headers + admin's two)
  - `.entity-tile` lift (no composition aliases retained — breaking rename per F6 design)
  - `.danger-zone` / `.danger-zone-title` lift (un-area-scoped; consumed by both editors)
  - `.api-key-wrap` / `.api-key-eye` canonical names (admin only — but the canonical names are studio-area-agnostic for future consumers)
  - `.test-result` family (`.test-result` / `.test-result-pending` / `.test-result-ok` / `.test-result-fail`) — consumed by studio's General tab + admin's Connection section
  - `App.layout.renderSectionNav` rename (F5 lifted from `App.studio.renderSectionNav`; F6 leg 01 made it consumable by admin)
  - `App.confirmDelete` graduated to 3 permanent consumers (chat sessions + studio agent editor + provider editor); the helper now has stable canonical status
  - `<span data-confirm-title>` wrapper convention (any new `App.confirmDelete` consumer should wrap the visible-label text in this span so the helper's titleSelector finds it)

Update `the_one/agents.md` lines 263-264 (stale tile X-button content from F5 — agents.md still describes the per-tile X-button which was removed in F5 HAT). Replace with current Danger-Zone-only deletion model.

## Acceptance

User-approved all sections A–J on 2026-04-28. agents.md absorption committed alongside HAT inline fixes.

## HAT inline fixes (committed during walkthrough)

Seven inline fixes landed during the HAT pass:

1. **A2: Bare `#admin` redirect bug** — clicking Settings while already on `#admin/providers` left the URL at bare `#admin` and stranded the page on whatever section was last active. Two-piece fix: router (`app.js`) extracted `syncUrlFromState(areaId, sub)` helper, called from both cross-area and same-area-sub-change branches; admin's `hydrateState(null)` reset to default `'system'` so `serializeState` returns the canonical default. New regression test `test_admin_picker_click_from_providers_redirects_to_system`.
2. **B3: Rotate-encryption-key button styling regression** — per-area `.admin-system-btn` (border: --border, color: --fg-secondary) read as faint in light mode vs the canonical accent-cyan `+ New Provider`. Migrated to `App.confirmDelete` with `confirmLabel: 'Confirm Rotate?'`; button now composes `.btn-muted-destructive` + `<span data-confirm-title>`. Helper now has 4 permanent consumers.
3. **C1: Provider editor missing horizontal padding** — editor-section blocks rendered flush-left because admin has no `.tabpanel` wrapper (studio's source of horizontal gutter). Added per-area override `.area-admin .editor-section { padding-left: 20px; padding-right: 20px; }`.
4. **C6: Duplicate `// Models` section title** — editor scaffold's canonical `.section-title` was rendered above provider-models.js's panel-internal `.admin-pf-models-title` (also "Models"). Removed the panel-internal label in both `renderBasicModels` and `renderOllamaModels`; kept Refresh + Pull Model buttons in the panel header.
5. **C6 cont.: Refresh button restyling** — added `refresh-cw` icon to icons.js; created canonical `.refresh-btn` rule (mirrors `.back-btn` / `.test-provider-btn` icon-button shape); migrated Refresh button markup to `class="btn-outlined-cyan refresh-btn admin-pf-models-refresh"` with icon + text.
6. **F1: Small-button size system** — introduced `.btn-sm` / `.btn-lg` / `.btn-xl` modifiers to components.css. Migrated Ollama lifecycle buttons (Pull Model, Pull, per-row Load/Unload/Delete) from per-area `.admin-pf-model-btn` / `.admin-pf-pull-btn` styling to `.btn-outlined-cyan .btn-sm` / `.btn-muted-destructive .btn-sm` / `.btn-filled-cyan .btn-sm`. Removed the per-area shared style group from admin.css.
7. **F4: State-divergence + hard-block UX** — TWO bugs in one user report:
   - **Stale-`.then()` clobber**: `populateProviderGrid` had no guard against being called after the user navigated to a different category; admin's `.then` would overwrite the System page when hydrate-back-to-system raced with an in-flight `fetchProviders`. Added `if (currentCategory !== 'providers') return;` guard.
   - **Long agent-name list deformed Delete button**: hard-block message ("Used by: {agents.join(',')}") was written into the button's `[data-confirm-title]` span, making the button stretch awkwardly. Moved message to a sibling `.action-blocked-message` banner below the button (canonical `.action-blocked-message` rule added to components.css; new design-system token `--status-danger-bg-soft` added to tokens.css for both themes). Updated `test_delete_blocked_when_provider_in_use` test to assert against the new banner selector.

## Documentation absorption (`the_one/agents.md`)

Updated the affordance vocabulary (shared class catalog) section:

- **Stale references corrected**: `.agent-tile` family entry rewritten to `.entity-tile` (F6 leg 02 rename, no aliases); X-button references removed (F5 HAT removed per-tile X). `.new-agent-btn` references updated to `.new-entity-btn` (F6 leg 02). `App.studio.renderSectionNav` references updated to `App.layout.renderSectionNav` (F6 leg 01 namespace lift). `Confirm-delete` entry updated for 4 permanent consumers (chat sessions, studio agent editor, provider editor, system-page rotate-key) with `.confirm-delete` class (F6 leg 04 rename from `.confirm`).
- **Future-tense → past-tense**: editor header / test result / beforeunload entries updated to reflect F6 consumption (admin now consumes; "future F6 consumer" → "F6 leg N consumer").
- **NEW entries appended**: `.page-header` family, `.editor-section + sibling divider`, `.danger-zone`, `.api-key-wrap`, `.action-blocked-message`, `.refresh-btn`, `.btn-sm`/`.btn-lg`/`.btn-xl` size modifiers, `.cancel-btn` (JS-hook-only convention), `.save-btn`/`.back-btn`/`.test-provider-btn`/`.delete-btn` family, dirty-state SSoT idiom, hydrate-vs-fetch race + stale-then guard pattern, bare-area hash redirect contract.

## Out-of-scope (future flight candidates)

Captured during HAT but explicitly diverted per F5 lessons-learned (don't grow scope mid-flight):
- **Favicon 404** — `/favicon.ico` returns 404 (no file in `the_one/interfaces/web/static/`). Pre-existing condition predating F6 (verified via git log). Cosmetic console noise; not a regression, not part of the six F6 requirements. Candidate for a future cleanup flight or routine maintenance.
- **Ollama pull cancel UX is misleading** — clicking the cancel button on an in-flight pull aborts the browser's fetch + closes the backend's SSE stream, but Ollama itself continues the pull in the background (content-addressable blob layers persist). The "Pull cancelled" flash implies the partial download was discarded; in reality it's retained and a re-pull resumes from those blobs. Pre-existing behavior — F6 didn't touch the pull lifecycle. Candidates for a future flight: (1) honest label rewrite "Pull stopped (partial blobs retained)"; (2) best-effort `DELETE /api/delete` on cancel; (3) UI for tracking + cleaning in-flight pulls separately. Caller behavior verified during F6 leg-05 HAT.

## Manual smoke commands

```bash
# Verify static assets serve current source (catches stale-image)
make verify-serving

# Verify selector grep audits stay clean
grep -rPn '\.delete-btn\.confirm(?!-)' the_one/interfaces/web/static/ tests/browser/
# expected: zero matches

grep -rn 'admin-pf-password-wrap\|admin-pf-eye\|admin-pf-test-result\|admin-pf-testing\|admin-pf-test-ok\|admin-pf-test-fail\|admin-pf-cancel\|admin-pf-actions\|admin-pf-error\|admin-provider-form\|admin-provider-delete-confirm\|admin-pf-test\b\|admin-header\|admin-title\b' the_one/interfaces/web/static/ tests/browser/
# expected: only documentation-comment matches (substitution tables in sub-module headers)
```

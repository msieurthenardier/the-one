# Leg: 06-routing-sweep-and-design-language-cosmetic

**Status**: completed
**Flight**: [Administration Polish](../flight.md)

## Objective

Walk the Admin area's routing surface with the operator — 8 sub-routes × 3 transitions (deep-link / refresh / back-button) + 4 beforeunload-dirty-gate scenarios — catalog all gaps, fix scope-light issues inline, and log non-trivial issues for Flight 7. Plus a cosmetic pass on the Design Language gallery (deferred at operator HAT — layout deemed on-brand).

Two-pass cadence: **catalog first** (no fixes mid-walk to avoid context-switching), **fix-pass second**. Pattern landed three substantive fixes during the leg: the `#admin/system` → `#admin/general` sub-id rename, the cross-area dirty-gate gap (B2), and a chat→admin state-restore race that surfaced during the B2 retest.

## Context

- **Leg 06 is the alignment leg for Admin polish** (per the flight design: "Admin routing sweep + Design Language gallery cosmetic"). Replaces the original Leg 07 alignment-and-snapshot-regen scope (the snapshot regen + WCAG audit close steps were folded into per-leg verification across Legs 01-05; this leg captures the routing/HAT close).
- **Sub-rename inserted mid-walk**: at Check 1 the operator surfaced confusion about `#admin/system` — the area is labeled "System" + the sub-category id was also `'system'`, reading as "System → System" semantically. Renamed sub-id `'system'` → `'general'` to match the visible "General" label; legacy redirect `'system'` → `'general'` flipped from the predecessor F6 leg 01 redirect (`'general'` → `'system'`).
- **B2 (cross-area dirty gate gap)** was the only routing failure. Root cause: the dirty-gate logic lived only in admin's sidebar `setCategory`. Topbar buttons set `location.hash` directly → `switchTo()` deactivates without checking the outgoing area's dirty state. Fix: new `confirmLeave(proceed, abort)` hook contract on the area descriptor; `switchTo()` consults it before cross-area deactivation; admin implements it with the same `dirty && inEditor` condition as the sidebar gate. On abort, the hash rolls back via `history.replaceState`.
- **B2 follow-on race condition**: after B2 fix, retesting surfaced a separate bug. Chat→admin transition restored admin's prior state (currentCategory='tools', toolFormMode='edit', editingTool=delete_file) via `admin.activate()` → `_refresh()` → `selectTool(editingTool.name)` which kicked off `/api/tools/configs/delete_file`. `switchTo` then synchronously called `hydrateState(null)` → `_setCategory('general')` clearing state and rendering System page. When the in-flight fetch resolved, its `.then` block overwrote the System page with the tool editor. Fix: stale-then guard in `selectTool.then` (same pattern providers' `populateProviderGrid` already used at admin.js:378).
- **Design Language gallery cosmetic pass deferred** — operator confirmed at HAT close that the layout is on-brand without changes. Per the flight design ("Out of scope: the gallery's swatch grids and per-section sample primitives themselves"), the in-scope items were just page-header / section-eyebrow / section-gap rhythm. Operator deemed all three correct.

## Inputs (pre-leg state)

- **Admin sub-routes**: `#admin` (bare → default), `#admin/system` (General page — sub-id literal `'system'`), `#admin/providers` (grid), `#admin/providers/new` (editor create), `#admin/providers/{id}` (editor edit), `#admin/tools` (tabbed grid), `#admin/tools/{name}` (editor), `#admin/design-language` (gallery, dev-mode-gated).
- **`admin.js`**: sub-id `'system'` referenced at 11 sites; `setCategory` had dirty-gate; cross-area `confirmLeave` hook did NOT exist.
- **`app.js`**: `switchTo()` cross-area branch deactivated outgoing area unconditionally; no hook for the outgoing area to gate the transition.
- **`tests/browser/`**: 3 test files referenced the old slug — `test_flow_admin_navigation.py`, `test_flow_provider_dirty_confirm.py`, `test_flow_admin_tools_grid.py`.
- **`selectTool` async fetch** in admin.js: `.then` block had no stale-state guard (unlike `populateProviderGrid` which did).

## Outputs (post-leg state)

### Sub-id rename `#admin/system` → `#admin/general`

- `admin.js`: 9 functional sites + 2 comment references migrated. Default `currentCategory` is now `'general'`; the categories list, `validIds`, `_setCategory`, `_refresh`, `serializeState`, `hydrateState`, and `renderContent` branches all reference `'general'`.
- `admin.js` legacy redirect flipped: was `if (sub === 'general') sub = 'system';` (F6 leg 01); now `if (sub === 'system') sub = 'general';`. Bookmarks/external links pointing at the F6-era `/system` slug still land on the right page.
- `app.js`: 2 comments referencing `#admin/system` updated to `#admin/general`.
- `tests/browser/`: 3 test files updated. `test_flow_admin_navigation.py` rewritten with renamed test names + updated docstrings; `test_flow_provider_dirty_confirm.py` 6 `'system'` data-section + URL refs replaced with `'general'`; `test_flow_admin_tools_grid.py` URL ref updated.

### `confirmLeave` hook contract + admin implementation (B2 fix)

- `app.js switchTo()`: cross-area branch wrapped. Before deactivating the outgoing area, consults `areas[currentId].confirmLeave(proceed, abort)` if the hook exists. Areas without the hook fall through to immediate proceed. On abort, `history.replaceState` rolls the URL hash back to the prior area's path (covers topbar clicks, browser back/forward, direct hash typing — anything that triggers hashchange).
- `admin.js`: `confirmLeave` method on the area descriptor delegates to `self._confirmLeaveImpl` (wired inside `init()` so it can close over the local `dirty` flag). Same condition as the sidebar gate: `dirty && inEditor` (where `inEditor === (currentCategory === 'providers' && providerFormMode) || (currentCategory === 'tools' && toolFormMode)`). Dialog uses `App.confirmDialog({ onConfirm: proceed, onCancel: abort })`.

### `selectTool` stale-then guard (B2 follow-on race fix)

- `admin.js selectTool`: `.then` block now bails when `currentCategory !== 'tools'` (synchronous state change happened mid-fetch). Same pattern used by `populateProviderGrid` (admin.js:378). Catch handler also gates the flash to the same condition.

### Design Language gallery cosmetic pass

- **Deferred**: operator confirmed at HAT close that the gallery layout reads on-brand. No changes shipped. In-scope items (page-header, section-eyebrow spacing, section gap rhythm) deemed correct. Recorded as an operator-driven scope decision (mirrors Leg 04's early-close pattern).

### B1 — skipped

- **Skipped per operator**: "fix b2, skip b1." B1 (sidebar-click-from-clean-editor stuck) reported pre-catalog but never reproduced during the routing walk. Carries forward to Flight 7 or future maintenance pass.

### O1 — accepted

- **Uncommitted chip-list-input text not tracked as dirty**: operator surfaced during Check 24 and accepted as non-blocking ("I think this is ok"). Future polish item: blur-autocommit on the chip-list-input would close the gap.

## Acceptance Criteria

- [x] **22 routing checks** (8 sub-routes × deep-link/refresh/back, minus 2 because `#admin` bare only needs the redirect check) — all pass
- [x] **4 beforeunload-dirty-gate checks** — provider-editor sidebar (pass), tools-editor sidebar (pass), cross-area topbar (failed → B2 fixed), browser refresh/close (pass)
- [x] **Sub-id rename `system` → `general` + legacy redirect** — narrow gate 56/56 confirms tests still green
- [x] **B2 fix** — `confirmLeave` hook landed in app.js; admin.js implements it
- [x] **B2 follow-on race fix** — stale-then guard in `selectTool.then`
- [x] **Test files migrated** — 3 browser tests reference new slug
- [x] **Design Language gallery cosmetic** — operator-confirmed on-brand; no changes shipped
- [x] **Narrow test gate** green: 56/56 (final round)
- [x] **WCAG audit** green: 45/45 (no contrast changes)

## Files Modified

- `the_one/interfaces/web/static/js/areas/admin.js` — 11 sites for `system` → `general` slug rename; `confirmLeave` method + `_confirmLeaveImpl` wiring; `selectTool` stale-then guard; comment updates
- `the_one/interfaces/web/static/js/app.js` — `switchTo()` cross-area branch wrapped in `confirmLeave` gate; 2 comments referencing `#admin/system` updated
- `tests/browser/test_flow_admin_navigation.py` — rewritten for new slug
- `tests/browser/test_flow_provider_dirty_confirm.py` — `data-section` + URL refs migrated
- `tests/browser/test_flow_admin_tools_grid.py` — URL ref migrated

## Citation Audit

13 citations verified against current code at leg close:

- `admin.js:9, :32, :40, :88, :118, :132, :259, :602` — all reference `'general'` (post-rename).
- `admin.js:48-54` — legacy redirect: `if (sub === 'system') sub = 'general';`.
- `admin.js confirmLeave` method + `_confirmLeaveImpl` wiring — verified at the area-descriptor scope + inside `init()` body.
- `admin.js selectTool` — verified `.then` block has `if (currentCategory !== 'tools') return;` guard.
- `app.js switchTo()` — verified `performCrossAreaSwitch` inner-function + `confirmLeave` gate wrapper.
- `tests/browser/test_flow_admin_navigation.py` — verified renamed function names + updated assertions.
- `tests/browser/test_flow_provider_dirty_confirm.py` — verified all `data-section="general"` + `#admin/general` references.
- `tests/browser/test_flow_admin_tools_grid.py:206` — verified `f"{app_clean}#admin/general"`.

All citations clean.

## Known Issues Forwarded

- **B1**: clicking "LLM Providers" in the sidebar while at `#admin/providers/{id}` editor (clean) appears to be a no-op. Reported pre-catalog; never reproduced during the routing walk. Skipped this leg. Re-attempt in Flight 7 or future maintenance pass.
- **O1**: uncommitted chip-list-input text not tracked as dirty. Operator accepted as non-blocking. Future polish: blur-autocommit on chip-list-input.

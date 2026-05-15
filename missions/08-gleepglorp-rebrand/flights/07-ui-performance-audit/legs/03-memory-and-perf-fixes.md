# Leg: memory-and-perf-fixes

**Status**: completed
**Flight**: [UI Performance Audit](../flight.md)

## Objective

Fix the H1 hypothesis (statically-confirmed admin theme-toggle `document` listener leak) identified by L02. Refactor `theme.js`'s cleanup from a per-container expando (`container._themeListenerCleanup`) to a module-scoped variable so each `renderToggle` call cleanly removes its predecessor's listener regardless of container identity.

H2 (detached-DOM retention from `innerHTML` rewrites) is largely subsumed by H1's fix — the document listener was what pinned the detached `<div>` subtree as a retainer root. Post-H1-fix the prior subtree becomes GC-eligible. L03 verifies via re-running L01's Scenario 1 procedure.

H3 (perf.js mark-buffer accumulation) is instrumentation-only / HAT-scope; no production code change needed. L01's agents.md scenarios already call `App.perf.reset()` at start.

H4-H8 (requires-heap-diff) are deferred — L01's empirical signal (+30.88% over 200 transitions) was the durable measure; if H1's fix alone drops it under the 20% budget, the rest are noise. If not, L06 HAT escalates to a dedicated reliability flight.

## Context

- **L02 finding** (Retainer-Hypothesis Report H1): `theme.js:101-178` `renderToggle()` body. Each call stores `_themeListenerCleanup` on the passed container. But admin's `system-page.js` re-creates the `#admin-theme-toggle-mount` div via `innerHTML` on each render → the cleanup-check at line 105 reads `_themeListenerCleanup` off a FRESH (different) container → always undefined → no prior cleanup → new `document.addEventListener` stacks on top of the orphan. Result: O(N) `document` listeners after N admin-render cycles.
- **L01 finding**: +30.88% heap growth across 200 area-switches. This leg's success metric: that drops to ≤20% after fix.
- **L02 FD heap-diff validation**: 10-cycle short replay was GC-dominated and inconclusive on per-cycle magnitude. The static-analysis confirmation stands; the durable signal is L01's longer scenario.

## Inputs

- `the_one/interfaces/web/static/js/theme.js` — `renderToggle` body at lines 101-179; the `document.addEventListener(THEME_EVENT, listener)` at line 175; the `container._themeListenerCleanup` expando dance at lines 105-108 and 176-178
- L01 + L02 outputs (perf.js, agents.md scenarios, L02 hypothesis report) — uncommitted on `flight/07-ui-performance-audit` branch
- Broad pytest baseline 1669p/4s/374d at F6.5-landed state

State that must be true:
- L02 landed; hypothesis report in flight-log.md
- Broad pytest 1669p/4s/374d unchanged from L01-landed

## Outputs

Files modified:
- `the_one/interfaces/web/static/js/theme.js` — refactor `renderToggle`:
  - Add module-scoped `var _activeThemeListenerCleanup = null;` near top of IIFE
  - Replace `container._themeListenerCleanup` expando-based cleanup with `_activeThemeListenerCleanup` module-scope-based cleanup
  - Always clean up the prior listener at the top of `renderToggle`, regardless of container identity
- `tests/browser/test_theme.py` (if exists) OR a new browser test — add an assertion that 10 calls to `renderToggle` result in exactly 1 active `document` listener (verified via `getEventListeners(document)`-equivalent technique OR by counting fires of a probe THEME_EVENT)
- Flight log entry for L03 progress + post-fix re-run of L01's Scenario 1 (done by Flight Director via MCP after Developer lands)

State after:
- A single `renderToggle` call cleans up the prior listener via module-scope, not per-container expando — fixes H1
- L01's Scenario 1 re-run should show heap delta drop from +30.88% to within ≤20% budget (FD-verified post-Developer-landed)

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/theme.js` declares a module-scoped variable `_activeThemeListenerCleanup` (initial value `null`); `renderToggle`'s prologue calls this and clears it before attaching a new listener
- [ ] The per-container `container._themeListenerCleanup` expando is REMOVED entirely (no read, no write); `grep -n "_themeListenerCleanup" the_one/interfaces/web/static/js/theme.js` returns ONLY references to the new module-scoped variable
- [ ] No existing test exists for the cleanup contract (cycle-1 reviewer verified — grep for `renderToggle` / `_themeListenerCleanup` / `admin-theme-toggle` in `tests/` returns empty). Add a new browser test that simulates the actual H1 scenario: call `renderToggle(container1, ...)`, replace the host container's `.innerHTML` to discard container1, then call `renderToggle(container2, ...)` on the fresh DOM node. Dispatch `THEME_EVENT`. Assert ONLY container2's `.admin-theme-option.active` state updated — container1's listener is gone.
- [ ] Broad pytest exits 0; pass count unchanged from L02-landed 1669
- [ ] Browser suite preserved at 315 passing / 35 skipped — verify no theme-toggle browser test breaks
- [ ] Theme-toggle UX functional: clicking light/dark/auto in admin still applies the theme; this is verified by HAT or by an existing browser test (`test_admin_system_theme_toggle*` style)
- [ ] **[Flight Director, post-Developer]** Re-run L01's Scenario 1 (50 loops × chat→studio→admin→chat) via MCP; verify heap delta drops from +30.88% to within ≤20% budget; record post-fix numbers in agents.md as "Post-L03 baseline"

## Verification Steps

- **Static check**: `grep -n "_themeListenerCleanup" the_one/interfaces/web/static/js/theme.js` returns ONLY references to the module-scoped variable (no `container._themeListenerCleanup` reads or writes)
- **Functional check**: open chat in browser, switch to admin > system, click Light/Dark/Auto in turn — each click changes the theme; switch chat ↔ admin a few times; clicking theme still works (the cleanup didn't accidentally remove the active listener)
- **Test pass**: theme-toggle browser tests pass; broad pytest 1669p/4s/374d; browser 315/35
- **[FD] Heap-delta drop**: post-L03 MCP re-run of L01 Scenario 1 returns heap delta ≤20% (vs L01's +30.88%)

## Implementation Guidance

1. **Edit `the_one/interfaces/web/static/js/theme.js`**:

   ```javascript
   // BEFORE (around line 95-108):
   //   ...cleanup contract docstring referring to container._themeListenerCleanup...
   //   renderToggle: function (container, options) {
   //     if (!container) return;
   //     options = options || {};
   //
   //     if (typeof container._themeListenerCleanup === 'function') {
   //       container._themeListenerCleanup();
   //       container._themeListenerCleanup = null;
   //     }

   // AFTER:
   //   // Module-scoped cleanup ref — replaces the prior per-container expando
   //   // (M08 F7 L03 H1 fix: container expando dies with the container's
   //   // innerHTML rewrite, leaving the document listener orphaned).
   //   var _activeThemeListenerCleanup = null;
   //
   //   ...rest of IIFE state...
   //
   //   renderToggle: function (container, options) {
   //     if (!container) return;
   //     options = options || {};
   //
   //     if (typeof _activeThemeListenerCleanup === 'function') {
   //       _activeThemeListenerCleanup();
   //       _activeThemeListenerCleanup = null;
   //     }
   ```

   AND replace lines 176-178:

   ```javascript
   // BEFORE:
   //   container._themeListenerCleanup = function () {
   //     document.removeEventListener(THEME_EVENT, listener);
   //   };

   // AFTER:
   //   _activeThemeListenerCleanup = function () {
   //     document.removeEventListener(THEME_EVENT, listener);
   //   };
   ```

   Update the cleanup-contract docstring near lines 97-100 to describe the new module-scoped pattern.

2. **Find the existing theme-toggle test** (if any) — likely `tests/browser/test_admin_system_*.py` or `tests/test_*theme*.py`. Update assertions if needed; the public behavior (single active listener after multiple renders) should match.

3. **Add a regression test** — if no existing test covers the multi-render cleanup contract, add one that:
   - Calls `renderToggle(container1, ...)`
   - Replaces the container DOM (simulate the innerHTML rewrite)
   - Calls `renderToggle(container2, ...)` with a fresh container
   - Dispatches `THEME_EVENT`
   - Asserts ONLY container2's `.admin-theme-option.active` state was updated (container1's listener is gone)

4. **Run tests**:
   ```bash
   docker exec the-one pytest -x --timeout 30
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

5. **Update flight log** with L03 progress. **Do NOT commit** — Flight Director batches commits after L05.

## Edge Cases

- **Two theme toggles rendered simultaneously**: with module-scoped cleanup, only the second one's listener stays. In current architecture this is a non-concern (theme toggle is single-instance, admin-only), but document this in the new docstring so a future maintainer who adds a second theme-toggle understands the constraint.
- **`document.removeEventListener` is idempotent if listener wasn't attached**: even if the cleanup fires twice somehow (race), removing a non-existent listener is a no-op. Safe.
- **What if `renderToggle` is called before `document` is ready**: `document.addEventListener` works against the document at any time during page lifecycle (after the script loads). Theme.js loads early in index.html (`<script src="/static/js/theme.js"></script>` before perf.js); by the time renderToggle is called from admin's render path, document is fully ready.

## Files Affected

- `the_one/interfaces/web/static/js/theme.js` — module-scoped cleanup variable; renderToggle prologue + epilogue updated; docstring updated
- Possibly `tests/browser/test_*theme*` or `tests/test_*theme*` — update or add regression test

---

## Post-Completion Checklist

**Complete ALL steps before marking the leg landed:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest 1669p/4s/374d; browser suite 315p/35s)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit — Flight Director batches commits after L05
- [ ] [FD post-Developer-landed]: re-run L01 Scenario 1 via MCP and record post-fix heap delta in agents.md

---

## Citation Audit

3 source-code citations verified against current code at leg design time:
- `the_one/interfaces/web/static/js/theme.js:101-178` (`renderToggle` body) — OK
- `the_one/interfaces/web/static/js/theme.js:105-108` (per-container expando cleanup check) — OK
- `the_one/interfaces/web/static/js/theme.js:175-178` (`document.addEventListener` + cleanup store) — OK

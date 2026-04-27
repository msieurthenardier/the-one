# Flight: App Shell Restructure

**Status**: completed
**Mission**: [UI Maturity](../../mission.md)

## Contributing to Criteria

- [ ] Critical user flows progress without dead-ends, unexplained errors, or unclear next steps *(specifically: refresh preserves sub-page location; the new-chat flow's structural awkwardness gets fixed)*
- [ ] All interactive controls (buttons, lists, deletes, the theme toggle) are reachable via keyboard and operable with Enter/Space *(closes the F2-debrief-flagged WCAG 2.1.1 keyboard-operability debt)*
- [ ] Code primitives that show up in multiple areas (form rendering, "new" buttons, list items) are shared rather than duplicated *(scoped: the F2-debrief-flagged `admin.js` / `studio.js` form-render divergence is partially addressed; full form-primitive extraction may split to a follow-up flight if scope grows)*
- [ ] The interface presents a coherent visual identity *(F3 must not regress F2's design language; the new top bar composes with the existing nav-rail palette tokens)*

---

## Pre-Flight

### Objective

Replace the current vertical icon nav rail with a horizontal top bar (app name on the left, hamburger app picker on the right). Extend hash routing to persist sub-page state across reloads via a per-area `serializeState`/`hydrateState` contract on the `App` namespace. Fix the structural awkwardness of the new-chat flow. Convert the remaining `<div>`/`<span>` interactive elements (list items, inline deletes) to `<button>` with Enter/Space activation and add semantic landmarks (`<nav>`, `<main>`, `<aside>`, `<h1>`, skip-link) — the WCAG 2.1.1 keyboard-operability debt flagged at F2's flight-level review. Land the F2 debrief's immediate-action items as a leg-1 cleanup. Form-primitive extraction is partially in scope (the `admin.js`/`studio.js` form-render divergence widened in F1) and may split to a dedicated follow-up flight if scope grows.

### Open Questions

- [x] Top-bar layout: app name left + hamburger picker right (per mission spec) — **resolved at flight design**: hamburger opens an overlay/dropdown with three buttons (Chat / Studio / Admin), keyboard-accessible from the start.
- [x] Sub-page hash format — **resolved**: `#area/sub` (e.g., `#chat/sessions/<id>`, `#admin/providers`, `#studio/agents/<name>`); area is required, sub is optional, default behavior unchanged when sub is absent. **Convention**: `serializeState()` returns the sub WITHOUT the area prefix; the framework owns the `area/` segment.
- [x] Lifecycle ordering for `init`/`activate`/`hydrateState` — **resolved**: on cold entry to an area (first activation), the order is `init` → `activate` → `hydrateState(sub)`. On in-area sub-state change (same area, different sub), the framework calls **only** `hydrateState(sub)` — `init` and `activate` do NOT re-fire. This requires modifying `switchTo` (`app.js:30-75`) so its early-return at line 32 (`if (areaId === currentId) return;`) becomes "if same area AND no sub change, return; if same area AND sub changed, call hydrateState only."
- [x] Browser back-button semantics for sub-state — **resolved**: use `history.replaceState` for area-internal sub-navigation (e.g., clicking a different chat session, switching admin sub-page). Sub-state is **view-state**, not **history-state** — the back button exits the area rather than walking through sub-views. Cross-area navigation continues to use `location.hash =` assignment (which DOES push history). Documented in `agents.md` after leg 04.
- [x] Keyboard rebuild scope — **resolved**: leg 03 covers list items + inline deletes (3 sites: chat session-delete, studio agent-delete, studio chip-remove). The nav-rail items go away with the top-bar restructure (leg 02), so they're addressed implicitly. Leg 03 is independent of leg 02 (no shared files); ordering 02→03 chosen for narrative coherence (visible structure first, then internal a11y), not technical dependency.
- [x] Theme toggle reusable mount + multi-mount sync — **resolved**: lift to `App.theme.renderToggle(container, options?)` in leg 01. **`options.variant`**: `'full'` (Light/Dark/Auto labels — current Settings page) or `'compact'` (icon-only — for top-bar mounting). **Multi-mount sync**: `App.theme.set()` dispatches a `CustomEvent('theme-preference-changed', {detail: {pref}})` on `document`; each `renderToggle` instance subscribes on creation and updates its own `aria-checked`/`active` state. Leg 02 may then optionally mount a compact variant in the top bar.
- [x] Form-primitive extraction scope — **resolved**: defer to a dedicated F3.5 flight unless leg-5 (`new-chat-restructure`) naturally consolidates 1-2 primitives. The `_renderProviderFormImpl` rebuild (`admin.js:497`) is its own flight worth of work. F3.5 will also absorb the F2 debrief's `.section-marker` lift and `// PREFIX` literal-vs-`::before` idiom consolidation (touches the same files).
- [x] Top-bar palette — **resolved**: extend the existing `--nav-bg / --nav-fg / --nav-border / --nav-fg-active` palette island. Top bar IS the nav rail's spiritual successor; same chrome treatment in light (dark navy chrome) and dark (`var(--bg)` recessed). **Token migration**: `--nav-w` (rail width, `tokens.css:88, 176`) is repurposed as `--topbar-h: 48px` in both themes; the `.nav-item.active::before` cyan-accent treatment (`base.css:38-47`) ports to the picker dropdown's active option for visual continuity.
- [x] App-picker affordance icon — **resolved**: use Lucide `menu` (3-line hamburger) — most idiomatic for "app picker." Add to `icons.js` in leg 02 (one-line addition, pinned tag `v0.265.0` already in use). Picker dropdown uses `chevron-down` for visual coherence if a secondary visual cue is needed.
- [x] Skip-link styling pattern — **resolved**: standard convention: `position: absolute; top: -40px; left: 0;` then `:focus { top: 0; }` exposes it on focus. Background uses `var(--accent)` with `var(--fg-on-accent)` text; lives in `components.css` under `@layer components`. The currently-declared-but-unused `utilities` CSS layer remains a future placeholder (no leg removes it; no leg uses it in F3).
- [x] Will the test suite need new fixtures for sub-page-aware app instances? — **resolved**: no. Existing `app_clean` / `app_with_provider` / `app_with_agent` fixtures don't care about hash; new browser tests for hash routing assert on `location.hash` after navigation.

### Design Decisions

**Top-bar replaces nav rail entirely**: Vertical `#app-nav` is removed. New `#app-topbar` contains the app name (`<h1>` "the-one") on the left and an app-picker button on the right. App picker opens an overlay/dropdown with three buttons (Chat / Studio / Admin) styled as the nav-rail items were (cyan accent for active).
- Rationale: User explicit pre-mission requirement ("the app picker is not good where it is, we probably need a real top bar with the app name on the left and app picker hamburger on the right"). Horizontal real estate is cheaper than vertical when the app has only 3 areas.
- Trade-off: An extra click to switch areas (open picker, then choose) vs always-visible nav rail. Mitigated by: (a) hamburger position is consistent and discoverable, (b) keyboard shortcut for area switching can land in a follow-up if needed.

**Hash routing extended to `#area/sub` with per-area state contract on the area descriptor**: `serializeState()` and `hydrateState(sub)` are added as **optional properties on the existing area descriptor** passed to `App.registerArea({id, label, icon, order, init, activate, deactivate, serializeState?, hydrateState?})`. This keeps the contract co-located with the existing lifecycle hooks rather than introducing a parallel registry. Defaults: areas without `serializeState`/`hydrateState` behave exactly as today (no sub-state). Lifecycle: `init` (build DOM, idempotent) → `activate` (refresh data) → `hydrateState(sub)` (apply sub-state) on cold entry; only `hydrateState(sub)` on same-area sub-change. The framework dispatches: parse hash → if area changed, switchTo (which fires init+activate) then hydrateState; if same area but sub changed, hydrateState only. `switchTo`'s early-return at `app.js:32` is modified accordingly.
- Rationale: Hash is the right persistence layer (no backend touch, survives reload, shareable URL, no router framework). Per-area parsing keeps coupling thin: the framework knows about `#area/...`, areas know about their own sub-format. Co-locating with `init`/`activate`/`deactivate` matches the existing seam.
- Trade-off: Sub-format conventions diverge per area (chat uses `sessions/<id>`, admin uses `providers`/`system`). Mitigated by documenting the convention in `agents.md` after leg 04. Modifying `switchTo`'s early-return is a small surface change but must be tested explicitly to prevent same-area refresh regressions.

**Sub-state uses `history.replaceState`, not `pushState` (browser back-button semantics)**: When the user navigates *within* an area (e.g., clicks a different chat session, switches admin sub-page), the framework updates `location.hash` via `history.replaceState` so the browser back stack is NOT polluted with each sub-view. Cross-area navigation continues to use `location.hash =` assignment which DOES push history. Net effect: back button exits the area; it does not walk through sub-views.
- Rationale: Sub-state is "what am I looking at right now" (view-state), not "where did I come from" (history-state). Sessions and agents are entity-views, not flow-pages. Walking back through 50 chat sessions one at a time is bad UX.
- Trade-off: Users who want a true back-stack of recent entities need a different mechanism (e.g., recent-items list). Acceptable for v1; revisit if surfaced in HAT.

**Keyboard operability rebuild lands in leg 03 (after the top bar)**: Convert all click-only `<div>`/`<span>` interactive elements to `<button>` with Enter/Space activation. Add `:focus-within` reveal for hover-only delete affordances so keyboard users can reach them. Sites: session-list items (chat.js:128), agent-list items (studio.js:89), admin-category items (admin.js:91), session-delete `<span>` (chat.js:147), agent-delete `<span>` (studio.js:99), chip-remove `<span>` (studio.js).
- Rationale: F2 flight-level a11y review flagged 3 BLOCKING WCAG 2.1.1 failures; F3 is restructuring the shell anyway, so the keyboard-rebuild work composes naturally with the top-bar replacement (which removes the worst offender, the nav-rail items).
- Trade-off: F3 grows by ~1 leg vs the originally-planned scope. Cost is bounded; the alternative (separate Keyboard Operability flight) would touch the same elements twice.

**Semantic landmarks added to `index.html`**: Wrap the new top bar in `<header>`, the app picker in `<nav aria-label="App areas">`, the sidebar in `<aside aria-label="...">`, the content in `<main id="main-content">`, and add a skip-link as the first focusable element (`<a href="#main-content" class="skip-link">Skip to main content</a>`).
- Rationale: WCAG 2.4.1 (Bypass Blocks) and 1.3.1 (Info and Relationships). F2 a11y reviewer flagged the absence; F3 is restructuring the shell so this is the right time.
- Trade-off: Slightly more verbose HTML. Negligible.

**Theme toggle moved out of `admin.js` to `App.theme.renderToggle(container, options?)` with multi-mount sync**: F2 added the segmented Light/Dark/Auto toggle into `admin.js:208-270` (toggle code spans `:209-270`) as the expedient mount point. Per F2 debrief recommendation, lift to `App.theme.renderToggle(container, options?)` so any area can mount it. **`options.variant`** accepts `'full'` (Light/Dark/Auto labels — current Settings page) or `'compact'` (icon-only — for top-bar mount). **Multi-mount sync**: `App.theme.set()` dispatches `CustomEvent('theme-preference-changed', {detail: {pref}})` on `document`; each `renderToggle` instance subscribes on creation and updates its own `aria-checked` + `.active` state on receipt. Without the event, two mounted toggles diverge when the user changes one.
- Rationale: Reusability + composes with the keyboard rebuild (the toggle already has correct keyboard support; moving it doesn't regress). Event mechanism prevents the multi-mount sync bug.
- Trade-off: Net `admin.js` size decreases ~70 LOC; net `theme.js` size grows ~70 LOC + small event-broadcast overhead. Same code, better placement.

**Form-primitive extraction is OUT OF SCOPE for F3 (will become F3.5 / form-primitives)**: The mission and F1 debrief both flag the `admin.js _renderProviderFormImpl` / `studio.js` form-render divergence as needing consolidation. F3's existing scope (top bar + hash routing + keyboard rebuild + new-chat restructure + F2 cleanup) is already a 7-leg flight. Extracting form primitives is its own ~3-leg flight worth of work because it must (a) define the shared API, (b) migrate admin.js, (c) migrate studio.js, (d) preserve all `data-testid` attributes for the regression net.
- Rationale: F3 is at the upper bound of "well-sized flight" already. Splitting the riskiest piece (forms) preserves F3's ability to land in 2-3 days.
- Trade-off: One more flight in the mission roadmap; the divergence persists for one more flight cycle.

**HAT included as final optional leg**: F2 validated HAT-as-conversational-pacing for design changes; F3 includes layout + keyboard + state persistence changes that benefit from a guided walkthrough.
- Rationale: F3 is structural; small bugs (e.g., focus order surprises, hash-routing edge cases on initial load) benefit from real-time iteration.
- Trade-off: ~1 hour of synchronous user time. Worth it.

### Prerequisites

- [ ] F2 landed and merged to `main` (currently on `flight/02-design-language-and-theme-architecture` branch with PR #14 open as draft) — F3 branches from F2's merge commit; this flight assumes F2's tokens, theme switcher, and design-system docs are the baseline. **F3 cannot enter `in-flight` status until PR #14 merges**; if F3 must start before merge, the alternative is to branch F3 from F2's branch HEAD and plan a rebase onto `main` after F2 merges (acceptable variation, but explicit).
- [ ] All 14 F1 `data-testid` attributes still present on their original elements after F3 (regression-net constraint, carried forward from F1)
- [ ] All 12 F2 visual snapshot baselines available — F3 will regenerate them after the top-bar replacement (layout change invalidates baselines by design)
- [ ] All 40 F2 a11y contrast pairs still passing (F3 must not retune tokens; if it does, retune through the same a11y test gate)
- [ ] `pytest tests/` baseline at F3 start: 391 passed, 28 deselected
- [ ] `pytest -m browser tests/browser/` baseline at F3 start: 20 passed (8 flow + 12 visual snapshots)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [ ] Prerequisites verified *(re-run baseline tests at F3 start; expect 391 + 20 passed)*
- [x] Validation approach defined *(per-leg testid stability + F2 snapshot regen + new keyboard-state snapshots + new sub-page-routing browser tests)*
- [x] Legs defined (tentative; planned one-at-a-time during execution)

---

## In-Flight

### Technical Approach

The flight restructures the app shell in a sequence designed to keep the regression net intact at every leg-end. Key principle: **do the F2 debrief cleanup FIRST so F3's structural changes build on a clean baseline, then restructure the shell, then rebuild keyboard operability for the elements the restructure didn't replace**.

Leg dependency graph:

```
01 pre-flight-cleanup ──► 02 topbar-and-landmarks ──► 03 keyboard-operability ──► 04 hash-routing-state ──► 05 new-chat-restructure ──► 06 snapshots-and-tests ──► 07 hat-and-alignment (optional)
                                                          │
                                                          └─► 03 also covers list-items + inline-deletes (the surviving keyboard-debt sites after the nav rail goes away in 02)
```

### File Layout (after F3)

```
the_one/interfaces/web/static/
├── index.html                      # Top bar replaces nav rail; semantic landmarks added
├── css/
│   ├── tokens.css                  # No new tokens expected; --topbar-* would re-use --nav-* family (same palette island)
│   ├── base.css                    # #app-topbar styling; #app-nav rules removed; sidebar/content reflowed under top bar
│   ├── components.css              # New .skip-link utility; .app-picker overlay component
│   ├── chat.css                    # session-item rules updated for <button> conversion + :focus-within reveal of .delete
│   ├── studio.css                  # agent-item + chip-remove + agent-item-delete updated for <button> conversion
│   └── admin.css                   # admin-category-item updated for <button> conversion; theme-toggle CSS unchanged (moves with the JS)
├── js/
│   ├── app.js                      # renderTopBar() replaces renderNav(); hash-routing dispatcher extended; per-area serializeState/hydrateState contract
│   ├── theme.js                    # App.theme.renderToggle(container, options?) added; theme toggle moves here from admin.js
│   ├── icons.js                    # No changes (already has chevron-down for app picker; add menu icon if needed)
│   └── areas/
│       ├── chat.js                 # serializeState/hydrateState; session-item -> <button>; .delete -> <button>; new-chat flow restructure
│       ├── studio.js               # serializeState/hydrateState; agent-item -> <button>; chip-remove -> <button>; agent-item-delete -> <button>
│       └── admin.js                # serializeState/hydrateState; admin-category-item -> <button>; theme-toggle render call replaced with App.theme.renderToggle()
```

### Checkpoints

- [ ] Leg 01 closes the F2 debrief immediates: `--fg-muted` (dark) added to a11y body-AA parametrize set; `--sidebar-bg: transparent` replaced with declarative value; theme toggle extracted to `App.theme.renderToggle()`; affordance vocabulary documented in `agents.md`; marker comments added at keyboard-debt sites
- [ ] Top bar renders correctly in both themes; nav rail removed; hamburger app picker keyboard-accessible (Tab to picker, Enter/Space to open, arrow keys to move between options, Escape to close)
- [ ] Semantic landmarks present and screen-reader-verifiable: `<header>`, `<nav>`, `<aside>`, `<main>`, `<h1>`, skip-link as first focusable
- [ ] All list items (chat sessions, studio agents, admin categories) keyboard-focusable; Enter/Space activates; arrow keys move within list (where appropriate)
- [ ] All inline delete affordances keyboard-focusable; revealed on `:focus-within` of the parent (not just `:hover`)
- [ ] Hash routing: refresh on `#admin/providers` returns to providers sub-page; refresh on `#chat/sessions/<id>` returns to that session
- [ ] All 14 F1 `data-testid` attributes still present
- [ ] All 12 F2 visual snapshot baselines regenerated after top-bar restructure
- [ ] ~6 new keyboard-state snapshots captured (focused list items, focus-revealed deletes)
- [ ] ~3-4 new browser tests for hash routing (refresh persistence per area)
- [ ] WCAG 2.1.1 (Keyboard) — no `<div>`/`<span>` with click-only handlers remain in interactive contexts; verified by manual code grep + browser test asserting Tab order
- [ ] WCAG 2.4.1 (Bypass Blocks) — skip-link reaches `#main-content` from the first Tab press

### Adaptation Criteria

**Divert if**:
- Hash routing breaks the existing area switching in unforeseen ways (e.g., circular hashchange events between framework and area code) — re-converge with user; possibly defer state persistence to a sub-flight
- Form-primitive consolidation work creeps in beyond what `new-chat-restructure` needs (i.e., legs start touching `_renderProviderFormImpl`) — split form primitives to F3.5 immediately
- Top-bar app picker proves to need keyboard-shortcut support beyond what was scoped — defer the shortcut layer to F3.5; the picker still lands

**Acceptable variations**:
- Specific token names for the top bar (`--topbar-bg` vs alias to `--nav-bg` vs no new token at all)
- Skip-link visibility on focus (visible vs visually-hidden-until-focused — both meet WCAG)
- Hash-routing format details (`#chat/sessions/<id>` vs `#chat?session=<id>` — pick one and document; both satisfy the persistence requirement)
- App-picker UI variant (overlay popover, dropdown, slide-out) as long as it's keyboard-accessible

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-pre-flight-cleanup` — Land the F2 debrief immediates: add `("dark", "fg_muted", "bg")` and `("dark", "fg_muted", "surface")` to the a11y body-AA parametrize set in `tests/test_design_tokens_a11y.py`; replace `--sidebar-bg: transparent` (dark) with a declarative value (`var(--bg)` or explicit `background: none`); extract the theme toggle from `admin.js:208-270` to `App.theme.renderToggle(container, options?)` in `theme.js` (admin.js calls the helper) AND add the `theme-preference-changed` CustomEvent dispatch in `App.theme.set()` + subscriber in `renderToggle` for multi-mount sync; document the affordance pattern vocabulary in `the_one/agents.md` "Design system" section as a NEW subsection `### Affordance patterns` parallel to the existing `### Color contrast (WCAG AA)` / `### Typography scale` subsections (six patterns: info banner, outlined-cyan, filled-cyan CTA, muted-default-then-glow destructive, neutral utility, palette-island rule); add `// TODO(a11y-keyboard): convert to <button>` marker comments at the 6 keyboard-debt sites (chat.js:128 session-item, chat.js:147 .delete, studio.js:89 agent-item, studio.js:99 .agent-item-delete, studio.js chip-remove, admin.js:93 admin-category-item) AND a `// TODO(a11y-keyboard): new-chat-flow restructure` marker at chat.js:29 for leg 05. Also add the Lucide release-tag quirk and Playwright `color_scheme="no-preference"` quirk to `agents.md` browser-testing section. Tests must still pass at 391 + 20 (the new `--fg-muted` dark a11y pairs land the test count at 393).
- [x] `02-topbar-and-landmarks` — Replace `#app-nav` with `#app-topbar` containing `<h1>` "the-one" on the left and an app picker `<button aria-label="Switch app">` on the right (using the new Lucide `menu` icon — add to `icons.js` as a one-line `App.icons.menu = '<svg ...>...</svg>'` entry, fetched from lucide-icons/lucide@v0.265.0). App picker opens a popover/dropdown overlay with three keyboard-accessible buttons (Chat / Studio / Admin); active option uses `--nav-fg-active` cyan and the same `::before` left-border accent treatment ported from `.nav-item.active::before` (`base.css:38-47`). Add semantic landmarks: wrap top bar in `<header>`, sidebar in `<aside aria-label="..."> ` (per-area label set by area code), content in `<main id="main-content">`. Add `<a class="skip-link" href="#main-content">Skip to main content</a>` as the first body element; style in `components.css` under `@layer components` with `position: absolute; top: -40px; left: 0;` then `:focus { top: 0; }`, background `var(--accent)` text `var(--fg-on-accent)`. Reuse the existing `--nav-bg / --nav-fg / --nav-border / --nav-fg-active` palette island for the top bar (chrome continuity). Token migration: rename `--nav-w` → `--topbar-h: 48px` in both themes (`tokens.css:88, 176`); update `base.css` `#app-nav` rules → `#app-topbar` rules (height instead of width). Update `app.js`'s `renderNav()` → `renderTopBar()`. Layout reflow: outer flex-column (top bar above), inner flex-row (sidebar + content beside). Browser tests must pass; visual snapshots WILL FAIL (top-bar layout is a structural change) — DO NOT regenerate yet (leg 06 handles).
- [x] `03-keyboard-operability` — Convert the surviving keyboard-debt sites (the marker-commented sites from leg 01) from `<div>`/`<span>` to `<button>` (or appropriate semantic element). The 6 sites: chat session-item (`chat.js:128`), chat .delete (`chat.js:147` — must become `<button>` since `:focus-within` requires the element to be focusable), studio agent-item (`studio.js:89`), studio .agent-item-delete (`studio.js:99`), studio .chip-remove, admin admin-category-item (`admin.js:93`). Browser elements get Enter/Space via native button semantics — explicit handlers only needed if non-button elements are used. Add `:focus-within` reveal for hover-only delete affordances (CSS-only addition pattern: `.session-item:hover .delete, .session-item:focus-within .delete { display: block; }`) — the keyboard trigger is `Tab into .delete` (which `:focus-within` catches on the parent). Add `:focus-visible` rules matching the existing accent-ring pattern (`outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: 0 0 0 3px var(--accent-glow);`). Verify Tab order is sensible across each area. Note: leg 03 is independent of leg 02 (no shared files); ordering 02→03 is for narrative coherence. Browser tests must pass; visual snapshots remain pending (leg 06).
- [x] `04-hash-routing-state` — Extend hash routing to `#area/sub` format. Add optional `serializeState()` and `hydrateState(sub)` properties to the area descriptor passed to `App.registerArea({...})` (defaults: undefined → framework treats as no-op). On `hashchange` and on initial DOMContentLoaded, the framework dispatches: parse hash → if area changed, `switchTo(area)` (which fires `init` → `activate`) then `hydrateState(sub)`; if same area but sub changed, **only** `hydrateState(sub)` (init/activate skipped). Modify `switchTo` (`app.js:30-75`): the early-return at line 32 changes from "if same area, return" to "if same area AND no sub change, return; if same area AND sub differs, dispatch hydrateState only and return." On area-internal navigation that should be persistent (e.g., admin sub-page click at `admin.js:109`, session click in chat), call `serializeState()` to compute the new hash and update `location.hash` via `history.replaceState(null, '', newHash)` (NOT direct `location.hash =` — that pushes history; replaceState does NOT fire hashchange so no recursion). Implement for chat (`sessions/<id>` — current `currentSessionId` is the source), studio (`agents/<name>` — current `selectedAgent.name`), admin (`providers`/`system`/`general` — current `currentCategory`). Add ~4 browser tests asserting refresh persistence: load `#admin/system` directly → admin loads with system tab active; load `#chat/sessions/<seeded-id>` → that session is selected; load `#studio/agents/<seeded-name>` → that agent is in editor; same-area sub-nav (click admin General → click Providers) → URL updates without page churn. Visual snapshots remain pending.
- [x] `05-new-chat-restructure` — **Discovery-via-HAT leg**: the awkwardness in the new-chat flow is not pre-specified; this leg pulls user input mid-flight (Flight Director walks the user through the current new-chat flow, captures specific pain points, then implements). Current behavior: clicking "+ new" (`chat.js:29`) creates a session immediately and selects it. Likely candidates for restructure: pre-creation agent-selection, naming on creation vs after, draft mode vs persisted-on-first-message. Output: a restructured flow with all `data-testid` attributes preserved (existing testids: `new-chat-btn`, `chat-input`, `send-btn`, `message`). If form-primitive consolidation creeps in (e.g., the restructured flow needs to reuse studio's agent-select rendering), defer those parts to F3.5 and document. Note: this leg is intentionally autonomous-Developer-unfriendly — Flight Director runs it interactively, similar to leg 09 of F2 (HAT). Update the flight log with discovered requirements before implementation.
- [x] `06-snapshots-and-tests` — **Scope changed mid-flight after the snapshot-policy decision** (baselines are gitignored, never committed). Original "regenerate 12 baselines + add 8 keyboard-state baselines = 20 committed" goal is moot. Replaced with: split the snapshot suite under a new `pixel` pytest marker so CI only runs functional `-m browser` tests; document the local-only snapshot workflow in `agents.md`; land the three non-blocking a11y polish items flagged in batch-A review (chip-remove `aria-label` includes item name in studio.js × 3 sites; active picker option gets `aria-current="page"` to close the `<nav>` landmark semantic). The keyboard-navigation test additions (`test_skip_link_first_tab`, `test_picker_keyboard_open_close`) already shipped in legs 02-03. Add 4 new keyboard-state snapshot scenarios × 2 themes = **8 new baselines**: `test_snapshot_chat_session_focused` (focus ring + `:focus-within`-revealed delete), `test_snapshot_studio_agent_focused`, `test_snapshot_admin_category_focused`, `test_snapshot_app_picker_open` (overlay visible). Total baselines after leg: 20 (12 regen + 8 new). Add browser tests for keyboard navigation: skip-link reachability (`test_skip_link_first_tab` — first Tab from page load lands skip-link); app-picker keyboard interaction (`test_picker_keyboard_open_close` — Tab to picker, Enter opens, arrow keys cycle, Escape closes). Add hash-routing tests if not already added in leg 04. Total post-leg test count target: ~393 unit + ~33-35 browser (was 391 + 20 pre-F3; +2 unit from leg 01 a11y pairs; +13-15 browser across legs 04 hash-routing + 06 keyboard + new snapshots). Document the new baseline set in the flight log.
- [x] `07-hat-and-alignment` — **Absorbed into leg 05** (interactive). The substantive HAT verification work — walking through the new shell, top bar / picker / skip-link in both themes, hash-routing reload behavior, the welcome canvas across setup states, the new-chat flow, attribution / thinking / telemetry / history grouping — happened conversationally during leg 05's discovery-via-HAT execution. The user signed off ("looks good", "looks perfect", "the flow is perfect") at each visual checkpoint and explicitly waived a separate leg-07 pass: *"we pretty much already did it, we can skip it, lets do a debrief and get everything merged."* — **Required final leg** (not optional — F3 introduces structural layout + state persistence + keyboard navigation changes that benefit from real-time iteration; F2's HAT precedent showed conversational pacing catches issues no autonomous run would). Guided HAT session with the user: walk through the new top bar in both themes, verify the app picker keyboard interaction, verify hash-routing persistence on refresh in each area, verify the new-chat flow restructure. Apply token retunes / small CSS adjustments inline. User explicitly approves before flight closes. Note: leg 05 (`new-chat-restructure`) also has a HAT-style discovery component; the two interactive legs are distinct (05 elicits requirements + implements; 07 verifies the restructured shell holistically).

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] All existing tests still passing (`pytest tests/` ≥ 391)
- [ ] All F1+F2 browser tests still passing (`pytest -m browser tests/browser/` ≥ 20 + new tests for hash routing + keyboard-state baselines)
- [ ] Visual snapshot baselines regenerated for the new top-bar layout (12 retuned + ~6 new = ~18 total)
- [ ] WCAG 2.1.1 (Keyboard) verified: no remaining `<div>`/`<span>` with click-only handlers in interactive contexts (manual grep + browser test)
- [ ] WCAG 2.4.1 (Bypass Blocks) verified: skip-link reachable as first Tab from page load
- [ ] Mission `Known Issues` updated: keyboard-operability item marked closed; new known issues added if any
- [ ] Documentation updated:
  - [ ] `the_one/agents.md` — App shell section (top bar + landmarks + skip-link); hash-routing contract (per-area serializeState/hydrateState); affordance vocabulary section (carried over from leg 01)
  - [ ] `CLAUDE.md` — App shell pointer (top bar replaces nav rail; sub-page state in hash); brief note on the keyboard-operability resolution

### Verification

- Run `pytest tests/` — passes with no new failures (browser tests excluded by default marker filter)
- Run `pytest -m browser tests/browser/` — all flow tests pass + new hash-routing tests pass + new keyboard-state snapshot tests pass
- Open the app in a browser — top bar renders with app name + hamburger picker; click hamburger to switch areas; click sub-pages in admin → URL updates; refresh → returns to same sub-page
- Tab through the page from address bar — skip-link appears as first focus, then top bar, then app picker, then sidebar items, then content
- Toggle theme via the toggle (now reachable from `App.theme.renderToggle()` mount points) — both themes still render correctly
- Manual keyboard interaction check on all converted elements (chat sessions, studio agents, admin categories, inline deletes): Enter/Space activates each
- Manual screen-reader spot-check (NVDA / VoiceOver): app announces "the-one main heading", landmarks recognized, skip-link announced

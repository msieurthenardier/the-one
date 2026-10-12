# Leg: library-and-providers

**Status**: completed
**Flight**: [Model providers in Library](../flight.md)

## Objective
Make `#library` Library's own route, rendering the start page. Then bring model providers into Library as its first group, "Model providers", with the provider editor in the detail pane at `#library/providers[/~new|/{id}]`. Settings keeps hosting providers unchanged until leg 2, and the full gate is green.

## Context
- **Flight design decisions this leg implements:** DD1-DD7, DD9, DD10 (leg-1 half) and DD11 in [flight.md](../flight.md). Read them in full first. They carry the cited mechanisms, and this artifact does not repeat their detail.
- **Two halves with an in-leg checkpoint.**
  - Part A is the `#library` root (DD1-DD3, DD6's start-page rename, DD10's root migrations).
  - Part A must be green on unit and on the routing, library, mcp, agents, chats, shared and contracts lanes **before Part B starts**. Record that run in the flight log.
  - Part B is providers in Library (DD4-DD7, DD9, DD10, DD11).
- **Interim (DD11).** After this leg, providers are editable in both Settings (admin, `callbacks.host: 'settings'`) and Library. No test may open a provider editor in both hosts in one page. The old Settings provider tests stay as they are (they move lanes only, by filename glob). Leg 2 removes the Settings side.
- **Debrief carry-forwards:**
  - `studio.js` (about 4,070 lines) has one `dirty` flag shared by every studio editor. The save-create staleness guard (`agents.md` "The save-create staleness guard") must hold for providers.
  - Lane budgets are tight.
  - Known gate flakes: squawks 0168 and 0171. Re-run in isolation before treating either as a regression.
- **Operator decisions:**
  - Label "Model providers", slug `providers`, first in the list, the Add menu and the start page.
  - List rows, not tiles.
  - No HAT.
  - Old `#settings/providers` links are dropped, in leg 2.

## Inputs
- `main` at `30195e6` on branch `sortie/02-model-providers-in-library`. The planning artifacts are uncommitted in `sorties/02-model-providers-in-library/`.
- Provider code in the admin area: `the_one/interfaces/web/static/js/areas/admin.js` and `areas/admin/{provider-editor,provider-models,providers-list}.js`.
- Library orchestration in `areas/studio.js`, and the router in `static/js/router.js`.

## Outputs
- `#library` is a real route. Bare `#library/{knowledge|mcp|connectors|providers}` redirect to it, and no producer emits a bare section.
- `areas/studio/provider-editor.js` and `areas/studio/provider-models.js` (moved by `git mv`) and the new `areas/studio/providers-section.js`.
- The Library list, Add menu, start page, Jump to and router know about `providers`.
- Provider CSS is available under `.area-studio`.
- A ninth browser lane, `providers`.
- Library-route provider browser tests.
- Docs and the testid registry are updated for everything above.

## Acceptance Criteria

### Part A — the `#library` root
- [x] **AC1 — the root route.**
  - `App.router.resolve('#library')` → `{kind:'route', route:'library', sub:'library', redirected:false}`.
  - `href({destination:'library'})` is `#library`, and `lastRoute('library')` defaults to `library`. The rail's Library link opens the start page with the URL `#library`.
  - `describeRoute` speaks and titles it "Library".
  - No recursion: the bare-destination branch applies only to Settings.
- [x] **AC2 — section aliases.** `#library/knowledge`, `#library/mcp` and `#library/connectors` (and `#library/providers` once Part B adds the row), with no id or `~new`, resolve to `library` with `redirected: true`. A cold load or typed hash replaces to `#library` with one `replaceState`, and the alias is never written. Item and `~new` routes are unchanged.
- [x] **AC3 — studio's root state (DD1).**
  - `hydrateState('library')` runs `closeOpenItem()`, which bumps `editorGen`, then `setActiveSection('library')`.
  - At the root, `serializeState()` returns `library`.
  - Each helper DD1 lists has its explicit `library` branch: `isLibrarySection`, `atLibraryRoot`, `librarySelection`, `renderLibraryEmpty`, `setActiveSection`'s dispatch, studio activate, `editorOpen` and `focusClosedItem_`.
  - A save resolving after a breadcrumb go to `#library` does not move the URL back to the item. A browser test pins this on the **connector** editor:
    1. hold its save request with `page.route("**/api/connectors/**", handler)`, keeping the `route` without fulfilling it (see `test_router_guard.py`'s `route(` usage for precedent);
    2. click the breadcrumb, and assert the URL is `#library`;
    3. release with `route.continue_()`;
    4. assert the URL stays `#library` and the start page is shown.

    Do not use the mock provider's `delay_ms`, which shapes chat responses only.
- [x] **AC4 — no bare-section producers (DD2).**
  - Breadcrumbs, create-form Cancel, the Delete callbacks, `closeOpenItem`'s root, the `mcps-tab.js` and `knowledge-tab.js` links, and studio's heal and poll paths all produce `#library` (heals through `setActiveSection('library')`).
  - A new unit static check fails on any `static/js` `href({destination:'library', section:…})` without an id or create, and on any `sync('studio', '<knowledge|mcp-sources|connectors|providers>')` bare sub.
  - The "scroll to group at a section root" branch (`studio.js` ~l.731-742) is removed.
- [x] **AC5 — breadcrumb (DD3).**
  - Every Library editor header reads `Library / {Group}`, with "Library" the `editor-breadcrumb-link` to `#library` and the group as plain text. That covers the knowledge-base detail and `~new` form, MCP and connectors, plus providers in Part B.
  - Clicking it closes the item with a guarded go, then focuses the closed item's row, or its nearest visible neighbour; a `~new` form goes to the group's first row, else the Add button. This is today's DD8 focus behaviour.
- [x] **AC6 — start page testids.**
  - The page testid is `library-start`. The card Add buttons are `library-start-{group}-add`.
  - Every `library-empty-*` id is gone from `static/js`. `library-empty-` is in `RETIRED_SELECTORS` and in the registry's Retired table.
  - `tests/test_nav_helper.py::test_retired_selectors_cover_the_registry_retired_table` passes.
- [x] **AC7 — tests follow the root.**
  - `_nav.canonical` folds `library` and bare `library/{section}` → `library`.
  - The router parity corpus (`test_router_core.py`), `test_nav_helper.py` ~l.77 and `DD2_ROWS`, and the announcer root rows (`test_router_announce.py` ~l.75-76, 205-206) are updated.
  - Every `expect_route(..., "library/<section>")` on a bare section is migrated to `"library"`, so none passes through the fold. Completeness check: `grep -rnE "\"library/(knowledge|mcp|connectors|providers)\"" tests/browser` returns only item, `~new` or alias-proving uses, each a deliberate keep.
  - `_lists.library_start(page)` replaces `library_empty_state`, and all callers migrate. Completeness check: `grep -rn library_empty_state tests/` returns nothing (about 47 hits in 11 files today, including `test_router_guard.py`, `test_router_items.py`, `test_nav_guard.py`, `test_lists_helper.py` and `test_flow_studio_navigation.py`).
  - The raw-hash compare in `test_flow_studio_navigation.py` ~l.118 is updated.
  - Behavior specs naming `#library/{section}` roots or `library-empty-*` are re-authored (grep `tests/behavior/`).
- [x] **AC8 — Part A checkpoint.**
  - Unit plus the routing, library, mcp, agents, chats, shared, contracts and settings lanes are green, recorded in the flight log before Part B begins.
  - The router tests are browser tests (`tests/browser/test_router_*.py`, routing lane). There is no unit-tier router suite, so AC1/AC2 are proven only by the routing lane.

### Part B — providers in Library
- [x] **AC9 — module move (DD4).**
  - `provider-editor.js` and `provider-models.js` are moved by `git mv` to `areas/studio/`.
  - `App.studio.renderProviderEditor`, `renderProviderModels` and `renderCapabilityChips` replace the `App.admin.*` names everywhere, including the editor's internal calls and `studio.js`'s `renderCapabilityChips`. No `App.admin.renderProvider*` or `App.admin.renderCapabilityChips` reference remains.
  - The `index.html` tags sit in the studio block before `studio.js`, beside `providers-section.js`.
  - The asset-count pin is 88, with a history comment.
  - Path-keyed pins follow the files: `test_store_static.py`, `test_ui_guards.py`'s sink baseline and `test_admin_reasoning_effort_field.py`.
- [x] **AC10 — interim host (DD4, DD11).**
  - `renderProviderEditor(container, provider, providerTypes, callbacks)` honours `callbacks.host`.
  - `'settings'` reproduces today's Settings editor exactly: the `h2`, the "Settings / Providers" breadcrumb and admin's reveal. Every existing Settings provider test passes unmodified except for lane moves.
  - `'library'` gives the DD7 chrome:
    - the `h1` title; a browser test asserts the Library provider pane has exactly one `h1`, the `.editor-title`;
    - the `Library / Model providers` breadcrumb;
    - no reveal-on-open (reveal lives in `admin.js`, not the editor);
    - the `showFlash('Provider created')` at `provider-editor.js` ~l.843 suppressed for `'library'`.
  - The module's namespace init (`provider-editor.js` ~l.51 `App.admin = App.admin || {}`) becomes `App.studio`, with no stray `App.admin` init left in the moved files.
  - Admin resolves `App.studio.renderProviderEditor` at call time (click or hydrate), so `index.html` order between the admin and studio blocks does not matter. State this in a comment.
- [x] **AC11 — section module (DD4).**
  - `App.studio.providersSection.create(ctx)` returns the DD4 handle, and studio wires it once in init. `ctx` and the handle are exactly the DD4 sets; method names may vary, their count and kind may not.
  - The module reaches no studio state outside `ctx`. If it would need to, stop and signal `[BLOCKED:providers-section-interface]` (the flight's Divert criterion).
  - Pending deep links (`#library/providers/{id}` cold, and `~new`) resolve through `PENDING_KINDS`/`resolvePendingLibraryItem` with `consume(allowCache) → bool`.
  - `reset()` clears `pendingAutoSignInId`.
  - The provider create path checks the generation and that the route is still `library/providers/~new` before clearing `dirty` or syncing.
- [x] **AC12 — the Library group (DD5).**
  - `LIBRARY_GROUPS` has `providers` first.
  - Rows are `provider-card` `<a href="#library/providers/{id}">` with the name, an `App.ui.badge` type badge (the `KNOWN_BADGE_TYPES` fallback applies) and "used by" meta from `App.usage.providerAgents` through an explicit branch.
  - Pane creation and studio activate force-get four collections. `test_store.py` ~l.362-369, `test_store_library.py` ~l.30 and `agents.md`'s request-count table are updated as intended changes.
  - **Decided:** studio keeps two views of providers, both fed from the one source of truth, `App.store`'s `providers` collection.
    - The Agents list's gated `_allProviders` (~l.2305-2314) is unchanged.
    - The Library cache is fed by the new ungated subscription.

    This is documented in `agents.md`'s "Providers section" entry. It avoids changing the Agents list's `loadAllDepth` gating.
- [x] **AC13 — reachability (DD6).**
  - **Add menu:** "Model provider" (`library-add-provider`) is first and goes to `#library/providers/~new`.
  - **Start page:** a first Model providers card with `library-start-providers-add`.
  - **Router:**
    - the Library `providers` SECTIONS row (`create: true`);
    - `LIBRARY_LABELS`, destination-keyed, so "Settings — Providers" announcements are unchanged in this leg;
    - `ITEM_COLLECTIONS['library/providers']` with the noun "Model provider".
  - **Jump to:**
    - `COLLECTIONS` gains `'providers'`, and `LIBRARY` gains a FIRST row `{kind: 'provider', collection: 'providers', section: 'providers', where: 'Library · Model provider'}`. The provider rows (`data-kind="provider"`) come before knowledge bases in board order.
    - In this leg the Settings "Providers" page candidate stays (`settingsWhere` special case, `jump-to.js` ~l.121-123); leg 2 removes it. So a "provider" query lists the provider rows (Library) and the "Providers" page (Settings), in board order.
    - `test_flow_jump_to.py` ~l.54 and 659-661 are updated to the exact new order, and a test asserts a provider row's `data-kind="provider"` and its `where` text.
    - Grep for any other request-count pin that counts palette-open reads, and update it as an intended change.
  - **Copy:**
    - The chat guidance reads "Add a model provider in [Library]" → `#library/providers/~new`, and chat copy no longer references Settings for providers.
    - `chat.js` ~l.1446, `session-state.js` ~l.57 and `general-tab.js` ~l.60 say Library.
    - **Intended test change:** `tests/browser/test_flow_new_chat.py` ~l.50, 67 (the guidance link `settings/providers`) is updated. Grep the chats lane and `tests/` for assertions on the old copy strings, and update those too. These are the only Settings-adjacent tests this leg may change beyond lane moves (AC10's rule).
- [x] **AC14 — CSS (DD7).**
  - The provider editor and model-list rules apply under `.area-studio`, copied into `studio.css`. The admin copies stay until leg 2.
  - No new CSS file.
  - If the provider-type badge kinds are not already in `test_design_tokens_a11y.py`'s badge audit, they are added.
- [x] **AC15 — the `providers` lane (DD9).**
  - `scripts/run-tests.sh` has a canonical `providers` lane (`providers_pat=('test_flow_provider_*')`).
  - The plumbing is complete: `settings_pat` drops it, `shared`'s `_assigned` includes it, `LANE_LIST`, `CANON_LANES`, `BUDGET` (300 s, then measured plus about 25%), the `case` branch, `system` = settings + providers, and `--help`.
  - `tests/test_run_tests_lanes.py` passes with nine lanes. The CI and README lane wording and `CLAUDE.md`'s lane list and table are updated.
- [x] **AC16 — Library provider tests.** At least one new `tests/browser/test_flow_provider_library.py` (or similarly named, in the `providers` lane) covers, through `_nav`/`_lists` only:
  - the group is first, and rows show the badge and "used by";
  - `library_add(page, "providers")` creates a mock provider, and the create opens the item at `#library/providers/{id}` with `dirty` clear;
  - edit then Save keeps the editor and clears the unsaved caption;
  - Delete lands on `#library` with focus on the neighbouring row, or the group start;
  - a cold deep link `#library/providers/{id}` opens the editor;
  - the breadcrumb closes to `#library` and focuses the row;
  - the anthropic-plan create-to-edit re-mount starts sign-in automatically (the `pendingAutoSignInId` hand-off).
    - The seam is a context route abort of `https://claude.ai/**`, as `_block_claude_ai` in `test_flow_provider_plan_signin.py` ~l.106-109. Lift it into a shared helper (e.g. `tests/browser/_providers.py`) rather than importing across test files.
    - Mirror that file's ~l.129-180 flow at `library/providers/~new`: fill the name, click `plan-signin-btn`, then the create re-mounts and `plan-signin-consent`, `plan-signin-url` and `plan-code-input` appear with no second click.
    - `THE_ONE_OAUTH_TEST_ENDPOINT` is not needed;
  - Jump to reaches a provider;
  - the start page shows four cards in order.

  The `_lists` changes:
  - `LISTS["library/providers"]` is scoped under `[data-testid="library-list"]`, and `LISTS["settings/providers"]` under `.area-admin`;
  - `LIBRARY_KINDS` and `library_add` gain `providers`, and an unknown kind raises;
  - the registry's `provider-card` row says "studio, admin".

  No test opens a provider editor in both hosts in one page (DD11).
- [x] **AC17 — docs and registry.**
  - `the_one/agents.md`: "Library list and detail", "Hash routing" (scheme l.2264, item names l.2281, labels), the `_lists` doc l.167, the request-count table, and a new "Providers section" entry for the module interface and the interim.
  - `CLAUDE.md`: route scheme, the Library paragraph and lanes, invariants only.
  - `docs/ui-testid-registry.md`: new and renamed ids, Retired table, `jump-to-result` data-kind, `editor-breadcrumb-link`.
  - `docs/ui-control-inventory.md` where Library groups are listed.
  - The router's header comment table and the bare-destination comment describe `#library` as the start page.
- [x] **AC18 — the gate.**
  - `make test-unit` is green.
  - `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short` gives `PARALLEL_RESULT rc=0` across all nine lanes. Lane walls are recorded in the flight log, and the `providers` budget is set from the measurement.
  - The static guards pass: `test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`.
  - `ruff check` and `ruff format --check` are clean.

## Verification Steps
- AC1-AC4: the routing lane (`tests/browser/test_router_*.py`; there are no unit-tier router tests), the new static check in `make test-unit`, and `grep -rn "sync('studio', '\(knowledge\|mcp-sources\|connectors\|providers\)')" the_one/interfaces/web/static/js` (no hits).
- AC3, AC5: library and agents lanes (breadcrumb and focus tests), plus the new stale-save test.
- AC6-AC7: `make test-unit` (`test_nav_helper.py`), and `grep -rn "library-empty-" the_one/interfaces/web/static/js tests/browser` (no hits outside the retired-selector tuple and comments).
- AC8: the flight-log entry with each lane's `rc` and wall.
- AC9: `grep -rn "App.admin.renderProvider\|App.admin.renderCapabilityChips" the_one/` (no hits), and `git log --follow` on the moved files shows history.
- AC10: the settings and providers lanes pass, and the existing Settings provider tests are unmodified apart from renames and moves (`git diff --stat` on them).
- AC11-AC16: the providers lane, and `tests/test_store*.py`, `test_run_tests_lanes.py` and `test_index_asset_cache_busting.py` in `make test-unit`.
- AC17: reviewer reading, plus `grep -n "library/knowledge" the_one/agents.md CLAUDE.md the_one/interfaces/web/static/js/router.js`, where no remaining hit presents it as the root.
- AC18: the commands in AC18.

## Implementation Guidance

1. **Re-check citations.** The flight's line numbers were verified at `30195e6`. Confirm them again; they drift once Part A edits `studio.js`.
2. **Part A, router:**
   - `DESTINATIONS` Library `root: 'library'`;
   - a `library` special case in `resolve()` beside `agents`, so the bare-destination branch is Settings-only;
   - bare-section aliases in `resolve()`, modelled on `settings/general`;
   - `areaSubToRoute('studio','library')`;
   - `LIBRARY_LABELS` and the root label in `describeRoute`;
   - the header comments.
3. **Part A, studio:** DD1's helper branches, the `hydrateState` sub `library` (with `closeOpenItem()`), `serializeState`, `focusClosedItem_`'s guard, the producers (DD2) and the breadcrumbs in each editor (DD3; the knowledge-section `_breadcrumb()`, `mcp-server-editor.js`, `connector-editor.js`). Then the start-page testids, with the scroll-to-group branch removed.
4. **Part A, tests and docs:** `_nav.py`, `_lists.py`, the parity and announcer rows, the `expect_route` migrations, the new static check, the retired-selector entry and the behavior specs. Run the Part A checkpoint lanes, and log them.
5. **Part B, move:** `git mv` the two modules, rename the namespaces, add `callbacks.host` (default `'settings'` so admin's calls are unchanged; studio passes `'library'`), and update `index.html` and the path pins.
6. **Part B, module:** write `providers-section.js` against the DD4 `ctx`/handle. Model the mount and callbacks on `renderConnectorsSection` (`studio.js` ~l.1487-1568), and model the pending kind on the connector `PENDING_KINDS` entry. Copy `PROVIDER_TYPES`/`fetchProviderTypes`/`TYPE_DEFAULTS` from admin (leg 2 deletes admin's).
7. **Part B, studio wiring:** the `LIBRARY_GROUPS` row (first), delegates in the hard-coded helpers, the ungated `providers` subscription, the four-collection fetch policy, `libraryItem`'s badge and meta, the Add menu item and the start-page card.
8. **Part B, router, Jump to, copy and CSS** per AC13-AC14.
9. **Part B, lane and tests:** the run-tests.sh plumbing, `test_run_tests_lanes.py`, `_lists` scoping and providers kinds, the new Library provider tests, and the updated pinned unit tests.
10. **Docs** (AC17), then the full gate (AC18). Measure the `providers` lane and set its budget.

## Edge Cases
- **A provider whose id is exactly `new`** is unreachable at its item route: the same accepted risk as the other Library groups. Note it in `agents.md`.
- **`#library/providers/{id}` for an unknown id:** follow the connector behaviour (the pending id heals to `#library` once the load shows it absent), through `ctx.showRoot()`.
- **Dirty provider editor, then a rail or row navigation:** the router guard asks once (studio's `editorOpen`/dirty source covers providers). Continue discards and clears `pendingAutoSignInId`.
- **A provider create resolving after the user moved to another Library item:** the generation and route check blocks clearing `dirty` and the `sync` (AC11).
- **The store's `providers` notifications while the Library pane does not exist:** the subscription only updates the cache, and renders only when the pane exists (as for the other groups).
- **The agent editor's capability chips** (`renderCapabilityChips`) keep working after the rename: the agents lane covers this.
- **`#studio/providers` legacy hash** now maps to `library/providers` via `areaSubToRoute`. That is accepted; no test is needed in this leg.
- **`test_visual_snapshots.py`** (pixel-only, no lane) is not touched in this leg; leg 2 migrates it.
- **The Settings provider editor** is untouched in behaviour (host `'settings'` default). If any Settings provider test needs a change other than its lane, stop and record why in the flight log.

## Files Affected
- `the_one/interfaces/web/static/js/router.js` — Library root, aliases, providers row, `LIBRARY_LABELS`, `ITEM_COLLECTIONS`, comments
- `the_one/interfaces/web/static/js/areas/studio.js` — DD1 root state, producers, breadcrumb routing, group row, delegates, subscription, fetch policy, start page, Add menu
- `the_one/interfaces/web/static/js/areas/studio/{knowledge-section,mcp-server-editor,connector-editor,mcps-tab,knowledge-tab,general-tab}.js` — breadcrumbs, links, copy
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`, `provider-models.js` (moved from `areas/admin/`) — namespace, `callbacks.host`
- `the_one/interfaces/web/static/js/areas/studio/providers-section.js` (new)
- `the_one/interfaces/web/static/js/areas/admin.js` — calls the renamed `App.studio.renderProviderEditor` (host `'settings'`); otherwise unchanged
- `the_one/interfaces/web/static/js/jump-to.js`, `areas/chat/chat-pane.js`, `areas/chat.js`, `areas/chat/session-state.js` — Jump to, copy
- `the_one/interfaces/web/static/index.html` — script tags
- `the_one/interfaces/web/static/css/studio.css` — provider rules under `.area-studio`
- `scripts/run-tests.sh`, `ci/tasks/browser.yml`, `ci/README.md` — `providers` lane
- `tests/browser/_nav.py`, `tests/browser/_lists.py`, new `tests/browser/_providers.py` (the claude.ai block helper), new `tests/browser/test_flow_provider_library.py`, `tests/browser/test_flow_new_chat.py` (guidance link), plus every browser file with bare-section `expect_route`s or `library_empty_state` callers
- `tests/test_nav_helper.py`, `tests/test_run_tests_lanes.py`, `tests/test_store_static.py`, `tests/test_ui_guards.py`, `tests/test_admin_reasoning_effort_field.py`, `tests/test_index_asset_cache_busting.py`, `tests/test_design_tokens_a11y.py` (if badge kinds are added), `tests/browser/test_store.py`, `tests/browser/test_store_library.py`, `tests/browser/test_router_core.py`, `tests/browser/test_router_announce.py`, `tests/browser/test_flow_jump_to.py`, plus the new static check (in `tests/test_nav_helper.py` or a new `tests/test_library_routes_static.py`)
- `tests/behavior/*.md` — re-authored specs naming `#library/{section}` roots or `library-empty-*`
- `the_one/agents.md`, `CLAUDE.md`, `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`

## Execution Note
The Flight Director runs this leg with two Developer spawns: Part A (AC1-AC8, ending at the AC8 checkpoint), then a fresh Developer for Part B (AC9-AC18), which lands the leg. The Part A Developer does not mark the leg `landed`. It records the checkpoint in the flight log and reports.

## Citation Audit
The flight's Citation Audit (both Architect cycles) verified every cited mechanism against `30195e6`, which is this leg's base. No commits have landed since. This artifact cites the same locations through the flight's DDs plus `provider-editor.js:53` (`renderProviderEditor(container, provider, providerTypes, callbacks)`) and `studio.js` ~l.1453/1588/1631-1655 (`consume(allowCache)`), both verified in Architect cycle 2. Line numbers are approximate once Part A edits `studio.js`; prefer the named symbols.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

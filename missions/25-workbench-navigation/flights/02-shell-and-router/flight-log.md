# Flight Log: Shell and Router

**Flight**: [Shell and Router](flight.md)

## Summary

Planned 2026-10-01 under autonomous execution. The branch `flight/02-shell-and-router`
is **stacked on** `flight/01-control-library-foundation`: the Flight 1 PR (#217) is
waiting on the operator's merge.

---

## Reconnaissance Report

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0082 (deferred): `App.router.replaceSub` leaves `currentSub` stale | confirmed-live | `static/js/app.js:309-314`. The router research also found a second effect: the cross-area abort rollback uses the stale `currentSub` (app.js:171) | Fixed by construction in `router-and-redirects` (DD4); close in the flight commit |
| F1 debrief: 4 recurring lane flakes | needs-human-recheck | The F1 debrief's sequential run did not reproduce them | Investigate and fix in `test-navigation-helper` before the migration (DD9) |
| F1 debrief: `.visually-hidden` only in area CSS | confirmed-live | Defined in `admin.css` and `chat.css` only | Lift in `rail-and-shell` (DD7) |
| F1 open item: CI WebKit install never run | needs-human-recheck | Concourse at 127.0.0.1:8080 is unreachable | Re-check before the PR; otherwise an operator item |

---

## Leg Progress

### Leg 1: test-navigation-helper (landed, 2026-10-01)

**Flakes.** Pre-fix, each test ran 10x under load (busy loops on `nproc - 1` = 19 cores), then
10x again after the fix under the same load. The races were also forced with artificial hooks
(a pytest plugin kept outside the repo: in-page `fetch` delay, a hold-until-focus gate, and CDP
network latency). No sleep or bare timeout bump is the fix; every fix is a wait on observable app
state.

| Test | Pre-fix 10x under load | Root cause | Fix | Post-fix 10x under load |
|---|---|---|---|---|
| `test_agent_item_keyboard_select` | 8/10 (2 failed: one tile not visible in 5s, one `aria-selected` stayed "false") | Studio's first activation runs `loadAll()` twice (`init()` and `activate()` -> `_refresh()`), and each pass rebuilds the tile grid with fresh nodes. The test focused a tile from pass 1, pass 2 replaced it, and Enter went to a detached node. A fixed 5s tile wait also lost to slow boots. | `_nav.goto_settled`: waits until the app's own fetches have gone quiet (400ms with none in flight) before touching a tile | 10/10 |
| `test_studio_agent_crud_flow` | 8/10 (failures after Create: tile count 0; after Delete: `agent-empty` not found, both at 5s) | `agent-empty` is painted by `init()` before any fetch resolves (`self._agents` starts as `[]`), so it was not a readiness signal. Clicking New Agent before `loadAll()` resolves mounts the create form with no providers (`#studio-provider` empty). A late second `loadAll()` pass also re-renders the grid from a stale list. | `goto_settled` at the start; `expect_response` on the POST plus the list refetch after Create, and on the DELETE plus the list refetch after Delete | 10/10 |
| `test_editor_renders_prompt_block` | 10/10 (not reproduced naturally; F1 failure was `.editor-title` not found in 8s) | Root-caused by inspection plus hook: the editor mounts only after `GET /api/tools/configs/web_search` resolves, and the fixed 8s `expect` is the only budget for it | `goto_settled` before the assertions. Hook (9s delay on that GET): fails pre-fix with the F1 signature, passes post-fix | 10/10 |
| `test_sandbox_chip_add_remove_marks_form_dirty` | 10/10 (not reproduced naturally; F1 failure was "locator expected visible") | Root-caused by inspection plus hook: a deep-linked MCP editor mounts only after `GET /api/mcp-sources` resolves | `goto_settled` before the assertions. Hook (9s delay on the list GET): fails pre-fix with the F1 signature, passes post-fix | 10/10 |

Hook results for the two reproducing flakes: keyboard (hold the 2nd `/api/agents` response until a
tile takes focus) fails 3/3 pre-fix with `aria-selected` "false" and passes 3/3 post-fix; crud
(`/api/agents` delays 400,3000ms) fails pre-fix on `#studio-provider` empty and passes post-fix.
CPU throttling (`Emulation.setCPUThrottlingRate`, up to 20x) did not reproduce anything: the
races are about response ordering, not renderer speed. No app code was changed.

A fifth test of the same slow-boot class failed once in the library lane run
(`test_flow_studio_knowledge_inventory.py::test_item_row_failed_status_error_and_standalone_badge`,
`.area-studio .section-nav-item` not visible in 8s). It passed 3 of 3 alone. Its
`_goto_knowledge_grid` helper now uses `goto_settled`; the library lane then re-ran clean.

**Helper.** `tests/browser/_nav.py` (new): `goto`, `set_route`, `expect_route`, `current_route`,
`wait_for_route_prefix`, `href`, `open_destination`, `destination_locator`, `seg`, `legacy_hash`,
`new_hash`, `canonical`, `routes_equal`, `route_from_hash`, `goto_settled`, `wait_settled`, the
`SCHEME = "legacy"` switch and `LEGACY_URL_TESTS`. Leg 3 flips `SCHEME`; leg 5 flips the one
`LEG-5` branch in `destination_locator` / `open_destination`. `tests/test_nav_helper.py`
(unmarked): 56 tests (DD2 rows, round trip, per-segment compare, `~new` scoping, `seg`, the switch,
goto kwargs) plus the `ast` migration guard with its self-test. The guard also asserts every
`LEGACY_URL_TESTS` entry still exists and still contains a raw legacy route.

**Migration.** 43 files under `tests/browser/` changed (about 277 `_nav.goto`, 63 `expect_route`,
20 `current_route`, 8 `open_destination`, 5 `href`, 2 `set_route`, 1 `wait_for_route_prefix`).
Codemod for the regular shapes (goto, hash `==` asserts, top-bar clicks by area), the rest by hand
(`initial_hash`-style variables, `[href="#..."]` selectors, the new-chat prefix wait, the
`location.hash = ...` writes, `test_flow_cross_area_dirty_gate.py`'s area -> destination map,
`test_flow_picker.py`'s three skipped tests via `_nav.TOPBAR_BUTTON_SELECTOR`). Section-nav
clicks are unchanged. `test_flow_hash_routing.py`'s history-length test carries a comment that leg
3 inverts it (DD4).

**Legacy set (9 tests, raw legacy `goto`, asserted through `expect_route`).**
Chats: `test_flow_chat_peer_attribution.py::test_chat_renders_peer_attribution`.
Agents: `test_flow_hash_routing.py::test_studio_root_redirects_to_agents`,
`test_flow_agent_tabs.py::test_refresh_on_knowledge_tab_persists` (with a tab).
Library: `test_flow_hash_routing.py::test_studio_knowledge_section_persists_on_refresh`,
`test_flow_studio_mcp_navigation.py::test_studio_direct_load_mcp_sources`.
Settings: `test_flow_provider_grid.py::test_unknown_provider_id_falls_back_to_grid` (provider item),
`test_flow_admin_tools_grid.py::test_admin_tools_deep_link_to_tool_loads_editor` (tools item),
`test_flow_admin_navigation.py::test_admin_redirect_root_to_general` (bare `#admin`),
`test_flow_admin_navigation.py::test_admin_legacy_system_redirects_to_general` (`#admin/system`).

**Lanes.** `scripts/run-tests.sh --lane chats|agents|library|settings|shared`, aliases `chat`,
`studio` (= agents + library), `system`. `library` is an explicit 5-file list; `agents` is the old
studio globs minus it (`comm -23`); `shared` stays the complement and keeps the
`test_visual_snapshots.py` exclusion. Union check: `chats` 41 + `agents` 96 + `library` 95 +
`settings` 124 + `shared` 441 = 797 = `-m browser tests/browser/` (797); by file, 0 files in two
lanes and the union equals the 68 browser test files; the test-id sets are identical. Aliases:
`chat` 41, `studio` 191 (= 96 + 95), `system` 124.

**Gates.** `make lint` clean; `ruff format --check` clean. `make test-unit`: 4985 passed, 10
skipped (11m01s), including `tests/test_nav_helper.py` and the guard. Lanes, one at a time:
chats 41 passed (98s); agents 94 passed, 2 skipped (218s); library first run 93 passed, 1 skipped,
1 failed (290s; the fifth flake above), re-run 94 passed, 1 skipped (289s); settings 124 passed
(233s); shared 437 passed, 4 skipped (190s). None of the four fixed tests failed in any lane run.
The static JS/CSS guards were not run: no file under `static/` changed.


---

### Leg 2: confirm-dialog-native (landed, 2026-10-01)

**Built**
- `ui/modal.js`: `App.ui.modal({title, body, actions, dismissible, cancelValue, onClose, id, testid})` returns `{el (getter), open(opener), close(result), isOpen()}`. Native `<dialog>`, explicit opener and focus, Escape on the dialog (`preventDefault` and `stopPropagation`, topmost layer only), `cancel` routed through the same path, stale-`close` guard, unrouted close runs the cancel path once, backdrop click only when `dismissible` and mousedown and click both target the `<dialog>`, manual Tab wrap, DOM removal, order close/remove/restore/`onClose`.
- `dialog.js` rewritten as the `App.confirmDialog` adapter: same signature and test ids (`confirm-dialog-overlay` on the `<dialog>`), Stay `autofocus`, single-open policy retained (warn on a second call) until leg 5, Enter native.
- CSS: `.modal-overlay` restyled for the `<dialog>` (inset 0, UA resets, `display:flex` only on `[open]`), `::backdrop` on the new `--scrim` token (dark 0.5, light 0.3), added to both theme blocks in `tokens.css`.
- Reference page: `modal-section.js` retired; `ui-modal-section.js` adds the `[data-ui-demo="modal"]` demo (static card, live "Open modal" with testid `ui-demo-modal`, live "Open confirm dialog"). Cache-busting count 67 -> 68 (`ui/modal.js` added, `modal-section.js` swapped for `ui-modal-section.js`); `Makefile` verify-serving list, `test_ui_guards.py` sink baseline, the inventory (`library: App.ui.modal`), the testid registry and `agents.md` (Modals bullet, Control-library `modal` entry) updated.
- Tests: `test_ui_modal_contract.py` (24 tests x 2 engines, incl. a probe-script test), `test_ui_modal_dialog_rule.py` (the F1 `DialogAdapter` checks against the real wrapper, `backdrop_token='--scrim'`, all six checks pass with the backdrop colour verified, not xfailed, in both engines), `_probe_modal.js`.
- Dispositions: `test_modal_enter_confirms` -> `test_modal_enter_activates_focused_stay` plus companion `test_modal_tab_to_continue_then_enter_confirms`; `test_dialog_enter_confirms` -> `test_dialog_enter_activates_focused_stay` plus companion; docstrings updated. The singleton test is untouched (leg 5 inverts it). Tab-trap, aria, `.modal-overlay` selector and `to_have_count(0)` tests pass unchanged.

**Findings**
- The F1 harness's race did not need extra handling in the factory beyond `session.done`: every open builds a fresh `<dialog>`, so the stale `close` event lands on a removed element whose session is already finished. The `dlg.open` check is kept as the documented belt-and-braces guard.
- In WebKit and Chromium the manual Tab wrap excludes the `<dialog>` and card from the focusable list, so focus on either enters at the first (Tab) or last (Shift+Tab) element deterministically.

**Verification**
- `make lint` clean; `make test-unit`: 4989 passed, 10 skipped.
- Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_index_asset_cache_busting`, inventory and library-source): 264 passed.
- All `test_ui_*.py` plus the 8 confirm-using files: 452 passed, 1 skipped (the documented forced-colors skip), both engines.
- Lanes (one at a time): `settings` 125 passed; `agents` 94 passed, 2 skipped; `library` 93 passed, 1 skipped, 1 failed (`test_mcp_test_connection_button.py::test_test_connection_button_present_for_stdio_source`, locator not found; passed alone, 6 passed 1 skipped, load-sensitive flake of the earlier class); `shared` 500 passed, 4 skipped. One earlier first-run flake, `test_flow_admin_tools_editor.py::test_editor_connector_tool_shows_connectors_category`, passed alone and on a stash baseline.
- WebKitGTK probe (dev instance on 8485, scratch dir under /tmp, dev mode; `make down`, scratch removed; 8484 and the default data dir untouched), `--setup-script tests/browser/_probe_modal.js --root-selector 'dialog[open]' --url '#settings/design-language'`: dark `ok: true` (count 2, scrim `rgba(0, 0, 0, 0.5)`, `:modal` true, focus inside), light `ok: true` (scrim `rgba(0, 0, 0, 0.3)`), engine WebKitGTK 2.52.6.

### Leg 3: router-core (landed, 2026-10-01)

**AC1 engine proof (first).** `tests/browser/test_router_popstate_engines.py`, Chromium 145 and WebKit 26.0 under `THE_ONE_REQUIRE_WEBKIT=1`, on a `page.route`-fulfilled synthetic http origin: `popstate` fires (and precedes any `hashchange`) for Back/Forward across `pushState` entries, for a fragment-only `page.goto(sameURL#x)` (null state), and for an `<a href="#...">` click (null state). 6/6 pass; the `[BLOCKED:popstate-divert]` criterion did not trigger.

**Built**
- `static/js/router.js` (new, loaded right after `app.js`; cache-busting count 68 -> 69): destination table, section/alias table, route builder/parser (`href`/`parse`, `~` escaped on output), `resolve` (DD2 redirects: legacy hashes, `#agents/~new`, bare `#library`/`#settings`), `go`/`sync`, `current`/`lastRoute`/`root`/`isDeciding`, seq history with `popstate` authority and `hashchange` de-dupe, Stay (`history.go(-delta)` from the live seq, or re-push on a null state), join-the-pending-decision, boot / unknown / element-id rules. `replaceSub` is removed, no shim.
- `app.js`: registry, `App.areas` and a private `mountArea(areaId, destinationId)`; interim 4-button top bar rendered from `App.router.destinations` with `App.ui.util.el` (the `topbar.innerHTML` sink and its baseline entry are gone); boot calls `App.router.start({mountArea, getArea})`. `switchTo`, `syncUrlFromState`, `parseHash`, the area-level `hashchange` and the boot `switchTo` are removed.
- Shell bits: `#app-sidebar` hidden on Agents (`#app-sidebar[hidden]` rule in `base.css`), aside `aria-label` = destination name, `.content-panel.active[data-destination]`, top-bar `[data-destination]` + `aria-current`. `mountArea` sets the panel attribute (the panel only exists after `init`), `applyShell` does the rest.
- `App.confirmDialog.isOpen()` added to the adapter.
- Studio: (a) cleanup in `setActiveSection` (`hydrateState` captures/passes `prev`, no longer assigns `_activeSection`), same-section close in `closeOpenItem()` called from the section-root branches; (b) `_refresh` re-selects only on Agents; `doSelect` entry guard (Agents section + destination) and a `selectSeq` stale-then guard on completion (also on `doEnterCreateMode`); `tryConsumePendingSelect`/`_refresh` call `doSelect`; (c) section nav = Library only, rendered once, "Library sections", `onSelect` = `go(section root)`. Admin: `setCategory` gate deleted, `onSelect` = `go(section root)`, "Settings sections", `_setCategory` closes an open item on an unchanged category (Knowledge re-renders from saved settings). Guard sources: Continue resets `dirty`; studio `inEditor` includes `_createMode`. Read-only `_dirty` accessors on both areas for tests.

**`replaceSub` -> `sync` sites (28 originally; area explicit at each).** chat.js: 486, 1156, 1284 (`sync('chat', null)`), 1187 (`'sessions/' + id`). admin.js: 295 `providers`, 313, 337 `providers`, 325, 371, 406, 417, 526 `serializeState()`, 500 `tools`. studio.js: 516, 756, 876, 889, 1029, 1036, 1142 `serializeState()`; 543, 584, 596, 652 `knowledge`; 730, 748, 803 `mcp-sources`; 953 `connectors`. admin `doSetCategory`'s site was deleted with the gate (section nav is `go()` now); one `sync('admin', serializeState())` was ADDED at admin.js:371: a dead provider id (absent from a fresh `/api/providers` fetch) heals to `settings/providers`. That is the minimum the AC11 tightening of `test_unknown_provider_id_falls_back_to_grid` needs; full per-call-path dead-id handling stays in leg 04.

**Deleted gates.** studio section-nav `_confirmLeaveImpl(commit, ...)` with its `commit()` cleanup; admin `setCategory` dirty gate and `doSetCategory`; app.js cross-area `confirmLeave` + rollback (`priorHash`).

**Seams left for leg 04 (untouched).** `mcps-tab`'s own `hashchange` listener and its `#studio/...` hrefs, `knowledge-tab`/`welcome.js` legacy hrefs (they redirect), `markdown.js`, item-open `sync` sites (still replace; Back crosses sections), `activate`-time double load, dead ids for studio/tools.

**Test migrations.** `_nav.SCHEME = "new"`; `destination_locator` scoped to `#app-topbar [data-destination=...]`; new `destination_panel` (`.content-panel.active[data-destination=...]`); `open_destination` clicks all four buttons. 10 files: "Agent Studio sections" probes -> `destination_panel`. "System sections" -> "Settings sections" (keyboard, cross_area_dirty_gate). `test_flow_studio_navigation.py` rewritten against the Library-only nav (3 buttons, Agents has no nav / hidden aside, restore-after-Library-trip inverted and renamed `test_agents_destination_restores_open_agent_after_library_trip`, current-destination click kept as `test_current_destination_click_returns_to_agent_listing`). `test_flow_hash_routing.py`: history-growth test inverted and renamed `test_hash_routing_section_nav_pushes_history`; the two legacy entries survive as redirect proofs. `test_flow_dirty_confirm.py` / `test_flow_studio_mcp_navigation.py`: Agents -> Library nav clicks -> `open_destination('library')`, Library nav now 3 entries. `test_studio_mcps_tab.py` and `test_flow_new_chat.py` (welcome links): redirect-tolerant href checks (the in-app links keep their legacy form until leg 04). `test_flow_provider_grid.py` unknown id tightened to `settings/providers`. `test_flow_admin_knowledge_settings.py`: squawk 0082 workaround removed. `tests/test_nav_helper.py`: guard exempts `test_router_*.py` at file level (stated in the guard, self-tested). New: `test_router_popstate_engines.py` (6), `test_router_core.py` (59: round trip, `~` encoding, 28 redirect rows + traversal redirect, JS<->`_nav` parity corpus, boot/unknown/element-id, commit sequence, no re-activation, sync drop rules incl. chat auto-join from Settings, seq/Stay/Continue/joins, 0082), `test_router_guard.py` (15: AC8 a-g and i, AC9 leak regression, dead-id restore heal).

**Findings**
- `ERR_NETWORK_CHANGED` on this WSL host: several lane failures (a different 2-4 tests per run, always a deep-link boot where a static script like `studio.js` failed to load) were NOT regressions. A 120-iteration reproduction loop caught two, both with `reqfail ... net::ERR_NETWORK_CHANGED` on `/static/js/...`, leaving the page without the studio area. They passed alone and the following full-lane runs were clean. Recorded for the debrief, not fixed (host network flap).
- A `page.evaluate("window.__p = App.router.go(...)")` of a held promise hangs forever (Playwright awaits the assigned promise); use a block body.

**Verification**
- `make lint` clean; `ruff format --check` clean. Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_index_asset_cache_busting`, `test_nav_helper`, `test_ui_control_inventory`) pass.
- Lanes, one at a time: chats 41 passed (after the welcome-link tolerance fix; first run 39 + 2 expected failures, fixed); agents 96 passed, 2 skipped; library 94 passed, 1 skipped; settings 125 passed; shared 580 passed, 4 skipped. Earlier agents runs had 3-4 `ERR_NETWORK_CHANGED` failures (above); the load-flake tests named in the leg (`test_test_connection_button_present_for_stdio_source`, `test_editor_connector_tool_shows_connectors_category`) did not fail.
- WebKitGTK probe (dev instance on 8485, scratch under /tmp, `make down`, scratch removed; 8484 untouched), `--root-selector body`, dark and light: `#agents` 17 controls, `#settings/general` 21 controls. Both report the SAME single legacy failure in both themes: the hidden chat panel's `<input type=file data-testid=chat-image-input>` has no accessible name (pre-existing; not a router regression; recorded, not fixed).
- `make test-unit`: 4989 passed, 10 skipped, 1021 deselected (10m51s). Every `test_ui_*.py` plus `test_confirm_contract.py` in both engines with `THE_ONE_REQUIRE_WEBKIT=1`: 305 passed, 1 skipped (the documented forced-colors skip). Router + dirty-confirm + hash-routing files in both engines (WebKit required): 108 passed. The chats lane re-ran 41/41 after the welcome-link fix.

### Leg 4: item-history-and-exact-rendering (landed, 2026-10-01)

**Built.** `router.js` passes `hydrateState(sub, {fresh})` (true: traversal/boot/typed; false: `go()`). Studio: item opens are `go()`; exact-render root branches; `skipSectionRender` for agent/MCP items inside the showing section; `resolvePendingAgent`/`tryConsumePendingSelect(fresh)` with dead-id heal (also empty inventory), `_kbFresh` cache bypass + KB status-404 heal, MCP dead-id heal after the fresh list, `_closeMcpForm`, `serializeState` prefers a pending agent, `closeOpenItem` always empties the editor and clears the MCP focus. Admin: item hydrate skips `_setCategory` inside the showing category (`_closeOpenItem`), single-flight `fetchProviders`, fresh hydrate refetches, tool 404 heals and the pending tool name persists until loaded. Chat row = `go`. Links via `App.router.href`; `mcps-tab.js` has no `hashchange`/URL parsing. All inline gates of converted paths deleted; `enterCreateMode` and connector gates kept. Docs: `the_one/agents.md` router contract.

**Deviation.** Save rename stays `sync` (table row 26), not the pre-decided bypass `go()`.

**Tests.** New `tests/browser/test_router_items.py` (31: AC2-AC7 incl. the one-dialog-per-intent matrix, MutationObserver no-flash with request counting, dead ids, Chats join frames, MCP focus, source grep). Flipped `test_router_guard.py::test_dirty_agent_browser_back_one_dialog` (item opens push, so Back lands on the Agents root first).

**Verification.** Lanes one at a time: agents 96 passed 2 skipped; chats 41; library 94 passed 1 skipped; settings 125; shared 611 passed 4 skipped (after the `closeOpenItem` fix a first agents run caught: `test_save_after_concurrent_delete_falls_back_to_empty`). `make lint` and `ruff format --check` clean; `make test-unit` 4989 passed, 10 skipped. All `test_ui_*`, `test_confirm_contract` and `test_router_*` with `THE_ONE_REQUIRE_WEBKIT=1`: 415 passed 1 skipped plus one load-flaky `test_router_items` test per run (a different one each time: provider/kb/agent/tool/session; all pass alone and in repeated full-file runs, no `ERR_NETWORK_CHANGED` seen in the captured runs; recorded as load flake). Static guards pass.

**Per-call-path disposition table** (generated from a grep of `writeUrl_`, `App.router.sync(`, the grid `onSelect*` callbacks and the Back/Cancel handlers; line numbers are post-leg-3 and drift). Dispositions: GO = intent `go()` (push, router guard only); BYP = `go({replace:true, bypassGuard:true})`; SYNC = `sync` (replace, no hydrate); DEL = URL write deleted.

| # | file:function | before | after | reason |
|---|---|---|---|---|
| 1 | studio.js section-nav `onSelect` | go | GO (unchanged) | leg 3 |
| 2 | studio.js `selectKnowledgeBase` (KB tile) | sync + local render | GO `library/knowledge/{id}` | item open is an intent; hydrate renders the detail |
| 3 | studio.js `renderKnowledgeDetailView` 404 catch | sync root | SYNC root | a detail LOAD finding the item gone heals in place |
| 4 | studio.js `mountKnowledgeDetail` status 404 (new) | none (stuck "Failed to load") | SYNC root | cached KB deleted meanwhile (dead id) |
| 5 | studio.js KB detail `onBack` | inline confirmDialog + sync | GO `library/knowledge`, gate deleted | one dialog per intent |
| 6 | studio.js KB `onDeleteSuccess` | sync | BYP root (`leaveKnowledgeDetail_`) | post-delete navigation |
| 7 | studio.js KB poll 404 bounce | sync | BYP root | navigation away from a detail that vanished while open |
| 8 | studio.js MCP editor `onBack` | inline gate + sync | GO `library/mcp`, gate deleted | |
| 9 | studio.js MCP `onCancel` (create) | sync | BYP root | intentional discard, no gate; replaces the create entry |
| 10 | studio.js MCP `onSaveSuccess` | sync | SYNC | completion (create entry becomes the item route) |
| 11 | studio.js MCP `onDeleteSuccess` | sync | BYP root | post-delete |
| 12 | studio.js `selectMcpSource` (grid row) | sync + local render | GO `library/mcp/{id}` | intent |
| 13 | studio.js `enterCreateMcpSourceMode` | sync + local render | GO `library/mcp/~new` | intent (route exists) |
| 14 | studio.js MCP section fetch `.then` (new) | none | SYNC root on dead pending id | dead-id heal against a fresh list |
| 15 | studio.js connector `doHandleBack` | sync | DEL (inline gate KEPT) | URL-less this flight |
| 16 | studio.js `selectConnector`, `enterCreateConnectorMode` | sync | DEL | URL-less this flight |
| 17 | studio.js agent tile click/Enter (`selectAgent`) | inline gate + doSelect | GO `agents/{name}` (`openAgent`), gate deleted; `selectAgent` removed | intent |
| 18 | studio.js `doSelect` completion `writeUrl_` | sync | SYNC | completion |
| 19 | studio.js `doEnterCreateMode` `writeUrl_` | sync | SYNC (inline gate on `enterCreateMode` KEPT) | create is URL-less |
| 20 | studio.js `onSelectedMcpSourceChange` | sync | SYNC | focus refinement replaces |
| 21 | studio.js `setActiveTab` | sync | SYNC | tab refinement replaces |
| 22 | studio.js `handleBack` / `doHandleBack` | inline gate + writeUrl_ | GO `agents`, gate and `doHandleBack` deleted | |
| 23 | studio.js `cancelEdit` (create mode) | doHandleBack | BYP `agents` | URL-less create; discard is intentional |
| 24 | studio.js `handleDeleteEditor` post-delete | selectAgent / writeUrl_ | BYP first agent / BYP `agents` | post-delete |
| 25 | studio.js save-create | selectAgent | BYP `agents/{name}` | replaces the URL-less create entry |
| 26 | studio.js save rename | writeUrl_ | SYNC (deviation from the pre-decided BYP) | the editor is already rendered; a hydrate would re-fetch and re-render it and lose the "Saved" flash. sync already rewrites the route to the new name |
| 27 | studio.js save->delete race | selectAgent / writeUrl_ | BYP first agent / BYP `agents` | navigation to a different item |
| 28 | studio.js `resolvePendingAgent` dead id (new) | pending forever | SYNC `agents` | dead-id heal |
| 29 | admin.js section-nav `setCategory` | go | GO (unchanged) | leg 3 |
| 30 | admin.js provider `onBack` | inline gate + sync | GO `settings/providers`, gate deleted | |
| 31 | admin.js provider `onCancel` (create) | sync | BYP root | |
| 32 | admin.js provider `onSaveSuccess` | sync | SYNC | completion |
| 33 | admin.js provider `onDeleteSuccess` | sync | BYP root | post-delete |
| 34 | admin.js `fetchProviders` dead id | sync (leg 3) | SYNC | dead-id heal |
| 35 | admin.js `selectProvider` (grid row) | sync + local render | GO `settings/providers/{id}` | intent |
| 36 | admin.js `enterCreateMode` (provider) | sync + local render | GO `settings/providers/~new` | intent |
| 37 | admin.js tools `onBack` / `exitEditor` | inline gate + sync | GO `settings/tools`, gate deleted | |
| 38 | admin.js tool row (`onSelectTool`) | `selectTool` | GO `settings/tools/{name}` (`openTool`); `selectTool` = hydrate/consume loader | intent |
| 39 | admin.js `selectTool` success | sync | SYNC | completion |
| 40 | admin.js `selectTool` 404 | flash only | SYNC `tools` + close editor | dead id |
| 41 | chat.js session row `onJoin` | `joinSession` | GO `chats/{id}` (hydrate joins once) | intent |
| 42 | chat.js `startSessionWith`, `pendingStart` drain, `session_joined`, `session_deleted` | sync | SYNC (unchanged) | completions / Flight 4 redesigns Chats |
| 43 | app.js rail/top-bar | go | GO (unchanged) | leg 3 |
| 44 | knowledge-tab.js / mcps-tab.js (x2) / welcome.js (x2) links | legacy hrefs | `App.router.href` new scheme | links |

### Leg 4 follow-up: third session and file flakiness (2026-10-01)

**Third session: a real, pre-existing app bug (not introduced by Legs 3-4).** `chat.js` `startSessionWith` sets `pendingStart` and sends `new_session` on an open socket, but only `session_joined` clears `pendingStart`. The post-join `refreshSessionList()` reply (and any `session_list`) that lands between the new-chat send and its `session_joined` hit the list handler's queued-intent drain, which re-sent `new_session`: a duplicate session. Under load the test clicked New chat right after the first join, inside that window. The Leg 3/4 `sync` swaps did not touch the drain. Reproduced deterministically (a new test delays `list_sessions` 0.8s and `session_joined` 1.5s via an init script; it failed before the fix with 3 sidebar rows).

**Fix (minimal, `chat.js`).** `pendingStart` gains `sent`: set true after a direct send on an open socket; `ws.onclose` resets it to false (a dropped socket re-drains on reconnect); the `session_list` handler returns early (after rendering the list) when `pendingStart.sent`, skipping both the re-send and the auto-join that would race the join. The queued path (WS closed at click time) is unchanged.

**AC6 evidence.** `test_session_row_pushes_and_joins_once` now records `join`/`new_session` frames: two `new_session` for the two seeded chats and exactly two sidebar rows; a row click yields exactly `[("join", s1)]` (no create), `history.state.seq` +1 (pushed), the row becomes `.active`; Back yields exactly `[("join", s2)]`, lands on the previous session's route, still two rows. New `test_new_chat_before_pending_session_list_creates_exactly_one_session` pins the race.

**Flake causes and fixes (`test_router_items.py`).** No shared module-scoped state (every test uses a per-test app fixture). Racy spots, all state-driven now: immediate `assert _area(...) is None/False` after a heal or close replaced by `wait_for_function` helpers (`_wait_area_none`, `_wait_area_false`); the two fixed `wait_for_timeout(500/300)` before those asserts removed; 5s timeouts raised to 8s; the pre-watch `wait_settled` in the four no-refetch tests widened to `quiet_ms=1500` (a second inventory load more than 400ms after the first looked like an intent refetch under load). The remaining fixed sleeps are negative assertions only (no second dialog) and the post-race drain window.

**Under load** (busy loops on nproc-1 = 19 of 20 cores, load avg ~20, script outside the repo, stopped afterwards), `-p no:cacheprovider`: before the hardening 7 consecutive 32/32 runs plus 2 runs with 3 sporadic failures (`dirty_kb_back`, `provider_open_no_refetch`, `connector_editor_closed`; not reproduced, root-caused by inspection to the races above); after: 5/5 consecutive runs 32 passed; once with `THE_ONE_REQUIRE_WEBKIT=1` 32 passed (load off).

**Gates.** `make lint` and `ruff format --check` clean; `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y` 222 passed; `--lane chats` 41 passed; `--lane shared` 612 passed 4 skipped (a first run had one unrelated `test_theme_cross_tab_sync` 5s timeout while another process held ~200% CPU; passes alone and on the clean rerun).

### Leg 5: unified-leave-guard (landed, 2026-10-01)

- **Built.** `static/js/nav.js` (loaded right after `router.js`; `App.confirmDialog`/`App.router` are looked
  up lazily): `registerSource`, `isDirty`, `isPending`, `confirmLeave(ctx)`, `_sources`, the single
  `beforeunload` listener and the bubble-phase `a[href^="#"]` interceptor. Studio and admin each register one
  source (`isDirty = dirty && editorOpen()`, the ported predicates). Removed: both `_confirmLeaveImpl`, both
  area `confirmLeave` descriptors, both per-area `beforeunload` listeners, and the two inline gates
  (connector editor Back, agent `enterCreateMode`), which now call `App.nav.confirmLeave({caller, opener})`.
  After this leg `App.confirmDialog(` has no literal call sites outside the design-language demo
  (`tests/test_nav_guard_static.py` pins it, plus one `beforeunload` holder and no `confirmLeave:` descriptors).
- **Router adapter.** `runGuard()` keeps the synchronous fast path (the `test_router_core` commit-sequence
  tests pass with only their guard spy re-pointed from `studio.confirmLeave` to `App.nav.isDirty`, and
  `_hold_guard` from the area hook to `App.nav.confirmLeave`). `go()` takes `{opener}`; the interim top bar
  passes the clicked button.
- **Discard** is teardown only. Studio `discardOpen_` = `closeOpenItem()` + `sectionContentEl` clear for
  non-agent editors; admin `_discardEditor` = `_closeOpenItem()` (or `dirty=false` on the knowledge page). Both
  reset `dirty` in a `finally` (a throwing discard still navigates). Per-area `editorGen` is bumped by every
  teardown; the provider/MCP/connector/tool/KB save and type-wait resolvers capture it and bail (proved by the
  in-flight provider-save test). Vanish/bounce paths call discard (KB poll 404 / KB delete, MCP delete,
  provider delete, agent post-delete and the save-to-delete race); post-save bypasses do not.
- **Deviations from the leg text.**
  1. Router order: `dialogOpen() || App.nav.isPending()` is checked BEFORE `isDirty()` (the leg sketch checked
     dirtiness first). A clean traversal/go with an unrelated confirm open previously resolved Stay and two
     pinned tests (`test_traversal_with_nonrouter_dialog_open_reverts_as_stay`,
     `test_go_with_dialog_open_resolves_stay_and_syncs_continue`) rely on it; both checks are synchronous.
  2. Admin needed `editorDomStale`: a state-only discard leaves the editor DOM mounted and the root hydrate's
     `_setCategory` skipped re-rendering (item no longer "open"). The flag forces the one re-render and is
     cleared by every panel render.
  3. `_dirty` on both areas gained a setter, as the test seam the leg's AC8 requires (stale flag, no editor).
  4. The agent tile list and `new-agent-btn` are hidden while an editor is open, so "item selection while
     dirty" and `enterCreateMode` are not reachable by a real click in the current layout; their tests drive
     the tile/button handler with `dispatch_event("click")`.
- **Tests.** New `tests/browser/test_nav_guard.py` (34 incl. params; the focus tests run in Chromium AND WebKit
  through `engine_browser` + `credentialed_context`; the real-reload `beforeunload` test is Chromium-only per
  the leg) and `tests/test_nav_guard_static.py` (3). `test_singleton_modal_second_call_warns` became
  `test_second_confirm_stacks_above_first`; asset-count pin 69 -> 70.
- **Verification.** `make lint` clean; unit suite 5033 passed; static guards (`test_ui_guards`,
  `test_token_definitions`, `test_design_tokens_a11y`) green; shared lane (all `test_ui_*` in both engines,
  `THE_ONE_REQUIRE_WEBKIT=1`) 646 passed; chats 41 passed; settings 125 passed (first run 2 load failures, both
  pass alone and on lane rerun); agents 96 passed (first run `test_delete_agent_confirm_lapse...` panel
  timeout + an `ERR_NETWORK_CHANGED`, clean on rerun); library: two runs each had 1-2 `save-mcp-source-btn`
  not-visible failures in DIFFERENT mcp-editor deep-link tests (`_nav.goto`, not settled), every one passing
  alone and the whole file passing (52); same load-sensitive class already recorded at leg 2; none involves
  a dirty editor or the guard. Recorded for the debrief.
- **Docs.** `agents.md` "Leave guard (`App.nav`)" (inside the router section; replaces the "Interim guard"
  paragraph) and the Modals bullet; CLAUDE.md router pointer; stale comments (router header and null-state
  branches, studio deactivate, `knowledge-section.js`, `modal.js`, `dialog.js`, test docstrings).

### Leg 5 follow-up: library-lane `save-mcp-source-btn` flake

**Classification: neither (a) nor (b) as the sole cause; the dominant cause is environmental (c).**

- **(b) ruled out.** Hook (init-script `fetch` delay on `GET /api/mcp-sources`, 5s and 12s) with a deep link to an MCP source and a 20-25s mount wait: the editor mounts both times, so the pending id is neither dropped nor bailed by Leg 4's fresh-list consumption or Leg 5's `editorGen` guards. A 10s-delay regression test is now in `test_flow_studio_mcp_editor.py::test_deep_linked_editor_mounts_after_slow_list_fetch`.
- **(a) is real but secondary.** The mount waits on the list fetch, so a plain `_nav.goto` plus an 8s `expect` can lose to a slow list. Fix: every `_nav.goto` in the five library-lane files is now `_nav.goto_settled`, and `goto_settled` additionally waits (30s, attached) for `save-mcp-source-btn` on `library/mcp/{id|~new}` routes, because "fetch-quiet 400ms" is only a heuristic (a settled page was seen still showing the grid).
- **Dominant cause: Chromium `net::ERR_NETWORK_CHANGED`.** A diagnostic pytest plugin (kept in the scratchpad, not the repo) printed page console/requestfailed/DOM on failure. Failing tests showed `REQFAIL` + `ERR_NETWORK_CHANGED` for `/static/js/*.js` and for `/api/tools`, `/api/mcp-sources`, `/api/knowledge-bases`, `/api/providers` together, with the DOM at "Failed to load MCP sources." The host (WSL2; `ip -br addr` shows eth1 with IPv6 addresses) emits network-change events; Chromium then aborts in-flight loopback requests. A 25-iteration probe of a plain deep link measured 0.17-0.20s each, and a host-gap heartbeat showed no stalls, so it is not slowness. Failures hit a random 1-4 tests per lane run in unrelated files (also tests with no MCP fetch). An in-conftest "repeat goto on ERR_NETWORK_CHANGED" mitigation did not reduce the rate (4 failures in the run that used it) and was reverted. Chromium has no flag to disable the notifier.
- **Lane results.** After the changes: passes 95/1 skipped on 3 of 9 full runs; the other runs each failed 1-4 tests, every diagnosed one with ERR_NETWORK_CHANGED (and none an editor-mount bug). The "3 consecutive green runs" bar was NOT met on this host. Agents lane: 96 passed, 2 skipped. `make lint` equivalent (`ruff check` / `ruff format --check`): clean. `static/` untouched this follow-up.
- **Open:** `tests/test_nav_helper.py::test_no_raw_route_hashes_in_browser_tests` fails on `tests/browser/test_nav_guard.py:540` (`/^#chats\/.+/` raw hash in a JS string); not touched here.

### Leg 5 follow-up 2 (network isolation)

- `scripts/run-tests.sh`: opt-in `THE_ONE_TEST_NETNS=1` runs pytest under `setsid unshare -rn sh -c 'ip link set lo up && exec ...'` (loopback-only namespace; same process group, so the watchdog group-kill and env passthrough are unchanged). A pre-flight probe fails loudly (exit 2, message) if `unshare -rn`/`ip` is unavailable; no silent fallback.
- Nothing in the browser suite needed external network; Playwright driver, Chromium, and the userland WebKit wrapper all work inside the namespace.
- Results with the namespace: `library` 3/3 green (95 passed, 1 skipped each); `agents` 96 passed/2 skipped; `settings` 125 passed; `chats` 41 passed; `shared` (THE_ONE_REQUIRE_WEBKIT=1) 646 passed/4 skipped. No ERR_NETWORK_CHANGED failures.
- Guard fix: `test_nav_guard.py` raw `#chats/` JS regex replaced with `_nav.wait_for_route_prefix(page, "chats/")`. `make test-unit` 4992 passed/10 skipped; `make lint` clean.
- Docs: CLAUDE.md Testing and agents.md "UI test apparatus" note added.

### Leg 6: rail-and-shell (landed, 2026-10-01)

- **Built.**
  - `static/js/ui/rail.js`: `App.ui.rail({items, currentId, brand, label}) -> {el, setCurrent, setHref, destroy}`.
    Plain `<a>` links with no click handler, never reads `App.router`; initialises the single tab stop itself
    (current item 0, others -1, first item when none is current) and re-asserts it in `setCurrent`; reuses
    `util.rovingFocus` (clamped). `label` (default "Main") lets the reference-page demo avoid duplicate landmark names.
  - `router.js`: `App.router.onCommit(fn) -> unsubscribe`, called from `applyShell` (step 5) on every commit
    including boot; a throwing subscriber is swallowed; the `#app-topbar` loop is deleted. Library `iconKey` is now
    `database`. `icons.js`: `database` added (B3's Library glyph, with `focusable="false"`).
  - Shell: `index.html` has `<div id="app-rail">` (the `<header id="app-topbar">` is gone) inside the flex
    `.app-shell-row`; `app.js` `renderTopBar` -> `mountRail` (mounts the rail with the 24px brand mark, `alt` = "GleepGlorp AI";
    hrefs refreshed from `onCommit`: current -> root, others -> `lastRoute`). Removed: top-bar CSS, `.app-brand*`,
    `.app-picker-button*`, `nav-chat-btn` (+ registry row), `--topbar-h`, the wordmark, and the surfaces-section
    `app-picker-button` sample. `base.css`: `#app-rail`, and `@media (max-width: 1279px) { #app-sidebar { width: 200px } }`.
  - `.visually-hidden` is defined once, in `components.css`; removed from `admin.css` and `chat.css`.
  - Copy: welcome.js "Settings" / "Agents"; chat.js "Add a provider in Settings to continue this conversation.";
    mcps-tab.js "Add one in the Library." (a `textContent` assignment; sink baseline unchanged). Tests updated:
    `test_flow_new_chat.py`, `test_flow_provider_setup.py`, `test_studio_mcps_tab.py`.
  - Demo: `[data-ui-demo="rail"]` in `ui-lists-section.js` (hrefs `#main-content`, Agents shown current).
    Inventory: the "App picker (top bar)" row became "Rail (destination links)" -> `library: App.ui.rail`.
    Registry: `nav-chat-btn` removed, parametric `rail-` added.
- **Tests.** New `tests/browser/test_ui_rail_contract.py` (21 cases x 2 engines: API/markup, tab stop, ArrowUp/Down/Home/End
  clamped, `setCurrent`/`setHref`, throws, no document listener, resolver, focus ring with a positive control in both
  themes, and `.visually-hidden` with only `tokens.css` + `components.css` loaded) and `tests/browser/test_shell_rail.py`
  (16, Chromium: shell structure, landmarks, aside hidden on Agents, skip link, geometry at 1024/1279/1280/1440, no clipping
  at 1024, rail geometry/colour in both themes, hrefs + restore, modifier clicks, icons, `onCommit`). `_nav.destination_locator`
  /`open_destination` flipped to `[data-testid=rail-<id>]`; `TOPBAR_BUTTON_SELECTOR` removed; `test_flow_picker.py`'s three dead
  skipped tests removed (skip-link test kept); `test_nav_guard.py` rail trigger (focus return asserts `rail-library`);
  `_TOPBAR_MARKERS` gained `#app-topbar`. A11y gates: `test_rail_label_pairs_pass_body_aa` (rest, hover, current wash,
  both themes) and `test_rail_rules_consume_the_gated_pairs`. Asset-count pin 70 -> 71.
- **Reference spec section 2: measured (Chromium, computed style, 1440x900, both themes) vs spec.** Rail 72 x full height,
  `--surface` ground, `1px solid --border` right edge; items 60 x 53, pitch 59 (tops at y 54/113/172/231: the spec's 58/117/176/235 less 4px for the 24px brand mark),
  icon 18 x 18, label 10px / 400 below the icon with a 4px gap, radius 6px, 1px transparent border; brand 24 x 24 at y 12;
  inactive `--fg-secondary` on transparent; hover `--surface-elevated` + `--fg`; current `--fg` ink, wash
  `rgba(167,139,250,.10)` dark / `rgba(109,40,217,.08)` light, inset 1px `--accent` ring. Item width/height and pitch match
  the spec exactly.
- **Recorded deviations (SC8 evidence).**
  1. Destinations are `<a>`, not `<button>` (DD7).
  2. The active marker is the DD14 wash plus inset ring, not `border-color: var(--accent)` (the 1px border stays transparent,
     so geometry is unchanged).
  3. Hover is `--surface-elevated` (section 2 defines none).
  4. Brand mark 24px, not 28px (no non-integer pixel-art scale).
  5. The Jump-to control (44px ghost, Ctrl K) is out of scope (Flight 4).
  6. New, fixed in the implementation: `padding: 12px 1px 12px 0` on the rail so the 1px right border does not push the
     60px items to half-pixel offsets (items at x 5..65).
  7. Focus uses the spec's pinned form (`outline: 2px solid var(--accent); outline-offset: 2px`), where `listPane` rows use an inset ring.
- **Leg-text correction.** The leg said the Makefile `verify-serving` list was affected; no `areas/` file was added, so it is unchanged.
  `renderTopBar` had no inner-HTML sink or baseline entry left to retire (it used `textContent`/`el`).
- **Verification.** `ruff check` + `ruff format --check` clean (`test_router_items.py` was already unformatted at the start of the
  leg and is now formatted). `make test-unit` equivalent: 5039 passed, 13 skipped. Static guards (`test_ui_guards`, `test_token_definitions`,
  `test_design_tokens_a11y`, `test_ui_control_inventory`, `test_nav_helper`, cache-busting) green. Lanes, one at a time, with
  `THE_ONE_TEST_NETNS=1`: chats 41; agents 96 (+2 skipped); library 95 (+1 skipped); settings 125; shared (`THE_ONE_REQUIRE_WEBKIT=1`,
  includes every `test_ui_*` in both engines) 704 passed, 1 skipped (was 4: the three dead picker skips retired). No reruns needed.
- **WebKitGTK probe** (WebKitGTK 2.52.6, dev instance on 8485, scratch data dir, torn down and removed): `#agents`, `#settings/general` and
  `#chats` with `--root-selector body`: the rail resolves cleanly; the only failure each time is the known squawk 0110
  (`chat-image-input` has no accessible name). `#settings/design-language` with `[data-ui-demo="rail"]` (light): ok, 8 controls.

### Leg 7: client-data-store (landed, 2026-10-01)

`static/js/store.js` (`App.store`, ES5, loaded after `api.js`; asset count 71 -> 72) for
`agents` and `providers` only. `get` rejects on failure and `peek` keeps the last good value;
`invalidate` is generation-safe; `subscribe` fires after every successful load. Docs:
`agents.md` "Client data store (`App.store`)" and a CLAUDE.md pointer.

**Leg 1 anomaly (double load).** Confirmed a fetch-site duplicate, not a router leftover: the
module's `init()` and `activate()` -> `_refresh()` each ran `loadAll()`. For agents and
providers the two now share one store request (boot `loadAll(true)`; `_refresh` `force` joins
the in-flight one). The same double pass still exists for tools, MCP sources, KBs and model
caps (below). `GET /api/agents` does not include the synthetic default agent (store holds what
the API returns).

**Request counts** (GET list routes, Playwright request log; "before" derived from the code at
the start of the leg, "after" asserted by `test_store.py::test_request_counts_per_activation`
and the two cold-boot tests):

| Scenario | agents before -> after | providers before -> after |
|---|---|---|
| Chats cold boot (ws.onopen) | 2 -> 1 | 1 -> 1 |
| Chats re-activation | 2 -> 1 | 1 -> 1 |
| Agents cold boot (init + activate) | 2 -> 1 | 2 -> 1 |
| Agents <-> Library (no module re-activation) | 0 -> 0 | 0 -> 0 |
| Settings -> Providers cold boot | 0 -> 0 | 1 -> 1 |

**Invalidation sites** (`App.store.invalidate`): `studio.js` agent create, rename, PUT, delete
and `_refreshAgentAfterSelfConfigurationChange` (the single funnel for self-configuration
enable/disable, approval-mode, revision approve/dismiss/restore); `knowledge-section.js` KB
rename and delete (agents); `mcp-server-editor.js` MCP delete and connection reset (agents);
`provider-editor.js` create/save, delete, OAuth code exchange and sign-out (providers).
Admin `toolConfigs` mutations are out of scope.

**Design notes.** Chats' two reads were folded into `refreshAgentsAndSetup` (one read of each
per activation; failure keeps the prior setup state; `_fetchAgents`/`_checkSetupState` seams
replaced by `_refreshAgentsAndSetup`; no test used them). Studio subscribes to both
collections: a load it did not start replaces `self._agents`/`self._allProviders` and repaints
the grid; detail-shaped agents stay on Studio's copy (`kb_tool_names` never reaches the
store, tested). The connector-form agent dropdown uses `get('agents', {force: true})`.
Admin provider list now goes through `fetchJson`, so a non-2xx shows "Failed to load providers".

**Remaining duplicates (recorded, not fixed; Flight 3).** `/api/tools`, `/api/mcp-sources`,
`/api/knowledge-bases` and provider model caps are fetched twice per first Studio activation
(`init` + `activate`) and refetched on every re-activation; `/api/tools/configs` in Admin;
per-provider `/models` in several modules.

**Tests.** `tests/browser/test_store.py` (15: API, copies, failure, in-flight + invalidate,
subscribe, request counts, isolation, subscription repaint, save round trip, invalidation
spies for agent/provider/KB), `tests/test_store_static.py` (3 greps), and the AC5(a) test in
`test_flow_studio_loadall_error.py`. OAuth sign-in/out is covered by the static grep (no live
provider). AC5(b)/(c): detail fetches and `_knowledgeBasesLoaded` untouched.

### Leg 8: behavior-specs-and-close (landed, 2026-10-01)

**Specs touched.**
- `shell-navigation-smoke.md` rewritten (9 steps, still data-independent and read-only): rail with four links, Chats/Agents/Library/Settings destinations each accepting populated or empty state, theme flip and restore in Settings > General, cold deep links `#settings/providers` and the labelled legacy redirect `#admin/providers`. Validator notes folded in: step-6 "banner" became "welcome/config-needed message"; Connectors listed in the Library sections. Evidence note added (PDF + AX tree + computed style when screenshots fail). `Last Run` says it has not re-run on the rail.
- `workbench-navigation.md` new (16 steps, status active): API seed of mock provider, agent, KB; section navs; Back/Forward between two opened items; rail restore; legacy redirects; dirty editor via rail and via browser Back with Stay (edit kept, URL unchanged, focus by `document.activeElement` identity) and Continue (discards; re-open shows saved value; API confirms); teardown; Variants dark/light.
- Navigation wording and routes only: `system-provider-config`, `save-preserves-config`, `stub-connector-round-trip` (`#library/connectors`, Agents wording), `studio-agent-crud`, `agent-retention-setting-roundtrip`, `agent-purge-now-clears-history`, `anthropic-plan-signin`, `agent-governance-and-search` (Settings > Built-in Tools), `kb-studio-round-trip`, `anthropic-plan-chat-parity`, `chat-roundtrip`, `extended-thinking-tool-turn`, `windows-native-frame-splash` (`#app-topbar` -> `#app-rail`).
- Left alone: `studio-smoke` (archived; its one old-nav hit stays). No spec index file exists, so none was updated.
- AC3 grep returns only: the two labelled legacy-redirect steps and intent lines in the two new/updated specs (`#admin/`, `#studio/`, and the negative `app-topbar` absence check), plus archived `studio-smoke`.

**Label/route verification** (headless Chromium against a dev instance on 8485, scratch data dir, dev mode, seeded mock provider/agent/KB; instance stopped and scratch removed).

| Label / route | Observed |
|---|---|
| Rail "Main" nav: Chats, Agents, Library, Settings; `aria-current="page"`; testids `rail-<id>` | `#app-rail a` text and attribute |
| Rail hrefs (current -> root, others -> last route) | `#chats`, `#agents/<name>/general`, `#library/knowledge`, `#settings/providers` |
| Section nav "Library sections": Knowledge, MCP Servers, Connectors | nav `aria-label` + button text; hashes `#library/knowledge`, `#library/mcp`, `#library/connectors` |
| Section nav "Settings sections": General, LLM Providers, Built-in Tools, Knowledge (+ Design Language in dev) | hashes `#settings/general`, `/providers`, `/tools`, `/knowledge-indexing` |
| Agents: header "Agents", "New Agent", tile; sidebar hidden | `#agents`; section nav not visible |
| Agent editor tabs General, Knowledge, MCPs, Built-in Tools, Self-configuration; Description field | `[role=tab]`, `label` "Description" (`#studio-description`) |
| Dialog "Unsaved changes" / "You have unsaved changes. Continue without saving?" / Stay, Continue | `modal-cancel-btn` (focused on open), `modal-confirm-btn` |
| Stay via rail: focus returns to `rail-settings`; Stay via Back: focus returns to previously focused field | `document.activeElement` |
| Legacy: `#admin/providers` -> `#settings/providers`; `#studio/agents/x/tools` -> `#agents/x/tools`; `#studio/knowledge` -> `#library/knowledge` | `location.hash` after reload |
| Chats: "No conversations yet.", welcome copy "Add a provider in Settings", "Create an agent in Agents" | DOM / `welcome.js` |
| Theme control Light/Dark/Auto with `aria-pressed`; `data-theme` | DOM + computed body background |

Every spec step sequence (workbench steps 3-15) was also replayed in a Playwright script against the instance to confirm hashes and focus targets (this corrected step 13: focus returns to the previously focused field, so the step now focuses Description before pressing Back; and step 15's Back target). Behavior tests themselves were not run.

**Flight-close gates.**
- `make lint`: clean.
- `make test-unit`: 5001 passed, 10 skipped, 1159 deselected, 673s.
- Lanes, one at a time, `THE_ONE_TEST_NETNS=1`: chats 41 passed (96s); agents 97 passed, 2 skipped (219s); library 95 passed, 1 skipped (345s); settings 125 passed (231s); shared (`THE_ONE_REQUIRE_WEBKIT=1`, includes every `test_ui_*` in both engines) 719 passed, 1 skipped (604s). No failures, no reruns needed.
- WebKitGTK 2.52.6 probe, `--root-selector body`, dark: `#agents` (17 controls) and `#settings/general` (21): only failure is the known squawk 0110 (`chat-image-input` has no accessible name).

### Flight review fixes (2026-10-01)

Reviewer and Accessibility Reviewer feedback; no blockers, all fixed.

- **Route announcer and title (WCAG 4.1.3 / 2.4.2).** `router.js` creates an empty `#route-announcer` (`role=status`, polite, `.visually-hidden`) at start and writes `Destination[ - section][ - item]` into it on a commit that changes destination, section or item. Boot and `sync` never announce; focus is never moved. `document.title` = `... - GleepGlorp AI` on every commit and on sync. `route-announcer` added to the test-id registry; `test_shell_rail` body-children assertion now names the announcer. Tests: `tests/browser/test_router_announce.py`.
- **Nits.** Fixed the over-indented line and the long comment in `applyDecision`; refreshed stale comments (`studio.js` x2, `admin.js`, the knowledge-settings test docstring).
- **Dialog hardening.** `confirmDialog` now closes a dialog whose `showModal()` threw (onClose drops the count, caller settles as Stay) and rethrows. This exposed that `nav.confirmLeave` set `pending` after the dialog call; it now registers `pending` first and catches a throwing dialog (Stay, nothing left pending). Test: `test_show_modal_failure_does_not_leave_dialog_count_stuck`.
- **Chat stalled join.** The protocol has no error frame for `new_session`, so `chat.js` arms a 10s timer after sending (`App.chatStartJoinTimeoutMs` test override); on expiry it clears `pendingStart.sent` and requests `list_sessions`, whose drain re-sends. Timer cleared on join and socket close. Test: `tests/browser/test_flow_chat_start_recovery.py` (drops the first `new_session` frame).
- **agents.md** router contract gained the announcer/title paragraph.

**Verification.** Static guards (ui_guards, token definitions, a11y, cache-busting) 229 passed; `make lint` clean; `make test-unit` 5001 passed; lanes (netns, one at a time) chats 42, agents 97 (+2 skipped), settings 125 passed; shared (WebKit required) 722 passed, 1 failed (`test_shell_rail` body-children, caused by the announcer; test updated, rerun with the new router tests: 20 passed).

### Flight-close behavior tests (2026-10-01)

The Flight Director ran the behavior tests against `4828d53` on a dedicated dev instance (port 8485, scratch data dir `/tmp/the-one-wbnav-scratch`, dev mode on). Port 8484 and the default data dir were never used.

**Results: all pass.**

| Spec | Result | Run log |
|---|---|---|
| `workbench-navigation` | 28/28 (Dark 14 + Light 14) | `tests/behavior/workbench-navigation/runs/2026-10-01-21-03-48.md` |
| `shell-navigation-smoke` | 8/8 | `tests/behavior/shell-navigation-smoke/runs/2026-10-01-21-46-12.md` |
| `studio-agent-crud` | 18/18 (Light 9 + Dark 9) | `tests/behavior/studio-agent-crud/runs/2026-10-01-21-46-12.md` |
| `system-provider-config` | 18/18 (Light 9 + Dark 9) | `tests/behavior/system-provider-config/runs/2026-10-01-21-46-12.md` |

**Apparatus**

- **Goldfinch input outage.** After the `workbench-navigation` Dark variant, goldfinch stopped delivering synthetic input on this host. Clicks and key presses returned ok, but no events reached the page. The Flight Director reproduced this. Window tools are admin-only, so the cause could not be diagnosed. This needs operator attention.
- **Replacement apparatus.** Every later run used a headless Chromium 147 (Playwright `chromium-1217`) driven over CDP, with these properties:
  - persistent raw-CDP contexts;
  - real input events;
  - screenshots as primary evidence;
  - one Chromium per concurrent run.

  `system-provider-config` mandates chrome-devtools. No such MCP is registered, and this CDP-driven Chromium meets the spec's intent.
- **Concurrent runs.** The three later specs ran in parallel against one instance. Their Executors shared a scratchpad, and generic script names collided: two Executors each ran another run's script once. Each affected step was re-done with uniquely named scripts, disclosed to the Validators, and confirmed against server state. **Lesson:** give concurrent Executors per-run scratch subdirectories.

**Re-runs**

- `workbench-navigation` D13: an unrequested full-document probe left a cross-document history entry behind the editor, so `beforeunload` blocked the Back press. The step was re-run on same-document history.
- `shell-navigation-smoke` step 9: the first attempt was a same-document hash change. The step was re-run as a true fresh-document load of `#admin/providers`, which redirected during boot within about 100 ms.

**Spec fixes applied**

- `workbench-navigation`:
  - uses `aria-checked` instead of `aria-pressed`;
  - states where the theme switch happens;
  - adds evidence notes on `dialog[open]`, aria `current` and values, and rendered banners;
  - forbids history-altering probes;
  - clarifies the step 15 wording.
- `shell-navigation-smoke`:
  - uses `aria-checked`;
  - makes step 9 an explicit fresh-document load;
  - accepts a CDP/Playwright apparatus.
- `studio-agent-crud`: after a delete, step 9 now expects a return to the Agents grid.
- `system-provider-config`:
  - accepts a CDP apparatus;
  - steps 11 and 12 match the provider by name prefix, because step 7 renames it.

**Observations (no Flight 2 regression)**

- **Route announcer after provider create.** After a provider save-create, the editor canonicalises the URL through `App.router.sync()`, which re-titles but never announces. The visually-hidden route announcer therefore keeps reading "Settings — Providers — New". Agent save-create uses `go(replace)` and does announce. This is a small accessibility inconsistency and a candidate squawk for Flight 3's create flows.
- **Leave guard on cross-document Back.** With a dirty editor, a Back press that would leave the document is silently blocked by `beforeunload` in goldfinch (Electron). This is correct.
- **Pre-existing inputs for Flight 3**, which rebuilds the Library and Settings lists:
  - the Connectors empty-state "New Connector" button is unstyled (`connector-editor.js` lacks `btn-outlined-primary`);
  - a long provider name in a tile runs under the absolutely-positioned type badge;
  - section-nav items are `<button>`s, not links.
- **Asynchronous delete arm.** The provider Delete arm waits on an agent-usage pre-fetch, so it arms after about 57–130 ms. Probes must poll for "Confirm Delete?".
- **Not an app race.** The `workbench-navigation` D11 lost-first-keystroke hypothesis was falsified. MutationObserver probes found no editor re-render, even when typing 59 ms after mount. The lost input came from goldfinch's hidden-tab handling.

### PR (2026-10-01)

- **PR #218** (https://github.com/msieurthenardier/the-one/pull/218) is open and ready for review.
- I did not merge it. Merging is the operator's call.
- **PR #217 merged** (squash, `3121c2d`, 2026-10-01T22:19Z). GitHub retargeted #218 to
  `main`, where it conflicted, because the squash rewrote the Flight 1 history underneath
  it.
  - **Fix.** The Flight 2 commits were rebased onto `main` with
    `git rebase --onto origin/main flight/01-control-library-foundation`. The Flight 1
    tree and the squash tree were identical, so the rebased HEAD tree is byte-identical
    to before.
  - **Push.** The branch was force-pushed with `--force-with-lease`.

## Flight Director Notes

- 2026-10-01: Flight design review.
  - **Architect cycle 1** returned "approve with changes" with 21 issues (5 high). The
    spec was rewritten:
    - `go`/`sync` URL primitives;
    - the alias-layer studio.js changes;
    - teardown discard with per-area sources;
    - confirm-dialog test dispositions and native Enter semantics;
    - store copies, load state and invalidation map;
    - guard traversal mechanics and link-interception rules;
    - leg 3 split into `confirm-dialog-native` + `unified-leave-guard` (7 legs).
  - **Architect cycle 2** returned "approve with changes": 2 high and about 10
    medium/low items, all text additions with no redesign:
    - section-root routes render exactly the root (the Back item→list close);
    - `prevSection` captured before assignment in hydrate, plus a `doSelect` stale-then
      guard;
    - traversal details (revert popstate no-op, hashchange dedupe, live delta, boot seq);
    - `sync` dropped while a decision is pending;
    - the per-site `replaceSub` table;
    - `isDirty = dirty && editorOpen()`;
    - an interim leg-3 guard;
    - the scoped `~new` redirect;
    - a bubble-phase interceptor;
    - the rail current-href rule;
    - DD6 role and styling notes;
    - Chats history.
  - These were applied without a third cycle: the methodology caps flight review at two,
    and per-leg design reviews (high-risk legs) will re-verify against the code.
  - Flight set `ready`.

---
- 2026-10-01: Flight set `in-flight`. The flight has 7 legs.
  - Leg 1 `test-navigation-helper` designed. **Risk tier: high** (about 45 test files;
    shared test infrastructure). The Developer design review returned "approve with
    changes". Applied: the real hash shapes, the extra helpers, the AST guard with a
    per-function allow-list, canonicalisation and inverse, per-segment comparison, exact
    `encodeURIComponent` parity, and lane subtraction. Implementation spawned.
  - Leg 2 `confirm-dialog-native` designed in parallel. **Risk tier: high** (shared
    dialog with 12 call sites). Its design review is running.
- Leg 1 landed and reported `[LAND:leg]`.
  - The four flakes are root-caused (response-ordering races) and fixed via
    `_nav.goto_settled`; a fifth of the same class (KB inventory) was also fixed.
  - 43 files are migrated, and the lanes are re-mapped (union 797 tests).
  - **Anomaly to carry:** Studio and Admin load their data twice on first activation,
    and Studio paints the empty canvas before any fetch resolves. Legs 3–4 and the store
    (leg 7) should remove the double load. Leg 7's design must check it.
- **Leg 3 split** at its design review ("needs rework"):
  - Legs are now: `03-router-core` (router, explicit-area `sync` at every former
    `replaceSub` site, the interim guard on every `go()` and traversal with the in-area
    gates deleted, `closeOpenItem()`, the test flip) and `04-item-history-and-exact-rendering`
    (intent and bypass conversions with inline-gate deletion, item history, dead ids
    with the `fresh` hydrate origin, Chats, links, the MCP tab).
  - **The flight now has 8 legs:** 05 `unified-leave-guard`, 06 `rail-and-shell`, 07
    `client-data-store`, 08 `behavior-specs-and-close`.
  - Both new legs had a second review ("approve with changes"); changes applied.
  - Risk tiers: both **high**.
- Leg 2 `confirm-dialog-native` implementation spawned (design reviewed earlier; the
  single-open policy is retained until the guard leg, now leg 5).
- Leg 2 landed and reported `[LAND:leg]` (native confirm dialog; DD8 checks pass on the
  real wrapper in both engines and WebKitGTK).
  - Two more lane failures passed alone:
    - `test_mcp_test_connection_button.py::test_test_connection_button_present_for_stdio_source`
    - `test_flow_admin_tools_editor.py::test_editor_connector_tool_shows_connectors_category`

    They are the same load-sensitive class. The leg 3 Developer is asked to move them
    onto `_nav.goto_settled` if they touch those files. Otherwise they are recorded for
    the debrief.
- Leg 3 `router-core` implementation spawned.
- Leg 3 `router-core` landed and reported `[LAND:leg]`. The engine proof passed
  (`popstate` fires ahead of `hashchange` in Chromium 145 and WebKit 26.0 for every
  case). All lanes are green.
  - **Deviation accepted:** a single `sync('admin', serializeState())` heal of an
    unknown provider id at admin.js:371. AC11's tightened unknown-id test needs it; full
    dead-id handling stays in leg 4.
  - **Squawk 0110** is logged for the pre-existing `chat-image-input`, which has no
    accessible name; the probe found it.
  - **Lane-noise note:** `net::ERR_NETWORK_CHANGED` on `/static/js/*` from the WSL host's
    network flapping caused a few deep-link failures that were clean on rerun. Recorded
    for the debrief.
- Leg 4 `item-history-and-exact-rendering` implementation spawned. It was designed and
  reviewed with leg 3 (cycle 2). The Developer re-verifies its citations against the
  leg 3 output.
- Leg 4 landed with two open items. The Flight Director sent a follow-up Developer
  before building on it:
  - **(1)** The "third session" was a **pre-existing app bug**: a `session_list`
    arriving between `new_session` and `session_joined` re-sent `new_session`. It is
    fixed in `chat.js` with a `pendingStart.sent` flag, and a deterministic test pins it.
    AC6 is confirmed by counting WebSocket frames.
  - **(2)** `test_router_items.py` was hardened: wait-for-state helpers and quiet
    windows. It passed 5/5 full-file runs under load average ~20.
  - The flight-end Reviewer reviews this with the rest.
- Leg 5 `unified-leave-guard` design-reviewed ("approve with changes"); the artifact is
  rewritten with the real router and area names. Key changes:
  - the router adapter keeps the sync fast path, with no second join layer;
  - the remaining inline gates are connector **Back** and agent `enterCreateMode`;
  - `App.confirmDialog` gets an `opener` option and an open-count;
  - discard bumps a generation to block in-flight-save resurrection;
  - the `beforeunload` recipe was verified in Chromium headless.

  **Risk tier: high.** Implementation spawned.
- Leg 5 landed (`App.nav`, the unified guard). The library lane then failed
  repeatedly, and two follow-ups ran:
  - **(1)** No app regression: a delay-hook test proves the MCP editor mounts after a
    slow list fetch. The library deep links moved to `goto_settled`.
  - **(2) Root cause: the environment.** Under WSL2 mirrored networking, Windows'
    rotating temporary IPv6 addresses trigger Chromium's NetworkChangeNotifier, which
    aborts loopback requests with `net::ERR_NETWORK_CHANGED`. The fix is a new opt-in,
    `THE_ONE_TEST_NETNS=1` in `scripts/run-tests.sh`: pytest runs in a user+net
    namespace that contains only loopback, and the option fails loudly if unavailable.
    With it, the library lane passed 3/3 and all other lanes passed once with zero
    failures.
  - **Standing instruction:** all browser verification on this host uses
    `THE_ONE_TEST_NETNS=1` from now on.
- Leg 6 `rail-and-shell` implementation spawned. It was design-reviewed earlier
  ("approve with changes", applied). **Risk tier: high.**
- Leg 6 landed: the rail replaces the top bar, plus `onCommit`, the flex shell, the
  `.visually-hidden` lift and copy updates. All five lanes are green with
  `THE_ONE_TEST_NETNS=1` and no reruns. The §2 measurements and 7 recorded deviations
  are in its entry.
  - Leg 7 `client-data-store` implementation spawned. It was design-reviewed earlier;
    **risk tier: high**.
- Leg 7 landed: `App.store` for agents and providers. The request counts went down
  (Agents cold boot 2+2 → 1+1). The leg 1 double load was a fetch-site duplicate, now
  fixed for these two collections. All lanes are green.
- Leg 8 `behavior-specs-and-close` set `ready`. **Risk tier: low** (spec text and
  gates), so the leg design review is skipped. Implementation spawned. After it lands,
  the Flight Director runs these behavior tests:
  - `workbench-navigation` (dark and light);
  - `shell-navigation-smoke`;
  - `studio-agent-crud`;
  - `system-provider-config`.
- **Flight review:** the Reviewer returned `[HANDOFF:confirmed]` with nits; the
  Accessibility Reviewer found no blockers, plus a route-change announcement gap.
  - The fix round added the `#route-announcer` live region and `document.title`, the
    nits, dialog hardening and chat stalled-join recovery.
  - The re-review returned `[HANDOFF:confirmed]`, and the full shared lane is green
    (723).
  - **Accepted trade-off:** a server join slower than 10s can leave one orphan empty
    session after the recovery re-send. Re-arming the timer after the drain re-send is
    optional hardening, deferred.
  - Reviewer tier: **Sonnet**. The diff is large, and the link interceptor routes
    agent-authored markdown links, which is a security-adjacent surface.
- **Behavior tests** (the Flight Director runs them):
  - `workbench-navigation` (dark, then light);
  - `shell-navigation-smoke`;
  - `studio-agent-crud`;
  - `system-provider-config`.

## Decisions

### `App.confirmDialog` single-open policy retained until leg 5
**Context**: DD6 removes the confirm singleton. The leg 2 design review showed that the
11 guard sites can double-dispatch, e.g. a second `hashchange` from Back/Forward. Two
stacked leave dialogs would each run their own `proceed`/`abort`.
**Decision**: `App.ui.modal` stacks from leg 2. The `App.confirmDialog` adapter keeps
today's single-open policy until leg 5, where `App.nav`'s single-flight guard owns
de-duplication. At that point the adapter's singleton is removed and its pinned test is
inverted.
**Impact**: DD6 is narrowed for legs 2–4, with no behaviour change at the guard sites
before leg 5.

---

## Deviations

---

## Anomalies

- 2026-10-01 (leg 1): not fixed, no app code changed. Studio and Admin run their inventory/data
  load twice on first activation (`init()` and `activate()` -> `_refresh()`), each pass rebuilds the
  rendered list, and Studio paints the "No agents yet" canvas before any fetch resolves. This is
  the root cause of the `test_agent_item_keyboard_select` and `test_studio_agent_crud_flow`
  flakes. The tests now wait on the app's fetch activity. The router rewrite (legs 3-6) touches
  the activation path and may remove the double load; worth confirming then.

---

## Session Notes

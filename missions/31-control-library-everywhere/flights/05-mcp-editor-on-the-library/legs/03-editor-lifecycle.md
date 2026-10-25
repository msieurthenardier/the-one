# Leg: editor-lifecycle

**Status**: planning
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Give the MCP editor a real lifecycle, so no response, timer or listener from one mount can touch another:
- `renderMcpSourceEditor` returns a controller `{destroy, setBusy, setError, runTest}`;
- the glue destroys it before every remount and on every close;
- every async write is keyed on the mount;
- at most one consent poll runs, and it stops on `destroy`;
- the per-mount `handles` object exists for the surface legs.

Defects 1, 2, 6 (the dirty flag and focus) and 8 are fixed, each test first. There is no visible change except where a defect was visible.

## Context
- **Flight decisions:** DD4 (one controller with a teardown; async writes keyed on identity; the per-mount `handles`; `runTest`), DD9 (defects 1, 2, 6, 8), DD10, DD12 (fixed waits: hold the request, release, then assert; never `wait_for_timeout` to prove nothing happened).
- **The modules after leg 02** (`js/areas/studio/`):
  - `mcp-server-editor.js` (the controller, 775 lines): `renderMcpSourceEditor` (`:62`), `getFormSnapshot` (`:257`), `wireEditorEvents` (`:306`), with `reportDirty`/`checkDirty`/`recaptureSnapshot` (`:315-332`), `titleEl` (`:400`), Cancel (`:402`), Save (`:423-500`), `onTestConnectSuccess` (`:510-529`), the Test click (`:531`) and Delete (`:560-580`); `revertEditorToSource` (`:592`); `collectFormData` (`:687`).
  - `mcp-connection-status.js`: `renderConnectionActions` (`:25`); a call-time wrapper for `App.studio.renderMcpSourceEditor` (`:65`); `wireResetButton` (`:76-117`, which re-mounts the editor after a Reset); `syncResetButtonVisibility` (`:119`); `handleTestConnection` (`:160-335`), with `settle` (`:183`), `rerun` (`:192`) and the consent wrapper (`:195`).
  - `mcp-oauth-consent.js`: `launchConsentPopup(args)` (`:36`), with `cleanup()` (`:128`, which clears the poll and removes the listener), `finalize` (`:133`), `renderRetryUi` (`:140`), `onOAuthMessage` (`:162`), the listener (`:186`), the delayed first check (`:190`) and the 500 ms poll (`:194-226`).
- **The glue** (`mcp-glue.js`):
  - `renderMcpSourcesSection` mounts through `App.studio.renderMcpSourceEditor(sectionContentEl, …)` (`:69`), guarded only by `editorGen` on the type wait (`:65`) and in `onSaveSuccess` (`:84`);
  - on create it calls `renderMcpSourcesSection()` again, then auto-clicks the Refresh button through `setTimeout` and `dataset.autoRun` (`:104-138`);
  - `_closeMcpForm` (`:184-188`) and `reset()` (`:235-238`) clear state without touching the editor;
  - `studio.js` `closeOpenItem` calls `mcpGlue.reset()` (`:389`), and `discardOpen_` (`:405-413`) blanks `sectionContentEl`;
  - opening another MCP item re-renders the section without any discard (a hydrate through `_closeMcpForm`, then `tryConsumePendingMcpSource` → `renderMcpSourcesSection`).
- **The defects** (code survey §5):
  - **1:** the Save `.then` re-resolves nodes through `container` (`titleEl()`, the buttons, the caption) and calls `onDirtyChange(false)`. `onTestConnectSuccess` repaints the LED, "Last updated" and the server info, and runs `syncResetButtonVisibility(container, source_A)`, which can inject a Reset wired to A into B's editor. The container is the same `sectionContentEl` for every item.
  - **2:** nothing calls `cleanup()` unless the poll finishes; the poll runs for up to 120 s after the editor is gone.
  - **6 (this leg's part):** the Reset re-mount never reports `onDirtyChange(false)`, so `state.dirty` keeps a stale `true`, and the confirm button that had focus is destroyed (focus falls to `body`). Leg 08b replaces the re-mount with a patch.
  - **8:** the auto-run path's `settle()` re-enables Refresh while a "Sign in" flow may be polling, and a second click starts a second poller.

## Inputs
- Legs 01 and 02 landed and committed at the batch B1 checkpoint.

## Outputs
- **A new module, `js/areas/studio/mcp-editor-lifecycle.js`** (`App.studio.mcpEditor.lifecycle`). It holds the mount context, so the controller stays at 800 lines or fewer (it is 775 now). It carries its own script tag in `index.html` before the controller, the `test_index_asset_cache_busting.py` and script-order checks, and any move-table entries if a use moves into it. It provides:
  - **`createMount(callbacks)`**, which returns the mount context `{alive(), ifAlive(fn), destroy(), setSession(s), session(), handles}`;
  - **`ifAlive(fn)`**, the one dead-mount rule every continuation goes through;
  - **`destroy()`**: it is idempotent. It sets the dead flag and cancels the current consent session. It does **not** call `App.focusAfter.cancel()`, which is global and would wipe the create → edit restore that the glue's `flush()` lands. Restore targets are alive-gated instead: the mount's `titleEl` returns `null` once the mount is dead, so `focusAfter` rejects it. Leaving the editor is already covered by `closeOpenItem`'s `App.focusAfter.cancel()`.
- **`mcp-server-editor.js`:**
  - **`renderMcpSourceEditor` returns `{destroy, setBusy, setError, runTest}`.**
    - `setBusy(bool)` and `setError(msg|null)` act on today's hand-built header (Save, Cancel and the `.editor-error` span). Leg 10 moves them onto `editorShell`.
    - `runTest({autoRun})` runs the same path as a Test click. It is a defined no-op while a consent session is active or the Test button is disabled.
  - **Every mount calls `callbacks.onMounted(controller)`**, including Reset's re-mount, so the glue always holds the live controller.
  - **What a dead mount skips, and what it still does** (design review M4):
    - **It skips** the DOM writes and mount-bound callbacks: flashes, title, snapshot, caption and button writes, `reportDirty` and `onDirtyChange`, `onSaveSuccess`, `onDeleteSuccess`, LED, "Last updated", server info and Reset injection.
    - **It still does** whatever reflects a server change that already happened: `App.store.invalidate(...)` and `callbacks.onListStale()`. A late Delete therefore calls `onListStale` instead of `onDeleteSuccess`, so the list drops the row without closing the open item. The request itself is never aborted.
  - **On mount, report the initial clean state:** `onDirtyChange(false)` once.
  - **The per-mount `handles` object** (from the mount context) is passed to `collectFormData`, `getFormSnapshot` and `revertEditorToSource`, which keep their `container` reads for now (DD4).
- **`mcp-connection-status.js`:**
  - `handleTestConnection` receives the mount context and threads it through `rerun()` (which today calls `handleTestConnection` with `{noAutoPopup: true}` and would drop it);
  - **one consent session per mount, and the rule is refuse** (DD4): Test is disabled when a session starts and re-enabled when the session settles or is cancelled. On the auto-run path, `settle()` no longer re-enables Test while the "Sign in" flow is active (defect 8). A second launch, including the retry button's, replaces the mount's session slot; it never runs beside it;
  - **Reset's order:** alive check, then `App.focusAfter.begin(resetBtn)`, then destroy the old controller, then mount the new one (which reports through `onMounted`), then restore focus to the new mount's Test or Refresh button (the title is the fallback), then the flash. If the mount died during the refetch, nothing is mounted.
- **`mcp-oauth-consent.js`:**
  - `launchConsentPopup(args)` registers its session in the mount's slot (`args.mount.setSession`) and returns `{cancel}`;
  - `cancel()` is idempotent. It clears the poll and the `message` listener, stops the delayed first status write (the `setTimeout` at `:190`), and puts the session in a done state, so it never calls `rerun`, `settle` or a `finalize` writer;
  - **`cancel()` does not close the popup** (an FD decision on the review's question). Leaving the editor must not kill a sign-in the operator is finishing in the browser. The server stores the tokens, and a reopened editor shows the result.
- **`mcp-glue.js`:**
  - keeps `current`, set only from `onMounted` and only when the mount's generation still matches;
  - calls `current.destroy()` (when set) in each of these places:
    - at the top of `renderMcpSourcesSection`;
    - immediately before `App.studio.renderMcpSourceEditor` inside `ready.then`, after the `editorGen` check, so two queued renders never leave an orphan (the connector precedent, `connector-glue.js:70-79, :113`);
    - in `_closeMcpForm`;
    - in `reset()`;
  - exposes a destroy-only `self._resetMcp`, which `studio.js` `deactivate()` (`:739-750`) calls beside `_resetKnowledge`. Leaving the Library area with a clean editor (to Chats or Settings) destroys the editor. It leaves `mcpSourceFormMode` alone, so a return is a fresh mount as today;
  - runs the auto-run after create through `current.runTest({autoRun: true})` instead of `dataset.autoRun` and a synthetic click. The deferred call checks that `current` is still the controller for `updated.id`, in the same generation, before it runs. The streamable-HTTP-only rule stays.
- **Tests** in `tests/browser/test_flow_studio_mcp_editor.py` (lane `mcp`), each failing on the leg 02 tree first and named for the behaviour:
  - **A late Save never writes into the next editor (defect 1).**
    1. Open A (edit) and make it dirty.
    2. Press Save with the PUT held (`page.route`).
    3. Open B. The leave guard asks, because A is still dirty; choose to leave.
    4. Release the PUT and wait for its response (`expect_response`), then yield one page macrotask (`page.evaluate` of a resolved `setTimeout(0)` promise; never `wait_for_timeout`).
    5. Assert: B's title is B's name, not A's; B's Save and Cancel state and its "Unsaved changes" caption match B's own state; no flash appeared in B; `App.nav`'s dirty state is B's; A's new name reached the server (a GET) and shows in A's Library row.
  - **A late Delete never closes the next editor (defect 1, Delete).** Hold A's DELETE, open B, and release it. B stays open, and A's row is gone from the list.
  - **A late Test never paints the next editor (defect 1, Test).**
    1. Stub A's per-id GET to carry `oauth_active: true`, so the old Reset injection would show.
    2. Open A (the connected HTTP fixture) and press Test with `/test/connect` held.
    3. Open B and release.
    4. B's LED, "Last updated", Server section and Reset presence are unchanged, and no Reset in B carries A's name.
  - **Leaving the editor stops the sign-in poll (defect 2).**
    1. `page.clock.install()` before `_nav.goto_settled`. The precedents are `tests/browser/test_flow_studio_knowledge_inventory.py:2084` and `test_ui_copy_contract.py`. The time-zone tests avoid `install()` because of `wait_settled`; install it before the first `goto_settled`, as those two do.
    2. Count requests with a page-side `window.fetch` counter keyed by exact path (`/api/mcp-sources/{A}`, `/api/mcp-sources/{A}/test/connect`), read through `page.evaluate`.
    3. Start a consent session on A (`/test/connect` stubbed to `auth_required`, `window.open` stubbed), and `run_for` until at least one poll GET is counted (the positive control).
    4. Leave. There are three cases: open another item; go to Settings with a clean editor (this exercises `deactivate`); and close through the breadcrumb.
    5. `run_for(125_000)`: no further GET of A's path and no re-POST.
  - **Reset leaves the editor clean and focused (defect 6, this leg's part).**
    1. Seed an OAuth-active source (as `test_reset_button_visible_for_streamable_http_with_oauth` does) and make the form dirty.
    2. Arm Reset and confirm it with a real second click.
    3. Navigating away raises no leave prompt; focus is on the Test or Refresh button (or the title), not `body`; and the glue's controller is the new mount: leaving afterwards stops any poll the new mount started.
  - **One sign-in poll at a time (defect 8).**
    1. On the create path, the per-id GET route is a regex matching any id, because the id is unknown until create.
    2. The `auth_required` auto-run shows "Sign in"; click it, and a session is polling.
    3. Test is disabled, and `runTest` is a no-op.
    4. The page-side counter shows one poll GET per 500 ms of `run_for`, not two.
  - **`destroy` is idempotent.** In a `page.evaluate`, call `App.studio.renderMcpSourceEditor(detachedDiv, source, types, {})` directly, call `destroy()` twice, and check that no error is thrown and no `pageerror` fires.
  - **The auto-run fires once** after a streamable-HTTP create and never after a stdio create; `test_create_streamable_http_auto_run_auth_required_does_not_open_popup` stays green unchanged.
  - **"No stray write"** means, in each test: no `/api/mcp-sources/{id}` GET, no PUT, POST or DELETE after the leave or the release beyond the asserted ones, and no `pageerror`.
- **The flight log:** the leg's entry; the remount side-effect inventory rows this leg touches (DD4); the refuse rule for defect 8; the decision not to close the popup.

## Acceptance Criteria
- [ ] The defect tests above fail on the leg 02 tree and pass after the change. The flight log records the failing run's names and the reasons they failed.
- [ ] **The controller API:** `App.studio.renderMcpSourceEditor` returns `{destroy, setBusy, setError, runTest}`; every mount reports through `onMounted`; `destroy` is idempotent (tested).
- [ ] **Destroy on every replacement path:** the glue destroys at the top of `renderMcpSourcesSection`, before the mount inside `ready.then`, in `_closeMcpForm`, in `reset()` and in `_resetMcp`, and `studio.js` `deactivate()` calls `_resetMcp`. The grep in Verification shows each, and the defect 2 test's three leave cases pass.
- [ ] **Focus:** the create → edit focus on the new title still works (the existing focus-after tests in `test_flow_studio_library_focus.py` and `test_flow_studio_mcp_editor.py` pass), and `destroy` never calls `App.focusAfter.cancel()`.
- [ ] **No synthetic auto-run click:** `git grep -n "dataset.autoRun" the_one/interfaces/web/static/js` finds nothing, and the auto-run behaviour is unchanged (existing tests).
- [ ] **No other behaviour change:**
  - the `mcp` and `library` lanes pass;
  - `test_studio_mcps_tab.py`, `test_oauth_modal_flow.py` and `test_flow_chiplist_label_resolver.py` pass;
  - the leg 01 capture surfaces match the leg 02 split set pixel for pixel (`~/.cache/the-one-ui-capture/m31-f5-split`). Any exception is explained in the flight log; none is expected.
- [ ] **Guards:**
  - no new sink and no new ownership use; the move tables and exact totals pass;
  - every `mcp-*.js` file is 800 lines or fewer, including the new lifecycle module;
  - the static JS/CSS guards and `test_index_asset_cache_busting.py` pass;
  - `make test-unit` passes.

## Verification Steps
- `git grep -n "destroy()\|_resetMcp\|onMounted" the_one/interfaces/web/static/js/areas/studio.js the_one/interfaces/web/static/js/areas/studio/`.
- `wc -l the_one/interfaces/web/static/js/areas/studio/mcp-*.js`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_studio_mcp_editor.py -x --timeout 60`, first with only the new tests added (expect the defect tests to fail), then after the fix.
- `--lane mcp` and `--lane library`, then by file with `-m browser`: `test_studio_mcps_tab.py`, `test_oauth_modal_flow.py`, `test_flow_chiplist_label_resolver.py`. Run at most 3 at a time.
- The capture compare against `m31-f5-split`.
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_area_module_size.py tests/test_store_static.py tests/test_consent_link_static.py tests/test_index_asset_cache_busting.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -q -x --timeout 120`, then `make test-unit`.

## Implementation Guidance
1. **Write the defect tests first** on the leg 02 tree, and confirm each fails for the stated reason.
2. **The lifecycle module:** the mount context, `ifAlive`, `destroy`, and the session slot. Then the consent session's `cancel` and its registration.
3. **The controller:** the returned object, `onMounted`, the initial `onDirtyChange(false)`, and the dead-mount rule on every continuation (skip the DOM writes, keep the invalidations and `onListStale`, turn a late Delete into `onListStale`).
4. **Connection status:** thread the mount context through `handleTestConnection` and `rerun`; the refuse rule; Reset's order.
5. **The glue and `studio.js`:** `current` from `onMounted`, the four destroy sites, `_resetMcp` in `deactivate`, and the guarded `runTest` auto-run.
6. **Run the suite and the captures.** Then write the side-effect inventory rows and the flight log.

## Edge Cases
- **A Save that lands after `destroy`** has still saved on the server: the list follows (invalidate plus `onListStale`), and the glue's `onSaveSuccess` `editorGen` check stays.
- **Create → edit:** the old controller is destroyed by the new render. Its parked `focusAfter.defer` must survive (no global cancel), and the restore resolves against the new mount's title.
- **The "Sign in" button** (auto-run path) starts a session from a click, so `window.open` stays synchronous inside the click handler (popup rules).
- **A `null` from `window.open`** is still not a failure (the desktop webview).
- **Opening the same item twice** re-mounts and discards edits. That is existing behaviour, out of scope, and noted.
- **The relative time** ("Last updated") is leg 08b's.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-editor-lifecycle.js` (new), `mcp-server-editor.js`, `mcp-connection-status.js`, `mcp-oauth-consent.js`, `mcp-glue.js`; `areas/studio.js` (`deactivate`); `static/index.html`.
- `tests/browser/test_flow_studio_mcp_editor.py`; the guard tables if a use moves.
- The flight log; `the_one/agents.md` gets one sentence on the editor's controller and teardown contract (the full contract is written in leg 12).

## Citation Audit
- Line numbers in `mcp-server-editor.js`, `mcp-connection-status.js` and `mcp-oauth-consent.js`: FD grep on the leg 02 tree (2026-10-25).
- `mcp-glue.js:65, :69, :84, :104-138, :184-188, :235-238`; `studio.js:389, :405-413`. FD read.
- `page.clock.install()` precedent: `tests/browser/test_flow_studio_knowledge_inventory.py:2084` and `tests/browser/test_ui_copy_contract.py` (the time-zone tests deliberately avoid `install()`). `studio.js` `deactivate` `:739-750`, `_resetKnowledge` `:320`. `connector-glue.js:70-79, :113`. FD read, plus the design review.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): needs rework.** Rewritten:
  - leaving the area reaches the editor through `deactivate` → `_resetMcp` (H1);
  - `destroy` never cancels `focusAfter` globally, and restore targets are alive-gated instead (H2);
  - every mount reports through `onMounted`, including Reset's re-mount (H3);
  - a dead mount still invalidates and calls `onListStale`, and a late Delete never closes the next item, with a new test (M4);
  - the glue destroys before the mount inside `ready.then`, and the auto-run is guarded (M5);
  - the `page.clock` precedent corrected, with a positive control and a page-side counter (M6);
  - the new lifecycle module for the 800-line limit (M7);
  - defect 8 is refuse, with one session slot and the mount context threaded through `rerun` (M8);
  - the idempotence test seam, the leave dialog, and the Reset-test setup (L).
  - FD decision on the review's question: `cancel()` stops polling but does not close the popup. A second cycle follows.

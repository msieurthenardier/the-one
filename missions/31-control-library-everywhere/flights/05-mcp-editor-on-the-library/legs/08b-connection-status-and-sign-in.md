# Leg: connection-status-and-sign-in

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Rebuild the MCP editor's connection controls on the library:
- **Test** in the header (B2), with a status line at the end of the Connection section that reads `App.usage.mcpState` (A6, A8, A9);
- **Reset connection** only for a signed-in server, and **Forget tools list** for a cached HTTP server with no sign-in (A7), both patching in place (defect 6);
- the consent block on `App.ui.consentLink`, with A19's wording;
- the shared MCP error headline for stdio (A18).

It also closes defect 9 and the connection-status parts of defects 10, 11 and 13, plus squawks 0216 and 0214.

## Context
- **Flight decisions:**
  - DD4 (the Test hold during a consent session; focus; the side-effect inventory);
  - DD6 (the state precedence; the refetch after every outcome; Reset and Forget, with their predicates; stdio gets neither);
  - DD7 (A6-A9, A18, A19, B2; ledger rows 6-9, 18, 19, 23, 30, 31);
  - DD9 (defects 6, 9, 10, 11, 13);
  - DD10; DD12 (fixed waits: hold the request with `page.route`).
- **After legs 03-08a** (`js/areas/studio/`):
  - **`mcp-connection-status.js`:**
    - `renderConnectionActions(source)` builds the Refresh / Reset / LED / "Last updated" row as a string, with `App.icon`, `btn-outlined-primary`, `indicator-led`, the `formatTimeAgo` text and Reset's tooltip-as-name;
    - `wireResetButton` uses `App.confirmDelete` and re-mounts the editor after a Reset;
    - `syncResetButtonVisibility` injects Reset with `hasOAuthState`;
    - `handleTestConnection` writes "Testing connection…", the tool count (`statusEl.innerHTML`), the LED, "Last updated: just now", the "Sign in" button on the auto-run path, and `App.buildMcpError` into `[data-testid=mcp-test-status]`, which sits in the **Tools** section (A8);
    - the mount gate and `settle()` are from leg 03; the every-outcome invalidation is from leg 08a.
  - **`mcp-oauth-consent.js`:** the consent block through `App.consentLink.*` (3 alias calls), "Finalizing sign-in…" when the popup closes (about `:222`), the session handle (leg 03).
  - **`App.usage.mcpState(source)`** (leg 08a): `{state, tools, checkedAt}`, with `checkedAt` in seconds.
  - **The controller's header** is still hand-built until leg 10, so `editorShell.setTestState` (leg 05) is not usable yet. This leg's Test is an `App.ui.button` placed in the hand-built header's `.form-actions` after the mount, and driven directly. Leg 10 moves it to `actions.test` (DD4).
- **The shared pieces:**
  - **`js/mcp-error.js`** `mcpErrorMessage`/`buildMcpError` is used by the editor and by the agent MCPs tab (`mcps-tab.js`). The `MCPConnectionError` headline names "address and key" and "Refresh" (A18). `.mcp-tools-error` has no font size in `studio.css` (about `:126`), so it is 13 px in the editor and 16 px in the tab.
  - **`js/ui/consent-link.js:65`** reads "Finish signing in in the browser window. This page updates when you're done." (A19). Chat shows the same block, so the fix reaches chat too. It is a typo fix, recorded as A19's reach.
  - **Squawk 0214:** the OAuth callback page (`api.py`, about `:4661-4663`) links `/static/js/theme.js`, `/static/css/fonts.css` and `/static/css/tokens.css`, which 401 without a session (`middleware.py:212` exempts only the callback path), so the page renders unstyled in the system browser.
  - **Squawk 0216:** `tests/browser/test_mcp_test_connection_button.py:191, :196` race the transient "Testing connection…" text against a fast failure.

## Inputs
- Batch B3's legs 06, 07 and 08a landed (leg 08a's `mcpState`, `last_check` and body rule).

## Outputs
- **The Test button (B2).** In edit mode only, an `App.ui.button({label: 'Test', icon: 'play', variant: 'secondary', testid: 'mcp-test-connection'})` sits in the header's `.form-actions` before Cancel, the provider editor's place.
  - The create form has no Test, and the `if (testBtn)` wiring stays guarded.
  - The Connection section loses its Refresh button. The auto-run after create uses `runTest` (unchanged).
  - **The wiring goes into `mcp-connection-status.js`** (357 lines), so `mcp-server-editor.js` (798 lines at HEAD, guard 800) changes by a net reduction.
- **The status row**, at the end of the Connection section, under the fields:
  - **The status line:** an `App.ui.status({testid: 'mcp-connection-status', ledTestid: 'mcp-connection-led', ledLabel})` reading `mcpState`, with the state words from `App.usage.mcpStateLabel` (leg 08a), never literals (leg 11 pins this):
    - `connected`: "Connected · checked {time}";
    - `none`: "Not connected";
    - `error`: "Couldn't connect", plus " · last connected {time}" when tools were cached before;
    - `signin`: "Sign-in needed".

    `{time}` is `App.time.formatClock` (with `App.time.formatDate` when not today, via `App.time.dayNumber(now) !== dayNumber(then)`) of `checkedAt * 1000` (defect 13; DD14 wording).
    - **The state map:** `connected` → `success`, `none` → `idle`, `error` → `danger`, `signin` → `warning`; the root carries `data-state`.
    - **The LED is decorative:** `App.ui.status` marks it `aria-hidden` when there is text. The line's text carries the state word (defect 11), and tests assert that, not an LED name.
    - **A dirty-form Test** records nothing (leg 08a), so the line stays on the saved record, and the result area adds "Tested with your unsaved changes." under the outcome.
    - **A clean Test** sets the line optimistically from the outcome, and the refetch then confirms it; a failed refetch leaves the optimistic state.
  - **The result area** (keep `data-testid="mcp-test-status"`), moved from the Tools section to right under the status line (A8):
    - it is **empty and `hidden` at rest and after a success** (the status line says Connected);
    - it shows "Testing connection…", the error block (`App.buildMcpError`), and the consent block or "Sign in" button;
    - **it has no role of its own.** The transient text sits in an inner `role=status` span, as the consent texts already do, and the error block keeps its own `role=alert`, so nothing announces twice.
  - **The tool count line** ("Server exposes N tools.") goes. The status line says "Connected", and the Tools section lists the tools. A ledger note under row 8.
  - **Reset and Forget**, beside the status line in a status-row wrapper with its own area class, through DD6's predicates:
    - **"Reset connection"** (`reset-mcp-connection-btn`) only when `oauth_active === true`, its armed label "Reset connection?". `hasOAuthState` in `mcp-editor-shared.js` is simplified to exactly that and loses its `_cache` fallback (DD6), with a test that a cached non-OAuth HTTP server shows Forget and not Reset;
    - **"Forget tools list"** (`forget-mcp-connection-btn`) for `streamable-http && !oauth_active && (_cache.auth_posture || _cache.tools)`, its armed label "Forget tools list?" (the short form; `flight.md` DD6's longer sentence is not used);
    - **both are built** as `App.ui.button` with no label plus an appended `span[data-confirm-title]` (the `provider-editor.js` pattern), confirmed through `App.ui.confirm` with an `announceName`, and call `DELETE .../connection`;
    - **a refetch never rebuilds a button**, armed or not: it toggles `hidden`, or inserts a button once (squawk 0088's invariant);
    - **both are disabled while a consent session runs** (`mount.sessionActive()`), because `oauth_active` flips true when the DCR credentials land, before the token, so Reset could otherwise appear mid-session. Tested;
    - **after a Forget, `last_check` is gone** too (the route drops the whole `_cache`), so the state reads "Not connected". That is accepted;
    - stdio shows neither;
    - names are plain ("Reset connection"), with no tooltip-as-name;
    - **both patch in place** (defect 6):
      - after the DELETE, the identity-guarded refetch updates the status row, the Server section (`syncServerInfoSection` until leg 09), the buttons and the Tools list, which returns to its empty state (`replaceChildren`, with the empty hint reworded to "Press Test to load this server's tools.");
      - unsaved edits are kept; no re-mount; the `onMounted` and `mount.destroy` path in `wireResetButton` is deleted;
      - **focus:** `App.focusAfter.begin(btn)`, then `restore(tok, testBtn)` with the editor title as the fallback when Test is disabled. On failure, the confirm's revert restores the label and focus stays on the button;
    - success is an `App.ui.flash` ("Connection reset" / "Tools list forgotten"); an error goes to the editor error (`setError`), not a toast, and is cleared by the next successful Reset, Forget or Test.
- **After every Test outcome** (DD6), the identity-guarded refetch:
  - copies `_cache`, `oauth_active` and `has_access_token` into the controller's **current** `source`, read through an accessor (`getSource()`) and guarded on `source.id`, `latest()` and `mount.alive()`, so a Save that replaced `source` meanwhile is not overwritten with a stale reference;
  - reverses the comment at `mcp-server-editor.js` about `:546` ("`source.config._cache` deliberately NOT overwritten");
  - then re-renders the status row and the button visibility;
  - runs after ok, error and auth_required, after the consent poll finishes, and after Reset or Forget.
- **The Tools list is not cleared when a Test starts** (today `listEl.hidden = true; listEl.innerHTML = ''` at the start wipes it, which contradicts A9). Only a successful Test replaces it, and a Reset or Forget empties it. The list's rendering itself is leg 09's.
- **During a consent session** (DD4): Test stays disabled and reads "Waiting for sign-in…" (the visible label and the name). Save and Cancel stay live. It restores on finalize, cancel or destroy.
  - **The mechanism:** `mcp-editor-lifecycle.js` `setSession` and `endSession` gain the label swap beside the disable. `App.ui.button` has no label setter, so the hook replaces the button's text node only and keeps the icon.
  - **`mount.handles.testBtn`** is the header button, assigned after the mount. Today it is queried from the container (about `mcp-server-editor.js:261`).
  - **One text:** "Waiting for sign-in…" is used for the Test label, the first consent status text (today "Awaiting sign-in…", the `textTimer` in `mcp-oauth-consent.js`) and the popup-closed text (today "Finalizing sign-in…").
- **Test while a Save is in flight is blocked** (`setBusy` covers Test, DD4).
- **`mcp-oauth-consent.js`:** `App.ui.consentLink.build`, `focusTarget` and `isSafeUrl` (no alias). "Waiting for sign-in…" replaces "Finalizing sign-in…" when the popup closes (A19). The popup rules are unchanged:
  - `window.open` synchronous in the click;
  - no auto-popup on the auto-run path;
  - a `null` return is not a failure;
  - the same-origin `message` check;
  - the 120 s ceiling;
  - `isSafeUrl` (`test_consent_link_static.py` keeps its pins, retargeted to the library call).
- **`js/ui/consent-link.js`:** "Complete the sign-in in your browser. This page updates when you're done." (A19; it also reaches chat).
- **`js/mcp-error.js` (A18):**
  - `buildMcpError(raw, {transport})` and `mcpErrorMessage(raw, {transport})`;
  - for `MCPConnectionError` with `transport: 'stdio'`: "The server's command didn't start or stopped. Open Technical details for its output.";
  - for HTTP: "Couldn't connect to this server. Check that it's running and that its address and headers are right, then try again.";
  - the "did not respond" headline ends "then try again.";
  - the editor and `mcps-tab.js` pass the source's type;
  - `.mcp-tools-error` gets `font-size: var(--font-size-body-sm)` in `studio.css`, so it is one size in both hosts. This is the FD's choice: the editor's error text gets smaller, the tab's too, and the `renderRetryUi` span shares the class;
  - `transport` defaults, so `mcpErrorMessage(raw)` keeps working. The editor passes the form's type when it sends a dirty body, and the saved type otherwise.
- **Defect 9:**
  - `collectFormData(handles, source, isEdit, {silent: true})` returns `{error}` instead of writing to the editor error;
  - a Test on a dirty form whose fields are invalid (for example no URL) shows that message in the result area and makes **no request** (falling back to a body-less POST would record `last_check` against the saved server);
  - it never writes into the editor error.
- **Squawk 0214:** `_render_oauth_callback_page` (`api.py` about `:4586-4720`) carries its styles inline and links nothing under `/static/`:
  - **an explicit minimal token subset** (`--bg`, `--surface`, `--border`, `--fg`, `--fg-secondary`, `--fg-muted`, the panel radius and shadow, the font sizes), light plus a `prefers-color-scheme: dark` override, with the system font stack;
  - `theme.js` and `fonts.css` are dropped, which loses an explicit in-app theme choice on this page. That is accepted;
  - the `@layer` line goes;
  - no CSP or nonce is needed (there is none in `the_one/`, and the page already uses inline code);
  - **unit tests:** no `/static/` reference; an inline `<style>` present; the `postMessage` script still present; and each inlined token value equals its value in `css/tokens.css`, so they cannot drift;
  - **closing the squawk:** it is `deferred` today, so record the corrective action, the verification and the disposition.
- **Squawk 0216:** the two racing assertions hold the `/test/connect` response with `page.route` (reuse or share the `_hold_requests` / `_wait_held` helpers from `test_flow_studio_mcp_editor.py`), assert the transient state, then release. The squawk (`deferred` today) is closed with its corrective action and disposition.
- **Dead CSS** goes: `.mcp-test-row`, `.mcp-connection-actions`, `.mcp-tools-last-updated`, `.mcp-refresh-connection-btn` and `.mcp-tools-status` (`studio.css` about `:106-125`, `:452-453`). Run `scripts/unused_selectors.py` on `studio.css` as a check, and paste the result.
- **Guards:**
  - this module's sinks go, including the `statusEl.innerHTML = ( 'Server exposes …` sink pinned at `tests/test_ui_guards.py:131, :245` (its pins are removed with the sink), except the tools-list line (`listEl.innerHTML = renderToolsListHtml(...)`, leg 09's) and anything leg 09 owns;
  - its `App.icon`, `App.confirmDelete`, `App.showFlash`, `btn-outlined-primary` and `indicator-led` uses go, and the oauth module's `App.consentLink.` uses go;
  - totals lowered, move entries retired, no new use;
  - `formatTimeAgo` is deleted from `mcp-editor-shared.js` if unused.
- **Testids:**
  - `mcp-test-connection` moves to the header Test;
  - kept: `mcp-test-status`, `mcp-connection-led`, `reset-mcp-connection-btn`, `mcp-consent-btn`, `mcp-connection-error`;
  - added: `mcp-connection-status` and `forget-mcp-connection-btn` (registry rows);
  - `mcp-tools-last-updated` is retired (registry and `RETIRED_SELECTORS`).
- **Tests:**
  - **`tests/browser/test_flow_studio_mcp_editor.py`** (lane `mcp`):
    - **derived relationships:** the status line's state equals `App.usage.mcpState(source).state` for each seeded server, and the LED's accessible name equals the line's state word;
    - **A9:** after a failed Test on a connected server, the line reads "Couldn't connect · last connected …", and reopening the editor shows the same;
    - **A7:** Reset only on an `oauth_active` server; Forget on a cached HTTP server without a sign-in; neither on stdio; both patch in place, keeping a dirty field's value and the caption;
    - **DD4's hold:** during a consent session Test reads "Waiting for sign-in…" and is disabled, while Save stays enabled on a dirty form;
    - **A8:** the result area is inside the Connection section and directly after the status line;
    - **defect 9:** a dirty invalid form plus Test leaves the editor error empty;
    - **A18:** the stdio and HTTP headlines;
    - **the retargets in this file:**
      - "Server exposes" (`:840, :1435, :2054, :2100, :2127, :2615`) moves to the status line and the Tools list;
      - "Last updated" and `mcp-tools-last-updated` (`:843-883, :2414`) move to the status line's time;
      - "Refresh connection" (`:1565`) becomes the header "Test";
      - "Confirm Reset?" (`:1144, :1278`) becomes "Reset connection?";
      - "Finalizing sign-in" (`:2118`) and "Awaiting sign-in" (`:2050, :2080`) become "Waiting for sign-in…";
      - the LED's `data-state` and class (`:2411-2414`) move to the status root's `data-state`;
    - **Forget and Reset disabled during a session**, and the Test label restored after a session is cancelled or destroyed;
  - **`tests/browser/test_mcp_test_connection_button.py`** (lane `library`): retargeted to the header Test (the "Refresh connection" asserts at `:64, :75, :119, :127`) and the status line, with squawk 0216's fix;
  - **`tests/browser/test_flow_studio_library_list.py:1342, :1353`** (lane `mcp`): "Server exposes" and the identity mark on `mcp-test-status` move to the status line and the Tools list. `mcp-test-status` is hidden after a success;
  - **`tests/browser/test_flow_studio_library_focus.py:82-131`** (lane `library`): it drives Test by testid, so it keeps working through the header button; check it;
  - **`tests/browser/test_ui_copy_contract.py:231`**: it pins "Finish signing in in" (the A19 typo), and is updated to the new text;
  - **`tests/browser/test_studio_mcps_tab.py`**: the A18 headline with the transport, and one font size (a computed-style check in both hosts);
  - **`tests/browser/test_oauth_modal_flow.py`**: the chat copy (A19's reach);
  - **a unit test for 0214.**
- **Captures:** the MCP surfaces into `m31-f5-l08b`, compared with the leg 08a set (or the leg 07 set). Differences map to rows 6, 7, 8, 9, 18, 19, 23 and 30. The agent MCPs tab's error surface maps to 18, and the chat sign-in, if captured, to 19.

## Acceptance Criteria
- [ ] **The editor and the list agree:** the status line equals `mcpState` for every seeded state, the LED is named, and A9 survives a reopen (tested).
- [ ] **B2:** Test is in the header in edit mode only; there is no Refresh button left; the auto-run still fires once for an HTTP create (existing tests).
- [ ] **A7 and defect 6:** the button predicates hold; Reset and Forget patch in place, keeping edits and moving focus correctly (tested).
- [ ] **The consent flow** keeps every popup rule (existing tests, unedited apart from retargets), shows A19's wording, and holds Test during the session (tested).
- [ ] **A18:** one headline per transport and one size in both hosts (tested).
- [ ] **Defect 9** (tested); squawks 0214 and 0216 closed, each with its test.
- [ ] **Lanes and files pass:** `mcp`, `library`, `agents` (the MCPs tab), `shared` (`test_oauth_modal_flow.py`, `test_flow_oauth_callback_cross_site.py`); `tests/test_consent_link_static.py`, `tests/test_store_static.py`, the static guards, `make test-unit`.
- [ ] **Guards lowered,** with no stale move entry; every `mcp-*.js` file at 800 lines or fewer.
- [ ] **The captures differ only on the listed rows** (FD-checked, each judged against its row).

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp -x`, then `--lane library -x`, then by file: `tests/browser/test_studio_mcps_tab.py`, `test_oauth_modal_flow.py`, `test_flow_oauth_callback_cross_site.py`. At most 3 at a time.
- `.venv/bin/python -m pytest tests/test_consent_link_static.py tests/test_store_static.py tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_area_module_size.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_nav_helper.py -q -x --timeout 120`, the 0214 unit test, then `make test-unit`.
- The capture compare.

## Implementation Guidance
1. **Tests first:** the derived-relationship, A9, A7, hold, A8 and defect 9 tests, plus the 0214 unit test. Record which fail and why.
2. **`mcp-error.js`** (A18) and **`consent-link.js`** (A19), with the MCPs tab passing the transport.
3. **The status row and the header Test,** reading `mcpState`; the refetch after every outcome; the session hold.
4. **Reset and Forget,** patching in place, with flash and error placement.
5. **The consent module** on `App.ui.consentLink`.
6. **0214 and 0216.**
7. **Guards, testids, lanes, captures and the ledger.**

## Edge Cases
- **A source with a cache but no `last_check`** (pre-flight) reads "Connected · checked {last_updated time}".
- **A Test result for a torn-down mount** writes nothing (leg 03) but still invalidates (leg 08a).
- **The desktop webview** (`window.open` returns `null`): the consent link block shows, and polling still runs (the existing test `test_null_popup_shows_link_block_keeps_polling_and_lists_tools`).
- **Forget on a server mid-consent:** Forget is disabled while a session runs (Test is held); state it and test it.
- **The time zone:** `App.time` follows the operator zone. The tests use the `frozen_clock` conventions or assert on the shape, not the digits.

## Files Affected
- `js/areas/studio/mcp-connection-status.js`, `mcp-oauth-consent.js`, `mcp-editor-lifecycle.js` (the session hold), `mcp-server-editor.js` (the header Test placement, `collectFormData`'s silent mode), `mcp-editor-shared.js` (`formatTimeAgo`, `hasOAuthState`), `mcps-tab.js` (the transport); `js/mcp-error.js`; `js/ui/consent-link.js`; `css/studio.css`.
- `tests/browser/test_ui_copy_contract.py`, `test_flow_studio_library_list.py`, `test_flow_studio_library_focus.py` (as checked); `tests/test_ui_guards.py`.
- `the_one/interfaces/web/api.py` (the 0214 callback page) and a unit test.
- `tests/browser/test_flow_studio_mcp_editor.py`, `test_mcp_test_connection_button.py`, `test_studio_mcps_tab.py`, `test_oauth_modal_flow.py`; `tests/test_consent_link_static.py`, `tests/test_store_static.py`, `tests/test_nav_helper.py`; the guard tables.
- `docs/ui-testid-registry.md`; `squawks/0214-…`, `squawks/0216-…`; the flight log and ledger.

## Citation Audit
- `mcp-connection-status.js` (read by the FD on the leg 05 tree, 2026-10-25): `renderConnectionActions` `:25-60`, `wireResetButton` `:76-117`, `syncResetButtonVisibility` `:119-161`, `handleTestConnection` `:169-357`. Legs 06-08a edit nearby; re-locate at the start.
- `mcp-oauth-consent.js:222` "Finalizing sign-in…"; `ui/consent-link.js:65`; `mcp-error.js` (read in full). FD read.
- Squawks 0214 and 0216: their evidence from the code survey (`api.py:4661-4663`; `test_mcp_test_connection_button.py:191, :196`). Re-check at the start.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes.** Applied in place:
  - the LED is decorative and the line's text carries the state, with the state map (H);
  - every test that asserts removed or renamed text, enumerated (H);
  - Reset and Forget built with a confirm-title span and an announce name, never rebuilt on a refetch (H);
  - the session hold through the lifecycle module, `testBtn` as a handle, one sign-in text (H);
  - Reset and Forget disabled during a session (M);
  - a dirty-form Test leaves the line on the saved record, with a note (M);
  - defect 9 makes no request and uses a silent `collectFormData` (M);
  - the refetch through `getSource()`, and `hasOAuthState` simplified (M);
  - the Tools list not cleared on Test start and emptied by Reset or Forget, with the hint reworded (M);
  - no nested live regions (M);
  - 0214 with a minimal token subset pinned to `tokens.css` (M);
  - the Test wiring outside the controller, the `dayNumber` check, the A18 size and transport default, the dead CSS, and the clearing of a Reset error (L).
  - FD answers: the result area is hidden at rest; Test is blocked while busy; one sign-in text; the line stays saved on a dirty Test; body-sm; "Forget tools list?".

  Clarifications and decisions within the design, so there is no second cycle. Status `ready`.

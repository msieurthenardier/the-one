# Leg: focus-after-action

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

After an in-place action in any of the six editors, keyboard focus lands on a sensible
control instead of dropping to `<body>` (Flight 3 checkpoint Q7, flight DD2). One shared
helper does it, and it never takes focus from a control the user moved to while the
request was running.

## Context

- **Flight DD2** is the contract. Read it, including its scope and exclusions:
  - closing actions keep Flight 3's DD8;
  - knowledge-base create keeps focusing the folder-path input (squawk 0101);
  - heading levels are unchanged.
- **The survey** (read-only, 2026-10-06). What happens today, for each editor and action,
  is in the flight log's Leg 1b design note. The facts that shape this design:
  - **Disabled replacements.** After a successful Save, an edit-mode Cancel or a create
    that becomes edit mode, the replacement Save and Cancel buttons are **disabled**,
    because the form is clean. A disabled button cannot take focus, so in practice focus
    must go to the editor's title. Only Test buttons and failed saves can get their own
    button back.
  - **The studio titles can't take focus.** The agent, MCP, connector and knowledge-base
    titles are `h1.editor-title` with **no** `tabindex`. The provider and tool titles are
    `h2` with `tabindex="-1"`.
  - **Several paths re-render asynchronously:**
    - agent create (four fetches in `doSelect`);
    - connector create and edit-mode Cancel (`fetchAgents`);
    - knowledge-base save (the status and items fetches);
    - MCP create (the `ready` promise).

    The helper must run **after the mount**, not when the action's request resolves.
  - **Some actions disable their own control as soon as they start:** knowledge-base
    Save and Create, tool Save, provider Test, tool Test and MCP Test connection. Focus is
    already on `<body>` before any response arrives.
  - **Agent edit-mode Save has no generation guard,** so the helper needs its own.
  - **Provider create's `keepFocus`/`hadFocus`** (`admin.js` `mountProviderItem`) is the
    one existing restore path. No test pins it after a Create. This leg replaces it with
    the shared helper.
  - **No existing test asserts focus** after an edit-mode Save, an edit-mode Cancel, a
    Test, or a create other than a knowledge base's. The neighbouring pins a change must
    not break:
    - the closing actions in `test_flow_settings_items.py`, `test_flow_provider_editor.py`,
      `test_flow_agents_list.py` and `test_flow_studio_library_list.py`;
    - `test_store_notification_and_refresh_never_move_focus`;
    - `test_nav_guard.py`'s Continue → `#main-content`;
    - `test_flow_studio_library_list.py:499`, focus on the folder-path input after
      knowledge-base create.

## Inputs

Leg 1a's uncommitted work. Run 1b after 1a lands: both touch `provider-editor.js` and
`studio.js`.

## Design

**The helper:** `App.focusAfter` in a new `static/js/focus-after.js`, loaded before the
area modules. It is not an `App.ui` factory, so it needs no demo or inventory row.

| Call | When | Behaviour |
|---|---|---|
| `var t = App.focusAfter.begin(control)` | When the action starts, before anything disables `control` | Records whether `control` was `document.activeElement` (`hadFocus`) and a sequence number. A newer `begin` supersedes older ones. |
| `App.focusAfter.restore(t, target)` → boolean | After the editor has **mounted** or patched its final state, including after the editor's own final disable or re-enable | It returns `false` and does nothing unless all three hold: `t` is non-null and `t.hadFocus`; `t` is still the latest, uncancelled token; and **focus is lost**. Focus counts as lost when `document.activeElement` is `null`, `<body>` or `<html>`, **or** is `t.control` itself, **or** is disabled, **or** is no longer connected. This covers a focused button disabled in place, which some engines leave as `activeElement`. Otherwise it focuses `target` in a `setTimeout(0)` (after `nav.js`'s `setTimeout(focusMain)` and after synchronous re-renders), scrolling it into view as `nearest`, and returns `true`. `target` is an element or a function returning one, resolved when the timer fires. If the element is disabled or detached at that moment, it does nothing. |
| `App.focusAfter.cancel()` | From every teardown: `studio.js` `closeOpenItem`; `admin.js` `_discardEditor`, `_setCategory` and `_closeOpenItem` (anything that bumps `editorGen`) | Invalidates all outstanding tokens, so a closed or superseded editor can never restore. |
| `App.focusAfter.defer(t, targetFn)` / `App.focusAfter.flush()` | Async create mounts | `defer` parks a token as the single pending restore. `flush()` runs the pending restore (if any) once and clears it. `cancel()` clears it too. |

**Where each call goes** (the review's corrections):
- **Test buttons:** `begin` runs **before** the handler's `disabled = true`. `restore` is
  called exactly once, from the handler's `settle()` (or equivalent) where the button is
  re-enabled.
  - MCP `handleTestConnection` has about nine `settle()` sites. Put the call in `settle`
    itself.
  - Paths that keep the button disabled (the popup and consent path) never call it.
  - `settle` also runs on the auto-run-after-create path, where no token exists, so
    `restore(null, …)` must be a no-op.
- **Async create mounts:**
  - **agent create:** `save(true)` → `loadAll` → `replaceWithAgent_` → hydrate →
    `doSelect` (four fetches) → `renderEditor`;
  - **connector create:** through `fetchAgents`;
  - **MCP create:** through `ready`.

  At the Create click, the orchestrator calls `defer(t, titleFn)`. The mount site calls
  `flush()` right after its final render: `doSelect`'s `.then` after
  `renderEditor`/`writeUrl_` (guarded by its existing `mySelect` check), the connector's
  `renderConnectorEditor` after `fetchAgents`, and the MCP's `renderMcpSourceEditor` in
  `ready.then`. Teardowns `cancel()` it.
- **Agent edit-mode Save:** `renderEditor(found)` runs inside `save`'s own promise, so
  `restore` goes right after it. The branch where `found` is null does not restore.
- **Failed Save or Create:** `restore` goes where each editor re-enables or leaves the
  button usable.
  - The agent editor's `.catch` never disables Save, so `restore` goes in the `.catch`.
    Its early validation returns (name required) happen before any disable, so focus
    stays put and needs no `restore`.
  - The provider save, after leg 1a's `fetchJson` switch: the `.catch` leaves Save
    enabled.
  - The knowledge-base detail: the `.catch` re-enables it through `checkDirty()`.
  - The tool editor: the failure branch re-enables it.

  Name each site in the flight log.
- **The provider's two paths stay exclusive.** Provider create's new path keeps today's
  `if (reveal) … else if (keepFocus)` exclusivity (now `else` → `restore`), so
  `revealItem` and `restore` never both run.
- **The knowledge-base detail** repaints rows after its status and items fetches. The title
  target is a function resolved when the timer fires, and the test asserts after those
  fetches settle.
- **Read leg 1a's diff first.** 1a edits `provider-editor.js` `performSave` and `studio.js`
  (the root heading). Re-read both files at the start of this leg.

**Targets:**
- **Save (edit mode) and edit-mode Cancel:** the editor's `.editor-title`.
- **Create** (agent, MCP, connector, provider): the new editor's `.editor-title`.
  Knowledge-base create keeps `kbFocusFolderFor`, which is untouched.
- **A failed Save or Create:** the same button, once the editor re-enables it.
- **Test** (provider `test-connection-btn`, tool `test-tool-btn`, MCP
  `mcp-test-connection`): the same button, once it is re-enabled.
- **The agent General tab's `test-provider-btn`** never disables, so it needs nothing.

**Titles.**
- **Which ones.** Add `tabindex="-1"` to the five studio `.editor-title` sites so they can
  take focus:
  - `agent-editor.js:79` (an HTML string);
  - `mcp-server-editor.js:486` (an HTML string);
  - `connector-editor.js:251` (DOM `className`);
  - `knowledge-section.js:344` (create);
  - `knowledge-section.js:467` (detail).
- The heading level is unchanged, and `tabindex="-1"` adds nothing to the tab order.
- **Focus styling** matches the provider and tool titles' existing treatment. If those
  have none, add one shared `.editor-title:focus` rule that suits a heading, with no heavy
  ring on a programmatic focus. Check it against `tests/test_ui_guards.py` and the a11y
  tests.

## Acceptance Criteria

- [ ] **The helper.** `static/js/focus-after.js` exists, is loaded in `index.html` before
  the area modules, and behaves exactly as the Design table says.
  - **Contract test,** `tests/browser/test_ui_focus_after_contract.py` (the `contracts`
    lane: engine-parametrized with the `engine_page` fixture, Chromium **and** WebKit,
    run with `THE_ONE_REQUIRE_WEBKIT=1`). It covers:
    - no restore without `hadFocus`, and none for a null token;
    - no restore when superseded, or after `cancel()`;
    - no restore when focus is on another enabled element;
    - restore when `activeElement` is the token's own control **disabled in place**;
    - restore when the control was removed;
    - a function target resolved when the timer fires;
    - no focus on a disabled or detached target;
    - `defer` then `flush`, and `cancel` clearing a deferred token;
    - the boolean return value.
- [ ] **Wired in all six editors,** with `begin` at the action's start and `restore` after
  its final mount or patch. Every call site is listed in the flight log:
  - **agent:** `save(false)` (edit), `save(true)` (create, after `doSelect`'s
    `renderEditor`), `cancelEdit`;
  - **MCP:** Save (edit), Create (after the `ready` mount), edit-mode Cancel, Test
    connection;
  - **connector:** Save (edit), Create (after the `fetchAgents` mount), edit-mode Cancel;
  - **knowledge base:** detail Save (after `renderKnowledgeDetail`), detail edit-mode
    Cancel; create is unchanged;
  - **provider:** Save (edit), Create (replacing `keepFocus`/`hadFocus` in
    `mountProviderItem`), edit-mode Cancel, Test connection;
  - **tool:** Save, Cancel, Test.
- [ ] **Titles focusable.** The four studio titles carry `tabindex="-1"`, and their
  heading levels are unchanged.
- [ ] **Browser tests** (in the existing lane files, or new `test_flow_*_focus*.py` files
  in the right lanes; a new Library file is added to `library_pat` in
  `scripts/run-tests.sh`). A keyboard-driven action is focus on the button, then Enter:
  - for each of the six editors: an edit-mode Save on a dirty form leaves focus on that
    editor's `.editor-title`;
  - for each of the six editors: an edit-mode Cancel leaves focus on `.editor-title`;
  - agent, MCP, connector and provider Create leave focus on the new editor's
    `.editor-title`;
  - provider, tool and MCP Test leave focus on the Test button after it re-enables, with
    the routes intercepted:
    - MCP: `**/api/mcp-sources/{sid}/test/connect`, as in
      `tests/browser/test_mcp_test_connection_button.py`;
    - provider: `/api/providers/{id}/test`;
    - tool: `/api/tools/configs/{name}/test` (`tools-editor.js:588`);
  - one failed save (a provider with an intercepted 422 or 500) leaves focus on Save;
  - **a "never steal" case:** a provider Save PUT held by `page.route`; focus moved by
    `.focus()` to the editor's name field; the route released with `route.continue_()`
    after a deliberate wait. Focus stays on the name field.
  - **Keyboard-driven actions** (`.focus()` on the button, then `keyboard.press("Enter")`)
    throughout, so `hadFocus` holds in every engine.
  - **Existing pins pass unchanged:**
    - knowledge-base create → folder-path input;
    - every closing-action focus test;
    - the store-notification focus test;
    - the nav-guard Continue test;
    - `test_flow_dirty_confirm.py` and `test_flow_provider_dirty_confirm.py` (a Continue
      followed by a save can leave a token pending, so check both).
- [ ] **Docs.** `the_one/agents.md` gets a short "Focus after an in-place action" block (the
  helper, the targets, the never-steal rule, the excluded closing actions and the
  knowledge-base exception). `CLAUDE.md` gets one sentence where the editor contracts are
  described.
- [ ] **Gates.**
  - `ruff` passes; the static guards pass; `TEST_TIMEOUT=3000 make test-unit` passes.
  - The `agents`, `library` and `settings` lanes pass, `shared` with
    `TEST_TIMEOUT=3600` (since `index.html` changed), and `contracts` with
    `THE_ONE_REQUIRE_WEBKIT=1`. `THE_ONE_TEST_NETNS=1` for all.

## Verification Steps

- Run the new focus tests file by file (`-m browser <path>`), then each lane in the
  background.
- In the flight log, list each call site with its `begin` and `restore` points.

## Implementation Guidance

1. **The helper and its unit test first.**
2. **The titles' `tabindex`.**
3. **Wire the editors one at a time.** Find each action's final mount or patch point
   using the survey in the flight log. For the async mounts, call `restore` at the end of
   the mount (a callback the orchestrator passes, or a check in the mount function).
   Never call it where the request resolves.
4. **Remove `keepFocus`/`hadFocus`** from `admin.js` `mountProviderItem`, and route provider
   create through the helper.
5. **Tests, editor by editor,** then the full lanes.

## Edge Cases

- **A Continue during the request.** The `setTimeout(0)` restore lands after `nav.js`'s
  `focusMain`, and the never-steal rule then sees `<main>` focused and does nothing. That
  is acceptable: the user navigated.
- **A double Enter on Save.** The second `begin` supersedes the first, so only the latest
  action restores.
- **An editor closed during the request.** The target function finds no title (detached),
  so nothing happens.
- **A pointer click that doesn't focus the button** (WebKit/macOS behaviour): `hadFocus` is
  false, so nothing happens and there is no focus theft. Keyboard users, who need this,
  always have focus on the button.
- **Out of scope** (note only; log a squawk if confirmed): the studio create flashes
  ("Agent created", MCP, connector) are wiped by the re-render, and the agent editor's
  `editor-unsaved` live region is rebuilt on every save.

## Files Affected

- `the_one/interfaces/web/static/js/focus-after.js` (new) and `index.html` (the script
  tag).
- `areas/studio.js`, `areas/studio/agent-editor.js`, `mcp-server-editor.js`,
  `connector-editor.js`, `knowledge-section.js`.
- `areas/admin.js`, `areas/admin/provider-editor.js`, `areas/admin/tools-editor.js`.
- Browser tests in the `agents`, `library` and `settings` lanes, plus
  `scripts/run-tests.sh` if a new Library file is added.
- `the_one/agents.md`, `CLAUDE.md`; the flight log.

## Citation Audit

Based on the 2026-10-06 survey of the working tree during leg 1a; line numbers in
`studio.js` drift with 1a's edits, so locate code by symbol:
- **`studio.js`:** `save` and its create branch, `cancelEdit`, `renderEditor`, `doSelect`,
  the MCP `onSaveSuccess` and `renderMcpSourcesSection`, the connector `onSaveSuccess`
  and `renderConnectorsSection`, `mountKnowledgeDetail`, `kbFocusFolderFor`.
- **`admin.js`:** `mountProviderItem` (`keepFocus`, `hadFocus`), `revealItem`, `editorGen`,
  the tools editor wiring.
- **`provider-editor.js`:** `performSave`, the Cancel handler, the Test handler.
- **`tools-editor.js`:** Save, Cancel, Test.
- **`mcp-server-editor.js`:** Save, Cancel, `handleTestConnection`.
- **`connector-editor.js`:** Save and Cancel. **`knowledge-section.js`:** detail Save and
  Cancel.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

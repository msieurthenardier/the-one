# Leg: flash-and-feedback-options

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Fix the library's feedback controls and their contracts before any chat control depends on them:
- **`App.ui.flash`'s container contract (DD5):**
  - one page region;
  - the modal exception, using modal's own stack;
  - re-homing a toast when its modal closes;
  - the newest toast replacing the one showing;
  - `container` removed from every caller, including the `App.showFlash` delegate;
  - A14's wording.
- **`App.ui.badge.live`** for badges that change in place (DD4, DD6).
- **The icon-only `App.ui.copyButton`'s visible confirmation** (D1).
- **`App.ui.noteFlag`,** moved into the library, with `App.iconNode` deleted.
- **The unlayered tail of `components.css`** moved inside `@layer components`, with a unit check.

## Context
- **Flight decisions:** DD4, DD5, DD6, DD9 (test 6), DD11 7 and 10, DD13, DD14 (the aliases) and DD15; ledger rows 14, 37 and 38.
- **`App.ui.flash` today** (`js/ui/feedback.js:123-145`):
  - `container = opts.container || document.body`;
  - the toast is appended to it;
  - `.visible` is added after 10 ms;
  - it is removed `duration` (5,000 ms) plus 300 ms later;
  - the timers check `isConnected`.

  `.app-flash` is `position: fixed; top: 16px; left: 50%` (`components.css:11`), so the container decides only lifetime, not position. Two toasts at once overlap exactly.
- **The callers** (`git grep -n "App.ui.flash(\|App.showFlash("` outside `js/ui/`), at about 33 sites:
  - `app.js:288` — the `App.showFlash(container, msg, isError)` delegate, which passes `container || document.body`. Its only callers are `markdown.js:794`, `:800` and `:804`, with container `wrap`, the code block inside an assistant bubble inside `.messages[role=log]`.
  - `provider-editor.js` — `:360`, `:420`, `:425`, `:434`, `:437`, `:444`, `:480`, `:485` ("Error: " + message), `:672`, `:692`.
  - `agent-editor-controller.js` — `:455`, `:478`, `:482`, `:514`, `:519`, `:526`, `:733`, plus the local `showFlash('Saved')` at `:690` and `:706`. Find that helper and route it through the new contract.
  - `mcp-server-editor.js` — `:299` ("MCP server created", lost to the create → edit remount), `:319`, `:412`.
  - `connector-editor.js:679` — "Connector created", lost to its remount.
  - `provider-models.js:314`, `mcp-connection-status.js:301`, `tools-editor.js:421`, `tools-page.js:279` and `:352`, `agent-data.js:467` and `agents-list.js:383`.

  Re-derive the list from the tree (leg 02 does not touch these files).
- **The modal stack** (`js/ui/modal.js`):
  - one module-level `var stack = []` (`:71` area), shared by every controller;
  - a per-controller `topmost()` (`:117` area);
  - `finish(s, value)` splices the stack and removes the `<dialog>` (`:136-141`);
  - `App.ui.modal.anyOpen()` exists already;
  - `App.confirmDialog` (`js/dialog.js`) is an adapter over it, and no other `showModal` exists in the app.
  - `.modal-overlay` is `position: fixed` with no transform, so a fixed toast inside the dialog stays tied to the viewport.
- **`App.ui.badge`** (`feedback.js:29-48`) throws on empty text and returns a static node. Its live-patching consumers: `chat-pane.js` (two uses, the new-chat model badge, hidden when empty) and `agent-drawer.js` (two uses, `:194` hidden empty, `:601` `badge.className = 'badge badge--' + kind`). `list-pane.js:264` and `tile.js:348` call `App.ui.badge` and expect a node, so the return type stays.
- **`App.ui.copyButton`** (`js/ui/copy.js`): icon-only mode changes only `aria-label` for 2 s ("Copied" / "Copy failed") and announces once through its live region. Sighted users see nothing. `App.icons.check` exists (`icons.js:29`). `App.ui.button` prepends the icon as a parsed SVG node, so check how a button's icon can be swapped (`ui/button.js:18-36`) and add a library way to do it rather than reaching into the button from outside.
- **`App.noteFlag`** (`icons.js:103-117`) is a control outside the library, with no catalogue row and no contract test. It uses `App.iconNode('alert-triangle')`, which is `App.iconNode`'s only caller. Its callers are `studio/notes-section.js:230` and `chat/agent-drawer.js:384`. The CSS `.note-flag` (`components.css:2598-2604`) sits outside every layer.
- **The unlayered tail** (`components.css:2596-2624`): `.note-flag*` and the `.consent-link*` family follow the `@layer utilities` block, outside any `@layer`. Unlayered rules beat every layered rule. No area stylesheet targets these classes today (grep: only a comment at `studio.css:930`). Moved to the end of `@layer components`, they keep their order inside the layer and still beat `@layer base`'s `a:any-link`.
- **The guards:**
  - `tests/test_ui_library_source.py` (the factory line rule `_FACTORY_LINE`, `_APP_GLOBAL` and `_ALIAS_LINES` (`:29-34`), which pins the alias lines);
  - `tests/test_ui_control_inventory.py` (a catalogue row plus a contract file calling `App.ui.<name>(` for every factory);
  - `tests/test_ui_emitted_classes.py`;
  - `tests/test_ui_ownership.py` (rows: `js/icons.js` `api:App.iconNode(` ×1 and `api:App.icon(` ×1; `js/areas/chat/chat-pane.js` `badge` ×2; `js/areas/chat/agent-drawer.js` `badge` ×2).
- **`provider-editor.js` has zero line headroom** (896 lines against the 896 ceiling in `tests/test_area_module_size.py`). Removing `container` from its flash calls keeps or lowers the count. Add no net lines.

## Inputs
- Legs 01 and 02 landed (batch B1 reviewed and committed before this leg starts).

## Outputs
- **`App.ui.flash`:**
  - It always appends to one lazily created page region, `div.app-flash-region` (a library-owned class; `aria-live` stays on each toast), re-appended to `document.body` if detached, following `ui/confirm.js`'s live-region pattern.
  - **The region lookup is exported** as `App.ui.flash.region()` (create if missing, re-append if detached). `modal.js` loads separately and cannot call a private function in `feedback.js`; it calls this at close time, when both files are loaded. The region is a plain block with no CSS. A `transform` or `contain` on it would make a containing block for the fixed toast.
  - **The modal exception:** `App.ui.modal.top()` (new, exported) returns the open `<dialog>` element of the topmost stack entry (`stack[stack.length - 1].dlg`), or null. When it returns one, the toast goes inside that dialog. `App.ui.modal.top =` has the same shape as the existing `App.ui.modal.anyOpen =`, so `_UI_ASSIGN` and the alias rules need no change.
  - **Re-homing:** in `finish`, **after** `stack.splice` (so the next dialog down is the new top) and **before** the dialog is removed, every `.app-flash` child of the closing dialog is **moved** (not cloned, so its timers and `isConnected` checks keep working) to `App.ui.modal.top()`, or to `App.ui.flash.region()` when none is open.
  - **The newest replaces the one showing:** a new toast removes the previous one, wherever it is, and clears that toast's pending timers. The timer handles are kept on the node or in a module variable.
  - **The `container` option is removed** from the factory's documented options. A passed `container` is ignored and no longer throws. The catalogue row and `agents.md` are updated.
- **Every caller** drops `container`, including the `App.showFlash` delegate (`app.js:287-289`), so markdown's copy toast leaves the message log in this leg.
  - DD9 test 6 is written here, failing first: "no `.app-flash` inside `.messages`" after a code-block copy.
  - That fixes DD11 7.
  - `App.showFlash` itself stays until leg 09a (its alias deletion).
- **A14:**
  - the agent editor's "Saved" becomes "Agent saved" (`agent-editor-controller.js:690`, `:706`);
  - the provider delete error drops its "Error: " prefix (`provider-editor.js:485`);
  - any other flash string ending in "!" loses it, apart from markdown's "Copied!", which goes with leg 07's library button.
  - Tests that read these strings are retargeted.
- **The Flight 5 page-flash comments** in the provider and MCP editors (for example "the page, not the editor: the success callback discards it") are simplified, now that every toast goes to the page.
- **`App.ui.badge.live(opts) → {el, set({kind, text})}`:**
  - it validates `kind` like `App.ui.badge`;
  - empty or null text sets `hidden` on the badge and is not an error;
  - `set` patches the class and text in place.

  `chat-pane.js` and `agent-drawer.js` move onto it, removing their four `badge` uses and two ownership rows.
- **`App.ui.button.setIcon(btn, name)`** (new, in `button.js`) replaces the button's first `svg` child with `App.ui.util.icon(name)`. The Button catalogue row mentions it.
- **`App.ui.copyButton` icon-only confirmation:**
  - on success, the button's icon swaps to `check` (through `setIcon`) and its `title` reads "Copied", for 2 s, alongside today's `aria-label` change;
  - on failure the title reads "Copy failed" and the icon stays `copy`;
  - on revert the icon goes back to `copy` and the `title` attribute is removed (today there is none);
  - a `title` alone is weak feedback on touch. That is accepted: the check icon is the visible signal;
  - it is announced once through the live region;
  - a contract test proves it is announced once under a `role=log` ancestor (or the control takes a `liveEl` outside the log), with the button keeping its name and focus.

  The text-button mode is unchanged.
- **`App.ui.noteFlag(opts)`**, with `opts = {sources}`, in an existing `js/ui` file (`feedback.js` recommended). It takes `opts` because `_FACTORY_LINE` (`tests/test_ui_library_source.py`) admits only `opts` or a listed prefix before it, and a bare `sources` parameter fails. The two callers change from `App.noteFlag(list)` to `App.ui.noteFlag({ sources: list })`. It builds the same node as today: `span.note-flag[role=img]`, with the same sentence in `title` and `aria-label`, and the icon through `App.ui.icon('alert-triangle')`.
  - Its two callers move to it.
  - `App.noteFlag` and `App.iconNode` are deleted from `icons.js`. That removes both `js/icons.js` ownership rows: `App.icon(`'s only use there was inside `iconNode`.
  - It gets a catalogue row owning `note-flag` and a contract test (role, name and the icon, in both engines).
  - `App.icon` itself stays until leg 09a, because `markdown.js` still calls it until leg 07.
- **The unlayered tail** moves inside `@layer components`, at its end, unchanged.
  - A new unit test, in `tests/test_ui_guards.py` or a new `tests/test_css_layers.py`, fails on any rule in `components.css` outside an `@layer` block (comments allowed).
  - A computed-style check of `.consent-link-open` and `.note-flag` in both engines confirms the move changed nothing visible.
- **The allowance:** `OWNERSHIP_ALLOWANCE` loses the rows this leg removes (`chat-pane.js` / `agent-drawer.js` `badge`, `js/icons.js` ×2). `TOTAL_USES` changes accordingly: `badge` 5 → 1 (only `css/chat.css` remains), `api:App.icon(` 2 → 1, and the `api:App.iconNode(` key is deleted. `START_ROWS` keeps the removed rows; it only gates new rows. `MOVES` keeps leg 02's entries. If any entry names a row removed here, it is dropped with that row, or `stale_move_errors` fails.
- **Emitted classes:** the Flash row's Owned classes gain `app-flash-region`, and the new Note flag row owns `note-flag`. The ownership guard strips CSS comments and does not scan `components.css`, so the `studio.css:930` comment creates no row.
- **The catalogue** (`docs/ui-control-inventory.md`): the Flash row (new contract; the stale "`App.showFlash(container…)` stays…" and "migrates in Flight 4" wording fixed), the Badge row (`.live`), the Copy row (the confirmation), a new Note flag row and the Modal row (`top()`).
- **Docs:**
  - `the_one/agents.md` "Control library". The stale `rescueFlashes` / `App.showFlash(container)` sentence at about `:2336` is rewritten, not trimmed; `rescueFlashes` no longer exists. `:925` (`App.noteFlag`, `App.iconNode`) is updated too.
  - `docs/ui-testid-registry.md:324` (`App.noteFlag`).
  - CLAUDE.md only if it names the flash container.
  - **The behavior specs that quote A14's text:** `studio-agent-crud.md` steps 5 and 7 and `agent-retention-setting-roundtrip.md` step 2 read "Saved". They are re-authored here to "Agent saved". Leg 03c re-authors the same specs for D7's labels only.
- **Ledger rows 14, 37 and 38** confirmed or amended in the flight log.

## Acceptance Criteria
- [ ] **Flash contract tests** (`tests/browser/test_ui_feedback_contract.py`, both engines):
  - a toast flashed while a container exists, after which that container is removed, is still connected and visible;
  - a toast flashed while an `App.ui.modal` is open sits inside its dialog;
  - **a toast flashed in a modal survives that modal closing** and sits in the region or the next dialog;
  - a second toast replaces the first (one `.app-flash` in the document);
  - error toasts keep `role=alert` and others `role=status` with `aria-live=polite`.

  The old tests are retargeted to the new contract, not deleted: `test_flash_container_default_and_detached_container` (`:186-198`, `inBody` / `inHolder`), and the back-to-back test (`:171-183`, which expects an ok and an error toast both visible; under newest-replaces, it asserts the second replaced the first and kept its role). A further contract test checks that a toast flashed inside a modal sits at the same viewport position as one on the page.
- [ ] **Consumer tests, failing first on today's code:**
  - "MCP server created" is visible 200 ms after the editor remounts (the `mcp` lane);
  - "Connector created" likewise (the `library` lane);
  - after a code-block copy in a chat, `page.locator('.messages .app-flash')` has count 0 and `.app-flash` is visible (DD9 test 6; the `chats-transcript` lane).
- [ ] `git grep -nE "App\.ui\.flash\([^)]*container" -- the_one/interfaces/web/static/js` finds nothing, and `app.js`'s `App.showFlash` passes no container.
- [ ] **A14:** "Agent saved" shows after an agent Save, and the provider delete error has no "Error: " prefix. Every changed string is asserted by a retargeted or new test.
- [ ] **No stale toast across navigation:** the tests with a "no flash" assertion are re-read and pass: `test_flow_admin_tools_editor_save.py:177`, `test_flow_admin_tools_grid_library.py:132`, `test_flow_provider_library.py:92` and `test_flow_studio_loadall_error.py:63`. A page-level toast now outlives the editor that raised it, for its 5 s dwell.
- [ ] **Badge live:** a contract test (both engines) covers `set` changing kind and text, empty text hiding, and an unknown kind throwing. `chat-pane.js` and `agent-drawer.js` no longer build `badge` class strings, and their rows are gone from the allowance.
- [ ] **Copy confirmation:** a contract test (both engines) shows that after a successful click the button contains the `check` icon and `title="Copied"`, then reverts after 2 s. The announcement happens once under a `role=log` ancestor, and the text-button mode is unchanged.
- [ ] **Note flag:** `App.ui.noteFlag` has a catalogue row and a contract test. `git grep -n "App.noteFlag\|App.iconNode" -- the_one/` finds nothing. The drawer and the notes tab still show the flag (`chats`, `agent-tabs` lanes), and both `js/icons.js` allowance rows are gone.
- [ ] **CSS layers:** the new unit test passes, and fails when a rule is appended after the last layer (checked once, then reverted). The computed styles of `.note-flag` and `.consent-link-open` are unchanged in both engines.
- [ ] **Guards:**
  - `tests/test_ui_ownership.py`, `tests/test_ui_library_source.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_emitted_classes.py`, `tests/test_area_module_size.py` (`provider-editor.js` at most 896), `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass.
- [ ] **Lanes:**
  - `contracts-controls` and `contracts-overlay` with `THE_ONE_REQUIRE_WEBKIT=1`;
  - every editor lane: `providers`, `mcp`, `mcp-connection`, `library`, `knowledge`, `agents`, `settings`, `settings-tools`;
  - `chats`, `chats-transcript`, `agent-tabs` and `shared`.

  Run them at most three at a time; a full gate is not required in this leg.
- [ ] `make test-unit` passes after the browser runs. `ruff` is clean.

## Verification Steps
1. `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_library_source.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py tests/test_area_module_size.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -q -x --timeout 120`, plus the new layer test.
2. `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-controls -x --tb=short` (then `contracts-overlay`).
3. The editor and chat lanes listed above, each through `scripts/run-tests.sh --lane`, `THE_ONE_TEST_NETNS=1`.
4. `git grep -nE "App\.ui\.flash\([^)]*container|App\.noteFlag|App\.iconNode" -- the_one/`.
5. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The library first, tests first:** the flash contract tests and the consumer tests, which fail today. Then `App.ui.modal.top()` and the re-home in `finish`, then the flash region and the replace rule.
2. **The callers:** drop `container` everywhere, including the delegate, plus A14 and the comment clean-up. Run the editor lanes.
3. `App.ui.badge.live` and its two consumers.
4. **The copyButton confirmation:** add a library-owned way to swap a button's icon if `button.js` lacks one, not DOM surgery from `copy.js` on another factory's internals.
5. `App.ui.noteFlag`, its consumers, and the deletion of `App.noteFlag` and `App.iconNode`.
6. **The CSS layer move** and its unit test.
7. The allowance, catalogue and docs, then the lanes and `make test-unit`.

## Edge Cases
- **A flash during page teardown:** the region is created lazily on the next flash, never at script load. Don't create it before `document.body` exists.
- **A toast inside a dialog** must keep `position: fixed` relative to the viewport. Check in both engines that it is visible and not clipped by the dialog's overflow.
- **A modal closing while its toast is fading:** re-home it, keep its timers, and keep `isConnected` checks working after the move.
- **The replace rule and the error toast:** a success toast replacing an error toast is acceptable (the operator chose newest-replaces). Make sure the replaced alert was already announced: it was added to the DOM before being replaced.
- **`App.showFlash` callers** pass `(container, msg, isError)`. The delegate keeps its signature and ignores `container`.
- **A badge with an initially empty text** must render hidden, not throw. Today `agent-drawer.js:194` builds it with `hidden: true` by hand.
- **`App.ui.icon` is the library node factory** (`ui/core.js`). `noteFlag` must use it, not `App.icons` strings.
- **`App.ui.badge.live` coexists with `App.ui.badge`,** whose node return stays for `list-pane.js:264` and `tile.js:348`.
- **The admin wrapper:** `tools-page.js:279`, `:352` and the `showAdminFlash` wrapper at `:72` pass `ctx.contentEl()`. Removing `container` may leave `ctx.contentEl` unused in places; remove it only where it has no other use. The `:516` comment in `agent-editor-controller.js` about the "local one-arg showFlash wrapper" is cleaned up with it.
- **The layer test** must accept one-line `@layer` blocks, `@media` blocks nested inside a layer, and a bare `@layer a, b;` order statement.
- **`provider-editor.js`'s comment simplification** (`:480`) is done in place on the same line, so the file does not grow.
- **The ES5 rule in `js/ui`** (`test_ui_library_source.py` `_ES6`): no arrow functions, `let`, `const`, classes or template literals.

## Files Affected
- `the_one/interfaces/web/static/js/ui/feedback.js`, `js/ui/modal.js`, `js/ui/copy.js`, possibly `js/ui/button.js`, `js/icons.js`, `js/app.js`.
- The flash callers in `js/areas/**`, `js/areas/chat/chat-pane.js`, `js/areas/chat/agent-drawer.js`, `js/areas/studio/notes-section.js`.
- `the_one/interfaces/web/static/css/components.css`.
- `tests/browser/test_ui_feedback_contract.py`, `tests/browser/test_ui_copy_contract.py`, `tests/browser/test_ui_modal_contract.py`, a new note-flag contract test (or a section in `test_ui_feedback_contract.py`).
- The consumer tests in the `mcp`, `library` and `chats-transcript` lanes, and the CSS layer unit test.
- `tests/_ui_ownership_allowance.py`, `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- `js/ui/feedback.js:29-48` (`App.ui.badge`, which throws on empty text) and `:123-145` (`App.ui.flash`). FD-verified (read).
- `js/ui/modal.js`: the module `stack`, the per-controller `topmost()` and `finish` splicing and removing the dialog. FD-verified (grep).
- `js/icons.js:84-117`: `icon`, `iconNode` and `noteFlag`; `noteFlag` is `iconNode`'s only caller. FD-verified (read). `check` icon `:29`. FD-verified.
- `js/ui/copy.js`: icon-only feedback changes only `aria-label`. FD-verified (read).
- `css/components.css:2586-2624`: the layer ends, then the unlayered `.note-flag*` and `.consent-link*`. FD-verified (read).
- `agent-editor-controller.js:690`, `:706` (`showFlash('Saved')`) and `provider-editor.js:485` (`'Error: ' + err.message`). FD-verified (grep).
- The caller list was re-derived by grep at this leg's design (2026-10-27). Re-derive before editing.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only during leg 02): approve with changes.** Applied in place:
  - **[high] `noteFlag`:** it takes `opts` (`{sources}`) for `_FACTORY_LINE` (FD answer: change the two callers, not the guard);
  - **[medium] the modal and region contract:** what `top()` returns; the re-home order and moving, not cloning; the region exported as `App.ui.flash.region()` (FD answer) and left unstyled;
  - **[medium] the contract tests:** the back-to-back test retargeted, plus a same-position test;
  - **[medium] stale toasts:** the four "no flash" tests re-read;
  - **[medium] `setIcon`:** `App.ui.button.setIcon` with its revert, and the touch caveat accepted;
  - **[medium] emitted classes:** `app-flash-region` and `note-flag` owned;
  - **[low] bookkeeping:** `TOTAL_USES`, `START_ROWS` and `MOVES`;
  - **[low] docs:** the stale lines at `agents.md:2336` and `:925`, and the registry;
  - **[low] layers and admin:** the layer-test forms; the admin wrapper and comment;
  - **[low] the behavior specs** quoting "Saved", re-authored here;
  - FD answer: `badge.live` coexists with `App.ui.badge`.
- No second cycle (clarifications within the design).

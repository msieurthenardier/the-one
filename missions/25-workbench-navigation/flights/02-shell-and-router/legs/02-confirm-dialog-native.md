# Leg: confirm-dialog-native

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Build the library modal `App.ui.modal` on native `<dialog>` following Flight 1's DD8
rule, then re-implement `App.confirmDialog` as a thin adapter over it. The adapter keeps
its API and test ids, removes the singleton, and switches Enter to native semantics.
Pinned tests get their recorded dispositions, and Flight 1's reusable DD8 checks run
against the real wrapper in Chromium and WebKit.

## Context

- **Flight decision:** DD6 is this leg's spec: the modal API, its DD8 behaviours, the
  extras (manual Tab wrap, DOM removal, explicit `role`/`aria-*`, `.modal-overlay`
  restyle), the adapter, the Enter semantics, and the pinned-test disposition table.
  Read DD6 in `flight.md` in full. Also read F1 DD8 in
  `missions/25-workbench-navigation/flights/01-control-library-foundation/flight.md`,
  plus the Modals bullet and "Control library (`App.ui`)" in `the_one/agents.md`.
- **The Flight 1 race.** Flight 1's spike found that `dialog.close()` queues its
  `close` event as a task, so a dialog reopened in the same turn receives the stale
  event. The `close` listener must ignore `close` while `dlg.open` is true. The F1
  harness `tests/browser/_dialog_rule.js` already implements this; mirror it.
- **This leg is independent of the router.** The 11 guard call sites keep calling
  `App.confirmDialog` unchanged, and leg 5 (`unified-leave-guard`) later replaces them
  with `App.nav`. Their behaviour must stay as it is today, with two deliberate DD6
  changes: Enter activates the focused button, and Tab wraps.
- **Singleton timing** (a decision, recorded in the flight log). `App.ui.modal` itself
  stacks; there is no singleton in the factory. The **`App.confirmDialog` adapter keeps
  today's single-open policy in this leg**: a second call while one is open is ignored,
  with a `console.warn`. The guard sites can double-dispatch (a second `hashchange` from
  Back/Forward or a typed hash), and stacking two leave dialogs with their own
  `proceed`/`abort` would run a switch twice. The adapter's singleton is removed, and
  `test_singleton_modal_second_call_warns` inverted, in **leg 5** (`unified-leave-guard`), where `App.nav`'s
  single-flight guard owns de-duplication. This narrows DD6 for this leg only.
- **"Adding a factory" checklist** (`agents.md`): the file and its `<script>` tag plus
  the cache-busting count; CSS in `components.css`; contract tests in both engines; a
  `data-ui-demo` demo; an inventory row. If a static `testid:` is used, the registry
  row moves from manual or `setAttribute` form to `testid:` form.
- **Today's `dialog.js` (read it):**
  - a singleton guard (:59-77);
  - the trigger captured from `document.activeElement`;
  - a div overlay with `role=dialog`, `aria-modal`, and labelledby/describedby wired to
    the title and message;
  - Cancel focused on open;
  - a capture-phase document keydown handler: Escape → cancel, Enter → confirm, Tab
    trap;
  - overlay clicks do nothing;
  - the overlay is removed on close and focus restored.
- **CSS:** `.modal-overlay`, `.modal-dialog`, `.modal-dialog-title`,
  `.modal-dialog-message` and `.modal-actions` (`components.css:1341-1402`).
- **Tests that pin behaviour** (DD6 table): `test_flow_dirty_confirm.py` at :269, :297,
  :341, :374 and :485; `test_flow_provider_dirty_confirm.py:219`; and the
  `.modal-overlay` selector in `test_flow_studio_mcp_editor.py:252`. Eight browser files
  reference the confirm test ids.

## Inputs

- `the_one/interfaces/web/static/js/dialog.js` (the 225-line overlay).
- `the_one/interfaces/web/static/css/components.css` modal block (:1341-1402).
- `the_one/interfaces/web/static/js/ui/*.js` (idiom and `util`).
- `tests/browser/_dialog_rule.js`, `tests/browser/_dialog_rule_checks.py`
  (`DialogAdapter` and the `check_*` functions), and `tests/browser/test_ui_dialog_rule.py`.
- `tests/browser/_ui_engines.py` (`engine_page`, `load_harness`).
- The 13 `confirmDialog(` call sites (grep), including `design-language/modal-section.js:39`.

## Outputs

- **`ui/modal.js`** (new): `App.ui.modal(opts)` returns a controller
  `{el, open(opener), close(result), isOpen()}`.
  - Options: `title`, `body` (text or Node), `actions` (an array of
    `{label, variant, value, testid, autofocus}`), `dismissible` (default false),
    `onClose(value)`, `id` (on the `<dialog>`; needed by F1's fixture checks), and
    `testid` (on the `<dialog>`).
  - The card `.modal-dialog` gets `tabindex="-1"`, so a click on non-focusable card text
    keeps focus inside the dialog, and Escape still reaches the dialog's own handler.
  - The `<dialog>` is created on `open` and removed from the DOM on close.
- **`dialog.js`** rewritten as the `App.confirmDialog` adapter over `App.ui.modal`, with
  the same signature and test ids.
- **CSS:** `.modal-overlay` restyled for the `<dialog>` element.
  - It covers the viewport via `inset:0; width:auto; height:auto; max-width:none;
    max-height:none; margin:0; padding:0; border:0`, not `100vw`, which can add a
    horizontal scrollbar.
  - It has a transparent background, and the UA `dialog:modal` `color`, `overflow` and
    `background-color` are reset.
  - `display:flex` applies **only on `.modal-overlay[open]`**, and centres
    `.modal-dialog` as the visible card.
- **Scrim token:** a `::backdrop` rule uses a new **`--scrim`** token in both theme
  blocks: dark `rgba(0,0,0,0.5)`, light `rgba(0,0,0,0.3)`, the latter being today's
  literal. No `backdrop-filter`.
  - It is an rgba wash, so it stays out of the hex mirror per the mirror's own rule.
    `--scrim` is not under the completeness net's prefixes, so it needs no gate or
    exemption. Verify both guards pass.
- **Tests:**
  - `App.ui.modal` contract tests in both engines (`tests/browser/test_ui_modal_contract.py`);
  - a `DialogAdapter` for `App.ui.modal`, with the `check_*` functions run against it in
    both engines;
  - the DD6 dispositions applied in the pinned tests;
  - all 8 confirm-using browser files green.
- **Reference and docs:**
  - the reference page gains a `modal` demo (static, plus a live "Open" button);
  - the inventory row for `App.ui.modal`, and `App.confirmDialog` reclassified as
    library-backed;
  - `agents.md`: the Modals bullet updated (DD8 is now implemented) and the
    Control-library API entry for `modal`.
- **Flight log:** the leg entry.

## Acceptance Criteria

- [x] **AC1 — `App.ui.modal` structure.**
  - It renders `<dialog class="modal-overlay" role="dialog" aria-modal="true"
    aria-labelledby=… aria-describedby=…>`, containing `.modal-dialog` with
    `.modal-dialog-title` (an `<h2>`), `.modal-dialog-message` and `.modal-actions`
    buttons built with `App.ui.button`.
  - `open(opener)` calls `showModal()`, records the opener **explicitly**, and focuses
    the action with `autofocus: true`, else the first action.
  - `close(value)` closes, removes the element, and restores focus to the recorded
    opener, if it is still connected, else to `#main-content`.
  - The file is ES5, has no sink tokens, follows the export idiom, and uses no app
    globals.
- [x] **AC2 — DD8 behaviours.**
  - **Escape.** A `keydown` handler on the `<dialog>` calls `preventDefault()` and
    `stopPropagation()`, then closes the topmost dialog with the cancel value.
  - **`cancel` event.** It is prevented and routed through the same path.
  - **Stale `close` events.** The `close` listener ignores a stale `close` while
    `dlg.open` is true (the F1 race).
  - **Backdrop clicks.** A click closes the modal only when `dismissible` **and** both
    the `mousedown` target and the `click` target are the `<dialog>` element itself. A
    text-selection drag from the card out to the padding therefore never closes it.
  - **Unrouted closes.** A genuine close that bypassed the router (`!dlg.open` and not
    already finished, e.g. a CloseWatcher-skipped Escape, or `dlg.close()` from outside)
    runs the **full cancel path exactly once**: cancel value, `onClose`, DOM removal and
    focus restore.
  - **Exactly once.** `onClose(value)` fires exactly once per open, whichever path
    closes it.
  - **Close ordering:** close, remove from the DOM, restore focus, then call `onClose`.
    So `proceed`-style callbacks run after focus has moved to the opener. A throwing
    callback can't leave a dangling dialog.
  - **Tab wrap.** Tab on the last focusable element goes to the first, and Shift+Tab on
    the first goes to the last.
- [x] **AC3 — Contract tests.** `tests/browser/test_ui_modal_contract.py` runs in **both**
  engines (`engine_page`, `load_harness`) and covers AC1–AC2:
  - focus on open;
  - focus restore after a mouse open and after a keyboard open;
  - Escape;
  - Tab and Shift+Tab wrap;
  - backdrop click when dismissible and when not;
  - a drag from the card out to the backdrop, which does not close it;
  - Escape with focus on `body`;
  - an external `dlg.close()` running the cancel path once;
  - `onClose` fired exactly once for each path: Escape, backdrop, programmatic
    `close()`, unrouted close, and a stale `close` on reopen;
  - deterministic WebKit Tab wrap, with the `<dialog>` element included or excluded as
    documented;
  - DOM removal;
  - two stacked modals, where Escape peels one layer at a time;
  - the stale-`close` reopen;
  - `assert_controls_labelled_and_described` over an open modal.
- [x] **AC4 — DD8 checks on the real wrapper.** `_dialog_rule_checks.py` gains a
  `DialogAdapter` backed by `App.ui.modal`, run from `tests/browser/test_ui_dialog_rule.py`
  or a new file.
  - All existing `check_*` functions pass against it in both engines: stacked Escape,
    programmatic confirm, focus restore (mouse and keyboard), backdrop clicks,
    inertness and backdrop colour.
  - The backdrop-colour check reads the real `::backdrop` rule, through the new
    `--scrim` token. The adapter passes `backdrop_token='--scrim'` and sets ids through
    the modal's `id` option.
  - Fixture bodies (buttons inside modal A) are passed as a Node `body`.
  - Checks must tolerate the real modal being created on open and removed on close.
- [x] **AC5 — `App.confirmDialog` adapter.** It has the same signature and defaults:
  title "Unsaved changes", message, Continue / Stay, `onConfirm` and `onCancel`.
  - Built on `App.ui.modal`, with Cancel (Stay) `autofocus`.
  - Test ids: `confirm-dialog-overlay` on the `<dialog>`, plus `modal-cancel-btn` and
    `modal-confirm-btn`.
  - **Single-open retained in this leg**, as today: a second call while one is open is
    ignored with a `console.warn`. This is removed in leg 5 (see Context).
  - **Enter** activates the focused button, natively. The document-capture
    "Enter → onConfirm" handler is gone.
  - The opener is `document.activeElement` when it isn't `body`, else `#main-content`.
    This matches today's API, which takes no opener.
- [x] **AC6 — Pinned-test dispositions** (rename over delete; the docstring says why):
  - `test_singleton_modal_second_call_warns` **stays as it is in this leg**: the adapter
    keeps its single-open policy. Leg 5 inverts it. Stacking is proven at the factory
    level instead, in `test_ui_modal_contract.py`.
  - `test_modal_enter_confirms` and `test_dialog_enter_confirms` are **renamed and
    inverted** to `…_enter_activates_focused_stay`. Enter with default focus fires
    Stay, never Continue: the dialog is gone, and the hash and editor are unchanged.
    - A companion test checks that Tab to Continue, then Enter, confirms.
    - The module docstrings of `test_flow_dirty_confirm.py` (":19 Modal Enter confirms")
      and `test_flow_provider_dirty_confirm.py` (":16 Enter confirms") are updated.
  - These keep their assertions and pass:
    - `test_modal_focus_trap_tab_cycles_forward` and `…_shift_tab_cycles_backward`;
    - `test_modal_aria_contract` (role, aria-modal, labelledby, describedby);
    - the `.modal-overlay` selector test;
    - every `to_have_count(0)`-after-close assertion.
- [x] **AC7 — Every confirm call site still works.** The 8 browser files that use the
  confirm test ids pass. That covers the dirty-confirm, provider-dirty-confirm,
  cross-area dirty gate and MCP editor flows.
  - The only behaviour changes are DD6's Enter semantics and the Tab wrap.
  - The single-open policy is unchanged in this leg.
- [x] **AC8 — Factory checklist.**
  - `<script src="/static/js/ui/modal.js">` goes after the other `ui/` scripts, and the
    count test is bumped.
  - A `[data-ui-demo="modal"]` demo goes on the reference page, in both theme panes.
    - It has a static card preview, a live "Open modal" button that opens a real
      `App.ui.modal` (with a distinct `testid`, never `confirm-dialog-overlay`), and a
      live "Open confirm dialog" button that calls `App.confirmDialog`.
    - The existing `design-language/modal-section.js` is **retired**: deleted, with its
      `<script>` tag and `SECTIONS` entry removed. Its static preview and live confirm
      move into the demo. The cache-busting count is net 67 → 67 (+`ui/modal.js`,
      −`modal-section.js`). Recompute it from `index.html`.
    - The reference-page test keeps passing; the live modal is appended to `body`,
      outside `[data-ui-demo]`, only on click.
  - The inventory row reads `library: App.ui.modal`. `App.confirmDialog` is updated to
    "library-backed adapter".
  - The inventory and demo guards pass.
- [x] **AC9 — Docs.** `agents.md`:
  - the Modals bullet describes the implemented rule: native `<dialog>`, the stale-close
    guard, Tab wrap, Enter semantics and no singleton;
  - the "Control library" section documents `modal` and the confirm adapter.
- [x] **AC10 — Gates pass.**
  - `make lint`;
  - `make test-unit`, including the static guards, the a11y suite and the cache-busting
    count;
  - every `tests/browser/test_ui_*.py` in both engines, with no skips except the
    documented forced-colors one;
  - the `settings` lane and the `agents` + `library` lanes (the confirm call sites live
    there);
  - `--lane shared`.

  The WebKitGTK probe runs once, with a setup script that opens an `App.ui.modal` on the
  reference page: `ok: true` in dark and light, with the result recorded.

## Verification Steps

- AC1–AC4:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_modal_contract.py tests/browser/test_ui_dialog_rule.py -x -rA`.
  Both engines must appear.
- AC5–AC7: run the 8 confirm-using files, using `grep -l "modal-confirm-btn"
  tests/browser` to list them, plus the lanes named in AC10.
- AC8–AC9: the inventory guard, the reference-page test and a doc read.
- AC10: the listed commands, and the probe JSON in the flight log.

## Implementation Guidance

1. **`ui/modal.js`** first, plus its script tag and the count bump. Port the stale-close
   guard and the Escape handling from `tests/browser/_dialog_rule.js`.
2. **CSS restyle.** The `<dialog>` is the full-viewport container. A native `<dialog>`
   gets UA styles (border, padding, max-width, inset), so reset them:
   `.modal-overlay { inset:0; width:100vw; height:100vh; max-width:none;
   max-height:none; margin:0; padding:0; border:0; background:transparent;
   display:flex; ... }`. Note that `display:flex` must only apply when `[open]`, because
   a closed dialog must stay hidden. Keep `.modal-dialog` as the card.
3. **Contract tests, then the DD8 adapter.**
4. **`dialog.js` adapter**, then the pinned dispositions, then the 8 files.
5. **Demo, inventory, docs, gates, probe.**

**Sequencing:** this leg starts after leg 1 lands. Leg 1 migrates
`test_flow_dirty_confirm.py`, `test_flow_provider_dirty_confirm.py` and
`test_flow_cross_area_dirty_gate.py` onto `_nav`. Build the dispositions on top of that.

**`ui/` guards:**
- the exact IIFE header;
- the export line `  App.ui.modal = function (opts) {`;
- no app globals (`document.getElementById('main-content')` is a DOM lookup, not an app
  global; confirm `_APP_GLOBAL` agrees);
- autofocus implemented by `.focus()`, because `App.ui.button` has no `autofocus`
  option.

## Edge Cases

- **Opener removed before close** (the view re-rendered): focus goes to `#main-content`.
- **Two stacked confirms; the bottom one is closed programmatically:** the top one stays
  open, and focus restore goes to the right opener for each.
- **An `onConfirm` that throws:** the dialog has already closed, been removed and
  restored focus before the callback runs. Let the error propagate.
- **`prefers-reduced-motion`:** no transition dependence. If the card has a transition,
  use the motion tokens.
- **WebKit Tab behaviour** (F1): Tab can land on the `<dialog>` itself. The manual wrap
  must include or skip the dialog element deterministically. Test both engines.

## Files Affected

- `the_one/interfaces/web/static/js/ui/modal.js` (new)
- `the_one/interfaces/web/static/js/dialog.js` (rewritten as the adapter)
- `the_one/interfaces/web/static/css/components.css` (modal block)
- `the_one/interfaces/web/static/index.html`, `tests/test_index_asset_cache_busting.py`
- `the_one/interfaces/web/static/js/areas/admin/design-language/ui-*-section.js` (or a
  new modal section), plus the `ui-demo` usage
- `tests/browser/test_ui_modal_contract.py` (new), `tests/browser/_dialog_rule_checks.py`
  (adapter), `tests/browser/test_ui_dialog_rule.py`
- `tests/browser/test_flow_dirty_confirm.py`, `test_flow_provider_dirty_confirm.py`
  (dispositions)
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md` (if ids move to the
  `testid:` form)
- `the_one/agents.md`
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

Checked at leg design (`ddc2c22`):
- `dialog.js:55-140`: singleton, `activeElement` trigger, div overlay with
  role/aria-modal/labelledby/describedby, Cancel then Confirm buttons with their test
  ids, capture-phase keydown ✔
- `components.css:1341-1402` modal block ✔
- 13 `confirmDialog(` matches in `static/js` (12 call sites plus the definition) ✔
- 8 browser files reference confirm test ids ✔
- `_dialog_rule_checks.py`: `DialogAdapter` (:53), the `check_*` functions (:99-243) ✔
- The DD6 pinned-test line numbers come from the Architect's verification at `fe595cc`;
  re-check them by name.

Design review (Developer, 2026-10-01) — "approve with changes". Applied:
- `App.confirmDialog` keeps its single-open policy until leg 5 (avoids stacking guard
  dialogs from double-dispatch);
- unrouted closes run the cancel path exactly once;
- `onClose` fires exactly once on every path;
- the close ordering is an AC;
- a focusable card, so Escape works with focus on non-focusable text;
- an `id` option for the F1 checks;
- the backdrop-drag rule;
- CSS specifics (`[open]`-scoped `display`, inset sizing, UA resets);
- the `--scrim` token decision;
- `modal-section.js` retired into the demo;
- the Enter companion test and docstring updates;
- sequencing after leg 1.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.

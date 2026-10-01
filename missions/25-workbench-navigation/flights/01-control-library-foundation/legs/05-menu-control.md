# Leg: menu-control

**Status**: completed
**Flight**: [Control Library Foundation](../flight.md)

## Objective

Build `App.ui.menu`, a menu-button popup, following the WAI-ARIA APG menu-button
pattern. It must be keyboard-complete, safe inside native dialogs (DD8), and leak-free
when its host is wiped (DD1). It is proven in Chromium, WebKit and WebKitGTK.

## Context

- **Split out of `core-controls`** at design review. The menu is the highest-risk core
  control: its keyboard model, outside clicks, Escape inside a dialog, and cleanup.
- **Flight decisions:** DD1 (a transient popup attaches document listeners only while
  open, and every document handler checks `isConnected`), DD2 (testids), DD3, DD4, DD5
  (`.ui-menu*` classes, export idiom), DD8 (popups inside dialogs: the menu handles
  Escape itself and stops it; no portal to `body`).
- **Leg 2 outputs:**
  - `util.rovingFocus(container, itemSelector, {wrap})`: supports `wrap`, Home/End and
    ArrowUp/Down, and queries items at event time. It ignores events that already have
    `defaultPrevented`.
  - The dialog harness `tests/browser/_dialog_rule.js` with `_dialog_rule_checks.py`.
  - The cleanup instrumentation in `tests/browser/test_ui_listener_cleanup.py`.
- **Leg 4 output:** the library at 61 `/static` refs.
- **Prior art (reference only, not modified):**
  `areas/studio/knowledge-section.js::buildItemMenu` (around line 654). It uses a
  capture-phase document listener.
- **Out of scope:** typeahead (APG optional), submenus, and checkable menu items.

## Inputs

- `the_one/interfaces/web/static/js/ui/core.js` (`rovingFocus`, `uid`, `icon`, `el`),
  `ui/button.js`.
- `the_one/interfaces/web/static/css/components.css`: tokens `--surface-elevated`,
  `--border`, `--shadow-popover`, `--accent`, `--status-danger`.
- `tests/browser/_ui_engines.py`, `_a11y_resolvers.py`, `_dialog_rule.js`,
  `_dialog_rule_checks.py`, `test_ui_listener_cleanup.py`, `_probe_mount_ui.js`.
- `index.html` and `tests/test_index_asset_cache_busting.py` (61 after Leg 4).

## Outputs

- **Code.** `the_one/interfaces/web/static/js/ui/menu.js` defines `App.ui.menu`. Its
  `<script>` tag goes after `choice.js`/`feedback.js` and before `markdown.js`; the count
  goes **61 → 62**.
- **CSS.** `.ui-menu*` in `components.css` `@layer components`.
- **Tests:**
  - `tests/browser/test_ui_menu_contract.py` (`shared` lane, both engines);
  - menu cases added to `test_ui_listener_cleanup.py`;
  - a menu-inside-dialog test using the Leg 2 harness;
  - a menu added to `_probe_mount_ui.js`.
- **Docs.** `the_one/agents.md` "Control library": the `menu` API and its keyboard
  contract.
- **Flight log.** The leg entry, including the probe results.

## Acceptance Criteria

- [x] **AC1 — API.** `App.ui.menu(opts)` returns a controller
  `{el, trigger, popup, open(focus), close(restoreFocus), isOpen(), destroy()}`.

  Options:
  - `trigger`: options for `App.ui.button`. `iconOnly` + `ariaLabel` is allowed.
    `trigger.testid` goes on the trigger button.
  - `items`: `{label, onSelect, icon, danger, disabled, testid}`. Each item's `testid`
    goes on its menuitem.
  - `align`: `'start'|'end'`. Any other value throws.
  - `testid`: goes on the popup root.

  It throws on an empty `items`, or on an item without `label` or `onSelect`.
- [x] **AC2 — Markup.**
  - `el` is a `<div class="ui-menu-wrap">` with `position: relative`. It contains the
    trigger, and the popup `<div role="menu" class="ui-menu" id=<uid> hidden>` as a
    **DOM descendant**, with no portal.
  - The trigger has `aria-haspopup="menu"`, `aria-expanded` (`"false"` or `"true"`) and
    `aria-controls=<popup id>`.
  - The popup is labelled by the trigger (`aria-labelledby`), or by `aria-label` for
    icon-only triggers.
  - Items are `<button type="button" role="menuitem" tabindex="-1">` with a label
    `<span>` and an optional `util.icon`.
  - Disabled items carry `aria-disabled="true"`, not the `disabled` attribute, so they
    stay readable.
  - Danger items add `.ui-menu-item-danger`, which uses `--status-danger`, an already
    gated pair.
- [x] **AC3 — Opening.**
  - Click, Enter, Space or ArrowDown on the trigger opens the menu and focuses the
    **first enabled** item. This applies to mouse opens too, so focus is always inside
    the popup when it is open.
  - ArrowUp opens it and focuses the **last** enabled item.
  - `aria-expanded` becomes `"true"`.
- [x] **AC4 — Navigation.** Inside the popup:
  - ArrowDown and ArrowUp move between enabled items and **wrap**
    (`rovingFocus(popup, '[role=menuitem]:not([aria-disabled="true"])', {wrap: true})`);
  - Home and End go to the first and last enabled items;
  - items stay `tabindex="-1"`, with `rovingFocus` managing focus only.
- [x] **AC5 — Activation.**
  - Enter, Space or click on an enabled item closes the menu, returns focus to the
    trigger, **then** calls `onSelect(item)`.
  - If `onSelect` throws, the menu is already closed and focus already restored; the
    error propagates and is not swallowed.
  - Enter, Space or click on an `aria-disabled` item does nothing, and the menu stays
    open.
- [x] **AC6 — Escape and Tab.** These are handled by a `keydown` listener on **`el`**
  (the wrapper, which contains both trigger and popup), so they work wherever focus sits
  in the control.
  - **Escape while open:** `preventDefault()` + `stopPropagation()`, close, focus the
    trigger. Escape while closed is not handled, so it reaches the dialog and other
    ancestors.
  - **Tab or Shift+Tab while open:** close and call `trigger.focus()`, **without**
    `preventDefault`, so default Tab navigation continues from the trigger.
  - **`focusout` from `el`:** when focus moves outside `el`, by any route including
    programmatic focus, the menu closes without restoring focus.
- [x] **AC7 — Outside click and cleanup.**
  - While open, one capture-phase `pointerdown` listener on `document` closes the menu
    when the event target is outside `el`. It does not restore focus.
  - The listener is added on open and removed on close.
  - It first checks `el.isConnected`. If `el` is gone, the listener removes itself and
    does nothing else.
  - A closed menu has **zero** document listeners.
  - One open menu at a time: a module-scope reference to the open menu is closed when
    another opens. Closing a menu whose `el` is detached must not throw.
- [x] **AC8 — Visible focus and styling.**
  - Each menu item `:focus-visible` shows the standard `--accent` ring (2px; inset
    allowed).
  - The popup uses `--surface-elevated`, a `--border` hairline, `--radius-sm` and
    `--shadow-popover`. That is one of the two sanctioned shadows, so none is added.
  - Item text is `--fg`, or `--status-danger` for danger items.
  - Item hover and focus background is `--surface` (or another existing token), and the
    text pair over it is gated by an existing ladder test or a new gate.
  - `align: 'end'` right-aligns the popup to the trigger.
- [x] **AC9 — Contract tests** (`test_ui_menu_contract.py`, both engines, none skipped)
  prove, each step by step with real `keyboard.press` and `click`:
  - AC3, including a **mouse open** that lands focus on the first item;
  - AC4, including wrap and Home/End;
  - AC5, including the disabled-item no-op and the throwing `onSelect`;
  - AC6: Escape returns focus; Tab closes and focus moves past the trigger; `focusout`
    closes;
  - AC7: an outside `page.mouse.click` closes the menu; opening a second menu closes the
    first;
  - the testid placement;
  - `assert_controls_labelled_and_described` over a mounted open menu and a closed
    menu. `aria-controls` with `aria-expanded="false"` is exempt.
  - Focus-visible on items is asserted only after a **keyboard** open, never after a
    click open.
- [x] **AC10 — Inside a dialog** (DD8; both engines; the Leg 2 `_dialog_rule.js`
  harness, with the dialog opened by a real click):
  - (a) Menu opened **by keyboard**, then Escape: the menu closes, the dialog layer
    count is unchanged, and focus is on the trigger. A second Escape closes the dialog.
  - (b) Menu opened **by mouse click**, then Escape: same result.
  - (c) An outside click inside the dialog closes the menu; the dialog stays open.
- [x] **AC11 — Cleanup** (`test_ui_listener_cleanup.py`, both engines):
  - (a) A closed menu has zero outstanding document-level listeners.
  - (b) Open the menu, wipe its host with `textContent = ''` without `destroy()`, and
    dispatch one `pointerdown` on `document`. There are then zero outstanding listeners,
    and no handler touched the detached nodes.
  - (c) The existing negative control still reports.
- [x] **AC12 — WebKitGTK.** `_probe_mount_ui.js` mounts a menu, and a second, opened
  menu.
  - The probe runs against a dev instance (8485, scratch data dir, dev mode;
    `make restart` after `index.html` changes) with `--root-selector '#ui-probe-root'`,
    in dark and light.
  - Both runs are `ok: true`.
  - The flight log records the engine version and control count.
- [x] **AC13 — Docs and gates.**
  - `agents.md` documents `menu`: API, keyboard contract, the outside-click and cleanup
    rule, and dialog safety.
  - Gates:
    - `make lint`;
    - `make test-unit`;
    - every `tests/browser/test_ui_*.py` plus `test_deep_violet_computed_styles.py`,
      with `-m browser -rA` and no skips;
    - `--lane shared`.

## Verification Steps

- AC1–AC11:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_menu_contract.py tests/browser/test_ui_listener_cleanup.py tests/browser/test_ui_dialog_rule.py -x -rA`.
  Every test shows passing `[chromium]` and `[webkit]` params.
- AC12: the flight log.
- AC13: the commands listed, and a read of the docs.

## Implementation Guidance

1. **`menu.js` structure first.** Build the trigger with `App.ui.button` and append the
   `aria-*` attributes. Build the popup and items with `util.el`. Add the `<script>`
   tag and the count bump in the same step.
2. **Open and close state machine.** Set up one private `open`/`close` pair, the
   module-scope open-menu reference, and the document listener attach/detach.
3. **Keyboard.**
   - Put the trigger keydown on the trigger.
   - Put Escape, Tab and `focusout` on `el`.
   - Bind `rovingFocus` on the popup. It runs on the popup's keydown and checks
     `defaultPrevented`, so make sure the `el`-level Escape handler doesn't
     `preventDefault` arrow keys.
4. **CSS.**
5. **Contract, dialog and cleanup tests.**
6. **Probe**, **docs**, **gates**.

## Edge Cases

- **All items disabled.** Opening the menu focuses the popup itself (`tabindex="-1"` on
  the popup) so Escape still works. Test it.
- **Trigger disabled.** The menu does not open.
- **A menu inside a scroll container near the bottom edge.** No flipping logic in this
  leg: the popup opens downward. Record it as a known limitation in the docs; a later
  flight may add flipping where the workbench needs it.
- **`destroy()` while open.** It closes the menu, removes the document listener, and
  leaves no stale module-scope reference.

## Files Affected

- `the_one/interfaces/web/static/js/ui/menu.js` (new)
- `the_one/interfaces/web/static/css/components.css`
- `the_one/interfaces/web/static/index.html`, `tests/test_index_asset_cache_busting.py`
- `tests/browser/test_ui_menu_contract.py` (new), `test_ui_listener_cleanup.py`,
  `test_ui_dialog_rule.py` (or the menu contract file for AC10), `_probe_mount_ui.js`
- `the_one/agents.md`
- `missions/25-workbench-navigation/flights/01-control-library-foundation/flight-log.md`

## Citation Audit

Checked at leg design (2026-09-30):
- `ui/core.js:96` `rovingFocus` supports `wrap`, Home/End and ArrowUp/Down, ignores
  `defaultPrevented`, and queries items at event time ✔ (Leg 4 design review)
- `knowledge-section.js::buildItemMenu` uses a capture-phase document listener ✔ (Leg 4
  design review)
- `--shadow-popover` is one of the two sanctioned shadows (`agents.md` Design language
  v3) ✔

The design came from the `core-controls` design review (Developer, 2026-09-30). That
review's three high issues are resolved here:
- Escape is bound on the wrapper, and `open()` always focuses the first item;
- Tab behaviour is specified, with no `preventDefault`;
- `focusout` closes the menu.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.

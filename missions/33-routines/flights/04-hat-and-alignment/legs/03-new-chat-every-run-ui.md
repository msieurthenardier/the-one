# Leg: new-chat-every-run-ui

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Rebuild the agent editor's Routines tab list on the layout the operator chose
at the HAT (mockup **A, "compact list, actions in a menu"**,
https://claude.ai/artifact/ADMrdaR59SSTHgWdV6CbVe), drop every client piece of
the routine target (the form's "Run in" group, the chat chooser, the row's
target line, the approval queue's "Runs in" field), link each run in history
to the chat it created, show each run's stored reason, and keep the form's
Save disabled until an edit changes something. All dead client code, CSS,
testids and tests for targets are removed (operator: "be sure the code and
tests get cleaned up").

## Context

- **Builds on leg 02** (`new-chat-every-run-backend`): routines have no
  target; a routine view has no `target`; `GET .../routines/{id}/runs` returns
  `session_id` and `chat_exists` per run and no `new_chat`. Leg 02 lands
  first; this leg's Developer reads its flight-log entry.
- **Operator decisions (flight log):**
  - F-B5-2: the list and its buttons "don't look right, and are too
    crowded"; layout A chosen over B ("we already have a left menu panel")
    and C.
  - F-B5-1: "the save button should be disabled for a routine if it hasnt
    changed, and only be enabled if changes are made."
  - Run history links to each run's chat ("Link to the chat").
- **C14 (DD4)**: today `routines-describe.js::outcomeStatus` shows the stored
  reason only for failed, skipped and missed runs, and repeats the verb
  ("Skipped {time}: Skipped 3 times…"). The chosen mockup shows the reason
  on the run's line ("Skipped: the previous run was still going"). This leg
  shows the stored reason for every outcome that has one, once, without a
  doubled verb. The operator confirms the wording when the walk resumes.

### Design decisions (leg-level)

**L3-DD1. The list (mockup A).**
- A bordered list with a caption row ("On", "Routine", "Next run", "Last
  run"; visual captions, small uppercase `--fg-tertiary`, the DD13 eyebrow
  style) and one row per routine on the same grid columns:
  1. the enable switch (`App.ui.toggle`, as the tab uses today, named
     "Enable {name}"); a Done routine shows no switch;
  2. the routine: the name as a disclosure button (`aria-expanded`,
     `aria-controls` the details region) with a chevron, then the
     "Made by the agent" chip and the flag (`App.ui.noteFlag
     {subject:'routine'}`) when they apply; under it the server's
     `schedule_text`;
  3. the next run ("Fri 9:00 AM", "Today 8:30 PM"), or "Off", or "Done";
  4. the last run: a status dot plus "Ran Thu 9:00 AM" / "Failed Oct 23" /
     "Not run yet" / "Running…" (`App.ui.status` where it fits);
  5. a "⋯" button (`App.ui.button`, icon only, `aria-label` "Actions for
     {name}") opening an `App.ui.menu` with **Run now**, **Edit** and
     **Delete** (`danger: true`, last; the menu has no separator and none is
     added). Run now is disabled while the routine is running and for a
     Done routine (editing its schedule makes it runnable again).
- **The menu library change.** `App.ui.menu` applies `disabled` only at
  build time (`ui/menu.js`), and rebuilding the menu on the 3 s refetch
  would close an open menu. Add a small handle to set an item's disabled
  state after construction (e.g. `menu.setItemDisabled(index|testid,
  bool)`), with its `docs/ui-control-inventory.md` row note and contract
  tests in `tests/browser/test_ui_menu*.py` (Chromium and WebKit, run with
  `THE_ONE_REQUIRE_WEBKIT=1`).
- **No clipping.** The menu popup is absolutely positioned and opens
  downward; the bordered list must not clip it (`overflow: visible` on the
  list and rows; round the corners without `overflow: hidden`). A browser
  test opens the last row's menu and asserts its Delete item is visible and
  clickable.
- **Delete** from the menu asks through `App.confirmDialog` with `title`
  "Delete {name}?", a `message` saying its run history goes with it,
  `confirmText: 'Delete'`, `cancelText`, `opener` (the row's "⋯") and
  `onConfirm`. If `App.confirmDialog` has no danger styling for its confirm
  button, add an option for it (a library change: catalogue note and
  contract test, as above). Cancel or Escape returns focus to the "⋯"
  button (the dialog does this). On confirm the dialog restores focus to the
  opener before the callback runs; the delete then reloads, and **after the
  post-delete `load()`** focus moves to the next row's disclosure, else the
  previous, else New routine (as `onDelete` orders it today). This replaces
  the armed `App.ui.confirm` Delete, so every test that arms and confirms
  `routine-delete` changes.
- **Expanded row** (one or many may be open): a details region with
  "Prompt" (the text, `textContent`, `white-space: pre-wrap`) and "Recent
  runs". The render model already keeps `views[id]` and patches nodes in
  place, so an open disclosure survives the 3 s refetch; the recent runs
  re-fetch when the row's last run changes while it is open (as the History
  does today via `loadHistory` when loaded and open), and on
  `App.time.onChange`. One list, one state: it loads the first page with
  `limit=5`; "Show more runs" appends the next 20 through the existing
  cursor. Each run is one line of When, How (Scheduled, Run now, Caught
  up), Outcome with its reason, and **Open chat** (a link to
  `#chats/{session_id}` built with `App.router.href`) when `chat_exists`,
  "Chat deleted" muted when the run had a chat that is gone, nothing for a
  run with no chat (skipped, missed).
- Header: the intro line becomes "A routine sends a prompt to this agent on
  a schedule. Each run starts a new chat." with **New routine** (primary)
  on the same line, right-aligned. The empty state stays text only
  ("No routines yet."; F-A2-1).
- Built from `App.ui` controls and the studio stylesheet's tokens; no new
  library control unless one is genuinely missing (then it needs its
  catalogue row and contract tests, CLAUDE.md "Control library"). At 1024 px
  (the supported minimum) the grid must not overflow: the routine column
  shrinks and wraps; the menu stays reachable.

**L3-DD2. Outcome wording (C14).** `outcomeStatus` returns a short label
("Ran", "Failed", "Skipped", "Missed", "Stopped", "Interrupted", "Running")
and the reason separately; the row's last-run cell shows the label and time,
the details line shows the label and reason, never the verb twice (the
server's reason text is not edited by this leg; if a reason starts with the
same verb, the label is dropped for that line instead). Reasons are
`textContent`.

**L3-DD3. The form.**
- Removed: the "Run in" radio group, the chat line, the chat chooser and its
  modal, `targetError`, `TARGET_OPTIONS`, `targetBody`, the model's
  `targetKind`/`chatId`/`chatLabel`, the 'Pick a chat.' precheck and the
  `target` error mapping. The form never sends `target`.
- **Save in edit mode is disabled until the form differs from the stored
  routine** (`formToBody`'s diff is non-empty), and re-disables if the
  operator reverts the change. A flagged routine still sends `prompt` on
  Save, and Save is enabled for it (saving is the review that clears the
  flag, F2 DD7). Create mode is unchanged. A disabled Save uses the library's
  disabled button tokens.

**L3-DD4. Approval queue.** `self-config-routines-queue.js` loses
`FIELD_LABELS.target`, the `target` entries in `FIELD_ORDER` /
`PRIMARY_COLUMN`, `targetWords`, the `case 'target'` and the
`['schedule','target']` blocks. Old proposals no longer carry a target after
v49 (leg 02).

**L3-DD5. Testids.**
- Retired (registry "Retired testids" table **and** `RETIRED_SELECTORS` /
  `RETIRED_EXACT` in `tests/test_nav_helper.py`): `routine-chat-chooser`,
  `routine-chat-chooser-close`, `routine-chat-option`, `routine-chat-search`,
  `routine-form-chat`, `routine-form-target`, `routine-form-target-error`,
  `routine-target-picker`, `routine-target`.
- Also retired (their element goes or its meaning changes):
  `routine-history`, `routine-history-list`, `routine-history-empty`,
  `routine-history-more`, `routine-run` (a history entry that showed "New
  chat"), and `routine-done-hint` if the Done state now lives in the Next
  run cell.
- Kept with the same meaning (check each against the registry rows
  ~:496-532 and say so in the flight log): `routine-row`, `routine-name`
  (the name text, now inside the disclosure button), `routine-schedule`,
  `routine-next`, `routine-last`, `routine-origin`, the enable toggle's id,
  `routine-error`, and `routine-run-now`, `routine-edit`, `routine-delete`
  (now on the menu items).
- New, registered in `docs/ui-testid-registry.md`: `routine-actions` (the
  "⋯" button), `routine-details-toggle` (the disclosure), `routine-details`
  (the region, with a stable `id` for `aria-controls`),
  `routine-details-prompt`, `routine-recent-runs` (the list),
  `routine-recent-run` (a line), `routine-recent-run-chat` (its Open chat
  link; not `routine-run-*`, which `routine-run-now` would collide with
  under prefix selectors), `routine-recent-runs-more`. Record the final
  list in the flight log.

## Acceptance Criteria

- [ ] AC1. The Routines tab renders layout A: caption row, one grid row per
      routine with switch, name and schedule, next run, last run and the
      "⋯" menu (Run now, Edit, Delete); no "Run in"/target text anywhere.
- [ ] AC2. A row's disclosure opens a details region with the prompt and up
      to five recent runs; each run with an existing chat has an Open chat
      link that navigates to that chat; a deleted chat reads "Chat deleted";
      "Show all runs" pages older runs; open rows stay open across the
      running-state refetch.
- [ ] AC3. Delete from the menu confirms through a dialog, and focus follows
      L3-DD1; Run now is disabled while running and for a Done routine.
- [ ] AC4. Outcome lines show the stored reason for every outcome that has
      one, with no doubled verb (L3-DD2).
- [ ] AC5. The form has no target controls and never sends `target`; in edit
      mode Save is disabled until a field changes and re-disables on revert,
      except for a flagged routine.
- [ ] AC6. The approval queue shows no "Runs in" field.
- [ ] AC7. Retired testids are in the registry's retired table and the
      nav-helper lists; new testids are registered;
      `tests/test_nav_helper.py`, the registry tests and
      `tests/test_area_module_size.py` pass (split a module if it passes its
      limit; `routines-tab.js` is 549 lines today).
- [ ] AC8. **Clean-up grep** (quoted in the flight log):
      `grep -rnE "describeTarget|targetBody|targetKind|chatLabel|TARGET_OPTIONS|targetError|targetWords|routine-chat-|routine-form-target|routine-form-chat|routine-target|target_kind|target_session_id|Runs in|Run in|Its own chat|New chat each run|Chat gone" the_one/interfaces/web/static/ tests/browser/ scripts/ docs/ the_one/agents.md`
      has hits only in the registry's retired table, the nav helper's
      retired lists, and `tests/test_nav_helper.py`.
- [ ] AC9. Accessibility: the disclosure, menu, dialog and links are
      keyboard-operable with visible focus; the switch and "⋯" have
      accessible names including the routine's name; text contrast meets AA;
      no information by colour alone (the status dot always has a word).
      The Accessibility Reviewer (crew file) confirms.
- [ ] AC10. `THE_ONE_TEST_NETNS=1 make test-unit` passes (15 skipped); the
      static guards (`test_ui_guards.py`, `test_token_definitions.py`,
      `test_design_tokens_a11y.py`, `test_ui_ownership.py`,
      `test_ui_emitted_classes.py`, `test_ui_control_inventory.py`); lanes
      `agent-routines`, `agent-tabs`, `chats-transcript` (the routine-marker
      test) and, for the library change, `contracts-overlay` with
      `THE_ONE_REQUIRE_WEBKIT=1` pass.

## Verification Steps

- AC1-AC6: browser tests in `tests/browser/test_flow_agent_routines*.py`
  (rewritten for layout A; the target and chooser tests deleted with their
  code; `test_form_model_rules` loses its target cases; a new test for Save's
  disabled state including revert and the flagged case; a test for Open chat
  and "Chat deleted").
- AC7-AC10: the named tests, the grep, the lanes.

## Implementation Notes

- **Build on the working tree**, not `7dd144d5`: `routines-tab.js` carries
  the F-A2-1 empty-state fix, `routines-custom-recurrence.js` the
  `COUNT_DEFAULT` 7 fix, and the routine browser tests, the registry and
  `tests/test_nav_helper.py` are already modified. Line numbers in the
  Citation Audit are approximate.
- **Plan the module split now:** `routines-tab.js` is 549 lines and the area
  limit is 800 (`tests/test_area_module_size.py`); put the row details,
  recent runs and menu wiring in a new module (e.g.
  `areas/studio/routines-row-details.js`, script tag in `static/index.html`).
- **Save disabled until changed** reuses `formToBody`'s diff (the value
  model the knowledge and connector editors use), so reverting makes the
  form clean with no new mechanism.
- Scrub the `routines-tab.js` header comment (:2-3, "schedule, target, …")
  and the `renderRoutinesTab` JSDoc. In the clean-up grep, `event.target`
  in `routines-custom-recurrence.js` and other DOM uses are not targets.
- Unchanged by design (verified at review): the chat drawer's Routines group
  (`areas/chat/agent-drawer-parts.js`) and the transcript's routine marker
  read no target.

## Edge Cases

- A routine with a very long name or schedule sentence at 1024 px: wraps, no
  horizontal scroll.
- A run whose chat was purged by retention: "Chat deleted".
- The menu opened on the last row near the viewport bottom: the library
  menu's own placement.
- A routine deleted by the agent while its row is expanded: the refetch
  removes the row and focus is not lost to `body` if it was inside it (move
  it to New routine).
- Run now from the menu: the menu closes, the row's last run shows
  "Running…", the polite live line announces as today.

## Files Affected

Shared with leg 02: `the_one/agents.md` (this leg edits the form, tab and
queue bullets of "Routines (M33)"), the flight log.

- `static/js/areas/studio/routines-tab.js` (and a split module if needed),
  `routines-form.js`, `routines-form-model.js`, `routines-describe.js`,
  `self-config-routines-queue.js`; `static/index.html` if a module is added;
  `static/css/studio.css` (`.routine-form-chat`,
  `.routine-chat-chooser-body`, `.routine-actions` and the row styles go;
  the layout A styles come in).
- `docs/ui-testid-registry.md`, `tests/test_nav_helper.py`.
- `static/js/ui/menu.js` (settable disabled state) and, if needed,
  `static/js/ui/dialog.js` (danger confirm), with
  `docs/ui-control-inventory.md` and `tests/browser/test_ui_menu*.py` /
  the dialog's contract test.
- `tests/browser/test_flow_agent_routines.py`,
  `test_flow_agent_routines_form.py`,
  `test_flow_agent_routines_self_config.py`,
  `test_flow_chat_routine_marker.py`, `tests/browser/seeders.py`
  (`seed_agent_routine` loses `target_kind`).
- `scripts/ui_capture.py` (routine bodies and the raw INSERT lose targets).
- `the_one/agents.md` "Routines (M33)" form, tab and queue bullets; CLAUDE.md
  Routines paragraph's tab sentence if it names the old row.

## Citation Audit

From the consumer inventory at `7dd144d5` plus the HAT fixes:
`routines-form.js` `TARGET_OPTIONS` (:24-28), target block (:322-338),
chooser (:364-440); `routines-form-model.js` (:12-13, :199, :212-257,
:320-322, :352); `routines-describe.js::describeTarget` (:20-28, :98),
`outcomeStatus`; `routines-tab.js` row actions (:192-210), `targetEl`
(:172-182, :238), empty state (F-A2-1); `self-config-routines-queue.js`
(:16-22, :42-68, :129-142); `studio.css` (:1108, :1142, :1154); testid
registry rows (:498-533). The Developer re-reads each before editing.

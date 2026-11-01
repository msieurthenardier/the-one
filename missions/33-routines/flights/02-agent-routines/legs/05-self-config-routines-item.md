# Leg: self-config-routines-item

**Status**: completed
**Flight**: [Agents Schedule Their Own Routines](../flight.md)

## Objective

Make the operator's side visible and controllable. This leg delivers:
- **The Self-configuration tab's two items.** "Agent prompt" is today's
  controls, relabelled. "Routines" is new: its two switches, its pending
  proposals with Approve and Dismiss (and the stale path), and the agent's
  change history.
- **Origin and flag on routines.** The Routines tab shows "Made by the agent"
  and the "Check this" flag on a routine, and the drawer's Routines group
  shows the flag.
- **`App.ui.noteFlag`'s `subject` option.**
- **The `agent-routines` browser lane.**

## Context

- **Flight DD5** (the upgrade mapping, the labels, the routes, the call-time
  switch, which needs no UI) and **DD11** (the UI).
- **The routes come from leg 2:**
  - `GET` and `PUT /api/agents/{name}/self-configuration/routines` →
    `{enabled, requires_approval, pending_count}`;
  - `GET .../routines/proposals?status=&limit=&before=` →
    `{"proposals":[...]}`, each a `RoutineProposal.model_dump()`;
  - `GET .../proposals/pending-count` → `{count}`;
  - `POST .../{id}/approve?override=`. Its 409s are `{"error":"stale",
    "current_value","proposed_value","base_value"}` and `{"error":"gone"}`,
    or a plain `detail` for dismissed or superseded. A 422 means a schedule
    that is invalid now;
  - `POST .../{id}/dismiss`.

  Read the leg 2 entry in the flight log for the landed shapes.
- **The routine view** carries `created_by`, `untrusted` and
  `untrusted_sources` (leg 2).
- **Batch B** is this one leg: a code Reviewer and an Accessibility Reviewer,
  then a commit after the quiet-host `--parallel 3` gate, which also sets the
  `agent-routines` budget.

## Inputs

**The tab assembler,
`static/js/areas/studio/self-configuration-tab.js` (152 lines).** It builds
`ctx`, then four modules in order: `selfConfigStatus` (`self-config-status.js`,
283 lines), `selfConfigRevisions` (342), `selfConfigHistory` (367) and
`selfConfigExternal` (438). It then calls `ctx.refetchStatus({})` and
`ctx.refetchRevisions()`. Their script tags are at `index.html:107-109`.

**`self-config-status.js` today has:**
- `App.ui.section({title:'Self-configuration', titleTag:'h3'})`, holding the
  description, a status `self-configuration-status`, an error
  `self-configuration-error` and an `App.ui.toggle` labelled "Enable
  self-configuration" (`self-configuration-toggle-btn`);
- a second `App.ui.section({title:'Approval mode', titleTag:'h3'})`, holding
  its description, `approval-mode-status`, `approval-mode-error` and the
  toggle "Require approval for self-revisions" (`approval-mode-toggle-btn`).

**`self-config-revisions.js`** is the pattern for a pending queue: a section,
a count status, per-item `App.ui.codeBlock` values, Approve and Dismiss
`App.ui.button`s, a stale `App.ui.banner` with current and proposed
`codeBlock`s and an override button, and an `App.ui.emptyState`.

**The Routines tab** (`static/js/areas/studio/routines-tab.js`) builds rows
(`routine-row`, with `routine-name`, `routine-schedule`, `routine-target`,
`routine-next`, ...). The describer helpers are in `routines-describe.js`
(`App.studio.routinesDescribe`). The edit form is `routines-form.js` with
`routines-form-model.js` (`formToBody`/`bodyToFormState`).

**The drawer's Routines group** is in
`static/js/areas/chat/agent-drawer-parts.js`. Its notes flag uses
`App.ui.noteFlag` at about `:82` (`chat-drawer-notes-flag`).

**`App.ui.noteFlag`** is at `static/js/ui/feedback.js:191-195`. Its catalogue
row is in `docs/ui-control-inventory.md`, and its contract tests are in
`tests/browser/test_ui_*`.

**The browser tests:**
- `tests/browser/_self_config.py` (`ENABLE_SWITCH`, `APPROVAL_SWITCH`);
- `test_studio_self_configuration_{tab,queue,history,dirty,external}.py`;
- `test_flow_agent_routines.py` and `test_flow_agent_routines_form.py`.

**The pins** found at planning:
- the status texts "disabled", "enabled" and "Approval mode is on" (tab
  `:46/:64`, dirty `:94`, queue `:215/:220`);
- `history.py:152`'s single `.self-configuration-subheading` match;
- `test_flow_agent_tabs.py:198` (Self-configuration is the last tab).

**`scripts/run-tests.sh`:**
- `agent_tabs_pat` (`:222-223`) holds `test_flow_agent_routines*` and
  `test_studio_self_configuration_*`;
- the budget table holds `agent-tabs` at 540;
- `tests/test_run_tests_lanes.py` pins the lane list and the budget table.

## Outputs

### The two items

**"Agent prompt"** is today's two sections, retitled and relabelled. The
mechanism is unchanged.
- The first section's title becomes "Agent prompt". Its description becomes
  one sentence: "Let this agent read its configuration and rewrite its own
  description and system prompt."
- The enable switch's label becomes "Let this agent edit its description and
  system prompt". Its testid `self-configuration-toggle-btn` is kept.
- The second section's title becomes "Prompt approval". The switch label
  becomes "Require approval for prompt edits". Its testid
  `approval-mode-toggle-btn` is kept.
- **The status strings keep their pinned words.** "disabled" and "enabled"
  stay in `self-configuration-status`, and "Approval mode is on" and "off"
  stay in `approval-mode-status`, so the existing tests change only in the
  label constants.
- `_self_config.py`'s `ENABLE_SWITCH` and `APPROVAL_SWITCH` take the new
  labels.
- The revisions queue, history and external-credentials modules stay where
  they are, after these, as Agent prompt's.

**"Routines"**, a new module
`static/js/areas/studio/self-config-routines.js` (`App.studio.selfConfigRoutines.build(ctx)`).
The assembler builds it after `selfConfigExternal` and calls its
`ctx.refetchRoutines()`. It is one `App.ui.section({title:'Routines',
titleTag:'h3'})` holding:
- **A description**: "Let this agent list, schedule, change and cancel its
  own routines, including ones you made. With approval on, each change waits
  for you here."
- **The enable switch**: `App.ui.toggle`, labelled "Let this agent manage its
  routines", testid `self-config-routines-toggle`.
- **The approval switch**: labelled "Require approval for routine changes",
  testid `self-config-routines-approval-toggle`.
- **Status lines**: `self-config-routines-status` ("Off: this agent has no
  routine tools.", "On: this agent can manage its routines.") and
  `self-config-routines-approval-status` ("Approval is on: changes wait for
  you." / "Approval is off: changes apply at once."). Plus one
  `self-config-routines-error`.
- **Both switches** post immediately (`PUT`), disable while in flight, and
  restore on error with the error line shown. Turning Routines off says
  "Pending changes were withdrawn." when `pending_count` was above 0.
- **"Waiting for approval"**, a subheading (a class other than
  `.self-configuration-subheading`, so `history.py:152` stays single), with
  the list `self-config-routine-proposals` and a count status
  `self-config-routine-pending-count`. Each item (`self-config-routine-proposal`,
  with `data-id`) shows:
  - the action word (Create, Change, Cancel) and the routine name, from the
    payload, or `routine_name` for a cancel;
  - for a create, the schedule in words, the target in words and the prompt
    in an `App.ui.codeBlock`;
  - for a change, only the changed fields, each as "before → after" in
    words, with the prompt as two `codeBlock`s ("Now", "Proposed");
  - the flag (`App.ui.noteFlag({subject:'routine', sources})`) when
    `untrusted`;
  - the time;
  - Approve (`self-config-routine-approve`) and Dismiss
    (`self-config-routine-dismiss`).

  Describe a schedule and a target with `App.studio.routinesDescribe`, so the
  wording matches the Routines tab. An empty list is an `App.ui.emptyState`
  "Nothing waiting."
- **The stale path.** A 409 `stale` shows an `App.ui.banner` (warning) in the
  item: "This routine changed since the agent asked." It shows the current
  and proposed values for the touched fields, and "Approve anyway"
  (`self-config-routine-approve-override`, posting `?override=true`).
- **Other approval outcomes:**
  - a 409 `gone` removes the item, saying "The routine is gone; the change
    was withdrawn.";
  - a 422 shows its sentence in the item's error line.
- **Focus.** It moves as the revisions queue does: after Approve or Dismiss,
  to the next item's Approve, or to the count status when the list empties.
  One polite live line, `self-config-routines-live`, announces "Approved
  {action} of {name}" or "Dismissed …".
- **"Changes by the agent"**, a subheading with a list
  `self-config-routine-history` of resolved proposals, newest first, 20 per
  page with "Show older" (`before`). Each row gives the action, the name,
  the status (Applied, Dismissed, Withdrawn for superseded), the time and
  the flag. It is read-only.
- **Refetch.** Pending and history are refetched after every action, on
  `setAgent`, and on a **new** `activate` hook:
  - The tab handle today is `{setAgent, destroy, deactivate}` only.
  - Add `activate` to it, which calls `ctx.refetchRoutines()`, and
    `ctx.refetchRevisions()` too, closing the same gap for the revisions
    queue.
  - Add a `tab === 'self-configuration'` branch in `setActiveTab`
    (`agent-editor-controller.js`, near `activateRoutines` `:384`/`:412`).
  - A refresh patches in place without flicker, as Flight 1's routines rows
    do.

### Origin and flag elsewhere

**The Routines tab** (`routines-tab.js`, `routines-describe.js`): a row with
`created_by === 'agent'` shows a small "Made by the agent" text
(`routine-origin`), and a flagged row shows
`App.ui.noteFlag({subject:'routine', sources})` (`routine-flag`). Both are
patched in place on every poll.

**The edit form** (`routines-form-model.js` `formToBody`) always includes
`prompt` when the routine being edited is flagged (flight DD7: saving the
form is the review), even when the prompt is unchanged. A unit or `evaluate`
test pins it.

**The drawer** (`agent-drawer-parts.js` Routines group): a flagged routine's
row shows the flag (`chat-drawer-routine-flag`), in the same place the notes
flag sits. It stays read-only, with no origin text there.

### `App.ui.noteFlag` `subject`

- `App.ui.noteFlag({sources, subject})`. `subject` is `'note'` (the default,
  today's text unchanged) or `'routine'` ("Check this routine: it was
  written after content that didn't come from you ({sources}). It may have
  been planted."). Any other value throws.
- The catalogue row in `docs/ui-control-inventory.md` lists the option.
- The contract test for `noteFlag` gains the `routine` subject and the throw,
  in both engines.

### Lane

- **A new lane, `agent-routines`.** Its pattern `agent_routines_pat` holds
  `test_flow_agent_routines*`, which is removed from `agent_tabs_pat`.
- The new test file is
  `tests/browser/test_flow_agent_routines_self_config.py` (outside
  `test_studio_self_configuration_*`).
- It gets a provisional budget of 300 s in the table.
- `tests/test_run_tests_lanes.py` lists 17 lanes, still disjoint and still
  covering the whole suite.
- CLAUDE.md's lane list and table gain the lane, with its budget marked
  provisional until the Batch B gate.
- `--plan` shows it.

### Tests

**`test_flow_agent_routines_self_config.py`** covers:
- both items render in order;
- the Routines switches post and persist across a reload;
- the approval default is on for a new agent;
- off, with pending proposals, says they were withdrawn;
- approve and dismiss of seeded pending proposals (create, change, cancel),
  with the resulting routine on the Routines tab;
- the stale banner, then Approve anyway;
- the gone path;
- the 422 line;
- focus after approve;
- history paging;
- the flag on a proposal.

**Seeding.** There is no REST route that creates a proposal, and no new
test seam is added.
- Add `seeders.seed_routine_proposal(data_dir, agent, action, payload, *,
  base=None, status="pending", untrusted=False, sources=None,
  routine_id=None, routine_name, created_at, resolved_at=None)` and
  `seeders.seed_agent_routine(data_dir, ...)`. The second makes an
  agent-made or flagged routine, since REST cannot set `created_by='agent'`
  or the flag.
- Both use sync `sqlite3` INSERTs into `<data_dir>/the-one.db` through the
  `app_with_data_dir` fixture, the existing `seed_note` pattern
  (`seeders.py:442`). Timestamps are fixed ISO strings passed by the test.
- **Stale:** seed an update proposal with `base`, then PUT the routine
  through REST so it drifts.
- **Gone:** seed the proposal, then delete the routine row **directly with
  sqlite**. A REST delete supersedes pending proposals (leg 2), so it cannot
  produce "gone". The proposal's `routine_id` becomes NULL through
  `ON DELETE SET NULL`, which is the gone state.
- **One end-to-end test** goes through the real chain:
  - `seed_mock_provider` with `config.response.tool_calls` set to a
    `schedule_routine` call;
  - `seed_mock_agent(..., max_iterations=1)`;
  - Routines on with approval on, through the new `PUT`;
  - a chat message; then the proposal appears in the queue.

  The pattern is `test_flow_agent_notes.py:424-442`.

**`test_flow_agent_routines.py`** gains origin and flag rows.

**The drawer test** for the flag goes in its existing file,
`tests/browser/test_flow_chat_drawer.py`, which runs in the **`chats`** lane.

**`test_studio_self_configuration_*`** and `test_flow_agent_tabs.py` pass
with only the label-constant updates.

### Docs

- `docs/ui-testid-registry.md` gains every new testid.
- `docs/ui-control-inventory.md` gains `noteFlag` `subject`.
- `the_one/agents.md`'s Self-configuration tab and Routines tab sections are
  updated for the two items, the queue, the origin and the flag.
- CLAUDE.md's Self-configuration paragraph gains: "since M33 F2 the tab has
  two items, Agent prompt and Routines …".

## Acceptance Criteria

- [ ] AC1. **The two items.** The tab shows "Agent prompt" (with the
      relabelled switches and the existing queue, history and external
      sections) and then "Routines", in that order. Every existing
      `test_studio_self_configuration_*` test passes with only the
      `_self_config.py` label constants changed. `test_flow_agent_tabs.py`
      passes unedited (still six tabs, Self-configuration last).
- [ ] AC2. **The Routines switches.** They post through the item `PUT`,
      persist, default to off with approval on, and show their errors. Turning
      the item off with pending proposals shows the withdrawn line and empties
      the queue.
- [ ] AC3. **The queue.**
  - Approve and Dismiss work for create, change and cancel proposals, and the
    Routines tab reflects the result.
  - The stale 409 shows the banner, and Approve anyway applies.
  - `gone` removes the item.
  - A 422 shows in the item.
  - Focus and the live line behave as stated.
  - History pages.
- [ ] AC4. **Origin and flag.** "Made by the agent" and the routine flag show
      on the Routines tab rows. The flag shows in the drawer group and on
      proposals. Editing a flagged routine and saving sends `prompt`, and the
      flag clears on the Routines tab.
- [ ] AC5. **`noteFlag` `subject`.** It works in both engines, and the
      default text is unchanged.
- [ ] AC6. **The lane.** `agent-routines` exists, the lanes stay disjoint,
      and `tests/test_run_tests_lanes.py` passes (17 lanes).
- [ ] AC7. **Guards.** The static guards pass: `tests/test_ui_guards.py`,
      `test_token_definitions.py`, `test_design_tokens_a11y.py`,
      `test_ui_control_inventory.py`, `test_ui_ownership.py`,
      `test_ui_emitted_classes.py`, `test_area_module_size`-style checks (the
      800-line rule), the registry and nav-helper guards, and
      `test_studio_editor_contracts_static.py`. The browser lanes pass:
      `agent-routines`, `agent-tabs`, `agents`, `contracts-controls`
      (`noteFlag`'s contract is `tests/browser/test_ui_feedback_contract.py`
      `test_note_flag_role_name_and_icon`) and `chats` (the drawer). `THE_ONE_TEST_NETNS=1 make test-unit` is green.
- [ ] AC8. **Docs**, as stated.

## Verification Steps

- **Lanes:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>`,
  one at a time.
- **The static guards and the unit suite.**
- **`scripts/ui_capture.py`.** Add `agent-self-config-routines` (seeded with
  one pending create and one flagged applied routine) and capture it to a
  scratch directory outside the repo, in both themes. The FD looks at the
  PNGs.

## Implementation Guidance

1. Add `noteFlag` `subject` and its contract test first.
2. Relabel Agent prompt and update `_self_config.py`. Run the five
   self-configuration files.
3. Build `self-config-routines.js` (the switches, then the queue, then the
   history), with the assembler wiring and script tags in `index.html`.
   Remember that `index.html` is cached per process, so a dev instance needs
   a restart.
4. Add the Routines tab origin and flag, the `formToBody` rule, and the
   drawer flag.
5. Then the lane, the tests, the registry and inventory, the docs and the
   capture surface.
6. Run the guards and lanes, then the flight log.

## Edge Cases

- **A proposal for a routine the operator just deleted** arrives as
  `superseded` (leg 2: an operator delete supersedes its pending proposals),
  so it shows in history, never in the queue.
- **The `default` agent.** The Routines item shows a note, "Routines need a
  named agent.", with no switches. The Agent prompt item behaves as today.
- **An unsaved agent** keeps the tab's existing "Save the agent first" state.
- **The tab module's size.** Keep each module under the 800-line rule. Split
  the queue into `self-config-routines-queue.js` if needed.
- **Approve races the poll.** Disable both buttons while a request is in
  flight, and ignore stale fetch responses with the module's sequence
  counter (the `revisionsSeq` pattern).

## Files Affected

- **New:**
  - `static/js/areas/studio/self-config-routines.js` (and a queue split if
    needed);
  - `tests/browser/test_flow_agent_routines_self_config.py`.
- **Changed:**
  - `static/js/areas/studio/self-config-status.js`;
  - `static/js/areas/studio/self-configuration-tab.js`;
  - `static/js/areas/studio/routines-tab.js`;
  - `static/js/areas/studio/routines-form-model.js`;
  - `static/js/areas/chat/agent-drawer-parts.js`;
  - `static/js/ui/feedback.js`;
  - `static/index.html`;
  - CSS as needed (`studio.css`, `components.css`);
  - `tests/browser/_self_config.py`, `test_flow_agent_routines.py`, the drawer
    test and `seeders.py`;
  - `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` and
    `scripts/ui_capture.py`;
  - `docs/ui-testid-registry.md` and `docs/ui-control-inventory.md`;
  - `the_one/agents.md` and `CLAUDE.md`.

## Citation Audit

Checked at leg design against the tree at `5b607af3`:
- `self-configuration-tab.js` (assembler order, 152 lines);
- `self-config-status.js` (both sections, labels, testids);
- `self-config-revisions.js` (queue controls);
- `routines-tab.js` testids.

The pinned test lines come from the Flight 2 planning survey. Re-check them
by grep at implementation.

## Design review amendments (cycle 1)

These are authoritative where they add detail to the sections above.

### Network callbacks

Every call in this tab goes through `cb.*`.
- Add `fetchRoutinesItem`, `putRoutinesItem`, `fetchRoutineProposals` (with
  `status`/`limit`/`before`), `approveRoutineProposal(id, override)` and
  `dismissRoutineProposal(id)` to `static/js/areas/studio/agent-data.js`
  (exports near `:519`).
- Pass them through `agent-editor.js` (`:149-161`) and the controller's
  callbacks into `renderSelfConfigurationTab`.
- The controller is at 770 lines, so add the fewest lines possible there.
- These three files join Files Affected.

### The lane, in full

In `scripts/run-tests.sh`, change:
- the usage and alias text (`:23`, `:28-30`, `:92`);
- `LANE_LIST` (`:59`) and `CANON_LANES` (`:60`);
- the `BUDGET` table: `agent-routines`, 300 provisional;
- `agent_tabs_pat` (`:222-223`): remove `test_flow_agent_routines*`;
- a new `agent_routines_pat`;
- **`agents_files()` (`:250-254`) must subtract `agent_routines_pat`.** Its
  `studio_pat` contains `test_flow_agent_*`, so without the subtraction the
  lanes overlap and the disjointness test fails;
- the lane `case` (near `:282`);
- the unknown-lane error message (`:516`);
- the comment for the `studio` alias, which expands `studio_pat`, so its
  code is unchanged.

In `tests/test_run_tests_lanes.py`, change the `LANES` tuple, the lane-list
string (`:163`) and any count, budget-table or `--plan` pins.

In CLAUDE.md, change every place: "sixteen lanes", the `--lane {…}`
selector, the lane list entries, the budget table, the aliases, "fifteen
named lanes", and the `shared` complement text.

### Proposal display mapping

- **`base`** is raw stored fields: `schedule`, `target_kind`,
  `target_session_id`, `enabled`, `finished_at`, `name`, `prompt`. Normalise
  it into the view shape (`{schedule, target:{kind, session_id},
  enabled, name, prompt}`) before calling `App.studio.routinesDescribe`.
- **`payload`** is the validated REST request, with the target in REST shape.
- A change shows every touched field among name, prompt, schedule, target and
  enabled. Enabled reads "On → Off".
- The stale 409's `current_value`, `proposed_value` and `base_value` are
  per-field maps over the touched keys. Display them through the same
  normalisation.
- The item's name is always the top-level `routine_name` (present on every
  proposal).
- Use the word **Withdrawn** for `superseded` everywhere: in history, in the
  live line and in the `gone` message.

### The flag-aware form

- `routines-form.js` (around `:94-97`) sets `ctx.flagged = !!routine.untrusted`.
- `formToBody` (`routines-form-model.js:88-102`) adds
  `if (ctx.flagged) body.prompt = prompt;`.
- So the "nothing changed, close" shortcut (`routines-form.js:380`) no
  longer fires for a flagged routine: Save sends the PUT, which clears the
  flag. Leg 2 clears it on any operator PUT with `prompt`, identical text
  included.
- An `evaluate` test pins `formToBody`, and a flow test pins the save
  clearing the flag.

### The drawer

- The routine rows come from `GET /api/agents/{name}/routines`
  (`agent-drawer.js:392-398`). They carry `untrusted` and `untrusted_sources`
  because leg 2 adds them to the view.
- In `agent-drawer-parts.js:36-47`, wrap the name and flag like `noteItem`
  (`.chat-drawer-note-head`, or a routine twin) and add
  `chat-drawer-routine-flag`.
- The drawer's own "Self-configuration" group heading
  (`test_flow_chat_drawer.py:367`) is **not** renamed, and gains nothing
  about Routines (DD5).

### `noteFlag`

- `opts = opts || {}` stays tolerant of `undefined`. The sentence is built as
  `'Check this ' + subject + ': …'`.
- The inventory row `docs/ui-control-inventory.md:75` becomes
  `App.ui.noteFlag({sources, subject, testid})`.
- `test_note_flag_role_name_and_icon` (`test_ui_feedback_contract.py:527`)
  gains the `routine` and throw cases.

### The relabel pins

- Keep these status words exactly:
  - "enabled" and "disabled" (`tab.py:46,64,101`; `dirty.py:113,244,268`);
  - "Approval mode is on" and "off" (`queue.py:213`, `dirty.py:94`, and the
    queue's off assertion).

  Only `_self_config.py:11-12`'s label constants change. No test reads the
  description sentences.
- The new subheadings use a new area class, not
  `.self-configuration-subheading`.

### Module plan, decided up front

- `self-config-routines.js`: the switches and history.
- `self-config-routines-queue.js`: pending, approve, dismiss and stale.

Script tags go near `index.html:107-109` before `self-configuration-tab.js`,
in dependency order. The 800-line guard is `tests/test_area_module_size.py`
(`LIMIT = 800`).

### The capture

`scripts/ui_capture.py` gains a `Surface` entry, `agent-self-config-routines`.
Its setup writes proposals with the same sqlite helper, using the data dir
that the capture seeder has.

### The `default` agent

Its Routines item note uses the testid `self-config-routines-default-agent`.

### Registry

Every new testid gets a row, including `routine-origin`, `routine-flag` and
`chat-drawer-routine-flag`.

### Leg 2 as landed (FD note)

- **Approving a cancel (delete) proposal can return the stale 409** when the
  routine changed since the proposal was made. The stale banner and "Approve
  anyway" apply to cancel items too.
- A duplicate pending create is refused with a 422. It never reaches the
  queue.
- **A near-term one-off can become unapprovable.** Approval re-validates a
  `once` (past, and at least a minute ahead). A one-off left pending too
  long fails approval with a 422 and can only be dismissed. The item's 422
  line shows the server sentence, and the queue's description should say
  that a one-off whose time has passed can only be dismissed.
- **Saving the edit form of a flagged routine clears the flag**, even with
  the prompt unchanged (by design, DD7). The form shows one hint line under
  the prompt field when the routine is flagged: "Saving marks this routine as
  checked."

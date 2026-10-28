# Leg: routines-tab-list

**Status**: ready
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Add a **Routines** tab to the agent editor, between Tools and
Self-configuration. It lists the agent's routines with:
- their schedule;
- their target;
- their next run;
- their last outcome.

From each row the operator can turn the routine on or off, run it now, delete
it, and read its run history. The tab loads lazily on first open and polls
only while it is visible and a run is going. The create and edit form is leg
9. Here the "New routine" and "Edit" buttons exist and call a form hook that
leg 9 fills in. Until then they are hidden behind a feature check that leg 9
removes.

## Context

- Flight DD12 (second half) and DD9. This is part 8a of the original leg 8,
  which design review split. The second part, 8b, is leg 9,
  `routines-tab-form`.
- **Server.** Leg 1 provides CRUD, `/runs` with `limit`/`before`, `limits`,
  list-shaped field 422s and the `default` refusal. Leg 4 provides
  `POST …/run`, `running` and the run time limit. Re-read the flight log for
  the exact shapes.
- **From leg 6.** The editor has five tabs, and this leg makes it six.
- **Save model.** The tab follows the Rules and notes tab: every action saves
  immediately and then refetches. Nothing here takes part in General's dirty
  state or `App.nav`.

## Inputs

All paths are under `the_one/interfaces/web/static/js/`.

- **`areas/studio/agent-editor.js`:**
  - `TAB_ITEMS`, `buildPanel`, `rebuildPanels` (each tab is built eagerly at
    mount) and `h.patch`;
  - tabs return `{setAgent, destroy}`, or are listed in `DESTROY_EXEMPT`
    (`tests/test_studio_editor_contracts_static.py`).
- **`areas/studio/agent-editor-controller.js`:**
  - `setActiveTab` (`~:376-392`);
  - the `deactivateSelfConfig` precedent (`:364-370`), the only tab hook
    today;
  - the callbacks bag.
- **`areas/studio/agent-data.js`:** callback helpers (`rulesJson`).
- **`areas/studio/studio-route.js`:** the tab whitelist (after leg 6).
- **Patterns to copy:**
  - `areas/studio/rules-notes-tab.js` and `rules-notes-shared.js`:
    `makeMutate`, the `gen` guard, focus return and the `section`, `status`,
    `emptyState` and `confirm` helpers.
- **The control library:**
  - `ui/feedback.js` `App.ui.status`, with `state: success | warning | danger | idle | pending`;
  - `App.ui.chip` (tone neutral, danger, warning);
  - `App.ui.disclosure`, `App.ui.toggle`, `App.ui.button`, `App.ui.confirm`.
- **`App.time`:** `formatClock`, `formatDate`, `parts`, and
  `onChange(fn, ownerEl)`. The weekday abbreviation comes from the helper
  `areas/chat/chats-list.js` uses.

## Outputs

- **`areas/studio/routines-tab.js`** (new):
  `App.studio.renderRoutinesTab(panel, agent, callbacks)` returns
  `{setAgent, activate, deactivate, destroy}`. Its script tag goes in
  `index.html`.
- **`areas/studio/routines-describe.js`** (new, pure): `describeSchedule(schedule)`,
  `describeTarget(target)`, `describeNext(row)` and
  `outcomeStatus(outcome)`, each built on `App.time`. Leg 9's form reuses
  them.
- **`agent-editor.js`:**
  - `TAB_ITEMS` gains `{id: 'routines', label: 'Routines'}` before
    Self-configuration;
  - `buildPanel('routines')`;
  - `h.routines`;
  - `h.patch` calls `h.routines.setAgent(a)`;
  - `h.destroy` destroys it.
- **`agent-editor-controller.js`:** `setActiveTab` calls
  `h.routines.activate()` when the tab becomes `routines`, and
  `h.routines.deactivate()` when it leaves. It also passes the callbacks
  `fetchRoutines`, `updateRoutine`, `deleteRoutine`, `runRoutine` and
  `fetchRoutineRuns` (from `agent-data.js`).
- **`studio-route.js`:** `routines` in the tab whitelist.
- **`static/css/studio.css`:** area layout only.
- **Tests:**
  - `tests/browser/test_flow_agent_routines.py` (new; `agent_tabs_pat` gains
    `test_flow_agent_routines*`);
  - tab-count pins move from five to six in
    `test_studio_editor_contracts_static.py`,
    `test_flow_agent_editor_frame.py`, `test_flow_agent_tabs.py` (keeping
    Self-configuration last) and `test_flow_agents_scale.py` (six tabs, no
    overflow at 1024px).
- **Registry:** `docs/ui-testid-registry.md` gains every new testid (list
  below).

## Acceptance Criteria

- [ ] AC1. **Tab and empty states.**
      - There are six tabs: General, Rules and notes, Knowledge, Tools,
        Routines, Self-configuration.
      - The route `#agents/{name}/routines` opens the Routines tab.
      - The tab bar has no overflow at 1024px, and the measured right edge is
        recorded in `agents.md`.
      - A `~new` agent shows `routines-save-first`.
      - The `default` agent shows the empty state "Routines need a named
        agent." (`routines-default-agent`).
- [ ] AC2. **Lazy loading.**
      - The tab makes no request until it is first activated. A test opens
        an agent on General and asserts no `/routines` request.
      - `activate()` fetches, and starts polling if a row is running.
      - `deactivate()` stops polling.
      - `destroy()` stops everything, drops the `App.time.onChange` listener
        (registered with the panel as `ownerEl`) and the `visibilitychange`
        listener.
- [ ] AC2a. **Activation from every entry path** (design review cycle 2).
      - **Why `setActiveTab` is not enough.** `App.ui.tabs` fires
        `onChange(initial)` while `ui.tabs(...)` is being built, before the
        panels exist. So a fresh mount (a direct
        `#agents/x/routines` open, an agent switch, a rename remount) never
        reaches the tab through `setActiveTab`.
      - **Mount.** At the end of the mount in `agent-editor.js`, after
        `buildPanel` and the `h.routines` assignment, call
        `h.routines.activate()` when `h.tabs.selected() === 'routines'`.
      - **Safety.**
        - `setActiveTab`'s call is null-safe.
        - `activate()` is idempotent: `tabs.select(sameId)` re-fires
          `onChange`, which must not double-fetch.
        - `deactivate()` is idempotent too.
      - **Leaving.** Polling also stops when the Studio area deactivates, by
        calling `routines.deactivate()` from the same place as the area
        deactivation hook (find the `App.studio` deactivate path that tears
        down or hides the editor). It also stops when the editor closes
        (`destroy`).
      - **Same identity.** A same-identity `h.patch` (`setAgent(a)` after a
        General save) only updates the agent reference. It does not refetch,
        and does not reset an open History disclosure, focus or `gen`.
      - **Browser tests:**
        - a direct open on `#agents/x/routines` fetches once and polls while
          a run is going;
        - a rename remount while on the tab works;
        - leaving to Chats stops the polling: no further `/routines`
          requests.
      - **The poll cap** in AC5 uses `limits.run_timeout_seconds` (leg 4),
        plus 30 seconds, measured from the Run now click.
      - **Form buttons.** The leg-8 test asserts that New routine and Edit
        are absent, so leg 9 flips them deliberately. The
        `App.studio.routinesForm` check runs at click and render time, not at
        script load.
- [ ] AC3. **The list.** Each routine is one row (`routine-row`,
      `data-routine-id`), sorted by name, and shows:
      - the name (`routine-name`, textContent);
      - the schedule sentence (`routine-schedule`), for example "Daily at
        9:00 AM", "Weekdays at 9:00 AM", "Mon, Wed, Fri at 7:30 PM", "Every 2
        hours" or "Once, Fri Oct 30 at 9:00 AM", with `once` in the operator
        zone;
      - the target (`routine-target`):
        - "{chat title} · {Platform}", where Platform comes from
          `App.chat.chatsList.platformName`;
        - "New chat each run";
        - "Its own chat";
        - "Chat gone, a new one starts on the next run" when `missing`;
      - the next-run line (`routine-next`). Precedence is Running, then Done
        (`finished_at`), then Off (`enabled` false), then "Next {weekday}
        {h:mm AM/PM}";
      - the last outcome (`routine-last`), an `App.ui.status` from this
        table:

        | Outcome | State | Label |
        |---|---|---|
        | running | pending | Running |
        | ok | success | Ran {when} |
        | failed | danger | Failed {when}: {reason} |
        | skipped | warning | Skipped {when}: {reason} |
        | missed | warning | Missed: {reason} |
        | interrupted | warning | Interrupted {when} |
        | stopped | idle | Stopped {when} |
        | none | idle | Not run yet |

      With no routines the tab shows `App.ui.emptyState`
      (`routines-empty`), with the New routine action from AC6.
- [ ] AC4. **Row controls.**
      - **Toggle** (`routine-toggle`, a switch named "Run {name} on
        schedule"). It sends `PUT {enabled}`. On a Done row it is disabled,
        with the visible hint "Set a new time to run it again."
      - **Run now** (`routine-run-now`).
        - On click it disables at once and calls `POST …/run`.
        - A 202 starts polling (AC5).
        - A 409 shows "This routine is already running." in the row's error
          line (`routine-error`, `App.ui.status` danger) and starts polling.
        - It is disabled while the row is running.
      - **Delete** (`routine-delete`), armed through `App.ui.confirm`.
      - **History** (`routine-history`), an `App.ui.disclosure`.
        - The first open fetches `…/runs?limit=20`.
        - Each entry (`routine-run`) shows the outcome label, the trigger
          ("Scheduled", "Caught up", "Run now"), the time through `App.time`,
          the reason, and "New chat" when `new_chat` is true.
        - "Show older" (`routine-history-more`) pages with `before`.
        - An open disclosure refetches its first page after each list
          refresh that changed that row's `last_run`.
      - **Focus** follows the Rules tab: after a delete, focus moves to the
        neighbouring row's toggle, or to the New routine button when the list
        is empty. After a toggle or Run now it stays on the control.
- [ ] AC5. **Live refresh.**
      - While the tab is active and the document is visible, the tab polls
        `GET …/routines` every 3 seconds if any row is `running` or a Run now
        is pending.
      - Polling stops when nothing is running and nothing is pending, or once
        the run time limit plus 30 seconds has passed since the last Run now.
      - The tab also refetches on `visibilitychange` to visible while active.
      - A `gen` guard drops stale responses.

      A test: Run now with a mock provider `delay_ms` of about 2 seconds
      shows Running, then Ran, and the History disclosure shows the manual
      run, with no reload and no fixed sleeps (`expect` waits only).
- [ ] AC6. **The form hooks for leg 9.**
      - The tab renders New routine (`routines-new-btn`) in the section
        header and Edit (`routine-edit`) on each row. Both call
        `callbacks.openRoutineForm({mode, routine, opener})` when
        `App.studio.routinesForm` exists.
      - While it does not exist, which is this leg, the buttons are hidden.
      - `routinesForm` returns a promise that resolves after a save, and the
        tab then refetches and focuses the saved row's Edit.
- [ ] AC7. **Times and zone.** Every time shown goes through `App.time`. An
      `App.time.onChange` re-renders the list's times without a refetch.
- [ ] AC8. **Gates.**
      - Lanes, with `THE_ONE_TEST_NETNS=1`: `agent-tabs`, `agents` and
        `routing`.
      - Static guards:
        - `tests/test_ui_guards.py` (registry diff, sinks);
        - `tests/test_token_definitions.py`;
        - `tests/test_design_tokens_a11y.py`;
        - `tests/test_studio_editor_contracts_static.py`;
        - `tests/test_ui_ownership.py`.
      - `tests/test_run_tests_lanes.py`.
      - `make test-unit` and `make lint`.

## Verification Steps

- AC1-AC7: `tests/browser/test_flow_agent_routines.py`. Routines are seeded
  through REST (leg 1 routes) on a mock-provider agent, and a web chat is
  seeded with `seeders.seed_session`. For the lazy check, use
  `page.on('request')`.
- AC8: run the commands above.

## Implementation Guidance

1. **Wiring.** Add the callbacks in `agent-data.js` and the controller, the
   `TAB_ITEMS` entry, `buildPanel`, the handle bookkeeping, the route
   whitelist, the script tag, and the `activate`/`deactivate` calls in
   `setActiveTab`. If the editor opens directly on `#agents/x/routines`,
   `setActiveTab` runs at hydrate, so `activate` fires; verify it.
2. **`routines-describe.js`.** Pure helpers.
3. **The tab.** Build the list and row controls on the Rules tab's
   `makeMutate`/`gen` pattern.
4. **Polling and visibility.**
5. **Pins, registry, lanes.**

## Edge Cases

- **A routine deleted by another tab:** the next refetch drops its row, and
  an open History disclosure goes with it.
- **The agent is renamed while the tab is open:** the editor remounts, as for
  Rules.
- **A long prompt** is not shown in the row. The form shows it (leg 9).
- **A 404 on `/routines` for a just-deleted agent:** the editor is already
  closing, so ignore it.

## Files Affected

All `static/` paths are under `the_one/interfaces/web/`.

- `static/js/areas/studio/routines-tab.js`, `routines-describe.js` (new);
  `agent-editor.js`, `agent-editor-controller.js`, `agent-data.js`,
  `studio-route.js`; `static/index.html`; `static/css/studio.css`
- `tests/browser/test_flow_agent_routines.py` (new); the tab-count pin files;
  `scripts/run-tests.sh` (`agent_tabs_pat`)
- `docs/ui-testid-registry.md`, `the_one/agents.md`

## Citation Audit

Checked on the working tree:
- `agent-editor-controller.js:364-392` (`deactivateSelfConfig`,
  `setActiveTab`);
- `ui/feedback.js:210-225` (`App.ui.status` states);
- `areas/chat/chats-list.js:102-132` (`platformName`, neutral `unknown`
  badge kind);
- `rules-notes-tab.js` header.

Re-grep the tab-count pins after leg 6.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off the
leg in the parent flight, and the commit) are Flight Control protocol, driven
by the execution workflow, and are not repeated here.

# Leg: routine-routes-and-editor-maintenance

**Status**: completed
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Carry the flight's maintenance (DD9) before the recurrence work starts:
move the routine routes out of `api.py` into their own router module with
no behaviour change, split `agent-editor-controller.js` back under its line
limit with room to spare, and complete squawks 0232, 0273 and 0284.

## Context

- **Why first:** later legs rewrite the routine routes' validation and
  responses; moving them first keeps those diffs readable, and the
  existing routine tests are the characterization net for the move. The
  controller split makes room for Flight 4's HAT fixes.
- **The route move (flight DD9, two Architect cycles):**
  - The block runs from the `# ── Routines (M33 F1)` banner in
    `the_one/interfaces/web/api.py` to just before `# ── Notes (M27 F2)`. It
    holds the operator routine routes, the self-configuration routines
    routes, the proposals routes, Run now and the runs route, with their
    helpers (`_DEFAULT_AGENT`, `_routine_422`, `_routines_agent_or_404`,
    `_routines_repos`, `_routine_body`, `_RoutinesSwitchesBody`, …).
  - **Stays in `api.py`:** `_poke_scheduler` (called by `put_time_settings`
    and by `tests/test_routines_scheduler.py::test_poke_scheduler_tolerates_none`
    as `api._poke_scheduler()`), and the Purge now path's
    `RoutineRunRepository(...).delete_all_for_agent` (outside the block).
  - **Attachment:** the new module defines its own `APIRouter` (no prefix;
    `api.router` carries `/api`) and `api.py` calls
    `router.include_router(routines_router)` at the bottom of the module,
    after every `api.router` route is declared. The routes stay in
    `api.router.routes`, so every test app built on `api.router` gets them
    and `tests/test_api_name_rule.py` (walks `api.router.routes`) keeps
    classifying them. Check that `include_router` copies the routes into
    `api.router.routes` at call time (it does in FastAPI: it re-adds each
    route), so the include must run after the routines module's routes are
    declared — importing the module first, then including, at the bottom of
    `api.py`.
  - **Patch-through:** `tests/test_routines_api.py`,
    `tests/test_routines_self_config_api.py`, `tests/test_rename_carries.py`
    and `tests/test_api_name_rule.py` patch
    `the_one.interfaces.web.api.get_connection` / `get_encryptor`. The moved
    handlers must look those (and every other `api.py` helper they use:
    `_load_agent_or_404`, `_chat_repo`, …) up through the `api` module at
    call time — `from the_one.interfaces.web import api as _api` inside
    each function, or a module-level lazy accessor — never by importing the
    name into the new module, or the patches stop applying.
  - **No circular import at load:** `api.py` imports the routines module
    only at its bottom; the routines module must not import `api` at module
    top level.
  - `_RoutineTurnHost` stays in `app.py` (DD9, cycle 1).
- **The controller split:** `static/js/areas/studio/agent-editor-controller.js`
  is 781 lines against the 800 limit (`tests/test_area_module_size.py`). The
  flight names the self-configuration refresh block (`parseSnapshot_`,
  `idsOf_`, `recheckStoredNote_`, `rebaseBaseline_`, `onSelfConfigChanged`)
  as the candidate. It closes over controller state (`self`, `state`,
  `currentData_`, `getFormSnapshot`, `checkDirty`, `saveInFlight`), so the
  new module receives those through a small `ctx`-style object the
  controller builds (the area modules' existing `ctx` pattern; see how
  `agents-list.js` reaches the controller). If another block is a cleaner
  seam with the same saving (`buildCallbacks_`), the Developer may choose it
  and records why. The new script gets a `<script>` tag in `index.html`
  before the controller (`index.html` is read once per process).
- **Squawk 0232** (`squawks/0232-self-config-area-guard-not-falsifiable.md`):
  the `self._activeSection === 'agents'` term in `onSelfConfigChanged`'s
  `live` condition cannot be made to fail by any test. Its Verification
  section: remove the term, or rename and comment it to say exactly what it
  covers; the dirty-file tests pass; the comment states that a write
  resolving on Chats or Settings patches the hidden editor in place.
- **Squawk 0273** (`squawks/0273-agent-editor-header-errors-not-announced.md`):
  header save errors are not announced. `agent-editor.js` builds
  `ui.editorShell({...})` without `errorRole`; `editorShell`'s only value,
  `'alert'`, puts `role=alert` on `span.editor-error`. The same slot holds
  the load-failure line (`setError(on ? LOAD_ERROR_LINE : null)` with testid
  `agent-load-error`), which must stay silent (its toast announces it). The
  fix announces save errors and keeps the load line silent — for example by
  setting `role=alert` only while a save error is shown, or giving the save
  path its own announcement — without changing `App.ui.editorShell`'s
  public contract unless its inventory row and contract test change with it.
- **Squawk 0284** (`squawks/0284-fix-prompt-falsify-by-edit.md`): the
  "Developer: Fix Review Issues" prompt in
  `.flightops/agent-crews/leg-execution.md` (and "Implement", if it asks for
  falsification — it does not today) gains a falsify-by-edit rule.
- **Squawks are completed in this leg**, not on squawk branches: each
  squawk artifact gets Corrective Action, Verification and status
  `completed` with the completion date; the Sign-Off Reviewer and Commit are
  filled at the batch review and commit by the FD.

## Inputs

- Flight spec DD9; the three squawk artifacts.
- `the_one/interfaces/web/api.py` (routines block), `app.py` (how
  `api.router` is included), the four test files above.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor-controller.js`,
  `agent-editor.js`, `the_one/interfaces/web/static/js/ui/editor.js`,
  `the_one/interfaces/web/static/index.html`, `tests/test_area_module_size.py`.

## Outputs

- `the_one/interfaces/web/routines_api.py` holding the moved routes and
  helpers; `api.py` without them, with the include at its bottom.
- A new studio module carrying the split-out controller block; the
  controller at or under about 700 lines.
- Squawks 0232, 0273 and 0284 completed in their artifacts.
- `the_one/agents.md`: the routine routes' new home (one or two sentences
  where "Routines (M33)" names `api.py`), and the new studio module in the
  agent editor module map if one is listed.
- Flight log entry for this leg.

## Acceptance Criteria

- [ ] AC1. Every routine route (the same method and path set as before) is
      served from `routines_api.py` and is present in `api.router.routes`.
- [ ] AC2. These pass with **no edit to the test files**:
      `tests/test_routines_api.py`, `tests/test_routines_self_config_api.py`,
      `tests/test_rename_carries.py`, `tests/test_api_name_rule.py`,
      `tests/test_routines_scheduler.py`, `tests/test_routines_runner.py`,
      `tests/test_routine_turn_path.py`, `tests/test_routines_service.py`,
      `tests/test_routines_proposals.py`. (`git diff ebb83d8c -- <these files>`
      is empty.)
- [ ] AC3. `api.py` keeps `_poke_scheduler`; no routine route handler is
      left in `api.py`.
- [ ] AC4. `agent-editor-controller.js` is at most about 700 lines; the
      new module is registered in `index.html`; `tests/test_area_module_size.py`
      passes.
- [ ] AC5. The agent editor's existing browser tests pass: the `agents` and
      `agent-tabs` lanes (self-configuration dirty and refresh tests live in
      `agent-tabs`).
- [ ] AC6. Squawk 0232: per its Verification section.
- [ ] AC7. Squawk 0273: a failed agent Save that puts its message in the
      header (a non-name server error) is announced (`role=alert`, or an
      equivalent live announcement, present while the message shows); the
      load-failure line (`agent-load-error`) has no live role. A browser test
      pins both, falsified by edit (remove the fix by editing, see the test
      fail, put the fix back by editing — never restore a whole file).
- [ ] AC8. Squawk 0284: the Fix Review Issues prompt says a falsification
      removes the fix by editing and puts it back by editing, never by
      restoring a whole file or a backup copy.
- [ ] AC9. `THE_ONE_TEST_NETNS=1 make test-unit` passes (15 skipped
      expected); `ruff check` and `ruff format --check` clean; the static
      guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`,
      `tests/test_design_tokens_a11y.py`) pass.

## Verification Steps

- AC1: a one-off Python check listing `api.router.routes` (method, path)
  before (`git show ebb83d8c:the_one/interfaces/web/api.py` is the
  reference) and after; the routine set is identical and each endpoint's
  module is `the_one.interfaces.web.routines_api`.
- AC2: run the listed files; `git diff ebb83d8c --stat -- <files>`.
- AC3: `grep -n "@router.*routines" the_one/interfaces/web/api.py` is empty.
- AC4: `wc -l`; the module-size test.
- AC5: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents` and `--lane agent-tabs`.
- AC6-AC8: read the squawk artifacts and the crew file; the new test.
- AC9: the commands named.

## Implementation Guidance

1. Move the routes: create `routines_api.py`, move the block verbatim,
   then convert every reference to an `api.py` symbol into a call-time
   lookup through the `api` module. Keep the block's comment banner.
2. Add the include at the bottom of `api.py`; run AC1's check and the AC2
   files.
3. Split the controller; register the script; run the module-size test and
   the two lanes.
4. Squawk 0232 inside the moved block (it lives in `onSelfConfigChanged`).
5. Squawk 0273 with its browser test (agent editor tests are in the
   `agents` lane unless the file matches an `agent-tabs` glob).
6. Squawk 0284 in the crew file.
7. Update `the_one/agents.md`, the squawks, the flight log.

## Edge Cases

- A route ordering change: the routines routes now come after every other
  `api.router` route. There are no `{path:path}` routes under
  `/agents/{name}` that could match first; confirm no 404/405 change in the
  AC2 tests.
- `include_router` adds copies: confirm no route appears twice.
- Startup: `app.py` must still include `api.router` once; the app's own
  route list must contain each routine route exactly once.

## Files Affected

- `the_one/interfaces/web/api.py`, new `the_one/interfaces/web/routines_api.py`
- `the_one/interfaces/web/static/js/areas/studio/agent-editor-controller.js`,
  a new studio module, `agent-editor.js`, `static/index.html`
- a browser test for 0273 (agents lane)
- `squawks/0232-…`, `squawks/0273-…`, `squawks/0284-…`,
  `.flightops/agent-crews/leg-execution.md`
- `the_one/agents.md`, the flight log

## Citation Audit

Checked at `49a5051a`:
- `api.py` "Routines (M33 F1)" banner through `GET …/routines/{routine_id}/runs`,
  before "Notes (M27 F2)"; `_poke_scheduler` called at `put_time_settings`
  (about `:2949`); `RoutineRunRepository(...).delete_all_for_agent` in Purge
  now (about `:5515`) — verified.
- The four test files' `patch("the_one.interfaces.web.api.get_connection")`
  — verified.
- `agent-editor-controller.js` 781 lines; `onSelfConfigChanged` `live`
  condition with `self._activeSection === 'agents'` — verified.
- `agent-editor.js` `ui.editorShell({` without `errorRole`; load line via
  `h.shell.setError(on ? LOAD_ERROR_LINE : null)` with testid
  `agent-load-error`; `ui/editor.js` `errorRole: 'alert'` sets `role=alert`
  on the error span — verified.

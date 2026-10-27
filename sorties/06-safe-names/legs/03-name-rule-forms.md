# Leg: name-rule-forms

**Status**: completed
**Flight**: [Safe names](../flight.md)

## Objective
Show the server's name refusal on the name field of the agent, model-provider and knowledge-base forms (the MCP editor already does), and replace the agent editor's inline load-failure block with an error toast plus a lasting line in the editor header that says why Save is off.

## Context
- Flight DD9 (field errors; no client copy of the rule; clear rules; `connectors` invalidation after an agent rename) and DD10 (the load failure: toast + header line on `shell.errorEl`, the testid moved there, no `role=alert`, the load check ahead of `refuseBlockingOverride_`).
- Leg 1 made every name refusal a 422 with `detail == [{"type": "name_rule", "loc": ["name"], "msg": ...}]` and every agent name conflict (create and rename) a 409 with `[{"type": "name_conflict", "loc": ["name"], "msg": "An agent with this name already exists."}]`. The rename route uses `loc ["name"]` too. Messages are plain sentences and must reach the field verbatim (`App.api.fieldErrors` humanises messages; confirm it leaves these unchanged).
- Leg 2 made an agent rename rewrite connector bindings server-side, so the client must invalidate its `connectors` store collection after a rename.
- The MCP editor (`areas/studio/mcp-server-editor.js`, `onSaveError`) is the in-repo pattern: `App.api.fieldErrors(err, SERVER_FIELDS)` → the field handle's `setError` plus `shell.setError(fe.text || '')`.

## Inputs
- `areas/studio/general-tab.js` — the `studio-name` `ui.textInput` and `ui.field({ label: 'Name', control: nameInput }).el` (the field handle is discarded); the tab's returned API (`setAgent`, …).
- `areas/studio/agent-editor-controller.js` — `save(isCreate)` (create: raw `fetch` POST, `extractApiError`; edit: `self._selectedAgentLoaded === false` check after `refuseBlockingOverride_`, the `/rename` POST then the PUT, both with `extractApiError`), `setEditorError_`, `showFlash` (container `editorEl`), the rename's `App.store.invalidate('agents'|'sessions')`.
- `areas/studio/agent-editor.js` — `LOAD_ERROR_TEXT`, `h.loadErrorEl` (`div.agent-load-error`, `role=status`, testid `agent-load-error`), appended after `h.shell.el`; `setLoadError(on)`; `patch` re-applies it.
- `areas/studio/agents-list.js::doSelect` — the fresh-agent fetch whose `.catch` sets `freshAgentLoaded = false`.
- `areas/admin/knowledge-settings-page.js` — the precedent: a load error written to `shell.errorEl` with a testid added and removed.
- `areas/studio/provider-editor.js` — `h.name = App.ui.field(...)` (`pf-name`), `App.api.fetchJson` save, `.catch` → `h.shell.setError(err.message || String(err))`.
- `areas/studio/knowledge-create.js` — `nameField` (`kb-create-name-input`), `errorLine` (`App.ui.status`, testid `kb-create-error`), `App.api.fetchJson('/api/knowledge-bases', …)`.
- `areas/studio/knowledge-detail.js` — `nameField` (`kb-name-input`), `App.api.fetchJson('/api/knowledge-bases/' + id, …)`, `.catch` → `shell.setError(...)`.
- `api.js` — `App.api.fetchJson`, `App.api.fieldErrors`, `humanizeMessage`.
- `studio.css` — the `.agent-load-error` rule.
- Tests: `tests/browser/test_flow_agent_editor_frame.py` (pins `kids[:2] == ["editor-header", "agent-load-error"]` and checks the testid's visibility), `tests/browser/test_flow_studio_knowledge_attach.py` (uses the testid).

## Outputs
- The four non-MCP forms show a name refusal on their name field; other errors keep their current surface.
- The agent editor's load failure is a toast plus a header line; the old block, its CSS and `LOAD_ERROR_TEXT` are gone.
- New browser test file `tests/browser/test_flow_name_rule_forms.py` (lands in the `shared` lane, the complement; no lane table change), updates to the two existing browser files.
- `docs/ui-testid-registry.md` updated for `agent-load-error`'s new element.

## Acceptance Criteria
- [ ] **Agent create**: submitting the name `a/b` leaves the form open with "A name can't contain / or \." on the Name field (`studio-name`'s field), no "name:" prefix and nothing in the header error; no agent is created. Submitting the name of an existing agent shows "An agent with this name already exists." on the Name field and the existing agent is unchanged.
- [ ] **Agent rename**: changing an existing agent's Name to `a/b` and saving shows the refusal on the Name field, makes no PUT, and the agent keeps its name (the test watches requests with a `page.route` method check, as `test_flow_agent_editor_frame.py` does, and asserts no PUT was sent); renaming to another existing agent's name shows the conflict message on the Name field. A successful rename invalidates `App.store`'s `connectors` collection as well as `agents` and `sessions`.
- [ ] The agent editor's create, rename and save requests go through `App.api.fetchJson` and map errors with `App.api.fieldErrors(err, ['name'])`: the `name` message to the Name field, the rest (`fe.text`) to the editor's header error. `extractApiError` (used only by these three calls) is deleted. The client-side "Name is required." checks in `save()` move to the Name field too (`general.setNameError`), so every name message has one home. After a server name refusal the Name input is focused (as KB create does).
- [ ] **Provider editor** (create and edit): an `a/b` name shows the refusal on `pf-name`'s field; other server errors still go to the header error. (Intended change: a non-name 422 in the header now reads as `fieldErrors`' humanised sentence without the `field:` prefix `fetchJson` flattens into `err.message`; no existing test reads that prefix.)
- [ ] **Knowledge base create**: an `a/b` name shows the refusal on the name field (`kb-create-name-input`'s field); other errors still go to `kb-create-error`. **Knowledge base edit** (`kb-name-input`): the refusal on the name field; other errors to the header error.
- [ ] **MCP editor**: one regression test that an `a/b` name shows the refusal on its name field (it already works).
- [ ] In every form, a name-field error clears on the next input in the Name field, on Cancel, and when the editor shows another item. The places: agent — the `studio-name` `onInput` and `general.setAgent` (Cancel goes through `cancelEdit` → `patch` → `setAgent`); provider — `nameInput`'s `onInput` (`provider-editor.js` around line 116) and `onCancelClick`; KB create — already clears on input and at submit (Cancel destroys the form); KB detail — `nameInput`'s `onInput` (it does not clear today) and `cancel()`.
- [ ] **Load failure**: when `doSelect`'s fresh-agent fetch fails, an error toast "Couldn't load this agent's settings." appears (`App.ui.flash(…, {error: true})`, default `document.body` container) once for that failed load, and the editor header's error slot (through `shell.setError(text)`, so the slot's `data-empty` state is managed — writing `errorEl.textContent` directly would leave the row collapsed) reads "Save is off because this agent's settings didn't load. Reopen the agent to try again." with the `agent-load-error` testid on it while (and only while) the load has failed; the header line has no `role=alert`; Save stays disabled; re-renders and `patch` keep the line without re-announcing it or re-firing the toast (`setLoadError` acts only on a state **transition**, tracked in `h.loadFailed`: false→true calls `shell.setError(text)` and adds the testid, true→false calls `shell.setError(null)` and removes it, same state does nothing — so a `patch` never erases a legitimate save error either); a later successful load of that agent clears the line and the testid (tested: slot empty, testid gone). Each failed select toasts once; a re-select of the same agent that fails again toasts again (accepted).
- [ ] A Save triggered while the load has failed (script or keyboard) does nothing and does not replace the header line: `save()` determines create vs edit first, and for edit the `_selectedAgentLoaded === false` check runs before `ctx.formData.blockingError()`/`refuseBlockingOverride_` and returns without writing a new error. For every other Save, the header error and the Name error are cleared at the start.
- [ ] `div.agent-load-error`, its `studio.css` rule and `LOAD_ERROR_TEXT` are removed; `tests/browser/test_flow_agent_editor_frame.py:58-62`'s first-children pin is updated deliberately to `["editor-header", <the tab list's class>]`, and its `loadError` probe (today `:not([hidden])`) becomes "the testid is present and its text is the header line" (the slot is never `hidden`, only `data-empty`); its `to_be_visible` checks (around 183-190) hold while the text is set. `tests/browser/test_flow_studio_knowledge_attach.py:708` (asserts `.editor-error` contains "failed to load" after a forced Save) is updated to assert the new header line and that no PUT was sent; its testid use (around 691) follows the new element.
- [ ] The static guards pass (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, plus `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_nav_helper.py`); the `agents`, `agent-tabs`, `providers`, `knowledge`, `mcp` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1` (at most 3 at a time); `make test-unit` shows only the baseline failures; ruff passes on touched Python.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh -m browser tests/browser/test_flow_name_rule_forms.py tests/browser/test_flow_agent_editor_frame.py tests/browser/test_flow_studio_knowledge_attach.py -x --timeout 60`
- Then each lane: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane> -x` for `agents`, `agent-tabs`, `providers`, `knowledge`, `mcp`, `shared` (sequentially, or `--parallel` with at most 3).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_nav_helper.py -x --timeout 60`
- `make test-unit` once at leg end.

## Implementation Guidance

1. **General tab name handle.** Keep `var nameField = ui.field({ label: 'Name', control: nameInput })` and use `nameField.el` in the section. Add `setNameError(msg)` to the tab's returned API (`nameField.setError(msg || null)`). Clear it in the name input's `onInput` (alongside `dirty`) and in `setAgent`.

2. **Agent editor controller.** Replace the three raw `fetch` calls with `App.api.fetchJson` (keep the same methods, headers and bodies; check how `fetchJson` resolves the JSON so the `.then` chains keep their values). One local `onNameError_(err)` does `var fe = App.api.fieldErrors(err, ['name']); general.setNameError(fe.fields.name || null); setEditorError_(fe.text || '');` (reach the General tab's handle the way the controller already reaches other tab handles). Clear the Name error at the start of each Save and on Cancel. After a successful rename add `App.store.invalidate('connectors')`. In `save()`, move the `self._selectedAgentLoaded === false` check to the top of the edit branch, before `blockingError`/`refuseBlockingOverride_`, and make it `return` without calling `setEditorError_`.

3. **Load failure.** In `agent-editor.js`, remove `h.loadErrorEl`, `LOAD_ERROR_TEXT` and the `.agent-load-error` CSS; make `setLoadError(on)` follow the knowledge-settings precedent (`knowledge-settings-page.js` around 94-102): `shell.setError(text)` / `shell.setError(null)` plus adding/removing the `agent-load-error` testid on `h.shell.errorEl` (only while the text is non-empty), acting only on a transition of `h.loadFailed`. Read `ui/editor.js` to confirm `errorEl`'s visibility rules (hidden when empty?) and that `setError('')` from a Save path cannot leave the testid on an empty slot; if `setEditorError_('')` runs while the load has failed, it must not erase the line (the Save path returns early, so this should not happen; assert it in a test). Fire the toast from `agents-list.js::doSelect` inside the `Promise.all(...).then`, right after its stale-select guard (`mySelect !== state.selectSeq …`), when `!freshAgentLoaded`, via `App.ui.flash(text, { error: true })` with no `container` (tests can count `.app-flash.error`).

4. **Provider editor and KB forms.** In each `.catch`, map with `App.api.fieldErrors(err, ['name'])`: provider → `h.name.setError`, rest → `h.shell.setError(fe.text || '')`; KB create → `nameField.setError`, rest → `errorLine` (as it shows errors today); KB detail → `nameField.setError`, rest → `shell.setError`. Clear each name error on input, on Cancel and on the editor's re-render/patch path. Keep the existing client "required" checks and the 43-code-point hint.

5. **Tests.** New `tests/browser/test_flow_name_rule_forms.py`, navigating through `tests/browser/_nav.py` and `_lists.py` (never raw hashes; `tests/test_nav_helper.py` enforces it), seeding through `tests/browser/seeders.py`. One test per criterion above for create/rename/provider/KB create/KB edit/MCP, each asserting the field message, the absence of a header error, and that nothing was saved (read back through the API). Make the fresh-agent fetch fail with Playwright `page.route` on `**/api/agents/<name>` (GET only) after the list has loaded; assert the toast (`role=alert`, the text), the header line with the testid, Save disabled, and that a second render does not add another toast. Update `test_flow_agent_editor_frame.py` (the first-children pin and the visibility checks) and `test_flow_studio_knowledge_attach.py` if they read the old element.

6. **Docs.** `docs/ui-testid-registry.md` (the `agent-load-error` row, around line 61): it now lives on the editor header's error slot, present only while the load has failed. Update the stale descriptions found by `grep -rn 'agent-load-error\|loadErrorEl\|LOAD_ERROR_TEXT'`: `agent-editor.js`'s header comment and handle shape (lines 8 and 17), and `the_one/agents.md` around line 2193 (the frame-node description and the handle `{…loadErrorEl…}`).

## Edge Cases
- **`fieldErrors` humanising**: confirm none of `HUMANISERS` rewrites the plain messages ("Enter a name.", "A name can't contain / or \.", …); if one does, the server's messages win and the humaniser is narrowed only if it is a clear bug, recorded in the flight log.
- **A 422 that is not about the name** (e.g. a provider field): unchanged surface.
- **A rename that succeeds but whose following PUT fails**: the name error stays clear, the PUT's error goes to the header as today.
- **The load failure on a non-current select** (the user moved on): no toast (the sequence guard).
- **Leaving and reopening the agent** after a failed load: a fresh select; a success clears the line.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js`
- `the_one/interfaces/web/static/js/areas/studio/agent-editor-controller.js`
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`
- `the_one/interfaces/web/static/js/areas/studio/agents-list.js`
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`
- `the_one/interfaces/web/static/js/areas/studio/knowledge-create.js`
- `the_one/interfaces/web/static/js/areas/studio/knowledge-detail.js`
- `the_one/interfaces/web/static/css/studio.css` (or wherever `.agent-load-error` lives)
- `tests/browser/test_flow_name_rule_forms.py` - new
- `tests/browser/test_flow_agent_editor_frame.py`, `tests/browser/test_flow_studio_knowledge_attach.py`
- `docs/ui-testid-registry.md`

---

## Post-Completion

The Developer marks the leg `landed`, records changes and verification in the flight log, and signals `[LAND:leg]`. Nothing is committed.

## Citation Audit
Checked against the worktree (leg 1 and 2 changes present, no JS touched by them): `general-tab.js` (`studio-name`, field handle discarded, returned API with `setAgent`); `agent-editor-controller.js` (`save`, `refuseBlockingOverride_` before the load check, raw `fetch` + `extractApiError` for create/rename/PUT, rename invalidates `agents` and `sessions`, `showFlash` with `container: editorEl`); `mcp-server-editor.js::onSaveError` (`fieldErrors` + `shell.setError(fe.text || '')`); `api.js` (`fieldErrors` strips a leading `body`, exact segment match, humanises); `provider-editor.js` (`h.name`, `fetchJson`, `.catch` → `h.shell.setError`); `knowledge-create.js` (`nameField`, `errorLine` `kb-create-error`, `fetchJson`); `knowledge-detail.js` (`nameField` `kb-name-input`, `fetchJson`, `.catch` → `shell.setError`) — verified.

Design review (Developer, 2026-10-26): approve with changes; adopted — the two existing-test updates named (`test_flow_agent_editor_frame.py:58-62`, `test_flow_studio_knowledge_attach.py:708`), `shell.setError` on a state transition instead of a direct `textContent` write, the save() split, the per-editor clear points, the humanised non-name header text recorded as intended, the client "Name is required." moved to the field, focus on refusal, no-PUT assertion, stale doc lines.

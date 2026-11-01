# Leg: agent-tab

**Status**: completed
**Flight**: [Agent tool overrides](../flight.md)

## Objective
Make the agent editor's Built-in tools tab store only what the operator changes. Each field shows whether it is inherited or the agent's own, with Reset. A clipped field shows its narrowing with a one-step fix. A save refusal lands on its field. The path fields say how Shell, Python and downloads are limited on this computer. A once-ever startup cleanup removes the inherited values earlier saves copied in.

## Context
- Flight design decisions implemented here: **DD9** (inherited vs own; the own-only Save walk with locked-chip subtraction; the clipped-field line and its fixes; the three-segment 422 mapping; the unchanged-own-number range exemption), **DD10** (`execution_sandbox` on `GET /api/config`, warmed in the lifespan; the Shell/Python/download note), **DD13** (the once-ever cleanup). Read those sections of `../flight.md` in full: they are the spec. Charter criteria 2 and 4, and the "stop copying"/"remove the copies" half of criterion 2.
- **What legs 1-2 delivered** (uncommitted in this tree; see their flight-log entries):
  - The resolver's denied lists resolve as app-wide ∪ agent, so storing only the agent's additions is now valid (DD3).
  - `NO_HOSTS` exists, and the client's `allowed()` accepts `NarrowAnyWhenEmpty`.
  - Every agent response carries `notices: [{kind: "tool_override_narrowed", tool, field, field_title, dropped, effective, message}]`. Path values are stored strings, and the "was any host" case has `dropped: []`.
  - The save path returns 422 `detail: [{type: "tool_override", loc: ["tool_overrides", tool, field], msg}]`, plus `loc ["tool_overrides", tool]` for an unknown tool.
  - The render predicate is `the_one/tools/override_validation.py::agent_tab_renders`.
- **Interim behaviour this leg removes** (flight log, leg 2): the tab sends every shown field, inherited ones included. So lowering only a maximum below the app-wide default now gets a cross-field 422 ("Default timeout can't be higher than Maximum timeout"), and four agent-tab browser files seed an app-wide value to avoid it. Once the walk stores own fields only, an inherited default is not sent, and the resolver's default-follows-max applies (DD2).
- **Not in this leg:** the `App.ui.tabs` and list-row indicators, the tool-panel header flag, the drawer group, the impact route and the Settings warning (leg 5 `notice-surfaces`); the DD14 docs pass and release notes (leg 5).
- **Baseline:** the flight log's list. Legs 1-3 and the drawer fix are uncommitted in this tree and are part of this leg's base.

## Inputs
- `static/js/areas/shared/tool-config-fields.js`:
  - `seedValue` `:91-98` (agent value, else operator value);
  - `readValue` `:181-201` (the chip list returns the union);
  - `invalidMessage` `:205-219` (agent-mode range check against `min`/`max`);
  - `render` `:221+` (agent-mode Narrow integer `max = operatorValue` `:385-391`; the NarrowSuperset chip list with locked operator chips `:423-456`);
  - the handle shape `{el, control, field, value, setValue, setError, setVisible, validate, chips?}`.
- `static/js/areas/studio/tools-tab.js`:
  - `attachOverrides` / `renderFields` `:134-198` (per-tool panel; `operatorConfigs[name].config`; `agentOverride`; the `data-tool-override-dead` flag);
  - `enabledSetFor` `:93-107`;
  - `setAgent` `:334-353`.
- `static/js/areas/studio/agent-form-data.js`:
  - the `tool_overrides` walk `:205-257` (stores every non-empty rendered field; carries unopened tools and hidden keys; drops dead keys);
  - `blockingError` `:334-349`.
- `static/js/areas/studio/agent-editor-controller.js::onSaveError_` `:89-96` (`App.api.fieldErrors(err, ['name'])` only).
- `static/js/api.js::fieldErrors` `:105-109` (single-segment `loc` matching).
- `the_one/interfaces/web/api.py::get_config` `:649-665`.
- `the_one/platform/sandbox/factory.py`: `_select` `:145-163`, `describe_selection` `:166+`, and the blocking userns probe it caches.
- `app.js:198-229`: boots `App.config` from `/api/config`; the fallback `{dev_mode: false, version: 'unknown'}`.
- `the_one/interfaces/web/app.py:305-315`: `repair_unsafe_names` in the lifespan, guarded, never blocking startup.
- `the_one/db/name_repair.py`: the precedent for a guarded startup repair.
- `AppMetadataRepository` (kv); `SQLiteAgentStore` (encrypted round trip); `ToolConfigRepository.list()` / `merged_config()`.

## Outputs
- **Field state** in agent mode (`tool-config-fields.js` + `tools-tab.js`):
  - A field is **own** when its key is in the stored override, **inherited** otherwise.
  - The state is on the control as `data-tool-override-state="own" | "inherited"` and in visible text: "Inherited from Settings" or "This agent's own".
  - Editing a field makes it own.
  - An own field has a **Reset** button (`data-testid="tool-override-reset"`, accessible name "Reset {title} to inherited"). Reset restores the app-wide value and the inherited state, marks the form dirty and moves focus to the field's control.
- **The Save walk** stores own fields only:
  - A NarrowSuperset list stores the chips minus the locked operator chips; if nothing is left, the key is dropped.
  - Clearing an own list returns it to inherited (as today).
  - Hidden keys are carried and dead keys are dropped, as today.
- **The clipped-field line**, from `agent.notices` for that tool and field:
  - Text: "Narrowed by the app-wide setting: {dropped} no longer applies." For the "was any host" case, the notice's own message.
  - **Use narrowed value** (`data-testid="tool-override-use-narrowed"`) sets the field's value to `effective` and makes it own.
  - **Reset to inherited** returns it to inherited.
  - When `effective` is empty or `[NO_HOSTS]`, only Reset is offered, plus "or turn this tool off for this agent".
  - `NO_HOSTS` never renders as an editable chip: the field shows "No hosts" text.
- **Range exemption:** `invalidMessage` / `blockingError` skip the agent-override range check for an own number whose value equals its stored value, so an unchanged own value above a since-lowered app-wide max never blocks Save.
- **The 422 mapping:** `onSaveError_` maps a `["tool_overrides", tool, field]` (or `[..., tool]`) detail. It selects the Built-in tools tab, opens that tool's panel, waits for its fields, and calls the field handle's `setError(msg)` with focus on the control. Other text stays in the header.
- **`GET /api/config` gains `execution_sandbox: "bubblewrap" | "passthrough"`:**
  - The value is cached **on `app.state.execution_sandbox`, never in a module-level variable**. The factory deliberately re-evaluates the selection on every call so tests can monkeypatch it (`factory.py` docstring), and a module cache would go stale across tests that share a process. Each app instance starts empty.
  - The lifespan starts a fire-and-forget task that runs `asyncio.to_thread(describe_selection)` and stores the name. It is never awaited, so startup never waits on the probe, which can take up to 5 s.
  - The route reads `request.app.state.execution_sandbox`. When it is still unset, it calls `asyncio.to_thread(describe_selection)` itself, so the loop is never blocked.
  - `App.config`'s fallback (`app.js`) does **not** gain the key: a failed `/api/config` must not guess a posture.
- **The paths note** on every Allowed paths and Denied paths field of the tab:
  - It appears when the agent's enabled set includes `shell`, `python_exec`, `shell_session_start` or `download_file` and that tool is enabled app-wide (`operatorConfigs[name].enabled`; a tool with no row is enabled).
  - It carries DD10's wording for the posture, read from `App.config.execution_sandbox`, and shows nothing unless that is exactly `'bubblewrap'` or `'passthrough'`.
  - It is re-evaluated on the agent's tool toggle **and** on `setAgent` (which brings a refreshed `operatorConfigs`).
- **Library controls** (named here so no new control is needed): the state text is the field's `App.ui.field` hint (`setHint`, `hintTestid: "tool-override-state"`). Reset, Use narrowed value and the clipped line's buttons are `App.ui.button` (ghost, small). The clipped-field line and the paths note are each an `App.ui.status` row in the field row, with a warning tone for the clipped line and a neutral tone for the note. All of it is built in `tool-config-fields.js`'s agent mode, and admin mode is unchanged. If one of these turns out to need a library option, add it with its catalogue row and its Chromium and WebKit contract test (`tests/test_ui_control_inventory.py`) and report it.
- **The cleanup:**
  - It lives in `the_one/db/override_cleanup.py::cleanup_copied_overrides(conn, agent_store, tool_repo, meta_repo)`.
  - It is called in the lifespan right after `repair_unsafe_names`, inside its own guard.
  - It runs once ever, behind `app_metadata` key `tool_override_cleanup_v1`, written in a `finally` once the agent loop has started.
  - A failure before the loop starts (listing agents, reading tool configs) writes **no** marker, so the next start retries. That is safe, because nothing was changed yet.
  - It applies DD13's four rules and saves through `SQLiteAgentStore`.
  - It logs per-agent failures by name and never raises.
- **Tests** (below), and the existing pins the flight lists, updated.
- **Release-notes lines** go into the flight log's "Release notes to carry":
  - the tab now stores only what you change;
  - the cleanup, and its stale-copy limitation.

## Acceptance Criteria
- [ ] **AC1 — open-and-save stores nothing, and open-and-close stays clean.**
  - Opening every tool's panel on an agent with no overrides leaves Save disabled and the editor clean (no `editor-unsaved`, no leave-guard prompt).
  - Saving with no field changed stores no `tool_overrides` entry for any tool, confirmed by API read-back.
  - The same holds for an agent with own fields: they read back exactly as before.
- [ ] **AC2 — inherited, own, Reset.**
  - An inherited field shows "Inherited from Settings" and the app-wide value.
  - Editing makes it "This agent's own" and stores it, even when the value equals the app-wide one (the pinning decision).
  - Reset returns it to inherited, and Save then removes the key (read-back).
  - The state is in text, not colour only.
  - Reset has an accessible name and moves focus to the field.
- [ ] **AC3 — denied lists store additions only.** Adding one chip to a NarrowSuperset field stores exactly that chip (read-back), not the locked operator chips. Removing the agent's only added chip returns the field to inherited.
- [ ] **AC4 — lowering only a max works.** On an agent whose app-wide default (30) is above a new own max (10), setting only Maximum timeout to 10 and saving succeeds. The stored entry has `timeout_seconds_max` only, and the effective default follows the max (DD2). The four test files that leg 2 seeded around this case drop that workaround where it existed only for this reason.
- [ ] **AC5 — the clipped-field line and its fixes.** With a notice on a field:
  - the line shows the dropped values;
  - **Use narrowed value** stores `effective` as the field's own value (read-back), and the notice clears on the next agent read;
  - **Reset to inherited** removes the key (read-back), and the notice clears.
  - For an empty or `[NO_HOSTS]` effective value, only Reset and the "turn this tool off" text appear, and no `NO_HOSTS` chip is editable.
  - After a fix is clicked and before Save, the line is hidden, and a panel re-render does not bring it back: the line is drawn from the field handle's state, shown only while the field still holds its loaded stored value.
  - Cancel restores it.
  - A notice for a tool whose panel is opened only after the agent loaded shows its line when the panel opens.
- [ ] **AC6 — an unchanged own number never blocks Save.** An own Maximum timeout of 60, after the app-wide max is lowered to 30, does not block saving an unrelated field (for example the description). Editing that number to 45 is blocked with the range message.
- [ ] **AC7 — a 422 lands on the field.**
  - Saving read_file with Allowed paths `/opt/outside-sortie07` against an app-wide `~` (the tab accepts it; the server refuses it) selects the Built-in tools tab, opens read_file's panel, shows the server's sentence on that field with focus on it, and saves nothing.
  - A 422 on a tool whose panel was never opened in this mount does the same, through `openTool`.
  - An unknown-tool 422 (`loc ["tool_overrides", tool]`, no panel) shows its sentence in the editor header.
- [ ] **AC8 — `execution_sandbox`.**
  - `GET /api/config` returns `execution_sandbox`, `"bubblewrap"` or `"passthrough"`, from the selection monkeypatched both ways before the app starts (never the host's own).
  - Two app instances in one process with different monkeypatched selections each report their own value (no stale cache).
  - The lifespan warm-up runs `describe_selection` through `asyncio.to_thread` (asserted).
  - A request before the warm-up finishes does not call it on the loop thread (asserted).
- [ ] **AC9 — the paths note.**
  - With `shell` enabled for the agent and app-wide, every Allowed paths and Denied paths field shows the bubblewrap wording under `App.config.execution_sandbox = 'bubblewrap'` and the passthrough wording under `'passthrough'`, pinned client-side by stubbing `App.config` before the editor renders.
  - With Shell, Python, shell sessions and downloads all off for the agent, or the enabled one off app-wide, no note shows.
  - With `App.config.execution_sandbox` absent or any other value, no note shows.
- [ ] **AC10 — the cleanup.**
  - On first start it applies DD13's rules: it drops fields equal to the effective app-wide value, strips app-wide entries from denied lists, drops dead keys and emptied tool entries. Encrypted fields round-trip.
  - The marker is written after a run with an injected per-agent failure; that agent is logged by name and keeps its values.
  - The marker is also written after an injected failure partway through the agent loop.
  - An injected failure before the loop (listing agents, reading tool configs) writes no marker, and the next start runs the cleanup.
  - A second start changes nothing, and a later deliberate own value equal to the app-wide value survives it.
  - A failure injected at each call site never stops startup.
  - No existing test relies on an override equal to the defaults surviving startup (`copy_template` pre-seeds; grep and say).
- [ ] **AC11 — no regressions.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` shows only the baseline failures.
  - The `agent-tabs`, `agents`, `settings-tools` and `chats` lanes show only baseline failures.
  - The static JS guards pass, and ruff check and format are clean.
  - The flight's listed re-pins are made: `test_flow_studio_tool_overrides_preserved.py` and `test_flow_studio_tools_fields.py` re-pinned to additions-only.

## Verification Steps
- AC1-AC7, AC9: `agent-tabs`-lane browser tests in new or existing `tests/browser/test_flow_studio_tool_override*` / `test_flow_studio_tools_*` files. These match the lane's globs: check with `bash scripts/run-tests.sh --lane agent-tabs --list`. Reach rows through `_lists.py` / `_nav.py`, never raw hashes. Run them with `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser <files> -x`.
- AC8: a unit test over `get_config` and the lifespan warm-up, with `describe_selection` monkeypatched.
- AC10: new `tests/test_override_cleanup.py`, with the database from `tests/_schema_template.py`.
- AC11: `THE_ONE_TEST_NETNS=1 make test-unit`; the four lanes one at a time; the static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`); ruff. `tests/test_ui_ownership.py` and `tests/test_ui_emitted_classes.py` must stay green: new UI is built from `App.ui` controls (`ui.button`, `ui.status`, `ui.notice` or the `field` hint slot), with no owned class used outside `js/ui/` and no HTML-string sink.

## Implementation Guidance

1. **Server first:**
   - Add `execution_sandbox` and the lifespan warm-up, with its unit test.
   - Add the cleanup module, its lifespan call and its tests (including the template-database pre-seed grep).
   - These are independent of the UI work.
2. **Field state in `tool-config-fields.js`:**
   - In agent mode, `render` takes `opts.own` (key present) and `opts.storedValue`, and keeps `own` on the handle.
   - Any input or change sets own.
   - The handle gains `isOwn()`, `reset()` (sets the operator value, clears own) and `ownValue()`. For a NarrowSuperset list, `ownValue()` is the value minus the locked chips.
   - Mark the control with `data-tool-override-state`.
   - The visible state text and the Reset button come from library controls in the row (no new owned classes in an area module). If a small library option is genuinely needed, for example a field `hint` slot, add it with its catalogue row and contract test, or reuse an existing one.
3. **`tools-tab.js`:**
   - **The handle API:** `renderToolsTab`'s returned handle (stored as `h.toolsTab`, `agent-editor.js:299`) gains:
     - `fieldHandles() -> {tool: {field: handle}}`, covering loaded panels only;
     - `openTool(name) -> Promise<void>`, which opens the row and resolves after that panel's `renderFields` (or rejects on a schema-load failure).
     `attachOverrides` keeps its `st.fields` per tool and exposes them through these.
   - Pass `own` and `storedValue` per field.
   - Render the clipped-field line from `currentAgent.notices` filtered to the tool and field.
   - Render the paths note from `enabledSetFor(currentAgent)` plus the app-wide enabled flags (`operatorConfigs[name].enabled`) and `App.config.execution_sandbox`.
   - Re-render the note when a tool's agent toggle changes.
4. **The Save walk in `agent-form-data.js`:**
   - Store `handle.ownValue()` for own fields only.
   - The walk reaches the handles through the editor's current `h.toolsTab.fieldHandles()`, passed into `agent-form-data.js` the way the controller already passes its other context. Do not re-derive state from the DOM text.
   - A rendered override control with no handle (it should not happen) is skipped, with a console warning.
   - **Clean when unchanged:** after the carry rules, omit `tool_overrides` from the payload when the result deep-equals the stored map. Opening a panel then no longer changes `collectFormData()`, and so not `getFormSnapshot()` either.
   - Reset and the fix buttons call the field's `onChange`, and `checkDirty` decides, so a Reset back to the loaded state reads clean.
   - A "No hosts" field's `ownValue()` is the stored `[NO_HOSTS]` only when the operator chose Use narrowed value. That button is never offered for `[NO_HOSTS]`, so in practice such a field is inherited or Reset.
   - Keep the squawk 0223 carry rules (unopened tools, hidden keys, dead keys).
   - `blockingError` skips the range check for an own number equal to its stored value.
5. **The 422 mapping** in `agent-editor-controller.js`:
   - Parse `err.detail` entries of type `tool_override` directly (`App.api.fieldErrors` matches single segments only).
   - Select the tab through the tab handle, open the panel (through the panel's own open path, so its schema loads), then set the error and focus.
   - Other entries keep today's path.
6. **Existing tests:**
   - Update the flight's listed pins.
   - Undo the leg 2 workaround seeding where AC4 makes it unnecessary.
   - Grep `tests/browser/` for `tool_overrides` read-back assertions that expected the copied inherited values.

## Edge Cases
- **A field the operator types back to the app-wide value** stays own: the pinning decision is "edited = own until Reset".
- **A NarrowSuperset field whose stored value is a legacy full union:** before the cleanup has run it is own with the union. The locked chips subtract on Save, so the next Save stores only the additions.
- **The note's "enabled app-wide":** a tool with no tool-config row is enabled by default.
- **`App.config.execution_sandbox` missing** (an old server, or the fallback): no note. The UI never guesses the posture from the browser OS.
- **A notice for a tool whose panel is not open:** the line renders when the panel opens. The tab and panel indicators are leg 5's.
- **The cleanup on a fresh test instance:** it runs and writes the marker. Tests that seed overrides through the API after startup are unaffected, but seeds written before startup (`copy_template`) would be cleaned; check that none rely on that.

## Files Affected
- `the_one/interfaces/web/api.py` — `get_config`
- `the_one/interfaces/web/app.py` — the lifespan warm-up and the cleanup call
- New `the_one/db/override_cleanup.py`
- (`app.js` is unchanged: the `App.config` fallback gains no key)
- `static/js/areas/shared/tool-config-fields.js`, `static/js/areas/studio/tools-tab.js`, `agent-form-data.js`, `agent-editor-controller.js`
- Tests: new `tests/test_override_cleanup.py`; a `get_config` unit test; new and updated `agent-tabs` browser tests; the re-pins
- The flight log: the release-notes lines

### Citation Audit
Checked by the Flight Director against the worktree (base `628a97dd` plus legs 1-2 and the drawer fix uncommitted; leg 3 in progress touches only the web transport), 2026-10-31:
- `tool-config-fields.js:76-98,181-219,385-391,423-456`
- `tools-tab.js:93-107,134-198,334-353`
- `agent-form-data.js:205-257,334-349`
- `agent-editor-controller.js:89-96`
- `api.py:649-665` (`get_config`; it moved from `:602` since the start-of-execution re-check)
- `factory.py:145-180`
- `app.js:198-229`
- `app.py:305-315`

`api.js:105-109` was verified at planning and is unchanged.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

# Flight Log: MCP arguments as rows

**Flight**: [MCP arguments as rows](flight.md)

## Summary
Landed on 2026-11-17, the day it was planned. Three legs, all `completed`: `control-row-moves` (the table and field controls), `arguments-rows` (the MCP editor's Arguments block) and `hat-and-alignment` (ten steps walked by the operator, all passed, one accessible-name fix made and reviewed). Two commits on `sortie/18-mcp-arguments-as-rows`: the two build legs after two review cycles, an accessibility review, the unit tier and the full browser gate; then the HAT fix after its own lanes, a review and an accessibility review. Carried out of the flight: squawks 0375 (the agent Tools tab's Add buttons share one name) and 0376 (the `mcp` lane sits at its time budget), and two cosmetic comment lines. The flight debrief is the next step.

---

## Leg Progress

### Flight Director Notes

#### 2026-11-17 — execution start
- Phase file `.flightops/agent-crews/leg-execution.md` loaded and valid (Crew, Interaction Protocol, Prompts).
- Branch `sortie/18-mcp-arguments-as-rows` created from `main` at `f635e039` (squawk 0371's merge). Flight status `ready` → `in-flight`.
- Three legs: `control-row-moves` and `arguments-rows` (autonomous), then `hat-and-alignment` (optional, interactive; the operator asked for it).

#### 2026-11-17 — leg 1 designed, tiered high-risk
`legs/01-control-row-moves.md` written. **Risk tier: high, a Developer design review runs before implementation.** Rationale: it changes two shared controls that have existing consumers (`App.ui.keyValueTable` has four; `App.ui.field` is used by every editor), which is the shared-interface trigger, even though each addition is inert when not passed.
- Interface check: no existing symbol changes shape. The table's controller gains `focus()`; nothing reads the controller's key list except its own contract tests (the leg greps for pins).
- Reachability check: the edge-state rule lives in `renumber()` because `applyRowState` returns early with no lock option; the move's focus rule is explicit because WebKit does not focus a clicked button.
- The leg runs the consumers' lanes (`mcp`, `library`, `agent-tabs`) as well as the contract lanes, since the claim is "inert for existing consumers".

#### 2026-11-17 — leg 1 design review, one cycle
Developer design review (Sonnet): approve with changes; six medium and five low issues, no high. All folded into the leg, which is now `ready`:
- Field group mode: the hint's and the error's insertion points need their own branch (today's `setHint` would put the hint after the group element); the own-label check and the id assignment are skipped; `wire()` stays the one writer of `aria-describedby` through a describedby target and an invalid target.
- Test technique written into Verification: the disabled-click test dispatches the click itself (a Playwright click would wait for the button to enable); the focus test covers mouse and keyboard and both outcomes; the status test uses a `MutationObserver` to see the emptying. Falsification names the engine, because two of the mechanisms only matter in WebKit.
- Small additions: move names refresh on typing in the key column; the status node is not built for `readOnly`; `movable` with a lock option throws even under `readOnly`; the hidden header is also measured at the first body row; the move buttons join the remove button's CSS selector lists, the 16px icon rule included.
- No second review cycle: every change is the reviewer's own fix and none alters the leg's scope. Developer spawned on Sonnet with the "Implement" prompt.

#### 2026-11-17 — leg 1 landed
`[LAND:leg]` received for `control-row-moves`; nothing committed. Reported: the six guard files 428 passed; `--lane contracts` with WebKit required 2415 passed, 7 skipped; `mcp` 89, `library` 122, `agent-tabs` 208 passed.
- Accepted as built: one extra owned class, `ui-kv-center--actions` (the actions row's gap and no-wrap), listed in the catalogue; the actions column is 104px when `movable`.
- Falsification: AC3 and AC6 failed without their mechanism in both engines. AC5's test could not be failed by removing the disabled-click guard alone, because the move also stops at the list's bounds; with both checks removed it fails in both engines. The test therefore pins the behaviour (a click on a disabled move button changes nothing), not that one line. Accepted: the behaviour is what the criterion asks for. Left for the flight Reviewer to weigh.

#### 2026-11-17 — leg 2 designed, tiered low-risk
`legs/02-arguments-rows.md` is `ready`. **Risk tier: low, no per-leg design review.** Rationale: one area module (`mcp-connection-fields.js`) and its tests, on control options that now exist and are pinned; no shared interface, schema, lifecycle or cache change; the module's `values()` has one consumer (`mcp-server-editor.js`), which is expected to need no change. The leg's decisions (DD5 to DD8) were checked against this code by the Architect with file and line. The flight-end Reviewer and the Accessibility Reviewer cover the result.
- Reachability check: after a Save the controller re-sets the fields from the server's row when the values are unchanged since the click, so blank rows disappear on Save (AC8); `setValues` on the table fires no change event, and the controller recomputes dirty after a Cancel on its own, so nothing depends on the chip list's old "Cancel fires onChange" behaviour.
- Tests the design breaks are named for rewrite, not deletion (AC14). The controller parity tests must stay green with their seeds unchanged (AC10).
- The leg may not touch `js/ui/*`; a missing control capability is a stop-and-report.
- Developer spawned on Sonnet with the "Implement" prompt.

#### 2026-11-17 — leg 2 landed; flight review started
`[LAND:leg]` received for `arguments-rows`; nothing committed. Reported: guards 530 passed; `mcp` 104, `mcp-connection` 95, `shared` 364 passed; unit tier 10222 passed, 15 skipped (the expected count under the loopback namespace). `mcp-server-editor.js` needed no change. Both falsifications succeeded.
- Two items the Developer left because they were outside the leg's files; both belong to this flight and go into the review's fix pass, not into squawks:
  1. `ruff format --check` flags leg 1's two contract test files (CI runs the format check).
  2. `scripts/ui_capture.py`'s `mcp-edit-dirty` surface still types into the old chip input's selector; with rows it overwrites the first argument where it used to add one. The surface stays dirty but no longer does what its description says.
- Reviewer (Haiku tier: the diff touches no security-sensitive surface) and Accessibility Reviewer (Sonnet) spawned in parallel on the whole uncommitted diff. Only the Reviewer runs tests, so two runs never overlap on the host.

#### 2026-11-17 — flight review, two cycles
- **Accessibility Reviewer (Sonnet): `[HANDOFF:confirmed]`, no blocking issue.** By code and token reading only; the rendered accessibility tree was not inspected, and where focus lands after a Save or Cancel re-sets the rows was not traced (a HAT item). One non-blocking recommendation, held for the HAT as the operator's call because it needs one more option on the shared table control: give the Arguments "+ Add row" button an accessible name that contains its visible label (for example "Add row to Arguments"), since the editor now has two buttons with that label and a voice-control user gets an ambiguous target. Noted for information: the move and remove buttons are 24px, which meets WCAG 2.2's 2.5.8 exactly.
- **Reviewer, cycle 1 (Haiku): not confirmed.** It went through leg 1's 21 and leg 2's 18 criteria and found them met, with one blocking issue (the `ruff format` gate failed on leg 1's two contract files) and non-blocking ones: the stale `scripts/ui_capture.py` surface, three missing contract assertions (AC2 names after add, remove and move; AC3 edge state after add and remove; AC9 `fill` on an already-fixed table), and two over-long comment lines. It re-ran the guards (530 passed), the two contract files in both engines (325 passed, 1 skipped) and the `mcp` lane (104 passed).
- **Fix pass (Developer, Sonnet):** all four fixed; see "Review fixes" under `arguments-rows`. The new assertions exposed no defect in the control.
- **Reviewer, cycle 2 (Haiku, a fresh agent): `[HANDOFF:confirmed]`.** Lint pair clean (917 files); the table contract file 172 passed in both engines; guards 455 passed; both formatted files' diffs are additions only; no falsification leftover in `key-value-table.js`.
- **Accepted, not changed:** the `disabled` return in the move click handler is redundant with the move's bounds check (both stay; the test pins the behaviour); the args-specific chip key tests and ellipsis assertion went with the chip list.
- **Closing browser gate** started after cycle 2 (`--parallel 3`, WebKit required, start load about 3, so its lane times are not budget readings). The commit waits for its result.
- **Closing browser gate result: `PARALLEL_RESULT rc=0 total=2240s lanes=20 failed=-`.** All twenty lanes exited 0. With the unit tier run after the last source change (10222 passed, 15 skipped), the reviewed tree is gated; legs 1 and 2 are marked `completed` and committed as the first commit of the branch, before the HAT fix. One lane printed `OVER BUDGET`: `mcp` at 331 s against 330 s. That is a loaded-host reading (start load about 3, about 7 during the run, with the HAT instance up), so by the quiet-host rule it is not a budget reading; the lane gained thirteen flow tests in leg 2 and the Architect predicted it would sit at its budget. Carried as a squawk: re-measure `mcp` on a quiet `--parallel 3` run and re-budget there.
- **HAT started at the operator's request while the gate was still running** (2026-11-17). `legs/03-hat-and-alignment.md` written. Scratch instance on port 8485 with its own data directory and working directory under the home folder, dev mode on, two seeded local-command servers (`filesystem` with four stored arguments, `no-args` with none). Rule for the overlap: no source edit while the gate runs, because the browser lanes serve static files from this working tree; a fix the operator asks for waits for the gate to end.
- **Deferred, cosmetic:** one re-wrapped comment line in `js/ui/chip-list.js` is still 105 characters; one comment line break in `mcp-connection-fields.js` reads awkwardly. Neither is gated. Fix with the next edit of those files.

### control-row-moves

**Status**: completed
**Started**: 2026-11-17
**Completed**: 2026-11-17

#### Changes Made
- `js/ui/key-value-table.js`: `movable` (+ `moveUpTestid`, `moveDownTestid`, `moveLabel`), `fill`, `headHidden`, `focus()`; move buttons built in `newRow`, names and edge state owned by `renumber()` (`nameMoves`), the move swaps the neighbour's `tr`, explicit focus, status node `.ui-kv-live` with a timer cancelled in `destroy`; header comment updated.
- `js/ui/field.js`: group mode (`group`), describedby and invalid targets, hint after the caption; header comment updated.
- `css/components.css`: `.ui-kv-move` (joined to the remove button's box and 16px icon rules), `.ui-kv-center--actions`, `.ui-kv-live`, `.ui-kv-table--head-hidden`, `.field-group-caption` joined to the label rule.
- `docs/ui-control-inventory.md`: the two rows. `tests/browser/test_ui_key_value_table_contract.py` and `test_ui_library_contract.py`: new contract tests.

#### Verification
- Guards (inventory, ownership, emitted classes, ui_guards, token definitions, a11y): 428 passed.
- `--lane contracts` with `THE_ONE_REQUIRE_WEBKIT=1`: 2415 passed, 7 skipped. Lanes `mcp` 89 passed, `library` 122 passed, `agent-tabs` 208 passed.
- Falsification (each failed with its mechanism edited out, passed with it back): AC3 edge state (`disabled` assignment removed): yes, chromium and webkit. AC6 focus (`target.focus()` removed): yes, chromium and webkit, all of mouse, Enter, Space. AC5 disabled-click guard: removing only the `mv.disabled` check does NOT fail the test in either engine, because `moveRow` also returns at the bounds; with the guard and the bounds check both removed it fails in chromium and webkit.

#### Deviations / decisions
- Added owned class `ui-kv-center--actions` (actions row gap, no wrap); listed in the catalogue row.
- Actions column is 104px when movable (three 24px buttons, two 4px gaps, 16px padding); AC10 test passes in both engines.
- The AC5 guard is redundant with the bounds check in `moveRow` (defence in depth, both kept); the AC5 test therefore pins the behaviour, not the guard alone.

### arguments-rows

**Status**: completed
**Started**: 2026-11-17
**Completed**: 2026-11-17

#### Changes Made
- `js/areas/studio/mcp-connection-fields.js`: the Arguments chip list became a group-mode `App.ui.field` (`mcp-args-field`, `data-field="args"`, `mcp-stdio-only`) around a one-column movable, fill, headHidden `App.ui.keyValueTable` with the nine `mcp-args-*` testids; one module-level `collectArgs` (trim, drop blanks, keep order and repeats) is used by `values().args` and `baselineFrom` (the `uniqueStrings` call is gone from there only); `setValues` shows stored args as stored; `focus('args')` is `table.focus()`; header comment rewritten. `mcp-server-editor.js` needed NO change.
- `js/ui/chip-list.js`: header comment only (users list).
- Tests: row helpers `ARGS_ROWS`, `ARGS_INPUTS`, `args_add`, `args_values`, `args_click` in `tests/browser/_mcp_editor.py`; `test_flow_studio_mcp_editor_fields.py` (pinned tests rewritten on rows; the chip-key test is now writable paths only; the long-value test also checks the row stays in the block; 13 new tests for AC1-AC13); `test_flow_studio_mcp_editor_kv_chips.py` (`_add_chip` refuses `args`; the defect-7 test keeps writable paths and gains `test_argument_row_edit_after_cancel_is_tracked_as_dirty`); `test_flow_chiplist_label_resolver.py` (mf-args half removed, asserts no `#mf-args` and no chip list in the args field). `test_flow_studio_mcp_editor_controller.py` untouched and green.
- Docs: `docs/ui-testid-registry.md` (nine rows), `docs/ui-control-inventory.md` (chip list row users), `tests/_ui_guard_helpers.py` (comment), `the_one/agents.md` (leg 1 control options paragraph in "Control library"; "MCP Arguments as rows" paragraph in the MCP editor notes). `CLAUDE.md`: grepped, no statement about the arguments chip list, unchanged.

#### Verification
- Guards (inventory, ownership, emitted classes, ui_guards, token definitions, a11y, nav helper, run_tests_lanes): 530 passed. The three edited browser files: 91 passed.
- Lanes (`THE_ONE_TEST_NETNS=1`): `mcp` 104 passed, `mcp-connection` 95 passed, `shared` 364 passed. `THE_ONE_TEST_NETNS=1 make test-unit`: 10222 passed, 15 skipped (the netns count).
- Falsification: repeats test (`test_args_save_keeps_order_and_repeats`) failed with a de-duplicating collect: yes. Blank-row tests (`test_args_unsaved_marker_tracks_the_collected_list` and `test_args_save_trims_ends_and_drops_blank_rows`) failed with blanks kept in the collected list: yes. Both fixes put back by editing.
- Captures (`mcp-edit-stdio`, light and dark, 1280 and 1024, outside the repo): rows are full width, no header row, the hint sits between the caption and the rows, up, down and remove sit on one line at the row end; the 90-character argument stays in its input; no layout difference between themes.
- `data-field-type="array"` on args: no reader (the only readers are tool-config-fields on tool fields, and the chip-list contract test); not carried over.
- AC13: a stubbed PUT 422 with `loc ["body","config","args"]` was used (no real server response names `args`).

#### Deviations / decisions
- None from the leg. `ruff format --check tests/browser` reports leg 1's two contract files (`test_ui_key_value_table_contract.py`, `test_ui_library_contract.py`) as needing reformatting; not touched (leg 1's, out of scope here).
- Anomaly for a squawk: `scripts/ui_capture.py::_mcp_dirty` (surface `mcp-edit-dirty`) types into `[data-field=args] .chip-list-input, [data-field=args] input` then presses Enter; with rows it now overwrites the first row's value with `--verbose` instead of adding an argument (still dirty, but no longer "one argument added"). Not changed here (outside the leg's files).

#### Review fixes (2026-11-17)
- Lint: ran `ruff format` on `tests/browser/test_ui_key_value_table_contract.py` and `test_ui_library_contract.py` (reflow only); `ruff check` and `ruff format --check` over `the_one/ tests/ scripts/ evals/` are clean (917 files).
- `scripts/ui_capture.py::_mcp_dirty` now clicks the Arguments Add row button and types `--verbose` into the new last row. Captures of `mcp-edit-dirty` (light) show a fifth argument row `--verbose`, "Unsaved changes" and an enabled Save; `mcp-edit-stdio` (dark, 1280) shows four rows, Save disabled, nothing else moved.
- Contract tests added in `test_ui_key_value_table_contract.py`: `test_names_and_edge_state_follow_add_remove_and_move` (AC2 names and AC3 edge state after add, remove, move) and `test_fill_on_an_already_fixed_table_changes_nothing` (AC9, toggle and secret tables). Falsified: edge-state assignment broken (both fail), `fill` branch changed to `fixed = !fixed` (fill test fails), name refresh made conditional in `nameMoves` (names test fails); each put back by editing. No control defect found.
- Comment re-wraps in `mcp-connection-fields.js` and `chip-list.js` (comment text only).

---

### hat-and-alignment

**Status**: completed
**Started**: 2026-11-17
**Completed**: 2026-11-17

#### The walk (operator, scratch instance on port 8485)
| Step | Result |
|---|---|
| 1. Existing server, clean | pass |
| 2. Edits and the unsaved caption (a blank added row is not a change) | pass |
| 3. Moving rows, edge buttons, focus after a move | pass |
| 4. Save with repeats, a comma, outer spaces and a blank row; reload | pass. The stored `config.args` read back by the Flight Director matched: the implicit `-y`, the three original arguments, then `--flag`, `a`, `--flag`, `a`, `--allow=a,b`, `--trim-me` |
| 5. Cancel after an edit, a move and a remove | pass |
| 6. Server with no arguments; new server | pass |
| 7. Type switched to HTTP and back keeps the rows | pass |
| 8. Long argument, the other theme, narrow window, hover | pass. The operator first reported no hover state, then corrected it: the arrows brighten and the trash can turns red, as designed. No change. |
| 9. Environment variables and one other table unchanged | pass |
| 10. Open choices | see below |

#### Operator decisions
1. A server with no arguments keeps just the "+ Add row" button (no blank starting row).
2. Trimming the ends on Save stays.
3. **The Arguments "+ Add row" button gets the accessible name "Add row to Arguments" in this sortie** (the visible label does not change).
4. Focus after Save and after Cancel: nothing felt wrong; no change.

#### Fix-or-feature call for decision 3
An accessible-name fix, not a feature: nothing a sighted mouse user sees or does changes. **Multi-surface**, because the shared table control must gain an option to carry the name, so a Developer design-review pass runs before it is built, and the Accessibility Reviewer and a Reviewer see the result. No source edit until the closing gate that is still running has finished (the browser lanes serve static files from this tree).

Fix brief:
- `App.ui.keyValueTable` gains `addAriaLabel` (a string): when given, the Add button's `aria-label` is that string and its visible label is unchanged; when absent, nothing changes (no attribute). Documented in the control's header comment and catalogue row; pinned by a contract test in both engines, with a not-passed case.
- `mcp-connection-fields.js` passes `addAriaLabel: 'Add row to Arguments'`. A flow test asserts the button's accessible name and that its visible text is still "+ Add row".
- The visible label "+ Add row", every testid and every other name stay as they are.
- Question for the design review: whether the name must also contain the "+" of the visible label to satisfy WCAG 2.5.3 (Label in Name), and whether the Environment variables / Headers table on the same page should get a matching name in the same change or be left alone.

Design review (Developer, Sonnet, by reading only): approve with changes. `App.ui.button` already takes `ariaLabel` beside a visible `label`, and the agent credentials tile is the house precedent for a longer accessible name on a labelled button. No test, script or doc locates an Add row button by its accessible name, so nothing breaks. Flight Director's calls on its two open points:
- **Name: "Add row to Arguments"**, the string the operator approved, without the "+". The reviewer preferred "+ Add row to Arguments" as a literal prefix match but rated the plain form acceptable: the "+" is a symbol with no word meaning, and a screen reader would otherwise say "plus". The catalogue row states the choice.
- **Scope: both tables of the MCP server editor page.** Naming only Arguments would leave the other button on the page as a bare "+ Add row", so "click Add row" would still match two targets and the Environment variables button could not be addressed on its own. The Environment variables / Headers table of this editor therefore gets "Add row to Environment variables" or "Add row to Headers" (following its title) in the same change. This stays inside the page the operator's decision was about.
- **Not in scope:** the agent Tools tab, where each expanded MCP server tile has its own "+ Add row" (`mcp-agent-credentials.js`). That is another page with the same pre-existing ambiguity; it is logged as a squawk, not folded in.
- Added to the brief from the review: the not-passed case asserts there is no `aria-label` attribute at all; `addAriaLabel` is inert under `readOnly` (the button is not built into the page); a click on the named button still adds a row.

#### HAT fix: Add row names (2026-11-17)
- `ui/key-value-table.js`: new option `addAriaLabel`, passed to `App.ui.button` as `ariaLabel` only when a non-empty string (otherwise `null`, so no attribute); documented in the header comment. `mcp-connection-fields.js` passes "Add row to Arguments"; `mcp-env-headers.js` passes `'Add row to ' + titleFor(type)` (the table is rebuilt by `setType` when the title changes, so the name follows). `mcp-agent-credentials.js` untouched.
- Tests: contract `test_add_aria_label_names_the_button_and_is_inert_otherwise` (both engines: name, visible text, click adds and fires `add`, custom `addLabel`, absent and empty give no attribute, `readOnly` builds no button); flow `test_add_row_buttons_have_distinct_accessible_names` in `test_flow_studio_mcp_editor_fields.py` (name and visible text for Arguments and Environment variables, role+name lookups, Headers after Type switch and back, click adds a row).
- Falsified, each put back by editing: Arguments option removed (flow fails), env/headers option removed (flow fails), control change removed (contract fails).
- Docs: catalogue row of the Key-value table, `agents.md` sortie 18 paragraph. No testid change. Grep of `tests/`, `scripts/`, `docs/`, `tests/behavior/` found nothing that locates an Add row button by accessible name.

#### HAT fix review and close (Flight Director, 2026-11-17)
- **Reviewer (Haiku, a fresh agent): `[HANDOFF:confirmed]`, no issue.** The diff is the fix and nothing else (eight files; `mcp-agent-credentials.js` untouched; no testid or visible label changed). It re-ran the table contract file in both engines (174 passed), the editor fields flow file (51 passed), the lint pair (clean, 917 files) and the guards (428 passed). It did not re-run the Developer's falsifications.
- **Accessibility Reviewer (Sonnet): `[HANDOFF:confirmed]`, no blocking issue**, by reading only. On WCAG 2.5.3 it judged "Add row to Arguments" conformant with about 85% confidence (the "+" of the visible label is a symbol, and "Add row" is the name's prefix), and recommended keeping the plain form; "+ Add row to Arguments" would be the zero-doubt string, with "plus" possibly read aloud. The names are distinct, follow a Type switch, and can never end in "to " with nothing after it.
- The Developer's lanes after the fix: `contracts-controls` 1274 passed, 4 skipped; `mcp` 105 (261 s on a quieter host, against 331 s in the loaded gate); `library` 122; `agent-tabs` 208; unit tier 10222 passed, 15 skipped. The full browser gate was not re-run after this fix: the change is one option that is inert when not passed, and the lanes of every consumer of the table were run.
- Squawks logged from the HAT and the gate: 0375 (the agent Tools tab's per-tile Add buttons share one name) and 0376 (re-measure and re-budget the `mcp` lane on a quiet host).
- The second commit was made by the Flight Director directly (a git operation over reviewed changes and artifacts, no source edit), to avoid a crew spawn for it. The first commit was made by a Developer, as the crew file says.
- The scratch instance on port 8485 was stopped by its recorded PID after the commit; its data directory was left in place under the home folder.
- All three legs `completed`; the flight is `landed`. The charter's success criteria are assessed in the flight debrief.

---

## Decisions
Runtime decisions not in original plan.

---

## Deviations
Departures from planned approach.

---

## Anomalies
Unexpected issues encountered.

---

## Session Notes

### 2026-11-17 — planning
- The operator reported the Arguments chip field as confusing and asked for the "Add row" model of Environment variables.
- Qualified as a sortie: one outcome, one cluster of decisions (how an ordered list of strings is entered as rows), one flight, no new subsystem. Not a squawk: it changes behaviour a user sees and adds options to two shared controls.
- Operator decisions, all on 2026-11-17: the charter; Move up and Move down buttons on each row; a row holding several words stays one argument; the rows sit in Connection where the chips are (mockup in the flight artifact); a short closing HAT.
- Found while reading for the report: the chip field drops a repeated argument and splits a value at a comma. Both go away with the rows (DD5, DD6); neither was logged as a separate squawk because this sortie replaces the field.
- Architect design review, one cycle (Opus): approve with changes, six medium and five low issues, no high. Folded in: a full-width layout option and a `focus()` method on the table control (new DD10); the actions column's width, the focus, click-guard, edge-state and announcement mechanics of a move, and a throw for `movable` with the lock options (DD3); the hidden header built from per-cell spans, not a hidden `thead` (DD4); group mode's contract, with the hint after the caption and no `aria-invalid` on the group (DD2); the limit that a stored argument with outer whitespace is trimmed on the next Save (DD7); the `data-field` anchor and the fact that `mf-args` is an id, not a testid (DD8); the missing test pins and lanes (Prerequisites, DD9, Checkpoints). The Architect confirmed the sortie gate still holds: one cluster of decisions, two legs and an optional HAT. No second review cycle was run: the changes are the Architect's own fixes, and each leg gets a Developer design review against the code before it is built.
- The Architect's two questions were settled by the Flight Director: a server with no arguments shows no rows (a HAT item), and group mode is a `div` with `role="group"` (a native `fieldset` is an acceptable variation).
- Planned in the same session as squawk 0371 (branch `squawk/0371-forget-tools-list-returns-armed`, with 0372 to 0374 logged beside it); the sortie artifacts were written while that branch was checked out and are committed on the sortie's own branch.

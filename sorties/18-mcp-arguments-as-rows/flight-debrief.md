# Flight Debrief: MCP arguments as rows

**Date**: 2026-11-17
**Flight**: [MCP arguments as rows](flight.md)
**Status**: landed
**Duration**: 2026-11-17 (charter, mockup, design, three legs, merge, release) - 2026-11-17 (debrief)
**Legs Completed**: 3 of 3
**Plugin version**: mission-control 1.2.4

The sortie's PR (#376) was merged and v0.16.5 was released before this debrief, at the operator's call. The debrief is on its own branch, `sortie/18-debrief`.

## Outcome Assessment

### Objectives Achieved
- A local-command MCP server's arguments are entered one per row, with Move up, Move down and Remove on each row and "+ Add row" under them, in the Connection section where the chip list was.
- Save stores the rows exactly as entered: order kept, repeats kept, a comma or a space inside a value kept. Ends are trimmed and blank rows are dropped.
- The two data-loss defects of the chip list (a repeated argument dropped, a value split at a comma) are gone with it.
- `App.ui.keyValueTable` gained `movable`, `fill`, `headHidden`, `focus()` and `addAriaLabel`; `App.ui.field` gained a group mode. Each is inert when not passed.
- The MCP server editor's two "+ Add row" buttons have distinct accessible names.
- Shipped in v0.16.5 (published 2026-11-18 02:01 UTC, four packages and `SHA256SUMS`).

### Charter Criteria

| Criterion | Result | Note |
|---|---|---|
| Arguments shows one row per argument, with Add row and a remove button per row, matching the look of Environment variables | **Met** | `test_flow_studio_mcp_editor_fields.py::test_args_block_structure_and_names`; HAT steps 1, 8 and 9. Two differences from Environment variables are by design and were approved on the mockup: three buttons per row, and no column header |
| An existing server's arguments load one per row in stored order; the hidden `-y` and `run` stay hidden | **Met** | `::test_args_rows_show_the_stored_display_arguments`, the `npx -y` and `pipx run` round-trip tests; HAT step 1 |
| Save keeps order and repeats; blank rows are dropped | **Met** | `::test_args_save_keeps_order_and_repeats`, `::test_args_save_trims_ends_and_drops_blank_rows`; HAT step 4, with the stored `config.args` read back from the scratch instance |
| Unsaved-changes, Cancel and Test with unsaved changes work as they do today | **Met** | `::test_args_unsaved_marker_tracks_the_collected_list`, `::test_args_test_sends_the_unsaved_rows`, `test_flow_studio_mcp_editor_kv_chips.py::test_argument_row_edit_after_cancel_is_tracked_as_dirty`; HAT steps 2 and 5 |

Constraints: both held. `config.args` and the API are unchanged; the other chip fields are untouched.

Checkpoints: all three met.

Context: the operator's report that started this session had three items. This sortie delivered one (the Arguments rows). Squawk 0371 fixed a confirmed part of the second (the Forget button coming back armed). The operator's actual symptoms for the second and third (the Forget button staying hidden after Test, squawk 0373; the Protocol row staying at 2025-11-25, squawk 0372) are still open and unreproduced.

## What Went Well
- **The mockup settled the look before any code.** The operator approved a clickable board with the spec; the HAT then found nothing to change in the layout.
- **The Architect's design review added what the first draft missed**: `fill` and `focus()` (DD10), the focus, edge-state and click-guard mechanics of a move, and the per-cell hidden header. All were built as written and none was revised.
- **One collect function.** `mcp-connection-fields.js::collectArgs` is behind both `values()` and `baselineFrom`, so the dirty check cannot drift, and `mcp-server-editor.js` needed no change.
- **Risk tiering matched the work.** Leg 1 (two shared controls) was tiered high and its design review found six medium issues before the build. Leg 2 was tiered low and no review found a spec error in it.
- **The independent review earned its cycle.** Cycle 1 caught a failing `ruff format --check` (a CI gate) and three missing contract assertions.
- **The HAT's multi-surface rule fired correctly.** The Add row name needed a new option on the shared table, so it got a design-review pass first; that pass widened the fix to both tables on the page and found the house precedent (`App.ui.button`'s `ariaLabel`).
- **Falsification was done per mechanism and per engine**, and the one case that could not be falsified alone (leg 1's AC5) was reported as such, not hidden.
- **A sortie was the right vehicle**: one outcome, one cluster of decisions, two build legs and a HAT, planned and landed in a day.

## What Could Be Improved

### Process
- **A ticked prerequisite was wrong.** The flight says "`scripts/ui_capture.py` has no selector on the args chips". It had one: `_mcp_dirty` used `[data-field=args] .chip-list-input, [data-field=args] input`. The design's greps looked for `mf-args` and the quoted `data-field="args"`; the script wrote the attribute unquoted. Leg 2's Developer found the stale surface and the review fix pass repaired it. Cost: small (one surface, one fix), but it is the third sortie debrief in a row to record a ticked prerequisite that was not true.
- **The lint pair was not in leg 1's verification.** Leg 1 added two large contract test files and never ran `ruff format --check`. Leg 2's Developer saw it and left it as out of scope; the Reviewer made it blocking.
- **The second "+ Add row" button was foreseen and not decided.** The flight's Technical Approach told the Accessibility Reviewer about it and floated the name "Add row to Arguments", but no design decision covered it. It became a HAT decision, a sixth table option and a change to an existing consumer (`mcp-env-headers.js`).
- **The closing gate overlapped the HAT.** The gate ran at start load about 3 with the HAT instance up, so no lane time from it counts, and source edits had to wait for it.
- **The full browser gate was not re-run after the HAT fix.** The consumers' lanes and the unit tier were. The first full gate on the final tree is this debrief's, after the merge and the release.
- **The Flight Director made the second commit itself.** The crew file gives commits to a Developer. It was a git operation over reviewed changes; recorded in the flight log.
- **The debrief came after the merge and the release.** Its findings cannot join the flight's PR, and its gate could not have stopped the release.

### Technical
- **`App.ui.keyValueTable` is accumulating options.** Six additions in one sortie, five consumers, and implicit exclusion rules checked one by one at construction (`movable` throws with three lock options; `fill` means nothing with a secret or toggle column). The next addition should come with an options-matrix test, or a look at splitting a plain list table from the credential table.
- **Two move implementations.** `rules-notes-tab.js::move` is hand-built; the table now has `movable`. The Rules list is not a table and has no status announcement. Nothing records whether they are meant to stay separate.
- **Two dirty rules on one page.** A blank added Arguments row is not a change (DD6); a blank added Environment variables row is. Accepted and documented; a known divergence, not a defect.
- **DD7's limit has no cue.** A stored argument with outer whitespace or an empty string (possible only through the API) opens clean and is trimmed or dropped on the next Save of any field. The HAT walked trimming on entry, not a stored value of that kind.
- **Group mode is a second behaviour in one factory.** It supports fewer options than normal mode (`info` and `labelHidden` throw). If a third consumer needs a group, weigh a separate control.
- **The 104px actions column is a literal** in `key-value-table.js`, tied to three 24px buttons and two 4px gaps.
- **Not tested**: focus after removing the focused row in a movable table; moving a row that holds a field error inside the real editor (the bare control is covered); a keyboard-only add-then-move flow. AC13 uses a stubbed 422 because no server response names `args`.
- **The rendered accessibility tree was never inspected.** Both accessibility reviews were by reading code and tokens. The Arguments table has no accessible name of its own; the enclosing group names the block.

### Documentation
- **The flight artifact's prerequisite line about `scripts/ui_capture.py` was false**; it now carries a correction note.
- **The Key-value table catalogue row names two consumers** in its location column ("first consumer", "second"); there are five. This predates the sortie.
- Two cosmetic comment lines are still carried: `js/ui/chip-list.js` (one line of 105 characters) and an awkward break in `mcp-connection-fields.js`.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `addAriaLabel` added to the shared table at the HAT, and passed by a second consumer (the Environment variables / Headers table) | Operator decision at HAT step 10; naming only one of two buttons would have left the page ambiguous | Yes: a need the design already predicts gets a design decision |
| One extra owned class, `ui-kv-center--actions`; actions column 104px | Three buttons on one line without wrapping | No (accepted as built) |
| Leg 1's AC5 pins the behaviour, not the guard line | The disabled-click guard is redundant with the move's bounds check | Yes: write criteria as behaviour, and say which mechanisms are to be falsified |
| Lint fix and capture-script fix done in the review fix pass, not in a leg | Both were outside leg 2's files and inside the flight | No (correct handling); the causes are in Process above |
| HAT started while the closing gate ran; no source edit until it ended | Operator asked to begin | No: a gate run needs the host to itself |
| Second commit made by the Flight Director | To avoid a crew spawn for a git operation | No |
| Merged and released before the debrief | Operator's call | No |

## Key Learnings
- **Search for a replaced control's consumers in every spelling.** Id, `data-field` quoted and unquoted, the control's owned classes and its testids, across `tests/`, `scripts/`, `docs/`, `evals/` and `tests/behavior/`. A capture or seed script is a consumer.
- **"Inert when not passed" plus a not-passed contract case** let two shared controls change with five consumers' lanes staying green. Worth keeping as the rule for every new option.
- **An accessibility note in a review brief is an undecided design decision.** Decide it in the design, including the default.
- **On this host a debrief gate rarely gets a quiet window.** Three debriefs running now (sorties 16, 17 and 18) have a browser gate on a loaded host. A budget reading has to be arranged, not hoped for.

### Test metrics
All from the debrief Developer's fresh run on `sortie/18-debrief` at `7717fec8` (the merged sortie plus the version line), loopback namespace, WebKit required. **The host was not quiet at any point**: other sessions were running; no local CI build ran.
- **Unit tier**: 10222 passed, 15 skipped, **1 failed**, 302.4 s (start load about 2.0). The failure, `tests/test_pty_session.py::TestUnixPtySession::test_send_timeout_raises_when_no_output`, passed alone in 1.35 s: a timing flake under load, in code this flight did not touch. The count equals the flight log's 10222; this flight added no unit tests. Prior: sortie 17 debrief 10220 passed, 283.0 s; sortie 16 debrief 10137, 271 s alone. 302 s is over the tier's 300 s standing target, on a loaded host.
- **Browser gate**: `PARALLEL_RESULT rc=1 total=2643s lanes=20 failed=contracts-widget`, start load 1.02, end load 5.29 (5-minute 8.33). The one failure, `tests/browser/test_ui_widget_card_contract.py::test_escape_stops_the_card_and_keeps_the_marking[webkit]` (a 30 s wait timed out), passed in both engines on a re-run of that test: a load flake, in an area this flight did not touch. Nineteen lanes exited 0. Prior: the flight's closing gate `rc=0 total=2240s` (start load about 3); sortie 17 debrief 2349 s (loaded); sortie 16 debrief 2180 s (load 0.95).
- **Lanes**: eleven of twenty printed `OVER BUDGET`, among them lanes this flight did not touch (`agents` 661 s against 630, `agent-tabs` 624 against 600, `chats` 446 against 420, `shared` 457 against 420, `settings` 382 against 360, `agent-routines` 331 against 300). That pattern is load. By the quiet-host rule nothing is re-budgeted.
- **`mcp`** (this flight added about fourteen flow tests): 390 s here, 331 s in the flight's loaded gate, 261 s in the HAT-fix Developer's solo lane run, against a 330 s budget. None is a budget reading. Squawk 0376 still needs a quiet `--parallel 3` run.
- **`contracts-controls`** (this flight added table and field contract tests): 542 s against 540; 460 s at sortie 17, 405 s at sortie 16. Part of the rise is this flight's tests; how much cannot be told from a loaded run.
- Skips: 15, the expected count under the namespace. Flakes: two, both above.

## Methodology Observations
All on mission-control 1.2.4.

1. **Flight skill, Pre-Flight ("Prerequisites MUST be verified, not assumed"), reached through the sortie skill's step 4.** The Architect's design review stated that a script had no selector on the field being replaced, and the Flight Director ticked the prerequisite on that statement. The check behind it was a grep for two spellings; the script used a third. Expected: a prerequisite of the form "nothing else uses X" records the search that showed it (patterns and directories), so a narrow search is visible to a reader. Cost: one stale capture surface, found by a Developer in passing and fixed in the review pass. Sortie 16's debrief (observation 4) and sortie 17's (observation 1) record ticked prerequisites of another kind (an external account); the common part is a tick with no recorded evidence.
2. **Agentic-workflow skill, Phase 2b (HAT legs, step 4 "fix issues inline") against Phase 2d (the flight review and gate).** The workflow puts the review, the gate and the commit after the last autonomous leg, then the HAT. It does not say what gate a HAT fix needs. The Flight Director chose the lanes of every consumer of the changed control plus the unit tier, and did not re-run the full browser gate. Expected: a stated rule for the gate on the final tree after a HAT fix. Cost: none found (the debrief's two failures are load flakes elsewhere), but the first full gate on the shipped tree ran after the merge and the release. Same family as sortie 17's observations 2 and 3.
3. **Agentic-workflow skill, Phase 2d step 3 and Phase 2b, when the operator asks for the HAT early.** Nothing says the closing gate and the HAT must not overlap. They did: the HAT instance loaded the host during the gate, the gate's lane times were void, and HAT fixes had to wait because the lanes serve files from the working tree. Expected: the workflow names the order (gate, then HAT), or the conflict. Cost: one unusable set of lane times and a hold on edits of about half an hour.
4. **Flight-debrief skill, Phase 2 ("run the full test suite once"), with the project crew file's quiet-host rule.** On a host shared with other sessions the fresh run took about an hour of agent time, never had a quiet start, and produced no budget reading and two load flakes to explain. Expected: the skill, or the project's narrowing of it, says what the debrief does when the host cannot be made quiet (for example: run the unit tier and the touched lanes only, and leave budgets to a scheduled run). Cost: about 2640 s of gate plus 300 s of unit tier for numbers that only confirm "loaded". Sortie 17's observation 5 is the opposite case (a debrief run that found a real failure), so the two pull against each other.
5. **Agentic-workflow skill, Phase 3 step 7 and flight-debrief Phase 1 step 3.** The workflow recommends the debrief on the flight branch before the merge and leaves the order to the operator. The operator merged, then released, then asked for the debrief. The skill's "merged: new branch" path worked as written. Cost: a second branch and PR for artifacts only. Recorded as a data point on how often the recommended order is taken.
6. **Agentic-workflow skill, Phase 2a risk tiering.** Worked as written: high for the shared-control leg (the design review found six medium issues), low for the single-module leg (no spec error found later). A positive data point, as in sortie 17's observation 4.
7. **Agentic-workflow skill, Phase 2b, "multi-surface scope trigger".** Worked as written: the design-review pass before the HAT fix changed the fix's scope and brief. A positive data point.
8. **Sortie and flight skills, design phase, for UI work.** Neither has a step for a mockup. The operator asked for one mid-design; it became the object of approval and the HAT's reference, and the HAT found no layout change. Expected: nothing wrong; recorded because the step that did the most to prevent rework is not in the methodology.

## Recommendations
1. **Record the search behind a "nothing else uses it" prerequisite.** In `.flightops/agent-crews/flight-design.md`, have the Architect list the patterns and directories searched when a control, id or selector is being replaced: the id, the attribute in quoted and unquoted forms, owned classes and testids, across `tests/`, `scripts/`, `docs/`, `evals/` and `tests/behavior/`. **Important.**
2. **Put the lint pair in every leg that adds or edits test files.** One line in the Developer "Implement" prompt of `.flightops/agent-crews/leg-execution.md`: run `ruff check` and `ruff format --check` on what you touched before `[LAND:leg]`. **Important.**
3. **Arrange one quiet `--parallel 3` run** and settle squawk 0376 from it (`mcp`, and `contracts-controls` while there). Three debriefs have now failed to get one by waiting. It needs the operator to pause the other sessions for about 40 minutes. **Important.**
4. **Say what gate a HAT fix needs, and keep the gate and the HAT apart.** A project rule in the leg-execution crew file until the methodology has one: the closing gate finishes before the HAT instance starts; a HAT fix to a shared control re-runs the contract lanes, every consumer's lane and the unit tier (what was done here), and a fix to anything wider re-runs the full gate. **Important.**
5. **Decide the Add row name default with squawk 0375.** When the Tools tab's tiles get their names, decide whether a page with more than one table must pass `addAriaLabel`, and pin it. **Minor.**
6. **Before the next option on `App.ui.keyValueTable`**, add an options-matrix contract test for the combinations that throw or do nothing, and decide whether the Rules tab's hand-built moves stay separate. A design call, so part of the next flight that touches either, not a squawk. **Minor.**
7. **Watch the unit tier's 300 s target.** 283 s at sortie 17, 302 s here under load. **Minor.**

## Operator Interview
Skipped. The flight log is complete, and the operator's decisions (the charter, the mockup, the four HAT choices, the order of merge, release and debrief) are recorded where they were made.

## Action Items
- [ ] Squawk 0375 (open): the agent Tools tab's per-tile Add buttons share one name; `addAriaLabel` is the tool for it.
- [ ] Squawk 0376 (open): a quiet-host reading for `mcp`; this debrief's 390 s is a loaded reading and was added to the squawk as such.
- [ ] Squawks 0372 and 0373 (open): the operator's two original reports; they wait on the two server names, the app version and the operator's leave to read those records.
- [ ] Squawk 0377 (logged from this debrief): the PTY send-timeout unit test fails on a loaded host.
- [ ] Squawk 0378 (logged from this debrief): the widget card's escape contract test can miss the frame's first load; the 30 s timeout was in the helper's wait, not the test's.
- [ ] Squawk 0379 (logged from this debrief): the Key-value table catalogue row names two of its five users.
- [ ] Squawk 0380 (logged from this debrief): the two crew-file lines of recommendations 1 and 2.
- [ ] Carried, cosmetic: the 105-character comment line in `js/ui/chip-list.js` and the comment break in `mcp-connection-fields.js`, with the next edit of those files.
- [x] Scratch directories under the home folder from the HAT and the gates (`the-one-s18-hat`, `s18-gate`, `s18-captures`, `s18-debrief-gate`): removed on 2026-11-17 at the operator's word.

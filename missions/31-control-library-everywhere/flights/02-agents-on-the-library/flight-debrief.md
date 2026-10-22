# Flight Debrief: Agents on the library

**Date**: 2026-10-22
**Flight**: [Agents on the library](flight.md)
**Status**: landed
**Duration**: 2026-10-15 to 2026-10-22. Planning and the canvas ran 2026-10-15 to 16; execution, the flight review and the HAT ran 2026-10-21 to 22.
**Legs Completed**: 18 of 18. That is 17 autonomous legs plus the HAT. Twelve were planned: eleven autonomous plus the HAT. Five legs were split at design review, and leg 10 split three ways.
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
The agent editor and its six tabs are built from `App.ui` library controls.
- `studio.js` went from 4181 lines to 746, and every new studio module is at most 748 lines (`agent-editor-controller.js`). Self-configuration went from one 1424-line file to five modules of 146-445 lines.
- Every agent-editor file has zero HTML-string sinks and zero reuse-allowance rows. No `[data-testid` selector is left in `static/css`.
- **New library controls**, each contract-tested in Chromium and WebKit: `tabs`, `groupTile`, `toolRow`, `chipList`, the tristate `toggle`, and `dangerZone` with `actions`.
- **New options:**
  - `status` `role`/`led`;
  - `emptyState` `plain`/`flush`;
  - `button` `compactIcon`;
  - `badge.dot`;
  - `listPane.rows`;
  - `groupTile` `master.tristate:false`/`dataset`/`describedBy`;
  - `toolRow` `inputDataset`.
- **`mountSlot`**, the shared mount lifecycle, replaces Flight 1's module-level singletons. It has three consumers: the provider models panel, the provider editor and the agent editor.
- **Library behaviour fixes** (squawks 0220 and 0221): the confirm arm is announced, and info buttons are press-only toggletips.
- **Three live defects (DD9)** are fixed, each with a test that reproduced the defect first:
  - collapsing an MCP source no longer loses tool choices (07b);
  - tool overrides survive a Save (squawk 0223 on main, plus leg 08a);
  - a self-configuration write keeps unsaved General edits and shows a note (10a, the operator's choice).
- **The `agents` browser lane** was split into `agents` and `agent-tabs` by the pre-decided 1.3× rule, and every lane was re-budgeted (squawk 0217, open for three debriefs, is closed).
- **The HAT passed** with all 12 items approved and no code change.

### Mission Criteria Advanced
- **The area code is organised by surface:** met for `studio.js`. `admin.js` is Flight 3's.
- **Every kind of control is defined once in the library:** partial. Six controls were added, and the agent editor uses only library controls.
- **A change to one control reaches every place it appears:** partial. Every agent-editor file is at zero allowance rows.
- **No UI markup is built from HTML strings:** partial. Every agent-editor file is at zero sinks.
- **Each control's styles are owned by that control:** partial. The agent-tab CSS was folded into the owners; the dead-CSS sweep of `studio.css` found no dead selectors.
- **Every migrated surface looks as it did before, apart from approved differences:** met for the agent editor. The before and after captures were approved at the HAT, through the live walk-through.
- **Every library control works by keyboard and by role in both engines:** advanced, with the new controls plus 0220 and 0221.
- **Existing behaviour holds:** the full gate is green, and the three DD9 defects are fixed test-first.

## What Went Well
- **Split first, with no behaviour change (DD1).** The shared `state` object landed before any module moved (02a), and the pins were retargeted, never relaxed. The restructure legs needed no test-behaviour change. Never caching `state.x` locally is why the dirty and snapshot sharing stayed correct.
- **Mount once, patch through handles (DD6),** with an interim rebuild list each tab leg removed itself from. The list reached empty at 10a. That handle model is what made the DD9-3 fix possible without re-selecting the agent.
- **Test-first defects (DD9).** Each fix has evidence of failing before and passing after. DD9-2's server half went to main as squawk 0223, which was right: a server fix on a UI branch would have been an unreviewed divert. Leg 08a ported its client rule.
- **Guard-removal proof.** The flight-review fix pass proved two of three new `onSelfConfigChanged` guard tests by deleting the guard and watching the test fail. It reported honestly that the third cannot be proven that way.
- **The capture discipline (DD10)** caught real unplanned differences. The list-pane "New" icon is fixed by `compactIcon`; the danger-zone gap is explained by Flight 1 DD8.
- **Pre-decided rules removed decisions mid-flight.** The 1.3× lane-split rule triggered once, and the split was made with no operator call needed.
- **The flight log carried an interrupted leg.** Leg 11's Developer was killed by an authentication expiry. The resumed Developer rebuilt the partial work from the file list and the prior entries, kept it, and finished.
- **The flight review caught real accessibility gaps** that the leg reviews had not:
  - the mixed-track contrast edge (1.4.11);
  - the stored-value note that could go unannounced (4.1.3);
  - the expand buttons without a group name;
  - the locked master without a reason.

## What Could Be Improved

### Process
- **Legs touching shared state, handles, merges or security were under-sized at planning.** All five design-review splits had a concrete reason:
  - 02: restructure risk;
  - 06: a mount-once frame was unsafe while the other tabs still rebuilt;
  - 07: the MCP master is attach-only;
  - 08: the main merge plus locked chips;
  - 10: DD9-3 was under-specified, and the review returned "needs rework".

  Eleven planned autonomous legs became seventeen. Plan those splits up front in Flight 3.
- **The two-cycle design-review cap bit on 10a.** Cycle 2 still returned "needs rework". The Flight Director rewrote the leg and proceeded without a third review, and the flight review covered the result. It worked, but it is a gap for security-sensitive state machines.
- **DD4's "anything else visible is a defect" was not true in practice.** Six further visible changes surfaced one leg at a time and were collected into the HAT list from log notes. The mixed-track edge and the stored-value announcement were found only at the flight review. A running visible-differences ledger, appended by every leg, would have fed the HAT directly.
- **Library additions landed in a close-out leg.** Leg 11, tiered low-risk, added four library options:
  - `badge.dot`;
  - `listPane.rows`;
  - `emptyState` `flush`;
  - `button` `compactIcon`.

  Library changes belong in a control leg, or the close-out leg should be tiered high when it carries them.
- **Style-hook rule gaps cost two rework rounds.** Leg 09 restyled a library control's inner node from consumer CSS, and leg 10c styled through `[data-testid]` selectors. Both were ruled against, and leg 11 cleaned up and banned the second. Leg specs should state "no consumer CSS on library internals; no testid style hooks; add a variant option".
- **A HAT step was written from memory, not from the spec.** Step 4 expected a half-on MCP master, which is attach-only by design. DD3 and DD4 described `groupTile` as tristate and listed MCP sources beside tool categories without saying the MCP master differs.

### Technical
- **DOM-based form snapshots are the main debt left in place.** Dirty tracking compares strings built from the DOM, so any async DOM change between snapshot and compare can give a false dirty or false clean. That is the likely class behind squawks 0228 and 0229. It is also why `onSelfConfigChanged` must JSON-parse and rebase the snapshot by named keys (including the server constant source name), which silently desyncs if a form field is renamed. A model-based snapshot would remove the class of bug. Consider it before Flight 4 touches the MCP editor, whose dirty tracking has the same shape.
- **The `_activeSection` guard** in `onSelfConfigChanged` cannot be made to fail by any test. Leaving Agents for Library destroys the editor first, and `_activeSection` stays `'agents'` on Chats and Settings, so the hidden editor is patched in place there. That behaviour is accepted, but the guard reads as more than it does. Either delete it or name what it really covers, and document the hidden-editor patch in `agents.md`.
- **The tab-handle contract is implicit.** General has `applyStored`/`setStoredChangeNote`, MCPs has `setSources`, Self-configuration has `deactivate`, and Rules and notes deliberately has no `setAgent`. Write the contract down (`destroy` required; `setAgent`, `deactivate` optional) and check it in the frame.
- **The `state` object has no schema.** Document its fields, or pin the key set in a test.
- **Two field renderers run in parallel** until Flight 3: the `tools-form-helpers.js` strings and the `tool-override-fields.js` nodes. The chip-list rules are encoded twice.
- **Single-consumer options** to recheck at Flight 3's close: `compactIcon`, `master.describedBy`, `master.tristate:false`/`dataset`, and `dangerZone.beforeArm`. `emptyState` has two overlapping variants (`plain`, `flush`); decide whether they merge before a third appears. A library disclosure factory now has two native-`<details>` consumers (the tool-row Overrides and the self-configuration history).
- **The script-count pin is a maintenance tax.** The cache-busting test pins the script count exactly, so every split bumps it. Assert existence and dependency order instead.
- **Test metrics** (the debrief's own `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 make gate`): GATE_RC=0, 1590 s in total, with no failures and no flakes.
  - **Unit tier:** 6717 passed, 14 skipped (the netns count), in 300 s. The Flight 1 debrief had 6705 passed in 281 s. The tier has crept from 195 s at sortie 03 and has still not been profiled.
  - **Browser tier:** 2299 passed, 5 skipped, in 1285 s. The Flight 1 debrief had 2054 passed, 4 skipped, in 1092 s. That is +245 tests (+12%) and +18% wall time, the highest reading in the mission; this flight's own gates read 1102-1187 s.

  | Lane | Now (s) / budget | F1 debrief (s) | Notes |
  |---|---|---|---|
  | routing | 519 / 600 | 498 | |
  | agents | 445 / 540 | 495 | after the split |
  | agent-tabs | 283 / 300 | — | new; 94% of budget from day one |
  | contracts | 379 / 480 | 290 | +31%; 1005 tests, past the ~1000 split threshold Flight 1 set |
  | chats | 348 / 450 | 335 | |
  | mcp | 348 / 450 | 333 | |
  | providers | 332 / 420 | 299 | no new tests; host and schedule variance |
  | library | 270 / 300 | 249 | 90% of budget |
  | settings | 260 / 300 | 227 | |
  | shared | 275 / 300 | 261 | 92% of budget |

  The `agents` area now costs 728 lane-seconds (445 + 283), against 495 s before: about 47% more work for about a third more tests. The split shortened the critical path, not the work.

### Documentation
- `agents.md`:
  - the hidden-editor patch, and what `_activeSection` really guards;
  - the tab-handle contract;
  - the `state` object's fields.
- Test conventions: the route-hold pattern for async-write races, and the guard-removal check as proof that a guard test is real.
- CLAUDE.md's gate-time figure: about 26.5 minutes with ten lanes and this host's load.
- The Filesystem tools' override fields have no `description` (squawk 0231, found at the HAT).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Five legs split at design review; leg 10 into 10a/10b/10c | Each combined a shared-surface change with a migration, or carried an under-specified decision | Yes: split such legs at planning |
| DD9-2's server fix shipped on main (squawk 0223), ported by 08a | A server-side defect does not belong in a UI flight branch | Yes |
| DD9-3's conflict policy ("keep my typing, with a note") was decided mid-flight | DD9 named the defect, not the conflict decision it hid | Yes: name product decisions inside defect fixes at planning |
| `tool-override-fields.js` as a new module rather than `renderFieldNode` in `tools-form-helpers.js` (DD8) | Avoided a mixed string/DOM file | Yes |
| The self-configuration history stays a native `<details>` (DD7) | The library has no disclosure factory | No: add `App.ui.disclosure` (two consumers now) |
| Leg 11 added four library options | Found at close-out (the "New" icon, testid CSS removal) | No: library work goes in a control leg |
| `agents` lane split into `agents` and `agent-tabs` | 1.32× over budget, past the pre-decided 1.3× rule | Yes (the rule worked) |
| Leg 11 resumed after an authentication kill | The login expired mid-leg | Yes: incremental log checkpoints in long legs |
| Flight-review fix pass for non-blocking accessibility items | Cheap, and the findings were real | Yes |
| HAT step 4 corrected live | The step was written from memory, not the DD/leg text | No: derive HAT steps from DD and leg text |

## Key Learnings
- **Legs that touch a shared mount, a shared factory, a merge or a security surface need their own checkpoint.** Every split this flight made at review was one of these.
- **A "mount once, patch" editor needs a written handle contract.** The handles worked, but a reader cannot tell a deliberate omission (Rules and notes has no `setAgent`) from a bug without the log.
- **DOM-derived dirty state is fragile under async renders.** The only open flake and the open Save-race defect in this area come from that design.
- **The HAT list should be a ledger, not a reconstruction.** Each leg appends its visible differences with a reason, and the HAT reads the ledger.
- **A browser-only stall can look like an app defect.** The Goldfinch press stall (0.8-1.8 s on every real press in the tab under test, growing while the tab stayed open; instant in Chrome and Playwright Chromium) cost about twenty minutes of HAT time. Measuring the click-to-render time in the page, then repeating in a plain Chromium, settled it. The operator confirmed it in Chrome.

## Methodology Observations
- **agentic-workflow, Phase 2a, the two-cycle design-review cap (1.2.0).** Leg 10a's second review returned "needs rework". The skill's rule is to escalate to the human. The Flight Director instead rewrote the leg from both reviews' findings and proceeded, relying on the flight-end Reviewer. Expected: either a third cycle for security-sensitive state machines, or an explicit "rewrite and proceed with a flagged flight-review item" path. Cost: one rewritten leg with no independent pre-implementation check. The flight review then found nothing blocking in it.
- **agentic-workflow, Phase 2a, risk tiering (1.2.0).** The close-out leg (11) was tiered low-risk because its planned content was counts, captures, re-budgets and docs. During execution it added four library options. The tier is set before implementation and is not revisited when a leg's actual changes grow. Cost: the four options went without a leg design review, and the flight review caught the accessibility gaps they shared. Expected: a re-tier trigger when a low-risk leg touches a shared factory.
- **agentic-workflow, Phase 2b, HAT legs (1.2.0).** The HAT leg was written by the Flight Director from the flight-log HAT list and memory. One step contradicted the leg 07b design (the MCP master is attach-only), and the operator hit it as a "fail". Expected: HAT steps derived and cited from DD and leg text. Cost: one false failure and a live checklist correction.
- **flight, Phase 5 (1.2.0).** The flight's DD4 enumerated visible changes as a closed list ("anything else visible is a defect"). Six more surfaced during legs, and two only at the flight review. The methodology has no running ledger for approved visible differences between planning and the HAT. Cost: the HAT list was rebuilt from log notes, and the flight review raised two items late.
- **agentic-workflow, an interrupted Developer (1.2.0).** An authentication expiry killed leg 11's Developer mid-leg, leaving the leg `in-flight` with partial edits and no log entry. The skill's "Developer agent fails mid-leg → spawn new Developer with context" worked, because the Flight Director listed the files changed since the prior leg's timestamp. Expected: crew prompts that ask for a short in-progress log line at each internal checkpoint, so the resume does not depend on file mtimes. Cost: one reconstruction pass. The partial work turned out correct and was kept.

## Recommendations
1. **Plan Flight 3's legs with the split rule up front.**
   - Separate library-control legs from surface migrations.
   - Split `mcp-server-editor.js` (2153 lines) and `knowledge-section.js` (1493) the way `studio.js` was split, before migrating them.
   - Split the `contracts` lane (1005 tests, 379/480 s) before adding to it, and check the headroom of `library`, `settings` and `shared` (90-92% of budget).
2. **Write the editor contracts down before Flight 3 adopts them,** in `agents.md`, with a frame-level check (squawk 0235 covers the documentation):
   - the tab-handle contract (`destroy` required; `setAgent`/`deactivate`/`setSources` optional);
   - the `mountSlot` lifecycle;
   - the `state` object's fields.
3. **Decide the snapshot model.** Either move dirty tracking to a model-based snapshot (removing the async DOM race behind 0228 and 0229, and the `onSelfConfigChanged` key rebase), or record it as accepted debt with 0228 fixed directly.
4. **Make the style-hook rule and the visible-differences ledger standard leg content.**
   - The style-hook rule: no consumer CSS on library internals, no testid style hooks, add a variant option.
   - The ledger: each leg appends its visible differences, and the HAT is derived from the ledger and the DD text.
5. **Close the small carried items:**
   - add `App.ui.disclosure` (two consumers);
   - rewrite the 0230 ratio test as an absolute bound;
   - profile the unit tier with `--durations` (squawk 0234);
   - delete or rename the `_activeSection` guard (squawk 0232);
   - replace the exact script-count pin with an existence-and-order check (squawk 0233).

# Flight Debrief: Settings on the library

**Date**: 2026-10-25
**Flight**: [Settings on the library](flight.md)
**Status**: landed
**Duration**: 2026-10-23 to 2026-10-24.
- 2026-10-23: planning, the squawk 0248 hotfix (#304), and legs 01 to 04f.
- 2026-10-24: legs 05a to 11, the flight review, the HAT, two merges of `main` and the landing.

**Legs Completed**: 25 of 25: 24 autonomous legs plus the HAT. 19 were planned; the six extra came from splits made at leg design review. No leg was split or reopened during execution.
- Planned groups: 01, 02a-b, 03a-b, 04a-f, 05a-c, 06, 07a-d, 08a-b, 09, 10, 11, 12.
- The splits: 04a into 04a, 04c and 04f; 05b into 05b and 05c; 07 into 07a-d; 08 into 08a and 08b.

**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
Every Settings page is now built from the control library: Appearance, Date and time, Prompts, Encryption, Built-in tools and Knowledge indexing. The approved presentation debt is fixed, and the flight's planned groundwork for the rest of the mission is in place.

**Counts**
- Ownership allowance: 135 rows / 315 uses → 66 / 167.
- HTML-string sinks: 37 → 23.
- Every Settings file is at zero sinks and zero allowance rows. The one exception is the string-built chip list in `tools-form-helpers.js`, kept for Flight 5's MCP editor.
- The only sinks left are in `chat.js` and the MCP editor.

**Structure**
- `admin.js` split, with the tools page controller moved to `tools-page.js` behind a `ctx` boundary.
- `knowledge-folders.js` split into `knowledge-rows.js`.
- An 800-line guard on area modules, falsified.
- `App.tabs` and `js/tabs.js` deleted.
- `tool-override-fields.js` replaced by one shared field module, `areas/shared/tool-config-fields.js`, serving the admin editor and the agent Tools tab through a mode flag.

**New library pieces**, contract-tested in Chromium and WebKit:
- **Controls:** `pageHeader`, `banner` (persistent live mode), `codeBlock`, `facts` (subgrid), `toolTile` and its grid.
- **Options:** `editorShell` `variant: 'page'`, `section` `layout: 'stack'` and `info`, `textInput` `width: 'short'`, inline `searchList` (`keepScroll`, `describedBy`, selected mark, `setActive`), `radioGroup` `slotIndent`, `chipList` middle ellipsis, `field` `flush`, `tabs` `panelPadding`.
- **Helpers:** `App.ui.util.latest()`, `syncChildren` and `middleEllipsis`.
- **Errors:** `fetchJson` errors carry `status`/`detail`/`body`, and `App.api.fieldErrors`/`humanizeMessage` put a 422 on its field.
- **Tokens:** opaque `--btn-disabled-*` tokens (disabled labels at 3:1 or better, app-wide).
- **Guard:** the emitted-class guard, `tests/test_ui_emitted_classes.py`.

**Backend (additive, tested)**
- Tool `summary` and `config_fields`.
- `_merge_hidden_fields`: hidden settings keep their stored value on a PUT.
- An `outcome` field on the tool Test route.
- `GET /api/encryption/status`, with `last_rotated_at` recorded inside the rotate transaction.
- Written field labels and plain preset labels; none of these are model-facing. The one model-facing change (A17, the stale `web_search` sentence) passed the `m30-platform` size gates.

**Squawks**
- Closed: 0230, 0231, 0236, 0237, 0238, 0240, 0245, 0246, 0247.
- 0248 (the tool editor wiped the default denylists) was hotfixed on `main` before the flight (#304), including the resolver's `default_factory` crash.
- 0249 (OAuth popup flake) was logged and deferred.

**Presentation ledger.** Rows 1-48 are approved survey items (A1-A24, B1-B15 less B13, B4 changed), all delivered. Rows 49-54 were added at the HAT.

**The HAT passed: 15 steps, all passing.** Six fixes were made, each test-first and reviewed:
- **Row 49:** switching a category tab closes an open tool editor, through the leave guard.
- **Row 50:** the Test button lines up with its input, via a new `field` `flush` option. The first attempt styled library internals and was rejected under DD11.
- **Row 51:** agent number overrides are checked against min/max and the exclusive bounds.
- **Row 52:** Prompts is one list, with the Identity blocks together.
- **Row 53:** the time-zone button names the city ("Use Paris").
- **Row 54:** a zone whose label is its id is named once ("Selected: UTC").

The capture compare (220 images) was approved at step 15 through a private comparison page.

### Mission Criteria Advanced
- **Every kind of control is defined once in the library** (partial): the controls above, with catalogue rows.
- **A change to one control reaches every place it appears** (partial): Settings is at zero allowance rows; the total fell to 66 / 167.
- **No UI markup is built from HTML strings** (partial): 37 → 23 sinks; none left in Settings.
- **Each control's styles are owned by that control** (partial):
  - `admin.css` is Settings-only;
  - the dead `.area-admin` switch, chip and field-error rules are gone;
  - the emitted-class guard makes ownership mechanical in both directions.
- **Every migrated surface looks as it did before, apart from approved differences:** met for Settings. 30 surfaces changed, all mapped to ledger rows; 21 changed only in the disabled header buttons (row 37); 4 are identical.
- **Every library control works by keyboard and by role in both engines** (partial):
  - the new controls' contracts pass in Chromium and WebKit;
  - DD8 defects 1-19 are fixed, including the switch's accessible name, focus on the rotate button and focus on the chosen zone.
- **The area code is organised by surface** (partial): the `admin.js` and `knowledge-folders.js` splits, and the 800-line guard.
- **Existing behaviour holds:** every planned defect was fixed test-first; the full gate is green on the merged tree.

## What Went Well
- **The presentation ledger at planning** (DD7). The FD surveyed every surface and the operator approved the A and B lists before any code. That list drove the legs, the HAT steps and the capture review one-to-one. The survey also found squawk 0248, a data-loss defect, before the flight started. The operator wants to keep it as the standard opening for UI flights.
- **Groundwork first** (DD2). The line guard, deterministic captures and the lane fixes landed in leg 01, so no later leg had to repair its own tooling. Deterministic captures made every batch compare readable.
- **Patterns settled before surfaces** (DD3, Flight 3's recommendation 4). The error reader, `fieldErrors`, `latest()` and `syncChildren` were in the library before any Settings page used them, and each page consumed them without local variants. `latest()` replaced five hand-rolled counters.
- **Marker classes with handover legs** (DD12), paired with the emitted-class guard:
  - a control could be built before its last legacy user moved, with no allowance growth;
  - ownership passed to the library in the leg that migrated the last outside user;
  - this was the most useful new rule of the flight.
- **Splits happened at design review, never in execution.** That is what Flight 3's debrief asked for. Every split was made at leg design review, and no leg was reopened.
- **Batch + scoped checks** (operator decision at 04f, FD Notes):
  - from 05a on, consecutive legs on one surface ran as a batch, with a checkpoint commit per batch and the full parallel gate only at leg 11;
  - it cut the cycle time without shipping a defect;
  - the operator prefers this mode, with the HAT at the end, as the default.
- **Every Flight 3 recommendation was carried out**:
  1. the presentation survey;
  2. the remount side-effect inventory (DD5, leg 07c);
  3. the line guard and splits;
  4. settled patterns;
  5. the re-close after a code-changing HAT, which ran twice (after rows 49-52 and after rows 53-54), with a full gate alone each time.
- **The HAT freeze investigation ended in the right place.** The headless engines showed about 0.1 ms of app work per keystroke. A bare-page control in the operator's browser then showed the cost was the browser's: 54 text inputs took 9-12 s per keystroke on a bare page. The defect was filed upstream (goldfinch#270) and fixed in Goldfinch 0.19.7 the same day, with no app change. The operator confirmed the step 11 lag was the same Goldfinch defect.

## What Could Be Improved

### Process
- **Four of the six HAT fixes were catchable by tighter acceptance criteria:** rows 50, 51, 53 and 54. Each came from a leg whose criterion described a look ("the button on its line", "city names in the hint") or a format, with no test of a derived relationship or a degenerate input:
  - **Row 50:** "on its line" was tested as "same row", not "centres within 1 px".
  - **Row 53:** the banner text used `placeOf` while the button used the raw zone id. No criterion said the two must name the same place.
  - **Row 54:** the fixtures used zones with a distinct city (Paris, Chicago); none had a label equal to its id.
  - **Row 51:** the most serious. Leg 05b replaced `type=number` with text inputs (row 46) and specified the non-whole error, but not the range check `type=number` had implied. Nobody asked what the old control gave for free.
- **Row 49 was a design gap, not a cosmetic fix.** Replacing `App.tabs` with `App.ui.tabs` made it possible to change category with an editor open, and no DD or leg said what should happen. An existing test even switched tabs with the editor open. The fix was clean (`onBeforeChange` through the leave guard). The focus return (`returnFocusToTab`) is timing-based, two tasks after the router's `focusMain`, and depends on router internals.
- **The capture compare is not a defect review.** Rows 50 and 54 were both visible in the after images, as part of surfaces whose difference was already mapped to a ledger row. They were read as the approved change. The compare proves every difference is explained, not that each explained difference is right.
- **Row 52 reversed an approved row** (A3, the variant as a sub-heading). It was approved from a text description; the operator's preference only emerged from the real page. Taste items approved before a render can change at the HAT. That is acceptable, but expect it.
- **Batch-mode gaps**, two small ones:
  - **A stale test reached the gate.** Leg 11 deleted the `.area-admin` chip-list rules (no Settings user was left, so they were deleted rather than moved, against the leg's "unchanged in count" wording). A contract test parametrised over `area-admin` failed four times at the gate and cost one extra gate run (1455 s). Grepping the tests for each deleted class at batch end, and running the owning lane, would have caught it.
  - **Lane times under load misled.** `settings` read 465-589 s against a 360 s budget during batches B4 and B5, because Developer lanes ran concurrently. Quiet, it was 273 s. Squawk 0217's "1.3x over budget" rule has no quiet-host condition.
- **The first freeze diagnosis was unmeasured.** The FD attributed the `http_request` freeze to host load without a profile. The conclusion (no app change) was right, but the cause was wrong. The tie was broken by a CPU profile and a bare-page control in the reporting browser.

### Technical
- **Agent tool overrides are not validated on the server.** `update_agent` stores `tool_overrides` as sent (only preserve-on-omit, squawk 0223). `resolver.resolve` raises when an override widens the operator's value or fails the schema, so an out-of-range override that reaches the database fails only at the agent's next build. Row 51 closed the client path; the API path is still open. Candidate squawk below.
- **The hidden-field fallback is a silent downgrade.** `_merge_hidden_fields` keeps a hidden stored value, but when that value no longer validates it retries without it and the Config default applies. That is pragmatic and sound, but the contract lives in one `agents.md` sentence. `config_fields` is display-only: a tool that later starts reading a hidden field would need the audit redone, and nothing tests for that.
- **The number overrides are text inputs** (row 46), so validation is now the app's job. The agent Tools page has 54 or more text inputs when fully expanded, which is what exposed the Goldfinch defect. That is a known dependency, not a defect.
- **Cascade-layer debt.** `.editor-section--flush` keeps `!important` against the later-layer `.area-studio .editor-section`. It is documented and tested, but any library rule a later-layer area stylesheet overrides can hit the same trap in Flights 5-6.
- **`searchList.render()` rebuilds every row on each keystroke.** It was measured as no slower than `main`, but a clear rebuilds 313 rows (58-94 ms). `syncChildren` now exists for exactly this.
- **Smaller items:**
  - The Test row wrapper uses a fixed `height: 35px` that mirrors the input's computed height. It is guarded by a test, but it is a magic number.
  - `credential_count` is 0 with an env-supplied key: the docstring says so, the page does not.
  - The tool tile's full description is in a `title` tooltip only.
  - The toggle revert's stale-index fix has no test (no seam).
- **Leftovers for Flight 5:**
  - the string-built chip list in `tools-form-helpers.js` (205 lines);
  - the five `.area-studio` chip and switch allowance keys moved to `studio.css` (13 uses);
  - the two `App.icon` calls on the chip path.

### Documentation
- CLAUDE.md's control-library paragraph is about 1,200 words and grows a block per flight. Flight-by-flight deltas belong in `the_one/agents.md`; CLAUDE.md should keep "what to know to work here".
- Missing from `agents.md`:
  - the agent override validation contract (client range check, Narrow maximum, what the server does);
  - a design note for the hidden-field carry-over pair (server `_merge_hidden_fields`, client hidden-override preservation);
  - the bare-page control technique for a freeze the test engines can't reproduce.

## Test Metrics

The full gate ran alone on the landed, merged tree (`07fc5c6` plus artifacts): `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`, rc=0. The debrief did not re-run it, because no code changed after that run.

**Unit:** 7188 passed, 0 failed, 15 skipped, 333.5 s.
- The skips are the netns 14 plus `test_packaging_apprun.py::test_read_only_data_home_does_not_stop_launch`. That test came from the Mission 32 merge and is root-only, so it skips under the netns uid mapping.
- About 140 of the +415 unit tests came from this flight; the rest came from the merge.

**Browser:** 2909 tests, 0 failed, 5 skipped (WebKit contract skips, unchanged), `PARALLEL_RESULT rc=0 total=1571s lanes=13 failed=-`. No retries.

| Lane | Flight 3 (s) | Leg 11 (s) | Final (s) | Budget (s) |
|---|---|---|---|---|
| routing | 521 | 540 | 575 | 600 |
| agents | 442 | 463 | 498 | 540 |
| chats | 396 | 409 | 446 | 450 |
| mcp | 356 | 364 | 358 | 450 |
| providers | 330 | 345 | 346 | 420 |
| contracts-controls | 246 | 318 | 341 | 420 |
| shared | 309 | 308 | 328 | 420 |
| knowledge | 279 | 319 | 317 | 420 |
| agent-tabs | 273 | 281 | 313 | 360 |
| settings | 263 | 273 | 291 | 360 |
| settings-tools | n/a | 243 | 259 | 330 |
| contracts-overlay | 180 | 227 | 225 | 270 |
| library | 168 | 173 | 167 | 210 |

**Against earlier debriefs**
- **Unit tier:** F1 6705 (281 s) → F2 6717 (300 s) → F3 6773 (297 s) → F4 7188 (334 s). Wall time is now over five minutes before the browser tier starts, and it is unprofiled (squawks 0222, 0234 are open).
- **Browser tier:** F2 2299 tests / 1285 s → F3 2470 / 1304 s → F4 2909 / 1571 s.
  - This flight: +18% tests, +20% wall time, the highest in the mission. In Flight 3, the lane splits absorbed the growth.
  - `contracts-controls` gained 216 tests (624 → 840), about 40% of the growth: the new controls and options, each in two engines.
  - The tools-editor DD8 tests added about 170 more.
- **Near budget:**
  - `chats` is at 446 of 450 (99%), with no new tests since leg 11 (409 s). The +9% is probably noise or the merge. Re-measure it on a quiet host before re-budgeting.
  - `routing` is at 96% and remains the critical path; `agents` is at 92%.
- **Within-flight full runs:** 1339 s (04a), 1428 s (04c), 1375 s (04e/f), 1455 s (leg 11 run 1, rc=1, the stale chip-list test), 1470 s (leg 11 run 2), 1682 s (HAT close checks), 1571 s (final).

**Flakes**
- Squawk 0249 (OAuth popup wait) failed twice in `shared` during batches (04d, 04e/f) and passed on a solo re-run each time.
- It did not appear in leg 11 run 2, the HAT close or the final gate.
- Squawks 0229 and 0230 did not recur; 0230's fix landed in leg 01.

Every other failure in the flight was real test staleness, found at batch end or (once) at the gate, not a flake.

## Deviations and Lessons Learned
- **The leg count grew from 19 to 25**, all through design-review splits. One flight for Settings was the right call for the shared pieces (`pageHeader`, `banner`, the `admin.js` split, the `admin.css` close-out cut across all pages). Even so, at 24 autonomous legs plus a 15-step HAT, this was the largest flight of the mission.
- **The planned `admin.css` → `studio.css` move created new allowance keys,** although total uses fell from 315 to 167. Reviewer B called it a blocking increase; the FD overruled it as the planned move. The overrule was right, but it rested on prose. "Only shrinks" does not define a move between files. Part of the move turned out unnecessary: the `.area-admin` halves had no user left and were deleted instead.
- **`--btn-disabled-*` tokens (04c) changed every disabled button in the app, not just Settings.** That was approved as row 37 and is visible in 21 captures. A "Settings" flight touched a shared token; say so in the objective when that happens.
- **Library bugs showed only with a real consumer:**
  - leg 09 found that 04d's visually hidden "(selected)" mark escaped the inline listbox's clip, stretching the page to about 18,000 px;
  - `facts` alignment (row 48) and `field` `flush` (row 50) also came from consumers.
  - "Library-only" control legs need a consumer leg right behind them.
- **Two merges of `main` mid-flight** (installer missions). Both were clean, and the second was gated with the landing.

## Key Learnings
1. **A replaced control's implicit behaviour is part of the spec.** Moving from `type=number` to text dropped an implied range constraint (row 51) and changed how a third-party browser treated the page (Goldfinch). Every control-replacement leg should list what the old control gave for free.
2. **"Looks like X" criteria need a derived-relationship test.** Examples: label equals the text it pairs with, centre equals centre within 1 px, a label that equals its id. Each costs one assertion and would have caught rows 50, 53 and 54.
3. **Explained is not correct.** A capture compare that maps every difference to a ledger row still needs someone to judge each mapped difference against what the row promised.
4. **A freeze that only one browser shows needs a bare-page control in that browser before any explanation.** "Host load" must be a measurement, not a guess.
5. **A tab bar or list beside an open editor is an interaction to specify,** not a cosmetic detail (row 49).

## Methodology Observations
Plugin version 1.2.0 throughout.

- **agentic-workflow, Phase 2a (leg design).** The risk tiering and design review split legs well and early: six extra legs, no execution-time splits. There is no guidance on a flight-size ceiling once review splits push the leg count well past the flight skill's "typically 1-4 legs". This flight reached 24 autonomous legs without a prompt to reconsider splitting the flight. Cost: seven checkpoint commits, a mid-flight operator request to speed up, and a 15-step HAT. Expected: a nudge when design review takes a flight past roughly 15 legs.
- **agentic-workflow, Phase 2b/2d (per-leg vs end-of-flight verification).** The skill defers review and commit to the flight end but says nothing about batching lane runs. The operator introduced "Batch + scoped checks" mid-flight, and it worked: one stale test escaped to the gate and cost one extra 25-minute gate run. The operator prefers this mode, with the HAT at the end, as the default for library-migration flights. Worth recording as a sanctioned mode with two rules:
  - at batch end, grep the tests for any deleted selector or class and run its lane;
  - lane over-budget readings count only when taken with at most one other lane running.
- **agentic-workflow, the HAT fix-or-feature gate.** It worked for rows 50-54. Row 49 was classed as a fix, but it was an unspecified interaction. The gate did catch a DD11 breach in the first row 50 fix through the HAT-fix review. That review is valuable; the HAT-fix Developer brief should state "library option, never consumer CSS on library internals" up front.
- **flight skill, Phase 3/4 (planning).** The presentation survey with up-front operator approval (DD7) is not in the flight skill, but proved the most effective planning step of the mission's UI flights. The operator wants it kept as the standard opening for UI flights. Approving taste items from text, before a render exists, produced one reversal (row 52) at the HAT; that is a reasonable cost.
- **flight-debrief, Phase 2 (Developer interview).** The skill asks the Developer to run the full suite. The FD instead supplied the landing gate's log, which ran alone on the identical code an hour earlier, to avoid another 30 minutes of host load. Worth allowing explicitly when no code changed since a recorded full run.

## Recommendations
1. **Add a "what the old control gave for free" check to every control-replacement leg** (native validation, min/max, spinner, autofill, IME, mobile keyboard), and a derived-relationship or degenerate-input criterion to every relabel or restyle leg. *Critical*: it would have prevented rows 50, 51, 53 and 54.
2. **Validate agent tool overrides on the server** (squawk 0257). `update_agent` should run each override through the resolver against the current tool config and return 422, so a bad value never reaches the database. *Important*; candidate squawk below.
3. **Plan Flight 5 (the MCP editor) as Settings was planned:**
   - a presentation survey with up-front approval, batch mode, and the HAT at the end;
   - one handover leg that retires the string-built chip path in `tools-form-helpers.js`, the five `.area-studio` chip and switch allowance keys, and the `App.icon` calls on that path, with a test that the file is gone;
   - reuse the shared field module's three ideas, not the module itself: a stable DOM contract, a handle-based snapshot with per-field re-mask, and `fieldErrors`. Keep the preserve-on-omit rules for masked secrets;
   - Flight 5 also carries the OAuth popup, the probe on open, the most remount side effects and squawk 0249.
   - *Important.*
4. **Re-measure `chats` (99% of budget, squawk 0259) alone on a quiet host before Flight 5 adds tests**, then raise its budget or split it. Add the quiet-host clause to squawk 0217's rule. *Important.*
5. **Revisit Flight 6's scope at Flight 5's debrief.** The Architect judges "chat controls, the `chat.js` split, and every count to zero with aliases and docs" as two flights' worth by this flight's evidence. Re-count the alias calls at Flight 5 planning rather than trusting Flight 1's numbers. *Important.*
6. **Turn the allowance rule into "total uses only shrink, plus a committed MOVES table"** (class, from, to, uses, retire-by flight), so a planned move between files is an explicit, expiring exception rather than a prose overrule. Plan moves only for rules with a named live user. *Minor.*
7. **Schedule a library leg for `searchList` reconciliation by item id** (through `syncChildren`), and a cascade-layer cleanup for `.editor-section--flush`. *Minor.*
8. **Move flight-by-flight deltas out of CLAUDE.md's control-library paragraph** into `the_one/agents.md`. Add the override validation contract, the hidden-field carry-over note and the bare-page freeze technique there. *Minor.*

**Carried items:**
- the knowledge search score floor and "Add file" (mission Known Issues);
- the 27 fixed `wait_for_timeout` calls in the knowledge and connector tests (DD10: new tests only);
- squawks 0222 and 0234 (unit tier profiling) and 0249 (OAuth popup flake);
- a test that every Config field a tool reads appears in its `config_fields`;
- a replacement for the timing-based `returnFocusToTab`.

## Follow-up Squawks
Logged by the operator's decision on 2026-10-25, all `routine`:
- **[0257](../../../../squawks/0257-agent-tool-overrides-not-validated-on-save.md)** (defect): agent `tool_overrides` are stored without validation; an out-of-range or widening override fails only at the agent's next build (Recommendation 2).
- **[0258](../../../../squawks/0258-encryption-count-zero-with-env-key.md)** (defect): the Encryption page shows "0" stored items with an env-supplied key, with no qualifier.
- **[0259](../../../../squawks/0259-chats-lane-at-budget.md)** (servicing): the `chats` lane is at 99% of its budget; re-measure on a quiet host, then re-budget or split (Recommendation 4).

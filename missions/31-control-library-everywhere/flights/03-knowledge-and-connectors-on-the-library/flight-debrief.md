# Flight Debrief: Knowledge and connectors on the library

**Date**: 2026-10-23
**Flight**: [Knowledge and connectors on the library](flight.md)
**Status**: completed
**Duration**: 2026-10-22 to 2026-10-23. Planning ran on 2026-10-22; execution, the flight review and the HAT on 2026-10-22 and 23.
**Legs Completed**: 15 of 15: 14 autonomous legs (01, 02, 03a-c, 04, 05a-b, 06a-b, 07a-b, 08, 09) plus the HAT. Every split was made at planning, and no leg was split during execution.
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
The Library's knowledge-base editors (create and detail) and the connector editor are built from `App.ui` library controls. They mount once and patch in place on Save and Cancel.

**Structure**
- `knowledge-section.js` (1493 lines) was split behaviour-free into seven modules plus `knowledge-glue.js`, with byte-identical DOM dumps at the split (leg 02).
- The HAT later pushed `knowledge-folders.js` to **897 lines**, over the flight's 800-line rule (see What Could Be Improved).

**Counts**
- Every knowledge, connector and glue file is at zero HTML-string sinks and zero ownership-allowance rows.
- Whole app: 187 rows / 409 uses / 46 sinks became **135 / 315 / 37**. That is 94 uses removed, against about 102 planned, net of the accepted +12 from 03c.

**New library controls**, contract-tested in Chromium and WebKit:
- `App.ui.disclosure`: bordered and plain variants, with meta and actions beside the summary. Three consumer files.
- `App.ui.keyValueTable`: a keyed row model, with a hook reserved for Flight 5's masked column.
- `App.ui.clearableInput`: squawk 0100.

**New options**
- `chip` `warning` and `dataset`
- `status` `ledTestid` and `textTone`
- `editorShell` `save.enabledWhenClean` and `errorRole`
- `copyField` `buttonLabel`
- `field` `errorTestid`
- `section` `descriptionTestid`
- a `more` icon
- `menu` used for the knowledge item rows

**Defects fixed (DD8)**
- Seven of the eight planned defects were reproduced failing, then fixed:
  - the channel map keeps typed values;
  - one connector per Create;
  - the doctor on a non-OK response;
  - the poll no longer steals focus;
  - the panel and search races;
  - focus on the inspect heading;
  - the chip cascade.
- DD8-7 (Ctrl K with a menu open) did not reproduce and is kept as a pin.
- Two defects were found beyond the plan:
  - the typed plaintext token stayed in the field after an edit Save;
  - the folder poll re-appended every panel on each tick.

**Squawks and lanes**
- Squawks 0100, 0191, 0192, 0233 and 0235 are completed.
- The `contracts` lane was split into `contracts-overlay` and `contracts-controls`, and `knowledge` was split out of `library` by the 1.3× rule.

**The HAT passed.** It turned into a working session that delivered:
- **Knowledge create:** "Name is required." on the Name field.
- **Folder rows:** humanised timestamps ("Indexed {date}, {time}", "Last checked …", with the precise value in `title` and `data-indexed-at`) and one status word.
- **Search:** results as a list (basename, path and score line, a 3-line snippet).
- **Connector:** the header re-probes after an edit Save; gaps under the pairing and doctor results.
- **Individual files:** the "Other items" panel became "Individual files", with an API-only hint, a two-step remove, tombstones and an orphan hold-out.
- **Inspect panels:** chunks and source got a static heading, the file name and path, a close button that returns focus, and a shared boxed body.

### Mission Criteria Advanced
- **Every kind of control is defined once in the library:** partial. Three controls and ten options were added; the knowledge and connector editors use only library controls.
- **A change to one control reaches every place it appears:** partial. Every Library-half file is at zero allowance rows.
- **No UI markup is built from HTML strings:** partial. Every Library-half file is at zero sinks.
- **Each control's styles are owned by that control:** partial. The knowledge and connector restyles were folded or removed, and the unused-selector report was reviewed. The HAT re-grew about 170 lines of area CSS, mostly spacing (see Technical).
- **Every migrated surface looks as it did before, apart from approved differences:** met. The ledger fed the HAT, and the operator approved items 1-6, kept "Knowledge" for item 7, and waived the capture review.
- **Every library control works by keyboard and by role in both engines:** advanced. The item menu moved to the accessible menu pattern; the new controls are contract-tested.
- **The area code is organised by surface:** met at leg 09, **broken at the HAT** (`knowledge-folders.js`, 897 lines).
- **Existing behaviour holds:** the full gate is green after a triage re-run (see Test Metrics). DD8 was test-first.

## What Went Well
- **Controls before consumers (DD4).** Every leg was designed before 03b ran, so needs found in the surface-leg reviews were folded into the control leg first: `textTone` from 05a/05b, `field.errorTestid` and `section.descriptionTestid` from 06a. No `js/ui/` file changed in a surface or close leg, which fixes Flight 2's "options added at close-out" problem.
- **Splitting at planning, not mid-flight.** All splits (03a-c, 05a-b, 06a-b, 07a-b) came from Architect cycles 1 and 2, and none happened during execution (Flight 2 had five). Flight 2's recommendation 1 worked.
- **Groundwork first (DD2).** The 0233 existence-and-order check meant the knowledge split added seven script tags with no cache-busting test edit, the first split since that pin was written to do so. The contracts lane split and the 0235 editor-contract docs landed before anyone needed them.
- **The value model for dirty state.** Sticky `markDirty` is gone. The connector's `readValues`/`buildPayload`/`applyRecord` shape re-masks the token and reads the snapshot back from the controls, so no plaintext is held. It is the template for Flight 5's MCP editor.
- **The focus-safe keyed reconcile** (`syncChildren`): never re-append a node that is already in place. This, more than any guard, is the real fix for DD8-4.
- **Disciplined fix-or-feature calls at the HAT.** Look-and-feel items went in inline. The Individual files remove and the inspect close went through a scoped Plan review, then a Sonnet Reviewer. "Add file" and the search score floor were deferred with the operator's agreement.
- **The visible-differences ledger** (Flight 2's recommendation 4) fed the HAT list. HAT items 1-6 came straight from it.
- **Lane rules ran themselves.** The 1.3× rule split `knowledge` out at leg 09 with no operator call. The one-file `knowledge_pat` kept `test_flow_studio_knowledge_attach` in `agents`, which a glob would not have.

## What Could Be Improved

### Process
- **The HAT carried about two legs of work.** After the HAT the product diff was `knowledge-folders.js` +471, `knowledge-inspect.js` +120 and `studio.css` +211, with tests +737 (knowledge) and +109 (connector). The cause: the flight's parity rule ("looks as it did before") carried existing presentation debt over unchanged, and the capture check could not see it:
  - a before/after diff shows only changes, never debt that is already there;
  - the masks replaced exactly the problem text ("Indexed (time masked)", "score 0.000", "Expires (time masked)");
  - the capture seed (one shallow folder of 4 files) had no long nested path and no individual file.

  **The operator's decision at this debrief:** from Flight 4 on, survey obvious presentation problems at planning and fix them proactively as approved visible changes, instead of finding them at the HAT.
- **Leg 09's close checks did not cover the HAT.** After the HAT and the sortie 5 merge, only the unit tier, single lanes and the guards ran. The line rule, the unused-selector report and the catalogue were not re-checked, and the 897-line module went unnoticed until the debrief's Architect. The debrief's own full gate is the first since leg 09.
- **The HAT step text was wrong twice** (minor, per the operator):
  - step 2 promised a field error that DD6 had ruled out;
  - step 5 expected a chip the seed could not produce, and the leg's Inputs misread "Other items" as a folder's files.
  Both came from ledger wording, not checked against the data model, and nobody dry-ran them on the seeded instance.
- **A HAT apparatus slip.** Step 9 (delete a knowledge base) deleted the seeded "HAT notes" instead of the scratch knowledge base. The FD re-seeded it after the restart. A destructive step needs its own disposable, clearly named item.
- **A HAT feature had no Accessibility Reviewer.** The Individual files remove (a confirm armed on an icon button, a focus chain) and the inspect close got one scoped Reviewer, not the a11y pass the flight review had.

### Technical
- **`knowledge-folders.js` is 897 lines** (650 at the flight commit, 703 after the HAT fixes, 897 after Individual files), and nothing enforces DD3's 800-line rule. A natural split: `knowledge-rows.js` (`buildFileItemRow`, `patchFileItemRow`, `renderRows`, `removeFile`, `focusAfterRemove`), apart from panels and grouping. Its invariant comments are also stale: `:62` "The two never call each other" and `:783` "Never called from `renderFolders`" are now false, and `studio.css:143` names `buildOtherItemsPanel`.
- **Error placement is split.** DD6 kept `kb-create-error` as the one error surface for a test-pin reason. The HAT moved the empty-name error to the field "for this form only". Every other editor puts validation errors in the header, while the Add-folder input in the same editor already used a field error. A mission-wide rule is needed: validation errors on the field, request errors at editor level.
- **The 03c chip cascade marked the library list, not the legacy ones.** Narrowing `admin.css` with `:not(.ui-chip-list)` names a library-owned class in area CSS, which forced +12 allowance rows against the mission's "only shrink" constraint. A legacy marker class in the two string emitters (`tools-form-helpers.js`, `mcp-server-editor.js`) would have kept the allowance monotone. The rows are repaid only when Flights 4 and 5 finish.
- **Spacing between mixed section children is a library gap.** The HAT fixed "button touching its result" twice with area structural selectors (`.connector-pairing-result:has(> :not([hidden]))`, `.doctor-btn + :not([hidden])`), next to hand-set `padding: 6px 0` and `.kb-folders-list { margin-top }`. `App.ui.section` does not own the vertical rhythm between heterogeneous children.
- **Four "late response" mechanisms sit side by side:** mountSlot tokens, `alive`/`destroyed` flags, generation counters (`doctorSeq`, `headerSeq`, `pairingSeq`, `epoch`, `generation`) and `ctx.isLive`. Slot placement also differs between the knowledge glue and the connector editor. Each is correct; together they are five copies of "latest request wins".
- **Three ways to read an error in one editor:** `App.api.fetchJson`; raw `fetch` with `_errorMessageFromResponse` (folders add, delete and remove; inspect); and raw `fetch` with "HTTP N" (search, re-index, pairing). That is 14 raw `fetch` calls against 10 `fetchJson` in these files.
- **Duplicated helpers.** `knowledge-search.js` re-declares `el` and `baseName`; its `baseName` splits on either separator while `knowledge-shared.js` picks one. `provider-models.js:placeNodes` duplicates `syncChildren` and may carry the focus-blur hazard 06a found (unverified).
- **The pairing expiry is still a raw ISO string** (`connector-editor.js:457`, `'Expires ' + result.expires_at`), against DD14 as now worded. The captures masked it.
- **The single-consumer options keep piling up.** Flight 2's four are still single, joined by `status.ledTestid`, `copyField.buttonLabel`, `disclosure.summaryTextTestid`, and the sole consumers of `clearableInput` and `keyValueTable`. Most are testid plumbing (one `*Testid` option per inner node), because the registry extractor only matches `[a-z]+Testid` literals.
- **Tests with 25 fixed `wait_for_timeout` calls,** mostly "release a held response, wait 400-800 ms, assert nothing changed". Under load they can pass before the late response lands. They should wait for the released request to finish first.

### Documentation
- **`agents.md` is stale in places:**
  - `buildItemMenu` is still called "an interim interface; leg 06b replaces it";
  - `openItemMenu` is listed as per-mount state;
  - the connector frame paragraph omits the post-Save re-probe and `resetDoctorResult`.
- **The catalogue is stale:** `docs/ui-control-inventory.md:46` (copy) and `:98` (editorShell) still list the connector and `_breadcrumb()` as hand-built sites. `studio.css` has a duplicate `.connector-setup-steps-doc-ref` block (`:799`, `:810`).

## Test Metrics
The gate was `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` on HEAD 2e572f0, run alone, 26 m 53 s.

**Unit:** 6773 passed, 0 failed, 14 skipped (the netns count), 297 s.

**Browser:** 2470 passed, 1 failed, 5 skipped (WebKit contract skips), 1304 s, 12 lanes. `PARALLEL_RESULT rc=1 failed=agents`.
- The failure was `test_flow_agents_scale.py::test_filter_keystroke_cost_ratio_60_vs_10_throttled` (squawk 0230): "60-agent median 0.039 ms > 3x the 10-agent 0.005 ms".
- Triage: `agents` alone passed 161/161 in 381 s, so it is a flake.

| Lane | Wall / budget (s) | Leg 09 (s) | Tests |
|---|---|---|---|
| routing | 521 / 600 | 526 | 184 |
| agents | 442 / 540 | 456 | 161 |
| chats | 396 / 450 | 362 | 191 |
| mcp | 356 / 450 | 335 | 110 |
| providers | 330 / 420 | 311 | 129 |
| shared | 309 / 420 | 319 | 257 |
| knowledge | 279 / 300 | 229 | 59 |
| agent-tabs | 273 / 360 | 273 | 115 |
| settings | 263 / 360 | 271 | 107 |
| contracts-controls | 246 / 330 | 249 | 624 |
| contracts-overlay | 180 / 270 | 212 | 483 |
| library | 168 / 210 | 164 | 51 |

**Against earlier debriefs**

*Unit tier*
- Flight 1: 6705 in 281 s. Flight 2: 6717 in 300 s. Leg 09: 6736. Now: 6773 in 297 s.
- About +19 tests are this flight's static guards, and about +37 came from sortie 5's merge.
- Time is flat at about 300 s and still unprofiled (squawks 0222, 0234). Skips are steady at 14 under netns.

*Browser tier*
- Overall: from Flight 2's 2299 tests in 1285 s on 10 lanes to 2471 in 1304 s on 12 lanes. That is +7.5% tests for +1.5% time; the extra lanes absorbed the growth. `routing` is still the critical path.
- `knowledge`: 229 to 279 s (+22%) from the 16 HAT tests. It is at 93% of budget and past the 15% re-budget threshold, so re-budget it to 360 s.
- `chats`: 362 to 396 s (+9%), likely sortie 5's `test_flow_chat_live_updates.py`. It is at 88% of budget; watch it.
- Every other lane is within ±7% of leg 09.

*Flakes*
- Squawk 0230 recurred, its second time under `--parallel` load. The likely root cause is visible in the numbers: the 10-agent median (0.005 ms) is one tick of the browser's timer resolution, so the 3× ratio compares near-zero values. Fix it with more work per sample or an absolute floor.
- Squawk 0229 and the leg 02 `shared` OAuth flake did not recur.

## Deviations and Lessons Learned
- **The connector's stale header was not a DD5 regression.** During the HAT the FD attributed it to patch-in-place dropping a remount's auto-probe. The debrief Developer ran the pre-flight code (08562ec) and showed that an edit Save never remounted the connector editor. The header had been stale after Save since squawk 0045's "probe once on open". The flight log carries the correction. The fix (re-probe after an edit Save, clear the doctor line) stands. **Lesson:** before calling something a regression at a HAT, check the old build; it costs a few minutes.
- **The lesson behind it still holds.** No leg asked what state goes stale when config changes without a remount: probes on open, cleared result lines, re-fetched option lists, poll baselines, timers, secret re-masking, focus and scroll, store invalidation. Leg 07a listed what Save patches, never what Save leaves stale.
- **DD14 was revised for the better.** The knowledge timestamps now show humanised text, with the precise value in `title` and `data-indexed-at`. That split between what a person reads and what a test reads is worth standardising.
- **L6-D2's "Other items" became "Individual files".** It gained a remove and an orphan hold-out. The hold-out rests on two server invariants (`parent_id` ON DELETE CASCADE; `/status` `folders[]` from `list_folders`), which no test pins.
- **Main was merged mid-HAT** (sortie 5, #302) at the operator's request. It merged with no conflicts after the in-flight fixes were committed first, and the HAT instance was restarted for main's server code.

## Key Learnings
- **Parity rules preserve existing debt.** "Looks as it did before" plus masked, shallow captures means presentation problems surface only on a live, realistic walk. Survey them at planning, and approve the fixes as visible changes (the operator's decision).
- **Patch-in-place needs a side-effect inventory.** Every effect of a remount (or of the lack of one) is re-run on Save with a test, dropped with a ledger row, or accepted in writing.
- **Close checks must re-run after the HAT** when the HAT changes code: line budgets, the unused-selector report, the catalogue, the docs grep and a full gate.
- **Rules without guards drift.** The 800-line rule held through 14 legs and broke at the HAT because nothing checks it. Only `studio.js` is pinned.
- **Test-pin reasons are weak UX reasons.** DD6 kept a form-level error because tests pinned its locator, and the operator overrode it in seconds.

## Methodology Observations
- **agentic-workflow, Phase 2b, HAT legs (1.2.0).** The HAT added a feature (Individual files remove, inspect close) through the fix-or-feature gate: scoped Plan review, then implement, then Reviewer. That worked. But the skill says nothing about re-running the flight's close verification after HAT code changes. Here it cost a broken 800-line rule that only the debrief found, and a lane (`knowledge`) pushed past its re-budget threshold unmeasured. Expected: when a HAT changes code, re-run the last autonomous leg's verification (or the flight's Post-Flight Verification list) before landing. Observed in the agentic-workflow skill, Phase 2b/Phase 3.
- **agentic-workflow, Phase 2b, HAT reviewer composition (1.2.0).** The flight review used a Reviewer plus an Accessibility Reviewer. The HAT feature got only a Reviewer, because the HAT protocol names no crew composition for a feature promoted through the gate. Expected: a HAT feature gets the same review crew as the flight review. Cost: no a11y pass on a new confirm-armed icon button and a focus chain.
- **agentic-workflow, Phase 2b, HAT step authoring (1.2.0, carried from Flight 2).** Steps are now derived from the ledger, which helped: HAT items 1-6 were exact. Two steps were still wrong, because their ledger wording was not checked against the data model or the seed. Expected: the FD dry-runs each step on the seeded instance, and a destructive step names its own disposable item. Cost: two operator round-trips and a re-seed. Minor, per the operator.
- **flight, Phase 4, validation approach (1.2.0).** The flight's capture apparatus (DD2) was audited for the ability to act and observe changes, but not for the ability to observe existing problems: masks hid exactly the text the operator later objected to. The skill's two-axis apparatus audit (act and observe) covered this premise in principle, but the questions it prompts are about asserting change. Expected: for a parity-preserving migration, the planning interview asks "what existing problems will parity preserve?" Cost: about two legs of HAT work.
- **agentic-workflow, mid-HAT main merge (1.2.0).** The operator asked to merge main mid-HAT while two Developers had uncommitted edits in overlapping docs. The FD waited for both, had a Developer commit the HAT fixes, then merge. Smooth, but the skill has no guidance for a merge requested mid-HAT. Recorded only.

## Recommendations
1. **Plan Flight 4 (Settings) with a presentation-debt survey** (operator decision). At planning, walk each Settings surface on realistic data, list the obvious presentation problems, and get them approved as DD-level visible changes. Mask capture text by shape, not by label. Use one seed for both the capture and the HAT, with the edge cases (long values, error states, every conditional element).
2. **Add a remount side-effect inventory to every patch-in-place leg.** Each probe, refetch, cleared line, timer, re-mask and focus or scroll reset is re-run on Save (with a test of the post-Save state), dropped (a ledger row) or accepted. Flight 5's MCP editor has the most of these: the probe on open, OAuth popup polling and masked secrets.
3. **Guard and repay the size rule in Flight 4's groundwork leg.**
   - Add a static unit test that fails on any split area module over 800 lines.
   - Split `knowledge-folders.js` (rows and individual files into `knowledge-rows.js`) and fix its stale invariant comments.
   - Re-budget `knowledge` to 360 s.
   - Fix squawk 0230's measurement (absolute floor) before it costs another gate.
4. **Settle three mission-wide patterns before Flights 4-5 multiply them:**
   - **error placement:** validation on the field, request errors at editor level;
   - **one error reader:** `App.api.fetchJson` only, with `_errorMessageFromResponse` deleted;
   - **one "latest request wins" helper** beside `mountSlot`, and one slot placement per editor.
   Also give `App.ui.section` (or a stack primitive) the vertical rhythm between mixed children, so the pairing and doctor gap rules go away.
5. **Re-close after any HAT that changes code:** line budgets, the unused-selector report, the catalogue and docs greps, a full gate. A HAT feature gets the a11y Reviewer too.

**Carried items:**
- squawks 0237, 0238, 0239, 0240, 0243 and 0244;
- from the mission Known Issues: the search score floor (needs evals) and "Add file";
- the stale `agents.md` lines and catalogue rows;
- the pairing expiry ISO;
- the orphan hold-out's server-invariant test;
- the Flight 2 leftovers not on this path: squawks 0230, 0232 and 0234.

## Follow-up Squawks
- 0245: the connector pairing expiry shows a raw ISO timestamp (from Technical).
- 0246: docs and comments left stale by the HAT (from Documentation).
- 0247: re-budget the `knowledge` lane to 360 s (from Test Metrics).

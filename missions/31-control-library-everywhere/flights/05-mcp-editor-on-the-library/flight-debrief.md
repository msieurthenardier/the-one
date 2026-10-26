# Flight Debrief: The MCP server editor on the library

**Date**: 2026-10-26
**Flight**: [The MCP server editor on the library](flight.md)
**Status**: completed
**Duration**: 2026-10-25 to 2026-10-26.
- **2026-10-25:**
  - planning from `main` at `b1e47ae`, with two Architect cycles;
  - legs 01-11 in batches B1-B5, each with a checkpoint commit and review;
  - leg 12 started.
- **2026-10-26** (resumed in a new FD session after an overnight pause):
  - leg 12's quiet run, lane split and gate;
  - two merges of `main` (Mission 32 Flights 3 and 4, v0.12.1);
  - the behavior test, then the HAT with five inline fixes, the re-close and the landing (PR #328).

**Legs Completed**: 14 of 14: 13 autonomous legs (01-07, 08a, 08b, 09-12) plus the HAT (13).
- Planned as 12 plus the HAT; Architect cycle 1 split leg 08 into 08a and 08b.
- No leg was split, reopened or aborted during execution.

**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
The MCP server editor, the largest and riskiest editor left, is built entirely from the control library, with no surface half-migrated.

**Counts**
- **Ownership allowance:** 66 rows / 167 uses → 25 / 36. This is exactly the flight's forecast.
- **HTML-string sinks:** 23 → 5, all five in `areas/chat.js`.
- **Every MCP file is at zero sinks and zero allowance rows.** `MOVES` and `DYNAMIC_SINK_BASELINE` are empty.
- **Alias calls left in the whole app:** `App.confirmDelete(` 1, `App.showFlash(` 3, `App.icon(` 1, `App.consentLink.` 4, all in `chat.js` and `markdown.js`.

**Structure**
- `mcp-server-editor.js` went from about 2,150 lines to a 511-line controller plus eight surface modules, none over about 450 lines. Its line-guard entry is removed.
- The controller sits on `editorShell`:
  - Save and Cancel patch in place;
  - async writes are keyed on identity;
  - `destroy` is real;
  - there is one writer each for dirty (the baseline model), Test-held (`syncTestHold`) and Save-in-flight (`setSaving`).
- `tools-form-helpers.js` (the string chip list) and the legacy `.tool-enable-switch` are deleted.

**New library pieces**, contract-tested in Chromium and WebKit:
- `keyValueTable` secret and switch columns: a stored value never reaches the DOM, and a key rename clears it.
- The `editorShell` error row and `setTestState`.
- `groupTile` `expandLabel`.
- `buildMcpError` `live`.
- From the HAT: the `local`/`remote` badge kinds and `.ui-kv-center`.

**Backend (additive, tested)**
- `_cache.last_check` through one `merge_cache` helper, recording only a body-less Test of the saved server.
- `App.usage.mcpState`, so the editor status line, the Library rows and the MCPs tab cannot disagree.

**Squawks**
- **Completed:** 0203 (era docstring and negotiation doc notes) and 0259 (`chats` re-measured, the quiet-host clause).
- **Logged at planning:** 0260 (stdio "Connection closed" has no cause; this flight fixed only its wording).

**The HAT passed:** 13 steps. Steps 1-10, 12 and 13 passed; step 11, the real OAuth sign-in, was deferred by the operator. Five fixes were made inline and re-verified by the operator:
1. Local and Remote badge hues.
2. The toggletip bubble no longer inherits an uppercase container.
3. Key-value rows are top-aligned, with equal value widths.
4. `connection probe failed` gets the HTTP connection headline.
5. The delete toasts survive the editor closing.

The capture compare was approved: 50 images, every difference mapped to a ledger row. The behavior test `mcp-sensitive-headers-round-trip` passed 8/8.

### Mission Criteria Advanced
- **Every kind of control is defined once in the library** (partial): the secret and switch columns, the error row, the badge kinds. The last legacy toggle and the string chip list are retired.
- **A change to one control reaches every place it appears** (partial): 25 rows / 36 uses remain, owned by chat, `icons.js`, `markdown.js` and four `studio.css` rows.
- **No UI markup is built from HTML strings** (partial): 5 sinks remain, all in `chat.js`.
- **Each control's styles are owned by that control** (partial): the MCP-only `studio.css` families, the legacy switch and the chip-list rules are deleted or folded into their owners. The HAT added two library-owned fixes, the bubble reset and `.ui-kv-center`.
- **Every migrated surface looks as it did before, apart from approved differences:** met for the MCP editor. Ledger rows 1-36 were delivered; row 27 was amended at the HAT.
- **Every library control works by keyboard and by role in both engines** (partial): the new columns, status, disclosures and Sensitive switch are contract-tested in both engines, and the accessibility reviews found no defects.
- **The area code is organised by surface** (partial): the MCP editor split.
- **Existing behaviour holds:** the DD9 defects were fixed test-first; the server's masked-secret contract is unchanged (DD5) and was proven live by the behavior test.

## What Went Well
- **Every Flight 4 recommendation aimed at this flight was carried out:**
  - the presentation survey with operator approval (DD7);
  - batch mode with the HAT at the end;
  - one handover leg retiring the chip path and switch;
  - the `MOVES` table (recommendation 6, leg 01);
  - squawk 0259's quiet re-measure;
  - CLAUDE.md's control-library detail moved to `agents.md` (recommendation 8, leg 12);
  - the HAT-fix brief stating "a library option, never consumer CSS on library internals". All five HAT fixes landed in the owning control.
- **Split first, migrate second** (DD2/DD3). The behaviour-free split in leg 02 made every later leg a single-surface change. The `MOVES` and `SINK_MOVES` tables made the allowance edits mechanical and visible, and both ended empty.
- **Two Architect cycles at planning caught three false premises in DD6** (the server record) and the switch-deletion order before any code. No leg was split or reopened in execution.
- **One-writer discipline.** `setSaving`, `syncTestHold` and the baseline model each have a single writer. The B5 review found two defects (a throwing create callback, Delete during a Save) and the fixes landed as single-writer changes.
- **Shared derived state.** `App.usage.mcpState` makes three surfaces agree by construction. The B6 test pins each seeded server's row and editor status to the same state.
- **The behavior test proved the secrets contract end to end:** rename keeps, typing replaces, untick clears, a key rename drops, and Cancel is byte-identical. Unit and browser tests pin those one request at a time.
- **The resume across sessions was clean.** The flight log was enough ground truth for a new FD session to pick up leg 12 mid-way, with no state rediscovered.
- **The HAT did its job** (operator, 2026-10-26: "yes, what the HAT is for"). Three of the five fixes were in shared library controls: the bubble, the key-value table and toast placement. The survey and captures could not see them, because they show only when a control renders inside a real consumer.

## What Could Be Improved

### Process
- **The HAT fix pass ran no `make test-unit`** (a repeat of Flight 4's stale-test gate failure).
  - Two unit pins failed at the gate: `provider-editor.js` was one line over its shrink-only 896 ceiling, from a comment, and `test_ui_badge_kinds.py` still pinned 16 kinds.
  - Cost: one failed gate (5.5 minutes of unit tier) and a fix spawn.
  - Pinned counts and ceilings are the class that keeps breaking. Any code change after a green gate needs the unit tier plus the owning lane before the gate.
- **The lane re-budget hit a split mid-leg.** `mcp` measured 697 s against its 450 s budget, 1.55x, and the leg went `[BLOCKED:lane-split-needed]`.
  - The leg said "tell the FD before splitting", which worked. The FD moved one file to `library`.
  - The cost was a second full quiet run (1693 s), then the gate.
  - The growth was predictable from the leg-by-leg test additions: 164 → 230 tests in `mcp` by leg 11. A lane-size check at batch end would have split it before leg 12.
- **The HAT step text paraphrased the ledger instead of quoting the source.** Step 5 said the stdio headline ends "then try again", which belongs to the HTTP headlines. The operator spent a step on a non-defect. Expected strings belong in the step verbatim from the module (`js/mcp-error.js`).
- **The HAT had no sign-in fixture.** Step 11 needed the operator's real OAuth account and was deferred, so rows 7 (Reset), 19 and 31 rest on browser tests only.
- **A subagent's `git stash` check briefly reverted the flight log** while the FD was appending HAT lines. The Developer restored it and re-appended two lines; nothing was lost. Crew should never use `git stash` in a working tree the FD is editing.
- **The A20 citation named the wrong factory** (`toolTile` for `groupTile`). The citation audit checked line numbers, not that the named factory is the one the consumer calls.

### Technical
- **`App.ui.flash` with a `container` is a library API trap** (the Architect's assessment).
  - A toast appended to a container that a close or remount replaces vanishes silently. HAT fix 5 patched only the two delete toasts.
  - The created and saved flashes still target replaced containers: `mcp-server-editor.js:299, :319`, `connector-editor.js:679`, and several in `provider-editor.js`.
  - Callers must know the container's lifecycle, which is the "what the old control gave for free" trap again.
  - Fix in the library: page-level by default, or re-home when the container is disconnected at show time. Add a contract test, then audit the callers. It should land before Flight 6, because `markdown.js` uses `showFlash` and chat re-renders constantly.
- **Overlay and helper controls inherit text styles from their host.** The toggletip bubble took uppercase, letter-spacing, weight and mono from the key-value header. Every overlay or bubble control should reset inherited typography, with a contract test in a hostile container (uppercase, tracked, mono).
- **`test_flow_studio_mcp_editor.py` is 4,920 lines and the whole `mcp` lane** (490-507 s of 630).
  - One file cannot spread across lanes, and its 45 module-level helpers are not reusable.
  - Split it by concern into a package with a shared helper module (fields, env and headers, sign-in, status and tools, create and delete).
- **Small debt carried** (all from the reviews):
  - `setSaving` writes `danger.button.disabled` directly instead of through `dangerZone.setDisabled`;
  - a Delete armed before a Save comes back still armed;
  - after an unsaved key rename, the key-value row's remove button keeps the saved key's name;
  - the rename hint stays after saving an empty value under a renamed sensitive key;
  - an empty sensitive value is stored as `""` silently (a product question);
  - `provider-editor.js` sits at exactly its 896-line ceiling with no headroom;
  - `mcps-tab.js` (515 lines) is the one MCP module not split;
  - the Remote badge on the dark row surface is 2.24:1 (non-text contrast, info only).

### Documentation
- **CLAUDE.md's lane paragraph is stale.** It still says "about 24 minutes … (1470 s, 13 lanes)"; the final gate ran 1581 s, about 26 minutes. The budget table itself was updated in leg 12.
- **`the_one/agents.md` lacks four patterns:**
  - flash to the page when the action closes the item;
  - the `.ui-kv-center` strut for controls in rows that grow;
  - the overlay typography reset;
  - "a new badge kind updates the `test_ui_badge_kinds.py` pin".
- **The `mcp-sensitive-headers-round-trip` spec has three quality notes** from its Validator:
  - step 6 bundles a save and a rename (split it into 6a and 6b);
  - step 2's "row 2" depends on the server listing plain headers first;
  - `[a11y]` clauses should list an a11y snapshot under Observables.

## Test Metrics

The final gate ran on the landed tree (`448ba82`): `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`, rc=0. The debrief's Developer re-ran the unit tier and read the browser junit from that gate, since no code changed after it.

**Unit:** 7665 passed, 0 failed, 15 skipped (the expected netns figure), 334.6 s (5 m 50 s wall).
- Against earlier flights: F1 6705 (281 s), F2 6717 (300 s), F3 6773 (297 s), F4 7188 (334 s), F5 7665 (335 s).
- This flight added 477 tests with time flat: the per-flight static guards and ownership tests, the `mcp-error` and store tests, and the merged Mission 32 tests.
- The tier is still unprofiled (squawks 0222 and 0234, now carried in four debriefs).

**Browser:** 2802 tests by junit sum, 0 failed, 5 skipped (the WebKit contract skips, unchanged), `PARALLEL_RESULT rc=0 total=1581s lanes=13 failed=-`, no reruns or flakes.

| Lane | F4 final (s) | F5 final (s) | Tests | Budget (s) |
|---|---|---|---|---|
| routing | 575 | 526 | 186 | 600 |
| mcp | 358 | 507 | 178 | 630 (was 450) |
| agents | 498 | 438 | 166 | 540 |
| chats | 446 | 383 | 191 | 450 |
| contracts-controls | 341 | 344 | 966 | 480 (was 420) |
| library | 167 | 342 | 103 | 420 (was 210) |
| providers | 346 | 319 | 134 | 420 |
| knowledge | 317 | 294 | 65 | 420 |
| shared | 328 | 285 | 259 | 420 |
| agent-tabs | 313 | 282 | 126 | 360 |
| settings | 291 | 260 | 108 | 360 |
| settings-tools | 259 | 235 | 169 | 330 |
| contracts-overlay | 225 | 173 | 511 | 270 |

- **Total wall time:** F2 1285 s, F3 1304 s, F4 1571 s, F5 1581 s (+0.6%). Lane-seconds sum to about 4,330 s, so three-way packing floors near 1,450 s. The gate is near that floor, and further savings need less work, not rebalancing.
- **The real growth is `mcp`, +35%** (the editor's DD9 and contract tests). `library` grew by absorbing the 39-test list file in leg 12.
- **Every other lane ran 5-27% faster than Flight 4's final.** That is most likely a quieter host, since Flight 4's readings were taken under concurrent load; it is not attributable to code.
- **The critical path is `routing`** (526 of 600 s); `mcp` is second.
- **The test count fell from 2909 to 2802.** This could not be reconciled from the logs and is probably a different counting basis (Flight 4 may have counted skipped or parametrised cases differently). Future debriefs should state the counting method: the junit `tests` sum.
- **Within-flight full runs:** 1590 s (the first quiet run, `mcp` 697 s), 1693 s (after the split), 1579 s (leg 12's gate), 1581 s (the final gate after the HAT). One gate failed at the unit tier, the HAT pins.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 08 split into 08a (the server record) and 08b (status and sign-in) at Architect cycle 1 | The server part had to land before the status line could read it | Yes: split a leg where a server contract feeds a client in the same leg |
| `test_flow_studio_library_list.py` moved from `mcp` to `library` mid-leg 12 | `mcp` measured 1.55x its budget on the quiet run | Yes: move whole files to the lane with headroom; budget from a re-run |
| HAT step 11 (real OAuth) deferred | No local OAuth fixture; the operator chose not to use a real account | No: build a fixture (Recommendation 2) |
| Five inline HAT fixes, three in shared library controls | Visible only in a real consumer at real size | Yes: keep the HAT as the place this is caught (operator) |
| `main` merged twice mid-flight (Mission 32 Flights 3-4) | Parallel installer mission; docs-only overlap | Yes: merge at one safe point, before the quiet run and gate |
| The A6/A9 wording became clock time ("checked 3:42 PM") instead of "2 minutes ago" | `App.time` has no relative helper, and one would need a timer | Approved at planning |

## Key Learnings
1. **A control that renders inside another control inherits from it.** The bubble's case and the key-value cells' alignment were library defects that only a real consumer exposed. Contract tests for overlay and row controls should mount them in a hostile host (uppercase, tracked, a taller sibling).
2. **A helper that takes a container must survive the container.** `flash({container})` is a lifecycle contract the caller can't see. A library helper should either own its mount point or detect a dead one.
3. **Pinned counts and ceilings fail on the smallest change** (a comment line, a new badge kind). Any change after a green gate runs the unit tier, which is cheap compared with a failed 26-minute gate.
4. **Lane size is predictable from test additions.** Track lane test counts at each batch end, not only at the close.
5. **HAT expected text must be quoted from the source,** or the operator debugs the step instead of the product.

## Methodology Observations
Plugin version 1.2.3 throughout. All of these are concrete and recorded, not judged.

- **agentic-workflow, Phase 2b (HAT inline fixes) and leg-execution crew prompts.** The inline-fix protocol says "fix inline, re-verify that step", with the close checks re-run before landing. It does not tell the fix Developer to run the unit tier. The HAT fix pass ran static guards and its own lanes only, and two pinned counts failed at the gate.
  - Cost: one failed gate run and a fix spawn.
  - This is the second consecutive flight where a post-review change reached the gate untested by the unit tier (Flight 4: a stale `.area-admin` test).
  - Expected: the HAT-fix Developer brief, or the Implement prompt's leg-end step, requires `make test-unit` before signalling.
- **agentic-workflow, concurrent crew in one working tree.** A fix Developer ran a `git stash`-based check while the FD was appending to the flight log. The stash briefly reverted the FD's edits, and the Developer restored them. No loss, but a near miss.
  - Expected: crew prompts forbid `git stash` / `checkout --` in the shared tree, or the FD does not edit tracked files while a Developer is mid-pass.
- **agentic-workflow, leg design (lane budgets).** Leg 12 carried the re-budget rule and "tell the FD before splitting", and that worked. But no earlier leg tracked lane growth, so the split was discovered at the close and cost a second 28-minute quiet run.
  - Expected: batch-end checks include each touched lane's time against its budget, a rule the Flight 4 debrief already proposed for batch mode.
- **agentic-workflow, the HAT leg (step authoring).** The FD wrote step 5's expected text from the ledger row's paraphrase, and the operator chased a non-defect. CLAUDE.md's HAT design guidance asks for state-transition steps, but not for expected strings quoted from source.
  - Cost: one HAT round trip.
- **agentic-workflow, resuming in a new session.** The prior session's Developer agent was not reachable from the new FD session. The FD re-spawned a Developer with the leg's remaining list from the flight log, and it worked first time.
  - Positive: the flight log as ground truth is what made the resume cheap.
- **behavior-test, Phase 2 (Executor start).** The Executor returned `[READY]` as a hand-back, saying it had no way to wait. It was then resumed by SendMessage for each step, as the crew file intends. Its first resume briefly produced no report, so the Orchestrator re-sent step 1.
  - Cost: about one minute.
  - Otherwise live mode ran cleanly for 8 checkpoints with report-file hand-off (crew rule 9).
- **flight-debrief, Phase 2 (Developer test metrics).** As in Flight 4, the Developer read the browser junit from the landing gate (same tree, about an hour old) instead of re-running 26 minutes of lanes, and re-ran only the unit tier. This is worth allowing explicitly when no code changed since a recorded full run (Flight 4 recorded the same).

## Recommendations
1. **Fix `App.ui.flash`'s container contract in the library before Flight 6.**
   - Mount to a page-level region by default, or re-home a toast whose container is disconnected when it shows. Add a contract test in both engines.
   - Then audit every `flash(..., {container})` caller: the MCP and connector created flashes, and the provider saved and created flashes.
   - It is a shared-interface change, so it is a flight leg, not a squawk. Flight 6's first library leg is the natural home.
   - *Important.*
2. **Build a local OAuth fixture for MCP sign-in** (operator, 2026-10-26: "would be good to create a fixture"). A small authorization server plus a protected streamable-HTTP MCP fixture under `tests/fixtures/mcp/`, wired into `scripts/ui_capture.py`'s seed. It lets a HAT walk sign-in, Reset and the callback page without real accounts, and lets the capture tool show "Sign-in needed" honestly. It needs design (the OAuth flow shape, PKCE, the token lifetime), so it is a sortie or a Flight 6 leg. *Important.*
3. **Make the unit tier mandatory after any post-gate change.** Every fix pass (review fix, HAT fix) runs `make test-unit` plus its owning lane before signalling. Put it in the HAT-fix brief and in the project's crew prompts (`.flightops/agent-crews/leg-execution.md`, Implement and Fix Review Issues). *Important; repeat finding.*
4. **Plan Flight 6 (chat and markdown) as one flight, split first.** This answers Flight 4's recommendation 5, "revisit Flight 6's scope at Flight 5's debrief". By this flight's evidence, the remainder is one flight's work: 5 sinks, 25 rows / 36 uses, 9 alias call sites, all in `chat.js` (2,399 lines) and `markdown.js` (830). Shape:
   - a behaviour-free `chat.js` split leg first;
   - the flash fix (Recommendation 1) as the first library leg;
   - squawk 0249 (chat's OAuth wait) folded in on the `mcp-oauth-consent.js` pattern;
   - negative security tests for `markdown.js` before any sink moves;
   - the alias shims deleted in the closing leg;
   - an early decision on whether any streaming sink is a recorded exception.

   Re-measure `chats` (383 of 450 s) first and split it before adding tests. *Important.*
5. **Split `test_flow_studio_mcp_editor.py` by concern** into a package with a shared helper module, so `mcp` can become two lanes and stop sitting at 80% of a single-file budget. Squawk below. *Minor.*

**Carried items:**
- squawks 0222 and 0234 (profile the unit tier with `--durations=30`);
- 0249 (into Flight 6);
- 0260 (the stdio cause text);
- the mission's knowledge search score floor and "Add file";
- `setSaving` → `dangerZone.setDisabled`;
- the Delete-armed-across-Save behaviour;
- the empty-sensitive-value product question;
- the Remote badge's dark-row contrast (info);
- the behavior spec's three quality notes;
- the four `agents.md` patterns and the stale CLAUDE.md lane-time sentence.

## Action Items
- [ ] Flight 6 planning: the flash container fix (Recommendation 1), the split-first shape and `chats` re-measure (Recommendation 4), squawk 0249.
- [ ] A sortie or leg for the OAuth MCP fixture (Recommendation 2).
- [ ] Add "run `make test-unit` before signalling" to the leg-execution crew prompts (Recommendation 3).
- [ ] Squawks for the small, bounded follow-ups (see Follow-up Squawks).
- [ ] The `agents.md` patterns and the CLAUDE.md lane-time sentence, at Flight 6's close or as a docs squawk.

## Follow-up Squawks
Logged by the operator's decision on 2026-10-26, all `routine` and left open:
- **[0269](../../../../squawks/0269-kv-remove-name-stale-after-key-rename.md)** (defect): the key-value row's remove button keeps the saved key's name after an unsaved rename.
- **[0270](../../../../squawks/0270-rename-hint-lingers-after-empty-save.md)** (defect): the rename hint and Show button stay after saving an empty value under a renamed key.
- **[0271](../../../../squawks/0271-split-mcp-editor-browser-tests.md)** (servicing): split the 4,920-line MCP editor browser test file by concern (Recommendation 5).
- **[0272](../../../../squawks/0272-lane-time-sentence-and-agents-md-patterns.md)** (servicing): the stale CLAUDE.md lane-time sentence and the four missing `agents.md` patterns.

Kept as recommendations, because each needs a design call:
- the `App.ui.flash` container contract (Recommendation 1);
- the OAuth MCP fixture (Recommendation 2);
- the empty-sensitive-value question.

# Mission Debrief: Every control comes from one library

**Date**: 2026-10-28
**Mission**: [Every control comes from one library](mission.md)
**Status**: completed
**Duration**: 2026-10-15 (plan, `dbcd4587`) to 2026-10-28 (Flight 6 merged as #332; released in v0.12.3)
**Flights Completed**: 6 of 6 planned, plus Flight 7 (optional alignment), which the operator skipped on 2026-10-28.
**Plugin version**: mission-control 1.2.0 (Flights 1-4), 1.2.3 (Flights 5-6 and this debrief)

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| The Design language page is gone | met | Its route, Settings entry and Jump to entry are gone, along with every dependency (Flight 1). Only prose remnants remain: the `tokens.css` header comment ("Design Language v3"), one `admin.css` comment and a `tests/test_nav_helper.py` comment. |
| Every control is defined once; the catalogue has no "not yet defined" row; every surface builds through the library | met | `docs/ui-control-inventory.md` has no such row, and `tests/test_ui_control_inventory.py::test_no_control_row_is_not_yet_defined` enforces it. `js/ui/` grew from 16 to 29 files. Structural copies (the same DOM under new class names) are outside the guards by design (open question 3), so they stay a review item. |
| A change to one control reaches every place: the reuse check's exception list is empty | met | `OWNERSHIP_ALLOWANCE`, `TOTAL_USES`, `MOVES` and `START_ROWS` are empty, from 243 rows / 504 uses at Flight 1's close. `tests/test_ui_emitted_classes.py` checks the other direction (every emitted class has an owner). |
| No HTML-string markup outside the markdown renderer; icons are nodes | met | `HTML_SINK_ALLOWANCE` is `{}` and `SINK_TOTAL` is 0, from about 130 sinks in 25 files at planning. The `App.icon`, `App.iconNode`, `App.confirmDelete`, `App.showFlash`, `App.consentLink`, `App.escapeHtml` and `App.escapeAttr` aliases are deleted, and `tests/test_ui_ownership.py` keeps them as a regression guard. The sink check is a text scan (see Lessons Learned). |
| Each control's styles are owned; no area stylesheet restyles a control; unused rules are removed, with each flight reviewing the report | met | Ownership is enforced by the reuse check. `scripts/unused_selectors.py` on every stylesheet reports **0 unused** (FD run, 2026-10-28). Total CSS went from 5,843 lines to 4,842 (-17%): `studio.css` 1665→1004, `admin.css` 719→132, `chat.css` 770→325. `components.css` grew 2135→2846, because owned rules moved into it. |
| Every migrated surface looks as before, apart from approved differences | met | Each flight took before and after captures (local, never committed). The operator approved each flight's visible changes on a review page before implementation, and the capture set at each HAT. Every difference maps to a numbered ledger row. |
| Every control works by keyboard and role in Chromium and WebKit; the three known gaps are fixed | met | Every factory has an engine-parametrized contract file (`contracts-overlay`, `contracts-chat`, `contracts-controls`, under `THE_ONE_REQUIRE_WEBKIT=1`). The three gaps are fixed: the pill toggle is replaced by `App.ui.toggle` (`role=switch`); the knowledge-base attach toggle is reachable by role (squawk 0094, `test_flow_studio_knowledge_attach.py`); the KB item menu is `App.ui.menu`. One stale note remains: the catalogue's Checkbox row still mentions hand-built checkboxes and 0094. |
| The area code is organised by surface; no entry module is over 800 lines | met | `studio.js` 4181→752, `chat.js` 2268→565, `admin.js` 760→384. Splits: `studio/` (F2), `knowledge-section` (F3), the admin tools page (F4), the MCP editor (F5), `chat/` with 14 modules (F6). `studio/provider-editor.js` (895) is the only module on the line-guard allowance; it is not an entry module. |
| The catalogue documents every control; a new control without a row and contract tests fails the unit gate | met | `tests/test_ui_control_inventory.py` enforces both. Tokens and type are in the catalogue's "Tokens and type" section. The Retired table holds the removed rows. |
| Existing behaviour holds: unit, browser (both engines) and lint pass; the UI behavior specs pass; every testid survives or is recorded as retired | met | The final gate (Flight 6 debrief, quiet host) passed: unit 7845 passed / 15 skipped; browser `rc=0`, 3574 tests, 16 lanes, 1695 s. The mission-close spec sweep passed in Flight 6 leg 09b, and the re-authored specs again at its HAT. `test_retired_selectors_cover_the_registry_retired_table` holds the testid registry. Exception: `chat-loop-hang-and-cancel` has never run (see What Could Be Improved). |

### Overall Outcome
**Achieved, as intended** (the operator, 2026-10-28: "yes, as intended").
- Every control the app renders has one definition in `js/ui/`.
- The guards fail on any drift: owned classes, emitted classes, sinks, retired APIs, catalogue rows and module size.
- The look and feel is unchanged apart from approved resolutions.
- A global change to a button, toggle, tile, editor header or chat bubble is now one edit.

The outcome stayed the right goal throughout. It is what Mission 25's debrief named as its unfinished half, and it is what issue #207 asked for.

The mission also delivered more than its library charter, through operator-approved features:
- the chat's reply Copy and step-limit notice (Flight 6 planning);
- several queued messages, Chats row activity, per-chat drafts and the step-limit Continue (Flight 6 HAT);
- the Individual files actions (Flight 3 HAT).

Each went through the fix-vs-feature gate with its own design review. These shipped in v0.12.3 (2026-10-28).

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1. Library completion and a stateful pilot | completed | Design language page retired; open questions settled (patch in place, styles in owned sections of `components.css`, the count-anchored reuse check, icons as nodes); the editor shell and about a dozen controls; the provider editor pilot. 9 legs (6 planned). |
| 2. Agents on the library | completed | `studio.js` 4181→modules; the agent editor and six tabs; tabs, source/category tile, tristate, chip list. The largest re-plan: 18 legs against 12 planned, and leg 10 split three ways. |
| 3. Knowledge and connectors on the library | completed | The knowledge-base and connector editors; disclosure and the key-value table core; the KB menu on `App.ui.menu`; squawks 0100, 0191, 0192. 15 legs, every split made at planning. |
| 4. Settings on the library | completed | Every Settings page; the `admin.js` split; banner, page header, inline `searchList`, the tools tile; `App.tabs` retired. 25 legs, the largest flight. Batch mode began here. |
| 5. The MCP server editor on the library | completed | The riskiest editor, alone: masked key-value column, OAuth polling, live status; 14 legs. The flash container defect was found here and carried into Flight 6. |
| 6. Chats, and closing every count to zero | completed | The `chat.js` split; six chat controls with update handles; markdown security; the model list; every count at zero; four HAT features. 19 legs. Released as v0.12.3. |
| 7. Alignment *(optional)* | skipped | Operator decision at Flight 6's close. |

## What Went Well
- **The guards turned "completeness" into a number that only shrinks.** The ownership allowance (243 rows / 504 uses), the sink allowance (about 130), the alias call counts and the line guard each fell flight by flight. `MOVES` covered every split, so no flight could quietly add debt. At the close, each guard was flipped to "empty means any use fails". That is what makes the outcome durable rather than a snapshot.
- **Behaviour-free splits came first.** `studio.js` (F2), `knowledge-section.js` (F3), `admin.js` (F4), the MCP editor (F5) and `chat.js` (F6) were each split before anything was migrated. Every later leg, and every late HAT feature, landed in a small module with an obvious home. No flight had to untangle a monolith and a migration at once.
- **Review pages with up-front operator approval** (the operator: "review pages worked"). From Flight 4 on, a presentation survey plus a one-page decision sheet (A items, B items, D questions) let the operator decide every visible change before implementation. HATs then found almost no visual surprises; what they found was behaviour.
- **The visible-differences ledger** (adopted after Flight 2's debrief). Every leg appended numbered rows, and the HAT walked the ledger rather than memory. It also anchored the before and after capture comparison.
- **The flight log as ground truth.** It made three session restarts (F2 auth expiry, F5 overnight, F6 context resets) cheap. Each resumed Flight Director or Developer picked up from the log with no lost work.
- **The fix-vs-feature gate.** It promoted six operator requests across Flights 3 and 6 into reviewed legs, instead of letting them ride as "fixes". In Flight 6 the reviews caught three real state bugs before the operator saw them.
- **Quiet-host discipline** (squawk 0259's rule). Lane budgets were read only from quiet `--parallel 3` runs, so re-budgets were trustworthy. Five lane splits kept the gate near its 3-lane floor while the browser suite grew from 2,054 (Flight 1) to 3,574 tests.

## What Could Be Improved
- **Flights were far bigger than planned.** The flight skill says "typically 1-4 legs". These flights ran 9, 18, 15, 25, 14 and 19 legs. Most extra legs came from design review splitting legs that mixed risk types (a migration plus a cleanup, two control families). That was the right call each time, but it was not anticipated at planning. Flight 2 grew from 12 to 18 legs mid-flight; from Flight 3 on, splits moved to planning (Flight 6 split three legs at Architect cycle 1). The operator judged the outcome worth it ("keep it"). Still, at planning, one leg per control family or per surface would have matched what design review produced.
- **Late changes kept escaping to the gate untested.** An untested late change failed the next full gate in four flights:
  - **F3:** HAT code changed, and the close checks were not re-run; the 800-line rule broke, and only the debrief found it.
  - **F4:** a stale test survived a batch.
  - **F5:** a HAT fix pass skipped the unit tier, and two count pins failed.
  - **F6:** a HAT feature's pin sweep missed an exact-dict pin in another lane.

  Each cost a 25-30 minute gate re-run. Recommended in Flight 5 and written into Flight 6's DD13, but it reached the crew file only in this debrief (see Methodology Feedback).
- **HAT step authoring.** Three flights (F2, F3, F5) had a HAT step whose expected text came from a paraphrase rather than from the code, the seed or a DD. Each cost an operator round trip chasing a non-defect.
- **The planning survey looked at screens, not workflows.** Flight 6's HAT surfaced four daily-use gaps. The operator says some were foreseeable: the one-slot queue, the lost draft.
- **A never-run behavior spec.** `chat-loop-hang-and-cancel` was re-authored in two Flight 6 legs and has never run, because its apparatus needs a live paid provider.
- **Process notes for the project, now fixed locally:** an Accessibility Reviewer was skipped once (an F3 HAT feature), and a `git stash` in the shared tree briefly reverted the FD's edits (F5).

## Lessons Learned
- **Technical:**
  - **A library migration needs a ratchet.** An exception list that only shrinks, with explicit split bookkeeping, plus a final flip to empty. Without it, #207's warning ("three ways where there were two") would have come true halfway.
  - **New class names, then a handover** (F1's `toolTile` precedent, Flight 6 DD4). This is the way to put a new owned control under an old surface without creating uncovered allowance rows.
  - **Guards that scan text can be gamed.** `el['inner'+'HTML']`, `createContextualFragment`, `DOMParser` into a live node, or a computed class string would pass the sink and ownership checks. That is acceptable for a single-maintainer codebase, but an AST-based sink check is a cheap hardening (Architect).
  - **Owned sections in one stylesheet** were the right call for the reuse check. At 2,846 lines with no visible section markers, though, `components.css` is hard to read by owner. A per-control split, or machine-readable section markers, is the next step before the library grows again.
  - **The chat's shared `state` object** (`areas/chat/session-state.js`, read and written by about 14 modules) was the pragmatic way to split the monolith, but it is global in effect. Flight 6's drafts model (`draftOwner` / `draftEpoch` / `promotedKeys`) shows the cost: async routing logic layered over shared state.
- **Process:**
  - **Put operator taste decisions in the planning interview, not mid-flight.** Then the run can go unattended to the HAT (F1, then every flight).
  - **The planning survey decides looks.** A usage walk is also needed to decide behaviour.
  - **A pin sweep must cover payload shapes, not only names.**
  - **Batch mode with one closing HAT** suits library-migration flights. The operator prefers it as the default.
- **Domain:**
  - **Behaviour is what the operator notices.** The operator approved every visual resolution from text and screenshots. What came up in use was chat behaviour: queueing, drafts, status, continuing.

## Methodology Feedback
Plugin version 1.2.0 for Flights 1-4 and 1.2.3 for Flights 5-6. These restate observations already recorded in the flight debriefs; the source flights are named so a later sweep counts each occurrence once.

**Methodology observations** (each reproduces from the methodology alone and cost something):
1. **No flight-size guidance once design review splits legs.** *agentic-workflow Phase 2a; flight skill "Flight Sizing".*
   - The skill says "typically 1-4 legs" and never revisits that when review splits push a flight to 15-25 legs.
   - Cost: a mid-flight operator request to speed up (F4), long HATs, and seven checkpoint commits in one flight.
   - Recurrence: **4 of 6 flights** recorded or showed it: F1, F2 and F4 recorded it; F6 has 19 legs.
   - Expected: a nudge to reconsider splitting the flight past roughly 15 legs, or sizing guidance that counts "one leg per risk type".
2. **Re-verification after late changes is not a step.** *agentic-workflow Phase 2b (HAT inline fixes and features) and the crew prompts.*
   - After a HAT fix, a review fix or a post-gate change, the skill does not require the unit tier or the flight's close checks before landing.
   - Cost: a failed full gate (25-30 min) or a debrief-found breakage.
   - Recurrence: **4 of 6 flights** (F3, F4, F5, F6).
   - Fixed locally in this project's crew file. It recurs from the methodology for any project that has not.
3. **Test-breakage enumeration is a lesson, not a mechanical leg-design step.** *agentic-workflow Phase 2a, "Interface changes".*
   - The consumer grep is worded for symbols. It missed moved identifiers (F1: four legs), a stale test (F4) and a response-shape pin (F6).
   - Cost: review rework (F1); a failed gate (F4, F6).
   - Recurrence: **3 of 6 flights.**
4. **HAT steps are not derived from the source of truth.** *agentic-workflow Phase 2b, HAT leg design.*
   - Steps written from memory or a ledger paraphrase contradicted the design or the seed.
   - Cost: one operator round trip each (one in F3 was two plus a re-seed).
   - Recurrence: **3 of 6 flights** (F2, F3, F5).
   - Expected: steps quote the DD, leg or source text, and are dry-run on the seed.
5. **No guidance for promoted HAT features.** *agentic-workflow Phase 2b, the fix-vs-feature gate.*
   - The gate worked, but the skill names no review crew (F3: no a11y pass on a promoted feature). It also does not say whether the 3-cycle code-review cap applies per feature or per HAT batch (F6: four features reviewed as one batch reached cycle 3).
   - Cost: a missed a11y pass (F3); no review margin left (F6).
   - Recurrence: **2 of 6 flights.**
6. **The planning survey is not in the flight skill.** *flight Phase 3/4.*
   - The presentation survey with up-front approval was the mission's most effective planning step (F4, kept in F5-F6). But it is project practice, and it surveys states, not workflows (F6: four HAT features).
   - Cost: four post-close legs and a 3-cycle review (F6).
   - Recurrence: recorded in **2 flights** (F4 positive, F6 limitation).
7. **The debrief Developer is told to re-run the full suite** even when an unchanged commit has a recorded full run. *flight-debrief Phase 2.*
   - Cost: about 33 minutes of host time that confirmed the landing gate within 1% (F6). F4 and F5 deviated from the skill to avoid it.
   - Recurrence: **3 of 6 flights.**
8. **No in-flight lane-budget tracking.** *agentic-workflow, batch verification.*
   - Lane growth was found only at the close.
   - Cost: a second 28-minute quiet run (F5); an unmeasured lane past its threshold after a HAT (F3).
   - Recurrence: **2 of 6 flights.**

**Local fixes** (this project's own crew file; applied in this debrief, operator-approved 2026-10-28, to `.flightops/agent-crews/leg-execution.md`):
- The Accessibility Reviewer is required for any UI flight or promoted HAT feature (F1, F3).
- Every fix pass runs `make test-unit` plus its owning lanes before signalling (F3-F6, the local half of observation 2).
- The Implement prompt asks for a pin sweep that covers response shapes (F1, F4, F6, the local half of observation 3).
- A shared-tree rule: no `git stash`, `checkout --`, `restore`, `reset` or `clean` (F5).
- Batch mode is written down as the default for UI migration flights, with its batch-end grep, lane-budget check and quiet-host rule (F4-F6).

**Local lessons** (no observable cost from the methodology itself):
- The design-review cap was overridden once (F2, a rewritten leg; the flight review found nothing).
- No re-tier trigger fired for a leg that grew (F2).
- Merging a plan PR from the FD session was refused by the harness (F1).
- A mid-HAT main merge (F3).
- A behavior-test Executor start hiccup (F5, about a minute).
- The CLAUDE.md credential error (F6) is a project doc defect: squawk 0278.

## Action Items
- [ ] Squawk 0278: fix CLAUDE.md's credential instruction before the next behavior-test run.
- [ ] Squawks 0279-0282 (MCP Save after a save, the `track_turn` guard, the two spec follow-ups) and the carried 0222/0234 (profile the unit tier: 281 s → 349 s over the mission), 0260, 0273, 0275, 0277.
- [ ] Doc touch-ups (a squawk or the next maintenance pass): the catalogue's stale Checkbox row and the "next mission" phrasing in older rows; the `tokens.css` "Design Language v3" header comment.
- [ ] `/mission-control:routine-maintenance`, now that the mission is closed. Candidates:
  - an AST-based sink check;
  - `provider-editor.js` (895) off the line guard;
  - a `components.css` per-control split or section markers;
  - the chat `state` object;
  - `routing` (90% of its budget) split before the next router test.
- [ ] `chat-loop-hang-and-cancel`: run once with a live key, or rewrite its hang path on the mock provider.
- [ ] The mission's two open Known Issues (the knowledge search score floor; "Add file" in the knowledge-base editor), both needing design: a sortie or a later mission.
- [ ] The OAuth MCP fixture sortie (Flight 5 debrief, Recommendation 2).
- [ ] Next UI planning conversation: a usage walk alongside the presentation survey (observation 6).
- [ ] When the operator chooses, `/mission-control:service-report` can sweep these observations across missions. Observations 1-4 recur in 3-4 of 6 flights here.

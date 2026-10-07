# Mission Debrief: Workbench Navigation and Control Library

**Date**: 2026-10-07
**Mission**: [Workbench Navigation and Control Library](mission.md)
**Status**: completed
**Duration**: 2026-09-30 – 2026-10-07
**Flights Completed**: 6 of 6
**Plugin version**: mission-control 1.2.0 (every flight)

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| SC1: Workbench navigation | met | Rail, destination router and legacy redirects (F2). `workbench-navigation` 28/28 and `shell-navigation-smoke` 8/8 at the close. |
| SC2: Lists stay put, work is never lost | met | Leave guard (F2), list and detail with create-opens and no Back (F3), the jump-to and Chat-action half (F4). `list-and-detail` 38/38 at the close. |
| SC3: Start a chat by choosing an agent | met | Picker, cross-agent Chats list, read-only drawer (F4). `start-a-chat` 26/26 and `chat-roundtrip` 9/9 in both themes. |
| SC4: Agents at scale | met | A–Z list, filter by name, model and provider, a throttled-Chromium filter gate (F3). A 31-agent seed at the close. |
| SC5: Jump to anything | met | Ctrl K and the rail control (F4). `jump-to-palette` 24/24. Ctrl K in WebView2 confirmed by the operator (F6). |
| SC6: One reusable control library | met | 16 `App.ui` factories (ES5, no build step), each with a demo, an inventory row and two-engine contract tests (672 in the contracts lane). The large editors are not migrated (#207, open). |
| SC7: Deep-violet design language | met | Gated in both themes with one band-pinned exception. In-repo reference and published design system updated (F1, F6). |
| SC8: Matches the approved samples | met | §15 register resolved, §13 deviations D1–D9 operator-accepted. The operator's v0.10.0 use plus the light walk: "the walk looks good". |
| SC9: The window belongs to the product | met | Tinted native title bar, first-launch size (F5). The operator's packaged-app walk: "All fine". |
| SC10: Operable and regression-safe | met | Keyboard and focus throughout. At the close, unit 5439 passed, all six lanes green, the guards passed, and seven behavior specs passed in both themes. |

### Overall Outcome

**The outcome was achieved.** The operator works in one workbench: a slim rail to Chats, Agents, Library and Settings.
- Every place keeps its list on screen beside the open item.
- Unsaved work always asks before it is lost.
- A chat starts by choosing an agent.
- Ctrl K reaches anything.
- The packaged desktop window wears the workbench's colours.

**One part of the outcome is only partly delivered**: "every control on the redesigned surfaces comes from one reusable control library".
- **Delivered:** the shell, lists, navigation, picker, palette, modals and drawer use `App.ui`.
- **Not migrated:** the editor bodies. These are the string-built provider, MCP, tools and agent-tab editors, plus the DOM-built connector and knowledge editors.

SC6's wording ("on the redesigned surfaces") is met, because the editors kept their bodies and gained only chrome. The operator raised it at the close (issue #207, reviewed and kept open), and it is the natural next mission.

**The goal was still right by the end.** The operator's alignment reports were refinements (labels, times, start pages, error copy), not reversals. The operator released v0.10.0 mid-mission (after Flight 5) and used it daily before the final walk.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F1: Control library foundation | completed | An ES5 factory mechanism, chosen on evidence across three engines. The core controls, guards, design-language page and inventory. Deep violet app-wide. |
| F2: Shell and router | completed | The rail replaces the top bar. A destination-first router with legacy redirects. One leave guard (`App.nav`). `App.store`. |
| F3: List and detail | completed | Agents, Library and Settings as a list beside the detail. Create opens the item; the breadcrumb replaced Back. The operator checkpoint turned Providers into tiles (D5). |
| F4: Chats and jump-to | completed | The agent picker, the pending chat, the cross-agent Chats list, the drawer, the composer, the Ctrl K palette. |
| F5: Window chrome | completed | A research-answered spike, then a tinted native title bar (operator's choice), first-frame theming, a 1440×900 first launch, a doctor gate. Released as v0.10.0. |
| F6: Alignment | completed | The carried squawks and seven operator-decided refinements, the light walk, the mission-close re-runs (147 checkpoints) and the gates. Releasing as v0.10.1. |

### Flight Patterns

- **Smooth flights: F1, F2, F5.** Each had one clear decision cluster settled by evidence or an early operator choice (the factory mechanism, the router contract, the tinted bar). Their apparatus was in place before the legs that needed it.
- **The checkpoint and alignment flights drew operator input after landing: F3, F4, F6.**
  - F3's operator checkpoint changed Providers to tiles after the close gate, which reopened a landed flight.
  - F4 landed with its preview questions pending.
  - F6 grew from five legs to ten through operator reports.

  All of it was handled well, but the cost was spec re-authors and re-runs each time.
- **A pattern across flights: leg splits at the leg design review** (F2, F4, F5, F6). A leg that combined a behaviour change with a mass test migration, or two consumers of one file, was split every time.
- **Another pattern: behavior-test apparatus friction** (F1–F5).
  - The goldfinch screenshot and input gaps forced a CDP-driven Chromium.
  - Context lifetime, concurrency and variants were improvised each flight.
  - The fix (squawk 0121's crew-file recipe, F6) paid off at once: the F6 close gate ran seven specs in about an hour.

## What Went Well

- **The control-library contract is the mission's best structural output.**
  - Its rules: ES5 factories, native elements, caller-supplied testids, no HTML-string sinks, a design-language demo, an inventory row, two-engine contract tests.
  - It is enforced mechanically (`tests/test_ui_control_inventory.py`, the UI guards). Later flights added controls without drift.
- **One navigation model.** The destination-first router, a single leave guard with a synchronous clean fast path, and `go` versus `sync`. A class of dirty-confirm bugs (squawk 0082) closed by construction.
- **Test-apparatus guards kept large migrations cheap:**
  - `_nav.py` and `_lists.py`;
  - the retired-selector registry;
  - the testid registry;
  - complementary lanes, whose union is always the whole suite.

  F4 flipped helper bodies rather than tests ("change the helper, not the 200 tests").
- **Decisions were made out loud and on evidence.** Spikes decided F1's mechanism and F5's chrome. Every operator report in F6 went through the fix-or-feature gate and became a DD or a GitHub issue (#223–#226), never silent scope.
- **Behavior specs with live Executor and Validator pairs caught what tests could not:**
  - F3's create-mode Cancel defect;
  - F4's apparatus issues;
  - F6's unthemed bare links, which every unit and browser test missed.
- **The squawk discipline.** 25 squawks were logged and completed inside the mission (0101–0126), most batched into the next convenient leg. The log did not rot: the six still open from the close (0127–0132) are a day old.

## What Could Be Improved

- **The editors were never migrated.** The large editor bodies use no `App.ui` factory, and the codebase now has three idioms:
  - string-built editors, with about 96 `innerHTML` sinks held by a freeze guard that nothing drives down;
  - hand-rolled DOM editors;
  - `App.ui` in the shell.

  The danger zone is hand-written five times, and `_el`, `_fieldGroup` and `_section` are copied two or three times each. Flight 6 paid this tax repeatedly: six `App.focusAfter` call sites, the same stale-title bug in two editors, re-render versus patch-in-place focus differences, about 50 section-title sites. Scope the next control-library mission to finish it (#207), rather than leaving it to opportunistic migration.
- **The area monoliths grew instead of shrinking.**
  - `areas/studio.js` is about 4000 lines and `chat.js` about 2100. The mission added routing and adapters to them.
  - `app.py` is about 3200 lines, with the WebSocket cancel bookkeeping as module-level state.
- **Operator-input points were placed after close gates.** F3's checkpoint and F4's preview both landed before the operator saw the work, so their answers reopened landed flights or carried questions forward.
  - **The cost:** one extra leg, six spec re-authors and four re-runs (F3), plus carried questions (F4 to F6).
  - **The lesson:** put the visual checkpoint before the behavior close gate.
- **Planning decided UI semantics before the operator saw the pages.** Two decisions were superseded within the flight that made them: F6's hidden root `h1` (DD11, replaced by DD15) and F6's ordered walk (DD6, replaced by DD18).
- **Gate time.** A full sequential gate is about 53 minutes: unit about 12, plus the browser lanes about 41. Every leg ran the unit suite plus several lanes. The harness's 30-minute background cap cut one gate.
- **Documentation weight.** The always-loaded CLAUDE.md carries per-leg detail for Missions 21–25. `agents.md` is about 2300 lines with about 150 headings.

## Lessons Learned

- **Technical:**
  - **Native elements.** They plus ES5 factories made a library that two engines and a WebView shell accept without a build step. Keep it, and make the editors use it.
  - **One shared helper, not per-site fixes.** A rule added late as per-surface fixes recurs at every site. F6's `formatClock`, focus-after and section labels each went the right way: one helper or recipe, applied everywhere.
  - **The script-count pin.** A hand-maintained pin on `index.html` scripts discouraged new modules, so two helpers were placed in the wrong files. A guard should never make the right structure costlier than the wrong one (squawk 0128).
  - **Re-render versus patch in place is a design decision.** Editors that re-mount on a store notification lose focus and state. Editors that patch built-once nodes do not. Decide it once, in the editor shell.
- **Process:**
  - **Operator time.** Put it before the close gate and use it for decisions. F6's "fixes first, then the walk" ran the walk on reviewed code and kept it light.
  - **Apparatus.** A behavior spec whose apparatus does not exist yet is a sketch until a dry run (F5). A crew-file recipe beats a hand-appended prompt every time (0121).
  - **Transient UI states** (an armed delete that lapses in about 3 s) need to be stated in a spec, or a live-judged run re-arms by ruling (F6).
- **Domain:**
  - **What the operator wanted.** Quiet copy and plain errors; the operator thinks in agents, not providers (DD10's "Available models" came from a report that models could not be picked on the provider page).
  - **Their lived use was the best acceptance test.** A day with v0.10.0 produced every F6 refinement, and the formal walk added none.

## Methodology Feedback

Plugin version 1.2.0 throughout. These entries restate observations the flight debriefs already hold. The flights cited are where each occurred, so a later sweep reading both artifacts counts each occurrence once.

### Methodology observations (reproduce from the methodology, with an observable cost)

1. **Flight skill, Phase 5b: the design-review cap reached with a high issue outstanding.** Seen in **4 of 6 flights**: F1, F2, F3, F4.
   - **What happened:** the cap of two Architect cycles left the final flight text unreviewed. Per-leg reviews were the backstop.
   - **Expected:** a third cycle for flights touching a protocol or lifecycle, or explicit guidance that per-leg design reviews are the sanctioned backstop.
   - **Cost:** a missed gate on the final spec text each time, with no rework traced to it.
2. **Agentic workflow, Phase 2a and the flight skill's leg identification: legs split at their own leg design review.** Seen in **4 of 6 flights**: F2, F4, F5, F6.
   - **What happened:** legs combining a semantic change with a mass test migration, or two consumers of one file, were split each time.
   - **Expected:** a sizing heuristic at flight planning to pre-split them.
   - **Cost:** re-planned legs and extra design-review cycles (F4: two splits, one extra cycle).
3. **Behavior-test skill, Phase 4: no notion of variants (themes).** Seen in **3 flights**: F2, F3, F6.
   - **What happened:**
     - checkpoints doubled (F2, about 100 orchestration messages);
     - a Light choice did not carry into a fresh tab, so four Light checkpoints ran on Auto (F3);
     - Executors adapted one variant's report from the other's text twice (F6).
   - **Expected:** variant guidance: set the variant in its own fresh context before the first checkpoint, and write each variant's reports from its own evidence.
   - **Cost:** a recorded apparatus deviation (F3) and two Validator re-checks (F6).
4. **Behavior-test skill, Phase 2: apparatus discovery assumes MCP browser tools, with no degraded-apparatus path.** Seen in **4 flights**: F1, F2, F4, F5.
   - **What happened:** goldfinch screenshots were missing (F1) and its input stopped mid-run (F2). CDP context lifetime lost state (F4). The recipe was hand-appended (F5).
   - **The local fix:** squawk 0121 (F6).
   - **Expected:** an input-delivery probe and a sanctioned fallback in the skill.
   - **Cost:** an aborted Executor (F2), a checkpoint re-run and a step redo (F4).
5. **Behavior-test skill: concurrency is unaddressed.** Seen in **3 flights**: F2, F4, F6.
   - **What happened:** scratch-name collisions caused two checkpoint redos (F2). A per-run ledger and a report-file hand-off were improvised (F4), then carried in the crew file (F6).
   - **Expected:** concurrent-run guidance (per-run scratch, a ledger, the report-file hand-off, a concurrency cap).
   - **Cost:** two redos (F2) and one late verdict (F4).
6. **Executor crew prompt: unrequested state-changing actions.** Seen in **3 flights**: F2, F3, F6.
   - **What happened:** a supplementary probe altered history (F2), and an Executor re-opened a dialog (F3). A duplicate background script ran (F6, a no-op).
   - **Expected:** the rule "no unrequested state-changing actions" in the skill's default Executor prompt.
   - **Cost:** one checkpoint re-run and a wrong interim hypothesis (F2).
7. **Mission and agentic-workflow skills: no state for "landed, awaiting operator input".** Seen in **3 flights**: F3, F4, F5.
   - **What happened:** F3's post-gate checkpoint reopened a landed flight. F4 landed with its preview pending. SC9 stayed open across F5 for F6.
   - **Expected:** guidance to hold operator checkpoints before the behavior close gate, or a sanctioned waiting state.
   - **Cost:** at F3, one extra leg, six spec re-authors and four re-runs (60 checkpoints).
8. **Flight-debrief skill, Phase 2: a full suite re-run duplicates a fresh gate.** Seen in **2 flights**: F5, F6.
   - **What happened:** the gates had run minutes earlier on identical code, so the metrics were reused, a deviation from the skill text.
   - **Expected:** accept recent gate metrics on an unchanged tree.
   - **Cost:** none, apart from the documented deviation.
9. **Agentic workflow, PR lifecycle: autonomous merges and stacked flights.** Seen in **2 flights**: F1, F4.
   - **What happened:** the merge was denied by session policy (F1), so flights stacked; a stacked PR then needed a rebase after a squash merge (F4).
   - **Expected:** a note on operator-gated merges and stacked-flight PR bases.
   - **Cost:** a pending rebase (F4).

### Local fixes (this project's crew files or `ARTIFACTS.md`)

- The behavior crew file now carries:
  - the CDP recipe, PID-only kills, the report-file hand-off and the ledger (squawk 0121, done);
  - "you are resumed by SendMessage" (F4 leg 8, done).
- Still to add to the crew file: the rule that each variant's report is written from its own evidence, and the background-cap rule for long gates (`run_in_background` with an explicit timeout above the run's length).

### Local lessons (real, but no methodology cost)

- **Agent hand-backs.** Agents ended every turn with an "ends my run" hand-back (F2–F4, noise only). In F5, hand-backs failed to arrive five times, costing a resend each; this is a harness behaviour. In F6, every hand-back arrived.
- **Operator overrides.** An operator instruction overrode a mission constraint (F5: release before mission completion); it was recorded in the flight log.
- **Transient states.** F6's armed-delete re-arm accommodation (one flight; a spec-authoring lesson).
- **The flight log's Deviations section** stayed empty in F6, and the debrief reconstructed the table (one flight).

## Action Items

- [ ] **Next mission: the editor shell and migration (#207).**
  - Factories first: entity tile, danger zone, field group.
  - Then an editor-shell factory: header, breadcrumb, unsaved caption, Save/Cancel with focus-after, section titles, error blocks.
  - Migrate whole editors. Decide patch-in-place over re-mount up front. Add a guard that flags component-owned class names re-emitted outside their module.
  - Plan the monolith splits (`studio.js`, `chat.js`) alongside.
- [ ] **Squawks 0127–0132**, the Flight 6 debrief follow-ups:
  - **0130** (the testid extractor's silent gap) and **0132** (the skip-count flap) first, because they weaken guards;
  - then **0129**, **0128**, **0131** and **0127**.
- [ ] **Older open squawks, triaged at the next maintenance pass:**
  - 0100 (knowledge-base search has no clear button);
  - 0107 (pip-audit runs only on PRs);
  - 0108 (emptyState docstring);
  - 0109 (menu tabindex listener order).
- [ ] **Routine maintenance after this mission:**
  - the WebSocket cancel-registry class;
  - a create-route `ValidationError` helper (`include_input=False`);
  - splitting `agents.md` by subsystem, with an index, and trimming CLAUDE.md to operating rules and pointers;
  - a "where a new JS helper goes" rule that treats the script-count pin as a deliberate bump;
  - lane parallelism or a further split, with a lane-time budget;
  - the `windows_test_copy.py` split (Flight 5).
- [ ] **GitHub issues carried:** #223 (time tool and time-zone setting, reusing `App.time`), #224 (per-message Copy), #225 (layouts below 1024, a shell-contract decision), #226 (the masked MCP cause; replace the classifier's string match with a structured code).
- [ ] **Crew file:** add the per-variant evidence rule and the background-cap rule (Local fixes above).
- [ ] Merge PR #227 and release v0.10.1 (the operator's direction, 2026-10-07; done right after this debrief)

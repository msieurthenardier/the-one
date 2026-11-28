# Flight Debrief: Usable at the smallest window

**Date**: 2026-11-27
**Flight**: [Usable at the smallest window](flight.md) (sortie 21; no parent mission)
**Status**: landed
**Duration**: 2026-11-27 (planning, four legs, HAT and debrief in one day)
**Legs Completed**: 4 of 4 (`narrow-shell`, `narrow-panels`, `height-clamps-and-proof`, `uat-and-alignment`), plus one HAT-promoted feature (`04a-hat-feature-narrow-tabs-and-actions`)
**Plugin version**: mission-control 1.2.4

## Outcome Assessment

### Objectives Achieved
The desktop app is usable at its 640×360 minimum window. Below 768px wide the shell shows one pane at a time by intent (a destination's list after choosing the destination, the detail after opening an item; the current rail icon returns to the list; Settings shows its menu on first entry). The agent panel and the GleepGlorp drawer fill the area right of the rail with the covered panes `inert`, take focus from their opener and return it, and close on any navigation except a GleepGlorp fill; the agent panel gained a narrow-only Close button. Windows under 480px tall compact the chat header and composer (measured 1 transcript line before, 6 after at 624×321) and the rail scrolls. Fixed widths clamp. From the HAT: the short-window composer on one centred row, and below 768px a tab strip becomes one menu button naming the current tab and an editor's secondary actions (Chat) move into a "More actions" menu. Issue #225 (the operator's own request from Mission 25) closes on merge.

### Charter Criteria (sortie)
| Criterion | Result | Note |
|---|---|---|
| Every page works at 624×321 (main pane ≥ 360px, no sideways scroll, ≥ 3 transcript lines, every control reachable and uncovered) | **met** | `test_flow_narrow_criteria.py` across every destination, agent tab, Library editor kind and Settings page in Chromium and WebKit; the WebKitGTK probe at 640×360 and 624×321 (visible pane 568 / 552px, no overflow, 8–10 transcript lines); operator HAT S2–S8. |
| List column, agent panel and GleepGlorp drawer usable at that size (mouse and keyboard, Escape, ≥ 360px, focus in and back) | **met** | One pane by intent replaces a list overlay (operator's Option A); panels fill the pane; `test_flow_narrow_panels.py` and HAT S3–S4, S8. |
| Narrower than the desktop minimum: no sideways scroll | **met** | 480×321 and 360×640 cases in the criterion tests. |
| At 1024×768 and 1280×800, every page looks and behaves as today | **met, with recorded exceptions** | Every pre-existing lane green with only deliberate pin edits; operator HAT S10–S11. Accepted differences: compaction in any window under 480px tall (DD5), the corner-button clearance (DD6, which in the event changed nothing at 1024/1280), the bare `#settings` rail href (DD3). |

### Value Delivered
The shipping desktop app no longer breaks at its own minimum size, and Windows snap-to-thirds (the reason the minimum is 640×360) now gets a working layout. The control library gained reusable narrow variants (`App.ui.drawer` `fill`, `App.ui.tabs` narrow menu, `App.ui.editorShell` `secondary` actions, `App.ui.util.narrow`) that future editors get for free.

## What Went Well
- **The design reviews earned their cost.** The two Architect cycles and the per-leg Developer reviews on the two high-risk legs caught roughly twenty defects before code, at least eight of them high-severity if shipped: bare `#chats` re-opening the current chat (the Chats list would have been unreachable); a real bare `#settings` route breaking about ten pinned contracts and GleepGlorp page awareness; the agent panel having no Close of its own under `inert`; Chats syncs outside a commit flipping the pane; the router's own Stay revert hitting the same-route arrival branch; GleepGlorp's areas-layer `width: 360px` beating the fill rule; `setCovered(false)` running after the focus return; the opener-based exemption mishandling Jump to.
- **Mockups before decisions.** The design canvas (today's layout, Option A, Option B, panels, a half-screen) let the operator choose quickly and spot that the A2 back link was redundant with the rail.
- **Risk tiering held.** Leg 3, tiered LOW, skipped per-leg design review and landed with no design defects (only test-side fixes).
- **Falsification discipline.** Every key fix was shown to fail its test with the fix removed, in both engines; this exposed two non-discriminating tests (a leg 1 Stay test, and the batch B listener-release test, which passed with the release removed).
- **Real-engine evidence.** The WebKitGTK probe gave the one direct check of the "real desktop window" constraint, with the viewport and device pixel ratio recorded.
- **The HAT found what nothing else did** (below), and the fix-vs-feature gate kept a new control out of the inline-fix path.

## What Could Be Improved

### Process
- **No one checked intermediate widths.** The spec, both Architect cycles, the leg design reviews, leg 3's criterion audit and the flight-end reviews all checked 624 and 1024+. The agent editor's header and six tabs crowd and wrap at about 750px, just above the 768px cut-over; only the operator found it (HAT S5). It cost the largest single piece of the sortie (the tabs and actions menus). Future layout flights should audit the band between the desktop minimum and the next breakpoint for wrapping and crowding, not only overflow and clearance.
- **The closing gate ran before the HAT.** Leg 3's full gate was green, but the HAT then changed three shared controls; the debrief's fresh gate on 83bf4b7a went red (one WebKit test under load; see Technical). The closing gate should run after the HAT on a UI flight, or the HAT's changes need their own full gate.
- **Crew process slips.** Two Developers (leg 2, HAT batch B) started lanes as detached subshells without recorded PIDs despite an explicit rule in their prompts; the FD traced the processes and waited them out each time. Leg 2's first Developer and batch B's Developer both stopped before finishing (no log entry, lanes unrun) and needed finishing Developers. One Developer wrote `landed` without an `in-flight` write. One stopped agent re-sent its final report five times until stopped with TaskStop.
- **Lint was not in the HAT batches' gates.** After the debrief was pushed, CI `lint` failed on PR #402: 7 E501 lines and 5 unformatted files, all in tests added or changed during the HAT (batches A and B and the debrief test fix). Legs 1–3 ran `ruff check` and `ruff format --check`; the HAT fix-batch prompts listed static guards and lanes but not ruff, and the closing gate (`make gate`) does not run ruff either. Fixed in a follow-up commit. Every Developer gate, including HAT batches, should end with `make lint` and `ruff format --check`.
- **A test pass was recorded that the gate did not reproduce.** The HAT tidy batch recorded "112 passed" for `test_ui_editor_contract.py`; the debrief gate failed one of its WebKit cases consistently (and so did an isolated re-run that day). A later Developer could not reproduce it on a quiet host and hardened the test; whether that fixes it under load is checked under Verification below.

### Technical
- **`router.js` grew from 921 to about 1,000 lines.** The 800-line rule (`tests/test_area_module_size.py`) covers only `js/areas/`, so nothing flags it. The pane-intent, sticky-list and `keepCovered` logic is a candidate to extract.
- **Timing-based focus.** `js/shell-pane.js` uses `setTimeout(0)` plus a bounded ~1s retry for focus after a navigation-close, because the opener's visibility settles after every commit subscriber runs. The behaviour it guards never reproduced. Recorded debt; a deterministic hook would be better.
- **Narrow special cases leak into consumers** (`tabs.place()`, `opener()`, `focusTab()` in the agent editor and the tools grid), and testid-assignment workarounds inside `js/ui/` show `test_ui_guards.py` and the registry pulling against each other.
- **The `layout` lane is slow and under-budgeted:** 558s at leg 3, about 600s at the debrief, against a provisional 240s; both readings on a loaded host.
- **WebKit media-query ordering.** WebKit updates `matchMedia().matches` before it dispatches `change` (in the next rendering update); a wait on `.matches` is not a wait on the event, and an unreferenced `MediaQueryList` may not deliver events. Worth recording as a testing pattern.

### Documentation
- The app guide's 600-word topic limit forced trims (leg 3 skipped a sentence; batch B trimmed batch A's). DD8-style "update the guide" requirements should budget words.
- `scripts/run-tests.sh -m browser <nodeid>` is the working form for one browser test; a bare path or `-k` without `-m browser` deselects everything. Two crew members hit this.

## Test Metrics
All from the Developer's fresh run on 83bf4b7a at the debrief (no other test processes; load 4.7 at start, 2.6 at end, never below 1.0, so timings are reference only per squawk 0259; counts are valid).
- **Unit tier:** 12,426 passed, 15 skipped, 0 failed (182.9 s pytest time). Same counts as leg 3's closing gate and the HAT batch B run. Squawk 0431's `test_mcp_pool` flake did not appear (it appeared once earlier in leg 2's run and passed in isolation).
- **Browser:** `PARALLEL_RESULT rc=1 total=3392s lanes=24 failed=contracts-controls`; the one failure was `test_ui_editor_contract.py::test_secondary_unsubscribes_when_the_header_leaves_the_document[webkit]` (timeout on its final `matchMedia` wait), reproduced alone that day. Leg 3's closing gate was `rc=0 total=3153s lanes=24` at load ~4; the 239 s (7.6%) increase comes mostly from the HAT feature's tests in `layout` and `contracts-controls`.
- **Per-lane (s, budget):** agents 762 (780), routing 759 (810), agent-tabs 728 (750), layout 599 (240, provisional), contracts-controls 575 (540), chats-transcript 537 (540), chats 511 (540), library 499 (570), providers 424 (420), shared 424 (420), gleepglorp-kinds 400 (450), settings 394 (480), mcp-connection 370 (390), mcp 360 (450), knowledge 351 (420), agent-routines 324 (360), settings-tools 314 (330), gleepglorp-chat 270 (330), contracts-widget 243 (300), contracts-overlay 222 (240), chats-widgets 182 (240), gleepglorp-fill 155 (210), contracts-chat 144 (180), contracts-widget-lifecycle 117 (150).
- **Prior debriefs** used other configurations (sortie 20: unit 12,346 passed / 40 skipped at `-n 4`; sortie 19: `rc=0 total=2179s lanes=20`), so only the leg 3 gate is a like-for-like comparison.
- **Verification of the hardened test** (FD run after the "Debrief gate fix" in the flight log; test-only change: a strong reference to the `MediaQueryList` and `change` event counters): three lanes run concurrently, as in the gate, at load 3.8–5.9: `contracts-controls` 1342 passed / 4 skipped (the WebKit case green), `layout` 119 passed, `agents` 196 passed. The original failure never reproduced on a quiet host, so the cause (WebKit not delivering `change` to an unreferenced `MediaQueryList` under load) remains a hypothesis; the hardened test still fails in both engines with the release removed.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Range-syntax media queries replaced by `(max-width: 767.98px)` | WebKitGTK 2.40+ / Safari 16.4+ floor | yes: check the engine floor of any CSS/JS feature a spec names |
| Sticky list flag and `reverting` flag added to DD1 | Chats syncs outside commits; Stay reverts land in the same-route arrival branch | no (specific), but "trace every sync and arrival path" is a good leg-review prompt |
| Explicit `keepCovered` flag instead of an opener-based exemption | Jump to's opener is the focused element inside the drawer | yes: prefer explicit intent flags to inferring intent from focus |
| Bounded focus retry instead of one deferred check | The opener's visibility settles after the commit subscribers | no; replace with a deterministic hook later |
| Three autonomous legs plus a HAT (over the two-leg soft limit) | Panels split from the shell after Architect cycle 2 | operator's knowing choice; recorded |
| HAT promoted a feature (tabs and actions menus) touching three shared controls | Crowding at ~750px found by the operator | see Methodology Observations |
| Leg 3 skipped the guide update | 600-word topic limit | no; budget guide words in the spec |

## Key Learnings
- For layout work, test the widths between breakpoints, not just the ends; dense control rows (tab strips, header button groups) fail there first.
- An intent-stamped pane (`data-pane` from a router accessor, not a widened `describeCurrent()`) and a single owner of `inert` behind a covering panel (`App.shellPane.setCovered`) were clean patterns; so is "below 768px, a strip of controls becomes one menu" (`tabs` narrow mode, `editorShell` `secondary`). Worth naming in `the_one/agents.md` "Project Conventions".
- A test that waits on `.matches` instead of the `change` event, or listens on an unreferenced `MediaQueryList`, can pass or fail by timing in WebKit.
- Falsify every new test, including cleanup and unsubscribe tests; the vacuous one here would otherwise have stood.

## Methodology Observations
(Recorded, not judged. Plugin 1.2.4.)
1. **Sortie skill, HAT phase (agentic-workflow fix-vs-feature gate):** a HAT-promoted feature added new behaviour to three shared `App.ui` controls. The gate routed it to "a scoped design review", which happened (one Developer pass, then two implementation batches), but nothing prompted a re-check of the sortie's qualification ("still one decision cluster?") at promotion time; the skill's step 5 re-check runs only before `ready`. The Architect's debrief judged the menus a second cluster (responsive dense-control patterns) and noted the defect sat at ~750px, outside the charter's stated sizes, so the feature was scope growth rather than a criterion miss. Cost: the largest piece of the sortie's code was designed in one pass inside the HAT. Expected: a prompt, at promotion, to re-qualify against the sortie gate and to offer a follow-on sortie.
2. **Agentic-workflow, Phase 2d / HAT ordering:** the skill runs the flight-end review and commit after the last autonomous leg, then the HAT; the closing gate (project crew rule) ran in leg 3, before the HAT. The HAT's code changes then had per-batch lane runs but no full gate until the debrief's fresh run, which went red. Expected: a full gate after the HAT when the HAT changes code. Cost: a red gate discovered at the debrief and a late fix cycle.
3. **Agentic-workflow, crew process (Developer spawns):** twice, a Developer started lane runs as detached subshells despite the prompt's explicit "run_in_background only" rule, and twice a Developer stopped before finishing its leg or batch. The FD recovered each time (process-table lookup, wait, finishing Developer). Expected: the crew prompt's rule to hold, or the methodology to provide a mechanical guard. Cost: two extra Developer spawns and FD monitoring.
4. **Flight-design skill, Phase 5b (Architect review):** both Architect cycles and the Citation Audit verified cited code and composed behaviour well (about twenty pre-code catches) but did not prompt a check of intermediate widths or component-level layout at the breakpoint. Expected: for layout work, a prompt to audit the band between the minimum and the breakpoint. Cost: one HAT-promoted feature.
5. **Sortie skill, step 1 qualification and charter:** the charter predicted "two legs plus an optional HAT" against #393's ~1,750 lines; the result was three legs plus a HAT and a promoted feature, ~5,100 lines (3,100 tests). The step 5 re-check caught the leg count before execution.

## Recommendations
1. **Run the full gate after the HAT on UI flights** (or give HAT code changes their own full gate) before marking a flight landed.
2. **Add an intermediate-width audit to layout flight designs and criterion tests:** sample widths between the desktop minimum and each breakpoint and assert no wrapping or crowding of control rows, not only overflow and clearance.
3. **Make the crew's background-run rule mechanical:** a project hook or wrapper that refuses `( ... ) &` / `nohup` / trailing `&` for `scripts/run-tests.sh` and `pytest` in Bash calls (like `block_shell_writes.py`), since two prompted Developers broke it.
4. **Re-budget the `layout` lane** from a quiet-host `--parallel 3` reading, or split it (criteria and panels vs tabs and header actions).
5. **Extract the pane-intent logic from `router.js`** and add `js/router.js` to a size ceiling.

## Action Items
- [ ] Squawk 0442: a size ceiling for `js/router.js`, or extract the pane-intent logic (logged at the debrief, operator's choice).
- [ ] Squawk 0443: document `run-tests.sh -m browser <nodeid>`, the WebKit `matchMedia` ordering rule and the narrow-control patterns (logged at the debrief, operator's choice).
- [ ] Re-budget or split the `layout` lane from a quiet-host reading (offered as a squawk; the operator did not log it; left as a recommendation for the next quiet-host measurement run).
- [ ] Squawk 0441 (logged during the HAT): short-window composer attach button tab order.
- [ ] Recommendations 1–3 above are methodology or tooling changes for the next flight's planning, not squawks.
- [ ] Post the follow-up comment on closed PR #393 (operator request; text approved before posting).

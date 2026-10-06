# Flight Debrief: Chats and Jump-to

**Date**: 2026-10-06
**Flight**: [Chats and Jump-to](flight.md)
**Status**: completed
**Duration**: 2026-10-05 to 2026-10-06, in one autonomous session. Planning and all ten legs
ran on 2026-10-05. The flight-end review, the commit, the close-gate runs and this debrief
followed on 2026-10-06.
**Legs Completed**: 11 of 11. Leg 9 `palette-empty-mix` was added after the operator answered the DD13 preview (see the addendum). The flight spec planned 8 legs, and leg design reviews split
leg 3 (into 3a `chats-test-seam` and 3b `start-flow-client`) and leg 4 (into 4a
`chats-sidebar-and-picker` and 4b `chats-pane`).
**Plugin version**: mission-control 1.2.0

The operator was not interviewed; the run was autonomous. The non-blocking operator preview
(DD13) was published before the close gate and had no answer by landing. The inputs were:
- the flight log;
- a Developer debrief interview with a full sequential test-metrics run;
- an Architect design review of the outcome;
- the flight-end review (a code Reviewer and an Accessibility Reviewer, one fix cycle);
- the five close-gate behavior-test run logs (96 checkpoints).

## Outcome Assessment

### Objectives Achieved

**The objective was met.** Chats now starts with the question that matters, *which agent?*,
and a palette reaches anything:
- **The Chats list.** A full-width **New chat** sits above a cross-agent history grouped
  by recency (Today, Yesterday, Last 7 days, Last 30 days, Older), with a row delete and a
  pending row. The agent dropdown and the welcome screen's agent list are gone.
- **The agent picker.** Search, Recently used, then All agents A–Z. Picking starts a
  pending chat (`#chats/~new/{agent}`) that creates nothing on the server.
- **Session on first send.** The first message creates exactly one session through the
  atomic, idempotent WebSocket `start_session` (DD1). This retired squawk 0111 by
  construction.
- **The chat pane.** A header ("{title}" with "with {agent}"), the new-chat state, and a
  restyled composer (Enter sends, IME-safe, auto-grow, "Attach images").
- **The agent drawer.** It shows the agent read-only, including what it can use. It pushes
  the pane at 1280px and wider and overlays below that, and Open agent settings reaches
  the agent with the filter cleared.
- **The agent editor's Chat action**, deferred from Flight 3 DD4, which asks first from a
  dirty editor.
- **The jump-to palette**, from Ctrl K (one shell-level listener) or the rail's Jump to
  control. It finds agents, chats, New chat…, Library items and Settings pages, and
  closes before navigating, so a dirty editor asks exactly once.
- **Control library additions.** `App.ui.searchList` (shared by the picker and the
  palette), `App.ui.drawer`, modal chooser options (`ariaLabel`, `anyOpen`), listPane chats
  rows and row actions, and the rail footer. Each has a demo, an inventory row and contract
  tests in both engines.

**Squawks:**
- **Closed:** 0110 (the image input's accessible name), 0111 (the stalled-join orphan
  session), 0117 (the `contracts` lane split from `shared`), and 0118 (the editor Cancel
  and dirty contract in `agents.md`).
- **Filed:** 0119 (a degraded same-id join stays subscribed) and 0120 (a cancel before the
  turn's first step sends no `cancelled`).

**Checkpoints:**
- **The DD13 preview** was published, not awaited: a comparison page beside the B3 board,
  in both themes at 1440 and 1024, with nine questions. It had no answer by landing.
- **The flight-end review** confirmed with non-blocking findings only; six were fixed in
  one cycle.
- **The close gate:**
  - `start-a-chat` 26/26 and `jump-to-palette` 24/24, both first runs, in Light and Dark;
  - `workbench-navigation` 28/28;
  - `shell-navigation-smoke` 9/9;
  - `chat-roundtrip` 9/9.

  96 of 96 in all. `vision-round-trip` was not run, because it needs a live Anthropic key.

### Mission Criteria Advanced

- **SC3, start a chat by choosing an agent:** met for this flight. `start-a-chat` passed
  26/26 in both themes.
- **SC5, jump to anything:** met. `jump-to-palette` passed 24/24 in both themes.
- **SC2, work is never lost (the jump-to and Chat-action half):** met.
  - A pick from a dirty editor asks once, Stay returns focus to the opener, and Continue
    discards. Both specs prove it.
  - The WebView2 side of Ctrl K is carried to Flight 5.
- **SC6, control library:** advanced.
  - searchList, drawer, modal options, listPane chats rows and actions, and the rail footer
    all landed.
  - The contracts lane grew from 556 to 646 tests.
- **SC8, matches the approved samples:** advanced, not closed.
  - The preview was published, and the close-gate visuals passed in both themes.
  - Flight 6 closes SC8 with the operator's answers.
- **SC10, operable and regression-safe:** met for this flight.
  - Keyboard paths are proven by the specs: Ctrl K, Escape, Enter, the arrows, Tab into the
    overlay drawer, and focus return.
  - Landmarks and the skip link are intact.
  - Every suite and guard is green, and the core flow passes in both themes.

## What Went Well

1. **DD1 held, and the session lifecycle is now explicit.**
   - A client-generated id with an idempotent `start_session`, a reservation (check-and-set
     before any await, `wait_for(shield(fut))`), a strict create and a typed `start_failed`
     closed the orphan-session, duplicate and lost-first-message hazards.
   - The client is a pure state machine with effects as data (`session-state.js`) that gates
     every inbound frame by state. That replaces "null means idle" logic and is unit-testable
     with plain inputs.
   - Design reviews refined DD1 rather than reversing it: "processed exactly once";
     `join_failed` for an unknown id; the reconnect rebind.
2. **The seam-first split (leg 3a, then 3b) was the flight's best process decision.**
   - Leg 3a moved 20 tests onto `tests/browser/_chats.py` helpers with no app change and
     every lane green.
   - Legs 3b, 4a and 4b then flipped the helper bodies rather than the tests, so each
     semantic change touched one helper module.
   - It is the same shape as Flight 2's `_nav` seam, and is worth naming as a project
     convention.
3. **Controls built where consumed** stayed honest: `setQuery` arrived with the drawer leg,
   and `ariaLabel`, `anyOpen` and the rail footer with the palette. No speculative API, and
   every factory carried its demo, inventory row and two-engine contracts.
4. **One shared table for Settings pages.** `App.settingsPages` is the single page table
   for the Settings nav, the router's labels and the palette. It is pinned by a static
   test, so the palette could not drift from the nav.
5. **The flight-end review earned its place.** It found:
   - a real cross-socket race on `join` against an in-flight `start_session` (R2);
   - a midnight-window test flake (R1);
   - three screen-reader gaps in new controls (A1–A3).

   All were fixed in one cycle, and the re-review saw only the fix diff, isolated through
   tree snapshots.
6. **The behavior close gate was fast and clean.** Five specs ran concurrently, each with a
   live Executor and Validator pair on its own fresh instance: 96 checkpoints in about 26
   minutes of wall time. The report-file hand-off (below) kept the Validators independent
   and the Orchestrator's context small.
7. **The leg 8 crew-file rules worked.** These are per-run scratch, no unrequested actions,
   the input-delivery probe, the variant rule and the toast rule. No Executor took an
   unrequested state-changing action, and every variant was set in its own context and
   confirmed before its first checkpoint.
8. **Latent defects surfaced by new surfaces.**
   - The drawer's "What it can use" exposed `find_platform_destination` sitting in no
     tool category; it now lists under Connectors.
   - Building the Chats pane removed the last chat HTML-string sink.

## What Could Be Improved

### Process

1. **DD1's cost was underestimated, and leg sizes were optimistic.**
   - The flight spec budgeted DD1 as two WebSocket actions and one removal. It became the
     flight's centre of gravity:
     - `session-state.js` (324 lines);
     - `chat.js` +1,280 lines;
     - `app.py` +598 lines;
     - `test_ws_start_session.py` +1,134 lines.
   - Every design review found a distinct "high": pending-chat isolation, frames in flight,
     `wait_for` cancelling the shared future, the reconnect rebind window, and the
     auto-create-on-join ambiguity.
   - Two legs were split at leg design review, not at planning. Any leg that combines a
     behaviour change with a mass test migration should be pre-split, seam first.
2. **The design-review cap was reached again.** Architect cycle 2 still raised high issues,
   and per-leg reviews had to re-verify legs 1, 2, 3, 4, 6 and 7. This is the third
   consecutive flight (see Methodology Observations).
3. **Accessibility found at the end, not the leg.** A2 (`aria-expanded` with no results)
   and A3 (no result count) were in a new control and would have been cheaper as leg-level
   acceptance criteria. Legs that introduce a listbox, combobox or armed-state control
   should carry a 4.1.2/4.1.3 checklist.
4. **Apparatus premises were the weakest.** Three were missed until implementation:
   - `Gtk.test_widget_send_key` not reaching the page under WSLg's XWayland;
   - the 1024 overlay covering the drawer's only close control;
   - the Playwright `new_context()`-over-CDP lifetime, at the close gate.

   Spike apparatus feasibility before the leg that depends on it.
5. **An Orchestrator slip at the close gate.** In a burst of concurrent reports, the
   Validator hand-off for workbench-navigation's Light step 7 was skipped. It was caught
   while writing the run log and judged late from the evidence recorded at the time (pass),
   and the run log says so. Five concurrent live pairs, about 400 messages, are at the edge
   of what one Orchestrator tracks reliably without a per-run cursor ledger.
6. **The preview produced no signal before the gate.** DD13 worked as designed, but nine
   questions and five close-gate observations are now carried unsettled. Without a
   decision sheet, Flight 6 would rediscover them.

### Technical

1. **`chat.js` is 2,133 lines**, and its state is split between the pure machine and closure
   variables (`rebinding`, `boundOn`, `pickIntent`). Either move those into the machine or
   document them as the deliberate non-pure residue. Extract the WebSocket frame handlers
   and `renderPane` before Flight 6 adds to them.
2. **`app.py` is 3,066 lines.**
   - The session-id single-writer invariant across `join`, `_restore_session` and
     `start_session` is held by convention; R2 showed how subtle it is. A `SessionRegistry`
     seam (get, restore, create, reserve) in its own module would own it.
   - The bare-`message` auto-create path is still present. The new client never sends it,
     but it is the source of the R2 race class. Deprecate it.
3. **listPane is becoming multi-mode.** The chats row style ignores `icon`, `lead` and
   `count`, and adds row actions, a block slot, a tab policy and focus-to-neighbour. Split
   variants if a fourth row style arrives. A1's armed-label sync is a MutationObserver per
   row in `chat.js`; move it into listPane actions if the pattern recurs.
4. **About 33 fixed `wait_for_timeout`/`sleep` calls** were added to browser tests (300 to
   1,500ms "for the list refresh to land"). They pad lane time and are a latent flake
   source; convert them to condition polls.
5. **Accepted carry-overs:**
   - A4: the 1024 overlay covers Send and sits late in the tab order (preview question 3).
   - A5: the unlabelled `#app-sidebar`, from Flight 2.
   - A cosmetic stale armed-delete label during an auto-title.
   - Squawk 0120 is pre-existing, but "Stop while starting" makes it easier to reach.
   - A lost reply on an open socket is deliberately not recovered (squawk 0111's
     corrective action). That is sound on loopback, but revisit it if a remote transport
     ever appears.

### Documentation

1. **The test-suite runtime wording is ambiguous.** CLAUDE.md's "about 38 minutes" is the
   six browser lanes summed; this run measured 39m12s. A full serial run including unit is
   about 51 minutes. Say both.
2. **The start-protocol reservation contract** has one sentence in `agents.md`. Give it its
   own contract subsection, alongside the R2 guard's invariant.
3. **Name the patterns that emerged** in `agents.md`'s Project Conventions:
   - a pure state machine with effects as data;
   - seam-first test migration;
   - adopt-a-static-node factories (`drawer`'s `el`);
   - one page table for nav, router and palette.
4. **`agents.md` grew 212 lines this flight** and keeps growing. Routine maintenance should
   consider splitting it.

## Test Metrics

These come from the Developer's debrief run on 2026-10-06, branch tip `f88bdb3`. The run
was sequential, one lane at a time, under `THE_ONE_TEST_NETNS=1` through
`scripts/run-tests.sh`.

| Suite | F3 debrief | F4 leg 1 baseline | F4 debrief | Delta vs F3 |
|---|---|---|---|---|
| Unit (`make test-unit`) | 5,045 passed, 10 skipped, 654s | 5,067, 659s | 5,178 passed, 10 skipped, 687s (715s wall) | +133, +33s |
| chats | 42, 96s | 42, 100s | 163 passed, about 255s | +121, +159s |
| agents | 130, 2 skipped, 317s | 132 | 134 passed, 2 skipped, 339s | +4, +22s |
| library | 145, 1 skipped, 477s | 146 | 145 passed, 1 skipped, 497s | 0, +20s |
| settings | 178, 335s | 178 | 178 passed, 348s | 0, +13s |
| contracts (WebKit required) | (in shared) | 556, 145s | 646 passed, 3 skipped, 174s | new lane |
| shared | 867, 3 skipped, 758s | 438, 654s | 461 passed, 729s | split (squawk 0117) |
| **Browser total** | 1,362 passed, 6 skipped, 1,982s (33m) | | **1,727 passed, 6 skipped, 2,352s (39m)** | +365 (+27%), +370s (+19%) |

- **Failures and flakes: none.** Every suite exited 0 on the first run. The counts match the
  flight log's final gates.
- **Skips are all known:**
  - unit, 10 (unchanged);
  - agents, 2 static skips;
  - library, 1;
  - contracts, 3 WebKit forced-colours skips. WebKit launched, because
    `THE_ONE_REQUIRE_WEBKIT=1` was set.
- **Chats** is the lane this flight rebuilt. It went from 42 to 163 tests:
  - session-state 55;
  - start-flow 11;
  - list 8;
  - picker 7;
  - pane 8;
  - composer 9;
  - drawer 18;
  - plus the migrated tests.

  At about 1.6s per test it is in line with the other app-spawning lanes.
- **The `shared` split worked, but did not shorten the long pole.**
  - `contracts` was only 2.5 to 3 minutes of the old lane. `shared` is still 11m43s,
    dominated by the router and navigation files' quiet-window waits.
  - `test_flow_jump_to.py` added 20 tests (about 40s).
  - A second split (routers and hash routing against the shell, rail and keyboard) is the
    next lever if wall time matters.
- **Contracts** grew from 556 to 646 tests (+29s) at a stable 0.27s per test.
- **Agents, library and settings** are within 2% to 7% of Flight 3, which is noise.
- **Totals.** A sequential run is now about 51 minutes (39 browser plus 12 unit). It was
  about 44 at Flight 3 and about 37 at Flight 2.
- **Flake history.**
  - The midnight-window flake (R1) was fixed in the flight-end review. The debrief run
    started at 01:30 local, so it did not exercise the window, and a frozen-clock test
    would prove the fix.
  - Leg 8's one load-related unit failure (unit beside a browser lane) did not recur in a
    strictly serial run. That is consistent with Flights 1 to 3: serial runs have zero
    flakes.

## Deviations and Lessons Learned

Every leg's deviations are recorded in the flight log ("Deviations"). The notable ones:

- **Leg 2: "processed exactly once" replaced "not processed again".**
  - A `start_session` re-send to an existing id with an empty history and a free lock now
    delivers the message.
  - Delivery also requires the session lock to be free and reports `is_processing: true`.
  - **Lesson:** idempotency rules for retried creates need a "first delivery" clause, not
    only "no duplicate".
- **Leg 3b: `join` of an unknown id answers `join_failed` and creates nothing.** This
  changed leg 2's behaviour. **Lesson:** a protocol decision found in a later leg's review
  can reach back into a landed leg; the flight log should mark it as such, and it did.
- **Leg 6: the drawer follows the header states.**
  - It shows in `starting` and `joining` too, and is open by default at 1280px and wider.
  - So every Chats browser test at Playwright's default 1280 runs with a 588px pane.
  - **Lesson:** a default-open layout region changes the test viewport's effective width,
    which is worth stating in the flight spec.
- **Leg 6: `find_platform_destination` joined Connectors.** It is a visible change, raised
  as preview question 9.
- **Leg 7: the GTK-level key method.** WebKitGTK verification uses `Gdk.EventKey` through
  `WebView.event`, because `Gtk.test_widget_send_key` never reached the page under WSLg.
  The result is "partially verified (GTK-level key)".
- **Close gate: CDP context lifetime.**
  - A Playwright `new_context()` over `connect_over_cdp` is destroyed when the driving
    script disconnects. Three Executors hit it.
  - The fix was a new Chromium process with a fresh profile per variant, or a long-lived
    driver process.
  - An advisory and a PID-only kill rule went out mid-run. One step was re-run as an
    apparatus re-run (`chat-roundtrip` step 3), and one browser was recovered on its own
    profile (`start-a-chat` before Light step 6).

## Key Learnings

1. **Seam first, then flip.** When a leg would combine a behaviour change with a mass
   test migration, first move the tests onto helpers with no app change, then change the
   helper bodies. It contained the blast radius of three semantic legs.
2. **Make lifecycles explicit before adding surfaces.** The pure session machine with
   effects as data made every review finding testable with plain inputs. Use this shape for
   any client lifecycle with stale-frame hazards.
3. **A non-blocking preview needs a decision sheet to land somewhere.** Without an
   operator answer, the questions must be carried as one list into the next human
   touchpoint, not left in a flight log.
4. **Live behavior runs at scale need Orchestrator bookkeeping.** A per-run ledger (one
   line per checkpoint), a report-file hand-off and the advisories turned out to be what
   made five concurrent runs workable. The one slip happened exactly where the ledger was
   updated out of order.
5. **Contrast and keyboard claims in acceptance criteria should be checked against the
   audit table before they are written.** Leg 1's `--fg-muted` on the active wash failed
   body AA.

## Methodology Observations

These are recorded, not judged. Plugin `mission-control` 1.2.0.

1. **Flight skill, Phase 5b (design-review cap). This recurs from Flight 2, observation 6,
   and Flight 3, observation 2.**
   - **What happened.** Architect cycle 2 raised a high issue again, so the final flight
     text went unreviewed at the cap. Per-leg design reviews re-verified six legs.
   - **Cost.** No rework that could be traced to the cap. It is the third consecutive
     flight to reach the cap with a high outstanding.
   - **Expected.** Either a third cycle for flights that touch a protocol or lifecycle, or
     explicit guidance that per-leg reviews are the designated backstop.
2. **agentic-workflow, Phase 2a (leg sizing).**
   - **What happened.** Two planned legs (3 and 4) were split at their own leg design
     review, raising the count from 8 to 10. Both splits were "behaviour change plus mass
     test migration", or two consumers sharing one file.
   - **Expected.** A sizing heuristic in the flight skill's leg identification:
     pre-split a leg that combines a semantic change with a mass test migration.
   - **Cost.** Two re-planned legs and one extra design-review cycle (leg 3b's second).
3. **behavior-test skill, live mode (agent continuity). This recurs from Flight 2,
   observation 1, and Flight 3, observation 3.**
   - **What happened.** Leg 8 added "you are resumed by SendMessage after each step" to the
     crew file. Agents still ended turns with "this hand-back ends my run; re-spawn me",
     and one Executor did so in every report.
   - **Cost.** Noise only. Every resume through SendMessage worked.
   - **Expected.** The harness's per-turn hand-back framing and the crew rule agree, or the
     skill states the framing explicitly.
4. **behavior-test skill, apparatus (CDP context lifetime). New.**
   - **What happened.** The crew file names "CDP-driven headless Chromium with real input"
     as the default but gives no recipe. Executors created per-variant contexts with
     Playwright `new_context()` over `connect_over_cdp`. Those contexts die when the
     script disconnects, so state was lost between steps.
   - **Cost.**
     - one apparatus step re-run (`chat-roundtrip` step 3);
     - one step 1 redo (`shell-navigation-smoke`);
     - one mid-run advisory to all Executors;
     - one browser death and recovery, cause not established.
   - **Expected.** An apparatus recipe:
     - one long-lived driver per run, or a fresh Chromium process and profile per variant;
     - record PIDs at launch;
     - kill only those PIDs.
5. **behavior-test skill, Phase 4 (concurrent runs). New.**
   - **What happened.** Five specs ran concurrently, each with a live pair, for about 400
     messages through one Orchestrator. The Orchestrator improvised:
     - a per-run ledger file;
     - a report-file hand-off (the Executor writes `step-N-report.json` without its notes,
       and the Validator reads the file), which kept the Validator's input to the
       structured subset and the Orchestrator's context small.

     Even so, one Validator hand-off was skipped in a burst and judged late from recorded
     evidence.
   - **Expected.** Skill guidance for concurrent runs: a cursor ledger per run, a cap on
     concurrency, and the report-file hand-off as a sanctioned pattern.
   - **Cost.** One late verdict, disclosed in the run log.
6. **agentic-workflow, Phase 2d (re-review after deferred commit). New.**
   - **What happened.** Every leg stays uncommitted until the flight-end review. To show
     the re-reviewer only the fix diff, the Flight Director snapshotted the working tree
     into tree objects through a scratch git index (`git write-tree`) before and after the
     fixes.
   - **Expected.** Guidance for isolating a fix-cycle diff when nothing is committed yet,
     for example a "fix-cycle" commit squashed later, or a sanctioned snapshot.
   - **Cost.** A few minutes of Flight Director improvisation.
7. **agentic-workflow, PR lifecycle (stacked flights). New.**
   - **What happened.** Flight 3's PR #219 was still open when Flight 4 landed. Flight 4's
     PR #220 targets `flight/03-list-and-detail`, and must be rebased onto `main` after
     #219's squash merge. The skill assumes the previous flight's PR has merged.
   - **Cost.** A pending rebase.
   - **Expected.** A note on stacked-flight PRs (base branch, rebase after squash).
8. **Flight skill, DD13-style non-blocking preview. New.**
   - **What happened.** The preview published, and the flight landed without operator
     signal, as designed.
   - **Expected.** The skill has no state for "landed with the preview pending", and no
     guidance on where unanswered preview questions go. The Flight Director carried them in
     the flight log and the mission.
   - **Cost.** None yet. There is a risk the questions are lost before Flight 6.

## Recommendations

1. **Before Flight 6, turn the open items into one decision sheet for the operator.**
   - **The nine DD13 preview questions:**
     - row delete;
     - the palette's empty query;
     - the drawer below 1280, and the overlay covering Send;
     - the 588px pane;
     - "Attach images";
     - the older recency groups;
     - the Dark scrim at 0.5;
     - the overlay toggle;
     - `find_platform_destination` under Connectors.
   - **The close-gate observations:**
     - the faint Dark pending-row wash (alpha 0.10);
     - no visible focus ring on `rail-jump-to` after a pointer close;
     - focus on `<main>` after Continue into a pending chat;
     - message timestamps re-rendering 1 to 4 seconds off after a reload;
     - UTC bubble times against local list times.
   - **The accepted A4 and A5.**
   - A4 (the 1024 overlay) is the likeliest redesign candidate. **Important.**
2. **Write the CDP apparatus recipe and the concurrent-run rules into
   `.flightops/agent-crews/behavior-tests-execution.md`:**
   - one long-lived driver, or a fresh Chromium per variant;
   - PID-only kills;
   - the report-file hand-off;
   - a per-run ledger.

   Logged as squawk 0121. **Important.**
3. **Pre-split legs and add a11y criteria at leg level.**
   - In flight planning, pre-split any leg that combines a behaviour change with a mass
     test migration (seam first).
   - Give legs that introduce a listbox, combobox or armed-state control explicit 4.1.2
     and 4.1.3 acceptance criteria.
   - Name the patterns in `agents.md` Project Conventions. **Important.**
4. **Extract before the next growth** (next mission or routine maintenance):
   - a `SessionRegistry` seam and a start-protocol module out of `app.py`;
   - the WebSocket handlers and `renderPane` out of `chat.js`;
   - deprecate the bare-`message` auto-create;
   - a dedicated `agents.md` subsection for the reservation contract. **Minor** now,
     **important** before more chat features.
5. **Test-suite time.**
   - Convert the about 33 fixed waits to condition polls.
   - Consider a second `shared` split.
   - Correct the runtime wording in CLAUDE.md: about 39 minutes of browser lanes, about
     51 with unit. **Minor.**
6. **Fix the spec wording the Validators raised** (squawk 0122). **Minor.**

## Action Items

- [x] Squawk 0121: add the CDP apparatus recipe and concurrent-run rules to the
  behavior-test crew file (recommendation 2)
- [x] Squawk 0122: behavior-spec wording fixes from the Flight 4 close gate
  (recommendation 6)
- [ ] Operator: answer the DD13 preview questions when convenient. Merge PR #219, then
  PR #220, which is rebased onto `main` after #219's squash merge.
- [ ] Flight 5 planning: carry Ctrl K in WebView2, route any desktop shortcut through
  `App.shortcuts`, and respect the static drawer slot and `--drawer-w` in the window
  chrome.
- [ ] Flight 6 planning: build the decision sheet (recommendation 1), and test the
  deleted-agent heal for a restored `#chats/~new/{agent}`.
- [ ] Routine maintenance:
  - the extractions (recommendation 4);
  - the fixed waits and the runtime wording (recommendation 5);
  - the `agents.md` pattern names (recommendation 3).
- [ ] Open squawks carried: 0112–0116, 0119 and 0120.

## Addendum: operator preview answers and leg 9 (2026-10-06)

The operator answered the DD13 preview after this debrief was written.
- **Accepted as built:**
  - row delete;
  - the drawer closed below 1280 and the 1024 overlay covering Send (A4);
  - the 588px pane at 1280;
  - the older recency groups;
  - the Dark scrim at 0.5;
  - closing the overlay through the header toggle;
  - `find_platform_destination` under Connectors.
- **"Attach images"** was accepted once it was confirmed that attachments really are
  image-only (`accept="image/*"`, and the server builds only `ImageContent`). General file
  attachment is a possible later feature.
- **Question 2, the palette's empty query.** The operator did not follow the question as
  first written. Re-asked in plain terms, the operator chose **option C**: a few recent
  chats, then New chat…, then recently used agents.

**Leg 9 `palette-empty-mix`** implemented option C:
- up to 3 recent chats, New chat…, then up to 4 recently used agents (the picker's
  `recentAgents` rule);
- filled to 8 from the board order without duplicates;
- a typed query unchanged.

It took one design review (approve with changes, no high issues) and one review
(confirmed). The commit is `0d0e114`, and the targeted `jump-to-palette` re-run
(`2026-10-06-14-00-21`) passed 2/2. Squawk 0121's apparatus recipe was used for the first
time, with no incidents.

**Lesson.** One of nine preview questions was not understood as written. It asked about an
implementation detail ("the empty-query content, board order") instead of what the
operator sees. Write preview questions in what-you-see terms, with the options spelled
out. This adds to methodology observation 8.

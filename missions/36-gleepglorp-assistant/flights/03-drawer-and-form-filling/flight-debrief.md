# Flight Debrief: The GleepGlorp drawer and form filling

**Date**: 2026-11-21
**Flight**: [The GleepGlorp drawer and form filling](flight.md)
**Status**: landed
**Duration**: 2026-11-19 - 2026-11-21
**Legs Completed**: 10 of 10
**Plugin version**: mission-control 1.2.4

## Outcome Assessment

### Objectives Achieved
- **The drawer.**
  - A violet corner button and a 360px drawer appear on Agents, Library and
    Settings. They are hidden on Chats and while GleepGlorp is off.
  - The drawer holds a real second chat instance (`App.chat.create`, two
    profiles) on its own window socket. Its conversation carries across
    pages, reloads and tabs, and it has New chat and Open in Chats.
- **Page awareness.** Every drawer message carries a route-fed descriptor.
  The server resolves it into one stored `[Page: …]` line, which the model
  reads, through the one approved `Agent.step(page=)` touch of the frozen
  core.
- **Form filling on the agent editor.**
  - `fill_form` records a fill (schema v55) and sends it to the screen.
  - The drawer that sent the turn claims it with a lease and writes it
    into the agent editor as unsaved edits only:
    - twelve allowlisted keys;
    - an operator's unsaved field is kept (`partly_filled`);
    - a note on each filled control.
  - The operator's Save is the only store. Receipts show in both chat
    instances, and Fill now retries.
- **Prompt and evals.**
  - Shipped prompt `p4c`: p3 plus the page, fill and no-copy rules, at
    exactly the 550-token cap.
  - The n=20 baseline `m36f3-gleepglorp.json` is recorded: Haiku 426/460
    with zero safety failures, qwen3-4b 178/460 (measured only).
  - Five new scenarios and five fill checks.
- **Desktop engines.** The drawer, Esc and a fill pass in WebKitGTK (probe),
  WebView2 (the Windows test copy) and WKWebView (macOS lifecycle step
  L9b), through a scripted mock.
- **HAT.** All 12 steps pass after three fixes (below).
- **Closing gate, as a correctness check.** Green on `1427d98c`.

### Mission Criteria Advanced
- **"Help is one click away on every page"**: met for Agents, Library and
  Settings. On Chats, GleepGlorp is reached through the chat list, per the
  2026-11-19 amendment.
- **"GleepGlorp fills the form; the operator saves it"**: met for the agent
  editor. The other editors are Flight 4.
- **"Nothing changes without the operator's click"**: fills store nothing,
  and the allowlist and no-write tests are extended.
- **"Secrets never pass through GleepGlorp"**: a fill passes the same guard
  as a proposal. The pasted-key scenario and HAT step 11 pass.
- **"GleepGlorp sticks to the app"**: a fill after outside content is
  flagged "Check this". There is an accepted residual of about 1 in 12
  fills carrying a planted link (see below).
- **"Quality is measured on every default eval model"**: the n=20 baseline
  is recorded on the final 23-scenario set.

## What Went Well
- **The factory refactor kept Chats unchanged** (DD2). Leg 1's gate held:
  every chats lane passed with assertions unedited. The drawer became "just
  another instance".
- **Two sockets with idempotent window frames** (DD3) closed Flight 2's
  socket gap. A window opened straight into Agents now gets
  `config_changed`, with no server protocol change.
- **Storing the page line, never re-resolving it,** kept provider bytes and
  prompt caching stable. The Architect's cycle-2 rejection of
  prefix-and-strip avoided a leak into echoes, titles and mid-turn joins.
- **Design review caught real hazards before code.** Examples:
  - the inverted model-write order;
  - the second fill reading the first fill's values as operator edits;
  - a `mode` column hitting the status CHECK;
  - the macOS step placed after L10, which deletes the app;
  - a case-sensitive probe key.
- **The eval method worked as designed.**
  - The fairness pass and the screen surfaced a real payload-in-fill
    failure and two false positives in checks.
  - The operator saw every quota round before it ran, and the stop-on-safety
    rule caught the n=20's three check false positives before a bad
    baseline was recorded.
- **The scripted-mock desktop driver** (`responses`, the seed script)
  checked three real engines with no model or key. The same driver gives a
  real-loop server test for fills.
- **Falsification on every safety-relevant test** kept the new tests honest.
  It caught several tests that would have passed vacuously.

## What Could Be Improved

### Process
- **Legs blocked on pins the leg did not list.** Four `[BLOCKED]` stops had
  this cause:
  - Leg 3 on Leg 2's focus and empty-body assertions;
  - Leg 4 on the evals freeze digests (a classifier refusal; the operator
    ruled that the FD may apply them);
  - Leg 7 on the scenario registries `REQUIRED` and `PASSING`;
  - Leg 8's ship, on three pins of the shipped candidate.

  Each needed an FD ruling. A leg that adds or changes an enumerated set
  (scenarios, topics, testids, tool lists, shipped candidates) should list
  the registries and pins that enumerate it, found by grep at design time.
- **Design review needed two cycles on Legs 3, 4, 6, 8 and 9.** Cycle 1
  often found four to six high issues. The first drafts of large legs were
  under-specified on mechanics: write order, engine specifics, budget
  arithmetic. The two-cycle cap held, but Leg 9's second cycle still folded
  in medium items with no third look.
- **The closing gate did not get a quiet host.** Outside load pushed the
  1-minute load to 5-7 mid-run. The quiet re-measure is now owed three
  flights running (squawk 0389).

### Technical
- **Fill and proposal plumbing are parallel copies.** Each has its own store,
  `events.py`, API module and card or receipt module. Only validation is
  shared (`shape.normalize`, `guard.check`, `compute_taint`). Flight 4
  should extract:
  - a per-chat status-row repository base;
  - frame emission;
  - one card and receipt folding rule.
- **Everything is agent-only.** The twelve-key allowlist in
  `agent-editor-fill.js`, the follow handlers and the receipt labels are
  hard-coded to one kind. Flight 4 needs a per-kind applier interface and
  registry before the first new kind.
- **Sizes:**
  - `proposals/shape.py` is 619 lines and `apply.py` 528;
  - `instance.js` is 506, at the DD12 size target;
  - the chat modules' `ctx` coupling keeps growing.
- **The applier is tied to editor mount timing** (settle waits, the
  `__ggFillSettleTimeoutMs` dev seam). It is correct, but each new editor
  needs its own settle contract.
- **The prompt has no headroom:** `p4c` is exactly 550 tokens. Flight 4
  must move per-kind guidance into tool descriptions or the guide, not the
  prompt.
- **`page-what-is-link` is 7/20 for a structural reason:** the page line
  carries no route, so the model guesses. This is a design gap in DD5, not
  a prompt flaw.

### Documentation
- `the_one/agents.md` describes the fill leg by leg. It lacks one worked
  sequence of the fill lifecycle: record, frame, `ownsTurn`, claim and
  lease, settle, unsaved-edit write, outcome, and why it differs from a
  proposal's single approve.
- The dev-mode seams (`__ggFillSettleTimeoutMs`,
  `scripts/gleepglorp_drawer_seed.py`, the mock `responses`) are not named
  in `CLAUDE.md`'s "UI test apparatus".

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 6 split into Parts A (receipts) and B (applier) | Two review cycles showed the receipt and the applier were separate risks | yes, for legs with a server seam plus a browser write seam |
| Evals freeze digests applied by the FD | Operator ruling 2026-11-20: the digests are data integrity, not a safety gate | yes, project rule, recorded in the log |
| Shipped `p4c`, not `p4` | The screen found the payload carried into a fill and a broken link; `p4c` added the no-copy rule and two links | n/a |
| `fill-after-fetch-no-secret` reclassified safety → report | Operator accepted the residual (about 1 in 12), mitigated by "Check this" and Save | **no**: must not become precedent for downgrading safety cells |
| Two n=20 confirmations | The first was stopped by the rule when three check false positives showed as safety failures; checks fixed, re-run | yes (stop-on-safety before recording) |
| macOS drawer check as lifecycle step L9b instead of a new mode | A new workflow input needs a PR on main first; operator chose to extend lifecycle | yes, for one-off checks |
| Show the form removed at the HAT | It caused data loss through a same-route guarded go; once fixed, the operator found no use case | n/a |
| Closing gate as a correctness check, re-budget moved to Flight 4 | Loaded host; Flight 4 changes lanes again anyway | no: pay it in Flight 4 |

## Key Learnings
- **Any action that calls `App.router.go` needs a same-route-with-dirty-
  state test.** Show the form's data loss came only from that sequence.
- **Keyboard handlers scoped to a container need a "click inside, then press
  the key" test.** Focus moves to `<body>` on a click on non-focusable
  content.
- **Safety checks are code under test.** Of the six safety failures across
  the screen and the two confirmations, four were check false positives
  ("where it's configured", "paste or send", "That page is where you enter
  your key"). Probing each pattern with adversarial must-pass and must-fail
  sentences before quota was the cheapest fix.
- **Prompt rules do not reliably stop injected content from reaching
  structured output.** The no-copy rule cut the planted-link rate from
  about 1 in 5 to about 1 in 12 but did not stop it. A deterministic guard
  in the tool would, and it matters more for secret-bearing kinds.
- **A scripted mock with a reply sequence is the right desktop driver.** It
  also gives a real-loop server test for free.
- **Operator view (HAT timing).** The HAT is the right place to find "this
  button has no use case". The flight was "big but right sized for the cut
  of work".

## Methodology Observations
All observations are on mission-control 1.2.4.

1. **`/mission-control:agentic-workflow`, Phase 2a risk checks: registries
   and enumerating pins are not covered.**
   - **What the skill does:** the "Interface changes" check says to grep for
     consumers of a changed symbol.
   - **What was missing:** it says nothing about tests and registries that
     enumerate a set the leg grows (scenario lists, topic lists, retired
     testids, shipped-candidate pins). Four legs hit `[BLOCKED]` on exactly
     such pins: Legs 3, 4, 7 and 8 (gate 4). Each cost an FD ruling and a
     resumed Developer, about 15-30 minutes each.
   - **What was expected:** the design phase should ask "which tests or
     registries enumerate the thing this leg adds, removes or ships?" and
     put them in the allowed-edits list.
2. **`/mission-control:agentic-workflow`, Phase 2a design review: the
   two-cycle cap was reached on Legs 6 and 9 with medium findings still
   coming.**
   - **What happened:** the cap forces "fold in and proceed". On Leg 9 that
     was right (the folded items were mechanical). On Leg 6 the second cycle
     found new high-severity items, which the FD fixed without a third
     look.
   - **Cost:** none visible this time.
   - **Observation:** the skill gives no guidance for a second cycle that
     still finds highs, other than escalating to a human, which the FD did
     not do because the fixes were mechanical.
3. **`/mission-control:flight-debrief` plus the project crew rule "Test
   metrics: reuse the flight's gate".**
   - **What happened:** the rule requires a fresh quiet-host run when the
     gate ran loaded. The operator had explicitly moved the quiet re-measure
     to the next flight, so the debrief reused the loaded gate for counts and
     recorded its timings as reference only.
   - **The gap:** neither the skill nor the crew rule anticipates an
     operator deferral of the timing reading.
4. **`/mission-control:agentic-workflow`, Phase 2b HAT legs: the
   fix-vs-feature gate worked as written.**
   - **What happened:**
     - three HAT findings were classified out loud: two fixes and one
       operator-directed removal;
     - the multi-surface trigger (the shared `App.ui.drawer` serves two
       drawers) was applied, with the FD reviewing inline;
     - the batched review at HAT end (code plus accessibility) was cheap.
   - **Why record it:** a positive data point.
5. **Crew handbacks while a background task is running** (harness
   behaviour, not the plugin).
   - **What happened:** several Developers reported, then "waited on their
     own background work". A follow-up `SendMessage` reply was sometimes not
     delivered, so the FD re-checked the working tree directly once (Leg 8
     key-check option b).
   - **Why record it:** this belongs to the crew-spawn guidance on "every
     background task you start must have ended by the time you report".

## Recommendations
1. **Start Flight 4 with the plumbing, the registry and the owed gate.**
   - **Plumbing:** extract the shared fill and proposal pieces (status-row
     repository base, frame emission, one card and receipt folding rule).
   - **Registry:** define a per-kind applier interface and registry
     (allowlist, writer, settle contract, labels) before the first new
     kind, alongside Flight 2's owed `ApplyError` and `shape.py` split.
   - **Gate:** run the quiet-host gate and re-budget first. Re-slice
     `shared` (683 s against a 420 s budget) into a drawer and fill lane.
2. **Put the route (or a stable page id) in the page line.** That fixes
   `page-what-is-link` without prompt tokens. Decide in the Flight 4 plan
   whether a page request about a different item fills (navigating) or
   proposes.
3. **Add a deterministic guard in `fill_form` and `propose_change` before
   secret-bearing kinds** (providers, MCP headers): refuse a link, address
   or credential-shaped value that the operator did not type, on a turn
   with outside content. The prompt-only mitigation leaves about 1 in 12,
   which is unacceptable when a field is a URL or a header.
4. **Make "grep the registries and pins this leg enumerates" a standing
   item** in the project's leg-design checklist (`.flightops`), and add
   two test patterns to every UI leg:
   - same-route-with-dirty-state for any navigation action;
   - click-inside-then-key for any container keyboard handler.
5. **Keep the prompt at the cap; grow through tools.** Per-kind guidance
   goes into tool descriptions and the guide. Each candidate is measured
   against 550 before scenarios are written.

## Action Items
- [ ] Flight 4 planning: recommendations 1-3 and 5, plus squawks 0389,
  0391, 0392 and 0393.
- [ ] `the_one/agents.md`: one worked sequence of the fill lifecycle (squawk
  0394).
- [ ] Name the drawer dev seams and the seed script in `the_one/agents.md`
  "UI test apparatus", not in `CLAUDE.md` (squawk 0395).
- [ ] The drawer's "Looking at Agents › New" against the editor title "New
  Agent" after a create fill: align the page label (squawk 0396).
- [ ] `CLAUDE.md` is too large: pare it back to the operational manual with
  pointers to `the_one/agents.md` (squawk 0397, raised by the operator at
  the debrief).
- [ ] `.flightops` leg-design checklist: add the registries-and-pins grep
  item (recommendation 4).

## Test Metrics
Source: the closing gate, `make gate` on `1427d98c`. `git diff
1427d98c..6a4f1375` touches no code. The run started at load 0.86 and ran at
about 5-7, so its lane times are not a budget reading (operator decision:
the quiet re-measure is in Flight 4).
- **Unit tier:** 11331 passed, 15 skipped (the expected netns set), 381.3 s.
  - Flight 2: 11031 passed, 343.5 s.
  - Flight 1: 10695 passed, 308.75 s.
  - That is +300 tests and +11% time over Flight 2. The 350 s target is
    exceeded on a loaded host; not judged.
- **Browser:** `PARALLEL_RESULT rc=0 total=2746s lanes=20 failed=-`. The
  whole gate took 3144 s, against a 43-minute target.
  - Flight 2: 2459 s (loaded). Flight 1: 2270 s.
  - In-flight batch B: 2348 s.
- **Lanes over budget,** reference only:

  | lane | wall (s) | budget (s) |
  |---|---|---|
  | `shared` | 683 | 420 |
  | `agent-tabs` | 707 | 600 |
  | `agents` | 705 | 630 |
  | `mcp` | 362 | 330 |
  | `chats-transcript` | 583 | 540 |
  | `chats` | 439 | 420 |
  | `routing` | 741 | 720 |

  `shared` was already 610 s at batch B, so its overrun is real growth (the
  drawer and fill files).
- **Flakes:** one `contracts-widget-lifecycle` layout test under load at
  batch B, 113/113 on a re-run.

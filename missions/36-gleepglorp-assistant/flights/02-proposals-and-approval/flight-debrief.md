# Flight Debrief: Proposals and approval

**Date**: 2026-11-19
**Flight**: [Proposals and approval](flight.md)
**Status**: completed
**Duration**: 2026-11-19 (planned, executed and landed in one day; landing commit `5f749e85`; PR #381)
**Legs Completed**: 11 of 11 (planned as 10. Leg 7 was split into 7 and 8 at its design review.)
**Plugin version**: 1.2.4

## Outcome Assessment

### Objectives Achieved
GleepGlorp can now change the app by proposal.
- **Proposals.** GleepGlorp proposes creating or changing an agent, one of its rules, or one of its routines, through one tool, `propose_change`.
  - The proposal is validated against one declared change shape (`the_one/gleepglorp/proposals/shape.py`) and stored in schema v54 `gleepglorp_proposals`.
  - A chat has at most one open proposal at a time.
- **The card.** The chat shows the proposal as the card the operator chose (option A, the field table), in every state the board drew. It sits after the turn that made it and survives a reload through `proposals_snapshot`.
- **Approve.**
  - It applies exactly the proposed fields through the same services Save uses. `the_one/agent/service.py` and `rules_service.py` were extracted from `api.py`, and the routines service already existed.
  - The apply happens once, under the write lock, with the proposal marked in the same transaction.
  - A stale proposal is refused unless the operator chooses Approve anyway. A failed apply shows its errors on the card.
  - Approve then starts GleepGlorp's next turn (the quiet line, option B), so a multi-step request continues one approved step at a time. Dismiss changes nothing.
- **Safety.**
  - Every string in a proposal is checked against every stored secret and against key shapes.
  - `read_app_config` marks results that hold only operator-typed fields, through a per-path provenance walk. So "Check this" flags only proposals made after real outside content. A flagged routine stays flagged.
  - No delete action exists.
- **Editors follow.** An open agent editor takes approved values into clean controls, keeps unsaved edits with the existing caption, and notes each changed control or tile (option A). This covers the General tab, Tools, MCP, Knowledge, Rules and Routines. A window that approves in Chats and then opens Agents sees the same notes.
- **Evals and prompt.**
  - The eval method is written into `evals/README.md`.
  - The GleepGlorp set now has approve and dismiss turns, five proposal checks and eight new scenarios (18 in all).
  - The proposals-aware prompt `p3` ships. It is 428 of 450 tokens.
  - The app guide has a `proposals` topic.
- **HAT.** The operator walked 9 of 9 steps with a real Claude model, and no fixes were needed.

### Mission Criteria Advanced
- **GleepGlorp proposes; the operator approves.** Met for agents, rules and routines (the kinds scoped to this flight, by operator decision). Each sub-criterion was walked in the HAT:
  - one proposal per step, with Approve continuing;
  - field-level apply through the forms' validation;
  - the error on the card;
  - stale refusal;
  - Dismiss changes nothing;
  - the open editor follows without overwriting.

  The other kinds come in Flight 3.
- **Nothing changes without the operator's click.** Met. `propose_change` writes only `gleepglorp_proposals`, which a no-write test proves. The approve and dismiss routes sit behind the credential gate. No setting relaxes this.
- **Secrets never pass through GleepGlorp.** Met for proposals. The server-side guard covers all nine encrypted columns and key shapes. In the HAT, GleepGlorp refused a pasted key and linked the Model providers page.
- **GleepGlorp sticks to the app.** Met for proposals. "Check this" was proven in the HAT. GleepGlorp declined the injected instruction outright, and a proposal made after the page was read carried the chip. It also declined a delete.
- **Quality is measured on every default eval model.** Partly met.
  - Met:
    - the set and checks are extended;
    - three fairness passes plus a control-and-screen on Haiku;
    - `p3` chosen on an n=5 recheck with zero safety failures.
  - Not met: the n=20 confirmation and the `m36f2-gleepglorp.json` baseline. These are folded into Flight 3 by operator decision. qwen3-4b was not run this flight (measured only).

## What Went Well
- **Design reviews paid for themselves again.** Every high-risk leg's review found at least one high issue before code was written:
  - **Leg 1:** the transaction re-entry made a compare-and-save impossible, so the services take a `precheck`/`on_commit` hook on `AgentStore.save`.
  - **Leg 3:** the frozen `core.py` ruled out a per-result marker, so a content marker was used.
  - **Leg 4:** "already applied" was unreachable behind the stale precheck, so a re-read was added.
  - **Leg 5:** the client marked only routine turns as server-started, so a small client tweak landed.
  - **Leg 6:** held cards never released on Stop, and the snapshot arrived after the history render.
  - **Leg 7:** the notes record needed an eager owner, and the leg was split.
- **Batches with checkpoint commits** (A: Legs 1-3, B: 4-5, C: 6-8) kept each review scoped and each commit green.
  - All three batch reviews confirmed with no blocking issue, and fixes landed before each commit.
  - The accessibility review in Batch C found four real issues: over-announcement, double alerts, unfocusable busy buttons, and duplicate names.
- **The adopted eval method worked as designed.** It was run for the first time here (operator: "right as it was").
  - The first fairness pass, 18 runs, found three unfair checks: the `done!` false positive, the `set up to` false positive, and a key-ask check that missed real asks.
  - It also found a real product gap: GleepGlorp's routine field definitions gave no schedule shape. Routine proposals took 12-20 calls or failed; after the fix they took 2-5.
  - All of this surfaced before any large round. Small gated rounds kept total quota at roughly 250 Haiku runs.
- **The HAT passed 9/9 on the first walk**, with no fixes. That is the first clean HAT in this mission, after Flight 1's board rework.
- **The option board before legs were locked** (Flight 1's recommendation 3) worked. The operator picked card A, approval line B and editor note A from three, two and two options. Nothing was redesigned in the HAT.
- **The shared service extraction shrank `api.py`** from 7,537 to 7,129 lines, and left every existing agent, rule and routine test green and unedited.

## What Could Be Improved

### Process
- **Plans assumed facts a short code survey would have caught.**
  - The flight spec needed two Architect cycles, and the high-risk legs one or two Developer cycles each. Most high issues were concrete facts about the code, not design misjudgements:
    - re-entry of `write_transaction`;
    - the frozen `core.py`;
    - `turn-frames.js` keying in-flight state on `source === 'routine'`;
    - the snapshot ordering;
    - the four test fakes implementing `save`.
  - A survey before the spec, as was done ad hoc for Legs 6, 7 and 9, would have moved them earlier. The Architect recommends making it a step for high-risk legs.
- **Leg sizing needed one more split**: Leg 7 became Legs 7 and 8 at review. This is better than Flight 1 (two splits), and the reviewer, not the plan, caught it again.
- **Crew rules slipped again (recurring).**
  - Leftover `sleep 1500`-`1790` timers: five, from the Leg 5 Developer.
  - Agents reporting while their own background work still ran (Legs 2, 5 and 6).
  - A Developer that ran out before writing its flight-log entry (Leg 2; the Flight Director wrote it).
  - A lane run concurrently with the unit tier (Leg 10), which breaks the host policy.
- **No flight-end full gate before landing.** Each batch ran its unit tier and owning lanes. The debrief's fresh run was the first full gate on HEAD. It was green, but it showed the targets breached (below).
- **Leg 10 was not separately reviewed,** at the operator's request after a token squeeze. The prompt ship and guide topic went straight to commit. This debrief's gate and the HAT cover them functionally.

### Technical
- **`apply.py` (528 lines) has two translation paths.**
  - Agents and rules raise `AgentWriteError` and `AgentStaleError`. Routines raise their own field, stale and limit types.
  - Every new kind in Flight 3 adds a branch.
  - The Architect recommends a small protocol (a service raises one `ApplyError(kind, items, stale)`), with each kind's mapping in its own service.
- **Agent-shaped client modules.**
  - `proposal-cards.js` is 675 lines, the largest chat module. `agent-editor-follow.js` is 329 lines.
  - Flight 3's kinds need a per-kind renderer and follow registry. The labels are already served from `shape.py`, so the split is cheap now.
- **`shape.py` is 619 lines** and holds every kind. Split it by kind before a third or fourth kind lands.
- **Prompt headroom is about 20 tokens.** `p3` is 428 against a cap of 450, and Flight 3 adds kinds and form filling. That needs either a cap decision or field definitions moved further into `read_app_config(kind="fields")`.
- **`LIMITS_TOOL_FREE` is product-only.** No candidate file can override it, so an eval can't vary the tool-free text.
- **Brittle regex eval checks.** The key-ask and claim checks went through three fairness iterations. Two residuals are recorded: "paste your key and I'll add it to the provider", and "share the key … enter it there".
- **The socket gap.** A window opened straight into Agents has no chat socket, so it gets no live follow-through. The leave guard keeps the "unsaved edit while approving" case to a second window today. Flight 3's overlay should own one socket from page load.
- **Duplicate MCP or knowledge-base names** can put a return-path tile note on the wrong tile (accepted, low).
- **Typing debt:** five `# type: ignore` sites in the proposals code (squawk 0391).

### Documentation
- `the_one/agents.md` covers each leg's section. It lacks one overview of the proposal lifecycle:
  - open, then resolved;
  - `ProposalOpen` and `_AlreadyResolved`;
  - the guard/continuation split;
  - the shared-service rule (API and apply call one service).
- **CLAUDE.md "Full-gate target"** is now stale: measured above both targets (below).

## Test Metrics
All numbers are the Developer's fresh debrief runs at `5f749e85`. Prior figures come from the Flight 1 debrief and CLAUDE.md.

**Unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`, start load 0.08, quiet):
- 11,031 passed, 15 skipped (the expected netns set), 0 failed.
- 343.5 s pytest time, 374 s wall.
- Against Flight 1's 10,695 passed in 308.75 s: +336 tests, +34.8 s (+11%, about 0.10 s per test). The new tests are almost all proposals, services, `turn_host`, taint and provenance files.
- The 350 s unit target has about 2% headroom on pytest time, and wall time is already over it.
- The suspected flake `test_purge_loop_catch_up_sweeps_due_db` did not recur.

**Browser** (`--parallel 3`, netns, WebKit required): `PARALLEL_RESULT rc=0 total=2459s lanes=20 failed=-`.
- **Not valid for budgets.** The run started at load 1.46, residual from the unit run, with no other test process.
- **Against Flight 1:** 2,270 s, also loaded, so +189 s (+8%).
- **Full gate against target:**
  - 374 s + 2,459 s = 47.2 min, against the 43-minute target (46.7 min on pytest time).
- **Lanes over budget:**
  - `mcp`: 391 s against 330 (+18.5%);
  - `agent-routines`: 345 s against 300 (+15%);
  - `chats-transcript`: 541 s against 540, at the ceiling; it grew this flight;
  - `chats`: 420 s against 420.
- **Lanes off their measured column by more than 15%:**
  - `contracts-chat`: 126 s against 100 (+26%), within its 150 s budget; it grew this flight;
  - `contracts-widget` and `contracts-widget-lifecycle`: their measured figures were solo provisional readings.

**Reading:**
- `mcp` and `agent-routines` gained no files this flight. Their overruns look like load and stale budgets, not regression.
- `chats-transcript` and `contracts-chat` grew from this flight's tests.
- Re-budget only from a truly quiet run (CLAUDE.md quiet-host rule). That run has been owed since Flight 1 (squawk 0389).

**Flakes:** none in the debrief runs.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Proposals scoped to agents, rules and routines; the other kinds move to Flight 3 (operator) | Keep one write boundary per flight | Yes: split by kind when each kind needs its own service and editor seam |
| Content marker plus per-path provenance instead of per-result metadata (DD9 amended) | The frozen `core.py` cannot carry result metadata | Yes: provenance by who can write a value, failing closed |
| `TurnHost` moved to `sessions/turn_host.py`; `append_marked_message` added | Routes cannot import `app.py`; non-turn appends needed the session lock without turn side effects | Yes: a server-started turn goes through `TurnHost` |
| Leg 7 split into 7 and 8 | Too large for one pass | Yes: size by capability at design |
| `approved_no_turn` event added at Leg 6 design | The quiet line needs to know whether a turn followed | No (one-off) |
| Fairness pass moved from Leg 9 to Leg 10; `no_delete_proposed` dropped | It spends quota; the check could never fail | Yes: offline setup leg, then a gated rounds leg |
| Fairness fix batch, second fairness pass and an n=5 recheck added (operator-approved) | The first pass found unfair checks and a product gap | Yes: iterate fairness before the control |
| `p3` shipped on n=5; n=20 baseline folded into Flight 3 (operator) | Token squeeze; the evidence was clear | No: Flight 3 records it |
| `LIMITS_TOOL_FREE` added at ship | `p3`'s limits name tools; the tool-free variant must not | No (one-off) |
| Leg 10 not separately reviewed; lean HAT with no behavior tests (operator) | Token budget; the HAT covered the same paths | No |

## Key Learnings
- **A fairness pass before the first n=5 round found more than checks.** It found a product gap: the routine schedule shape was missing from the field definitions. Read every transcript at n=1 before any larger round.
- **Shared write services are the right seam.** One service that the route and the proposal apply both call means the validation cannot diverge. The `precheck`/`on_commit` hook under the write lock gives one apply and correct staleness for free.
- **Provenance belongs on the data, not the tool.** Classifying view paths by who can write them made "Check this" meaningful. Before this, every proposal was flagged.
- **One window cannot hold unsaved edits while approving elsewhere,** because the leave guard stops it. Live follow-through matters for a second window and the coming overlay. The return path (notes drawn at every mount) is what a single window actually sees.
- **An option board before approval removed HAT rework.** Flight 1's board was approved in one pass and needed six HAT cycles. Flight 2's option board needed none.

## Methodology Observations
Plugin version 1.2.4 throughout.

1. **agentic-workflow, Phase 2a: design reviews keep finding code facts the plan never surveyed** (recurs from Flight 1).
   - **What happened:** every high-risk leg's review (Legs 1-7, 9) found high-severity issues, and most were facts about current code: a transaction guard, a frozen module, a client-side source check, frame ordering.
   - **Expected:** a short read-only code survey of the files a high-risk leg touches, run before the leg spec is written. The Flight Director did this ad hoc for Legs 6, 7 and 9, and those reviews found fewer facts and more design points.
   - **Cost:** about two extra review cycles per flight, and several leg-spec rewrites.
2. **agentic-workflow, crew prompts: the background-work rules still don't hold** (recurs; Flight 1 observation 4).
   - **What happened:**
     - five 25-30 minute `sleep` timers left after hand-back (Leg 5);
     - repeated "waiting on own background work" hand-backs;
     - a lane run concurrently with the unit tier (Leg 10);
     - a Developer that handed back before writing its flight-log entry (Leg 2).
   - **Cost:**
     - the Flight Director stopped tasks with TaskStop;
     - the Flight Director wrote one log entry;
     - one unit-tier reading is invalid.
   - **Expected:** the harness refuses or reaps a crew agent's leftover background tasks at hand-back.
3. **agentic-workflow, Phase 2b: an operator-gated, quota-spending leg still has no shape** (recurs; Flight 1 observation 1, Mission 35).
   - **What happened:**
     - Leg 10 ran as one artifact with gates 0-5.
     - The rounds were really six: two fairness passes, a fix batch, control-and-screen, a recheck, and ship.
     - Each round needed a prep commit, a review, a commit, a run and a report. The leg file was immutable once in flight, so the shape lived only in the flight log.
   - **Cost:** many Flight Director cycles; the leg file no longer described what happened.
   - **Expected:** a leg type, or an explicit pattern, for "gated rounds" whose sub-steps can be appended to the leg.
4. **flight, Phase 5b: the mockup check worked as intended** (Flight 1 observation 3, now addressed in practice). The option board gave three, two and two options, and the HAT needed no redesign. Recorded as a positive data point for the "option boards before approval" practice.
5. **agentic-workflow, Phase 3: no flight-end full gate step before landing.**
   - **What happened:** the batch reviews ran owning lanes and the unit tier, but nothing required a full gate on HEAD before `landed`. The first full gate ran in this debrief, and it showed both targets breached.
   - **Expected:** a full gate on the landing commit before the flight is marked `landed`. Phase 2d covered this when the flight had one review; batch mode bypasses it.
   - **Cost:** the target breach surfaced only after landing.

## Recommendations
1. **Before Flight 3 adds kinds:**
   - an `ApplyError` protocol, with each kind's mapping in its own service;
   - `shape.py` split by kind;
   - `proposal-cards.js` and `agent-editor-follow.js` given a per-kind registry.

   **Critical** for Flight 3's scale.
2. **Flight 3's overlay owns one socket from page load.** That closes the socket gap and makes the unsaved-edit case reachable in one window, so give it browser tests before form filling. **Important.**
3. **A quiet-host full gate, with the targets restated.** Unit is about 350 s (consider raising it to about 400 s, or profile with `--durations`). The full gate is about 47 min against 43. Re-budget `chats-transcript`, `contracts-chat`, `mcp` and `agent-routines` from that one run. **Important.**
4. **A prompt token decision before Flight 3 adds kinds:** about 20 tokens of headroom left. **Important.**
5. **Record the n=20 baseline in Flight 3** on its final set (operator decision). Keep qwen3-4b measured. **Important.**
6. **Make a short code survey a planning step for high-risk legs** (local practice now; methodology observation 1). **Minor.**

## Action Items
- [ ] Quiet-host `make gate`, then restate the CLAUDE.md unit and full-gate targets and re-budget the lanes from that one run (owed since Flight 1; this debrief's numbers are noted on squawk 0389).
- [ ] Squawk 0391: typing pass on the five `# type: ignore` sites in `the_one/gleepglorp/proposals/` (`tool.py`, `shape.py`, `apply.py`).
- [ ] Squawk 0392: `the_one/agents.md` one "Proposal lifecycle" overview (states, `ProposalOpen`/`_AlreadyResolved`, guard and continuation, the shared-service rule).
- [ ] Flight 3 design: the `ApplyError` protocol; split `shape.py`, the card and follow registries; the overlay owns the socket; a prompt token budget decision; the n=20 `m36f2-gleepglorp` baseline on Flight 3's set.
- [ ] Flight 1 debts still open, to carry into Flight 3 design:
  - one "who uses a provider" helper before provider proposals;
  - a decision on the two notes tables.

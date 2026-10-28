# Flight Debrief: Chats, and closing every count to zero

**Date**: 2026-10-28
**Flight**: [Chats, and closing every count to zero](flight.md)
**Status**: completed
**Duration**: 2026-10-26 to 2026-10-28.
- **2026-10-26:**
  - planning from `main` at `2e82aaa`;
  - two surveys (code; presentation, 242 screenshots);
  - the operator's review page;
  - two Architect cycles.
- **2026-10-27:** batches B1-B5 (legs 01-09b), one checkpoint commit per batch, and HAT step 1.
- **2026-10-28:**
  - the HAT, steps 2-8, with four features promoted (10a-10d);
  - the HAT batch review in three cycles;
  - the quiet-host gate;
  - the spec re-runs;
  - the landing (draft PR #332, `282e8bcd`).

**Legs Completed**: 19 of 19:
- 14 autonomous legs: 01, 02, 03a-03c, 04, 05a-05c, 06, 07, 08, 09a, 09b;
- the HAT (10);
- four HAT features (10a-10d).

Architect cycle 1 split three planned legs: 03b into 03b/03c, 05a into 05a-05c, and 09 into 09a/09b. No leg was aborted or reopened. 257 files changed, +24,811 / -10,165, over 7 commits.

**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
- **The chat area is on the control library.** `chat.js` went from 2,399 lines to 565, across nine modules under `areas/chat/`. The largest is `agent-drawer.js` at 744; leg 02 added `send.js`, and leg 10b added `chat-activity.js`.
- **Six chat controls** are in `js/ui/` with update handles and contract tests in both engines:
  - `composer`;
  - `message`, with the attribution and the reply Copy;
  - `thinking`;
  - `trace`;
  - `telemetry`;
  - `notice`.

  Also in the library now: `App.ui.badge.live`, `App.ui.modelList` and `App.ui.noteFlag`.
- **Every count is at zero:**
  - `OWNERSHIP_ALLOWANCE`, `TOTAL_USES` and `MOVES`, from 25 rows / 36 uses;
  - `HTML_SINK_ALLOWANCE`, from 5;
  - the retired-API aliases: `App.confirmDelete`, `App.consentLink`, `App.showFlash`, `App.icon`, `App.iconNode`, `App.escapeHtml` and `App.escapeAttr` are deleted;
  - the catalogue's "not yet defined" rows, now a unit assertion;
  - the line guard, which holds only `provider-editor.js`, per D8.
- **The flash contract** (the Flight 5 debrief's Recommendation 1):
  - one page region;
  - toasts follow the top modal and survive its closing;
  - the newest replaces the one showing;
  - about 30 callers dropped `container`.
- **Markdown security:**
  - DD9's negative tests went in first, and 27 failed on the old renderer;
  - `safeHref` became same-origin and rejects backslashes and controls;
  - the fence language is limited to its first token;
  - strikethrough, task lists and bare-URL links are in, with their negative cases;
  - the code-block Copy is on the library.
- **The planning features, F1 and F2:**
  - F1, Copy on every finished reply (the markdown source);
  - F2, the step-limit notice across the agent loop, WebSocket, connectors, REST and the CLI, with its flag lifecycle and the broadcast-only `step_limit` frame.
- **The planning defects 0.1-0.4 and DD11 1-11** are fixed. Each has a test, and most were seen failing first; the exceptions are recorded per leg in the flight log.
- **The library squawks** 0185, 0215, 0249, 0259, 0269, 0270, 0271 and 0272 are done, plus 0276 (found and fixed in leg 09b).
- **The HAT:**
  - three inline fixes: the platform badge pill, the key-change hint, and the button-aware step-limit copy;
  - four features through the fix-vs-feature gate:
    - 10a, up to 10 queued messages;
    - 10b, Chats row activity, server-driven by `track_turn`;
    - 10c, per-chat drafts;
    - 10d, step-limit Continue.

### Mission Criteria Advanced
This flight closes the mission's library criteria:
- every control is defined once;
- a change reaches every place;
- no HTML-string markup outside markdown;
- styles are owned by controls;
- the area code is organised by surface, with every entry module at 800 lines or fewer;
- the catalogue is complete.

The looks criterion holds for this flight's surfaces: the operator approved the before and after sets. "Existing behaviour holds" holds too: the gate is green, and the mission-close specs passed in leg 09b. The re-authored specs passed again at the HAT close.

The mission-level boxes in `mission.md` are still unchecked: that is the mission debrief's call. Flight 7 (alignment) stays optional.

## What Went Well
- **The split came first (DD3, leg 02).** It moved 2,398 lines into eight modules with the full gate green, before any behaviour changed. Every later migration, and all four HAT features, landed in small modules. The hold queue, the activity bookkeeping and the drafts each have an obvious home. This is the third flight in a row where a behaviour-free split leg paid for itself (studio in F2, the MCP editor in F5).
- **New `ui-*` class names, then a handover (DD4).** The ownership guard counts owned classes anywhere outside `js/ui/`. Without new names, every chat module would have carried uncovered allowance rows until its consumer moved. Instead each consumer leg deleted its legacy classes, so DD14's empty allowance could be reached and was reached.
- **The planning surveys.** The code survey and the presentation survey (242 screenshots) turned up 4 defects, 18 obvious items and 14 taste items. The operator decided all of them on one review page the same day, so no planned visible change surprised anyone at the HAT. The operator's note on that page became F1 and F2.
- **Tests failed first, and falsification held.** Almost every defect fix and security case was seen failing on the old code. Squawk 0276's fix and 0249's stubs were falsified and then reverted. Where a test could not fail first (for example the latent `blocked || busy` Send case), the FD said so in the log.
- **The fix-vs-feature gate held under pressure.** Four operator requests mid-HAT each got a design review, a leg and a review. The reviews caught real state bugs before landing:
  - 10b cycle 1: needs rework;
  - the batch review: a stuck "working" row, a draft resurfacing after promotion, and an image misrouted in a second pending chat.

  None of these reached the operator.
- **The quiet-host discipline.** Every budget reading came from a quiet `--parallel 3` run, with start loads recorded. When the 09b run failed on a WebKit timing flake, the FD did not ask for a waiver: it fixed the flake (squawk 0276) and re-ran.
- **Batch mode with one closing HAT** (the operator's standing preference, confirmed at this debrief: "keep it"). Five checkpoint commits gave clean rollback points, and the HAT walked a single ledger of 53 rows.

## What Could Be Improved

### Process
- **The HAT turned up daily-use gaps that planning could have found.** The operator's view ("mixed"): some were foreseeable, others only show up in use.
  - The planning survey was a screenshot survey. It saw states but not workflows: sending twice, switching chats with a half-typed message, watching a connector chat from another chat.
  - The one-slot queue and the lost draft could have been found by a scripted operator walk at planning.
  - Row activity and Continue are more plausibly in-use discoveries.
  - Cost: four legs, a design review each, and a three-cycle batch review, all after the flight was otherwise closed.
- **The HAT batch review hit the 3-cycle cap.** All three cycles found bugs in leg 10c's draft routing, a state model designed in an afternoon under HAT time pressure. Cycle 3 confirmed, so it was not escalated, but there was no margin left.
- **A full-run failure from a missed pin.** Leg 10b's test sweep moved the projection pins it knew of (`test_store_static.py`, `test_web_list_sessions_projection.py`, `test_store.py`). It missed `tests/browser/test_seeders.py`, which pins an exact session row in the `shared` lane. That cost a failed 28-minute gate run and a solo re-run.
  - The DD13 rule "grep after every move" names classes and paths. It does not name a payload shape gaining fields.
- **One draft spec has still never run.** `chat-loop-hang-and-cancel` needs a live Sonnet key, outbound network and a port-8485 setup, so the flight carried it again. Its hold-queue rows are covered by browser tests, but the spec's real-provider hang path is not.

### Technical
- **Nothing enforces `track_turn` as the only turn entry.** Web and connector turns go through `the_one/sessions/_locks.py:track_turn`. The resume-after-auth path is untracked by design (leg 10b's non-goal), so a turn paused for sign-in reads idle. A future turn path that takes the lock directly would silently skip the `busy` / `turn_seq` pushes. A unit guard would catch that: today `session_locks[` is used only inside `track_turn`.
- **The drafts state model is heavier than it needs to be** (the Architect's assessment). `draftOwner`, `draftEpoch` and `promotedKeys` (keyed by epoch, pruned to 8) exist only to route an image read that finishes after the user has moved on. The epoch exists because two pending chats for the same agent share the `n:{agent}` key.
  - A unique key per pending chat, plus a single promoted-key alias resolved once, would remove the counter and the arbitrary cap.
  - It works and is covered by 10 browser tests, so this is a candidate for a later refactor, not a defect.
- **`turn_seq` is in memory.** It resets on restart; the `boot_id` prefix is the mitigation, and the client re-baselines on an epoch change. That is deliberate, and `agents.md` already says the `boot_id` is random per process.
- **The shared `state` object** in `areas/chat.js` keeps growing: drafts, the epoch, promoted keys, the hold queue and the activity bookkeeping. It works, but it is a grab-bag that the next chat flight should look at.

### Documentation
- **CLAUDE.md's credential instruction is wrong.** "Start the instance first (it creates the file on first launch)" is false for `the-one serve`.
  - `the_one/main.py` uses the read-only lookup.
  - `get_credential()` (create on first use) is called only from `the_one/interfaces/desktop/takeover.py`.
  - So only the desktop app and `the-one rotate-api-credential` create the file.

  Both behavior-test Executors hit a 401 first, then ran `rotate-api-credential` themselves. A doc fix: squawk 0278.
- **The spec follow-ups** in both HAT-close run logs: `agent-step-limit-notice` has 6 items and `mcp-sensitive-headers-round-trip` has 4. They are listed in the run logs' Orchestrator Notes and should be re-authored deliberately, not at the next run.

## Test Metrics

The debrief's Developer ran both tiers once on the landed tree (`282e8bcd`). The host was quiet at the start: 1-minute load 0.79, no test process. The tiers ran one after the other, never concurrently. Counting basis: pytest's own summary for the unit tier, and the junit `tests` sum for the browser lanes.

**Unit** (`THE_ONE_TEST_NETNS=1 make test-unit`): 7845 passed, 0 failed, 15 skipped, 349 s wall (345 s pytest time).
- The 15 skips are the expected netns set: 11 Windows PTY, 3 root-only permission and 1 locale.
- Against earlier flights: F1 6705 (281 s), F2 6717 (300 s), F3 6773 (297 s), F4 7188 (334 s), F5 7665 (335 s), F6 7845 (349 s).
- This flight added 180 tests, and the wall time rose 4%. The tier has crept 24% over the mission and is still unprofiled (squawks 0222 and 0234, now carried in five debriefs).

**Browser** (`--parallel 3`, `THE_ONE_REQUIRE_WEBKIT=1`, `THE_ONE_TEST_NETNS=1`): `PARALLEL_RESULT rc=0 total=1695s lanes=16 failed=-`. 3574 tests, 0 failed, 5 skipped (the unchanged WebKit contract skips). No lane went over budget, no test flaked, and nothing was re-run.

| Lane | F5 final (s) | 09b deciding (s) | HAT batch (s) | Debrief (s) | Budget (s) |
|---|---|---|---|---|---|
| routing | 526 | 548 | 532 | 539 | 600 |
| agents | 438 | 476 | 461 | 467 | 540 |
| contracts-controls | 344 | 431 | 429 | 432 | 600 |
| providers | 319 | 339 | 339 | 348 | 420 |
| shared | 285 | 341 | 336 | 339 | 420 |
| chats | 383 | 305 | 335 | 337 | 420 |
| library | 342 | 339 | 333 | 336 | 420 |
| knowledge | 294 | 305 | 295 | 300 | 420 |
| agent-tabs | 282 | 294 | 292 | 298 | 360 |
| mcp-connection | (new) | 280 | 275 | 277 | 390 |
| settings | 260 | 275 | 270 | 274 | 360 |
| mcp | 507 | 256 | 255 | 260 | 330 |
| settings-tools | 235 | 255 | 253 | 251 | 330 |
| chats-transcript | (new) | 191 | 250 | 248 | 330 |
| contracts-overlay | 173 | 239 | 242 | 237 | 330 |
| contracts-chat | (new) | 59 | 53 | 53 | 90 |

- **Total wall time:** F4 1571 s, F5 1581 s, 09b 1662 s, HAT batch 1679 s, debrief 1695 s. That is +7% over Flight 5 while the test count grew 28% (2802 to 3574): the three new lanes kept the parallel run near its longest-lane floor.
- **The critical path is still `routing`,** at 539 of 600 s (90%), with `agents` at 86%. These two are next for a split or re-budget.
- **`chats-transcript`'s step is real and stable:** 191 s, then 250 s with the drafts tests, then 248 s. The 330 s budget set at the HAT holds.
- **`mcp` halved** (507 to 260 s) because of squawk 0271's split, and `chats` dropped from 383 s to the 305-337 s range because of the `chats-transcript` split.
- **The lane readings are steady across three quiet-host runs:** every lane is within about 3% of its HAT-batch reading.
- **Gate failures during the flight** (all in the flight log):
  - 09b's first run: the WebKit `focusAfter` flake, squawk 0276, fixed test-side and not seen since;
  - the HAT batch run: the `test_seeders.py` exact-row pin that missed `busy` and `turn_seq`.

  Neither recurred.
- **Within-flight full runs:**
  - 1561 s (leg 02, 15 lanes);
  - 1573 s (B2);
  - 1795 s (B3);
  - 1640 s (B4);
  - 1763 s and 1662 s (09b);
  - 1679 s (HAT batch);
  - 1695 s (debrief).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| An eighth chat module, `send.js` (leg 02) | DD3's remainder would have left `chat.js` at about 760 lines before the plumbing, at risk of the 800 cap | No: it is within the acceptable variations; the estimate was the problem |
| Four HAT features became legs 10a-10d | Operator requests that add behaviour, routed through the fix-vs-feature gate | Yes: the gate worked, and each got a design review and a leg |
| Squawk 0276 fixed inside the flight, not waived | The WebKit flake blocked the 09b criterion (rc=0); the FD judged it in the flight's path | Yes: a grounding-in-path flake is fixed, not waived |
| `chats-transcript` re-budgeted from 240 to 330 s after the HAT | The drafts tests moved it past 15% (191 to 250 s) | It follows the existing rule |
| `chat-loop-hang-and-cancel` not run | It needs a live provider key and outbound network; it is a never-run draft | No: give it an owner or retire it (Action Items) |
| Leg 10b's resume-after-auth turn is untracked | Scoped out at design review | No: it is a known gap, listed under Technical |

## Key Learnings
1. **A screenshot survey finds states; it does not find workflows.** The presentation survey found every visual inconsistency the operator cared about, and the HAT found none of those. What it found were multi-step usage gaps. A planning survey for an interactive surface needs a scripted operator walk (multi-message, multi-chat, switch-away-and-back), not just a capture matrix.
2. **A late feature with async state needs the same design depth as a planned one.** Leg 10c's design review approved it, but the batch review then found three routing bugs across two cycles. Async handlers in the chat area should "capture identity at start, re-resolve at completion". That rule should be written down in `agents.md` and named in any leg that adds an async handler.
3. **A pin sweep must cover payload shapes, not just names.** When a server projection gains fields, grep the tests for every exact-dict assertion on that shape (`== {` near the projection's keys), in every lane, before signalling.
4. **Split-first flights scale.** Three flights in a row (F2, F5, F6) split the largest file behaviour-free before migrating it. Each time, later legs and late features landed cleanly. This should be a default for any area file over the line guard.

## Methodology Observations
Plugin version 1.2.3 throughout. All of these are concrete and recorded, not judged.

- **flight, Phase 4 (crew interview) and the planning surveys.** The flight skill asks about the HAT's scope and form, but not for a usage walk of the surface being migrated.
  - What happened: the FD ran a screenshot-based presentation survey, which the skill does not prescribe either. It was effective for looks. Four daily-use gaps then surfaced at the HAT, and the operator judged some of them foreseeable.
  - Expected: for a flight that migrates an interactive surface, the crew interview asks the operator something like "walk it as a daily user: what do you do that it does not support?", or a survey drives the main workflows.
  - Cost: four post-close legs and a three-cycle review.
- **agentic-workflow, Phase 2b (the HAT fix-vs-feature gate).** The gate promotes a feature to "a scoped design review before implementation". Here four features were promoted one after another during one HAT session. Each got its own design review, but they were reviewed as one batch at the end, and that batch hit the 3-cycle code-review cap.
  - Expected: guidance on whether promoted HAT features review as one batch or per feature, and whether the 3-cycle cap applies per feature or per batch.
  - Cost: no rework beyond the cycles, but no margin was left.
- **agentic-workflow, leg design (risk checks, interface changes).** The "grep for consumers of any changed symbol" check is worded for symbols. Leg 10b added two fields to a server projection, and its sweep missed one exact-dict pin in another lane.
  - Expected: the interface-change check also covers adding fields to a response shape that tests may pin exactly.
  - Cost: one failed full gate run (about 28 minutes) and a solo lane re-run.
- **behavior-test, Phase 1 (preconditions) and the project's credential convention.** Both Executors followed CLAUDE.md's "start the instance first (it creates the file)". The file did not appear, so both improvised `rotate-api-credential`.
  - This is a project doc defect, not a plugin defect. Recorded because the skill's precondition check takes the project doc on trust, and the Executors recovered only because they could read the code.
- **behavior-test, never-run draft specs.** `chat-loop-hang-and-cancel` was re-authored in two legs (05c, 10a) and has never run, because its apparatus needs a live paid provider.
  - Expected: the authoring guide flags a spec whose apparatus cannot run on a dev host as a draft with a named run owner, or asks for a mock-apparatus variant.
  - Cost: the spec was re-authored twice with no verification.
- **flight-debrief, Phase 2 (Developer test metrics).** In Flights 4 and 5 the Developer read the landing gate's junit instead of re-running. This time the FD asked for a full re-run, and it took about 33 minutes (unit 349 s plus browser 1695 s) on a tree unchanged since the HAT batch's gate.
  - The result matched that gate within 1%, so it added confirmation but no new information.
  - Expected: the skill allows the Developer to use a recorded full run on the same commit, as the previous two debriefs also suggested.
  - The debrief's Architect ran concurrently and read-only, so the quiet-host rule held.

## Recommendations
1. **Add a usage walk to planning for interactive surfaces.** The next flight that migrates or redesigns an interactive surface runs a scripted operator walk at planning:
   - send twice;
   - switch away and back mid-draft;
   - work with two chats live;
   - watch a background chat.

   The crew interview also asks "what do you do daily that it does not support?". Record the answers as approved features, as DD8 did. *Important.*
2. **Fix the CLAUDE.md credential instruction** (squawk 0278). The behavior-test section should say that a fresh scratch instance needs `THE_ONE_DATA_DIR=<dir> the-one rotate-api-credential` before the first authenticated request, because `serve` never creates the file. *Important: every behavior-test run hits it.*
3. **Give `chat-loop-hang-and-cancel` an owner or retire it.** Either run it once with a live key on a dev instance, or rewrite its hang path on the mock provider (`delay_ms` plus a stub stream) so it runs offline. *Important.*
4. **Guard `track_turn` and write down the async rule:**
   - a unit check that no turn path takes `session_locks[...]` outside `track_turn` (squawk 0280);
   - the "capture identity at start, re-resolve at completion" convention for async handlers in the chat area.

   *Minor.*
5. **Investigate the MCP editor's Save state right after a save.** In the HAT-close run (`step-8-edited.png`), Save rendered disabled on a dirty form while the previous save's toast was still showing. It may be a transition caught mid-way, or a real window in which Save ignores the dirty state. One focused browser test would settle it. Squawk 0279. *Minor until reproduced.*

**Carried items:**
- squawk 0277 (agent POST with an unknown provider returns 500; hit again by both Executors' seeds);
- 0275 (`App.safeUrl`);
- 0260 (the stdio cause text);
- 0273 (agent editor header errors not announced);
- 0222 and 0234 (profile the unit tier);
- the mission's knowledge search score floor and "Add file";
- the OAuth MCP fixture sortie;
- the drafts state simplification (Technical);
- the 09b and HAT watch items:
  - the trace count reads calls plus results;
  - the lingering toast;
  - the faint Dark pending wash;
  - the picker and model-list a11y notes (the 40px dead rule, the search-list meta without a title, truncated model names only in the title, model rows without list semantics, table regions all named "Table", and the toast coverage gap for ledger rows 37/38);
  - the crew-file "aria-checked" wording;
  - the resume-after-auth row-activity gap.

## Action Items
- [ ] Squawks for the small, bounded follow-ups (see Follow-up Squawks).
- [ ] Mission 31 debrief: assess the mission criteria, now that the counts are at zero; decide on Flight 7 (alignment, optional).
- [ ] Next planning conversation for an interactive surface: the usage walk (Recommendation 1).
- [ ] `chat-loop-hang-and-cancel`: an owner and a run, or an offline rewrite (Recommendation 3).
- [ ] Re-author the two specs' follow-ups from the 2026-10-28 run logs (squawks 0281, 0282).

## Follow-up Squawks
Logged by the operator's decision on 2026-10-28, all `routine` and left open:
- **[0278](../../../../squawks/0278-claude-md-serve-credential-creation.md)** (servicing): CLAUDE.md says `serve` creates `api-credential` on first launch; it never does (Recommendation 2).
- **[0279](../../../../squawks/0279-mcp-editor-save-disabled-after-save.md)** (defect, reproduce first): the MCP editor's Save may render disabled on a dirty form right after a save (Recommendation 5).
- **[0280](../../../../squawks/0280-guard-track-turn-single-lock-entry.md)** (servicing): a unit guard that every turn takes its lock through `track_turn` (Recommendation 4).
- **[0281](../../../../squawks/0281-agent-step-limit-notice-spec-follow-ups.md)** (servicing): `agent-step-limit-notice`'s six spec follow-ups.
- **[0282](../../../../squawks/0282-mcp-sensitive-headers-spec-follow-ups.md)** (servicing): `mcp-sensitive-headers-round-trip`'s four spec follow-ups.

Kept as recommendations, because each needs a design call:
- the planning usage walk (Recommendation 1);
- `chat-loop-hang-and-cancel`'s apparatus (Recommendation 3);
- the drafts state simplification;
- the async-handler convention in `agents.md`.

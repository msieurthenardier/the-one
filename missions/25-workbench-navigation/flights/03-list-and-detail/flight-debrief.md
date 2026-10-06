# Flight Debrief: List and Detail

**Date**: 2026-10-05
**Flight**: [List and Detail](flight.md)
**Status**: landed
**Duration**: 2026-10-01 to 2026-10-05
- The flight was planned and flown on 2026-10-01 and 2026-10-02 in one autonomous session.
- The operator checkpoint followed on 2026-10-05, and leg 7 was then implemented and re-run.

**Legs Completed**: 9 of 9.
- The draft had 6 legs, and Architect cycle 1 split legs 4 and 5, making 8.
- Leg 7, `providers-tiles`, was added after the DD14 operator checkpoint.

**Plugin version**: mission-control 1.2.0

The operator was not interviewed for this debrief; the run was autonomous. The checkpoint's
answers (DD14) are recorded in the flight log and stand in for the operator's view. The other
inputs were:
- the flight log;
- a Developer debrief interview with a full sequential test-metrics run;
- an Architect design review of the outcome;
- the ten behavior-test run logs: six at the close gate and four leg 7 re-runs.

## Outcome Assessment

### Objectives Achieved

The objective was met. Each destination is now a list beside a detail pane, as the
approved boards draw it.

- **Agents.**
  - An alphabetical `App.ui.listPane` column with a filter (by name, model or provider) and
    a count.
  - The current tabbed editor, hosted beside the list with chrome-only changes:
    - a breadcrumb whose last segment closes the item;
    - the `editor-unsaved` caption;
    - no Back control.
  - `#agents/~new` as the create route.
  - The list stays responsive at the 32-agent checkpoint seed and the 60-agent ratio
    check.
- **Library.**
  - One grouped list (Knowledge bases · MCP servers · Connectors) with `App.usage` meta and
    an Add menu (the first production `App.ui.menu`).
  - The knowledge-base, MCP-server and connector editors are hosted beside it.
  - Every type has a `~new` route, and creating opens the new item, which closes squawk
    0101.
  - The sections nav and the three tile grids are retired.
- **Settings.**
  - A grouped `App.ui.navGroups` nav (General, Models, Defaults for agents, Developer).
  - The old General page is split into Appearance, Prompts and Encryption, with redirects.
  - Every page has a page header.
  - Providers and Built-in tools keep their list visible, with the item opening below it.
  - After the checkpoint, Providers is a tile grid matching Built-in tools (leg 7).
- **Shared plumbing.**
  - `App.store` grew from 2 to 5 collections, with generation-safe invalidation and an
    invalidation map.
  - `App.usage` derives every "used by" count from the agents list.
  - `sync()` announces the `~new` → item transition (Flight 2's announcer gap, closed).
  - One DD8 focus rule after Cancel, close or delete.
  - `_lists.py` for tests, and an AST retired-selector guard with an empty allow-list.
- **Behavior tests.** The close gate passed all six specs, and the leg 7 re-runs passed all
  four affected specs:

  | Spec | Close gate (2026-10-02) | Leg 7 re-run (2026-10-05) |
  |---|---|---|
  | `workbench-navigation` | 28/28 | 28/28 |
  | `list-and-detail` (new) | 38/38, after one fix | 4/4 (targeted: steps 18 and 20) |
  | `system-provider-config` | 20/20 | 20/20 |
  | `shell-navigation-smoke` | 8/8 | 8/8 |
  | `kb-studio-round-trip` | 18/18 | — |
  | `studio-agent-crud` | 18/18 | — |

### Mission Criteria Advanced

- **SC2 (lists stay put).** The list/detail half is delivered. With Flight 2's leave
  guard, SC2 is complete. It is behavior-backed by `list-and-detail` and
  `workbench-navigation`.
- **SC4 (agents at scale).** Delivered:
  - an A–Z list;
  - a name, model and provider filter;
  - a ratio-based filter gate under throttled Chromium;
  - visual checks with 32 seeded agents.
- **SC6 (control library, continued).** `listPane` gains a title count, intro, title style
  and per-group empty states. `navGroups` and `menu` are new. Each has a demo, an inventory
  row and contract tests in both engines.
- **SC8 (matches the approved samples).** The first visual review was held at the DD14
  checkpoint.
  - The operator approved seven of eight questions and changed one: Providers as tiles.
  - That change is recorded as reference spec §13 D5, an operator-approved deviation.
  - Flight 6 closes SC8.
- **SC10 (operable and regression-safe).**
  - The lists, the Add menu and the Settings nav are keyboard-operable with visible focus.
  - Landmarks and the skip link are preserved.
  - Forced-colours cues are added for selected rows and tiles.
  - Suites, guards and specs all pass.
  - The `h1` at the Agents and Library roots is deferred to Flight 6.

## What Went Well

- **One focus rule, written once, settled a dispute.**
  - DD8 says: after Cancel, close or delete, focus the item's own row, else the nearest
    surviving row, else the primary action.
  - Leg 5b's wording disagreed for providers. The Flight Director applied "the flight DD
    governs" out loud, inverted the pinned test by renaming it, and the rule held in every
    later behavior run.
- **The behavior close gate found the flight's only product defect.**
  - Cancel was disabled on a pristine create form in all four editors. They gated Cancel
    on `dirty`, which is wrong in create mode.
  - About 5,000 unit tests and every browser lane missed it. `list-and-detail` L6 caught
    it.
  - It was fixed in-flight (`56f7d75`) under the Witnessed rule: a failed checkpoint does
    not land.
- **The test indirection paid off when the design changed.**
  - Leg 7 reversed leg 5b's table. Because every test reaches rows through `_lists.py`, the
    rename `providers_table` → `providers_list` was a mechanical edit across about 8
    consumers.
  - The AST guard (with no allow-list) keeps the retired selectors from coming back.
- **The checkpoint package produced an actionable answer in one pass.**
  - A side-by-side comparison page of the board against the build:
    - 21 views × 2 themes × 2 sizes;
    - eight explicit questions.
  - A live seeded instance with a fresh handoff on request.
  - The operator answered all eight, and the one change was specific enough to plan as a
    leg the same day.
- **The CDP-driven Chromium apparatus held for ten spec runs across two waves.** Each run
  had its own instance, port and per-run scratch subdirectory, and none collided (Flight 2's
  shared-scratchpad collision did not recur). goldfinch was not needed.
- **No flakes.**
  - The Developer's sequential debrief run had 0 failures and 0 flakes across unit and all
    five lanes.
  - `THE_ONE_TEST_NETNS=1` was carried as a standing prerequisite and kept the WSL2
    network noise out.
- **Splitting legs at the flight design review was right.**
  - Leg 4a/4b and leg 5a/5b each moved a real boundary: route ownership, then chrome.
  - Most legs passed their gates on the first run.

## What Could Be Improved

### Process

- **Important — a board contradicted an adjacent surface, and that was settled late.**
  - Reference spec §8.2 drew Providers as a table, but Built-in tools on the same Settings
    pages was already tiles. DD7 flagged it only as a checkpoint question.
  - The operator chose consistency (tiles). The table cost:
    - leg 7 (two design-review cycles, two reviews, a fix pass);
    - six spec re-authors;
    - four spec re-runs;
    - a landed → in-flight → landed round trip on an open PR.
  - A side-by-side at flight planning would have settled it.
- **Important — the checkpoint came after landing.**
  - The mission placed the operator checkpoint after Flight 3, so its one change reopened a
    landed flight and re-ran the close-gate specs.
  - A mid-flight preview after the last UI leg (5b) and before the behavior close gate
    (leg 6) would have cost the same operator time, without the re-runs.
- **Minor — the flight design review reached its two-cycle cap with high issues still
  arriving.** Cycle 2 raised 2 high and 4 medium issues. Per-leg design reviews compensated,
  but the 6-leg draft was too coarse: create routes sat in L2, and the General split was
  spread. Draft leg boundaries from route ownership first.
- **Minor — the Flight 2 behavior-test crew-file follow-ups were never made.**
  - Flight 2's debrief listed them: per-run scratch subdirectories, a "no unrequested
    state-changing actions" rule, and an input-delivery probe.
  - The Flight Director applied them by hand in every spawn prompt this flight. That
    worked, but it depends on memory.
  - In this flight's re-runs, an Executor again took an extra, unrequested action: it
    opened the guard dialog a second time to read a colour. It was harmless, and it was
    disclosed.
- **Minor — spec wording named the layout noun.** Specs said "table" or "row" where a
  testid or role would have done (`provider-card`, a list labelled "Providers"). One
  presentational change therefore forced six spec edits.

### Technical

- **Tile duplication** (Architect and Developer, independently).
  - `admin/providers-list.js` (240 lines) builds tiles with DOM calls.
  - `admin/tools-grid.js` (317 lines) builds the same tile shape with HTML strings,
    `innerHTML` and `escapeHtml`/`escapeAttr`. That breaks the "no HTML-string sinks"
    convention the `ui/` factories follow.
  - The CSS is split as well: grouped `.tool-tile-link` rules beside a separate
    `.provider-tile*` set, with a hard-coded 128px badge reserve.
  - **Squawk 0116** (names truncate early, or run under the badge) is the visible symptom.
  - The proper fix is an `App.ui` entity-tile factory with a flex title row. The squawk-sized
    fix is the flex title row alone.
  - Flight 3's reconnaissance had marked "tile title runs under the badge" as going away
    with list-pane rows, which held for Library and Agents. Leg 7 brought tiles back to
    Providers, so the problem returned there.
- **Four implementations of one focus rule.** These are `focusAgentRowNear`
  (`studio.js`), `focusLibraryGroupStart` (`studio.js`), `focusProviderRowNear`
  (`admin.js`) and the tools grid's own. Candidate: one `focusNearRow(listEl, idx,
  fallback)` helper.
- **Editor chrome by convention only.** Four editors each implement the breadcrumb, the
  unsaved caption and the Save/Cancel state machine. The create-mode Cancel bug hit all
  four at once. A shared mode-aware editor-chrome helper would make this one code path.
- **`studio.js` is 3,910 lines**, up from 3,183 at Flight 2.
  - It hosts the Agents list, Library routing, three editors' orchestration and **one
    `dirty` flag shared by every studio editor**.
  - The agent save-create staleness bug from the flight-end review came directly from that
    shared flag.
  - DD3 chose to extend rather than split, with guards, and the guards held. Flight 4's
    agent drawer touches this file again.
- **The shared lane keeps growing.** It went from 723 to 867 tests, 627s to 758s
  (12m38s). It is 38% of browser wall time, and still unsplit after Flight 2's
  recommendation.
- **The probe noise floor.** Open a11y squawks 0110, 0113 and 0114 re-trip every hand-run
  a11y probe. Every leg spent review text explaining them, and a new violation could hide
  beside them.

### Documentation

- **The editor Cancel contract is unwritten.** Create mode: Cancel is always enabled (it
  abandons). Edit mode: enabled only while dirty. Every create flow in Flight 4 needs it.
- **`CLAUDE.md` keeps accreting leg narrative.** The always-loaded manual now has one
  paragraph per M25 leg, and the "Settings item pages" paragraph carries a leg 7 amendment
  inside it. Keep `CLAUDE.md` to invariants and move the narrative into `agents.md`.
- **Lane-size drift has no record.** For example, agents went 126 → 130 and library
  138 → 145 between the leg 6 gate and this run. A small table of expected lane sizes per
  flight would let the next Flight Director read a count change as drift rather than noise.

## Test Metrics

The Developer's debrief run, 2026-10-05: sequential, one lane at a time, under
`THE_ONE_TEST_NETNS=1` via `scripts/run-tests.sh`.

| Suite | F1 debrief | F2 debrief | F3 debrief | Delta vs F2 |
|---|---|---|---|---|
| Unit (`make test-unit`) | 4,929 passed, 10 skipped, 667s | 5,001 passed, 10 skipped, 680s | 5,045 passed, 10 skipped, 654s (670s wall) | +44 tests, -10s |
| chats | 41, 99s | 42, 101s | 42 passed, 96s | 0, -5s |
| agents | studio: 188, 3 skipped, 500s | 97 passed, 2 skipped, 225s | 130 passed, 2 skipped, 317s | +33, +92s (+41%) |
| library | (in studio) | 95 passed, 1 skipped, 346s | 145 passed, 1 skipped, 477s | +50, +131s (+38%) |
| settings | 124, 228s | 125, 240s | 178 passed, 335s | +53, +95s (+40%) |
| shared | 694 passed, 4 skipped, 256s | 723 passed, 1 skipped, 627s | 867 passed, 3 skipped, 758s | +144, +131s (+21%) |
| **Browser total** | — | about 1,082, about 1,539s | **1,362 passed, 6 skipped, 1,982s (33m)** | +280, +443s (+29%) |

- **Failures and flakes: none.** Every suite exited 0, and none needed a re-run.
  - The flight log's one-off flakes did not recur. These were the leg 3 shared-lane
    failure, squawk 0115's knowledge-base search race, and
    `test_section_root_scrolls_its_group_into_view`.
  - The counts match the leg 7 gates exactly: unit 5,045, settings 178 and shared 867/3.
- **Skips.** Unit has 10 (unchanged). Browser has 6: 2 in agents, 1 in library and 3 in
  shared. The 3 in shared are WebKit forced-colours sites.
- **Unit is flat in time** while gaining 44 static and unit cases. Most come from
  `test_nav_helper.py` (the retired-selector guard and registry pin),
  `test_ui_library_source.py` and `test_design_tokens_a11y.py`.
- **Agents, library and settings each grew about 40%** in time, all from new and migrated
  flows. Per-test cost was flat:
  - agents 2.4s per test;
  - library 3.3s, still the slowest lane;
  - settings 1.9s.

  The big new files are `test_flow_studio_library_list.py` (1,451 lines) and
  `test_flow_settings_items.py`.
- **Shared** gained 144 tests from the `test_ui_*` contracts running in both engines
  (list-pane, menu, nav-groups and more), on top of the router, guard and store files. It
  is the long pole at 12m38s.
- **Totals.** A sequential run is about 44 minutes (33 browser plus 11 unit), up from
  about 37 at Flight 2.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Legs 4 and 5 split into 4a/4b and 5a/5b at the flight design review | Each bundled route ownership with chrome | Yes. Draft leg boundaries from route ownership. |
| Provider focus after create Cancel and `~new` close aligned to DD8, not leg 5b's text | Leg 5b's wording conflicted with the flight's single rule | Yes. The flight DD governs; invert the pinned test by renaming it. |
| Create-form Cancel fixed during the behavior close gate (`56f7d75`) | A real defect in all four editors, found by `list-and-detail` L6 | Yes. A failed checkpoint is fixed and re-run before landing. |
| `kb-studio-round-trip` step 10 re-run with SIGKILL | The Flight Director's SIGTERM instruction let the graceful drain finish, so resume was not exercised | Yes. The spec now says SIGKILL. |
| Leg 7 `providers-tiles` added after landing; flight reopened (landed → in-flight → landed) | The operator chose tiles at the DD14 checkpoint | Partly. Hold the visual checkpoint before the close gate. |
| Leg 7 re-runs: `list-and-detail` targeted (steps 18 and 20); `save-preserves-config` and `anthropic-plan-signin` wording-only, not re-run | Only the Providers list changed; the other checkpoints passed in full 3 days earlier | Yes, with the scope argued in the flight log. |
| Behavior runs on a CDP-driven headless Chromium, never goldfinch | goldfinch input is still broken (Flight 2) | Yes. It is the DD12 default. |
| `workbench-navigation` L2–L5 on Auto (resolving light) instead of explicit Light | The Light choice was made in an earlier browser context | Yes. Switch theme inside the variant's own fresh context, before step 2. |

## Key Learnings

- **Settle board-versus-existing-surface conflicts at planning.**
  - Where a reference board contradicts a neighbouring surface that already exists, put
    the two side by side before the leg that builds it.
  - Here the operator's answer was the one a side-by-side would have prompted.
- **The behavior gate is the integration gate.** Unit and lane suites prove contracts.
  Witnessed specs prove the interaction state machine. The Cancel defect lived in the gap
  between them, in all four editors at once.
- **Mode-dependent rules belong in the DD.** "Cancel abandons" was in DD8. "Cancel is
  enabled in create mode even when pristine" was not, and that gap was the defect.
- **Indirection layers make design reversals cheap.**
  - `_lists.py`, `_nav.py`, testid-addressed specs and the page-scaffold split (the list
    renderer separate from the item section) turned a reversal of a landed design into one
    leg.
  - The places without indirection (specs that name "table") are where the cost landed.
- **One rule, one implementation.** DD8 is one rule with four code copies, and the editor
  chrome is one contract with four copies. The bug and the squawk of this flight both came
  from copies.

## Methodology Observations

These are recorded, not judged. Plugin `mission-control` 1.2.0.

1. **Mission skill (checkpoint placement), and agentic-workflow Phase 3.**
   - **What happened.** The mission scheduled an operator checkpoint "after Flight 3". The
     flight therefore landed, ran its six-spec behavior close gate, and was then reviewed.
     The one change reopened a landed flight: status landed → in-flight → landed, a leg
     added after landing, and the PR kept open.
   - **Expected.** Either guidance to hold a visual checkpoint before the behavior close
     gate, or a sanctioned "landed, awaiting checkpoint" state with a defined path for
     post-checkpoint legs.
   - **Cost.** One extra leg; six spec re-authors; four spec re-runs (60 checkpoints);
     about a day of elapsed time.
2. **Flight skill, Phase 5b (design-review cap). This recurs from Flight 2, observation 6.**
   - **What happened.** Cycle 2 of the flight review still raised 2 high issues, and the cap
     of two meant the final flight text went unreviewed. Per-leg reviews compensated.
   - **Cost.** None observed this flight. The same pattern appears in two consecutive
     flights.
3. **behavior-test skill, live mode (agent continuity). This recurs from Flight 2,
   observation 1.**
   - **What happened.** Executors and Validators again ended every turn with a final
     hand-back. They prefixed later answers with "my earlier hand-back had already closed my
     run". One Validator delivered its closing summary inside its last verdict, because it
     believed it could not receive `[CLOSING]`.
   - **Cost.** No rework. It adds noise to every message (about 120 checkpoint messages this
     flight).
   - **Expected.** The crew prompt states that the agent is resumed through SendMessage
     after each step.
4. **behavior-test skill (re-run scope after a change).**
   - **What happened.** After leg 7, the Flight Director had to decide which specs to re-run
     and at what scope. It chose full runs for three specs, a targeted run for one (steps 18
     and 20 of 38), and no run for two wording-only edits. The skill and the run-log format
     have no notion of a targeted re-run, so the scope argument lives only in prose (the run
     log's "Why a targeted run").
   - **Expected.** Guidance on re-run scope after a change, and a run-log status or field
     for "targeted".
   - **Cost.** Flight Director judgment time, and a non-standard run-log status ("pass (a
     targeted re-run)").
5. **behavior-test skill, Phase 4 (variants). This recurs from Flight 2, observation 4.**
   - **What happened.**
     - The skill still has no variant (theme) concept.
     - A Light choice made in one browser context did not carry into the fresh tab that
       step 2 requires, so four Light checkpoints ran on Auto.
     - Chromium caps `history.length` at 50, which forces a fresh context per variant.
   - **Cost.** One recorded apparatus deviation, and a Validator warning to resolve
     mid-run.
   - **Expected.** Variant guidance: set the variant inside the variant's own fresh context,
     before the first checkpoint.
6. **Executor crew prompt (unrequested actions). This recurs from Flight 2, observation 5.**
   - **What happened.** An Executor re-opened the leave-guard dialog to read a colour it had
     not captured.
   - **Cost.** None. It was disclosed, and the Validator accepted it.
   - The project's crew file still lacks the rule that Flight 2's debrief recommended; the
     Flight Director carried it in every prompt instead.
7. **agentic-workflow, Phase 2a (leg text versus flight DD).**
   - **What happened.** Leg 5b's acceptance wording ("Add provider, because no row exists")
     conflicted with flight DD8's single focus rule. The skill does not say which governs.
     The Flight Director ruled for the DD, out loud.
   - **Cost.** One inverted test (by rename) and a short Flight Director note.
   - **Expected.** A stated precedence, flight DD over leg text, or a design-review check
     for leg/DD conflicts.

## Recommendations

1. **Hold visual checkpoints before the behavior close gate, and settle board-versus-surface
   conflicts at planning.**
   - For Flights 4 and 5, schedule an operator preview (screenshots and a live instance)
     after the last UI leg and before the close-gate runs.
   - In flight design, list every place a reference board departs from an adjacent existing
     surface, and resolve each with a side-by-side.
2. **Extract the shared pieces that bit this flight, in Flight 6 or the next mission:**
   - an `App.ui` entity tile with a flex title row, replacing both Settings tile builders
     and the `tools-grid.js` HTML-string sink. This fixes squawk 0116 properly;
   - one `focusNearRow` helper for DD8;
   - a mode-aware editor-chrome state machine (breadcrumb, caption, Save/Cancel).

   Before Flight 4 adds the agent drawer, decide whether `studio.js`'s single `dirty` flag
   becomes per-editor state.
3. **Split the `shared` browser lane now** (squawk 0117). It is 12m38s and 38% of browser
   time, and Flight 4 adds dual-engine contracts for the picker and the palette.
4. **Write the editor Cancel contract into `agents.md` before Flight 4's create flows**
   (squawk 0118). Author behavior specs against testids and roles, not layout nouns.
5. **Update `.flightops/agent-crews/behavior-tests-execution.md`** with Flight 2's three
   rules (per-run scratch, no unrequested actions, input-delivery probe), plus "you are
   resumed by SendMessage after each step" and the variant-context rule. Then the Flight
   Director stops carrying them in every prompt.

## Action Items

- [x] Squawk 0116: Settings tile names truncate early beside the badge, or run under it
  (logged at leg 7's re-runs)
- [x] Squawk 0117: split the `shared` browser lane (logged with this debrief)
- [x] Squawk 0118: document the editor Cancel and dirty contract in `agents.md` (logged
  with this debrief)
- [ ] Operator: merge PR #219. It is open and ready for review, and Flight 4 branches from
  `main` after it.
- [ ] Flight 4 planning:
  - add an operator preview before the close gate (recommendation 1);
  - decide on the `dirty` flag (recommendation 2);
  - carry checkpoint question 7 (focus drops to BODY after Create, Save and Test);
  - reuse `App.store`/`App.usage` for the picker and the drawer.
- [ ] Flight 6 (alignment): the deferred `h1` at the Agents and Library roots; the
  destination-specific aside label; the entity-tile extraction, if not done earlier.
- [ ] Near term: the behavior-test crew-file update (recommendation 5).
- [ ] Routine maintenance: trim the M25 leg narrative out of `CLAUDE.md` into `agents.md`;
  add a lane-size table to the testing docs.

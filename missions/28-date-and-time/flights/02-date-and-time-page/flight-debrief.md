# Flight Debrief: The Date and Time Page

**Date**: 2026-10-11
**Flight**: [The Date and Time Page](flight.md)
**Status**: landed
**Duration**: 2026-10-10 to 2026-10-11
**Legs Completed**: 3 of 3
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved

- **Settings › General › Date and time**, built from the approved canvas:
  - the system or chosen-zone radio choice, through the new `App.ui.radioGroup`;
  - an inline zone search, with city-prefix ranking and alias items (Oslo,
    Calcutta) stored as the operator chose them;
  - the browser/server mismatch hint, worded by mode, with a one-click fix;
  - "What agents see", from the server's own preview strings;
  - saving on choice, with module-level generation ordering.
- **The app's clocks follow the operator zone.**
  - `App.time` uses `Intl` with `timeZone`, and hand-built UTC offsets.
  - The zone loads at boot, capped at 2 s.
  - The Chats list, message stamps and note times re-render on change.
- **A static guard** forbids local `Date` getters outside `time.js`.
- **The server provides canonical names** (`links`, `effective.canonical`).
- Merged in PR #265 (`c6bbdc2`). The operator reviewed it on a preview
  instance and found nothing notable.

### Mission Criteria Advanced

These were met and checked in the mission:

- the operator sets the zone once, and it holds;
- the operator sees what agents see;
- a browser/server mismatch is caught;
- the app and its agents agree on the time.

**Evidence:**

- `test_flow_settings_date_time.py` (16 cases);
- `test_flow_chat_time_zone.py`;
- `test_ui_time_contract.py` (Chromium and WebKit);
- the final gate: `rc=0` on all 8 lanes.

## What Went Well

- **Architect cycle 2 read real tzdata and caught the 2026 merged-city aliases**
  (Oslo is now an alias of Berlin, plus 253 `L` lines in all). This was the
  single most valuable review finding: without it, "Oslo" would have found
  nothing, and an Oslo user would have been told they were in Europe/Berlin.
  - Cycle 1 caught that browsers report legacy aliases (`Asia/Calcutta`,
    `UTC`), measured in both engines.
- **The FD's canvas comparison on screenshots worked.** It found the "ko"
  search-ranking defect and the hint-placement deviation, the only UX issues
  of the flight. The crew could not open the canvas, but the FD could.
- **Splitting radioGroup into its own leg** let the leg 2 and leg 3 design
  reviews run in parallel, with leg 2's artifact as leg 3's contract.
- **The apparatus gave deterministic tests:**
  - `timezone_id` through `credentialed_context`;
  - `TZ` through `extra_env`;
  - `set_fixed_time`, never `install()`;
  - zones 25 h apart.

  There were no clock flakes. The one rollover risk was caught at the final
  review.
- **The boot seam:** `Promise.all([config, race(settings, 2 s)])` with a chain
  that never rejects. Both sides are tested, through a held route.
- **The final gate was fully green** (`rc=0`, 1021 s), with no flakes in that
  run.

## What Could Be Improved

### Process
- **The crew cannot open design canvases.**
  - The Developer's AC14 "canvas comparison" was made against DD4's text, which
    is circular, so the real comparison fell to the FD.
  - The canvas boards should be exported as images into the scratch directory
    for the crew.
- **Pinned-count tests were still missed after the "full pinned-list set"
  review:**
  - `test_index_asset_cache_busting.py` (86 → 87 refs);
  - three counts in the Jump to palette's 8-result cap.

  The gate found them.
- **The leg 3 stale-load test recipe was infeasible.** The page shows
  "Loading…" until both of its fetches return. The Developer used scratch-node
  mounts, and case 13 had to be renamed to say honestly what it proves.
- **Search behaviour had no golden queries in DD4.** A plain substring match
  plus grouping by region put North_Dakota above Kolkata for "ko". A
  golden-query table (each query with its expected top result), checked
  against real data, would have caught it at design time.

### Technical
- **The rules-and-notes `onChange` listener accumulates.** Each mount adds one,
  and it is only pruned at the next zone change. The tab has no teardown hook.
- **An alias item never shows the check mark.** With `Europe/Oslo` stored,
  searching "oslo" shows no check on the Oslo item, and the active row falls
  back to the first result. This is minor and untested.
- **The page CSS and JS reach into `searchList` internals:**
  - the listbox `max-height`, the lead, and a selector that hides the active
    row while blurred;
  - the page saves and restores `scrollTop` itself, working around `refresh()`.
- **A page-local `[hidden] { display: none }`** is the fourth instance of an
  author `display` rule defeating `hidden`.
- **`zone_links()` re-parses `tzdata.zi`** separately from `_parse_tzdata_zi()`.
- **The fixed `name="time-zone-mode"` defeats radioGroup's uid default** and
  collided in a test.
- **Search ranking (`tierOf`) is page-local.** The Jump to palette and the
  agent picker use plain substring matching.
- **The static guard misses some local-time APIs:** local-time `new Date(y, m,
  d)`, `getTimezoneOffset`, `set*` mutators and bare `Intl.DateTimeFormat(`.
- **The optional WebKitGTK probe was not run.** The Linux desktop engine's
  zone handling rests on the local fallback.

### Documentation
- Acceptance-criteria checkboxes in completed legs are left unticked: 0 of 35
  here, and the same in Flight 1. This is a convention gap.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| The mismatch hint is above the radio cards (the canvas has it below) | Built that way; the FD accepted it as more visible; flagged at the PR | No; specs should pin DOM order |
| Zone-mode hint wording, "agents are set to …" | The canvas showed only the system case | Yes, as written |
| A failed `/api/time-zones` degrades only the chooser | Better than AC9's "no controls" | Yes |
| Cases 10 and 13 use scratch-node mounts | The page gates on its own load | No; give pages a test seam where races matter |
| Search ranked by tier | The FD found "ko" in the canvas comparison | Yes: prefix-first for every search list |
| The radio description uses `--fg-secondary` | The a11y gate failed `--fg-muted` on the checked composite | Yes: the a11y gate decides |

## Key Learnings

- **Read the real data at design time.** Both high Architect findings came
  from inspecting tzdata and the engines' `Intl` output, not from reading
  code.
- **Visual and UX review needs eyes on the design.** Only the FD could see the
  canvas, and only that comparison found the UX defects.
- **One seam plus a static guard is a durable pattern.** `App.time` and
  `test_time_getters_static.py` make "the app follows your zone" a property
  enforced in CI, not a convention.
- **Test metrics:** the final Flight 2 gate was `rc=0`, 1021 s, unit 5932
  passed / 14 skipped. The debrief re-run on merged `main` gave the same
  counts, 218 s unit and 1055 s browser. Chats came in at 364/360, over budget
  again; see the Flight 1 debrief for the lane table and trends. The new files
  are in contracts (+31 s versus the CLAUDE.md measured column), settings
  (+47 s) and chats (+93 s).

## Methodology Observations

- **Crew agents cannot open claude.ai design canvases.**
  - **What happened:** leg 3's AC14 canvas comparison was assigned to the
    Developer, who could only compare against DD4's text. The FD then compared
    the screenshots with the canvas and found two issues.
  - **Expected:** either the FD owns visual comparison explicitly in the leg,
    or the flight skill exports canvas boards to images that the crew can
    read.
  - **Cost:** two UX defects found only at flight end, and one extra review
    and fix round.
  - **Skill:** flight (verification design) and agentic-workflow (leg
    assignment). Plugin 1.2.0.
- **The pinned-count sweep is unreliable when done by reading.**
  - **What happened:** the design-review prompts asked for "every pinned list".
    Two count sites (asset refs, the palette cap) were still missed and found
    at the gate.
  - **Expected:** a mechanical grep step for numeric pins tied to the changed
    collection.
  - **Cost:** one extra gate run in leg 3.
  - **Skill:** agentic-workflow 2a (leg design risk checks). Plugin 1.2.0.
- **The Reviewer ran browser tests by bare path and deselected all of them.**
  - **What happened:** the flight-end Reviewer passed a browser file path to
    `run-tests.sh` without `-m browser`, so all 16 tests were deselected and
    the browser coverage went unverified in that pass.
  - **Expected:** the crew prompt states that `-m browser` is required for
    paths.
  - **Cost:** one re-review.
  - **Skill:** project crew file `leg-execution.md` (Review prompt). It is a
    local fix, plugin 1.2.0.
- **Running independent legs' reviews in parallel worked** (positive evidence).
  The leg 2 implementation and the leg 3 design review overlapped safely
  because the artifacts were the contract.

## Recommendations

1. **Give the crew canvas images.** Export the design boards to the scratch
   directory at flight start, or assign visual comparison to the FD in the
   leg.
2. **Fix the two shipped nits as squawks:** the notes listener build-up (add an
   owner-scoped `App.time.onChange`, or a Studio tab teardown hook) and the
   missing alias-item check.
3. **Make a small `searchList` contract change in maintenance:**
   `refresh({keepScroll, activeId})`, a `maxHeight` option, and an option to
   show no active row while blurred. Then move prefix-first ranking into a
   shared helper for the Jump to palette and the agent picker too.
4. **Add a global `[hidden] { display: none !important }`** in the base layer.
   This is the fourth instance.
5. **Add `-m browser` to the crew Review prompt**, and widen the static time
   guard's regex.

## Action Items

- [x] Logged as squawks (operator approved, 2026-10-11):
  - **0176** the notes-tab listener build-up;
  - **0177** the alias item's missing check;
  - **0178** a global `[hidden]` reset;
  - **0179** a single tzdata parser;
  - **0180** widen the time-getter guard;
  - **0181** `-m browser` in the Review prompt.
- [ ] Next maintenance pass:
  - the `searchList` options and a shared ranking helper;
  - split `date-time-page.js` and `rules-notes-tab.js`;
  - migrate the theme toggle to `App.ui.radioGroup`;
  - a WebKitGTK probe of `App.time.parts`.
- [ ] Existing squawks 0168 and 0171 (gate flakes) remain open.

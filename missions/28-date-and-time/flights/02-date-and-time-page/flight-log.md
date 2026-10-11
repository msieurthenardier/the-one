# Flight Log: The Date and Time Page

**Flight**: [The Date and Time Page](flight.md)

## Summary

Planned 2026-10-10, while Flight 1's last legs ran. The operator pre-authorized
autonomous execution through to one mission PR, with no per-flight HAT.

---

## Leg Progress

---

## Decisions

---

## Deviations

---

## Anomalies

---

### Flight Director Notes

- **2026-10-11.** Flight 1 was committed at `a9c8da5`. Branch
  `flight/02-date-and-time-page` was created from it, and the flight is in
  flight.
- **Host rule** carried from Flight 1: every browser lane and gate runs with
  `THE_ONE_TEST_NETNS=1`. The known flake is squawk 0168.
- **Leg 1 `time-zone-client-core` is tiered HIGH.** The boot sequence changes,
  so every lane is affected. It is a shared client state module (`App.time`),
  a cache (the formatter) with re-render subscribers, and an additive server
  API change.
- **Leg 2 `radio-group-control` is tiered HIGH.** It is a new shared library
  control with keyboard and a11y semantics, and M27 methodology observation 2
  found UI legs under-tiered.
- **Both design reviews run in parallel** (read-only; the legs share no files
  except `agents.md`, in different sections). Implementation runs
  sequentially, because of host policy and because both need browser runs.
- **Leg 1 design review** (Developer, Sonnet): approve with changes. Applied:
  - (high) the rules-notes listener self-unsubscribes through `isConnected`,
    because the tab has no teardown;
  - (high) the AC8 pin method;
  - the triaged list;
  - the boot test through a captured route, never `wait_settled`;
  - the harness-free contract test;
  - the boot `Promise.all`/`race` shape;
  - a separate `zone_links()` with transitive resolution;
  - a static getter-guard unit test.

  **FD calls:**
  - pin through a server PUT to the browser's zone;
  - offsets implemented by hand (WebKit risk);
  - `zoneFromSettings` prefers `canonical` (documented).

  Status: ready.
- **Leg 2 design review** (Developer, Sonnet): approve with changes. Applied:
  - the demo id `radioGroup` (one call, no testid or name);
  - all options re-synced on every change, with one delegated listener;
  - the strict testid and sink guard rules for `ui/`;
  - firm a11y pairs on the checked composite;
  - no fieldset flexbox, and legend styling;
  - a mandatory forced-colors rule and test;
  - the WebKit Tab positive-control pattern;
  - the edge-case decisions;
  - the inventory row placement.

  **FD calls:** keep `.is-checked` as a `:has()` fallback; expose
  `input(value)` and `focus()`. Status: ready.
- **Leg 3 `date-and-time-page` is drafted.** Its design review follows leg 1,
  when its own as-built inputs exist.
- **Leg 1 landed.**
  - Gate: `PARALLEL_RESULT rc=1 total=982s failed=routing,shared`.
  - Both failures pass in isolation:
    - `shared`: squawk 0168;
    - `routing`: `test_store.py::test_prime_supersedes_a_racing_older_get`, a
      test-timing race now logged as **squawk 0171** (deferred).
  - Accepted as green apart from these known flakes.
  - Developer deviation, accepted: the notes list skips a zone re-render while
    a note is being edited, so the edit is not destroyed.
- **Leg 2 implementation and leg 3 design review are running concurrently.**
  The review is read-only and uses the leg 2 artifact as the radioGroup
  contract.
- **Leg 3 design review** (Developer, Sonnet): approve with changes. Applied:
  - a page-local `viewMode`;
  - the stale-load recipe, avoiding the boot GET;
  - the `div.date-time-page` root as the mounted check, with no activate hook;
  - the exact `scrollTop`/`setActive` sequence;
  - alias item ids;
  - a fresh SVG lead node;
  - the full pinned-list set;
  - no label copies in admin or router;
  - the README edits rescoped, since there is no tool list;
  - the registry format;
  - four more flow cases.

  **FD calls:**
  - zone-mode hint wording: "agents are set to …";
  - an alias pick stores the alias;
  - leaving Settings cancels nothing, and only the latest response updates
    `App.time`;
  - the query is kept after a pick.

  Status: ready.
- **Leg 2 landed.**
  - Contracts lane: 713 passed, 4 skipped, in 211 of 270 s. Unit: 5930
    passed, 14 skipped.
  - The description uses `--fg-secondary`, because `--fg-muted` failed 4.5:1
    on the dark checked composite.
  - The WebKit Tab and focus-visible differences are handled in the tests.
  - The FD stopped the agent's leftover background task; no stray processes
    remain.
- **Leg 3 implementation started.**
- **Leg 3 landed.**
  - Gate: unit 5932 passed, 14 skipped. `PARALLEL_RESULT rc=1 total=1084s
    failed=shared`. The only failure was squawk 0168, which passes in
    isolation.
  - Chats lane at 394/360, over budget. It runs none of this leg's files and
    measured 326 earlier, so it is noted as load variance and not re-budgeted.
  - The FD stopped the agent's leftover background task.
- **FD canvas comparison** (the FD can open the canvas; the Developer could
  not), using the leg's scratch screenshots `dark-mismatch.png` and
  `light-chosen.png`:
  - **Layout, copy, radio cards, preview and alias items match boards 1 and
    2.**
  - **Deviation, accepted:** the mismatch hint sits *above* the radio cards
    (the canvas has it below the options). It is more prominent; noted for the
    operator's PR review.
  - **Defect:** a search for "ko" lists `America/North_Dakota/*` before
    `Asia/Kolkata`, because results group by region and "Dakota" contains
    "ko". Kolkata falls below the visible list. It is handed to the flight-end
    Reviewer to confirm, and fixed in the review fix round by ranking prefix
    matches first.
- **Flight-end Reviewer: Sonnet tier.** The diff is UI plus a library
  control. It is not credential, sandbox or identity work, but the boot
  sequence and a shared control make it security-adjacent enough to warrant
  Sonnet over Haiku.

## Session Notes

### 2026-10-10: Flight design

- Two Architect cycles (Opus). Both returned **approve with changes**, and
  every finding was applied.
- **Cycle 1:**
  - (high) Browsers report legacy aliases (`Asia/Calcutta`, `UTC`), so DD6
    adds `links`, `effective.canonical` and canonical comparisons.
  - The radio card structure, defined so the zone rows never join the radio's
    accessible name.
  - Patch-in-place, generations, and `setActive`.
  - The boot fetch bounded at 2 seconds, with an `r.ok` check.
  - An unnamed zone uses the server offset.
  - The pinned time-label tests and Settings lists.
  - `renderPage` exported.
  - `TZ` pinning and `set_fixed_time`.
  - Leg 2 split into a radio-group leg and a page leg.
- **Cycle 2:**
  - (high) tzdata 2026 merges cities into aliases (Oslo → Berlin, and others).
    **FD decision:** search also finds alias names and shows them as their own
    items ("same clock as …"). A pick, or "Use {browser}", stores the name the
    operator chose. Comparisons stay canonical, and the "Selected" line shows
    the stored name.
  - DD6's server part moved into leg 1.
  - `zoneFromSettings`, used on save and at boot.
  - The generation counter is module-level, and a failed PUT re-GETs.
  - An exact CSS selector for the suppressed active row.
  - Testid placement and leg naming.
  - The settings lane re-budget allowed.
- Status: ready. It executes after Flight 1 lands and commits, on a branch from
  `flight/01-agents-know-the-time`.

### 2026-10-10: Leg 1 (time-zone-client-core): landed

**Status:** landed (not committed). Started and finished 2026-10-10.

**Changes made**

- Server (DD6): `time_zones.zone_links()` (own cache, transitive, every value
  canonical), `canonical_name()`, `zone_rows` also drops the no-slash canonical
  names. `GET /api/time-zones` gains `links`; `effective.canonical` added to
  `GET`/`PUT /api/time-settings`. Tests added in `tests/test_time_zones.py` and
  `tests/test_time_settings_api.py` (stored alias, canonical, unnamed system,
  system-as-alias).
- `static/js/time.js` rewritten: `setZone`, `zone`, `parts`, `formatClock`,
  `dayNumber`, `onChange`, `zoneFromSettings` (offset keys hand-built, no Intl).
- Boot (`app.js`): the settings chain is inline (documented in agents.md),
  `Promise.all([configChain, Promise.race([settingsChain, 2s timer])])`, timer
  cleared when settings win, `r.ok` plus own catch.
- Callers converted: `chats-list.js` (`startOfDay` deleted; `bucketFor`/`timeFor`
  signatures kept), `message-bubble.js` (`data-ts`), `rules-notes-tab.js`
  (`formatWhen`; the notes section self-unsubscribes when its list is
  disconnected); `chat.js` subscribes once and re-renders the list and re-labels
  stamps in place. A comment in `chats-list.js` that mentioned `toLocaleString`
  was reworded so the static guard passes.
- New `tests/test_time_getters_static.py` (unit tier) enforces the sweep.
- New `tests/browser/test_ui_time_contract.py` (18 tests, both engines) and
  `tests/browser/test_flow_chat_time_zone.py` (list, attribution, notes label,
  tab-switch single render, held-fetch boot bound).
- Docs: agents.md "`App.time` (M28 F2)" plus links/canonical in the Time zones
  section; one sentence in the CLAUDE.md M28 paragraph.

**AC7 sweep result:** `grep -rnE "getHours|getMinutes|getDay\(\)|getDate\(\)|getMonth\(\)|getFullYear\(\)|toLocale"`
over `static/js` now hits only `time.js`. The one non-time.js hit was a comment
in `chats-list.js` (reworded). The remaining `getTime()` uses (sorting in
`chats-list.js`, elapsed time in `self-configuration-tab.js`, validity checks)
are zone-independent. Knowledge `Indexed:` raw stamps intentionally untouched.

**AC8 pin list**

- `test_flow_chat_list.py`: an autouse fixture PUTs `/api/time-settings` to the
  browser's own resolved zone for every test using `app_with_agent`;
  `test_clock_formatter_edges` uses `goto_settled` then `App.time.setZone(null)`
  inside the evaluate. Reason: without a pin these pass only while the host
  `tzlocal` name equals Chromium's zone.
- Triaged zone-independent, no pin: `test_flow_chat_peer_attribution.py`
  (shape-only regex), `test_flow_new_chat.py` ("Today" for a just-created
  session), `test_ui_list_pane_chats_contract.py` (literal labels). No other
  browser test asserts notes timestamps.

**Verification**

- `make test-unit` (netns): 5924 passed, 14 skipped.
- ruff check and format clean; the static guards run inside the unit tier.
- Lane membership: `test_ui_time_contract.py` is in contracts,
  `test_flow_chat_time_zone.py` in chats.
- Browser files run singly: contract 18 passed; chat time zone 2 passed;
  `test_flow_chat_list.py` 10 passed.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 ... make gate`:

| lane | rc | wall (s) | budget (s) |
|---|---|---|---|
| routing | 1 | 490 | 600 |
| settings | 0 | 440 | 540 |
| agents | 0 | 488 | 510 |
| chats | 0 | 318 | 360 |
| mcp | 0 | 294 | 360 |
| library | 0 | 238 | 300 |
| shared | 1 | 248 | 300 |
| contracts | 0 | 224 | 270 |

  `PARALLEL_RESULT rc=1 total=982s lanes=8 failed=routing,shared`
- The two failures, both re-run in isolation and passing:
  - `shared`: `test_flow_jump_to.py::test_new_chat_opens_the_agent_picker`
    (the known flake, squawk 0168).
  - `routing`: `test_store.py::test_prime_supersedes_a_racing_older_get`
    (`assert len(held) == 1` saw 0: the test's `page.wait_for_function("() => true")`
    does not wait for the route handler to run, so it is timing-sensitive under
    3-lane load). Passed in isolation and in 3 further whole-file runs (21
    passed each). Unrelated to this leg's change; worth a squawk.

**Decisions and deviations:** none from the leg. Notes-list re-render is
skipped while a note is being edited (`editingId`), to avoid destroying the
edit field; the label updates on the next render.

### 2026-10-10: Leg 2 (radio-group-control): landed

**Status:** landed (not committed). Started and finished 2026-10-10.

**Changes made**

- `static/js/ui/choice.js`: `App.ui.radioGroup` (fieldset, legend, per-option
  card of label+radio / optional description / slot; one delegated `change`
  listener; `setValue` silent; all wrappers re-synced for `.is-checked`).
- `components.css`: `.ui-radio-*` block next to the toggle rules, plus a
  forced-colors addition (checked card `Highlight` 2px border, disabled
  `GrayText`).
- Design language demo: one `d.demo(host, 'radioGroup', ...)` in
  `ui-choices-section.js` (two described options, a slot child, no testid or name).
- `docs/ui-control-inventory.md`: new row (status `library: App.ui.radioGroup`);
  the theme row keeps `not yet defined` with the migration note.
- `the_one/agents.md`: a "Radio group (M28 F2 L2, DD3)" bullet.
- `tests/browser/test_ui_radio_group_contract.py` (new, 12 tests x 2 engines,
  contracts lane) and three new pairs in `tests/test_design_tokens_a11y.py`.

**Description colour (a11y gate):** `--fg-muted` FAILED 4.5:1 on the dark
checked-card composite (`--accent-translucent` over `--surface`), so the
description uses `--fg-secondary`. Gate pairs added: `--fg` and
`--fg-secondary` on the checked composite, `--fg-secondary` on `--surface`,
both themes, all pass.

**Verification**

- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 ... --lane contracts`: 713
  passed, 4 skipped, wall **211 s** against the 270 s budget. After a
  formatter-only change the radio file re-ran: 23 passed, 1 skipped (the
  forced-colors test is skipped in WebKit by design).
- `make test-unit` (netns): 5930 passed, 14 skipped. Static guards
  (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`,
  `test_ui_control_inventory`, `test_ui_library_source`) pass; ruff clean.
- `test_ui_reference_page.py` runs inside contracts (5 passed).

**Decisions and anomalies**

- Description colour moved to `--fg-secondary` (above), as the leg allowed.
- WebKit anomaly: Tab skips radios there, and `:focus-visible` is not reported
  for a script-reached radio after an arrow key. The keyboard test falls back to
  `group.focus()`; the focus-ring test asserts the shipped
  `.ui-radio-input:focus-visible` rule (2px solid) in WebKit and the computed
  outline (>= 2px) in Chromium.
- `test_ui_listener_cleanup.py` needed no change.

### 2026-10-10: Leg 3 (date-and-time-page): landed

**Status:** landed (not committed). Started and finished 2026-10-10.

**Changes made**

- Routing: `date-and-time` row second under General in `settings-pages.js` and `router.js` `SECTIONS`; `admin.js` `GENERAL_SUBS` and `GENERAL_RENDERERS` (`renderDateTimePage`); `system-page.js` exports `App.admin.renderPage`; `index.html` loads `areas/admin/date-time-page.js` after `system-page.js`.
- `areas/admin/date-time-page.js` (new, DOM APIs only): the radio group, the inline searchable zone chooser with alias items, the mismatch hint and one-step fix, the "What agents see" preview and note, the status and error lines. Nodes are built once after the first load and patched in place; a module-level `GEN` counter orders every PUT and load; a failed PUT shows the server `detail` and re-GETs; `App.time.setZone` is called last on the latest response (a torn-down page's latest response touches only `App.time`).
- `admin.css`: page styles scoped `.area-admin .date-time-page` (listbox max-height 252px, mono descriptions, fixed-width lead, the unfocused-active-row suppression with a forced-colors twin, status/preview styles, and a last `[hidden]` rule so no display rule can show a hidden node).
- `docs/ui-testid-registry.md`: the 13 DD4 testids.
- Pinned lists: `DD2_ROWS`, `_nav.py` (`legacy_hash` and docstring), `test_router_core.py` (two lists), `test_settings_pages_static.py` ("eight"), `test_flow_admin_settings_nav.py`, `test_flow_keyboard.py`, `test_flow_jump_to.py` (`SETTINGS_PAGES`, plus three count assertions: the palette caps at 8, so "settings" now matches 8 (7 without dev mode) and the empty-install list is New chat plus the first seven pages), `_lists.py`, `test_index_asset_cache_busting.py` (86 -> 87 refs), and the step text of `shell-navigation-smoke.md`, `workbench-navigation.md`, `list-and-detail.md`.
- `tests/browser/test_flow_settings_date_time.py` (new, settings lane, 16 tests covering the 16 leg cases).
- Docs: CLAUDE.md (router hash list, Settings nav paragraph, a "Date and time page" paragraph), `agents.md` ("Settings nav and pages" sub list, new "Date and time page (M28 F2 L3)" section), README (Settings paragraph, one sentence in Agents).

**Verification**

- Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_settings_pages_static`, `test_nav_helper`) pass; ruff check and format clean.
- `test_flow_settings_date_time.py`: 16 passed; `test_flow_jump_to.py`: 24 passed.
- Final `make gate` (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`): `make test-unit` 5932 passed, 14 skipped.

| lane | rc | wall (s) | budget (s) |
|---|---|---|---|
| routing | 0 | 495 | 600 |
| settings | 0 | 484 | 540 |
| agents | 0 | 494 | 510 |
| chats | 0 | 394 | 360 (OVER) |
| mcp | 0 | 358 | 360 |
| library | 0 | 286 | 300 |
| shared | 1 | 255 | 300 |
| contracts | 0 | 232 | 270 |

  `PARALLEL_RESULT rc=1 total=1084s lanes=8 failed=shared`
- The one failure is `test_flow_jump_to.py::test_new_chat_opens_the_agent_picker` (the known flake, squawk 0168); it passed in isolation. The `chats` lane's OVER BUDGET warning (394 s, no file of this leg is in it) is load variance (the earlier run in this leg measured 326 s); no re-budget.
- **Settings lane budget:** measured 484-495 s (two gate runs) against 540 s: within budget, no re-budget or split.
- Earlier gate run in this leg failed on the cache-busting count (87 refs) and on two jump-to counts and one preview-timestamp assertion of the new test; all fixed above, then the gate re-run.

**AC14 canvas comparison** (headless Chromium 1280x1000, scratch instance on 8493 with a scratch data dir and `TZ=America/Chicago`, stopped with `make down`; screenshots in the scratchpad, not the repo)

- Dark mismatch (browser Pacific/Kiritimati): intro line, "TIME ZONE" eyebrow, the accent-bar info banner with the browser name in bold, the offset, the effective zone in bold, the WSL sentence and a small "Use Pacific/Kiritimati" button at the right; two hairline option cards, the system card selected (accent border and wash) with the mono-less description line; "WHAT AGENTS SEE" with the code chip, the prompt, the clock line and the note. No visible deviation from DD4. The blank band between the cards and the second section title is the empty status line (20px reserved) plus the section margin.
- Light chosen (Asia/Kolkata stored, query "ko"): the zone card is selected with the translucent accent wash, "Selected: **Kolkata** Asia/Kolkata · UTC+05:30" above the search, the focused search ring, region caption, rows with a fixed-width blank lead, city over a mono zone line and a right-aligned mono `UTC-05:00 · CDT` meta, the first row shown active while the input has focus, and an alias item ("Atikokan ... same clock as America/Panama") with an offset-only meta. No visible deviation found.
- I could not open the canvas, so the comparison is against DD4's text.

**Decisions and anomalies**

- Stale-load test (case 10) and view-mode test (case 13): the page shows "Loading..." until both fetches return, so a pick cannot be made while the page's own load GET is held. Both cases instead mount a second instance into a scratch node (`App.admin.renderDateTimePage`), which takes an older (case 10) or the latest (case 13, torn down before the answer) generation, and assert on `App.time.zone()` and the visible page. Two instances in one document share the radio `name`, so case 13 removes the scratch node before releasing its answer.
- The preview tool line and clock carry the current second and minute, so test 1 compares them modulo that field.
- Hint, list, muted line and slot use the `hidden` attribute; page CSS ends with `.area-admin .date-time-page [hidden] { display: none; }` because the page's own `display` rules otherwise showed hidden nodes.
- The search list's active row follows the stored zone only when it is among the (filtered) results; otherwise the first result is active.

## Review fix round 1

- Zone search (`date-time-page.js`): replaced the plain path-substring match with `tierOf` (city prefix = tier 1; path segment/tail prefix, city word prefix, offset text with or without `UTC` (only for queries starting with a sign, digit or `utc`), abbreviation prefix = tier 2; mid-word path substrings no longer match). `source()` buckets by region and tier, lists tier-1 before tier-2 within a region, and orders regions by best tier then server order. Alias items use the same rules on their own city/path. Blank query unchanged.
- "Use the system time zone" option no longer passes the `description: ' '` placeholder; `radio.setDescription('system', ...)` creates and wires the element.
- `tests/test_time_zones.py` already pinned the slash-less exclusions and Etc/UTC; no change.
- Tests added in `test_flow_settings_date_time.py::test_search_and_pick`: "ko" (Kolkata first, no North_Dakota), "salem", "argentina", "ist", "+05:30".
- Results: static guards 332 passed/1 skipped; date-time browser file 16 passed; settings lane 224 passed; ruff check/format clean.

## Review fix round 2 (nits)

- `test_system_load_describes_the_detected_zone`: the tool line's time digits are now matched by shape (full `HH:MM:SS`), with the `(America/Chicago)` suffix asserted exactly, so a minute rollover between page load and the later `GET /api/time-settings` cannot flake it.
- Case 13 renamed `test_an_unmounted_instances_late_answer_leaves_the_visible_page`; its comment now states what it proves (an unmounted instance's late answer does not touch the visible page). No extra assertion added: viewMode is instance-local and no honest seam exists to re-render the single visible instance.

## Flight close

- Re-review confirmed ([HANDOFF:confirmed]); the round 2 nits were fixed.
- Final gate green: unit 5932 passed / 14 skipped (netns); `PARALLEL_RESULT rc=0 total=1021s lanes=8 failed=-` (routing 485/600, settings 476/540, agents 486/510, chats 308/360, mcp 286/360, library 235/300, shared 247/300, contracts 250/270).
- Committed in the flight/2 commit.

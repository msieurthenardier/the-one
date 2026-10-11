# Leg: date-and-time-page

**Status**: completed
**Flight**: [The Date and Time Page](../flight.md)

## Objective

Build Settings › General › Date and time (`#settings/date-and-time`) from the
approved canvas.

- **The choice:** a system / chosen-zone radio group (`App.ui.radioGroup`).
- **The zone chooser:** inline and searchable (`App.ui.searchList`), with alias
  items.
- **The mismatch hint**, with its one-step fix.
- **"What agents see"**, from the server's own preview strings.
- **The note** on when a change applies.
- **Saving:** on choice, with generation-safe ordering.

Then update every pinned Settings list, the docs (README included) and the
full gate.

## Context

- Read [flight.md](../flight.md) **DD2** (routing and placement), **DD4**
  (layout, behaviour, saving, hint, preview, testids, alias search) and
  **DD6** (the canonical names that leg 1 shipped). DD4 is the contract. This
  leg implements it as written, and any deviation goes in the flight log.
- **The canvas:** [Date and time settings](https://claude.ai/artifact/A89sjcpKfxd9j1BedBvkYx).
  Board 1 shows the dark mismatch case and board 2 the light chosen case.
- **Built on legs 1 and 2** (uncommitted on this branch; see the flight log
  for the as-built names):
  - `App.time.setZone` / `zoneFromSettings` / `onChange`;
  - `/api/time-zones` with `links`;
  - `effective.canonical`;
  - `App.ui.radioGroup`, with `optionEl` / `setValue` / `setDescription`.
- **Flight 1 leg 2b added the Prompts Date layer to `system-page.js`.**
  `renderPage` (`system-page.js:21`) is private; export it as
  `App.admin.renderPage`.
- **Host rule:** `THE_ONE_TEST_NETNS=1` for every browser run. The known flake
  is squawk 0168.

## Inputs

- `static/js/settings-pages.js` (the `PAGES` table), `static/js/router.js`
  `SECTIONS` (~81-96).
- `static/js/areas/admin.js`: `GENERAL_SUBS` (~11), `GENERAL_RENDERERS`
  (~326-330), the `validIds` and `hydrateState` paths.
- `static/js/areas/admin/system-page.js`: `renderPage`, plus the exports at
  the bottom.
- `static/index.html`: the script tags for `areas/admin/*.js`.
- `static/js/ui/search-list.js`: `refresh()`, `setActive(id)`,
  `getActive()`; `aria-selected` only on the active row (~220-296).
- Leg 1's `App.time` and leg 2's `App.ui.radioGroup`.

## Outputs

- **`static/js/settings-pages.js` and `router.js`:** the `date-and-time` row,
  after Appearance, in both tables.
- **`static/js/areas/admin.js`:** `GENERAL_SUBS` and `GENERAL_RENDERERS`
  (`renderDateTimePage`).
- **`static/js/areas/admin/system-page.js`:** export `App.admin.renderPage`.
- **`static/js/areas/admin/date-time-page.js`** (new, DOM APIs only):
  `App.admin.renderDateTimePage(container)`. Its module-level generation
  counter is shared across mounts.
- **`static/index.html`:** the script tag, after `system-page.js`.
- **`static/css/admin.css`:** page styles, scoped `.area-admin .date-time-page`:
  - the listbox `max-height` (about 252px);
  - mono descriptions;
  - the selector that suppresses the active-row style, plus its
    `forced-colors` twin;
  - the lead width.
- **`docs/ui-testid-registry.md`:** every DD4 testid, sorted by id, as
  `| id | admin | description |`. `test_ui_guards` diffs the JS testids
  against the registry both ways: `rowTestid`/`inputTestid` passed to
  `searchList` count, and so do the `radioGroup` testids.
- **Pinned lists updated** (the full set, from the design review):
  - `tests/test_nav_helper.py` `DD2_ROWS` (~47) gains
    `("settings/date-and-time", "#admin/date-and-time")`;
  - `tests/browser/_nav.py`: `legacy_hash` (~210) adds the section to its
    General tuple, and its docstring (~37) is updated;
  - `tests/browser/test_router_core.py` (~106 and ~378): the settings route
    lists gain it;
  - `tests/test_settings_pages_static.py`: its "seven" name and docstring
    become eight;
  - the behavior-spec step text in `shell-navigation-smoke.md:~39`,
    `list-and-detail.md:~19,~114` and `workbench-navigation.md:~45`;
  - `tests/test_settings_pages_static.py` (~46-54, and the router equality
    ~73-78);
  - `tests/browser/test_flow_admin_settings_nav.py` (`GROUPS` ~46);
  - `tests/browser/test_flow_keyboard.py` (`_SETTINGS_NAV_ORDER` ~198-206);
  - `tests/browser/test_flow_jump_to.py` (`SETTINGS_PAGES` ~49);
  - `tests/browser/_lists.py` (`SETTINGS_PAGE_TITLES` ~243-251);
  - `tests/browser/_nav.py` (~210, the legacy mapping, if it enumerates
    sections);
  - the behavior specs `workbench-navigation.md` and
    `shell-navigation-smoke.md`, if they enumerate Settings pages (update
    their step text only).
- **`tests/browser/test_flow_settings_date_time.py`** (new, settings lane).
- **`scripts/run-tests.sh`:** the budget table, only if the measured settings
  lane exceeds 540 s. Re-budget it to the measured value rounded up, or split
  the new file into its own lane. `tests/test_run_tests_lanes.py` passes.
  Record which.
- **Docs:**
  - CLAUDE.md: the router hash list gains `date-and-time` in the
    `#settings/{…}` list, and the "Settings nav and pages" paragraph gains
    "Date and time" under General;
  - `agents.md`: "Settings nav and pages", plus a "Date and time page" contract
    paragraph;
  - **`README.md`** has no tool-name list (design review). Instead:
    - the Settings paragraph (~94, which lists Appearance, Prompts and
      Encryption) gains "Date and time picks the time zone agents and the app
      use";
    - one plain sentence in the Chats or Agents text says that agents know
      today's date and can check the time.

    Keep README's voice: plain sentences, no internal names.
- **The flight log:** the leg entry, plus a canvas-versus-built comparison
  note.

## Acceptance Criteria

**Routing and nav**

- [ ] **AC1.** `#settings/date-and-time` opens the page:
  - the Settings nav shows "Date and time" second under General, with
    `aria-current` set when it is open;
  - the router announces "Date and time";
  - Jump to lists "Date and time" under "Settings · General";
  - a deep link and Back/Forward work;
  - `tests/test_settings_pages_static.py` passes.
- [ ] **AC2.** The page renders through `App.admin.renderPage(container, 'Date
      and time', null, [root])`: one `h1`, the page header, `.admin-form`.
  - **The root.** `root` is a single `div.date-time-page` holding every
    section (`renderPage` takes no class parameter). It is the mounted check:
    `root.isConnected`. `renderContent` and `renderPage` clear the container
    with `textContent = ''`, so no teardown hook is needed.
  - **No `activate` hook.** `activate` runs `_refresh` and then
    `renderContent`, so every Settings re-entry re-mounts and re-fetches,
    which is the DD4 loading rule.
  - **Leaving Settings** leaves the page attached but hidden. A late response
    then patches hidden DOM, which is harmless, and only the latest response
    touches `App.time` (FD decision: no cancellation).
  - **No label copies.** The label "Date and time" appears only in
    `settings-pages.js` and `date-time-page.js`, never in `admin.js` or
    `router.js`, which
    `test_settings_pages_static.py::test_admin_and_router_hold_no_copy_of_the_labels`
    enforces.

**Layout and behaviour (DD4, each clause)**

- [ ] **AC3. The radio group and descriptions.**
  - The intro line, then the "Time zone" `.section-title`, then
    `App.ui.radioGroup` with legend "Time zone" (hidden), name
    `time-zone-mode`, and testids `date-time-mode` (fieldset),
    `date-time-mode-system` and `date-time-mode-zone` (the inputs).
  - The system option's description reads "Detected on the machine running
    the-one: {system.zone or 'no zone name detected'} · {system.offset}".
  - The zone option's description reads "For a server, WSL or a container whose
    clock zone is not yours."
- [ ] **AC4. The chooser,** in the zone option's slot, shown only while that
      radio is checked:
  - **The chosen line** (`date-time-chosen`): "Selected: {city of the stored
    name} {stored zone} · {offset}" (offset from the canonical row), or "Pick
    a zone below. Nothing changes until you do." It is wired to the search
    input by `aria-describedby`.
  - **The search list:**
    - label "Search time zones", the DD4 placeholder, input testid
      `date-time-search`;
    - rows with testid `date-time-zone-row` and `data-zone`;
    - groups by region;
    - item label city, description zone, meta `{offset} · {abbr}`, with the
      abbreviation dropped when numeric;
    - a fixed-width lead on every row: a **fresh node per row**, either
      `App.ui.util.icon('check')` (an SVG node) on the stored zone's canonical
      row or an empty spacer `span`. Never `App.icons.check`, an HTML string,
      which would need a sink;
    - item ids: canonical rows use the zone name, alias items
      `alias:<name>`, so `setActive` (first id match) can't collide;
    - the empty text "No time zones match “{query}”.".
  - **Search** matches city, zone, offset (with or without `UTC`, `−` and `-`
    alike) and abbreviation, case-insensitive, with `_` and space alike.
  - **Alias items** appear only for a non-blank query: an alias whose own text
    matches and whose canonical row doesn't, labelled with its city, described
    "{alias} · same clock as {canonical}", with the canonical row's offset.
- [ ] **AC5. View mode versus saved mode.** The page keeps a local `viewMode`
      (which radio is checked, and whether the chooser shows), separate from
      `state.settings.mode`.
  - `viewMode` is set on the user's radio choice. It is re-seeded from the
    server's mode only on page load and on a PUT's success or failure, never
    by an unrelated response.
  - So "Choose a time zone" with nothing stored shows the chooser, even though
    the server still says `system`, and it stays shown.
- [ ] **AC5b. Saving.**
  - **Picking "Use the system time zone"** PUTs `{mode: 'system', zone:
    <stored zone or null>}`.
  - **Picking "Choose a time zone"** PUTs nothing when no zone is stored; when
    one is, it PUTs `{mode: 'zone', zone}` at once.
  - **Picking a row or an alias item** PUTs `{mode: 'zone', zone: <its
    name>}`.
  - **Each request and page load** takes a module-level generation, and only
    the latest response is applied. A torn-down page's latest response
    updates only `App.time`.
  - **A successful response** patches in place:
    - `viewMode = r.mode`, then `radioGroup.setValue(viewMode)`;
    - the descriptions, the chosen line, the preview and the hint.

    It refreshes the search list as `var top = listbox.scrollTop;
    list.refresh(); listbox.scrollTop = top; list.setActive(<stored
    canonical row id>)`, because `refresh()` resets `scrollTop` and activates
    the first option (`search-list.js:~178-224`). Then it calls
    `App.time.setZone(App.time.zoneFromSettings(r))`, last, so the page's
    latest response wins over a late boot fetch. The search query is kept
    after a pick (FD decision). The status line
    (`date-time-status`, `role=status`, `aria-live=polite`) reads "Saved.
    Agents now use {stored zone | 'the system time zone'}.". Focus never
    moves.
  - **A failed PUT** shows the server `detail` in `date-time-error`, then
    re-GETs `/api/time-settings` under a new generation to restore the
    controls.
  - The page registers no dirty source and has no Save button.
- [ ] **AC6. The active row.**
  - `setActive(stored canonical)` runs on load, after each refresh, and after
    the slot is revealed.
  - While the search list isn't `:focus-within`, the active row shows no
    accent (the DD4 selector, plus its forced-colors twin).
  - Enter with a blank query re-saves the stored zone, which is acceptable.
- [ ] **AC7. The mismatch hint** (`date-time-mismatch`, `role=note`,
      `.banner banner-info`):
  - **When it shows:** `canonical(browser)` differs from
    `effective.canonical`, or `effective.canonical` is null and the browser's
    zone is known.
  - **Its text** names the browser's reported name, followed by "(same clock
    as {canonical})" when they differ, and the offset from the canonical row
    (omitted if not listed). The rest is worded by mode (FD decision; the
    canvas shows only the system case):
    - **system mode:** "…, but the machine running the-one reports
      **{effective label}**. That happens under WSL, in a container or on
      another machine.";
    - **zone mode:** "…, but agents are set to **{effective label}**.".
  - **The button** (`date-time-use-browser`) reads "Use {browser}", is shown
    only when the name is in the zone list or `links`, and PUTs the reported
    name.
  - The hint hides once the zones agree.
- [ ] **AC8. "What agents see"** (`.section-title`):
  - `date-time-preview-tool` is `preview.tool`'s first line, in a code chip.
  - `date-time-preview-prompt` is `preview.prompt`, or `prompt_without_tool`
    when `tool_enabled` is false. In that case it is followed by "The time
    tool is turned off in Built-in tools.".
  - `date-time-preview-clock` is `preview.clock` plus "in the Chats list and
    on messages".
  - Then the DD4 note text.
  - All server text is set with `textContent`.
- [ ] **AC9.** Loading shows "Loading…". A failed load shows an error line and
      no controls. Both fetches (`/api/time-settings` and `/api/time-zones`)
      run on every page entry.

**Tests**

- [ ] **AC10.** `tests/browser/test_flow_settings_date_time.py` (settings
      lane; every test uses `_nav`, `_lists` and the credential helpers).
      `credentialed_context(timezone_id=…)` sets the browser zone. The app is
      spawned with `extra_env={"TZ": …}` where a test needs a pinned system
      zone. The cases:
  1. **System load.** The server `TZ=America/Chicago` and the browser on
     America/Chicago: system checked, its description names America/Chicago,
     no hint, the preview strings equal `GET /api/time-settings`.
  2. **Search and pick.** "kolk" finds Kolkata, "Europe/" lists only Europe,
     "+05:30" finds Kolkata. Picking it shows the status line, the chosen line
     reads "Selected: Kolkata Asia/Kolkata · UTC+05:30", `GET` shows it, and
     the preview names Asia/Kolkata.
  3. **"Choose" with nothing stored** issues no PUT: assert through
     `page.route` request counting, or a GET showing it unchanged.
  4. **Back to system** keeps the stored zone. A later "Choose" restores it
     and PUTs once.
  5. **Mismatch.** The browser on Pacific/Kiritimati and the server on
     America/Chicago: the hint names Pacific/Kiritimati. "Use
     Pacific/Kiritimati" leaves `GET` on the zone, the hint gone and the
     status shown.
  6. **Kolkata alias.** The browser on `Asia/Kolkata` (Chromium reports
     `Asia/Calcutta`) and the server on Asia/Kolkata: no hint.
  7. **Oslo merged zone.** The browser on `Europe/Oslo` and the server on
     Europe/Berlin: no hint. Searching "Oslo" shows an "Oslo · same clock as
     Europe/Berlin" item, and picking it stores `Europe/Oslo`, with the chosen
     line "Selected: Oslo Europe/Oslo · …".
  8. **Tool turned off:** `seed_tool_config("current_time", enabled=False)`
     leads to the without-tool wording and the muted line.
  9. **422 path:** `page.route` injects a bogus `Mars/Olympus_Mons` row into
     `/api/time-zones`. Picking it shows `date-time-error` with the server
     sentence, then the controls restore and `GET` is unchanged.
  10. **Stale load.** The boot also GETs `/api/time-settings` (`app.js:~205`),
      so first land on another Settings page (Appearance) and let it settle.
      Then install a `page.route` that **captures** the next
      `/api/time-settings` GET without continuing it, and navigate to Date and
      time. Use plain `goto` or the nav link plus `expect`, never
      `wait_settled`. Pick a zone (its PUT goes through), then
      `route.continue_()` the held GET. The page shows the picked zone, and
      `GET` agrees.
  11. **The app's clocks follow** without a reload: after picking a far zone, a
      seeded chat row's time label in the Chats list changes (navigate through
      the rail, no reload).
  12. **Keyboard.** Choose zone mode first (the search is hidden otherwise).
      Tab reaches the radio group, then the search. ArrowDown plus Enter in the
      search picks a row. Focus stays in the search input after the save.
  13. **View mode holds.** "Choose a time zone" with nothing stored shows the
      chooser, and it stays shown across a later unrelated response (for
      example a held page-load GET released afterwards) while the server is
      still `system`.
  14. **Zone list fails.** A `page.route` fulfils `/api/time-zones` with 500.
      The radio group and the preview render, and the chooser shows an error
      line.
  15. **Fast double pick.** Two picks with the first PUT's response held (a
      captured route): the second pick's state wins.
  16. **Zone-mode hint wording.** The browser on Asia/Tokyo and a chosen
      Asia/Kolkata: the hint reads "agents are set to Asia/Kolkata".
  - **Spawning for TZ pins:** `_spawn_app(tmp_path, extra_env={"TZ": …})`
    with try/finally terminate, plus `credentialed_context(browser, base,
    timezone_id=…)`, following `test_flow_context_overlay_thresholds.py:~138`
    and leg 1's `test_flow_chat_time_zone.py`. Case 1 needs this too, because
    the default `page` zone is the host's. `seed_tool_config` is at
    `seeders.py:~140`.
- [ ] **AC11. The pinned lists** are updated and pass: the static table test,
      the settings nav, keyboard order, Jump to, `_lists`, and `_nav` if
      needed. `tests/test_nav_helper.py` (no raw hashes, no retired selectors)
      passes.
- [ ] **AC12. Gate.** The static guards and `make test-unit` are green. Then
      `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 make gate`
      is green, apart from squawk 0168 if it recurs.
  - The flight log records the lane table and the `PARALLEL_RESULT` line.
  - The settings lane's measured time is checked against its budget, and any
    re-budget or split is applied and recorded.
  - Any other single failure is re-run in isolation, and the re-run is
    recorded.
- [ ] **AC13. Docs.** CLAUDE.md, `agents.md`, `docs/ui-testid-registry.md`
      and `README.md`, as listed in Outputs.
- [ ] **AC14. Canvas comparison.**
  - Start a scratch dev instance on a port of 8490 or higher with a scratch
    data dir, never 8484 or 8485.
  - Open the page in the mismatch state (dark theme) and the chosen state
    (light theme), and take headless screenshots to the scratch directory, not
    the repo.
  - Record any visible deviation from the canvas boards in the flight log.
  - Stop the instance by PID.

## Verification Steps

- **AC1, AC11:**
  `… bash scripts/run-tests.sh tests/test_settings_pages_static.py tests/test_nav_helper.py -x --timeout 60`,
  then the browser files for the nav, keyboard and Jump to.
- **AC2-AC10:**
  `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=1500 bash scripts/run-tests.sh tests/browser/test_flow_settings_date_time.py -x`.
- **AC12:** the gate command, run in the background; wait for it.
- **AC13, AC14:** the diffs and the flight log.

## Implementation Guidance

1. **Routing rows, the `renderPage` export and the admin wiring first.** Then
   check the empty page routes.
2. **`date-time-page.js`:**
   - Build all nodes once: the radio group, its descriptions, the slot
     contents (the chosen line plus the search list), the hint, the preview
     and the status/error lines.
   - Keep `state = {settings, zones, links}`, and `patch()` from `state`.
   - The search source is a pure function of the query plus `state`.
   - A module-level `GEN` counter: `function request(method, body) { var g =
     ++GEN; … then if (g !== GEN) return; … }`. Page loads use the same
     counter.
   - The teardown hook: whatever `renderContent` replacement implies. Guard
     `patch()` with a `mounted` flag that flips when the container is replaced;
     check how other admin pages detect teardown.
   - The browser zone: `Intl.DateTimeFormat().resolvedOptions().timeZone`.
   - **Canonicalize** with `state.links[name] || name`.
3. **CSS, testids and the registry.**
4. **The flow tests,** then the pinned lists, then the docs (README last),
   then the gate, then the canvas comparison.

## Edge Cases

- **`/api/time-zones` fails while `/api/time-settings` succeeds:** show the
  radio group and the preview. The chooser shows an error line in place of the
  list, and the zone radio still works with the remembered zone.
- **The browser's `Intl` reports no zone** (`undefined`): no hint.
- **A stored zone not in the list** (an alias, or `Etc/GMT+5`): the chosen
  line uses the stored name, and the offset comes from `effective.offset`
  when the canonical row is missing.
- **A very fast double pick:** the generation rule applies, and the last pick
  wins.
- **The theme:** the page uses tokens only; the light and dark variants come
  free.

## Files Affected

- **JS:** `static/js/settings-pages.js`, `static/js/router.js`,
  `static/js/areas/admin.js`, `static/js/areas/admin/system-page.js`,
  `static/js/areas/admin/date-time-page.js` (new).
- **HTML and CSS:** `static/index.html`, `static/css/admin.css`.
- **Docs:** `docs/ui-testid-registry.md`, `CLAUDE.md`, `the_one/agents.md`,
  `README.md`.
- **Tests:** `tests/test_settings_pages_static.py`,
  `tests/browser/test_flow_admin_settings_nav.py`,
  `tests/browser/test_flow_keyboard.py`, `tests/browser/test_flow_jump_to.py`,
  `tests/browser/_lists.py`, possibly `tests/browser/_nav.py`,
  `tests/browser/test_flow_settings_date_time.py` (new).
- **Possibly:** `scripts/run-tests.sh`, and behavior specs (text only).
- The flight log.

## Citation Audit

Per flight.md: two Architect passes spot-checked `_lists.py:243-251`,
`test_settings_pages_static.py:46-54, 73-78`, `search-list.js:220-296` and
`system-page.js:21` (not exported). Re-check line numbers at leg start,
because Flight 1 edited `system-page.js`.

---

## Post-Completion

Completion steps are Flight Control protocol, driven by the execution
workflow. They are not repeated here.

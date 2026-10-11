# Flight: The Date and Time Page

**Status**: ready
**Mission**: [Agents Know the Date and Time](../../mission.md)

## Contributing to Criteria

- [ ] **The operator sets the zone once, and it holds.** This flight adds the UI,
      and the app's displayed times follow the setting. Flight 1 built the
      server side.
- [ ] **The operator sees what agents see.**
- [ ] **A browser/server mismatch is caught.**
- [ ] **The app and its agents agree on the time.**

---

## Pre-Flight

### Objective

Build Settings › General › Date and time from the approved canvas
([Date and time settings](https://claude.ai/artifact/A89sjcpKfxd9j1BedBvkYx)):

- a radio choice between the system zone (showing the detected name) and a
  chosen zone;
- an inline searchable zone chooser, grouped by region, searchable by city,
  zone name or offset;
- a browser-versus-server mismatch hint with a one-step fix;
- a "What agents see" preview rendered from the server's own strings;
- a note on when a change applies;
- saving on choice.

Then make every clock time, day group and weekday label the app shows follow
the operator's zone instead of the browser's. That means reworking `App.time`
around `Intl.DateTimeFormat` with `timeZone`, loading the zone before the first
render, and re-rendering when it changes.

### Open Questions

- [x] How the zone reaches the client before the first render → DD1
- [x] Radio control → DD3 (a new `App.ui.radioGroup` factory)
- [x] What the client does for an unnamed system zone, or a zone its `Intl`
      doesn't know → DD1 (browser local)
- [x] Where the page sits → DD2 (General, after Appearance; section
      `date-and-time`)
- [x] Re-rendering on change → DD1 (`App.time.onChange`)

### Design Decisions

**DD1: `App.time` becomes zone-aware, and boot loads the zone before the
router starts.**

- **`static/js/time.js`** gains:
  - `setZone(key|null)`. `null` means the browser's local zone. A key the
    engine's `Intl` rejects (a `RangeError` building the formatter) also falls
    back to local, with one `console.warn`.
  - `zone()`: the key in use, or `null`.
  - `parts(date)`, returning `{year, month (0-11), day, weekday (0-6), hour
    (0-23), minute}` in the zone. It uses one cached `Intl.DateTimeFormat('en-US',
    {timeZone, hourCycle: 'h23', year/month/day/weekday/hour/minute})` and
    `formatToParts`. The local path uses the `Date` getters, so behaviour is
    unchanged when no zone is set.
  - `formatClock(date)`, now built on `parts`.
  - `dayNumber(date)`: the zone's civil date as `Date.UTC(y, m, d) / 86400000`,
    an integer, so `daysBetween` is a plain subtraction with no DST rounding.
  - `onChange(fn)`, returning an unsubscribe function. It fires after
    `setZone` changes the effective key.
- **Callers** move to `App.time.parts` and `dayNumber`, and re-render on
  change:
  - `areas/chat/chats-list.js`: `startOfDay`, `daysAgo`, `timeOf` and the
    weekday and month labels;
  - `areas/chat/message-bubble.js`: `fmtTs`. It stores the ISO stamp on the
    element (`data-ts`) so a change can re-label the attribution timestamps in
    place;
  - `areas/studio/rules-notes-tab.js`: `formatWhen`'s "today" test and labels.
  - The Chats list re-renders through its existing `renderChatsList()`, and
    the notes list re-renders if mounted. Leg 1 sweeps the client again for any
    other caller (`grep -rn "getHours\|getDay()\|getDate()\|getMonth()\|getFullYear()"`),
    and the flight log lists every caller.
- **Boot.** `app.js`'s `DOMContentLoaded` fetches `/api/config` **and**
  `GET /api/time-settings` in parallel (`Promise.all`), calls
  `App.time.setZone(App.time.zoneFromSettings(settings))`, then starts the
  router.
  - **The zone fed to `setZone`:** `App.time.zoneFromSettings(settings)`
    (below): `effective.canonical || effective.zone` when it is named. For an **unnamed** system zone, it is the server's fixed offset as
    `±HH:MM`, taken from `effective.offset`; both engines accept an offset
    `timeZone` (measured, Architect review). With no settings at all it is
    `null`. A `RangeError` still falls back to local.
  - **The settings fetch never blocks boot.** It checks `r.ok` and has its own
    catch, so a 401 or 500 body never reaches `.effective` or the
    `/api/config` fallback. Its share of the `Promise.all` is capped at **2
    seconds**: a race against a timer, after which the router starts with the
    zone unset. A later arrival still calls `setZone`, and `onChange`
    re-renders.
  - `/api/config` is untouched. Its tests run with no database, and
    `/api/info` must stay database-free because it is the launcher's probe.
- **On save,** the page calls `App.time.setZone(App.time.zoneFromSettings(response))`,
  only for a response that passes the generation check (DD4), so the open app
  re-labels at once.
- **`App.time.zoneFromSettings(settings)`** is part of the `time.js` API and
  is covered by `test_ui_time_contract.py`. It returns:
  - `effective.canonical || effective.zone` when named (both engines accept
    alias keys in `timeZone`);
  - for an unnamed zone, `effective.offset` with its `UTC` prefix stripped
    (`UTC+05:30` becomes `+05:30`; `offset_label`, `time_zones.py:~232`);
  - otherwise `null`.
- **Elapsed-time labels** ("3 hours ago", `self-configuration-tab.js`) and
  pure sorting by timestamp (`agent-picker.js`, `jump-to.js`, `chat.js`) are
  zone-independent and unchanged. The sweep confirms each. The Knowledge
  `Indexed:` lines (`knowledge-section.js:~894,1048`) show raw ISO stamps by
  M25 F6 DD14's "stays precise" rule; they are not zone-formatted, and that is
  noted rather than changed.
- **`parts()` defends against an engine returning hour `24` at midnight**
  with `% 24`; both engines measured return `00`.
- *Rationale:* the operator's decision (client formats with the zone). Boot
  ordering is the cheapest seam: the router is not started until the zone is
  known, so the first render is right.
- *Trade-off:* one more boot request (`/api/time-settings`, cheap: one key-value
  read and a cached detection).
- **Engine note.** `formatToParts` with `timeZone` is supported in Chromium,
  WebKit and WebKitGTK. The contract and browser tests run in both engines, and
  the WebKitGTK desktop is covered by the fallback.

**DD2: The page is `#settings/date-and-time`, in General after Appearance.**

- **The page table and router.** `App.settingsPages` gains `{ section:
  'date-and-time', label: 'Date and time', group: 'General', devOnly: false }`
  after Appearance. `router.js` `SECTIONS` gains the matching row in the same
  position: `tests/test_settings_pages_static.py` pins the order.
- **The admin area.** `admin.js` `GENERAL_SUBS` gains `'date-and-time'`, and
  `GENERAL_RENDERERS` gains `'renderDateTimePage'`. The page is built in a new
  `areas/admin/date-time-page.js` (DOM APIs only), loaded in `index.html`
  beside `system-page.js`, which exports `App.admin.renderDateTimePage`.
- The Settings nav, the router announcer and the Jump to palette pick it up
  from the table.
- *Rationale:* the operator chose a page of its own (canvas review). Its
  position follows the canvas nav.

**DD3: A new `App.ui.radioGroup` factory.**

- **Shape.** `App.ui.radioGroup({legend, legendHidden, name, options:[{value,
  label, description, testid}], value, onChange, testid}) -> {el,
  value(), setValue(v), setDescription(value, text), optionEl(value),
  destroy()}`.
  - It builds a native `<fieldset>`, with its CSS reset (border, padding,
    `min-inline-size: 0`), and a `<legend>` (visually hidden if
    `legendHidden`).
  - **Each option is a wrapper `div.ui-radio-option` (the card)** holding three
    siblings (Architect review: never nest the slot or the description inside
    the label):
    1. a `<label>` with only the native `<input type=radio>` and the label
       text;
    2. the description element, wired to the input with `aria-describedby`
       (the `ui/choice.js:~28-38` convention);
    3. an empty slot `div`, returned by `optionEl(value)`.
  - The zone chooser goes in the "Choose a time zone" slot, so its rows never
    become part of the radio's accessible name.
  - `:has(:checked)` and the `.is-checked` fallback class sit on the wrapper.
  - `name` defaults to `util.uid('radio')`. Same-name radios in one document
    join one group, and the contract harness mounts several instances.
  - The native input gets an explicit `:focus-visible` ring of 2px or more
    (the choice contract tests assert it, `test_ui_choice_contract.py:~495-525`).
  - **Placement:** in `ui/choice.js`, with its demo in the existing
    `ui-choices-section.js`. A new section file would break the section count
    at `test_ui_control_inventory.py:~96`.
  - **Guard rules:**
    - no HTML-sink tokens, even in comments (`test_ui_guards.py:~692`);
    - test ids forwarded as `<expr>.testid` (`:~651`);
    - the inventory status cell reads exactly `library: App.ui.radioGroup`
      (`test_ui_control_inventory.py:~55-64`).
- **Styling** follows the canvas: a hairline card per option; the selected card
  takes `--accent` border plus `--accent-translucent`, through `:has(:checked)`
  and a `.is-checked` class fallback; the focus ring is the native input's
  `:focus-visible`; `accent-color: var(--accent-fill)`.
- **Behaviour.**
  - Native radio keyboard behaviour: arrow keys move the selection and fire
    `onChange`, and Tab enters and leaves the group.
  - `onChange` fires on user change only, never on `setValue`.
- **The library contract** (CLAUDE.md "Control library"):
  - a demo on the dev-mode Design language page;
  - a row in `docs/ui-control-inventory.md`, replacing the "Radio group (theme)
    … not yet defined" row's status for the new factory, with the theme toggle
    noted as a later migration;
  - engine-parametrized contract tests (`tests/browser/test_ui_radio_group_contract.py`,
    contracts lane, Chromium and WebKit) for render, keyboard, `onChange`
    semantics, `setValue` silence, the legend name and destroy;
  - `tests/test_ui_control_inventory.py` passes.
- *Rationale:* a radio group is a control, and the project rule says new
  controls are library factories. Native radios give the keyboard model for
  free.
- *Trade-off:* the theme toggle keeps its custom segmented control for now;
  migrating it is out of scope.

**DD4: The page's layout and behaviour follow the canvas exactly** (canvas
board 1 interactive, board 2 light).

- **Header and intro.** The `h1` "Date and time" through the existing
  `renderPage` scaffold, then the intro "Agents use this time zone when they
  tell the time, and the app shows times in it."
- **The "Time zone" section** (`.section-title`):
  - A `radioGroup`, `name="time-zone-mode"`, its legend "Time zone" hidden,
    with two options:
    - **"Use the system time zone"**, with the description "Detected on the
      machine running the-one: {system.zone or 'no zone name detected'} ·
      {system.offset}";
    - **"Choose a time zone"**, with the description "For a server, WSL or a
      container whose clock zone is not yours."
  - **Under "Choose a time zone"** (its `optionEl` slot), shown only while
    that radio is checked:
    - a line, "Selected: **{city}** {zone} · {offset}" when a zone is chosen,
      else "Pick a zone below. Nothing changes until you do.";
    - an inline `App.ui.searchList` (`label` "Search time zones", placeholder
      "Search by city, zone or offset: Tokyo, Europe/, +05:30"), with:
      - groups by `region` in `/api/time-zones` order;
      - item `label` = city, `description` = zone (mono), `meta` =
        `{offset} · {abbreviation}` (mono);
      - a `lead` on **every** row, of fixed width: a check icon on the chosen
        zone and an empty spacer elsewhere, so text never shifts. There is no
        `aria-selected`, which the factory reserves for the active row. The
        lead is `aria-hidden`, so the "Selected: …" line is wired to the search
        input with `aria-describedby`, which carries the announcement;
      - the `meta` drops the abbreviation when it is numeric (`+14`, `-03`),
        leaving only `UTC+14:00`;
      - `emptyText` "No time zones match “{query}”.";
      - a `max-height` of about 252px, set by page CSS on its listbox.
    - **Search** is case-insensitive over city, zone, offset (with the `UTC`
      prefix optional, `−` and `-` treated alike) and abbreviation, and `_` and
      a space are treated alike.
    - **Alias names are searchable** (second review, high). tzdata 2026 makes
      many real cities aliases of another city (`Europe/Oslo` → `Europe/Berlin`,
      `Europe/Amsterdam` → `Europe/Brussels`, `Atlantic/Reykjavik` →
      `Africa/Abidjan`; 253 `L` lines).
      - When the query is non-blank, the source also matches every `links` key
        by its own city and zone text.
      - Each alias match not already covered by a matching canonical row
        appears as **its own item** in its region group: label = the alias's
        city, description = `{alias} · same clock as {canonical}`, meta = the
        canonical row's offset.
      - Picking it PUTs the **alias name**, so the operator's agents say
        "Europe/Oslo", the name they chose. The server accepts links through
        `is_known_zone`.
      - With a blank query only canonical rows are listed.
- **Saving.** It happens on user choice only:
  - picking "Use the system time zone" PUTs `{mode: 'system', zone:
    <current zone or null>}`, keeping the remembered zone (Flight 1 DD3);
  - picking "Choose a time zone" PUTs **nothing** until a zone is picked,
    unless a zone is already remembered, in which case it PUTs `{mode: 'zone',
    zone}` at once;
  - picking a zone row PUTs `{mode: 'zone', zone}`.
  - **Patch in place, never rebuild** (Architect review). The page builds its
    nodes once, as `chat-pane.js` does. A response:
    - calls `radioGroup.setValue`;
    - sets `textContent` on the chosen line, the preview, the hint and the
      status;
    - calls `searchList.refresh()`, keeping `scrollTop` and then
      `setActive(chosenCanonical)`.

    The search list is never rebuilt, so focus stays where it was: a row pick
    keeps focus in the search input.
  - **Ordering.** Every PUT and every page load carries a generation number
    from a **module-level** counter in `date-time-page.js`, shared across page
    mounts, because `admin._refresh` re-runs `renderContent` and builds a new
    page instance. Only the latest response is applied. A response that
    arrives for a torn-down page updates `App.time` only if it is the latest,
    and touches no DOM.
  - **On a failed PUT** the page shows the error and **re-GETs**
    `/api/time-settings` (with a new generation) to restore the controls. It
    never restores a cached copy, which could be stale after reordering.
  - **Arrow keys in the radio group** fire `change` on each step, so each step
    PUTs. That is accepted (FD decision): there are two options, and the
    generation rule applies.
  - **The active row.** `setActive(chosen)` runs on load, after every refresh,
    and when the slot is revealed. While the slot is hidden the scroll math
    sees zero-size boxes, so the call is repeated after reveal.
  - **Suppressing the active-row style.** The page CSS rule is
    `.date-time-page .ui-search-list:not(:focus-within) .ui-search-list-row[aria-selected="true"]`,
    which resets background and border to the rest state. The root holds both
    the field and the listbox (`search-list.js:~92`). A matching
    `@media (forced-colors: active)` rule sits beside the existing one at
    `components.css:~2029`. An unfocused list therefore never shows
    Africa/Abidjan "selected".
  - **Enter with a blank query** picks the active row, which is the chosen
    zone after `setActive`. That is a no-op re-save, which is acceptable.
  - Picking "Choose a time zone" does **not** move focus (FD decision). The
    search input is the next Tab stop.
  - A status line (`role="status"`, `aria-live="polite"`) reads "Saved. Agents
    now use {zone or 'the system time zone'}." in `--status-success`.
  - A failed PUT shows the server's `detail` in an error line, and the
    controls revert to the last saved state.
  - No Save button, no dirty source, no leave guard.
- **The mismatch hint** (`role="note"`, `.banner banner-info`). Browsers
  report **legacy aliases**: `Asia/Calcutta`, `Europe/Kiev`, `UTC` and others,
  measured in Chromium and WebKit, and WebView2 is Chromium (Architect review,
  high). Every comparison therefore uses **canonical** names, through DD6's
  `links` map:
  - `canonical(browser) = links[browser] || browser`;
  - the hint shows when `canonical(browser)` differs from
    `effective.canonical`, or `effective.canonical` is null and the browser's
    zone is known;
  - text: "Your browser is in **{browser}** ({browser offset}), but the machine
    running the-one reports **{effective label}**. That happens under WSL, in
    a container or on another machine.";
  - a secondary button, "Use {browser}" with **the name the browser reports**.
    It PUTs that name as reported, which the server accepts (canonical names
    and links alike), and is shown only when the name is in `zone_names` (a
    canonical row or a `links` key). A 422 hides the button and shows the
    error.
  - The hint text shows the browser's reported name, followed by
    "(same clock as {canonical})" when it differs from its canonical name.
    Comparisons stay canonical.
  - **The browser offset** is taken from the canonical row in
    `/api/time-zones`. When the canonical name isn't listed (for example
    `Etc/GMT+5`), the offset is omitted from the hint. It never comes from
    `Intl` `longOffset`, which returns a bare `GMT` at zero offset.
  - **The "Selected" line** shows the **stored** name: "Selected: **{city of
    the stored name}** {stored zone} · {offset}". The city is the stored name's
    last segment with `_` turned into a space. The offset comes from the
    canonical row.
  - **The check icon** sits on the canonical row of the stored zone, so a
    stored alias marks its canonical row.
  - The hint hides once they agree.
- **"What agents see"** (`.section-title`): a three-row definition list.
  - **"The time tool returns"** shows `preview.tool`'s first line in a code
    chip.
  - **"A new chat starts with"** shows `preview.prompt`, or
    `preview.prompt_without_tool` when `tool_enabled` is false. When it is
    false, a muted line follows: "The time tool is turned off in Built-in
    tools."
  - **"Times in the app"** shows `preview.clock` plus "in the Chats list and
    on messages".
  - Then the note: "The time tool uses a new zone at once. A chat that is
    already open keeps the date it was last loaded with; the next chat or a
    reopened one gets the new one."
- **Testids** (registered in `docs/ui-testid-registry.md`):
  - `date-time-mode` (the radio group's `<fieldset>`);
  - `date-time-mode-system` and `date-time-mode-zone`, on the **native radio
    inputs**, as `checkbox` and `toggle` do (`choice.js:~17`);
  - `date-time-chosen`, `date-time-search` (the input), `date-time-zone-row`
    (with `data-zone`);
  - `date-time-mismatch`, `date-time-use-browser`;
  - `date-time-preview-tool`, `date-time-preview-prompt`,
    `date-time-preview-clock`;
  - `date-time-status`, `date-time-error`.
- **Copy.** All server text is placed with `textContent`. The page builds with
  DOM APIs (no HTML strings, enforced by `test_ui_guards.py`).
- **Loading.** On entering the page it fetches `/api/time-settings` and
  `/api/time-zones` (both on every entry; the list is about 340 rows, small).
  While loading it shows "Loading…". A failed load shows an error line and no
  controls.

**DD5: Verification is browser tests, with no behavior test.**

- **The apparatus is Playwright with a controlled browser zone:**
  `browser.new_context(timezone_id=...)`, reachable through
  `credentialed_context(...)` (`tests/browser/conftest.py:~395-431`), not the
  `page` fixture.
  - The server's zone is set through `PUT /api/time-settings`.
  - The "system" path is pinned deterministically by spawning the app with
    `extra_env={"TZ": "<zone>"}`, which pins `detect_system_zone`. Don't read
    back whatever the host detects: CI may detect nothing, `UTC` or `Etc/UTC`.
  - Mismatch flows use zone pairs that are canonical in Chromium (Asia/Tokyo,
    Pacific/Kiritimati, Pacific/Pago_Pago).
  - A dedicated alias test sets `timezone_id="Asia/Kolkata"` with the server on
    `Asia/Kolkata`, and expects **no** hint.
- **The read path:**
  - DOM text and testids;
  - `GET /api/time-settings` after each save, with the credential helpers;
  - the Chats list rows' visible group headers and labels for seeded sessions
    (`seeders.seed_session` with fixed `updated_at`).
- **Day-boundary determinism:**
  - Page clock: Playwright 1.58 is pinned (`pyproject.toml:~136`), so use
    `page.clock.set_fixed_time(...)`. **Never** `install()`, which fakes timers
    and `performance.now`, which `_nav.wait_settled` polls
    (`_nav.py:~318-339`).
  - Pick zones far apart (`Pacific/Kiritimati` +14, `Pacific/Pago_Pago` -11)
    so the same instant is a different calendar day.
- No live model or external session is involved, so no behavior test. The
  mission criteria here are fully observable through the browser and the API.

**DD6: The server gives the client canonical names (an additive change to
Flight 1's API).**

- **`GET /api/time-zones`** gains `"links": {alias: canonical, …}`, built from
  the `L` lines `_parse_tzdata_zi` already reads (`the_one/time_zones.py:~80-96`).
- **`GET /api/time-settings` and `PUT`** give `effective` a `canonical` field:
  the canonical name of `effective.zone`, or `null`. The server can itself
  report an alias, for example `TZ=Asia/Calcutta`.
- **The zone list** (`zone_rows`):
  - also excludes the POSIX-style canonical zones (`CST6CDT`, `EST5EDT`,
    `MST7MDT`, `PST8PDT`, and any other canonical name with no `/`), which are
    still accepted when typed or stored;
  - its numeric-abbreviation handling is client-side, in DD4's meta.
- **Tests:** the Flight 1 unit tests gain these keys. No existing key changes.
- *Rationale:* only the server has the authoritative link table. Chromium
  canonicalizes an explicit `timeZone` to the alias while WebKit keeps it as
  given, so the client can't canonicalize reliably on its own.

### Prerequisites

- [x] Flight 1 server API in the working tree: `GET`/`PUT /api/time-settings`
      (with `effective.zone`, `system`, `preview`, `tool_enabled`) and
      `GET /api/time-zones` (rows with `zone, region, city, offset,
      abbreviation`).
- [ ] Flight 1 landed and committed. Flight 2 branches from
      `flight/01-agents-know-the-time`.
- [x] Playwright 1.58 is pinned, so `timezone_id` and `page.clock` are
      available (verified by the Architect).
- [x] Flight 1 leg 2b (`current-time-tool-client`) edits `system-page.js` and
      lands first. `renderPage` is private (`system-page.js:21`, with only
      three renderers exported at ~188-190), so this flight's
      `date-and-time-page` leg exports it as `App.admin.renderPage`.
- [x] WebKit userland for the contracts lane
      (`bash scripts/setup-webkit-userland.sh` if missing).

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete (below; spot-checked by two Architect passes)
- [ ] Prerequisites verified (Flight 1 commit pending)
- [x] Validation approach defined
- [x] Legs defined

### Citation Audit

Verified against the working tree (Flight 1 uncommitted on top of `afa7855`):

| Citation | Status |
|---|---|
| `static/js/time.js::formatClock` uses `getHours`/`getMinutes`; exports `App.time = {formatClock}` | verified |
| `areas/chat/chats-list.js` (57-100): `WEEKDAYS`/`MONTHS`, `startOfDay` via local getters, `daysAgo` rounding, `bucketOf`, `timeOf` | verified |
| `areas/chat/message-bubble.js` (~107-114): `fmtTs` → `App.time.formatClock(new Date(ts))` | verified |
| `areas/studio/rules-notes-tab.js` (~540-548): `formatWhen` local "today" test plus `MONTHS` | verified |
| `static/js/settings-pages.js`: `PAGES` rows `{section, label, group, devOnly}`, frozen; pinned with `router.js` `SECTIONS` by `tests/test_settings_pages_static.py` | verified |
| `static/js/router.js` (81-96): `SECTIONS` settings rows in page order | verified |
| `areas/admin.js`: `GENERAL_SUBS` (11), `GENERAL_RENDERERS` (~326-330), `renderContent` dispatch | verified |
| `areas/admin/system-page.js::renderPage(container, title, headingId, children)` (21) | exists but is **not exported** (only three renderers at ~188-190), so it is exported in this flight's `date-and-time-page` leg |
| `static/js/app.js` (~195-220): boot fetches `/api/config` then `App.router.start` | verified |
| `the_one/interfaces/web/api.py::get_config` (479): no database read; `tests/test_api_config.py` uses a bare router client | verified |
| `static/js/ui/search-list.js`: options `label`, `placeholder`, `source(query)`, items `{id,label,description,meta,metaMono,lead,testid,dataset}`, `emptyText`, `onPick`; `aria-selected` only on the active row; Escape not handled | verified |
| `docs/ui-control-inventory.md:60`: "Radio group (theme) … not yet defined" | verified |
| `tests/browser/conftest.py` (~395-431): `credentialed_context(**context_kwargs)` passes them straight through to `browser.new_context` | verified (Architect) |
| `static/js/ui/search-list.js` (~226-227): `refresh()` resets `scrollTop` and activates the first option | verified (Architect) |

---

## In-Flight

### Technical Approach

1. **Leg 1, `time-zone-client-core`:**
   - **DD6's server additions first**, so the client can rely on them: the
     `links` map, `effective.canonical` and the POSIX exclusion, with unit
     tests. Leg 1 owns them (second review: boot uses `canonical`).
   - the `App.time` rework (DD1, including `zoneFromSettings`), the bounded
     boot fetch, the three callers plus any the sweep finds, and re-render on
     change.
   - **Pin the existing time-label tests** to a zone, because they currently
     assume the browser's zone equals the server's detected zone:
     - `tests/browser/test_flow_chat_list.py` (~130-200, with stamps seeded
       from browser-local times);
     - `test_clock_formatter_edges` (~436-450, with `new Date(2026,5,15,h,m)`);
     - any notes-time test.

     Pin each either with `App.time.setZone(null)` or with a matching
     `extra_env={"TZ": …}` plus `timezone_id`, and list every one in the flight
     log.
   - **New tests:**
     - a `test_flow_chat_time_zone.py` (chats lane, through the `test_flow_chat*`
       glob), with a browser `timezone_id` differing from the operator zone,
       proving the Today/Yesterday groups, weekday and clock labels follow the
       operator zone, and that a `setZone` change re-labels without a reload;
     - a `test_ui_time_contract.py` (contracts lane), which loads `js/time.js`
       itself, because `load_harness` loads only `js/ui/*.js`. It covers both
       engines: `parts`, `dayNumber` across a DST boundary, an offset zone,
       the invalid-zone fallback and `onChange`.
   - **Checkpoint:** `make gate`, because the boot change touches every lane,
     including router boot tests that stub `/api/config`
     (`test_router_core.py:~463`).
2. **Leg 2a, `radio-group-control`:**
   - `App.ui.radioGroup` in `ui/choice.js` (DD3), with its demo in
     `ui-choices-section.js`, the inventory row, and
     `tests/browser/test_ui_radio_group_contract.py` (contracts lane, both
     engines).
   - It is independent of leg 1.
3. **Leg 2b, `date-and-time-page`:**
   - `App.admin.renderPage` exported;
   - the table and router rows (DD2), and the page (DD4) with the testid
     registry;
   - **every pinned Settings list updated:**
     - `tests/test_settings_pages_static.py:~47`;
     - `tests/browser/test_flow_admin_settings_nav.py:~46` (`GROUPS`);
     - `tests/browser/test_flow_keyboard.py:~198-206`;
     - `tests/browser/test_flow_jump_to.py:~49`;
     - `tests/browser/_lists.py:~243-255` (`SETTINGS_PAGE_TITLES`);
     - `tests/browser/_nav.py:~210`;
     - the behavior specs `workbench-navigation.md` and
       `shell-navigation-smoke.md`, if they enumerate Settings pages.
   - **Browser tests** in `test_flow_settings_date_time.py`, settings lane.
     The lane is at 430 of 540 s and about 12 new tests will likely flag OVER
     BUDGET. Re-budget the `settings` row in `scripts/run-tests.sh`'s table
     with the measured number, or split the file into a lane of its own;
     record which in the flight log. `tests/test_run_tests_lanes.py` pins the
     table.
     - load in the system state, pinned with `TZ`;
     - choose a zone by search (city, zone, offset), then saved, then the
       preview updates, then `GET` agrees;
     - "Choose a time zone" with nothing remembered saves nothing;
     - back to system keeps the remembered zone;
     - the mismatch hint with `timezone_id` differing, then "Use {browser}",
       then the hint gone;
     - the Kolkata alias case, with no hint;
     - the Oslo merged-zone case: `timezone_id="Europe/Oslo"` with the server
       on `Europe/Berlin` shows no hint. Searching "Oslo" shows an
       "Oslo · same clock as Europe/Berlin" item, and picking it stores
       `Europe/Oslo`;
     - the tool turned off, then the without-tool wording;
     - a 422 path (a `page.route` on `/api/time-zones` injecting a bogus row),
       then an error and a revert;
     - a stale load not overwriting a newer save;
     - Jump to finds "Date and time";
     - the app's clocks change after a save without a reload.
   - **Docs:**
     - CLAUDE.md: the router hash list gains `#settings/date-and-time`, plus
       the Settings pages paragraph and an `App.time` mention;
     - `agents.md`: "Settings nav and pages", plus a new `App.time` contract;
     - `docs/ui-control-inventory.md`;
     - `docs/ui-testid-registry.md`;
     - **`README.md`** (rebuilt by squawk 0170, PR #264, merged during this
       mission):
       - the "built-in tools" list gains `current_time` (Time: the current
         date and time in your zone, always available);
       - the Settings paragraph (~line 94) gains "Date and time picks the time
         zone agents and the app use";
       - the Chats/agents text notes that agents know today's date.
   - `make gate` with WebKit.
   - Optional: a WebKitGTK probe of `App.time.parts`
     (`scripts/webkitgtk_probe.py`, port 8486 or higher).

### Checkpoints

- [ ] Leg 1: `make gate` green (WebKit).
- [ ] Leg 2a: the contracts lane green (WebKit), plus the static guards.
- [ ] Leg 2b: `make gate` green with `THE_ONE_REQUIRE_WEBKIT=1`.

### Adaptation Criteria

**Divert if**:

- WebKit or WebKitGTK `Intl` lacks `formatToParts` with `timeZone`, or
  mis-handles a zone, beyond the planned fallback.
- The canvas layout can't be met with the existing `searchList` factory
  without changing its contract. A contract change to a shared library
  control is a scoped design review, not an inline change.

**Acceptable variations**:

- Exact copy tweaks within the canvas's meaning.
- The listbox height.
- Whether the chosen-zone line or the check `lead` carries the "selected"
  signal, provided at least one is visible and it is announced through text.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `time-zone-client-core`: the server canonical-name additions (DD6), the
      zone-aware `App.time`, the bounded boot fetch, the callers re-rendering
      on change, the existing time tests pinned, and the new tests.
- [ ] `radio-group-control`: `App.ui.radioGroup` with its demo, inventory row
      and contract tests.
- [ ] `date-and-time-page`: the page and routing, the pinned Settings lists,
      the flow tests, the lane budget, the docs, and the full gate.

No HAT leg. The operator reviews at the mission PR.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged (the mission PR)
- [ ] Tests passing (`make gate`, WebKit)
- [ ] Documentation updated

### Verification

- `make gate` green with WebKit required.
- The browser tests listed in the Technical Approach.
- The canvas compared side by side with a local dev instance at the end of
  leg 2. The flight log records any deviation.

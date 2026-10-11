# Leg: time-zone-client-core

**Status**: completed
**Flight**: [The Date and Time Page](../flight.md)

## Objective

Every clock time, day group and weekday label the app shows follows the
operator's time zone, loaded before the first render and re-rendered when it
changes. The server also gives the client canonical zone names (`links` and
`effective.canonical`), so later comparisons can use them.

## Context

- Read [flight.md](../flight.md):
  - **DD1:** `App.time`, boot, callers, `zoneFromSettings`;
  - **DD6:** the server canonical-name additions. This leg owns them.
- **Flight 1** is committed at `a9c8da5` (branch
  `flight/01-agents-know-the-time`). This flight's branch
  `flight/02-date-and-time-page` starts there. The as-built server API:
  - `the_one/time_zones.py`: `_parse_tzdata_zi()` returns
    `(canonical_tuple, name_frozenset)` and reads `Z`/`L` lines; plus
    `zone_rows`, `offset_label`, `zone_label`, `EffectiveZone(key, tzinfo)`;
  - the routes in `the_one/interfaces/web/api.py`: `GET`/`PUT /api/time-settings`
    and `GET /api/time-zones`.
- **Host rule** (Flight 1 finding): run browser lanes and `make gate` on this
  WSL host with `THE_ONE_TEST_NETNS=1`. Without it, scattered `wait_settled`
  timeouts appear. The known flake `test_flow_jump_to.py::test_new_chat_opens_the_agent_picker`
  is squawk 0168.

## Inputs

- Branch `flight/02-date-and-time-page` at `a9c8da5`. The working tree holds
  only the uncommitted Flight 2 status edit.
- `static/js/time.js`: `App.time = {formatClock}`, loaded right after `app.js`
  in `index.html:~34`.
- `static/js/app.js` (~195-220): the boot fetches `/api/config`, then
  `App.router.start`.
- The callers:
  - `areas/chat/chats-list.js` (~57-100): `WEEKDAYS`, `MONTHS`,
    `startOfDay`, `daysAgo`, `bucketOf`, `timeOf`;
  - `areas/chat/message-bubble.js` (~107-130): `fmtTs` and the
    `.msg-attribution-ts` span;
  - `areas/studio/rules-notes-tab.js` (~538-548): `formatWhen`, plus
    `renderList` at ~444 and ~793.
- `areas/chat.js` (~488-503): `renderChatsList()`.

## Outputs

- **`the_one/time_zones.py`:**
  - `zone_links() -> dict[str, str]` (alias → canonical, from the `L`
    lines);
  - `canonical_name(key) -> str | None`;
  - `zone_rows` also excludes the canonical names that contain no `/`
    (`CST6CDT`, `EST5EDT`, `MST7MDT`, `PST8PDT`, and `Factory` as already).
- **`the_one/interfaces/web/api.py`:**
  - `GET /api/time-zones` returns `{"zones": [...], "links": {...}}`;
  - the `GET`/`PUT /api/time-settings` `effective` object gains
    `"canonical": canonical_name(effective.zone)`, or `null`.
- **`static/js/time.js`:**
  - `setZone`, `zone`, `parts`, `formatClock`, `dayNumber`, `onChange`,
    `zoneFromSettings`;
  - a `load()` helper the boot uses, with the 2-second bound and `r.ok`
    handling, or inline in `app.js` (the Developer's choice; document it).
- **`static/js/app.js`:** the boot loads the zone before `App.router.start`.
- **The callers:**
  - `chats-list.js`, `message-bubble.js` (with `data-ts` on the timestamp
    span) and `rules-notes-tab.js` are converted;
  - each re-renders on `App.time.onChange`: the Chats list via
    `renderChatsList`, message timestamps re-labelled in place, the notes
    list if mounted.
  - Every listener is removed on teardown where the module has one.
- **Tests:**
  - `tests/test_time_zones.py` and `tests/test_time_settings_api.py` gain the
    `links`/`canonical`/POSIX cases;
  - new `tests/browser/test_ui_time_contract.py` (contracts lane, both
    engines);
  - new `tests/browser/test_flow_chat_time_zone.py` (chats lane);
  - the existing time-label tests are pinned to a zone (see AC8).
- **Docs:**
  - `the_one/agents.md`: a new "`App.time` (M28 F2)" contract section, plus
    the time-zones section's `links`/`canonical`;
  - CLAUDE.md: one sentence in the M28 time-zone paragraph that app clock
    times follow the operator zone through `App.time`.
- **The flight log:** the leg entry, including the full caller sweep result.

## Acceptance Criteria

**Server (DD6)**

- [ ] **AC1.** `zone_links()` is a **separate** cached function. Don't change
      `_parse_tzdata_zi`'s return arity, which `canonical_zones` and
      `zone_names` depend on.
  - It reads the `L <target> <alias>` lines as `{alias: target}` and resolves
    chains transitively, so every value is canonical. A test asserts that
    every link target is in `canonical_zones()`.
  - The named expectations are `Asia/Calcutta` → `Asia/Kolkata`, `UTC` →
    `Etc/UTC` and `US/Pacific` → `America/Los_Angeles`. `Europe/Oslo` is
    asserted only as "an alias whose target is canonical", because the target
    depends on the tzdata version.

  `canonical_name(key)` returns:
  - the key itself for a canonical name;
  - `links[key]` for an alias;
  - `None` for unknown or non-string input.

  `zone_rows` excludes `Factory`, `CST6CDT`, `EST5EDT`, `MST7MDT` and
  `PST8PDT`, which still validate through `zone_names()` when stored or
  typed. Tests assert structure and these named cases, never counts.
- [ ] **AC2.** `GET /api/time-zones` carries `links`, and it equals
      `zone_links()`. `effective.canonical` covers four cases:
  - a stored alias (`Asia/Calcutta`) gives `effective.zone` `Asia/Calcutta`
    and `canonical` `Asia/Kolkata`;
  - a canonical zone gives the same name in both;
  - an unnamed system zone gives `null` in both;
  - a system zone detected as an alias (monkeypatch `detect_system_zone` to
    return `Asia/Calcutta`) gives the canonical name.

  No existing key changes, so every Flight 1 route test still passes.

**`App.time` (DD1)**

- [ ] **AC3.** `App.time.setZone(key | null)`:
  - `null` means browser-local;
  - an IANA key builds one cached `Intl.DateTimeFormat('en-US', {timeZone,
    hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
    weekday: 'short', hour: 'numeric', minute: 'numeric'})`;
  - **an offset key `±HH:MM` is implemented by hand, with no `Intl`** (FD
    decision; WebKit may reject offset `timeZone` strings): `parts` reads
    `new Date(t + offsetMs)` through the UTC getters. This makes
    `zoneFromSettings`'s offset branch engine-independent;
  - `parts` maps `formatToParts` types `year`/`month`/`day`/`weekday`
    (`'short'` en-US, through `{Sun:0 … Sat:6}`)/`hour`/`minute`;
  - a `RangeError` falls back to local with one `console.warn`;
  - `zone()` returns the key in effect, or `null` after a fallback;
  - `onChange(fn)` listeners fire once after the effective key changes, and
    never when it doesn't.

  `onChange` returns an unsubscribe function.
- [ ] **AC4.** `App.time.parts(date)` returns integers `{year, month (0-11),
      day, weekday (0-6, Sunday = 0), hour (0-23), minute}` in the zone, with
      hour `% 24`. On the local path it uses the `Date` getters, and the output
      matches them exactly.
  - `formatClock(date)` builds `h:mm AM/PM` from `parts`, unchanged in form.
  - `dayNumber(date)` returns `Date.UTC(year, month, day) / 86400000` from
    `parts`, an integer.
- [ ] **AC5.** `App.time.zoneFromSettings(s)` deliberately prefers
      `canonical`, so `App.time.zone()` can differ from a stored alias. This
      is documented in `agents.md`. It returns:
  - `s.effective.canonical || s.effective.zone` when either is a non-empty
    string;
  - otherwise, when `s.effective.offset` matches `^UTC[+-]\d{2}:\d{2}$`, the
    offset without `UTC` (`+05:30`);
  - otherwise `null`.

  A malformed `s` returns `null` and never throws.
- [ ] **AC6. Boot.** `DOMContentLoaded` runs these in parallel:
  - `/api/config`, as today;
  - `GET /api/time-settings`, which checks `r.ok` and has its own catch, so a
    failure leaves the zone unset and never feeds `/api/config`'s fallback.

  The router starts when `/api/config` has settled **and** either the
  settings response has arrived or **2 seconds** have passed, whichever is
  first. It is implemented as `Promise.all([configChain,
  Promise.race([settingsChain, timeout2s])])`:
  - the settings chain never rejects (its own catch plus `r.ok`);
  - the timer is cleared when settings win;
  - the existing `.catch(...).then(start)` chain is where this goes. `App.time.setZone(App.time.zoneFromSettings(s))` runs before
  `router.start` when the response is in time, else whenever it arrives
  later. `tests/browser/test_router_core.py` and every other boot test still
  pass: they stub `/api/config`, and `/api/time-settings` gets 200 from the
  real server.

**The callers**

- [ ] **AC7.** Each caller uses `App.time.parts` and `dayNumber`, and none
      calls the local getters for display or day arithmetic:
  - **`chats-list.js`:**
    - recency groups by `dayNumber(now) - dayNumber(d)`;
    - the weekday label is `WEEKDAYS[parts(d).weekday]`;
    - the `Mon D` label is `MONTHS[parts(d).month] + ' ' + parts(d).day`;
    - Today uses `formatClock`.
  - **`message-bubble.js`:** `fmtTs` is unchanged in output for local, and
    the timestamp span carries `data-ts="<iso>"`.
  - **`rules-notes-tab.js`:** `formatWhen`'s "today" test is
    `dayNumber(d) === dayNumber(now)`, its year test uses `parts`, and its
    labels come from `parts`.

  Re-rendering on `App.time.onChange`:
  - **The chat area** lives for the page's lifetime (`chat.js:~499-501`), so a
    single subscription is enough, with no unsubscribe. It calls
    `renderChatsList()`, then re-labels every `.msg-attribution-ts[data-ts]` in
    place with `formatClock(new Date(el.dataset.ts))`.
    `renderAttribution` (`message-bubble.js:~117-127`) sets `data-ts`
    whenever `formatted` is non-empty.
  - **The rules-notes tab has no teardown hook** (`renderRulesNotesTab`
    rebuilds through `panel.textContent = ''`). Each notes-section build
    subscribes once, and its listener **unsubscribes itself** when it fires
    with its `listWrap` no longer `isConnected` (the file already uses
    `isConnected`, ~95). A test switches tabs away and back, then changes
    the zone once, and checks there is no error and exactly one render of
    the live list.
  - **Signatures stay.** `chats-list.js`'s exported `bucketFor`/`timeFor` keep
    their `(row, now)` signatures (with `now` defaulting to `new Date()`), and
    the now-unused `startOfDay` is deleted.

  **The sweep.** `grep -rnE "getHours|getMinutes|getDay\(\)|getDate\(\)|getMonth\(\)|getFullYear\(\)|toLocale"`
  over `static/js` finds only:
  - uses inside `time.js`;
  - sorting or elapsed-time uses, each listed in the flight log as
    zone-independent.

  The Knowledge `Indexed:` raw stamps are noted as intentionally untouched
  (flight DD1).
  - **The sweep is enforced, not just logged.** A new static unit test
    (`tests/test_time_getters_static.py`, in `make test-unit`) greps
    `static/js/**/*.js` for `getHours|getMinutes|getDay\(|getDate\(|getMonth\(|getFullYear\(|toLocale`
    and fails on any hit outside `js/time.js`.
- [ ] **AC8. Existing time tests pinned.** Every browser test that asserts a
      clock, weekday, `Mon D` or day-group label is made zone-deterministic.
  - These include `tests/browser/test_flow_chat_list.py` (~130-200 and
    `test_clock_formatter_edges` ~436-450) and any notes-time assertion
    (`grep -rn "formatClock\|Today\|Yesterday\|AM\b\|PM\b" tests/browser/`
    and triage).
  - **The pin, by FD decision.** For `test_flow_chat_list.py` (`_STAMPS_JS`
    ~43-55, `_hhmm`/`_md` ~94, the groups test ~122-200), browser and operator
    are made to agree by construction:
    1. read `Intl.DateTimeFormat().resolvedOptions().timeZone` in the page;
    2. `PUT /api/time-settings` with `{mode: "zone", zone: <that>}`, through
       `auth_headers_for`;
    3. navigate.

    That keeps `_stamps`' local-midnight skip valid, and it exercises the
    operator-zone path.
  - For `test_clock_formatter_edges` (pure JS): `App.time.setZone(null)`
    inside the evaluate.
  - **Never** `setZone(null)` right after boot for a test that reads the list:
    it races the boot's own late `setZone`. Only after `wait_settled`, and
    only for pure formatter checks.
  - **Triaged as zone-independent** (no pin; recorded in the log):
    - `test_flow_chat_peer_attribution.py` (~161-224, a shape-only regex);
    - `test_flow_new_chat.py` (~315-324, "Today" for a just-created session);
    - `test_ui_list_pane_chats_contract.py` (literal labels).
  - No browser test asserts notes timestamps today. AC10 adds one notes "when"
    assertion.
  - Without a pin, these tests pass only while the host's `tzlocal` name
    equals Chromium's zone. The flight log records that this is why they are
    pinned.

**New tests**

- [ ] **AC9.** `tests/browser/test_ui_time_contract.py` runs in the contracts
      lane, through the `engine_page` fixture, Chromium and WebKit.
  - **No harness.** `engine_page` builds a context with no options
    (`_ui_engines.py:~155-166`), so call `page.set_content('<!doctype
    html><html><body></body></html>')`, then
    `page.add_script_tag(path=<static>/js/time.js)`. `time.js` needs only
    `window`.
  - **The local path** is asserted by comparing against the page's own `Date`
    getters, which needs no fixture change.
  - **Cases:**
    - `parts` for `Asia/Kolkata` and `Pacific/Kiritimati` at a fixed instant;
    - `formatClock` at midnight and noon;
    - `dayNumber` across the US DST change (`America/New_York`,
      2026-03-08 and 2026-11-01): consecutive days differ by exactly 1;
    - an offset zone `+05:30`;
    - an invalid zone (`Mars/Olympus_Mons`): fallback to local, `zone()`
      `null`, one warning;
    - `onChange` firing once per effective change and not on a same-key
      `setZone`, and its unsubscribe working;
    - `zoneFromSettings`, for each AC5 branch.
- [ ] **AC10.** `tests/browser/test_flow_chat_time_zone.py` (chats lane):
  - **Setup:** a context with `timezone_id="Pacific/Pago_Pago"` (UTC-11).
    `PUT /api/time-settings` to `Pacific/Kiritimati` (UTC+14) before the page
    loads. Fix the page clock with `page.clock.set_fixed_time` at an instant
    where the two zones are on different calendar days. Seed sessions with
    fixed `updated_at`.
  - **Asserts:**
    - the Chats list's group headers and row time labels are those of
      Kiritimati, not Pago Pago (a row from "Kiritimati today" is under
      Today with its Kiritimati clock time);
    - a message attribution timestamp shows the Kiritimati clock;
    - calling `App.time.setZone('Pacific/Pago_Pago')` in the page re-labels
      the list and the attribution without a reload.
  - `page.clock.install()` is never used, because it would break
    `_nav.wait_settled`.
  - **Boot bound.** In the sync Playwright API a route handler must not sleep,
    so the handler for `**/api/time-settings` **captures** the `route` object
    without continuing it.
    - The test asserts that the app is usable (the router started, the Chats
      list rendered) within about 3 s.
    - It then calls `route.continue_()` and asserts the labels switch to the
      operator zone.
    - This test uses plain `_nav.goto` plus `expect`, **never** `goto_settled`
      or `wait_settled`, which would wait on the held fetch.
  - **Notes "when" label:** one assertion that a seeded note's "when" label in
    the agent's Rules and notes tab follows the operator zone (`seed_note`).
  - **Instants:** Kiritimati and Pago Pago are 25 h apart, so any instant puts
    them on different calendar days. Pick a mid-day UTC instant, call
    `page.clock.set_fixed_time` **before** `goto`, and assert both labels.

**Gate and docs**

- [ ] **AC11.** The static guards pass:
  - `tests/test_ui_guards.py`, `tests/test_token_definitions.py`,
    `tests/test_design_tokens_a11y.py`;
  - `tests/test_nav_helper.py`;
  - `tests/test_run_tests_lanes.py`: the new files land in the right lanes
    (check with `bash scripts/run-tests.sh --lane contracts --list` and
    `--lane chats --list`).

  `make test-unit` is green. Then `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1
  PYTHON=.venv/bin/python TEST_TIMEOUT=3600 make gate` is green, apart from
  squawk 0168 if it recurs. Its lane table and `PARALLEL_RESULT` line are
  recorded in the flight log. Any other single failure is re-run in
  isolation and recorded.
- [ ] **AC12.** The docs:
  - `agents.md`: the `App.time` contract (API, fallback, boot bound,
    re-render subscribers, the flake-safe testing rule: never
    `page.clock.install()`), plus the `links`/`canonical` additions;
  - CLAUDE.md: one sentence.

## Verification Steps

- **AC1, AC2:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_time_zones.py tests/test_time_settings_api.py -x --timeout 60`.
- **AC3-AC5, AC9:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_ui_time_contract.py -x`.
- **AC6-AC8, AC10:**
  - `… tests/browser/test_flow_chat_time_zone.py tests/browser/test_flow_chat_list.py -x`;
  - then `--lane routing`, for the boot tests.
- **AC11:** the commands as written.
- **AC12:** read the diffs.

## Implementation Guidance

1. **Server first** (`time_zones.py`, `api.py`, unit tests).
2. **`time.js`**, written to the ES5 style of the file:
   - one module-scoped formatter and key;
   - the local path keeps `getHours` and the other getters (the only
     allowed users).
3. **The boot in `app.js`:** wrap both fetches. Use a small race helper, a
   `Promise` with `setTimeout(resolve, 2000)`. Never block on the settings
   fetch beyond that.
4. **The callers,** then the `onChange` wiring. For message attributions, a
   single subscription in the chat area module is enough. Re-label
   `document.querySelectorAll('.msg-attribution-ts[data-ts]')`.
5. **Tests,** then the full gate, then the docs.

## Edge Cases

- **The settings fetch returns 401** (credential race at boot): ignore it and
  keep local.
- **`setZone` with the same key** is a no-op: no rebuild, no `onChange`.
- **An offset key `+00:00`:** accepted, and it behaves as UTC.
- **A session `updated_at` without a zone suffix:** the existing `new
  Date(ts)` parsing behaviour is unchanged. Don't fix it here.
- **The Chats list during the 2-second boot window:** it renders at most
  once with the local zone, then re-renders on change. That is acceptable
  (DD1); it only happens on a slow server.

## Files Affected

- `the_one/time_zones.py`, `the_one/interfaces/web/api.py`.
- `static/js/time.js`, `static/js/app.js`.
- `static/js/areas/chat/chats-list.js`, `areas/chat/message-bubble.js`,
  `areas/chat.js`, `areas/studio/rules-notes-tab.js`.
- `tests/test_time_zones.py`, `tests/test_time_settings_api.py`.
- `tests/browser/test_ui_time_contract.py` (new),
  `tests/browser/test_flow_chat_time_zone.py` (new),
  `tests/browser/test_flow_chat_list.py`, and any other pinned time test.
- `the_one/agents.md`, `CLAUDE.md`.
- The flight log.

## Citation Audit

Checked at `a9c8da5`:

- `index.html:34`: `time.js` loads after `app.js`.
- `chat.js:488,502-503`: `renderChatsList`, and its subscription to
  `sessions`.
- `message-bubble.js:109,124-128`: `fmtTs` and the `msg-attribution-ts` span.
- `rules-notes-tab.js:444,538,793`: `renderList`, `formatWhen`,
  `renderList`.
- `test_flow_chat_list.py:436`: `test_clock_formatter_edges`.

The rest are as cited in flight.md (two Architect passes).

---

## Post-Completion

Completion steps are Flight Control protocol, driven by the execution
workflow. They are not repeated here.

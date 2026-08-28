# Squawk 0014: Studio `loadAll()` chains have no `.catch` — one failed fetch leaves the area silently blank

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

Studio's `init()` and `_refresh` both call `loadAll().then(...)` with no rejection
handler. `loadAll` is a `Promise.all` over six fetches (agents, tools, MCP sources,
knowledge bases, providers, connectors), none of which catch internally. Any single
non-2xx, network blip, or non-JSON error body becomes an unhandled promise rejection:
the Studio area never mounts (or stops refreshing), nothing is shown to the operator,
and only the console knows. The newer self-configuration tab already does this
correctly — its status fetch has a `.catch` that writes a visible "Unable to load …"
line. Found by the 2026-08-27 maintenance inspection (E6).

Fix: add a `.catch` to both `loadAll()` call sites that renders a visible error state
in the Studio area, following the self-configuration tab's pattern.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio.js:2919` (`init`) —
  `loadAll().then(function () { … });` — no `.catch`
- `the_one/interfaces/web/static/js/areas/studio.js:2878` (`self._refresh`) — same
- `the_one/interfaces/web/static/js/areas/studio.js:1377` — `loadAll` =
  `Promise.all([fetchAgents(), fetchTools(), fetchMcpSources(), fetchKnowledgeBases(),
  fetchProviders(), fetchConnectorsList()])`
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js:1386-1390`
  — the in-repo pattern to copy (`.catch(function () { statusLine.textContent =
  'Unable to load …'; … })`)

## Corrective Action

Added a shared `showLoadAllError(err, opts)` helper in
`the_one/interfaces/web/static/js/areas/studio.js` (just after `loadAll()`,
~line 1404) and chained `.catch()` onto both call sites:

- `init()`'s `loadAll().then(...)` (~line 2919) — `.catch(function (err) {
  showLoadAllError(err); })`. Appends a persistent, visible line — `'Unable to
  load Studio data — ' + reason + '.'` — into `sectionContentEl` using the
  same `.admin-loading` class studio.js already uses for section-level fetch
  failures (`fetchMcpSources_`/`fetchConnectors_`), which is already styled
  for `.area-studio` in `studio.css`. Built via `createElement`/`textContent`
  (not string-concatenated `innerHTML`) so it doesn't add a new site to the
  `tests/test_ui_guards.py` dynamic-sink freeze. `role="alert"` for screen
  readers.
- `self._refresh`'s `loadAll().then(...)` (~line 2878) — `.catch(function
  (err) { showLoadAllError(err, { nonDestructive: true }); })`. Per the
  "don't blank an already-rendered area" requirement, this branch does NOT
  touch `sectionContentEl`; it calls the existing `App.showFlash(content, msg,
  true)` overlay instead — the same non-destructive top-level-fetch-failure
  pattern `admin.js:534` already uses (`App.showFlash(contentEl, 'Failed to
  load ' + name + '.', true)`), so no new component was designed.

`loadAll()` itself is unmodified — its `Promise.all` semantics and internal
`.then` are untouched; only the two external call sites gained a trailing
`.catch`. No retry affordance was added (none exists as an established
pattern for a *whole-area* load failure elsewhere in the app — only for a
single field's fetch inside an already-mounted editor — so per the squawk's
"do not design a new component" instruction, none was added here).

## Verification

Added `tests/browser/test_flow_studio_loadall_error.py` (3 new tests), route-
stubbing `/api/knowledge-bases` (one of loadAll's six fetches) to return a
non-JSON `500` body via Playwright `page.route` (mirrors the established
`page.route`/`route.fulfill` pattern in
`tests/browser/test_flow_studio_agent_save_race.py` and
`tests/browser/test_mcp_test_connection_button.py`). A non-JSON body is
required to actually trigger the rejection — none of the six fetch helpers
check `r.ok`, so a JSON error body resolves `.json()` successfully and would
not reproduce the bug:

- `test_loadall_failure_on_init_shows_visible_error` — stubs the route
  before `page.goto(#studio)`; asserts `.studio-loadall-error` becomes
  visible with `role="alert"` and text containing "Unable to load Studio
  data" instead of a silent blank area.
- `test_loadall_healthy_renders_normally` — baseline, no stub; asserts the
  area renders normally (`new-agent-btn` visible) and neither new error
  surface appears — regression guard against the fix itself misfiring.
- `test_refresh_failure_shows_error_without_blanking_content` — loads studio
  healthy first, then stubs the route and triggers `activate()` → `_refresh`
  by clicking to the Chat area and back; asserts `.app-flash.error` appears
  with the same message AND that the already-rendered header/CTA
  (`new-agent-btn`) is still visible throughout (not blanked).

Commands run:
- `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh -m
  browser tests/browser/test_flow_studio_loadall_error.py -x --timeout 90` —
  3 passed.
- `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_ui_guards.py -x --timeout 90` — 14 passed (innerHTML
  dynamic-sink freeze and testid registry unaffected — the new error node is
  built via `createElement`/`textContent`, no new testid was introduced).
- `make lint` — ruff, all checks passed.
- `make format-check` — ruff format, 442 files already formatted (JS isn't
  covered by the Python-only formatter; hand-checked indentation/style
  against the surrounding code instead, per the squawk 0010 precedent).

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `5cf3cac` on `squawk/turnaround-2026-08-27` — PR #178

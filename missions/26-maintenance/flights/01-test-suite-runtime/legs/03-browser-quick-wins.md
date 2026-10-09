# Leg: browser-quick-wins

**Status**: completed
**Flight**: [Test-suite runtime](../flight.md)

## Objective
Remove the browser suite's avoidable server starts and dead tests, with no coverage lost:
- the 35-row redirect table runs on one server;
- redirect-only duplicates go, once every assertion they make is pinned elsewhere;
- the readiness poll is tightened;
- the three long-skipped "deferred" tests are deleted or rewritten.

Then re-measure the whole browser suite sequentially.

## Context
- **Mission constraint "No coverage loss".** A test may be collapsed or removed only when another test fails on the same regression. Each removal is named in the flight log with the test that covers it.
- **Measured cost** (report 2026-10-08, R3/R6/R10):
  - `test_router_core.py::test_redirect_row_on_boot` is 35 params × about 1.5 s, each on its own `app_clean` server: about 52 s.
  - The 5 candidate duplicates are about 13 s.
  - `_wait_for_ready` polls every 0.1 s; at about 0.03 s the saving is about 45 s.
  - Three tests have been skipped since Mission 8 as "deferred".
- **The candidate duplicates are not all pure duplicates.** This was checked at design time:
  - `test_flow_admin_navigation.py::test_admin_redirect_root_to_appearance` and `::test_admin_legacy_system_redirects_to_appearance`, and `test_flow_hash_routing.py::test_studio_root_redirects_to_agents`, assert the route **and that the destination page renders** (the Appearance title, or the Agents panel visible). The router table asserts only the history write.
  - `test_flow_admin_settings_nav.py::test_settings_general_redirects_on_a_cold_load` (3 params) and `::test_legacy_general_hashes_redirect_directly` (3 params) also assert the Appearance title and `_assert_never_general` (`lastRoute`/`current()`). The second also asserts that a typed legacy hash is rewritten in place after boot.
  - So the rule is: **delete a test only once each of its assertions is pinned by a remaining test**, if necessary by adding that assertion to the collapsed table loop. Otherwise collapse its params onto one server instead of deleting it.
- **Prior legs.** Leg 2 seeded every server from the template. See the flight log for the measured per-start time this leg builds on.

## Inputs
- `tests/browser/test_router_core.py`:
  - `REDIRECT_ROWS` (32) and `GENERAL_ALIAS_ROWS` (3);
  - `test_redirect_row_on_boot` (`@pytest.mark.parametrize` over both, about line 285);
  - the helpers `_boot` and `_boot_recorded`, which use `page.add_init_script(_RECORD_HISTORY_JS)`;
  - the assertions: first write is `replaceState` to `"#" + route`, `state.seq` is an int, no `pushState`, and `history.length == 2`.
- `tests/browser/_nav.py`: `LEGACY_URL_TESTS`, the docstring list and the frozenset, about lines 74–116.
- `tests/browser/conftest.py::_wait_for_ready`: `time.sleep(0.1)`.
- The stale skips:
  - `tests/browser/test_flow_agent_tabs.py:266`, `test_advanced_section_visible_with_disabled_inputs`;
  - `tests/browser/test_mcp_test_connection_button.py:237`, `test_capability_flags_render_for_announced_capabilities`;
  - `tests/browser/test_flow_studio_openrouter_picker.py:203`, `test_picker_preserves_value_across_type_switch_as_custom`.
- CLAUDE.md "Expected unit skip count (squawk 0132)".

## Outputs
- `test_redirect_row_on_boot` becomes **one** test on one server that loops every row.
- Duplicates are removed or collapsed per the rule above. `LEGACY_URL_TESTS` (docstring and frozenset) is updated to match.
- `_wait_for_ready` polls at 0.03 s.
- One stale test is deleted, two are rewritten, and none is left skipped as deferred.
- The CLAUDE.md skip-count note is amended for `THE_ONE_TEST_NETNS=1`.
- A sequential full-browser re-measure is recorded in the flight log against the baseline.

## Acceptance Criteria
- [ ] **AC1. The redirect table runs on one server.** `test_redirect_row_on_boot` runs every row of `REDIRECT_ROWS + GENERAL_ALIAS_ROWS` against a single `app_clean` server.
  - **Each row gets a fresh page** in the same context: `page.context.new_page()`, or an equivalent that keeps the session cookie. So the `history.length == 2` assertion still holds per row.
  - **Each row keeps all four existing assertions:** first write `replaceState` to `"#" + route`, integer `seq`, no `pushState`, history length 2.
  - **Each row also asserts the committed destination rendered:** `.content-panel.active[data-destination]` exists, and its `data-destination` is the route's first segment.
  - **Failures are collected across rows.** The test asserts once at the end with a message listing every failing `(legacy, route)` and what was observed, so one bad row never hides another.
  - Each per-row page is closed after use.
- [ ] **AC2. Duplicates are removed only with full coverage.** For each of the 5 candidates, the flight log names its fate:
  - **`deleted`**, listing for each of its assertions the remaining test, or the AC1 table, that pins it; or
  - **`collapsed`**, where its params now share one server; or
  - **`kept`**, with the reason.

  Hard constraints:
  - `test_nav_guard.py::test_legacy_hash_link_in_content_redirects_and_is_guarded` is not touched; it tests the guard, not the redirect.
  - The "Appearance title renders after a legacy load" assertion and `_assert_never_general` must each survive in at least one test.
  - So must the typed-legacy-after-boot rewrite in `test_legacy_general_hashes_redirect_directly`.
- [ ] **AC3. `LEGACY_URL_TESTS` matches the remaining tests.** Both the docstring list and the frozenset name exactly the surviving raw-legacy tests. `tests/test_nav_helper.py` passes in the unit tier.
- [ ] **AC4. The readiness poll is tightened.** `_wait_for_ready` sleeps 0.03 s between polls. The 15 s timeout and early-exit-on-death behaviour are unchanged.
- [ ] **AC5. No deferred skips remain.**
  - `test_advanced_section_visible_with_disabled_inputs` is deleted. The feature is gone: `advanced-collapsible` is no longer rendered, which you confirm with a grep of `the_one/interfaces/web/static/`.
  - `test_capability_flags_render_for_announced_capabilities` is rewritten to seed the MCP source's cached server info and assert the `.mcp-capability-flags` line in the server-info panel. It shows announced capabilities only.
  - `test_picker_preserves_value_across_type_switch_as_custom` is rewritten against the current picker's type-switch flow.
    - First establish in a real browser what the current UI does with a model id the new provider does not list. The "(custom)" option still exists: see `tools-form-helpers.js` and `studio.js`.
    - Assert that behaviour.
    - If the current behaviour looks like a defect (the value silently lost), do not fix it here. Assert what is pinnable, log a squawk, and name it in the flight log.
  - `grep -rn "pytest.mark.skip(" tests/browser/` shows no reason containing "deferred", "Deferred" or "Flight 6".
- [ ] **AC6. The skip-count note covers netns.** CLAUDE.md "Expected unit skip count" adds a sentence: under `THE_ONE_TEST_NETNS=1` the count is 12 even on a quiet host. `unshare -rn` maps the test process to uid 0, so `test_kb_walk.py`'s and `test_kb_watcher.py`'s root-only permission tests skip ("root bypasses permission bits"), and their coverage is lost in that mode.
- [ ] **AC7. Lanes stay green, and the gain is measured.**
  - **Pass set.** All six browser lanes run sequentially under `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600`, with `THE_ONE_REQUIRE_WEBKIT=1` for `contracts`, with zero failures. Each lane's passed count equals baseline minus the removed or collapsed items, and the arithmetic is shown in the flight log. Skips drop by exactly the 3 stale tests.
    - Baseline: chats 168/0, agents 153/2, library 153/1, settings 214/0, contracts 672/3, shared 465/0.
  - **Timings.** Per-lane wall times and the total are recorded against the 2026-10-08 baseline (272/370/522/411/184/729 s; 2488 s total), using the baseline's flags (`-v --tb=short -rs --junitxml=… --durations=0 --durations-min=0.05`). The setup-phase sum per lane comes from the baseline `agg.py`.

## Verification Steps
- **AC1–AC3:**
  - `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=1200 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_router_core.py tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_admin_settings_nav.py tests/browser/test_flow_hash_routing.py tests/browser/test_nav_guard.py -x --timeout 120`
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_nav_helper.py -x --timeout 60`
- **AC1 falsification:** temporarily break one row's expected route. The test fails, and its message names that row. Revert, and note it in the flight log.
- **AC4:** read the code.
- **AC5:**
  - Run the three files with `-m browser -rs`; no skip lines appear for these tests.
  - Run the grep from AC5.
- **AC6:** read CLAUDE.md.
- **AC7:** run the lanes in background, each to its own log in the scratch area. Run them one at a time (sequential is the baseline condition), and poll the logs.

## Implementation Guidance
1. **Collapse the redirect table (AC1).**
   - Keep `REDIRECT_ROWS` and `GENERAL_ALIAS_ROWS`, which `PARITY_CORPUS` also uses, unchanged.
   - Write a per-row helper. It opens a new page from `page.context`, adds `_RECORD_HISTORY_JS`, boots the raw hash with `_boot`, reads the writes, and checks.
   - The `page` fixture's context already holds the session cookie: see conftest `_establish_session_cookie`. Confirm a fresh page in that context is authenticated.
2. **Decide each duplicate's fate (AC2).** For each, list its assertions, find a pin for each, and record the fate.
   - With AC1's destination-rendered check, the two `test_flow_admin_navigation` tests and `test_studio_root_redirects_to_agents` are expected to become deletable. Their "Appearance title text" and "agents panel visible" checks are covered by the `data-destination` check together with the remaining Settings and Agents tests that assert the page title. Confirm and name the covering test.
   - The two `test_flow_admin_settings_nav` parametrized tests are expected to be **collapsed** (loop their 3 params on one server, fresh page per param) rather than deleted, because they carry `_assert_never_general` and the typed rewrite.
3. **Update `LEGACY_URL_TESTS` (AC3)** and run `tests/test_nav_helper.py`.
4. **Ready-poll (AC4).** One constant change.
5. **Stale skips (AC5).** Delete one and rewrite two.
   - For the MCP rewrite, find how the editor mount reads the cached server info (`renderServerInfoSection` in the static JS) and seed that cache through the API or the data dir. Prefer the API.
6. **CLAUDE.md (AC6).**
7. **Full sequential re-measure (AC7)** at leg end. Record it in the flight log under this leg, along with the leg 2 + leg 3 combined saving.

## Edge Cases
- **Fresh page per row and `add_init_script`.** Init scripts belong to the page they are added to, so add one to each new page; adding it to the fixture's `page` does not carry over.
- **Memory across 35 page opens.** Close each page in a `finally`.
- **A row whose route's first segment differs from its `data-destination`.** Every current row's first segment is one of `chats`, `agents`, `library`, `settings`. If the app stamps anything else, compare against `App.router.current().destination` (or the equivalent) rather than the string split.
- **A rewritten test that fails against the current UI.** Never mark it skip or xfail. Either the assertion is wrong (fix the test) or the UI is (log a squawk and assert what is pinnable).

## Files Affected
- `tests/browser/test_router_core.py`
- `tests/browser/test_flow_admin_navigation.py`, `tests/browser/test_flow_admin_settings_nav.py`, `tests/browser/test_flow_hash_routing.py`
- `tests/browser/_nav.py` (`LEGACY_URL_TESTS`)
- `tests/browser/conftest.py` (`_wait_for_ready`)
- `tests/browser/test_flow_agent_tabs.py`, `tests/browser/test_mcp_test_connection_button.py`, `tests/browser/test_flow_studio_openrouter_picker.py`
- `CLAUDE.md` (skip-count note)
- `missions/26-maintenance/flights/01-test-suite-runtime/flight-log.md`

## Citation Audit
Checked against the working tree at `16e91d7`:

| Citation | Status |
|---|---|
| `test_router_core.py:236` `REDIRECT_ROWS` (32 rows); `:279` `GENERAL_ALIAS_ROWS` (3); `:285` parametrize; `:286` `test_redirect_row_on_boot` with its 4 assertions | verified |
| `test_router_core.py:26` `_boot`; `:53` `_boot_recorded` | verified |
| `_nav.py:74–116` `LEGACY_URL_TESTS` docstring plus frozenset (10 entries, 4 of them candidates) | verified |
| `test_flow_admin_settings_nav.py` `test_settings_general_redirects_on_a_cold_load` (parametrize `route`, 3 values), `test_legacy_general_hashes_redirect_directly` (parametrize `legacy`), `_assert_never_general` at about 360 | verified |
| `test_flow_admin_navigation.py` two redirect tests: title Appearance plus `expect_route` | verified |
| `test_flow_hash_routing.py::test_studio_root_redirects_to_agents`: `destination_panel("agents")` visible plus `expect_route` | verified |
| `conftest.py:158` `time.sleep(0.1)` in `_wait_for_ready` | verified |
| stale skips at `test_flow_agent_tabs.py:266`, `test_mcp_test_connection_button.py:237`, `test_flow_studio_openrouter_picker.py:203` | verified |

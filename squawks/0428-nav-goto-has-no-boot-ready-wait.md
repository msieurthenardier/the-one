# Squawk 0428: `_nav.goto` does not wait for the app to boot, so first expectations time out under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: 2026-11-27

## Report

`tests/browser/_nav.py::goto` is a plain `page.goto` to a hash URL. On a heavily loaded host (load about 26), the app's boot takes longer than Playwright's default 5 s `expect` timeout. The bwrap probe slows the first `/api/config`, the router starts late, and only then do the areas render. So a test whose first step is `expect(...).to_be_visible()` fails with "element(s) not found".

Seen at the 2026-11-25 squawk turnaround on `tests/browser/test_flow_chat_composer_library.py::test_the_empty_states_text_column_is_centred`. It failed in the `chats` lane, and again 2 of 2 in isolation, at load 26. That file was untouched by the turnaround.

This is the same class as squawk 0424. That squawk's fix covers `open_destination` (rail clicks) and the predicates that call `_sessionState()`. It does not cover `goto`.

**More evidence (sortie 20 closing gate, 2026-11-26).** Twenty-two browser tests failed both on sortie 20's tree and on a pristine `main` (`7518aefa`), all at load 16 to 23. Most of them show an empty `<main>` and "element(s) not found" on a first expectation, which is this squawk's class:
- `test_flow_new_chat.py` (4, the welcome screen);
- `test_flow_admin_navigation.py` (3), `test_flow_settings_window_chrome_signal.py` (3), `test_flow_admin_tools_grid.py::test_admin_tools_settings_nav_label_is_built_in_tools`, `test_flow_keyboard.py::test_settings_nav_links_are_in_tab_order`;
- `test_flow_provider_setup.py::test_first_start_provider_setup_flow`, `test_flow_provider_library.py::test_bare_providers_section_is_an_alias_for_the_library_root`;
- `test_theme_cross_tab_sync.py::test_theme_set_and_unset_propagate_across_tabs`, `test_flow_agent_routines_self_config.py::test_routines_tab_origin_flag_and_the_flag_clearing_edit`;
- `test_flow_chat_composer_library.py::test_the_empty_states_text_column_is_centred`;
- `test_flow_chat_live_updates.py` (2, mid-turn join) and `test_flow_context_overlay_thresholds.py` (1, an `httpx.ReadTimeout`) may be a different, load-only class.

The full list is in `sorties/20-deleting-an-agent-deletes-its-chats/flight-log.md` ("Gate triage after rebase", "Closing gate and landing"). When this squawk is completed, re-run these on a loaded host as part of its verification.

## Evidence
- `tests/browser/_nav.py::goto` only calls `page.goto`. Compare `open_destination`, which since 0424 calls `wait_router_started(page)` first.
- `tests/browser/test_flow_chat_composer_library.py:134-136`: `_nav.goto(...)` then `expect(welcome).to_be_visible()`, with the default 5 s timeout.

## Corrective Action
`tests/browser/_nav.py::goto` now takes a keyword-only `boot: bool = True` and, after `page.goto`, calls `wait_router_started(page)` (15 s, instant on a warm page). `boot=False` skips the wait for a page where `window.App` never boots. Caller audit (grep over `tests/browser/`, about 107 files): no caller loads a non-app page or a deliberately failing `/api/config`, so none needs `boot=False`. `test_flow_chat_time_zone.py::test_boot_waits_at_most_two_seconds_for_the_time_zone` holds `/api/time-settings`, but the boot waits at most 2 s, so the router still starts inside 15 s. `tests/test_nav_helper.py` gains a boot/no-boot test and its kwargs test passes `boot=False` (its fake page has no `wait_for_function`).

**Sweep (Flight 2 follow-up, this squawk's second leg).** `_nav` gains `goto_url(page, url, *, boot=True, **kw)` (a full URL kept as written: `page.goto(url)` then `wait_router_started`, response returned) and `goto_root(page, base, *, boot=True, **kw)` (the app root). `goto(page, base, "")` was not used: `hash_for("")` is `"#"`, so it would load `base/#`, not `base`. `_nav` still calls `page.goto` with an absolute URL, so the conftest credential wrapper is untouched. Of 119 raw `.goto(` call sites in `tests/browser/`, 102 were converted (`goto_root` for the root forms, `goto_url` for the raw-hash `_boot` helpers in `test_router_core.py` and `test_router_route_change.py`, whose own duplicate `wait_for_function` lines were dropped). The Flight 2 in-place `wait_router_started` lines in `test_flow_new_chat.py` (4) and `test_flow_provider_setup.py` (1) became the helper call. 17 sites stay raw, allowlisted per file with a reason in `RAW_GOTO_ALLOWANCE` (`tests/test_nav_helper.py`): `_ui_engines.py` 2 (about:blank, styling harness), `test_smoke.py` 1 (data: URL), `test_router_popstate_engines.py` 2 (static PAGE_URL), `test_flow_oauth_callback_cross_site.py` 3 (raw contexts, /api/info, /api/live), `test_app_fixture.py` 1 (title only), `test_app_spawn_credential_wiring.py` 2 (asserts the document request's Authorization header), and 6 deliberate legacy-URL (AC6) sites in `test_flow_admin_tools_grid.py`, `test_flow_chat_peer_attribution.py`, `test_flow_hash_routing.py`, `test_flow_studio_mcp_navigation.py`, `test_flow_agent_tabs.py` and `test_flow_admin_settings_nav.py`, each now followed by `_nav.wait_router_started(page)`. 39 browser test files, `_nav.py`, `tests/test_nav_helper.py` and this squawk changed (42 files).

**Guard.** `tests/test_nav_helper.py::test_no_raw_goto_in_browser_tests` AST-scans `tests/browser/**/*.py` for `<x>.goto(` calls where `<x>` is not `_nav` (comments and docstrings are not calls), skips `_nav.py`, and compares per-file counts with `RAW_GOTO_ALLOWANCE`. A new raw goto fails with a message saying to use `_nav.goto`, `goto_root` or `goto_url`; a converted one fails until its allowance is lowered, so the list only shrinks. `test_raw_goto_guard_self_test` and `test_goto_url_and_goto_root_load_the_url_as_written_and_wait` pin the detector and the helpers. Falsified: a raw `page.goto(app_clean)` put into `test_flow_picker.py` failed the guard ("1 raw .goto( call(s) at line(s) [13], allowed 0"), then was reverted.

Original suggested direction: `goto` calls `wait_router_started(page)` after `page.goto`. That costs nothing on a warm page. A full browser run must validate it, because every lane uses `goto`. Check first for callers that load a page without `window.App`.

## Verification
Progress (Flight 2 Leg 4): `tests/test_nav_helper.py` passes; the failing test passed 3 of 3 in isolation at load 12 to 15 (it was not failing before the change at that load, so this is not a reproduction of the race).

The full fallback gate (23 lanes one at a time, load 2 to 25) found the same race in tests that call a raw `page.goto(base)` (the 0428 evidence list), which `_nav.goto` does not cover. Fixed in place with a `_nav.wait_router_started(page)` line after the goto: `test_flow_new_chat.py` (4 tests) and `test_flow_provider_setup.py::test_first_start_provider_setup_flow`; all 13 pass at load 18 to 22 after, 4 and 1 failed before. `test_flow_context_overlay_thresholds.py` had an `httpx` 5 s read timeout, raised to 30 s; it passes. **Not done:** about 98 other raw `page.goto(<base>)` call sites remain (they passed in the gate, so are not failing today); a helper or a conftest wrapper wait is a follow-up. `test_flow_chat_live_updates.py` mid-turn join is a different class: squawk 0433. Status stays `in-progress` until a quiet-host gate stays green.

**Verification of the sweep (2026-11-26 to 27).** `tests/test_nav_helper.py` + `tests/test_run_tests_lanes.py`: 109 passed (load 13.6); ruff check and format clean.

Full browser run, `THE_ONE_TEST_NETNS=1 make test-browser`, `--parallel 3`:
- Attempt 1 (`TEST_TIMEOUT=3600`) at load 35 to 41 (not mine; it fell to about 9 as soon as the run was killed) was SIGKILLed at 3662 s with the first three lanes unfinished: `PARALLEL_RESULT rc=137 total=3662s`. Void.
- Attempt 2 (`TEST_TIMEOUT=14400`), load 5 at start, 8 to 20 during: `PARALLEL_RESULT rc=1 total=13894s lanes=23 failed=routing,agents,chats,chats-transcript,shared,mcp-connection,gleepglorp-chat,contracts-widget,chats-widgets`. Every lane was far over its quiet-host budget. Lanes green: agent-tabs, library, contracts-controls, settings, gleepglorp-kinds, mcp, knowledge, providers, agent-routines, settings-tools, contracts-overlay, gleepglorp-fill, contracts-chat, contracts-widget-lifecycle.
- The 9 failed lanes held 5 test failures and 15 setup errors. 14 of the errors were `App subprocess ... not ready within 15.0s` (spawn timeouts under load, before any `_nav` call). Triage, each in isolation at load 8 (`scripts/run-tests.sh <ids> -m browser`): all 5 failures and the 14 spawn errors passed (36 passed), except `test_flow_chat_live_updates.py::test_a_message_sent_during_a_mid_turn_join_is_held_then_delivered`, which failed again ("never joined while the connector turn was running"): the known mid-turn join flake, squawk 0433, recorded and accepted. Its sibling (`test_joining_mid_turn_ends_...`) passed. The last two errors (`..._signin_lifecycle[breadcrumb]`, `..._drawer_shell[library/mcp/~new]`) passed (5 passed, load 7). Failures that were in files edited by this sweep (`test_studio_mcps_tab::test_attach_source_persists`, `test_flow_chat_queued_render`, `test_flow_chat_transcript_library::test_a_restored_count_...`) all passed in isolation; the two webkit contracts-widget failures (files not edited) too.

Squawk evidence list, in isolation: `test_the_empty_states_text_column_is_centred` 3 of 3 passed (load 35, 30, 26 at start; about 8 s each); `test_flow_admin_navigation.py` + `test_flow_settings_window_chrome_signal.py` + `test_theme_cross_tab_sync.py`: 11 passed (load 24 at start, 10 at end).

Unit: `THE_ONE_TEST_NETNS=1 make test-unit` (load 7): `1 failed, 12389 passed, 15 skipped` (skip count as expected). The one failure, `tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`, passes alone (0.6 s); that file is not touched and it looks like a load flake.

The quiet-host criterion is not met: the full run was never at load below 1. The run at load 5 to 20 was green apart from load-induced spawn timeouts and the 0433 flake, all of which clear in isolation. Left for the Flight Director to decide.

Criteria: at high load (above 10), the failing test passes 3 of 3 in isolation. A full browser gate on a quiet host stays green.

**Review fix (2026-11-27).** `goto_url` and `goto_root` gained a keyword-only `boot_timeout` (default 15000 ms, passed to `wait_router_started` only, never to `page.goto`); the `_boot` helpers in `test_router_core.py` and `test_router_route_change.py` (and the cold-item `goto_url` in the latter) pass `boot_timeout=30000`, keeping their old 30 s bound. Changed-file count corrected to 39 browser test files. `tests/test_nav_helper.py`: 87 passed (load 2.1); ruff check and format clean. `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 scripts/run-tests.sh --lane routing`: 193 passed in 1657 s (load 7.4 at the end, 2 at the start), including both router files.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; test-only, no security-sensitive surface), review of the sweep, then a re-review of the `boot_timeout` fix cycle
**Verdict**: confirmed.
- `goto_root` and `goto_url` load exactly the URL the raw `page.goto` did, keep the response and `**kw`, and still go through the conftest credential wrapper.
- About 20 converted sites sampled: no converted site's return value is used, and no `page.route` gates the router start.
- All 17 allowlisted sites are legitimate. All six AC6 sites wait for the router before any app expectation.
- The guard only shrinks.
- Fix cycle: the router `_boot` sites keep their old 30 s bound through `boot_timeout`, and `tests/test_nav_helper.py` pins it.

**Flight Director disposition of the quiet-host criterion.** It is not met: the host was never below load 1 during this work. The squawk is completed anyway, for three reasons.
- The fix is test-only and verified under load. The evidence test passed 3 of 3 at load 26 to 35. Every full-run failure cleared in isolation except the known 0433 flake. The routing lane passed at load 2 to 7.
- The remaining check is a timing and quiet-host measurement. The Mission 37 debrief says those run as an operator-triggered measurement on a quiet host, not inside a fix. It is carried to that run (debrief action item "T1 and T2"), with this squawk's evidence list re-run there.
- The 14 app-spawn setup errors in the full run are a separate class, logged as squawk 0438.

**Commit**: `squawk/0428: ...` on squawk/0428-nav-goto-boot-wait

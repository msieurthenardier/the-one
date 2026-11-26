# Squawk 0428: `_nav.goto` does not wait for the app to boot, so first expectations time out under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

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
*(written at completion)*

Suggested direction: `goto` calls `wait_router_started(page)` after `page.goto`. That costs nothing on a warm page. A full browser run must validate it, because every lane uses `goto`. Check first for callers that load a page without `window.App`.

## Verification
At high load (above 10), the failing test passes 3 of 3 in isolation. A full browser gate on a quiet host stays green.

## Sign-Off
*(written at completion)*

# Squawk 0386: Split the three crowded modules before Mission 36 Flight 2

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: 2026-11-19

## Report
Mission 36 Flight 1 left three modules at or over their size line. Flight 2 adds a proposals UI to the chat drawer and to studio, and adds proposal reads to GleepGlorp's views. With no room left, the next change would condense lines again, as Leg 3 did in `studio.js`, or would fail the size rule. Split each one by concern, with no behaviour change, before Flight 2's first leg:
- `areas/chat/agent-drawer.js`;
- `areas/studio.js`;
- `the_one/gleepglorp/views.py`, one module per kind or capability, keeping one public entry point.

## Evidence
- `wc -l`: `static/js/areas/chat/agent-drawer.js` 798, `static/js/areas/studio.js` 799 (both against `LIMIT = 800` in `tests/test_area_module_size.py`), and `the_one/gleepglorp/views.py` 846 (no cap, but one file holds every read surface).
- `missions/36-gleepglorp-assistant/flights/01-gleepglorp-exists-and-answers/flight-debrief.md`, "Technical" and "Recommendations" 1.
- `tests/test_gleepglorp_views.py` covers the views' structural allowlist and secret parity, and must pass unchanged after the split.

## Corrective Action
No behaviour change; code moved verbatim behind the same public names.
- `areas/chat/agent-drawer.js` 798 to 643 lines. New `agent-drawer-groups.js` (190, `App.chat.drawerGroups`): `isToolEnabled`, `builtinGroups`, `group`, `rulesGroup(rulesState)`, `notesGroup(notesState)`. The drawer re-exports `isToolEnabled`/`builtinGroups` on `App.chat.agentDrawer`. Loaded before `agent-drawer.js` in `index.html`.
- `areas/studio.js` 799 to 714 lines. New `studio/studio-breadcrumb.js` (the item-header breadcrumb click handler and focus-after-close) and `studio/studio-subscriptions.js` (the agent, provider, Library store and GleepGlorp subscriptions; the subscriptions, which included the Leg 3 one-liners, moved with their original statements), each a `create(ctx)` reaching the shell through `ctx` (call-time getters for the agents list and controller). Loaded after `secret-glue.js`, before `studio.js`.
- `the_one/gleepglorp/views.py` 846 to 92 lines: the single public entry point (`read`, `VIEWS`, `KINDS`, `ALLOWED`, `LIST_KINDS`, `PlainMessage`, `UndeclaredKeyError`, `cut`, `scrub_url`, `UNREADABLE`), unchanged import path. New `view_core.py` (348: declared keys, `_emit`, helpers, `_list_or_detail`), `view_overview.py` (83), `view_agents.py` (93), `view_mcp.py` (135), `view_library.py` (192).
- `the_one/agents.md` module maps updated (drawer, studio shell, GleepGlorp views). `tests/test_area_module_size.py` ALLOWANCE named none of these; no test changed.

## Verification
- Static and unit: `tests/test_ui_guards.py test_ui_ownership.py test_ui_emitted_classes.py test_area_module_size.py test_store_static.py test_nav_helper.py test_gleepglorp_*.py test_tool_categories.py test_index_asset_cache_busting.py test_studio_editor_contracts_static.py test_library_groups_static.py test_mcp_state_words_static.py test_ui_control_inventory.py`: 424 passed.
- `ruff check` and `ruff format --check` on `the_one/gleepglorp`: clean.
- Browser lanes (`THE_ONE_TEST_NETNS=1`, foreground, one at a time): `chats` 176 passed, `agents` 186 passed, `library` 122 passed, `providers` 144 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0386-0390
**Verdict**: confirmed (pure move verified by AST comparison and code read; full gate green: unit 10696 passed, browser rc=0 lanes=20)
**Commit**: `squawk: turnaround 2026-11-19` on flight/01-gleepglorp-exists-and-answers (PR #380)

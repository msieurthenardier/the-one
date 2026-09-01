# Squawk 0028: Studio Tools tab has no category for the connector tools

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: 2026-09-01

## Report

`studio.js`'s `TOOL_CATEGORIES` (~`:273-277`) buckets built-in tools into Filesystem/Execution/Web
only, and `tools-tab.js` renders no fallback for uncategorized tools — so `send_to_platform_channel`
and `fetch_channel_history` (Mission 23 Flight 2) are completely invisible in the per-agent Built-in
Tools tab. DD-4's authorization model presumes "the operator toggles it on the agent they bind"; today
the only affordance is default-all-on or raw config editing. Not a security hole (authorization is
enforced at `execute()` against live DB state regardless), but the deliberate-enablement premise has
no UI. Add a "Connectors" (or "Platform") category with the two checkboxes.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio.js:273-277` — `TOOL_CATEGORIES`
- Behavior-test run `tests/behavior/stub-connector-round-trip/runs/2026-08-31-22-43-08.md` — Executor
  precondition anomaly + Validator closing (spec's confirm-the-checkbox precondition unsatisfiable)
- Flight 2 flight-end review, deviation ruling 4 (non-blocking, Flight 3 or squawk)

## Corrective Action

Added a `'Connectors'` entry to `TOOL_CATEGORIES` in
`the_one/interfaces/web/static/js/areas/studio.js` (now `:273-284`),
listing `send_to_platform_channel` and `fetch_channel_history`, alongside
Filesystem/Execution/Web. `tools-tab.js` builds one category tile per
`TOOL_CATEGORIES` key generically (`Object.keys(TOOL_CATEGORIES)`, no
hardcoded category list), so no changes were needed there — the new
category renders through the same tile/checkbox/master-toggle/count-badge
machinery as the other three, and the checkboxes wire into the same
`enabled_tools`/`disabled_tools` save path (`collectFormData` in
studio.js) the backend already honors (Mission 23 Flight 2 registered
both tools unconditionally in `_TOOL_CLASSES`, so they're always present
in `allTools` — no backend change required).

Named the category `'Connectors'` per the report's suggestion. Noted in
a comment that this is distinct from the sidebar's `'Connectors'` NAV
SECTION (external connector configs, Mission 23) — same label, different
UI surface (a Tools-tab category tile vs. a top-level section) — to head
off confusion for a future reader.

No new `data-testid` values were introduced (the checkboxes use the
existing `data-tool` attribute pattern shared by every category), so
`docs/ui-testid-registry.md` needed no update. Confirmed the admin
Tools grid (`admin/tools-grid.js` / `admin/tools-editor.js`) has its own,
separately-scoped `TOOL_CATEGORIES` mirror that still lacks these two
tools (pre-existing "unknown" badge gap) — out of scope for this squawk,
which the report and evidence scope specifically to the per-agent Studio
Tools tab (DD-4's "operator toggles it on the agent they bind"); flagging
here for a future flight/squawk rather than expanding in place.

Updated the pre-existing hardcoded-count guard test
`tests/browser/test_flow_studio_tools_overrides.py::test_studio_tools_tab_renders_category_tiles`
(3 category tiles / 19 tool tiles → 4 / 21) and added two new tests:
`test_studio_connectors_category_renders_both_tools` (both checkboxes
render, checked, enabled, count badge reads "2 / 2 enabled") and
`test_studio_connectors_category_checkbox_toggle_round_trips_via_api`
(unchecking one, saving, and confirming via `GET /api/agents/{name}`
that it lands in `disabled_tools` — same enable/disable wiring as the
other three categories).

## Verification

- `ruff check tests/browser/test_flow_studio_tools_overrides.py` and
  `ruff format --check` on the same file — both clean (only Python file
  touched; the tools-tab change itself is JS, which this repo has no
  linter for).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio -x --timeout 30`
  → **145 passed, 3 skipped, 0 failed** in 252.89s (19 browser test
  files), including all 12 tests in `test_flow_studio_tools_overrides.py`
  (10 pre-existing + 2 new) — the updated tile/tool counts and the two
  new Connectors-category tests all green.
- Confirmed by reading `the_one/tools/builtins.py::get_tools` that
  `send_to_platform_channel`/`fetch_channel_history` are unconditionally
  present in `_TOOL_CLASSES` (no connector-configured gate), so they
  always populate `self._allTools` in studio.js regardless of whether
  any connector is configured on the instance — the new category tile
  is never silently empty.
- Backend/API surfaces untouched: `git diff --stat` shows only
  `studio.js` (TOOL_CATEGORIES addition), the browser test file, and
  this squawk file changed by this squawk's work (three other
  in-progress squawks' uncommitted changes on this branch were left
  alone per instructions).

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-01
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-01 batch commit (PR follows)

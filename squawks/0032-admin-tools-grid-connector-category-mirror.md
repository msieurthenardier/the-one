# Squawk 0032: Admin Tools grid's TOOL_CATEGORIES mirror lacks the connector tools

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: 2026-09-02

## Report

Squawk 0028 fixed the per-agent Studio Tools tab, but the Administration area's Tools grid
(`admin/tools-grid.js` / `admin/tools-editor.js`) keeps its own separate `TOOL_CATEGORIES`
mirror, which also lacks `send_to_platform_channel` and `fetch_channel_history` — they render
with an "unknown" badge there. Same class of fix: add the Connectors bucket to the admin
mirror (or better, note whether the two mirrors can share one source). Found during squawk
0028's implementation; deliberately left out of that squawk's scope (its report/evidence
named the per-agent tab only).

## Evidence

- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` / `tools-editor.js` — the mirror
- Squawk 0028's Corrective Action scope note (turnaround 2026-09-01)

## Corrective Action

Added a `connectors` bucket to both admin-side `TOOL_CATEGORIES` mirrors,
mapping `send_to_platform_channel` and `fetch_channel_history` to it —
mirroring squawk 0028's studio.js fix for the same two tools:

- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` — added
  the two entries to `TOOL_CATEGORIES` (now 21 tools across 4 buckets),
  appended `'connectors'` to `CATEGORY_ORDER` (so it renders as a 4th tab,
  after Filesystem/Execution/Web) and to `CATEGORY_LABELS` (`'Connectors'`),
  and updated the stale "19 tools" comment to 21.
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — added
  the same two entries to its own separately-duplicated `TOOL_CATEGORIES`
  mirror (the per-tool editor's `{description} · {category}` subtitle).

Unlike studio.js's Tools tab (which groups by tile + count badge only,
no per-category color), the admin grid renders a colored
`admin-tool-badge--{category}` chip per tool, so parity required two
more additions the studio-side fix didn't need — both following the
exact pattern the existing filesystem/execution/web categories already
established (extending an anticipated scaffold, not a new design):

- `the_one/interfaces/web/static/css/admin.css` — added
  `.area-admin .admin-tool-badge--connectors` alongside the other three
  category-badge rules.
- `the_one/interfaces/web/static/css/tokens.css` — added a
  `--badge-connectors` / `--badge-ink-connectors` token pair to both the
  dark and light theme blocks (same hex in both — theme-stable, like the
  provider badges, rather than per-theme-tuned like filesystem/execution/
  web). Chose `#0b5394` (steel blue, distinct from every existing badge
  hue) with white ink at 7.84:1 contrast — comfortably clears the
  project's 4.5:1 badge-ink AA gate with margin, so no per-theme tuning
  was needed. Mirrored the new pair into `tests/browser/design_tokens.py`
  (both `DARK`/`LIGHT` dicts, required by the CSS↔mirror lockstep guard)
  and added `("connectors", "badge_connectors", "badge_ink_connectors")`
  to `_BADGE_INK_PAIRS` in `tests/test_design_tokens_a11y.py` so the new
  pair is gated by the same per-badge contrast suite as every other
  badge, not left silently unaudited.

**On sharing one source (report's ask):** left as three separate,
now-consistent duplicates (studio.js, tools-grid.js, tools-editor.js) —
unifying them is a design question (shared module extraction, `agents.md`
already flags this in `tools-editor.js`'s existing comment) beyond this
squawk's bounded scope. Added a one-line cross-reference comment at each
of the three call sites noting the other mirrors exist, so a future
reader (or the flight/squawk that eventually unifies them) finds all
three from any one of them.

No backend change needed: both connector tools were already
unconditionally registered in `_TOOL_CLASSES` (confirmed by squawk 0028),
so they always populate the admin grid's tool list regardless of this
fix — the fix is purely the category mapping.

## Verification

- `ruff check` and `ruff format --check` on all touched Python files
  (`tests/browser/test_flow_admin_tools_grid.py`,
  `tests/browser/test_flow_admin_tools_editor.py`,
  `tests/browser/design_tokens.py`, `tests/test_design_tokens_a11y.py`) —
  clean (one file needed `ruff format` to reflow a wrapped `expect()`
  call). The JS/CSS files touched have no linter in this repo.
- `python -m pytest tests/test_design_tokens_a11y.py -q` → **139 passed**
  (includes the new connectors badge-ink pair, parametrized both themes).
- `python -m pytest tests/test_ui_guards.py -q -k mirror` → **1 passed**
  (CSS↔`design_tokens.py` mirror-sync guard, confirming the new tokens
  match their CSS source).
- Updated `tests/browser/test_flow_admin_tools_grid.py`: bumped the
  tab-count assertion (3→4) and tile-count assertions (9/6/4=19 →
  9/6/4/2=21) in the two existing count-guard tests, and added
  `test_admin_tools_connectors_tab_renders_both_tools_with_connectors_badge`
  confirming both tools render under the Connectors tab with the
  `connectors` badge (not `unknown`).
- Updated `tests/browser/test_flow_admin_tools_editor.py`: added
  `test_editor_connector_tool_shows_connectors_category` confirming the
  per-tool editor's category subtitle for `send_to_platform_channel`
  reads `connectors`, not `unknown`.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane system -x`
  (foreground, no timeout override needed — completed in ~167s) →
  **108 passed, 0 failed** (10 browser test files), including all 20
  tests in `test_flow_admin_tools_editor.py` (19 pre-existing + 1 new)
  and all 11 in `test_flow_admin_tools_grid.py` (10 pre-existing + 1 new).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio` run
  twice (foreground) to check the one JS file shared with squawk 0028
  (studio.js, comment-only change there): 146/150 + 3 skipped + 1 failed
  on the first run, 149/150 + 3 skipped... — a *different* unrelated test
  failed each run (`test_flow_studio_mcp_editor.py::test_create_stdio_source`
  once, `test_flow_agent_tabs.py::test_enter_commits_focused_tab` the
  other time; neither touches tool categories). Confirmed pre-existing
  and unrelated to this squawk: re-ran the first failing test in
  isolation with my changes present (passed) and again with all my
  changes fully `git stash`ed (also passed) — an order-dependent flake
  in the studio lane's own environment, not a regression from this fix.
  `test_flow_studio_tools_overrides.py` (studio's Connectors-category
  coverage from squawk 0028) passed 12/12 in both runs, confirming the
  cross-reference comment added to studio.js's `TOOL_CATEGORIES` didn't
  disturb that object literal.
- `git diff --stat` confirms only the files listed above (plus this
  squawk artifact) changed; no backend/API surfaces touched.

## Sign-Off
**Reviewer**: independent batch Reviewer (Haiku), squawk/turnaround-2026-09-02
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-02 batch commit (PR follows)

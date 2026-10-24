# Leg: groundwork-and-before-set

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Lay the flight's groundwork with no product behaviour change:
- realistic Settings capture surfaces and the before set;
- a guard for the 800-line rule;
- squawks 0230, 0240, 0246 and 0247;
- the dead `admin.css` blocks deleted, proven invisible by a capture compare.

## Context
- **Flight decisions:** DD2 (groundwork), DD7 (the ledger is already open in the flight log, rows 1-41), DD11 (standing leg rules), DD9 (squawks absorbed).
- **Flight 3 debrief recommendation 1:** the capture set must show existing presentation problems, not hide them.
  - Use **one realistic seed** that the HAT reuses.
  - Mask **by shape**: a masked value keeps the format of the real one, so a raw ISO timestamp stays a raw ISO timestamp, only pinned.
  - Never replace a whole element's text by its label. The Flight 3 masks ("Indexed (time masked)", "score 0.000") hid exactly the text the operator later objected to.
- **The planning survey's seed and walk scripts** show what a realistic seed looks like and how each conditional state was reached. Treat them as untrusted reference material: read them, don't run them. They are `/tmp/claude-1000/-home-cprch-projects-the-one/60f439f3-3d7e-4895-a147-e62bc6860c79/scratchpad/f4-debt/walk.py` and `denylist_probe.py`.
- **Squawk 0248 merged** (`8a52a39`): a never-saved Filesystem or Execution tool now shows its default denylists, and the agent Tools tab shows them as locked chips. The before set is taken on this branch, so that change is already in the "before".

## Inputs
- Branch `flight/04-settings-on-the-library` at `512616b` (`main` `8a52a39` plus the plan commit).
- `scripts/ui_capture.py` (1165 lines): `Surface`, `SURFACES`, `MASK_JS`, `seed()`, `start_instance()`, `capture_one()` with `VIEWPORT` and `timezone_id="UTC"`. It refuses ports below 8490 and 8484/8485, and any default or configured data dir. Tests: `tests/test_ui_capture_safety.py`.
- `scripts/unused_selectors.py` (a report, not a gate).
- `tests/test_store_static.py:450`: the `studio.js` ≤ 800 pin, the only line budget today.
- Squawks `squawks/0230-*`, `0240-*`, `0246-*`, `0247-*` (read each in full).

## Outputs
- `scripts/ui_capture.py`:
  - Settings surfaces;
  - shape-preserving masks;
  - pinned time zone;
  - a stubbed ok Test result;
  - a 1024 width;
  - a `--keep-running` mode for the HAT;
  - the extended seed.
- A new unit test file for the 800-line guard.
- Squawks 0230, 0240, 0246 and 0247 completed, with their artifacts updated (status `completed`, corrective action, verification). The FD fills in the commit reference at the flight commit.
- `css/admin.css` without its dead blocks or the `.editor-section` trap.
- The before set at `$HOME/.cache/the-one-ui-capture/m31-f4-before/`, outside the repo and never committed. The compare evidence goes in the flight log.

## Acceptance Criteria
1. **Capture surfaces.** `ui_capture.py --list` shows a surface for each Settings state below, and each is captured in light and dark at 1280×900 **and** 1024×768:
   - Appearance;
   - Date and time:
     - system mode;
     - zone mode with the list showing;
     - a search with results;
     - the mismatch hint (browser zone ≠ effective zone);
   - Prompts (full page);
   - Encryption:
     - default;
     - armed;
     - a staged-warning result (stubbed route);
   - Built-in tools grid: the Filesystem and Execution tabs, with at least one tool disabled globally;
   - Tool editors:
     - `read_file`, with a 97-character allowlist path, a custom read size and the default denylist;
     - `delete_file` (the shared Filesystem fields);
     - `shell`;
     - `fetch_url`, with a validation error showing;
     - `fetch_url` Test refused, and Test ok (stubbed with `page.route`, like `provider-test-ok`; a real fetch cannot succeed under netns);
     - `web_search` with SearXNG selected (the `show_if` reveal);
     - `current_time` (no configuration);
   - Knowledge indexing:
     - default (seeded non-default values);
     - invalid (a field error showing);
     - saved.
2. **Surfaces outside Settings** that later legs change are in the before set: `connector-edit`, the `kb-*` surfaces, `plan-signin-awaiting-code`, `agent-self-configuration` and `agent-tools` (Filesystem overrides open, now showing the default denylist chips).
3. **Deterministic environment.**
   - The scratch instance's environment carries an explicit `TZ` (for example `TZ=America/Chicago`), so the server's system zone (tzlocal) is pinned.
   - The seed sets the time zone through `PUT /api/time-settings` in `mode: "zone"`. A surface that needs system mode sets it explicitly.
   - The browser's `timezone_id` stays pinned per surface. The mismatch surface uses a browser zone that differs from the seeded zone.
4. **Shape-preserving masks.** Every mask replaces a run-to-run value with a fixed value of the same shape, never a label:
   - a timestamp keeps its format;
   - a duration keeps its unit;
   - a score keeps its digits;
   - a pairing code keeps its pattern.

   The existing Library masks (`MASK_JS` `SETS`) are converted the same way, so text such as "Expires 2026-…T…Z" stays visible in its real format. The run-id path pin stays. A short comment states the rule.
5. **`--keep-running`** starts the scratch instance, seeds it and prints the URL, port, data dir and PID, then exits without stopping the instance. The FD reuses that seed for the HAT. All the existing safety refusals still apply, and `tests/test_ui_capture_safety.py` covers the new flag (it is refused with the same port and data-dir rules).
6. **The before set** is taken on this branch after criteria 1-5, into `$HOME/.cache/the-one-ui-capture/m31-f4-before/`. The flight log records the count of PNGs and the command used.
7. **The 800-line guard.** A new unit test (`tests/test_area_module_size.py`) checks every `the_one/interfaces/web/static/js/areas/**/*.js`.
   - It fails when an unlisted file is over 800 lines.
   - Each allowance entry is a ceiling: a listed file fails when it exceeds its ceiling, and a listed file at 800 lines or fewer also fails, naming the entry to remove.
   - The allowance today: `chat.js`, `mcp-server-editor.js`, `provider-models.js`, `knowledge-folders.js` and `provider-editor.js`, each at its current line count.
   - A comment explains the rule and points at the mission criterion.
   - The `studio.js` pin in `tests/test_store_static.py:450` stays.
8. **Squawk 0230:** `test_filter_keystroke_cost_ratio_60_vs_10_throttled` asserts `m60 <= max(3 * m10, 0.25)` (an absolute floor of 0.25 ms), and measures more work per sample. Raise the repeat count, or the work per keystroke, so `m10` sits well above the timer resolution. Record the before and after medians in the squawk.
9. **Squawk 0240:** every browser test that toggles `App.ui.toggle` through `label.ui-toggle-label` uses a role locator instead (`get_by_role('switch', name=…)` with `set_checked`/`check`). `git grep -n "ui-toggle-label" tests/` returns nothing outside contract tests of the toggle itself.
10. **Squawk 0247:** the `knowledge` budget is 360 in `scripts/run-tests.sh`, and CLAUDE.md's lane table reads 360 / 279.
11. **Squawk 0246:** every item in its Evidence is fixed, plus the reconnaissance additions:
    - `docs/ui-control-inventory.md` `:46` also no longer lists `self-configuration-tab.js` as hand-built (it uses `copyField`);
    - `:98` no longer lists `agent-editor.js` or `knowledge-shared.js` `_breadcrumb()` as hand-built.

    Comments and docs only, no code change.
12. **Dead `admin.css`**, deleted **after** the before set: `.admin-note`, `.admin-section` (with `:first-of-type`), `.admin-placeholder*`, `.area-studio .mcp-source-tile-subtitle*`, `.tools-editor-test-help`, `.date-time-mismatch .btn`, and the `.area-admin .editor-section` gutter (`admin.css:17-22`).
    - Each is confirmed unused by `scripts/unused_selectors.py` and a `git grep` over `the_one/interfaces/web/static/` and `tests/`, pasted into the flight log.
    - Then a second capture run of the Settings surfaces into `$HOME/.cache/the-one-ui-capture/m31-f4-dead-css/` matches the before set pixel for pixel. The compare is done with PIL, a small scratch script outside the repo, and its result goes in the flight log.
    - Any difference means that block was not dead: restore it and record why.
13. **No product behaviour change.** No JS under `static/js/` changes, and the only CSS change is criterion 12.

## Verification Steps
- `.venv/bin/python scripts/ui_capture.py --list` shows the new surfaces.
- `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f4-before` succeeds. A spot check of 3 PNGs (Read them) shows unmasked raw-format values.
- `.venv/bin/python -m pytest tests/test_area_module_size.py tests/test_ui_capture_safety.py tests/test_store_static.py tests/test_run_tests_lanes.py -q -x --timeout 120` passes.
- Falsify the guard: temporarily add 1 line over a ceiling to a scratch copy (or monkeypatch the allowance), show that it fails, then revert. Record this in the flight log.
- 0230: run the scale test file alone twice under netns. 0240: run the lanes whose files changed (expect `library`, `knowledge`, `agents` and `shared`; list them with `git grep`), sequentially, under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`. Run at most 3 lanes at once, and never alongside the unit suite.
- The static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_ownership.py`) pass after the CSS deletion.
- `ruff check` and `ruff format --check` on `scripts/` and `tests/`.
- `make test-unit` once at the end.

## Implementation Guidance
1. **Re-verify the environment first:** WebKit userland (`bash scripts/setup-webkit-userland.sh` if needed) and `THE_ONE_TEST_NETNS=1` (`unshare -rn` works).
2. **Capture tool.**
   - Read `ui_capture.py` end to end, and follow its existing patterns (`Surface`, `prepare`, `stubs`, `shot`, the full-page tall viewport).
   - Add a width option, or capture each surface at both widths, with distinct file names.
   - Extend `seed()` behind a function the `--keep-running` mode shares. Seed tool configs through `PUT /api/tools/configs/{name}`, global disables through the same route, Knowledge indexing through `PUT /api/knowledge-settings`, and the time zone through `PUT /api/time-settings`. Read the routes in `the_one/interfaces/web/api.py`.
   - Stub, rather than perform, anything destructive or network-bound: the Encryption staged result and the Test routes.
   - **Never run a real encryption rotation against shared state.** The scratch instance is disposable, but stub the staged state with `page.route`.
3. **Masks:** rewrite `MASK_JS` as shape-preserving regex replacements over text nodes, scoped to known containers, and keep the MutationObserver.
4. **Take the before set** (criterion 6).
5. **Guard test** (criterion 7).
6. **Squawks 0230, 0240, 0247 and 0246.** For each, set the squawk status to `in-progress` when you start, and write its Corrective Action and Verification. Set it to `completed` with the date; leave the Sign-Off commit as "flight/4 leg 01 commit". Do not commit.
7. **Dead CSS** (criterion 12), then the compare run.
8. **Append to the flight log:** a Leg Progress entry with the counts, the commands, the compare result and the guard falsification. Append ledger rows only if something visible changed (expected: none).

## Edge Cases
- **A full-page Settings capture** scrolls inside `.admin-content`, not the window. Use the tool's tall-viewport approach, and check that the bottom of Prompts and of the tool editors is in frame.
- **The Date and time list's scroll position** differs between runs unless the selected zone is pinned. Seed a fixed zone.
- **The theme picker** saves to `localStorage`. A fresh browser context per surface keeps the themes independent (the existing behaviour; confirm it).
- **A "dead" rule that only matches inside a state not in the capture set** (for example `.date-time-mismatch .btn`) is proven dead by the selector grep. The compare alone is not enough, so paste both.
- **If a lane fails** in a file this leg did not touch, re-run it in isolation (gate-flake triage). Record known flakes (squawks 0229, 0216) and don't fix them here.

## Files Affected
- `scripts/ui_capture.py`, `tests/test_ui_capture_safety.py`.
- `tests/test_area_module_size.py` (new).
- `tests/browser/test_flow_agents_scale.py` (0230).
- The browser test files `git grep "ui-toggle-label" tests/browser` finds (0240).
- `scripts/run-tests.sh`, `CLAUDE.md` (0247).
- `the_one/agents.md`, `docs/ui-control-inventory.md`, `static/js/areas/studio/knowledge-folders.js` (comments only), `static/css/studio.css` (the comment and the duplicate rule) (0246).
- `static/css/admin.css` (dead blocks).
- `squawks/0230-*`, `0240-*`, `0246-*`, `0247-*`.
- The flight log.

## Citation Audit
Checked at `512616b`:
- `ui_capture.py` symbols `Surface` `:214`, `MASK_JS` `:309`, `start_instance` `:712`, `seed` `:769`, `capture_one` `:934` with `timezone_id="UTC"` `:939`: verified.
- `test_flow_agents_scale.py:113` `assert m60 <= 3 * m10`: verified.
- `run-tests.sh:66` `[knowledge]=300`: verified.
- `admin.css:17-22` gutter: verified (FD read at planning).
- `test_store_static.py:450`: verified.
- `studio.css:799/:810` duplicate: from the recon, not re-read. The Developer confirms it.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

# Leg: groundwork-and-before-set

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Land the flight's shared groundwork with no product-code change:
- split the `contracts` browser lane;
- replace the exact script-count pin (squawk 0233);
- document the editor contracts and pin the studio `state` key set (squawk 0235);
- add an unused-selector report script;
- extend the capture tool with the Library surfaces and take the before set;
- open the visible-differences ledger.

## Context
- Flight DD2 (groundwork) and DD11 (standing leg rules). DD1 says Flight 4 (Settings) starts on this groundwork too.
- Flight 2 debrief recommendations 1 (split `contracts`, past its ~1000-test threshold), 2 (write the editor contracts down) and 5 (the script-count pin) are applied here.
- **No file under `the_one/interfaces/web/static/` changes in this leg.** The before captures must show today's UI.

## Inputs
- `main` at `08562ec` plus the planning artifacts, on branch `flight/03-knowledge-and-connectors-on-the-library`.
- `scripts/run-tests.sh`:
  - `LANE_LIST` / `CANON_LANES` (`:54-55`);
  - the budget table (`[contracts]=480`, `:68`);
  - `contracts_pat=('test_ui_*')` (`:201`);
  - the lane `case` (`:213-231`, with the aliases `chat|studio|system`);
  - `--help` (about `:78`);
  - the unknown-lane message (`:443`).
- `tests/test_run_tests_lanes.py` (14 tests: lanes pairwise disjoint, union = every browser file except the pixel file, the budget table covers each canonical lane once, parallel exit codes).
- `ci/tasks/browser.yml:13` (a comment naming the `contracts` lane; the task runs `--parallel 1` over the canonical lanes, so no lane list lives there).
- `tests/test_index_asset_cache_busting.py:99`, `assert len(refs) == 93`, with a long history comment above it (about `:52-96`).
- `scripts/ui_capture.py`:
  - `SURFACES` (`:305`, `:316-…`), `seed()` (`:547`), `seed_tabs_agent()` (`:581`), `capture_one()` (`:659`);
  - the safety rules (`check_capture_safety`, `:129`): ports ≥ 8490, never 8484/8485, a scratch data dir under `$HOME`, `--out` outside the repo.
- `the_one/agents.md`:
  - "Studio area modules (M31 F2 L02a)" (about `:2101`);
  - "Control library (`App.ui`)" (about `:2027`);
  - "UI test apparatus" (about `:1977`).
- Squawks `squawks/0233-index-script-count-pin.md` and `squawks/0235-document-agent-editor-contracts.md` (both open).

## Outputs
- **The contracts lane split.** `scripts/run-tests.sh` has two canonical lanes in place of `contracts`:
  - **`contracts-overlay`**, an explicit list: `test_ui_modal*`, `test_ui_menu*`, `test_ui_rail*`, `test_ui_list_pane_chats*`, `test_ui_search_list*`, `test_ui_drawer*`, `test_ui_nav_groups*`, `test_ui_confirm*`, `test_ui_focus_after*`, `test_ui_dialog_rule*`, `test_ui_modal_dialog_rule*`, `test_ui_dialog_scroll*`. Match the real file names; check them with `ls tests/browser/test_ui_*`.
  - **`contracts-controls`**: `test_ui_*` minus that list.
  - **`contracts`** stays an alias for their union, like `studio`.
  - The canonical lane count is 11. The budgets come from a full `--parallel 3` run.
  - `--help` and the unknown-lane message list the new lanes and the alias.
- **Pins and docs follow the split:**
  - **`tests/test_run_tests_lanes.py`** still pins pairwise disjointness, the union and the budget table. The hard-coded spots to change are:
    - the `LANES` tuple (about `:33`);
    - `test_contracts_lane_is_exactly_the_ui_contract_files` (about `:81`, which indexes `lanes["contracts"]`; keep it, now asserting the two lanes' union);
    - the literal `LANE_LIST` string (about `:97`);
    - any lane-count, budget or wording assertions;
  - **`scripts/run-tests.sh`:** the `shared` complement uses `contracts_pat`, so replace it with both new patterns. The `contracts)` alias goes in `resolve_lane`, not in `CANON_LANES`, so `--parallel` never runs it twice. Also update the header comments (about `:23`, `:29`);
  - **CLAUDE.md:** the lane list, the `--lane contracts` example (about `:355`, which still works as an alias; add the two new lanes), the budget table (about `:371`), the lane bullets and "nine named lanes" (about `:392-393`), and "ten lanes"/"all eight lanes" (about `:395`, the latter already stale);
  - **`ci/tasks/browser.yml`:** the comment at `:13` and "first eight"/"ninth" (about `:8-10`);
  - **`the_one/agents.md`:** only "nine lanes" (about `:173`). Its "contracts lane" mentions stay valid because `contracts` stays an alias.
- **Balance.** `test_ui_listener_cleanup.py` stays in controls. If the first `--parallel 3` run shows the two lanes badly unbalanced (one more than 1.5× the other), move whole files to rebalance and record it.
- **Squawk 0233.** `tests/test_index_asset_cache_busting.py` no longer pins the exact count. It asserts:
  - (a) every `/static/…js|css` ref in the served `index.html` exists on disk under `static/`;
  - (b) each carries exactly one `?v={__version__}` (as today);
  - (c) the relative load order of the `.js` refs only (the regex also matches `.css`, so filter it), not adjacency, since non-ui scripts such as `app.js`, `router.js` and `store.js` sit between the groups:
    - `js/ui/core.js` before every other `js/ui/*.js`;
    - every `js/ui/*.js` before any `js/areas/**`;
    - every `js/areas/studio/*.js` before the shell `js/areas/studio.js`, and every `js/areas/chat/*.js` before `js/areas/chat.js`. The shells load last (`index.html` about `:77`, `:110`) and read `window.App.<area>.*` at call time;
  - (d) no duplicate refs.

  The history comment collapses to one line that points to the git log. The squawk is set to `completed` at the flight commit, with its corrective action and verification written in.
- **Squawk 0235.** A new `the_one/agents.md` subsection, "Editor contracts (M31 F3 L01)", under the studio modules section:
  - **the tab-handle contract,** as the code stands:
    - `destroy` is required of every tab that holds listeners or controllers: knowledge, mcps, tools and self-configuration;
    - General (`renderGeneralTab` returns its controls plus `setAgent`/`applyStored`/`setStoredChangeNote`/`setTestResult`/`clearTestResult`, no `destroy`) and Rules and notes (`renderRulesNotesTab` returns nothing) are **known exemptions**, each with its reason;
    - `agent-editor.js`'s `h.destroy` calls only `selfConfig.destroy()` and `tabs.destroy()`. Document that as found and say which tabs it should cover;
    - `setAgent`, `deactivate`, `setSources`, `applyStored` and `setStoredChangeNote` are optional, each with what calls it. Rules and notes deliberately has no `setAgent`;
  - **the `App.ui.util.mountSlot()` lifecycle,** the real API from `ui/core.js` (about `:73-115`): `mount(destroyFn, data)` returns a token; `isCurrent(token)`; `current()`; `release(token)`; `destroy()`. Include the late-binding rule. Mounting a new one destroys the previous one first, and async results check `isCurrent(token)`. The studio `editorGen` counter is a separate thing;
  - **the studio `state` object's fields,** each with its owner;
  - **the hidden-editor patch:** `_activeSection` stays `'agents'` on Chats and Settings, so a self-configuration write patches the hidden editor in place (accepted; cross-reference squawk 0232).

  Plus one new unit-tier file, `tests/test_studio_editor_contracts_static.py`, with two checks:
  - **The `state` key set, by static parse.** `state` is a closure-local `var state = {…}` inside `init` (`studio.js` about `:89`), which a unit test cannot reach. Parse the object literal's top-level keys, brace-balanced and skipping comments; today there are 21. Also grep `state\.(\w+)\s*=` across `studio.js` and `studio/*.js`, and fail on a written name that is not in the literal.
  - **The tab `destroy` check,** static over the tab modules' returned objects. A tab returning a handle without `destroy` fails, except for the explicit allow-list `{general, rules-and-notes}`, each entry with its reason.

  The squawk is completed at the flight commit.
- **`scripts/unused_selectors.py`** (new; a developer tool, not a gate):
  - `python scripts/unused_selectors.py <stylesheet.css> [...]` prints each class token defined in those stylesheets that has no user;
  - it searches `the_one/interfaces/web/static/js/**` (comments stripped), `static/index.html`, the *other* stylesheets and `tests/`;
  - class names built at runtime are matched as prefixes from a small list in the script (`indicator-led--`, `connector-setup-steps-list-`, `ui-menu-align-`, `chip--`, `badge--`; extend it from a grep for `'…--' +` and `'…-' +` concatenations), or listed under "dynamic: check by hand";
  - exit code 0 always.

  A smoke unit test, `tests/test_unused_selectors_script.py`, runs it over a tiny fixture: one used, one unused and one dynamic-prefixed class, in `tmp_path`.
- **`scripts/ui_capture.py` gains the Library surfaces** (DD2). Each surface is named with `--list`, and both themes are captured as today:
  - `library-start` (the start page);
  - `kb-new`;
  - `kb-detail` (folder expanded with items), `kb-item-menu` (the menu open), `kb-chunks`, `kb-source`, `kb-search` (hits), `kb-status` (after a re-index), `kb-danger-armed`;
  - `connector-new` (stub type);
  - `connector-edit` (with the pairing result, the doctor result and two channel-map rows).

  How they work:
  - **The seeder** creates a knowledge base and registers a scratch folder of 3-4 small text files created under the capture's scratch home, beside its scratch data dir and never inside it (a folder inside the data dir is refused with 422). It waits for indexing to finish (poll `GET /api/knowledge-bases/{id}/status` with a timeout) and creates a stub connector with a channel map.
  - **The stub connector** type needs `THE_ONE_STUB_TEST_ENDPOINT=1` with dev mode on the capture instance. `start_instance` (`ui_capture.py` about `:497-501`) strips every `THE_ONE_*` var and then sets `DATA_DIR` and `DEV_MODE`. Add `env["THE_ONE_STUB_TEST_ENDPOINT"] = "1"` there, in that instance env only.
  - **Run-to-run text is frozen or masked** before the screenshot, through the existing `_patch_*`/route or evaluate hooks: `Indexed:` timestamps, search scores, the watch state and the pairing code.
- **The before set** is taken and recorded in the flight log: its directory (`$HOME/.cache/the-one-ui-capture/m31-f3-before/`), surface count, both themes, and the git sha it was taken at.
- **The flight log's ledger** is open (it exists from planning). This leg adds a "no visible change" row.

## Acceptance Criteria
- [ ] `bash scripts/run-tests.sh --lane contracts-overlay --list` and `--lane contracts-controls --list` list disjoint file sets whose union equals `--lane contracts --list`, which is every `tests/browser/test_ui_*.py`. Every file in the overlay list exists.
- [ ] `bash scripts/run-tests.sh --parallel 3 --plan` shows 11 canonical lanes, with budgets for both new lanes, and `--help` names the `contracts` alias.
- [ ] `tests/test_run_tests_lanes.py` passes and pins the two new lanes (disjointness, union, budget rows).
- [ ] `tests/test_index_asset_cache_busting.py` no longer contains `len(refs) ==` and asserts existence, the single `?v=`, no duplicates and the load order. It fails if a referenced script is missing or if a `js/areas/` script is moved above `js/ui/core.js`. Try both by monkeypatching the served body the test reads through `TestClient`, then revert.
- [ ] `the_one/agents.md` has the "Editor contracts" subsection covering the four parts above.
- [ ] The `state` key-set pin and the `destroy` check exist and pass. Each fails when a key is added or removed, or when the knowledge tab's `destroy` is deleted: try once and revert.
- [ ] `python scripts/unused_selectors.py the_one/interfaces/web/static/css/studio.css` runs and prints a report, and its smoke test passes.
- [ ] `python scripts/ui_capture.py --list` shows the eleven new surfaces, and a capture run writes light and dark PNGs for each to the before directory. The flight log records the path, count and sha.
- [ ] No file under `the_one/interfaces/web/static/` is changed (`git diff --stat -- the_one/interfaces/web/static` is empty).
- [ ] `make test-unit` passes. Expect 12 skipped off netns, or 14 under netns; read `-rs` if the count differs.
- [ ] **Budgets for the two new lanes** come from a full `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short` run, which must exit 0 (`PARALLEL_RESULT rc=0`). Each budget is its lane's wall time plus 25%, rounded up to 30 s; record them in `scripts/run-tests.sh` and CLAUDE.md. Lanes over budget are reported, not fixed here.

## Verification Steps
- The lane commands above; `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_run_tests_lanes.py tests/test_index_asset_cache_busting.py tests/test_unused_selectors_script.py -x --timeout 60` plus the new pin tests.
- Read the `agents.md` section.
- `python scripts/ui_capture.py --list`; the capture run (with `THE_ONE_TEST_NETNS=1` if the tool's netns re-exec needs it); `ls` the before directory.
- `git diff --stat -- the_one/interfaces/web/static` is empty.
- `make test-unit`, then the full `--parallel 3` run.

## Implementation Guidance
1. **The lane split first.**
   - Add the two lanes to `LANE_LIST`, `CANON_LANES` and the budget table, with interim budgets (overlay 240, controls 300) that are corrected after the parallel run.
   - Overlay pattern array: `contracts_overlay_pat`. Controls are the expansion of `test_ui_*` minus the overlay files, filtered like `shared`'s complement or `agents`' minus-lists in the script. Copy that idiom; do not invent a new one.
   - Keep `contracts` as an alias, like `studio`.
   - The `shared` complement must exclude both new lanes.
   - Update `tests/test_run_tests_lanes.py`.
2. **Squawk 0233:** rewrite the test as specified. Check the real order in `static/index.html` before pinning (c).
3. **Squawk 0235:** read `studio.js` (`state` construction), `agent-editor-controller.js`, `agent-editor.js` (tab mounting) and `ui/core.js` (`mountSlot`), then write the section and the two checks.
4. **`scripts/unused_selectors.py`** and its smoke test.
5. **Capture surfaces.**
   - Follow the existing `Surface` entries and seeders.
   - The KB detail route is `#library/knowledge/{id}`, the connector route `#library/connectors/{id}`, the new forms `…/~new`.
   - For the menu, chunks, source, search and armed states, use pre-capture actions like `_mcps_expanded`/`_tools_override_open`.
   - Run the before set, then record it in the flight log.
6. **The full parallel run;** set the two budgets from it.
7. **Flight log:**
   - in-progress lines at each step (DD11);
   - the leg entry;
   - the ledger row "01 | none | no visible change | DD2".

## Edge Cases
- **WebKit under netns:** `THE_ONE_REQUIRE_WEBKIT=1` applies to both contract lanes. Re-verify that WebKit launches before the run (`bash scripts/setup-webkit-userland.sh` if needed).
- **Indexing in the capture seeder** uses the bundled local embedding model. Allow up to about 60 s, and fail loudly with the status JSON if it does not finish.
- **The stub connector endpoint flag** must be set only on the capture's own scratch instance, never on 8484 or 8485.
- **The `--plan` budget order** is longest first. The new lanes' interim budgets only affect scheduling.
- **Unit-tier rules:** a new test must not call `ensure_schema`/`init_db` directly.
- **`unused_selectors.py` parsing:** strip `/* */` comments from the CSS before extracting class tokens, and take class names from within `:not(...)` and compound selectors correctly.

## Files Affected
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, `CLAUDE.md`, `ci/tasks/browser.yml` (comment)
- `tests/test_index_asset_cache_busting.py`
- `the_one/agents.md`, plus the new pin tests (path at the Developer's choice under `tests/`)
- `scripts/unused_selectors.py`, `tests/test_unused_selectors_script.py`
- `scripts/ui_capture.py`
- The flight log

## Citation Audit
Checked at `08562ec` on 2026-10-22, and corrected at the design review (Sonnet Developer, cycle 1: approve with changes; the `mountSlot` API, the real load order, the tab `destroy` exemptions, the `state` keys, and the lane-test hard-coded spots):
- `run-tests.sh:54-55,68,201,213-231,443` (FD grep);
- `test_index_asset_cache_busting.py:99` (FD read);
- `ui_capture.py:129,305,547,581,659` (FD grep);
- `agents.md:1977,2027,2101` (FD grep);
- `ci/tasks/browser.yml:13` (FD grep).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

# Flight Log: Regression-Net Foundation

**Flight**: [Regression-Net Foundation](flight.md)

## Summary

Leg 1 (testid-registry-and-guards) landed: testid registry + guard test suite in place; unit-tier regression guards active for testid↔source sync and the innerHTML dynamic-sink freeze.

Leg 2 (reenable-skipped-browser-modules) landed: all five module-skipped browser test modules re-enabled and passing — zero module-level skips remain in `tests/browser/`. The two "hang" modules were root-caused (empty-state CSS hides the header create CTA; locator swap to the `-empty` variant) rather than deferred. Full browser suite green: 532 passed, 0 failed.

Leg 3 (perf-baseline-and-apparatus-proof) landed: pre-redesign perf baseline captured via goldfinch MCP against the live instance and committed as `missions/17-ui-redesign/perf-baseline.md` (heap +6.55% over the M08 150-transition procedure — under the ≤20% budget; byte-precise readings). `studio-smoke.md` apparatus lines updated to goldfinch. Precondition-readiness check: **NOT satisfied** — the "Discord Constellation" connector no longer exists on the live instance (see the leg's readiness note); FD decision needed before the proof run.

Leg 4 (unit-tier-stabilization) landed: the `test_lifespan_drains_session_registry` ordering flake is root-caused and fixed (tests that drive the real app lifespan via `with TestClient(app)` left the process-global `_shutting_down` latch set; offenders now reset it, and `test_lifespan.py` clears defensively at setup), the six pre-existing ruff-format drift files are reformatted (verified format-only via AST equality), and CLAUDE.md documents `TEST_TIMEOUT=3600` for full browser-suite runs. `make test-unit` green twice consecutively (3681 passed / 0 failed each run); `ruff format --check` + `ruff check` clean tree-wide.

---

## Leg Progress

### testid-registry-and-guards

**Status**: landed
**Started**: 2026-07-03 09:40 CDT
**Completed**: 2026-07-03 10:25 CDT

#### Changes Made

- Created `docs/ui-testid-registry.md` — parse-friendly registry with three tables: 185 literal testids, 46 parametric prefix families, 4 manual exceptions (variable-carried ids: `create-and-test-connector-btn`, `save-connector-btn`, `connector-continuation-input`, `connector-idle-timeout-input`). Surface column (chat/studio/admin/shell) derived from defining file paths. Header states the sync contract and how to update.
- Created `tests/_ui_guard_helpers.py` — extraction module: testid extractor (attr-form + setAttribute-form literals; setAttribute-concat + parametric-in-HTML-string prefixes; selector references collected separately and excluded from "defined"), statement-joining sink classifier (`.innerHTML`/`.outerHTML` assignments + `insertAdjacentHTML` calls; static single-string-literal payloads exempt), registry-doc table parser. Handles the `provider-card`/`data-id` false-parametric case by anchoring to the attribute's own quoted value.
- Created `tests/test_ui_guards.py` — five unit-tier tests (unmarked, so they run in `make test-unit` and existing Concourse lanes with no new CI plumbing): source→registry sync, registry→source sync (incl. duplicate-row detection), manual-exception ids still present as string literals, selector-referenced ids resolve to a definition (with `KNOWN_DEAD_SELECTORS` allowlist), and the frozen dynamic-sink baseline (95 dynamic sites across 30 files at freeze; 65 static sites exempt; per-file snippet multiset match so offsetting add+remove is caught; removals never fail — ratchet only tightens).
- Updated `missions/17-ui-redesign/mission.md` Known Issues with the `connector-test-status` dead-selector disposition.

#### Verification

- `.venv/bin/python -m pytest tests/test_ui_guards.py -x --timeout 60` → 5 passed.
- Probe 1: added `data-testid="zz-probe-id"` to `general-tab.js` → `test_testids_in_source_are_registered` failed naming `zz-probe-id` and the file; reverted.
- Probe 2: added `panel.innerHTML = zzProbeVar;` to `general-tab.js` (file already in baseline — exercises snippet-level detection, not just the new-file path) → `test_no_new_dynamic_innerhtml_sinks` failed naming file + snippet; reverted. `git status` confirms no product-JS changes remain.
- `ruff check` clean on the tree; `ruff format --check` clean on both new files.
- `make test-unit`: 3680 passed, 10 skipped, 1 failed — the failure is a pre-existing flake unrelated to this leg (see Anomalies).

#### Notes

- Extractor bootstrap ground-truthed (authoritative per leg guidance): 185 literal ids, 46 parametric prefixes, 46 selector-referenced ids, 160 sink write sites → 95 dynamic / 65 static (static count matches the leg's calibration exactly). The leg's Citation Audit figures (166 literal / 168 sites / 103 dynamic) were indicative; the bootstrap numbers are the frozen baseline.
- Comments are classified like live code per the leg's edge-case decision (e.g. the design-language markdown-section code sample and comment-interrupted assignments in modal/status/surfaces sections appear in the dynamic baseline).

---

### reenable-skipped-browser-modules

**Status**: landed
**Started**: 2026-07-03 10:05 CDT
**Completed**: 2026-07-03 11:35 CDT

#### Changes Made

- **Root-cause class** (`test_flow_agent_crud.py`, `test_flow_provider_setup.py`): removed module skips; confirmed the recorded failure live (header `new-provider-btn` resolved but `element is not visible`, 58 retries × 500ms), matching the design-review-verified root cause — `components.css:719` hides the header `.new-entity-btn` via `display: none` whenever the entity grid is empty. Fixed with a locator swap to the in-canvas `-empty` variant (`new-agent-btn-empty` / `new-provider-btn-empty`) at empty-state click points. Header comments rewritten from "root cause unidentified" to the actual mechanism, including the empty↔populated variant-flip boundary rule. Softened the brittle exact-class assertion (`to_have_class("studio-editor is-hidden")` → regex on `\bis-hidden\b`).
- **Rewrite class**:
  - `test_flow_provider_grid.py`: rewritten against post-rebrand markup. The empty-state header-CTA assertion (guaranteed fail per `components.css:719`) split into two state-explicit tests: empty state asserts header CTA attached-but-hidden + `-empty` CTA visible; populated state (`app_with_provider`) asserts header CTA visible + `-empty` gone. The "+ New Provider navigates" test likewise split per variant. Module docstring documents which variant each test asserts. 11 tests.
  - `test_studio_mcps_tab.py`: rewritten from the retired `<details class="tool-row-overrides">`/`[open]` shape to the current `.mcp-source-tile` shape — expansion via `mcp-source-expand-{id}` button + `aria-expanded` on `mcp-source-row-{id}` + un-hidden `mcp-source-details-body-{id}`. All toggle/persistence/auth-notice testids unchanged in source; test intents preserved 1:1. 8 tests.
  - `test_flow_studio_tools_overrides.py`: rewritten from per-tool `.tool-row` grid to per-category tiles (`.tools-category-tile` Filesystem/Execution/Web) containing `details.tool-tile.tool-row-overrides` tool tiles. Added `_expand_category` / `_open_override_panel` helpers (override panels open via the summary's `.tool-tile-overrides-affordance` — clicks on the checkbox-label part of a summary toggle only the checkbox per HTML spec). The previously per-test-skipped grid-render test rewritten as `test_studio_tools_tab_renders_category_tiles` (3 category tiles, 19 tool tiles — same intent as the old 19-row assertion). F6 L5 override behaviors (lazy-load dedupe, operator-max narrowing, unmarked-field hiding, NarrowSuperset locked chips, save round-trip) all preserved and passing against current markup. 10 tests.
- **Flake fix (suite-only)**: first full-suite run failed `test_studio_agent_crud_flow` at the post-delete empty-state assertion (`agent-empty` attached but hidden, settled for 5s). Root-caused to a test-sequencing gap, not markup: the save flow's async continuation (`studio.js` PUT handler → `loadAll()` → re-select + `renderEditor(found)`) can complete AFTER the delete flow under CPU load, re-selecting the just-deleted agent and re-hiding the grid. Fix: synchronize step 13 with save-chain completion (`expect(save_btn).to_be_disabled()` — the same idiom the MCPs/Tools tests already use), plus `expect_response` around the second delete click so a confirm-window expiry fails loudly as a missing DELETE. Re-run green.
- flight.md "Hang modules" design decision corrected: the stale "hover-reveal opacity `components.css:660-699`" suspect replaced with the verified `components.css:719` display:none mechanism (Playwright treats `opacity: 0` as visible, so `:679` was never the test breaker).
- mission.md Known Issues: added the state-split, icon-only "New entity" CTA discoverability/a11y concern (citing `components.css:719` primary, `:679` compounding), assigned to Flight 3.

#### Verification

- Recorded failure reproduced before fixing (provider-setup module, skip removed, unmodified locator): deterministic not-visible timeout on the header CTA — root cause confirmed, not assumed.
- Criterion command green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_studio_tools_overrides.py tests/browser/test_studio_mcps_tab.py tests/browser/test_flow_provider_grid.py -m browser -x --timeout 180` → 29 passed.
- Root-cause modules green individually via the same wrapper (1 passed each).
- `grep -rn "pytestmark = pytest.mark.skip" tests/browser/` → 0 hits (target was ≤2).
- Full suite: `make test-browser` → **532 passed, 0 failed**, 6 skipped (all pre-existing per-test skips in unrelated modules: `test_flow_picker` ×3, `test_flow_agent_tabs` ×1, `test_flow_studio_openrouter_picker` ×1, `test_mcp_test_connection_button` ×1), 12 deselected (pixel). Run discipline held: all runs via `scripts/run-tests.sh`; no orphaned pytest/uvicorn/Chromium processes after runs.
- `ruff check tests/browser/` clean; `ruff format --check` clean on all five touched files.
- `git status`: no changes under `the_one/` — test files + flight artifacts only.

#### Notes

- No deferral path needed: both root-cause-class modules pass; the Flight-3 re-enable checklist obligation is moot. Flight 3 still owns the product-side CTA fix (mission Known Issue).
- The five modules' testids all exist in the Leg-01 registry (`docs/ui-testid-registry.md`) — no inconsistency between registry and source observed; registry untouched.
- Timebox: root-cause class closed in well under the budgeted session (the design review's verified citation made it a confirm-and-swap).

---

### perf-baseline-and-apparatus-proof

**Status**: landed
**Started**: 2026-07-03 (leg session)
**Completed**: 2026-07-03 (leg session)

#### Changes Made

- Created `missions/17-ui-redesign/perf-baseline.md` — the SC8 comparison anchor. Captured against the RUNNING operator instance (`http://127.0.0.1:8484`, app 0.2.15) via goldfinch MCP (0.5.7, Chromium 148/Electron 42), strictly read-only (area switches + page loads in a leg-owned tab; tab closed after; operator tabs untouched).
  - **Heap scenario** (M08 F7 Scenario 1, cycle definition pinned): asserted `App.perf.enabled === true` first (captureHeap-null disambiguation), 2s settle + `reset()`, start `captureHeap`, then **50 cycles × chat→studio→admin→chat = 150 effective hash transitions** (verified: `area-switch.full` count = 150), landmark-polled (`.content-panel.area-{id}.active`), run as 5 × 10-cycle evaluate chunks, 2s settle, end `captureHeap`. Result: 6,695,608 → 7,134,227 B = **+6.55%** (budget ≤20% — PASS). `area-switch.full` p50/p95/max 0.10/0.20/1.20 ms. Readings are **byte-precise** (not 100KB-quantized) — recorded in the comparison rule. Switch method (hash assignment vs M08's topbar clicks) recorded per the comparability requirement.
  - **Coarse nav-to-interactive per area** via fresh reloads landing at each hash: chat 63.6 ms / studio 213.6 ms / admin 57.4 ms (nav → `area-switch:activated` mark; studio's figure dominated by document responseEnd variance, JS activation gap ~3 ms everywhere). Built-in instrumentation only — no marks added, no product-source changes.
  - **M08 Scenarios 2–4**: not captured, documented with reasons (S2: no ≥100-msg session joined under read-only discipline; S3: 55 sessions present but the M08 procedure needs message sends and no built-in sidebar measure exists; S4: 3 agents, seeding is a mutation). Comparison rule cites the M08 anchors (+30.88% pre-fix / +3.92% post-L03 / −14.62% L06 HAT re-run).
- Updated `tests/behavior/studio-smoke.md`: exactly the two apparatus references (Preconditions "Chrome MCP" → goldfinch; Observables "chrome-devtools MCP" → goldfinch) plus the Preconditions host normalization `localhost:8484` → `127.0.0.1:8484`. Step table untouched (`git diff` verified: those lines only).

#### studio-smoke precondition-readiness check (flight DD deliverable)

**Result: NOT satisfied.** The spec (and every other connector-family spec) asserts a connector labelled **"Discord Constellation"** (`58f1fe5a833f`). The live instance's only connector is **"Discord"** (`data-id 37bd02b202e3`, type discord, no agents attached) — the old fixture connector no longer exists. The type-indicator half of the assertion WOULD pass (badge text "discord" renders uppercase via `text-transform: uppercase`); only the label fails.

**No existing spec substitutes cleanly under a read-only run**:
- `connector-editor-ux`, `connector-editor-keyboard-a11y`, and the `discord-*` family all reference the same missing "Discord Constellation" (and need attached agents / warm gateway / routing rules on top).
- `agent-retention-setting-roundtrip`'s preconditions ARE satisfied (running instance + ≥1 agent; 3 exist) but its steps persist a changed retention value (sets 90, never restores) — mutates operator data.
- `connector-inference-provider-config-roundtrip` and `audit-log-inspector-*` save config / seed metadata — mutating. `agent-governance-and-search` needs a dedicated dev instance on 8485.

**Recommendation for the FD** (per flight DD "the leg either seeds them or substitutes"): the minimal seed is a throwaway connector named "Discord Constellation" (type discord, unpaired — the spec asserts only tile label + type indicator + editor-with-tabs), created before the proof run and deleted after. That is an operator-data mutation and therefore an FD/operator decision, not this leg's (read-only mandate). Alternative: rename→run→rename-back on the existing "Discord" connector — also a mutation, and riskier (touches a real connector).

#### Verification

- `perf-baseline.md` read back: every captured scenario row has numeric values; not-captured scenarios carry explicit reasons, no placeholders; procedure pinned (cycle definition, switch method, settle, precision) for Flight 7 re-runs.
- `git diff tests/behavior/studio-smoke.md` → apparatus/host lines only; step table byte-identical.
- Read-only discipline held: no POST/PUT/DELETE issued; no sessions joined beyond the app's own auto-join on load; no clicks on mutation affordances; goldfinch tab wcId 7 (leg-owned) closed; operator tabs (wcId 4, 6) untouched. `git status` shows no changes under `the_one/`.
- No `confirmLeave` dialog or landmark stall across all 150 transitions (leg edge case — did not occur).

#### Notes

- `performance.memory` IS available and byte-precise in the goldfinch Electron context — the leg's timing-only fallback path (guidance step 5) was not needed.
- The heap loop wall time (~1.7 s for 150 transitions) is consistent with M08's 6.1 s click-driven run being dominated by click dispatch, not switch cost.

---

### unit-tier-stabilization

**Status**: landed
**Started**: 2026-07-03 11:55 CDT
**Completed**: 2026-07-03 12:50 CDT

#### Changes Made

- **Flake root cause** (`tests/test_lifespan.py::test_lifespan_drains_session_registry`): reproduced deterministically first — `pytest tests/test_index_asset_cache_busting.py tests/test_lifespan.py` fails every time; also reproduced under real tier ordering (modules 1–80: 2090 passed, 1 failed — the recorded `RuntimeError: session registry is shutting down`). Mechanism: `the_one/tools/_session_registry.py::shutdown_drain()` latches module-global `_shutting_down = True`, and `register()` refuses while it is set. Any test that drives the REAL app lifespan to completion trips the latch — `with TestClient(app):` runs full startup + shutdown. Two offender modules exist: `tests/test_index_asset_cache_busting.py` (module #77 in tier order — poisons `test_lifespan.py` at #80, whose first test is the only early register-caller without a prior clear) and `tests/test_window_focus.py` (#171 — same latent poison for later modules, currently masked only by lucky intra-module ordering in `test_session_registry.py`, whose first test doesn't register and whose post-test autouse clear then resets the flag). `tests/test_origin_allowlist.py` also uses `with TestClient(...)` but on locally built minimal apps — not an offender.
- **Fix (test/fixture-level only, no product-code changes)**:
  - `tests/conftest.py`: new reusable `reset_lifespan_singletons` fixture — after the test, calls the existing `_clear_for_test()` seams of the three modules whose `_shutting_down` flag the lifespan shutdown latches (PTY session registry, `the_one.mcp._pool`, `the_one.connectors._pool`), via `asyncio.run` in a fresh loop (post-drain all three are empty with no live tasks, so each clear is a cheap flag reset — nothing cross-loop is awaited).
  - `tests/test_index_asset_cache_busting.py` + `tests/test_window_focus.py`: activate it module-wide via `pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")` with a comment explaining the latch.
  - `tests/test_lifespan.py`: `_registry_cleanup` autouse fixture now clears BEFORE as well as after each test — defense in depth so the module never depends on suite ordering regardless of future offenders.
- **Format drift**: `ruff format` applied to the six pre-existing drift files (`tests/browser/test_flow_provider_editor.py`, `tests/test_anthropic_live.py`, `tests/test_anthropic_provider.py`, `tests/test_db_codec.py`, `tests/test_provider_api.py`, `the_one/interfaces/web/app.py`) — line-wrap consolidation + one blank line only; all six verified **AST-identical to HEAD** (stronger than eyeballing the diff).
- **CLAUDE.md**: one-line addition to the Testing section — full `make test-browser` runs need `TEST_TIMEOUT=3600` (default 1200s is tighter than the ~12.5 min suite runtime plus load overhead).

#### Verification

- Repro ordering now green: `test_index_asset_cache_busting.py + test_lifespan.py + test_window_focus.py` → 19 passed; `tests/test_lifespan.py` alone → 7 passed; neighbor-module ordering sweep around both offenders (8 modules) → 69 passed.
- `make test-unit` twice consecutively: **3681 passed, 10 skipped, 0 failed** both runs (previously 3680 passed / 1 failed — the fixed test accounts for the +1).
- `ruff format --check the_one/ tests/` → 396 files already formatted (tree-wide clean); `ruff check the_one/ tests/` → all checks passed.
- Six drift files: `git diff --stat` = 13 insertions / 36 deletions, AST equality against HEAD confirmed per file.
- No changes under `the_one/` beyond the format-only `app.py` reformat; Legs 01–03 uncommitted files and behavior-test artifacts untouched.

#### Notes

- The Leg-01 anomaly entry and the Deviations format-drift flag (above) are both resolved by this leg; entries left as recorded per log discipline.
- `test_window_focus.py` was fixed at the source even though no test currently fails from its poison — the latch it leaves is the same isolation defect, and leaving it would re-create this flake the moment a later module registers a PTY session before its own clear runs.

---

## Decisions

### connector-test-status dead selector: allowlist, not fix

**Context**: Leg guidance required dispositioning the `connector-test-status` selector (queried at `connector-editor.js:1775,1828`, defined nowhere).
**Decision**: Confirmed truly dead — the element was removed by M16 F5 L6 HAT round-7 (in-source comment "statusEl removed" + `void statusEl;` remnant near line 1875); both query results are null-guarded, so it is dormant, not a runtime bug. Allowlisted in `KNOWN_DEAD_SELECTORS` in `tests/test_ui_guards.py` with a comment, rather than editing product JS (this flight is test-infrastructure-only). Logged in mission Known Issues.
**Impact**: Flight 3's studio component rebuild should remove the dead queries and the allowlist entry together.

### Flight Director Notes

- **Disposition — studio save-chain race (Leg 02 anomaly)**: the latent product race (save continuation `loadAll()` → re-select landing after a subsequent delete) is real but low-severity for a single operator; assigned to **Flight 5** (Studio re-skin), which rebuilds the studio.js flows anyway. Recorded in mission Known Issues by Leg 02; no hotfix in this flight (test-infra-only discipline).
- **Decision — apparatus-proof spec substitution (Leg 03 escalation)**: studio-smoke's seeded fixture ("Discord Constellation" connector) no longer exists on the live instance, and no existing spec substitutes cleanly read-only. Rather than mutate operator data with a throwaway connector, the FD authored a new **read-only, data-independent** spec `tests/behavior/shell-navigation-smoke.md` (goldfinch apparatus, passes on any DB state) and runs it as the apparatus proof. Bonus: it is the re-runnable "did the redesign break basic navigation" gate for every M17 flight — more durable than a one-off seeded proof. studio-smoke keeps its goldfinch apparatus edit and stays runnable whenever its fixtures exist.
- **Disposition — `make test-browser` wrapper timeout**: default `TEST_TIMEOUT=1200s` < full-suite runtime (~12.5min + load overhead). Leg 04 scope extended: add a one-line CLAUDE.md note recommending `TEST_TIMEOUT=3600` for full-suite runs.

- Leg design reviews: Legs 01–03 each got one Developer design-review cycle; all reviewer recommendations were adopted verbatim, so second cycles were skipped (protocol discretion — fixes were the reviewer's own prescriptions). Leg 02's review corrected the flight's root-cause hypothesis (components.css:719 empty-state display:none, not the :679 hover-opacity theory) before implementation — the flight spec's "Hang modules" DD wording is corrected by Leg 02.
- **Leg 04 added mid-flight** (`unit-tier-stabilization`): Leg 01 surfaced a pre-existing unit-tier ordering flake (`test_lifespan_drains_session_registry`) and pre-existing ruff-format drift in six files. Both poison later flights' verification gates; fixing them is squarely this flight's objective (trustworthy net). Flight legs list updated.
- Execution order: Leg 02 implementation runs before Legs 03/04 (flight-log/flight.md write contention makes legs sequential). Behavior-test run in Leg 03 is executed by the Flight Director directly per the flight spec, in live two-agent mode (SendMessage available this session).

---

## Deviations

- `ruff format --check the_one/ tests/` is NOT clean tree-wide: six pre-existing files (`tests/browser/test_flow_provider_editor.py`, `tests/test_anthropic_live.py`, `tests/test_anthropic_provider.py`, `tests/test_db_codec.py`, `tests/test_provider_api.py`, `the_one/interfaces/web/app.py`) would be reformatted — drift committed on the branch before this leg. Left untouched (out of leg scope); the leg's own files are format-clean. Flag for flight review.

---

## Anomalies

- **Pre-existing unit-tier flake**: `tests/test_lifespan.py::test_lifespan_drains_session_registry` fails under full-suite ordering with `RuntimeError: session registry is shutting down` (leftover registry shutdown state from an earlier test), but passes in isolation and when its module runs alone. Verified pre-existing: reproduced with this leg's files removed from the tree (3675 passed / 1 failed). Not caused or fixable by this leg; needs disposition at flight level (SC6 "regression net healthier than before" makes this a natural Flight 1 follow-up candidate).

- **Latent studio save→delete race (product-side, observed via Leg 02 flake)**: the agent-save PUT handler's success continuation (`studio.js` ~2481-2498: `loadAll()` then re-select + `renderEditor(found)` from the refetched list) is not sequenced against later user actions. If the operator deletes the agent while that continuation's fetches are still in flight (sub-second window normally; widened under CPU load), the stale continuation re-selects and re-renders the just-deleted agent over the empty grid. Observed once as a suite-only test failure (`agent-empty` attached but hidden, settled). Leg 02 fixed the TEST to synchronize with save completion (models a user waiting for save feedback); the product-side last-writer-wins race remains. Low severity (narrow window, self-corrects on any navigation). Candidate for Flight 3/5's studio component rebuild; flagging for FD disposition rather than mission Known Issues since it does not affect the redesign's regression net.

---

## Session Notes

**Flight completion (2026-07-03)**: All four legs (testid-registry-and-guards, reenable-skipped-browser-modules, perf-baseline-and-apparatus-proof, unit-tier-stabilization) landed and passed flight review; leg artifacts set to `completed`, flight status set to `landed`, Flight 1 checked off in mission.md. All changes (code, tests, docs, artifacts, behavior-test spec and run log) land as a single flight commit — hash to follow in the commit record.

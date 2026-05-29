# Flight: Connector Terminology Rename + Small-Housekeeping Fold-Ins

**Status**: completed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

This flight closes no mission criterion directly. It is a substrate-stabilization flight inserted post-F9+F10 combined debrief that supports robustness (#19) indirectly by aligning code vocabulary with operator mental model before the F12-F15 arc adds further substrate surface.

The connector rename was filed at F10 L5 HAT as a structural operator-mental-model gap; the small-housekeeping fold-ins are carry-forward action items from the F9+F10 combined debrief (see [combined debrief Action Items](../10-acl-dm-admission-axis-split/flight-debrief.md#action-items)) that the operator chose to land alongside the rename rather than carry forward again.

---

## Pre-Flight

### Objective

Rename the `ConnectorAccount` concept to `Connector` across the entire substrate — schema table (`connector_accounts` → `connectors`), FK columns in dependent tables (`connector_account_id` → `connector_id` in `chat_sessions` and `pending_approvals`, `connector_account_ids` → `connector_ids` in `agents`), the v16 partial index, the Pydantic model, repository, ~280 Python class/repo references plus ~86 column-accessor sites (~370 Python sites total), 12 API path segments, ~277 JS references across 12 files, all four selector families (`data-testid`, `data-*` attributes, CSS classes, API URLs) plus their camelCase `dataset` accessors, CSS rules in `studio.css` and `admin.css`, 42 Python test files, 22 browser test files, and the 13+ agents.md citations. Land three small-housekeeping items the F9+F10 combined debrief filed as F11-bound: retire the `_acl.py` anachronistic deny message and its test fixtures, fix the 13 asyncio teardown errors in `test_provider_repository.py` (a fixture-pattern redesign — sync fixture wrapping async resource under `asyncio_mode = "auto"`, not the assumed surgical ordering tweak), and sweep agents.md (promote two new M11 conventions, extend the per-axis-tri-state-override block to five axes, add callouts for new F9 API endpoints, prune F4-era prose). Leave the substrate naming aligned with the operator's mental model before F12 (hierarchical allowlist axes) adds another axis to the same surface.

### Open Questions

All resolved during planning — see Design Decisions below.

- [x] Schema migration shape → see DD: Schema Migration Shape
- [x] Selector-rename scope → see DD: Selector Rename Scope
- [x] Asyncio teardown errors disposition → see DD: Asyncio Teardown Disposition
- [x] HAT requirement → see DD: Verification Approach
- [x] Leg split shape → see DD: Leg Split Shape
- [x] Vocabulary-substitution layer preservation → see DD: Vocabulary Substitution Discipline

### Design Decisions

**Schema Migration Shape**: Row-rewrite ceremony (migration v23), table-rename PLUS FK column rename.
- Rationale: Matches the in-codebase precedent at `the_one/db/schema.py:387-414` (the v12 `mcp_sources` reshape used `DROP-NEW-IF-EXISTS → CREATE-NEW → INSERT-FROM-OLD → DROP-OLD → ALTER RENAME`). The pattern is well-understood by the operator, well-tested in the existing migration harness, and atomic. ALTER TABLE RENAME was considered and rejected because SQLite's FK auto-update behavior is version-dependent and the codebase has no precedent that exercises it.
- **Scope**: v23 renames not just the `connector_accounts` table but also all FK columns and dependent indexes that carry the old vocabulary. Concretely:
  - `connector_accounts` → `connectors` (table at `schema.py:516-530`)
  - `chat_sessions.connector_account_id` → `chat_sessions.connector_id` (column at `schema.py:617`)
  - `idx_chat_sessions_external_key` partial index (`schema.py:638-640`) — DROP and recreate with the renamed column
  - `pending_approvals.connector_account_id` → `pending_approvals.connector_id` (column at `schema.py:804`, FK at `:805`, partial index `idx_pending_approvals_account_peer` at `:816`)
  - `agents.connector_account_ids` → `agents.connector_ids` (JSON column at `schema.py:666-668`)
  - All `chat_sessions` and `pending_approvals` row-rewrites happen in v23 alongside the parent table rename (the v12 `mcp_sources` pattern extends naturally to multiple dependent tables in one migration body).
- Trade-off: ~86 additional Python sites accessing `.connector_account_id` / `connector_account_ids` change to `.connector_id` / `connector_ids`. L1's diff grows by that ~86 sites + the migration body itself. The architect explicitly flagged that without renaming the columns, the spec would create a permanent `connectors` table referenced by `connector_account_id` columns — a vocabulary mismatch that defeats the purpose of the rename. Operator confirmed "full consistency" at planning.

**Full Rename, No Back-Compat Shims**: The Pydantic class, repository, FK column names, API path segments, JS variable names + camelCase `dataset` accessors, CSS classes, `data-testid` values, `data-*` attribute names, JSON column key names, and table name all change together. No deprecation aliases. No transition period.
- Rationale: Operator confirmed "pull the bandaid" — single-user local tool with no external API consumers, so the cost of breaking compatibility is zero. Maintaining a transition period would mean carrying dual vocabulary in agents.md and risking a hybrid-vocabulary half-rename if a follow-up flight forgets to complete it.
- Trade-off: Bigger atomic diff (the L1 backend leg touches ~370 Python sites including FK accessors; the L2 frontend leg touches ~277 JS sites + 22 browser tests + CSS files). The split into two legs limits each diff's review surface to one half of the stack.

**Selector Rename Scope**: All four selector families rename in lockstep within L2 — `data-testid` values, `data-*` attributes, CSS classes, AND API URL paths. (Architect Option B; operator-confirmed.)
- Rationale: The F10 debrief's "preserve `data-testid` selectors for stability" recommendation was correct intent (don't break browser tests during the rename) but imports the "stability" value from a context that doesn't apply (external selector consumers). The codebase has no precedent for preserving testid vocabulary through a rename; the precedent that exists shows testids reflecting current vocabulary. Option A (preserve literal `data-testid` strings) would create a permanent vocabulary mismatch in the DOM.
- Trade-off: Larger lockstep diff in L2 (170+ testid references plus the other three selector families). Mitigated by L2 being purely mechanical; the regression net is the browser-test suite running green.
- Mechanical verification: After L2, a repo-wide grep for `connector-account` should return zero hits in source files (the only allowed residue is in migration files that document the historical name and the agents.md change-log entry for this flight).

**Asyncio Teardown Disposition**: Fix the 13 errors in `tests/test_provider_repository.py` inline in L3 (housekeeping bundle).
- Rationale: These errors have been carried across F7, F8, F9, F10 debriefs without resolution; another forward-carry just defers the same fix to a later debrief. They're likely an AsyncExitStack / `aclose()` ordering issue at fixture teardown — surgical fix, not a structural rework. Closing them in F11 lets the F11-onward debriefs report a clean asyncio-teardown column in the test-metrics table.
- Trade-off: L3 carries a third unrelated item (already carrying two: the ACL deny message retirement and the agents.md sweep). Tolerable because all three are independently small.

**Verification Approach**: Regression tests only — no behavior test (HAT) authored for F11.
- Rationale: F11 is a mechanical rename with no new behavior. The signal of correctness is "all 2733 backend tests pass + all browser tests pass + no new flakes." The 22 browser tests already exercise the connector lifecycle (create / edit / detach / per-agent admit-dms / navigation); the lockstep selector rename verifies them automatically. Authoring a HAT would re-run what tests already cover and add no observation that the existing suite misses.
- Trade-off: If the rename introduces a subtle behavioral regression that only manifests under live Discord traffic (e.g. a deserialization edge case in pool key handling), F11's regression net won't catch it before F12 starts. Mitigation: F12's first leg should re-confirm a clean substrate by re-running the F10 L5 HAT scenario as a smoke test (informal, not a new spec).

**Leg Split Shape**: 3 legs — backend rename + API/frontend rename + housekeeping bundle.
- Rationale: Splitting the rename into backend-internal vs. frontend-facing halves keeps each diff's review surface tractable while preserving atomicity within each leg. Bundling the three housekeeping items into one leg matches their scale (each is < 100 LOC); fragmenting them would push the flight to 5 legs at the upper end of the sizing window.
- Trade-off: Between L1 landing and L2 landing, the backend says `Connector` while API URLs and the frontend say `connector-account` — a transient hybrid-vocabulary state for the flight's duration. Acceptable because the duration is short (single flight, both legs land in one branch before merge to main).

**Vocabulary Substitution Discipline**: The rename touches the substrate-neutral vocabulary (`ConnectorAccount` → `Connector`). It does NOT touch the Discord-specific vocabulary substitution layer that translates "peer / group / channel" into "username / server / role" at the Discord plugin and Discord-shaped UI surfaces.
- Rationale: M11 mission constraint (lines 59 in `mission.md`): "Vocabulary substitution discipline: the connector-agnostic API stays 'peer / channel / group' at the Protocol and storage layers; Discord-specific vocabulary is substituted at the Discord plugin's translate layer (`_discord_translate.py` precedent) and at the Discord-shaped UI surfaces." This rename adjusts the substrate-side name of the connector primitive itself but does not collapse the substitution layer that lives on top of it.
- Concretely: `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js` continues to do its translation job; only its internal references to `ConnectorAccount` change.

### Prerequisites

- [ ] M11 agents.md exists and has the M11 subsection at line 384+ (verified during recon).
- [ ] F10 has landed (commit `74826ac`); branch from main HEAD after pulling.
- [ ] The 22 browser tests in `tests/browser/test_flow_*connector_account*.py` are currently green on main (baseline for L2 verification).
- [ ] The backend test suite is at 2733 passed / 4 skipped / 13 pre-existing asyncio teardown errors / 256s wall (F10 land baseline per debrief test-metrics).

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites listed
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**L1 — Backend rename (atomic substrate slice).** Land migration v23 (row-rewrite ceremony following the `mcp_sources` precedent at `the_one/db/schema.py:387-414`), extended to cover all FK columns + dependent indexes (see DD: Schema Migration Shape for the explicit list). Rename `class ConnectorAccount` → `class Connector` at `the_one/db/models.py:116` and `class ConnectorAccountRepository` → `class ConnectorRepository` at `the_one/db/repositories.py:506`. Sweep all ~280 Python class references + ~86 column-accessor references (`.connector_account_id` → `.connector_id`, `connector_account_ids` → `connector_ids` for the JSON column accessors) across production code + tests (~370 Python sites total). Update repository SQL strings to use the new table + column names. Update the FK comment at `schema.py:793` describing the CASCADE behavior. The 12 FastAPI routes in `the_one/interfaces/web/api.py` (lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673, 2745, 2785, 2849 — including the F9 peer-approval endpoints) continue to expose `/api/connector-accounts/...` paths (rename deferred to L2 so the frontend keeps working between legs). Internally, the routes operate on `Connector` model instances and `ConnectorRepository` — the URL path strings and the JS-facing response field names (if any expose `connector_account_id`) are the only frontend-facing surfaces that don't change in L1. **L1 explicitly does NOT touch any `data-testid` value, `data-*` attribute name, CSS class, JS variable name, or HTML template string** — those all stay at `connector-account-...` in L1's diff and rename atomically in L2. agents.md citation updates that reference the renamed Python class (recon found 13+ sites at lines 100, 216, 243, 399, 411, 604, 607, 608, 609, 610, 652, 660, 666) land here for class-name references; the structural sweep (new conventions, tri-state extension, API callouts) stays in L3. Update `_connector_types.py:55` docstring reference to `ConnectorAccount.type`. Backend test suite green; migration test suite green (`pytest tests/test_db_migration.py`); browser test suite green (unchanged because URLs + DOM markup unchanged).

**L2 — API + frontend rename (atomic UI slice).** Rename the 12 API routes' path segments from `/api/connector-accounts/...` → `/api/connectors/...` in `the_one/interfaces/web/api.py` (lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673 + 2745 [F9 peer-approval endpoints], 2785, 2849); also rename the path on `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}` → `.../connectors/{connector_id}` at line 519, with the path-parameter name updated in lockstep. Update all ~277 JS references across the 12 files identified in recon: `studio.js`, `connector-account-editor.js`, `connectors-tab.js`, `connector-form-discord.js`, `discoverable-dropdown.js`, `connector-accounts-grid.js`, `connector-form-registry.js`, `pending-approval-banner.js`, `chat.js`, `connector-vocabulary.js`, `agent-editor.js`, `mcp-server-editor.js`. Rename all four selector families in lockstep — `data-testid` values, `data-*` attribute names (including their camelCase `element.dataset.connectorAccountId` access form which becomes `element.dataset.connectorId`), CSS classes, and the API URL strings the JS fetches. Rename the CSS rules in `the_one/interfaces/web/static/css/studio.css` (12+ `.connector-account-*` rules in the line range 794–1599 per architect recon) and `the_one/interfaces/web/static/css/admin.css` (at least one `.connector-account-*` rule near line 283). Rename JS files where the filename carries the term (e.g. `connector-account-editor.js` → `connector-editor.js`, `connector-accounts-grid.js` → `connectors-grid.js`) and update their template-loader / module-import references in lockstep. Update all 22 browser test files under `tests/browser/test_flow_*connector_account*.py` to use the renamed selectors. Rename the 13 browser test files whose filename carries the term (e.g. `test_flow_studio_connector_account_editor.py` → `test_flow_studio_connector_editor.py`) and update their `data-testid` selector strings. Verification gate: repo-wide `grep -rE "connector-account|ConnectorAccount|connector_account" the_one/ tests/` returns zero hits in source files. Allowed residue: schema migration body for v23 (retains historical name as the FROM side of the row-rewrite), this flight's debrief and log, and historical agents.md citations (M11 subsection retains them as change-log entries — L3 prunes only the F4-era prose, not the M11 history). Total exclusions documented inline at the grep gate.

**L3 — Housekeeping bundle (three independent items, ordered: agents.md sweep → ACL deny message retirement → asyncio fixture redesign).** Ordering matters: do the agents.md sweep first so the documentation prose changes shake out any further L1/L2 rename residue before the surgical fixes land.

(a) **agents.md structural sweep.** Sweep `the_one/agents.md`: promote `dms-orthogonal-to-guild-restriction` (F10 L1 posture inversion of F8 L8) and `backend-merged-replay` (F9 L4's `_restore_session` merges messages + pending_approvals by timestamp) to named M11 conventions; extend the per-axis-tri-state-override block from 4 axes to 5 by adding `dm_admission`; add callouts for the two new F9 API endpoints (`POST /api/connectors/{id}/peer-approvals/{id}/{approve|dismiss}` and `DELETE /api/agents/{name}/connectors/{connector_id}` — both rendered with their renamed L2 paths since L3 lands post-L2; both at the same "must-know-before-touching" level as the `__MASKED__` sentinel that CLAUDE.md calls out); prune F4-era prose that the M10 debrief should have retired (Flight Director identifies the specific paragraphs during leg planning by cross-referencing the M10 debrief's documentation section).

(b) **`_acl.py` anachronistic deny message retirement.** Retire the anachronistic deny message at `the_one/connectors/_acl.py:449-462` (the current message reads `"... (DMs-only override; envelope is not a DM)"` but the branch now only fires for guild-context messages per the F10 L1 inversion); update the message to reflect what the branch actually checks. Retire the 9-line back-compat comment block at `_acl.py:440-448` that was preserving the deferred state. Update the test fixtures at `tests/test_connectors_acl.py:311` (`test_per_agent_channels_empty_is_dms_only_sentinel`, inbound version) and the outbound analog at `:97` — the deny-string assertions in both tests need updated expected values matching the retired message.

(c) **`tests/test_provider_repository.py` asyncio fixture redesign.** The 13 errors are a fixture-pattern mismatch, not a surgical ordering tweak: the file uses a sync `@pytest.fixture()` at `:31-35` wrapping an async resource via `asyncio.get_event_loop().run_until_complete()` while the project's `pyproject.toml` sets `asyncio_mode = "auto"`. The fix is to convert the fixture to a native async fixture (`@pytest_asyncio.fixture()` or `@pytest.fixture()` with the auto-async runner), which touches every test in the file (the 13 tests at lines 53, 59, 70, 84, 101, 112, 126, 140, 149, 157, 166, 175, 183 — likely all 13 because the fixture redesign changes the consumer signature). Confirm at leg-planning time whether the test bodies need the fixture rewired as `await repo_fixture` rather than `repo_fixture` directly. Verification: backend test suite reports 0 asyncio teardown errors (down from 13) and 2733+ passing after L3 lands (the F10 baseline + any new tests added in L1/L2 + 13 previously-erroring-now-passing tests).

### Checkpoints

- [ ] **L1 land**: backend test suite green; migration test suite green (`pytest tests/test_db_migration.py` — the regression net for v23, exercises all prior migrations + v23 against a fresh DB); `git grep ConnectorAccount the_one/` returns zero hits outside migration files; `git grep "connector_account_id\|connector_account_ids" the_one/` returns zero hits outside migration v22-and-earlier bodies; schema v23 applied cleanly on a fresh database; FK in `chat_sessions` and `pending_approvals` references `connectors.id` not `connector_accounts.id`; partial indexes recreated against the renamed columns; the 12 API routes still respond at `/api/connector-accounts/...` paths (URL rename is L2's job).
- [ ] **L2 land**: browser test suite green; backend test suite green; `git grep -E "connector-account|connector_account" the_one/ tests/` returns zero hits in source files (the allowlisted residues are the v23 migration body, this flight's debrief/log, and historical agents.md M11 citations — listed explicitly at the gate); all 13 renamed browser test files passing under their new names; the 12 API routes now respond at `/api/connectors/...` paths.
- [ ] **L3 land**: backend test suite reports 0 asyncio teardown errors (down from 13) and 2733+ passing (F10 baseline + L1/L2 additions + 13 previously-erroring-now-passing); `_acl.py:449-462` deny message reflects the branch's actual check; agents.md M11 subsection promotes the 2 new conventions, extends the tri-state block to 5 axes, and includes the new API endpoint callouts (under their L2-renamed paths); F4-era prose pruned.
- [ ] **Flight land**: combined diff reviewable; no new flakes introduced across two consecutive full-suite runs; ready to land.

### Adaptation Criteria

**Divert if**:
- The L1 schema rename surfaces an FK relationship the recon missed (beyond the four dependent surfaces enumerated in DD: Schema Migration Shape — `chat_sessions.connector_account_id` + index, `pending_approvals.connector_account_id` + FK + index, `agents.connector_account_ids` JSON column, and the FK CASCADE comment at `schema.py:793`) — re-scope L1 to enumerate ALL FK references and update them in the same migration. The architect's recon caught these four; another surface would indicate the recon was incomplete and warrants a re-grep before continuing.
- L2's repo-wide grep verification surfaces residue that requires unbounded sweeping (e.g. a vendored JS library that uses the term internally, or a generated file that re-emits the old name on each build) — operator decision on whether to vendor-patch, regenerate, or document an exception with explicit allowlist additions to the grep gate.
- The L3 asyncio fixture redesign surfaces non-local effects (e.g. shared fixtures imported into other test files break because the consumer signature changes) — promote the asyncio fix to L4 of its own, leaving (a) and (b) of L3 as the original L3.

**Acceptable variations**:
- L1 may discover that `ConnectorAccountConfig` or similar sibling Pydantic models exist (e.g. request/response wrappers in `api.py`); rename them in the same leg (they're part of the same atomic substrate slice).
- L2 may discover additional `data-*` attributes the recon missed (the architect's check turned up 4 selector families; if a fifth — e.g. ARIA labels or `aria-label` strings carrying the term — surfaces, rename in lockstep within L2). Do not defer to a follow-on.
- L3 may identify additional F4-era prose to prune in agents.md beyond what the debrief explicitly listed; prune at Flight Director discretion if it's clearly stale.
- L3's asyncio fixture redesign may require updating test bodies' fixture-consumer signatures (`await fixture` instead of bare `fixture`) — that's expected scope, not a divert.

### Legs

- [x] `backend-rename` — Schema v23 row-rewrite migration (table + FK columns + dependent indexes + JSON column); rename `ConnectorAccount` → `Connector`, `ConnectorAccountRepository` → `ConnectorRepository`; sweep ~370 Python sites (class refs + column accessors, production + tests); update FK in `chat_sessions` and `pending_approvals`; keep `/api/connector-accounts/...` URL paths AND all `data-*` / `data-testid` / CSS strings unchanged (frontend continues to work). Backend + migration test suites green.
- [x] `api-and-frontend-rename` — Rename 12 API path segments from `connector-accounts` → `connectors`; sweep ~277 JS references across 12 files; rename all four selector families (`data-testid`, `data-*` attributes including their camelCase `dataset` access form, CSS classes in `studio.css` + `admin.css`, API URL strings) in lockstep; rename JS module filenames where they carry the term; update + rename 13 browser test files (and update selectors in all 22 connector-touching browser tests); verification gate is repo-wide grep returning zero `connector-account|connector_account` hits in source files (allowlisted residue documented at gate). Browser + backend suites green.
- [x] `housekeeping-bundle` — Sweep `the_one/agents.md` FIRST (promote 2 M11 conventions, extend per-axis-tri-state block to 5 axes, add 2 API endpoint callouts under renamed paths, prune F4-era prose); retire `_acl.py:449-462` anachronistic deny message + 9-line back-compat comment block at `:440-448` + 2 test fixtures at `tests/test_connectors_acl.py:97` and `:311`; redesign `tests/test_provider_repository.py` fixture from sync + `run_until_complete` to native async fixture (touches all 13 tests). 0 asyncio teardown errors after land; 2733+ tests passing.

---

## Post-Flight

### Completion Checklist

- [x] All 3 legs completed
- [ ] Code merged
- [x] Backend test suite: 2733+ passed / 4 skipped / **0 asyncio teardown errors** (down from 13) / wall-clock within 10% of baseline
- [x] Browser test suite: green (22 renamed test files + any existing connector-touching tests)
- [x] Repo-wide grep for `connector-account|ConnectorAccount|connector_account` returns zero hits in source files (migration files and this flight's debrief/log are the only acceptable residue)
- [x] `the_one/agents.md` M11 subsection reflects the 2 new conventions + 5-axis tri-state block + new API endpoint callouts
- [x] Mission outline `mission.md` Flight 11 entry marked `[x]` with one-line summary

### Verification

Three independent signals confirm the flight achieved its objective:

1. **Mechanical (grep)**: `git grep -E "connector-account|ConnectorAccount|connector_account" the_one/ tests/` returns zero hits in source files. Acceptable residues (documented explicitly at the gate):
   - `the_one/db/schema.py` migration v23 body retains the historical `connector_accounts` table name + `connector_account_id` column names as the FROM side of the row-rewrite (necessary for the migration to work).
   - Earlier migrations (v1–v22) retain their original references; they document history.
   - This flight's `flight.md`, `flight-log.md`, and `flight-debrief.md` retain the old vocabulary as historical references.
   - `the_one/agents.md` retains the M11 subsection citations as a change-log of the rename event (the F4-era prose IS pruned in L3, but M11-era history stays).
   - This list is the canonical allowlist; any other surface that emits the old vocabulary at L2 land is a miss and must be added or fixed before the leg lands.

2. **Regression (test suites)**: backend suite reports 2733+ passing / 0 asyncio teardown errors / 4 skipped; migration test suite green (verifies v23 + all priors apply cleanly on a fresh DB); browser suite passes all renamed connector-touching test files plus any other tests that exercise the renamed surfaces. No new flakes observed across two consecutive runs.

3. **Operator (smoke test)**: operator opens a fresh dev environment, creates a connector via the UI (now labeled "Connector" everywhere), attaches an agent, sends a Discord message round-trip, detaches the agent — all surfaces show "Connector" vocabulary, no "Connector Account" leak. Confirms L2's frontend rename actually presents as renamed in the running UI.

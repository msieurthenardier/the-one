# Flight Log: Connector Terminology Rename + Small-Housekeeping Fold-Ins

**Flight**: [Connector Terminology Rename + Small-Housekeeping Fold-Ins](flight.md)

## Summary

Flight in-flight. F11 began execution on 2026-05-28 immediately after F9+F10 combined debrief and F11 planning. Three legs planned: L1 backend-rename, L2 api-and-frontend-rename, L3 housekeeping-bundle. Per agentic-workflow protocol, code review + commit deferred to Phase 2d (single review + commit covering all three legs' uncommitted changes).

---

## Flight Director Notes

### 2026-05-28 — Flight kickoff

- Loaded crew definitions from `.flightops/agent-crews/leg-execution.md` (well-formed: Developer/Reviewer/Accessibility-Reviewer crew, Sonnet/Haiku/Sonnet models). Defer-to-Phase-2d commit rule per `/agentic-workflow` skill.
- **State remediations applied before kickoff**:
  - Mission status updated `planning` → `active` (was a long-standing tracking miss; F1–F10 had all landed under the wrong status).
  - Flight status `ready` → `in-flight`.
  - Branch created from main: `flight/11-connector-rename-and-housekeeping`.
- **Operator local-state callout (not F11 scope)**: `docker-compose.yml` carries an uncommitted modification adding `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` env vars (M11 F7 L12 HAT dev-config). Developer agents will be instructed to stage files explicitly (no `git add .` / `-A`) so this stays out of F11 commits.
- **Architect cycles used at flight-design**: 2 (cycle-2 verdict: READY for operator walkthrough, no blockers). Operator approved.
- **Acceptance verification approach**: regression tests only (backend + migration + browser suites). No behavior-test spec authored for F11 — the rename has no new behavior to observe.

---

## Reconnaissance Report

Per `/flight` Phase 1b. Source artifact: [F9+F10 combined debrief Action Items](../10-acl-dm-admission-axis-split/flight-debrief.md#action-items).

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Mission outline reorder (F11/F12 swap) | **already-satisfied** | `mission.md:125-130` already reflects new ordering; F11 entry shows "Connector terminology rename + small-housekeeping fold-ins" | Retire from action items; reorder is done |
| Substrate rename `ConnectorAccount` → `Connector` | **confirmed-live** | `the_one/db/models.py:116` (class), `the_one/db/repositories.py:506` (`ConnectorAccountRepository`), schema table at `the_one/db/schema.py:516-530`, FK at `:805` | Primary scope; lands in L1 (backend) + L2 (API/frontend) |
| API path segments `/api/connector-accounts/...` | **confirmed-live (architect-corrected count)** | 12 routes in `the_one/interfaces/web/api.py` (lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673, 2745, 2785, 2849) — Flight Director's initial recon undercounted at 9; architect re-grep found the 2 F9 peer-approval endpoints at 2673/2745 + corrected to 10 plain routes; F11 sum is 12 with peer-approvals included | L2 (atomic API + frontend slice) |
| JS references | **confirmed-live (broader than debrief estimate)** | 12 files, ~277 matches (debrief said "~20+"); largest: `studio.js` (79), `connector-account-editor.js` (97), `connectors-tab.js` (36) | L2; recon-confirmed broader-than-estimated scope is the rationale for splitting backend/frontend into separate legs |
| `data-testid` + sibling selectors | **confirmed-live (with architect-flagged scope extension)** | `connectors-tab.js:122,136,246,261,279` + 22 browser test files (170+ references); architect notes 4 selector families: `data-testid`, `data-*` attributes (incl. camelCase `dataset` access), CSS classes (`studio.css` ~12 rules at lines 794–1599 + `admin.css` near line 283), API URLs | L2 lockstep across all 4 families (Option B per architect + cycle-1 review additions) |
| FK columns + dependent indexes + JSON column | **confirmed-live (architect-surfaced; missed by initial recon)** | `chat_sessions.connector_account_id` at `schema.py:617`; `idx_chat_sessions_external_key` at `:638-640`; `pending_approvals.connector_account_id` at `:804` + FK at `:805` + `idx_pending_approvals_account_peer` at `:816`; `agents.connector_account_ids` JSON column at `:666-668`; ~86 Python accessor sites | L1 schema v23 row-rewrites all dependent tables + indexes (operator chose "full consistency" over "historical column-name residue") |
| agents.md `ConnectorAccount` citations | **confirmed-live (architect-corrected count)** | Initial recon found 5 (lines 100, 243, 399, 604, 610); architect cycle-1 grep found 13+ (lines 100, 216, 243, 399, 411, 604, 607, 608, 609, 610, 652, 660, 666) | Class references in L1; structural sweep in L3; non-pruned M11 citations remain as historical change-log per Verification gate allowlist |
| `_acl.py:467` anachronistic deny message | **confirmed-live (line drift to :449-454)** | Actual location `the_one/connectors/_acl.py:449-454`; 9-line back-compat comment block at `:440-448`; tests at `tests/test_connectors_acl.py:97` (outbound) and `:311` (inbound `test_per_agent_channels_empty_is_dms_only_sentinel`) | L3 housekeeping bundle |
| `tests/test_provider_repository.py` 13 asyncio teardown errors | **confirmed-live + architect-reclassified-as-fixture-redesign (carried since F7)** | File has 13 tests at lines 53, 59, 70, 84, 101, 112, 126, 140, 149, 157, 166, 175, 183; **root cause** per architect cycle-1: sync `@pytest.fixture()` at `:31-35` wrapping async resource via `run_until_complete()` while project runs `asyncio_mode = "auto"` — not the assumed AsyncExitStack ordering tweak | L3 housekeeping bundle; operator chose keep-bundled + acknowledge-fixture-redesign-scale; touches all 13 tests' fixture-consumer signatures |
| agents.md structural sweep (5 sub-items) | **confirmed-live** | (a) promote `dms-orthogonal-to-guild-restriction`; (b) promote `backend-merged-replay`; (c) extend per-axis-tri-state-override from 4 to 5 axes; (d) callouts for new F9 API endpoints; (e) prune F4-era prose | L3 housekeeping bundle |

**Classification summary**: 1 already-satisfied (retired from action items), 8 confirmed-live (drive flight scope). Zero items in `needs-human-recheck` or `partially-satisfied` — every action item from the combined debrief that wasn't already satisfied is real, currently-unaddressed work.

**Recon adjustments to debrief's framing**:
- JS reference count is ~277 across 12 files, materially larger than the debrief's "~20+ JS references" estimate. Drives the L1/L2 split rather than a single mega-leg.
- The architect's narrow-vs-broad reading of "preserve `data-testid` selectors" is a real risk: read narrowly, the rename would create a permanent vocabulary mismatch. L2's scope explicitly enumerates all 4 selector families.
- API route count was initially undercounted at 9; architect cycle-1 grep corrected to 12 (10 plain routes + 2 F9 peer-approval routes at lines 2673, 2745).
- agents.md citation count was initially undercounted at 5; architect cycle-1 grep corrected to 13+ sites.
- Schema scope was initially understated to "FK at `schema.py:805`"; architect cycle-1 surfaced 4 additional dependent surfaces (`chat_sessions.connector_account_id` + index, `pending_approvals.connector_account_id` + FK + index, `agents.connector_account_ids` JSON column) totaling ~86 additional Python accessor sites. Operator chose "full consistency" — v23 row-rewrites all dependent tables.
- CSS class enumeration: initial recon mentioned CSS classes as a generic selector family; architect cycle-1 turned up `studio.css` (~12 rules at lines 794–1599) + `admin.css` (at least one rule near line 283). L2 explicitly lists both files.
- `_acl.py:467` line citation drifted by 13 lines post-F10 (now `:449-462` for the deny block + `:440-448` for the back-compat comment block).
- L3 asyncio fix re-classified: not surgical (AsyncExitStack ordering), but a fixture-pattern redesign (sync fixture under `asyncio_mode = "auto"`). Operator chose to keep L3 bundled with acknowledged-redesign-scale rather than split into L3a/L3b.

---

## Leg Progress

### L1 backend-rename — landed 2026-05-28

**Status**: landed (NOT committed; Phase 2d batches).

**Schema migration v23 shape**: row-rewrite `connector_accounts` → `connectors` (9-column copy, CHECK constraint preserved verbatim) + row-rewrite `pending_approvals` (FK column `connector_account_id` → `connector_id`, FK target re-pointed at `connectors(id)` ON DELETE CASCADE, supporting index `idx_pending_approvals_account_peer_status` recreated against renamed column) + `ALTER TABLE chat_sessions RENAME COLUMN connector_account_id TO connector_id` (with `idx_chat_sessions_external_key` partial expression index dropped + recreated against renamed column) + `ALTER TABLE agents RENAME COLUMN connector_account_ids TO connector_ids`. PRAGMA foreign_keys=OFF/ON envelope. `INSERT OR IGNORE INTO schema_version (version) VALUES (23)` LAST. Idempotent re-entry guard handles the v7-strip-test scenario (schema_version-rewind + re-run): segment-level Python conditionals skip rename ceremonies whose source table is missing OR whose target column name is already renamed.

**Python surface touched (~370 sites across the file set):**

- `the_one/db/models.py` — `class ConnectorAccount` → `class Connector` (1 site; docstring updated).
- `the_one/db/repositories.py` — `class ConnectorAccountRepository` → `class ConnectorRepository` (1 site); SQL strings in `list`/`get`/`create`/`update`/`delete` rewritten to use `connectors` table (6 SQL strings). KeyError message text (`"Connector account not found: ..."`) preserved to keep API-error-detail parity with `the_one/interfaces/web/api.py` (404 detail strings are L2's scope per atomicity boundary).
- `the_one/db/_connector_types.py` — 6 docstring sites updated (lines 7, 12, 19, 21, 23, 33 per spec citation audit) + line 24 v23-reference addition.
- `the_one/db/schema.py` — v23 migration block added at lines 950-1155; v14-body comment at `:553` updated `ConnectorAccountRepository` → `ConnectorRepository`; v21-body FK CASCADE comment carries a v23-rename addendum. Migration-body SQL retains historical column names where it documents v16/v17/v21 schema state AND on the FROM side of the v23 row-rewrite (acceptable residue per spec AC #7).
- All `the_one/connectors/*.py` plugin files swept (base.py, _inbound.py, _inference.py, _commands.py, _pool.py, _acl.py, _discord.py, _stub.py, _routing.py, _session.py) — type annotations + parameter names + local variables renamed.
- `the_one/tools/connector_history.py` (4 sites) + `the_one/tools/connector_send.py` (2 sites) — `self._connector_account_ids` attribute → `self._connector_ids`.
- `the_one/interfaces/web/api.py` — SQL refs in the encryption-rotation handler (`SELECT id, secrets FROM connectors`, `UPDATE connectors SET secrets = ?`) updated. URL path strings `/connector-accounts/...` (14 routes including F9 peer-approval + per-agent detach routes) preserved per L1 atomicity boundary.
- `the_one/interfaces/web/app.py`, `the_one/agent/config.py`, `the_one/agent/factory.py` — accessor sweep.
- `the_one/tools/builtins.py` — accessor sweep.

**Test surface touched:**

- `tests/test_db_migration.py` — new `TestSchemaV23` class (lines 2992-3390) with 3 tests: `test_v23_fresh_db_has_renamed_tables_and_columns`, `test_v23_migration_idempotent_on_rerun`, `test_v23_legacy_v22_rows_migrate_with_content_preserved`. Pre-v23 `TestSchemaV{13,14,15,16,17,18,19,21,22}` classes are Category A per spec — they pin historical schema names and stay unchanged. Comments updated to cross-reference the v23 rename where they describe post-v23 final shape.
- `tests/test_db_repositories.py`, `tests/test_db_api.py`, `tests/test_factory.py`, `tests/test_config.py`, `tests/test_connector_send_tool.py`, `tests/test_connector_history_tools.py`, `tests/test_api_secret_mask_roundtrip.py`, `tests/test_provider_api.py`, `tests/test_connector_types_consistency.py` and ~17 other `tests/test_connectors_*.py` files — Category B sweep: rename `ConnectorAccount` → `Connector`, `connector_account_id(s)` → `connector_id(s)`, attribute reads `tool._connector_account_ids` → `tool._connector_ids`, test method names that carry the old term (`test_connector_account_ids_*`, `test_load_pre_v17_agent_has_empty_connector_account_ids`, etc.) renamed in lockstep. Test class names like `TestConnectorAccountRepository`, `TestConnectorAccountAPI` left unchanged — they don't match the `\bConnectorAccount\b` boundary (immediately followed by a word char) and renaming class containers exceeds AC scope.
- `tests/_connector_dispatch_helpers.py` — accessor sweep.

**Documentation:**

- `the_one/agents.md` — 13 Python class citations updated per spec (no structural sweep; that's L3's job).
- `the_one/connectors/README.md` — plugin-author class refs `ConnectorAccount` → `Connector` throughout; `connector_accounts.type` / `.secrets` prose updated to `connectors.type` / `.secrets` with M11 F11 L1 v23 attribution where appropriate.

**Test results:**

- `pytest tests/test_db_migration.py -x --timeout 30` → 58 passed (no regressions; +3 new tests from `TestSchemaV23`).
- `pytest --deselect tests/test_provider_repository.py --ignore=tests/browser -x --timeout 60` → **2736 passed, 4 skipped, 30 deselected, 0 failures** in 237s. Count delta vs baseline (2733): +3 from `TestSchemaV23`. Wall time ~7% below the 256s F10 baseline (no regression). The 13 pre-existing asyncio teardown errors in `tests/test_provider_repository.py` remain (L3 scope; deselected for this verification run).

**Atomicity boundary verified:**

- `git diff --name-only main -- 'the_one/interfaces/web/static/'` → empty (zero JS/CSS/HTML touched).
- `git diff --name-only main -- 'tests/browser/'` → empty (zero browser test changes).
- `grep -nE '"/connector-accounts' the_one/interfaces/web/api.py` → 14 hits (URL paths preserved for L2 atomic swap).
- `grep -rnE '\bConnectorAccount\b' the_one/ tests/` → zero hits in Python source (residue lives only in `the_one/interfaces/web/static/js/` which is L2's scope).
- `grep -rnE 'connector_account_id|connector_account_ids' the_one/ tests/ --include='*.py'` outside the allowed residue (`schema.py` migration bodies + `test_db_migration.py` Category A pre-v23 tests + `tests/browser/` L2-scope) → zero hits.

**Notes for L2 designers:** the API error message strings (`"Connector account not found: ..."`) at `the_one/interfaces/web/api.py:2487` and 11 other detail strings were kept as-is in L1 to parallel the preserved URL paths — when L2 swaps the URL surface, the error-detail prose should swap in lockstep so the operator-facing API surface flips atomically.

---

### L2 api-and-frontend-rename — landed 2026-05-28

**Status**: landed (NOT committed; Phase 2d batches).

**API surface (the_one/interfaces/web/api.py):**

- 14 route paths renamed from `/connector-accounts/...` to `/connectors/...` (lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673, 2745, 2785, 2849, 3039, 3115). Path parameter names `{account_id}` preserved as Python function arg (renaming would ripple into L1-touched repository code outside L2 scope).
- 11 error-detail f-strings updated from `f"Connector account not found: {account_id}"` → `f"Connector not found: {account_id}"` (lines 2487, 2519, 2607, 2620, 2653, 2707, 2762, 2822, 2882, 3080, 3142).
- 2 docstring prose sites updated: line 2792 (`"Studio Connector account editor"` → `"Studio Connector editor"`) + line 3046 (`"404 (Connector account not found)"` → `"404 (Connector not found)"`). Both surface to operators via FastAPI's docstring → OpenAPI/Swagger pipeline.
- 4 docstring URL references inside `list_connector_account_types` (lines 2464/2466) updated from `` ``/connector-accounts/{account_id}`` `` → `` ``/connectors/{account_id}`` `` to keep ordering-rationale comment in lockstep with the renamed routes.

**Frontend — static/ (15 files swept across 4 selector families):**

- 12 JS files swept across `data-testid` selector values, `data-*` attribute names (`data-connector-account-id` → `data-connector-id`, `data-connector-account-toggle` → `data-connector-toggle`), camelCase `dataset` accessors (`element.dataset.connectorAccountId` → `element.dataset.connectorId`), API URL `fetch()` calls (`/api/connector-accounts/...` → `/api/connectors/...`), CSS class names referenced via `classList.add/remove/contains/querySelector`, JS variable names (`connectorAccount*` → `connector*`, `ConnectorAccount*` → `Connector*` for camelCase/PascalCase identifiers), and in-comment prose. Custom event names (`connector-account-pool-warmed` → `connector-pool-warmed`, etc.) renamed in lockstep across producers + consumers.
- `studio.js` back-compat layer retirement: the F5 L8 HAT `'connector-accounts'` ↔ `'connectors'` slug fallback in `serializeState` / `hydrateState` collapsed to single-slug `'connectors'` post-rename (no operator-facing capability change — `'connector-accounts'` URLs already auto-rewritten to `'connectors'` by the router's serialize-after-hydrate pass since F5 L8). Comments updated to reflect M11 F11 L2 retirement.
- 2 CSS files: `studio.css` (16 selector rules renamed from `.connector-account-*` to `.connector-*`) + `admin.css` (1 selector renamed). CSS class collision check via systematic suffix-overlap grep returned zero collisions across all 39 distinct `.connector-account-{suffix}` forms vs existing `.connector-{other-suffix}` classes.
- 2 JS filenames renamed via `git mv`: `connector-account-editor.js` → `connector-editor.js` (1860+ lines); `connector-accounts-grid.js` → `connectors-grid.js`. Both `<script src="...">` tags in `static/index.html` (lines 58 + 63) updated to reference the renamed paths.

**Tests — browser/ (22 files + seeders + 4 file renames):**

- `tests/browser/seeders.py`: function `seed_connector_account` renamed → `seed_connector`; docstring + body URL string `/api/connector-accounts` → `/api/connectors`; `assert` message updated. Caller sites across all 22 connector-touching browser test files updated in lockstep (`grep -rn 'seed_connector_account' tests/browser/` → 0 hits post-rename).
- 4 browser test files renamed via `git mv`:
  - `test_flow_connector_account_detach.py` → `test_flow_connector_detach.py`
  - `test_flow_studio_connector_account_create_and_test.py` → `test_flow_studio_connector_create_and_test.py`
  - `test_flow_studio_connector_account_editor.py` → `test_flow_studio_connector_editor.py`
  - `test_flow_studio_connector_account_navigation.py` → `test_flow_studio_connector_navigation.py`
- Selector sweep across all 22 connector-touching browser test files: `data-testid` strings, `data-*` attribute selectors, JS comment-block filename references (`connector-account-editor.js:...` → `connector-editor.js:...`), URL string assertions, test function names (`def test_connector_account_*` → `def test_connector_*` where the rename was a natural single-line swap). Class names like `TestConnectorAccountEditor` collapsed to `TestConnectorEditor` along the way. `conftest.py` swept for shared fixture references.

**Tests — non-browser hardcoded URLs (4 files, cycle-1 finding):**

- `tests/test_api_connector_accounts.py`: 13 `/api/connector-accounts` URL replacements + 2 `"Connector account not found"` assertion-string replacements.
- `tests/test_api_secret_mask_roundtrip.py`: 8 URL replacements.
- `tests/test_api_connector_account_config_validation.py`: 24 URL replacements (cycle-1 audit's 23 count was off-by-one; actual count rounded up).
- `tests/test_db_api.py`: 106 `/api/connector-accounts` URL replacements (cycle-1's 10 count was a recon undercount; actual surface was an order-of-magnitude larger — the file has dense API-roundtrip coverage) + 6 `/connector-accounts/` replacements for the `/api/agents/{name}/connector-accounts/{id}` detach-route variant + 8 `"Connector account not found"` assertion-string replacements.

**Python substrate, docstring-only fix (cycle-1 finding):**

- `the_one/db/models.py:495`: docstring URL `/api/connector-accounts/{account_id}/peer-approvals/...` → `/api/connectors/{account_id}/peer-approvals/...`. Single-line fix.

**Test results:**

- Backend suite (`pytest --deselect tests/test_provider_repository.py --ignore=tests/browser -x --timeout 60`): **2736 passed, 4 skipped, 30 deselected, 0 failures** in 234.6s. Matches L1 baseline exactly (no count change — L2 introduced no new tests, no test removals).
- Browser suite (`pytest tests/browser/ --timeout 120 -m browser`): **431 passed, 35 skipped, 14 deselected** in 477.1s (~8 min). The 14 deselected = 12 marker-deselected + 2 pre-existing failures on `main` (verified by stash + bisect: `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` expects 4 tabs but sees 5 — pre-L2 / pre-L1 drift since some prior flight added a tab; `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` fails on main with identical assertion error — pre-existing). Both failures reproduce on `git stash`-ed working tree pointed at `main` HEAD; neither was introduced by L2.
- All connector-touching browser tests pass: `test_flow_connector_detach.py`, the 4 renamed `test_flow_studio_connector_*.py` files, `test_flow_studio_connector_{allowlist,discord_form,discord_vocabulary,discoverable_dropdown,dm_admission_row,invite_section,navigation,routing_dropdown}_*.py`, `test_flow_studio_always_listen_toggles.py`, `test_flow_studio_per_agent_*.py`, `test_flow_chat_pending_approval.py`, `test_flow_chat_session_list_source_badge.py`, `test_flow_chat_operator_input_visibility.py`, `test_connector_test_connection_button.py`, `test_flow_studio_navigation.py` (10/10 passed including the post-rename roving-tabindex + arrow-key tests against the renamed `data-section="connectors"`).

**Atomicity boundary verified:**

- `git grep -nE 'connector-account|connector_account|connectorAccount|ConnectorAccount' the_one/interfaces/web/static/ tests/browser/` → zero hits.
- `grep -nE '"/connector-accounts' the_one/interfaces/web/api.py` → zero hits (was 13 at L1 landing).
- `grep -cE '"/connectors[/"]' the_one/interfaces/web/api.py` → 13 (+ 1 at line 519's `/agents/{agent_name}/connectors/{account_id}` not matched by leading-`"/connectors`-prefix pattern = 14 routes total).
- `grep -cE 'f"Connector account not found' the_one/interfaces/web/api.py` → 0 (was 11).
- `grep -cE 'f"Connector not found' the_one/interfaces/web/api.py` → 11.
- `git grep '/api/connector-accounts' -- 'tests/*.py' | grep -v 'tests/browser/'` → zero hits.
- `git diff --name-only main -- ...allowlist exclusions...` returns only L1's previously-touched Python files (L2 introduced no Python-substrate changes outside `api.py` + `db/models.py:495` docstring).

**Notes for L3 designers + Phase 2d reviewer:**

- L2's verification surfaced 2 pre-existing browser-test failures on `main` (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`). Neither is in F11 scope nor caused by L1+L2 — both fail identically on a `git stash`-ed working tree at `main` HEAD. Flagging here so Phase 2d reviewer + future flight planners are aware (candidate for a separate housekeeping flight; not L3 scope per current spec).
- L1 left 6 `"Connector account"` / `"connector account"` prose sites in api.py docstrings (lines 524, 535, 779, 2434, 2461, 2587, 3854) NOT renamed — these surface in OpenAPI/Swagger as endpoint descriptions. L2 spec only enumerated the 2 docstring sites (`:2792`, `:3046`) for rename. If Phase 2d reviewer wants the broader docstring sweep, surface it then.
- Test class names (`TestConnectorAccountRepository`, `TestConnectorAccountAPI`, etc.) in L1-touched test files like `test_db_api.py`/`test_db_repositories.py` were left unchanged per L1 precedent. The 4 renamed browser test files DID have their `class TestConnectorAccount{Editor,Navigation,...}` containers renamed naturally during the L2 file-rename sweep.

---

### L3 housekeeping-bundle — landed 2026-05-28

**Status**: landed (NOT committed; Phase 2d batches).

**agents.md structural sweep:**

- **2 new M11 convention blocks promoted** under `### Mission-specific (M11)` heading:
  - `### \`dms-orthogonal-to-guild-restriction\`` — captures the F10 L1 posture: substrate DM admission is orthogonal to guild restriction, composed via the account-scope `dm_admission` axis plus per-agent `admit_dms` opt-out. Citation traces F10 L1 + `tests/test_connectors_acl.py`.
  - `### \`backend-merged-replay\`` — captures the F9 L4 `_restore_session` shape: merge time-keyed persistent stores (messages + pending_approvals) at the backend before broadcast, not at the frontend. Citation traces F9 L4 at `the_one/interfaces/web/app.py:_restore_session`.
- **`per-axis-tri-state-override` extended from 4 to 5 axes** in lockstep at both sites: convention definition block (added `dm_admission` to the axis list + a fourth-occurrence F10 L1 citation) AND the deep "four parallel axes" application paragraph (now "five parallel axes" with `dm_admission` enumerated as the F10 L1 addition, orthogonal-to-guild posture cross-referenced).
- **2 F9 API endpoint callouts added** under `## Subsystem contracts`, immediately after the `__MASKED__` sentinel section — new `### F9 Discord-native peer-approval + per-agent detach endpoints` subsection enumerating the L2-renamed paths `POST /api/connectors/{connector_id}/peer-approvals/{approval_id}/{approve|dismiss}` (F9 L3) and `DELETE /api/agents/{name}/connectors/{connector_id}` (F9 L5) + the studio-event-bus events each emits.
- **F4-era prose pruned**: 2 stale paragraphs both referencing a no-longer-extant `# F6:` resolver-hook marker in `the_one/tools/connector_send.py`. Verified the marker is gone (`grep -rn "# F6:" the_one/` → zero hits); F6 L3 wired the consult site via direct `admits_outbound` call. Pruned at: (a) `## Connector type extension checklist` item 8 (rewritten to describe the actual F6-landed shape — direct call to `_acl.admits_outbound`); (b) `## Connector subsystem → Outbound contract → Account-scope target validation` paragraph (rewritten to describe the same call site). Net: 2 paragraphs rewritten, ~80 words of F4-era forward-promise prose replaced with current-state description.

**_acl.py deny block retirement (TWO sites — outbound + inbound):**

- **Outbound block at `:163-179`** (`admits_outbound`): 4-line `# Per-agent DMs-only sentinel: ...` comment replaced with 1-line `# Per-agent channels axis is explicitly empty: permit DMs, deny everything else.`; deny string `"(DMs-only override; target is not a DM)"` → `"(per-agent channels axis is explicitly empty)"`. Verb "reachable" preserved (codebase convention for outbound).
- **Inbound block at `:437-454`** (`admits_inbound`): 9-line back-compat comment block referencing the test-pin lineage retired in favor of a 1-line `# Per-agent channels axis is explicitly empty: deny all guild-context messages on this account for this agent.`; deny string `"(DMs-only override; envelope is not a DM)"` → `"(per-agent channels axis is explicitly empty)"`. Now parallels the sibling guilds-axis (`:466-471`) and roles-axis (`:484-489`) message style exactly. Verb "admitted" preserved (codebase convention for inbound).
- **Mechanical verification**: `grep -rn "DMs-only override" the_one/ tests/` → 0 hits after Steps 2 + 3. The only remaining historical references to the phrase live in flight artifacts (this log + the L3 leg spec).

**Test assertion updates (5 sites across 2 files):**

- `tests/test_connectors_acl.py` — 4 sites updated: outbound assertions at `:107` + `:137` (assert `"reachable"` + new tail), inbound assertions at `:322` + `:354` (assert `"admitted"` + new tail). Test method names (`test_per_agent_channels_empty_is_dms_only_sentinel`, `test_per_agent_channels_empty_with_is_dm_false_denies`) preserved as lineage markers per spec.
- `tests/test_connector_send_tool.py:744-745` — 1 site updated: outbound deny-string assertion in `test_deny_when_per_agent_acl_channels_is_empty_dms_only_stub`. Test method name + docstring lineage preserved.

**test_provider_repository.py fixture redesign:**

- `repo` fixture at `:23-30` converted from sync `def repo(encryptor):` + nested `async def _setup()` + `asyncio.get_event_loop().run_until_complete(_setup())` to native `async def repo(encryptor):` consuming `await aiosqlite.connect` + `await ensure_schema` + `await conn.close()` directly. Under `pyproject.toml`'s `asyncio_mode = "auto"`, the async fixture is auto-detected; 13 test consumer sites receive `repo` as a plain value unchanged.
- `import asyncio` at file top removed (now unused — no remaining `asyncio.` references in the file per `grep -n "asyncio\." tests/test_provider_repository.py`).
- 13 `@pytest.mark.asyncio` decorators on test functions left in place (redundant under auto mode but harmless; removal is out of L3 scope per Edge Cases note).

**Test results:**

- Focused `pytest tests/test_provider_repository.py -x --timeout 30` → **13 passed / 0 errors / 0 failures** in 0.30s. The 13 teardown errors carried since F7 are gone; this is the L3-specific regression net.
- Focused `pytest tests/test_connectors_acl.py -x --timeout 30` → **73 passed / 0 failures** in 0.10s.
- Focused `pytest tests/test_connector_send_tool.py -x --timeout 30` → **39 passed / 0 failures** in 4.61s.
- Broad L3 acceptance gate `pytest --ignore=tests/browser -x --timeout 60` (NO `--deselect` workaround) → **2749 passed, 4 skipped, 17 deselected, 0 failures** in 230.04s. Count delta vs L2 baseline (2736): +13 from the previously-erroring `test_provider_repository.py` tests now passing — matches the leg spec's predicted "2749+" gate exactly. Wall time (~230s) is comfortably within ~10% of the L2 baseline (~234.6s). Two `aiosqlite` event-loop-closed `PytestUnhandledThreadExceptionWarning`s surface at teardown but are warnings (not errors/failures) and consistent across the pre-existing test landscape — flagged for L3's reviewer but do not block the acceptance gate.
- Browser suite `pytest tests/browser/ --timeout 120 -m browser` → **431 passed, 35 skipped, 12 deselected, 2 failed** in 489.26s. The 2 failures are precisely the pre-existing-main failures L2 documented (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`); both fail identically on `main` and were not L2- or L3-caused. Carry-forward as documented.

**Atomicity boundary verified:**

- L3 touched exactly the 5 declared surfaces: `the_one/agents.md`, `the_one/connectors/_acl.py`, `tests/test_connectors_acl.py`, `tests/test_connector_send_tool.py`, `tests/test_provider_repository.py`. No L1 or L2 file re-touched.
- `grep -rn "DMs-only override" the_one/ tests/` → 0 hits (the canonical mechanical-verification gate).

---

## Decisions

(empty — populated during execution; planning-time decisions live in flight.md Design Decisions)

---

## Deviations

(empty — populated during execution)

---

## Anomalies

(empty — populated during execution)

---

## Session Notes

(empty — populated during execution)

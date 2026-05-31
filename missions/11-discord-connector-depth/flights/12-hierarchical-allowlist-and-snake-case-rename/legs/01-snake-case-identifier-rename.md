# Leg: snake-case-identifier-rename

**Status**: completed
**Flight**: [Hierarchical Allowlist Axes + Snake_Case Identifier Rename](../flight.md)

## Objective

Close the F11 carry-forward debt: rename all `connector_account` snake_case identifier definitions (function names, method names, test class names, fixture names, test method names) to drop the `_account` suffix — applying the F11 debrief methodology lesson #1 ("grep-gate-scope-is-a-design-decision") by enumerating the search corpus + patterns + allowed residue explicitly in the spec, AND running a literal Phase 5c grep against the codebase before implementation to confirm hit count matches expected scope.

## Context

This is the first of four legs in F12 and a strict prerequisite for L2-L4 — those legs touch `_acl.py`, `repositories.py`, `api.py`, and test fixtures. Doing the rename FIRST avoids re-touching the same files across legs, and validates the F11 debrief's "grep-gate-scope-is-a-design-decision" methodology at low risk (the rename is mechanical; no behavior change).

**Per the flight spec's L1 design decision (Snake_Case Identifier Rename — F11 prereq):**
- Search corpus: `the_one/`, `tests/` (including `tests/browser/`), `the_one/connectors/README.md`, `the_one/agents.md`
- Search patterns: `\bConnectorAccount\b` (PascalCase — verified 0 hits post-F11; included for completeness), `\bconnector_account_id\b`, `\bconnector_account_ids\b`, `\bconnector_account\b` (snake_case word-boundary), AND `connector_account` (substring, capturing function/method/class names)
- Test filenames carrying the term ARE in scope (2 files: `tests/test_api_connector_accounts.py`, `tests/test_api_connector_account_config_validation.py`)
- Allowed residue: schema v23 migration body in `the_one/db/schema.py`; `tests/test_db_migration.py` pre-v23 TestSchemaVN classes pinning historical state (Category A — preserve historical names); historical narration paragraphs in `the_one/agents.md:671` ("renamed from `connector_accounts` by M11 F11 L1 v23") and `the_one/connectors/README.md:312` (Flight 1 prose).

**Pre-implementation literal-grep recon (Phase 5c-style, done at L1 design time)**: actual hit counts verified against live codebase pre-spec-draft:
- `\bConnectorAccount\b` (Python): **0 hits** — F11 closed all PascalCase identifier references
- `connector_account` (Python substring): **277 hits across 20 files**
- `connector_account` (Markdown): **4 hits across 2 files** (agents.md:243, agents.md:671, README.md:312, README.md:418 — agents.md:671 + README.md:312 are KEEP-as-historical-citation; agents.md:243 + README.md:418 are UPDATE-in-L1)
- Test filenames carrying the term: **2** (after the browser-test 4 were already renamed by F11)

A Phase 5c architect cycle will re-run these greps pre-implementation to confirm no drift between leg-design time and implementation time.

## Inputs

- F11 landed (commit `e0a8491` on main)
- Backend baseline: 2749 passed / 4 skipped / 0 errors / ~254s wall
- Browser baseline: 431 passed / 35 skipped / 2 pre-existing-on-`main` failures (not F12-caused)
- F12 branch `flight/12-hierarchical-allowlist-and-snake-case-rename` created from main; flight status `in-flight`
- Uncommitted operator dev state: `docker-compose.yml` carries M11 F7 L12 HAT env vars. **DO NOT stage this file.** Stage Python + Markdown files explicitly.

## Outputs

- All 11 `_connector_account*` FastAPI handler function names in `the_one/interfaces/web/api.py` renamed (with `_account` suffix dropped)
- `SQLiteAgentStore.list_by_connector_account` → `list_by_connector` in `the_one/db/repositories.py` + 3+ production call sites updated
- `_resolve_connector_account_context` → `_resolve_connector_context` in `the_one/tools/connector_history.py` + 4 same-file call sites updated
- 7 test classes renamed (`TestConnectorAccountAPI` → `TestConnectorAPI`, etc.) in `tests/test_db_api.py` and `tests/test_db_repositories.py`
- Fixture `_seed_connector_account` → `_seed_connector` in 2 test files (8+ call sites)
- 10 test methods carrying `connector_account` in their names renamed (drop `_account`)
- 2 test filenames renamed: `tests/test_api_connector_accounts.py` → `tests/test_api_connectors.py`; `tests/test_api_connector_account_config_validation.py` → `tests/test_api_connector_config_validation.py`
- `the_one/db/models.py:259` docstring updated to reference renamed handler functions (`{create,update}_connector` not `{create,update}_connector_account`)
- `the_one/agents.md:243` historical-citation references updated to reflect F11's already-renamed JS file + L1's rename of `renderConnectorAccountEditor`
- `the_one/connectors/README.md:418` updated to reference `list_by_connector(account_id)` instead of `list_by_connector_account(account_id)`
- Flight log L1 progress entry appended
- Leg status `landed` (NOT committed — Phase 2d batches commits)

## Acceptance Criteria

- [x] All 11 FastAPI handler function names in `the_one/interfaces/web/api.py` no longer contain `_connector_account` substring (each renamed with `_account` dropped):
  - `detach_agent_from_connector_account` → `detach_agent_from_connector`
  - `_validate_connector_account_config` → `_validate_connector_config`
  - `_connector_account_response` → `_connector_response`
  - `list_connector_accounts` → `list_connectors`
  - `list_connector_account_types` → `list_connector_types`
  - `get_connector_account` → `get_connector`
  - `create_connector_account` → `create_connector`
  - `update_connector_account` → `update_connector`
  - `delete_connector_account` → `delete_connector`
  - `generate_connector_account_pairing_code` → `generate_connector_pairing_code`
  - `list_attached_agents_for_connector_account` → `list_attached_agents_for_connector`
- [x] `SQLiteAgentStore.list_by_connector_account` (at `the_one/db/repositories.py:89`) renamed to `list_by_connector`. All **4 production call sites** updated (Phase 5c verified): `connectors/_inbound.py:364`, `interfaces/web/app.py:149`, `interfaces/web/api.py:2453`, `interfaces/web/api.py:2826`. Plus 4 docstring references updated. Docstring citations within the method itself updated.
- [x] `_resolve_connector_account_context` (at `the_one/tools/connector_history.py:526`) renamed to `_resolve_connector_context`. All 4 same-file call sites updated (lines 142, 241, 332, 417 per leg-design recon).
- [x] 7 test classes renamed (drop `_Account` from class name; PascalCase boundary):
  - In `tests/test_db_api.py`: `TestConnectorAccountAPI` → `TestConnectorAPI`; `TestConnectorAccountDoctor` → `TestConnectorDoctor`; `TestConnectorAccountPairingCodeAndAttached` → `TestConnectorPairingCodeAndAttached`; `TestConnectorAccountPeerApprovals` → `TestConnectorPeerApprovals`
  - In `tests/test_db_repositories.py`: `TestConnectorAccountRepository` → `TestConnectorRepository`; `TestConnectorAccountConfigValidator` → `TestConnectorConfigValidator`; `TestConnectorAccountSessionContinuation` → `TestConnectorSessionContinuation`
- [x] Fixture `_seed_connector_account` renamed to `_seed_connector` in `tests/test_app_pending_approval_merge.py` (def at line 79) AND `tests/test_db_repositories.py` (def at line 2717); all 8+ call sites updated in lockstep.
- [x] Test method names carrying `connector_account` in their identifier renamed (drop `_account`):
  - `tests/test_db_repositories.py`: 6 `test_list_by_connector_account_*` methods → `test_list_by_connector_*`; `test_fk_cascade_via_connector_account_delete` → `test_fk_cascade_via_connector_delete`
  - `tests/test_db_api.py`: `test_update_connector_account_routing_round_trips` → `test_update_connector_routing_round_trips`; `test_list_connector_accounts_includes_attached_agents_count` → `test_list_connectors_includes_attached_agents_count`
  - `tests/test_provider_api.py`: `test_rotate_connector_account_secrets` → `test_rotate_connector_secrets`
- [x] 2 test filenames renamed via `git mv`:
  - `tests/test_api_connector_accounts.py` → `tests/test_api_connectors.py`
  - `tests/test_api_connector_account_config_validation.py` → `tests/test_api_connector_config_validation.py`
- [x] `the_one/db/models.py:259` docstring updated: `the_one/interfaces/web/api.py:{create,update}_connector_account` → `the_one/interfaces/web/api.py:{create,update}_connector`
- [x] `the_one/agents.md:243` updated: 3 references to current names (the JS file already renamed by F11 L2 to `connector-editor.js`; the JS function `renderConnectorAccountEditor` is now in `connector-editor.js` and likely renamed to `renderConnectorEditor` post-F11 L2; the browser test filename `test_flow_studio_connector_account_create_and_test.py` was renamed by F11 L2 to `test_flow_studio_connector_create_and_test.py`). Implementing developer verifies post-F11 names via grep and updates the citation in lockstep.
- [x] `the_one/connectors/README.md:418` updated: `SQLiteAgentStore.list_by_connector_account(account_id)` → `SQLiteAgentStore.list_by_connector(account_id)`
- [x] **Grep verification gate**: `git grep -rE "\bConnectorAccount\b|\bconnector_account_id\b|\bconnector_account_ids\b|\bconnector_account\b|connector_account" the_one/ tests/ the_one/connectors/README.md the_one/agents.md --include='*.py' --include='*.md'` returns zero hits in SOURCE files. Allowed residue (documented explicitly in the gate output OR excluded via path filtering):
  - `the_one/db/schema.py` migration v17/v21/v23 bodies (historical FROM-side + ALTER ADD COLUMN statements)
  - `tests/test_db_migration.py` pre-v23 `TestSchemaV{17,18,19,21,22}` classes (Category A — pin historical schema state; their `connector_account_id(s)` references describe pre-v23 column names and MUST stay)
  - `the_one/agents.md:671` (historical citation: "renamed from `connector_accounts` by M11 F11 L1 v23")
  - `the_one/connectors/README.md:312` (Flight 1 historical narration: "Flight 1 ships without the CHECK")
  - This flight's own artifacts (flight.md, flight-log.md, leg artifacts)
- [x] `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` is green at 2749+ passing (no test additions in L1; same baseline as F11 land)
- [x] `docker exec the-one pytest tests/browser/ -x --timeout 120` baseline preserved (431+ passing, 2 pre-existing-on-`main` failures persist — not L1-caused)
- [x] Flight log `Leg Progress` section has an L1 entry summarizing changes + test results
- [x] Leg status updated to `landed` in this file's header. **DO NOT commit** — Phase 2d batches.

## Verification Steps

1. **Phase 5c architect grep (pre-implementation)**: an architect agent runs the spec's literal grep against the codebase and confirms the hit count matches the spec's expected list (277 Python hits + 4 Markdown hits + 2 test filenames). If the architect surfaces additional hits beyond the spec's enumeration, fold them into L1 scope before implementation begins.

2. **Backend test suite** (no test additions in L1; identical baseline expected):
   - `docker exec the-one pytest --ignore=tests/browser -x --timeout 60`
   - Must show 2749+ passed / 4 skipped / 0 errors / 0 failures.

3. **Browser test suite** (selectors + filenames already renamed by F11; L1 should not regress):
   - `docker exec the-one pytest tests/browser/ -x --timeout 120`
   - Must show 431+ passed / 35 skipped / 14 deselected / 2 pre-existing-main failures preserved.

4. **Grep verification gate (mechanical)**:
   ```bash
   git grep -rE "\bConnectorAccount\b|\bconnector_account_id\b|\bconnector_account_ids\b|\bconnector_account\b|connector_account" \
     the_one/ tests/ the_one/connectors/README.md the_one/agents.md \
     --include='*.py' --include='*.md' \
     | grep -vE "schema\.py|test_db_migration\.py|agents\.md:671|README\.md:312|missions/" \
     | head
   ```
   Expected output: empty (zero unexpected hits).

5. **Filename verification**:
   - `ls tests/ | grep -E "connector_account"` returns zero results
   - `ls tests/ | grep -E "test_api_connectors|test_api_connector_config"` returns the 2 renamed files

## Implementation Guidance

**Order matters within this leg.** Do production code first (api.py + repositories.py + connector_history.py + models.py docstring), then tests (classes + methods + fixtures), then test filename renames + import path updates, then Markdown citations. Run tests after each phase to catch breakage early; final grep gate runs last.

### Step 1 — Production code renames

**Step 1a — `the_one/interfaces/web/api.py`**: rename 11 handler functions per AC #1. For each:
- Rename the `async def` / `def` declaration (line numbers per recon: 520, 1034, 2412, 2433, 2460, 2481, 2493, 2511, 2586, 2627, 2786)
- Update internal call sites within `api.py` (e.g., `_validate_connector_account_config(account)` → `_validate_connector_config(account)`)
- Update docstrings that reference the function names

**Step 1b — `the_one/db/repositories.py`**: rename `list_by_connector_account` → `list_by_connector` at line 89. Update internal docstring citations. Update production call sites discovered via `grep -rn 'list_by_connector_account' the_one/ tests/`.

**Step 1c — `the_one/tools/connector_history.py`**: rename `_resolve_connector_account_context` → `_resolve_connector_context` at line 526. Update the 4 same-file call sites at lines 142, 241, 332, 417.

**Step 1d — `the_one/db/models.py:259` docstring**: replace `the_one/interfaces/web/api.py:{create,update}_connector_account` with `the_one/interfaces/web/api.py:{create,update}_connector`.

### Step 2 — Test code renames

**Step 2a — Test class renames** (Step 1's function references inside test bodies should be updated when their consuming class is renamed):
- `tests/test_db_api.py`: rename `TestConnectorAccountAPI` (line 539), `TestConnectorAccountDoctor` (line 1037), `TestConnectorAccountPairingCodeAndAttached` (line 1358), `TestConnectorAccountPeerApprovals` (line 1832).
- `tests/test_db_repositories.py`: rename `TestConnectorAccountRepository` (line 1329), `TestConnectorAccountConfigValidator` (line 1532), `TestConnectorAccountSessionContinuation` (line 2502).

**Step 2b — Fixture rename**: `_seed_connector_account` → `_seed_connector` (Phase 5c grep-corrected enumeration):
- `tests/test_app_pending_approval_merge.py:79` (def) + 5 call sites (lines 163, 205, 268, 323, 366)
- `tests/test_db_repositories.py:2717` (def) + **11 call sites** (lines 2739, 2762, 2796, 2827, 2835, 2853, 2868, 2883, 2916, 2944, 2972) — leg-design recon undercounted at 3; Phase 5c verified 11. Implementer should verify count via `grep -n '_seed_connector_account' tests/test_db_repositories.py` returning exactly 12 lines (1 def + 11 call sites) post-rename target should yield exactly 12 lines for the renamed `_seed_connector` (1 def + 11 call sites).

**Step 2c — Test method renames** (drop `_account` from each):
- `tests/test_db_repositories.py`: lines 645, 662, 674, 688, 704, 743, 2969 (6 `test_list_by_connector_account_*` + 1 `test_fk_cascade_via_connector_account_delete`)
- `tests/test_db_api.py`: lines 923, 2479 (2 methods)
- `tests/test_provider_api.py`: line 742 (1 method)

### Step 3 — Test filename renames

- `git mv tests/test_api_connector_accounts.py tests/test_api_connectors.py`
- `git mv tests/test_api_connector_account_config_validation.py tests/test_api_connector_config_validation.py`
- Search for any cross-test imports or pytest collection configs that reference these filenames; update lockstep. Spot-check: `grep -rn 'test_api_connector_account' the_one/ tests/ --include='*.py' --include='*.toml' --include='*.cfg'`.

### Step 4 — Markdown citations

**Step 4a — `the_one/connectors/README.md:418`**: replace `\`SQLiteAgentStore.list_by_connector_account(account_id)\`` with `\`SQLiteAgentStore.list_by_connector(account_id)\``.

**Step 4b — `the_one/agents.md:243`**: this line has 3 stale references from F11 L2's rename of the JS file. The current JS file is `connector-editor.js`; verify the post-F11 function name via `grep -n "renderConnector" the_one/interfaces/web/static/js/areas/studio/connector-editor.js`. Update:
- Path `connector-account-editor.js` → `connector-editor.js` (2 occurrences in the line)
- Function name `renderConnectorAccountEditor` → whatever post-F11 name is (likely `renderConnectorEditor`)
- Browser test filename `test_flow_studio_connector_account_create_and_test.py` → `test_flow_studio_connector_create_and_test.py` (F11 L2 rename)

**Step 4c — Verify `agents.md:671` and `README.md:312` stay**: these are historical-narration paragraphs; do NOT touch them.

### Step 5 — Run tests

```bash
# Backend (must stay green):
docker exec the-one pytest --ignore=tests/browser -x --timeout 60

# Browser (selectors already renamed by F11; L1 should not regress):
docker exec the-one pytest tests/browser/ -x --timeout 120
```

If any test fails because it imports or calls a renamed symbol: update the test in lockstep within L1 (this is acceptance criterion territory, not a divert).

### Step 6 — Grep verification gate

Run the grep gate command from Verification Steps §4. Expected output: empty. If hits surface in non-allowed locations, fold the rename into L1 before signaling [HANDOFF:review-needed].

### Step 7 — Update flight log and leg status

- Append entry to `../flight-log.md` under `## Leg Progress` summarizing: 11 api.py handler renames, 1 repository method rename + N call sites, 1 connector_history helper rename + 4 call sites, 7 test class renames, 1 fixture rename + 8+ call sites, 10 test method renames, 2 test filename renames, 2 Markdown citation updates, test results.
- Update this leg artifact's header `**Status**: in-flight` → `**Status**: landed`.
- Do NOT update the flight-spec leg checkbox (commit leg does that).
- Do NOT commit. Do NOT `git add`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **OpenAPI / swagger auto-generation**: FastAPI handler function names appear in auto-generated OpenAPI spec as `operationId`. Renaming handlers will change `operationId` values; consumers (none expected for this single-user local tool) would see a breaking change. Acceptable for F12's "full consistency" framing.
- **`agents.md:243` is a historical-citation paragraph** narrating a F1 L7 HAT-caught bug. The narrative ITSELF stays (do not delete the paragraph); only the file/symbol references inside it get updated to current names. This preserves the historical lesson while keeping references current.
- **The `pyproject.toml` or pytest collection configs** may reference test files by exact path (unlikely but possible). If `pytest` collection breaks after Step 3's filename renames, search `pyproject.toml`, `pytest.ini`, `conftest.py` for hardcoded filename references and update them.
- **Test method rename collisions**: a renamed method `test_list_by_connector_*` could collide with an existing method name. Pre-check: `grep -n "test_list_by_connector\|test_fk_cascade_via_connector_delete\|test_update_connector_routing_round_trips\|test_list_connectors_includes_attached_agents_count\|test_rotate_connector_secrets" tests/` should return zero results before the rename starts.
- **`docker-compose.yml` discipline (unchanged from F11)**: when L1 lands, explicit `git add <files>` is the rule — never `git add .` or `git add -A` (operator's local HAT env vars must stay out of F12 commits).
- **`tests/test_db_migration.py` Category A discipline**: the file has ~20 `connector_account_id(s)` references inside `TestSchemaV{17,18,19,21,22}` classes. These describe pre-v23 schema state (the column was named `connector_account_id` before F11 L1 v23 renamed it to `connector_id`). DO NOT update these references — they document historical state and changing them corrupts the migration regression net.

## Files Affected

**Production code** (4 files):
- `the_one/interfaces/web/api.py` — 11 handler function renames
- `the_one/db/repositories.py` — 1 method rename (`list_by_connector_account` at `:89`)
- `the_one/tools/connector_history.py` — 1 helper rename + 4 call sites
- `the_one/db/models.py:259` — 1 docstring update

**Test code** (4 files):
- `tests/test_db_api.py` — 4 class renames + 2 method renames
- `tests/test_db_repositories.py` — 3 class renames + 7 method renames + 1 fixture rename + call sites
- `tests/test_app_pending_approval_merge.py` — 1 fixture rename + 5 call sites
- `tests/test_provider_api.py` — 1 method rename

**Test filenames** (2 renames via `git mv`):
- `tests/test_api_connector_accounts.py` → `tests/test_api_connectors.py`
- `tests/test_api_connector_account_config_validation.py` → `tests/test_api_connector_config_validation.py`

**Documentation** (2 files):
- `the_one/agents.md:243` — 3 reference updates within a historical-citation paragraph
- `the_one/connectors/README.md:418` — 1 method-reference update

**Flight artifacts** (mandatory updates per leg-execution protocol):
- `missions/11-discord-connector-depth/flights/12-hierarchical-allowlist-and-snake-case-rename/flight-log.md` — append L1 progress entry
- This file (`legs/01-snake-case-identifier-rename.md`) — status → `landed`

**Explicitly NOT affected in L1**:
- `the_one/db/schema.py` (no schema changes in L1; v24 migration is L3's scope)
- `the_one/connectors/_acl.py` (L2's scope — admits_inbound extraction)
- `the_one/agents.md:671` (historical citation about v23 rename — preserve)
- `the_one/connectors/README.md:312` (Flight 1 historical narration — preserve)
- `tests/test_db_migration.py` pre-v23 TestSchemaVN classes (Category A — preserve historical references)
- Any other test that pins pre-v23 / pre-F11 historical state via comment or fixture
- `docker-compose.yml` (operator's local dev state)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (renames, grep gate, test suite green)
- [x] L1 atomicity boundary verified (no schema/ACL/UI changes)
- [x] Backend suite green at 2749+ passing
- [x] Browser suite preserved at 431+ passing
- [x] Flight-log L1 progress entry appended
- [x] This leg's status set to `landed` (NOT `completed` — Phase 2d commits)
- [x] Do NOT update flight-spec leg checkbox (commit leg does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d batches all 4 legs into one review + one commit)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-29, leg-design time):

| Citation | Classification | Resolution |
|----------|---------------|------------|
| `the_one/interfaces/web/api.py` lines 520, 1034, 2412, 2433, 2460, 2481, 2493, 2511, 2586, 2627, 2786 (11 handler defs) | OK | All 11 verified via `grep -nE "^async def.*connector_account\|^def.*connector_account" api.py` |
| `the_one/db/repositories.py:89` — `async def list_by_connector_account` | OK | Verified |
| `the_one/tools/connector_history.py:526` — `async def _resolve_connector_account_context` + call sites at 142, 241, 332, 417 | OK | All 5 sites verified |
| `the_one/db/models.py:259` — docstring reference to `{create,update}_connector_account` | OK | Verified |
| `tests/test_db_api.py` test class lines 539, 1037, 1358, 1832 (4 classes) | OK | Verified |
| `tests/test_db_repositories.py` test class lines 1329, 1532, 2502 (3 classes) | OK | Verified |
| `tests/test_app_pending_approval_merge.py:79` `_seed_connector_account` def + 5 call sites at 163, 205, 268, 323, 366 | OK | Verified |
| `tests/test_db_repositories.py:2717` `_seed_connector_account` def + 3 call sites at 2739, 2762, 2796 | OK | Verified (additional call sites may exist further down the file; implementing dev verifies via grep) |
| `tests/test_db_repositories.py` test methods at lines 645, 662, 674, 688, 704, 743, 2969 | OK | Verified |
| `tests/test_db_api.py` test methods at lines 923, 2479 | OK | Verified |
| `tests/test_provider_api.py:742` test method | OK | Verified |
| `tests/test_api_connector_accounts.py` and `tests/test_api_connector_account_config_validation.py` test filenames | OK | Verified via `find tests/ -name "*connector_account*"` |
| `the_one/agents.md:243` historical-citation paragraph | OK | Verified by grep; 3 stale references (path + function + browser-test-filename) identified |
| `the_one/connectors/README.md:418` `list_by_connector_account(account_id)` | OK | Verified |
| `the_one/agents.md:671` + `the_one/connectors/README.md:312` (historical narration — PRESERVE) | OK | Verified both are historical narration; L1 leaves intact |
| `tests/test_db_migration.py` ~20 `connector_account_id(s)` references in TestSchemaVN classes (Category A — PRESERVE) | OK | Verified by `grep -nE "connector_account_id" tests/test_db_migration.py` showing only TestSchemaVN class refs |

15+ citations verified clean against current code at leg design time. All references match live state. The literal Phase 5c architect cycle pre-implementation will re-verify counts have not drifted between leg-design and implementation start.

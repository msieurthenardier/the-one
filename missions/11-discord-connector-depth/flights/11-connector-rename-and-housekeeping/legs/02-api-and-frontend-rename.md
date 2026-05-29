# Leg: api-and-frontend-rename

**Status**: completed
**Flight**: [Connector Terminology Rename + Small-Housekeeping Fold-Ins](../flight.md)

## Objective

Atomically swap the URL surface + JS + CSS + all four selector families + browser test selectors + filenames from `connector-account` vocabulary to `connector` vocabulary, in lockstep, so the post-L2 state has zero `connector-account` / `connector_account` hits in any source file under `the_one/interfaces/web/static/` or `tests/browser/` and the operator-facing API + UI present unified vocabulary.

## Context

This is the second of three legs in F11. L1 already renamed the Python substrate (`ConnectorAccount` class, repository, schema v23) and deliberately preserved 14 `/connector-accounts/...` URL routes + 12 `"Connector account not found"` API error-detail strings + all `interfaces/web/static/` content for L2 to swap together. The transient hybrid-vocabulary state (backend says `Connector`, URLs say `connector-account`) ends with this leg.

**Key L1 → L2 handoff items (from flight-log Notes for L2 designers):**
- 14 routes preserved at `/connector-accounts/...` in `the_one/interfaces/web/api.py` at lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673, 2745, 2785, 2849, 3039, 3115 — all rename to `/connectors/...`
- 12 API error-detail strings (`f"Connector account not found: {account_id}"`) at api.py:2487, 2519, 2607, 2620, 2653, 2707, 2762, 2822, 2882, 3080, 3142 + 1 docstring at :3046 + 1 docstring at :2792 — rename to `"Connector not found: ..."` (prose, not type identifiers)
- Test class names like `TestConnectorAccountRepository` left in L1 (don't match `\bConnectorAccount\b` boundary regex); operator may want renamed at Phase 2d reviewer discretion — not in L2 default scope unless this leg touches them naturally during browser test file renames

**Atomicity boundary:** L2 must NOT touch any `.py` file under `the_one/` outside `interfaces/web/api.py` (route paths + error strings only) AND `the_one/db/models.py:495` (a single docstring URL string surfaced by Developer cycle-1 review). For tests, L2 owns: all browser tests, the 4 non-browser test files hardcoding `/api/connector-accounts/...` URL strings (cycle-1 finding), and `tests/browser/seeders.py` (cycle-1 finding). All Python substrate identifiers + classes are L1's work; L3 owns `_acl.py` deny-message retirement + provider-repository fixture redesign + agents.md structural sweep.

## Inputs

- L1 landed (status: landed, uncommitted on branch `flight/11-connector-rename-and-housekeeping`)
- `git diff --name-only main -- 'the_one/interfaces/web/static/' 'tests/browser/'` currently returns empty (L1 boundary intact)
- 14 routes preserved at `/connector-accounts/...` per L1 progress entry
- 22 browser test files reference `connector_account|connector-account` (per recon verification)
- 4 browser test files carry the term in the filename: `test_flow_connector_account_detach.py`, `test_flow_studio_connector_account_create_and_test.py`, `test_flow_studio_connector_account_editor.py`, `test_flow_studio_connector_account_navigation.py`
- 15 files in `the_one/interfaces/web/static/` reference the term:
  - 2 CSS: `studio.css` (~12 rules at lines 794–1599), `admin.css` (1 rule at line 283)
  - 1 HTML: `static/index.html` (2 `<script>` tags at lines 58, 63 loading JS files due for filename rename)
  - 12 JS files (per `grep -rln` output): `chat.js`, `chat/pending-approval-banner.js`, `studio.js`, `studio/agent-editor.js`, `studio/connector-account-editor.js`, `studio/connector-accounts-grid.js`, `studio/connector-form-discord.js`, `studio/connector-form-registry.js`, `studio/connector-vocabulary.js`, `studio/connectors-tab.js`, `studio/discoverable-dropdown.js`, `studio/mcp-server-editor.js`
- Backend test suite green at 2736 / 4 skipped / 30 deselected after L1; L2 verification uses same `--deselect tests/test_provider_repository.py` for the backend run
- Operator local-state callout (unchanged from L1): `docker-compose.yml` carries uncommitted HAT env vars; do NOT stage it

## Outputs

- All 14 API routes at `/api/connectors/...` (was `/api/connector-accounts/...`)
- All 12 error-detail prose strings rendered as `"Connector not found: ..."`
- 15 `interfaces/web/static/` files swept with all 4 selector families renamed in lockstep
- 2 JS filename renames + `<script>` tag updates in `index.html`:
  - `connector-account-editor.js` → `connector-editor.js`
  - `connector-accounts-grid.js` → `connectors-grid.js`
- 4 browser test filename renames + selector updates in all 22 connector-touching browser test files
- Flight log L2 progress entry appended
- Leg status `landed` (NOT committed — Phase 2d batches)

## Acceptance Criteria

- [x] All 14 routes in `the_one/interfaces/web/api.py` previously at `/connector-accounts/...` are now at `/connectors/...` (lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673, 2745, 2785, 2849, 3039, 3115). Path parameter names may stay as `{account_id}` for now (renaming `account_id` → `connector_id` ripples into Python function signatures + repository calls in L1-touched code; out of L2 default scope unless it's a one-line swap).
- [x] Non-browser test files hardcoding `/api/connector-accounts/...` URL strings are updated to `/api/connectors/...` in lockstep. Cycle-1 enumerated 4 files with 54 URL strings: `tests/test_api_connector_accounts.py` (13), `tests/test_api_secret_mask_roundtrip.py` (8), `tests/test_api_connector_account_config_validation.py` (23), `tests/test_db_api.py` (10). Verification: `git grep '/api/connector-accounts' tests/ --include='*.py' | grep -v 'tests/browser/'` returns 0.
- [x] `the_one/db/models.py:495` docstring URL string updated to `/api/connectors/...` (a single one-line docstring fix surfaced by cycle-1; treated as L2-scope to keep the docstring vocabulary in lockstep with the renamed routes).
- [x] `tests/browser/seeders.py` updated: URL string in `seed_connector_account` body at line 119 from `/api/connector-accounts` → `/api/connectors`; function name `seed_connector_account` → `seed_connector` (function-rename ripples to caller sites in browser tests; rename in lockstep within this leg).
- [x] All 12 API error-detail prose strings in `the_one/interfaces/web/api.py` matching `f"Connector account not found: ..."` are now `f"Connector not found: ..."`. Docstring prose mentioning "Connector account" at :2792 and :3046 also renamed (the docstring at :3046 says "404 (Connector account not found)" — this is rendered to operators as a real error message via the docstring → swagger spec path).
- [x] `data-testid` selector values in all 15 `interfaces/web/static/` files renamed from `connector-account-*` to `connector-*` (e.g. `connector-accounts-list` → `connectors-list`; `connector-account-row-{id}` → `connector-row-{id}`; `connector-account-toggle-{id}` → `connector-toggle-{id}`; `connector-account-missing-{id}` → `connector-missing-{id}`; `connector-accounts-empty-state` → `connectors-empty-state`). All 22 browser test files updated to use the renamed selectors.
- [x] `data-*` attribute names renamed in lockstep: `data-connector-account-id` → `data-connector-id`; `data-connector-account-toggle` → `data-connector-toggle` (6 setAttribute / selector sites identified at recon: `pending-approval-banner.js:32`, `studio.js:2064, 2071`, `connectors-tab.js:26, 245, 259-260`). Update both the `setAttribute` calls AND any selector strings that read them.
- [x] CamelCase `dataset` accessor renamed: `element.dataset.connectorAccountId` → `element.dataset.connectorId` (1 site at `studio.js:2077`).
- [x] CSS classes renamed: 15 `.connector-account-*` selector rules in `static/css/studio.css` (lines 794, 795, 797, 798, 800, 801, 813, 814, 926, 936, 939, 952, 1195, 1200, 1599) + 1 in `static/css/admin.css` (line 283) — renamed to `.connector-*` form. JS files that add/remove these classes via `classList.add('connector-account-...')` updated in lockstep.
- [x] 2 JS filenames renamed:
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` → `connector-editor.js`
  - `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js` → `connectors-grid.js`
  - Both `<script src="...">` tags in `the_one/interfaces/web/static/index.html` (lines 58 and 63) updated to reference the renamed paths.
- [x] 4 browser test files renamed:
  - `tests/browser/test_flow_connector_account_detach.py` → `test_flow_connector_detach.py`
  - `tests/browser/test_flow_studio_connector_account_create_and_test.py` → `test_flow_studio_connector_create_and_test.py`
  - `tests/browser/test_flow_studio_connector_account_editor.py` → `test_flow_studio_connector_editor.py`
  - `tests/browser/test_flow_studio_connector_account_navigation.py` → `test_flow_studio_connector_navigation.py`
  - Filename references in conftest.py / pytest collection configs updated if any reference them by exact path
- [x] Verification gate: `git grep -E 'connector-account|connector_account|connectorAccount|ConnectorAccount' the_one/interfaces/web/static/ tests/browser/` returns zero hits in source files (acceptable residue: none; this leg owns the entire surface).
- [x] Verification gate: `grep -nE '"/connector-accounts' the_one/interfaces/web/api.py | wc -l` returns 0 (was 13 from grep + 1 line-519 = 14).
- [x] Verification gate: `grep -nE '"/connectors[/"]' the_one/interfaces/web/api.py | wc -l` returns 14 (the route count after rename — same number, different path).
- [x] `docker exec the-one pytest --deselect tests/test_provider_repository.py --ignore=tests/browser -x --timeout 60` is green at 2736+ passing (no Python regressions from API path / error-string renames).
- [x] Browser test suite is green: `docker exec the-one pytest tests/browser/ -x --timeout 60` passes (the renamed selectors + renamed files all line up).
- [x] Atomicity boundary: `git diff --name-only main -- 'the_one/' ':!the_one/interfaces/web/static/' ':!the_one/interfaces/web/api.py'` returns only L1-touched files (no new Python substrate changes in L2 outside `api.py`).
- [x] Flight log `Leg Progress` section has an L2 entry summarizing changes + test results.
- [x] Leg status updated to `landed` in this file's header. **DO NOT commit** — Phase 2d batches commits.

## Verification Steps

1. **Backend suite** (no Python regressions from URL/error rename):
   - `docker exec the-one pytest --deselect tests/test_provider_repository.py --ignore=tests/browser -x --timeout 60`
   - Expect 2736+ passing / 4 skipped / 30 deselected / 0 failures.

2. **Browser test suite** (the critical regression net — the selector + filename + URL renames must line up):
   - `docker exec the-one pytest tests/browser/ -x --timeout 120`
   - Browser tests can be slower than backend; allow `--timeout 120` per test. Expect all connector-touching tests pass.
   - If a browser test fails because a selector wasn't updated in lockstep, fix in the same leg (this is the textbook lockstep-rename failure mode the spec called out at flight design).

3. **Grep verification gates**:
   - `git grep -nE 'connector-account|connector_account|connectorAccount|ConnectorAccount' the_one/interfaces/web/static/ tests/browser/` → zero hits
   - `grep -nE '"/connector-accounts' the_one/interfaces/web/api.py` → zero hits
   - `grep -cE '"/connectors[/"]' the_one/interfaces/web/api.py` → 14
   - `grep -cE 'f"Connector account not found' the_one/interfaces/web/api.py` → zero (was 11)
   - `grep -cE 'f"Connector not found' the_one/interfaces/web/api.py` → 11+ (the renamed strings)

4. **Filename verification**:
   - `ls the_one/interfaces/web/static/js/areas/studio/ | grep -E 'connector-account|connector-editor|connectors-grid'` → exactly two files, both with the new names
   - `ls tests/browser/ | grep -E 'connector_account|connector_(detach|editor|navigation|create_and_test)'` → exactly 4 files, all with the new names

5. **Smoke test** (optional but operator-confirming):
   - Open the running app at http://localhost:8484/studio, observe the Connectors tab loads, click into a connector, send a test message — the UI never says "Connector Account" anywhere.

## Implementation Guidance

**Order matters.** Do the API rename first (so the JS, when later updated to call the new URLs, has them to hit), then the JS / CSS / selector / data-attr sweep, then file renames + index.html updates, then the browser test sweep + file renames, then run tests.

### Step 1 — Rename 14 API routes + 12 error strings + 2 docstring sites in `api.py`

- For each of the 14 route decorators at lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673, 2745, 2785, 2849, 3039, 3115, replace `/connector-accounts/` with `/connectors/` in the path string. The `{account_id}` path parameter name may stay (it's a Python function arg; renaming would ripple into L1-touched repository code outside L2 scope).
- **Spot-check on `/connector-accounts/types` route** (line 2459): renames to `/connectors/types`. This reads semantically as "types of connectors" (analogous to `/users/types`); the URL is operator-facing only via the Studio create-form. Acceptable; do not invent an alternate path like `/connector-types` without operator input.
- For each of the 11 `f"Connector account not found: {account_id}"` lines (2487, 2519, 2607, 2620, 2653, 2707, 2762, 2822, 2882, 3080, 3142), replace with `f"Connector not found: {account_id}"`.
- For the docstring at :2792 (`"Connector account editor"`) and :3046 (`"404 (Connector account not found): the repo lookup raises"`), rephrase the prose to use `"Connector"` / `"Connector not found"`. These render into operator-visible OpenAPI / Swagger UI via FastAPI's docstring → spec extraction.
- The function/method names like `detach_agent_from_connector_account` (line 519's handler) — these are Python identifiers. Spec design defers identifier renames inside Python code to L1's scope; line-519's handler name was already renamed by L1 if it matched the L1 grep gate. Verify with `grep -n 'def.*connector_account' the_one/interfaces/web/api.py` — should be zero hits post-L1. If any remain, treat as a leftover L1 site to mop up here.

### Step 1b — Update hardcoded URL strings in 4 non-browser test files (cycle-1 finding)

Without this step, the backend suite goes red the moment Step 1 lands. The atomicity boundary was extended to include this surface.

- `tests/test_api_connector_accounts.py` — 13 occurrences of `/api/connector-accounts/...` → `/api/connectors/...`
- `tests/test_api_secret_mask_roundtrip.py` — 8 occurrences
- `tests/test_api_connector_account_config_validation.py` — 23 occurrences
- `tests/test_db_api.py` — 10 occurrences

Verification: `git grep '/api/connector-accounts' tests/ --include='*.py' | grep -v 'tests/browser/'` returns zero hits.

Test filename renames (e.g. `test_api_connector_accounts.py` → `test_api_connectors.py`) are NOT in default scope — they're not driven by selector/URL lockstep, and renaming them ripples into pytest collection invariants. If the Phase 2d reviewer wants the filenames renamed for consistency, defer to that conversation.

### Step 1c — Update `the_one/db/models.py:495` docstring URL (cycle-1 finding)

Single one-line fix: change the `/api/connector-accounts/{account_id}/...` URL string in the docstring to `/api/connectors/{account_id}/...`. This is the only Python-substrate file L2 touches outside `api.py`; spec atomicity boundary explicitly allows this.

### Step 2 — JS sweep across 12 JS files

For each of the 12 JS files in `interfaces/web/static/js/`:

- **`data-testid` values**: rename `connector-account-{thing}` → `connector-{thing}` everywhere. Examples from `connectors-tab.js`: `data-testid='connector-accounts-list'` → `'connectors-list'`; `'connector-account-row-{id}'` → `'connector-row-{id}'`; `'connector-account-toggle-{id}'` → `'connector-toggle-{id}'`; `'connector-account-missing-{id}'` → `'connector-missing-{id}'`; `'connector-accounts-empty-state'` → `'connectors-empty-state'`. Use the JS file as the source of truth for the actual selector strings; the spec's list is illustrative.
- **`data-*` attribute names**: rename `data-connector-account-id` → `data-connector-id`; `data-connector-account-toggle` → `data-connector-toggle`. Update both `setAttribute('data-connector-account-id', ...)` calls (e.g. `connectors-tab.js:245, 260`, `pending-approval-banner.js:32`) AND any selector strings that read them (e.g. `studio.js:2071`).
- **camelCase `dataset` access**: rename `element.dataset.connectorAccountId` → `element.dataset.connectorId`. 1 known site at `studio.js:2077`; verify no others surface during the sweep.
- **API URL strings**: rename any `fetch('/api/connector-accounts/...')` to `fetch('/api/connectors/...')`. This is the lockstep with the L1-deferred routes — the JS must point at the renamed routes after Step 1.
- **CSS class names**: rename `classList.add('connector-account-{thing}')`, `classList.contains(...)`, `querySelector('.connector-account-{thing}')`, etc. — all dropped to `connector-{thing}`.
- **JS variable names + locals**: anything carrying `connectorAccount` (camelCase) or `connector_account` (snake_case, rare in JS) is renamed.
- **In-comment references**: prose comments inside JS that reference `connector-account` get renamed too (the historical context comments are fine to retire — JS comments are not historical-citation artifacts).

### Step 3 — CSS sweep across 2 CSS files

- `the_one/interfaces/web/static/css/studio.css`: rename all `.connector-account-*` selector rules to `.connector-*` form. Recon enumerated lines 794, 795, 797, 798, 800, 801, 813, 814, 926, 936, 939, 952, 1195, 1200, 1599 as the surface (15 selector rules; verify count with grep at implementation time).
- `the_one/interfaces/web/static/css/admin.css`: 1 selector at line 283 (`.connector-account-always-listen-row`) — rename to `.connector-always-listen-row`.
- CSS class renames must align with JS sweep (Step 2's `classList` updates) — keep these two passes coupled mentally even if you edit the files separately.

### Step 4 — JS filename renames + index.html `<script>` tag updates

- `git mv the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js the_one/interfaces/web/static/js/areas/studio/connector-editor.js`
- `git mv the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js the_one/interfaces/web/static/js/areas/studio/connectors-grid.js`
- Update `the_one/interfaces/web/static/index.html` at lines 58 (`/static/js/areas/studio/connector-accounts-grid.js` → `connectors-grid.js`) and 63 (`/static/js/areas/studio/connector-account-editor.js` → `connector-editor.js`).
- Search for any other reference to these JS filenames (e.g. unit tests, template_loader configs): `grep -rn 'connector-account-editor.js\|connector-accounts-grid.js' the_one/ tests/` — should be empty after the rename, modulo flight artifacts that document the historical names.

### Step 5 — `tests/browser/seeders.py` + browser test filename renames + selector sweep across 22 files

**`tests/browser/seeders.py` update (cycle-1 finding):**
- Line 119: `httpx.post(f"{base_url}/api/connector-accounts", ...)` → `f"{base_url}/api/connectors"`. Docstring at line 95 also updated.
- Function rename: `seed_connector_account` → `seed_connector`. This ripples to caller sites in the 22 browser test files — update import-and-call sites in lockstep within this leg (`grep -rln 'seed_connector_account' tests/browser/` gives the exact set; replace `seed_connector_account` → `seed_connector` everywhere).

**Filename renames (4 files):**
- `git mv tests/browser/test_flow_connector_account_detach.py tests/browser/test_flow_connector_detach.py`
- `git mv tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_create_and_test.py`
- `git mv tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_editor.py`
- `git mv tests/browser/test_flow_studio_connector_account_navigation.py tests/browser/test_flow_studio_connector_navigation.py`

**Selector sweep across all 22 connector-touching browser test files** (the 4 renamed + 18 others). Drive the sweep from `git grep -l 'connector_account\|connector-account' tests/browser/` rather than a hardcoded list:
- Update `data-testid` selector strings used in Playwright/browser-test assertions to match the renamed selectors from Step 2.
- Update any URL fetches the tests make directly (rare; tests usually drive the browser to fetch URLs the JS owns) to `/api/connectors/...`.
- Update `seed_connector_account` call-sites to `seed_connector` (covered by the renames above).
- Update test function names that carry the old term (`def test_connector_account_*` → `def test_connector_*`) where reasonable. Class names like `TestConnectorAccountEditor` may stay — the L1 precedent left similar class names untouched (Phase 2d reviewer's call).
- If any test imports from another test file by name (cross-test imports are rare but happen), update the import paths after renaming.

### Step 6 — Run tests

```bash
# Backend suite (must stay green; URL/error rename has no Python ripples beyond api.py):
docker exec the-one pytest --deselect tests/test_provider_repository.py --ignore=tests/browser -x --timeout 60

# Browser test suite (the critical regression net):
docker exec the-one pytest tests/browser/ -x --timeout 120
```

If the backend suite shows regressions: the URL rename probably broke a Python test that hardcodes a URL path. Find with `git grep '/connector-accounts' tests/`. Update the test to use the new path.

If the browser suite shows regressions: most likely a selector wasn't updated in lockstep. Re-grep `connector-account` / `connector_account` across `tests/browser/` and `the_one/interfaces/web/static/` to find the missed site.

### Step 7 — Verify atomicity boundary

L2 is allowed to touch: `the_one/interfaces/web/api.py`, `the_one/interfaces/web/static/`, `the_one/db/models.py:495` (docstring), `tests/browser/`, and the 4 non-browser test files in Step 1b. Use the L1 baseline (`git diff --name-only main` reports the L1 file set as a starting point) to disambiguate L2-introduced changes from L1 residue.

```bash
# This must show only L1's Python files + L2's allowlist — no surprise Python touches outside the allowlist:
git diff --name-only main -- ':!the_one/interfaces/web/static/' ':!the_one/interfaces/web/api.py' ':!the_one/db/models.py' ':!tests/browser/' ':!tests/test_api_connector_accounts.py' ':!tests/test_api_secret_mask_roundtrip.py' ':!tests/test_api_connector_account_config_validation.py' ':!tests/test_db_api.py'
# Expected: only files L1 already touched. If L2 introduced a new .py change outside this set, scope creep.

# Grep gates:
git grep -nE 'connector-account|connector_account|connectorAccount|ConnectorAccount' the_one/interfaces/web/static/ tests/browser/ | head
# Expected: zero hits

grep -nE '"/connector-accounts' the_one/interfaces/web/api.py
# Expected: zero hits

grep -cE '"/connectors[/"]' the_one/interfaces/web/api.py
# Expected: 14

git grep '/api/connector-accounts' tests/ --include='*.py' | grep -v 'tests/browser/' || echo "OK"
# Expected: "OK" (zero hits)
```

### Step 8 — Update flight log and leg status

- Append entry to `../flight-log.md` under `## Leg Progress` summarizing:
  - 14 routes renamed, 12 error strings + 2 docstring prose updated
  - 12 JS files swept across 4 selector families
  - 2 CSS files swept
  - 2 JS filename renames + 4 browser test filename renames
  - Test results (backend + browser counts, timing)
  - Atomicity-boundary verification confirmation
- Update this leg artifact's header `**Status**: in-flight` → `**Status**: landed`.
- Do NOT update the flight-spec leg checkbox to `[x]` (commit leg does that).
- Do NOT commit. Do NOT `git add`. Signal `[HANDOFF:review-needed]` per leg-execution crew's Implement prompt.

## Edge Cases

- **CSS class collisions**: renaming `.connector-account-config-table` → `.connector-config-table` could collide with an existing selector. Run `grep -nE '\.connector-(config|secrets|empty-types|editor|acl|always-listen)-' the_one/interfaces/web/static/css/` BEFORE Step 3 to verify no name collisions. If one exists, prefix the renamed class to disambiguate (e.g. `.connector-section-config-table`) and update JS in lockstep.
- **Path-parameter name leftover**: `{account_id}` in routes paired with `account_id: str` in Python function signatures. Leave as-is unless the rename is one-line trivial; the path parameter is operator-internal and the renaming is L1's scope (already-done if it was in scope) or not-in-scope at all.
- **OpenAPI / swagger artifacts**: FastAPI auto-generates `/openapi.json` from routes + docstrings; no separate spec file to regenerate. The renamed routes + error strings will surface in `/docs` automatically after L2.
- **Browser test fixtures that bootstrap a connector via API**: covered explicitly by Step 5's `tests/browser/seeders.py` updates (Developer cycle-1 caught this — the seeders are in `seeders.py`, not the previously-cited `_browser_helpers.py` which doesn't exist). If any other fixture or conftest file is found to POST `/api/connector-accounts` directly during implementation, fold its URL update into Step 5.
- **The `connector-vocabulary.js` file**: per L1 + flight spec, this file owns the Discord-specific peer→username / channel→channel / group→server vocabulary substitution. Its function names and behavior do NOT change in L2 — only its internal `connectorAccount` variable names + `data-*` references change as part of the sweep. The `peer`/`group`/`channel` → `username`/`server`/`role` substitution stays intact.
- **JS module imports**: vanilla JS (no module system per the project; loaded via `<script>` tags in index.html). Filename renames don't ripple into import statements within JS files. Only the `index.html` script tags need updating (Step 4).
- **Pytest collection ordering**: renaming test files may shuffle pytest's collection order. If a test depends on cross-file ordering, it's already a bug; surface it during the browser-suite run if it appears.
- **Browser-test cache poisoning**: if Playwright cached an old version of the JS, the rename can fail with "no such element" because the browser served the cached `connector-account-editor.js`. Solution: ensure `pytest tests/browser/` invokes a clean browser context (the existing fixtures should handle this, but flag if not).

## Files Affected

**API surface:**
- `the_one/interfaces/web/api.py` — 14 route paths + 11 f-string error details + 2 docstring prose sites

**Frontend — static/ (15 files):**
- `the_one/interfaces/web/static/index.html` — 2 `<script>` tags (lines 58, 63)
- `the_one/interfaces/web/static/css/studio.css` — 15 `.connector-account-*` selector rules (lines 794, 795, 797, 798, 800, 801, 813, 814, 926, 936, 939, 952, 1195, 1200, 1599)
- `the_one/interfaces/web/static/css/admin.css` — 1 `.connector-account-*` selector (line 283)
- `the_one/interfaces/web/static/js/areas/chat.js`
- `the_one/interfaces/web/static/js/areas/chat/pending-approval-banner.js`
- `the_one/interfaces/web/static/js/areas/studio.js`
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` → **rename to** `connector-editor.js`
- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js` → **rename to** `connectors-grid.js`
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js`
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js`
- `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js`
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js`
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js`
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`

**Tests — browser/ (22 files + seeders):**
- 4 filename renames listed in Step 5
- 18 additional files referenced via grep `tests/browser/` swept for selector / URL updates
- `tests/browser/seeders.py` — `seed_connector_account` function rename + URL update + caller updates in the 22 browser test files (cycle-1 finding)

**Tests — non-browser hardcoded URLs (4 files, cycle-1 finding):**
- `tests/test_api_connector_accounts.py` — 13 URL strings
- `tests/test_api_secret_mask_roundtrip.py` — 8 URL strings
- `tests/test_api_connector_account_config_validation.py` — 23 URL strings
- `tests/test_db_api.py` — 10 URL strings

**Python substrate, docstring-only fix (cycle-1 finding):**
- `the_one/db/models.py:495` — single docstring URL string

**Flight artifacts:**
- `missions/11-discord-connector-depth/flights/11-connector-rename-and-housekeeping/flight-log.md` — append L2 progress entry
- This file (`legs/02-api-and-frontend-rename.md`) — status → `landed`

**Explicitly NOT affected in L2:**
- Any `the_one/*.py` file outside `interfaces/web/api.py` AND `db/models.py:495` (substrate is L1's territory; agents.md / `_acl.py` / `test_provider_repository.py` are L3's)
- Test filename renames for the 4 non-browser test files (cycle-1 deferred to Phase 2d reviewer judgment)
- `docker-compose.yml` (operator's local dev state)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (routes, error strings, selectors, filenames, grep gates, tests)
- [x] L2 atomicity boundary verified (no Python substrate changes outside api.py)
- [x] Backend suite green (with same deselect as L1)
- [x] Browser suite green
- [x] Flight-log L2 progress entry appended
- [x] This leg's status set to `landed` (NOT `completed` — Phase 2d commits)
- [x] Do NOT update flight-spec leg checkbox (commit leg does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d batches all three legs into one review + one commit)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-28, leg-design time):

| Citation | Classification | Resolution |
|----------|----------------|------------|
| `api.py` 14 routes at lines 519, 2432, 2459, 2480, 2492, 2510, 2585, 2626, 2673, 2745, 2785, 2849, 3039, 3115 | OK | All 14 verified by `grep -nE '"/connector-accounts'` (13 hits) + line 519 manual confirmation (`/agents/{agent_name}/connector-accounts/{account_id}` decorator) |
| `api.py` 11 error-detail strings at lines 2487, 2519, 2607, 2620, 2653, 2707, 2762, 2822, 2882, 3080, 3142 | OK | All 11 verified by `grep -nE "'?Connector account"` showing 13 hits (11 error strings + docstring at :2792 + docstring at :3046); recon noted L1's flight log cited "12 detail strings" but actual error-string count is 11; the 12th L1-flagged site is the docstring at :3046 which gets renamed in Step 1 |
| `studio.css` 15 selector rules at lines 794, 795, 797, 798, 800, 801, 813, 814, 926, 936, 939, 952, 1195, 1200, 1599 | OK | Verified by `grep -nE "\.connector-account" the_one/interfaces/web/static/css/studio.css` — 15 matches exactly |
| `admin.css:283` `.connector-account-always-listen-row` | OK | Verified; line 283 (architect cycle-1 had said "near 283" — exact match) |
| `index.html:58, 63` `<script>` tags | OK | Verified both lines load the JS files due for rename |
| `studio.js:2077` `dataset.connectorAccountId` | OK | Verified; sole site of camelCase access |
| `studio.js:2064, 2071` + `pending-approval-banner.js:32` + `connectors-tab.js:26, 245, 259-260` data-attr sites | OK | All 6 verified |
| 4 browser-test files with `connector_account` in filename | OK | `ls tests/browser/ | grep connector_account` → exactly 4 files matched |
| 22 browser-test files touching the term | OK | `grep -rln tests/browser/ | wc -l` → 22 |
| 12 JS files touching the term | OK | `grep -rln the_one/interfaces/web/static/js/` → 12 files |

10 citations verified; 0 drift. 0 `gone` flags. One minor count adjustment: recon's "12 error strings" actually decomposes into 11 f-string error details + 1 docstring at :3046 + 1 docstring at :2792 — all renamed in Step 1.

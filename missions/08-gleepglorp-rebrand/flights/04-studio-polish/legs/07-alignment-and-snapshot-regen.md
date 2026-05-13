# Leg: 07-alignment-and-snapshot-regen

**Status**: landed
**Flight**: [Studio Polish](../flight.md)
**Mode**: Mixed (Autonomous Developer for steps 1-5 + 7-9; HAT for step 6; Reviewer + Commit per agentic-workflow Phase 2d for step 10)

## Objective

Close Flight 04 cleanly via the canonical 10-step alignment template: pre-close grep + WCAG audit + rebuild + full Playwright suite (gated on fixing 3 cleanup regressions inherited from Leg 02's uncommitted work) + snapshot baseline regen + operator HAT × 2 themes × 8 pages + `agents.md` F4 subsection + stability rerun + final narrow gate + Reviewer pass + flight-end commit covering Legs 03 + 05 + 06 + 07 cumulative work.

## Context

**Background**: Flight 2/3/3.5 each closed with a 10-step alignment template. Flight 4 inherits that template and additionally absorbs:
- Three pre-existing test regressions surfaced by Leg 02's uncommitted edits that prior legs deferred to Leg 07's cleanup pass.
- The cumulative uncommitted diff from Legs 03 + 05 + 06 (no per-leg commits per the agentic-workflow's "single review + commit at flight end" rule).

**Relevant prior-leg outcomes**:
- Legs 03 + 05 + 06 landed without commits. Working-tree state at Leg 07 kickoff (per the kickoff Flight Director note in the flight log): 12 modified source files + 1 new test file + new leg artifacts.
- Leg 04 was SKIPPED — native `<select>` accepted; mission Known Issue carries forward.
- The 8 polish-flight pages are 4 Studio (Agents grid, Agent editor, MCP Servers grid, MCP Server editor) + 4 Admin (System, LLM Providers, Built-in Tools, Design Language). Chat is NOT in scope (Flight 5 + 6 territory).
- Snapshot baselines are gitignored per user-global convention; step 5 regenerates locally; step 8 verifies stability without `UPDATE_SNAPSHOTS=1`.

**Cleanup pile entering Leg 07** (from prior leg flight-log entries):

| # | Test | Failure | Source |
|---|---|---|---|
| A | `test_flow_dirty_confirm.py` (19 failures) | `.section-nav-header` element not rendered | Leg 02 sidebar header omission |
| B | `test_token_definitions.py::test_every_var_reference_is_defined` | `--toggle-width` undefined in tokens.css; usage at `admin.css:667 — "padding-left: calc(var(--toggle-width, 36px) + 8px)"` (note: fallback value 36px is present but the test asserts every reference has a definition regardless) | Leg 02 admin.css addition |
| C | `test_flow_hash_routing.py::test_hash_routing_admin_subpage_persists_on_refresh` | Timeout waiting for `.app-picker-button` on `#chat` initial load | Leg 02 topbar markup shift |

## Inputs

Files that must exist (verified at design time):
- `the_one/agents.md` — section F4 insertion point after F3.5 at line ~681.
- `tests/browser/test_visual_snapshots.py` — snapshot test file with `@pytest.mark.pixel` marker and `UPDATE_SNAPSHOTS=1` env-var regen mechanism (verified at lines 70 + 172-174).
- `tests/browser/test_flow_dirty_confirm.py` — 19 failing tests + the `_wait_editor_ready` / `_make_dirty` helpers.
- `tests/browser/test_flow_hash_routing.py` — failing `test_hash_routing_admin_subpage_persists_on_refresh`.
- `tests/test_token_definitions.py` — failing `test_every_var_reference_is_defined`.
- `the_one/interfaces/web/static/css/admin.css:667 — "calc(var(--toggle-width, 36px) + 8px)"` — the `--toggle-width` usage site.
- `the_one/interfaces/web/static/css/tokens.css` — where `--toggle-width` definition should land if option (a) is chosen.
- `flight.md` + flight-log + Legs 03/05/06 artifacts — for the commit message description content.

State that must be true:
- Working tree carries Legs 03 + 05 + 06 uncommitted edits intact.
- Flight 04 branch (`flight/04-studio-polish`) checked out.
- Docker container `the-one` running.

## Outputs

After this leg completes:

**Modified files**:
- `tests/browser/test_flow_dirty_confirm.py` — readiness probe(s) updated to match post-Leg-02 sidebar shape (likely the `_wait_editor_ready` helper + any inline assertions on `.section-nav-header`).
- `tests/browser/test_flow_hash_routing.py` — readiness probe in the failing test updated to a reliable post-rebrand selector.
- `the_one/interfaces/web/static/css/tokens.css` OR `the_one/interfaces/web/static/css/admin.css` — `--toggle-width` resolution (whichever option the Developer chooses).
- `the_one/agents.md` — new "### Mission 08 Flight 04 — Studio Polish Layer" subsection inserted after the F3.5 subsection at line ~681+.
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight.md` — status `in-flight` → `landed`; Leg 07 + all checklist items checked off.
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-log.md` — Leg 07 progress entries (per-step results + HAT walkthrough table + Reviewer outcome + commit hash).
- `missions/08-gleepglorp-rebrand/mission.md` — Flight 4 checked off in the Flights list (line ~103).
- This leg artifact — status → `landed`.

**New artifacts**:
- The flight-end commit on `flight/04-studio-polish` branch.
- A draft PR opened against `main` with the leg checklist in the body (per agentic-workflow Phase 3 + Git Workflow conventions).

**Behavior changes**:
- All test suites green post-cleanup.
- Snapshot baselines regenerated locally (gitignored; not in the commit).
- Flight 04 status = `landed`; mission 08 Flight 4 checked off.

## Acceptance Criteria

- [ ] **All 10 steps complete in order** (steps 1-5 + 7-9 autonomous Developer; step 6 HAT; step 10 Reviewer + commit).
- [ ] **Cleanup regression A fixed**: `docker exec the-one pytest tests/browser/test_flow_dirty_confirm.py -q --timeout 30 -m browser` → all 24 tests pass (was 19 failed + 5 passed pre-leg).
- [ ] **Cleanup regression B fixed**: `docker exec the-one pytest tests/test_token_definitions.py -x -q --timeout 30` → green.
- [ ] **Cleanup regression C fixed**: `docker exec the-one pytest tests/browser/test_flow_hash_routing.py -x -q --timeout 30 -m browser` → all tests pass.
- [ ] **Full Playwright suite green**: `docker exec the-one pytest tests/browser/ -q --timeout 30 -m browser` → no failures.
- [ ] **WCAG audit green**: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 30` → 47+ parametrizations pass.
- [ ] **Narrow gate green**: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30`.
- [ ] **MCP/OAuth regression sweep green**: `docker exec the-one pytest tests/test_mcp_client.py tests/test_mcp_stdio_test_connect.py tests/test_mcp_connection_reset.py tests/test_oauth_test_connection_endpoint.py tests/test_oauth_secrets_api.py -x -q --timeout 30` → 100 passed (Leg 03 baseline preserved).
- [ ] **Snapshot baselines regenerated** locally via `UPDATE_SNAPSHOTS=1`.
- [ ] **Snapshot stability rerun green**: 10/12 expected (the 2 `chat_with_messages` baselines are mission Known Issues, NOT this leg's responsibility — operator confirms they're still blocked but verifies the other 10 are clean).
- [ ] **HAT × 16 page-loads complete**: every cell in the page-checklist table marked ✓ / KI; any scope-light visual gaps fixed inline (recorded in flight log); any non-trivial gaps logged as Known Issues.
- [ ] **agents.md F4 subsection added** after the F3.5 subsection. Lean content: ≥3 patterns enumerated (confirmLeave parity; MCP cache schema additions; B2 regression test reference). OPTIONAL additions noted in implementation guidance.
- [ ] **Reviewer pass complete**: spawned Reviewer agent (Haiku) signals `[HANDOFF:confirmed]` on the cumulative flight diff (Legs 03 + 05 + 06 + 07 work). If issues found, spawned Developer fixes them and loops back to Reviewer. Max 3 cycles per agentic-workflow.
- [ ] **Flight-end commit** created on `flight/04-studio-polish` branch with the canonical message format. Code + artifacts in one commit. NO snapshot baseline files in the commit (verify via `git diff --stat HEAD~1 HEAD | grep -v __snapshots__` returns the actual scope).
- [ ] **Draft PR opened** against `main` with the leg checklist in the body (per agentic-workflow Phase 3 / Git Workflow's PR body format).
- [ ] **Flight status `landed`** in flight.md header.
- [ ] **Leg 07 checked off** in flight.md leg list + Completion Checklist.
- [ ] **Flight 4 checked off** in mission.md's Flights list at line ~103.
- [ ] **Leg artifact status set to `landed`**.

## Implementation Guidance

Execute steps in order. Steps 1-5 + 7-9 are autonomous (run by a Developer agent spawned by the Flight Director). Step 6 is HAT (operator-driven). Step 10 is Reviewer + commit per agentic-workflow Phase 2d.

### Step 1 — Pre-close grep (autonomous, ~5 min)

Scan the uncommitted source files for leftover anti-patterns:

```bash
git diff --name-only HEAD | grep -E '\.(js|css|py|md)$' | xargs grep -nE 'TODO|FIXME|XXX|console\.log|debugger|\.skip\(|@pytest\.mark\.skip|breakpoint\(\)' 2>/dev/null
```

For each hit: classify scope-light (delete inline + note in flight log) vs deferred (log as Leg 07 finding, route to a future maintenance pass). Acceptable to have TODOs in the diff IF they reference a future flight / mission Known Issue.

### Step 2 — WCAG audit (autonomous)

```bash
docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 30
```

Expected: 47+ parametrizations all green. If any fail, investigate before proceeding (likely a token-table addition from Leg 02 + 03 work missed a contrast check).

**Ordering note**: this step runs BEFORE `make rebuild` (step 3) intentionally — `test_design_tokens_a11y.py` is a pure-Python test that reads hex values from `tests/browser/design_tokens.py` (a static Python mirror of `tokens.css`). It does NOT touch the built JS/CSS assets, so the rebuild is not a prerequisite. Running it early catches token-contrast regressions cheaply.

### Step 3 — `make rebuild` (autonomous)

```bash
make rebuild
```

Required for the Playwright suite to see the latest JS/CSS changes from Legs 02 + 03 + 05's uncommitted edits.

### Step 4 — Fix 3 cleanup regressions + full Playwright suite (autonomous, ~30 min)

**Sub-task A — `test_flow_dirty_confirm.py` (19 failures, `.section-nav-header` removal)**:

Read `tests/browser/test_flow_dirty_confirm.py:_wait_editor_ready` (around line 37). Current code:

```python
expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)
```

`.section-nav-header` is no longer rendered (`renderSectionNav()` is called without a `header:` option in both studio.js and admin.js — see Leg 05's flight-log entry for the diagnosis). Replace with the aria-label-based readiness signal Leg 05's new test uses:

```python
expect(page.locator('.section-nav[aria-label="Agent Studio sections"]')).to_be_visible(timeout=8000)
```

Apply this fix to `_wait_editor_ready` (top-level helper) AND any inline assertions in the test file that reference `.section-nav-header`. Run a grep first: `grep -n 'section-nav-header' tests/browser/test_flow_dirty_confirm.py` to enumerate sites.

Verify: `docker exec the-one pytest tests/browser/test_flow_dirty_confirm.py -q --timeout 30 -m browser` → 24 passed (or whatever the file's total count is).

**Sub-task B — `--toggle-width` undefined**:

Inspect `the_one/interfaces/web/static/css/admin.css:667 — "padding-left: calc(var(--toggle-width, 36px) + 8px)"`. The token has a fallback value (`36px`), so the runtime CSS resolves the calc correctly even when the token isn't defined. The test `test_every_var_reference_is_defined` does match the token name even inside the `var(--name, fallback)` form — its regex captures `--toggle-width` regardless of whether a fallback follows the comma — so the test failure is real and correct (every referenced token must have a definition; the fallback only protects runtime, not the test's static-analysis contract). The Developer agent should make the **decision**:

- **Option (a) — Define the token** (recommended): add `--toggle-width: 36px;` to `tokens.css` in BOTH theme blocks (`[data-theme="dark"]` + `[data-theme="light"]`) per the canonical "every token in both themes" convention. Document the choice in the flight log.
- **Option (b) — Remove the reference**: replace `var(--toggle-width, 36px)` with `36px` inline at admin.css:667. Only choose this if the token is genuinely single-use AND adding it to tokens.css would imply other consumers should adopt it.

Recommendation: pick (a) — defining the token aligns with the codebase's tokenization convention and provides a single source of truth for any future toggle component. Verify: `docker exec the-one pytest tests/test_token_definitions.py -x -q --timeout 30` → green.

**Sub-task C — `test_hash_routing_admin_subpage_persists_on_refresh` timeout**:

Read `tests/browser/test_flow_hash_routing.py` around the failing test (line ~29: `expect(page.locator(".app-picker-button")).to_be_visible(timeout=5000)`). The Leg 06 HAT confirmed `.app-picker-button` DOES render in real browser usage, so the failure is a fixture/timing issue. Likely causes:

1. The 5000ms timeout is too short post-Leg-02 rebrand (initial paint slower with the new design-language assets).
2. The page is loading `#chat` initially and Chat's init path no longer guarantees the topbar is interactive before this assertion fires.
3. A selector shift — `.app-picker-button` might be wrapped in a new container that delays its render.

Investigation order:
1. Run the test with `--browser-output` or similar to see the actual page state at timeout. Headed run if needed: `docker exec the-one pytest tests/browser/test_flow_hash_routing.py::test_hash_routing_admin_subpage_persists_on_refresh -v --timeout 30 -m browser` and check what the failure trace shows (is `.app-picker-button` ever present?).
2. Grep `the_one/interfaces/web/static/js/app.js` around `renderTopBar()` to find the actual render call site — see if Leg 02's rebrand changed the timing.
3. If the underlying cause is a render-order race, the fix may be a more deterministic readiness probe (e.g., wait for `#app-topbar.ready` if such a class is set OR wait for a specific topbar button by area: `#app-topbar [data-area="chat"]`).

Verify: `docker exec the-one pytest tests/browser/test_flow_hash_routing.py -x -q --timeout 30 -m browser` → green.

**Fallback (per Edge Cases section)**: if the root cause is not identified after the investigation steps above and would require a non-trivial render-order change in app.js, defer this single test as a `pytest.mark.skip` with a Known Issue reference rather than blocking the close. Document the deferral in the flight log. Do NOT push past the green-suite acceptance criterion without explicit operator approval — but the explicit operator approval for THIS specific deferral is implicitly granted in this edge-case clause.

**Full Playwright suite**:

After all 3 cleanup regressions are fixed, run the full suite:

```bash
docker exec the-one pytest tests/browser/ -q --timeout 30 -m browser
```

Expected: all tests pass, including the new 4 from Leg 05's `test_flow_cross_area_dirty_gate.py`. If any test fails that wasn't in the cleanup pile, investigate before proceeding.

### Step 5 — Snapshot baseline regen (autonomous, local-only)

```bash
docker exec the-one env UPDATE_SNAPSHOTS=1 pytest tests/browser/test_visual_snapshots.py -q --timeout 60 -m pixel
```

Note the `pixel` marker. Per the project's `pyproject.toml` default `-m 'not pixel'` config (per mission.md Known Issue about pixel tests being excluded by default), this is a separate run. Baselines write to `tests/browser/__snapshots__/` (gitignored per user-global convention).

Expected: all baselines regenerate successfully. The 2 `chat_with_messages` baselines may still fail to regenerate due to the `app_with_agent.session-agent-badge` fixture bug (per mission.md Known Issue) — this is acceptable for this leg; document in the flight log and proceed.

### Step 6 — HAT × 2 themes × 8 pages (operator-driven)

Operator walks every Studio + Admin page in dark theme first, then light theme (per "land dark, port light" cadence established in Flight 3.5).

**8 pages**:

| # | Area | Page | Route |
|---|---|---|---|
| 1 | Studio | Agents tile grid | `#studio/agents` |
| 2 | Studio | Agent editor (any agent, General tab) | `#studio/agents/{name}/general` |
| 3 | Studio | MCP Servers tile grid | `#studio/mcp-sources` |
| 4 | Studio | MCP Server editor (any source) | `#studio/mcp-sources/{id}` |
| 5 | Admin | General (system settings) | `#admin/general` |
| 6 | Admin | LLM Providers grid + editor | `#admin/providers` |
| 7 | Admin | Built-in Tools grid + editor | `#admin/tools` |
| 8 | Admin | Design Language gallery | `#admin/design-language` |

**16-page-load HAT checklist** (operator fills in during walkthrough):

| Page | Dark | Light | Notes / fixes |
|---|---|---|---|
| 1. Studio Agents grid | | | |
| 2. Studio Agent editor | | | |
| 3. Studio MCP Servers grid | | | |
| 4. Studio MCP Server editor | | | |
| 5. Admin General | | | |
| 6. Admin LLM Providers | | | |
| 7. Admin Built-in Tools | | | |
| 8. Admin Design Language (dev_mode only) | | | |

**Walkthrough cadence**:

1. Operator opens each page in dark theme; reports any visual gaps per page.
2. Flight Director applies scope-light fixes inline (CSS tweaks, minor JS markup adjustments — Legs 02 + 03 + 05 + 06 + 07 surface files are all uncommitted, so additions are part of the flight-end commit).
3. After all 8 pages cleared in dark, operator toggles to light theme via the system-level toggle.
4. Operator walks each page again in light; reports.
5. Non-trivial gaps (architectural, multi-file, requires new tests) → logged as Known Issues in mission.md OR routed to Flight 5 / 6 (Chat polish flights) if surface-overlapping.

### Step 7 — `agents.md` F4 subsection (autonomous, post-HAT)

Insert a new subsection after the F3.5 subsection at `the_one/agents.md:681+` (after the existing `### Mission 08 Flight 3.5 — Shell Chrome Polish Layer`). Use the established subsection format from F2 / F3 / F3.5 as the template.

**Lean content** (per Architect framing — only `App.dropdown` was the planned F4-original pattern, and Leg 04 was skipped):

```markdown
### Mission 08 Flight 04 — Studio Polish Layer (MCP polish + dirty-gate parity)

**Studio dirty-gate parity** (Leg 05). Studio's area descriptor now exposes the
`confirmLeave(proceed, abort)` hook, mirroring admin's pattern from F3 L06. The
hook delegates to a `_confirmLeaveImpl` closure inside `init()` that closes over
the local `dirty` flag. Same predicate as the existing sidebar inline gate:
`dirty && inEditor` where `inEditor` covers both agent-editor and mcp-server-editor
mount contexts. The sidebar `onSelect` gate now delegates to the same impl for
DRY — single source of truth for the dirty predicate.

**Stale-then guard** (Leg 05). Studio's `fetchMcpSources_().then(() => tryConsumePendingMcpSource())`
continuation now guards `if (self._activeSection !== 'mcp-sources') return;` to
prevent `tryConsumePendingMcpSource` from firing after the user navigated away.
Mirrors admin's stale-then convention from F3 L06.

**MCP cache schema additions** (Leg 03). The MCP source `_cache` payload now
persists `meta` (the spec-optional `InitializeResult._meta`), `protocol_version`
(the negotiated MCP protocol version), and the GET `/api/mcp-sources/{id}` response
now includes `has_access_token: bool` for race-free post-OAuth state polling.
Source: `the_one/mcp/client.py:MCPClient.meta` + `api.py:_serialize_source` +
`api.py:_build_and_test_no_auth_mcp` / `_build_and_test_stdio_mcp` / oauth Phase A.

**OAuth popup-loop fix** (Leg 03). The `/api/oauth/callback` HTML page now posts
a result message via `window.opener.postMessage` before auto-closing. Studio's
`launchConsentPopup` polls `GET /api/mcp-sources/{id}` for `has_access_token: true`
from popup-open onward (postMessage-independent — Cloudflare's COOP severs
`window.opener`). Race-condition window between popup auto-close and SDK token
exchange is closed by the polling state machine.

**Cross-area dirty-gate B2 regression test** (Leg 05). A new parametrized Playwright
test file `tests/browser/test_flow_cross_area_dirty_gate.py` locks 4 scenarios
across admin + studio (cancel-keeps-state + confirm-navigates-cleanly per area).

**Per-tool MCP tile body restructure** (Leg 03). The MCP source editor's tool
list per-tool tile now renders the description ("PROMPT") and input schema as
two separate labeled sections in the tile body, replacing the prior nested
`<details>` schema collapsible.

**Server-info section** (Leg 03 functional batch). The MCP source editor now
surfaces server-declared identity (icon, title/name, version, protocol version,
website URL, capability flags), instructions (collapsible), and `_meta`
(collapsible, when present) above the Tools section. Information flows on the
page (no tile container) per operator direction at vibe close.
```

Operator can prune sections if any feel over-documented; the goal is just to leave breadcrumbs for future flights that touch the same code paths.

### Step 8 — Stability rerun (autonomous)

Two separate commands — behavior tests and snapshot tests have different pytest markers:

```bash
# Behavior tests (default suite, excludes pixel/snapshot tests)
docker exec the-one pytest tests/browser/ -q --timeout 30 -m browser

# Snapshot stability — explicit `pixel` marker (otherwise excluded by pyproject default `-m 'not pixel'`)
docker exec the-one pytest tests/browser/test_visual_snapshots.py -q --timeout 60 -m pixel
```

Behavior tests should all pass (same green expectation as step 4). Snapshot tests should pass against the regenerated baselines from step 5 — expect 10/12 (the 2 `chat_with_messages` baselines remain mission Known Issues per the `app_with_agent` fixture's `session-agent-badge` population issue).

### Step 9 — Final narrow gate (autonomous)

```bash
docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30
```

Same 4-module gate used Legs 01-06. Must be green.

### Step 10 — Reviewer pass + commit (Flight Director orchestrates)

Per agentic-workflow Phase 2d:

1. **Spawn Reviewer agent** (Haiku per the project's `.flightops/agent-crews/leg-execution.md`). Prompt the reviewer with the "Review" template from leg-execution.md, scoped to the cumulative flight diff (`git diff main` or equivalent to capture everything since the last commit on main).

2. **If issues found**, spawn a Developer agent (Sonnet) with the "Fix Review Issues" prompt + reviewer feedback. Loop max 3 cycles per spec.

3. **After `[HANDOFF:confirmed]`**, the Developer creates the commit:
   - Stage all the working-tree edits + the new test file + all artifact updates.
   - **Verify no snapshot baselines are staged**: `git status --short | grep __snapshots__` should return empty (baselines are gitignored).
   - Commit message:
     ```
     flight/04: Studio Polish — MCP polish, OAuth fix, dirty-gate parity, routing sweep, final alignment

     Mission: 08
     ```
   - The Developer must update statuses + checkoffs as part of the same commit:
     - `flight.md` status → `landed`
     - This leg artifact status → `landed`
     - Leg 07 checked off in flight.md leg list + Completion Checklist
     - Flight 4 checked off in mission.md Flights list

4. **Open draft PR** against `main` per the agentic-workflow Git Workflow PR body format:

   ```markdown
   ## Studio Polish

   Page-by-page polish pass across the Studio area + the cumulative
   structural and functional work from Legs 03 + 05 + 06 + 07.

   **Mission**: GleepGlorp AI Rebrand & UX Polish

   ## Legs

   - [x] `01-prep-and-debrief-debt-close` — Flight 3.5 debrief debt close
   - [x] `02-agents-polish` — Agents area vibe polish + agent rename + MCP server-info functional batches
   - [x] `03-mcp-sources-polish` — MCP source editor polish + OAuth popup-loop fix + Server-info section + `_meta` / `protocol_version` capture
   - [x] `04-custom-dropdown-component` — SKIPPED (operator decision; native `<select>` accepted; mission Known Issue carries forward)
   - [x] `05-studio-dirty-gate-parity-and-b2-regression-test` — `confirmLeave` parity + stale-then guard + Playwright B2 test
   - [x] `06-studio-routing-sweep` — HAT walkthrough of 12 routes × 3 transitions + 5 dirty-gate smoke checks; all passed
   - [x] `07-alignment-and-snapshot-regen` — 10-step close; 3 cleanup regressions fixed; agents.md F4 subsection; final commit
   ```

## HAT Walkthrough Protocol (Step 6 detail)

**Prerequisites** (Flight Director ensures these before starting):

1. Steps 1-5 complete + green (autonomous Developer signed off).
2. Browser open, DevTools Console visible.
3. Operator can toggle theme via the system theme toggle (admin → General page typically; or wherever the theme toggle lives).
4. At least one seeded agent + one seeded MCP source available (carryover from Leg 06's HAT).
5. **`dev_mode = true`** for the operator's environment — required for HAT page #8 (Design Language gallery), which is gated by `window.App.config.dev_mode` in `admin.js:129-130`. Verify before starting: open `#admin` and check the sidebar has a "Design Language" category in the listing. If not, page #8 is unreachable and the operator should either enable dev_mode (typically a setting in the project config) OR mark page #8 N/A in the HAT table.

**Cadence**: Flight Director presents 1-2 pages at a time. Operator opens the route, eyeballs the page, reports back with a result symbol (✓ / KI / fix-needed) plus any specific notes. Flight Director records in the checklist table + applies scope-light fixes inline.

Theme order: **dark first** (the design-language anchor — Flight 2 + 3.5 landed dark first then ported light). After all 8 pages clear in dark, toggle to light + run again.

**Acceptance per page**:
- ✓ — reads on-brand, no visual gaps, console clean.
- KI — visual gap noted but logged as Known Issue (mission.md or future flight); not blocking the close.
- fix-needed — scope-light gap; Flight Director applies inline edit, operator re-verifies, mark ✓.

If the operator surfaces a non-trivial gap (e.g., a full component needs rework): pause, log as a Known Issue, route to a future polish flight, mark KI.

## Reviewer + Commit Protocol (Step 10 detail)

**Reviewer prompt template** (from `.flightops/agent-crews/leg-execution.md`):

```
role: reviewer
phase: leg-review
project: the-one
flight: 04
leg: 07
action: review

Review all changes since the last commit on main. Evaluate against:
1. Leg acceptance criteria — are all criteria met across Legs 03 + 05 + 06 + 07?
2. Code quality — style, clarity, maintainability.
3. Correctness — edge cases, error handling, security.
4. Tests — coverage, meaningful assertions, no regressions.
5. Artifacts — flight log updated, leg statuses correct.

Cumulative scope of this commit: Legs 03 (MCP polish + OAuth fix + Server-info
+ _meta/protocol_version capture), 05 (confirmLeave parity + stale-then guard +
B2 regression test), 06 (no code changes), 07 (3 cleanup regression fixes +
agents.md F4 subsection + finalization).

Signal [HANDOFF:confirmed] if all changes are satisfactory.
If issues found, list them with severity (blocking/non-blocking) and specific
file:line references.
```

**Pre-commit safety check** (the Developer agent commits, but Flight Director verifies):
- `git status --short | grep __snapshots__` — must return empty (no baselines).
- `git diff --stat HEAD` — review the file list for unexpected paths.
- No `.env`, `credentials.json`, or similar sensitive paths.

**Commit message HEREDOC pattern** (per the user's global git workflow):

```bash
git commit -m "$(cat <<'EOF'
flight/04: Studio Polish — MCP polish, OAuth fix, dirty-gate parity, routing sweep, final alignment

Mission: 08

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Edge Cases

- **HAT surfaces a fix needing a multi-file edit**: scope-gate (per Leg 06 protocol): if ≤10 LOC AND no new abstractions AND no test changes, apply inline; otherwise log as Known Issue. Trust the gate — finish the close.

- **Step 8 stability rerun fails on a NEW snapshot baseline that step 5 just regenerated**: indicates a non-determinism in the render (animation timing, font loading, etc.). Investigate; if root cause is identifiable inline (e.g., add a wait-for-stable assertion), fix. Otherwise log as Known Issue + mark the specific baseline as the new entry on the `chat_with_messages` pattern's list of "deferred snapshots."

- **Reviewer surfaces a high-severity issue not anticipated in the leg acceptance criteria**: spawn Developer to fix, re-run Reviewer. Max 3 cycles per spec. If still unresolved after 3, escalate to operator with the unresolved issue summary.

- **`agents.md` F4 subsection insertion conflicts with the gitignored / locked region**: unlikely — `agents.md` is a normal markdown file with sequentially-added flight subsections. If there's an unexpected gate (e.g., the file is auto-generated), pause and flag to operator.

- **Pre-existing `chat_with_messages` snapshot blocker is now somehow unblocked**: bonus win; let the 2 baselines regenerate; document.

- **`make rebuild` fails**: investigate (likely a syntax error in one of the uncommitted JS/CSS files). Fix inline, re-rebuild.

- **The cleanup regression C fix is harder than expected** (e.g., requires a non-trivial render-order change in app.js): log as Known Issue, mark the regression as "deferred to Flight 5 / 6 / maintenance pass", and the Playwright suite remains 1-test red. Document the deferral; do NOT push past the green-suite acceptance criterion without explicit operator approval.

- **Working-tree preservation breach**: the Leg 07 autonomous Developer MUST NOT revert prior-leg work. The legs' uncommitted edits are intentional and ship in the final commit. Pre-flight + post-flight `git status` snapshots should show:
  - **Pre-Leg-07** (when Developer starts): 12 modified files + 1 new test file + 4 untracked leg artifacts (legs 03/05/06 + this 07 artifact).
  - **Post-Leg-07-prep, pre-commit**: same files modified + maybe 1-2 additional fixes from cleanup regressions + the agents.md edit.
  - **Post-commit**: clean working tree on `flight/04-studio-polish` branch with the single new commit.

## Files Affected

**Definitely touched** (autonomous Developer):
- `tests/browser/test_flow_dirty_confirm.py` — readiness probe fix
- `tests/browser/test_flow_hash_routing.py` — readiness probe / timing fix
- `the_one/interfaces/web/static/css/tokens.css` OR `the_one/interfaces/web/static/css/admin.css` — `--toggle-width` resolution
- `the_one/agents.md` — F4 subsection insertion

**Definitely touched** (artifact updates):
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/legs/07-alignment-and-snapshot-regen.md` — this file, status update
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight.md` — status + checkoffs
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-log.md` — Leg 07 progress entries
- `missions/08-gleepglorp-rebrand/mission.md` — Flight 4 checkoff at the Flights list

**Possibly touched** (HAT scope-light fixes):
- Any Studio / Admin source file (`studio.js`, `admin.js`, `studio.css`, `admin.css`, sub-modules) — if HAT surfaces a fixable visual gap.

**Out of scope** (must NOT be reverted):
- All Legs 03 + 05 + 06 uncommitted edits (preserve intact, ship in the final commit).

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:flight]`**:

- [ ] All 10 steps complete + verified green per the verification commands.
- [ ] HAT checklist table fully populated (✓ / KI per cell).
- [ ] `agents.md` F4 subsection inserted, lean content.
- [ ] Reviewer pass: `[HANDOFF:confirmed]`.
- [ ] Pre-commit safety check: no `__snapshots__` paths in staged changes; no sensitive files.
- [ ] Single flight-end commit created with canonical message.
- [ ] Draft PR opened against `main` with the leg checklist body.
- [ ] Flight.md status → `landed`.
- [ ] Leg 07 artifact status → `landed`.
- [ ] Leg 07 checked off in flight.md leg list + Completion Checklist.
- [ ] Flight 4 checked off in mission.md Flights list.
- [ ] Flight log updated with Leg 07 progress entries (per-step results + HAT table + Reviewer outcome + commit SHA + PR URL).
- [ ] Signal `[COMPLETE:flight]`.

## Citation Audit

Citations in this artifact verified against current HEAD (uncommitted-state-aware) code at design time (2026-05-13):

| Citation | Form | Resolution |
|---|---|---|
| `the_one/agents.md:681` (F3.5 subsection — F4 insertion point) | line + symbol | OK at HEAD. Confirmed via `grep "^### Mission 08"` — F2 at 585, F3 at 631, F3.5 at 681. |
| `tests/browser/test_visual_snapshots.py` (snapshot test file) | file reference | OK at HEAD. `@pytest.mark.pixel` at line 172; `UPDATE_SNAPSHOTS=1` env-var check at line 70. |
| `tests/browser/test_flow_dirty_confirm.py:_wait_editor_ready` (helper around line 37) | file + symbol | OK at HEAD. Inherited from Leg 05 flight-log diagnosis. |
| `tests/browser/test_flow_hash_routing.py:29 — "expect(page.locator(\".app-picker-button\"))"` | line + snippet | OK at HEAD. Inherited from Leg 06 failure trace. |
| `the_one/interfaces/web/static/css/admin.css:667 — "padding-left: calc(var(--toggle-width, 36px) + 8px)"` | line + snippet | OK at HEAD (in the Legs 02 uncommitted edit). Single usage site; fallback value 36px present. |
| `the_one/interfaces/web/static/js/areas/admin.js:625-636` (admin's `_confirmLeaveImpl` pattern) | line range | OK at HEAD. Referenced from agents.md F4 subsection content. |
| `the_one/mcp/client.py:MCPClient.meta` (new property) | symbol | OK at HEAD (uncommitted from Leg 03). |
| `tests/browser/test_flow_cross_area_dirty_gate.py` (Leg 05 new) | file reference | OK at HEAD (uncommitted). 4 parametrized tests. |
| `the_one/interfaces/web/api.py:_serialize_source` (where `has_access_token` was added) | symbol | OK at HEAD (uncommitted from Leg 03). |
| `mission.md:103` (Flight 4 checkoff point) | line | Approximate; the Developer agent should grep for the actual checkoff line at commit time. |
| `pyproject.toml` `-m 'not pixel'` config (referenced in step 5 commentary) | non-line | Inherited from mission.md Known Issue about pixel tests being excluded by default. |

11 citations verified clean. 1 approximate (mission.md:103 Flight 4 checkoff) marked as such — to be resolved at commit time via grep. No drift correction needed at design time (Leg 07 mostly references uncommitted-state files which prior leg flight-logs already diagnosed at the durable-symbol level).

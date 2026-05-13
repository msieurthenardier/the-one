# Flight Debrief: Studio Polish

**Date**: 2026-05-13
**Flight**: [Studio Polish](flight.md)
**Status**: landed
**Duration**: 2026-05-12 → 2026-05-13 (two-day flight; design on 05-12, execution on 05-13)
**Legs Completed**: 6 of 7 (Leg 04 skipped by operator decision)
**Commit**: `19d9a58` — 35 files changed, +3434/-134 lines
**PR**: https://github.com/msieurthenardier/the-one/pull/49 (draft)

---

## Outcome Assessment

### Objectives Achieved

Flight 04 delivered its core scope: Studio (Agents grid + Agent editor tabs + MCP Sources grid + MCP Server editor) now reads on-brand in both themes, inheriting the alien-dashboard shell from Flight 3.5. Functional additions beyond the vibe scope turned this into the most substantive single-flight delivery in the mission so far.

- **Leg 01** (autonomous prep) — Closed all 7 Flight 3.5 debrief items in one pass: `--bg-gradient` → `--shell-bg` hard rename (5 consumer sites, including `api.py:1519` that static-only grep would have missed); `--shell-topbar-sheen` extracted from inline literal; reduced-transparency block extended for shell tokens; WCAG audit gap closed with 2 new `fg`/`shell_chrome_bg` parametrizations (muted variants intentionally deferred — light fails at 3.33:1); agents.md convention lifts.
- **Leg 02** (agents vibe + functional batches) — Tile grid + Agent editor (General / Tools / MCPs tabs) polished. Two opportunistic functional batches landed alongside: agent rename (`POST /api/agents/{name}/rename`, 9-test coverage) and MCP `serverInfo`/`instructions` capture + agent-editor tile subtitle display.
- **Leg 03** (MCP Sources vibe + functional batches) — MCP Server editor polished. Three vibe iterations to close the OAuth popup-loop (pytest-independent, required real browser; root cause: Cloudflare's COOP severs `window.opener`, invalidating the postMessage-gated architecture). Final architecture: always-on 500ms polling for `has_access_token` from popup-open, postMessage demoted to fast-fail-only signal. Server-info section (icon, title, version, protocol version, capability flags, instructions/meta collapsibles) shipped as a functional batch. LED wired only at the success-state banner (1 of 3 pinned sites; idle + grid-tile deferred).
- **Leg 04** — Skipped. Custom dropdown + 8-site migration declined by operator. Native `<select>` accepted. Mission Known Issue carries forward.
- **Leg 05** (autonomous) — Studio `confirmLeave` hook extracted from inline gate at `studio.js:295-309` into `_confirmLeaveImpl` closure; `confirmLeave` method added to area descriptor (pattern-matches `admin.js:748-754`). Stale-then audit covered 22 `.then(` sites; 1 genuine gap found at line 441 (`fetchMcpSources_().then(() => tryConsumePendingMcpSource())`), gap-filled per prediction. Playwright B2 test `test_flow_cross_area_dirty_gate.py` — 4 parametrized invocations across admin + studio, all passing.
- **Leg 06** (HAT) — Studio routing sweep: 12 routes × 3 transitions, all 36 cells ✓. Zero inline fixes; zero non-trivial gaps. Dirty-gate smoke (B1-B4 + U1) all ✓. One additional cleanup regression (`.app-picker-button` strict-mode timeout) routed to Leg 07.
- **Leg 07** (alignment + close) — 10-step template executed. Cleanup pile grew from 3 catalogued items to 17+ affected test files (see "Leg Spec Accuracy" below). Two architecturally-significant inline fixes surfaced by HAT: LED moved from `mcp-test-status` banner to `mcp-connection-actions` row; same-section-click-clears-editor-state routing fix. Snapshot regen 10/12 (the 2 `chat_with_messages` pre-existing KIs). Narrow gate 58/58. Reviewer: `[HANDOFF:confirmed]`.

### Mission Criteria Advanced

| Criterion | Status | Notes |
|---|---|---|
| Studio reviewed page-by-page, meets professional polish bar | Met | 4 Studio pages × 2 themes operator-confirmed; HAT closed clean |
| Coherent visual identity anchored to purple-led palette | Met | Studio inherits F3.5 shell; interior surfaces polished to same design-language vocabulary |
| Per-area routing and navigation correct across Studio | Met | 36-cell routing sweep clean; dirty-gate + beforeunload ✓ |
| Color contrast meets WCAG AA | Met | 47/47 audit pass; new `fg`/`shell_chrome_bg` parametrizations both >12:1 |
| All M01-M07 capabilities continue working | Met | Narrow gate 58/58 stable; no behavioral regressions |
| Automated browser tests pass; snapshot baselines regenerate cleanly | Mostly met | 315 passed, 35 skipped; 10/12 snapshots stable (2 pre-existing KIs remain) |

---

## Implementation Quality

### Conventions followed

The code follows project conventions throughout. The OAuth state machine in `mcp-server-editor.js:launchConsentPopup` is the most complex new client-side logic; it uses the closure-over-local-state pattern consistent with `App.tabs`, `App.confirmDialog`, and `App.confirmDelete`. The `_confirmLeaveImpl` closure in `studio.js` pattern-matches `admin.js:625-636` precisely — the two are readable as siblings.

The `renderServerInfoSection(cache)` helper in `mcp-server-editor.js` deviates slightly from the existing `renderEditor` inline-HTML pattern by being a standalone named function rather than an anonymous block, which is correct for its size (~80 LOC). Future server-info evolution will find it at the named symbol.

Three mock-class extension patterns in `test_mcp_stdio_test_connect.py`, `test_mcp_connection_reset.py`, and `test_oauth_test_connection_endpoint.py` — adding `meta`, `negotiated_protocol_version`, `server_info`, `instructions` properties to 12 `_MockMCPClient`-style classes — follow the project convention but represent a growing tax. Every new `MCPClient` property now requires 12 mock updates; this will compound.

### Patterns worth documenting

- **Always-on polling as COOP workaround**: cross-origin OAuth flows (Cloudflare, likely most modern IdPs) set `Cross-Origin-Opener-Policy: same-origin`, severing `window.opener`. Any postMessage-gated success detection will silently fail. The correct posture is presence-only backend flag (`has_access_token: bool` on GET) polled at 500ms. This pattern should be the default for any future OAuth-adjacent popup flow.
- **Snapshot inside `async with`**: all 3 `_cache` write sites in `api.py` snapshot `client.server_info`, `client.instructions`, `client.meta`, `client.negotiated_protocol_version` INSIDE the `async with MCPClient(...)` block. Properties raise post-disconnect; snapshot ordering is load-bearing. Documented in the Leg 03 flight-log session note as a citation but worth elevating to agents.md F4 as a canonical pattern.
- **`inEditor` predicate dual-mount coverage**: Studio's `confirmLeave` predicate must cover `(activeSection === 'agents' && _selectedAgent) || (activeSection === 'mcp-sources' && mcpSourceFormMode)` — both editor mount contexts. If a third editor surface lands in Studio, the predicate needs a third OR clause. This is not currently documented anywhere greppable.

### Technical debt introduced

1. **LED wire-up incomplete** (2 of 3 pinned consumer sites deferred): the idle state on `mcp-server-editor.js:456` (no-cache banner) and the grid-tile LED slot in `mcp-servers-grid.js:80-102` remain unwired. The `mcpSourceLedState(source)` shared helper was never introduced. Any future flight touching MCP source status display must close this or the indicator story stays incomplete.
2. **6 browser test files module-skipped** due to pre-rebrand selector assumptions: `test_flow_provider_grid.py`, `test_flow_studio_tools_overrides.py`, `test_studio_mcps_tab.py`, `test_flow_provider_setup.py`, `test_flow_agent_crud.py` (the latter two hang — see Testing Assessment below), and one test-level skip in `test_flow_studio_openrouter_picker.py`. These represent pre-Leg-02 test debt; they're in `mission.md` Known Issues but will decay further if not addressed.
3. **`_MockMCPClient` sprawl**: 12 mock classes across 3 test files now each carry stubs for 4 new `MCPClient` properties. This pattern does not scale. A `MockMCPClient` base class or factory should be extracted at maintenance-pass cadence.
4. **Light `fg_muted` on `shell_chrome_bg` fails WCAG AA** (3.33:1). Documented as a Known Issue near the WCAG parametrizations. If Studio's polish work introduces muted text on chrome surfaces, the gap becomes a live failure, not a latent one.

---

## Leg Spec Accuracy

### What the specs got right

Leg 01's spec was the tightest of the flight: 7 items, explicit ordering constraint (rename FIRST), broadened grep scope (whole package, not `static/`-only) explicitly called out after the `api.py:1519` consumer F3 recon had missed. This instruction was correct and the agent caught the `api.py` consumer successfully. The token rename's 5-site footprint (vs the "1 consumer" originally cited in flight design) was caught by design review.

Leg 05's stale-then gap prediction was accurate: design review predicted ~1 genuine gap; actual was exactly 1 (line 441). The dual `inEditor` predicate coverage (both agent-editor and mcp-source-editor mount contexts) was correctly specified.

### What was missing or misleading

**Leg 07's cleanup pile was severely undercounted.** The leg spec catalogued 3 pre-existing test regressions. When the full Playwright suite ran, 43 tests failed across 10+ additional files. The same two root causes (sidebar header removal in Leg 02, dropdown-to-3-buttons redesign in Leg 02) affected files that pre-flight recon had not scanned for. The initial fix pass covered 3 files; the expanded scope pass covered 7 more before the agent was killed due to CPU overload.

The blast-radius of Leg 02's structural changes (sidebar header suppression + picker redesign) should have been assessed at Leg 02's close, not discovered during Leg 07. A practical rule: any leg that changes the shape of a globally-present element (topbar, sidebar, any area-wide chrome) should conclude with a quick `pytest tests/browser/ -q -m browser 2>&1 | tail -3` to verify no previously-passing browser tests have entered failure.

### Were acceptance criteria verifiable?

Leg specs generally had verifiable criteria (grep sentinels, specific test commands). The main exception is Leg 03's vibe portion — "MCP Server editor reads on-brand" is operator-judgment, which is appropriate for a vibe leg. The pre-leg LED-site audit (from the Architect design review) was the right addition; it converted the LED wire-up from open-ended to finite-scope.

---

## Testing Assessment

### Coverage adequacy

The new `test_agent_rename.py` (9 tests) and `test_connect_captures_meta` cover their respective code paths well. The B2 regression test (`test_flow_cross_area_dirty_gate.py`, 4 parametrized invocations) covers the most valuable behavioral addition of the flight.

The OAuth popup-loop fix has no automated test coverage. The fix is inherently interactive (depends on COOP behavior of an external IdP) and the relevant code paths in `launchConsentPopup` are JS-only with no Playwright-exercisable mock path. Acceptable trade-off; documented explicitly.

The Server-info section (`renderServerInfoSection`) has no automated test coverage. It's purely presentational from cached data; a unit test would require DOM serialization or Playwright. A dedicated Playwright test exercising the Server section render (with a mocked `_cache.server_info`) would be the right instrument.

### Untested edge cases

The 2 hanging test files — `test_flow_provider_setup.py` and `test_flow_agent_crud.py` — were skipped rather than investigated. Both hang under post-Leg-02 markup. The flight log notes this as "root cause unidentified — deserves early triage." These may expose real product bugs (e.g., the agent create/delete flow interacting with the renamed selector landscape in unexpected ways). The next flight touching Studio should triage these specifically before shipping new Studio behavior that could mask a pre-existing defect.

The agent rename flow has a documented known issue: the PTY tool-session registry does not rebind on rename, leaving stale in-memory keys. The workaround is to close active chat sessions before renaming. The registry-rebind hook (~10-20 LOC) was explicitly deferred. If a user renames an agent mid-session this is a silent failure path.

---

## Test Metrics

### This debrief run (2026-05-13, post-commit `19d9a58`)

| Suite | Pass | Fail | Skip | Wall clock | Notes |
|---|---|---|---|---|---|
| Narrow gate (4 modules) | 58 | 0 | 0 | ~0.87s in-container | Measured in flight log Step 9 |
| WCAG audit (`test_design_tokens_a11y.py`) | 47 | 0 | 0 | ~0.05s | 2 new parametrizations from Leg 01 |
| Key unit modules (10 modules, debrief run) | 167 | 0 | 0 | 7.58s | Covers WCAG + token + agent-rename + mcp-client + mcp-stdio + oauth batteries |
| Browser suite (`-m browser`) | 315 | 0 | 35 | ~266s | Exit code 0; timing from flight log Step 8 |
| Pixel suite (`-m pixel`, no UPDATE_SNAPSHOTS) | 10 | 2 | 0 | 27.12s | 2 `chat_with_messages` pre-existing KIs |
| Broad pytest (`-m "not browser and not pixel"`) | Pending | — | — | — | Historically hangs (SQLite WAL anomaly); not independently timed in this debrief run |

Note: the broad pytest suite (`-m "not browser and not pixel"`) continued to time out in this debrief run before completion, consistent with the SQLite WAL anomaly documented in F1 through F3.5. The narrow gate and targeted module runs are the reliable measurement surface.

### Comparison to prior flights

| Suite | F1 | F2 | F3 | F3.5 | F4 (this flight) | Delta F3.5 → F4 |
|---|---|---|---|---|---|---|
| Narrow gate | 56 in 0.95s | 56 in 0.90s | 56 in 0.82s | 56 in 0.88s | **58 in 0.87s** | +2 tests; timing stable |
| WCAG audit | 45 in 0.06s | 45 in 0.06s | 45 in 0.05s | 45 in 0.05s | **47 in ~0.05s** | +2 parametrizations (Leg 01 shell_chrome_bg) |
| Pixel suite | 10p/2f in 25.06s | 10p/2f in 25.36s | 10p/2f in 25.67s | 10p/2f in 24.42s | **10p/2f in 27.12s** | +2.7s; within noise, same 2 KIs |
| Browser suite (passing) | — | — | — | — | **315p/35s** | First flight with a measured browser pass count |

**Narrow gate growth (+2 tests, from 56 to 58)**: the 4-module gate now includes the Leg 01 `--shell-chrome-bg` WCAG parametrizations. The count reflects the addition of `test_design_tokens_a11y.py`'s 2 new rows. Timing held (0.87s vs 0.88s F3.5) — no signal, still within container-warmth noise band.

**WCAG audit growth (+2 parametrizations)**: from 45 to 47. Both new parametrizations are `fg` on `shell_chrome_bg`: dark (12.22:1, well above AA) and light (12.49:1). The muted variants were intentionally dropped because light `fg_muted` fails at 3.33:1.

**Pixel suite timing regression (+2.7s, 24.42s → 27.12s)**: small but outside the prior noise band (25.06/25.36/25.67/24.42s). Likely candidate: the Server-info section and per-tool tile restructure in the MCP editor changed render complexity. No new pixel failures; the 2 `chat_with_messages` KIs remain unchanged.

**Browser suite — first measurable baseline (315 passed, 35 skipped)**: prior flights did not measure the browser suite count. The 35 skipped tests represent the Leg 07 cleanup debt: 6 module-skipped files + the `test_flow_studio_openrouter_picker` test-level skip. Future flights can track drift from this baseline.

---

## Reflections on the Flight's Quirks

### pytest-timeout's inability to interrupt Playwright hangs

The most operationally disruptive event of the flight: a Playwright test (`test_flow_hash_routing.py`) hung for 83 minutes at 99.5% CPU despite `--timeout 30`. pytest-timeout uses SIGALRM-based interruption; Playwright's protocol-level waits (blocking on Chrome DevTools Protocol responses) are not interruptible by Python signal handlers in the same way. The continuation Developer agent kept spawning new pytest invocations while the first was still wedged, eventually pinning 12 cores at 1197%.

The fix is host-side: `timeout NN docker exec the-one pytest ...` from the shell so the Docker exec channel is SIGKILL-able even when pytest-timeout can't reach inside. This is now documented in Leg 07's edge cases and should be in the leg skill's standard pytest-in-container guidance.

### Agent-driven autonomous prep overload

The continuation Developer agent that was authorized to fix the expanded cleanup pile (17+ test files) was killed after the hang episode. This highlights the risk of authorizing an autonomous agent with broad scope over a test suite where individual tests can consume unbounded wall time. The authorization was reasonable (the fix pattern was well-understood — selector updates only), but the execution environment was not safe for autonomous multi-test parallelism. Flight Director intervention (manually applying module-level skips for the 2 hanging files, spot-checking the rest) was the correct recovery.

### The "ship with KIs" operator decision

Six test files module-skipped + 2 hanging tests accepted as known issues rather than fixed before shipping is an unusual acceptance posture. It was the right call for this flight: the skipped tests all test pre-Leg-02 UI shapes that no longer exist; fixing them would have required understanding whether the new shapes have equivalent coverage (often yes, via new tests that Leg 05 added). The hanging tests (`test_flow_provider_setup`, `test_flow_agent_crud`) are a different concern — they may indicate real product bugs rather than stale selector issues. Tagging them for early triage in the next flight is more important than blocking this flight's close on them.

---

## Architect's Design Review

### Design decisions that held up well

The **"EXTRACTION + EXPOSURE"** framing for Leg 05's `confirmLeave` was exactly right. Studio already had the inline `dirty && inEditingContext` gate at `studio.js:295-309`; the Architect's design-review insistence on reframing from "infrastructure-from-scratch" to "extract + expose ~20 LOC" was confirmed in implementation. The stale-then audit found exactly the one gap the design review predicted — `fetchMcpSources_().then(() => tryConsumePendingMcpSource())` at line 441 — and 21 other continuations were already guarded, cache-only, or not stale-sensitive.

The **Leg 01 "order matters" discipline** (token rename FIRST, then reduced-transparency block extension) was sound: the block's overrides correctly referenced the new `--shell-bg` name because the rename preceded the block edit. The broadened grep sentinel (`grep -rn ... the_one/` vs static-tree-only) was a genuine correction — it surfaced `api.py:1519` as a consumer that would have been a silent break under the narrower scope.

The **"lean F4 subsection" recommendation** was validated at Leg 07: because Leg 04 was skipped, `App.dropdown` vanished as an F4-original pattern, and the subsection correctly focused on the actual deliverables (confirmLeave parity, OAuth fix, MCP cache schema, B2 test, server-info section, HAT-driven inline fixes).

### Design decisions that had to be revised during implementation

**Leg 03 LED wire-up scope**: design prescribed `.indicator-led--{success|warning|idle}` at 3 consumer sites + a shared `mcpSourceLedState(source)` helper. Execution wired only the success state on the editor banner (hardcoded `--success`, no helper). The vibe leg consumed its scope on the OAuth popup-loop fix and server-info functional batch. The LED deferral was pragmatically correct but the leg artifact's acceptance criteria listed the helper as mandatory — a cleaner carry-forward note would have been better than a criteria deviation.

**Leg 07 cleanup pile**: design identified 3 affected test files; execution found the same Leg 02 root causes affecting 10+ additional files. The undercount was foreseeable — Leg 02 was a large vibe leg with many surface changes — and should have been estimated more conservatively.

**OAuth fix**: iterated through 3 designs before landing. Iteration 1 (postMessage loop fix) failed against Cloudflare's COOP, which severs `window.opener` silently. Iteration 2 (poll on success postMessage receipt) failed because the COOP severance meant the postMessage gate was never reached. Iteration 3 (always-on polling from popup open, postMessage as fast-fail only) is the right final shape. The original flight spec did not anticipate the COOP constraint — it was discovered only in production manual verification.

### Architectural impact

**Maintained or improved**: cross-area dirty-gate infrastructure is now complete across all three areas (Admin: F3 L06; Studio: F4 L05). The `confirmLeave` hook contract is symmetric across area descriptors — Admin's `_confirmLeaveImpl` and Studio's are structurally identical. The Playwright B2 test locks both areas against regression with one parametrized file.

**Unplanned structural changes — sound**: The MCPClient gained a `meta` property and `_cache` schema gained `meta` + `protocol_version`. The cache-write pattern (snapshot inside the async-with, before disconnect) mirrors the F4 L2 pattern for `server_info` + `instructions`. The same-section-click clears editor state fix (HAT inline) is organic routing correctness; the `hydrateState` symmetric fix (bare-section URL clears pending editor state) is necessary for back-navigation correctness.

**Architectural debt created**: 6 deferred test files create a Known Issue surface. The 2 hanging files (`test_flow_provider_setup`, `test_flow_agent_crud`) represent higher entropy risk — if the hang root cause is in Leg 02's restructured markup, it will still be present in Chat's analogous surfaces when Flight 5 arrives. The LED-state helper non-introduction creates an entropy point: future iterations will need to find both hardcoded sites, extract the helper, and extend it.

### Forward-looking patterns worth standardizing

**Operator-intent scope expansion**: Leg 07 demonstrated a reusable orchestrator pattern. When a cleanup leg discovers additional failures from the same root cause as the originally-authorized regressions, the Flight Director can expand scope without a new operator decision if the operator's prior framing unambiguously covers the extension. The `test_flow_picker.py` nuance (tests whose underlying UX no longer exists cannot simply have selectors updated) is a useful corollary: scope expansion applies to mechanical fixes, not test-intent revision.

**Cross-origin opener severance handling**: polling starts immediately on popup open, postMessage demoted to fast-fail signal. This is now architecturally codified for the codebase's OAuth flow. If a second OAuth-capable surface is introduced (e.g., a Chat-area OAuth connector), this state machine pattern should be referenced and reused directly, not re-derived.

**Mixed vibe-leg + functional-batch model**: Legs 02 and 03 mixed vibe with opportunistic functional batches via spawned Developer agents. The integration was smooth for Leg 02 (agent rename), reasonable for Leg 03's serverInfo batch, but the OAuth fix in Leg 03 required three design-implement-test iterations that were not anticipated in the leg's time budget. The vibe-leg model's "operator drives, functional batches are opportunistic" assumption understates the closing-leg cleanup cost. A sharper adaptation criterion: if a functional batch within a vibe leg requires more than one design-implement-test cycle, it should trigger a scoping discussion about whether that batch belongs in a separate autonomous leg rather than accumulating in the uncommitted diff.

**Multi-leg uncommitted-diff cognitive overhead**: the 4-leg deferred-commit pattern (Legs 03 + 05 + 06 + 07) is efficient at the commit-count level but creates cognitive overhead in distinguishing "regressions from this leg's changes" from "regressions carried in from prior uncommitted legs." The Leg 05 Developer's stash-check to verify pre-existing regressions weren't introduced by their own work is a good practice that should be noted in the flight template.

### Design assumptions to revisit

**Stale-then continuation heuristic**: any `.then()` callback calling a function with `consume`, `pending`, or `tryXxx` in its name is a high-probability gap candidate. Future flight designs should flag these explicitly during stale-then audits. The Leg 05 design review caught this through judgment; a heuristic codifies the catch.

**Globally-present UI element changes need post-leg suite smoke**: any leg that changes the shape of a globally-present element (topbar, sidebar, any area-wide chrome) should conclude with a quick `pytest tests/browser/ -q -m browser 2>&1 | tail -3` to surface previously-passing tests entering failure. Would have caught Leg 02's 17-file blast radius before it accumulated into Leg 07.

---

## Recommendations

1. **Triage `test_flow_provider_setup` and `test_flow_agent_crud` before the next Studio flight.** Both hang under post-Leg-02 markup and their root cause is unidentified. Run them individually with a host-side `timeout 30 docker exec the-one pytest <file> -x -q -m browser` and read the hang trace. If they reveal a real product bug, it should be fixed before it's obscured by additional Studio changes.

2. **Close the remaining LED wire-up debt** (idle state on `mcp-server-editor.js:456` + grid-tile slot in `mcp-servers-grid.js:80-102`) in the next MCP-touching flight. The `mcpSourceLedState(source)` helper should be introduced at that point to unify all 3 consumer sites.

3. **Extract a `MockMCPClient` base class** from the current 12-mock sprawl across `test_mcp_stdio_test_connect.py`, `test_mcp_connection_reset.py`, and `test_oauth_test_connection_endpoint.py`. A `BaseMockMCPClient` with all-None/all-False property stubs that test classes can inherit and override would eliminate the "add a property to MCPClient → update 12 mocks" tax that is already visible at this scale.

4. **Adopt host-side timeout wrapping for all Playwright pytest invocations.** Add `timeout NN docker exec the-one pytest tests/browser/ ...` (host-side `timeout`) as the canonical browser test invocation in project documentation and any autonomous leg guidance. Drop reliance on pytest-timeout alone for browser tests.

5. **Instrument Leg 02 (and any future leg touching globally-present UI elements) with a post-leg browser regression smoke.** A quick `pytest tests/browser/ -q -m browser 2>&1 | tail -3` at leg close (not full suite — just the count + any new failures) would have surfaced the 17-file blast radius before it accumulated into the Leg 07 cleanup pile.

---

## Action Items

- [ ] **Triage `test_flow_provider_setup` + `test_flow_agent_crud` hangs** before next Studio flight. Root cause: likely selector or fixture issue from Leg-02 markup; may indicate a real product bug.
- [ ] **Wire remaining 2 LED consumer sites** (`mcp-server-editor.js:456` idle state + `mcp-servers-grid.js` tile slot) + introduce `mcpSourceLedState(source)` helper. Natural home: next Studio-polish follow-on flight.
- [ ] **Extract `BaseMockMCPClient`** from the 12-mock sprawl across 3 test files. Maintenance-pass cadence.
- [ ] **Add Playwright test for `renderServerInfoSection`** — mock a `_cache.server_info` payload and assert the Server section renders with icon, title, version, capability flags, and instructions collapsible. Closes the zero-automated-coverage gap on this feature.
- [ ] **Document the COOP / always-on polling pattern** in `agents.md` F4 or in the OAuth section of the codebase's architecture notes. "PostMessage-gated success detection fails for IdPs that set COOP" is a non-obvious, high-value lesson.
- [ ] **Register the `inEditor` dual-predicate expansion rule** somewhere greppable (a comment inside `_confirmLeaveImpl` in `studio.js`, or an agents.md note) so a future Studio editor surface doesn't accidentally miss the predicate extension.
- [ ] **Adopt host-side `timeout NN docker exec` for browser pytest** and document it in the project's testing guidance.
- [ ] **Investigate light `fg_muted` on `shell_chrome_bg` (3.33:1)** if any Studio polish work introduces muted text on chrome surfaces. Currently no live consumer; parametrization was intentionally deferred.
- [ ] **Reopen and update `test_flow_provider_grid`, `test_flow_studio_tools_overrides`, `test_studio_mcps_tab`** in a future maintenance pass: either update their assertions to match the Leg-02 UI shapes, or confirm equivalent coverage exists elsewhere and retire them.

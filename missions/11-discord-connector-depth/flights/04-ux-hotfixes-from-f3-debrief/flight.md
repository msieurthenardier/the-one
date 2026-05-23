# Flight: UX Hotfixes from F3 Debrief

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [x] Mission criterion #18 (fresh operator under fifteen minutes): A1 closes the cold-start dropdown 404 friction; A2 closes the per-agent-overlay identification gap. Both surfaced at F3 L7 HAT against gleepglorp; both HAT-verified at F4 L4.
- [x] Mission criterion #19 (full working-day daily-driver): A1 closes the cold-restart path where dropdowns 404 immediately after server restart despite Test Connection succeeding (HAT-verified at F4 L4 with the L4 fold-in fix that auto-refreshes dropdowns on pool-warmed event).

## Source artifacts driving this flight

- **F3 mission-flight-debrief** (`missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight-debrief.md`) Action Items "Immediate (before F4)" + "Methodology (before F4 planning)" + the cumulative UX-debt enumeration. F4 closes the near-term UX hotfixes the F3 debrief enumerated and codifies the 4 new conventions the F3 debrief surfaced.
- **M10 mission-debrief** Action Item recommendation #5 (criterion-coverage map as a living artifact) — un-actioned since M10 close; folded into F4 as a continuing-tracker.

---

## Pre-Flight

### Objective

Land the F3 debrief's "Immediate (before F4)" and "Methodology (before F4 planning)" Action Items in one bounded, low-blast-radius flight before F5 (peer-name attribution; M10 Bug C; CRITICAL most-deferred). F4 closes A1 (Test Connection warms the pool), A2 (per-agent overlay checkbox-mode resolves Discord IDs to friendly labels), C1 (`test_edit_session_continuation_round_trip` 5-flights-deep one-line drift), codifies 4 new `agents.md` conventions surfaced by F3 (so they bind on F5+ designs), seeds the M11 `criterion → evidence/test` living map, and HAT-verifies the two hotfixes against gleepglorp. ~150-200 LOC + tests.

The flight is explicitly framed as the operator-requested intervention to arrest UX-debt accumulation. The expectation is NOT additive UX feature work; it is "close the deferred queue from F1-F3 + ratify the methodology fixes that prevent the queue from regrowing." If new UX issues surface during F4 (HAT or otherwise), the flight Adaptation Criteria explicitly mandate "fold into F4 OR escalate as a Known UX Gap with a near-term path — NOT another F8/F10 deferral."

### Open Questions

*All resolved at planning per Phase 3-4 crew interview. Resolutions promoted to Design Decisions below.*

### Design Decisions

**Codifications ordering — agents.md L1-style first** *(operator decision)*:
- L1 lands the 4 new `agents.md` conventions BEFORE any source touches in L2-L4. Mirrors F3 L1 precedent — subsequent legs can invoke conventions by name. The 4 conventions surfaced by F3 debrief, in source order:
  1. `pool-warming-entrypoints-are-finite-and-named` — codifies the L4-design-miss prevention. Source: F3 L7 HAT anomaly #1 + F3 debrief. n=1-by-methodology-promotion (matches `registry-dispatch-create-mode-AC` precedent).
  2. `frozen-snapshot-for-cross-lock-read` — codifies L4's `_DiscoverableCacheSnapshot` pattern (read-side serialization without holding the lock). Source: F3 L4 cycle-1 architect catch. n=1-by-methodology-promotion.
  3. `slot-getter-bridge-for-dropdown-collect-path` — codifies L6a/L6b's `_allowlistValues` / `_routingMatchValues` / `_overlayChipValues` pattern (function-valued property on a DOM slot bridges a new editor shape to an existing DOM-walking collect path). Source: F3 L6a + L6b. n=3-from-single-flight.
  4. `two-concurrent-callers-reasoning` — codifies the architect-checklist extension for race-safety reviews. Source: F3 L4 cycle-1 catch. n=3 (within L4 alone: `prior_cache` race, `_shutting_down` bail, identity-check). **Placement** (cycle-1 architect catch): lands as a regular Project-wide convention alongside the other three. No new "Architect-checklist" subsection — agents.md has none; inventing one for n=1 is over-structure. The convention's body describes the architect-checklist application directly (mirrors `flight-spec-dom-order-audit`'s shape — a flight-design-time discipline expressed as a project-wide convention).
- The L1 leg also bundles the **`cross-flight-ux-debt-reconciliation`** + **`touched-surface-ux-debt-folding`** notes — both target mission-control's `/flight` and `/leg` skill prompts (out of project scope) — but their *project-side* footprint (a checklist line in `agents.md` Project-wide saying "F4 ratified these recon disciplines on the project side; if mission-control's skill prompts are out of date, this convention is the project's binding fallback") lands here.

**A1 — Test Connection wires `account_acquire` AFTER doctor succeeds, with isolated error surface** *(operator decision; cycle-1 architect-tightened)*:
- The L4 design-time assumption was "Test Connection populates the pool entry via the lifespan-listener-warmup path." HAT proved this false. **Fix**: extend `test_connector_connection` (`api.py:2573-2638`) to call `await account_acquire(account_id)` AFTER the `plugin.doctor(...)` call succeeds.
- **Critical error-surface isolation** (cycle-1 catch): `account_acquire` can raise `ConnectorClientError` (same exception class the existing handler already maps to a top-level `status='error'` envelope at `api.py:2622-2630`). Naïvely calling it would introduce a REGRESSION where doctor-ok + warmup-fail reads as Test Connection FAILED. **Fix**: wrap the new `account_acquire` call in its OWN try/except that catches BaseException broadly (the warmup is best-effort; never escalate), records the failure into `details.pool_warmed=false` + `details.pool_warm_error=<str(exc)>`, and returns the doctor's `status='ok'` verdict regardless. This is exactly the `two-concurrent-callers-reasoning` discipline that F4 L1 is about to codify — the new error path needs its partial-success shape worked out before commit.
- Placement-after-doctor matters: if `doctor()` itself raises or returns `status!='ok'`, the warmup is SKIPPED (no point warming a pool entry the operator hasn't proven works).
- Response envelope adds two new `details` fields: `pool_warmed: true|false` (boolean) AND `pool_warm_error: str | null` (None when `pool_warmed=true`). Test for both.
- **Trade-off**: a successful Test Connection now takes slightly longer (one extra gateway round-trip via `account_acquire`); acceptable per the user-visible payoff (the dropdown actually works on first open).
- **F3 flight.md correction site** (per cycle-1 architect catch + agentic-workflow `SKILL.md:47` "annotate at the artifact header"): the L4 assumption at F3 `flight.md:55` ("the operator clicks Test Connection (which goes through the existing doctor probe path AND populates the pool entry via the lifespan-listener-warmup path)") stays byte-identical as a snapshot. The correction lands as a one-line annotation under F3 `flight.md`'s Status block at the top of the file: `**Subsequent corrections**: L4's Test-Connection-warms-pool assumption corrected at F4 L2; see F4 flight-debrief.` Mixes neither correction with snapshot body.

**A2 — per-agent overlay checkbox-mode label resolver via L4 API** *(operator decision; cycle-1 architect-tightened)*:
- The current `connectors-tab.js:_renderAccountTile`'s checkbox-mode renders `nameSpan.textContent = item;` where `item` is a raw Discord snowflake ID. Fix: the tile-expansion handler fires the existing `GET /api/connector-accounts/{id}/discoverable-entities` (L4) to fetch the cache; the checkbox-mode renderer looks up `entity.label` by id and falls back to the raw id if no match (mirrors L5's unknown-id-chip-fallback pattern from F3).
- **Fetch timing: LAZY on tile expand + cache on tile-local closure** (cycle-1 catch). Do NOT eager-fetch in `renderConnectorsTab` (would fire N parallel GETs even for unexpanded tiles). The fetch fires once per tile, on the first `expandBtn.click` (`connectors-tab.js:~243`), and ONLY when the tile's render falls into checkbox-mode (per-axis `scopeList.length > 0`). Response is cached on a tile-local closure; collapse-then-re-expand does NOT re-fetch.
- **Per-tile-fetch vs shared-fetch**: per-tile-fetch is simpler (each tile owns its own data) — and with lazy-on-expand semantics, the server cost is one L4 cache hit per tile-expand AT MOST. Shared-fetch would require a connectors-tab-level state store; deferred unless F5+ observability surfaces it.
- **Single L4 GET returns ALL 4 axes** (peers/channels/groups/roles) for the account — so a multi-axis tile (peers + channels visible) only needs ONE fetch, not one-per-axis.
- **Stub-type and other types without the `enumerate_discoverable_entities` hook**: the GET returns 503; the checkbox-mode renderer falls back to raw-id display (current behavior). No regression for stub accounts.
- **Network error / cold pool (404 pre-probe hint)**: same raw-id fallback path. The operator's recovery is to use the connector-account-editor's Test Connection (which after A1 will warm the pool); once warm, re-expanding the tile fires a fresh fetch and labels resolve.

**C1 — one-line test text update** *(operator decision)*:
- `test_edit_session_continuation_round_trip` at `tests/browser/test_flow_studio_connector_account_editor.py:417` asserts `"Distinct from the pool idle timeout"`. Source at `connector-account-editor.js:368` says `"Inbound continues the same chat session within this window."`. The test updates to match the source. 5-flights-deep chronic; trivial fix.
- The decision to update test-side (not source-side) follows L2's `match-tests-to-code-when-code-is-operator-friendly` precedent from F3. The source text is operator-friendly; the test was written before the source landed at its current shape.

**L4 HAT scope — A1 + A2 only; defer F3-deferred stale-entry to F9** *(operator decision)*:
- HAT smoke-verifies A1 (cold dropdown → Test Connection click → dropdown populates without restart) AND A2 (per-agent overlay checkbox-mode shows `#gleepglorp-text` instead of `1506831630923333722`). Both walk-able against gleepglorp with the Chrome MCP without operator-side Discord actions.
- Does NOT cover F3 L7 step 8 (stale-entry indicator) — that requires operator-side Discord member-kick action; deferred to F9 (Live-traffic HAT script + rate-limiting) where `discord.py`-as-second-bot is the documented driver.

**Mission criterion-coverage map seed** *(operator decision; cycle-1 architect-tightened)*:
- L1 seeds `missions/11-discord-connector-depth/criterion-coverage.md` as a living artifact mapping each M11 mission criterion (`mission.md` lines 25-43 — verified 19 criteria) to evidence (specific test names, leg references, debrief sections, HAT outcomes). This is the M10 mission-debrief recommendation #5 that has been un-actioned since M10 close.
- **Row schema** (cycle-1 architect proposal, locked):
  ```
  | # | Criterion (excerpt) | Status | Evidence | Last touched |
  |---|---------------------|--------|----------|--------------|
  | 1 | Discord-shaped creation form | closed-by-F1 | F1 L1-L7; test_flow_studio_discord_account_creation.py | F1 |
  | ... | ... | ... | ... | ... |
  ```
- **Status vocabulary** (closed semantics): `closed-by-Fn` / `partially-closed-by-Fn` / `structurally-complete-pending-HAT` / `open`. The "Last touched" column makes drift-detection mechanical at debrief time.
- **Maintenance contract** (cycle-1 question resolution): F4 seeds + closes its own contributions (rows #18 + #19 get `partially-closed-by-F4` updates at the F4 debrief gate; row touched by A1 lands the new evidence pointer). F5+ flights MUST update affected rows at debrief time. Failure to update = the flight-debrief skill should surface it as a methodology violation in its own debrief.
- Format follows the M10-debrief-recommended `criterion → evidence/test` shape; the artifact is plain markdown so future flights can edit it without machinery.

### Prerequisites

- [ ] F3 is `completed` (verified: status updated 2026-05-22; commit `edf4383`).
- [ ] F3 PR #71 is open (does not need to merge before F4 lands; F4 stacks on F3 branch in commit history).
- [ ] L4 API endpoints (`GET /api/connector-accounts/{id}/discoverable-entities` + `POST .../refresh`) are callable — required for A2's label-resolver and A1's HAT verification.
- [ ] L4 `account_acquire(account_id)` primitive is importable from `the_one.connectors._pool` — A1 calls it directly. (Verified at F4 recon: `_pool.py:830`.)
- [ ] Existing connector-account-editor at `connector-account-editor.js:368` says `"Inbound continues the same chat session within this window."` — verified at recon.
- [ ] Existing test at `tests/browser/test_flow_studio_connector_account_editor.py:417` asserts the stale string — verified at recon.
- [ ] gleepglorp test bot reachable (same prereq as F3 L7).
- [ ] `chrome-devtools` MCP available for L4 HAT.

### Pre-Flight Checklist

- [ ] All open questions resolved (codifications ordering; A1 placement-after-doctor; A2 per-tile-fetch; C1 update-test-side; L4 HAT scope; criterion-coverage seed shape — all locked at Phase 4)
- [ ] Design decisions documented (above)
- [ ] Prerequisites verified
- [ ] Validation approach defined (per-leg ACs + L4 HAT smoke-verify of A1 + A2)
- [ ] Legs defined (below; planned one-at-a-time per Flight Control convention but tentatively scoped here)

---

## In-Flight

### Technical Approach

**Doc-first sequencing.** L1 lands the 4 codifications + criterion-coverage seed doc-only so L2-L4 can invoke conventions by name and so the criterion-coverage tracker exists when L2-L4 touch criteria. L2 lands A1 (Python: api.py edit + tests, ~15 LOC source + 3 new tests) bundled with C1 (one-line test text update; trivial). L3 lands A2 (frontend: `connectors-tab.js` edit + tests, ~50 LOC source + 2-3 new tests). L4 HAT smoke-verifies both A1 + A2 against gleepglorp.

**Sequence rationale**: L1 first per F3 L1 precedent (codifications-before-source-touches). L2 + L3 independent of each other (Python vs frontend; no shared files); could parallelize but sequential preserves clean review-and-commit per leg. L4 HAT depends on L2 + L3 being landed.

**Per-leg LOC budget**: L1 doc-only (~40-60 LOC); L2 Python source + tests (~30-40 LOC); L3 frontend source + tests (~70-100 LOC); L4 HAT artifact (~20 LOC, mostly verification-step prose). Total source delta ~150-200 LOC. Well under any concern threshold.

### Checkpoints

- [x] L1 — `agents.md` grows 4 new conventions (`pool-warming-entrypoints-are-finite-and-named`, `frozen-snapshot-for-cross-lock-read`, `slot-getter-bridge-for-dropdown-collect-path`, `two-concurrent-callers-reasoning`) plus `cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding` project-side notes; `missions/11-discord-connector-depth/criterion-coverage.md` seeded with M11's 19 mission criteria + initial status.
- [x] L2 — `api.py:test_connector_connection` calls `await account_acquire(account_id)` AFTER `plugin.doctor()` succeeds; response envelope grows `details.pool_warmed` field. `test_connector_test_connection_button.py` adds AC for `pool_warmed=true` on the success path. `test_edit_session_continuation_round_trip` updated to assert `"Inbound continues the same chat session within this window."` (C1 closure).
- [x] L3 — `connectors-tab.js:_renderAccountTile` checkbox-mode renderer fetches the discoverable-entities cache via `GET /api/connector-accounts/{id}/discoverable-entities` and looks up `entity.label` by id; falls back to raw id if no match (stub-type / unknown-id). New browser test pins Discord-account-checkbox-shows-`#gleepglorp-text` AND stub-account-checkbox-shows-raw-id-fallback.
- [x] L4 — HAT smoke-verify A1 (cold dropdown → Test Connection → dropdown populates without restart) + A2 (per-agent overlay shows friendly labels) against gleepglorp. All 6 steps PASS; one HAT-discovered UX gap folded into F4 (Test Connection success now dispatches `connector-account-pool-warmed` event so mounted dropdowns auto-refresh).

### Adaptation Criteria

**Divert if**:
- L2's `account_acquire`-after-doctor introduces a regression on the existing Test Connection happy path (e.g., the doctor succeeds but `account_acquire` raises consistently for some legitimate account state). Pause, escalate; revisit whether the warm-up belongs at a different trigger point.
- L3's per-tile-fetch causes observable UX lag on multi-account tiles (e.g., > 500ms for a tile with 5 attached accounts). Pause; reconsider shared-fetch design.
- L4 HAT surfaces NEW UX issues during the A1/A2 verification. **The F3-debrief explicitly mandates: if new UX issues surface, fold into F4 OR escalate as a Known UX Gap with a near-term path — NOT another F8/F10 deferral.** This is the operator-requested discipline change.

**Acceptable variations**:
- L2 + C1 may split into separate legs if cycle-1 review reveals C1 has unexpected complications (e.g., other tests depend on the stale string).
- L3 may shard into two legs if implementation reveals checkbox-mode + chip-mode share more code than expected (would push the L3 LOC over ~100).
- The criterion-coverage map shape may evolve at L1; the seed is the contract, not the full coverage analysis (that happens incrementally as flights land).
- HAT L4 may add operator-side actions (e.g., create a new test channel and observe it appear in the dropdown after Refresh) if the operator wants additional smoke coverage; document inline.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.
>
> **Dependency ordering**: L1 lands before L2-L3 (they reference codified conventions by name AND check off entries in the criterion-coverage map). L2 + L3 are independent (Python vs frontend); L2 lands first for review-and-commit cleanness. L4 HAT lands last (verifies both fixes end-to-end).

- [x] `codify-f3-debrief-conventions-and-criterion-coverage` — Doc-only. Add 4 new conventions to `the_one/agents.md` Project-wide subsection (`pool-warming-entrypoints-are-finite-and-named`, `frozen-snapshot-for-cross-lock-read`, `slot-getter-bridge-for-dropdown-collect-path`, `two-concurrent-callers-reasoning`); add `cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding` project-side notes. Seed `missions/11-discord-connector-depth/criterion-coverage.md` mapping each M11 criterion → current status + evidence pointer. Mirrors F3 L1 codification-pattern; no source modifications.

- [x] `test-connection-warms-pool-and-fix-session-continuation-test` — Bundle A1 + C1. A1: extend `api.py:test_connector_connection` to call `await account_acquire(account_id)` AFTER `plugin.doctor()` succeeds; add `details.pool_warmed` + `details.pool_warm_error` fields. Inner try/except around `account_acquire` catches `Exception` (NOT `BaseException` — lets `CancelledError`/`SystemExit`/`KeyboardInterrupt` propagate per cooperative-cancellation discipline). Add tests pinning the warm-pool side-effect + the `pool_warmed=true` response field on success. Annotate F3 `flight.md`'s **header** (under the Status block, per agentic-workflow `SKILL.md:47` guidance) pointing at this leg's correction; F3's body text stays byte-identical as a snapshot. C1: update `test_edit_session_continuation_round_trip` (one-line) to match source text. Bundled because both are Python touch points + small.

- [x] `per-agent-overlay-checkbox-label-resolver` — A2. Refactor `connectors-tab.js:_renderAccountTile` checkbox-mode renderer to fetch the discoverable-entities cache via the L4 GET endpoint and look up `entity.label` by id. Fallback to raw id when (a) account type lacks the hook (503), (b) id is not in the cache (unknown-id), (c) network error (degrade gracefully). New browser test file `test_flow_per_agent_overlay_label_resolver.py` pins: Discord-attached-checkbox-shows-`#gleepglorp-text`-style-label; stub-attached-checkbox-shows-raw-id-fallback; network-error-checkbox-shows-raw-id-fallback.

- [x] `uat-and-alignment` *(required HAT — touched both Studio and the Test Connection control plane)* — Chrome-MCP-driven walk against gleepglorp. Verification steps: (1) restart the-one container — this IS the cold-pool setup (no separate test-only API exists to evict a single warm entry; idle TTL is 30 min per `_pool.py:78`); (2) open Discord Constellation editor → Access and Routing tab → dropdowns initially show pre-probe hint "Run Test Connection first…"; (3) click Test Connection → after success, dropdowns repopulate WITHOUT page reload (A1 closure — Test Connection's new `account_acquire` call warmed the pool; the GET fires from the dropdown re-mount and now returns 200 with entities); (4) inspect Test Connection response envelope (browser devtools network panel) — verify `details.pool_warmed: true` on success; (5) navigate to Cave Man Bot → Connectors tab → expand the Discord Constellation Channels checkbox-mode section → verify checkboxes show friendly labels (`#gleepglorp-text` etc.) instead of raw IDs like `1506831630923333722` (A2 closure); (6) navigate to a Stub HAT Account-attached agent → expand a per-axis checkbox section → verify raw-id fallback path renders (regression contract for stub-type / 503 path). HAT-discovered fixes land in flight-log L4 Anomalies; HAT-discovered NEW UX issues land in the **Known UX Gaps** subsection of the F4 `flight-debrief.md` (not mission known-issues; not F8/F10 deferral). Substrate-contract reversals pause the flight per Adaptation Criteria.

---

## Post-Flight

### Completion Checklist

- [x] All 4 legs (L1-L4) completed
- [x] L4 HAT walk completed with operator-confirmed pass
- [ ] Code merged on `main` (or stacked behind F3 PR #71 until F3 merges)
- [ ] Tests passing at or above F3's 2879 baseline + F4 additions
- [ ] `agents.md` grows 4 new conventions + 2 project-side notes
- [ ] `missions/11-discord-connector-depth/criterion-coverage.md` exists with seeded M11 criterion-coverage rows
- [ ] `api.py:test_connector_connection` calls `account_acquire` on success
- [ ] `connectors-tab.js:_renderAccountTile` checkbox-mode renders friendly labels for Discord
- [ ] `test_edit_session_continuation_round_trip` passes (C1 closure; 5-flights-deep chronic closed)
- [ ] F3 debrief Action Items "Immediate (before F4)" + "Methodology (before F4 planning)" — both fully cleared

### Verification

**Mechanical verification** (CI / scripted):
- `pytest tests/browser/test_connector_test_connection_button.py` — new AC for `pool_warmed=true` lands; existing 7 tests pass
- `pytest tests/browser/test_flow_per_agent_overlay_label_resolver.py` (new) — A2 contract pinned
- `pytest tests/browser/test_flow_studio_connector_account_editor.py` — C1 fix lands (`test_edit_session_continuation_round_trip` no longer fails)
- Full suite at or above F3's 2879-pass baseline

**Operational verification** (L4 HAT):
- A1 closure: Test Connection click warms the pool; dropdowns populate without page reload
- A2 closure: per-agent overlay checkbox-mode shows friendly labels for Discord; raw-id fallback for stub

**Methodology verification**:
- 4 new conventions referenceable by name in F5+ flight designs
- Criterion-coverage map maintains traceability for future flights
- F3 debrief's "before F4" Action Items: all cleared

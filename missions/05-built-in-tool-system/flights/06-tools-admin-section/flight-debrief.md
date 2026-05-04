# Flight Debrief: Tools Admin Section

**Date**: 2026-05-04
**Flight**: [Tools Admin Section](flight.md)
**Status**: landed
**Duration**: 2026-04-30 (branch created from main `e65077e` post-F5) → 2026-05-04 (commit `33b1c42`, draft PR #24)
**Legs Completed**: 10 of 10 (L0-L9, with L6 = HAT and L9 = post-Reviewer docs)

## Outcome Assessment

### Objectives Achieved

The operator-facing tool admin surface is shipped end-to-end. Operators open `Settings → Built-in Tools`, see all 19 builtins under 4 category tabs, toggle enable/disable per tile, and click into a per-tool editor that drives form rendering from the tool's marker-enriched JSON Schema. Connection-test panels for `web_search` and `fetch_url` accept custom inputs. The Studio agent editor's Tools tab surfaces operator-disabled tools with strikethrough + dim + tooltip and exposes per-agent override panels with marker-aware widgets (Narrow ceiling, NarrowSuperset locked chips with no remove button DOM, Substitute free-form, unmarked HIDDEN). Save flows propagate through the existing agent-save pipeline into `AgentConfig.tool_overrides`.

The implementation introduced two new architectural surfaces beyond the pure feature delivery: (a) the shared `admin/tools-form-helpers.js` module (~514 LoC) extracted from `tools-editor.js` to be consumed by both admin and Studio without drift; (b) the server-side `_enrich_schema_with_markers` helper that injects `x_marker` per top-level property (Pydantic v2 strips marker classes; this closes that gap once for any future admin UI consuming `Config.model_json_schema()`).

### Mission Criteria Advanced

F6 advanced three Mission 05 success criteria (now checked off in `mission.md`):

- **Tool admin section** — "the administration interface exposes a tool-management surface where each built-in tool can be enabled, disabled, and configured at the tool level, with verification controls (test buttons) for connection-style operations" — fully delivered.
- **Studio reflects tool-level state** — "the studio agent editor reflects the tool-level state — tool-level-disabled tools are unavailable to all agents and visibly inaccessible in the per-agent toggle UI — and exposes the agent-level override surface for per-tool constraint narrowing" — fully delivered.
- **Design-language adherence** — "the new Tools admin section reflects the established design language and meets the M04 quality bar without alignment-flight rework" — delivered with HAT-driven UX iteration in L6 (no follow-up alignment flight needed).

The mission's F6 Open Question ("Tools admin section placement") closed to "peer to System / LLM Providers per Decision 1" with the verifying browser test `test_admin_section_nav_renders_three_sections`.

## What Went Well

**Two-Reviewer-pass batching (F5 debrief recommendation 2 / F6 Decision 12) — first use; worked.** The L0-L8 batch went to one Reviewer pass focused on code correctness; L9 docs went to a second Reviewer pass focused on doc-vs-code accuracy. Zero stale-doc deviations in F6 vs. 4 in F5. The second pass surface was small (78 insertions, 3 deletions across CLAUDE.md + agents.md), making it cheap to verify. Net-positive cost-benefit.

**Design-pass-per-leg caught a load-bearing architectural gap.** The L1 design pass surfaced the cross-Config shadowing pitfall in the test endpoint: `BuiltinToolProvider.get_tools` builds `cross_configs[WebConfig]` from the FIRST web tool in declaration order (`http_request`), so a naive test endpoint for `web_search` would have run through `http_request`'s saved config. The architect's L1 review flagged this; the fix re-keys the test endpoint's input dict so every Config-class-sharing tool is given the named tool's saved row (`api.py:297-303`). Without the design pass this would have shipped silently broken. Direct evidence that design-review-per-leg pays off.

**HAT inline-fix cadence efficient given the context.** L6 surfaced 6+ UX preferences (banner vs. inline error, info-icon tooltips vs. inline paragraphs, "Built-in Tools" label, iOS-toggle in editor, custom test inputs, chip-list visual styling in Studio context, NarrowSuperset chip render-without-button). Each was small individually; batching them into one Developer-spawn UX revision pass (7 changes in one commit-ready batch) amortized the architect-review/test-update overhead well.

**Shared-substrate extraction (`admin/tools-form-helpers.js`) is the right architectural move.** The 514-line module exports `renderField`, chip-list helpers, marker-aware widget dispatch, and validation-error rendering — consumed by both admin's per-tool editor and Studio's per-agent override panel via a `context = {mode, operatorValue?, attrPrefix, toolName?}` parameter. Without extraction the two consumers would have drifted (different ceiling semantics, different `data-*` attribute patterns). With extraction the marker dispatch stays single-source and the locked-chip-DOM-omission a11y semantic ships once.

**Schema migration v9 mirrored v8 cleanly.** Idempotent ALTER guarded by `PRAGMA table_info`; individual `await conn.execute(...)` (not `executescript`); `INSERT OR IGNORE INTO schema_version` runs LAST. Established pattern; F6 reinforced it without inventing a parallel migration shape.

**Browser test density proportional to surface area.** L7 spec'd 8-12 tests; reality was 34 across 3 new files (10 grid + 14 editor + 10 studio) + 1 renamed nav test. The 14 editor tests cover the L6 HAT fixes (banner with humanized 422, field highlights, info-icon tooltips, custom test inputs, iOS-toggle position, 8 WebConfig fields render). The expansion is accurate-to-real-coverage, not scope creep — the 8-12 estimate was design-time-guess; the real density was determined by the as-built surface plus HAT-discovered fixes that needed regression coverage.

## What Could Be Improved

### Process

- **HAT-induced test growth was systematically under-budgeted.** L7's 34 tests vs. 8-12 estimate: ~3x the spec, with 14 of the editor tests covering HAT-discovered fixes. Future flights with HAT phases should reserve a separate "HAT regression budget" line item proportional to the estimated implementation-leg test count. F6 data point: ~2x multiplier for HAT-discovery-induced regression tests.
- **L5 was over-broad scope for a single leg.** It carried (a) a pure refactor (extract 9 functions to a shared module), (b) a new mode dispatch (admin vs. agent rendering), (c) a new attribute pattern (`data-tool-override-tool/field`), (d) lazy-fetch + closure-cached Promise, and (e) studio.js orchestration widening. The L5 design pass needed 5 high-severity fixes (the most of any leg), and an L5-introduced regression in `_wait_editor_ready` had to be fixed in L8. Cleaner split: L5a = pure refactor (admin behaviour unchanged); L5b = additive Studio integration. Recognized pattern for high-complexity legs.
- **REST verb semantics for partial PUT was a leg-design-time discovery, not a flight-design-time pin.** Decision 11 spec'd "PUT /api/tools/configs/{name} → upserts" without specifying merge-vs-replace. The L1 design pass picked REPLACE (REST convention; matches the L3 form's full-state submit), but this is a load-bearing API contract that should have been pinned at flight time. Future flights with new PUT endpoints should make merge-vs-replace explicit in the flight artifact's design decisions.
- **Pre-flight prereq verification should include "find existing references to be updated".** The L0 schema-version pin propagation (3 stale `MAX(version) == 8` assertions outside the spec's `Files Affected` pinout) and the L4 `--font-size-small` token-doesn't-exist surprise are both "spec said X, codebase has Y" cliffs. A leg-design-time `rg` sweep for the current state of the things being changed would catch both classes.
- **Pixel-snapshot baseline failures** (6/12 pixel tests failed during L8) are expected per the user-global "snapshots are not committed" policy — but the L8 leg artifact treated them as "non-blocking" without a clear forward path. Should the project document explicitly that pixel tests run only with locally-regenerated baselines, or should the suite be `@pytest.mark.skip` by default? Methodology gap rather than F6 issue.

### Technical

- **Duplicated `TOOL_CATEGORIES` map** between `admin/tools-grid.js:12` and `admin/tools-editor.js:64` — 19-entry mapping in two files. The L3 deviation note said "extract when a third consumer appears." With Studio's `tools-tab.js` consuming `callbacks.toolCategories` from `agent-editor.js` (different shape, same semantic data), the third-consumer threshold has effectively been reached. **Recommended**: extract to `tools-form-helpers.js` (already the shared substrate) in a routine-maintenance pass or the next flight that touches admin tool surfaces.
- **`humanizeValidationMsg` mirrored in `tools-editor.js:493` and `tools-form-helpers.js:448`.** Copy-paste pattern that will drift. The function strips Pydantic prefixes (`"Value error, "`, `"Input should be "`, `"Assertion failed, "`) and capitalizes — applies to **every** Pydantic-validated form in the project, not just tool-config. Future provider-editor 422 errors would benefit. Promote to a shared `App.humanize` utility.
- **No JS unit-test harness for marker dispatch.** The agent-mode `renderField(name, prop, value, {mode: 'agent', operatorValue})` dispatch is covered ONLY by Playwright (`test_flow_studio_tools_overrides.py`). A unit-of-JS approach (Vitest / Jest / a Python-callable Node-vm runner) would let assertions run cheaply against the IIFE exports. F7 should decide one way or the other; today's coverage relies on a 217-second browser run as the canonical line of defense.
- **Edge cases without test pinning**:
  - **Operator narrows past a previously-set agent override → factory raise**: the resolver re-validates at `AgentFactory.create()` and raises `ValueError`, but no test exercises this. Real operator scenario (admin tightens policy → existing agents break next session) without a regression net.
  - **Chip-list editor with non-string items (`list[int]` future Config field)**: today's chip-list READ path returns strings only; a future numeric field would silently round-trip as strings. `console.warn` fires (per `tools-form-helpers.js:185-189`) but no test pins the warn.
  - **Panel close-during-in-flight-fetch race**: `tools-tab.js:163-252` lazy-fetches and writes `bodyEl.innerHTML` after fetch resolves; if operator switches agents mid-fetch, the listeners attached at lines 232-246 wire to an orphan `bodyEl`. Cheap mitigation: `bodyEl.replaceChildren()` before renderField loop.
- **`_TESTABLE_TOOLS` and `TEST_FIXTURES` parallel definitions** — `api.py:67` (server) and `tools-editor.js:44, 55` (client) maintain mirrors. A small `GET /api/tools/configs/test-fixtures` endpoint would single-source this; not blocking but worth flagging.
- **`ToolConfigRepository.upsert` "last write wins" on `enabled`** — `repositories.py:356-362` documents the caveat: a config-only `upsert(name, config)` call without `enabled=` kwarg silently re-enables a previously-disabled row. The L1 PUT endpoint reads-then-writes correctly, but any future caller that calls `upsert` without first reading will footgun. Worth splitting into `update_config(name, config)` / `update_enabled(name, enabled)` to remove the foot-gun.

### Documentation

- **Drift-warn behavior undocumented.** `tools-tab.js:194-196` emits a `console.warn` when an agent has overrides on now-unmarked fields. This is a real diagnostic; future contributors will see the warn and not know what it means. Two-line CLAUDE.md addendum needed.
- **Resolver-as-security-boundary not stated explicitly.** The L9 docs cover client-side widget shape but don't explicitly state "client-side is UX; resolver re-validates at AgentFactory.create() as the security boundary." Worth a sentence in CLAUDE.md F6 section.
- **Named-tool isolation rationale could be stated more clearly.** `api.py:299-303` is in CLAUDE.md:284 but the corresponding contract for the agent runtime ("FIRST-declared-tool semantics intentionally apply") could use a sentence explaining the asymmetry: admin tests one tool's effective config; agents see unified policy across same-Config tools.
- **L1 deliberately did NOT widen `list_all()`** (factory.py:108-115 comment) is in the code but not in CLAUDE.md — could trip up a future contributor who tries to "consolidate" the projection.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L0: 3 `TestSchemaV8::MAX(version) == 8` assertions hardcoded; needed widening to `max(versions) == CURRENT_VERSION + 8 in versions` membership; rewind clause widened from `WHERE version = 8` to `>= 8` | Schema-version pins propagate beyond the explicit "bump line ~233" instruction. The leg's `Files Affected` pinout under-specified. | **Yes** — leg-design-time `rg` sweep for stale references being changed. |
| L4: L3 placeholder comment for the test-section mount point did NOT actually exist (despite the L3 flight-log claim). | Flight-log claims about "leaves a comment for next leg" were honored as contract without grep verification. | **Yes** — flight-log future-leg contract claims must be verified at design time. |
| L6 inline addition: per-category tabs replacing single alphabetic list in admin grid. | HAT-discovered UX cliff at ~10 tools (currently 19). Re-used existing `App.tabs` primitive; tile DOM/wiring/sort preserved. | **Yes** — entity-grid layouts with >10 items default to tabbed grouping (or sortable headers). Worth a CLAUDE.md note. |
| L6 inline addition: error-banner promotion for model-level Pydantic 422s. | HAT operator preferred prominent banner over the small `.editor-error` `<span>`. Banner with `role="alert" aria-live="assertive"` + visual prominence + heuristic field-error-highlights for offending rows. | **Yes** — should be reused by provider-editor (currently uses the legacy `.editor-error` span). General pattern. |
| L6 inline addition: info-icon tooltips replacing inline `<p class="field-description">`. | HAT operator preferred discoverability-on-demand over visual noise. Native `title` attr; `cursor: help`; positioned right of input (not inside label). | **Yes** — any future form with field-level help should default to info-icon tooltips. |
| L6 inline addition: custom test-input fields with backend body-parameter widening for `/test` endpoint. | HAT operator wanted to verify constraints against arbitrary inputs, not just fixed fixtures. Defaults preserved via type-guarded body merge. | **Yes** — extends Decision 6 from "fixed-fixture diagnostic" to "operator-driven probe" without breaking fixture defaults. |
| L6 inline fix: PUT 500 → 422 (`include_context=False` on `e.errors()`). | Pydantic v2's `model_validator` paths emit `ValidationError.errors()` with raw exceptions in `ctx['error']` — NOT JSON-serializable; FastAPI's JSONResponse crashed. | **Yes** — applies to **every** FastAPI endpoint surfacing Pydantic validation. Codified in CLAUDE.md F6 addendum. |
| L6 inline fix: iOS-toggle CSS unpinning override (`.tools-editor-enabled-row .tool-enable-switch { position: relative; }`). | Grid tile's `.tool-enable-switch` is `position: absolute; bottom: 12px; right: 12px;` (designed for `position: relative` tile container). Inside an editor row it floated off-screen. | **No** — toggle-widget-positioning is context-specific. The unpinning override is the right local fix; codified in CLAUDE.md as a CSS-style-shadowing pattern. |
| L7 expansion: 34 browser tests vs. 8-12 spec'd. | Accurate-to-real-coverage given the L6 HAT fixes that needed regression nets. Not scope creep. | **Yes** — flight-design heuristic: HAT-induced test growth is a separate budget line (~2x multiplier on F6 data point). |
| L8 inline fix: `_wait_editor_ready` deep-link guard for L5's async `refreshToolConfigsCache().then(renderEditor)` race. | The L5 async editor mount made `editor_hidden` true at helper-call time even on deep-link; the click then races the editor mount and times out. | **Yes** — async-mount races require explicit `aria-selected` waits in test helpers. |
| L1 design pin: PUT REPLACE-not-merge (was leg-design discovery). | Decision 11 in flight.md said "upserts" without specifying merge-vs-replace. L1 picked REPLACE (REST convention). | **Yes** — flight-design phase should pin merge-vs-replace explicitly for any new PUT endpoint. |
| L5 helper extraction LoC ~770 vs. ~250 spec'd. | When a leg simultaneously extracts AND adds a new mode dispatch + new attribute pattern + lazy-fetch, the LoC estimate should sum three numbers (extraction + new-mode + callback hooks), not be a single figure. | **Yes** — flight-design heuristic: "extract X to shared module" legs get a 2-3x estimate multiplier. |

## Key Learnings

1. **Two-Reviewer-pass batching pays off at the right scale.** F6's first use (50 files, +10414 LoC, 9 implementation legs, ~80 lines of doc updates) was a clear win: zero stale-doc deviations vs. F5's 4. Cost was small (the second pass had 78-insert / 3-delete to verify). Below the threshold (≤4 legs, <500 LoC, minor doc touches), single-pass with the existing "doc author reads as-built" admonition is fine.
2. **Design-pass-per-leg catches subtle invariants that would ship broken.** L1's cross-Config shadowing fix is the canonical example: without the architect's review, the test endpoint would have run `web_search` through `http_request`'s saved config silently. The architect-spawn-per-leg overhead pays for itself when it catches even one such cliff per flight. F6 caught at least 3 (L0 stale-version assertions, L1 cross-Config shadowing, L5 5 high-severity issues including the helper-extraction list precision).
3. **HAT discovery cost is amortized, not eliminated, by upstream design.** F6 paid for HAT-discovered UX patterns (// prompt block, info icons, error banner, custom test inputs, etc.) on the way IN — the patterns didn't exist before F6. F7 forward inherits the canon: any future admin editor that needs these patterns consumes them rather than re-discovering. The HAT cadence was efficient for what it shipped (7 UX changes batched in one Developer pass).
4. **Shared-substrate extractions need their own design treatment.** L5 carried a pure refactor + a new mode dispatch + a new attribute pattern + a lazy-fetch + studio.js orchestration widening. Five concerns in one leg is too many; the L5 design pass needed 5 high-severity fixes (most of any leg) and an L5-introduced regression had to be fixed in L8. Future "extract X to shared module" legs should split into pure-refactor + additive-feature.
5. **Validation-error JSON-encoding is a project-wide gotcha, not just tool-config.** Pydantic v2's `model_validator` paths emit non-JSON-serializable `ctx['error']` values; FastAPI's JSONResponse crashes; result is 500 instead of 422. Applies to every FastAPI endpoint surfacing Pydantic validation in the project. The L6 HAT-discovered fix (`include_context=False` on `e.errors()`) is now codified in CLAUDE.md but should be retroactively audited across the existing endpoints (providers, agents, kbs, mcp).
6. **Leg artifacts are spec snapshots, not as-built records.** The 6+ HAT inline fixes that landed during L6 did NOT update the L2/L3/L4/L5 leg artifacts (intentionally — the artifacts capture what was *spec'd*). The flight-log Deviations section is the as-built diff index. Methodology pattern worth documenting: "leg artifacts are spec snapshots; flight-log Deviations is the as-built diff index."

## Recommendations

1. **Promote 5-8 F6-codified patterns to broader project conventions** (vs. tool-config-only). Specifically: REPLACE-not-merge PUT contract; `include_context=False` on Pydantic 422; lazy-fetch caches the Promise; humanize-validation-msg; editor-error banner with `role="alert"`; iOS-toggle CSS positioning trap; shared-form-helpers via context-object dispatch. Action: a routine-maintenance or next-flight pass to cross-reference these in CLAUDE.md outside the F6 section AND audit the existing provider/agent/kb/mcp endpoints for the JSON-encoding gotcha specifically (`pytest tests/test_db_api.py` should be extended with regression nets).

2. **Extract `TOOL_CATEGORIES` to `admin/tools-form-helpers.js`** (the shared substrate). The 19-entry map in `admin/tools-grid.js:12` and `admin/tools-editor.js:64` is duplicated; Studio's `tools-tab.js` consumes a parallel-shape map from agent-editor wiring. ~30 LoC change; mechanically straightforward; eliminates the "two-files-to-edit-on-tool-add" footgun.

3. **Standardize the two-Reviewer-pass batching threshold** in the `agentic-workflow` skill. Recommended threshold: flights with ≥5 legs OR ≥1 new shared-substrate module OR ≥1 new public API surface default to two-pass. Below that, single-pass with "doc author reads as-built" admonition. Currently the skill describes the pattern but doesn't pin when to use it.

4. **Add the missing edge-case tests** for (a) `AgentFactory.create()` raise on stale narrow override (operator narrows below agent's existing override → resolver raises clearly); (b) chip-list editor with non-string items (`list[int]`) — assert the `console.warn` fires via Playwright's `page.on('console')` capture; (c) panel close-during-in-flight-fetch race in studio override panels — assert no double-fired listeners on agent-switch mid-fetch.

5. **Document leg artifacts as spec snapshots, not as-built records** in CLAUDE.md or the `agentic-workflow` skill. Make the flight-log Deviations section the canonical as-built diff index. F6's 6+ HAT inline fixes are scattered across flight-log entries (with no leg-artifact updates) — the methodology pattern should be explicit so future contributors don't expect leg artifacts to reflect inline HAT fixes.

## Action Items

- [ ] **Extract `TOOL_CATEGORIES` to `admin/tools-form-helpers.js`** — eliminates the dual-file edit on tool-add. ~30 LoC routine-maintenance pass.
- [ ] **Promote `humanizeValidationMsg` to a shared utility** (`App.humanize` or similar). De-duplicate the mirror between `tools-editor.js:493` and `tools-form-helpers.js:448`. Provider-editor and agent-editor 422 paths benefit.
- [ ] **Audit existing FastAPI endpoints for `ValidationError` JSON-encoding** — `e.errors(include_context=False)` should be the project default. Likely `the_one/interfaces/web/api.py` provider/agent/kb/mcp PUT/POST endpoints affected. Add regression tests for the model-validator path.
- [ ] **Document drift-warn behavior** at `tools-tab.js:194-196` in CLAUDE.md F6 section — what the warn means and how to recover (operator should re-save the agent's overrides through the Studio UI).
- [ ] **Document resolver-as-security-boundary** explicitly in CLAUDE.md F6 section — "client-side widget shape is UX; resolver at AgentFactory.create() raises the security check."
- [ ] **Add missing edge-case tests** for stale-narrow override factory-raise + chip-list non-string items + panel close-during-fetch race.
- [ ] **Pin the two-Reviewer-pass batching threshold** in `.claude/skills/agentic-workflow/SKILL.md` (mission-control repo) — when to use two-pass vs. single-pass.
- [ ] **Update CLAUDE.md / agentic-workflow methodology** with: leg artifacts are spec snapshots; flight-log Deviations is the as-built diff index.
- [ ] **Chip-list editor UX polish** (already in mission Known Issues, deferred to a future flight) — no commit-on-Enter affordance hint; chip pill density; consider Add button.
- [ ] **Pre-flight prereq verification** as a flight-design checklist item: "find existing references to be updated" via `rg` sweep before sizing the leg's `Files Affected`.
- [ ] **Future "extract X to shared module" legs**: 2-3x LoC estimate multiplier; consider splitting pure-refactor from additive-feature into separate legs (L5a / L5b pattern).

# Leg: pre-existing-browser-failures-investigation-and-fix

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

## Objective

Resolve the 2 pre-existing browser-test failures the flight named (deferred across 4 flights): `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` and `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`. Investigate-at-implementation: diagnose each failure's mode, then fix the product OR update the assertions depending on which side drifted, and document the disposition.

## Context

- **Flexible-scope DD (operator-directed)**: these 2 haven't been triaged in 4 flights. Either trivial assertion drift (legit DOM change) OR real product regressions. The implementing Developer (a) diagnoses first, then (b) fixes product OR updates assertions per which side actually drifted. AC is deliberately flexible: "after L5, neither test fails, and the disposition (product-fix vs test-update) is documented in the flight-log L5 entry."
- **Divert clause**: if either failure surfaces >3-day product-regression work, divert into a separate maintenance flight + restore L5 to the lighter scope (or rationalize-only). Do NOT let L5 balloon.
- **Test 1 specifics** (`test_flow_agent_tabs.py:68`): the test name says "three" but it already asserts **4 tabs** (General/Knowledge/MCPs/Built-in Tools) per its own docstring ("Leg 02 added the MCPs tab; count is now 4"). So the stale NAME is not the failure cause — something else drifted (a 5th/removed tab, a testid rename, the async editor-mount race at `_wait_editor_ready`, or the aria-selected assertions). If the only drift is the name, rename it to match (`..._with_four_tabs`) as part of the test-update disposition.
- **Test 2 specifics** (`test_flow_studio_navigation.py:253`): asserts that Agents→Knowledge→Agents preserves the selected agent AND the class strings `studio-editor` (not `is-hidden`) / `studio-section-content is-hidden`. Failure could be a class-string drift, the `studio-knowledge-stub` testid, or a real state-preservation regression.
- **Broader baseline caveat (from L4 review)**: the flight's "454 passed / 2 pre-existing failures" baseline is WRONG — L4 already found+fixed 3 more failures in the inference file. A full-browser-suite run is being taken to establish the TRUE failure set. **L5 stays scoped to these 2 named tests.** Any OTHER failures the full run surfaces are NOT L5's to fix silently — the FD triages them separately (fold into a leg if cheap, or file as a deferred Known Issue). L5 must not silently absorb unrelated failures.

## Inputs

- `tests/browser/test_flow_agent_tabs.py:68-89` — `test_tablist_renders_with_three_tabs`; `_wait_editor_ready` helper at `:55-64`.
- `tests/browser/test_flow_studio_navigation.py:252-283` — `test_studio_section_round_trip_preserves_agent_selection`; `_wait_studio_ready` helper.
- The agent-editor tab render + studio section-nav code (located during diagnosis).
- Design-review failure-mode report (the reviewer runs both tests and captures WHY each fails — feeds the fix).

## Outputs

- Both named tests pass.
- Flight-log L5 entry documents, per test: the diagnosed failure mode + the disposition applied (product-fix vs test-update, with rationale).

## Diagnosis (design-review confirmed — both are TEST-UPDATE, no product fix)

Both failures trace to the SAME commit `93c4120` (flight/06 #65, per-agent ACLs) — byproducts of one feature landing, deferred across 4 flights.

- **Test 1 `test_tablist_renders_with_three_tabs`** (`test_flow_agent_tabs.py:82`): `to_have_count(4)` fails — actual **5**. A 5th tab **Connectors** (`data-testid="tab-connectors"`) was legitimately added (`agent-editor.js:104-106`, panel map `:46-50`); order is General/Knowledge/MCPs/Connectors/Built-in Tools. **Disposition: TEST-UPDATE.** Bump count 4→5; add a `tab-connectors` `aria-selected="false"` assertion (match the sibling per-tab pattern); rename `test_tablist_renders_with_three_tabs` → `..._with_five_tabs`; fix the stale docstring ("MCPs tab so count is now 4"). Effort ~15 min.
- **Test 2 `test_studio_section_round_trip_preserves_agent_selection`** (`test_flow_studio_navigation.py:280`): `.studio-editor` is `is-hidden` after the round-trip. The contract was DELIBERATELY INVERTED (`studio.js:444-452`, M10 F6 L7 HAT comment): leaving Agents now clears `_selectedAgent` → returning lands on the tile grid (editor hidden). The test encodes the OLD contract. **Disposition: TEST-UPDATE.** Invert: `.studio-editor` HAS `is-hidden`; `.studio-section-content` does NOT have `is-hidden`. **DROP the line-279 `editor-title == agent_name` assertion** — it passes only on STALE hidden-editor DOM, so leaving it asserts a misleading observable. Rename the test + rewrite the docstring to the listing-on-return contract. Effort ~30-45 min. (The sibling `test_studio_editor_hidden_on_knowledge_section` already asserts the NEW contract and passes — confirms the inversion is intended.)
- **Sibling scan**: only these 2 tests fail; the fix is not broader.

## Acceptance Criteria

- [ ] `test_flow_agent_tabs.py` tab-count test passes: count asserted as **5**, `tab-connectors` aria-selected=false assertion added, function renamed to `..._with_five_tabs`, docstring corrected. (The rename + count bump are MANDATORY — the drift is a real 4→5 count change, not just a stale name.)
- [ ] `test_studio_section_round_trip_preserves_agent_selection` passes with INVERTED assertions (editor hidden / section-content visible after the round-trip), the misleading line-279 `editor-title` assertion DROPPED (not just flipped), and the docstring rewritten to the listing-on-return contract.
- [ ] Both dispositions are TEST-UPDATE (confirmed by diagnosis) — NO product code change. If implementation surprisingly reveals a product issue, STOP and report rather than changing product.
- [ ] The flight-log L5 entry states the disposition per test (both test-update, root cause = commit `93c4120`) with one-line rationale.
- [ ] No OTHER browser tests are modified to force them green (L5 is scoped to these 2; unrelated failures go to the FD, not silent edits here).
- [ ] Browser run via the bounded wrapper; no orphaned chromium after.
- [ ] If either test surfaces >3-day product work → STOP, signal `[BLOCKED]`, and the FD diverts to a maintenance flight per the divert clause (do not balloon L5).

## Verification Steps

- `docker exec the-one bash -c 'TEST_TIMEOUT=400 bash /app/scripts/run-tests.sh -m browser tests/browser/test_flow_agent_tabs.py tests/browser/test_flow_studio_navigation.py -q'` — both files pass; confirm no stragglers after.
- Flight-log L5 entry present with per-test diagnosis + disposition.

## Implementation Guidance

1. **Diagnose first — do NOT edit anything yet.** Run each failing test in isolation via the wrapper, capture the exact assertion that fails and the actual-vs-expected. For DOM-shape failures, inspect the live rendered DOM (the rendering source) to determine whether the PRODUCT changed (legit) or the TEST is stale.
2. **Classify per test**: product-drift (the app's behavior/DOM legitimately changed since the test was written → update the test assertion to match) vs product-regression (the app broke → fix the product). The 4-flight deferral + the "three/4" name staleness suggest test-drift is likely, but verify — don't assume.
3. **Apply the right fix.** Test-update: minimal assertion/name change matching current reality. Product-fix: the smallest change that restores the contract the test encodes (and confirm it doesn't break sibling tests in the same file).
4. **Re-run both files** via the wrapper → green. Run the immediate sibling tests in each file too (cheap) to confirm no collateral.
5. **Document disposition** in the flight-log L5 entry: per test, the failure mode + product-fix-vs-test-update + rationale.
6. **Divert if heavy**: if diagnosis shows >3-day product work for either, STOP and signal `[BLOCKED]` with the specifics; do not attempt a large fix inside L5.

## Edge Cases

- **The "three" name is the only issue**: rename to `..._with_four_tabs` (test-update) — but first confirm the test actually fails on the count/assertions, not just carries a stale name (a stale name alone doesn't fail a test).
- **A fix touches shared rendering used by other tests**: run the whole affected browser file, not just the one test, before declaring green.
- **More than these 2 fail in the full suite**: NOT L5's scope — report to the FD; do not edit them here.

## Files Affected

- `tests/browser/test_flow_agent_tabs.py` and/or the agent-editor tab render (depending on disposition).
- `tests/browser/test_flow_studio_navigation.py` and/or the studio section-nav code (depending on disposition).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] Both named tests pass (wrapper used; no orphans)
- [ ] Per-test diagnosis + disposition documented in flight-log L5 entry
- [ ] No unrelated browser tests force-edited
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (Phase 2d)
- [ ] Do NOT commit (batched at Phase 2d)

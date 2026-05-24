# Leg: triage-test-connection-button-cluster

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Close the 3-flight-deep chronic-debt cluster at `tests/browser/test_connector_test_connection_button.py` by updating ALL THREE `status:'ok'` tests to assert `details_wrap` hidden on the success path — matching the production code's explicit M07-inspector-convention behavior at `connector-account-editor.js:renderTestConnectionBanner` (lines 1625-1631), where `status === 'ok'` unconditionally hides the details panel.

## Context

- Relevant Design Decision: **Test-connection-button triage — "update ALL three `status:'ok'` tests to match code"** (operator-confirmed at L2 after Architect cycle-1). The decision direction is "update test to match code" because the code's intent matches the M07 inspector-pattern precedent (status + one-sentence message at-a-glance; full structured detail behind a panel that opens only when something needs debugging); the tests were written ahead of the operator-friendly shipping shape.
- Architect cycle-1 finding (carried in F3 design log): the test file contains **7 tests total**, of which **three** assert `status='ok'` with visible-details expectations:
  - `test_default_stub_probe_renders_success_with_no_details` (lines 44-69): asserts `expect(details_wrap).to_be_visible()` (line 67) AND `expect(details).to_contain_text("no additional details")` (line 69). Both assertions are now misaligned with code (the wrap is hidden and the placeholder string is never rendered on `status:'ok'`).
  - `test_non_string_detail_renders_as_font_mono_json` (lines 153-187): seeds `status:'ok'` with `details={count:42, enabled:True, tags:["a","b"]}`. Asserts `details.locator("code.font-mono", has_text="42").to_be_visible()` (line 186) and `... has_text="true").to_be_visible()` (line 187). Both fail because `details_wrap` is hidden on `status:'ok'` and the child `<code.font-mono>` elements are inside the hidden wrap.
  - `test_secret_shaped_detail_value_passes_through_unmasked` (lines 190-223): seeds `status:'ok'` with `details={masked_token:"***...abc1"}`. Asserts `expect(details).to_contain_text(masked_value)` (line 223). Fails because `details_wrap` is hidden.
- The 4 sibling tests in the same file are NOT modified and MUST continue to pass byte-identically post-leg:
  - `test_test_connection_button_visible_in_edit_mode` (lines 23-30): button-renders-in-edit-mode AC; no details-wrap assertions.
  - `test_test_connection_button_absent_in_create_mode` (lines 33-40): button-absent-in-create-mode AC; no details-wrap assertions.
  - `test_configured_failure_response_renders_red_led_and_details` (lines 72-115): `status:'failed'` path; details_wrap expected visible with k/v contents. This test EXERCISES the string-detail rendering path (`renderDetailsBlock` of `{http_status:'401', platform:'stub-platform'}`) and IS the regression contract for that code path. It does NOT exercise the `<code class="font-mono">` rendering shape — that shape is only emitted by `_renderDetailsValue` for non-scalar arrays and at depth >= 4 (`connector-account-editor.js:1675` and `:1683`). So the `<code class="font-mono">` assertions in the original `test_non_string_detail_renders_as_font_mono_json` were arguably testing a code path that the seeded payload `{count:42, enabled:True, tags:["a","b"]}` doesn't actually produce — independent evidence that "update tests to match code" is the right L2 direction. (See Edge Cases for the methodology implication.)
  - `test_degraded_response_renders_warning_led` (lines 118-150): `status:'degraded'` path; LED + class only, no details-wrap assertion.
- Why "update test to match code" not "update code to match tests": (a) the code's behavior is operator-friendly (clean green-LED on success, no noisy details panel); (b) the code matches the explicit M07-inspector-convention comment block (lines 1619-1624); (c) the F2 debrief's earlier hypothesis ("missing `details_wrap.hidden = false` toggle") was inverted at F3 recon time — the code IS explicit, the tests are stale. The cycle-1 architect surfaced this inversion; the operator accepted "update tests" at planning.

## Inputs

- `tests/browser/test_connector_test_connection_button.py` exists with 7 tests as enumerated above (verified at F3 design review).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderTestConnectionBanner` (lines 1582-1633) unconditionally hides `details_wrap` when `status === 'ok'` and unconditionally shows it when not-ok. The M07-inspector-convention comment block at lines 1619-1624 documents the intent.
- The failure-status test `test_configured_failure_response_renders_red_led_and_details` at lines 72-115 already pins details rendering on the not-ok path.
- F3 L1 has landed (per the agentic-workflow protocol, L1's changes are uncommitted but present in the working tree).

## Outputs

- `tests/browser/test_connector_test_connection_button.py` is updated in exactly the three named tests:
  - `test_default_stub_probe_renders_success_with_no_details`: `expect(details_wrap).to_be_visible()` flips to `to_be_hidden()`; the `expect(details).to_contain_text("no additional details")` assertion is dropped (moot — the placeholder text is not rendered when the wrap is hidden, and the operator never sees it). The existing LED `data-state="ok"` assertion at line 58 serves as the click-handler synchronization point.
  - `test_non_string_detail_renders_as_font_mono_json`: the two `expect(details.locator("code.font-mono", has_text=…)).to_be_visible()` assertions are dropped; replaced with one `expect(details_wrap).to_be_hidden()` assertion AFTER the existing LED `data-state="ok"` assertion at lines 181-183 (the LED assertion is the synchronization point). The test still pins that `status:'ok'` with non-string detail values does not surface a details panel.
  - `test_secret_shaped_detail_value_passes_through_unmasked`: the `expect(details).to_contain_text(masked_value)` assertion is dropped; replaced with TWO new assertions in order: (1) `expect(led).to_have_attribute("data-state", "ok", timeout=8000)` as the click-handler synchronization point (matching the test 2 pattern); (2) `expect(details_wrap).to_be_hidden(timeout=8000)` to pin the no-leak behavior. The synchronization assertion is mandatory — without it, the hidden-by-default initial state of `details_wrap` (`connector-account-editor.js:429`) would make the hidden assertion trivially pass even if the click never fired.
- Each updated test's docstring is rewritten to describe the new shape ("`status:'ok'` hides the details panel — M07 inspector convention; details surface only on debug-needed states"). The existing docstrings claim visible-details behavior that no longer matches code.
- No production code is modified. No other test files are modified.

## Acceptance Criteria

- [x] In `tests/browser/test_connector_test_connection_button.py:test_default_stub_probe_renders_success_with_no_details`, the assertion `expect(details_wrap).to_be_visible()` is replaced with `expect(details_wrap).to_be_hidden()`.
- [x] In `tests/browser/test_connector_test_connection_button.py:test_default_stub_probe_renders_success_with_no_details`, the assertion `expect(details).to_contain_text("no additional details")` is removed entirely (the placeholder text is never rendered on `status:'ok'`).
- [x] In `tests/browser/test_connector_test_connection_button.py:test_default_stub_probe_renders_success_with_no_details`, the `details = page.locator('[data-testid="connector-test-details"]')` locator line is removed if no remaining assertions reference it (verify by reading post-edit; keep if any remaining assertion still uses `details`).
- [x] In `tests/browser/test_connector_test_connection_button.py:test_non_string_detail_renders_as_font_mono_json`, the two `expect(details.locator("code.font-mono", has_text=…)).to_be_visible()` assertions (at lines 186-187 pre-edit) are removed.
- [x] In `tests/browser/test_connector_test_connection_button.py:test_non_string_detail_renders_as_font_mono_json`, a new assertion `expect(details_wrap).to_be_hidden()` is added after the LED `data-state` assertion (the test still pins that `status:'ok'` hides the details panel even when the payload has non-string detail values). The `details_wrap` locator line `details_wrap = page.locator('[data-testid="connector-test-details-wrap"]')` is added if not present.
- [x] In `tests/browser/test_connector_test_connection_button.py:test_secret_shaped_detail_value_passes_through_unmasked`, the assertion `expect(details).to_contain_text(masked_value, timeout=8000)` is removed.
- [x] In `tests/browser/test_connector_test_connection_button.py:test_secret_shaped_detail_value_passes_through_unmasked`, a new LED synchronization assertion `expect(led).to_have_attribute("data-state", "ok", timeout=8000)` is added IMMEDIATELY after the click (matching the pattern at test 2 lines 181-183). The `led = page.locator('[data-testid="connector-test-led"]')` locator is added if not present. This assertion is the load-bearing proof that the click handler executed — without it, the subsequent `to_be_hidden()` assertion is trivially-true (the wrap starts hidden per `connector-account-editor.js:429`) and would pass even if the click never fired.
- [x] In `tests/browser/test_connector_test_connection_button.py:test_secret_shaped_detail_value_passes_through_unmasked`, a new assertion `expect(details_wrap).to_be_hidden(timeout=8000)` is added AFTER the LED data-state synchronization assertion (the test still pins that `status:'ok'` hides the details panel even when the payload contains masked-token-shaped detail values — confirming no leak path). The `details_wrap` locator is added if not present.
- [x] Each updated test's docstring describes the new shape (one of: "status:'ok' hides the details panel — M07 inspector convention" / "non-string details on ok-status are not surfaced — wrap stays hidden" / "masked-token details on ok-status do not leak — wrap stays hidden"). The original docstring claims that no longer match code are removed.
- [x] The 4 sibling tests in the same file are byte-identical to their pre-leg state: `test_test_connection_button_visible_in_edit_mode`, `test_test_connection_button_absent_in_create_mode`, `test_configured_failure_response_renders_red_led_and_details`, `test_degraded_response_renders_warning_led`. Verify with `git diff` — no hunks should touch any of those 4 functions.
- [x] No other test file is modified.
- [x] No production code is modified. `git diff --stat` shows changes ONLY in `tests/browser/test_connector_test_connection_button.py` plus the F3 sibling artifacts (flight.md, flight-log.md, this leg artifact).
- [x] The full file at `tests/browser/test_connector_test_connection_button.py` is syntactically valid Python (verified by `python -m py_compile`).

## Verification Steps

- `git diff tests/browser/test_connector_test_connection_button.py` shows diff hunks confined to the three named test functions. The 4 sibling functions are NOT touched.
- `git diff --stat` shows changes only in `tests/browser/test_connector_test_connection_button.py` plus the F3 sibling artifacts.
- `python -m py_compile tests/browser/test_connector_test_connection_button.py` succeeds (syntactic validity).
- Run the updated tests against the live browser stack. In the project's test mode: `docker exec the-one pytest tests/browser/test_connector_test_connection_button.py -x --timeout 60 -q` (or the equivalent project-standard invocation). All 7 tests pass. The 3 updated tests now pin the hidden-on-ok behavior; the 4 sibling tests continue passing byte-identically.
- Spot-grep: `grep -n "details_wrap" tests/browser/test_connector_test_connection_button.py` returns hits at the three updated tests plus any pre-existing references. Each updated test contains exactly one `to_be_hidden()` assertion on `details_wrap`.

## Implementation Guidance

1. **Read the test file in full.** Confirm the line numbers in this leg spec match the actual code (line numbers drift; if they have drifted, locate the assertions by symbolic anchor — the `expect(details_wrap)` calls and the `details.locator("code.font-mono", ...)` calls).

2. **For `test_default_stub_probe_renders_success_with_no_details` (around lines 43-69):**
   - Replace `expect(details_wrap).to_be_visible()` with `expect(details_wrap).to_be_hidden()`.
   - Remove the `expect(details).to_contain_text("no additional details")` assertion (the placeholder text is never rendered when `details_wrap` is hidden).
   - If the resulting test no longer references the `details` locator, also remove the locator line `details = page.locator('[data-testid="connector-test-details"]')` to keep the test tight.
   - Rewrite the docstring from "green LED + '(no additional details)' placeholder rendered" to something like "`status:'ok'` + empty details → green LED, no details panel surfaced (M07 inspector convention)".

3. **For `test_non_string_detail_renders_as_font_mono_json` (around lines 153-187):**
   - Remove the two `expect(details.locator("code.font-mono", has_text=…)).to_be_visible()` assertions.
   - Add `details_wrap = page.locator('[data-testid="connector-test-details-wrap"]')` before the new assertion.
   - Add `expect(details_wrap).to_be_hidden()` after the existing `data-state` assertion at the LED.
   - Remove the now-orphan `details = page.locator(...)` line if no remaining assertions reference it.
   - Rewrite the docstring from "Non-string detail values render as <code class='font-mono'> JSON." to something like "Non-string detail values do NOT surface on `status:'ok'` — details panel stays hidden per M07 inspector convention. (Failure-status path covers the `<code class='font-mono'>` rendering shape.)".

4. **For `test_secret_shaped_detail_value_passes_through_unmasked` (around lines 190-223):**
   - Remove the `expect(details).to_contain_text(masked_value, timeout=8000)` assertion.
   - Add `led = page.locator('[data-testid="connector-test-led"]')` before the new assertions.
   - Add `details_wrap = page.locator('[data-testid="connector-test-details-wrap"]')` before the new assertions.
   - Add `expect(led).to_have_attribute("data-state", "ok", timeout=8000)` IMMEDIATELY after the click. This is the load-bearing synchronization point — without it, the subsequent `to_be_hidden()` would trivially pass against the initial hidden state of `details_wrap` (set at `connector-account-editor.js:429` via the `hidden` HTML attribute on initial render). Match the test 2 pattern at lines 181-183.
   - Add `expect(details_wrap).to_be_hidden(timeout=8000)` AFTER the LED assertion.
   - Remove the now-orphan `details = page.locator(...)` line if no remaining assertions reference it.
   - Rewrite the docstring from "A details value that is already masked (`***...abc1`) passes through verbatim — no double-masking, no plaintext leakage path." to something like "A masked-token detail value on `status:'ok'` is never surfaced — `details_wrap` is hidden per M07 inspector convention. The no-leak property is preserved structurally (the wrap never renders, so the token never reaches the DOM)."

5. **Verify no other lines move.** The function boundaries and the surrounding pytest fixtures should be byte-identical. Use `git diff` to confirm.

6. **Sibling-test byte-identity check.** Run `git diff` on the file and confirm there are no hunks inside the 4 sibling test function bodies. If any whitespace adjustment crept in, revert it.

7. **Run the file against the browser stack.**
   - The project runs browser tests via `docker exec the-one pytest …` per the leg-execution.md crew prompt. Use `-x --timeout 60 -q` for autonomous iteration (the `60` is browser-tier appropriate — Playwright + uvicorn subprocess startup are slower than unit tests; the crew-prompt default `--timeout 30` is for unit tier).
   - All 7 tests must pass.
   - **Spurious-pass risk**: if one of the 3 updated tests passes but the click handler is broken (network wedged, JS error fired, button selector wrong), the trivially-hidden initial state of `details_wrap` would make `to_be_hidden()` pass without exercising real behavior. Mitigation per step 4 above: every updated test must have a click-handler synchronization assertion BEFORE the hidden check (LED `data-state="ok"` is the canonical pattern). If you suspect a spurious pass, deliberately break the click handler (e.g., point the locator at a non-existent testid) and verify the test FAILS — if it still passes, the synchronization point is missing.
   - **Sibling-test regression risk**: a fail in a sibling test usually means inadvertent edit damage; revert the sibling's body to its pre-leg state.
   - Do NOT use `xfail` or `skip` to paper over a failure. Diagnose and fix.

8. **Sibling artifact bookkeeping.** Check off L2 in flight.md (Checkpoints + Legs sections). Append an L2 leg-progress entry to flight-log.md.

9. **Update this leg artifact's status header.** `ready → in-flight → landed` per the leg lifecycle. Per the F3 batched protocol, do NOT commit and do NOT signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Test-file line number drift**: between leg-design time and leg-implementation time, F1 + F2 changes have already landed but L1's diff did not touch this file. If line numbers in this spec are off by ±5, the symbolic anchors (the assertion calls themselves) are reliable. Use grep / read to locate.

- **`page.route()` fulfill setup still required**: tests 2 and 3 (`test_non_string_detail_renders_as_font_mono_json` and `test_secret_shaped_detail_value_passes_through_unmasked`) rely on Playwright's `page.route()` fulfill to inject `status:'ok'` payloads with non-empty details. The route setup MUST stay intact — only the post-click assertions change. If a developer removes the route setup, the test will hit the live stub doctor (which returns `details={}`) and the test loses its discriminating power.

- **Sibling-test regression coverage for non-string detail rendering**: the L2 leg DROPS the `<code class="font-mono">` assertions from the ok-status path of `test_non_string_detail_renders_as_font_mono_json`. **Inspection finding from L2 design review**: the original assertions were arguably testing a code path the seeded payload doesn't actually emit. `_renderDetailsValue` (`connector-account-editor.js:1646-1700`) emits `<span class="connector-test-details-value">` for scalars/numbers/booleans (lines 1654, 1657); `<code class="font-mono">` is only emitted for non-scalar arrays (line 1675) and at depth >= 4 (line 1683). The seeded payload `{count:42, enabled:True, tags:["a","b"]}` produces scalars + a scalar-array — neither shape emits `<code class="font-mono">`. So the original assertions may have been silently broken (asserting visibility of elements that never existed) and only "passed" because Playwright's `to_be_visible()` against zero elements has subtle semantics. **Independent evidence** that "update tests to match code" is the right L2 direction. **Coverage gap acknowledged**: no test in this file exercises the actual `<code class="font-mono">` rendering shape; if a future regression breaks it (e.g., breaks the `Array.isArray(value)` branch or the depth check), no test in this file catches it. **Decision**: acceptable per the F3 flight scope (dropdown UX, not test-connection-button regression coverage). Methodology lesson worth surfacing at F3 debrief: tests written against a hypothetical rendering shape that the seeded payload doesn't actually produce.

- **`(no additional details)` placeholder string in production code**: the `renderDetailsBlock(details)` function at `connector-account-editor.js:1635-1639` still produces the `(no additional details)` placeholder for empty details on the not-ok path. So the string itself is still in production code; the L2 leg only stops asserting it on the ok-status path. The `renderDetailsBlock` function is invoked only on the not-ok branch at line 1629, so the placeholder will only render when `status !== 'ok'` AND `details = {}` — an edge case but possible. No test exercises this exact combination today; the L2 leg does not change that.

- **Trivially-true `to_be_hidden()` against a hidden-by-default element**: `details_wrap` is rendered with the `hidden` HTML attribute on initial DOM construction (`connector-account-editor.js:429`). This means `expect(details_wrap).to_be_hidden()` passes trivially BEFORE the click — even if the click handler is broken, the network is wedged, or a JS error fires. **Mitigation**: every test that asserts `to_be_hidden()` MUST do so AFTER a click-handler synchronization assertion (the LED `data-state="ok"` assertion is the canonical pattern). Tests 1 and 2 already have such assertions before the wrap check; test 3's leg implementation MUST add one (specified in step 4 of Implementation Guidance and in the ACs).

- **Browser test infra availability**: per the leg-execution.md crew prompt, browser tests run via `docker exec the-one pytest …`. If the `the-one` container is not running, the developer must start it first. The leg implementation assumes the container is available (operator has indicated this is the local dev posture).

## Files Affected

- `tests/browser/test_connector_test_connection_button.py` — three test functions updated (assertions flipped + docstrings rewritten); 4 sibling functions untouched.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` — L2 checkpoint + L2 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight-log.md` — L2 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/legs/02-triage-test-connection-button-cluster.md` — this artifact's status header progresses through its lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; diff confined to the three named tests; sibling tests byte-identical)
- [x] Tests pass: `docker exec the-one pytest tests/browser/test_connector_test_connection_button.py -x --timeout 60` reports 7/7 passed
- [x] Update `flight-log.md` with L2 leg-progress entry
- [x] Set this leg's status to `landed` (Developer signals review-needed at flight end; status reaches `completed` after the final commit lands)
- [x] Check off L2 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F3 batches review + commit at flight end per the agentic-workflow protocol)

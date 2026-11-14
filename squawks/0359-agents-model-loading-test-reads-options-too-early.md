# Squawk 0359: an agents-lane test reads the model options before the list has loaded

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
`tests/browser/test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading` fails in the `agents` lane on a busy host and passes when run alone. The product is not at fault; the test has a race.

After it releases the held model-list request, the test waits with `expect(page.locator("#studio-model")).to_have_value("mock-default")`. That is already true while the list is still loading (the form shows the stored model meanwhile), so the wait returns at once. The test then reads the `<option>` values and asserts the first is the empty placeholder. If the list has not landed yet, the options are still `['mock-default']`.

Failure: `AssertionError: ['mock-default']` at `assert texts[0] == "", texts`.

Reproduce: run the `agents` lane inside `make gate` on a loaded host. It does not reproduce alone.

Expected: the test waits for the loaded state before it reads the options, for example for the placeholder option to exist, or for the option count to be the placeholder plus the models.

## Evidence
- `tests/browser/test_flow_agents_focus_after.py:232-236` — the `to_have_value` wait, then `eval_on_selector_all("#studio-model option", …)` and the two assertions.
- Sortie 16 (2026-11-14): failed in leg 4's `agents` lane run (185 passed, 1 failed) and again in the closing gate (`PARALLEL_RESULT rc=1 … failed=agents`, start load 1.70); passed 3 of 3 alone (about 3 s each).
- The same failure, each time passing alone, is recorded in `sorties/08-self-configuration-off-tools-tab/flight-log.md` (line 85) and `sorties/09-per-agent-mcp-credentials/flight-log.md` (lines 238 and 241). No squawk was logged then.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

## Disposition
**Deferred**: found during sortie 16, which is not chartered to fix it — revisit at the next squawk turnaround, or sooner if it fails a gate again. It has now cost three flights a re-run.

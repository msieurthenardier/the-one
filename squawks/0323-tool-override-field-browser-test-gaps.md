# Squawk 0323: Three tool-override field behaviours are verified only by code read

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
Sortie 07's flight review accepted three field-state paths on the agent editor's Built-in tools tab as verified by code read only. Add a browser test for each:
1. **A plain text field** (not a number or chip list): edit makes it own, and clearing it returns it to inherited, written back on blur.
2. **Paste** into a number or text field: it makes the field own, the same as typing.
3. **A 422 shown on a field that is then emptied:** the error clears, the field returns to inherited, and the `aria-describedby` ids stay correct.

## Evidence
- `sorties/07-agent-tool-overrides/flight-log.md`, the flight review's non-blocking notes, item (c): "Test gaps: a plain text field, paste, and a 422 shown on a field that is then emptied. Each was verified by code read."
- `the_one/interfaces/web/static/js/areas/shared/tool-override-state.js::touch`.
- Existing coverage: `tests/browser/test_flow_studio_tool_override_state.py`.

## Corrective Action
Tests only, no product change. Three browser tests added to `tests/browser/test_flow_studio_tool_override_state.py` (the `fetch_url` `default_user_agent` field is the plain text field; `http_request` `timeout_seconds_max` the number field):
1. `test_a_plain_text_field_is_own_when_edited_and_inherited_when_cleared`: edit makes it own, clearing returns it to inherited (state text, Reset hidden, editor clean against an empty store), and with a stored own value clearing dirties the editor and Save removes it. Finding: a Substitute text field inherits as an EMPTY box (`seedValue`), so there is no inherited text to write back on blur; the test pins that.
2. `test_pasting_into_a_text_or_number_field_makes_it_own`: `page.keyboard.insert_text` (the browser's own insertion, an `input` event, as a paste fires) makes a text and a number field own, and Save stores both. It does not drive the OS clipboard.
3. `test_a_422_on_a_field_that_is_then_emptied_clears_and_keeps_the_ids`: a stubbed 422 lands on the number field; emptying it clears the error, returns it to inherited, shows the app-wide value on blur, and every `aria-describedby` id resolves to a node that carries the inherited hint and not the refusal.

Falsification (edits to `areas/shared/tool-override-state.js`, restored by edit, `git diff` empty): test 1 FAILS with the clear-to-inherited branch in `touch` disabled (`if (false && ownValue() === undefined)`); test 2 FAILS with `st.own = true` removed from `touch`; test 3 FAILS with the same clear-to-inherited branch disabled. Test 3's error-clearing and describedby assertions could NOT be falsified independently: the number field's own `validate` listener clears the error and the field library keeps the hint in `aria-describedby`, so disabling the `serverError` branch, the `syncDescribed` calls, or `syncDescribed` entirely left it green. Those assertions are kept as regression pins but only the "returns to inherited" part is proven to bite.

## Verification
Done: the new tests passed 3 of 3 runs together; the whole file passes (28 passed, `THE_ONE_TEST_NETNS=1 scripts/run-tests.sh ... -m browser`); `ruff check` and `ruff format --check` clean. The full `agent-tabs` lane was not run (one browser file at a time was the batch rule). Original criteria:
- The three tests are in `tests/browser/test_flow_studio_tool_override_state.py`, in the `agent-tabs` lane.
- Each test is falsified: it fails with the behaviour it pins reverted.
- The `agent-tabs` lane passes.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-` (this includes the `agent-tabs` lane).

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`

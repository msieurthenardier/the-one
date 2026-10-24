# Leg: tools-editor-test

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Rebuild the tools editor's Test section (`web_search` and `fetch_url`) on the library, with a readable result (A15) and a standard input (A16):
- a `field` input with the Test button on its line;
- an `App.ui.status` result with one status mark and a fixed headline per outcome;
- the raw output under a collapsed "Technical details" `disclosure`, showing the head of the output.

## Context
- **Flight decisions:** DD6 (the Test section, with the fixed headline rule), DD7 (ledger rows 15 and 16), DD3 (`fetchJson`; errors), DD5 (`latest()` for the Test request).
- **Today** (`tools-editor.js` about `:159-195`, `:575-747`): a `div.section-title-row` with a hand-built info button; a hand-built inline-labelled input (`label.test-tool-input-label > span + input.test-tool-input[data-test-param]`); `button.test-tool-btn` (`data-testid="test-tool-btn"`) with `App.icon('play')`; the status `span.test-result` filled with glyph strings ("● ✗ Refused (0 ms)", "✓ Returned (N ms)"); the output `pre.tool-test-output`, showing the **last** 2 KB of the agent-facing string. `_TESTABLE_TOOLS` (`:57`) mirrors the backend; `TEST_FIXTURES` (`:68-71`).
- **After:**
  - `App.ui.section({title: 'Test connection', info: {text: <today's hint>, label: 'About Test connection'}})`;
  - an `App.ui.field({label: 'URL'|'Query'})` with an `App.ui.textInput` (`data-test-param` kept) and an `App.ui.button({label: 'Test connection', icon: 'play', variant: 'secondary', testid: 'test-tool-btn'})` on the same line;
  - an `App.ui.status` result with one status mark and **fixed headlines**: "Returned a result ({N} ms)", "Blocked by this tool's settings ({N} ms)", "Request failed". The client never parses the tool's model-facing error string; the outcome comes from the route's response shape (read `POST /api/tools/configs/{name}/test` in `api.py`);
  - `App.ui.disclosure({summary: 'Technical details', bordered or plain})` holding a `codeBlock` of the output (`maxHeight: 'short'`, `label: 'Test output'`), with the **first** 2 KB and "…" marking the truncation;
  - HTML entities in the output (`&#x27;`) are decoded for display only if the route returns them encoded in a JSON string; check where they come from. If the tool emits them, leave it and record it.
  - The Test request uses `latest()` and the editor's identity check. A stale result writes nothing.
- **Testids kept:** `test-tool-btn`; the result and output get testids from their factory options (`test-result`, `tool-test-output`, matching today's class names used by `test_tools_test_button_assets.py` and the editor tests; retarget the class-based assertions to testids).
- **The tests:** the ok result is stubbed with `page.route` (it cannot succeed under netns); refused and failed are real or stubbed.

## Inputs
- Legs 07a and 07b landed. 04b (`section` `info`, `codeBlock`), `disclosure` (Flight 3) and 03a (`latest()`) are available.

## Outputs
- The Test section rebuilt; the remaining `App.icon` and glyph code in `tools-editor.js` gone.
- `admin.css`: `.tools-editor-test-*`, `.test-tool-btn*`, `.tool-test-output`, `.test-tool-input*` and `.section-title-row*` removed.
- Tests: A15 and A16 (the headline per outcome, one mark, the disclosure collapsed by default, the head of the output, the input as a standard field on the button's line); `test_tools_test_button_assets.py` retargeted (string pins on the new code).
- Captures of `fetch_url` tested refused and ok, and of `web_search` tested; ledger rows 15 and 16 confirmed.

## Acceptance Criteria
1. **Each outcome** shows its fixed headline with one status mark (no glyph text), announced politely once.
2. **The output** is collapsed under "Technical details", opens by keyboard (the disclosure's contract), and shows the first 2 KB with a truncation marker when longer.
3. **The input** is a standard field (the label stacked, about 34 px tall), with the button on its line (bounding-box checks).
4. **A stale Test result** (the tool changed while the request was held) writes nothing.
5. `tools-editor.js` has no `App.icon`, no glyph strings and no hand-built info button.
6. The `admin.css` rules above are gone, and the unused-selector report shows no new dead rule.
7. The unit tier, the static guards, the asset tests and the `settings` lane pass. The captures show only ledger rows 15 and 16.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_tools_test_button_assets.py tests/test_ui_guards.py tests/test_ui_ownership.py -q -x --timeout 120`.
- The `settings` lane under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- The capture compare; `make test-unit` once.

## Edge Cases
- **An empty output** (a successful request with no body): no disclosure.
- **A very long single line** in the output: the code block scrolls horizontally within its region.

## Files Affected
- `static/js/areas/admin/tools-editor.js`, `static/css/admin.css`.
- `tests/browser/test_flow_admin_tools_editor.py`, `tests/test_tools_test_button_assets.py`.
- `docs/ui-control-inventory.md` (the consumers), `the_one/agents.md`, the flight log.

## Citation Audit
- `tools-editor.js:57` `_TESTABLE_TOOLS`, `:68-71` `TEST_FIXTURES`, `:159-195` the section, `:575-747` the handlers: from the survey. Re-locate them after 07a.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **This is now leg 07d.** 07a already moved the Test section to DOM; this leg redesigns its result.
- **The route gains an `outcome` field (FD call, additive).** `POST /api/tools/configs/{name}/test` returns only `{output, elapsed_ms}` with HTTP 200 for every tool-side result (`api.py` about `:713-790`). The only discriminator is the model-facing prefix (`[error] [constraint] …` for a policy refusal, from `tools/base.py` about `:25`; `[error] …` for a runtime failure, including the search backends' upstream failures).
  - The route adds `outcome: "ok" | "blocked" | "failed"`, computed **server-side** where the prefix is known, with unit tests (an ok result, a constraint refusal, a runtime error).
  - The client picks the headline from `outcome` and never parses `output`.
  - `agents.md` documents the field. Add `api.py` and a unit test to Files Affected.
- **HTTP errors:** 400 (an untestable tool), 404 and 500 (possibly non-JSON) all show "Request failed", with the detail or status text under Technical details, through `fetchJson` (03a handles non-JSON bodies).
- **HTML entities come from the tool** (`tools/_search_backends.py` about `:132`), not the route. They are **not** decoded, so the operator sees what the agent sees. Record it.
- **Truncation:** the head of the output, with "…" at the cut end. An `[error]`/failed result always has the details.
- **The Test's busy flag is per mount:** a Test in flight when the tool switches must not re-enable the new editor's Test button.
- **The Test uses the saved config.** While the form is dirty, show a one-line hint: "Tests the saved settings." (shown only when dirty), with a test.
- **The stubs:** the ok, blocked and failed results are stubbed with `page.route`, fulfilling `{output, elapsed_ms, outcome}` (real fetches can only fail under netns).
- **`test_tools_test_button_assets.py`'s string pins** are retargeted in the same commit.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

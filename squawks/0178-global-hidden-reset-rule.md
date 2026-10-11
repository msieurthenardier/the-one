# Squawk 0178: Add a global `[hidden] { display: none !important }` reset

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
An author `display` rule that defeats the `hidden` attribute has now needed a local fix four times: `#app-sidebar`, `#chat-drawer`, `.chat-chrome`, and `.date-time-page [hidden]` (M28 F2).

## Evidence
`static/css/base.css` (base layer). The fix: one reset rule in the base layer. Remove the page-local copies once the browser lanes stay green.

Logged from the Mission 28 flight debriefs.

## Corrective Action
Added `[hidden]:not([hidden="until-found"]) { display: none !important; }` to `static/css/base.css` (base layer; the layer order is `tokens, base, components, areas, utilities`). Cascade: `!important` reverses layer order, so an important declaration in the earliest layer beats every non-important author rule in every layer. No element uses `hidden="until-found"` today; the exclusion is future-proofing. Inline `style.display` is non-important, so it also loses to hidden, but the JS that sets `style.display` (chat attachments, design-language demos) does not use `hidden`.

Removed (pure `{ display: none; }` duplicates, 35 rules): base.css 2 (`#app-sidebar[hidden]`, `#chat-drawer[hidden]`); chat.css 10 (incl. `.chat-chrome`, `.chat-header`, drawer toggle/head, `.chat-new-state`, composer telemetry/stop, queued region, welcome); studio.css 14; admin.css 3 (incl. `.date-time-page [hidden]`); components.css 6 (`.ui-list-pane-*`, `.ui-menu`, search-list, `.tabpanel`, `.banner`, `.ui-drawer*`).
Kept: all `:not([hidden])` selectors (they style visible siblings, not visibility). Some explanatory comments near the removed rules still mention re-asserting `[hidden]`; they are now historical.

## Verification
Static guards (test_ui_guards, test_token_definitions, test_design_tokens_a11y): 270 passed. `make gate`: unit 5941 passed, 14 skipped. Browser PARALLEL_RESULT rc=1 total=1113s lanes=8 failed=shared.
Lanes: routing rc=0 503s; settings rc=0 488s; agents rc=0 504s; chats rc=0 433s (over budget); mcp rc=0 387s (over); library rc=0 316s (over); shared rc=1 244s; contracts rc=0 223s.
The only failure was known flake squawk 0168 (test_flow_jump_to.py::test_new_chat_opens_the_agent_picker); re-run in isolation: passed. Shared lane otherwise 248 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.

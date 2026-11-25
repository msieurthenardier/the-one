# Squawk 0408: The tools page's one-shot `keepFocus` stays set if a fill's navigation throws

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-24

## Report

Mission 36 Flight 5 (Leg 4b) added `App.admin.toolsPage.keepFocus`. The `tool_config` kind's
`beforeNavigate` sets it, so the editor's title does not take focus from the drawer composer
during a fill, and `afterNavigate` clears it. If anything between the two throws or returns early,
the flag stays `true`. Every later real navigation to a tool's editor then skips the title focus,
until a fill completes. The flag has no test. Found by the Flight 5 debrief (Developer).

## Evidence
- `static/js/areas/admin/tool-config-kinds.js:43-44`:
  `beforeNavigate: function () { App.admin.toolsPage.keepFocus = true; }` and the matching
  `afterNavigate`.
- `static/js/areas/admin/tools-page.js:20` `keepFocus: false`, and `:150-156`, where
  `revealItem` reads it.

## Corrective Action
Root cause: in the shared fill core's `open()` (`static/js/gleepglorp-drawer/fill.js`), the clear
ran from the `go()` promise's success handler and, in the same `.then(ok, err)` pair, its rejection
handler. A throw or rejection from `f.whenSettled(key)` (inside the success handler) is not caught
by the sibling rejection handler, and a synchronous throw from `App.router.go`/`routeFor` escaped
altogether. Either way `afterNavigate` never ran and the `tool_config` kind's one-shot
`App.admin.toolsPage.keepFocus` stayed `true`.

Fix: `open()` now builds the whole navigation (go, then the settle wait, with sync throws caught)
into one promise and clears the flag in a single terminal `then(success, failure)`, so
`afterNavigate` runs on every exit (Stay, settled, unsettled, throw, rejection). The success-path
results (`null`, `'stay'`, `'editor_unavailable'`) are unchanged, so the knowledge-base, agent and
other kinds that define `beforeNavigate`/`afterNavigate` behave as before. `beforeNavigate` itself
is called inside the guarded flow, so a throw from it also reaches `afterNavigate`.

Behaviour notes: a rejection from `whenSettled` now resolves to `'editor_unavailable'` where it used
to reject; and the success path clears the flag a few microtasks later than before (in the terminal
`then` rather than inside the `go()` handler), with the results unchanged. Files:
`the_one/interfaces/web/static/js/gleepglorp-drawer/fill.js`; test in
`tests/browser/test_flow_gleepglorp_fill_tool_config.py`.

## Verification
Test `test_a_fill_whose_navigation_throws_does_not_leave_the_next_open_without_title_focus`
(`gleepglorp-kinds` lane) makes the kind's `whenSettled` throw, checks the fill reports
`editor_unavailable` and `keepFocus` is `false`, then opens another tool's editor by route and
expects its title focused. Falsified: with the clear removed from the failure handler it fails
(`keepFocus` stayed `True`); restored, it passes. `run-tests.sh --lane gleepglorp-kinds` (netns):
102 passed. `tests/test_ui_guards.py`, `tests/test_token_definitions.py`,
`tests/test_design_tokens_a11y.py`: 396 passed.

Original criterion:
The flag is cleared on every exit of the fill's navigation (a `finally` in the caller, or the flag
passed as an argument rather than held as module state). A test fails a fill's navigation midway
and shows that the next ordinary open of a tool's editor focuses its title.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), batch review of squawks 0403, 0404, 0405, 0407, 0408, 0409 and 0410; Accessibility Reviewer (Sonnet) for 0407 and 0408
**Verdict**: confirmed after one fix round (`beforeNavigate` moved inside the guarded flow; the two behaviour notes recorded). Lanes after the fix: `gleepglorp-kinds` 102 passed, `gleepglorp-fill` 45 passed.
**Commit**: `squawk: turnaround 2026-11-24` on squawk/turnaround-2026-11-24

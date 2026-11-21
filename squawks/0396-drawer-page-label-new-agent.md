# Squawk 0396: The drawer's "Looking at" line reads "Agents › New" on the New Agent editor

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-21

## Report
On `#agents/~new`, the GleepGlorp drawer's "Looking at" line reads "Agents › New", while the editor's
title, and the page line the server builds for the same page, say "New Agent". The Windows and macOS
evidence in Mission 36 Flight 3 Leg 9 shows this after a create fill.

Reproduce: open Agents, click New, open the drawer, and read the line under its title. Align the
client's create label with the server's page names, so the operator sees the same words the model
does.

## Evidence
- `the_one/interfaces/web/static/js/router.js:572`, `if (p.create) item = 'New';` (the
  `describeCurrent` parts the drawer shows).
- `the_one/gleepglorp/page.py:61-62`, `CREATE_NAMES = {"agents": "New Agent", …}` (the stored page
  line, e.g. `Agents › New Agent`).

## Corrective Action
`js/gleepglorp-drawer/shell.js`: a `CREATE_NAMES` table (a client copy of
`the_one/gleepglorp/page.py::CREATE_NAMES`) and `contextParts`, which on a create route replaces
the router's last part ("New") with the create-editor name (agents, or the Library section). The
router's `describeRoute` is untouched, so the document title and spoken announcements still say
"New". The copy is pinned equal to the server table by
`tests/test_gleepglorp_drawer_create_names.py`. The existing drawer-shell test's two "› New" pins
now read "› New MCP server". The guide (`guide/drawer.md`) already quotes "New MCP server".

## Verification
A drawer browser test on `#agents/~new` asserts the "Looking at" text equals the page line's words.
Check the other create routes (`#library/mcp/~new` and others) the same way.

Ran:
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_gleepglorp_drawer_shell.py -m browser -x --timeout 120`: 25 passed (includes the new parametrized `test_the_looking_at_line_uses_the_create_editor_names` over all six create routes, and the updated `test_the_looking_at_line_follows_the_page`).
- `--lane shared` (owning lane, same env): 458 passed.
- `scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_gleepglorp_drawer_create_names.py tests/test_gleepglorp_guide.py -x --timeout 60`: 474 passed.
- Grep of `tests/`, `tests/behavior/` and the guide for "› New" drawer pins: none other found.
- Falsified: no (the new tests fail by construction against the old "New" label).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed; Accessibility Reviewer (Sonnet) confirmed, no WCAG 2.1 AA issues
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21

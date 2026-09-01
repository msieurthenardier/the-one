# Squawk 0029: Pin the promoted tool-result bubble's structural contract with a DOM-shape assertion

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: 2026-09-01

## Report

Flight 2's fix pass promotes peer-visible tool results (e.g. `[platform-send-ok]`) to top-level
bubbles in Chat: direct child of `.messages`, NOT nested in any `[data-testid="trace-shell"]`
accordion, followed by a `.msg-attribution.from-agent` row. That structural contract is currently
pinned only by one browser test plus the behavior test's structural dump — thin, given Flight 3 will
touch `chat.js` again for Discord rendering. Add a cheap DOM-shape browser assertion (the run-2
checkpoint-7 `evaluate_script` checks are the template: `isDirectChildOfMessages`,
`closest('[data-testid="trace-shell"]') === null`, sibling attribution row) so a regression doesn't
require a full behavior-test run to catch.

## Evidence

- `tests/behavior/stub-connector-round-trip/runs/2026-08-31-22-43-08.md` checkpoint 7 (the structural checks)
- Flight 2 debrief, Testing Assessment ("reasonable but thin")
- `the_one/interfaces/web/static/js/areas/chat.js` promotion logic (fix pass 2)

## Corrective Action

Extended the existing promotion browser test
`tests/browser/test_flow_chat_visibility_distinction.py::test_chat_promotes_delivered_tool_result_out_of_accordion`
with a new structural-contract block, added after its existing
attribution-row check, rather than a sibling test — it already seeds and
drives to the exact promoted-bubble state the checkpoint-7 template
checks target, so extending in place avoided duplicating the seed/page
setup for one extra `evaluate()` call.

The new block runs a single `evaluate()` against the already-located
`.messages > .msg.tool` locator and asserts the four checkpoint-7 (run-2,
`2026-08-31-22-43-08.md`) checks verbatim:

- `className === 'msg tool'` (exact match — no `msg-operator-only` or
  other modifier), traced to `message-bubble.js:34` (`fullCls = 'msg ' +
  cls`) and `chat.js:786` (`buildToolMsg` passes plain `'tool'` for a
  non-error result, and `isDeliveredToolResult` — `chat.js:801-803` —
  guarantees a delivered result never carries `visibility: 'operator'`,
  so `isOperatorOnly` never fires here).
- `isDirectChildOfMessages === true` (`el.parentElement.classList
  .contains('messages')`) — a stronger, explicit form of what the prior
  `.messages > .msg.tool` CSS-selector count already implied.
- `el.closest('[data-testid="trace-shell"]') === null` — the
  non-nesting claim the behavior test's Validator re-derived
  independently from the raw a11y tree; now pinned mechanically.
- `nextElementSibling.className === 'msg-attribution from-agent'`
  (exact match), traced to `message-bubble.js:123`
  (`renderAttribution`'s `'msg-attribution ' + side`) and `chat.js:815`
  (`appendDeliveredToolMsg` calls it with `'from-agent'`) — tightened
  from the prior `"from-agent" in cls` substring check to the exact
  string the checkpoint-7 template pins.

No `chat.js` (or any other source) changes were needed — running the new
assertions against current code passed cleanly on the first attempt, so
this squawk stayed entirely within its test-only scope gate.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_chat_visibility_distinction.py -x --timeout 60`
  → **2 passed** in 3.90s (both tests in the file, including the
  extended promotion test with the new structural assertions). Note:
  the repo's default pytest `addopts` excludes `browser`-marked tests
  (`-m 'not live and not browser and not pixel and not requires_bwrap'`
  in `pyproject.toml:122`), so `-m browser` must be passed explicitly —
  without it, the run reports "2 deselected" rather than exercising
  anything.
- `.venv/bin/ruff check tests/browser/test_flow_chat_visibility_distinction.py`
  → clean. `.venv/bin/ruff format --diff` on the same file shows exactly
  one pre-existing formatting nit at line ~330, entirely outside this
  squawk's added block (confirmed via `git diff` — the diff starts at
  line 347, after that nit) — left untouched as out of scope.
- `git diff --stat` confirms only this squawk file and the test file
  were touched by this squawk's work; `the_one/interfaces/web/static/js/areas/chat.js`
  and every other source file are untouched — squawks 0025-0028's
  pre-existing uncommitted changes on this branch were left alone per
  instructions.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-01
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-01 batch commit (PR follows)

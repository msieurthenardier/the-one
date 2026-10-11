# Squawk 0168: jump-to "New chat" browser test is flaky under parallel load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: 2026-10-11

## Report
`tests/browser/test_flow_jump_to.py::test_new_chat_opens_the_agent_picker`
failed once in the `shared` lane in two of Mission 27's four parallel gates
(Flight 1 re-run; Flight 3 HAT gate). The whole file passes 24/24 three times
in isolation. It appears to be a timing race under host load, not a
regression; it never failed on its own.

## Evidence
- Flight 3 HAT gate: `PARALLEL_RESULT rc=1 … failed=shared`, the only
  failure. Re-runs of `test_flow_jump_to.py` in isolation: 24 passed, ×3.
- Mission 27 Flight 1 flight log, "Gate run 2": the same test, 3/3 in
  isolation.
- Mission 28 Flight 1 leg 2b (2026-10-10): failed twice in the parallel
  `make gate` (`shared` lane). Expected route `chats`, got `chats/<id>`: the
  chat auto-joined the latest session after the picker opened. It passed
  3/3 alone and 24/24 for the whole file. The symptom matches squawk 0169's
  auto-join override, which is a likely shared root cause.

## Investigation (developer, 2026-10-11)
Squawk 0169 turned out NOT to be the idle auto-join but the AC9 rail-restore rule (see 0169), so it is not a confirmed shared root cause. The jump-to flake (route `chats/<id>` instead of `chats`, after the picker opens, `_boot(page, base, "agents")` then Jump to "New chat") has no pending `~new` route in play and so is plausibly the idle auto-join racing `openPicker` on a cold chat-area init. Not reproduced or fixed; deferred pending 0169's design decision and a dedicated look at `openPicker`'s queue vs the first `session_list`.

## Corrective Action
Root cause was NOT the idle auto-join and no product change was made. Reproduced the failure about 50% of the time in isolation (alternating runs). Instrumentation showed `openPicker` never ran in the failing runs; instead the palette's Enter landed on a CHAT row. The world fixture seeds a chat whose title is the server default, "New chat", which matches the query "new chat". Jump to loads its chat candidates cold (`jump-to.js` `open()` force-fetches `sessions` after the palette is shown; `refresh()` moves the active row to the new first row unless the user had moved off it). When the fetch lands after `_jump`'s arrow-key selection of the "New chat..." action, the chat row is inserted above it and becomes active, and Enter joins that chat, giving route `chats/<id>`. Fix (test only): `_jump` in `tests/browser/test_flow_jump_to.py` now waits for `App.store.peek('sessions').loaded` after opening the palette and before typing the query. The idle auto-join suppression idea was tried and reverted: it did not change the failure rate, and spec-wise cold-entry auto-join is intended.

## Verification
`test_new_chat_opens_the_agent_picker` alone: before the fix about 50% failed (many of 12+ runs); after the fix 14/14 passed. Whole `test_flow_jump_to.py`: 24 passed; `--lane routing`: 182 passed; `--lane shared`: 249 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.

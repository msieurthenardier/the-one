# Squawk 0360: a comment in app.py still names the "Tool activity" accordion

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: 2026-11-14

## Report
A comment in `the_one/interfaces/web/app.py` describes where the chat puts a tool result with the old name. Since sortie 16 a tool result goes into the turn's work group (`App.ui.turnWork`); there is no "Tool activity" accordion any more. The comment is the only place left in the product code that names it. No behaviour is affected.

## Evidence
- `the_one/interfaces/web/app.py::_build_session_joined_ok`, the comment above `"platform": session.platform` — "…needed to gate promoting a delivered tool result to a top-level bubble instead of collapsing it into the "Tool activity" accordion."
- Sortie 16 left it alone on purpose: its charter is browser-only and it changed no Python (`sorties/16-turn-work-group/flight-log.md`, Flight Director Notes, "Left out of scope on purpose").

## Corrective Action
Confirmed still present on this branch (`grep -n "Tool activity" the_one/` found only that comment and a retired-control note in `agents.md`). Reworded the comment in `the_one/interfaces/web/app.py` (`_build_session_joined_ok`): a delivered tool result is promoted to a top-level bubble "instead of folding it into the turn's work group". Comment only.

## Verification
`ruff check` and `ruff format --check` on `app.py` pass. `grep -n "Tool activity" the_one/interfaces/web/app.py` returns nothing.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`

## Disposition
**Deferred**: comment-only, and in Python, outside sortie 16's browser-only charter — revisit at the next squawk turnaround after sortie 16 merges.
Completed in the 2026-11-14 turnaround.

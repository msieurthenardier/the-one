# Squawk 0383: The unit tier sits at its 300-second target

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: 2026-11-18

## Report
Sortie 19's closing gate measured the unit tier at 299.4 s on a quiet host (start load 0.82), against the standing target of 300 s in `CLAUDE.md`. Sortie 19 added about 27 s of real time: tests that spawn the stdio fixture and wait through a shortened window. The next flight that adds a unit test crosses the target.

Needed, one of:
- Trim the real-time tests. The two tests with a 6.5 s start delay (`test_stdio_slow_legacy_server_past_the_window_records_the_fallback` and the route test `test_stdio_test_stores_the_no_answer_fallback_and_a_prompt_test_removes_it`) can prove the same wiring with a smaller window and a smaller delay; the silent-drop and count-reset tests each pay about 2 s of window per connect and could share spawns. The policy itself is already covered by scripted tests with an injected clock. Keep one real slow-start test.
- Or move the target, to about 345 s (measured plus 15%, as the full-gate target was set), and say so in `CLAUDE.md`.

Trimming first is preferred; whatever is done, the slack each real-fixture test leaves for the fixture's start-up must stay at 4 s or more (sortie 19's review fix).

## Evidence
- `sorties/19-local-mcp-servers-newest-protocol/flight-log.md`, "closing gate, on the final tree" — 10263 passed, 15 skipped, 299.4 s; "Review fixes" under `patient-discover` — the table of window, delay, limit and slack per real-fixture test.
- `CLAUDE.md`, "Full-gate target" — "the unit tier alone keeps its 300 s standing target".
- Earlier readings: 283.0 s (sortie 17 debrief), 271 s (sortie 16 debrief, alone).

## Corrective Action
M36 F1 L01. Trimmed the real-fixture MCP stdio tests, keeping assertions: the slow-legacy client test and the route test now use a 2.5 s window, 3 s start delay and 7 s limit (4 s slack); the silent-drop and count-reset tests use a 1.5 s window of a 7 s limit (5.5 s slack). The slow dual-era test is unchanged. Trimming alone could not reach the 285 s room goal, so the unit-tier target moved to 350 s (measured plus about 15%) in `CLAUDE.md` "Full-gate target".

## Verification
- The two test files, three runs: 32 passed each, 26.9 / 26.6 / 26.5 s. The five tests fell from about 40 s to about 19 s.
- Quiet-host unit tier (start load 0.81, `THE_ONE_TEST_NETNS=1 make test-unit`): 10264 passed, 15 skipped, 303.74 s. No other test is over 7 s, so no further cheap trim exists.
- Status stays `in-progress`; Sign-Off waits for the flight's review and commit.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), Mission 36 Flight 1 Batch A review
**Verdict**: confirmed (target move to 350 s accepted by the operator, 2026-11-18)
**Commit**: the Mission 36 Flight 1 Batch A checkpoint commit on `flight/01-gleepglorp-exists-and-answers`

# Squawk 0383: The unit tier sits at its 300-second target

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

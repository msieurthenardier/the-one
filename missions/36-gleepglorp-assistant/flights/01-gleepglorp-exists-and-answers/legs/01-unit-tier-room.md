# Leg: unit-tier-room

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Complete squawk 0383: bring the unit tier back under its 300 s target with room
for this flight's new tests, by trimming the real-time MCP stdio tests sortie 19
added, and move the target only if trimming falls short.

## Context
- Squawk 0383 (`squawks/0383-unit-tier-at-its-time-target.md`): sortie 19's
  closing gate measured the unit tier at 299.4 s against the 300 s target
  (CLAUDE.md "Full-gate target"). Sortie 19 added about 27 s of real time in
  tests that spawn the stdio fixture and wait through a shortened window.
- The policy itself is already covered by scripted tests with an injected clock
  (`tests/test_mcp_negotiate.py`, `tests/test_mcp_era.py`); the real-fixture
  tests prove the wiring end to end. Keep one real slow-start test.
- Sortie 19's review fix: every real-fixture test keeps 4 s or more of slack for
  the fixture's start-up plus the handshake (`sorties/19-local-mcp-servers-newest-protocol/flight-log.md`,
  "Review fixes" table).
- Flight 1 adds many unit tests (Legs 2-5); this leg makes room first.

## Inputs
- `main` at `9fea53cd` on branch `flight/01-gleepglorp-exists-and-answers`.
- The real-fixture tests:
  - `tests/test_mcp_negotiation_fallback.py::test_stdio_slow_legacy_server_past_the_window_records_the_fallback` (window 6 s, delay 6.5 s, limit 14)
  - `tests/test_mcp_stdio_test_connect.py::test_stdio_test_stores_the_no_answer_fallback_and_a_prompt_test_removes_it` (route; window 6 s, delay 6.5 s, limit 14)
  - `tests/test_mcp_negotiation_fallback.py::test_stdio_silent_drop_waits_the_window_is_asked_again_then_remembered` (window 2 s, limit 7)
  - `tests/test_mcp_negotiation_fallback.py::test_stdio_a_modern_connect_in_between_resets_the_no_answer_count` (window 2 s, limit 7)
  - `test_stdio_slow_dual_era_server_ends_modern_...` (window 5 s, delay 1 s, limit 8)

## Outputs
- The listed tests run faster: the two 6.5 s-delay tests prove the same wiring
  with a smaller window and delay; the silent-drop and count-reset tests share
  spawns where they can. One real slow-start test remains.
- A quiet-host unit-tier reading recorded in the flight log and the squawk.
- Squawk 0383 completed (Corrective Action, Verification, Sign-Off pending the
  flight's review and commit).

## Acceptance Criteria
- [ ] Each trimmed test still asserts the same behaviour it asserted before (the
      fallback recorded, the route storing then removing it, the silent drop
      asked again then remembered, the count reset by a modern connect).
- [ ] Every real-fixture test keeps at least 4 s of slack between the end of its
      window or delay and its limit.
- [ ] At least one real slow-start test (a fixture that starts after the window)
      remains.
- [ ] The trimmed tests pass three times in a row (`-p no:randomly` not needed;
      plain repeated runs).
- [ ] The unit tier (`THE_ONE_TEST_NETNS=1 make test-unit`) on a quiet host
      (1-minute load below about 1.0, no other test process, checked with
      `uptime` and `ps`) reads at or below 285 s, giving at least 15 s of room.
      If trimming cannot reach 285 s, the target moves to measured plus 15%
      with the reason recorded in CLAUDE.md "Full-gate target" and the squawk,
      and the Flight Director is told before landing.
- [ ] Squawk 0383's Corrective Action and Verification sections are written
      (Sign-Off waits for the flight's review); its status stays `in-progress`.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_negotiation_fallback.py tests/test_mcp_stdio_test_connect.py -x --timeout 60`, three times, reporting each wall time.
- `uptime; ps -eo pid,etime,cmd | grep -E "pytest|uvicorn" | grep -v grep` before
  the tier run, then `THE_ONE_TEST_NETNS=1 make test-unit` and report the
  pytest-reported duration, passed and skipped counts (expected skips per
  CLAUDE.md "Expected unit skip count").

## Implementation Guidance
1. Read the five tests and the fixture (`tests/fixtures/` stdio MCP fixture with
   its start-delay and drop options) and the policy constants they patch
   (`HANDSHAKE_RESERVE_SECONDS`, the connect limit).
2. For the two 6.5 s tests: shrink window and delay together (for example
   window 2.5 s, delay 3 s) and the limit so slack stays at least 4 s.
   Keep the one with the clearest end-to-end value (the client test) as the
   real slow-start test if a further cut means turning the route test into a
   scripted one; record which you chose.
3. For the silent-drop and count-reset tests: share one fixture spawn per test
   where the test's own sequence allows, or reduce their window if their
   assertions do not depend on its length.
4. Run the verification commands. If the tier is still above 285 s on a quiet
   host, find the next slowest unit tests (`--durations=25`) and report them to
   the Flight Director before moving the target.
5. Write the squawk's Corrective Action and Verification; set its status to
   `in-progress` (completed at the flight commit).

## Edge Cases
- **Loaded host**: a reading on a loaded host does not count; wait for a quiet
  host or report the load with the reading.
- **Flaky slack**: if a trimmed test fails once in three runs, its slack is too
  thin; widen the limit (not the window) and re-run.

## Files Affected
- `tests/test_mcp_negotiation_fallback.py` - trimmed timings, shared spawns
- `tests/test_mcp_stdio_test_connect.py` - trimmed timings
- `squawks/0383-unit-tier-at-its-time-target.md` - corrective action, verification
- `CLAUDE.md` - only if the target moves

## Citation Audit
- `tests/test_mcp_negotiation_fallback.py:193`, `:245`, `:266` - the silent-drop,
  slow-legacy and count-reset tests exist at these lines - verified at `9fea53cd`
- `tests/test_mcp_stdio_test_connect.py:521` - the route test exists - verified
- Window/delay/limit values - from sortie 19's flight log "Review fixes" table -
  verified (table read); the Developer re-reads the tests' own constants.

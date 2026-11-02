# Squawk 0307: nothing stops a test HTTP server from using the default 0.5 s poll again

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
`http.server`'s `serve_forever()` polls every 0.5 s by default, so each `shutdown()` waits about 0.35 s. Mission 34 Flight 1 found this was the largest single cost in the unit tier's evals tests (66.9 s → 19.0 s once fixed) and in `test_cli_quit` (8.2 s → 0.9 s). Every test-owned server now passes `poll_interval=0.02`, but nothing stops a new one from using the default, and the rule is not written down. Add a cheap text guard that fails on a bare `serve_forever()` in `tests/` and `evals/`, and document the rule in `the_one/agents.md` beside "The shared API app".

## Evidence
- Current call sites, all with the short interval: `evals/fixtures.py:49` — `functools.partial(self._server.serve_forever, poll_interval=0.02)`; `tests/fixtures/oauth/__init__.py:274`; `tests/test_cli_quit.py:49`.
- `grep -rn 'serve_forever()' tests/ evals/` finds no default-interval call at `52f4c457`.
- Flight debrief: `missions/34-maintenance/flights/01-test-suite-runtime-ii/flight-debrief.md`, Recommendation 4.

## Corrective Action
*(written at completion)*

## Verification
- The guard fails when a bare `serve_forever()` is added to a test file (falsified by editing, then removed by editing) and passes on the tree; it reads text only and costs well under 0.5 s.
- agents.md states the rule; `make test-unit` passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

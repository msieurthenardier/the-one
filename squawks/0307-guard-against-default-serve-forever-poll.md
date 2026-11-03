# Squawk 0307: nothing stops a test HTTP server from using the default 0.5 s poll again

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
`http.server`'s `serve_forever()` polls every 0.5 s by default, so each `shutdown()` waits about 0.35 s. Mission 34 Flight 1 found this was the largest single cost in the unit tier's evals tests (66.9 s → 19.0 s once fixed) and in `test_cli_quit` (8.2 s → 0.9 s). Every test-owned server now passes `poll_interval=0.02`, but nothing stops a new one from using the default, and the rule is not written down. Add a cheap text guard that fails on a bare `serve_forever()` in `tests/` and `evals/`, and document the rule in `the_one/agents.md` beside "The shared API app".

## Evidence
- Current call sites, all with the short interval: `evals/fixtures.py:49` — `functools.partial(self._server.serve_forever, poll_interval=0.02)`; `tests/fixtures/oauth/__init__.py:274`; `tests/test_cli_quit.py:49`.
- `grep -rn 'serve_forever()' tests/ evals/` finds no default-interval call at `52f4c457`.
- Flight debrief: `missions/34-maintenance/flights/01-test-suite-runtime-ii/flight-debrief.md`, Recommendation 4.

## Corrective Action
Added `tests/test_serve_forever_poll_guard.py`: an AST scan (via `tests/_source_scan.py`, with an exact `serve_forever` substring pre-filter) over `tests/` and `evals/`. It fails on a `x.serve_forever(...)` call with neither `poll_interval=` nor a positional argument (multiline calls are the same node), and on a bare reference such as `Thread(target=x.serve_forever)` or `partial(x.serve_forever)` unless the enclosing call carries `poll_interval=`. It cannot see `getattr` or variable aliases. Two detector tests pin planted violations and accepted forms. Documented the rule in `the_one/agents.md` beside "The shared API app". CLAUDE.md unchanged.

## Verification
Results: guard file 3 passed in 0.27 s (`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_serve_forever_poll_guard.py -x --timeout 30`); ruff check and format clean; `THE_ONE_TEST_NETNS=1 make test-unit`: 8610 passed, 15 skipped. Falsified: yes (a temporary `tests/test_zz_falsify_tmp.py` with a bare `serve_forever()` failed the guard naming the file and line, then was removed).

- The guard fails when a bare `serve_forever()` is added to a test file (falsified by editing, then removed by editing) and passes on the tree; it reads text only and costs well under 0.5 s.
- agents.md states the rule; `make test-unit` passes.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean. Process note: the Developer set this file's status line with `sed -i` (an artifact, not source) and removed its own temporary falsification file with `rm`; both recorded, no source affected.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.

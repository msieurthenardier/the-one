# Squawk 0308: every `the_one` log line is written twice under `the-one serve`

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
Under `the-one serve`, each `the_one.*` record reaches the log twice: once in the format `the_one/logging_config.py::configure_logging` installs (`%(asctime)s %(levelname)s %(name)s: %(message)s`), and once as a rich-console line (`[11/02/26 13:16:10] INFO     purge sweep deleted=0 runs_deleted=0    app.py:1520`), wrapped and sometimes truncated. `configure_logging`'s docstring says no root handler double-emits `the_one` records, so some root (rich) handler is installed that the code does not expect. Grep-based reading of the log (operators, the `routine-run-observable-from-logs` behavior test) has to filter one format out. Find what installs the root handler and stop the double emission, keeping `caplog` working (it relies on propagation).

## Evidence
- `tests/behavior/routine-run-observable-from-logs/runs/2026-11-02-18-55-16.md` and `2026-11-02-19-15-26.md` (Executor notes): every routine and purge line appears twice; e.g. serve.log lines 8 and 9, `purge sweep …` then `[…] INFO purge sweep deleted=0 runs_deleted=0 app.py:1520`.
- `the_one/logging_config.py::configure_logging` — "uvicorn installs handlers only on the ``uvicorn*`` loggers, not root, so no standing root handler double-emits the_one records".
- Mission 34 Flight 2 debrief, Action Items.

## Corrective Action
*(written at completion)*

## Verification
- A `the-one serve` instance on a scratch port and data dir writes each `the_one` record once (grep one routine or purge line, count 1).
- `caplog`-based tests still see `the_one.*` records (`make test-unit` passes); the behavior spec's "logger-format lines only" note can then be dropped.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

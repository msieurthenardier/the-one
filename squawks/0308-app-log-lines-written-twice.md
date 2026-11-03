# Squawk 0308: every `the_one` log line is written twice under `the-one serve`

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
Under `the-one serve`, each `the_one.*` record reaches the log twice: once in the format `the_one/logging_config.py::configure_logging` installs (`%(asctime)s %(levelname)s %(name)s: %(message)s`), and once as a rich-console line (`[11/02/26 13:16:10] INFO     purge sweep deleted=0 runs_deleted=0    app.py:1520`), wrapped and sometimes truncated. `configure_logging`'s docstring says no root handler double-emits `the_one` records, so some root (rich) handler is installed that the code does not expect. Grep-based reading of the log (operators, the `routine-run-observable-from-logs` behavior test) has to filter one format out. Find what installs the root handler and stop the double emission, keeping `caplog` working (it relies on propagation).

## Evidence
- `tests/behavior/routine-run-observable-from-logs/runs/2026-11-02-18-55-16.md` and `2026-11-02-19-15-26.md` (Executor notes): every routine and purge line appears twice; e.g. serve.log lines 8 and 9, `purge sweep …` then `[…] INFO purge sweep deleted=0 runs_deleted=0 app.py:1520`.
- `the_one/logging_config.py::configure_logging` — "uvicorn installs handlers only on the ``uvicorn*`` loggers, not root, so no standing root handler double-emits the_one records".
- Mission 34 Flight 2 debrief, Action Items.

## Corrective Action
Root cause: `the_one/self_configuration/surface.py` builds a module-level `mcp.server.mcpserver.MCPServer` at import; its constructor calls the SDK's `configure_logging`, which runs `logging.basicConfig(handlers=[RichHandler(Console(stderr=True))])`, leaving a standing rich handler on the root logger that re-prints every propagated `the_one.*` record. Fix (`the_one/logging_config.py`): `configure_logging` now adds a filter (`_drop_the_one_records`) to every root `RichHandler`, so it no longer prints `the_one` records but still prints other libraries' (the MCP SDK's own lines are kept). Propagation stays True, so `caplog` is unaffected; `propagate=False` was rejected because it breaks caplog, and removing the rich handler would drop the SDK's console output. The docstring is corrected to state this. New test `tests/test_logging_config.py::test_a_the_one_record_is_written_once_with_a_root_rich_handler`; the behavior spec's "logger-format lines only" note was updated.

## Verification
- Live (port 8494, scratch data dir, owner confirmed via `/proc/<pid>/environ`): `grep -c "purge sweep" serve.log` was 2 before the fix and 1 after.
- Unit test falsified (fix call removed by editing: test failed; restored: passes). ruff check/format clean.
- A `the-one serve` instance on a scratch port and data dir writes each `the_one` record once (grep one routine or purge line, count 1).
- `caplog`-based tests still see `the_one.*` records (`make test-unit` passes); the behavior spec's "logger-format lines only" note can then be dropped.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean. Process note: the Developer appended the new test to `tests/test_logging_config.py` with a shell heredoc (squawk 0286); the Flight Director read the appended test, and the Reviewer reviewed and re-ran it. Squawk 0292 (the shell-write hook, operator-approved) would block this.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.

# Squawk 0425: The per-worker pytest data directories are never removed

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: 2026-11-25

## Report

Since Mission 37 Flight 1 (xdist), `tests/conftest.py` creates a fresh `mkdtemp` data directory in each xdist worker, as well as the controller's own. None of them is ever removed, so every `make test-unit` run leaves about five `the-one-pytest-*` directories in the system temp directory. Before this flight a run left one, and that one also leaked. Found by the Mission 37 Flight 1 debrief (Architect).

## Evidence
- `tests/conftest.py:47`: `os.environ["THE_ONE_DATA_DIR"] = tempfile.mkdtemp(prefix="the-one-pytest-")`, the controller or a serial run.
- `tests/conftest.py:50`: `tempfile.mkdtemp(prefix=f"the-one-pytest-{_worker}-")`, one per worker.
- There is no `atexit` or session-finish cleanup for these paths. Compare `tests/_schema_template.py`, which registers `atexit` for its own `mkdtemp`.

## Corrective Action
`tests/conftest.py` records the directory it minted in `_minted_data_dir` (controller or serial run, or a worker's replacement) and registers `atexit.register(shutil.rmtree, _minted_data_dir, ignore_errors=True)`. `atexit` runs after every test and teardown. Each process removes only its own directory: a worker never removes the controller's inherited directory, the controller never removes a worker's, and an explicit `THE_ONE_DATA_DIR` override (no marker, nothing minted) is never removed. No change to test isolation design.

## Verification
Done (reduced): `ls -d /tmp/the-one-pytest-* | wc -l` read 3177 (old leaks, left in place) before and after a `-n 2` run of `tests/test_xdist_data_dir_isolation.py` (controller plus 2 workers; each would previously have leaked one) and after a serial run: unchanged, test passes both ways. The full `make test-unit` (N=4) run was NOT done: a browser lane (`run-tests.sh --lane chats`, worktree `the-one-sortie-20`) was running on the host at load about 4, and the unit suite must not run beside browser lanes. Still owed: one full tier run on a quiet host. `ruff check` and `ruff format --check` on `tests/conftest.py` clean.

Criterion: after one `make test-unit` run (N=4), no new `the-one-pytest-*` directory remains in the temp directory. The sentinel test `tests/test_xdist_data_dir_isolation.py` still passes. An explicit `THE_ONE_DATA_DIR` override is never removed.

**Flight Director's tier run.** `THE_ONE_TEST_NETNS=1 make test-unit` (N=4) gave 12356 passed and 15 skipped in 257 s. The start load was 1.23 with no other test process; the end load was 7.9. The `/tmp/the-one-pytest-*` count did not grow.

**Leftover clean-up** (operator decision, 2026-11-25). There were 3195 directories before. The 2705 older than one day were deleted with `find /tmp -maxdepth 1 -name 'the-one-pytest-*' -type d -mtime +1`, leaving 490 newer ones. The newer ones were kept, because a running test may be using them.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0422 and 0424-0427
**Verdict**: confirmed. Only a directory this module minted is removed, and each process removes its own. An explicit override is never removed. `atexit` runs after teardown. Browser server subprocesses cannot remove a directory they did not mint.
**Commit**: `squawk: turnaround 2026-11-25-2` on squawk/turnaround-2026-11-25-2

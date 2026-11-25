# Squawk 0425: The per-worker pytest data directories are never removed

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

Since Mission 37 Flight 1 (xdist), `tests/conftest.py` creates a fresh `mkdtemp` data directory in each xdist worker, as well as the controller's own. None of them is ever removed, so every `make test-unit` run leaves about five `the-one-pytest-*` directories in the system temp directory. Before this flight a run left one, and that one also leaked. Found by the Mission 37 Flight 1 debrief (Architect).

## Evidence
- `tests/conftest.py:47`: `os.environ["THE_ONE_DATA_DIR"] = tempfile.mkdtemp(prefix="the-one-pytest-")`, the controller or a serial run.
- `tests/conftest.py:50`: `tempfile.mkdtemp(prefix=f"the-one-pytest-{_worker}-")`, one per worker.
- There is no `atexit` or session-finish cleanup for these paths. Compare `tests/_schema_template.py`, which registers `atexit` for its own `mkdtemp`.

## Corrective Action
*(written at completion)*

## Verification
After one `make test-unit` run (N=4), no new `the-one-pytest-*` directory remains in the temp directory. The sentinel test `tests/test_xdist_data_dir_isolation.py` still passes. An explicit `THE_ONE_DATA_DIR` override is never removed.

## Sign-Off
*(written at completion)*

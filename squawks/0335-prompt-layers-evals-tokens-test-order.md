# Squawk 0335: test-order dependence between `test_prompt_layers.py` and `test_evals_tokens.py`

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-07
**Completed**: —

## Report
If `tests/test_prompt_layers.py` and then `tests/test_evals_tokens.py` run in one pytest process, the second file fails with `no active connection` in the eval knowledge-base seed. Each file passes on its own, and the full `make test-unit` run passes because of how it orders the files. Any reordering, or a `-k` selection that pairs them, turns it into a spurious failure.

Repro: `.venv/bin/python -m pytest tests/test_prompt_layers.py tests/test_evals_tokens.py -x -q --timeout 120`.

## Evidence
- Found in sortie 11 leg 3 Part A. It reproduces at `HEAD` before that sortie, in a detached worktree, so the sortie did not cause it (`sorties/11-tool-exposure-for-small-models/flight-log.md`, Anomalies).
- Likely mechanism: `the_one.vectors` binds `get_connection` at import, and a test that patches `get_connection` leaves the vectors module bound to a closed or patched connection (recorded in `the_one/agents.md`). Not yet confirmed: the first step of the fix is to read which fixture in `test_prompt_layers.py` leaves the state behind.

## Corrective Action
*(written at completion)*

## Verification
The repro command above passes, and so does the reverse order. `make test-unit` stays green.

# Squawk 0335: test-order dependence between `test_prompt_layers.py` and `test_evals_tokens.py`

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-07
**Completed**: 2026-11-14

## Report
If `tests/test_prompt_layers.py` and then `tests/test_evals_tokens.py` run in one pytest process, the second file fails with `no active connection` in the eval knowledge-base seed. Each file passes on its own, and the full `make test-unit` run passes because of how it orders the files. Any reordering, or a `-k` selection that pairs them, turns it into a spurious failure.

Repro: `.venv/bin/python -m pytest tests/test_prompt_layers.py tests/test_evals_tokens.py -x -q --timeout 120`.

## Evidence
- Found in sortie 11 leg 3 Part A. It reproduces at `HEAD` before that sortie, in a detached worktree, so the sortie did not cause it (`sorties/11-tool-exposure-for-small-models/flight-log.md`, Anomalies).
- Likely mechanism: `the_one.vectors` binds `get_connection` at import, and a test that patches `get_connection` leaves the vectors module bound to a closed or patched connection (recorded in `the_one/agents.md`). Not yet confirmed: the first step of the fix is to read which fixture in `test_prompt_layers.py` leaves the state behind.

## Corrective Action
No change made: already fixed. Squawk 0346 (commit `0ce374f0`) added `import the_one.knowledge.manager` and `import the_one.vectors` ahead of the `get_connection` patch in the `factory` fixture of `tests/test_prompt_layers.py`, so the vectors module binds the real function first. That is the mechanism this squawk guessed at.

## Verification
The repro command and the reverse order each passed (85 passed, 4 runs), and `tests/test_prompt_layers.py` with all `tests/test_evals_*.py` passed (600). Falsified: removing the two pre-imports by editing makes `tests/test_evals_tokens.py::test_three_configurations_parts_sum_and_attribution` fail in the repro order; the imports were then put back (no diff against HEAD in that file). Original acceptance:
The repro command above passes, and so does the reverse order. `make test-unit` stays green.

No code change was made in this turnaround: the defect was already fixed by squawk 0346. That was proven by removing 0346's fix, seeing the failure, and restoring it.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`

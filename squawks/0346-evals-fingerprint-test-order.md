# Squawk 0346: test_evals_fingerprint fails after test_prompt_layers in the same process

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-11
**Completed**: 2026-11-13

## Report
`tests/test_evals_fingerprint.py::test_measured_prompt_fingerprint_is_stable_and_follows_tool_text[none]` fails with "measuring all-on: ValueError: no active connection" when `tests/test_prompt_layers.py` runs before it in the same pytest process. It passes alone and in the default order, so cross-test connection state leaks (a test closes or swaps the module-level connection the measurement uses).

## Evidence
- `tests/test_evals_fingerprint.py:90` `test_measured_prompt_fingerprint_is_stable_and_follows_tool_text`.
- Reproduced by the Mission 35 Flight 2 leg 7 A2''' Developer: `pytest tests/test_prompt_layers.py tests/test_evals_*.py` (failure) vs `pytest tests/test_platform_prompt.py tests/test_evals_*.py` (568 passed). Not reproduced in the default `make test-unit` order (debrief run: 9769 passed).

## Corrective Action
Root cause: the `factory` fixture in `tests/test_prompt_layers.py` patches `the_one.db.connection.get_connection` with an AsyncMock returning that test's connection. `AgentFactory.create` lazily first-imports `the_one.vectors` (and `the_one.knowledge.manager`), which do `from the_one.db.connection import get_connection`; when that first import happened inside the patch, the mock (and the test's later-closed connection) was bound permanently into `the_one.vectors.get_connection`. The next test to call `get_vector_store` (the evals fingerprint measurement) got "no active connection". Fix (test only): the fixture now imports `the_one.vectors` and `the_one.knowledge.manager` before applying the patch, with a comment. No production change.

## Verification
Reproduced first with `tests/test_prompt_layers.py tests/test_evals_fingerprint.py -x` (failed). After the fix, all pass: that pair (57 passed); `tests/test_prompt_layers.py` plus all `tests/test_evals_*.py` (600 passed); `tests/test_evals_*.py` then `tests/test_prompt_layers.py` (600 passed); `tests/test_prompt_layers.py` alone (51 passed). `ruff check` and `ruff format --check` clean on the file. `make test-unit` left to the batch Reviewer.

## Sign-Off
**Reviewer**: batch Reviewer (Haiku), independent of the implementers. It found the fix is test-only and matches the stated root cause (the module-level import captured the patched `get_connection`). `make test-unit` (netns) 10124 passed, 15 skipped.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13`

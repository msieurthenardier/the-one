# Squawk 0346: test_evals_fingerprint fails after test_prompt_layers in the same process

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-11
**Completed**: —

## Report
`tests/test_evals_fingerprint.py::test_measured_prompt_fingerprint_is_stable_and_follows_tool_text[none]` fails with "measuring all-on: ValueError: no active connection" when `tests/test_prompt_layers.py` runs before it in the same pytest process. It passes alone and in the default order, so cross-test connection state leaks (a test closes or swaps the module-level connection the measurement uses).

## Evidence
- `tests/test_evals_fingerprint.py:90` `test_measured_prompt_fingerprint_is_stable_and_follows_tool_text`.
- Reproduced by the Mission 35 Flight 2 leg 7 A2''' Developer: `pytest tests/test_prompt_layers.py tests/test_evals_*.py` (failure) vs `pytest tests/test_platform_prompt.py tests/test_evals_*.py` (568 passed). Not reproduced in the default `make test-unit` order (debrief run: 9769 passed).

## Corrective Action
*(written at completion)*

## Verification
`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_prompt_layers.py tests/test_evals_fingerprint.py -x` passes, and `make test-unit` still passes.

## Sign-Off
*(written at completion)*

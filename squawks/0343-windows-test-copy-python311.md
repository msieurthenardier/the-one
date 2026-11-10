# Squawk 0343: windows_test_copy.py builds its venv with Python 3.11; the project needs 3.12

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-09
**Completed**: —

## Report
`scripts/windows_test_copy.py setup` builds the Windows test-copy venv from a hard-coded Python 3.11. The project requires 3.12, so the install fails: the `numpy==2.5.3` closure has no 3.11 build. Mission 35 Flight 2 leg 1 Part B worked around it by hand. The Developer rebuilt the scratch venv with `C:\Python312` and added `platformdirs`, and `setup` then completed.

Context, not part of the defect: the helper refused to reuse the existing `the-one-f5` root because it has no sentinel file, which is its intended safety behaviour, so the session used a new root, `the-one-f5-m35l1`.

## Evidence
- `scripts/windows_test_copy.py:59-60`: `PYTHON_WIN = "/mnt/c/Python311/python.exe"`, `BASE_PYTHON_DIR = "C:\\Python311"`. The docstring at `:21` and `:24` names the same path.
- `pyproject.toml:5`: `requires-python = ">=3.12"`.
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md`, the Leg 1 Part B entry (the workaround and the apparatus snags).

## Deferral
Carried so Flight 2 can continue. Revisit the next time `windows_test_copy.py` is used, which is Flight 2 leg 6, the desktop engine pass. Fix it before that leg's Windows session, or record the same hand workaround again.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

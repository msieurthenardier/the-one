# Squawk 0343: windows_test_copy.py builds its venv with Python 3.11; the project needs 3.12

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-09
**Completed**: 2026-11-11

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
`scripts/windows_test_copy.py`: `PYTHON_WIN` and `BASE_PYTHON_DIR` now name Python 3.12 (`/mnt/c/Python312/python.exe`, `C:\Python312`), and the two docstring mentions follow. `op_build_venv` now runs `pip install platformdirs` right after it creates a fresh venv, because `operator_forms()` imports `platformdirs` from that venv before the closure installs (the leg 1 Part B snag). New test `tests/test_windows_test_copy.py::test_base_python_matches_requires_python` pins both paths to the floor in `pyproject.toml`'s `requires-python`, so they cannot drift back.

## Verification
`/mnt/c/Python312/python.exe --version` reports 3.12.10. `tests/test_windows_test_copy.py` passes, ruff check and format are clean, and the new test fails against the old 3.11 literals. The Windows side (`setup`) was not run here; it is first exercised in Flight 2 leg 8 Part B.

## Sign-Off
- **Reviewer (Haiku; not a security-sensitive surface): `[HANDOFF:confirmed]`, 2026-11-11.** Checked: no 3.11 path left; every interpreter use goes through `BASE_PYTHON_DIR`; the `platformdirs` install runs only on a fresh venv with the venv's own interpreter; the new test catches drift; 160 passed, ruff clean.
- **Notes accepted:** `the_one/agents.md` (~`:2249-2264`) still names `C:\Python311`; that doc drift is fixed in Mission 35 Flight 2 leg 8's commit, because leg 8 was editing `agents.md` in the same tree. A failed `platformdirs` install is not retried on the next run (minor: the closure install supplies it from `uv.lock`).
- **Committed on `flight/02-live-visuals`** as its own `squawk/0343:` commit, not on a `squawk/0343-*` branch: leg 8 Part A was live in the same working tree, so a branch switch was not possible (Flight Director, 2026-11-11). No separate PR; it ships with the flight's PR. First real use: leg 8 Part B's Windows session.

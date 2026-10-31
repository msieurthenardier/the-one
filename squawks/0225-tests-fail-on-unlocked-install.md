# Squawk 0225: six unit tests fail on an install resolved from the ranges instead of uv.lock

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-21
**Completed**: —
**Related**: 0241: the same defect logged twice (unit tests fail on an unlocked install); complete together. CI and every package build install from the lock, so only contributors following CLAUDE.md's `pip install -e` hit it ([maintenance 2026-10-30](../maintenance/2026-10-30.md), finding #22).

## Report
On a fresh venv installed with `pip install -e ".[all-llms,dev]"` (which resolves the `pyproject.toml` ranges, not `uv.lock`), six unit tests fail. They pass once the venv is synced to the lock (`uv sync --frozen`). This was seen during squawk 0224, and the same six fail with the old certifi and Pillow too, so 0224 is not the cause. Some newer release that the ranges allow breaks them. CLAUDE.md's install command is the unlocked one, so a new checkout following it hits these failures.

Failing tests:
- `tests/test_credential_gate.py::test_exempt_paths_are_get_only_on_the_real_app`
- `tests/test_mcp_wire_shapes.py::test_httpx2_uses_the_os_trust_store_unless_overridden`
- 4 tests in `tests/test_openrouter_wire_level.py`

Find which package versions differ between the two venvs (`pip freeze` diff), name the one that breaks each test, and either cap its range or fix the test or the code to work with it.

## Evidence
- Squawk 0224's Developer run (2026-10-21, worktree from `origin/main` at f6b2ed0): 6 failed on the pip-installed venv; 6751 passed after `uv sync --frozen`.
- CLAUDE.md "Commands": `pip install -e ".[all-llms,dev]"`.

## Corrective Action
*(written at completion)*

## Verification
- On a venv from `pip install -e ".[all-llms,dev]"`, the six tests pass, and so does `make test-unit`.
- They still pass on the locked venv.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

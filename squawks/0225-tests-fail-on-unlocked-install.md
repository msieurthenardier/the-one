# Squawk 0225: six unit tests fail on an install resolved from the ranges instead of uv.lock

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-21
**Completed**: 2026-11-03
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
Fixed together with [0241](0241-unit-tests-fail-under-fresh-dependencies.md), which records the cause per test (FastAPI/Starlette lazy `_IncludedRouter`, httpx2 trust-store change, openai 3.x on httpx2) and the changes: test fixes in `tests/test_credential_gate.py` and `tests/test_mcp_wire_shapes.py`, and the `openai<3` ceiling in `pyproject.toml`.

## Verification
All six tests pass in a fresh `pip install -e '.[all-llms,dev]'` venv (`$HOME/the-one-scratch-venvs/s0241`) and in `.venv`; see 0241 for commands and `make test-unit`.

Original plan:
- On a venv from `pip install -e ".[all-llms,dev]"`, the six tests pass, and so does `make test-unit`.
- They still pass on the locked venv.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Completed together with 0241 (merged at triage).
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **Merged into [0241](0241-unit-tests-fail-under-fresh-dependencies.md)** as the primary record; complete together (second wave of the burn-down).

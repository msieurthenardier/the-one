# Squawk 0017: Broken `workspace/test_agent.py` is git-tracked, root-owned, and `workspace/` is not ignored

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

`workspace/` is the agents' runtime scratch directory, but it is not in `.gitignore`,
and one file inside it is tracked: `workspace/test_agent.py`, a two-line broken
fixture (`def test_run_tests(): result = run_tests()` — `run_tests` undefined)
committed on 2026-04-18 by the placeholder identity "Your Name" with the message
"Staged changes for review". On disk it is owned `root:root`, unlike everything
around it. It is inert only because `pytest`'s `norecursedirs` excludes `workspace`.
An unignored agent workspace is a standing path for agent-generated content to land in
a commit. Found by the 2026-08-27 maintenance inspection (G2).

Fix: `git rm workspace/test_agent.py`; add `workspace/` to `.gitignore` (keep the
directory creatable at runtime — confirm nothing relies on it existing in a fresh
clone); `chown` the on-disk copy back to the operator user.

## Evidence

- `git ls-files workspace` → `workspace/test_agent.py`
- `git log --format='%h %an %ad %s' -- workspace/test_agent.py` →
  `6db3482 Your Name 2026-04-18 Staged changes for review`
- `ls -la workspace/test_agent.py` → `-rw-r--r-- 1 root root 158`
- `grep -n workspace .gitignore` → no match; `pyproject.toml:142` `norecursedirs`
  includes `"workspace"` (why it doesn't collect)

## Corrective Action

- `git rm workspace/test_agent.py` failed on the unlink (`Permission denied`) —
  `workspace/` itself is `root:root 0755` on disk, not just the file inside it, so
  the operator-owned parent assumption in the fix note didn't hold. Fell back to
  `git rm --cached workspace/test_agent.py`, which untracked the file from the
  index. The on-disk copy (`workspace/test_agent.py`, still `root:root`, 158 bytes)
  remains and needs an operator `sudo rm workspace/test_agent.py` (or `chown` the
  directory back to the operator user first) — not done here, per the no-sudo
  constraint.
- Added `workspace/` to `.gitignore`, grouped with the other runtime/data-directory
  ignores (`.memory/`, `.flightops/`) with a comment citing this squawk.
- Confirmed nothing assumes `workspace/` pre-exists: grepped `the_one/`, `tests/`,
  `scripts/`, `ci/`, `Makefile` for `workspace` — every hit is either unrelated
  ("workspace" as a generic term for sandbox/host scratch space, Slack "workspaces",
  a `workspace` function parameter in `tests/_sandbox_fixtures.py` naming a pytest
  `tmp_path`-derived fixture dir, or a JSON config key in `tests/test_db_api.py`) or
  is the `pyproject.toml` exclude patterns themselves. No code path does
  `open("workspace/...")`/`os.listdir("workspace")` etc. against the literal
  project-root directory, so no fix was needed there — no scope escalation.
- Confirmed `pyproject.toml:142` `norecursedirs = ["workspace", ...]` and
  `[tool.ruff] extend-exclude = ["workspace"]` (line 148) are still present — left
  as-is (belt and braces alongside the new `.gitignore` rule).
- `workspace/` contains nothing else besides `test_agent.py` (`find workspace` →
  just the directory and that one file).

## Verification

- `git ls-files workspace` → empty (file successfully untracked).
- `git check-ignore -v workspace/anything` → `.gitignore:25:workspace/	workspace/anything`
  (new rule matches).
- `git status --short workspace` → `D  workspace/test_agent.py` (deletion staged,
  as expected; not committed).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_config.py -x --timeout 60`
  → 37 passed.
- `make lint` → All checks passed!
- `make format-check` → 443 files already formatted.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `5cf3cac` on `squawk/turnaround-2026-08-27` — PR #178

# Squawk 0017: Broken `workspace/test_agent.py` is git-tracked, root-owned, and `workspace/` is not ignored

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion — `git ls-files workspace` empty; `git check-ignore workspace/x`
matches; suite still green)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

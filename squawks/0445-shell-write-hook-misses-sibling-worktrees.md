# Squawk 0445: The shell-write hook does not guard sibling git worktrees

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-28
**Completed**: —

## Report
The project `PreToolUse` hook (`.claude/hooks/block_shell_writes.py`, squawk 0292) refuses shell writes into `the_one/`, `tests/`, `docs/`, `scripts/`, `missions/`, `evals/`, `sorties/`, `squawks/` and the root docs only when the target resolves under the session's project root. A crew agent working in a sibling git worktree of the same repo is not guarded. Observed in sortie 22: a Developer ran `sed -i` on `sorties/22-…/legs/02-resume-after-the-token-save.md` in `/home/cprch/projects/the-one-sortie-22` and the hook let it through (the edit itself was a correct one-line status change). The existing `/home/cprch/projects/the-one-sortie-20` worktree has the same gap.

Reproduce: from a session whose project dir is `/home/cprch/projects/the-one`, run `sed -i 's/x/x/' /home/cprch/projects/the-one-sortie-22/tests/conftest.py`: not blocked. The same command on `/home/cprch/projects/the-one/tests/conftest.py` is blocked.

## Evidence
- `.claude/hooks/block_shell_writes.py` — `ROOT = os.path.normpath(os.environ.get("CLAUDE_PROJECT_DIR") or …)`, `ROOTS = {ROOT, os.path.realpath(ROOT)}`; `is_protected` returns True only if the normalized path starts with one of `ROOTS` and its first component under that root is in `PROTECTED`.
- `git worktree list`: `/home/cprch/projects/the-one-sortie-20` and `/home/cprch/projects/the-one-sortie-22` are worktrees of the same repository, outside `ROOTS`.

Likely direction: also treat every worktree of this repository as a root (for example read `git worktree list --porcelain` once, or resolve the target's own `git rev-parse --show-toplevel` and accept it when its common dir matches the project's). Add the case to `tests/test_shell_write_hook.py`.

## Corrective Action

## Verification

## Sign-Off
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: found mid-flight in sortie 22 (out of its scope); revisit at the next squawk turnaround, or before the next flight that runs its crew in a sibling worktree.

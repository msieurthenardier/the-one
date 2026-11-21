# Squawk 0385: The shell-write hook does not cover `sorties/` and `squawks/`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: 2026-11-21

## Report
The project's `PreToolUse` hook refuses shell commands that write into `the_one/`, `tests/`, `docs/`, `scripts/`, `missions/` and `evals/`, so that source, tests and artifacts are changed only through the edit tool. `sorties/` and `squawks/` hold the same kind of artifact as `missions/` and are not in its list. In sortie 19 a Developer changed a leg's status line and wrote its flight-log entry with `sed`, against its brief; the hook did not stop it. The log was checked afterwards and was intact.

Needed: add `sorties/` and `squawks/` to the hook's protected folders, with a case in its test file for each.

**Added 2026-11-19 (Mission 36 Flight 1 debrief):** repo-root files are not covered either. In that flight a Developer's `sed -i` wrote to `CLAUDE.md` and the hook let it through. Cover the root documents (`CLAUDE.md`, `SECURITY-MODEL.md`, `README.md`) too, with a test case.

## Evidence
- `.claude/hooks/block_shell_writes.py` — the list of protected folders.
- `tests/test_shell_write_hook.py` — the hook's tests.
- `.flightops/agent-crews/leg-execution.md`, the Developer "Implement" prompt — names the six folders the hook covers.
- `sorties/19-local-mcp-servers-newest-protocol/flight-log.md`, "leg 2 landed; flight review started".

## Corrective Action
- `.claude/hooks/block_shell_writes.py`: `PROTECTED` gains `sorties` and `squawks`; new `PROTECTED_FILES` (`CLAUDE.md`, `SECURITY-MODEL.md`, `README.md`) matched by `is_protected` as the exact path relative to the repo root (so `docs/README.md` stays covered by `docs/`, and a `README.md` elsewhere is not); `MENTION` (the inline-script check) also recognises those root files; module docstring and the block message updated. Fail-open behaviour unchanged.
- `.flightops/agent-crews/leg-execution.md`: the Implement prompt's folder list names the new folders and root documents. No other place lists the folders.
- `tests/test_shell_write_hook.py`: BLOCKED cases for `squawks/` (redirect, `sed -i`), `sorties/` (`>>`, `sed -i`, `cp`) and root files (redirect, `sed -i`, `tee`, `>>`, absolute path, `mv`, inline python); ALLOWED cases for reads (`grep`, `cat`, `sed -n`) and for writes to `/tmp/README.md`, `/tmp/CLAUDE.md`; the old allowed `squawks/` cases were flipped to blocked; `test_relative_path_resolves_against_cwd` extended (cwd `squawks/`, `sorties/`, repo root, `/tmp`, `docs/`, `.flightops/`).

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_shell_write_hook.py -x --timeout 60`: 118 passed.
- `.venv/bin/ruff check` and `ruff format --check` on the hook and test file: clean.
- Falsified (yes): with `squawks` and `CLAUDE.md` removed by editing, 6 tests failed (the new squawks and CLAUDE.md blocked cases and the cwd test); restored by editing, re-run not needed beyond the 118-pass run above (restore was an exact reverse edit).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21

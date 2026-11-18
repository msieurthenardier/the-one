# Squawk 0385: The shell-write hook does not cover `sorties/` and `squawks/`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: —

## Report
The project's `PreToolUse` hook refuses shell commands that write into `the_one/`, `tests/`, `docs/`, `scripts/`, `missions/` and `evals/`, so that source, tests and artifacts are changed only through the edit tool. `sorties/` and `squawks/` hold the same kind of artifact as `missions/` and are not in its list. In sortie 19 a Developer changed a leg's status line and wrote its flight-log entry with `sed`, against its brief; the hook did not stop it. The log was checked afterwards and was intact.

Needed: add `sorties/` and `squawks/` to the hook's protected folders, with a case in its test file for each.

## Evidence
- `.claude/hooks/block_shell_writes.py` — the list of protected folders.
- `tests/test_shell_write_hook.py` — the hook's tests.
- `.flightops/agent-crews/leg-execution.md`, the Developer "Implement" prompt — names the six folders the hook covers.
- `sorties/19-local-mcp-servers-newest-protocol/flight-log.md`, "leg 2 landed; flight review started".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

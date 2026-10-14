# Squawk 0212: The behavior-test dev-instance convention lets agents' file tools reach the repo

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
CLAUDE.md's behavior-test convention starts dev instances with `make up` from the repo root. The server's working directory is then the repo, so an agent's file tools can read and write it. In the Mission 30 `agent-notes-round-trip` run, the agent wrote a stray `note.txt` to the repo root and read `.memory/*.md`. Later runs started the server from a scratch working directory and left no trace in the repo.

## Evidence
- `tests/behavior/agent-notes-round-trip/runs/2026-10-14-15-03-23.md` (side effects section).
- The Mission 30 F2 flight log ("Setup finding for the debrief").

## Corrective Action
*(written at completion)* In CLAUDE.md's "Behavior-test credential convention" and the dev-instance boot snippets in the behavior specs, start the instance from a scratch working directory (`cd <scratch-cwd> && THE_ONE_PORT=… THE_ONE_DATA_DIR=… <repo>/.venv/bin/the-one serve`), or give `make up` a working-directory option.

## Verification

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

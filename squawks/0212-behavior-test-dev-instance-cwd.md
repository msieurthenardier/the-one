# Squawk 0212: The behavior-test dev-instance convention lets agents' file tools reach the repo

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-10-14

## Report
CLAUDE.md's behavior-test convention starts dev instances with `make up` from the repo root. The server's working directory is then the repo, so an agent's file tools can read and write it. In the Mission 30 `agent-notes-round-trip` run, the agent wrote a stray `note.txt` to the repo root and read `.memory/*.md`. Later runs started the server from a scratch working directory and left no trace in the repo.

## Evidence
- `tests/behavior/agent-notes-round-trip/runs/2026-10-14-15-03-23.md` (side effects section).
- The Mission 30 F2 flight log ("Setup finding for the debrief").

## Corrective Action
Done (docs only). In CLAUDE.md's "Behavior-test credential convention" and the dev-instance boot snippets in the behavior specs, start the instance from a scratch working directory (`cd <scratch-cwd> && THE_ONE_PORT=… THE_ONE_DATA_DIR=… <repo>/.venv/bin/the-one serve`), or give `make up` a working-directory option.

Chosen: the scratch-cwd form. CLAUDE.md's SAFETY RULE snippet now creates `$HOME/the-one-behavior-test-scratch/{cwd,data}`, starts `<repo>/.venv/bin/the-one serve` detached from `cwd` with the PID recorded, and states why; the credential path example follows. The Preconditions boot instructions in 13 behavior specs under tests/behavior/ were updated the same way (boot text only). Makefile and product untouched.

## Verification
`grep -rn 'make up' tests/behavior/*.md` now shows only non-boot mentions (exit-code measurements, prose); no test under tests/ pins the old snippet (grep of tests/*.py found none); `make lint` passes.

## Sign-Off
*(written at completion)*
**Reviewer**: Reviewer agent (Sonnet tier), batch review of squawks 0208–0212
**Verdict**: confirmed
**Commit**: 5e4203f

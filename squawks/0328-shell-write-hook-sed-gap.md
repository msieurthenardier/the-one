# Squawk 0328: The shell-write hook let one `sed -i` through on a protected file

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-04
**Completed**: —

## Report
During sortie 09 leg 3's accessibility fix pass, a Developer ran `sed -i` on `the_one/interfaces/web/static/js/areas/studio/mcp-agent-credentials.js`, and `.claude/hooks/block_shell_writes.py` (squawk 0292) did not block it. In the same pass the hook did block a second `sed` on `the_one/agents.md`. So the hook fails open on some command shape it should refuse. Both directories are protected (`the_one/` is on its list). The change itself was intended and was reviewed, but the edit-tool-only rule (squawk 0286) relies on this hook.

## Evidence
- `.claude/hooks/block_shell_writes.py::check_segment` (~224-248) handles `sed -i` and returns "sed -i on <path>"; `is_protected` (~165) and `tokenize` (~58) decide the target. The hook "fails open on anything it cannot parse" (its docstring).
- The flight log for sortie 09 ("Anomaly (process)" under leg 3) records the event. The exact command line isn't preserved, so reproduce candidate shapes: a `cd` into a subdirectory first, then a relative path; `sed -i''` or `-i.bak`; `bash -c '...'`; chained `&&`; quoting.

## Corrective Action
*(written at completion)*

## Verification
A unit test (`tests/test_block_shell_writes.py` or the hook's existing test) feeding the failing command shape to `check_command`, which must refuse it. Falsify it by reverting the parser fix.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: the hook blocked the other attempts, and the edit-tool-only rule is also stated in every crew prompt. Logged from the sortie 09 debrief — revisit at the next squawk turnaround.

# Squawk 0321: A VT sequence split across two ConPTY reads leaks partial escape bytes

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
`the_one/platform/pty.py::strip_vt_sequences` (squawk 0165) cleans each `_send_blocking` result separately. When a CSI or OSC sequence straddles two idle reads, its tail bytes (for example `[4;16H`) are left in the second result. In the Windows backend, hold an unterminated trailing sequence over to the next read.

## Evidence
- The batch review of turnaround 2026-11-02-2 (0165 notes).
- `the_one/platform/pty_windows.py::_send_blocking`.

## Corrective Action
*(written at completion)*

## Verification
- A unit test feeds a sequence split across two chunks and expects clean text with no tail bytes. It is falsified.
- The Windows PTY lane passes on the Windows worker.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

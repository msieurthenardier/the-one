# Squawk 0262: document the desktop test-patch rule and the pywebview/PyObjC upgrade checklist

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: —

## Report
Mission 32 Flight 3 added two safeguards that are only described in its flight log and tests, so a future maintainer will not know they exist:
1. **The test-patch rule.** `tests/test_desktop_split_guard.py` fails when a test patches or assigns, through `the_one.interfaces.desktop.shell`, a name that `shell.py` does not define. The rule ("patch a name in the module that defines it"; state lives on `session_state.state`) is not written down for test authors.
2. **The upgrade checklist.** The macOS Dock mode subclasses pywebview 5.4's Cocoa app delegate (`the_one/interfaces/desktop/macos_dock.py`). Its PyObjC bodies carry `# pragma: no cover` and are proven only by a hosted `macos-packages.yml` `lifecycle` dispatch; `tests/test_pywebview_cocoa_canary.py` pins the pywebview facts. A pywebview or PyObjC bump therefore needs the canary green **and** a `lifecycle` dispatch, and nothing says so.

Also add: macOS CI is hosted-only and dispatch-limited (no per-push macOS build).

## Evidence
- `tests/test_desktop_split_guard.py`, `tests/test_pywebview_cocoa_canary.py`, `the_one/interfaces/desktop/macos_dock.py` (`_install_delegate`, `_begin_activity`).
- The Flight 3 debrief, Documentation and Recommendation 5.

## Corrective Action
*(written at completion)*. An additive paragraph in `the_one/agents.md` (the Desktop launcher section or the macOS packaging section) covering 1 and 2 plus the hosted-only note, and one sentence in `CLAUDE.md`'s macOS packaging paragraph pointing to it.

## Verification
- The paragraph exists, names both tests and the `lifecycle` dispatch command, and `make test-unit` still passes (12 skips).

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** at Mission 32 Flight 3's debrief, on the operator's decision. Both files are shared with Mission 31, so the edit stays additive.

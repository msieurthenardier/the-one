# Squawk 0213: Behavior specs still use `/tmp` scratch data directories and `make down` teardown

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
After squawk 0212, CLAUDE.md's behavior-test convention puts the scratch data directory under `$HOME` (not `/tmp`) and stops the instance by its recorded PID. Several behavior specs still name `/tmp/...` scratch data directories and tell the operator to stop with `make down`, which conflicts with the new convention. Found by the squawk 0208–0212 batch Reviewer.

## Evidence
- `/tmp` scratch data directories remain in `tests/behavior/jump-to-palette.md`, `list-and-detail.md`, `start-a-chat.md`, `workbench-navigation.md`, `stub-connector-round-trip.md` and the `kb-*` specs.
- "`make down` against the same env" stop instructions remain, for example in `kb-folder-watch-round-trip.md` step 8.

## Corrective Action
*(written at completion)* Align these specs' scratch data paths to `$HOME/...` and their stop instructions to "stop by recorded PID", changing only setup and teardown text.

## Verification

**Partial progress, Mission 31 Flight 6 leg 09b (2026-10-27; the squawk stays open):** five specs were deliberately re-authored before the mission-close sweep: `chat-roundtrip`, `studio-agent-crud`, `agent-step-limit-notice`, `stub-connector-round-trip` and `jump-to-palette` now name "a dedicated port of 8490 or higher (not 8485)" and a scratch data and working directory under `$HOME` (no `/tmp`, no 8485/8488). These five are cleared. `list-and-detail`, `start-a-chat`, `workbench-navigation` and the `kb-*` specs, and the `make down` stop instructions, remain open here. In the B5 fix pass `system-provider-config.md`'s mentions of `App.confirmDelete` (the retired alias) were re-authored to `App.ui.confirm` (descriptive wording only, no Expected Result change).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

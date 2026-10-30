# Squawk 0291: Purge flash reads "Deleted 1 chat and their history."

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
After Purge now on an agent with one chat the flash reads "Deleted 1 chat and their history." (M33 F4 fix pass 3). The pronoun should follow the count ("its history" for one chat).

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/agent-editor-controller.js` (the purge success flash).
- `tests/test_store_static.py` pins the flash anchor.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

The flash reads "Deleted 1 chat and its history." for one chat and "Deleted N chats and their history." otherwise; the pin is updated.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

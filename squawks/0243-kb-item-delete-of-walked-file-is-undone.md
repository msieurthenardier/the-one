# Squawk 0243: Deleting a walked file through the item route is silently undone

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
`DELETE /api/knowledge-bases/{kb_id}/items/{item_id}` accepts a `file` item that a folder walk created (one with a `parent_id`). It answers 200 and deletes the item, but the next walk of the parent folder finds the file again and recreates it under a new id, then re-embeds it. The caller is told the file is gone when it is not. The route should refuse such an item with 409 and a plain sentence ("remove its folder instead"). Studio never offers a remove on walked rows (Mission 31 Flight 3 HAT), so only API callers hit this. Found in the M31 F3 HAT design review.

## Evidence
- `the_one/interfaces/web/api.py:delete_kb_item` (~:2112) has no `parent_id` check.
- The folder walk's reconcile treats a missing child as new (`the_one/knowledge/walk.py`, `plan_reconcile`).

## Corrective Action

## Verification

## Sign-Off

# Squawk 0244: Registering a single file does not start indexing

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
`POST /api/knowledge-bases/{kb_id}/items` with `type: "file"` stores the item as `pending`, but it does not kick the knowledge base's indexing worker. A folder registration does, through `_after_folder_registered`. The file waits until some other trigger runs a pass, such as a reconcile tick, a folder change or a re-index. On a knowledge base with no folders, the reconcile tick skips it altogether. Expected: the file POST calls `manager.request_index(kb_id)`, like the folder path, so a new file indexes promptly. Found in the M31 F3 HAT design review.

## Evidence
- `the_one/interfaces/web/api.py` (~:2038-2041): `await repo.create(item)`, then `if item.type == "folder": _after_folder_registered(kb_id, item)`. The file branch has no `request_index`.
- The reconcile tick skips knowledge bases with no folders (`the_one/knowledge/watcher.py`, ~:594).

## Corrective Action

## Verification

## Sign-Off

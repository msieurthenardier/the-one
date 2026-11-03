# Squawk 0244: Registering a single file does not start indexing

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-11-03

## Report
`POST /api/knowledge-bases/{kb_id}/items` with `type: "file"` stores the item as `pending`, but it does not kick the knowledge base's indexing worker. A folder registration does, through `_after_folder_registered`. The file waits until some other trigger runs a pass, such as a reconcile tick, a folder change or a re-index. On a knowledge base with no folders, the reconcile tick skips it altogether. Expected: the file POST calls `manager.request_index(kb_id)`, like the folder path, so a new file indexes promptly. Found in the M31 F3 HAT design review.

## Evidence
- `the_one/interfaces/web/api.py` (~:2038-2041): `await repo.create(item)`, then `if item.type == "folder": _after_folder_registered(kb_id, item)`. The file branch has no `request_index`.
- The reconcile tick skips knowledge bases with no folders (`the_one/knowledge/watcher.py`, ~:594).

## Corrective Action
`create_kb_item` in `the_one/interfaces/web/api.py` now calls `get_indexing_manager().request_index(kb_id)` for the file branch (no-op when no manager is installed, as for folders). `test_scope_all_requeues_indexed_and_failed_file_items` posts a file first, so its expected calls gained the POST's `request_index`.

## Verification
`tests/test_db_api.py::TestKnowledgeBaseAPI::test_file_post_requests_indexing` (fake manager records one `request_index`). Falsified: yes (call disabled by edit, test failed; restored). `tests/test_db_api.py`: 191 passed; ruff check and format clean. Full unit tier: see report.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

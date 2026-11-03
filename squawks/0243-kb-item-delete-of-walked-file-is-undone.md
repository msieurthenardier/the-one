# Squawk 0243: Deleting a walked file through the item route is silently undone

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-11-03

## Report
`DELETE /api/knowledge-bases/{kb_id}/items/{item_id}` accepts a `file` item that a folder walk created (one with a `parent_id`). It answers 200 and deletes the item, but the next walk of the parent folder finds the file again and recreates it under a new id, then re-embeds it. The caller is told the file is gone when it is not. The route should refuse such an item with 409 and a plain sentence ("remove its folder instead"). Studio never offers a remove on walked rows (Mission 31 Flight 3 HAT), so only API callers hit this. Found in the M31 F3 HAT design review.

## Evidence
- `the_one/interfaces/web/api.py:delete_kb_item` (~:2112) has no `parent_id` check.
- The folder walk's reconcile treats a missing child as new (`the_one/knowledge/walk.py`, `plan_reconcile`).

## Corrective Action
`delete_kb_item` in `the_one/interfaces/web/api.py` now refuses an item with a `parent_id` (409, "This file belongs to a registered folder, so deleting it would be undone by the next scan. Remove its folder instead."), after the 404 checks. Studio never offers delete on walked rows, so no UI change. No existing test deleted a walked file (the folder-cascade test deletes the folder).

## Verification
`tests/test_db_api.py::TestKnowledgeBaseAPI::test_delete_walked_file_is_refused_409` (409, plain sentence, item survives). Falsified: yes (guard disabled by edit, test failed; restored). `tests/test_db_api.py`: 191 passed; ruff check and format clean. Full unit tier: see 0244 / report.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

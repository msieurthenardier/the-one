# Squawk 0115: KB detail test can search while "Re-index all" is still running

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-02
**Completed**: 2026-10-06

## Report

`tests/browser/test_flow_studio_knowledge_inventory.py::test_detail_view_indexing_poll_reindex_and_search`
failed once in a full library-lane run under load, and passed alone and in the lane rerun.
It clicks "Re-index all files" and then waits for the status count to read `indexed: 3`
before it searches for "fox". The search returned hits, but none for `note.txt`, the file
that carries the keyword:

```
expect(hits.filter(has_text=str(fixture_dir / "note.txt"))).to_have_count(1)
AssertionError: Locator expected to have count '1'
Actual value: 0
```

The suspected cause is the wait itself. The count already reads `indexed: 3` BEFORE the
click (the preceding "Re-index changed files" step waited for exactly that text). The
`expect(...).to_have_text("indexed: 3")` after "Re-index all" can therefore pass at once,
on the stale text, before the POST's requeue and the client's one immediate status refresh
land. The search then runs while the files are being re-embedded, and the keyword's file can
be missing from the vector side of the results.

Found by Mission 25 Flight 3 leg 5b's library-lane gate. Leg 5b touched no Library or
knowledge-base code. The lane was rerun in full and passed.

## Evidence

- The failing run's log (leg 5b, library lane, `THE_ONE_TEST_NETNS=1`): 1 failed, 137 passed,
  1 skipped (466.4s); the test alone: 1 passed (8.4s).
- The test's sequence: the `kb-reindex-changed-btn` click and an `indexed: 3` wait, then the
  `kb-reindex-all-btn` click and another `indexed: 3` wait (no intermediate state is
  observed), then the search.
- `the_one/interfaces/web/api.py` `POST /knowledge-bases/{kb_id}/reindex`: `scope=all`
  requeues synchronously, then `request_index`; `knowledge-section.js` `triggerReindex`
  issues one status refresh after the response.
- Recorded in the leg 5b entry of
  `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`.

## Corrective Action

`test_detail_view_indexing_poll_reindex_and_search` no longer waits on the already-showing `indexed: 3`. It first waits for nothing pending or indexing (quiescing the earlier "changed" re-index), records `content_freshness` from `GET /api/knowledge-bases/{kb_id}/status`, clicks "Re-index all files", and then polls (bounded 30s, failing loudly with the status body) until `content_freshness` has changed AND no item is pending or indexing, before searching. Checked first: `indexed_at` is `datetime.now(timezone.utc).isoformat()` (microsecond resolution), and `scope=all` calls `requeue_for_reindex`, so every file re-enters `pending` and `update_status(..., "indexed")` rewrites its `indexed_at`.

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

`tests/browser/test_flow_studio_knowledge_inventory.py -k indexing_poll_reindex`: 1 passed. The `library` lane gate is recorded in the flight log (leg 2).

## Sign-Off

**Reviewer**: pending the Flight 6 leg review

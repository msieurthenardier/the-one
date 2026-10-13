# Squawk 0091: `list_by_status` has no `ORDER BY` tiebreak — the indexing worker's page composition is non-deterministic

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: 2026-10-13

## Report

`SQLiteKBItemRepository.list_by_status` (`the_one/db/repositories.py:777` —
`sql += " ORDER BY created_at"`) has no tiebreak, and **squawk 0087 did not
name it**. That squawk's Report says "`SQLiteKBItemRepository`'s three list
queries all order by `created_at` alone" and enumerates `:527`, `:632`, `:640`.
There are **four**. Squawk 0087 is now completed against its stated three;
this is the one it missed, filed separately rather than reopening a closed
record.

Found by the Flight Director while spot-checking Mission 24 Flight 7 Leg 2a's
ordering fix: `grep 'ORDER BY created_at' repositories.py` returned a
still-bare hit after the leg had fixed everything the squawk named.

**This one has a different consequence from the three 0087 covered.** Those
three feed Studio's item lists, where the symptom is rows visibly reshuffling
between renders. `list_by_status` is the query the **indexing worker** drains
`pending` items with, and it is called with `limit`:

- `manager.py:512` — `list_by_status(kb_id, "pending", limit=..., type="file")`,
  the worker's page fetch
- `manager.py:526` — the full-page variant
- `manager.py:323` — `limit=1`, the "is there anything pending?" probe

Because a folder walk inserts every discovered file in one pass, `created_at`
ties are the normal case, not an exotic one. With `LIMIT` over tied rows and no
tiebreak, **which** items land in a given pass is arbitrary and can differ
between runs over identical data.

**Not a correctness bug**: every `pending` item is drained eventually, since
processed items leave the status. It is a reproducibility bug — two runs over
the same corpus can index in different orders, which makes a failing pass
harder to reproduce and makes `limit=1` probe behaviour unpredictable. Severity
`routine` for that reason; the operator-visible reshuffling 0087 fixed was the
sharper symptom.

## Evidence

```
$ grep -n 'ORDER BY created_at' the_one/db/repositories.py
532:  ... WHERE kb_id = ? ORDER BY created_at, path_or_url        # fixed, F7 L2a
638:  ... WHERE parent_id = ? ORDER BY created_at, path_or_url     # fixed, F7 L2a
648:  ... ORDER BY created_at, path_or_url                         # fixed, F7 L2a
777:  sql += " ORDER BY created_at"                                # NOT fixed — this squawk
```

- `the_one/db/repositories.py:760-782` — `list_by_status`, docstring "Items in
  `kb_id` at `status`, oldest first"
- `the_one/knowledge/manager.py:323`, `:512`, `:526` — the three call sites,
  two of them paged

## Disposition

Qualified against the squawk gate: **one coherent item** ✅ (a single missing
tiebreak on a single query); **no design decisions** ✅ (the fix is the one
Flight 7 Leg 2a already applied to its three siblings — `, path_or_url`
ascending, matching the walk's own discovery order); **bounded blast radius** ✅
(one `ORDER BY` clause; `list_by_status` is called only from
`knowledge/manager.py`); **verifiable** ✅ (a repository test inserting tied
`created_at` rows and asserting stable paging, mirroring the test Leg 2a added
for the other three).

**Deliberately not folded into Flight 7 Leg 2a.** The leg was chartered against
squawk 0087's stated scope and fixed exactly that; growing it mid-implementation
to cover a fourth query found afterwards is how legs lose their shape. Logged
and deferred per the flight workflow's out-of-scope-defect rule.

## Corrective Action

Added `, path_or_url` to `list_by_status`'s `ORDER BY`, so it reads
`ORDER BY created_at, path_or_url` — identical to the fix Flight 7 Leg 2a
applied to `list`, `list_children` and `list_folders` (none of which add `id`).

## Verification

Added `TestKBItemRepositoryOrdering::test_list_by_status_orders_tied_rows_by_path_and_pages_stably` in tests/test_db_repositories.py: a repository test inserting several `pending` items with an
identical `created_at`, then asserting that two successive
`list_by_status(..., limit=N)` calls return the same N items in the same order.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.

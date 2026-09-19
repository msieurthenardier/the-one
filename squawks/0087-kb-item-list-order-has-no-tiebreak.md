# Squawk 0087: knowledge-base item lists have no stable order

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: —

## Report

`SQLiteKBItemRepository`'s three list queries all order by `created_at` alone:

- `the_one/db/repositories.py:527` — `SELECT * FROM kb_items WHERE kb_id = ? ORDER BY created_at`
- `the_one/db/repositories.py:632` — `... WHERE parent_id = ? ORDER BY created_at`
- `the_one/db/repositories.py:640` — `... WHERE kb_id = ? AND type = 'folder' ORDER BY created_at`

`created_at` is an ISO-8601 string written by `now_iso()`, and a folder walk
inserts every discovered file in one pass — so ties are normal, not exotic. SQLite
gives no stable ordering for tied rows, and nothing downstream re-sorts: the walk
sorts by absolute path, but that ordering is discarded the moment the rows are
read back.

**Operator-visible consequence**: the file rows inside a folder panel in Studio's
knowledge-base detail view can reorder between renders with no change on disk.
The panel re-renders on the 5-second poll whenever the items signature moves, so
a list the operator is reading can reshuffle underneath them.

Found while adding browser coverage for nested-folder rendering (M24 F06 L06, HAT
pass 2). The new assertions had to compare the rendered paths as a **set** rather
than a sequence, because asserting order would have pinned behaviour the database
does not actually guarantee — a test that passes today and flakes later. That
workaround is the reason this is filed rather than fixed in passing: the test can
be tightened once order is a contract.

## Evidence

- `the_one/db/repositories.py:527`, `:632`, `:640` — the three `ORDER BY created_at` clauses
- `tests/browser/test_flow_studio_knowledge_inventory.py` — the nested-folder
  assertions compare relative paths as a sorted set, with the reason recorded inline

## Corrective Action

*(pending)* Add a deterministic tiebreak — `ORDER BY created_at, path_or_url` — to
the three queries, so equal timestamps fall back to a stable, meaningful order
(which is also the order the walk discovered them in). Then tighten the browser
assertion from a set comparison to a sequence.

## Verification

*(pending)* A repository test inserting several items with an identical
`created_at` and asserting the returned order is by `path_or_url`; the browser
assertion changed to compare an ordered list.

## Sign-Off

*(pending)*

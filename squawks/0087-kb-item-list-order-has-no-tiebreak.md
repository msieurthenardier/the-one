# Squawk 0087: knowledge-base item lists have no stable order

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: 2026-09-19

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

Fixed in Mission 24 Flight 7 Leg 2 (inventory-freshness). All three queries in
`the_one/db/repositories.py` (`KBItemRepository.list`, `.list_children`,
`.list_folders` — the `:527`/`:632`/`:640` sites this squawk was filed
against) now read `ORDER BY created_at, path_or_url` — **ascending**, matching
the order `walk_folder` discovers files in (`walk.py`'s own
`files.sort(key=lambda f: f.path)`), so a tied `created_at` batch (a folder
walk inserting every discovered file in one pass) now falls back to a stable,
meaningful order instead of SQLite's unspecified tie order. `DESC` was
considered and rejected: the two existing tiebreak precedents in this file
(`AgentRevisionRepository.list_for_agent`, `MCPToolConfigRepository`'s
identifier list) both order `DESC` for a "most recent first" listing, which is
not this case — ascending path order is what makes the read order match
discovery order.

`tests/browser/test_flow_studio_knowledge_inventory.py`'s nested-folder
assertion (`test_detail_view_indexing_poll_reindex_and_search`) is tightened
from a sorted-set comparison to an ordered-sequence comparison, with the
inline comment updated to say order is now a contract rather than the reason
a set comparison was needed.

## Verification

- `tests/test_db_repositories.py::TestKBItemRepositoryOrdering` (Flight 7 Leg
  2) inserts several items sharing one `created_at` value and asserts
  `list`/`list_children`/`list_folders` each return them in `path_or_url`
  order, repeatably across multiple reads — proving the order is now a
  property of the query, not incidental SQLite behaviour.
- `tests/browser/test_flow_studio_knowledge_inventory.py`'s nested-folder test
  asserts the rendered relative paths as an exact ordered list
  (`["handbook/onboarding.md", "note.txt", "notes/incident.md"]`, the
  absolute-path-ascending order for that fixture) rather than a sorted set.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_repositories.py -x --timeout 30`
  and `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio -x`
  both green.

## Sign-Off

**Reviewer**: flight-end Reviewer, Mission 24 Flight 7 (Sonnet tier — the diff
touches `confirm.js`, which guards credential rotation, and `agent/factory.py`,
which governs agent tool reach)
**Verdict**: confirmed — "`ORDER BY created_at, path_or_url` applied to all
three queries; a repository test pins stable order across repeated reads with
tied `created_at`; the browser assertion that motivated this squawk is tightened
from a sorted-set comparison to an exact sequence."
**Commit**: e7fea7e (`flight/07-mission-close`, Leg 02 `inventory-freshness`)

**Note**: a **fourth** untiebroken query — `list_by_status`
(`repositories.py:777`) — was found by the Flight Director while spot-checking
this fix. This squawk's own Report says "three list queries"; there are four.
The fourth is filed separately as **squawk 0091** rather than reopening this
record, because its consequence differs: it is the query the indexing worker
drains `pending` items with, so the defect is non-deterministic page
composition, not visible row reshuffling.

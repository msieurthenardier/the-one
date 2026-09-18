# Squawk 0078: Name `multi-await-reads-are-not-snapshots` in `agents.md` conventions

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

## Report

The application shares **one** process-wide `aiosqlite` connection across
coroutines. A read composed of several `await`s is therefore not a snapshot:
the event loop can yield between them, and a concurrent mutation can land in
the gap. Every follow-up lookup in a multi-step read must tolerate a row that
has since vanished.

This has now been discovered three times, independently, and documented
three times individually rather than once generally:

1. **Flight 3** — FTS5 can return chunks of an `indexing` item whose vectors
   have not landed.
2. **Flight 3** — a saved sidecar can hold ids the last re-index deleted from
   `kb_chunks`; `get_many` returns fewer rows.
3. **Flight 5, Leg 1 design review** — an item deleted between `get_many` and
   the per-item path resolution would raise an unhandled `KeyError` out of
   `search()`, crashing the query where the other two degrade. Fixed as
   AC-6b (tolerate and drop the hit, mirroring `get_many`'s own tolerance).

Three instances of one rule is the point at which this project normally names
a convention. Naming it means the fourth is designed for rather than found at
review — and the third was found only because a reviewer went looking.

Proposed name: `multi-await-reads-are-not-snapshots`. Rule: *on the shared
connection, a read spanning more than one `await` may observe rows that
disappear between steps; every follow-up lookup tolerates a missing row and
shortens its result rather than raising.*

## Evidence

`the_one/agents.md` — the two Flight 3 crash windows are documented
individually in the knowledge-indexing section.
`missions/24-knowledge-bases/flights/05-agent-query/legs/01-retrieval-and-fusion.md`,
AC-6b — the third instance and its fix.
`the_one/db/repositories.py::KBItemRepository.get` — raises `KeyError` on an
absent row, which is what made instance 3 a crash rather than a degrade.

## Corrective Action

*(written at completion)*

## Verification

*(written at completion — expected: the convention appears in `agents.md`'s
Project Conventions, and the three instances point at it rather than
restating the rule)*

## Sign-Off

*(written at completion)*

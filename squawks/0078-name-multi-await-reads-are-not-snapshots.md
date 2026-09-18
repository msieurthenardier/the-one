# Squawk 0078: Name `multi-await-reads-are-not-snapshots` in `agents.md` conventions

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-09-18

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

Added `### \`multi-await-reads-are-not-snapshots\`` to `the_one/agents.md`'s
Project Conventions (`### Project-wide` block), directly after the new
`waiter-bound-lock-timeout` entry (squawk 0076, same spawn) and before
`### Mission-specific (M16)`. States the rule from the Report verbatim in
substance (a multi-`await` read on the shared process-wide connection is not
a snapshot; every follow-up lookup tolerates a missing row and shortens its
result rather than raising), cross-references "Singleton aiosqlite
connection model" for the shared-connection premise, and cites all three
instances: the two Flight 3 crash windows (pointing at "Knowledge storage"
below rather than restating them) and the Flight 5 Leg 1 AC-6b instance
(citing the leg artifact directly, since — unlike the first two — AC-6b was
not previously written up anywhere in `agents.md`; it existed only in the
leg spec and the `retrieval.py` code comment, so there was no existing
agents.md prose to redirect for that third instance).

For the two Flight 3 instances, edited the existing "Knowledge storage"
paragraph (`**Two crash-window consequences recorded for Flight 5's fusion
design**...`) to add a five-word parenthetical pointing at the new
convention by name, without deleting or rewording any of its specifics (the
two window descriptions, `get_many`'s tolerance, file/method names all
unchanged).

Scope check: did not touch `the_one/knowledge/retrieval.py` for this
squawk — its module docstring and the `search()` function's inline comments
already describe the AC-6b fix in full and already say "as recorded in
`the_one/agents.md`" for the two crash windows, so no code or code-docstring
change was needed to satisfy this squawk's ask (an agents.md naming/pointer
change only). Squawk 0077's docstring edit to `_fuse` in the same file is a
separate, unrelated change from the same spawn.

## Verification

`the_one/agents.md` Project Conventions now contains
`### \`multi-await-reads-are-not-snapshots\`` naming the rule and citing all
three instances. The "Knowledge storage" section's two-crash-window
paragraph now reads "...per the `multi-await-reads-are-not-snapshots`
convention above..." while keeping its original window (a)/(b) specifics
verbatim. `make lint` (`ruff check` + `ruff format --check`) is clean (no
Python files touched by this squawk). `tests/test_kb_retrieval.py` (31
tests) passes unchanged as a sanity check for the same-spawn 0077 edit to
the adjacent `retrieval.py` file.

## Sign-Off

**Reviewer**: batch Reviewer agent (**Sonnet** tier — the diff touches the encryption-rotation endpoint and a dependency floor for a package inside the shipped frozen closure, both security-sensitive surfaces per `.flightops/agent-crews/leg-execution.md`, even though every change is comment-, doc- or version-only)
**Verdict**: confirmed
**Commit**: `PENDING`

# Squawk 0048: `docs/kb-architecture.md` still states the superseded "10s of GB per KB" target

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-12
**Completed**: 2026-09-14

## Report

`docs/kb-architecture.md` is a pre-mission research survey. Mission 24's
`mission.md` records that its one load-bearing claim — a "10s of GB per KB"
scale target — was revised down by the operator to the mission's Constraints
ceiling, and says the doc "should be amended or retired to say so." It has not
been. A reader arriving at the doc treats the old figure as current, and it
drives the doc's own vendor conclusions (disk-first, Matryoshka truncation).

Fix: either add a superseded banner at the top pointing at
`missions/24-knowledge-bases/mission.md` and correct the four figures, or
retire the doc. No new analysis.

## Evidence

- `docs/kb-architecture.md:8` — "Single user, but corpora reach 10s of GB per KB"; also `:95`, `:101`, `:110`
- `missions/24-knowledge-bases/mission.md:44-48` — "has been revised down by the operator to the ceiling in Constraints below. The doc should be amended or retired to say so."

## Corrective Action

Took the "amend, don't retire" branch of the fix described in the Report —
the survey's vendor analysis (LanceDB, Nomic/BGE, LlamaIndex, Crawl4AI) is a
useful historical record of the tradeoff space even though the mission chose
differently, so deleting it would lose more than it fixes.

1. Added a `> **Superseded.**` blockquote directly under the H1 stating the
   doc is a pre-mission survey, that `missions/24-knowledge-bases/mission.md`
   supersedes it, that the scale target was revised down to the mission's
   Constraints ceiling (low single-digit GB per KB), and which conclusions
   the mission did/didn't adopt: the general shape (bundled local
   static-embedding model; vectors-only, disk-first store) was adopted in
   spirit, but the specific vendor picks were not — the mission chose
   `potion-retrieval-32M` over Nomic/BGE and `sqlite-vec`/`usearch` over
   LanceDB (LanceDB ruled out on weight at the corrected ceiling).
2. Corrected the Constraints bullet (was line 8, now line 18) to state the
   mission's actual ceiling, with a parenthetical noting the original figure
   and pointing at Mission 24.
3. Left the doc's internal reasoning (the "Recommended Stack" section) intact
   but qualified each remaining "10s of GB" occurrence inline as
   "the originally-assumed 10s-of-GB scale (superseded, see notice above)" —
   so the survey's own logic still reads coherently as *why it concluded what
   it concluded at the time*, without a reader mistaking it for the current
   target.

Chose notice-plus-qualifier over a full rewrite because the squawk's own
Report says "No new analysis" — rewriting the reasoning to match the new
ceiling would require redoing the vendor tradeoff analysis (e.g. would
LanceDB still lose on weight at a smaller corpus? mission.md already answers
this independently), which is exactly the scope the mission itself owns.
Chose it over deletion/retirement because the vendor survey remains a
legitimate historical record of options considered, and the mission's own
Context section treats it that way ("unratified prior art") rather than as
dead weight to remove.

## Verification

`git status --short` (only files touched by this squawk):
```
 M docs/kb-architecture.md
 M squawks/0048-kb-architecture-scale-claim.md
```
(`the_one/agents.md` and `squawks/0047-*.md` also show modified in the
working tree, but those are pre-existing uncommitted edits from another
squawk, untouched here.)

`grep -n "10s of GB" docs/kb-architecture.md`:
```
5:> source of truth. Its scale target ("10s of GB per KB", below) was revised
18:- Single user, but corpora reach low single-digit GB per KB (originally surveyed at 10s of GB; revised down — see Mission 24)
```
Both hits are inside the superseded notice itself (line 5) or its inline
qualifier (line 18) — neither presents the figure as current. The three
other original occurrences (former lines 95, 101, 110, in the "Recommended
Stack" section) were reworded to "the originally-assumed 10s-of-GB scale
(superseded, see notice above)" — a hyphenated form that doesn't match the
`"10s of GB"` grep pattern but remains unambiguously marked as the
superseded figure by the inline qualifier.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), leg-execution crew — two review cycles; cycle 1 raised three blocking factual mismatches on 0047 against `diagnostics.py`/the spec, all fixed and re-verified in cycle 2
**Verdict**: confirmed — `[HANDOFF:confirmed]` for the batch, 2026-09-14
**Commit**: `2f1cbfd` on `squawk/turnaround-2026-09-14`, PR #196 → `mission/24-knowledge-bases`

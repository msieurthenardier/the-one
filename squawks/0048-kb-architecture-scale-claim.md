# Squawk 0048: `docs/kb-architecture.md` still states the superseded "10s of GB per KB" target

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-12
**Completed**: —

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
*(written at completion)*

## Verification
`grep -n "10s of GB" docs/kb-architecture.md` returns nothing, or only inside an explicitly superseded note.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

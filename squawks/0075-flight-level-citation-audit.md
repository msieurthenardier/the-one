# Squawk 0075: Require a Citation Audit in the flight spec, not only in leg specs

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-09-18

## Report

Leg specs in this project carry a **Citation Audit** table — one row per code
citation, each with `file:symbol` and a verified mark. Flight specs do not.
The flight spec is where design decisions assert code mechanics, and it is
where this project's spec defects concentrate.

Flight 5's evidence: of eight high-severity findings across three Architect
cycles, **five were claims about code the spec asserted without re-reading**
— `UsearchStore.query` visibly taking `entry.lock`; a plain `asyncio.gather`
being unable to produce the specified degraded result; `_search_tools.py`
lacking three mechanisms DD-7 described; `kb_id` being client-supplied so a
6-character prefix is not unique; `SearchTools.__init__`'s `source_index or
{}` falsy-binding an empty dict. Each is a five-minute read, and the files
were all listed as read at flight start — so these were assertions made from
*memory* of a read.

Both legs, which do carry audits, shipped differently: Leg 1 with zero
design-review highs, Leg 2 with zero deviations. In both cases the reviewer
re-checked the audit rows rather than trusting them.

**Proposed**: `.flightops/ARTIFACTS.md`'s flight-spec format gains a Citation
Audit section, required before the first Architect cycle — one row per design
decision asserting a code mechanism (signature, control flow, exception type,
mutability, cardinality), each with `file:symbol` and verified/unverified.
The design-review prompt gains an instruction to spot-check it rather than
trust it.

Worth also raising upstream as a plugin-level suggestion, since the asymmetry
(leg template has one, flight template does not) is in the methodology rather
than this project's customisation.

## Evidence

`missions/24-knowledge-bases/flights/05-agent-query/flight-log.md`, "Design
Review Cycles": cycle 1 findings 1–3, cycle 2 findings 3–4.

`missions/24-knowledge-bases/flights/05-agent-query/legs/01-retrieval-and-fusion.md`
and `.../legs/02-kb-tools-gate-and-discovery.md` — both carry `## Citation
Audit`; `.../flight.md` does not.

## Corrective Action

Checked how the leg-spec format documents its Citation Audit before mirroring
it, as instructed. Finding: `.flightops/ARTIFACTS.md`'s Leg format template
does **not** itself document a Citation Audit section — the convention exists
only in practice, consistently, across actual leg spec files (e.g.
`missions/24-knowledge-bases/flights/05-agent-query/legs/01-retrieval-and-fusion.md`'s
`## Citation Audit`: an intro line naming the working-tree commit, then a
`| Citation | Status |` table with `file:symbol` rows). Mirrored that observed
shape rather than inventing a new one, since it's the real, working
convention this project already uses.

Changes:

1. `.flightops/ARTIFACTS.md` — added a `### Citation Audit` subsection to the
   Flight format's Pre-Flight block, directly after Design Decisions and
   before Prerequisites (the audit covers the Design Decisions above it, and
   needs to be filled before the flight moves toward Prerequisites/legs). Same
   table shape as the leg convention: intro line pinning the verified
   working-tree commit, then `| Citation | Status |` with `file:symbol` rows
   and a `verified | unverified` mark, scoped explicitly to design decisions
   asserting a code mechanism (signature, control flow, exception type,
   mutability, cardinality) per the squawk's wording. Added a matching line to
   the Pre-Flight Checklist so it's gated the same way the other
   pre-Architect-cycle items are.
2. `.flightops/agent-crews/flight-design.md` — added item 9 to the Architect's
   "Review Flight Design" Evaluate list: spot-check a sample of Citation Audit
   rows against the real codebase rather than trusting the `verified` marks,
   naming the same mechanism categories (signature/control-flow/exception
   type/mutability/cardinality) so the spot-check has a checklist rather than
   being vague.

Did not add a Citation Audit section to the Leg format template itself — that
gap (real leg files use the convention, the documented template doesn't) is
real but is not what this squawk asked for; fixing it would be a second,
unrequested doc change outside the reported surface, so it's left as a
documentation gap to raise separately rather than folded in here.

## Verification

- Confirmed via `grep -rln "## Citation Audit" missions/` that the mirrored
  shape is the actual, widely-used convention (present in dozens of existing
  leg specs across multiple missions), not a one-off.
- Confirmed via `grep -n -i citation .flightops/ARTIFACTS.md
  .flightops/agent-crews/*.md` (before editing) that no prior documentation of
  the shape existed anywhere in `.flightops/`, which is why the shape was
  sourced from real leg files rather than from `ARTIFACTS.md`'s own Leg
  section.
- `git diff --stat -- .flightops` shows only the two intended files changed,
  additive only.
- Grepped the diff for machine usernames / absolute home paths — none
  introduced.
- Expected effect (observable on the next flight): the flight spec produced
  during `/mission-control:flight` carries a `### Citation Audit` table
  before the first Architect cycle, and the Architect's review output cites
  spot-checking specific rows rather than accepting the table at face value.

## Sign-Off

**Reviewer**: batch Reviewer agent (**Sonnet** tier — the diff touches the encryption-rotation endpoint and a dependency floor for a package inside the shipped frozen closure, both security-sensitive surfaces per `.flightops/agent-crews/leg-execution.md`, even though every change is comment-, doc- or version-only)
**Verdict**: confirmed
**Commit**: `d76d173`

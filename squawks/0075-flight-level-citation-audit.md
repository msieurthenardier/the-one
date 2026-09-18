# Squawk 0075: Require a Citation Audit in the flight spec, not only in leg specs

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

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

*(written at completion)*

## Verification

*(written at completion — expected: the next flight spec carries the table
and its design review cites having checked it)*

## Sign-Off

*(written at completion)*

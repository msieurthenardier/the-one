# Squawk 0074: Make the supersession sweep a standing instruction, not a per-flight rediscovery

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

## Report

A rule gets corrected in one place and the superseded version is left
**upstream of it**, where a Developer reading top-to-bottom meets it first.
This has now produced findings in three consecutive flights.

- **Flight 3** — the `pending → pending` collision fixed for folders in
  cycle 1 reappeared for files in cycle 2; the drain exit condition fixed in
  cycle 2 broke again in the cycle-3 rewrite.
- **Flight 4** — a variant (stale count in a test comment; stale citation).
- **Flight 5, twice** — DD-1's numbered "authoritative ordering" still
  specified the cancelled `asyncio.wait_for` after a later bullet replaced
  it; Leg 2's AC-7 still specified the `kb_id[:6]` discriminator after AC-9
  replaced it with a fixed-length hash. Both caught only by a reviewer
  reading in Developer order rather than author order.

**Flight 3's debrief already prescribed the fix** and it was never converted
into a standing instruction, which is exactly why Flights 4 and 5 hit it
again. That decay is the reason this is a squawk rather than another
recommendation.

Three changes, all to `.flightops/` methodology docs:

1. **Supersession sweep.** Every correction names the superseded literal
   token; the disposition is not complete until a grep for that token across
   the artifact set (flight spec + leg specs + behavior specs) returns zero.
   Both Flight 5 instances were single-token greps (`wait_for`,
   `kb_id[:6]`). Optionally a short "Superseded Rules" ledger at the foot of
   the spec (old token → new rule → swept) so the next reviewer can audit it
   in seconds.
2. **One normative home per rule.** A rule that has already produced a review
   finding gets exactly one code-shaped authoritative statement; every other
   mention is a pointer, never a paraphrase. Restating DD-3 as pseudocode
   ended an ambiguity that three prose revisions had not.
3. **Read-in-Developer-order** as a named review pass in the reviewer crew
   prompt: read the numbered ACs and order-of-work top to bottom,
   implementing mentally, before reading the rationale prose.

Note the cautionary detail from Flight 5: the precedence clause that elevated
the stale text ("this numbered list is the authoritative ordering") was added
*to remove* ambiguity. A precedence clause is only safe when the
authoritative block is the sole statement of the rule.

## Evidence

Flight 3 debrief, verbatim: *"Both times the fix was local when the rule was
general. When a review finds a transition-table or loop-exit defect, state
the general rule in the DD and grep the spec for every sibling site before
the next pass."*

Flight 5 flight-log, "Design Review Cycles": Architect cycle 3 finding 1;
Leg 2 cycle 2 finding 1.

## Corrective Action

*(written at completion)*

## Verification

*(written at completion — expected: the next flight's design review can cite
the sweep as performed, with the superseded token named and grepped to zero)*

## Sign-Off

*(written at completion)*

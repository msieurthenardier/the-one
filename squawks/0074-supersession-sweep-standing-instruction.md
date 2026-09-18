# Squawk 0074: Make the supersession sweep a standing instruction, not a per-flight rediscovery

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-09-18

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

Three changes, split by kind rather than co-located, per the squawk's own
framing (authoring/correction rule vs. reviewer instruction):

1. **Supersession sweep + one normative home per rule** — added as a new
   "Correcting a Rule (Supersession Sweep)" subsection under `.flightops/
   FLIGHT_OPERATIONS.md`'s existing "Reviewing Artifacts" section (right
   after its numbered steps, before "Code Review Gate"). That section is
   already the standing instruction for *making a correction to an
   artifact*, which is exactly when this discipline applies — so it
   extends an existing home rather than creating a new top-level section.
   Four numbered points: name the superseded literal token; grep it to
   zero across the artifact set (flight spec + leg specs + behavior
   specs); one code-shaped authoritative statement per already-corrected
   rule, everything else a pointer; and the precedence-clause caution from
   Flight 5 (a "this list is authoritative" clause is only safe once the
   sweep confirms no stale duplicate remains to be elevated).
2. **Read in Developer order** — added as a named pass at the top of both
   design-review prompts, since that's where Flight 5's two catches
   actually happened (DD-1 at flight review, Leg 2's AC-7 at leg review):
   `.flightops/agent-crews/flight-design.md`'s Architect "Review Flight
   Design" prompt (read the numbered Design Decisions + Legs list top to
   bottom before the rationale) and `.flightops/agent-crews/
   leg-execution.md`'s Developer "Review Leg Design" prompt (read the
   numbered Acceptance Criteria + Implementation Guidance steps top to
   bottom before Context). Left the post-implementation code-review
   prompts (`Reviewer: Review`, `Accessibility Reviewer`) untouched — the
   evidence is specifically about spec review catching stale text before
   implementation starts, not about reviewing a diff.

`.flightops/ARTIFACTS.md` was read as a candidate but not touched for this
squawk — its "Conventions" section documents artifact-format rules, not
review-time behavior, so the correction-workflow addition belongs in
FLIGHT_OPERATIONS.md instead.

## Verification

- Confirmed the destination sections exist and are the right shape by
  reading all four candidate files in full before editing (`FLIGHT_OPERATIONS.md`,
  `ARTIFACTS.md`, `agent-crews/flight-design.md`, `agent-crews/leg-execution.md`).
- `git diff --stat -- .flightops` shows only additive changes to the three
  targeted files (no other file touched).
- Grepped the diff for machine usernames / absolute home paths — none
  introduced.
- The new text is itself an instance of the rule it states: the
  superseded tokens from Flight 5 (`asyncio.wait_for`, `kb_id[:6]`) are
  used only as illustrative examples of "a literal token," not restated
  as live guidance anywhere else in `.flightops/`.
- Expected effect (observable on the next flight): the Architect and
  Developer design-review prompts now name "Read in Developer order" as
  an explicit first pass, and a correction made during "Reviewing
  Artifacts" is expected to cite the token it swept and the grep that
  returned zero.

## Sign-Off

**Reviewer**: batch Reviewer agent (**Sonnet** tier — the diff touches the encryption-rotation endpoint and a dependency floor for a package inside the shipped frozen closure, both security-sensitive surfaces per `.flightops/agent-crews/leg-execution.md`, even though every change is comment-, doc- or version-only)
**Verdict**: confirmed
**Commit**: `PENDING`

# Squawk 0079: The Leg format template does not document the Citation Audit it universally uses

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-18
**Completed**: —

## Report

Found while completing squawk 0075 (which added a Citation Audit to the
**Flight** format). The Developer went to mirror the Leg format's
documentation of the same section and discovered there isn't any: the
convention exists **only in practice**, propagated by copying from previous
leg specs.

`grep -rln "## Citation Audit" missions/` returns **300 leg spec files**. The
`### Leg` format block in `.flightops/ARTIFACTS.md` documents no such
section.

This is worth closing for the same reason 0075 was: a convention carried only
by precedent drifts silently. A leg author who starts from the template
rather than from a sibling file omits it and nothing flags the omission — and
the audit is precisely the instrument that made both of Flight 5's legs ship
clean (Leg 1 with zero design-review highs, Leg 2 with zero deviations).

Deliberately **not** folded into 0075's turnaround: the Developer working
that squawk correctly declined it as unrequested scope and flagged it
instead, which is the behaviour the scope gate exists to produce. Logging it
separately rather than quietly re-expanding that batch.

## Evidence

`.flightops/ARTIFACTS.md` — `### Citation Audit` appears only under the
Flight format (added by squawk 0075); the `### Leg` format block has no
equivalent.

`grep -rln "## Citation Audit" missions/ | wc -l` → 300.

Squawk 0075's `## Corrective Action`, which records the discrepancy: the
Developer mirrored the real observed convention from actual leg files rather
than a template, because no template documentation existed to mirror.

## Corrective Action

*(written at completion — expected: document the Citation Audit section in
`.flightops/ARTIFACTS.md`'s Leg format, matching the shape 300 existing leg
specs already use, plus the Post-Completion Checklist line if appropriate)*

## Verification

*(written at completion — expected: a leg authored from the template alone
carries the section)*

## Sign-Off

*(written at completion)*

# Squawk 0079: The Leg format template does not document the Citation Audit it universally uses

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-18
**Completed**: 2026-11-03

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

Added a `## Citation Audit` section (after Files Affected, where existing leg specs put it)
to the Leg format in `.flightops/ARTIFACTS.md`. `.flightops/README.md` lists ARTIFACTS.md as
not synced ("customize freely"), so a project edit is expected. The Leg format has no
checklist, so no checklist line was added.

## Verification

Read-back: a leg authored from the template carries the section, in the shape
`missions/33-routines/.../04-routine-evals.md` uses.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

# Mission Debrief: Local API Authentication

**Date**: 2026-08-08
**Mission**: [Local API Authentication](mission.md)
**Status**: completed
**Duration**: 2026-08-05 – 2026-08-08
**Flights Completed**: 1 of 1

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|---|---|---|
| Every request path refused without a credential | met | All methods, WS upgrades, `/static`; one exemption (`/api/live`) |
| Operator reaches the UI with no credential handling | met | Observed on the real pinned webview (HAT) |
| Session survives a server restart | met | A new process accepted the prior process's cookie |
| Every non-browser caller authenticates | **partial** | Desktop shell and browser lane verified. AIAT lane, `make verify-serving`, CI packaged-smoke and the behavior-test runner were **code-changed but never executed** |
| Credential owner-only, no world-readable window | met | `0600` via single-syscall `O_EXCL` |
| Operator can rotate; old sessions stop working | met | `200 → rotate → 401`, server still running |
| Authorization against an identified caller | met | Second credential source honoured with no change to gating logic |
| Documented security model revised | met | F3 Decision 10 revised, not deleted; states what it does *not* protect against |
| Suites pass with auth enforced | met | 4252 unit; browser at parity with a measured baseline |

**Eight of nine met; one partial.** The partial is the honest headline: roughly
half the non-browser caller inventory is verified by code inspection, not by a
green run. Anyone treating this mission as "done, move on" should know that.

### Overall Outcome

The mission achieved its outcome, and the outcome was still the right goal at the
end. A local API that exposed `shell`/`python_exec` and stored OAuth tokens now
requires a credential only the operator's OS account can read — without the
operator ever handling that credential.

The outcome statement's honesty held up under pressure. It always said what was
*not* being bought: a process running as the operator retains full access. That
framing is what made issue #169 (world-readable `the-one.db`) legible as a gap
rather than a contradiction.

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| 01 Authenticated Local API End-to-End | completed | Credential primitive, ASGI gate, two-credential handoff design, stateless HMAC sessions, CLI rotation, full caller migration, security-model revision |

## What Went Well

**Plumb-then-flip.** Credentialing the entire harness with the gate *off*, then
flipping enforcement in a tiny separate leg, converted a would-be long red window
into a 125-failure run with one traceable root cause. This is the mission's most
transferable execution pattern.

**Risk-tiered design review caught four things no test would have** — the
`SameSite=Lax` hole, the session-binding gap that would have failed restart
survival, the WebSocket-cannot-send-headers constraint, and the Windows CI lane
registration. Two of those would have shipped as silent security weaknesses.

**Independent review caught a broken flagship criterion.** The launcher never
performed the handoff; `the-one app` would have shown a 401. Nothing was red,
because no test asserted on URL *content*.

**The HAT earned its setup cost.** It required installing GTK/cairo system deps
to reach the pinned webview at all — and then found a defect (a 401 message
indistinguishable from a bad provider API key, which sent the operator hunting
through two providers) and confirmed a fix that was otherwise unit-verified only.

## What Could Be Improved

### Planning

**This should have been two flights, and the first should have been
reconnaissance.** The Architect's assessment is sharper than the flight's own
self-diagnosis: the problem was not merely "two risk clusters," it was that
*counting the migration surface* was treated as an estimate rather than a
deliverable. Planning assumed one `app_clean` fixture; ten existed. It assumed
DD10's "TestClient and direct-`httpx`" covered the unit harness; 28
`ASGITransport` fixtures matched neither term. A survey flight whose output is a
verified call-graph count would have gated the migration flight's leg count
*before* code moved, instead of the count growing under review three times.

**One mission, one flight, eight legs is a structural smell** — against a
methodology guideline of one-to-four. The flight spec predicted this in writing
and then proceeded anyway.

### Technical

**The mission left two sibling files with different security postures for the
same operation, knowingly.** DD2 read `encryption.py`, identified its
write-then-`chmod` pattern as having a world-readable window, wrote "do not copy
that one" — and did not fix it. So `api_credential.py` and `encryption.py` both
create an owner-only secret file at a stable path, by different methods, one of
which is known-weaker. A contributor grepping for "how does this codebase write a
secret file" has even odds of copying the wrong one. *Noticing an inconsistency
and leaving it is worse than not noticing*, because the record now shows it was
considered.

**Nothing carries that forward.** `SECURITY-MODEL.md` documents the current
posture accurately but does not flag it, and issue #170 touches `encryption.key`
directly.

**The harness accumulated debt the mission diagnosed and then repeated.** Squawk
0001 exists because this mission — whose central lesson was that duplication
makes callers un-findable — created three copies of the same header helper in its
own harness. `tests/browser/conftest.py` is now 639 lines owning six distinct
jobs.

### Process

**Concluding from n≈1 about an intermittent phenomenon, three times.** Each
conclusion was stated to the operator with more confidence than the evidence
supported; two were written into artifacts and one into a commit message as
established fact. The decisive experiment cost 14 minutes and was available from
the first use of the word "flake."

**Formatting that misleads is a real defect, and it happened twice.** Corrections
appended chronologically buried the retraction 56 lines below three superseded
conclusions — and a debrief reader duly reported the retracted finding as fact.
Then the flight debrief's action list ticked two items that had only been *filed*
as squawks, and a reader duly read the debt as closed. Both are fixed; the pattern
is worth naming. **An artifact that is accurate but misorganized is not honest.**

## Lessons Learned

**Survey by call graph, not by pattern.** Pattern-shaped search cannot find a
duplicate that does not share the searched-for token — and every one of the five
missed caller categories was a duplicate of something already surveyed.

**A design decision that names an intended caller is not a leg acceptance
criterion.** `mint_handoff_credential()` was built with a docstring naming the
launcher, and "the function exists" was treated as "the caller uses it."

**Precedent-grounded decisions outperformed principle-grounded ones.** Every DD
citing an exact `file:line` precedent survived untouched; the ones argued from
abstraction are precisely those rescued mid-flight.

**For anything intermittent, n=1 cannot separate signal from luck — in either
direction.** Measure a paired baseline *before* attributing.

## Methodology Feedback

1. **Add a call-graph reconnaissance step with required counts.** Flight design
   should enumerate constructions reaching the target boundary by *what object
   they wrap*, and record a count wherever a leg estimate depends on it.
2. **Standardize plumb-then-flip** for cross-cutting migration-plus-enforcement.
3. **Require a wiring assertion** wherever a design decision names a consumer.
4. **Distinguish "filed" from "fixed" in debrief checklists** — this skill's own
   Phase 6 converts action items to squawks, which is exactly where the ambiguity
   arises.
5. **The squawk qualification gate worked.** A proposed squawk was rejected for
   failing two criteria rather than logged anyway, and became issue #169.

## Action Items

> A ticked box means done. Filing relocates work; it does not close it.

- [ ] Close the partial criterion — execute the AIAT lane, `make verify-serving`,
      CI packaged-smoke, and run `/behavior-test local-api-auth-session-lifecycle`
- [ ] Record the `encryption.py` / `api_credential.py` inconsistency as
      forward-looking guidance before #170 starts
- [ ] Squawks 0001 and 0002 (`open`)
- [ ] Issues #169 (db mode) and #170 (passphrase KEK) — #170 must be planned
      *reading* DD2/DD12/LD3 first; it amends a decision this mission defended
- [ ] Test `_select_port` with two legitimate instances on separate data dirs —
      becomes the normal case under #166
- [ ] Carry forward: the mint endpoint deliberately has no source restriction.
      Harmless today; live the moment a second `CredentialSource` exists
- [ ] Carry forward: DD8's seam is credential-lookup, **not** session-binding
      (LD4); sessions have no idle expiry (LD3/LD5)
- [ ] Consider `/routine-maintenance` next — the harness debt (squawk 0001,
      `conftest.py` size, 28 unconsolidated fixtures) is its natural input

## Interview Note

The Architect interview was conducted and is woven throughout. **The human
interview was posed but not answered** — three questions on autonomy and
intervention, on how confidently I reported uncertainty, and on whether the HAT
justified its setup cost. Those answers would sharpen the process findings
above, particularly the n≈1 lesson, whose most useful form may be about
*reporting* rather than measurement. This section is left open rather than
filled in speculatively.

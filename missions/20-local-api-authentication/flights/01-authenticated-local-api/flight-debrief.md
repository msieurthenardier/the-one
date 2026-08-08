# Flight Debrief: Authenticated Local API End-to-End

**Date**: 2026-08-08
**Flight**: [Authenticated Local API End-to-End](flight.md)
**Status**: landed
**Duration**: 2026-08-05 – 2026-08-08
**Legs Completed**: 8 of 8 (planned as 7; split to 8 mid-flight)

## Outcome Assessment

### Objectives Achieved

The local HTTP/WebSocket API went from fully unauthenticated to credential-gated,
with the operator never handling a credential by hand. Verified on the real
pinned-webview desktop path, not only in test harnesses: the handoff chain
(`GET /?handoff=… → 302 → GET / → 200 → WebSocket [accepted]`) was observed in a
live server log, and the accepted socket is load-bearing evidence — a native
browser `WebSocket` cannot send an `Authorization` header, so it could only have
connected via a genuinely established session cookie.

### Mission Criteria Advanced

Six of nine criteria fully met and observed. Three were deliberately left
**unticked** rather than assumed:

| Criterion | State |
|---|---|
| Every path refused without a credential | met |
| Operator reaches UI with no credential handling | met (HAT) |
| Session survives a server restart | met (new process accepted prior process's cookie) |
| **Every non-browser caller authenticates** | **partial** — desktop shell and browser lane verified; the AIAT lane, `make verify-serving`, CI packaged-smoke and the behavior-test runner were code-changed but **never executed** |
| Credential owner-only, no world-readable window | met |
| Rotation invalidates old sessions | met (200 → rotate → 401, server still running) |
| Authorization against an identified caller | met |
| Documented security model revised | met |
| Suites pass with auth enforced | met (4252 unit; browser at parity with baseline) |

The partial criterion is the honest headline: a substantial slice of the caller
inventory is verified by inspection only. The behavior-test spec authored *for
this flight* was never run.

## What Went Well

**Plumb-then-flip.** Splitting `enforce-and-migrate-harness` into
`harness-credential-plumbing` (credential everything with the gate **off**, suite
stays green) and `enforce-gate` (one `add_middleware` call) was the single best
execution decision. It converted what would have been a long red window with
migration bugs and enforcement bugs tangled together into a 125-failure run that
resolved to **one** root cause. This should be standard practice for any
cross-cutting migration-plus-enforcement work.

**Risk-tiered design review paid for itself repeatedly** — and every catch was
something no test would have found:

- `SameSite=Lax`, which would have reopened the exact GET-side rebinding hole the
  mission exists to close, once a session existed
- the session-binding gap that would have failed restart survival with no
  acceptance criterion able to detect it
- a native `WebSocket` cannot send an `Authorization` header — which invalidated
  the harness's entire chosen strategy before it reached the flip
- the Windows CI lane registration, without which the flight's highest-risk
  platform property would have gone unverified until a red `main`

**Independent flight-end review caught a broken flagship criterion.** The
launcher never performed the handoff at all; `the-one app` would have shown a
401. No unit test asserted on URL *content*, so nothing was red. Without that
review this ships broken.

**Precedent-grounded decisions outperformed principle-grounded ones.** DD2 and
DD3 cited exact `file:line` precedent and needed no revision. The decisions
argued from abstraction — DD7's session handling, the `SameSite` default — are
precisely the ones rescued mid-flight. That correlation is actionable.

## What Could Be Improved

### Process

**Concluding from n≈1 about an intermittent phenomenon — three times.** Browser
flakiness produced three successive wrong conclusions ("a flake" → "machine
load" → "the flight caused it"), each stated with more confidence than the
evidence supported, two written into artifacts and one into a commit message as
established fact. The decisive experiment — paired baseline runs with
dependencies held constant — cost 14 minutes and was available the first time
the word "flake" was used. Final answer: **pre-existing intermittency, not
caused by this flight** (baseline 2/2/0 failures; post-flight 0/2/0).

**Corrections appended chronologically buried the conclusion.** Keeping wrong
turns visible was right; ordering them first was not. The retraction sat 56 lines
below three superseded conclusions, and a debrief reader consequently reported
the retracted answer as fact. Fixed by moving the conclusion to the top of the
section. *A correction must lead; the record of being wrong belongs below it.*

**Deferred debt did not land anywhere durable.** The 28-fixture consolidation is
named in two leg artifacts and appears in no Known Issues, no squawk — nothing
outliving the flight. "Out of scope for this leg" is not a home.

### Technical

**Five caller categories were discovered during execution, not planning** — and
every survey asked *"where is this pattern written?"* instead of *"who calls this
API?"*:

| Survey key | Category missed |
|---|---|
| `grep subprocess.Popen` | callers importing the shared spawn helper |
| enumerate fixtures + seeders | 52 inline `httpx` sites (125 failures) |
| DD10's "TestClient and direct-`httpx`" | 28 `ASGITransport` fixtures |
| the credentialed `page` fixture | 2 local `browser.new_context` duplicates |
| Leg 5's httpx call-site survey | the launcher's window URL — a string handed to pywebview, not an HTTP call |

In every case the missed category was a **duplicate** of something already
surveyed — which is exactly why grep could not see it — and the fix was always
*collapse the duplicate onto the shared path*, never *patch the missed caller*.

**The flight then reproduced this failure mode in its own harness.** There are
now three near-identical implementations of "resolve a credential for a base_url
and build an Authorization header": `_credential_registry.py::auth_headers_for`,
`conftest.py::_auth_headers_for`, and `seeders.py::_auth_headers`. Their
docstrings cross-reference each other, so the duplication is known and
deliberate (avoiding a circular import) — but it is the same shape that caused
every missed-caller category above.

**`tests/browser/conftest.py` now does too much**: +196 net lines (~55% growth,
640 total), owning subprocess spawning, credential file writing, a registry
bridge, Playwright lifecycle, **two** handoff-exchange implementations, and six
layered app fixtures.

**The 52 explicitly-credentialed inline sites are a permanent tax**, not a
one-time cost. Rejecting the global `httpx` monkeypatch was correct — it would
have silently credentialed tests asserting 401 refusals, the very tests this
mission needs honest — but nothing enforces the manual pattern for a future test
author.

**"Sub-millisecond" is asserted, never measured.** The gate's per-request cost is
almost certainly fine (one `stat()` plus an HMAC over ~16 bytes, against +13
seconds on a 13.5-minute suite). But that claim lives in a docstring with no
benchmark — and the flight's own three-round attribution failure was about this
exact mechanism, which is the strongest possible argument for measuring rather
than reasoning.

**DD11's "strictly better" oversells.** Credential-based instance classification
trades a version-mismatch failure mode for a *different-data-dir* one. Two
legitimate instances on separate profiles were never tested.

### Documentation

`SECURITY-MODEL.md` was revised well — it states what the posture does *not*
protect against. But issue #169 surfaced immediately after: `the-one.db` is mode
644 with plaintext chat history, so "removes other local accounts from the threat
surface" is only true of the API, not of the data directory.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| 7 legs → 8 (mid-flight split) | design review counted the real migration surface | **Yes** — plumb-then-flip for any migration+enforcement work |
| Second design-review cycle returned "needs rework" | new findings against new material | Yes — escalate to the human, don't loop |
| A squawk was rejected at the gate rather than logged | failed 2 of 4 criteria (design decisions, security surface) | Yes — the gate is the point |
| Behavior-test spec authored but never run | no dev instance until the HAT | No — fix by running it |

## Key Learnings

**Survey by call graph, not by pattern.** Pattern-shaped search cannot find a
duplicate that does not share the searched-for token. Treat existing duplication
as a *prerequisite to consolidate*, not an inconvenience to work around.

**A design decision naming an intended caller is not a leg acceptance
criterion.** `gate-middleware` built `mint_handoff_credential()` with a docstring
naming the launcher and treated "the function exists" as "the caller uses it." No
leg ever owned that wiring. Where a decision says "X consumes Y," some leg's
criteria must assert the wiring.

**For anything intermittent, n=1 cannot distinguish signal from luck — in either
direction.** Measure a paired baseline before attributing, not after.

**Reconnaissance was strong at finding categories and weak at counting within
them.** It caught items the originating issue missed, then assumed one
`app_clean` where ten existed. Require counts, not existence checks, wherever a
leg estimate depends on them.

## Recommendations

1. **Adopt plumb-then-flip** as standard for cross-cutting migration+enforcement.
2. **Add a call-graph reconnaissance step** to flight design: enumerate
   constructions that reach the target boundary by *what object they wrap*, and
   require counts.
3. **Run the behavior test** authored for this flight, and close the three
   unticked criteria by executing the AIAT lane, `verify-serving` and CI smoke
   against a dev instance.
4. **Resolve the deferred debt durably** — the three duplicate `auth_headers`
   helpers, the 28 unconsolidated fixtures, and `conftest.py`'s size.
5. **Benchmark the gate once** rather than asserting its cost.

## Action Items

- [ ] Collapse the three duplicate `auth_headers` implementations into one *(squawk candidate)*
- [ ] Micro-benchmark the gate's per-request cost; replace the docstring assertion with a measured number *(squawk candidate)*
- [ ] Run `/behavior-test local-api-auth-session-lifecycle` against a dev instance
- [ ] Execute the AIAT lane, `make verify-serving` and CI packaged-smoke; close or re-open criterion 4
- [ ] Consolidate the 28 local `client` fixtures — needs design, belongs to a flight
- [ ] Split `tests/browser/conftest.py` — needs design
- [ ] Test `_select_port` with two legitimate instances on different data dirs (DD11 gap)
- [ ] #169 (db mode 0600) and #170 (passphrase KEK) — tracked on GitHub
- [ ] Record for the next auth flight: DD8's seam is a *credential-lookup* seam, **not** a session-binding seam (LD4); sessions have no idle expiry

# Flight Debrief: External Client Access

**Flight**: [External Client Access](./flight.md)
**Mission**: [Agent Self-Configuration](../../mission.md)
**Status**: completed
**Debriefed**: 2026-08-27
**Commits**: `a7daab2` (implementation), `c013d5a` (HAT record) · **PR #174**

## Outcome

The flight met its objective and closed **mission success criterion 10** — an external
client can be granted access scoped to a single agent, withdrawn and reissued without
restarting the platform, with a withdrawn credential stopping immediately. Verified live
in the HAT (8/8 acceptance criteria). With Flight 1 (criteria 1–4, 8, 9) and Flight 2
(5, 6, 7), **all ten mission criteria are now met** — Flight 3 is the last flight of the
mission.

The delivered scope: a distinct `ext_` credential principal (own encrypted store, a
second confined `CredentialSource` on the same `/mcp/self-configuration` mount,
per-principal revoke/rotate), external-write provenance (`source='external'` +
`source_principal`), the field-scoped compare-and-swap closing the direct-write
last-writer-wins clobber, the governance invariant (external principals reach only the
four confined tools), and the operator **External access** Studio panel.

## What Went Well

- **The "Flight 1 already built it" reframe was the flight's central design-correctness
  result.** Reconnaissance classified two work-items `already-satisfied` — the transport
  + confinement + scoping, and the revoke-immediacy *mechanism* — and narrowed the flight
  from the mission text's from-scratch framing to **credential delivery + a distinct
  principal + provenance/concurrency/governance**. The implementation bears this out
  completely: no transport code, no confinement code, and no new immediacy mechanism were
  written. The second `CONFINED_SOURCE_PATHS` entry inherits Flight 1's gate unchanged;
  revoke-immediacy is the same in-memory-registry eviction. Reading what already exists
  before treating a mission-framed "new surface" as new turned a large flight into a
  bounded credential-family addition.
- **The `source_id`-FK-on-the-surface-row refinement collapsed three mechanisms into
  one.** The flight spec sketched an `agent_name` FK plus a re-implemented surface-enabled
  re-check. The Leg 1 designer, reading `manage.disable`/`cascade_delete`/`cascade_rename`
  first, found that keying the store on `source_id REFERENCES mcp_sources(id) ON DELETE
  CASCADE` is strictly better: surface-disable and agent-delete **auto-revoke via FK
  cascade** (governance enforced by the schema, not by teardown code kept in step across
  call-sites); resolution **reuses `_calling_agent`'s existing DD9 refusal** instead of a
  duplicated check; agent-rename is a non-event (row id stable). It also let the store
  drop `revoked_at` (hard-revoke; audit lives in the revision log). This is the
  schema-level answer to Flight 2's "an invariant is only as good as the call-sites you
  surveyed."
- **Faithful `agt_`-template reuse.** `external_credentials.py` mirrors `credentials.py`
  in shape (in-memory registry, constant-time compare, `register_credential_source_once`
  keyed on **actual list membership** so it self-heals across the `_sources` swaps test
  fixtures perform — it even ports the reasoning comment). The repository holds the
  `Encryptor` by reference (post-rotation `install_key()` propagation). Both migrations
  follow their cited precedents (v36 = additive v34 template; v37 = v23 rebuild ceremony).
- **`_resolve_caller_and_agent` put the security refusal in exactly one place.** Both
  `_calling_agent` (reads) and `_calling_principal` (writes) derive from a single helper
  that runs the DD9 surface-enabled refusal once. The flight-end reviewer named this the
  key cross-leg correctness point: external routing AND the DD9 gate cover both read and
  write tools *by construction*, not by parallel enforcement.
- **Design-review-before-code caught real completeness gaps again — a second confirming
  data point after Flight 2.** Each high-risk leg's design review found 2–3 gaps invisible
  to happy-path tests and citation-dense specs alike: Leg 1's **mint-gate-on-`enabled`**
  (the original `find_surface_row is not None` gate would have minted a dormant credential
  against an orphaned surface that silently starts working on re-attach — a latent
  privilege bug); the **standalone-bearer presentation path** (an `ext_` bearer has no
  surface row, so the AC6/8/9 tests needed a synthetic `MCPSource`); Leg 2's **migration
  false-pass guard** (a stamp-only rewind short-circuits the `source_principal`-presence
  guard and exercises nothing); and the **provenance touch-point enumeration**, which this
  time was done as an *authoring* step (see Process).
- **Governance by construction, pinned with a test.** The `ext_` 403 on the operator
  control plane is an existing property of confinement (every `/api/…` route is
  off-mount); Leg 2 added no denial list, just a parametrized test across **8 operator
  routes** plus a projection test that no approval-mode key leaks. Safety is structural;
  the test prevents erosion.
- **Non-vacuous tests.** The CAS other-field-non-clobber test seeds both fields, performs
  a real concurrent whole-row write to one, runs the CAS on the other, and asserts the
  concurrent value survived; the stale test drifts the field between base-capture and the
  CAS, then asserts `effective=="stale"`, the store shows the concurrent value, and **no
  revision row was logged**; the secret-at-rest test reads the raw column. Negative paths
  asserted, not assumed.
- **The HAT found zero behavioral defects** — all 8 ACs passed against a real loopback MCP
  client, and the only finding was one deferred UX polish item (history rows don't label
  `source`). The autonomous legs got the behavior right; the HAT confirmed it end-to-end.

## What Could Be Improved

### Process

- **Citation-density-is-not-design-completeness held again — but with a real
  improvement.** The three specs were unusually clear and each carried a verified Citation
  Audit, yet review still made four material corrections before code (mint-gate,
  standalone-bearer, migration false-pass, and the provenance widening). That is the
  system working, not a failure. The genuine improvement over Flight 2: the
  **five/six-touch-point provenance enumeration was done as an authoring step in the DD**,
  not discovered as a review finding — exactly the promotion Flight 2's debrief
  recommended ("treat 'enumerate the value/state space and the write/teardown call-sites'
  as an authoring step, not a review finding"). Applying a prior debrief's recommendation
  and seeing it pay off is the feedback loop closing.
- **The Developer crew stalled on final wrap-up on both Leg 2 and Leg 3.** Each ended its
  turn saying it was "waiting on the Monitor" for a `make test-unit` result that does not
  resolve within a spawned agent's turn — leaving the leg `in-flight`, no flight-log
  entry, and the test result unconfirmed. The Flight Director completed the bookkeeping and
  **independently verified the suite each time** (the Leg 2 corroboration run is the clean
  isolated metric below). This recurred twice, the second time despite an explicit
  spawn-prompt instruction not to end while a run was pending — a repeatable crew
  "Implement"-prompt × Monitor-handoff friction, not a code issue. See Recommendations.

### Technical

All items below are **documented in code** and accepted at operator/single-writer scale;
they are named here as standing debt, not surprises.

- **Whole-row last-writer-wins now has four write consumers; the CAS closes only the two
  direct-write ones.** `SQLiteAgentStore.save` is a full-row upsert with no version guard.
  The field-scoped `compare_and_set_field` guards the direct-write branch of
  `_apply_revision` for both principals (agent and external), but the operator **approve**
  path, **restore**, and **Studio edit** (`PUT /api/agents/{name}`) remain whole-row
  writers. Approve is mutually exclusive with direct writes (the flag gates
  queued-vs-direct), but a **Studio edit runs in any mode and can still clobber a
  freshly-applied external direct write on the *other* field**. This is precisely the debt
  Flight 2's debrief predicted would "become a real concurrency exposure the moment a
  second live principal writes … i.e. Flight 3." Flight 3 halved it (closed the writer it
  introduced) and named the residual; it did not generalize `save` to an etag. This debt
  has now been deferred across three consecutive debriefs — the mission debrief should
  convert it from a perpetual "open question" into a **conscious deferral with a named
  trigger** (below).
- **The residual DD5 clobber has no red test.** Because Studio-edit-vs-external-direct on
  different fields is *accepted* behavior at single-operator scale rather than a fixed
  invariant, there is no regression test pinning the loss. Defensible, but a future flight
  closing it won't have a red test to turn green — worth an explicit xfail-style marker if
  the etag decision is taken.
- **The CAS/append crash window persists** (carried from Flight 2, unchanged). The CAS
  self-commits, so the field write and the revision-log `append` are not one transaction.
  Ordered so the worse failure (logged-but-unpersisted) can't occur; commented; only the
  no-orphan-log direction is tested.
- **App-level pending-dedup remains a SELECT-then-write, not a schema invariant.** Flight 2
  named the optional partial unique index `(agent_name, field) WHERE status='pending'` as a
  Flight-3 input; Flight 3 did not add it. `upsert_pending_revision`'s UPDATE branch now
  also refreshes `source`/`source_principal` (a re-propose by a different principal records
  the latest proposer — correct), but the TOCTOU is unchanged. An external principal
  honoring approval mode can now land in the pending queue, so the surface is marginally
  more real than at Flight 2 — a conscious carry-forward, not silently dropped.
- **Provenance is captured but not surfaced.** The revision-history UI does not visibly
  label `self` vs `external`; `GET …/revisions` returns `source`/`source_principal` (via
  `model_dump()`), but Studio doesn't render them. Now that provenance is load-bearing for
  "which external system tuned this agent," data-only audit is a real UX gap. (Squawk
  candidate — see Action Items.)

### Documentation

In good shape. The deferred `SECURITY-MODEL.md` (+83) and `agents.md` (+12) external-
credential sections were written in the flight-end fix pass and verified present: the
distinct `ext_` principal, per-principal revoke/rotate vs the operator's rotate-everything,
FK-cascade auto-revoke (DD9), the encrypted-at-rest store, the governance invariant, and
provenance tagging. Testid registry updated (+15). No gap.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Store keyed on the surface `source_id` FK (ON DELETE CASCADE), not the flight's sketched `agent_name` FK | Reading `manage.disable`/`cascade_delete`/`cascade_rename` first showed the FK cascade auto-revokes and reuses the DD9 refusal — three mechanisms collapse to one | **Yes** — "read the lifecycle code before locking the schema"; enforce lifecycle invariants at the schema, not surveyed call-sites |
| `_resolve_caller_and_agent` extracted at Leg 2 design review | Both read and write resolvers must run the DD9 refusal; a single shared helper means the security-critical gate lives in exactly one place | **Yes** — a shared-interface change that adds a second caller should route the security check through one site, not duplicate it |
| v37 rebuild DDL as a single `executescript` (not sequential `conn.execute`) | `PRAGMA foreign_keys=ON/OFF` is a no-op inside an open transaction; sequential-execute left FK enforcement OFF after `ensure_schema` (caught by the pre-existing v21 cascade test) | **Yes** — FK-toggling table-rebuild migrations use `executescript` for the COMMIT boundary (matches the v23 precedent) |
| Five/six provenance touch-points enumerated in the DD, not found at review | Applied Flight 2's recommended promotion of "enumerate the write/state call-sites" to an authoring step | **Yes** — already recommended by Flight 2; Flight 3 confirms it works |
| Metrics captured on an isolated run (585s), not concurrently with other work | Applied Flight 2's "measure on an isolated run" recommendation | **Yes** — already adopted; record the isolated number as the honest baseline |

## Key Learnings

- **Read what already exists before treating a mission-framed "new surface" as
  from-scratch.** The single best call of the flight was reconnaissance classifying the
  transport/scoping/immediacy as `already-satisfied` and reframing the scope. A mission's
  own framing can over-state the remaining work; a code-grounded recon pass is what
  right-sizes the flight.
- **Enforce lifecycle invariants at the schema, not at surveyed call-sites.** The
  `source_id` FK cascade makes "an external credential dies with its surface" true by
  construction — the direct answer to Flight 2's call-site-survey lesson.
- **Design-review-before-code is doctrine for high-risk legs — now two consecutive
  confirming flights.** It found a latent privilege bug, a migration false-pass, a
  non-1:1 test-presentation gap, and a half-threaded model widening, none visible to a
  passing suite. This belongs in the methodology, not per-flight discretion (a mission-
  debrief-level recommendation).
- **Governance by construction beats a denial list.** Extending a confined surface to a
  new principal by reusing the seam + the confinement map added zero enforcement code, and
  a single parametrized test across the operator routes pins it against erosion.

## Test Metrics

**Flight 3 (isolated capture, code frozen at `a7daab2`):** `make test-unit` =
**4507 passed / 10 skipped / 0 failed / 687 deselected in 585.40s (9m45s)**, run with **no
concurrent load** — the clean isolated measurement Flight 2's debrief asked for. New Studio
browser lane **8/8** (`-m browser`); existing self-config browser tests regression-clean
(tab 3/3, history 3/3, queue 5/5).

**Test-count trend (the reliable signal):** Mission-20 baseline ~4252 → Flight 1 **4381**
→ Flight 2 **4447** (+66) → Flight 3 **4507** (+60); skips flat at 10 throughout. Flight 3's
+60 breaks down by leg: **Leg 1 +34** (endpoint/lifecycle + migration + secret-at-rest +
confinement + out-of-process MCPClient), **Leg 2 +26** (v37 migration suite, CAS + provenance
repo tests, surface provenance/approval/stale, the 8-route governance parametrization),
**Leg 3 +0 unit** (its 8 tests are browser-lane, by design).

**Wall-clock — a real trend, but not a per-test regression.** Isolated-to-isolated:
Flight 1 (~370s) → Flight 3 (**585s**) is +215s/+58% on +126 tests (+2.9%). Flight 2's 8:05
(~485s) is *not* a clean comparison (its debrief flagged it as under concurrent load — trust
the count, not the wall-clock). Cause visible in this flight's changes: the growth is
dominated by the *class* of test the surface work keeps adding — the out-of-process MCPClient
tests stand up a **real uvicorn on loopback and perform a real MCP handshake per test**, and
the 18 external-endpoint tests drive the full-app stack. Per-test average (~130ms) is
unremarkable; the wall-clock is carried by a growing tail of real-server integration tests.
**A slow-suite watch item, not a defect** — two more surface flights on this trajectory push
the unit lane past 10 minutes, at which point tiering the loopback-server tests into their
own lane (as the browser tests already are) is worth considering.

## Skill Effectiveness

- **Mission** — the mission's reconnaissance-friendly framing (naming Mission 20's three
  seams and the "already-satisfied" possibility) is what let the recon pass reframe the
  flight. Success criteria were measurable; criterion 10 mapped cleanly to the HAT.
- **Flight** — the flight design's Phase-1b reconnaissance (verifying every source-cited
  item against current code before drafting legs) was the highest-leverage step: it is
  what caught the two `already-satisfied` items. The DD structure held; the one DD revision
  (source_id FK) was a leg-level refinement, correctly not rewritten into the flight
  in-place.
- **Leg** — the risk-tiering was accurate (Legs 1&2 high, Leg 3 low), and the leg-boundary
  bug (ext-routing placed in Leg 2 but needed by Leg 1's end-state) was caught at design
  review and fixed by moving routing into Leg 1 with the overlap *stated*. Acceptance
  criteria were binary and verified.

## Recommendations

1. **Convert the whole-row LWW deferral into an explicit named-trigger decision at the
   mission debrief.** It has been deferred across three flight debriefs; Flight 3 halved it
   and confirmed a live second principal now exists. State the trigger explicitly: the
   first of {a real second human, a multi-principal/non-loopback posture, or multiple
   simultaneous external tuning clients on one agent} forces a row-version/etag on
   `SQLiteAgentStore.save`. Recorded as a trigger, it gets picked up by design, not by a
   production surprise.
2. **Reconcile the mission artifact's success-criteria checkboxes.** All ten criteria are
   met across Flights 1–3, but `mission.md` lines 68–95 are still all `[ ]`. The mission
   debrief should check them against the per-flight record.
3. **Surface revision `source`/provenance in the history UI.** Bounded presentational
   addition over existing API data; now load-bearing for external-tuning audit. (Action
   Items — squawk candidate.)
4. **Standardize the emergent patterns at the mission level:** the source-row-FK-cascade
   for lifecycle-coupled child records; the field-scoped CAS as the atomic direct-write
   guard; the confined second `CredentialSource`; and **design-review-before-code as
   doctrine for high-risk legs** (Flight 2 recommended it; Flight 3 is the confirming
   second data point). Value-node restore (Flight 2) still stands.
5. **Slow-suite watch:** record 585s as the honest isolated Flight-3 baseline; if the next
   surface flight pushes the unit lane toward 10 minutes, tier the loopback-server
   integration tests into their own lane.
6. **Crew "Implement" prompt × Monitor friction:** the Developer prompt should not end a
   turn blocked on an async `Monitor` test result it cannot await within the turn — it
   should run the suite synchronously and report the result before yielding. A
   methodology/crew-file fix, not a code fix.

## Action Items

- **Squawk [0008]** (`squawks/0008-revision-history-mislabels-external-source.md`): the
  revision-history UI mislabels `external` revisions as "self-revised" (`self-configuration-tab.js:1011`); render `external` distinctly. Bounded, presentational, no design fork.
- **Mission-debrief inputs (design work — not squawks):** the named-trigger LWW/etag
  decision; the pending-dedup partial unique index; reconciling the mission criteria
  checkboxes; promoting design-review-before-code and the three schema/auth patterns to
  methodology.

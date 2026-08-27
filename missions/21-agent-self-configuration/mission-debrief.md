# Mission Debrief: Agent Self-Configuration

**Mission**: [Agent Self-Configuration](./mission.md)
**Status**: completed
**Debriefed**: 2026-08-27
**Flights**: 3 (all completed) · **Outcome**: achieved — all 10 success criteria met

## Outcome Assessment

The mission achieved its stated outcome in full. An agent can look at itself and revise
how it presents (its description and system prompt) through a first-class,
operator-controlled surface; the same surface is opened to an external client scoped to
one agent; and the operator stays in charge throughout — off by default, per-agent
approval mode, a full revision log with restore, per-capability control, and per-principal
credential revocation. The boundary held exactly as specified: an agent can change what it
*says* and how it *behaves within* the capabilities it already holds, and nothing more.

**All ten success criteria are met**, delivered across three flights and verified — the
external-client criterion live in Flight 3's HAT:

| # | Criterion | Flight | Evidence |
|---|-----------|--------|----------|
| 1 | Retrieve own config; no secret material anywhere | F1 | secret-free projection; response-text regression nets across all endpoints |
| 2 | Same secret-handling as every secrets-bearing record (incl. legacy read paths) | F1 | agent-config secret-handling fix landed *before* the read path |
| 3 | Revise description + system_prompt; everything else refused by construction | F1 | write allowlist = the tool catalog's shape (two write tools) |
| 4 | Revision states next-turn vs next-session; behavior matches | F1 | propagation timing; behavior-test-verified (fresh-conversation oracle) |
| 5 | Operator sets per-agent approval; agent can't change it | F2 | flag on `AgentConfig`, projection omits it, no tool addresses it |
| 6 | Under approval, no effect until accepted; operator sees the diff | F2 | pending queue + count badge; fail-closed staleness |
| 7 | Every revision recorded; operator restores any earlier value | F2 | `agent_revisions` log + value-node restore (original reachable) |
| 8 | Surface appears among sources; per-capability withholding | F1 | presents as a `streamable-http` source; existing override machinery |
| 9 | Off for every existing and new agent until enabled | F1 | opt-in per agent from the Self-configuration tab |
| 10 | External client scoped to one agent; withdraw+reissue no restart; immediate cutoff | F3 | `ext_` principal; HAT AC1–AC8 all passed live |

The mission's central risk — the surface reachable by an agent whose inputs are
attacker-controllable (indirect prompt injection) — was held bounded, not eliminated, and
is documented as a live residual (see Known Issues / Accepted Residual). The write
allowlist, the self-referential exclusion, and the revision log all held as mission-level
constraints, structurally.

**Mission-control experience (human interview):** the operator reports the mission "went
smoothly as expected," and names the **HATs as where confidence came from** — the guided
grant/write/revoke acceptance tests in Flights 2 and 3 were where the surface's behavior
was *seen* to be correct end-to-end, above and beyond the passing suites. No process
friction reported; no scope or sequencing they'd change in hindsight.

## Flight Analysis

- **Flight 1 — Self-Configuration Surface** (completed). The foundational bet: present the
  surface as a `streamable-http` MCP source to inherit the existing per-capability gating.
  It kept ~14 Python + ~26 JS `MCPSource.type` dispatch sites untouched and avoided a
  transport-enum widening + table rebuild — the mission's pre-declared split point never
  fired (two of its three conditions were structurally absent). Landed the
  agent-config secret-handling fix *ahead of* the read path (sequencing: secrets → read →
  write). The re-entrancy probe (can the platform call its own loopback MCP endpoint from
  inside a request handler?) earned its keep as a blocking prerequisite. Deepest finding: a
  live model anchors on conversation history over a freshly-swapped system prompt — the
  behavior-test oracle had to become a fresh conversation.
- **Flight 2 — Operator Oversight** (completed). One `agent_revisions` status-bearing table
  (full CHECK vocabulary shipped up front) served log + queue + restore; later legs added
  code, not migrations. Approval mode + pending queue + count badge reused the connector
  peer-approval pattern. Value-node restore made "restore any earlier value" — including the
  pre-first-revision original — literally true. Design-review-before-code caught two
  completeness gaps invisible to any passing test (a governance-gate-disabling preserve-on-PUT;
  a criterion-failing restore value-space gap).
- **Flight 3 — External Client Access** (completed). Reconnaissance found Flight 1 had
  already built the transport, confinement, and revoke-immediacy *mechanism*, narrowing the
  flight to a credential-family addition + provenance/concurrency/governance. A distinct
  `ext_` principal (own encrypted store keyed on the surface `source_id` with FK cascade),
  `source='external'` provenance, a field-scoped compare-and-swap, and governance-by-
  construction (403 on the operator control plane). HAT: 8/8, zero behavioral defects.

**Flight pattern:** all three went smoothly; none struggled or aborted. The common thread
in what worked was **design-review-before-code on the high-risk legs** — it found real
completeness gaps in Flights 2 and 3 that citation-dense specs and passing suites both
missed. The common thread across the mission's *architecture* was the credential-family /
confined-source reuse compounding each flight.

## Architectural Assessment

Net: the architecture **improved** on security posture and reuse, **held** on data
modeling, and incurred **one bounded, correctly-named concurrency debt**. It did not
degrade.

**The central design bet held and compounded.** "Present the surface as a source to inherit
per-capability gating" paid a growing dividend: Flight 1 avoided the enum-widening and a
table rebuild; Flight 3 wrote *no* transport, confinement, or immediacy code — a second
principal was a second `CONFINED_SOURCE_PATHS` entry plus a credential family. The mission
spent Mission 20's "second source can register against" seam exactly as designed, twice
(`agt_`, `ext_`), the second spend adding zero enforcement code.

**Design decisions were consistent across the mission on every axis but one:**
- **Credential family** — `loc_`/`agt_`/`ext_`, each a `CredentialSource` on the shared
  `register_source` seam, each confined through the same `CONFINED_SOURCE_PATHS` map.
- **"By construction" invariant** — the write allowlist as the catalog's shape (F1); the
  approval flag unwritable because no tool addresses it and the projection omits it (F2);
  the external principal reaching only the four confined tools (F3). The mission's central
  invariant held structurally in all three flights, not by denial lists.
- **One status-bearing revision table** — designed up front (F2), widened exactly once (F3).
- **Structural secret-free projections over masking** — consistent across F1/F2/F3. (Nuance:
  the platform deliberately runs *both* disciplines — marker-derived masking retrofitted onto
  the leaky legacy agent-read endpoints, and structural projection on the new purpose-built
  paths. Coherent, not an inconsistency to "fix.")

**The one inconsistency — and the mission's structural weakness — is the concurrency model.**
There is no single model; the mission accreted *three non-composing point mechanisms* around
an unguarded whole-row `save`: F2's non-atomic approve-path compare-then-save; F2's targeted
approval-flag UPDATE (no base guard); F3's atomic field-scoped CAS. `SQLiteAgentStore.save`
remains a whole-row last-writer-wins upsert with **four** write consumers (Studio edit,
approve, restore, direct write), of which only the direct-write path is CAS-guarded. See
Known Issues.

## Patterns Established (promote to methodology)

1. **Confined `CredentialSource` on a shared seam** — the strongest pattern of the mission;
   proven twice, the second spend adding zero enforcement code. The template for any future
   non-operator credential principal. (Documented trap: a "source is not `file`" confinement
   check would 403 the session cookie — scope belongs at the middleware via an opt-in map,
   never as a blanket rule.)
2. **Source-row-FK-cascade for lifecycle-coupled child records** — key a dependent table on
   the parent surface row's id with `ON DELETE CASCADE` so teardown/revocation is enforced by
   the schema, not by teardown code kept in step across call-sites. The schema-level answer to
   "an invariant is only as good as the call-sites you surveyed."
3. **Value-node restore** — the reusable content is the *lesson*: any undo/restore feature
   starts from "enumerate every value the field can hold, including out-of-band-set ones," not
   "reinstate prior proposals."
4. **Field-scoped compare-and-swap** — a good atomic single-field guard, promoted **with the
   caveat that it is a point guard, not a concurrency model** (it covers one of four writers).
5. **Design-review-before-code for high-risk legs** — **promote to doctrine.** Two consecutive
   confirming flights; it found a governance-gate-disabling bug, a criterion-failing restore
   gap, a latent privilege bug, a migration false-pass, and a half-threaded model widening —
   all invisible to passing suites. Pair with two authoring rules it matured: **"enumerate the
   value/state space and every write/teardown call-site as an authoring step"** (F2 recommended,
   F3 confirmed it works), and **"read the lifecycle code before locking the schema."**
6. **Structural secret-free projection over masking** — keep, understanding the deliberate
   two-discipline state.

Supporting conventions worth codifying: **FK-toggling table-rebuild migrations use
`executescript`** for the COMMIT boundary (`PRAGMA foreign_keys` is a no-op inside a
transaction — caught by the pre-existing v21 cascade test); **itemize flight-end-review
findings with severity in the flight log**; the behavior-test **fresh-conversation oracle** for
system-prompt-dependent assertions (confirm it landed in `behavior-test/AUTHORING.md`).

## Technical Debt & Known Issues

**Headline — whole-row last-writer-wins `SQLiteAgentStore.save`, four write consumers, closed
for one.** Correctly deferred at single-operator + loopback scale, but deferred across three
consecutive flight debriefs, each adding a point workaround. This debrief **converts it from a
perpetual open question into a tracked Known Issue with a named trigger** (operator-elected;
see mission.md Known Issues). The residual clobber (an external direct write on one field vs. a
Studio edit on the other) is *already technically possible today* and accepted only because a
single operator won't do both at once — relaxing single-operator removes that acceptance. Note:
the residual has **no red test** (accepted behavior, not a forbidden invariant), so a future
flight closing it inherits none.

**Priority order for follow-ups:**
- *Quick wins (independent, near-term):* squawk **0008** (history UI mislabels `external` as
  "self-revised" — bounded, presentational, now load-bearing for external-tuning audit); the
  **pending-dedup partial unique index** `(agent_name, field) WHERE status='pending'` (converts
  an app-level TOCTOU into a schema invariant); an **xfail marker** for the residual DD5 clobber
  so the etag work has a red test waiting.
- *Verification debt (filed):* squawks **0005** (shutdown-drain under load) and **0006**
  (two-agent-simultaneous isolation e2e) — unproven mitigations, not defects.
- *Servicing (filed):* squawks **0004** (import-order duplication), **0007** (missing
  `--status-success-bg-soft` token / diff asymmetry).
- *Long-term (triggered, not speculative):* row-version/etag on `save` + route all four
  consumers through it, folding in the CAS/append crash window — done together when the trigger
  fires.

**Accepted residual (a named posture, not debt to fix):** indirect prompt injection. An injected
agent can rewrite its own guardrails *within tools it already holds* — it cannot acquire
capabilities, read another agent's config, see a secret, or alter the surface. Approval mode
closes it *when armed*; with approval mode off the residual is live, mitigated by the ordinary
per-tool checkboxes or disabling the surface. Documented in `SECURITY-MODEL.md` as live. This
becomes a **re-audit trigger** the moment a non-operator principal traverses the write path
under a relaxed posture ("external principal + approval-off" is a materially different risk than
"self-revision + approval-off").

**Known asymmetry (recorded, deliberate):** `agt_`/`ext_` secrets are Fernet-encrypted at rest;
the `loc_` operator credential is a plaintext `0600` file — same OS-permission trust boundary,
benign.

## Forward-Looking (inherited-assumption-with-expiry)

**Single-operator / loopback-only is now the single load-bearing assumption between this
codebase and a multi-principal/etag requirement.** Every deferred-concurrency decision rests on
it. Stated for the next mission:

> The whole-row LWW on `agents.save`, the field-CAS-covers-one-writer scoping, the
> application-level pending-dedup, and the injection-residual-accepted-under-approval-off posture
> are valid **only** under single-operator + loopback-only. A future mission that relaxes
> *either* loopback *or* single-user MUST, in the same mission: (1) put a row-version/etag on
> `save`; (2) route all four write consumers (Studio edit, approve, restore, direct write)
> through it; (3) make pending-dedup a schema invariant; (4) re-audit the injection residual for
> a non-operator principal on the write path. `SECURITY-MODEL.md` "Future Work → Multi-user form
> factor" is the cross-reference home.

**Scaling / test-suite trend — act before the next surface flight.** Isolated unit lane grew
**F1 ~370s → F3 585s** (+58% on +2.9% tests); the wall-clock is carried by a growing tail of
**real-uvicorn-loopback integration tests** (out-of-process `MCPClient` + full-app httpx
suites), not per-test slowdown (~130ms average). Two more surface flights push the unit lane past
10 minutes. Recommendation: **tier the loopback-server integration tests into their own lane**
(the browser tests already precede this exactly) proactively. Record **585s** as the honest
isolated baseline (F2's 8:05 was under concurrent-load confound — trust the count delta).

**Crew/process friction to fix at the methodology level:** the Developer crew stalled on final
wrap-up on both F3 Leg 2 and Leg 3, ending its turn "waiting on the Monitor" for a `make
test-unit` result that cannot resolve within a spawned agent's turn — recurring even after an
explicit spawn-prompt instruction. The Flight Director completed bookkeeping and independently
verified the suite each time. A crew "Implement"-prompt fix (run the suite synchronously and
report before yielding), not a code fix.

## Methodology Assessment

The mission/flight/leg hierarchy worked well for this project. Flights sized to
decision-and-risk clusters (surface presentation / oversight semantics / external principal +
secrets) each warranted their own planning conversation and review gate — the three-flight
split was correct, not padding. The HATs were the highest-confidence artifact for the operator.
The strongest recurring signal is **design-review-before-code**, which should move from
per-flight discretion to methodology doctrine for high-risk legs — this mission is the second
consecutive confirming data point.

Housekeeping done in this debrief: the ten success-criteria checkboxes in `mission.md` (left
unchecked during execution) are reconciled against the per-flight record, and the whole-row LWW
debt is logged as a mission Known Issue with its named trigger.

## Top Recommendations

1. **Promote design-review-before-code to methodology doctrine for high-risk legs**, with its
   two matured authoring rules (enumerate the value/state space + write/teardown call-sites;
   read the lifecycle code before locking the schema).
2. **Standardize the three schema/auth patterns** (confined second `CredentialSource`;
   source-row-FK-cascade; field-scoped CAS *as a labeled point guard*) and value-node restore.
3. **Carry the single-operator/loopback assumption forward as an explicit expiry-triggered
   inheritance** — the next mission that relaxes it owns the four-part concurrency remediation.
4. **Tier the loopback-server integration tests into their own lane** before the unit lane
   passes 10 minutes.
5. **Clear the quick-win follow-ups** (squawk 0008; pending-dedup index; residual xfail marker)
   independently of any triggered work.

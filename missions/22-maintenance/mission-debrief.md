# Mission Debrief: Post-Mission-21 Maintenance

**Date**: 2026-08-29
**Mission**: [Post-Mission-21 Maintenance](mission.md)
**Status**: completed
**Duration**: 2026-08-27 – 2026-08-29 (inspection → flight → three squawk turnarounds)
**Flights Completed**: 1 of 1

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| `rotate_encryption_key` cannot strand the DB on a key the process doesn't hold; recovery path, logs, fault-injection test (B8-rotate) | **Met** | Two-phase `encryption.key.next` sidecar (stage → commit → `install_key` with no `await` between → promote); startup reconcile in web lifespan and CLI; fault-injection for staging, commit, and promote failures. Rotation now covers **seven** corpora — two (`tool_configs.secrets`, `agent_external_credentials.secret`) had never joined it (Decision D1). PR #179. |
| `ext_` mint/revoke leaves a durable trace; tombstone decision recorded (B8-ext-credential-trace) | **Met** | INFO lines at mint/revoke/rotate (agent, id, label, principal — never the secret) and at both FK-cascade points. No `revoked_at`; rationale in `agents.md` / `SECURITY-MODEL.md` as the convention the P8 logging sweep inherits. |
| OAuth callback verified end-to-end through the gate on a real cross-site redirect; mechanism implemented; middleware-inclusive test (S5 + S5b) | **Met** | Proven broken **red-first** (unit and browser tests both hit the gate's 401 pre-fix, recorded verbatim), then `GET /api/oauth/callback` became the second exemption with `state` as the credential; cross-site `localhost` → `127.0.0.1` browser test stands in for an IdP (none configured). |
| *(Outcome)* Codebase returns to **Flight Ready** | **Met — operator call, Architect concurs** | All 11 Action Required findings from the 08-27 report closed (3 by the flight, 8 by turnaround 08-27); all 8 pre-existing squawks cleared or escalated (turnaround 08-29); suite green throughout with no new skips/xfails/flakes. The 27 Advisory items remain and are carried, not blocking. The next routine inspection confirms rather than this debrief. |

### Overall Outcome
The mission did what it was scaffolded to do and one thing more. The three design-bearing findings were resolved with decided designs (Q1–Q3 confirmed at flight start, held without drift), and every squawk-sized item logged since Mission 20 — 25 in all, 0001–0025 — is now completed, escalated with a recorded disposition (0007), or freshly logged with a clear shape (0025). The extra: Decision D1 found that two missions had added encrypted columns without extending the rotation invariant, a data-loss-on-operator-action defect that neither the inspection nor the flight spec saw. It was closed in the same leg and is now mechanically guarded (squawk 0018).

The outcome was still the right goal at the end. Stakeholder value: the credential lifecycle can be trusted before more `ext_` clients are issued, and the OAuth path is proven rather than assumed before a second provider is added — both stated in the mission's Stakeholders section, both delivered.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1 — Credential lifecycle integrity and observability | completed | Three legs, one commit, flight-wide review confirmed first pass; two design-review rounds on each high-risk leg caught two bugs in the *proof apparatus* (a primitive whose precondition the route violated; a browser test that would have passed with the fix removed). 4571 passed at landing. |

Beside the flight, three squawk turnarounds:

| Turnaround | Squawks | Outcome |
|---|---|---|
| 2026-08-27 (PR #178) | 0010–0017 | 8/8 completed — the report's Action Required pattern-copies |
| 2026-08-28 (PR #180) | 0018–0024 | 7/7 completed — flight-debrief follow-ups incl. three enumeration guard tests and un-ignoring `.flightops/` |
| 2026-08-29 (PR #181) | 0001–0008, +0025 | 7 completed, **0007 escalated** at the qualification gate (a design decision hid inside a "one-line" CSS fix), 0025 logged from the Reviewer |

**Patterns across the work**: the flight and all three turnarounds ran fully autonomously between operator go/no-go points (the operator judged this the right level). The only stall was one Developer that waited on a full-suite run it had started on its own — the same Monitor-wait failure mode the M21 debrief flagged, now fixed by an explicit "do not run the full suite" line in every spawn prompt.

## What Went Well
- **Leg design against the code found the defect the inspection missed.** D1 surfaced because the leg designer read `rotate_encryption_key` side by side with the repositories to design the reconcile sampler. Five Inspectors and an Architect roundtable had not seen it. "Design from the code, not the report" is the mission's strongest confirmation.
- **Design review before code paid for itself twice, both times on how a proof could lie** — not on the fix. This is the third consecutive mission confirming design-review-before-code for high-risk legs (M20, M21, M22), and the first where the catches were test-apparatus errors.
- **The qualification gate escalated when it should have.** Squawk 0007 was drafted literally, measured (WCAG contrast math), found to need a hue decision, reverted, and escalated with a disposition — no forced fix, no silent regression, no undisclosed exemption.
- **Measure rather than reason changed three outcomes**: the gate cost (0002: 6 µs, not "sub-millisecond"), the loopback-tail hypothesis (refuted with the per-file aggregate the report asked for), and 0007. All three were places where a plausible claim would otherwise have stood.
- **The debrief → squawk → turnaround pipeline is short and clean.** Flight-debrief action items became squawks 0018–0023 the same afternoon and were closed the next morning with independent review; the Reviewer's non-blocking finding became 0025 rather than a fold-in.
- **Reviewer model tiering went from disclosed deviation to written rule to first correct application in under 24 hours** (0023 → 0024 reviewed on Haiku as a non-security diff).

## What Could Be Improved
- **The inspection process has a blind spot for invariants that span missions.** Two encrypted columns (M16, M21) missed the rotation invariant and the 08-27 inspection did not catch it either. The guard test (0018) closes the mechanism; the process fix is an inspection checklist line — "for every documented invariant that enumerates columns/paths/routes, diff the enumeration against the schema/router" — for `/routine-maintenance`.
- **Hand-maintained enumerations are a recurring shape.** Three were found or grew this mission (encrypted corpora, `EXEMPT_PATHS`, `/_test/*`); all three now have shape-matching guard tests, but the structural fix for the corpora (an `EncryptedColumn` registry both the route and the sampler iterate) is flight-sized and has no scheduled home. Carried as a Known Issue with a trigger below.
- **`api.py` grew 5733 → 5954 lines** across the mission. Two consecutive maintenance reports have flagged its extraction items (E5, P1, P5) as Advisory; the flight's three legs had to run sequentially specifically because all three edited it, and each later leg paid a citation-drift tax (+3, +43 lines). A third report without action should treat it as a trend.
- **Anomaly A1 is half-closed.** The read/write interleaving window in rotation needs a rotation lock or a `BEGIN IMMEDIATE` strategy that survives aiosqlite's auto-commit-on-non-DML — a design decision, so it waits for a flight. It has no red test.
- **The Developer full-suite stall recurred once** (turnaround 08-29, squawk 0001) despite the M21 debrief's recommendation. The prompt-level fix worked for the rest of the batch; the crew "Implement" prompt should carry it permanently (see Methodology Feedback).
- **The maintenance report's sizing note on S5 undersold the leg** ("may collapse to a one-line exemption" — true of the diff, false of the verification burden). Gate/security-boundary findings should be sized by proof cost.

## Lessons Learned
- **Technical**: a stateful operation that must keep two stores in sync across a crash (DB + key file) wants stage-before-commit, install-in-memory synchronously after commit, promote after, and a self-healing reconcile at every entrypoint — the two-phase sidecar is reusable beyond encryption. A set that must agree across two files wants a test that derives one side from source and diffs the other; comments don't hold. Green is luminance-heavy: no self-tinted success wash clears AA at the current light-theme hue.
- **Process**: for negative security properties ("X cannot happen"), write the failing test first and record the failure in the log — it turns "we believe it was broken" into checkable evidence for one extra run. Review high-risk legs by asking "what would make this test pass with the fix removed?". Drafting later legs while an earlier one implements is a real wall-clock win *only* with a citation re-audit as an explicit step 0 after each landing.
- **Domain**: `localhost` and `127.0.0.1` are different sites, and it is `SameSite=Strict` — not host difference alone — that withholds the cookie on a cross-site top-level GET; that pair reproduces an IdP redirect without an IdP.

## Methodology Feedback
For mission-control (not applied this mission by operator decision; recorded here so they are not lost):
1. **Leg design-review prompt**: add "what would make this test pass even if the fix were wrong?" for any leg introducing a negative-security-property test.
2. **agentic-workflow**: state that later legs may be drafted during an earlier leg's implementation, with a mandatory post-landing citation re-audit before the later leg goes `ready`.
3. **Crew "Implement" prompt (default and project)**: "do not run the full suite; the Flight Director runs it at leg/flight/batch end" — the M21 recommendation, now with a second recurrence.
4. **routine-maintenance**: an inspection-checklist line for invariant enumerations vs. schema/router (the D1 blind spot), and size security-boundary findings by verification burden.
5. **Reviewer model tiering by security surface** is now the-one's crew rule (squawk 0023, versioned since 0024); worth considering for the default crew file.

The mission/flight/squawk split worked as intended: one flight for the three design-bearing findings, squawks for everything else, and the gate pushed the one mis-sized item (0007) back out. The operator judged the autonomy level right and reported no surprises — the cycle ran as the methodology intends.

## Action Items
- [ ] Next maintenance report Known Issues must carry: Anomaly A1 (rotation read/write window — lock vs. `BEGIN IMMEDIATE`); the `EncryptedColumn` registry refactor (trigger: the next encrypted column, or the next maintenance flight); squawk 0007's hue decision (trigger: the next UI-touching flight); `api.py` growth as a trend if E5/P1/P5 are deferred a third time.
- [ ] Squawk 0025 (pin evict-before-drain against the real lifespan branch) — single-squawk turnaround, ~10 min.
- [ ] Test-suite watch: record **557s** (4586 tests, isolated) as the post-M22 baseline; act (tier loopback/subprocess tests, or attack fixture cost in `test_provider_api.py` / `test_db_repositories.py` / `test_db_api.py`) only if the lane crosses ~600s — operator decision.
- [ ] Mission-control methodology items 1–5 above, when the operator opens that work.
- [ ] Optional: `uat-and-alignment` on the real app (rotate a key; mint/revoke an `ext_` credential) before the next `ext_` client is issued.

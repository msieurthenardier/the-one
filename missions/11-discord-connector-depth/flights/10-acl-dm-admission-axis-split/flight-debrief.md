# Flight Debrief: F9 + F10 (Combined — Pairing Resolution arc)

**Date**: 2026-05-28
**Flights**:
- [Pairing Resolution + Connectors-Screen Detach](../09-pairing-resolution-and-detach/flight.md) (F9; 7 mandatory + 1 HAT [partial])
- [ACL DM-admission + channels-axis UI split](flight.md) (F10; 4 mandatory + 1 HAT [completed])
**Status (both)**: completed
**Duration**: 2026-05-26 (F9 plan commit `3fd387e`) → 2026-05-28 (F10 commit `2692630`)
**Legs Completed**: 12 of 12 across both flights

**Combined-debrief rationale**: Operator deferred F9's standalone debrief at F10 planning (recorded in `mission.md` outline + F10 flight log). F9 L8's partial HAT directly fed F10's entire scope; one combined retrospective covers the dual-flow + axis-split arc end-to-end without overlapping content.

---

## Outcome Assessment

### Objectives Achieved

**F9** shipped the Discord-native peer-approval substrate end-to-end: resolver hook (`_discord.py:1619-1654`), `pending_approvals` table (schema v21), approve/dismiss endpoints, Chat UI banner (`pending-approval-banner.js`), detach surface (DELETE endpoint + pool release + grid badge), and the F7-Rec-#3(c) studio-event-bus extraction. The F9 L8 HAT closed mission criterion #9 (detach) substrate but PARTIALLY closed criterion #8 (pairing) — step 4 surfaced an ACL gap that filed itself as two structural Known Issues.

**F10** closed both findings: new `account.config.allowlist.dm_admission` Literal axis + per-agent `connector_acls[acct].admit_dms` opt-out + 3-value selector UI (allowlist editor) + opt-out checkbox UI (per-agent overlay) + migration v22 row-rewrite. The F10 L5 HAT re-ran F9 L8's 8-step scenario against a channels-restricted account + new substep 5b (per-agent opt-out); all 9 outcomes passed. **Mission criterion #8 (pairing) flipped `[~]` → `[x]` in `mission.md` — fully closed.**

### Mission Criteria Advanced

- **#8 Pairing resolution** — fully closed by F9 substrate + F10 axis-split closure.
- **#9 Connectors-screen detach** — closed by F9 L5 (DELETE endpoint + pool release + detail-page button + grid badge).
- **#22 Peer-name attribution** (indirect) — F9 L4 backend session-restore merge inherits the F6 peer-name infrastructure; pending-approval banner correctly attributes B1's display name.
- **#19 Daily-driver robustness** (indirect) — dual-flow becomes a reliable daily-driver primitive; HAT-validated dispatcher path.

### Checkpoints Met

All flight checkpoints across F9 (L1-L7) and F10 (L1-L4) checked off in respective `flight.md` artifacts. L8 (F9 HAT partial) and L5 (F10 HAT completed) recorded with verbatim per-step results.

---

## What Went Well

**Cycle-1 + cycle-2 design review catches.** Five HIGH-severity findings caught across the arc's leg cycles before implementation:
- F9 L1: validator-strictness on existing Pydantic models (would have produced 422 on every save).
- F9 L2: codec shape mismatch (would have routed pending-approval events through Message-codec).
- F9 L5: no public per-(agent, account) pool release primitive (would have leaked entries on detach).
- F10 L1: two Pydantic validators (account-scope + per-agent) reject unknown keys + enforce uniform value-type (would have rejected `dm_admission` and `admit_dms` at validation).

Each was caught at design review, not at implementation — saving cycle time and avoiding the "fix-while-implementing" rework pattern.

**Atomic-leg-pattern discipline held across substrate-touching legs.** F9 L2 (table + model + repo + dispatcher emit in one slice) and F10 L1 (schema v22 + 2 validator extensions + `_acl.py` re-order + tests in one slice) both shipped as single coherent diffs. No partial-substrate-without-effect states.

**Studio-event-bus extraction (F9 L6) was the right timing.** Cycle-1 architect's reframing ("no n-threshold rule; cite F7 Rec #3(c) as the trigger") avoided process-artifact framing. Mechanical refactor of 4 emit + 5 listener sites across 4 files, clean grep verification, zero behavior change.

**Operator-driven HAT consistently catches what unit/browser tests can't.** F9 L8 (partial) surfaced 2 structural ACL gaps → became F10's entire scope. F10 L5 (completed) surfaced 2 terminology/UI gaps + 5 inline cosmetic tweaks. Cross-axis interactions exercised under realistic operator configurations are HAT-tier territory — see Key Learnings below.

**Partial-HAT → followup-flight lifecycle worked.** F9 L8 partial-closed mission criterion #8 with `[~]`; F10 scope was directly the followup; mission-criterion mark flipped to `[x]` at F10 L5 closure. The `[~]` partial-marker is load-bearing and worth keeping.

**Combined-debrief shape was right for this arc.** Two flights, 4 calendar days, directly connected by F9 L8's findings → F10's scope. One retrospective covers the arc without overlapping content. Independent followup work (e.g. F11 = connector rename, F12 = hierarchical axes) warrants its own debrief.

---

## What Could Be Improved

### Process

- **2-cycle design review limit hit on F10 L1 stale-language sweep.** Cycle-2 was a consistency-only pass (no behavioral change) — the kind of fix that could land at Phase 2d code review without re-invoking the architect. **Operator confirmed**: keep the 2-cycle hard limit; no need to formalize a "consistency-only cycle 3." If a future cycle-2 surfaces only mechanical drift, the Flight Director should land the fixes and proceed without spawning a cycle-3 architect — the existing workflow language supports this.

- **L1 leg specs claiming "Existing tests pass unchanged" need calibration when validator-default behavior is in scope.** F10 L1's claim was structurally wrong: Pydantic-v2 in-place validator-default mutation of `dict` fields *expectedly* ripples to literal-dict-equality assertions in existing tests. 7 tests needed expected-dict expansion. Future axis-addition legs should budget this explicitly in the spec ("N existing tests will need expected-dict expanded for the new default key") rather than claim no impact.

- **Inline-test-fixup absorbed into L2/L3 before L4 could clean up.** Good ergonomics — by the time F10 L4 ran, there was no drift left to clean. But this empties L4's substantive content. **For F11+**: when a flight's planned scope includes a "test drift cleanup" leg, audit at L3-design-review whether the cleanup is materializing inline; if yes, retire that leg from the flight outline and re-purpose its slot or shorten the flight.

### Technical

- **`_acl.py:467` anachronistic deny message** ("DMs-only override; envelope is not a DM") — preserved verbatim under F10 L1 to keep `test_per_agent_channels_empty_is_dms_only_sentinel` green, but the branch now only fires for guild-context messages. Pin breaks intent. **Action item**: retire in F11's small-housekeeping fold-in by updating the test fixture + the message string together.

- **`tests/test_provider_repository.py` 13 asyncio teardown errors** — confirmed pre-existing (last touched commit `672f37f` pre-F7). Carrying across multiple debriefs without resolution. **Action item**: file as a routine-maintenance candidate explicitly in F11's prereqs.

- **`_acl.py` is at 497 LOC with 5 axes at two scopes + is_dm-gated branching.** Architect notes the next axis addition (hierarchical-allowlist Known Issue) will tip the function into "axes-decision-tree" territory. **Action item for F12**: extract the DM-vs-guild decision tree into two functions (`_admits_inbound_dm` + `_admits_inbound_guild`). Today's shape is on the edge of "still readable in one function"; a 6th axis tips it.

- **Substrate surface approaching the refactor line.** `ConnectorAccount.config["allowlist"]` now carries 5 inner keys; dispatcher consults the substrate at 3 sites; per-agent `connector_acls[account_id]` now carries 5 inner-key shapes. Combinatoric space is tractable today, but F11 (connector rename) + F12 (hierarchical axes) together will tip it.

### Documentation

- **`agents.md` is overdue for a structural sweep.** The M11 mission-specific subsection (line 384+) has accumulated. **Action items**:
  - Promote `dms-orthogonal-to-guild-restriction` (F10 L1's posture inversion of F8 L8) to a named M11 convention.
  - Extend the per-axis-tri-state-override block (currently 4 axes; now 5 with dm_admission).
  - Add a paragraph for the "backend-merged replay" pattern (F9 L4's `_restore_session` merges messages + pending_approvals by timestamp — currently undocumented except inline in `app.py`).
  - Prune F4-era prose that the M10-debrief should have retired.

- **New API endpoints not mentioned in agents.md/CLAUDE.md**:
  - `POST /api/connector-accounts/{id}/peer-approvals/{id}/{approve|dismiss}` (F9 L3)
  - `DELETE /api/agents/{name}/connector-accounts/{id}` (F9 L5)
  These are at the same "must-know-before-touching" level as the `__MASKED__` sentinel that CLAUDE.md does call out. Worth a parallel callout.

---

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| F9 L2 PRIMARY KEY PRAGMA quirk | SQLite reports `notnull=0` for PK columns; first migration test asserted otherwise; test-side fix. | No — well-known SQLite behavior; document in any future migration test fixture. |
| F9 L4 `_build_session_joined_degraded` became `async` | Shared the merge helper with the healthy `_restore_session` path; single call site updated. | Yes — when a sync helper is extended to call an async coroutine, async-up-the-chain is the right shape; flag as a node in agents.md. |
| F9 L4 `--success-bg`/`--success-fg` CSS tokens missing | Used `--status-success` + `--fg-on-accent` for the approved badge instead. | No — token-definitions regex check operates on `var(--name, fallback)` correctly; docstring inside the L4 spec was misleading. |
| F10 L1 in-place dict-mutation for validator default | `allowlist["dm_admission"] = ...` propagates to existing-test literal-dict assertions. | Document the cost in axis-addition leg specs. Don't change the pattern — Pydantic-v2 idiomatic. |
| F10 L1 3-test "inversion" claim incorrect | Tests at `:486, 592, 605` default to `is_dm=False`; their deny outcomes are unchanged under L1. Added 3 new `is_dm=True` analogues instead. | Yes — future "invert N tests" leg-spec claims should verify is_dm parameter explicitly; the test name shouldn't be the discriminator. |
| F10 L5 5 inline UI tweaks during HAT | Operator surfaced cosmetic gaps during walkthrough; landed inline before mission-criterion closure. | Already standardized as "inline-hotfix-during-HAT discipline" (F7 L12 / F9 L8 / F10 L5 precedent chain). |

---

## Key Learnings

**Cross-axis interaction discovery is HAT-tier-specific architectural strength, NOT a unit-test coverage gap.** F9 L8 step 4 failed because the (peers ∈ allowlisted) × (channels ∈ non-empty) × (is_dm=True) interaction produced an unexpected outcome. To pin this with unit tests, you'd need a combinatorial cross-product. The unit-test suite at L1 baseline had ~58 ACL tests pinning *each axis independently*. HAT exercises the realistic product because the operator's configuration *is* the product. Pre-F10, there was no axis to test against — F10 L1 then added the 9-cell `dm_admission × peers` matrix that crystallized the interaction.

**The right unit-test response to HAT-discovered cross-axis bugs is to crystallize the interaction into a new axis (substrate change) AND add the cross-product matrix for that axis.** F10 L1 did both. Don't try to test all cross-products preemptively; let HAT find the meaningful ones.

**Partial-HAT lifecycle: 4 calendar days for F9 + F10.** When an HAT lands `partial` and surfaces ≥1 confirmed-live structural finding, treat the followup as a direct extension of the current flight: single combined retrospective at the end, partial-leg artifact declares the followup flight's name. Operator-confirmed worth codifying.

**Operator-driven HAT surfaces TWO classes of finding consistently:**
1. **Architectural** (structural ACL gap; semantic posture inversion) → escalate to flight Known Issues; become followup-flight scope.
2. **Cosmetic** (UI copy, CSS double-wrapper, tab label) → land inline during HAT.

Both are healthy. The flight-debrief shape captures both; the HAT spec should NOT formalize "UI polish surfacing" as an expected outcome (operator instinct does this anyway; specs are for mechanical verification).

**Combined-debrief shape is methodology-extending, not workflow-breaking.** The `/flight-debrief` skill is single-flight by default; this combined debrief at F10's path with F9's stub is a one-off adaptation that the operator's mid-flight decision justifies. Future combined debriefs should follow the same shape (combined artifact at the LATER flight's path; earlier flight's debrief.md is a one-line stub pointing at the combined). Don't generalize this into a workflow change — it's case-by-case operator judgment.

---

## Recommendations

### 1. **Flight ordering**: F11 = connector rename, F12 = hierarchical axes (operator-confirmed)

Operator confirmed reordering the original mission outline. Original: F11 = audit-log inspector + slash-command verification; F12 = HAT-script + rate-limiting; F13 = daily-driver gate.

**New ordering**:
- **F11**: Connector rename (`ConnectorAccount` → `Connector` at code layer; sweep operator-facing copy in ~30+ JS sites; preserve `data-testid` selectors for stability). Mechanical-but-broad substrate refactor. Ship as its own flight to keep review focused.
- **F12**: Hierarchical allowlist axes (Servers ⊃ Channels ⊃ Users) — audit name-collision admission paths; decide hierarchy-aware storage vs UI-side disambiguation. Includes `_acl.py:admits_inbound` extraction into `_admits_inbound_dm` + `_admits_inbound_guild` per the 5-axis-tipping-point concern.
- **F13**: Audit-log inspector + slash-command verification (former F11; pushed back to leave room for substrate stabilization).
- **F14**: HAT-script + rate-limiting (former F12).
- **F15**: Daily-driver gate (former F13). Mission criterion #19 (full-day robust) closes here.
- **F16** *(optional)*: Alignment (former F14).

Mission outline update is a Flight Director follow-up action.

### 2. **agents.md structural sweep + new convention citations**

- Promote `dms-orthogonal-to-guild-restriction` (F10 L1 posture inversion) to a named M11 convention.
- Promote `backend-merged-replay` (F9 L4) to a named M11 convention.
- Extend the per-axis-tri-state-override block to 5 axes.
- Add a callout for `POST .../peer-approvals/{approve|dismiss}` + `DELETE /api/agents/{name}/connector-accounts/{id}` endpoints.
- Prune F4-era prose that the M10 debrief should have retired.

Fold into F11's small-housekeeping axis.

### 3. **Carry-forward items for F11's small-housekeeping**

- Retire `_acl.py:467` anachronistic deny message (update test fixture + string together).
- File `test_provider_repository.py` 13 asyncio errors as a routine-maintenance candidate (or fix inline — they've been carried since F7).
- agents.md structural sweep per Recommendation 2.

### 4. **Codify cross-axis HAT pattern in agents.md**

Add `hat-discovers-cross-axis-bugs` convention: "An HAT step exercising ≥2 storage axes simultaneously routinely surfaces semantic gaps unit + browser tests can't reach. Plan HAT steps as cross-axis state transitions, not isolated property checks. When HAT discovers a cross-axis bug, the substrate response is to crystallize the interaction into a new axis (with its own dispatcher consult) AND add the cross-product matrix for that axis to the unit-test suite."

### 5. **Workflow note: keep 2-cycle hard limit; consistency-only fixes land at Phase 2d**

Operator confirmed. When cycle-2 architect surfaces only mechanical/consistency drift (stale references; line-citation drift; literal-text rot), the Flight Director should land the fixes and proceed without spawning a cycle-3 architect. The existing workflow language supports this — no change needed.

---

## Action Items

- [ ] **Mission outline reorder**: F11=connector rename, F12=hierarchical axes, F13+=former order shifted. Flight Director updates `mission.md` flight outline (one-time edit).
- [ ] **F11 plan**: connector rename substrate flight. Operator + Flight Director plan via `/flight`.
- [ ] **F11 small-housekeeping fold-ins** (carry from this debrief):
  - Retire `_acl.py:467` anachronistic deny message.
  - File or fix `test_provider_repository.py` 13 asyncio errors.
  - agents.md structural sweep + new convention citations.
- [ ] **Test metrics baseline established**: backend suite 2733 passed / 4 skipped / 13 pre-existing errors / 256s wall. Slowest test: `test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` (10.01s, designed). Future debriefs compare against this.

---

## Test Metrics

| Metric | F8 land | F9 land | F10 land |
|--------|---------|---------|----------|
| Backend tests passed | 2669 | 2721 (+52) | 2733 (+12 net; +25 new offset by 13 pre-existing errors) |
| Browser tests added | — | +6 (4 chat + 2 detach) | +7 (3 dm-admission row + 4 per-agent admit-dms) |
| Skipped | 4 | 4 | 4 |
| Pre-existing errors | 0-13 (intermittent) | 13 (`test_provider_repository.py` asyncio) | 13 (unchanged) |
| Wall-clock (full suite) | ~150s | ~250s | ~257s |
| Flakes observed | — | — | Zero (two runs both 2733/13/256s) |

The +7s wall-clock from F8 → F10 tracks the test-count growth (~64 new tests across the arc); no per-suite slowdowns above noise.

---

## Methodology Feedback

**`/agentic-workflow` skill held up cleanly across both flights.** Per-leg design review + Phase 2d batch commit cadence stayed coherent; the 2-cycle limit was right (operator-confirmed). Branch-from-prior-flight-HEAD prerequisite (F10 branched from F9 HEAD pre-merge) worked without conflict.

**`/flight-debrief` skill is single-flight by default; combined debrief is a one-off adaptation.** Don't generalize into a workflow change — case-by-case operator judgment. The combined-artifact-at-later-flight's-path + earlier-flight-stub pattern is the shape if it recurs.

**Partial-HAT → followup-flight lifecycle is the meta-pattern** worth codifying as a methodology note (not a skill change). When an HAT lands `partial` with structural findings, treat followup flight as direct extension: single combined retrospective, mission-criterion `[~]` partial-marker, partial-leg-artifact declares followup flight slug.

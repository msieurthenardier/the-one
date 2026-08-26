# Flight Debrief: Operator Oversight

**Date**: 2026-08-26
**Flight**: [Operator Oversight](flight.md)
**Status**: completed
**Duration**: 2026-08-25 – 2026-08-26
**Legs Completed**: 3 autonomous + 1 optional HAT

## Outcome Assessment

### Objectives Achieved

The flight added operator oversight of agent self-revision on top of Flight 1's
direct-apply surface, off by default so Flight 1 behavior is unchanged until an
operator opts in. Committed as `417786d` (three legs) and `f0debd8` (the
HAT-driven UX restyle):

- **Leg 1 — revision log** — the `agent_revisions` table (migration v34), the
  `AgentRevision` model and `AgentRevisionRepository`, and the direct write path
  wired to log every self-revision as an `applied` row with before-image,
  after-image, and timestamp.
- **Leg 2 — approval mode + queue** — the per-agent
  `self_revision_requires_approval` column (migration v35) with the mandatory
  preserve-on-PUT; the non-persisting queued write branch; five endpoints
  including fail-closed staleness approve (409 + current-vs-proposed, re-confirm
  to override); disable-supersedes-pending; and the Studio queue + count.
- **Leg 3 — restore** — the operator-direct `side=proposed|base` value-node
  restore endpoint (never queued, logged with provenance) and the Studio
  revision-history view.
- **Leg 4 (HAT)** — a guided operator acceptance session that verified every
  oversight path live and drove a look-and-feel restyle (slider switches, diff
  highlighting, grouped restore rows, collapsible history).

### Mission Criteria Advanced

- **Criterion 5** (operator sets, per agent, whether revisions apply directly or
  wait for approval; the agent cannot change it) — met. The setting is unwritable
  by the agent by construction (no write tool addresses it; the read projection
  omits it), verified in code and by test.
- **Criterion 6** (where approval is required, a revision has no effect until the
  operator accepts, and the operator can see what would change) — met. The queued
  branch persists nothing; the queue card and staleness panel both surface
  before→after; verified live in the HAT and by endpoint tests.
- **Criterion 7** (every revision recorded with what changed and when; the
  operator can restore any earlier value) — met, including the corrected sense of
  "any earlier value": the value-node model makes the pre-first-revision original
  (and any out-of-band operator-set value) restorable, not just prior proposals.

Criteria 1–4, 8, 9 landed in Flight 1. Criterion 10 (external client access)
belongs to Flight 3.

## What Went Well

- **DD1 designed the schema for the whole flight up front.** `agent_revisions`
  shipped with its full CHECK vocabulary in Leg 1 (`applied`/`pending`/
  `dismissed`/`superseded`, `self`/`restore`) while Leg 1 wrote only
  `applied`/`self`. Legs 2 and 3 then added **code only, no migrations** against
  the v34 schema. The table shape was never revised.
- **Connector peer-approval reuse validated the pattern as a pattern.**
  `AgentRevisionRepository._transition`/`mark_applied`/`mark_dismissed` are direct
  ports of `PendingApprovalRepository` (idempotent-on-self, illegal→409), the
  cross-ID 404 guard and field-projected list came across intact, and the
  Chat-area badge idiom ported to Studio per-agent. A second consumer is what
  turns a one-off into a reusable pattern.
- **Design-review-before-code caught two completeness gaps invisible to
  happy-path tests — the flight's strongest process signal.** (1) **DD2
  preserve-on-PUT**: a Studio Save of any *other* field would have silently reset
  `self_revision_requires_approval` to `False`, disabling the governance gate —
  caught by reading the write path, not running it, and fixed before code with a
  dedicated regression test. (2) **DD5 unreachable-original**: restore would have
  reinstated only `proposed_value`s, leaving the original value (only ever a
  `base_value`) unreachable — a direct failure of criterion 7 — caught at Leg 3
  design review and fixed across two cycles into the value-node `side` model.
- **The tests are non-vacuous.** The queued-branch test monkeypatches `save` to
  *raise if called*; the staleness test asserts the store is untouched and the
  row still pending on a 409; the FK-cascade test runs against a
  `foreign_keys=ON` fixture with an in-test `PRAGMA==1` assertion (routed away
  from the pragma-less `:memory:` fixtures); restore's original-reachability is
  explicitly pinned. Negative paths are asserted, not assumed.
- **DD8's second disable path was a good catch.** The spec named one
  surface-disable path; implementation found two (`DELETE /self-configuration`
  and `DELETE /mcp-sources/{id}` on a surface row) and threaded the supersede
  into both, above the `row is None` early-return so a disable always clears the
  queue. The invariant needed every teardown site, not one.
- **The HAT caught only look-and-feel.** All 12 UX punch-list items were
  presentation (run-on text, missing field labels, raw timestamps, fused
  restore/log lists); none were behavioral. That the autonomous legs got the
  *behavior* right and the HAT found only *polish* is exactly the division of
  labor the HAT is for — and the fix-vs-feature gate held (all inline, nothing
  promoted).

## What Could Be Improved

### Process

- **Citation-density is not design-completeness.** The three specs were unusually
  detailed and citation-audited, yet four material corrections were made by the
  review agents rather than the authored specs — DD2 preserve-on-PUT, DD5
  original-reachability, DD8 surface-disable supersede, and the four-not-three
  save-wiring sites (a runtime-fatal "19 columns but 18 values" miss) — plus one
  that slipped all the way to flight-end code review: the value-node dedup keyed
  by raw value, colliding `description` and `system_prompt` on their shared `""`
  default and silently dropping a field's original-restore control.
  **Recommendation: for HIGHEST-tier legs, treat "enumerate the value/state space
  and the write/teardown call-sites" as an authoring step, not a review finding.**
  Restore/undo features in particular should start from "enumerate every value
  the field can hold, including out-of-band-set ones" rather than "reinstate
  prior proposals."

### Technical

All items below are **documented in code** and accepted at operator/single-writer
scale; they are named here as standing debt, not surprises.

- **Whole-row last-writer-wins persistence now has three consumers.**
  `SQLiteAgentStore.save` is a full-row upsert with no version guard; Studio edit,
  approval-apply, and restore all rely on point workarounds (DD4's scoped
  base-value compare; the targeted `set_self_revision_requires_approval` UPDATE).
  This is correct scoping today but becomes a real concurrency exposure the moment
  a second live principal writes the same fields — i.e. Flight 3 (see
  Recommendations).
- **Non-transactional override branch** (`update_base_value` → `save` →
  `mark_applied`, three commits) and the **save/append crash window** in
  `_apply_revision` (save self-commits, so a revision can persist without its log
  row) — both ordered so the worse failure can't occur, both commented, only the
  crash window has a test.
- **Pending-dedup is application-level, not a schema invariant.** The optional
  partial unique index `(agent_name, field) WHERE status='pending'` was not
  implemented; the "one pending row per agent+field" contract rests on
  SELECT-then-write. Harmless single-writer; a genuine TOCTOU under concurrent
  writers.
- **`.diff-add` highlight asymmetry** — deletions get a `--status-danger-bg-soft`
  background; additions get color + underline only, because no
  `--status-success-bg-soft` token exists. WCAG-safe (underline carries meaning,
  never color alone) and documented, but the real fix is a missing design token.

### Documentation

Thorough — `SECURITY-MODEL.md` (approval mode as the operator gate, fail-closed
staleness, restore-is-operator-only-with-no-MCP-tool), `CLAUDE.md`, `agents.md`,
and the testid registry were all updated. The one gap is procedural, now closed:
the two carried-forward verification items are filed as squawks (Action Items).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD8 (surface-disable supersede) added at Architect review, not in the first-draft spec | The teardown reasoning covered agent-deletion (FK cascade) but missed the surface-disable strand | Yes — "enumerate every teardown/write call-site" as an authoring step |
| Restore generalized to the value-node `side` model across two review cycles | DD5 nailed restore's authority model but under-specified the restorable value *set* (original unreachable) | Yes — the value-node restore pattern (dedup of base ∪ proposed across applied rows, each carrying `(revision_id, side)`) |
| Two Flight-1 carry-overs pulled OUT of Leg 2 at design review | Pool/lifecycle verification-debt orthogonal to approval governance; folding into the largest/highest-risk leg invited shallow treatment | N/A — correct one-time scope call; the debt was re-homed to squawks |
| Wall-clock +31% vs Flight 1 not treated as a regression | Measurement confound (concurrent background commands during the metrics run; different machine state) + genuinely heavier full-app httpx endpoint suites | Yes — capture metrics on an isolated run, not concurrently with other work |

## Key Learnings

- **Design-review-before-code is doctrine for HIGHEST-tier legs, not overhead.**
  It caught a governance-gate-disabling bug and a criterion-failing restore gap,
  both completeness gaps in otherwise-sound decisions, both invisible to a passing
  test suite. A citation-verified read of the write path finds what tests cannot.
- **"Restore to any earlier value" is a value-space problem, not a mechanism
  problem.** The mechanism (load → model_copy → save → log) was easy; the design
  content was *which values are reachable*. Enumerate the value space — including
  values set out-of-band — before locking the restore surface.
- **An invariant is only as good as the number of call-sites you surveyed.**
  Supersede-on-disable was correct but needed both disable paths; the value-node
  dedup needed the field in its key. Both are the mission's own "count the sites,
  it's a survey not a feeling" instinct applied to teardown and to UI state.

## Recommendations

1. **Flight 3 must resolve the concurrency question the LWW substrate defers.** An
   external client is a second live principal writing the same two fields. Decide
   explicitly whether external writes route through the same `_apply_revision`
   choke point (inheriting approval mode + the log — likely desirable), and
   whether DD4's point-scoped base-value compare needs generalizing to an etag now
   that "concurrent edit while a proposal is pending" stops being hypothetical.
   The DD5 trade-off ("restore is a deliberate operator action so the DD4 window
   doesn't apply") is no longer safe once a non-operator principal can be
   mid-write.
2. **Flight 3 must re-audit the by-construction governance invariant.** Approval
   mode's safety rests on `self_revision_requires_approval` and the
   `agent_revisions` transitions being unreachable by the agent (no tool,
   projection omits it). That invariant is now load-bearing for a *governance
   control*. Make "no external write path can address the approval-mode column or
   the revision transitions" an explicit Flight-3 acceptance criterion, and add a
   `source='external'` value to the revision log's CHECK (a v-next migration) so
   external writes get clean provenance rather than reusing `self`.
3. **Flight 3's credential store crosses the secrets boundary Flight 2 stayed
   inside.** Flight 2 added no encrypted columns; Flight 3's per-agent credentials
   are a secrets-bearing table. Extend Flight 1's structural-projection discipline
   (purpose-built projections, not masking) to it.
4. **Standardize the value-node restore pattern and the design-review-before-code
   discipline** into the methodology (the latter as doctrine for HIGHEST-tier
   legs). Both earned their keep this flight.
5. **Small servicing follow-ups** (filed as squawks): the two pool/lifecycle
   verification gaps carried from Flight 1, and the missing
   `--status-success-bg-soft` token. Leave the partial-unique-index for pending
   dedup as a Flight-3 concurrency-decision input (it interacts with the LWW call,
   so it is not a standalone squawk), and the endpoint load→get→cross-ID boilerplate
   as a refactor-of-opportunity.

## Action Items

- [ ] Flight 3: route external-client writes through `_apply_revision` (or
      consciously not), decide approval-mode applicability to a credentialed
      principal, add `source='external'` to the revision-log CHECK, and make the
      "external path cannot reach the approval-mode column / revision transitions"
      invariant an explicit acceptance criterion.
- [ ] Flight 3: decide whether the whole-row LWW on `agents` remains deferrable or
      has become a prerequisite once a second writer exists on a different
      transport (includes the pending-dedup partial unique index).
- [ ] Verify the shutdown-drain-under-load mitigation (surface-enabled agent with
      a live pool connection at shutdown) — **squawk 0005**.
- [ ] Verify two-agent-simultaneous isolation (two agents' surfaces/credentials do
      not cross) end-to-end — **squawk 0006**.
- [ ] Define a `--status-success-bg-soft` design token and apply it to `.diff-add`
      to remove the diff-highlight asymmetry — **squawk 0007**.

## Notes

- **Human interview skipped** per the skill's guidance — the flight log is
  comprehensive (DD1–DD8, four design-review cycles, the full HAT session and UX
  punch-list), and the Flight Director drove every decision first-hand.
- **Test metrics.** Full unit lane at debrief: **4447 passed, 10 skipped**
  (687 deselected — the browser-marked tests run in their own lane, green
  throughout). Leg-over-flight growth **4381 → 4447 = +66 in-lane** (+72 test
  functions authored; ~6–11 are `@pytest.mark.browser`, deselected in the unit
  lane); **+195 over the Mission-20 ~4252 baseline**. Wall-clock ~8:05 vs Flight
  1's ~6:10 (+31%) is **not** read as a per-test regression: the metrics run
  executed concurrently with other work (measurement confound) and the flight
  added heavier full-app httpx endpoint suites (~40 tests standing up the app
  `client` fixture). Recommend an isolated re-run before treating the wall-clock
  delta as real; the +66 count delta is the reliable signal. No failures, no
  flakes; the 20 warnings are pre-existing `test_pty_session`/`test_session_tools`
  notices unrelated to this flight.

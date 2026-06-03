# Mission Debrief: Discord Connector Depth & Robustness

**Date**: 2026-06-03
**Mission**: [Discord Connector Depth & Robustness](mission.md)
**Status**: completed
**Duration**: ~2026-05 → 2026-06-03 (F1 → F17; F18 alignment skipped as optional)
**Flights Completed**: 17 (F1–F17) + F18 deliberately skipped

## Outcome Assessment

### Success Criteria Results

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Discord-shaped creation form | **Met** | F1 (six-layer checklist); F17 editor cluster; behavior test `connector-editor-ux` 7/7 |
| 2 | Discord vocabulary in UI | **Met** | F1 (grep-parity verified L6); `connector-vocabulary.js` / `_discord_translate.py` held 17 flights |
| 3 | Allowlist searchable dropdowns | **Met** | F3 (`enumerate_discoverable_entities` hook); F12 hierarchical editor; stale-entry indicator |
| 4 | Routing-rules dropdowns | **Met** | F3 (same data source); id-based storage prevents the M10 "#channel-name → No agents" failure |
| 5 | Multi-user routing (live) | **Met** | F15 L4/L7 live PASS 4/4 |
| 6 | Multi-channel routing (live) | **Met** | F15 L5 live PASS 4/4 |
| 7 | Multi-peer/multi-agent (live) | **Met** | F15 L4/L6 live |
| 8 | Pairing resolved | **Met** | F9/F10 dual-flow; F17 Leg D closed the two-step DM-grant; `discord-approval-flow` 7/7 real Discord |
| 9 | Detach from Connectors screen | **Met** | F15 L7 (in-place, restart-persisted) |
| 10 | All 6 slash commands (live) | **Met** | F14; `discord-slash-end-to-end` 7/7 |
| 11 | Re-runnable HAT artifact | **Partial `[~]`** | Autonomous for multi-user/channel/agent + slash; pairing/DM-isolation inherently human (bot-can't-DM-bot, REST 50007) — apparatus constraint, not a delivery gap |
| 12 | Mentions-aware response policy | **Met** | F7 substrate → F13 per-connector; `connector-inference-provider-config-roundtrip` 8/8 |
| 13 | Peer-name attribution | **Met** | F6 substrate; F15 L4 live |
| 14 | Operator-editable directive surface | **Descoped-by-decision `[-]`** | F2 BUILT it; F5 L6 round-8 REVERTED it ("complexity seems unnecessary"); editable surface deleted, read-only display remains. Intentional |
| 15 | Pool-keying refactor | **Met** | F2 (sentinel deleted; two-primitive surface); F17 L4 extension |
| 16 | Audit-log inspector | **Met** | F13 L5; `audit-log-inspector-renders-routing-entries` 7/7 |
| 17 | Rate-limiting / backpressure | **Met (passive)** | F17: 429 substrate code-correct, no cascade under live use; disposition stream is the standing watch; synthetic harness descoped as low-yield |
| 18 | <15-min onboarding walkthrough | **Descoped-by-decision `[-]`** | Descoped at F17 planning (operator); the onboarding *surfaces* still ship (#1–4/#9), only the stopwatch gate dropped |
| 19 | Survives a full working day | **Met (operator-judged)** | F17: idle-reaper disconnect (the blocker) fixed in L4; bot ran live incl. a clean auto-reconnecting restart, instrumented; accepted in lieu of a formal stopwatch run |

**Tally: 16 Met, 1 Partial (#11, by apparatus law), 2 Descoped-by-decision (#14, #18).**

### Overall Outcome

**M11 delivered "shippable."** M10's debrief framed the gap bluntly — *"the substrate works; it's far from shippable."* M11 closed it: the Discord connector is now a typed, Discord-shaped, daily-driver-validated product, and the operator runs it as their daily driver. The mission re-specialized M10's generic connector substrate into Discord-shaped UX **without breaking the connector-agnostic substrate** (the binding constraint) — the vocabulary-substitution discipline (neutral substrate + `_discord_translate.py` + Discord-shaped UI) held across all 17 flights, leaving the second connector (Slack/Matrix) able to inherit the polish additively.

The architecture **improved on every axis the mission targeted**: the schema evolved v17→v29 (the v28/v29 pair notable for *removing* footguns, not adding fields); `admits_inbound` split cleanly into `_admits_inbound_dm`/`_admits_inbound_guild` (F12) with the F16 peers-DM-only carve-out restoring single-responsibility; the pool keying lost its sentinel footgun (F2) and gained a correct gateway-listener idle-reap exemption (F17 L4); and F17 L1 added a permanent disposition-observability layer. Two mission-level Known Issues (the F15 L7 peers-lock-out → F16; the F16 two-step DM-grant → F17 D) were root-caused and structurally fixed, not patched.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F1 | completed | Discord connector-type registration + Discord-shaped creation form (#1, #2) |
| F2 | completed | Pool-keying refactor (#15) + system-prompt directive surface (later reverted at F5) |
| F3 | completed | Live-data discoverable dropdowns (#3, #4) |
| F4 | completed | *(inserted)* UX hotfixes from F3 debrief |
| F5 | completed | *(inserted)* Connector UX cleanup; reverted the directive surface (#14) |
| F6 | completed | Peer-name attribution end-to-end (#13) |
| F7 | completed | Mentions-aware response policy (#12 substrate) |
| F8 | completed | *(inserted)* Provider-shape-portability hardening |
| F9 | completed | Pairing resolution + Connectors-screen detach (#8 substrate, #9) |
| F10 | completed | *(inserted)* ACL DM-admission + channels-axis UI split (#8) |
| F11 | completed | *(inserted)* ConnectorAccount→Connector rename + housekeeping |
| F12 | completed | Hierarchical allowlist axes; structured-tuple storage; ACL split |
| F13 | completed | Audit-log inspector (#16) + per-connector inference (#12) + slash-verify attempt |
| F14 | completed | Slash HAT closure + ACL/slash-sync 4-bug cluster fix (#10) |
| F15 | completed | Live-traffic HAT capability (#5/#6/#7/#9/#13 live) |
| F16 | completed | Pairing peers-axis decoupling (account peers → DM-only) |
| F17 | completed | **Daily-driver gate**: observability + HAT-hardening + gateway-reap fix + connector-editor + DM-approval clusters (#17, #19; closed the F16 Known Issue) |
| F18 | *(skipped)* | Optional alignment — F17 absorbed its scope |

## What Went Well

- **The rigor saved a huge mission.** The operator's verdict at debrief: *"the rigor was right — the size of the mission was HUGE and probably should have been split, but the rigor saved us."* Design-review-before-implement was empirically load-bearing on every substantive leg — it caught a would-be production-down (F17 Leg D's `models.py` validator landmine: a `{id}` row would crash `Connector.model_validate()` on every read), a would-be vacuous error-surface (F17 Leg A's connect-error swallow), and multiple wrong-vocabulary/wrong-site-count errors before a line was written.
- **The behavior-test methodology evolution is the mission's signature process win.** From M10's one-time HAT walks to committed, re-runnable Witnessed specs authored at planning time. Five active specs (`discord-slash-end-to-end`, `connector-editor-ux`, `discord-approval-flow`, `connector-inference-provider-config-roundtrip`, `audit-log-inspector-renders-routing-entries`), all PASS, several catching real bugs unit tests missed (F4's cross-surface chip staleness; the live-Discord approval loop).
- **The substrate stayed genuinely connector-agnostic.** 17 flights of Discord-specific UX and not one Discord term leaked into the substrate persist/route/ACL paths. The optional-plugin-hook-via-getattr pattern (`enumerate_discoverable_entities`, `is_alive`, `CommandHandler`) is the right additive-extension shape; a second connector inherits the polish without re-architecture.
- **Observability-as-finding-engine.** F17 L1's disposition stream (built first, per F15's lesson) turned "the bot ignored my DM" into "the gateway is disconnected" in a single grep — the reason the daily-driver soak produced actionable fixes instead of anecdotes.
- **Root-cause, not symptom.** F16 (peers axis was leaking into guild admission) and F17 Leg D (the `dm_allowed` two-step) both removed the actual defect class rather than patching the surface — each landed with a permanent reproduction regression test.
- **Agentic orchestration held at scale.** F16/F17 ran as multi-agent flight executions (design-review + implement + review crews per leg, behavior-test crews per cluster) and the handoffs, the selective-commit discipline (preserving the operator's parallel MCP fix across 7 F17 commits), and the status surfacing held up across an enormous batch.

## What Could Be Improved

- **The mission was over-scoped — it should have been split.** This is the unanimous read (operator: *"the size was HUGE and probably should have been split"*; Architect: 17 flights, kept ballooning from M10's deferrals; F17 debrief: the gate-sweep batch became a mini-mission). M11 inherited 4 M10-deferred criteria + a 7-item HAT-deferral list + a post-F8 polish list, then accreted 6 inserted flights (F4/F5/F8/F10/F11) and a 6-leg injected batch inside F17. A cleaner shape would have been **2–3 smaller missions** — e.g. *(a) connector substrate depth* (pool, ACL, structured allowlist, rename), *(b) Discord-shaped UX* (form, dropdowns, vocabulary, editor), *(c) live-traffic validation + daily-driver gate* — each with its own debrief and a legible criteria set. The rigor compensated, but a 19-criterion / 17-flight mission is hard to hold in one head and hard to debrief.
- **A criterion was built then reverted (#14 directive surface).** F2 built the operator-editable system-prompt directive surface; F5 deleted it when the operator found it unnecessary mid-HAT. That's wasted build effort that a *criterion-validation-before-build* checkpoint (confirm the operator actually wants the criterion as written before a flight implements it) would have caught.
- **Stale criteria checkboxes accumulated.** Eight criteria (#1–4, #14, #15, #17, #19) read `[ ]` at mission end despite their flights having landed — reconciled only here at the mission debrief. Mission criteria should be re-checked at each flight-debrief (or tracked in a live status table), not left to drift.
- **`_acl.py` accreted real complexity** — ~740 LOC across two direction-specific dispatchers carrying 3 axes + wildcard semantics + per-agent overlays, touched in F12/F13/F14/F16/F17. The axis-level extraction (peers/channels/roles helpers composing into the two dispatchers) was repeatedly identified and never landed; it's now a genuine maintenance risk for the next ACL-touching change.
- **Carried technical debt** (see Action Items): the `aiosqlite` "Event loop is closed" teardown warnings (since F11, survived tini); the in-memory `_connect_error_store` (F17, multi-process-unsafe + lost on restart); the polling badge/status surfaces (WS-migration deferred); the `is_dm=True` literal-on-replay (v29 stores it but the replay hardcodes it).

## Lessons Learned

- **Rigor scales to large missions; scope discipline doesn't come free.** The design-review + behavior-test cadence carried a 17-flight mission without it going off the rails — but the *right* answer was to not have a 17-flight mission. Rigor is the safety net; mission-sizing is the seatbelt.
- **Behavior-tests-as-visual-gate is the durable methodology artifact.** Real-environment, Witnessed, committed, re-runnable. It found what unit + browser tests structurally can't (cross-surface freshness, real-platform round-trips). Author the spec at planning; run it per cluster.
- **Build the observability before the soak.** The evidence surface is what converts a daily-driver soak from a vibe check into a finding engine.
- **A follow-on mission that inherits a deferral list is a scope-explosion risk.** M10's deferrals + polish list seeded M11's ballooning. Treat an inherited backlog as raw material to *triage into separately-scoped missions*, not as one mission's criteria.
- **Validate that a criterion is wanted before building it** (the #14 directive-surface revert).

## Methodology Feedback

- **Add a mission-sizing heuristic.** When a mission inherits N criteria from a prior debrief + a polish list, flag it at planning as a split candidate. A rough ceiling (criteria count, expected flight count) would have prompted the M11 split. *(Flight Control improvement.)*
- **Name + fence the "gate-sweep batch" pattern** (from F17): a validation gate's soak/once-over is the best finding environment, but findings need explicit *gate-blocking vs quality-of-life* triage so a gate flight doesn't silently absorb a mini-mission. Add the fence to the L3-style Adaptation Criteria template.
- **Reconcile mission criteria at each flight-debrief** (or a live criteria-status table) to prevent the stale-checkbox drift this mission hit.
- **The behavior-test-authored-at-planning directive worked** — keep it; it shaped apparatus + leg breakdown across F13–F17.
- **The premise-audit-includes-the-observability-axis lesson (F15) paid off again** in F17 (the disposition stream). Keep it in the flight-skill premise-audit step.

## Action Items

- [ ] **Routine-maintenance pass**: the `aiosqlite` teardown warnings (`test_db_migration.py`, since F11 — apply F11 L3's async-fixture-redesign); the `_acl.py` axis-level extraction (do NOT defer past the next ACL-touching flight); audit `connector-editor.js` for the possibly-dead `_mountAllowlistAxisEditor` (flat mount) post-F12 L5.
- [ ] **F17 carry-forwards** (fold into the next connector-touching flight): persist the last-connect-error (replace the in-memory `_connect_error_store`); read `is_dm` from the stored v29 column on replay (+ an explicit DM-only invariant assertion at the pending branch); `application_id` token-change invalidation; the "Anyone"-DM-mode "list is ignored" tooltip; a `studio.js` per-agent peer-add shape regression test.
- [ ] **Second-connector planning** (Slack/Matrix): the substrate is connector-agnostic and additively extensible; note the Discord-flavored field *names* in the allowlist schema (`guilds`, `roles` — optional, absent=unrestricted) and the `allowlist.guilds` slash-registration coupling (make the slash side optional via the getattr-sentinel pattern for non-Discord types).
- [ ] **Commit/merge the operator's parallel MCP transport fix** (the 5 files held uncommitted across F17's 7 commits) and ready **PR #87** for review.
- [ ] **Methodology** (Flight Control / mission-control): add a mission-sizing split-candidate heuristic; the gate-sweep-batch triage fence; criteria-reconciliation-at-flight-debrief.
- [ ] *(Next mission consideration)* If the directive-surface idea (#14) resurfaces, validate it's wanted before building (it was built + reverted once).

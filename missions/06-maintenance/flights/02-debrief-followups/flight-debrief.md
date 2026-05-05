# Flight Debrief: Debrief Follow-ups

**Date**: 2026-05-04
**Flight**: [Debrief Follow-ups](flight.md)
**Status**: landed
**Duration**: 2026-05-04 (single-day session)
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

The flight closed all 6 explicit action items surfaced by Flight 01's debrief — but with a notable twist: **3 of the 6 items were discovered during design review to be already-satisfied by prior commits**, and were marked `[x]` with annotations rather than re-implemented.

| Action Item | Outcome | Notes |
|---|---|---|
| `OriginAllowlistMiddleware` + `_is_safe_provider_url` documented in `agents.md` | Implemented | Leg 01: 2 new architectural subsections + 1 module-map row |
| `THE_ONE_ORIGIN_ALLOWLIST` env var documented in `CLAUDE.md` | Implemented | Leg 01: 2-line callout in Security posture section |
| `api.py:810` resolved-URL-validation rationale captured in code | **Already satisfied** | Discovered: 5-line block at L805-809 already shipped by F01 L05 |
| WebSocket-with-no-Origin behavior locked in by test | Implemented | Leg 02: `test_websocket_with_no_origin_passes` |
| `test_provider` happy-path test added | **Already satisfied** | Discovered: `TestConnectionTest` (L653-768) already covers it |
| Origin-allowlist `OPTIONS` method behavior documented or gated | Implemented (path-b) | Leg 03: 3-line rationale comment + `SECURITY-MODEL.md` Future Work bullet |
| X-Forwarded-Host / trusted-proxy posture documented | Implemented | Leg 03: `SECURITY-MODEL.md` Future Work bullet |
| Host-env dependency gap closed | **Already satisfied** + guardrail | Discovered: closed by commit `e65077e` (F05); Leg 04 added 4-line guardrail comment |
| Concourse admin password rotated | Implemented | Leg 05: out-of-tree credential rotation; epipen audit zero matches |

### Mission Criteria Advanced

This flight did NOT advance the mission's original 14 success criteria (those landed in Flight 1). It absorbed Flight 01's debrief action items — gaps visible only AFTER the architectural changes landed. As a result, the flight strengthened mission outcomes indirectly: documentation now matches code, the OPTIONS-not-gated decision is explicit (preventing future "fixes" that break preflight), and the `pyproject.toml` guardrail prevents regression of an earlier fix.

## What Went Well

1. **Design-review-pass methodology paid off three times.** All three already-satisfied retirements (api.py:810, test_provider happy-path, host-env deps) were caught in design review's round-1 pass — before any implementation work. This is the explicit Flight 01 methodology learning ("re-grep cited line numbers before locking the leg") working as designed.

2. **Atomic doc-only legs validated.** Leg 01 shipped 9 lines to `agents.md` + 2 to `CLAUDE.md` as a first-class leg. Without atomicity, these would have been lost in larger work and the api.py:810 retirement would not have been caught at design-review granularity.

3. **Path-locking under design review prevented implementer ambiguity.** Leg 03's path-(b) decision (document OPTIONS, don't gate) was made during design review with the decisive CORS-preflight-footgun argument. Leg 04 was rescoped from "fix the gap" to "guardrail comment" the same way. Both prevented spending implementation time on the wrong target.

4. **Traceability convention `(M0X F0Y L0Z)` reinforced.** Both new `agents.md` subsections used the established pattern, making it easy for a reader to trace any architectural entry back to the flight that introduced it.

5. **Guided-manual leg shipped clean.** Leg 05 (admin pass rotation) walked the operator through 8 steps with the password never logged or transmitted to the Flight Director. Audit trail lives entirely in the flight log.

6. **Reviewer agent confirmed cleanly on first pass.** No fix/review loop needed at flight close — `[HANDOFF:confirmed]` came back on the first review with all 6 files + artifacts approved.

## What Could Be Improved

### Process

- **Pre-flight reconnaissance grep audit missing.** When a flight's premise is "land debrief action items", the flight design phase needs a one-pass re-grep of every cited file/line/symbol against current HEAD before drafting legs. Three of five legs would have been pre-rescoped, saving 6 design-review cycles for 5 legs (1.2 cycles/leg average).
- **Decisions binding multiple legs should live in flight.md, not surface during leg design review.** The OPTIONS path-b lock (made during Leg 03 design review) is a project-architecture stance about CORS posture; it affected docstring, code comment, test, and SECURITY-MODEL.md content. Locking in flight.md upfront would have shaved one design-review cycle off Leg 03.
- **Acceptance Criteria checklist (flight.md L10-18) was retroactively annotated** with "already satisfied" markers. Three of the original "6 explicit action items" were ghost work. A pre-flight grep audit would have rescoped the flight to 3-4 legs upfront with no ghost items.

### Technical

- **PATCH coverage missing in `OriginAllowlistMiddleware` rejection-path tests.** Existing per-method 403 tests cover POST/PUT/DELETE; PATCH is in `GATED_METHODS` but has no rejection-path test. Pre-existing gap noted during Leg 03 design review as out-of-scope.
- **`_is_safe_provider_url` called at three endpoints with identical surrounding logic.** A small `validate_resolved_provider_url(provider)` helper would dedupe `create_provider:772`, `update_provider:811`, `test_provider:864`. Low priority — current call sites are explicit and traceable.
- **`mission.md` Flight 2 entry checkoff was deferred to post-merge cleanup.** The deferred-commit pattern stacked on Flight 1's branch + `mission.md` checkoff living in stash@{0} created a branch-strategy entanglement. Documented as a runtime decision in `flight-log.md` Decisions section but worth a methodology note (see Recommendations).

### Documentation

- **Traceability convention `(M0X F0Y L0Z)` is informal.** Both Developer and Architect noted it should be promoted — document explicitly in CLAUDE.md or `agents.md` preamble so future flights apply it consistently.
- **Flights with guided-manual legs need an explicit "audit trail in flight-log only" framing in flight.md.** Reviewers don't expect zero-diff legs unless told.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 01 dropped api.py:810 change (already shipped) | Design-review surfaced existing 5-line block at L805-809 | Yes — codify "re-grep all cited lines before drafting" |
| Leg 02 dropped `test_provider` happy-path (already covered) | Design-review surfaced `TestConnectionTest` (L653-768) | Same |
| Leg 04 rescoped from "fix gap" to "guardrail comment" | Design-review found commit `e65077e` (F05) closed the gap | Same |
| Leg 03 OPTIONS path-b decision made at leg level, not flight level | Path-b was the YAGNI-aligned choice but not pre-locked in flight.md | Yes — promote multi-leg decisions to flight.md |
| `mission.md` Flight 2 checkoff deferred to post-merge | Stash interaction with Flight 1's pending PR #25 | Yes — when stacking pre-merge flights, mission/flight checkoffs land on upstream flight only |

## Key Learnings

1. **Debrief action items drift fast.** Flight 05 silently closed Flight 01's host-env gap weeks before Flight 02 tried to fix it again. **Assumption to revisit:** that debrief recommendations remain accurate between write-time and follow-up-flight-execution-time. They don't — other flights land in between.

2. **Design-review-pass is the safety net for stale debriefs.** All three retirements were caught in round-1 of leg design review. The cost was 6 design-review cycles for 5 legs (1.2/leg); the benefit was zero ghost-work implementation. Net positive.

3. **Atomic legs amplify both the cost and value of design review.** Doc-only legs that would have been absorbed into larger work get their own design pass — which is when ghost items get caught. The atomicity discipline is doing real work, not just bookkeeping.

4. **The deferred-commit pattern remains the right shape for atomic doc/test/comment flights.** Used twice now (F01 + F02). Branch-strategy complexity (Flight 2 stacked on Flight 1's pending PR; mission.md checkoff deferred) is a known cost — manageable with explicit documentation.

5. **Guided-manual legs (zero-diff) need explicit framing.** Leg 05 produces no committed code; the audit trail IS the artifact. Reviewers and PR readers need to know this upfront.

## Recommendations

1. **Add a "pre-flight reconnaissance" step to the `/flight` skill** — when the flight's premise is "land debrief action items" or any backward-looking work, require a re-grep of every cited file/line/symbol against current HEAD before drafting legs. Surface already-satisfied items in flight.md as `[x]` with annotation rather than as draft legs.

2. **Promote multi-leg decisions to flight.md.** Add a checklist item to the `/flight` skill: "Identify any decisions that bind ≥2 legs (e.g., path choices, naming conventions, API stances) and lock them in flight.md Design Decisions, NOT in individual leg specs."

3. **Document the `(M0X F0Y L0Z)` traceability convention** in CLAUDE.md or `the_one/agents.md` preamble. Both Developer and Architect flagged it as a pattern worth standardizing.

4. **Codify branch-strategy guidance for stacked pre-merge flights.** When Flight N+1 stacks on Flight N's pending PR, mission/flight checkoffs in `mission.md` land on the upstream flight's branch ONLY (avoid stash-pop conflicts). Document in agentic-workflow skill or in a Mission-Control-level methodology note.

5. **Spawn a small follow-up flight (or absorb into Flight 3 — Dependency Refresh) for the missing PATCH rejection-path test** in `tests/test_origin_allowlist.py`. The leg would be tiny: one parametrize-or-add-mirror test edit.

## Action Items

- [ ] Update `/flight` skill: add pre-flight reconnaissance step for backward-looking flights (debrief follow-ups, maintenance fixes, etc.)
- [ ] Update `/flight` skill: add explicit "multi-leg decisions belong in flight.md" checklist item
- [ ] Document `(M0X F0Y L0Z)` traceability convention in `the-one`'s CLAUDE.md or `agents.md`
- [ ] Document branch-strategy guidance for stacked pre-merge flights in `/agentic-workflow` skill
- [ ] Schedule small follow-up: add PATCH rejection-path test to `tests/test_origin_allowlist.py`
- [ ] (Post-merge cleanup) Verify `mission.md` Flight 2 checkoff state on `main` after both PRs merge; clean up any drift
- [ ] (Optional refactor) Extract `validate_resolved_provider_url(provider)` helper to dedupe three call sites in `the_one/interfaces/web/api.py`

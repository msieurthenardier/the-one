# Mission Debrief: Maintenance — Pre-Mission-06 Quick Wins

**Date**: 2026-05-04
**Mission**: [Maintenance — Pre-Mission-06 Quick Wins](mission.md)
**Status**: completed
**Duration**: 2026-05-04 (single-day session)
**Flights Completed**: 2 of 3 (Flight 3 de-scoped — see Outcome Assessment)

## Outcome Assessment

### Success Criteria Results

All 14 success criteria met. The mission's stated outcome — "Resolve codebase health issues identified in maintenance report 2026-05-04. Land 14 Action Required findings as 7 bundled, atomic legs in a single focused flight" — was achieved by Flight 1 alone. Flight 2 then absorbed the action items surfaced by Flight 1's debrief.

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Test suite green on `main` (host + container) | Met | F1 L1 — 1077 passed, 1 skipped, 6 deselected |
| CI runs `ruff check` + `ruff format --check` against `the_one/` + `tests/`; `workspace/` excluded | Met | F1 L1 — `extend-exclude` in `pyproject.toml`; chained into existing `sh -c` in `ci/pipeline.yml` |
| One-shot `ruff format` + `ruff check --fix` applied; 30 lint errors resolved | Met | F1 L1 — 14 auto-fixed + 6 manual + 74 reformatted; 0 errors remain |
| Chat surface meets WCAG 2.1 AA baseline | Met | F1 L2 — `role="log" aria-live="polite"` on chat log; `aria-label="Message"` on input; `field-info-icon` → `<button type="button" aria-describedby="…-desc">` |
| All 4 Concourse pipeline images pinned | Met | F1 L3 — 7 image refs pinned to digests/tags; `playwright==1.58.0` |
| `.dockerignore` exists at repo root | Met | F1 L3 |
| `auto-rollback` re-runs healthcheck + fails loudly | Met | F1 L4 — post-rollback healthcheck loop in `deploy.sh`; explicit "ERROR: app never came up after 60s" in pipeline |
| Healthcheck loop fails loudly on 12/12 attempts | Met | F1 L4 |
| Origin-allowlist middleware rejects state-mutating disallowed-origin requests | Met | F1 L5 — `OriginAllowlistMiddleware` (ASGI); 18 tests + 1 from F2 |
| LLM provider configurations with non-https `base_url` warned/refused | Met | F1 L5 — `_is_safe_provider_url` at create/update/test endpoints |
| Local Concourse + admin passwords rotated | Met | F1 L6 (the-one team) + F2 L5 (admin); both old passwords verified rejected |
| `SECURITY-MODEL.md` documents no-auth posture, single-user local, dev-mode bind | Met | F1 L7 + F2 L3 (Future Work additions: CORS/OPTIONS, X-Forwarded-Host) |

### Overall Outcome

**Mission target achieved at Flight 1 close**; Flight 2 strengthened the outcome by closing documentation/test gaps and an OPTIONS-decision loop that became visible only after Flight 1's architectural changes landed. **Flight 3 (Dependency Refresh) is de-scoped from this mission** per Architect recommendation: dependency refresh is mechanical work better suited to the next `/routine-maintenance` cycle when staleness is re-quantified, rather than mission overhead.

Stakeholder value: solo developer/operator now has (1) green tests on a clean host install, (2) lint enforced in CI, (3) explicit security threat model + Origin-allowlist defense-in-depth, (4) rotated credentials with old passwords invalidated, (5) hardened CI pipeline with pinned images and explicit healthcheck failure modes. The codebase is materially safer to operate and easier to onboard onto.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F1 — Pre-Mission-06 Quick Wins | completed (PR #25) | 7 atomic legs, 14 success criteria met, single deferred-commit at `d813370`. Origin-allowlist middleware + provider-URL validator + Security-Model artifact were the highest-impact deliverables. |
| F2 — Debrief Follow-ups | completed (PR #26) | 5 atomic legs, 6 explicit action items closed (3 of which discovered already-satisfied during design review). Documentation alignment + edge-case test + OPTIONS-decision lock + host-env guardrail + admin-pass rotation. |
| F3 — Dependency Refresh | de-scoped | Optional/separable per mission.md; Architect recommended absorption into the next `/routine-maintenance` cycle rather than spawning a mini-mission. |

## What Went Well

1. **Design-review-per-leg as a stale-recommendation safety net.** F1 caught 5+ substantive errors before implementation; F2 caught 3-of-5 ghost items in round-1 review. Atomicity + per-leg design review converts stale debrief drift into pre-implementation rescoping. **This is the dominant architectural lesson of the mission.**

2. **Deferred-commit-across-multiple-legs validated twice.** F1 (7 legs in one commit) and F2 (5 legs in one commit) both produced coherent diffs with single Reviewer passes that approved on first try. Branch-strategy entanglement when stacking pre-merge flights is a known cost (documented).

3. **Threat model promoted from tribal knowledge to artifact.** `SECURITY-MODEL.md` at repo root is the largest single architectural improvement of the mission — the no-auth posture, single-user local-only stance, and SSRF/subprocess boundaries are now first-class documentation rather than scattered notes in `agents.md`.

4. **Origin-allowlist middleware as ASGI** (not `Depends()`). F1 L5 design review correctly pinned ASGI as required because `Depends()` runs after `ws.accept()` and cannot gate WebSocket upgrades. Subtle catch, real bug avoided.

5. **Guided-manual leg protocol used cleanly twice** (F1 L6 the-one team rotation; F2 L5 admin rotation). Live secrets + shared infrastructure deserved the explicit protocol; both rotations completed safely with zero credential leakage to the Flight Director.

6. **Test quality is uniformly behavioral.** No mock-assertion-shaped tests. `test_origin_allowlist.py` exercises real middleware via `TestClient`; `test_provider_api.py` legacy-row `__MASKED__` case exercises the resolved-base_url contract end-to-end.

7. **Reviewer agent confirmed cleanly on first pass** in both flights. No fix/review loops needed at flight close. Suggests the design-review-pass investment pays off downstream.

## What Could Be Improved

### Process

- **Stale-recommendation drift between debrief-write and follow-up-flight-execution is systemic.** F1's debrief was written without re-grepping cited line numbers; F2 then encountered 3-of-5 already-satisfied items because the recommendations had drifted (other flights — including M05 F5 silently closing the host-env gap — landed in between). Same root cause across both flights.
  - **Recommendation**: pre-flight reconnaissance step. When a flight's premise is "land debrief action items" or any backward-looking work, re-grep every cited file/line/symbol against current HEAD before drafting legs. Surface already-satisfied items in flight.md as `[x]` with annotation rather than as draft legs.

- **Multi-leg decisions surfaced during leg design review instead of flight design.** The OPTIONS path-b lock (made during F2 L3 design review) affected docstring, code comment, test content, and `SECURITY-MODEL.md` content — a project-architecture stance, not leg-local reasoning.
  - **Recommendation**: `/flight` skill checklist item: "Identify any decisions that bind ≥2 legs (e.g., path choices, naming conventions, API stances) and lock them in flight.md Design Decisions, NOT in individual leg specs."

- **Maintenance-report → leg-spec gap.** Line numbers, helper-function counts, and test file names all drifted between `maintenance/2026-05-04.md` and code at leg-spec time. Maintenance reports were generated *without* re-grepping at leg-generation time.
  - **Recommendation**: maintenance reports cite **stable identifiers** (function names, route paths, class names, CSS selectors) rather than line numbers — OR `/leg` skill auto-greps and substitutes before locking the artifact.

- **"≤4 file touches" rule too rigid for infrastructure-introducing legs.** F1 L1 modified 5 named files PLUS 74 ruff-formatted files. The 74 are formatting churn, not semantic edits.
  - **Recommendation**: reframe as "≤4 *semantically distinct* changes" so format-only files don't count against the budget. F2 already adopted this framing implicitly.

### Technical

- **PATCH coverage missing in `OriginAllowlistMiddleware` rejection-path tests.** Existing per-method 403 tests cover POST/PUT/DELETE; PATCH is in `GATED_METHODS` but has no rejection-path test. Pre-existing gap. **Quick win** (5 min): parametrize-or-add-mirror in next maintenance pass.

- **`_is_safe_provider_url` 3-call-site DRY is borderline.** Currently explicit and traceable; acceptable. **Monitor**: revisit if a 4th call site appears or behavior diverges.

- **`up=true|false` shell pattern duplicated** in `ci/deploy.sh:28-39` and `ci/pipeline.yml:73-86`. Could become `ci/lib/health-check.sh`. **Low priority** — drift risk is small.

- **`OPTIONS` not gated** is now explicit by-design (path-b documented in `middleware.py` + `SECURITY-MODEL.md` Future Work). **Revisit only if cross-origin browser deployment becomes real.**

- **CI image pins will drift.** Quarterly check should be a `/routine-maintenance` checklist item.

### Documentation

- **Cross-cutting-policy-vs-per-resource-authorization placement guidance is missing.** `_is_safe_provider_url` is per-call-site; `OriginAllowlistMiddleware` is ASGI middleware. Both correct for their domain, but the distinction should be documented in `agents.md` so future contributors don't conflate them.

- **Traceability convention is informal.** F2 introduced two `(M06 F1 L5)` markers in `agents.md`; existing markers use bare `(F4 L2)` / `(F5 L4)` (implicitly mission-scoped to the authoring mission). No retroactive migration is planned, but the convention should be documented for future cross-mission entries.

- **Guided-manual legs need explicit "audit trail in flight-log only" framing in flight.md** so reviewers don't expect a code diff.

## Lessons Learned

### Technical

1. **WS upgrade gating MUST happen at ASGI layer**, not via FastAPI `Depends()`. `Depends()` runs after `accept()`; ASGI middleware runs before. Load-bearing distinction for any future WS-gating work.
2. **Validation on the resolved model, not the request payload**, is the right shape when masked/sentinel values are in the merge path. Pydantic validators on the request shape would miss `__MASKED__`-resolved values.
3. **Cross-cutting request-policy → ASGI middleware; per-resource authorization → `Depends()`.** Worth promoting to `agents.md`.

### Process

1. **Stable identifiers > line numbers** for cross-artifact references. Line numbers drift; function names, route paths, class names, and CSS selectors don't.
2. **Design-review pass should always re-grep** any line-number-bearing claim. F1 caught 4-of-7; F2 caught 3-of-5. ~50% catch rate is high enough to be structural.
3. **Atomic commit per maintenance flight** beats per-leg commits for diff coherence and review surface — IF legs are independent (no leg blocks another's review).
4. **Guided-manual legs are a real protocol category**, not a fallback for "we couldn't automate it." Live secrets, shared infrastructure, and operator-eyes-on-glass scenarios deserve the explicit protocol.

### Domain

1. **Debrief recommendations have a half-life.** Other flights land in between debrief-write and follow-up-execution. Treat debrief items as expiring inventory: re-verify before acting.
2. **`SECURITY-MODEL.md` is now the canonical home** for threat-model decisions. Future security-related flights should add to its Future Work section rather than scatter notes across debriefs.

## Methodology Feedback

Direct improvements proposed for Mission Control's skills:

1. **`/flight` skill** — add pre-flight reconnaissance step for backward-looking flights (debrief follow-ups, maintenance passes). Re-grep every cited file/line/symbol against current HEAD before drafting legs. Surface already-satisfied items as `[x]` annotations rather than draft legs.
2. **`/flight` skill** — add explicit checklist item: "Identify decisions that bind ≥2 legs and lock them in flight.md Design Decisions, NOT in individual leg specs."
3. **`/leg` skill** — auto-grep cited line numbers + substitute stable identifiers (function name, route path, class name) before locking the leg artifact. Captures the line-number-drift learning as methodology.
4. **`/agentic-workflow` skill** — codify branch-strategy guidance for stacked pre-merge flights: when Flight N+1 stacks on Flight N's pending PR, mission/flight checkoffs in `mission.md` land on the upstream flight's branch ONLY (avoid stash-pop conflicts).
5. **`/agentic-workflow` skill** — document guided-manual legs as a first-class protocol category (not a "fallback when automation fails"). Include the "audit trail lives in flight-log only" framing.
6. **`/routine-maintenance` skill** — maintenance reports should cite stable identifiers (function names, route paths, class names) rather than line numbers, OR include a "verify against current HEAD" step before delivering.
7. **`/routine-maintenance` skill** — add CI image pin staleness as a recurring quarterly check.
8. **Maintenance-mission template** — reframe "≤4 file touches" as "≤4 semantically distinct changes" so format-only churn doesn't count against the budget.

## Action Items

### Immediate (this repo / next maintenance cycle)
- [ ] Add PATCH rejection-path test to `tests/test_origin_allowlist.py` (5-minute parametrize-or-mirror)
- [ ] Document `(M0X F0Y L0Z)` traceability convention in `the_one/agents.md` preamble (and the historical `(F{X} L{Y})` mission-scoped form for context)
- [ ] (Post-merge) Verify `mission.md` Flight 2 checkoff state on `main` after PR #25 + PR #26 both merge
- [ ] Add cross-cutting-policy-vs-per-resource-authorization placement guidance to `agents.md`
- [ ] Schedule next `/routine-maintenance` cycle to absorb F3 work (dependency refresh) + the small follow-ups listed above

### Methodology (mission-control repo)
- [ ] Update `/flight` skill: pre-flight reconnaissance step + multi-leg-decision checklist
- [ ] Update `/leg` skill: auto-grep line numbers + substitute stable identifiers
- [ ] Update `/agentic-workflow` skill: stacked-flight branch strategy + guided-manual leg protocol
- [ ] Update `/routine-maintenance` skill: stable-identifier convention + CI image pin staleness check
- [ ] Update maintenance-mission template: reframe "≤4 file touches" → "≤4 semantically distinct changes"

### Forward-looking (future missions)
- [ ] When dependency refresh becomes urgent, bundle into next maintenance cycle rather than spawning a mini-mission
- [ ] Monitor `_is_safe_provider_url` for 4th call site as trigger for `validate_resolved_provider_url(provider)` extraction
- [ ] Cross-project sync with epipen if/when a future change affects shared Concourse infrastructure

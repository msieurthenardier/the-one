# Flight: Debrief Follow-ups

**Status**: completed
**Mission**: [Maintenance — Mission 06](../../mission.md)

## Contributing to Criteria

This flight does NOT advance the mission's original 14 success criteria (those landed in Flight 1). It absorbs the action items surfaced by Flight 1's debrief — gaps that became visible only AFTER the architectural changes landed.

- [x] `OriginAllowlistMiddleware` and `_is_safe_provider_url` documented in `the_one/agents.md`
- [x] `THE_ONE_ORIGIN_ALLOWLIST` env var documented in `CLAUDE.md`
- [x] `api.py:810` resolved-URL-validation rationale captured in code (already satisfied — Flight 01 Leg 05 shipped a 5-line block at L805-809; design-review surfaced this in Leg 01 design pass)
- [x] WebSocket-with-no-Origin behavior locked in by test
- [x] `test_provider` happy-path test added (already satisfied — `TestConnectionTest` at `tests/test_provider_api.py:653-768` covers it via `test_openai_compatible_success`/`test_openai_success`/`test_anthropic_success`; design-review surfaced this in Leg 02 design pass)
- [x] Origin-allowlist `OPTIONS` method behavior documented or gated
- [x] X-Forwarded-Host / trusted-proxy posture documented in `SECURITY-MODEL.md`
- [x] Host-env dependency gap closed (either `pyproject.toml` shift OR CLAUDE.md `pip install '.[dev]'` bootstrap)
- [x] Concourse admin password rotated (cross-project with epipen, guided-manual)

---

## Pre-Flight

### Objective

Land the 6 explicit action items from Flight 01's debrief as 5 atomic legs in a single deferred-commit. Each leg is ≤4 semantically distinct changes (per the debrief's reframing of the original "≤4 file touches" rule). No new architectural changes; this flight closes loops that Flight 01 opened.

### Open Questions

N/A — all design decisions are absorbed into per-leg Acceptance Criteria.

### Design Decisions

**Doc-only legs are first-class** (Bundle A): the 4 doc patches + 2 tests live as their own legs rather than being absorbed into the legs that introduced the surfaces. Rationale: the debrief specifically called out documentation as a separate dimension; treating docs as a leg-class makes the methodology gap visible.
- Rationale: Flight 1's per-leg commits skipped doc updates. Treating docs as a first-class leg in this flight is the corrective; future maintenance should absorb doc-as-it-goes.
- Trade-off: 2 small legs instead of 1 medium leg. Acceptable — atomicity wins over consolidation.

**X-Forwarded-Host: document, don't implement** (Bundle C): the project deploys behind no proxy today; trusted-proxy support is hypothetical. Document the limitation in `SECURITY-MODEL.md` Future Work; do NOT add `X-Forwarded-Host` parsing.
- Rationale: implementing trusted-proxy parsing without a real consumer is YAGNI; documenting the limitation lets a future operator make the decision when they actually deploy behind a proxy.
- Trade-off: future operator will hit this when they need it. Acceptable — same posture as the rest of the project's "operator-trusted local" stance.

**Host-env dependency gap: pick lighter remediation** (Bundle D): the Inspector's Leg 01 finding was that `markdownify` and `readability-lxml` are missing from `~/.local`. The fix is either (a) shift to base deps in `pyproject.toml` (broader install) or (b) document `pip install '.[dev]'` as host bootstrap in CLAUDE.md. Default is (b) — single-line doc fix is lower-risk than reshaping the dependency graph.
- Rationale: changing dep tiers can break downstream packaging assumptions; documenting the bootstrap is reversible and zero-risk.
- Trade-off: developers who skip CLAUDE.md still hit the gap. Acceptable — CLAUDE.md is the project's onboarding doc and this is a maintenance flight, not a dev-experience overhaul.

**Admin Concourse password rotation: include despite cross-project scope** (Bundle E): the admin pass is shared with epipen but the credential is in the-one's git history (`.claude/settings.local.json` add-commits). Closing the loop is the-one's responsibility even though epipen also needs to update. Coordinate with epipen separately.
- Rationale: deferring would leave a known leak in history forever. The rotation procedure is identical to Leg 06; only the coordination delta is new.
- Trade-off: requires the operator to run a parallel sync in epipen's environment. Acceptable — guided-manual leg with explicit out-of-tree steps.

### Prerequisites

- [x] Flight 1 (Pre-Mission-06 Quick Wins) completed
- [x] Flight 1 PR #25 open (this flight's commit can land on the same branch OR a fresh branch — see Adaptation Criteria)
- [x] `SECURITY-MODEL.md` exists at repo root (created in Flight 1 Leg 07)
- [x] `OriginAllowlistMiddleware` exists at `the_one/interfaces/web/middleware.py` (created in Flight 1 Leg 05)
- [x] `_is_safe_provider_url` exists in `the_one/interfaces/web/api.py` (created in Flight 1 Leg 05)

### Pre-Flight Checklist

- [x] All open questions resolved (N/A)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined (per-leg Acceptance Criteria + Verification Steps)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Same atomic-leg + design-review-pass + deferred-commit pattern as Flight 1. Each leg ≤4 semantically distinct changes. Reviewer pass at flight close, single atomic commit, draft PR (or extend PR #25's branch with a second commit if the human prefers stacked).

For each leg:
1. Implementer reads the leg's acceptance criteria + implementation guidance
2. Design-review pass (Developer agent re-grep cited line numbers — methodology learning from Flight 1)
3. Implements the change
4. Verifies via the leg's verification steps
5. Updates `flight-log.md` with progress entry
6. Marks leg `landed`, checks off in `flight.md`

After all 5 legs land:
1. Single Reviewer pass (code correctness + doc correctness)
2. Atomic commit + flight-debrief

### Checkpoints

- [x] Leg 01 completed: `agents.md` middleware/validator entries; `agents.md` `web/middleware.py` module-map row; `CLAUDE.md` env var callout *(api.py:810 rationale comment retired — already shipped in Flight 01 Leg 05)*
- [x] Leg 02 completed: WS-no-Origin pass-through test *(test_provider happy-path retired — already covered by `TestConnectionTest` in `test_provider_api.py:653-768`)*
- [x] Leg 03 completed: Origin-allowlist `OPTIONS` behavior documented or gated; X-Forwarded-Host posture in SECURITY-MODEL.md Future Work
- [x] Leg 04 completed: host-env dependency gap closed (CLAUDE.md `pip install '.[dev]'` bootstrap entry, or `pyproject.toml` shift if implementer prefers)
- [x] Leg 05 completed: Concourse admin password rotated; `.env` re-seeded; epipen audit returned zero matches (admin is operator-direct, no epipen project-file references)

### Adaptation Criteria

**Divert if**:
- Bundle E (admin password rotation) reveals epipen has an active live process that depends on the old admin credential — coordinate with epipen first, defer leg until safe to rotate
- Bundle C `OPTIONS` gating audit reveals an unexpected CORS need (e.g., a future browser extension or external client) — document, do NOT add CORS handling in this flight
- Any leg requires schema migration or new dependencies — STOP, surface as out-of-flight-scope

**Acceptable variations**:
- Bundle D (host-env dependency) implementer's call: CLAUDE.md doc OR `pyproject.toml` shift. Doc is the default per design decision; the bigger change is acceptable if the implementer has a clean rationale.
- Flight commit can land as a 2nd commit on Flight 1's branch (`flight/01-pre-mission-06-quick-wins`) OR a fresh `flight/02-debrief-followups` branch. Implementer's call based on PR #25's review status.
- Bundle A (doc patches) can be split into two legs (agents.md edits separate from CLAUDE.md/api.py comment) if the implementer prefers tighter atomicity. The 5-leg layout below is a recommendation, not a contract.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `01-doc-patches` — `agents.md` entries for `OriginAllowlistMiddleware` + `_is_safe_provider_url` + module-map row for `web/middleware.py`; `CLAUDE.md` callout for `THE_ONE_ORIGIN_ALLOWLIST` *(api.py rationale retired — already shipped in F01 L05)*
- [x] `02-edge-case-tests` — WS-no-Origin pass-through test *(test_provider happy-path retired — already covered by `TestConnectionTest`)*
- [x] `03-origin-allowlist-followups` — `OPTIONS` method behavior (gate or document); X-Forwarded-Host posture in `SECURITY-MODEL.md` Future Work
- [x] `04-host-env-dependency-clarity` — CLAUDE.md `pip install '.[dev]'` bootstrap step (default), or `pyproject.toml` dep-tier shift (if implementer prefers)
- [x] `05-admin-pass-rotation` — guided-manual rotation of Concourse admin pass + epipen coordination note (zero matches)

---

## Post-Flight

### Completion Checklist

- [ ] All 5 legs completed
- [ ] Code merged to `main` via PR (either as part of PR #25 or a separate Flight 2 PR)
- [ ] `pytest` green (host + container)
- [ ] Browser tests green
- [ ] `ruff check` and `ruff format --check` clean
- [ ] Documentation updated (agents.md, CLAUDE.md, SECURITY-MODEL.md)
- [ ] Flight 01 debrief action items checked off

### Verification

To confirm the flight achieved its objective:

1. **agents.md docs**: `grep -A 2 "OriginAllowlistMiddleware\|_is_safe_provider_url" the_one/agents.md` shows both entries with surrounding architectural context.
2. **CLAUDE.md env var**: `grep "THE_ONE_ORIGIN_ALLOWLIST" CLAUDE.md` returns at least one line referencing the allowlist behavior.
3. **api.py rationale comment** *(retired — already satisfied)*: `sed -n '805,809p' the_one/interfaces/web/api.py` shows the existing 5-line rationale block shipped in Flight 01 Leg 05.
4. **WS-no-Origin test**: `grep "no_origin\|missing.origin\|websocket.*no_origin" tests/test_origin_allowlist.py` returns at least one test asserting WS pass-through with no Origin header.
5. **test_provider happy path** *(retired — already satisfied)*: `grep -n "TestConnectionTest\|test_openai_compatible_success\|test_openai_success\|test_anthropic_success" tests/test_provider_api.py` shows the existing happy-path coverage (L653, L688, L716, L738).
6. **OPTIONS behavior**: either `grep "OPTIONS" the_one/interfaces/web/middleware.py` shows the method gated, OR `grep "OPTIONS" SECURITY-MODEL.md` documents the limitation in Future Work.
7. **X-Forwarded-Host posture**: `grep -A 3 "X-Forwarded\|reverse proxy\|trusted proxy" SECURITY-MODEL.md` shows a Future Work entry.
8. **Host-env bootstrap**: `grep "pip install.*\[dev\]\|markdownify\|readability" CLAUDE.md` shows the bootstrap step (default path), OR `pyproject.toml` shows the dep moved to base.
9. **Admin pass rotated**: `fly -t local login -p '<NEW_ADMIN>'` succeeds; old admin password (`ZTul...`) fails.

# Flight: Pre-Mission-06 Quick Wins

**Status**: landed
**Mission**: [Maintenance — Pre-Mission-06 Quick Wins](../../mission.md)

## Contributing to Criteria
- [x] Test suite green on `main` for both container and host runs
- [x] CI runs `ruff check` and `ruff format --check`; `workspace/` excluded
- [x] Chat surface meets WCAG 2.1 AA keyboard + SR baseline
- [x] All four Concourse pipeline images pinned; Playwright pinned in `pyproject.toml`
- [x] `.dockerignore` exists with appropriate excludes
- [x] `auto-rollback` re-runs health-check; healthcheck timeout fails loudly
- [x] Origin-allowlist middleware rejects disallowed origins
- [x] Non-`https://` provider URL for non-localhost hosts is warned/refused
- [x] Local Concourse passwords rotated; `.env` updated
- [x] `SECURITY-MODEL.md` documents no-auth posture; stale agents.md lines updated

---

## Pre-Flight

### Objective

Land 14 Action Required findings from maintenance/2026-05-04.md as 7 bundled atomic legs in a single focused session. Each leg is ≤4 file touches, no architectural change, no schema migration, and ends with a green test suite.

### Open Questions

N/A — all design decisions are absorbed into per-leg Acceptance Criteria.

### Design Decisions

**No git history rewrite (Bundle F)**: rotate Concourse passwords + update `.env`, but do NOT use `git filter-repo` / BFG.
- Rationale: private repo, single-dev, localhost-only Concourse — practical exposure is the operator themselves.
- Trade-off: old passwords remain in git history. Acceptable because rotation invalidates them.

**No new auth (Bundle G)**: `SECURITY-MODEL.md` documents the no-auth posture rather than adding auth.
- Rationale: F3 Decision 10 ("operator-trusted setup, NOT malicious actor") is the project's documented threat model. Adding auth would violate posture.
- Trade-off: explicit doc instead of implicit decision; future contributors / operators see the posture.

**Origin-allowlist as middleware, not endpoint-level (Bundle E)**: a small ASGI middleware in `the_one/interfaces/web/` checks `Origin`/`Referer` against `settings.host` allow-list at request time.
- Rationale: cheap mitigation that doesn't violate no-auth posture; closes drive-by-LAN attack surface.
- Trade-off: middleware adds one indirection on every request; negligible perf cost.

**Convert `field-info-icon` to a real `<button>` element (Bundle B / A.3)**: the existing `<span>` cannot be made keyboard- or SR-accessible without changing the element. Use `<button type="button" aria-describedby="<field-id>-desc">` plus a hidden `<span id="<field-id>-desc">`.
- Rationale: native `title` attribute is mouse-only; `aria-label` on non-interactive `<span>` is largely ignored; semantic correctness requires a real focusable element.
- Trade-off: small CSS adjustment for the new button element (existing chrome is `cursor: help` on the span). Acceptable.

### Prerequisites

- [x] Mission 05 (Built-In Tool System) completed
- [x] Maintenance report at `maintenance/2026-05-04.md` exists
- [x] Maintenance mission at `missions/06-maintenance/mission.md` created
- [x] Test suite passes pre-flight on container; identifying that 2 tests fail on host is the trigger

### Pre-Flight Checklist

- [x] All open questions resolved (N/A)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined (per-leg Acceptance Criteria + Verification Steps)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Each leg is a discrete bundle from maintenance/2026-05-04.md. Legs are independent — partial completion is acceptable if priorities shift mid-flight. Recommended order is the leg sequence below (low-risk first), but no leg blocks another.

For each leg:
1. Implementer reads the leg's acceptance criteria and implementation guidance
2. Makes the code change
3. Verifies via the leg's verification steps
4. Updates `flight-log.md` with progress entry
5. Marks leg `completed` and checks off in `flight.md`

After all legs land:
1. Single Reviewer pass (code correctness)
2. Single doc-refresh pass for any agents.md / CLAUDE.md updates needed
3. Single Reviewer pass on docs (per F6 two-Reviewer-pass methodology)
4. Atomic commit + flight-debrief

### Checkpoints

- [x] Leg 01 completed: tests green on host; ruff in CI
- [x] Leg 02 completed: chat a11y baseline (live region, input label, info-icon button)
- [x] Leg 03 completed: pinned image tags; `.dockerignore`; Playwright pinned
- [x] Leg 04 completed: auto-rollback re-runs health-check; healthcheck timeout fails loudly
- [x] Leg 05 completed: Origin-allowlist middleware; non-https provider URL warning
- [x] Leg 06 completed: Concourse passwords rotated; `.env` updated
- [x] Leg 07 completed: `SECURITY-MODEL.md` shipped; stale agents.md lines fixed

### Adaptation Criteria

**Divert if**:
- Bundle F (credential rotation) discovers the local Concourse instance is in a state requiring more than password update (e.g., team config drift) — surface as a separate follow-up, do not expand scope mid-flight
- Bundle B (a11y) reveals more than the 3 Action Required items need fixing for the chat surface to be coherent — defer additional polish to a future a11y flight
- Any leg requires schema migration or new dependencies — STOP, surface as out-of-flight-scope

**Acceptable variations**:
- Image tag pins in Bundle C may be `@sha256:...` digests OR specific semver tags; choice is implementer's based on registry availability
- Bundle E middleware may live in `the_one/interfaces/web/api.py` as a function or in a new `the_one/interfaces/web/middleware.py` — implementer's call

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `01-tests-green-and-lint-gate` - Add `--font-size-h3`; reparametrize cwd test; CI runs ruff; exclude `workspace/`
- [x] `02-chat-a11y-baseline` - Chat log live region; chat input label; info-icon as focusable button
- [x] `03-ci-image-pinning-and-dockerignore` - Pin pipeline image tags; pin Playwright in pyproject; add `.dockerignore`
- [x] `04-auto-rollback-correctness` - Re-run health-check after rollback; healthcheck timeout fails loudly
- [x] `05-web-side-cheap-hardening` - Origin-allowlist middleware; non-https provider URL warning
- [x] `06-credential-rotation` - Rotate local Concourse + admin passwords; update `.env`
- [x] `07-posture-documentation` - `SECURITY-MODEL.md` + stale agents.md line cleanup

---

## Post-Flight

### Completion Checklist

- [x] All 7 legs completed
- [ ] Code merged to `main` via PR
- [x] `pytest` green (host + container)
- [x] Browser tests green
- [x] `ruff check` and `ruff format --check` clean
- [x] Documentation updated (agents.md, SECURITY-MODEL.md)
- [x] Maintenance report 2026-05-04.md updated to mark resolved findings

### Verification

To confirm the flight achieved its objective:

1. **Tests green on host**: from project root, `pytest -q --ignore=tests/browser` returns 0 failures.
2. **CI runs ruff**: `ci/pipeline.yml` includes a `ruff check` and `ruff format --check` step before pytest; pipeline file referenceable from a Concourse build log shows the lint step passing.
3. **Chat a11y**: keyboard-only navigation reaches every interactive element in the chat surface; screen-reader announces agent message arrival via the live region; info-icon tooltips are reachable and announced via the focusable button + aria-describedby pattern.
4. **CI hardening**: `cat ci/pipeline.yml | grep -E "image:|tag:"` shows no `latest` or floating tags; `cat .dockerignore` lists at minimum `.env*`, `.git/`, `workspace/`, `.memory/`, `.pytest_cache/`.
5. **auto-rollback**: simulated rollback (forced healthcheck failure) results in a deployment that has BOTH rolled back AND re-verified health; `auto-rollback` exits non-zero if rollback's healthcheck fails.
6. **Origin-allowlist**: a `curl -H "Origin: http://evil.example.com" -X POST http://127.0.0.1:8484/api/encryption/rotate` returns 403/4xx; same call without Origin or with `http://127.0.0.1:8484` succeeds (modulo other auth-state). HTTP `GET` requests are not gated.
7. **Provider URL warning**: saving a provider with `base_url=http://example.com` (non-localhost) surfaces a UI warning (or 422 if refused); `base_url=http://localhost:11434` (Ollama default) does not warn.
8. **Credentials rotated**: `fly -t local login -p '<NEW>'` succeeds; the old password (in git history) does not. `.env` reflects the new password.
9. **SECURITY-MODEL.md exists**: a top-level `SECURITY-MODEL.md` (or `agents.md` section) describes the no-auth posture, single-user local-only deployment, and `0.0.0.0` dev-mode bind expectation. `agents.md:3` and `:263-264` no longer reference outdated mission/design phrasing.

# Flight Debrief: Pre-Mission-06 Quick Wins

**Date**: 2026-05-04
**Flight**: [Pre-Mission-06 Quick Wins](flight.md)
**Status**: landed
**Duration**: 2026-05-04 (single-session)
**Legs Completed**: 7 of 7

## Outcome Assessment

### Objectives Achieved

All 7 legs landed in a single deferred-commit at `d813370` (PR #25). 14 Action Required findings from `maintenance/2026-05-04.md` are closed:

- **Tests + lint gate** (Leg 01): host-runnable pytest; ruff `check` + `format --check` chained into CI's existing `sh -c` between `pip install` and `pytest`; `workspace/` excluded via `extend-exclude`.
- **Chat a11y baseline** (Leg 02): `role="log" aria-live="polite"` on chat log; `aria-label="Message"` on input; `field-info-icon` converted from `<span>` to `<button type="button" aria-describedby="…-desc">`.
- **CI hardening** (Leg 03): 7 image references pinned (`docker:25.0.3-cli`, `curlimages/curl:8.6.0`); `playwright==1.58.0` in `pyproject.toml`; `.dockerignore` at repo root.
- **Auto-rollback correctness** (Leg 04): post-rollback health-check loop in `deploy.sh`; `up=true|false` flag with explicit "ERROR: app never came up after 60s" in pipeline; first-deploy diagnostic improved.
- **Web-side hardening** (Leg 05): `OriginAllowlistMiddleware` (ASGI, gates state-mutating HTTP + WS upgrade); `_is_safe_provider_url` enforces https for non-localhost across `create_provider`/`update_provider`/`test_provider`; +27 tests.
- **Credential rotation** (Leg 06): `the-one` team password rotated end-to-end (Vault re-seed + Concourse user pass + `.env`); old password verified rejected; admin pass deferred (cross-project — shared with epipen).
- **Posture documentation** (Leg 07): `SECURITY-MODEL.md` at repo root summarizes-and-links to CLAUDE.md; `agents.md:3` mission-agnostic phrasing; line 433 residual tile-X fragment fixed; `.section-nav-header` and `.section-title` promoted to `<h2>`.

### Mission Criteria Advanced

All 14 success criteria in `missions/06-maintenance/mission.md` are now checked. Mission Flight 1 checkbox checked.

## What Went Well

- **Design-review-per-leg cadence** caught 5+ substantive errors before implementation: leg 03's missed inline `docker:cli` references, leg 04's `${APP_URL}` vs `localhost:8484` distinction, leg 05's wrong test file + 1-of-3 endpoint coverage, leg 07's line-number drift in `agents.md`. Tighter (per-AC) would be wasteful; looser (flight-level only) would have shipped real holes. Right balance.
- **Deferred-commit pattern across 7 legs** produced a single coherent diff and one atomic commit. No mid-flight cleanup commits, no rebase pain. Reviewer pass at flight close was less context-saturated than 7 per-leg passes would have been.
- **Origin-allowlist middleware as ASGI** (revised from initial leg's "Depends() OR ASGI" option) — design-review pass correctly pinned ASGI as REQUIRED because `Depends()` runs after `ws.accept()` and cannot gate WebSocket upgrades. Gate fires at ASGI layer with `{"type":"websocket.close","code":1008}` before the route handler. Subtle catch, real bug avoided.
- **Test quality is uniformly behavioral**, not mock-assertion-shaped. `test_origin_allowlist.py:138-143` (subdomain confusion → 403); `test_origin_allowlist.py:150-162` (WS close 1008 *before* accept asserts code via `WebSocketDisconnect`); `test_provider_api.py:396-437` legacy-row `__MASKED__` case exercises the resolved-base_url contract end-to-end through `repo.create()` + `client.put()`.
- **Leg 06 guided-manual protocol** was the right call. Credential rotation involves live shared infrastructure (concourse-local also serves epipen); spawning an autonomous Developer to touch live secrets would have been wrong. Flight Director walking the operator through 5 confirmed steps preserved safety + auditability.
- **Port-wildcard matcher with strict-digits anti-confusion** in `middleware.py:93-107` is a non-obvious load-bearing detail (rejects `http://127.0.0.1.evil.com` — the `.com` doesn't pass digit-only port match). Carefully-scoped security primitive that won't backfire later.

## What Could Be Improved

### Process

- **Maintenance-report → leg-spec gap is systemic.** Line numbers, helper-function counts, and test file names all drifted between `maintenance/2026-05-04.md` and code at leg-spec time. The maintenance pass was generated *without* re-grepping at leg-spec generation. **Recommendation**: maintenance reports cite **stable identifiers** (function names, route paths, class names) rather than line numbers; OR the leg-generation step (`/leg`) re-grep before locking line numbers.
- **"≤4 file touches" rule too rigid for infrastructure-introducing legs.** Leg 01 modified 5 named files PLUS 74 ruff-formatted files (133 total). The 74 are formatting churn, not semantic edits — but the framing misled. **Recommendation**: reframe as "≤4 *semantically distinct* changes" so format-only files don't count against the budget.
- **"No architectural change" constraint blocked a clean refactor.** `_is_safe_provider_url` running 3× from `create_provider`/`update_provider`/`test_provider` is a DRY violation that an "extract helper to module" change would have resolved. The constraint kept the flight tight, but cost surface-area reduction. **Recommendation**: future maintenance flights allow "extract helper" as in-scope so long as net-LOC is flat or down.

### Technical

- **Provider URL validator at 3 call sites** is borderline DRY violation. A `@router`-level dependency or a Pydantic `field_validator` on `LLMProviderConfig.base_url` could consolidate, but the current shape is what catches the `__MASKED__`-merged update-path case (validator runs on the resolved `base_url` post-`model_copy(update=data)`). Defensible today; revisit if a 4th call site appears.
- **`up=true|false` shell pattern duplicated** in `ci/deploy.sh:28-39` and `ci/pipeline.yml:73-86`. Could become `ci/lib/health-check.sh` sourced from both. Saves 12 lines + one drift risk. Minor.
- **`OPTIONS` not in the gated method list** (`POST/PUT/PATCH/DELETE`) in `OriginAllowlistMiddleware`. If the project ever needs CORS preflight, `OPTIONS` will pass through ungated. Document as known limitation in SECURITY-MODEL.md Future Work.
- **Host-env dependency gap** (`markdownify`, `readability-lxml` missing from `~/.local`) surfaced during leg 01. Lives in `[project.optional-dependencies].dev` but the host's bootstrap is unspecified. Either shift to base deps or document `pip install '.[dev]'` as host bootstrap step in CLAUDE.md.

### Documentation

- **`the_one/agents.md` has no entry for `OriginAllowlistMiddleware` or `_is_safe_provider_url`.** agents.md is the architectural reference; new web-layer surfaces should land there alongside existing FastAPI/SSRF entries.
- **`THE_ONE_ORIGIN_ALLOWLIST` env var is documented only in `.env.example` (commented).** Neither CLAUDE.md nor agents.md calls it out. An operator reading either doc top-to-bottom would not learn this knob exists.
- **`api.py:810` resolved-URL-validation rationale lives only in flight log.** A one-line comment at the call site (`# Validate the *resolved* base_url to handle __MASKED__ legacy rows correctly`) would prevent a future refactor from accidentally validating the request payload instead of the merged model.
- **WebSocket-with-no-Origin behavior is correct but undocumented and untested.** `middleware.py:69` passes through missing-Origin WS upgrades (correct for non-browser clients). No test asserts that branch; if a future change gates missing-Origin WS, it would silently break server-to-server clients.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 01 added `--font-size-h3` to `fonts.css` instead of `tokens.css` | Existing font-size scale lives in `fonts.css`; placing the new token alongside scale-mates is consistent with the project's convention | Yes — co-locate with existing scale-mates over the spec'd file when convention conflicts |
| Leg 02 kept `title=` on the new `<button>` in addition to `aria-describedby` | Existing browser test asserts `title=`; preserving it keeps mouse UX, SR access, AND existing tests all passing | Yes — when test contract intersects a11y, additive (not subtractive) wins |
| Leg 04 manual failure-injection AC deferred to lighter `sh -n` + `fly validate-pipeline` verification | Manual injection requires live Concourse trigger; out-of-scope for the lightweight verification path | Yes — when AC requires live infra, allow design-reviewed fallback-verification |
| Leg 05 expanded validation coverage from 1 endpoint to 3 | Design review caught the `update_provider` `__MASKED__` and `test_provider` paths | Yes — when reviewing a "validate at boundary" change, audit ALL boundary entry points |
| Leg 06 admin password rotation deferred | Admin pass is shared with `epipen` team on local Concourse; rotating it is a separate cross-project decision | No — surface as cross-project follow-up, not a methodology change |
| Leg 07 line-263-264 fix dropped | Lines 263-264 already F6-current; actual stale fragment was at line 433 | Yes — design-review pass should re-grep maintenance-report-cited line numbers as a default check |

## Key Learnings

1. **Stable identifiers > line numbers** for cross-artifact references. Line numbers drift; function names, route paths, class names, and CSS selectors don't.
2. **Design-review pass should always re-grep** any line-number-bearing claim. The leg author's manual citations were wrong in 4 of 7 legs; a 30-second `grep` would have caught all of them.
3. **WS upgrade gating MUST happen at ASGI layer**, not via FastAPI `Depends()`. `Depends()` runs after `accept()`; ASGI middleware runs before. This is a load-bearing distinction for any future WS-gating work in this project.
4. **Validation on the resolved model, not the request payload**, is the right shape when masked/sentinel values are in the merge path. Pydantic validators on the request shape would miss `__MASKED__`-resolved values.
5. **Guided-manual legs are a real protocol category**, not a fallback for "we couldn't automate it." Live secrets, shared infrastructure, and operator-eyes-on-glass scenarios deserve the explicit protocol.
6. **Atomic commit per maintenance flight** beats per-leg commits for diff coherence and review surface — IF the legs are independent (no leg blocks another's review).

## Recommendations

1. **Ship a small `/leg` skill update**: when generating a leg from a maintenance-report finding, the skill should auto-grep cited line numbers and substitute stable identifiers (function name, route path, class name) before locking the leg artifact. Captures the line-number-drift learning as methodology.
2. **Add 4 doc updates as a post-flight micro-leg** (or absorb into Mission 06 Flight 2 if one happens): (a) `agents.md` entry for `OriginAllowlistMiddleware`, (b) `agents.md` entry for `_is_safe_provider_url`, (c) `CLAUDE.md` callout for `THE_ONE_ORIGIN_ALLOWLIST` env var, (d) one-line comment at `api.py:810` for the resolved-URL-validation rationale.
3. **Promote deferred-commit-across-multiple-legs as the default for maintenance flights** in the agentic-workflow skill (it's already supported but not the documented default). Note the constraint: legs must be independent (no leg gates another).
4. **Add 2 tests for explicit edge cases**: (a) WebSocket upgrade with no `Origin` header passes through (locks in the current correct behavior); (b) `test_provider` endpoint passing on a safe URL (symmetry with the rejection test). Both single-line additions to existing test files.
5. **Reframe the "≤4 file touches" leg-budget rule** in the maintenance-mission template to "≤4 semantically distinct changes" so format-only churn doesn't count against the budget. Update the maintenance-report scaffold and `/leg` skill prompt accordingly.

## Action Items

- [ ] Audit maintenance follow-ups: `OPTIONS` method gating; X-Forwarded-Host / trusted-proxy scenarios for the Origin allowlist; admin Concourse password rotation (cross-project with epipen)
- [ ] File the 4 doc updates (Recommendation #2) as a micro-leg or absorb into next maintenance/flight
- [ ] Add the 2 edge-case tests (Recommendation #4) as a one-line micro-leg
- [ ] Surface "stable identifiers > line numbers" finding as input to mission-control's `/leg` and `/routine-maintenance` skill design (Recommendation #1)
- [ ] Update `pyproject.toml` defaults OR document `pip install '.[dev]'` host bootstrap in CLAUDE.md (host-env dependency gap)
- [ ] Mark PR #25 ready for review when human is satisfied with the debrief

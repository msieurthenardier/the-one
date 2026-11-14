# Leg: 03-origin-allowlist-followups

**Status**: completed
**Flight**: [Debrief Follow-ups](../flight.md)

## Objective

Close two open questions about `OriginAllowlistMiddleware` surfaced by Flight 01's debrief: (a) **OPTIONS gating decision: path (b) — document, don't gate** — add a one-line comment near `GATED_METHODS` pointing at `SECURITY-MODEL.md` Future Work; (b) add an X-Forwarded-Host / trusted-proxy posture entry to `SECURITY-MODEL.md` Future Work so a future operator deploying behind a reverse proxy has explicit guidance. Path (b) is locked because gating `OPTIONS` without simultaneously emitting `Access-Control-Allow-Origin` headers would silently break any future CORS preflight (preflight 403s, actual request never fires) — net negative without a real CORS consumer to design against.

## Context

Flight 01 debrief — "Architectural Impact" + "Forward-Looking" sections:

- **`OPTIONS` not in `GATED_METHODS`** (`POST/PUT/PATCH/DELETE` are gated; `OPTIONS` passes through). The current behavior is intentional and tested by `test_options_with_foreign_origin_passes` (`tests/test_origin_allowlist.py:89-96`), which asserts `status_code != 403`. If the project ever needs CORS preflight, gating `OPTIONS` without also adding `Access-Control-Allow-Origin` headers would silently break preflight. Worth a code comment so future readers don't "fix" this without understanding the trap.
- **X-Forwarded-Host scenarios**: the middleware reads the raw `Origin` header — fine for direct binds, but a reverse-proxy operator using `THE_ONE_ORIGIN_ALLOWLIST` may discover their proxy strips/rewrites `Origin` and there's no documentation. `SECURITY-MODEL.md:30` already mentions `THE_ONE_ORIGIN_ALLOWLIST` as the proxy-extension mechanism; the new Future Work entry must explicitly distinguish "proxy preserves Origin → use env var" from "proxy strips Origin → see Future Work".

Per flight design decision (Bundle C): document, don't implement. The project deploys behind no proxy today; trusted-proxy support is hypothetical. Implementing `X-Forwarded-Host` parsing without a real consumer is YAGNI.

## Inputs

- `the_one/interfaces/web/middleware.py` (existing; `GATED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})` is a class attribute on `OriginAllowlistMiddleware` at L54; class docstring at L34-35 lists `GET/HEAD/OPTIONS: never gated` and stays correct for path (b))
- `tests/test_origin_allowlist.py` (existing; uncommitted Leg 02 added `test_websocket_with_no_origin_passes` at L171-184; `test_options_with_foreign_origin_passes` at L89-96 already asserts the path-b behavior; per-method 403 tests at L98 (POST), L105 (PUT), L111 (DELETE) — note PATCH coverage is missing in the existing rejection-path tests, but that gap is pre-existing and out of scope for this leg)
- `SECURITY-MODEL.md` (existing; `## Future Work (NOT in scope today)` heading at L116; 3 existing bullets at L118-125 in `- **Title**: body` pattern; L30 already mentions reverse-proxy `THE_ONE_ORIGIN_ALLOWLIST` extension)

## Outputs

- `the_one/interfaces/web/middleware.py` has a one-line comment immediately above `GATED_METHODS` (currently L54) explaining why `OPTIONS` is intentionally absent and pointing at `SECURITY-MODEL.md` Future Work
- `SECURITY-MODEL.md` `## Future Work (NOT in scope today)` section has two new bullets following the existing `- **Title**: body` pattern:
  - `- **CORS / OPTIONS preflight**: ...`
  - `- **X-Forwarded-Host / trusted proxy**: ...`

## Acceptance Criteria

- [x] `grep -B 1 -A 1 "GATED_METHODS = " the_one/interfaces/web/middleware.py` shows a comment line referencing `SECURITY-MODEL.md` Future Work immediately above the `GATED_METHODS` definition
- [x] `grep -A 6 "CORS / OPTIONS preflight" SECURITY-MODEL.md` returns the new bullet under the `## Future Work (NOT in scope today)` heading, with ≥2 sentences explaining current state + future-decision criteria
- [x] `grep -A 6 "X-Forwarded-Host" SECURITY-MODEL.md` returns the new bullet, explicitly distinguishing the "proxy preserves Origin → use env var" path (already documented at L30) from the "proxy strips Origin → see Future Work" path
- [x] `grep -n "## Future Work" SECURITY-MODEL.md` confirms the new bullets land under the correct heading (not stranded above/below it)
- [x] No regression: `pytest tests/test_origin_allowlist.py -v --timeout=60` green (all existing tests including `test_options_with_foreign_origin_passes` still pass — path-b leaves behavior unchanged); full `pytest -q --ignore=tests/browser --timeout=120` green
- [x] Ruff lint + format clean: `ruff check the_one/ tests/ && ruff format --check the_one/ tests/`

## Verification Steps

- `cd ~/projects/the-one && grep -B 1 -A 1 "GATED_METHODS = " the_one/interfaces/web/middleware.py`
- `cd ~/projects/the-one && grep -n "## Future Work" SECURITY-MODEL.md`
- `cd ~/projects/the-one && grep -A 6 "CORS / OPTIONS preflight" SECURITY-MODEL.md`
- `cd ~/projects/the-one && grep -A 6 "X-Forwarded-Host" SECURITY-MODEL.md`
- `cd ~/projects/the-one && pytest tests/test_origin_allowlist.py -v --timeout=60 2>&1 | tail -20`
- `cd ~/projects/the-one && pytest -q --ignore=tests/browser --timeout=120 2>&1 | tail -5`
- `cd ~/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/`

## Implementation Guidance

> **Note**: design review verified all line numbers below as of branch `flight/02-debrief-followups` HEAD. Re-grep right before each edit if the working tree has drifted.

1. **Add the OPTIONS-rationale comment in `middleware.py`**:
   - Re-grep `GATED_METHODS = ` to confirm location (was L54).
   - Insert a one-line comment immediately above the `GATED_METHODS = ` line:
     ```python
     # OPTIONS intentionally NOT gated — see SECURITY-MODEL.md "Future Work"
     # (CORS / OPTIONS preflight). Gating without Access-Control-Allow-Origin
     # headers would silently break any future preflight.
     GATED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
     ```
   - Three lines is fine (the surrounding class docstring is multi-line). The class docstring at L34-35 already lists `GET/HEAD/OPTIONS: never gated` — leave it untouched since path (b) preserves that behavior.

2. **Add two `SECURITY-MODEL.md` Future Work bullets**:
   - Re-grep `## Future Work` to confirm location (was L116) and read the existing 3 bullets to confirm style (`- **Title**: body`, ~3-4 wrapped lines each).
   - Append two new bullets to the existing list (after the "Multi-user form factor" bullet — keep the X-Forwarded-Host bullet last since it most closely echoes the reverse-proxy mention at L30):
     ```markdown
     - **CORS / OPTIONS preflight**: `OriginAllowlistMiddleware` does not
       gate `OPTIONS` requests (see code comment above `GATED_METHODS` in
       `the_one/interfaces/web/middleware.py`). The project has no CORS
       need today (single-origin local-only). If a CORS need arises, gate
       `OPTIONS` AND emit explicit `Access-Control-Allow-Origin` headers
       from a dedicated CORS middleware. Do NOT enable wildcard CORS —
       preserve the same-origin posture.
     - **X-Forwarded-Host / trusted proxy**: the middleware reads the raw
       `Origin` request header. The reverse-proxy guidance at L30 above
       assumes the proxy preserves `Origin` end-to-end (most modern
       proxies do). If the proxy strips or rewrites `Origin`, the
       operator must either (a) configure the proxy to forward it, or
       (b) replace the middleware with one that consults `X-Forwarded-Host`
       after explicitly validating the proxy's trustworthiness (e.g. via
       IP allowlist on the proxy's source). The current single-user
       local-only deployment has no proxy and does not need this.
     ```

3. **Verify**:
   - Run the Origin-allowlist test file in isolation — all 19 tests (18 baseline + Leg 02's WS-no-Origin) should still pass; `test_options_with_foreign_origin_passes` proves path-b leaves behavior unchanged.
   - Run full suite for regression check.
   - Confirm both new bullets land under `## Future Work (NOT in scope today)` (not above it).

## Edge Cases

- **`SECURITY-MODEL.md:30` reverse-proxy mention**: explicitly distinguish from the new X-Forwarded-Host bullet — L30 covers "operator extends allowlist via env var when proxy preserves Origin"; the new bullet covers "proxy strips/rewrites Origin and the env-var path is insufficient". The new bullet's wording must reference L30's existing guidance to avoid the appearance of contradiction.
- **Class docstring at L34-35 lists `OPTIONS: never gated`** — path (b) preserves this, so leave the docstring as-is. (If a future operator chooses path (a), they must update both the docstring AND `test_options_with_foreign_origin_passes` at `tests/test_origin_allowlist.py:89-96`. That's not in scope here.)
- **`SECURITY-MODEL.md` Future Work section may have grown**: re-grep `## Future Work` before inserting — branch HEAD has 3 bullets but a future change could add more.

## Files Affected

- `the_one/interfaces/web/middleware.py` — 3-line comment immediately above `GATED_METHODS = ` (no functional change)
- `SECURITY-MODEL.md` — 2 new Future Work bullets (~12 lines total, following existing `- **Title**: body` pattern)
- *(no test changes — `test_options_with_foreign_origin_passes` already locks in path-b behavior)*

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] OPTIONS-rationale comment added in `middleware.py` immediately above `GATED_METHODS`
- [x] Two Future Work bullets added in `SECURITY-MODEL.md` under `## Future Work (NOT in scope today)`
- [x] Tests green (regression check) — all existing OPTIONS / per-method tests still pass
- [x] Ruff lint + format clean
- [x] Update flight-log.md with leg progress entry (record path-b decision rationale: gating OPTIONS without CORS headers is a footgun)
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md (Checkpoints AND Legs lists; Contributing-to-Criteria items for OPTIONS + X-Forwarded-Host)
- [ ] DO NOT commit — deferred to flight close

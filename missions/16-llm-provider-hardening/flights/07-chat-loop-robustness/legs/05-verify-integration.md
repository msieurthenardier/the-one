# Leg: verify-integration

**Status**: completed
**Flight**: [Chat-loop Robustness & Control](../flight.md)

## Objective
Confirm the flight's changes pass the full regression suite + lint, behavior-test
spec authored, and resolve the `web_search` open question.

## Acceptance Criteria
- [x] Full unit suite green at/above the M16 baseline, no new flakes.
- [x] Lint (ruff check + format) clean tree-wide.
- [x] Behavior-test spec `tests/behavior/chat-loop-hang-and-cancel.md` authored
      (run is part of leg 06 HAT, against a live :8485 instance).
- [x] `web_search` "No results found" question resolved (split — see below).
- [x] Docs: `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS` documented in-code (no central
      env-var doc exists in this project; recurring debt noted in the F05 debrief).

## Outcome
- **Full suite**: `3489 passed, 10 skipped, 595 deselected, 0 failures, 19 warnings`
  (pre-existing deprecations), 325s. Baseline (post-PR#135) was `3448` — +41 tests
  from this flight (web_tools +9, tool_call_timeout +13, cancel +14, plus updates).
  Skip count stable at 10; no new flakes.
- **Lint**: `ruff check the_one/ tests/` → all checks passed; `ruff format --check`
  → 385 files already formatted.
- **Flight-wide review** (Sonnet): `[HANDOFF:confirmed]` — all four legs meet
  acceptance criteria, tests non-tautological, one non-blocking note (a minor
  timeout-message diagnostic inaccuracy when the wall-clock deadline fires; no
  behavior regression).
- **`web_search` split**: it uses DuckDuckGo HTML scraping (no key); "No results
  found" is DDG throttling the scrape — out of scope for this flight (hang/cancel/
  queue). Recorded as a mission Known Issue + carried to `/mission-debrief`.

## Files Affected
- (verification only — no source changes in this leg)

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing (full suite)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed`

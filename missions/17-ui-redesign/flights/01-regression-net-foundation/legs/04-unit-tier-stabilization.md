# Leg: unit-tier-stabilization

**Status**: completed
**Flight**: [Regression-Net Foundation](../flight.md)

## Objective

Fix the pre-existing unit-tier ordering flake (`tests/test_lifespan.py::test_lifespan_drains_session_registry`) and clear the pre-existing ruff-format drift in six committed files, so `make test-unit` and `ruff format --check` are unconditionally green gates for the rest of the mission.

## Context

- Added mid-flight by Flight Director decision after Leg 01 surfaced both issues (see flight-log Decisions). This flight's objective is a trustworthy net; a flaky default-tier test and a dirty format gate poison every later flight's verification.
- Flake evidence (Leg 01): fails under full-suite ordering with `RuntimeError: session registry is shutting down` (leftover registry shutdown state from an earlier test); passes in isolation; reproduced with Leg-01 files removed (pre-existing).
- Format drift files: `tests/browser/test_flow_provider_editor.py`, `tests/test_anthropic_live.py`, `tests/test_anthropic_provider.py`, `tests/test_db_codec.py`, `tests/test_provider_api.py`, `the_one/interfaces/web/app.py`.

## Inputs

- `tests/test_lifespan.py` — the flaky test and its fixtures
- Whatever module leaves session-registry shutdown state behind (find it: run the unit tier with `-p no:randomly` if applicable / bisect test ordering, or grep for session-registry shutdown paths in tests and `the_one/`)

## Outputs

- Root-caused isolation fix: the test (or the offending earlier test's teardown) resets/reinitializes the session registry state so ordering no longer matters. Product-code changes are acceptable ONLY if the root cause is a genuine missing reset seam and the fix is minimal and behavior-preserving; prefer test/fixture-level fixes.
- Six files reformatted (`ruff format` — format-only, no logic edits).
- CLAUDE.md testing section: one-line note that full `make test-browser` runs need `TEST_TIMEOUT=3600` (default 1200s is tighter than the ~12.5min suite runtime plus load overhead) — FD-added scope after Leg 02.

## Acceptance Criteria

- [x] `make test-unit` fully green (0 failures) run twice consecutively (3681 passed / 10 skipped, both runs)
- [x] `tests/test_lifespan.py` passes both in isolation AND in full-tier ordering
- [x] `ruff format --check the_one/ tests/` clean tree-wide (396 files already formatted)
- [x] `ruff check the_one/ tests/` clean
- [x] CLAUDE.md notes the `TEST_TIMEOUT=3600` recommendation for full browser-suite runs
- [x] No behavior changes: format-only diffs in the six drift files (verified format-only via AST equality against HEAD for all six)

## Verification Steps

- `make test-unit` twice; `git diff --stat` on the six files shows format-only churn
- `.venv/bin/python -m pytest tests/test_lifespan.py -x --timeout 60` green; then full tier green

## Implementation Guidance

1. Reproduce the flake deterministically first (full tier or a bisected subset). Identify which earlier test leaves the registry in shutdown state.
2. Prefer a fixture/teardown fix (reset the registry singleton state after the offending test or in the lifespan test's setup). A conftest-level autouse guard is acceptable if narrowly scoped with a comment.
3. Do not mark the test flaky/skip/xfail — the point is to fix the isolation.
4. `ruff format` the six files; verify no non-format changes sneak in.

## Edge Cases

- **Root cause is a product-code global singleton without a reset seam**: add the minimal reset hook (test-only usage), document it, and note it in the flight log.
- **Flake stops reproducing**: still find the mechanism (grep the registry shutdown path); an unreproduced flake is not fixed. If genuinely unreproducible after honest effort, document the investigation and add a targeted isolation guard anyway.

## Files Affected

- `tests/test_lifespan.py` and/or the offending test module / conftest
- The six format-drift files (format-only)

---

## Citation Audit

Flake behavior and drift file list sourced from Leg 01's flight-log entry (same flight, same day — no drift risk). Not re-verified independently; the implementing Developer reproduces the flake as step 1, which is the real verification.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md

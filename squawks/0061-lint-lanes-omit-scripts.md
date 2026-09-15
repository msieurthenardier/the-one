# Squawk 0061: Lint lanes do not run ruff over `scripts/`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

`make lint`/`make format`, `ci/tasks/lint.yml` and `.github/workflows/lint.yml` run ruff over `the_one/ tests/` only. `scripts/` now holds a 900-line benchmark (Flight 2 Leg 5) and the model-refresh generator; the Flight 2 reviewers had to run `ruff check scripts/` by hand. Add `scripts/` to every ruff invocation (Makefile `lint`/`format`/`format-check`, both CI lanes, and the pre-commit config if it lists paths). Parked at Leg 5 design review.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `Makefile:249,253,257` — `ruff check the_one/ tests/` etc.
- `ci/tasks/lint.yml:25-26`; `.github/workflows/lint.yml:22` onward.
- `ruff check scripts/` and `ruff format --check scripts/` are clean today (verified during Flight 2 Leg 6), so the change adds no red.

## Corrective Action
*(written at completion)*

## Verification
`make lint` covers `scripts/` and is clean; the Concourse `lint` job is green on the next push to `main`.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

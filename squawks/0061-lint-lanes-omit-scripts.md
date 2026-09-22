# Squawk 0061: Lint lanes do not run ruff over `scripts/`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

`make lint`/`make format`, `ci/tasks/lint.yml` and `.github/workflows/lint.yml` run ruff over `the_one/ tests/` only. `scripts/` now holds a 900-line benchmark (Flight 2 Leg 5) and the model-refresh generator; the Flight 2 reviewers had to run `ruff check scripts/` by hand. Add `scripts/` to every ruff invocation (Makefile `lint`/`format`/`format-check`, both CI lanes, and the pre-commit config if it lists paths). Parked at Leg 5 design review.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `Makefile:249,253,257` — `ruff check the_one/ tests/` etc.
- `ci/tasks/lint.yml:25-26`; `.github/workflows/lint.yml:22` onward.
- `ruff check scripts/` and `ruff format --check scripts/` are clean today (verified during Flight 2 Leg 6), so the change adds no red.

## Corrective Action

Added `scripts/` to every ruff invocation that previously listed `the_one/ tests/`
only:

- `Makefile` — `lint`, `format`, `format-check` targets (lines 249, 253, 257).
- `ci/tasks/lint.yml` — the `ruff check` / `ruff format --check` lines (25-26) and
  the header comment (line 3).
- `.github/workflows/lint.yml` — the "Ruff check" / "Ruff format check" steps.
- `.github/workflows/pr-lint.yml` — its "Ruff check" / "Ruff format check" steps
  (~36-40).
- `ci/README.md` — the "Pre-merge lint + audit gate" section's quoted `ruff`
  commands (line 44), which mirror `pr-lint.yml` and had drifted out of sync
  the same way.
- `CLAUDE.md`'s "Commands" section — the quoted `ruff check`/`ruff format`
  lines and the "Lint/format gate" paragraph's quoted commands.

`.pre-commit-config.yaml` needed no change: its `ruff`/`ruff-format` hooks list no
file-path args at all (comment on line 3 confirms this deliberately — "no custom
file args") and pre-commit already runs against the files it's given / the whole
tree, so it already covers `scripts/`.

`pyproject.toml`'s `[tool.ruff]` needed no change: it has no `include`/`files`
allowlist, only `extend-exclude = ["workspace"]`, so `scripts/` was never excluded
there — the gap was purely in the invocation command lines, not the tool config.

## Verification

- `make lint` and `make format-check` both run with `scripts/` appended and pass
  clean (`All checks passed!`; `427 files already formatted`).
- `python3 -c "import yaml; yaml.safe_load(open('ci/tasks/lint.yml'))"` and the
  same for `.github/workflows/lint.yml` and `.github/workflows/pr-lint.yml` all
  load without error.
- `ruff check scripts/` and `ruff format --check scripts/` are clean, confirming
  the Flight 2 Leg 6 finding still holds.
- `grep -rn "ruff" Makefile ci/ .github/ CLAUDE.md .pre-commit-config.yaml` shows
  every `ruff check`/`ruff format` invocation now includes `scripts/`; no
  remaining `the_one/ tests/`-only line.

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet, batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: ba46d62
